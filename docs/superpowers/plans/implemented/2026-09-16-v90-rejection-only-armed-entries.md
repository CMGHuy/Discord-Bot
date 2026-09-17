# v90 Rejection-Only Armed Entries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-16-v90-rejection-only-armed-entries-design.md`
**Bump:** none
**Edge:** expectancy

**Goal:** Re-measure armed confluence entries under the v72 funnel with one mechanism change — only a rejection (R1) confirms an arm, while a follow-through (R2) or reclaim (R3) abandons it — and record the verdict whatever it is.

**Architecture:** v88 already built every moving part; this plan changes three things inside them. `walk_arm` (`core/backtesting/armed_replay.py`) stops confirming on any reaction and confirms only R1, returning two new named cancels otherwise. The `mode` axis disappears from `Cell` and with it `plan_at`'s market-entry branch, since `M2` existed only to give R2/R3 a market fill. `armed_measurement.py`'s grid drops `MODES` and refines `B_GRID` to five 0.05-ATR steps so the 0.03R plateau check can actually pass or fail on merit. Code lands on a worktree branch and merges; the runs and results docs are committed on `main`.

**Tech Stack:** Python 3.11, numpy, pandas, pytest; existing `acceptance.py`, `backtest_wf.plateau_report`, `backtest_scenarios.levels_asof`/`replay_scenarios`, `plan_engine.build_confluence_plan`/`simulate_exit`, `validate_component.py`.

## Global Constraints

- **Pre-registration is frozen by the spec (§3–§4).** Grid: `N` 3/5/10 × `k` 0.25/0.5 ATR × `b` 0.00/0.05/0.10/0.15/0.20 ATR = **30 cells**, no mode axis. Reactions R1/R2/R3 keep their exact v88 definitions and are not gridded. `STOP_ENTRY_EXPIRY_BARS = 2`. ATR = `indicators.atr(df, 14)`. Nothing here may be retuned after a number is seen.
- **`reaction.py` is not modified by this plan.** Not its predicates, not its constants, and not `reaction_kind`'s `R3 > R2 > R1` precedence — spec §3.2 accepts the cost that a bar which is both a reclaim and a rejection cancels.
- **Windows:** Run 1 = 2018-06-01..2023-12-31; selection = **2018-06-01..2020-12-31** only; fold-test years 2021/2022/2023; VALIDATION = 2024-01-01..2025-12-31, **one shot**, replay refused in code without a Stage 2 doc reading `**Overall: PASS**`.
- **Selection rule unchanged from v88:** eligible iff volume cut <= 25% **and** `ΔExpR >= −0.01R` **and** mix-standardised `ΔWR > 0`; pick greatest `ΔExpR`, ties → greater `ΔWR`, then smaller `N`; `plateau_report` (tolerance 0.03R) on `N`, `k`, `b` each, holding the rest at the selected values; any spike disqualifies. **No threshold, margin or tolerance in this plan may be edited.**
- **Clause (c) is the win-rate guarantee.** No cell with `ΔWR <= 0` can be selected at any expectancy. If the `b=0.00` cells breach clause (a)'s 25% volume ceiling they are simply ineligible; the ceiling is not relaxed (spec §3.4).
- **An alert** is every issued plan on either arm, including a stop-entry that ends `not_triggered`.
- **Frozen constants untouched:** `MIN_RISK_REWARD_RATIO = 1.5`, `MAX_RISK_REWARD_RATIO = 2.5`, `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`, `COOLDOWN_BARS = 5`, `CONFLUENCE_TOLERANCE_PCT = 5.0`, and every clause constant in `acceptance.py` / `backtest_wf.py`.
- **No `config.Field` for any v90 knob** — `N_GRID`, `K_GRID`, `B_GRID` stay module constants, so no v75-style search can sweep them.
- **NO-LOOKAHEAD law:** every decision at bar `j` reads bars `<= j`. The arm state machine keeps its truncation test, extended to the new cancels.
- **Stage-window discipline (spec §4.4):** the fold years and the VALIDATION window must not be queried for reaction-kind behaviour before their stage runs. RJ7 reads the selection window only.
- **`data/v88/run1` is read-only input** to the overlap report and must not be regenerated or deleted.
- Worktree for Phase 1: `.claude/worktrees/2026-09-16-v90-rejection-only-armed-entries/`, branch of the same name. Phase 2 runs on `main` after the merge.
- Per-task check: `python scripts/dev/testrun.py file <test file>`. The full suite runs **once**, in RJ5, before the first long run.
- Long runs go to the `backtest-runner` subagent, with a flushed percent figure in a progress file that is deleted on completion.
- Never `cd` in a Bash tool command; use absolute paths or `git -C`.
- Commit messages end with the session's attribution lines.

## Parallelisation

- **Sequential:** RJ1 → RJ2. Both edit `armed_replay.py`, and RJ2's `plan_at` change depends on RJ1 having made `kind` always `R1` at confirmation.
- **Group 1 (parallel):** RJ3 may run alongside RJ1, but **not** alongside RJ2 — RJ3 constructs `Cell` without a mode, which is RJ2's change. Simplest safe order is RJ1 → RJ2 → RJ3; run RJ3 in parallel only if RJ2 is already committed.
- **Sequential:** RJ4 after RJ3 (imports the refined `CELLS` and the new `overlap_report`). RJ5 after RJ4.
- **Phase 2 is strictly sequential:** each stage reads the previous stage's results doc, and RJ10's replay is locked in code behind RJ9's PASS.

## Outcomes (spec §4.5)

