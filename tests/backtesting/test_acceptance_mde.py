# tests/backtesting/test_acceptance_mde.py
"""Stage 0: is the hypothesis answerable at the N we can actually get?

v68 spent a one-shot budget on a +0.0104R effect with a standard error
near +-0.05R. Nothing stopped it. This does.
"""
import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, design_effect, intracluster_correlation, mde_win_rate,
    project_target_n,
)


def mk(ticker, outcome, date="2021-01-01"):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m",
                    entry_date=date, outcome=outcome,
                    r_multiple=2.0 if outcome == "win" else -1.0,
                    planned_rr=2.0)


def test_icc_is_near_zero_when_tickers_do_not_differ():
    """Every ticker at exactly 50% -- no between-ticker signal at all."""
    trades = []
    for t in range(20):
        trades += [mk(f"T{t}", "win") for _ in range(5)]
        trades += [mk(f"T{t}", "loss") for _ in range(5)]
    assert intracluster_correlation(trades) < 0.05


def test_icc_is_high_when_outcome_is_decided_by_ticker():
    """Half the tickers always win, half always lose -- the outcome is a
    property of the symbol, which is the worst case for independence."""
    trades = []
    for t in range(20):
        outcome = "win" if t % 2 == 0 else "loss"
        trades += [mk(f"T{t}", outcome) for _ in range(10)]
    assert intracluster_correlation(trades) > 0.8


def test_design_effect_is_one_when_every_cluster_is_a_singleton():
    trades = [mk(f"T{t}", "win" if t % 2 else "loss") for t in range(40)]
    assert abs(design_effect(trades) - 1.0) < 1e-9


def test_design_effect_grows_with_cluster_size_and_icc():
    clustered = []
    for t in range(20):
        outcome = "win" if t % 2 == 0 else "loss"
        clustered += [mk(f"T{t}", outcome) for _ in range(10)]
    assert design_effect(clustered) > 5.0


def test_mde_shrinks_as_target_n_grows():
    trades = []
    for t in range(20):
        trades += [mk(f"T{t}", "win") for _ in range(4)]
        trades += [mk(f"T{t}", "loss") for _ in range(6)]
    small = mde_win_rate(trades, target_n=500)
    large = mde_win_rate(trades, target_n=50_000)
    assert small > large > 0.0


def test_mde_is_none_without_decided_trades():
    assert mde_win_rate([mk("T1", "scratch")], target_n=1000) is None


def test_mde_matches_the_textbook_two_proportion_formula():
    """Independent trades (one per ticker) at p=0.5, N=1000 per arm.
    (z_a + z_b) * sqrt(2 p (1-p) / N) = (1.6449 + 0.8416) * sqrt(0.5/1000)
    = 0.0556 -> 5.56pp.
    """
    trades = [mk(f"T{i}", "win" if i % 2 else "loss") for i in range(1000)]
    got = mde_win_rate(trades, target_n=1000)
    assert got == pytest.approx(5.56, abs=0.10)


def test_project_target_n_scales_by_window_length():
    """Achievable N is projected from fold-test years, NEVER read out of
    2024-25 -- touching the validation window to size a run is still
    touching it."""
    assert project_target_n(observed_n=800, observed_days=365,
                            target_days=730) == 1600
