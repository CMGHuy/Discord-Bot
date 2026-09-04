# v72 — Validation acceptance v2, Part 2: fixture, funnel and verification

> Part of the v72 plan. Header block, global constraints, parallelisation map
> and the part table live in `_0-index`. **Read that first.** These tasks
> consume the whole acceptance module from Parts 1a and 1b.

# Phase B — the v68 regression fixture

### Task B1: Regenerate v68's population as a committed fixture

**Files:**
- Create: `scripts/backtest/make_v68_fixture.py`
- Create: `tests/backtesting/fixtures/v68_validation_arms.json` (generated, committed)
- Test: `tests/backtesting/test_v68_fixture_shape.py`

**Interfaces:**
- Consumes: `ArmTrade`, `arm_trade_from_plan` from A1; `replay_scenarios`, `simulate_exit`, `dead_cat_bounce` from the live modules; `BASE_GATES`, `VALIDATION`, `HORIZONS_TO_TEST`, `SAMPLE_EVERY`, `CACHE_DIR`, `load_frames` from `scripts/backtest/measure_dcb_veto.py`.
- Produces: `tests/backtesting/fixtures/v68_validation_arms.json` with `{"baseline": [...], "component": [...], "meta": {...}}`, and `load_v68_arms() -> tuple[list, list]` in the test module.

**Why a new script rather than editing `measure_dcb_veto.py`:** that script recorded a shot that was fired. Its rows carry no `strategy` and no geometry, so they cannot feed clause 3 or the stratum table — but editing it would mean the archived script no longer matches what ran. It stays as history; this reads its constants and builds a richer record.

**This is not a re-run of the pre-registration.** v68's verdict stands. No task in this plan may change `DEAD_CAT_BOUNCE_VETO`'s default.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_v68_fixture_shape.py
"""The v68 fixture is this plan's regression anchor.

data/v68_validation_dcb.json was gitignored and is gone from this machine,
as is the .log its results doc cites. That is why the population is
regenerated and COMMITTED here: an instrument tested against a fixture
that can evaporate is not tested.
"""
import json
from pathlib import Path

FIXTURE = (Path(__file__).parent / "fixtures" / "v68_validation_arms.json")


def test_fixture_exists():
    assert FIXTURE.exists(), (
        "run: python scripts/backtest/make_v68_fixture.py")


def test_fixture_has_both_arms_and_provenance():
    blob = json.loads(FIXTURE.read_text())
    assert set(blob) == {"baseline", "component", "meta"}
    meta = blob["meta"]
    assert meta["cell"] == "d15_gN_voff"
    assert meta["window"] == ["2024-01-01", "2025-12-31"]
    assert meta["horizons"] == ["4w", "2m", "3m", "4m", "6m"]
    assert "generated_by" in meta


def test_arms_carry_every_field_the_clauses_read():
    blob = json.loads(FIXTURE.read_text())
    row = blob["baseline"][0]
    assert set(row) >= {"ticker", "strategy", "horizon_key", "entry_date",
                        "outcome", "r_multiple", "planned_rr"}


def test_component_is_a_subset_of_baseline():
    """The dcb veto only removes bullish scenarios; it changes no surviving
    outcome. Anything else would mean the regeneration diverged from what
    v68 actually measured."""
    blob = json.loads(FIXTURE.read_text())
    key = lambda r: (r["ticker"], r["strategy"], r["horizon_key"],
                     r["entry_date"])
    b = {key(r) for r in blob["baseline"]}
    c = {key(r) for r in blob["component"]}
    assert c < b


