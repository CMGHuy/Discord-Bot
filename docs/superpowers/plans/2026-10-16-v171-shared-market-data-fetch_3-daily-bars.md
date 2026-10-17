# v171 Shared market-data fetch. Part 3: daily bars (V171-11..V171-16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-12:" -A 400 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_3-daily-bars.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D1 "CSV writes", D3, D4 including the partner's two-cache choice and the parity fixtures (a)-(d), D8 "`refresh_all` batches", Anti-goals "a delta-fetched frame that differs from a full fresh download", "silent depth loss" and "lookahead", Rollout "CSV safety")
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. After every task run `git -C $R status --short` and confirm the main tree is clean.

**Order.** V171-11 may start once part 1 is committed. V171-12 needs V171-11 and V171-8. V171-13 needs V171-12. V171-14 needs V171-12 and V171-10. V171-15 needs V171-12 and V171-10. V171-16 needs V171-11 only.

**Consumed from parts 1 and 2 (ledger names only):** `shared.kinds`: `Asker`, `DataKind.DAILY_BARS`, `PROVIDER_ALPACA`, `PROVIDER_YF`; `shared.layer.lease(kind, symbol, *, asker, deadline_s=30.0) -> ContextManager[bool]` (part 1: `off`/`count` or a spot symbol yields True with no Postgres; `on` yields True when this call holds the key, False when another holder finished or the lease statement failed open); `shared.counters`: `count(provider, kind, asker, outcome, n=1)`, `snapshot_and_clear()`, `merge(rows)`, `flush(force=False)`, `warn_fail_open(operation, exc)`; `router.asker_scope(asker)`, `router.current_asker()` (V171-8; a spawned worker enters the scope itself); `yf_safe.BudgetDeferred` (the re-export of `budget.BudgetDeferred`; only tier 4-5 yfinance calls are denied); `plan_manager.monitor_quotes` (V171-10, untouched here).

