"""V180-6: TURTLE_SOUP_RESEARCH_MODE is a research-only select (off | structural), default off,
searchable, reachable through the strategy engine only, and threaded through ScanParams."""
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability
from swingbot.core.backtesting.arms.knobs import apply_knobs, parse_knob
from swingbot.scan_params import ScanParams

KNOB = "TURTLE_SOUP_RESEARCH_MODE"
ROOT = Path(__file__).resolve().parent.parent.parent


def test_knob_is_a_research_select_defaulting_off():
    field = next(f for f in config.FIELDS if f.attr == KNOB)
    assert field.default == "off"
    assert [value for value, _ in field.options] == ["off", "structural"]
    assert config.TURTLE_SOUP_RESEARCH_MODE == "off"


def test_parse_knob_accepts_only_the_two_modes():
    assert parse_knob(f"{KNOB}=structural") == (KNOB, "structural")
    with pytest.raises(ValueError):
        parse_knob(f"{KNOB}=screened")          # arm A is closed without a run


def test_knob_is_reachable_through_the_strategy_engine_only():
    reach = reachability.REGISTRY[KNOB]
    assert reach.cls == reachability.REACHABLE
    assert reach.observed_by == frozenset({"strategy"})
    assert reach.fixture_observable is False
    assert "v180" in reach.reason


def test_scan_params_carries_the_knob():
    assert ScanParams.from_config().turtle_soup_research_mode == "off"
    with apply_knobs({KNOB: "structural"}):
        assert ScanParams.from_config().turtle_soup_research_mode == "structural"
    assert config.TURTLE_SOUP_RESEARCH_MODE == "off"           # restored


def test_env_example_documents_it_off():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"\n{KNOB}=off\n" in text
