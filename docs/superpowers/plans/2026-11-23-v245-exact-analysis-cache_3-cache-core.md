# v245 — Exact analysis caching — Part 3: cache core, trendline prefix split, live wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-8" -A 500 <this file>`).

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and Decisions 3–6 (one `now` per scan, the trendline window, the fingerprint, the reload hook) live there.

**Only executed when V245-6 recorded `MISSED`** (spec § Exact prefix caching).
If the spec's `## Results` says the exit criterion was met, stop: this part
and the ones after it are not built.

This part covers spec § Exact prefix caching (storage, key, invalidation,
the trendline unit, call sites). V245-7 and V245-8 may run in parallel
(disjoint files, the split does not use the cache); V245-9 needs both.
Every task keeps V245-1b's golden
(`tests/scanning/test_v245_scan_one_golden.py`) byte-identical: a task that
needs it regenerated has changed behaviour — stop and report.

Code this part builds on, already on `main` from Part 2:
- V245-4 gave `trendlines._find_best_trendline(df, current_price, side, *, all_pivots=None)`,
  `_trimmed_zigzag(df)`, `_volume_average`, `_zigzag_or_empty`, `_pivot_ratio`,
  `_shift_to_full_frame(best, trim_start)`, and `custom_scanner_levels` computes
  `shared = _trimmed_zigzag(df)` once for both sides.
- V245-5 decorated `_scan_one` with `@frame_memo.with_ticker_memo`; the memo
  is untouched here.

If V245-3's doc ranked V245-4/V245-5 differently and those shapes are not
on `main`, run `git grep -n "_trimmed_zigzag\|_shift_to_full_frame" swingbot/core/market/trendlines.py`
first: V245-8 then adds the two helpers itself, verbatim from Part 2's
V245-4 Step 4, as its first step.

# Phase B — Exact prefix cache

### Task V245-7: `StructureCache`, config fields and reload clear/resize

**Model:** sonnet — a self-contained module with a lock and an LRU plus two config fields, fully specified here; no analysis code is touched.

Spec § Exact prefix caching → Storage, Cache key and invalidation; index
Decisions 5–6. Nothing calls the cache yet (V245-9 wires it), so alerts
cannot change in this task.

**Config reaches the bot by three paths**, and each must clear the cache:
SIGHUP (`_reload_callbacks`), the 30 s `config_watcher` loop (`loops.py:393`,
calls `_apply_scan_interval_change(changed)` directly) and
`scan_run._reload_config_before_scan` (`scan_run.py:338`, no callback). The
first two call `_apply_structure_cache_change`; the third is caught because
`config.reload()` bumps `store_generation` `"settings"` on every change
(`config.py:1971`) and `cache_for_mode`, called once per scan, clears on a
moved generation.

**Files:**
- Create: `swingbot/core/scanning/structure.py`
- Modify: `swingbot/config.py` (two `Field`s after `SCAN_WORKERS`, ~1246; `_MODE_VALUES`, ~1780)
- Modify: `swingbot/commands/scanning/loops.py` (callback after `_apply_scan_interval_change`, ~1401; one call in `config_watcher`, ~412; one import)
- Modify: `.env.example` (after `SCAN_WORKERS=1`, ~679)
- Create: `tests/scanning/test_structure_cache.py`

**Interfaces:**
- Consumes: `store_generation.generation("settings")` (`swingbot/core/infra/store_generation.py`, a leaf module); `bot_core.on_config_reload`; V245-3 doc `## Cache size` (the default entry count).
- Produces (ledger row V245-7, code in Step 3): `StructureCache` (`get`, `put`, `get_or_build(key, build, *, ticker="")`, `clear`, `resize`, `stats()` with `cache_hits, cache_misses, cache_evictions, cache_entries`, `prefix_build_s`, `reset_counters`, plus `max_entries` and `sync_config(generation, max_entries)`); `STRUCTURE_CACHE`; `prefix_fingerprint(frame, m) -> tuple`; `analysis_cache_mode() -> str`; `cache_for_mode(mode) -> StructureCache | None`; `apply_config_change(changed: dict)`; `config.ANALYSIS_CACHE: str`, `config.STRUCTURE_CACHE_MAX: int`; `loops._apply_structure_cache_change(changed: dict)`.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_structure_cache.py`:

```python
"""v245 V245-7: the analysis prefix cache, its key and its invalidation."""
import logging
import threading

import pandas as pd
import pytest

from swingbot import bot_core, config
from swingbot.core.infra import store_generation
from swingbot.core.scanning import structure
from swingbot.core.scanning.structure import StructureCache, prefix_fingerprint


def _frame(n: int = 40, start: str = "2024-01-02") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    close = pd.Series([100.0 + i for i in range(n)], index=idx)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": 1_000_000.0}, index=idx)


@pytest.fixture
def fresh(monkeypatch):
    cache = StructureCache(3)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", cache)
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 3, raising=False)
    return cache


# --- key -------------------------------------------------------------------

def test_fingerprint_ignores_rows_after_the_prefix():
    df = _frame()
    moved = df.copy()
    moved.iloc[-1, moved.columns.get_loc("Close")] += 5.0     # the forming bar moves
    assert prefix_fingerprint(df, 39) == prefix_fingerprint(moved, 39)


@pytest.mark.parametrize("change", ["new_bar", "restated_history", "revised_volume", "trim_start"])
def test_fingerprint_changes_with_the_prefix(change):
    df = _frame(41)
    base = prefix_fingerprint(df.iloc[:40], 39)
    if change == "new_bar":
        other = prefix_fingerprint(df, 40)
    elif change == "restated_history":                       # a split adjusts the whole series
        other = prefix_fingerprint(df.iloc[:40] * 0.5, 39)
    elif change == "revised_volume":
        revised = df.iloc[:40].copy()
        revised.iloc[38, revised.columns.get_loc("Volume")] = 1_234_567.0
        other = prefix_fingerprint(revised, 39)
    else:                                                    # the 1500-bar trim moved one session
        other = prefix_fingerprint(df.iloc[1:41], 39)
    assert other != base


def test_fingerprint_of_an_empty_prefix():
    assert prefix_fingerprint(_frame(), 0) == (0,)


def test_fingerprint_without_volume_column():
    fp = prefix_fingerprint(_frame().drop(columns=["Volume"]), 10)
    assert fp[0] == 10 and fp[-1] is None


# --- cache -----------------------------------------------------------------

def test_hit_on_the_same_key_and_miss_counts():
    cache = StructureCache(4)
    key = ("AAA", "trendline:support", (1,))
    assert cache.get(key) is None
    cache.put(key, ("value",))
    assert cache.get(key) == ("value",)
    assert cache.stats() == {"cache_hits": 1, "cache_misses": 1, "cache_evictions": 0, "cache_entries": 1}


def test_miss_on_a_changed_fingerprint_and_on_an_absent_horizon():
    cache = StructureCache(4)
    cache.put(("AAA", "unit:4w", (1,)), "4w")
    assert cache.get(("AAA", "unit:4w", (2,))) is None       # new prefix
    assert cache.get(("AAA", "unit:2w", (1,))) is None       # horizon not in the entry
    assert cache.get(("BBB", "unit:4w", (1,))) is None       # other ticker


def test_lru_eviction_drops_the_least_recently_used():
    cache = StructureCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")                                            # a is now most recent
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3
    assert cache.stats()["cache_evictions"] == 1


