"""v140 idea registry: four frozen triggers, one parameter set each."""
import dataclasses

import pytest

from swingbot.core.backtesting.screen import ideas
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea


def test_registry_holds_the_first_batch_in_spec_order():
    assert ideas.IDEA_MODULES == ("high52w", "uptrend_pullback", "gap_volume",
                                  "turn_of_month")
    assert list(IDEAS) == list(ideas.IDEA_MODULES)
    assert all(IDEAS[name].name == name for name in IDEAS)


def test_time_caps_are_the_spec_values():
    assert {n: i.time_cap_bars for n, i in IDEAS.items()} == {
        "high52w": 60, "uptrend_pullback": 10, "gap_volume": 20, "turn_of_month": 4}


def test_frozen_parameter_sets():
    assert dict(IDEAS["high52w"].params) == {
        "near_high": 0.95, "lookback": 252, "fast_sma": 50, "slow_sma": 200,
        "quiet_bars": 20}
    assert dict(IDEAS["uptrend_pullback"].params) == {
        "trend_sma": 200, "rsi_n": 2, "rsi_below": 10}
    assert dict(IDEAS["gap_volume"].params) == {
        "gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
    assert dict(IDEAS["turn_of_month"].params) == {
        "day": "last trading day of the calendar month"}


def test_every_idea_is_long_and_cites_its_source():
    for idea in IDEAS.values():
        assert idea.direction == "long"
        assert idea.summary.strip() and idea.source.strip()
        assert callable(idea.events)


def test_params_are_read_only_and_the_idea_is_frozen():
    idea = IDEAS["high52w"]
    with pytest.raises(TypeError):
        idea.params["near_high"] = 0.9
    with pytest.raises(dataclasses.FrozenInstanceError):
        idea.time_cap_bars = 5


def test_an_idea_refuses_a_short_direction_and_a_zero_cap():
    def events(df):
        return df["Close"] > 0
    with pytest.raises(ValueError):
        Idea(name="x", events=events, time_cap_bars=5, direction="short")
    with pytest.raises(ValueError):
        Idea(name="x", events=events, time_cap_bars=0)
