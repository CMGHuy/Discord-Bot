# Multi-Timeframe Trend Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor

**Goal:** Stop alerting swing setups that fight the next horizon up, by adding
an adjacent-horizon hard gate and a 6m macro-anchor confidence penalty.

**Architecture:** A new `mtf.py` module computes each horizon's own trend from
its `HORIZONS` EMA pair. The adjacent check becomes a pre-scenario gate in the
scan loop; the macro check becomes a factor in v32's registry. **Four** existing
trend signals are reconciled down first.

**Tech Stack:** Python 3.11+, pandas, pytest. No new dependencies.

## Global Constraints

- **No new market data.** All 10 horizons' EMAs are computed per scan already.
- **Ships default-OFF** behind `MTF_ADJACENT_GATE`; flips ON only on VALIDATION.
- **Alert-volume loss ≤ ~30%**, measured **per horizon**, not just aggregate.
- **`9m` has no horizon above it** and `6m`–`9m` have no macro anchor. Both are
  logged as *exemptions*, never as passes.
- **The macro anchor is a constant**, not a config field, until measurement says
  otherwise.
- **DEPENDS ON v32.** The macro penalty is a factor in v32's `FACTORS` registry.

## v32 landed, but not as this plan assumed -- read before starting Task 5

`docs/superpowers/plans/implemented/2026-08-16-v32-unified-confidence-score.md`
merged to `main` on 2026-08-17. The registry (`FactorResult`/`FactorContext`/
`FACTORS`/`run_factors`, `_resolve_confluence`, `level_for_score`) is real,
live code -- Task 5 below can still register a factor into it. But
**`UNIFIED_CONFIDENCE` stays default-off**: v32's TRAIN measurement found no
factor with real, positively-signed win-rate lift (14 of 15 measured
factors were Wilson-overlapping, 1 was real but wrong-signed), so v32's own
`FACTORS` list ships with only one inert, never-firing factor
(`factor_gap`), and its one-shot VALIDATION run then FAILed (a small
win-rate regression vs. the legacy scorer). There is no "point budget v32
establishes" to draw from -- the merged score's quality-points pool is
empty, and it is not live in production regardless. Full result:
`docs/superpowers/plans/implemented/v32-train-preregistration.md`.

