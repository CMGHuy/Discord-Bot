"""v227: the short headline the admin site speaks for a simple-channel post.

Table-driven: one phrase per Kind of the five families the simple channel
carries, then the ticker, then -- for new setups and tickets only -- the entry
price ("New long alert, AAPL, buy at 187.50"). A missing piece is dropped,
never spoken as "None". A Kind with no phrase speaks its registry label,
lower-cased. Reads ``direction`` and ``entry_price`` off the embed with
``getattr`` (presentation.components.PushEmbed carries both).
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from swingbot.core.presentation import kinds, tokens
from swingbot.core.presentation.kinds import Family, Kind

#: The families the simple channel posts; SYSTEM and BOOK never go there.
FEED_FAMILIES: tuple[Family, ...] = (Family.NEW_SETUP, Family.ENTRY, Family.MANAGE,
                                     Family.WATCH, Family.RESULT)

KIND_PHRASES: dict[Kind, str] = {
    Kind.SETUP_ALERT: "New {side} alert",
    Kind.SETUP_SIMPLE: "New {side} alert",
    Kind.STRATEGY_SIGNAL: "New {side} alert",
    Kind.TICKET_PLACE: "Place order",
    Kind.TICKET_DO_NOT_PLACE: "Do not place",
    Kind.DIGEST: "Setup digest",
    Kind.ENTRY_TRIGGERED: "Entry triggered",
    Kind.FILLED: "Order filled",
    Kind.RECLAIM_ORDER: "Reclaim order",
    Kind.BE_MOVED: "Stop moved to break even",
    Kind.TP1_HIT: "Take profit one",
    Kind.MOVE_STOP: "Move stop loss",
    Kind.CANCEL: "Order cancelled",
    Kind.RISK_CAP: "Cancelled by risk cap",
    Kind.PLAN_UPDATE: "Plan updated",
    Kind.NEAR_STOP: "Near stop",
    Kind.NEAR_TP: "Near target",
    Kind.CLOSED_TRADE: "Trade closed",
    Kind.STOPPED: "Stopped out",
    Kind.WIN: "Winner",
    Kind.SCRATCHED: "Scratched",
    Kind.EXITED: "Exited",
    Kind.CLOSE_AT_MARKET: "Close at market",
    Kind.EXPIRED: "Expired",
    Kind.INVALIDATED: "Invalidated",
}

#: Kinds whose headline speaks the entry price.
_PRICED = frozenset({Kind.SETUP_ALERT, Kind.SETUP_SIMPLE, Kind.STRATEGY_SIGNAL,
                     Kind.TICKET_PLACE})
_PRICE_VERB = {"bullish": "buy at", "bearish": "sell at"}
_SAMPLE = SimpleNamespace(direction="bullish", entry_price=187.50)


def _side(direction) -> str | None:
    word = kinds.side_word(direction if isinstance(direction, str) else None)
    return None if word == tokens.ABSENT else word.lower()


def kind_phrase(kind: Kind, side: str | None = None) -> str:
    """The phrase for ``kind``; ``{side}`` filled or dropped with its space."""
    template = KIND_PHRASES.get(kind)
    if template is None:
        return kind.label.lower()
    return template.replace("{side} ", f"{side} " if side else "")


def _ticker(ticker) -> str:
    return ticker.strip() if isinstance(ticker, str) else ""


def _price(embed) -> float | None:
    try:
        value = float(getattr(embed, "entry_price", None))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _price_clause(kind: Kind, direction, price: float | None) -> str:
    if kind not in _PRICED or price is None:
        return ""
    return f"{_PRICE_VERB.get(direction, 'entry')} {price:.2f}"


def feed_headline(kind: Kind, embed, ticker: str | None) -> str:
    """"New long alert, AAPL, buy at 187.50" / "Order filled, MSFT" / "Order cancelled"."""
    direction = getattr(embed, "direction", None)
    parts = (kind_phrase(kind, _side(direction)), _ticker(ticker),
             _price_clause(kind, direction, _price(embed)))
    return ", ".join(part for part in parts if part)


def sample_headline(kind: Kind) -> str:
    """What ``kind`` sounds like for a long AAPL plan entering at 187.50."""
    return feed_headline(kind, _SAMPLE, "AAPL")
