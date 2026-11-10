"""v212: the confluence limit-entry knob -- schema, ScanParams, reachability,
.env.example. Ships inert at 0 (spec § The rule)."""
import pathlib

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

REPO = pathlib.Path(__file__).resolve().parents[1]
KNOB = "CONFLUENCE_LIMIT_ENTRY_F"


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_knob_is_an_inert_searchable_float():
    f = _field(KNOB)
    assert (f.key, f.section, f.type, f.default) == (KNOB, "Trade Filters & Risk", "float", "0")
    assert (f.min, f.max, f.step) == (0, 0.9, 0.01)
    assert f.search_class == "searchable" and KNOB in config.searchable_attrs()
    assert config._cast(f, f.default) == 0.0
    assert config.CONFLUENCE_LIMIT_ENTRY_F == 0.0


def test_knob_follows_the_v191_fields():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs[attrs.index("CONFLUENCE_ATR_TARGET_MODE") + 1] == KNOB


def test_help_states_the_rule_and_the_default():
    text = _field(KNOB).help
    for phrase in ("v212", "0 = off", "0.25%", "TP1", "3 sessions", "2%", "Keep 0"):
        assert phrase in text, phrase


def test_scan_params_default_is_off():
    assert ScanParams.from_config().confluence_limit_entry_f == 0.0


@pytest.mark.parametrize("value", [1 / 3, 0.5, 2 / 3])
def test_scan_params_carries_the_knob(value, monkeypatch):
    monkeypatch.setattr(config, KNOB, value)
    assert ScanParams.from_config().confluence_limit_entry_f == value


def test_reachability_row_is_confluence_only_and_names_its_own_replay():
    assert reach.classify(KNOB) == reach.REACHABLE
    row = reach.REGISTRY[KNOB]
    assert row.observed_by == reach.C
    assert "confluence_limit_replay.py" in row.reason
    assert "measure_arms.py" in row.reason           # names what does NOT measure it
    assert row.fixture_observable is False


def test_measure_arms_parses_the_knob():
    assert parse_knob(f"{KNOB}=0.5") == (KNOB, 0.5)


def test_env_example_ships_it_at_zero():
    assert dotenv_values(REPO / ".env.example").get(KNOB) == "0"
