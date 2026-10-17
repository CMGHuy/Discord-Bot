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

import asyncio
import datetime as dt
import logging

from discord.ext import tasks

from swingbot import config
from swingbot.bot_core import in_session
from swingbot.core import presentation as ui
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.scanning import telemetry

from . import notices, runstate

log = logging.getLogger(__name__)

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


# --- v148 OH18: the sends, the watchdog loop and the provider check -----------

def _channel():
    """``loops._ops_channel()``, looked up at call time (``loops`` imports us)."""
    from . import loops
    return loops._ops_channel()


async def _post(embed) -> bool:
    """False when no ops channel is configured. A failed send raises, so the
    caller's flag stays unset and the next tick retries (as escalation does)."""
    channel = _channel()
    if channel is None:
        return False
    await channel.send(**ui.push_kwargs(embed))
    return True


def _stale_embed(verdict: str, now: dt.datetime, last_success: str):
    if verdict == "recover":
        return notices.stale_scan_recovered_embed(last_success)
    age_min = int((now - parse_moment(last_success)).total_seconds() // 60)
    return notices.stale_scan_embed(age_min, last_success)


async def watchdog_tick(now: dt.datetime | None = None) -> str | None:
    """One stale-scan decision; returns the verdict it posted, or None."""
    now = now or dt.datetime.now(dt.timezone.utc)
    last = runstate.last_success_iso()
    verdict = stale_scan_verdict(
        now, last, int(config.SCAN_INTERVAL_MINUTES), BOOTED_AT,
        in_session=in_session(), paused=runstate.is_scan_paused(),
        failure_alert_active=runstate.get_alert_active(),
        stale_alert_active=runstate.get_stale_alert_active())
    if verdict is None or not await _post(_stale_embed(verdict, now, last)):
        return None
    runstate.set_stale_alert_active(verdict == "alert")
    return verdict


@tasks.loop(minutes=1)
async def scan_watchdog():
    """v148 O3: the wedged tick the failure streak cannot see (a dead process
    is the VM cron's). Never raises: that would stop the loop for good."""
    try:
        await watchdog_tick()
    except Exception as exc:
        swallowed(log, "ops.scan_watchdog", exc, "scan watchdog tick failed",
                  level=logging.ERROR, exc_info=True)


async def _latest_scan_row() -> dict | None:
    rows = await asyncio.to_thread(telemetry.recent_scan_telemetry, 1)
    return rows[-1] if rows else None


async def _provider_check(row: dict | None) -> str | None:
    row = row if row is not None else await _latest_scan_row()
    fallback_pct = float(config.PROVIDER_FALLBACK_ALERT_PCT)
    empty_pct = float(config.EMPTY_SYMBOLS_ALERT_PCT)
    verdict = provider_verdict(row, fallback_pct=fallback_pct, empty_pct=empty_pct,
                               alert_active=runstate.get_provider_alert_active())
    if verdict is None:
        return None
    embed = (notices.provider_degraded_embed(row, fallback_pct, empty_pct)
             if verdict == "alert" else notices.provider_recovered_embed(row))
    if not await _post(embed):
        return None
    runstate.set_provider_alert_active(verdict == "alert")
    return verdict


async def check_provider_health(row: dict | None = None) -> str | None:
    """v148 O4: one notice per provider incident, one on recovery, from the
    newest scan row (or `row`). Never raises into the scan tick."""
    try:
        return await _provider_check(row)
    except Exception as exc:
        swallowed(log, "ops.provider_health", exc, "provider health check failed",
                  level=logging.ERROR, exc_info=True)
        return None
