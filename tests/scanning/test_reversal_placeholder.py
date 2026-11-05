"""v189 A1: a reversal never books P&L on a never-filled placeholder.

A stop-entry plan's trade row is logged while the plan is still PENDING. When
an opposite setup reverses the ticker before the order fills, there is no
position to close: the plan is cancelled and the placeholder discarded, with
no P&L and no balance point. The "never filled" check runs under the plan row
lock, so a fill the poll records meanwhile turns it into the real position it
is, closed and settled with its plan in one transaction.
"""
import inspect

import pytest

from swingbot.core.db.engine import LockTimeout
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import scan_run
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store


@pytest.fixture
def tlog(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _pending():
    return _plan(entry_type="stop_entry")          # PENDING, plan_id "p1"


def _filled():
    plan = _plan(entry_type="stop_entry", entry_price=100.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill",
                      at="2026-10-20T14:00:00+00:00")
    return plan


def _open_trade(tl, plan) -> dict:
    """The trade the scan reads with open_trade_for_ticker before reversing."""
    PlanStore().add(plan)
    tid = tl.log_trade(ticker=plan.ticker, strategy="RSI", horizon_key="2w",
                       direction="bullish", confidence_level=3, confidence_label="Medium",
                       entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)
    return tl.get_trade_by_id(tid)


@pytest.mark.parametrize("live_price", [97.5, None])
def test_a_reversal_against_a_placeholder_books_nothing_and_cancels_the_plan(tlog, live_price):
    existing = _open_trade(tlog, _pending())
    settled = scan_run._settle_reversal(tlog, existing, live_price)
    assert settled is not None and settled["status"] == "discarded"
    plan = PlanStore().get("p1")
    assert plan.status == "CANCELLED"
    assert plan.status_history[-1]["reason"] == "reversed"
    assert tlog.trade_for_plan("p1") is None
    assert tlog.get_trades(status=None, limit=None) == []
    assert account_module.get_balance_history() == []


def test_a_plan_that_filled_meanwhile_is_reversed_as_the_real_position(tlog):
    """`existing` was read while the plan was PENDING; the poll fills it before
    the reversal takes the lock. The locked check sees ACTIVE and books it."""
    existing = _open_trade(tlog, _pending())
    plan = PlanStore().get("p1")
    plan.entry_price = 100.0
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill",
                      at="2026-10-20T14:00:00+00:00")
    PlanStore().update(plan)
    tlog.record_plan_fill("p1", 100.0)

    settled = scan_run._settle_reversal(tlog, existing, 97.5)
    assert (settled["status"], settled["close_reason"]) == ("closed", "reversed")
    assert settled["realized_pnl_amount"] < 0
    assert PlanStore().get("p1").status == "CLOSED"
    assert len(account_module.get_balance_history()) == 1


@pytest.mark.parametrize("live_price", [None, 0.0, float("nan")])
def test_no_usable_price_settles_nothing_for_a_real_position(tlog, live_price):
    existing = _open_trade(tlog, _filled())
    assert scan_run._settle_reversal(tlog, existing, live_price) is None
    assert tlog.trade_for_plan("p1")["status"] == "open"
    assert PlanStore().get("p1").status == "ACTIVE"


def test_a_locked_plan_defers_the_reversal(tlog, monkeypatch):
    existing = _open_trade(tlog, _pending())

    def locked(plan_id, reason):
        raise LockTimeout("plan row held by the poll")

    monkeypatch.setattr(plan_links, "cancel_if_unfilled", locked)
    assert scan_run._settle_reversal(tlog, existing, 97.5) is None
    assert PlanStore().get("p1").status == "PENDING"
    assert tlog.trade_for_plan("p1")["status"] == "open"


def test_close_trade_reversed_never_books_a_placeholder(tlog):
    existing = _open_trade(tlog, _pending())
    assert tlog.close_trade_reversed(existing["id"], 97.5) is None
    assert PlanStore().get("p1").status == "CANCELLED"
    assert tlog.trade_for_plan("p1") is None
    assert account_module.get_balance_history() == []


def test_the_reversal_and_its_plan_close_commit_together(tlog, monkeypatch):
    existing = _open_trade(tlog, _filled())

    def refuse(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(plan_links, "end_linked_plan", refuse)
    with pytest.raises(RuntimeError):
        tlog.close_trade_reversed(existing["id"], 97.5)
    assert tlog.trade_for_plan("p1")["status"] == "open"
    assert PlanStore().get("p1").status == "ACTIVE"
    assert account_module.get_balance_history() == []


def test_the_scan_loop_settles_reversals_through_the_helper():
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "_settle_reversal(trade_log, existing_trade, live_price)" in source
    assert "close_trade_reversed(" not in source
