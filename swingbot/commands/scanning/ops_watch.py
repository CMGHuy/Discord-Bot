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
from swingbot.bot_core import SESSION_TZ, in_session
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


def moment_text(iso: str | None) -> str:
    """"07:04 UTC (08:04 Berlin)" for an ISO timestamp; the raw text if unreadable."""
    moment = parse_moment(iso)
    if moment is None:
        return str(iso)
    local = moment.astimezone(SESSION_TZ)
    return f"{moment:%H:%M} UTC ({local:%H:%M} {local.tzname()})"


def describe_stale_cause(now: dt.datetime, snap: dict, interval_min: int) -> str:
    """What the heartbeat says the scan is doing, in one or two bullet lines.

    Three readings, most specific first: a tick that started and has not
    finished (slow, not necessarily hung), a tick that failed (with its error),
    or no tick started at all (the loop itself is stuck before the scan)."""
    limit = STALE_FACTOR * interval_min
    started = parse_moment(snap.get("tick_started_at"))
    if started is not None:
        run_min = int((now - started).total_seconds() // 60)
        return (f"• A scan tick started at {moment_text(snap['tick_started_at'])} "
                f"(phase: {snap.get('tick_phase') or 'scan'}) and has run {run_min} min "
                f"without finishing. It may just be slow, not hung; the limit is {limit} min "
                f"between completed ticks (a tick is due every {interval_min} min).")
    if snap.get("last_error"):
        return (f"• The last tick failed ({snap.get('consecutive_failures') or 1} in a row) at "
                f"{moment_text(snap.get('last_error_at'))}: `{snap['last_error']}`")
    return (f"• No scan tick has started since the last completed one (a tick is due every "
            f"{interval_min} min). The scan loop itself may be stuck before the scan begins.")


def _stale_embed(verdict: str, now: dt.datetime, last_success: str, snap: dict):
    shown = moment_text(last_success)
    if verdict == "recover":
        return notices.stale_scan_recovered_embed(shown)
    age_min = int((now - parse_moment(last_success)).total_seconds() // 60)
    cause = describe_stale_cause(now, snap, int(config.SCAN_INTERVAL_MINUTES))
    return notices.stale_scan_embed(age_min, shown, cause)


def _log_stale_verdict(verdict: str, now: dt.datetime, last: str, snap: dict) -> None:
    interval = int(config.SCAN_INTERVAL_MINUTES)
    age_min = int((now - parse_moment(last)).total_seconds() // 60)
    fields = (f"age_min={age_min} limit_min={STALE_FACTOR * interval} interval_min={interval} "
              f"last_success={last} tick_started_at={snap.get('tick_started_at')} "
              f"tick_phase={snap.get('tick_phase')} last_error={snap.get('last_error')} "
              f"consecutive_failures={snap.get('consecutive_failures')}")
    if verdict == "alert":
        log.warning("scan watchdog: STALE alert posted -- %s", fields)
    else:
        log.info("scan watchdog: stale alert cleared -- %s", fields)


async def watchdog_tick(now: dt.datetime | None = None) -> str | None:
    """One stale-scan decision; returns the verdict it posted, or None."""
    now = now or dt.datetime.now(dt.timezone.utc)
    last = runstate.last_success_iso()
    verdict = stale_scan_verdict(
        now, last, int(config.SCAN_INTERVAL_MINUTES), BOOTED_AT,
        in_session=in_session(), paused=runstate.is_scan_paused(),
        failure_alert_active=runstate.get_alert_active(),
        stale_alert_active=runstate.get_stale_alert_active())
    if verdict is None:
        return None
    snap = runstate.tick_snapshot()
    if not await _post(_stale_embed(verdict, now, last, snap)):
        log.warning("scan watchdog: %s verdict but no ops channel configured; not posted", verdict)
        return None
    runstate.set_stale_alert_active(verdict == "alert")
    _log_stale_verdict(verdict, now, last, snap)
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
