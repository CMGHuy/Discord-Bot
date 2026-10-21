"""v175: the book-status message -- one line in the alerts channel when the
whole closed book's losing-run zone rises into rough or outside.

This half is pure: it turns a variance band (swingbot/core/analytics/
variance_band.py) into the message text and its BOOK_STATUS embed. The copy
describes and never instructs: no "edge", no stop/check/skip/size/review.
Plan embeds are untouched; this is its own message.

The other half is the latch: post_book_status, called once per scan tick,
posts only when the zone RISES above the one stored under ZONE_JOB in
scheduled_jobs (fired_on is sa.Text, so the zone string needs no migration;
the live_loss_watch latch precedent). A fall stores the lower zone and
posts nothing, so the next rise posts again. The new zone is stored only
after a send returned a message.
"""
from __future__ import annotations

import asyncio
import logging

from swingbot import config
from swingbot.core.analytics import variance_band as vb
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Kind

from . import notices

log = logging.getLogger(__name__)

#: The zone sentence of the message, per posting zone. `normal` posts nothing.
ZONE_PHRASE: dict[str, str] = {
    "rough": "deeper than 80% of simulated runs, within 95%",
    "outside": "beyond 95% of simulated runs",
}


def _usd(band: dict, currency: str) -> str:
    """' (≈ $312.34)' beside the drawdown, or '' when the band has no dollars.

    fmt_money always signs its figure; a drawdown is already worded as
    "down", so the sign is dropped."""
    dollars = band.get("dollars")
    if not dollars:
        return ""
    money = tokens.fmt_money(abs(dollars["drawdown_usd"]), currency).lstrip("+")
    return f" (≈ {money})"


def book_status_text(band: dict, currency: str) -> str | None:
    """The message line, or None when there is nothing to post (insufficient
    band, or a zone other than rough/outside)."""
    if band.get("status") != "ok":
        return None
    current = band["current"]
    phrase = ZONE_PHRASE.get(current.get("zone"))
    if phrase is None:
        return None
    line = (f"Book: {current['run']} losing days in a row / {current['drawdown']:.1f}R"
            f"{_usd(band, currency)} down over 50 close days, {phrase}. Closed trades only.")
    if band["expr"]["not_positive"]:
        line = f"{line} {vb.CAVEAT}"
    return line


def book_status_embed(band: dict, currency: str):
    """The BOOK_STATUS push embed for `band`, or None when nothing posts."""
    text = book_status_text(band, currency)
    if text is None:
        return None
    return notices.system_embed(Kind.BOOK_STATUS, description=text)


#: scheduled_jobs key holding the last zone posted, or fallen back to.
ZONE_JOB = "variance_band:zone"


def _closed_book() -> list[dict]:
    """The whole closed book, every ledger -- the same population the
    /analytics/variance-band route serves. A seam for tests."""
    from swingbot.core.analytics.scope import closed_only
    from swingbot.core.tracking.performance import TradeLog

    return closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])


def _rank(zone: str) -> int:
    return vb.ZONES.index(zone)


def stored_zone() -> str:
    """The last stored zone; a missing or unknown value reads as normal."""
    value = scheduled_repo().fired_on(ZONE_JOB)
    return value if value in vb.ZONES else vb.ZONES[0]


def next_action(stored: str, zone: str) -> str:
    """"post" on a rise, "reset" on a fall, "none" when the zone is unchanged."""
    if _rank(zone) > _rank(stored):
        return "post"
    if _rank(zone) < _rank(stored):
        return "reset"
    return "none"


def _compute_band() -> dict:
    return vb.variance_band(_closed_book())


async def _apply(channel, band: dict) -> bool:
    """Post on a rise (storing the zone only after a successful send), store
    the lower zone on a fall, do nothing on the same zone."""
    zone = band["current"]["zone"]
    action = next_action(stored_zone(), zone)
    if action == "reset":
        scheduled_repo().mark(ZONE_JOB, zone)
        log.info("book status: zone fell to %s -- stored, nothing posted", zone)
        return False
    if action != "post":
        return False
    embed = book_status_embed(band, config.CURRENCY_SYMBOL)
    message = await notices.send_guarded(channel, embed, what="book status")
    if message is None:            # send_guarded swallows failures: store only on success
        return False
    scheduled_repo().mark(ZONE_JOB, zone)
    log.info("book status: zone rose to %s -- posted", zone)
    return True


async def post_book_status(channel) -> bool:
    """Once per scan tick: compute the band off the event loop and post the
    book-status line if the zone rose. Never raises; True only when posted."""
    try:
        band = await asyncio.to_thread(_compute_band)
        if band.get("status") != "ok":
            return False
        return await _apply(channel, band)
    except Exception as exc:
        swallowed(log, "scan.book_status", exc,
                  "book status: could not compute or post the variance band",
                  level=logging.ERROR, exc_info=True)
        return False
