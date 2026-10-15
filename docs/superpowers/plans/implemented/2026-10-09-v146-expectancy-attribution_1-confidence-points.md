# v146 Expectancy attribution: Part 1, numeric confidence points (I1)

> Part of the v146 plan. Header, Global Constraints, Handoff decisions, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v146-expectancy-attribution_0-index.md). **Never read this file whole**: `/task-brief V146-2` or `grep -n "^### Task V146-2:" -A 400 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_1-confidence-points.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md) § I1, § Testing (I1).

All commands run inside the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution` (created by V146-1 Step 0). Paths below are relative to it. Never `cd` in Bash: use `git -C <worktree>` and absolute paths, or run from a session rooted in the worktree.

Order inside this part: V146-1 → V146-2 → (V146-3 ∥ V146-4). Both scorers keep today's level, label, score and breakdown byte for byte; the only additions are the `points` and `unevaluated` attributes and the fields that carry them.

---

### Task V146-1: Unified scorer and `run_factors` return numeric points

**Model:** sonnet — a three-caller signature widening plus a new dataclass field, every value fixed by the spec.

**Files:**
- Modify: `swingbot/core/scanning/factors.py` (`run_factors`, lines 62-73)
- Modify: `swingbot/core/scanning/confidence.py` (`ConfidenceResult` at 232-236; unified path of `score_confidence` at 626-638)
- Modify: `scripts/backtest/measure_factor_lift.py` (lines 207-216)
- Modify: `tests/scanning/test_factors.py` (the three `run_factors` tests, lines 20-52)
- Create: `tests/scanning/test_confidence_points.py`

**Interfaces:**
- Consumes (existing): `factors.FactorResult(name: str, points: int, line: str)`, `factors.FactorContext`, `factors.FACTORS` (imported by name into `confidence`, so `monkeypatch.setattr(confidence, "FACTORS", [...])` swaps the registry the unified path reads), `confidence.score_confidence(scenario, regime_trend=None, df=None, target_confluence=None, stop_confluence=None, track_record=None, **kwargs) -> ConfidenceResult`, `swingbot.core.market.levels.Scenario`.
- Produces: `run_factors(factors, ctx) -> tuple[int, dict[str, str], dict[str, int]]` — `(total, {name: line}, {name: points})`, factors returning `None` absent from both maps. `ConfidenceResult.points: dict[str, int]` (default `{}`), `ConfidenceResult.unevaluated: list[str]` (default `[]`). The unified path fills `points` from the third map and leaves `unevaluated == []` (a unified factor with no input returns `None` and is omitted, so it never has a fallback line). `tests/scanning/test_confidence_points.py` exists with a `_scenario(**over) -> Scenario` helper that V146-2 extends.

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then create the branch and worktree from `main`:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add -b 2026-10-09-v146-expectancy-attribution E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution main
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
```

Expected: the new worktree is listed on branch `2026-10-09-v146-expectancy-attribution`. If `git worktree list` already shows it, reuse it and resume at the first uncommitted task.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_confidence_points.py`:

```python
"""v146 I1: ConfidenceResult carries the integer each scored factor added.

Unified path (V146-1) and legacy path (V146-2, appended below). The
breakdown text is never parsed here: every expected integer comes from the
scorer's own rule table, so a test fails if `points` and the scorer disagree.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.market.levels import Scenario
from swingbot.core.scanning import confidence
from swingbot.core.scanning.confidence import ConfidenceResult, score_confidence
from swingbot.core.scanning.factors import FactorResult


def _scenario(**over) -> Scenario:
    base = dict(
        direction="bullish", entry=100.0, market_price=100.0, stop_loss=98.0,
        stop_sources=["EMA", "VWAP"], stop_distance_pct=2.0, tight_stop=False,
        atr_floor_pct=1.5, take_profit=106.0, target_distance_pct=6.0,
        target_sources=["EMA", "VWAP", "Fibonacci"], target2_price=None,
        target2_distance_pct=None, target2_sources=None,
    )
    base.update(over)
    return Scenario(**base)


# --- unified path (V146-1) --------------------------------------------

def test_confidence_result_points_and_unevaluated_default_empty_and_unshared():
    first = ConfidenceResult(level=3, label="Medium", score=50)
    assert first.points == {} and first.unevaluated == []
    first.points["x"] = 1
    first.unevaluated.append("x")
    second = ConfidenceResult(level=3, label="Medium", score=50)
    assert second.points == {} and second.unevaluated == []


def test_unified_points_are_each_factor_results_integer(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)

    def f_trend(ctx):
        return FactorResult("Trend", 12, "trend agrees (+12)")

    def f_absent(ctx):
        return None

    def f_gap(ctx):
        return FactorResult("Gap penalty", -10, "⚠️ fragile gap risk (-10)")

    monkeypatch.setattr(confidence, "FACTORS", [f_trend, f_absent, f_gap])
    result = score_confidence(_scenario(), regime_trend="bullish", df=None)
    assert result.points == {"Trend": 12, "Gap penalty": -10}
    assert result.unevaluated == []
    assert "Confirming methods" in result.breakdown
    assert "Confirming methods" not in result.points


def test_unified_points_sum_to_the_unclamped_score(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)

    def f_a(ctx):
        return FactorResult("A", 30, "a (+30)")

    def f_b(ctx):
        return FactorResult("B", 25, "b (+25)")

    monkeypatch.setattr(confidence, "FACTORS", [f_a, f_b])
    result = score_confidence(_scenario(), regime_trend="bullish", df=None)
    assert sum(result.points.values()) == result.score == 55


def test_unified_real_registry_records_its_zero_and_penalty_factors(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(
        _scenario(), regime_trend="bullish", df=None, gap_fragile=True,
        macro_verdict={"status": "aligned", "reason": "agrees", "trend": "bullish"})
    assert result.points == {"Gap penalty": -10, "Macro trend (6m)": 0}
```

In `tests/scanning/test_factors.py`, replace the three `run_factors` tests (lines 20-52) with:

```python
def test_run_factors_sums_points_and_collects_breakdown():
    def f_a(ctx):
        return FactorResult("a", 5, "a (+5)")

    def f_b(ctx):
        return FactorResult("b", 3, "b (+3)")

    total, breakdown, points = run_factors([f_a, f_b], _ctx())
    assert total == 8
    assert breakdown == {"a": "a (+5)", "b": "b (+3)"}
    assert points == {"a": 5, "b": 3}


def test_run_factors_skips_factors_returning_none():
    """A factor whose input is absent returns None and must not appear in the
    breakdown at all -- an absent reading must never render as a real one that
    happened to score zero. The same holds for the numeric points map."""
    def f_present(ctx):
        return FactorResult("present", 4, "present (+4)")

    def f_absent(ctx):
        return None

    total, breakdown, points = run_factors([f_present, f_absent], _ctx())
    assert total == 4
    assert "absent" not in breakdown
    assert points == {"present": 4}


def test_run_factors_propagates_negative_points():
    def f_penalty(ctx):
        return FactorResult("penalty", -10, "penalty (-10)")

    total, _, points = run_factors([f_penalty], _ctx())
    assert total == -10
    assert points == {"penalty": -10}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_points.py`
Expected: FAIL — `AttributeError: 'ConfidenceResult' object has no attribute 'points'`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: FAIL — `ValueError: not enough values to unpack (expected 3, got 2)`.

- [ ] **Step 3: Implement**

In `swingbot/core/scanning/factors.py`, replace `run_factors`:

```python
def run_factors(factors: list[Factor], ctx: FactorContext) -> tuple[int, dict, dict]:
    """Returns (total_points, {name: line}, {name: points}). Factors returning
    None are omitted from all three -- v146 I1 reads the third map so no
    caller ever has to parse a line for its integer."""
    total = 0
    breakdown: dict[str, str] = {}
    points: dict[str, int] = {}
    for fn in factors:
        result = fn(ctx)
        if result is None:
            continue
        total += result.points
        breakdown[result.name] = result.line
        points[result.name] = int(result.points)
    return total, breakdown, points
```

