"""v144: risk is surfaced, not prevented. When the other lane holds an open or
pending trade on the same ticker, an alert says so with that trade's dollar
risk, so the partner sees the combined exposure before placing a second order.
Display only: it gates, sizes and cancels nothing, and a failure renders no
field rather than breaking an alert. A pending stop-entry plan's placeholder
trade is "open", so "open or pending" is one query.
"""
from __future__ import annotations

import logging

from swingbot.core.tracking.origin import NEXT_SESSION, origin_of

log = logging.getLogger(__name__)

OVERLAP_FIELD = "⚠ Overlap"
_LANE_WORDS = {None: "regular", NEXT_SESSION: "outlook"}


def _other_lane_trades(ticker: str, viewer_origin: str | None) -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status="open", ticker=ticker, limit=None) or []
    return [trade for trade in trades if origin_of(trade) != viewer_origin]


def _risk_text(trade: dict) -> str:
    shares, entry, stop = trade.get("shares"), trade.get("entry"), trade.get("stop_loss")
    if not shares or entry is None or stop is None:
        return "risk n/a"
    return f"risk ${float(shares) * abs(float(entry) - float(stop)):,.0f}"


def overlap_line(ticker: str, *, viewer_origin: str | None) -> str | None:
    try:
        others = _other_lane_trades(ticker, viewer_origin)
    except Exception:
        log.debug("overlap line unavailable for %s", ticker, exc_info=True)
        return None
    if not others:
        return None
    trade = others[0]
    lane = _LANE_WORDS.get(origin_of(trade), str(origin_of(trade)))
    return f"⚠ {lane} plan also open on {ticker} ({trade.get('direction')}, {_risk_text(trade)})"


def append_overlap_field(embed, ticker: str, *, viewer_origin: str | None = None) -> None:
    """Add the ⚠ Overlap field when the other lane is open on `ticker`."""
    line = overlap_line(ticker, viewer_origin=viewer_origin)
    if line:
        embed.add_field(name=OVERLAP_FIELD, value=line, inline=False)
