"""v148 O3/O4: the bot's own ops watch -- stale-scan and provider verdicts.

The verdicts are pure functions of their arguments, so the truth tables are
tested without a bot, a database or a clock. OH18 adds the
``scan_watchdog`` loop and ``check_provider_health``, which read the
heartbeat flags and post to the ops channel.

**Never import ``loops`` at module level here.** ``loops`` imports this
module at its top; the ops channel is looked up at call time instead
(``_channel()``, OH18), which also keeps tests' monkeypatching of
``loops._ops_channel`` effective.
"""
from __future__ import annotations

import datetime as dt

#: Process boot (UTC). The watchdog stays quiet until the process has been up
#: STALE_FACTOR x SCAN_INTERVAL_MINUTES, so a morning restart after an
#: overnight outage gets its first tick before anyone is paged.
BOOTED_AT: dt.datetime = dt.datetime.now(dt.timezone.utc)

#: A scan is stale when its last success is older than this many intervals.
STALE_FACTOR = 2

_PROVIDER_FIELDS = ("provider_fallback_rate", "empty_rate")


def parse_moment(iso: str | None) -> dt.datetime | None:
    """An ISO timestamp as an aware datetime (naive taken as UTC), or None."""
    try:
        moment = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def stale_scan_verdict(now: dt.datetime, last_success: str | None, interval_min: int,
                       booted_at: dt.datetime, *, in_session: bool, paused: bool,
                       failure_alert_active: bool, stale_alert_active: bool) -> str | None:
    """"alert", "recover" or None (spec § O3).

    - "alert": in session, not paused, no failure-streak alert already open,
      the last success older than STALE_FACTOR x the interval, the process up
      at least that long, and no stale alert already open.
    - "recover": a stale alert is open and the last success is fresh again,
      whatever the session (ticks stamp ``last_success`` off-session too).
    - None otherwise, and whenever ``last_success`` is missing or unreadable:
      unknown is never stale (the rule of ``runstate._read_heartbeat``).
    """
    last = parse_moment(last_success)
    if last is None:
        return None
    threshold = dt.timedelta(minutes=STALE_FACTOR * interval_min)
    stale = now - last > threshold
    if stale_alert_active:
        return None if stale else "recover"
    if not stale or not in_session or paused or failure_alert_active:
        return None
    return "alert" if now - booted_at >= threshold else None


def _above(rate: float | None, pct: float) -> bool:
    return rate is not None and rate > pct / 100


def provider_verdict(row: dict | None, *, fallback_pct: float, empty_pct: float,
                     alert_active: bool) -> str | None:
    """"alert", "recover" or None for the newest scan row (spec § O4).

    A breach is ``provider_fallback_rate > fallback_pct/100`` or
    ``empty_rate > empty_pct/100``; a None rate never breaches. A row that
    predates v148 (neither field present) is unknown: it neither alerts nor
    recovers. Once per incident: an open alert only ever recovers.
    """
    if not row or not any(key in row for key in _PROVIDER_FIELDS):
        return None
    breach = (_above(row.get("provider_fallback_rate"), fallback_pct)
              or _above(row.get("empty_rate"), empty_pct))
    if breach == alert_active:
        return None
    return "alert" if breach else "recover"
