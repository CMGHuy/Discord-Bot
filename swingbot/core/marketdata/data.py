"""Fetches daily OHLC data for a ticker."""
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.infra.retry import with_retry
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import spot_metals, yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.base import SOURCE_YF, is_alpaca_eligible
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.budget import BudgetDeferred
from swingbot.core.marketdata.shared.kinds import (PROVIDER_ALPACA, PROVIDER_YF, Asker, DataKind, QuoteDetail,
                                                   resolve_asker)
from swingbot.core.marketdata.ticker_utils import candidate_symbols

log = logging.getLogger(__name__)

# Absorbs a transient yfinance failure (rate-limiting, a momentarily empty
# response) that would otherwise cost this ticker its whole 5-minute scan
# cycle. Kept short -- this runs inline in the live scan, not a background
# loop, and stays well inside COLD_FETCH_TIMEOUT_SECONDS/
# LIVE_PRICE_TIMEOUT_SECONDS even in the worst case.
FETCH_RETRY_ATTEMPTS = 2
FETCH_RETRY_BASE_DELAY = 1.5


def get_daily_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """
    Download daily OHLCV data for a ticker.
    Returns a DataFrame indexed by date with columns: Open, High, Low, Close, Volume.
    Raises ValueError if no data is returned for any resolved candidate symbol.

    Default period is 2 years, which comfortably covers the slowest
    indicator used across all swing horizons (EMA200 for the 6-month
    horizon, plus its lookback window).
    """
    if spot_metals.is_spot_metal(ticker):
        return _spot_daily_or_raise(ticker, period)
    if is_alpaca_eligible(ticker):
        # v106: an Alpaca miss comes back empty (the no-op yf_fetch), so the
        # candidate_symbols loop below runs exactly as before.
        key = ticker.upper().strip()
        hit = router.daily_bars([key], period, lambda ts, p: {}).get(key)
        if hit is not None and not hit.empty:
            return hit
    tried = []
    for candidate in candidate_symbols(ticker):
        tried.append(candidate)
        try:
            df = with_retry(yf_safe.download, candidate, period=period, interval="1d",
                            progress=False, auto_adjust=True,
                            attempts=FETCH_RETRY_ATTEMPTS, base_delay=FETCH_RETRY_BASE_DELAY,
                            label=f"get_daily_data({candidate})")
        except Exception as exc:
            swallowed(log, "marketdata.daily_data.candidate", exc, level=logging.DEBUG)
            continue
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.attrs["source"] = SOURCE_YF
            return df

    raise ValueError(
        f"No data returned for '{ticker}'. Tried: {', '.join(tried)}. "
        f"Check the symbol matches Yahoo Finance's format (e.g. '^GSPC' for S&P 500, "
        f"'EURUSD=X' for forex). Spot gold = 'XAUUSD', spot silver = 'XAGUSD' "
        f"('GC=F' / 'SI=F' still work and stay futures-priced)."
    )


def _spot_daily_or_raise(ticker: str, period: str) -> pd.DataFrame:
    """v109: a spot metal's bars are its future's bars x the live spot ratio
    (router.daily_bars). Never the candidate_symbols() loop: ALIASES maps
    XAUUSD -> GC=F, which would hand back UNSCALED futures prices."""
    key = ticker.upper().strip()
    df = router.daily_bars([key], period, _yf_daily_batch).get(key)
    if df is None:
        raise ValueError(
            f"No spot data for '{key}': {router.spot_miss_reason(key) or 'unavailable'}. "
            f"Spot symbols never fall back to unscaled futures prices.")
    return df


def get_daily_data_batch(tickers: list, period: str = "2y") -> dict:
    """v55: batched sibling of get_daily_data() -- one yf.download() call
    for many tickers instead of one call each, replacing what used to be
    N sequential/pooled network round trips with O(1) per chunk (see
    scanning/engine.py's _fetch_cold_frames, which calls this per chunk).

    group_by="ticker" gives a per-ticker slice keyed by symbol even for a
    batch of one (verified against live data: still a 2-level column index),
    so there is no special-casing between a chunk of 1 and a chunk of 100.

    Returns {ticker: DataFrame} for tickers whose slice came back non-empty.
    A ticker absent from the result (its own slice was empty/all-NaN, or
    the whole call failed/raised) is simply missing -- same "unavailable
    this scan" contract get_daily_data() already has. Unlike get_daily_data(),
    this does NOT try candidate_symbols() aliasing -- it only ever asks for
    the tickers' literal symbols; a ticker that needs alias resolution comes
    back absent here and the caller falls back to get_daily_data() for it.
    """
    tickers = list(dict.fromkeys(
        str(ticker).upper().strip()
        for ticker in tickers if ticker is not None and str(ticker).strip()
    ))
    if not tickers:
        return {}
    return router.daily_bars(tickers, period, _yf_daily_batch)


