"""v191: the ATR-band knobs and the long gap-sizing switch -- schema,
ScanParams, reachability, .env.example. Every one ships inert."""
import pathlib

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

REPO = pathlib.Path(__file__).resolve().parents[1]
FLOOR, MODE, LONG = "CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE", "LONG_GAP_SIZING"


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_floor_is_an_inert_searchable_float_capped_below_the_ceiling():
    f = _field(FLOOR)
    assert (f.key, f.section, f.type, f.default) == (FLOOR, "Trade Filters & Risk", "float", "0")
    assert (f.min, f.max, f.step) == (0, 1.5, 0.25)
    assert f.max < 2.0                                  # k < BAND_CEILING_ATR, so lo < hi always
    assert f.search_class == "searchable" and FLOOR in config.searchable_attrs()
    assert config._cast(f, f.default) == 0.0
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0


def test_target_mode_is_a_searchable_select_defaulting_to_rechoose():
    f = _field(MODE)
    assert (f.key, f.section, f.type, f.default) == (MODE, "Trade Filters & Risk", "select", "rechoose")
    assert [value for value, _label in f.options] == ["rechoose", "keep"]
    assert f.search_class == "searchable" and MODE in config.searchable_attrs()
    assert config._cast(f, "KEEP") == "keep"
    assert config._cast(f, "typo") == "rechoose"        # an unknown value lands on today's arm
    assert config.CONFLUENCE_ATR_TARGET_MODE == "rechoose"


def test_the_band_fields_follow_the_v139_knobs():
    attrs = [f.attr for f in config.FIELDS]
    base = attrs.index("CONFLUENCE_STOP_DROP_PCT")
    assert attrs[base + 1:base + 3] == [FLOOR, MODE]


def test_floor_help_names_the_coupling_and_the_default():
    text = _field(FLOOR).help
    assert "LONG_GAP_SIZING" in text and "SHORT_GAP_SIZING" in text
    assert "Keep 0" in text


def test_short_gap_sizing_help_no_longer_claims_longs_are_never_affected():
    assert "Longs are never affected" not in _field("SHORT_GAP_SIZING").help
    assert "LONG_GAP_SIZING" in _field("SHORT_GAP_SIZING").help


def test_scan_params_defaults_are_off():
    params = ScanParams.from_config()
    assert params.confluence_atr_stop_floor == 0.0
    assert params.confluence_atr_target_mode == "rechoose"


@pytest.mark.parametrize("attr,value", [(FLOOR, 1.0), (MODE, "keep")])
def test_scan_params_carries_the_knob(attr, value, monkeypatch):
    monkeypatch.setattr(config, attr, value)
    assert getattr(ScanParams.from_config(), attr.lower()) == value


@pytest.mark.parametrize("attr", [FLOOR, MODE])
def test_reachability_row_is_confluence_only(attr):
    assert reach.classify(attr) == reach.REACHABLE
    assert reach.REGISTRY[attr].observed_by == reach.C
    assert "measure_arms.py" in reach.REGISTRY[attr].reason        # names what does NOT measure it


def test_measure_arms_parses_the_knobs():
    assert parse_knob(f"{FLOOR}=1.0") == (FLOOR, 1.0)
    assert parse_knob(f"{MODE}=keep") == (MODE, "keep")


def test_long_gap_sizing_is_not_searchable():
    assert LONG not in config.searchable_attrs()


def test_env_example_ships_all_three_inert():
    env = dotenv_values(REPO / ".env.example")
    assert (env.get(FLOOR), env.get(MODE), env.get(LONG)) == ("0", "rechoose", "false")