| Result | Plan ends at | Live ARMED lifecycle |
|---|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` (RJ7), MDE refused (RJ8), Stage 2 FAIL (RJ9) | RJ11, budget intact | not written |
| Stage 3 FAIL (RJ10) | RJ11, budget spent | not written |
| Stage 3 PASS (RJ10) | RJ11 | brainstormed next |

---

# Phase 1 — Code (worktree branch)

Create the worktree first, via the `superpowers:using-git-worktrees` skill:
`.claude/worktrees/2026-09-16-v90-rejection-only-armed-entries/`, branch `2026-09-16-v90-rejection-only-armed-entries`, from `main`.

### Task RJ1: Only a rejection confirms the arm

**Files:**
- Modify: `swingbot/core/backtesting/armed_replay.py:105-143` (`walk_arm`)
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes: `reaction.R1` / `R2` / `R3` and `reaction.reaction_kind`, unchanged.
- Produces: `ArmOutcome.status` gains `"cancelled_follow_through"` and `"cancelled_reclaim"`. `ArmOutcome("confirmed", ...)` is now only ever returned with `kind == reaction.R1`, which RJ2 relies on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_armed_replay.py`, after `test_walk_bearish_mirror_confirms`:

```python
def test_walk_cancels_on_a_follow_through_instead_of_confirming():
    """Bar 26 tests the level; bar 27 closes above bar 26's high -> R2."""
    out = _walk(_frame({26: (99.5, 99.8, 98.6, 99.0),
                        27: (99.2, 100.5, 99.1, 100.4)}))
    assert out == ar.ArmOutcome("cancelled_follow_through", 27)


def test_walk_cancels_on_a_reclaim_instead_of_confirming():
    """Bar 26 closes below the level; bar 27 closes back above it -> R3."""
    out = _walk(_frame({26: (99.0, 99.2, 98.0, 98.2),
                        27: (98.3, 99.4, 98.1, 99.0)}))
    assert out == ar.ArmOutcome("cancelled_reclaim", 27)


def test_a_follow_through_ends_the_arm_before_a_later_rejection():
    """Spec §3.1: we do not wait past a follow-through. Bar 29 is a clean
    R1 the walk must never reach."""
    df = _frame({26: (99.5, 99.8, 98.6, 99.0),
                 27: (99.2, 100.5, 99.1, 100.4),
                 29: (99.0, 99.6, 97.6, 99.4)})
    assert _walk(df) == ar.ArmOutcome("cancelled_follow_through", 27)


def test_walk_bearish_mirror_cancels_on_a_follow_through():
    cand = _cand(direction="bearish", level=101.5, target=94.0)
    out = _walk(_frame({26: (100.5, 101.4, 100.2, 101.0),
                        27: (100.8, 100.9, 99.5, 99.6)}), cand=cand)
    assert out == ar.ArmOutcome("cancelled_follow_through", 27)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/backtesting/test_armed_replay.py -k "follow_through or reclaim" -v`
Expected: FAIL — all four return `ArmOutcome("confirmed", 27, 'R2'|'R3', 26)` instead of a cancel.

- [ ] **Step 3: Change the terminal condition**

In `swingbot/core/backtesting/armed_replay.py`, inside `walk_arm`, replace:

```python
            if kind is not None:
                return ArmOutcome("confirmed", t, kind, first_test)
```

with:

```python
            if kind == reaction.R1:
                return ArmOutcome("confirmed", t, kind, first_test)
            if kind == reaction.R2:
                return ArmOutcome("cancelled_follow_through", t)
            if kind == reaction.R3:
                return ArmOutcome("cancelled_reclaim", t)
```

- [ ] **Step 4: Update `walk_arm`'s docstring**

Replace the docstring's first paragraph:

```python
    """Walk one armed scenario across [i, i + N] (spec §3.2).

    Only a rejection (R1) confirms. A follow-through (R2) or a reclaim
    (R3) abandons the arm where it stands -- price left the level without
    holding it, so the entry thesis is void and a later rejection would be
    a rejection of a different level.

    Per bar t, in this order: the target check (bars after the arm bar
    only; a bar that both reaches the target and reacts is a cancel), the
    test, the reaction, then the close-through-not-reclaimed cancel. Every
    check at t reads bars <= t.
    """
```

- [ ] **Step 5: Run the file's tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: the four new tests PASS. Existing R1 tests (`test_walk_confirms_a_rejection_and_records_the_first_test`, `test_walk_bearish_mirror_confirms`, `test_target_reached_on_the_arm_bar_itself_is_ignored`) still PASS. Failures in `test_one_live_arm_per_direction_and_cooldown_after_issuance`, `test_replay_armed_never_reads_past_the_confirmation_bar` and the `_build`/`_replay`/permutation tests are **expected here** and are fixed in RJ2 — note which fail and carry the list into RJ2.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py
git commit -m "feat(v90): confirm an arm only on a rejection"
```

---

### Task RJ2: Drop the mode axis and the market-entry branch

**Files:**
- Modify: `swingbot/core/backtesting/armed_replay.py` (`Cell`, imports, `plan_at`, `build_armed_plan`, `delay_permutations`)
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes: RJ1's guarantee that `outcome.kind` is always `reaction.R1` at confirmation.
- Produces: `Cell(n: int, k: float, b: float)` with `cell_id` = `f"N{n}-k{k:.2f}-b{b:.2f}"`. `plan_at(...)` loses its `kind` keyword argument entirely; `build_armed_plan` and `delay_permutations` lose the plumbing that fed it. RJ3 constructs `Cell` with this three-argument shape.

- [ ] **Step 1: Write the failing tests**

In `tests/backtesting/test_armed_replay.py`, replace the module-level `CELL` and `test_cell_id_format`:

```python
CELL = ar.Cell(5, 0.25, 0.10)


def test_cell_id_format():
    assert ar.Cell(10, 0.5, 0.25).cell_id == "N10-k0.50-b0.25"
    assert ar.Cell(3, 0.25, 0.0).cell_id == "N3-k0.25-b0.00"