def _yf_daily_batch(tickers: list, period: str) -> dict:
    """get_daily_data_batch's yfinance path (pre-v106 body, unchanged): one
    batched download, sliced per ticker. The router hands it the tickers
    Alpaca does not serve or missed."""
    try:
        raw = with_retry(yf_safe.download, " ".join(tickers), period=period, interval="1d",
                         group_by="ticker", auto_adjust=True, progress=False,
                         attempts=FETCH_RETRY_ATTEMPTS, base_delay=FETCH_RETRY_BASE_DELAY,
                         label=f"get_daily_data_batch({len(tickers)} tickers)")
    except yf_safe.DownloadBusy as exc:
        log.info("yfinance busy, skipped %d ticker(s): %s", len(tickers), exc)
        return {}
    except Exception as exc:
        swallowed(log, "marketdata.daily_batch", exc,
                  "get_daily_data_batch failed for %d ticker(s) after %d attempt(s): %s",
                  len(tickers), FETCH_RETRY_ATTEMPTS, exc, level=logging.ERROR, exc_info=True)
        return {}
    if raw is None or raw.empty:
        return {}
    out: dict = {}
    for ticker in tickers:
        try:
            sub = raw[ticker].dropna(how="all")
        except KeyError:
            continue
        if not sub.empty:
            out[ticker] = sub
    return out


#: Last known-good price per ticker from a SUCCESSFUL get_current_price_batch
#: call, regardless of which batch asked for it. {ticker: (value, fetched_at)}
#: -- no `stale` third element: unlike _price_cache below, nothing here reads
#: a PriceQuote off this dict directly, only through get_current_price_batch's
#: own float-only contract.
_last_good_batch_price: dict = {}
#: How long a ticker's last-good batch price stays eligible as a fallback
#: on a failed batch. Deliberately longer than a single scan cycle (a few
#: minutes) so one transient failure never shows "no price" -- a stale-but-
#: real number for a bit is a smaller lie than blanking every ticker in the
#: batch, which is what returning {} on failure used to do.
_LAST_GOOD_BATCH_PRICE_TTL_SECONDS = 15 * 60
# Successful batch responses are also a short-lived display cache.  The
# dashboard refreshes more often than quotes need to be re-downloaded, while
# trading callers pass allow_stale=False and therefore bypass this cache.
_BATCH_PRICE_CACHE_TTL_SECONDS = 15


def _normalise_tickers(tickers) -> list:
    return list(dict.fromkeys(str(t).upper().strip() for t in tickers
                              if t is not None and str(t).strip()))


def _usable(entry, window, fresh_only: bool) -> bool:
    """A layer entry a caller may use; fresh-only callers never take a
    budget-deferred or over-window value (D2: never "close enough")."""
    if entry is None or entry.value is None:
        return False
    if not fresh_only:
        return True
    if entry.outcome == "budget-deferred":
        return False
    # "fetched" = fetched by this very call: fresh even at ADMIN_FRESH's 0 s window.
    return entry.outcome == "fetched" or window is None or entry.age_s() <= window


def get_quote_batch(tickers, *, asker, max_age_s=None, fresh_only=False) -> dict:
    """v171: timestamped quotes through the shared layer at `asker`'s window
    and tier. Spot metals keep spot_metals' own path and are never cached."""
    marked = _marked_quotes(tickers, asker=asker, max_age_s=max_age_s)
    return {t: q for t, (q, fresh) in marked.items() if fresh or not fresh_only}


def _marked_quotes(tickers, *, asker, max_age_s=None) -> dict:
    """{ticker: (QuoteDetail, fresh)} -- get_quote_batch's read, keeping
    whether each value passes the fresh-only rule (`_usable`), so price
    callers can flag a deferred / over-window value stale and never re-stamp
    it into an in-process cache as a new observation."""
    tickers = _normalise_tickers(tickers)
    spot, rest = spot_metals.split_spot(tickers)
    out = {t: (q, True) for t, q in
           (router.latest_quotes(spot, _yf_quote_details) if spot else {}).items()}
    if not rest:
        return out
    with router.asker_scope(asker):
        entries = layer.get(DataKind.QUOTE, rest,
                            lambda syms: router.latest_quotes(list(syms), _yf_quote_details),
                            asker=asker, provider=PROVIDER_ALPACA, max_age_s=max_age_s,
                            encode=QuoteDetail.to_doc, decode=QuoteDetail.from_doc)
    window = max_age_s if max_age_s is not None else resolve_asker(asker).window_s(DataKind.QUOTE)
    out.update({t: (e.value, _usable(e, window, True))
                for t, e in entries.items() if _usable(e, window, False)})
    return out


def get_current_price_batch(tickers: list, *, allow_stale: bool = True,
                            asker: Asker = Asker.SCAN) -> dict:
    """{ticker: price}. See _price_batch_legacy for the contract (unchanged).
    v171: MARKETDATA_LAYER off is that function exactly; count/on read
    get_quote_batch at `asker`, fresh-only when allow_stale=False."""
    if config.MARKETDATA_LAYER == "off":
        return _price_batch_legacy(tickers, allow_stale=allow_stale)
    return _price_batch_layer(tickers, allow_stale=allow_stale, asker=asker)


