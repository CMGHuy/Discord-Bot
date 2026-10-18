"""Data kinds, askers, freshness windows, cache keys and quote shape (v171 D2/D6/D9).

Pure types: no database, no provider imports. Windows are read from
``swingbot.config`` at call time so a hot reload takes effect immediately.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterator, Optional

from swingbot import config

# Duplicate of data_store.INTRADAY_MAX_AGE_SECONDS so this module imports nothing
# from data_store; V171-24 asserts the two agree.
INTRADAY_MAX_AGE_S = 4 * 3600

PROVIDER_ALPACA = "alpaca"
PROVIDER_YF = "yfinance"

OUTCOMES = ("hit", "shared-wait", "fetched", "budget-deferred", "failed")


class DataKind(str, Enum):
    QUOTE = "quote"
    DAILY_BARS = "daily"
    INTRADAY_BARS = "intraday"
    INDEX_QUOTE = "index"
    EARNINGS = "earnings"
    METADATA = "meta"


class Asker(str, Enum):
    STOP_MONITOR = "stop_monitor"
    REQUOTE = "requote"
    SCAN = "scan"
    BACKGROUND = "background"
    ADMIN_DASHBOARD = "admin_dashboard"
    ADMIN_PAGE = "admin_page"
    ADMIN_FRESH = "admin_fresh"

    @property
    def priority(self) -> int:
        return _PRIORITY[self]

    def window_s(self, kind: DataKind) -> Optional[float]:
        """Max cache age for this asker and kind. None = persistent, 0.0 = never cached."""
        if kind is DataKind.METADATA:
            return None
        if self is Asker.ADMIN_FRESH or kind is DataKind.DAILY_BARS:
            return 0.0
        if kind is DataKind.QUOTE:
            return float(getattr(config, _QUOTE_ATTR[self]))
        if kind is DataKind.INTRADAY_BARS:
            return float(INTRADAY_MAX_AGE_S)
        return float(getattr(config, _KIND_ATTR[kind]))


_PRIORITY = {
    Asker.STOP_MONITOR: 1, Asker.REQUOTE: 2, Asker.SCAN: 3, Asker.BACKGROUND: 4,
    Asker.ADMIN_DASHBOARD: 5, Asker.ADMIN_PAGE: 5, Asker.ADMIN_FRESH: 5,
}

_QUOTE_ATTR = {
    Asker.STOP_MONITOR: "QUOTE_MAX_AGE_MONITOR_S",
    Asker.REQUOTE: "QUOTE_MAX_AGE_REQUOTE_S",
    Asker.SCAN: "QUOTE_MAX_AGE_SCAN_S",
    Asker.BACKGROUND: "QUOTE_MAX_AGE_SCAN_S",
    Asker.ADMIN_DASHBOARD: "QUOTE_MAX_AGE_DASHBOARD_S",
    Asker.ADMIN_PAGE: "QUOTE_MAX_AGE_ADMIN_S",
}

_KIND_ATTR = {
    DataKind.INDEX_QUOTE: "INDEX_QUOTE_MAX_AGE_S",
    DataKind.EARNINGS: "EARNINGS_MAX_AGE_S",
}


def cache_key(kind: DataKind, symbol: str, variant: str = "") -> str:
    return f"{kind.value}:{symbol.upper()}:{variant}"


@dataclass(frozen=True)
class Entry:
    value: Any
    fetched_at: datetime
    source: str
    outcome: str

    def age_s(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.fetched_at).total_seconds()


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class QuoteDetail:
    symbol: str
    price: Optional[float]
    trade_at: Optional[datetime]
    bid: Optional[float]
    ask: Optional[float]
    quote_at: Optional[datetime]
    source: str

    def mid(self) -> Optional[float]:
        """Bid/ask midpoint, only for a sane two-sided (uncrossed) quote."""
        if self.bid is None or self.ask is None:
            return None
        if self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
            return (self.bid + self.ask) / 2
        return None

    def to_doc(self) -> dict:
        return {
            "symbol": self.symbol, "price": self.price,
            "trade_at": _iso(self.trade_at), "bid": self.bid, "ask": self.ask,
            "quote_at": _iso(self.quote_at), "source": self.source,
        }

    @classmethod
    def from_doc(cls, doc: dict) -> "QuoteDetail":
        return cls(
            symbol=doc["symbol"], price=doc.get("price"),
            trade_at=_parse(doc.get("trade_at")), bid=doc.get("bid"), ask=doc.get("ask"),
            quote_at=_parse(doc.get("quote_at")), source=doc["source"],
        )


_FRESH: ContextVar[bool] = ContextVar("marketdata_fresh", default=False)


@contextmanager
def fresh_request() -> Iterator[None]:
    token = _FRESH.set(True)
    try:
        yield
    finally:
        _FRESH.reset(token)


def is_fresh_request() -> bool:
    return _FRESH.get()


def resolve_asker(asker: Asker) -> Asker:
    """Admin askers become ADMIN_FRESH inside a fresh_request(); others are untouched."""
    if is_fresh_request() and asker in (Asker.ADMIN_PAGE, Asker.ADMIN_DASHBOARD):
        return Asker.ADMIN_FRESH
    return asker
