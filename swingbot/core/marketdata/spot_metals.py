"""v109: spot gold/silver (XAUUSD / XAGUSD) as spot-priced instruments.

Yahoo has no spot metals series, so a spot symbol's bars are its COMEX
future's bars (GC=F / SI=F) rescaled by one live spot/futures ratio, and its
live price is gold-api.com's keyless spot quote. One constant multiplier
across a frame preserves every percentage distance, indicator crossing and
level ordering, so detection on XAUUSD equals detection on GC=F -- only the
price scale differs (tests/marketdata/test_spot_scaling_parity.py).

Cache rule (docs/claude/known-traps.md, two OHLCV caches): only the raw
futures frame is ever cached, under its own name (GC_F). A scaled frame is
computed on read and never written under XAUUSD -- it would freeze one day's
ratio into every later day's levels.
"""
import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot import config

log = logging.getLogger("swing-bot.spot_metals")

#: spot symbol -> (gold-api.com metal code, Yahoo futures symbol). The single
#: source of truth: another spot metal is one line here.
SPOT_PAIRS: dict[str, tuple[str, str]] = {
    "XAUUSD": ("XAU", "GC=F"),
    "XAGUSD": ("XAG", "SI=F"),
}
QUOTE_URL = "https://api.gold-api.com/price/{code}"
QUOTE_TIMEOUT_SECONDS = 10
#: Same TTL as data.py's _price_cache. Failures are cached too, so an outage
#: costs one blocking GET per 15 s rather than one per caller.
QUOTE_CACHE_TTL_SECONDS = 15

_quote_cache: dict = {}   # key -> (SpotQuote | None, fetched_at monotonic)
_failing: set = set()     # keys inside a failure streak (logged once)


@dataclass(frozen=True)
class SpotQuote:
    price: float
    updated_at: datetime   # aware, UTC


def _key(symbol) -> str:
    return str(symbol or "").upper().strip()


def is_spot_metal(symbol) -> bool:
    return _key(symbol) in SPOT_PAIRS


def underlying(symbol) -> str:
    """The Yahoo futures symbol a spot symbol's bars are scaled from.
    KeyError for a non-spot symbol."""
    return SPOT_PAIRS[_key(symbol)][1]


def cache_symbol(symbol: str) -> str:
    """What a cache writer stores for `symbol`: the underlying future for a
    spot symbol (the cache rule), else `symbol` unchanged."""
    key = _key(symbol)
    return SPOT_PAIRS[key][1] if key in SPOT_PAIRS else symbol


def cache_symbols(symbols) -> list:
    return list(dict.fromkeys(cache_symbol(s) for s in symbols))


def split_spot(tickers) -> tuple:
    """(spot symbols, everything else), each in input order."""
    tickers = list(tickers)
    return ([t for t in tickers if is_spot_metal(t)],
            [t for t in tickers if not is_spot_metal(t)])


def reset() -> None:
    """Tests only: forget cached quotes and failure streaks."""
    _quote_cache.clear()
    _failing.clear()


def _now_mono() -> float:
    return time.monotonic()


def _raw_get(url: str) -> str:
    """The HTTP GET, split out so tests never touch the network
    (marketdata/fmp_client.py's pattern)."""
    req = urllib.request.Request(url, headers={"User-Agent": "swingbot-spot/1.0"})
    with urllib.request.urlopen(req, timeout=QUOTE_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", "replace")


def _parse_quote(body: str):
    data = json.loads(body)
    price = float(data["price"])
    if price <= 0:
        return None
    updated = datetime.fromisoformat(str(data["updatedAt"]).replace("Z", "+00:00"))
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return SpotQuote(price, updated)


def _note_failure(key: str, why: str) -> None:
    if key not in _failing:
        _failing.add(key)
        log.warning("%s: spot quote unavailable (%s) -- not logged again until it recovers",
                    key, why)


def _note_success(key: str) -> None:
    if key in _failing:
        _failing.discard(key)
        log.info("%s: spot quote recovered", key)


def _fetch_quote(key: str):
    try:
        quote = _parse_quote(_raw_get(QUOTE_URL.format(code=SPOT_PAIRS[key][0])))
    except Exception as exc:
        _note_failure(key, f"{type(exc).__name__}: {exc}")
        return None
    if quote is None:
        _note_failure(key, "non-positive price")
        return None
    _note_success(key)
    return quote


def _cached_quote(key: str):
    now = _now_mono()
    hit = _quote_cache.get(key)
    if hit is not None and now - hit[1] < QUOTE_CACHE_TTL_SECONDS:
        return hit[0]
    quote = _fetch_quote(key)
    _quote_cache[key] = (quote, now)
    return quote


def quote_with_reason(symbol, *, now: datetime | None = None) -> tuple:
    """(SpotQuote, "") for a fresh quote, else (None, why). Stale is missing."""
    key = _key(symbol)
    if key not in SPOT_PAIRS:
        return None, f"{key} is not a spot metal"
    quote = _cached_quote(key)
    if quote is None:
        return None, "spot quote missing"
    age = ((now or datetime.now(timezone.utc)) - quote.updated_at).total_seconds()
    if age > float(config.SPOT_QUOTE_MAX_AGE_SECONDS):
        return None, f"spot quote stale ({age:.0f}s old)"
    return quote, ""


def spot_quote(symbol, *, now: datetime | None = None):
    """The fresh spot quote for a spot symbol, or None (missing, stale, not spot)."""
    return quote_with_reason(symbol, now=now)[0]