def test_arm_sizes_are_close_to_the_published_run():
    """v68's published VALIDATION numbers: baseline N=859, component N=844
    decided trades. The regeneration uses the same tickers, horizons, gates
    and window, so it must land near them -- a wide tolerance, because this
    asserts 'the same measurement', not bit-identity."""
    blob = json.loads(FIXTURE.read_text())
    decided = lambda arm: sum(1 for r in arm if r["outcome"] in ("win", "loss"))
    assert 800 <= decided(blob["baseline"]) <= 920
    assert 790 <= decided(blob["component"]) <= 905
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_v68_fixture_shape.py -v`
Expected: FAIL — `test_fixture_exists` fails; the rest error on the missing file.

- [ ] **Step 3: Write the generator and run it**

```python
# scripts/backtest/make_v68_fixture.py
#!/usr/bin/env python3
"""Regenerate v68's VALIDATION population as a committed test fixture.

WHY THIS EXISTS: `data/v68_validation_dcb.json` was gitignored and is not
on this machine; neither is the `.log` the v68 results doc cites. The v72
acceptance gate uses that population as its regression anchor -- the new
gate must FAIL v68 -- so the population has to be reproducible and
committed rather than sitting in a gitignored path.

THIS IS NOT A RE-RUN OF THE PRE-REGISTRATION. v68's verdict is final and
unchanged: DEAD_CAT_BOUNCE_VETO's default stays false. Regenerating a
population to test an *instrument* makes no selection decision.

Reads its constants from measure_dcb_veto.py rather than restating them, so
the fixture cannot silently describe a different run than the one that
fired. Emits the richer ArmTrade shape (strategy + planned RR), which that
script's own row dialect does not carry.

Run: python scripts/backtest/make_v68_fixture.py   (~5-6 minutes)
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from measure_dcb_veto import (  # noqa: E402
    BASE_GATES, CACHE_DIR, HORIZONS_TO_TEST, SAMPLE_EVERY, VALIDATION,
    load_frames,
)

from swingbot.core.backtesting.acceptance import arm_trade_from_plan  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios  # noqa: E402
from swingbot.core.market.chart_patterns import dead_cat_bounce  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

#: The one cell v68's TRAIN selected and VALIDATION spent its shot on.
CELL = {"decline_pct": 15.0, "gap_required": False, "volume_ratio": None}
CELL_ID = "d15_gN_voff"
OUT = ROOT / "tests" / "backtesting" / "fixtures" / "v68_validation_arms.json"


def main() -> int:
    frames = load_frames(CACHE_DIR, ROOT / "data" / "watchlist.json",
                         None, SAMPLE_EVERY)
    print(f"{len(frames)} tickers | horizons {HORIZONS_TO_TEST} | "
          f"window {VALIDATION}", flush=True)
    baseline, component = [], []
    for n, (ticker, df) in enumerate(sorted(frames.items()), 1):
        kept = 0
        for hk in HORIZONS_TO_TEST:
            for i, plan in replay_scenarios(ticker, df, hk, gates=BASE_GATES,
                                            dcb_params=None):
                entry_date = str(df.index[i].date())
                if not (VALIDATION[0] <= entry_date <= VALIDATION[1]):
                    continue
                result = simulate_exit(df, i, plan, scale_out=True)
                trade = arm_trade_from_plan(plan, entry_date=entry_date,
                                            outcome=result.outcome,
                                            r_multiple=result.r_total)
                baseline.append(trade)
                vetoed = (plan.direction == "bullish" and
                          dead_cat_bounce(df.iloc[:i + 1], CELL)["detected"])
                if not vetoed:
                    component.append(trade)
                    kept += 1
        print(f"[{n}/{len(frames)}] {ticker}: kept {kept}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "baseline": [asdict(t) for t in baseline],
        "component": [asdict(t) for t in component],
        "meta": {"cell": CELL_ID, "cell_params": CELL,
                 "window": list(VALIDATION), "horizons": HORIZONS_TO_TEST,
                 "sample_every": SAMPLE_EVERY, "gates": BASE_GATES,
                 "generated_by": "scripts/backtest/make_v68_fixture.py",
                 "note": "regenerated to test an instrument; v68's verdict "
                         "is unchanged and its budget stays spent"},
    }, indent=1))
    print(f"\nwrote {OUT} | baseline={len(baseline)} "
          f"component={len(component)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it (progress prints per ticker, ~5-6 min):

```bash
python scripts/backtest/make_v68_fixture.py
```

If the printed decided-trade counts fall outside the tolerances in
`test_arm_sizes_are_close_to_the_published_run`, **stop and investigate** —
the regeneration has diverged from what v68 measured, and a fixture that
does not reproduce the published run is not an anchor. Do not widen the
tolerance to make it pass.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_v68_fixture_shape.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/make_v68_fixture.py \
        tests/backtesting/fixtures/v68_validation_arms.json \
        tests/backtesting/test_v68_fixture_shape.py
git commit -m "test(v72): regenerate v68's VALIDATION population as a committed fixture"
```

---

### Task B2: The v68 regression — the new gate must fail it

**Files:**
- Create: `tests/backtesting/test_acceptance_v68_regression.py`

**Interfaces:**
- Consumes: `ArmTrade`, `evaluate`, `mde_win_rate`, `project_target_n`, `win_rate` from Phase A; the fixture from B1.
- Produces: nothing — this is the acceptance criterion, not a component.

Spec acceptance criteria 1 and 3. **A v2 gate that passed v68 would be evidence against this design.**

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_acceptance_v68_regression.py
"""v68 is the regression anchor for the whole v72 gate.

Published VALIDATION numbers (docs/superpowers/results/
2026-08-30-v68-dcb-veto-validation.md): baseline N=859 WR=34.9%
ExpR=+0.0058; component N=844 WR=34.5% ExpR=-0.0039. The delta was
-0.0097R -- the opposite sign from TRAIN's +0.0104R.

