"""v189 D4 A7: deleting a trade ends its linked v2 plan in the same
transaction -- a PENDING plan is cancelled (cancelled_trade_deleted), an
ACTIVE/PARTIAL one is closed with no P&L -- and the plan's pending_notice
carries the follow / feed notice. A plan is never left stepping with no trade."""
import pytest

from swingbot.core.db.repositories import trades as trades_repo_module
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.tracking.plan_links import DeleteResult, EndedPlan, describe_ended
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store

_TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def tlog(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _partial(**kw):
    plan = _active(**kw)
    plan.legs_realized.append(dict(_TP1))
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    return plan


_BUILD = {"PENDING": lambda **kw: _plan(entry_type="stop_entry", **kw),
          "ACTIVE": _active, "PARTIAL": _partial}
_ENDS = {"PENDING": "CANCELLED", "ACTIVE": "CLOSED", "PARTIAL": "CLOSED"}


def _log(tl, ticker, plan_id=None) -> str:
    return tl.log_trade(ticker=ticker, strategy="RSI", horizon_key="2w", direction="bullish",
                        confidence_level=3, confidence_label="Medium", entry=100.0,
                        stop_loss=95.0, take_profit=110.0, plan_id=plan_id)


def _open(tl, status, plan_id="p1", ticker="AAPL") -> str:
    """A plan in `status` and its open trade row; returns the trade id."""
    PlanStore().add(_BUILD[status](plan_id=plan_id, ticker=ticker))
    tid = _log(tl, ticker, plan_id)
    if status == "PARTIAL":
        tl.append_leg_by_plan(plan_id, dict(_TP1))
    return tid


def _resent():
    events = PlanManager(PlanStore(), lambda ticker: None).resend_notices()
    return [(e.plan_id, e.transition, e.detail) for e in events]


@pytest.mark.parametrize("status", list(_BUILD))
def test_delete_trade_ends_its_plan_by_status(tlog, status):
    tid = _open(tlog, status)
    result = tlog.delete_trade(tid)
    assert result == DeleteResult(1, (EndedPlan("p1", "AAPL", status, _ENDS[status]),))
    plan = PlanStore().get("p1")
    assert plan.status == _ENDS[status]
    assert plan.status_history[-1]["reason"] == "trade_deleted" == plan_links.TRADE_DELETED_REASON
    assert tlog.get_trade_by_id(tid) is None
    assert account_module.get_balance_history() == []


def test_a_pending_delete_queues_the_cancel_notice_and_resend_emits_it(tlog):
    tlog.delete_trade(_open(tlog, "PENDING"))
    assert _resent() == [
        ("p1", "cancelled_trade_deleted", {"reason": "trade_deleted", "live_price": None})]


@pytest.mark.parametrize("status", ["ACTIVE", "PARTIAL"])
def test_a_position_delete_queues_a_closed_notice_and_resend_emits_it(tlog, status):
    tlog.delete_trade(_open(tlog, status))
    assert _resent() == [("p1", "closed", {"reason": "trade_deleted"})]


def test_deleting_a_partial_leaves_the_balance_where_it_was(tlog):
    """The copy says banked TP1 dollars never reached the balance: an open
    PARTIAL has no realized_pnl_amount until its close settles."""
    tid = _open(tlog, "PARTIAL")
    before = account_module.load_account_config()["balance"]
    tlog.delete_trade(tid)
    assert account_module.load_account_config()["balance"] == before


def test_deleting_a_closed_trade_leaves_its_terminal_plan_alone(tlog):
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="loss", at="t2")
    PlanStore().add(plan)
    tid = _log(tlog, "AAPL", "p1")
    history = PlanStore().get("p1").status_history
    assert tlog.delete_trade(tid) == DeleteResult(1)
    assert PlanStore().get("p1").status_history == history
    assert PlanStore().get("p1").pending_notice is None


def test_deleting_a_legacy_trade_ends_nothing(tlog):
    assert tlog.delete_trade(_log(tlog, "MSFT")) == DeleteResult(1)


def test_deleting_an_unknown_trade_is_falsy(tlog):
    result = tlog.delete_trade("nope")
    assert not result and result == DeleteResult(0)


def test_a_failed_row_delete_rolls_the_plan_back(tlog, monkeypatch):
    tid = _open(tlog, "ACTIVE")

    def boom(self, key, *, conn=None):
        raise RuntimeError("trade row delete failed")

    monkeypatch.setattr(trades_repo_module.TradeRepository, "delete", boom)
    with pytest.raises(RuntimeError):
        tlog.delete_trade(tid)
    assert PlanStore().get("p1").status == "ACTIVE"
    assert PlanStore().get("p1").pending_notice is None


def test_clear_open_ends_every_plan_in_plan_id_order(tlog, monkeypatch):
    _open(tlog, "PARTIAL", plan_id="p3", ticker="NVDA")
    _open(tlog, "PENDING", plan_id="p1", ticker="AAPL")
    _open(tlog, "ACTIVE", plan_id="p2", ticker="MSFT")
    _log(tlog, "AMD")
    locked = []
    real_end = plan_links.end_linked_plan

    def spy(plan_id, reason, *, conn, notice=False):
        locked.append(plan_id)
        return real_end(plan_id, reason, conn=conn, notice=notice)

    monkeypatch.setattr(plan_links, "end_linked_plan", spy)
    result = tlog.clear_open()
    assert locked == ["p1", "p2", "p3"]
    assert result.removed == 4
    assert [(e.plan_id, e.status_after) for e in result.ended] == [
        ("p1", "CANCELLED"), ("p2", "CLOSED"), ("p3", "CLOSED")]
    assert [PlanStore().get(p).status for p in ("p1", "p2", "p3")] == [
        "CANCELLED", "CLOSED", "CLOSED"]
    assert tlog.get_trades(status="open", limit=None) == []


def test_clear_open_keeps_closed_history(tlog):
    _open(tlog, "ACTIVE")
    closed = _log(tlog, "MSFT")
    assert tlog.close_trade_manual(closed, exit_price=108.0)
    result = tlog.clear_open()
    assert result.removed == 1
    assert tlog.get_trade_by_id(closed) is not None


def test_clear_open_on_an_empty_book(tlog):
    result = tlog.clear_open()
    assert result == DeleteResult(0) and describe_ended(result) == ""


def test_describe_ended_names_positions_then_cancels():
    result = DeleteResult(3, (
        EndedPlan("p1", "AAPL", "PENDING", "CANCELLED"),
        EndedPlan("p2", "MSFT", "ACTIVE", "CLOSED"),
        EndedPlan("p3", "NVDA", "PARTIAL", "CLOSED"),
    ))
    assert describe_ended(result) == (
        "Ended 2 open position(s): MSFT (`p2`, was ACTIVE), NVDA (`p3`, was PARTIAL). "
        "The bot no longer monitors them and sends no more stop or take-profit alerts "
        "for them. Any TP1 dollars they banked are deleted with the trade and never "
        "reach the balance.\n"
        "Cancelled 1 unfilled plan(s): AAPL (`p1`, was PENDING). Its order never filled.")


def test_describe_ended_with_only_cancels_or_nothing():
    two = DeleteResult(2, (EndedPlan("p1", "AAPL", "PENDING", "CANCELLED"),
                           EndedPlan("p2", "MSFT", "PENDING", "CANCELLED")))
    assert describe_ended(two) == (
        "Cancelled 2 unfilled plan(s): AAPL (`p1`, was PENDING), MSFT (`p2`, was PENDING). "
        "Their orders never filled.")
    assert describe_ended(DeleteResult(2)) == ""
