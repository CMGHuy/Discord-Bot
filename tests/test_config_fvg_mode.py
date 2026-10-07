"""v128: FVG_LEVELS_MODE / FVG_DISPLACEMENT_ATR_K -- schema, validation, ScanParams, reachability."""
import dataclasses
import math

import pytest

from swingbot import config, scan_params
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.core.market import fvg
from swingbot.scan_params import ScanParams


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_fvg_fields_exist_with_documented_defaults():
    mode, k = _field("FVG_LEVELS_MODE"), _field("FVG_DISPLACEMENT_ATR_K")
    assert (mode.type, mode.default, mode.search_class) == ("select", "all", "searchable")
    assert tuple(value for value, _ in mode.options) == fvg.FVG_MODES
    assert (k.type, k.default, k.search_class) == ("float", "1.5", "searchable")
    assert config._cast(mode, mode.default) == "all"
    assert config._cast(k, k.default) == 1.5


def test_unknown_mode_falls_back_to_all_never_off():
    field = _field("FVG_LEVELS_MODE")
    assert config._cast(field, "sideways") == "all"
    assert config._cast(field, "of") == "all"
    assert config._cast(field, "DISPLACEMENT") == "displacement"
    assert config._cast(field, "off") == "off"


def test_other_mode_fields_still_fall_back_to_off():
    assert config._cast(_field("PLAN_ENGINE_V2"), "banana") == "off"


@pytest.mark.parametrize("raw", ["0", "-1.5", "nan", "inf", "abc"])
def test_non_positive_or_non_numeric_k_is_a_parse_failure(raw):
    with pytest.raises(ValueError):
        config._cast(_field("FVG_DISPLACEMENT_ATR_K"), raw)


def test_env_with_bad_values_falls_back_to_the_defaults(monkeypatch):
    monkeypatch.setenv("FVG_DISPLACEMENT_ATR_K", "0")
    monkeypatch.setenv("FVG_LEVELS_MODE", "sideways")
    try:
        config._apply_env()
        assert config.FVG_DISPLACEMENT_ATR_K == 1.5
        assert config.FVG_LEVELS_MODE == "all"
    finally:
        monkeypatch.undo()
        config._apply_env()


@pytest.mark.parametrize("text", ["FVG_LEVELS_MODE=sideways", "FVG_DISPLACEMENT_ATR_K=0",
                                  "FVG_DISPLACEMENT_ATR_K=-1"])
def test_measure_arms_refuses_an_invalid_arm(text):
    with pytest.raises(ValueError):
        parse_knob(text)


def test_parse_knob_accepts_the_frozen_grid():
    assert parse_knob("FVG_LEVELS_MODE=off") == ("FVG_LEVELS_MODE", "off")
    assert parse_knob("FVG_LEVELS_MODE=displacement") == ("FVG_LEVELS_MODE", "displacement")
    for k in (1.0, 1.5, 2.0):
        assert parse_knob(f"FVG_DISPLACEMENT_ATR_K={k}") == ("FVG_DISPLACEMENT_ATR_K", k)


def test_scan_params_carry_the_two_fields():
    params = ScanParams.from_config()
    assert params.fvg_levels_mode == config.FVG_LEVELS_MODE
    assert params.fvg_displacement_atr_k == config.FVG_DISPLACEMENT_ATR_K
    assert scan_params._FVG_MODES == fvg.FVG_MODES


@pytest.mark.parametrize("changes", [{"fvg_levels_mode": "sideways"}, {"fvg_displacement_atr_k": 0.0},
                                     {"fvg_displacement_atr_k": -1.0},
                                     {"fvg_displacement_atr_k": math.nan}])
def test_scan_params_reject_an_invalid_fvg_value(changes):
    with pytest.raises(ValueError):
        dataclasses.replace(ScanParams.from_config(), **changes)


def test_both_knobs_are_reachable_through_both_engines():
    for attr in ("FVG_LEVELS_MODE", "FVG_DISPLACEMENT_ATR_K"):
        assert reach.classify(attr) == reach.REACHABLE
        assert reach.REGISTRY[attr].observed_by == reach.CS
        assert reach.REGISTRY[attr].fixture_observable is False
