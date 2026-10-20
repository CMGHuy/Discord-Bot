"""v175: the book-status message -- one line in the alerts channel when the
whole closed book's losing-run zone rises into rough or outside.

This half is pure: it turns a variance band (swingbot/core/analytics/
variance_band.py) into the message text and its BOOK_STATUS embed. The copy
describes and never instructs: no "edge", no stop/check/skip/size/review.
Plan embeds are untouched; this is its own message.
"""
from __future__ import annotations

from swingbot.core.analytics import variance_band as vb
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Kind

from . import notices

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
