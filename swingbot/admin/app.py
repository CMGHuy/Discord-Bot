"""
Small, self-contained admin web UI for the swing bot -- runs as its own
container alongside the bot (see docker-compose.yml), sharing the same
project directory (and therefore the same .env, data/, and logs/
directories).

Pages (sidebar navigation, see NAV_ITEMS):
  - Dashboard: open trades, auto-refreshing every 5s so a trade logged
    by `!check` or the background scan shows up without a manual
    browser refresh, click through to full detail on any of them,
    "clear all open trades".
  - Settings: every .env-driven setting as its own compact input field,
    grouped into sections (swingbot.config.FIELDS is the single source
    of truth both this UI and config.py itself read from). "Update
    settings" saves .env AND hot-reloads the bot -- see below.
  - Logs: a live-updating tail of the bot's log file.

Hot reload: "Update settings" sends the bot container a SIGHUP (via the
Docker socket, same mechanism as "Restart bot container" but without
actually stopping/starting anything); the bot's signal handler (see
bot_core.py) re-reads .env and updates its live config in place. A few
settings genuinely can't apply without a real restart (the Discord
token, and the admin UI's own username/password/port) -- those are
flagged in the UI and the save confirmation message says so explicitly
rather than claiming success it didn't achieve.

This is meant for trusted, private use (e.g. behind your own firewall/
VPN, or just on localhost) -- it's protected by a single ADMIN_USERNAME/
ADMIN_PASSWORD from the environment, not a full user/permissions system.
Don't expose it to the open internet without putting a reverse proxy with
real auth in front of it.

Two ways in, both checked against the same ADMIN_USERNAME/ADMIN_PASSWORD:
a browser hitting any page gets redirected to /login (a real HTML form,
so password managers can save it), which sets a long-lived (90-day)
signed session cookie on success -- see the Auth section below. Anything
that sends an HTTP Basic Auth header (scripts, this project's own test
suite) is still checked the old way, untouched. Changing ADMIN_PASSWORD
(and restarting, same as today) invalidates existing sessions immediately.

Page markup lives in templates/*.html (Flask's standard auto-discovered
templates/ folder next to this module) rather than inline Python string
constants -- keeps this file to routes/logic only and lets the HTML be
edited/linted as HTML. Shared CSS lives in static/style.css.
"""
import csv
import gzip
import hashlib
import hmac
import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import wraps
from logging.handlers import RotatingFileHandler

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

from flask import Flask, Response, abort, redirect, render_template, request, send_file, session, url_for

from swingbot import config
from swingbot.core.performance import TradeLog
from swingbot.core.scan_engine import is_scan_running, regenerate_chart_for_trade, request_stop
from swingbot.core.data import get_company_name, get_currency_symbol
from swingbot.core.watchlist import load_watchlist, add_ticker, remove_ticker
from swingbot.core.backtest_cache import ensure_cached_background
from swingbot.core.ticker_directory import search_tickers
from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
# Dashboard view-model builders. Imported as a namespace rather than by name:
# these are the ONLY dashboard computation left outside this file's routes,
# and `dash.` at each call site says so.
from . import dashboard as dash
# Pure helper functions (.env parsing, Docker container control, confidence-hex,
# log tailing) live in their own module -- see helpers.py's own docstring for why.
from .helpers import (
    BOT_CONTAINER_NAME, FIELDS_BY_KEY, FIELDS_BY_SECTION, docker_sdk,
    _build_env_text, _changed_non_hot_reloadable_fields, _clear_log, _confidence_hex,
    _field_display_value, _get_bot_container, _hot_reload_bot_container, _primary_strategy_label,
    _read_env_values, _restart_bot_container, _sources_str, _tail_log, _tail_admin_log,
    _clear_admin_log, _write_env_text, get_versions, settings_diff,
    append_settings_audit, read_settings_audit, import_env_text,
    build_settings_export_text, _load_or_create_secret_key,
)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
TRIGGER_FILE        = os.path.join(config.DATA_DIR, "trigger_check.flag")
MANUAL_CLOSE_QUEUE  = os.path.join(config.DATA_DIR, "manual_close_notify.json")
PAUSE_FILE = os.path.join(config.DATA_DIR, "scan_paused.flag")

NAV_ITEMS = [
    ("dashboard", "🏠", "Dashboard", "index"),
    ("plans",     "📋", "Plans", "pages.plans_page"),
    ("stats",     "📊", "Performance", "stats_page"),
    ("strategies","🧭", "Strategies", "pages.strategies_page"),
    ("calibration","📐", "Calibration", "pages.calibration_page"),
    ("journal",   "📓", "Journal", "pages.journal_page"),
    ("tuning",    "🛠", "Tuning", "pages.tuning_page"),
    ("watchlist", "📋", "Watchlist", "watchlist_page"),
    ("risk",      "🛡", "Risk", "risk_panel"),
    ("settings",  "⚙️", "Settings", "settings_page"),
    ("logs",      "📜", "Logs", "logs_page"),
]

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


try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None


