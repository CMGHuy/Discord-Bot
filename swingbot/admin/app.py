"""
Admin web API for the swing bot -- runs as its own container alongside the
bot (see docker-compose.yml), sharing the same project directory (and
therefore the same .env, data/, and logs/ directories).

**This module renders no HTML.** Release B (2026-08-14) deleted the Jinja UI,
so what is left here is the Flask app object, the auth layer, and the handful
of payload builders that `/api/v1/*` imports back out of this module. The
browser-facing surface is the Angular SPA in `frontend/`, served as static
assets by `spa.py`; `/` redirects into the SPA's router and every data route
lives under `/api/v1/`.

This is meant for trusted, private use (e.g. behind your own firewall/VPN, or
just on localhost) -- it's protected by a single ADMIN_USERNAME/ADMIN_PASSWORD
from the environment, not a full user/permissions system. Don't expose it to
the open internet without putting a reverse proxy with real auth in front of
it.

Two ways in, both checked against the same ADMIN_USERNAME/ADMIN_PASSWORD: a
browser gets the SPA, which renders its own login form and sets a long-lived
(90-day) signed session cookie on success -- see the Auth section below.
Anything that sends an HTTP Basic Auth header (scripts, this project's own
test suite) is still checked the old way, untouched. Changing ADMIN_PASSWORD
(and restarting, same as today) invalidates existing sessions immediately.

Hot reload: saving settings sends the bot container a SIGHUP (via the Docker
socket, same mechanism as "Restart bot container" but without actually
stopping/starting anything); the bot's signal handler re-reads .env and
updates its live config in place. A few settings genuinely can't apply without
a real restart (the Discord token, and the admin UI's own
username/password/port) -- `/api/v1/system/settings` flags those rather than
claiming a success it didn't achieve. This process picks up .env changes via
the `_reload_env_if_changed` before-request hook further down.
"""
import gzip
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from logging.handlers import RotatingFileHandler

from flask import Flask, Response, redirect, request, session, url_for

from swingbot import config
from swingbot.core.scan_engine import is_scan_running
# `docker_sdk` is re-exported: api_v1/system.py imports it from here rather
# than from helpers, so it is used even though nothing in this file calls it.
from .helpers import docker_sdk, _load_or_create_secret_key

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
TRIGGER_FILE        = os.path.join(config.DATA_DIR, "trigger_check.flag")
MANUAL_CLOSE_QUEUE  = os.path.join(config.DATA_DIR, "manual_close_notify.json")
PAUSE_FILE = os.path.join(config.DATA_DIR, "scan_paused.flag")

# Section headings for the Settings screen, keyed by the section name in
# swingbot.config.FIELDS. Consumed by api_v1/system.py, which imports this
# from here.
_SECTION_META = {
    "Discord Connection":    ("🔗", "Token and channel IDs for the Discord bot."),
    "Scanning & Session":    ("⏱", "When the bot scans automatically and how often."),
    "Trade Filters & Risk":  ("🎯", "Hard constraints every scenario must meet before being scored or alerted."),
    "Data & Display":        ("📊", "Data history, currency, and market benchmark settings."),
    "Account Defaults":      ("💰", "Starting account values seeded into data/account.json on first run."),
    "Admin UI":              ("🔐", "Credentials and port for this web UI (requires admin container restart to take effect)."),
    "Secondary Alerts":       ("🔔", "Email and push (ntfy.sh) notifications for high-confidence signals."),
    "Multi-Timeframe Confluence": ("📈", "Higher-timeframe EMA bias filter applied as a per-ticker gate during scans."),
}

app = Flask(__name__)
# Signed session cookie for the /login page (see below) -- Basic Auth (the
# require_auth check further down) still works independently of this, so
# scripts/tests hitting routes with an Authorization header are unaffected.
app.secret_key = _load_or_create_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=90)
# Lax (not the Flask/Werkzeug default of no attribute at all) means the
# browser never attaches this cookie to a cross-site POST/PUT/DELETE -- the
# session cookie can't be ridden by a CSRF attempt from another origin.
# Basic Auth's cached-credentials path had this same class of exposure
# already (out of scope here); this closes it for the new session-cookie
# path specifically. Not forcing Secure=True: this app is documented as
# often run over plain HTTP on a private network/localhost (see module
# docstring), and Secure=True would silently break the cookie there.
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Wire Flask + Werkzeug request logs to admin.log so the Logs page can show
# admin UI activity separately from the bot's own log stream.
_admin_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_admin_file_handler = RotatingFileHandler(config.ADMIN_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2)
_admin_file_handler.setFormatter(_admin_log_fmt)
app.logger.addHandler(_admin_file_handler)
app.logger.setLevel(logging.INFO)
logging.getLogger("werkzeug").addHandler(_admin_file_handler)
logging.getLogger("werkzeug").setLevel(logging.INFO)


