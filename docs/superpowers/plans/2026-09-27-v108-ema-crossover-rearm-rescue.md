# v108 — EMA Crossover re-arm rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`](../specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md)
**Bump:** `none` for Phases A–B (the code ships inert); `bot minor` only if V108-8's PASS path ships a K > 1 (the alert stream gains entries; the badge may flip)
**Edge:** volume

**Goal:** Let EMA Crossover's pullback entry take the first K touch *events* after each held cross instead of only the first touch, then measure K ∈ {2, 3} per direction through v103's funnel and ship a K only when the pre-registered stages clear.

**Architecture:** The nested `_first_touch_after` in `ema_cross_entries` becomes a module-level numpy helper `_touch_events_after(cross, touch, window, max_touches)`. Its K comes from two new `DEFAULT_PARAMS["EMA Crossover"]` keys, `max_touches_bull` and `max_touches_bear`, both defaulting to `1`, which reproduces today's entries bit-for-bit. The v103 harness `scripts/backtest/measure_fib_v103.py` gains mechanism `E`. It sets only the scored direction's knob and adds a Stage 0 "mechanism inert" closure. `scripts/backtest/fib_funnel.py` is reused unchanged.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, the v103 funnel (`fib_funnel.py`, `measure_fib_v103.py`), and the extended OHLCV cache `data/backtest_cache_ext`.

## Global Constraints

Copied from the spec. Every task's requirements include this section.

- Param names: `max_touches_bull` and `max_touches_bear` in `DEFAULT_PARAMS["EMA Crossover"]`, both default **`1`**. At `1`/`1`, entries are identical to today's.
- A touch event is a bar that satisfies the existing touch mask while the previous bar did not. A run of consecutive touching bars is **one** event. **K=1 parity rule:** the first touching bar inside a cross's window always opens an event, even when the cross bar itself touched.
- These stay unchanged: `pullback_max_bars = 15`, all ten ANDed filters, the stop/target arithmetic, and the absence of a `STRATEGY_GATES["EMA Crossover"]` entry. No cooldown knob is added.
- No lookahead: a touch event at bar `j` reads bars `<= j` only (the cross at `ci < j`, the touch mask at `j` and `j-1`).
- Mechanism `E` uses grid **`K ∈ {2, 3}`**, loosest **`K=3`**, and reference **`K=1`**. The reference is reported but can never win.
- Stage 0 closes a direction if (1) the `K=3` TRAIN_EXT signal count is `< 30` (`MIN_N_TRAIN`), or (2) the `K=3` count is `< 1.15 ×` the `K=1` count (**mechanism inert**).
- Windows: `TRAIN_EXT = 2010-01-01..2023-12-31`, `FOLD_YEARS = 2013..2023` (anchored at 2010), `VALIDATION = 2024-01-01..2025-12-31`.
- Arithmetic: `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`, `frictions=True`, `one_at_a_time=True`, level lifecycle as today. All ten horizons are pooled. Directions are scored separately, each as live today.
- Tier 1 = WR ≥ 50, ExpR > 0, N ≥ 30 (≥ 15 on VALIDATION), scratch+timeout share ≤ 0.5. Tier 2 = ExpR > 0 and ticker-cluster bootstrap lower bound > 0, with the same floors. **Only a Tier 1 winner can earn `VALIDATED`.**
- Universe: the 77-name production watchlist, passed via `--tickers`. It must give `universe_n == 73` after the liquidity filter. **A run with any other `universe_n` is discarded.**
- Cache: **every** measurement command sets `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext` (absolute main-tree path; the directory is git-ignored and does not exist in a worktree).
- The pre-registration is committed **before the first `count` run** and before any `collect`. After that commit, no threshold, grid value or window may change.
- **One VALIDATION shot per direction**, ever.
- The 2026-07 VALIDATION read of the pullback entry (N=36, WR 75.0%, deleted fixed R:R table) is never consulted for any choice.
- Every function written or changed stays at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`).
- Never `cd` in Bash. Every command runs from the root of the tree the task names.

## Parallelisation

- **Group 1 (parallel): V108-1 and V108-2.** V108-1 touches `swingbot/core/market/entry_filters.py` and `tests/market/test_ema_rearm.py`. V108-2 touches `scripts/backtest/measure_fib_v103.py` and `tests/scripts/test_measure_fib_v103.py`. The files are disjoint. There is no contract dependency either: the harness uses only the param *names*, which this spec fixes, and V108-2's tests pin those keys with `monkeypatch.setitem`, so they pass whether or not V108-1 has landed. Both run on the same worktree branch, and each task stages only its own two files.
- **Sequential, from here on:**
  - V108-3 comes after Group 1. It runs the real-data K=1 parity check through both tasks' code, then merges to `main`.
  - V108-4 comes after V108-3. The pre-registration names the merged commit, and it must be committed before any measurement.
  - V108-5 → V108-6 → V108-7 run strictly in order. Stage 0 decides which directions Stage 1 collects; the committed Stage 1–2 evaluate JSON is `validation`'s required input; each stage gates the next.
  - V108-8 comes after the verdict, because its path (PASS wiring or NO-LIFT close-out) is the verdict.
  - V108-9 runs last: the one full-suite run, then the bump and the document move.

## Conventions for every task

- **Phase A** runs in the worktree `.claude/worktrees/2026-09-27-v108-ema-crossover-rearm-rescue` on branch `2026-09-27-v108-ema-crossover-rearm-rescue` (`worktree-lifecycle` skill). **Phases B–C** run in the main tree on `main`, after V108-3's merge. V108-8's PASS path uses its own short worktree.
- `<date>` is the run date (`YYYY-MM-DD`). Pick it once in V108-4 and reuse it in every file name. Result files live under `docs/superpowers/results/`.
- `$CACHE` in this plan always means the literal prefix `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`. Type it out in full. Shell state does not persist between calls.
- `--tickers "$(cat docs/superpowers/results/<date>-v108-universe.txt)"` is how every measurement command passes the universe. V108-4 creates that file.
- Stage by explicit path, commit with a pathspec, and check `git log --oneline -3` first: another session may have committed on `main`. Never `git add -A`, `git add data/`, or `git add .`.
- Load `backtest-gate` before every measurement command (V108-5, 6, 7). Load `pooled-numbers` before writing any N / WR / ExpR figure. Every figure carries its N and window, and comes from a JSON this plan wrote, never from memory.
- Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

# Phase A — Code (worktree branch)

### Task V108-1: Touch-event re-arm in `ema_cross_entries`

Load the `no-lookahead` and `edge-module` skills first.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (the `DEFAULT_PARAMS["EMA Crossover"]` block at ~line 440, and `ema_cross_entries` at line 454 with its nested `_first_touch_after` at line 472)
- Create: `tests/market/test_ema_rearm.py`

**Interfaces:**
- Consumes: `tests.market.test_rescue_ema._cross_then_pullback()` (existing fixture, 292 bars, one 4w bullish entry under defaults) and `tests.conftest.make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01")`.
- Produces:
  - `entry_filters._touch_events_after(cross: np.ndarray[bool], touch: np.ndarray[bool], window: int, max_touches: int) -> np.ndarray[bool]`, which raises `ValueError` when `max_touches < 1`.
  - `entry_filters._pullback_entries(cross: pd.Series, touch: pd.Series, window: int, max_touches: int) -> pd.Series[bool]`.
  - `DEFAULT_PARAMS["EMA Crossover"]["max_touches_bull"] == 1` and `["max_touches_bear"] == 1`.
  - V108-2 depends on the key names only. V108-8 changes the values.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_ema_rearm.py`:

```python
"""v108: EMA Crossover re-arm -- the first K pullback touch *events* per held cross.

A touch event is a touching bar whose previous bar did not touch; the first
touching bar inside a cross's window always opens one (K=1 parity with the
pre-v108 first-touch rule, including when the cross bar itself touched).
"""
import math

import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS
from tests.conftest import make_ohlcv
from tests.market.test_rescue_ema import _cross_then_pullback

WINDOW = 15


def _legacy_first_touch(cross, touch, window):
    """The pre-v108 nested `_first_touch_after`, verbatim in logic: first touch only."""
    out = np.zeros(len(touch), dtype=bool)
    for ci in np.flatnonzero(cross):
        for j in range(ci + 1, min(ci + 1 + window, len(touch))):
            if touch[j]:
                out[j] = True
                break
    return out


def _mask(n, *on):
    mask = np.zeros(n, dtype=bool)
    mask[list(on)] = True
    return mask


def _hits(cross, touch, window=WINDOW, k=1):
    return np.flatnonzero(ef._touch_events_after(cross, touch, window, k)).tolist()


def _multi_cross():
    """Gentle uptrend plus a 45-bar sine: 16 held bullish crosses on 4w."""
    closes = [100 * 1.0006 ** i + 6 * math.sin(2 * math.pi * i / 45) for i in range(700)]
    return make_ohlcv(closes, spread_pct=2.0)


