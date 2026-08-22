Version: ui 1.8.0 · bot 1.3.2
Spec: docs/superpowers/specs/2026-08-22-v49-effective-confluence-design.md
Bump: bot minor (1.3.2 → 1.4.0) — changes what `count_confirming_strategies`
returns for every scenario, moving both the `MIN_TARGET_CONFLUENCE_COUNT` gate
and the confidence base level. Observably different alert stream. `ui` none.
Edge: expectancy — removes a negative-expectancy population (scenarios whose
confluence count is inflated by redundant detectors).
Origin: EXTERNAL — HKUDS/Vibe-Trading, read 2026-08-22 from
`C:\Users\HuyCao\Downloads\Vibe-Trading-main`. Reduction adapted from
`agent/backtest/regime.py`; permutation control from
`agent/src/factors/bench_runner_strict.py`. Not measured on this repo's data
before adoption. **Revert lever:** `EFFECTIVE_CONFLUENCE_ENABLED = false` —
see "Reverting" below.

# Effective confluence count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discount the confluence count by measured inter-family redundancy, so
that six price-envelope detectors landing on one price count as the two-ish
independent observations they are rather than six. Ship dark, then spend one
pre-registered VALIDATION shot.

**Architecture:** One new pure-arithmetic module (`edge/confluence.py`) holding
the participation-ratio reduction and a frozen 12×12 redundancy matrix; one new
config Field; a three-line change at the tail of
`levels.count_confirming_strategies`. Two scripts that never ship: the matrix
measurement and the pre-registration harness.

**Tech Stack:** numpy, pandas, pytest. No new dependency.

## Global Constraints

- **`N_eff <= N` always.** The gate can only tighten. If any code path can
  produce `N_eff > N`, that is a bug, not a tuning choice — the whole safety
  argument for spending a validation shot rests on this.
- **Nothing is fitted at scan time.** `swingbot/` imports no estimator and reads
  no data file for the matrix. The matrix is a literal constant in the module,
  with the measuring commit hash in a comment beside it.
- **The new config `Field` must also be added to `.env.example`**, or
  `tests/test_env_example_sync.py` fails.
- **The flag check sits OUTSIDE any `try`**, following `levels.py:352`'s
  `AVWAP_LEVELS_ENABLED` precedent — a renamed Field must fail loudly, not
  silently disable the component forever.
- **Slot 1 of the return tuple is untouched.** `count_confirming_strategies`
  returns `(count, family_names)`; only slot 0 changes. `embeds.py:209`,
  `engine.py:1126` and the charts all read slot 1 and must be byte-identical
  with the flag on and off.
- **The replay harness cannot see this component.** `run_backtest_range.py`
  never calls `scanning/engine.py` — the trap v34's RS gate hit. Task 6
  confirms this before any measurement is trusted; do not inherit the
  assumption.
- **Do not touch the pre-registration once Phase 4 starts.** The grid, the
  permutation rule and the VALIDATION clauses are frozen by the spec. A
  failure closes the component.
- Verify with `python scripts/dev/testrun.py file <test file>` while iterating;
  `test-runner` subagent for the full suite. Green means `0 failed` **and**
  `0 xfailed`. Touching the scan pipeline makes `fast` auto-escalate.

---

# Phase 1 — The reduction

### Task 1: Participation-ratio reduction

**Files:**
- Create: `swingbot/core/edge/confluence.py`
- Test: `tests/edge/test_confluence_reduction.py`

**Interfaces:**
- Consumes: `levels.ALL_STRATEGY_FAMILIES` (for index order only).
- Produces: `FAMILY_ORDER: tuple[str, ...]`,
  `effective_count(families: Sequence[str], matrix: Sequence[Sequence[float]] | None = None) -> float`,
  `effective_count_int(families, matrix=None) -> int`.

The matrix constant lands in Task 4; until then `matrix=None` must raise rather
than default to something plausible. A silent identity default would make every
test in this task pass against a component that does nothing.

- [ ] **Step 1: Write the failing test**

Create `tests/edge/test_confluence_reduction.py`:

```python
"""Participation-ratio reduction: N_eff = N^2 / sum(R[i][j]) over present families.

Pure arithmetic over hand-built matrices -- no market data, no config, no I/O.
"""
from __future__ import annotations

import math

import pytest

from swingbot.core.edge import confluence
from swingbot.core.market import levels


def _identity(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _ones(n: int) -> list[list[float]]:
    return [[1.0] * n for _ in range(n)]


def test_family_order_matches_levels_exactly():
    # An ordering drift here silently mislabels every weight in the matrix.
    assert list(confluence.FAMILY_ORDER) == list(levels.ALL_STRATEGY_FAMILIES)


def test_independent_families_give_neff_equal_n():
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:5])
    assert confluence.effective_count(fams, m) == pytest.approx(5.0)


def test_perfectly_redundant_families_collapse_to_one():
    m = _ones(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:5])
    assert confluence.effective_count(fams, m) == pytest.approx(1.0)


def test_half_redundant_pair_lands_between():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    m[0][1] = m[1][0] = 0.5
    fams = list(confluence.FAMILY_ORDER[:2])
    # 4 / (1 + 0.5 + 0.5 + 1) = 1.333...
    assert confluence.effective_count(fams, m) == pytest.approx(4.0 / 3.0)


@pytest.mark.parametrize("k", [0, 1])
def test_degenerate_counts_are_identity(k):
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:k])
    assert confluence.effective_count(fams, m) == pytest.approx(float(k))


def test_neff_never_exceeds_n_over_random_matrices():
    # The safety property the whole plan rests on.
    import random
    rng = random.Random(11)
    n = len(confluence.FAMILY_ORDER)
    for _ in range(200):
        m = _identity(n)
        for i in range(n):
            for j in range(i + 1, n):
                v = rng.random()
                m[i][j] = m[j][i] = v
        k = rng.randint(1, n)
        fams = list(confluence.FAMILY_ORDER[:k])
        neff = confluence.effective_count(fams, m)
        assert 1.0 - 1e-9 <= neff <= k + 1e-9


def test_reduction_is_order_free():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    m[0][3] = m[3][0] = 0.7
    m[1][3] = m[3][1] = 0.2
    a = confluence.effective_count([confluence.FAMILY_ORDER[i] for i in (0, 1, 3)], m)
    b = confluence.effective_count([confluence.FAMILY_ORDER[i] for i in (3, 0, 1)], m)
    assert a == pytest.approx(b)


def test_unknown_family_raises():
    m = _identity(len(confluence.FAMILY_ORDER))
    with pytest.raises(ValueError, match="unknown family"):
        confluence.effective_count(["Not A Family"], m)


def test_duplicate_families_are_collapsed():
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = [confluence.FAMILY_ORDER[0], confluence.FAMILY_ORDER[0]]
    assert confluence.effective_count(fams, m) == pytest.approx(1.0)


def test_missing_matrix_raises_rather_than_defaulting():
    # Until Task 4 lands the constant there is no safe default: an implicit
    # identity would make this component a no-op that still passes its tests.
    with pytest.raises(ValueError, match="no redundancy matrix"):
        confluence.effective_count([confluence.FAMILY_ORDER[0]], None)


def test_int_form_floors_rather_than_rounds():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    # Three families, one near-redundant pair -> N_eff just under 3.
    m[0][1] = m[1][0] = 0.001
    fams = list(confluence.FAMILY_ORDER[:3])
    assert confluence.effective_count(fams, m) < 3.0
    assert confluence.effective_count_int(fams, m) == 2
```

- [ ] **Step 2: Implement**

Create `swingbot/core/edge/confluence.py`:

```python
"""Effective confluence count: how many INDEPENDENT votes a set of confirming
strategy families actually represents.

`levels.count_confirming_strategies` counts families. EMA, VWAP, AVWAP,
Bollinger Bands, Donchian Channel and Rolling S/R are all moving-window
derivations of the same close series; Fibonacci, Zigzag Pivot and Floor Pivot
are all swing-extreme derivations of the same pivots. Several co-locate by
construction rather than by corroboration, so a raw count of 5 can be two
observations wearing five hats.

The reduction is the participation ratio -- the effective number of
independent bets:

    N_eff = N^2 / sum_{i,j in F} R[i][j]

R is a symmetric matrix of measured co-occurrence probabilities with a unit
diagonal (Task 4). Independent families give N_eff = N; perfectly redundant
ones give N_eff = 1; and 1 <= N_eff <= N always, which is why wiring this in
can only ever TIGHTEN the gate.

Transparent arithmetic, no fitted object at runtime: the matrix is a frozen
constant measured once on TRAIN, so the fold harness can audit it.
"""
from __future__ import annotations

import math
from typing import Sequence

from swingbot.core.market.levels import ALL_STRATEGY_FAMILIES

FAMILY_ORDER: tuple[str, ...] = tuple(ALL_STRATEGY_FAMILIES)
_INDEX = {name: i for i, name in enumerate(FAMILY_ORDER)}


def effective_count(families: Sequence[str],
                    matrix: Sequence[Sequence[float]] | None = None) -> float:
    """Effective (redundancy-discounted) number of confirming families.

    `matrix` defaults to the frozen `REDUNDANCY` constant once Task 4 lands.
    Passing None before then raises -- an implicit identity default would turn
    this whole component into a silent no-op.
    """
    if matrix is None:
        matrix = globals().get("REDUNDANCY")
    if matrix is None:
        raise ValueError("no redundancy matrix available")

    seen: list[int] = []
    for name in families:
        if name not in _INDEX:
            raise ValueError(f"unknown family: {name!r}")
        idx = _INDEX[name]
        if idx not in seen:
            seen.append(idx)

    n = len(seen)
    if n <= 1:
        return float(n)

    total = 0.0
    for i in seen:
        for j in seen:
            total += float(matrix[i][j])
    if total <= 0.0:
        raise ValueError("redundancy matrix produced a non-positive denominator")
    return (n * n) / total


def effective_count_int(families: Sequence[str],
                        matrix: Sequence[Sequence[float]] | None = None) -> int:
    """`effective_count` floored to the integer the scan pipeline consumes.

    FLOOR, not round, and pre-registered as such: the gate fails closed, so a
    scenario at 2.9 effective votes has not earned a 3.
    """
    return int(math.floor(effective_count(families, matrix) + 1e-9))
```

- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/edge/test_confluence_reduction.py`

---

### Task 2: Matrix invariant guard

**Files:**
- Create: `tests/edge/test_confluence_matrix.py`

**Interfaces:**
- Consumes: `confluence.REDUNDANCY` (lands in Task 4), `confluence.FAMILY_ORDER`.
- Produces: nothing.

Written now, expected to fail until Task 4. It is the guard that stops a
hand-pasted constant from drifting: wrong shape, asymmetry, an out-of-range
entry or a reordered family list are all silent mislabellings, not crashes.

- [ ] **Step 1: Write the test (red until Task 4)**

```python
"""Invariants the frozen redundancy matrix must satisfy.

These are not style checks. The matrix is pasted by hand from a measurement
script; every failure mode here mislabels weights silently rather than
raising, so it has to be asserted.
"""
from __future__ import annotations

import pytest

from swingbot.core.edge import confluence
from swingbot.core.market import levels


@pytest.fixture()
def m():
    return confluence.REDUNDANCY


def test_shape_is_square_and_matches_family_count(m):
    n = len(levels.ALL_STRATEGY_FAMILIES)
    assert len(m) == n
    assert all(len(row) == n for row in m)


def test_family_order_is_element_for_element(m):
    assert list(confluence.FAMILY_ORDER) == list(levels.ALL_STRATEGY_FAMILIES)


def test_diagonal_is_unit(m):
    for i in range(len(m)):
        assert m[i][i] == pytest.approx(1.0)


def test_symmetric(m):
    for i in range(len(m)):
        for j in range(len(m)):
            assert m[i][j] == pytest.approx(m[j][i]), f"asymmetry at ({i},{j})"


def test_every_entry_is_a_probability(m):
    for row in m:
        for v in row:
            assert 0.0 <= v <= 1.0


def test_provenance_comment_present():
    # The measuring commit must be recoverable from the source, or the
    # constant is unauditable.
    import inspect
    src = inspect.getsource(confluence)
    assert "measured-on:" in src, "REDUNDANCY needs a `measured-on:` provenance comment"
