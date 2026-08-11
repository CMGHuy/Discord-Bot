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
from swingbot.core.performance import TradeLog
from swingbot.core.plan_store import PlanStore

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

FILTERS = frozenset({"status", "ticker", "strategy", "horizon", "direction",
                     "tier", "origin", "has_note"})

# Compared as booleans, not as strings. `has_note` is a real bool on the row,
# and the generic comparison below stringifies it -- so `?has_note=1` would
# test "1" == "True" and quietly match nothing.
_BOOLEAN_FILTERS = frozenset({"has_note"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Closed set, per the collection convention: an unsortable field is a 400.
SORTABLE = frozenset({
    "opened_at", "closed_at", "ticker", "status", "pnl_pct", "r_multiple",
    "entry", "exit_price", "held_hours", "realized_pnl_amount",
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


def _row_from_plan(plan: dict, trade: dict | None, noted: set) -> dict:
    """A plan is the identity; its trade row supplies execution detail.

    Where both carry a field, the PLAN wins for intent (entry, stop, targets)
    and the TRADE wins for what actually happened (fills, exit, sizing).
    """
    t = trade or {}
    opened_at = t.get("opened_at")
    closed_at = t.get("closed_at")
    return {
        "id": plan["plan_id"],
        "origin": "plan",
        "status": plan.get("status"),
        "ticker": plan.get("ticker"),
        "direction": plan.get("direction"),
        "strategy": plan.get("strategy"),
        "horizon": plan.get("horizon_key"),
        "tier": plan.get("tier"),
        "badge": plan.get("badge"),
        "confidence_level": t.get("confidence_level"),
        "confidence_score": t.get("confidence_score"),
        "quality_score": plan.get("quality_score"),
        "entry": plan.get("entry_price"),
        "stop_loss": plan.get("stop_loss"),
        "target": plan.get("tp1"),
        "target2": plan.get("tp2"),
        "risk_reward": t.get("risk_reward_ratio"),
        "shares": t.get("shares"),
        "position_value": t.get("position_value"),
        "current_price": None,
        "exit_price": t.get("exit_price"),
        "realized_pnl_amount": t.get("realized_pnl_amount"),
        "pnl_pct": dash.closed_pnl(t) if trade else None,
        "r_multiple": dash.closed_r(t) if trade else None,
        "held_hours": _held_hours(opened_at, closed_at),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "has_note": plan["plan_id"] in noted or t.get("id") in noted,
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
        "ticker": t.get("ticker"),
        "direction": t.get("direction"),
        "strategy": t.get("strategy"),
        "horizon": t.get("horizon_key"),
        "tier": t.get("tier"),
        "badge": t.get("badge"),
        "confidence_level": t.get("confidence_level"),
        "confidence_score": t.get("confidence_score"),
        "quality_score": t.get("quality_score"),
        "entry": t.get("entry"),
        "stop_loss": t.get("stop_loss"),
        "target": t.get("take_profit"),
        "target2": t.get("target2"),
        "risk_reward": t.get("risk_reward_ratio"),
        "shares": t.get("shares"),
        "position_value": t.get("position_value"),
        "current_price": None,
        "exit_price": t.get("exit_price"),
        "realized_pnl_amount": t.get("realized_pnl_amount"),
        "pnl_pct": dash.closed_pnl(t),
        "r_multiple": dash.closed_r(t),
        "held_hours": _held_hours(t.get("opened_at"), t.get("closed_at")),
        "opened_at": t.get("opened_at"),
        "closed_at": t.get("closed_at"),
        "has_note": t.get("id") in noted,
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
    else:
        trade = log.get_trade_by_id(trade_id)
        if trade is None:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        row = _row_from_trade(trade, noted)
        row["detail"] = _legacy_detail(trade)

    _attach_current_prices([row])
    return jsonify(row)


def _sort_key(field: str):
    """None sorts to the bottom in both directions rather than raising --
    a half-populated row must never 500 the whole list."""
    def key(row):
        value = row.get(field)
        return (value is None, value if value is not None else "")
    return key


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
        else:
            rows = [r for r in rows if str(r.get(key) or "") == str(value)]

    field, direction = params.sort or ("opened_at", "desc")
    try:
        rows.sort(key=_sort_key(field), reverse=(direction == "desc"))
    except TypeError:
        rows.sort(key=lambda r: str(r.get(field) or ""), reverse=(direction == "desc"))

    total = len(rows)
    start = (params.page - 1) * params.per_page
    page_rows = rows[start:start + params.per_page]

    _attach_current_prices(page_rows)
    return jsonify(collection(page_rows, total, params.page, params.per_page))


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
        from swingbot.core.data import get_current_price, prefetch_prices
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
