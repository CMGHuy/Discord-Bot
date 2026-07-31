"""Plan v8 Task V11: the reachability screen behind the target floor.

The floor on its own just points targets into a wall -- raising TP1 to 2.5%
achieves nothing if the first resistance sits at +0.8% and price stalls
there. This screen refuses those setups, and while `TARGET_FLOOR_ENABLED` is
off it reports without refusing (V12's log-only survival week).
"""
import types

import pytest

from swingbot import config
from swingbot.core.plan_engine import target_is_reachable
from swingbot.core.scanning.embeds import _build_requirement_checks, _reachability_check


class _Level:
    def __init__(self, price):
        self.price = price


def _levels(*prices):
    return [_Level(p) for p in prices]


def _scenario(direction="bullish", entry=100.0):
    return types.SimpleNamespace(
        direction=direction, entry=entry, market_price=entry,
        stop_loss=98.0 if direction == "bullish" else 102.0,
        target_distance_pct=5.0, stop_distance_pct=2.0,
        risk_reward_ratio=1.5,
        constraints={"min_reward": True, "min_stop_distance": True,
                     "max_stop_distance": True, "min_risk_reward": True},
    )


@pytest.fixture(autouse=True)
def floor_on(monkeypatch):
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", True)
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 2.5)


# -- the primitive ----------------------------------------------------------

def test_level_beyond_the_floor_is_reachable():
    # Nearest resistance at 103 clears the 102.5 floor.
    assert target_is_reachable(_prices(103.0, 110.0), [], "bullish", 100.0) == \
        (True, "level_beyond_floor")


def test_a_nearer_level_is_a_wall():
    # Resistance at 100.8 caps the move well short of 102.5.
    assert target_is_reachable(_prices(100.8, 110.0), [], "bullish", 100.0) == \
        (False, "wall")


def test_level_exactly_at_the_floor_counts_as_reachable():
    assert target_is_reachable(_prices(102.5), [], "bullish", 100.0)[0] is True


def test_no_levels_ahead_is_blue_sky_not_unsupported():
    """Recorded judgment call: nothing ahead means nothing is capping the
    move. Reported under its own reason so V12 can measure how often it
    fires before V28 enforces anything."""
    assert target_is_reachable([], [], "bullish", 100.0) == (True, "no_levels")


def test_levels_behind_entry_are_ignored():
    # Resistances below entry are already passed -- they cannot be the wall.
    assert target_is_reachable(_prices(95.0, 99.0), [], "bullish", 100.0) == \
        (True, "no_levels")


def test_bearish_mirror():
    assert target_is_reachable([], _prices(97.0, 90.0), "bearish", 100.0) == \
        (True, "level_beyond_floor")
    assert target_is_reachable([], _prices(99.2, 90.0), "bearish", 100.0) == \
        (False, "wall")


def test_floor_width_moves_the_verdict(monkeypatch):
    """The screen is defined against MIN_TARGET_PCT, so widening the floor
    must be able to turn a passing setup into a wall."""
    above = _prices(103.0)
    assert target_is_reachable(above, [], "bullish", 100.0)[0] is True
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 5.0)
    assert target_is_reachable(above, [], "bullish", 100.0) == (False, "wall")


def _prices(*prices):
    return list(prices)


# -- the requirement row ----------------------------------------------------

def test_check_fails_a_walled_setup():
    check = _reachability_check(_scenario(), (_levels(), _levels(100.8, 110.0)))
    assert check.key == "target_reachable" and check.passed is False
    assert "nearest level is inside" in check.detail


def test_check_passes_when_structure_supports_the_move():
    check = _reachability_check(_scenario(), (_levels(), _levels(103.0)))
    assert check.passed is True


def test_check_is_report_only_while_the_floor_is_disabled(monkeypatch):
    """V12 Step 2: the screen must measure a full week without removing a
    single alert, or the survival number it produces is measuring itself."""
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    check = _reachability_check(_scenario(), (_levels(), _levels(100.8)))
    assert check.passed is True
    assert "log-only" in check.detail
    assert "nearest level is inside" in check.detail   # still says what it found


def test_no_level_map_adds_no_row():
    """Absence of data is never a failure -- callers without a level map
    simply don't get the check."""
    assert _reachability_check(_scenario(), None) is None


# -- integration with the requirement list ----------------------------------

def _checks(level_map):
    conf = types.SimpleNamespace(level=5, label="Very strong", score=90)
    return _build_requirement_checks(_scenario(), (3, ["Fib"]), conf, 2,
                                     level_map=level_map)


def test_requirement_list_gains_the_row_only_with_a_level_map():
    keys = {c.key for c in _checks(None)}
    assert "target_reachable" not in keys
    keys = {c.key for c in _checks((_levels(), _levels(103.0)))}
    assert "target_reachable" in keys


def test_a_wall_makes_the_scenario_fail_its_requirements():
    """This is what actually stops the alert: engine.py posts only when
    every requirement passes."""
    checks = _checks((_levels(), _levels(100.8)))
    assert not all(c.passed for c in checks)
    assert [c.key for c in checks if not c.passed] == ["target_reachable"]
