"""v106 router: Alpaca first for eligible US symbols, yfinance for the rest
and for every Alpaca miss -- per symbol, never per batch. The yfinance path is
injected as `yf_fetch` (today's code, unchanged), so with ALPACA_ENABLED off
this module is a pass-through that only adds source tags.

Config is read at call time; the provider is cached per (key_id, secret) so
rotated keys take effect on the next call in any process -- the admin
container has no on_config_reload hook."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from swingbot import config
from swingbot.core.infra.logsetup import with_current_context
from swingbot.core.marketdata import spot_metals
from swingbot.core.marketdata.providers.alpaca_provider import (
    AlpacaAuthError, AlpacaMiss, AlpacaProvider, symbols_per_request)
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_SPOT, SOURCE_YF, is_alpaca_eligible)

log = logging.getLogger(__name__)
_provider_factory = AlpacaProvider
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alpaca")
_lock = threading.Lock()


class _Bucket:
    def __init__(self, per_minute=150):
        self.capacity = float(per_minute)
        self.tokens = float(per_minute)
        self.refill_per_s = per_minute / 60.0
        self.stamp = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.refill_per_s)
        self.stamp = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class _Breaker:
    def __init__(self):
        self.fails, self.open_until, self.auth_latched = 0, 0.0, False

    def allows(self) -> bool:
        return not self.auth_latched and time.monotonic() >= self.open_until

    def record(self, ok: bool, auth: bool = False) -> None:
        was_open = not self.allows()
        if ok:
            self.fails = 0
        else:
            self.fails += 1
            self.auth_latched = self.auth_latched or auth
            if self.fails >= int(config.ALPACA_BREAKER_FAILURES):
                self.open_until = time.monotonic() + float(config.ALPACA_BREAKER_COOLDOWN_SECONDS)
        if was_open != (not self.allows()):
            log.warning("Alpaca breaker %s", "OPEN" if not self.allows() else "closed")


_bucket = _Bucket()
_breaker = _Breaker()
_provider = None
_provider_key = None
_last_source: dict = {}
_spot_miss: dict = {}
_stats = {"alpaca": 0, "yfinance": 0, "fallback": 0, "failures": 0}


def reset() -> None:
    global _provider, _provider_key, _bucket, _breaker
    _provider, _provider_key = None, None
    _bucket, _breaker = _Bucket(), _Breaker()
    _last_source.clear()
    _spot_miss.clear()
    for k in _stats:
        _stats[k] = 0


def _active_provider():
    global _provider, _provider_key, _breaker
    if not config.ALPACA_ENABLED or not config.ALPACA_API_KEY_ID:
        return None
    key = (config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY)
    with _lock:
        if key != _provider_key:
            _provider = _provider_factory(key[0], key[1], config.ALPACA_DATA_FEED_LIVE)
            _provider_key, _breaker = key, _Breaker()
    return _provider if _breaker.allows() else None


def _collect(future, method: str, deadline: float):
    """Result of one submitted call before `deadline` (monotonic), else None.
    Records the breaker/stats outcome; runs in the calling thread."""
    try:
        result = future.result(timeout=max(0.0, deadline - time.monotonic()))
    except (AlpacaMiss, FutureTimeout, Exception) as exc:
        _stats["failures"] += 1
        _breaker.record(False, auth=isinstance(exc, AlpacaAuthError))
        log.info("Alpaca %s miss: %s", method, str(exc) or type(exc).__name__)
        return None
    _breaker.record(True)
    return result


def _attempt(method: str, *args):
    """One bounded Alpaca call. Returns its result, or None on any miss."""
    prov = _active_provider()
    if prov is None or not _bucket.take():
        return None
    deadline = time.monotonic() + float(config.ALPACA_TIMEOUT_SECONDS)
    return _collect(_pool.submit(with_current_context(getattr(prov, method)), *args), method, deadline)


def _attempt_many(method: str, batches: list, *args) -> list:
    """One result per batch (None on miss), all in flight together under one
    shared deadline. A batch without a bucket token is not submitted."""
    prov = _active_provider()
    if prov is None:
        return [None] * len(batches)
    deadline = time.monotonic() + float(config.ALPACA_TIMEOUT_SECONDS)
    futures = [_pool.submit(with_current_context(getattr(prov, method)), b, *args) if _bucket.take() else None
               for b in batches]
    return [_collect(f, method, deadline) if f is not None else None for f in futures]


def _split(tickers):
    """(Alpaca-bound, yfinance-bound). Disabled or breaker-open means every
    ticker is plain yfinance -- tagged SOURCE_YF, never SOURCE_FALLBACK."""
    if _active_provider() is None:
        return [], list(tickers)
    wanted = [t for t in tickers if is_alpaca_eligible(t)]
    chosen = set(wanted)
    return wanted, [t for t in tickers if t not in chosen]


def _tag(frames: dict, source: str) -> dict:
    for df in frames.values():
        df.attrs["source"] = source
    return frames


def _log_fallback(kind: str, symbols) -> None:
    """DEBUG line for Alpaca-eligible symbols served by yfinance instead."""
    if symbols:
        log.debug("Alpaca %s fallback to yfinance for %d symbol(s): %s",
                  kind, len(symbols), ", ".join(list(symbols)[:10]))


def _merge(alpaca: dict, rest: list, misses: list, fetch) -> dict:
    out = _tag(dict(alpaca), SOURCE_ALPACA)
    out.update(_tag(fetch(rest), SOURCE_YF) if rest else {})
    out.update(_tag(fetch(misses), SOURCE_FALLBACK) if misses else {})
    _stats["alpaca"] += len(alpaca)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    return out


def _scaled_or_miss(ticker, raw):
    """v109: one spot symbol's scaled frame, or None with the reason recorded
    for spot_miss_reason() (the scan crawl reads it back in its worker)."""
    df, reason = spot_metals.scale_underlying(ticker, raw)
    key = str(ticker).upper().strip()
    if df is None:
        _spot_miss[key] = reason
        log.info("%s: no spot-scaled bars (%s)", key, reason)
    else:
        _spot_miss.pop(key, None)
    return df


def _spot_daily(spot, have: dict, fetch) -> dict:
    """v109: spot symbols are never sent to Alpaca or to yfinance under their
    own name -- their future is fetched under ITS name (reusing a frame this
    call already has) and rescaled by the live spot ratio."""
    if not spot:
        return {}
    unders = list(dict.fromkeys(spot_metals.underlying(t) for t in spot))
    need = [u for u in unders if u not in have]
    raw = {**have, **(fetch(need) if need else {})}
    scaled = {t: _scaled_or_miss(t, raw.get(spot_metals.underlying(t))) for t in spot}
    return {t: df for t, df in scaled.items() if df is not None}


def _spot_prices(spot) -> dict:
    """v109: a spot symbol's live price is its spot quote -- or nothing."""
    out = {}
    for ticker in spot:
        quote, reason = spot_metals.quote_with_reason(ticker)
        if quote is None:
            _spot_miss[str(ticker).upper().strip()] = reason
            continue
        out[ticker] = quote.price
        _last_source[ticker] = SOURCE_SPOT
    return out