**Decisions this part fixes** (inside the ledger's contracts; the controller should check the ones marked *beyond the ledger*):

- **Two caches, one basis each, frames never cross.** `market_data/daily_alpaca/<SYMBOL>_daily.csv` holds `alpaca-all` bars and is written only by `daily_delta.write_daily`. `market_data/daily/<SYMBOL>.csv` stays yfinance `auto_adjust`; `write_daily` writes it too (with a sidecar), beside its existing writers. `write_daily` refuses any frame whose `attrs["source"]` does not belong to the target basis (`alpaca` -> `alpaca-all`; `yfinance` or `yfinance-fallback` -> `yfinance-auto_adjust`). An untagged frame is refused as well.
- **Only closed bars are persisted.** A bar is closed when its date is before today's New York date (`daily_delta._today_ny()`). The forming bar is spliced onto the returned frame in memory, but never written. As a result a symbol's CSV is rewritten at most once per trading day (the first delta after a new close), so a warm scan adds no CSV writes. The overlap check compares only bars dated on or before `last_verified` (the newest closed bar at the last write). So yesterday's forming bar, written mid-session by a legacy writer, can never fail the check.
- **When `layer.lease()` yields False, `write_daily` still writes** (controller decision, spec D1: unique temp names plus `os.replace` make two writers safe). It re-reads the file after the lease call, so a concurrent holder's rows are part of the union. It logs once per minute through `counters.warn_fail_open("daily-write", RuntimeError("lease not held"))`.
- *Beyond the ledger:* **the anchor fingerprint runs on both bases.** The yfinance basis also keeps its window `Dividends`/`Stock Splits` trigger. A dividend that the provider publishes after its ex-date has passed leaves the overlap closes in agreement and has no action in the window. Only an anchor bar catches it, and fixture (a) is exactly that case on both bases. The anchor costs one batched ranged request per basis per trading day.
- *Beyond the ledger:* **`DailyMeta` gains `anchor_checked: str | None = None`** (the ISO date of the last anchor check). Without it, "once per trading day" has nowhere to live. `write_daily` gains the keywords `today: date | None = None` and `anchor_checked: str | None = None`. Both are defaulted, and no other part calls `write_daily`.
- *Beyond the ledger:* **V171-12 adds one ranged Alpaca call.** `AlpacaProvider.daily_bars_between(tickers, start, end)` and `router.daily_bars_between(tickers, start, end)` are Alpaca-only, with no yfinance fallback, and go through `_attempt_many`, so V171-8's budget and breaker apply. Both the window fetch and the anchor fetch need a start and an end, and `router.daily_bars` takes only a period. V171-12 therefore also modifies `providers/alpaca_provider.py`, `providers/router.py` and their two test files. It runs after V171-8, the last task that edits `router.py`.
- *Beyond the ledger (shape of V171-13):* **provider calls run in spawned workers and the splice runs in the scan's own process.** `_crawl_delta` calls `daily_delta.delta_update` in the parent and injects `fetch_window`/`fetch_full` callables that each make one `_run_bounded` call per (basis, chunk). The ledger instead runs the whole `delta_update` in a worker. That layout would re-parse every full-history CSV in a fresh interpreter on every scan (the process-local `load_normalized` memo starts empty there) and would pickle every frame back, which is CPU the 1 vCPU cap does not have. Provider calls still never run in the parent's threads (Global Constraints, "cold fetches stay in processes"). Writes happen in the parent, under the lease.
- **Window.** `delta_window(meta, today)` starts 5 business days before `last_verified` (3 overlap bars plus a holiday margin) and ends `today`. It returns `None` (full refetch) when the start is more than `DELTA_WINDOW_MAX_DAYS` calendar days before `today`.
- **A provider miss never goes shallow and never crosses.** A warm symbol whose window fetch misses gets its cached frame unchanged, the same as today's warm path. A cold Alpaca-basis symbol whose full fetch misses falls back, for this call only, to the yfinance basis (read plus delta of `market_data/daily`, tagged `yfinance-fallback`), which is today's cold fallback. It never writes `daily_alpaca`.
- **`refresh_all` has no Alpaca leg** (V171-16). Every file it writes is yfinance-basis (D4), so writing an Alpaca frame there would cross caches. The Alpaca-basis daily file is kept current by the scan crawl and the re-anchor. The ledger's "Alpaca for the timeframes it serves" therefore resolves to none.
- **Telemetry.** A delta-spliced frame carries no `attrs["source"]`, so `_count_sources` counts it as `cache` (warm, as today). A full-refetched frame carries its provider tag, so it counts as cold. Every bar provider call is counted as kind `DAILY_BARS` with outcome `fetched` or `failed` per symbol. A worker returns its counter rows with the frames.

---

# Phase 3 — Daily bars: one writer, proven delta splice, warm scan, shared frames

### Task V171-11: One tolerance home; atomic unique-temp CSV writer; `_merge_save` and `save_to_disk` through it

**Model:** sonnet — constants and file I/O inside `marketdata`, behaviour unchanged

**Files:**
- Modify: `swingbot/core/marketdata/adjustments.py` (constants :8-10 and their uses in `adjustment_ratio` :14-39)
- Modify: `swingbot/core/marketdata/history_splice.py` (import :15-17, uses :31-41)
- Modify: `swingbot/core/marketdata/data_refresh.py` (import block :22-35; delete the copies :152, :162, :168; `_adjustment_ratio` :173-213 reads the imported names; `_merge_save` :245-252)
- Modify: `swingbot/core/marketdata/data_store.py` (new `atomic_write_csv` beside `save_to_disk` :209; `save_to_disk` :209-213; `update_cache` :416-421)
- Create: `tests/marketdata/test_atomic_csv_writer.py`
- Modify: `tests/marketdata/test_history_splice.py`

**Interfaces:**
- Consumes: `jsonio._replace_with_retry(tmp, path)` (exists, `swingbot/core/infra/jsonio.py:33`: the Windows `PermissionError` retry every atomic JSON write already uses).
- Produces:
  - `adjustments.ADJUSTMENT_MISMATCH_TOLERANCE = 0.01`, `adjustments.MIN_OVERLAP_BARS = 3`, `adjustments.DELTA_OVERLAP_TOLERANCE = 1e-4`. `_ADJUSTMENT_RATIO_DISPERSION` (0.005) stays private in `adjustments.py`, and `data_refresh` imports it instead of keeping its own copy. `git grep -n "_ADJUSTMENT_MISMATCH_TOLERANCE\|_MIN_OVERLAP_BARS" -- tests` finds nothing today, so no private alias is kept.
  - `data_store.atomic_write_csv(df: pd.DataFrame, path: str) -> None`. V171-12 writes both caches through it, and V171-16 writes through `_merge_save`, which calls it.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_atomic_csv_writer.py`:

```python
"""v171 D1/D4: one tolerance home, one atomic CSV writer with unique temp names."""
import inspect
import os
import re
import threading

import pandas as pd
import pytest

from swingbot.core.marketdata import adjustments, data_refresh, data_store, history_splice
from tests.helpers import make_ohlcv


def _read(path):
    return pd.read_csv(path, index_col=0, parse_dates=True)


def test_adjustments_owns_the_three_tolerances():
    assert adjustments.ADJUSTMENT_MISMATCH_TOLERANCE == 0.01
    assert adjustments.MIN_OVERLAP_BARS == 3
    assert adjustments.DELTA_OVERLAP_TOLERANCE == 1e-4
    for mod in (data_refresh, history_splice):
        assert mod.ADJUSTMENT_MISMATCH_TOLERANCE is adjustments.ADJUSTMENT_MISMATCH_TOLERANCE
        assert mod.MIN_OVERLAP_BARS is adjustments.MIN_OVERLAP_BARS
        src = inspect.getsource(mod)
        assert not re.search(r"^_?(ADJUSTMENT_MISMATCH_TOLERANCE|MIN_OVERLAP_BARS|"
                             r"_?ADJUSTMENT_RATIO_DISPERSION)\s*=", src, re.M), mod.__name__


def test_write_round_trips_and_leaves_only_the_target(tmp_path):
    df = make_ohlcv([100.0, 101.0, 102.0])
    path = str(tmp_path / "AAPL.csv")
    data_store.atomic_write_csv(df, path)
    pd.testing.assert_frame_equal(_read(path), df, check_freq=False)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def test_parent_directory_is_created(tmp_path):
    path = str(tmp_path / "daily_alpaca" / "AAPL_daily.csv")
    data_store.atomic_write_csv(make_ohlcv([1.0, 2.0]), path)
    assert os.path.exists(path)


def test_every_write_uses_its_own_temp_name(monkeypatch, tmp_path):
    seen = []
    real = data_store._replace_with_retry
    monkeypatch.setattr(data_store, "_replace_with_retry",
                        lambda tmp, path: (seen.append(tmp), real(tmp, path)))
    path = str(tmp_path / "AAPL.csv")
    data_store.atomic_write_csv(make_ohlcv([1.0]), path)
    data_store.atomic_write_csv(make_ohlcv([2.0]), path)
    assert len(set(seen)) == 2
    assert all(t.startswith(f"{path}.{os.getpid()}.") and t.endswith(".tmp") for t in seen)
    assert path + ".tmp" not in seen


def test_failed_replace_removes_its_temp_and_keeps_the_old_file(monkeypatch, tmp_path):
    path = str(tmp_path / "AAPL.csv")
    old = make_ohlcv([100.0, 101.0])
    data_store.atomic_write_csv(old, path)

    def boom(tmp, target):
        raise OSError("disk full")
    monkeypatch.setattr(data_store, "_replace_with_retry", boom)
    with pytest.raises(OSError):
        data_store.atomic_write_csv(make_ohlcv([1.0, 2.0, 3.0]), path)
    pd.testing.assert_frame_equal(_read(path), old, check_freq=False)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def test_concurrent_writers_never_tear_the_file(tmp_path):
    path = str(tmp_path / "AAPL.csv")
    frames = [make_ohlcv([float(i)] * 50) for i in range(8)]

    def work(df):
        for _ in range(10):
            data_store.atomic_write_csv(df, path)
    threads = [threading.Thread(target=work, args=(f,)) for f in frames]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = _read(path)
    assert any(final.equals(_read_like(f, tmp_path)) for f in frames)
    assert os.listdir(tmp_path) == ["AAPL.csv"]


def _read_like(df, tmp_path):
    probe = str(tmp_path / "probe.csv.cmp")
    df.to_csv(probe)
    out = _read(probe)
    os.remove(probe)
    return out


def test_every_existing_writer_goes_through_it(monkeypatch, tmp_path):
    calls = []
    real = data_store.atomic_write_csv

    def rec(df, path):
        calls.append(os.path.basename(path))
        real(df, path)
    monkeypatch.setattr(data_store, "atomic_write_csv", rec)
    monkeypatch.setattr(data_refresh, "atomic_write_csv", rec)
    base = str(tmp_path)
    data_store.save_to_disk(make_ohlcv([1.0, 2.0, 3.0, 4.0]), "AAPL", "daily", base_dir=base)
    data_store.update_cache(["AAPL"], "1d", base_dir=base,
                            fetch_fn=lambda s, start: make_ohlcv([4.0, 5.0], start="2024-01-05"))
    data_refresh._merge_save(None, make_ohlcv([1.0]), "MSFT", "daily", base)
    assert calls == ["AAPL.csv", "AAPL.csv", "MSFT.csv"]


def test_spot_writes_are_still_refused(tmp_path):
    with pytest.raises(ValueError):
        data_store.save_to_disk(make_ohlcv([1.0]), "XAUUSD", "daily", base_dir=str(tmp_path))
```

Append to `tests/marketdata/test_history_splice.py`:

```python
def test_splice_reads_the_shared_tolerance(monkeypatch):
    from swingbot.core.marketdata import history_splice
    cached, live = _pair()
    cached = cached.copy()
    cached[["Open", "High", "Low", "Close"]] *= 1.10      # a 10% basis gap
    assert len(splice_cached_history(live, cached, "AAPL")) == len(live)
    monkeypatch.setattr(history_splice, "ADJUSTMENT_MISMATCH_TOLERANCE", 0.5)
    assert len(splice_cached_history(live, cached, "AAPL")) == 302
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_atomic_csv_writer.py` and `python $WT/scripts/dev/testrun.py file tests/marketdata/test_history_splice.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.marketdata.adjustments' has no attribute 'ADJUSTMENT_MISMATCH_TOLERANCE'` / `... data_store ... 'atomic_write_csv'`; the splice test fails on `history_splice.ADJUSTMENT_MISMATCH_TOLERANCE`.

- [ ] **Step 3: Move the constants to their one home**

In `adjustments.py`, rename `_ADJUSTMENT_MISMATCH_TOLERANCE` -> `ADJUSTMENT_MISMATCH_TOLERANCE` and `_MIN_OVERLAP_BARS` -> `MIN_OVERLAP_BARS`, update their two uses in `adjustment_ratio`, and add `DELTA_OVERLAP_TOLERANCE = 1e-4` with a comment saying that it is the D4 delta-splice tolerance (real end-of-day closes agree exactly, so this is rounding noise), owned here and imported by `daily_delta`. In `history_splice.py`, import the two public names and use them in `_bases_agree`. In `data_refresh.py`, delete the three local constants (keep their explanatory comments, moved above the import as a short note) and import `ADJUSTMENT_MISMATCH_TOLERANCE, MIN_OVERLAP_BARS, _ADJUSTMENT_RATIO_DISPERSION` from `adjustments`. `_adjustment_ratio` keeps its body and its exact comparison (`<= ADJUSTMENT_MISMATCH_TOLERANCE`, no `+ 1e-9`): behaviour is unchanged.

- [ ] **Step 4: Add `atomic_write_csv` and route the writers through it**

In `data_store.py` (add `import contextlib` and `from uuid import uuid4`, and `from swingbot.core.infra.jsonio import _replace_with_retry`):

```python
def atomic_write_csv(df: pd.DataFrame, path: str) -> None:
    """v171 D1: the one CSV writer. A unique temp name per call (pid + uuid), so
    two writers whose lease failed open never share a temp file; os.replace
    (with jsonio's Windows retry) makes readers see the old or the new file,
    never a torn one, and invalidates load_normalized's signature memo."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{uuid4().hex}.tmp"
    try:
        df.to_csv(tmp)
        _replace_with_retry(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
```

`save_to_disk` keeps `refuse_spot_write` and calls `atomic_write_csv(df, path)` in place of `df.to_csv(path)`. `update_cache`'s warm branch replaces its three `tmp = path + ".tmp"` lines with `atomic_write_csv(merged, path)`. In `data_refresh.py`, add `atomic_write_csv` to the `from swingbot.core.marketdata.data_store import (...)` block, and `_merge_save` replaces its three temp lines with `atomic_write_csv(merged, path)`. After this step, `git grep -n '"\.tmp"' -- swingbot/core/marketdata` prints nothing.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_atomic_csv_writer.py`, then `... file tests/marketdata/test_history_splice.py`, then `... file tests/marketdata/test_data_refresh.py` (behaviour unchanged) and `... file tests/marketdata/test_spot_cache_rule.py`.
Expected: all PASS, `0 failed`.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/adjustments.py $WT/swingbot/core/marketdata/data_store.py $WT/swingbot/core/marketdata/data_refresh.py $WT/swingbot/core/marketdata/history_splice.py`
Expected: only the pre-existing `refresh_all - C (17)` and `load_normalized - C (13)` lines; nothing new.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/marketdata/adjustments.py swingbot/core/marketdata/history_splice.py swingbot/core/marketdata/data_refresh.py swingbot/core/marketdata/data_store.py tests/marketdata/test_atomic_csv_writer.py tests/marketdata/test_history_splice.py
git -C $WT commit -m "refactor(marketdata): v171 one tolerance home and one atomic unique-temp CSV writer (V171-11)"
```

### Task V171-12: D4 delta splice: sidecar meta, window rule, event trigger, overlap check, full refetch, single writer under the lease; parity fixtures (a)-(d)

**Model:** opus — data integrity and NO-LOOKAHEAD territory, a wrong splice corrupts every level

**Files:**
- Create: `swingbot/core/marketdata/daily_delta.py`
- Modify: `swingbot/core/marketdata/data_store.py` (constant `ALPACA_DAILY_DIR` beside `DATA_DIR` :43; `load_normalized` :285-343 split into `_normalize_cached` + new `load_normalized_file`)
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py` (`_bars` :101-107 gains `end=None`; new `daily_bars_between` after `daily_bars` :109-112) *(beyond the ledger, see part header)*
- Modify: `swingbot/core/marketdata/providers/router.py` (new `daily_bars_between` after `daily_bars` :348-365) *(beyond the ledger)*
- Create: `tests/marketdata/daily_fakes.py` (shared fake market, not collected)
- Create: `tests/marketdata/test_daily_delta.py`, `tests/marketdata/test_daily_delta_parity.py`
- Modify: `tests/marketdata/test_alpaca_provider.py`, `tests/marketdata/test_provider_router.py`

**Interfaces:**
- Consumes: `adjustments.MIN_OVERLAP_BARS`, `DELTA_OVERLAP_TOLERANCE`, `_ADJUSTMENT_RATIO_DISPERSION`, `merge_adjusted`; `data_store.atomic_write_csv` (V171-11), `cache_path`, `safe_symbol`, `refuse_spot_write`, `_align_tz`, `OHLCV_COLUMNS`; `jsonio.atomic_write_json`, `read_json`; `layer.lease`, `counters.count/flush/warn_fail_open`, `router.asker_scope/current_asker` (parts 1-2); `base.is_alpaca_eligible`, `SOURCE_ALPACA`, `SOURCE_YF`, `SOURCE_FALLBACK`, `NY`; `spot_metals.is_spot_metal`; `yf_safe.download`, `yf_safe.DownloadBusy`, `yf_safe.BudgetDeferred`; `config.ALPACA_ENABLED`, `DEFAULT_HISTORY_PERIOD`, `DELTA_WINDOW_MAX_DAYS`, `ALPACA_ANCHOR_DATE`.
- Produces (ledger names, plus the part-header additions):
  - `data_store.ALPACA_DAILY_DIR = os.path.join(DATA_DIR, "daily_alpaca")`; `data_store.load_normalized_file(path: str, label: str = "") -> pd.DataFrame | None` (the same normalisation and signature memo as `load_normalized`, for any path).
  - `AlpacaProvider.daily_bars_between(self, tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]` (SIP, `Adjustment.ALL`, `[start 00:00 UTC, end + 1 day 00:00 UTC]` clamped to `now - SIP_DELAY`, `to_yf_daily` frames, empty frames dropped).
  - `router.daily_bars_between(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]`: Alpaca only. Spot and non-eligible symbols are dropped, and so is everything when the provider is inactive. Calls go through `_attempt_many("daily_bars_between", batches, start, end)` with `ROWS_PER_PAGE // ((end - start).days * 252 // 365 + 10)` symbols per batch, and frames come back tagged `SOURCE_ALPACA`. There is no yfinance fallback.
  - `daily_delta`: everything in the ledger row, plus `DailyMeta.anchor_checked: str | None = None`, `write_daily(..., today: date | None = None, anchor_checked: str | None = None)`, `provider_window(tickers: list[str], start: date, end: date, basis: str) -> dict[str, pd.DataFrame]` and `provider_full(tickers: list[str], basis: str) -> dict[str, pd.DataFrame]` (the default `fetch_window`/`fetch_full`; module-level so a spawned worker can call them, V171-13), and `_today_ny() -> date` (test seam). The injected callables have exactly these two signatures.
  - Frames returned by `delta_update`/`full_refetch` are keyed by the upper-cased symbol. A delta-spliced frame has empty `attrs`, a full-refetched frame keeps its provider's `attrs["source"]`, and a yfinance fallback frame is tagged `SOURCE_FALLBACK`.

**Rules the tests pin** (D4, Global Constraints "Delta rule", part header):

| Step | Rule |
|---|---|
| cold | no CSV -> `"cold"`; no or unreadable sidecar -> `"no-meta"` (d); sidecar `basis` != file basis -> `"basis"` (e); `delta_window` None -> `"window-cap"`. Each goes straight to a full refetch on the same basis |
| window | one `fetch_window(warm, min(starts), today, basis)` per basis per call |
| anchor | symbols whose `meta.anchor_checked != today`: one `fetch_window(due, anchor_date, anchor_date + 7 days, basis)` per (basis, anchor_date). The fresh close on `anchor_date` is passed to `needs_full_refetch`. A failed anchor fetch leaves the symbol due |
| `needs_full_refetch` order | yfinance basis: any non-zero `Dividends`/`Stock Splits` row dated after `last_full_fetch` -> `"event"`; `|anchor_close / meta.anchor_close - 1| > DELTA_OVERLAP_TOLERANCE` -> `"anchor"`; fewer than `MIN_OVERLAP_BARS` common bars dated <= `last_verified` -> `"overlap-short"` (b); any common close off by more than `DELTA_OVERLAP_TOLERANCE` relative -> `"overlap-mismatch"` (c); else None |
| refusal | logged `daily delta <T> (<basis>): full refetch (<reason>)` at INFO, then a full refetch on the same basis; never `history_splice`'s live-only path |
| write | only bars dated before `today`; union via `merge_adjusted` (delta) or `_union_full` (full); `atomic_write_csv`, then the sidecar; a delta with no new closed bar writes no CSV (only the sidecar, when the anchor was checked) |
| return | persisted closed bars plus the provider frame's bars dated >= `today` (the forming bar, in memory only); never shallower than the file |
| misses | warm window miss -> cached frame unchanged; cold full miss on `alpaca-all` -> the yfinance basis for this call, tagged `yfinance-fallback`; a refused symbol's full miss -> cached frame unchanged; `BudgetDeferred` -> treated as a miss |
| spot | `XAUUSD`/`XAGUSD` are dropped before any fetch and `write_daily` raises for them |

- [ ] **Step 1: Write the shared fake market**

Create `tests/marketdata/daily_fakes.py`:

```python
"""v171 D4 test fakes: one raw series served by a fake Alpaca and a fake
yfinance, each adjusted as of the day it is asked (a dividend/split counts
only once it is published), so cache + delta can be compared with a full
fresh download on either basis."""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from swingbot.core.marketdata import daily_delta as dd

DAYS = pd.bdate_range("2026-01-02", "2026-10-16")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
PRICE = ["Open", "High", "Low", "Close"]


@dataclass
class Market:
    divs: list = field(default_factory=list)     # (ex_date "YYYY-MM-DD", amount, published date)
    splits: list = field(default_factory=list)   # (date "YYYY-MM-DD", ratio, published date)
    calls: list = field(default_factory=list)
    missing: set = field(default_factory=set)    # {(op, basis)} answered with {}

    def _raw(self) -> pd.DataFrame:
        i = np.arange(len(DAYS), dtype=float)
        close = 100.0 + 5.0 * np.sin(i / 7.0) + 0.05 * i
        return pd.DataFrame({"Open": close - 0.3, "High": close + 1.0, "Low": close - 1.0,
                             "Close": close, "Volume": 1e6 + i}, index=DAYS)

    def frame(self, basis: str, as_of: date, start: date | None = None,
              end: date | None = None) -> pd.DataFrame:
        df = self._raw()
        df = df[df.index.date <= as_of].copy()
        acts = pd.DataFrame(0.0, index=df.index, columns=["Dividends", "Stock Splits"])
        for ex, amount, pub in self.divs:
            if pub <= as_of:
                before = df.index < pd.Timestamp(ex)
                df.loc[before, PRICE] *= 1.0 - amount / df.loc[before, "Close"].iloc[-1]
                acts.loc[pd.Timestamp(ex), "Dividends"] = amount
        for d, ratio, pub in self.splits:
            if pub <= as_of:
                before = df.index < pd.Timestamp(d)
                df.loc[before, PRICE] /= ratio
                df.loc[before, "Volume"] *= ratio
                acts.loc[pd.Timestamp(d), "Stock Splits"] = ratio
        if basis == dd.BASIS_YF:
            df = df.join(acts)
        if start is not None:
            df = df[df.index.date >= start]
        if end is not None:
            df = df[df.index.date <= end]
        df.attrs["source"] = "alpaca" if basis == dd.BASIS_ALPACA else "yfinance"
        return df

    def providers(self, as_of: date):
        def window(tickers, start, end, basis):
            self.calls.append(("window", basis, start, end, tuple(tickers)))
            if ("window", basis) in self.missing:
                return {}
            return {t: self.frame(basis, as_of, start, end) for t in tickers}

        def full(tickers, basis):
            self.calls.append(("full", basis, tuple(tickers)))
            if ("full", basis) in self.missing:
                return {}
            return {t: self.frame(basis, as_of) for t in tickers}
        return window, full
```

- [ ] **Step 2: Write the failing parity tests**

Create `tests/marketdata/test_daily_delta_parity.py`:

```python
"""v171 D4 parity: cache + delta equals a full fresh download bar for bar,
Volume included, on both bases (a)-(d); and frames never cross caches."""
import dataclasses
import logging
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store
from swingbot.core.marketdata.shared.kinds import Asker
from tests.marketdata.daily_fakes import OHLCV, Market

T0, TMID, T1 = date(2026, 9, 30), date(2026, 10, 9), date(2026, 10, 16)
BASES = [dd.BASIS_ALPACA, dd.BASIS_YF]


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "ALPACA_ANCHOR_DATE", "2026-01-05")
    monkeypatch.setattr(config, "DELTA_WINDOW_MAX_DAYS", 30)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    data_store.clear_normalized_frame_cache()


def _run(monkeypatch, market, basis, as_of):
    monkeypatch.setattr(dd, "basis_for", lambda t: basis)
    window, full = market.providers(as_of)
    return dd.delta_update(["AAPL"], asker=Asker.SCAN, today=as_of,
                           fetch_window=window, fetch_full=full)["AAPL"]


def _assert_parity(market, basis, as_of, got):
    want = market.frame(basis, as_of)[OHLCV]
    pd.testing.assert_frame_equal(got[OHLCV], want, check_freq=False, check_names=False, rtol=1e-12)
    disk = dd.read_daily("AAPL", basis)
    pd.testing.assert_frame_equal(disk, want[want.index.date < as_of], check_freq=False,
                                  check_names=False, rtol=1e-12)


@pytest.mark.parametrize("basis", BASES)
def test_parity_dividend_older_than_overlap(monkeypatch, caplog, basis):
    """A 0.3% dividend, ex-date 2026-09-15, published only on 2026-10-14: the
    overlap bars after the ex-date agree exactly and the window holds no
    action, so only the anchor bar can see it."""
    m = Market(divs=[("2026-09-15", 0.30, date(2026, 10, 14))])
    _assert_parity(m, basis, T0, _run(monkeypatch, m, basis, T0))
    _assert_parity(m, basis, TMID, _run(monkeypatch, m, basis, TMID))
    assert [c[0] for c in m.calls].count("full") == 1
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (anchor)" in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_dividend_inside_window(monkeypatch, caplog, basis):
    m = Market(divs=[("2026-10-13", 0.30, date(2026, 10, 13))])
    _run(monkeypatch, m, basis, T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert ("full refetch (event)" if basis == dd.BASIS_YF else "full refetch (anchor)") in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_split(monkeypatch, caplog, basis):
    m = Market(splits=[("2026-10-08", 2.0, date(2026, 10, 8))])
    _run(monkeypatch, m, basis, T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (" in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_fewer_than_three_overlap_bars(monkeypatch, caplog, basis):
    m = Market()
    _run(monkeypatch, m, basis, T0)
    disk = dd.read_daily("AAPL", basis)
    data_store.atomic_write_csv(disk[disk.index <= "2026-09-23"], dd.cache_file("AAPL", basis))
    meta = dd.read_meta("AAPL", basis)
    dd._write_meta("AAPL", basis, dataclasses.replace(meta, anchor_checked=T1.isoformat()))
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (overlap-short)" in caplog.text
    _assert_parity(m, basis, T1, got)


def test_alpaca_frame_never_written_to_yfinance_cache(monkeypatch):
    m = Market()
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", m.frame(dd.BASIS_ALPACA, T0), basis=dd.BASIS_YF, full=True, today=T0)
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_YF))
    m.missing.add(("full", dd.BASIS_ALPACA))         # Alpaca misses the cold symbol
    got = _run(monkeypatch, m, dd.BASIS_ALPACA, T0)
    assert got.attrs["source"] == "yfinance-fallback"
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
    assert dd.read_meta("AAPL", dd.BASIS_YF).basis == dd.BASIS_YF


def test_yfinance_frame_never_written_to_alpaca_cache():
    m = Market()
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", m.frame(dd.BASIS_YF, T0), basis=dd.BASIS_ALPACA, full=True, today=T0)
    untagged = m.frame(dd.BASIS_ALPACA, T0)
    untagged.attrs = {}
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", untagged, basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
```

- [ ] **Step 3: Write the failing unit tests**

Create `tests/marketdata/test_daily_delta.py`:

```python
"""v171 D3/D4 daily_delta units: paths, sidecar, window, triggers, writer, batching."""
import contextlib
import logging
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store
from swingbot.core.marketdata.shared.kinds import Asker
from tests.marketdata.daily_fakes import Market

T0, T1 = date(2026, 9, 30), date(2026, 10, 16)


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "ALPACA_ANCHOR_DATE", "2026-01-05")
    monkeypatch.setattr(config, "DELTA_WINDOW_MAX_DAYS", 30)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    data_store.clear_normalized_frame_cache()


def _meta(**kw):
    base = dict(basis=dd.BASIS_ALPACA, last_full_fetch="2026-09-30", last_verified="2026-10-09",
                anchor_date="2026-01-05", anchor_close=100.0, anchor_checked=None)
    return dd.DailyMeta(**{**base, **kw})


def test_basis_for_routes_by_eligibility_and_the_alpaca_switch(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    assert dd.basis_for("AAPL") == dd.BASIS_ALPACA
    assert dd.basis_for("SAP.DE") == dd.BASIS_YF and dd.basis_for("^GSPC") == dd.BASIS_YF
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    assert dd.basis_for("AAPL") == dd.BASIS_YF


def test_one_file_and_one_sidecar_per_basis():
    assert dd.cache_file("aapl", dd.BASIS_ALPACA) == os.path.join("market_data", "daily_alpaca", "AAPL_daily.csv")
    assert dd.cache_file("AAPL", dd.BASIS_YF) == data_store.cache_path("AAPL", "daily")
    assert dd.meta_path("AAPL", dd.BASIS_ALPACA).endswith(os.path.join("daily_alpaca", "AAPL_daily.meta.json"))
    assert dd.meta_path("AAPL", dd.BASIS_YF).endswith(os.path.join("daily", "AAPL.meta.json"))


def test_sidecar_round_trips_and_unreadable_reads_as_none():
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) is None
    dd._write_meta("AAPL", dd.BASIS_ALPACA, _meta())
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) == _meta()
    with open(dd.meta_path("AAPL", dd.BASIS_ALPACA), "w") as f:
        f.write("{not json")
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) is None


def test_delta_window_starts_five_business_days_back_and_caps():
    assert dd.delta_window(_meta(), T1) == (date(2026, 10, 2), T1)
    assert dd.delta_window(_meta(last_verified="2026-09-10"), T1) is None   # 43 days > 30


def _bars(closes, start="2026-10-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": [1.0] * len(closes)}, index=idx)


def test_needs_full_refetch_reasons():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])      # Oct 1..9
    window = cached.iloc[1:].copy()
    meta = _meta()
    assert dd.needs_full_refetch(cached, window, meta) is None
    off = window.copy(); off.loc[off.index[0], "Close"] *= 1 + 2e-4
    assert dd.needs_full_refetch(cached, off, meta) == "overlap-mismatch"
    tiny = window.copy(); tiny.loc[tiny.index[0], "Close"] *= 1 + 5e-5
    assert dd.needs_full_refetch(cached, tiny, meta) is None
    assert dd.needs_full_refetch(cached, window.iloc[-2:], meta) == "overlap-short"
    last = window.copy(); last.loc[last.index[-1], "Close"] *= 1.05        # Oct 9 == last_verified: compared
    assert dd.needs_full_refetch(cached, last, meta) == "overlap-mismatch"
    assert dd.needs_full_refetch(cached, window, meta, anchor_close=100.02) == "anchor"
    assert dd.needs_full_refetch(cached, window, meta, anchor_close=100.005) is None


def test_bars_after_last_verified_are_never_compared():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 999.0])             # Oct 1..8, last = a legacy forming bar
    window = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    assert dd.needs_full_refetch(cached, window, _meta(last_verified="2026-10-07")) is None


def test_yfinance_actions_after_the_last_full_fetch_trigger():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    window = cached.assign(Dividends=0.0, **{"Stock Splits": 0.0})
    meta = _meta(basis=dd.BASIS_YF, last_full_fetch="2026-10-05")
    assert dd.needs_full_refetch(cached, window, meta) is None
    window.loc[pd.Timestamp("2026-10-02"), "Dividends"] = 0.3                # before last_full_fetch
    assert dd.needs_full_refetch(cached, window, meta) is None
    window.loc[pd.Timestamp("2026-10-07"), "Stock Splits"] = 2.0
    assert dd.needs_full_refetch(cached, window, meta) == "event"


def test_write_daily_persists_closed_bars_only():
    m = Market()
    out = dd.write_daily("AAPL", m.frame(dd.BASIS_ALPACA, T1), basis=dd.BASIS_ALPACA, full=True, today=T1)
    assert out.index.max() < pd.Timestamp(T1)
    assert dd.read_daily("AAPL", dd.BASIS_ALPACA).index.max() == pd.Timestamp("2026-10-15")
    meta = dd.read_meta("AAPL", dd.BASIS_ALPACA)
    assert (meta.last_full_fetch, meta.last_verified, meta.anchor_date) == ("2026-10-16", "2026-10-15", "2026-01-05")
    assert meta.anchor_close == pytest.approx(float(out.loc["2026-01-05", "Close"]))


def test_write_daily_still_writes_when_the_lease_is_not_held(monkeypatch):
    warned = []

    @contextlib.contextmanager
    def no_lease(kind, symbol, *, asker, deadline_s=30.0):
        yield False
    monkeypatch.setattr(dd.layer, "lease", no_lease)
    monkeypatch.setattr(dd.counters, "warn_fail_open", lambda op, exc: warned.append(op))
    dd.write_daily("AAPL", Market().frame(dd.BASIS_ALPACA, T0), basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA)) and warned == ["daily-write"]


def test_full_write_is_never_shallower_than_the_file():
    m = Market()
    deep = m.frame(dd.BASIS_ALPACA, T0)
    older = deep.iloc[:20].copy()
    older.index = older.index - pd.DateOffset(years=12)
    data_store.atomic_write_csv(pd.concat([older, deep])[["Open", "High", "Low", "Close", "Volume"]],
                                dd.cache_file("AAPL", dd.BASIS_ALPACA))
    fresh = Market(divs=[("2026-06-01", 0.5, T0)]).frame(dd.BASIS_ALPACA, T0)
    out = dd.write_daily("AAPL", fresh, basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert out.index[0] == older.index[0]
    ratio = fresh["Close"].iloc[0] / deep["Close"].iloc[0]
    assert out["Close"].iloc[0] == pytest.approx(older["Close"].iloc[0] * ratio, rel=1e-9)


def test_spot_metals_are_refused():
    window, full = Market().providers(T0)
    assert dd.delta_update(["XAUUSD"], asker=Asker.SCAN, today=T0, fetch_window=window, fetch_full=full) == {}
    with pytest.raises(ValueError):
        dd.write_daily("XAUUSD", Market().frame(dd.BASIS_YF, T0), basis=dd.BASIS_YF, full=True, today=T0)
    assert not os.path.exists(os.path.join("market_data", "daily", "XAUUSD.csv"))


def _warm(monkeypatch, m, symbols, as_of=T0):
    monkeypatch.setattr(dd, "basis_for", lambda t: dd.BASIS_YF if "." in t else dd.BASIS_ALPACA)
    window, full = m.providers(as_of)
    return dd.delta_update(symbols, asker=Asker.SCAN, today=as_of, fetch_window=window, fetch_full=full)


def test_one_window_call_per_basis_and_the_anchor_once_per_day(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"])
    m.calls.clear()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"], as_of=T1)
    windows = [(c[1], c[2]) for c in m.calls if c[0] == "window"]
    assert sorted(b for b, _ in windows) == sorted([dd.BASIS_ALPACA, dd.BASIS_ALPACA, dd.BASIS_YF, dd.BASIS_YF])
    assert (dd.BASIS_ALPACA, date(2026, 1, 5)) in windows                  # the batched anchor call
    m.calls.clear()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"], as_of=T1)
    assert len([c for c in m.calls if c[0] == "window"]) == 2              # anchor not due again today
    assert not [c for c in m.calls if c[0] == "full"]


def test_window_miss_serves_the_cached_frame_unchanged(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL"])
    before = os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns
    m.missing.add(("window", dd.BASIS_ALPACA))
    got = _warm(monkeypatch, m, ["AAPL"], as_of=T1)["AAPL"]
    pd.testing.assert_frame_equal(got, dd.read_daily("AAPL", dd.BASIS_ALPACA), check_freq=False)
    assert os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns == before


def test_a_second_delta_the_same_day_rewrites_nothing(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL"])
    _warm(monkeypatch, m, ["AAPL"], as_of=T1)
    before = os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns
    got = _warm(monkeypatch, m, ["AAPL"], as_of=T1)["AAPL"]
    assert os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns == before
    assert got.index[-1] == pd.Timestamp(T1) and got.attrs == {}            # forming bar in memory only


def test_full_refetch_logs_anchor_drift(monkeypatch, caplog):
    monkeypatch.setattr(dd, "basis_for", lambda t: dd.BASIS_ALPACA)
    _warm(monkeypatch, Market(), ["AAPL"])
    m = Market(divs=[("2026-09-15", 0.30, T0)])
    monkeypatch.setattr(dd, "provider_full", m.providers(T0)[1])
    monkeypatch.setattr(dd, "_today_ny", lambda: T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        out = dd.full_refetch(["AAPL"], asker=Asker.BACKGROUND)
    assert "AAPL" in out and "anchor_close" in caplog.text and "drift" in caplog.text
```

Append to `tests/marketdata/test_alpaca_provider.py`:

```python
def test_daily_bars_between_sends_the_range_on_sip_all():
    from datetime import date
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).daily_bars_between(["AAPL"], date(2026, 9, 20), date(2026, 9, 25))
    req = c.requests[0]
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    assert req.start == datetime(2026, 9, 20)
    assert req.end <= (NOW - pd.Timedelta(minutes=15)).replace(tzinfo=None)
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]
```

In `tests/marketdata/test_provider_router.py`, add to `FakeProvider`:

```python
    def daily_bars_between(self, tickers, start, end):
        self._maybe(); self.between = (list(tickers), start, end)
        return {t: _df() for t in tickers if t in self.daily}
```

and append:

```python
def test_daily_bars_between_is_alpaca_only(enabled, monkeypatch):
    from datetime import date
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    out = router.daily_bars_between(["AAPL", "SAP.DE", "XAUUSD"], date(2026, 10, 1), date(2026, 10, 16))
    assert set(out) == {"AAPL"} and out["AAPL"].attrs["source"] == "alpaca"
    assert prov.between == (["AAPL"], date(2026, 10, 1), date(2026, 10, 16))


def test_daily_bars_between_disabled_returns_nothing(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False); router.reset()
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    from datetime import date
    assert router.daily_bars_between(["AAPL"], date(2026, 10, 1), date(2026, 10, 16)) == {}
    assert prov.calls == 0
```

- [ ] **Step 4: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_daily_delta.py`, `... file tests/marketdata/test_daily_delta_parity.py`, `... file tests/marketdata/test_alpaca_provider.py`, `... file tests/marketdata/test_provider_router.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.marketdata.daily_delta'` and `AttributeError: ... 'daily_bars_between'`.

- [ ] **Step 5: Provider and router range call**

`AlpacaProvider._bars(self, tickers, timeframe, start, end=None)`: `end` defaults to `self._now() - SIP_DELAY` and is otherwise `min(end, self._now() - SIP_DELAY)`. `daily_bars_between` converts `start`/`end` to `datetime(y, m, d, tzinfo=timezone.utc)` (end + 1 day) and returns `{t: to_yf_daily(df) for t, df in raw.items() if not df.empty}`. `router.daily_bars_between` follows the Produces line, importing `ROWS_PER_PAGE` from `alpaca_provider` beside the names the router already imports.

- [ ] **Step 6: `data_store` additions**

Add `ALPACA_DAILY_DIR = os.path.join(DATA_DIR, "daily_alpaca")` after `DATA_DIR`. Move `load_normalized`'s body from `df = _normalize_columns(df)` through the dedup/empty check into `_normalize_cached(df, label) -> pd.DataFrame | None`, where `label` is `f"{ticker}/{interval}"` in the existing warnings. `load_normalized` keeps its signature check, memo, `load_from_disk` read and memo store, and calls the helper. Then add `load_normalized_file(path, label="")`: the same steps around `pd.read_csv(path, index_col=0, parse_dates=True)`, reusing `_frame_signature`, `_cached_normalized_frame` and `_remember_normalized_frame`. Both functions must end below CC 13.

- [ ] **Step 7: Implement `daily_delta.py`**

Module docstring: the D4 rules table above, the NO-LOOKAHEAD rule (nothing is placed after the provider frame's last bar, and the forming bar is never persisted), and "one writer: `write_daily`".

Module constants: `BASIS_ALPACA`, `BASIS_YF`, `_SOURCES = {BASIS_ALPACA: {SOURCE_ALPACA}, BASIS_YF: {SOURCE_YF, SOURCE_FALLBACK}}`, `_WINDOW_BDAYS = MIN_OVERLAP_BARS + 2`, `_ANCHOR_SPAN_DAYS = 7`, `_LEASE_DEADLINE_S = 10.0`, `_OHLC = ["Open", "High", "Low", "Close"]`. Import `layer` and `counters` as modules (`from swingbot.core.marketdata.shared import counters, layer`) so tests patch one place.

- `_today_ny()`: `datetime.now(NY).date()`.
- `basis_for`, `cache_file`, `meta_path`, `read_meta`, `_write_meta(ticker, basis, meta)` (`atomic_write_json(meta_path(...), dataclasses.asdict(meta))`, which uses `mkstemp`, so it is unique per write), `read_daily` (`data_store.load_normalized_file(cache_file(t, basis or basis_for(t)), label=...)`). `read_meta` returns `None` for a missing file, unreadable JSON or missing keys.
- `delta_window(meta, today)`: `start = (pd.Timestamp(meta.last_verified) - pd.offsets.BDay(_WINDOW_BDAYS)).date()`; `None` when `(today - start).days > config.DELTA_WINDOW_MAX_DAYS`; else `(start, today)`.
- `needs_full_refetch`: the order in the Rules table, each reason in its own small helper (`_action_after`, `_anchor_moved`, `_overlap_reason`).
- `_ohlcv(df)`: `df[OHLCV_COLUMNS].astype("float64")`, tz-naive `DatetimeIndex`, de-duplicated (keep last), sorted.
- `_union_full(existing, fresh)`: fresh wins on its span. Cached bars older than `fresh.index.min()` are kept and rescaled to the fresh basis when the closes on the oldest `_RESCALE_BARS = 20` common bars (the ones nearest the kept segment) prove one ratio: `r = median(fresh/cached)` with `|r - 1| > DELTA_OVERLAP_TOLERANCE` and `max|ratios/r - 1| <= _ADJUSTMENT_RATIO_DISPERSION`, then OHLC `*= r` and Volume `/= r`, the convention of `adjustments.py:66`. An unproven ratio keeps them unscaled with one WARNING naming the symbol. The result is the concat, sorted and de-duplicated.
- `write_daily(ticker, fresh, *, basis, full, today=None, anchor_checked=None)`: `refuse_spot_write`; source check -> `ValueError(f"{ticker}: a {src!r} frame cannot be written to the {basis} cache")`; `closed = _ohlcv(fresh)` restricted to dates `< today`; nothing closed and not `full` -> return `read_daily(ticker, basis)`; under `layer.lease(DataKind.DAILY_BARS, ticker, asker=Asker.BACKGROUND, deadline_s=_LEASE_DEADLINE_S)` (False -> `counters.warn_fail_open("daily-write", RuntimeError("lease not held"))` and carry on): `existing = read_daily(ticker, basis)` re-read inside the lease, `merged = _union_full(existing, closed) if full else merge_adjusted(existing, closed, ticker, "daily", data_store._align_tz)` (an empty `existing` is just `closed`), `atomic_write_csv(merged, cache_file(...))`, then `_write_meta(ticker, basis, _next_meta(read_meta(ticker, basis), merged, basis, full, today, anchor_checked))`. `_next_meta` sets `last_verified` to the newest merged bar dated before `today`. On `full` it sets `last_full_fetch = today`, `anchor_checked = today`, and `anchor_date`/`anchor_close` from the first merged bar on or after `config.ALPACA_ANCHOR_DATE`. Otherwise it carries the previous values, and `anchor_checked` becomes the argument when given.
- `provider_window` / `provider_full`: Alpaca basis -> `router.daily_bars_between(tickers, start, end)` / `router.daily_bars(tickers, config.DEFAULT_HISTORY_PERIOD, lambda ts, p: {})`, keeping only frames tagged `SOURCE_ALPACA`. yfinance basis -> one `yf_safe.download(" ".join(tickers), start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), interval="1d", group_by="ticker", auto_adjust=True, actions=True, progress=False)` / the same with `period="max"`, sliced per ticker as `data._yf_daily_batch` does (`raw[t].dropna(how="all", subset=OHLC)`), tagged `SOURCE_YF`. `BudgetDeferred` propagates, while `DownloadBusy` and any other exception give `{}` with one INFO line. Both count `counters.count(provider, DataKind.DAILY_BARS, router.current_asker(), "fetched", n=len(got))` and `"failed"` for the rest (skipped when n is 0).
- `delta_update` and `full_refetch`: the whole body runs inside `router.asker_scope(asker)` and ends with `counters.flush()`. Keep every function below CC 15 with the helper split `_plain(tickers)` (upper/strip/dedupe, spot dropped with a DEBUG line) -> `_by_basis(symbols) -> dict[str, list]` -> `_delta_basis(basis, group, today, fw, ff)` -> `_cold_reason(df, meta, basis, today)`, `_splice_warm(...)`, `_anchor_closes(basis, warm, metas, today, fw) -> dict[str, float]`, `_apply_delta(...)` (writes only when the window holds a closed bar newer than `last_verified`; otherwise writes the sidecar alone when the anchor was checked), `_full_basis(...)` (writes each fetched frame with `full=True`; a cold `alpaca-all` miss goes to `_delta_basis(BASIS_YF, missing, ...)`, re-tagged `SOURCE_FALLBACK`; a refused symbol's miss returns its cached frame), and `_with_forming(persisted, provider_frame, today)` (persisted bars before `today` plus the provider's bars on or after `today`, `attrs` cleared). `full_refetch` writes each frame with `full=True` and logs one INFO line per symbol whose `anchor_close` changed: `daily re-anchor %s (%s): anchor_close %.6f -> %.6f (drift %+.4f%%)`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_daily_delta.py`, `... file tests/marketdata/test_daily_delta_parity.py`, `... file tests/marketdata/test_alpaca_provider.py`, `... file tests/marketdata/test_provider_router.py`, `... file tests/marketdata/test_frame_equivalence.py`
Expected: all PASS, `0 failed`. If a parity case fails, fix `daily_delta`, never the fixture's expected frame. The full fresh download is the oracle (spec Success row "bar-for-bar equal, every check").

- [ ] **Step 9: Complexity and lookahead check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/daily_delta.py $WT/swingbot/core/marketdata/data_store.py $WT/swingbot/core/marketdata/providers/router.py $WT/swingbot/core/marketdata/providers/alpaca_provider.py`
Expected: no `daily_delta` line, and no new `data_store`/router/provider line. Invoke the `no-lookahead` skill on `daily_delta.py` and confirm `_with_forming` never places a bar after the provider frame's last bar.

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/marketdata/daily_delta.py swingbot/core/marketdata/data_store.py swingbot/core/marketdata/providers/alpaca_provider.py swingbot/core/marketdata/providers/router.py tests/marketdata/daily_fakes.py tests/marketdata/test_daily_delta.py tests/marketdata/test_daily_delta_parity.py tests/marketdata/test_alpaca_provider.py tests/marketdata/test_provider_router.py
git -C $WT commit -m "feat(marketdata): v171 D4 proven delta splice over two single-basis daily caches (V171-12)"
```

### Task V171-13: Scan crawl on the delta path with write-back of cold frames (flag `DAILY_DELTA_FETCH`)

**Model:** opus — the scan's daily frames, crosses `scanning` and `marketdata`

**Files:**
- Modify: `swingbot/core/scanning/fetch.py` (imports :12-22; new `_delta_provider_worker`, `_bounded_delta_call`, `_crawl_delta` after `_crawl_spot` :327-348; one branch at the top of `_crawl_latest_data` :374-459)
- Create: `tests/scanning/test_crawl_delta_path.py`

**Interfaces:**
- Consumes: `daily_delta.delta_update(tickers, *, asker, today=None, fetch_window=None, fetch_full=None)`, `provider_window(tickers, start, end, basis)`, `provider_full(tickers, basis)`, `basis_for`, `cache_file`, `_today_ny` (V171-12); `counters.snapshot_and_clear()`, `counters.merge(rows)` (V171-4); `router.asker_scope` (V171-8); `yf_safe.BudgetDeferred`; `Asker.SCAN`; `config.DAILY_DELTA_FETCH`, `BATCH_FETCH_CHUNK_SIZE`, `COLD_FETCH_TIMEOUT_SECONDS` (exist or V171-1); `tests.marketdata.daily_fakes.Market` (V171-12).
- Produces: `fetch._crawl_delta(tickers: list[str], progress=None) -> dict[str, pd.DataFrame]` (ledger), plus the worker body `fetch._delta_provider_worker(op: str, tickers: list[str], start: date | None, end: date | None, basis: str, asker_name: str) -> tuple[dict, list, float]` (frames, counter rows, in-worker seconds) and `fetch._bounded_delta_call(op, tickers, start, end, basis) -> dict[str, pd.DataFrame]`. The return shape of `_crawl_latest_data` is unchanged; `scan_run` is untouched.

How the crawl runs with the flag on (part header: provider calls in workers, splice in the scan's process):

1. `spot, plain = spot_metals.split_spot(tickers)`. Spot keeps `_crawl_spot` unchanged.
2. `plain` goes through `daily_delta.delta_update(chunk, asker=Asker.SCAN, fetch_window=fw, fetch_full=ff)` in `BATCH_FETCH_CHUNK_SIZE` chunks, checking `runstate.is_stop_requested()` between chunks the way `_fetch_cold_frames` does. `fw(ts, start, end, basis)` and `ff(ts, basis)` are closures in the parent that call `_bounded_delta_call("window" | "full", ...)`, so each provider call is one `_run_bounded` worker (label `Crawl: delta <op> (<basis>) for N ticker(s)`, timeout `COLD_FETCH_TIMEOUT_SECONDS`). A chunk costs one window call per basis, plus one anchor call per basis on the first scan of the day, plus one full call per basis only when the chunk has cold or refused symbols.
3. `_delta_provider_worker` enters `router.asker_scope(Asker[asker_name])`, calls `daily_delta.provider_window` or `provider_full`, turns `BudgetDeferred` into `{}`, and returns `(frames, counters.snapshot_and_clear(), elapsed)`. The parent merges the rows with `counters.merge` and appends `elapsed` to `_fetch_stats["cold_fetch_s"]` for `full` calls only, so the telemetry keeps its "cold fetch" meaning. A timed-out or failed worker gives `{}`, which `delta_update` treats as a miss: a warm symbol keeps its cached frame, a cold one is absent (unavailable this scan, as today).
4. A chunk whose `delta_update` raises is logged once (`log.exception`) and goes through today's `_fetch_cold_frames(chunk, progress)`. A bug in the new path therefore degrades to today's cold path, never to missing frames.
5. With the flag on, `_load_cached_daily`, `_with_cached_depth` and the `SCAN_CACHE_MAX_AGE_HOURS` staleness are not used.
6. Log line: `Crawl (delta) complete in %.1fs: %d/%d ticker(s) resolved (%d cold-fetched)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_crawl_delta_path.py`:

```python
"""v171 D3: with DAILY_DELTA_FETCH on, the crawl reads the two single-basis
caches, fetches one window per basis in bounded workers, and writes cold
frames back so the next scan is warm."""
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store
from swingbot.core.marketdata.shared import counters
from swingbot.core.scanning import engine as scan_engine, fetch
from tests.helpers import make_ohlcv
from tests.marketdata.daily_fakes import Market
from tests.scanning.conftest import _InlineProcessPool

TODAY = date(2026, 10, 16)


@pytest.fixture
def market(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key, value in {"DAILY_DELTA_FETCH": True, "MARKETDATA_LAYER": "off", "ALPACA_ENABLED": True,
                       "ALPACA_ANCHOR_DATE": "2026-01-05", "DELTA_WINDOW_MAX_DAYS": 30,
                       "BATCH_FETCH_CHUNK_SIZE": 100}.items():
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlineProcessPool)
    monkeypatch.setattr(dd, "_today_ny", lambda: TODAY)
    data_store.clear_normalized_frame_cache()
    m = Market()
    window, full = m.providers(TODAY)
    monkeypatch.setattr(dd, "provider_window", window)
    monkeypatch.setattr(dd, "provider_full", full)
    m.labels = []
    real = fetch._run_bounded

    def bounded(fn, args, timeout, label):
        m.labels.append(label)
        return real(fn, args, timeout, label)
    monkeypatch.setattr(fetch, "_run_bounded", bounded)
    return m


def _forbid(monkeypatch, *names):
    for name in names:
        monkeypatch.setattr(fetch, name, lambda *a, **k: pytest.fail(f"{name} called with the flag on"))


def test_flag_off_keeps_todays_path(monkeypatch, market):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    _forbid(monkeypatch, "_crawl_delta")
    cached = make_ohlcv([100.0, 101.0, 102.0])
    monkeypatch.setattr(fetch, "_load_cached_daily", lambda t: cached)
    assert scan_engine._crawl_latest_data(["AAPL"])["AAPL"].equals(cached)
    assert market.calls == []


def test_cold_symbols_are_full_fetched_in_workers_and_written_back(monkeypatch, market):
    _forbid(monkeypatch, "_load_cached_daily", "_with_cached_depth")
    frames = scan_engine._crawl_latest_data(["AAPL", "SAP.DE"])
    assert frames["AAPL"].attrs["source"] == "alpaca"
    assert frames["SAP.DE"].attrs["source"] == "yfinance"
    assert frames["AAPL"].index[-1] == pd.Timestamp(TODAY)              # forming bar, in memory
    assert os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
    assert os.path.exists(dd.cache_file("SAP.DE", dd.BASIS_YF))
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_YF))      # never crosses
    assert sorted(c[1] for c in market.calls if c[0] == "full") == sorted([dd.BASIS_ALPACA, dd.BASIS_YF])
    assert len(market.labels) == len(market.calls)                      # every provider call bounded
    assert all(label.startswith("Crawl: delta ") for label in market.labels)