def test_none_is_never_stored():
    cache = StructureCache(2)
    cache.put("a", None)
    assert cache.stats()["cache_entries"] == 0


def test_get_or_build_builds_once_then_hits():
    cache = StructureCache(2)
    calls = []

    def build():
        calls.append(1)
        return ("built",)

    assert cache.get_or_build("k", build, ticker="AAA") == ("built",)
    assert cache.get_or_build("k", build, ticker="AAA") == ("built",)
    assert len(calls) == 1
    assert cache.prefix_build_s >= 0.0


def test_build_failure_warns_with_the_ticker_and_stores_nothing(caplog):
    cache = StructureCache(2)

    def boom():
        raise ValueError("bad frame")

    with caplog.at_level(logging.WARNING, logger=structure.__name__):
        assert cache.get_or_build(("AAA", "trendline:support", (1,)), boom, ticker="AAA") is None
    assert "AAA" in caplog.text and "trendline:support" in caplog.text
    assert cache.stats()["cache_entries"] == 0


def test_clear_resize_and_reset_counters():
    cache = StructureCache(5)
    for k in "abcde":
        cache.put(k, k)
    cache.resize(2)
    assert cache.stats()["cache_entries"] == 2 and cache.max_entries == 2
    assert cache.get("e") == "e" and cache.get("a") is None
    cache.clear()
    assert cache.stats()["cache_entries"] == 0
    cache.reset_counters()
    assert cache.stats() == {"cache_hits": 0, "cache_misses": 0, "cache_evictions": 0, "cache_entries": 0}
    assert cache.prefix_build_s == 0.0


def test_concurrent_get_and_put_from_two_threads():
    cache = StructureCache(50)
    errors = []

    def worker(offset):
        try:
            for i in range(2000):
                key = (offset + i) % 120
                cache.put(key, (key,))
                value = cache.get(key)
                assert value is None or value == (key,)
        except Exception as exc:          # surfaced below; a thread cannot fail the test itself
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n * 7,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stats = cache.stats()
    assert not errors
    assert stats["cache_entries"] <= 50
    assert stats["cache_hits"] + stats["cache_misses"] == 4000


# --- mode, config, reload ---------------------------------------------------

def test_cache_for_mode(fresh):
    assert structure.cache_for_mode("off") is None
    assert structure.cache_for_mode("shadow") is fresh
    assert structure.cache_for_mode("on") is fresh


def test_config_fields_parse_and_fall_back():
    fields = {f.attr: f for f in config.FIELDS}
    assert config._cast(fields["ANALYSIS_CACHE"], "ON") == "on"
    assert config._cast(fields["ANALYSIS_CACHE"], "bogus") == "off"
    assert fields["ANALYSIS_CACHE"].default == "off"
    assert isinstance(config._cast(fields["STRUCTURE_CACHE_MAX"], "250"), int)
    assert fields["ANALYSIS_CACHE"].hot_reloadable and fields["STRUCTURE_CACHE_MAX"].hot_reloadable


def test_a_moved_settings_generation_clears_on_the_next_scan(fresh):
    structure.cache_for_mode("on")
    fresh.put("a", 1)
    store_generation.bump("settings")              # any reload path that changed a value
    assert structure.cache_for_mode("on").stats()["cache_entries"] == 0


def test_a_new_cap_resizes_on_the_next_scan(fresh, monkeypatch):
    structure.cache_for_mode("on")
    for k in "abc":
        fresh.put(k, k)
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 1)
    assert structure.cache_for_mode("on").stats()["cache_entries"] == 1


def test_apply_config_change_clears_and_resizes(fresh, monkeypatch):
    fresh.put("a", 1)
    structure.apply_config_change({})
    assert fresh.stats()["cache_entries"] == 1                # nothing changed: kept
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 7)
    structure.apply_config_change({"STRUCTURE_CACHE_MAX": (3, 7)})
    assert fresh.stats()["cache_entries"] == 0 and fresh.max_entries == 7


def test_sighup_clears_through_the_loops_callback(fresh, monkeypatch):
    from swingbot.commands.scanning import loops
    assert loops._apply_structure_cache_change in bot_core._reload_callbacks
    monkeypatch.setattr(bot_core, "_reload_callbacks", [loops._apply_structure_cache_change])
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    fresh.put("a", 1)
    bot_core._handle_reload_signal()
    assert fresh.stats()["cache_entries"] == 0
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_structure_cache.py`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'swingbot.core.scanning.structure'`.

- [ ] **Step 3: Write `structure.py`**

Create `swingbot/core/scanning/structure.py`:

```python
"""v245: the exact prefix cache for the live scan's analysis phase.

A cached value is a frozen, pure function of ``frame.iloc[:m]``, stored under
``(ticker, unit, prefix_fingerprint(frame, m))``; the tail and the live price
are recomputed every scan (spec § Exact prefix caching). Only the two live
call sites pass a cache. Every config change clears it (``apply_config_change``
on SIGHUP/config_watcher; the settings generation in ``cache_for_mode``).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Callable

from swingbot import config
from swingbot.core.infra import store_generation

log = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 600
_MISSING = object()


def prefix_fingerprint(frame, m: int) -> tuple:
    """Identity of ``frame.iloc[:m]`` (index Decision 5): ``m``, the first row's
    date and close (trim start, split restatement), the last prefix row's date
    and OHLCV (revised bar or volume). ``m == 0`` is the empty prefix."""
    if m <= 0:
        return (0,)
    row = frame.iloc[m - 1]
    volume = float(row["Volume"]) if "Volume" in frame.columns else None
    return (m, str(frame.index[0]), float(frame["Close"].iloc[0]), str(frame.index[m - 1]),
            float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), volume)


class StructureCache:
    """Bounded, lock-guarded LRU. ``None`` is never stored: a ``None`` get is a miss."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._lock = threading.Lock()
        self._entries: OrderedDict = OrderedDict()
        self._max = max(int(max_entries), 0)
        self._generation = store_generation.generation("settings")
        self._hits = self._misses = self._evictions = 0
        self.prefix_build_s = 0.0

    @property
    def max_entries(self) -> int:
        return self._max

    def get(self, key):
        with self._lock:
            value = self._entries.get(key, _MISSING)
            if value is _MISSING:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return value

    def put(self, key, value) -> None:
        if value is None:
            return
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            self._evict_locked()

    def get_or_build(self, key: tuple, build: Callable[[], object], *, ticker: str = ""):
        """Cached value, or ``build()`` stored; a failing build warns, stores nothing, returns None."""
        value = self.get(key)
        if value is not None:
            return value
        started = time.perf_counter()
        try:
            value = build()
        except Exception as exc:
            log.warning("analysis cache: building %s failed for %s; computing uncached this scan: %s",
                        key[1] if len(key) > 1 else key, ticker, exc)
            return None
        finally:
            self._add_build_time(time.perf_counter() - started)
        self.put(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def resize(self, max_entries: int) -> None:
        with self._lock:
            self._max = max(int(max_entries), 0)
            self._evict_locked()

    def sync_config(self, generation: int, max_entries: int) -> None:
        """Clear when the settings generation moved since the last sync;
        resize when the cap changed."""
        with self._lock:
            if generation != self._generation:
                self._generation = generation
                self._entries.clear()
        if int(max_entries) != self._max:
            self.resize(max_entries)

    def stats(self) -> dict:
        with self._lock:
            return {"cache_hits": self._hits, "cache_misses": self._misses,
                    "cache_evictions": self._evictions, "cache_entries": len(self._entries)}

    def reset_counters(self) -> None:
        with self._lock:
            self._hits = self._misses = self._evictions = 0
            self.prefix_build_s = 0.0

    def _add_build_time(self, seconds: float) -> None:
        with self._lock:
            self.prefix_build_s += seconds

    def _evict_locked(self) -> None:
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
            self._evictions += 1


STRUCTURE_CACHE = StructureCache(getattr(config, "STRUCTURE_CACHE_MAX", DEFAULT_MAX_ENTRIES))


def analysis_cache_mode() -> str:
    """``ANALYSIS_CACHE`` as config parsed it: off | shadow | on."""
    return getattr(config, "ANALYSIS_CACHE", "off")


def cache_for_mode(mode: str) -> StructureCache | None:
    """The live cache for ``shadow``/``on``, synced to the current config;
    ``None`` for ``off``. Called once per scan, never per ticker."""
    if mode not in ("shadow", "on"):
        return None
    STRUCTURE_CACHE.sync_config(store_generation.generation("settings"),
                                getattr(config, "STRUCTURE_CACHE_MAX", DEFAULT_MAX_ENTRIES))
    return STRUCTURE_CACHE


def apply_config_change(changed: dict) -> None:
    """Reload hook: any changed setting clears the whole cache (no hand-kept
    field list); a changed ``STRUCTURE_CACHE_MAX`` also resizes it."""
    if not changed:
        return
    if "STRUCTURE_CACHE_MAX" in changed:
        STRUCTURE_CACHE.resize(config.STRUCTURE_CACHE_MAX)
    STRUCTURE_CACHE.clear()
    log.info("analysis cache cleared: %d setting(s) changed", len(changed))
```

