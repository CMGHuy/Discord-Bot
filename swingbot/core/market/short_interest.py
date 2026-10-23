"""v183 squeeze-notice cache: short interest and dividend facts per ticker.

The alert path only ever calls ``cached_short_interest`` and
``request_refresh``; only the daily loop calls ``fetch_short_interest``
(yfinance ``.info`` via the shared layer, network). Nothing here feeds a filter, a score or a
backtest, and a missing field stays ``None`` -- never a comfortable 0.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

CACHE_NAME = "short_interest.json"
QUEUE_NAME = "short_interest_queue.json"
STALE_DAYS = 21

#: The yfinance ``.info`` keys ``parse_info`` reads -- all the layer fetches and caches.
INFO_KEYS = ("shortPercentOfFloat", "sharesShort", "floatShares", "shortRatio",
             "dateShortInterest", "exDividendDate", "lastDividendDate", "lastDividendValue")
INFO_VARIANT = "short_interest"

_QUEUE_LOCK = threading.Lock()


class ShortInterestCacheError(Exception):
    """The cache file exists but cannot be read as a symbol map."""


class ShortInterestUnavailable(Exception):
    """The shared layer had no value for a ticker (budget-deferred or failed)."""


def _path(name: str) -> str:
    return os.path.join(config.DATA_DIR, name)


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _epoch_date(value) -> str | None:
    num = _num(value)
    if num is None:
        return None
    try:
        return dt.datetime.fromtimestamp(num, dt.timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _short_pct(info: dict) -> float | None:
    frac = _num(info.get("shortPercentOfFloat"))
    if frac is None:
        shares, flt = _num(info.get("sharesShort")), _num(info.get("floatShares"))
        if shares is None or flt is None:
            return None
        frac = shares / flt
    return round(frac * 100, 1)


def _div_estimated(ex_div: str | None, last_div: str | None, today: dt.date) -> bool:
    return ex_div is not None and ex_div >= today.isoformat() and last_div != ex_div


def _round1(value) -> float | None:
    num = _num(value)
    return None if num is None else round(num, 1)


def parse_info(info: dict, *, today: dt.date) -> dict:
    ex_div = _epoch_date(info.get("exDividendDate"))
    last_div = _epoch_date(info.get("lastDividendDate"))
    return {
        "short_pct_float": _short_pct(info),
        "days_to_cover": _round1(info.get("shortRatio")),
        "float_shares": _num(info.get("floatShares")),
        "si_date": _epoch_date(info.get("dateShortInterest")),
        "ex_div_date": ex_div,
        "div_per_share": _num(info.get("lastDividendValue")),
        "div_estimated": _div_estimated(ex_div, last_div, today),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def fetch_short_interest(ticker) -> dict:
    """One ticker's facts through the shared market-data layer (v171 D1): the
    layer's yfinance provider function reads just ``INFO_KEYS``. ``fetched_at``
    is when the value was fetched -- a budget-deferred call may serve an older one."""
    from swingbot.core.marketdata import data
    entry = data.get_info_fields(ticker, INFO_KEYS, variant=INFO_VARIANT)
    if entry is None:
        raise ShortInterestUnavailable(f"{ticker}: no short-interest answer from the layer")
    parsed = parse_info(entry.value or {}, today=dt.date.today())
    parsed["fetched_at"] = entry.fetched_at.isoformat()
    return parsed


def _read_cache() -> dict:
    try:
        with open(_path(CACHE_NAME), encoding="utf-8") as fh:
            body = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ShortInterestCacheError(str(exc)) from exc
    if not isinstance(body, dict):
        raise ShortInterestCacheError("short-interest cache is not an object")
    return body


def _clean(symbols) -> list[str]:
    return sorted({str(s).strip().upper() for s in symbols if str(s).strip()})


def _existing_entries() -> dict:
    try:
        entries = _read_cache().get("symbols", {})
    except ShortInterestCacheError as exc:
        log.warning("short-interest cache unreadable, rebuilding: %s", exc, exc_info=True)
        return {}
    return dict(entries) if isinstance(entries, dict) else {}


def _fetch_all(symbols: list[str], fetch) -> list[tuple[str, dict | None]]:
    def one(sym):
        try:
            return sym, fetch(sym)
        except Exception as exc:  # one bad ticker never stops the batch
            swallowed(log, "marketdata.short_interest.fetch", exc, level=logging.DEBUG)
            return sym, None

    with ThreadPoolExecutor(max_workers=4) as pool:   # Yahoo rate-limits .info
        return list(pool.map(one, symbols))


def _drop_from_queue(done: list[str]) -> None:
    with _QUEUE_LOCK:
        queue = read_json(_path(QUEUE_NAME), [])
        if not isinstance(queue, list):
            queue = []
        atomic_write_json(_path(QUEUE_NAME), [s for s in queue if s not in set(done)])


def refresh_short_interest(symbols, *, now=None, fetch=None) -> dict:
    fetch = fetch or fetch_short_interest
    now = now or dt.datetime.now(dt.timezone.utc)
    entries = _existing_entries()
    updated, failed = [], []
    for sym, result in _fetch_all(_clean(symbols), fetch):
        if result is None:
            failed.append(sym)
        else:
            entries[sym] = result
            updated.append(sym)
    atomic_write_json(_path(CACHE_NAME), {"updated_at": now.isoformat(), "symbols": entries})
    _drop_from_queue(updated)
    return {"updated": len(updated), "failed": sorted(failed)}


def cached_short_interest(ticker) -> dict | None:
    entry = _read_cache().get("symbols", {}).get(str(ticker).upper().strip())
    return entry if isinstance(entry, dict) else None


def request_refresh(ticker) -> None:
    try:
        with _QUEUE_LOCK:
            queue = read_json(_path(QUEUE_NAME), [])
            if not isinstance(queue, list):
                queue = []
            atomic_write_json(_path(QUEUE_NAME), sorted(set(queue) | {str(ticker).strip().upper()}))
    except Exception as exc:
        swallowed(log, "marketdata.short_interest.queue", exc, level=logging.DEBUG)


def _watchlist() -> list[str]:
    from swingbot.core.marketdata.watchlist import load_watchlist
    return list(load_watchlist())


def _short_universe(today: dt.date) -> list[str]:
    from swingbot.core.marketdata import universe
    snap = universe.short_snapshot(today.isoformat(), live=True)
    return [] if snap is None else list(snap.symbols)


def _open_short_tickers() -> list[str]:
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.trade_log import TradeLog
    rows = list(PlanStore().open_plans()) + list(TradeLog().get_trades(status="open", limit=None))
    return [t for t in (_bearish_ticker(r) for r in rows) if t]


def _bearish_ticker(row) -> str | None:
    get = row.get if isinstance(row, dict) else lambda k: getattr(row, k, None)
    return get("ticker") if get("direction") == "bearish" else None


def _queued() -> list[str]:
    queue = read_json(_path(QUEUE_NAME), [])
    return list(queue) if isinstance(queue, list) else []


def refresh_symbols() -> list[str]:
    today = dt.date.today()
    sources = (_watchlist, lambda: _short_universe(today), _open_short_tickers, _queued)
    out: list[str] = []
    for source in sources:
        try:
            out.extend(source())
        except Exception as exc:
            swallowed(log, "marketdata.short_interest.source", exc,
                      "short-interest source failed: %s", exc, exc_info=True)
    return _clean(out)
