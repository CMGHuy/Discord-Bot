# v48 — Scan Throughput Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.8.0 · bot 1.3.2
Bump: `bot patch` · `ui patch`

**Spec:** `docs/superpowers/specs/2026-08-21-v47-scan-throughput-design.md`

**On the two numbers:** this plan is `v48`, its spec is `v47` — a number appears
exactly once across `specs/` and `plans/` (see `docs/claude/document-conventions.md`).
**The code you write cites `v47`, not `v48`:** commit prefixes (`feat(v47): …`),
test names and source comments below all point a future reader at the spec, which
is where the rationale lives. Use them exactly as written; do not "correct" them
to `v48`.

**Goal:** Make the live scan read the already-maintained daily cache instead of
re-downloading 10 years of history per ticker per tick, fetch genuine cache
misses through a process pool that cannot repeat the cross-ticker corruption bug,
and parallelise the offline scenario replay.

**Architecture:** Three layers, all in-process. (1) `_crawl_latest_data()` gains a
cache-first lookup via `data_refresh.is_stale()` + `data_store.load_from_disk()`,
routing misses to a `cold` list instead of fetching inline. (2) The `cold` list is
fetched sequentially below a threshold and through a `ProcessPoolExecutor` above
it — processes, not threads, because the pinned yfinance's shared `_DFS` global is
not reentrant. (3) `run_scenario_backtest()` maps one task per ticker (all
horizons inside) across a process pool. No new container, no new deployable, no
dependency bump.

**Tech Stack:** Python 3.11+, pandas, yfinance 0.2.66 (pinned — do not change),
`concurrent.futures.ProcessPoolExecutor`, pytest.

## Global Constraints

- **Do not change the yfinance version pin.** 0.2.66's `download()` is built on a
  non-reentrant shared module global (`_DFS`). Never call it from multiple
  *threads*. Processes are safe; threads are not.
- **This is a pure throughput change.** Scan output — alerts, horizons, plans,
  confidence — must be observably identical. Any behavioural difference is a bug.
- **Green means `0 failed` AND `0 xfailed`.** Reference baseline:
  `1686 passed, 66 skipped, 0 failed`. A changed pass count is not itself a
  failure; a new `xfailed` is.
- Use `python scripts/dev/testrun.py file tests/<f>.py` (~7s) while iterating and
  `python scripts/dev/testrun.py full` for the pre-commit gate. Never run raw
  full-suite pytest — it emits ~1150 progress lines.
- `Field` defaults are **strings** cast by `_CASTERS` (`swingbot/config.py:705`);
  `type="number"` casts with `int()`. A computed default cannot live in the
  schema — that is why `FETCH_WORKERS=0` means "auto".
- Every new `Field` must also be added to `.env.example` or
  `tests/test_env_example_sync.py::test_every_setting_appears_in_env_example`
  fails.
- Do not edit anything under `.claude/worktrees/` from this tree.

## Parallelisation

- **Sequential:** Task 1 before everything (every later task reads the three new
  config attrs, and all of them would otherwise edit `swingbot/config.py`
  concurrently — this working tree is shared, so that is an overwrite, not a
  merge). Task 3 before Task 4 (Task 4 consumes the `cold` list Task 3 produces,
  and both edit `swingbot/core/scanning/engine.py`). Task 5 after Task 4 (it
  asserts against `_fetch_cold_frames`, which Task 4 introduces). Task 6 after
  Task 4 (same file, and it reuses `_load_cached_daily` and `_fetch_cold_frames`).
- **Group 1 (parallel), once Task 1 is committed:** Task 2 and Task 7. Task 2
  touches `swingbot/core/marketdata/data_store.py` + `tests/marketdata/`; Task 7
  touches `swingbot/core/backtesting/backtest_scenarios.py` +
  `tests/backtesting/`. Disjoint files, and neither consumes a symbol the other
  introduces.
- Tasks 3, 4, 5, 6 are a strict chain — all four edit
  `swingbot/core/scanning/engine.py`. **Never dispatch two of them at once.**

---

# Phase 1 — Config and cache plumbing

### Task 1: Add the three config fields

