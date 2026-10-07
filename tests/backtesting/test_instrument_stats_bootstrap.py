"""v136 §4: the week-clustered bootstrap resamples whole ISO weeks of entry
date, across every ticker, so a market-wide move is one resampling unit
instead of N correlated 'independent' tickers."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.instrument import stats

FAST = dict(n_resamples=300, seed=42)


def _expectancy(_baseline, component):
    return acceptance.expectancy_r(component)


def _trade(ticker, entry_date, win, r_win=2.0):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m",
                    entry_date=entry_date, outcome="win" if win else "loss",
                    r_multiple=r_win if win else -1.0, planned_rr=2.0)


def market_wide(n_tickers=20, n_weeks=20):
    """Every ticker shares its week's outcome: a market-wide move. Each
    ticker carries the identical sequence, so resampling tickers returns the
    same population on every draw; only resampling weeks sees the dependence."""
    monday = date(2021, 1, 4)
    out = []
    for w in range(n_weeks):
        win = w % 3 != 0
        for t in range(n_tickers):
            day = monday + timedelta(weeks=w, days=t % 5)
            out.append(_trade(f"T{t}", day.isoformat(), win,
                              r_win=1.0 + 0.25 * (w % 5)))
    return out


@pytest.mark.parametrize("entry_date, key", [
    ("2020-12-31", "2020-W53"),            # Thursday
    ("2021-01-03", "2020-W53"),            # Sunday still in the ISO year before
    ("2021-01-04", "2021-W01"),            # Monday starts ISO week 1
    ("2021-01-10", "2021-W01"),
    ("2021-01-11", "2021-W02"),
    ("2024-12-30", "2025-W01"),            # calendar 2024, ISO year 2025
    ("2021-01-04 00:00:00", "2021-W01"),   # str(pandas.Timestamp)
])
def test_iso_week_key_follows_the_iso_calendar(entry_date, key):
    assert stats.iso_week_key(entry_date) == key


def test_iso_week_key_accepts_a_date_object():
    assert stats.iso_week_key(date(2021, 1, 4)) == "2021-W01"


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_a_trade_without_an_entry_date_cannot_be_clustered(missing):
    with pytest.raises(ValueError, match="entry_date"):
        stats.iso_week_key(missing)


def test_group_by_week_pools_every_ticker_in_one_week():
    trades = [_trade("AAA", "2021-01-04", True), _trade("BBB", "2021-01-08", False),
              _trade("AAA", "2021-01-11", True)]
    grouped = stats.group_by_week(trades)
    assert sorted(grouped) == ["2021-W01", "2021-W02"]
    assert [t.ticker for t in grouped["2021-W01"]] == ["AAA", "BBB"]


def test_group_by_week_reads_row_namespaces_too():
    rows = [SimpleNamespace(ticker="AAA", entry_date="2021-01-04")]
    assert list(stats.group_by_week(rows)) == ["2021-W01"]


def test_defaults_are_the_spec_values():
    assert stats.WEEK_BOOTSTRAP_RESAMPLES == 10_000
    assert stats.WEEK_BOOTSTRAP_SEED == 42


def test_week_bootstrap_is_deterministic_under_a_fixed_seed():
    pop = market_wide()
    a = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    b = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    assert np.array_equal(a, b)


def test_a_different_seed_gives_a_different_draw():
    pop = market_wide()
    a = stats.week_cluster_bootstrap([], pop, _expectancy, n_resamples=300, seed=42)
    b = stats.week_cluster_bootstrap([], pop, _expectancy, n_resamples=300, seed=7)
    assert not np.array_equal(a, b)


def test_week_clustering_sees_a_market_wide_move_ticker_clustering_misses():
    pop = market_wide()
    by_ticker = acceptance.cluster_bootstrap([], pop, _expectancy, **FAST)
    by_week = stats.week_cluster_bootstrap([], pop, _expectancy, **FAST)
    assert np.ptp(by_ticker) == pytest.approx(0.0, abs=1e-12)
    assert np.ptp(by_week) > 0.5


def test_both_arms_share_one_week_draw():
    """Pairing survives: identical arms give a delta of exactly 0 on every draw."""
    pop = market_wide()
    draws = stats.week_cluster_bootstrap(pop, list(pop), acceptance.delta_expectancy_r,
                                         **FAST)
    assert draws.size == 300
    assert np.allclose(draws, 0.0)


def test_undefined_draws_are_dropped_not_zero_filled():
    pop = market_wide(n_tickers=2, n_weeks=6)
    calls = []

    def every_other(_baseline, component):
        calls.append(1)
        return None if len(calls) % 2 else acceptance.expectancy_r(component)

    draws = stats.week_cluster_bootstrap([], pop, every_other, n_resamples=100, seed=42)
    assert draws.size == 50


def test_no_trades_gives_an_empty_array():
    assert stats.week_cluster_bootstrap([], [], _expectancy, **FAST).size == 0


def test_one_resample_draws_as_many_weeks_as_exist():
    pop = market_wide(n_tickers=3, n_weeks=4)
    sizes = []

    def size(_baseline, component):
        sizes.append(len(component))
        return 0.0

    stats.week_cluster_bootstrap([], pop, size, n_resamples=50, seed=42)
    assert set(sizes) == {12}   # 4 weeks drawn x 3 trades per week, whichever weeks
