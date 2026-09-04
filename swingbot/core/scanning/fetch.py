"""Cache-first, bounded data acquisition helpers for scanning."""
import logging
import multiprocessing
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scan_run import ScanProgress

from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait as _futures_wait

from swingbot import config
from swingbot.core.marketdata.data import (
    get_current_price, get_current_price_batch, get_daily_data,
    get_daily_data_batch,
)
from swingbot.core.marketdata import data_refresh, data_store, universe

from . import runstate


log = logging.getLogger("swing-bot.scan_engine")


class LRUFrames(OrderedDict):
    """Frame store with an explicit capacity for one complete scan.

    The crawl passes ``max_frames=len(tickers)``. A scan must retain every
    fetched frame: an eviction would otherwise look like a data failure to
    later analysis and open-trade monitoring.

    get() is overridden alongside __getitem__: CPython's dict.get() calls
    into the C-level hash table directly and does NOT dispatch through a
    subclass's __getitem__ override, and this module reads frames almost
    exclusively via `fresh_data.get(ticker)`, never `fresh_data[ticker]` --
    without this override, recency would only ever update on insert, and
    eviction would silently degrade to FIFO instead of LRU."""
    def __init__(self, max_frames: int = 200):
        super().__init__()
        self.max_frames = max_frames

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_frames:
            self.popitem(last=False)
def _chunked(items: list, size: int) -> list:
    """Splits `items` into consecutive slices of at most `size` each."""
    size = max(1, int(size))
    return [items[i:i + size] for i in range(0, len(items), size)]


# E47 follow-up, confirmed live on production 2026-08-25: the default
# ProcessPoolExecutor start method on Linux is 'fork', which clones the
# parent's entire memory -- including yfinance 0.2.66's process-wide
# singleton curl_cffi session (libcurl/OpenSSL handles, connection state,
# internal locks) the instant it has been touched even once by the parent
# (any earlier _fetch_one_ticker/get_current_price call, or the background
# market_data_refresh loop, all running in this same long-lived process).
# libcurl and OpenSSL are not fork-safe once used -- glibc's own malloc
# arena locks aren't guaranteed safe across fork() either when other
# threads are alive, and this process always has some (asyncio's default
# to_thread executor, map_tickers' ThreadPoolExecutor). Every worker forked
# after that point crashed on startup with a libc.so.6 segfault (`dmesg`:
# identical faulting address/instruction pointer every time), which
# concurrent.futures surfaces as BrokenProcessPool ("A process in the
# process pool was terminated abruptly") -- not the timeout-kill path
# below, a completely different failure that happened to look similar in
# the logs. With v55's batched fetch (one fork per whole chunk, not per
# ticker) a single crashed fork now fails 10-15+ tickers at once, which is
# what pushed E47's data_fail_frac over the 20% kill-switch threshold on
# every single scan. 'spawn' starts each worker as a brand-new interpreter
# with no inherited C-level state, eliminating the hazard at the root
# instead of chasing it fork-by-fork; the extra ~1-2s interpreter startup
# per chunk is cheap against COLD_FETCH_TIMEOUT_SECONDS' 180s budget. This
# is a no-op on Windows dev machines, which only ever had 'spawn' to begin
# with (no fork() at all) -- exactly why this never reproduced off Linux.
_SPAWN_CTX = multiprocessing.get_context("spawn")


