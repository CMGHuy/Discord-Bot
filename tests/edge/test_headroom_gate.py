"""v135 predicate and scope rules (spec: The predicate, Scope, Testing)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import SHORT_STRATEGIES

TWO = ("EMA50", "Rolling S/R")        # two families
ONE = ("Bollinger Bands",)            # one family
SAME = ("EMA20", "EMA50")             # two labels, one family (EMA)
ENTRY, LONG_STOP, SHORT_STOP = 100.0, 98.0, 102.0   # risk 2.0; at h=0.75 the bound is 1.5 away


def lv(price, *sources):
    return Level(price=price, sources=list(sources))


@pytest.fixture
def scope(monkeypatch):
    def set_scope(value, min_r=0.75):
        monkeypatch.setattr(config, "HEADROOM_SCOPE", value)
        monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    return set_scope


@pytest.fixture
def must_not_compute(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("an inactive headroom veto must not read any level")
    monkeypatch.setattr(gates, "nearest_blocker", boom)


@pytest.mark.parametrize("levels,expected", [
    (None, False),
    ([], False),
    ([lv(101.0, *ONE)], False),                      # single family inside the bound
    ([lv(101.0, *TWO)], True),                       # two families inside
    ([lv(101.5, *TWO)], False),                      # exactly at min_r x risk
    ([lv(101.4999, *TWO)], True),
    ([lv(99.0, *TWO)], False),                       # behind entry
    ([lv(100.0, *TWO)], False),                      # at entry: not strictly beyond
    ([lv(101.0, *SAME)], False),                     # EMA20 + EMA50 count as one family
    ([lv(103.0, *TWO), lv(101.0, *ONE)], False),     # the near one is unconfirmed, the confirmed one is far
    ([lv(103.0, *TWO), lv(101.2, *TWO)], True),
])
def test_bullish_predicate(levels, expected):
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", levels, 0.75) is expected


@pytest.mark.parametrize("levels,expected", [
    ([lv(99.0, *TWO)], True),
    ([lv(98.5, *TWO)], False),                       # exactly at the bound
    ([lv(101.0, *TWO)], False),                      # behind a short entry
    ([lv(99.0, *ONE)], False),
])
def test_bearish_mirror(levels, expected):
    assert gates.headroom_rejects(ENTRY, SHORT_STOP, "bearish", levels, 0.75) is expected


def test_zero_min_r_and_zero_risk_never_reject():
    near = [lv(100.01, *TWO)]
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", near, 0.0) is False
    assert gates.headroom_rejects(ENTRY, ENTRY, "bullish", near, 1.0) is False


def test_zero_min_r_never_computes(must_not_compute):
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", [lv(100.5, *TWO)], 0.0) is False


def test_non_finite_prices_pass():
    nan = float("nan")
    assert gates.headroom_rejects(nan, LONG_STOP, "bullish", [lv(101.0, *TWO)], 1.0) is False
    assert gates.headroom_rejects(ENTRY, nan, "bullish", [lv(101.0, *TWO)], 1.0) is False
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", [lv(nan, *TWO)], 1.0) is False


def test_nearest_blocker_reports_the_nearest_confirmed_level_and_the_risk():
    levels = [lv(104.0, *TWO), lv(100.5, *ONE), lv(101.0, *TWO), lv(97.0, *TWO)]
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", levels) == (1.0, 2.0)
    assert gates.nearest_blocker(ENTRY, SHORT_STOP, "bearish", levels) == (3.0, 2.0)
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", [lv(100.5, *ONE)]) is None
    assert gates.nearest_blocker(ENTRY, ENTRY, "bullish", levels) is None
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", None) is None


@pytest.mark.parametrize("reading,min_r,expected", [
    ((1.0, 2.0), 0.5, False),            # exactly at the bound
    ((1.0, 2.0), 0.75, True),
    ((1.0, 2.0), 0.0, False),            # off
    (None, 1.0, False),                  # no confirmed level ahead
])
def test_blocker_inside_is_the_shared_comparison(reading, min_r, expected):
    assert gates.blocker_inside(reading, min_r) is expected


def test_the_predicate_is_the_two_shared_steps_composed():
    levels = [lv(101.0, *TWO), lv(103.0, *TWO)]
    for min_r in (0.5, 0.75, 1.0):
        reading = gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", levels)
        assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", levels, min_r) \
            is gates.blocker_inside(reading, min_r)


def test_frozen_constants():
    assert gates.HEADROOM_MIN_FAMILIES == 2
    assert gates.HEADROOM_STRATEGIES == frozenset(backtest.ALL_STRATEGIES) - {"MACD", "Volume Profile"}
    assert len(gates.HEADROOM_STRATEGIES) == 9
    assert not gates.HEADROOM_STRATEGIES & set(SHORT_STRATEGIES)
    assert gates.HEADROOM_REASON == "headroom"


@pytest.mark.parametrize("strategy", ["MACD", "Volume Profile", None, *SHORT_STRATEGIES])
def test_strategies_outside_the_list_are_never_in_scope(strategy):
    assert gates.strategy_in_headroom_scope(strategy) is False


def test_scopes_never_cross(scope):
    scope("strategy")
    assert gates.headroom_active("strategy", "Fibonacci") is True
    assert gates.headroom_active("strategy", "MACD") is False
    assert gates.headroom_active("confluence") is False
    scope("confluence")
    assert gates.headroom_active("confluence") is True
    assert gates.headroom_active("strategy", "Fibonacci") is False
    scope("off")
    assert not gates.headroom_active("confluence")
    assert not gates.headroom_active("strategy", "Fibonacci")


def test_a_scope_with_zero_min_r_is_inactive(scope):
    scope("strategy", 0.0)
    assert gates.headroom_active("strategy", "Fibonacci") is False
    scope("confluence", 0.0)
    assert gates.headroom_active("confluence") is False


def _plan(entry_price=None):
    return SimpleNamespace(trigger_price=ENTRY, entry_price=entry_price, stop_loss=LONG_STOP,
                           direction="bullish")


def test_plan_gate_flips_with_the_scope_on_the_next_call(scope):
    level_map = ([], [lv(101.0, *TWO)])
    scope("off")
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="RSI") is False
    scope("strategy")
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="RSI") is True
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="MACD") is False
    assert gates.headroom_blocks_plan(_plan(), None, strategy="RSI") is False
    assert gates.headroom_blocks_plan(None, level_map, strategy="RSI") is False


def test_plan_gate_reads_the_filled_price_only_when_the_plan_has_one(scope):
    scope("strategy")
    level_map = ([], [lv(101.0, *TWO)])
    assert gates.planned_entry(_plan()) == ENTRY
    assert gates.planned_entry(_plan(entry_price=101.0)) == 101.0
    assert gates.planned_entry(SimpleNamespace(trigger_price=ENTRY)) == ENTRY
    assert gates.headroom_blocks_plan(_plan(entry_price=101.0), level_map, strategy="RSI") is False


def test_an_inactive_plan_gate_never_touches_the_plan(scope, must_not_compute):
    scope("off")
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="RSI") is False
    scope("strategy", 0.0)
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="RSI") is False
    scope("strategy")
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="MACD") is False


def _scenario(direction, stop):
    return SimpleNamespace(direction=direction, entry=ENTRY, stop_loss=stop)


def test_filter_splits_kept_and_rejected_by_direction(scope):
    scope("confluence")
    bull, bear = _scenario("bullish", LONG_STOP), _scenario("bearish", SHORT_STOP)
    kept, rejected = gates.filter_headroom([bull, bear], [lv(95.0, *TWO)], [lv(101.0, *TWO)])
    assert kept == [bear] and rejected == [bull]


def test_an_inactive_filter_returns_everything_and_never_computes(scope, must_not_compute):
    sentinel = object()
    for value, min_r in (("off", 0.75), ("strategy", 0.75), ("confluence", 0.0)):
        scope(value, min_r)
        assert gates.filter_headroom([sentinel], [], [lv(101.0, *TWO)]) == ([sentinel], [])


def test_level_map_levels_flattens_or_empties():
    below, above = lv(95.0, *TWO), lv(101.0, *TWO)
    assert gates.level_map_levels(([below], [above])) == [below, above]
    assert gates.level_map_levels(None) == []
