"""v144: post the next-session outlook and its wrap-up (the Discord side).

The scan itself is core (scanning/outlook_run.py), run off the event loop and
under the same scan lock every other scan holds. A failing scan still posts a
digest saying "Outlook unavailable", and issues nothing. Everything goes to the
alerts channel (silenced, like every alert there); cards go through
_send_alerts, so they get the plan buttons and the simple-channel mirror.

Length: the digest and wrap-up text are split with notices.chunk_text (1990
chars, under Discord's 2000-char message and 4096-char embed-description caps).
"""
import asyncio
import logging

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core.db import write_failure
from swingbot.core.infra.logsetup import new_scan_id, scan_context
from swingbot.core.infra.silent_channel import silence
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import outlook_embeds, outlook_run, outlook_session, runstate, scan_run
from swingbot.core.scanning.outlook_types import OutlookResult

from . import notices
from .alerts import _send_alerts

log = logging.getLogger(__name__)


def _alerts_channel():
    cid = config.DISCORD_CHANNEL_TRADES_ID
    return silence(bot.get_channel(int(cid))) if cid else None


def _safe_outlook(run_date) -> OutlookResult:
    try:
        return outlook_run.run_outlook(run_date)
    except Exception as exc:
        halt = outlook_run.as_halt(exc, [])
        if halt is exc:
            raise
        if halt is not None:
            raise halt from exc
        log.exception("next_session_scan: the outlook scan failed")
        return OutlookResult(run_date=run_date, target=outlook_session.target_session(run_date),
                             unavailable=f"scan failed ({type(exc).__name__}: {exc})"[:300])


def _halted_result(run_date, halt: write_failure.StoreWriteHalt) -> OutlookResult:
    """The store stopped recording mid-issue: the cards already built still go out
    (a trade in the book with no alert is never silently lost)."""
    log.error("next_session_scan: store write halt -- %s", halt)
    return OutlookResult(run_date=run_date, target=outlook_session.target_session(run_date),
                         unavailable=f"store write halted ({halt})"[:300], alerts=list(halt.alerts),
                         halted=halt)   # the loop pauses scanning and tells ops (loops._halt_on_store_failure)


def digest_embeds(result: OutlookResult) -> list:
    detail = result.target.strftime("%A") if result.target else "no session"
    return [notices.system_embed(Kind.OUTLOOK, detail, chunk)
            for chunk in notices.chunk_text(outlook_embeds.digest_text(result))]


async def run_next_session_outlook(run_date) -> OutlookResult | None:
    channel = _alerts_channel()
    if channel is None:
        log.warning("next_session_scan: DISCORD_CHANNEL_TRADES_ID not set or channel not found; no outlook posted")
        return None
    with scan_context(new_scan_id()):
        async with scan_run._scan_lock:
            runstate._mark_running(True)
            try:
                result = await asyncio.to_thread(_safe_outlook, run_date)
            except write_failure.StoreWriteHalt as halt:
                result = _halted_result(run_date, halt)
            finally:
                runstate._mark_running(False)
    for embed in digest_embeds(result):
        await notices.send_guarded(channel, embed, what="outlook digest")
    if result.alerts:
        await _send_alerts(channel, result.alerts)
    log.info("next_session_scan: %s -> %d plan(s), %d watch, %d near-miss(es)%s", run_date,
             len(result.plans), len(result.watch), len(result.near_misses),
             f" (unavailable: {result.unavailable})" if result.unavailable else "")
    return result


async def post_wrapup_when_terminal(day) -> bool:
    """Post D's wrap-up once none of its outlook plans is still PENDING.
    True = done (posted, or nothing to post); False = ask again next minute."""
    plans = await asyncio.to_thread(PlanStore().for_session, day)
    if any(plan.status == PlanStatus.PENDING for plan in plans):
        return False
    if not plans:
        return True
    channel = _alerts_channel()
    if channel is None:
        log.warning("next_session_wrapup: no alerts channel; %s's wrap-up not posted", day)
        return True
    for chunk in notices.chunk_text(outlook_embeds.wrapup_text(day, plans)):
        await notices.send_guarded(channel, notices.system_embed(Kind.OUTLOOK_WRAPUP, day.strftime("%A"), chunk),
                                   what="outlook wrap-up")
    return True