- [ ] **Step 4: Add the config fields and the mode values**

In `swingbot/config.py`, directly after the `SCAN_WORKERS` `Field(...)`
(ends ~1246), add the two fields. Take the default from `## Cache size` in
`docs/superpowers/results/2026-11-23-v245-analysis-profile.md`: `"600"`
unless that section recommends a lower figure, in which case that figure
goes here, in `.env.example` and in `DEFAULT_MAX_ENTRIES` above.

```python
    Field("ANALYSIS_CACHE", "ANALYSIS_CACHE", "Universe & Scanning", "Analysis prefix cache",
          type="select", default="off", options=["off", "shadow", "on"],
          help="v245. on = work that is a pure function of the frame minus its last bar is "
               "cached per ticker; the last bar and the live price are recomputed every scan, so "
               "alerts are byte-identical to off. shadow = on, plus a rotating third of the "
               "watchlist re-run uncached and compared (logs/analysis_cache_shadow.jsonl)."),
    Field("STRUCTURE_CACHE_MAX", "STRUCTURE_CACHE_MAX", "Universe & Scanning",
          "Analysis cache entries",
          type="number", default="600", min=0, max=20000, step=10,
          help="v245. Most entries the analysis cache keeps (LRU; two per ticker). Sized so the "
               "worst case stays under 150 MB; watch rss_mb in scan telemetry."),
```

In `_MODE_VALUES` (~1780), after `"PLAN_ENGINE_V2"`:

```python
    "ANALYSIS_CACHE": ("off", "shadow", "on"),
```

(No `_MODE_FALLBACK` entry: unknown values fall back to `"off"`, the safe value.)

In `.env.example`, after `SCAN_WORKERS=1`:

```bash

# v245 analysis prefix cache: off | shadow | on. Alerts are byte-identical in
# every mode; shadow also compares a third of the watchlist uncached.
ANALYSIS_CACHE=off

# Most entries the analysis cache keeps (LRU); two per ticker. Resized on reload.
STRUCTURE_CACHE_MAX=600
```

- [ ] **Step 5: Register the reload hook**

In `swingbot/commands/scanning/loops.py`, add to the imports (after
`from swingbot.core.scanning import outlook_session`):

```python
from swingbot.core.scanning import structure as analysis_structure
```

After `_apply_scan_interval_change` (~1401-1411):

```python
@on_config_reload
def _apply_structure_cache_change(changed: dict):
    """v245: any config change clears the analysis prefix cache (resized when
    STRUCTURE_CACHE_MAX changed), so no scan reads a prefix built under the
    previous config."""
    analysis_structure.apply_config_change(changed)
```

In `config_watcher` (~412), directly after `_apply_scan_interval_change(changed)`:

```python
        _apply_structure_cache_change(changed)
```

- [ ] **Step 6: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_structure_cache.py
python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py
python scripts/dev/testrun.py file tests/commands/test_config_watcher_reload.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
```

Expected: all PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes; every function in `structure.py` is below 10 and
`config_watcher` does not grow a branch.

- [ ] **Step 8: Commit (two scoped commits)**

```bash
git add swingbot/core/scanning/structure.py swingbot/config.py .env.example tests/scanning/test_structure_cache.py
git commit -m "feat(v245): StructureCache, prefix fingerprint, ANALYSIS_CACHE and STRUCTURE_CACHE_MAX (V245-7)"
git add swingbot/commands/scanning/loops.py
git commit -m "feat(v245): clear the analysis cache on SIGHUP and config_watcher reloads (V245-7)"
```

Re-run the test file after the second commit (its SIGHUP test needs both).

### Task V245-8: Trendline prefix split

**Model:** opus — rewrites the O(pivots³) pair search on the hottest path into cached and per-scan halves; one float or ordering slip changes alerts.

Spec § Exact prefix caching (trendline row, § The 1500-bar trim), § Testing
→ Trendline split; index Decision 4. No cache here: `_find_best_trendline`
accepts a prefix result, and every result equals today's.

**Why it is exact.** With the window's pivots split as `C + tail` (`C` =
the prefix's confirmed pivots), a pair's geometry reads only its two pivots
and its touches are collected in pivot order, so `touches = touches_over_C +
touches_over_tail` (same list, same order, same `avg_vol` sum). Everything
reading `n_bars` or `current_price` (`line_at_now`, both price gates,
`recency`, score) is recomputed per scan; pairs touching the tail run
`_score_candidate` as today; the `i < j` order and strict `>` tie-break are
kept. The prefix is `T.iloc[:m]` of the trimmed window `T`, so coordinates
match. **Correctness rests on one check:** `_verified_prefix` compares the
window's pivots with `confirmed` element for element on every call; cached
cells are pure functions of `confirmed`, so a match is exact and any
mismatch (moved trim start, the volume filter's 30 % rule flipping, a
restated price, the other side's prefix) falls back to the empty prefix,
today's algorithm on the same path. The two constants only set the hit rate.

**Signature note.** `prefix` joins V245-4's keyword-only `all_pivots` after the `*`.

**Files:**
- Modify: `swingbot/core/market/trendlines.py` (after `MAX_PIVOT_SCAN_BARS` ~137; `_score_candidate` ~216; `_trimmed_zigzag`, `_find_best_trendline`, `custom_scanner_levels` as V245-4 left them)
- Create: `tests/market/test_trendline_split.py`

**Interfaces:**
- Consumes: V245-4's `_volume_confirmed_pivots(..., all_pivots=None)`, `_zigzag_or_empty`, `_trimmed_zigzag`, `_shift_to_full_frame`; the golden.
- Produces (ledger row V245-8): `TRENDLINE_PREFIX_TAIL_BARS`, `UNSTABLE_PREFIX_PIVOTS`, `TrendlinePrefix`, `trimmed_frame`, `prefix_length`, `build_trendline_prefix(trimmed, side, m)`, `_find_best_trendline(..., *, all_pivots=None, prefix=None)`, `custom_scanner_levels(df, current_price, prefixes=None)` — code below.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_trendline_split.py`:

```python
"""v245 V245-8: every prefix (none, own, yesterday's, tampered, other side) gives the
pre-v245 result (``_reference_best``: the old loop and old ``_score_candidate``, copied)."""
import copy
import dataclasses

import pandas as pd
import pytest

from swingbot.core.market import trendlines as tl

_PERIOD = 20


def _wave(n, drift=-0.3, jitter=0.37, volume=True):
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    vals, vols = [], []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        vals.append(200.0 + drift * i + 8.0 * (1.0 - abs(2.0 * phase - 1.0) * 2.0) + jitter * (i % 7))
        turn = i % _PERIOD in (0, _PERIOD // 2)
        vols.append((2_500_000.0 if turn else 1_000_000.0) if volume else 0.0)
    close = pd.Series(vals, index=idx)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": pd.Series(vols, index=idx)}, index=idx)


FRAMES = {
    "short_140": lambda: _wave(140),
    "flat_ties": lambda: _wave(200, drift=0.0, jitter=0.0),   # every low equal: pairs tie
    "steep_140": lambda: _wave(140, drift=-0.6),              # the slope gate rejects
    "no_volume": lambda: _wave(160, volume=False),
    "exactly_1500": lambda: _wave(1500, drift=-0.02),
    "long_1700": lambda: _wave(1700, drift=-0.01),            # the 1500-bar trim applies
}
PRICE_MULTS = [1.0, 0.9, 1.1, 0.5]
SIDES = ["support", "resistance"]


def _kind(side):
    return "low" if side == "support" else "high"


def _old_score(slope, intercept, pivots, n_bars, price, side):
    line_at_now = slope * (n_bars - 1) + intercept
    if side == "support" and line_at_now > price * 1.01:
        return None
    if side == "resistance" and line_at_now < price * 0.99:
        return None
    if price > 0 and abs(slope / price * 100) > tl.MAX_SLOPE_PCT_PER_BAR:
        return None
    touches = []
    for b, p, v in pivots:
        here = slope * b + intercept
        if here > 0 and abs(p - here) / here * 100 <= tl.TOUCH_TOLERANCE_PCT:
            touches.append((b, p, v))
    if len(touches) < 2:
        return None
    avg = sum(v for _, _, v in touches) / len(touches)
    recency = max(b for b, _, _ in touches) / max(n_bars - 1, 1)
    return {"slope": slope, "intercept": intercept, "touches": touches, "strength": len(touches),
            "score": len(touches) * avg * (0.4 + 0.6 * recency), "line_at_now": line_at_now}


def _pairs(pivots):
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            (x0, y0, _), (x1, y1, _) = pivots[i], pivots[j]
            if x1 != x0 and y0 > 0 and y1 > 0:
                slope = (y1 - y0) / (x1 - x0)
                yield slope, y0 - slope * x0


def _reference_best(df, price, side):
    """The pre-v245 _find_best_trendline."""
    trim = max(len(df) - tl.MAX_PIVOT_SCAN_BARS, 0)
    frame = df.tail(tl.MAX_PIVOT_SCAN_BARS) if trim else df
    pivots = tl._volume_confirmed_pivots(frame, _kind(side))
    best = None
    for slope, intercept in _pairs(pivots):
        r = _old_score(slope, intercept, pivots, len(frame), price, side)
        if r and (best is None or r["score"] > best["score"]):
            best = r
    if best is not None and trim:
        best["intercept"] -= best["slope"] * trim
        best["touches"] = [(b + trim, p, v) for b, p, v in best["touches"]]
    return best


def _census(df, price, side):
    """(scores of accepted pairs, side-gate rejects, slope-gate rejects)."""
    frame, _ = tl.trimmed_frame(df)
    pivots, n = tl._volume_confirmed_pivots(frame, _kind(side)), len(frame)
    scores, side_rej, slope_rej = [], 0, 0
    for slope, intercept in _pairs(pivots):
        now = slope * (n - 1) + intercept
        if (side == "support" and now > price * 1.01) or (side == "resistance" and now < price * 0.99):
            side_rej += 1
        elif abs(slope / price * 100) > tl.MAX_SLOPE_PCT_PER_BAR:
            slope_rej += 1
        elif (r := _old_score(slope, intercept, pivots, n, price, side)):
            scores.append(r["score"])
    return scores, side_rej, slope_rej


def _prefix_for(df, side):
    trimmed, _ = tl.trimmed_frame(df)
    return tl.build_trendline_prefix(trimmed, side, tl.prefix_length(trimmed))


def _price(df, mult=1.0):
    return float(df["Close"].iloc[-1]) * mult


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("mult", PRICE_MULTS)
@pytest.mark.parametrize("side", SIDES)
def test_no_prefix_and_own_prefix_equal_the_old_algorithm(name, mult, side):
    df = FRAMES[name]()
    want = _reference_best(df, _price(df, mult), side)
    assert tl._find_best_trendline(df, _price(df, mult), side) == want
    assert tl._find_best_trendline(df, _price(df, mult), side, prefix=_prefix_for(df, side)) == want


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("side", SIDES)
def test_yesterdays_prefix_carried_into_today_equals_the_old_algorithm(name, side):
    df = FRAMES[name]()
    carried = _prefix_for(df.iloc[:-1], side)           # built by yesterday's scans
    for mult in PRICE_MULTS:
        assert tl._find_best_trendline(df, _price(df, mult), side, prefix=carried) == \
            _reference_best(df, _price(df, mult), side)


@pytest.mark.parametrize("name", ["short_140", "flat_ties", "exactly_1500", "long_1700"])
@pytest.mark.parametrize("side", SIDES)
def test_own_prefix_is_verified_and_used(name, side):
    df = FRAMES[name]()
    pre = _prefix_for(df, side)
    pivots = tl._volume_confirmed_pivots(tl.trimmed_frame(df)[0], _kind(side))
    assert len(pre.confirmed) >= 2, "the fixture must give the prefix pairs to cache"
    assert tl._verified_prefix(pre, pivots, side) is pre


@pytest.mark.parametrize("variant", ["tampered", "other_side"])
def test_a_wrong_prefix_falls_back_to_todays_algorithm(variant):
    df = FRAMES["short_140"]()
    pre = _prefix_for(df, "support")
    if variant == "tampered":
        b, p, v = pre.confirmed[0]
        pre = tl.TrendlinePrefix("support", pre.m, ((b, p + 0.5, v),) + pre.confirmed[1:], pre.pairs)
    else:
        pre = _prefix_for(df, "resistance")
    pivots = tl._volume_confirmed_pivots(df, "low")
    assert tl._verified_prefix(pre, pivots, "support") == tl.TrendlinePrefix("support", 0, (), ())
    assert tl._find_best_trendline(df, _price(df), "support", prefix=pre) == \
        _reference_best(df, _price(df), "support")


def test_fixtures_exercise_ties_and_both_price_gates():
    """On failure, change the fixture's drift, never the assertion."""
    flat = FRAMES["flat_ties"]()
    scores, _, _ = _census(flat, _price(flat), "support")
    assert scores and scores.count(max(scores)) >= 2
    short = FRAMES["short_140"]()
    assert _census(short, _price(short, 0.9), "support")[1] > 0
    steep = FRAMES["steep_140"]()
    assert _census(steep, _price(steep), "support")[2] > 0


def test_cached_pairs_skip_the_full_touch_scan(monkeypatch):
    df = FRAMES["long_1700"]()
    pre = _prefix_for(df, "support")
    calls = {"n": 0}
    real = tl._score_candidate

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tl, "_score_candidate", counting)
    tl._find_best_trendline(df, _price(df), "support")
    uncached, calls["n"] = calls["n"], 0
    tl._find_best_trendline(df, _price(df), "support", prefix=pre)
    assert calls["n"] < uncached


def test_prefix_window_and_unstable_pivots():
    df = FRAMES["short_140"]()
    trimmed, start = tl.trimmed_frame(df)
    m = tl.prefix_length(trimmed)
    assert start == 0 and m == len(df) - tl.TRENDLINE_PREFIX_TAIL_BARS
    found = tl._volume_confirmed_pivots(trimmed.iloc[:m], "low")
    pre = tl.build_trendline_prefix(trimmed, "support", m)
    assert list(pre.confirmed) == found[:max(len(found) - tl.UNSTABLE_PREFIX_PIVOTS, 0)]
    assert tl.build_trendline_prefix(trimmed, "support", 10).confirmed == ()
    assert tl.trimmed_frame(FRAMES["long_1700"]())[1] == 200


def test_prefix_is_frozen_and_unchanged_by_scans():
    df = FRAMES["long_1700"]()
    pre = _prefix_for(df, "support")
    before = copy.deepcopy(pre)
    for mult in (1.0, 0.95):
        best = tl._find_best_trendline(df, _price(df, mult), "support", prefix=pre)
        if best:
            best["touches"].append(("junk",))
            best["intercept"] = 0.0
    assert pre == before
    assert isinstance(pre.confirmed, tuple) and all(isinstance(row, tuple) for row in pre.pairs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pre.m = 0


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_custom_scanner_levels_with_prefixes_is_unchanged(name):
    df = FRAMES[name]()
    prefixes = {side: _prefix_for(df, side) for side in SIDES}
    assert tl.custom_scanner_levels(df, _price(df), prefixes=prefixes) == \
        tl.custom_scanner_levels(df, _price(df))
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_trendline_split.py`
Expected: FAIL — `AttributeError: ... 'trimmed_frame'`.

