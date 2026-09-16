Bump: bot patch
Edge: harvest

# Exit-quality harvest (adaptive trail + stall-exit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two independently pre-registered `Edge: harvest` mechanisms — an R-adaptive chandelier trail on the runner leg, and a pre-TP1 MAE/time stall-exit — behind a new expectancy-primary/win-rate-floor acceptance gate, and take each through TRAIN → walk-forward → one VALIDATION shot.

**Architecture:** A new `acceptance_harvest.py` module reuses `acceptance.py`'s bootstrap/permutation primitives with a different clause set (expectancy is the objective, win rate a floor). Both mechanisms are additive checks in the existing `exit_sim.py`/`plan_manager.py` walk that already serves both live trading and backtesting, gated behind new, independently-off `config.py` flags. Two purpose-built measurement scripts (mirroring the existing `measure_avwap_confluence.py`/RS-gate precedent) drive each hypothesis through the funnel.

**Tech Stack:** Python 3.11, numpy (no scipy — not in requirements.txt), pytest, the existing `swingbot/core/backtesting/backtest.py:run_backtest` simulator.

**Spec:** `docs/superpowers/specs/2026-09-16-v92-exit-quality-harvest-design.md`

## Global Constraints

- TRAIN window `2020-01-01..2023-12-31`, VALIDATION window `2024-01-01..2025-12-31` (`docs/claude/backtest-methodology.md`). VALIDATION is a one-shot budget **per hypothesis** — never re-run after a config is chosen on TRAIN.
- Neither hypothesis touches `swingbot/core/backtesting/acceptance.py` (the v72 funnel) or its constants — this plan's gate is a sibling, not a replacement.
- Neither hypothesis reuses `DATA_DRIVEN_STOPS_ENABLED` — Hypothesis 2 gates behind its own new flag, `STALL_EXIT_ENABLED` (see spec's provenance note).
- Both new flags default `false`; with either off, exit behavior is byte-identical to today.
- `python scripts/dev/testrun.py file <touched test file>` per task (~7s); one `python scripts/dev/testrun.py full` (or the `test-runner` subagent) at the very end of this plan, not per-task.
- Any backtest run expected to exceed ~2 minutes is dispatched to the `backtest-runner` subagent so its per-symbol progress output never enters the main session's context.

## Parallelisation

Not parallel-safe across phases, and barely within them — this mirrors the spec's own call: both hypotheses ultimately touch `exit_sim.py`, so despite being logically independent (different trade phases, different flags), they fail the "disjoint files" test.

- **Phase 1** (Tasks 1-4): sequential. Tasks 1→2→3 build up the same `acceptance_harvest.py` file incrementally (each later clause function is appended after the last); Task 4 is documentation-only and could run in parallel with Tasks 1-3 in principle, but is placed last because it describes the finished clause table.
- **Phase 2** (Tasks 5-9): sequential group of one. Task 5 (config) gates Task 6 (the code that reads those flags); Task 6 gates Task 7 (the measurement script imports the function Task 6 adds); Tasks 7→8→9 are each other's gate by construction (TRAIN gates fold, fold gates validation) — this is the "sequential throughout, each task consumes the previous task's payload" shape.
- **Phase 3** (Tasks 10-16): same shape as Phase 2, one task longer for the extra plumbing (plan field + two wiring sites instead of one). Tasks 12 and 13 both depend on Task 10/11 but touch different files (`exit_sim.py` vs `plan_manager.py`) and neither reads the other's output — **these two could run as a Group of 2 in parallel** if using subagent-driven execution, the one genuine parallel opportunity in this plan. Everything else in Phase 3 is sequential for the same TRAIN→fold→validation reason as Phase 2.
- **Phase 4** (Task 17) must run after every prior phase that reached implementation, by definition of a final verification task.
- **Phases 2 and 3 as a pair**: sequential, per the spec — both write to `exit_sim.py`.

---

# Phase 1 — Harvest acceptance gate (shared infra)

### Task 1: `acceptance_harvest.py` skeleton + `mde_expectancy_r`

**Files:**
- Create: `swingbot/core/backtesting/acceptance_harvest.py`
- Test: `tests/backtesting/test_acceptance_harvest.py`

**Interfaces:**
- Consumes: `swingbot.core.backtesting.acceptance` — `ArmTrade`, `CLOSED`, `DECIDED`, `win_rate`, `expectancy_r`, `delta_expectancy_r`, `delta_standardised_win_rate`, `cluster_bootstrap`, `bootstrap_delta`, `BootstrapResult`, `ClauseResult`, `AcceptanceResult`, `population_split`, `stratum_table`, `design_effect`, `_clause_volume`, `_clause_permutation`, `render_markdown`, `BOOTSTRAP_RESAMPLES`, `ALPHA`, `_Z_ALPHA_ONE_SIDED`, `_Z_POWER`, `STAGES`.
- Produces: `HARVEST_VERSION` (int), `WIN_RATE_FLOOR_PP` (float), `mde_expectancy_r(population, *, target_n, power=0.80, alpha=ALPHA) -> float | None` — used by later tasks and by any future `Edge: harvest` spec.

- [ ] **Step 1: Write the failing test for `mde_expectancy_r`**

```python
# tests/backtesting/test_acceptance_harvest.py
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting import acceptance_harvest as ah


def _trade(ticker, r, outcome="win"):
    return ArmTrade(ticker=ticker, strategy="RSI", horizon_key="4w",
                    entry_date="2021-01-01", outcome=outcome,
                    r_multiple=r, planned_rr=2.0)


def test_mde_expectancy_r_shrinks_with_larger_target_n():
    pop = [_trade(f"T{i}", 0.2 if i % 2 else -1.0) for i in range(20)]
    mde_small = ah.mde_expectancy_r(pop, target_n=30)
    mde_large = ah.mde_expectancy_r(pop, target_n=300)
    assert mde_small is not None and mde_large is not None
    assert mde_large < mde_small


def test_mde_expectancy_r_none_on_empty_population():
    assert ah.mde_expectancy_r([], target_n=30) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.acceptance_harvest'`

- [ ] **Step 3: Write the module and `mde_expectancy_r`**

```python
# swingbot/core/backtesting/acceptance_harvest.py
"""Harvest acceptance gate (v92) -- expectancy-primary, win-rate-floor.

Read docs/claude/backtest-methodology.md's "Harvest acceptance gate" section
before changing anything here. `Edge: harvest` features are out of scope for
the v72 funnel (acceptance.py) by design -- its clause 3 (geometry lock)
rejects any exit/target/sizing change on sight, because that clause exists
to stop a *selectivity* feature from buying win rate by pulling targets
nearer, a different failure mode than a harvest feature's.

Win rate and expectancy swap roles versus v72: expectancy is the objective,
win rate a floor -- the inversion the methodology doc itself names as
legitimate. Reuses acceptance.py's ArmTrade / cluster-bootstrap /
population_split machinery wholesale; only the clause set differs.

numpy only -- scipy is NOT in requirements.txt.
"""
from __future__ import annotations

import numpy as np

from .acceptance import (
    ArmTrade, CLOSED, DECIDED, win_rate, expectancy_r,
    delta_expectancy_r, delta_standardised_win_rate,
    cluster_bootstrap, bootstrap_delta, BootstrapResult, ClauseResult,
    AcceptanceResult, population_split, stratum_table, design_effect,
    _clause_volume, _clause_permutation, render_markdown,
    BOOTSTRAP_RESAMPLES, ALPHA, _Z_ALPHA_ONE_SIDED, _Z_POWER, STAGES,
)

__all__ = [
    "HARVEST_VERSION", "WIN_RATE_FLOOR_PP", "mde_expectancy_r",
    "evaluate_harvest", "render_markdown",
]

HARVEST_VERSION = 1

#: PRE-REGISTERED gate constant. Changing it is a new pre-registration, not
#: a tuning step -- mirrors v72's GEOMETRY_MAX_DROP_PCT=2.0 tolerance for
#: "how much secondary-axis slip is acceptable" (see spec S3).
WIN_RATE_FLOOR_PP = -2.0


def mde_expectancy_r(population, *, target_n: int, power: float = 0.80,
                     alpha: float = ALPHA) -> float | None:
    """Smallest ΔExpR detectable at `power` with a one-sided test at
    `alpha`, given `target_n` closed trades per arm and the clustering
    `population` exhibits. Same z-score/design-effect math as
    acceptance.mde_win_rate, with the sample variance of `r_multiple`
    standing in for the binomial variance term."""
    closed = [t for t in population if t.outcome in CLOSED and t.r_multiple is not None]
    if not closed or target_n <= 0:
        return None
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    variance = float(np.var([t.r_multiple for t in closed], ddof=1))
    n_eff = target_n / design_effect(closed)
    if n_eff <= 0:
        return None
    return float((z_a + z_b) * np.sqrt(2.0 * variance / n_eff))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/test_acceptance_harvest.py
git commit -m "feat(v92): acceptance_harvest module skeleton + mde_expectancy_r"
```

### Task 2: `expectancy_gain` and `win_rate_floor` clauses

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_harvest.py`
- Test: `tests/backtesting/test_acceptance_harvest.py`

**Interfaces:**
- Consumes: `Task 1`'s imports (already in module).
- Produces: `_clause_expectancy_gain(baseline, component, n_resamples, seed) -> ClauseResult`, `_clause_win_rate_floor(baseline, component, n_resamples, seed, *, structurally_immune=False) -> ClauseResult` — consumed by Task 3's `evaluate_harvest`.

- [ ] **Step 1: Write the failing tests**

```python
def _arm(rs, outcomes=None):
    outcomes = outcomes or ["win"] * len(rs)
    return [_trade(f"T{i}", r, o) for i, (r, o) in enumerate(zip(rs, outcomes))]


def test_expectancy_gain_passes_on_clear_improvement():
    baseline = _arm([0.3] * 40 + [-1.0] * 40, ["win"] * 40 + ["loss"] * 40)
    component = _arm([0.8] * 40 + [-1.0] * 40, ["win"] * 40 + ["loss"] * 40)
    res = ah._clause_expectancy_gain(baseline, component, 500, seed=1)
    assert res.verdict == "PASS"


def test_expectancy_gain_fails_on_no_change():
    baseline = _arm([0.3] * 40 + [-1.0] * 40, ["win"] * 40 + ["loss"] * 40)
    res = ah._clause_expectancy_gain(baseline, baseline, 500, seed=1)
    assert res.verdict == "FAIL"


def test_win_rate_floor_skips_when_structurally_immune():
    baseline = _arm([0.3] * 10, ["win"] * 10)
    res = ah._clause_win_rate_floor(baseline, baseline, 500, seed=1,
                                    structurally_immune=True)
    assert res.verdict == "PASS"
    assert "cannot move" in res.detail


def test_win_rate_floor_fails_when_wr_collapses():
    baseline = _arm([0.3] * 70 + [-1.0] * 30, ["win"] * 70 + ["loss"] * 30)
    component = _arm([0.3] * 40 + [-1.0] * 60, ["win"] * 40 + ["loss"] * 60)
    res = ah._clause_win_rate_floor(baseline, component, 500, seed=1)
    assert res.verdict == "FAIL"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_clause_expectancy_gain'`

- [ ] **Step 3: Implement both clauses**

Append to `swingbot/core/backtesting/acceptance_harvest.py`:

```python
def _clause_expectancy_gain(baseline, component, n_resamples, seed) -> ClauseResult:
    """The objective clause: ExpR must IMPROVE, not merely hold -- the
    inverse of v72 clause 2's non-inferiority floor, because for
    Edge:harvest work expectancy is what the feature exists to buy."""
    res = bootstrap_delta(baseline, component, delta_expectancy_r,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.p_greater_than_zero is None:
        return ClauseResult("expectancy_gain", "FAIL",
                            "no closed trades in one arm", None, 0.0)
    ok = res.point > 0.0 and res.p_greater_than_zero < ALPHA
    return ClauseResult(
        "expectancy_gain", "PASS" if ok else "FAIL",
        f"dExpR {res.point:+.4f}R [{res.lo:+.4f},{res.hi:+.4f}] "
        f"p={res.p_greater_than_zero:.4f}", res.point, 0.0)


def _clause_win_rate_floor(baseline, component, n_resamples, seed, *,
                          structurally_immune: bool = False) -> ClauseResult:
    """The floor clause: standardised WR may not fall by more than
    WIN_RATE_FLOOR_PP. A mechanism that only touches behaviour after the
    win/loss decision (e.g. the runner leg, post-TP1) cannot move WR at
    all -- pass structurally_immune=True to report that fact instead of
    bootstrapping a quantity with zero variance."""
    if structurally_immune:
        return ClauseResult("win_rate_floor", "PASS",
                            "mechanism acts only after the win/loss decision "
                            "(post-TP1) -- win rate cannot move by construction",
                            0.0, WIN_RATE_FLOOR_PP)
    res = bootstrap_delta(baseline, component, delta_standardised_win_rate,
                          n_resamples=n_resamples, seed=seed)
    if res.point is None or res.lo is None:
        return ClauseResult("win_rate_floor", "FAIL",
                            "no decided trades in one arm", None, WIN_RATE_FLOOR_PP)
    ok = res.lo >= WIN_RATE_FLOOR_PP
    return ClauseResult(
        "win_rate_floor", "PASS" if ok else "FAIL",
        f"standardised dWR {res.point:+.2f}pp, lower bound {res.lo:+.2f}pp "
        f"vs floor {WIN_RATE_FLOOR_PP:+.2f}pp", res.lo, WIN_RATE_FLOOR_PP)
```

- [ ] **Step 4: Run to verify all pass**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/test_acceptance_harvest.py
git commit -m "feat(v92): expectancy_gain and win_rate_floor harvest clauses"
```

### Task 3: `evaluate_harvest` orchestrator

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_harvest.py`
- Test: `tests/backtesting/test_acceptance_harvest.py`

**Interfaces:**
- Consumes: `_clause_expectancy_gain`, `_clause_win_rate_floor` (Task 2), `_clause_volume`, `_clause_permutation`, `population_split`, `stratum_table`, `AcceptanceResult` (all imported already).
- Produces: `evaluate_harvest(baseline, component, *, stage, structurally_immune_to_wr=False, permutation_p=None, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult` — the function both measurement scripts (Tasks 7/9/14/16) call.

- [ ] **Step 1: Write the failing test**

```python
def test_evaluate_harvest_passes_clean_improvement_at_validation():
    baseline = _arm([0.3] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    component = _arm([0.9] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    result = ah.evaluate_harvest(baseline, component, stage="validation",
                                structurally_immune_to_wr=True,
                                permutation_p=0.001)
    assert result.verdict == "PASS"
    assert result.clause("win_rate_floor").verdict == "PASS"
    assert result.version == ah.HARVEST_VERSION


def test_evaluate_harvest_fails_without_permutation_p_at_validation():
    baseline = _arm([0.3] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    component = _arm([0.9] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    result = ah.evaluate_harvest(baseline, component, stage="validation",
                                structurally_immune_to_wr=True)
    assert result.verdict == "FAIL"
    assert result.clause("permutation").verdict == "FAIL"


def test_evaluate_harvest_permutation_skipped_at_walkforward():
    baseline = _arm([0.3] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    component = _arm([0.9] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    result = ah.evaluate_harvest(baseline, component, stage="walkforward",
                                structurally_immune_to_wr=True)
    assert result.clause("permutation").verdict == "SKIPPED"
    assert result.verdict == "PASS"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'evaluate_harvest'`

- [ ] **Step 3: Implement the orchestrator**

Append to `swingbot/core/backtesting/acceptance_harvest.py`:

```python
def evaluate_harvest(baseline, component, *, stage: str,
                    structurally_immune_to_wr: bool = False,
                    permutation_p: float | None = None,
                    n_resamples: int = BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> AcceptanceResult:
    """The harvest gate. Every applicable clause must PASS.

    No `mechanism` clause (v72 clause 6) -- these hypotheses don't remove
    trades, they change how already-accepted trades exit, so there is no
    removed population to interrogate. The caller's results doc should
    instead report the win->non-win outcome-flip count from
    population_split(baseline, component)['changed'] as a disclosure table
    (informational, not gating -- expectancy_gain already prices in
    whatever those flips cost or bought)."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    split = population_split(baseline, component)
    clauses = (
        _clause_expectancy_gain(baseline, component, n_resamples, seed),
        _clause_win_rate_floor(baseline, component, n_resamples, seed,
                              structurally_immune=structurally_immune_to_wr),
        _clause_volume(baseline, component),
        _clause_permutation(stage, permutation_p),
    )
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return AcceptanceResult(stage=stage, verdict=verdict, clauses=clauses,
                            strata=stratum_table(baseline, component),
                            split={k: len(v) if isinstance(v, list) else v
                                   for k, v in split.items()},
                            seed=seed, version=HARVEST_VERSION)
```

- [ ] **Step 4: Run to verify all pass**

Run: `python -m pytest tests/backtesting/test_acceptance_harvest.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/test_acceptance_harvest.py
git commit -m "feat(v92): evaluate_harvest orchestrator"
```

### Task 4: Document the harvest gate in `backtest-methodology.md`

**Files:**
- Modify: `docs/claude/backtest-methodology.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: a citable section future `Edge: harvest` specs point at instead of re-deriving the gate.

- [ ] **Step 1: Add a new section immediately after the existing "`Edge: harvest` features are OUT OF SCOPE for this funnel" paragraph**

```markdown
- **Harvest acceptance gate (v92, `swingbot/core/backtesting/acceptance_harvest.py`).**
  Fills the gap named above. Reuses acceptance.py's bootstrap/permutation
  machinery; the clause set inverts v72's role assignment (expectancy is the
  objective, win rate a floor):

  | # | Clause | Instrument | Threshold |
  |---|---|---|---|
  | 1 | `expectancy_gain` (objective) | ticker-cluster bootstrap ΔExpR | lower 95% bound > 0, one-sided p < 0.05 |
  | 2 | `win_rate_floor` | ticker-cluster bootstrap Δstandardised-WR | lower 95% bound ≥ −2.0pp (`WIN_RATE_FLOOR_PP`) — `SKIPPED` when the mechanism cannot structurally move WR |
  | 3 | `volume_floor` | closed-trade count, baseline vs component | cut ≤ 25% (reuses v72's `VOLUME_MAX_CUT_PCT`) |
  | 4 | `not_luck` | `permutation_test.py`, n=200, on ΔExpR | p < 0.05, validation stage only |

  Same Stage 0 (MDE precheck, via `acceptance_harvest.mde_expectancy_r`) →
  Stage 1 (TRAIN plateau) → Stage 2 (free walk-forward folds) → Stage 3 (one-shot
  VALIDATION) funnel as v72. No `mechanism` clause — a harvest feature changes
  how accepted trades exit, not which trades are accepted, so results docs
  report the win→non-win outcome-flip count as disclosure instead.
```

- [ ] **Step 2: Commit**

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v92): document the harvest acceptance gate"
```

---

# Phase 2 — Hypothesis 1: R-adaptive chandelier trail

### Task 5: Config flags

**Files:**
- Modify: `swingbot/config.py` (near `DATA_DRIVEN_STOPS_ENABLED`, `Field` list around line 880; `_SEARCH_CLASSES["searchable"]` set around line 947)

**Interfaces:**
- Consumes: nothing new.
- Produces: `config.ADAPTIVE_RUNNER_TRAIL_ENABLED` (bool), `config.TIGHTEN_TRIGGER_R` (float), `config.TIGHTEN_ATR_MULT` (float) — consumed by Task 6.

- [ ] **Step 1: Add the three `Field` entries**

Insert immediately after the existing `DATA_DRIVEN_STOPS_ENABLED` `Field` block (ends at the line reading `"the strategy or it does nothing. ... Off until the E33 walk-forward folds judge it."),`):

```python
    Field("ADAPTIVE_RUNNER_TRAIL_ENABLED", "ADAPTIVE_RUNNER_TRAIL_ENABLED",
          "Exit quality", "Tighten the runner trail once R clears a threshold",
          type="checkbox", default="false",
          help="Once the runner leg's own extreme-close-since-TP1 has banked "
               "TIGHTEN_TRIGGER_R since entry, the chandelier trail multiplier "
               "switches from the strategy's base value to TIGHTEN_ATR_MULT "
               "(never looser). Cannot move win rate -- TP1 already decided "
               "win/loss before the runner leg starts (v92 Hypothesis 1). Off "
               "until its TRAIN/VALIDATION shots judge it."),
    Field("TIGHTEN_TRIGGER_R", "TIGHTEN_TRIGGER_R", "Exit quality",
          "Runner R that triggers a tighter trail",
          type="float", default="2.0", min=0.5, max=5.0, step=0.25,
          help="One of v92 Hypothesis 1's two TRAIN grid dimensions."),
    Field("TIGHTEN_ATR_MULT", "TIGHTEN_ATR_MULT", "Exit quality",
          "Tightened chandelier ATR multiplier",
          type="float", default="1.75", min=0.5, max=2.5, step=0.25,
          help="Applied once TIGHTEN_TRIGGER_R clears; always <= the base "
               "trail_atr_mult by construction (min() in exit_sim.py). The "
               "other of v92 Hypothesis 1's two TRAIN grid dimensions."),
```

- [ ] **Step 2: Register them as searchable**

In `_SEARCH_CLASSES["searchable"]` (the set literal around line 947), add the three names right after `"DATA_DRIVEN_STOPS_ENABLED",`:

```python
        "MAX_ALERTS_PER_SCAN", "DATA_DRIVEN_STOPS_ENABLED",
        "ADAPTIVE_RUNNER_TRAIL_ENABLED", "TIGHTEN_TRIGGER_R", "TIGHTEN_ATR_MULT",
        "DEAD_CAT_BOUNCE_VETO", "DCB_DECLINE_PCT", "DCB_GAP_REQUIRED",
```

- [ ] **Step 3: Verify config loads**

Run: `python -c "from swingbot import config; print(config.ADAPTIVE_RUNNER_TRAIL_ENABLED, config.TIGHTEN_TRIGGER_R, config.TIGHTEN_ATR_MULT)"`
Expected: `False 2.0 1.75`

- [ ] **Step 4: Commit**

```bash
git add swingbot/config.py
git commit -m "feat(v92): config flags for the adaptive runner trail"
```

### Task 6: `_effective_trail_mult` and wiring into `_scale_out_exit_walk`

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (add helper near `chandelier_stop` at line 129; wire into the ratchet call currently at line 267)
- Test: `tests/planning/test_exit_sim_scaleout.py`

**Interfaces:**
- Consumes: `config.ADAPTIVE_RUNNER_TRAIL_ENABLED`, `config.TIGHTEN_TRIGGER_R`, `config.TIGHTEN_ATR_MULT` (Task 5).
- Produces: `_effective_trail_mult(base_mult: float, runner_r: float) -> float`, called from `_scale_out_exit_walk`'s ratchet loop.

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_exit_sim_scaleout.py (add to existing file)
from swingbot import config
from swingbot.core.planning.exit_sim import _effective_trail_mult


def test_effective_trail_mult_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    assert _effective_trail_mult(2.5, runner_r=5.0) == 2.5


def test_effective_trail_mult_unchanged_below_trigger(monkeypatch):
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", True)
    monkeypatch.setattr(config, "TIGHTEN_TRIGGER_R", 2.0)
    monkeypatch.setattr(config, "TIGHTEN_ATR_MULT", 1.75)
    assert _effective_trail_mult(2.5, runner_r=1.9) == 2.5


def test_effective_trail_mult_tightens_at_or_past_trigger(monkeypatch):
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", True)
    monkeypatch.setattr(config, "TIGHTEN_TRIGGER_R", 2.0)
    monkeypatch.setattr(config, "TIGHTEN_ATR_MULT", 1.75)
    assert _effective_trail_mult(2.5, runner_r=2.0) == 1.75
    assert _effective_trail_mult(2.5, runner_r=4.0) == 1.75


def test_effective_trail_mult_never_loosens_base(monkeypatch):
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", True)
    monkeypatch.setattr(config, "TIGHTEN_TRIGGER_R", 2.0)
    monkeypatch.setattr(config, "TIGHTEN_ATR_MULT", 3.5)  # misconfigured: "tighter" > base
    assert _effective_trail_mult(2.5, runner_r=3.0) == 2.5
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/planning/test_exit_sim_scaleout.py -v -k effective_trail_mult`
Expected: FAIL — `ImportError: cannot import name '_effective_trail_mult'`

- [ ] **Step 3: Add the helper and wire it in**

In `swingbot/core/planning/exit_sim.py`, confirm `from swingbot import config` is imported at module top (add it if not already present — `exit_sim.py`'s existing imports are local per-function, e.g. `from swingbot.core.market.indicators import atr as atr_indicator` inside `_scale_out_exit_walk`; add `from swingbot import config` as a module-level import instead, since this helper is called every ratchet iteration).

Add immediately after `chandelier_stop` (after line 135):

```python
def _effective_trail_mult(base_mult: float, runner_r: float) -> float:
    """R-adaptive tightening (v92 Hypothesis 1). Once the runner has banked
    TIGHTEN_TRIGGER_R since entry (measured off the same extreme_close the
    ratchet itself tracks, so this only ever tightens, never loosens on a
    pullback), trail at TIGHTEN_ATR_MULT instead of the strategy's base
    multiplier. `min()` guards a misconfigured TIGHTEN_ATR_MULT that is
    actually looser than base. Byte-identical to `base_mult` when the flag
    is off."""
    if not config.ADAPTIVE_RUNNER_TRAIL_ENABLED or runner_r < config.TIGHTEN_TRIGGER_R:
        return base_mult
    return min(base_mult, config.TIGHTEN_ATR_MULT)
```

In `_scale_out_exit_walk`, replace the ratchet line (currently `trail = chandelier_stop(extreme_close, atr_val, plan.trail_atr_mult, plan.direction)`, the line after the `extreme_close = ...` reassignment inside the phase-2 `for j in range(tp1_index + 1, end + 1):` loop) with:

```python
        runner_r = (extreme_close - entry_price) * sign / risk
        mult = _effective_trail_mult(plan.trail_atr_mult, runner_r)
        trail = chandelier_stop(extreme_close, atr_val, mult, plan.direction)
```

- [ ] **Step 4: Run to verify all pass**

Run: `python -m pytest tests/planning/test_exit_sim_scaleout.py -v`
Expected: PASS, no regressions in the existing scale-out tests in this file (flag defaults `false`, so pre-existing tests see byte-identical behavior).

- [ ] **Step 5: Run the narrow suite**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py`
Expected: one-line verdict, `0 failed`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_scaleout.py
git commit -m "feat(v92): R-adaptive chandelier trail tightening"
```

### Task 7: Measurement script — Stage 0/1 TRAIN grid

**Files:**
- Create: `scripts/backtest/measure_adaptive_trail.py`

**Interfaces:**
- Consumes: `swingbot.core.backtesting.backtest.run_backtest`, `window_trades`, `_tickers_for_run`, `ALL_STRATEGIES` (from `scripts/backtest/run_backtest_range.py`, imported the same way `measure_avwap_confluence.py` imports `fetch_backtest_data` — `sys.path.insert(0, os.path.join(ROOT, "scripts", "backtest"))` then a plain import), `swingbot.core.backtesting.acceptance.arm_trade_from_backtest`, `swingbot.core.backtesting.acceptance_harvest.{mde_expectancy_r, evaluate_harvest}`.
- Produces: printed Stage 0/1 verdicts per grid cell; a results doc written by hand from the printed table (Task 8 pattern, matching `results/2026-08-30-v68-dcb-veto-train.md`'s style).

- [ ] **Step 1: Write the script**

```python
"""v92 Hypothesis 1 -- R-adaptive chandelier trail. TRAIN grid.

Run: python scripts/backtest/measure_adaptive_trail.py [n_tickers]

Purpose-built instrument, same shape as measure_avwap_confluence.py: toggles
config attributes directly and calls the simulator in-process, because
run_backtest_range.py's --json output is pooled per-strategy stats, not the
per-ticker per-trade rows acceptance_harvest's cluster bootstrap needs.

Baseline = ADAPTIVE_RUNNER_TRAIL_ENABLED off. Component = on, at each grid
cell. Grid: TIGHTEN_TRIGGER_R x {1.5, 2.0, 2.5}, TIGHTEN_ATR_MULT x
{1.5, 1.75, 2.0} (9 cells). exit_model=v2, scale_out=True throughout --
Hypothesis 1 lives entirely in that path.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "data"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "backtest"))

from fetch_backtest_data import load_cached
from run_backtest_range import _tickers_for_run, window_trades, ALL_STRATEGIES
from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.backtesting.acceptance import arm_trade_from_backtest
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r, evaluate_harvest
from swingbot.core.market.strategy_types import HORIZONS

TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"
TRIGGER_GRID = (1.5, 2.0, 2.5)
MULT_GRID = (1.5, 1.75, 2.0)


def _arm_trades(flag_on, trigger, mult, tickers):
    config.ADAPTIVE_RUNNER_TRAIL_ENABLED = flag_on
    config.TIGHTEN_TRIGGER_R = trigger
    config.TIGHTEN_ATR_MULT = mult
    out = []
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None:
            continue
        for hk in HORIZONS:
            for strat in ALL_STRATEGIES:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model="v2", scale_out=True,
                                      tp2_mode="levels", frictions=True)
                except Exception:
                    continue
                for tr in window_trades(s, TRAIN_FROM, TRAIN_TO):
                    out.append(arm_trade_from_backtest(tr, ticker=ticker, strategy=strat,
                                                        horizon_key=hk))
    return out


def main():
    tickers = _tickers_for_run(None)
    if len(sys.argv) > 1:
        tickers = tickers[:int(sys.argv[1])]

    print(f"Baseline (flag off), {len(tickers)} tickers...", flush=True)
    baseline = _arm_trades(False, 2.0, 1.75, tickers)
    print(f"  {len(baseline)} closed trades")

    mde = mde_expectancy_r(baseline, target_n=len(baseline))
    print(f"Stage 0 MDE (ExpR, target_n={len(baseline)}): {mde:+.4f}R" if mde else "Stage 0 MDE: n/a")

    print("\n" + "=" * 72)
    print(f"{'trigger_r':>10s} {'tighten_mult':>13s} {'n':>6s} {'dExpR':>9s} "
          f"{'lo95':>9s} {'expect':>7s} {'wr_floor':>9s} {'volume':>7s}")
    for trigger in TRIGGER_GRID:
        for mult in MULT_GRID:
            component = _arm_trades(True, trigger, mult, tickers)
            result = evaluate_harvest(baseline, component, stage="walkforward",
                                     structurally_immune_to_wr=True)
            eg = result.clause("expectancy_gain")
            wf = result.clause("win_rate_floor")
            vol = result.clause("volume_floor")
            print(f"{trigger:10.2f} {mult:13.2f} {len(component):6d} "
                  f"{eg.value:+9.4f} {eg.detail.split('[')[1].split(',')[0]:>9s} "
                  f"{eg.verdict:>7s} {wf.verdict:>9s} {vol.verdict:>7s}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (dispatch to `backtest-runner` — full universe x 10 horizons x 11 strategies x 9 cells is well past 2 minutes)**

Command for the subagent: `python scripts/backtest/measure_adaptive_trail.py`

- [ ] **Step 3: Record the TRAIN result**

Write `docs/superpowers/results/2026-09-16-v92-adaptive-trail-train.md` by hand from the printed table: the grid, which cell(s) cleared `expectancy_gain` PASS with `is_plateau`-style neighbor agreement (per `docs/claude/backtest-methodology.md` Stage 1's plateau requirement — a single spiking cell with non-clearing neighbors does not proceed), and the Stage 0 MDE line. If no cell clears, this closes the hypothesis on TRAIN exactly like `v49`/`v69`'s no-lift closures — document it and stop; do not proceed to Task 8.

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest/measure_adaptive_trail.py docs/superpowers/results/2026-09-16-v92-adaptive-trail-train.md
git commit -m "measure(v92): H1 adaptive-trail TRAIN grid"
```

### Task 8: Stage 2 walk-forward folds (free, repeatable)

**Files:**
- Modify: `scripts/backtest/measure_adaptive_trail.py` (add a `--fold` argument)

**Interfaces:**
- Consumes: the winning `(trigger, mult)` cell from Task 7's results doc.
- Produces: `docs/superpowers/results/2026-09-16-v92-adaptive-trail-walkforward.md`.

- [ ] **Step 1: Add fold-window support**

```python
FOLDS = {"2021": ("2018-06-01", "2020-12-31", "2021-01-01", "2021-12-31"),
        "2022": ("2018-06-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        "2023": ("2018-06-01", "2022-12-31", "2023-01-01", "2023-12-31")}
```

Add `ap.add_argument("--fold", choices=list(FOLDS))` to a new `argparse`-based `main()` (replacing the bare `if __name__` call), and use the fold's test window (`FOLDS[name][2:]`) in place of `TRAIN_FROM, TRAIN_TO` inside `_arm_trades`'s `window_trades` call when `--fold` is passed.

- [ ] **Step 2: Run all three folds for the winning cell (dispatch to `backtest-runner`)**

Command: `python scripts/backtest/measure_adaptive_trail.py --fold 2021` (repeat for `2022`, `2023`), fixed at the Task 7 winning `(trigger, mult)`.

- [ ] **Step 3: Apply the pre-registered fold-stability rule**

Per `docs/claude/backtest-methodology.md` Stage 2: `gate_win_rate`-equivalent here is **≥ 2 of 3 folds improving ExpR, no fold worse than −0.01R, per-fold N ≥ 15** (the validation-stage N floor, since folds are smaller than the full TRAIN window). Record the three per-fold rows in `docs/superpowers/results/2026-09-16-v92-adaptive-trail-walkforward.md`. If the rule fails, this closes the hypothesis before spending the VALIDATION shot (the `v84` Break & Retest / VWAP precedent) — document and stop; do not proceed to Task 9.

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest/measure_adaptive_trail.py docs/superpowers/results/2026-09-16-v92-adaptive-trail-walkforward.md
git commit -m "measure(v92): H1 adaptive-trail walk-forward folds"
```

### Task 9: Stage 3 VALIDATION shot (one-shot) + default decision

**Files:**
- Modify: `scripts/backtest/measure_adaptive_trail.py` (add `--stage validation` using `TRAIN_FROM`/`TRAIN_TO`-shaped constants for `2024-01-01..2025-12-31`, and `evaluate_harvest(..., stage="validation", permutation_p=...)`)
- Modify: `swingbot/config.py` (flip `ADAPTIVE_RUNNER_TRAIL_ENABLED`'s default only if this PASSES)

**Interfaces:**
- Consumes: the fold-cleared `(trigger, mult)` cell from Task 8.
- Produces: `docs/superpowers/results/2026-09-16-v92-adaptive-trail-validation.md`; a closed-pre-registration row for `backtest-methodology.md`.

- [ ] **Step 1: Add validation-window support and a permutation-test call**

Add `VALIDATION_FROM, VALIDATION_TO = "2024-01-01", "2025-12-31"` and a `--validation` flag mirroring Task 8's `--fold`; run `scripts/backtest/permutation_test.py` (existing, n=200, per `docs/claude/backtest-methodology.md`) against the winning cell's baseline/component ArmTrade lists to get `permutation_p`, passed into `evaluate_harvest`.

- [ ] **Step 2: Run once (dispatch to `backtest-runner`) — this is the one-shot budget**

Command: `python scripts/backtest/measure_adaptive_trail.py --validation`

- [ ] **Step 3: Record the result and decide the default**

Write `docs/superpowers/results/2026-09-16-v92-adaptive-trail-validation.md` with the full clause table (`render_markdown` from `acceptance_harvest`, reused as-is) and the win→non-win outcome-flip disclosure (`population_split(baseline, component)['changed']`, per Task 3's docstring). If `PASS`, flip `ADAPTIVE_RUNNER_TRAIL_ENABLED`'s `config.py` default `"false"` → `"true"` with the winning `TIGHTEN_TRIGGER_R`/`TIGHTEN_ATR_MULT` as the new defaults. If `FAIL`, leave all three defaults as `Task 5` shipped them — the code stays merged and inert, same shape as `v36`/`v68`.

- [ ] **Step 4: Add the closed row to `backtest-methodology.md`**

Append a row to the "Closed pre-registrations" table with the outcome, mirroring the existing rows' format exactly (component name, one-line outcome, record path).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_adaptive_trail.py docs/superpowers/results/2026-09-16-v92-adaptive-trail-validation.md docs/claude/backtest-methodology.md swingbot/config.py
git commit -m "measure(v92): H1 adaptive-trail VALIDATION shot + default decision"
```

---

# Phase 3 — Hypothesis 2: MAE/time stall-exit

### Task 10: Config flag, plan field, and resolver

**Files:**
- Modify: `swingbot/config.py` (new `Field`, near the three added in Task 5; add to `_SEARCH_CLASSES["searchable"]`)
- Modify: `swingbot/core/planning/plan_types.py` (new field on `TradePlanV2`, near `time_stop_days` at line 73)
- Modify: `swingbot/core/planning/params.py` (new resolver, after `_resolve_time_stop_days` at line 100)
- Modify: `swingbot/core/planning/plan_engine.py` (re-export, mirroring `_resolve_time_stop_days`'s existing entries in the import/`__all__` lists)
- Test: `tests/planning/test_params.py` (create if it does not already exist as a dedicated file — check `tests/planning/` first; if resolver tests already live in a different file following an established convention, add there instead)

**Interfaces:**
- Consumes: `swingbot.core.edge.stops.optimal_time_stop_days` (existing, unmodified), `_journal_entries()` (existing, `params.py`).
- Produces: `config.STALL_EXIT_ENABLED` (bool), `TradePlanV2.stall_exit_day: int | None`, `params._resolve_stall_exit_day(strategy: str) -> int | None` — consumed by Task 11.

- [ ] **Step 1: Add the config `Field`**

Insert after Task 5's three `Field` entries:

```python
    Field("STALL_EXIT_ENABLED", "STALL_EXIT_ENABLED", "Exit quality",
          "Close stalled pre-TP1 positions early",
          type="checkbox", default="false",
          help="If a plan is still open past its strategy's "
               "optimal_time_stop_days (edge/stops.py, needs 40+ journaled "
               "winners for that strategy) and has not yet reached +0.5R, "
               "closes it at market instead of continuing to hold. Pre-TP1 "
               "only -- v92 Hypothesis 2, independent of the older, closed "
               "DATA_DRIVEN_STOPS_ENABLED flag (see the spec's provenance "
               "note). Off until its own TRAIN/VALIDATION shots judge it."),
```

Add `"STALL_EXIT_ENABLED",` to `_SEARCH_CLASSES["searchable"]`.

- [ ] **Step 2: Add the plan field**

In `plan_types.py`, immediately after the `time_stop_days: int | None = None` line:

```python
    # v92 Hypothesis 2: the day, resolved independently of time_stop_days /
    # DATA_DRIVEN_STOPS_ENABLED, past which this plan is a stall-exit
    # candidate if still pre-TP1 and below +0.5R. None when
    # STALL_EXIT_ENABLED is off or the strategy lacks enough journaled
    # winners -- see params._resolve_stall_exit_day.
    stall_exit_day: int | None = None
```

- [ ] **Step 3: Write the failing resolver test**

```python
# tests/planning/test_params.py
from swingbot import config
from swingbot.core.planning import params as plan_params


def test_resolve_stall_exit_day_none_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    assert plan_params._resolve_stall_exit_day("RSI") is None


def test_resolve_stall_exit_day_none_on_lookup_failure(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    monkeypatch.setattr(plan_params, "_journal_entries",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert plan_params._resolve_stall_exit_day("RSI") is None


def test_resolve_stall_exit_day_calls_optimal_time_stop_days(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    monkeypatch.setattr(plan_params, "_journal_entries", lambda: ["entry"])
    import swingbot.core.edge.stops as stops_mod
    monkeypatch.setattr(stops_mod, "optimal_time_stop_days",
                        lambda entries, strategy: 7)
    assert plan_params._resolve_stall_exit_day("RSI") == 7
```

- [ ] **Step 4: Run to verify failure**

Run: `python -m pytest tests/planning/test_params.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_resolve_stall_exit_day'`

- [ ] **Step 5: Implement the resolver**

Append to `swingbot/core/planning/params.py`, after `_resolve_time_stop_days`:

```python
def _resolve_stall_exit_day(strategy: str) -> int | None:
    """Live-path resolution of v92 Hypothesis 2's stall-exit day. Deliberately
    its own flag (STALL_EXIT_ENABLED), never DATA_DRIVEN_STOPS_ENABLED --
    see the spec's provenance note. Same degrade-to-None contract as
    _resolve_time_stop_days: off, thin journal, or a read failure all mean
    'do nothing', never an exception reaching plan construction."""
    if not config.STALL_EXIT_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import optimal_time_stop_days
        return optimal_time_stop_days(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("Stall-exit lookup failed for %s: %s -- not recorded", strategy, exc)
        return None
```

- [ ] **Step 6: Re-export from `plan_engine.py`**

In `swingbot/core/planning/plan_engine.py`, add `_resolve_stall_exit_day` to the `from .params import (...)` block and to `__all__`, in both cases right beside the existing `_resolve_time_stop_days` entry.

- [ ] **Step 7: Run to verify all pass**

Run: `python -m pytest tests/planning/test_params.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py swingbot/core/planning/plan_types.py swingbot/core/planning/params.py swingbot/core/planning/plan_engine.py tests/planning/test_params.py
git commit -m "feat(v92): STALL_EXIT_ENABLED flag, plan field, and resolver"
```

### Task 11: Populate `stall_exit_day` at plan creation

**Files:**
- Modify: `swingbot/core/planning/builders.py` (near line 207-208, beside the existing `plan.time_stop_days = ...` assignment)
- Test: `tests/planning/test_builders.py` (or wherever this file's existing plan-construction tests live — check `tests/planning/` before creating a new file)

**Interfaces:**
- Consumes: `params._resolve_stall_exit_day` (Task 10).
- Produces: `plan.stall_exit_day` populated on every strategy-source plan (mirrors `time_stop_days`; confluence-source plans stay unpopulated, same carve-out `time_stop_days` already has — `build_confluence_plan` does not read this table either).

- [ ] **Step 1: Write the failing test**

```python
def test_strategy_plan_populates_stall_exit_day(monkeypatch):
    from swingbot import config
    from swingbot.core.planning import params as plan_params
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    monkeypatch.setattr(plan_params, "_resolve_stall_exit_day", lambda strategy: 5)
    plan = build_strategy_plan(...)  # use this file's existing fixture/helper call shape
    assert plan.stall_exit_day == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/planning/test_builders.py -v -k stall_exit_day`
Expected: FAIL — `AttributeError: 'TradePlanV2' object has no attribute` or assertion `None == 5` fails

- [ ] **Step 3: Wire the assignment**

In `builders.py`, immediately after the existing `plan.time_stop_days = (...)` line:

```python
    plan.stall_exit_day = plan_params._resolve_stall_exit_day(strategy)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/planning/test_builders.py -v -k stall_exit_day`
Expected: PASS

- [ ] **Step 5: Run the narrow suite and commit**

Run: `python scripts/dev/testrun.py file tests/planning/test_builders.py`

```bash
git add swingbot/core/planning/builders.py tests/planning/test_builders.py
git commit -m "feat(v92): populate stall_exit_day on strategy-source plans"
```

### Task 12: Stall check in the pre-TP1 walk

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (`_scale_out_exit_walk`'s phase-1 loop, lines ~192-215)
- Test: `tests/planning/test_exit_sim_scaleout.py`

**Interfaces:**
- Consumes: `plan.stall_exit_day`, `config.STALL_EXIT_ENABLED`.
- Produces: a new `ExitResult.outcome == "loss"`, `legs[0]["reason"] == "stall_exit"` path, ordered **after** the existing stop-loss check on the same bar (conservative ordering: a real stop breach always wins over a stall exit on the same bar).

**Scope note:** `_single_leg_exit_walk` (used only when `SCALE_OUT_ENABLED` is off) is out of scope for this task — the live default has scale-out on, so the phase-1 loop below is where the measured disposition effect actually lives. Extending the single-leg walk is a follow-up, not silently folded in here.

- [ ] **Step 1: Write the failing tests**

```python
def _bars(closes):
    """Minimal OHLC DataFrame, one row per close, no intrabar excursion."""
    import pandas as pd
    return pd.DataFrame({"High": closes, "Low": closes, "Close": closes})


def test_stall_exit_fires_past_day_threshold_below_half_r(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    plan = _make_plan(stop_loss=90, tp1=120, entry=100, stall_exit_day=3)  # use this
    # file's existing plan-fixture helper; entry at bar 0, price drifts to
    # +0.2R (not yet +0.5R) and holds flat through bar 4
    df = _bars([100, 100, 102, 102, 102, 102])
    result = _scale_out_exit_walk(df, entry_index=0, entry_price=100, plan=plan,
                                  max_holding_days=10)
    assert result.legs[0]["reason"] == "stall_exit"
    assert result.exit_index == 4  # first bar strictly past stall_exit_day=3


def test_stall_exit_does_not_fire_once_half_r_reached(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    plan = _make_plan(stop_loss=90, tp1=120, entry=100, stall_exit_day=3)
    df = _bars([100, 108, 115, 115, 115, 115])  # +0.5R (of the 100->120 target) by bar 1
    result = _scale_out_exit_walk(df, entry_index=0, entry_price=100, plan=plan,
                                  max_holding_days=10)
    assert result.legs[0]["reason"] != "stall_exit"


def test_stop_loss_still_wins_over_stall_exit_on_same_bar(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    plan = _make_plan(stop_loss=90, tp1=120, entry=100, stall_exit_day=1)
    df = _bars([100, 89])  # stop breached exactly when the stall day passes
    result = _scale_out_exit_walk(df, entry_index=0, entry_price=100, plan=plan,
                                  max_holding_days=10)
    assert result.legs[0]["reason"] == "stop"


def test_stall_exit_inert_when_flag_off(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    plan = _make_plan(stop_loss=90, tp1=120, entry=100, stall_exit_day=3)
    df = _bars([100, 100, 102, 102, 102, 102])
    result = _scale_out_exit_walk(df, entry_index=0, entry_price=100, plan=plan,
                                  max_holding_days=10)
    assert result.legs[0]["reason"] != "stall_exit"
```

(Adapt `_make_plan`/`_bars` to whatever fixture helpers `test_exit_sim_scaleout.py` already defines — read the top of that file first; do not introduce a second, differently-named plan-builder helper if one already exists there.)

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/planning/test_exit_sim_scaleout.py -v -k stall_exit`
Expected: FAIL — all four assert on behavior that doesn't exist yet (stall exit never fires)

- [ ] **Step 3: Implement the check**

In `_scale_out_exit_walk`'s phase-1 loop (the `for j in range(entry_index + 1, end + 1):` loop, before TP1 touches), add the stall check **after** the existing `hit_stop`/`hit_target` handling for bar `j` and before the loop's `if reached_trigger and not stop_moved:` line:

```python
        if (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
                and (j - entry_index) > plan.stall_exit_day):
            current_r = (float(close[j]) - entry_price) * sign / risk
            if current_r < 0.5:
                exit_price = float(close[j])
                r = round(current_r, 3)
                return ExitResult(outcome="loss" if r < 0 else "scratch",
                                  runner_outcome=None, entry_index=entry_index,
                                  exit_index=j, entry_price=entry_price, r_total=r,
                                  legs=[{"fraction": 1.0, "exit_price": exit_price,
                                         "r": r, "reason": "stall_exit"}])
```

Add `from swingbot import config` at module top if Task 6 has not already added it.

- [ ] **Step 4: Run to verify all pass**

Run: `python -m pytest tests/planning/test_exit_sim_scaleout.py -v`
Expected: PASS, no regressions on pre-existing tests (flag off by default)

- [ ] **Step 5: Run the narrow suite and commit**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py`

```bash
git add swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_scaleout.py
git commit -m "feat(v92): pre-TP1 stall-exit check in the scale-out walk"
```

### Task 13: Live poll path wiring

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (wherever the live per-bar/per-poll loop applies the pre-TP1 stop/target checks — search for the function that calls `chandelier_stop`/`runner_floor` per Task 6's discovery that both are already shared with this file)
- Test: whichever existing test file covers `plan_manager.py`'s poll path (locate via `Glob("tests/**/test_plan_manager*.py")` before writing)

**Interfaces:**
- Consumes: `config.STALL_EXIT_ENABLED`, `plan.stall_exit_day` (same fields Task 12 reads).
- Produces: the live path closing a stalled plan identically to the backtest walk — the same invariant `chandelier_stop`/`runner_floor` already hold.

- [ ] **Step 1: Locate the live pre-TP1 check**

Run: `grep -n "hit_stop\|stop_loss\|PENDING\|ACTIVE" swingbot/core/planning/plan_manager.py | head -40` to find the equivalent per-poll bar-check function before writing the test — this task's exact line numbers depend on that read, which the executing session performs at task time (this plan does not fabricate line numbers for a file this detailed which none of this plan's earlier research tasks opened).

- [ ] **Step 2: Write the failing test**

Mirror Task 12's `test_stall_exit_fires_past_day_threshold_below_half_r` and `test_stop_loss_still_wins_over_stall_exit_on_same_bar` shapes, against whatever this file's existing poll-path test harness uses to simulate a bar/price update (its own fixture, not `_scale_out_exit_walk`'s raw DataFrame).

- [ ] **Step 3: Implement the same check**

Add the identical condition from Task 12 Step 3 (`config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None and days_held > plan.stall_exit_day and current_r < 0.5`) at the equivalent point in the live poll's stop-check, closing the plan with reason `"stall_exit"` — same string, same ordering-after-stop-loss discipline.

- [ ] **Step 4: Run to verify all pass, then run the narrow suite**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py <the test file found in Step 1>
git commit -m "feat(v92): stall-exit check in the live poll path"
```

### Task 14: Measurement script — Stage 0/1 TRAIN (single comparison, no grid)

**Files:**
- Create: `scripts/backtest/measure_stall_exit.py`

**Interfaces:**
- Consumes: same imports as Task 7's script.
- Produces: printed Stage 0/1 verdict; a results doc.

**Note:** unlike Hypothesis 1, there is no free grid parameter here — `stall_exit_day` comes from the journal via `optimal_time_stop_days`, not a tuned constant. TRAIN is a single flag-off-vs-flag-on comparison.

- [ ] **Step 1: Write the script**

```python
"""v92 Hypothesis 2 -- MAE/time stall-exit. TRAIN comparison (no grid --
stall_exit_day is journal-derived, not tuned).

Run: python scripts/backtest/measure_stall_exit.py [n_tickers]
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "data"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "backtest"))

