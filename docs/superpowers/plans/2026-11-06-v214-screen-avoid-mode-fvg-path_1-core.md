# v214 — Avoid mode for the idea screen, and the overhead bearish-gap idea — Part 1: core (V214-1..V214-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md`](../specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md)
**Index:** [`2026-11-06-v214-screen-avoid-mode-fvg-path_0-index.md`](2026-11-06-v214-screen-avoid-mode-fvg-path_0-index.md). Its Goal, Architecture, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and `## Task ledger` apply to every task here. Its signatures are the contract.

This part covers four things: the raising FVG helper (G4), the verdict's avoid mode (G1, G5), the ledger vocabulary (G5), and `Idea.mode`/`Idea.states` with the idea module `fvg_overhead_aged` (G1, G3).

**Sequencing gate, checked by symbol.** The index's commit-log grep also matches v211's *docs* commits (`docs(v211): plan part 2 -- ... (V211-4..6)`), so it is not a reliable gate. Every task in this part starts with the symbol check below. If either command prints nothing, stop and report `BLOCKED: v211 V211-4/V211-6 not merged on main`.

```bash
git grep -n "context_kind" main -- swingbot/core/backtesting/screen/ideas/__init__.py
git grep -n "checkpoint_dir" main -- scripts/backtest/screen_idea.py
```

**The v211 pins**, which every task touching `verdict.py` or `ideas/__init__.py` runs:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
git grep -ln "hypotheses_pre_v211" -- tests
```

The third command names the test file that loads the hypothesis golden; run it with `testrun.py file` as well. All three must stay green, untouched.

# Phase 1 — Instruments (wave A)

### Task V214-1: Raising FVG scan helper; live detector byte-identical (G4)

**Model:** sonnet — a mechanical split of one function, with a parity pin and no design choice.

**Files:**
- Modify: `swingbot/core/market/fvg.py` (`find_fair_value_gaps_detailed`, today at :109-154; new `scan_fair_value_gaps` directly above it)
- Create: `tests/market/test_fvg_scan_helper.py` (suite `market-signals`, already covers `tests/market/`)

**Interfaces:**
- Consumes: nothing new. It uses `fvg.LOOKBACK_BARS` (100) and `fvg.MAX_GAPS_PER_SIDE` (3), which exist today.
- Produces (V214-5 calls it):
  - `fvg.scan_fair_value_gaps(df: pd.DataFrame, lookback: int = LOOKBACK_BARS, max_per_side: int = MAX_GAPS_PER_SIDE) -> list[dict]`: today's detection body, unchanged, without the `try`. It raises on bad input, for example `KeyError` for a missing `High` column or `TypeError` for `None`.
  - `find_fair_value_gaps_detailed(df, lookback=LOOKBACK_BARS, max_per_side=MAX_GAPS_PER_SIDE) -> list`: `try: return scan_fair_value_gaps(df, lookback, max_per_side)` / `except Exception: return []`. Same signature, same docstring, same output for every input.

- [ ] **Step 0: Sequencing gate.** Run the two `git grep` commands from this part's header. Both must print a line.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_fvg_scan_helper.py`:

```python
"""v214 G4: the FVG scan splits into a raising helper (the screen's) and the
live wrapper that keeps its blanket swallow, byte-identical to before."""
import hashlib
import json

import pandas as pd
import pytest

from swingbot.core.market import fvg
from tests.backtesting.screen.helpers import random_walk
from tests.market.fvg_frames import BEAR_THIRD, FLAT, bar_frame, gap_frame, witness_frame

#: sha256 of json.dumps([[gap rounded to 10 dp, ...] per prefix df.iloc[:t+1]],
#: sort_keys=True), captured from find_fair_value_gaps_detailed BEFORE v214
#: (main at 5c5d1990). A change to the scan body changes these.
PRE_V214_DIGESTS = {
    ("witness", 126): "0d1d8ef4d366db583ae4eccd6aa7a4188e7027608ed807c17605881012bda6b9",
    ("witness", 7): "6a231876944681381aa681e6fec9b1cfcbe6dfc9326bc3b12a261ba96ea7033b",
    ("witness", 3): "6b719750d698d25684f8c358778e47fed8a2e2e18e20ef3cd2a72a0d522e5bd5",
    ("random_walk", 21): "0690f8482987d35fed2e0415d57e1513f90df542982fb8c809b1856814ac8be2",
}


def _frame(kind, seed):
    return witness_frame(seed=seed) if kind == "witness" else random_walk(700, seed=seed)


def _rounded(gap):
    return {k: (round(v, 10) if isinstance(v, float) else v) for k, v in gap.items()}


def _digest(fn, df):
    out = [[_rounded(g) for g in fn(df.iloc[: t + 1])] for t in range(len(df))]
    return hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("key", sorted(PRE_V214_DIGESTS))
def test_the_live_detector_output_is_byte_identical_to_before(key):
    assert _digest(fvg.find_fair_value_gaps_detailed, _frame(*key)) == PRE_V214_DIGESTS[key]


@pytest.mark.parametrize("key", sorted(PRE_V214_DIGESTS))
def test_the_helper_returns_exactly_what_the_live_detector_returns(key):
    df = _frame(*key)
    for t in range(len(df)):
        part = df.iloc[: t + 1]
        assert fvg.scan_fair_value_gaps(part) == fvg.find_fair_value_gaps_detailed(part)


def test_the_helper_passes_lookback_and_max_per_side_through():
    df = witness_frame(seed=126)
    for lookback, per_side in ((20, 1), (100, 3), (260, 5)):
        assert (fvg.scan_fair_value_gaps(df, lookback, per_side)
                == fvg.find_fair_value_gaps_detailed(df, lookback, per_side))


def test_a_hand_built_bearish_gap_keeps_its_exact_geometry():
    gap = {"bottom": 98.5, "top": 99.0, "mid": 98.75, "bar_index": 21, "direction": "bearish"}
    df = gap_frame(FLAT, BEAR_THIRD)
    assert fvg.scan_fair_value_gaps(df) == [gap]
    assert fvg.find_fair_value_gaps_detailed(df) == [gap]


def test_fewer_than_three_bars_is_no_gap_in_both():
    df = bar_frame([FLAT, FLAT])
    assert fvg.scan_fair_value_gaps(df) == [] == fvg.find_fair_value_gaps_detailed(df)


@pytest.mark.parametrize("bad", [None, pd.DataFrame({"Low": [1.0, 2.0, 3.0]})])
def test_the_helper_raises_where_the_live_detector_swallows(bad):
    with pytest.raises(Exception):
        fvg.scan_fair_value_gaps(bad)
    assert fvg.find_fair_value_gaps_detailed(bad) == []


def test_the_live_detector_swallows_whatever_the_helper_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", boom)
    assert fvg.find_fair_value_gaps_detailed(witness_frame(seed=126)) == []


def test_the_live_wrapper_callers_are_unchanged():
    df = gap_frame(FLAT, BEAR_THIRD)
    assert fvg.find_fair_value_gaps(df) == [(98.75, "FVG (bearish)")]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_fvg_scan_helper.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.market.fvg' has no attribute 'scan_fair_value_gaps'`. The two `byte_identical` cases and the hand-built geometry case already pass on today's code, which proves the digests were captured correctly.

