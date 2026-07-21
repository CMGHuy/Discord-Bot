"""Page-rendering blueprint for the cockpit's new sections: Plans,
Strategies, Calibration, Journal, Tuning. Split out of app.py (which keeps
Dashboard/Performance/Watchlist/Settings/Logs) purely to keep any one file
from growing unbounded -- same reasoning as api.py. Every view here uses
app.py's existing require_auth (HTML 401 challenge, not JSON) and _render
helper, since these are full pages a human loads in a browser, not fetch()
targets (those live in api.py).
"""
import dataclasses
import hashlib
import json
import os
from datetime import datetime, timezone

from flask import Blueprint, Response, abort, redirect, render_template, request, send_file, url_for

from swingbot import config
from swingbot.core.analytics.metrics import win_rate
from swingbot.core.analytics.rank import follow_score, rank_plans
from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
from swingbot.core.backtest import ALL_STRATEGIES
from swingbot.core.charts.trade_chart import generate_trade_chart
from swingbot.core.data import get_daily_data
from swingbot.core.performance import TradeLog, primary_strategy_label
from swingbot.core.plan_engine import PlanStatus, plan_to_dict, record_transition
from swingbot.core.plan_store import PlanStore
from swingbot.core.registry import load_registry
from swingbot.core.strategy_types import HORIZONS, STRATEGY_GATES, STRATEGY_RR_OVERRIDE

from .app import MANUAL_CLOSE_QUEUE, _is_today_berlin, _render, require_auth

pages = Blueprint("pages", __name__)

_ALL_PLAN_STATUSES = (
    PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL,
    PlanStatus.CLOSED, PlanStatus.CANCELLED,
)


def _ranked_plan_rows(plans: list) -> list[dict]:
    """Ranks `plans` by analytics.rank.rank_plans (the one shared ordering)
    and serializes each to a JSON-safe dict with its follow_score attached.
    rank_plans itself returns ordered TradePlanV2 objects, not dicts -- this
    is the one place the Plans board / /api/plans convert between the two."""
    ranked = rank_plans(plans)
    return [dict(plan_to_dict(p), follow_score=follow_score(p)) for p in ranked]


def _plan_rows(status: str | None = None, tier: str | None = None,
               badge: str | None = None, ticker: str | None = None) -> dict:
    """Shared by the Plans board page (this task) and /api/plans (api.py
    imports this function instead of keeping its own copy). Counts are
    always computed from the UNFILTERED set (Task C15 refines this
    further to scope CLOSED/CANCELLED counts to "today")."""
    all_plans = PlanStore().all()
    counts = {s: 0 for s in _ALL_PLAN_STATUSES}
    for p in all_plans:
        if p.status in (PlanStatus.CLOSED, PlanStatus.CANCELLED):
            last_at = p.status_history[-1]["at"] if p.status_history else None
            if not _is_today_berlin(last_at):
                continue  # only today's closes/cancels count toward the strip
        counts[p.status] = counts.get(p.status, 0) + 1

    rows = _ranked_plan_rows(all_plans)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    if badge:
        rows = [r for r in rows if r["badge"] == badge]
    if ticker:
        needle = ticker.strip().upper()
        rows = [r for r in rows if needle in r["ticker"].upper()]
    return {"plans": rows, "counts": counts}


def _render_plans_board(rows: list, counts: dict, filters: dict) -> str:
    return render_template("_plans_board.html", plans=rows, counts=counts, filters=filters)


@pages.route("/plans", methods=["GET"])
@require_auth
def plans_page():
    filters = {
        "status": request.args.get("status", ""),
        "tier": request.args.get("tier", ""),
        "badge": request.args.get("badge", ""),
        "ticker": request.args.get("ticker", ""),
    }
    result = _plan_rows(status=filters["status"] or None, tier=filters["tier"] or None,
                        badge=filters["badge"] or None, ticker=filters["ticker"] or None)
    fragment = _render_plans_board(result["plans"], result["counts"], filters)
    return _render("Plans", "plans", "plans.html", fragment=fragment,
                   dashboard_refresh_seconds=config.DASHBOARD_REFRESH_SECONDS)


