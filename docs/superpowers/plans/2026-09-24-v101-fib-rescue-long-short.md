# Fibonacci Rescue (Long/Short) Implementation Plan — Part 1: Phase A diagnostic

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-24-v101-fib-rescue-long-short-design.md`
**Bump:** none for this part (a TRAIN-only script and tests; no bot behaviour changes). Part 2 declares `bot minor` if a mechanism ships.
**Edge:** expectancy

**Goal:** A free, TRAIN-only diagnostic (`scripts/backtest/measure_fib_diagnostic.py`) that measures, per direction, whether one of three new mechanisms (#1 structural-stop filter, #2 deeper-ratio stop, #4 reclaim entry) can lift Fibonacci to WR ≥ 50 at N ≥ 30. Its verdict decides between writing Part 2 (pre-registration + flag + funnel + wiring) and closing v101 as no-lift.

**Architecture:** One script beside `measure_bearish_arms.py`, reusing its universe filter, laggard rule and `gate_override` pattern. Trades come from `run_backtest` (v2 exits, scale-out, TP2 levels, frictions), so the baseline and mechanism #1 use real backtest outcomes. Mechanisms #2 and #4 change the stop or entry, so they are compared **paired** under one simple first-touch simulator applied to both the baseline and the arm. The simulator's absolute numbers are not the backtest's; only the deltas are meaningful.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest.

## Global Constraints

- **TRAIN only: 2020-01-01..2023-12-31.** Never read or pass `--validation` / 2024–2025 data. No VALIDATION shot exists in this part.
- **No production code changes.** `STRATEGY_GATES` is lifted only inside the script via `entry_filters.gate_override`. `swingbot/` is not modified.
- **Closed and not re-runnable:** the v93 bearish arm (`results/2026-09-17-v93-bearish-arms-train.md`), v31's per-horizon grid (mechanism #3 is closed), the 2026-09-10 badge refresh, and v84's `FIB_TARGET_1_0_EXTENSION`. The diagnostic *reproduces* v93's bearish baseline as a sanity check; it does not re-decide it.
- **Success-bar constants copied from the spec:** `WR_FLOOR = 50.0`, `MIN_N = 30` (TRAIN, decided trades), scratch+timeout share ≤ 50%. The Phase A exit rule only looks at **pooled per-direction** cells. Per-horizon rows are description, never candidates (a mechanism × horizon pick is the closed #3 in disguise).
- **Diagnostic parameters are fixed before running:** `RECLAIM_WINDOW = 5` bars, `RATIO_LADDER = (0.382, 0.5, 0.618, 0.786, 1.0)`. Do not change them after seeing output. A grid over them belongs in Part 2's pre-registration with a plateau check.
- **NO-LOOKAHEAD:** plan geometry at bar `i` reads only bars `≤ i` (`fib_target_candidates` slices `df.iloc[:i+1]`, and the rolling swing series are trailing). The reclaim entry at bar `j` reads only bars `≤ j`. Exit simulation walks forward, as every harness here does. Load the `no-lookahead` skill before Task F101-2.
- **Never read `data/journal.json`.**
- **Tests:** iterate with `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`. The full suite runs once, in Task F101-6.
- **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- No `cd` in Bash commands (breaks the relative guardrails hook).
- Implement Tasks F101-1..3 on a branch in a worktree (`worktree-lifecycle` skill), not on `main`. Tasks F101-4..5 write docs, which go on `main`.

## Parallelisation

- **Sequential:** F101-1 → F101-2 → F101-3 (each imports the previous task's functions from the same file) → F101-4 (runs the finished script) → F101-5 (reads F101-4's numbers) → F101-6.
- No parallel groups: one script file, one test file.
- **Cross-plan:** v100 (arm producer) is live and unimplemented. This part touches none of its files (`validate_component.py`, `measure_arms.py`, `swingbot/core/backtesting/arms/`). Part 2 must check whether v100 has merged before choosing its funnel tooling.

---

# Phase A — Diagnostic

### Task F101-1: Geometry and first-touch simulator helpers

**Files:**
- Create: `scripts/backtest/measure_fib_diagnostic.py`
- Test: `tests/scripts/test_measure_fib_diagnostic.py`

**Interfaces:**
- Consumes: `swingbot.core.planning.params.STRUCTURE_BUFFER_ATR` (0.25), `swingbot.core.risk_limits.capped_planned_loss_pct(configured_pct) -> float`, `swingbot.core.market.strategy_types.HORIZONS` (`max_risk_pct`, `max_holding_days`, `fib_lookback`).
- Produces (all module-level in `measure_fib_diagnostic`):
  - `fib_level(swing_high: float, swing_low: float, ratio: float, direction: str) -> float`
  - `tested_ratio(close: float, swing_high: float, swing_low: float, direction: str, ratios=ENTRY_RATIOS) -> float`
  - `structural_stop(swing_high, swing_low, atr_val, direction) -> float`
  - `deeper_ratio_stop(close, swing_high, swing_low, atr_val, direction) -> float`
  - `cap_distance(entry: float, horizon_key: str) -> float`
  - `apply_cap(entry, stop, direction, cap) -> tuple[float, bool]` (stop, capped?)
  - `simulate_first_touch(high, low, close, start, entry, stop, target, direction, max_hold) -> tuple[str, float | None]` with outcome in `"win" | "loss" | "timeout" | "open"`
  - `reclaim_bar(high, low, close, i, direction, window=RECLAIM_WINDOW) -> int | None`
  - constants `ENTRY_RATIOS`, `RATIO_LADDER`, `RECLAIM_WINDOW`, `WR_FLOOR`, `MIN_N`, `STRATEGY`

- [ ] **Step 1: Write the failing tests**

```python
"""v101 Phase A: Fibonacci mechanism diagnostic (TRAIN only)."""
import sys
from pathlib import Path
from types import SimpleNamespace as T

import numpy as np
import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _mfd():
    import measure_fib_diagnostic as mfd
    return mfd


def test_fib_level_bull_measures_down_from_the_high():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.5, "bullish") == pytest.approx(105.0)
    assert mfd.fib_level(110.0, 100.0, 0.382, "bullish") == pytest.approx(106.18)


def test_fib_level_bear_measures_up_from_the_low():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.382, "bearish") == pytest.approx(103.82)


