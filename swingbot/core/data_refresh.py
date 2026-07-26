"""Automatic market-data cache refresh.

Keeps market_data/{timeframe}/{TICKER}.csv current for the training
timeframes (monthly, weekly, daily, hourly) while the bot is running.

Design notes:
  - **Incremental by default.** A symbol that already has a CSV only fetches
    bars newer than its last row; a cold symbol gets the deepest history
    Yahoo will serve for that timeframe (full history for daily and coarser).
  - **Staleness-gated.** Each timeframe declares how often it is worth
    re-fetching -- refetching monthly candles every hour is pure waste --
    so a loop tick usually does nothing and costs no network.
  - **Never raises into the caller.** This runs on a bot task loop; one bad
    symbol or a rate-limited window must not kill the loop. Every failure is
    counted and logged, and the run continues.
  - **Blocking.** Contains no asyncio; the bot calls it via asyncio.to_thread
    so the event loop keeps serving Discord while it works.
"""
import logging
import os
import time

import pandas as pd

from .data_store import (
    DATA_DIR,
    TIMEFRAMES,
    TRAINING_TIMEFRAMES,
    _default_ranged_fetch,
    cache_path,
    fetch_interval_data,
    load_from_disk,
    save_to_disk,
    timeframe_name,
)

log = logging.getLogger("swing-bot.data_refresh")

# How often each timeframe is worth re-fetching. A new monthly candle only
# closes twelve times a year; an hourly one closes every session hour.
REFRESH_HOURS = {
    "monthly": 24.0,
    "weekly": 24.0,
    "daily": 12.0,
    "hourly": 4.0,
}
DEFAULT_REFRESH_HOURS = 24.0


def is_stale(symbol: str, timeframe: str, base_dir: str = DATA_DIR,
             max_age_hours: float = None) -> bool:
    """True when this symbol/timeframe is missing or old enough to re-fetch."""
    tf = timeframe_name(timeframe)
    path = cache_path(symbol, tf, base_dir=base_dir)
    if not os.path.exists(path):
        return True
    if max_age_hours is None:
        max_age_hours = REFRESH_HOURS.get(tf, DEFAULT_REFRESH_HOURS)
    age_hours = (time.time() - os.path.getmtime(path)) / 3600.0
    return age_hours >= max_age_hours


def refresh_symbol(symbol: str, timeframe: str, base_dir: str = DATA_DIR,
                   force: bool = False) -> dict:
    """Bring one symbol/timeframe up to date. Returns a result dict with
    status 'full' | 'incremental' | 'fresh' | 'skipped' | 'failed'."""
    tf = timeframe_name(timeframe)
    out = {"symbol": symbol, "timeframe": tf, "rows": 0, "added": 0}

    if not force and not is_stale(symbol, tf, base_dir=base_dir):
        existing = load_from_disk(symbol, tf, base_dir=base_dir)
        return {**out, "status": "fresh", "rows": len(existing) if existing is not None else 0}

    existing = None if force else load_from_disk(symbol, tf, base_dir=base_dir)

    # Cold (or forced): pull the deepest history this timeframe allows.
    if existing is None or existing.empty:
        try:
            df = fetch_interval_data(symbol, tf)
        except Exception as exc:
            log.warning("refresh %s/%s failed: %s", symbol, tf, exc)
            return {**out, "status": "failed", "error": str(exc)[:200]}
        save_to_disk(df, symbol, tf, base_dir=base_dir)
        return {**out, "status": "full", "rows": len(df), "added": len(df)}

    # Warm: fetch only what is newer than the last cached bar.
    last = existing.index.max()
    try:
        fresh = _default_ranged_fetch(symbol, last, tf)
    except Exception as exc:
        log.warning("incremental %s/%s failed: %s", symbol, tf, exc)
        return {**out, "status": "failed", "rows": len(existing), "error": str(exc)[:200]}

    if fresh is None or fresh.empty:
        # Nothing new, but touch the file so a closed market doesn't make
        # every tick re-request the same empty window.
        os.utime(cache_path(symbol, tf, base_dir=base_dir), None)
        return {**out, "status": "fresh", "rows": len(existing)}

    # Align tz-awareness before comparing/concatenating: intraday frames come
    # back tz-aware, daily-and-coarser naive, and a cached CSV can round-trip
    # either way depending on which timeframe wrote it.
    try:
        if fresh.index.tz is not None and existing.index.tz is None:
            fresh.index = fresh.index.tz_localize(None)
        elif fresh.index.tz is None and existing.index.tz is not None:
            existing.index = existing.index.tz_localize(None)
    except (AttributeError, TypeError):
        pass

    fresh = fresh[fresh.index > last]
    if fresh.empty:
        os.utime(cache_path(symbol, tf, base_dir=base_dir), None)
        return {**out, "status": "fresh", "rows": len(existing)}

    merged = pd.concat([existing, fresh])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()

    # Atomic replace so a crash mid-write never leaves a truncated CSV.
    path = cache_path(symbol, tf, base_dir=base_dir)
    tmp = path + ".tmp"
    merged.to_csv(tmp)
    os.replace(tmp, path)
    return {**out, "status": "incremental", "rows": len(merged), "added": len(fresh)}


def refresh_all(symbols, timeframes=TRAINING_TIMEFRAMES, base_dir: str = DATA_DIR,
                force: bool = False, sleep_seconds: float = 0.0,
                on_progress=None) -> dict:
    """Refresh every (symbol, timeframe) pair. Never raises."""
    timeframes = [timeframe_name(t) for t in timeframes]
    summary = {tf: {"full": 0, "incremental": 0, "fresh": 0, "failed": 0,
                    "added": 0} for tf in timeframes}
    failures = []

    for tf in timeframes:
        for symbol in symbols:
            try:
                r = refresh_symbol(symbol, tf, base_dir=base_dir, force=force)
            except Exception as exc:      # belt-and-braces: loop must survive
                log.warning("refresh %s/%s crashed: %s", symbol, tf, exc)
                r = {"symbol": symbol, "timeframe": tf, "status": "failed",
                     "added": 0, "error": str(exc)[:200]}
            bucket = summary[tf]
            bucket[r["status"]] = bucket.get(r["status"], 0) + 1
            bucket["added"] += r.get("added", 0)
            if r["status"] == "failed":
                failures.append((symbol, tf, r.get("error", "")))
            if on_progress:
                try:
                    on_progress(r)
                except Exception:
                    pass
            if sleep_seconds and r["status"] not in ("fresh", "skipped"):
                time.sleep(sleep_seconds)

    return {"summary": summary, "failures": failures}


def summary_line(result: dict) -> str:
    """One-line log summary of a refresh_all result."""
    parts = []
    for tf, s in result["summary"].items():
        touched = s["full"] + s["incremental"]
        if touched or s["failed"]:
            parts.append(f"{tf}: {touched} updated (+{s['added']} bars)"
                         + (f", {s['failed']} failed" if s["failed"] else ""))
    return "; ".join(parts) if parts else "all timeframes already fresh"
