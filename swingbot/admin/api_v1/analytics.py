"""GET /api/v1/analytics/* — the historical-analysis surface.

Spec 3 folds Performance, Strategies, Calibration and Tuning into one
Analytics workspace, rendered as four tabs (spec v14 Decision 6). These
endpoints back those tabs.

**"UI renders, analytics computes."** Every figure here already exists,
computed by `swingbot.core.analytics` and cached in
`data/analytics_snapshot.json`. These routes project it; they do not
derive. The one exception is `/performance`, which assembles the six
metrics spec 3 relocated from the Dashboard header out of
`TradeLog.get_extended_stats` -- an assembly of existing values, not a new
calculation.

Rendered artefacts are stripped. The old `pages._sparkline_svg` gave Jinja an
`<svg>` string; the SPA gets the underlying series and draws it itself,
because sub-project 3 owns how a sparkline looks.
"""
from __future__ import annotations

from datetime import datetime

from flask import jsonify, request

from swingbot.core.tracking.performance import TradeLog

from . import ApiError, _positive_int, api_v1
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


def _iso_day(name: str) -> str | None:
    """Read a `YYYY-MM-DD` query parameter, or raise ApiError.

    A malformed date is a 400, never a silently-dropped filter. Accepting
    `?from=last-tuesday` and quietly returning the whole history is how a user
    ends up reading all-time numbers as this month's -- the same class of bug
    SR52 fixed on the Trades list, where filters applied only to the rows that
    happened to be on screen.
    """
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ApiError("invalid", f"{name} must be a YYYY-MM-DD date", 400)
    return raw


@api_v1.route("/analytics/performance", methods=["GET"])
@require_auth
def analytics_performance():
    """Overall record, the six metrics relocated from the Dashboard, and
    (SR54) every figure `stats.html` used to derive in browser JS.

    Spec 3 accepted the cost of moving wins, losses, avg realised P&L, best
    trade, worst trade and avg holding period one click away. They have to
    actually arrive here, or that trade was a straight loss -- hence the
    explicit block below rather than dumping get_stats() wholesale.

    **What `?from=`/`?to=` scopes, and what it does not.** The range drives
    `derived`, `distributions` and the four series; the top-level `win_rate`
    and `expectancy_r` stay all-time, unchanged from before SR54, because
    existing clients read them as the account's overall record. The scoped
    copies live inside `derived` alongside everything else the range moves, so
    a workspace showing "March" reads one block and gets a consistent answer
    rather than mixing a scoped Calmar with an all-time win rate.

    Every figure is computed in `core.analytics.metrics` -- this route selects
    and assembles, it does not derive. That is the same "one definition per
    stat" rule that keeps `aggregate.py` delegating, and the reason the
    annualised Sharpe here is `sharpe() * annualisation_factor()` rather than
    a second Sharpe expression written inline.
    """
    from swingbot.admin.dashboard import closed_pnl
    from swingbot.core.analytics import metrics as m

    start, end = _iso_day("from"), _iso_day("to")

    tl = TradeLog()
    all_raw = tl.get_trades(status=None, limit=None) or []
    stats = tl.get_stats(trades=all_raw)
    stats.update(tl.get_extended_stats(trades=all_raw))

    closed = [t for t in all_raw if t.get("status") in ("win", "loss", "closed")]
    realized = [p for p in (closed_pnl(t) for t in closed) if p is not None]

    scoped = m.in_date_range(closed, start=start, end=end)
    returns = [r for r in (m.trade_return_pct(t) for t in scoped) if r is not None]
    factor = m.annualisation_factor(scoped)
    raw_sharpe, raw_sortino = m.sharpe(returns), m.sortino(returns)

    return jsonify({
        "totals": {
            "total": stats.get("total"),
            "open": stats.get("open"),
            "closed": stats.get("closed"),
        },
        # The six spec 3 moved here from the Dashboard header.
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

        "range": {
            "from": start, "to": end,
            "span_years": (round(sy, 4) if (sy := m.span_years(scoped)) is not None else None),
            "n": len(scoped),
        },
        "derived": {
            "avg_win_pct": m.avg_win_pct(scoped),
            "avg_loss_pct": m.avg_loss_pct(scoped),
            "total_return_pct": m.total_return_pct(scoped),
            "annualised_return_pct": m.annualised_return_pct(scoped),
            "calmar": m.calmar(scoped),
            "volatility_ann_pct": m.volatility_ann_pct(scoped),
            "trades_per_month": m.trades_per_month(scoped),
            "pct_in_market": m.pct_in_market(scoped),
            # Annualised by multiplying the module's per-trade ratio, never by
            # re-deriving one here -- see this docstring's last paragraph.
            "sharpe_ann": round(raw_sharpe * factor, 4) if raw_sharpe is not None else None,
            "sortino_ann": round(raw_sortino * factor, 4) if raw_sortino is not None else None,
            "win_rate": m.win_rate(scoped),
            "expectancy_r": m.expectancy_r(scoped),
        },
        "distributions": {
            "returns": m.histogram(returns, bins=12),
            "r_multiples": m.histogram(m.r_multiples(scoped), bins=12),
        },
        "rolling_returns": m.rolling_return_pct(scoped),
        "holding_period_split": m.holding_period_split(scoped),
        "calendar": m.calendar_returns(scoped),
        "cumulative_by_strategy": m.cumulative_pnl_by_strategy(scoped),
        # Best-effort: get_extended_stats swallows a failed yfinance fetch and
        # returns {}. The key is always present so the workspace never has to
        # distinguish "no benchmark" from "no such field".
        "benchmark": {"spy_cum": stats.get("spy_cum") or {}},
    })


