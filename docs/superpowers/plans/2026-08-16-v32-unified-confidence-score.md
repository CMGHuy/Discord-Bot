# Unified Confidence Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor (1.1.4 → 1.2.0) · ui patch

**Goal:** Merge the two parallel scoring systems into one 0–100 score that both
grades and gates alerts, so relative strength, MTF alignment and market breadth
finally influence which alerts fire.

**Architecture:** `score_confidence()` is refactored from a 280-line monolith
into a **factor registry** — a list of small pure functions each returning
`(points, breakdown_line)`. The registry absorbs `quality.score_plan()`'s
components. Weights become data, not literals, so the TRAIN measurement can
re-derive them without touching logic. Level mapping extends to 1–6 with an
explicit method-count cap replacing today's emergent one.

**Tech Stack:** Python 3.11+, pandas/numpy, pytest. No new dependencies.

## Global Constraints

- **No new market data.** Every factor input is already computed during a scan.
- **Ships default-OFF** behind `UNIFIED_CONFIDENCE`; flips ON only on a
  VALIDATION pass.
- **Weights stay legible integers.** The breakdown renders verbatim in embeds;
  no fitted regression coefficients.
- **`MIN_ALERT_CONFIDENCE_LEVEL` keeps its name and default of `4`** (config.py:167 —
  *not* 3, which is what `docs/strategy.md` wrongly says).
- **The honesty property becomes an explicit tested cap**, not an emergent
  effect of `min(5, target_count)` plus two ±1 adjustments.
- **Level 6 is conditional** on: n ≥ 100 TRAIN samples, point-estimate win rate
  ≥ 90%, and Wilson 95% lower bound ≥ 80% *and* above Level 5's point estimate.
- **NO-LOOKAHEAD** (`docs/claude/architecture.md`) applies to every measurement
  script.
- Test with `python scripts/dev/testrun.py file tests/<file>` while iterating;
  `full` only at the pre-commit gate.

## File Structure

| File | Responsibility |
|---|---|
| `swingbot/core/scanning/factors.py` | **NEW.** Factor registry: one pure function per factor, each `(ctx) -> FactorResult`. Weights table. |
| `swingbot/core/scanning/confidence.py` | Orchestration only: build ctx, run registry, apply cap, map to level. Shrinks substantially. |
| `swingbot/core/planning/quality.py` | Components move to `factors.py`; `_tier`/`QualityResult.tier` removed. |
| `swingbot/config.py` | `UNIFIED_CONFIDENCE` flag; `MIN_ALERT_CONFIDENCE_LEVEL` options gain `"6"`. |
| `scripts/backtest/measure_factor_lift.py` | **NEW.** TRAIN per-factor win-rate lift + Wilson intervals. |
| `tests/scanning/test_factors.py` | **NEW.** Per-factor unit tests. |
| `tests/scanning/test_confidence_levels.py` | **NEW.** Level mapping + honesty cap tests. |

---

# Phase 1 — Reconciliation and the registry

### Task 1: Enumerate and reconcile the merged factor set

**Files:**
- Create: `docs/superpowers/plans/v32-factor-reconciliation.md`

**Interfaces:**
- Produces: the authoritative factor list every later task implements. No code.

This is the most important task in the plan. Shipping the union of both scorers
would triple-count trend context (ADX + MACD + regime + HTF + MTF all read
trend) and double-count regime and candlestick, which both scorers compute.

- [ ] **Step 1: Extract both factor sets verbatim**

From `confidence.py:275-436`: distance(0-20), stop confluence(0-15),
regime(0-15), ADX(0-15), MACD(0-15), RSI(0-10), squeeze(0-10),
candlestick(0-10 bonus), tight-stop penalty(0 to -15).

From `quality.py:19-139`: `component_regime`(15/8/0), `component_htf`(15/8/0),
`component_confluence`(0-20), `component_volume`(0-10),
`component_atr_percentile`(0-10), `component_distance`(0-10),
`component_badge`(0/20), `rs_points`(0-10), `mtf_points`(0/3/6/10),
`breadth_points`(0-5), `candle_points`(0-5), `gap_penalty`(0/-10).

- [ ] **Step 2: Write the correlation measurement**

Sample ≥500 TRAIN scenarios, record every factor's raw value, compute a
pairwise Spearman correlation matrix. Dispatch via the `backtest-runner`
subagent so per-scenario output stays out of context.

- [ ] **Step 3: Decide each duplicate/overlap pair**

Record a decision and its evidence for each. Required decisions:

| Pair | Decision to make |
|---|---|
| `confidence.regime` vs `quality.component_regime` | Identical input — keep **one** |
| `confidence.candlestick` vs `quality.candle_points` | Same detector — keep **one** |
| `confidence.distance` vs `quality.component_distance` | Different meanings (target distance vs trigger distance) — keep **both**, rename to disambiguate |
| ADX vs MACD vs RSI | Three momentum reads; if pairwise ρ > 0.7, merge into one composite |
| `quality.component_htf` vs `factors.mtf_alignment` | Both higher-timeframe; keep at most one (v33 revisits) |
| `confidence.stop_confluence` vs `quality.component_confluence` | Stop-side vs target-side — keep **both** |

Rule: any pair with |ρ| > 0.7 collapses to one factor unless a written
justification says why both earn their place.

- [ ] **Step 4: Write the reconciliation document**

