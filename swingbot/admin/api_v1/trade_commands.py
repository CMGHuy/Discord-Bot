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

Every state change also enqueues a notify_queue row. The bot is a separate
process; that queue is the only way it learns a human closed something, and
the trade-history channel goes quiet without it.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request

from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import LockTimeout
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.tracking.performance import _usable_price
from swingbot.core.tracking import account_reset
from swingbot.core.tracking.plan_links import describe_ended
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore

from . import api_v1, error
from . import lifecycle_commands as lifecycle
from .auth import require_auth
from .trades import (
    _attach_current_prices,
    _looks_like_a_plan_id,
    _noted_ids,
    _row_from_plan,
    _row_from_trade,
)

log = logging.getLogger(__name__)

_CLOSEABLE_PLAN = (PlanStatus.ACTIVE, PlanStatus.PARTIAL)


def _linked_trade(log_: TradeLog, plan_id: str) -> dict | None:
    return next(
        (t for t in log_.get_trades(status=None, limit=None) or []
         if t.get("plan_id") == plan_id),
        None,
    )


def _plan_row(plan_id: str):
    """Re-read and render a plan-backed position after mutating it."""
    plan = PlanStore().get_record(plan_id)
    trade = _linked_trade(TradeLog(), plan_id)
    row = _row_from_plan(plan, trade, _noted_ids())
    _attach_current_prices([row])
    return jsonify(row)


def _trade_row(trade_id: str):
    row = _row_from_trade(TradeLog().get_trade_by_id(trade_id) or {}, _noted_ids())
    _attach_current_prices([row])
    return jsonify(row)


# --- close ---------------------------------------------------------------

def _live_quote(ticker: str) -> tuple[float | None, str | None]:
    """(price, quote_ts) for the override stamp, fetched once. A fetch that
    raises is "no quote" (one warning), so the stamp falls back to the bar
    close rather than being lost. Looked up on the module at call time."""
    try:
        from swingbot.core.marketdata import data as md
        quote = md.get_current_price_detail(ticker, allow_stale=False)
    except Exception as exc:
        swallowed(log, "ops.override_stamp.quote", exc,
                  "override stamp: quote fetch failed for %s: %s", ticker, exc, exc_info=True)
        return None, None
    quote_ts = datetime.now(timezone.utc).isoformat()
    if quote is None or not quote.price:
        return None, None
    return float(quote.price), quote_ts


def _last_bar(bars) -> tuple[str | None, float | None]:
    """(ISO date, close) of the daily cache's last bar; Nones when empty.
    A NaN close is no price."""
    if bars is None or len(bars) == 0:
        return None, None
    close = float(bars["Close"].iloc[-1])
    return bars.index[-1].date().isoformat(), (close if close == close else None)


def _build_override_stamp(ticker: str) -> dict:
    """The four-field `override` stamp (spec v173 §1). May raise; callers
    go through `_override_stamp`."""
    price, quote_ts = _live_quote(ticker)
    bars_asof, last_close = _last_bar(rp.cached_daily_bars(ticker))
    if price is not None:
        source = "quote"
    elif last_close is not None:
        price, source = last_close, "bar_close"
    else:
        source = "none"
    return {"exit_price": price, "price_source": source,
            "quote_ts": quote_ts if source == "quote" else None, "bars_asof": bars_asof}


def _override_stamp(ticker: str) -> dict | None:
    """What a manual close records about its exit, read only by the v173
    override-fidelity report. Never raises: a failure logs and returns None
    (written as `override: null`), and the close goes ahead."""
    try:
        return _build_override_stamp(ticker)
    except Exception as exc:
        swallowed(log, "ops.override_stamp", exc,
                  "override stamp failed for %s: %s", ticker, exc, exc_info=True)
        return None


