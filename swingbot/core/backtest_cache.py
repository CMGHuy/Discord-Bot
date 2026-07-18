"""OHLCV backtest cache: one CSV per ticker under data/backtest_cache/,
daily bars from the beginning of the ticker's history until now.

This is the single source of truth for the cache's location, filename
scheme, and CSV shape (Date index + Open/High/Low/Close/Volume,
split/dividend adjusted). Both the one-time bulk populator
(scripts/fetch_backtest_data.py) and the auto-cache-on-add path import from
here so the two can never drift.

`ensure_cached_background()` is the entry point wired into the watchlist add
surfaces (Discord `!watchlist add`, the admin single-add and bulk-import
routes): it fetches a newly added ticker's full history without blocking the
caller, and works in both the bot process and the separate Flask admin
process because it uses a plain daemon thread, not the asyncio loop.
"""
import logging
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from swingbot import config

log = logging.getLogger("swing-bot.backtest_cache")

CACHE_DIR = Path(config.DATA_DIR) / "backtest_cache"
# Below this many daily bars a ticker can't clear the backtest warm-up
# (200-SMA + 120-bar shift); we still cache it, just flag it as too short.
BACKTEST_MIN_BARS = 260


@dataclass
class CacheResult:
    ticker: str
    status: str  # "ok" | "skipped" | "failed"
    bars: int = 0
    note: str = ""


def cache_path(ticker: str) -> Path:
    safe = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}.csv"


def is_cached(ticker: str) -> bool:
    return cache_path(ticker).exists()


def normalize_ohlcv(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Canonical cache shape: Date index + Open/High/Low/Close/Volume.
    Flattens yfinance's MultiIndex columns. Returns None on empty input.
    Shared by the bulk populator script and the auto-cache path."""
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df


def fetch(ticker: str) -> pd.DataFrame | None:
    """Full available daily history (IPO -> now), split/dividend adjusted,
    normalized to the cache's canonical shape. Returns None on empty."""
    import yfinance as yf  # local import: keeps module import cheap + test-safe

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.download(ticker, period="max", auto_adjust=True, progress=False)
    return normalize_ohlcv(df)


def ensure_cached(ticker: str, force: bool = False) -> CacheResult:
    """Fetch and cache a ticker's full history if not already cached.
    Blocking. Never raises -- failures come back as CacheResult(status=failed).
    Unlike the backtest bar-count gate, this caches whatever history exists
    (a brand-new IPO still gets a file), noting when it's too short to backtest."""
    ticker = ticker.upper()
    if is_cached(ticker) and not force:
        return CacheResult(ticker, "skipped", note="already cached")
    try:
        df = fetch(ticker)
    except Exception as e:  # network / bad symbol / yfinance internals
        log.warning("backtest cache fetch failed for %s: %s", ticker, e)
        return CacheResult(ticker, "failed", note=str(e))
    if df is None or df.empty:
        log.warning("backtest cache: no data for %s (empty response)", ticker)
        return CacheResult(ticker, "failed", note="no data")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path(ticker))
    bars = len(df)
    note = "" if bars >= BACKTEST_MIN_BARS else f"only {bars} bars -- too short to backtest yet"
    log.info(
        "backtest cache: %s %d bars (%s -> %s)%s",
        ticker, bars, df.index[0].date(), df.index[-1].date(),
        f" [{note}]" if note else "",
    )
    return CacheResult(ticker, "ok", bars=bars, note=note)


def ensure_cached_background(ticker: str) -> threading.Thread:
    """Fire-and-forget: cache the ticker on a daemon thread, log the result.
    Returns the thread (mainly so tests can join it). Skips instantly if the
    ticker is already cached without spawning network work."""
    ticker = ticker.upper()
    if is_cached(ticker):
        log.debug("backtest cache: %s already cached, skipping background fetch", ticker)
        # Still spawn-and-return a no-op thread so callers get a uniform type.
        t = threading.Thread(target=lambda: None, daemon=True)
        t.start()
        return t

    def _run():
        ensure_cached(ticker)

    t = threading.Thread(target=_run, name=f"cache-{ticker}", daemon=True)
    t.start()
    return t
