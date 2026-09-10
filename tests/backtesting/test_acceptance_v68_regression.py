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
