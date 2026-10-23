"""range_breakdown_close: a close below the 30-bar range's support, short, next open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from swingbot.core.backtesting.screen.ideas import range_breakdown_close as idea
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk
from tests.backtesting.screen.test_range_breakdown_rules import T, _tall, breakdown_frame


def _positions(df, fn=idea.events):
    return np.flatnonzero(fn(df).to_numpy()).tolist()


def test_the_module_freezes_a_short_fixed_cap_20_next_open_idea():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (20, "fixed", "short")
    assert getattr(idea, "ENTRY", "next_open") == "next_open"
    assert not hasattr(idea, "levels")
    assert idea.PARAMS == {**rb.PARAMS, "trigger": "close[t] < S"}
    assert idea.SOURCE == rb.SOURCE and idea.FAMILY == rb.FAMILY
    assert "close[t] < S" in idea.SUMMARY and "short" in idea.SUMMARY


def test_fires_on_the_close_below_support_only():
    assert _positions(breakdown_frame()) == [T]
    assert idea.events(breakdown_frame()).name == "range_breakdown_close"


@pytest.mark.parametrize("close, low, fires", [
    (98.875, 97.875, True),    # closed below S = 99
    (99.0, 98.0, False),       # closed at S: not below
    (99.5, 98.0, False),       # low broke S, the close did not
])
def test_the_close_must_end_below_support(close, low, fires):
    df = breakdown_frame(event_close=close, event_low=low)
    assert (T in _positions(df)) is fires


def test_events_are_the_setup_with_the_close_trigger():
    walk = random_walk(3000)
    expected = (rb.setup(walk) & (walk["Close"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.events(walk), expected, check_names=False)
    assert idea.events(walk).any()


def test_control_events_drop_the_range_clauses_only():
    tall = breakdown_frame(edit=_tall)
    assert _positions(tall) == []
    assert T in _positions(tall, idea.control_events)
    walk = random_walk(3000)
    expected = (rb.control_setup(walk) & (walk["Close"] < rb.support(walk))).fillna(False)
    pd.testing.assert_series_equal(idea.control_events(walk), expected, check_names=False)
    assert not (idea.events(walk) & ~idea.control_events(walk)).any()


def test_reads_no_later_bar():
    assert _positions(breakdown_frame()) == [T]                    # non-vacuous
    assert_prefix_stable(idea.events, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert idea.events(walk).any()
    assert_prefix_stable(idea.events, walk, [100, 1500, 2999])
    assert_prefix_stable(idea.control_events, walk, [100, 1500, 2999])
