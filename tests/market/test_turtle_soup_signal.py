"""v180: the live Turtle Soup trigger -- bar-for-bar parity with the frozen v140 screen,
no lookahead, masked by default. The screen import is test-only: live code never imports it."""
import inspect

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import backtest
from swingbot.core.backtesting.screen.ideas import turtle_soup as screen
from swingbot.core.market import entry_filters as ef
from swingbot.core.market import turtle_soup as live
from swingbot.core.market.strategy_types import STRATEGY_GATES, TURTLE_SOUP, admits
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

CELL = {"directions": (), "cells": {("bullish", "2w")}}
WALKS = [(7, 500), (11, 300), (23, 1200), (42, 60), (99, 2500)]


def _screen_fixture(low25=95.0, low35=94.0, close35=100.0):
    """The screen tests' fixture (tests/backtesting/screen/test_idea_turtle_soup.py), copied:
    40 flat bars (C 100, L 99); bar 25 sets a 95 low; bar 35 breaks it, closes at close35."""
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[25], lows[35] = low25, low35
    closes[35] = close35
    return frame(closes, lows=lows)


def _equal_lows(age):
    """The old 95 low at bar 20, repeated `age` bars before bar 35, which sweeps it to 94."""
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[20], lows[35 - age], lows[35] = 95.0, 95.0, 94.0
    return frame(closes, lows=lows)


def _assert_parity(df):
    pd.testing.assert_series_equal(live.turtle_soup_signal(df), screen.events(df))


@pytest.mark.parametrize("seed, n", WALKS)
def test_random_walks_match_the_screen_bar_for_bar(seed, n):
    _assert_parity(random_walk(n, seed=seed))


def test_the_random_walk_parity_is_not_vacuous():
    assert sum(int(live.turtle_soup_signal(random_walk(n, seed=s)).sum()) for s, n in WALKS) >= 10


@pytest.mark.parametrize("close35", [100.0, 95.01, 95.0, 94.5])
def test_the_screen_fixture_matches(close35):
    _assert_parity(_screen_fixture(close35=close35))


def test_the_screen_fixture_fires_once_on_the_reclaim():
    assert np.flatnonzero(live.turtle_soup_signal(_screen_fixture()).to_numpy()).tolist() == [35]


@pytest.mark.parametrize("age, fires", [(3, False), (4, True)])
def test_equal_lows_age_from_the_latest_bar_holding_the_low(age, fires):
    df = _equal_lows(age)
    _assert_parity(df)
    assert bool(live.turtle_soup_signal(df).iloc[35]) is fires
    assert live.sweep_frame(df)["age"].iloc[35] == age


def test_short_and_nan_frames_match_the_screen():
    for n in (5, 20, 21):
        _assert_parity(random_walk(n))
    assert not live.turtle_soup_signal(random_walk(20)).any()
    df = random_walk(400, seed=5)
    df.iloc[100, df.columns.get_loc("Low")] = np.nan
    _assert_parity(df)
    assert not live.turtle_soup_signal(df).iloc[100:121].any()


def test_sweep_frame_shape_and_frozen_params():
    df = _screen_fixture()
    sweep = live.sweep_frame(df)
    assert list(sweep.columns) == ["prior_low", "age", "signal"]
    assert sweep.index.equals(df.index)
    assert np.isnan(sweep["prior_low"].iloc[19]) and sweep["prior_low"].iloc[20] == 99.0
    assert (sweep["prior_low"].iloc[35], sweep["age"].iloc[35]) == (95.0, 10.0)
    assert sweep["signal"].dtype == bool
    assert (live.CHANNEL, live.MIN_AGE) == (screen.PARAMS["channel"], screen.PARAMS["min_age"])
    assert live.turtle_soup_signal(df).name == "turtle_soup"


def test_reads_no_later_bar():
    assert live.turtle_soup_signal(random_walk(500)).any()      # non-vacuous
    assert_prefix_stable(live.turtle_soup_signal, random_walk(500), [30, 250, 499])
    assert_prefix_stable(lambda df: live.sweep_frame(df)["age"], random_walk(500), [30, 250, 499])
    assert_prefix_stable(live.turtle_soup_signal, _screen_fixture(), [20, 25, 34, 35, 36, 39])


def test_the_live_module_never_imports_the_screen():
    assert "backtesting" not in inspect.getsource(live)


def test_ships_masked_and_out_of_the_backtest_strategy_list():
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}
    assert TURTLE_SOUP not in backtest.ALL_STRATEGIES
    assert ef.ENTRY_FUNCS[TURTLE_SOUP] is ef.turtle_soup_entries
    df = random_walk(1200, seed=23)
    for horizon_key in ("1w", "2w", "4w"):
        assert not admits(TURTLE_SOUP, "bullish", horizon_key)
        bullish, bearish = ef.entries_for(TURTLE_SOUP, df, horizon_key)
        assert not bullish.any() and not bearish.any()


def test_the_masked_entry_function_skips_the_work(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("masked Turtle Soup computed its signal")
    monkeypatch.setattr(live, "turtle_soup_signal", boom)
    bullish, bearish = ef.turtle_soup_entries(random_walk(500), "2w")
    assert not bullish.any() and not bearish.any()


def test_the_research_cell_unmasks_bullish_2w_only():
    df = random_walk(1200, seed=23)
    expected = live.turtle_soup_signal(df)
    assert expected.any()
    with ef.gate_override(TURTLE_SOUP, CELL):
        bullish, bearish = ef.entries_for(TURTLE_SOUP, df, "2w")
        assert bullish.tolist() == expected.tolist() and not bearish.any()
        other, _ = ef.entries_for(TURTLE_SOUP, df, "4w")
        assert not other.any()
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}