Final factor list with name, point range, input source, and for every dropped
factor one line on why. This document is the input to Task 2.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/v32-factor-reconciliation.md
git commit -m "docs(v32): reconcile the merged factor set from measured correlation"
```

---

### Task 2: The `FactorResult` contract and registry skeleton

**Files:**
- Create: `swingbot/core/scanning/factors.py`
- Test: `tests/scanning/test_factors.py`

**Interfaces:**
- Consumes: Task 1's factor list.
- Produces: `FactorResult`, `FactorContext`, `FACTORS`, `run_factors()` —
  every later task registers into `FACTORS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_factors.py
import pytest
from swingbot.core.scanning.factors import (
    FactorResult, FactorContext, run_factors,
)


def _ctx(**kw):
    """Minimal context; every field defaults to None so a factor under test
    only has to supply what it reads."""
    return FactorContext(**kw)


def test_factor_result_carries_points_and_line():
    r = FactorResult(name="demo", points=7, line="demo scored (+7)")
    assert (r.name, r.points, r.line) == ("demo", 7, "demo scored (+7)")


def test_run_factors_sums_points_and_collects_breakdown():
    def f_a(ctx):
        return FactorResult("a", 5, "a (+5)")

    def f_b(ctx):
        return FactorResult("b", 3, "b (+3)")

    total, breakdown = run_factors([f_a, f_b], _ctx())
    assert total == 8
    assert breakdown == {"a": "a (+5)", "b": "b (+3)"}


def test_run_factors_skips_factors_returning_none():
    """A factor whose input is absent returns None and must not appear in the
    breakdown at all -- an absent reading must never render as a real one that
    happened to score zero."""
    def f_present(ctx):
        return FactorResult("present", 4, "present (+4)")

    def f_absent(ctx):
        return None

    total, breakdown = run_factors([f_present, f_absent], _ctx())
    assert total == 4
    assert "absent" not in breakdown


def test_run_factors_propagates_negative_points():
    def f_penalty(ctx):
        return FactorResult("penalty", -10, "penalty (-10)")

    total, _ = run_factors([f_penalty], _ctx())
    assert total == -10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.scanning.factors`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/scanning/factors.py
"""Factor registry for the unified confidence score (v32).

One pure function per factor: (FactorContext) -> FactorResult | None.
Returning None means "this factor had no input to read" and the factor is
omitted from the breakdown entirely -- an absent reading must never render
as a real one that scored zero (the rule quality.py:107-111 already states).

Weights live in the FactorResult each function returns, so re-weighting on
TRAIN evidence never edits control flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class FactorResult:
    name: str
    points: int
    line: str


@dataclass
class FactorContext:
    """Everything any factor may read. All optional: a factor whose inputs
    are missing returns None rather than inventing a neutral value."""
    scenario: object = None
    df: object = None
    regime_trend: str | None = None
    htf_bias: str | None = None
    rs_percentile: float | None = None
    mtf: int | None = None
    breadth: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    trigger_distance_pct: float | None = None
    badge_status: str | None = None
    gap_fragile: bool = False
    target_count: int = 0
    target_families: list = field(default_factory=list)
    stop_count: int = 0
    stop_families: list = field(default_factory=list)


Factor = Callable[[FactorContext], "FactorResult | None"]

FACTORS: list[Factor] = []


def run_factors(factors: list[Factor], ctx: FactorContext) -> tuple[int, dict]:
    """Returns (total_points, {name: line}). Factors returning None are
    omitted from both."""
    total = 0
    breakdown: dict[str, str] = {}
    for fn in factors:
        result = fn(ctx)
        if result is None:
            continue
        total += result.points
        breakdown[result.name] = result.line
    return total, breakdown
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/factors.py tests/scanning/test_factors.py
git commit -m "feat(v32): factor registry contract for the unified score"
```

---

### Task 3: Port the `confidence.py` factors into the registry

**Files:**
- Modify: `swingbot/core/scanning/factors.py`
- Test: `tests/scanning/test_factors.py`

**Interfaces:**
- Consumes: `FactorResult`, `FactorContext` from Task 2.
- Produces: `factor_target_distance`, `factor_stop_confluence`,
  `factor_regime`, `factor_momentum`, `factor_squeeze`, `factor_candlestick`,
  `factor_tight_stop` — names Task 5 imports.

Port only the factors Task 1's document kept. The example below shows two;
implement every kept `confidence.py` factor the same way, preserving its
current point range unless Task 1 changed it.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/scanning/test_factors.py
from types import SimpleNamespace

from swingbot.core.scanning.factors import (
    factor_target_distance, factor_stop_confluence,
)


def test_target_distance_scales_with_multiples_of_minimum():
    """20 pts max, 10 pts per 1x of MIN_REWARD_PCT (default 5%)."""
    ctx = _ctx(scenario=SimpleNamespace(target_distance_pct=10.0))
    r = factor_target_distance(ctx)
    assert r.points == 20
    assert "10.0%" in r.line


def test_target_distance_caps_at_twenty():
    ctx = _ctx(scenario=SimpleNamespace(target_distance_pct=99.0))
    assert factor_target_distance(ctx).points == 20


def test_target_distance_absent_scenario_returns_none():
    assert factor_target_distance(_ctx()) is None


def test_stop_confluence_five_points_per_method_capped_at_fifteen():
    assert factor_stop_confluence(_ctx(stop_count=1)).points == 5
    assert factor_stop_confluence(_ctx(stop_count=3)).points == 15
    assert factor_stop_confluence(_ctx(stop_count=9)).points == 15