The v2 gate must FAIL this, and fail it on the clauses that describe the
feature (win_rate, mechanism) rather than on the absolute floors v2 no
longer applies.
"""
import json
from pathlib import Path

import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, evaluate, expectancy_r, mde_win_rate, project_target_n,
    win_rate,
)

FIXTURE = Path(__file__).parent / "fixtures" / "v68_validation_arms.json"


def load_arms():
    if not FIXTURE.exists():
        pytest.skip("run scripts/backtest/make_v68_fixture.py first")
    blob = json.loads(FIXTURE.read_text())
    to_arm = lambda rows: [ArmTrade(**r) for r in rows]
    return to_arm(blob["baseline"]), to_arm(blob["component"])


def test_fixture_reproduces_the_published_arm_level_numbers():
    baseline, component = load_arms()
    assert win_rate(baseline) == pytest.approx(34.9, abs=1.5)
    assert win_rate(component) == pytest.approx(34.5, abs=1.5)
    assert expectancy_r(component) < expectancy_r(baseline)


def test_the_v2_gate_fails_v68():
    """The headline assertion of this plan."""
    baseline, component = load_arms()
    res = evaluate(baseline, component, stage="validation",
                   permutation_p=None, n_resamples=500, seed=42)
    assert res.verdict == "FAIL"


def test_it_fails_on_the_win_rate_clause_not_an_absolute_floor():
    """v68's arm failed the OLD `win_rate >= 50` while its baseline sat at
    34.9% -- an absolute floor that measured the population, not the
    feature. v2 must fail it for the right reason: the win rate did not
    improve."""
    baseline, component = load_arms()
    res = evaluate(baseline, component, stage="validation",
                   permutation_p=0.01, n_resamples=500, seed=42)
    assert res.clause("win_rate").verdict == "FAIL"
    assert res.clause("win_rate").value < 0.0     # dWR is negative


def test_the_mechanism_clause_shows_the_removed_trades_were_not_worse():
    """Clause 6 is the explanation: if the veto were working, the trades it
    removed would be worse than the ones it kept."""
    baseline, component = load_arms()
    res = evaluate(baseline, component, stage="validation",
                   permutation_p=0.01, n_resamples=500, seed=42)
    assert res.clause("mechanism").verdict == "FAIL"


def test_the_volume_clause_passes_because_the_cut_was_tiny():
    """A 1.7% alert cut is nowhere near the 25% ceiling. Recording this
    keeps the failure honest -- v68 did not fail for trading too little."""
    baseline, component = load_arms()
    res = evaluate(baseline, component, stage="validation",
                   permutation_p=0.01, n_resamples=500, seed=42)
    assert res.clause("volume").verdict == "PASS"


def test_stage_0_would_have_refused_the_shot():
    """Spec acceptance criterion 3. v68's TRAIN effect was +0.0104R, with a
    win-rate effect far below what its sample could resolve. The MDE at the
    achievable N must exceed the effect that was chased."""
    baseline, _ = load_arms()
    # VALIDATION is 2 years; project from it to itself is the honest
    # self-check that the achievable N is what it was.
    target_n = project_target_n(
        observed_n=sum(1 for t in baseline if t.outcome in ("win", "loss")),
        observed_days=730, target_days=730)
    mde = mde_win_rate(baseline, target_n=target_n)
    assert mde is not None
    # v68's selected cell moved win rate by -0.45pp; anything under the MDE
    # was never resolvable either way.
    assert mde > 0.45
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_acceptance_v68_regression.py -v`
Expected: FAIL before Phase A is merged. After A1–A5 and B1, it should pass — run it and confirm.

- [ ] **Step 3: No implementation**

This task writes no production code. If any assertion fails, the defect is
in Phase A and is fixed there — **do not weaken an assertion to make it
green.** A gate that passes v68 is the one outcome this plan exists to
prevent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_acceptance_v68_regression.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add tests/backtesting/test_acceptance_v68_regression.py
git commit -m "test(v72): the v2 gate must fail v68 -- and for the right reasons"
```

---

# Phase C — funnel wiring

### Task C1: Correct the `ANCHORED_FOLDS` start date

**Files:**
- Modify: `swingbot/core/backtesting/backtest_wf.py:17-21`
- Test: `tests/backtesting/test_wf_engine.py` (add one test)

**Interfaces:**
- Consumes: nothing.
- Produces: `ANCHORED_FOLDS` with `2018-06-01` fold-train starts.

The cache starts `2018-06-01` (`scripts/data/fetch_backtest_data.py:42`), so the `2018-01-01` edge is fiction — the first fold trains on ~2.5 years, not 3. A documentation fix, not a behaviour change: the data was never there.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/backtesting/test_wf_engine.py
def test_anchored_folds_start_where_the_cache_actually_starts():
    """scripts/data/fetch_backtest_data.py:42 sets START = 2018-06-01.
    A fold nominally starting 2018-01-01 claims five months of data that
    have never existed, which silently overstates the first fold's train
    length."""
    from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS
    assert all(fold[0] == "2018-06-01" for fold in ANCHORED_FOLDS)


def test_anchored_folds_test_windows_are_unchanged():
    """The correction touches train starts ONLY. The test years are
    pre-registered and frozen."""
    from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS
    assert [(f[2], f[3]) for f in ANCHORED_FOLDS] == [
        ("2021-01-01", "2021-12-31"),
        ("2022-01-01", "2022-12-31"),
        ("2023-01-01", "2023-12-31"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_wf_engine.py`
Expected: FAIL — `test_anchored_folds_start_where_the_cache_actually_starts`

- [ ] **Step 3: Write minimal implementation**

Replace `swingbot/core/backtesting/backtest_wf.py:17-21`:

```python
#: Fold train windows start 2018-06-01 because that is where the OHLCV
#: cache starts (scripts/data/fetch_backtest_data.py: START = "2018-06-01").
#: They read 2018-01-01 until v72; that edge was always fiction -- the data
#: was never there -- so this corrects a description, not a behaviour. The
#: TEST windows are pre-registered and frozen, and are untouched.
ANCHORED_FOLDS = (
    ("2018-06-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-06-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-06-01", "2022-12-31", "2023-01-01", "2023-12-31"),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_wf_engine.py`
Expected: PASS, `0 failed`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/backtest_wf.py tests/backtesting/test_wf_engine.py
git commit -m "fix(v72): anchored folds start 2018-06-01, where the cache actually starts"
```

---

### Task C2: Re-metric the fold gate to ΔWR

**Files:**
- Modify: `swingbot/core/backtesting/backtest_wf.py:23-26, 181-194`
- Test: `tests/backtesting/test_wf_gate_winrate.py`

**Interfaces:**
- Consumes: `delta_standardised_win_rate` from A3.
- Produces: `GATE_MIN_IMPROVING_FOLDS = 2`, `GATE_MAX_WR_DEGRADATION_PP = 1.0`, `GATE_MIN_N_PER_FOLD = 30`, `gate_win_rate(result) -> str`.

Stage 2 of the funnel. `gate()` keeps its expectancy metric and its existing callers; `gate_win_rate()` is added beside it so the v72 funnel reads win rate without changing what any existing caller gets.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_wf_gate_winrate.py
"""Stage 2: the free, repeatable gate in front of the one-shot budget.

