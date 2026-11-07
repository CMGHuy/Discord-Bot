# v219 — Partials tab: runner endings — Part 1: backend (V219-1..V219-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v219 — Partials tab: runner endings](../specs/2026-11-07-v219-partials-runner-endings-design.md)
**Index:** [`2026-11-07-v219-partials-runner-endings_0-index.md`](2026-11-07-v219-partials-runner-endings_0-index.md) — Goal, Architecture, `## Global Constraints`, the `runner_endings` payload contract with its worked block, `## Parallelisation` and the task ledger. Every task below implicitly includes the index's Global Constraints.

**Worktree:** every task runs in `.claude/worktrees/2026-11-07-v219-partials-runner-endings` (branch of the same name). Paths below are relative to that worktree root.

**Partner decisions (2026-11-08) this part implements:**
- The Giveback strip (`counterfactuals.giveback`) uses the **full decidable filter**: manual closes, no-TP2 runners and runners with no TP1→TP2 distance are all out. A `giveback_excluded` count (closed runners minus decidable ones) says how many it dropped.
- `PartialTrade.pathed` itself checks value types (dict stamp, `mfe_r` a finite real number that is not a bool, `ladder` a dict). The ladder therefore also stops reading malformed stamps; for well-formed books its figures are unchanged.
- Path exclusions are counted **first failing**, in the order `runner_r_unavailable` → `manual_close` → `unpathed` → `no_tp2_distance`, so they sum to `n − decidable`.

**Shared test fixture (already in `tests/analytics/test_partials.py`):** `_trade(...)` builds a plan with entry 100, stop 95 (risk 5), a TP1 leg at exactly 2.0R (fraction 0.5), a runner exit at `100 + 5·runner_r`, and `tp2=120.0` by default (so `tp2_r` is 4.0). `_book()` with `MANUAL` is A tp2 (runner 4.0, mfe 4.2), B floor (1.34, mfe 2.6), C trail (3.0, mfe 3.6), D manual (2.5 from `MANUAL`, no path), E open, F trail with no TP2, G active, H stopped before TP1. Hold from TP1 to exit is 2 sessions except A (4).

**Narrow runs only.** `python scripts/dev/testrun.py file <test>`; no task runs the full suite (CI does).

---

# Phase 1 — Primitives

### Task V219-1: Wilson interval helper

**Model:** sonnet — new statistical helper in one module; the behaviour is fixed by the formula and pinned by reference values.

**Files:**
- Create: `swingbot/core/analytics/intervals.py`
- Create: `tests/analytics/test_intervals.py` (joins the `analytics` suite through its `tests/analytics/` path; no `tests/suites.toml` edit)

**Interfaces:**
- Consumes: nothing.
- Produces: `wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None` — the Wilson score interval for `k` successes in `n` trials, as **fractions** clamped to [0, 1]; `None` when `n < 1`. V219-3's `_share` turns it into percentages.

