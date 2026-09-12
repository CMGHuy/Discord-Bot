import math

import pandas as pd
import pytest

from swingbot.core.analytics import risk_metrics as rm


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2026-01-01", periods=len(values)))


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"Close": closes}, index=pd.bdate_range("2026-01-01", periods=len(closes)))


class TestValueAtRisk:
    def test_is_the_fifth_percentile_reported_as_a_positive_loss(self):
        returns = _series([-0.10, -0.05, 0.0, 0.01, 0.02] * 20)
        var = rm.value_at_risk(returns, level=0.95)
        assert var > 0
        assert var == pytest.approx(0.10, abs=0.02)

    def test_is_none_for_a_series_too_short_to_have_a_tail(self):
        assert rm.value_at_risk(_series([0.01, -0.01])) is None

    def test_is_none_for_an_empty_series(self):
        assert rm.value_at_risk(_series([])) is None

    def test_is_none_for_a_flat_series_rather_than_zero(self):
        """C2: a 20+ bar series with no spread must read as "insufficient
        data", exactly like `annualised_vol` on the same input -- not as a
        VaR of 0, which reads as "no risk"."""
        assert rm.value_at_risk(_series([0.0] * 60)) is None

    def test_floors_a_non_negative_quantile_at_zero(self):
        """C2: a book where even the worst 5% of days were flat or up has a
        positive 5th-percentile return -- the reported loss floors at 0
        rather than showing a negative "loss" figure."""
        returns = _series([0.01, 0.02, 0.03, 0.04, 0.05] * 20)
        var = rm.value_at_risk(returns)
        assert var == 0.0


class TestExpectedShortfall:
    def test_is_at_least_as_large_as_var(self):
        returns = _series([-0.20, -0.10, -0.05, 0.0, 0.01] * 20)
        assert rm.expected_shortfall(returns) >= rm.value_at_risk(returns)

    def test_is_none_when_var_is_none(self):
        assert rm.expected_shortfall(_series([0.01])) is None

    def test_is_none_for_a_flat_series_rather_than_zero(self):
        """C2: same guard as value_at_risk -- a flat series is "insufficient
        data", not a shortfall of 0."""
        assert rm.expected_shortfall(_series([0.0] * 60)) is None

    def test_floors_a_non_negative_tail_mean_at_zero(self):
        returns = _series([0.01, 0.02, 0.03, 0.04, 0.05] * 20)
        assert rm.expected_shortfall(returns) == 0.0


class TestAnnualisedVol:
    def test_scales_the_daily_deviation_by_root_252(self):
        returns = _series([0.01, -0.01] * 60)
        daily = returns.std(ddof=1)
        assert rm.annualised_vol(returns) == pytest.approx(daily * math.sqrt(252))

    def test_is_none_for_a_flat_series_rather_than_zero(self):
        assert rm.annualised_vol(_series([0.0] * 60)) is None


class TestBeta:
    def test_a_portfolio_that_is_the_benchmark_has_beta_one(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        assert rm.beta_vs(bench, bench) == pytest.approx(1.0)

    def test_a_portfolio_of_twice_the_benchmark_has_beta_two(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        assert rm.beta_vs(bench * 2, bench) == pytest.approx(2.0)

    def test_is_none_when_the_benchmark_never_moves(self):
        bench = _series([0.0] * 80)
        assert rm.beta_vs(_series([0.01] * 80), bench) is None

    def test_uses_only_overlapping_days(self):
        bench = _series([0.01, -0.02, 0.03, -0.01] * 20)
        short = bench.iloc[:40]
        assert rm.beta_vs(short, bench) is not None


class TestSharpeOfR:
    def test_is_mean_over_standard_deviation(self):
        assert rm.sharpe_of([1.0, -1.0, 2.0, -1.0, 1.0]) == pytest.approx(
            pd.Series([1.0, -1.0, 2.0, -1.0, 1.0]).mean()
            / pd.Series([1.0, -1.0, 2.0, -1.0, 1.0]).std(ddof=1)
        )

    def test_is_none_when_every_trade_returned_the_same(self):
        assert rm.sharpe_of([1.0, 1.0, 1.0]) is None

    def test_is_none_for_fewer_than_two_trades(self):
        assert rm.sharpe_of([1.0]) is None

    def test_is_none_for_no_trades_rather_than_zero(self):
        assert rm.sharpe_of([]) is None


class TestMaxDrawdownR:
    def test_measures_the_largest_peak_to_trough_fall(self):
        assert rm.max_drawdown_r([1.0, 1.0, -3.0, 1.0]) == pytest.approx(3.0)

    def test_is_zero_for_a_curve_that_only_rises(self):
        assert rm.max_drawdown_r([1.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_is_none_for_no_trades(self):
        assert rm.max_drawdown_r([]) is None


class TestPortfolioReturns:
    def test_weights_each_position_by_its_share_of_notional(self):
        bars = {"A": _frame([100, 110]), "B": _frame([100, 100])}
        out = rm.portfolio_returns({"A": 0.5, "B": 0.5}, bars)
        assert out.iloc[-1] == pytest.approx(0.05)

    def test_drops_days_a_position_has_no_bar_for(self):
        bars = {"A": _frame([100, 110, 121]), "B": _frame([100, 100])}
        assert len(rm.portfolio_returns({"A": 0.5, "B": 0.5}, bars)) == 1

    def test_is_empty_for_an_empty_book(self):
        assert rm.portfolio_returns({}, {}).empty


class TestCorrelationMatrix:
    def test_the_diagonal_is_one(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 55, 52, 60] * 10)}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][0] == pytest.approx(1.0)
        assert m[1][1] == pytest.approx(1.0)

    def test_is_symmetric(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 52, 55, 53] * 10)}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] == pytest.approx(m[1][0])

    def test_two_symbols_that_move_together_correlate_near_one(self):
        closes = [100, 110, 105, 120] * 10
        bars = {"A": _frame(closes), "B": _frame([c * 2 for c in closes])}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] == pytest.approx(1.0, abs=0.01)

    def test_a_zero_variance_pair_is_none_not_nan(self):
        """C1: a flat-price leg (a halted ticker, a stale cache entry) makes
        .corr() return NaN. float('nan') survives Python's own float() cast,
        but Flask's default JSON provider then emits the literal token
        `NaN` -- invalid JSON that blanks the whole page on the browser
        side. It must come out as None instead."""
        bars = {"A": _frame([100.0] * 40), "B": _frame([100, 110, 105, 120] * 10)}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] is None
        assert m[1][0] is None
        for row in m:
            for value in row:
                assert value is None or not math.isnan(value)

    def test_a_pair_with_too_little_overlap_is_none_not_zero(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10), "B": _frame([50, 55])}
        _, m = rm.correlation_matrix(["A", "B"], bars)
        assert m[0][1] is None

    def test_a_symbol_with_no_bars_yields_a_row_of_nones_and_keeps_its_label(self):
        bars = {"A": _frame([100, 110, 105, 120] * 10)}
        labels, m = rm.correlation_matrix(["A", "GHOST"], bars)
        assert labels == ["A", "GHOST"]
        assert m[1][0] is None

    def test_labels_keep_the_order_they_were_given(self):
        bars = {"B": _frame([100, 110] * 20), "A": _frame([100, 105] * 20)}
        labels, _ = rm.correlation_matrix(["B", "A"], bars)
        assert labels == ["B", "A"]

    def test_an_empty_book_yields_empty_labels_and_matrix(self):
        assert rm.correlation_matrix([], {}) == ([], [])
