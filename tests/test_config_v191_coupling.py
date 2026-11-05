"""v191 coupling: a live CONFLUENCE_ATR_STOP_FLOOR > 0 needs LONG_GAP_SIZING
and SHORT_GAP_SIZING both on. Config load and every reload treat a broken
combination as floor 0 and log an ERROR, so a hand-edited .env cannot
bypass the admin validator."""
import logging

import pytest

from swingbot import config

FLOOR = "CONFLUENCE_ATR_STOP_FLOOR"


@pytest.fixture(autouse=True)
def _restore_config():
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS if hasattr(config, f.attr)}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def _set(monkeypatch, floor, long_on, short_on):
    monkeypatch.setattr(config, FLOOR, floor)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", long_on)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", short_on)


@pytest.mark.parametrize("long_on,short_on", [(False, True), (True, False), (False, False)])
def test_a_floor_without_both_gap_flags_is_zeroed_and_logged(monkeypatch, caplog, long_on, short_on):
    _set(monkeypatch, 1.0, long_on, short_on)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is True
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "CONFLUENCE_ATR_STOP_FLOOR=1.0" in errors[0].getMessage()
    assert "treated as 0" in errors[0].getMessage()


def test_a_floor_with_both_flags_on_is_honoured(monkeypatch, caplog):
    _set(monkeypatch, 1.5, True, True)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is False
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 1.5
    assert not caplog.records


def test_floor_zero_never_logs(monkeypatch, caplog):
    _set(monkeypatch, 0.0, False, False)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is False
    assert not caplog.records


def test_apply_env_enforces_the_coupling(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "false")
    monkeypatch.setenv("SHORT_GAP_SIZING", "true")
    monkeypatch.setattr(config, FLOOR, 0.0)
    changed = config._apply_env()
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0
    assert FLOOR not in changed                       # 0 -> 0: nothing changed for reload() to log


def test_apply_env_reports_a_live_floor_switched_off(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "false")
    monkeypatch.setattr(config, FLOOR, 1.5)            # was live before this reload
    assert config._apply_env()[FLOOR] == (1.5, 0.0)


def test_apply_env_keeps_a_coupled_floor(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "true")
    monkeypatch.setenv("SHORT_GAP_SIZING", "true")
    config._apply_env()
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 1.0


def test_reload_goes_through_apply_env():
    import inspect
    assert "_apply_env()" in inspect.getsource(config.reload)


def test_malformed_persisted_floor_returns_a_validation_error(monkeypatch):
    # Import the app first: its registration owns the API module import order.
    from swingbot.admin import app  # noqa: F401
    from swingbot.admin import helpers
    from swingbot.admin.api_v1 import system

    monkeypatch.setattr(helpers, "_read_env_values", lambda: {FLOOR: "broken-floor"})
    problem = system._validate({"LOG_LEVEL": "DEBUG"})
    assert problem == ("invalid", "Confluence ATR stop floor must be a number, got 'broken-floor'")
