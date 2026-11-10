"""v209: the "Market Shock" config section (spec § Starting thresholds)."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default). Key == attr for every v209 field. Dict order is the FIELDS order.
V209_FIELDS = {
    "MARKET_SHOCK_MODE": ("select", "shadow"),
    "SHOCK_ATR_K": ("float", "1.0"),
    "SHOCK_BREADTH_ENTER": ("float", "0.40"),
    "SHOCK_DEPTH_FRAC": ("float", "0.50"),
    "SHOCK_BREADTH_MAJORITY": ("float", "0.50"),
    "SHOCK_BREADTH_FAST": ("float", "0.25"),
    "SHOCK_SPEED_ENTER": ("float", "0.10"),
    "SHOCK_VIX_SPIKE_PCT": ("float", "15.0"),
    "SHOCK_VIX_RELIEF": ("float", "0.05"),
    "SHOCK_BREADTH_REENTER": ("float", "0.30"),
    "SHOCK_BREADTH_EXIT": ("float", "0.20"),
    "RECOVERY_VIX_OFF_HIGH_PCT": ("float", "5.0"),
    "RECOVERY_SPY_RETRACE": ("float", "0.5"),
    "SHOCK_MIN_DWELL_MIN": ("number", "45"),
    "RECOVERY_MIN_DWELL_MIN": ("number", "30"),
    "SHOCK_MIN_NAMES": ("number", "20"),
    "SHOCK_VIX_MAX_AGE_S": ("number", "600"),
    "SHOCK_OPEN_SETTLE_MIN": ("number", "15"),
    "SHOCK_QUOTE_MAX_AGE_S": ("number", "300"),
    "SHOCK_READINGS_KEEP_DAYS": ("number", "180"),
}

#: The value each default casts to (spec § Starting thresholds, verbatim).
CAST_DEFAULTS = {
    "MARKET_SHOCK_MODE": "shadow",
    "SHOCK_ATR_K": 1.0, "SHOCK_BREADTH_ENTER": 0.40,
    "SHOCK_DEPTH_FRAC": 0.50, "SHOCK_BREADTH_MAJORITY": 0.50,
    "SHOCK_BREADTH_FAST": 0.25, "SHOCK_SPEED_ENTER": 0.10, "SHOCK_VIX_SPIKE_PCT": 15.0,
    "SHOCK_VIX_RELIEF": 0.05, "SHOCK_BREADTH_REENTER": 0.30, "SHOCK_BREADTH_EXIT": 0.20,
    "RECOVERY_VIX_OFF_HIGH_PCT": 5.0, "RECOVERY_SPY_RETRACE": 0.5,
    "SHOCK_MIN_DWELL_MIN": 45, "RECOVERY_MIN_DWELL_MIN": 30, "SHOCK_MIN_NAMES": 20,
    "SHOCK_VIX_MAX_AGE_S": 600, "SHOCK_OPEN_SETTLE_MIN": 15, "SHOCK_QUOTE_MAX_AGE_S": 300,
    "SHOCK_READINGS_KEEP_DAYS": 180,
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_twenty_fields_one_mode_plus_nineteen_thresholds():
    # A1: SHOCK_SECTORS_FRAC removed, SHOCK_DEPTH_FRAC and SHOCK_BREADTH_MAJORITY added
    assert len(V209_FIELDS) == 20
    assert set(V209_FIELDS) == set(CAST_DEFAULTS)


def test_sectors_frac_is_gone_from_the_schema_and_the_example():
    assert not any(f.attr == "SHOCK_SECTORS_FRAC" for f in config.FIELDS)
    assert all("SHOCK_SECTORS_FRAC" not in (f.help or "") for f in config.FIELDS)
    assert "SHOCK_SECTORS_FRAC" not in (REPO / ".env.example").read_text(encoding="utf-8")


def test_a_stale_sectors_frac_env_key_is_ignored(monkeypatch):
    monkeypatch.setenv("SHOCK_SECTORS_FRAC", "0.6")
    try:
        config._apply_env()
        assert config.SHOCK_DEPTH_FRAC == 0.50 and config.SHOCK_BREADTH_MAJORITY == 0.50
    finally:
        monkeypatch.undo()
        config._apply_env()


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_field_is_a_hot_reloadable_excluded_market_shock_knob(attr):
    field = _field(attr)
    kind, default = V209_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Market Shock", kind, default)
    assert field.hot_reloadable is True
    assert field.sensitive is False
    assert field.search_class == "excluded"
    assert attr not in config.searchable_attrs()
    assert "v209" in field.help


def test_fields_sit_together_between_chart_patterns_and_database():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("DCB_VOLUME_RATIO") + 1
    assert attrs[start:start + len(V209_FIELDS)] == list(V209_FIELDS)
    assert attrs[start + len(V209_FIELDS)] == "DATABASE_URL"


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    value = config._cast(field, field.default)
    assert value == CAST_DEFAULTS[attr]
    assert type(value) is type(CAST_DEFAULTS[attr])


def test_mode_is_off_shadow_live_and_a_typo_falls_back_to_off():
    field = _field("MARKET_SHOCK_MODE")
    assert [value for value, _label in field.options] == ["off", "shadow", "live"]
    assert config._MODE_VALUES["MARKET_SHOCK_MODE"] == ("off", "shadow", "live")
    assert "MARKET_SHOCK_MODE" not in config._MODE_FALLBACK
    assert config._cast(field, "SHADOW") == "shadow"
    assert config._cast(field, "live") == "live"
    assert config._cast(field, "off") == "off"
    assert config._cast(field, "on") == "off"
    assert config._cast(field, "") == "off"


def test_numeric_fields_carry_bounds_around_their_default_and_a_step():
    for attr, (kind, _default) in V209_FIELDS.items():
        if kind not in ("float", "number"):
            continue
        field = _field(attr)
        assert field.min is not None and field.max is not None, attr
        assert field.step is not None, attr
        assert field.min <= CAST_DEFAULTS[attr] <= field.max, attr


def test_module_attrs_hold_the_cast_defaults_on_a_clean_env(monkeypatch):
    for attr in V209_FIELDS:
        monkeypatch.delenv(attr, raising=False)
    try:
        config._apply_env()
        for attr, expected in CAST_DEFAULTS.items():
            assert getattr(config, attr) == expected, attr
    finally:
        monkeypatch.undo()
        config._apply_env()


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V209_FIELDS[attr][1]}\n" in text
