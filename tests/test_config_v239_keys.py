"""v239: BEAR_REGIME_MODE (spec § Config) and the regime pass's mode reader."""
import pathlib

import pytest

from swingbot import config
from swingbot.core.scanning import regime_scan

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "BEAR_REGIME_MODE"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_field_is_a_hot_reloadable_excluded_select_in_its_own_section():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (
        ATTR, "Bear Regime", "select", "shadow")
    assert field.hot_reloadable is True
    assert field.sensitive is False
    assert field.search_class == "excluded"
    assert ATTR not in config.searchable_attrs()
    assert "v239" in field.help
    assert "identical to shadow" in field.help
    assert "falls back to off" in field.help


def test_field_sits_after_market_shock_and_before_database():
    attrs = [f.attr for f in config.FIELDS]
    at = attrs.index(ATTR)
    assert attrs[at - 1] == "SHOCK_READINGS_KEEP_DAYS"
    assert attrs[at + 1] == "DATABASE_URL"


def test_mode_is_off_shadow_live_and_a_typo_falls_back_to_off():
    field = _field()
    assert [value for value, _label in field.options] == ["off", "shadow", "live"]
    assert config._MODE_VALUES[ATTR] == ("off", "shadow", "live")
    assert ATTR not in config._MODE_FALLBACK
    assert config._cast(field, "SHADOW") == "shadow"
    assert config._cast(field, "live") == "live"
    assert config._cast(field, "off") == "off"
    assert config._cast(field, "on") == "off"
    assert config._cast(field, "") == "off"


def test_module_attr_is_shadow_on_a_clean_env(monkeypatch):
    monkeypatch.delenv(ATTR, raising=False)
    try:
        config._apply_env()
        assert config.BEAR_REGIME_MODE == "shadow"
    finally:
        monkeypatch.undo()
        config._apply_env()


def test_env_example_lists_the_key_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=shadow\n" in text


def test_deploy_doc_names_the_flag_the_table_and_the_rollback():
    text = (REPO / "docs/deploy/DEPLOY_HETZNER.md").read_text(encoding="utf-8")
    assert "### v239: bear-regime engine (`market_regime_days`)" in text
    assert f"python3 scripts/ops/env_set.py {ATTR} off" in text
    assert "%bear_regime%" in text


def test_modes():
    assert regime_scan.MODES == ("off", "shadow", "live")


@pytest.mark.parametrize("value, mode", [
    ("off", "off"), ("shadow", "shadow"), ("live", "live"), (" SHADOW ", "shadow"),
    ("bogus", "off"), ("", "off"), (None, "off"),
])
def test_regime_mode_reads_config_and_falls_back_to_off(monkeypatch, value, mode):
    monkeypatch.setattr(config, ATTR, value)
    assert regime_scan.regime_mode() == mode