In `swingbot/core/scanning/confidence.py`, replace the `ConfidenceResult` dataclass:

```python
@dataclass
class ConfidenceResult:
    level: int
    label: str
    score: int
    breakdown: dict = field(default_factory=dict)
    # v146 I1: the integer each scored factor added, keyed exactly as in
    # `breakdown`. Non-factor lines (base level, quality score, track record,
    # level adjustment, confirming methods) never appear here.
    points: dict = field(default_factory=dict)
    # v146 I1: factors whose line was a neutral fallback for a missing input
    # ("regime unavailable", "not evaluated ..."). Their `points` entry is the
    # integer awarded, so the sum still reconciles; this list lets a reader
    # keep "no data" out of a per-factor comparison.
    unevaluated: list = field(default_factory=list)
```

In the unified path of `score_confidence`, replace `raw, breakdown = run_factors(FACTORS, ctx)` with:

```python
    raw, breakdown, points = run_factors(FACTORS, ctx)
```

and its final return with:

```python
    return ConfidenceResult(level=level, label=label, score=score, breakdown=breakdown,
                            points=points, unevaluated=[])
```

In `scripts/backtest/measure_factor_lift.py`, replace lines 207-216 (the `run_factors` call through the re-derive loop) with:

```python
                    score_raw, _breakdown, points = run_factors(FACTORS, ctx)
                    score = max(0, min(100, score_raw))
                    level, _label = level_for_score(score, target_confluence[0])
```

