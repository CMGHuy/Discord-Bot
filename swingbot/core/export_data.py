"""
Exports full historical data for every ticker in the watchlist:
  - raw OHLCV as CSV (complete history yfinance has, via period="max")
  - a candlestick chart image (PNG) for visual review

Charts are rendered with mplfinance. Full history for a mature stock can be
thousands of daily candles, which is unreadable squeezed into one image, so
each ticker gets two charts: one zoomed to the last ~2 years (readable
candle-by-candle) and one full-history overview (line-style, for the long
view). The CSV always has the complete history regardless.

The bulk scraping functions below (export_full_history_csv_only,
scrape_watchlist_history) are inspired by gunjannandy/stock-market-scraper
(https://github.com/gunjannandy/stock-market-scraper, MIT licensed) --
specifically two ideas from it, adapted on top of yfinance rather than
its own hand-rolled requests to Yahoo's chart API:
  1. "All time" means literally the full available range -- that repo
     requests Yahoo's chart endpoint with period1=0 (epoch) and a huge
     period2, which is exactly what yfinance's period="max" already
     does under the hood; fetch_full_history() below already used it.
  2. For scraping an entire watchlist rather than one ticker, it
     downloads with multithreading, and skips a ticker entirely if a
     data file for it already exists and is non-empty, rather than
     re-fetching everything on every run. scrape_watchlist_history()
     below does the same two things: a bounded ThreadPoolExecutor for
     concurrent fetches (network-bound, so real speedup, not fake
     parallelism), and skips a ticker's fetch if its CSV already exists
     and is fresh (see CACHE_MAX_AGE_HOURS) -- daily bars don't change
     until the next session closes, so re-downloading a ticker's entire
     history more than once a day is pure waste.
"""
import concurrent.futures
import os
import time

import matplotlib
matplotlib.use("Agg")  # headless rendering, no display needed
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import yfinance as yf

from .ticker_utils import candidate_symbols

# How many tickers to fetch from Yahoo Finance at once during a bulk
# watchlist scrape. Each fetch is network-bound (waiting on Yahoo's
# response), so this is real concurrency, not CPU contention -- but kept
# modest and easy to tune here, rather than hammering Yahoo with dozens
# of simultaneous requests for a large watchlist.
BULK_SCRAPE_MAX_WORKERS = 5

# A ticker's cached full-history CSV is considered fresh (and its fetch
# skipped) if it's younger than this. Daily bars only change once a
# session closes, so once a day is already generous -- default matches
# roughly one trading session plus a safety margin.
CACHE_MAX_AGE_HOURS = 20


def fetch_full_history(ticker: str) -> pd.DataFrame:
    tried = []
    for candidate in candidate_symbols(ticker):
        tried.append(candidate)
        try:
            df = yf.download(candidate, period="max", interval="1d", progress=False, auto_adjust=True)
        except Exception:
            continue
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
    raise ValueError(f"No historical data returned for '{ticker}'. Tried: {', '.join(tried)}.")


def save_csv(df: pd.DataFrame, ticker: str, out_dir: str) -> str:
    path = os.path.join(out_dir, f"{ticker}_historical.csv")
    df.to_csv(path)
    return path


_DISCLAIMER_TEXT = "Not financial advice — for informational purposes only. Trade at your own risk."


def _save_with_disclaimer(fig, path: str) -> None:
    """
    Stamps the same fine-print disclaimer trade_chart.py's alert/trade charts
    carry onto these plain historical exports too, then saves. Uses
    returnfig=True + a manual fig.savefig() (instead of mpf.plot's own
    savefig=dict(...) kwarg) specifically so there's a fig handle to draw
    this onto before the image is written.
    """
    fig.text(0.5, -0.02, _DISCLAIMER_TEXT, ha="center", va="top", fontsize=7, color="#5a6169", alpha=0.9)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def save_recent_candlestick_chart(df: pd.DataFrame, ticker: str, out_dir: str, lookback_days: int = 504) -> str:
    """Readable candlestick chart of the most recent ~2 years."""
    recent = df.tail(lookback_days)
    path = os.path.join(out_dir, f"{ticker}_candles_recent.png")
    fig, _ = mpf.plot(
        recent,
        type="candle",
        style="yahoo",
        title=f"{ticker} — last {len(recent)} trading days",
        volume=True,
        mav=(20, 50),
        returnfig=True,
    )
    _save_with_disclaimer(fig, path)
    return path


