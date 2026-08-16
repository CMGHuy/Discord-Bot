"""
Checks for a known scheduled event -- currently just earnings dates --
that could affect a trade within its intended holding window. This is
what "events happening with the stock" means here: a concrete, fetchable
date, not sentiment analysis of news text.

Best-effort: if Yahoo doesn't have the data (delisted, no analyst
coverage, temporary API hiccup), this silently returns None rather than
blocking a trade recommendation. An earnings date is a real risk factor
for a swing trade -- surprises in either direction can blow through both
the stop-loss and the take-profit overnight -- so when one falls inside
the holding window, the bot flags it rather than pretending it isn't there.
"""
import datetime as dt
import logging
import threading
import time

import yfinance as yf

from swingbot.core.marketdata.ticker_utils import candidate_symbols
from swingbot.core.marketdata.universe import is_etf

log = logging.getLogger("swing-bot.events")

# An earnings date is essentially static for weeks at a time -- nothing like
# get_current_price's 15s TTL is warranted, and the cost of NOT caching this
# is severe: GET /watchlist/tickers calls get_next_earnings_datetime once per
# watchlist ticker on every page load, uncached, and each call is a live
# Yahoo round trip with no local-data fallback (unlike company-name lookups,
# which resolve most US symbols from a local directory). Measured on a
# ~34-ticker watchlist: 23 seconds per load before this cache existed --
# severe enough to read as "the page shows nothing" rather than "slow".
# Same in-memory {ticker: (value, fetched_at)} shape as _price_cache in
# marketdata/data.py, just a much longer TTL.
_EARNINGS_DATETIME_CACHE_TTL_SECONDS = 6 * 60 * 60
_earnings_datetime_cache: dict[str, tuple[dt.datetime | None, float]] = {}

#: Distinguishes "checked Yahoo, confirmed nothing" (a real cached `None`)
#: from "never checked, or the entry expired" -- callers that must not
#: block (the watchlist endpoint) need to tell those apart.
_NOT_CACHED = object()


def get_next_earnings_date(ticker: str) -> dt.date | None:
    """Returns the next known earnings date for a ticker, or None if unavailable."""
    if is_etf(ticker):
        return None  # funds don't report earnings; never gate or fetch

    for candidate in candidate_symbols(ticker):
        try:
            calendar = yf.Ticker(candidate).calendar
        except Exception as e:
            log.debug("Calendar fetch failed for %s: %s", candidate, e)
            continue

        if not calendar:
            continue
        dates = calendar.get("Earnings Date")
        if not dates:
            continue

        today = dt.date.today()
        upcoming = [d for d in dates if isinstance(d, dt.date) and d >= today]
        if upcoming:
            return min(upcoming)

    return None


def get_next_earnings_datetime(ticker: str) -> dt.datetime | None:
    """Like `get_next_earnings_date`, but with a time-of-day and timezone
    attached when Yahoo has one.

    `Ticker.calendar["Earnings Date"]` (what `get_next_earnings_date` reads)
    is a plain date list with no time. `Ticker.get_earnings_dates()` is a
    separate yfinance call that returns a real, per-company,
    `America/New_York`-zoned timestamp -- confirmed empirically: AAPL/MSFT/
    NVDA consistently report after close (16:00 ET) while JPM/WMT
    consistently report before open (06:00-08:00 ET), correctly shifting
    across the EST/EDT boundary. Admin-display use only (the Watchlist
    Earnings calendar) -- kept independent of `get_next_earnings_date`
    rather than sharing an implementation, because that function backs the
    earnings-blackout gate, a trading-safety check with its own tests, and
    this path must never be able to shift its behaviour.

    For a future date, Yahoo has not necessarily confirmed the exact time
    (some companies announce it only weeks ahead) -- treat every returned
    value as an estimate, never as confirmed.

    Cached in-memory per ticker for `_EARNINGS_DATETIME_CACHE_TTL_SECONDS`
    (6h) -- see that constant's comment for why this one needs a cache at
    all where `get_next_earnings_date` (below) has gone without one.
    """
    ticker_key = ticker.upper().strip()
    cached = _earnings_datetime_cache.get(ticker_key)
    now_monotonic = time.monotonic()
    if cached and (now_monotonic - cached[1]) < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return cached[0]

    result = _fetch_next_earnings_datetime(ticker_key)
    _earnings_datetime_cache[ticker_key] = (result, now_monotonic)
    return result


def peek_cached_earnings_datetime(ticker: str):
    """Read-only: the cached value if fresh, or `_NOT_CACHED` -- never
    fetches, never blocks.

    For a caller that must answer instantly (the watchlist endpoint) and
    would rather show "unknown for now" than make a request wait on a live
    Yahoo call. Pair with `warm_earnings_cache_background` to fill the gap
    for next time without making THIS request pay for it.
    """
    ticker_key = ticker.upper().strip()
    cached = _earnings_datetime_cache.get(ticker_key)
    if cached and (time.monotonic() - cached[1]) < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return cached[0]
    return _NOT_CACHED


def warm_earnings_cache_background(tickers: list[str]) -> threading.Thread:
    """Fire-and-forget: populate the cache for `tickers` on a daemon thread.

    Same shape as `marketdata.backtest_cache.ensure_cached_background` --
    the caller gets an immediate return and the next request (or the next
    poll of the same page) sees the warmed cache instead of paying for it.
    Sequential within the thread rather than its own pool: this already
    runs off the request thread, so there is no response latency to
    protect, and stacking a second pool under a pool the caller may already
    be running (`_next_earnings`'s `ThreadPoolExecutor`) buys nothing.
    """
    def _run():
        for ticker in tickers:
            try:
                get_next_earnings_datetime(ticker)
            except Exception:
                log.debug("background earnings warm-up failed for %s", ticker, exc_info=True)

    t = threading.Thread(target=_run, name="earnings-cache-warm", daemon=True)
    t.start()
    return t


def _fetch_next_earnings_datetime(ticker: str) -> dt.datetime | None:
    if is_etf(ticker):
        return None

    for candidate in candidate_symbols(ticker):
        try:
            earnings = yf.Ticker(candidate).get_earnings_dates(limit=6)
        except Exception as e:
            log.debug("Earnings-dates fetch failed for %s: %s", candidate, e)
            continue
        if earnings is None or earnings.empty:
            continue

        now = dt.datetime.now(dt.timezone.utc)
        upcoming = [ts for ts in earnings.index if ts.to_pydatetime() >= now]
        if upcoming:
            return min(upcoming).to_pydatetime()

    return None


def earnings_within_window(ticker: str, max_holding_days: int):
    """
    Returns (earnings_date, days_away) if the next known earnings date
    falls within the next `max_holding_days` calendar days, else None.
    """
    next_date = get_next_earnings_date(ticker)
    if next_date is None:
        return None

    days_away = (next_date - dt.date.today()).days
    if 0 <= days_away <= max_holding_days:
        return next_date, days_away
    return None
