"""v139 confluence_stop_geometry: arm S (structural stop up to c - 0.25,
target re-selected, rollback to the clamp) and arm D (no plan beyond c), both
directions. Spec: docs/superpowers/specs/2026-10-08-v139-confluence-stop-geometry-design.md"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.builders import clamped_distance, confluence_stop_geometry
from swingbot.scan_params import ScanParams

BOTH = pytest.mark.parametrize("is_bull", [True, False])


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(s=0.0, d=0.0):
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5,
                               confluence_structural_stop_pct=s, confluence_stop_drop_pct=d)


def _m(is_bull, price):
    """Mirror a bullish price around the 100.0 entry for the bearish case."""
    return price if is_bull else 200.0 - price


def _geo(is_bull, level, candidate, **knobs):
    return confluence_stop_geometry(100.0, _m(is_bull, level), is_bull,
                                    [_m(is_bull, candidate)], _params(**knobs))


@BOTH
def test_unclamped_plan_is_unchanged_by_both_arms(is_bull):
    assert _geo(is_bull, 98.5, 104.0, s=5.0, d=3.0) == (_m(is_bull, 98.5), None)


@BOTH
def test_arm_s_applies_at_exactly_c_minus_headroom(is_bull):
    # d = 2.75 = 3.0 - 0.25; 105 is 1.82R at the 2.75 structural risk.
    assert _geo(is_bull, 97.25, 105.0, s=3.0) == (_m(is_bull, 97.25), 3.0)


@BOTH
def test_arm_s_just_past_the_headroom_keeps_the_clamp(is_bull):
    stop, ceiling = _geo(is_bull, 97.24, 105.0, s=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_s_without_an_rr_band_target_rolls_back_to_the_clamp(is_bull):
    # 103 is 1.09R at the 2.75 structural risk, under the 1.5R floor.
    stop, ceiling = _geo(is_bull, 97.25, 103.0, s=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_d_keeps_a_plan_exactly_at_c(is_bull):
    stop, ceiling = _geo(is_bull, 97.0, 104.0, d=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_d_drops_just_past_c(is_bull):
    assert _geo(is_bull, 96.99, 104.0, d=3.0) is None


@BOTH
def test_both_set_arm_s_first_then_arm_d(is_bull):
    # d = 3.5 <= 4.0 - 0.25: arm S keeps it, although arm D's 3.0 would drop it.
    assert _geo(is_bull, 96.5, 108.0, s=4.0, d=3.0) == (_m(is_bull, 96.5), 4.0)
    # d = 4.0 is past arm S's 3.75: arm D drops it.
    assert _geo(is_bull, 96.0, 108.0, s=4.0, d=3.0) is None


@BOTH
def test_arm_s_rollback_past_arm_d_is_dropped(is_bull):
    # d = 3.5: arm S applies by geometry but 103 has no RR-band slot -> rollback;
    # the rolled-back plan is then beyond arm D's 3.0 -> dropped.
    assert _geo(is_bull, 96.5, 103.0, s=4.0, d=3.0) is None


@BOTH
def test_both_off_is_exactly_todays_clamp(is_bull):
    for level in (98.5, 98.0, 97.0, 90.0):
        lv = _m(is_bull, level)
        expected = (builders._clamp_stop_to_hard_cap(100.0, lv, is_bull), None)
        assert confluence_stop_geometry(100.0, lv, is_bull, [_m(is_bull, 120.0)],
                                        _params()) == expected


def test_clamped_distance_is_the_set_the_clamp_moves():
    assert clamped_distance(100.0, 98.0, True) is None          # exactly the cap
    assert clamped_distance(100.0, 97.0, True) == pytest.approx(3.0)
    assert clamped_distance(100.0, 103.0, False) == pytest.approx(3.0)
    assert clamped_distance(100.0, 103.0, True) is None          # profit side
    assert clamped_distance(100.0, None, True) is None
    assert clamped_distance(0.0, 97.0, True) is None
    assert clamped_distance(None, 97.0, True) is None


def test_clamped_distance_ignores_the_clamp_flag(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    assert clamped_distance(100.0, 97.0, True) == pytest.approx(3.0)


def test_invalid_inputs_pass_through_like_the_clamp():
    assert confluence_stop_geometry(100.0, None, True, [], _params(s=4.0, d=3.0)) == (None, None)
    assert confluence_stop_geometry(0.0, 5.0, True, [], _params(s=4.0, d=3.0)) == (5.0, None)
