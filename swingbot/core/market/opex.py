"""Options-expiration ("opex") calendar and the caution policy built on it.

WHY A MODULE AND NOT A CONTEXT COLUMN
-------------------------------------
`market_context` exists to align an EXTERNAL series -- SPY-derived regime --
onto a ticker's index without leaking tomorrow's value into today's bar; its
module docstring argues that at length. Opex has no external series. The tier
is a pure function of the bar's own date, so there is nothing to align and no
lookahead to guard against, and the machinery would buy nothing.

It would also cost something real. `market_context.get()` returns None
whenever `REGIME_GATES_ENABLED` is off, so putting `ctx_opex_tier` in
CTX_COLUMNS would wire this feature's on/off switch to an unrelated flag --
turning regime gating off would silently stop opex caution too, with nothing
anywhere saying so.

WHY US/EASTERN AND NOT SESSION_TZ
---------------------------------
The scanning session is Europe/Berlin (`bot_core.SESSION_TZ`), but an
expiration is a US-market event. Berlin runs six hours ahead of New York, so
the two calendars only agree during 15:30-22:00 Berlin. `SESSION_END_HOUR`
defaults to 23, which puts the tail of every session in the gap where the
Berlin date has already rolled over and the New York date has not.

The same reasoning fixes the near-close anchor at 16:00 America/New_York
rather than SESSION_END_HOUR: 23:00 Berlin is 17:00 ET, an hour after the
US close, so a window measured back from it would sit entirely after the
event it exists to protect against.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

US_MARKET_TZ = ZoneInfo("America/New_York")

#: US equity regular-session close. Half-days (the 13:00 closes around
#: Thanksgiving and Christmas) are deliberately not modelled: none of them is
#: ever a third Friday, and treating one as a full day only makes the
#: suppression window start later than needed on a day that is not an opex
#: day at all.
US_CLOSE_TIME = dt.time(16, 0)

MONTHLY = "monthly"
WEEKLY = "weekly"

#: NYSE full-day closures that land on a **Friday** -- the only ones that can
#: displace an expiration. A Friday holiday does two things: it cancels that
#: week's weekly expiration, and if it was the nominal third Friday it moves
#: the monthly expiration back to the Thursday.
#:
#: Fridays only, on purpose. This is not a general market calendar and must
#: not be used as one; `MAINTENANCE` below says how to extend it.
_FRIDAY_HOLIDAYS: frozenset[dt.date] = frozenset({
    dt.date(2026, 4, 3),     # Good Friday
    dt.date(2026, 6, 19),    # Juneteenth            (also the 3rd Friday)
    dt.date(2026, 7, 3),     # Independence Day observed (4 Jul is a Saturday)
    dt.date(2026, 12, 25),   # Christmas Day
    dt.date(2027, 1, 1),     # New Year's Day
    dt.date(2027, 3, 26),    # Good Friday
    dt.date(2027, 6, 18),    # Juneteenth observed  (19 Jun is a Saturday)
    dt.date(2027, 12, 24),   # Christmas observed   (25 Dec is a Saturday)
    dt.date(2028, 4, 14),    # Good Friday
    dt.date(2029, 3, 30),    # Good Friday
    dt.date(2030, 4, 19),    # Good Friday          (also the 3rd Friday)
})

#: MAINTENANCE: the table above is complete through this year and empty
#: after it, so from 1 Jan of the following year every Friday holiday is
#: silently treated as a normal expiration. Extend it by listing the NYSE
#: full-day closures that fall on a Friday -- in practice Good Friday every
#: year, plus whichever of New Year's Day, Juneteenth, Independence Day and
#: Christmas land on (or are observed on) a Friday.
LAST_YEAR_COVERED = 2030


def _third_friday(year: int, month: int) -> dt.date:
    """The nominal third Friday, before any holiday adjustment."""
    first = dt.date(year, month, 1)
    # weekday(): Monday is 0, Friday is 4.
    first_friday_offset = (4 - first.weekday()) % 7
    return first + dt.timedelta(days=first_friday_offset + 14)


def monthly_expiration(year: int, month: int) -> dt.date:
    """The month's standard equity/index expiration date.

    The third Friday, moved back to the Thursday when that Friday is a
    full-day closure -- the convention US exchanges use.
    """
    nominal = _third_friday(year, month)
    if nominal in _FRIDAY_HOLIDAYS:
        return nominal - dt.timedelta(days=1)
    return nominal


def opex_tier(day: dt.date) -> str | None:
    """Classify one calendar date.

    `MONTHLY` for the month's standard expiration, `WEEKLY` for any other
    Friday the market is open, `None` otherwise. Total: every date has an
    answer, so there is nothing here to raise.

    Quarterly "triple witching" (Mar/Jun/Sep/Dec) is deliberately folded into
    MONTHLY rather than given a third tier -- nothing in the policy layer
    would currently treat it differently.
    """
    if day == monthly_expiration(day.year, day.month):
        return MONTHLY
    if day.weekday() == 4 and day not in _FRIDAY_HOLIDAYS:
        return WEEKLY
    return None