(The comment and the `for fn in FACTORS:` loop that re-called every factor to recover its points are deleted: `run_factors` now returns them. The `rows.append({... "points": points})` that follows is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_points.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_factors.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: `VERDICT: PASS` (the legacy bit-identical pin, `LEGACY_EXPECTED_LEVEL = 4`, `LEGACY_EXPECTED_SCORE = 73`, still holds).

Run: `python scripts/dev/testrun.py file tests/backtesting/test_factor_lift.py`
Expected: `VERDICT: PASS`.

Run: `python -m py_compile scripts/backtest/measure_factor_lift.py`
Expected: no output.

Confirm no caller still unpacks two values:

Run: `git grep -n "run_factors(" -- swingbot scripts tests`
Expected: every call site unpacks three values (`confidence.py`, `measure_factor_lift.py`, `tests/scanning/test_factors.py`); `factors.py` holds the definition.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s swingbot/core/scanning/factors.py swingbot/core/scanning/confidence.py`
Expected: `run_factors - A (3)`, `score_confidence - A (4)`, `ConfidenceResult - A (1)`, `_score_confidence_legacy - E (40)` — all unchanged.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/scanning/factors.py swingbot/core/scanning/confidence.py scripts/backtest/measure_factor_lift.py tests/scanning/test_factors.py tests/scanning/test_confidence_points.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): run_factors and the unified scorer return numeric factor points"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command prints nothing (the main tree is unchanged).

---

### Task V146-2: Legacy scorer stamps points and unevaluated factors

**Model:** opus — edits inside the E40 legacy scorer that production runs; every branch must stay byte-identical and the complexity must not move.

**Files:**
- Modify: `swingbot/core/scanning/confidence.py` (new `LEGACY_POINT_KEYS` and `_legacy_points` just above `_score_confidence_legacy` at line 319; fallback branches at 387-394, 400-418, 425-451, 458-487, 494-514, 519-532; tight-stop block at 538-549; final return at 591)
- Modify: `tests/scanning/test_confidence_points.py` (created by V146-1)

**Interfaces:**
- Consumes: `ConfidenceResult.points` / `.unevaluated` (V146-1); `tests/scanning/test_confidence_points._scenario(**over)` (V146-1).
- Produces: `confidence.LEGACY_POINT_KEYS: tuple[str, ...]` = `("Target distance quality", "Stop level confluence", "Market regime alignment", "ADX trend strength", "MACD momentum", "RSI trend alignment", "TTM Squeeze + volume breakout", "Candlestick pattern", "Tight stop penalty")`. The legacy path returns `points` with the first eight keys always present and `"Tight stop penalty"` (a negative int, or `0` when the shortfall rounds to zero) present exactly when its breakdown line is. `unevaluated` lists, in scoring order, every factor whose line is a fallback: `"Market regime alignment"` when `regime_trend is None`; `"ADX trend strength"` when `df is None` or ADX is `None`; `"MACD momentum"` when `df is None`; `"RSI trend alignment"` when `df is None` or RSI is `None`; `"TTM Squeeze + volume breakout"` and `"Candlestick pattern"` when `df is None`. Test helper `scenario_matrix() -> list[tuple[str, ConfidenceResult]]` in `tests/scanning/test_confidence_points.py` (one legacy result per rule-table case; V146-3 imports it).

- [ ] **Step 1: Write the failing tests**

Append to `tests/scanning/test_confidence_points.py` (the imports go to the top of the file, merged with the existing ones):

```python
from types import SimpleNamespace
from unittest import mock

import pytest

from swingbot.core.scanning.confidence import LEGACY_POINT_KEYS


# --- legacy path (V146-2) ---------------------------------------------
#
# Every indicator the legacy scorer reads is stubbed, so each case drives
# exactly one branch and the expected integer is the rule table's, not a
# re-reading of the line. `_DF` is any non-None object: with every
# indicator stubbed, the scorer only ever tests `df is not None`.

_DF = object()

# The "evaluated, scores zero" reading of every indicator; a case overrides
# the one it is about.
_BASE_READINGS = {
    "adx_trend_strength": {"adx": 18.0, "strong": False, "trending": False, "label": "ranging"},
    "macd_momentum_aligned": {"strength": "opposed", "macd_val": -0.1, "histogram": -0.05},
    "rsi_trend_aligned": {"rsi_val": 40.0, "strength": "opposed"},
    "squeeze_breakout_confirmation": {"confirmed": False, "is_squeeze": False, "width_pct": 3.0},
    "detect_confirming_pattern": {"confirmed": False, "bars_ago": None, "pattern": None},
}

_NON_FACTOR_KEYS = {
    "Strategies confirmed (base level)", "Quality score", "Track record (expectancy)",
    "Level adjustment", "Confirming methods",
}


def _case(label, key, points, unevaluated=False, *, readings=None, scenario=None,
          regime="bullish", df=_DF):
    return SimpleNamespace(label=label, key=key, points=points, unevaluated=unevaluated,
                           readings=readings or {}, scenario=scenario or {},
                           regime=regime, df=df)


_CASES = [
    _case("distance 1.2x", "Target distance quality", 12, scenario={"target_distance_pct": 6.0}),
    _case("distance capped", "Target distance quality", 20, scenario={"target_distance_pct": 15.0}),
    _case("stop two methods", "Stop level confluence", 10, scenario={"stop_sources": ["EMA", "VWAP"]}),
    _case("stop capped", "Stop level confluence", 15,
          scenario={"stop_sources": ["EMA", "VWAP", "Fibonacci", "Donchian"]}),
    _case("regime aligned", "Market regime alignment", 15, regime="bullish"),
    _case("regime counter", "Market regime alignment", 0, regime="bearish"),
    _case("regime unavailable", "Market regime alignment", 7, True, regime=None),
    _case("adx strong", "ADX trend strength", 15, readings={"adx_trend_strength": {
        "adx": 31.0, "strong": True, "trending": True, "label": "strong trend"}}),
    _case("adx trending", "ADX trend strength", 8, readings={"adx_trend_strength": {
        "adx": 22.0, "strong": False, "trending": True, "label": "emerging trend"}}),
    _case("adx ranging", "ADX trend strength", 0),
    _case("adx short history", "ADX trend strength", 7, True, readings={"adx_trend_strength": {
        "adx": None, "strong": False, "trending": False, "label": "n/a"}}),
    _case("adx no df", "ADX trend strength", 7, True, df=None),
    _case("macd strong", "MACD momentum", 15, readings={"macd_momentum_aligned": {
        "strength": "strong", "macd_val": 0.5, "histogram": 0.1}}),
    _case("macd moderate", "MACD momentum", 10, readings={"macd_momentum_aligned": {
        "strength": "moderate", "macd_val": 0.3, "histogram": 0.05}}),
    _case("macd weak", "MACD momentum", 5, readings={"macd_momentum_aligned": {
        "strength": "weak", "macd_val": 0.1, "histogram": -0.01}}),
    _case("macd opposed", "MACD momentum", 0),
    _case("macd no df", "MACD momentum", 7, True, df=None),
    _case("rsi strong", "RSI trend alignment", 10, readings={"rsi_trend_aligned": {
        "rsi_val": 62.0, "strength": "strong"}}),
    _case("rsi moderate", "RSI trend alignment", 6, readings={"rsi_trend_aligned": {
        "rsi_val": 56.0, "strength": "moderate"}}),
    _case("rsi weak", "RSI trend alignment", 3, readings={"rsi_trend_aligned": {
        "rsi_val": 51.0, "strength": "weak"}}),
    _case("rsi opposed", "RSI trend alignment", 0),
    _case("rsi short history", "RSI trend alignment", 5, True, readings={"rsi_trend_aligned": {
        "rsi_val": None, "strength": None}}),
    _case("rsi no df", "RSI trend alignment", 5, True, df=None),
    _case("squeeze fired", "TTM Squeeze + volume breakout", 10, readings={
        "squeeze_breakout_confirmation": {"confirmed": True, "is_squeeze": False, "width_pct": 4.0}}),
    _case("squeeze on", "TTM Squeeze + volume breakout", 5, readings={
        "squeeze_breakout_confirmation": {"confirmed": False, "is_squeeze": True, "width_pct": 2.0}}),
    _case("squeeze none", "TTM Squeeze + volume breakout", 0),
    _case("squeeze no df", "TTM Squeeze + volume breakout", 0, True, df=None),
    _case("candle today", "Candlestick pattern", 10, readings={"detect_confirming_pattern": {
        "confirmed": True, "bars_ago": 0, "pattern": "Bullish Engulfing"}}),
    _case("candle yesterday", "Candlestick pattern", 6, readings={"detect_confirming_pattern": {
        "confirmed": True, "bars_ago": 1, "pattern": "Hammer"}}),
    _case("candle none", "Candlestick pattern", 0),
    _case("candle no df", "Candlestick pattern", 0, True, df=None),
    _case("tight stop", "Tight stop penalty", -11, scenario={
        "tight_stop": True, "atr_floor_pct": 4.0, "stop_distance_pct": 1.0}),
    _case("tight stop capped", "Tight stop penalty", -15, scenario={
        "tight_stop": True, "atr_floor_pct": 2.0, "stop_distance_pct": 0.0}),
]


def _stub(value):
    return lambda *args, **kwargs: value


def _run(case) -> ConfidenceResult:
    readings = {**_BASE_READINGS, **case.readings}
    stubs = {name: _stub(value) for name, value in readings.items()}
    with mock.patch.multiple(confidence, **stubs), \
            mock.patch.object(config, "MIN_REWARD_PCT", 5.0), \
            mock.patch.object(config, "UNIFIED_CONFIDENCE", False):
        return score_confidence(_scenario(**case.scenario), regime_trend=case.regime, df=case.df)


def scenario_matrix() -> list[tuple[str, ConfidenceResult]]:
    """One legacy ConfidenceResult per rule-table case. V146-3's parser test
    imports this so the backfill parser is proven against every line form
    the legacy scorer can emit -- fallbacks and the negative penalty included."""
    return [(case.label, _run(case)) for case in _CASES]


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_equal_the_rule_table(case):
    result = _run(case)
    assert result.points[case.key] == case.points
    assert (case.key in result.unevaluated) is case.unevaluated


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_cover_exactly_the_scored_breakdown_lines(case):
    result = _run(case)
    assert set(result.points) == set(result.breakdown) - _NON_FACTOR_KEYS
    assert set(result.points) <= set(LEGACY_POINT_KEYS)
    assert set(result.unevaluated) <= set(result.points)


@pytest.mark.parametrize("case", _CASES, ids=[c.label for c in _CASES])
def test_legacy_points_reconcile_with_the_quality_score(case):
    result = _run(case)
    quality = int(result.breakdown["Quality score"].split("/", 1)[0])
    positive = sum(v for k, v in result.points.items() if k != "Tight stop penalty")
    penalty = result.points.get("Tight stop penalty", 0)
    assert quality == max(0, min(100, positive) + penalty)


def test_every_legacy_point_key_is_exercised():
    assert {case.key for case in _CASES} == set(LEGACY_POINT_KEYS)


def test_no_tight_stop_line_means_no_penalty_key():
    result = _run(_case("plain", "Target distance quality", 12))
    assert "Tight stop penalty" not in result.points


def test_no_price_history_marks_every_df_factor_unevaluated_in_scoring_order():
    result = _run(_case("no df", "ADX trend strength", 7, True, df=None))
    assert result.unevaluated == [
        "ADX trend strength", "MACD momentum", "RSI trend alignment",
        "TTM Squeeze + volume breakout", "Candlestick pattern",
    ]


def test_regime_and_df_missing_together_lists_regime_first():
    result = _run(_case("bare", "Market regime alignment", 7, True, regime=None, df=None))
    assert result.unevaluated[0] == "Market regime alignment"
    assert len(result.unevaluated) == 6


def test_scenario_matrix_returns_one_result_per_case():
    matrix = scenario_matrix()
    assert [label for label, _ in matrix] == [case.label for case in _CASES]
    assert all(isinstance(result, ConfidenceResult) for _, result in matrix)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_points.py`
Expected: FAIL — `ImportError: cannot import name 'LEGACY_POINT_KEYS'`.

- [ ] **Step 3: Implement**

In `swingbot/core/scanning/confidence.py`, insert directly above `def _score_confidence_legacy(`:

```python
# v146 I1: the legacy scorer's scored factors, in scoring order, keyed exactly
# as its breakdown lines. "Tight stop penalty" is negative and present only
# when its line is. The other breakdown keys (base level, quality score, track
# record, level adjustment) are not scored factors and never enter `points`.
LEGACY_POINT_KEYS = (
    "Target distance quality", "Stop level confluence", "Market regime alignment",
    "ADX trend strength", "MACD momentum", "RSI trend alignment",
    "TTM Squeeze + volume breakout", "Candlestick pattern", "Tight stop penalty",
)


def _legacy_points(scored: tuple, tight_penalty: int | None) -> dict[str, int]:
    """{factor: integer added} from the legacy scorer's eight point locals, in
    LEGACY_POINT_KEYS order, plus the penalty (negated) when it applied."""
    points = {key: int(value) for key, value in zip(LEGACY_POINT_KEYS[:-1], scored)}
    if tight_penalty is not None:
        points["Tight stop penalty"] = -int(tight_penalty)
    return points
```

Inside `_score_confidence_legacy`, make these edits only (each adds a statement, none adds a branch):

1. Directly after `breakdown = {}`:

```python
    breakdown = {}
    unevaluated: list[str] = []   # v146 I1: factors scored on a neutral fallback
```

2. Regime fallback branch:

```python
    if regime_trend is None:
        pts_regime = 7
        breakdown["Market regime alignment"] = "regime unavailable (+7)"
        unevaluated.append("Market regime alignment")
```

3. Both ADX fallback branches:

```python
        else:
            pts_adx = 7   # neutral when unavailable
            breakdown["ADX trend strength"] = "not evaluated (insufficient history) (+7)"
            unevaluated.append("ADX trend strength")
    else:
        pts_adx = 7
        breakdown["ADX trend strength"] = "not evaluated (no price history passed in) (+7)"
        unevaluated.append("ADX trend strength")
```

4. MACD fallback branch:

```python
    else:
        pts_macd = 7   # neutral when unavailable
        breakdown["MACD momentum"] = "not evaluated (no price history passed in) (+7)"
        unevaluated.append("MACD momentum")
```

5. Both RSI fallback branches:

```python
        if rsi_mom["rsi_val"] is None:
            pts_rsi = 5   # neutral when unavailable
            breakdown["RSI trend alignment"] = "not evaluated (insufficient history) (+5)"
            unevaluated.append("RSI trend alignment")
```

```python
    else:
        pts_rsi = 5   # neutral when unavailable
        breakdown["RSI trend alignment"] = "not evaluated (no price history passed in) (+5)"
        unevaluated.append("RSI trend alignment")
```

6. Squeeze fallback branch (the outer `else`, not the "no squeeze/breakout confirmation right now" one — that is a real reading of zero):

```python
    else:
        breakdown["TTM Squeeze + volume breakout"] = "not evaluated (no price history passed in) (+0)"
        unevaluated.append("TTM Squeeze + volume breakout")
```

7. Candlestick fallback branch (the outer `else`, not "no confirming pattern ..."):

```python
    else:
        breakdown["Candlestick pattern"] = "not evaluated (no price history passed in) (+0)"
        unevaluated.append("Candlestick pattern")
```

8. Directly above the tight-stop comment block (`# Tight-stop penalty: if the stop sits below ...`):

```python
    pts_tight_penalty = None   # v146 I1: stays None when no penalty line is written
```

9. Replace the final `return ConfidenceResult(level=level, label=label, score=score, breakdown=breakdown)` with:

```python
    points = _legacy_points(
        (pts_distance, pts_stop, pts_regime, pts_adx, pts_macd, pts_rsi, pts_squeeze, pts_candle),
        pts_tight_penalty)
    return ConfidenceResult(level=level, label=label, score=score, breakdown=breakdown,
                            points=points, unevaluated=unevaluated)
```

Nothing else in the function changes: no breakdown string, no point value, no level or score arithmetic.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_points.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: `VERDICT: PASS` (`LEGACY_EXPECTED_LEVEL = 4`, `LEGACY_EXPECTED_SCORE = 73` unchanged).

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_quality_inputs.py`
Expected: `VERDICT: PASS`.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s swingbot/core/scanning/confidence.py`
Expected: `_score_confidence_legacy - E (40)` (not higher), `_legacy_points - A (2)`.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/scanning/confidence.py tests/scanning/test_confidence_points.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): legacy confidence scorer stamps numeric points and unevaluated factors"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command prints nothing.

---

### Task V146-3: `v146_001` backfill revision with its parser

**Model:** opus — an Alembic data revision over production rows, whose parser must provably cover every line form the scorer emits.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v146_001_confidence_points.py`
- Create: `tests/db/test_v146_confidence_points_migration.py`

**Interfaces:**
- Consumes: `tests/scanning/test_confidence_points.scenario_matrix() -> list[tuple[str, ConfidenceResult]]` and `_scenario(**over)` (V146-1/V146-2); `ConfidenceResult.points` / `.unevaluated` (V146-1); existing `swingbot.core.db.doc_fields.drop_doc_field(table, name, *, conn=None) -> int`, `TradeRepository().insert(record, conn=...)` / `.get(trade_id, conn=...)`, fixtures `db_conn` and `db_engine_empty` (`tests/db/conftest.py`), `factors.factor_tight_stop`, `factors.FactorContext`.
- Produces: revision `"v146_001"`, `down_revision` = the head at implementation time (`"v144_001"` on 2026-10-10). Module functions: `parse_breakdown(breakdown: dict) -> tuple[dict[str, int], list[str], list[str]]` (points, unevaluated, unparsed keys); `backfill(conn) -> tuple[int, dict[str, collections.Counter]]` (rows stamped, per-key `{"parsed", "skipped", "unparsed"}` counts); `upgrade()` logs one line per key, `v146_001 <key>: parsed=<n> skipped=<n> unparsed=<n>`, plus `v146_001: stamped <n> trade row(s)`, on logger `alembic.runtime.migration`; `downgrade()` drops both doc fields with `drop_doc_field`. Stored trade-doc fields `confidence_points: {factor: int}` and `confidence_unevaluated: [factor, ...]` on every pre-v146 row whose `confidence_breakdown` is an object.

- [ ] **Step 1: Re-check the head and load the schema-change skill**

Invoke the `schema-change` skill (this is a doc-field ADD by data revision; `docs/claude/schema-evolution.md` applies: no read-time upcasting, the parser lives only in the revision).

Run: `python -m alembic heads`
Expected: exactly one head, `v144_001 (head)`. If it is a different id, use that id as `down_revision` below and in the docstring's `Revises:` line.

- [ ] **Step 2: Write the failing tests**

Create `tests/db/test_v146_confidence_points_migration.py`:

```python
"""v146_001: backfill confidence_points / confidence_unevaluated from the
breakdown text, once. The parser is loaded from the revision file itself --
it exists nowhere else, so no reader can ever parse the text again."""
from __future__ import annotations

import importlib.util
import logging
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.scanning import factors
from swingbot.core.scanning.confidence import score_confidence
from tests.scanning.test_confidence_points import _scenario, scenario_matrix

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v146_001_confidence_points.py")
TS = "2026-10-01T10:00:00+00:00"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v146_001_confidence_points", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
MATRIX = scenario_matrix()
BY_LABEL = dict(MATRIX)


# --- the parser against both scorers ----------------------------------

@pytest.mark.parametrize("label,result", MATRIX, ids=[label for label, _ in MATRIX])
def test_parser_reproduces_the_legacy_scorer(label, result):
    points, unevaluated, unparsed = MIG.parse_breakdown(result.breakdown)
    assert points == result.points
    assert unevaluated == result.unevaluated
    assert unparsed == []


def test_parser_reproduces_the_unified_scorer(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(
        _scenario(), regime_trend="bullish", df=None, gap_fragile=True,
        macro_verdict={"status": "opposed", "reason": "disagrees", "trend": "bearish"})
    points, unevaluated, unparsed = MIG.parse_breakdown(result.breakdown)
    assert (points, unevaluated, unparsed) == (result.points, result.unevaluated, [])
    assert "Confirming methods" not in points


@pytest.mark.parametrize("scenario_kw", [
    {"tight_stop": True, "atr_floor_pct": 4.0, "stop_distance_pct": 1.0},
    {"tight_stop": True, "atr_floor_pct": 2.0, "stop_distance_pct": 1.98},   # rounds to 0
])
def test_parser_reads_the_unified_tight_stop_line(scenario_kw):
    result = factors.factor_tight_stop(factors.FactorContext(scenario=_scenario(**scenario_kw)))
    points, _, unparsed = MIG.parse_breakdown({result.name: result.line})
    assert points == {result.name: result.points}
    assert unparsed == []


def test_non_factor_keys_are_skipped_not_unparsed():
    breakdown = {
        "Strategies confirmed (base level)": "3 strategies agree on the target -> base Level 3",
        "Quality score": "73/100 (quality score 73/100 -> no adjustment)",
        "Track record (expectancy)": "50% assumed win rate, 3.0:1 reward:risk -> expectancy +1.00R",
        "Level adjustment": "base Level 3 +1 -> final Level 4 (High)",
        "Confirming methods": "3 independent method(s) -> base Level 5",
    }
    assert MIG.parse_breakdown(breakdown) == ({}, [], [])


def test_an_unparseable_line_is_reported_not_fatal():
    points, unevaluated, unparsed = MIG.parse_breakdown({
        "ADX trend strength": "ADX 31.0 (strong trend) (+15)",
        "Mystery factor": "no integer at the end",
        "Odd value": None,
    })
    assert points == {"ADX trend strength": 15}
    assert unevaluated == []
    assert unparsed == ["Mystery factor", "Odd value"]


# --- the backfill on a real trades table ------------------------------

@pytest.fixture
def trades_conn(db_conn):
    db_conn.execute(sa.text("DELETE FROM trades"))   # rolled back with the fixture
    return db_conn


def _trade(conn, trade_id, **doc):
    TradeRepository().insert({"trade_id": trade_id, "ticker": "AAPL",
                              "strategy": "S/R Confluence", "horizon": "2w",
                              "direction": "bullish", "status": "win",
                              "opened_at": TS, **doc}, conn=conn)


def _row(conn, trade_id):
    return TradeRepository().get(trade_id, conn=conn)


def test_backfill_writes_both_fields_from_the_breakdown(trades_conn):
    result = BY_LABEL["regime unavailable"]
    _trade(trades_conn, "T1", confidence_breakdown=result.breakdown)
    stamped, _counts = MIG.backfill(trades_conn)
    row = _row(trades_conn, "T1")
    assert stamped == 1
    assert row["confidence_points"] == result.points
    assert sorted(row["confidence_unevaluated"]) == sorted(result.unevaluated)


def test_backfill_leaves_rows_without_a_breakdown_or_already_stamped(trades_conn):
    _trade(trades_conn, "T-null", confidence_breakdown=None)
    _trade(trades_conn, "T-strategy")
    _trade(trades_conn, "T-new", confidence_breakdown={"ADX trend strength": "ADX 30 (+15)"},
           confidence_points={"sentinel": 1}, confidence_unevaluated=[])
    stamped, _counts = MIG.backfill(trades_conn)
    assert stamped == 0
    assert "confidence_points" not in _row(trades_conn, "T-null")
    assert "confidence_points" not in _row(trades_conn, "T-strategy")
    assert _row(trades_conn, "T-new")["confidence_points"] == {"sentinel": 1}


def test_backfill_counts_parsed_skipped_and_unparsed_per_key(trades_conn):
    _trade(trades_conn, "T1", confidence_breakdown={
        "Quality score": "73/100 (quality score 73/100 -> no adjustment)",
        "ADX trend strength": "ADX 30 (strong trend) (+15)",
        "Mystery factor": "no integer here",
    })
    _stamped, counts = MIG.backfill(trades_conn)
    assert counts["ADX trend strength"]["parsed"] == 1
    assert counts["Quality score"]["skipped"] == 1
    assert counts["Mystery factor"]["unparsed"] == 1
    assert _row(trades_conn, "T1")["confidence_points"] == {"ADX trend strength": 15}


def test_upgrade_logs_counts_and_downgrade_drops_both_fields(trades_conn, caplog):
    _trade(trades_conn, "T1", confidence_breakdown=BY_LABEL["tight stop"].breakdown)
    with Operations.context(MigrationContext.configure(trades_conn)):
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            MIG.upgrade()
        assert _row(trades_conn, "T1")["confidence_points"]["Tight stop penalty"] == -11
        MIG.downgrade()
    row = _row(trades_conn, "T1")
    assert "confidence_points" not in row
    assert "confidence_unevaluated" not in row
    assert "v146_001 Tight stop penalty: parsed=1 skipped=0 unparsed=0" in caplog.text
    assert "v146_001: stamped 1 trade row(s)" in caplog.text


# --- the revision graph -----------------------------------------------

def test_revision_sits_on_an_existing_revision_and_runs_up_and_down(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert MIG.revision == "v146_001"
    assert script.get_revision(MIG.down_revision) is not None
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, MIG.down_revision)
        upgrade(cfg, "head")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v146_confidence_points_migration.py`
Expected: FAIL at collection — `FileNotFoundError` for `v146_001_confidence_points.py`.

- [ ] **Step 4: Implement the revision**

Create `swingbot/core/db/migrations/versions/v146_001_confidence_points.py`:

```python
"""trades.confidence_points / confidence_unevaluated: backfill from the breakdown text

v146 I1. Every trade logged before v146 carries `confidence_breakdown` as
{factor: "... (+N)"} text only. This revision parses each scored factor's line
once and writes the integers to `confidence_points` and the neutral-fallback
factors to `confidence_unevaluated`. It is the only place that text is ever
parsed (docs/claude/schema-evolution.md: no read-time upcasting). Plans are
not backfilled: they never carried a breakdown.

A line matching neither the trailing "(+N)" / "(-N)" form nor the penalty's
"-> -N quality pts" form is left out of `points` and counted as unparsed;
the per-key parsed / skipped / unparsed counts are logged.

Revision ID: v146_001
Revises: v144_001
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter

import sqlalchemy as sa
from alembic import op

from swingbot.core.db.doc_fields import drop_doc_field

revision = "v146_001"
down_revision = "v144_001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Breakdown keys that are not scored factors, from either scorer.
NON_FACTOR_KEYS = frozenset({
    "Strategies confirmed (base level)", "Quality score", "Track record (expectancy)",
    "Level adjustment", "Confirming methods",
})
_POINTS_RE = re.compile(r"\(([+-]\d+)\)\s*$")
_PENALTY_RE = re.compile(r"->\s*(-?\d+) quality pts\s*$")
_FALLBACK_RE = re.compile(r"^\s*(?:regime unavailable|not evaluated)\b")

_SELECT = sa.text(
    "SELECT id, doc -> 'confidence_breakdown' FROM trades "
    "WHERE jsonb_typeof(doc -> 'confidence_breakdown') = 'object' "
    "AND NOT (doc ? 'confidence_points')")
_UPDATE = sa.text(
    "UPDATE trades SET doc = doc || jsonb_build_object("
    "'confidence_points', CAST(:points AS jsonb), "
    "'confidence_unevaluated', CAST(:unevaluated AS jsonb)) WHERE id = :id")


def _line_points(line) -> int | None:
    if not isinstance(line, str):
        return None
    match = _POINTS_RE.search(line) or _PENALTY_RE.search(line)
    return int(match.group(1)) if match else None


def parse_breakdown(breakdown: dict) -> tuple[dict[str, int], list[str], list[str]]:
    """(points, unevaluated, unparsed) for one stored breakdown."""
    points: dict[str, int] = {}
    unevaluated: list[str] = []
    unparsed: list[str] = []
    for key, line in breakdown.items():
        if key in NON_FACTOR_KEYS:
            continue
        value = _line_points(line)
        if value is None:
            unparsed.append(key)
            continue
        points[key] = value
        if _FALLBACK_RE.match(line):
            unevaluated.append(key)
    return points, unevaluated, unparsed


def _tally(counts: dict[str, Counter], breakdown: dict, points: dict, unparsed: list) -> None:
    for key in breakdown:
        if key in points:
            outcome = "parsed"
        elif key in unparsed:
            outcome = "unparsed"
        else:
            outcome = "skipped"
        counts.setdefault(key, Counter())[outcome] += 1


def backfill(conn) -> tuple[int, dict[str, Counter]]:
    """Stamp every unstamped trade whose breakdown is an object; returns
    (rows stamped, per-key parsed/skipped/unparsed counts)."""
    counts: dict[str, Counter] = {}
    rows = conn.execute(_SELECT).all()
    for row_id, breakdown in rows:
        points, unevaluated, unparsed = parse_breakdown(breakdown)
        _tally(counts, breakdown, points, unparsed)
        conn.execute(_UPDATE, {"id": row_id, "points": json.dumps(points),
                               "unevaluated": json.dumps(unevaluated)})
    return len(rows), counts


def upgrade() -> None:
    stamped, counts = backfill(op.get_bind())
    for key in sorted(counts):
        tally = counts[key]
        log.info("v146_001 %s: parsed=%d skipped=%d unparsed=%d",
                 key, tally["parsed"], tally["skipped"], tally["unparsed"])
    log.info("v146_001: stamped %d trade row(s)", stamped)


def downgrade() -> None:
    drop_doc_field("trades", "confidence_points")
    drop_doc_field("trades", "confidence_unevaluated")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_v146_confidence_points_migration.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/db/test_migrations.py`
Expected: `VERDICT: PASS` (`test_exactly_one_head`, part-prefixed id `v146_001`, schema diff empty — the revision adds no column).

Run: `python scripts/dev/testrun.py file tests/db/test_doc_fields.py`
Expected: `VERDICT: PASS`.

Confirm the parser exists in exactly one place:

Run: `git grep -n -e "def parse_breakdown" -e "_PENALTY_RE = " -- swingbot scripts`
Expected: only `swingbot/core/db/migrations/versions/v146_001_confidence_points.py`.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/db/migrations/versions/v146_001_confidence_points.py`
Expected: no output.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/db/migrations/versions/v146_001_confidence_points.py tests/db/test_v146_confidence_points_migration.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): v146_001 revision backfills numeric confidence points from the breakdown text"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command prints nothing. The revision reaches production only through the normal deploy after merge (the partner's call, `mirror-prod`); V146-14 runs it on a scratch copy of the production rows.

---

### Task V146-4: Trade records and plans carry the points

**Model:** opus — additive kwargs on the legacy C15 `TradeLog.log_trade` and on the live scan's two trade-logging call sites; nothing a user sees may move and no legacy function may score higher.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (new `_confidence_point_fields` just above `_db_record` at line 468; `TradeLog.log_trade` signature at 565-572 and the record literal at 614)
- Modify: `swingbot/core/scanning/scan_run.py` (new `_confidence_point_kwargs` just above `_logged_plan_fields` at line 249; the `trade_log.log_trade(` call at 975-996)
- Modify: `swingbot/core/scanning/short_run.py` (`_log_trade`, lines 172-193)
- Modify: `swingbot/core/planning/plan_types.py` (`TradePlanV2`, after `confidence_level` at line 99)
- Modify: `swingbot/core/planning/params.py` (`_apply_quality`, line 168)
- Modify: `swingbot/core/scanning/analyze.py` (`_build_quality_inputs`, lines 259-306)
- Modify: `tests/scanning/test_engine_v2_plans.py` (the key-set pin in `test_build_quality_inputs_never_duplicates_direction_or_badge_status`, lines 105-107). Not in the ledger row: the pin is an exact `set(out) == {...}` over the dict this task widens, so it has to move with it. No other task edits this file.
- Create: `tests/tracking/test_log_trade_confidence_points.py`

**Interfaces:**
- Consumes: `ConfidenceResult.points: dict[str, int]` and `ConfidenceResult.unevaluated: list[str]` (V146-1); the legacy scorer filling both, and the test helper `tests/scanning/test_confidence_points.scenario_matrix() -> list[tuple[str, ConfidenceResult]]` (V146-2). Existing: `TradeLog.log_trade(...)` / `TradeLog.get_trade_by_id(trade_id)`, `plan_types.plan_to_dict` / `plan_from_dict`, `params._apply_quality(plan, quality_inputs)`, `analyze._build_quality_inputs(item, scenario, df, horizon_key, *, regime=None, rs_percentile=None, breadth=None) -> dict`, `analyze.attach_plan_v2(...)`, `short_run._log_trade(item, nums, explanation, fit, alerts, origin=None)`, `tests/planning/test_plan_engine_model._plan(**kw) -> TradePlanV2`, `tests.store_seed.seed_store`, `tests.helpers.make_ohlcv`.
- Produces: `TradeLog.log_trade(..., confidence_points: dict | None = None, confidence_unevaluated: list | None = None)` (two keyword parameters appended after `origin`). Trade record keys `confidence_points` (`{factor: int}` or `None`) and `confidence_unevaluated` (`[factor, ...]` or `None`), always present on a row written from v146 on; `None` on both means "this trade carried no score" (strategy-path trades, plan-manager fills). `TradePlanV2.confidence_points: dict | None = None`, `TradePlanV2.confidence_unevaluated: list | None = None`, set by `_apply_quality` from the `confidence_points` / `confidence_unevaluated` keys of `quality_inputs`, which `_build_quality_inputs` fills from `item.conf`. Private helpers: `performance._confidence_point_fields(points, unevaluated) -> dict`, `scan_run._confidence_point_kwargs(conf) -> dict`.

**Why `getattr` and not `conf.points`.** Several existing tests drive these paths with a stand-in `conf` that has no `points` attribute (`tests/scanning/test_outlook_run.py:202`, `tests/scanning/test_engine_v2_plans.py:768` and `:819`), and `swingbot/commands/stats.py:104` builds one in production code. A stand-in without the attribute is a trade without factor points, which the record already spells as `None`; reading with a `None` default keeps those callers working unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_log_trade_confidence_points.py`:

```python
"""v146 I1: the numeric confidence points reach the trade record and the plan.

Trade side: TradeLog.log_trade stores `confidence_points` and
`confidence_unevaluated` beside `confidence_breakdown`, from both confluence
callers (scan_run and short_run). Plan side: TradePlanV2 carries the same
two fields, set where confidence_level is set (_build_quality_inputs ->
_apply_quality). Trades and plans that carry no score store None.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import params
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze, scan_run, short_run
from swingbot.core.scanning.confidence import ConfidenceResult
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.scanning.test_confidence_points import scenario_matrix
from tests.store_seed import seed_store

POINTS = {"Target distance quality": 12, "Stop level confluence": 10,
          "Market regime alignment": 7, "Tight stop penalty": -6}
UNEVALUATED = ["Market regime alignment"]


def _conf(**over) -> ConfidenceResult:
    base = dict(level=3, label="Medium", score=60, breakdown={},
                points=dict(POINTS), unevaluated=list(UNEVALUATED))
    base.update(over)
    return ConfidenceResult(**base)


def _open(log, ticker="AAPL", **kw):
    return log.log_trade(ticker=ticker, strategy="Fibonacci", horizon_key="4w",
                         direction="bullish", confidence_level=3, confidence_label="Medium",
                         entry=100.0, stop_loss=98.0, take_profit=106.0, **kw)


# --- the trade record ---------------------------------------------------

def test_log_trade_stores_points_and_unevaluated():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, confidence_points=POINTS,
                                      confidence_unevaluated=UNEVALUATED))
    assert trade["confidence_points"] == POINTS
    assert trade["confidence_unevaluated"] == UNEVALUATED


