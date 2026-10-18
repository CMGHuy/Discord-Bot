"""WSGI entry for gunicorn (v148, spec O1): `gunicorn ... admin_wsgi:app`.

Imported once, in the single gunicorn worker (preload_app = False), never by
`python admin_ui.py`'s own app.run path. It does what admin_ui.py's
__main__ block and app.main() do before serving, in the same order:

1. root logging (so anything logged while importing the app lands in
   logs/admin.log),
2. the boot record for the deploy telemetry,
3. the app itself,
4. the v132 bound on the admin's wait for the yfinance download lock --
   app.main() sets it, and gunicorn never runs app.main().
"""
import admin_ui
from swingbot import config
from swingbot.core.infra import deploy_marker

admin_ui.setup_logging()
deploy_marker.record_boot("admin")

from swingbot.admin.app import app  # noqa: E402  -- after logging, as in admin_ui.py
from swingbot.core.marketdata import yf_safe  # noqa: E402

yf_safe.set_default_lock_timeout(float(config.ADMIN_YF_LOCK_TIMEOUT_SECONDS))

__all__ = ["app"]
