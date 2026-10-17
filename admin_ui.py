"""
Admin web UI -- entry point. The actual implementation lives at
swingbot/admin/app.py; this file configures logging and launches it.

Run with: python admin_ui.py
Listens on ADMIN_HOST:ADMIN_PORT (default 0.0.0.0:1234).

v148 (spec O1): the server is chosen INSIDE the image, never in
docker-compose.yml. Off Windows, with gunicorn importable (the production
image), this process replaces itself with gunicorn (deploy/gunicorn.conf.py,
admin_wsgi:app) before doing anything else, and admin_wsgi.py then does the
logging and boot record in the worker. Anywhere else (Windows dev, a
pre-v148 image without gunicorn) it falls through to Flask's app.run as
before. A rollback to an older image under today's compose file still boots.
"""
import logging
import os
import sys
from importlib.util import find_spec
from logging.handlers import RotatingFileHandler
from pathlib import Path

from swingbot import config
from swingbot.core.infra.logsetup import _OWNED, configure_logging

ADMIN_LOG_MAX_BYTES = 5 * 1024 * 1024
ADMIN_LOG_BACKUPS = 2
# gunicorn sets propagate=False on both and writes them to stdout/stderr with
# its own handlers, so logs/admin.log only sees them through a handler
# attached here.
GUNICORN_LOGGERS = ("gunicorn.access", "gunicorn.error")


def _pin_gunicorn_loggers() -> None:
    """Route gunicorn's request and error lines into logs/admin.log at INFO.

    Only the logsetup-owned FILE handler is attached: gunicorn already prints
    both loggers to the console. The handler an earlier call attached is
    removed first, because configure_logging closes and replaces it."""
    root = logging.getLogger()
    files = [h for h in root.handlers
             if isinstance(h, RotatingFileHandler) and getattr(h, _OWNED, False)]
    for name in GUNICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        for stale in [h for h in logger.handlers if getattr(h, _OWNED, False)]:
            logger.removeHandler(stale)
        for handler in files:
            logger.addHandler(handler)


def setup_logging() -> None:
    """Root logging for the admin process: console plus logs/admin.log (5MB x 2).

    Werkzeug request lines stay pinned at INFO whatever LOG_LEVEL says, as
    they were before v111, so the Logs page still shows admin activity; under
    gunicorn (v148) its access and error loggers get the same treatment."""
    configure_logging(config.ADMIN_LOG_FILE, config.LOG_LEVEL,
                      max_bytes=ADMIN_LOG_MAX_BYTES, backups=ADMIN_LOG_BACKUPS)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    _pin_gunicorn_loggers()


def _gunicorn_argv(root: Path) -> list[str]:
    """The command that replaces this process when the image ships gunicorn."""
    return [sys.executable, "-m", "gunicorn",
            "-c", str(root / "deploy" / "gunicorn.conf.py"),
            "admin_wsgi:app"]


def _maybe_exec_gunicorn() -> None:
    """Become gunicorn when it is importable off Windows; otherwise return.

    `find_spec` locates the package without importing it (gunicorn needs
    fcntl). On success `os.execv` never returns."""
    if sys.platform == "win32" or find_spec("gunicorn") is None:
        return
    argv = _gunicorn_argv(Path(__file__).resolve().parent)
    os.execv(argv[0], argv)


if __name__ == "__main__":
    # v148: before logging and record_boot, so neither runs twice -- under
    # gunicorn, admin_wsgi.py does both in the worker.
    _maybe_exec_gunicorn()
    # Logging first, so anything logged while importing the app lands in admin.log.
    setup_logging()
    from swingbot.admin.app import main
    from swingbot.core.infra.deploy_marker import record_boot
    record_boot("admin")
    main()
