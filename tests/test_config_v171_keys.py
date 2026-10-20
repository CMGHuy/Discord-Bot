"""v171: the shared market-data layer's flags and knobs (spec D2, D6, Rollout)."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default). Key == attr for every v171 field. Dict order is the FIELDS order.
V171_FIELDS = {
    "MARKETDATA_LAYER": ("select", "off"),
    "DAILY_DELTA_FETCH": ("checkbox", "false"),
    "PLAN_REBUILD_ENABLED": ("checkbox", "false"),
    "TAPE_SHARED_ENABLED": ("checkbox", "false"),
    "MARKETDATA_PG_TIMEOUT_MS": ("number", "250"),
    "MARKETDATA_LEASE_SECONDS": ("number", "30"),
    "QUOTE_MAX_AGE_REQUOTE_S": ("number", "5"),
    "QUOTE_MAX_AGE_MONITOR_S": ("number", "15"),
    "QUOTE_MAX_AGE_SCAN_S": ("number", "15"),
    "QUOTE_MAX_AGE_DASHBOARD_S": ("number", "15"),
    "QUOTE_MAX_AGE_ADMIN_S": ("number", "60"),
    "INDEX_QUOTE_MAX_AGE_S": ("number", "60"),
    "EARNINGS_MAX_AGE_S": ("number", "21600"),
    "REBUILD_PRICE_MAX_AGE_S": ("number", "60"),
    "TAPE_STALE_FALLBACK_S": ("number", "180"),
    "ALPACA_BUDGET_PER_MINUTE": ("number", "150"),
    "YF_BUDGET_PER_MINUTE": ("number", "60"),
    "DELTA_WINDOW_MAX_DAYS": ("number", "30"),
    "ALPACA_ANCHOR_DATE": ("text", "2017-01-03"),
    "REANCHOR_WEEKDAY": ("number", "6"),
    "REANCHOR_HOUR": ("number", "4"),
    "TAPE_PROXY_SYMBOLS": ("text", "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV"),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_field_is_a_hot_reloadable_excluded_data_sources_knob(attr):
    field = _field(attr)
    kind, default = V171_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", kind, default)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert attr not in config.searchable_attrs()
    assert "v171" in field.help


def test_fields_sit_together_after_the_spot_quote_age():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("SPOT_QUOTE_MAX_AGE_SECONDS") + 1
    assert attrs[start:start + len(V171_FIELDS)] == list(V171_FIELDS)


def test_layer_mode_is_off_count_on_and_a_typo_falls_back_to_off():
    field = _field("MARKETDATA_LAYER")
    assert [value for value, _label in field.options] == ["off", "count", "on"]
    assert config._MODE_VALUES["MARKETDATA_LAYER"] == ("off", "count", "on")
    assert config._cast(field, "COUNT") == "count"
    assert config._cast(field, "on") == "on"
    assert config._cast(field, "shadow") == "off"


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    kind, default = V171_FIELDS[attr]
    expected = {"number": int, "checkbox": lambda v: v == "true"}.get(kind, str)(default)
    assert config._cast(field, field.default) == expected


@pytest.mark.parametrize("attr", sorted(V171_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V171_FIELDS[attr][1]}\n" in text


def test_module_attributes_exist():
    for attr in V171_FIELDS:
        assert hasattr(config, attr), attr
