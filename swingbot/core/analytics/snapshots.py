"""Pure assembly of everything Phase A1/A2 computed into one JSON blob
(data/analytics_snapshot.json) so every UI (!stats, /api/stats, the
Performance page, the Strategies heatmap) reads ONE pre-built file
instead of recomputing on every request -- see design decision #3 in
docs/superpowers/plans/2026-07-11-cockpit-v3.md. build_snapshot itself is
pure (a function of its three arguments); save/load are the only I/O in
this module, both going through jsonio."""
from __future__ import annotations

import dataclasses
import datetime as dt
import os

from swingbot import config
from swingbot.core.analytics import calibration, metrics
from swingbot.core.analytics.aggregate import DIMENSIONS, stats_by
from swingbot.core.jsonio import atomic_write_json, read_json

DEFAULT_PATH = os.path.join(config.DATA_DIR, "analytics_snapshot.json")


def build_snapshot(closed: list[dict], starting_balance: float, registry_entries: list[dict]) -> dict:
    """Assemble the full analytics snapshot from a closed-trade list, the
    account's starting balance, and the already-loaded validation
    registry. Pure -- callers (refresh_snapshot, Task A29) are
    responsible for gathering these three inputs from disk/TradeLog."""
    wins = sum(1 for t in closed if t.get("status") == "win")
    losses = sum(1 for t in closed if t.get("status") == "loss")
    curve = metrics.equity_curve(closed, starting_balance)
    points = curve["points"]
    returns = [r for t in closed if (r := metrics.trade_return_pct(t)) is not None]

    overall = {
        "n": len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate": metrics.win_rate(closed),
        "expectancy_r": metrics.expectancy_r(closed),
        "profit_factor": metrics.profit_factor(closed),
        "sharpe": metrics.sharpe(returns),
        "sortino": metrics.sortino(returns),
        "max_drawdown_pct": metrics.max_drawdown_pct(points),
        "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in closed), 2),
        "streaks": metrics.streaks(closed),
    }

    by = {dim: [dataclasses.asdict(row) for row in stats_by(closed, dim)] for dim in DIMENSIONS}

    calibration_block = {
        "deciles": calibration.score_deciles(closed),
        "tiers": calibration.tier_calibration(closed),
        "drift": calibration.badge_drift(closed, registry_entries),
    }

    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "overall": overall,
        "equity_curve": curve,
        "drawdown": metrics.drawdown_series(points),
        "rolling_wr": metrics.rolling_win_rate(closed),
        "by": by,
        "calibration": calibration_block,
        "r_multiples": metrics.r_multiples(closed),
    }


def save_snapshot(snap: dict, path: str | None = None) -> None:
    atomic_write_json(path or DEFAULT_PATH, snap)


def load_snapshot(path: str | None = None, max_age_seconds: int = 3600) -> dict | None:
    """None when the file is missing/corrupt (read_json's own default
    handles that) OR when it parses fine but is older than
    `max_age_seconds` -- a stale snapshot silently served as fresh would
    be worse than no snapshot at all (the caller, e.g. !stats, falls back
    to an explicit "rebuilding..." path when this returns None, per
    Plan B's consumption of this function)."""
    snap = read_json(path or DEFAULT_PATH, None)
    if snap is None:
        return None
    try:
        built_at = dt.datetime.fromisoformat(snap["built_at"])
    except (KeyError, ValueError, TypeError):
        return None
    if built_at.tzinfo is None:
        built_at = built_at.replace(tzinfo=dt.timezone.utc)
    age = (dt.datetime.now(dt.timezone.utc) - built_at).total_seconds()
    return snap if age <= max_age_seconds else None
