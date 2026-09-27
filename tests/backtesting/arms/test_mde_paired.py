import numpy as np
import pytest

from swingbot.core.backtesting.acceptance import (
    ArmTrade, delta_expectancy_r, delta_standardised_win_rate, mde_paired,
    mde_win_rate,
)


def _arm(rng, n_tickers=40, per=25, p=0.4, date_offset=0):
    out = []
    for ticker_index in range(n_tickers):
        for trade_index in range(per):
            win = rng.random() < p
            out.append(ArmTrade(
                ticker=f"T{ticker_index}", strategy="MACD", horizon_key="3m",
                entry_date=f"D{trade_index + date_offset:04d}",
                outcome="win" if win else "loss",
                r_multiple=2.0 if win else -1.0, planned_rr=2.0,
            ))
    return out


def _decided(arm):
    return sum(trade.outcome in ("win", "loss") for trade in arm)


def test_small_paired_change_has_far_smaller_mde_than_unpaired():
    rng = np.random.default_rng(1)
    base = _arm(rng)
    component, flipped = [], set()
    for trade in base:
        if trade.outcome == "loss" and trade.ticker not in flipped:
            flipped.add(trade.ticker)
            trade = ArmTrade(**{**trade.__dict__, "outcome": "win", "r_multiple": 2.0})
        component.append(trade)
    count = _decided(base)
    paired = mde_paired(base, component, delta_standardised_win_rate,
                        observed_n=count, target_n=count)
    unpaired = mde_win_rate(base, target_n=count)
    assert paired is not None and unpaired is not None
    assert paired < 0.5 * unpaired


def test_independent_arms_match_the_unpaired_formula():
    rng = np.random.default_rng(2)
    base, component = _arm(rng), _arm(rng, date_offset=10_000)
    count = _decided(base)
    paired = mde_paired(base, component, delta_standardised_win_rate,
                        observed_n=count, target_n=count)
    unpaired = mde_win_rate(base, target_n=count)
    assert 0.7 * unpaired < paired < 1.4 * unpaired


def test_scales_with_sqrt_of_target_n():
    rng = np.random.default_rng(3)
    base, component = _arm(rng), _arm(rng, date_offset=10_000)
    count = _decided(base)
    one = mde_paired(base, component, delta_expectancy_r,
                     observed_n=count, target_n=count)
    four = mde_paired(base, component, delta_expectancy_r,
                      observed_n=count, target_n=4 * count)
    assert four == pytest.approx(one / 2.0)


def test_undefined_inputs_return_none():
    rng = np.random.default_rng(4)
    base = _arm(rng, n_tickers=3)
    assert mde_paired(base, base, delta_expectancy_r, observed_n=0, target_n=10) is None
    assert mde_paired(base, base, delta_expectancy_r, observed_n=10, target_n=0) is None
    assert mde_paired([], [], delta_expectancy_r, observed_n=10, target_n=10) is None