**Background.** Copies of this formula exist only in research scripts (`scripts/backtest/screen_trail_calibration.py:144`, which raises on `n < 1`). `swingbot/` has none, and a `swingbot` module must not import from `scripts/`. The runtime version returns `None` for an empty group instead of raising, because an exception inside `build_report` fails the whole Partials tab. `k` outside `[0, n]` is a caller bug and raises `ValueError`; the V219-3 callers never pass one (every `k` is a count of a sub-list of the denominator's list).

- [ ] **Step 1: Write the failing test**

Create `tests/analytics/test_intervals.py`:

```python
"""v219: the Wilson score interval used for every share on the Partials tab."""
import pytest

from swingbot.core.analytics.intervals import wilson_interval


@pytest.mark.parametrize("k, n, lo, hi", [
    (1, 4, 0.045586, 0.699364),
    (1, 3, 0.061490, 0.792345),
    (1, 2, 0.094529, 0.905471),
    (5, 10, 0.236590, 0.763410),
])
def test_reference_values(k, n, lo, hi):
    got = wilson_interval(k, n)
    assert got == pytest.approx((lo, hi), abs=1e-6)


def test_zero_successes_pins_the_lower_bound_at_zero():
    lo, hi = wilson_interval(0, 3)
    assert lo == 0.0
    assert hi == pytest.approx(0.561506, abs=1e-6)


def test_all_successes_pins_the_upper_bound_at_one():
    lo, hi = wilson_interval(3, 3)
    assert hi == 1.0
    assert lo == pytest.approx(0.438494, abs=1e-6)


@pytest.mark.parametrize("n", [6, 11, 21, 22, 27])
def test_the_ends_are_exact_where_floats_drift(n):
    assert wilson_interval(0, n)[0] == 0.0
    assert wilson_interval(n, n)[1] == 1.0


def test_bounds_stay_inside_zero_and_one_and_bracket_the_rate():
    for n in range(1, 30):
        for k in range(n + 1):
            lo, hi = wilson_interval(k, n)
            assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_a_wider_z_gives_a_wider_interval():
    lo95, hi95 = wilson_interval(5, 10)
    lo99, hi99 = wilson_interval(5, 10, z=2.576)
    assert lo99 < lo95 and hi99 > hi95
    assert (lo99, hi99) == pytest.approx((0.184213, 0.815787), abs=1e-6)


@pytest.mark.parametrize("n", [0, -1])
def test_no_trials_is_none_not_an_error(n):
    assert wilson_interval(0, n) is None


@pytest.mark.parametrize("k, n", [(-1, 3), (4, 3)])
def test_successes_outside_the_trials_are_rejected(k, n):
    with pytest.raises(ValueError):
        wilson_interval(k, n)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_intervals.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.analytics.intervals'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/analytics/intervals.py`:

```python
"""v219: confidence intervals for the shares the admin analytics tabs show.

Pure functions, no I/O. The live book is small, so a share is shown with
its interval rather than alone; nothing here is a gate.
"""
from __future__ import annotations

from math import sqrt


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for `k` successes in `n` trials, as fractions in
    [0, 1] (z = 1.96 is 95%). None when there are no trials, so an empty
    group reads as "no share" instead of failing the report."""
    if n < 1:
        return None
    if not 0 <= k <= n:
        raise ValueError(f"successes {k} outside 0..{n}")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    # The exact ends are pinned: in floats centre - half drifts to ~1e-17 at
    # k == 0 (n = 11, 22, 27) and centre + half to 0.9999999999999999 at k == n.
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/analytics/test_intervals.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`wilson_interval` is complexity 7).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/intervals.py tests/analytics/test_intervals.py
git commit -m "feat(analytics): Wilson score interval helper for tab shares (V219-1)"
```

### Task V219-2: PartialTrade: `tp2_r`, typed `pathed`, `decidable`, `progress`; Giveback strip on the path filter

**Model:** sonnet — normal TDD inside one module: one derived field, three properties and a narrowed population for one existing figure.

**Files:**
- Modify: `swingbot/core/analytics/partials.py` (imports :11-21; constants :23-36; `PartialTrade` :39-75; `partial_trade` :154-169; `_giveback` :238-240; `counterfactuals` :249-262)
- Modify: `tests/analytics/test_partials.py` (`test_giveback_and_visible_exclusions` :122-125, `test_a_stamp_without_ladder_or_mfe_is_path_unavailable_not_a_crash` :190-194; new tests appended)

**Interfaces:**
- Consumes: nothing from earlier tasks (runs in parallel with V219-1).
- Produces (consumed by V219-3 and V219-4):
  - `PartialTrade.tp2_r: float | None = None` — the **last** field, with a default; the plan's TP2 in R on the initial entry/stop basis (`_one_leg_r(view, {"exit_price": plan.tp2})`), `None` when `plan.tp2 is None`.
  - `PartialTrade.pathed -> bool` — now type-checked: `runner_path` is a dict, `runner_path["mfe_r"]` is a finite `int`/`float` that is not a `bool`, `runner_path["ladder"]` is a dict.
  - `PartialTrade.decidable -> bool` — `pathed and r_runner is not None and bucket != "manual" and tp2_r is not None and tp2_r > r_tp1`.
  - `PartialTrade.progress -> float | None` — `(mfe_r − r_tp1) ÷ (tp2_r − r_tp1)` clamped to [0, 1]; `None` unless `decidable`.
  - `GIVEBACK_PROGRESS = 0.5` (module constant; V219-3's `is_giveback` reads it).
  - `counterfactuals(trades)["giveback"]` now lists decidable closed runners only; new key `counterfactuals(trades)["giveback_excluded"]: int` = closed runners − decidable closed runners.

**Background.** `tp2_r` is derived, never stored (`docs/claude/schema-evolution.md` does not apply). `plan.tp2` is set only at plan build (`swingbot/core/planning/builders.py:494`, `tp2=tp2`), so the TP2 on the record is the TP2 in force at TP1. `metrics.r_multiple` derives a leg's R from its `exit_price` when the leg has no `r` (rounded to 2 dp), exactly as it already does for the manual-close leg. `PartialTrade` is built positionally in one place only (`partials.py:165`); no test constructs it, so a defaulted last field breaks nothing.

The manual-close trap: the route prices a manual close from its linked trade (`_manual_exit_prices()`), so such a runner is *measured* (`r_runner` known) while its `runner_path` never saw the exit (`runner_path.exit_r` is `None`) and its `mfe_r` understates the trade. `decidable` therefore filters on `bucket != "manual"`, never on `r_runner is None`.

`counterfactuals` is complexity 11 and must not grow: the strip moves into a new helper `_giveback_strip(closed)` that returns both keys and is splatted in. The ladder keeps its own population (`measured and pathed`); with the typed `pathed` its figures for well-formed books are unchanged (the existing ladder tests pin it).

- [ ] **Step 1: Write the failing tests**

In `tests/analytics/test_partials.py`, replace `test_giveback_and_visible_exclusions` (:122-125) with:

```python
def test_giveback_and_visible_exclusions(report):
    cf = report["counterfactuals"]
    assert cf["giveback"] == pytest.approx([0.2, 1.26, 0.6])     # A, B, C; F has no TP2, D is manual
    assert cf["giveback_excluded"] == 2
    assert cf["path_unavailable"] == 1 and cf["runner_r_unavailable"] == 0
```

Replace `test_a_stamp_without_ladder_or_mfe_is_path_unavailable_not_a_crash` (:190-194) with:

```python
def test_a_stamp_without_ladder_or_mfe_is_path_unavailable_not_a_crash():
    plan = _trade("S", reason="tp1_runner_tp2", runner_r=4.0, path={"source": "live"})
    cf = pa.counterfactuals([pa.partial_trade(plan)])
    assert cf["giveback"] == [] and cf["path_unavailable"] == 1
    assert cf["giveback_excluded"] == 1
    assert [row["n"] for row in cf["ladder"]] == [0] * 5
```

Append at the end of the file:

```python
# -- v219: tp2_r, typed pathed, decidable, progress --------------------------

def _one(plan, manual_exits=None):
    return pa.partial_trade(plan, manual_exits)


def test_tp2_r_is_the_plans_tp2_on_the_initial_risk_basis():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0)).tp2_r == 4.0
    assert _one(_trade("S", reason="tp1_runner_tp2", runner_r=4.0, direction="bearish",
                       tp2=80.0)).tp2_r == 4.0
    assert _one(_trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None)).tp2_r is None


def test_a_well_formed_stamp_is_pathed():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))).pathed
    whole = {**_path(4.0, 4.0), "mfe_r": 4}                     # an int is a real number
    assert _one(_trade("I", reason="tp1_runner_tp2", runner_r=4.0, path=whole)).pathed


@pytest.mark.parametrize("stamp", [
    None,
    {},
    "garbage",
    ["mfe_r", "ladder"],
    {"mfe_r": 3.1},
    {"ladder": {}},
    {"mfe_r": None, "ladder": {}},
    {"mfe_r": "3.1", "ladder": {}},
    {"mfe_r": True, "ladder": {}},
    {"mfe_r": float("nan"), "ladder": {}},
    {"mfe_r": float("inf"), "ladder": {}},
    {"mfe_r": 3.1, "ladder": None},
    {"mfe_r": 3.1, "ladder": ["2026-10-06"]},
])
def test_a_malformed_stamp_is_unpathed_and_never_raises(stamp):
    trade = _one(_trade("X", reason="tp1_runner_trail", runner_r=3.0, path=stamp))
    assert trade.pathed is False and trade.decidable is False and trade.progress is None
    cf = pa.counterfactuals([trade])
    assert cf["giveback"] == [] and cf["giveback_excluded"] == 1


def test_decidable_needs_every_condition():
    assert _one(_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))).decidable
    unpriced = _trade("N", reason="tp1_runner_trail", path=_path(3.0, 3.0))
    flat = _trade("Q", reason="tp1_runner_trail", runner_r=3.0, tp2=110.0, path=_path(3.0, 3.0))
    below = _trade("R", reason="tp1_runner_trail", runner_r=3.0, tp2=105.0, path=_path(3.0, 3.0))
    no_tp2 = _trade("F", reason="tp1_runner_trail", runner_r=2.4, tp2=None, path=_path(2.8, 2.5))
    assert not _one(unpriced).decidable                           # runner R unknown
    assert _one(flat).tp2_r == 2.0 and not _one(flat).decidable   # tp2_r == r_tp1: no distance
    assert not _one(below).decidable                              # tp2_r < r_tp1
    assert not _one(no_tp2).decidable


def test_a_priced_manual_close_with_a_stamp_is_still_not_decidable():
    plan = _trade("M", reason="manual", path=_path(3.0, 2.5))
    trade = _one(plan, {"M": 107.5})                              # priced from its trade: 1.5R
    assert trade.bucket == "manual" and trade.r_runner == 1.5 and trade.pathed
    assert trade.decidable is False and trade.progress is None
    cf = pa.counterfactuals([trade])
    assert cf["giveback"] == [] and cf["giveback_excluded"] == 1


@pytest.mark.parametrize("mfe, expected", [
    (4.2, 1.0),      # past TP2: clamped at 1
    (4.0, 1.0),
    (3.0, 0.5),      # exactly halfway
    (2.0, 0.0),      # at TP1
    (1.5, 0.0),      # below TP1 (a hand-built stamp): clamped at 0
])
def test_progress_to_tp2_is_clamped(mfe, expected):
    trade = _one(_trade("P", reason="tp1_runner_trail", runner_r=2.0, path=_path(mfe, 2.0)))
    assert trade.progress == pytest.approx(expected)
    assert 0.0 <= trade.progress <= 1.0


def test_progress_is_none_unless_decidable():
    assert _one(_trade("N", reason="tp1_runner_trail", path=_path(3.0, 3.0))).progress is None


def test_the_giveback_threshold_is_half_way():
    assert pa.GIVEBACK_PROGRESS == 0.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: FAIL — `AttributeError: 'PartialTrade' object has no attribute 'tp2_r'` (and `decidable`, `progress`, `GIVEBACK_PROGRESS`), `KeyError: 'giveback_excluded'`, the giveback list still holding F's `0.4`, and several malformed-stamp cases raising or reading as pathed.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/analytics/partials.py`:

3a. Imports (:13-14): add `import math` above `from dataclasses import dataclass`:

```python
import math
from dataclasses import dataclass
from statistics import mean
```

3b. Constants: below `SPLIT_FRACTIONS = (0.33, 0.5, 0.67)` (:24) add:

```python
#: v219: a runner that got this far from TP1 to TP2 and then closed below
#: TP1 gave the move back (the Giveback ending).
GIVEBACK_PROGRESS = 0.5
```

3c. Above `@dataclass(frozen=True)` (:39) add the value check:

```python
def _is_real(value) -> bool:
    """A finite int/float; a bool is not one (JSON `true` is an int in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
```

3d. In `PartialTrade`, add the field after `hold_entry_exit: int | None` (:54):

```python
    hold_entry_exit: int | None
    tp2_r: float | None = None  # v219: plan TP2 in R, initial entry/stop basis; None without a TP2
```

Replace the `pathed` property (:60-63) with:

```python
    @property
    def pathed(self) -> bool:
        """A runner_path stamp carrying the fields the ladder and giveback read,
        with the types they read: a malformed stamp is unpathed, never a crash."""
        path = self.runner_path
        return (isinstance(path, dict) and _is_real(path.get("mfe_r"))
                and isinstance(path.get("ladder"), dict))
```

After the `delta_r` property (:70-75) add:

```python
    @property
    def decidable(self) -> bool:
        """v219 path filter: a runner whose path figures can be trusted. A manual
        close is out by bucket (its stamp never saw the exit), not by r_runner."""
        return (self.pathed and self.r_runner is not None and self.bucket != "manual"
                and self.tp2_r is not None and self.tp2_r > self.r_tp1)

    @property
    def progress(self) -> float | None:
        """How far the runner got from TP1 towards TP2, clamped to [0, 1]."""
        if not self.decidable:
            return None
        raw = (self.runner_path["mfe_r"] - self.r_tp1) / (self.tp2_r - self.r_tp1)
        return min(1.0, max(0.0, raw))
```

3e. Above `partial_trade` (:154) add:

```python
def _tp2_r(plan, view: dict) -> float | None:
    """The plan's TP2 in R on the initial entry/stop basis; None without a TP2."""
    return None if plan.tp2 is None else _one_leg_r(view, {"exit_price": plan.tp2})
```

and extend the `PartialTrade(...)` call in `partial_trade` (:165-169) with the new last argument:

```python
    return PartialTrade(
        plan.plan_id, plan.strategy, plan.horizon_key, plan.direction,
        tp1.isoformat()[:7] if tp1 else "unknown", float(plan.tp1_fraction), r_tp1,
        r_runner, blended, outcome_bucket(plan), plan.runner_path,
        _span(fill, tp1), _span(tp1, exit_), _span(fill, exit_), _tp2_r(plan, view))
```

3f. Replace `_giveback` (:238-240) with `_giveback` plus the strip helper:

```python
def _giveback(runners: list[PartialTrade]) -> list[float]:
    """MFE R minus banked runner R, per runner (unclamped). The Runner endings
    "Gave back" column uses the same formula."""
    return [round(t.runner_path["mfe_r"] - t.r_runner, 4) for t in runners]


def _giveback_strip(closed: list[PartialTrade]) -> dict:
    """The Giveback strip over the v219 path filter (manual, no-TP2 and
    no-distance runners out), with the count it dropped."""
    decidable = [t for t in closed if t.decidable]
    return {"giveback": _giveback(decidable), "giveback_excluded": len(closed) - len(decidable)}
```

3g. In `counterfactuals` (:249-262) replace the line `"giveback": _giveback(pathed),` with `**_giveback_strip(closed),`, and update the docstring:

```python
def counterfactuals(trades: list[PartialTrade]) -> dict:
    """The four what-ifs, over closed runners with a known runner R; the
    ladder further needs a stamped runner_path, the giveback strip the v219
    path filter (`PartialTrade.decidable`)."""
    closed = [t for t in trades if t.closed]
    measured = [t for t in closed if t.measured]
    pathed = [t for t in measured if t.pathed]
    return {
        "actual_exp_r": _mean(t.blended_r for t in measured),
        "all_out_exp_r": _mean(t.r_tp1 for t in measured),
        **_giveback_strip(closed),
        "ladder": [_ladder_row(pathed, level) for level in LADDER_R],
        "split": [_split_row(measured, fraction) for fraction in SPLIT_FRACTIONS],
        **_exclusions(closed),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: PASS, `0 failed`. The untouched ladder, split, KPI and outcome tests still pass: the typed `pathed` changes nothing for `_book()`, and `outcomes` stays until V219-4.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `counterfactuals` stays at or below 11, `partial_trade` at 9, the new properties and helpers are all under 10.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/partials.py tests/analytics/test_partials.py
git commit -m "feat(analytics): PartialTrade tp2_r, typed pathed, decidable and progress; giveback strip on the path filter (V219-2)"
```

# Phase 2 — Runner endings

### Task V219-3: Ending rows and path exclusions

**Model:** sonnet — new metric builders in one module over the population V219-2 defined; every figure is pinned by the index's worked block.

**Files:**
- Modify: `swingbot/core/analytics/partials.py` (imports :18-21; constants after `GIVEBACK_PROGRESS`; new section `# -- runner endings (v219)` after `counterfactuals`)
- Modify: `tests/analytics/test_partials.py` (new tests appended)

**Interfaces:**
- Consumes: `wilson_interval(k, n, z=1.96) -> tuple[float, float] | None` (V219-1, fractions); `PartialTrade.tp2_r`, `.pathed`, `.decidable`, `.progress`, `GIVEBACK_PROGRESS` (V219-2); existing `_rate`, `_mean`, `_median`, `THIN_N`, `PartialTrade.delta_r`.
- Produces (consumed by V219-4):
  - `ENDING_ROWS = ("tp2", "trail", "floor", "other")`
  - `_section(trades: list[PartialTrade]) -> list[PartialTrade]` — closed runners of plans with a TP2 (`closed and bucket != "no_tp2"`), in input order.
  - `ending_of(t: PartialTrade) -> str` — `tp2`→`tp2`, `trail`→`trail`, `floor`→`floor`, every other bucket → `other`.
  - `is_giveback(t: PartialTrade) -> bool` — `decidable and progress >= GIVEBACK_PROGRESS and r_runner < r_tp1`.
  - `_share(k: int, n: int) -> dict` — `{"share", "lo", "hi"}`, percentages 1 dp, all `None` when `n == 0`.
  - `ending_rows(runners: list[PartialTrade]) -> list[dict]` — five Rows (`tp2`, `trail`, `floor`, `other`, `giveback`) in the index's Row shape; `runners` is a `_section` list.
  - `path_exclusions(runners: list[PartialTrade]) -> dict` — `{"runner_r_unavailable", "manual_close", "unpathed", "no_tp2_distance"}`, first failing in that order; sums to `len(runners) − decidable`.

**Background.** The Row shape is fixed by the index's payload contract:

```
Share = {"ending", "n", "denominator", "share", "lo", "hi", "thin"}
Row   = Share + {"r_n", "avg_r", "median_r", "total_r", "vs_all_out",
                 "path_n", "best_r", "progress", "gave_back", "sessions"}
```

- The four ending rows share the denominator `len(runners)`, so their `n` sum to it and their shares to 100% (± rounding). The Giveback row's denominator is the decidable runners and it is not part of that total.
- R columns (`avg_r`, `median_r`, `total_r`, `vs_all_out`, `sessions`) read only runners with a known `r_runner`; `r_n` counts them. A runner with no runner R counts in `n` and Share only.
- Path columns (`best_r`, `progress`, `gave_back`) read only decidable runners; `path_n` counts them. `progress` is a percentage, 1 dp.
- `total_r` is `round(sum((1 − fraction)·r_runner), 4)` (what the row added to the book in R); `vs_all_out` is mean `delta_r`; `gave_back` is mean `mfe_r − r_runner`, the strip's formula; `sessions` is the median `hold_tp1_exit`.
- `thin` is `n < THIN_N` (10) on every row; thin is marked, never hidden.
- `path_exclusions` walks `_PATH_CHECKS`, a table of `(name, fails)` pairs that is the exact negation of `decidable`, so the counts are first-failing and sum to `n − decidable` by construction. Table-driven, so no function grows past complexity 15.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_partials.py`:

```python
# -- v219: runner endings -- rows and path exclusions --------------------------

def _runners(plans, manual_exits=MANUAL):
    trades = [t for plan in plans if (t := pa.partial_trade(plan, manual_exits)) is not None]
    return pa._section(trades)


def _rows(plans, manual_exits=MANUAL):
    return {row["ending"]: row for row in pa.ending_rows(_runners(plans, manual_exits))}


def test_the_section_is_closed_runners_with_a_tp2():
    assert [t.plan_id for t in _runners(_book())] == ["A", "B", "C", "D"]  # E open, F no TP2


@pytest.mark.parametrize("reason, ending", [
    ("tp1_runner_tp2", "tp2"), ("tp1_runner_trail", "trail"), ("tp1_runner_be", "floor"),
    ("tp1_runner_progress_stall", "other"), ("time_exit", "other"), ("manual", "other"),
    ("manual_bulk", "other"), ("acceptance", "other"),
])
def test_every_close_reason_has_one_ending(reason, ending):
    trade = pa.partial_trade(_trade("X", reason=reason, runner_r=1.0))
    assert pa.ending_of(trade) == ending


def test_share_carries_a_wilson_interval_in_percent():
    assert pa._share(1, 4) == {"share": 25.0, "lo": 4.6, "hi": 69.9}
    assert pa._share(0, 3) == {"share": 0.0, "lo": 0.0, "hi": 56.2}
    assert pa._share(0, 0) == {"share": None, "lo": None, "hi": None}


def test_ending_rows_on_the_book():
    rows = _rows(_book())
    assert list(rows) == ["tp2", "trail", "floor", "other", "giveback"]
    assert rows["tp2"] == {
        "ending": "tp2", "n": 1, "denominator": 4, "share": 25.0, "lo": 4.6, "hi": 69.9,
        "thin": True, "r_n": 1, "avg_r": 4.0, "median_r": 4.0, "total_r": 2.0,
        "vs_all_out": 1.0, "path_n": 1, "best_r": 4.2, "progress": 100.0, "gave_back": 0.2,
        "sessions": 4.0}
    cols = ("n", "denominator", "share", "r_n", "avg_r", "median_r", "total_r", "vs_all_out",
            "path_n", "best_r", "progress", "gave_back", "sessions")
    pick = lambda row: tuple(row[c] for c in cols)
    assert pick(rows["trail"]) == (1, 4, 25.0, 1, 3.0, 3.0, 1.5, 0.5, 1, 3.6, 80.0, 0.6, 2.0)
    assert pick(rows["floor"]) == (1, 4, 25.0, 1, 1.34, 1.34, 0.67, -0.33, 1, 2.6, 30.0, 1.26, 2.0)
    assert pick(rows["other"]) == (1, 4, 25.0, 1, 2.5, 2.5, 1.25, 0.25, 0, None, None, None, 2.0)
    assert pick(rows["giveback"]) == (0, 3, 0.0, 0, None, None, None, None, 0, None, None, None, None)
    assert (rows["giveback"]["lo"], rows["giveback"]["hi"]) == (0.0, 56.2)


def test_the_four_ending_rows_make_the_whole_section():
    book = [*_book(), _trade("S1", reason="tp1_runner_progress_stall", runner_r=1.5),
            _trade("T1", reason="time_exit", runner_r=0.8)]
    rows = pa.ending_rows(_runners(book))
    endings = [row for row in rows if row["ending"] in pa.ENDING_ROWS]
    assert sum(row["n"] for row in endings) == 6 == endings[0]["denominator"]
    assert sum(row["share"] for row in endings) == pytest.approx(100.0, abs=0.2)
    assert {row["ending"]: row["n"] for row in endings} == {"tp2": 1, "trail": 1, "floor": 1, "other": 3}


def _giveback_case(plan_id, *, reason="tp1_runner_trail", runner_r, mfe):
    return _trade(plan_id, reason=reason, runner_r=runner_r, path=_path(mfe, 2.5))


@pytest.mark.parametrize("runner_r, mfe, expected", [
    (1.98, 3.0, True),      # exactly halfway to TP2, closed just below TP1
    (2.0, 3.0, False),      # closed exactly at TP1: not a giveback
    (1.0, 2.98, False),     # 49% of the way: not far enough
    (1.0, 4.2, True),       # past TP2 (progress clamped to 1), closed well below TP1
])
def test_giveback_definition(runner_r, mfe, expected):
    trade = pa.partial_trade(_giveback_case("G", runner_r=runner_r, mfe=mfe))
    assert pa.is_giveback(trade) is expected


def test_giveback_spans_endings_and_has_its_own_denominator():
    book = [*_book(),
            _giveback_case("G1", runner_r=1.98, mfe=3.0),                        # trail
            _giveback_case("G2", reason="tp1_runner_be", runner_r=1.34, mfe=3.2),  # floor
            _trade("M1", reason="manual", path=_path(3.5, 3.0))]                 # priced below TP1
    rows = _rows(book, {**MANUAL, "M1": 105.0})
    give = rows["giveback"]
    assert (give["n"], give["denominator"]) == (2, 5)     # A, B, C, G1, G2 decidable; D, M1 manual
    assert (give["share"], give["lo"], give["hi"]) == (40.0, 11.8, 76.9)
    assert give["r_n"] == give["path_n"] == 2
    assert rows["trail"]["n"] == 2 and rows["floor"]["n"] == 2 and rows["other"]["n"] == 2
    assert rows["tp2"]["denominator"] == 7


def test_a_runner_without_runner_r_counts_in_n_and_share_only():
    rows = _rows([_trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0)),
                  _trade("U", reason="tp1_runner_trail", path=_path(3.0, 3.0))], manual_exits={})
    trail = rows["trail"]
    assert (trail["n"], trail["share"], trail["r_n"], trail["path_n"]) == (1, 50.0, 0, 0)
    assert trail["avg_r"] is None and trail["total_r"] is None
    assert trail["vs_all_out"] is None and trail["sessions"] is None