def test_stop_confluence_names_the_methods():
    r = factor_stop_confluence(_ctx(stop_count=2, stop_families=["EMA", "VWAP"]))
    assert "EMA, VWAP" in r.line
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: FAIL — `ImportError: cannot import name 'factor_target_distance'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to swingbot/core/scanning/factors.py
from swingbot import config


def factor_target_distance(ctx: FactorContext) -> FactorResult | None:
    if ctx.scenario is None:
        return None
    min_reward = config.MIN_REWARD_PCT if config.MIN_REWARD_PCT > 0 else 5.0
    ratio = ctx.scenario.target_distance_pct / min_reward
    points = min(20, round(10 * ratio))
    return FactorResult(
        "Target distance quality",
        points,
        f"{ctx.scenario.target_distance_pct:.1f}% away "
        f"({ratio:.1f}x the {min_reward:.0f}% minimum) (+{points})",
    )


def factor_stop_confluence(ctx: FactorContext) -> FactorResult | None:
    points = min(15, 5 * ctx.stop_count)
    families = ", ".join(ctx.stop_families) if ctx.stop_families else "none"
    plural = "y" if ctx.stop_count == 1 else "ies"
    return FactorResult(
        "Stop level confluence",
        points,
        f"{ctx.stop_count} strateg{plural} agree: {families} (+{points})",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: PASS

- [ ] **Step 5: Port the remaining kept `confidence.py` factors**

Same pattern for each factor Task 1 kept: `factor_regime` (from
`confidence.py:289-298`), `factor_momentum` (the ADX/MACD/RSI composite or the
separate factors, per Task 1's decision, from lines 300-391), `factor_squeeze`
(393-418), `factor_candlestick` (420-436), `factor_tight_stop` (440-453, the
only negative-points factor). Each gets tests mirroring Step 1: a scoring case,
a boundary case, and an absent-input case returning `None`.

**Preserve the two side effects** at `confidence.py:407` and `:431` — the
squeeze and candlestick factors *append to `scenario.target_sources`*, which
feeds method count. Losing them silently lowers every affected base level. Add
an explicit test that each still appends its source label.

- [ ] **Step 6: Run the full scanning tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/factors.py tests/scanning/test_factors.py
git commit -m "feat(v32): port confidence.py factors into the registry"
```

---

### Task 4: Port the `quality.py` components, including RS/MTF/breadth

**Files:**
- Modify: `swingbot/core/scanning/factors.py`
- Test: `tests/scanning/test_factors.py`

**Interfaces:**
- Produces: `factor_rs`, `factor_mtf`, `factor_breadth`, `factor_htf`,
  `factor_volume`, `factor_atr_percentile`, `factor_trigger_distance`,
  `factor_badge`, `factor_gap` — whichever Task 1 kept.

These three are the point of the whole spec: RS, MTF and breadth become able to
change an alert's fate for the first time.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/scanning/test_factors.py
from swingbot.core.scanning.factors import factor_rs, factor_mtf, factor_breadth


def test_rs_scores_zero_at_or_below_median():
    assert factor_rs(_ctx(rs_percentile=50.0)).points == 0
    assert factor_rs(_ctx(rs_percentile=10.0)).points == 0


def test_rs_scales_above_median_and_caps():
    assert factor_rs(_ctx(rs_percentile=75.0)).points == 5
    assert factor_rs(_ctx(rs_percentile=100.0)).points == 10


def test_rs_absent_returns_none_not_zero():
    """None means the RS benchmark fetch failed. It must be omitted from the
    breakdown, not rendered as a real reading of zero."""
    assert factor_rs(_ctx()) is None


def test_mtf_uses_the_discrete_alignment_ladder():
    assert factor_mtf(_ctx(mtf=0)).points == 0
    assert factor_mtf(_ctx(mtf=1)).points == 3
    assert factor_mtf(_ctx(mtf=2)).points == 6
    assert factor_mtf(_ctx(mtf=3)).points == 10


def test_mtf_absent_returns_none():
    assert factor_mtf(_ctx()) is None


def test_breadth_scores_above_forty_percent_and_caps_at_sixty():
    assert factor_breadth(_ctx(breadth=40.0)).points == 0
    assert factor_breadth(_ctx(breadth=60.0)).points == 5
    assert factor_breadth(_ctx(breadth=95.0)).points == 5


def test_breadth_absent_returns_none():
    assert factor_breadth(_ctx()) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: FAIL — `ImportError: cannot import name 'factor_rs'`

- [ ] **Step 3: Write minimal implementation**

Point ranges are carried over verbatim from `quality.py:114-129` so this task
introduces no weight change; re-weighting happens in Task 8 on TRAIN evidence.