def test_tested_ratio_is_the_nearest_entry_ratio():
    mfd = _mfd()
    # bullish levels: 0.382 -> 106.18, 0.5 -> 105.0, 0.618 -> 103.82
    assert mfd.tested_ratio(104.0, 110.0, 100.0, "bullish") == 0.618
    assert mfd.tested_ratio(106.0, 110.0, 100.0, "bullish") == 0.382


def test_structural_stop_sits_one_buffer_beyond_the_swing_extreme():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bullish") == pytest.approx(100.0 - buf)
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bearish") == pytest.approx(110.0 + buf)


def test_deeper_ratio_stop_uses_the_next_ratio_on_the_ladder():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    # close 104 tests 0.618 -> deeper is 0.786 -> level 110 - 7.86 = 102.14
    assert mfd.deeper_ratio_stop(104.0, 110.0, 100.0, 2.0, "bullish") == pytest.approx(102.14 - buf)
    # bearish close 106.2 tests 0.618 (100 + 6.18) -> deeper 0.786 -> 107.86
    assert mfd.deeper_ratio_stop(106.2, 110.0, 100.0, 2.0, "bearish") == pytest.approx(107.86 + buf)


def test_apply_cap_pulls_a_too_wide_stop_in_and_flags_it():
    mfd = _mfd()
    assert mfd.apply_cap(100.0, 90.0, "bullish", 5.0) == (pytest.approx(95.0), True)
    assert mfd.apply_cap(100.0, 97.0, "bullish", 5.0) == (pytest.approx(97.0), False)
    assert mfd.apply_cap(100.0, 110.0, "bearish", 5.0) == (pytest.approx(105.0), True)


def test_cap_distance_matches_the_builder_arithmetic():
    mfd = _mfd()
    pct = mfd.capped_planned_loss_pct(mfd.HORIZONS["4w"]["max_risk_pct"])
    assert mfd.cap_distance(200.0, "4w") == pytest.approx(200.0 * pct / 100)


