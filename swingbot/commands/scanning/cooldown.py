"""v152 D3: the per-symbol alert cooldown, owner of the alert_posts record.

On the scheduled session scan only (alerts._send_alerts(apply_cooldown=True)),
an alert for (ticker, direction, horizon_key) is not posted when one with the
same key was POSTED within ALERT_SYMBOL_COOLDOWN_HOURS. Only the Discord post
is held: the plan and its placeholder trade were persisted by scan_run before
any of this runs, so the book is unchanged.

Fails open: any error reading the window or writing the record posts the
alert and logs one WARNING -- a cooldown fault never costs an alert and never
raises into the scan. The callers run these through asyncio.to_thread.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot import config
from swingbot.core.db.repositories.alert_posts import alert_posts_repo
from swingbot.core.market.session import BERLIN_TZ, now_berlin

log = logging.getLogger(__name__)

PRUNE_FLOOR_HOURS = 168.0          # keep at least a week of alert_posts
_DIRECTION_WORDS = {"bullish": "long", "bearish": "short"}


def _now(now: dt.datetime | None) -> dt.datetime:
    return now if now is not None else dt.datetime.now(dt.timezone.utc)


def _hours() -> float:
    return float(config.ALERT_SYMBOL_COOLDOWN_HOURS or 0)


def suppressed(plan, now: dt.datetime | None = None) -> bool:
    """True when an alert with this plan's key was posted inside the window."""
    try:
        hours = _hours()
        if hours <= 0:
            return False
        since = _now(now) - dt.timedelta(hours=hours)
        return alert_posts_repo().posted_since(plan.ticker, plan.direction,
                                               plan.horizon_key, since)
    except Exception:
        log.warning("cooldown: window read failed for %s -- posting the alert anyway.",
                    getattr(plan, "ticker", "?"), exc_info=True)
        return False


def record(plan, outcome: str, now: dt.datetime | None = None) -> None:
    """Append one alert_posts row ('posted' after Discord accepted it, or
    'suppressed'). Never raises."""
    try:
        alert_posts_repo().add(plan.ticker, _now(now), outcome,
                               direction=plan.direction, horizon_key=plan.horizon_key,
                               plan_id=getattr(plan, "plan_id", None))
    except Exception:
        log.warning("cooldown: could not record the %s alert for %s.",
                    outcome, getattr(plan, "ticker", "?"), exc_info=True)


def _held_label(plan) -> str:
    direction = _DIRECTION_WORDS.get(plan.direction, plan.direction)
    return f"{plan.ticker} {direction} {plan.horizon_key}"


def held_note(held: list) -> str | None:
    """The one-line ops note for a scan that held alerts; None when it held none."""
    if not held:
        return None
    names = ", ".join(_held_label(plan) for plan in held)
    return (f"Cooldown held {len(held)} alert(s) this scan: {names} "
            f"(posted within {_hours():g}h).")


def held_today(now: dt.datetime | None = None) -> int:
    """Alerts held since 00:00 Europe/Berlin of today's Berlin date; 0 on error."""
    try:
        day = now_berlin(now).date()
        since = dt.datetime.combine(day, dt.time.min, tzinfo=BERLIN_TZ)
        return alert_posts_repo().count_since("suppressed", since)
    except Exception:
        log.warning("cooldown: could not count today's held alerts.", exc_info=True)
        return 0


def prune(now: dt.datetime | None = None) -> int:
    """Delete alert_posts rows older than max(window, one week). Raises: the
    nightly caller (loops.daily_recap) logs a failure."""
    keep = max(_hours(), PRUNE_FLOOR_HOURS)
    return alert_posts_repo().prune_before(_now(now) - dt.timedelta(hours=keep))