```

Delete `test_m2_goes_straight_to_market_on_a_follow_through` and `test_m2_keeps_a_rejection_as_a_stop_entry` outright — they assert behaviour this task removes. Replace them with:

```python
def test_every_confirmed_plan_is_a_stop_entry():
    """No mode, no market fill: R1 is the only confirmation and it always
    triggers above the rejection bar's extreme."""
    plan, reason = _build(_frame({26: REJECTION}), ar.ArmOutcome("confirmed", 26, rx.R1, 26),
                          cell=ar.Cell(5, 0.25, 0.25))
    assert reason == "issued"
    assert plan.entry_type == "stop_entry" and plan.entry_price is None
    assert plan.trigger_price == pytest.approx(99.6)
    assert plan.expiry_bars == ar.STOP_ENTRY_EXPIRY_BARS
    assert plan.status == PlanStatus.PENDING
    assert plan.status_history == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/backtesting/test_armed_replay.py::test_cell_id_format -v`
Expected: FAIL with `TypeError: Cell.__init__() missing 1 required positional argument: 'b'` (the three-argument call binds to `mode, n, k`).

- [ ] **Step 3: Drop `mode` from `Cell`**

In `swingbot/core/backtesting/armed_replay.py`:

```python
@dataclass(frozen=True)
class Cell:
    n: int         # arm window, bars
    k: float       # test proximity, ATR
    b: float       # stop buffer, ATR

    @property
    def cell_id(self) -> str:
        return f"N{self.n}-k{self.k:.2f}-b{self.b:.2f}"
```

- [ ] **Step 4: Remove the market branch from `plan_at`**

Change the signature — delete the `kind: str,` parameter:

```python
def plan_at(ticker: str, df, horizon_key: str, cand: ArmCandidate, *, j: int,
            first_test_index: int, cell: Cell, bars: reaction.Bars,
            atr_values: np.ndarray, params: ScanParams, level_map_at, confluence_at):
```

Replace the entry block:

```python
    market = cell.mode == "M2" and kind in (reaction.R2, reaction.R3)
    if market:
        entry = float(bars.close[j])
    else:
        entry = float(bars.high[j] if bull else bars.low[j])
```

with:

```python
    entry = float(bars.high[j] if bull else bars.low[j])
```

Replace the closing block:

```python
    plan = dataclasses.replace(
        plan, entry_type="market" if market else "stop_entry", trigger_price=entry,
        entry_price=entry if market else None,
        expiry_bars=plan.expiry_bars if market else STOP_ENTRY_EXPIRY_BARS,
        status=PlanStatus.PENDING, status_history=[])
    if market:
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=plan.created_at)
    return plan, "issued"
```

with:

```python
    plan = dataclasses.replace(
        plan, entry_type="stop_entry", trigger_price=entry, entry_price=None,
        expiry_bars=STOP_ENTRY_EXPIRY_BARS,
        status=PlanStatus.PENDING, status_history=[])
    return plan, "issued"
```

Delete the now-unused import at the top of the file:

```python
from swingbot.core.planning.plan_types import record_transition
```

- [ ] **Step 5: Drop the `kind` plumbing from the two callers**

In `build_armed_plan`, delete `kind=outcome.kind,` from the `plan_at` call:

```python
    return plan_at(ticker, df, horizon_key, cand, j=outcome.resolved_index,
                   first_test_index=outcome.first_test_index, cell=cell,
                   bars=bars, atr_values=atr_values, params=params,
                   level_map_at=level_map_at, confluence_at=confluence_at)
```

In `delay_permutations`, change `row_at` to drop its `kind` parameter and argument:

```python
    def row_at(arm_index: int, cand: ArmCandidate, j: int):
        key = (arm_index, j)
        if key not in memo:
            first_test = next((t for t in range(cand.index, j + 1)
                               if reaction.is_test(bars, t, cand.level, cand.direction,
                                                   cell.k, atr_values[t])), cand.index)
            plan, _ = plan_at(ticker, df, horizon_key, cand, j=j, first_test_index=first_test,
                              cell=cell, bars=bars, atr_values=atr_values,
                              params=params, level_map_at=level_map_at,
                              confluence_at=confluence_at)
```

and its call site inside the permutation loop:

```python
            row = row_at(arm_index, cand, j)
```

- [ ] **Step 6: Correct `delay_permutations`' docstring**

The docstring still describes the deleted mode split. Replace this sentence:

```
    confirmation to a bar drawn uniformly from its own
    [i, min(i + N, last bar)] window. The plan is built by plan_at exactly
    as at a real confirmation: the stop anchors from the first test at or
    before the drawn bar (the arm bar when nothing has tested yet), and the
    entry follows the arm's REAL reaction kind -- M2's market/stop split
    needs a kind, and a random bar has none of its own.
```

with:

```
    confirmation to a bar drawn uniformly from its own
    [i, min(i + N, last bar)] window. The plan is built by plan_at exactly
    as at a real confirmation: the stop anchors from the first test at or
    before the drawn bar (the arm bar when nothing has tested yet), and the
    entry is a stop-entry at that bar's extreme. The population is every arm
    that confirmed on R1 -- R2 and R3 no longer confirm anything (spec §4.2).
```

- [ ] **Step 7: Prove the cooldown release (spec §3.3, §6)**

This is the test that backs the spec's claim that v90's population is not a re-label of v88's R1 rows. Add to `tests/backtesting/test_armed_replay.py`:

```python
def test_a_cancelled_follow_through_releases_the_next_arm(monkeypatch):
    """Spec §3.3: in v88 the R2 at bar 27 ISSUED a plan, setting
    last_issued=27 and suppressing the arm at 29 for COOLDOWN_BARS. Here it
    cancels, issues nothing, and the arm at 29 goes on to confirm on R1."""
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = _frame({26: (99.5, 99.8, 98.6, 99.0),      # test
                 27: (99.2, 100.5, 99.1, 100.4),    # R2 -> cancel, no issuance
                 31: REJECTION}, n=40)              # R1 for the released arm
    result = _replay(df, {25: [_cand(index=25)], 29: [_cand(index=29)]})
    assert result.counts["armed"] == 2              # 29 - 27 = 2 < COOLDOWN_BARS
    assert result.counts["cancelled_follow_through"] == 1
    assert [j for j, _, _ in result.issued] == [31]