def _run_bounded(fn, args: tuple, timeout_seconds: float, label: str):
    """Runs fn(*args) in a single-process pool with a hard wall-clock
    budget. Returns fn's result, or None if the budget is exceeded (or fn
    itself raised).

    A PROCESS, not a thread -- two independent reasons stacked on top of
    each other. First, the pinned yfinance 0.2.66 builds download() on a
    shared, non-reentrant module global (_DFS); a separate process has its
    own interpreter and memory, so nothing here can ever race a concurrent
    caller's _DFS the way a ThreadPoolExecutor once did (see this module's
    own docstring -- two real watchlist tickers once had their price data
    swapped this way). Second -- why the budget exists at all -- a stalled
    DNS lookup or a fork-inherited lock can wedge a worker past whatever
    timeout `fn` itself was given, with no exception and no CPU use; only a
    killed OS process is a reliable ceiling. Confirmed live on production
    2026-08-24: a single stuck cold fetch froze session_scan, and every
    tick behind it, for 2+ hours (d251cef fixed this for the per-ticker
    pool it used to bound; this helper generalizes that same wait-then-kill
    mechanism to one future per batched call instead of one per ticker).

    mp_context=_SPAWN_CTX (E47 follow-up, 2026-08-25): see that constant's
    own comment -- 'fork' (the Linux default) crashes on startup here.

    shutdown(wait=False) alone only cancels futures that never started --
    it does not stop one mid-flight, so a still-running worker is force-
    killed outright.
    """
    with ProcessPoolExecutor(max_workers=1, mp_context=_SPAWN_CTX) as pool:
        future = pool.submit(fn, *args)
        done, not_done = _futures_wait([future], timeout=timeout_seconds)
        if future in done:
            try:
                return future.result()
            except Exception as exc:
                log.error("%s failed: %s", label, exc)
                return None
        log.error(
            "%s did not finish within %ss -- killing the worker process and "
            "treating this as a failed fetch", label, timeout_seconds)
        for proc in pool._processes.values():
            proc.kill()
        # wait=True (v56, was False): confirmed live on production 2026-08-24
        # that wait=False lets this function return with the pool's manager
        # thread still alive in the background -- unjoined, since Executor's
        # own __exit__ shutdown(wait=True) call on the way out of the `with`
        # block is a no-op by then (this shutdown() already cleared
        # _executor_manager_thread/_processes to None, which is exactly what
        # that second call's own guards check). A NEW ProcessPoolExecutor
        # created by the very next _run_bounded call then fork()s while that
        # orphaned thread is still running -- and every subsequent call that
        # scan pass failed instantly with "process ... terminated abruptly"
        # (15 tickers' cold-fetch fallback, the live-price batch, and the
        # sector-ETF fetch all failed in the same few seconds). The worker
        # is already SIGKILLed above, so the manager thread notices via its
        # sentinel almost immediately -- wait=True here joins that thread
        # before returning, so it can no longer be alive at the next call's
        # fork() point. This is NOT the same risk shutdown()'s wait=True
        # normally carries (blocking on a live, possibly-still-hung worker):
        # that worker is already dead.
        pool.shutdown(wait=True, cancel_futures=True)
        return None


def _fetch_one_ticker(ticker: str) -> tuple:
    """Single-ticker fetch, module-level so it stays picklable for
    _run_bounded(). No longer the primary cold-fetch path (v55:
    _fetch_cold_frames batches instead) -- kept as the candidate_symbols()-
    aliasing fallback for a ticker whose batch slice came back empty, since
    a batched get_daily_data_batch() call only ever tries a ticker's
    literal symbol.

    Returns (ticker, DataFrame|None). Never raises -- a worker that raised
    would surface as a BrokenProcessPool and take down whatever else
    _run_bounded is protecting alongside it.
    """
    try:
        return ticker, get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
    except Exception as exc:
        log.error("Crawl: error fetching data for %s: %s", ticker, exc)
        return ticker, None


