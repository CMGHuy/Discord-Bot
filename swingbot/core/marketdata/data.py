"""Fetches daily OHLC data for a ticker."""
import logging
import os
import time

import pandas as pd
import yfinance as yf

from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.infra.retry import with_retry
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
    tried = []
    for candidate in candidate_symbols(ticker):
        tried.append(candidate)
        try:
            df = with_retry(yf.download, candidate, period=period, interval="1d",
                            progress=False, auto_adjust=True,
                            attempts=FETCH_RETRY_ATTEMPTS, base_delay=FETCH_RETRY_BASE_DELAY,
                            label=f"get_daily_data({candidate})")
        except Exception:
            continue
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df

    raise ValueError(
        f"No data returned for '{ticker}'. Tried: {', '.join(tried)}. "
        f"Check the symbol matches Yahoo Finance's format (e.g. '^GSPC' for S&P 500, "
        f"'GC=F' for gold, 'EURUSD=X' for forex)."
    )


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
    try:
        raw = with_retry(yf.download, " ".join(tickers), period=period, interval="1d",
                         group_by="ticker", auto_adjust=True, progress=False,
                         attempts=FETCH_RETRY_ATTEMPTS, base_delay=FETCH_RETRY_BASE_DELAY,
                         label=f"get_daily_data_batch({len(tickers)} tickers)")
    except Exception as exc:
        log.error("get_daily_data_batch failed for %d ticker(s) after %d attempt(s): %s",
                   len(tickers), FETCH_RETRY_ATTEMPTS, exc)
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
#: call, regardless of which batch asked for it. Same in-memory
#: {ticker: (value, fetched_at)} shape as _price_cache, just fed by the
#: batch path instead of the single-ticker one.
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


def get_current_price_batch(tickers: list, *, allow_stale: bool = True) -> dict:
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
        current = {
            ticker: cached[0]
            for ticker in tickers
            if (cached := _last_good_batch_price.get(ticker))
            and now - cached[1] < _BATCH_PRICE_CACHE_TTL_SECONDS
        }
        if len(current) == len(tickers):
            return current
    try:
        raw = yf.download(" ".join(tickers), period="1d", interval="1m",
                          group_by="ticker", prepost=True, progress=False)
    except Exception as exc:
        log.error("get_current_price_batch failed for %d ticker(s): %s", len(tickers), exc)
        return _stale_batch_fallback(tickers, now) if allow_stale else {}
    if raw is None or raw.empty:
        return _stale_batch_fallback(tickers, now) if allow_stale else {}
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
                _last_good_batch_price[ticker] = (price, now)
    # Tickers THIS batch call missed (a partial failure, not the all-or-
    # nothing case above) still get a stale-fallback chance individually.
    missing = [t for t in tickers if t not in out]
    if missing and allow_stale:
        out.update(_stale_batch_fallback(missing, now))
    return out


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
    except Exception:
        log.debug("Could not save ticker_meta_cache.json", exc_info=True)


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
    name = None
    for candidate in candidate_symbols(ticker_key):
        try:
            info = yf.Ticker(candidate).info
            name = info.get("longName") or info.get("shortName")
            if name:
                break
        except Exception:
            continue

    _company_name_cache[ticker_key] = name
    _save_ticker_meta_cache()  # persist so this network call isn't repeated after the next restart
    return name


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
        except Exception:
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
    code = _resolve_currency_code(ticker_key)
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
_price_cache: dict[str, tuple[float, float]] = {}   # ticker -> (price, fetched_at monotonic)


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
        except Exception:
            continue
    return None


def get_current_price(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS,
                      *, allow_stale: bool = True) -> float | None:
    """
    Returns the latest traded price for `ticker`, including premarket and
    aftermarket sessions.

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
    """
    ticker_key = ticker.upper().strip()
    cached = _price_cache.get(ticker_key)
    now = time.monotonic()
    # A fresh cache entry is a recent market observation for every caller.
    # ``allow_stale=False`` excludes only the expired last-known-good fallback
    # below; otherwise a trading transition needlessly refetches a quote that
    # was observed moments ago.
    if cached and (now - cached[1]) < ttl_seconds:
        return cached[0]

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
                    _price_cache[ticker_key] = (price, now)
                    return price
        except Exception:
            pass

        # Fallback: fast_info is cheaper but may be stale during extended hours
        try:
            fi = yf.Ticker(candidate).fast_info
            price = _fast_info_price(fi)
            if price:
                _price_cache[ticker_key] = (price, now)
                return price
        except Exception:
            continue

    # Serve last known-good price on transient failure rather than blanking
    # the UI -- to display callers only (see the docstring).
    if cached and allow_stale:
        return cached[0]
    return None


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
    ``get_current_price`` now hit ``_price_cache`` rather than downloading
    every ticker again.
    """
    del max_workers
    unique = list(dict.fromkeys(t.upper().strip() for t in tickers if t and t.strip()))
    if not unique:
        return
    try:
        prices = get_current_price_batch(unique)
    except Exception as exc:
        log.debug("prefetch_prices batch failed: %s", exc)
        return
    now = time.monotonic()
    for ticker, price in prices.items():
        if price and price > 0:
            _price_cache[ticker.upper().strip()] = (float(price), now)