def _berlin_time(dt_str: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Jinja filter: converts a UTC ISO datetime string to Berlin local time."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if _BERLIN_TZ:
            dt = dt.astimezone(_BERLIN_TZ)
        return dt.strftime(fmt)
    except Exception:
        return dt_str[:16]


app.jinja_env.filters["berlin_time"] = _berlin_time


def _trades() -> TradeLog:
    """
    A fresh TradeLog *every call*, deliberately not a module-level
    singleton. TradeLog reads trades.json once, in __init__, and caches
    it in memory -- fine for the bot process, which is the only writer
    and always reads its own in-memory copy right after writing it. The
    admin UI is a *separate process* though: a singleton created once at
    Flask startup would never see trades the bot logs afterward (e.g.
    from `!check`), even though they're sitting right there in the
    shared trades.json file. Re-reading fresh each request is cheap
    (small JSON file) and guarantees the admin UI always reflects
    what's actually on disk right now.
    """
    return TradeLog()


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


def _safe_next(next_value: str | None) -> str:
    """Only ever redirect to a same-site relative path -- next_value comes
    from a query string / form field, so an unvalidated value (e.g.
    "https://evil.example") would be an open-redirect vector."""
    if next_value and next_value.startswith("/") and not next_value.startswith("//") and "://" not in next_value:
        return next_value
    return url_for("index")


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


# ---------------------------------------------------------------------------
# Page rendering -- shared sidebar layout (templates/base.html) wraps every
# page's own template via Jinja's {% extends %}.
# ---------------------------------------------------------------------------
def _render(title: str, active_page: str, template_name: str, **ctx) -> str:
    # The admin process never otherwise re-reads .env on its own (only the
    # BOT process's scan loop calls this) -- without it, a value changed via
    # the Settings page (or by hand) wouldn't show up here until the admin
    # container itself restarted. Cheap (a single stat() call) unless .env
    # actually changed, so safe to call on every single page render.
    config.auto_reload_if_changed()
    return render_template(
        template_name,
        title=title,
        active_page=active_page,
        nav_items=NAV_ITEMS,
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        msg=request.args.get("msg"),
        ok=request.args.get("ok"),
        versions=get_versions(),
        **ctx,
    )


# ---------------------------------------------------------------------------
# Routes -- Dashboard
# ---------------------------------------------------------------------------
# Every computation these three routes need lives in dashboard.py as plain
# functions of their arguments. What is left here is the HTTP shell: read the
# query string, clamp it, delegate, respond.


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


def _dashboard_page():
    """Full Dashboard page.

    Renders the auto-refreshing fragment inline for first paint, and -- unlike
    the fragment -- also the Trade History card's filter options. Those belong
    to markup the poll never replaces, so building them once per page load
    rather than once per 5s tick costs nothing and saves a full-history walk
    every tick.
    """
    mode = dash.normalize_mode(request.args.get("mode"))
    all_raw = _trades().get_trades(status=None, limit=None, sort_by="opened_at")
    first_page, total = dash.query_closed_trades(
        all_raw, mode=mode, page=1, per_page=dash.CLOSED_TRADES_FIRST_PAGE)
    return _render(
        "Dashboard", "dashboard", "dashboard.html",
        fragment=render_template("dashboard_fragment.html",
                                 **dash.build_fragment_context(mode)),
        dashboard_refresh_seconds=config.DASHBOARD_REFRESH_SECONDS,
        dashboard_mode=mode,
        closed_trades=first_page,
        closed_trades_total=total,
        closed_trade_filter_options=dash.build_filter_options(all_raw),
        strategy_map={t["id"]: _primary_strategy_label(t) for t in first_page},
        cur_map={t["ticker"]: get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL)
                 for t in first_page},
        confidence_hex=_confidence_hex,
        trade_pnl=dash.closed_pnl, trade_r=dash.closed_r, trade_days=dash.closed_days,
        row_offset=0,
    )


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


def trade_levels(trade: dict) -> dict:
    """The plan lines a chart draws, from a trade record.

    Shared with /api/v1/market/ohlcv (NG17). Two charts read these keys
    during the migration; a second mapping here would let one of them draw a
    take-profit line at the wrong price, which looks entirely plausible.
    """
    return {"entry": trade.get("entry"), "stop_loss": trade.get("stop_loss"),
            "tp1": trade.get("take_profit"), "tp2": trade.get("target2_price"),
            "direction": trade.get("direction")}


def ohlcv_bars(df) -> list:
    """DataFrame rows -> the bar objects a chart consumes. One definition,
    shared with /api/v1/market/ohlcv so the Angular and Jinja charts cannot
    disagree about rounding or field names."""
    return [
        {"time": idx.strftime("%Y-%m-%d"), "open": round(float(r["Open"]), 4),
         "high": round(float(r["High"]), 4), "low": round(float(r["Low"]), 4),
         "close": round(float(r["Close"]), 4), "volume": float(r["Volume"])}
        for idx, r in df.iterrows()
    ]


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
# helpers, ...) already exists in this module's namespace. Importing these
# any earlier (e.g. alongside the top-of-file imports) would deadlock on
# the circular reference: api.py/pages.py both do `from .app import app`.
# ---------------------------------------------------------------------------
# api_v1 registers itself (blueprint + its two error handlers) rather than
# exposing a blueprint to register here: its 404 handler must be app-level,
# because an unmatched URL never reaches a blueprint.
#
# (Release B note: an earlier version of this comment said api_v1 "imports
# require_auth_json from api.py, so that module must already exist". It does
# not -- `api_v1/auth.py` imports the `app` MODULE and builds its own
# decorator, precisely so the legacy error shape never leaked into v1. The
# stale claim would have made deleting api.py look impossible.)
from . import api_v1 as _api_v1  # noqa: E402
_api_v1.register(app)
# The SPA's own routes -- an allow-list of workspace prefixes plus its asset
# directory. Registered last so a workspace name can never shadow an API
# route; /dashboard and /api/v1/dashboard are different rules, but the
# ordering makes that a property of this file rather than of Werkzeug's
# matcher.
from . import spa as _spa  # noqa: E402
_spa.register(app)