- [ ] **Step 3: Constants, the frozen prefix and the window helpers**

In `swingbot/core/market/trendlines.py`, add `from dataclasses import dataclass`
to the imports. After `MAX_PIVOT_SCAN_BARS` (~137):

```python
# v245 prefix/tail split (index Decision 4): the prefix is the trimmed window
# minus its last row(s); its last pivots are left to the tail. Hit rate only:
# _verified_prefix checks every call that the window's pivots start with it.
TRENDLINE_PREFIX_TAIL_BARS = 1
UNSTABLE_PREFIX_PIVOTS = 2


@dataclass(frozen=True)
class TrendlinePrefix:
    """``confirmed``: (bar_idx, price, vol_ratio) pivots, trimmed-window coordinates.
    ``pairs[i][j - i - 1]`` (i < j): None (skipped pair) or (slope, intercept, touches over confirmed)."""
    side: str
    m: int
    confirmed: tuple
    pairs: tuple


def trimmed_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """(last MAX_PIVOT_SCAN_BARS rows, their start offset in df)."""
    trim_start = max(len(df) - MAX_PIVOT_SCAN_BARS, 0)
    return (df.tail(MAX_PIVOT_SCAN_BARS) if trim_start else df), trim_start


def prefix_length(trimmed: pd.DataFrame) -> int:
    return max(len(trimmed) - TRENDLINE_PREFIX_TAIL_BARS, 0)
```

Change `_trimmed_zigzag`'s body to `return _zigzag_or_empty(trimmed_frame(df)[0])`.

- [ ] **Step 4: Split `_score_candidate` into gates, touches and score**

Add four helpers above `_score_candidate` (each expression verbatim from its body):

```python
def _pair_line(p0: tuple, p1: tuple) -> tuple[float, float] | None:
    x0, y0, _ = p0
    x1, y1, _ = p1
    if x1 == x0 or y0 <= 0 or y1 <= 0:
        return None
    slope = (y1 - y0) / (x1 - x0)
    return slope, y0 - slope * x0


def _touches(slope: float, intercept: float, pivots) -> list:
    touches: list = []
    for bar_idx, price, vol_ratio in pivots:
        line_here = _eval_line(slope, intercept, bar_idx)
        if line_here > 0 and abs(price - line_here) / line_here * 100 <= TOUCH_TOLERANCE_PCT:
            touches.append((bar_idx, price, vol_ratio))
    return touches


def _price_gates_pass(slope: float, line_at_now: float, current_price: float, side: str) -> bool:
    if side == "support" and line_at_now > current_price * 1.01:
        return False
    if side == "resistance" and line_at_now < current_price * 0.99:
        return False
    return not (current_price > 0 and abs(slope / current_price * 100) > MAX_SLOPE_PCT_PER_BAR)


def _scored(slope: float, intercept: float, touches: list, n_bars: int, line_at_now: float) -> dict | None:
    if len(touches) < 2:
        return None
    avg_vol = sum(v for _, _, v in touches) / len(touches)
    last_touch_bar = max(b for b, _, _ in touches)
    recency = last_touch_bar / max(n_bars - 1, 1)          # 0 … 1
    score = len(touches) * avg_vol * (0.4 + 0.6 * recency)
    return {"slope": slope, "intercept": intercept, "touches": touches,
            "strength": len(touches), "score": score, "line_at_now": line_at_now}
```

`_score_candidate`'s new body:

```python
    line_at_now = _eval_line(slope, intercept, n_bars - 1)
    if not _price_gates_pass(slope, line_at_now, current_price, side):
        return None
    return _scored(slope, intercept, _touches(slope, intercept, pivots), n_bars, line_at_now)
```

- [ ] **Step 5: Prefix build, verification and the split search**

Add above `_find_best_trendline`:

```python
def _empty_prefix(side: str) -> TrendlinePrefix:
    return TrendlinePrefix(side, 0, (), ())


def _prefix_row(confirmed: tuple, i: int) -> tuple:
    row = []
    for j in range(i + 1, len(confirmed)):
        line = _pair_line(confirmed[i], confirmed[j])
        row.append(None if line is None else (*line, tuple(_touches(*line, confirmed))))
    return tuple(row)


def build_trendline_prefix(trimmed: pd.DataFrame, side: str, m: int) -> TrendlinePrefix:
    found = _volume_confirmed_pivots(trimmed.iloc[:m], "low" if side == "support" else "high")
    confirmed = tuple(found[:max(len(found) - UNSTABLE_PREFIX_PIVOTS, 0)])
    return TrendlinePrefix(side, m, confirmed, tuple(_prefix_row(confirmed, i) for i in range(len(confirmed))))


def _verified_prefix(prefix: TrendlinePrefix | None, pivots: list, side: str) -> TrendlinePrefix:
    if prefix is None or prefix.side != side:
        return _empty_prefix(side)
    k = len(prefix.confirmed)
    if k > len(pivots) or tuple(pivots[:k]) != prefix.confirmed:
        return _empty_prefix(side)
    return prefix


def _cached_pair_result(cell, tail: list, n_bars: int, current_price: float, side: str) -> dict | None:
    if cell is None:
        return None
    slope, intercept, prefix_touches = cell
    line_at_now = _eval_line(slope, intercept, n_bars - 1)
    if not _price_gates_pass(slope, line_at_now, current_price, side):
        return None
    touches = list(prefix_touches) + _touches(slope, intercept, tail)
    return _scored(slope, intercept, touches, n_bars, line_at_now)


def _live_pair_result(p0, p1, pivots: list, n_bars: int, current_price: float, side: str) -> dict | None:
    line = _pair_line(p0, p1)
    if line is None:
        return None
    return _score_candidate(line[0], line[1], pivots, n_bars, current_price, side)


def _pick_best(pivots: list, prefix: TrendlinePrefix, n_bars: int, current_price: float, side: str) -> dict | None:
    k = len(prefix.confirmed)
    tail = pivots[k:]
    best: dict | None = None
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            if j < k:
                result = _cached_pair_result(prefix.pairs[i][j - i - 1], tail, n_bars, current_price, side)
            else:
                result = _live_pair_result(pivots[i], pivots[j], pivots, n_bars, current_price, side)
            if result and (best is None or result["score"] > best["score"]):
                best = result
    return best
```

