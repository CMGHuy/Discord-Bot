"""
Local historical data cache.

Downloads OHLCV data at any supported interval and saves it to disk under
market_data/{TICKER}/{interval}.csv, so backtests, chart exports, and
re-downloads don't have to keep re-fetching from Yahoo Finance.

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
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from .ticker_utils import candidate_symbols

DATA_DIR = "market_data"

# max_days = how far back Yahoo will serve this interval at all
# chunk_days = max span allowed in a single request (chunk to cover max_days)
INTERVAL_CONFIG = {
    "1m":  {"max_days": 30, "chunk_days": 7},
    "2m":  {"max_days": 60, "chunk_days": 60},
    "5m":  {"max_days": 60, "chunk_days": 60},
    "15m": {"max_days": 60, "chunk_days": 60},
    "30m": {"max_days": 60, "chunk_days": 60},
    "60m": {"max_days": 730, "chunk_days": 730},
    "90m": {"max_days": 60, "chunk_days": 60},
    "1d":  {"max_days": None, "chunk_days": None},
}


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


def fetch_interval_data(ticker: str, interval: str = "1m") -> pd.DataFrame:
    cfg = INTERVAL_CONFIG.get(interval)
    if cfg is None:
        raise ValueError(f"Unsupported interval '{interval}'. Use one of: {', '.join(INTERVAL_CONFIG)}")

    tried = []
    for candidate in candidate_symbols(ticker):
        tried.append(candidate)
        try:
            if cfg["max_days"] is None:
                df = yf.download(candidate, period="max", interval=interval, progress=False, auto_adjust=True)
            elif cfg["chunk_days"] >= cfg["max_days"]:
                df = yf.download(candidate, period=f"{cfg['max_days']}d", interval=interval, progress=False, auto_adjust=True)
            else:
                df = _chunked_fetch(candidate, interval, cfg["max_days"], cfg["chunk_days"])
        except Exception:
            continue
        if df is not None and not df.empty:
            return _normalize_columns(df)

    raise ValueError(f"No {interval} data returned for '{ticker}'. Tried: {', '.join(tried)}.")


def cache_path(ticker: str, interval: str, base_dir: str = DATA_DIR) -> str:
    d = os.path.join(base_dir, ticker.upper())
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{interval}.csv")


def save_to_disk(df: pd.DataFrame, ticker: str, interval: str, base_dir: str = DATA_DIR) -> str:
    path = cache_path(ticker, interval, base_dir)
    df.to_csv(path)
    return path


def load_from_disk(ticker: str, interval: str, base_dir: str = DATA_DIR) -> pd.DataFrame | None:
    path = cache_path(ticker, interval, base_dir)
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def download_and_cache(ticker: str, interval: str = "1m", base_dir: str = DATA_DIR) -> dict:
    df = fetch_interval_data(ticker, interval)
    path = save_to_disk(df, ticker, interval, base_dir)
    cfg = INTERVAL_CONFIG[interval]
    return {
        "ticker": ticker,
        "interval": interval,
        "rows": len(df),
        "start": str(df.index.min()),
        "end": str(df.index.max()),
        "path": path,
        "max_days_available": cfg["max_days"],  # None means full history
    }
