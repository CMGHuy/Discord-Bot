"""Trade commands — close, cancel, delete, and the two bulk clears.

Spec v11 Decision 3: these are verb sub-paths, always POST (DELETE for
the one real deletion), never a PATCH on a status field. "Close this position" and
"cancel this plan" carry their own preconditions and failure modes, and
modelling them as field assignments would hide both.

**The domain rules are the Jinja handlers', not new ones.** They are
enforced here by the same preconditions `pages.plan_cancel`,
`pages.plan_close` and `app.close_trade` already apply:

    cancel   PENDING plan only
    close    ACTIVE / PARTIAL plan, or an `open` legacy trade
    delete   legacy trade only -- see delete_trade() for why

Every state change also appends to data/manual_close_notify.json. The bot
is a separate process; that file is the only way it learns a human closed
something, and the trade-history channel goes quiet without it.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot import config
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore

from . import api_v1, error
from .auth import require_auth
from .trades import (
    _attach_current_prices,
    _looks_like_a_plan_id,
    _noted_ids,
    _row_from_plan,
    _row_from_trade,
)

log = logging.getLogger("swing-bot.admin.api_v1")

_CLOSEABLE_PLAN = (PlanStatus.ACTIVE, PlanStatus.PARTIAL)
_OPEN_LEGACY = "open"


def _queue_path() -> str:
    """Resolved per call, not at import: config.DATA_DIR is monkeypatched
    per test, and a module-level constant would point at the real data/."""
    return os.path.join(config.DATA_DIR, "manual_close_notify.json")


def _queue_notify(record: dict) -> None:
    """Append to the bot's manual-close queue. Never raises.

    Bookkeeping must not fail the command: the position is already closed by
    the time this runs, and turning a successful close into a 500 because a
    notification could not be queued would be strictly worse.
    """
    try:
        path = _queue_path()
        existing = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (OSError, json.JSONDecodeError):
                existing = []
        existing.append(record)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f)
    except OSError as exc:
        log.warning("could not queue manual-close notification: %s", exc)


def _linked_trade(log_: TradeLog, plan_id: str) -> dict | None:
    return next(
        (t for t in log_.get_trades(status=None, limit=None) or []
         if t.get("plan_id") == plan_id),
        None,
    )


def _plan_row(plan_id: str):
    """Re-read and render a plan-backed position after mutating it."""
    plan = PlanStore()._plans.get(plan_id)
    trade = _linked_trade(TradeLog(), plan_id)
    row = _row_from_plan(plan, trade, _noted_ids())
    _attach_current_prices([row])
    return jsonify(row)


def _trade_row(trade_id: str):
    row = _row_from_trade(TradeLog().get_trade_by_id(trade_id) or {}, _noted_ids())
    _attach_current_prices([row])
    return jsonify(row)


# --- close ---------------------------------------------------------------

@api_v1.route("/trades/<trade_id>/close", methods=["POST"])
@require_auth
def close_trade(trade_id: str):
    if _looks_like_a_plan_id(trade_id):
        store = PlanStore()
        plan = store.get(trade_id)
        if plan is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        if plan.status not in _CLOSEABLE_PLAN:
            return error(
                "invalid",
                f"Only ACTIVE or PARTIAL plans can be closed; this one is {plan.status}.",
                422,
            )
        tl = TradeLog()
        linked = _linked_trade(tl, trade_id)
        if linked and linked.get("status") == _OPEN_LEGACY:
            # Through TradeLog's own locked mutator: the admin and the bot are
            # separate processes over one trades.json, so an unlocked
            # read-modify-write here could race the scan loop.
            tl.close_trade_manual(linked["id"], reason="manual (plan close, admin UI)")
        # `at` is passed explicitly. record_transition defaults it to None,
        # and the lifecycle strip's "today" counts read status_history[-1]["at"]
        # -- an implicit None makes this close invisible to today's count.
        record_transition(plan, PlanStatus.CLOSED, reason="manual",
                          at=datetime.now(timezone.utc).isoformat())
        store.update(plan)
        _queue_notify({"kind": "plan_transition", "plan_id": plan.plan_id,
                       "ticker": plan.ticker, "status": plan.status})
        return _plan_row(trade_id)

    tl = TradeLog()
    trade = tl.get_trade_by_id(trade_id)
    if trade is None:
        return error("not_found", f"No trade with id {trade_id!r}", 404)
    if trade.get("status") != _OPEN_LEGACY:
        return error("invalid", "Trade is already closed.", 422)
    tl.close_trade_manual(trade_id, reason="manual (admin UI)")
    _queue_notify(tl.get_trade_by_id(trade_id) or {})
    return _trade_row(trade_id)


# --- cancel --------------------------------------------------------------

@api_v1.route("/trades/<trade_id>/cancel", methods=["POST"])
@require_auth
def cancel_trade(trade_id: str):
    if not _looks_like_a_plan_id(trade_id):
        # Not merely disallowed -- legacy trades have no PENDING state, so
        # there is nothing a cancel could mean for one.
        if TradeLog().get_trade_by_id(trade_id) is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        return error("invalid", "Only plans can be cancelled.", 422)

    store = PlanStore()
    plan = store.get(trade_id)
    if plan is None:
        return error("not_found", f"No trade with id {trade_id!r}", 404)
    if plan.status != PlanStatus.PENDING:
        return error(
            "invalid",
            f"Only PENDING plans can be cancelled; this one is {plan.status}.",
            422,
        )
    record_transition(plan, PlanStatus.CANCELLED, reason="manual",
                      at=datetime.now(timezone.utc).isoformat())
    store.update(plan)
    _queue_notify({"kind": "plan_transition", "plan_id": plan.plan_id,
                   "ticker": plan.ticker, "status": plan.status})
    return _plan_row(trade_id)


# --- delete --------------------------------------------------------------

@api_v1.route("/trades/<trade_id>", methods=["DELETE"])
@require_auth
def delete_trade(trade_id: str):
    """Legacy trade records only.

    Plans are deliberately not deletable. The Jinja UI has no plan-delete
    route either, and a plan is a lifecycle record whose CANCELLED / CLOSED
    states exist precisely to record how it ended -- erasing one destroys
    that history. Deleting only the linked trade row would be worse: the
    plan would survive as a position with no execution behind it.

    Supporting it would need a PlanStore.delete() in core, which is outside
    this migration's remit. Left as an open question for sub-project 5.
    """
    if _looks_like_a_plan_id(trade_id):
        if PlanStore()._plans.get(trade_id) is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        return error(
            "invalid",
            "Plans cannot be deleted; cancel a PENDING plan or close an active one.",
            422,
        )
    if not TradeLog().delete_trade(trade_id):
        return error("not_found", f"No trade with id {trade_id!r}", 404)
    return jsonify({"deleted": trade_id})


# --- bulk clears ---------------------------------------------------------

@api_v1.route("/trades/clear-open", methods=["POST"])
@require_auth
def clear_open():
    return jsonify({"removed": TradeLog().clear_open()})


@api_v1.route("/trades/clear-history", methods=["POST"])
@require_auth
def clear_history():
    return jsonify({"removed": TradeLog().clear_history()})


# --- journal --------------------------------------------------------------

@api_v1.route("/trades/<trade_id>/journal", methods=["GET"])
@require_auth
def get_journal(trade_id: str):
    """SR55 — one position's journal entry: MFE, MAE, exit efficiency, the
    entry tags and the auto-generated lesson.

    **200 with `journaled: false`, not 404.** `PUT /trades/:id/note` returns
    404 for an unjournaled trade and that is right there -- the write genuinely
    did nothing. A GET asking "is there an entry for this trade" has a perfectly
    good answer either way, and forcing the client to catch an error to hear
    "not yet" is how the normal state of every open position ends up rendered
    as a failure. `trade-detail.store` already models `unjournaled` as a state;
    this lets it read that state directly instead of discovering it by trying.

    Plan-backed positions resolve to their linked trade first, for the same
    reason `set_note` does: entries are keyed by TRADE id, so looking one up
    by plan id silently misses.

    An unreadable journal degrades to "not journaled" rather than 500ing --
    the excursion figures are context for a note, and losing them must not
    take the detail view down with them.
    """
    from swingbot.core.analytics.journal import JournalStore

    target = trade_id
    if _looks_like_a_plan_id(trade_id):
        linked = _linked_trade(TradeLog(), trade_id)
        if linked is not None:
            target = linked["id"]

    try:
        entry = JournalStore().get(target)
    except Exception:
        entry = None

    return jsonify({"journaled": entry is not None, "entry": entry})


# --- note ----------------------------------------------------------------

@api_v1.route("/trades/<trade_id>/note", methods=["PUT"])
@require_auth
def set_note(trade_id: str):
    """Replace the free-text note on a position.

    PUT, not POST: this is idempotent replacement of one field, not
    creation of a resource.

    404 when the trade has no journal entry. Journal entries are written at
    close, so an open position usually has none, and `JournalStore.set_note`
    returns False for it. Creating the entry here was rejected -- journal
    records feed the analytics snapshot and `_resolve_outcome` expects a
    closed trade, so a half-populated entry for a running position could
    corrupt the numbers. Sub-project 5's Notes tab must render "not
    journaled yet" as a state rather than surfacing it as an error.
    """
    from swingbot.core.analytics.journal import JournalStore

    payload = request.get_json(silent=True) or {}
    if "note" not in payload:
        # An ABSENT note is malformed, not an instruction to clear: treating
        # it as a clear would let a client bug silently destroy text. An
        # explicit empty string does clear, and that is tested.
        return error("invalid", "Body must contain a 'note' field.", 400)

    note = payload["note"]
    if not isinstance(note, str):
        return error("invalid", "'note' must be a string.", 400)

    plan_backed = _looks_like_a_plan_id(trade_id)
    target = trade_id
    if plan_backed:
        # Notes live against the TRADE id, so a plan-backed position notes
        # through its linked trade -- otherwise the note would attach to an
        # id the journal has never seen.
        linked = _linked_trade(TradeLog(), trade_id)
        if linked is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        target = linked["id"]
    elif TradeLog().get_trade_by_id(trade_id) is None:
        return error("not_found", f"No trade with id {trade_id!r}", 404)

    if not JournalStore().set_note(target, note):
        return error(
            "not_found",
            f"Trade {trade_id!r} has no journal entry yet; notes attach on close.",
            404,
        )
    return jsonify({"id": trade_id, "note": note})
