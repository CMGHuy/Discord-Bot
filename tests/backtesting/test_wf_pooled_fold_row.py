"""v180 A1 at stage 2: fold rows on the pooled dWR; per-fold N counts decided ADDED trades
(spec § The funnel, stage 2), never the pooled book."""
import pytest

from swingbot.core.backtesting.acceptance import delta_standardised_win_rate
from swingbot.core.backtesting.backtest_wf import gate_win_rate, win_rate_fold_row
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade


def test_the_standardised_row_is_todays_row():
    baseline, component = _arms()
    assert win_rate_fold_row("2021", baseline, component) == {
        "test_years": "2021",
        "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
        "n": 400}


def test_pooled_row_counts_only_decided_added_trades():
    baseline, component = _arms(n_tickers=3)                     # 30 added, all decided
    extra = [_trade("T0", "Turtle Soup", "2w", 90, "timeout")]
    row = win_rate_fold_row("2022", baseline, component + extra, wr_statistic="pooled")
    assert set(row) == {"test_years", "delta_win_rate_pp", "n", "wr_statistic"}
    assert (row["test_years"], row["n"], row["wr_statistic"]) == ("2022", 30, "pooled")
    assert row["delta_win_rate_pp"] > 0


def test_a_fold_with_no_decided_added_trade_fails_the_floor():
    baseline, _ = _arms()
    undecided = [_trade(f"T{t}", "Turtle Soup", "2w", 60, "timeout") for t in range(40)]
    row = win_rate_fold_row("2023", baseline, baseline + undecided, wr_statistic="pooled")
    assert row["n"] == 0 and row["delta_win_rate_pp"] == pytest.approx(0.0)
    assert gate_win_rate({"folds": [row, row, row]}) == "FAIL"


def test_the_floor_reads_added_trades_not_the_pooled_book():
    baseline, component = _arms(n_tickers=3)                     # 30 added
    passing = win_rate_fold_row("2021", baseline, component, wr_statistic="pooled")
    thin = win_rate_fold_row("2021", baseline, component[:-1], wr_statistic="pooled")
    assert gate_win_rate({"folds": [passing] * 3}) == "PASS"
    assert thin["n"] == 29 and gate_win_rate({"folds": [thin] * 3}) == "FAIL"


def test_an_unknown_statistic_is_refused():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(ValueError):
        win_rate_fold_row("2021", baseline, component, wr_statistic="mixed")