@api_v1.route("/analytics/journal", methods=["GET"])
@require_auth
def analytics_journal():
    """SR55 — the trailing-week digest and the recurring lessons.

    Both already existed (`core.analytics.insights`) and were rendered by the
    since-deleted `pages.py:journal_page`; only the API in front of them was
    missing, which is why the parity audit found this cluster with nothing on
    the wire.

    This is NOT a rebuilt Journal page. Spec v14 Decision 4 collapsed that
    page deliberately: the digest and lessons are analytics and belong on the
    Analytics workspace, while a single trade's excursions belong beside the
    note that explains them, on the detail view. Serving both from here would
    re-create the page the IA change removed.

    `today` comes from the server clock rather than a parameter. The digest is
    "the trailing week", and letting a client choose the anchor would turn a
    fixed report into an ad-hoc query with no pre-registered meaning.
    """
    import datetime as dt

    from swingbot.core.analytics.insights import top_lessons, weekly_digest
    from swingbot.core.analytics.journal import JournalStore

    raw_lessons = (request.args.get("lessons") or "").strip()
    lessons_n = _positive_int(raw_lessons, "lessons") if raw_lessons else 5

    try:
        entries = JournalStore().entries()
    except Exception:
        # Same posture as `_noted_ids`: an unreadable journal degrades to
        # "nothing to report" rather than failing an analytics tab whose
        # other panels came from elsewhere and are fine.
        entries = []

    tl = TradeLog()
    closed = [t for t in (tl.get_trades(status=None, limit=None) or [])
              if t.get("status") in ("win", "loss", "closed")]

    return jsonify({
        "digest": weekly_digest(entries, closed, today=dt.datetime.now().date()),
        "lessons": top_lessons(entries, n=lessons_n),
        # The sample behind both lists. A digest drawn from three entries and
        # one drawn from three hundred should not read the same way.
        "entries_n": len(entries),
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
    from swingbot.admin.queries import (
        _registry_rows,
        _rolling_win_rate_series,
        _strategy_horizon_heatmap,
    )
    from swingbot.core.tracking.performance import primary_strategy_label

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
    from swingbot.admin.queries import _registry_rows

    return jsonify({"registry": _registry_rows()})