- [ ] **Step 3: Implement `scan_fair_value_gaps` in `swingbot/core/market/fvg.py`**

Move the body of `find_fair_value_gaps_detailed`, from `highs = df["High"].values` through `return bullish_gaps[-max_per_side:] + bearish_gaps[-max_per_side:]`, verbatim into the new function, one indent level shallower. Do not reorder, rename or "tidy" anything. Its docstring:

```python
    """The FVG scan itself, raising on bad input (v214 G4).

    Same output as find_fair_value_gaps_detailed() for every frame it can
    read. The idea screen calls this one, so a malformed frame aborts the
    ticker with a counted error instead of reading as "no gap" and shrinking
    N silently. Live callers keep the swallowing wrapper below.
    """
```

`find_fair_value_gaps_detailed` keeps its signature and docstring. Append one docstring line: `Never raises: any error from scan_fair_value_gaps() reads as no gaps (v214 keeps the live behaviour).` Its body becomes exactly:

```python
    try:
        return scan_fair_value_gaps(df, lookback, max_per_side)
    except Exception:
        return []
```

The call must go through the module global `scan_fair_value_gaps`, which the monkeypatch test relies on. Complexity: the helper carries today's 11 branches, and the wrapper drops to 2. Both stay < 15.

- [ ] **Step 4: Run the test to verify it passes, and the existing FVG callers' tests**

```bash
python scripts/dev/testrun.py file tests/market/test_fvg_scan_helper.py
python scripts/dev/testrun.py file tests/market/test_fvg_displacement.py
python scripts/dev/testrun.py file tests/market/test_levels_fvg_mode.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_fvg_attribution.py
python scripts/dev/testrun.py file tests/charts/test_chart_geometry.py
python scripts/dev/complexity_gate.py
```