```python
# append to swingbot/core/scanning/factors.py
def factor_rs(ctx: FactorContext) -> FactorResult | None:
    if ctx.rs_percentile is None:
        return None
    points = int(round(max(0.0, min(ctx.rs_percentile - 50.0, 50.0)) / 5.0))
    return FactorResult(
        "Relative strength",
        points,
        f"RS percentile {ctx.rs_percentile:.0f} vs the scanned universe (+{points})",
    )


def factor_mtf(ctx: FactorContext) -> FactorResult | None:
    if ctx.mtf is None:
        return None
    points = {0: 0, 1: 3, 2: 6, 3: 10}.get(int(ctx.mtf), 0)
    return FactorResult(
        "Multi-timeframe alignment",
        points,
        f"{int(ctx.mtf)}/3 higher timeframes agree (+{points})",
    )


def factor_breadth(ctx: FactorContext) -> FactorResult | None:
    if ctx.breadth is None:
        return None
    points = int(round(max(0.0, min(ctx.breadth - 40.0, 20.0)) / 4.0))
    return FactorResult(
        "Market breadth",
        points,
        f"{ctx.breadth:.0f}% of the universe above its 50 EMA (+{points})",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: PASS

- [ ] **Step 5: Port the remaining kept `quality.py` components**

Same pattern for `factor_htf` (`quality.py:25-28`), `factor_volume` (37-46),
`factor_atr_percentile` (65-72), `factor_trigger_distance` (75-82),
`factor_badge` (85-86), `factor_gap` (138-139, negative). Each with a scoring
test, a boundary test, and an absent-input test.

- [ ] **Step 6: Populate `FACTORS`**

```python
# append to swingbot/core/scanning/factors.py
FACTORS = [
    # exactly the factors Task 1's reconciliation document kept, in
    # breakdown display order
]
```

- [ ] **Step 7: Run tests and commit**

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`

```bash
git add swingbot/core/scanning/factors.py tests/scanning/test_factors.py
git commit -m "feat(v32): port quality.py components, RS/MTF/breadth now scorable"
```

---

# Phase 2 — Levels, the honesty cap, and config

### Task 5: Six levels and an explicit honesty cap

**Files:**
- Modify: `swingbot/core/scanning/confidence.py:133-141` (LEVELS), `:253`, `:471-486`
- Test: `tests/scanning/test_confidence_levels.py`

**Interfaces:**
- Consumes: `run_factors`, `FACTORS` from Tasks 2–4.
- Produces: `LEVELS` (6 bands), `honesty_cap(target_count) -> int`,
  `level_for_score(score, target_count) -> tuple[int, str]`.

Today the honesty property is emergent: `base_level = max(1, min(5, target_count))`
at `:253` plus at most +2 from adjustments. Extending naively to `min(6, …)`
would let two methods reach Lv6. This task makes the cap explicit and tested.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_confidence_levels.py
import pytest
from swingbot.core.scanning.confidence import (
    LEVELS, honesty_cap, level_for_score,
)


def test_levels_table_has_six_contiguous_bands():
    assert [lvl for lvl, _label, _lo, _hi in LEVELS] == [1, 2, 3, 4, 5, 6]
    for (_l, _lab, _lo, hi), (_l2, _lab2, lo2, _hi2) in zip(LEVELS, LEVELS[1:]):
        assert lo2 == hi + 1, "level bands must be contiguous with no gap"


@pytest.mark.parametrize("methods,expected_cap", [
    (0, 1), (1, 3), (2, 4), (3, 5), (4, 6), (9, 6),
])
def test_honesty_cap_by_method_count(methods, expected_cap):
    """One method can never exceed Lv3, two never Lv4, three never Lv5.
    Level 6 additionally requires a FOURTH independent method -- stricter
    than Lv5's 3, per the spec."""
    assert honesty_cap(methods) == expected_cap


def test_high_score_cannot_beat_the_cap():
    """A perfect 100 on one confirming method still caps at Level 3. This is
    the whole point of the honesty property."""
    level, _label = level_for_score(100, target_count=1)
    assert level == 3


def test_level_six_needs_four_methods_even_at_full_score():
    assert level_for_score(100, target_count=3)[0] == 5
    assert level_for_score(100, target_count=4)[0] == 6


def test_low_score_is_not_rescued_by_many_methods():
    """The cap only ever lowers a level, never raises one."""
    level, _label = level_for_score(5, target_count=9)
    assert level == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: FAIL — `ImportError: cannot import name 'honesty_cap'`

- [ ] **Step 3: Write minimal implementation**

```python
# swingbot/core/scanning/confidence.py -- replace the LEVELS table at :133
LEVELS = [
    (1, "Very Low", 0, 20),
    (2, "Low", 21, 40),
    (3, "Medium", 41, 60),
    (4, "High", 61, 75),
    (5, "Very High", 76, 90),
    (6, "Elite", 91, 100),
]
_LEVEL_LABELS = {lvl: label for lvl, label, _lo, _hi in LEVELS}
_LEVEL_RANGE = {lvl: (lo, hi) for lvl, _label, lo, hi in LEVELS}

# Method-count ceiling. Until v32 this was emergent -- min(5, target_count)
# plus at most +2 of adjustment -- which meant extending the scale to 6
# would have silently let TWO methods reach Elite. It is explicit now.
_HONESTY_CAP = {0: 1, 1: 3, 2: 4, 3: 5}
_MAX_LEVEL = 6


def honesty_cap(target_count: int) -> int:
    """Highest level `target_count` independent confirming methods may reach.
    Level 6 needs 4+, one stricter than Level 5's 3+."""
    return _HONESTY_CAP.get(max(0, int(target_count)), _MAX_LEVEL)


def level_for_score(score: int, target_count: int) -> tuple[int, str]:
    """Map a 0-100 score to a level, then lower it to the honesty cap if the
    method count does not support it. The cap never raises a level."""
    level = _MAX_LEVEL
    for lvl, _label, lo, hi in LEVELS:
        if lo <= score <= hi:
            level = lvl
            break
    level = min(level, honesty_cap(target_count))
    return level, _LEVEL_LABELS[level]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/confidence.py tests/scanning/test_confidence_levels.py
git commit -m "feat(v32): six levels with an explicit honesty cap"
```

