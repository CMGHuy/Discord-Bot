"""V192-2: MARKET_ENTRY_NEXT_OPEN and GAP_RECLAIM_ATR ship inert, are searchable,
reach ScanParams and the reachability registry, and GAP_RECLAIM_ATR > 0 is
zeroed with an ERROR log at load and reload while MARKET_ENTRY_NEXT_OPEN is off."""
import logging

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as r
from swingbot.scan_params import ScanParams

KNOBS = ("MARKET_ENTRY_NEXT_OPEN", "GAP_RECLAIM_ATR")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_fields_ship_inert_and_searchable():
    nxt, gap = _field("MARKET_ENTRY_NEXT_OPEN"), _field("GAP_RECLAIM_ATR")
    assert (nxt.key, nxt.type, nxt.default, nxt.section) == (
        "MARKET_ENTRY_NEXT_OPEN", "checkbox", "false", "Trade Filters & Risk")
    assert (gap.key, gap.type, gap.default, gap.section) == (
        "GAP_RECLAIM_ATR", "float", "0", "Trade Filters & Risk")
    assert (gap.min, gap.max, gap.step) == (0, 1.0, 0.05)
    assert config._cast(nxt, nxt.default) is False
    assert config._cast(gap, gap.default) == 0.0
    for attr in KNOBS:
        assert attr in config.searchable_attrs()
        assert _field(attr).hot_reloadable is True


def test_knobs_reach_scan_params(monkeypatch):
    assert ScanParams.from_config().market_entry_next_open is False
    assert ScanParams.from_config().gap_reclaim_atr == 0.0
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.25)
    params = ScanParams.from_config()
    assert params.market_entry_next_open is True and params.gap_reclaim_atr == 0.25


def test_knobs_have_reachability_rows():
    for attr in KNOBS:
        assert r.classify(attr) == r.REACHABLE
        assert r.REGISTRY[attr].observed_by == r.CS
        assert r.REGISTRY[attr].fixture_observable is False
        assert "Stage -1" in r.reason(attr)


def test_gap_without_next_open_is_zeroed_at_load_with_an_error(monkeypatch, caplog, restore_config):
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "false")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    with caplog.at_level(logging.ERROR, logger=config.log.name):
        changed = config._apply_env()
    assert config.GAP_RECLAIM_ATR == 0.0
    assert "GAP_RECLAIM_ATR" not in changed or changed["GAP_RECLAIM_ATR"][1] == 0.0
    assert any("MARKET_ENTRY_NEXT_OPEN" in rec.getMessage() for rec in caplog.records
               if rec.levelno == logging.ERROR)


def test_gap_with_next_open_is_honoured(monkeypatch, caplog, restore_config):
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "true")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    with caplog.at_level(logging.ERROR, logger=config.log.name):
        config._apply_env()
    assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.25
    assert not [rec for rec in caplog.records if rec.levelno == logging.ERROR
                and "GAP_RECLAIM_ATR" in rec.getMessage()]


def test_reload_turning_next_open_off_zeroes_a_live_gap(monkeypatch, restore_config):
    """A SIGHUP that switches MARKET_ENTRY_NEXT_OPEN off while GAP_RECLAIM_ATR stays
    0.25 in .env: the change log reports the zeroing, not a silent stale 0.25."""
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "true")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    config._apply_env()
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "false")
    changed = config._apply_env()
    assert config.GAP_RECLAIM_ATR == 0.0
    assert changed["GAP_RECLAIM_ATR"] == (0.25, 0.0)
    assert changed["MARKET_ENTRY_NEXT_OPEN"] == (True, False)


def test_enforce_is_a_no_op_when_coupled(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    assert config.enforce_gap_reclaim_coupling() is False
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.5)
    assert config.enforce_gap_reclaim_coupling() is False
    assert config.GAP_RECLAIM_ATR == 0.5
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    assert config.enforce_gap_reclaim_coupling() is True
    assert config.GAP_RECLAIM_ATR == 0.0