This is where v68 would have died at zero cost -- its effect did not hold
across fold-test years, and the funnel never had to spend a shot to learn
that.
"""
from swingbot.core.backtesting.backtest_wf import (
    GATE_MAX_WR_DEGRADATION_PP, GATE_MIN_IMPROVING_FOLDS, gate_win_rate,
)


def result(deltas, ns=None):
    ns = ns or [100] * len(deltas)
    return {"folds": [{"test_years": str(2021 + i), "delta_win_rate_pp": d,
                       "n": n}
                      for i, (d, n) in enumerate(zip(deltas, ns))]}


def test_all_three_folds_improving_passes():
    assert gate_win_rate(result([1.5, 2.0, 0.8])) == "PASS"


def test_two_of_three_improving_passes():
    assert gate_win_rate(result([1.5, -0.4, 0.8])) == "PASS"


def test_one_of_three_improving_fails():
    assert gate_win_rate(result([1.5, -0.4, -0.2])) == "FAIL"


def test_a_single_bad_fold_fails_even_with_two_improving():
    """Consistency, not an average: a fold that degrades past the ceiling
    fails the component however well the others did."""
    bad = -(GATE_MAX_WR_DEGRADATION_PP + 0.5)
    assert gate_win_rate(result([3.0, 4.0, bad])) == "FAIL"


def test_a_thin_fold_fails():
    assert gate_win_rate(result([1.5, 2.0, 0.8], ns=[100, 100, 29])) == "FAIL"


def test_a_missing_delta_fails():
    assert gate_win_rate(result([1.5, None, 0.8])) == "FAIL"


def test_the_improving_fold_minimum_is_two_of_three():
    assert GATE_MIN_IMPROVING_FOLDS == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_wf_gate_winrate.py -v`
Expected: FAIL — `ImportError: cannot import name 'gate_win_rate'`

- [ ] **Step 3: Write minimal implementation**

Add to `swingbot/core/backtesting/backtest_wf.py`, beside the existing constants and `gate()`:

```python
#: v72 Stage 2. Win-rate flavour of the fold gate -- same shape as gate()'s
#: expectancy rule, same pre-registered spirit: consistency across folds,
#: not a flattering average. A fold that degrades past the ceiling fails the
#: component however well its siblings did.
GATE_MAX_WR_DEGRADATION_PP = 1.0


def gate_win_rate(result: dict) -> str:
    """The PRE-REGISTERED Stage 2 pass rule, on mix-standardised ΔWR.

    Free and repeatable, unlike the VALIDATION shot behind it -- which is
    the point: a component that cannot hold its sign across three
    independent test years never reaches the one-shot budget.
    """
    folds = result["folds"]
    deltas = [f.get("delta_win_rate_pp") for f in folds]
    if any(d is None for d in deltas):
        return "FAIL"
    if any(f["n"] < GATE_MIN_N_PER_FOLD for f in folds):
        return "FAIL"
    if sum(d > 0 for d in deltas) < GATE_MIN_IMPROVING_FOLDS:
        return "FAIL"
    if any(d < -GATE_MAX_WR_DEGRADATION_PP for d in deltas):
        return "FAIL"
    return "PASS"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_wf_gate_winrate.py -v`
Expected: PASS, 7 passed

Then confirm the existing expectancy gate still behaves:

Run: `python scripts/dev/testrun.py file tests/backtesting/test_wf_engine.py`
Expected: `0 failed`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/backtest_wf.py tests/backtesting/test_wf_gate_winrate.py
git commit -m "feat(v72): win-rate fold gate for funnel stage 2"
```

---

### Task C3: The `validate_component.py` funnel CLI

**Files:**
- Create: `scripts/backtest/validate_component.py`
- Test: `tests/backtesting/test_validate_component_cli.py`

**Interfaces:**
- Consumes: `ArmTrade`, `evaluate`, `render_markdown`, `render_json`, `mde_win_rate`, `project_target_n` from Phase A; `gate_win_rate` from C2.
- Produces: `load_arms(path) -> tuple[list, list]`, `stage_mde(args) -> int`, `stage_walkforward(args) -> int`, `stage_validation(args) -> int`, `main() -> int`.

The CLI reads arms from a JSON file the component's own measurement script wrote, so it stays independent of any one component's replay. **It writes the results-doc skeleton with the clause set quoted into it before the run**, so the pre-registration is on disk before the number is known.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_validate_component_cli.py
"""The CLI is thin on purpose: every decision lives in acceptance.py, so a
measurement script cannot quietly pick its own bar.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CLI = ROOT / "scripts" / "backtest" / "validate_component.py"


