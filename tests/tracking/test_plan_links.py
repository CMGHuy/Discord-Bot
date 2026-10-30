"""v189 D4 A1/A7: tracking/plan_links ends a trade's v2 plan in the trade's
own transaction -- PENDING cancels, ACTIVE/PARTIAL close -- and checks
"never filled" under the plan row lock."""
import logging

import pytest

from swingbot.core.db.engine import transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.tracking.plan_links import DeleteResult, EndedPlan
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store


@pytest.fixture(autouse=True)
def _account(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})


def _partial():
    plan = _active()
    plan.legs_realized.append({"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"})
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    return plan


_PLANS = {"PENDING": lambda: _plan(entry_type="stop_entry"), "ACTIVE": _active,
          "PARTIAL": _partial}
_ENDS = {"PENDING": "CANCELLED", "ACTIVE": "CLOSED", "PARTIAL": "CLOSED"}


def _log(tl, plan):
    return tl.log_trade(ticker=plan.ticker, strategy="RSI", horizon_key="2w",
                        direction="bullish", confidence_level=3, confidence_label="Medium",
                        entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)


def _end(plan_id, reason="reversed", notice=False):
    with transaction() as tx:
        return plan_links.end_linked_plan(plan_id, reason, conn=tx, notice=notice)


@pytest.mark.parametrize("status", list(_PLANS))
def test_end_linked_plan_maps_each_open_status(status):
    PlanStore().add(_PLANS[status]())
    ended = _end("p1")
    assert ended == EndedPlan("p1", "AAPL", status, _ENDS[status])
    stored = PlanStore().get("p1")
    assert stored.status == _ENDS[status]
    assert stored.status_history[-1]["reason"] == "reversed"
    assert stored.status_history[-1]["at"]
    assert stored.pending_notice is None


def _terminal(status):
    if status == "CLOSED":
        plan = _active()
        record_transition(plan, PlanStatus.CLOSED, reason="loss", at="t2")
        return plan
    plan = _plan(entry_type="stop_entry")
    record_transition(plan, PlanStatus.CANCELLED, reason="expired", at="t2")
    return plan


@pytest.mark.parametrize("status", ["CLOSED", "CANCELLED"])
def test_a_terminal_plan_is_left_alone(status):
    PlanStore().add(_terminal(status))
    before = PlanStore().get("p1").status_history
    assert _end("p1") is None
    assert PlanStore().get("p1").status_history == before


def test_a_missing_plan_is_none():
    assert _end("nope") is None


def test_notice_on_a_cancel_queues_the_trade_deleted_event():
    PlanStore().add(_PLANS["PENDING"]())
    _end("p1", reason="trade_deleted", notice=True)
    notice = PlanStore().get("p1").pending_notice
    assert notice["transition"] == plan_links.TRADE_DELETED_EVENT == "cancelled_trade_deleted"
    assert notice["detail"] == {"reason": "trade_deleted", "live_price": None}
    assert notice["at"]


@pytest.mark.parametrize("status", ["ACTIVE", "PARTIAL"])
def test_notice_on_a_close_queues_a_closed_event_without_a_price(status):
    PlanStore().add(_PLANS[status]())
    _end("p1", reason="trade_deleted", notice=True)
    notice = PlanStore().get("p1").pending_notice
    assert (notice["transition"], notice["detail"]) == ("closed", {"reason": "trade_deleted"})


def test_ending_a_plan_rolls_back_with_its_transaction():
    PlanStore().add(_active())
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            plan_links.end_linked_plan("p1", "reversed", conn=tx)
            raise RuntimeError("the trade write after it failed")
    assert PlanStore().get("p1").status == "ACTIVE"


def test_cancel_if_unfilled_cancels_a_pending_plan_and_drops_its_placeholder():
    tl = TradeLog()
    PlanStore().add(_PLANS["PENDING"]())
    _log(tl, PlanStore().get("p1"))
    assert plan_links.cancel_if_unfilled("p1", "reversed") is True
    assert PlanStore().get("p1").status == "CANCELLED"
    assert tl.trade_for_plan("p1") is None


def test_cancel_if_unfilled_leaves_a_filled_plan_and_its_trade_alone():
    tl = TradeLog()
    PlanStore().add(_active())
    _log(tl, PlanStore().get("p1"))
    assert plan_links.cancel_if_unfilled("p1", "reversed") is False
    assert PlanStore().get("p1").status == "ACTIVE"
    assert tl.trade_for_plan("p1")["status"] == "open"


def test_cancel_if_unfilled_on_a_missing_plan_is_false():
    assert plan_links.cancel_if_unfilled("nope", "reversed") is False


def test_delete_result_is_truthy_only_when_something_was_removed():
    assert not DeleteResult(removed=0)
    assert DeleteResult(removed=2)
    assert DeleteResult(removed=1).ended == ()


def test_close_linked_plan_safely_raises_inside_a_transaction(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    PlanStore().add(_active())
    monkeypatch.setattr(plan_links, "end_linked_plan", boom)
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            perf._close_linked_plan_safely("p1", "reversed", conn=tx)


def test_close_linked_plan_safely_alone_never_raises(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(plan_links, "end_linked_plan", boom)
    with caplog.at_level(logging.WARNING):
        perf._close_linked_plan_safely("p1", "reversed")
    assert "could not close plan p1" in caplog.text