def _held_bull_crosses(df, horizon_key):
    h = HORIZONS[horizon_key]
    diff = ema(df["Close"], h["ema_fast"]) - ema(df["Close"], h["ema_slow"])
    return int(((diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)).sum())


# --- the pure helper ---------------------------------------------------------

def test_k1_equals_legacy_first_touch_on_random_masks():
    rng = np.random.default_rng(108)
    for _ in range(2000):
        cross = rng.random(60) < 0.08
        touch = rng.random(60) < 0.4
        assert np.array_equal(ef._touch_events_after(cross, touch, WINDOW, 1),
                              _legacy_first_touch(cross, touch, WINDOW))


def test_cross_bar_touch_still_opens_the_first_event():
    # The K=1 parity trap: the cross bar (0) touches and the run carries into
    # the window. Bar 1's predecessor touched, yet bar 1 must open an event.
    cross, touch = _mask(20, 0), _mask(20, 0, 1, 2)
    assert _hits(cross, touch, k=1) == [1]
    assert _hits(cross, touch, k=3) == [1]


def test_consecutive_touching_bars_are_one_event():
    cross, touch = _mask(20, 0), _mask(20, 2, 3, 4, 7)
    assert _hits(cross, touch, k=2) == [2, 7]
    assert _hits(cross, touch, k=3) == [2, 7]


def test_k_caps_the_event_count():
    cross, touch = _mask(20, 0), _mask(20, 2, 4, 6, 8)
    assert _hits(cross, touch, k=1) == [2]
    assert _hits(cross, touch, k=2) == [2, 4]
    assert _hits(cross, touch, k=3) == [2, 4, 6]


def test_touches_past_the_window_are_ignored():
    # window=5 after a cross at 0 covers bars 1..5; bar 7 is outside.
    cross, touch = _mask(20, 0), _mask(20, 3, 5, 7)
    assert _hits(cross, touch, window=5, k=3) == [3, 5]


def test_a_new_cross_resets_the_count():
    cross, touch = _mask(30, 0, 6), _mask(30, 2, 4, 8, 10)
    assert _hits(cross, touch, k=1) == [2, 8]
    assert _hits(cross, touch, k=2) == [2, 4, 8, 10]


def test_max_touches_below_one_is_rejected():
    with pytest.raises(ValueError):
        ef._touch_events_after(_mask(5, 0), _mask(5, 1), WINDOW, 0)


def test_helper_truncation_never_changes_an_earlier_event():
    rng = np.random.default_rng(7)
    cross = rng.random(80) < 0.1
    touch = rng.random(80) < 0.4
    full = ef._touch_events_after(cross, touch, WINDOW, 3)
    for cut in range(1, 81):
        part = ef._touch_events_after(cross[:cut], touch[:cut], WINDOW, 3)
        assert np.array_equal(part, full[:cut]), cut


# --- wired into ema_cross_entries ---------------------------------------------

def test_fixtures_exercise_several_crosses_and_a_real_entry():
    assert _held_bull_crosses(_multi_cross(), "4w") >= 3
    assert ef.ema_cross_entries(_cross_then_pullback(), "4w")[0].any()


@pytest.mark.parametrize("fixture", [_cross_then_pullback, _multi_cross])
def test_default_entries_identical_to_the_legacy_path(monkeypatch, fixture):
    df = fixture()
    new = {hk: ef.ema_cross_entries(df, hk) for hk in HORIZONS}
    monkeypatch.setattr(ef, "_touch_events_after",
                        lambda cross, touch, window, max_touches: _legacy_first_touch(cross, touch, window))
    old = {hk: ef.ema_cross_entries(df, hk) for hk in HORIZONS}
    for hk in HORIZONS:
        assert new[hk][0].equals(old[hk][0]) and new[hk][1].equals(old[hk][1]), hk


def test_each_direction_gets_its_own_k(monkeypatch):
    seen = []

    def spy(cross, touch, window, max_touches):
        seen.append((window, max_touches))
        return np.zeros(len(touch), dtype=bool)

    monkeypatch.setattr(ef, "_touch_events_after", spy)
    ef.ema_cross_entries(_multi_cross(), "4w", params={"max_touches_bull": 3, "max_touches_bear": 2})
    assert seen == [(15, 3), (15, 2)]


def test_cross_mode_ignores_max_touches():
    df = _cross_then_pullback()
    base = {"entry_mode": "cross"}
    a = ef.ema_cross_entries(df, "4w", params=base)
    b = ef.ema_cross_entries(df, "4w", params={**base, "max_touches_bull": 3, "max_touches_bear": 3})
    assert a[0].equals(b[0]) and a[1].equals(b[1])


def test_frame_truncation_never_changes_an_earlier_entry():
    df = _cross_then_pullback()
    params = {"max_touches_bull": 3, "max_touches_bear": 3}
    full_bull, full_bear = ef.ema_cross_entries(df, "4w", params=params)
    for cut in range(255, len(df)):
        bull, bear = ef.ema_cross_entries(df.iloc[:cut], "4w", params=params)
        assert bull.equals(full_bull.iloc[:cut]) and bear.equals(full_bear.iloc[:cut]), cut


def test_defaults_ship_inert():
    params = ef.DEFAULT_PARAMS["EMA Crossover"]
    assert (params["max_touches_bull"], params["max_touches_bear"]) == (1, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`
Expected: FAIL. The helper tests raise `AttributeError: module ... has no attribute '_touch_events_after'`, and `test_defaults_ship_inert` raises `KeyError: 'max_touches_bull'`. `test_cross_mode_ignores_max_touches` and `test_fixtures_exercise_several_crosses_and_a_real_entry` may already pass. That is fine: they are guards, not the change.

- [ ] **Step 3: Add the params**

In `swingbot/core/market/entry_filters.py`, replace the last line of the `DEFAULT_PARAMS["EMA Crossover"]` dict:

```python
    "entry_mode": "pullback", "pullback_max_bars": 15,
}
```

with:

```python
    "entry_mode": "pullback", "pullback_max_bars": 15,
    # v108 re-arm: pullback touch *events* taken per held cross, per direction.
    # 1 = first touch only -- the pre-v108 entry, bit-for-bit. Changed only by
    # a v108 funnel verdict (docs/superpowers/results/*-v108-*.md).
    "max_touches_bull": 1, "max_touches_bear": 1,
}
```

- [ ] **Step 4: Add the two module-level helpers**

Directly above `def ema_cross_entries(df, horizon_key, params=None):`, insert:

```python
def _touch_events_after(cross, touch, window, max_touches):
    """Mark the first `max_touches` touch events in the `window` bars after each cross.

    A touch event is a touching bar whose previous bar did not touch, so a run
    of consecutive touching bars is one event. The first touching bar inside a
    window always opens an event, even when the cross bar itself touched --
    that keeps max_touches=1 identical to the pre-v108 first-touch rule. Each
    cross counts independently. Bar j reads only the cross at ci < j and the
    touch mask at j and j-1 (no lookahead).
    """
    if max_touches < 1:
        raise ValueError(f"max_touches must be >= 1, got {max_touches}")
    cross = np.asarray(cross, dtype=bool)
    touch = np.asarray(touch, dtype=bool)
    starts = touch & ~np.concatenate(([False], touch[:-1]))
    out = np.zeros(len(touch), dtype=bool)
    for ci in np.flatnonzero(cross):
        taken = 0
        for j in range(ci + 1, min(ci + 1 + window, len(touch))):
            if touch[j] and (j == ci + 1 or starts[j]):
                out[j] = True
                taken += 1
                if taken >= max_touches:
                    break
    return out


def _pullback_entries(cross, touch, window, max_touches):
    """Series wrapper: the touch-event bars that follow a held cross."""
    marks = _touch_events_after(cross.fillna(False).to_numpy(dtype=bool),
                                touch.fillna(False).to_numpy(dtype=bool),
                                window, max_touches)
    return pd.Series(marks, index=cross.index)


```

- [ ] **Step 5: Route `ema_cross_entries` through them**

In `ema_cross_entries`, replace this block (the nested helper and its two calls):

```python
        def _first_touch_after(cross_mask, touch_mask):
            out = pd.Series(False, index=df.index)
            for ci in np.where(cross_mask.values)[0]:
                for j in range(ci + 1, min(ci + 1 + window, len(df))):
                    if touch_mask.values[j]:
                        out.iloc[j] = True
                        break                     # first touch only
            return out

        held_bull = _first_touch_after(held_bull, touched_bull).fillna(False)
        held_bear = _first_touch_after(held_bear, touched_bear).fillna(False)
```

with:

```python
        # v108 re-arm: the first K touch events per held cross (K=1 = pre-v108).
        held_bull = _pullback_entries(held_bull, touched_bull, window,
                                      int(p.get("max_touches_bull", 1)))
        held_bear = _pullback_entries(held_bear, touched_bear, window,
                                      int(p.get("max_touches_bear", 1)))