---

### Task 6: Rewire `score_confidence()` onto the registry, behind the flag

**Files:**
- Modify: `swingbot/core/scanning/confidence.py:214-496`
- Modify: `swingbot/config.py` (add `UNIFIED_CONFIDENCE`)
- Test: `tests/scanning/test_confidence_levels.py`

**Interfaces:**
- Consumes: `run_factors`/`FACTORS` (Tasks 2–4), `level_for_score` (Task 5).
- Produces: `score_confidence()` with an unchanged signature and
  `ConfidenceResult` shape — every existing caller keeps working.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_confidence_levels.py
from swingbot import config
from swingbot.core.scanning.confidence import score_confidence


def test_legacy_path_is_bit_identical_when_flag_off(monkeypatch, sample_scenario):
    """Default-OFF must mean *nothing changes*. This is the safety property
    the whole rollout depends on."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    result = score_confidence(sample_scenario, regime_trend="bullish", df=None)
    assert result.level == LEGACY_EXPECTED_LEVEL
    assert result.score == LEGACY_EXPECTED_SCORE


def test_unified_path_returns_same_result_shape(monkeypatch, sample_scenario):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(sample_scenario, regime_trend="bullish", df=None)
    assert 1 <= result.level <= 6
    assert 0 <= result.score <= 100
    assert isinstance(result.breakdown, dict)
```

`LEGACY_EXPECTED_LEVEL`/`LEGACY_EXPECTED_SCORE` are captured by running the
current implementation against `sample_scenario` **before** editing it, and
pasted in as literals. Add `sample_scenario` to `tests/scanning/conftest.py`
if no equivalent fixture exists.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: FAIL — `AttributeError: config has no attribute 'UNIFIED_CONFIDENCE'`

- [ ] **Step 3: Add the config flag**

```python
# swingbot/config.py -- beside MIN_ALERT_CONFIDENCE_LEVEL at :166
    Field("UNIFIED_CONFIDENCE", "UNIFIED_CONFIDENCE", "Trade Filters & Risk",
          "Unified confidence score (v32)",
          type="checkbox", default="false",
          help="Score alerts with the merged factor registry, so relative strength, "
               "multi-timeframe alignment and market breadth affect which alerts fire. "
               "Off = the legacy 1-5 score. Enable only after VALIDATION."),
```

- [ ] **Step 4: Branch `score_confidence` on the flag**

Keep the existing body as `_score_confidence_legacy()` untouched, and add:

```python
def score_confidence(scenario, regime_trend: str = None, df=None,
                     target_confluence=None, stop_confluence=None,
                     track_record=None, **kwargs):
    if not getattr(config, "UNIFIED_CONFIDENCE", False):
        return _score_confidence_legacy(
            scenario, regime_trend=regime_trend, df=df,
            target_confluence=target_confluence,
            stop_confluence=stop_confluence, track_record=track_record,
            **kwargs)

    target_count, target_families = _resolve_confluence(
        target_confluence, scenario.target_sources)
    stop_count, stop_families = _resolve_confluence(
        stop_confluence, scenario.stop_sources)

    ctx = FactorContext(
        scenario=scenario, df=df, regime_trend=regime_trend,
        target_count=target_count, target_families=target_families,
        stop_count=stop_count, stop_families=stop_families,
        **{k: kwargs.get(k) for k in
           ("htf_bias", "rs_percentile", "mtf", "breadth", "volume_ratio",
            "atr_pct", "trigger_distance_pct", "badge_status")},
    )
    raw, breakdown = run_factors(FACTORS, ctx)
    score = max(0, min(100, raw))

    # Method count is re-read AFTER the factors run: the squeeze and
    # candlestick factors append to scenario.target_sources, so counting
    # earlier would miss confirmations they just added.
    target_count, _ = _resolve_confluence(None, scenario.target_sources)
    level, label = level_for_score(score, target_count)
    breakdown["Confirming methods"] = (
        f"{target_count} independent method(s) -> caps at Level "
        f"{honesty_cap(target_count)}")
    return ConfidenceResult(level=level, label=label, score=score,
                            breakdown=breakdown)
```

Extract the duplicated confluence-resolution at `:240-250` into
`_resolve_confluence(explicit, sources) -> tuple[int, list]` and use it in both
paths.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: PASS

- [ ] **Step 6: Fix the duplicated band arithmetic at `engine.py:939`**

`engine.py` re-buckets the level after the HTF counter-trend penalty with a
**hardcoded** copy of the band boundaries:

```python
new_level = max(1, min(5, 1 + new_score // 20))   # assumes 5 equal 20-pt bands
```

Task 5's recalibrated bands are *not* five equal 20-point bands, so this
silently computes the wrong level the moment v32 lands. It must go through the
single source of truth instead:

```python
from .confidence import level_for_score
new_level, new_label = level_for_score(new_score, target_count)
```

Add a regression test asserting `engine`'s post-penalty level equals
`level_for_score(new_score, target_count)` for a score in a non-20-wide band
(e.g. 78, which is Level 5 under the new table but Level 4 under `1 + 78//20`).

- [ ] **Step 7: Run the fast tier — nothing else may move**

Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/confidence.py swingbot/core/scanning/engine.py swingbot/config.py tests/scanning/test_confidence_levels.py
git commit -m "feat(v32): score_confidence runs the factor registry behind UNIFIED_CONFIDENCE"
```

---

### Task 7: Feed the real RS/MTF/breadth values into `score_confidence`

**Files:**
- Modify: `swingbot/core/scanning/engine.py:917`
- Test: `tests/scanning/test_engine_quality_inputs.py`

**Interfaces:**
- Consumes: `score_confidence`'s kwargs (Task 6).
- Produces: nothing new — this is the wiring that makes the spec's premise true.

`engine.py:917` currently calls `score_confidence(scenario, regime_trend=…, df=df, …)`
with no RS, MTF or breadth. The values exist in scope — `item.rs_percentile`
and `item.breadth` are already passed to `attach_plan_v2` at `:1251`.

- [ ] **Step 1: Write the failing test**

```python
# tests/scanning/test_engine_quality_inputs.py
def test_score_confidence_receives_rs_mtf_breadth(monkeypatch):
    """Regression guard for the v32 premise: these three were computed and
    then never handed to the gate. If this test fails, RS/MTF/breadth have
    stopped influencing which alerts fire."""
    captured = {}

    def fake_score(scenario, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(level=4, label="High", score=70, breakdown={})

    monkeypatch.setattr("swingbot.core.scanning.engine.score_confidence", fake_score)
    _run_one_scan_item_with(rs_percentile=82.0, breadth=61.0)

    assert captured["rs_percentile"] == 82.0
    assert captured["breadth"] == 61.0
    assert captured["mtf"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_quality_inputs.py`
Expected: FAIL — `KeyError: 'rs_percentile'`

- [ ] **Step 3: Pass the values through**

```python
# swingbot/core/scanning/engine.py:917
conf = score_confidence(
    scenario,
    regime_trend=(regime.trend if regime else None),
    df=df,
    rs_percentile=getattr(item, "rs_percentile", None),
    breadth=getattr(item, "breadth", None),
    mtf=rs_factors.mtf_alignment(df, scenario.direction) if df is not None else None,
    htf_bias=(get_htf_bias(df, horizon_key) or {}).get("bias"),
    ...  # keep every existing keyword argument
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_quality_inputs.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_engine_quality_inputs.py
git commit -m "feat(v32): hand RS/MTF/breadth to the alert gate for the first time"
```

---

# Phase 3 — Measure, weight, validate

### Task 8: TRAIN factor-lift measurement and Wilson intervals

**Files:**
- Create: `scripts/backtest/measure_factor_lift.py`
- Test: `tests/backtesting/test_factor_lift.py`

**Interfaces:**
- Produces: `wilson_interval(wins, n, z=1.96) -> tuple[float, float]`,
  `factor_lift_table(trades) -> list[dict]`, and a JSON report.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_factor_lift.py
import pytest
from scripts.backtest.measure_factor_lift import wilson_interval


def test_wilson_interval_matches_known_values():
    lo, hi = wilson_interval(95, 100)
    assert lo == pytest.approx(0.8872, abs=0.001)
    assert hi == pytest.approx(0.9793, abs=0.001)


def test_wilson_lower_bound_is_brutal_on_small_samples():
    """6/6 wins looks like 100% and is worth almost nothing. This is exactly
    the claim the Level 6 gate exists to reject."""
    lo, _hi = wilson_interval(6, 6)
    assert lo < 0.65


def test_wilson_interval_handles_zero_samples():
    assert wilson_interval(0, 0) == (0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_factor_lift.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/backtest/measure_factor_lift.py
"""TRAIN-only per-factor win-rate lift for v32. Prints one flushed line per
ticker (CLAUDE.md: any script running more than a couple of minutes must
report progress per unit of work, not just a final summary)."""
import math


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Unlike the normal
    approximation it stays inside [0,1] and stays honest at small n --
    which is the entire reason the Level 6 gate uses it."""
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_factor_lift.py -v`
Expected: PASS

- [ ] **Step 5: Add the lift table and the per-level report**

`factor_lift_table(trades)` returns, per factor: n, win rate with the factor
scoring above its median, win rate below, the lift between them, and the Wilson
interval on each. A separate per-level table reports n / win rate / Wilson
bounds for levels 1–6 — this is the table Task 9 reads to decide Level 6.

Print one flushed line per ticker processed.

- [ ] **Step 6: Run the TRAIN measurement**

Dispatch via the `backtest-runner` subagent. Requires the CSV cache
(`python scripts/data/fetch_backtest_data.py`) if not already populated.

Run: `python scripts/backtest/measure_factor_lift.py --train --json data/v32_train_lift.json`

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_factor_lift.py tests/backtesting/test_factor_lift.py data/v32_train_lift.json
git commit -m "feat(v32): TRAIN factor-lift measurement with Wilson intervals"
```