Expected: all `0 failed`, and the complexity gate passes.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/fvg.py tests/market/test_fvg_scan_helper.py
git commit -m "feat(v214): raising FVG scan helper; live detector byte-identical (V214-1)"
```

### Task V214-2: Verdict avoid mode — mirrored clauses, control arm, mode-aware p (G1, G5)

**Model:** opus — this is the frozen pass rule that every later avoid verdict rests on; an off-by-sign or a wrong boundary is a silent licence.

**Files:**
- Modify: `swingbot/core/backtesting/screen/verdict.py` (module docstring, constants, `Verdict`, new `ControlArm`, `years_negative`, `avoid_mean_clause`, `avoid_ci_clause`, `bootstrap`, `label`, `control_arm`, `decide`)
- Create: `tests/backtesting/screen/test_verdict_avoid.py` (suite `backtesting-arms` covers `tests/backtesting/screen/`)

**Interfaces:**
- Consumes: `stats.week_cluster_bootstrap`, `stats.WEEK_BOOTSTRAP_RESAMPLES`, `stats.WEEK_BOOTSTRAP_SEED`. These exist, and `verdict.py` already uses them.
- Produces (V214-7 and V214-9 consume these; the names and shapes are final):
  - `MODES = ("edge", "avoid")` and `SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"`.
  - `years_negative(table) -> int`: the count of years with `n > 0` and mean strictly `< 0`. An empty year is not counted, so it counts against the clause.
  - `avoid_mean_clause(delta) -> bool`: `delta is not None and delta <= -PASS_EXP_R + _TOLERANCE`.
  - `avoid_ci_clause(high) -> bool`: `high is not None and high < 0`.
  - `bootstrap(events, *, n_resamples: int, seed: int, mode: str = "edge") -> (low, high, p)`. In edge mode p is the share of draws `<= 0.0` (today's p); in avoid mode it is the share `>= 0.0`. `low` and `high` do not depend on the mode.
  - `@dataclass(frozen=True) class ControlArm: n: int; delta_exp_r: float | None; ci_low: float | None; ci_high: float | None; per_year: dict`.
  - `control_arm(events, *, n_resamples: int, seed: int) -> ControlArm`: `events` are `PairedEvent`s whose `d` is `R_event − mean(R_control)`.
  - `Verdict` gains trailing `mode: str = "edge"`, `years_negative: int | None = None`, `control: ControlArm | None = None`, after `clauses`. The existing 9 positional fields are unchanged, so `Verdict("SCREEN-FAIL", 412, ...)` with 9 arguments, as the runner tests build it, keeps working.
  - `label(clauses: dict, mode: str = "edge") -> str`.
  - `decide(events, *, mode: str = "edge", control=None, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=stats.WEEK_BOOTSTRAP_SEED) -> Verdict`. In avoid mode the `clauses` keys are exactly `("exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n")`. A mode outside `MODES`, or a `control` passed in edge mode, raises `ValueError`. Avoid mode with `control=None` means no control events: N_c = 0, which gives `SCREEN-UNDERPOWERED`.

- [ ] **Step 0: Sequencing gate.** Run the two `git grep` commands from this part's header. Both must print a line.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/screen/test_verdict_avoid.py`:

```python
"""v214 G1: the avoid mode's six frozen clauses. Against the matched null:
mean(d) <= -0.10R, upper 95% bound < 0, mean(d) < 0 in >= 7 of 2011-2019
(an empty year counts against), N >= 300. Against the control arm:
mean(d_c) <= -0.10R, upper bound < 0, N_c >= 300. N or N_c < 300 is
UNDERPOWERED; any other failing clause is FAIL. Edge mode is unchanged."""
import dataclasses
import functools
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.backtesting.screen import verdict

FAST = 500
AVOID_KEYS = ("exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n")


def _events(n, d=-0.25, years=verdict.YEARS):
    """n events, one per ISO week, cycling through ``years`` (as test_verdict.py)."""
    out = []
    for i in range(n):
        day = date(years[i % len(years)], 1, 4) + timedelta(weeks=i // len(years))
        out.append(verdict.PairedEvent(day.isoformat(), d(i) if callable(d) else d))
    return out


def _avoid(events, control):
    return verdict.decide(events, mode="avoid", control=control, n_resamples=FAST)


def test_mode_constants_are_the_spec_values():
    assert verdict.MODES == ("edge", "avoid")
    assert verdict.SCREEN_AVOID_PASS == "SCREEN-AVOID-PASS"


@pytest.mark.parametrize("delta, holds", [
    (-0.10, True), (-0.0999, False), (-0.25, True), (0.0, False), (0.10, False), (None, False)])
def test_avoid_mean_clause_mirrors_the_tolerance(delta, holds):
    assert verdict.avoid_mean_clause(delta) is holds


def test_avoid_mean_clause_survives_float_summation_at_exactly_minus_ten_cents():
    assert verdict.avoid_mean_clause(float(np.mean([-0.1] * 300)))


@pytest.mark.parametrize("high, holds", [(-1e-9, True), (0.0, False), (0.01, False), (None, False)])
def test_avoid_ci_clause_is_strict_on_the_upper_bound(high, holds):
    assert verdict.avoid_ci_clause(high) is holds


def test_years_negative_counts_strictly_negative_non_empty_years():
    table = {2011: (3, -0.1), 2012: (0, None), 2013: (2, 0.0), 2014: (1, 0.2), 2015: (5, -1e-9)}
    assert verdict.years_negative(table) == 2


def test_avoid_p_is_the_share_of_resamples_at_or_above_zero():
    below, above = _events(300, d=-0.25), _events(300, d=0.25)
    assert verdict.bootstrap(below, n_resamples=FAST, seed=42, mode="avoid")[2] == 0.0
    assert verdict.bootstrap(below, n_resamples=FAST, seed=42, mode="edge")[2] == 1.0
    assert verdict.bootstrap(above, n_resamples=FAST, seed=42, mode="avoid")[2] == 1.0
    assert verdict.bootstrap(above, n_resamples=FAST, seed=42)[2] == 0.0


def test_the_bounds_do_not_depend_on_the_mode_and_the_two_p_cover_everything():
    mixed = _events(400, d=lambda i: (-0.6, 0.2, 0.1, -0.3, 0.05)[i % 5])
    edge = verdict.bootstrap(mixed, n_resamples=FAST, seed=42)
    avoid = verdict.bootstrap(mixed, n_resamples=FAST, seed=42, mode="avoid")
    assert edge[:2] == avoid[:2]
    assert edge[2] + avoid[2] >= 1.0 - 1e-12


def test_all_six_clauses_holding_is_an_avoid_pass():
    out = _avoid(_events(300), _events(300))
    assert out.verdict == "SCREEN-AVOID-PASS" and out.mode == "avoid"
    assert tuple(out.clauses) == AVOID_KEYS and all(out.clauses.values())
    assert out.years_negative == 9 and out.p == 0.0
    assert out.control == verdict.ControlArm(
        n=300, delta_exp_r=pytest.approx(-0.25), ci_low=pytest.approx(-0.25),
        ci_high=pytest.approx(-0.25), per_year=verdict.per_year(_events(300)))


def test_exactly_minus_ten_cents_on_both_arms_passes():
    assert _avoid(_events(300, d=-0.10), _events(300, d=-0.10)).verdict == "SCREEN-AVOID-PASS"


def test_a_hair_short_of_minus_ten_cents_fails_on_the_null_clause():
    out = _avoid(_events(300, d=-0.0999), _events(300))
    assert out.verdict == "SCREEN-FAIL" and out.clauses["exp_r"] is False


def test_a_control_arm_short_of_minus_ten_cents_fails():
    out = _avoid(_events(300), _events(300, d=-0.05))
    assert out.verdict == "SCREEN-FAIL"
    assert out.clauses["control_exp_r"] is False and out.clauses["control_ci"] is True


def test_an_upper_bound_of_exactly_zero_on_the_control_arm_fails():
    out = _avoid(_events(300), _events(300, d=0.0))
    assert out.control.ci_high == 0.0 and out.clauses["control_ci"] is False
    assert out.verdict == "SCREEN-FAIL"


def test_299_events_is_underpowered_even_when_everything_else_passes():
    out = _avoid(_events(299), _events(300))
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.clauses == dict(zip(AVOID_KEYS, (True, True, True, False, True, True, True)))


def test_300_events_and_300_control_events_is_powered():
    assert _avoid(_events(300), _events(300)).verdict == "SCREEN-AVOID-PASS"


def test_299_control_events_is_underpowered_even_when_everything_else_passes():
    out = _avoid(_events(300), _events(299))
    assert out.verdict == "SCREEN-UNDERPOWERED"
    assert out.clauses == dict(zip(AVOID_KEYS, (True, True, True, True, True, True, False)))


def test_no_control_events_is_underpowered_not_fail():
    for control in (None, []):
        out = _avoid(_events(300), control)
        assert out.verdict == "SCREEN-UNDERPOWERED"
        assert out.control == verdict.ControlArm(0, None, None, None, verdict.per_year([]))
        assert out.clauses["control_n"] is False


def test_an_empty_year_counts_against_the_avoid_years_clause():
    six = _avoid(_events(300, years=verdict.YEARS[:6]), _events(300))
    assert six.years_negative == 6 and six.clauses["years"] is False
    assert six.verdict == "SCREEN-FAIL"
    seven = _avoid(_events(300, years=verdict.YEARS[:7]), _events(300))
    assert seven.years_negative == 7 and seven.verdict == "SCREEN-AVOID-PASS"


def test_an_avoid_idea_never_gets_an_edge_label_and_vice_versa():
    """G5: whatever the events, an avoid verdict is AVOID-PASS, FAIL or
    UNDERPOWERED; an edge verdict never reads AVOID-PASS."""
    for d in (0.25, 0.10, 0.0, -0.10, -0.25):
        avoid = _avoid(_events(300, d=d), _events(300, d=d))
        edge = verdict.decide(_events(300, d=d), n_resamples=FAST)
        assert avoid.verdict != verdict.SCREEN_PASS
        assert edge.verdict != verdict.SCREEN_AVOID_PASS
    assert _avoid(_events(300, d=0.25), _events(300, d=0.25)).verdict == "SCREEN-FAIL"


def test_label_is_table_driven_per_mode():
    assert verdict.label(dict.fromkeys(AVOID_KEYS, True), "avoid") == "SCREEN-AVOID-PASS"
    assert verdict.label({"exp_r": True, "ci": True, "years": True, "n": True}) == "SCREEN-PASS"
    assert verdict.label({**dict.fromkeys(AVOID_KEYS, True), "control_n": False},
                         "avoid") == "SCREEN-UNDERPOWERED"


def test_edge_mode_is_today_s_verdict_exactly():
    events = _events(400, d=lambda i: 0.3 if i % 3 else -0.1)
    plain = verdict.decide(events, n_resamples=FAST)
    assert verdict.decide(events, mode="edge", n_resamples=FAST) == plain
    assert tuple(plain.clauses) == ("exp_r", "ci", "years", "n")
    assert (plain.mode, plain.years_negative, plain.control) == ("edge", None, None)
    low, high, p = verdict.bootstrap(events, n_resamples=FAST, seed=42)
    assert (plain.ci_low, plain.ci_high, plain.p) == (low, high, p)


def test_verdict_fields_append_after_the_original_nine():
    assert [f.name for f in dataclasses.fields(verdict.Verdict)] == [
        "verdict", "n", "delta_exp_r", "ci_low", "ci_high", "p", "years_positive",
        "per_year", "clauses", "mode", "years_negative", "control"]
    legacy = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {})
    assert (legacy.mode, legacy.years_negative, legacy.control) == ("edge", None, None)


def test_the_partial_monkeypatch_the_runner_tests_use_still_works():
    fast = functools.partial(verdict.decide, n_resamples=FAST)
    assert fast(_events(300), mode="avoid", control=_events(300)).verdict == "SCREEN-AVOID-PASS"
    assert fast(_events(300, d=0.25)).verdict == "SCREEN-PASS"


def test_an_unknown_mode_or_an_edge_control_is_refused():
    with pytest.raises(ValueError, match="mode"):
        verdict.decide(_events(300), mode="veto", n_resamples=FAST)
    with pytest.raises(ValueError, match="control"):
        verdict.decide(_events(300), control=_events(300), n_resamples=FAST)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict_avoid.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.screen.verdict' has no attribute 'MODES'`, and more of the same.

- [ ] **Step 3: Implement the avoid mode in `swingbot/core/backtesting/screen/verdict.py`**

- **Module docstring.** Append one paragraph. It names the six avoid clauses as listed in this test file's docstring, the avoid p (the share of resamples `>= 0`, the same ledger BH family), and `SCREEN-AVOID-PASS`. It also says that edge mode is unchanged.
- **Constants.** `MODES = ("edge", "avoid")` and `SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"` go beside the existing labels. Add `_PASS_LABEL = {"edge": SCREEN_PASS, "avoid": SCREEN_AVOID_PASS}` and `_POWER_CLAUSES = {"edge": ("n",), "avoid": ("n", "control_n")}`. Also add `_P_SIDE = {"edge": np.less_equal, "avoid": np.greater_equal}`, which `bootstrap` reads as `float(np.mean(_P_SIDE[mode](draws, 0.0)))`.
- **`ControlArm`** is a frozen dataclass placed above `Verdict`. `Verdict` gains its three trailing fields with the defaults from Interfaces.
- **`years_negative`, `avoid_mean_clause`, `avoid_ci_clause`** each mirror their edge twin: `years_positive`, `mean_clause`, `ci_clause`.
- **`label(clauses, mode="edge")`.** UNDERPOWERED if any key in `_POWER_CLAUSES[mode]` is False. Otherwise `_PASS_LABEL[mode]` if all clauses hold, else FAIL. For an edge clause dict it is today's function exactly.
- **`control_arm(events, *, n_resamples, seed)`.** It takes `events = list(events)`, then `low, high, _ = bootstrap(events, n_resamples=n_resamples, seed=seed)`, and returns `ControlArm(len(events), mean_d([], events), low, high, per_year(events))`. It uses the same seed as the null pairing: the two arms are separate statistics, so one frozen seed is enough.
- **`decide`.** It is split so that each piece stays well under complexity 15:

```python
def _check_mode(mode: str, control) -> None:
    if mode not in MODES:
        raise ValueError(f"verdict mode {mode!r} is not one of {MODES}")
    if mode == "edge" and control is not None:
        raise ValueError("an edge verdict takes no control arm")


def _avoid_clauses(delta, high, negative: int, n: int, arm: ControlArm) -> dict:
    return {"exp_r": avoid_mean_clause(delta), "ci": avoid_ci_clause(high),
            "years": years_clause(negative), "n": n_clause(n),
            "control_exp_r": avoid_mean_clause(arm.delta_exp_r),
            "control_ci": avoid_ci_clause(arm.ci_high), "control_n": n_clause(arm.n)}
```

`decide` calls `_check_mode`, then computes `delta`, `low, high, p = bootstrap(..., mode=mode)`, `table` and `positive` exactly as today. In edge mode it returns today's `Verdict(...)` unchanged, with the 4-key dict and the default trailing fields. In avoid mode it builds `arm = control_arm(control or [], ...)` and `negative = years_negative(table)`, and returns `Verdict(label(clauses, "avoid"), len(events), delta, low, high, p, positive, table, clauses, mode="avoid", years_negative=negative, control=arm)`. Put the avoid branch in its own `_avoid_verdict(...)` helper if `decide` would otherwise pass complexity 6.

- [ ] **Step 4: Run the test to verify it passes, then today's verdict tests and the v211 pins**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict_avoid.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/complexity_gate.py
```

Then run the three v211 pins from this part's header. Expected: all `0 failed`. `test_verdict.py` is untouched and green, which proves edge identity, the 4-key `clauses` pin included.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/verdict.py tests/backtesting/screen/test_verdict_avoid.py
git commit -m "feat(v214): verdict avoid mode -- mirrored clauses, control arm, mode-aware p (V214-2)"
```

### Task V214-3: `SCREEN-AVOID-PASS` in the ledger vocabulary and the admin research API (G5)

**Model:** haiku — it appends one string to a pinned tuple and adds two tests.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py` (`VERDICTS` at :120-122 and the `#:` comment above it)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py` (the `VERDICTS` pin at :20-23; the `test_a_screen_row_validates` parametrize at :152)
- Modify: `tests/admin/test_api_v1_research.py` (append one test)

**Interfaces:**
- Consumes: nothing.
- Produces: `stats.VERDICTS` = today's 13 labels, then `"SCREEN-AVOID-PASS"` **last**. It is the same string as `verdict.SCREEN_AVOID_PASS` (V214-2); V214-7 cross-checks the two. Three consumers pick it up with no change of their own: `validate_ledger_row`, `scripts/reports/preregistration_ledger.py` (`choices=stats.VERDICTS`) and `GET /api/v1/research/ledger` (`"verdicts": list(stats.VERDICTS)`). The research page's `VERDICT_TONE` deliberately leaves a new label neutral (`research.ts`: *"A verdict added to the ledger later stays neutral"*). No frontend change.

- [ ] **Step 0: Sequencing gate.** Run the two `git grep` commands from this part's header. Both must print a line.

- [ ] **Step 1: Write the failing tests**

In `tests/backtesting/test_instrument_stats_ledger.py`, extend the pin in `test_fields_and_vocabularies_are_the_plan_set` to:

```python
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED", "COST", "SAVED", "INCONCLUSIVE",
                              "DESCRIPTION", "SCREEN-AVOID-PASS")
```

Change the parametrize of `test_a_screen_row_validates` to:

```python
@pytest.mark.parametrize("verdict", ["SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED",
                                     "SCREEN-AVOID-PASS"])
```

Append to the same file:

```python
def test_the_avoid_label_is_appended_last_and_the_old_order_is_kept():
    """v214: an addition, never a reorder; the committed ledger is never edited."""
    assert stats.VERDICTS[-1] == "SCREEN-AVOID-PASS"
    assert stats.VERDICTS.count("SCREEN-AVOID-PASS") == 1
    rows = stats.load_ledger()
    assert all(row["verdict"] in stats.VERDICTS for row in rows)


def test_an_avoid_row_enters_the_same_bh_family():
    rows = [_row(id="a", p=0.01), _row(id="b", verdict="SCREEN-AVOID-PASS",
                                       instrument="screen-v1", p=0.04)]
    for row in rows:
        stats.validate_ledger_row(row)
    assert stats.ledger_qvalues(rows) == {"a": pytest.approx(0.02), "b": pytest.approx(0.04)}
```

Append to `tests/admin/test_api_v1_research.py`:

```python
def test_the_avoid_label_is_listed_and_a_row_carrying_it_renders(logged_in, ledger):
    """v214: SCREEN-AVOID-PASS reaches the SPA through the vocabulary and a row."""
    ledger([_row(id="screen-demo", instrument="screen-v1", verdict="SCREEN-AVOID-PASS")])
    body = logged_in.get(_URL).get_json()
    assert body["verdicts"][-1] == "SCREEN-AVOID-PASS"
    assert body["rows"][0]["verdict"] == "SCREEN-AVOID-PASS"
    assert body["rows"][0]["q"] == pytest.approx(0.03)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py
```

Expected: FAIL. The tuple pin mismatches, the new parametrize case and the avoid row raise a validation error (`verdict`), and in the API test the ledger fails to load (non-200, so `get_json()` has no `verdicts`).

- [ ] **Step 3: Append `"SCREEN-AVOID-PASS"` to `stats.VERDICTS`**

Add it last, after `"DESCRIPTION"`. Extend the `#:` comment with one sentence: `v214 appends SCREEN-AVOID-PASS: an avoid-mode screen pass (six clauses against the null and a control arm), which licenses a veto spec only; its p (share of resamples >= 0) is in the same BH family.`

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py
git grep -ln "stats.VERDICTS" -- tests
```

Run every test file the last command lists with `testrun.py file` as well. Expected: all `0 failed`. The API test logs in with the fixture's own test client (`_LOGIN` is the test app's credentials, not `.env`'s), so no database replica is needed for it.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py tests/admin/test_api_v1_research.py
git commit -m "feat(v214): SCREEN-AVOID-PASS in the ledger vocabulary and research API (V214-3)"
```

### Task V214-4: `Idea.mode` and `Idea.states`; edge-mode witness pin (G1)

**Model:** sonnet — two dataclass fields and a validator in the established `_problem` pattern, on a file v211 also edits.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (module docstring, `MODES`, `_mode_problem`, `Idea` fields, `Idea.__post_init__`, `_load`)
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (append tests; no existing pin changes)

**Interfaces:**
- Consumes: V211-4's `Idea.context_kind` and `_context_problem`. Both must be on `main` (Step 0).
- Produces (V214-5, V214-6, V214-7 and V214-9 read these):
  - `ideas.MODES = ("edge", "avoid")`: the same tuple as `verdict.MODES` (V214-2). V214-7 cross-checks the two.
  - `Idea.mode: str = "edge"` and `Idea.states: Callable[[pd.DataFrame], pd.DataFrame] | None = None`: two dataclass fields placed **directly after `context_kind`**, in that order. `_load` reads them from module attributes `MODE` (default `"edge"`) and `states` (default `None`).
  - `_mode_problem(idea: "Idea") -> str | None`, which refuses four cases:
    - a mode outside `MODES`;
    - an avoid idea without `states`;
    - an edge idea with `states`;
    - an avoid idea whose `entry != "next_open"` or `race_shape != "fixed"`.
  - `__post_init__` chains it last: `_side_problem(self) or _shape_problem(self) or _context_problem(self) or _mode_problem(self)`.

- [ ] **Step 0: Sequencing gate.** Run the two `git grep` commands from this part's header. Both must print a line. Then read the current `Idea` field list and `__post_init__` in `ideas/__init__.py`, because v211 may have changed their shape since this plan was written. The symbols here are authoritative; the line numbers are not.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_ideas_registry.py`. It already defines `_events`, `_levels` and `_fake_module(monkeypatch, name, **attrs)`, and imports `dataclasses`.

```python
def _states(df):
    return df


def test_modes_and_the_defaults():
    """v214 G1: MODE is part of the frozen definition, like RACE/DIRECTION/ENTRY."""
    assert ideas.MODES == ("edge", "avoid")
    idea = Idea(name="x", events=_events, time_cap_bars=5)
    assert (idea.mode, idea.states) == ("edge", None)


def test_every_registered_idea_reads_edge_mode_with_no_states():
    """v214 witness: every idea frozen before v214 reads MODE = "edge" and no
    states(df), so its verdict, results doc and hypothesis stay byte-identical."""
    assert {n: (i.mode, i.states) for n, i in IDEAS.items()} == {
        n: ("edge", None) for n in IDEAS}


def test_mode_and_states_sit_directly_after_context_kind():
    names = [f.name for f in dataclasses.fields(Idea)]
    at = names.index("context_kind")
    assert names[at + 1: at + 3] == ["mode", "states"]


def test_load_reads_mode_and_states_and_defaults_to_edge(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_edge_default", CAP=10)
    avoid = _fake_module(monkeypatch, "fake_avoid", CAP=20, MODE="avoid", states=_states)
    assert (ideas._load(plain).mode, ideas._load(plain).states) == ("edge", None)
    loaded = ideas._load(avoid)
    assert loaded.mode == "avoid" and loaded.states is _states


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="mode 'veto'"):
        Idea(name="x", events=_events, time_cap_bars=20, mode="veto")


def test_an_avoid_idea_needs_states_and_an_edge_idea_refuses_them():
    with pytest.raises(ValueError, match="avoid idea needs states"):
        Idea(name="x", events=_events, time_cap_bars=20, mode="avoid")
    with pytest.raises(ValueError, match="edge idea takes no states"):
        Idea(name="x", events=_events, time_cap_bars=20, states=_states)
    idea = Idea(name="x", events=_events, time_cap_bars=20, mode="avoid", states=_states)
    assert idea.mode == "avoid" and idea.states is _states


def test_an_avoid_idea_races_the_fixed_shape_from_the_next_open():
    with pytest.raises(ValueError, match="fixed shape from the next open"):
        Idea(name="x", events=_events, time_cap_bars=60, race_shape="trail",
             mode="avoid", states=_states)
    with pytest.raises(ValueError, match="fixed shape from the next open"):
        Idea(name="x", events=_events, time_cap_bars=20, direction="short",
             entry="level", levels=_levels, mode="avoid", states=_states)


def test_load_refuses_an_avoid_module_without_states(monkeypatch):
    bad = _fake_module(monkeypatch, "fake_avoid_no_states", CAP=20, MODE="avoid")
    with pytest.raises(ValueError, match="states"):
        ideas._load(bad)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL, with `AttributeError: module ... has no attribute 'MODES'` and `TypeError: Idea.__init__() got an unexpected keyword argument 'mode'`. Every test that was there before still passes.

- [ ] **Step 3: Implement in `swingbot/core/backtesting/screen/ideas/__init__.py`**

- **`MODES = ("edge", "avoid")`** goes after `CONTEXT_KINDS`, with the comment `#: v214: "edge" (every idea before v214: must beat the matched null) or "avoid" (must do worse than the null AND a control arm; licenses a veto spec only).`
- **`_mode_problem(idea)`** returns these messages, in this order, and `None` otherwise:
  - `f"{idea.name}: mode {idea.mode!r} is not one of {MODES}"`
  - `f"{idea.name}: an avoid idea needs states(df)"` when `mode == "avoid"` and `states is None`
  - `f"{idea.name}: an edge idea takes no states"` when `mode == "edge"` and `states is not None`
  - `f"{idea.name}: an avoid idea races the fixed shape from the next open"` when `mode == "avoid"` and (`entry != "next_open"` or `race_shape != "fixed"`)
- **`Idea`** gets `mode: str = "edge"` and `states: Callable[[pd.DataFrame], pd.DataFrame] | None = None`, directly after `context_kind`. If v211 has placed other fields after `context_kind` by then, these two still go immediately after it; the field-order test pins that.
- **`__post_init__`** appends `or _mode_problem(self)` to the problem chain.
- **`_load`** gains `mode=getattr(module, "MODE", "edge")` and `states=getattr(module, "states", None)`.
- **Module docstring.** Append: *"v214: a module may also export MODE ("edge" default, or "avoid") and, for an avoid idea, states(df): one frame per ticker with bool columns event, control_condition and condition, and a float column bottom (spec v214 G3). An avoid idea races the fixed shape from the next open, and its verdict is the six-clause avoid rule (screen/verdict.py). A changed MODE is a new idea with a new name."*

The four `if` branches keep `_mode_problem` at complexity 6 or less.

- [ ] **Step 4: Run the tests to verify they pass, plus the v211 pins**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/complexity_gate.py
```

Then run the three v211 pins from this part's header. Expected: all `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v214): Idea.mode and Idea.states with the edge-mode witness pin (V214-4)"
```

# Phase 2 — The idea (wave B)

### Task V214-5: Idea `fvg_overhead_aged` (G3)

**Model:** opus — this is the frozen event definition, with per-gap onset, warm-up, wick fill and causality; a slip here spends the one shot on the wrong idea.

**Files:**
- Create: `swingbot/core/backtesting/screen/errors.py`
- Create: `swingbot/core/backtesting/screen/ideas/fvg_overhead_aged.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (append to `IDEA_MODULES` only)
- Create: `tests/backtesting/screen/test_idea_fvg_overhead_aged.py`
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (the exact pins, in the same commit as `IDEA_MODULES`)

