"""A trade whose target nobody owns must still close.

`manager_owns_target()` hands the TARGET side of a v2 trade to plan_manager
and keeps only the stop side as a legacy backstop. But `PlanManager.poll()`
walks `store.open_plans()` -- so if the plan behind the trade is missing from
plans.json or already terminal, the handover is to nobody: the legacy loops
skip the target because a `plan_id` is set, and the manager never sees the
plan. The trade then sits open straight through its own target forever and
only a stop-out can close it.

Observed live 2026-08-04 on the admin dashboard, which renders SL=0% / TP=100%
for an open trade: GOOGL `p5LTtQ06` (plan 769f9e58) and RKLB `nsj3TwaM` (plan
c7aa1f86) were both open against a plan_id absent from the store.

The same pass found the other half of it: AVGO plan `47def9d0` owned TWO open
trades, and both `close_plan_trade` and `append_leg_by_plan` picked the first
by `next()`. So the manager closed one, the plan went terminal, and the
leftover trade became exactly the orphan above -- unclosable by target from
then on.
"""
import json
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.core.performance import TradeLog, manager_owns_target
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_store import PlanStore
from tests.conftest import make_ohlcv
from tests.fixtures.gate.plans import make_plan


def _trade(tid="t1", plan_id="p_test_0001"):
    t = {"id": tid, "ticker": "TEST", "direction": "bullish", "status": "open",
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "opened_at": "2026-07-01T10:00:00+00:00"}
    if plan_id:
        t["plan_id"] = plan_id
    return t


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Same shape as tests/test_plan_orphaning.py's fixture: TradeLog and
    PlanStore both on tmp, journal off the network, and the lazily-imported
    PlanStore (in _open_plan_ids / _close_plan_safely) pointed at the same
    tmp store the test asserts against."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(
        "swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    plan_store = PlanStore(path=str(tmp_path / "plans.json"))
    monkeypatch.setattr("swingbot.core.plan_store.PlanStore",
                        lambda *a, **k: plan_store)

    def _make(trades, plans=()):
        for p in plans:
            plan_store.add(p)
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(trades))
        return TradeLog(path=str(path)), plan_store

    return _make


def _plan(**kw):
    return make_plan(entry_price=100.0, stop_loss=95.0, tp1=110.0, **kw)


# -- ownership predicate ---------------------------------------------------

def test_ownership_requires_a_plan_the_manager_will_actually_poll(env):
    """The whole bug in one assertion: a plan_id alone is not ownership."""
    env([_trade()], [])          # trade references a plan that isn't stored
    assert manager_owns_target(_trade()) is False


def test_open_plan_is_still_owned_by_the_manager(env):
    """V4 Step 2 must not regress -- with a live plan the legacy loop still
    keeps its hands off the target so scale-out can happen."""
    env([_trade()], [_plan(status=PlanStatus.ACTIVE)])
    assert manager_owns_target(_trade()) is True


@pytest.mark.parametrize("status", [PlanStatus.CLOSED, PlanStatus.CANCELLED])
def test_terminal_plan_is_not_owned(env, status):
    env([_trade()], [_plan(status=status)])
    assert manager_owns_target(_trade()) is False


def test_unreadable_plan_store_keeps_the_old_behaviour(env, monkeypatch):
    """A transient read error must not resurrect the double-close that
    manager_owns_target exists to prevent -- unknown means 'leave it with
    the manager', not 'close it here'."""
    env([_trade()], [_plan(status=PlanStatus.ACTIVE)])

    def boom(*a, **k):
        raise RuntimeError("plans.json is unreadable")

    monkeypatch.setattr("swingbot.core.plan_store.PlanStore", boom)
    assert manager_owns_target(_trade()) is True


# -- the close paths -------------------------------------------------------

def test_live_price_closes_an_orphaned_trade_at_its_target(env):
    """The reported symptom: 100% on the dashboard, never closes."""
    log, _ = env([_trade()], [])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=111.0)

    assert [t["status"] for t in closed] == ["win"]


def test_bar_scan_closes_an_orphaned_trade_at_its_target(env):
    log, _ = env([_trade()], [])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.update_open_trades(
            "TEST", make_ohlcv([112.0], spread_pct=4.0, start="2026-07-02"))

    assert [t["status"] for t in closed] == ["win"]


def test_managed_trade_is_still_left_for_the_manager(env):
    """Guard against over-correcting: a live plan's target stays untouched."""
    log, _ = env([_trade()], [_plan(status=PlanStatus.ACTIVE)])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=111.0)

    assert closed == []
    assert log.get_trade_by_id("t1")["status"] == "open"


# -- a plan owning more than one open trade --------------------------------

def test_close_plan_trade_closes_every_open_trade_for_the_plan(env):
    """AVGO 47def9d0: two open trades, one plan. Closing the first and
    leaving the second is what manufactured the orphan in the first place."""
    log, _ = env([_trade("t1"), _trade("t2")],
                 [_plan(status=PlanStatus.ACTIVE)])

    log.close_plan_trade("p_test_0001",
                         {"fraction": 1.0, "exit_price": 110.0,
                          "r": 2.0, "reason": "tp1_runner"},
                         "win")

    assert [log.get_trade_by_id(i)["status"] for i in ("t1", "t2")] == \
        ["win", "win"]


def test_append_leg_by_plan_legs_every_open_trade_for_the_plan(env):
    log, _ = env([_trade("t1"), _trade("t2")],
                 [_plan(status=PlanStatus.ACTIVE)])

    log.append_leg_by_plan("p_test_0001",
                           {"fraction": 0.5, "exit_price": 110.0,
                            "r": 2.0, "reason": "tp1"})

    assert [len(log.get_trade_by_id(i)["legs"]) for i in ("t1", "t2")] == [1, 1]


def test_close_plan_trade_leaves_already_closed_trades_alone(env):
    """Only OPEN trades are touched -- a plan whose trade closed earlier must
    not be reopened or double-settled."""
    already = _trade("t1")
    already.update(status="loss", exit_price=95.0)
    log, _ = env([already, _trade("t2")], [_plan(status=PlanStatus.ACTIVE)])

    log.close_plan_trade("p_test_0001",
                         {"fraction": 1.0, "exit_price": 110.0,
                          "r": 2.0, "reason": "tp1_runner"},
                         "win")

    assert log.get_trade_by_id("t1")["status"] == "loss"
    assert log.get_trade_by_id("t2")["status"] == "win"
