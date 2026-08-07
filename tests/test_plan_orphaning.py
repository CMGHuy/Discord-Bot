"""A legacy close path must close the PLAN too, not just the trade.

Only plan_manager transitions plans, but three paths in performance.py close
a manager-owned trade without it: the stop-side backstop in
`close_if_live_price_hit` and `update_open_trades` (the target side is handed
over, the stop side deliberately is not -- see manager_owns_target), and the
admin UI's manual Close button. Each one left the plan ACTIVE forever: still
polled every manager tick, still shown as live in the admin UI and /plans,
and with its trade-log hooks silently no-opping because append_leg_by_plan /
close_plan_trade both require a still-OPEN trade.

Observed live 2026-08-04 -- plan 6341bd00 (MRNA) sat ACTIVE against a trade
already closed as `loss`. Recorded in plan v8's Progress block as "a second,
pre-existing bug ... Not yet fixed".
"""
import json
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.core.performance import TradeLog
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_store import PlanStore
from tests.conftest import make_ohlcv
from tests.fixtures.plans import make_plan


def _trade(plan_id="p_test_0001", direction="bullish"):
    t = {"id": "t1", "ticker": "TEST", "direction": direction, "status": "open",
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "opened_at": "2026-07-01T10:00:00+00:00"}
    if direction == "bearish":
        t.update(stop_loss=105.0, take_profit=90.0)
    if plan_id:
        t["plan_id"] = plan_id
    return t


@pytest.fixture
def env(tmp_path, monkeypatch):
    """TradeLog + PlanStore both on tmp, journal pinned off the network, and
    the lazily-imported PlanStore inside _close_plan_safely redirected to the
    same tmp store the test asserts against."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(
        "swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    plan_store = PlanStore(path=str(tmp_path / "plans.json"))
    monkeypatch.setattr("swingbot.core.plan_store.PlanStore",
                        lambda *a, **k: plan_store)

    def _make(trades, plan=None):
        if plan is not None:
            plan_store.add(plan)
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(trades))
        return TradeLog(path=str(path)), plan_store

    return _make


def _active(status=PlanStatus.ACTIVE, **kw):
    return make_plan(status=status, entry_price=100.0,
                     stop_loss=95.0, tp1=110.0, **kw)


# -- the three orphaning paths ---------------------------------------------

def test_live_price_stop_backstop_closes_the_plan(env):
    log, store = env([_trade()], _active())
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=94.0)

    assert [t["status"] for t in closed] == ["loss"]
    plan = store.get("p_test_0001")
    assert plan.status == PlanStatus.CLOSED
    assert plan.status_history[-1]["reason"] == "stop_backstop"


def test_bar_scan_stop_backstop_closes_the_plan(env):
    log, store = env([_trade()], _active())
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.update_open_trades(
            "TEST", make_ohlcv([93.0], spread_pct=4.0, start="2026-07-02"))

    assert [t["status"] for t in closed] == ["loss"]
    assert store.get("p_test_0001").status == PlanStatus.CLOSED


def test_manual_close_closes_the_plan(env):
    """A human closing the trade closes the thesis -- otherwise the manager
    keeps managing a position that no longer exists."""
    log, store = env([_trade()], _active())
    assert log.close_trade_manual("t1") is True

    plan = store.get("p_test_0001")
    assert plan.status == PlanStatus.CLOSED
    assert plan.status_history[-1]["reason"].startswith("manual_close:")


def test_partial_plan_is_closed_too(env):
    """PARTIAL -> CLOSED is legal: a runner stopped out by the backstop after
    TP1 banked must not strand the plan either."""
    log, store = env([_trade()], _active(status=PlanStatus.PARTIAL))
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        log.close_if_live_price_hit("TEST", live_price=94.0)

    assert store.get("p_test_0001").status == PlanStatus.CLOSED


def test_legacy_target_close_also_closes_the_plan(env, monkeypatch):
    """With the manager OFF the legacy loop owns the target as well, so that
    close must transition the plan too."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    log, store = env([_trade()], _active())
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=111.0)

    assert [t["status"] for t in closed] == ["win"]
    plan = store.get("p_test_0001")
    assert plan.status == PlanStatus.CLOSED
    assert plan.status_history[-1]["reason"] == "target_backstop"


# -- cases that must NOT transition ----------------------------------------

def test_pending_plan_is_left_alone(env):
    """PENDING -> CLOSED is not a legal transition; record_transition would
    raise. The close must still succeed."""
    log, store = env([_trade()], _active(status=PlanStatus.PENDING))
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=94.0)

    assert [t["status"] for t in closed] == ["loss"]
    assert store.get("p_test_0001").status == PlanStatus.PENDING


def test_plan_the_manager_already_closed_is_not_transitioned_twice(env):
    """The normal case: the manager got there first. No second CLOSED entry."""
    log, store = env([_trade()], _active(status=PlanStatus.CLOSED))
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        log.close_if_live_price_hit("TEST", live_price=94.0)

    plan = store.get("p_test_0001")
    assert plan.status == PlanStatus.CLOSED
    assert [h for h in plan.status_history
            if h.get("reason") == "stop_backstop"] == []


def test_trade_without_a_plan_is_unaffected(env):
    log, store = env([_trade(plan_id=None)])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=94.0)

    assert [t["status"] for t in closed] == ["loss"]
    assert store.all() == []


def test_a_plan_store_failure_never_breaks_the_trade_close(env, monkeypatch):
    """Plan bookkeeping is best-effort -- same contract as the journal hook.
    A broken PlanStore must not strand the trade open."""
    log, _ = env([_trade()], _active())

    def boom(*a, **k):
        raise RuntimeError("plans.json is unreadable")

    monkeypatch.setattr("swingbot.core.plan_store.PlanStore", boom)
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("TEST", live_price=94.0)

    assert [t["status"] for t in closed] == ["loss"]
    assert log.get_trade_by_id("t1")["status"] == "loss"
