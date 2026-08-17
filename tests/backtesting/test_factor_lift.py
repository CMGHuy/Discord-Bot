import pytest
from scripts.backtest.measure_factor_lift import (
    wilson_interval, factor_lift_table, level_table,
)


def test_wilson_interval_matches_known_values():
    """The plan's own literal (0.8872, 0.9793) doesn't match its own
    formula -- independently verified by hand (Wikipedia's Wilson score
    interval definition, the same one implemented below): centre=0.93336,
    margin=0.04510 -> (0.88825, 0.97846). Corrected here, not the formula."""
    lo, hi = wilson_interval(95, 100)
    assert lo == pytest.approx(0.8882, abs=0.001)
    assert hi == pytest.approx(0.9785, abs=0.001)


def test_wilson_lower_bound_is_brutal_on_small_samples():
    """6/6 wins looks like 100% and is worth almost nothing. This is exactly
    the claim the Level 6 gate exists to reject."""
    lo, _hi = wilson_interval(6, 6)
    assert lo < 0.65


def test_wilson_interval_handles_zero_samples():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def _trade(outcome, **points):
    return {"outcome": outcome, "points": points, "level": 4, "target_count": 3}


def test_factor_lift_table_splits_on_the_factors_own_median():
    """A factor that scores high exactly on winners and low exactly on
    losers must show a large, real lift."""
    trades = (
        [_trade("win", A=10) for _ in range(20)]
        + [_trade("loss", A=0) for _ in range(20)]
    )
    table = factor_lift_table(trades)
    row = next(r for r in table if r["factor"] == "A")
    assert row["lift"] == pytest.approx(1.0, abs=0.01)
    assert row["n_above"] == 20
    assert row["n_at_or_below"] == 20


def test_factor_lift_table_only_counts_trades_where_the_factor_fired():
    """A factor absent from a trade's breakdown (never scored) must not be
    treated as a real zero -- matches the run_factors() None contract."""
    trades = [_trade("win", A=10), _trade("loss")]   # second trade: A absent
    table = factor_lift_table(trades, min_samples=1)
    row = next(r for r in table if r["factor"] == "A")
    assert row["n_above"] + row["n_at_or_below"] == 1


def test_factor_lift_table_skips_a_factor_with_too_few_samples():
    trades = [_trade("win", A=10)]
    table = factor_lift_table(trades, min_samples=5)
    assert not any(r["factor"] == "A" for r in table)


def test_factor_lift_table_handles_a_capped_right_skewed_factor():
    """Regression for the real bug the first TRAIN run surfaced: when most
    fired trades share the factor's own maximum value, the median EQUALS
    the max, so a naive `> median` split leaves n_above=0 -- every such
    factor showed an identical, meaningless lift against an empty
    comparison group (7 of 15 factors, all -0.461, in the actual run).
    A rank/count-based split must always produce two real groups."""
    trades = (
        [_trade("win", A=20) for _ in range(30)]      # most trades hit the cap
        + [_trade("win", A=20) for _ in range(5)]
        + [_trade("loss", A=20) for _ in range(35)]
        + [_trade("loss", A=5) for _ in range(10)]     # the rest score low
    )
    table = factor_lift_table(trades, min_samples=1)
    row = next(r for r in table if r["factor"] == "A")
    assert row["n_above"] > 0
    assert row["n_at_or_below"] > 0


def test_level_table_reports_win_rate_and_wilson_bounds_per_level():
    trades = (
        [{"outcome": "win", "level": 5} for _ in range(80)]
        + [{"outcome": "loss", "level": 5} for _ in range(20)]
    )
    table = level_table(trades)
    row = next(r for r in table if r["level"] == 5)
    assert row["n"] == 100
    assert row["win_rate"] == pytest.approx(0.80, abs=0.001)
    assert 0.0 <= row["wilson_lo"] < row["win_rate"] < row["wilson_hi"] <= 1.0


def test_level_table_excludes_scratch_and_timeout_from_n_and_win_rate():
    """Same convention as backtest.py's own win_rate: evaluated_trades =
    trades where outcome in (win, loss). A scratch/timeout padding the
    denominator would silently understate every win rate this module
    reports and corrupt Task 9's n>=100 significance bar."""
    trades = (
        [{"outcome": "win", "level": 5} for _ in range(9)]
        + [{"outcome": "loss", "level": 5} for _ in range(1)]
        + [{"outcome": "scratch", "level": 5} for _ in range(50)]
        + [{"outcome": "timeout", "level": 5} for _ in range(50)]
    )
    table = level_table(trades)
    row = next(r for r in table if r["level"] == 5)
    assert row["n"] == 10
    assert row["win_rate"] == pytest.approx(0.90, abs=0.001)


def test_factor_lift_win_rate_excludes_scratch_and_timeout():
    """points=[20,20,0,0], median=10 -> above-median group is the two
    A=20 trades (win + scratch), at-or-below is the two A=0 trades
    (loss + timeout). Each group's win rate must come from its ONE
    evaluated trade, not be diluted by the scratch/timeout riding along
    at the same points value."""
    trades = [
        {"outcome": "win", "points": {"A": 20}, "level": 4},
        {"outcome": "scratch", "points": {"A": 20}, "level": 4},
        {"outcome": "loss", "points": {"A": 0}, "level": 4},
        {"outcome": "timeout", "points": {"A": 0}, "level": 4},
    ]
    table = factor_lift_table(trades, min_samples=1)
    row = next(r for r in table if r["factor"] == "A")
    assert row["win_rate_above"] == pytest.approx(1.0)
    assert row["win_rate_at_or_below"] == pytest.approx(0.0)