def test_first_touch_checks_the_stop_before_the_target_on_the_same_bar():
    mfd = _mfd()
    high, low, close = np.array([100, 112.0]), np.array([100, 94.0]), np.array([100, 100.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("loss", -1.0)


def test_first_touch_win_pays_the_planned_r():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 111.0]), np.array([100, 99, 100.0]), np.array([100, 100, 110.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_bearish_win():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 100.0]), np.array([100, 99, 89.0]), np.array([100, 100, 90.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 105.0, 90.0, "bearish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_timeout_marks_to_the_last_close_in_the_hold():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 103, 150.0]), np.array([100, 99, 99, 99.0]), np.array([100, 100, 102, 150.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 2) == ("timeout", pytest.approx(0.4))


def test_first_touch_is_open_when_no_forward_bar_exists():
    mfd = _mfd()
    a = np.array([100.0])
    assert mfd.simulate_first_touch(a, a, a, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("open", None)


def test_reclaim_bar_is_the_first_close_beyond_the_signal_bar_extreme():
    mfd = _mfd()
    high = np.array([101, 100, 100, 100.0])
    low = np.array([99, 98, 98, 98.0])
    close = np.array([100, 99, 101.5, 102.0])
    assert mfd.reclaim_bar(high, low, close, 0, "bullish") == 2
    assert mfd.reclaim_bar(high, low, close, 0, "bearish") is None
    assert mfd.reclaim_bar(high, low, close, 0, "bullish", window=1) is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'measure_fib_diagnostic'`.

- [ ] **Step 3: Write the helpers**

```python
#!/usr/bin/env python3
"""v101 Phase A: can a new mechanism lift Fibonacci to WR >= 50 at N >= 30?

TRAIN only (2020-01-01..2023-12-31); never spends VALIDATION. Measures, per
direction, three mechanisms the closed rows never tried:

  #1 structural-stop filter -- drop plans whose stop the max_risk_pct cap
     pulled in from the swing extreme (real v2 backtest outcomes, a pure
     partition of the baseline trades).
  #2 deeper-ratio stop -- stop one buffer beyond the next deeper fib ratio
     instead of the swing extreme, target re-selected for the new risk.
  #4 reclaim entry -- enter on the first close back beyond the signal bar's
     extreme within RECLAIM_WINDOW bars, same stop, target re-selected.

#2 and #4 change the geometry, so they are compared PAIRED against the same
trades' baseline under one first-touch simulator (simulate_first_touch).
Its absolute numbers are not the backtest's; its deltas are the signal.

Mechanism #3 (horizon split) is closed by v31 and the bearish baseline by v93
(docs/claude/backtest-methodology.md). Per-horizon rows are printed as
description only, and the bearish baseline must reproduce v93 exactly.

Run:
  python scripts/backtest/measure_fib_diagnostic.py \\
      --out docs/superpowers/results/<date>-v101-fib-diagnostic.json \\
      --md  docs/superpowers/results/<date>-v101-fib-diagnostic-table.md
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR  # noqa: E402
from swingbot.core.risk_limits import capped_planned_loss_pct  # noqa: E402

STRATEGY = "Fibonacci"
ENTRY_RATIOS = (0.382, 0.5, 0.618)              # DEFAULT_PARAMS["Fibonacci"]["ratios"]
RATIO_LADDER = (0.382, 0.5, 0.618, 0.786, 1.0)  # fixed before the run; 1.0 == the swing extreme
RECLAIM_WINDOW = 5                              # fixed before the run
WR_FLOOR = 50.0                                 # badge clause, spec "Success bar"
MIN_N = 30                                      # TRAIN decided-trade floor, spec "Success bar"
MAX_SCRATCH_SHARE = 0.5


def fib_level(swing_high, swing_low, ratio, direction):
    """Retracement level of the impulse being traded: measured down from the
    high for a bullish (up-impulse) pullback, up from the low for bearish."""
    rng = swing_high - swing_low
    return swing_high - ratio * rng if direction == "bullish" else swing_low + ratio * rng


def tested_ratio(close, swing_high, swing_low, direction, ratios=ENTRY_RATIOS):
    return min(ratios, key=lambda r: abs(close - fib_level(swing_high, swing_low, r, direction)))


def structural_stop(swing_high, swing_low, atr_val, direction):
    """The stop _fibonacci_plan builds before the risk cap (builders.py)."""
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return swing_low - buf if direction == "bullish" else swing_high + buf


def deeper_ratio_stop(close, swing_high, swing_low, atr_val, direction):
    ratio = tested_ratio(close, swing_high, swing_low, direction)
    deeper = RATIO_LADDER[RATIO_LADDER.index(ratio) + 1]
    level = fib_level(swing_high, swing_low, deeper, direction)
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return level - buf if direction == "bullish" else level + buf


def cap_distance(entry, horizon_key):
    """Max risk per share, the same arithmetic _fibonacci_plan applies."""
    return entry * (capped_planned_loss_pct(HORIZONS[horizon_key]["max_risk_pct"]) / 100)


def apply_cap(entry, stop, direction, cap):
    if abs(entry - stop) > cap:
        return (entry - cap if direction == "bullish" else entry + cap), True
    return stop, False


def simulate_first_touch(high, low, close, start, entry, stop, target, direction, max_hold):
    """Walk bars start+1 .. start+max_hold. The stop is checked before the
    target on the same bar (the conservative ordering the badge uses).
    No scale-out, no trailing: a paired yardstick, not the v2 engine."""
    risk = abs(entry - stop)
    last = min(start + max_hold, len(close) - 1)
    if last <= start or risk <= 0:
        return "open", None
    bull = direction == "bullish"
    for j in range(start + 1, last + 1):
        if bull:
            if low[j] <= stop:
                return "loss", -1.0
            if high[j] >= target:
                return "win", (target - entry) / risk
        else:
            if high[j] >= stop:
                return "loss", -1.0
            if low[j] <= target:
                return "win", (entry - target) / risk
    r = (close[last] - entry) / risk if bull else (entry - close[last]) / risk
    return "timeout", r


def reclaim_bar(high, low, close, i, direction, window=RECLAIM_WINDOW):
    """First bar j in (i, i+window] closing beyond the signal bar's extreme.
    Reads only bars <= j, so an entry at j's close is knowable at j."""
    for j in range(i + 1, min(i + window, len(close) - 1) + 1):
        if direction == "bullish" and close[j] > high[i]:
            return j
        if direction == "bearish" and close[j] < low[i]:
            return j
    return None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: PASS, 13 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fib_diagnostic.py tests/scripts/test_measure_fib_diagnostic.py
git commit -m "feat(v101): Fibonacci diagnostic geometry and first-touch simulator"
```

---

### Task F101-2: Per-trade features, aggregation and the Phase A exit rule

Load the `no-lookahead` skill first: `trade_features` builds geometry at bars `i` and `j`.

**Files:**
- Modify: `scripts/backtest/measure_fib_diagnostic.py` (append below the Task F101-1 helpers)
- Test: `tests/scripts/test_measure_fib_diagnostic.py` (append)

**Interfaces:**
- Consumes: Task F101-1 helpers; `swingbot.core.planning.targets.fib_target_candidates(df, index, h, entry) -> list[float]` (slices `df.iloc[:index+1]`); `swingbot.core.planning.targets.select_structural_target(entry, stop_loss, is_bull, candidate_levels, min_rr, max_rr) -> float | None`; `swingbot.core.backtesting.arm_rule.pooled_stats(trades) -> dict` (keys `n`, `wins`, `losses`, `win_rate` in percent, `expectancy_r`, `scratch_timeout_share`) and `stage1_verdict(pooled, folds) -> dict` (keys `clears`, `clauses`, `good_folds`); `swingbot.core.backtesting.backtest_wf.ANCHORED_FOLDS` (4-tuples, test window at `[2]`/`[3]`).
- Produces:
  - `trade_features(frame, i, horizon_key, trade, atr_val, swing_high, swing_low, cap, min_rr, max_rr) -> dict` with keys `capped: bool`, `stop_mismatch: bool`, `tested_ratio: float`, `stop_atr: float`, `base_simple: (outcome, r)`, `deeper: (outcome, r)`, `reclaim: (outcome, r)`. `deeper`/`reclaim` outcome may also be `"no_target"`, and `reclaim` may be `"no_reclaim"`.
  - `simple_stats(pairs) -> dict` with keys `n` (decided), `win_rate` (percent or None), `expectancy_r`, `closed`, `dropped`
  - `summarise(records) -> dict`: `{"bullish": direction_summary, "bearish": direction_summary, "candidates": [...]}`. A record is `{"ticker", "horizon_key", "trade", "features"}`.
  - `direction_summary(rows) -> dict` with keys `n_rows`, `baseline`, `cap_rate`, `structural_only`, `capped_only`, `deeper_stop`, `reclaim`, `stop_mismatch`, `horizons`. `baseline` / `structural_only` / `capped_only` are `{"pooled", "folds", "verdict"}`.
  - `phase_a_candidates(summary) -> list[dict]`, each `{"direction", "mechanism", "stats"}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fib_diagnostic.py`:

```python
def _impulse_frame():
    # 30-bar up impulse, then a 15-bar pullback, then a flat tail.
    closes = [100 + k for k in range(30)] + [129 - 0.8 * k for k in range(1, 16)] + [117.0] * 25
    return make_ohlcv(closes, start="2021-01-04")


def _trade(frame, i, direction, stop, target):
    entry = float(frame["Close"].iloc[i])
    return T(entry_date=str(frame.index[i].date()), direction=direction, entry=entry,
             stop_loss=stop, take_profit=target, outcome="win", r_multiple=1.0)


def test_trade_features_flags_capped_only_when_the_cap_binds():
    mfd = _mfd()
    frame, i = _impulse_frame(), 44
    entry = float(frame["Close"].iloc[i])
    hi, lo = float(frame["High"].iloc[i - 42:i + 1].max()), float(frame["Low"].iloc[i - 42:i + 1].min())
    trade = _trade(frame, i, "bullish", entry * 0.9, entry * 1.2)
    wide = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5)
    tight = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 0.01, 1.5, 2.5)
    assert wide["capped"] is False and tight["capped"] is True
    assert set(wide) == {"capped", "stop_mismatch", "tested_ratio", "stop_atr",
                         "base_simple", "deeper", "reclaim"}
    assert wide["tested_ratio"] in mfd.ENTRY_RATIOS


def test_trade_features_never_reads_past_the_signal_bar_for_geometry():
    mfd = _mfd()
    frame, i = _impulse_frame(), 44
    entry = float(frame["Close"].iloc[i])
    hi, lo = float(frame["High"].iloc[i - 42:i + 1].max()), float(frame["Low"].iloc[i - 42:i + 1].min())
    trade = _trade(frame, i, "bullish", entry * 0.9, entry * 1.2)
    base = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5)
    poisoned = frame.copy()
    poisoned.iloc[i + 1:, :4] = poisoned.iloc[i + 1:, :4] * 3   # future bars only
    again = mfd.trade_features(poisoned, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5)
    # Geometry (cap flag, tested ratio, stop distance) must not see the future.
    assert (again["capped"], again["tested_ratio"], again["stop_atr"]) == \
           (base["capped"], base["tested_ratio"], base["stop_atr"])


