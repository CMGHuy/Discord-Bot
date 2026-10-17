# v157 Instrument v2, phase 2: fills and costs. Part 1: contract, fills, costs, the v2 walk (FC1-FC5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (section 2 "Fills and costs", rule 1, "Testing")
**Bump:** bot minor
**Edge:** none (integrity)

> Index, Global Constraints, Where to work, Parallelisation and the task ledger: `2026-10-10-v157-instrument-v2-fills-costs_0-index.md`. Every task here implicitly includes the index's Global Constraints. **Never read this file whole**: pull one task with `grep -n "^### Task FC4" -A 400 docs/superpowers/plans/2026-10-10-v157-instrument-v2-fills-costs_1-contract-fills-walk.md`.

`$R` is the main tree's root, `$WT` = `$R/.claude/worktrees/2026-10-10-v157-instrument-v2-fills-costs`. Never `cd`; every command uses absolute paths or `git -C $WT`.

Worked numbers in the tests below were computed by running the code shown here against today's `main`; a mismatch is a bug in the implementation, not a reason to edit an expected value.

# Phase A: the contract values and the pure fill and cost modules

### Task FC1: v2 fill and cost values in the contract

**Model:** haiku — two constants, one dict entry and a docstring in one file, fully specified below.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/contract.py` (module docstring, two field comments, new `V2_FILLS`/`V2_COSTS`, `_SPECS["v2"]`)
- Modify: `tests/backtesting/instrument/test_contract.py` (module docstring; replace `test_phase_one_v2_stub_carries_v1_fills_and_costs` with three tests)

**Interfaces:**
- Consumes: the existing `FillModel`, `CostModel`, `InstrumentSpec`, `V1_FILLS`, `ZERO_COSTS`, `resolve` (`contract.py:25,34,43,57,58,68`, verified with `git grep -n`).
- Produces (ledger):
  - `V2_FILLS = FillModel(market_entry="next_open", gap_through=True, same_bar="stop_first")`
  - `V2_COSTS = CostModel(commission_per_share=0.0, slippage_bps=5.0, stop_slippage_bps=10.0)`
  - `_SPECS["v2"] = InstrumentSpec("v2", V2_FILLS, V2_COSTS)`, so `resolve("v2")` carries spec section 2's values.
- No field is added to `FillModel`, `CostModel` or `InstrumentSpec` (contract ownership with v158: it appends `InstrumentSpec` fields; `test_phase_one_carries_no_span_fields` stays as it is, v158 updates it).

- [ ] **Step 0: Create the worktree** (this task runs first). Invoke the `worktree-lifecycle` skill, then:

```bash
R=$(git rev-parse --show-toplevel)
WT=$R/.claude/worktrees/2026-10-10-v157-instrument-v2-fills-costs
git -C $R worktree list | grep -F "$WT" || git -C $R worktree add "$WT" -b 2026-10-10-v157-instrument-v2-fills-costs main
git -C $WT log --oneline -1
```

Expected: the worktree exists on branch `2026-10-10-v157-instrument-v2-fills-costs`, at `main`'s HEAD. Name `$WT` in every later dispatch.

- [ ] **Step 1: Write the failing tests.** In `$WT/tests/backtesting/instrument/test_contract.py`, replace the first line (module docstring) with:

```python
"""v136 phases 1-2: the instrument contract (v157 sets v2's fills and costs)."""
```

and replace the whole function `test_phase_one_v2_stub_carries_v1_fills_and_costs` (its docstring says phase 2 rewrites it) with:

```python
def test_v2_carries_spec_section_two_fills_and_costs():
    spec = resolve("v2")
    assert spec.fill_model == FillModel(market_entry="next_open", gap_through=True,
                                        same_bar="stop_first")
    assert spec.cost_model == CostModel(commission_per_share=0.0, slippage_bps=5.0,
                                        stop_slippage_bps=10.0)
    assert spec.fill_model is contract.V2_FILLS
    assert spec.cost_model is contract.V2_COSTS


def test_v1_keeps_its_own_constants_untouched():
    assert resolve("v1").fill_model is contract.V1_FILLS
    assert resolve("v1").cost_model is contract.ZERO_COSTS
    assert contract.V2_FILLS != contract.V1_FILLS
    assert contract.V2_COSTS != contract.ZERO_COSTS


def test_fill_and_cost_models_keep_their_phase_one_fields():
    """v157 adds no field: the three of each carry every spec section 2 rule."""
    assert [f.name for f in dataclasses.fields(FillModel)] == [
        "market_entry", "gap_through", "same_bar"]
    assert [f.name for f in dataclasses.fields(CostModel)] == [
        "commission_per_share", "slippage_bps", "stop_slippage_bps"]
```

Leave every other test in the file exactly as it is (`test_v1_is_todays_behaviour_and_keeps_its_own_plan_path` is the v1 pin; `test_phase_one_carries_no_span_fields` belongs to v158).

- [ ] **Step 2: Run them and watch them fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: 2 failed (`test_v2_carries_spec_section_two_fills_and_costs` on the values, `test_v1_keeps_its_own_constants_untouched` on `AttributeError: ... has no attribute 'V2_FILLS'`), 7 passed.

- [ ] **Step 3: Implement.** Three edits in `$WT/swingbot/core/backtesting/instrument/contract.py`.

(a) In the module docstring, replace the paragraph

```
Phase 1 (v137) ships the fill/cost fields only, and v2's values equal v1's:
the one v2 difference phase 1 delivers is the plan constructor
(``InstrumentSpec.live_constructor``). Phase 2 sets v2's fill and cost values
(spec section 2) and owns the final shape of ``FillModel``/``CostModel``;
phase 3 adds the span, universe and fold fields. v1 is frozen: a change to its
values breaks tests/backtesting/instrument/test_v1_golden.py, which is the point.
```

with

```
Phase 1 (v137) shipped the fill/cost fields and the plan constructor
(``InstrumentSpec.live_constructor``). Phase 2 (v157) sets v2's fill and cost
values from spec section 2 (``V2_FILLS``, ``V2_COSTS``): they are read by
``instrument/fills.py`` and ``instrument/costs.py`` through
``planning/exit_sim_v2.py``, and are frozen at cutover -- a change to them is
a new instrument version. Phase 3 adds the span, universe and fold fields.
v1 is frozen: a change to its values breaks
tests/backtesting/instrument/test_v1_golden.py, which is the point.
```

(b) Two comment-only edits inside the dataclasses: in `FillModel`, `# "signal_close" (v1) | "next_open" (v2, phase 2)` becomes `# "signal_close" (v1) | "next_open" (v2)`; in `CostModel`, the docstring `"""Per-trade costs, converted to R once at booking (phase 2)."""` becomes `"""Per-trade costs, converted to R once at booking (instrument/costs.py)."""`.

(c) Replace

```python
_SPECS = {
    "v1": InstrumentSpec("v1", V1_FILLS, ZERO_COSTS),
    # Phase-1 stub: v1's fills and costs until phase 2 sets spec section 2's values.
    "v2": InstrumentSpec("v2", V1_FILLS, ZERO_COSTS),
}
```

with

