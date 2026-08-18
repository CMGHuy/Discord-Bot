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
definition of win rate here would drift from the projected one.

The equity sparkline ships as NUMBERS, via `_equity_30d()` below. Jinja's
equivalent builder returned a rendered `<svg>` string and was deleted with
it: the SPA owns how a sparkline looks, and a server that ships markup has
taken that decision away from it.
"""
from __future__ import annotations

from flask import jsonify, request

from swingbot import config
from swingbot.admin import dashboard as dash
from swingbot.core.planning.plan_engine import DEFAULT_EXPIRY_BARS
from swingbot.core.tracking.performance import TradeLog

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


def _lifecycle_counts(mode: str) -> dict:
    """The five plan-lifecycle counts the Jinja dashboard's strip showed.

    SR53. PENDING/ACTIVE/PARTIAL are all-time -- `_plan_rows` already counts
    them that way, so those three are projected from it unchanged.

    CLOSED/CANCELLED are NOT projected from `_plan_rows`: that function counts
    PLANS only, by `status_history`'s own timestamp, which is two different
    things from what the Dashboard's own Closed table (and the Trades
    collection behind it, `trades.build_rows`) shows -- a plan-only count
    misses legacy trades that never had a plan at all, and a `status_history`
    timestamp is a different clock than the trade's own `closed_at`
    (`trades._terminal_at`). Both gaps make the strip's number disagree with
    what clicking through to the table actually lists. So CLOSED/CANCELLED
    are counted from `build_rows()` instead -- the exact same rows and the
    exact same `today` flag the Closed table's own query uses -- which makes
    the two structurally unable to disagree. `mode` selects between them the
    same way `today` is bound in trade-group.ts: 'all' counts every close
    ever, anything else counts only today's.

    Returns an empty dict on failure rather than raising: this is the landing
    page, and one degraded panel is better than a 500 for the other nine
    figures.
    """
    try:
        from swingbot.admin.queries import _plan_rows
        from .trades import build_rows

        counts = dict(_plan_rows()["counts"])
        rows = build_rows()
        for status in ("CLOSED", "CANCELLED"):
            matching = [r for r in rows if r["status"] == status]
            if mode != "all":
                matching = [r for r in matching if r["today"]]
            counts[status] = len(matching)
        return counts
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
        "lifecycle": _lifecycle_counts(mode),
        # The Dashboard's own plan-lifecycle diagram names this number in its
        # "Expires" definition -- projected here rather than hardcoded a
        # second time in the SPA, which is exactly the kind of copy that
        # drifts silently the moment DEFAULT_EXPIRY_BARS changes. A PLAN's
        # own `expiry_bars` can differ from this (plans.py/embeds.py already
        # show the per-plan number where one exists); this is only the
        # default new plans get built with, for a definition that has no
        # one plan to read it from.
        "default_expiry_bars": DEFAULT_EXPIRY_BARS,
        # SR58 -- the date scope, echoed back so the workspace can label the
        # figures it is showing rather than assume the request applied.
        "scope": {"mode": mode},
        "realized": _realized(
            [t for t in all_raw if t.get("status") in ("win", "loss", "closed")],
            mode,
        ),
    })