```

- [ ] **Step 6: Run the new tests and the existing EMA tests**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/market/test_rescue_ema.py`
Expected: PASS, `0 failed`. `test_default_now_matches_adopted_pullback_config` still holds, because `_params` merges the new defaults into the explicit dict as well.

Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`
Expected: exactly one line, `F ...:0 elliott_wave_entries - C (15)` (legacy and untouched). Neither `_touch_events_after`, `_pullback_entries` nor `ema_cross_entries` may appear.

- [ ] **Step 8: Commit (on the worktree branch)**

```bash
git add swingbot/core/market/entry_filters.py tests/market/test_ema_rearm.py
git commit -m "feat(v108): EMA Crossover re-arm -- first K pullback touch events per held cross, K=1 default (inert)

max_touches_bull / max_touches_bear in DEFAULT_PARAMS['EMA Crossover'], both 1.
A run of touching bars is one event; the first in-window touch always opens
one, so K=1 matches the pre-v108 first-touch rule bit-for-bit.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/market/entry_filters.py tests/market/test_ema_rearm.py
```

---

### Task V108-2: Harness mechanism `E` in `measure_fib_v103.py`

**Files:**
- Modify: `scripts/backtest/measure_fib_v103.py` (the module docstring at line 2, `MECHANISMS` at line 32, `mechanism_cell` at line 64, `collect_trades` at line 97, `count_signals` at line 126, `stage0_closures` at line 135, and `_cmd_count` at line 187)
- Modify: `tests/scripts/test_measure_fib_v103.py` (append tests)

**Interfaces:**
- Consumes: the param names `max_touches_bull` / `max_touches_bear` (fixed by the spec; the tests pin them with `monkeypatch.setitem`, so this task does not wait for V108-1). From `fib_funnel`: `stage1`, `stage2`, `cell_key`, `MIN_N_TRAIN` (unchanged).
- Produces:
  - `MECHANISMS["E"]` with `strategy="EMA Crossover"`, `grid=(2, 3)`, `loosest=3`, `baseline=1`, `inert_ratio=Fraction(115, 100)`. A and C gain `inert_ratio=None`.
  - `E_PARAMS = {"bullish": "max_touches_bull", "bearish": "max_touches_bear"}`.
  - `mechanism_cell(mech, value, direction=None)`. For `E`, `direction` is required, and `ValueError` is raised without it.
  - `stage0_reasons(counts, mech) -> dict[str, str | None]`, whose values are `"min_n"`, `"inert"` or `None`.
  - `stage0_closures(counts, mech) -> list[str]`, same contract as before.
  - The `count` output JSON gains the key `"stage0_reasons"`.
  - CLI: `--mechanism E` on `count`, `collect` and `validation`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fib_v103.py`:

```python
# --- v108 mechanism E: EMA Crossover re-arm (K touch events per held cross) ---

@pytest.fixture
def ema_knobs(monkeypatch):
    """Pin the v108 keys so these tests never depend on the entry-filter task having landed."""
    from swingbot.core.market import entry_filters
    params = entry_filters.DEFAULT_PARAMS["EMA Crossover"]
    monkeypatch.setitem(params, "max_touches_bull", 1)
    monkeypatch.setitem(params, "max_touches_bear", 1)
    return params


def _tier1(direction="bullish"):
    return [row for index in range(10) for row in (
        [_row(f"T{index}", "win", 2.0, direction) for _ in range(4)]
        + [_row(f"T{index}", "loss", -1.0, direction) for _ in range(2)]
    )]


def test_mechanism_e_definition_keeps_k1_out_of_the_grid():
    from fractions import Fraction
    spec = _module().MECHANISMS["E"]
    assert (spec.strategy, spec.grid, spec.loosest, spec.baseline) == ("EMA Crossover", (2, 3), 3, 1)
    assert spec.inert_ratio == Fraction(115, 100)
    assert spec.baseline not in spec.grid
    assert _module().MECHANISMS["A"].inert_ratio is None and _module().MECHANISMS["C"].inert_ratio is None


def test_mechanism_e_sets_only_the_scored_direction_and_restores(ema_knobs):
    module = _module()
    with module.mechanism_cell("E", 3, "bullish"):
        assert (ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]) == (3, 1)
    with module.mechanism_cell("E", 2, "bearish"):
        assert (ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]) == (1, 2)
    assert (ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]) == (1, 1)


def test_mechanism_e_restores_after_an_exception(ema_knobs):
    with pytest.raises(RuntimeError):
        with _module().mechanism_cell("E", 3, "bullish"):
            raise RuntimeError("boom")
    assert ema_knobs["max_touches_bull"] == 1


def test_mechanism_e_needs_a_direction(ema_knobs):
    with pytest.raises(ValueError):
        _module().mechanism_cell("E", 2)


def test_collect_trades_e_scores_each_direction_under_its_own_knob(ema_knobs):
    module, frame, seen = _module(), make_ohlcv([100.0] * 300, start="2012-01-02"), []
    def run_fn(ticker, df, strategy, horizon, **kwargs):
        seen.append((strategy, ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]))
        return NS(trades=[])
    module.collect_trades("E", {"AAA": frame}, {}, 3, module.TRAIN_EXT, horizons=("4w",), run_fn=run_fn, progress=NS(tick=lambda label: None))
    assert seen == [("EMA Crossover", 3, 1), ("EMA Crossover", 1, 3)]
    assert (ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]) == (1, 1)


def test_count_signals_e_counts_each_direction_under_its_own_knob(monkeypatch, ema_knobs):
    import pandas as pd
    module, seen = _module(), []
    def fake(strategy, df, horizon):
        seen.append((ema_knobs["max_touches_bull"], ema_knobs["max_touches_bear"]))
        on = pd.Series(True, index=df.index)
        return on, on
    monkeypatch.setattr(module, "entries_for", fake)
    counts = module.count_signals("E", {"AAA": make_ohlcv([100.0] * 5, start="2015-01-05")}, (1, 3), horizons=("4w",))
    assert set(counts) == {"1|bullish", "1|bearish", "3|bullish", "3|bearish"}
    assert seen == [(1, 1), (1, 1), (3, 1), (1, 3)]


def test_stage0_e_closes_an_inert_direction_at_the_exact_ratio():
    module = _module()
    counts = {"1|bullish": {"total": 40}, "3|bullish": {"total": 45},
              "1|bearish": {"total": 40}, "3|bearish": {"total": 46}}
    assert module.stage0_reasons(counts, "E") == {"bullish": "inert", "bearish": None}
    assert module.stage0_closures(counts, "E") == ["bullish"]


def test_stage0_e_min_n_is_checked_first():
    counts = {"1|bullish": {"total": 10}, "3|bullish": {"total": 29},
              "1|bearish": {"total": 100}, "3|bearish": {"total": 300}}
    assert _module().stage0_reasons(counts, "E") == {"bullish": "min_n", "bearish": None}


def test_count_command_counts_the_reference_and_writes_reasons(monkeypatch, tmp_path):
    module, asked = _module(), []
    monkeypatch.setattr(module, "require_ext_cache", lambda: None)
    monkeypatch.setattr(module, "_load_frames", lambda universe, tickers: {"AAA": None, "BBB": None})
    def fake_counts(mech, frames, values, **kwargs):
        asked.append(values)
        return {f"{value}|{direction}": {"total": 100 if value == 1 else 200}
                for value in values for direction in module.DIRECTIONS}
    monkeypatch.setattr(module, "count_signals", fake_counts)
    out = tmp_path / "s0.json"
    module.main(["count", "--mechanism", "E", "--out", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert asked == [(1, 2, 3)] and payload["universe_n"] == 2
    assert payload["closed_at_stage0"] == []
    assert payload["stage0_reasons"] == {"bullish": None, "bearish": None}


def test_evaluate_e_never_selects_the_k1_reference():
    module = _module()
    failing = [_row(f"T{index}", "loss", -1.0) for index in range(40)]
    result = module.evaluate("E", {"1": _tier1(), "2": failing, "3": failing}, closed=("bearish",), **FAST)
    bullish = result["bullish"]
    assert bullish["baseline"]["n"] == 60
    assert set(bullish["stage1"]["cells"]) == {"2", "3"}
    assert bullish["stage1"]["winner"] is None and bullish["proceed_to_validation"] is False
    assert result["bearish"]["closed_at"] == "stage0"


def test_evaluate_e_picks_a_tier1_plateau_winner_from_the_grid():
    result = _module().evaluate("E", {"1": _tier1(), "2": _tier1(), "3": _tier1()}, closed=("bearish",), **FAST)
    stage1 = result["bullish"]["stage1"]
    assert stage1["winner"] in (2, 3) and stage1["winner_tier"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`
Expected: FAIL on the new tests (`KeyError: 'E'`, `AttributeError: ... 'stage0_reasons'`, and argparse `invalid choice: 'E'`). The 13 pre-existing tests still pass.

- [ ] **Step 3: Mechanism table**

In `scripts/backtest/measure_fib_v103.py`, change the docstring on line 2 to:

```python
"""v103 Fibonacci level-stop (A) / continuation (C) and v108 EMA Crossover re-arm (E) measurement funnel."""
```

