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
    from swingbot.core.db import stages
    if stages.reads_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        return flags_repo().is_set("stop_scan")
    return os.path.exists(_STOP_FILE)


def request_stop() -> None:
    """Ask whatever scan is currently running to stop at its next checkpoint."""
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_STOP_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        flags_repo().set("stop_scan")


def _clear_stop() -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        try:
            os.remove(_STOP_FILE)
        except OSError:
            pass
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        flags_repo().clear("stop_scan")


def is_scan_running() -> bool:
    """Whether a scan (manual !check/`/check`, admin-UI-triggered, or the
    automatic session scan) is currently executing. Used by the admin UI
    to enable/disable its "Stop scan" button."""
    from swingbot.core.db import stages
    if stages.reads_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        return flags_repo().is_set("scan_running")
    return os.path.exists(_RUNNING_FILE)


def _mark_running(running: bool) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags") and running:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_RUNNING_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    elif stages.writes_json("flags"):
        try:
            os.remove(_RUNNING_FILE)
        except OSError:
            pass
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        if running:
            flags_repo().set("scan_running")
        else:
            flags_repo().clear("scan_running")
