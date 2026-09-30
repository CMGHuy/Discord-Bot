"""
Admin web UI -- entry point. The actual implementation lives at
swingbot/admin/app.py; this file configures logging and launches it.

Run with: python admin_ui.py
Listens on ADMIN_HOST:ADMIN_PORT (default 0.0.0.0:1234).
"""
import logging

from swingbot import config
from swingbot.core.infra.logsetup import configure_logging

ADMIN_LOG_MAX_BYTES = 5 * 1024 * 1024
ADMIN_LOG_BACKUPS = 2


def setup_logging() -> None:
    """Root logging for the admin process: console plus logs/admin.log (5MB x 2).

    Werkzeug request lines stay pinned at INFO whatever LOG_LEVEL says, as
    they were before v111, so the Logs page still shows admin activity."""
    configure_logging(config.ADMIN_LOG_FILE, config.LOG_LEVEL,
                      max_bytes=ADMIN_LOG_MAX_BYTES, backups=ADMIN_LOG_BACKUPS)
    logging.getLogger("werkzeug").setLevel(logging.INFO)


if __name__ == "__main__":
    # Logging first, so anything logged while importing the app lands in admin.log.
    setup_logging()
    from swingbot.admin.app import main
    from swingbot.core.infra.deploy_marker import record_boot
    record_boot("admin")
    main()