Replace `_find_best_trendline`'s signature and body (docstring stays, plus a
paragraph on `prefix`):

```python
def _find_best_trendline(df: pd.DataFrame, current_price: float, side: str, *,
                         all_pivots: list | None = None,
                         prefix: TrendlinePrefix | None = None) -> dict | None:
    """
    (existing docstring and V245-4's all_pivots paragraph, then:)

    ``prefix`` (v245): used only when the window's pivots start with its
    confirmed pivots; otherwise every pair runs live. Same result either way.
    """
    df, trim_start = trimmed_frame(df)
    pivots = _volume_confirmed_pivots(df, "low" if side == "support" else "high", all_pivots=all_pivots)
    if len(pivots) < 2:
        return None
    best = _pick_best(pivots, _verified_prefix(prefix, pivots, side), len(df), current_price, side)
    return _shift_to_full_frame(best, trim_start)
```

In `custom_scanner_levels`, change the signature to
`custom_scanner_levels(df: pd.DataFrame, current_price: float, prefixes: dict | None = None) -> list`,
add a docstring line (``prefixes``: side -> TrendlinePrefix, v245; same result), and pass it through:

```python
    shared = _trimmed_zigzag(df)
    prefixes = prefixes or {}
    candidates: list = []
    for side in ("support", "resistance"):
        try:
            result = _find_best_trendline(df, current_price, side, all_pivots=shared,
                                          prefix=prefixes.get(side))
```

- [ ] **Step 6: Run the tests, the golden and the neighbours**

```bash
python scripts/dev/testrun.py file tests/market/test_trendline_split.py
python scripts/dev/testrun.py file tests/market/test_trendline_shared_pivots.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/charts/test_trendline_fit.py
python scripts/dev/testrun.py file tests/charts/test_trade_chart_stored_fit.py
```

Expected: all PASS, `0 failed`, `0 xfailed`, golden unchanged.

- [ ] **Step 7: Complexity gate**

```bash
python scripts/dev/complexity_gate.py
python -m radon cc -s swingbot/core/market/trendlines.py | grep -E "_find_best_trendline|_pick_best|_score_candidate|_price_gates_pass|_verified_prefix|custom_scanner_levels"
```

Expected: passes; `_find_best_trendline` ~3, `_pick_best` ~7, `_score_candidate` 2.
On a shrinkable baseline run `python scripts/dev/complexity_gate.py --update`.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/market/trendlines.py tests/market/test_trendline_split.py
git add scripts/dev/complexity_baseline.json   # only if Step 7 updated it
git commit -m "perf(v245): trendline pair search split into a verified prefix and a per-scan tail (V245-8)"
```

### Task V245-9: Wire the cache and one `now` into the two live call sites; `ScanItem.prefix_results`; `rescenario`

**Model:** opus — threads new state through `_scan_one` (complexity 35, may not grow), both scan lanes and the pre-post rebuild; the cache-free callers must stay byte-for-byte unchanged.

Spec § Call sites, § Knob and shadow check (the `now` bullet); index
Decisions 3 and 5. After this task `ANALYSIS_CACHE=on` (or `shadow`) makes
the live scan read the trendline prefixes from the cache; `off` (the
default) passes `structure=None` and runs exactly today's code.

**What changes.** `_scan_one(..., structure=None, now=None)` looks up
`ticker_prefixes` once per ticker, hands the trendline prefixes to
`custom_scanner_levels`, passes `now` to `_band_live` (via
`_horizon_scenarios`) and `_apply_pullback_dryup`, and stores
`prefix_results` on each `ScanItem`; `rescenario` reuses them and never
looks the cache up. The base lane reads `_analysis_cache()` and one
`scan_now` per scan; the SHORT lane carries the cache on
`ExtraScanContext.structure` and passes no `now` (Decision 3:
`ExtraScanContext.now` is the replay date, `scan_replay.py:346`).
**Unchanged:** `outlook_run.py:114`, `scan_replay.py:299/346` and every
cache-free path. The trendline unit is self-verifying (V245-8), so even a
fingerprint collision between two lanes' frames cannot change a line.

**Files:**
- Modify: `swingbot/core/scanning/structure.py` (units, `ticker_prefixes`, `trendline_prefixes`)
- Modify: `swingbot/core/scanning/analyze.py` (`ScanItem`, `_horizon_scenarios`, `_scan_one`, `rescenario`, `ExtraScanContext`, `scan_extra_candidate`; lines in Step 4)
- Modify: `swingbot/core/scanning/scan_run.py` (`_analysis_cache` helper; the call site ~754)
- Modify: `swingbot/core/scanning/short_run.py` (`_scan_context` ~73)
- Modify: `tests/scanning/v245_golden_cases.py` (`run_case`)
- Create: `tests/scanning/test_analysis_cache_wiring.py`

**Interfaces:**
- Consumes: V245-7 `StructureCache`, `prefix_fingerprint`, `cache_for_mode`; V245-8 `trimmed_frame`, `prefix_length`, `build_trendline_prefix`, `custom_scanner_levels(..., prefixes=)`; V245-1's golden helpers.
- Produces (ledger): `_scan_one(..., io=None, structure: StructureCache | None = None, now=None)`; `ScanItem.prefix_results: dict | None = None`; `_horizon_scenarios(..., *, ticker="", now=None, prefix_results: dict | None = None)`; `ExtraScanContext.structure: object = None`; `structure.TRENDLINE_UNITS`; `@dataclass(frozen=True) PrefixUnit(name, build)`; `structure.PREFIX_UNITS`; `structure.ticker_prefixes(cache, ticker, df) -> dict | None`; `scan_run._analysis_cache() -> tuple[str, StructureCache | None]`. Also `structure.trendline_prefixes(prefix_results) -> dict | None` and `run_case(case, *, structure=None, now=GOLDEN_NOW)` (new keyword, default keeps every caller).

- [ ] **Step 1: Write the failing test**

Run `/replicate-prod-db` first: `test_base_lane_passes_the_cache_and_one_now`
drives the real `_sync_run_scan` (it seeds the account store).

Create `tests/scanning/test_analysis_cache_wiring.py`:

```python
"""v245 V245-9: the prefix cache and one `now` reach `_scan_one` at the two live call sites."""
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import trendlines
from swingbot.core.scanning import analyze, scan_run, short_run, structure
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.scanning.v245_golden_cases import (CASES, GOLDEN_NOW, HERMETIC_IO, first_diff,
                                              frozen_clock, load_golden, run_case)