```

- [ ] **Step 8: Extend the NO-LOOKAHEAD truncation cover to the two new cancels (spec §4.3)**

Add to `tests/backtesting/test_armed_replay.py`:

```python
def test_the_new_cancels_resolve_identically_on_a_truncated_frame():
    """NO-LOOKAHEAD: a cancel at bar j is the same decision whether or not
    the frame continues past j."""
    df = _frame({26: (99.5, 99.8, 98.6, 99.0), 27: (99.2, 100.5, 99.1, 100.4)}, n=40)
    full = _walk(df)
    assert full == ar.ArmOutcome("cancelled_follow_through", 27)
    assert _walk(df.iloc[:full.resolved_index + 1]) == full

    df2 = _frame({26: (99.0, 99.2, 98.0, 98.2), 27: (98.3, 99.4, 98.1, 99.0)}, n=40)
    full2 = _walk(df2)
    assert full2 == ar.ArmOutcome("cancelled_reclaim", 27)
    assert _walk(df2.iloc[:full2.resolved_index + 1]) == full2
```

In the existing `test_replay_armed_never_reads_past_the_confirmation_bar`, line ~241 builds two cells that differ only by mode:

```python
    cells = [ar.Cell("M1", 10, 0.5, 0.10), ar.Cell("M2", 10, 0.5, 0.10)]
```

With the mode gone these collapse into the same cell id. Replace with two genuinely different cells:

```python
    cells = [ar.Cell(10, 0.5, 0.10), ar.Cell(10, 0.5, 0.20)]
```

- [ ] **Step 9: Re-derive the remaining fixtures RJ1 broke**

`test_one_live_arm_per_direction_and_cooldown_after_issuance` uses candidate bars `(25, 26, 27, 28, 31, 32, 33)` on a frame whose only reaction bar is an R1 at 27, so its arithmetic is unchanged by RJ1 — only its `cell=CELL` construction changes, which Step 3 already handled. Run it and confirm. `test_a_random_bar_before_any_test_anchors_the_stop_at_the_arm_bar` (line ~290) spies on `plan_at` and asserts `kind == rx.R1`; delete that assertion and its `kind` capture:

```python
def test_a_random_bar_before_any_test_anchors_the_stop_at_the_arm_bar(monkeypatch):
    df, confirmed, kwargs = _perm_setup(monkeypatch)
    seen = {}
    real = ar.plan_at
    def spy(*a, **k):
        seen[k["j"]] = k["first_test_index"]
        return real(*a, **k)
    monkeypatch.setattr(ar, "plan_at", spy)
    ar.delay_permutations("AAPL", df, "4w", CELL, confirmed, n=200, seed=1, **kwargs)
    assert seen, "200 draws over 6 bars must visit some bar"
    for j, first_test in seen.items():
        assert first_test == (27 if j >= 27 else 25)