def daily_bars(tickers, period, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    n = symbols_per_request(period)
    batches = [wanted[i:i + n] for i in range(0, len(wanted), n)]
    got = {}
    for part in _attempt_many("daily_bars", batches, period):
        got.update(part or {})
    misses = [t for t in wanted if t not in got]
    _log_fallback("daily_bars", misses)
    out = _merge(got, rest, misses, lambda ts: yf_fetch(ts, period))
    out.update(_spot_daily(spot, out, lambda ts: yf_fetch(ts, period)))
    return out


def latest_prices(tickers, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got = (_attempt("latest_prices", wanted,
                    int(config.ALPACA_MAX_TRADE_AGE_SECONDS)) or {}) if wanted else {}
    misses = [t for t in wanted if t not in got]
    _log_fallback("latest_prices", misses)
    out = dict(got)
    for group, source in ((rest, SOURCE_YF), (misses, SOURCE_FALLBACK)):
        fetched = yf_fetch(group) if group else {}
        out.update(fetched)
        _last_source.update({t: source for t in fetched})
    _last_source.update({t: SOURCE_ALPACA for t in got})
    _stats["alpaca"] += len(got)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    out.update(_spot_prices(spot))
    return out


def intraday_bars(ticker, interval, yf_fetch):
    if spot_metals.is_spot_metal(ticker):
        # v109: the future's bars under its own name, rescaled -- never the
        # spot symbol itself, never unscaled.
        return _scaled_or_miss(
            ticker, intraday_bars(spot_metals.underlying(ticker), interval, yf_fetch))
    # Only 1h is served by Alpaca; any other interval is plain yfinance,
    # not a fallback.
    if interval != "1h" or not is_alpaca_eligible(ticker) or _active_provider() is None:
        df = yf_fetch(ticker, interval)
        source = SOURCE_YF
    else:
        df = _attempt("intraday_bars", ticker, interval)
        source = SOURCE_ALPACA
        if df is None or df.empty:
            _log_fallback("intraday_bars", [ticker])
            df, source = yf_fetch(ticker, interval), SOURCE_FALLBACK
    if df is not None:
        df.attrs["source"] = source
    return df


def last_source(ticker: str):
    return _last_source.get(str(ticker).upper().strip())


def spot_miss_reason(ticker: str):
    """v109: why this process last served a spot symbol no frame/price, or None."""
    return _spot_miss.get(str(ticker).upper().strip())


def stats() -> dict:
    return {**_stats, "enabled": bool(config.ALPACA_ENABLED),
            "breaker_open": not _breaker.allows()}