from tests.store_seed import seed_store

HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False, "confluence_deviation_pct": 1.0}
LONG = next(c for c in CASES if c.name == "long_completed")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_cache_on_matches_the_golden_cold_and_warm(case, monkeypatch):
    frozen_clock(monkeypatch)
    golden = load_golden()[case.name]
    cache = StructureCache(100)
    for _ in range(2):                                   # cold (builds), then warm (hits)
        got = run_case(case, structure=cache)
        assert got == golden, first_diff(got, golden)


def test_a_warm_scan_hits_both_trendline_units(monkeypatch):
    frozen_clock(monkeypatch)
    cache = StructureCache(100)
    run_case(LONG, structure=cache)
    cache.reset_counters()
    run_case(LONG, structure=cache)
    assert cache.stats()["cache_hits"] == 2 and cache.stats()["cache_misses"] == 0


def test_a_failing_prefix_build_warns_and_computes_uncached(monkeypatch, caplog):
    frozen_clock(monkeypatch)

    def boom(*args, **kwargs):
        raise ValueError("bad prefix")

    monkeypatch.setattr(trendlines, "build_trendline_prefix", boom)
    cache = StructureCache(100)
    with caplog.at_level(logging.WARNING, logger=structure.__name__):
        got = run_case(LONG, structure=cache)
    assert got == load_golden()[LONG.name]
    assert "GOLD" in caplog.text and cache.stats()["cache_entries"] == 0


def test_now_reaches_both_clock_readers(monkeypatch):
    seen = []
    real_band, real_dryup = analyze._band_live, analyze._apply_pullback_dryup

    def band(*args, **kwargs):
        seen.append(("band", args[3]))
        return real_band(*args, **kwargs)

    def dryup(*args, **kwargs):
        seen.append(("dryup", kwargs.get("now")))
        return real_dryup(*args, **kwargs)

    monkeypatch.setattr(analyze, "_band_live", band)
    monkeypatch.setattr(analyze, "_apply_pullback_dryup", dryup)
    when = GOLDEN_NOW + timedelta(days=3)
    run_case(LONG, now=when)
    assert {name for name, _ in seen} == {"band", "dryup"}
    assert all(value == when for _, value in seen)


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _items(df, cache):
    stats = analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, hard_filters=dict(HF),
                              io=HERMETIC_IO, structure=cache, now=GOLDEN_NOW)
    assert stats["items"], "the structured frame must build a 4w scenario"
    return stats["items"]


def test_items_carry_prefix_results_and_rescenario_never_looks_up(loose, monkeypatch):
    df = _structured_df()
    cached_items, plain_items = _items(df, StructureCache(10)), _items(df, None)
    assert set(cached_items[0].prefix_results) == set(structure.TRENDLINE_UNITS.values())
    assert plain_items[0].prefix_results is None

    def no_lookup(*args, **kwargs):
        raise AssertionError("rescenario must not look the cache up")

    monkeypatch.setattr(structure, "ticker_prefixes", no_lookup)
    for cached, plain in zip(cached_items, plain_items):
        for price in (cached.scan_price, cached.scan_price * 1.01):
            a, b = analyze.rescenario(cached, df, price), analyze.rescenario(plain, df, price)
            assert (a is None) == (b is None)
            if a is not None:
                assert (a.direction, a.entry, a.stop_loss, a.take_profit) == \
                    (b.direction, b.entry, b.stop_loss, b.take_profit)
                assert cached.level_map == plain.level_map


@pytest.mark.parametrize("mode,expect", [("off", False), ("shadow", True), ("on", True)])
def test_analysis_cache_follows_the_mode(mode, expect, monkeypatch):
    fresh = StructureCache(5)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", fresh)
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    got_mode, cache = scan_run._analysis_cache()
    assert got_mode == mode and (cache is fresh) == expect


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


@pytest.mark.parametrize("mode", ["off", "on"])
def test_base_lane_passes_the_cache_and_one_now(mode, data_dir, monkeypatch):
    fresh = StructureCache(10)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", fresh)
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    seen = []
    real = analyze._scan_one

    def spy(*args, **kwargs):
        seen.append((kwargs.get("structure"), kwargs.get("now")))
        return real(*args, **kwargs)

    monkeypatch.setattr(analyze, "_scan_one", spy)
    _scan_with_funnel("bullish")
    assert seen
    assert all(s is (fresh if mode == "on" else None) for s, _ in seen)
    assert len({n for _, n in seen}) == 1 and seen[0][1].tzinfo is not None


def test_extra_lane_passes_its_context_cache_and_no_now(monkeypatch):
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return {"newly_closed": [], "near_close_warnings": [], "funnel_events": [], "items": []}

    monkeypatch.setattr(analyze, "_scan_one", spy)
    monkeypatch.setattr(analyze, "align_completed", lambda frame, spy_df, _x, _now: (frame, spy_df, None))
    cache = StructureCache(1)
    ctx = analyze.ExtraScanContext(regime=None, min_confluence=0, min_confidence=0, rs_cache=None,
                                   spy_df=None, live_prices={}, hard_filters=None, opex_tier=None,
                                   io=HERMETIC_IO, structure=cache)
    analyze.scan_extra_candidate(SimpleNamespace(ticker="XYZ", source="s", mode="m"), object(), ctx, ["4w"])
    assert seen["structure"] is cache and "now" not in seen


def test_replay_contexts_carry_no_cache():
    ctx = analyze.ExtraScanContext(regime=None, min_confluence=0, min_confidence=0, rs_cache=None,
                                   spy_df=None, live_prices={}, hard_filters=None, opex_tier=None)
    assert ctx.structure is None


def test_short_lane_context_takes_the_scan_cache(monkeypatch):
    cache = StructureCache(1)
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("on", cache))
    monkeypatch.setattr(short_run.opex, "current_tier", lambda: None)
    monkeypatch.setattr(short_run.opex, "effective_min_confluence", lambda n, tier: n)
    monkeypatch.setattr(short_run.opex, "effective_min_confidence_level", lambda tier: 0)
    monkeypatch.setattr(scan_run, "_hard_filters_snapshot", lambda params=None: {})
    reference = SimpleNamespace(reference_rels=[], spy=None, now=None)
    ctx = short_run._scan_context(reference, SimpleNamespace(min_target_confluence_count=2), {}, None)
    assert ctx.structure is cache
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py`
Expected: FAIL — `TypeError: _scan_one() got an unexpected keyword argument 'structure'`,
`ExtraScanContext.__init__() got an unexpected keyword argument 'structure'`,
`AttributeError: ... '_analysis_cache'`.

- [ ] **Step 3: Units and lookups in `structure.py`**

Add `from dataclasses import dataclass` and
`from swingbot.core.market import trendlines` to the imports, and at the end
of `swingbot/core/scanning/structure.py`:

```python
TRENDLINE_UNITS = {"support": "trendline:support", "resistance": "trendline:resistance"}


@dataclass(frozen=True)
class PrefixUnit:
    """``build(df) -> (fingerprint, builder)``; a horizon-specific unit names its horizon."""
    name: str
    build: Callable


def _trendline_unit(side: str) -> PrefixUnit:
    def build(df):
        trimmed, _ = trendlines.trimmed_frame(df)
        m = trendlines.prefix_length(trimmed)
        return prefix_fingerprint(trimmed, m), lambda: trendlines.build_trendline_prefix(trimmed, side, m)
    return PrefixUnit(TRENDLINE_UNITS[side], build)