```

- [ ] **Step 2: Verify it fails for the right reason** — `AttributeError: REDUNDANCY`, not a shape error.

---

# Phase 2 — Measuring the matrix

### Task 3: The measurement script

**Files:**
- Create: `scripts/backtest/measure_confluence_redundancy.py`
- Test: `tests/scripts/test_measure_confluence_redundancy.py`

**Interfaces:**
- Consumes: `levels.collect_candidate_levels`, `levels.strategy_family`,
  `config.CONFLUENCE_DEVIATION_PCT`, the CSV cache from
  `scripts/data/fetch_backtest_data.py`.
- Produces: a printed Python literal ready to paste into `confluence.py`, plus
  `docs/superpowers/results/2026-08-XX-confluence-redundancy.md`.

**What it measures.** For every (ticker, horizon, bar) in TRAIN
(2020-01-01…2023-12-31), run `collect_candidate_levels`, fold labels to
families, and for every candidate price count which families land within
`CONFLUENCE_DEVIATION_PCT` of it. That yields a co-occurrence tally
`C[i][j]` = times `j` landed given `i` landed, and `C[i][i]` = times `i`
landed. Then `R[i][j] = (C[i][j]/C[i][i] + C[j][i]/C[j][j]) / 2`, symmetrised.

**Progress output is mandatory.** This is a multi-ticker sweep and the repo's
rule is one flushed line per unit of work before it is ever backgrounded —
`print(f"[{n}/{total}] {ticker} {horizon} pairs={pairs}", flush=True)` per
ticker-horizon. Confirm it prints before kicking anything off.

- [ ] **Step 1: Write the failing test** — the tally→matrix arithmetic only,
  over a hand-built tally. Do not test the sweep; it needs the CSV cache.

```python
"""Tally -> symmetric redundancy matrix. Pure arithmetic, no data."""
from __future__ import annotations

import pytest

from scripts.backtest.measure_confluence_redundancy import tally_to_matrix


def test_unit_diagonal():
    tally = {(0, 0): 100, (1, 1): 50}
    m = tally_to_matrix(tally, n=2)
    assert m[0][0] == pytest.approx(1.0)
    assert m[1][1] == pytest.approx(1.0)


def test_symmetrised_conditional():
    # 0 landed 100x, 1 landed 50x, they co-occurred 25x.
    tally = {(0, 0): 100, (1, 1): 50, (0, 1): 25, (1, 0): 25}
    m = tally_to_matrix(tally, n=2)
    # (25/100 + 25/50) / 2 = (0.25 + 0.5) / 2 = 0.375
    assert m[0][1] == pytest.approx(0.375)
    assert m[1][0] == pytest.approx(0.375)


def test_never_observed_family_gets_zero_offdiagonal_and_unit_diagonal():
    # A family that never fired must not poison the matrix with a divide-by-zero
    # or an implicit 1.0 -- it is simply uninformative.
    tally = {(0, 0): 10, (1, 1): 0}
    m = tally_to_matrix(tally, n=2)
    assert m[1][1] == pytest.approx(1.0)
    assert m[0][1] == pytest.approx(0.0)


def test_entries_stay_in_unit_interval():
    tally = {(0, 0): 10, (1, 1): 10, (0, 1): 10, (1, 0): 10}
    m = tally_to_matrix(tally, n=2)
    for row in m:
        for v in row:
            assert 0.0 <= v <= 1.0
```

- [ ] **Step 2: Implement `tally_to_matrix`, then the sweep around it.**
- [ ] **Step 3: Verify** — `python scripts/dev/testrun.py file tests/scripts/test_measure_confluence_redundancy.py`

---

### Task 4: Run the sweep, freeze the constant

**Files:**
- Modify: `swingbot/core/edge/confluence.py` (add `REDUNDANCY`)
- Create: `docs/superpowers/results/2026-08-XX-confluence-redundancy.md`

- [ ] **Step 1:** Ensure the CSV cache exists (`python scripts/data/fetch_backtest_data.py`).
- [ ] **Step 2:** Run the sweep. Dispatch the `backtest-runner` subagent — this
  is a multi-ticker × multi-horizon pass and its per-ticker output must not
  reach the controlling context. Per the repo's subagent rule, it keeps a
  plain-text progress file updated at each real milestone, not once at the start.
- [ ] **Step 3:** Paste the 12×12 literal into `confluence.py` under a
  `# measured-on: <commit-sha> TRAIN 2020-01-01..2023-12-31` comment.
