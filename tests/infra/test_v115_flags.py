"""v115: the two issuance flags and the stop floor (2.0 at v115, 1.75 since 2026-10-01), in the schema and in .env.example."""
from pathlib import Path

from dotenv import dotenv_values

from swingbot import config

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


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


def test_stop_floor_code_default_is_1_75():
    # 2.0 at v115; the partner moved it to 1.75 on 2026-10-01 and made that the code default.
    assert _field("MIN_STOP_DISTANCE_PCT").default == "1.75"


def test_env_example_ships_the_v115_values():
    values = dotenv_values(ENV_EXAMPLE)
    # .env.example and the schema default both say 1.75 since 2026-10-01.
    assert values.get("MIN_STOP_DISTANCE_PCT") == "1.75"
    assert values.get("CLAMP_STOP_TO_HARD_CAP") == "true"
    assert values.get("LIQUIDITY_EXEMPT_NON_EQUITY") == "false"
    assert values.get("SIGNAL_CONFIRMATION_SCANS") == "1"   # spec: stays 1
