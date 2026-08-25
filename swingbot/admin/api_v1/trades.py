"""GET /api/v1/trades — the unified trades collection.

Spec v11 Decision 2 and its NG1 amendment. Read the amendment before
changing anything here.

The Jinja UI split one concept across two stores and four pages: a *plan*
(data/plans.json, Plan Engine v2) and a *trade* (data/trades.json). Spec 3
abolished that split in the UI -- one Trades list, with status as a filter.
So this endpoint presents one collection.

**The two stores overlap.** When a plan fills, PlanManager calls
TradeLog.log_trade(..., plan_id=plan.plan_id) and the plan STAYS in
plans.json, advancing to ACTIVE. From that moment one real position exists
as two records. Concatenating the row sets would list it twice.

The union is a join, and it is built so a duplicate cannot occur rather
than being filtered out afterwards:

    all plans          -- authoritative for PENDING/ACTIVE/PARTIAL/
                          CLOSED/CANCELLED, which is exactly spec 3's
                          vocabulary; enriched by the matching trades.json
                          row when there is one
    + trades whose plan_id names no plan we loaded -- legacy v1 records
      (plan_id is None) and orphans whose plan has been deleted

A concatenate-then-dedup would be one forgotten branch away from letting
duplicates back in; "plans, plus trades that no plan claimed" cannot
produce one at all.

Derived values (P&L %, R multiple, holding period) are imported from
`dashboard`, not recomputed. The admin already has one definition of each
and a second would drift from it silently.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify, request

from swingbot.admin import dashboard as dash
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.planning.plan_store import PlanStore

from . import api_v1, collection, error, parse_collection_params
from .auth import require_auth

# Legacy v1 trades carry their own status vocabulary. They have no PENDING,
# PARTIAL or CANCELLED equivalent and none is synthesised for them.
_LEGACY_STATUS = {
    "open": "ACTIVE",
    "win": "CLOSED",
    "loss": "CLOSED",
    "closed": "CLOSED",
}

# Statuses where a live price is meaningless -- the position is over.
_TERMINAL = {"CLOSED", "CANCELLED"}

FILTERS = frozenset({"status", "outcome", "ticker", "strategy", "horizon",
                     "direction", "origin", "has_note",
                     # SR52. `strategy` and `horizon` were already
                     # accepted and had no control; these two were accepted by
                     # neither side. `tag` is deliberately NOT here -- journal
                     # tags are not on a trade row at all, so filtering by one
                     # needs the journal endpoint SR55 adds.
                     # v32 Task 11: `tier` (A/B/C) retired -- `confidence`
                     # already covered the same "filter by quality
                     # classification" role.
                     "badge", "confidence",
                     # The Dashboard lifecycle strip's "today" scope -- see
                     # `_row_from_plan`'s `today` field.
                     "today"})

# Query-parameter name -> row key, where the two differ. `confidence` reads
# better in a URL than `confidence_level` and is what the chip row calls it;
# the row field keeps its own name.
_FILTER_KEYS = {"confidence": "confidence_level"}

# Filters compared case-insensitively. These hold vocabulary the UI displays
# (VALIDATED, bullish, A) rather than free text, and `?badge=validated` failing
# to match VALIDATED is the exact shape of the NG54 bug.
_CASELESS_FILTERS = frozenset({"badge", "direction", "origin"})

# NG54. `status` normalises win and loss to CLOSED, so the two cannot be told
# apart by it -- but the Jinja UI had an `outcome` filter over exactly that
# distinction (dashboard.py's history table), and the SPA's Win/Loss chips
# were sending `status=win` into a field that never holds "win". This is the
# field they mean: the RAW status of the underlying trade, untranslated.
#
# `None` for a plan with no trade behind it. A PENDING or CANCELLED plan has
# no outcome, which is different from having an outcome of "not yet".
_OUTCOMES = frozenset({"win", "loss", "open", "closed"})

# The two plan statuses that both mean "position is live". `status=open` is
# accepted as an alias for either, because "open" is what a user means and
# splitting it across two chips would be exposing a storage detail.
_OPEN_STATUSES = frozenset({"ACTIVE", "PARTIAL"})

# Compared as booleans, not as strings. `has_note` and `today` are real bools
# on the row, and the generic comparison below stringifies it -- so
# `?has_note=1` would test "1" == "True" and quietly match nothing.
_BOOLEAN_FILTERS = frozenset({"has_note", "today"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Closed set, per the collection convention: an unsortable field is a 400.
SORTABLE = frozenset({
    "opened_at", "closed_at", "ticker", "status", "pnl_pct", "r_multiple",
    "entry", "exit_price", "held_hours", "realized_pnl_amount",
    # SR53. Both are plan-shaped: `created_at` is the only time an unfilled
    # plan has, and `follow_score` is a ranking, which is a column nobody wants
    # unsorted. `_sorted_rows` already puts valueless rows last in BOTH
    # directions, so a legacy row with no score sinks rather than floating to
    # the top of a descending sort.
    "created_at", "follow_score",
})


def _held_hours(opened_at, closed_at) -> float | None:
    """Holding period in hours. Open positions measure to now, closed ones
    to their close -- so the Trades list can sort both by the same column."""
    if not opened_at:
        return None
    try:
        start = datetime.fromisoformat(opened_at)
        end = datetime.fromisoformat(closed_at) if closed_at else datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds() / 3600.0)
    except (TypeError, ValueError):
        return None


def _open_shares(shares: float | None, legs_realized: list) -> float | None:
    """The share count still exposed to price movement right now.

    `shares` alone is the ORIGINAL size at open, and stays that number even
    after a TP1 partial has already closed part of the position -- it is a
    snapshot of what was bought, not what is still held. Unrealized P&L on
    the remaining position needs the remainder: a plan that closed half at
    TP1 has half the shares left to move, so its live dollar P&L is half
    what the same price move would be on the original size, even though the
    live PERCENTAGE (which is priced off one share, not the count) is
    unaffected. `legs_realized` is `plan.legs_realized` -- each leg's
    `fraction` is the share of the ORIGINAL position that leg closed (see
    `plan_manager.py`'s `_step_active`/`_close_runner`), so summing them is
    the total fraction gone and `1 -` that is what remains.
    """
    if shares is None:
        return None
    closed_fraction = sum(leg.get("fraction", 0) for leg in legs_realized)
    return round(shares * max(0.0, 1.0 - closed_fraction), 4)


def _in_today_scope(status: str, closed_at: str | None) -> bool:
    """Whether a row belongs to the Dashboard's Today scope.

    Two ways in, matching how "Today" was defined once `active` ("Today +
    open") and `today` were merged into one mode: the row has not closed yet
    AT ALL, OR it closed today. A PENDING/ACTIVE/PARTIAL plan (or an open
    legacy trade) stays in Today no matter how old it is -- exactly what the
    lifecycle strip's own PENDING/ACTIVE/PARTIAL counts already do (SR53,
    all-time) -- so this only actually narrows CLOSED/CANCELLED rows, to
    whichever day they actually CLOSED. Keying this off when the row was
    *opened* instead (the previous behaviour) silently dropped any trade that
    ran for more than a day: it closed today but opened earlier, so it never
    matched "opened today" and vanished from the Dashboard's Closed table.
    `closed_at` is `_terminal_at(plan, trade)` for a plan row, `t.get("closed_at")`
    for a legacy one -- both already computed by the caller.
    """
    return status not in _TERMINAL or dash.is_today_berlin(closed_at)


def _terminal_at(plan: dict, trade: dict | None) -> str | None:
    """When a plan-backed row actually reached its terminal state.

    A CLOSED plan always has a trade behind it (closing a position is what
    creates the close), so the trade's own `closed_at` is authoritative. A
    CANCELLED plan never fills -- it has no trade at all -- so the only
    record of when the cancellation happened is the plan's own
    `status_history`, appended by `record_transition` at cancel time.
    """
    if trade and trade.get("closed_at"):
        return trade["closed_at"]
    history = plan.get("status_history") or []
    return history[-1].get("at") if history else None


def _row_from_plan(plan: dict, trade: dict | None, noted: set) -> dict:
    """A plan is the identity; its trade row supplies execution detail.

    Where both carry a field, the PLAN wins for intent (entry, stop, targets)
    and the TRADE wins for what actually happened (fills, exit, sizing).
    """
    t = trade or {}
    opened_at = t.get("opened_at")
    closed_at = t.get("closed_at")
    # A PARTIAL plan has already banked TP1: the position it still carries is
    # the runner, not the original one, so "the plan" it displays has to be
    # the runner's own numbers -- working_stop (break-even, then wherever the
    # chandelier trail has since moved it) and TP2, not the original entry
    # stop/TP1 that already happened. `or` falls back to the original level
    # when a PARTIAL plan has no TP2 (most strategies run without one -- see
    # test_partial_plan_falls_back_when_the_runner_fields_are_unset) or
    # predates working_stop -- showing the last known level beats showing
    # nothing. This is also why a PARTIAL row's "stop" can legitimately sit
    # below entry for a short (it's the runner floor protecting TP1's
    # profit, not the original risk level) -- see PlanCell's `trailing`
    # input / trade-detail's `stopLabel()`, which label it "Trailing stop"
    # rather than leaving it looking like an inverted original stop.
    is_partial = plan.get("status") == "PARTIAL"
    legs_realized = plan.get("legs_realized") or []
    banked_leg = legs_realized[0] if is_partial and legs_realized else None
    current_stop = (plan.get("working_stop") if is_partial else None) or plan.get("stop_loss")
    current_target = (plan.get("tp2") if is_partial else None) or plan.get("tp1")
    return {
        "id": plan["plan_id"],
        "origin": "plan",
        "status": plan.get("status"),
        # The linked trade's own status, or None when no trade exists yet.
        "outcome": t.get("status") if trade else None,
        "ticker": plan.get("ticker"),
        "direction": plan.get("direction"),
        "strategy": plan.get("strategy"),
        "horizon": plan.get("horizon_key"),
        "badge": plan.get("badge"),
        "confidence_level": t.get("confidence_level"),
        "confidence_score": t.get("confidence_score"),
        "quality_score": plan.get("quality_score"),
        "entry": plan.get("entry_price"),
        "stop_loss": current_stop,
        "target": current_target,
        "target2": plan.get("tp2"),
        "banked_fraction": banked_leg.get("fraction") if banked_leg else None,
        "banked_exit_price": banked_leg.get("exit_price") if banked_leg else None,
        "banked_r": banked_leg.get("r") if banked_leg else None,
        "risk_reward": t.get("risk_reward_ratio"),
        "shares": t.get("shares"),
        "open_shares": _open_shares(t.get("shares"), plan.get("legs_realized") or []),
        "position_value": t.get("position_value"),
        "current_price": None,
        "exit_price": t.get("exit_price"),
        "realized_pnl_amount": t.get("realized_pnl_amount"),
        "pnl_pct": dash.closed_pnl(t) if trade else None,
        "r_multiple": dash.closed_r(t) if trade else None,
        # Transient -- consumed and stripped by `_attach_unrealized_pnl`
        # once a live price exists to compute pnl_pct/r_multiple/
        # realized_pnl_amount for a row that hasn't closed yet.
        "_legs": plan.get("legs_realized") or [],
        "_risk_stop": plan.get("stop_loss"),
        "held_hours": _held_hours(opened_at, closed_at),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "has_note": plan["plan_id"] in noted or t.get("id") in noted,
        # Dashboard lifecycle-strip parity: clicking any of the five used to
        # land here with no date filter at all, regardless of the strip's
        # own Today/All days toggle. See `_in_today_scope`.
        "today": _in_today_scope(plan.get("status"), _terminal_at(plan, trade)),
        # SR53 — the plan's own numbers, for a row that has not filled.
        #
        # `opened_at` and `held_hours` both describe an execution, so both are
        # null on a PENDING plan; `created_at` is what it has instead, and it is
        # what the plans board's Age column showed. `trigger_price` is likewise
        # the only actionable price before a fill.
        "created_at": plan.get("created_at"),
        "trigger_price": plan.get("trigger_price"),
        # Composite ranking from analytics.rank. Attached by the caller, which
        # ranks the whole set at once -- scoring one plan in isolation here
        # would mean loading every other plan per row.
        "follow_score": None,
    }


def _row_from_trade(t: dict, noted: set) -> dict:
    """A trade no plan claimed: legacy v1, or an orphan whose plan is gone.

    Orphans are deliberately included rather than dropped -- losing real
    trading history is a worse failure than showing a row unjoined.
    """
    return {
        "id": t.get("id"),
        "origin": "legacy",
        "status": _LEGACY_STATUS.get(t.get("status"), "CLOSED"),
        # Legacy rows ARE the trade, so their raw status is the outcome.
        "outcome": t.get("status"),
        "ticker": t.get("ticker"),
        "direction": t.get("direction"),
        "strategy": t.get("strategy"),
        "horizon": t.get("horizon_key"),
        "badge": t.get("badge"),
        "confidence_level": t.get("confidence_level"),
        "confidence_score": t.get("confidence_score"),
        "quality_score": t.get("quality_score"),
        "entry": t.get("entry"),
        "stop_loss": t.get("stop_loss"),
        "target": t.get("take_profit"),
        "target2": t.get("target2"),
        "banked_fraction": None,
        "banked_exit_price": None,
        "banked_r": None,
        "risk_reward": t.get("risk_reward_ratio"),
        "shares": t.get("shares"),
        # Legacy v1 trades have no PARTIAL status and never scale out --
        # the full size stays open until the whole position closes at once.
        "open_shares": t.get("shares") if t.get("status") == "open" else None,
        "position_value": t.get("position_value"),
        "current_price": None,
        "exit_price": t.get("exit_price"),
        "realized_pnl_amount": t.get("realized_pnl_amount"),
        "pnl_pct": dash.closed_pnl(t),
        "r_multiple": dash.closed_r(t),
        # Transient -- see `_row_from_plan`'s matching fields. Legacy v1
        # trades never scale out, so `_legs` is always empty and `_risk_stop`
        # is always the same value already shown as `stop_loss`.
        "_legs": [],
        "_risk_stop": t.get("stop_loss"),
        "held_hours": _held_hours(t.get("opened_at"), t.get("closed_at")),
        "opened_at": t.get("opened_at"),
        "closed_at": t.get("closed_at"),
        "has_note": t.get("id") in noted,
        # See `_row_from_plan`'s "today" for what this represents.
        "today": _in_today_scope(_LEGACY_STATUS.get(t.get("status"), "CLOSED"),
                                 t.get("closed_at")),
        # SR53. A legacy trade has no plan, so it has no creation time apart
        # from its open, no trigger it waited on, and no ranking. Emitted as
        # null rather than omitted, so both origins return one shape -- the
        # same rule the detail payload follows.
        "created_at": t.get("opened_at"),
        "trigger_price": None,
        "follow_score": None,
    }


def _noted_ids() -> set:
    """Ids with a journal note, for the `has_note` flag and its filter.

    Read once per request rather than per row. A missing or unreadable
    journal degrades to "no notes" -- it must never fail the trades list.
    """
    try:
        from swingbot.core.analytics.journal import JournalStore
        return {
            e.get("trade_id")
            for e in JournalStore().entries()
            if e.get("note")
        }
    except Exception:
        return set()


def _note_for(trade_id: str | None) -> str | None:
    """The note TEXT for one position, for the detail payload.

    `has_note` on the row answers "is there one"; the Notes tab needs the
    words, and there is no journal endpoint in v1 to fetch them from -- so
    without this the tab could write a note through
    `PUT /trades/{id}/note` and then never read it back.

    Notes attach to the TRADE id: `set_note` resolves a plan-backed position
    to its linked trade before writing, so callers must pass the trade id
    rather than the plan id or the lookup silently misses.

    Same defensive read as `_noted_ids` -- an unreadable journal degrades to
    "no note" rather than failing the whole detail response.
    """
    if not trade_id:
        return None
    try:
        from swingbot.core.analytics.journal import JournalStore
        for entry in JournalStore().entries():
            if entry.get("trade_id") == trade_id:
                return entry.get("note") or None
    except Exception:
        return None
    return None


def _attach_follow_scores(rows: list[dict], plans: list[dict]) -> None:
    """Fill in `follow_score` for the plan-backed rows, in one pass.

    SR53. This is the plans board's ranking column, and the parity audit found
    it nowhere in the SPA because it was never on the wire.

    Scored for the whole set at once rather than per row: `follow_score` is a
    composite over the plan population (`analytics.rank`), so scoring one plan
    in isolation would mean loading every other plan once per row. Failure is
    silent and leaves every score None -- a ranking is a nicety, and the list
    itself must not 500 because the ranker did.
    """
    try:
        from swingbot.core.analytics.rank import follow_score
        from swingbot.core.planning.plan_engine import plan_from_dict
    except Exception:
        return

    by_id: dict[str, float] = {}
    for plan in plans:
        try:
            by_id[plan["plan_id"]] = follow_score(plan_from_dict(plan))
        except Exception:
            continue

    for row in rows:
        if row["id"] in by_id:
            row["follow_score"] = by_id[row["id"]]


def build_rows() -> list[dict]:
    """The join. Every row the collection can return, unfiltered."""
    plans = list(PlanStore()._plans.values())
    trades = TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []
    noted = _noted_ids()

    by_plan_id: dict[str, dict] = {}
    for t in trades:
        pid = t.get("plan_id")
        if pid:
            by_plan_id[pid] = t

    rows = [_row_from_plan(p, by_plan_id.get(p.get("plan_id")), noted) for p in plans]
    _attach_follow_scores(rows, plans)

    # Anything no plan claimed. Structural: a trade cannot be emitted twice
    # because it is only reached when its plan_id matched nothing above.
    claimed = {p.get("plan_id") for p in plans}
    rows += [
        _row_from_trade(t, noted)
        for t in trades
        if not t.get("plan_id") or t.get("plan_id") not in claimed
    ]
    return rows


def _looks_like_a_plan_id(value: str) -> bool:
    """NG1's invariant, applied as routing.

    Plan ids are 36-char dashed uuid4s; trade ids are 16 dash-free
    alphanumerics. The spaces are disjoint by length AND by charset, so a
    bare id names its own store and needs no `plan:` / `trade:` prefix.
    Pinned by tests/admin/test_id_uniqueness.py -- if that ever fails, this
    function is the first thing that breaks.
    """
    return len(value) == 36 and value.count("-") == 4


def _plan_detail(plan: dict, trade: dict | None) -> dict:
    """Heavy fields for a plan-backed position.

    `trade_id` is deliberately exposed: the plan id is the public identity,
    but close/cancel/delete act on the underlying trade record, and the SPA
    would otherwise have no way to name it.
    """
    t = trade or {}
    return {
        "trade_id": t.get("id"),
        "note": _note_for(t.get("id")),
        "created_at": plan.get("created_at"),
        "plan_source": plan.get("source"),
        "entry_type": plan.get("entry_type"),
        "trigger_price": plan.get("trigger_price"),
        "expiry_bars": plan.get("expiry_bars"),
        "tp1_fraction": plan.get("tp1_fraction"),
        "breakeven_trigger_fraction": plan.get("breakeven_trigger_fraction"),
        "trail_atr_mult": plan.get("trail_atr_mult"),
        "working_stop": plan.get("working_stop"),
        "runner_high_close": plan.get("runner_high_close"),
        "stop_mult_applied": plan.get("stop_mult_applied"),
        "quality_breakdown": plan.get("quality_breakdown") or [],
        "badge_stats": plan.get("badge_stats") or {},
        "status_history": plan.get("status_history") or [],
        "legs_realized": plan.get("legs_realized") or [],
        "legs": t.get("legs") or [],
        "confidence_breakdown": t.get("confidence_breakdown"),
        "explanation": t.get("explanation"),
        "confirmed_by": t.get("confirmed_by") or [],
        "target_sources": t.get("target_sources") or [],
        "stop_sources": t.get("stop_sources") or [],
        "target2_sources": t.get("target2_sources") or [],
        "sizing_mode": t.get("sizing_mode"),
        "account_balance_after": t.get("account_balance_after"),
    }


def _legacy_detail(t: dict) -> dict:
    """Same keys as _plan_detail, with the plan-only fields None.

    One detail shape rather than two: the SPA renders one Plan tab, and
    branching it on `origin` would double the component for a handful of
    fields that are simply absent on older records.
    """
    return {
        "trade_id": t.get("id"),
        "note": _note_for(t.get("id")),
        "created_at": t.get("opened_at"),
        "plan_source": t.get("source"),
        "entry_type": None,
        "trigger_price": None,
        "expiry_bars": None,
        "tp1_fraction": None,
        "breakeven_trigger_fraction": None,
        "trail_atr_mult": None,
        "working_stop": None,
        "runner_high_close": None,
        "stop_mult_applied": None,
        "quality_breakdown": [],
        "badge_stats": {},
        "status_history": [],
        "legs_realized": [],
        "legs": t.get("legs") or [],
        "confidence_breakdown": t.get("confidence_breakdown"),
        "explanation": t.get("explanation"),
        "confirmed_by": t.get("confirmed_by") or [],
        "target_sources": t.get("target_sources") or [],
        "stop_sources": t.get("stop_sources") or [],
        "target2_sources": t.get("target2_sources") or [],
        "sizing_mode": t.get("sizing_mode"),
        "account_balance_after": t.get("account_balance_after"),
    }


@api_v1.route("/trades/<trade_id>", methods=["GET"])
@require_auth
def get_trade(trade_id: str):
    """One position, as the list row plus a `detail` object.

    Spec v11 open question 1, answered: detail EXTENDS the list row rather
    than being its own shape, so a detail response drops straight into the
    SPA's store beside list rows instead of needing reconciliation.

    Looks in one store, not both -- see _looks_like_a_plan_id.
    """
    noted = _noted_ids()
    log = TradeLog()

    if _looks_like_a_plan_id(trade_id):
        plan = PlanStore()._plans.get(trade_id)
        if plan is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        trade = next(
            (t for t in log.get_trades(status=None, limit=None) or []
             if t.get("plan_id") == trade_id),
            None,
        )
        row = _row_from_plan(plan, trade, noted)
        row["detail"] = _plan_detail(plan, trade)
        # SR53. Ranked against the whole plan population, exactly as the list
        # does -- follow_score is a composite, so scoring this plan alone would
        # give a different number from the one the list shows for the same row.
        # `test_detail_row_fields_match_the_list_exactly` is what caught that.
        _attach_follow_scores([row], list(PlanStore()._plans.values()))
    else:
        trade = log.get_trade_by_id(trade_id)
        if trade is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        row = _row_from_trade(trade, noted)
        row["detail"] = _legacy_detail(trade)

    _attach_current_prices([row])
    _attach_status_fields([row])
    _attach_unrealized_pnl([row])
    _strip_internal_fields([row])
    return jsonify(row)


#: `sort=status` means "how close is this to its target", not the status
#: word. Alphabetical status is meaningless to a trader; progress is the
#: thing the column actually draws. SR16 step 5.
_SORT_ALIASES = {"status": "progress_pct"}


def _sort_key(field: str):
    """None sorts to the bottom rather than raising -- a half-populated row
    must never 500 the whole list."""
    def key(row):
        value = row.get(field)
        return (value is None, value if value is not None else "")
    return key


def _sorted_rows(rows: list[dict], field: str, descending: bool) -> list[dict]:
    """Sort, with valueless rows last in BOTH directions.

    `sort(key=..., reverse=True)` reverses the whole comparison including the
    is-None flag, so the plain version floats every null to the TOP on
    descending -- a user asking for "closest to target first" would get a
    screenful of rows with no live price. Partitioning first is what makes
    "missing" mean "last" rather than "extreme".
    """
    field = _SORT_ALIASES.get(field, field)
    present = [r for r in rows if r.get(field) is not None]
    missing = [r for r in rows if r.get(field) is None]
    try:
        present.sort(key=_sort_key(field), reverse=descending)
    except TypeError:
        # Mixed types in one column: fall back to string order rather than
        # 500 the list.
        present.sort(key=lambda r: str(r.get(field) or ""), reverse=descending)
    return present + missing


def _filter_by_status(rows: list[dict], value: str) -> list[dict]:
    """Match the `status` filter, case-insensitively, with one alias.

    NG54. This was an exact, case-sensitive string compare, which meant the
    SPA's own chips matched nothing: they send the lowercase legacy vocabulary
    (`open`, `cancelled`, `expired`) and rows carry the uppercase plan
    vocabulary. Every chip but "All" returned an empty list, and it looked
    exactly like "no trades in that state".

    `open` is an alias for ACTIVE-or-PARTIAL rather than a status of its own.
    A partially-realised position is still open, and making the user pick
    between two chips to see all their live trades would be exposing how the
    plan lifecycle is stored rather than what they asked for.
    """
    want = value.strip().lower()
    if want == "open":
        return [r for r in rows if r.get("status") in _OPEN_STATUSES]
    return [r for r in rows if str(r.get("status") or "").lower() == want]


@api_v1.route("/trades", methods=["GET"])
@require_auth
def list_trades():
    params = parse_collection_params(
        request.args, allowed_filters=FILTERS, sortable=SORTABLE
    )

    rows = build_rows()

    # Filter -> sort -> slice, in that order, so `total` is the post-filter
    # pre-slice count the collection convention requires.
    for key, value in params.filters.items():
        if key in _BOOLEAN_FILTERS:
            want = str(value).strip().lower() in _TRUTHY
            rows = [r for r in rows if bool(r.get(key)) is want]
        elif key == "status":
            rows = _filter_by_status(rows, str(value))
        elif key == "outcome":
            # Case-insensitive, like status. Values outside _OUTCOMES simply
            # match nothing rather than 400ing: an unknown filter value is a
            # request for an empty set, and the collection convention reserves
            # 400 for a malformed request, not an unsatisfiable one.
            want = str(value).strip().lower()
            rows = [r for r in rows
                    if str(r.get("outcome") or "").lower() == want]
        elif key in _CASELESS_FILTERS:
            want = str(value).strip().lower()
            field = _FILTER_KEYS.get(key, key)
            rows = [r for r in rows
                    if str(r.get(field) or "").strip().lower() == want]
        else:
            field = _FILTER_KEYS.get(key, key)
            rows = [r for r in rows if str(r.get(field) or "") == str(value)]

    field, direction = params.sort or ("opened_at", "desc")
    # progress_pct/pnl_pct/r_multiple are only live-priced AFTER slicing
    # (a price is fetched for at most one page of tickers) -- a sort on any
    # of the three has to compute it for the whole set first, or it sorts on
    # a column that is still None for every open row.
    if _SORT_ALIASES.get(field) == "progress_pct" or field in ("pnl_pct", "r_multiple"):
        _attach_current_prices(rows)
        _attach_status_fields(rows)
        _attach_unrealized_pnl(rows)
    rows = _sorted_rows(rows, field, direction == "desc")

    total = len(rows)
    start = (params.page - 1) * params.per_page
    page_rows = rows[start:start + params.per_page]

    _attach_current_prices(page_rows)
    _attach_status_fields(page_rows)
    _attach_unrealized_pnl(page_rows)
    _strip_internal_fields(page_rows)
    return jsonify(collection(page_rows, total, params.page, params.per_page))


def _status_fields(row: dict, price: float | None) -> dict:
    """The status-bar numbers, from the two functions that already own them.

    `trade_proximity` (core/performance.py) owns urgency and the label -- it
    is the same computation the bot's own near-close alerts use, so a second
    implementation here could make the UI and the alerts disagree about how
    close a trade is to its stop. The 0..100 position is the dashboard's
    (`admin/dashboard.py`, `pos_pct`), restated here rather than imported
    because that module builds a whole Jinja view model to produce it -- and
    that module is deleted at NG57.

    No colour is returned. The band names which pair of tokens the client
    interpolates between; the palette lives in tokens.css, so a repaint is a
    CSS change and never an API change. See spec v18 Decision 5.
    """
    from swingbot.core.tracking.performance import trade_proximity

    entry, sl, tp = row.get("entry"), row.get("stop_loss"), row.get("target")
    direction = row.get("direction") or "bullish"
    label_only = {"progress_pct": None, "entry_pct": None, "progress_band": None,
                  "blink_seconds": None, "status_label": "No live price"}

    if price is None or not all(isinstance(v, (int, float)) for v in (entry, sl, tp)):
        return label_only

    prox = trade_proximity(direction, entry, sl, tp, price)
    is_bull = direction == "bullish"
    span = (tp - sl) if is_bull else (sl - tp)
    if span <= 0:
        # Malformed record -- stop on the wrong side of the target. Degrade to
        # a label rather than render a bar that is confidently backwards.
        return label_only

    pos = ((price - sl) if is_bull else (sl - price)) / span * 100
    ent = ((entry - sl) if is_bull else (sl - entry)) / span * 100
    band = ("toward_target" if prox["proximity"] > 0.15
            else "toward_stop" if prox["proximity"] < -0.15
            else "neutral")
    return {
        # Clamped: price runs past the stop or target all the time, and a bar
        # is 0..100 by definition. The band and label still carry "past it".
        "progress_pct": max(0.0, min(100.0, round(pos, 1))),
        "entry_pct": max(0.0, min(100.0, round(ent, 1))),
        "progress_band": band,
        "blink_seconds": prox["blink_seconds"],
        "status_label": prox["label"],
    }


def _attach_status_fields(rows: list[dict]) -> None:
    """Merge the status-bar fields into every row, terminal ones included.

    Every row gets all five keys. A cell that has to ask whether a field
    exists before reading it is a cell with two rendering paths, and the
    second one only runs on data nobody tests with.
    """
    for row in rows:
        if row["status"] in _TERMINAL or row["status"] == "PENDING":
            # Nothing has opened, or it is already over: there is no position
            # to place on a bar. The label is the status itself, which is what
            # the cell shows in place of the bar.
            row.update({"progress_pct": None, "entry_pct": None,
                        "progress_band": None, "blink_seconds": None,
                        "status_label": row["status"]})
        else:
            row.update(_status_fields(row, row.get("current_price")))


def _attach_unrealized_pnl(rows: list[dict]) -> None:
    """Live pnl_pct/r_multiple/realized_pnl_amount for a row that hasn't
    closed yet -- must run AFTER `_attach_current_prices` so `current_price`
    is there to compute from.

    `_row_from_plan`/`_row_from_trade` leave these three None on every
    still-open row (there is no exit_price yet for `dash.closed_pnl`/
    `closed_r` to read), which is the exact display gap that made a PARTIAL
    position look unpriced -- it has real live P&L, just not the terminal
    kind those two functions compute.

    Reads `_legs`/`_risk_stop` (transient, set by the two row builders) with
    `.get`, not `.pop`: like `_attach_status_fields`, this may run twice on
    the same row objects when a request sorts by a field that needs a price
    for every row, not just the page (see the `_SORT_ALIASES` branch in
    `list_trades`) -- popping here would make the second pass recompute from
    an empty/missing fallback and silently overwrite the first pass's real
    numbers. `_strip_internal_fields` removes both once, at the very end.
    """
    for row in rows:
        if row["status"] in _TERMINAL or row["status"] == "PENDING":
            continue
        price = row.get("current_price")
        entry, direction = row.get("entry"), row.get("direction")
        if price is None or entry is None:
            continue
        row["pnl_pct"] = dash.unrealized_pnl(entry, direction, price)
        row["r_multiple"] = dash.unrealized_r(entry, row.get("_risk_stop"), direction, price)
        row["realized_pnl_amount"] = dash.unrealized_pnl_amount(
            entry, direction, row.get("shares"), row.get("_legs"), price)


def _strip_internal_fields(rows: list[dict]) -> None:
    """Drop the transient `_legs`/`_risk_stop` keys `_attach_unrealized_pnl`
    reads -- must run exactly once, after every other row transform, so
    neither leaks onto the wire and breaks the row's declared shape."""
    for row in rows:
        row.pop("_legs", None)
        row.pop("_risk_stop", None)


def _attach_current_prices(rows: list[dict]) -> None:
    """Live price for the still-open rows ON THIS PAGE only.

    Prefetching after slicing is the whole point: `prefetch_prices` fetches
    concurrently and fills an in-memory cache, so this costs one batched
    round trip for at most `per_page` tickers rather than one per row, and
    never touches the tickers on pages nobody asked for.

    A price failure leaves `current_price` as None. The list must render
    without the network.
    """
    live = [r for r in rows if r["status"] not in _TERMINAL and r.get("ticker")]
    if not live:
        return
    try:
        from swingbot.core.marketdata.data import get_current_price, prefetch_prices
        prefetch_prices([r["ticker"] for r in live])
        for r in live:
            r["current_price"] = get_current_price(r["ticker"])
    except Exception:
        pass


@api_v1.route("/trades/export.csv", methods=["GET"])
@require_auth
def export_trades_csv():
    """Stays CSV rather than JSON (spec v11): rebuilding the file in the SPA
    would mean shipping every row to the browser only to serialise it back,
    and what the user wants is a download.

    Shares its serialiser with the Jinja route so the two cannot drift.
    """
    from flask import Response

    from swingbot.admin.trade_export import FILENAME, trades_csv_bytes

    return Response(
        trades_csv_bytes(TradeLog().get_trades(status=None, limit=None)),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={FILENAME}"},
    )