def _price_batch_layer(tickers, *, allow_stale: bool, asker) -> dict:
    tickers = _normalise_tickers(tickers)
    if not tickers:
        return {}
    now = time.monotonic()
    current = _count_mode_display_hit(tickers, now, allow_stale)
    if current is not None:
        return current
    out, served_stale = _split_fresh_prices(_marked_quotes(tickers, asker=asker))
    # Only a fresh value is a new observation; a deferred / over-window one
    # is never re-stamped `now`, so the last-good TTL keeps counting.
    for ticker, price in out.items():
        _last_good_batch_price[ticker] = (price, now)
    if allow_stale:
        out.update(served_stale)
    missing = [t for t in tickers if t not in out]
    if missing and allow_stale:
        out.update(_stale_batch_fallback(missing, now))
    return out


def _count_mode_display_hit(tickers: list, now: float, allow_stale: bool) -> dict | None:
    """count mode keeps the in-process 15 s display short-circuit so its call
    volume is today's (the D9 baseline); on mode leaves it to the layer."""
    if not allow_stale or config.MARKETDATA_LAYER != "count":
        return None
    current = _fresh_batch_prices(tickers, now)
    return current if len(current) == len(tickers) else None


def _split_fresh_prices(marked: dict) -> tuple:
    """(fresh {ticker: price}, non-fresh {ticker: price}) from _marked_quotes."""
    fresh = _priced({t: q for t, (q, ok) in marked.items() if ok})
    stale = _priced({t: q for t, (q, ok) in marked.items() if not ok})
    return fresh, stale


def _priced(quotes: dict) -> dict:
    """{ticker: price} for quotes carrying a positive trade price; a
    bid/ask-only QuoteDetail (price None) is skipped."""
    return {t: q.price for t, q in quotes.items() if q.price and q.price > 0}


def _price_batch_legacy(tickers: list, *, allow_stale: bool = True) -> dict:
    """v55: batched sibling of get_current_price() -- one yf.download() call
    (1-day/1-minute, prepost=True) for many tickers' live price instead of a
    Ticker().history() + fast_info fallback per ticker (see
    scanning/engine.py's _fetch_live_prices).

    Returns {ticker: price} using each ticker's last non-NaN Close. A ticker
    absent from the result falls back to today's daily close in the caller --
    same fallback get_current_price()'s own failure case already has. No
    candidate_symbols() aliasing (see get_daily_data_batch).

    ``allow_stale=False`` is for trading decisions.  It suppresses the
    last-known-good fallback, because an old batch quote must never confirm a
    stop/target fill or a debounce transition.  Display callers retain the
    existing resilient default.

    Deliberately NOT wrapped in with_retry, unlike get_daily_data_batch
    right above it (tried 2026-09-14, reverted the same day):
    test_api_v1_watchlist.py's test_next_earnings_fields_null_and_non_
    blocking_when_not_yet_cached asserts /api/v1/watchlist/tickers answers
    in under 1 second even for a not-yet-cached ticker -- "the whole point"
    of that endpoint's own fix, which this is one call inside. A blocking
    retry (2 attempts, 1.5s+ backoff) on every transient failure directly
    breaks that contract. Falls back to each ticker's own last known-good
    batch price instead: one network call covers the whole batch, so a
    single transient failure (a timeout, a Yahoo throttle) used to blank
    EVERY ticker's price for the tick, not just the one that actually
    failed -- reported as the market/watchlist tape persistently showing
    "no price" for tickers that plainly have one. The fallback fixes that
    symptom without adding latency to the success path or blocking the
    failure path.
    """
    tickers = list(dict.fromkeys(
        str(ticker).upper().strip()
        for ticker in tickers if ticker is not None and str(ticker).strip()
    ))
    if not tickers:
        return {}
    now = time.monotonic()
    if allow_stale:
        current = _fresh_batch_prices(tickers, now)
        if len(current) == len(tickers):
            return current
    out = router.latest_prices(tickers, _yf_batch_prices)
    for ticker, price in out.items():
        _last_good_batch_price[ticker] = (price, now)
    # A failed download (every ticker missed) and a partial one land here
    # alike: each ticker THIS call missed still gets a stale-fallback chance
    # individually.
    missing = [t for t in tickers if t not in out]
    if missing and allow_stale:
        out.update(_stale_batch_fallback(missing, now))
    return out


def _fresh_batch_prices(tickers: list, now: float) -> dict:
    """The tickers whose last-good batch price is inside the short display
    cache TTL -- a display caller whose whole batch is here skips the fetch."""
    return {
        ticker: cached[0]
        for ticker in tickers
        if (cached := _last_good_batch_price.get(ticker))
        and now - cached[1] < _BATCH_PRICE_CACHE_TTL_SECONDS
    }