Add `from fractions import Fraction` to the stdlib imports, placed alphabetically after `import contextlib`:

```python
import contextlib
from fractions import Fraction
import json
```

Replace the `MECHANISMS` block with:

```python
MECHANISMS = {
    "A": SimpleNamespace(strategy="Fibonacci", grid=(0.1, 0.25, 0.5), loosest=0.1, baseline=0.0, inert_ratio=None),
    "C": SimpleNamespace(strategy="Fibonacci Continuation", grid=(0.5, 0.618, 0.786), loosest=0.786, baseline=None, inert_ratio=None),
    # v108: K = pullback touch events taken per held cross. K=1 is today's
    # entry -- the reference arm, reported, never a candidate. Stage 0 also
    # closes a direction whose K=3 count is < 1.15x the K=1 count (inert).
    "E": SimpleNamespace(strategy="EMA Crossover", grid=(2, 3), loosest=3, baseline=1, inert_ratio=Fraction(115, 100)),
}
# v108 scores one direction at a time and sets only that direction's knob.
E_PARAMS = {"bullish": "max_touches_bull", "bearish": "max_touches_bear"}
```

`Fraction` keeps the 1.15 boundary exact (`46 < 1.15 * 40` is not decided by float rounding).

- [ ] **Step 4: Direction-aware cell**

Replace `mechanism_cell` with:

```python
def mechanism_cell(mech, value, direction=None):
    if mech == "A":
        enabled = float(value) > 0
        return _config_values(FIB_LEVEL_STOP_ATR=float(value), FIB_LEVEL_STOP_DIRECTIONS="bullish,bearish" if enabled else "")
    if mech == "E":
        if direction not in E_PARAMS:
            raise ValueError(f"mechanism E sets one direction's knob; got direction={direction!r}")
        return _param_value(MECHANISMS["E"].strategy, E_PARAMS[direction], int(value))
    return _param_value(MECHANISMS["C"].strategy, "d_max", float(value))
```

- [ ] **Step 5: Enter the cell per direction in `collect_trades` and `count_signals`**

For A and C this is behaviour-identical (their cell ignores `direction`). Replace `collect_trades` with:

```python
def collect_trades(mech, frames, asof_map, value, window, *, directions=DIRECTIONS, horizons=ALL_HZ, run_fn=None, progress=None):
    spec = MECHANISMS[mech]
    run_fn = run_fn or run_backtest
    progress = progress or Progress(len(frames) * len(directions))
    rows = []
    for direction in directions:
        with mechanism_cell(mech, value, direction):
            rows.extend(_direction_pass(spec.strategy, frames, asof_map, direction, window, horizons, run_fn, progress, f"{mech} {cell_key(value)}"))
    return rows
```

Replace `count_signals` with:

```python
def count_signals(mech, frames, values, *, horizons=ALL_HZ):
    strategy, results = MECHANISMS[mech].strategy, {}
    for value in values:
        for direction in DIRECTIONS:
            with mechanism_cell(mech, value, direction):
                results[f"{cell_key(value)}|{direction}"] = _count_direction(strategy, frames, direction, horizons)
    return results
```

- [ ] **Step 6: Stage 0 reasons**

Replace `stage0_closures` with:

```python
def _stage0_reason(counts, spec, direction):
    loosest = counts[f"{cell_key(spec.loosest)}|{direction}"]["total"]
    if loosest < MIN_N_TRAIN:
        return "min_n"
    if spec.inert_ratio is not None:
        reference = counts[f"{cell_key(spec.baseline)}|{direction}"]["total"]
        if loosest < spec.inert_ratio * reference:
            return "inert"
    return None


def stage0_reasons(counts, mech):
    spec = MECHANISMS[mech]
    return {direction: _stage0_reason(counts, spec, direction) for direction in DIRECTIONS}


def stage0_closures(counts, mech):
    reasons = stage0_reasons(counts, mech)
    return [direction for direction in DIRECTIONS if reasons[direction] is not None]
```

In `_cmd_count`, replace the `_write(...)` line with:

```python
    _write(args.out, {"mechanism": args.mechanism, "universe_n": len(frames), "counts": counts, "closed_at_stage0": stage0_closures(counts, args.mechanism), "stage0_reasons": stage0_reasons(counts, args.mechanism)})
```

- [ ] **Step 7: Run the harness tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`
Expected: PASS, `0 failed` (the 13 pre-existing tests plus the 11 new ones).

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C scripts/backtest/measure_fib_v103.py`
Expected: no output.

- [ ] **Step 9: Commit (on the worktree branch)**

```bash
git add scripts/backtest/measure_fib_v103.py tests/scripts/test_measure_fib_v103.py
git commit -m "feat(v108): harness mechanism E -- EMA Crossover re-arm K in {2,3}, K=1 reference, Stage 0 inert closure

Sets only the scored direction's max_touches_<dir>; A and C unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- scripts/backtest/measure_fib_v103.py tests/scripts/test_measure_fib_v103.py
```

---

### Task V108-3: Real-data K=1 parity, then merge Phase A to `main`

**Files:**
- No file changes. This task produces the merge commit on `main`.

**Interfaces:**
- Consumes: V108-1's `_touch_events_after` and `DEFAULT_PARAMS` keys, and V108-2's `MECHANISMS["E"]`.
- Produces: `main` containing both Phase A commits. V108-4 records that merge's SHA.

- [ ] **Step 1: Real-data parity on the TRAIN window only**

This is a code-equivalence check, not a measurement. It compares boolean masks only, scores nothing, and truncates every frame at 2023-12-31 so no VALIDATION bar is read. Run it from the worktree root:

```bash
python - <<'EOF'
import sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import HORIZONS

CACHE = pathlib.Path("E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext")

def legacy(cross, touch, window, max_touches):
    out = np.zeros(len(touch), dtype=bool)
    for ci in np.flatnonzero(cross):
        for j in range(ci + 1, min(ci + 1 + window, len(touch))):
            if touch[j]:
                out[j] = True
                break
    return out

new_impl, frames, entries, mismatches = ef._touch_events_after, 0, 0, []
for path in sorted(CACHE.glob("*.csv")):
    df = pd.read_csv(path, index_col=0, parse_dates=True).loc[:"2023-12-31"]
    if len(df) < 260:
        continue
    frames += 1
    for hk in HORIZONS:
        ef._touch_events_after = new_impl
        nb, ns = ef.ema_cross_entries(df, hk)
        ef._touch_events_after = legacy
        ob, os_ = ef.ema_cross_entries(df, hk)
        ef._touch_events_after = new_impl
        entries += int(nb.sum() + ns.sum())
        if not (nb.equals(ob) and ns.equals(os_)):
            mismatches.append((path.stem, hk))
print("frames", frames, "k1_entries", entries, "mismatches", mismatches)
EOF
```

Required: `mismatches []`, `frames` ≥ 70, and `k1_entries` > 0. Any mismatch means V108-1 broke K=1 parity. **Stop**, fix V108-1 under `superpowers:systematic-debugging`, and re-run this step. Do not print or read any K > 1 count here: that is Stage 0's job, after the pre-registration.

- [ ] **Step 2: Branch-level checks**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`, then `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`, then `python scripts/dev/testrun.py fast`.
Expected: each prints `0 failed` / `0 xfailed`. `fast` is here because the two tasks' blast radii meet in `DEFAULT_PARAMS`. It is not the plan's full-suite run, which stays in V108-9.

- [ ] **Step 3: Merge**

Follow the `worktree-lifecycle` skill. Run `git fetch` and `git log --oneline main -5` to see other sessions' commits. Then merge branch `2026-09-27-v108-ema-crossover-rearm-rescue` into `main`, and record the resulting `main` HEAD SHA for V108-4. Do not remove the worktree yet: V108-9 does that. If the merge resolved conflicts, re-run Step 2's `fast` on `main`. Otherwise, do not run it again.

---

# Phase B — Measurement (main tree, on `main`)

### Task V108-4: Pre-registration (committed before any count or collect)

**Files:**
- Create: `docs/superpowers/results/<date>-v108-preregistration.md`
- Create: `docs/superpowers/results/<date>-v108-universe.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: V108-3's merge SHA, and the constants in `scripts/backtest/fib_funnel.py` and `scripts/backtest/measure_fib_v103.py` as they are on `main`.
- Produces: the committed pre-registration path, which V108-7's `--preregistration` requires; the universe file every measurement command reads; and the ignore rule for `data/v108_*.json`.

- [ ] **Step 1: Confirm nothing was measured yet**

Run: `ls docs/superpowers/results/ | grep -- "-v108-"`
Expected: no output. Any v108 stage file already present means a measurement preceded the pre-registration. **Stop** and report it to the partner. Do not pre-register after the fact.

- [ ] **Step 2: Freeze the universe file**