**Interfaces:**
- Consumes:
  - V214-1's `fvg.scan_fair_value_gaps(df, lookback, max_per_side)`;
  - V214-4's `Idea.mode`/`Idea.states`, read from `MODE`/`states`;
  - `screen.indicators.atr(df, n)` (exists; NaN on bars 0..12 for n = 14).
- Produces (V214-6 reads these):
  - `errors.IdeaError(RuntimeError)`: an idea's own computation failed on one ticker. The runner aborts that ticker and counts it.
  - Module `fvg_overhead_aged` constants: `CAP = 20`, `MODE = "avoid"`, `RACE = "fixed"`, `DIRECTION = "long"`, `ENTRY = "next_open"`, `MIN_AGE_BARS = 5`, `REACH_ATR = 3.0`, `STATE_COLUMNS = ("event", "control_condition", "condition", "bottom")`, plus `PARAMS`, `SUMMARY` and `SOURCE`.
  - `states(df) -> pd.DataFrame`: index `df.index`, columns `STATE_COLUMNS` in that order. `event`, `control_condition` and `condition` are bool; `bottom` is float64, the lowest within-reach gap bottom on event bars and NaN elsewhere. A detector or input failure raises `IdeaError`.
  - `events(df) -> pd.Series`: `states(df)["event"]`, renamed `"fvg_overhead_aged"`.

