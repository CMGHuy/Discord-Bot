"""build_scenarios' new veto: bullish blocked, bearish untouched."""
import pytest

from swingbot.core.market import levels
from swingbot.core.market.levels import Level, build_scenarios


def _levels():
    # Symmetric distances from the 100.0 current price (used below), not the
    # brief's 90/115: bearish reward:risk is exactly the reciprocal of
    # bullish reward:risk when both scenarios share the same two levels
    # (swapped as target/stop), so an asymmetric pair can only ever clear
    # min_risk_reward=1.0 for ONE direction -- the other never builds, no
    # matter what the veto logic does. Symmetric levels are needed so both
    # directions genuinely build in the unblocked baseline case.
    supports = [Level(price=90.0, sources=["EMA"])]
    resistances = [Level(price=110.0, sources=["Fib"])]
    return supports, resistances


def _build(**kw):
    supports, resistances = _levels()
    return build_scenarios(100.0, supports, resistances, min_reward_pct=3.0,
                           min_stop_distance_pct=2.0, max_stop_distance_pct=20.0,
                           min_risk_reward=1.0, **kw)


def test_both_directions_build_when_nothing_is_blocked():
    directions = {s.direction for s in _build()}
    assert "bullish" in directions and "bearish" in directions


def test_blocking_removes_the_bullish_scenario():
    directions = {s.direction for s in _build(block_bullish=True)}
    assert "bullish" not in directions


def test_blocking_leaves_the_bearish_scenario_alone():
    # The veto is one-sided by design: a dead cat bounce says nothing about
    # shorting into support.
    directions = {s.direction for s in _build(block_bullish=True)}
    assert "bearish" in directions


def test_the_constraint_is_recorded_on_a_surviving_scenario():
    bearish = next(s for s in _build(block_bullish=True)
                   if s.direction == "bearish")
    assert bearish.constraints["not_dead_cat_bounce"] is True


def test_the_default_is_off_so_existing_callers_are_untouched():
    import inspect
    sig = inspect.signature(build_scenarios)
    assert sig.parameters["block_bullish"].default is False