def test_simple_stats_counts_decided_and_drops_non_trades():
    mfd = _mfd()
    pairs = [("win", 2.0), ("loss", -1.0), ("timeout", 0.5), ("no_target", None), ("open", None)]
    s = mfd.simple_stats(pairs)
    assert s["n"] == 2 and s["win_rate"] == pytest.approx(50.0)
    assert s["expectancy_r"] == pytest.approx((2.0 - 1.0 + 0.5) / 3)
    assert s["closed"] == 3 and s["dropped"] == 2


def _record(direction, horizon, outcome, r, capped, entry_date="2021-06-01"):
    trade = T(direction=direction, entry_date=entry_date, outcome=outcome, r_multiple=r)
    features = {"capped": capped, "stop_mismatch": False, "tested_ratio": 0.5, "stop_atr": 2.0,
                "base_simple": (outcome, r), "deeper": (outcome, r), "reclaim": ("no_reclaim", None)}
    return {"ticker": "AAA", "horizon_key": horizon, "trade": trade, "features": features}


def test_summarise_partitions_capped_and_structural():
    mfd = _mfd()
    rows = ([_record("bullish", "3m", "win", 2.0, False) for _ in range(3)]
            + [_record("bullish", "3m", "loss", -1.0, True) for _ in range(2)])
    out = mfd.summarise(rows)
    bull = out["bullish"]
    assert bull["n_rows"] == 5 and bull["cap_rate"] == pytest.approx(0.4)
    assert bull["structural_only"]["pooled"]["win_rate"] == pytest.approx(100.0)
    assert bull["capped_only"]["pooled"]["win_rate"] == pytest.approx(0.0)
    assert out["bearish"]["n_rows"] == 0
    assert set(bull["horizons"]) == set(mfd.HORIZONS)


def test_phase_a_candidates_needs_both_the_wr_floor_and_n():
    mfd = _mfd()
    thin = [_record("bullish", "3m", "win", 2.0, False) for _ in range(29)]
    assert mfd.summarise(thin)["candidates"] == []
    enough = thin + [_record("bullish", "3m", "win", 2.0, False)]
    cands = mfd.summarise(enough)["candidates"]
    assert {(c["direction"], c["mechanism"]) for c in cands} >= {("bullish", "#1 structural_only")}
```

- [ ] **Step 2: Run the tests and confirm the new ones fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: FAIL, `AttributeError: module 'measure_fib_diagnostic' has no attribute 'trade_features'` (the 13 Task F101-1 tests still pass).

- [ ] **Step 3: Write the implementation**

Append to `scripts/backtest/measure_fib_diagnostic.py`. Put these imports with the others at the top of the file:

```python
from swingbot.core.backtesting import arm_rule  # noqa: E402
from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS  # noqa: E402
from swingbot.core.planning.targets import fib_target_candidates, select_structural_target  # noqa: E402
```

Then the functions:

```python
DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)


def trade_features(frame, i, horizon_key, trade, atr_val, swing_high, swing_low, cap, min_rr, max_rr):
    """Everything the three mechanisms need about one baseline trade.

    Geometry (cap flag, ratio, stop distance, re-selected targets) reads bars
    <= i, or <= j for the reclaim entry. Only simulate_first_touch walks
    forward, which is an exit, the same as run_backtest."""
    h = HORIZONS[horizon_key]
    direction, entry = trade.direction, trade.entry
    is_bull = direction == "bullish"
    high, low, close = frame["High"].values, frame["Low"].values, frame["Close"].values
    hold = h["max_holding_days"]

    struct = structural_stop(swing_high, swing_low, atr_val, direction)
    expected_stop, capped = apply_cap(entry, struct, direction, cap)
    # The builder's own stop should equal expected_stop; a mismatch means the
    # diagnostic's geometry drifted from _fibonacci_plan and #1 is unreliable.
    stop_mismatch = abs(trade.stop_loss - expected_stop) > 1e-6 * entry

    base = simulate_first_touch(high, low, close, i, entry, trade.stop_loss,
                                trade.take_profit, direction, hold)

    # #2: stop beyond the next deeper ratio (still risk-capped), new target.
    deep_stop, _ = apply_cap(entry, deeper_ratio_stop(close[i], swing_high, swing_low, atr_val, direction),
                             direction, cap)
    deep_target = select_structural_target(entry, deep_stop, is_bull,
                                           fib_target_candidates(frame, i, h, entry), min_rr, max_rr)
    deeper = (simulate_first_touch(high, low, close, i, entry, deep_stop, deep_target, direction, hold)
              if deep_target is not None else ("no_target", None))

    # #4: enter on the reclaim close, same stop, target re-selected at j.
    j = reclaim_bar(high, low, close, i, direction)
    if j is None:
        reclaim = ("no_reclaim", None)
    else:
        entry_j = float(close[j])
        still_valid = entry_j > trade.stop_loss if is_bull else entry_j < trade.stop_loss
        target_j = (select_structural_target(entry_j, trade.stop_loss, is_bull,
                                             fib_target_candidates(frame, j, h, entry_j), min_rr, max_rr)
                    if still_valid else None)
        reclaim = (simulate_first_touch(high, low, close, j, entry_j, trade.stop_loss, target_j, direction, hold)
                   if target_j is not None else ("no_target", None))

    return {
        "capped": bool(capped),
        "stop_mismatch": bool(stop_mismatch),
        "tested_ratio": tested_ratio(close[i], swing_high, swing_low, direction),
        "stop_atr": abs(entry - trade.stop_loss) / atr_val if atr_val else None,
        "base_simple": base,
        "deeper": deeper,
        "reclaim": reclaim,
    }


def simple_stats(pairs):
    closed = [(o, r) for o, r in pairs if o in ("win", "loss", "timeout")]
    decided = [o for o, _ in closed if o in ("win", "loss")]
    wins = sum(o == "win" for o in decided)
    returns = [r for _, r in closed if r is not None]
    return {"n": len(decided),
            "win_rate": wins / len(decided) * 100 if decided else None,
            "expectancy_r": sum(returns) / len(returns) if returns else None,
            "closed": len(closed),
            "dropped": len(pairs) - len(closed)}


