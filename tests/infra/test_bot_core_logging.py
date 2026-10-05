"""v111 §1: the bot process logs through the shared root setup."""
import logging
import re
from logging.handlers import RotatingFileHandler

from swingbot import bot_core, config


def _owned_file_handler(root):
    [handler] = [h for h in root.handlers
                 if isinstance(h, RotatingFileHandler) and getattr(h, "_swingbot_logsetup", False)]
    return handler


def test_bot_logging_writes_the_shared_format_to_log_file(tmp_path, monkeypatch, restore_root_logging):
    path = tmp_path / "bot.log"
    monkeypatch.setattr(config, "LOG_FILE", str(path))
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")

    bot_core.configure_bot_logging()

    handler = _owned_file_handler(restore_root_logging)
    assert (handler.maxBytes, handler.backupCount) == (5 * 1024 * 1024, 3)
    logging.getLogger("swingbot.core.scanning.scan_run").info("hello")
    handler.flush()
    assert re.search(r"\[INFO\] \[-\] swingbot\.core\.scanning\.scan_run: hello", path.read_text())


def test_sighup_reapplies_log_level_through_the_one_setter(monkeypatch):
    applied = []
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(bot_core.config, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(bot_core, "apply_log_level", applied.append)
    monkeypatch.setattr(bot_core, "_reload_callbacks", [])

    bot_core._handle_reload_signal()

    assert applied == ["DEBUG"]


def test_sighup_without_a_level_change_leaves_the_level_alone(monkeypatch):
    applied = []
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    monkeypatch.setattr(bot_core, "apply_log_level", applied.append)
    monkeypatch.setattr(bot_core, "_reload_callbacks", [])

    bot_core._handle_reload_signal()

    assert applied == []


def _root_log_files(tmp_path, statements):
    import pathlib
    import subprocess
    import sys
    script = (
        "import logging\n"
        "from logging.handlers import RotatingFileHandler\n"
        f"{statements}\n"
        "print('|'.join(h.baseFilename for h in logging.getLogger().handlers"
        " if isinstance(h, RotatingFileHandler)))\n"
    )
    root = str(pathlib.Path(__file__).resolve().parents[2])
    out = subprocess.run([sys.executable, "-c", script], cwd=root,
                         capture_output=True, text=True, check=True).stdout
    return out.strip().splitlines()[-1] if out.strip() else ""


def test_importing_bot_core_installs_no_handlers(tmp_path):
    assert _root_log_files(tmp_path, "import swingbot.bot_core") == ""


def test_the_bot_entry_point_configures_bot_logging(tmp_path):
    assert _root_log_files(tmp_path, "import bot").endswith("bot.log")
