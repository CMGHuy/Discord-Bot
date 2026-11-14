"""v208: the Benchmark tab's one read, with account-wide equity and daily paging.

Every figure comes from core.analytics.benchmark_view; this module only loads
and pages. Equity is account-wide, so there is no BookScope.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from flask import jsonify, request

from swingbot.core.analytics.benchmark_view import BenchmarkInputs, build_benchmark
from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo
from swingbot.core.db.repositories.equity_samples import equity_samples_repo
from swingbot.core.market import session
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.benchmarks import BENCHMARK_SYMBOLS
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.core.tracking import equity
from swingbot.refresher.benchmarks import live_since

from . import ApiError, api_v1
from .analytics import _iso_day
from .auth import require_auth
from .equity import _choice, _limit

ALLOWED_PARAMS = ("from", "to", "capture", "limit", "before")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def _reject_unknown() -> None:
    unknown = sorted(set(request.args) - set(ALLOWED_PARAMS))
    if unknown:
        raise ApiError("invalid", f"unknown parameter '{unknown[0]}'; allowed: {list(ALLOWED_PARAMS)}", 400)


def _day(name: str) -> date | None:
    raw = _iso_day(name)
    return date.fromisoformat(raw) if raw else None


def _mixed_tickers(trades: list[dict], since: date) -> list[str]:
    tickers = {str(trade.get("ticker", "")).upper() for trade in equity.main_book(trades)
               if trade.get("status") == "open"
               or (trade.get("closed_at") or "")[:10] >= since.isoformat()}
    return sorted(ticker for ticker in tickers
                  if fx.quote_currency_code(ticker, fetch=False) != "USD")


def _load_inputs(now: datetime, start: date | None = None) -> BenchmarkInputs:
    today = session.market_today(now)
    first = live_since() or today
    trades = _trades()
    return BenchmarkInputs(
        rows=equity_samples_repo().list_rows(),
        legs=equity.realized_legs(trades),
        bars=benchmark_bars_repo().list_range(BENCHMARK_SYMBOLS, first, today),
        sessions=session.nyse_calendar().sessions(first, today),
        now=now,
        account_currency=fx.account_currency_code(),
        mixed_tickers=_mixed_tickers(trades, start or first),
        refresher_on=admin_refresh.refresher_on(),
    )


def _page_daily(daily: list[dict], before: date | None, limit: int) -> tuple[list[dict], bool]:
    rows = daily if before is None else [row for row in daily if row["date"] < before.isoformat()]
    return rows[:limit], len(rows) > limit


@api_v1.route("/analytics/benchmark", methods=["GET"])
@require_auth
def analytics_benchmark():
    _reject_unknown()
    start, end, before = _day("from"), _day("to"), _day("before")
    if start and end and start > end:
        raise ApiError("invalid", "from must be on or before to", 400)
    capture = _choice("capture", BENCHMARK_SYMBOLS, "SPY")
    limit = _limit()
    body = build_benchmark(_load_inputs(_now(), start), start=start, end=end, capture=capture)
    body["daily"], body["daily_has_more"] = _page_daily(body["daily"], before, limit)
    return jsonify(body)
