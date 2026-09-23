from unittest.mock import patch

from swingbot.core.backtesting.acceptance import ArmTrade, BootstrapResult
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


def test_expectancy_gain_fails_when_p_clears_alpha_but_lower_bound_does_not():
    """The pre-registration (spec S3, methodology doc) requires BOTH lower
    95% bound > 0 AND one-sided p < 0.05. The old code only checked
    `point > 0 and p < ALPHA`, which silently accepted a bootstrap draw
    whose lower tail still crosses zero as long as p snuck under 0.05 --
    this is exactly that draw, constructed directly (bootstrap_delta
    mocked) so the boundary case doesn't depend on getting cluster_bootstrap
    to land on it by chance."""
    baseline = _arm([0.3] * 40 + [-1.0] * 40, ["win"] * 40 + ["loss"] * 40)
    component = _arm([0.8] * 40 + [-1.0] * 40, ["win"] * 40 + ["loss"] * 40)
    crafted = BootstrapResult(point=0.05, lo=-0.001, hi=0.30,
                              p_greater_than_zero=0.04, n_resamples=500, seed=1)
    with patch.object(ah, "bootstrap_delta", return_value=crafted):
        res = ah._clause_expectancy_gain(baseline, component, 500, seed=1)
    assert res.verdict == "FAIL"


def test_win_rate_floor_skipped_when_immunity_confirmed():
    baseline = _arm([0.3] * 10, ["win"] * 10)
    res = ah._clause_win_rate_floor(baseline, baseline, 500, seed=1,
                                    structurally_immune=True)
    assert res.verdict == "SKIPPED"
    assert "cannot move" in res.detail


def test_win_rate_floor_falls_through_when_immunity_claim_is_false():
    """structurally_immune=True is a claim, not a fact -- if the two arms'
    trade populations actually differ (outcomes flipped), the guard must
    not trust the claim and must run the real bootstrap instead of
    reporting SKIPPED on a false premise."""
    baseline = _arm([0.3] * 70 + [-1.0] * 30, ["win"] * 70 + ["loss"] * 30)
    component = _arm([0.3] * 40 + [-1.0] * 60, ["win"] * 40 + ["loss"] * 60)
    res = ah._clause_win_rate_floor(baseline, component, 500, seed=1,
                                    structurally_immune=True)
    assert res.verdict == "FAIL"
    assert "cannot move" not in res.detail


def test_win_rate_floor_fails_when_wr_collapses():
    baseline = _arm([0.3] * 70 + [-1.0] * 30, ["win"] * 70 + ["loss"] * 30)
    component = _arm([0.3] * 40 + [-1.0] * 60, ["win"] * 40 + ["loss"] * 60)
    res = ah._clause_win_rate_floor(baseline, component, 500, seed=1)
    assert res.verdict == "FAIL"


def test_evaluate_harvest_passes_clean_improvement_at_validation():
    baseline = _arm([0.3] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    component = _arm([0.9] * 60 + [-1.0] * 40, ["win"] * 60 + ["loss"] * 40)
    result = ah.evaluate_harvest(baseline, component, stage="validation",
                                structurally_immune_to_wr=True,
                                permutation_p=0.001)
    assert result.verdict == "PASS"
    assert result.clause("win_rate_floor").verdict == "SKIPPED"
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