```python
# Spec section 2: market entries at the next open, gaps fill at the open in
# both directions, stop first on a bar holding both levels; $0/share, 5 bps on
# entries and target/close exits, 10 bps on stop exits.
V2_FILLS = FillModel(market_entry="next_open", gap_through=True, same_bar="stop_first")
V2_COSTS = CostModel(commission_per_share=0.0, slippage_bps=5.0, stop_slippage_bps=10.0)

_SPECS = {
    "v1": InstrumentSpec("v1", V1_FILLS, ZERO_COSTS),
    "v2": InstrumentSpec("v2", V2_FILLS, V2_COSTS),
}
```

`V1_FILLS`, `ZERO_COSTS`, the dataclasses' fields and `resolve` are not touched. Nothing in `swingbot/` or `scripts/` reads `fill_model`/`cost_model` yet (`git -C $WT grep -n "fill_model\|cost_model" -- swingbot scripts` shows only `contract.py`), so this changes no behaviour until FC5's seam.

- [ ] **Step 4: Run the tests, the v1 golden and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: `9 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `1 passed` (never regenerate the golden).
Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/contract.py`
Expected: no output.

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/instrument/contract.py tests/backtesting/instrument/test_contract.py
git -C $WT commit -m "feat(v157): resolve(v2) carries spec section 2 fills and costs (FC1)"
git -C $R status --short
```

Expected: the commit lands on the branch; `git -C $R status --short` shows nothing new.

---

### Task FC2: `fills.py`: every v2 compare-and-fill

**Model:** sonnet — a new pure module with parity tests against two existing modules; no judgement beyond the rules written out below.

**Files:**
- Create: `swingbot/core/backtesting/instrument/fills.py`
- Create: `tests/backtesting/instrument/test_fills.py`

**Interfaces:**
- Consumes: `FillModel`, `V1_FILLS`, `V2_FILLS` (contract.py; `V2_FILLS` created by FC1). Parity targets, read but never imported by `fills.py`: `plan_manager.gap_stop_fill`/`gap_target_fill` (`swingbot/core/planning/plan_manager.py:39,45`), `lifecycle.trigger_hit`, `fill_price`, `limit_hit`, `limit_fill_price`, `stop_touched`, `at_or_beyond_stop` (`swingbot/core/planning/lifecycle.py:116,127,155,183,191,198`).
- Produces (ledger, exact signatures):
  - `require_supported(fill_model: FillModel) -> None`: `ValueError` unless `market_entry == "next_open"` and `same_bar == "stop_first"`.
  - `gap_stop_fill(bar_open: float, level: float, direction: str) -> float`: `min` bull / `max` bear.
  - `gap_target_fill(bar_open: float, level: float, direction: str) -> float`: `max` bull / `min` bear.
  - `stop_touched(bar_high, bar_low, stop, direction) -> bool`, `target_touched(bar_high, bar_low, target, direction) -> bool`, `at_or_beyond_stop(price, stop, direction) -> bool`.
  - `entry_touched(entry_type: str, direction: str, bar_high: float, bar_low: float, level: float, *, strict: bool = False) -> bool` for `"stop_entry"`/`"limit"`.
  - `entry_fill(fill_model: FillModel, entry_type: str, direction: str, *, bar_open: float, level: float | None = None) -> float` for `"market"`/`"stop_entry"`/`"limit"`.
  - `exit_fill(fill_model: FillModel, kind: str, level: float, bar_open: float, direction: str) -> float`, `kind` `"stop"`/`"target"`.
- Rules (index, "Fill rules under v2"): entries keep today's open-aware rules whatever `gap_through` says (a stop entry fills at the trigger or the worse open, a limit at the limit or the better open; a market entry at the bar's open, refused unless the model says `next_open`). `gap_through` governs exits: True fills a gapped stop or target at the open, False at the level.
- Import rule (Global Constraints): `fills.py` imports nothing from `swingbot` except `.contract`. The last test below enforces it.

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/instrument/test_fills.py`:

```python
"""v157 FC2: instrument/fills.py -- the v2 compare-and-fill rules and their
parity with the live gap helpers and the v1 lifecycle touch/fill rules."""
import ast
import itertools
from pathlib import Path

import pytest

from swingbot.core.backtesting.instrument import fills
from swingbot.core.backtesting.instrument.contract import V1_FILLS, V2_FILLS, FillModel
from swingbot.core.planning import lifecycle, plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2

DIRECTIONS = ("bullish", "bearish")
PRICES = (94.0, 95.0, 96.0, 100.0, 104.0, 105.0, 106.0)
NO_GAP = FillModel(market_entry="next_open", gap_through=False, same_bar="stop_first")


def _plan(direction, *, trigger=100.0, stop=95.0, strict=False):
    if direction == "bearish" and stop < trigger:
        stop = 2 * trigger - stop
    return TradePlanV2(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="2w", direction=direction,
        entry_type="limit", trigger_price=trigger, entry_price=None, expiry_bars=3,
        stop_loss=stop, tp1=110.0 if direction == "bullish" else 90.0, tp1_fraction=0.5,
        tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, status_history=[], limit_strict_fill=strict)


# --- exits: gap-through in both directions ---------------------------------

def test_bullish_stop_gapped_through_fills_at_the_open():
    assert fills.exit_fill(V2_FILLS, "stop", 95.0, 93.0, "bullish") == 93.0


def test_bullish_stop_touched_intrabar_fills_at_the_stop():
    assert fills.exit_fill(V2_FILLS, "stop", 95.0, 98.0, "bullish") == 95.0


def test_bearish_stop_gapped_through_fills_at_the_open():
    assert fills.exit_fill(V2_FILLS, "stop", 105.0, 107.0, "bearish") == 107.0


def test_bullish_target_gapped_through_fills_at_the_better_open():
    assert fills.exit_fill(V2_FILLS, "target", 110.0, 112.0, "bullish") == 112.0


def test_bearish_target_gapped_through_fills_at_the_better_open():
    assert fills.exit_fill(V2_FILLS, "target", 90.0, 88.0, "bearish") == 88.0


def test_target_touched_intrabar_fills_at_the_target():
    assert fills.exit_fill(V2_FILLS, "target", 110.0, 105.0, "bullish") == 110.0


def test_without_gap_through_both_kinds_fill_at_the_level():
    assert fills.exit_fill(NO_GAP, "stop", 95.0, 93.0, "bullish") == 95.0
    assert fills.exit_fill(NO_GAP, "target", 110.0, 112.0, "bullish") == 110.0


def test_unknown_exit_kind_is_refused():
    with pytest.raises(ValueError, match="exit kind"):
        fills.exit_fill(V2_FILLS, "close", 95.0, 93.0, "bullish")


# --- entries ---------------------------------------------------------------

def test_market_entry_fills_at_the_bar_open():
    assert fills.entry_fill(V2_FILLS, "market", "bullish", bar_open=101.25) == 101.25


def test_market_entry_needs_a_next_open_model():
    with pytest.raises(ValueError, match="next_open"):
        fills.entry_fill(V1_FILLS, "market", "bullish", bar_open=101.0)


@pytest.mark.parametrize("direction,bar_open,expected", [
    ("bullish", 99.0, 100.0), ("bullish", 102.0, 102.0),
    ("bearish", 101.0, 100.0), ("bearish", 98.0, 98.0)])
def test_stop_entry_fills_at_the_trigger_or_the_worse_open(direction, bar_open, expected):
    assert fills.entry_fill(V2_FILLS, "stop_entry", direction, bar_open=bar_open,
                            level=100.0) == expected


@pytest.mark.parametrize("direction,bar_open,expected", [
    ("bullish", 101.0, 100.0), ("bullish", 99.5, 99.5),
    ("bearish", 99.0, 100.0), ("bearish", 100.5, 100.5)])
def test_limit_fills_at_the_limit_or_the_better_open(direction, bar_open, expected):
    assert fills.entry_fill(V2_FILLS, "limit", direction, bar_open=bar_open,
                            level=100.0) == expected


def test_resting_entry_without_a_level_is_refused():
    with pytest.raises(ValueError, match="needs its level"):
        fills.entry_fill(V2_FILLS, "limit", "bullish", bar_open=100.0)


def test_unknown_entry_type_is_refused():
    with pytest.raises(ValueError, match="unknown entry_type"):
        fills.entry_fill(V2_FILLS, "moc", "bullish", bar_open=100.0)
    with pytest.raises(ValueError, match="no resting order"):
        fills.entry_touched("market", "bullish", 101.0, 99.0, 100.0)


def test_require_supported_accepts_v2_and_refuses_v1_market_entries():
    fills.require_supported(V2_FILLS)
    fills.require_supported(NO_GAP)
    with pytest.raises(ValueError, match="next_open"):
        fills.require_supported(V1_FILLS)
    with pytest.raises(ValueError, match="stop_first"):
        fills.require_supported(FillModel("next_open", True, "target_first"))


# --- parity with the live gap helpers and the v1 lifecycle rules -----------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_gap_helpers_match_plan_manager(direction):
    for bar_open, level in itertools.product(PRICES, PRICES):
        assert fills.gap_stop_fill(bar_open, level, direction) == \
            plan_manager.gap_stop_fill(bar_open, level, direction)
        assert fills.gap_target_fill(bar_open, level, direction) == \
            plan_manager.gap_target_fill(bar_open, level, direction)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_touches_match_lifecycle(direction):
    plan = _plan(direction)
    for high, low in itertools.product(PRICES, PRICES):
        if low > high:
            continue
        assert fills.entry_touched("stop_entry", direction, high, low, plan.trigger_price) == \
            lifecycle.trigger_hit(plan, high, low)
        assert fills.entry_touched("limit", direction, high, low, plan.trigger_price) == \
            lifecycle.limit_hit(plan, high, low)
        assert fills.stop_touched(high, low, plan.stop_loss, direction) == \
            lifecycle.stop_touched(plan, high, low)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_limit_touch_matches_lifecycle(direction):
    plan = _plan(direction, strict=True)
    for high, low in itertools.product(PRICES, PRICES):
        if low <= high:
            assert fills.entry_touched("limit", direction, high, low, plan.trigger_price,
                                       strict=True) == lifecycle.limit_hit(plan, high, low)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_entry_fills_and_stop_side_match_lifecycle(direction):
    plan = _plan(direction)
    for price in PRICES:
        assert fills.entry_fill(V2_FILLS, "stop_entry", direction, bar_open=price,
                                level=plan.trigger_price) == lifecycle.fill_price(plan, price)
        assert fills.entry_fill(V2_FILLS, "limit", direction, bar_open=price,
                                level=plan.trigger_price) == lifecycle.limit_fill_price(plan, price)
        assert fills.at_or_beyond_stop(price, plan.stop_loss, direction) == \
            lifecycle.at_or_beyond_stop(plan, price)


@pytest.mark.parametrize("direction,high,low,expected", [
    ("bullish", 110.0, 104.0, True), ("bullish", 109.9, 104.0, False),
    ("bearish", 96.0, 90.0, True), ("bearish", 96.0, 90.1, False)])
def test_target_touched_counts_an_exact_touch(direction, high, low, expected):
    target = 110.0 if direction == "bullish" else 90.0
    assert fills.target_touched(high, low, target, direction) is expected


def test_fills_imports_nothing_from_swingbot_but_the_contract():
    src = Path(fills.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert imported <= {"__future__", ".contract"}
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_fills.py`
Expected: collection error, `ImportError: cannot import name 'fills' from 'swingbot.core.backtesting.instrument'`.

- [ ] **Step 3: Implement** `$WT/swingbot/core/backtesting/instrument/fills.py`:

```python
"""v2 fills (v136 spec section 2): every price-vs-level comparison the v2 exit
walk makes, and the price each comparison fills at.

Pure functions of bar prices, a level and a direction ("bullish" | anything
else = bearish, as everywhere in planning). Imports nothing from swingbot but
the contract: ``plan_manager`` imports ``exit_sim`` (a cycle) and
``planning.lifecycle`` takes a whole plan. The two live gap helpers
(``plan_manager.gap_stop_fill``/``gap_target_fill``) and the lifecycle touch
and entry-fill rules are mirrored here one line each, and
tests/backtesting/instrument/test_fills.py pins the parity.

Entries keep today's open-aware rules (a stop entry never fills better than
its trigger, a limit never worse than its limit) whatever ``gap_through``
says; ``gap_through`` governs exits: True fills a stop or target the bar
gapped through at the open, False at the level.
"""
from __future__ import annotations

from .contract import FillModel

STOP, TARGET = "stop", "target"
_ENTRY_TYPES = ("market", "stop_entry", "limit")


def require_supported(fill_model: FillModel) -> None:
    """ValueError unless the v2 walk implements this fill model's rules."""
    if fill_model.market_entry != "next_open" or fill_model.same_bar != "stop_first":
        raise ValueError(
            "the v2 exit walk implements market_entry='next_open' and "
            f"same_bar='stop_first' only; got {fill_model!r}")


def gap_stop_fill(bar_open: float, level: float, direction: str) -> float:
    """A stop the bar reached: at the level, or at the open if it gapped through."""
    return min(bar_open, level) if direction == "bullish" else max(bar_open, level)


def gap_target_fill(bar_open: float, level: float, direction: str) -> float:
    """A target the bar reached: at the level, or at the (better) open past it."""
    return max(bar_open, level) if direction == "bullish" else min(bar_open, level)


def stop_touched(bar_high: float, bar_low: float, stop: float, direction: str) -> bool:
    """The bar traded at or through `stop` (bullish: low <= stop)."""
    return bar_low <= stop if direction == "bullish" else bar_high >= stop


def target_touched(bar_high: float, bar_low: float, target: float, direction: str) -> bool:
    """The bar traded at or through a favourable level (bullish: high >= target)."""
    return bar_high >= target if direction == "bullish" else bar_low <= target


def at_or_beyond_stop(price: float, stop: float, direction: str) -> bool:
    """`price` already sits at or through the stop."""
    return price <= stop if direction == "bullish" else price >= stop


def entry_touched(entry_type: str, direction: str, bar_high: float, bar_low: float,
                  level: float, *, strict: bool = False) -> bool:
    """A resting order traded on this bar. ``stop_entry``: the breakout reached
    the trigger (bullish: high >= level). ``limit``: the pullback reached the
    limit (bullish: low <= level), or traded strictly through it when `strict`
    (v131 limit_strict_fill)."""
    bull = direction == "bullish"
    if entry_type == "stop_entry":
        return bar_high >= level if bull else bar_low <= level
    if entry_type != "limit":
        raise ValueError(f"no resting order for entry_type {entry_type!r}")
    if strict:
        return bar_low < level if bull else bar_high > level
    return bar_low <= level if bull else bar_high >= level


def entry_fill(fill_model: FillModel, entry_type: str, direction: str, *,
               bar_open: float, level: float | None = None) -> float:
    """The entry price on the fill bar. ``market``: the bar's open (only under
    ``market_entry == "next_open"``). ``stop_entry``: the trigger, or the worse
    open past it (bullish: max). ``limit``: the limit, or the better open past
    it (bullish: min)."""
    if entry_type not in _ENTRY_TYPES:
        raise ValueError(f"unknown entry_type {entry_type!r}")
    if entry_type == "market":
        require_supported(fill_model)
        return float(bar_open)
    if level is None:
        raise ValueError(f"a {entry_type} fill needs its level")
    take_max = (entry_type == "stop_entry") == (direction == "bullish")
    return float(max(bar_open, level) if take_max else min(bar_open, level))


def exit_fill(fill_model: FillModel, kind: str, level: float, bar_open: float,
              direction: str) -> float:
    """The exit price of a stop or target this bar reached: at the open when the
    bar gapped through it and the model fills gaps there, else at the level."""
    if kind not in (STOP, TARGET):
        raise ValueError(f"exit kind must be 'stop' or 'target', got {kind!r}")
    if not fill_model.gap_through:
        return float(level)
    if kind == STOP:
        return float(gap_stop_fill(bar_open, level, direction))
    return float(gap_target_fill(bar_open, level, direction))
```