def test_a_row_of_ten_is_not_thin_and_an_empty_one_is():
    plans = [_trade(f"T{i}", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))
             for i in range(10)]
    rows = _rows(plans)
    assert (rows["tp2"]["n"], rows["tp2"]["thin"]) == (10, False)
    assert (rows["trail"]["n"], rows["trail"]["thin"]) == (0, True)


def test_an_empty_section_is_measured_zeros_and_nones():
    rows = pa.ending_rows([])
    assert [row["ending"] for row in rows] == ["tp2", "trail", "floor", "other", "giveback"]
    for row in rows:
        assert (row["n"], row["denominator"], row["r_n"], row["path_n"], row["thin"]) == (0, 0, 0, 0, True)
        assert all(row[key] is None for key in ("share", "lo", "hi", "avg_r", "median_r",
                                                "total_r", "vs_all_out", "best_r", "progress",
                                                "gave_back", "sessions"))
    assert pa.path_exclusions([]) == {"runner_r_unavailable": 0, "manual_close": 0,
                                      "unpathed": 0, "no_tp2_distance": 0}


def test_path_exclusions_on_the_book():
    assert pa.path_exclusions(_runners(_book())) == {
        "runner_r_unavailable": 0, "manual_close": 1, "unpathed": 0, "no_tp2_distance": 0}


