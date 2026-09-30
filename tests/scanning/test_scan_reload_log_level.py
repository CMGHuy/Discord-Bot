"""v111 §1/§4: the scan-time config auto-reload reapplies LOG_LEVEL (it used
to miss it) and does not repeat config.reload()'s own change log."""
import logging

from swingbot import config
from swingbot.core.scanning import scan_run


def test_scan_time_auto_reload_reapplies_log_level(monkeypatch, restore_root_logging):
    monkeypatch.setattr(scan_run, "auto_reload_if_changed", lambda: {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")

    changed = scan_run._reload_config_before_scan()

    assert changed == {"LOG_LEVEL": ("INFO", "DEBUG")}
    assert logging.getLogger().level == logging.DEBUG


def test_other_changes_leave_the_level_alone(monkeypatch, restore_root_logging):
    logging.getLogger().setLevel(logging.WARNING)
    monkeypatch.setattr(scan_run, "auto_reload_if_changed",
                        lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")

    scan_run._reload_config_before_scan()

    assert logging.getLogger().level == logging.WARNING


def test_the_reload_is_not_logged_a_second_time(monkeypatch, caplog):
    monkeypatch.setattr(scan_run, "auto_reload_if_changed",
                        lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._reload_config_before_scan()
    assert not any("auto-reloaded" in r.getMessage() for r in caplog.records)
