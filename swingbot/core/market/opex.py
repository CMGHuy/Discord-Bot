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


# ---------------------------------------------------------------------------
# Policy layer
#
# Everything below reads config. `_UNSET` distinguishes "caller did not say"
# from an explicit `None` meaning "not an opex day": a scan resolves the tier
# once and passes it down, rather than re-deriving it per ticker per horizon.
# ---------------------------------------------------------------------------

_UNSET = object()


def _enabled() -> bool:
    from swingbot import config
    return bool(getattr(config, "OPEX_CAUTION_ENABLED", False))


def current_tier(now: dt.datetime | None = None) -> str | None:
    """Today's tier, in US market time. None when the feature is off.

    `now` may carry any timezone -- it is converted before the date is taken,
    which is the whole point. A naive datetime is rejected rather than
    guessed at: assuming it meant UTC or local time is exactly the mistake
    this function exists to prevent.
    """
    if not _enabled():
        return None
    if now is None:
        now = dt.datetime.now(US_MARKET_TZ)
    elif now.tzinfo is None:
        raise ValueError(
            "opex.current_tier() needs an aware datetime -- a naive one has no "
            "defined US date. Pass tzinfo, or omit the argument entirely."
        )
    return opex_tier(now.astimezone(US_MARKET_TZ).date())


def _resolve(tier):
    """The tier the policy should act on.

    The flag is re-checked here, not only inside `current_tier()`: callers
    pass an explicit tier so one scan resolves the calendar once, and without
    this guard `OPEX_CAUTION_ENABLED=false` would still widen a stop for
    anyone who handed a tier straight in.
    """
    if not _enabled():
        return None
    return current_tier() if tier is _UNSET else tier


def minutes_to_us_close(now: dt.datetime | None = None) -> float:
    """Minutes until 16:00 America/New_York on `now`'s US date.

    Negative once the close has passed. Building the close from the
    already-converted local date is what makes this DST-correct on both
    sides without a table.
    """
    if now is None:
        now = dt.datetime.now(US_MARKET_TZ)
    local = now.astimezone(US_MARKET_TZ)
    close = dt.datetime.combine(local.date(), US_CLOSE_TIME, tzinfo=US_MARKET_TZ)
    return (close - local).total_seconds() / 60.0


def effective_min_confidence_level(tier=_UNSET) -> int:
    """`MIN_ALERT_CONFIDENCE_LEVEL`, raised on a monthly expiration.

    Capped at 5 because the level is a 1-5 select; a bump past the top of the
    scale would silently mean "never alert".
    """
    from swingbot import config
    base = int(config.MIN_ALERT_CONFIDENCE_LEVEL)
    if _resolve(tier) != MONTHLY:
        return base
    bump = int(getattr(config, "OPEX_MONTHLY_CONFIDENCE_BUMP", 0) or 0)
    return min(5, base + bump)


def effective_min_confluence(base: int, tier=_UNSET) -> int:
    """`base` (already resolved from config or a `!check` override), raised
    on either tier. Capped at 10, the top of the setting's own range."""
    from swingbot import config
    resolved = _resolve(tier)
    if resolved == MONTHLY:
        bump = getattr(config, "OPEX_MONTHLY_CONFLUENCE_BUMP", 0)
    elif resolved == WEEKLY:
        bump = getattr(config, "OPEX_WEEKLY_CONFLUENCE_BUMP", 0)
    else:
        return base
    return min(10, int(base) + int(bump or 0))


def suppress_new_entries(now: dt.datetime | None = None, tier=_UNSET) -> bool:
    """True inside the monthly-expiration near-close window.

    Monthly only, and only BEFORE the close: once 16:00 ET has passed the
    remaining figure goes negative and this returns False again. The bot's
    session runs to 23:00 Berlin (17:00 ET), so without that lower bound the
    window would keep firing for an hour after the event it guards.
    """
    from swingbot import config
    # Resolved against `now` rather than via _resolve(), so an injected clock
    # decides the tier and the window consistently -- otherwise a test could
    # pin the window to a Friday afternoon while the tier came from the real
    # wall clock.
    if not _enabled():
        return False
    resolved = current_tier(now) if tier is _UNSET else tier
    if resolved != MONTHLY:
        return False
    window = float(getattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 0) or 0)
    if window <= 0:
        return False
    remaining = minutes_to_us_close(now)
    return 0 <= remaining <= window


def stop_mult(tier=_UNSET) -> float:
    """Multiplier for the ATR stop distance. 1.0 leaves it untouched."""
    from swingbot import config
    if _resolve(tier) != MONTHLY:
        return 1.0
    return 1.0 + float(getattr(config, "OPEX_STOP_WIDEN_PCT", 0.0) or 0.0) / 100.0


def size_mult(tier=_UNSET) -> float:
    """Multiplier for position size. 1.0 leaves it untouched."""
    from swingbot import config
    if _resolve(tier) != MONTHLY:
        return 1.0
    cut = float(getattr(config, "OPEX_SIZE_REDUCTION_PCT", 0.0) or 0.0)
    return max(0.0, 1.0 - cut / 100.0)


def badge(tier=_UNSET) -> tuple[str, str] | None:
    """`(title, body)` for the alert embed, or None off an expiration day.

    Posted on EVERY alert that day, whether or not the tightened gates
    changed the outcome -- following the `heat_blocked` precedent in
    embeds.py, where a constraint is flagged rather than hidden.
    """
    resolved = _resolve(tier)
    if resolved == MONTHLY:
        return (
            "⚠️ MONTHLY OPEX",
            "Monthly options expiration: pinning toward big round strikes and "
            "unwind volatility into the close are both elevated. Entry bar raised.",
        )
    if resolved == WEEKLY:
        return (
            "⚠️ Weekly opex",
            "Weekly options expiration. Pinning risk is milder than a monthly "
            "expiration, but present.",
        )
    return None