```bash
printf '%s' "AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT" > docs/superpowers/results/<date>-v108-universe.txt
python - <<'EOF'
import glob, hashlib, json
path = sorted(glob.glob("docs/superpowers/results/*-v108-universe.txt"))[-1]
names = open(path, encoding="utf-8").read().split(",")
print(len(names), hashlib.sha256(",".join(names).encode()).hexdigest())
watch = sorted(json.load(open("E:/Documents/Private/Projects/Discord-Bot/data/watchlist.json", encoding="utf-8")))
print("equals main-tree watchlist:", watch == names)
EOF
```

Required: `77 4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`, which is the v103 universe (`results/2026-09-25-v103-preregistration.md`, § Data). If the main-tree watchlist no longer equals it, still use the frozen v103 list (it keeps the v84/v103 comparison intact), and state the difference in the pre-registration.

- [ ] **Step 3: Git-ignore the collect dump**

In `.gitignore`, directly under the `data/v103_*.json` line, add:

```gitignore
# v108 EMA Crossover re-arm collect dump (scripts/backtest/measure_fib_v103.py
# collect --mechanism E); the committed stage JSONs under docs/superpowers/results/ are the record.
data/v108_*.json
```

Run: `git check-ignore -v data/v108_collect_E.json`. Expected: it names the new line.

- [ ] **Step 4: Write the pre-registration**

Read every constant from the files, not from this plan: `grep -n "^[A-Z_]* = " scripts/backtest/fib_funnel.py`, the `MECHANISMS` / `E_PARAMS` block of `measure_fib_v103.py`, and `grep -n "TRAIN_EXT =\|VALIDATION =" scripts/backtest/measure_fib_confluence.py`. Write `docs/superpowers/results/<date>-v108-preregistration.md` with these sections:

- `# v108 pre-registration -- EMA Crossover re-arm (mechanism E)`: registered `<date>` before any count or backtest. Name the merged SHA from V108-3 and the scripts under test (`measure_fib_v103.py`, `fib_funnel.py`, `entry_filters.py::_touch_events_after`). Link the spec.
- `## Mechanism`: K = the first K touch **events** inside `pullback_max_bars = 15` bars after each held cross. A run of consecutive touching bars is one event, and the first in-window touching bar always opens one. Per-direction knobs `max_touches_bull` / `max_touches_bear`; the harness sets only the scored direction's knob. Unchanged: the ten ANDed filters, the stop/target arithmetic, and no `STRATEGY_GATES` entry. V108-3's parity result goes here: `frames`, `k1_entries`, mismatches `[]`.
- `## Grid`: `K ∈ {2, 3}`, loosest `K=3`, reference `K=1` (reported, **never eligible to win**; if `K=1` would clear and no `K>1` cell does, the verdict is NO-LIFT).
- `## Windows`: `TRAIN_EXT`, `FOLD_YEARS = 2013..2023` anchored at 2010-01-01, and `VALIDATION`, which only the `validation` command reads.
- `## Stage 0`: per direction, closed if `K=3` N < 30, or if `K=3` count < 1.15 × `K=1` count (`inert_ratio = Fraction(115, 100)`, compared exactly). A closed direction keeps its budget.
- `## Clauses and constants`: every `fib_funnel.py` constant with its value, plus `BOOTSTRAP_RESAMPLES = 10_000`, seed `42`, lower bound = 2.5th percentile over ticker clusters with an empty baseline arm. Tier 1 and Tier 2 exactly as in this plan's Global Constraints.
- `## Stage 1`: the plateau rule over the grid `(2, 3)`. Each cell's only neighbour is the other cell, so a winner needs **both** cells to pass the same tier. Winner order: Tier 1 plateau, then Tier 2 plateau, then none. **Only a Tier 1 winner can earn `VALIDATED`.** A Tier 2-only winner still runs Stages 2–3; if it passes, its K ships but the badge stays `WEAK`.
- `## Stage 2`: per fold Y, re-select from `{2, 3}` the highest-ExpR cell on 2010..Y−1 with N ≥ 30 (none qualifies = unselected, counted in the report). The fold clears when ≥ 3 folds have test N ≥ 15 and ≥ 2/3 of those have ExpR > 0. A direction proceeds only with a Stage 1 winner **and** a Stage 2 clear.
- `## Populations and arithmetic`: both directions unmasked, as live today (EMA Crossover has no `STRATEGY_GATES` entry). Bearish rows pass through the v93 laggard rule (`apply_laggard_rule`), as live does. `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`, `frictions=True`, `one_at_a_time=True`, level lifecycle as today, all ten horizons pooled.
- `## Data`: the extended cache at its absolute main-tree path, and the universe file with its sha256. 73 of 77 survive the liquidity/data-quality filter, and **any run whose `universe_n` ≠ 73 is discarded**. Survivorship bias is stated, not corrected: it biases WR and ExpR upward in the early years.
- `## The one-shot rule`: at most one `validation` run per direction (two in all), only at the committed evaluate output's `validation_cell`, never at another cell, and never again after a FAIL.
- `## Outcomes (decided now)`:
  - **Tier 1 PASS in a direction:** that direction's knob is set to its winning K.
  - **Tier 2 PASS:** the knob is set as above, the badge stays `WEAK`, and no registry row is emitted.
  - **Anything else:** both knobs stay `1`.
- `## Registry-row rule (decided now, before any score)`: the `EMA Crossover` registry row is strategy-level and must describe the population live lets through, which is both directions. `emit-registry` therefore runs **only when both directions pass VALIDATION at Tier 1**. It pools their rows (`registry_status` → `VALIDATED` only if the pooled badge also clears). In any other case no row is emitted and the existing row (`WEAK`, N=36, 2024-01-01..2025-12-31, run 2026-07-18) stays untouched. A one-direction Tier 1 PASS ships that direction's K and records in `docs/claude/backtest-methodology.md` why the badge did not change. This is v103's population-equality rule applied to a strategy with no direction mask.
- `## Not consulted`: the 2026-07 VALIDATION read (N=36, WR 75.0%, fixed R:R table). `## Not re-run`: v84's `pullback_max_bars` axis (closed, round 2) and the v84 EMA fold-stability row.

- [ ] **Step 5: Commit on `main`, then verify**

```bash
git add .gitignore docs/superpowers/results/<date>-v108-preregistration.md docs/superpowers/results/<date>-v108-universe.txt
git commit -m "docs(v108): pre-register EMA Crossover re-arm (E) -- K in {2,3}, K=1 reference, TRAIN_EXT, 11 folds, one shot per direction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- .gitignore docs/superpowers/results/<date>-v108-preregistration.md docs/superpowers/results/<date>-v108-universe.txt
```

Run: `git status --short docs/superpowers/results/ .gitignore`. Expected: nothing listed for these three files. `validation` refuses a pre-registration that has uncommitted changes.

---

### Task V108-5: Stage 0 signal counts (free)

**Files:**
- Create: `docs/superpowers/results/<date>-v108-stage0-E.json`, `docs/superpowers/results/<date>-v108-stage0.md`

**Interfaces:**
- Consumes: V108-4's committed pre-registration and universe file, and V108-2's `count --mechanism E`.
- Produces: `closed_at_stage0` / `stage0_reasons` in `<date>-v108-stage0-E.json`, which V108-6's `collect --stage0` reads.

- [ ] **Step 1: Load `backtest-gate`, then confirm the pre-registration is committed**

Run: `git log --oneline -1 -- docs/superpowers/results/<date>-v108-preregistration.md`
Expected: V108-4's commit. If there is no output, **stop**: nothing may be counted before it is committed.

- [ ] **Step 2: Check the extended cache covers the universe (no fetch)**

```bash
python - <<'EOF'
import pathlib, pandas as pd
ext = pathlib.Path("E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext")
names = open(sorted(pathlib.Path("docs/superpowers/results").glob("*-v108-universe.txt"))[-1], encoding="utf-8").read().split(",")
have = {p.stem for p in ext.glob("*.csv")}
print("missing_in_ext", sorted(n for n in names if n not in have and n.replace("=", "_") not in have))
spy = pd.read_csv(ext / "SPY.csv", index_col=0)
print("SPY", spy.index[0], spy.index[-1], len(spy))
EOF
```

Required: SPY's first date ≤ `2010-01-05` and its last date ≥ `2025-12-30`. `missing_in_ext` was `['CRWV', 'SNDK', 'SPCX']` when this plan was written. Those names, plus one the liquidity/data-quality filter drops, make up the 77 → 73 gap. The `universe_n` check in Step 4 is the binding one. If SPY fails the check, **stop** and report it: re-fetching the cache is out of this plan's scope.

- [ ] **Step 3: Count**

Stage 0 counts entry signals on TRAIN_EXT only. It runs no backtest and reads no VALIDATION bar.

```bash
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py count --mechanism E --tickers "$(cat docs/superpowers/results/<date>-v108-universe.txt)" --out docs/superpowers/results/<date>-v108-stage0-E.json
```

Expected last line: `v103 count done`. If the run goes past 2 minutes, stop it and dispatch the same command to `backtest-runner` in the background, with progress in a scratchpad log that is deleted on success.

- [ ] **Step 4: Check the universe, then read the decision**

