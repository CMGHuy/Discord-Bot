"""v106 router: Alpaca first for eligible US symbols, yfinance for the rest
and for every Alpaca miss -- per symbol, never per batch. The yfinance path is
injected as `yf_fetch` (today's code, unchanged), so with ALPACA_ENABLED off
this module is a pass-through that only adds source tags.

Config is read at call time; the provider is cached per (key_id, secret) so
rotated keys take effect on the next call in any process -- the admin
container has no on_config_reload hook."""
import contextlib
import contextvars
import dataclasses
import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from swingbot import config
from swingbot.core.infra.logsetup import with_current_context
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import spot_metals
from swingbot.core.marketdata.providers.alpaca_provider import (
    ROWS_PER_PAGE, AlpacaAuthError, AlpacaMiss, AlpacaProvider, symbols_per_request)
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_SPOT, SOURCE_YF, is_alpaca_eligible)
from swingbot.core.marketdata.shared import budget
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, Asker, QuoteDetail

log = logging.getLogger(__name__)
_QUOTE_METHODS = frozenset({"latest_prices", "latest_quotes"})
_provider_factory = AlpacaProvider
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alpaca")
# Quotes get their own workers: a slow bulk-bars call must never starve the
# short-deadline quote path (a timed-out call keeps its worker until the SDK
# returns, so sharing one pool would silently push quotes onto yfinance).
_quote_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alpaca-quote")
_lock = threading.Lock()
#: v106 T13b: a spot symbol's future is fetched from yfinance here while the
#: Alpaca batches are in flight, instead of after them.
_side_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spot-side")


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


class _WarnGate:
    """At most one WARNING per `every` seconds (monotonic) for a persistent
    outage's per-call summary."""
    def __init__(self, every: float = 60.0):
        self.every, self.last = every, None

    def ready(self) -> bool:
        now = time.monotonic()
        if self.last is not None and now - self.last < self.every:
            return False
        self.last = now
        return True


class _NotSent(Exception):
    """A batch that never left (no rate-limit token) -- not an Alpaca failure."""


class DeadlineExpired(TimeoutError):
    """The shared call deadline passed before the provider returned."""


class _Breaker:
    def __init__(self):
        self.fails, self.open_until, self.auth_latched = 0, 0.0, False
        self.last_reason = ""

    def allows(self) -> bool:
        return not self.auth_latched and time.monotonic() >= self.open_until

    def record(self, ok: bool, auth: bool = False, reason: str = "") -> None:
        was_open = not self.allows()
        if ok:
            self.fails = 0
        else:
            self.fails += 1
            self.last_reason = reason or self.last_reason
            self.auth_latched = self.auth_latched or auth
            if self.fails >= int(config.ALPACA_BREAKER_FAILURES):
                self.open_until = time.monotonic() + float(config.ALPACA_BREAKER_COOLDOWN_SECONDS)
        if was_open != (not self.allows()):
            self._log_transition()

    def _log_transition(self) -> None:
        if self.allows():
            log.warning("Alpaca breaker closed")
        else:
            log.warning("Alpaca breaker OPEN (last miss: %s)", self.last_reason or "unknown")


_bucket = _Bucket()
_breaker = _Breaker()
_warn_gate = _WarnGate()
_provider = None
_provider_key = None
_last_source: dict = {}
_spot_miss: dict = {}
_stats = {"alpaca": 0, "yfinance": 0, "fallback": 0, "failures": 0}
_ASKER: contextvars.ContextVar = contextvars.ContextVar("marketdata_asker", default=Asker.SCAN)
#: v171: process-local memo of the shared breaker; at most one read per second.
_SHARED_BREAKER_MEMO_S = 1.0
_shared_breaker_memo: dict = {"stamp": None, "allows": True}


@contextlib.contextmanager
def asker_scope(asker: Asker):
    """Every provider call made inside runs at `asker`'s budget tier (D6)."""
    token = _ASKER.set(asker)
    try:
        yield
    finally:
        _ASKER.reset(token)


def current_asker() -> Asker:
    return _ASKER.get()


def _shared() -> bool:
    return config.MARKETDATA_LAYER == "on"


def _take_token() -> bool:
    """One token for one provider call: the shared budget in `on` mode,
    this process's bucket otherwise (pre-v171, unchanged)."""
    if not _shared():
        return _bucket.take()
    return budget.take(PROVIDER_ALPACA, current_asker())


def _shared_breaker_allows() -> bool:
    if not _shared():
        return True
    now = time.monotonic()
    stamp = _shared_breaker_memo["stamp"]
    if stamp is not None and now - stamp < _SHARED_BREAKER_MEMO_S:
        return _shared_breaker_memo["allows"]
    allows = budget.breaker_allows(PROVIDER_ALPACA)
    _shared_breaker_memo.update(stamp=now, allows=allows)
    return allows


def _record_verdict(ok: bool, auth: bool = False, reason: str = "") -> None:
    """The local breaker always; the shared one too in `on` mode."""
    _breaker.record(ok, auth=auth, reason=reason)
    if _shared():
        budget.breaker_record(PROVIDER_ALPACA, ok)
        _shared_breaker_memo["stamp"] = None