def _runner_leg(plan, price, at: str) -> dict | None:
    """v189 A2: a PARTIAL plan's still-open remainder realized at `price`, in
    the shape `_close_runner` writes. None for an ACTIVE plan, a PARTIAL with
    no banked leg on record, a zero-risk plan or no usable price (the trade
    side then closes unpriced as well, so the two stores still agree)."""
    if plan.status != PlanStatus.PARTIAL or not plan.legs_realized or not _usable_price(price):
        return None
    remaining = round(1.0 - sum(leg.get("fraction", 0) for leg in plan.legs_realized), 6)
    risk = abs(plan.entry_price - plan.stop_loss) if plan.entry_price is not None else 0.0
    if remaining <= 0 or not risk:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    return {"fraction": remaining, "exit_price": price,
            "r": (price - plan.entry_price) * sign / risk, "reason": "manual", "closed_at": at}


def _close_plan(store: PlanStore, plan, reason: str = "manual") -> None:
    """Keep the bulk-close seam while the service owns fresh reads and commit."""
    lifecycle.close_plan_atomic(plan.plan_id, reason)


def _perform_lifecycle(action, identity, projection):
    try:
        action(identity)
    except lifecycle.LifecycleNotFound as exc:
        return error("not_found", str(exc), 404)
    except lifecycle.LifecycleConflict as exc:
        return error("invalid", str(exc), 422)
    except LockTimeout:
        return error("conflict",
                     "This position changed or is being updated by the bot; "
                     "reload and try again.", 409)
    except Exception as exc:
        log.error("admin lifecycle action could not commit type=%s", type(exc).__name__)
        return error("unavailable", "The action could not be saved. Try again.", 503)
    # Projection failure after commit must not be described as an action rollback.
    return projection(identity)


def _reject_legacy_cancel(trade_id):
    if TradeLog().get_trade_by_id(trade_id) is None:
        raise lifecycle.LifecycleNotFound("No trade with that ID.")
    raise lifecycle.LifecycleConflict("Only plans can be cancelled.")


@api_v1.route("/trades/<trade_id>/close", methods=["POST"])
@require_auth
def close_trade(trade_id: str):
    if _looks_like_a_plan_id(trade_id):
        return _perform_lifecycle(lifecycle.close_plan_atomic, trade_id, _plan_row)
    return _perform_lifecycle(lifecycle.close_legacy_atomic, trade_id, _trade_row)


# --- cancel --------------------------------------------------------------

@api_v1.route("/trades/<trade_id>/cancel", methods=["POST"])
@require_auth
def cancel_trade(trade_id: str):
    action = lifecycle.cancel_plan_atomic if _looks_like_a_plan_id(trade_id) else _reject_legacy_cancel
    return _perform_lifecycle(action, trade_id, _plan_row)


# --- delete --------------------------------------------------------------

_DELETE_LOCKED = ("A plan behind this delete is being updated by the bot; "
                  "nothing was deleted. Try again in a moment.")


