"""v201: the request-path door for market values.

When ``admin_refresh.refresher_on()`` this is the only door page handlers use
for prices. It never fetches: it reads the cache and the in-flight marks, and
the Refresh control only enqueues work for the refresher process. v204 adds
snapshot reads, which never build.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from swingbot.core.db.repositories import admin_snapshots as snapshot_store
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
        swallowed(log, "ops.admin.market_values.marks", exc, "refresh marks unreadable: %s", exc)
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
        swallowed(log, "ops.admin.market_values.enqueue", exc, "refresh enqueue failed: %s", exc)


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


def last_close_fields(symbols: Iterable[str]) -> dict[str, dict]:
    """{SYMBOL: {"last_close", "last_close_date"}} from the cached daily bars, for
    rows with no live quote. A greyed last-known price beats an empty cell, but it
    is shown as a close with its date, never as a live price, and nothing derived
    (P&L, status bar) is computed from it. Reads the file cache only; a symbol with
    no bars, or a cache that is not mounted, is simply absent."""
    wanted = _upper_unique(symbols)
    if not wanted:
        return {}
    from swingbot.core.marketdata import daily_readonly
    try:
        frames = daily_readonly.read_cached_daily(wanted, period="6mo").frames
    except Exception as exc:  # noqa: BLE001 - the page renders without a last close
        swallowed(log, "ops.admin.market_values.last_close", exc, "last close unreadable: %s", exc)
        return {}
    out: dict[str, dict] = {}
    for sym, df in frames.items():
        try:
            close = float(df["Close"].iloc[-1])
            stamp = df.index[-1]
            day = stamp.date().isoformat() if hasattr(stamp, "date") else str(stamp)[:10]
        except Exception:  # noqa: BLE001 - one malformed frame never hides the others
            continue
        if close > 0:
            out[sym] = {"last_close": close, "last_close_date": day}
    return out


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


def _snapshot_row(key: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        return snapshot_store.admin_snapshot_repo().read(key), None
    except Exception as exc:  # noqa: BLE001 - fail open: the page renders without the row
        swallowed(log, "ops.admin.market_values.snapshot_read", exc, "snapshot read failed: %s", exc)
        return None, "snapshot store unavailable"


def _snapshot_stale(computed_at: datetime, now: datetime) -> bool:
    limit = admin_refresh.stale_after_s("snapshot", session.session_state())
    if limit is None:
        return computed_at < session.last_regular_close(now)
    return (now - computed_at).total_seconds() > limit


def _snapshot_priority(row: Optional[dict], in_flight: bool, now: datetime) -> Optional[int]:
    if kinds.is_fresh_request():
        return admin_refresh.PRIORITY_FRESH_HINT
    if row is None:
        return admin_refresh.PRIORITY_MISSING
    if not in_flight and _snapshot_stale(row["computed_at"], now):
        return admin_refresh.PRIORITY_MISSING
    return None


def read_snapshot(key: str, *, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    mark = admin_refresh.snapshot_mark_key(key)
    row, read_error = _snapshot_row(key)
    active, errors = _marks([mark])
    in_flight = mark in active
    priority = _snapshot_priority(row, in_flight, now)
    if priority is not None:
        _enqueue(admin_refresh.QUEUE_KIND_SNAPSHOT, [key], priority)
    computed_at = row["computed_at"] if row else None
    return {"key": key, "doc": row["doc"] if row else None,
            "inputs": row["inputs"] if row else None,
            "computed_at": computed_at.isoformat() if computed_at else None,
            "stale_inputs": bool(row["stale_inputs"]) if row else False,
            "refreshing": row is None or in_flight,
            "error": errors.get(mark) or read_error}


def _as_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _oldest_as_of(*values: Optional[str]) -> Optional[str]:
    present = [v for v in values if v]
    return min(present, key=_as_utc) if present else None


def _missing_symbols(inputs: Optional[dict]) -> set[str]:
    missing = (inputs or {}).get("missing") or {}
    return (set(missing.get("quotes") or ()) | set(missing.get("fx") or ())
            | set(missing.get("bars") or ()))


def snapshot_meta(snap: dict, *, extra_missing: int = 0) -> dict:
    inputs = snap.get("inputs")
    count = len(_missing_symbols(inputs)) + extra_missing
    oldest = _oldest_as_of((inputs or {}).get("oldest_quote_as_of"),
                           (inputs or {}).get("oldest_fx_as_of"))
    return _meta(as_of=oldest or snap.get("computed_at"), refreshing=snap["refreshing"],
                 missing_count=count, incomplete=count > 0, computed_at=snap["computed_at"],
                 stale_inputs=snap["stale_inputs"], source="snapshot", error=snap["error"])


def request_refresh(symbols: Iterable[str], *, snapshots: Iterable[str] = (),
                    priority: int = admin_refresh.PRIORITY_USER) -> int:
    keys = list(dict.fromkeys(snapshots))
    unknown = [k for k in keys if not admin_refresh.is_snapshot_key(k)]
    if unknown:
        raise ValueError(f"unknown snapshot keys: {unknown}")
    wanted = _upper_unique(symbols)
    queue = market_refresh.refresh_queue_repo
    added = 0
    if wanted:
        added += queue().enqueue(admin_refresh.QUEUE_KIND_QUOTE, wanted, priority=priority)
    if keys:
        added += queue().enqueue(admin_refresh.QUEUE_KIND_SNAPSHOT, keys, priority=priority)
    return added
