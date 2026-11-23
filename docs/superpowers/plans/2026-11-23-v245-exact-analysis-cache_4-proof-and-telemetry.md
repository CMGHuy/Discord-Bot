# v245 — Exact analysis caching, Part 4: proof, further units, telemetry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-11" -A 400 <this file>`).

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md) — Global Constraints, Parallelisation and the task ledger live there; every task below includes them.

Phase B only: these tasks run only if V245-6 recorded `MISSED`. All three
need V245-9 (`_scan_one(structure=, now=)`, `ScanItem.prefix_results`,
`structure.PREFIX_UNITS`, `ticker_prefixes`) committed. V245-10 and V245-12
may run in parallel; V245-11 then V245-11b run alone, in that order (11b
edits `structure.py` and V245-9's wiring test).

# Phase B — proof, further units, telemetry

### Task V245-10: Prefix property test and immutability

**Model:** sonnet — a test-only task over interfaces that already exist; the reasoning lives in the case list below.

Spec § Testing, "Prefix property test" and "Immutability". This task adds
**no production code**. It proves on today's tree (after V245-9) that
`_scan_one` gives the same snapshot with the cache as without it. The cache
is carried across successive truncations of one frame, the way live scans
carry it across days, and the live price varies within a day. It also proves
that no scan can change a cached value.

**Expected outcome: every test passes the first time.** A failure is a real
cache bug, not a test to loosen. Stop and report the `first_diff` path and
the case label to the controller. Never weaken an assertion, and never
regenerate the golden.

**Case list (what each test pins):**

| Test | What it carries / varies | Spec line it covers |
|---|---|---|
| `test_wave_sweep_cache_on_equals_cache_off` | 421-row frame truncated to 419, 420, 421; per day: forming bar at 19:00 UTC at two prices, then "last row is yesterday" at 13:00 UTC next day | successive truncations, varying `current_price`, yesterday's last row |
| `test_long_sweep_crosses_the_trim` (slow) | 1561-row frame at 1499, 1500, 1501, 1561: the 1500-bar trim starts moving | the 1500-bar trim (spec § Exact prefix caching) |
| `test_half_day_bar` | last row a short-session bar (30 % volume, narrow range) at 18:30 UTC | half-day frame |
| `test_intraday_scans_hit_every_entry`, `test_a_new_day_misses_every_unit` | hit/miss counts | the sweep is not vacuous |
| `test_restated_history_misses` | whole frame × 0.5 (a split) at the same length | restatement → new key |
| `test_revision_behind_an_unchanged_fingerprint` | a mid-history pivot bar revised; the fingerprint is the same, so the key hits | a served entry is verified, never trusted |
| `test_cached_values_are_frozen` | every cached value walked: tuples, frozen dataclasses, scalars only | cached objects are frozen |
| `test_two_prices_against_one_entry_are_independent` | a first scan's results mutated (`Level.sources`, `trendline_candidates`) before a second | immutability, `Level.sources` included |

**Files:**
- Create: `tests/scanning/test_analysis_cache_property.py`

**Interfaces:**
- Consumes: V245-1 `tests/scanning/v245_golden_cases.py` (`GoldenCase`, `CASE_BY_NAME`, `TICKER == "GOLD"`, `GOLDEN_NOW`, `HERMETIC_IO`, `frozen_clock(monkeypatch, now)`, `run_case(case, *, structure=None, now=GOLDEN_NOW)` as V245-9 left it, `snapshot(stats)`, `first_diff(a, b)`); V245-7 `StructureCache(max_entries)` with `stats()`, `reset_counters()`, `structure.prefix_fingerprint(frame, m)`; V245-9 `structure.ticker_prefixes(cache, ticker, df) -> dict | None`, `structure.TRENDLINE_UNITS`, `_scan_one(..., io=, structure=, now=)`; V245-8 `trendlines.trimmed_frame(df)`; V245-4 `trendlines._volume_confirmed_pivots(df, kind)`; `levels.Level` (levels.py:109); `tests/scanning/test_engine_v2_plans._structured_df()`.
- Produces: nothing later tasks consume. V245-11 re-runs this file after adding its unit.

- [ ] **Step 1: Write the test file**

Create `tests/scanning/test_analysis_cache_property.py`:

```python
"""v245 V245-10: the prefix cache never changes `_scan_one`'s output.

Over successive truncations of a long frame, with one cache carried across
them the way live scans carry it across days, and with the live price varied
inside a day, the cache-on snapshot equals the cache-off snapshot exactly.
Cached values are frozen; no scan can change them.
"""
import copy
import dataclasses
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import trendlines
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.scanning import analyze, structure
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.v245_golden_cases import (CASE_BY_NAME, GOLDEN_NOW, HERMETIC_IO, TICKER, GoldenCase,
                                              first_diff, frozen_clock, run_case, snapshot)

WAVE = CASE_BY_NAME["wave_forming"].frame      # 421 rows, last row dated 2024-03-15
LONG = CASE_BY_NAME["long_forming"].frame      # 1561 rows: longer than MAX_PIVOT_SCAN_BARS


def _at(day, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def _intraday(df, hour: int = 19, minute: int = 0) -> datetime:
    """A clock on the last row's own date: that row is today's forming bar."""
    return _at(df.index[-1].date(), hour, minute)


def _next_morning(df) -> datetime:
    """13:00 UTC the next business day: the last row is yesterday's completed bar."""
    return _at((df.index[-1] + pd.offsets.BDay(1)).date(), 13)


def _case(df: pd.DataFrame, mult: float) -> GoldenCase:
    price = round(float(df["Close"].iloc[-1]) * mult, 4)
    return GoldenCase(f"n{len(df)}x{mult}", lambda: df.copy(), tuple(LEGACY_HORIZONS), None, False,
                      lambda _frame: price)


def _same(monkeypatch, df, mult, now, cache, label) -> None:
    """One scan with the cache and one without: same frame, price and clock."""
    frozen_clock(monkeypatch, now)
    case = _case(df, mult)
    cached = run_case(case, structure=cache, now=now)
    plain = run_case(case, structure=None, now=now)
    assert cached == plain, f"{label}: {first_diff(cached, plain)}"


def _sweep(monkeypatch, base: pd.DataFrame, lengths) -> StructureCache:
    cache = StructureCache(1000)                     # carried across every day, as live scans do
    for n in lengths:
        df = base.iloc[:n].copy()
        for mult in (1.0, 0.96):                     # at the close, then through a nearer stop
            _same(monkeypatch, df, mult, _intraday(df), cache, f"n={n} intraday x{mult}")
        _same(monkeypatch, df, 1.0, _next_morning(df), cache, f"n={n} next morning")
    return cache


def test_wave_sweep_cache_on_equals_cache_off(monkeypatch):
    cache = _sweep(monkeypatch, WAVE(), (419, 420, 421))
    assert cache.stats()["cache_hits"] > 0           # the warm path really ran


@pytest.mark.slow
def test_long_sweep_crosses_the_trim(monkeypatch):
    cache = _sweep(monkeypatch, LONG(), (1499, 1500, 1501, 1561))
    assert cache.stats()["cache_hits"] > 0


def _half_day(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    o, c = float(out["Open"].iloc[-1]), float(out["Close"].iloc[-1])
    out.iloc[-1, out.columns.get_loc("High")] = round(max(o, c) * 1.002, 4)
    out.iloc[-1, out.columns.get_loc("Low")] = round(min(o, c) * 0.998, 4)
    out.iloc[-1, out.columns.get_loc("Volume")] = round(float(out["Volume"].iloc[-2]) * 0.3)
    return out


def test_half_day_bar(monkeypatch):
    cache = StructureCache(100)
    df = _half_day(WAVE())
    for mult in (1.0, 1.012):
        _same(monkeypatch, df, mult, _intraday(df, 18, 30), cache, f"half day x{mult}")


def test_intraday_scans_hit_every_entry(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    run_case(_case(df, 1.0), structure=cache)
    entries = cache.stats()["cache_entries"]
    cache.reset_counters()
    run_case(_case(df, 0.96), structure=cache)
    stats = cache.stats()
    assert entries >= len(structure.TRENDLINE_UNITS)
    assert (stats["cache_hits"], stats["cache_misses"]) == (entries, 0)


def test_a_new_day_misses_every_unit(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    base, cache = WAVE(), StructureCache(100)
    run_case(_case(base.iloc[:420].copy(), 1.0), structure=cache)
    cache.reset_counters()
    run_case(_case(base, 1.0), structure=cache)      # one more session: every prefix moved
    assert cache.stats()["cache_hits"] == 0


def test_restated_history_misses(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    run_case(_case(df, 1.0), structure=cache)
    split = df.copy()
    ohlc = ["Open", "High", "Low", "Close"]
    split[ohlc] = (split[ohlc] * 0.5).round(4)
    split["Volume"] = split["Volume"] * 2
    cache.reset_counters()
    _same(monkeypatch, split, 1.0, GOLDEN_NOW, cache, "2:1 split")
    assert cache.stats()["cache_hits"] == 0


def _revised(df: pd.DataFrame) -> pd.DataFrame:
    """Lower one mid-history low pivot's Close and Low by 3 %. The first and
    last prefix rows are untouched, so prefix_fingerprint cannot see it."""
    trimmed, trim_start = trendlines.trimmed_frame(df)
    pivots = trendlines._volume_confirmed_pivots(trimmed, "low")
    bar = trim_start + pivots[len(pivots) // 2][0]
    out = df.copy()
    for col in ("Close", "Low"):
        out.iloc[bar, out.columns.get_loc(col)] = round(float(out[col].iloc[bar]) * 0.97, 4)
    return out


def test_revision_behind_an_unchanged_fingerprint(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    revised = _revised(df)
    m = len(df) - 1
    assert structure.prefix_fingerprint(df, m) == structure.prefix_fingerprint(revised, m)
    assert trendlines._volume_confirmed_pivots(revised, "low") != trendlines._volume_confirmed_pivots(df, "low")
    run_case(_case(df, 1.0), structure=cache)
    cache.reset_counters()
    _same(monkeypatch, revised, 1.0, GOLDEN_NOW, cache, "mid-history revision")
    assert cache.stats()["cache_hits"] > 0           # the stale entry was served by key, then verified


def _assert_frozen(value, path: str = "entry") -> None:
    if value is None or isinstance(value, (str, bytes, bool, int, float, np.generic)):
        return
    if isinstance(value, tuple):
        for i, item in enumerate(value):
            _assert_frozen(item, f"{path}[{i}]")
        return
    if isinstance(value, Level):                     # spec: a cached Level carries tuple sources
        assert isinstance(value.sources, tuple), f"{path}.sources is {type(value.sources).__name__}"
        _assert_frozen(value.sources, f"{path}.sources")
        return
    if dataclasses.is_dataclass(value) and value.__dataclass_params__.frozen:
        for field in dataclasses.fields(value):
            _assert_frozen(getattr(value, field.name), f"{path}.{field.name}")
        return
    raise AssertionError(f"{path}: {type(value).__name__} is mutable")


def test_cached_values_are_frozen(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    for frame in (WAVE, LONG):
        df, cache = frame(), StructureCache(100)
        values = structure.ticker_prefixes(cache, TICKER, df)
        assert values
        for name, value in values.items():
            _assert_frozen(value, name)


HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False, "confluence_deviation_pct": 1.0}


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _scan(df, price, cache) -> dict:
    return analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, live_prices={"T0": price},
                             hard_filters=dict(HF), io=HERMETIC_IO, structure=cache, now=GOLDEN_NOW)


def _vandalise(stats: dict) -> int:
    """Mutate everything a caller can reach in a scan's items; returns how much."""
    touched = 0
    for item in stats["items"]:
        if isinstance(item.trendline_candidates, list):
            item.trendline_candidates.append((1.0, "vandal"))
            touched += 1
        for side in item.level_map or ():
            for level in side:
                level.sources.append("vandal")
                touched += 1
    return touched


def test_two_prices_against_one_entry_are_independent(loose, monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = _structured_df(), StructureCache(10)
    close = float(df["Close"].iloc[-1])
    first = _scan(df, close, cache)
    entries = structure.ticker_prefixes(cache, "T0", df)
    before = copy.deepcopy(entries)
    assert _vandalise(first) > 0, "the structured frame must build items with a level map"
    second = snapshot(_scan(df, close * 1.01, cache))
    plain = snapshot(_scan(df, close * 1.01, None))
    assert second == plain, first_diff(second, plain)
    after = structure.ticker_prefixes(cache, "T0", df)
    assert after == before
    assert all(after[name] is entries[name] for name in entries)   # the same objects, unchanged
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_property.py`
Expected: all PASS, `0 failed`, `0 xfailed`. Any FAIL other than the one
below is a cache bug: stop and report (index § Global Constraints), never
loosen an assertion.

If `test_revision_behind_an_unchanged_fingerprint` fails on its second
`assert` (the revision left the pivots unchanged), the case is vacuous, not
a bug. Move the revised bar to `pivots[len(pivots) // 3]`, lower it by 6 %
instead of 3 %, and re-run. Never drop the assertion.

- [ ] **Step 3: Check the golden is untouched**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py`
Expected: PASS. This task changes no production file: `git status --short`
shows only the new test.

- [ ] **Step 4: Commit**

```bash
git add tests/scanning/test_analysis_cache_property.py
git commit -m "test(v245): prefix property test over truncations and cache immutability (V245-10)"
```

### Task V245-11: Further prefix-pure units — doc `U2..` (prepared: a resumable zigzag walk; none → recorded no-op)

**Model:** opus — splits a hot indicator that every level map and five other callers use; one float or order drift changes alerts.

Spec § Exact prefix caching, row "Any other source the profile shows is
prefix-pure **and** can be split without a float difference". This task
builds the unit's split function; V245-11b registers it in the cache and
wires its consumer. **The results doc decides what both build.** Step 0
reads `## Prefix-pure units` in
`docs/superpowers/results/2026-11-23-v245-analysis-profile.md`:

- **"none beyond U1"** (or every `U2..` row's verdict is "skip"): recorded no-op, Step 0 only. V245-11b is then skipped too.
- **`U2` is the horizon zigzag** (`collect_candidate_levels`' "Pivot high/low" source, `levels.py:276`): Steps 1–6 as written.
- **`U2` is another unit:** build its split with the same discipline. Write a verbatim copy of the old function in the test as the reference. Assert equality, element types included, over frames × parameters × prefix lengths, plus mismatched-state cases. The frozen state must verify itself against the frame it is given. One commit per unit. V245-11b then registers it the same way it registers the zigzag.

**Prepared design: resume the zigzag walk.** For each horizon,
`collect_candidate_levels` runs
`zigzag_pivots(df, threshold_pct=h["max_risk_pct"])` over the whole frame
(~2,500 closes on production). The ten scanned horizons have ten
**different** thresholds (2.0 … 10.7, `strategy_types.py:68-206`), so
V245-5's memo shares none of them. That makes ten full Python walks per
ticker per scan. `zigzag_pivots` (indicators.py:73) is a left-to-right
state machine over `Close`. After bar `m - 1` its whole state is the
pivots appended so far plus five variables, and pivots are only ever
appended, never revised. So walking `closes[:m]` once, freezing that state,
and continuing from bar `m` runs **the same comparisons on the same floats
in the same order** as a walk from bar 0: the result is identical, element
types included (`np.float64` prices are kept, never cast). The last,
unconfirmed pivots are recomputed anyway, since the tail walk continues
from the state. So `W = 1` bar, with no unstable-pivot rule.

**Safety without trusting the key.** The state stores a 16-byte BLAKE2b
digest of `closes[:m]` (plus dtype) and its threshold. `zigzag_pivots`
resumes only when both match the frame it is given, and otherwise walks from
bar 0. A mid-history revision that `prefix_fingerprint` cannot see therefore
still gives today's result, and so does a `rescenario` on a re-fetched frame.
Callers that pass no `state` (chart_geometry, signals, short_builders,
`indicators.py:241`) run exactly today's walk.

**Files (prepared design):**
- Modify: `swingbot/core/market/indicators.py` (`zigzag_pivots` :73; new `ZigzagState`, `ZIGZAG_PREFIX_UNIT`, `zigzag_prefix_state`, `zigzag_prefix_states` and helpers right after it)
- Create: `tests/market/test_prefix_units.py`

**Interfaces:**
- Consumes: V245-3 doc rows `U2..`; V245-1b's golden.
- Produces (V245-11b and the ledger rely on these): `indicators.ZIGZAG_PREFIX_UNIT = "zigzag:horizons"`; `@dataclass(frozen=True) indicators.ZigzagState(threshold_pct, m: int, digest: bytes, pivots: tuple, walk: tuple)`; `indicators.zigzag_pivots(df, threshold_pct, *, state=None) -> list`; `indicators.zigzag_prefix_state(df, threshold_pct, m) -> ZigzagState | None`; `indicators.zigzag_prefix_states(df, thresholds, m) -> tuple | None` (`((threshold, ZigzagState), ...)`); `indicators._zigzag_walk(closes, threshold_pct, carry, stop) -> tuple`; test helpers `_old_zigzag`, `_closes`, `_same`, `FRAMES` in `tests/market/test_prefix_units.py` (V245-11b appends to this file).

- [ ] **Step 0: Read the doc and pick the branch**

Run: `python scripts/dev/doc_section.py docs/superpowers/results/2026-11-23-v245-analysis-profile.md "Prefix-pure units" "Cache size"`
(exit code 2: find the two sections with `grep -n "^## "` and read them with `sed -n`).

Recorded no-op: under the `## Prefix-pure units` table, add the line
`V245-11 (<date>): none beyond U1 -- structure.PREFIX_UNITS stays the two trendline units; V245-11b skipped.`
Then run `git add docs/superpowers/results/2026-11-23-v245-analysis-profile.md && git commit -m "docs(v245): no prefix-pure unit beyond U1 (V245-11)"`
and stop.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_prefix_units.py`:

```python
"""v245 V245-11 (doc U2): the horizon zigzag resumes from a cached prefix walk.

zigzag_pivots(df, t, state=...) must return exactly what the walk from bar 0
returns, for every frame, threshold and prefix length; a state that does not
match the frame is ignored.
"""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import indicators
from swingbot.core.market.indicators import zigzag_pivots, zigzag_prefix_state, zigzag_prefix_states
from swingbot.core.market.strategy_types import HORIZONS


def _old_zigzag(df, threshold_pct):
    """zigzag_pivots before V245-11, verbatim (indicators.py:73)."""
    closes = df["Close"].values
    n = len(closes)
    pivots = []
    if n == 0:
        return pivots
    start_idx = 0
    start_price = closes[0]
    last_extreme_idx = 0
    last_extreme_price = closes[0]
    direction = None
    for i in range(1, n):
        price = closes[i]
        if last_extreme_price == 0:
            continue
        change_pct = (price - last_extreme_price) / last_extreme_price * 100
        if direction is None:
            if change_pct >= threshold_pct:
                pivots.append((start_idx, start_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
            elif change_pct <= -threshold_pct:
                pivots.append((start_idx, start_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "up":
            if price >= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (last_extreme_price - price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "down":
            if price <= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (price - last_extreme_price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
    return pivots


def _closes(values) -> pd.DataFrame:
    return pd.DataFrame({"Close": np.asarray(values, dtype=float)},
                        index=pd.bdate_range("2020-01-01", periods=len(values)))


def _walk(n, seed, vol=0.012):
    rng = np.random.RandomState(seed)
    return np.round(100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, n))), 4)


FRAMES = {
    "walk": _closes(_walk(600, 3)),
    "volatile": _closes(_walk(400, 8, vol=0.03)),
    "flat_start": _closes(np.concatenate([np.full(60, 100.0), _walk(300, 5)])),
    "zero_start": _closes(np.concatenate([[0.0], _walk(120, 9)])),
    "two_bars": _closes([100.0, 112.0]),
    "one_bar": _closes([100.0]),
}
THRESHOLDS = sorted({h["max_risk_pct"] for h in HORIZONS.values()} | {3.0})


def _same(got, want):
    assert got == want
    assert [tuple(map(type, p)) for p in got] == [tuple(map(type, p)) for p in want]


@pytest.mark.parametrize("name", FRAMES)
def test_no_state_is_unchanged(name):
    for t in THRESHOLDS:
        _same(zigzag_pivots(FRAMES[name], t), _old_zigzag(FRAMES[name], t))


@pytest.mark.parametrize("name", FRAMES)
def test_resumed_walk_equals_full_walk(name):
    df = FRAMES[name]
    n = len(df)
    for t in THRESHOLDS:
        for m in sorted({1, 2, 37, n // 2, n - 1, n} & set(range(1, n + 1))):
            _same(zigzag_pivots(df, t, state=zigzag_prefix_state(df, t, m)), _old_zigzag(df, t))


def test_yesterdays_state_resumes_today():
    df = FRAMES["walk"]
    for t in THRESHOLDS:
        state = zigzag_prefix_state(df.iloc[:-1], t, len(df) - 2)
        _same(zigzag_pivots(df, t, state=state), _old_zigzag(df, t))


def _starts(monkeypatch) -> list:
    seen, real = [], indicators._zigzag_walk

    def spy(closes, threshold_pct, carry, stop):
        seen.append(carry[0])
        return real(closes, threshold_pct, carry, stop)

    monkeypatch.setattr(indicators, "_zigzag_walk", spy)
    return seen


def test_a_matching_state_skips_the_prefix_and_a_mismatch_restarts(monkeypatch):
    df = FRAMES["walk"]
    t, m = 5.0, len(df) - 1
    state = zigzag_prefix_state(df, t, m)
    revised = df.copy()
    revised.iloc[m // 2, 0] = round(float(revised["Close"].iloc[m // 2]) * 0.9, 4)
    short = df.iloc[:100]
    seen = _starts(monkeypatch)
    _same(zigzag_pivots(df, t, state=state), _old_zigzag(df, t))
    _same(zigzag_pivots(revised, t, state=state), _old_zigzag(revised, t))   # digest differs
    _same(zigzag_pivots(df, 7.0, state=state), _old_zigzag(df, 7.0))         # threshold differs
    _same(zigzag_pivots(short, t, state=state), _old_zigzag(short, t))       # state.m > len(frame)
    assert seen == [m, 1, 1, 1]


def test_empty_frames_and_prefixes():
    assert zigzag_pivots(_closes([]), 3.0) == []
    assert zigzag_prefix_state(FRAMES["walk"], 3.0, 0) is None
    assert zigzag_prefix_states(FRAMES["walk"], (3.0,), 0) is None


def test_prefix_states_are_frozen_pairs():
    df = FRAMES["walk"]
    states = zigzag_prefix_states(df, (2.0, 3.0), len(df) - 1)
    assert isinstance(states, tuple) and [t for t, _ in states] == [2.0, 3.0]
    state = states[0][1]
    assert isinstance(state.pivots, tuple) and isinstance(state.walk, tuple) and len(state.digest) == 16
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.m = 1
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_prefix_units.py`
Expected: FAIL at import — `ImportError: cannot import name 'zigzag_prefix_state'`.

- [ ] **Step 3: Split `zigzag_pivots` into a resumable walk**

In `swingbot/core/market/indicators.py`, add `import hashlib`,
`from dataclasses import dataclass` and `import numpy as np` (each only if
not already imported). `zigzag_pivots` keeps its docstring, which gains the
`state` paragraph. Its loop moves into `_zigzag_walk`, statement for
statement. The block below is today's loop copied from indicators.py. If
the source differs in anything but comments, the source wins: copy it, never
rewrite it.

```python
def zigzag_pivots(df: pd.DataFrame, threshold_pct: float, *, state: "ZigzagState | None" = None) -> list:
    """
    (existing docstring, unchanged, then:)

    ``state`` (v245): a ZigzagState from zigzag_prefix_state over a prefix of
    this frame's closes. The walk resumes after it when its threshold and its
    closes[:m] digest match; otherwise it starts at bar 0. Same list either way.
    """
    closes = df["Close"].values
    n = len(closes)
    if n == 0:
        return []
    return _zigzag_walk(closes, threshold_pct, _resume_carry(state, closes, threshold_pct), n)[1]


ZIGZAG_PREFIX_UNIT = "zigzag:horizons"   # v245 U2: structure.PREFIX_UNITS name of the horizon walks


@dataclass(frozen=True)
class ZigzagState:
    """zigzag_pivots' walk after closes[:m] (v245 U2). ``digest`` identifies
    closes[:m] exactly; ``walk`` = (start_idx, start_price, last_extreme_idx,
    last_extreme_price, direction)."""
    threshold_pct: float
    m: int
    digest: bytes
    pivots: tuple
    walk: tuple


def _closes_digest(closes, m: int) -> bytes:
    head = np.ascontiguousarray(closes[:m])
    return hashlib.blake2b(head.tobytes() + str(head.dtype).encode(), digest_size=16).digest()


def _fresh_carry(closes) -> tuple:
    """The walk before bar 1: (next index, pivots, *ZigzagState.walk)."""
    return (1, [], 0, closes[0], 0, closes[0], None)


def _resume_carry(state, closes, threshold_pct) -> tuple:
    """``state``'s walk when it was built on these closes at this threshold, else a fresh walk."""
    if state is None or state.threshold_pct != threshold_pct or not 1 <= state.m <= len(closes):
        return _fresh_carry(closes)
    if _closes_digest(closes, state.m) != state.digest:
        return _fresh_carry(closes)
    return (state.m, list(state.pivots), *state.walk)


def _zigzag_walk(closes, threshold_pct: float, carry: tuple, stop: int) -> tuple:
    """zigzag_pivots' loop from carry's next index up to ``stop`` (exclusive).
    ``pivots`` is always a fresh list, so no caller can mutate a cached state."""
    next_i, pivots, start_idx, start_price, last_extreme_idx, last_extreme_price, direction = carry
    for i in range(next_i, stop):
        price = closes[i]
        if last_extreme_price == 0:
            continue
        change_pct = (price - last_extreme_price) / last_extreme_price * 100

        if direction is None:
            if change_pct >= threshold_pct:
                # First confirmed move is up -- the starting point was a low.
                pivots.append((start_idx, start_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
            elif change_pct <= -threshold_pct:
                # First confirmed move is down -- the starting point was a high.
                pivots.append((start_idx, start_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "up":
            if price >= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (last_extreme_price - price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "down":
            if price <= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (price - last_extreme_price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
    return (max(next_i, stop), pivots, start_idx, start_price, last_extreme_idx, last_extreme_price, direction)


def zigzag_prefix_state(df: pd.DataFrame, threshold_pct: float, m: int) -> "ZigzagState | None":
    """The walk over df's first ``m`` closes, frozen; None for an empty prefix."""
    closes = df["Close"].values
    m = min(int(m), len(closes))
    if m < 1:
        return None
    _, pivots, *walk = _zigzag_walk(closes, threshold_pct, _fresh_carry(closes), m)
    return ZigzagState(threshold_pct, m, _closes_digest(closes, m), tuple(pivots), tuple(walk))


def zigzag_prefix_states(df: pd.DataFrame, thresholds, m: int) -> tuple | None:
    """((threshold, ZigzagState), ...) over df's first ``m`` closes; None for an empty prefix."""
    if min(int(m), len(df)) < 1:
        return None
    return tuple((t, zigzag_prefix_state(df, t, m)) for t in thresholds)
```

- [ ] **Step 4: Run the test, the golden and the other callers**

```bash
python scripts/dev/testrun.py file tests/market/test_prefix_units.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py changed
```

Expected: all PASS, `0 failed`, `0 xfailed`; the golden unchanged. `changed`
selects the tests that reach `zigzag_pivots`' other callers. They pass no
`state`, so they take the walk from bar 0.

- [ ] **Step 5: Complexity gate**

```bash
python scripts/dev/complexity_gate.py
python -m radon cc -s swingbot/core/market/indicators.py | grep -E "zigzag|_resume_carry"
```

Expected: passes. `_zigzag_walk` is about 12 (today's `zigzag_pivots` minus
its empty check), `zigzag_pivots` 2, `_resume_carry` about 5,
`zigzag_prefix_state` 2.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/indicators.py tests/market/test_prefix_units.py
git add scripts/dev/complexity_baseline.json   # only if Step 5 shrank it with --update
git commit -m "perf(v245): zigzag_pivots resumes from a verified prefix walk (V245-11, U2)"
```

### Task V245-11b: Register the unit and wire its consumer (horizon zigzag states join the prefix cache)

**Model:** sonnet — mechanical wiring with exact code; the byte-identity reasoning was settled in V245-11, and the golden, wiring and property tests guard it.

**Skip this task** if V245-11 recorded the no-op ("none beyond U1"). If
V245-11 built another unit, register and wire that unit the same way: one
`PrefixUnit`, a consumer reading `prefix_results.get(<name>)` with a direct
computation on `None`, the Step 1 tests adapted, and Steps 5–7 unchanged.

**What changes.** `structure.PREFIX_UNITS` gains the unit
`zigzag:horizons`. Its value holds every horizon threshold's
`ZigzagState` in one frozen tuple, so there is one entry per ticker. The key
is the prefix fingerprint (`m = len(df) - 1`) plus the threshold tuple, so a
changed `max_risk_pct` is a miss. `_horizon_scenarios` hands the ticker's
`prefix_results` to `collect_candidate_levels`, whose zigzag line resumes
from the carried state. `rescenario` gets the same values from
`ScanItem.prefix_results` (V245-9), so it never looks the cache up. Entries
per ticker go from 2 to 3, and Step 7 checks that against the doc's
`## Cache size`.

**Files:**
- Modify: `swingbot/core/market/levels.py` (import :71; `_horizon_pivots` above `collect_candidate_levels` :198; its signature; the zigzag line :276)
- Modify: `swingbot/core/scanning/analyze.py` (`_horizon_scenarios`: pass `prefix_results` on; docstring)
- Modify: `swingbot/core/scanning/structure.py` (the unit)
- Modify: `tests/market/test_prefix_units.py` (append three tests)
- Modify: `tests/scanning/test_analysis_cache_wiring.py` (three unit-count assertions)
- Modify: `docs/superpowers/results/2026-11-23-v245-analysis-profile.md` (U2 verdict, entries per ticker)

**Interfaces:**
- Consumes: V245-11 `ZIGZAG_PREFIX_UNIT`, `zigzag_pivots(..., state=)`, `zigzag_prefix_states(df, thresholds, m)`, test helpers `_old_zigzag`, `_same`, `FRAMES`; V245-7 `prefix_fingerprint`, `StructureCache`; V245-9 `PrefixUnit(name, build)` (`build(df) -> (fingerprint, builder)`), `PREFIX_UNITS`, `ticker_prefixes`, `TRENDLINE_UNITS`, `_horizon_scenarios(..., prefix_results=)` (accepted, unused until now); V245-5's memo line at levels.py:276 if V245-5 built it; V245-1 `CASE_BY_NAME`; V245-10's property test.
- Produces (ledger: appends to `structure.PREFIX_UNITS`): `levels.collect_candidate_levels(df, h, current_price, trendline_candidates=None, params=None, prefix_results: dict | None = None)`; `levels._horizon_pivots(df, threshold_pct, prefix_results) -> list`; `structure.ZIGZAG_TAIL_BARS = 1`; unit name `"zigzag:horizons"` in `PREFIX_UNITS`. V245-13/14 compare whatever `PREFIX_UNITS` holds; nothing else depends on the name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/market/test_prefix_units.py` (add `levels` to the
`swingbot.core.market` import, `ZIGZAG_PREFIX_UNIT` to the indicators import,
`LEGACY_HORIZONS` to the strategy_types import, and these imports):

```python
from swingbot.core.scanning import structure
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.v245_golden_cases import CASE_BY_NAME


def test_horizon_pivots_reads_the_carried_state(monkeypatch):
    df, t = FRAMES["walk"], HORIZONS["4w"]["max_risk_pct"]
    states = zigzag_prefix_states(df, (t,), len(df) - 1)
    seen, real = [], levels.zigzag_pivots

    def spy(frame, threshold_pct, state=None):
        seen.append(state)
        return real(frame, threshold_pct, state=state)

    monkeypatch.setattr(levels, "zigzag_pivots", spy)
    for carried in ({ZIGZAG_PREFIX_UNIT: states}, None, {}):
        _same(levels._horizon_pivots(df, t, carried), _old_zigzag(df, t))
    assert seen == [states[0][1], None, None]


@pytest.mark.parametrize("case", ["wave_forming", "long_completed"])
def test_collect_candidate_levels_is_unchanged_with_prefix_results(case):
    df = CASE_BY_NAME[case].frame()
    values = structure.ticker_prefixes(StructureCache(10), "T", df)
    assert ZIGZAG_PREFIX_UNIT in values
    price = float(df["Close"].iloc[-1])
    for key in LEGACY_HORIZONS:
        h = HORIZONS[key]
        assert levels.collect_candidate_levels(df, h, price, prefix_results=values) == \
            levels.collect_candidate_levels(df, h, price)


def test_the_unit_is_registered_and_keyed_by_the_thresholds(monkeypatch):
    unit = next(u for u in structure.PREFIX_UNITS if u.name == ZIGZAG_PREFIX_UNIT)
    df = CASE_BY_NAME["wave_forming"].frame()
    key, build = unit.build(df)
    assert key[-1] == tuple(sorted({h["max_risk_pct"] for h in HORIZONS.values()}))
    assert key[:-1] == structure.prefix_fingerprint(df, len(df) - structure.ZIGZAG_TAIL_BARS)
    assert {t for t, _ in build()} == set(key[-1])
    monkeypatch.setitem(HORIZONS["4w"], "max_risk_pct", 4.25)
    assert unit.build(df)[0] != key
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_prefix_units.py`
Expected: the three new tests FAIL (`AttributeError: ... '_horizon_pivots'`,
`TypeError: ... unexpected keyword argument 'prefix_results'`, `StopIteration`);
V245-11's tests still pass.

- [ ] **Step 3: Levels read the carried state; `_horizon_scenarios` passes it**

`swingbot/core/market/levels.py`: extend the indicators import (:71) with
`ZIGZAG_PREFIX_UNIT`, and add above `collect_candidate_levels`:

```python
def _horizon_pivots(df, threshold_pct, prefix_results: dict | None) -> list:
    """zigzag_pivots at a horizon's threshold, resumed from the ticker's cached
    prefix walk when one is carried (v245 U2); the same list either way."""
    states = dict((prefix_results or {}).get(ZIGZAG_PREFIX_UNIT) or ())
    return zigzag_pivots(df, threshold_pct=threshold_pct, state=states.get(threshold_pct))
```

`collect_candidate_levels`' signature gains
`prefix_results: dict | None = None` after `params=None`. Its docstring gains
one line: "`prefix_results` (v245): the ticker's prefix-cache values; only
the horizon zigzag reads them; None walks it from bar 0." At :276, replace
the expression `zigzag_pivots(df, threshold_pct=h["max_risk_pct"])` with
`_horizon_pivots(df, h["max_risk_pct"], prefix_results)`. If V245-5 built
the memo, the expression sits inside the
`frame_memo.memo(df, ("zigzag", h["max_risk_pct"]), lambda: ...)` lambda;
replace it there and keep the memo (the carried state is constant within one
`_scan_one`). That adds no branch: the function stays at 42.

`swingbot/core/scanning/analyze.py` `_horizon_scenarios`: the
`levels.collect_candidate_levels(...)` call gains
`prefix_results=prefix_results`, and the docstring's last sentence becomes
"Trendline units are consumed once per ticker in `_scan_one`; the horizon
zigzag states here."

- [ ] **Step 4: Register the unit**

`swingbot/core/scanning/structure.py`: change the market import to
`from swingbot.core.market import indicators, trendlines`, add
`from swingbot.core.market.strategy_types import HORIZONS`, and below
`PREFIX_UNITS`:

```python
ZIGZAG_TAIL_BARS = 1     # the zigzag walk resumes from its state: only the last row is per scan


def _horizon_thresholds() -> tuple:
    """Every horizon's zigzag threshold (levels' "Pivot high/low" source), read per build."""
    return tuple(sorted({h["max_risk_pct"] for h in HORIZONS.values()}))


def _zigzag_build(df):
    thresholds = _horizon_thresholds()
    m = max(len(df) - ZIGZAG_TAIL_BARS, 0)
    return (prefix_fingerprint(df, m) + (thresholds,),
            lambda: indicators.zigzag_prefix_states(df, thresholds, m))


PREFIX_UNITS = PREFIX_UNITS + (PrefixUnit(indicators.ZIGZAG_PREFIX_UNIT, _zigzag_build),)
```

The raw `max_risk_pct` values are used, never `float(...)`, so the
threshold lookup in `_horizon_pivots` sees exactly the key levels passes.

- [ ] **Step 5: V245-9's wiring test counts every unit, not two**

In `tests/scanning/test_analysis_cache_wiring.py`:

- rename `test_a_warm_scan_hits_both_trendline_units` to `test_a_warm_scan_hits_every_unit`, and make its assertion `assert cache.stats()["cache_hits"] == len(structure.PREFIX_UNITS) and cache.stats()["cache_misses"] == 0`;
- in `test_a_failing_prefix_build_warns_and_computes_uncached`, change `cache.stats()["cache_entries"] == 0` to `cache.stats()["cache_entries"] == len(structure.PREFIX_UNITS) - len(structure.TRENDLINE_UNITS)` (only the trendline build is broken there);
- in `test_items_carry_prefix_results_and_rescenario_never_looks_up`, change the first assertion to `assert set(cached_items[0].prefix_results) == {unit.name for unit in structure.PREFIX_UNITS}`.

- [ ] **Step 6: Run the tests, the golden, the property test and the neighbours**

```bash
python scripts/dev/testrun.py file tests/market/test_prefix_units.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_property.py
python scripts/dev/testrun.py file tests/scanning/test_rescenario.py
python scripts/dev/testrun.py changed
python scripts/dev/complexity_gate.py
```

Expected: all PASS, `0 failed`, `0 xfailed`, golden unchanged. The property
test now carries the zigzag unit too: `test_revision_behind_an_unchanged_fingerprint`
proves its digest check. The gate passes, with `collect_candidate_levels`
still at 42 and `_horizon_pivots` at 3.

- [ ] **Step 7: Record in the doc and commit**

In the results doc's `## Prefix-pure units` table, set U2's verdict to
`built in V245-11/11b (unit zigzag:horizons, one entry per ticker)`. Under
`## Cache size`, add the line
`Entries per ticker after V245-11b: 3 (two trendline sides + zigzag:horizons); 92 tickers = 276 entries.`
If the recommended `STRUCTURE_CACHE_MAX` there is below 276, the live cache
would evict every scan. In that case do not commit: report it to the
controller as the open question (raise the cap or drop the unit).

```bash
git add swingbot/core/market/levels.py swingbot/core/scanning/analyze.py tests/market/test_prefix_units.py
git commit -m "perf(v245): level maps resume the horizon zigzag from carried prefix states (V245-11b)"
git add swingbot/core/scanning/structure.py tests/scanning/test_analysis_cache_wiring.py docs/superpowers/results/2026-11-23-v245-analysis-profile.md
git commit -m "perf(v245): zigzag:horizons joins the prefix cache, one entry per ticker (V245-11b)"
```

### Task V245-12: Cache telemetry — `cache_*`, `phases_s.analysis_prefix`, `rss_mb`, summary line

**Model:** sonnet — small helpers plus four branch-free edits in `_sync_run_scan`; the shape is fixed by the spec and by V245-6's reader.

Spec § Observability. Each scan row in `scan_telemetry.jsonl` gains
`cache_mode`, `cache_hits`, `cache_misses`, `cache_evictions`,
`cache_entries` and `rss_mb`. `phases_s` gains `analysis_prefix`, and the
INFO `Scan pass:` line ends with the hit and miss counts. V245-6's
`scripts/perf/analysis_phase_report.py` already reads `cache_hits`,
`cache_misses`, `rss_mb` and `phases_s.analysis_prefix` with `.get` and
treats non-numbers as absent, so the keys and types below are its contract.

**Decisions this task fixes (spec silent):**
- **Per-scan counters.** The base lane zeroes the cache's counters and build timer at the start of its analysis phase (`_start_analysis_cache`). The row therefore reports this scan's base-lane analysis. The SHORT lane keeps calling `_analysis_cache()`, which never resets, so a SHORT-lane hit that lands after the row is written is cleared by the next scan's reset and is never reported twice.
- **`analysis_prefix` is a sub-total of `analysis`**, written by hand right after `_finish_phase("analysis")` (not through `_finish_phase`, which would move the phase clock). Nothing in the repo sums `phases_s` (`git grep -n "phases_s"` finds only the writer), so it cannot be double-counted. It is `0.0` with no cache.
- **No cache (`off`)**: the counters are `None`, not `0`, so a report never mistakes "off" for "0 % hit rate". `rss_mb` is measured in every mode.
- **The summary line** is the existing `Scan pass:` INFO line (scan_run.py:967) with `; analysis cache <mode>[: N hit(s), M miss(es)]` appended. Its start is unchanged for ops greps, and no test pins its text.

**Complexity:** `_sync_run_scan` is at 94 and must not grow. Every
conditional lives in the new helpers; the four edits inside `_sync_run_scan`
are a call swap, one assignment, one log argument and one `**` entry.

**Files:**
- Modify: `swingbot/core/scanning/structure.py` (`rss_mb`)
- Modify: `swingbot/core/scanning/scan_run.py` (helpers next to `_analysis_cache`; `_sync_run_scan` at the call site ~753, after `_finish_phase("analysis")` ~760, the `Scan pass:` line ~967, the telemetry dict ~1343-1360)
- Create: `tests/scanning/test_analysis_cache_telemetry.py`

**Interfaces:**
- Consumes: V245-7 `StructureCache.stats()` (`cache_hits, cache_misses, cache_evictions, cache_entries`), `reset_counters()` (also zeroes `prefix_build_s`), `prefix_build_s`; V245-9 `scan_run._analysis_cache() -> (mode, cache)` and the lines it added at the call site (`cache_mode, analysis_cache = _analysis_cache()`, `scan_now`, the lambda's `structure=analysis_cache, now=scan_now`); `tests/scanning/test_mtf_gate._scan_with_funnel(direction)`; `tests.store_seed.seed_store`; V245-6's report keys.
- Produces (ledger): `structure.rss_mb(status_path: str = "/proc/self/status") -> float | None`; `scan_run._cache_telemetry(mode: str, cache) -> dict` (`cache_mode, cache_hits, cache_misses, cache_evictions, cache_entries, rss_mb`). Also `scan_run._start_analysis_cache() -> tuple[str, StructureCache | None]` (the base lane's call at the analysis start: **V245-14's `_AnalysisCtx` must be built from it, not from `_analysis_cache()`**), `scan_run._analysis_prefix_s(cache) -> float`, `scan_run._cache_summary(mode, cache) -> str`, `scan_run._CACHE_COUNTERS`.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_analysis_cache_telemetry.py`:

```python
"""v245 V245-12: analysis-cache telemetry -- cache_* counters,
phases_s.analysis_prefix, rss_mb and the Scan pass summary."""
import logging
import sys

import pytest

from swingbot import config
from swingbot.core.scanning import scan_run, structure, telemetry
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.store_seed import seed_store

COUNTERS = ("cache_hits", "cache_misses", "cache_evictions", "cache_entries")


def test_rss_mb_reads_vmrss_in_megabytes(tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmPeak:\t  999999 kB\nVmRSS:\t  409600 kB\nThreads:\t4\n",
                      encoding="ascii")
    assert structure.rss_mb(str(status)) == 400.0


@pytest.mark.parametrize("body", ["Name:\tpython\n", "VmRSS:\tlots kB\n", "VmRSS:\n"])
def test_rss_mb_is_none_without_a_readable_vmrss(tmp_path, body):
    status = tmp_path / "status"
    status.write_text(body, encoding="ascii")
    assert structure.rss_mb(str(status)) is None


def test_rss_mb_is_none_where_the_file_is_missing(tmp_path):
    assert structure.rss_mb(str(tmp_path / "missing")) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc/self/status is Linux-only")
def test_rss_mb_reads_this_process_on_linux():
    value = structure.rss_mb()
    assert isinstance(value, float) and value > 0


def _warm(cache: StructureCache) -> StructureCache:
    cache.put(("T", "u", (1,)), ("v",))
    cache.get(("T", "u", (1,)))          # one hit
    cache.get(("T", "u", (2,)))          # one miss
    return cache


def test_cache_telemetry_with_a_cache(monkeypatch):
    monkeypatch.setattr(structure, "rss_mb", lambda: 321.5)
    assert scan_run._cache_telemetry("on", _warm(StructureCache(5))) == {
        "cache_mode": "on", "cache_hits": 1, "cache_misses": 1, "cache_evictions": 0,
        "cache_entries": 1, "rss_mb": 321.5}


def test_cache_telemetry_without_a_cache(monkeypatch):
    monkeypatch.setattr(structure, "rss_mb", lambda: None)
    assert scan_run._cache_telemetry("off", None) == {
        "cache_mode": "off", **dict.fromkeys(COUNTERS), "rss_mb": None}


def test_start_resets_the_counters_and_the_build_timer(monkeypatch):
    cache = _warm(StructureCache(5))
    cache.prefix_build_s = 1.5
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("on", cache))
    assert scan_run._start_analysis_cache() == ("on", cache)
    assert cache.stats() == {"cache_hits": 0, "cache_misses": 0, "cache_evictions": 0, "cache_entries": 1}
    assert cache.prefix_build_s == 0.0


def test_start_without_a_cache(monkeypatch):
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("off", None))
    assert scan_run._start_analysis_cache() == ("off", None)


def test_analysis_prefix_seconds():
    cache = StructureCache(5)
    cache.prefix_build_s = 0.12345
    assert scan_run._analysis_prefix_s(cache) == 0.123
    assert scan_run._analysis_prefix_s(None) == 0.0


def test_cache_summary_text():
    assert scan_run._cache_summary("shadow", _warm(StructureCache(5))) == \
        "analysis cache shadow: 1 hit(s), 1 miss(es)"
    assert scan_run._cache_summary("off", None) == "analysis cache off"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


def _rows(monkeypatch) -> list:
    rows: list = []
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    monkeypatch.setattr(telemetry, "scan_slowdown", lambda *args, **kwargs: False)
    return rows


def test_scan_rows_carry_the_cache_fields_cold_then_warm(data_dir, monkeypatch, caplog):
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", StructureCache(50))
    monkeypatch.setattr(config, "ANALYSIS_CACHE", "on")
    rows = _rows(monkeypatch)
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        _scan_with_funnel("bullish")
        _scan_with_funnel("bullish")             # same frame: every unit hits
    assert len(rows) == 2, caplog.text           # a swallowed telemetry error shows up here
    cold, warm = rows
    assert cold["cache_mode"] == "on" and cold["cache_hits"] == 0 and cold["cache_misses"] > 0
    assert (warm["cache_hits"], warm["cache_misses"]) == (cold["cache_misses"], 0)
    assert warm["cache_entries"] == cold["cache_entries"] > 0
    assert cold["phases_s"]["analysis_prefix"] >= 0.0 and warm["phases_s"]["analysis_prefix"] == 0.0
    assert "rss_mb" in warm and "analysis" in warm["phases_s"]
    assert "analysis cache on: 0 hit(s)" in caplog.text
    assert f"analysis cache on: {cold['cache_misses']} hit(s), 0 miss(es)" in caplog.text


def test_scan_rows_without_a_cache(data_dir, monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_CACHE", "off")
    rows = _rows(monkeypatch)
    _scan_with_funnel("bullish")
    (row,) = rows
    assert row["cache_mode"] == "off" and all(row[key] is None for key in COUNTERS)
    assert row["phases_s"]["analysis_prefix"] == 0.0
```

- [ ] **Step 2: Run it to make sure it fails**

`_scan_with_funnel` runs a real `_sync_run_scan`, whose telemetry block
reads open trades from the local Postgres. Run `/replicate-prod-db` first
unless a sibling task in this session already did (CLAUDE.md).

Run: `python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_telemetry.py`
Expected: FAIL — `AttributeError: module ... 'structure' has no attribute 'rss_mb'`,
`... 'scan_run' has no attribute '_cache_telemetry'`, and the two scan-row
tests fail on `KeyError: 'cache_mode'`.

- [ ] **Step 3: `rss_mb` in `structure.py`**

Append to `swingbot/core/scanning/structure.py`:

```python
def rss_mb(status_path: str = "/proc/self/status") -> float | None:
    """This process's resident memory in MB (``VmRSS`` kB / 1024, one decimal);
    None where the file or the line is missing or unreadable (Windows, macOS)."""
    try:
        with open(status_path, encoding="ascii", errors="replace") as handle:
            line = next((row for row in handle if row.startswith("VmRSS:")), None)
        return None if line is None else round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None
```

- [ ] **Step 4: Helpers in `scan_run.py`**

Below `_analysis_cache` in `swingbot/core/scanning/scan_run.py`:

```python
_CACHE_COUNTERS = ("cache_hits", "cache_misses", "cache_evictions", "cache_entries")


def _start_analysis_cache() -> tuple[str, "analysis_structure.StructureCache | None"]:
    """The base lane's `_analysis_cache()` at the start of its analysis phase:
    counters and the build timer restart at zero, so the telemetry row reports
    this scan only (v245 V245-12). The SHORT lane keeps `_analysis_cache()`."""
    mode, cache = _analysis_cache()
    if cache is not None:
        cache.reset_counters()
    return mode, cache


def _analysis_prefix_s(cache) -> float:
    """Seconds the analysis phase spent building cache entries; 0.0 without a cache."""
    return round(cache.prefix_build_s, 3) if cache is not None else 0.0


def _cache_summary(mode: str, cache) -> str:
    """The analysis-cache clause of the INFO "Scan pass:" line."""
    if cache is None:
        return f"analysis cache {mode}"
    counts = cache.stats()
    return f"analysis cache {mode}: {counts['cache_hits']} hit(s), {counts['cache_misses']} miss(es)"


def _cache_telemetry(mode: str, cache) -> dict:
    """scan_telemetry fields (v245 V245-12): the mode, the counters since the
    scan start (None without a cache) and the bot's resident memory now."""
    counters = cache.stats() if cache is not None else dict.fromkeys(_CACHE_COUNTERS)
    return {"cache_mode": mode, **counters, "rss_mb": analysis_structure.rss_mb()}
```

- [ ] **Step 5: Four branch-free edits in `_sync_run_scan`**

1. At the call site (~753), V245-9's line becomes
   `cache_mode, analysis_cache = _start_analysis_cache()`.
2. Directly below `_finish_phase("analysis")` (~760):

   ```python
       phase_durations["analysis_prefix"] = _analysis_prefix_s(analysis_cache)   # v245: a sub-total of "analysis"
   ```

3. The `Scan pass:` line (~967) becomes:

   ```python
       log.info("Scan pass: %d ticker(s) evaluated, %d scenario(s) shown, %d after dedup; %s",
                 len(tickers), len(scan_items), len(deduped), _cache_summary(cache_mode, analysis_cache))
   ```

4. In the telemetry dict (~1358), after `**_rebuild_stats(requote),` add
   `**_cache_telemetry(cache_mode, analysis_cache),`.

- [ ] **Step 6: Run the tests and the neighbours**

```bash
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_telemetry.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/scripts/test_analysis_phase_report.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. If
`test_scan_rows_carry_the_cache_fields_cold_then_warm` reports
`len(rows) == 0`, the telemetry block swallowed an error: its caplog shows
`Scan health telemetry failed` with the cause (usually the local database
not running). Fix the environment, never the assertion.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes; `_sync_run_scan` stays at 94; each new helper ≤ 3; `rss_mb` ≤ 4.

- [ ] **Step 8: Commit (two scoped commits)**

```bash
git add swingbot/core/scanning/structure.py
git commit -m "feat(v245): rss_mb gauge from /proc/self/status (V245-12)"
git add swingbot/core/scanning/scan_run.py tests/scanning/test_analysis_cache_telemetry.py
git commit -m "feat(v245): scan telemetry carries cache counters, analysis_prefix and rss_mb (V245-12)"
```

