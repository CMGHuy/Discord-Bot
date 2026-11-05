"""V191-8: build_confluence_plan's band path. Floor on and an ATR on the
scenario -> the stop sits in the ATR band, the ceiling stored is the band
distance + 0.25, stop_moved_by says why; arm R re-chooses TP1 against the band
stop, arm K keeps today's TP1 and drops below MIN_RISK_REWARD_RATIO."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(k=1.0, mode="rechoose", **kw):
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0, confluence_atr_stop_floor=k,
                               confluence_atr_target_mode=mode, **kw)


def _scenario(direction, stop_loss, take_profit, atr14_pct, entry=100.0):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"], atr14_pct=atr14_pct)


def _build(scenario, params):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=None, params=params)


def test_today_band_floor_is_the_v115_clamp_target():
    assert builders.TODAY_BAND_FLOOR_PCT == pytest.approx(1.75)


# --- floor off / no ATR: today's plan, nothing new on it ---------------------------

def test_floor_off_builds_todays_clamped_plan_even_with_an_atr():
    plan = _build(_scenario("bullish", 96.5, 108.0, 4.0), _params(k=0.0))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.stop_ceiling_pct is None and plan.stop_moved_by is None
    assert "stop_moved_by" not in plan_to_dict(plan)


def test_floor_on_without_an_atr_builds_todays_plan():
    plan = _build(_scenario("bullish", 96.5, 108.0, None), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.stop_ceiling_pct is None and plan.stop_moved_by is None


# --- the band stop (a = 4.0, k = 1.0 -> lo 4%, hi 8%) ------------------------------

def test_confluence_atr_band_stop_returns_stop_ceiling_and_reason():
    got = builders.confluence_atr_band_stop(100.0, 99.0, True, 4.0, _params(k=1.0))
    assert got == (pytest.approx(96.0), pytest.approx(4.25), "floor")
    assert builders.confluence_atr_band_stop(100.0, 99.0, True, 4.0, _params(k=0.0)) is None
    assert builders.confluence_atr_band_stop(100.0, 99.0, True, None, _params(k=1.0)) is None


def test_arm_r_floor_moved_plan():
    plan = _build(_scenario("bullish", 99.0, 108.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(96.0)
    assert plan.stop_ceiling_pct == pytest.approx(4.25)
    assert plan.stop_moved_by == "floor"
    assert plan.tp1 == pytest.approx(108.0)              # 2.0R against the 4.0 band risk
    assert plan.acceptance_level == 99.0                 # v129 still leans on the level
    assert plan_to_dict(plan)["stop_moved_by"] == "floor"


def test_arm_r_floor_moved_plan_bearish_mirror():
    plan = _build(_scenario("bearish", 101.0, 92.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(104.0)
    assert plan.stop_ceiling_pct == pytest.approx(4.25)
    assert plan.stop_moved_by == "floor"
    assert plan.tp1 == pytest.approx(92.0)


def test_arm_r_untouched_stop_between_two_percent_and_hi_is_not_clamped():
    plan = _build(_scenario("bullish", 95.0, 109.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == 95.0                        # today would clamp to 98.25
    assert plan.stop_ceiling_pct == pytest.approx(5.25)
    assert plan.stop_moved_by == "untouched"
    assert plan.tp1 == pytest.approx(109.0)              # 1.8R


def test_arm_r_ceiling_moved_plan():
    plan = _build(_scenario("bullish", 90.0, 115.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(92.0)
    assert plan.stop_ceiling_pct == pytest.approx(8.25)
    assert plan.stop_moved_by == "ceiling"
    assert plan.tp1 == pytest.approx(115.0)              # 1.875R


def test_arm_r_no_candidate_clears_the_band_is_no_plan():
    scenario = _scenario("bullish", 99.0, 104.0, 4.0)    # 1.0R against the band stop
    assert _build(scenario, _params(k=1.0)) is None
    assert builders.band_no_plan_reason(scenario, None, _params(k=1.0)) == "band_no_target"


def test_arm_r_reselects_where_arm_k_drops():
    scenario = _scenario("bullish", 96.5, 106.0, 2.5)    # untouched at 3.5%, hi 5%
    plan = _build(scenario, _params(k=1.0, mode="rechoose"))
    assert plan.tp1 == pytest.approx(106.0)              # 1.71R against 3.5
    assert _build(scenario, _params(k=1.0, mode="keep")) is None
    # today's TP1 against the 1.75 risk is the synthetic 2.5R target 104.375 -> 1.25R
    assert builders.band_no_plan_reason(scenario, None, _params(k=1.0, mode="keep")) == "band_rr_drop"


# --- arm K: today's TP1 kept, dropped under the minimum ----------------------------

@pytest.mark.parametrize("entry,level,is_bull,expected", [
    (100.0, 99.0, True, 98.25),       # newly admitted, d 1.0 < 1.75: the 1.75% stop today requires
    (100.0, 98.1, True, 98.1),        # inside today's 1.75-2% band: the level
    (100.0, 96.5, True, 98.25),       # past 2%: the v115 clamp
    (100.0, 101.0, False, 101.75),
    (100.0, 103.5, False, 101.75),
])
def test_arm_k_today_stop(entry, level, is_bull, expected):
    assert builders.arm_k_today_stop(entry, level, is_bull) == pytest.approx(expected)


def test_arm_k_keeps_todays_tp1_against_the_band_stop():
    # a 2.4, k 0.75 -> lo 1.8: stop 98.2. Today's TP1 against 1.75: 104 (2.29R); 2.22R vs 1.8.
    plan = _build(_scenario("bullish", 99.0, 104.0, 2.4), _params(k=0.75, mode="keep"))
    assert plan.stop_loss == pytest.approx(98.2)
    assert plan.tp1 == pytest.approx(104.0)
    assert plan.stop_moved_by == "floor"
    assert plan.stop_ceiling_pct == pytest.approx(2.05)


def test_arm_k_keeps_todays_tp1_bearish_mirror():
    plan = _build(_scenario("bearish", 101.0, 96.0, 2.4), _params(k=0.75, mode="keep"))
    assert plan.stop_loss == pytest.approx(101.8)
    assert plan.tp1 == pytest.approx(96.0)


def test_arm_k_reward_risk_exactly_at_the_minimum_is_kept():
    # a 2.5, k 1.0 -> stop 97.5 (risk 2.5); today's TP1 103.75 is 2.14R vs 1.75, exactly 1.5R vs 2.5
    plan = _build(_scenario("bullish", 99.0, 103.75, 2.5), _params(k=1.0, mode="keep"))
    assert plan is not None and plan.tp1 == pytest.approx(103.75)


def test_arm_k_reward_risk_just_below_the_minimum_is_dropped():
    scenario = _scenario("bullish", 99.0, 103.74, 2.5)   # 1.496R vs 2.5
    params = _params(k=1.0, mode="keep")
    assert _build(scenario, params) is None
    assert builders.band_no_plan_reason(scenario, None, params) == "band_rr_drop"


def test_arm_k_without_a_today_tp1_is_band_no_target():
    scenario = _scenario("bullish", 99.0, 100.5, 2.5)    # 0.29R even against today's 1.75
    params = _params(k=1.0, mode="keep")
    assert _build(scenario, params) is None
    assert builders.band_no_plan_reason(scenario, None, params) == "band_no_target"


# --- the v139 arms and the reason helper ----------------------------------------------

def test_band_path_never_consults_the_v139_arms(monkeypatch):
    monkeypatch.setattr(builders, "_arm_s_stop", lambda *a, **k: pytest.fail("arm S consulted"))
    params = dataclasses.replace(_params(k=1.0), confluence_structural_stop_pct=4.0)
    plan = _build(_scenario("bullish", 95.0, 109.0, 4.0), params)
    assert plan.stop_moved_by == "untouched"


def test_band_no_plan_reason_is_none_when_a_plan_builds_or_the_band_is_off():
    built = _scenario("bullish", 99.0, 108.0, 4.0)
    assert builders.band_no_plan_reason(built, None, _params(k=1.0)) is None
    off = _scenario("bullish", 99.0, 104.0, 4.0)
    assert builders.band_no_plan_reason(off, None, _params(k=0.0)) is None


def test_plan_geometry_today_path_matches_confluence_stop_geometry():
    scenario = _scenario("bullish", 96.5, 108.0, None)
    geo = builders._plan_geometry(scenario, [108.0], _params(k=1.0))
    assert geo == builders.PlanGeometry(pytest.approx(98.25), None, None, pytest.approx(104.375), None)


def test_band_geometry_at_the_creating_bar_is_unchanged_without_future_bars():
    """The builder consumes ATR at the creating bar, never the next bar's range."""
    from swingbot.core.market import atr_band
    from swingbot.core.market.indicators import atr

    full = make_ohlcv([100.0] * 61)
    full["High"], full["Low"] = 102.0, 98.0
    full.iloc[-1, full.columns.get_loc("High")] = 500.0
    completed = full.iloc[:-1]
    full_at_creation = float(atr(full, 14).iloc[-2])
    truncated_at_creation = atr_band.raw_atr14_pct(completed, 100.0)
    params = _params()
    with_future = _build(_scenario("bullish", 99.0, 108.0, full_at_creation), params)
    truncated = _build(_scenario("bullish", 99.0, 108.0, truncated_at_creation), params)
    assert (with_future.stop_loss, with_future.tp1, with_future.stop_moved_by) == (96.0, 108.0, "floor")
    assert (truncated.stop_loss, truncated.tp1, truncated.stop_moved_by) == (96.0, 108.0, "floor")
