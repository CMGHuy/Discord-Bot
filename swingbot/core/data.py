"""Fetches daily OHLC data for a ticker."""
import io
import json
import logging
import os
import time
import urllib.request

import pandas as pd
import yfinance as yf

from .ticker_utils import candidate_symbols

log = logging.getLogger(__name__)


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
            df = yf.download(candidate, period=period, interval="1d", progress=False, auto_adjust=True)
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
    path = _ticker_meta_cache_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, "r") as f:
            data = json.load(f)
        _currency_cache.update(data.get("currency_symbols", {}))
        _company_name_cache.update(data.get("company_names", {}))
    except Exception:
        log.debug("Could not load ticker_meta_cache.json -- starting with an empty cache.", exc_info=True)


def _save_ticker_meta_cache():
    path = _ticker_meta_cache_path()
    try:
        with open(path, "w") as f:
            json.dump({
                "currency_symbols": _currency_cache,
                "company_names": _company_name_cache,
            }, f, indent=2, sort_keys=True)
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
    from .ticker_directory import lookup_name  # avoid circular import at module level

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


def get_current_price(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS) -> float | None:
    """
    Returns the latest traded price for `ticker`, including premarket and
    aftermarket sessions.

    Primary source: 1-minute history with prepost=True — this always returns
    the most recently traded price in any session and is the most accurate.
    Fallback: fast_info attributes for when the history call fails (e.g.
    network timeout, symbol not found in history endpoint).

    Cached in-memory per ticker for `ttl_seconds` (default 15s).
    """
    ticker_key = ticker.upper().strip()
    cached = _price_cache.get(ticker_key)
    now = time.monotonic()
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

    # Serve last known-good price on transient failure rather than blanking the UI
    if cached:
        return cached[0]
    return None


def is_us_market_active() -> bool:
    """
    Returns True when any US equity market session is currently open:
      Pre-market:  4:00 AM – 9:30 AM  ET
      Regular:     9:30 AM – 4:00 PM  ET
      After-hours: 4:00 PM – 8:00 PM  ET
    Returns False on weekends and between 8 PM and 4 AM ET.
    Uses a simple DST approximation (months 3–11 = EDT, otherwise EST).
    """
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:          # Saturday or Sunday
        return False
    # Approximate ET offset: Mar–Nov = UTC-4 (EDT), Dec–Feb = UTC-5 (EST)
    et_offset = -4 if 3 <= now_utc.month <= 11 else -5
    et_hour = (now_utc.hour + et_offset) % 24
    et_min  = now_utc.minute
    et_t    = et_hour * 60 + et_min     # minutes since midnight ET
    # Active window: 4:00 AM (t=240) through 8:00 PM (t=1200)
    return 4 * 60 <= et_t < 20 * 60


def prefetch_prices(tickers: list[str], max_workers: int = 10) -> None:
    """
    Warm the price cache for a list of tickers in parallel.
    Call this before `get_current_price` in a render loop so all fetches
    happen concurrently instead of sequentially.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    unique = list({t.upper().strip() for t in tickers if t})
    if not unique:
        return
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as pool:
        futures = [pool.submit(get_current_price, tk) for tk in unique]
        for fut in as_completed(futures):
            fut.result()  # discard -- side-effect is populating _price_cache