`entry_fill`'s one comparison covers the four cases: `take_max` is True for a bullish stop entry (`max(open, trigger)`, as `lifecycle.fill_price`) and a bearish limit (`max(open, limit)`, as `lifecycle.limit_fill_price`), False for the other two. The parity tests pin all four.

- [ ] **Step 4: Run the tests and check complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_fills.py`
Expected: `34 passed`.
Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/fills.py`
Expected: no output (the largest, `entry_touched`, is A).

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/instrument/fills.py tests/backtesting/instrument/test_fills.py
git -C $WT commit -m "feat(v157): instrument/fills.py -- v2 gap-through compares and fills, parity with live and lifecycle (FC2)"
git -C $R status --short
```

---

### Task FC3: `costs.py`: slippage and commission to R, booked once

**Model:** sonnet — a new pure module whose arithmetic is fully specified; the tests carry worked numbers.

**Files:**
- Create: `swingbot/core/backtesting/instrument/costs.py`
- Create: `tests/backtesting/instrument/test_costs.py`

**Interfaces:**
- Consumes: `CostModel`, `ZERO_COSTS`, `V2_COSTS` (contract.py; `V2_COSTS` created by FC1).
- Produces (ledger, exact signatures):
  - `EXIT_KINDS = ("stop", "target", "close")`
  - `slip(price: float, *, buy: bool, bps: float) -> float`
  - `exit_bps(cost_model: CostModel, kind: str) -> float`: `stop_slippage_bps` for `"stop"`, `slippage_bps` for `"target"`/`"close"`, `ValueError` otherwise.
  - `book(cost_model: CostModel, *, direction: str, entry_price: float, stop_loss: float, legs: list[dict]) -> tuple[float, list[dict]]`. In: legs `{"fraction", "exit_price", "reason", "kind"}` at raw fill prices. Out: `(r_total, [{"fraction", "exit_price", "r", "reason"}])`, `exit_price` still raw.
- Rules (index, "Cost rules under v2"; controller decisions 5 and 6): the entry slips against the trader at `slippage_bps`; each exit at `exit_bps(kind)`; `risk = (slipped entry − stop_loss) * sign` (equal to `|slipped entry − stop|` on the right side of the stop; `ValueError` when it is not positive); leg `r = ((slipped exit − slipped entry) * sign − 2 * commission_per_share) / risk`, rounded to 3 dp per leg; `r_total = round(Σ fraction * unrounded r, 3)`. Nothing here reads `config` or `edge/frictions.py` (v1-only).
- Why `book` refuses an entry at or beyond the stop: the v2 walk never books one (FC4 returns `no_trade` at zero risk; FC5 turns a fill at or beyond the stop into a 0R `entry_gap_scratch` that is not booked), so reaching it is a bug, not a trade.

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/instrument/test_costs.py`:

```python
"""v157 FC3: instrument/costs.py -- slippage and commission to R, booked once."""
import pytest

from swingbot.core.backtesting.instrument import costs
from swingbot.core.backtesting.instrument.contract import V2_COSTS, ZERO_COSTS, CostModel


def _leg(exit_price, kind, fraction=1.0, reason="x"):
    return {"fraction": fraction, "exit_price": exit_price, "reason": reason, "kind": kind}


def test_slip_moves_a_buy_up_and_a_sell_down():
    assert costs.slip(100.0, buy=True, bps=5.0) == pytest.approx(100.05)
    assert costs.slip(100.0, buy=False, bps=10.0) == pytest.approx(99.9)
    assert costs.slip(100.0, buy=True, bps=0.0) == 100.0


def test_stop_exits_pay_the_stop_rate_and_everything_else_the_base_rate():
    assert costs.exit_bps(V2_COSTS, "stop") == 10.0
    assert costs.exit_bps(V2_COSTS, "target") == 5.0
    assert costs.exit_bps(V2_COSTS, "close") == 5.0


def test_unknown_exit_kind_is_refused():
    with pytest.raises(ValueError, match="exit kind"):
        costs.exit_bps(V2_COSTS, "gap")


def test_zero_costs_book_the_gross_price_r():
    r_total, legs = costs.book(ZERO_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(93.0, "stop", reason="stop")])
    assert r_total == -1.4
    assert legs == [{"fraction": 1.0, "exit_price": 93.0, "r": -1.4, "reason": "stop"}]


def test_bullish_stop_loss_pays_entry_and_stop_slippage():
    # entry 100 * 1.0005 = 100.05; exit 95 * 0.999 = 94.905; risk 100.05 - 95 = 5.05
    r_total, legs = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(95.0, "stop")])
    assert r_total == round((94.905 - 100.05) / 5.05, 3) == -1.019
    assert legs[0]["exit_price"] == 95.0                     # raw price kept


def test_bullish_target_pays_the_base_rate_both_sides():
    # exit 110 * 0.9995 = 109.945
    r_total, _ = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                            stop_loss=95.0, legs=[_leg(110.0, "target")])
    assert r_total == round((109.945 - 100.05) / 5.05, 3) == 1.959


def test_bearish_slippage_is_mirrored():
    # short: sells 100 * 0.9995 = 99.95; buys back the 105 stop at 105 * 1.001 = 105.105
    r_total, _ = costs.book(V2_COSTS, direction="bearish", entry_price=100.0,
                            stop_loss=105.0, legs=[_leg(105.0, "stop")])
    assert r_total == round(-(105.105 - 99.95) / (105.0 - 99.95), 3) == -1.021


def test_commission_is_a_round_trip_per_share_in_r():
    model = CostModel(commission_per_share=0.05, slippage_bps=0.0, stop_slippage_bps=0.0)
    r_total, legs = costs.book(model, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(110.0, "target")])
    assert r_total == round((10.0 - 0.10) / 5.0, 3) == 1.98
    assert legs[0]["r"] == 1.98


def test_r_total_sums_unrounded_leg_r_and_rounds_once():
    # risk 3: leg r 0.00333 and 0.02000. Summing the rounded legs gives 0.011;
    # the unrounded sum, rounded once, gives 0.012.
    r_total, legs = costs.book(ZERO_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=97.0,
                               legs=[_leg(100.01, "target", 0.5), _leg(100.06, "close", 0.5)])
    assert [leg["r"] for leg in legs] == [0.003, 0.02]
    assert round(0.5 * 0.003 + 0.5 * 0.02, 3) == 0.011
    assert r_total == 0.012


def test_scale_out_legs_book_each_leg_at_its_own_kind():
    r_total, legs = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0,
                               legs=[_leg(110.0, "target", 0.5, "tp1"),
                                     _leg(104.0, "stop", 0.5, "runner_be")])
    r1 = (110.0 * 0.9995 - 100.05) / 5.05
    r2 = (104.0 * 0.999 - 100.05) / 5.05
    assert [leg["r"] for leg in legs] == [round(r1, 3), round(r2, 3)]
    assert r_total == round(0.5 * r1 + 0.5 * r2, 3)
    assert [leg["reason"] for leg in legs] == ["tp1", "runner_be"]


def test_an_entry_at_or_beyond_the_stop_is_refused():
    with pytest.raises(ValueError, match="at or beyond the stop"):
        costs.book(ZERO_COSTS, direction="bullish", entry_price=95.0, stop_loss=95.0,
                   legs=[_leg(95.0, "stop")])
    with pytest.raises(ValueError, match="at or beyond the stop"):
        costs.book(ZERO_COSTS, direction="bearish", entry_price=106.0, stop_loss=105.0,
                   legs=[_leg(105.0, "stop")])
```

