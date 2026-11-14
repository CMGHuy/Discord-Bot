"""v208 benchmark bars for the Analytics Benchmark tab.

Skip both fetches while a scan runs or when there is no equity sample.

After the close, rewrite adjusted history since the earliest equity sample.
The stored benchmark_refresh date is the once-per-session-day guard.

During regular trading, refresh the provisional row every five minutes.
The two process-memory throttles only space out retries.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo, benchmark_refresh_repo
from swingbot.core.db.repositories.equity_samples import equity_samples_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session
from swingbot.core.marketdata import benchmarks as mb
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker

if TYPE_CHECKING:
    from swingbot.refresher.loop import CycleContext

log = logging.getLogger(__name__)

INTRADAY_EVERY_S = 300
FULL_RETRY_S = 900
_FETCH_LEAD = timedelta(days=10)  # The bar before the first session supplies its day return.

_last_intraday: datetime | None = None
_last_try: dict[str, datetime] = {}


def benchmarks_step(ctx: CycleContext) -> None:
    try:
        _run(ctx)
    except Exception as exc:  # noqa: BLE001 - a missed benchmark write never fails the cycle
        swallowed(log, "ops.refresher.benchmarks", exc, "benchmarks step failed: %s", exc,
                  level=logging.WARNING)


def _run(ctx: CycleContext) -> None:
    if ctx.scan_running:
        return
    since = live_since()
    if since is None:
        return
    with router.asker_scope(Asker.ADMIN_REFRESH):
        _full_refresh(ctx.now, since)
        if ctx.session == session.SESSION_REGULAR:
            _intraday(ctx.now)


def live_since() -> date | None:
    repo = equity_samples_repo()
    earliest = min((at for source in ("live", "backfill")
                    if (at := repo.earliest_at(source)) is not None), default=None)
    return earliest.astimezone(session.US_MARKET_TZ).date() if earliest is not None else None


def last_completed_session(now: datetime) -> date:
    return session.last_regular_close(now).astimezone(session.US_MARKET_TZ).date()


def _full_refresh(now: datetime, since: date) -> None:
    last = last_completed_session(now)
    if last < since:
        return
    sessions = session.nyse_calendar().sessions(since, last)
    for symbol in mb.BENCHMARK_SYMBOLS:
        if not _full_due(symbol, last, now):
            continue
        try:
            _refresh_symbol(symbol, since, sessions, last, now)
        except Exception as exc:  # noqa: BLE001 - keep refreshing the other benchmarks
            swallowed(log, "ops.refresher.benchmarks", exc,
                      "benchmarks step failed for %s: %s", symbol, exc, level=logging.WARNING)


def _full_due(symbol: str, last: date, now: datetime) -> bool:
    refreshed = benchmark_refresh_repo().full_refreshed_on(symbol)
    if refreshed is not None and refreshed >= last:
        return False
    tried = _last_try.get(symbol)
    return tried is None or (now - tried).total_seconds() >= FULL_RETRY_S


def _refresh_symbol(symbol: str, since: date, sessions: list[date], last: date,
                    now: datetime) -> None:
    _last_try[symbol] = now
    rows = mb.history_with_fallback(symbol, since - _FETCH_LEAD, sessions=sessions,
                                    final_through=last, now=now)
    if rows:
        benchmark_bars_repo().upsert_bars(rows)
    if any(row["session"] == last for row in rows):
        benchmark_refresh_repo().mark_full_refresh(symbol, last)


def _new_intraday_rows(previous: dict, current: dict, prices: dict, today: date, now: datetime) -> list[dict]:
    rows = []
    for symbol, quote in prices.items():
        row = mb.intraday_row(symbol, previous.get(symbol), quote.price, today, now, observed_at=quote.trade_at)
        old = current.get(symbol)
        if row is not None and (old is None or (not old["final"] and old["as_of"] < row["as_of"])):
            rows.append(row)
    return rows


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _intraday(now: datetime) -> None:
    global _last_intraday
    if _last_intraday is not None and (now - _last_intraday).total_seconds() < INTRADAY_EVERY_S:
        return
    today = session.market_today(now)
    if not session.nyse_calendar().is_session(today):
        return
    _last_intraday = now
    last = last_completed_session(now)
    symbols = mb.BENCHMARK_SYMBOLS
    repo = benchmark_bars_repo()
    stored = repo.list_range(symbols, last, today)
    previous = {row["symbol"]: row for row in stored if row["session"] == last}
    current = {row["symbol"]: row for row in stored if row["session"] == today}
    prices = mb.latest_benchmark_prices(symbols)
    rows = _new_intraday_rows(previous, current, prices, today, max(now, _now()))
    if rows:
        repo.upsert_bars(rows)


def reset_state() -> None:
    global _last_intraday
    _last_intraday = None
    _last_try.clear()