**Files:**
- Modify: `swingbot/config.py` (append to the "Universe & Scanning" block, after the `SCAN_WORKERS` entry at line 573)
- Modify: `.env.example`
- Test: `tests/test_config_flags.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SCAN_CACHE_MAX_AGE_HOURS: int`, `config.COLD_FETCH_PROCESS_THRESHOLD: int`,
  `config.FETCH_WORKERS: int` (0 = auto). Every later task reads these.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_flags.py`:

```python
def test_v47_throughput_fields_exist_with_documented_defaults():
    """v47: the scan's cache-freshness bar, the cold-fetch cutover point and
    the process-pool size are all configurable, and their defaults match the
    spec. FETCH_WORKERS=0 means auto -- a Field default is a string cast by
    int(), so a computed cpu_count default cannot live in the schema."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["SCAN_CACHE_MAX_AGE_HOURS"].default == "6"
    assert by_key["COLD_FETCH_PROCESS_THRESHOLD"].default == "10"
    assert by_key["FETCH_WORKERS"].default == "0"

    # All three are integers on the module after parsing, not raw strings.
    assert isinstance(config.SCAN_CACHE_MAX_AGE_HOURS, int)
    assert isinstance(config.COLD_FETCH_PROCESS_THRESHOLD, int)
    assert isinstance(config.FETCH_WORKERS, int)

    # The scan's freshness bar must sit BELOW data_refresh's own 12h daily
    # window, or the scan would trust a frame the refresh loop already
    # considers due for replacement.
    from swingbot.core.marketdata.data_refresh import REFRESH_HOURS
    assert config.SCAN_CACHE_MAX_AGE_HOURS < REFRESH_HOURS["daily"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_flags.py::test_v47_throughput_fields_exist_with_documented_defaults -v`
Expected: FAIL with `KeyError: 'SCAN_CACHE_MAX_AGE_HOURS'`

- [ ] **Step 3: Add the fields**

In `swingbot/config.py`, immediately after the `SCAN_WORKERS` `Field(...)` entry:

```python
    Field("SCAN_CACHE_MAX_AGE_HOURS", "SCAN_CACHE_MAX_AGE_HOURS", "Universe & Scanning",
          "Scan cache max age (hours)",
          type="number", default="6", min=1, max=48, step=1,
          help="How old market_data/daily/{TICKER}.csv may be before a scan treats the "
               "ticker as cold and refetches it. Deliberately below data_refresh's own 12h "
               "daily window so the scan's freshness bar is independent of the background "
               "refresh loop's refetch cadence. Swing horizons run 2w-9m, so only today's "
               "daily bar matters -- a warm ticker costs no network at all."),
    Field("COLD_FETCH_PROCESS_THRESHOLD", "COLD_FETCH_PROCESS_THRESHOLD", "Universe & Scanning",
          "Cold-fetch process-pool threshold",
          type="number", default="10", min=1, max=500, step=1,
          help="Cold (missing/stale) ticker count at or below which the scan fetches "
               "sequentially, exactly as it always has. Above it, the cold list is fanned "
               "out across FETCH_WORKERS processes. Below the threshold the process-pool "
               "startup cost outweighs the saving, and the sequential path carries zero "
               "new risk surface."),
    Field("FETCH_WORKERS", "FETCH_WORKERS", "Universe & Scanning",
          "Cold-fetch / replay process-pool size",
          type="number", default="0", min=0, max=32, step=1,
          help="Process-pool size for the cold-ticker fetch fallback and the offline "
               "scenario replay. 0 means auto: max(1, cpu_count() - 1). PROCESSES, not "
               "threads -- the pinned yfinance 0.2.66 builds download() on a shared "
               "non-reentrant module global, and concurrent threads once attributed one "
               "ticker's price data to another. Separate processes do not share it."),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_flags.py::test_v47_throughput_fields_exist_with_documented_defaults -v`
Expected: PASS

- [ ] **Step 5: Add the keys to `.env.example`**

In the scanning section of `.env.example`:

```bash
SCAN_CACHE_MAX_AGE_HOURS=6
COLD_FETCH_PROCESS_THRESHOLD=10
FETCH_WORKERS=0
```

- [ ] **Step 6: Verify the sync guard passes**

Run: `python -m pytest tests/test_env_example_sync.py -v`
Expected: PASS (this is the test that catches a `Field` added without an
`.env.example` key)

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_flags.py
git commit -m "feat(v47): add scan cache-freshness, cold-fetch threshold and pool-size settings"
```

---

# Phase 2 — Cache-first crawl

### Task 2: Normalize frames loaded from the CSV cache

A frame that has round-tripped through `to_csv`/`read_csv` can differ from a live
download in dtype (`Volume` as `float64` vs `int64`) and index tz-awareness —
`data_refresh._align_tz()` (`data_refresh.py:102`) exists precisely because "a
cached CSV can round-trip either way". Every downstream consumer
(`market_context.attach`, `refresh_rs_cache`, every indicator in `_scan_one`)
assumes the live-download shape, so the load path must normalize before the
cache can be trusted. **This task is the load-bearing guard for the whole plan.**

**Files:**
- Modify: `swingbot/core/marketdata/data_store.py` (add after `load_from_disk`, line 204)
- Test: `tests/marketdata/test_frame_equivalence.py` (create)

**Interfaces:**
- Consumes: `config.*` from Task 1 (not directly used here, but Task 1 must land first — shared file ordering).
- Produces: `data_store.load_normalized(ticker: str, interval: str, base_dir: str = DATA_DIR) -> pd.DataFrame | None`
  — returns a frame with columns exactly `["Open", "High", "Low", "Close", "Volume"]`
  (all `float64`), a tz-naive `DatetimeIndex`, sorted, de-duplicated. Returns
  `None` if the file is missing or unreadable. Task 3 calls this.

- [ ] **Step 1: Write the failing test**

Create `tests/marketdata/test_frame_equivalence.py`:

```python
"""v47: a cached frame must be indistinguishable from a live-download frame.