def _fetch_cold_frames(tickers: list, progress: "ScanProgress" = None) -> list:
    """v55: fetch the cache misses via batched, chunked, bounded calls.

    Every cold ticker -- any count -- goes through one or more batched
    get_daily_data_batch() calls (BATCH_FETCH_CHUNK_SIZE tickers per call,
    default covers today's whole watchlist in one chunk) instead of a
    per-ticker call. Each chunk runs through _run_bounded(), so a stalled
    chunk is killed and treated as a failed fetch for every ticker in it
    rather than wedging the crawl -- COLD_FETCH_TIMEOUT_SECONDS now bounds
    one batched chunk instead of one ticker's fetch.

    A ticker absent from its chunk's batch result (the whole chunk failed,
    or just that ticker's own slice was empty) falls back to the single-
    ticker _fetch_one_ticker(), which -- unlike the batch path -- also
    tries candidate_symbols() aliasing. In steady state this remainder is
    empty or near-empty.

    Returns order-preserving (ticker, DataFrame|None) pairs -- the same
    contract this function has always had.
    """
    if not tickers:
        return []

    period = config.DEFAULT_HISTORY_PERIOD
    chunk_size = int(getattr(config, "BATCH_FETCH_CHUNK_SIZE", 100))
    timeout = int(getattr(config, "COLD_FETCH_TIMEOUT_SECONDS", 180))
    resolved: dict = {}
    remainder: list = []

    for chunk in _chunked(tickers, chunk_size):
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        result = _run_bounded(
            get_daily_data_batch, (chunk, period), timeout,
            label=f"Crawl: cold-fetch batch of {len(chunk)} ticker(s)") or {}
        for ticker in chunk:
            if ticker in result:
                resolved[ticker] = result[ticker]
            else:
                remainder.append(ticker)
        if progress is not None:
            progress.done += len(chunk)
            progress.current_ticker = chunk[-1]

    for ticker in remainder:
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        _, df = _run_bounded(
            _fetch_one_ticker, (ticker,), timeout,
            label=f"Crawl: cold-fetch fallback for {ticker}") or (ticker, None)
        resolved[ticker] = df

    return [(t, resolved.get(t)) for t in tickers]

def _load_cached_daily(ticker: str):
    """v47: today's daily bar from market_data/daily/{TICKER}.csv, or None.

    None means "cold" -- missing, stale, or unreadable -- and the caller
    fetches it instead. `market_data_refresh` (commands/scanning.py) already
    keeps this cache warm for exactly load_watchlist(), so in steady state this
    is the path every ticker takes and the scan makes no network calls at all.

    Staleness reuses data_refresh.is_stale() rather than reimplementing it: it
    already handles "file missing" and takes an explicit max_age_hours, so the
    scan's freshness bar (SCAN_CACHE_MAX_AGE_HOURS, 6h) stays independent of
    the background loop's own 12h daily refetch cadence.
    """
    try:
        if data_refresh.is_stale(ticker, "daily",
                                 max_age_hours=config.SCAN_CACHE_MAX_AGE_HOURS):
            return None
        return data_store.load_normalized(ticker, "daily")
    except Exception as exc:
        log.debug("Crawl: cache lookup failed for %s (%s) -- treating as cold", ticker, exc)
        return None


