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

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.marketdata.data_store import (
    DATA_DIR,
    TRAINING_TIMEFRAMES,
    _default_ranged_fetch,
    cache_path,
    fetch_interval_data,
    load_from_disk,
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

# Transient-fault retry (see _with_retry -- provider depth caps are NOT
# retried; they are a refusal, not a fault).
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0

# A symbol/timeframe that failed every attempt is re-tried this soon rather
# than waiting out its normal staleness window, so the bot keeps chipping at
# genuine gaps for as long as it runs.
FAILED_RETRY_HOURS = 0.5

STATE_FILE = os.path.join(config.DATA_DIR, "market_data_state.json")


def load_state() -> dict:
    """Per-(symbol,timeframe) coverage + failure record. Survives restarts so
    an unresolved gap keeps being retried across bot sessions."""
    return read_json(STATE_FILE, {}) or {}


def save_state(state: dict) -> None:
    try:
        atomic_write_json(STATE_FILE, state)
    except Exception as exc:            # never let bookkeeping break a refresh
        log.warning("could not write %s: %s", STATE_FILE, exc)


def _key(symbol: str, timeframe: str) -> str:
    return f"{symbol.upper()}|{timeframe}"


def is_stale(symbol: str, timeframe: str, base_dir: str = DATA_DIR,
             max_age_hours: float = None, state: dict = None) -> bool:
    """True when this symbol/timeframe is missing or old enough to re-fetch.

    A record that failed its last attempt becomes eligible again after
    FAILED_RETRY_HOURS instead of its normal (much longer) staleness window,
    so transient outages get chipped away at while the bot runs rather than
    waiting a full day.
    """
    tf = timeframe_name(timeframe)
    path = cache_path(symbol, tf, base_dir=base_dir)
    if not os.path.exists(path):
        return True
    if max_age_hours is None:
        max_age_hours = REFRESH_HOURS.get(tf, DEFAULT_REFRESH_HOURS)
        if state is not None:
            rec = state.get(_key(symbol, tf))
            if rec and rec.get("last_status") == "failed":
                max_age_hours = min(max_age_hours, FAILED_RETRY_HOURS)
    age_hours = (time.time() - os.path.getmtime(path)) / 3600.0
    return age_hours >= max_age_hours


def _align_tz(a, b):
    """Make two DatetimeIndexes comparable. Intraday frames come back
    tz-aware, daily-and-coarser naive, and a cached CSV can round-trip
    either way depending on which timeframe wrote it."""
    try:
        if a.index.tz is not None and b.index.tz is None:
            a = a.copy(); a.index = a.index.tz_localize(None)
        elif a.index.tz is None and b.index.tz is not None:
            b = b.copy(); b.index = b.index.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return a, b


_ADJUSTMENT_MISMATCH_TOLERANCE = 0.01   # 1%: real EOD closes agree exactly; a split/dividend shifts price by far more

_PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


def _adjustment_ratio(existing, fresh, symbol: str, timeframe: str):
    """Detects a stock split/dividend that landed between refreshes.

    yfinance's auto_adjust re-derives EVERY historical bar's price from the
    ticker's FULL corporate-action history each time it's called -- a split
    or dividend that lands between two refreshes changes `fresh`'s prices
    for dates `existing` already has on disk, not just new ones. Compares
    the two on their overlapping dates (median ratio, robust to the odd
    stale/rounding-off bar) and returns the fresh/existing ratio if they
    disagree by more than a real adjustment ever would from EOD noise
    alone, else None (no adjustment change -- the common case, every scan).
    """
    common = existing.index.intersection(fresh.index)
    if len(common) == 0:
        return None
    ratios = (fresh.loc[common, "Close"] / existing.loc[common, "Close"]).dropna()
    ratios = ratios[ratios > 0]
    if ratios.empty:
        return None
    ratio = float(ratios.median())
    if abs(ratio - 1.0) <= _ADJUSTMENT_MISMATCH_TOLERANCE:
        return None
    log.warning(
        "%s/%s: adjustment-basis mismatch detected on %d overlapping bar(s) "
        "(fresh/cached price ratio %.4f) -- re-scaling %d cached bar(s) to "
        "the new basis before merging (split/dividend since the last refresh?)",
        symbol, timeframe, len(common), ratio, len(existing))
    return ratio


def _merge_save(existing, fresh, symbol: str, timeframe: str,
                base_dir: str) -> tuple:
    """UNION existing with fresh and write atomically. Returns (df, added).

    Never overwrites: bars already on disk survive even when the provider
    stops serving them. This is what lets the archive grow deeper than the
    provider's window over time -- a plain save_to_disk() here would let a
    shallower response silently destroy accumulated history.

    Before unioning, re-scales `existing`'s price columns to `fresh`'s
    adjustment basis if `_adjustment_ratio` finds they've diverged (v56) --
    without this, a split/dividend between refreshes left every bar BEFORE
    the overlap on the old basis while bars AT/AFTER it took the new one,
    producing a single-bar cliff at the seam. universe.data_quality_issues'
    own ">40% bar without volume spike (bad split adjust?)" check exists
    for exactly this artifact, and it was firing live in production
    2026-08-24 -- this is the actual bad-split-adjust it was warning about,
    not a false positive. Volume is deliberately left unscaled: the quality
    check and every live consumer of these frames key off price move (and
    a volume RATIO, not an absolute value), so a volume-only split factor
    isn't needed to fix the observed symptom and isn't worth the extra risk
    of getting split-vs-dividend volume conventions wrong here.
    """
    if existing is None or len(existing) == 0:
        merged, added = fresh, len(fresh)
    else:
        existing, fresh = _align_tz(existing, fresh)
        ratio = _adjustment_ratio(existing, fresh, symbol, timeframe)
        if ratio is not None:
            existing = existing.copy()
            cols = [c for c in _PRICE_COLUMNS if c in existing.columns]
            existing[cols] = existing[cols] * ratio
        before = set(existing.index)
        merged = pd.concat([existing, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        added = sum(1 for i in fresh.index if i not in before)

    path = cache_path(symbol, timeframe, base_dir=base_dir)
    tmp = path + ".tmp"
    merged.to_csv(tmp)
    os.replace(tmp, path)          # atomic: a crash mid-write can't truncate
    return merged, added


def _with_retry(fn, *args, attempts: int = None, base_delay: float = None,
                label: str = ""):
    """Call fn with exponential backoff. Raises the last error if all
    attempts fail.

    Only worth doing for TRANSIENT faults -- curl timeouts, rate limiting,
    a momentarily empty response. A provider depth limit is a refusal, not
    a fault: it returns the same truncated window every time, so retrying
    it is pure waste and is deliberately NOT retried here.
    """
    attempts = attempts or RETRY_ATTEMPTS
    base_delay = base_delay if base_delay is not None else RETRY_BASE_DELAY
    last = None
    for i in range(attempts):
        try:
            return fn(*args)
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                delay = base_delay * (2 ** i)
                log.info("retry %s in %.1fs (attempt %d/%d): %s",
                         label, delay, i + 1, attempts, str(exc)[:120])
                time.sleep(delay)
    raise last


def refresh_symbol(symbol: str, timeframe: str, base_dir: str = DATA_DIR,
                   force: bool = False, state: dict = None) -> dict:
    """Bring one symbol/timeframe up to date. Returns a result dict with
    status 'full' | 'incremental' | 'fresh' | 'failed'.

    Transient failures are retried with backoff. Whatever is already on
    disk is always preserved -- see _merge_save.
    """
    tf = timeframe_name(timeframe)
    out = {"symbol": symbol, "timeframe": tf, "rows": 0, "added": 0}
    existing = load_from_disk(symbol, tf, base_dir=base_dir)
    have = 0 if existing is None else len(existing)

    if not force and not is_stale(symbol, tf, base_dir=base_dir, state=state):
        return {**out, "status": "fresh", "rows": have}

    # Cold, or forced: pull the deepest history this timeframe allows.
    # NOTE force no longer discards `existing` -- it re-pulls full depth and
    # merges, so a forced refresh can only ever ADD bars.
    if have == 0 or force:
        try:
            df = _with_retry(fetch_interval_data, symbol, tf,
                             label=f"{symbol}/{tf} full")
        except Exception as exc:
            log.warning("refresh %s/%s failed after retries: %s", symbol, tf, exc)
            return {**out, "status": "failed", "rows": have, "error": str(exc)[:200]}
        merged, added = _merge_save(existing, df, symbol, tf, base_dir)
        return {**out, "status": "full" if have == 0 else "incremental",
                "rows": len(merged), "added": added}

    # Warm: fetch only what is newer than the last cached bar.
    last = existing.index.max()
    try:
        fresh = _with_retry(_default_ranged_fetch, symbol, last, tf,
                            label=f"{symbol}/{tf} incremental")
    except Exception as exc:
        log.warning("incremental %s/%s failed after retries: %s", symbol, tf, exc)
        return {**out, "status": "failed", "rows": have, "error": str(exc)[:200]}

    if fresh is None or len(fresh) == 0:
        # Nothing new, but touch the file so a closed market doesn't make
        # every tick re-request the same empty window.
        os.utime(cache_path(symbol, tf, base_dir=base_dir), None)
        return {**out, "status": "fresh", "rows": have}

    merged, added = _merge_save(existing, fresh, symbol, tf, base_dir)
    if added == 0:
        os.utime(cache_path(symbol, tf, base_dir=base_dir), None)
        return {**out, "status": "fresh", "rows": len(merged)}
    return {**out, "status": "incremental", "rows": len(merged), "added": added}


def _record(state: dict, symbol: str, tf: str, r: dict, base_dir: str) -> None:
    """Update the persistent coverage/failure record for one pair."""
    k = _key(symbol, tf)
    rec = dict(state.get(k) or {})
    rec["last_status"] = r["status"]
    rec["last_attempt"] = int(time.time())
    if r["status"] == "failed":
        rec["fail_count"] = int(rec.get("fail_count", 0)) + 1
        rec["last_error"] = str(r.get("error", ""))[:200]
    else:
        rec["fail_count"] = 0
        rec.pop("last_error", None)
        rec["last_success"] = rec["last_attempt"]
        rec["rows"] = r.get("rows", 0)
        # Earliest bar we hold. Tracked because it is the ONLY evidence that
        # the archive is outgrowing the provider's window: it should stay put
        # (or move earlier) forever, and a later value is worth an alert.
        #
        # The alert must still adopt the new value as the baseline (rather
        # than freezing `rec["earliest"]` at the old one forever) -- production
        # bug 2026-08-24: get_intraday() once overwrote instead of merged
        # (fixed in 2b67124), permanently truncating dozens of tickers'
        # hourly archives. Freezing the baseline here meant every refresh
        # tick since kept re-comparing against a 2016 earliest the archive
        # can now never reach again (Yahoo doesn't serve it), so the SAME
        # already-reported, already-fixed-going-forward loss logged an ERROR
        # every 4 hours forever instead of once. The same freeze would also
        # misfire on a legitimate, benign cause: a near-boundary archive's
        # front edge eroding a few days as Yahoo's rolling intraday window
        # advances over time is not a bug and must not re-alert forever
        # either. Adopting the new value each time means a regression is
        # reported exactly once per new drop, and a genuinely worse repeat
        # regression (past the newly-adopted floor) still alerts correctly.
        try:
            df = load_from_disk(symbol, tf, base_dir=base_dir)
            if df is not None and len(df):
                earliest = str(df.index.min())[:10]
                prev = rec.get("earliest")
                if prev and earliest > prev:
                    log.error(
                        "COVERAGE REGRESSION %s/%s: earliest bar moved %s -> %s "
                        "(history was lost, not merged)", symbol, tf, prev, earliest)
                rec["earliest"] = earliest
                rec["latest"] = str(df.index.max())[:10]
        except Exception:
            pass
    state[k] = rec


def refresh_all(symbols, timeframes=TRAINING_TIMEFRAMES, base_dir: str = DATA_DIR,
                force: bool = False, sleep_seconds: float = 0.0,
                on_progress=None, state: dict = None,
                persist_state: bool = True, deadline_seconds: float = None) -> dict:
    """Refresh every (symbol, timeframe) pair. Never raises.

    deadline_seconds: once this many wall-clock seconds have elapsed since
    the call began, stop starting new refreshes and return what's done so
    far -- whatever pairs weren't reached simply carry their existing
    staleness into the next scheduled tick, nothing is lost or undone.
    None (the default) is unbounded, for scripts/tests that want a complete
    pass. The live background loop (market_data_refresh in
    commands/scanning.py) always passes one: an unbounded sweep is what let
    it run long enough, under a large stale backlog or a slow/rate-limited
    provider, to starve the Discord gateway heartbeat and drop the bot's
    connection.
    """
    timeframes = [timeframe_name(t) for t in timeframes]
    summary = {tf: {"full": 0, "incremental": 0, "fresh": 0, "failed": 0,
                    "added": 0} for tf in timeframes}
    failures = []
    if state is None:
        state = load_state() if persist_state else {}

    started = time.monotonic()
    deadline_hit = False
    for tf in timeframes:
        if deadline_hit:
            break
        for symbol in symbols:
            if deadline_seconds is not None and time.monotonic() - started >= deadline_seconds:
                deadline_hit = True
                break
            try:
                r = refresh_symbol(symbol, tf, base_dir=base_dir, force=force,
                                   state=state)
            except Exception as exc:      # belt-and-braces: loop must survive
                log.warning("refresh %s/%s crashed: %s", symbol, tf, exc)
                r = {"symbol": symbol, "timeframe": tf, "status": "failed",
                     "rows": 0, "added": 0, "error": str(exc)[:200]}
            bucket = summary[tf]
            bucket[r["status"]] = bucket.get(r["status"], 0) + 1
            bucket["added"] += r.get("added", 0)
            if r["status"] == "failed":
                failures.append((symbol, tf, r.get("error", "")))
            _record(state, symbol, tf, r, base_dir)
            if on_progress:
                try:
                    on_progress(r)
                except Exception:
                    pass
            if sleep_seconds and r["status"] not in ("fresh", "skipped"):
                time.sleep(sleep_seconds)

    if persist_state:
        save_state(state)
    return {"summary": summary, "failures": failures, "state": state,
            "deadline_hit": deadline_hit}


def pending_gaps(state: dict = None) -> list:
    """Pairs whose last attempt failed -- what the loop keeps retrying."""
    state = load_state() if state is None else state
    return [(k.split("|")[0], k.split("|")[1], rec.get("fail_count", 0),
             rec.get("last_error", ""))
            for k, rec in sorted(state.items())
            if rec.get("last_status") == "failed"]


def summary_line(result: dict) -> str:
    """One-line log summary of a refresh_all result."""
    parts = []
    for tf, s in result["summary"].items():
        touched = s["full"] + s["incremental"]
        if touched or s["failed"]:
            parts.append(f"{tf}: {touched} updated (+{s['added']} bars)"
                         + (f", {s['failed']} failed" if s["failed"] else ""))
    return "; ".join(parts) if parts else "all timeframes already fresh"