@app.after_request
def _gzip_response(response):
    """Hand-rolled response gzip -- no flask-compress dependency (the plan's
    "no new pip dependencies" constraint). Only compresses text/html and
    application/json bodies over 4 KB when the client advertises gzip
    support; send_file responses (chart PNGs, CSV export) are always
    direct_passthrough and are left completely alone, both because they're
    usually already-compressed binary and because rewriting a passthrough
    response's body would break Flask's streaming path."""
    accept_encoding = request.headers.get("Accept-Encoding", "")
    if "gzip" not in accept_encoding:
        return response
    if response.direct_passthrough or response.content_encoding:
        return response
    if response.mimetype not in ("text/html", "application/json"):
        return response
    body = response.get_data()
    if len(body) < 4096:
        return response
    compressed = gzip.compress(body, compresslevel=6)
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    response.headers.add("Vary", "Accept-Encoding")
    return response


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _password_hash() -> str:
    """Pinned into the session at login time and re-checked on every
    request (see _session_authenticated) -- so if ADMIN_USERNAME/PASSWORD
    change (Settings page) and the admin container restarts, any session
    logged in under the old credentials stops working immediately, the same
    way a stale Basic Auth header already does today. Without this, a
    session cookie would otherwise keep working indefinitely: its secret
    key is persisted (_load_or_create_secret_key) specifically so 90-day
    sessions survive a restart, so it can't double as the "did the password
    change" signal on its own.

    Keyed HMAC, not a plain hash: Flask's session cookie is signed but not
    encrypted, so a plain sha256(username:password) would sit in every
    session cookie as an offline-crackable, unsalted password hash anyone
    holding the cookie could brute-force. HMAC-ing it with the same secret
    that signs the cookie means the value is meaningless without also
    holding that server-side secret."""
    return hmac.new(
        app.secret_key.encode("utf-8"),
        f"{ADMIN_USERNAME}:{ADMIN_PASSWORD}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _session_authenticated() -> bool:
    return session.get("admin_authed") is True and hmac.compare_digest(
        session.get("pw_hash", ""), _password_hash()
    )


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if _session_authenticated():
            return view(*args, **kwargs)
        auth = request.authorization
        if auth:
            # Client explicitly attempted Basic Auth (e.g. a script, or this
            # suite's `auth` fixture) -- keep the original challenge behavior
            # for that path rather than redirecting it to an HTML login page.
            if auth.username == ADMIN_USERNAME and auth.password == ADMIN_PASSWORD:
                return view(*args, **kwargs)
            return Response(
                "Authentication required.", 401,
                {"WWW-Authenticate": 'Basic realm="Swing Bot Admin"'},
            )
        # Release B: there is no Jinja login page to redirect to any more.
        # An unauthenticated browser gets the SPA, which renders its OWN login
        # form instead of the shell (`App` branches on `session`), and asks
        # `/api/v1/session` — the one v1 route that is deliberately NOT
        # auth-guarded, precisely so "am I logged in" is answerable.
        #
        # Guarding the HTML here would be theatre: the SPA bundle is static
        # assets, and what actually protects data is `/api/v1/*` being
        # guarded, which it is.
        return redirect(url_for("spa_dashboard"))
    return wrapped


@app.before_request
def _reload_env_if_changed():
    """Pick up .env edits without restarting the admin container.

    The admin process never otherwise re-reads .env on its own (only the BOT
    process's scan loop calls this) -- without it, a value changed via the
    Settings page, or by hand, wouldn't show up here until the container
    itself restarted. Cheap (a single stat() call) unless .env actually
    changed, so safe to run per request.

    This lived in the Jinja `_render()` helper and so covered page renders
    only. Release B deleted the last route that called it, which silently
    dropped admin-side hot reload altogether -- the API kept serving whatever
    config was loaded at import. Moving it here restores the documented
    behaviour and widens it to `/api/v1/*`, which is the only thing serving
    config-derived values now.
    """
    config.auto_reload_if_changed()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    """The front door. Release B: the SPA owns it unconditionally.

    The `ADMIN_UI` flag is gone with the Jinja UI it used to select, so this
    no longer asks `spa.serves_root()` -- there is nothing to fall back to.

    A redirect rather than serving index.html here, so the URL in the address
    bar is one the SPA's router actually owns; landing on "/" and having the
    router rewrite it is the version that breaks the back button.

    `index` stays the endpoint `url_for` resolves to `/`. The endpoint it
    redirects to is bare `spa_dashboard` because `spa.register()` adds the
    workspace rules to the app directly, not to a blueprint.

    **Not `@require_auth`.** It was, and that shipped a 500: the decorator
    redirected an unauthenticated browser to `url_for("login_page")`, a Jinja
    endpoint Release B deleted, so every logged-out request to `/` raised
    BuildError. Guarding it was never the thing protecting anything anyway —
    the SPA renders its own login form, and `/api/v1/*` is what is guarded.
    """
    return redirect(url_for("spa_dashboard"))


def _ohlcv_frame(ticker: str):
    """Daily OHLCV for the interactive chart: live fetch first, falling back
    to the backtest CSV cache so the chart still renders offline. Split out
    of the route for testability (tests monkeypatch this)."""
    try:
        from swingbot.core.data import get_daily_data
        df = get_daily_data(ticker)
        if df is not None and len(df):
            return df
    except Exception:
        pass
    import pandas as pd
    safe = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    p = os.path.join(config.DATA_DIR, "backtest_cache", f"{safe}.csv")
    if os.path.exists(p):
        try:
            return pd.read_csv(p, index_col="Date", parse_dates=True)
        except Exception:
            return None
    return None


def _trade_for_levels(trade_id: str):
    """Look up a trade record by id for the ohlcv payload's optional
    `levels` block. Split out of the route for testability (tests
    monkeypatch this), same pattern as `_ohlcv_frame`."""
    from swingbot.core.performance import TradeLog
    return TradeLog().get_trade_by_id(trade_id)


# `trade_levels` and `ohlcv_bars` lived here so the Jinja chart and
# /api/v1/market/ohlcv could not disagree about rounding or about which key a
# take-profit line reads. Release B deleted the Jinja UI and v25 deleted the
# ohlcv route, leaving both with no callers -- and a `tp1`/`tp2` mapping that
# the surviving payload deliberately does not use (it carries Decision 10's
# names). Kept as dead code they would be a second mapping waiting to be
# picked up by mistake, which is the exact failure they were written against.


def scan_status_payload() -> dict:
    """Whether a scan trigger is pending, whether the automatic background
    scan loop is paused, whether a scan is running right now, and whether the
    bot process appears alive (from the heartbeat file session_scan writes on
    every tick -- see commands/scanning.py).

    A plain dict rather than a Response so /api/v1/system/scan can serve the
    same payload (NG16). The flag-file names this reads must match the ones
    the BOT reads; a mismatch is invisible in the UI, which simply shows
    "not paused" forever. tests/admin/test_api_v1_system_scan.py pins
    these constants against commands/scanning.py's.
    """
    pending = os.path.exists(TRIGGER_FILE)
    mtime = None
    if pending:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(TRIGGER_FILE), tz=timezone.utc).isoformat()
        except OSError:
            pass
    paused = os.path.exists(PAUSE_FILE)
    paused_at = None
    if paused:
        try:
            paused_at = datetime.fromtimestamp(os.path.getmtime(PAUSE_FILE), tz=timezone.utc).isoformat()
        except OSError:
            pass
    running = is_scan_running()

    # Bot liveness: the heartbeat file is written on every session_scan tick
    # (every SCAN_INTERVAL_MINUTES). If it's older than 2× that interval the
    # bot process is likely hung or offline.
    heartbeat_file = os.path.join(config.DATA_DIR, "bot_heartbeat.json")
    bot_alive = False
    bot_last_seen = None
    bot_session_active = None
    bot_scan_paused = None
    if os.path.exists(heartbeat_file):
        try:
            age_seconds = datetime.now(timezone.utc).timestamp() - os.path.getmtime(heartbeat_file)
            threshold = config.SCAN_INTERVAL_MINUTES * 60 * 2  # 2× interval
            bot_alive = age_seconds < threshold
            bot_last_seen = datetime.fromtimestamp(
                os.path.getmtime(heartbeat_file), tz=timezone.utc
            ).isoformat()
            with open(heartbeat_file) as hf:
                hb = json.load(hf)
                bot_session_active = hb.get("session_active")
                bot_scan_paused = hb.get("scan_paused")
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "pending": pending, "triggered_at": mtime, "paused": paused, "paused_at": paused_at,
        "running": running,
        "bot_alive": bot_alive,
        "bot_last_seen": bot_last_seen,
        "bot_session_active": bot_session_active,
        "bot_scan_paused": bot_scan_paused,
    }


def main():
    host = os.getenv("ADMIN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_PORT", 1234))
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
# Blueprints -- registered at the BOTTOM of this module, after every name
# they import from here (app, ADMIN_USERNAME, ADMIN_PASSWORD, require_auth,
# _SECTION_META, the payload builders above, ...) already exists in this
# module's namespace. Importing them any earlier (e.g. alongside the
# top-of-file imports) would deadlock on the circular reference: the api_v1
# endpoint modules reach back into `.app` for those names.
# ---------------------------------------------------------------------------
# api_v1 registers itself (blueprint + its two error handlers) rather than
# exposing a blueprint to register here: its 404 handler must be app-level,
# because an unmatched URL never reaches a blueprint.
from . import api_v1 as _api_v1  # noqa: E402
_api_v1.register(app)
# The SPA's own routes -- an allow-list of workspace prefixes plus its asset
# directory. Registered last so a workspace name can never shadow an API
# route; /dashboard and /api/v1/dashboard are different rules, but the
# ordering makes that a property of this file rather than of Werkzeug's
# matcher.
from . import spa as _spa  # noqa: E402
_spa.register(app)