def _real(rows):
    """Real v2 backtest outcomes, pooled plus the anchored test-year folds
    the v93 Stage 1 rule reads."""
    trades = [r["trade"] for r in rows]
    pooled = arm_rule.pooled_stats(trades)
    folds = [{"test_year": start[:4],
              "stats": arm_rule.pooled_stats([r["trade"] for r in rows
                                              if start <= r["trade"].entry_date <= end])}
             for _, _, start, end in ANCHORED_FOLDS]
    return {"pooled": pooled, "folds": folds, "verdict": arm_rule.stage1_verdict(pooled, folds)}


def direction_summary(rows):
    structural = [r for r in rows if not r["features"]["capped"]]
    capped = [r for r in rows if r["features"]["capped"]]
    reclaimed = [r for r in rows if r["features"]["reclaim"][0] != "no_reclaim"]
    return {
        "n_rows": len(rows),
        "baseline": _real(rows),
        "cap_rate": len(capped) / len(rows) if rows else None,
        "structural_only": _real(structural),
        "capped_only": _real(capped),
        "deeper_stop": {"base_simple": simple_stats([r["features"]["base_simple"] for r in rows]),
                        "arm": simple_stats([r["features"]["deeper"] for r in rows])},
        "reclaim": {"reclaim_rate": len(reclaimed) / len(rows) if rows else None,
                    "base_simple": simple_stats([r["features"]["base_simple"] for r in reclaimed]),
                    "arm": simple_stats([r["features"]["reclaim"] for r in reclaimed])},
        "stop_mismatch": sum(r["features"]["stop_mismatch"] for r in rows),
        # Description only -- mechanism #3 is closed (v31).
        "horizons": {h: {"baseline": arm_rule.pooled_stats([r["trade"] for r in rows if r["horizon_key"] == h]),
                         "structural_only": arm_rule.pooled_stats([r["trade"] for r in structural
                                                                   if r["horizon_key"] == h])}
                     for h in ALL_HZ},
    }


def _clears(stats):
    return (stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR
            and (stats.get("n") or 0) >= MIN_N)


def phase_a_candidates(summary):
    """The spec's Phase A exit rule: pooled per-direction cells only."""
    out = []
    for d in DIRECTIONS:
        s = summary[d]
        cells = {"#1 structural_only": s["structural_only"]["pooled"],
                 "#2 deeper_stop": s["deeper_stop"]["arm"],
                 "#4 reclaim": s["reclaim"]["arm"]}
        out.extend({"direction": d, "mechanism": k, "stats": v} for k, v in cells.items() if _clears(v))
    return out


def summarise(records):
    out = {d: direction_summary([r for r in records if r["trade"].direction == d]) for d in DIRECTIONS}
    out["candidates"] = phase_a_candidates(out)
    return out
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: PASS, 18 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fib_diagnostic.py tests/scripts/test_measure_fib_diagnostic.py
git commit -m "feat(v101): per-trade mechanism features and Phase A exit rule"
```

---

### Task F101-3: Collection passes, reproduction check, report and CLI

**Files:**
- Modify: `scripts/backtest/measure_fib_diagnostic.py` (append)
- Test: `tests/scripts/test_measure_fib_diagnostic.py` (append)

**Interfaces:**
- Consumes: `run_backtest_range` (sibling script) `TRAIN`, `_build_asof_map(tickers, frames, universe)`, `_tickers_for_run(universe)`, `_with_context(df)`, `load_cached(ticker)`, `window_trades(summary, date_from, date_to)`; `measure_bearish_arms` (sibling) `_unmasked_gates(strategy) -> dict`, `apply_laggard_rule(rows) -> rows`; `swingbot.core.backtesting.backtest.run_backtest`, `_plan_series(df, strategy, horizon_key) -> (atr, swing_high, swing_low, volume_ratio, entry_levels)`; `swingbot.core.planning.plan_engine._safe_atr_value(entry, atr) -> float`; `swingbot.core.market.entry_filters.gate_override(strategy, gates)`; `swingbot.scan_params.ScanParams.from_config()` (`min_risk_reward_ratio`, `max_risk_reward_ratio`); `swingbot.core.marketdata.universe.liquidity_reason`, `data_quality_issues`.
- Produces:
  - `collect(frames, asof_map, *, horizons=ALL_HZ, run_fn=None) -> tuple[list[dict], dict]` (records, meta with `bearish_before_rs`, `bearish_after_rs`)
  - `reproduction_report(summary, meta) -> dict` with key `v93_exact: bool`
  - `render_markdown(result) -> str`
  - `main(argv=None) -> int`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def _fake_summary(frame, i):
    entry = float(frame["Close"].iloc[i])
    d = str(frame.index[i].date())
    return T(trades=[
        T(direction="bullish", entry_date=d, entry=entry, stop_loss=entry * 0.95,
          take_profit=entry * 1.1, outcome="win", r_multiple=2.0, context={}),
        T(direction="bearish", entry_date=d, entry=entry, stop_loss=entry * 1.05,
          take_profit=entry * 0.9, outcome="loss", r_multiple=-1.0, context={"rs_combined": 10.0}),
        T(direction="bearish", entry_date=d, entry=entry, stop_loss=entry * 1.05,
          take_profit=entry * 0.9, outcome="win", r_multiple=2.0, context={"rs_combined": 80.0}),
    ])


def test_collect_takes_bulls_from_the_live_pass_and_laggard_bears_from_the_unmasked_pass():
    mfd = _mfd()
    frame = make_ohlcv([100 + 0.1 * k for k in range(300)], start="2020-01-01")
    seen_gates = []

    def run_fn(ticker, df, strategy, horizon, **kw):
        seen_gates.append(dict(mfd.STRATEGY_GATES.get(strategy) or {}))
        return _fake_summary(df, 250)

    records, meta = mfd.collect({"AAA": frame}, {}, horizons=("3m",), run_fn=run_fn)
    assert [r["trade"].direction for r in records] == ["bullish", "bearish"]
    assert meta == {"bearish_before_rs": 2, "bearish_after_rs": 1}
    assert seen_gates[0].get("directions") == ("bullish",)            # live gate
    assert seen_gates[1].get("directions") == ("bullish", "bearish")  # unmasked
    assert mfd.STRATEGY_GATES["Fibonacci"]["directions"] == ("bullish",)  # restored
    assert set(records[0]["features"]) >= {"capped", "deeper", "reclaim"}


def test_reproduction_report_is_exact_only_on_the_v93_figures():
    mfd = _mfd()
    pooled = {"n": 89, "win_rate": 21.3, "expectancy_r": -0.255}
    summary = {"bearish": {"baseline": {"pooled": pooled}}, "bullish": {"baseline": {"pooled": {}}}}
    ok = mfd.reproduction_report(summary, {"bearish_before_rs": 226, "bearish_after_rs": 107})
    off = mfd.reproduction_report(summary, {"bearish_before_rs": 225, "bearish_after_rs": 107})
    assert ok["v93_exact"] is True and off["v93_exact"] is False


def test_render_markdown_names_every_mechanism_and_the_reproduction_line():
    mfd = _mfd()
    rows = [_record("bullish", "3m", "win", 2.0, False) for _ in range(3)]
    result = mfd.summarise(rows)
    result["reproduction"] = mfd.reproduction_report(result, {"bearish_before_rs": 0, "bearish_after_rs": 0})
    md = mfd.render_markdown(result)
    for needle in ("#1 structural_only", "#2 deeper_stop", "#4 reclaim", "v93 reproduction", "Candidates"):
        assert needle in md
```

