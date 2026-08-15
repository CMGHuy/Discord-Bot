"""
Tracks broad, market-wide scheduled events that can move EVERY ticker at
once -- as distinct from events.py, which tracks a single ticker's own
earnings date. A swing trade can get blown through its stop-loss or
take-profit by a Fed decision or a jobs report just as easily as by that
specific company's earnings, so both get surfaced.

Sources of dates:
  - FOMC rate decisions: hardcoded from the Federal Reserve's own
    published calendar (confirmed for 2026, tentative "preview" schedule
    for 2027 -- the Fed publishes next year's dates roughly a year out).
    These need a yearly bump once new schedules are published.
  - US jobs report (Non-Farm Payrolls): always the first Friday of the
    month, a fixed BLS rule, so this is computed rather than hardcoded.
  - US CPI (inflation) release: the BLS doesn't fix this to a weekday
    rule, so this is an APPROXIMATE mid-month placeholder (flagged as
    such) rather than an exact date -- good enough to flag "inflation
    print risk in this window", not precise enough to trade the exact day.

Best-effort, like events.py: if something here goes stale (e.g. next
year's FOMC schedule isn't in the list yet) it just won't be flagged --
it never blocks a trade recommendation.
"""
import calendar
import datetime as dt
from dataclasses import dataclass

# FOMC decision dates = the SECOND day of each 2-day meeting, when the
# rate decision + press conference happen. Source: federalreserve.gov.
FOMC_DECISION_DATES = [
    # 2026 -- confirmed
    dt.date(2026, 1, 28), dt.date(2026, 3, 18), dt.date(2026, 4, 29),
    dt.date(2026, 6, 17), dt.date(2026, 7, 29), dt.date(2026, 9, 16),
    dt.date(2026, 10, 28), dt.date(2026, 12, 9),
    # 2027 -- tentative preview schedule, re-confirm when published
    dt.date(2027, 1, 27), dt.date(2027, 3, 17), dt.date(2027, 4, 28),
    dt.date(2027, 6, 9), dt.date(2027, 7, 28), dt.date(2027, 9, 15),
    dt.date(2027, 10, 27), dt.date(2027, 12, 8),
]


@dataclass
class MarketEvent:
    name: str
    date: dt.date
    days_away: int
    approximate: bool = False


def _first_friday(year: int, month: int) -> dt.date:
    cal = calendar.Calendar()
    for day in cal.itermonthdates(year, month):
        if day.month == month and day.weekday() == calendar.FRIDAY:
            return day
    raise ValueError("no Friday found")  # unreachable


def _next_n_month_starts(from_date: dt.date, n: int):
    year, month = from_date.year, from_date.month
    for _ in range(n):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _upcoming_nfp_dates(today: dt.date, months_ahead: int = 3) -> list[dt.date]:
    dates = []
    for year, month in _next_n_month_starts(today, months_ahead):
        d = _first_friday(year, month)
        if d >= today:
            dates.append(d)
    return dates


def _upcoming_cpi_dates(today: dt.date, months_ahead: int = 3) -> list[dt.date]:
    # BLS CPI releases historically land around the 10th-13th; the 12th is
    # used as an approximate midpoint. Flagged as approximate everywhere
    # it's surfaced -- treat this as "inflation-print risk this week", not
    # a specific tradeable date.
    dates = []
    for year, month in _next_n_month_starts(today, months_ahead):
        d = dt.date(year, month, 12)
        if d >= today:
            dates.append(d)
    return dates


def get_market_events(max_days_ahead: int, today: dt.date = None) -> list[MarketEvent]:
    """
    Returns every known/approximate macro event (FOMC, NFP, CPI) that
    falls within the next `max_days_ahead` calendar days, soonest first.
    """
    today = today or dt.date.today()
    events = []

    for d in FOMC_DECISION_DATES:
        days_away = (d - today).days
        if 0 <= days_away <= max_days_ahead:
            events.append(MarketEvent("FOMC rate decision", d, days_away, approximate=False))

    for d in _upcoming_nfp_dates(today):
        days_away = (d - today).days
        if 0 <= days_away <= max_days_ahead:
            events.append(MarketEvent("US jobs report (NFP)", d, days_away, approximate=False))

    for d in _upcoming_cpi_dates(today):
        days_away = (d - today).days
        if 0 <= days_away <= max_days_ahead:
            events.append(MarketEvent("US CPI release", d, days_away, approximate=True))

    events.sort(key=lambda e: e.date)
    return events