@pages.route("/plans/fragment", methods=["GET"])
@require_auth
def plans_fragment():
    """Same ETag'd auto-refresh pattern as app.py's dashboard_fragment
    (C10) -- see that function's docstring for the rationale. Polled by
    plans.html's own JS every config.DASHBOARD_REFRESH_SECONDS, preserving
    whatever filter query params are currently in the URL so a filtered
    view keeps polling that same filtered slice."""
    filters = {
        "status": request.args.get("status", ""),
        "tier": request.args.get("tier", ""),
        "badge": request.args.get("badge", ""),
        "ticker": request.args.get("ticker", ""),
    }
    result = _plan_rows(status=filters["status"] or None, tier=filters["tier"] or None,
                        badge=filters["badge"] or None, ticker=filters["ticker"] or None)
    html = _render_plans_board(result["plans"], result["counts"], filters)
    etag = hashlib.sha1(html.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.headers["ETag"] = etag
    return resp


def _gate_description(strategy: str) -> str:
    """Human-readable rendering of a STRATEGY_GATES entry -- e.g.
    Fibonacci's real current {"directions": ("bullish",)} becomes
    "bullish only"; VWAP's {"directions": ("bullish",),
    "horizons": ("4w","6m","7m","8m","9m")} becomes
    "bullish only {4w,6m,7m,8m,9m}". A missing key means no gate at all
    (both directions, every horizon)."""
    gate = STRATEGY_GATES.get(strategy)
    if not gate:
        return "no gate (all directions, all horizons)"
    parts = []
    directions = gate.get("directions")
    if directions:
        parts.append(f"{'/'.join(directions)} only" if len(directions) == 1 else "/".join(directions))
    horizons = gate.get("horizons")
    if horizons:
        parts.append("{" + ",".join(horizons) + "}")
    return " ".join(parts) if parts else "no gate (all directions, all horizons)"


def _registry_rows() -> list[dict]:
    """Shared by /strategies (this task) and /api/registry (C9 -- api.py
    imports this instead of keeping its own copy). snap["by"]["strategy"]
    is a LIST of StatRow dicts (each carrying its dimension value in
    "key"), not a strategy-name-keyed dict -- see aggregate.py's StatRow /
    snapshots.py's build_snapshot -- so it's converted below exactly like
    the original C9 api.py implementation did.

    load_registry() returns one record per (strategy, horizon) plus a
    pooled (horizon=None) record per strategy, plus a non-strategy "ALL"
    pseudo-entry. This page wants one summary row per real strategy, so it
    filters to the pooled record (horizon is None) for each name in
    ALL_STRATEGIES -- that also makes the strategy->record mapping
    deterministic (no ambiguity from multiple records sharing a strategy
    key)."""
    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    by_strategy_rows = ((snap or {}).get("by") or {}).get("strategy", [])
    by_strategy = {row["key"]: row for row in by_strategy_rows}
    drift_by_strategy = {d["strategy"]: d for d in ((snap or {}).get("calibration") or {}).get("drift") or []}
    rows = []
    for rec in load_registry():
        if rec.get("horizon") is not None or rec["strategy"] not in ALL_STRATEGIES:
            continue
        live = by_strategy.get(rec["strategy"], {})
        drift = drift_by_strategy.get(rec["strategy"], {})
        live_wr = live.get("win_rate")
        rows.append({
            **rec,
            "live_n": live.get("n"),
            "live_wr": live_wr,
            "delta_vs_oos": (live_wr - rec["win_rate"]) if live_wr is not None else None,
            "decayed": bool(drift.get("drift_alert")),
            "rr_override": STRATEGY_RR_OVERRIDE.get(rec["strategy"]),
            "gate_description": _gate_description(rec["strategy"]),
        })
    return rows


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _heatmap_color(win_rate: float) -> str:
    """Linear red (<=60) -> amber (75) -> green (>=85)."""
    if win_rate <= 60:
        return "#da6d6d"
    if win_rate >= 85:
        return "#6dda9e"
    if win_rate <= 75:
        return _lerp_hex("#da6d6d", "#e2b25a", (win_rate - 60) / 15)
    return _lerp_hex("#e2b25a", "#6dda9e", (win_rate - 75) / 10)


def _strategy_horizon_heatmap() -> dict:
    """Live win-rate per (strategy, horizon) cell, grouped directly here
    since aggregate.stats_by only supports a single grouping dimension,
    not a joint (strategy, horizon) cross-tab. Relabels each trade's
    strategy via primary_strategy_label first -- the raw t["strategy"]
    field is a fixed placeholder for confluence-engine trades (see
    performance.primary_strategy_label's own docstring), so grouping on
    it directly would silently misbucket almost every real trade. Reuses
    metrics.win_rate() for the actual ratio -- same definition as every
    other win-rate number in this cockpit, not reimplemented here."""
    tl = TradeLog()
    closed = [t for t in tl.get_trades(status=None, limit=None) if t["status"] in ("win", "loss", "closed")]
    horizons = list(HORIZONS.keys())
    buckets: dict[tuple[str, str], list[dict]] = {}
    for t in closed:
        strategy = primary_strategy_label(t)
        horizon = t.get("horizon_key") or "unknown"
        buckets.setdefault((strategy, horizon), []).append(t)
    matrix = {}
    for s in ALL_STRATEGIES:
        for h in horizons:
            group = buckets.get((s, h), [])
            matrix[(s, h)] = {"n": len(group), "win_rate": win_rate(group)}
    return {"strategies": list(ALL_STRATEGIES), "horizons": horizons, "matrix": matrix}


def _rolling_win_rate_series(closed_trades: list[dict], window: int = 10) -> list[float | None]:
    """Rolling win-rate (0-100 scale) over a strategy's own closed-trade
    sequence, ordered by closed_at. Same "small per-trade display helper"
    category as app.py's _closed_pnl/_closed_r -- not an analytics call,
    just windowed arithmetic for a sparkline."""
    ordered = sorted(closed_trades, key=lambda t: t.get("closed_at") or "")
    outcomes = [1 if t["status"] == "win" else 0 for t in ordered if t["status"] in ("win", "loss")]
    points: list[float | None] = []
    for i in range(len(outcomes)):
        chunk = outcomes[max(0, i - window + 1):i + 1]
        points.append(sum(chunk) / len(chunk) * 100 if chunk else None)
    return points


def _sparkline_svg(points: list, *, width: int = 120, height: int = 28,
                    ref: float | None = 80.0) -> str:
    """Inline <svg> polyline sparkline over a 0-100 scale. `ref` draws a
    dashed horizontal reference line (the 80% OOS win-rate bar) so the eye
    has a fixed anchor point. Reused verbatim by Task C43's dashboard
    equity-curve card. Empty data -> em-dash (nothing to draw)."""
    pts = [p for p in points if p is not None]
    if not pts:
        return "&mdash;"
    n = len(pts)

    def _xy(i, v):
        x = (i / max(n - 1, 1)) * width
        y = height - (v / 100.0) * height
        return f"{x:.1f},{y:.1f}"

    poly = " ".join(_xy(i, v) for i, v in enumerate(pts))
    last = pts[-1]
    color = "#6dda9e" if last >= 80 else ("#e2b25a" if last >= 60 else "#da6d6d")
    ref_line = ""
    if ref is not None:
        ry = height - (ref / 100.0) * height
        ref_line = f'<polyline class="spark-ref" stroke="#9aa0b0" points="0,{ry:.1f} {width},{ry:.1f}" />'
    return (
        f'<svg class="sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f"{ref_line}"
        f'<polyline class="spark-line" stroke="{color}" points="{poly}" />'
        f"</svg>"
    )


@pages.route("/strategies", methods=["GET"])
@require_auth
def strategies_page():
    rows = _registry_rows()
    tl = TradeLog()
    closed = [t for t in tl.get_trades(status=None, limit=None) if t["status"] in ("win", "loss", "closed")]
    labeled = [{**t, "strategy": primary_strategy_label(t)} for t in closed]
    for row in rows:
        strat_trades = [t for t in labeled if t["strategy"] == row["strategy"]]
        row["sparkline_svg"] = _sparkline_svg(_rolling_win_rate_series(strat_trades, window=10))
    return _render("Strategies", "strategies", "strategies.html",
                   rows=rows, heatmap=_strategy_horizon_heatmap(),
                   heatmap_color=_heatmap_color)


@pages.route("/calibration", methods=["GET"])
@require_auth
def calibration_page():
    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    calibration = (snap or {}).get("calibration", {})
    chart_data_json = json.dumps({"deciles": calibration.get("deciles", [])})
    return _render(
        "Calibration", "calibration", "calibration.html",
        tiers=calibration.get("tiers", []), drift=calibration.get("drift", []),
        chart_data_json=chart_data_json,
    )


@pages.route("/journal", methods=["GET"])
@require_auth
def journal_page():
    return _render("Journal", "journal", "journal.html")


@pages.route("/tuning", methods=["GET"])
@require_auth
def tuning_page():
    return _render("Tuning", "tuning", "tuning.html")


def _queue_manual_close_notify(plan) -> None:
    """Same file app.py's close_trade route already appends to (see
    MANUAL_CLOSE_QUEUE's module docstring in app.py) -- the bot's own poll
    loop picks this up and posts the transition to Discord. A plan-level
    entry is tagged "kind": "plan_transition" so the bot's consumer can
    format it distinctly from a raw trade-close entry.

    NOTE (verified against the real consumer as of this task): the queue
    write below happens, but swingbot/core/scanning/embeds.py's
    notify_closed_trades() -- the function that actually reads this file
    and posts to Discord -- only recognizes trade.get("status") in
    {"win", "loss", "closed"} (lowercase) and has no notion of a "kind"
    field. A TradePlanV2's status is uppercase ("CANCELLED"/"CLOSED"), so
    every entry this function writes is currently silently skipped by that
    consumer. This is a known, out-of-scope gap for this task (see the
    task report) -- the write itself is harmless and matches the brief.
    """
    try:
        existing = []
        if os.path.exists(MANUAL_CLOSE_QUEUE):
            with open(MANUAL_CLOSE_QUEUE, "r") as f:
                existing = json.load(f)
        existing.append({"kind": "plan_transition", **dataclasses.asdict(plan)})
        with open(MANUAL_CLOSE_QUEUE, "w") as f:
            json.dump(existing, f)
    except Exception:
        pass  # best-effort notify -- never block the actual state transition on this


@pages.route("/plans/<plan_id>/cancel", methods=["POST"])
@require_auth
def plan_cancel(plan_id):
    store = PlanStore()
    plan = store.get(plan_id)
    if not plan:
        abort(404, f"No plan found with id '{plan_id}'.")
    if plan.status != PlanStatus.PENDING:
        abort(400, "Only PENDING plans can be cancelled.")
    # at= passed explicitly (not left as record_transition's None default):
    # the C15 lifecycle-strip's "today" count (_plan_rows above) reads
    # status_history[-1]["at"] through _is_today_berlin, which returns False
    # for None -- an implicit-None "at" would make this cancel invisible to
    # today's CANCELLED count.
    record_transition(plan, PlanStatus.CANCELLED, reason="manual",
                       at=datetime.now(timezone.utc).isoformat())
    store.update(plan)
    _queue_manual_close_notify(plan)
    return redirect(url_for("pages.plans_page", msg=f"Plan {plan.ticker} cancelled.", ok=1))


@pages.route("/plans/<plan_id>/close", methods=["POST"])
@require_auth
def plan_close(plan_id):
    store = PlanStore()
    plan = store.get(plan_id)
    if not plan:
        abort(404, f"No plan found with id '{plan_id}'.")
    if plan.status not in (PlanStatus.ACTIVE, PlanStatus.PARTIAL):
        abort(400, "Only ACTIVE/PARTIAL plans can be closed.")
    tl = TradeLog()
    linked = next((t for t in tl.get_trades(status=None, limit=None) if t.get("plan_id") == plan_id), None)
    if linked and linked["status"] == "open":
        tl.close_trade_manual(linked["id"], reason="manual (plan close, admin UI)")
    # at= passed explicitly -- see the comment in plan_cancel above.
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                       at=datetime.now(timezone.utc).isoformat())
    store.update(plan)
    _queue_manual_close_notify(plan)
    return redirect(url_for("pages.plans_page", msg=f"Plan {plan.ticker} closed.", ok=1))


