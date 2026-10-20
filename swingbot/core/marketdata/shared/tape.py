"""v171 D7: the index tape on the shared layer.

The bot's ``tape_feed`` loop refreshes the fixed tape (``TAPE_FIXED``) plus any
proxied symbol the admin asked for in the last ``DEMAND_TTL_S``, once a minute in
session, into ``DataKind.INDEX_QUOTE`` rows. The admin reads them with
``read_tape`` and never fetches while the copy is fresh.

A row is a Yahoo level and change %, or, when Yahoo is blank for that symbol,
the change % of its ETF proxy from ``TAPE_PROXY_SYMBOLS`` (``is_proxy`` set,
``price`` None: a proxy never stands in for a level). A symbol blank everywhere
is a miss, never written, so the last good value stays and its age grows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from swingbot import config
from swingbot.core.db.repositories.market_shared import market_shared_repo
from swingbot.core.db.side_engine import side_connection
from swingbot.core.market.session import market_today
from swingbot.core.marketdata import data, yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import (
    PROVIDER_YF, Asker, DataKind, Entry, cache_key)

TAPE_FIXED = ("^GSPC", "^NDX", "^DJI", "^VIX")
DEMAND_TTL_S = 15 * 60
DEMAND_KEY = cache_key(DataKind.INDEX_QUOTE, "tape-demand")
_DEMAND_RESTAMP_S = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TapeEntry:
    symbol: str
    price: Optional[float]
    change_pct: Optional[float]
    is_proxy: bool
    proxy_symbol: Optional[str]
    as_of: Optional[datetime]


# -- symbols ---------------------------------------------------------------------


def proxy_map() -> dict[str, str]:
    """``TAPE_PROXY_SYMBOLS`` as ``{symbol: proxy}``; each entry splits on its last ``=``."""
    out: dict[str, str] = {}
    for item in str(getattr(config, "TAPE_PROXY_SYMBOLS", "") or "").split(","):
        symbol, sep, proxy = item.strip().rpartition("=")
        if sep and symbol.strip() and proxy.strip():
            out[symbol.strip().upper()] = proxy.strip().upper()
    return out


def is_tape_symbol(symbol: str) -> bool:
    sym = symbol.upper()
    return sym in TAPE_FIXED or sym in proxy_map()


def _tape_only(symbols) -> list[str]:
    return [s for s in dict.fromkeys(s.upper() for s in symbols) if is_tape_symbol(s)]


# -- demand ledger ---------------------------------------------------------------


def _read_demand(conn) -> dict[str, str]:
    row = market_shared_repo().read_entries([DEMAND_KEY], conn=conn).get(DEMAND_KEY)
    value = (row or {}).get("value")
    return dict(value) if isinstance(value, dict) else {}


def _age_s(stamp, now: datetime) -> float | None:
    try:
        return (now - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return None


def _live_demand(stamps: dict[str, str], now: datetime) -> dict[str, str]:
    """Entries younger than ``DEMAND_TTL_S``, order kept."""
    return {s: t for s, t in stamps.items()
            if (age := _age_s(t, now)) is not None and age < DEMAND_TTL_S}


def _needs_stamp(stamps: dict[str, str], symbol: str, now: datetime) -> bool:
    age = _age_s(stamps.get(symbol), now)
    return age is None or age > _DEMAND_RESTAMP_S


def record_demand(symbols: list[str]) -> None:
    """Note that the admin shows these proxied symbols; restamped at most once a minute each."""
    wanted = [s for s in _tape_only(symbols) if s not in TAPE_FIXED]
    if not wanted or config.MARKETDATA_LAYER != "on":
        return
    try:
        now = _now()
        with side_connection() as conn:
            stamps = _live_demand(_read_demand(conn), now)
            if not any(_needs_stamp(stamps, s, now) for s in wanted):
                return
            stamps.update({s: now.isoformat() for s in wanted})
            market_shared_repo().write_entries([{
                "key": DEMAND_KEY, "kind": DataKind.INDEX_QUOTE.value, "symbol": "TAPE-DEMAND",
                "fetched_at": now, "source": "admin", "value": stamps}], conn=conn)
    except Exception as exc:  # noqa: BLE001 - demand is best effort
        counters.warn_fail_open("tape-demand", exc)


def demanded_symbols(now: datetime) -> list[str]:
    """``TAPE_FIXED`` plus live demand that is still a tape symbol; ``TAPE_FIXED`` on any error."""
    fixed = list(TAPE_FIXED)
    if config.MARKETDATA_LAYER != "on":
        return fixed
    try:
        with side_connection() as conn:
            stamps = _live_demand(_read_demand(conn), now)
    except Exception as exc:  # noqa: BLE001 - the fixed tape still refreshes
        counters.warn_fail_open("tape-demand", exc)
        return fixed
    extra = [s for s in stamps if s not in TAPE_FIXED and is_tape_symbol(s)]
    return list(dict.fromkeys(fixed + extra))


# -- refresh and read ------------------------------------------------------------


def _entry(symbol: str, e: Entry) -> TapeEntry:
    doc = e.value if isinstance(e.value, dict) else {}
    return TapeEntry(symbol, doc.get("price"), doc.get("change_pct"), bool(doc.get("is_proxy")),
                     doc.get("proxy_symbol"), e.fetched_at)


def refresh_tape(symbols: list[str], *, asker: Asker = Asker.BACKGROUND,
                 max_age_s: float | None = None) -> dict[str, TapeEntry]:
    """One shared ``INDEX_QUOTE`` fetch for the tape symbols among ``symbols``."""
    syms = _tape_only(symbols)
    if not syms:
        return {}
    with router.asker_scope(asker):
        got = layer.get(DataKind.INDEX_QUOTE, syms, _fetch_tape, asker=asker,
                        provider=PROVIDER_YF, max_age_s=max_age_s)
    return {s: _entry(s, e) for s, e in got.items()}


def read_tape(symbols: list[str]) -> dict[str, TapeEntry]:
    """The last stored tape rows of any age; never fetches."""
    syms = _tape_only(symbols)
    if not syms:
        return {}
    return {s: _entry(s, e) for s, e in layer.last_cached(DataKind.INDEX_QUOTE, syms).items()}


# -- provider function (runs inside layer.get) -----------------------------------


def _valid_closes(series) -> list[float]:
    out = []
    for v in series.tolist():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isnan(f):
            out.append(f)
    return out


def _close_series(raw, symbol: str):
    columns = getattr(raw, "columns", None)
    if columns is None or raw.empty:
        return None
    if getattr(columns, "nlevels", 1) > 1:
        return raw[(symbol, "Close")] if (symbol, "Close") in columns else None
    return raw["Close"] if "Close" in columns else None


def _close_pair(raw, symbol: str) -> tuple[float, float] | None:
    """The last two non-NaN closes ``(prev, last)``, both positive."""
    series = _close_series(raw, symbol)
    if series is None:
        return None
    closes = _valid_closes(series)
    if len(closes) < 2 or closes[-2] <= 0 or closes[-1] <= 0:
        return None
    return closes[-2], closes[-1]


def _change(prev: float, last: float) -> float:
    return round((last / prev - 1) * 100, 2)


def _yahoo_docs(symbols: list[str]) -> dict[str, dict]:
    """Yahoo level + change % per symbol with two closes; ``BudgetDeferred`` propagates."""
    try:
        raw = yf_safe.download(" ".join(symbols), period="5d", interval="1d", group_by="ticker",
                               auto_adjust=False, progress=False)
    except yf_safe.BudgetDeferred:
        raise
    except Exception:  # noqa: BLE001 - DownloadBusy or a Yahoo error: every symbol blank
        return {}
    out = {}
    for symbol in symbols:
        pair = _close_pair(raw, symbol)
        if pair is not None:
            out[symbol] = {"symbol": symbol, "price": pair[1], "change_pct": _change(*pair),
                           "is_proxy": False, "proxy_symbol": None}
    return out


def _prev_close(frame) -> float | None:
    """The last close dated before the market's today."""
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame.columns:
        return None
    today = market_today()
    before = frame[[ts.date() < today for ts in frame.index]]
    closes = _valid_closes(before["Close"])
    return closes[-1] if closes and closes[-1] > 0 else None


