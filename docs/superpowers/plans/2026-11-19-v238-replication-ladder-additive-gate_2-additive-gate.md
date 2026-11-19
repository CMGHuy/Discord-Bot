# v238 — Replication ladder and additive gate: Part 2, additive gate core (V238-4..V238-6b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-5" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (`### Part C — the additive-strategy gate`, `## Testing` "Additive gate")
**Index:** [2026-11-19-v238-replication-ladder-additive-gate_0-index.md](2026-11-19-v238-replication-ladder-additive-gate_0-index.md) — Goal, `## Global Constraints`, `## Handoff`, `## Decisions this index fixes` (add-only detection, Stage 0 spread) and `## Parallelisation` live there and bind every task below.

Lane C2, sequential (one file, `swingbot/core/backtesting/acceptance_additive.py`), independent of lane C1 (Part 1): no shared file, no shared contract. V238-4 creates the module with the add-only split and clauses 1–2; V238-5 adds clauses 3–4; V238-6 adds the Stage 0 MDE and `evaluate_additive`, the one entry point Part 3 (`validate_component.py --gate additive`) calls; V238-6b adds the never-gating disclosures (V238-6 was split for the 20 KB task cap, `SPLIT: V238-6 -> V238-6b`). The module is pure: no file I/O, no CLI, no `r_basis` check (that is Part 3's Stage −1 through `provenance.check_r_basis`). `acceptance.py`, `acceptance_harvest.py` and `instrument/stats.py` are imported, never edited.

Conventions every task below shares:

- Every interval is the week-cluster bootstrap (`instrument/stats.week_cluster_bootstrap`, resampling ISO weeks of `entry_date`), 10,000 resamples and seed 42 by default; tests pass `n_resamples=300` for speed. The lower 95% bound is the 2.5th percentile of the draws, the upper the 97.5th, the one-sided p the share of draws at or below zero (as `acceptance.bootstrap_delta`).
- Clause thresholds are strict (`>`), compared with a `_EPS = 1e-9` guard so a boundary value equal to its bar FAILs regardless of the last floating-point bit.
- `ClauseResult.value` / `.threshold`: clause 1 point own ExpR / `0.0`; clause 2 lower-bound win rate / break-even, both in percent; clause 3 point book ΔR / the floor; clause 4 positive folds / `FOLDS_POSITIVE`.

# Phase 2 — Additive gate core

### Task V238-4: Additive split and clauses 1–2

**Model:** opus — a new pre-registered gate module whose misuse rules and clause arithmetic other gates and v231 build on; the boundary semantics need judgement.

**Files:**
- Create: `swingbot/core/backtesting/acceptance_additive.py`
- Test: `tests/backtesting/test_acceptance_additive.py` (create; suite `backtesting-a-k`, glob `tests/backtesting/test_[a-k]*.py`, no `suites.toml` edit)

**Interfaces:**
- Consumes (all exist, never edited): `acceptance.ArmTrade` (:28, `.key` = `(ticker, strategy, horizon_key, entry_date, source, direction)`), `acceptance.population_split(baseline, component) -> dict` (keys `removed`, `added`, `changed` (outcome differs), `unchanged`, `is_subset`; pairs are `(baseline_trade, component_trade)`), `acceptance.expectancy_r`, `acceptance.win_rate` (percent, decided only), `acceptance.CLOSED`, `acceptance.DECIDED`, `acceptance.ClauseResult(name, verdict, detail, value=None, threshold=None)`, `acceptance.BOOTSTRAP_RESAMPLES = 10_000`, `acceptance.ALPHA = 0.05`; `arms.pairing.index_by_key(trades)` (raises `DuplicateKeyError`, a `ValueError`); `instrument.stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` (calls `statistic(b_draw, c_draw)`, drops `None` draws).
- Produces (index ledger, final):
  - `ADDITIVE_VERSION = 1`; `ADDITIVE_GATE_MISUSE = "ADDITIVE_GATE_MISUSE"`
  - `CLAUSES = ("own_expectancy", "win_rate_above_breakeven", "book_net_gain", "stability")`
  - `@dataclass(frozen=True) AdditiveSplit(added: tuple, displaced: tuple, misuse: str | None = None)` — `misuse` is `None` or a reason string that starts with `ADDITIVE_GATE_MISUSE`.
  - `split_additive(baseline, component) -> AdditiveSplit` (raises `DuplicateKeyError` on a duplicate key in either arm)
  - `added_bootstrap(added, statistic, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> np.ndarray` — `statistic(rows)` on each week draw of the added rows.
  - `clause_own_expectancy(added, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> ClauseResult` (`value` = point own net ExpR, `threshold = 0.0`)
  - `realised_breakeven(rows) -> float | None` — a fraction in `[0, 1]`.
  - `clause_win_rate_above_breakeven(added, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> ClauseResult` (`value` = lower-bound win rate in percent, `threshold` = break-even in percent)
  - Private helpers V238-5/V238-6 reuse: `_EPS = 1e-9`, `_closed(rows) -> list`, `_interval(draws) -> tuple[float, float, float]` (lo, hi, p).

Add-only rules (index `## Decisions this index fixes`, final): misuse when the component adds no row; when any shared key's outcome **or** R changed (`population_split` compares outcome only, so R is checked here); when more baseline rows vanished than rows were added. Every vanished baseline key is a displaced row. The checks run in that order and the first one that fires is the reason.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_acceptance_additive.py`:

```python
"""v238 additive gate (v230 spec Part C): the add-only split and clauses 1-2.

Fixtures put rows in distinct ISO weeks so the week-cluster bootstrap has
units to resample. Where a clause is tested at its boundary every week has
the same composition, so every bootstrap draw equals the full-sample value
and the lower bound is exact.
"""
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms.pairing import DuplicateKeyError

FAST = dict(n_resamples=300, seed=42)


def _row(i, r, outcome="win", *, week=0, strategy="Turtle Soup", source="strategy"):
    entry = date(2021, 1, 4) + timedelta(days=7 * week)
    return ArmTrade(ticker=f"T{i}", strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _base(n=20):
    return [_row(i, 1.0 if i % 2 else -1.0, "win" if i % 2 else "loss", week=i,
                 strategy="RSI", source="confluence") for i in range(n)]


def _weekly(pattern, weeks=30):
    """`pattern` = [(r, outcome), ...] repeated in every week, one ticker per row."""
    return [_row(100 * w + j, r, outcome, week=w)
            for w in range(weeks) for j, (r, outcome) in enumerate(pattern)]


ADDED = [_row(500 + i, 2.0, "win", week=i) for i in range(3)]


def test_module_constants_are_pinned():
    assert aa.ADDITIVE_VERSION == 1
    assert aa.ADDITIVE_GATE_MISUSE == "ADDITIVE_GATE_MISUSE"
    assert aa.CLAUSES == ("own_expectancy", "win_rate_above_breakeven",
                          "book_net_gain", "stability")


# --- split_additive -----------------------------------------------------------------

def test_an_add_only_component_splits_cleanly():
    base = _base()
    split = aa.split_additive(base, base + ADDED)
    assert split.misuse is None
    assert split.added == tuple(ADDED)
    assert split.displaced == ()


def test_a_component_that_adds_nothing_is_misuse():
    base = _base()
    split = aa.split_additive(base, list(base))
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "adds no row" in split.misuse


def test_a_changed_shared_outcome_is_misuse():
    base = _base()
    flipped = replace(base[1], outcome="loss", r_multiple=-1.0)
    split = aa.split_additive(base, [base[0], flipped, *base[2:], *ADDED])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "changed outcome or R" in split.misuse


def test_a_changed_shared_r_with_the_same_outcome_is_misuse():
    base = _base()
    moved = replace(base[1], r_multiple=1.5)
    split = aa.split_additive(base, [base[0], moved, *base[2:], *ADDED])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "changed outcome or R" in split.misuse


def test_a_vanished_baseline_row_with_an_added_row_is_a_displacement():
    base = _base()
    split = aa.split_additive(base, base[1:] + ADDED)
    assert split.misuse is None
    assert split.displaced == (base[0],)
    assert len(split.added) == 3


def test_more_rows_vanished_than_added_is_misuse():
    base = _base()
    split = aa.split_additive(base, base[3:] + ADDED[:2])
    assert split.misuse.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert "3 baseline row(s) vanished but only 2 were added" in split.misuse


def test_the_first_failing_rule_is_the_reason():
    base = _base()
    split = aa.split_additive(base, base[3:])   # adds nothing AND removes three
    assert "adds no row" in split.misuse


def test_a_duplicate_key_is_refused_not_collapsed():
    base = _base()
    with pytest.raises(DuplicateKeyError):
        aa.split_additive(base, base + [ADDED[0], ADDED[0]])


# --- the week bootstrap over added rows ---------------------------------------------

def test_added_bootstrap_resamples_whole_weeks():
    week_a = [_row(1, 1.0, week=0), _row(2, 1.0, week=0)]
    week_b = [_row(3, -1.0, "loss", week=1)]
    draws = aa.added_bootstrap(week_a + week_b, aa.expectancy_r, **FAST)
    values = set(np.round(draws, 6))
    assert values <= {1.0, round(1 / 3, 6), -1.0}    # AA, AB, BB
    assert round(-1 / 3, 6) not in values            # a row bootstrap would hit this


# --- clause 1: own_expectancy -------------------------------------------------------

def test_own_expectancy_passes_when_every_week_pays():
    res = aa.clause_own_expectancy(_weekly([(2.0, "win"), (-1.0, "loss")]), **FAST)
    assert res.name == "own_expectancy"
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(0.5)
    assert res.threshold == 0.0
    assert "p=" in res.detail                        # the one-sided p is reported


def test_own_expectancy_fails_at_a_lower_bound_of_exactly_zero():
    res = aa.clause_own_expectancy(_weekly([(1.0, "win"), (-1.0, "loss")]), **FAST)
    assert res.value == pytest.approx(0.0)
    assert res.verdict == "FAIL"


def test_own_expectancy_fails_when_the_rows_lose():
    res = aa.clause_own_expectancy(_weekly([(0.5, "win"), (-1.0, "loss")]), **FAST)
    assert res.verdict == "FAIL"


def test_own_expectancy_fails_with_no_closed_row():
    rows = [_row(i, None, "not_triggered", week=i) for i in range(5)]
    res = aa.clause_own_expectancy(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.value is None
    assert "undefined" in res.detail


# --- realised break-even ------------------------------------------------------------

def test_breakeven_is_avg_loss_over_avg_win_plus_avg_loss():
    rows = [_row(1, 2.0), _row(2, 2.0), _row(3, -1.0, "loss")]
    assert aa.realised_breakeven(rows) == pytest.approx(1.0 / 3.0)


def test_breakeven_ignores_undecided_rows():
    rows = [_row(1, 2.0), _row(2, -1.0, "loss"), _row(3, -0.4, "timeout"),
            _row(4, 0.0, "scratch")]
    assert aa.realised_breakeven(rows) == pytest.approx(1.0 / 3.0)


def test_breakeven_with_no_win_is_one_and_with_no_loss_is_zero():
    assert aa.realised_breakeven([_row(1, -1.0, "loss")]) == pytest.approx(1.0)
    assert aa.realised_breakeven([_row(1, 2.0)]) == pytest.approx(0.0)


def test_breakeven_is_undefined_with_no_decided_row():
    assert aa.realised_breakeven([_row(1, -0.2, "timeout")]) is None
    assert aa.realised_breakeven([]) is None


# --- clause 2: win_rate_above_breakeven ---------------------------------------------

def test_win_rate_passes_above_its_own_breakeven():
    # WR 33.33% every week; break-even 1 / (2.2 + 1) = 31.25%
    rows = _weekly([(2.2, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.name == "win_rate_above_breakeven"
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(100.0 / 3.0)
    assert res.threshold == pytest.approx(31.25)


def test_win_rate_fails_when_its_lower_bound_equals_breakeven():
    # WR 33.33% every week; break-even 1 / (2 + 1) = 33.33%
    rows = _weekly([(2.0, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.value == pytest.approx(res.threshold)
    assert res.verdict == "FAIL"


def test_win_rate_fails_below_breakeven_even_with_a_high_pooled_look():
    # WR 33.33%, break-even 50%: a 1R winner with two 1R losers
    rows = _weekly([(1.0, "win"), (-1.0, "loss"), (-1.0, "loss")])
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.threshold == pytest.approx(50.0)


def test_win_rate_fails_with_no_decided_row():
    rows = [_row(i, -0.1, "timeout", week=i) for i in range(5)]
    res = aa.clause_win_rate_above_breakeven(rows, **FAST)
    assert res.verdict == "FAIL"
    assert res.value is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive.py`
Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.acceptance_additive'`.

- [ ] **Step 3: Create `swingbot/core/backtesting/acceptance_additive.py`**

```python
"""Additive-strategy acceptance gate (v230 spec Part C, plan v238).

Read docs/claude/backtest-methodology.md's "Additive gate" section before
changing anything here. The clause set and its constants are PRE-REGISTERED.

The v72 gate makes the book's pooled win rate the objective. A strategy that
only ADDS rows at reward:risk 2 breaks even at a 33% win rate, so it can pay
while lowering the pooled win rate, and v72 refuses it (v180 died on a
-0.21pp pooled dWR). This gate judges an added strategy on its own rows:

1. own_expectancy (the objective): the added rows' net ExpR.
2. win_rate_above_breakeven: their decided win rate against their OWN
   realised break-even, avg loss / (avg win + avg loss).
3. book_net_gain: the book's total R must not fall when an added position
   displaces a baseline plan (SKIPPED with no displacement).
4. stability: the added rows' ExpR per walk-forward fold.

Every interval is week-clustered (instrument.stats): an added strategy's
signals bunch on market days, so one bad week is one bet. Both arms must be
net of costs; that precondition is checked by the caller
(validate_component.py, provenance.check_r_basis), not here. numpy only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .acceptance import (
    ALPHA, BOOTSTRAP_RESAMPLES, CLOSED, DECIDED, ClauseResult, expectancy_r,
    population_split, win_rate,
)
from .arms.pairing import index_by_key
from .instrument.stats import week_cluster_bootstrap

ADDITIVE_VERSION = 1   # additive-procedure version, recorded in every results doc
ADDITIVE_GATE_MISUSE = "ADDITIVE_GATE_MISUSE"
CLAUSES = ("own_expectancy", "win_rate_above_breakeven", "book_net_gain", "stability")

#: Strict thresholds: a value equal to its bar FAILs whatever its last bit.
_EPS = 1e-9


@dataclass(frozen=True)
class AdditiveSplit:
    """The component against the baseline, by pairing key.

    ``added`` are component rows with no baseline key; ``displaced`` are
    baseline rows with no component key (an added position blocked them).
    ``misuse`` is None for an add-only arm, else the refusal reason."""
    added: tuple
    displaced: tuple
    misuse: str | None = None


def _r_changed(baseline_trade, component_trade) -> bool:
    b, c = baseline_trade.r_multiple, component_trade.r_multiple
    if (b is None) != (c is None):
        return True
    return b is not None and abs(b - c) > _EPS


def _misuse(split: dict, moved: list) -> str | None:
    added, removed = split["added"], split["removed"]
    if not added:
        return (f"{ADDITIVE_GATE_MISUSE}: the component adds no row; a filter or "
                f"veto belongs to the v72 gate")
    if moved:
        return (f"{ADDITIVE_GATE_MISUSE}: {len(moved)} shared row(s) changed outcome "
                f"or R (first {moved[0].key}); an exit or geometry change belongs "
                f"to the v92 harvest gate")
    if len(removed) > len(added):
        return (f"{ADDITIVE_GATE_MISUSE}: {len(removed)} baseline row(s) vanished but "
                f"only {len(added)} were added; every displaced row needs an added "
                f"position")
    return None


def split_additive(baseline, component) -> AdditiveSplit:
    """Partition the arms and decide whether the component only adds rows.

    A duplicate key in either arm raises (``index_by_key``): pairing would
    silently keep one row and every clause would be wrong."""
    index_by_key(baseline)
    index_by_key(component)
    split = population_split(baseline, component)
    moved = [bt for bt, _ in split["changed"]]
    moved += [bt for bt, ct in split["unchanged"] if _r_changed(bt, ct)]
    return AdditiveSplit(added=tuple(split["added"]),
                         displaced=tuple(split["removed"]),
                         misuse=_misuse(split, moved))


def _closed(rows) -> list:
    return [t for t in rows if t.outcome in CLOSED and t.r_multiple is not None]


def added_bootstrap(added, statistic, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> np.ndarray:
    """``statistic(rows)`` on each week-cluster draw of the added rows alone
    (no baseline), undefined draws dropped."""
    return week_cluster_bootstrap([], list(added),
                                  lambda _baseline, rows: statistic(rows),
                                  n_resamples=n_resamples, seed=seed)


def _interval(draws) -> tuple:
    """(lower 95% bound, upper 95% bound, one-sided p = share of draws <= 0)."""
    lo = float(np.percentile(draws, 100 * ALPHA / 2))
    hi = float(np.percentile(draws, 100 * (1 - ALPHA / 2)))
    return lo, hi, float(np.mean(draws <= 0.0))


def clause_own_expectancy(added, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                          seed: int = 42) -> ClauseResult:
    """Clause 1, the objective: the added rows' net ExpR, lower 95% bound > 0."""
    closed = _closed(added)
    point = expectancy_r(closed)
    if point is None:
        return ClauseResult(CLAUSES[0], "FAIL",
                            "no closed added row with an R; own ExpR undefined",
                            None, 0.0)
    lo, hi, p = _interval(added_bootstrap(closed, expectancy_r,
                                          n_resamples=n_resamples, seed=seed))
    ok = lo > _EPS
    return ClauseResult(
        CLAUSES[0], "PASS" if ok else "FAIL",
        f"own net ExpR {point:+.4f}R [{lo:+.4f},{hi:+.4f}] p={p:.4f} "
        f"N={len(closed)} (lower bound must be > 0)", point, 0.0)


def _mean_or_zero(values) -> float:
    return float(np.mean(values)) if values else 0.0


def realised_breakeven(rows) -> float | None:
    """The win rate (a fraction) at which these rows' own average win and
    average loss break even: avg loss / (avg win + avg loss), decided rows
    only. No winner gives 1.0, no loser 0.0; no decided row gives None."""
    decided = [t for t in rows if t.outcome in DECIDED and t.r_multiple is not None]
    avg_win = _mean_or_zero([t.r_multiple for t in decided if t.outcome == "win"])
    avg_loss = _mean_or_zero([-t.r_multiple for t in decided if t.outcome == "loss"])
    total = avg_win + avg_loss
    if not decided or total <= 0.0:
        return None
    return avg_loss / total


def clause_win_rate_above_breakeven(added, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
                                    seed: int = 42) -> ClauseResult:
    """Clause 2: the decided win rate's lower 95% bound (percent) above the
    added rows' realised break-even (percent). Replaces v72's pooled
    win-rate comparison with the strategy's own arithmetic."""
    decided = [t for t in added if t.outcome in DECIDED and t.r_multiple is not None]
    point, breakeven = win_rate(decided), realised_breakeven(decided)
    if point is None or breakeven is None:
        return ClauseResult(CLAUSES[1], "FAIL",
                            "no decided added row; win rate and break-even undefined",
                            None, None)
    bar = 100.0 * breakeven
    lo, hi, _ = _interval(added_bootstrap(decided, win_rate,
                                          n_resamples=n_resamples, seed=seed))
    ok = lo > bar + _EPS
    return ClauseResult(
        CLAUSES[1], "PASS" if ok else "FAIL",
        f"own WR {point:.2f}% [{lo:.2f},{hi:.2f}] vs realised break-even "
        f"{bar:.2f}% (avg loss / (avg win + avg loss)), N={len(decided)}", lo, bar)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function is under 6).

Run: `python scripts/dev/testrun.py suites`
Expected: `backtesting-a-k` is still under its `max_tests`; if it is not, split it by feature in `tests/suites.toml` in this commit (never raise the limit).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_additive.py tests/backtesting/test_acceptance_additive.py
git commit -m "feat(backtesting): v238 additive gate -- add-only split, own ExpR and own break-even clauses"
```

### Task V238-5: Additive clauses 3–4: book net gain and stability

**Model:** opus — paired book-total bootstrap with a displacement-dependent floor and a three-fold stability rule; the boundary and degenerate-fold cases need judgement.

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_additive.py` (append after `clause_win_rate_above_breakeven`, the last function V238-4 wrote)
- Test: `tests/backtesting/test_acceptance_additive_book.py` (create; suite `backtesting-a-k`)

**Interfaces:**
- Consumes: from V238-4 (same module) `CLAUSES`, `AdditiveSplit`, `split_additive`, `_EPS`, `_closed`, `_interval`; `acceptance.expectancy_r`, `acceptance.ClauseResult`, `acceptance.BOOTSTRAP_RESAMPLES`; `instrument.stats.week_cluster_bootstrap` (already imported by V238-4).
- Produces (index ledger, final):
  - `TOLERANCE_SHARE = 0.10`; `FOLD_YEARS = ("2021", "2022", "2023")`; `FOLD_FLOOR_R = -0.10`; `FOLD_MIN_N = 30`; `FOLDS_POSITIVE = 2`
  - `clause_book_net_gain(baseline, component, split, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> ClauseResult` — `SKIPPED` when `split.displaced` is empty; else PASS when the point change in the book's total R (component sum minus baseline sum, CLOSED rows with an R) is > 0 **and** its week-cluster lower 95% bound is > `-TOLERANCE_SHARE × (added rows' total R)`. `value` = point, `threshold` = that floor.
  - `clause_stability(folds: list[dict]) -> ClauseResult` — folds in `validate_component.load_folds` shape `{"test_year", "baseline", "component"}` (`test_year` may be `int` or `str`; compared as `str`). PASS when the years are exactly `FOLD_YEARS`, no fold's arms are misuse, every fold has ≥ `FOLD_MIN_N` closed added rows, no fold's added-row ExpR is below `FOLD_FLOOR_R`, and ≥ `FOLDS_POSITIVE` folds are > 0. `value` = positive folds, `threshold = 2.0`.
  - Private, tested here: `_book_verdict(point: float, lo: float, floor: float) -> bool`.

Why clause 3 sums rather than averages: the question is whether the book as a whole made more R with the strategy on. Unchanged rows cancel inside each resampled week (both arms share the week draw), so the statistic is in effect added R minus displaced R, with the uncertainty of the weeks they fell in.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_acceptance_additive_book.py`:

```python
"""v238 additive gate clauses 3-4 (v230 spec Part C): book net gain, stability."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade

FAST = dict(n_resamples=300, seed=42)


def _outcome(r):
    return "win" if r > 0 else ("loss" if r < 0 else "scratch")


def _row(ticker, r, *, week=0, year=2021, strategy="Turtle Soup", source="strategy"):
    entry = date(year, 1, 4) + timedelta(days=7 * week)
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=_outcome(r), r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _base_row(ticker, r, **kw):
    return _row(ticker, r, strategy="RSI", source="confluence", **kw)


def _displacing_arms(added_r, displaced_r, weeks=30):
    """Every week: one kept baseline row (+1R), one baseline row the added
    strategy displaces, one added row. Identical weeks make every bootstrap
    draw equal the point estimate."""
    baseline, component = [], []
    for w in range(weeks):
        kept = _base_row(f"K{w}", 1.0, week=w)
        baseline += [kept, _base_row(f"D{w}", displaced_r, week=w)]
        component += [kept, _row(f"A{w}", added_r, week=w)]
    return baseline, component


def test_clause_constants_are_pinned():
    assert aa.TOLERANCE_SHARE == 0.10
    assert aa.FOLD_YEARS == ("2021", "2022", "2023")
    assert aa.FOLD_FLOOR_R == -0.10
    assert aa.FOLD_MIN_N == 30
    assert aa.FOLDS_POSITIVE == 2


# --- clause 3: book_net_gain --------------------------------------------------------

def test_book_net_gain_is_skipped_without_displacement():
    baseline = [_base_row(f"K{w}", 1.0, week=w) for w in range(10)]
    component = baseline + [_row(f"A{w}", 2.0, week=w) for w in range(10)]
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.name == "book_net_gain"
    assert res.verdict == "SKIPPED"
    assert "no baseline row displaced" in res.detail


def test_book_net_gain_passes_when_the_book_makes_more_r():
    baseline, component = _displacing_arms(added_r=2.0, displaced_r=-1.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.verdict == "PASS"
    assert res.value == pytest.approx(30 * 3.0)          # sum, not mean
    assert res.threshold == pytest.approx(-0.10 * 30 * 2.0)


def test_book_net_gain_fails_at_a_point_change_of_zero():
    baseline, component = _displacing_arms(added_r=1.0, displaced_r=1.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value == pytest.approx(0.0)
    assert res.verdict == "FAIL"


def test_book_net_gain_fails_when_displacement_costs_more_than_it_adds():
    baseline, component = _displacing_arms(added_r=0.5, displaced_r=2.0)
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value < 0
    assert res.verdict == "FAIL"


def test_book_net_gain_fails_a_positive_point_with_a_lower_bound_under_the_floor():
    # Weeks 0-4 displace a +5R plan for a +1R add (-4R each); weeks 5-29
    # only add +1R. Point +5R, floor -3R, but a draw heavy in bad weeks
    # sinks the book well below the floor.
    baseline = [_base_row(f"D{w}", 5.0, week=w) for w in range(5)]
    component = [_row(f"A{w}", 1.0, week=w) for w in range(30)]
    split = aa.split_additive(baseline, component)
    res = aa.clause_book_net_gain(baseline, component, split, **FAST)
    assert res.value == pytest.approx(5.0)
    assert res.threshold == pytest.approx(-3.0)
    assert res.verdict == "FAIL"
    assert "floor" in res.detail


@pytest.mark.parametrize("point, lo, floor, ok", [
    (0.5, -0.999, -1.0, True),
    (0.5, -1.0, -1.0, False),        # the lower bound must be strictly above the floor
    (0.0, 2.0, -1.0, False),         # the point must be strictly positive
    (1e-12, 2.0, -1.0, False),       # ... beyond float noise
])
def test_book_verdict_boundaries(point, lo, floor, ok):
    assert aa._book_verdict(point, lo, floor) is ok


# --- clause 4: stability ------------------------------------------------------------

def _fold(year, r, n=40):
    baseline = [_base_row(f"K{year}", 1.0, year=int(year))]
    added = [_row(f"A{i}", r, week=i % 40, year=int(year)) for i in range(n)]
    return {"test_year": year, "baseline": baseline, "component": baseline + added}


def _folds(r21, r22, r23, *, n=(40, 40, 40)):
    return [_fold("2021", r21, n[0]), _fold("2022", r22, n[1]), _fold("2023", r23, n[2])]


def test_stability_passes_with_two_positive_folds_and_none_sunk():
    res = aa.clause_stability(_folds(0.5, 0.2, -0.05))
    assert res.name == "stability"
    assert res.verdict == "PASS"
    assert res.value == 2.0
    assert res.threshold == 2.0
    assert "2021 +0.5000R N=40" in res.detail


def test_stability_fails_with_one_positive_fold():
    res = aa.clause_stability(_folds(0.5, -0.05, -0.05))
    assert res.verdict == "FAIL"
    assert res.value == 1.0


def test_a_fold_of_exactly_zero_is_not_positive():
    assert aa.clause_stability(_folds(0.5, 0.0, 0.0)).verdict == "FAIL"


def test_a_fold_exactly_at_the_floor_is_allowed():
    assert aa.clause_stability(_folds(0.5, 0.2, -0.10)).verdict == "PASS"


def test_a_fold_below_the_floor_fails_even_with_two_positive():
    res = aa.clause_stability(_folds(0.5, 0.2, -0.15))
    assert res.verdict == "FAIL"
    assert "below floor: 2023" in res.detail


@pytest.mark.parametrize("n, verdict", [(29, "FAIL"), (30, "PASS")])
def test_every_fold_needs_thirty_added_rows(n, verdict):
    res = aa.clause_stability(_folds(0.5, 0.2, 0.1, n=(40, n, 40)))
    assert res.verdict == verdict
    if verdict == "FAIL":
        assert "thin: 2022" in res.detail


def test_integer_fold_years_are_accepted_and_order_does_not_matter():
    folds = [_fold(2023, 0.1), _fold(2021, 0.5), _fold(2022, 0.2)]
    res = aa.clause_stability(folds)
    assert res.verdict == "PASS"
    assert res.detail.index("2021") < res.detail.index("2022") < res.detail.index("2023")


def test_folds_other_than_2021_to_2023_fail():
    folds = [_fold("2020", 0.5), _fold("2021", 0.5), _fold("2022", 0.5)]
    res = aa.clause_stability(folds)
    assert res.verdict == "FAIL"
    assert "folds must be 2021/2022/2023, got 2020/2021/2022" in res.detail


def test_no_folds_fail():
    res = aa.clause_stability([])
    assert res.verdict == "FAIL"
    assert "got none" in res.detail


def test_a_misused_fold_fails_the_clause():
    folds = _folds(0.5, 0.2, 0.1)
    folds[1] = {**folds[1], "component": list(folds[1]["baseline"])}   # adds nothing
    res = aa.clause_stability(folds)
    assert res.verdict == "FAIL"
    assert "fold 2022" in res.detail
    assert aa.ADDITIVE_GATE_MISUSE in res.detail
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_book.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.acceptance_additive' has no attribute 'TOLERANCE_SHARE'` (and the same for the clause functions).

- [ ] **Step 3: Append clauses 3 and 4 to `acceptance_additive.py`**

Append after `clause_win_rate_above_breakeven`:

```python
# --- clause 3: book_net_gain ----------------------------------------------------------

#: PRE-REGISTERED (spec Part C): the book's total R may fall by at most 10%
#: of the added rows' own total R at the lower bound.
TOLERANCE_SHARE = 0.10


def _book_total(rows) -> float:
    return float(sum(t.r_multiple for t in _closed(rows)))


def _book_delta(baseline, component) -> float:
    """Strategy on minus strategy off, the book's total R (a sum, not a mean)."""
    return _book_total(component) - _book_total(baseline)


def _book_verdict(point: float, lo: float, floor: float) -> bool:
    return point > _EPS and lo > floor + _EPS


def clause_book_net_gain(baseline, component, split: AdditiveSplit, *,
                         n_resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = 42) -> ClauseResult:
    """Clause 3: an added position that displaces a baseline plan (heat, one
    position per ticker) must not cost the book its total R. Paired: both
    arms resampled with the same week draw, so unchanged rows cancel."""
    if not split.displaced:
        return ClauseResult(CLAUSES[2], "SKIPPED",
                            "no baseline row displaced; the book only gains rows",
                            None, None)
    added_total = _book_total(split.added)
    floor = -TOLERANCE_SHARE * added_total
    point = _book_delta(baseline, component)
    lo, hi, p = _interval(week_cluster_bootstrap(
        list(baseline), list(component), _book_delta,
        n_resamples=n_resamples, seed=seed))
    ok = _book_verdict(point, lo, floor)
    return ClauseResult(
        CLAUSES[2], "PASS" if ok else "FAIL",
        f"book total R {point:+.2f}R [{lo:+.2f},{hi:+.2f}] p={p:.4f}; floor "
        f"{floor:+.2f}R (-{TOLERANCE_SHARE:.0%} of the added rows' {added_total:+.2f}R); "
        f"{len(split.added)} added, {len(split.displaced)} displaced", point, floor)


# --- clause 4: stability --------------------------------------------------------------

#: PRE-REGISTERED (spec Part C): the walk-forward test years and the bar.
FOLD_YEARS = ("2021", "2022", "2023")
FOLD_FLOOR_R = -0.10
FOLD_MIN_N = 30
FOLDS_POSITIVE = 2


def _fold_row(fold: dict) -> dict:
    split = split_additive(fold["baseline"], fold["component"])
    closed = _closed(split.added)
    return {"year": str(fold["test_year"]), "n": len(closed),
            "exp_r": expectancy_r(closed), "misuse": split.misuse}


def _fold_problem(rows: list) -> str | None:
    years = tuple(row["year"] for row in rows)
    if years != FOLD_YEARS:
        return f"folds must be {'/'.join(FOLD_YEARS)}, got {'/'.join(years) or 'none'}"
    for row in rows:
        if row["misuse"]:
            return f"fold {row['year']}: {row['misuse']}"
    return None


def _fold_text(row: dict) -> str:
    exp = "n/a" if row["exp_r"] is None else f"{row['exp_r']:+.4f}R"
    return f"{row['year']} {exp} N={row['n']}"


def _stability_detail(rows: list, positive: int, thin: list, sunk: list) -> str:
    parts = [_fold_text(row) for row in rows]
    parts.append(f"positive {positive}/{len(FOLD_YEARS)} (need {FOLDS_POSITIVE}), "
                 f"floor {FOLD_FLOOR_R:+.2f}R, min N {FOLD_MIN_N}")
    if thin:
        parts.append(f"thin: {', '.join(thin)}")
    if sunk:
        parts.append(f"below floor: {', '.join(sunk)}")
    return "; ".join(parts)


def clause_stability(folds: list) -> ClauseResult:
    """Clause 4: the added rows' net ExpR per walk-forward fold (2021, 2022,
    2023) is > 0 in at least two, below -0.10R in none, on N >= 30 each."""
    rows = sorted((_fold_row(fold) for fold in folds), key=lambda row: row["year"])
    problem = _fold_problem(rows)
    if problem:
        return ClauseResult(CLAUSES[3], "FAIL", problem, None, float(FOLDS_POSITIVE))
    positive = sum(1 for row in rows if row["exp_r"] is not None and row["exp_r"] > _EPS)
    thin = [row["year"] for row in rows if row["n"] < FOLD_MIN_N]
    sunk = [row["year"] for row in rows
            if row["exp_r"] is not None and row["exp_r"] < FOLD_FLOOR_R - _EPS]
    ok = positive >= FOLDS_POSITIVE and not thin and not sunk
    return ClauseResult(CLAUSES[3], "PASS" if ok else "FAIL",
                        _stability_detail(rows, positive, thin, sunk),
                        float(positive), float(FOLDS_POSITIVE))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_book.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive.py`
Expected: still green (V238-4's tests untouched).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`clause_stability` is the largest new function, under 10).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_additive.py tests/backtesting/test_acceptance_additive_book.py
git commit -m "feat(backtesting): v238 additive gate -- book net gain and fold stability clauses"
```

### Task V238-6: Additive Stage 0 MDE and evaluate_additive

**Model:** opus — the gate's single entry point Part 3 calls, plus the frozen-effect power precheck; stage-to-clause mapping and misuse raising are the contract.

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_additive.py` (extend the imports at the top; append after `clause_stability`, the last function V238-5 wrote)
- Test: `tests/backtesting/test_acceptance_additive_evaluate.py` (create; suite `backtesting-a-k`)

Split for the 20 KB cap (`SPLIT: V238-6 -> V238-6b`): this task delivers the Stage 0 precheck and `evaluate_additive`; V238-6b delivers `disclosures` / `render_disclosures`. Every ledger symbol of V238-6 is delivered across the pair.

**Interfaces:**
- Consumes: from V238-4/V238-5 (same module) `CLAUSES`, `ADDITIVE_VERSION`, `split_additive`, `clause_own_expectancy`, `clause_win_rate_above_breakeven`, `clause_book_net_gain`, `clause_stability`, `_EPS`; from `acceptance` (exist, not edited) `AcceptanceResult(stage, verdict, clauses, strata, split, seed=42, version=VERSION, cluster="ticker", wr_statistic="standardised")`, `verdict_of(clauses, *, skipped_fails=False)` (a SKIPPED clause does not block), `stratum_table(baseline, component)`, `_Z_POWER = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}`, `render_json`.
- Produces (index ledger, final; Part 3 V238-7/V238-8 call these):
  - `STAGE_CLAUSES = {"selection": CLAUSES[:3], "walkforward": CLAUSES[3:], "validation": CLAUSES}`
  - `class AdditiveMisuse(ValueError)` with `.reason: str` (the `split_additive` reason, starting `ADDITIVE_GATE_MISUSE`)
  - `mde_own_expectancy(*, n, sd_r, power=0.80, alpha=ALPHA) -> float | None` = `(z(1 - alpha/2) + z(power)) × sd_r / sqrt(n)`; `None` when `n <= 0`; `ValueError` for a negative or non-finite `sd_r` or an untabulated `alpha`/`power`.
  - `STAGE0_REFUSAL = "refused:additive-mde"` (a new token; Part 3 prints the whole string, budget intact) and `stage0_refusal(*, n, expected_r, sd_r) -> str | None` — refused when `expected_r <= 0`, when `n <= 0`, or when the MDE **exceeds** `expected_r` (equal is not refused). `expected_r` is the frozen pre-registered own ExpR (already half the selected rung's net mean R); `n` is the count of added rows from a count-only pass; no R is read.
  - `evaluate_additive(baseline, component, *, stage, folds=None, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult` — `ValueError` for an unknown stage or a clause-4 stage without `folds`; raises `AdditiveMisuse` when the split is misuse; result has `cluster="week"`, `version=ADDITIVE_VERSION`, `split={"added": int, "displaced": int}`, verdict via `verdict_of` (clause 3 `SKIPPED` never blocks).

Stage 0 (index `## Decisions this index fixes`): the spread is frozen with the effect (`--expected-sd-r`, the selected ladder rung's per-event net R standard deviation), so Stage 0 never reads fold-train R. The z for a two-sided 95% interval is 1.9600, matching the gate's lower 95% bound; numpy only, so the quantiles are tabulated.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_acceptance_additive_evaluate.py`:

```python
"""v238 additive gate (v230 spec Part C): Stage 0 and evaluate_additive."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade, render_json

FAST = dict(n_resamples=300, seed=42)


def _row(ticker, r, *, day=0, year=2021, strategy="Turtle Soup", source="strategy"):
    entry = date(year, 1, 4) + timedelta(days=day)
    outcome = "win" if r > 0 else ("loss" if r < 0 else "scratch")
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source=source, direction="bullish")


def _baseline(weeks=20, year=2021):
    return [_row(f"B{w}", 1.0 if w % 2 else -1.0, day=7 * w, year=year,
                 strategy="RSI", source="confluence") for w in range(weeks)]


def _added(pattern, weeks=30, year=2021):
    return [_row(f"T{w}-{j}", r, day=7 * w, year=year)
            for w in range(weeks) for j, r in enumerate(pattern)]


PAYING = (2.2, -1.0, -1.0)     # own ExpR +0.067R every week, WR 33% vs break-even 31.25%
LOSING = (1.0, -1.0, -1.0)     # own ExpR -0.33R


def _fold(year, r=0.5, n=40):
    base = _baseline(5, year=int(year))
    return {"test_year": year, "baseline": base,
            "component": base + [_row(f"F{i}", r, day=7 * (i % 40), year=int(year))
                                 for i in range(n)]}


FOLDS = [_fold("2021"), _fold("2022"), _fold("2023")]


# --- Stage 0 --------------------------------------------------------------------------

def test_mde_is_the_two_sided_95_plus_power_z_over_root_n():
    assert aa.mde_own_expectancy(n=100, sd_r=1.0) == pytest.approx((1.96 + 0.8416) / 10.0)
    assert aa.mde_own_expectancy(n=400, sd_r=2.0) == pytest.approx((1.96 + 0.8416) / 10.0)


def test_mde_is_undefined_without_rows_and_refuses_bad_inputs():
    assert aa.mde_own_expectancy(n=0, sd_r=1.0) is None
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=-0.1)
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=float("nan"))
    with pytest.raises(ValueError):
        aa.mde_own_expectancy(n=100, sd_r=1.0, power=0.85)


def test_stage0_passes_when_the_frozen_effect_clears_the_mde():
    assert aa.stage0_refusal(n=100, expected_r=0.30, sd_r=1.0) is None


def test_stage0_passes_when_the_mde_equals_the_frozen_effect():
    mde = aa.mde_own_expectancy(n=100, sd_r=1.0)
    assert aa.stage0_refusal(n=100, expected_r=mde, sd_r=1.0) is None


def test_stage0_refuses_when_the_mde_exceeds_the_frozen_effect():
    refusal = aa.stage0_refusal(n=100, expected_r=0.25, sd_r=1.0)
    assert refusal.startswith(aa.STAGE0_REFUSAL)
    assert "exceeds" in refusal and "budget intact" in refusal


@pytest.mark.parametrize("n, expected_r", [(0, 0.30), (100, 0.0), (100, -0.1)])
def test_stage0_refuses_no_rows_or_a_non_positive_effect(n, expected_r):
    refusal = aa.stage0_refusal(n=n, expected_r=expected_r, sd_r=1.0)
    assert refusal.startswith(aa.STAGE0_REFUSAL)
    assert "budget intact" in refusal


# --- evaluate_additive ----------------------------------------------------------------

def test_stage_clauses_are_pinned():
    assert aa.STAGE_CLAUSES == {"selection": aa.CLAUSES[:3],
                                "walkforward": aa.CLAUSES[3:],
                                "validation": aa.CLAUSES}


def test_selection_runs_clauses_one_to_three_and_passes_a_paying_add():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="selection", **FAST)
    assert tuple(c.name for c in res.clauses) == aa.CLAUSES[:3]
    assert res.clause("book_net_gain").verdict == "SKIPPED"   # no displacement
    assert res.verdict == "PASS"
    assert (res.version, res.cluster, res.stage) == (1, "week", "selection")
    assert res.split == {"added": 90, "displaced": 0}
    assert render_json(res)["cluster"] == "week"


def test_a_losing_add_fails_selection():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(LOSING), stage="selection", **FAST)
    assert res.clause("own_expectancy").verdict == "FAIL"
    assert res.verdict == "FAIL"


def test_walkforward_runs_only_stability():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="walkforward",
                               folds=FOLDS, **FAST)
    assert tuple(c.name for c in res.clauses) == ("stability",)
    assert res.verdict == "PASS"


def test_validation_runs_all_four_clauses():
    base = _baseline()
    res = aa.evaluate_additive(base, base + _added(PAYING), stage="validation",
                               folds=FOLDS, **FAST)
    assert tuple(c.name for c in res.clauses) == aa.CLAUSES
    assert res.verdict == "PASS"


@pytest.mark.parametrize("stage", ["walkforward", "validation"])
def test_a_clause_four_stage_without_folds_is_refused(stage):
    base = _baseline()
    with pytest.raises(ValueError, match="needs folds"):
        aa.evaluate_additive(base, base + _added(PAYING), stage=stage, **FAST)


def test_an_unknown_stage_is_refused():
    base = _baseline()
    with pytest.raises(ValueError, match="stage must be one of"):
        aa.evaluate_additive(base, base + _added(PAYING), stage="mde", **FAST)


def test_misuse_raises_with_its_reason():
    base = _baseline()
    with pytest.raises(aa.AdditiveMisuse) as caught:
        aa.evaluate_additive(base, base[3:], stage="selection", **FAST)
    assert caught.value.reason.startswith(aa.ADDITIVE_GATE_MISUSE)
    assert isinstance(caught.value, ValueError)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_evaluate.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.acceptance_additive' has no attribute 'mde_own_expectancy'` (and likewise for the other new names).

- [ ] **Step 3: Extend the `acceptance` import at the top of `acceptance_additive.py`**

Replace V238-4's `from .acceptance import (...)` block with:

```python
from .acceptance import (
    ALPHA, BOOTSTRAP_RESAMPLES, CLOSED, DECIDED, AcceptanceResult, ClauseResult,
    _Z_POWER, expectancy_r, population_split, stratum_table, verdict_of, win_rate,
)
```

- [ ] **Step 4: Append Stage 0 and `evaluate_additive`**

Append after `clause_stability`:

```python
# --- Stage 0: the frozen-effect MDE precheck ------------------------------------------

#: Two-sided normal quantiles z(1 - alpha/2), tabulated (no scipy in the image).
_Z_TWO_SIDED = {0.05: 1.9600, 0.01: 2.5758, 0.10: 1.6449}
STAGE0_REFUSAL = "refused:additive-mde"


def mde_own_expectancy(*, n: int, sd_r: float, power: float = 0.80,
                       alpha: float = ALPHA) -> float | None:
    """Smallest own net ExpR the gate's lower 95% bound detects at ``power``
    with ``n`` added rows of per-row spread ``sd_r`` (frozen with the effect
    in the pre-registration, never read from fold-train)."""
    if sd_r is None or not np.isfinite(sd_r) or sd_r < 0:
        raise ValueError(f"sd_r must be a finite number >= 0, got {sd_r!r}")
    z_a, z_b = _Z_TWO_SIDED.get(alpha), _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    if n <= 0:
        return None
    return float((z_a + z_b) * sd_r / np.sqrt(n))


def stage0_refusal(*, n: int, expected_r: float, sd_r: float) -> str | None:
    """None when the shot may be spent; else the refusal line (budget intact).
    ``n`` is a count-only pass of added rows; no R is read here."""
    if expected_r <= 0:
        return (f"{STAGE0_REFUSAL} -- the frozen expected own ExpR {expected_r:+.4f}R "
                f"is not positive; budget intact")
    mde = mde_own_expectancy(n=n, sd_r=sd_r)
    if mde is None:
        return f"{STAGE0_REFUSAL} -- no added row to size (N={n}); budget intact"
    if mde > expected_r + _EPS:
        return (f"{STAGE0_REFUSAL} -- MDE {mde:.4f}R at N={n} exceeds the frozen "
                f"expected own ExpR {expected_r:.4f}R; budget intact")
    return None


# --- the gate -------------------------------------------------------------------------

STAGE_CLAUSES = {"selection": CLAUSES[:3], "walkforward": CLAUSES[3:],
                 "validation": CLAUSES}


class AdditiveMisuse(ValueError):
    """The component does not only add rows: it belongs to v72 or v92."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _clause_runners(baseline, component, split, folds, kw: dict) -> dict:
    return {
        CLAUSES[0]: lambda: clause_own_expectancy(split.added, **kw),
        CLAUSES[1]: lambda: clause_win_rate_above_breakeven(split.added, **kw),
        CLAUSES[2]: lambda: clause_book_net_gain(baseline, component, split, **kw),
        CLAUSES[3]: lambda: clause_stability(folds),
    }


def evaluate_additive(baseline, component, *, stage: str, folds=None,
                      n_resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = 42) -> AcceptanceResult:
    """The additive gate at one funnel stage. Every clause the stage reads
    must PASS; clause 3's SKIPPED (no displacement) never blocks."""
    if stage not in STAGE_CLAUSES:
        raise ValueError(f"stage must be one of {tuple(STAGE_CLAUSES)}, got {stage!r}")
    names = STAGE_CLAUSES[stage]
    if CLAUSES[3] in names and folds is None:
        raise ValueError(f"stage {stage!r} reads clause 4 and needs folds")
    split = split_additive(baseline, component)
    if split.misuse:
        raise AdditiveMisuse(split.misuse)
    runners = _clause_runners(baseline, component, split, folds,
                              {"n_resamples": n_resamples, "seed": seed})
    clauses = tuple(runners[name]() for name in names)
    return AcceptanceResult(stage=stage, verdict=verdict_of(clauses), clauses=clauses,
                            strata=stratum_table(baseline, component),
                            split={"added": len(split.added),
                                   "displaced": len(split.displaced)},
                            seed=seed, version=ADDITIVE_VERSION, cluster="week")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_evaluate.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive.py` and `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_book.py`
Expected: both still green.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function under 8).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/acceptance_additive.py tests/backtesting/test_acceptance_additive_evaluate.py
git commit -m "feat(backtesting): v238 additive gate -- Stage 0 MDE precheck and evaluate_additive"
```

### Task V238-6b: Additive disclosures (never gating)

**Model:** sonnet — six descriptive statistics with fixed definitions and hand-checkable fixtures; no gate decision.

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_additive.py` (extend the imports at the top; append after `evaluate_additive`, the last function V238-6 wrote)
- Test: `tests/backtesting/test_acceptance_additive_disclosures.py` (create; suite `backtesting-a-k`)

Second half of `SPLIT: V238-6 -> V238-6b`. Part 3 (V238-8) prints these lines in the additive results doc beside the clauses.

**Interfaces:**
- Consumes: from V238-4 (same module) `_EPS`, `_closed`; `instrument.stats.iso_week_key(entry_date) -> "YYYY-Www"`.
- Produces (index ledger row V238-6, final):
  - `disclosures(added, baseline) -> dict` with exactly the keys `max_drawdown_r` (float ≥ 0, R, over the closed added rows in `(entry_date, ticker)` order, equity starting at 0), `longest_losing_streak` (int, consecutive `loss` outcomes in that order), `top5_week_share` (sum of the five best ISO-week R sums over the added rows' total R; may exceed 1; `None` when the total is ≤ 0), `signals_per_day_p95` (float, linear-interpolated p95 of added rows per entry date; `None` with no added row), `signals_per_day_max` (int, `0` with no added row), `same_week_corr` (Pearson correlation of weekly added R sums with weekly baseline R sums over weeks both arms trade; `None` with fewer than 3 shared weeks or a constant series).
  - `render_disclosures(d) -> list[str]` — a heading line containing `never gating`, then five `- ` lines, `n/a` for `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_acceptance_additive_disclosures.py`:

```python
"""v238 additive gate disclosures (v230 spec Part C): reported, never gating."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade


def _row(ticker, r, *, day=0, strategy="Turtle Soup"):
    entry = date(2021, 1, 4) + timedelta(days=day)          # a Monday
    outcome = "win" if r > 0 else ("loss" if r < 0 else "scratch")
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source="strategy", direction="bullish")


def _sequence():
    # in (date, ticker) order: +2 -1 -1 -1 +3 -1 -> equity 2 1 0 -1 2 1
    return [_row("T1", 2.0, day=0), _row("T2", -1.0, day=0), _row("T3", -1.0, day=1),
            _row("T4", -1.0, day=7), _row("T5", 3.0, day=7), _row("T6", -1.0, day=7)]


def test_disclosure_keys_are_pinned():
    assert set(aa.disclosures(_sequence(), [])) == {
        "max_drawdown_r", "longest_losing_streak", "top5_week_share",
        "signals_per_day_p95", "signals_per_day_max", "same_week_corr"}


def test_drawdown_streak_and_signals_per_day():
    d = aa.disclosures(list(reversed(_sequence())), [])   # input order does not matter
    assert d["max_drawdown_r"] == pytest.approx(3.0)
    assert d["longest_losing_streak"] == 3
    assert d["signals_per_day_max"] == 3                   # day 7
    assert d["signals_per_day_p95"] == pytest.approx(2.9)  # counts 2, 1, 3
    assert d["top5_week_share"] == pytest.approx(1.0)      # weeks sum 0 and +1


def test_unclosed_rows_count_as_signals_but_not_in_r():
    rows = _sequence() + [ArmTrade(ticker="T9", strategy="Turtle Soup", horizon_key="4w",
                                   entry_date="2021-01-11", outcome="not_triggered",
                                   r_multiple=None, planned_rr=2.0)]
    d = aa.disclosures(rows, [])
    assert d["signals_per_day_max"] == 4
    assert d["max_drawdown_r"] == pytest.approx(3.0)


def test_top5_week_share_can_exceed_one_and_is_undefined_without_profit():
    weekly = [5.0, 4.0, 3.0, 2.0, 1.0, -1.0, -4.0]
    rows = [_row(f"T{w}", r, day=7 * w) for w, r in enumerate(weekly)]
    assert aa.disclosures(rows, [])["top5_week_share"] == pytest.approx(15.0 / 10.0)
    losing = [_row(f"T{w}", -1.0, day=7 * w) for w in range(4)]
    assert aa.disclosures(losing, [])["top5_week_share"] is None


def test_same_week_correlation_uses_shared_weeks_only():
    added = [_row(f"T{w}", float(w + 1), day=7 * w) for w in range(5)]
    base = [_row(f"B{w}", 2.0 * (w + 1), day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures(added, base)["same_week_corr"] == pytest.approx(1.0)
    assert aa.disclosures(added, base[:2])["same_week_corr"] is None      # 2 shared weeks
    flat = [_row(f"B{w}", 1.0, day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures(added, flat)["same_week_corr"] is None          # constant


def test_empty_added_rows_disclose_zeros_and_none():
    base = [_row(f"B{w}", 1.0, day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures([], base) == {
        "max_drawdown_r": 0.0, "longest_losing_streak": 0, "top5_week_share": None,
        "signals_per_day_p95": None, "signals_per_day_max": 0, "same_week_corr": None}


def test_render_disclosures_says_never_gating_and_prints_na():
    lines = aa.render_disclosures(aa.disclosures([], []))
    assert len(lines) == 6
    assert "never gating" in lines[0]
    assert all(line.startswith("- ") for line in lines[1:])
    assert "n/a" in lines[3] and "n/a" in lines[4] and "n/a" in lines[5]
    full = aa.render_disclosures(aa.disclosures(_sequence(), []))
    assert "3.00R" in full[1]
    assert "100.0%" in full[3]
    assert "p95 2.9, max 3" in full[4]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_disclosures.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.acceptance_additive' has no attribute 'disclosures'`.

- [ ] **Step 3: Extend the imports at the top of `acceptance_additive.py`**

Add `from collections import Counter, defaultdict` above `from dataclasses import dataclass`, and replace the `instrument.stats` import line with:

```python
from .instrument.stats import iso_week_key, week_cluster_bootstrap
```

- [ ] **Step 4: Append the disclosures**

Append after `evaluate_additive`:

```python
# --- disclosures (never gating) -------------------------------------------------------

def _ordered(rows) -> list:
    return sorted(_closed(rows), key=lambda t: (str(t.entry_date)[:10], t.ticker))


def _max_drawdown(rs) -> float:
    peak = equity = worst = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return float(worst)


def _longest_losing_streak(rows) -> int:
    best = run = 0
    for trade in rows:
        run = run + 1 if trade.outcome == "loss" else 0
        best = max(best, run)
    return best


def _week_sums(rows) -> dict:
    out = defaultdict(float)
    for trade in _closed(rows):
        out[iso_week_key(trade.entry_date)] += trade.r_multiple
    return dict(out)


def _top5_week_share(rows) -> float | None:
    sums = _week_sums(rows)
    total = sum(sums.values())
    if total <= _EPS:
        return None
    return float(sum(sorted(sums.values(), reverse=True)[:5]) / total)


def _signals_per_day(rows) -> tuple:
    counts = list(Counter(str(t.entry_date)[:10] for t in rows).values())
    if not counts:
        return None, 0
    return float(np.percentile(counts, 95)), int(max(counts))


def _same_week_corr(added, baseline) -> float | None:
    a, b = _week_sums(added), _week_sums(baseline)
    weeks = sorted(set(a) & set(b))
    if len(weeks) < 3:
        return None
    x = np.array([a[w] for w in weeks])
    y = np.array([b[w] for w in weeks])
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def disclosures(added, baseline) -> dict:
    """Spec Part C disclosures for the results doc. None of them gates."""
    ordered = _ordered(added)
    p95, peak = _signals_per_day(added)
    return {"max_drawdown_r": _max_drawdown([t.r_multiple for t in ordered]),
            "longest_losing_streak": _longest_losing_streak(ordered),
            "top5_week_share": _top5_week_share(added),
            "signals_per_day_p95": p95, "signals_per_day_max": peak,
            "same_week_corr": _same_week_corr(added, baseline)}


def _fmt(value, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def render_disclosures(d: dict) -> list:
    return [
        "Disclosures (never gating):",
        f"- Max drawdown of the added rows: {_fmt(d['max_drawdown_r'], '.2f')}R",
        f"- Longest losing streak: {d['longest_losing_streak']}",
        f"- Share of the added rows' total R from the five best weeks: "
        f"{_fmt(d['top5_week_share'], '.1%')}",
        f"- Signals per day: p95 {_fmt(d['signals_per_day_p95'], '.1f')}, "
        f"max {d['signals_per_day_max']}",
        f"- Same-week correlation of added R with the baseline book: "
        f"{_fmt(d['same_week_corr'], '+.2f')}",
    ]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_disclosures.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_additive_evaluate.py`
Expected: still green.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function under 5).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/acceptance_additive.py tests/backtesting/test_acceptance_additive_disclosures.py
git commit -m "feat(backtesting): v238 additive gate -- never-gating disclosures"
```

