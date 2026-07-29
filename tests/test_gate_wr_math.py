import pytest
from swingbot.core.gate.wr_math import (
    breakeven_wr, implied_expectancy, required_filter_precision, wilson_lower_bound,
)


def test_breakeven_wr_golden():
    assert breakeven_wr(1.5) == pytest.approx(40.0)   # 1/(1+1.5)
    assert breakeven_wr(1.0) == pytest.approx(50.0)


def test_implied_expectancy_95_at_1_5r():
    # 95% WR, +1.5R wins, -1R losses -> 0.95*1.5 - 0.05*1 = +1.375R.
    # No swing system sustains that; the number itself is the honesty check.
    assert implied_expectancy(95.0, 1.5) == pytest.approx(1.375)


def test_filter_precision_needed_for_85_to_95():
    # Lifting 85% -> 95% means removing ~70.2% of losers without touching winners.
    assert required_filter_precision(85.0, 95.0) == pytest.approx(0.7018, abs=1e-3)


def test_wilson_needs_n_59_for_proven_90():
    # 59/59 wins is the smallest all-win sample whose 95% lower bound clears 90%.
    assert wilson_lower_bound(59, 59) > 0.90
    assert wilson_lower_bound(35, 35) < 0.90