def _quote_price(quote) -> float | None:
    if quote is None:
        return None
    price = quote.price if quote.price is not None else quote.mid()
    return price if price is not None and price > 0 else None


def _proxy_changes(symbols: list[str]) -> dict[str, tuple[str, float]]:
    """``{symbol: (proxy, change %)}`` for symbols whose proxy has a price and a prior close."""
    proxies = proxy_map()
    wanted = {s: proxies[s] for s in symbols if s in proxies}
    if not wanted:
        return {}
    tickers = list(dict.fromkeys(wanted.values()))
    quotes = data.get_quote_batch(tickers, asker=router.current_asker()) or {}
    frames = data.get_daily_data_batch(tickers, period="5d") or {}
    out = {}
    for symbol, proxy in wanted.items():
        price, prev = _quote_price(quotes.get(proxy)), _prev_close(frames.get(proxy))
        if price is not None and prev is not None:
            out[symbol] = (proxy, _change(prev, price))
    return out


def _fetch_tape(symbols) -> dict[str, dict | None]:
    """Provider function for ``layer.get``: Yahoo first, labelled proxy change % for blanks."""
    symbols = list(symbols)
    docs: dict[str, dict | None] = dict(_yahoo_docs(symbols))
    blank = [s for s in symbols if s not in docs]
    for symbol, (proxy, change) in _proxy_changes(blank).items():
        docs[symbol] = {"symbol": symbol, "price": None, "change_pct": change,
                        "is_proxy": True, "proxy_symbol": proxy}
    return {s: docs.get(s) for s in symbols}
