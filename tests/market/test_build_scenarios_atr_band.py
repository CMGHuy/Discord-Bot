"""V191-9: with an active ATR band, build_scenarios drops the min/max stop
distance gates and checks its own-target R:R against the band stop."""
import pytest

from swingbot.core.market import levels
from swingbot.core.market.atr_band import AtrBand

LIVE = dict(min_reward_pct=3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=3.0,
            min_risk_reward=1.5)


def _bull(support, target, band=None, **gates):
    sup = [levels.Level(support, ["Rolling S/R"])]
    res = [levels.Level(target, ["Rolling S/R"])]
    got = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, band=band, **{**LIVE, **gates})
    return [s for s in got if s.direction == "bullish"]


def test_a_one_percent_stop_is_refused_without_the_band_and_admitted_with_it():
    assert _bull(99.0, 108.0) == []
    (sc,) = _bull(99.0, 108.0, band=AtrBand(1.0, 4.0))
    assert sc.stop_loss == 99.0 and sc.stop_distance_pct == pytest.approx(1.0)  # the raw level
    assert sc.atr14_pct == pytest.approx(4.0)
    assert sc.constraints["min_stop_distance"] and sc.constraints["max_stop_distance"]
    assert sc.meets_all_own_constraints


def test_the_horizon_max_stop_is_bypassed_by_the_band():
    assert _bull(95.0, 110.0) == []                                  # 5% > max 3%
    assert len(_bull(95.0, 110.0, band=AtrBand(1.0, 4.0))) == 1      # untouched in [4, 8]


def test_own_target_reward_risk_is_measured_against_the_band_stop():
    # 5R against the raw 99 level, 1.25R against the 96 band stop -> refused
    assert _bull(99.0, 105.0, band=AtrBand(1.0, 4.0)) == []


def test_a_band_without_atr_is_todays_admission():
    assert _bull(99.0, 108.0, band=AtrBand(1.0, None)) == []
    (sc,) = _bull(98.0, 108.0, band=AtrBand(1.0, None))             # d 2.0 passes today
    assert sc.atr14_pct is None


def test_bearish_mirror():
    sup = [levels.Level(92.0, ["Rolling S/R"])]
    res = [levels.Level(101.0, ["Rolling S/R"])]
    off = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, **LIVE)
    on = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, band=AtrBand(1.0, 4.0), **LIVE)
    assert [s.direction for s in off] == []
    bear = [s for s in on if s.direction == "bearish"]
    assert bear[0].stop_loss == 101.0 and bear[0].atr14_pct == pytest.approx(4.0)


def test_no_band_keeps_the_constraint_keys_and_order():
    (sc,) = _bull(98.0, 108.0)
    assert list(sc.constraints) == ["min_reward", "min_stop_distance", "max_stop_distance",
                                    "min_risk_reward", "not_dead_cat_bounce"]
    assert sc.atr14_pct is None


def test_an_inactive_floor_keeps_the_legacy_stop_gates():
    assert _bull(99.0, 108.0, band=AtrBand(0.0, 4.0)) == []
