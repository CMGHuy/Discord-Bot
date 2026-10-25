"""GET /api/v1/cancel-precision -- v188 cancelled-plan precision.

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
"UI renders, analytics computes": every figure comes from
`swingbot.core.analytics.cancel_precision`; this route loads, memoises and
forwards. Bars come from `market_data/` through `daily_delta.read_daily`, which
follows the scan's Alpaca/yfinance basis routing and is kept fresh by the
bot's MARKET_DATA_AUTO_REFRESH; `data/backtest_cache/` is never read (nothing
refreshes it on the VM). Cost per recompute: one PlanStore scan, one
process-cached frame per ticker, the week bootstraps. The memo recomputes at
most hourly or on any plan write. Runs only in the admin process; a failure
is a 500 on this one screen.
"""
from __future__ import annotations

import datetime as dt

from flask import jsonify, request

from . import ApiError, api_v1
from .auth import require_auth

_MEMO: dict = {}


def _load_plans() -> list[dict]:
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().records()


def _bar_loader(ticker: str):
    from swingbot.core.marketdata import daily_delta, spot_metals
    if spot_metals.is_spot_metal(ticker):
        return None
    return daily_delta.read_daily(ticker)


def _memo_key() -> tuple:
    from swingbot.core.db.repositories.plans import plans_repo
    hour = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")
    return (plans_repo().version(), hour)


def reset_memo() -> None:
    _MEMO.clear()


@api_v1.route("/cancel-precision", methods=["GET"])
@require_auth
def cancel_precision():
    if request.args:
        raise ApiError("invalid",
                       f"unknown parameter {sorted(request.args)[0]!r}; this route takes none",
                       400)
    from swingbot.core.analytics.cancel_precision import precision_payload
    key = _memo_key()
    if key not in _MEMO:
        payload = precision_payload(
            _load_plans(), _bar_loader,
            generated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        _MEMO.clear()
        _MEMO[key] = payload
    return jsonify(_MEMO[key])