```bash
python - <<'EOF'
import glob, json
d = json.load(open(sorted(glob.glob("docs/superpowers/results/*-v108-stage0-E.json"))[-1], encoding="utf-8"))
print("universe_n", d["universe_n"], "closed", d["closed_at_stage0"], "reasons", d["stage0_reasons"])
for direction in ("bullish", "bearish"):
    k1, k3 = d["counts"][f"1|{direction}"], d["counts"][f"3|{direction}"]
    ratio = k3["total"] / k1["total"] if k1["total"] else float("inf")
    print(direction, "K1", k1["total"], "K2", d["counts"][f"2|{direction}"]["total"], "K3", k3["total"], f"K3/K1={ratio:.3f}")
    for year in sorted(set(k1["by_year"]) | set(k3["by_year"])):
        print("   ", year, "K1", k1["by_year"].get(year, 0), "K3", k3["by_year"].get(year, 0))
    top2 = sum(sorted(k3["by_horizon"].values(), reverse=True)[:2])
    print("    K3 top-2 horizon share", f"{top2 / k3['total']:.0%}" if k3["total"] else "n/a", k3["by_horizon"])
EOF
```

If `universe_n` ≠ 73, **discard the run**: delete the JSON (nothing is staged yet). Find the cause (wrong `--tickers`, wrong cache path), fix it, and re-run Step 3. Do not continue on any other count.

The decision is `closed_at_stage0` / `stage0_reasons`. **Do not recompute or override it.** Signal counts are an upper bound on decided trades.

- [ ] **Step 5: Write `docs/superpowers/results/<date>-v108-stage0.md`**

Sections:
- `## Run`: the command, `universe_n = 73`, and Step 2's cache output.
- `## Counts`: per direction, a table of K=1 / K=2 / K=3 totals, K3/K1 against the 1.15 threshold, and the per-year K=1 vs K=3 counts for 2010–2023. The per-year table is the free preview of the fold picture the spec's prior asked for.
- `## Horizon spread`: K=3 `by_horizon` per direction. Where the top-2-horizon share is ≥ 80%, say plainly that a PASS would not be a cross-horizon result. This is disclosed, not gated.
- `## Decision`: per direction, `ENTERS Stage 1`, `NO-LIFT at Stage 0 -- min_n (K=3 N=<n> < 30)`, or `NO-LIFT at Stage 0 -- inert (K3/K1=<r> < 1.15)`.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/results/<date>-v108-stage0-E.json docs/superpowers/results/<date>-v108-stage0.md
git commit -m "docs(v108): Stage 0 signal counts -- <bullish: enters | NO-LIFT reason>; <bearish: enters | NO-LIFT reason>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/<date>-v108-stage0-E.json docs/superpowers/results/<date>-v108-stage0.md
```

If both directions closed, skip V108-6 and V108-7 and go to V108-8's NO-LIFT path.

---

### Task V108-6: Stages 1–2 — collect once, evaluate

**Files:**
- Create (local, git-ignored, never staged): `data/v108_collect_E.json`
- Create: `docs/superpowers/results/<date>-v108-stage12-E.json`, `docs/superpowers/results/<date>-v108-stage12.md`

**Interfaces:**
- Consumes: `<date>-v108-stage0-E.json` (`closed_at_stage0`), and V108-2's `collect` / `evaluate` for `E`.
- Produces: the committed `<date>-v108-stage12-E.json`, whose per-direction `proceed_to_validation`, `validation_cell` and `tier` V108-7 requires.

- [ ] **Step 1: Load `backtest-gate`, then confirm the pre-registration is committed**

Run: `git log --oneline -1 -- docs/superpowers/results/<date>-v108-preregistration.md`
Expected: V108-4's commit.

- [ ] **Step 2: Collect in the background**

Dispatch one `backtest-runner` in the background. It backtests K ∈ {1, 2, 3}, times the open directions, 73 names, 10 horizons, and 14 years, so expect tens of minutes. The brief:

> From the main-tree repo root, with no `cd`: `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py collect --mechanism E --stage0 docs/superpowers/results/<date>-v108-stage0-E.json --tickers "$(cat docs/superpowers/results/<date>-v108-universe.txt)" --out data/v108_collect_E.json > <scratchpad>/v108_collect_E.log 2>&1`. Progress lines read `[k/N] P% E <cell> <direction> <TICKER>`, so answer "how far along" from the last line's percent. On success, return the final line plus `universe_n`, `elapsed_s` and `closed_at_stage0` from the JSON, then delete the log. On failure, return the last 40 log lines and keep the log.

Required: the returned `universe_n` is 73. Any other value: **discard** `data/v108_collect_E.json`, find the cause, and re-run. Never evaluate it.

- [ ] **Step 3: Evaluate** (fast; no backtest, no cache)

```bash
python scripts/backtest/measure_fib_v103.py evaluate --rows data/v108_collect_E.json --out docs/superpowers/results/<date>-v108-stage12-E.json
```

Expected last line: `v103 evaluate done`.

- [ ] **Step 4: Print the verdict fields**

```bash
python - <<'EOF'
import glob, json
ev = json.load(open(sorted(glob.glob("docs/superpowers/results/*-v108-stage12-E.json"))[-1], encoding="utf-8"))
for d in ("bullish", "bearish"):
    x = ev[d]
    if x.get("closed_at") == "stage0":
        print(d, "closed at Stage 0"); continue
    s1, s2 = x["stage1"], x["stage2"]
    print(d, "K=1 reference", x["baseline"])
    for k, c in s1["cells"].items():
        print(f"   K={k}: {c['stats']}  lb={c['lower_bound']}  tier={c['tier']}")
    print("   plateau t1", s1["plateau_tier1"], "t2", s1["plateau_tier2"], "winner", s1["winner"], "tier", s1["winner_tier"])
    for f in s2["folds"]:
        print("   fold", f["test_year"], "K", f["tol"], f["stats"] and {k: f["stats"][k] for k in ("n", "win_rate", "expectancy_r")})
    print("   stage2", s2["verdict"], "=> proceed", x["proceed_to_validation"], "cell", x["validation_cell"], "tier", x["tier"])
EOF
```

`proceed_to_validation`, `validation_cell` and `tier` are the decision. **Never override them by hand.** A cell that "looks close" but did not clear is NO-LIFT. If the K=1 reference would clear a tier while no K>1 cell forms a plateau, the verdict is still NO-LIFT, and the report says so.

- [ ] **Step 5: Write `docs/superpowers/results/<date>-v108-stage12.md`**

Load `pooled-numbers` first. Per open direction:
- The K=1 reference: N / WR / ExpR / scratch+timeout share. Label it the reference (never a candidate). Put the v84 row beside it for context only (TRAIN 2020–2023, N=55, WR 61.8%, ExpR +0.494; a different window, so it is not comparable as a gate).
- K=2 and K=3: N / WR / ExpR / scratch share / bootstrap lower bound / the Tier 1 and Tier 2 clauses / the tier.
- **Re-arm quality:** for each K>1 cell, the added trades are `N_K − N_1`. Report the ExpR the added population implies, `(N_K·ExpR_K − N_1·ExpR_1) / (N_K − N_1)`, labelled "implied, not separately measured". Second touches that are worse trades show up here even when the pooled cell clears.
- The plateaus, the winner and its tier (or "no winner").
- Stage 2: the fold table (test year, selected K, test N, test WR, test ExpR) and the verdict (qualifying, positive, unselected). Put the v84 fold row (2021 N=13, 2022 N=16, 2023 N=13) beside the same years for context.
- `## Verdict`: per direction, `PROCEED-VALIDATION at K=<k> (Tier <t>)` or `NO-LIFT at Stage 1|2`.

- [ ] **Step 6: Commit** (the evaluate JSON must be committed before V108-7: `validation` refuses an uncommitted one)

```bash
git add docs/superpowers/results/<date>-v108-stage12-E.json docs/superpowers/results/<date>-v108-stage12.md
git commit -m "docs(v108): Stages 1-2 on TRAIN_EXT -- <bullish verdict>; <bearish verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/<date>-v108-stage12-E.json docs/superpowers/results/<date>-v108-stage12.md
```

If no direction proceeds, skip V108-7 and go to V108-8's NO-LIFT path.

---

### Task V108-7: Stage 3 — VALIDATION (one shot per proceeding direction)

**Files:**
- Create: `docs/superpowers/results/<date>-v108-validation-E-<direction>.json` (one per shot), `docs/superpowers/results/<date>-v108-validation.md`

**Interfaces:**
- Consumes: the committed `<date>-v108-preregistration.md` and `<date>-v108-stage12-E.json`, and V108-2's `validation --mechanism E`.
- Produces: the per-direction `verdict.passes` / `verdict.tier`, and the `cell` (the winning K) that V108-8 wires.

- [ ] **Step 1: Load `backtest-gate`, then check that no shot is spent**

Run: `ls docs/superpowers/results/ | grep -- "-v108-validation-"`
Expected: no output. Any existing `-v108-validation-E-<direction>.json` from **any date** means that direction's shot is spent. **Stop** and do not re-run it. The script only refuses an existing file at the *same* path, so this check closes the different-`<date>` gap.