def reset() -> None:
    global _provider, _provider_key, _bucket, _breaker, _warn_gate
    _provider, _provider_key = None, None
    _bucket, _breaker, _warn_gate = _Bucket(), _Breaker(), _WarnGate()
    _last_source.clear()
    _spot_miss.clear()
    _shared_breaker_memo.update(stamp=None, allows=True)
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
    return _provider if _breaker.allows() and _shared_breaker_allows() else None


def _label(exc) -> str:
    """Log name of a failure: a deadline expiry reads as a timeout, a
    provider-raised error keeps its own type."""
    return "TimeoutError(deadline)" if isinstance(exc, DeadlineExpired) else type(exc).__name__


def _reason(exc) -> str:
    return f"{_label(exc)}: {exc}" if str(exc) else _label(exc)


def _wait(future, deadline: float):
    """(result, None) or (None, exc) for one submitted call, waiting at most
    until `deadline` (monotonic). No breaker/stat side effects."""
    try:
        return future.result(timeout=max(0.0, deadline - time.monotonic())), None
    except FutureTimeout as exc:
        if future.done():  # the provider itself raised a timeout before the deadline
            return None, exc
        return None, DeadlineExpired(str(exc) or "deadline expired")
    except Exception as exc:  # AlpacaMiss, anything the provider raised
        swallowed(log, "marketdata.router.wait", exc, level=logging.DEBUG)
        return None, exc


def _collect(future, method: str, deadline: float):
    """Single-call path: result of one submitted call before `deadline`, else
    None. Records the breaker/stats outcome; runs in the calling thread."""
    result, exc = _wait(future, deadline)
    if exc is not None:
        _stats["failures"] += 1
        _record_verdict(False, auth=isinstance(exc, AlpacaAuthError), reason=_reason(exc))
        log.debug("Alpaca %s miss: %s", method, str(exc) or type(exc).__name__)
        return None
    _record_verdict(True)
    return result


def _bars_timeout() -> float:
    return float(config.ALPACA_BARS_TIMEOUT_SECONDS)


def _attempt(method: str, *args, timeout: float = None):
    """One bounded Alpaca call. Returns its result, or None on any miss.
    `timeout` defaults to the quote deadline (ALPACA_TIMEOUT_SECONDS)."""
    prov = _active_provider()
    if prov is None or not _take_token():
        return None
    deadline = time.monotonic() + float(config.ALPACA_TIMEOUT_SECONDS if timeout is None else timeout)
    pool = _quote_pool if method in _QUOTE_METHODS else _pool
    return _collect(pool.submit(with_current_context(getattr(prov, method)), *args), method, deadline)


def _round(prov, method: str, batches: list, args: tuple, deadline: float) -> list:
    """(result, exc) per batch, all in flight together. A batch without a
    bucket token is not submitted (exc is a _NotSent)."""
    futures = [_pool.submit(with_current_context(getattr(prov, method)), b, *args)
               if _take_token() else None for b in batches]
    return [(None, _NotSent()) if f is None else _wait(f, deadline) for f in futures]


def _retryable(exc, deadline: float) -> bool:
    """A real failure with deadline budget left. Auth errors, an expired
    deadline and an open breaker are never retried; a provider-raised timeout
    that fired before the deadline is an ordinary failure and is retried."""
    if exc is None or isinstance(exc, (AlpacaAuthError, DeadlineExpired, _NotSent)):
        return False
    return time.monotonic() < deadline and _breaker.allows()


def _retry_failed(prov, method: str, batches: list, args: tuple, deadline: float, outcomes: list) -> list:
    """One in-call retry of the batches that failed; a retry that cannot be
    sent keeps the original failure."""
    idx = [i for i, (_, exc) in enumerate(outcomes) if _retryable(exc, deadline)]
    if not idx:
        return outcomes
    again = _round(prov, method, [batches[i] for i in idx], args, deadline)
    out = list(outcomes)
    for i, outcome in zip(idx, again):
        if not isinstance(outcome[1], _NotSent):
            out[i] = outcome
    return out


def _account(method: str, batches: list, outcomes: list) -> None:
    """One breaker verdict per call: a success if any sent batch succeeded (a
    deterministic poison batch must not trip the breaker for every symbol), one
    failure only when every sent batch failed, nothing when none was sent.
    Failed batches still get one rate-limited summary."""
    failed = [(i, exc) for i, (_, exc) in enumerate(outcomes)
              if exc is not None and not isinstance(exc, _NotSent)]
    succeeded = any(exc is None for _, exc in outcomes)
    if not failed:
        if succeeded:
            _record_verdict(True)
        return
    _stats["failures"] += len(failed)
    for i, exc in failed:
        log.debug("Alpaca %s batch %d miss: %s", method, i, _reason(exc))
    auth = any(isinstance(e, AlpacaAuthError) for _, e in failed)
    if succeeded and not auth:
        _record_verdict(True)
    else:
        _record_verdict(False, auth=auth, reason=_reason(failed[-1][1]))
    _warn_miss_summary(method, batches, failed)