- [ ] **Step 2: Run the tests and confirm the new ones fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: FAIL, `AttributeError: ... has no attribute 'collect'`.

- [ ] **Step 3: Write the implementation**

Add these imports at the top of the file with the others:

```python
from measure_bearish_arms import _unmasked_gates, apply_laggard_rule  # noqa: E402
from run_backtest_range import (  # noqa: E402
    TRAIN, _build_asof_map, _tickers_for_run, _with_context, load_cached, window_trades,
)
from swingbot.core.backtesting.backtest import _plan_series, run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import gate_override  # noqa: E402
from swingbot.core.market.strategy_types import STRATEGY_GATES  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402
from swingbot.core.planning.plan_engine import _safe_atr_value  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402
```

Then append:

```python
# v93's bearish Fibonacci row (results/2026-09-17-v93-bearish-arms-train.md).
# Same universe filter, same unmasked pass, same laggard rule: must match exactly.
V93_BEARISH = {"before_rs": 226, "after_rs": 107, "n": 89, "win_rate": 21.3, "expectancy_r": -0.255}
# Registry row (run_backtest_range universe, which filters differently): approximate only.
REGISTRY_BULLISH = {"n": 246, "win_rate": 35.4, "expectancy_r": 0.232}


def _features_for(frame, horizon_key, trade, series, rr):
    atr_s, sh_s, sl_s = series
    i = frame.index.get_loc(pd.Timestamp(trade.entry_date))
    atr_val = _safe_atr_value(trade.entry, float(atr_s.iloc[i]))
    return trade_features(frame, i, horizon_key, trade, atr_val, float(sh_s.iloc[i]), float(sl_s.iloc[i]),
                          cap_distance(trade.entry, horizon_key), *rr)


def collect(frames, asof_map, *, horizons=ALL_HZ, run_fn=None):
    """Two passes. Bullish trades come from the LIVE gate, so an unmasked
    bearish trade never blocks a bullish one under one_at_a_time. Bearish
    trades come from v93's unmasked pass plus its laggard rule."""
    run_fn = run_fn or run_backtest
    params = ScanParams.from_config()
    rr = (params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    total = len(frames) * len(horizons) * len(DIRECTIONS)
    done, records, meta = 0, [], {}
    for direction in DIRECTIONS:
        ctx = (gate_override(STRATEGY, _unmasked_gates(STRATEGY)) if direction == "bearish"
               else contextlib.nullcontext())
        rows = []
        with ctx:
            for ticker, frame in sorted(frames.items()):
                for h in horizons:
                    done += 1
                    print(f"[{done}/{total}] {done / total * 100:.0f}% {direction} {ticker} {h}", flush=True)
                    summary = run_fn(ticker, frame, STRATEGY, h, one_at_a_time=True, exit_model="v2",
                                     scale_out=True, tp2_mode="levels", frictions=True,
                                     asof=asof_map.get(ticker))
                    trades = [t for t in window_trades(summary, *TRAIN) if t.direction == direction]
                    if not trades:
                        continue
                    atr_s, sh_s, sl_s, _, _ = _plan_series(frame, STRATEGY, h)
                    rows.extend({"ticker": ticker, "horizon_key": h, "trade": t,
                                 "features": _features_for(frame, h, t, (atr_s, sh_s, sl_s), rr)}
                                for t in trades)
        if direction == "bearish":
            meta["bearish_before_rs"] = len(rows)
            rows = apply_laggard_rule(rows)
            meta["bearish_after_rs"] = len(rows)
        records.extend(rows)
    return records, meta


def reproduction_report(summary, meta):
    bear = summary["bearish"]["baseline"]["pooled"]
    observed = {"before_rs": meta.get("bearish_before_rs"), "after_rs": meta.get("bearish_after_rs"),
                "n": bear.get("n"),
                "win_rate": None if bear.get("win_rate") is None else round(bear["win_rate"], 1),
                "expectancy_r": None if bear.get("expectancy_r") is None else round(bear["expectancy_r"], 3)}
    return {"v93_expected": V93_BEARISH, "v93_observed": observed, "v93_exact": observed == V93_BEARISH,
            "registry_bullish_expected": REGISTRY_BULLISH,
            "bullish_observed": summary["bullish"]["baseline"]["pooled"],
            "note": "bullish uses the v93 universe filter, not run_backtest_range's; expect an approximate match"}


def _fmt(s):
    wr = "—" if s.get("win_rate") is None else f"{s['win_rate']:.1f}%"
    er = "—" if s.get("expectancy_r") is None else f"{s['expectancy_r']:+.3f}"
    return f"{s.get('n', 0)} | {wr} | {er}"


def render_markdown(result):
    lines = ["| Direction | Cell | N (decided) | WR | ExpR |", "|---|---|---:|---:|---:|"]
    for d in DIRECTIONS:
        s = result[d]
        cells = [("baseline (v2)", s["baseline"]["pooled"]),
                 ("#1 structural_only (v2)", s["structural_only"]["pooled"]),
                 ("#1 capped_only (v2)", s["capped_only"]["pooled"]),
                 ("#2 deeper_stop base (simple)", s["deeper_stop"]["base_simple"]),
                 ("#2 deeper_stop arm (simple)", s["deeper_stop"]["arm"]),
                 ("#4 reclaim base (simple)", s["reclaim"]["base_simple"]),
                 ("#4 reclaim arm (simple)", s["reclaim"]["arm"])]
        lines += [f"| {d} | {name} | {_fmt(st)} |" for name, st in cells]
    lines += ["", "| Direction | cap rate | reclaim rate | stop mismatches |", "|---|---:|---:|---:|"]
    for d in DIRECTIONS:
        s = result[d]
        cap = "—" if s["cap_rate"] is None else f"{s['cap_rate'] * 100:.1f}%"
        rec = "—" if s["reclaim"]["reclaim_rate"] is None else f"{s['reclaim']['reclaim_rate'] * 100:.1f}%"
        lines.append(f"| {d} | {cap} | {rec} | {s['stop_mismatch']} |")
    lines += ["", "Per-horizon rows (description only; #3 is closed):", "",
              "| Direction | Horizon | baseline N / WR / ExpR | #1 structural N / WR / ExpR |",
              "|---|---|---|---|"]
    for d in DIRECTIONS:
        for h, row in result[d]["horizons"].items():
            lines.append(f"| {d} | {h} | {_fmt(row['baseline'])} | {_fmt(row['structural_only'])} |")
    rep = result["reproduction"]
    lines += ["", f"**v93 reproduction:** exact={rep['v93_exact']} "
                  f"observed={rep['v93_observed']} expected={rep['v93_expected']}", "",
              "**Candidates** (pooled per-direction cells with WR >= 50 and N >= 30):", ""]
    lines += ([f"- {c['direction']} {c['mechanism']}: {_fmt(c['stats'])}" for c in result["candidates"]]
              or ["- none"])
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v101 Phase A Fibonacci diagnostic (TRAIN only)")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument("--md", help="markdown table output path")
    ap.add_argument("--universe")
    ap.add_argument("--tickers", help="comma-separated subset, for smoke runs only")
    args = ap.parse_args(argv)
    started = time.monotonic()
    tickers = args.tickers.split(",") if args.tickers else _tickers_for_run(args.universe)
    frames = {t: _with_context(load_cached(t)) for t in tickers}
    frames = {t: f for t, f in frames.items()
              if f is not None and liquidity_reason(f) is None and not data_quality_issues(f, t)}
    records, meta = collect(frames, _build_asof_map(list(frames), frames, args.universe))
    result = summarise(records)
    result.update(meta=meta, universe_n=len(frames), elapsed_s=round(time.monotonic() - started, 1),
                  reproduction=reproduction_report(result, meta))
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(render_markdown(result), encoding="utf-8")
    print(f"v93_exact={result['reproduction']['v93_exact']} candidates={len(result['candidates'])} -> {args.out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: PASS, 21 passed, 0 failed.

- [ ] **Step 5: Smoke-run on three tickers**

Run: `python scripts/backtest/measure_fib_diagnostic.py --tickers AAPL,MSFT,NVDA --out "$TMPDIR/fib_smoke.json" --md "$TMPDIR/fib_smoke.md"` (use the session scratchpad if `$TMPDIR` is unset)
Expected: 60 flushed progress lines ending `100%`, then `v93_exact=False candidates=... -> ...` (`False` is correct on a 3-ticker subset). Open the `.md` and check that every table renders and `stop mismatches` is `0` for both directions. **A non-zero mismatch count is a bug in `structural_stop`/`apply_cap` vs `_fibonacci_plan`. Fix it before Task F101-4; #1's partition is meaningless until it is 0.**

- [ ] **Step 6: Commit and merge**

```bash
git add scripts/backtest/measure_fib_diagnostic.py tests/scripts/test_measure_fib_diagnostic.py
git commit -m "feat(v101): Fibonacci diagnostic collection passes, v93 reproduction check, report"
```

Merge the branch to `main` per the `worktree-lifecycle` skill (check `git worktree list` and HEAD first; another session may have committed).

---

### Task F101-4: Run the diagnostic on TRAIN and record the result

**Files:**
- Create: `docs/superpowers/results/YYYY-MM-DD-v101-fib-diagnostic.json` (raw, script output)
- Create: `docs/superpowers/results/YYYY-MM-DD-v101-fib-diagnostic-table.md` (script `--md` output)
- Create: `docs/superpowers/results/YYYY-MM-DD-v101-fib-diagnostic.md` (the write-up)

`YYYY-MM-DD` is the run date.

**Interfaces:**
- Consumes: `measure_fib_diagnostic.py` from Task F101-3, merged to `main`.
- Produces: the write-up's `## Verdict` line, which is exactly one of `PROCEED: <direction> <mechanism>[, ...]` or `NO-LIFT`. Task F101-5 branches on it.

