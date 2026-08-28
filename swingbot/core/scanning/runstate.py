"""File-backed stop/running state shared by the bot and admin process.

The admin UI and bot are separate processes sharing only data/ on disk, so
scan state must be file-backed and cooperatively checked at safe checkpoints.
"""
import os
from datetime import datetime, timezone

from swingbot import config


_STOP_FILE = os.path.join(config.DATA_DIR, "stop_scan.flag")
_RUNNING_FILE = os.path.join(config.DATA_DIR, "scan_running.flag")


def is_stop_requested() -> bool:
    return os.path.exists(_STOP_FILE)


def request_stop() -> None:
    """Ask whatever scan is currently running to stop at its next checkpoint."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(_STOP_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def _clear_stop() -> None:
    try:
        os.remove(_STOP_FILE)
    except OSError:
        pass  # already clear


def is_scan_running() -> bool:
    """Whether a scan (manual !check/`/check`, admin-UI-triggered, or the
    automatic session scan) is currently executing. Used by the admin UI
    to enable/disable its "Stop scan" button."""
    return os.path.exists(_RUNNING_FILE)


def _mark_running(running: bool) -> None:
    if running:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_RUNNING_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    else:
        try:
            os.remove(_RUNNING_FILE)
        except OSError:
            pass  # already clear