def _warn_miss_summary(method: str, batches: list, failed: list) -> None:
    if not _warn_gate.ready():
        return
    kinds = Counter(_label(exc) for _, exc in failed)
    log.warning("Alpaca %s: %d/%d batch(es) missed (%s); %d symbol(s) fall back to yfinance",
                method, len(failed), len(batches),
                ", ".join(f"{k} x{n}" for k, n in kinds.items()),
                sum(len(batches[i]) for i, _ in failed))


def _attempt_many(method: str, batches: list, *args) -> list:
    """One result per batch (None on miss), all in flight together under one
    shared bulk deadline (ALPACA_BARS_TIMEOUT_SECONDS). Failed batches get one
    retry while the deadline has time left; the call records at most one
    breaker failure however many batches missed."""
    prov = _active_provider()
    if prov is None:
        return [None] * len(batches)
    deadline = time.monotonic() + _bars_timeout()
    outcomes = _round(prov, method, batches, args, deadline)
    outcomes = _retry_failed(prov, method, batches, args, deadline, outcomes)
    _account(method, batches, outcomes)
    return [result for result, _ in outcomes]


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


def _spot_alongside(spot, tickers, wanted, fetch):
    """A future of `_spot_daily` started now, or None to run it afterwards.
    Only when Alpaca has work to overlap and no underlying is in this call
    itself -- that frame is reused, so the spot path must wait for it."""
    if not spot or not wanted:
        return None
    if any(spot_metals.underlying(t) in tickers for t in spot):
        return None
    return _side_pool.submit(with_current_context(_spot_daily), spot, {}, fetch)


def daily_bars(tickers, period, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)

    def fetch(ts):
        return yf_fetch(ts, period)

    side = _spot_alongside(spot, tickers, wanted, fetch)
    n = symbols_per_request(period)
    batches = [wanted[i:i + n] for i in range(0, len(wanted), n)]
    got = {}
    for part in _attempt_many("daily_bars", batches, period):
        got.update(part or {})
    misses = [t for t in wanted if t not in got]
    _log_fallback("daily_bars", misses)
    out = _merge(got, rest, misses, fetch)
    out.update(side.result() if side is not None else _spot_daily(spot, out, fetch))
    return out


def daily_bars_between(tickers, start, end) -> dict:
    """v171 D4: Alpaca-only ranged daily bars for the alpaca-all cache. Spot,
    non-eligible symbols and an inactive provider give nothing; there is no
    yfinance fallback (a yfinance frame never enters that cache)."""
    _, tickers = spot_metals.split_spot(tickers)
    if _active_provider() is None:
        return {}
    wanted = [t for t in tickers if is_alpaca_eligible(t)]
    rows = (end - start).days * 252 // 365 + 10
    n = max(1, ROWS_PER_PAGE // rows)
    batches = [wanted[i:i + n] for i in range(0, len(wanted), n)]
    got = {}
    for part in _attempt_many("daily_bars_between", batches, start, end):
        got.update(part or {})
    _stats["alpaca"] += len(got)
    return _tag(got, SOURCE_ALPACA)


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


def _with_alpaca_quote(fallback: QuoteDetail, alpaca: QuoteDetail | None) -> QuoteDetail:
    """The fallback's price, the Alpaca IEX bid/ask (the D5 midpoint source)."""
    if alpaca is None or alpaca.quote_at is None:
        return fallback
    return dataclasses.replace(fallback, bid=alpaca.bid, ask=alpaca.ask, quote_at=alpaca.quote_at)


def _spot_quotes(spot) -> dict:
    """v171: spot_metals' quote as a QuoteDetail -- never cached here, never Alpaca."""
    out = {}
    for ticker in spot:
        quote, reason = spot_metals.quote_with_reason(ticker)
        if quote is None:
            _spot_miss[str(ticker).upper().strip()] = reason
            continue
        out[ticker] = QuoteDetail(symbol=ticker, price=quote.price, trade_at=quote.updated_at,
                                  bid=None, ask=None, quote_at=None, source="spot")
        _last_source[ticker] = SOURCE_SPOT
    return out


def latest_quotes(tickers, yf_fetch):
    """v171: latest_prices' routing with timestamps. A symbol whose Alpaca
    answer has no fresh trade price is re-asked from yfinance, keeping the
    Alpaca bid/ask on the merged detail."""
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got = (_attempt("latest_quotes", wanted,
                    int(config.ALPACA_MAX_TRADE_AGE_SECONDS)) or {}) if wanted else {}
    priced = {t: q for t, q in got.items() if q.price is not None}
    misses = [t for t in wanted if t not in priced]
    _log_fallback("latest_quotes", misses)
    out = dict(got)
    for group, source in ((rest, SOURCE_YF), (misses, SOURCE_FALLBACK)):
        fetched = yf_fetch(group) if group else {}
        out.update({t: _with_alpaca_quote(q, got.get(t)) for t, q in fetched.items()})
        _last_source.update({t: source for t in fetched})
    _last_source.update({t: SOURCE_ALPACA for t in priced})
    _stats["alpaca"] += len(priced)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    out.update(_spot_quotes(spot))
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
        df = _attempt("intraday_bars", ticker, interval, timeout=_bars_timeout())
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
