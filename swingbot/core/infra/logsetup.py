"""One logging setup for both processes (bot and admin), plus the scan id.

configure_logging() owns the ROOT logger's two handlers, console and a
rotating file, so every module logger (logging.getLogger(__name__)) reaches
both without wiring of its own. Before v111 the admin process attached
admin.log to app.logger and werkzeug only, and every other module's INFO in
that process was dropped.

The scan id is a ContextVar. scan_context() sets it around one scan, and
ScanIdFilter copies it onto every record the two handlers see, so a line
logged anywhere inside a scan carries the id without knowing about it.
asyncio tasks and asyncio.to_thread() copy the context. A ThreadPoolExecutor
does NOT, so pool work inside a scan goes through with_current_context().
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
import secrets
import string
import time
from logging.handlers import RotatingFileHandler

# The level stays the FIRST bracketed word: the admin Logs page filters on it.
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(scan_id)s] %(name)s: %(message)s"
NO_SCAN = "-"
_OWNED = "_swingbot_logsetup"
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits

scan_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("scan_id", default=NO_SCAN)


class ScanIdFilter(logging.Filter):
    """Stamp record.scan_id from the emitting thread's context. Never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.scan_id = scan_id_var.get()
        return True


def _level_value(level) -> int:
    if isinstance(level, int):
        return level
    return logging.getLevelNamesMapping().get(str(level).upper(), logging.INFO)


def apply_log_level(level) -> int:
    """Set the root logger's level. The only level setter after startup.

    An unknown name falls back to INFO, as bot_core always did."""
    value = _level_value(level)
    logging.getLogger().setLevel(value)
    return value


def _remove_owned_handlers(root: logging.Logger) -> None:
    for handler in [h for h in root.handlers if getattr(h, _OWNED, False)]:
        root.removeHandler(handler)
        handler.close()


def configure_logging(log_file: str, level, *, max_bytes: int, backups: int) -> None:
    """Install the console and rotating-file handlers on the root logger.

    Idempotent: handlers an earlier call installed are removed and closed
    first, so calling it twice never duplicates output."""
    root = logging.getLogger()
    _remove_owned_handlers(root)
    formatter = logging.Formatter(LOG_FORMAT, defaults={"scan_id": NO_SCAN})
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backups)
    for handler in (logging.StreamHandler(), file_handler):
        handler.setFormatter(formatter)
        handler.addFilter(ScanIdFilter())
        setattr(handler, _OWNED, True)
        root.addHandler(handler)
    apply_log_level(level)


def new_scan_id(now: float | None = None) -> str:
    """'s-' + local HHMM (the clock %(asctime)s prints) + two chars of [a-z0-9]."""
    stamp = time.strftime("%H%M", time.localtime(now))
    return "s-" + stamp + "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(2))


@contextlib.contextmanager
def scan_context(scan_id: str):
    """Set the scan id for everything logged inside the block."""
    token = scan_id_var.set(scan_id)
    try:
        yield scan_id
    finally:
        scan_id_var.reset(token)


def with_current_context(fn):
    """Wrap fn so each call runs in a fresh copy of the CALLER's context.

    For ThreadPoolExecutor work inside a scan. One Context object cannot be
    entered by two threads at once, so every call gets its own copy."""
    parent = contextvars.copy_context()

    @functools.wraps(fn)
    def run(*args, **kwargs):
        return parent.copy().run(fn, *args, **kwargs)

    return run