def _bar_time_utc(ts):
    stamp = pd.Timestamp(ts)
    return (stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")).to_pydatetime()


def _last_minute_quote(raw, ticker):
    try:
        closes = raw[ticker]["Close"].dropna()
    except KeyError:
        return None
    if closes.empty or float(closes.iloc[-1]) <= 0:
        return None
    return QuoteDetail(symbol=ticker, price=float(closes.iloc[-1]),
                       trade_at=_bar_time_utc(closes.index[-1]), bid=None, ask=None,
                       quote_at=None, source="yfinance-1m")


def _yf_quote_details(tickers: list) -> dict:
    """v171: _yf_batch_prices with each price's own bar timestamp (D5: a
    delayed yfinance value counts only if its own timestamp passes 60 s)."""
    try:
        raw = yf_safe.download(" ".join(tickers), period="1d", interval="1m",
                               group_by="ticker", prepost=True, progress=False)
    except yf_safe.BudgetDeferred:
        raise
    except yf_safe.DownloadBusy as exc:
        log.info("yfinance busy, skipped %d ticker(s): %s", len(tickers), exc)
        return {}
    except Exception as exc:
        log.error("_yf_quote_details failed for %d ticker(s): %s", len(tickers), exc, exc_info=True)
        return {}
    if raw is None or raw.empty:
        return {}
    return {t: q for t in tickers if (q := _last_minute_quote(raw, t)) is not None}


def _yf_batch_prices(tickers: list) -> dict:
    """get_current_price_batch's yfinance path (pre-v106, unchanged): one
    1-day/1-minute prepost download, each ticker's last non-NaN Close > 0.
    Returns {} on a failed or empty download."""
    try:
        raw = yf_safe.download(" ".join(tickers), period="1d", interval="1m",
                          group_by="ticker", prepost=True, progress=False)
    except yf_safe.DownloadBusy as exc:
        log.info("yfinance busy, skipped %d ticker(s): %s", len(tickers), exc)
        return {}
    except Exception as exc:
        swallowed(log, "marketdata.price_batch", exc,
                  "get_current_price_batch failed for %d ticker(s): %s", len(tickers), exc,
                  level=logging.ERROR, exc_info=True)
        return {}
    if raw is None or raw.empty:
        return {}
    out: dict = {}
    for ticker in tickers:
        try:
            closes = raw[ticker]["Close"].dropna()
        except KeyError:
            continue
        if not closes.empty:
            price = float(closes.iloc[-1])
            if price > 0:
                out[ticker] = price
    return out


def peek_cached_batch_price(tickers: list) -> dict:
    """Cache-only sibling of `get_current_price_batch`: whichever of
    `tickers` has a fresh-enough last-good batch price, never fetches,
    never blocks. Same shape as `core.market.events.peek_cached_
    earnings_datetime` -- pair with `warm_batch_price_cache_background` to
    fill the gap for next time without making THIS request pay for it.
    """
    tickers = list(dict.fromkeys(
        str(ticker).upper().strip()
        for ticker in tickers if ticker is not None and str(ticker).strip()
    ))
    if not tickers:
        return {}
    return _stale_batch_fallback(tickers, time.monotonic())


def warm_batch_price_cache_background(tickers: list) -> threading.Thread:
    """Fire-and-forget: populate `_last_good_batch_price` for `tickers` on
    a daemon thread. Same shape as `core.market.events.
    warm_earnings_cache_background` -- the caller gets an immediate return
    and the next request (or the next poll of the same page) sees the
    warmed price instead of paying for it.

    ``allow_stale=False`` so the fetch always hits the network rather than
    short-circuiting on a fresh-enough cache entry `peek_cached_batch_price`
    would already have returned -- there would be nothing new to warm.
    """
    def _run():
        try:
            get_current_price_batch(tickers, allow_stale=False)
        except Exception as exc:
            swallowed(log, "marketdata.price_warmup", exc,
                      "background price warm-up failed for %d ticker(s)", len(tickers),
                      level=logging.DEBUG, exc_info=True)

    t = threading.Thread(target=_run, name="price-cache-warm", daemon=True)
    t.start()
    return t


def _stale_batch_fallback(tickers: list, now: float) -> dict:
    """Whichever of `tickers` still has a fresh-enough last-good batch
    price, else absent -- same contract get_current_price_batch's own
    empty-dict failure case already had for anything this can't cover."""
    out: dict = {}
    for ticker in tickers:
        cached = _last_good_batch_price.get(ticker)
        if cached and (now - cached[1]) < _LAST_GOOD_BATCH_PRICE_TTL_SECONDS:
            out[ticker] = cached[0]
    return out


# Maps an ISO currency code (as reported by Yahoo Finance) to the symbol
# people actually recognize on a chart. Anything not listed falls back to
# "<CODE> " (e.g. "PLN ") rather than guessing wrong.
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "GBp": "£", "JPY": "¥", "CNY": "¥",
    "CHF": "CHF ", "CAD": "C$", "AUD": "A$", "NZD": "NZ$", "HKD": "HK$",
    "SGD": "S$", "SEK": "kr", "NOK": "kr", "DKK": "kr", "INR": "₹",
    "KRW": "₩", "BRL": "R$", "MXN": "$", "ZAR": "R", "PLN": "zł", "ILS": "₪",
}

