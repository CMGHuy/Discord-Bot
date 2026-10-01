"""v115: the two issuance flags and the 2.0 stop floor, in the schema and in .env.example."""
from pathlib import Path

from dotenv import dotenv_values

from swingbot import config

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


def test_clamp_flag_is_a_default_on_checkbox_outside_the_search():
    f = _field("CLAMP_STOP_TO_HARD_CAP")
    assert (f.attr, f.type, f.default, f.section) == (
        "CLAMP_STOP_TO_HARD_CAP", "checkbox", "true", "Trade Filters & Risk")
    assert f.search_class == "excluded"
    assert config._cast(f, f.default) is True


def test_liquidity_flag_is_a_default_off_checkbox_outside_the_search():
    f = _field("LIQUIDITY_EXEMPT_NON_EQUITY")
    assert (f.attr, f.type, f.default, f.section) == (
        "LIQUIDITY_EXEMPT_NON_EQUITY", "checkbox", "false", "Universe & Scanning")
    assert f.search_class == "excluded"
    assert config._cast(f, f.default) is False


def test_stop_floor_code_default_is_two():
    assert _field("MIN_STOP_DISTANCE_PCT").default == "2.0"


def test_env_example_ships_the_v115_values():
    values = dotenv_values(ENV_EXAMPLE)
    # .env.example mirrors production (1.75 since 2026-10-01); the schema default stays 2.0.
    assert values.get("MIN_STOP_DISTANCE_PCT") == "1.75"
    assert values.get("CLAMP_STOP_TO_HARD_CAP") == "true"
    assert values.get("LIQUIDITY_EXEMPT_NON_EQUITY") == "false"
    assert values.get("SIGNAL_CONFIRMATION_SCANS") == "1"   # spec: stays 1
