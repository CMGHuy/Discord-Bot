"""Read-side helpers the v1 API shares — extracted from `pages.py`.

**Why this module exists.** Release B (spec `v15-jinja-cutover-design`,
Decision 3) deletes `pages.py` outright, and its readiness appendix verified
one coupling before doing so: that no bot path reached chart generation
through the admin HTTP layer (Appendix C1). It did not check the other
direction, and there `pages.py` turned out to be load-bearing —
`swingbot/admin/api_v1/` imported **eleven** symbols from it across
`analytics.py`, `dashboard.py` and `jobs.py`. Deleting the file wholesale, as
the spec instructs, would have taken the Analytics, Dashboard and Tuning
endpoints of the SPA down with the UI it replaced.

So the functions moved here first, unchanged, and only the Jinja half of
`pages.py` was deleted. Nothing in this module renders HTML or touches Flask:
it is queries and shaping, which is exactly why the v1 API wanted it.

`primary_strategy_label` is deliberately NOT here — `pages.py` only
re-exported it, and callers now import it from `swingbot.core.tracking.performance`,
its real home.

Two colour helpers (`_lerp_hex`, `_heatmap_color`) came across with the
extraction and were kept on the stated grounds that `_strategy_horizon_heatmap`
called them. It does not, and did not: its cells have only carried `n` and
`win_rate`. Nothing else referenced them either, so they were deleted on
2026-08-14. Colour is the SPA's decision — `api_v1/analytics.py::_json_heatmap`
projects the matrix without one, and no colour crosses the wire.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from statistics import median

from swingbot import config
from swingbot.core.analytics.metrics import win_rate
from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
from swingbot.core.analytics.rank import follow_score, rank_plans
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.tracking.performance import TradeLog, primary_strategy_label
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES
from swingbot.core.backtesting.registry import load_registry

from .dashboard import is_today_berlin as _is_today_berlin


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


def _reached(plan, status: str) -> bool:
    """Whether `plan` ever transitioned INTO `status`, at any point in its
    history -- not whether it is currently there. The state machine
    (_LEGAL_TRANSITIONS) is monotonic with no backward transition, so a
    plan currently CLOSED may or may not have passed through PARTIAL on the
    way, and only the history says which."""
    return any(h.get("status") == status for h in (plan.status_history or []))


def _days_between(start: str, end: str) -> float:
    """Whole days, swing-trade granularity -- created_at is documented as
    an 'ISO date of the bar/scan', not a precise timestamp, so resolving
    below day granularity would imply precision neither field actually
    carries."""
    return (datetime.fromisoformat(end[:10]) - datetime.fromisoformat(start[:10])).days


def _plan_lifecycle(plans: list) -> dict:
    """Funnel, fill-rate/time-to-fill, and badge/tier distribution over
    every plan ever posted -- the Plans tab's three panels. Walks
    `PlanStore().all()` the same way `_plan_rows` already does, rather than
    a second read path.

    Funnel counts are BY FURTHEST STAGE EVER REACHED (`_reached`), not by
    current status: a plan currently CLOSED may have stopped out directly
    from ACTIVE without ever hitting PARTIAL, so "hit_tp1" cannot be read
    off current status alone.

    fill_rate is scoped to RESOLVED plans (CLOSED or CANCELLED) only --
    a still-PENDING plan hasn't finished its journey yet, and folding it in
    would bias the rate toward "undecided" rather than measure a real
    outcome.
    """
    posted = len(plans)
    filled = sum(1 for p in plans if _reached(p, PlanStatus.ACTIVE))
    hit_tp1 = sum(1 for p in plans if _reached(p, PlanStatus.PARTIAL))
    closed = sum(1 for p in plans if p.status == PlanStatus.CLOSED)
    in_flight = sum(
        1 for p in plans
        if p.status in (PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL)
    )

    resolved = [p for p in plans if p.status in (PlanStatus.CLOSED, PlanStatus.CANCELLED)]
    filled_resolved = [p for p in resolved if _reached(p, PlanStatus.ACTIVE)]
    fill_days = []
    for p in filled_resolved:
        active_entry = next(h for h in p.status_history if h["status"] == PlanStatus.ACTIVE)
        fill_days.append(_days_between(p.created_at, active_entry["at"]))

    badges: dict[str, int] = {}
    tiers: dict[str, int] = {}
    for p in plans:
        badges[p.badge] = badges.get(p.badge, 0) + 1
        tiers[p.tier] = tiers.get(p.tier, 0) + 1

    return {
        "funnel": {"posted": posted, "filled": filled, "hit_tp1": hit_tp1, "closed": closed},
        "in_flight": in_flight,
        "fill_rate": {
            "resolved_n": len(resolved),
            "fill_rate_pct": (
                round(len(filled_resolved) / len(resolved) * 100, 1) if resolved else None
            ),
            "median_days_to_fill": median(fill_days) if fill_days else None,
        },
        "badges": badges,
        "tiers": tiers,
    }


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
            "gate_description": _gate_description(rec["strategy"]),
        })
    return rows


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
    category as dashboard.py's closed_pnl/closed_r -- not an analytics call,
    just windowed arithmetic for a sparkline."""
    ordered = sorted(closed_trades, key=lambda t: t.get("closed_at") or "")
    outcomes = [1 if t["status"] == "win" else 0 for t in ordered if t["status"] in ("win", "loss")]
    points: list[float | None] = []
    for i in range(len(outcomes)):
        chunk = outcomes[max(0, i - window + 1):i + 1]
        points.append(sum(chunk) / len(chunk) * 100 if chunk else None)
    return points


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")  # no '/', '\', or '.' -- blocks path traversal


def _load_result(job_id: str) -> dict | None:
    if not _JOB_ID_RE.match(job_id):
        return None  # reject anything that isn't a real job id -- job_id flows
        # straight from the ?job_id= query param into a filesystem path below
    path = os.path.join(config.DATA_DIR, "tuning_results", f"{job_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _grid_row_passes(stats: dict) -> bool:
    """Same acceptance gate scripts/backtest/tune_strategy.py itself already prints
    -- restated here purely to color a table row, never to decide anything."""
    return (
        stats.get("n_eval", 0) >= 30 and (stats.get("win_rate") or 0) >= 80
        and (stats.get("expectancy_r") or 0) > 0 and stats.get("excluded_share", 1) <= 0.5
    )


TUNING_PROPOSALS_DIR_NAME = "tuning_proposals"


def _list_proposals() -> list[dict]:
    proposals_dir = os.path.join(config.DATA_DIR, TUNING_PROPOSALS_DIR_NAME)
    if not os.path.exists(proposals_dir):
        return []
    rows = []
    for fname in sorted(os.listdir(proposals_dir), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(proposals_dir, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            rows.append({"filename": fname, **data})
        except (OSError, json.JSONDecodeError):
            continue
    return rows


_PROPOSAL_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.json$")