def write_arms(tmp_path, n_tickers=25, drop_from=8):
    rows = {"baseline": [], "component": []}
    for t in range(n_tickers):
        for i in range(10):
            row = {"ticker": f"T{t}", "strategy": "MACD", "horizon_key": "3m",
                   "entry_date": f"2021-03-{i + 1:02d}",
                   "outcome": "win" if i < 4 else "loss",
                   "r_multiple": 2.0 if i < 4 else -1.0, "planned_rr": 2.0}
            rows["baseline"].append(row)
            if i < drop_from:
                rows["component"].append(row)
    p = tmp_path / "arms.json"
    p.write_text(json.dumps(rows))
    return p


def run(*args):
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True)


def test_validation_stage_emits_a_verdict_and_a_results_doc(tmp_path):
    arms = write_arms(tmp_path)
    out_md = tmp_path / "result.md"
    out_json = tmp_path / "result.json"
    r = run("--stage", "validation", "--arms", str(arms),
            "--title", "v99 demo", "--window", "2024-01-01..2025-12-31",
            "--permutation-p", "0.01", "--resamples", "200",
            "--out-md", str(out_md), "--out-json", str(out_json))
    assert r.returncode in (0, 1), r.stderr
    assert out_md.exists() and out_json.exists()
    blob = json.loads(out_json.read_text())
    assert blob["verdict"] in ("PASS", "FAIL")
    assert blob["acceptance_version"] == 2
    assert "win_rate" in out_md.read_text()


def test_exit_code_is_one_on_a_failing_component(tmp_path):
    """A FAIL is a legitimate outcome, but the shell must be able to see it
    -- a gate that always exits 0 cannot gate anything in CI."""
    arms = write_arms(tmp_path, drop_from=2)     # a 80% alert cut
    r = run("--stage", "validation", "--arms", str(arms), "--title", "t",
            "--window", "w", "--permutation-p", "0.01", "--resamples", "200",
            "--out-md", str(tmp_path / "m.md"),
            "--out-json", str(tmp_path / "j.json"))
    assert r.returncode == 1
    assert "FAIL" in r.stdout


def test_mde_stage_prints_a_refusal_when_the_effect_is_too_small(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "mde", "--arms", str(arms), "--title", "t",
            "--window", "w", "--train-effect-pp", "0.01",
            "--target-days", "730", "--observed-days", "365")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout


def test_mde_stage_allows_a_resolvable_effect(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "mde", "--arms", str(arms), "--title", "t",
            "--window", "w", "--train-effect-pp", "40.0",
            "--target-days", "730", "--observed-days", "365")
    assert r.returncode == 0
    assert "RESOLVABLE" in r.stdout