- [ ] **Step 4:** `python scripts/dev/testrun.py file tests/edge/test_confluence_matrix.py` — Task 2's guard must now go green.
- [ ] **Step 5:** Write the results doc: the matrix, the N behind each cell, and
  an honest observations section. **If the matrix comes back near-identity**
  (every off-diagonal < 0.15), the mechanism's premise is false — the families
  are already independent, there is nothing to discount, and the correct
  outcome is to record that and stop. That is a finished measurement, not a
  failed task; do not proceed to Phase 3 to salvage it.

---

# Phase 3 — Wiring

### Task 5: Config Field and the `levels.py` seam

**Files:**
- Modify: `swingbot/config.py` (new Field; fix the stale "10 total" help text)
- Modify: `swingbot/core/market/levels.py` (`count_confirming_strategies` tail)
- Modify: `.env.example`
- Test: `tests/market/test_effective_confluence_wiring.py`

**Interfaces:**
- Consumes: `confluence.effective_count_int`, `config.EFFECTIVE_CONFLUENCE_ENABLED`.
- Produces: unchanged `(count, families)` tuple shape.

**Drive-by, same commit:** `config.py:172-173`'s help text for
`MIN_TARGET_CONFLUENCE_COUNT` enumerates the families and says "10 total".
`ALL_STRATEGY_FAMILIES` has held **12** since AVWAP (v35) and Volume Profile
were added. It is user-visible on the Settings page.

- [ ] **Step 1: Write the failing test**

```python
"""Flag-off equivalence, flag-on discounting, and slot-1 stability."""
from __future__ import annotations

import pytest

from swingbot import config
from swingbot.core.market import levels


@pytest.fixture()
def scenario(monkeypatch):
    """A target that four families confirm, two of them near-redundant."""
    fams = ["EMA", "VWAP", "Fibonacci", "Donchian Channel"]
    monkeypatch.setattr(levels, "collect_candidate_levels",
                        lambda df, h, price: [(100.0, f) for f in fams])
    monkeypatch.setattr(config, "CONFLUENCE_DEVIATION_PCT", 5.0)
    return fams


def test_flag_off_returns_raw_family_count(monkeypatch, scenario):
    monkeypatch.setattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", False)
    count, families = levels.count_confirming_strategies(None, {}, 99.0, 100.0, 5.0)
    assert count == 4
    assert families == sorted(scenario)


def test_flag_on_never_exceeds_raw_count(monkeypatch, scenario):
    monkeypatch.setattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", True)
    count, _ = levels.count_confirming_strategies(None, {}, 99.0, 100.0, 5.0)
    assert 1 <= count <= 4


def test_family_list_is_identical_with_flag_on_and_off(monkeypatch, scenario):
    monkeypatch.setattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", False)
    _, off = levels.count_confirming_strategies(None, {}, 99.0, 100.0, 5.0)
    monkeypatch.setattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", True)
    _, on = levels.count_confirming_strategies(None, {}, 99.0, 100.0, 5.0)
    assert off == on, "slot 1 feeds embeds and charts; it must not move"


def test_no_target_price_still_short_circuits(monkeypatch):
    monkeypatch.setattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", True)
    assert levels.count_confirming_strategies(None, {}, 99.0, 0.0, 5.0) == (0, [])


def test_missing_field_raises_loudly(monkeypatch, scenario):
    # The levels.py:352 precedent: a renamed Field must not silently disable
    # the component forever.
    monkeypatch.delattr(config, "EFFECTIVE_CONFLUENCE_ENABLED", raising=False)
    with pytest.raises(AttributeError):
        levels.count_confirming_strategies(None, {}, 99.0, 100.0, 5.0)
```