---

### Task 9: Re-weight from TRAIN, and decide Level 6

**Files:**
- Modify: `swingbot/core/scanning/factors.py` (point values only)
- Modify: `swingbot/core/scanning/confidence.py` (LEVELS bands only)
- Create: `docs/superpowers/plans/v32-train-preregistration.md`

**Interfaces:**
- Consumes: `data/v32_train_lift.json` (Task 8).
- Produces: final weights and the Level 6 verdict.

- [ ] **Step 1: Write the pre-registration BEFORE looking at VALIDATION**

The acceptance gate, committed before the Task 10 run and **not revised after
seeing its result**:

```markdown
## v32 VALIDATION pre-registration
- Primary: win rate (TP1 before stop) at MIN_ALERT_CONFIDENCE_LEVEL=4.
- PASS: win rate improves vs. the legacy scorer on the same VALIDATION window,
  AND alert volume falls by no more than 30%.
- FAIL: any regression in win rate, or volume loss > 30%.
- Level 6 ships only if TRAIN showed n>=100, point estimate >=90%,
  Wilson lower bound >=80% and above Level 5's point estimate.
- One shot. A FAIL means UNIFIED_CONFIDENCE stays default-off.
```

- [ ] **Step 2: Re-weight each factor proportionally to measured lift**

