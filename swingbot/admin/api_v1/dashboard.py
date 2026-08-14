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

from flask import jsonify, request

from swingbot import config
from swingbot.admin import dashboard as dash
from swingbot.core.performance import TradeLog

from . import ApiError, api_v1
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


def _lifecycle_counts() -> dict:
    """The five plan-lifecycle counts the Jinja dashboard's strip showed.

    SR53. PENDING/ACTIVE/PARTIAL are all-time; CLOSED/CANCELLED count only
    today's, because a lifetime CLOSED count is a number that only ever goes up
    and says nothing about the session. `_plan_rows` already applies exactly
    that scoping for the Jinja strip, so this projects its counts rather than
    recomputing them -- the module's own "nothing is computed here" rule.

    Returns an empty dict on failure rather than raising: this is the landing
    page, and one degraded panel is better than a 500 for the other nine
    figures.
    """
    try:
        from swingbot.admin.pages import _plan_rows
        return dict(_plan_rows()["counts"])
    except Exception:
        return {}


_SCOPES = ("active", "today", "all")


def _scope() -> str:
    """SR58 -- the dashboard's date scope, from `?mode=`.

    The Jinja dashboard's three modes: `active` (today plus anything still
    open, the default), `today`, and `all`. An unknown value is a 400 rather
    than a silent fall back to the default -- a scope that quietly ignores
    what was asked for makes all-time numbers read as today's, which is the
    same class of bug SR52 fixed on the Trades list.
    """
    raw = (request.args.get("mode") or "").strip() or "active"
    if raw not in _SCOPES:
        raise ApiError("invalid", f"mode must be one of {', '.join(_SCOPES)}", 400)
    return raw


def _realized(closed: list[dict], mode: str) -> dict:
    """Realised P&L over the scoped closes.

    **`active` and `today` are identical here, deliberately.** The only thing
    separating those two modes is whether still-open positions are included,
    and an open position has no realised P&L to contribute. `2026-08-07-v9`
    made the same call for Trade History; asserting it in a test stops a
    later change inventing a difference.

    Amounts are `None` rather than `0.0` when nothing closed: "nothing closed
    today" and "closed exactly flat" are different facts and a card must not
    render them identically.
    """
    if mode != "all":
        closed = [t for t in closed if dash.is_today_berlin(t.get("closed_at"))]

    amounts = [a for a in (t.get("realized_pnl_amount") for t in closed)
               if isinstance(a, (int, float))]
    pcts = [p for p in (dash.closed_pnl(t) for t in closed) if p is not None]

    return {
        "amount": round(sum(amounts), 2) if amounts else None,
        "pct": round(sum(pcts) / len(pcts), 2) if pcts else None,
        "n": len(closed),
        "wins": sum(1 for t in closed if t.get("status") == "win"),
        "losses": sum(1 for t in closed if t.get("status") == "loss"),
    }


@api_v1.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    mode = _scope()
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
        "lifecycle": _lifecycle_counts(),
        # SR58 -- the date scope, echoed back so the workspace can label the
        # figures it is showing rather than assume the request applied.
        "scope": {"mode": mode},
        "realized": _realized(
            [t for t in all_raw if t.get("status") in ("win", "loss", "closed")],
            mode,
        ),
    })
