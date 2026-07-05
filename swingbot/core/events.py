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

from .ticker_utils import candidate_symbols

log = logging.getLogger("swing-bot.events")


def get_next_earnings_date(ticker: str) -> dt.date | None:
    """Returns the next known earnings date for a ticker, or None if unavailable."""
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