This does not block Task 5 mechanically (the registry still accepts a new
factor), but it changes what registering into it accomplishes: a factor
added to `FACTORS` only affects scoring when `UNIFIED_CONFIDENCE` is on,
which it is not, and won't be without a future spec re-measuring the whole
merged set (this plan's macro-anchor factor included) against real TRAIN
evidence. Task 5's "provisional until v33 Task 7" framing and the PASS
criterion at the bottom of this plan ("win rate improves vs. v32
baseline") should be re-read with this in mind before executing -- not
rewritten here, since that is this plan's own scope to work out, not v32's
closing task's.

## The four overlapping trend signals

This plan's spec named three. Reading config for v32's plan found a fourth.

| Signal | Where | What it reads |
|---|---|---|
| `factors.mtf_alignment(df, direction) -> int` | *retired by Task 6* | **Weekly** resample: EMA10 slope+position, swing-low/high sequence, prior-week pivot. Scored 0–3. Task 1 measured a real, wrong-signed −8.0pp lift (Wilson non-overlapping); Task 6 deleted it as a scored input everywhere. |
| `get_htf_bias(df, horizon_key) -> dict\|None` | `scanning/regime.py:46` | Daily 50 EMA (`2w`/`4w`/`2m`) or 200 EMA (`3m`–`9m`, all seven of the remaining horizons). |
| `HTF_COUNTER_TREND_PENALTY` | *retired by Task 6* | Used to subtract 15 raw score points when `get_htf_bias` opposed direction. Task 1 found it an exact duplicate (Cramér's V = 1.0) of the `htf` label's agreement boolean; Task 6 removed the penalty and its config field, keeping only the informational label/embed warning. |
| **NEW: adjacent-horizon check** | this plan | Next horizon's own `ema_fast`/`ema_slow` from `HORIZONS`. |

Two were the *same signal counted twice*: `get_htf_bias` fed both the `htf`
quality component and `HTF_COUNTER_TREND_PENALTY` — Task 1/6 resolved this
by keeping only the former (see the table above and
`docs/superpowers/plans/v33-trend-signal-reconciliation.md`).

**This table describes the pre-Task-1 state.** The claim that used to sit
here — "`get_htf_bias` only maps `2w`,`4w`,`2m`,`3m`,`6m`; the horizons `4m`,
`5m`, `7m`, `8m`, `9m` return `None`; half the horizons have no
higher-timeframe signal at all today" — was **false even when this plan was
written**: Task 1 measured `get_htf_bias` returning `None` zero times across
4337 TRAIN scenarios, because `_HTF_EMA_PERIOD` has mapped all ten `HORIZONS`
keys to an EMA period since commit `512200e` (2026-07-07), predating this
plan. There was nothing for Task 1 to resolve here and no `_HTF_EMA_PERIOD`
change was made. See the reconciliation doc's Decision 4 for the full
measurement. Do not carry the "half the horizons have no signal" claim into
Tasks 7–8.

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/market/mtf.py` | **NEW.** `horizon_trend()`, `adjacent_horizon()`, `adjacent_aligned()`, `macro_aligned()`. Pure, no config reads. |
| `swingbot/core/scanning/engine.py` | Applies the adjacent gate; funnel counter. |
| `swingbot/core/scanning/factors.py` | `factor_macro_alignment` registered into v32's `FACTORS`. |
| `swingbot/config.py` | `MTF_ADJACENT_GATE`. |
| `tests/market/test_mtf.py` | **NEW.** |

---

# Phase 1 — Reconcile four signals into two

### Task 1: Measure the four trend signals' mutual correlation and decide

**Files:**
- Create: `docs/superpowers/plans/v33-trend-signal-reconciliation.md`

**Interfaces:**
- Produces: the decision on which signals survive. No code.

- [ ] **Step 1: Instrument all four signals over TRAIN**

For ≥500 TRAIN scenarios record: `mtf_alignment` (0–3), `get_htf_bias` agreement
(bool/None), whether `HTF_COUNTER_TREND_PENALTY` fired, and the proposed
adjacent-horizon agreement (bool/None). Dispatch via `backtest-runner`.

- [ ] **Step 2: Compute pairwise agreement and per-signal win-rate lift**

For each pair, Cramér's V (all are categorical). For each signal, win rate when
it agrees vs. opposes, with Wilson intervals (reuse
`scripts/backtest/measure_factor_lift.py::wilson_interval` from v32 Task 8).

- [ ] **Step 3: Make these four decisions explicitly**

1. **Does `get_htf_bias` survive at all**, given the adjacent check covers the
   same idea with per-horizon EMAs and no unmapped-horizon hole?
2. **If it survives, is `HTF_COUNTER_TREND_PENALTY` double-counting it?** It and
   the `htf` quality component read the identical boolean. Keeping both means
   one signal is worth 15 raw points *plus* a factor score.
3. **Does `mtf_alignment` (weekly) add anything** over the adjacent check
   (per-horizon daily)? If Cramér's V > 0.7, keep one.
4. **How do `4m`,`5m`,`7m`,`8m`,`9m` get higher-timeframe coverage?** Either
   extend `_HTF_EMA_PERIOD` to all ten horizons or let the adjacent check
   replace `get_htf_bias` entirely (it works for all ten by construction).

Rule: any pair with Cramér's V > 0.7 collapses to one, unless written
justification says otherwise.

- [ ] **Step 4: Write the reconciliation document and commit**

```bash
git add docs/superpowers/plans/v33-trend-signal-reconciliation.md
git commit -m "docs(v33): reconcile four overlapping trend signals on TRAIN evidence"
```

---

# Phase 2 — The mtf module

### Task 2: `horizon_trend()` and `adjacent_horizon()`

**Files:**
- Create: `swingbot/core/market/mtf.py`
- Test: `tests/market/test_mtf.py`

**Interfaces:**
- Produces: `horizon_trend(df, horizon_key) -> str | None`,
  `adjacent_horizon(horizon_key) -> str | None`,
  `MACRO_ANCHOR_HORIZON = "6m"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_mtf.py
import pandas as pd
import pytest

from swingbot.core.market.mtf import (
    horizon_trend, adjacent_horizon, MACRO_ANCHOR_HORIZON,
)


def _frame(closes):
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    })


def test_rising_series_is_bullish():
    """ema_fast above ema_slow = bullish, using the horizon's own pair."""
    assert horizon_trend(_frame([100 + i for i in range(120)]), "4w") == "bullish"


def test_falling_series_is_bearish():
    assert horizon_trend(_frame([300 - i for i in range(120)]), "4w") == "bearish"


def test_insufficient_history_returns_none():
    """None means 'unknown', which callers must treat as an exemption --
    never as agreement."""
    assert horizon_trend(_frame([100, 101, 102]), "6m") is None


@pytest.mark.parametrize("horizon,expected", [
    ("2w", "4w"), ("4w", "2m"), ("2m", "3m"), ("3m", "4m"),
    ("4m", "5m"), ("5m", "6m"), ("6m", "7m"), ("7m", "8m"), ("8m", "9m"),
])
def test_adjacent_horizon_chains_upward(horizon, expected):
    assert adjacent_horizon(horizon) == expected


def test_longest_horizon_has_no_adjacent():
    """9m is the top of the ladder: exempt, not failed."""
    assert adjacent_horizon("9m") is None


def test_macro_anchor_is_six_months():
    assert MACRO_ANCHOR_HORIZON == "6m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_mtf.py`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.market.mtf`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/market/mtf.py
"""Horizon-to-horizon trend agreement (v33).

Every check here compares THIS bot's own horizons against each other, using
each horizon's own ema_fast/ema_slow from HORIZONS. That is the difference
from regime.get_htf_bias (a fixed 50/200 EMA proxy that only covers 5 of the
10 horizons) and from factors.mtf_alignment (a weekly resample).

Pure functions: no config reads, no I/O, so the gate that consumes them stays
testable and the backtest can call them directly.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS

MACRO_ANCHOR_HORIZON = "6m"

_LADDER = list(HORIZONS.keys())


def adjacent_horizon(horizon_key: str) -> str | None:
    """The next horizon up, or None for the longest one (an exemption)."""
    try:
        idx = _LADDER.index(horizon_key)
    except ValueError:
        return None
    return _LADDER[idx + 1] if idx + 1 < len(_LADDER) else None


def horizon_trend(df: pd.DataFrame, horizon_key: str) -> str | None:
    """"bullish" when this horizon's ema_fast is above its ema_slow, else
    "bearish". None when the horizon is unknown or history is too short --
    callers must treat None as unknown, never as agreement."""
    settings = HORIZONS.get(horizon_key)
    if settings is None or df is None:
        return None
    slow = settings["ema_slow"]
    if len(df) < slow + 1:
        return None
    fast_series = ema(df["Close"], settings["ema_fast"])
    slow_series = ema(df["Close"], slow)
    if fast_series.empty or slow_series.empty:
        return None
    return "bullish" if fast_series.iloc[-1] > slow_series.iloc[-1] else "bearish"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_mtf.py`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/mtf.py tests/market/test_mtf.py
git commit -m "feat(v33): per-horizon trend and the adjacent-horizon ladder"
```

---

### Task 3: `adjacent_aligned()` and `macro_aligned()` with explicit exemptions

**Files:**
- Modify: `swingbot/core/market/mtf.py`
- Test: `tests/market/test_mtf.py`

**Interfaces:**
- Produces: `adjacent_aligned(df, horizon_key, direction) -> dict`,
  `macro_aligned(df, horizon_key, direction) -> dict`, both returning
  `{"status": "aligned"|"opposed"|"exempt", "reason": str, "trend": str|None}`.

A tri-state, not a bool. The spec requires an exemption to be distinguishable
from agreement in logs and scoring, and a bool cannot express that.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/market/test_mtf.py
from swingbot.core.market.mtf import adjacent_aligned, macro_aligned

_RISING = None  # set in the fixture below


def test_adjacent_aligned_when_next_horizon_agrees():
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "2w", "bullish")
    assert r["status"] == "aligned"
    assert r["trend"] == "bullish"


def test_adjacent_opposed_when_next_horizon_disagrees():
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "2w", "bearish")
    assert r["status"] == "opposed"


def test_longest_horizon_is_exempt_not_aligned():
    """The distinction that matters: 9m has nothing above it. If this returned
    'aligned' the gate would silently pass every 9m scenario as confirmed."""
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "9m", "bullish")
    assert r["status"] == "exempt"
    assert "no higher horizon" in r["reason"]


def test_short_history_is_exempt_not_opposed():
    r = adjacent_aligned(_frame([100, 101, 102]), "2w", "bullish")
    assert r["status"] == "exempt"


def test_macro_exempt_at_and_above_the_anchor():
    """6m..9m cannot anchor to 6m -- a horizon cannot check itself."""
    df = _frame([100 + i for i in range(300)])
    for horizon in ("6m", "7m", "8m", "9m"):
        assert macro_aligned(df, horizon, "bullish")["status"] == "exempt"


def test_macro_evaluates_below_the_anchor():
    df = _frame([100 + i for i in range(300)])
    assert macro_aligned(df, "2w", "bullish")["status"] == "aligned"
    assert macro_aligned(df, "2w", "bearish")["status"] == "opposed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_mtf.py`
Expected: FAIL — `ImportError: cannot import name 'adjacent_aligned'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to swingbot/core/market/mtf.py
def _verdict(trend: str | None, direction: str, reason_if_unknown: str) -> dict:
    if trend is None:
        return {"status": "exempt", "reason": reason_if_unknown, "trend": None}
    if trend == direction:
        return {"status": "aligned", "reason": f"{trend} trend agrees", "trend": trend}
    return {"status": "opposed", "reason": f"{trend} trend opposes", "trend": trend}


def adjacent_aligned(df: pd.DataFrame, horizon_key: str, direction: str) -> dict:
    """Does the next horizon up agree? 'exempt' when there is no higher
    horizon or its trend is unknowable -- never conflated with 'aligned'."""
    nxt = adjacent_horizon(horizon_key)
    if nxt is None:
        return {"status": "exempt", "reason": "no higher horizon above "
                f"{horizon_key}", "trend": None}
    return _verdict(horizon_trend(df, nxt), direction,
                    f"insufficient history for {nxt}")


def macro_aligned(df: pd.DataFrame, horizon_key: str, direction: str) -> dict:
    """Agreement with the fixed 6m macro anchor. Horizons at or beyond the
    anchor are exempt: a horizon cannot anchor to itself or to something
    shorter than itself."""
    if horizon_key not in _LADDER:
        return {"status": "exempt", "reason": "unknown horizon", "trend": None}
    if _LADDER.index(horizon_key) >= _LADDER.index(MACRO_ANCHOR_HORIZON):
        return {"status": "exempt",
                "reason": f"{horizon_key} is at or beyond the "
                          f"{MACRO_ANCHOR_HORIZON} anchor", "trend": None}
    return _verdict(horizon_trend(df, MACRO_ANCHOR_HORIZON), direction,
                    f"insufficient history for {MACRO_ANCHOR_HORIZON}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_mtf.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/mtf.py tests/market/test_mtf.py
git commit -m "feat(v33): tri-state adjacent and macro alignment verdicts"
```

---

# Phase 3 — Wire the gate and the penalty

### Task 4: The adjacent-horizon hard gate

**Files:**
- Modify: `swingbot/core/scanning/engine.py` (scenario loop, near `:917`)
- Modify: `swingbot/config.py`
- Test: `tests/scanning/test_mtf_gate.py`

**Interfaces:**
- Consumes: `adjacent_aligned` (Task 3).
- Produces: a `mtf_misaligned` funnel counter.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_mtf_gate.py
from swingbot import config


def test_gate_off_by_default_lets_counter_trend_through(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", False)
    items = _scan_with(direction="bullish", next_horizon_trend="bearish")
    assert len(items) == 1


def test_gate_on_drops_a_counter_trend_scenario(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", next_horizon_trend="bearish")
    assert items == []


def test_gate_on_keeps_an_aligned_scenario(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", next_horizon_trend="bullish")
    assert len(items) == 1


def test_exempt_horizon_is_never_dropped(monkeypatch):
    """9m has no higher horizon. It must pass the gate, not fail it."""
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    items = _scan_with(direction="bullish", horizon="9m")
    assert len(items) == 1


def test_dropped_scenarios_increment_the_funnel_counter(monkeypatch):
    monkeypatch.setattr(config, "MTF_ADJACENT_GATE", True)
    _items, funnel = _scan_with_funnel(direction="bullish",
                                       next_horizon_trend="bearish")
    assert funnel["mtf_misaligned"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py`
Expected: FAIL — `AttributeError: config has no attribute 'MTF_ADJACENT_GATE'`

- [ ] **Step 3: Add the config field**

```python
# swingbot/config.py, in the "Multi-Timeframe Confluence" section beside
# HTF_COUNTER_TREND_PENALTY at :401
    Field("MTF_ADJACENT_GATE", "MTF_ADJACENT_GATE", "Multi-Timeframe Confluence",
          "Adjacent-horizon hard gate",
          type="checkbox", default="false",
          help="Drop a scenario when the next horizon up trends against it "
               "(e.g. a 2w bullish setup while the 4w trend is bearish). "
               "The longest horizon is exempt. Enable only after VALIDATION."),
```

- [ ] **Step 4: Apply the gate as a pre-scenario check**

Place it with the other pre-scenario gates, **before** confidence scoring —
a dropped scenario should cost no scoring work:

```python
# swingbot/core/scanning/engine.py, in the per-scenario loop
if config.MTF_ADJACENT_GATE:
    mtf_verdict = adjacent_aligned(df, horizon_key, scenario.direction)
    if mtf_verdict["status"] == "opposed":
        log.debug("%s/%s %s dropped: %s", ticker, horizon_key,
                  scenario.direction, mtf_verdict["reason"])
        mtf_misaligned += 1
        continue
```

Add `mtf_misaligned` to the funnel dict beside `filtered_by_confirmation`
(`engine.py:1151`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py swingbot/config.py tests/scanning/test_mtf_gate.py
git commit -m "feat(v33): adjacent-horizon hard gate behind MTF_ADJACENT_GATE"
```

---

### Task 5: The macro-anchor penalty as a v32 factor

**Files:**
- Modify: `swingbot/core/scanning/factors.py`
- Test: `tests/scanning/test_factors.py`

**Interfaces:**
- Consumes: v32's `FactorResult`/`FactorContext`; `macro_aligned` (Task 3).
- Produces: `factor_macro_alignment`, registered in `FACTORS`.

**Blocked on v32 Task 4.** Point value is provisional until v33 Task 7
re-derives it from TRAIN.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_factors.py
from swingbot.core.scanning.factors import factor_macro_alignment


def test_macro_alignment_scores_full_when_aligned():
    ctx = _ctx(macro_verdict={"status": "aligned", "reason": "bullish trend agrees",
                              "trend": "bullish"})
    assert factor_macro_alignment(ctx).points == 10


def test_macro_alignment_scores_zero_when_opposed():
    ctx = _ctx(macro_verdict={"status": "opposed", "reason": "bearish trend opposes",
                              "trend": "bearish"})
    r = factor_macro_alignment(ctx)
    assert r.points == 0
    assert "⚠️" in r.line


def test_macro_alignment_exempt_returns_none_not_zero():
    """An exempt horizon has no macro reading. Scoring it 0 would penalise
    every 6m-9m scenario for a check that cannot apply to it."""
    ctx = _ctx(macro_verdict={"status": "exempt", "reason": "6m is at the anchor",
                              "trend": None})
    assert factor_macro_alignment(ctx) is None


def test_macro_alignment_absent_returns_none():
    assert factor_macro_alignment(_ctx()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: FAIL — `ImportError: cannot import name 'factor_macro_alignment'`

- [ ] **Step 3: Write minimal implementation**

Add `macro_verdict: dict | None = None` to `FactorContext`, then:

```python
# append to swingbot/core/scanning/factors.py
_MACRO_ALIGNMENT_POINTS = 10   # provisional; re-derived in v33 Task 7


def factor_macro_alignment(ctx: FactorContext) -> FactorResult | None:
    """Agreement with the 6m macro anchor. Never blocks -- only the adjacent
    check gates. Exempt horizons return None so they are omitted from the
    breakdown rather than scored zero."""
    verdict = ctx.macro_verdict
    if not verdict or verdict["status"] == "exempt":
        return None
    if verdict["status"] == "aligned":
        return FactorResult(
            "Macro trend (6m)", _MACRO_ALIGNMENT_POINTS,
            f"agrees with the 6m {verdict['trend']} trend "
            f"(+{_MACRO_ALIGNMENT_POINTS})")
    return FactorResult(
        "Macro trend (6m)", 0,
        f"⚠️ counter to the 6m {verdict['trend']} trend (+0)")
```

Register it in `FACTORS` and populate `macro_verdict` where `engine.py` builds
the `FactorContext` (v32 Task 6).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/factors.py swingbot/core/scanning/engine.py tests/scanning/test_factors.py
git commit -m "feat(v33): 6m macro-anchor alignment factor"
```

---

### Task 6: Remove whichever signals Task 1 retired

**Files:**
- Modify: per Task 1's document — some of `edge/factors.py:88`,
  `scanning/regime.py:46`, `config.py:401`, `scanning/engine.py:932-945`
- Test: existing tests for the removed signals

- [ ] **Step 1: Re-read Task 1's reconciliation document**

Implement exactly its decisions. If it kept all four, this task is a no-op —
record that and move on.

- [ ] **Step 2: If `HTF_COUNTER_TREND_PENALTY` was retired**

Remove the block at `engine.py:932-945` and the `Field` at `config.py:401`.
Also remove the explanatory sentence at `embeds.py:622`.

Note v32 Task 6 Step 6 already replaced this block's hardcoded band arithmetic;
if the whole block goes, that fix goes with it.

- [ ] **Step 3: If `get_htf_bias` was retired**

Remove it from `regime.py`, its `htf` factor from `factors.py`, and
`HTF_CONFLUENCE_ENABLED` from config. If it was **kept**, extend
`_HTF_EMA_PERIOD` to cover all ten horizons — five returning `None` is a hole,
not a design.

- [ ] **Step 4: If `mtf_alignment` was retired**

Remove it from `edge/factors.py` and its `factor_mtf` from the registry. Check
`tracking/retrospective.py` for references first.

- [ ] **Step 5: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(v33): retire the trend signals Task 1's measurement subsumed"
```

---

# Phase 4 — Measure and ship

### Task 7: TRAIN sweep with per-horizon volume reporting

**Files:**
- Create: `docs/superpowers/plans/v33-train-preregistration.md`
- Modify: `swingbot/core/scanning/factors.py` (macro points only)

- [ ] **Step 1: Run the TRAIN sweep**

Dispatch via `backtest-runner`. It must report, **per horizon**: alerts before,
alerts after, win rate before, win rate after, with Wilson intervals.

Run: `python scripts/backtest/run_backtest_range.py --train --json data/v33_train.json`

- [ ] **Step 2: Check the per-horizon volume loss**

The spec's ~30% ceiling is an aggregate. If a single horizon (most likely `2w`,
whose EMA8/13 pair flips most) loses far more, the honest fix is a
**horizon-scoped gate** — enable the adjacent check only for horizons where it
earns its keep. Record which horizons qualify.

- [ ] **Step 3: Test whether a neutral band is needed**

A horizon whose EMAs are nearly equal flips on noise. Measure win rate for
scenarios where `|ema_fast - ema_slow| / close < 0.5%`. If those are
indistinguishable from coin flips, add a neutral band that returns `exempt`.
Only add it if the data asks.

- [ ] **Step 4: Re-derive the macro-alignment points**

Replace `_MACRO_ALIGNMENT_POINTS = 10` with the value TRAIN supports, on the
same normalized scale v32 Task 9 established.

- [ ] **Step 5: Write the pre-registration**

```markdown
## v33 VALIDATION pre-registration
- Primary: win rate at MIN_ALERT_CONFIDENCE_LEVEL=4 with MTF_ADJACENT_GATE=on.
- PASS: win rate improves vs. v32 baseline AND aggregate alert volume falls
  by no more than 30% AND no single horizon loses more than 50%.
- Gate scope: <horizons Step 2 qualified>.
- Neutral band: <included/excluded, per Step 3>.
- One shot. FAIL means MTF_ADJACENT_GATE stays default-off.
```

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/v33-train-preregistration.md swingbot/core/scanning/factors.py data/v33_train.json
git commit -m "feat(v33): TRAIN sweep, per-horizon volume, macro weight derived"
```

---

### Task 8: VALIDATION, docs, version bump

**Files:**
- Modify: `swingbot/config.py`, `docs/strategy.md`, `VERSION.json`
- Modify: `docs/superpowers/plans/v33-train-preregistration.md`

- [ ] **Step 1: Confirm the pre-registration is committed and unedited**

Run: `git log --oneline -- docs/superpowers/plans/v33-train-preregistration.md`

- [ ] **Step 2: Run VALIDATION once**

Run: `python scripts/backtest/run_backtest_range.py --validation --json data/v33_validation.json`

- [ ] **Step 3: Record the result verbatim. Do not re-run on FAIL.**

- [ ] **Step 4: On PASS, flip `MTF_ADJACENT_GATE` to `default="true"`**

- [ ] **Step 5: Document the behavior in `docs/strategy.md`**

A new section covering both checks, the exemptions, and — explicitly — that
`9m` and `6m`–`9m` exemptions are not passes.

- [ ] **Step 6: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 7: Bump `VERSION.json` and close the spec**

`bot` minor on PASS; no bump on FAIL. Then:

```bash
git mv docs/superpowers/specs/2026-08-16-v33-mtf-trend-alignment-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-16-v33-mtf-trend-alignment.md docs/superpowers/plans/implemented/
git add -A
git commit -m "feat(v33): VALIDATION result, docs, version bump"
```

---

## Parallelisation

- **Sequential: Task 1 before everything.** It decides which signals survive;
  Task 6 implements its verdict and Tasks 4–5 assume it.
- **Group A (parallel, after Task 1):** Task 2 and Task 4's config field —
  disjoint files (`mtf.py` vs `config.py`).
- **Sequential: Task 2 → Task 3.** Task 3 consumes `horizon_trend`/`adjacent_horizon`.
- **Group B (parallel, after Task 3):** Task 4 (`engine.py`) and Task 5
  (`factors.py`) — disjoint files, both consume Task 3's verdict dicts.
- **Sequential: Task 6 after Tasks 4–5** (removing a signal while wiring its
  replacement in another file races).
- **Sequential: Task 7 → Task 8.**

## Progress

- [x] Task 1 — Reconcile four trend signals
- [x] Task 2 — `horizon_trend` / `adjacent_horizon`
- [x] Task 3 — Tri-state alignment verdicts
- [x] Task 4 — Adjacent-horizon hard gate
- [x] Task 5 — Macro-anchor factor
- [x] Task 6 — Retire subsumed signals
- [x] Task 7 — TRAIN sweep, per-horizon volume
- [x] Task 8 — VALIDATION, docs, bump

## Close-out — all 8 tasks executed; the gate FAILed VALIDATION and is OFF

Every task ran and is committed; that is what the boxes above record. **What
they do not record — and what a reader must not infer from them — is that the
feature shipped as behaviour. It did not.**

Task 8's one-shot VALIDATION run (2804 scenarios, 2024-01-01..2025-12-31)
returned **FAIL** on the first of the three pre-registered conditions: the
gate *lowered* aggregate win rate, 47.98% vs. 48.50% ungated (−0.51pp), with
overlapping Wilson intervals. The other two conditions passed (aggregate
volume cut 6.63% ≤ 30%; worst horizon `2w` at 32.06% ≤ 50%), which does not
offset condition 1. Full numbers, the run's exact command, and what a future
spec may legitimately ask:
`docs/superpowers/plans/implemented/v33-train-preregistration.md`.

Consequently, per this plan's own Global Constraints and the pre-registration's
FAIL clause:

- **`MTF_ADJACENT_GATE` stays `default="false"`.** The gate is committed,
  tested and wired into `scanning/engine.py`, but off — an option, not the
  bot's behaviour.
- **No `VERSION.json` bump for the gate itself.** This plan's `Bump: bot
  minor` header was a prediction conditional on a PASS, and `MTF_ADJACENT_GATE`
  staying off earns nothing on its own. Task 6's retirements are a different
  matter: removing `HTF_COUNTER_TREND_PENALTY` and removing `mtf_alignment`
  from `quality.score_plan()` are both default-on behavior changes a running
  container does show — alerts previously suppressed by the penalty now post,
  and every v2 plan's quality score, embed breakdown and `rank.follow_score`
  shifted. That earned a `bot` patch bump, `1.2.1` → `1.2.2`, taken as a
  standalone follow-up commit after this plan's close-out (not folded into
  Task 6 itself, since the close-out here is what surfaced it).
- **`_MACRO_ALIGNMENT_POINTS = 0`** (Task 7, re-derived from TRAIN):
  `factor_macro_alignment` ships registered and informational, contributing
  nothing to the score.

What v33 *did* land and keep: `swingbot/core/market/mtf.py`'s tri-state
horizon-trend verdicts, the retirement of the subsumed weekly-resample
`mtf_alignment` signal (Task 6, measured −8.0pp), and two committed
measurement instruments under `scripts/backtest/`.