- [ ] **Step 0: Gate and prerequisites.** Run the two `git grep` commands from this part's header. Then check that V214-1 and V214-4 have landed on the branch: `git grep -n "def scan_fair_value_gaps" -- swingbot/core/market/fvg.py` and `git grep -n "_mode_problem" -- swingbot/core/backtesting/screen/ideas/__init__.py` must both print a line.

- [ ] **Step 1: Write the failing idea tests**

Create `tests/backtesting/screen/test_idea_fvg_overhead_aged.py`. Frames A, C and D were checked against today's detector; their positions are exact.

```python
"""v214 G3: fvg_overhead_aged. The live FVG detector per bar on df.iloc[:t+1];
bearish gaps aged >= 5 bars; within reach = Close[t] < bottom <= Close[t] +
3 x ATR14[t]; one event per gap bar_index, at its first qualifying bar;
control = no gap within reach but an aged gap beyond it."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.errors import IdeaError
from swingbot.core.backtesting.screen.ideas import fvg_overhead_aged as idea
from swingbot.core.market import fvg
from tests.backtesting.screen.helpers import frame, random_walk
from tests.market.fvg_frames import BEAR_THIRD, FLAT, STRONG_BEAR, bar_frame

N_FLAT = 40          # helpers.frame([100]*40): TR 2, ATR14 exactly 2.0 from bar 13, reach 106.0


def _on(col, df):
    return np.flatnonzero(idea.states(df)[col].to_numpy()).tolist()


def _descending(count=20, start=95.5):
    """Overlapping bars falling 1.0 a bar: no new gap, gap 31 never filled."""
    return [(start - k, start - k + 1.5, start - k - 1.5, start - k) for k in range(count)]


def _frame_a(wick_at=None, wick_high=None):
    """Flat 30 bars, then a bearish gap 98.5..99.0 formed at bar 31, then a slide."""
    bars = [FLAT] * 30 + [STRONG_BEAR, BEAR_THIRD] + _descending()
    if wick_at is not None:
        close = bars[wick_at][3]
        bars[wick_at] = (close, wick_high, close - 1.5, close)
    return bar_frame(bars)


def _gap(bottom, bar_index, direction="bearish"):
    return {"bottom": float(bottom), "top": float(bottom) + 0.5,
            "mid": float(bottom) + 0.25, "bar_index": bar_index, "direction": direction}


def _script(monkeypatch, gaps_at):
    """The detector sees gaps_at(t) on df.iloc[:t+1]; returns the call log."""
    calls = []

    def fake(part, *args, **kwargs):
        calls.append((len(part), args, kwargs))
        return list(gaps_at(len(part) - 1))

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", fake)
    return calls


def test_the_frozen_definition():
    assert (idea.CAP, idea.MODE, idea.RACE, idea.DIRECTION, idea.ENTRY) == (
        20, "avoid", "fixed", "long", "next_open")
    assert (idea.MIN_AGE_BARS, idea.REACH_ATR) == (5, 3.0)
    assert idea.STATE_COLUMNS == ("event", "control_condition", "condition", "bottom")
    assert idea.PARAMS["lookback"] == fvg.LOOKBACK_BARS == 100
    assert idea.PARAMS["max_per_side"] == fvg.MAX_GAPS_PER_SIDE == 3
    assert idea.SOURCE.startswith("docs/superpowers/results/2026-11-06-loss-review-sep-nov.md")


def test_the_flat_fixture_reach_is_exactly_106():
    atr = indicators.atr(frame([100.0] * N_FLAT), 14)
    assert atr.iloc[:13].isna().all() and (atr.iloc[13:] == 2.0).all()


def test_the_states_frame_shape():
    df = random_walk(300, seed=7)
    out = idea.states(df)
    assert tuple(out.columns) == idea.STATE_COLUMNS and out.index.equals(df.index)
    assert [str(out[c].dtype) for c in idea.STATE_COLUMNS] == ["bool", "bool", "bool", "float64"]
    ev = idea.events(df)
    assert ev.name == "fvg_overhead_aged" and ev.dtype == bool
    pd.testing.assert_series_equal(ev, out["event"], check_names=False)


def test_a_real_gap_fires_once_when_five_bars_old_and_in_reach():
    df = _frame_a()                 # gap at bar 31; bar 35 is in reach but only 4 bars old
    assert _on("event", df) == [36] and _on("condition", df) == [36]
    assert _on("control_condition", df) == list(range(37, 52))   # slid out of reach
    bottom = idea.states(df)["bottom"]
    assert bottom.iloc[36] == 98.5 and bottom.drop(df.index[36]).isna().all()


def test_a_gap_parked_within_reach_fires_once_and_stays_a_condition():
    df = bar_frame([FLAT] * 30 + [STRONG_BEAR, BEAR_THIRD] + [(96.5, 97.0, 96.0, 96.5)] * 20)
    assert _on("event", df) == [36]
    assert _on("condition", df) == list(range(36, 52)) and _on("control_condition", df) == []


def test_a_wick_touching_the_bottom_exactly_fills_the_gap_as_live():
    touched = _frame_a(wick_at=34, wick_high=98.5)         # High == bottom: filled
    assert _on("event", touched) == _on("condition", touched) == []
    assert _on("control_condition", touched) == []
    assert _on("event", _frame_a(wick_at=34, wick_high=98.49)) == [36]


def test_age_four_is_too_young_and_age_five_qualifies(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(103.0, 10)] if t >= 10 else [])
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [15] and _on("condition", df) == list(range(15, N_FLAT))
    assert _on("control_condition", df) == []


@pytest.mark.parametrize("bottom, where", [
    (106.0, "condition"), (np.nextafter(106.0, np.inf), "control_condition"),
    (100.0, None), (100.01, "condition")])
def test_the_reach_bounds(monkeypatch, bottom, where):
    """Close < bottom (strict) and bottom <= Close + 3 ATR (inclusive)."""
    _script(monkeypatch, lambda t: [_gap(bottom, 2)])
    df = frame([100.0] * N_FLAT)
    for col in ("condition", "control_condition"):
        assert _on(col, df) == (list(range(13, N_FLAT)) if col == where else [])
    assert _on("event", df) == ([13] if where == "condition" else [])


def test_bullish_gaps_are_ignored(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(103.0, 2, "bullish"), _gap(110.0, 2, "bullish")])
    df = frame([100.0] * N_FLAT)
    assert not idea.states(df)[["event", "condition", "control_condition"]].to_numpy().any()


def test_several_gaps_on_one_bar_are_one_event_with_the_lowest_bottom(monkeypatch):
    _script(monkeypatch, lambda t: [_gap(104.5, 2), _gap(103.0, 3)] + (
        [_gap(105.0, 20)] if t >= 25 else []))
    out = idea.states(frame([100.0] * N_FLAT))
    assert np.flatnonzero(out["event"]).tolist() == [13, 25]
    assert out["bottom"].iloc[13] == 103.0 and out["bottom"].iloc[25] == 103.0


def test_an_evicted_gap_that_comes_back_never_fires_again(monkeypatch):
    """Top-3 eviction or a window exit drops a gap; a later fill of a newer gap
    can bring it back. It keeps its bar_index, so it never re-fires."""
    a, b = _gap(103.0, 2), _gap(104.0, 20)
    _script(monkeypatch, lambda t: ([a] if 13 <= t <= 20 or t >= 26 else []) + (
        [b] if t >= 30 else []))
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [13, 30]
    assert _on("condition", df) == list(range(13, 21)) + list(range(26, N_FLAT))


def test_control_needs_no_gap_in_reach_and_an_aged_gap_beyond(monkeypatch):
    near, far, young_far = _gap(103.0, 2), _gap(110.0, 2), _gap(110.0, 30)
    _script(monkeypatch, lambda t: [far] + ([near] if t <= 20 else []) + [young_far])
    df = frame([100.0] * N_FLAT)
    assert _on("condition", df) == list(range(13, 21))
    assert _on("control_condition", df) == list(range(21, N_FLAT))


def test_warm_up_bars_neither_call_the_detector_nor_mark_a_gap_fired(monkeypatch):
    calls = _script(monkeypatch, lambda t: [_gap(103.0, 2)] if t >= 2 else [])
    df = frame([100.0] * N_FLAT)
    assert _on("event", df) == [13]          # in reach and aged from t = 7; ATR from 13
    assert [n for n, _, _ in calls] == list(range(14, N_FLAT + 1))


def test_the_live_detector_is_called_per_bar_on_the_truncated_frame(monkeypatch):
    real, seen = fvg.scan_fair_value_gaps, []

    def spy(part, *args, **kwargs):
        seen.append((part.index, args, kwargs))
        return real(part, *args, **kwargs)

    monkeypatch.setattr(fvg, "scan_fair_value_gaps", spy)
    df = _frame_a()
    assert _on("event", df) == [36]
    assert [len(i) for i, _, _ in seen] == list(range(14, len(df) + 1))
    assert all(i.equals(df.index[: len(i)]) for i, _, _ in seen)
    assert all(args == (100, 3) and not kw for _, args, kw in seen)


def test_a_detector_failure_raises_an_idea_error_naming_the_bar(monkeypatch):
    def gaps_at(t):
        if t == 20:
            raise RuntimeError("bad frame")
        return []

    _script(monkeypatch, gaps_at)
    with pytest.raises(IdeaError, match=r"fvg_overhead_aged.*bar 20") as info:
        idea.states(frame([100.0] * N_FLAT))
    assert isinstance(info.value.__cause__, RuntimeError)
    assert issubclass(IdeaError, RuntimeError)


def test_a_frame_the_idea_cannot_read_raises_an_idea_error():
    with pytest.raises(IdeaError, match="fvg_overhead_aged"):
        idea.states(frame([100.0] * N_FLAT).drop(columns=["High"]))


@pytest.mark.parametrize("seed", [7, 21])
def test_no_bar_reads_a_later_bar(seed):
    """Appending bars after t never changes the event or the condition at t."""
    df = random_walk(700, seed=seed)
    full = idea.states(df)
    assert full["event"].sum() >= 3 and full["control_condition"].sum() >= 3
    for t in (100, 250, 400, 699):
        pd.testing.assert_frame_equal(idea.states(df.iloc[: t + 1]), full.iloc[: t + 1])


@pytest.mark.parametrize("seed", [7, 21])
def test_condition_and_control_exclude_each_other_and_events_are_conditions(seed):
    out = idea.states(random_walk(700, seed=seed))
    assert not (out["condition"] & out["control_condition"]).any()
    assert not (out["event"] & ~out["condition"]).any()
    assert out["bottom"].notna().equals(out["event"])
```

