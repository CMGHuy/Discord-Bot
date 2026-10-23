"""range_breakdown_stop: a resting sell stop at the 30-bar range's support, short, level entry."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from swingbot.core.backtesting.screen.ideas import range_breakdown_close as close_idea
from swingbot.core.backtesting.screen.ideas import range_breakdown_stop as idea
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk
from tests.backtesting.screen.test_range_breakdown_rules import T, _tall, breakdown_frame


def _positions(df, fn=idea.events):
    return np.flatnonzero(fn(df).to_numpy()).tolist()


def test_the_module_freezes_a_short_fixed_cap_20_level_idea():
    assert (idea.CAP, idea.RACE, idea.DIRECTION, idea.ENTRY) == (20, "fixed", "short", "level")
    assert idea.PARAMS == {**rb.PARAMS, "trigger": "low[t] < S", "level": "S"}
    assert idea.SOURCE == rb.SOURCE and idea.FAMILY == rb.FAMILY
    assert "low[t] < S" in idea.SUMMARY and "sell stop" in idea.SUMMARY


def test_fires_when_the_low_trades_through_support():
    assert _positions(breakdown_frame()) == [T]
    assert idea.events(breakdown_frame()).name == "range_breakdown_stop"


@pytest.mark.parametrize("low, fires", [
    (98.875, True),    # traded below S = 99: the sell stop fills
    (99.0, False),     # touched S only: Low[t] < level is strict
])
def test_the_low_must_trade_below_support(low, fires):
    df = breakdown_frame(event_close=100.0, event_low=low)
    assert (T in _positions(df)) is fires


def test_a_close_back_inside_the_range_still_fires():
    df = breakdown_frame(event_close=100.0, event_low=98.0, event_open=100.0)
    assert T in _positions(df)
    assert T not in _positions(df, close_idea.events)


def test_the_level_is_support_on_every_bar():
    df = breakdown_frame()
    pd.testing.assert_series_equal(idea.levels(df), rb.support(df), check_names=False)
    assert idea.levels(df).iloc[T] == 99.0


def test_the_order_is_placed_from_bars_before_t():
    df = breakdown_frame()
    wild = df.copy()
    wild.iloc[T] = [50.0, 300.0, 10.0, 20.0, 1e6]
    assert idea.levels(wild).iloc[T] == idea.levels(df).iloc[T] == 99.0


def test_the_trigger_reads_only_bar_ts_low():
    """Nothing beyond bar t's Open/Low decides the order: High and Close of
    bar t, and every later bar, can change without moving the event."""
    df = breakdown_frame(event_close=100.0, event_low=98.0)
    moved = df.copy()
    moved.iloc[T, moved.columns.get_loc("High")] = 250.0
    moved.iloc[T, moved.columns.get_loc("Close")] = 40.0
    moved.iloc[T + 1:, moved.columns.get_loc("Low")] = 1.0
    assert idea.events(moved).iloc[T] and idea.events(df).iloc[T]
    assert idea.levels(moved).iloc[T] == idea.levels(df).iloc[T]


def test_events_are_the_setup_with_the_low_trigger():
    walk = random_walk(3000)
    expected = (rb.setup(walk) & (walk["Low"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.events(walk), expected, check_names=False)


def test_every_close_event_is_a_stop_event():
    """The two ideas are nested (spec Part C): Close < S implies Low < S."""
    for seed in (1, 2, 7, 13):
        walk = random_walk(2700, seed=seed)
        assert not (close_idea.events(walk) & ~idea.events(walk)).any(), seed
    assert idea.events(random_walk(2700, seed=7)).sum() > close_idea.events(
        random_walk(2700, seed=7)).sum()


def test_control_events_drop_the_range_clauses_only():
    tall = breakdown_frame(edit=_tall)
    assert _positions(tall) == []
    assert T in _positions(tall, idea.control_events)
    walk = random_walk(3000)
    expected = (rb.control_setup(walk) & (walk["Low"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.control_events(walk), expected, check_names=False)


def test_reads_no_later_bar():
    assert _positions(breakdown_frame()) == [T]                    # non-vacuous
    assert_prefix_stable(idea.events, breakdown_frame(), [60, 89, 90, 91, 94])
    assert_prefix_stable(idea.levels, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert idea.events(walk).any()
    for fn in (idea.events, idea.levels, idea.control_events):
        assert_prefix_stable(fn, walk, [100, 1500, 2999])
