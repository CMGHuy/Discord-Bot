"""Scan stop/running flags shared by the bot and admin process.

The admin UI and bot are separate processes sharing only the database, so
scan state lives in the flags table and is cooperatively checked at safe
checkpoints.
"""


def _flags():
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo()


def is_stop_requested() -> bool:
    return _flags().is_set("stop_scan")


def request_stop() -> None:
    """Ask whatever scan is currently running to stop at its next checkpoint."""
    _flags().set("stop_scan")


def _clear_stop() -> None:
    _flags().clear("stop_scan")


def is_scan_running() -> bool:
    """Whether a scan (manual !check/`/check`, admin-UI-triggered, or the
    automatic session scan) is currently executing. Used by the admin UI
    to enable/disable its "Stop scan" button."""
    return _flags().is_set("scan_running")


def _mark_running(running: bool) -> None:
    if running:
        _flags().set("scan_running")
    else:
        _flags().clear("scan_running")