- [ ] **Step 2: Write the failing registry pins**

In `tests/backtesting/screen/test_ideas_registry.py`, add `fvg_overhead_aged` to the module import line beside `range_breakdown_close, range_breakdown_stop`, then:
- **`IDEA_MODULES`:** the pinned tuple ends `..., "shock_support_break_short", "shock_failed_bounce_short", "fvg_overhead_aged")`. If V211-8/9 have not merged, it ends after the last idea present.
- **Caps:** add `"fvg_overhead_aged": 20`.
- **Params:** append `assert dict(IDEAS["fvg_overhead_aged"].params) == {"side": "bearish", "anchor": "bottom", "min_age_bars": 5, "reach_atr": 3.0, "atr_n": 14, "lookback": 100, "max_per_side": 3, "fill": "any wick touch", "onset": "once per gap bar_index"}`.
- **Direction and entry:** add `"fvg_overhead_aged": "long"` and `"fvg_overhead_aged": "next_open"`. It stays in the `older` set, with `levels`/`control`/`family` = `(None, None, ())`.
- **Race shape:** in `test_every_registered_idea_is_raced_under_one_pinned_shape` add `"fvg_overhead_aged": "fixed"`. If the context-series test enumerates every idea, add `"fvg_overhead_aged": ()`.
- **V214-4's witness test:** `test_every_registered_idea_reads_edge_mode_with_no_states` becomes the following, plus one new test:

```python
def test_every_registered_idea_reads_edge_mode_with_no_states():
    """v214 witness: every idea frozen before v214 reads MODE = "edge" and no
    states(df), so its verdict, results doc and hypothesis stay byte-identical."""
    edge = {n: i for n, i in IDEAS.items() if n != "fvg_overhead_aged"}
    assert {n: (i.mode, i.states) for n, i in edge.items()} == {n: ("edge", None) for n in edge}


def test_the_overhead_gap_idea_is_the_only_avoid_idea():
    aged = IDEAS["fvg_overhead_aged"]
    assert {n for n, i in IDEAS.items() if i.mode == "avoid"} == {"fvg_overhead_aged"}
    assert aged.states is fvg_overhead_aged.states and aged.events is fvg_overhead_aged.events
    assert (aged.context, aged.context_kind, aged.levels, aged.control, aged.family) == (
        (), "z", None, None, ())
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_fvg_overhead_aged.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: FAIL, with `ModuleNotFoundError: No module named 'swingbot.core.backtesting.screen.errors'` and the registry pins mismatched.

- [ ] **Step 4: Implement**

`swingbot/core/backtesting/screen/errors.py`:

```python
"""Errors an idea module raises to the screen runner (v214 G4)."""


class IdeaError(RuntimeError):
    """An idea's own computation failed on one ticker's frame. The runner
    aborts that ticker, counts it per ticker and carries on; it never reads
    as "no event", which would shrink N silently."""