The whole cache-first design rests on this. fetch_interval_data() resolves
symbols through the same candidate_symbols() helper as get_daily_data(), uses
the same auto_adjust=True, and for daily requests period="max" -- a superset of
the 10y get_daily_data asks for. So the DATA is equivalent by construction; what
is NOT guaranteed is the shape after a to_csv/read_csv round-trip.
"""
import pandas as pd
import pytest

from swingbot.core.marketdata import data_store
from tests.helpers import make_ohlcv


@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path / "market_data")


def test_round_trip_preserves_columns_dtypes_and_index(cache_dir):
    live = make_ohlcv([100.0, 101.0, 102.0, 103.0])
    data_store.save_to_disk(live, "TEST", "daily", base_dir=cache_dir)

    loaded = data_store.load_normalized("TEST", "daily", base_dir=cache_dir)

    assert list(loaded.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert all(str(loaded[c].dtype) == "float64" for c in loaded.columns)
    assert isinstance(loaded.index, pd.DatetimeIndex)
    assert loaded.index.tz is None
    assert loaded.index.is_monotonic_increasing
    assert not loaded.index.has_duplicates
    pd.testing.assert_frame_equal(loaded, live, check_dtype=True)


def test_tz_aware_cached_index_is_flattened(cache_dir):
    """A CSV written by an intraday refresh round-trips tz-aware. The scan's
    frames are compared against tz-naive daily frames downstream, so an
    unflattened index raises on comparison rather than silently misaligning."""
    live = make_ohlcv([100.0, 101.0, 102.0])
    live.index = live.index.tz_localize("UTC")
    data_store.save_to_disk(live, "TZT", "daily", base_dir=cache_dir)

    loaded = data_store.load_normalized("TZT", "daily", base_dir=cache_dir)

    assert loaded.index.tz is None


def test_missing_file_returns_none(cache_dir):
    assert data_store.load_normalized("NOPE", "daily", base_dir=cache_dir) is None


def test_unreadable_file_returns_none_rather_than_raising(cache_dir):
    """A truncated/corrupt CSV must degrade to a cache miss, not kill the scan."""
    path = data_store.cache_path("BAD", "daily", base_dir=cache_dir)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("this is not a csv\x00\x00")

    assert data_store.load_normalized("BAD", "daily", base_dir=cache_dir) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_frame_equivalence.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.marketdata.data_store' has no attribute 'load_normalized'`

- [ ] **Step 3: Implement `load_normalized`**

In `swingbot/core/marketdata/data_store.py`, directly after `load_from_disk`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_frame_equivalence.py`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/data_store.py tests/marketdata/test_frame_equivalence.py
git commit -m "feat(v47): normalize cache-loaded frames to the live-download shape"
```

---

### Task 3: Route the crawl through the cache, collect a cold list

**Files:**
- Modify: `swingbot/core/scanning/engine.py:614-681` (`_crawl_latest_data`)
- Test: `tests/scanning/test_crawl_cache_first.py` (create)

**Interfaces:**
- Consumes: `data_store.load_normalized(...)` (Task 2), `config.SCAN_CACHE_MAX_AGE_HOURS` (Task 1).
- Produces: `engine._load_cached_daily(ticker: str) -> pd.DataFrame | None` — returns a
  normalized frame when the cache is present and fresh, else `None`.
  `_crawl_latest_data` keeps its `(tickers, progress) -> dict` signature and its
  `LRUFrames` return type. Task 4 replaces the placeholder sequential fetch of
  the `cold` list; Task 6 reuses `_load_cached_daily`.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_crawl_cache_first.py`:

```python
"""v47: the scan reads market_data/daily/*.csv first and only fetches misses.

At 5-minute ticks over a 6.5h session this is the difference between ~78 full
10-year downloads per ticker per day and ~1.
"""
import pytest

from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


@pytest.fixture
def no_network(monkeypatch):
    """Any get_daily_data call is recorded; none are allowed to hit yfinance."""
    calls = []

    def _fake(ticker, period=None):
        calls.append(ticker)
        return make_ohlcv([10.0, 11.0, 12.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _fake)
    return calls


def test_warm_ticker_is_served_from_cache_with_no_fetch(monkeypatch, no_network):
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT"])

    assert set(frames) == {"AAPL", "MSFT"}
    assert no_network == [], "a warm ticker must cost zero network calls"
    assert frames["AAPL"].equals(cached)


def test_cold_ticker_falls_back_to_a_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._crawl_latest_data(["AAPL"])

    assert no_network == ["AAPL"]
    assert "AAPL" in frames


def test_mixed_warm_and_cold_fetches_only_the_cold_ones(monkeypatch, no_network):
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(
        scan_engine, "_load_cached_daily",
        lambda t: cached if t in ("AAPL", "MSFT") else None,
    )

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "NVDA"])

    assert no_network == ["NVDA"]
    assert set(frames) == {"AAPL", "MSFT", "NVDA"}


def test_stop_request_still_ends_the_crawl_early(monkeypatch, no_network):
    """The existing per-ticker stop checkpoint must survive the rewrite."""
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: make_ohlcv([1.0, 2.0]))
    monkeypatch.setattr(scan_engine, "is_stop_requested", lambda: True)

    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "NVDA"])

    assert len(frames) == 0


def test_progress_counters_still_advance(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: make_ohlcv([1.0, 2.0]))
    progress = scan_engine.ScanProgress()

    scan_engine._crawl_latest_data(["AAPL", "MSFT"], progress)

    assert progress.total == 2
    assert progress.done == 2
    assert progress.stage == "crawling data"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_crawl_cache_first.py`
Expected: FAIL — `AttributeError: <module 'swingbot.core.scanning.engine'> does not have the attribute '_load_cached_daily'`

- [ ] **Step 3: Add `_load_cached_daily` and rewrite the crawl loop**

Add the import near the other marketdata imports in `swingbot/core/scanning/engine.py` (line 87 area):

```python
from swingbot.core.marketdata import data_refresh, data_store
```

Add `_load_cached_daily` immediately above `_crawl_latest_data`:

```python
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
```

Replace the body of the `for ticker in tickers:` loop in `_crawl_latest_data`
(lines 661-677) with:

```python
    cold = []
    for ticker in tickers:
        if is_stop_requested():
            log.info("Crawl: stop requested -- ending early (%d/%d ticker(s) resolved so far)",
                      len(results), len(tickers))
            if progress is not None:
                progress.stopped = True
            return results
        df = _load_cached_daily(ticker)
        if df is not None:
            results[ticker] = df
            if progress is not None:
                progress.done += 1
                progress.current_ticker = ticker
            continue
        cold.append(ticker)

    # Placeholder -- Task 4 replaces this with the threshold + process pool.
    for ticker in cold:
        if is_stop_requested():
            if progress is not None:
                progress.stopped = True
            break
        try:
            df = get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
        except Exception as e:
            log.error("Crawl: error fetching data for %s: %s", ticker, e)
            df = None
        if df is not None:
            results[ticker] = df
        if progress is not None:
            progress.done += 1
            progress.current_ticker = ticker
```

Update the closing log line to report the split:

```python
    elapsed = time.monotonic() - started
    log.info("Crawl complete in %.1fs: %d/%d ticker(s) resolved (%d from cache, %d fetched)",
              elapsed, len(results), len(tickers), len(results) - len(cold), len(cold))
    return results
```

Also update `_crawl_latest_data`'s docstring: the "Fetched ONE TICKER AT A TIME,
sequentially" paragraph now describes the *cold* path only. Keep the entire
yfinance `_DFS` rationale — it is still why threads are forbidden — and add one
sentence saying warm tickers never reach it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_crawl_cache_first.py`
Expected: PASS (5 tests)

- [ ] **Step 5: Confirm no scanning regression**

Run: `python scripts/dev/testrun.py file tests/scanning/`
Expected: PASS, `0 failed`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_crawl_cache_first.py
git commit -m "feat(v47): serve the scan crawl from the daily cache, collect cold tickers"
```

---

### Task 4: Fetch the cold list, with a process-pool fallback

**Files:**
- Modify: `swingbot/core/scanning/engine.py` (add `_fetch_cold_frames` above `_crawl_latest_data`; replace the Task 3 placeholder loop)
- Test: `tests/scanning/test_cold_fetch_pool.py` (create)

**Interfaces:**
- Consumes: `config.COLD_FETCH_PROCESS_THRESHOLD`, `config.FETCH_WORKERS` (Task 1).
- Produces: `engine._fetch_cold_frames(tickers: list, progress=None) -> list[tuple[str, "pd.DataFrame | None"]]`
  — order-preserving, error-isolated, `(ticker, frame_or_None)` pairs.
  `engine._resolve_workers() -> int`. `engine._fetch_one_ticker(ticker: str)`
  is the module-level process-pool entry point. Task 5 tests
  `_fetch_cold_frames`; Task 6 reuses it.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_cold_fetch_pool.py`:

```python
"""v47: cold tickers fetch sequentially below the threshold, pooled above it."""
import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def test_resolve_workers_auto_is_at_least_one(monkeypatch):
    monkeypatch.setattr(config, "FETCH_WORKERS", 0)
    assert scan_engine._resolve_workers() >= 1


def test_resolve_workers_honours_an_explicit_value(monkeypatch):
    monkeypatch.setattr(config, "FETCH_WORKERS", 3)
    assert scan_engine._resolve_workers() == 3


def test_below_threshold_never_builds_a_process_pool(monkeypatch):
    """The common case (a ticker or two the refresh loop hasn't caught up on)
    must take today's exact sequential path -- zero new risk surface."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 10)
    monkeypatch.setattr(scan_engine, "get_daily_data",
                        lambda t, period=None: make_ohlcv([1.0, 2.0, 3.0]))

    def _boom(*a, **kw):
        raise AssertionError("process pool must not be built below the threshold")

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _boom)

    pairs = scan_engine._fetch_cold_frames(["AAPL", "MSFT"])

    assert [t for t, _ in pairs] == ["AAPL", "MSFT"]
    assert all(df is not None for _, df in pairs)


def test_above_threshold_uses_the_process_pool(monkeypatch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    used = []

    class _FakePool:
        def __init__(self, max_workers=None):
            used.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            return [(t, make_ohlcv([1.0, 2.0])) for t in items]

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _FakePool)

    pairs = scan_engine._fetch_cold_frames(["A", "B", "C"])

    assert used, "the process pool should have been constructed"
    assert [t for t, _ in pairs] == ["A", "B", "C"]


def test_one_failing_ticker_does_not_abort_the_batch(monkeypatch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 10)

    def _flaky(ticker, period=None):
        if ticker == "BAD":
            raise ValueError("no data returned")
        return make_ohlcv([1.0, 2.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _flaky)

    pairs = scan_engine._fetch_cold_frames(["AAPL", "BAD", "MSFT"])

    assert [t for t, _ in pairs] == ["AAPL", "BAD", "MSFT"]
    assert dict(pairs)["BAD"] is None
    assert dict(pairs)["AAPL"] is not None


def test_empty_cold_list_is_a_no_op(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not build a pool for an empty list")

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _boom)
    assert scan_engine._fetch_cold_frames([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py`
Expected: FAIL — `_resolve_workers` / `_fetch_cold_frames` / `ProcessPoolExecutor` not found on the module

- [ ] **Step 3: Implement the fetch helpers**

Extend the existing import at `swingbot/core/scanning/engine.py:51`:

```python
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
```

Add above `_crawl_latest_data`:

```python
def _resolve_workers() -> int:
    """FETCH_WORKERS, with 0 meaning auto.

    A Field default is a string cast by int() (config.py:705), so a computed
    cpu_count default cannot live in the schema -- 0-as-auto is how it is
    expressed. Leaves one core for the bot's own event loop; the work is
    network-bound anyway, so oversubscribing buys nothing.
    """
    configured = int(getattr(config, "FETCH_WORKERS", 0) or 0)
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2) - 1)


def _fetch_one_ticker(ticker: str) -> tuple:
    """Process-pool entry point: must be module-level to be picklable.

    Returns (ticker, DataFrame|None). Never raises -- a worker that raised
    would surface as a BrokenProcessPool and take the whole batch with it,
    which is exactly the "one bad ticker never aborts the crawl" contract
    _crawl_latest_data has always had.
    """
    try:
        return ticker, get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
    except Exception as exc:
        log.error("Crawl: error fetching data for %s: %s", ticker, exc)
        return ticker, None


def _fetch_cold_frames(tickers: list, progress: "ScanProgress" = None) -> list:
    """v47: fetch the cache misses, sequentially or pooled.

    PROCESSES, never threads. The pinned yfinance 0.2.66 builds download() on a
    shared module-level global (_DFS) that it writes non-reentrantly; the
    reentrancy fix landed only in yfinance 1.4.0, a major bump this project has
    not taken. A ThreadPoolExecutor here once let two tickers' downloads clobber
    each other mid-flight -- two real watchlist tickers were logged as open
    trades with byte-identical entry/stop/target/confidence values, one
    ticker's price data attributed to the other. Separate processes have
    separate interpreters and separate memory, so _DFS is not shared and cannot
    be clobbered across workers.

    Returns order-preserving (ticker, DataFrame|None) pairs.
    """
    if not tickers:
        return []

    threshold = int(getattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 10))
    if len(tickers) <= threshold:
        pairs = []
        for ticker in tickers:
            if is_stop_requested():
                if progress is not None:
                    progress.stopped = True
                break
            pairs.append(_fetch_one_ticker(ticker))
            if progress is not None:
                progress.done += 1
                progress.current_ticker = ticker
        return pairs

    workers = _resolve_workers()
    log.info("Crawl: %d cold ticker(s) over the threshold of %d -- fetching across %d process(es)",
              len(tickers), threshold, workers)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pairs = list(pool.map(_fetch_one_ticker, tickers))
    if progress is not None:
        progress.done += len(pairs)
        progress.current_ticker = tickers[-1]
    return pairs
```

- [ ] **Step 4: Replace the Task 3 placeholder**

In `_crawl_latest_data`, replace the entire `# Placeholder -- Task 4 replaces
this...` block with:

```python
    for ticker, df in _fetch_cold_frames(cold, progress):
        if df is not None:
            results[ticker] = df
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py`
Expected: PASS (6 tests)

Run: `python scripts/dev/testrun.py file tests/scanning/test_crawl_cache_first.py`
Expected: PASS (5 tests) — the Task 3 behaviour is unchanged by the swap

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_cold_fetch_pool.py
git commit -m "feat(v47): fetch cold tickers through a process pool above the threshold"
```

---

### Task 5: Regression test — cross-ticker data mixing

The failure this design routes around **already happened in production and
corrupted real trade records**. It gets a test aimed directly at it, not
incidental coverage.

**Files:**
- Test: `tests/scanning/test_no_cross_ticker_mixing.py` (create)
- Modify: none (this task adds only the guard)

**Interfaces:**
- Consumes: `engine._fetch_cold_frames`, `engine._fetch_one_ticker` (Task 4).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the test**

Create `tests/scanning/test_no_cross_ticker_mixing.py`:

```python
"""v47 regression guard: a fetched frame must belong to ITS OWN ticker.

This is not a hypothetical. The scan's crawl used to run through a
ThreadPoolExecutor; yfinance 0.2.66 builds download() on a shared, non-reentrant
module global (_DFS), and two real watchlist tickers scanned seconds apart in
the same concurrent batch were once logged as open paper trades with
byte-identical entry/stop/target/confidence values -- one ticker's price data
had been attributed to the other. The crawl was made sequential in response.

v47 restores concurrency using PROCESSES instead of threads, so the shared
global is not shared. This test asserts the routing that makes that claim true:
each ticker's frame carries a price signature derived from its own symbol, so a
swap is detectable without any network and without trusting Yahoo's data.
"""
import pytest

from swingbot import config
from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


def _signature_price(ticker: str) -> float:
    """A per-ticker price no other ticker in the batch can produce."""
    return 100.0 + sum(ord(c) for c in ticker)


def _identifiable_frame(ticker: str, period=None):
    base = _signature_price(ticker)
    return make_ohlcv([base, base + 1.0, base + 2.0])


@pytest.fixture
def identifiable_fetch(monkeypatch):
    monkeypatch.setattr(scan_engine, "get_daily_data", _identifiable_frame)


BATCH = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META", "NFLX",
         "AMD", "INTC", "ORCL", "CRM"]


def test_sequential_path_never_mixes_tickers(monkeypatch, identifiable_fetch):
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", len(BATCH) + 1)

    pairs = scan_engine._fetch_cold_frames(list(BATCH))

    assert [t for t, _ in pairs] == BATCH
    for ticker, df in pairs:
        assert df is not None
        assert df["Close"].iloc[0] == _signature_price(ticker), (
            f"{ticker} received another ticker's data"
        )


def test_pooled_path_never_mixes_tickers(monkeypatch, identifiable_fetch):
    """Above the threshold the pool is used. A fake pool stands in for
    ProcessPoolExecutor so the test needs no subprocess and no network, but it
    exercises the real _fetch_one_ticker and the real result-merging."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)

    class _InlinePool:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            # Deliberately reversed: a correct implementation carries the
            # ticker in the RESULT, so completion order cannot misattribute.
            done = {t: fn(t) for t in reversed(list(items))}
            return [done[t] for t in items]

    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlinePool)

    pairs = scan_engine._fetch_cold_frames(list(BATCH))

    assert [t for t, _ in pairs] == BATCH
    for ticker, df in pairs:
        assert df is not None
        assert df["Close"].iloc[0] == _signature_price(ticker), (
            f"{ticker} received another ticker's data"
        )


def test_frames_reach_the_crawl_result_under_their_own_key(monkeypatch, identifiable_fetch):
    """End-to-end through _crawl_latest_data: nothing between the fetch and
    the LRUFrames result may re-key a frame."""
    monkeypatch.setattr(config, "COLD_FETCH_PROCESS_THRESHOLD", 2)
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._crawl_latest_data(list(BATCH))

    for ticker in BATCH:
        assert frames[ticker]["Close"].iloc[0] == _signature_price(ticker)


def test_fetch_one_ticker_returns_its_own_symbol(identifiable_fetch):
    """The invariant the pooled path depends on: the worker's return value
    carries the ticker, so results are never matched up by position alone."""
    ticker, df = scan_engine._fetch_one_ticker("NVDA")
    assert ticker == "NVDA"
    assert df["Close"].iloc[0] == _signature_price("NVDA")
```

- [ ] **Step 2: Run the test**

Run: `python scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py`
Expected: PASS (4 tests). If any fail, **stop** — the concurrency in Task 4 is
unsafe and must be fixed before proceeding, not worked around in the test.

- [ ] **Step 3: Commit**

```bash
git add tests/scanning/test_no_cross_ticker_mixing.py
git commit -m "test(v47): guard the cold-fetch path against cross-ticker data mixing"
```

---

### Task 6: Serve the regime benchmark and sector ETFs from cache too

The watchlist crawl is not the scan's only sequential fetch: the regime
benchmark (`engine.py:1267`) and up to 11 SPDR sector ETFs (`_fetch_frames`,
`engine.py:726`) add ~12 more per scan.

**Files:**
- Modify: `swingbot/core/scanning/engine.py:726-743` (`_fetch_frames`)
- Modify: `swingbot/core/scanning/engine.py:1267` (the `spy_df` fetch)
- Test: `tests/scanning/test_sidelist_cache_first.py` (create)

**Interfaces:**
- Consumes: `engine._load_cached_daily` (Task 3), `engine._fetch_cold_frames` (Task 4).
- Produces: `_fetch_frames` keeps its `(symbols: list) -> dict` signature.
  `engine._daily_frame_for(symbol: str)` — cache-first single-symbol accessor
  used for the regime benchmark.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_sidelist_cache_first.py`:

```python
"""v47: SPY and the sector ETFs come from the cache too.

They are ~12 further sequential fetches per scan on top of the watchlist crawl.
"""
import pytest

from swingbot.core.scanning import engine as scan_engine
from tests.helpers import make_ohlcv


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def _fake(ticker, period=None):
        calls.append(ticker)
        return make_ohlcv([10.0, 11.0, 12.0])

    monkeypatch.setattr(scan_engine, "get_daily_data", _fake)
    return calls


def test_warm_sector_etfs_cost_no_network(monkeypatch, no_network):
    cached = make_ohlcv([50.0, 51.0, 52.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    frames = scan_engine._fetch_frames(["XLK", "XLF", "XLE"])

    assert set(frames) == {"XLK", "XLF", "XLE"}
    assert no_network == []


def test_cold_sector_etfs_still_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK", "XLF"])

    assert sorted(no_network) == ["XLF", "XLK"]
    assert set(frames) == {"XLK", "XLF"}


def test_a_failing_etf_is_absent_not_fatal(monkeypatch):
    def _flaky(ticker, period=None):
        raise ValueError("no data")

    monkeypatch.setattr(scan_engine, "get_daily_data", _flaky)
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    frames = scan_engine._fetch_frames(["XLK"])

    assert frames == {}


def test_daily_frame_for_prefers_cache(monkeypatch, no_network):
    cached = make_ohlcv([400.0, 401.0])
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: cached)

    df = scan_engine._daily_frame_for("SPY")

    assert df.equals(cached)
    assert no_network == []


def test_daily_frame_for_falls_back_to_fetch(monkeypatch, no_network):
    monkeypatch.setattr(scan_engine, "_load_cached_daily", lambda t: None)

    df = scan_engine._daily_frame_for("SPY")

    assert df is not None
    assert no_network == ["SPY"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_sidelist_cache_first.py`
Expected: FAIL — `_daily_frame_for` not found, and `_fetch_frames` still fetches warm symbols

- [ ] **Step 3: Rewrite `_fetch_frames` and add `_daily_frame_for`**

Replace the body of `_fetch_frames` (keeping its docstring's "a symbol whose
fetch fails is simply absent" contract, and updating it to say cache-first):

```python
def _fetch_frames(symbols: list) -> dict:
    """Cache-first resolution for a small side-list of symbols (sector ETFs,
    currently at most the 11 SPDR sector funds in etfs.json).

    v47: warm symbols come from market_data/daily/*.csv and cost no network;
    the cold remainder goes through _fetch_cold_frames, which is sequential at
    this size (11 symbols is far below COLD_FETCH_PROCESS_THRESHOLD) and so
    keeps the same one-at-a-time behaviour this list has always had. A symbol
    whose fetch fails is simply absent from the result, exactly like
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
```

At `engine.py:1267`, replace:

```python
        spy_df = get_daily_data(config.MARKET_REGIME_TICKER)
```

with:

```python
        spy_df = _daily_frame_for(config.MARKET_REGIME_TICKER)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_sidelist_cache_first.py`
Expected: PASS (5 tests)

- [ ] **Step 5: Confirm the sector-RS behaviour is unchanged**

Run: `python scripts/dev/testrun.py file tests/scanning/test_sector_rs.py`
Expected: PASS, `0 failed` — `_apply_sector_rs`'s "at least 2 sector ETF frames"
guard depends on `_fetch_frames`'s contract, which this task preserves

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_sidelist_cache_first.py
git commit -m "feat(v47): serve the regime benchmark and sector ETFs from the daily cache"
```

---

# Phase 3 — Offline replay

### Task 7: Parallelise the scenario replay

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py:145-164` (`run_scenario_backtest`)
- Test: `tests/backtesting/test_scenario_parallel.py` (create)

**Interfaces:**
- Consumes: `config.FETCH_WORKERS` (Task 1).
- Produces: `run_scenario_backtest(frames, start, end, *, gates, scale_out=True, horizons=None, workers=None) -> dict`
  — the return shape (`{"pooled": ..., "by_horizon": {...}}`) is **unchanged**.
  `workers=1` forces the sequential path.
  `backtest_scenarios._replay_ticker(args) -> dict[str, list]` is the pool entry
  point (one task per ticker, all horizons inside).

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_scenario_parallel.py`:

```python
"""v47: parallel scenario replay must be output-identical to sequential.

This is the gate protecting the closed pre-registrations in
docs/claude/backtest-methodology.md -- a changed aggregate here would silently
invalidate measurements that must not be re-run.
"""
import pytest

from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.backtesting.backtest_scenarios import run_scenario_backtest
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


@pytest.fixture
def frames():
    """A handful of tickers with enough bars for the slowest horizon's
    indicators to have a value at all."""
    import numpy as np
    rng = np.random.default_rng(44)
    out = {}
    for i, ticker in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        base = 100.0 + i * 10
        walk = base + np.cumsum(rng.normal(0, 1.0, 400))
        out[ticker] = make_ohlcv([float(x) for x in walk])
    return out


def test_parallel_matches_sequential(frames):
    horizons = list(HORIZONS)[:3]
    gates = backtest_scenarios.CONFLUENCE_GATES

    sequential = run_scenario_backtest(frames, None, None, gates=gates,
                                       horizons=horizons, workers=1)
    parallel = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=4)

    assert parallel["pooled"] == sequential["pooled"]
    assert parallel["by_horizon"] == sequential["by_horizon"]


def test_worker_completion_order_cannot_change_the_result(frames, monkeypatch):
    """Results are grouped by the horizon carried in each task's RESULT, so a
    pool whose workers finish out of order still aggregates identically."""
    horizons = list(HORIZONS)[:3]
    gates = backtest_scenarios.CONFLUENCE_GATES

    expected = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=1)

    class _OutOfOrderPool:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            # Compute in reverse, return in input order -- exactly what
            # ProcessPoolExecutor.map guarantees. This catches any dependency
            # on the order work actually COMPLETES in.
            items = list(items)
            computed = {i: fn(a) for i, a in reversed(list(enumerate(items)))}
            return [computed[i] for i in range(len(items))]

    monkeypatch.setattr(backtest_scenarios, "ProcessPoolExecutor", _OutOfOrderPool)

    shuffled = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=4)

    assert shuffled["pooled"] == expected["pooled"]
    assert shuffled["by_horizon"] == expected["by_horizon"]


def test_date_window_still_filters_signals(frames):
    gates = backtest_scenarios.CONFLUENCE_GATES
    horizons = list(HORIZONS)[:2]

    everything = run_scenario_backtest(frames, None, None, gates=gates,
                                       horizons=horizons, workers=2)
    windowed = run_scenario_backtest(frames, "2025-01-01", "2025-06-30",
                                     gates=gates, horizons=horizons, workers=2)

    assert windowed["pooled"]["n"] <= everything["pooled"]["n"]


def test_single_worker_never_builds_a_pool(frames, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("workers=1 must stay sequential")

    monkeypatch.setattr(backtest_scenarios, "ProcessPoolExecutor", _boom)

    result = run_scenario_backtest(frames, None, None,
                                   gates=backtest_scenarios.CONFLUENCE_GATES,
                                   horizons=list(HORIZONS)[:2], workers=1)

    assert "pooled" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_parallel.py`
Expected: FAIL — `run_scenario_backtest() got an unexpected keyword argument 'workers'`

- [ ] **Step 3: Rewrite `run_scenario_backtest`**

Add to the imports at the top of `swingbot/core/backtesting/backtest_scenarios.py`:

```python
import os
from concurrent.futures import ProcessPoolExecutor

from swingbot import config
```

Replace `run_scenario_backtest` (lines 145-164) with:

```python
def _replay_ticker(args) -> dict:
    """All horizons for ONE ticker -- the process-pool entry point, so it must
    be module-level and take a single picklable argument.

    Grouped per ticker rather than per (ticker, horizon) pair on purpose: the
    OHLCV frame is the expensive thing to move across a process boundary (~2MB
    for a ten-year daily history), and a per-pair split would ship the same
    frame once per horizon -- ten times the IPC for parallelism a 2-4 core box
    cannot use anyway. At 300-500 tickers there are already far more tasks
    than cores.

    Returns {horizon_key: [exit_result, ...]}. The horizon travels in the
    RESULT rather than being inferred from completion order, which is what
    makes the pooled path order-independent.
    """
    ticker, df, horizons, start, end, gates, scale_out = args
    out = {hk: [] for hk in horizons}
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk, gates=gates):
            signal_date = str(df.index[i].date())
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            out[hk].append(simulate_exit(df, i, plan, scale_out=scale_out))
    return out


def _resolve_replay_workers(workers: int | None) -> int:
    if workers is not None:
        return max(1, int(workers))
    configured = int(getattr(config, "FETCH_WORKERS", 0) or 0)
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2) - 1)


def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None, workers=None) -> dict:
    """frames: {ticker: OHLCV df}. start/end (ISO or None) restrict SIGNAL
    dates -- the exit walk may run past `end`, same convention as
    run_backtest_daterange.

    v47: each ticker is replayed across a process pool, all horizons inside
    one task. Every task is fully independent -- it reads one frame and
    contributes only to its own result lists -- and aggregation happens
    strictly after every task returns, so the output is identical to the
    sequential walk. `workers=1` forces the sequential path; None resolves
    FETCH_WORKERS (0 = auto).

    This is CPU-bound work on in-memory frames with no network and no yfinance
    involvement, so it carries none of the crawl's thread-safety constraints --
    processes are used here purely because the work is GIL-bound Python.
    """
    horizons = horizons or list(HORIZONS)
    results_by_hz: dict = {hk: [] for hk in horizons}

    tasks = [
        (ticker, df, horizons, start, end, gates, scale_out)
        for ticker, df in frames.items()
    ]

    n = _resolve_replay_workers(workers)
    if n <= 1 or len(tasks) <= 1:
        per_ticker_results = [_replay_ticker(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=n) as pool:
            per_ticker_results = list(pool.map(_replay_ticker, tasks))

    for per_ticker in per_ticker_results:
        for hk, results in per_ticker.items():
            results_by_hz[hk].extend(results)

    all_results = [r for rs in results_by_hz.values() for r in rs]
    return {"pooled": _aggregate(all_results),
            "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_parallel.py`
Expected: PASS (4 tests)

- [ ] **Step 5: Confirm the existing scenario tests still pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`
Expected: PASS, `0 failed`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_scenario_parallel.py
git commit -m "feat(v47): replay scenario backtests across a process pool"
```

---

# Phase 4 — Close-out

### Task 8: Full gate, documentation, and version bump

**Files:**
- Modify: `VERSION.json`
- Modify: `docs/claude/known-traps.md`
- Modify: `docs/superpowers/plans/2026-08-21-v48-scan-throughput.md` (Progress block)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. The pass count will have risen by ~28 (the new
tests); a changed count is not a failure, a `failed` or `xfailed` is.

- [ ] **Step 2: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py $(git ls-files 'swingbot/**/*.py')`
Expected: no output