- [ ] **Step 2: Run each proceeding direction exactly once**

Dispatch each shot to `backtest-runner`. The two directions may run concurrently, since they write separate files. The brief, per direction `<d>`:

> From the main-tree repo root, with no `cd`: `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py validation --mechanism E --direction <d> --evaluate docs/superpowers/results/<date>-v108-stage12-E.json --preregistration docs/superpowers/results/<date>-v108-preregistration.md --tickers "$(cat docs/superpowers/results/<date>-v108-universe.txt)" --out docs/superpowers/results/<date>-v108-validation-E-<d>.json > <scratchpad>/v108_val_<d>.log 2>&1`. Return the final line and the JSON's `cell` and `verdict`, then delete the log. On a refusal (`SystemExit`), return the message verbatim and **do not retry with changed arguments**.

A refusal means a precondition failed: an uncommitted file, a direction that did not proceed, or a spent shot. Fix the precondition, which is usually a missing commit. Never work around the refusal. The `validation` payload has no `universe_n`. Confirm the universe instead by checking that `rows` spans more than 3 distinct tickers and that the command used the universe file. Do not spend a second shot to "check" it.

- [ ] **Step 3: Write `docs/superpowers/results/<date>-v108-validation.md`**

Load `pooled-numbers` first. Per shot:
- K and tier; N / WR / ExpR / scratch share / lower bound; each clause with its value; and `PASS` or `FAIL`.
- One line comparing TRAIN_EXT and VALIDATION at the same K (N, WR, ExpR). A large drop is information even on a PASS.

**A FAIL is final:** no re-run, no other K, no other tier. Close with `## Registry-row consequence`, which applies V108-4's registry-row rule: emit only if both directions passed at Tier 1; otherwise say which case applies.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<date>-v108-validation-E-*.json docs/superpowers/results/<date>-v108-validation.md
git commit -m "docs(v108): VALIDATION -- <bullish PASS/FAIL (Tier t, K=k) | not run>; <bearish ...>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/<date>-v108-validation-E-*.json docs/superpowers/results/<date>-v108-validation.md
```

---

# Phase C — Outcome

### Task V108-8: Wiring (any PASS) or close-out (NO-LIFT)

Run the PASS path for each direction whose V108-7 shot passed. Run the NO-LIFT steps for everything else. Both can apply, for example when bullish passes and bearish closed at Stage 0.

**Files (PASS path):**
- Modify: `swingbot/core/market/entry_filters.py` (the `max_touches_<dir>` value and its comment)
- Modify: `swingbot/core/market/strategy_types.py:200-210` (the EMA Crossover comment block above `STRATEGY_GATES`)
- Modify: `tests/market/test_ema_rearm.py` (`test_defaults_ship_inert` → the validated pin)
- Create: `tests/scanning/test_strategy_pass_open_trade.py`
- Modify (only under V108-4's registry-row rule): `swingbot/core/backtesting/validation_registry.json`, through the script only
- Modify: `docs/claude/backtest-methodology.md` (§ "Closed pre-registrations — do not re-run these", beside the v84 EMA row at line 177)

**Files (NO-LIFT path):**
- Modify: `docs/claude/backtest-methodology.md` (same table)

**Interfaces:**
- Consumes: V108-7's `cell` (K) and `verdict.tier` per passing direction, V108-1's param keys, and `swingbot.core.scanning.strategy_pass.run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes, rs_combined_of, mode, live_allow, trade_log, plan_store, asof_of=None) -> PassResult` (existing; `PassResult.opened`, `.stored_only`, `.alerts`).
- Produces: shipped defaults (PASS) or the closed methodology row (NO-LIFT).

**PASS path.** Work on a short worktree branch named `2026-09-27-v108-ema-crossover-rearm-rescue-wiring` (`worktree-lifecycle` skill), and merge at the end. Load `edge-module` first.

- [ ] **P1: Live-path check first (characterization test)**

With K > 1 live, a second pullback in the same leg posts a second signal. The backtest measured `one_at_a_time=True`, so live must also suppress that second signal while the first trade is open. Otherwise the live population differs from the measured one. Create `tests/scanning/test_strategy_pass_open_trade.py`:

```python
"""v108 wiring: a re-armed EMA Crossover signal on a ticker that already holds
an open trade is stored only -- never logged as a trade, never alerted.

The backtest measured one_at_a_time=True per ticker x strategy x horizon;
live is at least as strict (one open trade per ticker, any strategy or
horizon), so K > 1 cannot put a second resting order on a live ticker.
"""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv


class _TradeLog:
    def __init__(self, open_for=()):
        self.open_for, self.logged = set(open_for), []

    def open_trade_for_ticker(self, ticker):
        return {"ticker": ticker, "direction": "bullish"} if ticker in self.open_for else None

    def log_trade(self, **kwargs):
        self.logged.append(kwargs)
        self.open_for.add(kwargs["ticker"])


class _PlanStore:
    def __init__(self):
        self.plans = []

    def all(self):
        return list(self.plans)

    def add(self, plan):
        self.plans.append(plan)


def _plan(ticker, horizon_key):
    return NS(ticker=ticker, strategy="EMA Crossover", horizon_key=horizon_key, direction="bullish",
              trigger_price=100.0, stop_loss=98.0, tp1=104.0, tp2=106.0, plan_id=f"p-{ticker}-{horizon_key}",
              badge="WEAK", quality_score=None, source="strategy", cohort_label=None, cohort_stats=None,
              risk_features=None, ledger="paper", entry_context={}, created_at="2024-03-11")


def _run(monkeypatch, tickers, horizons, trade_log):
    monkeypatch.setattr(sp, "strategy_signals", lambda frame, horizon, spy_df: [("EMA Crossover", "bullish")])
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda frame, **kw: _plan(kw["ticker"], kw["horizon_key"]))
    monkeypatch.setattr(sp, "build_strategy_alert_embed", lambda plan: "embed")
    frame = make_ohlcv([100.0] * 50, start="2024-01-02")
    return sp.run_strategy_pass(
        tickers, {ticker: frame for ticker in tickers}, now=datetime(2030, 1, 2, tzinfo=timezone.utc),
        horizons=horizons, spy_df=frame, regimes=None, rs_combined_of=lambda ticker: 50.0,
        mode="live", live_allow=set(), trade_log=trade_log, plan_store=_PlanStore())


def test_open_trade_suppresses_the_rearmed_signal(monkeypatch):
    log = _TradeLog(open_for={"AAA"})
    result = _run(monkeypatch, ["AAA", "BBB"], ("4w",), log)
    assert (result.opened, result.stored_only) == (1, 1)
    assert [call["ticker"] for call in log.logged] == ["BBB"]
    assert [plan.ticker for _, _, plan, _ in result.alerts] == ["BBB"]


def test_second_signal_same_ticker_same_scan_is_suppressed(monkeypatch):
    log = _TradeLog()
    result = _run(monkeypatch, ["AAA"], ("4w", "2m"), log)
    assert (result.opened, result.stored_only) == (1, 1)
    assert len(result.alerts) == 1 and len(log.logged) == 1
