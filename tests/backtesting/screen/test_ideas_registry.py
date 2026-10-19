"""v140 idea registry: four frozen triggers, one parameter set each."""
import dataclasses
import sys
import types

import pytest

from swingbot.core.backtesting.screen import ideas
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea


def test_registry_holds_the_first_batch_in_spec_order_then_later_ideas():
    assert ideas.IDEA_MODULES == ("high52w", "uptrend_pullback", "gap_volume",
                                  "turn_of_month", "turtle_soup", "quiet_pullback",
                                  "bond_spike_rebound", "dollar_drop")
    assert list(IDEAS) == list(ideas.IDEA_MODULES)
    assert all(IDEAS[name].name == name for name in IDEAS)


def test_time_caps_are_the_spec_values():
    assert {n: i.time_cap_bars for n, i in IDEAS.items()} == {
        "high52w": 60, "uptrend_pullback": 10, "gap_volume": 20, "turn_of_month": 4,
        "turtle_soup": 10, "quiet_pullback": 10, "bond_spike_rebound": 10,
        "dollar_drop": 10}


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
    assert dict(IDEAS["turtle_soup"].params) == {"channel": 20, "min_age": 4}
    assert dict(IDEAS["quiet_pullback"].params) == {
        "trend_sma": 200, "rsi_n": 2, "rsi_below": 10, "quiet_bars": 3,
        "gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}

    assert dict(IDEAS["bond_spike_rebound"].params) == {
        "series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}
    assert dict(IDEAS["dollar_drop"].params) == {
        "series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}


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


def test_every_registered_idea_is_raced_under_one_pinned_shape():
    """One shape per idea, frozen with the idea (v163 spec § One shape per
    idea). Flipping a shape means editing this pin in the same diff."""
    assert ideas.RACE_SHAPES == ("fixed", "trail")
    assert {n: i.race_shape for n, i in IDEAS.items()} == {
        "high52w": "fixed", "uptrend_pullback": "fixed", "gap_volume": "fixed",
        "turn_of_month": "fixed", "turtle_soup": "fixed", "quiet_pullback": "fixed",
        "bond_spike_rebound": "fixed", "dollar_drop": "fixed"}


MURPHY = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def test_only_the_two_intermarket_ideas_read_context_series():
    """v174 § 3: the six older ideas keep `events(df)`; the two new ones
    each name one context series and cite the scope section."""
    assert {n: i.context for n, i in IDEAS.items()} == {
        "high52w": (), "uptrend_pullback": (), "gap_volume": (), "turn_of_month": (),
        "turtle_soup": (), "quiet_pullback": (),
        "bond_spike_rebound": ("TLT",), "dollar_drop": ("UUP",)}
    assert IDEAS["bond_spike_rebound"].source == MURPHY
    assert IDEAS["dollar_drop"].source == MURPHY


def _events(df):
    return df["Close"] > 0


def test_an_idea_defaults_to_the_fixed_shape():
    assert Idea(name="x", events=_events, time_cap_bars=5).race_shape == "fixed"


def test_an_unknown_race_shape_is_refused():
    with pytest.raises(ValueError, match="race shape"):
        Idea(name="x", events=_events, time_cap_bars=60, race_shape="donchian")


def test_a_trail_idea_needs_a_cap_of_at_least_sixty_bars():
    assert ideas.TRAIL_MIN_CAP == 60
    with pytest.raises(ValueError, match="at least 60"):
        Idea(name="x", events=_events, time_cap_bars=59, race_shape="trail")
    assert Idea(name="x", events=_events, time_cap_bars=60,
                race_shape="trail").race_shape == "trail"


def test_a_fixed_idea_keeps_any_cap_of_one_bar_or_more():
    assert Idea(name="x", events=_events, time_cap_bars=4).time_cap_bars == 4


def _fake_module(monkeypatch, name, **attrs):
    module = types.ModuleType(f"{ideas.__name__}.{name}")
    module.CAP, module.PARAMS = attrs.pop("CAP"), {"k": 1}
    module.SUMMARY, module.SOURCE, module.events = "s", "src", _events
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return name


def test_load_reads_the_race_constant_and_defaults_to_fixed(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_plain", CAP=10)
    trail = _fake_module(monkeypatch, "fake_trail", CAP=60, RACE="trail")
    assert ideas._load(plain).race_shape == "fixed"
    assert ideas._load(trail).race_shape == "trail"


def test_load_refuses_a_trail_module_with_a_short_cap(monkeypatch):
    short = _fake_module(monkeypatch, "fake_short_trail", CAP=20, RACE="trail")
    with pytest.raises(ValueError, match="at least 60"):
        ideas._load(short)


def test_the_six_v140_ideas_read_no_context():
    for name in ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
                 "turtle_soup", "quiet_pullback"):
        assert IDEAS[name].context == ()


def test_load_reads_the_context_constant_and_defaults_to_empty(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_no_context", CAP=10)
    reads = _fake_module(monkeypatch, "fake_context", CAP=10, CONTEXT=["TLT"])
    assert ideas._load(plain).context == ()
    assert ideas._load(reads).context == ("TLT",)


def test_context_is_stored_as_a_tuple():
    idea = Idea(name="x", events=lambda df, context: df["Close"] > 0,
                time_cap_bars=5, context=["TLT", "UUP"])
    assert idea.context == ("TLT", "UUP")