- [ ] **Step 3: Update the known-traps entry**

`docs/claude/known-traps.md` currently says the two OHLCV caches are separate and
that the live scan does not read `market_data/`. That is now false. Replace the
`Scans run through map_tickers()...` bullet (line 84) with:

```markdown
- Scans run through `map_tickers()` (`SCAN_WORKERS`, default 4). Anything
  touching shared state (`state.confirm_or_update`, funnel counters) must stay
  serial/post-join.
- **The live scan reads `market_data/daily/` now (v47).** `_crawl_latest_data`
  is cache-first: `_load_cached_daily()` serves any ticker whose CSV is fresher
  than `SCAN_CACHE_MAX_AGE_HOURS` (6h), and only the cold remainder is fetched.
  So the two OHLCV caches are no longer "backtest reads one, scan reads
  neither" — `market_data/` is now on the live path, and a change to
  `data_store.load_normalized()` affects live alerts.
- **Cold fetches use PROCESSES, never threads** (`_fetch_cold_frames`). yfinance
  0.2.66's `download()` writes a shared module global (`_DFS`) non-reentrantly;
  a thread pool here once attributed one ticker's price data to another and
  logged both as open trades with identical values.
  `tests/scanning/test_no_cross_ticker_mixing.py` is the standing guard — if
  you ever make this concurrent a different way, that test must still pass.
```