def save_full_history_chart(df: pd.DataFrame, ticker: str, out_dir: str) -> str:
    """Full-history overview as a line/OHLC chart (too many bars for readable candles)."""
    path = os.path.join(out_dir, f"{ticker}_full_history.png")
    chart_type = "candle" if len(df) <= 800 else "line"
    fig, _ = mpf.plot(
        df,
        type=chart_type,
        style="yahoo",
        title=f"{ticker} — full history ({len(df)} trading days)",
        volume=True,
        returnfig=True,
    )
    _save_with_disclaimer(fig, path)
    return path


def export_ticker(ticker: str, out_dir: str) -> dict:
    """Fetch, save CSV + both charts for one ticker. Returns paths."""
    os.makedirs(out_dir, exist_ok=True)
    df = fetch_full_history(ticker)
    csv_path = save_csv(df, ticker, out_dir)
    recent_chart = save_recent_candlestick_chart(df, ticker, out_dir)
    full_chart = save_full_history_chart(df, ticker, out_dir)
    return {
        "ticker": ticker,
        "bars": len(df),
        "csv": csv_path,
        "recent_chart": recent_chart,
        "full_chart": full_chart,
    }


def _csv_is_fresh(path: str, max_age_hours: float) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < max_age_hours


def export_full_history_csv_only(ticker: str, out_dir: str, force: bool = False,
                                  cache_max_age_hours: float = CACHE_MAX_AGE_HOURS) -> dict:
    """
    CSV-only sibling of export_ticker() -- no chart rendering -- for
    bulk multi-ticker scraping where the goal is the raw data for every
    ticker, not a chart per ticker (those stay available individually
    via !charts / !download). Skips the network fetch entirely and
    reads the existing file instead if a fresh CSV is already on disk,
    unless force=True.

    Returns a dict with ticker/bars/csv/start/end/from_cache. Raises on
    a genuine fetch failure (caller -- scrape_watchlist_history --
    catches this per-ticker so one bad ticker doesn't abort the batch).
    """
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, f"{ticker}_historical.csv")

    if not force and _csv_is_fresh(csv_path, cache_max_age_hours):
        df = pd.read_csv(csv_path, index_col=0)
        return {
            "ticker": ticker, "bars": len(df), "csv": csv_path, "from_cache": True,
            "start": str(df.index[0])[:10] if len(df) else None,
            "end": str(df.index[-1])[:10] if len(df) else None,
        }

    df = fetch_full_history(ticker)
    csv_path = save_csv(df, ticker, out_dir)
    return {
        "ticker": ticker, "bars": len(df), "csv": csv_path, "from_cache": False,
        "start": str(df.index[0])[:10] if len(df) else None,
        "end": str(df.index[-1])[:10] if len(df) else None,
    }


def scrape_watchlist_history(tickers: list, out_dir: str, max_workers: int = BULK_SCRAPE_MAX_WORKERS,
                              force: bool = False, cache_max_age_hours: float = CACHE_MAX_AGE_HOURS,
                              on_ticker_done=None) -> list:
    """
    Downloads full ("all time", period="max") daily history for every
    ticker in `tickers` at once, concurrently, via a bounded thread
    pool -- see the module docstring for the stock-market-scraper ideas
    this borrows (multithreaded bulk download + skip-if-already-fetched
    caching), adapted on top of yfinance.

    `on_ticker_done(ticker, ok: bool)`, if given, is called from a
    worker thread as each ticker finishes -- for a live progress
    counter in the caller; keep it fast and thread-safe (e.g. just
    incrementing a counter), since it runs inside the pool.

    Returns a list of per-ticker result dicts, in the SAME order as
    `tickers` (not completion order), so a summary table lines up with
    however the caller wants to present it. A ticker whose fetch failed
    gets {"ticker": ..., "error": "..."} instead of the normal result
    shape -- one bad ticker (delisted, typo'd, rate-limited) doesn't
    abort the rest of the batch.
    """
    results = [None] * len(tickers)

    def _worker(i, ticker):
        try:
            info = export_full_history_csv_only(ticker, out_dir, force=force, cache_max_age_hours=cache_max_age_hours)
            info["error"] = None
            ok = True
        except Exception as e:
            info = {"ticker": ticker, "error": str(e)}
            ok = False
        if on_ticker_done:
            try:
                on_ticker_done(ticker, ok)
            except Exception:
                pass
        return i, info

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, i, t) for i, t in enumerate(tickers)]
        for future in concurrent.futures.as_completed(futures):
            i, info = future.result()
            results[i] = info

    return results