# Per-ticker currency is looked up once (a network call) and cached for the
# life of the process -- it doesn't change scan to scan, so this doesn't add
# a network round-trip to every chart generated on every 5-minute scan.
_currency_cache: dict[str, str] = {}

# Real company name lookups (e.g. "Apple Inc." for AAPL), same lazy
# in-memory cache pattern as _currency_cache above -- one network call
# per ticker for the life of the process, not per Watchlist page view.
_company_name_cache: dict[str, str | None] = {}

# Both caches above used to be purely in-memory, which meant every time the
# ADMIN container restarted (redeploy, `docker compose restart`, a crash --
# it's a separate process from the bot, with its own memory, so the bot
# staying up doesn't help), the Watchlist page paid the full cost again:
# every ticker not covered by the local NASDAQ/NYSE directory (newer/small-
# cap/international symbols -- SPCX, IREN, QBTS, ASML.AS, etc.) fell through
# to a live yfinance network call, one by one, for every uncached ticker on
# the list. That's what made the page occasionally take a long time to load
# -- not "sometimes slow", but reliably slow exactly once per admin restart
# until the in-memory cache warmed back up, which then reset the next
# restart. Persisting both caches to a small JSON file survives restarts/
# redeploys entirely, so only a genuinely NEW ticker ever pays the network
# cost again.
_TICKER_META_CACHE_PATH = None  # set lazily below to avoid a hard import-time dependency on config.DATA_DIR


def _ticker_meta_cache_path() -> str:
    global _TICKER_META_CACHE_PATH
    if _TICKER_META_CACHE_PATH is None:
        from swingbot import config as _app_config
        _TICKER_META_CACHE_PATH = os.path.join(_app_config.DATA_DIR, "ticker_meta_cache.json")
    return _TICKER_META_CACHE_PATH


def _load_ticker_meta_cache():
    # jsonio, like every other data/ file: UTF-8 regardless of platform, and a
    # corrupt file is logged rather than silently starting empty.
    data = read_json(_ticker_meta_cache_path(), {})
    if isinstance(data, dict):
        _currency_cache.update(data.get("currency_symbols", {}))
        _company_name_cache.update(data.get("company_names", {}))


def _save_ticker_meta_cache():
    # Atomic: the admin's Watchlist page and the bot both write this file, and
    # a plain truncate-then-write left a reader a torn document mid-write.
    try:
        atomic_write_json(_ticker_meta_cache_path(), {
            "currency_symbols": _currency_cache,
            "company_names": _company_name_cache,
        })
    except Exception as exc:
        swallowed(log, "marketdata.save_ticker_meta", exc, "Could not save ticker_meta_cache.json",
                  level=logging.DEBUG, exc_info=True)


_load_ticker_meta_cache()


def get_company_name(ticker: str) -> str | None:
    """
    Returns the real company/fund name for `ticker` (e.g. "Apple Inc."
    for AAPL, "SPDR S&P 500 ETF Trust" for SPY), or None if it can't be
    resolved for any reason (unusual symbol, index, future, transient
    network failure). Used by the Watchlist page's "Company" column.

    Fast path: NASDAQ/NYSE directory lookup (no network call, covers most
    US-listed tickers). Falls back to yfinance only for international or
    OTC symbols not in the directory.
    """
    from swingbot.core.marketdata.ticker_directory import lookup_name  # avoid circular import at module level

    ticker_key = ticker.upper().strip()
    if ticker_key in _company_name_cache:
        return _company_name_cache[ticker_key]

    # Fast path: local directory, no network needed
    name = lookup_name(ticker_key)
    if name:
        _company_name_cache[ticker_key] = name
        return name

    # Slow path: yfinance for international / OTC symbols
    name, answered = _provider_company_name(ticker_key)
    if not answered:
        return None            # v171: deferred or failed shared lookup; retry next time
    _company_name_cache[ticker_key] = name
    _save_ticker_meta_cache()  # persist so this network call isn't repeated after the next restart
    return name


def _company_name_legacy(ticker_key: str) -> str | None:
    name = None
    for candidate in candidate_symbols(ticker_key):
        try:
            info = yf.Ticker(candidate).info
            name = info.get("longName") or info.get("shortName")
            if name:
                break
        except Exception as exc:
            swallowed(log, "marketdata.company_name", exc, level=logging.DEBUG)
            continue
    return name


def _fast_info_currency(ticker):
    try:
        fast_info = ticker.fast_info
        return fast_info.get("currency") if hasattr(fast_info, "get") else getattr(fast_info, "currency", None)
    except Exception as exc:
        swallowed(log, "marketdata.ticker_meta_fast", exc, level=logging.DEBUG)
        return None


def _meta_for(symbol: str) -> dict | None:
    """One symbol's name and currency; the first candidate that answered wins, None when all raised."""
    for candidate in candidate_symbols(symbol):
        try:
            yf_safe._take_yf_token()
            ticker = yf.Ticker(candidate)
            info = ticker.info
            name = info.get("longName") or info.get("shortName")
            code = info.get("currency") or _fast_info_currency(ticker)
            return {"name": name, "currency": str(code).upper() if code else None}
        except BudgetDeferred:
            raise
        except Exception as exc:
            swallowed(log, "marketdata.ticker_meta", exc, level=logging.DEBUG)
    return None


