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
