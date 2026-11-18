"""v232: one clock for the reconciliation -- UTC stamps to NYSE sessions.

All zone work is Python zoneinfo (session.US_MARKET_TZ); Git Bash has no zone
data and nothing here reads TZ or the process clock.

issue_session(stamp) is the latest regular session whose 09:30 ET open is at
or before the stamp: a pre-open stamp belongs to the previous session, an
after-close stamp to that day's, a weekend or holiday stamp to the last session
before it. override_fidelity.assign_session maps a pre-open time to the same
day and is deliberately not reused (spec clarification 4).

A plan doc's created_at is the creating bar's DATE (plan_types.py); without
issued_at the stamp is that session's close, so its issue bucket is
outside_session by construction and consumers split buckets by stamp source.
"""
from __future__ import annotations

import datetime as dt
import re

from swingbot.core.market import session

UTC = dt.timezone.utc
NY = session.US_MARKET_TZ
ISSUE_BUCKETS = ("open_to_1030", "mid_day", "last_hour", "outside_session")
_BARE_OFFSET = re.compile(r"([+-]\d{2})$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse(text: str) -> dt.datetime:
    text = text.strip().replace(" ", "T", 1)
    if _DATE_ONLY.match(text):
        raise ValueError(f"{text!r} is a date, not a time of day")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return dt.datetime.fromisoformat(_BARE_OFFSET.sub(r"\1:00", text))


def to_utc(value: str | dt.datetime) -> dt.datetime:
    """An aware UTC datetime; a naive value is read as UTC (stores write UTC)."""
    stamp = value if isinstance(value, dt.datetime) else _parse(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def ny_time(stamp) -> dt.datetime:
    return to_utc(stamp).astimezone(NY)


def issue_session(stamp) -> dt.date:
    """The latest NYSE regular session whose open is at or before the stamp."""
    et = ny_time(stamp)
    day = et.date() if et.time() >= session.RTH_OPEN else et.date() - dt.timedelta(days=1)
    found = session.nyse_calendar().session_after(day, 0)
    if found is None:
        raise ValueError(f"{stamp!r} lies outside the NYSE calendar")
    return found


def _close_at(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, session.session_close(day), tzinfo=NY)


def _open_at(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, session.RTH_OPEN, tzinfo=NY)


def in_regular_session(stamp) -> bool:
    et = ny_time(stamp)
    day = et.date()
    if not session.nyse_calendar().is_session(day):
        return False
    return _open_at(day) <= et < _close_at(day)


def minutes_after_open(stamp) -> float | None:
    """Minutes since that day's 09:30 ET open, inside the regular session only."""
    if not in_regular_session(stamp):
        return None
    et = ny_time(stamp)
    return (et - _open_at(et.date())).total_seconds() / 60.0


def issue_bucket(stamp) -> str:
    """open_to_1030 [09:30, 10:30), last_hour [close - 60 min, close), else mid_day;
    outside_session outside the regular session (early closes included)."""
    minutes = minutes_after_open(stamp)
    if minutes is None:
        return "outside_session"
    if minutes < 60:
        return "open_to_1030"
    et = ny_time(stamp)
    if (_close_at(et.date()) - et).total_seconds() <= 3600:
        return "last_hour"
    return "mid_day"


def stamp_source(plan_doc: dict) -> tuple[dt.datetime, str]:
    """(issue stamp, "issued_at" | "created_at") for one stored plan doc."""
    issued = plan_doc.get("issued_at")
    if issued:
        return to_utc(issued), "issued_at"
    created = str(plan_doc.get("created_at") or "").strip()
    if not created:
        raise ValueError(f"plan {plan_doc.get('plan_id')!r} has neither issued_at "
                         f"nor created_at")
    if _DATE_ONLY.match(created):
        day = dt.date.fromisoformat(created)
        return _close_at(day).astimezone(UTC), "created_at"
    return to_utc(created), "created_at"


def sessions_apart(a: dt.date, b: dt.date) -> int:
    """Signed NYSE session count from a to b (each read as its session on or before)."""
    cal = session.nyse_calendar()
    pa, pb = cal.position_on_or_before(a), cal.position_on_or_before(b)
    if pa is None or pb is None:
        raise ValueError(f"{a} or {b} lies before the NYSE calendar")
    return pb - pa