def test_unknown_stage_is_rejected(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "nonsense", "--arms", str(arms), "--title", "t",
            "--window", "w")
    assert r.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_validate_component_cli.py -v`
Expected: FAIL — the CLI file does not exist, so every subprocess returns a non-zero code with `can't open file`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/backtest/validate_component.py
#!/usr/bin/env python3
"""The v72 acceptance funnel -- the single CLI that decides whether a
component ships.

Read docs/claude/backtest-methodology.md first. The clause set lives in
swingbot/core/backtesting/acceptance.py and is PRE-REGISTERED: a component
that fails is dropped and documented, never re-measured against a bar moved
to fit it.

Stages:
  mde          Is the hypothesis answerable at the N we can get? A TRAIN
               effect below the MDE means the shot is REFUSED and the
               budget stays unspent -- an unanswerable question wastes a
               shot whatever the answer looks like.
  walkforward  Score on fold-test years 2021/2022/2023. Free and
               repeatable. Clauses 1-4 and 6; no permutation required.
  validation   2024-01-01..2025-12-31. ONE shot, ever. All six clauses; a
               missing permutation p is a FAIL, not a skip.

Arms come from a JSON file the component's own measurement script wrote:
  {"baseline": [ArmTrade...], "component": [ArmTrade...]}

Exit code 0 = PASS / RESOLVABLE, 1 = FAIL / REFUSED.

Run:
  python scripts/backtest/validate_component.py --stage mde \\
      --arms data/mycomponent_train.json --title "v73 my component" \\
      --window "fold-train" --train-effect-pp 1.2 \\
      --observed-days 365 --target-days 730
  python scripts/backtest/validate_component.py --stage validation \\
      --arms data/mycomponent_validation.json --title "v73 my component" \\
      --window "2024-01-01..2025-12-31" --permutation-p 0.013 \\
      --out-md docs/superpowers/results/2026-XX-XX-v73-validation.md
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.acceptance import (  # noqa: E402
    BOOTSTRAP_RESAMPLES, ArmTrade, evaluate, mde_win_rate, project_target_n,
    render_json, render_markdown, win_rate,
)

DECIDED = ("win", "loss")


def load_arms(path: Path) -> tuple:
    blob = json.loads(Path(path).read_text())
    to_arm = lambda rows: [ArmTrade(**r) for r in rows]
    return to_arm(blob["baseline"]), to_arm(blob["component"])


def stage_mde(args) -> int:
    baseline, _ = load_arms(args.arms)
    observed = sum(1 for t in baseline if t.outcome in DECIDED)
    target_n = project_target_n(observed_n=observed,
                                observed_days=args.observed_days,
                                target_days=args.target_days)
    mde = mde_win_rate(baseline, target_n=target_n)
    print(f"observed decided N : {observed} over {args.observed_days}d")
    print(f"projected target N : {target_n} over {args.target_days}d")
    print(f"baseline win rate  : {win_rate(baseline):.2f}%")
    if mde is None:
        print("\nREFUSED -- no decided trades to estimate an MDE from.")
        return 1
    print(f"MDE (dWR, 80% power, one-sided 0.05): {mde:.3f}pp")
    print(f"TRAIN effect claimed               : {args.train_effect_pp:.3f}pp")
    if args.train_effect_pp < mde:
        print("\nREFUSED -- the TRAIN effect is below the minimum this "
              "sample can detect. The VALIDATION budget is NOT spent; "
              "record this as 'unresolvable, budget intact'.")
        return 1
    print("\nRESOLVABLE -- the shot may proceed.")
    return 0


def _run_gate(args, stage: str) -> int:
    baseline, component = load_arms(args.arms)
    result = evaluate(baseline, component, stage=stage,
                      permutation_p=args.permutation_p,
                      n_resamples=args.resamples, seed=args.seed)
    md = render_markdown(result, title=args.title, window=args.window,
                         notes=args.notes)
    print(md)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md)
        print(f"[wrote {args.out_md}]")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(render_json(result), indent=1))
        print(f"[wrote {args.out_json}]")
    return 0 if result.verdict == "PASS" else 1


def stage_walkforward(args) -> int:
    return _run_gate(args, "walkforward")


def stage_validation(args) -> int:
    return _run_gate(args, "validation")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True,
                    choices=("mde", "walkforward", "validation"))
    ap.add_argument("--arms", required=True, type=Path,
                    help='JSON: {"baseline": [...], "component": [...]}')
    ap.add_argument("--title", required=True, help="component name for the doc")
    ap.add_argument("--window", required=True, help="the window, for the record")
    ap.add_argument("--permutation-p", type=float, default=None,
                    help="p from permutation_test.py -- REQUIRED at --stage "
                         "validation")
    ap.add_argument("--train-effect-pp", type=float, default=0.0,
                    help="--stage mde: the dWR the TRAIN grid claimed")
    ap.add_argument("--observed-days", type=int, default=365)
    ap.add_argument("--target-days", type=int, default=730)
    ap.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--notes", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()
    return {"mde": stage_mde, "walkforward": stage_walkforward,
            "validation": stage_validation}[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_validate_component_cli.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_cli.py
git commit -m "feat(v72): validate_component.py -- one funnel CLI, one bar"
```

---

# Phase D — documentation and verification

### Task D1: Rewrite the methodology doc and mirror to Codex

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (the "Acceptance gates" bullet and a new "The acceptance funnel" section)
- Modify: `CLAUDE.md` (the reference-doc table row for `backtest-methodology.md`)
- Modify: `.codex/AGENTS.md` (condensed mirror — Claude updates it, never the reverse)

**Interfaces:**
- Consumes: the finished CLI's stage names from C3.
- Produces: no code.

- [ ] **Step 1: Replace the acceptance-gates bullet**

In `docs/claude/backtest-methodology.md`, replace the `**Acceptance gates:**` bullet with:

```markdown
- **Acceptance gates (v72, `swingbot/core/backtesting/acceptance.py`).** A
  feature ships on-by-default only if every applicable clause passes.
  **Win rate is the objective; expectancy is a non-inferiority constraint.**

  | # | Clause | Instrument | Threshold |
  |---|---|---|---|
  | 1 | win rate improves | mix-standardised ΔWR, ticker-cluster bootstrap | ΔWR > 0, one-sided p < 0.05 |
  | 2 | profit preserved | ΔExpR, same bootstrap | lower 95% bound > −0.01R |
  | 3 | geometry lock | median planned RR and mean win R | neither falls > 2% |
  | 4 | volume floor | accepted-alert count | cut ≤ 25% |
  | 5 | not luck | `permutation_test.py`, n = 200 | p < 0.05 on ΔWR |
  | 6 | mechanism (subset features) | removed vs retained population | removed WR < retained WR **and** removed ExpR ≤ 0 |

  **Clause 3 is load-bearing.** Break-even win rate at reward:risk `X` is
  `1/(1+X)`, so win rate and expectancy trade one-for-one along the geometry
  axis and move together only along the discrimination axis. Without clause 3,
  "win rate up, expectancy flat" is passed trivially by pulling targets nearer.

  **The absolute `win_rate >= 50` floor no longer applies to feature
  acceptance.** It measured the population, not the feature: v68's component
  arm failed it at 34.5% while its own baseline sat at 34.9%. The floor
  survives only as a strategy-badge threshold. `expectancy_r > 0` as an
  absolute clause is likewise gone — a feature is judged against the baseline
  it replaces, never against zero. `N >= 15` is superseded by the Stage 0 MDE
  precheck below.

- **The acceptance funnel.** Selection never touches scoring data, and two
  free gates stand in front of the one-shot budget. Run it with
  `python scripts/backtest/validate_component.py --stage <stage>`.

  | Stage | Window | Cost | Rule |
  |---|---|---|---|
  | 0 `mde` | fold-train | free | TRAIN effect below the minimum detectable effect ⇒ **shot refused, budget intact** |
  | 1 selection | fold-train only (2018-06..2020 / ..2021 / ..2022) | free | `plateau_report()` mandatory and disqualifying — a spike, not a plateau, does not proceed |
  | 2 `walkforward` | fold-test 2021 / 2022 / 2023 | free, repeatable | `gate_win_rate`: ≥ 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30 |
  | 3 `validation` | 2024-01-01..2025-12-31 | **ONE shot, ever** | all six clauses; a missing permutation p is a FAIL, not a skip |

  Stage 2 being free and repeatable is the point: it is where v68 would have
  died at no cost to its budget. Sample width for stages 2–3 is the full
  cached universe × all 10 horizons, dispatched to `backtest-runner`.

- **`Edge: harvest` features are OUT OF SCOPE for this funnel, and that is a
  known gap, not an oversight.** Exits, targets and sizing move geometry by
  construction, so clause 3 rejects them by design. The honest rule for
  harvest work is expectancy-primary with a win-rate floor — close to the
  pre-v72 gate — and it needs its own reasoning about what floor and why.
  Until that spec exists, a harvest feature must **say in its own
  pre-registration** that it is not using this funnel and name the gate it
  is using instead. `Edge: expectancy` and `Edge: volume` are fully covered.
```

- [ ] **Step 2: Add the v72 row to the closed-pre-registrations preamble**

Immediately above the `### Closed pre-registrations` table, add:

```markdown
**The v72 procedure change does not reopen anything below.** A better
instrument is not a new hypothesis. Every row in this table stays closed,
and the features shipped on-by-default under the old gates
(`RS_GATE`, `AVWAP_LEVELS_ENABLED`, level-lifecycle stops) keep their
current defaults without a re-run.
```

- [ ] **Step 3: Update the `CLAUDE.md` reference row**

Replace the `backtest-methodology.md` row in the reference-docs table with:

```markdown
| `backtest-methodology.md` | running or interpreting any backtest/grid/validation — the v72 six-clause acceptance gate and its four-stage funnel, TRAIN/VALIDATION windows, frozen constants, and the table of **closed pre-registrations that must not be re-run** |
```

- [ ] **Step 4: Mirror into `.codex/AGENTS.md`**

Find the section mirroring the acceptance gates and replace its gate list with a condensed form — the six clause names with their thresholds, the four stage names, and the two sentences that matter most: win rate is the objective and expectancy the constraint; the absolute `win_rate >= 50` floor no longer gates feature acceptance. Keep it condensed, not copied verbatim; `CLAUDE.md`/`docs/claude/` stay canonical.

- [ ] **Step 5: Verify the docs are consistent and commit**

```bash
grep -n "win_rate >= 50" docs/claude/backtest-methodology.md .codex/AGENTS.md CLAUDE.md
```

Every surviving hit must be describing the *old* gate or the strategy-badge
threshold — not stating a live feature-acceptance rule. Fix any that is.

```bash
git add docs/claude/backtest-methodology.md CLAUDE.md .codex/AGENTS.md
git commit -m "docs(v72): the acceptance funnel and its six clauses"
```

---

### Task D2: First timed funnel run

**Files:**
- Create: `docs/superpowers/results/2026-09-04-v72-funnel-smoke.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a measured runtime, replacing the spec's *estimate*.

The spec estimates 2–5 h for a full funnel by extrapolating v68's 5.4-minute run at 25 tickers × 5 horizons to 89 × 10. That number is an extrapolation and the spec says to measure it. This task measures it.

**No component is being decided here.** This is a smoke run against the committed v68 fixture and a single fold-test year, to time the machinery and prove the stages wire together end to end.

- [ ] **Step 1: Time the gate on the committed fixture**

```bash
python -c "
import json, time
from pathlib import Path
from swingbot.core.backtesting.acceptance import ArmTrade, evaluate
blob = json.loads(Path('tests/backtesting/fixtures/v68_validation_arms.json').read_text())
arms = lambda k: [ArmTrade(**r) for r in blob[k]]
b, c = arms('baseline'), arms('component')
t0 = time.time()
res = evaluate(b, c, stage='validation', permutation_p=0.5, n_resamples=10000, seed=42)
print(f'{len(b)} vs {len(c)} trades | 10k resamples | {time.time()-t0:.1f}s | {res.verdict}')
"
```

Record the seconds. If it exceeds ~600s, note it in the results doc — the
bootstrap is the one part of this design whose cost scales with both
resamples and population size, and a real Stage 3 population is several
times this fixture.

- [ ] **Step 2: Time one fold-test year of replay at full width**

Dispatch the `backtest-runner` subagent (this is a long run; per `CLAUDE.md`
anything over ~2 minutes goes to that subagent so its per-symbol progress
never reaches the main context):

> Run `python scripts/backtest/make_v68_fixture.py` with `SAMPLE_EVERY = 1`
> and `HORIZONS_TO_TEST` set to all 10 horizon keys from
> `swingbot.core.market.strategy_types.HORIZONS`, over the window
> 2021-01-01..2021-12-31 instead of VALIDATION. Do not commit the output.
> Report only: wall-clock seconds, ticker count, total baseline trades.

- [ ] **Step 3: Write the results doc**

```markdown
# v72 acceptance funnel — timing smoke run

Not a component decision. This times the machinery and proves the stages
wire together; no pre-registration is opened, spent or affected.

## Gate cost (bootstrap)

| Population | Resamples | Wall clock |
|---|---|---|
| v68 fixture (<baseline> vs <component> trades) | 10,000 | <N>s |

## Replay cost (one fold-test year, full width)

| Tickers | Horizons | Window | Trades | Wall clock |
|---|---|---|---|---|
| <N> | 10 | 2021 | <N> | <N>s |

## Projected full funnel

Stage 2 is three fold-test years, two arms each. Stage 3 is one two-year
window, two arms. Projected total: **<N> h**, against the spec's 2-5 h
estimate. <One sentence: does the estimate hold, and if not, which stage
dominates.>
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-09-04-v72-funnel-smoke.md
git commit -m "measure(v72): funnel timing -- the spec's 2-5h estimate, measured"
```

---

### Task D3: Full-suite verification

**Files:** none — this task runs the plan's one full verification.

- [ ] **Step 1: Run the full suite once**

Dispatch the `test-runner` subagent, or run:

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. A *changed* pass count is not a failure —
this plan adds roughly 55 tests.

- [ ] **Step 2: Fix forward from any failure**

If it is not green, those are this plan's regressions. Fix from the failures
the run names; do not re-litigate earlier tasks. The most likely candidates,
and what each would mean:

- `tests/backtesting/test_wf_engine.py` — Task C1 changed a constant other
  fold tests assert against. Check whether the failing test asserts a *train*
  start (correct to update) or a *test* window (leave alone — those are
  frozen and a failure there means C1 went too far).
- Any test importing `backtest_wf.gate` — C2 added a function beside it and
  must not have altered it.

- [ ] **Step 3: Syntax pass**

```bash
python -m py_compile bot.py admin_ui.py swingbot/core/backtesting/acceptance.py scripts/backtest/validate_component.py scripts/backtest/make_v68_fixture.py
```

Expected: no output.

- [ ] **Step 4: Confirm nothing changed a default**

```bash
git diff main --stat -- swingbot/config.py
```

Expected: **empty.** This plan ships tooling. If `config.py` moved, a task
overstepped — `DEAD_CAT_BOUNCE_VETO` and every other flag keep the default
they had.

- [ ] **Step 5: Commit and close out**

```bash
git add -A
git commit -m "chore(v72): full-suite verification"
```

Then close the plan out per `docs/claude/document-lifecycle.md`: move both
the spec and this plan to `implemented/`, and bump `VERSION.json`'s `bot`
line to 1.6.2 per `docs/claude/working-conventions.md` — **and regenerate
`version_history.json` in the same commit**, since the local gate runs
before the bump and structurally cannot catch a missed regeneration.
