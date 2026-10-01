"""v111 §3: the kill switch logs each real flip, once, at INFO."""
import logging

from swingbot import config
from swingbot.core.edge import throttle


def _kill_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == throttle.log.name]


def test_each_real_flip_logs_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)

    with caplog.at_level(logging.INFO, logger=throttle.log.name):
        throttle.set_kill(True, reason="drawdown >20%")
        throttle.set_kill(True, reason="drawdown >20%")   # already on: early return, no line
        throttle.set_kill(False)

    assert _kill_lines(caplog) == [
        "Kill switch ON: drawdown >20%",
        "Kill switch OFF (released, was: drawdown >20%)",
    ]
    assert all(r.levelno == logging.INFO for r in caplog.records if r.name == throttle.log.name)


def test_releasing_an_already_released_switch_is_silent(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)

    with caplog.at_level(logging.INFO, logger=throttle.log.name):
        throttle.set_kill(False)

    assert _kill_lines(caplog) == []