- [ ] **Step 2: Implement.** Replace the tail of `count_confirming_strategies`
  (`levels.py:496`) — the flag read stays outside any `try`:

```python
    names = sorted(families)
    if config.EFFECTIVE_CONFLUENCE_ENABLED:
        from swingbot.core.edge import confluence
        return confluence.effective_count_int(names), names
    return len(names), names
```

- [ ] **Step 3:** Add the Field to `config.py` (`type="bool"`, `default="false"`,
  section `"Trade Filters & Risk"`), the matching line to `.env.example`, and fix
  the "10 total" string.
- [ ] **Step 4: Verify** — the new test file, plus
  `tests/test_env_example_sync.py` and `tests/test_config_flags.py`.

---

### Task 6: Confirm the measurement instrument

**Files:**
- Create: `scripts/backtest/measure_effective_confluence.py`
- Test: `tests/scripts/test_measure_effective_confluence.py`

**Do this before trusting any number.** v34's RS gate was invisible to
`run_backtest_range.py` because the replay harness never calls
`scanning/engine.py`, and the gate had to be measured with a purpose-built
instrument. Assume the same here and *verify it*:

- [ ] **Step 1:** Run `run_backtest_range.py --train` with
  `EFFECTIVE_CONFLUENCE_ENABLED` on and off. If the two runs are byte-identical,
  the harness cannot see the component — confirmed, proceed to Step 2. If they
  differ, record that the replay harness *does* reach this seam and say so in
  the results doc; the purpose-built script is then a cross-check rather than
  the only instrument.
- [ ] **Step 2:** Build the script so it drives `scanning/engine.py` directly
  over the TRAIN window and emits, per (strategy, horizon) cell: `n`,
  `win_rate`, `expectancy_r`, alert count, and the mean `N_eff − N` gap.
- [ ] **Step 3:** One flushed progress line per ticker-horizon.
- [ ] **Step 4: Verify** the aggregation arithmetic on a fixture trade list.

---

# Phase 4 — Pre-registration

**Frozen by the spec. Do not adjust a threshold, widen the grid, or re-run a
failed clause.**

### Task 7: TRAIN grid

**Files:**
- Create: `docs/superpowers/results/2026-08-XX-effective-confluence-train.md`

- [ ] **Step 1:** Three cells only —
  `MIN_TARGET_CONFLUENCE_COUNT ∈ {2, 3}` × `EFFECTIVE_CONFLUENCE_ENABLED = true`,
  plus the single baseline (`false`, `MIN = 2`, the shipped default).
- [ ] **Step 2:** Dispatch `backtest-runner`. Progress file updated at each
  milestone, including before it waits on its own sweep.
- [ ] **Step 3:** Record the full table and quote the selection rule verbatim
  before reading the numbers.

### Task 8: Fold gate

- [ ] **Step 1:** `backtest_wf.run_folds` with the winning override, against the
  unchanged `ANCHORED_FOLDS`.
- [ ] **Step 2:** Gate: `GATE_MIN_IMPROVING_FOLDS = 2`,
  `GATE_MAX_DEGRADATION_R = 0.05`, `GATE_MIN_N_PER_FOLD = 30`. A fail closes the
  component — append the result to the TRAIN doc and stop.

### Task 9: Permutation control

**Files:**
- Modify: `scripts/backtest/measure_effective_confluence.py` (`--permute K --seed S`)

The clause that separates this from a fitted result. Our gates are all
zero-benchmarked; this one is not.

- [ ] **Step 1:** Permute the family labels of the frozen matrix — family `i`
  inherits family `π(i)`'s row *and* column, preserving symmetry, the unit
  diagonal and the whole distribution of values. Assert those three properties
  hold for every draw before using it.
- [ ] **Step 2:** `K = 200`, seed recorded. Recompute `N_eff` for every scenario
  and re-run the identical TRAIN measurement per draw.
- [ ] **Step 3: Rule** — the real matrix's pooled ΔExpR must exceed the **95th
  percentile** of the 200 permuted ΔExpR values. Below it, the component is
  closed: the structure carried no information and the TRAIN result was
  selection luck. Record the full percentile ladder either way.

### Task 10: VALIDATION — one shot