from fetch_backtest_data import load_cached
from run_backtest_range import _tickers_for_run, window_trades, ALL_STRATEGIES
from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.backtesting.acceptance import arm_trade_from_backtest
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r, evaluate_harvest
from swingbot.core.market.strategy_types import HORIZONS

TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"


def _arm_trades(flag_on, tickers):
    config.STALL_EXIT_ENABLED = flag_on
    out = []
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None:
            continue
        for hk in HORIZONS:
            for strat in ALL_STRATEGIES:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model="v2", scale_out=True,
                                      tp2_mode="levels", frictions=True)
                except Exception:
                    continue
                for tr in window_trades(s, TRAIN_FROM, TRAIN_TO):
                    out.append(arm_trade_from_backtest(tr, ticker=ticker, strategy=strat,
                                                        horizon_key=hk))
    return out


def main():
    tickers = _tickers_for_run(None)
    if len(sys.argv) > 1:
        tickers = tickers[:int(sys.argv[1])]

    print(f"Baseline (flag off), {len(tickers)} tickers...", flush=True)
    baseline = _arm_trades(False, tickers)
    print(f"  {len(baseline)} closed trades")
    mde = mde_expectancy_r(baseline, target_n=len(baseline))
    print(f"Stage 0 MDE (ExpR, target_n={len(baseline)}): {mde:+.4f}R" if mde else "Stage 0 MDE: n/a")

    print(f"Component (flag on), {len(tickers)} tickers...", flush=True)
    component = _arm_trades(True, tickers)
    print(f"  {len(component)} closed trades")

    result = evaluate_harvest(baseline, component, stage="walkforward",
                             structurally_immune_to_wr=False)
    for c in result.clauses:
        print(f"  {c.name}: {c.verdict} -- {c.detail}")
    print(f"OVERALL: {result.verdict}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (dispatch to `backtest-runner`)**

Command: `python scripts/backtest/measure_stall_exit.py`

- [ ] **Step 3: Record the TRAIN result**

Write `docs/superpowers/results/2026-09-16-v92-stall-exit-train.md`. If `expectancy_gain` or `win_rate_floor` FAILs on TRAIN, this closes the hypothesis here (`NO_ELIGIBLE_CELL`-equivalent, since there is no grid to retry) — document and stop, do not proceed to Task 15. This is the hypothesis the spec flagged as a real coin flip, not a foregone conclusion.

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest/measure_stall_exit.py docs/superpowers/results/2026-09-16-v92-stall-exit-train.md
git commit -m "measure(v92): H2 stall-exit TRAIN comparison"
```

### Task 15: Stage 2 walk-forward folds

**Files:**
- Modify: `scripts/backtest/measure_stall_exit.py` (add the same `--fold` support as Task 8, reusing Task 8's `FOLDS` dict — copy it verbatim rather than importing across the two sibling scripts, matching this repo's existing script-to-script import convention of copying small shared constants rather than creating a third shared module for two call sites)

**Interfaces:**
- Consumes: Task 14's TRAIN PASS.
- Produces: `docs/superpowers/results/2026-09-16-v92-stall-exit-walkforward.md`.

- [ ] **Step 1: Add fold support** (identical shape to Task 8 Step 1)

- [ ] **Step 2: Run all three folds (dispatch to `backtest-runner`)**

- [ ] **Step 3: Apply the same fold-stability rule as Task 8 Step 3**, record the result. If it fails, stop here (do not proceed to Task 16).

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest/measure_stall_exit.py docs/superpowers/results/2026-09-16-v92-stall-exit-walkforward.md
git commit -m "measure(v92): H2 stall-exit walk-forward folds"
```

### Task 16: Stage 3 VALIDATION shot + default decision

**Files:**
- Modify: `scripts/backtest/measure_stall_exit.py` (add `--validation`, mirroring Task 9)
- Modify: `swingbot/config.py` (flip `STALL_EXIT_ENABLED`'s default only if this PASSES)

**Interfaces:**
- Consumes: Task 15's fold PASS.
- Produces: `docs/superpowers/results/2026-09-16-v92-stall-exit-validation.md`; a closed-pre-registration row.

- [ ] **Step 1: Add validation support and permutation-test call** (identical shape to Task 9 Step 1)

- [ ] **Step 2: Run once (dispatch to `backtest-runner`) — the one-shot budget**

- [ ] **Step 3: Record the result and decide the default**, including the win→non-win outcome-flip disclosure table — this is the clause most likely to explain a FAIL here, since the mechanism's whole risk is converting would-be TP1 touches into early losses.

- [ ] **Step 4: Add the closed row to `backtest-methodology.md`**

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_stall_exit.py docs/superpowers/results/2026-09-16-v92-stall-exit-validation.md docs/claude/backtest-methodology.md swingbot/config.py
git commit -m "measure(v92): H2 stall-exit VALIDATION shot + default decision"
```

---

# Phase 4 — Final verification

### Task 17: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Dispatch the `test-runner` subagent, or run `python scripts/dev/testrun.py full` directly. Expect `0 failed`, `0 xfailed`.

- [ ] **Step 2: Fix forward from any failure**

Per `docs/claude/document-conventions.md`: a red result here is this plan's own regression — fix from the failures the run names, then re-run once more.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "test(v92): full-suite verification for exit-quality harvest"
```