```

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_open_trade.py`
Expected: PASS. This test pins behaviour that already exists (`strategy_pass.py:128` gates on `trade_log.open_trade_for_ticker(ticker)`), so it is not red first. **If it FAILS, stop the PASS path** and ask the partner via `AskUserQuestion`: live would post a second alert that the backtest never measured. Do not change `run_strategy_pass` inside this plan. (`opened == 1` also guards against the pass's broad `except` silently swallowing an error.)

- [ ] **P2: Set the validated K**

In `swingbot/core/market/entry_filters.py`, replace:

```python
    # v108 re-arm: pullback touch *events* taken per held cross, per direction.
    # 1 = first touch only -- the pre-v108 entry, bit-for-bit. Changed only by
    # a v108 funnel verdict (docs/superpowers/results/*-v108-*.md).
    "max_touches_bull": 1, "max_touches_bear": 1,
```

with the following, where each passing direction gets its K and a failing or closed direction stays `1`:

```python
    # v108 re-arm: pullback touch *events* taken per held cross, per direction.
    # 1 = first touch only (pre-v108). Validated <date>
    # (docs/superpowers/results/<date>-v108-validation.md):
    # <direction> K=<k> Tier <t> -- TRAIN_EXT 2010-2023 N=<n> WR=<wr>% ExpR=<e>;
    # VALIDATION 2024-25 N=<n> WR=<wr>% ExpR=<e>. <other direction>: K=1 (<its stage/verdict>).
    "max_touches_bull": <K_bull>, "max_touches_bear": <K_bear>,
```

Every figure comes from the committed V108-6 and V108-7 JSONs (`pooled-numbers`).

- [ ] **P3: Update the gate comment**

In `swingbot/core/market/strategy_types.py`, directly after the line `# clears N>=15) -- CLOSED, stays WEAK, not gated here either` and its following `# (results/2026-09-10-v84-ema-crossover-preregistration.md).` line, insert:

```python
# v108 (<date>) re-armed the pullback entry (max_touches_<dir>=<k>, <direction>,
# Tier <t>; results/<date>-v108-validation.md). Still ungated: the badge is
# <VALIDATED | WEAK -- Tier 2 | WEAK -- one direction only, see backtest-methodology.md>.
```

- [ ] **P4: Replace the inert pin with the validated pin**

In `tests/market/test_ema_rearm.py`, replace `test_defaults_ship_inert` with:

```python
def test_v108_validated_defaults():
    # results/<date>-v108-validation.md -- change only with a new pre-registration.
    params = ef.DEFAULT_PARAMS["EMA Crossover"]
    assert (params["max_touches_bull"], params["max_touches_bear"]) == (<K_bull>, <K_bear>)
```

`test_default_entries_identical_to_the_legacy_path` now fails for the shipped direction by design, because the default is no longer K=1. Change its first line inside the test to pin K=1 explicitly, which keeps it the K=1 parity witness:

```python
    df = fixture()
    k1 = {"max_touches_bull": 1, "max_touches_bear": 1}
    new = {hk: ef.ema_cross_entries(df, hk, params=k1) for hk in HORIZONS}
```

and in the same test, change `old = {hk: ef.ema_cross_entries(df, hk) for hk in HORIZONS}` to `old = {hk: ef.ema_cross_entries(df, hk, params=k1) for hk in HORIZONS}`.

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`, then `python scripts/dev/testrun.py file tests/market/test_rescue_ema.py`.
Expected: both `0 failed`.

- [ ] **P5: Other tests that assert today's EMA Crossover entries**

Run: `python scripts/dev/testrun.py fast`. For each failure that names EMA Crossover entries or plans:
- If the test is a frozen **no-behaviour-change witness** (its docstring says it pins a pre-change result), pin `max_touches_bull`/`max_touches_bear` to `1` with `monkeypatch.setitem(entry_filters.DEFAULT_PARAMS["EMA Crossover"], "<key>", 1)` and a one-line reason.
- Otherwise it asserts production behaviour. Update its expectation to what the shipped K produces.

Never loosen an assertion or add an `xfail`. If the category is unclear, stop and ask.

- [ ] **P6: Registry row, only under V108-4's rule**

Only when **both** directions passed VALIDATION at Tier 1:

```bash
python scripts/backtest/measure_fib_v103.py emit-registry --validation-json docs/superpowers/results/<date>-v108-validation-E-bullish.json docs/superpowers/results/<date>-v108-validation-E-bearish.json --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

Then run `git diff swingbot/core/backtesting/validation_registry.json`. Expected: exactly the `EMA Crossover` row changed, with `run_date` `<date>` and `status` `VALIDATED` (or `WEAK` if the pooled badge failed, which `registry_status` decides). In every other case, **do not emit**, and the existing row stays as it is.

- [ ] **P7: Methodology row**

In `docs/claude/backtest-methodology.md`, add a row directly under the v84 EMA Crossover row (line 177), in the same style as the v103 rows:
- Mechanism: `EMA Crossover re-arm, first K pullback touch events per held cross, K ∈ {2,3} (v108 E)`.
- Per direction: the stage reached, K, tier, TRAIN_EXT and VALIDATION figures with N, and the added-trade implied ExpR.
- The badge outcome, and why (the registry-row rule).
- **Live-vs-backtest population:** live allows one open trade per ticker across all strategies and horizons, which is stricter than the backtest's per ticker × strategy × horizon `one_at_a_time`. So the live population is a subset of the measured one (P1's test pins this).
- Links to the four results docs.

- [ ] **P8: Complexity, commit, merge**

Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py swingbot/core/scanning/strategy_pass.py`
Expected: only the two legacy lines, `elliott_wave_entries - C (15)` and `run_strategy_pass - C (20)`, with unchanged scores.

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py tests/market/test_ema_rearm.py tests/scanning/test_strategy_pass_open_trade.py docs/claude/backtest-methodology.md
git commit -m "feat(v108): ship EMA Crossover re-arm -- <direction> K=<k> (Tier <t>), <other direction> K=1

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py tests/market/test_ema_rearm.py tests/scanning/test_strategy_pass_open_trade.py docs/claude/backtest-methodology.md
```

If P5 touched other test files, add them to both the `git add` and the pathspec. If P6 emitted, add `swingbot/core/backtesting/validation_registry.json` to both. Merge per `worktree-lifecycle`, after `git fetch` and a check of `git log --oneline main -5` for other sessions' commits. Leave `STRATEGY_ALERTS_MODE` and the live allow-list alone: whether EMA Crossover posts live is governed by them, not by this plan.

**NO-LIFT path** (every direction that did not pass). Runs on `main`.

- [ ] **N1: Methodology row**

In `docs/claude/backtest-methodology.md`, add a row directly under the v84 EMA Crossover row (line 177), in the same style as the v103 rows:
- Per direction: the stage it ended at (Stage 0 `min_n` / Stage 0 `inert` with K3/K1 / Stage 1 / Stage 2 / VALIDATION FAIL).
- The figures with N and window, and whether the VALIDATION shot was spent (FAIL, final) or remains unspent.
- Any horizon-concentration caveat from V108-5.
- What reopening needs: "a trigger other than the first K ∈ {2,3} fast-EMA touch events in 15 bars after a held cross".

State that the knobs stay `1` (inert code on `main`) and that EMA Crossover stays `WEAK` with its registry row untouched. If one direction shipped under the PASS path, this row covers only the other direction, and the PASS row names the shipped one.

- [ ] **N2: Commit**

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v108): close EMA Crossover re-arm <direction list> no-lift at <stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/claude/backtest-methodology.md
```

---

### Task V108-9: Full-suite verification and close-out

**Files:**
- Modify (PASS path only): `VERSION.json`, `swingbot/admin/version_history.json`
- Move: `docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md` → `docs/superpowers/specs/implemented/`, and `docs/superpowers/plans/2026-09-27-v108-ema-crossover-rearm-rescue.md` → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: everything above, merged on `main`.
- Produces: a green suite, the release (PASS only), and the closed documents.

- [ ] **Step 1: The one full-suite run**

Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full` on `main`. Require `0 failed` and `0 xfailed`. A red result is this plan's regressions: fix forward from the failures it names. If a failure passes in isolation and sits in code v108 never touched, report it with both outputs, and do not call the suite green.

- [ ] **Step 2 (PASS path only): Release `bot minor`**

Read `VERSION.json` from disk (never from this plan or memory). Increment `bot` at the **minor** level (reset the patch to 0), leave `ui` untouched, and set `bot_updated` to now in the `YYYY-MM-DD HH-MM-SS` format. Then run `python scripts/dev/build_version_matrix.py` and confirm with `git diff swingbot/admin/version_history.json` that the new pair appears.

```bash
git add VERSION.json swingbot/admin/version_history.json
git commit -m "release(v108): bot minor -- EMA Crossover re-arm ships <direction> K=<k>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- VERSION.json swingbot/admin/version_history.json
```

If the spec's `Bump:` prediction came out differently (for example, a Tier 2 ship that changed no badge), amend the spec's `Bump:` line in Step 3's commit, with one clause saying why.

- [ ] **Step 3: Move the documents to `implemented/`**

Both outcomes go to `implemented/`: the inert code landed on `main` in V108-3 (`document-lifecycle.md`).

```bash
git mv docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-27-v108-ema-crossover-rearm-rescue.md docs/superpowers/plans/implemented/
```

Then make two edits:
- In the moved spec, set `**Status:**` to `<Shipped <direction> K=<k> (Tier <t>) | Closed no-lift at <stage>> <date>; VALIDATION spent: <list or none>.`
- In the moved plan, fix the `**Spec:**` link so it still resolves (v107 needed a follow-up commit for exactly this). From `plans/implemented/`, the spec is at `../../specs/implemented/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`, so use that as the link target. Check it with `ls docs/superpowers/specs/implemented/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`.

```bash
git add docs/superpowers/specs/implemented/2026-09-27-v108-ema-crossover-rearm-rescue-design.md docs/superpowers/plans/implemented/2026-09-27-v108-ema-crossover-rearm-rescue.md
git commit -m "docs(v108): close out -- <shipped <direction> K=<k> | no-lift>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md docs/superpowers/plans/2026-09-27-v108-ema-crossover-rearm-rescue.md docs/superpowers/specs/implemented/2026-09-27-v108-ema-crossover-rearm-rescue-design.md docs/superpowers/plans/implemented/2026-09-27-v108-ema-crossover-rearm-rescue.md
```

- [ ] **Step 4: Remove the worktrees**

Remove `.claude/worktrees/2026-09-27-v108-ema-crossover-rearm-rescue` and, if it was created, the `-wiring` worktree, per `worktree-lifecycle`. Before deleting either branch, run `git rev-list --count main..<branch>`: it must print `0`. Otherwise **stop** and ask. Never touch a branch with `backup` in its name or any `stable-*` branch (`docs/claude/git-safety.md`).
