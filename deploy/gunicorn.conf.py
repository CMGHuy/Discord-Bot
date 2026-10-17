"""gunicorn settings for the admin container (v148, spec O1).

Loaded by `admin_ui._maybe_exec_gunicorn` (`gunicorn -c deploy/gunicorn.conf.py
admin_wsgi:app`). Plain Python on purpose: it never imports gunicorn, so
tests/admin/test_gunicorn_conf.py can load it with runpy on any OS.

ONE worker is a requirement, not a tuning choice: the login limiter
(swingbot/admin/login_limiter.py), the admin-side swallowed-error counter and
the SSE broker's event sequence all live in this process's memory. Two
workers would split each of them in two (OH1's finding is in the plan's
Progress block).

ADMIN_HOST / ADMIN_PORT come from the container environment (compose's
env_file), exactly as app.main() reads them. They are read once at launch,
so a bind change needs a container restart, not a SIGHUP (as with app.run).
"""
import os

bind = f"{os.environ.get('ADMIN_HOST') or '0.0.0.0'}:{os.environ.get('ADMIN_PORT') or 1234}"
workers = 1
worker_class = "gthread"
# The broker's 8-stream SSE cap (broker.MAX_CONNECTIONS) plus 8 threads for
# ordinary requests. The cap stays at 8.
threads = 16
timeout = 60
# Open SSE streams would otherwise hold every restart for the 30 s default;
# the SPA's EventSource reconnects on its own.
graceful_timeout = 5
keepalive = 5
# Request lines to stdout (docker logs); admin_ui.setup_logging also routes
# the gunicorn.access logger into logs/admin.log for the Logs page.
accesslog = "-"
# The app module (and the DB LISTEN thread it starts) must load in the
# worker, never in the master.
preload_app = False