def _fetch_ticker_meta(symbols: list) -> dict:
    return {s: _meta_for(s) for s in symbols}


def _ticker_meta(ticker: str) -> dict:
    """v171: the persistent metadata doc through the shared layer; {} when it has nothing."""
    with router.asker_scope(Asker.BACKGROUND):
        got = layer.get(DataKind.METADATA, [ticker], _fetch_ticker_meta,
                        asker=Asker.BACKGROUND, provider=PROVIDER_YF)
    entry = got.get(ticker)
    return dict(entry.value) if entry is not None and entry.value else {}


def _count_meta_fetch() -> None:
    counters.count(PROVIDER_YF, DataKind.METADATA, router.current_asker(), "fetched")


def _provider_company_name(key: str) -> tuple:
    mode = config.MARKETDATA_LAYER
    if mode == "on":
        meta = _ticker_meta(key)
        return meta.get("name"), bool(meta)
    name = _company_name_legacy(key)
    if mode == "count":
        _count_meta_fetch()
    return name, True


def _provider_currency_code(key: str) -> tuple:
    mode = config.MARKETDATA_LAYER
    if mode == "on":
        meta = _ticker_meta(key)
        return meta.get("currency"), bool(meta)
    code = _resolve_currency_code(key)
    if mode == "count":
        _count_meta_fetch()
    return code, True


def _resolve_currency_code(ticker: str) -> str | None:
    """Tries yfinance metadata for each resolved candidate symbol; returns
    the ISO currency code (e.g. 'USD', 'EUR') for the first one that has
    it, else None."""
    for candidate in candidate_symbols(ticker):
        try:
            fast_info = yf.Ticker(candidate).fast_info
            code = fast_info.get("currency") if hasattr(fast_info, "get") else getattr(fast_info, "currency", None)
            if code:
                return str(code).upper()
        except Exception as exc:
            swallowed(log, "marketdata.currency_code", exc, level=logging.DEBUG)
            continue
    return None


def get_currency_symbol(ticker: str, default_symbol: str = "€") -> str:
    """
    Returns the currency symbol this ticker actually trades in -- e.g. an
    NYSE/NASDAQ ticker like AAPL is USD ($), while a Euronext-listed
    ticker like ASML.AS is EUR (€) -- instead of one hardcoded symbol
    applied to every chart regardless of what exchange it's actually
    listed on. Falls back to `default_symbol` (config.CURRENCY_SYMBOL) if
    the currency can't be determined for any reason.
    """
    ticker_key = ticker.upper().strip()
    if ticker_key in _currency_cache:
        return _currency_cache[ticker_key]

    symbol = default_symbol
    code, answered = _provider_currency_code(ticker_key)
    if not answered:
        return default_symbol  # v171: deferred or failed shared lookup; retry next time
    if code:
        symbol = CURRENCY_SYMBOLS.get(code, f"{code} ")

    _currency_cache[ticker_key] = symbol
    _save_ticker_meta_cache()  # persist so this network call isn't repeated after the next restart
    return symbol


# ---------------------------------------------------------------------------
# Live price fetching (admin dashboard trade-health status)
# ---------------------------------------------------------------------------

# How long a fetched price is trusted before the next call re-fetches it.
# 15s TTL means prices stay fresh across the dashboard's 5s auto-refresh
# without hammering yfinance on every single poll.
_PRICE_CACHE_TTL_SECONDS = 15
# ticker -> (price, fetched_at monotonic, stale). `stale` is a property of
# the QUOTE, not of cache age: a fast_info fallback written THIS second is
# still stale (see PriceQuote), so a fresh-within-TTL hit must replay the
# stored flag rather than assume False just because it was just written.
_price_cache: dict[str, tuple[float, float, bool]] = {}


@dataclass(frozen=True)
class PriceQuote:
    """A price plus whether it is safe to treat as a live tick.

    `stale=True` covers two cases, both display-only concerns a trading
    caller never sees (they pass `allow_stale=False` and get `None` instead,
    same as before this type existed):

    - yfinance's `fast_info` fallback, which can echo the PREVIOUS session's
      close during early extended hours (`_fast_info_price`'s docstring) --
      the exact misread that showed MRNA as having hit a stop-loss it never
      touched (2026-09-18): the primary 1-minute-history fetch failed on a
      real, logged `YFRateLimitError`, and fast_info's stand-in for it was
      wrong for the moment even though it was fetched "just now".
    - the last-known-good `_price_cache` entry served past its normal TTL,
      which `test_current_price_staleness.py` already covered before this
      type existed -- any age, by definition not a live observation.

    v171: `as_of` and `age_s` are when the price was observed and how old it
    was at return; `None` before v171 and on the off path.
    """
    price: float
    stale: bool
    as_of: datetime | None = None
    age_s: float | None = None


