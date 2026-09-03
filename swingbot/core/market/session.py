"""US regular-trading-hours calendar for the live plan manager."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from swingbot import config

US_MARKET_TZ = ZoneInfo("America/New_York")

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