def test_log_trade_without_a_score_stores_null_under_both_keys():
    """Strategy-path trades and plan-manager fills pass neither argument. The
    keys are present and null: 'this trade carried no score', never a guess."""
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log))
    assert "confidence_points" in trade and trade["confidence_points"] is None
    assert "confidence_unevaluated" in trade and trade["confidence_unevaluated"] is None


def test_an_empty_map_is_stored_as_empty_not_null():
    """A scored trade whose scorer awarded nothing is not an unscored trade."""
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, confidence_points={}, confidence_unevaluated=[]))
    assert trade["confidence_points"] == {}
    assert trade["confidence_unevaluated"] == []


def test_every_legacy_scorer_result_survives_the_store_round_trip():
    """Each rule-table case of the legacy scorer -- fallbacks and the negative
    tight-stop penalty included -- reads back exactly as the scorer produced it."""
    log = TradeLog()
    matrix = scenario_matrix()
    assert matrix
    for index, (label, conf) in enumerate(matrix):
        trade = log.get_trade_by_id(_open(
            log, ticker=f"T{index}", confidence_score=conf.score,
            confidence_breakdown=conf.breakdown, confidence_points=conf.points,
            confidence_unevaluated=conf.unevaluated))
        assert trade["confidence_points"] == conf.points, label
        assert trade["confidence_unevaluated"] == conf.unevaluated, label
        assert trade["confidence_breakdown"] == conf.breakdown, label


