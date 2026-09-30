"""v111 §1/§4: config_watcher uses apply_log_level, hands interval changes
to the one shared callback, and does not repeat config.reload()'s log."""
import asyncio
import logging

from swingbot import config
from swingbot.commands.scanning import loops


def _quiet_watcher(monkeypatch, tmp_path, changed):
    monkeypatch.setattr(loops, "auto_reload_if_changed", lambda: changed, raising=False)
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE", str(tmp_path / "manual_close_notify.json"))
    monkeypatch.setattr(loops.runstate, "_TRIGGER_FILE", str(tmp_path / "trigger_check.flag"))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "")


def test_watcher_reapplies_log_level_through_the_one_setter(monkeypatch, tmp_path):
    applied = []
    _quiet_watcher(monkeypatch, tmp_path, {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(loops, "apply_log_level", applied.append)

    asyncio.run(loops.config_watcher.coro())

    assert applied == ["DEBUG"]


def test_watcher_hands_interval_changes_to_the_shared_callback(monkeypatch, tmp_path):
    calls = []
    changed = {"SCAN_INTERVAL_MINUTES": (5, 10)}
    _quiet_watcher(monkeypatch, tmp_path, changed)
    monkeypatch.setattr(loops, "_apply_scan_interval_change", calls.append)

    asyncio.run(loops.config_watcher.coro())

    assert calls == [changed]


def test_watcher_does_not_repeat_the_reload_log(monkeypatch, tmp_path, caplog):
    _quiet_watcher(monkeypatch, tmp_path, {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    with caplog.at_level(logging.INFO):
        asyncio.run(loops.config_watcher.coro())
    assert not any("auto-reloaded" in r.getMessage() for r in caplog.records)