Worked numbers: the bullish stop loss is entry `100 * 1.0005 = 100.05`, exit `95 * 0.999 = 94.905`, risk `100.05 − 95 = 5.05`, `r = −5.145 / 5.05 = −1.0188 → −1.019`. The rounding test is the case the "round once" rule exists for: legs of `0.00333R` and `0.02R` at half each give `0.0117 → 0.012` summed unrounded, but `0.0115 → 0.011` summed from the rounded legs.

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_costs.py`
Expected: collection error, `ImportError: cannot import name 'costs' from 'swingbot.core.backtesting.instrument'`.

- [ ] **Step 3: Implement** `$WT/swingbot/core/backtesting/instrument/costs.py`:

```python
"""v2 costs (v136 spec section 2): slippage and commission, converted to R
once, at booking, with the trade's own risk per share.

The v2 walk records raw legs -- the fill prices fills.py produced -- and hands
them to ``book`` exactly once per trade. Rules (v157 controller decisions 5, 6):

* the entry slips against the trader at ``slippage_bps`` (a bull buys higher);
* an exit of kind ``"stop"`` slips at ``stop_slippage_bps``; kinds
  ``"target"`` and ``"close"`` (timeout, acceptance, stall, a runner stall at
  the open) at ``slippage_bps``;
* risk = |slipped entry - stop_loss|; leg r = ((slipped exit - slipped entry)
  * sign - 2 * commission_per_share) / risk;
* each leg's r is rounded to 3 dp for display; r_total is the rounded sum of
  fraction * UNROUNDED r, so nothing is rounded twice.

Prices in the returned legs stay raw: costs show only in r. The v1 friction
code (``edge/frictions.py``, config SLIPPAGE_BPS/COMMISSION_*) is v1-only and
never read here.
"""
from __future__ import annotations

from .contract import CostModel

EXIT_KINDS = ("stop", "target", "close")
_BPS = 10_000.0


def slip(price: float, *, buy: bool, bps: float) -> float:
    """`price` moved `bps` basis points against the trader: up for a buy."""
    factor = bps / _BPS
    return price * (1.0 + factor) if buy else price * (1.0 - factor)


def exit_bps(cost_model: CostModel, kind: str) -> float:
    """The slippage an exit of `kind` pays."""
    if kind not in EXIT_KINDS:
        raise ValueError(f"exit kind must be one of {EXIT_KINDS}, got {kind!r}")
    return cost_model.stop_slippage_bps if kind == "stop" else cost_model.slippage_bps


def book(cost_model: CostModel, *, direction: str, entry_price: float, stop_loss: float,
         legs: list[dict]) -> tuple[float, list[dict]]:
    """(r_total, booked legs) for one trade's raw legs.

    In: legs ``{"fraction", "exit_price", "reason", "kind"}`` at raw fill
    prices. Out: ``{"fraction", "exit_price", "r", "reason"}`` per leg, the
    exit price still raw, r net of slippage and commission."""
    bull = direction == "bullish"
    sign = 1 if bull else -1
    entry = slip(entry_price, buy=bull, bps=cost_model.slippage_bps)
    risk = (entry - stop_loss) * sign
    if risk <= 0:
        raise ValueError(f"entry {entry_price} is at or beyond the stop {stop_loss}")
    commission = 2.0 * cost_model.commission_per_share
    total, booked = 0.0, []
    for leg in legs:
        exit_px = slip(leg["exit_price"], buy=not bull, bps=exit_bps(cost_model, leg["kind"]))
        r = ((exit_px - entry) * sign - commission) / risk
        total += leg["fraction"] * r
        booked.append({"fraction": leg["fraction"], "exit_price": leg["exit_price"],
                       "r": round(r, 3), "reason": leg["reason"]})
    return round(total, 3), booked
```

- [ ] **Step 4: Run the tests and check complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_costs.py`
Expected: `11 passed`.
Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/costs.py`
Expected: no output.

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/instrument/costs.py tests/backtesting/instrument/test_costs.py
git -C $WT commit -m "feat(v157): instrument/costs.py -- slippage and commission to R, rounded once (FC3)"
git -C $R status --short
```

---

# Phase B: the v2 exit walk and its entries behind the `simulate_exit` seam

### Task FC4: v2 exit walks: gap-through stops and targets, booked through costs

**Model:** opus — re-expresses the shared exit simulator's bar order on new primitives; a silent ordering slip changes every v2 number, and rule 1 forbids touching the v1 walk it mirrors.

**Files:**
- Create: `swingbot/core/planning/exit_sim_v2.py`
- Create: `tests/planning/test_exit_sim_v2_walk.py`

**Interfaces:**
- Consumes:
  - FC2: `fills.stop_touched`, `fills.target_touched`, `fills.exit_fill`. FC3: `costs.book`. FC1: `resolve("v2")`, `ZERO_COSTS`, `FillModel`.
  - Reused unchanged from `swingbot/core/planning/exit_sim.py` (verified with `git grep -n`): `ExitResult` :61, `acceptance_exit` :89, `_tenth_session_reached` :220, `runner_floor` :249, `runner_structure_frame` :46, `_no_trade` :354, `_chandelier_ratchet` :424, `_runner_timeout` :433, `_structure_update` :477, `_is_compression` :557. `_chandelier_ratchet`, `_structure_update` and `_runner_timeout` read their context by attribute name (`entry_price`, `entry_index`, `sign`, `risk`, `plan`, `is_bull`, `close`, `end`), which `_V2Ctx` carries under the same names.
  - `time_exit.PROXY_BASIS`, `TIME_EXIT_REASON` (`swingbot/core/planning/time_exit.py`), `config.STALL_EXIT_ENABLED`, `config.RUNNER_STRUCTURE_EXIT`, `indicators.atr`.
  - Test helpers: `tests/helpers.py:make_ohlcv`, `pin_code_defaults` (`tests/backtesting/test_pullback_dryup_witness.py:18`), `COMPRESSION_SHORT` (`strategy_types.py:26`).