def _fast_info_price(fi) -> float | None:
    """Extract last price from a yfinance FastInfo object, trying multiple
    attribute names to handle different yfinance versions and market sessions."""
    for attr in ("last_price", "lastPrice", "regularMarketPrice",
                 "pre_market_price", "preMarketPrice",
                 "post_market_price", "postMarketPrice"):
        try:
            val = fi.get(attr) if hasattr(fi, "get") else getattr(fi, attr, None)
            if val is not None and float(val) > 0:
                return float(val)
        except Exception as exc:
            swallowed(log, "marketdata.fast_info_price", exc, level=logging.DEBUG)
            continue
    return None


def _cached_or_alpaca_quote(ticker_key: str, cached, now: float,
                            ttl_seconds: int) -> PriceQuote | None:
    """The answers get_current_price_detail tries before yfinance.

    A fresh cache entry is a recent market observation for every caller.
    ``allow_stale=False`` excludes only the expired last-known-good fallback
    in the caller; otherwise a trading transition needlessly refetches a
    quote that was observed moments ago. The stored `stale` bit is replayed
    as-is: a fast_info fallback written a second ago is still that fallback.

    v106: then a fresh Alpaca last trade for an eligible US symbol, cached
    like the 1-minute-history hit it stands in for. None (a miss, or
    ineligible) lets the yfinance path run exactly as before."""
    if cached and (now - cached[1]) < ttl_seconds:
        return PriceQuote(cached[0], cached[2])
    if not is_alpaca_eligible(ticker_key):
        return None
    price = router.latest_prices([ticker_key], lambda ts: {}).get(ticker_key)
    if not price:
        return None
    _price_cache[ticker_key] = (price, now, False)
    return PriceQuote(price, False)


def _spot_price_detail(ticker_key: str, cached, now: float,
                       allow_stale: bool) -> PriceQuote | None:
    """v109: a spot metal's live price is gold-api.com's spot quote. Missing
    or stale is the same "no price" a failed quote already gives: None for a
    trading caller, the last known-good value (flagged stale) for display.
    Never the candidate loop, which would price XAUUSD off GC=F."""
    quote = spot_metals.spot_quote(ticker_key)
    if quote is not None:
        _price_cache[ticker_key] = (quote.price, now, False)
        return PriceQuote(quote.price, False)
    if cached and allow_stale:
        return PriceQuote(cached[0], True)
    return None


def get_current_price_detail(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS,
                             *, allow_stale: bool = True,
                             asker: Asker = Asker.ADMIN_PAGE) -> PriceQuote | None:
    """
    `get_current_price`'s full answer: the price AND whether it is safe to
    treat as a live tick (see `PriceQuote`). `get_current_price` itself stays
    a bare float-or-None so no trading call site has to change; this is for
    a display caller that wants to say "delayed" instead of rendering a
    fallback number with full confidence -- the admin dashboard's
    `current_price_stale` field is the one caller today.

    Primary source: 1-minute history with prepost=True — this always returns
    the most recently traded price in any session and is the most accurate.
    Fallback: fast_info attributes for when the history call fails (e.g.
    network timeout, symbol not found in history endpoint).

    Cached in-memory per ticker for `ttl_seconds` (default 15s).

    When every fetch fails, the last known price is returned however old it
    is -- right for a dashboard, wrong for anything that trades on the
    answer. Trading callers (the plan manager, the SL/TP monitor, reversal and
    manual-close fills) pass `allow_stale=False` and get None instead: a
    repeated cached print would otherwise count as a fresh confirming tick
    for the extended-hours debounce and fill a close at a price that stopped
    being current an unknown time ago.

    v171: off is _price_detail_legacy exactly; count/on ask get_quote_batch
    at `asker` first and stamp as_of/age_s.
    """
    if config.MARKETDATA_LAYER == "off":
        return _price_detail_legacy(ticker, ttl_seconds, allow_stale)
    return _price_detail_layer(ticker, ttl_seconds, allow_stale, asker)


def _quote_to_price(q, stale: bool) -> PriceQuote:
    as_of = q.trade_at or q.quote_at
    age = (datetime.now(timezone.utc) - as_of).total_seconds() if as_of else None
    return PriceQuote(q.price, stale, as_of, age)


def _price_detail_layer(ticker, ttl_seconds, allow_stale, asker) -> PriceQuote | None:
    key = ticker.upper().strip()
    cached = _price_cache.get(key)
    now = time.monotonic()
    if spot_metals.is_spot_metal(key):
        return _spot_price_detail(key, cached, now, allow_stale)
    if config.MARKETDATA_LAYER == "count" and cached and now - cached[1] < ttl_seconds:
        return PriceQuote(cached[0], cached[2])
    q, fresh = _marked_quotes([key], asker=asker).get(key, (None, False))
    if q is not None and q.price and (fresh or allow_stale):
        if fresh:
            _price_cache[key] = (q.price, now, False)
        return _quote_to_price(q, stale=not fresh)
    return _detail_from_yfinance(key, cached, now, allow_stale)