- [ ] **Step 1:** Only if Tasks 7–9 all cleared. One run, 2024-01-01…2025-12-31,
  pooled over the confluence-scan population.
- [ ] **Step 2:** All four clauses, pre-registered, no substitutions:
  1. `expectancy_r` strictly greater than the `false` arm's, and `> 0` absolute;
  2. `win_rate >= 50`;
  3. `N >= 15`;
  4. alert-count reduction `<= 25%` vs the `false` arm.
- [ ] **Step 3:** Record as-is in
  `docs/superpowers/results/2026-08-XX-effective-confluence-validation.md`,
  including the permutation percentiles. Failures are recorded, not fixed.
- [ ] **Step 4:** On a pass, flip the default to `true`; on a fail, leave it
  `false` and say in the config help text that the component was measured and
  did not clear.

### Task 11: Close-out

- [ ] **Step 1:** Full suite via the `test-runner` subagent. `0 failed`, `0 xfailed`.
- [ ] **Step 2:** `VERSION.json` bot bump **only if the default flipped** — a
  component that ships dark and stays dark is not an observable difference.
  Then regenerate and commit `version_history.json` in the same commit; the
  local gate runs before the bump and structurally cannot catch a miss.
- [ ] **Step 3:** Amend the `Bump:`/`Edge:` header lines if the prediction came
  out wrong, with one clause saying why.
- [ ] **Step 4:** `git mv` this plan and its spec into `implemented/`, then
  remove the worktree and delete its branch with `git branch -d` (never `-D`,
  and never any branch matching `backup*` or `stable-*`).

---

## Reverting

This plan is the only one of the four Vibe-Trading-derived documents that can
change trading behaviour, so the back-out path is stated rather than assumed.

**The lever is one flag.** `EFFECTIVE_CONFLUENCE_ENABLED = false` restores the
pre-v49 alert stream exactly: `count_confirming_strategies` returns
`len(families)` again, the `MIN_TARGET_CONFLUENCE_COUNT` gate and the confidence
base level move back with it, and slot 1 of the return tuple never changed in
either state. `.env` is hot-reloaded via SIGHUP, so the flip needs no redeploy.

**Nothing else has to be undone.** There is no data migration, no persisted
file, and no schema change — `edge/confluence.py` and the frozen matrix simply
stop being called. Leaving the dead code in place is the *preferred* revert: it
keeps the measurement reproducible and stops a future session re-deriving the
same idea from scratch.

**What to watch after a default flip.** The four VALIDATION clauses are the same
things to re-check live: pooled `expectancy_r`, `win_rate`, `N`, and alert
volume against the pre-flip baseline. The volume guard (`<= 25%` reduction) is
the one most likely to bite in production, because live universe composition
differs from the backtest universe.

**If it is reverted, say so in the document.** Amend the `Bump:` and `Edge:`
header lines with one clause explaining what the live numbers did, then move the
plan to `implemented/` — which deliberately holds rolled-back work alongside
finished work. A reverted plan that still reads as shipped is the failure mode
`docs/claude/document-conventions.md` warns about.

---

## Parallelisation

- **Group 1 (parallel):** Task 1 and Task 3 — `edge/confluence.py` and
  `scripts/backtest/measure_confluence_redundancy.py`, disjoint files. The
  reduction's contract (`effective_count(families, matrix) -> float`) is fixed
  by the spec, so neither has to wait to learn it from the other.
- **Task 2 alongside Group 1** — it is a new test file that touches nothing
  else, and it is *meant* to be red until Task 4.
- **Sequential:** Task 4 after Task 3 (the constant is that script's output).
  Task 5 after Task 4 (it consumes the constant). Task 6 after Task 5 (it
  measures the wired seam).
- **Sequential throughout Phase 4:** each task is gated on the previous one
  clearing. Running the VALIDATION shot before the permutation control spends
  the one-shot budget on a component that has not earned it, and the budget does
  not refill.
- **A second reason Task 5 is one task, not three:** `levels.py`, `config.py`
  and `.env.example` must move together, and this working tree is shared with
  concurrent sessions — two agents on `levels.py` overwrite rather than merge.