def _crawl_latest_data(tickers: list, progress: "ScanProgress" = None) -> dict:
    """
    Phase 1 of every scan: fetches the latest daily OHLCV data for every
    ticker in `tickers` BEFORE any analysis runs. This is the only place
    a scan fetches price data from -- build_level_map(), build_scenarios(),
    confidence scoring, etc. downstream never fetch anything themselves,
    they only ever see what this function already pulled fresh.

    v47: cache-first. A ticker whose market_data/daily/{TICKER}.csv is
    present and fresher than SCAN_CACHE_MAX_AGE_HOURS is served from disk and
    never reaches the fetch path at all -- `market_data_refresh` already keeps
    that cache warm for exactly load_watchlist(), so in steady state the whole
    crawl costs no network. Only genuine misses (the "cold" list) are fetched,
    and everything below is about them.

    Cold tickers are fetched ONE AT A TIME, sequentially -- deliberately NOT a
    concurrent thread pool. This used to run through a bounded
    ThreadPoolExecutor for speed, but yfinance's `download()` (which
    get_daily_data() calls) is built on a shared module-level global
    (`_DFS`) that earlier yfinance releases -- including 0.2.66, the
    version this project is pinned to -- write to non-reentrantly; the
    upstream fix ("Make yf.download() reentrant by removing shared
    module globals", yfinance changelog 1.4.0) only landed in the 1.x
    line, a major-version jump this project deliberately hasn't taken
    (see requirements.txt's pinning rationale). Calling it from several
    threads at once let two different tickers' downloads clobber each
    other's data mid-flight: two real watchlist tickers scanned 2 seconds
    apart in the same concurrent batch were once logged as open trades
    with byte-identical entry/stop/target/confidence values -- one
    ticker's real price data got attributed to the other. Sequential
    fetching is slower for a large watchlist, but for a paper-trading
    bot that posts real alerts and logs real trade records, correctness
    beats speed here -- this can be revisited if/when yfinance is
    upgraded past 1.4.0 and re-verified thread-safe.

    Returns {ticker: DataFrame} for tickers that fetched successfully.
    A ticker whose fetch failed is simply absent from the result (the
    caller logs and skips it downstream) -- one bad ticker never aborts
    the crawl for the rest of the watchlist.

    Checks runstate.is_stop_requested() once per ticker and ends the crawl early
    (returning whatever was fetched so far) if a stop was requested --
    see the module-level _STOP_FILE docstring above for why this is
    file-based and only checked at per-ticker checkpoints, not instant.
    """
    if progress is not None:
        progress.stage = "crawling data"
        progress.total = len(tickers)
        progress.done = 0
        progress.current_ticker = None

    results = LRUFrames(max_frames=len(tickers))
    started = time.monotonic()

    cold = []
    warm = 0
    for ticker in tickers:
        if runstate.is_stop_requested():
            log.info("Crawl: stop requested -- ending early (%d/%d ticker(s) resolved so far)",
                      len(results), len(tickers))
            if progress is not None:
                progress.stopped = True
            return results
        df = _load_cached_daily(ticker)
        if df is not None:
            results[ticker] = df
            warm += 1
            if progress is not None:
                progress.done += 1
                progress.current_ticker = ticker
            continue
        cold.append(ticker)

    for ticker, df in _fetch_cold_frames(cold, progress):
        if df is not None:
            results[ticker] = df

    elapsed = time.monotonic() - started
    log.info("Crawl complete in %.1fs: %d/%d ticker(s) resolved (%d from cache, %d fetched)",
              elapsed, len(results), len(tickers), warm, len(cold))
    return results


def _fetch_live_prices(tickers: list, progress: "ScanProgress" = None) -> dict:
    """v55: Phase 1b of every scan -- one batched live-price fetch (chunked)
    for the WHOLE watchlist, not just cold tickers: a warm daily-bar cache
    says nothing about today's live (incl. pre/post-market) price. Runs
    through the same bounded process pool as the cold OHLCV fetch
    (_run_bounded), so a stalled chunk can never hang the scan the way the
    old analyze-phase loop's unbounded per-ticker get_current_price() calls
    could -- LIVE_PRICE_TIMEOUT_SECONDS bounds one batched chunk.

    Returns {ticker: price} for tickers whose chunk resolved. A ticker
    absent from the result falls back to today's daily close in _scan_one,
    exactly as a live-price fetch failure has always degraded.
    """
    if not tickers:
        return {}
    chunk_size = int(getattr(config, "BATCH_FETCH_CHUNK_SIZE", 100))
    timeout = int(getattr(config, "LIVE_PRICE_TIMEOUT_SECONDS", 60))
    started = time.monotonic()
    prices: dict = {}
    for chunk in _chunked(tickers, chunk_size):
        if runstate.is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        result = _run_bounded(
            get_current_price_batch, (chunk,), timeout,
            label=f"Crawl: live-price batch of {len(chunk)} ticker(s)")
        if result:
            prices.update(result)
    log.info("Live-price fetch complete in %.1fs: %d/%d ticker(s) resolved",
              time.monotonic() - started, len(prices), len(tickers))
    return prices