def _ended_body(result) -> dict:
    """The A7 part of a delete response: every plan ended, and the copy."""
    return {"ended": [asdict(e) for e in result.ended], "notice": describe_ended(result)}


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

    v189 A7: a trade-id delete of a plan-linked trade ends that plan in the
    same transaction (PENDING cancelled, ACTIVE/PARTIAL closed, no P&L); the
    response lists it under `ended`, with the confirmation in `notice`. A
    lock timeout is a 409 and nothing is deleted.
    """
    if _looks_like_a_plan_id(trade_id):
        if PlanStore().get_record(trade_id) is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        return error(
            "invalid",
            "Plans cannot be deleted; cancel a PENDING plan or close an active one.",
            422,
        )
    try:
        result = TradeLog().delete_trade(trade_id)
    except LockTimeout:
        return error("conflict", _DELETE_LOCKED, 409)
    if not result:
        return error("not_found", f"No trade with id {trade_id!r}", 404)
    return jsonify({"deleted": trade_id, **_ended_body(result)})


# --- bulk clears ---------------------------------------------------------

@api_v1.route("/trades/clear-open", methods=["POST"])
@require_auth
def clear_open():
    try:
        result = TradeLog().clear_open()
    except LockTimeout:
        return error("conflict", _DELETE_LOCKED, 409)
    return jsonify({"removed": result.removed, **_ended_body(result)})


_TRUE_WORDS = frozenset({"1", "true", "yes"})


def _force_requested() -> bool:
    """`?force=true` (or 1/yes), or a JSON object body `{"force": true}`.
    Anything else, including a JSON "yes", is no force."""
    if request.args.get("force", "").strip().lower() in _TRUE_WORDS:
        return True
    body = request.get_json(silent=True)
    return isinstance(body, dict) and body.get("force") is True


def _reset_payload(result: account_reset.ResetResult) -> dict:
    return {
        "removed": result.removed_trades,
        "removed_plans": result.removed_plans,
        "archive": Path(result.archive_path).name,
        "throttle": {"multiplier": result.throttle_multiplier, "paused": result.throttle_paused},
        "kill_switch": result.kill_on,
        "notice": account_reset.describe_reset(result),
    }


@api_v1.route("/trades/clear-history", methods=["POST"])
@require_auth
def clear_history():
    """v189 A6: the archived full reset. 409 while the kill switch is tripped
    unless forced; 500 when the archive cannot be written (nothing deleted)."""
    try:
        result = account_reset.reset_closed_history(force=_force_requested())
    except account_reset.ResetRefused as exc:
        return error("kill_switch_tripped", str(exc), 409)
    except account_reset.ArchiveFailed as exc:
        return error("archive_failed", str(exc), 500)
    except LockTimeout:
        return error("conflict", account_reset.LOCKED_TEXT, 409)
    return jsonify(_reset_payload(result))


_CLOSE_SCOPES = {
    "": _CLOSEABLE_PLAN,
    "open": (PlanStatus.ACTIVE,),
    "partial": (PlanStatus.PARTIAL,),
    "open_partial": _CLOSEABLE_PLAN,
}


@api_v1.route("/trades/close-open", methods=["POST"])
@require_auth
def close_open():
    """Close every ACTIVE/PARTIAL position at its current price.

    **This is not `/trades/clear-open`.** That one DELETES open trade records
    and realises nothing; this one banks them. The two live in the same file
    and read one word apart, so check which you are calling.

    PENDING plans are untouched: one that never filled has nothing to close,
    and cancelling it is a different act with a different meaning.

    `?scope=open|partial|open_partial`, default `open_partial` (the historical,
    only behaviour before this parameter existed): narrows which of the two
    closeable statuses this call actually closes, for the dashboard's
    close-all control offering the three separately. An unrecognised scope is
    a 400, the same "never silently narrow to the default" rule `_scope` in
    `dashboard.py` applies to `?mode=`.

    Per position it runs `_close_plan` -- the same path the single-position
    close uses, including the manual-close notify record the bot reads --
    with reason "manual_bulk" (v173), so a bulk clear is never counted as
    an individual override.

    One failure does not abort the rest: a half-closed book with no report of
    which half is worse than a partial success that says so.
    """
    scope = (request.args.get("scope") or "").strip().lower()
    if scope not in _CLOSE_SCOPES:
        return error(
            "invalid",
            f"scope must be one of {', '.join(s for s in _CLOSE_SCOPES if s)}",
            400,
        )
    closeable = _CLOSE_SCOPES[scope]

    store = PlanStore()
    closed, failed, tickers = 0, 0, []
    # store.all(), not store._plans.values() -- the latter holds raw dicts
    # (no .status/.ticker/.plan_id), and it is already a fresh list rather
    # than a live view, so _close_plan's store.update() inside the loop
    # cannot turn this into a mutate-while-iterating RuntimeError.
    for plan in store.all():
        if plan.status not in closeable:
            continue
        try:
            _close_plan(store, plan, "manual_bulk")
            closed += 1
            tickers.append(plan.ticker)
        except Exception as exc:
            log.error("bulk close failed plan=%s type=%s", plan.plan_id, type(exc).__name__)
            failed += 1
    return jsonify({"closed": closed, "failed": failed, "tickers": tickers})


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