Assign points from each factor's measured lift, normalized so the kept factors
sum to 100. Round to integers — the breakdown renders verbatim in embeds.
A factor with a lift indistinguishable from zero (Wilson intervals overlapping
across its median split) gets **dropped**, not given token points.

- [ ] **Step 3: Recalibrate the level bands**

Adjust the `LEVELS` band edges so that `MIN_ALERT_CONFIDENCE_LEVEL=4` admits an
alert population within ±10% of today's count on the TRAIN window, so the
default keeps roughly its current meaning.

- [ ] **Step 4: Decide Level 6 against the three criteria**

If the top band does not clear all three, **remove Level 6**: restore the
five-band `LEVELS` table, set `_HONESTY_CAP`'s fallback to 5, revert the
config `options` to `["1".."5"]`, and record the negative result in the
pre-registration document. A negative result here is a finished task.

- [ ] **Step 5: Run the level-mapping tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`

Update the parametrized cap expectations if Level 6 was dropped.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/factors.py swingbot/core/scanning/confidence.py docs/superpowers/plans/v32-train-preregistration.md
git commit -m "feat(v32): TRAIN-derived weights, level bands recalibrated"
```

---

### Task 10: The single VALIDATION run

**Files:**
- Modify: `docs/superpowers/plans/v32-train-preregistration.md` (result only)
- Modify: `swingbot/config.py` (default flip, only on PASS)

- [ ] **Step 1: Confirm the pre-registration is committed and unedited**

Run: `git log --oneline -- docs/superpowers/plans/v32-train-preregistration.md`
Expected: the Task 9 commit, with no later edits to the gate.

- [ ] **Step 2: Run VALIDATION once**

Dispatch via the `backtest-runner` subagent.

Run: `python scripts/backtest/run_backtest_range.py --validation --json data/v32_validation.json`

- [ ] **Step 3: Record the result verbatim**

Append measured win rate, alert volume delta and the verdict to the
pre-registration. **Do not re-run on a FAIL.**

- [ ] **Step 4: On PASS only, flip the default**

```python
# swingbot/config.py
    Field("UNIFIED_CONFIDENCE", "UNIFIED_CONFIDENCE", "Trade Filters & Risk",
          "Unified confidence score (v32)",
          type="checkbox", default="true",
```

And extend the level selector:

```python
# swingbot/config.py:167
          type="select", default="4", options=["1", "2", "3", "4", "5", "6"],
```

On FAIL, leave both as they are and stop. The spec's outcome is then a measured
negative result, which is a completed spec.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py docs/superpowers/plans/v32-train-preregistration.md
git commit -m "feat(v32): VALIDATION result and default-state decision"
```

---

# Phase 4 — Retire tier, then ship

### Task 11: Remove A/B/C tier from the seven consumers

**Files:**
- Modify: `swingbot/core/planning/quality.py:89-101`, `core/planning/plan_engine.py:605`,
  `core/planning/plan_manager.py:161`, `core/scanning/embeds.py:390`,
  `commands/plans.py:71,88`, `commands/views.py:136,201,226,229`,
  `admin/queries.py:146`
- Test: `tests/planning/test_quality.py`, `tests/commands/test_plans.py`

**Interfaces:**
- Produces: `QualityResult` without `tier`; plan records without `tier`.

Wider than a field deletion: `views.py` has a **live Discord tier filter** and
`plan_manager.py` **persists** tier onto records.

- [ ] **Step 1: Write the failing test**

```python
# tests/planning/test_quality.py
def test_quality_result_has_no_tier():
    """QualityResult was (score, tier, breakdown); it becomes (score, breakdown)."""
    from swingbot.core.planning.quality import QualityResult
    result = QualityResult(score=50, breakdown=[("regime", 15)])
    assert not hasattr(result, "tier")
    assert result.score == 50


def test_score_plan_no_longer_returns_a_tier():
    from swingbot.core.planning.quality import score_plan
    result = score_plan(direction="bullish", regime="bullish", htf_bias="bullish",
                        confluence_count=3, volume_ratio=1.5, atr_pct=0.5,
                        trigger_distance_pct=0.4, badge_status="VALIDATED")
    assert not hasattr(result, "tier")


def test_legacy_plan_record_with_tier_still_loads():
    """Persisted records written before v32 carry a tier field. Loading one
    must not raise -- users have live plans on disk."""
    from swingbot.core.planning.plan_manager import _plan_from_dict
    plan = _plan_from_dict({"plan_id": "x", "ticker": "AAPL", "tier": "A",
                            "quality_score": 80})
    assert plan.ticker == "AAPL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_quality.py`
