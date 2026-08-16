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

import yfinance as yf

from swingbot.core.marketdata.ticker_utils import candidate_symbols
from swingbot.core.marketdata.universe import is_etf

log = logging.getLogger("swing-bot.events")


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
    """
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