def _price_detail_legacy(ticker: str, ttl_seconds: int,
                         allow_stale: bool) -> PriceQuote | None:
    """get_current_price_detail before v171, unchanged (MARKETDATA_LAYER off)."""
    ticker_key = ticker.upper().strip()
    cached = _price_cache.get(ticker_key)
    now = time.monotonic()
    if spot_metals.is_spot_metal(ticker_key):
        return _spot_price_detail(ticker_key, cached, now, allow_stale)
    early = _cached_or_alpaca_quote(ticker_key, cached, now, ttl_seconds)
    if early is not None:
        return early
    return _detail_from_yfinance(ticker_key, cached, now, allow_stale)


def _detail_from_yfinance(ticker_key: str, cached, now: float,
                          allow_stale: bool) -> PriceQuote | None:
    """The yfinance 1-minute history / fast_info candidate loop, then the
    last-known-good tail -- moved verbatim from get_current_price_detail."""
    for candidate in candidate_symbols(ticker_key):
        # Primary: 1-minute history with prepost=True is the most accurate
        # source — it returns the true last-traded price in any session
        # (pre-market, regular, after-hours).  fast_info can return the
        # previous regular-session close during extended hours which causes
        # the stale-price issue.
        try:
            hist = yf.Ticker(candidate).history(period="1d", interval="1m", prepost=True)
            if hist is not None and not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
                if price > 0:
                    _price_cache[ticker_key] = (price, now, False)
                    return PriceQuote(price, False)
        except Exception as exc:
            swallowed(log, "marketdata.price_detail.history", exc, level=logging.DEBUG)

        # Fallback: fast_info is cheaper but may be stale during extended hours
        try:
            fi = yf.Ticker(candidate).fast_info
            price = _fast_info_price(fi)
            if price:
                _price_cache[ticker_key] = (price, now, True)
                return PriceQuote(price, True)
        except Exception as exc:
            swallowed(log, "marketdata.price_detail.fast_info", exc, level=logging.DEBUG)
            continue

    # Serve last known-good price on transient failure rather than blanking
    # the UI -- to display callers only (see the docstring). Always stale:
    # this is being served past its normal freshness window regardless of
    # what it was tagged when written.
    if cached and allow_stale:
        return PriceQuote(cached[0], True)
    return None


def get_current_price(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS,
                      *, allow_stale: bool = True, asker: Asker = Asker.SCAN) -> float | None:
    """The price alone, for every existing (mostly trading) call site.

    See `get_current_price_detail` for the full docstring and for the
    `stale` flag a display caller should be reading instead of calling this.
    """
    detail = get_current_price_detail(ticker, ttl_seconds, allow_stale=allow_stale,
                                      asker=asker)
    return detail.price if detail is not None else None


def is_us_market_active(now=None) -> bool:
    """
    Returns True when any US equity market session is currently open:
      Pre-market:  4:00 AM – 9:30 AM  ET
      Regular:     9:30 AM – 4:00 PM  ET
      After-hours: 4:00 PM – 8:00 PM  ET
    Returns False on weekends and between 8 PM and 4 AM ET.

    Reads the real America/New_York clock. It used to guess the offset from
    the month (Mar-Nov = EDT), which is an hour wrong for the weeks between
    1 March and DST's second-Sunday start, and after its first-Sunday-of-
    November end. `now` (aware) is for tests.
    """
    from datetime import datetime, timezone
    from swingbot.core.market.session import US_MARKET_TZ
    now_et = (now or datetime.now(timezone.utc)).astimezone(US_MARKET_TZ)
    if now_et.weekday() >= 5:           # Saturday or Sunday, in New York
        return False
    minutes = now_et.hour * 60 + now_et.minute
    return 4 * 60 <= minutes < 20 * 60


def prefetch_prices(tickers: list[str], max_workers: int = 10) -> None:
    """
    Warm the single-price display cache with one batched request.

    ``max_workers`` remains accepted for callers using the old interface, but
    threaded individual yfinance calls are both slower and unsafe with this
    pinned yfinance version. Consumers that follow by calling
    ``get_current_price``/``get_current_price_detail`` now hit
    ``_price_cache`` rather than downloading every ticker again.

    Written as `stale=False`: `get_current_price_batch` has its own,
    separately tested last-good-price fallback (`_stale_batch_fallback`, up
    to 15 minutes old) with no per-ticker signal of whether a given result
    came from it, so this warms the display cache without a staleness claim
    either way rather than a wrong one. The `PriceQuote.stale` flag's proven
    case is `get_current_price_detail`'s OWN fast_info/last-known-good
    fallback below it, entered when this batch omits a ticker entirely
    (see `_attach_current_prices`).
    """
    del max_workers
    unique = list(dict.fromkeys(t.upper().strip() for t in tickers if t and t.strip()))
    if not unique:
        return
    try:
        prices = get_current_price_batch(unique)
    except Exception as exc:
        swallowed(log, "marketdata.prefetch_prices", exc, "prefetch_prices batch failed: %s", exc,
                  exc_info=True)
        return
    now = time.monotonic()
    for ticker, price in prices.items():
        if price and price > 0:
            _price_cache[ticker.upper().strip()] = (float(price), now, False)