def test_the_next_scan_is_warm_one_window_per_basis(monkeypatch, market):
    scan_engine._crawl_latest_data(["AAPL", "MSFT", "SAP.DE"])
    market.calls.clear()
    frames = scan_engine._crawl_latest_data(["AAPL", "MSFT", "SAP.DE"])
    assert sorted(c[1] for c in market.calls) == sorted([dd.BASIS_ALPACA, dd.BASIS_YF])
    assert all(c[0] == "window" for c in market.calls)
    assert all(frames[t].attrs == {} for t in ("AAPL", "MSFT", "SAP.DE"))   # counted as cache


def test_spot_symbols_keep_the_spot_crawl(monkeypatch, market):
    spot = make_ohlcv([2400.0, 2410.0])
    monkeypatch.setattr(fetch, "_crawl_spot", lambda ts, progress=None: {"XAUUSD": spot} if ts else {})
    frames = scan_engine._crawl_latest_data(["AAPL", "XAUUSD"])
    assert frames["XAUUSD"] is spot
    assert all("XAUUSD" not in c[-1] for c in market.calls)


def test_worker_counter_rows_ride_back_and_are_merged(monkeypatch, market):
    row = ("2026-10-16T14:00:00+00:00", "alpaca", "daily", "SCAN", "fetched", 1)
    merged = []
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: [row])
    monkeypatch.setattr(counters, "merge", lambda rows: merged.extend(rows))
    scan_engine._crawl_latest_data(["AAPL"])
    assert merged and all(r == row for r in merged)


