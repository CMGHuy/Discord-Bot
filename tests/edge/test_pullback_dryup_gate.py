"""v122 predicate and scope rules (spec: Testing -- Predicate, Scope)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.market import entry_filters, structure
from tests.edge.pullback_frames import IMPULSE_VOLUME, mirror, pullback_frame

FROZEN = {"Fibonacci", "EMA Crossover", "Break & Retest", "RSI", "RSI Divergence",
          "MA Ribbon", "VWAP"}


@pytest.fixture
def ratio(monkeypatch):
    """Pin pullback_vol_ratio to a chosen value and record each call."""
    state = {"value": None, "calls": []}

    def fake(df, direction):
        state["calls"].append(direction)
        return state["value"]
    monkeypatch.setattr(gates, "pullback_vol_ratio", fake)
    return state


@pytest.fixture
def scope(monkeypatch):
    def set_scope(value, max_ratio=0.75):
        monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", value)
        monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", max_ratio)
    return set_scope


@pytest.mark.parametrize("value,rejects", [
    (None, False), (0.75, False), (0.75 + 1e-9, True), (0.30, False), (5.0, True),
    (float("nan"), False)])
def test_predicate_boundaries(ratio, value, rejects):
    ratio["value"] = value
    assert gates.pullback_dryup_rejects(object(), "bullish", 0.75) is rejects


@pytest.mark.parametrize("value,max_ratio,expected", [
    (0.75, 0.75, False), (0.7500001, 0.75, True), (None, 0.75, False),
    (float("nan"), 0.75, False), (9.0, 0.0, False)])
def test_ratio_exceeds_is_the_shared_comparison(value, max_ratio, expected):
    assert gates.ratio_exceeds(value, max_ratio) is expected


def test_zero_max_ratio_never_rejects_and_never_computes(ratio):
    ratio["value"] = 99.0
    assert gates.pullback_dryup_rejects(object(), "bullish", 0.0) is False
    assert ratio["calls"] == []


def test_direction_reaches_the_instrument(ratio):
    ratio["value"] = 0.1
    gates.pullback_dryup_rejects(object(), "bearish", 0.6)
    assert ratio["calls"] == ["bearish"]


def test_real_instrument_bullish_and_bearish_mirror():
    frame = pullback_frame(0.9 * IMPULSE_VOLUME)
    assert structure.pullback_vol_ratio(frame, "bullish") == pytest.approx(0.9)
    assert structure.pullback_vol_ratio(mirror(frame), "bearish") == pytest.approx(0.9)
    for df, direction in ((frame, "bullish"), (mirror(frame), "bearish")):
        assert gates.pullback_dryup_rejects(df, direction, 0.75) is True
        assert gates.pullback_dryup_rejects(df, direction, 0.90) is False


def test_frozen_list_is_exact_and_names_real_entry_functions():
    assert gates.PULLBACK_DRYUP_STRATEGIES == frozenset(FROZEN)
    assert FROZEN <= set(entry_filters.ENTRY_FUNCS)


@pytest.mark.parametrize("strategy", ["MACD", "Volume Profile", "Support/Resistance",
                                      "Elliott Wave", "Fibonacci Continuation", None])
def test_strategies_outside_the_list_are_never_in_scope(strategy):
    assert gates.strategy_in_dryup_scope(strategy) is False


def test_ema_crossover_only_in_pullback_mode(monkeypatch):
    assert gates.strategy_in_dryup_scope("EMA Crossover") is True
    monkeypatch.setitem(entry_filters.DEFAULT_PARAMS["EMA Crossover"], "entry_mode", "cross")
    assert gates.strategy_in_dryup_scope("EMA Crossover") is False


def test_scopes_never_cross(scope):
    scope("strategy")
    assert gates.pullback_dryup_scoped("strategy", "Fibonacci") is True
    assert gates.pullback_dryup_scoped("confluence") is False
    scope("confluence")
    assert gates.pullback_dryup_scoped("confluence") is True
    assert gates.pullback_dryup_scoped("strategy", "Fibonacci") is False
    scope("off")
    assert not gates.pullback_dryup_scoped("confluence")
    assert not gates.pullback_dryup_scoped("strategy", "Fibonacci")


def test_scope_flip_takes_effect_on_the_next_call(scope, ratio):
    ratio["value"] = 5.0
    scope("off")
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is False
    scope("strategy")
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is True


def test_blocks_off_scope_never_computes(scope, ratio):
    ratio["value"] = 5.0
    scope("off", 0.6)
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is False
    sentinel = object()
    assert gates.filter_pullback_dryup([sentinel], object()) == ([sentinel], [])
    scope("confluence", 0.0)
    assert gates.filter_pullback_dryup([sentinel], object()) == ([sentinel], [])
    assert ratio["calls"] == []


def test_filter_splits_kept_and_rejected_by_direction(scope, monkeypatch):
    monkeypatch.setattr(gates, "pullback_vol_ratio",
                        lambda df, direction: 0.95 if direction == "bullish" else None)
    scope("confluence", 0.75)
    bull, bear = SimpleNamespace(direction="bullish"), SimpleNamespace(direction="bearish")
    kept, rejected = gates.filter_pullback_dryup([bull, bear], object())
    assert kept == [bear] and rejected == [bull]