- [ ] **Step 4: Bump the versions**

In `VERSION.json`: `bot` `1.3.2` → `1.3.3`, `ui` `1.8.0` → `1.8.1`, and set both
`_updated` timestamps to now. Patch on both lines: the bot does what it did
before but faster (no user has to look at it anew), and the UI gains three new
Settings rows, which is "a new control" — a patch.

- [ ] **Step 5: Measure the result and fill in the Progress block**

Success criterion 1 is "a warm scan issues zero OHLCV network calls". Measure it
rather than assuming it. With the cache warm (let `market_data_refresh` run once,
or run `python scripts/data/fetch_backtest_data.py`), run:

```bash
python -c "
import logging, time
logging.basicConfig(level=logging.INFO, format='%(message)s')
from swingbot.core.scanning import engine
from swingbot.core.marketdata.watchlist import load_watchlist
calls = []
real = engine.get_daily_data
engine.get_daily_data = lambda t, period=None: (calls.append(t), real(t, period=period))[1]
tickers = load_watchlist()
t0 = time.monotonic()
frames = engine._crawl_latest_data(tickers)
print(f'{len(tickers)} tickers | {len(frames)} frames | {len(calls)} fetches | {time.monotonic()-t0:.1f}s')
print('fetched:', calls)
"
```