def test_point_fields_are_copies_of_the_scorer_objects():
    points, unevaluated = dict(POINTS), list(UNEVALUATED)
    fields = performance._confidence_point_fields(points, unevaluated)
    assert fields == {"confidence_points": POINTS, "confidence_unevaluated": UNEVALUATED}
    assert fields["confidence_points"] is not points
    assert fields["confidence_unevaluated"] is not unevaluated
    assert all(type(value) is int for value in fields["confidence_points"].values())


def test_point_fields_keep_none_and_empty_apart():
    assert performance._confidence_point_fields(None, None) == {
        "confidence_points": None, "confidence_unevaluated": None}
    assert performance._confidence_point_fields({}, []) == {
        "confidence_points": {}, "confidence_unevaluated": []}


# --- the two confluence callers -----------------------------------------

def test_point_kwargs_read_a_real_result():
    assert scan_run._confidence_point_kwargs(_conf()) == {
        "confidence_points": POINTS, "confidence_unevaluated": UNEVALUATED}


@pytest.mark.parametrize("conf", [
    None,
    SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
], ids=["no-conf", "stand-in-without-points"])
def test_point_kwargs_are_null_without_a_scored_result(conf):
    assert scan_run._confidence_point_kwargs(conf) == {
        "confidence_points": None, "confidence_unevaluated": None}


