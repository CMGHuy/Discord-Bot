"""GET /api/v1/calendar/* -- the day-level P&L calendar surface.

Spec: `docs/superpowers/specs/2026-08-22-v53-pnl-calendar-design.md`.

**"UI renders, analytics computes."** Every figure here is computed by
`swingbot.core.analytics.pnl_calendar`; these routes select, scope and
forward. That is the same rule `analytics.py` states, and the reason this
module holds no arithmetic.

`TradeLog` / `JournalStore` are constructed inside the view, never at import
time -- see `tests/admin/conftest.py:34-47`. An api_v1 module that binds a
`config.DATA_DIR` path at import would read the real project's `data/`
directory throughout the test suite.
"""
from __future__ import annotations

import datetime as dt

from flask import jsonify, request

from . import ApiError, api_v1
from .auth import require_auth

# `month` is handled separately from the filters: it scopes the grid rather
# than narrowing the population, and it has its own format.
_FILTERS = frozenset({"month", "strategy", "horizon", "date"})


def _reject_unknown_params() -> None:
    """A query parameter nobody declared is a 400, never an ignored filter.

    Same reasoning as `parse_collection_params`: a silently dropped filter
    is how a filter that has stopped working survives to production -- the
    caller sees results, just not the ones it asked for.
    """
    unknown = sorted(set(request.args) - _FILTERS)
    if unknown:
        raise ApiError(
            "invalid",
            f"unknown parameter {unknown[0]!r}; allowed: {sorted(_FILTERS)}",
            400,
        )


def _month_param() -> str:
    """The `?month=YYYY-MM` scope, defaulting to the current month.

    A malformed value is a 400 rather than a silent fallback to all-time --
    the same trap `_iso_day` in `analytics.py` guards, where accepting
    `?from=last-tuesday` would hand a user all-time numbers to read as this
    month's.
    """
    raw = (request.args.get("month") or "").strip()
    if not raw:
        return dt.date.today().strftime("%Y-%m")
    try:
        dt.datetime.strptime(raw, "%Y-%m")
    except ValueError:
        raise ApiError("invalid", "month must be a YYYY-MM value", 400)
    return raw


def _filter_args() -> tuple[str | None, str | None]:
    strategy = (request.args.get("strategy") or "").strip() or None
    horizon = (request.args.get("horizon") or "").strip() or None
    return strategy, horizon


@api_v1.route("/calendar/pnl", methods=["GET"])
@require_auth
def calendar_pnl():
    """One month's day grid, plus the full-history context beside it.

    **Two different scopes in one payload, deliberately.** `days` and
    `totals` are the requested month; `day_of_week`, `best_day`,
    `worst_day` and `streak` are ALL of history under the same
    strategy/horizon filter. A weekday pattern drawn from one month is 4-5
    observations per weekday and would be noise presented as a finding.
    """
    from swingbot.core.analytics import pnl_calendar as pc

    _reject_unknown_params()
    month = _month_param()
    strategy, horizon = _filter_args()

    everything = pc.load_rows()
    rows = pc.filter_rows(everything, strategy=strategy, horizon=horizon)
    grid = pc.month_grid(rows, month)
    extremes = pc.best_worst_days(rows)

    return jsonify({
        "month": grid["month"],
        "days": grid["days"],
        "totals": grid["totals"],
        "day_of_week": pc.day_of_week_breakdown(rows),
        "best_day": extremes["best"],
        "worst_day": extremes["worst"],
        "streak": pc.day_streak(rows),
        # Derived from the UNFILTERED set -- see `available_filters`.
        "filters": pc.available_filters(everything),
    })
