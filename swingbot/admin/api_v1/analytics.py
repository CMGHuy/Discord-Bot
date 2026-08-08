"""GET /api/v1/analytics/* — the historical-analysis surface.

Spec 3 folds Performance, Strategies, Calibration and Tuning into one
Analytics workspace, rendered as four tabs (spec v14 Decision 6). These
endpoints back those tabs.

**"UI renders, analytics computes."** Every figure here already exists,
computed by `swingbot.core.analytics` and cached in
`data/analytics_snapshot.json`. These routes project it; they do not
derive. The one exception is `/performance`, which assembles the six
metrics spec 3 relocated from the Cockpit header out of
`TradeLog.get_extended_stats` -- an assembly of existing values, not a new
calculation.

Rendered artefacts are stripped. `pages._sparkline_svg` gives Jinja an
`<svg>` string; the SPA gets the underlying series and draws it itself,
because sub-project 3 owns how a sparkline looks.
"""
from __future__ import annotations

from flask import jsonify, request

from swingbot.core.performance import TradeLog

from . import api_v1
from .auth import require_auth


def _snapshot(fresh: bool = False) -> dict:
    """The analytics snapshot, self-healing.

    A missing or expired snapshot rebuilds on this very request rather than
    500ing -- the behaviour /api/stats already has, and the reason the
    Analytics workspace works on a fresh install.
    """
    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot

    if fresh:
        refresh_snapshot()
        return load_snapshot(max_age_seconds=3600) or {}
    return load_snapshot(max_age_seconds=3600) or refresh_snapshot() or {}


@api_v1.route("/analytics/snapshot", methods=["GET"])
@require_auth
def analytics_snapshot():
    """The whole snapshot, forwarded verbatim (was /api/stats)."""
    return jsonify(_snapshot(fresh=request.args.get("fresh") == "1"))


@api_v1.route("/analytics/performance", methods=["GET"])
@require_auth
def analytics_performance():
    """Overall record, INCLUDING the six metrics relocated from the Cockpit.

    Spec 3 accepted the cost of moving wins, losses, avg realised P&L, best
    trade, worst trade and avg holding period one click away. They have to
    actually arrive here, or that trade was a straight loss -- hence the
    explicit block below rather than dumping get_stats() wholesale.
    """
    from swingbot.admin.dashboard import closed_pnl

    tl = TradeLog()
    all_raw = tl.get_trades(status=None, limit=None) or []
    stats = tl.get_stats(trades=all_raw)
    stats.update(tl.get_extended_stats(trades=all_raw))

    closed = [t for t in all_raw if t.get("status") in ("win", "loss", "closed")]
    realized = [p for p in (closed_pnl(t) for t in closed) if p is not None]

    return jsonify({
        "totals": {
            "total": stats.get("total"),
            "open": stats.get("open"),
            "closed": stats.get("closed"),
        },
        # The six spec 3 moved here from the Cockpit header.
        "relocated": {
            "wins": stats.get("wins"),
            "losses": stats.get("losses"),
            "avg_realized_pct": round(sum(realized) / len(realized), 2) if realized else None,
            "best_trade_pct": round(max(realized), 2) if realized else None,
            "worst_trade_pct": round(min(realized), 2) if realized else None,
            "avg_holding_days": stats.get("avg_holding_days"),
        },
        "win_rate": stats.get("win_rate"),
        "expectancy_r": stats.get("expectancy_r"),
        "by_confidence": tl.get_stats_by_confidence(),
    })


def _json_heatmap(heatmap: dict) -> dict:
    """Flatten the (strategy, horizon) matrix into JSON-addressable cells.

    `_strategy_horizon_heatmap` keys its matrix by a TUPLE, which Jinja is
    happy to index and json.dumps refuses outright. Rather than inventing a
    delimiter-joined string key the client would have to parse apart again,
    the matrix becomes a list of explicit cells -- each carrying its own
    strategy and horizon -- with the axes preserved alongside so the SPA can
    still lay out a grid without deriving them.
    """
    return {
        "strategies": heatmap.get("strategies", []),
        "horizons": heatmap.get("horizons", []),
        "cells": [
            {"strategy": s, "horizon": h, "n": cell.get("n"),
             "win_rate": cell.get("win_rate")}
            for (s, h), cell in (heatmap.get("matrix") or {}).items()
        ],
    }


@api_v1.route("/analytics/strategies", methods=["GET"])
@require_auth
def analytics_strategies():
    """Per-strategy record plus the strategy x horizon heatmap.

    The rolling win-rate series ships as numbers; the Jinja page renders the
    same data as an inline SVG.
    """
    from swingbot.admin.pages import (
        _registry_rows,
        _rolling_win_rate_series,
        _strategy_horizon_heatmap,
        primary_strategy_label,
    )

    rows = _registry_rows()
    closed = [
        t for t in TradeLog().get_trades(status=None, limit=None) or []
        if t.get("status") in ("win", "loss", "closed")
    ]
    labeled = [{**t, "strategy": primary_strategy_label(t)} for t in closed]
    for row in rows:
        strat = [t for t in labeled if t["strategy"] == row["strategy"]]
        row["win_rate_series"] = _rolling_win_rate_series(strat, window=10)

    return jsonify({"strategies": rows, "heatmap": _json_heatmap(_strategy_horizon_heatmap())})


@api_v1.route("/analytics/calibration", methods=["GET"])
@require_auth
def analytics_calibration():
    calibration = _snapshot().get("calibration", {})
    return jsonify({
        "deciles": calibration.get("deciles", []),
        "tiers": calibration.get("tiers", []),
        "drift": calibration.get("drift", []),
    })


@api_v1.route("/analytics/registry", methods=["GET"])
@require_auth
def analytics_registry():
    from swingbot.admin.pages import _registry_rows

    return jsonify({"registry": _registry_rows()})
