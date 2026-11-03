"""v201: the request-path door for market values.

When ``admin_refresh.refresher_on()`` this is the only door page handlers use
for prices. It never fetches: it reads the cache and the in-flight marks, and
the Refresh control only enqueues work for the refresher process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from swingbot.core.db.repositories import market_refresh
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session
from swingbot.core.marketdata.shared import admin_refresh, kinds
from swingbot.core.marketdata.shared.kinds import DataKind, Entry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: Optional[float]
    as_of: Optional[str]
    age_s: Optional[float]
    refreshing: bool
    error: Optional[str]
    source: Optional[str] = None


def _upper_unique(symbols: Iterable[str]) -> list[str]:
    cleaned = (str(s).upper().strip() for s in symbols if s)
    return list(dict.fromkeys(s for s in cleaned if s))


def _cached(kind: DataKind, symbols: list[str]) -> dict[str, Entry]:
    from swingbot.core.marketdata.shared import layer
    return layer.last_cached(kind, symbols) if symbols else {}


def _doc_as_of(entry: Entry) -> datetime:
    doc = entry.value if isinstance(entry.value, dict) else {}
    raw = doc.get("trade_at") or doc.get("quote_at")
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            pass
    return entry.fetched_at


def _quote(symbol: str, entry: Optional[Entry], in_flight: set[str],
           error: Optional[str], now: datetime) -> MarketQuote:
    refreshing = admin_refresh.quote_mark_key(symbol) in in_flight
    if entry is None:
        return MarketQuote(symbol, None, None, None, True, error)
    doc = entry.value if isinstance(entry.value, dict) else {}
    price = doc.get("price")
    price = float(price) if price is not None and float(price) > 0 else None
    as_of = _doc_as_of(entry)
    return MarketQuote(symbol, price, as_of.isoformat(),
                       max(0.0, (now - as_of).total_seconds()),
                       refreshing, error, entry.source)


def _marks(keys: list[str]) -> tuple[set[str], dict[str, str]]:
    if not keys:
        return set(), {}
    try:
        repo = market_refresh.refresh_mark_repo()
        return set(repo.active(keys, now=datetime.now(timezone.utc))), dict(repo.errors(keys))
    except Exception as exc:  # noqa: BLE001 - fail open: the page renders without marks
        swallowed(log, "admin.market_values.marks", exc, "refresh marks unreadable: %s", exc)
        return set(), {}


def _due(wanted: list[str], entries: dict[str, Entry], quotes: dict[str, MarketQuote],
         now: datetime) -> tuple[list[str], int]:
    """Symbols to enqueue and their priority."""
    if kinds.is_fresh_request():
        return list(wanted), admin_refresh.PRIORITY_FRESH_HINT
    limit = admin_refresh.stale_after_s("price", session.session_state())
    due = []
    for sym in wanted:
        entry = entries.get(sym)
        if entry is None:
            due.append(sym)
        elif limit is not None and entry.age_s(now) > limit and not quotes[sym].refreshing:
            due.append(sym)
    return due, admin_refresh.PRIORITY_MISSING


def _enqueue(kind: str, keys: list[str], priority: int) -> None:
    if not keys:
        return
    try:
        market_refresh.refresh_queue_repo().enqueue(kind, keys, priority=priority)
    except Exception as exc:  # noqa: BLE001 - a failed enqueue never fails the page
        swallowed(log, "admin.market_values.enqueue", exc, "refresh enqueue failed: %s", exc)


def read_quotes(symbols: Iterable[str], *, kind: DataKind = DataKind.QUOTE,
                enqueue: bool = True,
                now: Optional[datetime] = None) -> dict[str, MarketQuote]:
    now = now or datetime.now(timezone.utc)
    wanted = _upper_unique(symbols)
    entries = _cached(kind, wanted)
    in_flight, errors = _marks([admin_refresh.quote_mark_key(s) for s in wanted])
    quotes = {s: _quote(s, entries.get(s), in_flight,
                        errors.get(admin_refresh.quote_mark_key(s)), now)
              for s in wanted}
    if enqueue:
        due, priority = _due(wanted, entries, quotes, now)
        _enqueue(admin_refresh.QUEUE_KIND_QUOTE, due, priority)
    return quotes


def quote_fields(quote: Optional[MarketQuote]) -> dict:
    if quote is None:
        return {"current_price": None, "current_price_stale": False, "price_as_of": None,
                "price_age_s": None, "price_refreshing": False, "price_error": None}
    limit = admin_refresh.stale_after_s("price", session.session_state())
    stale = bool(limit is not None and quote.age_s is not None and quote.age_s > limit)
    return {"current_price": quote.price, "current_price_stale": stale,
            "price_as_of": quote.as_of,
            "price_age_s": round(quote.age_s, 1) if quote.age_s is not None else None,
            "price_refreshing": quote.refreshing, "price_error": quote.error}


def _meta(**overrides) -> dict:
    meta = {"as_of": None, "refreshing": False, "stale_count": 0, "missing_count": 0,
            "incomplete": False, "computed_at": None, "stale_inputs": False,
            "source": "request", "error": None}
    meta.update(overrides)
    return meta


def _stale_count(priced: list[MarketQuote]) -> int:
    limit = admin_refresh.stale_after_s("price", session.session_state())
    return 0 if limit is None else sum(1 for q in priced if (q.age_s or 0) > limit)


def total_meta(quotes: Iterable[Optional[MarketQuote]], *, extra_missing: int = 0) -> dict:
    items = list(quotes)
    priced = [q for q in items if q is not None and q.price is not None]
    stale = _stale_count(priced)
    missing = (len(items) - len(priced)) + extra_missing
    return _meta(
        as_of=min((q.as_of for q in priced), default=None),
        refreshing=any(q is not None and q.refreshing for q in items),
        stale_count=stale, missing_count=missing, incomplete=missing > 0,
        error=next((q.error for q in items if q is not None and q.error), None))


def request_refresh(symbols: Iterable[str], *,
                    priority: int = admin_refresh.PRIORITY_USER) -> int:
    wanted = _upper_unique(symbols)
    if not wanted:
        return 0
    return market_refresh.refresh_queue_repo().enqueue(
        admin_refresh.QUEUE_KIND_QUOTE, wanted, priority=priority)
