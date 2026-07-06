"""Fetches daily OHLC data for a ticker."""
import io
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
    for candidate in candidate_symbols(ticker_key):
        try:
            info = yf.Ticker(candidate).info
            name = info.get("longName") or info.get("shortName")
            if name:
                break
        except Exception:
            continue

    _company_name_cache[ticker_key] = name
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
    return symbol


# ---------------------------------------------------------------------------
# Live price fetching (admin dashboard trade-health status)
# ---------------------------------------------------------------------------

# How long a fetched price is trusted before the next call re-fetches it.
# The admin dashboard polls its HTML fragment every 5s (see app.py's
# dashboard auto-refresh), but re-hitting yfinance for every open trade
# on every one of those polls would be both wasteful and slow -- a 60s
# TTL means the underlying price (and therefore the trade-health status
# color) only actually changes about once a minute, matching what the
# dashboard asked for, while the fragment itself can still re-render
# every 5s for everything else (new trades, stat counts, etc.).
_PRICE_CACHE_TTL_SECONDS = 15
_price_cache: dict[str, tuple[float, float]] = {}   # ticker -> (price, fetched_at monotonic)


def get_current_price(ticker: str, ttl_seconds: int = _PRICE_CACHE_TTL_SECONDS) -> float | None:
    """
    Returns the latest traded price for `ticker`, or None if it can't be
    fetched. Uses yfinance's `fast_info` (a lightweight quote endpoint)
    rather than `get_daily_data`'s full OHLCV history download -- this is
    called once per open trade on every dashboard render, so it needs to
    stay cheap. Cached in-memory per ticker for `ttl_seconds` (default
    60s) so repeated calls within that window return instantly without
    another network round-trip.
    """
    ticker_key = ticker.upper().strip()
    cached = _price_cache.get(ticker_key)
    now = time.monotonic()
    if cached and (now - cached[1]) < ttl_seconds:
        return cached[0]

    for candidate in candidate_symbols(ticker_key):
        try:
            fast_info = yf.Ticker(candidate).fast_info
            price = fast_info.get("lastPrice") if hasattr(fast_info, "get") else getattr(fast_info, "last_price", None)
            if price:
                price = float(price)
                _price_cache[ticker_key] = (price, now)
                return price
        except Exception:
            continue

    # Nothing resolved -- keep serving the last known-good price (if any)
    # rather than blanking the status out just because of a transient
    # fetch failure; only actually returns None the very first time.
    if cached:
        return cached[0]
    return None


