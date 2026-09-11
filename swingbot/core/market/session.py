"""US regular-trading-hours calendar for the live plan manager."""
from __future__ import annotations

import datetime as dt
import bisect
import functools
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from swingbot import config

US_MARKET_TZ = ZoneInfo("America/New_York")
# The operator's clock: the scan session window, the dashboard's "today", the
# daily retrospective and the account's day boundary all read it. Defined once
# so no two surfaces can disagree about when a day starts.
BERLIN_TZ = ZoneInfo("Europe/Berlin")

# The open is inclusive and the close is exclusive.
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def now_et(now: dt.datetime | None = None) -> dt.datetime:
    """Return ``now`` (or the current moment) as an aware ET datetime."""
    if now is None:
        return dt.datetime.now(US_MARKET_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=US_MARKET_TZ)
    return now.astimezone(US_MARKET_TZ)


def is_regular_session(now: dt.datetime | None = None) -> bool:
    """Return whether ``now`` falls in Mon-Fri 09:30 <= t < 16:00 ET."""
    et = now_et(now)
    if et.weekday() >= 5:
        return False
    return RTH_OPEN <= et.time() < RTH_CLOSE


def is_quiet_hours(now: dt.datetime | None = None) -> bool:
    """Return whether ``now`` falls in the overnight window the v70
    extended-hours exit check never runs in: ``config.QUIET_HOURS_START_ET``
    through ``config.QUIET_HOURS_END_ET`` ET, plus every hour of Saturday
    and Sunday -- a market that is fully shut all weekend.

    The bounds are read from ``config`` rather than passed in, the same way
    ``plan_manager`` already reads ``config.INTRADAY_RTH_ONLY`` directly.
    The window always runs START -> midnight -> END, so a START earlier than
    END (e.g. 8 and 23) means "quiet all day" and switches plan monitoring
    off entirely. That is the honest reading of an inverted window, not a
    bug to special-case.
    """
    et = now_et(now)
    if et.weekday() >= 5:
        return True
    start = dt.time(config.QUIET_HOURS_START_ET, 0)
    end = dt.time(config.QUIET_HOURS_END_ET, 0)
    t = et.time()
    return t >= start or t < end


def session_date(now: dt.datetime | None = None) -> str:
    """Return the ET calendar date used to stamp a plan."""
    return now_et(now).date().isoformat()


#: NYSE full-day closures from 2018 through 2030.  Weekend holidays are
#: represented by their observed weekday (except Saturday New Year's Day,
#: which NYSE does not observe).  Keep this in agreement with opex's subset.
NYSE_HOLIDAYS: frozenset[dt.date] = frozenset(dt.date.fromisoformat(d) for d in (
    "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28", "2018-07-04", "2018-09-03", "2018-11-22", "2018-12-05", "2018-12-25",
    "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27", "2019-07-04", "2019-09-02", "2019-11-28", "2019-12-25",
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25", "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25",
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20", "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29", "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19", "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
    "2029-01-01", "2029-01-15", "2029-02-19", "2029-03-30", "2029-05-28", "2029-06-19", "2029-07-04", "2029-09-03", "2029-11-22", "2029-12-25",
    "2030-01-01", "2030-01-21", "2030-02-18", "2030-04-19", "2030-05-27", "2030-06-19", "2030-07-04", "2030-09-02", "2030-11-28", "2030-12-25",
))
NYSE_FIRST_DATE = dt.date(2018, 1, 1)
NYSE_LAST_YEAR_COVERED = 2030


class SessionCalendar:
    """An ordered run of trading sessions."""

    def __init__(self, sessions: Iterable[dt.date]):
        self._sessions = tuple(sorted(set(sessions)))
        if not self._sessions:
            raise ValueError("SessionCalendar needs at least one session")

    @classmethod
    def from_bar_index(cls, index) -> "SessionCalendar":
        import pandas as pd
        return cls(ts.date() for ts in pd.DatetimeIndex(index))

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def first(self) -> dt.date:
        return self._sessions[0]

    @property
    def last(self) -> dt.date:
        return self._sessions[-1]

    def sessions(self, start: dt.date, end: dt.date) -> list[dt.date]:
        return list(self._sessions[bisect.bisect_left(self._sessions, start):bisect.bisect_right(self._sessions, end)])

    def is_session(self, d: dt.date) -> bool:
        i = bisect.bisect_left(self._sessions, d)
        return i < len(self._sessions) and self._sessions[i] == d

    def position_on_or_after(self, d: dt.date) -> int | None:
        i = bisect.bisect_left(self._sessions, d)
        return i if i < len(self._sessions) else None

    def position_on_or_before(self, d: dt.date) -> int | None:
        i = bisect.bisect_right(self._sessions, d) - 1
        return i if i >= 0 else None

    def session_on_or_after(self, d: dt.date) -> dt.date | None:
        i = self.position_on_or_after(d)
        return None if i is None else self._sessions[i]

    def next_session(self, d: dt.date) -> dt.date | None:
        i = bisect.bisect_right(self._sessions, d)
        return self._sessions[i] if i < len(self._sessions) else None

    def sessions_between(self, asof: dt.date, target: dt.date) -> int | None:
        a, b = self.position_on_or_before(asof), self.position_on_or_after(target)
        return None if a is None or b is None else b - a


@functools.lru_cache(maxsize=1)
def nyse_calendar() -> SessionCalendar:
    """Every NYSE session covered by the frozen holiday table."""
    day, end = NYSE_FIRST_DATE, dt.date(NYSE_LAST_YEAR_COVERED, 12, 31)
    sessions = []
    while day <= end:
        if day.weekday() < 5 and day not in NYSE_HOLIDAYS:
            sessions.append(day)
        day += dt.timedelta(days=1)
    return SessionCalendar(sessions)
