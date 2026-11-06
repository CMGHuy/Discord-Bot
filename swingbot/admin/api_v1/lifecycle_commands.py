"""Atomic admin transitions and immutable notification recording (v197).

A manual close or cancel commits the plan, its linked trade, the account
settlement and the notification event in ONE transaction, or none of them.
Every command takes the settlement advisory lock first, then the plan row,
then the trade row (lock order advisory -> plan -> trade -> account). Quotes
and cached bars are read before any lock; the locked rows are re-validated.
Only a committed close reaches the derived journal/snapshot hooks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from swingbot.core.infra.swallowed import swallowed
from swingbot import config
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus, record_transition
from swingbot.core.tracking.performance import (TradeLog, _json_record, _locked_open_trade,
                                                _manual_close_quote)

log = logging.getLogger(__name__)
CLOSEABLE = (PlanStatus.ACTIVE, PlanStatus.PARTIAL)


class LifecycleNotFound(LookupError):
    """No plan or trade with that id."""


class LifecycleConflict(ValueError):
    """The plan or trade is not in a state the action applies to, or it changed
    between the unlocked read and the lock. Nothing was written."""


def _serialize_settlement(conn) -> None:
    conn.execute(sa.text("SELECT pg_advisory_xact_lock(197, 1)"))


def _now() -> tuple[str, str]:
    """(ISO instant, fresh transition id) for one transition."""
    return datetime.now(timezone.utc).isoformat(), str(uuid4())


def _require_plan(plan, statuses) -> None:
    if plan is None:
        raise LifecycleNotFound("No plan with that ID.")
    if plan.status not in statuses:
        raise LifecycleConflict(f"Cannot apply this action to a {plan.status} plan.")


def _trade_commands():
    # Lazy: trade_commands registers the HTTP routes and will import this module.
    from . import trade_commands
    return trade_commands


def _prepared_plan(plan_id: str):
    """(ticker, override stamp, settlement quote, cached bars), read with no
    lock held. The stamp's live quote first; without one, the standalone
    manual close's own fetch."""
    plan = PlanStore().get(plan_id)
    _require_plan(plan, CLOSEABLE)
    stamp = _trade_commands()._override_stamp(plan.ticker)
    quote = stamp.get("exit_price") if stamp and stamp.get("price_source") == "quote" else None
    if quote is None:
        quote = _manual_close_quote(plan.ticker)
    try:
        bars = rp.cached_daily_bars(plan.ticker)
    except Exception as exc:
        swallowed(log, "ops.lifecycle_bars", exc)
        bars = None
    return plan.ticker, stamp, quote, bars


def _runner_leg_price(plan, quote, at: str):
    """(leg, price): v189 A2's runner leg for a PARTIAL plan, appended by the
    caller. A PARTIAL plan with no leg (zero risk, nothing banked) closes its
    trade unpriced too, so the two stores agree."""
    leg = _trade_commands()._runner_leg(plan, quote, at)
    if plan.status == PlanStatus.PARTIAL and leg is None:
        return None, None
    return leg, quote


def _close_linked(plan_id: str, price, at: str, transition_id: str, conn) -> dict | None:
    linked = _locked_open_trade(plan_id, conn)
    if linked is None:
        return None
    closed = TradeLog().close_trade_manual_in_transaction(
        linked["id"], "manual (plan close, admin UI)", exit_price=price, closed_at=at,
        transition_id=transition_id, conn=conn)
    if closed is None:
        raise LifecycleConflict("The linked trade changed; retry the action.")
    return closed


def _enqueue_plan(plan, prior: str, closed: dict | None, channel, conn) -> None:
    transition = plan.status_history[-1]
    payload = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id,
                   trade_id=closed["id"] if closed else None, prior_status=prior,
                   new_status=plan.status, reason=transition["reason"],
                   occurred_at=transition["at"])
    if closed is not None:
        payload["trade"] = closed
    event = make_event(transition_id=transition["transition_id"], kind="plan_transition",
                       target_channel_id=channel, occurred_at=transition["at"], payload=payload)
    notify_queue_repo().enqueue(event, conn=conn)


def _write_plan(store: PlanStore, plan, conn) -> None:
    if not store.update(plan, conn=conn):
        raise LifecycleConflict("The plan changed; retry the action.")