- [ ] **Step 1: Load the `backtest-gate` skill.** Confirm TRAIN-only and that this measures no closed row (v93 is only reproduced).

- [ ] **Step 2: Dispatch the run to `backtest-runner`**

Prompt the subagent with:

> Run from the repo root, no `cd`: `python scripts/backtest/measure_fib_diagnostic.py --out docs/superpowers/results/<date>-v101-fib-diagnostic.json --md docs/superpowers/results/<date>-v101-fib-diagnostic-table.md > <scratchpad>/v101_fib_diag.log 2>&1`. Progress lines carry a percent figure; when asked how far along it is, answer from the last line of the log. When it finishes, return only: the final `v93_exact=... candidates=...` line, `elapsed_s`, `universe_n`, and the full contents of the `-table.md` file. Delete the log on success.

- [ ] **Step 3: Check the sanity gates before interpreting anything**
  - `v93_exact` must be `True`. If it is `False`, **stop here**. Run `git log --oneline d78bd3f5..HEAD -- swingbot/core scripts/backtest/run_backtest_range.py` to find what changed the bearish population since v93, record that in the write-up, and do not treat any mechanism figure as evidence until it is explained.
  - `stop mismatches` must be `0` in both directions (see Task F101-3 Step 5).
  - The bullish baseline should sit near the registry row (N 246, WR 35.4%, ExpR +0.232). The universes differ, so report the gap rather than requiring a match.

