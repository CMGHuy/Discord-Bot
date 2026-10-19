"""v176: RUNNER_GIVEBACK_ENABLED / RUNNER_GIVEBACK_PCT in the schema and .env.example."""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from swingbot import config

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_enabled_flag_is_a_default_on_checkbox_outside_the_search():
    f = _field("RUNNER_GIVEBACK_ENABLED")
    assert (f.attr, f.type, f.default, f.section) == (
        "RUNNER_GIVEBACK_ENABLED", "checkbox", "true", "Exit quality")
    assert f.search_class == "excluded"
    assert f.hot_reloadable is True
    assert config._cast(f, f.default) is True


def test_pct_is_a_float_with_the_clamp_range():
    f = _field("RUNNER_GIVEBACK_PCT")
    assert (f.attr, f.type, f.default, f.section) == (
        "RUNNER_GIVEBACK_PCT", "float", "5.0", "Exit quality")
    assert (f.min, f.max) == (0.5, 49.0)
    assert f.search_class == "excluded"
    assert f.hot_reloadable is True
    assert config._cast(f, f.default) == 5.0


def test_module_globals_carry_the_types():
    assert isinstance(config.RUNNER_GIVEBACK_ENABLED, bool)
    assert isinstance(config.RUNNER_GIVEBACK_PCT, float)


def test_env_example_lists_both_keys_at_their_defaults():
    values = dotenv_values(ENV_EXAMPLE)
    assert values["RUNNER_GIVEBACK_ENABLED"] == "true"
    assert values["RUNNER_GIVEBACK_PCT"] == "5.0"


def test_absent_keys_take_the_defaults(monkeypatch, restore_config):
    monkeypatch.delenv("RUNNER_GIVEBACK_ENABLED", raising=False)
    monkeypatch.delenv("RUNNER_GIVEBACK_PCT", raising=False)
    config._apply_env()
    assert config.RUNNER_GIVEBACK_ENABLED is True
    assert config.RUNNER_GIVEBACK_PCT == 5.0


def test_a_reload_picks_up_a_changed_percent(monkeypatch, restore_config):
    # _apply_env() is what config.reload() (SIGHUP) runs after re-reading .env.
    from swingbot.core.planning.exit_sim import giveback_level
    monkeypatch.setenv("RUNNER_GIVEBACK_PCT", "7.5")
    monkeypatch.setenv("RUNNER_GIVEBACK_ENABLED", "true")
    config._apply_env()
    assert config.RUNNER_GIVEBACK_PCT == 7.5
    assert giveback_level(100.0, "bullish") == pytest.approx(92.5)


def test_a_reload_can_turn_the_flag_off(monkeypatch, restore_config):
    from swingbot.core.planning.exit_sim import giveback_level
    monkeypatch.setenv("RUNNER_GIVEBACK_ENABLED", "false")
    config._apply_env()
    assert config.RUNNER_GIVEBACK_ENABLED is False
    assert giveback_level(100.0, "bullish") is None
