"""Ending a trade's v2 plan in the trade's own transaction (v189 D4 A1, A7).

A paper trade row and its v2 plan are two halves of one position. A path that
ends the trade OUTSIDE the plan manager -- a reversal, a delete -- ends the
plan in the same database transaction, through here:

* `end_linked_plan` maps PENDING -> CANCELLED and ACTIVE/PARTIAL -> CLOSED (the
  mapping `_close_linked_plan_safely` has always used), records the reason and
  the time, and on request queues the plan's durable `pending_notice`, which
  `PlanManager.resend_notices` re-emits to the execution feed and the follow
  channel until it is acknowledged.
* `cancel_unfilled_in` / `cancel_if_unfilled` are the reversal's "has this plan
  filled?" check and cancel, under the plan row lock, so a fill the poll
  records meanwhile is seen and the trade is treated as the position it is.

Lock order is the plan row first (`PlanStore.lock_for_update`), then the trade
row, then the account. No process-local lock is taken here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore

#: open plan status -> the terminal status its plan takes when the trade ends
#: outside the plan manager. A PENDING plan never filled, so it can only cancel.
LINKED_TERMINAL = {PlanStatus.PENDING: PlanStatus.CANCELLED,
                   PlanStatus.ACTIVE: PlanStatus.CLOSED,
                   PlanStatus.PARTIAL: PlanStatus.CLOSED}

#: the cancel event a PENDING plan announces when its placeholder is deleted.
TRADE_DELETED_EVENT = "cancelled_trade_deleted"

#: the transition reason a delete writes on the plan it ends.
TRADE_DELETED_REASON = "trade_deleted"


@dataclass(frozen=True)
class EndedPlan:
    """One plan a trade-side path ended."""
    plan_id: str
    ticker: str
    status_before: str
    status_after: str


@dataclass(frozen=True)
class DeleteResult:
    """What a delete removed: the trade rows, and every plan it ended."""
    removed: int
    ended: tuple[EndedPlan, ...] = ()

    def __bool__(self) -> bool:
        return self.removed > 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notice(terminal: str, reason: str, at: str) -> dict:
    """The pending_notice a delete leaves on its plan (index clarification 2).
    A cancelled plan announces `cancelled_trade_deleted`; a closed one a
    `closed` with no exit price -- the trade was deleted, nothing was exited."""
    if terminal == PlanStatus.CANCELLED:
        return {"transition": TRADE_DELETED_EVENT,
                "detail": {"reason": reason, "live_price": None}, "at": at}
    return {"transition": "closed", "detail": {"reason": reason}, "at": at}


def end_linked_plan(plan_id: str, reason: str, *, conn,
                    notice: bool = False) -> EndedPlan | None:
    """Lock `plan_id` in the caller's transaction and end it by
    LINKED_TERMINAL. None (nothing written) when the plan is missing or
    already terminal. `notice=True` (the delete path) queues the plan's
    feed / follow notice in the same write. Raises on a failed write, so the
    caller's transaction rolls back whole."""
    store = PlanStore()
    plan = store.lock_for_update(plan_id, conn=conn)
    terminal = LINKED_TERMINAL.get(getattr(plan, "status", None))
    if terminal is None:
        return None
    before, at = plan.status, _now_iso()
    record_transition(plan, terminal, reason=reason, at=at)
    if notice:
        plan.pending_notice = _notice(terminal, reason, at)
    store.update(plan, conn=conn)
    return EndedPlan(plan.plan_id, plan.ticker, before, terminal)


def cancel_unfilled_in(plan_id: str, reason: str, *, conn) -> bool:
    """In the caller's transaction: when `plan_id` is still PENDING under its
    row lock (its order never filled), cancel it with `reason` and discard its
    placeholder trade row; True. Otherwise touch nothing; False. No P&L is
    ever booked here."""
    plan = PlanStore().lock_for_update(plan_id, conn=conn)
    if plan is None or plan.status != PlanStatus.PENDING:
        return False
    from swingbot.core.tracking.performance import TradeLog   # performance imports this module
    end_linked_plan(plan_id, reason, conn=conn)
    TradeLog().discard_plan_placeholder(plan_id, conn=conn)
    return True


def cancel_if_unfilled(plan_id: str, reason: str) -> bool:
    """`cancel_unfilled_in` in its own transaction, on the bot's lock timeout
    (the reversal runs in the scanner). LockTimeout propagates."""
    with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as tx:
        return cancel_unfilled_in(plan_id, reason, conn=tx)


def _names(ended) -> str:
    """`AAPL (`p1`, was PARTIAL), ...` for the plans a delete ended."""
    return ", ".join(f"{e.ticker} (`{e.plan_id}`, was {e.status_before})" for e in ended)


def _cancel_line(cancelled: list[EndedPlan]) -> str:
    """The confirmation line for the unfilled plans a delete cancelled."""
    tail = "Its order never filled." if len(cancelled) == 1 else "Their orders never filled."
    return f"Cancelled {len(cancelled)} unfilled plan(s): {_names(cancelled)}. {tail}"


def describe_ended(result: DeleteResult) -> str:
    """The confirmation lines for the plans a delete ended ("" when none).
    Held positions first: they lose their monitoring and alerts. An open
    PARTIAL's TP1 leg is not in the balance until the close settles, so the
    deleted trade takes it along."""
    closed = [e for e in result.ended if e.status_after == PlanStatus.CLOSED]
    cancelled = [e for e in result.ended if e.status_after == PlanStatus.CANCELLED]
    lines = []
    if closed:
        lines.append(
            f"Ended {len(closed)} open position(s): {_names(closed)}. "
            "The bot no longer monitors them and sends no more stop or take-profit alerts "
            "for them. Any TP1 dollars they banked are deleted with the trade and never "
            "reach the balance.")
    if cancelled:
        lines.append(_cancel_line(cancelled))
    return "\n".join(lines)
