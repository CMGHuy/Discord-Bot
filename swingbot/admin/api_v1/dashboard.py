"""GET /api/v1/dashboard — the nine metrics of spec 3's header.

**Not `swingbot/admin/dashboard.py`.** That is the Jinja UI's view-model
builder module, and this file imports it as `dash`. The two have shared a name
since SR4 renamed this one from `cockpit.py` (plan v21, spec v18 Decision 7);
they are different packages and there is no import ambiguity, but a reader
grepping for "dashboard.py" will find both. The Jinja one dies at NG57.


Fourteen equal-weight stat cards became three large cards and six compact
chips. This endpoint returns exactly those nine:

    primary   account_balance · open_pnl_pct · risk_used_pct
    chips     open_trades · avg_confidence · win_rate · expectancy_r ·
              equity_30d · position_premium

The six that moved to Analytics -- wins, losses, avg realised P&L, best
trade, worst trade, avg holding period -- are deliberately NOT here. They
are served by /api/v1/analytics/performance. Spec 3 accepted the cost of
that move, so re-adding one here is a design change, not a convenience.

**Nothing is computed in this module.** Spec 3's constraint is "UI renders,
analytics computes": every figure is projected from `dashboard`'s existing
builders, `TradeLog.get_stats`, or `_collect_portfolio_state`. A second
definition of win rate here would drift from the one the Jinja UI shows,
and the two would disagree during the whole migration.

The equity sparkline ships as numbers. `dashboard.build_equity_curve()`
returns a rendered `<svg>` string because Jinja needs one; sub-project 3
owns how a sparkline looks in the SPA, and a server that ships markup has
taken that decision away from it.
"""
from __future__ import annotations

from flask import jsonify

from swingbot import config
from swingbot.admin import dashboard as dash
from swingbot.core.performance import TradeLog

from . import api_v1
from .auth import require_auth


def _equity_30d() -> dict:
    """The last 30 balance points, raw, plus the window's change.

    Reads the same analytics snapshot `build_equity_curve` does, but stops
    before the SVG: the SPA gets the series and draws it itself.
    """
    try:
        from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
        snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
        points = [
            p["balance"]
            for p in ((snap or {}).get("equity_curve") or {}).get("points", [])[-30:]
        ]
    except Exception:
        points = []

    first = points[0] if points else None
    change = (
        round((points[-1] - first) / first * 100.0, 2)
        if first else None
    )
    return {"points": points, "change_pct": change}


def _risk_used() -> tuple[float | None, float | None]:
    """Open portfolio heat, and the cap it is measured against.

    Spec 3 promotes this from the Risk page because current exposure
    belongs beside current P&L. The cap travels with it -- a heat figure
    without its cap says nothing about whether you are near the limit.

    Degrades to (None, cap) rather than failing: every other collector on
    the Risk page already treats heat as best-effort, and the Dashboard is
    the landing page.
    """
    cap = float(getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0))
    try:
        from swingbot.commands.growth import _collect_portfolio_state
        state = _collect_portfolio_state()
        return state.get("open_heat"), float(state.get("heat_cap", cap))
    except Exception:
        return None, cap


@api_v1.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    tl = TradeLog()
    all_raw = tl.get_trades(status=None, limit=None, sort_by="opened_at") or []
    open_trades = [t for t in all_raw if t.get("status") == "open"]

    stats = tl.get_stats(trades=all_raw)
    stats.update(tl.get_extended_stats(trades=all_raw))

    account_cfg = dash.load_account_config()
    views = dash.build_open_trade_views(open_trades, account_cfg)
    pcts = views["unrealized_pcts"]

    confidences = [
        t["confidence_level"] for t in open_trades
        if t.get("confidence_level") is not None
    ]
    heat, cap = _risk_used()

    return jsonify({
        # primary
        "account_balance": account_cfg.get("balance"),
        "open_pnl_pct": round(sum(pcts) / len(pcts), 2) if pcts else None,
        "risk_used_pct": heat,
        "risk_cap_pct": cap,
        # chips
        "open_trades": len(open_trades),
        "avg_confidence": (
            round(sum(confidences) / len(confidences), 2) if confidences else None
        ),
        "win_rate": stats.get("win_rate"),
        "expectancy_r": stats.get("expectancy_r"),
        "equity_30d": _equity_30d(),
        "position_premium": dash.build_sizing_note(account_cfg),
    })
