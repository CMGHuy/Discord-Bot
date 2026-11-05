"""v192: session timing for a market plan waiting for its next open (live only).

Which NYSE session's open decides the plan, and where one poll at ``now`` sits
against it. Pure: no store, no price, no I/O. What happens at that open -- fill,
cancel, rest for a reclaim -- is gap_reclaim.decide_at_open, the function the
replay calls too.

* deciding session: the first NYSE session whose 09:30 ET open is at or after
  the plan's ``issued_at`` (the alert); a plan without one (or with an
  unreadable one) uses the session after ``created_at``;
* phases of a waiting plan: BEFORE (no live tape, or a regular session before
  the deciding one), EXTENDED (a live extended-hours tape before the deciding
  open: the premarket stop-cross debounce runs), OPEN (the deciding session's
  regular hours: the first such poll decides), MISSED (that session closed, or
  a later one is trading, with no deciding poll);
* phases of a plan resting for its reclaim (``reclaim_session`` set): WAITING
  until that session's official close, AFTER_CLOSE from it on.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.market.session import (RTH_OPEN, US_MARKET_TZ, is_nyse_regular_session,
                                          is_tape_open, now_et, nyse_calendar, session_close)

PREMARKET_STOP_CONFIRM_POLLS = 2

BEFORE = "before"
EXTENDED = "extended"
OPEN = "open"
MISSED = "missed"
WAITING = "waiting"
AFTER_CLOSE = "after_close"


def _as_et(stamp) -> dt.datetime | None:
    """An ISO timestamp in ET (naive = UTC, as plan stamps are written), or None."""
    if stamp is None:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(US_MARKET_TZ)


def _created_day(created_at) -> dt.date | None:
    """The signal day: a date-only stamp (or UTC midnight) is that date, any
    other stamp its ET date -- plan_manager._eligible_session's reading."""
    try:
        created = dt.datetime.fromisoformat(str(created_at))
    except ValueError:
        return None
    if created.tzinfo is None:
        return created.date()
    utc = created.astimezone(dt.timezone.utc)
    if utc.time() == dt.time.min:
        return utc.date()
    return created.astimezone(US_MARKET_TZ).date()


def deciding_session(plan) -> dt.date | None:
    """The NYSE session whose open decides ``plan`` (module docstring), or None."""
    calendar = nyse_calendar()
    issued = _as_et(getattr(plan, "issued_at", None))
    if issued is not None:
        day = issued.date()
        if calendar.is_session(day) and issued.time() <= RTH_OPEN:
            return day
        return calendar.next_session(day)
    created = _created_day(getattr(plan, "created_at", None))
    return calendar.next_session(created) if created is not None else None


def _iso_day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _closed(day: dt.date, et: dt.datetime) -> bool:
    """``et`` is at or after ``day``'s official close (13:00 ET on a half-day)."""
    return et.date() > day or (et.date() == day and et.time() >= session_close(day))


def market_phase(plan, now=None) -> str:
    """Where a poll at ``now`` sits for this waiting plan (module docstring)."""
    et = now_et(now)
    rest = _iso_day(getattr(plan, "reclaim_session", None))
    if rest is not None:
        return AFTER_CLOSE if _closed(rest, et) else WAITING
    day = deciding_session(plan)
    if day is None:
        return MISSED
    if is_nyse_regular_session(et):
        if et.date() == day:
            return OPEN
        return MISSED if et.date() > day else BEFORE
    if _closed(day, et):
        return MISSED
    return EXTENDED if is_tape_open(et) else BEFORE