def test_the_scan_loop_passes_the_points_to_log_trade():
    """_sync_run_scan is the main confluence caller; its log_trade call is
    pinned by source because driving the whole scan to a logged trade is a
    slow-tier fixture (tests/scanning/test_engine_v2_plans.py)."""
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "**_confidence_point_kwargs(conf)" in source


def _short_item(conf):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", strategy="RSI", horizon_key="4w", trend="bearish"),
        plan=SimpleNamespace(stop_sources=[], target2_sources=[]),
        plan_v2=_plan(entry_type="stop_entry"), level_map=None, conf=conf, combined_from=[])


@pytest.fixture
def logged(monkeypatch):
    """short_run._log_trade with its collaborators stubbed; yields the kwargs
    log_trade received."""
    seen = {}
    monkeypatch.setattr(short_run.scan_run, "_logged_plan_fields", lambda *a: ([], 2.0))
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2", lambda plan, alerts: None)
    monkeypatch.setattr(short_run.trade_log, "log_trade", lambda **kw: seen.update(kw) or "T1")
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    return seen


NUMS = {"entry": 102.0, "stop_loss": 103.5, "take_profit": 98.0, "target2": None}


def test_short_lane_passes_the_points_to_log_trade(logged):
    assert short_run._log_trade(_short_item(_conf()), NUMS, "why", None, []) == "T1"
    assert logged["confidence_points"] == POINTS
    assert logged["confidence_unevaluated"] == UNEVALUATED


