"""v144: the outlook's calendar.

When it runs (Sunday to Thursday at the configured Berlin slot), which bar it
reads (the last NYSE session on or before the run date, so Sunday reads Friday),
which session it targets (the NEXT CALENDAR DAY, only if that is a session; it
never skips ahead), how late a missed run may still fire (before the target's
RTH open), and when the wrap-up is due (15 minutes after the official close).
Every session boundary is ET from market.session; no Berlin hour is hard-coded.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot.core.market.session import (RTH_OPEN, US_MARKET_TZ, now_et, nyse_calendar,
                                          session_close)

log = logging.getLogger(__name__)

RUN_WEEKDAYS = frozenset({6, 0, 1, 2, 3})      # Sunday .. Thursday (Monday = 0)
DEFAULT_SLOT = dt.time(23, 30)
WRAPUP_DELAY = dt.timedelta(minutes=15)
_LOOKBACK_DAYS = 10


def parse_slot(raw) -> dt.time:
    try:
        hour, minute = (int(part) for part in str(raw).strip().split(":"))
        return dt.time(hour, minute)
    except (TypeError, ValueError):
        log.warning("NEXT_SESSION_SCAN_TIME %r is not HH:MM -- using %s",
                    raw, DEFAULT_SLOT.strftime("%H:%M"))
        return DEFAULT_SLOT


def latest_slot_date(now_berlin: dt.datetime, slot: dt.time) -> dt.date | None:
    """The newest Sunday-Thursday run date whose slot is at or before `now_berlin`."""
    for back in range(7):
        day = now_berlin.date() - dt.timedelta(days=back)
        slot_at = dt.datetime.combine(day, slot, tzinfo=now_berlin.tzinfo)
        if day.weekday() in RUN_WEEKDAYS and now_berlin >= slot_at:
            return day
    return None


def target_session(run_date: dt.date) -> dt.date | None:
    """Tomorrow, if tomorrow is an NYSE session; otherwise None ("no session")."""
    tomorrow = run_date + dt.timedelta(days=1)
    return tomorrow if nyse_calendar().is_session(tomorrow) else None


def signal_session(run_date: dt.date) -> dt.date | None:
    """The bar the outlook reads: the last session on or before the run date."""
    sessions = nyse_calendar().sessions(run_date - dt.timedelta(days=_LOOKBACK_DAYS), run_date)
    return sessions[-1] if sessions else None


def fire_allowed(now: dt.datetime, run_date: dt.date) -> bool:
    """A run may fire late, but never into a session already underway."""
    session = target_session(run_date) or run_date + dt.timedelta(days=1)
    return now_et(now) < dt.datetime.combine(session, RTH_OPEN, tzinfo=US_MARKET_TZ)


def wrapup_due(now: dt.datetime, day: dt.date) -> bool:
    close_at = dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)
    return now_et(now) >= close_at + WRAPUP_DELAY


def wrapup_candidates(now: dt.datetime) -> list[dt.date]:
    """The last two sessions on or before today (ET): today's, and the one a
    restart may still owe a wrap-up for."""
    today = now_et(now).date()
    return nyse_calendar().sessions(today - dt.timedelta(days=_LOOKBACK_DAYS), today)[-2:]