- Produces (ledger):
  - `_V2Ctx`, frozen dataclass, fields in this order: `high, low, close, open_, entry_index, entry_price, plan, is_bull, sign, risk, end, fills, costs, stall` (`fills` is the `FillModel`, `costs` the `CostModel`, `stall` True for the scale-out walk: pre-TP1 stall exit and a runner after TP1).
  - `_booked(ctx, outcome: str, exit_index: int, legs: list[dict], runner_outcome: str | None = None) -> ExitResult`.
  - `walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int, instrument: InstrumentSpec, *, scale_out: bool) -> ExitResult`.
  - Module-private helpers FC5 also calls: `_context(df, entry_index, entry_price, plan, max_holding_days, instrument, scale_out) -> _V2Ctx` and `_leg(fraction, exit_price, reason, kind) -> dict`.
- Bar order (identical to exit_sim's, only the compares and fill prices change): pre-TP1, per bar: stop (the breakeven stop once moved) → TP1 → acceptance close → stall close (scale-out walk only) → breakeven move, effective next bar; timeout at the last walked close. Runner, per bar: a pending progress stall exits at this open → runner stop → TP2 → chandelier ratchet from this close → structure update; timeout clamped to the stop checked. Stops fill through `exit_fill(kind="stop")`, TP1/TP2 through `exit_fill(kind="target")`, every close-priced exit is kind `"close"`.
- What v2 changes against v1, by design: r is price-derived (a gapped stop books worse than −1R, a gapped breakeven stop below 0R); costs are booked once in `_booked`; `ExitResult.entry_price` and every leg's `exit_price` stay raw. Outcome labels follow the event (loss / scratch / win / timeout), never the sign of the net r (controller-accepted).
- Not here: entries, the fill-bar check, hold caps and the `simulate_exit` dispatch (FC5). This task does not edit `exit_sim.py`.

- [ ] **Step 1: Write the failing test**, `$WT/tests/planning/test_exit_sim_v2_walk.py`:

```python
"""v157 FC4: the v2 exit walk -- gap-through stops and targets in both
directions, stop first, trailing stops effective next bar, and every trade's
r booked once through instrument/costs.py.

Most fixtures use FREE (v2 fills, zero costs) so the expected r is the plain
price arithmetic; the cost tests use resolve("v2"). Entry is at bar 0's
price; the walk starts at bar 1.
"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, FillModel, resolve
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.time_exit import PROXY_BASIS, TIME_EXIT_REASON
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
NO_GAP = dataclasses.replace(FREE, fill_model=FillModel("next_open", False, "stop_first"))
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _bear(**kw):
    return _plan(direction="bearish", stop_loss=105.0, tp1=90.0, **kw)


def _walk(bars, plan=None, *, instrument=FREE, scale_out=False, hold=10):
    df = make_ohlcv([ENTRY, *bars])
    return walk_v2(df, 0, 100.0, plan or _plan(), hold, instrument, scale_out=scale_out)


def _leg(res, i=0):
    leg = res.legs[i]
    return leg["exit_price"], leg["r"], leg["reason"]


# --- stops ----------------------------------------------------------------

def test_bullish_stop_gapped_through_fills_at_the_open_worse_than_minus_one_r():
    res = _walk([(93.0, 94.0, 92.0, 93.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("loss", 1, -1.4)
    assert _leg(res) == (93.0, -1.4, "stop")


def test_bullish_stop_touched_intrabar_fills_at_the_stop():
    res = _walk([(98.0, 99.0, 94.0, 96.0)])
    assert (res.outcome, res.r_total) == ("loss", -1.0)
    assert _leg(res) == (95.0, -1.0, "stop")


def test_bearish_stop_gapped_through_fills_at_the_open():
    res = _walk([(107.0, 108.0, 106.0, 107.0)], _bear())
    assert (res.outcome, res.r_total) == ("loss", -1.4)
    assert _leg(res) == (107.0, -1.4, "stop")


def test_without_gap_through_a_gapped_stop_fills_at_the_level():
    res = _walk([(93.0, 94.0, 92.0, 93.0)], instrument=NO_GAP)
    assert _leg(res) == (95.0, -1.0, "stop")


def test_breakeven_stop_gapped_through_is_a_scratch_below_zero():
    # bar 1 reaches the 105 trigger (entry + 0.5 x 10); bar 2 gaps under entry.
    res = _walk([(104.0, 106.0, 103.0, 105.0), (98.0, 99.0, 97.0, 98.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("scratch", 2, -0.4)
    assert _leg(res) == (98.0, -0.4, "breakeven_stop")


def test_breakeven_move_protects_only_the_bars_after_the_trigger_bar():
    # bar 1 reaches the trigger AND trades under entry: the original stop governs it.
    res = _walk([(101.0, 106.0, 99.0, 104.0), FLAT])
    assert res.outcome == "scratch" and res.exit_index == 2


# --- targets --------------------------------------------------------------

def test_bullish_target_gapped_through_fills_at_the_better_open():
    res = _walk([(112.0, 113.0, 111.0, 112.0)])
    assert (res.outcome, res.r_total) == ("win", 2.4)
    assert _leg(res) == (112.0, 2.4, "tp1")


def test_bearish_target_gapped_through_fills_at_the_better_open():
    res = _walk([(88.0, 89.0, 87.0, 88.0)], _bear())
    assert (res.outcome, res.r_total) == ("win", 2.4)


def test_target_touched_intrabar_fills_at_the_target():
    res = _walk([(105.0, 111.0, 104.0, 109.0)])
    assert _leg(res) == (110.0, 2.0, "tp1")


def test_a_bar_holding_both_stop_and_target_is_a_stop_first_loss():
    res = _walk([(100.0, 111.0, 94.0, 105.0)])
    assert (res.outcome, res.r_total) == ("loss", -1.0)


# --- close-priced exits ---------------------------------------------------

def test_timeout_exits_at_the_last_walked_close():
    res = _walk([FLAT, (100.0, 101.0, 99.0, 100.6), FLAT], hold=2)
    assert (res.outcome, res.exit_index) == ("timeout", 2)
    assert _leg(res) == (100.6, 0.12, "timeout")


def test_acceptance_close_exits_after_stop_and_target():
    res = _walk([(99.0, 100.0, 96.5, 96.8)], _plan(acceptance_close_below=97.0))
    assert (res.outcome, res.exit_index) == ("loss", 1)
    assert _leg(res) == (96.8, -0.64, "acceptance_exit")


def test_stall_exit_runs_only_in_the_scale_out_walk(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    bars = [(100.0, 101.0, 99.0, 100.0), (99.0, 100.0, 98.0, 99.0), FLAT]
    plan = _plan(tp1_fraction=0.5, stall_exit_day=1)
    res = _walk(bars, plan, scale_out=True)
    assert (res.outcome, res.exit_index) == ("loss", 2)
    assert _leg(res) == (99.0, -0.2, "stall_exit")
    assert _walk(bars, plan, scale_out=False, hold=3).outcome == "timeout"


def test_compression_single_leg_timeout_keeps_the_tenth_session_label():
    plan = _bear(strategy=COMPRESSION_SHORT)
    res = _walk([FLAT, FLAT], plan, hold=2)
    assert res.legs[0]["reason"] == TIME_EXIT_REASON
    assert res.legs[0]["price_basis"] == PROXY_BASIS


# --- runner ---------------------------------------------------------------

TP1_BAR = (105.0, 111.0, 104.0, 110.0)


def test_runner_floor_gapped_through_fills_at_the_open():
    # floor = 100 + 2/3 x 10 = 106.667; bar 2 opens at 104, under it.
    res = _walk([TP1_BAR, (104.0, 105.0, 103.0, 104.0)], _plan(tp1_fraction=0.5),
                scale_out=True)
    assert (res.outcome, res.runner_outcome, res.exit_index) == ("win", "runner_be", 2)
    assert res.legs[0] == {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
    assert _leg(res, 1) == (104.0, 0.8, "runner_be")
    assert res.r_total == 1.4


def test_tp2_gapped_through_fills_at_the_better_open():
    res = _walk([TP1_BAR, (118.0, 119.0, 117.0, 118.0)], _plan(tp1_fraction=0.5, tp2=115.0),
                scale_out=True)
    assert (res.runner_outcome, res.r_total) == ("runner_tp2", 2.8)
    assert _leg(res, 1) == (118.0, 3.6, "runner_tp2")


def test_trailing_stop_from_a_close_takes_effect_on_the_next_bar():
    # Short tape: ATR falls back to 2% of entry = 2.0; trail mult 1.0.
    # Bar 2 closes 119 -> stop 117, but bar 2's own 107 low is checked against
    # the floor (106.667) only. Bar 3 opens 118 and trades to 116: out at 117.
    res = _walk([TP1_BAR, (110.0, 120.0, 107.0, 119.0), (118.0, 118.5, 116.0, 117.0)],
                _plan(tp1_fraction=0.5), scale_out=True)
    assert (res.runner_outcome, res.exit_index) == ("runner_trail", 3)
    assert _leg(res, 1) == (117.0, 3.4, "runner_trail")


def test_single_leg_walk_takes_the_whole_position_at_tp1():
    res = _walk([TP1_BAR], _plan(tp1_fraction=0.5), scale_out=False)
    assert (res.outcome, res.runner_outcome, len(res.legs)) == ("win", None, 1)


# --- costs, booked once ---------------------------------------------------

def test_v2_costs_book_a_stop_loss_net_of_both_slippages():
    res = _walk([(98.0, 99.0, 94.0, 96.0)], instrument=V2)
    # entry 100.05 (5 bps), stop exit 94.905 (10 bps), risk 5.05
    assert res.r_total == round((94.905 - 100.05) / 5.05, 3) == -1.019
    assert res.entry_price == 100.0 and res.legs[0]["exit_price"] == 95.0


def test_v2_costs_book_each_runner_leg_at_its_own_rate_and_round_once():
    res = _walk([TP1_BAR, (104.0, 105.0, 103.0, 104.0)], _plan(tp1_fraction=0.5),
                instrument=V2, scale_out=True)
    r1 = (110.0 * 0.9995 - 100.05) / 5.05
    r2 = (104.0 * 0.999 - 100.05) / 5.05
    assert [leg["r"] for leg in res.legs] == [round(r1, 3), round(r2, 3)]
    assert res.r_total == round(0.5 * r1 + 0.5 * r2, 3)


def test_outcome_label_follows_the_event_not_the_net_r():
    # A TP1 touch a hair above entry nets below zero after costs: still a win.
    res = _walk([(100.0, 100.1, 99.9, 100.0)], _plan(tp1=100.05), instrument=V2)
    assert res.outcome == "win" and res.r_total < 0


def test_zero_risk_entry_is_no_trade():
    res = _walk([FLAT], _plan(stop_loss=100.0))
    assert (res.outcome, res.legs, res.r_total) == ("no_trade", [], 0.0)


def test_booked_legs_carry_no_kind():
    res = _walk([(98.0, 99.0, 94.0, 96.0)])
    assert set(res.legs[0]) == {"fraction", "exit_price", "r", "reason"}
```

Worked numbers (zero costs, entry 100, stop 95, risk 5): a stop gapped to a 93 open books `(93 − 100) / 5 = −1.4`; the breakeven stop (moved after bar 1 reached `100 + 0.5 × 10 = 105`) gapped to a 98 open books `−0.4` and stays a scratch; TP1 at a 112 open books `2.4`; the runner floor is `100 + 2/3 × 10 = 106.667`, so a 104 open books leg 2 at `0.8` and the trade `0.5 × 2 + 0.5 × 0.8 = 1.4`. The trail test leans on `_safe_atr_value`'s fallback (2% of entry = 2.0 on a tape shorter than the ATR window) with `trail_atr_mult=1.0`: bar 2's 119 close sets the stop to 117 for bar 3 only.

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py`
Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.planning.exit_sim_v2'`.

- [ ] **Step 3: Implement** `$WT/swingbot/core/planning/exit_sim_v2.py`:

```python
"""The v2 instrument's exit simulator (v136 spec section 2, plan v157).

``exit_sim.simulate_exit(..., instrument=spec)`` hands every non-v1 spec here,
so the v1 walk in exit_sim.py is never edited (spec rule 1). This module keeps
exit_sim's bar order and reuses its pure helpers unchanged; what differs is
that every price-vs-level comparison and every fill price comes from
``instrument/fills.py`` (gaps fill at the open, in both directions, stop
first), and every trade's r is booked once through ``instrument/costs.py``.

Legs are recorded raw -- ``{"fraction", "exit_price", "reason", "kind"}``
with ``kind`` one of ``costs.EXIT_KINDS`` -- and ``_booked`` turns them into
the usual ``ExitResult`` with net ``r``. Outcome labels follow the event (a
stop before the breakeven move is a loss, after it a scratch, a TP1 touch a
win) whatever the net r; r itself is always price-derived.
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot import config
from swingbot.core.backtesting.instrument import costs, fills
from swingbot.core.backtesting.instrument.contract import CostModel, FillModel, InstrumentSpec
from .exit_sim import (ExitResult, _chandelier_ratchet, _is_compression, _no_trade,
                       _runner_timeout, _structure_update, _tenth_session_reached,
                       acceptance_exit, runner_floor, runner_structure_frame)
from .plan_types import TradePlanV2
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON


@dataclass(frozen=True)
class _V2Ctx:
    """exit_sim._WalkCtx's fields (the reused helpers read them by name), plus
    the instrument's fill and cost models and whether this is the scale-out
    walk (pre-TP1 stall exit, runner after TP1)."""
    high: object
    low: object
    close: object
    open_: object
    entry_index: int
    entry_price: float
    plan: TradePlanV2
    is_bull: bool
    sign: int
    risk: float
    end: int
    fills: FillModel
    costs: CostModel
    stall: bool


def _context(df, entry_index: int, entry_price: float, plan: TradePlanV2,
             max_holding_days: int, instrument: InstrumentSpec, scale_out: bool) -> _V2Ctx:
    is_bull = plan.direction == "bullish"
    return _V2Ctx(high=df["High"].values, low=df["Low"].values, close=df["Close"].values,
                  open_=df["Open"].values, entry_index=entry_index,
                  entry_price=float(entry_price), plan=plan, is_bull=is_bull,
                  sign=1 if is_bull else -1, risk=abs(entry_price - plan.stop_loss),
                  end=min(entry_index + max_holding_days, len(df) - 1),
                  fills=instrument.fill_model, costs=instrument.cost_model,
                  stall=bool(scale_out and plan.tp1_fraction < 1.0))


def _leg(fraction: float, exit_price: float, reason: str, kind: str) -> dict:
    return {"fraction": fraction, "exit_price": float(exit_price), "reason": reason,
            "kind": kind}


def _booked(ctx, outcome: str, exit_index: int, legs: list[dict],
            runner_outcome: str | None = None) -> ExitResult:
    """The trade's ExitResult, its raw legs booked once through costs.book."""
    r_total, booked = costs.book(ctx.costs, direction=ctx.plan.direction,
                                 entry_price=ctx.entry_price, stop_loss=ctx.plan.stop_loss,
                                 legs=legs)
    for raw, leg in zip(legs, booked):
        if "price_basis" in raw:
            leg["price_basis"] = raw["price_basis"]
    return ExitResult(outcome=outcome, runner_outcome=runner_outcome,
                      entry_index=ctx.entry_index, exit_index=exit_index,
                      entry_price=ctx.entry_price, r_total=r_total, legs=booked)


def _gross_r(ctx, price: float) -> float:
    return (price - ctx.entry_price) * ctx.sign / ctx.risk


def _stall_due(ctx, j: int) -> bool:
    """exit_sim._stall_exit's condition: flag on, past the plan's stall day,
    and still short of +0.5R (gross) at this close."""
    plan = ctx.plan
    if not (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
            and (j - ctx.entry_index) > plan.stall_exit_day):
        return False
    return _gross_r(ctx, float(ctx.close[j])) < 0.5


def _close_exit(ctx, j: int) -> ExitResult | None:
    """A full-position exit at close[j]: acceptance first, then (scale-out
    walk only) the stall exit -- after stop and target, as in v1."""
    close_j = float(ctx.close[j])
    if acceptance_exit(ctx.plan, close_j):
        reason = "acceptance_exit"
    elif ctx.stall and _stall_due(ctx, j):
        reason = "stall_exit"
    else:
        return None
    outcome = "loss" if round(_gross_r(ctx, close_j), 3) < 0 else "scratch"
    return _booked(ctx, outcome, j, [_leg(1.0, close_j, reason, "close")])


def _stop_out(ctx, j: int, cur_stop: float, stop_moved: bool) -> ExitResult:
    price = fills.exit_fill(ctx.fills, "stop", cur_stop, float(ctx.open_[j]),
                            ctx.plan.direction)
    outcome, reason = ("scratch", "breakeven_stop") if stop_moved else ("loss", "stop")
    return _booked(ctx, outcome, j, [_leg(1.0, price, reason, "stop")])


def _timeout(ctx) -> ExitResult:
    """Out at the last walked close. The compression short's single-leg
    timeout keeps v119's tenth-session label and price basis."""
    leg = _leg(1.0, float(ctx.close[ctx.end]), "timeout", "close")
    if (not ctx.stall and _is_compression(ctx.plan)
            and _tenth_session_reached(ctx.plan, ctx.entry_index, ctx.end)):
        leg["reason"], leg["price_basis"] = TIME_EXIT_REASON, PROXY_BASIS
    return _booked(ctx, "timeout", ctx.end, [leg])


def _pre_tp1_v2(ctx) -> ExitResult | int:
    """exit_sim's pre-TP1 bar order (stop, TP1, acceptance, stall, then the
    breakeven move, effective next bar) on fills.py's compares: a terminal
    ExitResult, or the TP1 bar's index."""
    plan, direction, stop_moved = ctx.plan, ctx.plan.direction, False
    be_trigger = ctx.entry_price + ctx.sign * plan.breakeven_trigger_fraction * abs(
        plan.tp1 - ctx.entry_price)
    for j in range(ctx.entry_index + 1, ctx.end + 1):
        cur_stop = ctx.entry_price if stop_moved else plan.stop_loss
        hi, lo = float(ctx.high[j]), float(ctx.low[j])
        if fills.stop_touched(hi, lo, cur_stop, direction):
            return _stop_out(ctx, j, cur_stop, stop_moved)
        if fills.target_touched(hi, lo, plan.tp1, direction):
            return j
        early = _close_exit(ctx, j)
        if early is not None:
            return early
        if not stop_moved and fills.target_touched(hi, lo, be_trigger, direction):
            stop_moved = True
    return _timeout(ctx)


def _runner_bar_v2(ctx, j: int, runner_stop: float, floor: float):
    """Runner stop first, then TP2, each filled through fills.exit_fill:
    (price, index, reason, kind) or None."""
    hi, lo, op = float(ctx.high[j]), float(ctx.low[j]), float(ctx.open_[j])
    direction = ctx.plan.direction
    if fills.stop_touched(hi, lo, runner_stop, direction):
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return fills.exit_fill(ctx.fills, "stop", runner_stop, op, direction), j, reason, "stop"
    tp2 = ctx.plan.tp2
    if tp2 is not None and fills.target_touched(hi, lo, tp2, direction):
        return fills.exit_fill(ctx.fills, "target", tp2, op, direction), j, "runner_tp2", "target"
    return None


def _runner_v2(df, ctx, tp1_index: int):
    """exit_sim._runner_phase on fills.py's compares: (price, index, reason,
    kind) of the post-TP1 leg. The trailing stop set from bar j's close is
    first checked on bar j + 1."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", "close"
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close"
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close"


def walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2,
            max_holding_days: int, instrument: InstrumentSpec, *,
            scale_out: bool) -> ExitResult:
    """The v2 exit walk from a filled entry: bars entry_index + 1 .. entry_index
    + max_holding_days (capped at the data). Single-leg unless `scale_out` and
    the plan keeps a runner (tp1_fraction < 1.0), as exit_sim._walk_for."""
    if abs(entry_price - plan.stop_loss) <= 0:
        return _no_trade(entry_index, entry_price)
    ctx = _context(df, entry_index, entry_price, plan, max_holding_days, instrument, scale_out)
    pre = _pre_tp1_v2(ctx)
    if isinstance(pre, ExitResult):
        return pre
    tp1_fill = fills.exit_fill(ctx.fills, "target", plan.tp1, float(ctx.open_[pre]),
                               plan.direction)
    if not ctx.stall:
        return _booked(ctx, "win", pre, [_leg(1.0, tp1_fill, "tp1", "target")])
    price, exit_index, reason, kind = _runner_v2(df, ctx, pre)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason)
```

Import order matters for cycles: `exit_sim_v2` imports `exit_sim` at module level, so `exit_sim` must never import `exit_sim_v2` at module level (FC5 uses a function-local import). `swingbot/core/backtesting/__init__.py` is empty and `instrument/__init__.py` re-exports nothing, so importing `instrument.fills`/`costs` from `planning` pulls in no backtest module.

- [ ] **Step 4: Run the tests, the older exit tests and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py`
Expected: `23 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/planning/`
Expected: `0 failed` (nothing in `planning/` changed besides the new module; this proves the import graph is clean).
Run: `python -m radon cc -s -n B $WT/swingbot/core/planning/exit_sim_v2.py`
Expected: only `_pre_tp1_v2 - B (8)` and `_runner_v2 - B (8)`; nothing at C or above.

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/planning/exit_sim_v2.py tests/planning/test_exit_sim_v2_walk.py
git -C $WT commit -m "feat(v157): v2 exit walk -- gap-through stops and targets, costs booked once (FC4)"
git -C $R status --short
```

---

**Continued in `2026-10-10-v157-instrument-v2-fills-costs_1b-entries-seam.md`** (Task FC5): this file would pass the 1500-line cap with FC5 in it, and a task is never split or compressed.