Expected: FAIL — `QualityResult` still has `tier`

- [ ] **Step 3: Remove `_tier` and the `tier` field**

Delete `_tier()` (`quality.py:89-94`) and `tier` from `QualityResult`.
Update `plan_engine.py:605` to `plan.quality_score = q.score`.

- [ ] **Step 4: Replace the Discord tier filter with a level filter**

`views.py:201,226,229` filter by tier. Replace with a **confidence-level**
filter over 1–6 (or 1–5 if Task 9 dropped Level 6). `plans.py:88`'s `tier`
argument becomes `level`, parsed as an int.

- [ ] **Step 5: Update the display surfaces**

`embeds.py:390` → `f"Quality: {plan.quality_score}/100"`.
`views.py:136` → `f"🔍 Breakdown — {plan.ticker} ({plan.badge})"`.
`queries.py:146` → aggregate by confidence level instead of tier.

- [ ] **Step 6: Tolerate legacy persisted records**

`plan_manager.py` must ignore an unknown `tier` key on read rather than raising.

- [ ] **Step 7: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(v32): retire A/B/C tier in favour of confidence levels"
```

---

### Task 12: Re-point the decile audit and E43 ablation harness

**Files:**
- Modify: the decile-audit and ablation scripts under `scripts/`

Task 11 removed the structure these two measure against. Leaving them broken
would strand the evidence behind the thresholds v32 keeps.

- [ ] **Step 1: Locate both harnesses**

Run: `git grep -rln "decile\|ablation" -- scripts/ tests/`

- [ ] **Step 2: Re-point the decile audit at confidence levels**

Replace A/B/C bucketing with the 1–6 level bands. Its output table keeps the
same shape so historical runs stay comparable.

- [ ] **Step 3: Re-point the ablation harness at `FACTORS`**

It ablates one component at a time; make it iterate `FACTORS` and drop one per
run, which is strictly more general than the hardcoded component list.

- [ ] **Step 4: Run both and confirm they produce tables**

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(v32): re-point decile audit and ablation harness at the merged score"
```

---

### Task 13: Documentation and version bump

**Files:**
- Modify: `docs/strategy.md`, `README.md`, `VERSION.json`
- Modify: `docs/superpowers/specs/2026-08-16-v32-unified-confidence-score-design.md`

- [ ] **Step 1: Correct `docs/strategy.md`**

It is wrong in ways this plan uncovered, independently of v32's changes:
- `MIN_ALERT_CONFIDENCE_LEVEL` default is **4**, not 3.
- The honesty gate is now a real explicit cap (it describes one that never existed).
- Horizons: **10** (`2w`…`9m`), not 5.
- Level methods now include anchored VWAP, RS, MTF and breadth.
- Confidence is 1–6 (or 1–5 if Task 9 dropped it).

- [ ] **Step 2: Update the spec's `Bump:` line to what actually shipped**

Per `docs/claude/document-conventions.md`, a prediction that missed is amended
with one clause on why — not hidden.

- [ ] **Step 3: Bump `VERSION.json`**

`bot` minor → `1.2.0` on a VALIDATION PASS. On FAIL, no bot bump (no observable
change shipped); `ui` patch only if Task 11's control changes shipped.

- [ ] **Step 4: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`

- [ ] **Step 5: Move the spec to `implemented/`**

```bash
git mv docs/superpowers/specs/2026-08-16-v32-unified-confidence-score-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-16-v32-unified-confidence-score.md docs/superpowers/plans/implemented/
```

Re-point every reference in the same commit — v33–v36 all cite this spec.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs(v32): correct strategy.md, bump version, close the spec"
```

---

## Parallelisation

- **Sequential: Task 1 before everything.** Every later task implements the
  factor set it decides.
- **Group A (parallel, after Task 1):** Task 3 and Task 4 — both append to
  `factors.py`. **Only if executed by one agent**; two agents on one file
  overwrite rather than merge in this shared working tree. Two agents means
  running them sequentially.
- **Sequential: Tasks 5 → 6 → 7.** Task 6 consumes Task 5's `level_for_score`;
  Task 7 consumes Task 6's kwargs.
- **Group B (parallel):** Task 8 (new script + test) alongside Tasks 5–7 —
  disjoint files, no contract dependency.
- **Sequential: Tasks 9 → 10.** Weights before VALIDATION; the pre-registration
  must be committed before the run.
- **Group C (parallel, after Task 10):** Task 11 and Task 12 are **not**
  parallel — Task 12 measures what Task 11 changes.
- **Sequential: Task 13 last.**

## Progress

- [ ] Task 1 — Factor reconciliation
- [ ] Task 2 — Registry contract
- [ ] Task 3 — Port confidence.py factors
- [ ] Task 4 — Port quality.py components (RS/MTF/breadth)
- [ ] Task 5 — Six levels + honesty cap
- [ ] Task 6 — Rewire score_confidence behind the flag
- [ ] Task 7 — Feed real RS/MTF/breadth to the gate
- [ ] Task 8 — TRAIN factor-lift measurement
- [ ] Task 9 — Re-weight, decide Level 6
- [ ] Task 10 — VALIDATION run
- [ ] Task 11 — Retire tier
- [ ] Task 12 — Re-point audit + ablation
- [ ] Task 13 — Docs + version bump