def test_a_failing_delta_chunk_falls_back_to_the_cold_path(monkeypatch, market):
    monkeypatch.setattr(dd, "delta_update", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bug")))
    cold = make_ohlcv([1.0, 2.0, 3.0])
    monkeypatch.setattr(fetch, "_fetch_cold_frames", lambda ts, progress=None: [(t, cold) for t in ts])
    assert scan_engine._crawl_latest_data(["AAPL"])["AAPL"] is cold
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_crawl_delta_path.py`
Expected: FAIL. `test_flag_off_keeps_todays_path` fails with `AttributeError: ... has no attribute '_crawl_delta'` (raised by `monkeypatch.setattr`), and the others fail because the flag is ignored (`_load_cached_daily called with the flag on`).

- [ ] **Step 3: Implement**

Add to `fetch.py`'s imports: `from datetime import date`, `from swingbot.core.marketdata import daily_delta, yf_safe`, `from swingbot.core.marketdata.shared import counters` and `from swingbot.core.marketdata.shared.kinds import Asker`. Then add the three functions per the Interfaces block and steps 1-6 above. The worker imports `router` inside its body, as `_price_batch_with_sources` does. In `_crawl_latest_data`, directly after the `progress` initialisation, add:

```python
    if config.DAILY_DELTA_FETCH:
        return _crawl_delta(tickers, progress)
```

and add one sentence to its docstring: "v171: with DAILY_DELTA_FETCH on, `_crawl_delta` replaces everything below (two single-basis caches plus a batched window; cold frames written back)". `_crawl_delta` keeps `progress.done` and `progress.current_ticker` current per chunk and sets `progress.stopped` on a stop request. Frames are stored under the caller's ticker string (`delta_update` keys are upper-cased; map back with `t.upper()`).

- [ ] **Step 4: Run the tests to verify they pass, with the standing guards**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_crawl_delta_path.py`, then `... file tests/scanning/test_no_cross_ticker_mixing.py`, `... file tests/scanning/test_crawl_cache_first.py`, `... file tests/scanning/test_cold_fetch_splice.py`, `... file tests/scanning/test_scan_telemetry_sources.py`, `... file tests/scanning/test_crawl_spot.py`
Expected: all PASS, `0 failed`. The pre-v171 tests run with the flag at its default `False`.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/scanning/fetch.py`
Expected: no line for `_crawl_latest_data` (was B 9, now at most B 10), `_crawl_delta`, `_bounded_delta_call` or `_delta_provider_worker`; `_fetch_cold_frames` unchanged at 13.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/scanning/fetch.py tests/scanning/test_crawl_delta_path.py
git -C $WT commit -m "feat(scanning): v171 D3 crawl on the delta path, cold frames written back (V171-13)"
```

### Task V171-14: Plan manager daily frames from the cache plus the shared forming bar (no per-plan 2y downloads)

**Model:** opus — exit decisions on open plans, crosses `planning` and `marketdata`

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (`_daily_frame` :356-358, `_live_atr` :1400-1404, `_bars_since` :1416-1421; new `_manager_daily`, `_shared_daily` beside `_daily_frame`)
- Create: `tests/planning/test_plan_manager_cached_frames.py`

**Interfaces:**
- Consumes: `daily_delta.delta_update(tickers, *, asker, ...)`, `daily_delta.read_daily(ticker, basis=None)` (V171-12); `Asker.STOP_MONITOR`; `config.DAILY_DELTA_FETCH`.
- Produces:
  - `plan_manager._manager_daily(ticker: str) -> pd.DataFrame`: the one daily-frame source for `_daily_frame`, `_live_atr` and `_bars_since`. Flag off -> `data.get_daily_data(ticker)` exactly as today (2y, raises on no data). Flag on -> `_shared_daily(ticker)`, and today's `get_daily_data(ticker)` when that is `None` (spot metals, a provider miss on a cold symbol, any error).
  - `plan_manager._shared_daily(ticker: str) -> pd.DataFrame | None`: memo `_SHARED_DAILY: dict[str, tuple[float, pd.DataFrame]]` under `_SHARED_DAILY_LOCK`, TTL `_SHARED_DAILY_TTL_S = 60.0` on `_clock = time.monotonic` (test seam). A fresh memo entry returns a copy. Otherwise it makes one `daily_delta.delta_update([ticker], asker=Asker.STOP_MONITOR)` (closed bars from the cache plus the refreshed forming bar, the same basis and frame the scan used, so ATR and bars-since match the scan's), memoises it and returns a copy. If `delta_update` raises, it logs at DEBUG and returns `daily_delta.read_daily(ticker)`, unmemoised. At most one provider window call per ticker per 60 s tick, whichever of the three helpers asks first.
  - `PlanManager.__init__` and `_manager()` are unchanged: they still inject `_daily_frame`, `_live_atr`, `_bars_since`.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_cached_frames.py`:

```python
"""v171 D3/D8: the plan manager's daily frames come from the shared cache plus
one forming-bar refresh per ticker per 60 s tick, not per-plan 2y downloads."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta, data
from swingbot.core.marketdata.shared.kinds import Asker
from swingbot.core.planning import plan_manager as pm
from tests.helpers import make_ohlcv


@pytest.fixture
def calls(monkeypatch):
    rec = {"delta": [], "legacy": []}
    frame = make_ohlcv([100.0 + i for i in range(40)], start="2026-08-20")

    def delta(tickers, *, asker, **kw):
        rec["delta"].append((list(tickers), asker))
        return {t.upper(): frame.copy() for t in tickers if t != "XAUUSD"}

    def legacy(ticker, period="2y"):
        rec["legacy"].append(ticker)
        return frame.copy()
    monkeypatch.setattr(daily_delta, "delta_update", delta)
    monkeypatch.setattr(data, "get_daily_data", legacy)
    monkeypatch.setattr(pm, "_SHARED_DAILY", {})
    rec["now"] = [1000.0]
    monkeypatch.setattr(pm, "_clock", lambda: rec["now"][0])
    rec["frame"] = frame
    return rec


def test_flag_off_keeps_the_per_call_download(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    pm._daily_frame("AAPL"); pm._live_atr("AAPL"); pm._bars_since("AAPL", "2026-09-01T14:00:00+00:00")
    assert calls["legacy"] == ["AAPL", "AAPL", "AAPL"] and calls["delta"] == []


def test_one_refresh_per_ticker_per_tick_serves_all_three_helpers(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    df = pm._daily_frame("AAPL")
    atr = pm._live_atr("AAPL")
    bars = pm._bars_since("AAPL", "2026-09-01T14:00:00+00:00")
    assert calls["delta"] == [(["AAPL"], Asker.STOP_MONITOR)] and calls["legacy"] == []
    assert df.equals(calls["frame"]) and atr > 0
    assert bars == int((calls["frame"].index > pd.Timestamp("2026-09-01 10:00")).sum())
    calls["now"][0] += 61.0
    pm._daily_frame("AAPL")
    assert len(calls["delta"]) == 2                                       # next tick refreshes


def test_the_memo_hands_out_copies(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    pm._daily_frame("AAPL")["Close"] = 0.0
    assert pm._daily_frame("AAPL")["Close"].iloc[-1] == calls["frame"]["Close"].iloc[-1]


def test_spot_and_misses_fall_back_to_todays_download(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    pm._daily_frame("XAUUSD")
    assert calls["legacy"] == ["XAUUSD"]


def test_a_delta_error_reads_the_cache_without_memoising(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    monkeypatch.setattr(daily_delta, "delta_update", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    cached = make_ohlcv([5.0, 6.0, 7.0])
    monkeypatch.setattr(daily_delta, "read_daily", lambda t, basis=None: cached)
    assert pm._daily_frame("AAPL").equals(cached) and pm._SHARED_DAILY == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_manager_cached_frames.py`
Expected: FAIL with `AttributeError: <module 'swingbot.core.planning.plan_manager'> has no attribute '_SHARED_DAILY'` (from `monkeypatch.setattr`).

- [ ] **Step 3: Implement**

In `plan_manager.py`, add module state beside `_daily_frame`: `_SHARED_DAILY: dict = {}`, `_SHARED_DAILY_LOCK = threading.Lock()`, `_SHARED_DAILY_TTL_S = 60.0`, `_clock = time.monotonic` (add `import threading`/`import time` if missing). Then add `_manager_daily` and `_shared_daily` per the Interfaces block. Import `daily_delta`, `data` and `Asker` inside the functions, the way the three helpers import `get_daily_data` today, and call `data.get_daily_data` through the module attribute so tests patch one place. Re-point the helpers:

```python
def _daily_frame(ticker):
    return _manager_daily(ticker)
```

`_live_atr` computes `atr(_manager_daily(ticker), 14)`, and `_bars_since` takes `_manager_daily(ticker).index`. The rest of each body is unchanged. Hold the lock only around memo reads and writes, never around the provider call. Two concurrent first askers may then both refresh; that is harmless, because `write_daily` is safe under the lease.

- [ ] **Step 4: Run the tests to verify they pass, with the manager's suites**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_plan_manager_cached_frames.py`, then `... file tests/planning/test_plan_manager_active.py`, `... file tests/planning/test_plan_manager_shared_quote.py` (V171-10)
Expected: all PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/planning/plan_manager.py`
Expected: the pre-existing lines only (`poll` C 20, `_step_active` D 21, `_on_event` C 15, plus anything V171-10 already left); no line for `_manager_daily` or `_shared_daily`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_cached_frames.py
git -C $WT commit -m "feat(planning): v171 D8 plan manager frames from the shared daily cache (V171-14)"
```

### Task V171-15: Weekly full re-anchor bot loop (outside session)

**Model:** sonnet — one loop task in the established weekly pattern

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (module date beside `_earnings_refresh_fired_date` :690; new `daily_reanchor` and `_run_reanchor` after `weekly_earnings_refresh` :882-904; `_always_on_loops` :1043-1047)
- Create: `tests/commands/test_daily_reanchor_loop.py`

**Interfaces:**
- Consumes: `daily_delta.full_refetch(tickers, *, asker) -> dict` (V171-12; it writes each symbol on its own basis, `daily_alpaca` from Alpaca and `market_data/daily` from yfinance, and logs per-symbol `anchor_close` drift); `spot_metals.cache_symbols` (exists: XAUUSD -> GC=F, never the spot name); `_scheduled_job_already_fired` / `_mark_scheduled_job_fired` (exist); `config.DAILY_DELTA_FETCH`, `REANCHOR_WEEKDAY` (6 = Sunday), `REANCHOR_HOUR` (4, Berlin) (V171-1).
- Produces: `loops.daily_reanchor` (`@tasks.loop(minutes=1)`, job name `"daily_reanchor"`), a member of `_always_on_loops()` (appended last, so V171-28's later append still holds); `loops._run_reanchor() -> None` (async); `_REANCHOR_CHUNK = 30` and `_REANCHOR_PAUSE_S = 10.0`. A 10y Alpaca request carries 3 symbols, so 30 symbols are 10 requests; the pause keeps one chunk per 10 s, inside the 150/min Alpaca budget at tier 4's 25 % reserve.

Behaviour: no-op when `DAILY_DELTA_FETCH` is off. It fires in the first tick of hour `REANCHOR_HOUR` on weekday `REANCHOR_WEEKDAY` (Berlin, `SESSION_TZ`); any minute of that hour counts, so a restart at 04:07 still runs. It runs once per date, with the module date plus the Postgres `scheduled_jobs` marker set **before** the work (the `weekly_earnings_refresh` pattern). Each chunk runs through `await asyncio.to_thread(daily_delta.full_refetch, chunk, asker=Asker.BACKGROUND)` inside `try/except: log.exception`, so one failed chunk never stops the rest. It ends with `log.info("daily_reanchor: re-anchored %d/%d symbol(s)", done, total)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_daily_reanchor_loop.py`:

```python
"""v171 D4 backstop: the weekly full re-anchor, once per Sunday 04:00 Berlin."""
import asyncio
import datetime as dt

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.marketdata import daily_delta
from swingbot.core.marketdata.shared.kinds import Asker

JOB = "daily_reanchor"
SUNDAY = dt.date(2026, 10, 18)


def _tick(monkeypatch, when):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    asyncio.run(loops_mod.daily_reanchor.coro())


@pytest.fixture
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    monkeypatch.setattr(config, "REANCHOR_WEEKDAY", 6)
    monkeypatch.setattr(config, "REANCHOR_HOUR", 4)
    monkeypatch.setattr(loops_mod, "_reanchor_fired_date", None)
    monkeypatch.setattr(loops_mod, "_REANCHOR_PAUSE_S", 0.0)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL", "SAP.DE", "XAUUSD"])

    def refetch(tickers, *, asker):
        got.append((list(tickers), asker))
        return {t: None for t in tickers}
    monkeypatch.setattr(daily_delta, "full_refetch", refetch)
    return got


def test_fires_once_in_the_slot_with_spot_mapped_to_its_future(monkeypatch, calls):
    _tick(monkeypatch, dt.datetime(2026, 10, 18, 3, 59))
    assert calls == []
    _tick(monkeypatch, dt.datetime(2026, 10, 18, 4, 7))
    monkeypatch.setattr(loops_mod, "_reanchor_fired_date", None)      # simulated restart
    _tick(monkeypatch, dt.datetime(2026, 10, 18, 4, 30))
    assert len(calls) == 1
    symbols, asker = calls[0]
    assert sorted(symbols) == ["AAPL", "GC=F", "SAP.DE"] and asker is Asker.BACKGROUND
    assert scheduled_repo().fired_on(JOB) == SUNDAY.isoformat()


def test_other_days_and_the_flag_off_do_nothing(monkeypatch, calls):
    _tick(monkeypatch, dt.datetime(2026, 10, 17, 4, 0))                 # Saturday
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    _tick(monkeypatch, dt.datetime(2026, 10, 18, 4, 0))
    assert calls == []


def test_the_watchlist_is_re_anchored_in_chunks_of_thirty(monkeypatch, calls):
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: [f"T{i:02d}" for i in range(65)])
    _tick(monkeypatch, dt.datetime(2026, 10, 25, 4, 0))                 # its own Sunday: markers persist
    assert [len(c[0]) for c in calls] == [30, 30, 5]


def test_a_failing_chunk_does_not_stop_the_rest(monkeypatch, calls):
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: [f"T{i:02d}" for i in range(65)])
    seen = []

    def flaky(tickers, *, asker):
        seen.append(len(tickers))
        if len(seen) == 1:
            raise RuntimeError("provider down")
        return {}
    monkeypatch.setattr(daily_delta, "full_refetch", flaky)
    _tick(monkeypatch, dt.datetime(2026, 11, 1, 4, 0))
    assert seen == [30, 30, 5]


def test_registered_as_an_always_on_loop():
    loops = loops_mod._always_on_loops()
    assert loops_mod.daily_reanchor in loops and loops[-1] is loops_mod.daily_reanchor
```

(If V171-28 has already landed and appended `tape_feed`, the last assertion becomes `loops.index(loops_mod.daily_reanchor) < loops.index(loops_mod.tape_feed)`; part 5 owns that edit.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_daily_reanchor_loop.py`
Expected: FAIL with `AttributeError: module 'swingbot.commands.scanning.loops' has no attribute '_reanchor_fired_date'` (from `monkeypatch.setattr`) and `... 'daily_reanchor'`.

- [ ] **Step 3: Implement**

Add `_reanchor_fired_date: dt.date | None = None` beside the other `_*_fired_date` globals, plus the two constants. Then add `daily_reanchor` after `weekly_earnings_refresh` per the Behaviour paragraph: the gate order is flag, weekday/hour, fired check, mark, then `await _run_reanchor()`. Write `_run_reanchor()` with the chunk loop (`await asyncio.sleep(_REANCHOR_PAUSE_S)` between chunks, none after the last). Import `daily_delta`, `spot_metals` and `Asker` inside it and call `daily_delta.full_refetch` through the module attribute. Append `daily_reanchor` to the tuple `_always_on_loops()` returns. The docstring says why the loop exists: it is the D4 backstop for an adjustment the daily anchor somehow missed, run outside session on the VM, and it stays after the per-part flags are removed (spec Rollout).

- [ ] **Step 4: Run the tests to verify they pass, with the loop suites**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_daily_reanchor_loop.py`, then `... file tests/commands/test_scheduled_jobs.py`, `... file tests/commands/test_market_data_refresh_task.py`, `... file tests/commands/test_trade_monitor_shared_quote.py` (V171-10, same module)
Expected: all PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/scanning/loops.py`
Expected: only the pre-existing `_session_scan_tick - C (15)` line (plus whatever V171-10 left, unchanged); no line for `daily_reanchor` or `_run_reanchor`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/scanning/loops.py tests/commands/test_daily_reanchor_loop.py
git -C $WT commit -m "feat(loops): v171 D4 weekly full re-anchor of both daily caches (V171-15)"
```

### Task V171-16: `refresh_all` batches symbols per timeframe (yfinance multi-ticker download; Alpaca for the timeframes it serves)

**Model:** sonnet — one module, legacy CC 17 function gains logic only via helpers

**Files:**
- Modify: `swingbot/core/marketdata/data_refresh.py` (`refresh_symbol` :254-322 warm tail extracted; new helpers after `_record`; `refresh_all` :369-430, three lines)
- Create: `tests/marketdata/test_refresh_all_batched.py`

**Interfaces:**
- Consumes: `_merge_save` (writes through `atomic_write_csv`, V171-11), `is_stale`, `load_from_disk`, `cache_path`, `timeframe_name`, `yf_interval` (exist); `yf_safe.download`, `yf_safe.BudgetDeferred`; `router.asker_scope`, `Asker.BACKGROUND` (V171-8, V171-2); `config.MARKETDATA_LAYER`, `BATCH_FETCH_CHUNK_SIZE`.
- Produces:
  - `data_refresh._refresh_timeframe_batch(symbols: list[str], timeframe: str, base_dir: str, *, state, force: bool) -> dict[str, dict]` (ledger). Only **warm, stale** pairs are batched: a CSV exists, `is_stale(symbol, tf, base_dir, state=state)` holds, and `force` is False. They get one `yf_safe.download(" ".join(symbols), start=<the oldest last-bar date in the chunk, "YYYY-MM-DD">, interval=yf_interval(tf), group_by="ticker", auto_adjust=True, progress=False)`. Each symbol's slice is cut to bars dated on or after its **own** last cached bar's date, so its merge sees exactly the overlap `refresh_symbol`'s `start=last` fetch gives today. Each result dict has the same shape as `refresh_symbol`'s (`symbol`, `timeframe`, `rows`, `added`, `status`), plus `"batched": True`. Behaviour on failure: a whole-batch exception -> `{}` (those pairs then take `refresh_symbol` as today); `BudgetDeferred` -> every pair `status "failed"`, `error "budget-deferred"`, with no per-symbol retry, so a short budget is not spent N times over; an empty slice -> `"fresh"` plus `os.utime`, exactly like `refresh_symbol`'s empty warm fetch.
  - `data_refresh._apply_incremental(symbol: str, tf: str, base_dir: str, existing, fresh, out: dict) -> dict`: `refresh_symbol`'s warm tail after the fetch (empty -> utime + `"fresh"`; `_merge_save`; `added == 0` -> utime + `"fresh"`; else `"incremental"`), shared by both paths so they cannot drift.
  - `data_refresh._prefetch(symbols, tf, base_dir, *, state, force, started: float, deadline_seconds) -> dict[str, dict]`: `{}` when `MARKETDATA_LAYER == "off"` or `force`. Otherwise it first keeps only the pairs `_refresh_timeframe_batch` would batch (a CSV exists and `is_stale` holds: an mtime check, no CSV read), so every chunk is full. It then chunks those by `BATCH_FETCH_CHUNK_SIZE` inside `router.asker_scope(Asker.BACKGROUND)` and stops starting chunks once the deadline has passed.
  - `data_refresh._refresh_one(prefetched, symbol, tf, base_dir, force, state) -> dict` (the batched result, else `refresh_symbol(...)`) and `data_refresh._pause(r: dict, seconds: float) -> None` (sleeps unless `r.get("batched")`: per-symbol pacing is pointless for a pair that cost no request of its own).
- **No Alpaca leg** (part header): every file `refresh_all` writes is yfinance-basis, so Alpaca serves none of them. The Alpaca-basis daily file is kept current by V171-13 and V171-15.

`refresh_all` changes by exactly three lines and keeps CC 17. Inside `for tf in timeframes:`, after the `deadline_hit` check, it adds `prefetched = _prefetch(symbols, tf, base_dir, state=state, force=force, started=started, deadline_seconds=deadline_seconds)`. The `refresh_symbol(...)` call becomes `_refresh_one(prefetched, symbol, tf, base_dir, force, state)`, and `time.sleep(sleep_seconds)` becomes `_pause(r, sleep_seconds)`. `MARKETDATA_LAYER == "off"` therefore restores today's per-symbol path exactly.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_refresh_all_batched.py`:

```python
"""v171 D8: refresh_all batches stale warm symbols per timeframe chunk; layer
off, force and cold symbols keep today's per-symbol path."""
import os
import time

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data_refresh as rf, data_store, yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker


def _frame(start, periods):
    idx = pd.bdate_range(start, periods=periods)
    v = 100.0 + np.arange(periods, dtype=float)
    return pd.DataFrame({"Open": v, "High": v + 1, "Low": v - 1, "Close": v, "Volume": 1e6}, index=idx)


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 2)
    for s in ("AAA", "BBB", "CCC"):
        data_store.save_to_disk(_frame("2026-09-01", 20), s, "daily", base_dir=str(tmp_path))
        old = time.time() - 13 * 3600
        os.utime(data_store.cache_path(s, "daily", base_dir=str(tmp_path)), (old, old))
    return str(tmp_path)


@pytest.fixture
def downloads(monkeypatch):
    calls = []
    fresh = _frame("2026-09-28", 3)                     # Sep 28 (= last cached bar), 29, 30

    def download(tickers, **kw):
        syms = tickers.split()
        calls.append((syms, kw, router.current_asker()))
        return pd.concat({s: fresh for s in syms}, axis=1)
    monkeypatch.setattr(yf_safe, "download", download)
    return calls


@pytest.fixture
def per_symbol(monkeypatch):
    calls = []

    def fake(symbol, timeframe, base_dir=None, force=False, state=None):
        calls.append(symbol)
        return {"symbol": symbol, "timeframe": "daily", "rows": 0, "added": 0, "status": "fresh"}
    monkeypatch.setattr(rf, "refresh_symbol", fake)
    return calls


def _run(base, symbols=("AAA", "BBB", "CCC"), **kw):
    return rf.refresh_all(list(symbols), ["daily"], base_dir=base, state={}, persist_state=False, **kw)


def test_one_download_per_chunk_with_refresh_symbol_shaped_results(base, downloads, per_symbol):
    out = _run(base)
    assert [c[0] for c in downloads] == [["AAA", "BBB"], ["CCC"]] and per_symbol == []
    kw = downloads[0][1]
    assert (kw["start"], kw["interval"], kw["group_by"], kw["auto_adjust"]) == ("2026-09-28", "1d", "ticker", True)
    assert out["summary"]["daily"]["incremental"] == 3 and out["summary"]["daily"]["added"] == 6
    assert len(data_store.load_from_disk("AAA", "daily", base_dir=base)) == 22


def test_layer_off_keeps_the_per_symbol_path(monkeypatch, base, downloads, per_symbol):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    _run(base)
    assert per_symbol == ["AAA", "BBB", "CCC"] and downloads == []


def test_force_and_cold_symbols_take_the_per_symbol_path(base, downloads, per_symbol):
    _run(base, symbols=("AAA", "DDD"))
    assert per_symbol == ["DDD"]
    per_symbol.clear()
    _run(base, force=True)
    assert per_symbol == ["AAA", "BBB", "CCC"]


def test_a_failed_batch_falls_back_per_symbol(monkeypatch, base, per_symbol):
    monkeypatch.setattr(yf_safe, "download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    _run(base)
    assert per_symbol == ["AAA", "BBB", "CCC"]


def test_budget_deferred_fails_the_chunk_without_per_symbol_retries(monkeypatch, base, per_symbol):
    def deferred(*a, **k):
        raise yf_safe.BudgetDeferred("tier 4")
    monkeypatch.setattr(yf_safe, "download", deferred)
    out = _run(base)
    assert per_symbol == []
    assert out["summary"]["daily"]["failed"] == 3
    assert {e for _, _, e in out["failures"]} == {"budget-deferred"}


def test_batched_pairs_are_not_paced_and_run_at_background_tier(monkeypatch, base, downloads, per_symbol):
    slept = []
    monkeypatch.setattr(rf.time, "sleep", lambda s: slept.append(s))
    _run(base, sleep_seconds=5.0)
    assert slept == [] and {c[2] for c in downloads} == {Asker.BACKGROUND}


def test_a_pair_inside_its_window_is_not_batched(base, downloads, per_symbol):
    now = time.time()
    os.utime(data_store.cache_path("BBB", "daily", base_dir=base), (now, now))
    _run(base)
    assert [c[0] for c in downloads] == [["AAA", "CCC"]] and per_symbol == ["BBB"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_refresh_all_batched.py`
Expected: FAIL. `test_one_download_per_chunk...` fails on `per_symbol == []` (today every pair goes through `refresh_symbol`), and the budget test fails on its `failed == 3`.

- [ ] **Step 3: Implement**

Extract `_apply_incremental` from `refresh_symbol`'s warm tail and make `refresh_symbol` call it (behaviour unchanged; its CC falls). Then add `_refresh_timeframe_batch`, `_prefetch`, `_refresh_one` and `_pause` per the Interfaces block. The per-symbol slice is `raw[symbol].dropna(how="all")` under a `KeyError` guard, then the rows whose `str(index)[:10]` is on or after `str(existing.index.max())[:10]`; the date-string comparison is deliberate, because cached intraday indexes may be tz-aware, naive or object. Last, make the three edits to `refresh_all`. `data_refresh` imports `router` and `Asker` at module level, and `yf_safe` as a module (`from swingbot.core.marketdata import spot_metals, yf_safe`), so the tests' patch of `yf_safe.download` reaches it.

- [ ] **Step 4: Run the tests to verify they pass, with the refresh suites**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_refresh_all_batched.py`, then `... file tests/marketdata/test_data_refresh.py`, `... file tests/marketdata/test_market_data_state_db.py`, `... file tests/commands/test_market_data_refresh_task.py`
Expected: all PASS, `0 failed`.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/data_refresh.py`
Expected: exactly one line, `refresh_all - C (17)` (unchanged); `refresh_symbol` below 12; no line for the new helpers.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/marketdata/data_refresh.py tests/marketdata/test_refresh_all_batched.py
git -C $WT commit -m "perf(marketdata): v171 D8 refresh_all batches stale symbols per timeframe chunk (V171-16)"
```
