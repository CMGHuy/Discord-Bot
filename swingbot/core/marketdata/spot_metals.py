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
from swingbot.core.marketdata.providers.base import SOURCE_SPOT_SCALED

log = logging.getLogger(__name__)

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


#: A reading outside this band is a bad quote or a contract-roll glitch, and
#: must not rescale a whole history.
RATIO_BAND = (0.95, 1.05)
_PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


@dataclass(frozen=True)
class SpotRatio:
    symbol: str
    spot: float
    underlying: str
    futures: float
    ratio: float


def _futures_price(symbol: str):
    """The future's live price, trading-grade (no stale last-good fallback).
    Imported here: data.py imports the router, which imports this module."""
    from swingbot.core.marketdata.data import get_current_price_batch
    return get_current_price_batch([symbol], allow_stale=False).get(symbol)


def spot_ratio_detail(symbol, *, now: datetime | None = None) -> tuple:
    """(SpotRatio, "") or (None, why). Missing/stale spot, a missing future
    price, or a ratio outside RATIO_BAND are all None."""
    quote, reason = quote_with_reason(symbol, now=now)
    if quote is None:
        return None, reason
    key = _key(symbol)
    under = SPOT_PAIRS[key][1]
    futures = _futures_price(under)
    if not futures or futures <= 0:
        return None, f"{under} live price unavailable"
    ratio = quote.price / float(futures)
    if not RATIO_BAND[0] <= ratio <= RATIO_BAND[1]:
        log.warning("%s: spot ratio %.5f (spot %.2f / %s %.2f) outside [%.2f, %.2f] -- rejected",
                    key, ratio, quote.price, under, futures, *RATIO_BAND)
        return None, f"ratio {ratio:.5f} outside [{RATIO_BAND[0]}, {RATIO_BAND[1]}]"
    return SpotRatio(key, quote.price, under, float(futures), ratio), ""


def spot_ratio(symbol, *, now: datetime | None = None):
    reading, _ = spot_ratio_detail(symbol, now=now)
    return reading.ratio if reading is not None else None


def scale_frame(df, reading: SpotRatio):
    """A copy of `df` with Open/High/Low/Close x reading.ratio. Volume and
    every other column (market-context columns included) are untouched.
    One constant multiplier: every % distance, crossing and ordering is
    preserved, and no bar reads anything but itself."""
    out = df.copy()
    cols = [c for c in _PRICE_COLUMNS if c in out.columns]
    out[cols] = out[cols] * reading.ratio
    out.attrs = {**df.attrs,
                 "source": f"{SOURCE_SPOT_SCALED}:{reading.underlying}",
                 "spot_ratio": reading.ratio, "spot_price": reading.spot,
                 "futures_price": reading.futures, "spot_underlying": reading.underlying}
    return out


def scale_underlying(symbol, raw) -> tuple:
    """(scaled frame, "") from the underlying's raw bars, or (None, why).
    Checks the bars first so an empty fetch costs no quote/price call."""
    under = underlying(symbol)
    if raw is None or raw.empty:
        return None, f"no {under} bars"
    reading, reason = spot_ratio_detail(symbol)
    if reading is None:
        return None, reason
    return scale_frame(raw, reading), ""
