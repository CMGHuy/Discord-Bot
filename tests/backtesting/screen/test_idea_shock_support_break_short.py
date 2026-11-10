"""v211 Idea 1 (spec v209 § Track 2): the first close below the prior 20-day low
inside a SHOCK episode, short at the next open."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from swingbot.core.backtesting.screen.ideas import shock_support_break_short as idea
from tests.backtesting.screen.helpers import (assert_prefix_stable, episodes_covering,
                                              frame, random_walk, shock_context)

#: Breaks (Close < prior 20-day low, Low = Close - 1): bars 50, 51, 60, 75.
CLOSES = [100.0] * 50 + [97.0, 95.0] + [95.0] * 8 + [92.0] * 15 + [89.0] * 5
#: Episode 1 = bars 48..58 (released on 58); episode 2 re-enters on 59, the
#: day after the release, and releases on 70; bar 75 is NORMAL.
EPISODES = [(48, 58), (59, 70)]


def _stock():
    return frame(CLOSES, start="2010-01-04")


def _hits(series):
    return np.flatnonzero(series.to_numpy()).tolist()


def test_the_constants_are_the_frozen_spec_values():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (10, "fixed", "short")
    assert idea.CONTEXT == ("BREADTH_ATR1", "^VIX") and idea.CONTEXT_KIND == "level"
    assert idea.FAMILY == ("shock_support_break_short", "shock_failed_bounce_short")
    assert idea.PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                           "release": 0.10, "low_window": 20, "side": "short"}
    assert idea.SOURCE == sb.SOURCE and idea.SUMMARY.strip()
    assert not hasattr(idea, "ENTRY") and not hasattr(idea, "levels")


def test_the_fixture_breaks_where_the_comment_says():
    assert _hits(idea.low_break(_stock())) == [50, 51, 60, 75]


def test_fires_on_the_first_break_of_each_episode_only():
    """51 is the second break of episode 1; 60 is the first break of episode
    2, entered the day after episode 1's release; 75 breaks while NORMAL."""
    df = _stock()
    out = idea.events(df, shock_context(df.index, EPISODES))
    assert _hits(out) == [50, 60]
    assert out.dtype == bool and out.name == "shock_support_break_short"
    assert out.index.equals(df.index)


def test_without_any_episode_nothing_fires():
    df = _stock()
    assert not idea.events(df, shock_context(df.index, [])).any()


def test_one_long_episode_fires_once():
    df = _stock()
    assert _hits(idea.events(df, shock_context(df.index, [(40, 79)]))) == [50]


def test_a_stock_date_the_context_lacks_is_never_an_event():
    df = _stock()
    thin = {k: v.drop(df.index[50]) for k, v in shock_context(df.index, EPISODES).items()}
    assert not idea.events(df, thin).iloc[50]


def test_the_control_is_every_fresh_break_with_the_shock_state_ignored():
    out = idea.control_events(_stock())
    assert _hits(out) == [50, 60, 75]
    assert out.dtype == bool and out.name == "shock_support_break_short_control"


def test_events_on_t_read_no_later_stock_or_context_bar():
    df = random_walk(700, seed=21)
    ctx = shock_context(df.index, episodes_covering(_hits(idea.low_break(df)), len(df)))

    def fn(d):
        return idea.events(d, {k: v.loc[: d.index[-1]] for k, v in ctx.items()})

    assert fn(df).sum() >= 3                                  # non-vacuous
    assert_prefix_stable(fn, df, [100, 250, 400, 699])
    assert_prefix_stable(idea.control_events, df, [100, 250, 400, 699])