def _after_commit(closed: dict | None) -> None:
    """The derived journal/snapshot effects. A failure here never relabels the
    committed action: it is logged and the command still succeeds."""
    if closed is None:
        return
    try:
        TradeLog().after_manual_close_commit(closed)
    except Exception as exc:
        swallowed(log, "ops.lifecycle_post_commit", exc,
                  "lifecycle post-commit derived hooks failed trade=%s", closed["id"],
                  level=logging.ERROR, exc_info=True)


def _locked_plan(store: PlanStore, plan_id: str, statuses, conn):
    plan = store.get(plan_id, conn=conn, for_update=True)
    _require_plan(plan, statuses)
    return plan


def close_plan_atomic(plan_id: str, reason: str = "manual") -> None:
    """Close one ACTIVE/PARTIAL plan, its open linked trade (settled at the
    prepared quote), and queue its `plan_transition` event, atomically."""
    ticker, stamp, quote, bars = _prepared_plan(plan_id)
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    store = PlanStore()
    with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
        _serialize_settlement(conn)
        plan = _locked_plan(store, plan_id, CLOSEABLE, conn)
        if plan.ticker != ticker:
            raise LifecycleConflict("The plan changed; retry the action.")
        prior = plan.status
        at, transition_id = _now()
        leg, price = _runner_leg_price(plan, quote, at)
        closed = _close_linked(plan_id, price, at, transition_id, conn)
        if leg is not None:
            plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at,
                          extra={"transition_id": transition_id, "prior_status": prior,
                                 "override": stamp})
        if prior == PlanStatus.PARTIAL:
            rp.stamp_runner_path(plan, lambda _ticker: bars, source="live")
        _write_plan(store, plan, conn)
        _enqueue_plan(plan, prior, closed, channel, conn)
    _after_commit(closed)


def cancel_plan_atomic(plan_id: str) -> None:
    """Cancel one PENDING plan and queue its unfilled `plan_transition` event,
    atomically. No trade, no settlement."""
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    store = PlanStore()
    with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
        _serialize_settlement(conn)
        plan = _locked_plan(store, plan_id, (PlanStatus.PENDING,), conn)
        prior = plan.status
        at, transition_id = _now()
        record_transition(plan, PlanStatus.CANCELLED, reason="manual", at=at,
                          extra={"transition_id": transition_id, "prior_status": prior})
        _write_plan(store, plan, conn)
        _enqueue_plan(plan, prior, None, channel, conn)


def _require_open_trade(trade: dict | None) -> None:
    if trade is None:
        raise LifecycleNotFound("No trade with that ID.")
    if trade.get("status") != "open":
        raise LifecycleConflict("Trade is already closed.")


def _locked_trade(trade_id: str, conn) -> dict | None:
    row = trades_repo().get_for_update(trade_id, conn=conn)
    return None if row is None else _json_record(row)


def _enqueue_trade(closed: dict, channel, conn) -> None:
    payload = dict(ticker=closed["ticker"], direction=closed["direction"],
                   plan_id=closed.get("plan_id"), trade_id=closed["id"], prior_status="open",
                   new_status=closed["status"], reason=closed["close_reason"],
                   occurred_at=closed["closed_at"], trade=closed)
    event = make_event(transition_id=closed["manual_transition_id"], kind="trade_closed",
                       target_channel_id=channel, occurred_at=closed["closed_at"],
                       payload=payload)
    notify_queue_repo().enqueue(event, conn=conn)


def _close_unlinked(trade_id: str, ticker: str, quote, conn) -> dict:
    current = _locked_trade(trade_id, conn)
    _require_open_trade(current)
    if current.get("plan_id") or current["ticker"] != ticker:
        raise LifecycleConflict("The trade changed; retry the action.")
    at, transition_id = _now()
    closed = TradeLog().close_trade_manual_in_transaction(
        trade_id, "manual (admin UI)", exit_price=quote, closed_at=at,
        transition_id=transition_id, conn=conn)
    if closed is None:
        raise LifecycleConflict("The trade changed; retry the action.")
    return closed


def close_legacy_atomic(trade_id: str) -> None:
    """Close one open trade by its trade id and queue its `trade_closed` event,
    atomically. A plan-linked trade goes through `close_plan_atomic` before
    any trade lock, so a trade never closes behind an active plan."""
    before = TradeLog().get_trade_by_id(trade_id)
    _require_open_trade(before)
    if before.get("plan_id"):
        close_plan_atomic(before["plan_id"])
        return
    quote = _manual_close_quote(before["ticker"])
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
        _serialize_settlement(conn)
        closed = _close_unlinked(trade_id, before["ticker"], quote, conn)
        _enqueue_trade(closed, channel, conn)
    _after_commit(closed)