```

`swingbot/core/backtesting/screen/ideas/fvg_overhead_aged.py`:
- **Docstring.** The test file's docstring, plus *"Frozen 2026-11-06 (v214 G3). Avoid mode: must do worse than the matched null and the out-of-reach control (screen/verdict.py). Event uses Close[t] as the frozen proxy for the next-open entry. Never vectorised: the per-bar call is the implementation (a vectorised form needs the spec's parity test)."*
- **Constants.** `NAME = "fvg_overhead_aged"` (private use in messages), plus the Interfaces constants.
- **`PARAMS`.** Exactly the registry pin. `SUMMARY = ("first bar t at which an unfilled bearish FVG (live detector on bars <= t) aged >= 5 bars has Close[t] < bottom <= Close[t] + 3 x ATR14[t]; once per gap; avoid mode against the null and an out-of-reach control")`. `SOURCE = ("docs/superpowers/results/2026-11-06-loss-review-sep-nov.md: live longs whose TP1 sits at an older unfilled bearish FVG, N = 68, ExpR -0.199R since 2026-09-01 (motivation only)")`.
- **Helpers.** Each stays well under complexity 15:

```python
def _inputs(df: pd.DataFrame):
    try:
        return (indicators.atr(df, PARAMS["atr_n"]).to_numpy(dtype=float),
                df["Close"].to_numpy(dtype=float))
    except Exception as exc:
        raise IdeaError(f"{NAME}: cannot read the frame: {exc!r}") from exc


def _aged_bearish(df: pd.DataFrame, t: int) -> list:
    try:
        gaps = fvg.scan_fair_value_gaps(df.iloc[: t + 1], PARAMS["lookback"],
                                        PARAMS["max_per_side"])
    except Exception as exc:
        raise IdeaError(f"{NAME}: FVG detector failed at bar {t} "
                        f"({df.index[t]}): {exc!r}") from exc
    return [g for g in gaps
            if g["direction"] == "bearish" and t - g["bar_index"] >= MIN_AGE_BARS]
```

- **`states(df)`.** Allocate three bool arrays, a NaN float array `bottom`, and `fired: set[int]`. Loop `for t in np.flatnonzero(np.isfinite(atr))`, so that a warm-up bar never calls the detector or marks a gap fired. At each bar:
  - `reach = close[t] + REACH_ATR * atr[t]`;
  - `within = [g for g in aged if close[t] < g["bottom"] <= reach]`;
  - `beyond = [g for g in aged if g["bottom"] > reach]`;
  - `condition[t] = bool(within)`;
  - `control[t] = not within and bool(beyond)`;
  - if any `g["bar_index"]` in `within` is not in `fired`: `event[t] = True` and `bottom[t] = min(g["bottom"] for g in within)`;
  - then `fired.update(g["bar_index"] for g in within)`.

  Return the frame with columns in `STATE_COLUMNS` order on `df.index`. Call the detector as `fvg.scan_fair_value_gaps(...)` through the module, with two positional arguments: the spy test checks `args == (100, 3)`, and both tests monkeypatch the module attribute.
- **`events(df)`.** `return states(df)["event"].rename("fvg_overhead_aged")`.

`swingbot/core/backtesting/screen/ideas/__init__.py`: append `"fvg_overhead_aged"` last to `IDEA_MODULES`, after v211's two shock ideas. Nothing else in the file changes. `_load` already reads `MODE` and `states` (V214-4), and the screen importing `swingbot.core.market.fvg` is allowed (`test_import_guard.py` only forbids imports *into* the screen from outside `swingbot/core/backtesting`).

- [ ] **Step 5: Run the tests to verify they pass, plus the guards and the v211 pins**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_fvg_overhead_aged.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py
python scripts/dev/complexity_gate.py
```

Then run the three v211 pins from this part's header. Expected: all `0 failed`. If a runner test enumerates `IDEAS` and races each one (`git grep -n "IDEAS.values()\|for name in IDEAS" -- tests/backtest_scripts`), confirm it still passes. An avoid idea is only wired into the runner in V214-6, so such a test must either skip `mode == "avoid"` or already pass. Report any that needs a skip rather than editing runner code here.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/errors.py swingbot/core/backtesting/screen/ideas/fvg_overhead_aged.py swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_idea_fvg_overhead_aged.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v214): idea fvg_overhead_aged, frozen avoid-mode trigger (V214-5)"
```