def test_short_lane_logs_null_points_for_a_stand_in_conf(logged):
    stand_in = SimpleNamespace(level=3, label="Medium", score=60, breakdown={})
    short_run._log_trade(_short_item(stand_in), NUMS, "why", None, [], origin="next_session")
    assert logged["confidence_points"] is None
    assert logged["confidence_unevaluated"] is None
    assert logged["origin"] == "next_session"


# --- the plan -----------------------------------------------------------

def test_plan_fields_default_to_none_and_round_trip():
    plan = _plan()
    assert plan.confidence_points is None and plan.confidence_unevaluated is None
    plan.confidence_points, plan.confidence_unevaluated = dict(POINTS), list(UNEVALUATED)
    back = plan_from_dict(plan_to_dict(plan))
    assert back.confidence_points == POINTS
    assert back.confidence_unevaluated == UNEVALUATED


def test_a_pre_v146_plan_record_loads_with_both_fields_none():
    """Plans are not backfilled (no source text): an old record simply has no
    keys, and the dataclass defaults answer for it."""
    record = plan_to_dict(_plan())
    record.pop("confidence_points")
    record.pop("confidence_unevaluated")
    back = plan_from_dict(record)
    assert back.confidence_points is None and back.confidence_unevaluated is None


def _quality_inputs(**over):
    base = dict(regime="bullish", htf_bias="bullish", confluence_count=2, volume_ratio=1.2,
                atr_pct=50.0, trigger_distance_pct=0.3, rs_percentile=None, breadth=None)
    base.update(over)
    return base


def test_apply_quality_sets_the_points_where_it_sets_the_level():
    plan = _plan()
    inputs = _quality_inputs(confidence_level=4, confidence_points=dict(POINTS),
                             confidence_unevaluated=list(UNEVALUATED))
    params._apply_quality(plan, inputs)        # a leaked key would be a TypeError in score_plan
    assert plan.confidence_level == 4
    assert plan.confidence_points == POINTS
    assert plan.confidence_unevaluated == UNEVALUATED
    assert "confidence_points" in inputs, "the caller's dict is not mutated"


def test_apply_quality_without_the_keys_leaves_both_none():
    """The offline decile-audit caller passes no confidence keys at all."""
    plan = _plan()
    params._apply_quality(plan, _quality_inputs())
    assert plan.confidence_level is None
    assert plan.confidence_points is None and plan.confidence_unevaluated is None


def _scan_scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=98.0, take_profit=110.0,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