def _etf_symbol_of_sector() -> dict:
    """v34 Task 5 fix: the sector-name -> SPDR ETF symbol resolution,
    factored out so both `_sector_etfs_for_tickers` (which ETFs does this
    watchlist need fetched) and `_apply_sector_rs` (was THIS ticker's own
    sector ETF actually among the frames fetched this scan) share one
    mapping instead of each inverting etfs.json's {symbol: sector} on its
    own.

    Static-file lookup only, no network -- sp500.json's `sector` strings
    and etfs.json's `sector` strings come from the same GICS-style
    vocabulary (e.g. "Information Technology", "Financials"), so inverting
    the ETF file's {symbol: sector} into {sector: symbol} is enough to
    translate a ticker's sector into the SPDR ETF that tracks it, with no
    separate translation table to maintain.
    """
    etf_of_symbol = universe.sector_map("etfs")          # {ETF symbol: sector}
    return {sector: sym for sym, sector in etf_of_symbol.items()}


def _sector_etfs_for_tickers(tickers: list) -> tuple:
    """v34 Task 5: which sector ETFs does this watchlist touch?

    Returns (sector_of_ticker, needed_etf_symbols):
      - sector_of_ticker: {ticker: sector} for every ticker sp500.json
        knows about (its own universe file, not the watchlist -- unrelated
        tickers just won't be looked up). A ticker sp500.json doesn't have
        (delisted, newly added, ETF-only watchlist, ...) is simply absent
        -- the caller's `.get()` treats that the same as "unknown sector".
      - needed_etf_symbols: the distinct, sorted list of ETF symbols to
        fetch -- sorted only for deterministic test/log output, order
        carries no meaning downstream.
    """
    sector_of_ticker = universe.sector_map("sp500")
    etf_symbol_of_sector = _etf_symbol_of_sector()
    needed = sorted({
        etf_symbol_of_sector[sector_of_ticker[t]]
        for t in tickers
        if sector_of_ticker.get(t) in etf_symbol_of_sector
    })
    return sector_of_ticker, needed


def _fetch_frames(symbols: list) -> dict:
    """Cache-first resolution for a small side-list of symbols (sector ETFs,
    currently at most the 11 SPDR sector funds in etfs.json).

    v47: warm symbols come from market_data/daily/*.csv and cost no network;
    the cold remainder goes through _fetch_cold_frames, which batches this
    small a list (11 symbols) into a single call (v55). A symbol whose
    fetch fails is simply absent from the result, exactly like
    _crawl_latest_data."""
    frames = {}
    cold = []
    for symbol in symbols:
        df = _load_cached_daily(symbol)
        if df is not None:
            frames[symbol] = df
        else:
            cold.append(symbol)
    for symbol, df in _fetch_cold_frames(cold):
        if df is not None:
            frames[symbol] = df
    return frames


def _daily_frame_for(symbol: str):
    """v47: cache-first single-symbol daily frame, for the regime benchmark.

    Returns None on a cache miss whose fetch also failed -- callers already
    treat that as "unavailable this scan"."""
    df = _load_cached_daily(symbol)
    if df is not None:
        return df
    try:
        return get_daily_data(symbol, period=config.DEFAULT_HISTORY_PERIOD)
    except Exception as exc:
        log.warning("Could not resolve daily frame for %s: %s", symbol, exc)
        return None


def map_tickers(fn, tickers: list, workers: int | None = None) -> list:
    """Order-preserving, error-isolated parallel map for the scan loop.
    The per-ticker work is pandas/numpy-heavy (releases the GIL in C) so
    threads give real speedup without multiprocessing's pickling pain.

    Unlike _crawl_latest_data (network-bound, kept strictly sequential --
    see that function's docstring for the yfinance thread-safety reason),
    this is for the ANALYZE phase only, which never touches yfinance --
    it's safe to parallelize.
    """
    n = workers if workers is not None else getattr(config, "SCAN_WORKERS", 4)

    def safe(t):
        try:
            return fn(t)
        except Exception:
            log.exception("scan worker failed for %s", t)
            return None

    if n <= 1 or len(tickers) <= 1:
        return [safe(t) for t in tickers]
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(safe, tickers))