Expected on a warm cache: `0 fetches`, and a crawl time in the low seconds. The
`Crawl complete in ...` log line from Task 3 reports the same cache/fetch split.

Then add to the bottom of this plan file, filling in the real numbers:

```markdown
## Progress

- [x] Tasks 1-8 complete. Live scan is cache-first; cold fetches are pooled by
      process above COLD_FETCH_PROCESS_THRESHOLD; scenario replay is parallel
      per ticker.
- Measured warm crawl: N tickers, N frames, 0 fetches, N.Ns (was: N fetches,
  N.Ns).
- Full suite: `1686+N passed, 66 skipped, 0 failed, 0 xfailed`.
```

- [ ] **Step 6: Commit**

```bash
git add VERSION.json docs/claude/known-traps.md docs/superpowers/plans/2026-08-21-v48-scan-throughput.md
git commit -m "docs(v47): record the live scan's new cache dependency, bump versions"
```

- [ ] **Step 7: Close the plan out**

Per `docs/claude/document-conventions.md`, move the plan and its spec into
`implemented/` as part of the closing commit:

```bash
git mv docs/superpowers/plans/2026-08-21-v48-scan-throughput.md docs/superpowers/plans/implemented/
git mv docs/superpowers/specs/2026-08-21-v47-scan-throughput-design.md docs/superpowers/specs/implemented/
git commit -m "docs(v47): close out the scan-throughput plan"
```
