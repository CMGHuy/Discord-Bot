"""v119: the compression short's ten-session paper close -- pure helpers.

The fill session is session 1, so the tenth session is the ninth after it, in
the live manager and in the replay walker alike. Nothing here reads a price:
the manager owns every decision, this module owns the dates, the notice ids and
the rule for which closing price may be trusted.
"""
from __future__ import annotations

import datetime as dt
from typing import NamedTuple

from swingbot.core.market.session import (US_MARKET_TZ, SessionCalendar,
                                          nyse_calendar, session_close)

TIME_EXIT_DUE = "time_exit_due"
TIME_EXIT_UNRESOLVED = "time_exit_unresolved"
TIME_EVENTS = frozenset({TIME_EXIT_DUE, TIME_EXIT_UNRESOLVED})

TIME_EXIT_REASON = "time_exit"
#: price_basis stamped on a leg: the paper close at the official auction, and
#: the replay's stand-in (the tenth bar's Close).
OFFICIAL_BASIS = "official_auction"
PROXY_BASIS = "daily_close_proxy"

#: The notice goes out at 15:30 ET, or this long before an early close.
NOTICE_STANDARD = dt.time(15, 30)
NOTICE_LEAD = dt.timedelta(minutes=20)
#: A first notice later than the deadline by more than this is marked LATE
#: (the manager polls about once a minute, so a few seconds are not "late").
LATE_GRACE = dt.timedelta(minutes=5)


class AuctionClose(NamedTuple):
    """What an injected closing-auction price source returns."""

    price: float
    source: str
    asof: str


def tenth_session(fill_day: dt.date, calendar: SessionCalendar) -> dt.date:
    """The session on which the position must be flat; the fill session is #1."""
    days = calendar.sessions(fill_day, calendar.last)
    if not days or days[0] != fill_day or len(days) < 10:
        raise ValueError("fill session outside calendar coverage")
    return days[9]


def _et_date(stamp: str) -> dt.date:
    moment = dt.datetime.fromisoformat(str(stamp))
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(US_MARKET_TZ).date()


def fill_day_from_history(history: list[dict]) -> dt.date:
    """The ET session date of the first ACTIVE transition (the fill), never of
    ``created_at``, which is the signal day."""
    for entry in history:
        if entry.get("status") == "ACTIVE" and entry.get("at"):
            return _et_date(entry["at"])
    raise ValueError("no ACTIVE transition with a timestamp in the status history")


def official_close_at(day: dt.date) -> dt.datetime | None:
    """The exchange close of ``day`` as an aware ET datetime, or None when the
    schedule does not cover it (not a session of the frozen calendar). Callers
    fail closed on None; 16:00 is never guessed."""
    if not nyse_calendar().is_session(day):
        return None
    return dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)


def notice_deadline(close_at_et: dt.datetime) -> dt.datetime:
    """min(15:30 ET, close - 20 minutes)."""
    standard = close_at_et.replace(hour=NOTICE_STANDARD.hour, minute=NOTICE_STANDARD.minute,
                                   second=0, microsecond=0)
    return min(standard, close_at_et - NOTICE_LEAD)


def time_notice_id(plan_id: str, transition: str, day: dt.date) -> str:
    return f"{plan_id}:{transition}:{day.isoformat()}"


def parse_auction(observed) -> AuctionClose | None:
    """An official, positive closing-auction print, or None. A tuple from the
    injected source is accepted; a last quote or a daily Close never is."""
    if observed is None:
        return None
    try:
        auction = AuctionClose(*observed)
        price = float(auction.price)
    except (TypeError, ValueError):
        return None
    if auction.source != OFFICIAL_BASIS or not price > 0:
        return None
    return AuctionClose(price, auction.source, auction.asof)


def cover_fraction(plan) -> float:
    """The part of the original position still open: legs already realized
    (a legacy PARTIAL's TP1) are subtracted."""
    return round(max(0.0, 1.0 - sum(leg["fraction"] for leg in plan.legs_realized)), 6)