def test_path_exclusions_count_the_first_failing_reason():
    plans = [
        _trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0)),   # decidable
        _trade("M0", reason="manual", path=_path(3.0, 3.0)),                        # no price
        _trade("M1", reason="manual", path=_path(3.0, 3.0)),                        # priced
        _trade("U", reason="tp1_runner_trail", runner_r=3.0),                       # no stamp
        _trade("Q", reason="tp1_runner_trail", runner_r=3.0, tp2=110.0, path=_path(3.0, 3.0)),
        _trade("W", reason="tp1_runner_trail", runner_r=3.0, tp2=105.0,
               path={"mfe_r": "x", "ladder": {}}),                                  # both: unpathed first
    ]
    runners = _runners(plans, {"M1": 107.5})
    counts = pa.path_exclusions(runners)
    assert counts == {"runner_r_unavailable": 1, "manual_close": 1, "unpathed": 2,
                      "no_tp2_distance": 1}
    assert sum(counts.values()) == len(runners) - sum(t.decidable for t in runners)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.analytics.partials' has no attribute '_section'` (and `ending_of`, `_share`, `ending_rows`, `is_giveback`, `path_exclusions`, `ENDING_ROWS`). The V219-2 tests still pass.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/analytics/partials.py`:

3a. Imports: below `from swingbot.core.analytics import metrics as m` (:18) add:

```python
from swingbot.core.analytics.intervals import wilson_interval
```

3b. Constants: below `GIVEBACK_PROGRESS = 0.5` (added by V219-2) add:

```python
#: v219 Runner endings: the four scorecard endings, which sum to the section.
ENDING_ROWS = ("tp2", "trail", "floor", "other")
_ENDING_OF_BUCKET = {"tp2": "tp2", "trail": "trail", "floor": "floor"}
```

3c. After `counterfactuals` (and before `_quantiles`), add the new section:

```python
# -- runner endings (v219) -------------------------------------------------------

#: The path filter's conditions, in counting order. Each is the negation of one
#: clause of `PartialTrade.decidable`, so first-failing counts sum to n - decidable.
_PATH_CHECKS = (
    ("runner_r_unavailable", lambda t: t.r_runner is None),
    ("manual_close", lambda t: t.bucket == "manual"),
    ("unpathed", lambda t: not t.pathed),
    ("no_tp2_distance", lambda t: t.tp2_r is None or t.tp2_r <= t.r_tp1),
)


def _section(trades: list[PartialTrade]) -> list[PartialTrade]:
    """The Runner endings population: closed runners of plans that have a TP2."""
    return [t for t in trades if t.closed and t.bucket != "no_tp2"]


def ending_of(trade: PartialTrade) -> str:
    """The scorecard ending of a closed runner; stall, time, manual and
    unknown close reasons all read as "other"."""
    return _ENDING_OF_BUCKET.get(trade.bucket, "other")


def is_giveback(trade: PartialTrade) -> bool:
    """Got at least halfway from TP1 to TP2, then closed below TP1, whatever
    the ending. Exactly at TP1 is not a giveback."""
    return (trade.decidable and trade.progress >= GIVEBACK_PROGRESS
            and trade.r_runner < trade.r_tp1)


def _share(k: int, n: int) -> dict:
    """A share and its Wilson 95% interval, percentages to 1 dp; None when n is 0."""
    bounds = wilson_interval(k, n)
    if bounds is None:
        return {"share": None, "lo": None, "hi": None}
    lo, hi = bounds
    return {"share": _rate(k, n), "lo": round(100.0 * lo, 1), "hi": round(100.0 * hi, 1)}


def _share_fields(ending: str, k: int, n: int) -> dict:
    return {"ending": ending, "n": k, "denominator": n, **_share(k, n), "thin": k < THIN_N}


def _total(values: list[float]) -> float | None:
    return round(sum(values), 4) if values else None


def _r_fields(group: list[PartialTrade]) -> dict:
    """R columns, over runners whose runner R is known."""
    measured = [t for t in group if t.r_runner is not None]
    sessions = [t.hold_tp1_exit for t in measured if t.hold_tp1_exit is not None]
    return {"r_n": len(measured),
            "avg_r": _mean(t.r_runner for t in measured),
            "median_r": _median([t.r_runner for t in measured]),
            "total_r": _total([(1.0 - t.fraction) * t.r_runner for t in measured]),
            "vs_all_out": _mean(t.delta_r for t in measured),
            "sessions": _median(sessions)}


def _path_fields(group: list[PartialTrade]) -> dict:
    """Path columns, over decidable runners only."""
    decidable = [t for t in group if t.decidable]
    progress = _mean(t.progress for t in decidable)
    return {"path_n": len(decidable),
            "best_r": _mean(t.runner_path["mfe_r"] for t in decidable),
            "progress": None if progress is None else round(100.0 * progress, 1),
            "gave_back": _mean(t.runner_path["mfe_r"] - t.r_runner for t in decidable)}


def _row(ending: str, group: list[PartialTrade], denominator: int) -> dict:
    return {**_share_fields(ending, len(group), denominator), **_r_fields(group),
            **_path_fields(group)}


def ending_rows(runners: list[PartialTrade]) -> list[dict]:
    """The five scorecard rows over a `_section` list. The four endings share
    the section as denominator; Giveback (any ending) is over decidable runners
    and is not part of that 100%."""
    rows = [_row(ending, [t for t in runners if ending_of(t) == ending], len(runners))
            for ending in ENDING_ROWS]
    decidable = [t for t in runners if t.decidable]
    rows.append(_row("giveback", [t for t in decidable if is_giveback(t)], len(decidable)))
    return rows


def path_exclusions(runners: list[PartialTrade]) -> dict:
    """Section runners left out of the path figures, by first failing reason."""
    counts = {name: 0 for name, _ in _PATH_CHECKS}
    for trade in runners:
        reason = next((name for name, fails in _PATH_CHECKS if fails(trade)), None)
        if reason is not None:
            counts[reason] += 1
    return counts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; every new function is under 10 (`_r_fields` is the largest, 9; `ending_rows` 8).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/partials.py tests/analytics/test_partials.py
git commit -m "feat(analytics): runner ending rows with Wilson shares and first-failing path exclusions (V219-3)"
```

