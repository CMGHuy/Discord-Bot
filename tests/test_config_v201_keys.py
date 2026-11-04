"""v201: the admin market refresher's flags and knobs (index "Config fields")."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default, min, max). Dict order is the FIELDS order.
V201_FIELDS = {
    "ADMIN_REFRESHER": ("select", "on", None, None),
    "ADMIN_REFRESH_REGULAR_S": ("number", "30", 10, 300),
    "ADMIN_REFRESH_EXTENDED_S": ("number", "300", 60, 3600),
    "ADMIN_REFRESH_CLOSED_S": ("number", "1800", 300, 7200),
    "ADMIN_REFRESH_YF_FALLBACK_CAP": ("number", "25", 0, 500),
    "ADMIN_REFRESH_MARK_TIMEOUT_S": ("number", "120", 30, 900),
    "ADMIN_REFRESH_FX_UNKNOWN_RETRY_S": ("number", "21600", 600, 604800),
    "ADMIN_STALE_PRICE_REGULAR_S": ("number", "120", 30, 1800),
    "ADMIN_STALE_PRICE_EXTENDED_S": ("number", "900", 60, 7200),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_field_is_a_hot_reloadable_data_sources_knob(attr):
    field = _field(attr)
    kind, default, low, high = V201_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", kind, default)
    assert (field.min, field.max) == (low, high)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v201" in field.help


def test_fields_sit_together_after_the_tape_proxies():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("TAPE_PROXY_SYMBOLS") + 1
    assert attrs[start:start + len(V201_FIELDS)] == list(V201_FIELDS)


def test_kill_switch_is_on_off_and_a_typo_falls_back_to_off():
    field = _field("ADMIN_REFRESHER")
    assert [value for value, _label in field.options] == ["on", "off"]
    assert config._MODE_VALUES["ADMIN_REFRESHER"] == ("on", "off")
    assert config._cast(field, "ON") == "on"
    assert config._cast(field, "maybe") == "off"


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    kind, default, _low, _high = V201_FIELDS[attr]
    expected = int(default) if kind == "number" else default
    assert config._cast(field, field.default) == expected


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V201_FIELDS[attr][1]}\n" in text
