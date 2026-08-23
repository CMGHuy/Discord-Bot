"""
Local historical data cache.

Downloads OHLCV data at any supported interval and saves it to disk under
market_data/{timeframe}/{TICKER}.csv -- grouped by candle timeframe
("monthly", "weekly", "daily", "hourly", "15min", ...) so a training run can
point at one folder and get every symbol at that granularity, rather than
walking 500+ per-ticker directories.

Callers may pass EITHER the semantic folder name ("hourly") or the yfinance
interval code ("1h"/"60m") anywhere an `interval` is accepted -- both resolve
to the same folder, so existing call sites did not have to change.

IMPORTANT -- Yahoo Finance's real intraday depth limits (not a choice we're
making, this is what their API actually allows):
  - 1m               : only the trailing ~30 days, max 7 days per request
  - 2m/5m/15m/30m/90m : only the trailing ~60 days
  - 60m/1h            : only the trailing ~730 days (~2 years)
  - 1d and coarser     : full history

There is no way to get "1-minute candles for the whole history" of a stock
from Yahoo Finance -- that data isn't available for free anywhere at that
granularity going back years. `download_and_cache('1m')` pulls the maximum
Yahoo actually has (~30 days) and says so plainly in the result.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from swingbot.core.marketdata.ticker_utils import candidate_symbols

log = logging.getLogger("swing-bot.data_store")

DATA_DIR = "market_data"

# Semantic timeframe -> the yfinance interval code and Yahoo's real depth.
# folder    = subdirectory under market_data/ (what training runs point at)
# interval  = the code actually sent to yfinance
# max_days  = how far back Yahoo will serve this interval at all (None = full)
# chunk_days= max span allowed in one request (chunk to cover max_days)
TIMEFRAMES = {
    "monthly": {"interval": "1mo", "max_days": None, "chunk_days": None},
    "weekly":  {"interval": "1wk", "max_days": None, "chunk_days": None},
    "daily":   {"interval": "1d",  "max_days": None, "chunk_days": None},
    "hourly":  {"interval": "1h",  "max_days": 730,  "chunk_days": 730},
    "90min":   {"interval": "90m", "max_days": 60,   "chunk_days": 60},
    "30min":   {"interval": "30m", "max_days": 60,   "chunk_days": 60},
    "15min":   {"interval": "15m", "max_days": 60,   "chunk_days": 60},
    "5min":    {"interval": "5m",  "max_days": 60,   "chunk_days": 60},
    "2min":    {"interval": "2m",  "max_days": 60,   "chunk_days": 60},
    "1min":    {"interval": "1m",  "max_days": 30,   "chunk_days": 7},
}

# The four the bot auto-refreshes: the only ones with enough depth to train
# on. Everything below hourly is capped at 30-60 days by Yahoo and is for
# live entry timing, not history.
TRAINING_TIMEFRAMES = ("monthly", "weekly", "daily", "hourly")

# Every accepted spelling -> canonical folder name. Both the semantic name
# and the yfinance code resolve here, so old call sites passing "1h"/"1d"
# keep working unchanged.
_TIMEFRAME_ALIASES = {}
for _name, _cfg in TIMEFRAMES.items():
    _TIMEFRAME_ALIASES[_name] = _name
    _TIMEFRAME_ALIASES[_cfg["interval"]] = _name
_TIMEFRAME_ALIASES["60m"] = "hourly"   # Yahoo's other spelling of 1h

# Back-compat: keyed by BOTH spellings so `!download 1h` and `!download
# hourly` both validate. Values carry the same max_days/chunk_days shape
# this module has always exposed.
INTERVAL_CONFIG = {
    alias: TIMEFRAMES[canonical]
    for alias, canonical in _TIMEFRAME_ALIASES.items()
}


def timeframe_name(interval: str) -> str:
    """Canonical folder name for any accepted interval spelling."""
    key = str(interval).strip().lower()
    name = _TIMEFRAME_ALIASES.get(key)
    if name is None:
        raise ValueError(
            f"Unsupported interval '{interval}'. Use a timeframe name "
            f"({', '.join(TIMEFRAMES)}) or a yfinance code "
            f"({', '.join(c['interval'] for c in TIMEFRAMES.values())})."
        )
    return name


def yf_interval(interval: str) -> str:
    """The code to actually send to yfinance for any accepted spelling."""
    return TIMEFRAMES[timeframe_name(interval)]["interval"]


def safe_symbol(ticker: str) -> str:
    """Filesystem-safe filename stem. Mirrors backtest_cache.cache_path's
    scheme so `GC=F` lands as GC_F.csv in both caches, not a stray folder."""
    return ticker.upper().strip().replace("=", "_").replace("^", "_").replace("/", "_")


def chunk_windows(max_days: int, chunk_days: int, now: datetime = None):
    """
    Pure helper (no network) that yields (start, end) datetime windows
    covering the last `max_days`, each no wider than `chunk_days`, newest
    first. Split out for easy testing.
    """
    now = now or datetime.now(timezone.utc)
    floor = now - timedelta(days=max_days)
    windows = []
    chunk_end = now
    while chunk_end > floor:
        chunk_start = max(chunk_end - timedelta(days=chunk_days), floor)
        windows.append((chunk_start, chunk_end))
        chunk_end = chunk_start
    return windows


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _chunked_fetch(ticker: str, interval: str, max_days: int, chunk_days: int) -> pd.DataFrame:
    frames = []
    for start, end in chunk_windows(max_days, chunk_days):
        df = yf.download(ticker, start=start, end=end, interval=interval, progress=False, auto_adjust=True)
        if df is not None and not df.empty:
            frames.append(_normalize_columns(df))
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined


def _capped_attempts(max_days: int):
    """Request shapes for a depth-capped interval, widest first.

    `period=<max_days>d` empirically returns MORE than max_days of calendar
    history (Yahoo serves ~max_days of *trading* days), so it is tried first.
    But for a symbol that listed inside the window yfinance clamps the start
    to the listing date and Yahoo rejects the whole request -- so an
    explicitly in-window start/end is the fallback that makes recent
    listings work at all.
    """
    now = datetime.now(timezone.utc)
    safe_start = now - timedelta(days=max_days - 2)
    return [
        {"period": f"{max_days}d"},
        {"start": safe_start.strftime("%Y-%m-%d"), "end": now.strftime("%Y-%m-%d")},
    ]


def fetch_interval_data(ticker: str, interval: str = "1d") -> pd.DataFrame:
    cfg = TIMEFRAMES[timeframe_name(interval)]
    code = cfg["interval"]

    tried = []
    for candidate in candidate_symbols(ticker):
        tried.append(candidate)
        try:
            if cfg["max_days"] is None:
                df = yf.download(candidate, period="max", interval=code,
                                 progress=False, auto_adjust=True)
            elif cfg["chunk_days"] >= cfg["max_days"]:
                df = None
                for kwargs in _capped_attempts(cfg["max_days"]):
                    df = yf.download(candidate, interval=code, progress=False,
                                     auto_adjust=True, **kwargs)
                    if df is not None and not df.empty:
                        break
            else:
                df = _chunked_fetch(candidate, code, cfg["max_days"], cfg["chunk_days"])
        except Exception:
            continue
        if df is not None and not df.empty:
            return _normalize_columns(df)

    raise ValueError(f"No {interval} data returned for '{ticker}'. Tried: {', '.join(tried)}.")


def cache_path(ticker: str, interval: str, base_dir: str = DATA_DIR) -> str:
    """market_data/{timeframe}/{TICKER}.csv -- grouped by candle timeframe."""
    d = os.path.join(base_dir, timeframe_name(interval))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{safe_symbol(ticker)}.csv")


def save_to_disk(df: pd.DataFrame, ticker: str, interval: str, base_dir: str = DATA_DIR) -> str:
    path = cache_path(ticker, interval, base_dir)
    df.to_csv(path)
    return path


def load_from_disk(ticker: str, interval: str, base_dir: str = DATA_DIR) -> pd.DataFrame | None:
    path = cache_path(ticker, interval, base_dir)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def load_normalized(ticker: str, interval: str, base_dir: str = DATA_DIR) -> pd.DataFrame | None:
    """v47: load_from_disk() plus the shape guarantees a live download gives.

    The cache-first scan (core/scanning/engine.py:_crawl_latest_data) feeds
    these frames to exactly the same consumers a fresh yf.download() frame
    reaches -- market_context.attach(), refresh_rs_cache(), every indicator in
    _scan_one. A to_csv/read_csv round-trip does NOT preserve dtype or index
    tz-awareness (see data_refresh._align_tz, which exists for this reason), so
    normalizing here is what makes "read the cache instead of fetching" a
    throughput change rather than a behaviour change.

    Returns None for missing, unreadable or unusable files -- every caller
    already treats a missing frame as "no data for this ticker this scan", so a
    corrupt CSV degrades to a cache miss instead of killing the scan.
    """
    try:
        df = load_from_disk(ticker, interval, base_dir=base_dir)
    except Exception as exc:
        log.warning("cache read failed for %s/%s: %s", ticker, interval, exc)
        return None
    if df is None or df.empty:
        return None

    df = _normalize_columns(df)
    if not all(c in df.columns for c in OHLCV_COLUMNS):
        log.warning("cached frame for %s/%s is missing OHLCV columns (has %s)",
                    ticker, interval, list(df.columns))
        return None
    df = df[OHLCV_COLUMNS].astype("float64")

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception as exc:
            log.warning("cached frame for %s/%s has an unparseable index: %s",
                        ticker, interval, exc)
            return None
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()

    return df if not df.empty else None


def download_and_cache(ticker: str, interval: str = "daily", base_dir: str = DATA_DIR) -> dict:
    tf = timeframe_name(interval)
    df = fetch_interval_data(ticker, tf)
    path = save_to_disk(df, ticker, tf, base_dir)
    cfg = TIMEFRAMES[tf]
    return {
        "ticker": ticker,
        "interval": interval,
        "timeframe": tf,
        "rows": len(df),
        "start": str(df.index.min()),
        "end": str(df.index.max()),
        "path": path,
        "max_days_available": cfg["max_days"],  # None means full history
    }


def _default_ranged_fetch(symbol: str, start, interval: str = "1d") -> "pd.DataFrame | None":
    try:
        # yfinance's start= only accepts a bare date -- str() on a Timestamp
        # with a time/tz component (as every intraday `last` index value has,
        # e.g. "2026-07-24 19:30:00+00:00") produces a string yfinance's own
        # date parser can't consume. It doesn't raise: it prints "1 Failed
        # download" and hands back an empty frame, which this function then
        # (correctly, but silently) treats as "nothing new" -- so every warm
        # incremental refresh at an intraday interval was a silent no-op.
        # Normalizing to a date-only string here fetches from the start of
        # that calendar day; any bars already cached get de-duped by the
        # caller's index-based merge, so the coarser start costs nothing.
        start_date = pd.Timestamp(start).strftime("%Y-%m-%d")
        df = yf.download(symbol, start=start_date, interval=yf_interval(interval),
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        return _normalize_columns(df)
    except Exception as exc:  # network flake: skip symbol this run
        log.warning("ranged fetch %s failed: %s", symbol, exc)
        return None


def update_cache(symbols: list, interval: str = "1d", base_dir: str = DATA_DIR,
                 fetch_fn=None) -> dict:
    """Incremental cache update: fetch only bars newer than each CSV's
    last date; atomic replace so a crash mid-write never corrupts a file."""
    # Interval is bound here rather than threaded through the call: injected
    # fetch_fn's are (symbol, start) two-arg callables and must stay that way.
    fetch = fetch_fn or (lambda symbol, start: _default_ranged_fetch(symbol, start, interval))
    result = {}
    for symbol in symbols:
        existing = load_from_disk(symbol, interval, base_dir=base_dir)
        if existing is None or existing.empty:
            fresh = fetch(symbol, "2018-06-01")
            if fresh is None or fresh.empty:
                result[symbol] = 0
                continue
            save_to_disk(fresh, symbol, interval, base_dir=base_dir)
            result[symbol] = len(fresh)
            continue
        last = existing.index.max()
        # Keep as a Timestamp (not `.date()`): fetch_fn implementations may
        # compare `start` against a DatetimeIndex, and pandas raises
        # TypeError comparing datetime64 to a bare `datetime.date`.
        # `_default_ranged_fetch` stringifies this fine for yfinance either way.
        fresh = fetch(symbol, last + pd.Timedelta(days=1))
        fresh = fresh[fresh.index > last] if fresh is not None else None
        if fresh is None or fresh.empty:
            result[symbol] = 0
            continue
        merged = pd.concat([existing, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        path = cache_path(symbol, interval, base_dir=base_dir)
        tmp = path + ".tmp"
        merged.to_csv(tmp)
        os.replace(tmp, path)
        result[symbol] = len(fresh)
    return result


INTRADAY_MAX_AGE_SECONDS = 4 * 3600


def get_intraday(symbol: str, interval: str = "1h", base_dir: str = DATA_DIR,
                 fetch_fn=None) -> "pd.DataFrame | None":
    """Cached 1h bars for the E29 entry-timing annotation. NEVER required:
    every caller must treat None as 'no intraday data, stay neutral'."""
    path = cache_path(symbol, interval, base_dir=base_dir)
    fresh_enough = (os.path.exists(path)
                    and time.time() - os.path.getmtime(path) < INTRADAY_MAX_AGE_SECONDS)
    if fresh_enough:
        return load_from_disk(symbol, interval, base_dir=base_dir)

    def _default_fetch(sym, iv):
        df = yf.download(sym, period="700d", interval=iv,
                         auto_adjust=True, progress=False)
        return _normalize_columns(df) if df is not None and not df.empty else None

    try:
        df = (fetch_fn or _default_fetch)(symbol, interval)
    except Exception as exc:
        log.warning("intraday fetch %s failed: %s", symbol, exc)
        df = None
    if df is None or df.empty:
        return load_from_disk(symbol, interval, base_dir=base_dir)  # stale > nothing
    save_to_disk(df, symbol, interval, base_dir=base_dir)
    return df