PREFIX_UNITS: tuple[PrefixUnit, ...] = tuple(_trendline_unit(side) for side in ("support", "resistance"))


def _unit_value(cache: StructureCache, ticker: str, unit: PrefixUnit, df):
    try:
        fingerprint, builder = unit.build(df)
    except Exception as exc:
        log.warning("analysis cache: keying %s failed for %s; computing uncached this scan: %s",
                    unit.name, ticker, exc)
        return None
    return cache.get_or_build((ticker, unit.name, fingerprint), builder, ticker=ticker)


def ticker_prefixes(cache: StructureCache | None, ticker: str, df) -> dict | None:
    """Unit name -> cached value for this ticker's frame; a unit whose build
    failed is absent (its consumer computes it directly). None without a cache."""
    if cache is None or df is None:
        return None
    found = {unit.name: _unit_value(cache, ticker, unit, df) for unit in PREFIX_UNITS}
    return {name: value for name, value in found.items() if value is not None}


def trendline_prefixes(prefix_results: dict | None) -> dict | None:
    """side -> TrendlinePrefix for custom_scanner_levels; None when there are none."""
    if not prefix_results:
        return None
    found = {side: prefix_results.get(name) for side, name in TRENDLINE_UNITS.items()}
    return {side: value for side, value in found.items() if value is not None} or None
```

- [ ] **Step 4: Thread `structure`, `now` and `prefix_results` through `analyze.py`**

Import (with the other `from . import` lines): `from . import structure as analysis_structure`.

`ScanItem`, after `hard_filters` (~109):

```python
    prefix_results: dict | None = None    # v245: the prefix-cache values this item was built from
```

`_horizon_scenarios` signature and one docstring sentence:

```python
def _horizon_scenarios(df, h: dict, current_price: float, trendline_candidates,
                       hard_filters: dict, *, ticker: str = "", now=None,
                       prefix_results: dict | None = None) -> HorizonBuild:
    """One horizon's level map and scenarios at `current_price` (v171 D5 seam:
    `_scan_one` at the scan price, `rescenario` at a re-quoted one).
    `prefix_results` (v245): the ticker's prefix-cache values for horizon-level
    units; None computes everything directly. Trendline units are consumed once
    per ticker in `_scan_one`, not here."""
```

`_scan_one`: append after `io: ScanIO | None = None` in the signature:

```python
              io: ScanIO | None = None,
              structure: "analysis_structure.StructureCache | None" = None, now=None) -> dict:
```

and add to its docstring: "`structure` (v245): the live prefix cache, passed only
by the two live call sites; None = compute everything (outlook, replay).
`now`: the scan's single clock reading for `_band_live` and
`_apply_pullback_dryup`; None reads the wall clock there, as before."

Replace the trendline line (~1111, keep the comment above it):

```python
    prefix_results = analysis_structure.ticker_prefixes(structure, ticker, df)   # v245; None without a cache
    trendline_candidates = trendlines.custom_scanner_levels(
        df, current_price, prefixes=analysis_structure.trendline_prefixes(prefix_results))
```

The `_horizon_scenarios` call (~1121):

```python
        candidates, supports, resistances, scenarios = _horizon_scenarios(
            df, h, current_price, trendline_candidates, hard_filters, ticker=ticker,
            now=now, prefix_results=prefix_results)
```

The dry-up line (~1148):

```python
        scenarios = _apply_pullback_dryup(scenarios, df, stats, ticker, horizon_key, now=now)
```

`ScanItem(...)` (~1288): add `prefix_results=prefix_results,` after
`hard_filters=hard_filters,`.

`rescenario` (~1316):

```python
    build = _horizon_scenarios(df, HORIZONS[horizon_key], price, item.trendline_candidates,
                               _default_hard_filters(item.hard_filters), ticker=item.result.ticker,
                               prefix_results=item.prefix_results)
```

`ExtraScanContext`, after `io`:

```python
    structure: object = None          # v245: the live prefix cache; replay leaves it None
```

`scan_extra_candidate`'s `_scan_one` call: change the last line to
`funnel_source=candidate.source, funnel_mode=candidate.mode, io=context.io,
structure=context.structure)` (no `now`, Decision 3).

- [ ] **Step 5: The two live call sites**

`swingbot/core/scanning/scan_run.py`: add
`from . import structure as analysis_structure` below the `from . import (...)`
block, and next to `_hard_filters_snapshot`:

```python
def _analysis_cache() -> tuple[str, "analysis_structure.StructureCache | None"]:
    """ANALYSIS_CACHE and the cache it selects, read once per scan (v245)."""
    mode = analysis_structure.analysis_cache_mode()
    return mode, analysis_structure.cache_for_mode(mode)
```

At the call site (~753), directly above `per_ticker_results = ...`:

```python
    cache_mode, analysis_cache = _analysis_cache()
    scan_now = datetime.now(timezone.utc)   # one clock for the whole analysis phase (v245 Decision 3)
    log.debug("analysis cache: %s", cache_mode)
```

and extend the lambda's last line to
`hard_filters=hard_filters, opex_tier_today=opex_tier_today, structure=analysis_cache, now=scan_now),`.

`swingbot/core/scanning/short_run.py` `_scan_context`: add
`structure=scan_run._analysis_cache()[1],` after `now=reference.now` (it is
built once per extra scan).

- [ ] **Step 6: `run_case` passes `now` and `structure` explicitly**

In `tests/scanning/v245_golden_cases.py`, `run_case` becomes:

```python
def run_case(case: GoldenCase, *, structure=None, now: datetime | None = GOLDEN_NOW) -> dict:
    """Run `_scan_one` on the case, hermetically, and return its snapshot.
    `now` is passed explicitly (V245-9); with frozen_clock it must give the same golden."""
    df = case.frame()
    live = case.live_price(df) if df is not None else None
    hard_filters = {**GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                    "confluence_atr_stop_floor": case.atr_stop_floor}
    with pytest.MonkeyPatch.context() as mp:
        _pin_config_defaults(mp)
        stats = analyze._scan_one(
            TICKER, df, list(case.horizons), None, None, MIN_CONFLUENCE, MIN_CONFIDENCE,
            live_prices={TICKER: live} if live else None, hard_filters=hard_filters,
            allowed_directions=case.allowed_directions, io=HERMETIC_IO,
            structure=structure, now=now)
    return snapshot(stats)
```

- [ ] **Step 7: Run the tests, the golden and the lanes' neighbours**

```bash
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/scanning/test_rescenario.py
python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py
python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py
```

Expected: all PASS, `0 failed`, `0 xfailed`; the golden unchanged with
`now=GOLDEN_NOW` passed explicitly; `git diff --stat` shows no `outlook_run.py`/`scan_replay.py`.

- [ ] **Step 8: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes; `_scan_one` stays 35, `_sync_run_scan` 94 (no new branch),
`ticker_prefixes` and `trendline_prefixes` below 6.

- [ ] **Step 9: Commit (two scoped commits)**

```bash
git add swingbot/core/scanning/structure.py swingbot/core/scanning/analyze.py tests/scanning/v245_golden_cases.py
git commit -m "feat(v245): _scan_one takes the prefix cache and one now; items carry prefix_results (V245-9)"
git add swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py tests/scanning/test_analysis_cache_wiring.py
git commit -m "feat(v245): base and SHORT lanes pass the analysis cache; base lane one clock per scan (V245-9)"
```