@pytest.mark.parametrize("item,points,unevaluated", [
    (SimpleNamespace(conf=_conf()), POINTS, UNEVALUATED),
    (SimpleNamespace(conf=SimpleNamespace(level=3)), None, None),
    (SimpleNamespace(), None, None),
], ids=["scored", "stand-in-conf", "no-conf"])
def test_build_quality_inputs_carries_the_points(item, points, unevaluated):
    out = analyze._build_quality_inputs(item, _scan_scenario(), make_ohlcv([100.0] * 60), "4w")
    assert out["confidence_points"] == points
    assert out["confidence_unevaluated"] == unevaluated


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """The account row and data dir attach_plan_v2's plan build reads -- the
    same isolation tests/scanning/test_engine_v2_plans.py applies."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")


def test_attach_plan_v2_stamps_the_live_plan(scan_env):
    item = SimpleNamespace(plan_v2=None, target_confluence=(2, ["EMA21", "Fib"]),
                           conf=_conf(), htf_bias="bullish")
    analyze.attach_plan_v2(
        item, _scan_scenario(), make_ohlcv([100.0] * 60), ticker="TEST", horizon_key="4w",
        level_map=None, regime=SimpleNamespace(trend="bullish"), rs_percentile=50.0,
        breadth=60.0, regime2_state="bull_normal")
    assert item.plan_v2 is not None, "plan_v2 should be built"
    assert item.plan_v2.confidence_level == 3
    assert item.plan_v2.confidence_points == POINTS
    assert item.plan_v2.confidence_unevaluated == UNEVALUATED
```

In `tests/scanning/test_engine_v2_plans.py`, in `test_build_quality_inputs_never_duplicates_direction_or_badge_status`, replace the key-set assertion:

```python
    assert set(out) == {"regime", "htf_bias", "confluence_count", "volume_ratio",
                        "atr_pct", "trigger_distance_pct", "rs_percentile",
                        "breadth", "confidence_level"}
```

with:

```python
    # v146 I1: confidence_points / confidence_unevaluated ride along exactly
    # as confidence_level does -- _apply_quality pops all three before the
    # rest is spread into score_plan().
    assert set(out) == {"regime", "htf_bias", "confluence_count", "volume_ratio",
                        "atr_pct", "trigger_distance_pct", "rs_percentile",
                        "breadth", "confidence_level", "confidence_points",
                        "confidence_unevaluated"}
```

- [ ] **Step 2: Run the tests to verify they fail**

First record the numbers Step 6 compares against:

Run: `python -m radon cc -s swingbot/core/tracking/performance.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/planning/params.py swingbot/core/scanning/analyze.py`
Expected, among the output: `TradeLog.log_trade - C (15)`, `_sync_run_scan - F (100)`, `_log_trade - C (13)`, `_apply_quality - A (2)`, `_build_quality_inputs - B (6)`, `attach_plan_v2 - B (9)`. If a figure differs, write down what you measured: Step 6's rule is "not higher than this run", not these literals.

Run: `python scripts/dev/testrun.py file tests/tracking/test_log_trade_confidence_points.py`
Expected: `VERDICT: FAIL` — `TypeError: log_trade() got an unexpected keyword argument 'confidence_points'`, `AttributeError: module 'swingbot.core.tracking.performance' has no attribute '_confidence_point_fields'`, `AttributeError: ... 'scan_run' has no attribute '_confidence_point_kwargs'`, `AttributeError: 'TradePlanV2' object has no attribute 'confidence_points'`, `KeyError: 'confidence_points'`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: `VERDICT: FAIL` — only `test_build_quality_inputs_never_duplicates_direction_or_badge_status` (the widened key set does not exist yet).

- [ ] **Step 3: Implement the trade side**

In `swingbot/core/tracking/performance.py`, add just above `def _db_record(trade: dict) -> dict:`:

```python
def _confidence_point_fields(points, unevaluated) -> dict:
    """v146 I1: the two record fields written beside `confidence_breakdown`.

    `points` is the integer each scored factor added (ConfidenceResult.points)
    and `unevaluated` the factors whose line was a neutral fallback for a
    missing input. Both are copied, so the stored record never aliases the
    scorer's own objects. None stays None -- a trade that carried no score
    (strategy-path trades, plan-manager fills) -- and is never turned into an
    empty map, which would read as "scored, nothing awarded"."""
    return {
        "confidence_points": (None if points is None
                              else {str(key): int(value) for key, value in points.items()}),
        "confidence_unevaluated": (None if unevaluated is None
                                   else [str(key) for key in unevaluated]),
    }


```

In `TradeLog.log_trade`, replace the last line of the signature:

```python
                  risk_features=None, ledger=None, entry_context=None, origin=None) -> str:
```

with:

```python
                  risk_features=None, ledger=None, entry_context=None, origin=None,
                  confidence_points=None, confidence_unevaluated=None) -> str:
```

and in the `record = {` literal, directly under the `"confidence_breakdown": confidence_breakdown,` line, add:

```python
            # v146 I1: the same factors as numbers, so no reader parses the
            # breakdown text. None on both = this trade carried no score.
            **_confidence_point_fields(confidence_points, confidence_unevaluated),
```

Nothing else in `log_trade` changes: no `if`, no `or`. The unpack adds no branch, which is what keeps the method at its legacy C15.

In `swingbot/core/scanning/scan_run.py`, add just above `def _logged_plan_fields(`:

```python
def _confidence_point_kwargs(conf) -> dict:
    """v146 I1: the two log_trade kwargs carrying the scorer's numeric points.

    Read with a None default: a stand-in `conf` that has no `points` (the
    stats-command placeholder, test doubles) is a trade without factor
    points, which the record spells as None."""
    return {"confidence_points": getattr(conf, "points", None),
            "confidence_unevaluated": getattr(conf, "unevaluated", None)}


```

In `_sync_run_scan`'s `trade_log.log_trade(` call, replace its last argument and closing parenthesis:

```python
                entry_context=plan_v2.entry_context if plan_v2 is not None else None,
            )
```

with:

```python
                entry_context=plan_v2.entry_context if plan_v2 is not None else None,
                **_confidence_point_kwargs(conf),
            )
```

In `swingbot/core/scanning/short_run.py`, replace the last line of `_log_trade`:

```python
        entry_context=plan_v2.entry_context if plan_v2 is not None else None, origin=origin)
```

with:

```python
        entry_context=plan_v2.entry_context if plan_v2 is not None else None, origin=origin,
        **scan_run._confidence_point_kwargs(conf))
```

(`short_run` already reaches `scan_run._logged_plan_fields` and `scan_run._persist_plan_v2` the same way; the outlook lane logs through this same `_log_trade`, so it is covered too.)

`swingbot/core/scanning/strategy_pass.py:130` and `swingbot/core/planning/plan_manager.py:615` are deliberately left alone: they carry no score and now write `null` under both keys through the defaults.

- [ ] **Step 4: Implement the plan side**

In `swingbot/core/planning/plan_types.py`, directly under `confidence_level: int | None = None` in `TradePlanV2`, add:

```python
    # v146 I1: the integer each scored confidence factor added, keyed as the
    # trade's confidence_breakdown is, and the factors whose reading was a
    # neutral fallback for a missing input. Set where confidence_level is
    # set (_apply_quality, from the live scan's item.conf). None for every
    # replayed plan, every caller with no live conf, and every record
    # persisted before v146 -- plans are never backfilled, there is no
    # source text to parse.
    confidence_points: dict | None = None
    confidence_unevaluated: list | None = None
```

In `swingbot/core/planning/params.py`, in `_apply_quality`, directly under `plan.confidence_level = quality_inputs.pop("confidence_level", None)`, add:

```python
    # v146 I1: the same ride-along, for the same reason -- neither is a
    # score_plan() kwarg.
    plan.confidence_points = quality_inputs.pop("confidence_points", None)
    plan.confidence_unevaluated = quality_inputs.pop("confidence_unevaluated", None)
```

In `swingbot/core/scanning/analyze.py`, in `_build_quality_inputs`, add one line directly above `return {`:

```python
    conf = getattr(item, "conf", None)
```

and in the returned dict, directly under the `"confidence_level": item.conf.level if getattr(item, "conf", None) else None,` line (which stays exactly as it is), add:

```python
        # v146 I1: ride along beside confidence_level and are popped with it
        # in _apply_quality. getattr with a None default: a stand-in conf
        # without `points` is a plan without factor points.
        "confidence_points": getattr(conf, "points", None),
        "confidence_unevaluated": getattr(conf, "unevaluated", None),
```

`attach_plan_v2` itself is unchanged (V146-5 edits it next, for `days_to_earnings`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_log_trade_confidence_points.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: `VERDICT: PASS` (the widened key set; the `SimpleNamespace(level=3)` stand-ins at 768 and 819 still build a plan).

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py`
Expected: `VERDICT: PASS` (`test_log_trade_passes_the_origin_through` drives `short_run._log_trade` with a stand-in conf that has no `points`).

Run: `python scripts/dev/testrun.py file tests/tracking/test_trade_metadata.py`
Expected: `VERDICT: PASS`.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: `VERDICT: PASS` (`test_exact_round_trip` walks every dataclass field, the two new ones included).

Confirm the two confluence callers, and only they, pass the points:

Run: `git grep -n -e "_confidence_point_kwargs" -e "confidence_points=" -- swingbot`
Expected: the definition and one use in `swingbot/core/scanning/scan_run.py`, one use in `swingbot/core/scanning/short_run.py`, the `confidence_points=None` parameter in `swingbot/core/tracking/performance.py`; nothing in `strategy_pass.py` or `plan_manager.py`.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s swingbot/core/tracking/performance.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/planning/params.py swingbot/core/scanning/analyze.py`
Expected: every figure recorded in Step 2 is unchanged — `TradeLog.log_trade - C (15)` (not higher), `_sync_run_scan - F (100)` (not higher), `_log_trade - C (13)`, `_apply_quality - A (2)`, `_build_quality_inputs - B (6)`, `attach_plan_v2 - B (9)` — and the two new helpers rank `A`: `_confidence_point_fields - A (5)`, `_confidence_point_kwargs - A (1)`. If `log_trade` or `_sync_run_scan` scores higher, a branch crept into it: move it into the helper before committing.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution add swingbot/core/tracking/performance.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/planning/plan_types.py swingbot/core/planning/params.py swingbot/core/scanning/analyze.py tests/scanning/test_engine_v2_plans.py tests/tracking/test_log_trade_confidence_points.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution commit -m "feat(v146): trade records and plans carry numeric confidence points"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command prints nothing.

---
