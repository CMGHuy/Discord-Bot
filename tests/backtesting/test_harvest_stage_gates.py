from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.acceptance_harvest import permutation_p_expectancy
from swingbot.core.backtesting.backtest_wf import gate_expectancy_harvest


def _fold(d, n=40):
    return {"test_years": "y", "delta_expectancy_r": d, "n_tp1": n}


def test_harvest_fold_gate():
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.01), _fold(-0.01)]}) == "PASS"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(-0.01), _fold(-0.01)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.05), _fold(-0.03)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(0.05), _fold(0.05, n=29)]}) == "FAIL"
    assert gate_expectancy_harvest({"folds": [_fold(0.05), _fold(None), _fold(0.05)]}) == "FAIL"


def _t(ticker, r, i):
    return ArmTrade(ticker, "S", "2w", f"2021-01-{i:02d}", "win", r, 2.0)


def test_permutation_detects_a_uniform_lift_and_not_noise():
    base = [_t(f"T{k}", 1.0, i) for k in range(30) for i in range(1, 4)]
    lift = [_t(t.ticker, t.r_multiple + 0.3, int(t.entry_date[-2:])) for t in base]
    assert permutation_p_expectancy(base, lift) < 0.05
    assert permutation_p_expectancy(base, base) == 1.0
