"""v111 §1: the admin process configures the ROOT logger, so INFO from any
swingbot.admin.* module reaches admin.log (before v111 only app.logger and
werkzeug had a handler, and every other module's INFO was dropped)."""
import logging
import re
from logging.handlers import RotatingFileHandler

import admin_ui
from swingbot import config


def _owned_file_handler(root):
    [handler] = [h for h in root.handlers
                 if isinstance(h, RotatingFileHandler) and getattr(h, "_swingbot_logsetup", False)]
    return handler


def test_admin_module_info_reaches_admin_log(tmp_path, monkeypatch, restore_root_logging):
    path = tmp_path / "admin.log"
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(path))
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")

    admin_ui.setup_logging()

    handler = _owned_file_handler(restore_root_logging)
    assert (handler.maxBytes, handler.backupCount) == (5 * 1024 * 1024, 2)
    logging.getLogger("swingbot.admin.events.stream").info("client connected")
    handler.flush()
    assert re.search(r"\[INFO\] \[-\] swingbot\.admin\.events\.stream: client connected",
                     path.read_text())


def test_werkzeug_request_lines_stay_at_info_under_a_warning_level(tmp_path, monkeypatch,
                                                                    restore_root_logging):
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(tmp_path / "admin.log"))
    monkeypatch.setattr(config, "LOG_LEVEL", "WARNING")

    admin_ui.setup_logging()

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("werkzeug").getEffectiveLevel() == logging.INFO


def test_importing_the_app_attaches_no_handlers_of_its_own():
    import swingbot.admin.app as app_mod

    assert not hasattr(app_mod, "_admin_file_handler")
    assert not any(isinstance(h, RotatingFileHandler)
                   for h in logging.getLogger("werkzeug").handlers)


def test_lazy_bot_core_import_leaves_the_admin_handler_alone(tmp_path):
    """The admin process lazily imports swingbot.commands.growth (-> bot_core)."""
    import subprocess
    import sys
    script = (
        "import logging\n"
        "from logging.handlers import RotatingFileHandler\n"
        "import admin_ui\n"
        "from swingbot import config\n"
        f"config.ADMIN_LOG_FILE = {str(tmp_path / 'admin.log')!r}\n"
        f"config.LOG_FILE = {str(tmp_path / 'bot.log')!r}\n"
        "admin_ui.setup_logging()\n"
        "import swingbot.commands.growth\n"
        "names = [h.baseFilename for h in logging.getLogger().handlers"
        " if isinstance(h, RotatingFileHandler)]\n"
        "print('|'.join(names))\n"
    )
    root = str(__import__("pathlib").Path(__file__).resolve().parents[2])
    out = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True,
                         text=True, check=True).stdout.strip().splitlines()[-1]
    assert out.endswith("admin.log") and "bot.log" not in out