def prefetch_prices(tickers: list[str], max_workers: int = 10) -> None:
    """
    Warm the price cache for a list of tickers in parallel.
    Call this before `get_current_price` in a render loop so all fetches
    happen concurrently instead of sequentially -- the loop then hits the
    cache on every call and returns instantly.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    unique = list({t.upper().strip() for t in tickers if t})
    if not unique:
        return
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as pool:
        futures = [pool.submit(get_current_price, tk) for tk in unique]
        for fut in as_completed(futures):
            fut.result()  # discard — side-effect is populating _price_cache


# ---------------------------------------------------------------------------
# Stock logo fetching
# ---------------------------------------------------------------------------

# Logo cache dir — logos are saved to disk so we don't re-download on every
# chart generation.  The directory is created on first use.
_LOGO_CACHE: dict[str, str | None] = {}   # ticker -> local path or None
# Separate from _LOGO_CACHE so a real ticker that just doesn't HAVE a logo
# (an index like ^GSPC, a future like GC=F -- legitimately no logo, no
# point retrying) isn't confused with a merely TRANSIENT failure (a
# timeout, a DNS hiccup) -- without this, the first attempt's outcome for
# ANY reason got cached as a permanent "don't bother again" for the rest
# of the process's lifetime. Transient failures get retried after this
# many seconds; a ticker that fails again just gets the same short TTL
# again, so a genuinely logo-less ticker still doesn't retry on every
# single call, just periodically instead of never.
_LOGO_FAIL_RETRY_SECONDS = 3600
_LOGO_FAIL_TIME: dict[str, float] = {}


def _logo_cache_dir() -> str:
    from swingbot import config
    d = os.path.join(config.DATA_DIR, "logos")
    os.makedirs(d, exist_ok=True)
    return d


def _fetch_logo_url(ticker: str) -> str | None:
    """Try several sources to find a square logo URL for `ticker`."""
    # 1. yfinance info (works for many tickers but is slow)
    for candidate in candidate_symbols(ticker):
        try:
            info = yf.Ticker(candidate).info
            # yfinance >= 0.2 puts it in "logoUrl" or "logo_url"
            url = info.get("logoUrl") or info.get("logo_url")
            if url and url.startswith("http"):
                return url
            # Fall back to Clearbit using the company website domain
            website = info.get("website", "")
            if website:
                import urllib.parse
                domain = urllib.parse.urlparse(website).netloc.lstrip("www.")
                if domain:
                    return f"https://logo.clearbit.com/{domain}"
        except Exception:
            continue
    return None


def get_ticker_logo(ticker: str) -> "PIL.Image.Image | None":
    """
    Return a PIL Image of the stock's logo (≤64×64 px, RGBA), or None if
    it can't be fetched.  Results are cached to disk so repeated calls
    for the same ticker are instant.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    ticker_key = ticker.upper().strip()
    if ticker_key in _LOGO_CACHE:
        cached_path = _LOGO_CACHE[ticker_key]
        if cached_path and os.path.exists(cached_path):
            try:
                return Image.open(cached_path).convert("RGBA")
            except Exception:
                pass
        # A previous attempt failed. Only treat that as still valid within
        # the retry window -- past it, fall through and try again instead
        # of caching a transient failure (a timeout, a DNS hiccup) as
        # permanent for the rest of the process's lifetime.
        failed_at = _LOGO_FAIL_TIME.get(ticker_key, 0.0)
        if time.monotonic() - failed_at < _LOGO_FAIL_RETRY_SECONDS:
            return None
        _LOGO_CACHE.pop(ticker_key, None)

    cache_dir = _logo_cache_dir()
    local_path = os.path.join(cache_dir, f"{ticker_key}.png")

    # Return from disk cache if already downloaded
    if os.path.exists(local_path):
        try:
            img = Image.open(local_path).convert("RGBA")
            _LOGO_CACHE[ticker_key] = local_path
            return img
        except Exception:
            pass

    # Download
    try:
        url = _fetch_logo_url(ticker_key)
        if not url:
            _LOGO_CACHE[ticker_key] = None
            _LOGO_FAIL_TIME[ticker_key] = time.monotonic()
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "swingbot/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        # Resize to at most 64×64 keeping aspect ratio
        img.thumbnail((64, 64), Image.LANCZOS)
        img.save(local_path, "PNG")
        _LOGO_CACHE[ticker_key] = local_path
        log.debug("Logo downloaded for %s → %s", ticker_key, local_path)
        return img
    except Exception as exc:
        log.debug("Logo fetch failed for %s: %s", ticker_key, exc)
        _LOGO_CACHE[ticker_key] = None
        _LOGO_FAIL_TIME[ticker_key] = time.monotonic()
        return None


def get_logo_path(ticker: str) -> str | None:
    """
    Ensures `ticker`'s logo is downloaded/cached (see get_ticker_logo above),
    then returns the local PNG file path -- or None if no logo could be
    found for it. Used by the admin UI to serve `<img src>` tags by
    streaming the cached file directly, instead of re-decoding/re-encoding
    the image on every page load.
    """
    img = get_ticker_logo(ticker)
    if img is None:
        return None
    ticker_key = ticker.upper().strip()
    path = os.path.join(_logo_cache_dir(), f"{ticker_key}.png")
    return path if os.path.exists(path) else None