```

`_build` (line ~117) and `test_nan_atr_refuses` (line ~182) call `ar.build_armed_plan` positionally and pass no `kind`, so they need no change beyond the `Cell` shape Step 3 settled.

- [ ] **Step 10: Run the file's tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: `0 failed`. Every test listed at the end of RJ1 Step 5 is now green.

- [ ] **Step 11: Commit**

```bash
git add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py
git commit -m "feat(v90): drop the mode axis and the market-entry branch"
```

---

### Task RJ3: The refined 30-cell grid

**Files:**
- Modify: `swingbot/core/backtesting/armed_measurement.py:23-27` (grid), `:39-52` (rule and limitations text), `:172-193` (`render_selection_md`)
- Test: `tests/backtesting/test_armed_measurement.py`

**Interfaces:**
- Consumes: RJ2's `Cell(n, k, b)`.
- Produces: `CELLS` of 30 `Cell`s ordered `n → k → b`; `B_GRID = (0.00, 0.05, 0.10, 0.15, 0.20)`; `MODES` no longer exists. `select_cell`, `score_cell`, `arms_blob`, `folds_blob` and `permutation_p` keep their current signatures.

- [ ] **Step 1: Write the failing test**

In `tests/backtesting/test_armed_measurement.py`, replace `test_the_grid_is_the_pre_registered_24_cells`:

```python
def test_the_grid_is_the_pre_registered_30_cells():
    assert len(am.CELLS) == 30
    assert len({c.cell_id for c in am.CELLS}) == 30
    assert am.CELLS[0].cell_id == "N3-k0.25-b0.00"
    assert am.CELLS[-1].cell_id == "N10-k0.50-b0.20"
    # order is n -> k -> b, 5 cells per (n, k): N5-k0.25 starts at 10
    assert am.cell_by_id("N5-k0.25-b0.10") == am.CELLS[12]
    assert not hasattr(am, "MODES")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/backtesting/test_armed_measurement.py::test_the_grid_is_the_pre_registered_30_cells -v`
Expected: FAIL with `assert 24 == 30`.

- [ ] **Step 3: Refine the grid**

In `swingbot/core/backtesting/armed_measurement.py`, replace lines 23–27:

```python
N_GRID = (3, 5, 10)
K_GRID = (0.25, 0.5)
B_GRID = (0.00, 0.05, 0.10, 0.15, 0.20)
CELLS = tuple(Cell(n, k, b) for n in N_GRID for k in K_GRID for b in B_GRID)
BASELINE = "baseline"
```

(`MODES = ("M1", "M2")` is deleted, not commented out.)

- [ ] **Step 4: Correct the pre-registered prose**

Replace `SELECTION_RULE`'s final sentence — drop `and the mode`:

```python
SELECTION_RULE = (
    "A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), "
    "ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible "
    "cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. "
    "The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along each "
    "of N, k and b with the other knobs held; any spike disqualifies."
)
```

Replace `LIMITATIONS` — the market-fill limitation is gone because market fills are gone (spec §4.3):

```python
LIMITATIONS = (
    "Recorded limitations: daily-bar ordering is conservative (stop before target on the "
    "same bar); the universe is today's cached tickers (survivorship)."
)
```

- [ ] **Step 5: Retitle the Stage 1 renderer**

In `render_selection_md`, change the first line and the table heading:

```python
    lines = ["# v90 rejection-only armed entries — Stage 1 selection", "",
             f"**Verdict: {selection.verdict}**", "",
             f"Window: {SELECTION_WINDOW[0]}..{SELECTION_WINDOW[1]} (fold-train only).", "",
             "## Pre-registered rule", "", SELECTION_RULE, "", LIMITATIONS, "",
             "## All 30 cells", "",
```

- [ ] **Step 6: Fix the fixture cell ids in the rest of the file's tests**

`tests/backtesting/test_armed_measurement.py` names `M1-N3-k0.25-b0.10` and `M1-N5-k0.25-b0.10` in five places (lines ~41, 65, 71–72, 86, 88, 92). Replace every `M1-N3-k0.25-b0.10` with `N3-k0.25-b0.10` and every `M1-N5-k0.25-b0.10` with `N5-k0.25-b0.10`. The tie-break assertion at line ~65 still holds: with all cells tied, the winner is the smallest `N` first in order, which is now `N3-k0.25-b0.00`, so update that expectation:

```python
    assert selection.selected == "N3-k0.25-b0.00"                     # all tie -> smaller N, first in order
```

- [ ] **Step 7: Run the file's tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_measurement.py`
Expected: `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/armed_measurement.py tests/backtesting/test_armed_measurement.py
git commit -m "feat(v90): refine the b axis and drop the mode axis from the grid"
```

---

### Task RJ4: The overlap disclosure and the v90 output root

**Files:**
- Modify: `swingbot/core/backtesting/armed_measurement.py` (add `overlap_report`, extend `render_selection_md`)
- Modify: `scripts/backtest/measure_armed_entries.py:40` (`OUT_ROOT`), `cmd_select`
- Modify: `.gitignore`
- Test: `tests/backtesting/test_armed_measurement.py`, `tests/scripts/test_measure_armed_entries.py`

**Interfaces:**
- Consumes: RJ3's `CELLS`, and `Row.reaction` as written by v88's run1 shards.
- Produces: `overlap_report(rows, v88_rows) -> list[dict]`, each `{"cell_id", "n", "v88_r1_n", "shared", "new_here", "only_in_v88"}`. `render_selection_md(selection, overlap=None)`.

**Why:** spec §3.3 — the v90 population is *not* a re-label of v88's R1 rows, because releasing the R2/R3 issuance cooldown lets arms through that v88 never evaluated. The degree of reproduction is evidence to be measured, not asserted.

- [ ] **Step 1: Write the failing test**

Append to `tests/backtesting/test_armed_measurement.py`:

```python
def test_overlap_report_separates_shared_from_newly_released_arms():
    shared = _rows("N3-k0.25-b0.10", 1, 0, date="2019-01-02")
    mine_only = _rows("N3-k0.25-b0.10", 1, 0, date="2019-02-02")
    v88 = [am.Row("M1-N3-k0.25-b0.10", shared[0].trade, "R1"),
           am.Row("M1-N3-k0.25-b0.10", mine_only[0].trade, "R2"),
           am.Row("M2-N3-k0.25-b0.10",
                  dataclasses.replace(shared[0].trade, entry_date="2019-03-02"), "R1")]
    report = {r["cell_id"]: r for r in am.overlap_report(shared + mine_only, v88)}
    row = report["N3-k0.25-b0.10"]
    assert row["n"] == 2
    assert row["v88_r1_n"] == 2          # the R2 row is not an R1 counterpart
    assert row["shared"] == 1
    assert row["new_here"] == 1          # released by the dropped cooldown
    assert row["only_in_v88"] == 1
    assert report["N3-k0.25-b0.00"]["v88_r1_n"] is None   # b=0.00 had no v88 counterpart
```

Add `import dataclasses` at the top of the test file if it is not already imported.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/backtesting/test_armed_measurement.py::test_overlap_report_separates_shared_from_newly_released_arms -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'overlap_report'`.

- [ ] **Step 3: Implement `overlap_report`**

Add to `swingbot/core/backtesting/armed_measurement.py`, after `arm_trades`:

```python
V88_B_GRID = (0.10, 0.25)      # the b values v88 actually ran, for the overlap only


def _trade_key(trade) -> tuple:
    return (trade.ticker, trade.strategy, trade.horizon_key, trade.entry_date)


def overlap_report(rows, v88_rows) -> list[dict]:
    """Spec §3.3: how much of each cell's confirmed population is the same
    trades v88 already showed as R1, and how much the released R2/R3
    cooldown added. `v88_rows` carry v88's mode-bearing cell ids; a v90
    cell whose `b` v88 never ran has no counterpart and reports None.
    """
    v88_by_cell: dict = {}
    for row in v88_rows:
        if row.reaction == "R1":
            v88_by_cell.setdefault(row.arm, set()).add(_trade_key(row.trade))
    out = []
    for cell in CELLS:
        mine = {_trade_key(row.trade) for row in rows if row.arm == cell.cell_id}
        if cell.b not in V88_B_GRID:
            out.append({"cell_id": cell.cell_id, "n": len(mine), "v88_r1_n": None,
                        "shared": None, "new_here": None, "only_in_v88": None})
            continue
        theirs: set = set()
        for mode in ("M1", "M2"):
            theirs |= v88_by_cell.get(f"{mode}-{cell.cell_id}", set())
        out.append({"cell_id": cell.cell_id, "n": len(mine), "v88_r1_n": len(theirs),
                    "shared": len(mine & theirs), "new_here": len(mine - theirs),
                    "only_in_v88": len(theirs - mine)})
    return out
```

- [ ] **Step 4: Render it into the Stage 1 doc**

Change `render_selection_md`'s signature and append the section before the return:

```python
def render_selection_md(selection: Selection, overlap: list | None = None) -> str:
```

and immediately before `return "\n".join(lines) + "\n"`:

```python
    if overlap:
        lines += ["", "## Overlap with v88's R1 rows (spec §3.3)", "",
                  "This mechanism is not a re-label of v88's R1 population: dropping the "
                  "R2/R3 issuances releases arms their 5-bar cooldown suppressed, and those "
                  "arms shift later ones in turn. `n/a` means v88 never ran that `b`.", "",
                  "| cell | n | v88 R1 n | shared | new here | only in v88 |",
                  "|---|---|---|---|---|---|"]
        for row in overlap:
            lines.append(
                f"| {row['cell_id']} | {row['n']} | "
                + " | ".join("n/a" if row[key] is None else str(row[key])
                             for key in ("v88_r1_n", "shared", "new_here", "only_in_v88"))
                + " |")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run the measurement tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_measurement.py`
Expected: `0 failed`.

- [ ] **Step 6: Point the script at `data/v90` and wire the overlap in**

In `scripts/backtest/measure_armed_entries.py`, change line 40:

```python
OUT_ROOT = ROOT / "data" / "v90"
```

In `cmd_select`, read v88's rows and pass them through. Replace the `render_selection_md` call and add the source directory resolution just above it:

```python
    v88_dir = Path(args.v88_run_dir)
    overlap = am.overlap_report(rows, read_rows(v88_dir)) if v88_dir.exists() else None
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(am.render_selection_md(selection, overlap), encoding="utf-8")
```

(Keep whatever surrounding `out_md` handling the function already has; only the rendered call gains `overlap`.)

Add the argument to the `select` subparser, beside its existing `--out-md` / `--out-json`:

```python
    p.add_argument("--v88-run-dir", default=str(ROOT / "data" / "v88" / "run1"),
                   help="v88 run1 shards, read-only, for the spec §3.3 overlap report")
```

- [ ] **Step 7: Ignore the v90 run output**

In `.gitignore`, below the `data/v88/` entry:

```
# v90 rejection-only armed-entries replay output (large, regenerable)
data/v90/
```

- [ ] **Step 8: Update the script's tests**

In `tests/scripts/test_measure_armed_entries.py`, replace both `am.Cell("M1", 10, 0.5, 0.10)` monkeypatches (lines ~67, ~86) with `am.Cell(10, 0.5, 0.10)`, and every `M1-N10-k0.50-b0.10` / `M1-N3-k0.25-b0.10` string with its mode-less form (`N10-k0.50-b0.10`, `N3-k0.25-b0.10`).

One expectation genuinely moves: `test_summary_select_and_arms` (line ~113) asserts `payload["selected"] == "M1-N3-k0.25-b0.10"`. `_synthetic_rows()` gives every cell the same record, so the tie-break picks the smallest `N` first in grid order — which is now `N3-k0.25-b0.00`, not `b0.10`. Set the expectation to whatever that test's `payload["selected"]` actually prints and confirm it is `N3-k0.25-b0.00` before accepting it. Then add, using the same helpers that test uses:

```python
def test_select_skips_the_overlap_section_without_a_v88_run(tmp_path):
    out = tmp_path / "out"
    _write_rows(out / "run1", _synthetic_rows())
    md = tmp_path / "stage1.md"
    assert mae.main(["select", "--out-root", str(out), "--out-md", str(md),
                     "--v88-run-dir", str(tmp_path / "absent")]) == 0
    assert "Overlap with v88" not in md.read_text(encoding="utf-8")
```

- [ ] **Step 9: Run both test files**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_armed_entries.py`
Expected: `0 failed`.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/backtesting/armed_measurement.py scripts/backtest/measure_armed_entries.py .gitignore tests/backtesting/test_armed_measurement.py tests/scripts/test_measure_armed_entries.py
git commit -m "feat(v90): report the overlap with v88's R1 rows and split the output root"
```

---

### Task RJ5: Full-suite verification and merge

- [ ] **Step 1: Run the full suite once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) once, over RJ1–RJ4. Expect `0 failed`, `0 xfailed`.

**If it is not green, fix forward from those failures** — they are this plan's regressions, and the task is not done until the run is. Two known non-obvious callers to check if something fails outside the four files above: anything importing `Cell` positionally, and anything asserting `entry_type == "market"` on an armed plan.

> **Known environment trap:** this suite's Postgres-backed tests are not isolated per `pytest-xdist` worker and produce non-deterministic failures under `testrun.py full`'s `-n 4` — a different DB test fails on each run (observed 2026-09-16 across three runs, v88 AR8). Those failures are **not** this plan's. Confirm by re-running the failing node IDs serially (`python -m pytest <node id> -v`); if they pass serially and the only failures are in `tests/db/`, `tests/planning/test_plan_trade_atomicity.py`, `tests/tracking/`, `tests/analytics/test_journal_db.py` or `tests/commands/test_*_db.py`, run the whole suite serially (`python -m pytest tests/`) and use that as the gate.

- [ ] **Step 2: Merge the worktree branch to `main`**

Per `document-lifecycle.md`. A conflict-free merge is not re-run; a merge that resolved conflicts gets one run. Do not remove the worktree yet — RJ11 closes the plan out.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-09-16-v90-rejection-only-armed-entries -m "Merge branch '2026-09-16-v90-rejection-only-armed-entries'"
```

`Bump: none`: no `VERSION.json` change.

---

# Phase 2 — Measurement runs (on `main`, after RJ5's merge)

Every task here runs on `main` in the main tree. `<run-date>` is the date (`YYYY-MM-DD`) the command in that task finishes; `<cell>` is the cell id RJ7 selects. **Commit each result as written before reading anything into it.** A verdict that ends the measurement goes straight to RJ11 — the grid, windows, rule and constants never change.

### Task RJ6: Run 1 replay

**Files:**
- Create (local, not committed): `data/v90/run1/*.jsonl`, `*.counts.json`, `run.json`
- Create: `docs/superpowers/results/<run-date>-v90-rejection-run1.md`

**Interfaces:**
- Consumes: the merged code (RJ1–RJ4); `data/backtest_cache/*.csv`.
- Produces: Run 1 rows (2018-06-01..2023-12-31) for the baseline and all 30 cells.

- [ ] **Step 1: Confirm the cache covers both runs**

```bash
python -c "import pandas as pd, glob; f=sorted(glob.glob('data/backtest_cache/*.csv')); d=[pd.read_csv(p, index_col='Date', parse_dates=True).index for p in f]; print(len(f), 'files', min(i.min() for i in d).date(), '->', min(i.max() for i in d).date())"
```

Expected: `88 files 2018-06-01 -> 2025-12-31`. The cache was refreshed and pruned on 2026-09-16 during v88 AR9 (`--end 2026-01-01`, since yfinance's `end` is exclusive; the delisted non-watchlist `EA.csv` was removed). If the last date falls short, re-run `python scripts/data/fetch_backtest_data.py --end 2026-01-01 --force` and re-check. Do not start on a short cache — `run.json` pins the file list and a later refetch refuses the resume.

- [ ] **Step 2: Dispatch the replay to `backtest-runner`**

Brief: run `python scripts/backtest/measure_armed_entries.py replay --run run1` from the repo root; it is resumable (re-running skips finished tickers); answer progress questions from `data/v90/run1/progress.txt`; report the final `complete: N rows` line, the elapsed time, and any traceback verbatim.

Expected: exit 0, `complete: <N> rows`, no `progress.txt` left behind. Budget ~2h (v88's 24 cells took 1h41m over the same 88 tickers; this runs 30). Row count will be far below v88's 940,993 — R2/R3 no longer produce trades.

- [ ] **Step 3: Summarise and commit**

```bash
python scripts/backtest/measure_armed_entries.py summary --run run1 --window 2018-06-01..2023-12-31 --out-md docs/superpowers/results/<run-date>-v90-rejection-run1.md
git add docs/superpowers/results/<run-date>-v90-rejection-run1.md
git commit -m "docs(v90): run 1 replay complete"
```

Sanity check before committing: the funnel table must show non-zero `cancelled_follow_through` and `cancelled_reclaim` columns. If either is zero across every cell, RJ1 did not take effect — stop and debug rather than reading the numbers.

---

### Task RJ7: Stage 1 — selection

**Files:**
- Create: `docs/superpowers/results/<run-date>-v90-rejection-stage1.md` and `.json`

**Interfaces:**
- Consumes: Run 1 rows; `data/v88/run1` (read-only) for the overlap section.
- Produces: `<cell>` and its selection-window `ΔWR`, or a terminal verdict.

- [ ] **Step 1: Run the pre-registered selection**

```bash
python scripts/backtest/measure_armed_entries.py select --out-md docs/superpowers/results/<run-date>-v90-rejection-stage1.md --out-json docs/superpowers/results/<run-date>-v90-rejection-stage1.json
```

Expected: `verdict: SELECTED; selected: <cell>` (exit 0), or `NO_ELIGIBLE_CELL` / `SPIKE` (exit 1), or exit 2 if the window holds no rows (a broken run — stop and debug; that is not a verdict). Capture the exit code directly (`echo $?` without a pipe — a pipe reports the last command's status, not the script's).

- [ ] **Step 2: Commit the result as written**

```bash
git add docs/superpowers/results/<run-date>-v90-rejection-stage1.md docs/superpowers/results/<run-date>-v90-rejection-stage1.json
git commit -m "docs(v90): stage 1 selection -- <verdict as printed>"
```

- [ ] **Step 3: Branch on the verdict**

- `SELECTED` → read `<cell>`'s `delta_win_rate_pp` from the JSON's `scores` list; carry both to RJ8.
- `NO_ELIGIBLE_CELL` or `SPIKE` → go to RJ11 with that verdict.

Read the overlap table before moving on, and quote its headline (shared vs new-here for the selected cell) in RJ11's close-out row. Per spec §4.4 a Stage 1 PASS here is close to a reproduction of the observation that motivated the plan; it is not confirmatory evidence and must not be described as such.

---

### Task RJ8: Stage 0 — minimum detectable effect

**Files:**
- Create (local): `data/v90/arms_mde.json`
- Create: `docs/superpowers/results/<run-date>-v90-rejection-stage0.md`

**Interfaces:**
- Consumes: RJ7's `<cell>` and `<effect>` (its `delta_win_rate_pp`).
- Produces: RESOLVABLE (continue) or REFUSED (budget intact).

- [ ] **Step 1: Build the selection-window arms**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage mde --cell <cell> --out data/v90/arms_mde.json
```

Expected: exit 0.

- [ ] **Step 2: Run the MDE gate**

```bash
python scripts/backtest/validate_component.py --stage mde --arms data/v90/arms_mde.json --title "v90 rejection-only armed entries <cell>" --window "2018-06-01..2020-12-31" --train-effect-pp <effect> --observed-days 945 --target-days 730
```

Expected: ends in `RESOLVABLE` (exit 0) or `REFUSED` (exit 1).

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v90-rejection-stage0.md`:

```markdown
# v90 rejection-only armed entries — Stage 0 (MDE)

**Verdict: <RESOLVABLE | REFUSED>**

Cell: <cell>. Window: 2018-06-01..2020-12-31. Train effect: <effect>pp.
Observed/target days: 945 / 730.

## Gate output (verbatim)

<paste the command's full stdout>
```

```bash
git add docs/superpowers/results/<run-date>-v90-rejection-stage0.md
git commit -m "docs(v90): stage 0 MDE -- <verdict>"
```

`REFUSED` → RJ11, budget intact.

---

### Task RJ9: Stage 2 — walk-forward

**Files:**
- Create (local): `data/v90/arms_walkforward.json`
- Create: `docs/superpowers/results/<run-date>-v90-rejection-stage2.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; Run 1 rows for 2021, 2022, 2023.
- Produces: `**Overall: PASS**` (unlocks RJ10's replay) or FAIL.

- [ ] **Step 1: Build the fold arms**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage walkforward --cell <cell> --out data/v90/arms_walkforward.json
```

Expected: exit 0, three folds (`2021`, `2022`, `2023`) each carrying a baseline and a component arm.

- [ ] **Step 2: Run the walk-forward gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward --arms data/v90/arms_walkforward.json --title "v90 rejection-only armed entries <cell>" --json docs/superpowers/results/<run-date>-v90-rejection-stage2.json
```

Expected: the pre-registered clause — **>= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N >= 30** — resolved to `**Overall: PASS**` (exit 0) or FAIL (exit 1). A fold with N < 30 fails the clause; it is not dropped to rescue the average.

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v90-rejection-stage2.md`, and note that RJ10's replay reads this file for the literal marker `**Overall: PASS**`:

```markdown
# v90 rejection-only armed entries — Stage 2 (walk-forward)

**Overall: <PASS | FAIL>**

Cell: <cell>. Fold-test years: 2021 / 2022 / 2023.
Clause: >= 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N >= 30.

| fold | N | ΔWR pp | ΔExpR R |
|---|---|---|---|
| 2021 | <n> | <dwr> | <dexpr> |
| 2022 | <n> | <dwr> | <dexpr> |
| 2023 | <n> | <dwr> | <dexpr> |

## Gate output (verbatim)

<paste the command's full stdout>
```

```bash
git add docs/superpowers/results/<run-date>-v90-rejection-stage2.md docs/superpowers/results/<run-date>-v90-rejection-stage2.json
git commit -m "docs(v90): stage 2 walk-forward -- <PASS|FAIL>"
```

FAIL → RJ11, budget intact.

---

### Task RJ10: Stage 3 — VALIDATION, one shot

**Files:**
- Create (local): `data/v90/run2/*`, `data/v90/arms_validation.json`
- Create: `docs/superpowers/results/<run-date>-v90-rejection-stage3.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; RJ9's Stage 2 doc reading `**Overall: PASS**`.
- Produces: the plan's terminal verdict.

**This is the one shot. It runs once, on a window no one has inspected for reaction-kind behaviour. Do not run it to "see", and do not re-run it after reading it.**

- [ ] **Step 1: Replay the VALIDATION window**

Dispatch to `backtest-runner`:

```bash
python scripts/backtest/measure_armed_entries.py replay --run run2 --stage2-doc docs/superpowers/results/<run-date>-v90-rejection-stage2.md
```

Expected: exit 0, `complete: <N> rows`. The script refuses to start unless the Stage 2 doc contains `**Overall: PASS**`; that refusal is the integrity guard working, not a bug to route around.

- [ ] **Step 2: Build the VALIDATION arms and run the gate**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage validation --cell <cell> --out data/v90/arms_validation.json
python scripts/backtest/measure_armed_entries.py permute --cell <cell> --out data/v90/permutation.json
python scripts/backtest/validate_component.py --stage validation --arms data/v90/arms_validation.json --permutation data/v90/permutation.json --title "v90 rejection-only armed entries <cell>" --json docs/superpowers/results/<run-date>-v90-rejection-stage3.json
```

Expected: clauses 1–5 each resolved; clause 6 reports `SKIPPED` and never blocks. **A missing permutation p is a FAIL**, not a skip.

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v90-rejection-stage3.md` with the verdict in bold, every clause's detail line verbatim, the permutation `p`, and `LIMITATIONS` quoted.

```bash
git add docs/superpowers/results/<run-date>-v90-rejection-stage3.md docs/superpowers/results/<run-date>-v90-rejection-stage3.json
git commit -m "docs(v90): stage 3 VALIDATION -- <PASS|FAIL>"
```

---

### Task RJ11: Close-out

Runs whatever verdict ended the measurement.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Move: `docs/superpowers/plans/2026-09-16-v90-rejection-only-armed-entries.md` and `docs/superpowers/specs/2026-09-16-v90-rejection-only-armed-entries-design.md` → `implemented/` (the code reached `main`, so not `no-lift/`)

- [ ] **Step 1: Add the closed-table row**

Append a row to `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, in the table's existing three-column shape. The component cell reads `Rejection-only armed entries — R2/R3 void the arm (v90)`. The outcome cell states, in this order: the verdict in bold with `budget intact` or `budget spent`; the stage it ended at; the selected cell (or that none was selected); the numbers that decided it (Stage 1: the best cell's cut %, ΔWR, ΔExpR **and its overlap with v88's R1 rows**; Stage 2: per-fold ΔWR; Stage 3: every clause's detail line); and one sentence on what reopening would need (**a new mechanism**, not a looser threshold or another grid over these knobs). The record cell lists the results docs by path.

If Stage 1 ended it, the row must also say that v88's R1 slice motivated the plan, so a Stage 1 failure here contradicts the observation that generated it — that is a finding about the cooldown interaction (spec §3.3), not a tuning problem.

- [ ] **Step 2: Record the outcome in the spec**

Append to the spec's §4.5: `**Outcome (<date>):** <verdict> at <stage>; the live ARMED lifecycle <is not written | is brainstormed next>.` If the verdict is PASS, say so in the close-out commit message so the next session picks it up.

- [ ] **Step 3: Amend `Edge:` only if the prediction was wrong**

A negative measurement stays `Edge: expectancy` with `Bump: none` (`document-conventions.md`: removing or failing to find edge is still an expectancy result). Change nothing unless the work turned out to buy something other than what was predicted, and then say why in one clause.

- [ ] **Step 4: Move the documents and commit**

```bash
git mv docs/superpowers/plans/2026-09-16-v90-rejection-only-armed-entries.md docs/superpowers/plans/implemented/
git mv docs/superpowers/specs/2026-09-16-v90-rejection-only-armed-entries-design.md docs/superpowers/specs/implemented/
git add docs/claude/backtest-methodology.md
git commit -m "docs(v90): close out rejection-only armed entries -- <verdict>"
```

Verify with `git show --stat HEAD` that the spec's §4.5 edit is actually in the commit — a `git mv` of a file edited in the same breath can land the rename without the edit.

- [ ] **Step 5: Remove the worktree**

Per `document-lifecycle.md`: confirm the branch is merged (`git rev-list --count main..2026-09-16-v90-rejection-only-armed-entries` prints `0`), then `git worktree remove .claude/worktrees/2026-09-16-v90-rejection-only-armed-entries`. The branch name contains neither `backup` nor `stable-`; still, deleting the branch is the human partner's call, not a default step — leave it.