### Task V219-4: Odds, cards, `runner_endings`, `outcomes` key removed, never-raise and endpoint tests

**Model:** sonnet — assembles V219-3's builders into the payload block, deletes one superseded function and adjusts its endpoint test; no cross-package design.

**Files:**
- Modify: `swingbot/core/analytics/partials.py` (constants :25-27 `OUTCOME_BUCKETS` removed, `ENDING_CARDS`/`ODDS_LEVELS` added; `outcomes` :213-221 deleted; new builders appended to the `# -- runner endings (v219)` section; `build_report` :315-330)
- Modify: `tests/analytics/test_partials.py` (`test_outcome_buckets_cover_every_partial_once` :78-84, `test_an_unknown_close_reason_is_reported_not_dropped` :87-89, `test_bulk_and_single_manual_closes_share_one_bucket_row` :204-209 rewritten; new tests appended)
- Modify: `tests/admin/test_api_v1_analytics_partials.py` (imports :4-8; `test_shape_and_echo` :39-48; new tests appended)

**Interfaces:**
- Consumes: `ENDING_ROWS`, `_section`, `ending_of`, `_share`, `ending_rows`, `path_exclusions` (V219-3); `PartialTrade.decidable`, `.progress` (V219-2).
- Produces (the payload Part 2 reads; shape fixed by the index's payload contract):
  - `ENDING_CARDS = ("tp2", "floor", "giveback", "trail")`, `ODDS_LEVELS = (25, 50, 75)`
  - `ending_cards(rows: list[dict]) -> list[dict]` — the matching rows' Share fields (`ending`, `n`, `denominator`, `share`, `lo`, `hi`, `thin`), in `ENDING_CARDS` order.
  - `runner_odds(runners: list[PartialTrade]) -> list[dict]` — per level `{"level", "n", "thin", "split": [{"ending", "n", "share", "lo", "hi"}]}`, `split` in `ENDING_ROWS` order; the group at level L is the decidable runners with `progress >= L / 100`.
  - `runner_endings(trades: list[PartialTrade]) -> dict` — `{"n", "decidable", "cards", "rows", "odds", "excluded"}`; `excluded` = `{"no_tp2", "runner_r_unavailable", "manual_close", "unpathed", "no_tp2_distance"}`.
  - `build_report(...)["runner_endings"]`; the `outcomes` key, `outcomes()` and `OUTCOME_BUCKETS` are gone.

**Background.** The route (`swingbot/admin/api_v1/analytics.py::analytics_partials`) returns `build_report` whole, so it needs no edit; only its endpoint test's key set changes. `OUTCOME_BUCKETS` was read only by `outcomes()` and one test (`git grep -n OUTCOME_BUCKETS` shows nothing else), so it goes with it; `outcome_bucket()` and `_REASON_BUCKET` stay (`PartialTrade.bucket` is built from them). Bucket `"other"` is now reported through `ending_of`, so the old "an unknown close reason is reported, never dropped" guarantee moves to the `other` row.

The never-raise requirement: `build_report` runs inside the endpoint, and one exception fails the whole Partials tab. V219-2 made `pathed` type-checked, so a malformed stamp is unpathed before any builder reads `mfe_r`; the tests below pin it at the builder and at the endpoint. Nothing else reads `runner_path` values unguarded: `_ladder_row` reads `pathed` runners only.

The worked block for `_book()` with `MANUAL` (index § Payload contract) is pinned below in full.

- [ ] **Step 1: Write the failing tests (analytics)**

In `tests/analytics/test_partials.py`, replace `test_outcome_buckets_cover_every_partial_once` (:78-84) with:

```python
def test_runner_endings_on_the_book(report):
    block = report["runner_endings"]
    assert (block["n"], block["decidable"]) == (4, 3)              # A, B, C, D; D is manual
    assert block["excluded"] == {"no_tp2": 1, "runner_r_unavailable": 0, "manual_close": 1,
                                 "unpathed": 0, "no_tp2_distance": 0}
    assert sum(v for k, v in block["excluded"].items() if k != "no_tp2") == \
        block["n"] - block["decidable"]
    assert [row["ending"] for row in block["rows"]] == ["tp2", "trail", "floor", "other", "giveback"]
    assert [card["ending"] for card in block["cards"]] == ["tp2", "floor", "giveback", "trail"]
    assert block["cards"][2] == {"ending": "giveback", "n": 0, "denominator": 3, "share": 0.0,
                                 "lo": 0.0, "hi": 56.2, "thin": True}
    assert block["cards"][0] == {"ending": "tp2", "n": 1, "denominator": 4, "share": 25.0,
                                 "lo": 4.6, "hi": 69.9, "thin": True}
```

Replace `test_an_unknown_close_reason_is_reported_not_dropped` (:87-89) with:

```python
def test_an_unknown_close_reason_lands_in_other_not_dropped():
    block = pa.runner_endings([pa.partial_trade(_trade("X", reason="acceptance", runner_r=1.0))])
    other = {row["ending"]: row for row in block["rows"]}["other"]
    assert (other["n"], other["share"], other["avg_r"]) == (1, 100.0, 1.0)
```

Replace `test_bulk_and_single_manual_closes_share_one_bucket_row` (:204-209) with:

```python
def test_bulk_and_single_manual_closes_share_the_other_row():
    book = [*_book(), _trade("Z", reason="manual_bulk")]
    block = pa.build_report(book, manual_exits={**MANUAL, "Z": 107.5})["runner_endings"]
    other = {row["ending"]: row for row in block["rows"]}["other"]
    assert other["n"] == 2 and other["path_n"] == 0
    assert other["avg_r"] == pytest.approx((2.5 + 1.5) / 2)
    assert block["excluded"]["manual_close"] == 2
```

Append at the end of the file:

```python
# -- v219: odds, cards, the runner_endings block -----------------------------

def _split(bar):
    return [(s["ending"], s["n"], s["share"], s["lo"], s["hi"]) for s in bar["split"]]


def test_odds_on_the_book(report):
    odds = report["runner_endings"]["odds"]
    assert [(bar["level"], bar["n"], bar["thin"]) for bar in odds] == \
        [(25, 3, True), (50, 2, True), (75, 2, True)]
    assert _split(odds[0]) == [("tp2", 1, 33.3, 6.1, 79.2), ("trail", 1, 33.3, 6.1, 79.2),
                               ("floor", 1, 33.3, 6.1, 79.2), ("other", 0, 0.0, 0.0, 56.2)]
    half = [("tp2", 1, 50.0, 9.5, 90.5), ("trail", 1, 50.0, 9.5, 90.5),
            ("floor", 0, 0.0, 0.0, 65.8), ("other", 0, 0.0, 0.0, 65.8)]
    assert _split(odds[1]) == half and _split(odds[2]) == half    # C's progress is 0.8


def test_an_odds_group_includes_a_runner_exactly_at_the_level():
    plans = [_trade("H", reason="tp1_runner_be", runner_r=1.34, path=_path(3.0, 2.5))]  # progress 0.5
    odds = pa.runner_odds(_runners(plans))
    assert [bar["n"] for bar in odds] == [1, 1, 0]
    assert odds[2]["split"][0] == {"ending": "tp2", "n": 0, "share": None, "lo": None, "hi": None}


def test_an_odds_bar_of_ten_is_not_thin():
    plans = [_trade(f"T{i}", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0))
             for i in range(10)]
    odds = pa.runner_odds(_runners(plans))
    assert [(bar["n"], bar["thin"]) for bar in odds] == [(10, False)] * 3


def test_cards_are_the_matching_rows_share_fields(report):
    block = report["runner_endings"]
    rows = {row["ending"]: row for row in block["rows"]}
    keys = ("ending", "n", "denominator", "share", "lo", "hi", "thin")
    for card in block["cards"]:
        assert card == {key: rows[card["ending"]][key] for key in keys}


def test_the_outcomes_key_and_function_are_gone(report):
    assert "outcomes" not in report and "runner_endings" in report
    assert not hasattr(pa, "outcomes") and not hasattr(pa, "OUTCOME_BUCKETS")


def test_malformed_stamps_never_fail_the_report():
    book = [
        _trade("A", reason="tp1_runner_tp2", runner_r=4.0, path=_path(4.2, 4.0)),
        _trade("N", reason="tp1_runner_trail", runner_r=3.0, path={"mfe_r": None, "ladder": {}}),
        _trade("S", reason="tp1_runner_trail", runner_r=3.0, path={"mfe_r": "3.6", "ladder": {}}),
        _trade("L", reason="tp1_runner_be", runner_r=1.34, path={"mfe_r": 2.6, "ladder": []}),
        _trade("K", reason="tp1_runner_be", runner_r=1.34, path="garbage"),
        _trade("B", reason="tp1_runner_trail", runner_r=3.0, path={"mfe_r": True, "ladder": {}}),
    ]
    report = pa.build_report(book)
    block = report["runner_endings"]
    assert (block["n"], block["decidable"]) == (6, 1)
    assert block["excluded"]["unpathed"] == 5
    assert report["counterfactuals"]["giveback"] == [0.2]
    assert report["counterfactuals"]["giveback_excluded"] == 5
    assert [row["n"] for row in report["counterfactuals"]["ladder"]] == [1] * 5


def test_all_runners_open_is_a_block_of_measured_zeros():
    report = pa.build_report([_trade("E", status=PlanStatus.PARTIAL)])
    block = report["runner_endings"]
    assert report["population"]["partial"] == 1
    assert (block["n"], block["decidable"]) == (0, 0)
    assert all(card["share"] is None and card["n"] == 0 for card in block["cards"])
    assert all(bar["n"] == 0 and bar["thin"] for bar in block["odds"])


def test_empty_scope_runner_endings():
    block = pa.build_report([])["runner_endings"]
    assert block["excluded"] == {"no_tp2": 0, "runner_r_unavailable": 0, "manual_close": 0,
                                 "unpathed": 0, "no_tp2_distance": 0}
    assert [row["denominator"] for row in block["rows"]] == [0] * 5
    assert [bar["level"] for bar in block["odds"]] == [25, 50, 75]
```

- [ ] **Step 2: Write the failing tests (endpoint)**

In `tests/admin/test_api_v1_analytics_partials.py`, replace the import line `from tests.analytics.test_partials import _book` (:7) with:

```python
from tests.analytics.test_partials import _book
from tests.analytics.test_partials import _trade as _partial_plan
```

Replace `test_shape_and_echo` (:39-48) with:

```python
def test_shape_and_echo(seed, logged_in):
    seed(plans=_book(), trades=[_manual_trade()])
    body = logged_in.get(_URL).get_json()
    assert set(body) == {"kpis", "funnel", "runner_endings", "counterfactuals", "holds",
                         "breakdowns", "thin_n", "population", "scope", "n"}
    assert body["n"] == 8 and body["scope"]["ledger"] == "main"
    assert [row["n"] for row in body["funnel"]] == [8, 6, 5, 1]
    assert body["counterfactuals"]["runner_r_unavailable"] == 0     # D priced from its trade
    assert body["kpis"]["beat_all_out_n"] == 5
    assert set(body["breakdowns"]) == {"strategy", "horizon", "side", "month"}


def test_the_runner_endings_block(seed, logged_in):
    seed(plans=_book(), trades=[_manual_trade()])
    body = logged_in.get(_URL).get_json()
    block = body["runner_endings"]
    assert set(block) == {"n", "decidable", "cards", "rows", "odds", "excluded"}
    assert (block["n"], block["decidable"]) == (4, 3)
    assert block["excluded"]["manual_close"] == 1 and block["excluded"]["no_tp2"] == 1
    assert [row["ending"] for row in block["rows"]] == ["tp2", "trail", "floor", "other", "giveback"]
    assert [bar["level"] for bar in block["odds"]] == [25, 50, 75]
    assert body["counterfactuals"]["giveback_excluded"] == 2
```

Append at the end of the file:

```python
def test_a_malformed_runner_path_leaves_the_endpoint_answering(seed, logged_in):
    seed(plans=[_partial_plan("A", reason="tp1_runner_tp2", runner_r=4.0,
                              path={"mfe_r": "high", "ladder": []}),
                _partial_plan("B", reason="tp1_runner_trail", runner_r=3.0,
                              path={"mfe_r": None, "ladder": {}})])
    response = logged_in.get(_URL)
    assert response.status_code == 200
    block = response.get_json()["runner_endings"]
    assert (block["n"], block["decidable"], block["excluded"]["unpathed"]) == (2, 0, 2)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: FAIL — `KeyError: 'runner_endings'`, `AttributeError: ... has no attribute 'runner_endings'` / `'runner_odds'`, and `test_the_outcomes_key_and_function_are_gone` failing on the old key.

The endpoint file reaches the local Postgres. **Run `/replicate-prod-db` first** (it tops up the one shared `swing-db` container on port 56789 with `.env` credentials, never a per-task container), then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py`
Expected: FAIL — `test_shape_and_echo` (key set still has `outcomes`), `test_the_runner_endings_block` and `test_a_malformed_runner_path_leaves_the_endpoint_answering` (`KeyError: 'runner_endings'`).

- [ ] **Step 4: Write the implementation**

In `swingbot/core/analytics/partials.py`:

4a. Constants: delete the `OUTCOME_BUCKETS` constant and its two comment lines (:25-27):

```python
#: Every partial trade lands in exactly one; "other" (an unknown close
#: reason) is reported only when non-empty, never dropped.
OUTCOME_BUCKETS = ("tp2", "trail", "floor", "stall", "time", "manual", "no_tp2", "open")
```

and below `ENDING_ROWS` (added by V219-3) add:

```python
#: Card order (the partner's layout C) and the odds chart's progress levels (%).
ENDING_CARDS = ("tp2", "floor", "giveback", "trail")
ODDS_LEVELS = (25, 50, 75)
_SHARE_KEYS = ("ending", "n", "denominator", "share", "lo", "hi", "thin")
```

4b. Delete the whole `outcomes` function (:213-221).

4c. At the end of the `# -- runner endings (v219)` section (after `path_exclusions`), add:

```python
def ending_cards(rows: list[dict]) -> list[dict]:
    """The four cards: each is its scorecard row's Share fields, so card and
    row cannot disagree."""
    by_ending = {row["ending"]: row for row in rows}
    return [{key: by_ending[ending][key] for key in _SHARE_KEYS} for ending in ENDING_CARDS]


def _odds_bar(decidable: list[PartialTrade], level: int) -> dict:
    group = [t for t in decidable if t.progress >= level / 100]
    split = []
    for ending in ENDING_ROWS:
        k = sum(1 for t in group if ending_of(t) == ending)
        split.append({"ending": ending, "n": k, **_share(k, len(group))})
    return {"level": level, "n": len(group), "thin": len(group) < THIN_N, "split": split}


def runner_odds(runners: list[PartialTrade]) -> list[dict]:
    """Of the decidable runners that got at least L% of the way from TP1 to
    TP2, how they ended. Descriptive conditionals on the live book, not rules."""
    decidable = [t for t in runners if t.decidable]
    return [_odds_bar(decidable, level) for level in ODDS_LEVELS]


def runner_endings(trades: list[PartialTrade]) -> dict:
    """The Runner endings section: cards, scorecard rows, odds and every
    exclusion, over closed runners of plans with a TP2. Never raises on a
    malformed runner_path (`PartialTrade.pathed` is type-checked)."""
    runners = _section(trades)
    rows = ending_rows(runners)
    return {
        "n": len(runners),
        "decidable": sum(1 for t in runners if t.decidable),
        "cards": ending_cards(rows),
        "rows": rows,
        "odds": runner_odds(runners),
        "excluded": {"no_tp2": sum(1 for t in trades if t.bucket == "no_tp2"),
                     **path_exclusions(runners)},
    }
```

4d. In `build_report` (:315-330) replace the line `"outcomes": outcomes(trades),` with `"runner_endings": runner_endings(trades),`:

```python
    return {
        "kpis": kpis(trades, decided),
        "funnel": funnel(plans, trades),
        "runner_endings": runner_endings(trades),
        "counterfactuals": counterfactuals(trades),
        "holds": holds(trades),
        "breakdowns": {dim: breakdown(dim, trades, plans) for dim in BREAKDOWN_DIMENSIONS},
        "thin_n": THIN_N,
        "population": {"filled": len(plans), "partial": len(trades),
                       "unreadable": len(partials) - len(trades)},
    }
```

4e. Confirm nothing else reads the removed names:

Run: `git grep -n "OUTCOME_BUCKETS\|pa\.outcomes\|\"outcomes\"" -- swingbot tests scripts`
Expected: no hits under `swingbot/` or `scripts/`; under `tests/` only `test_the_outcomes_key_and_function_are_gone` in `tests/analytics/test_partials.py`, which asserts the names are gone (the frontend's `outcomes` is Part 2's, V219-6).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_partials.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py`
Expected: PASS, `0 failed`, no skips (a skip means the shared `swing-db` is not reachable on port 56789: start it and re-run, never accept the skip).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `build_report` keeps its complexity (one key swapped), `kpis` 12 and `counterfactuals` 11 are untouched, every new function is under 10.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/analytics/partials.py tests/analytics/test_partials.py tests/admin/test_api_v1_analytics_partials.py
git commit -m "feat(analytics): runner_endings block (cards, odds, exclusions) replaces outcomes in /analytics/partials (V219-4)"
```