@pages.route("/plans/<plan_id>", methods=["GET"])
@require_auth
def plan_detail_page(plan_id):
    plan = PlanStore().get(plan_id)
    if not plan:
        abort(404, f"No plan found with id '{plan_id}'.")

    tl = TradeLog()
    linked_trade = next(
        (t for t in tl.get_trades(status=None, limit=None) if t.get("plan_id") == plan_id), None,
    )

    # analytics.rank may or may not expose a per-plan breakdown function
    # depending on how far Plan A's own scope went -- fall back to the
    # score alone (already shown in badge_stats/quality_score) rather than
    # failing the whole page over an optional enrichment.
    follow_breakdown = None
    try:
        from swingbot.core.analytics.rank import follow_breakdown as _follow_breakdown
        follow_breakdown = _follow_breakdown(plan)
    except (ImportError, AttributeError):
        follow_breakdown = None

    return _render(
        f"{plan.ticker} — Plan {plan.plan_id[:8]}", "plans", "plan_detail.html",
        plan=plan, linked_trade=linked_trade, follow_breakdown=follow_breakdown,
    )


@pages.route("/plans/<plan_id>/chart.png", methods=["GET"])
@require_auth
def plan_chart_image(plan_id):
    plan = PlanStore().get(plan_id)
    if not plan:
        abort(404)
    df = get_daily_data(plan.ticker)
    if df is None:
        abort(404, "Could not fetch chart data for this plan right now (data fetch may have failed).")
    h = HORIZONS.get(plan.horizon_key, {})
    path = generate_trade_chart(
        plan.ticker, df,
        entry=plan.entry_price or plan.trigger_price,
        stop_loss=plan.stop_loss, take_profit=plan.tp1,
        direction=plan.direction, strategy=plan.strategy,
        horizon_label=h.get("label", plan.horizon_key),
        out_dir=config.TRADE_CHART_DIR,
        filename=f"{plan.ticker}_{plan.plan_id}_plan.png",
    )
    return send_file(path, mimetype="image/png")