- [ ] **Step 4: Write `docs/superpowers/results/<date>-v101-fib-diagnostic.md`**

Sections, in order:
1. `**Edge:** expectancy`, window (TRAIN 2020-01-01..2023-12-31), universe N, arithmetic (v2, scale-out, TP2 levels, frictions), and the fixed parameters (`RECLAIM_WINDOW = 5`, `RATIO_LADDER`).
2. `## Sanity gates`: v93 reproduction, stop mismatches, the bullish gap to the registry.
3. `## Results`: paste the `-table.md` content.
4. `## Reading`: one paragraph per mechanism per direction, stating whether the arm moved WR and ExpR relative to its paired base and at what N. For #1, the headline is capped vs structural WR at the cap rate. Per-horizon rows are description only: state that they are not candidates.
5. `## Verdict`: `PROCEED: ...` listing each candidate cell (direction, mechanism, N, WR, ExpR), or `NO-LIFT`. A cell counts only if it is pooled per direction with WR ≥ 50 and N ≥ 30. For #2/#4, which are measured under the simple simulator, add one sentence saying the v2 figure is not yet known and Part 2's Stage 0 measures it.

- [ ] **Step 5: Commit on `main`**

Invoke the `pooled-numbers` skill before writing any figure into the commit message.

```bash
git add docs/superpowers/results/*-v101-fib-diagnostic*
git commit -m "docs(v101): Phase A Fibonacci diagnostic on TRAIN -- <PROCEED ...|NO-LIFT>"
```

---

# Phase B entry — branch on the verdict

### Task F101-5: Write Part 2 (PROCEED) or close out (NO-LIFT)

**Files (PROCEED):**
- Create: `docs/superpowers/results/YYYY-MM-DD-v101-fib-preregistration.md`
- Create: `docs/superpowers/plans/2026-09-24-v101-fib-rescue-long-short_2-mechanism.md`
- Modify: this file (add a `## Parts` table under Global Constraints naming `_2-mechanism`)

**Files (NO-LIFT):**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table: one row)
- Move: this plan → `docs/superpowers/plans/no-lift/`, the spec → `docs/superpowers/specs/no-lift/` (per `document-lifecycle.md`; `git mv`)
- Modify: the spec's `**Status:**` line (add one under the headers: `Closed no-lift <date>. Phase A found no pooled per-direction cell with WR >= 50 and N >= 30; VALIDATION not spent.`)

**Interfaces:**
- Consumes: Task F101-4's `## Verdict` line and results JSON.
- Produces (PROCEED): a committed pre-registration, and a Part 2 plan whose tasks carry full code for the chosen mechanism.

- [ ] **Step 1 (both paths): Re-read the verdict and load `backtest-gate`.**

- [ ] **Step 2 (PROCEED): Write the pre-registration.** It must fix, before any Stage 0 run:
  - **exactly one** mechanism. If both directions produced candidates, the mechanism must be the same for both, or the second direction waits for its own pre-registration. Name the Phase A figure that justifies it.
  - the flag name (`FIB_STRUCTURAL_STOP_ONLY`, `FIB_DEEPER_RATIO_STOP` or `FIB_RECLAIM_ENTRY`), default `False`;
  - its parameter grid and plateau neighbours. #1 has no parameter (single arm). #2 grids the ladder step `{1, 2}`. #4 grids `RECLAIM_WINDOW ∈ {3, 5, 8}`, with the neighbours being the adjacent grid points;
  - the directions entering the funnel, and one verdict per direction under the spec's success bar;
  - the tooling: `measure_strategy_arm.py --component-json '{"<FLAG>": true}'` feeding `validate_component.py --stage mde|walkforward|validation`. **Run `git log --oneline -5 -- scripts/backtest/measure_arms.py` first.** If v100 has merged, use `measure_arms.py` with its stamp instead.

  Commit it on `main` **before** writing Part 2: `docs(v101): pre-register Fibonacci <mechanism> (<directions>)`.

- [ ] **Step 3 (PROCEED): Write Part 2 with `superpowers:writing-plans`** (on Opus; see memory `plan-writing-on-opus`). Its tasks, each with full code:
  1. The flag in `swingbot/config.py` and its effect in `_fibonacci_plan` (`swingbot/core/planning/builders.py`) for #1/#2, or in `fibonacci_entries` (`swingbot/core/market/entry_filters.py`) for #4. TDD, both directions, flag-off bit-identical test. For a bearish direction the flag needs a way through the mask, so plan how the funnel measures bearish arms: under `gate_override`, the way `measure_bearish_arms.py` does.
  2. Stage 0 MDE → Stage 1 plateau → Stage 2 walk-forward, each dispatched to `backtest-runner`, with results docs. A Stage 0–2 failure closes v101 no-lift (same close-out as Step 4).
  3. Stage 3 VALIDATION: one shot per direction, results doc.
  4. For passing directions only: flip the flag on; rewrite `STRATEGY_GATES["Fibonacci"]` and its comment with current figures (cite v93 if bearish stays gated); re-emit registry rows with `run_backtest_range.py --emit-registry` (extend the registry key to carry direction first if both directions pass); a backtest/live parity test for bullish and bearish; the `backtest-methodology.md` closed-row entry.
  5. Final verification: the full suite, once, then close-out with the `VERSION.json` `bot minor` bump and `version_history.json` regeneration (memory `version-bump-needs-regeneration`).

  Then update this file's `## Parts` table and commit both docs on `main`.

- [ ] **Step 4 (NO-LIFT): Close out.** Add the methodology row: `| Fibonacci rescue v2: structural-stop / deeper-ratio stop / reclaim entry (v101) | **TRAIN diagnostic only, no VALIDATION spent.** <one line per mechanism per direction with N / WR / ExpR>. v93 bearish reproduced exactly. Reopening Fibonacci needs a mechanism outside #1–#4. | results/<date>-v101-fib-diagnostic.md |`. `git mv` the spec and this plan into their `no-lift/` folders and set the spec's Status line. Commit: `docs(v101): close Fibonacci rescue no-lift after Phase A`.

---

### Task F101-6: Full-suite verification (NO-LIFT path only)

On the PROCEED path, skip this task. Part 2 owns the plan's single full-suite run as its final task.

- [ ] **Step 1:** Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full`.
- [ ] **Step 2:** Require `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).
- [ ] **Step 3:** No version bump: this part changed no bot behaviour (`Bump: none`).
