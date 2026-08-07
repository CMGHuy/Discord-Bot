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
from swingbot.core.performance import TradeLog, trade_proximity
from swingbot.core.scan_engine import is_scan_running, regenerate_chart_for_trade, request_stop
from swingbot.core.account import compute_position_size, get_daily_summary, load_account_config
from swingbot.core.data import get_company_name, get_currency_symbol, get_current_price, prefetch_prices, is_us_market_active
from swingbot.core.watchlist import load_watchlist, add_ticker, remove_ticker
from swingbot.core.backtest_cache import ensure_cached_background
from swingbot.core.ticker_directory import search_tickers
from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
# Pure helper functions (.env parsing, Docker container control, confidence-hex,
# log tailing) live in their own module -- see helpers.py's own docstring for why.
from .helpers import (
    BOT_CONTAINER_NAME, FIELDS_BY_KEY, FIELDS_BY_SECTION, docker_sdk,
    _build_env_text, _changed_non_hot_reloadable_fields, _clear_log, _confidence_hex,
    _field_display_value, _get_bot_container, _hot_reload_bot_container, _primary_strategy_label,
    _read_env_values, _restart_bot_container, _sources_str, _tail_log, _tail_admin_log,
    _clear_admin_log, _write_env_text, get_versions, settings_diff,
    append_settings_audit, read_settings_audit, import_env_text,
    _load_or_create_secret_key,
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

# Bounds the Trade History table's server-rendered payload -- see the
# closed_trades slicing in _render_dashboard_fragment() below. High enough
# that the table's own 10/25/50/All per-page selector has real rows to
# paginate through, low enough to keep the fragment render/transfer cheap
# even on an account with years of history.
CLOSED_TRADES_FRAGMENT_LIMIT = 500

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
        next_path = request.full_path if request.query_string else request.path
        return redirect(url_for("login_page", next=next_path))
    return wrapped


@app.route("/login", methods=["GET"])
def login_page():
    if _session_authenticated():
        return redirect(url_for("index"))
    return render_template("login.html", next=request.args.get("next", ""), error=None)


@app.route("/login", methods=["POST"])
def login_submit():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    next_value = request.form.get("next", "")
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session.clear()
        session["admin_authed"] = True
        session["pw_hash"] = _password_hash()
        session.permanent = True
        return redirect(_safe_next(next_value))
    return render_template("login.html", next=next_value, error="Invalid username or password."), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))


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
def _format_duration_hms(total_seconds: float) -> str:
    """
    Human-readable elapsed-time label with day/hour/MINUTE granularity --
    e.g. "12m", "4h 20m", "1d 5h 32m" -- used everywhere a "how long has
    this been open/how long was this held" figure is shown (dashboard's
    Open Trades + Trade History Holding columns, plus the Avg holding
    period stat card). Short d/h/m suffixes (not the old spelled-out
    "4 hours 20 minutes") so the figure stays compact in a narrow table
    column. Whole-calendar-days-only (as this used to show, before d/h/m
    granularity was added at all) reads as "0" for anything opened/closed
    same-day regardless of whether that was 10 minutes or 23 hours -- this
    is precise down to the minute instead, and always surfaces hours+
    minutes even once the duration spans full days, rather than dropping
    them once a coarser unit is available.
    """
    total_seconds = max(0.0, total_seconds)
    total_minutes = int(total_seconds // 60)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return ' '.join(parts)


def _format_open_duration(total_hours: float) -> str:
    """Thin wrapper over _format_duration_hms for callers that already have
    an elapsed-hours figure (the Open Trades loop below)."""
    return _format_duration_hms(max(0.0, total_hours) * 3600)


def _pos_color(pos_pct: float, entry_pct: float) -> str:
    """Color for the SL→TP progress bar and percentage text.
    Interpolates red (SL, 0%) → grey (entry) → green (TP, 100%)
    so the bar always shows absolute position between stop and target,
    independent of whether the trade is currently profitable.
    """
    SL      = (0xda, 0x6d, 0x6d)   # red   (#da6d6d)
    NEUTRAL = (0x5a, 0x62, 0x75)   # grey  (#5a6275)
    TP      = (0x6d, 0xda, 0x9e)   # green (#6dda9e)
    ep = max(1.0, min(99.0, entry_pct))
    if pos_pct <= ep:
        t = max(0.0, min(1.0, pos_pct / ep))
        c1, c2 = SL, NEUTRAL
    else:
        t = max(0.0, min(1.0, (pos_pct - ep) / (100.0 - ep)))
        c1, c2 = NEUTRAL, TP
    r = round(c1[0] + (c2[0] - c1[0]) * t)
    g = round(c1[1] + (c2[1] - c1[1]) * t)
    b = round(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_today_berlin(iso_ts: str | None) -> bool:
    """True if the given ISO timestamp falls on today's Europe/Berlin calendar
    day -- the same day boundary the daily retrospective and account summary
    already use, so the dashboard's "Today" mode lines up with them."""
    if not iso_ts:
        return False
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if _BERLIN_TZ:
            dt = dt.astimezone(_BERLIN_TZ)
            today = datetime.now(_BERLIN_TZ).date()
        else:
            today = datetime.now(timezone.utc).date()
        return dt.date() == today
    except Exception:
        return False


CLOSED_TRADE_STATUSES = ("win", "loss", "closed")

# Allowed page sizes, mirroring the table's own selector. 0 means "All".
# Clamped server-side: the page size decides how much work a request does, so
# it is never taken on trust from the query string.
ALLOWED_PER_PAGE = (10, 25, 50, 0)

# Query-string filter name -> how to read the matching value off a trade.
# These MUST stay in step with the data-* attributes the row partial emits,
# since both describe the same six Trade History dropdowns.
_CT_FILTER_FIELDS = {
    "outcome":  lambda t: t.get("status"),
    "ticker":   lambda t: t.get("ticker"),
    "strategy": _primary_strategy_label,
    "horizon":  lambda t: t.get("horizon_key"),
    "dir":      lambda t: t.get("direction"),
    "conf":     lambda t: t.get("confidence_level"),
}


def _query_closed_trades(all_raw, *, mode="all", filters=None, page=1, per_page=25):
    """Scope -> filter -> sort -> slice the closed-trade history, in that order.

    Returns ``(rows, total)`` where *total* is the count after scoping and
    filtering but BEFORE slicing, so the pager can work out how many pages
    exist without a second pass.

    `mode` follows the dashboard toggle: "today" and "active" both narrow to
    trades CLOSED today (Europe/Berlin). Those two modes are deliberately
    identical here -- the only thing separating them is whether still-open
    positions from other days show, and this table never contains open trades.
    """
    rows = [t for t in all_raw if t.get("status") in CLOSED_TRADE_STATUSES]

    if mode in ("today", "active"):
        rows = [t for t in rows if _is_today_berlin(t.get("closed_at"))]

    for key, value in (filters or {}).items():
        if not value:
            continue                      # absent/blank means "no filter"
        getter = _CT_FILTER_FIELDS.get(key)
        if getter is None:
            continue
        rows = [t for t in rows if str(getter(t) or "") == str(value)]

    rows.sort(key=lambda t: t.get("closed_at") or "", reverse=True)
    total = len(rows)

    if per_page:
        page = max(1, int(page or 1))
        start = (page - 1) * per_page
        rows = rows[start:start + per_page]
    return rows, total


def _render_dashboard_fragment() -> str:
    # Three modes for the dashboard's summarized panels (stat cards + tables):
    #   - "active" (the default): today's new trades PLUS every still-open
    #     position regardless of which day it was opened -- "what do I need
    #     to pay attention to right now". This is the only mode that mixes
    #     days: an old open swing sitting from last week still shows up
    #     (it's still live risk), but closed-trade stats only count today's
    #     closes, not the whole history.
    #   - "today": strictly today's activity (Europe/Berlin calendar day)
    #     only -- trades opened today, or closed today. An old open trade
    #     from last week is NOT shown here even though it's still open,
    #     since it's not part of "today".
    #   - "all": the original behavior -- every trade, no filtering.
    # Read from the query string so both the full-page load and the
    # auto-refresh fragment fetch respect whichever mode the user picked.
    mode = request.args.get("mode", "active")
    if mode not in ("active", "today", "all"):
        mode = "active"

    # Single TradeLog read for the whole render -- avoids re-reading trades.json
    # separately for get_stats(), get_extended_stats(), and the trade lists.
    tl = _trades()
    all_raw = tl.get_trades(status=None, limit=None, sort_by="opened_at")

    if mode == "today":
        scoped_trades = [
            t for t in all_raw
            if _is_today_berlin(t.get("opened_at")) or _is_today_berlin(t.get("closed_at"))
        ]
    elif mode == "active":
        scoped_trades = [
            t for t in all_raw
            if t["status"] == "open"
            or _is_today_berlin(t.get("opened_at"))
            or _is_today_berlin(t.get("closed_at"))
        ]
    else:
        scoped_trades = None  # None -> get_stats()/get_extended_stats() use the full trade set

    if mode in ("today", "active"):
        open_trades = sorted(
            [t for t in scoped_trades if t["status"] == "open"],
            key=lambda t: (t.get("confidence_level") or 0, t.get("confidence_score") or 0),
            reverse=True,
        )
    else:
        open_trades = tl.get_trades(status="open", limit=None, sort_by="confidence")

    stats = tl.get_stats(trades=scoped_trades)
    stats.update(tl.get_extended_stats(trades=scoped_trades))
    # Day/hour/minute label for the "Avg holding period" stat card, same
    # granularity as every other holding-period display on this page (Open
    # Trades' Days column, Trade History's Days column) -- avg_holding_days
    # alone as "%.1f d" collapsed anything under a day down to "0.0 d",
    # which is a less useful reading than "18 hours 24 minutes".
    stats["avg_holding_label"] = (
        _format_duration_hms(stats["avg_holding_days"] * 86400)
        if stats.get("avg_holding_days") is not None else None
    )

    # Closed trades -- built early so their tickers are included in cur_map
    # below. Deliberately NOT scoped to the dashboard mode -- this feeds the
    # "Trade history" browser table further down the page, which is its own
    # general trade log with its own ticker/strategy/horizon/outcome filter
    # dropdowns. Scoping it to "today" or "active" mode would starve the
    # table down to whatever handful of trades closed today -- often just
    # one or two, or none. The mode toggle only affects the KPI stat cards
    # and the open-trades table above.
    #
    # all_closed_trades is the FULL, unbounded history -- used to build the
    # filter dropdowns' option lists (closed_trade_filter_options below) from
    # the COMPLETE history, not just whatever rows end up in the table. The
    # table itself (closed_trades) is then sliced down to the most recent 25
    # for actual display -- that row limit and the filter options are two
    # different concerns and shouldn't share one data source (they used to,
    # which meant any ticker/strategy/horizon that only appeared in an older,
    # 26th+ closed trade could never be selected in the dropdowns even though
    # it's a perfectly real filterable value).
    all_closed_trades = [t for t in all_raw if t["status"] in ("win", "loss", "closed")]
    closed_trades_total = len(all_closed_trades)
    closed_trades = sorted(
        all_closed_trades,
        key=lambda t: t.get("closed_at") or "",
        reverse=True,
    )[:CLOSED_TRADES_FRAGMENT_LIMIT]
    closed_trades_truncated = closed_trades_total > CLOSED_TRADES_FRAGMENT_LIMIT

    # Currency symbol map -- covers every ticker shown on the page (open AND
    # recently closed). Previously only open_trades were included, so closed
    # trades for tickers without a current open position showed no symbol.
    all_tickers = {t["ticker"] for t in open_trades + closed_trades}
    cur_map     = {tk: get_currency_symbol(tk, config.CURRENCY_SYMBOL) for tk in all_tickers}

    # Ticker/strategy/horizon options for the Trade History filter dropdowns.
    closed_trade_filter_options = {
        "ticker":   sorted({t["ticker"] for t in all_closed_trades if t.get("ticker")}),
        "strategy": sorted({_primary_strategy_label(t) for t in all_closed_trades}),
        "horizon":  sorted({t.get("horizon_key") for t in all_closed_trades if t.get("horizon_key")}),
    }

    # Account config for position sizing (guaranteed to have all keys via
    # load_account_config's {**defaults, **stored} merge).
    account_cfg = load_account_config()

    # "What does a trade actually cost right now" note for the dashboard --
    # answers the recurring question of why unrealized P&L on open positions
    # doesn't match a naive "balance x position %" guess. In Account % mode
    # the premium IS that exact fixed number every time. In Risk % mode
    # (the default) there is no single fixed premium -- position value varies
    # per trade with how far away its stop is, up to the Max position size %
    # cap -- so we surface the worked-out range instead of a single figure.
    #
    # Every figure here is ALSO run through the two absolute $ caps
    # (max_position_value_absolute / max_risk_amount_absolute -- see
    # compute_position_size()'s docstring in core/account.py) the same way
    # compute_position_size() itself does, taking whichever cap is tighter.
    # This card used to only apply the %-based caps, so once the absolute
    # caps were introduced it could show a stale, much larger "up to" figure
    # than any trade could actually reach -- e.g. balance x max_position_pct
    # coming out to $50,000 while every real trade was actually being capped
    # at the $1,000 absolute limit under the hood.
    #
    # Note this reflects TODAY's settings only: any trade opened under a
    # different balance/risk/mode has its own shares snapshotted at open time
    # (see account.py's module docstring) and won't retroactively match this.
    _sizing_balance = float(account_cfg.get("balance", 0))
    _max_pos_abs = float(account_cfg.get("max_position_value_absolute", 0) or 0)
    _max_risk_abs = float(account_cfg.get("max_risk_amount_absolute", 0) or 0)
    if account_cfg.get("sizing_mode") == "account_pct":
        _premium = _sizing_balance * float(account_cfg.get("position_pct", 0)) / 100.0
        _premium = min(_premium, _sizing_balance * float(account_cfg.get("max_position_pct", 0)) / 100.0) \
            if account_cfg.get("max_position_pct") else _premium
        if _max_pos_abs > 0:
            _premium = min(_premium, _max_pos_abs)
        sizing_note = {
            "mode": "account_pct",
            "premium": round(_premium, 2),
            "position_pct": account_cfg.get("position_pct", 0),
        }
    else:
        _risk_amount = _sizing_balance * float(account_cfg.get("risk_pct", 0)) / 100.0
        if _max_risk_abs > 0:
            _risk_amount = min(_risk_amount, _max_risk_abs)
        _max_position = _sizing_balance * float(account_cfg.get("max_position_pct", 0)) / 100.0
        if _max_pos_abs > 0:
            _max_position = min(_max_position, _max_pos_abs)
        sizing_note = {
            "mode": "risk_pct",
            "risk_amount": round(_risk_amount, 2),
            "risk_pct": account_cfg.get("risk_pct", 0),
            "max_position": round(_max_position, 2),
            "max_position_pct": account_cfg.get("max_position_pct", 0),
            "max_position_value_absolute": _max_pos_abs,
            "max_risk_amount_absolute": _max_risk_abs,
        }

    # Per-trade strategy label (reuses chart ranking so dashboard + chart agree).
    # Covers open_trades AND all_closed_trades (not just open_trades) -- the
    # Trade History table below looks up this same map for its Strategy
    # column, and needs the identical recomputed label that was shown while
    # the trade was still open, not the raw t["strategy"] field (which is
    # always the same hardcoded default -- see primary_strategy_label's
    # docstring in core/performance.py). Previously this map only covered
    # open_trades, so every closed-trade lookup missed and silently fell back
    # to that one hardcoded string for every row.
    strategy_map = {t["id"]: _primary_strategy_label(t) for t in open_trades + all_closed_trades}

    # ── Single pass over open trades ─────────────────────────────────────────
    # Computes prices, status colors, P&L, SL/TP progress, position bar,
    # days-open, and sizing all in one loop instead of the previous two
    # (price/status then pnl/days) plus a separate sizing loop.
    status_map    : dict = {}
    price_map     : dict = {}
    pnl_map       : dict = {}
    days_map      : dict = {}
    sizing_map    : dict = {}
    unrealized_pnls: list = []
    now_utc = datetime.now(timezone.utc)

    # Fetch all prices concurrently so the loop below hits the in-memory
    # cache and never blocks on a sequential network call per ticker.
    prefetch_prices([t["ticker"] for t in open_trades])

    for t in open_trades:
        tid     = t["id"]
        price   = get_current_price(t["ticker"])
        entry   = t.get("entry")    or 0.0
        sl      = t.get("stop_loss")  or 0.0
        tp      = t.get("take_profit") or 0.0
        is_bull = t.get("direction") == "bullish"

        price_map[tid] = price

        # Status dot color/speed
        if price is None:
            status_map[tid] = {
                "color": "#5a6275", "proximity": 0.0,
                "blink_seconds": 2.2, "label": "Price unavailable",
            }
        else:
            status_map[tid] = trade_proximity(t["direction"], entry, sl, tp, price)

        # Time open -- shown as hours while under a day old, then "N day(s) M
        # hours" once it crosses 24h, instead of a coarse whole-calendar-days
        # count that reads as "0" for anything opened today regardless of
        # whether that was 10 minutes or 23 hours ago.
        try:
            elapsed = now_utc - datetime.fromisoformat(t["opened_at"])
            total_hours = max(0, elapsed.total_seconds() / 3600.0)
            days_map[tid] = {
                "days": int(total_hours // 24),          # whole calendar days, for the >30-day aging color
                "total_hours": total_hours,               # for sorting
                "label": _format_open_duration(total_hours),
            }
        except Exception:
            days_map[tid] = None

        # P&L, SL/TP progress, position bar
        if price and entry:
            raw_pnl = (price - entry) / entry * 100
            pnl_pct = raw_pnl if is_bull else -raw_pnl
            unrealized_pnls.append(pnl_pct)

            # Progress toward each level from entry (0% = at entry, 100% = at
            # level, >100% = past it). Clamped to 0 when price moved AWAY.
            sl_dist = abs(entry - sl) or 1.0
            tp_dist = abs(tp - entry) or 1.0
            if is_bull:
                sl_raw = (entry - price) / sl_dist * 100
                tp_raw = (price - entry) / tp_dist * 100
            else:
                sl_raw = (price - entry) / sl_dist * 100
                tp_raw = (entry - price) / tp_dist * 100

            # Position bar: SL = 0%, TP = 100%
            span = (tp - sl) if is_bull else (sl - tp)
            if span > 0:
                cur_pos   = (price - sl) / span * 100 if is_bull else (sl - price) / span * 100
                entry_pos = (entry - sl) / span * 100 if is_bull else (sl - entry) / span * 100
            else:
                cur_pos = entry_pos = 50.0

            _p   = max(0.0, min(100.0, round(cur_pos, 1)))
            _ep  = max(0.0, min(100.0, round(entry_pos, 1)))
            pnl_map[tid] = {
                "pnl_pct":   round(pnl_pct, 2),
                "to_sl_pct": round(max(0.0, sl_raw), 1),
                "to_tp_pct": round(max(0.0, tp_raw), 1),
                "pos_pct":   _p,
                "entry_pct": _ep,
                "pos_color": _pos_color(_p, _ep),
            }
        else:
            pnl_map[tid] = None

        # Position sizing
        sizing_map[tid] = compute_position_size(entry=entry, stop_loss=sl, account_cfg=account_cfg)

    # Equal-weighted average unrealized return across all open positions with a
    # live price (None → shown as "—" in the stat card).
    stats["total_unrealized_pct"] = (
        sum(unrealized_pnls) / len(unrealized_pnls) if unrealized_pnls else None
    )

    # ── Closed-trade P&L helpers (passed as callables to Jinja) ──────────────
    def _closed_pnl(t) -> float | None:
        ex, en = t.get("exit_price"), t.get("entry")
        if not ex or not en:
            return None
        raw = (ex - en) / en * 100
        return round(raw if t["direction"] == "bullish" else -raw, 2)

    def _closed_r(t) -> float | None:
        ex, en, sl_v = t.get("exit_price"), t.get("entry"), t.get("stop_loss")
        if not ex or not en or not sl_v:
            return None
        risk = abs(en - sl_v)
        if not risk:
            return None
        realized = (ex - en) if t["direction"] == "bullish" else (en - ex)
        return round(realized / risk, 2)

    def _closed_days(t) -> dict | None:
        """Returns {label, total_hours} -- the full day/hour/minute holding
        period label (see _format_duration_hms) plus a raw sortable figure,
        for the Trade History table's Days column."""
        try:
            elapsed = (
                datetime.fromisoformat(t["closed_at"]) -
                datetime.fromisoformat(t["opened_at"])
            )
            total_seconds = max(0.0, elapsed.total_seconds())
            return {
                "label": _format_duration_hms(total_seconds),
                "total_hours": total_seconds / 3600.0,
            }
        except Exception:
            return None

    realized_pnls = [p for p in (_closed_pnl(t) for t in closed_trades) if p is not None]
    stats["total_realized_pct"] = round(sum(realized_pnls) / len(realized_pnls), 2) if realized_pnls else None
    stats["best_trade_pct"]     = round(max(realized_pnls), 2) if realized_pnls else None
    stats["worst_trade_pct"]    = round(min(realized_pnls), 2) if realized_pnls else None

    # Account balance + today's movement -- recomputed on every fragment
    # render, so with the dashboard's existing auto-refresh poll this stat
    # card updates on its own the moment a trade closes and settles into
    # the account balance (see performance.py's _settle_account_balance),
    # with no extra JS/websocket plumbing needed.
    stats["account"] = get_daily_summary()

    # Local import -- pages.py does `from .app import _render, require_auth`
    # at its own top, so a module-level import here would deadlock on the
    # circular reference. Both modules are fully loaded by request time.
    from .pages import _plan_rows, _sparkline_svg

    plan_counts = _plan_rows()["counts"]

    # Equity (30d) sparkline. snap["equity_curve"] is {"points": [...],
    # "skipped_n": ...} (see metrics.equity_curve), not a bare list -- each
    # point's balance key is "date"/"balance", not "ts"/"balance". Balances
    # are raw account-currency figures (e.g. 10000+), not the 0-100 scale
    # _sparkline_svg assumes (it's shared with the win-rate sparkline), so
    # they're min-max normalized to 0-100 purely for the sparkline's shape;
    # the headline number below still shows the real current balance.
    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    equity_points_raw = [
        p["balance"] for p in ((snap or {}).get("equity_curve") or {}).get("points", [])[-30:]
    ]
    if equity_points_raw:
        lo, hi = min(equity_points_raw), max(equity_points_raw)
        span = hi - lo
        equity_points = [(v - lo) / span * 100.0 if span else 50.0 for v in equity_points_raw]
        equity_sparkline_svg = _sparkline_svg(equity_points, ref=None)
    else:
        equity_sparkline_svg = "&mdash;"

    return render_template(
        "dashboard_fragment.html",
        open_trades=open_trades, stats=stats, confidence_hex=_confidence_hex,
        cur_map=cur_map, status_map=status_map, strategy_map=strategy_map,
        price_map=price_map, pnl_map=pnl_map, days_map=days_map,
        sizing_map=sizing_map, account_cfg=account_cfg, sizing_note=sizing_note,
        closed_trades=closed_trades, closed_trade_filter_options=closed_trade_filter_options,
        closed_trades_total=closed_trades_total, closed_trades_truncated=closed_trades_truncated,
        trade_pnl=_closed_pnl, trade_r=_closed_r, trade_days=_closed_days,
        is_market_active=is_us_market_active(),
        dashboard_mode=mode,
        plan_counts=plan_counts, equity_sparkline_svg=equity_sparkline_svg,
    )


@app.route("/", methods=["GET"])
@require_auth
def index():
    return _render(
        "Dashboard", "dashboard", "dashboard.html",
        fragment=_render_dashboard_fragment(),
        dashboard_refresh_seconds=config.DASHBOARD_REFRESH_SECONDS,
        dashboard_mode=request.args.get("mode", "active"),
    )


@app.route("/dashboard/fragment", methods=["GET"])
@require_auth
def dashboard_fragment():
    """
    Just the open-trades table + stats, re-rendered fresh from
    trades.json. Polled by the dashboard's own JS every few seconds so a
    trade logged by `!check` (or the background scan) shows up without
    a manual browser refresh -- the admin process is separate from the
    bot process, so nothing pushes it a notification; it has to ask.

    ETag'd on the rendered HTML's sha1: when nothing has actually changed
    since the browser's last poll (the common case -- most 5s ticks see
    no new trade), the response is a 5-byte "304 Not Modified" instead of
    the full fragment, which on a page auto-refreshing indefinitely adds
    up to a meaningful bandwidth/CPU (Jinja render) saving over a session.
    """
    html = _render_dashboard_fragment()
    etag = hashlib.sha1(html.encode("utf-8")).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.headers["ETag"] = etag
    return resp


@app.route("/trades/clear-open", methods=["POST"])
@require_auth
def clear_open_trades():
    removed = _trades().clear_open()
    msg = f"Cleared {removed} open trade(s). Closed win/loss history was left untouched."
    return redirect(url_for("index", msg=msg, ok=1))


@app.route("/trades/history/clear", methods=["POST"])
@require_auth
def clear_trade_history():
    removed = _trades().clear_history()
    msg = f"Cleared {removed} closed trade record(s). Open trades were left untouched."
    return redirect(url_for("index", msg=msg, ok=1))


@app.route("/trades/<trade_id>/delete", methods=["POST"])
@require_auth
def delete_single_trade(trade_id):
    deleted = _trades().delete_trade(trade_id)
    if deleted:
        return redirect(url_for("index", msg=f"Trade {trade_id} deleted.", ok=1))
    return redirect(url_for("index", msg=f"Trade {trade_id} not found.", ok=0))


# ---------------------------------------------------------------------------
# Routes -- Risk panel (Task E54). Stands alone off the existing admin nav
# (no dashboard-card dependency): open heat vs cap, sector heat bars,
# drawdown throttle multiplier, and the manual-release-only kill switch
# (swingbot.core.edge.throttle) surfaced as a toggle. Reuses
# _collect_portfolio_state (E52's !portfolio dashboard collector) so this
# page and the Discord command always agree on the numbers.
# ---------------------------------------------------------------------------
@app.route("/risk")
@require_auth
def risk_panel():
    from swingbot.commands.growth import _collect_portfolio_state
    from swingbot.core.scanning.engine import recent_telemetry, scan_slowdown
    from swingbot.admin.helpers import scan_duration_sparkline

    # Scan health (Task E82): best-effort, same degrade-not-crash treatment
    # as every other _collect_portfolio_state sub-collector on this page.
    try:
        durations = [r["duration_s"] for r in recent_telemetry(50) if "duration_s" in r]
        slowdown = scan_slowdown()
    except Exception:
        durations, slowdown = [], False

    return _render("Portfolio Risk", "risk", "risk.html", state=_collect_portfolio_state(),
                  scan_sparkline=scan_duration_sparkline(durations),
                  scan_latest=durations[-1] if durations else None,
                  scan_slowdown=slowdown)


@app.route("/risk/killswitch", methods=["POST"])
@require_auth
def risk_killswitch():
    from swingbot.core.edge import throttle
    throttle.set_kill(request.form.get("action") == "on", reason="admin panel")
    return redirect(url_for("risk_panel"))


# ---------------------------------------------------------------------------
# Routes -- Settings
# ---------------------------------------------------------------------------
@app.route("/settings", methods=["GET"])
@require_auth
def settings_page():
    env_values = _read_env_values()
    restart_available = docker_sdk is not None
    return _render(
        "Settings", "settings", "settings.html",
        fields_by_section=FIELDS_BY_SECTION,
        field_value=lambda f: _field_display_value(f, env_values),
        restart_available=restart_available,
        section_meta=_SECTION_META,
        settings_audit=read_settings_audit(20),
    )


@app.route("/settings/preview", methods=["POST"])
@require_auth
def settings_preview():
    existing = _read_env_values()
    diff = settings_diff(request.form, existing)
    return render_template("_settings_diff.html", diff=diff)


@app.route("/settings/save", methods=["POST"])
@require_auth
def save_settings():
    existing = _read_env_values()
    diff = settings_diff(request.form, existing)
    restart_needed_for = _changed_non_hot_reloadable_fields(existing, request.form)

    new_text = _build_env_text(request.form, existing)
    _write_env_text(new_text)
    append_settings_audit(diff)

    success, message = _hot_reload_bot_container()
    if restart_needed_for:
        names = ", ".join(restart_needed_for)
        message += f" Note: {names} won't take effect until the bot container is actually restarted (see field help text)."
    return redirect(url_for("settings_page", msg=message, ok=1 if success else 0))


@app.route("/settings/export", methods=["GET"])
@require_auth
def settings_export():
    existing = _read_env_values()
    lines = []
    for f in config.FIELDS:
        if f.sensitive:
            continue  # omitted entirely, not masked -- an import must never accidentally blank a real secret
        lines.append(f"{f.key}={existing.get(f.key, f.default)}")
    body = "\n".join(lines) + "\n"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        body, mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=swingbot-settings-{today}.env"},
    )


@app.route("/settings/import", methods=["POST"])
@require_auth
def settings_import():
    text = request.form.get("env_text", "")
    upload = request.files.get("env_file")
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
    applied_count, unknown_keys = import_env_text(text)
    msg = f"Imported {applied_count} setting(s)."
    if unknown_keys:
        msg += f" Unknown keys skipped: {', '.join(unknown_keys[:10])}."
    return redirect(url_for("settings_page", msg=msg, ok=1))


@app.route("/bot/restart", methods=["POST"])
@require_auth
def restart_bot():
    success, message = _restart_bot_container()
    # Redirects back to wherever the restart button was actually clicked from
    # (Settings originally; now also Logs, for a "hard reload" button right
    # next to the log stream that's usually what you're staring at when a
    # restart is actually needed) instead of always landing on Settings.
    next_page = request.form.get("next", "settings")
    if next_page == "logs":
        return redirect(url_for(
            "logs_page", msg=message, ok=1 if success else 0,
            lines=request.form.get("lines", 500), source=request.form.get("source", "bot"),
        ))
    return redirect(url_for("settings_page", msg=message, ok=1 if success else 0))


# ---------------------------------------------------------------------------
# Routes -- Logs
# ---------------------------------------------------------------------------
@app.route("/logs", methods=["GET"])
@require_auth
def logs_page():
    try:
        lines = int(request.args.get("lines", 500))
    except ValueError:
        lines = 500
    lines = max(1, min(lines, 5000))
    source = request.args.get("source", "bot")  # "bot" or "admin"
    if source == "admin":
        log_content = _tail_admin_log(lines)
        log_path = config.ADMIN_LOG_FILE
    else:
        source = "bot"
        log_content = _tail_log(lines)
        log_path = config.LOG_FILE
    return _render(
        "Logs", "logs", "logs.html",
        log_content=log_content, lines=lines, log_path=log_path,
        log_source=source, logs_refresh_seconds=config.LOGS_REFRESH_SECONDS,
        restart_available=docker_sdk is not None,
    )


@app.route("/logs/clear", methods=["POST"])
@require_auth
def logs_clear():
    source = request.args.get("source", "bot")
    if source == "admin":
        success, message = _clear_admin_log()
    else:
        source = "bot"
        success, message = _clear_log()
    return redirect(url_for("logs_page", msg=message, ok=1 if success else 0, source=source))


@app.route("/logs/raw", methods=["GET"])
@require_auth
def logs_raw():
    try:
        lines = int(request.args.get("lines", 500))
    except ValueError:
        lines = 500
    lines = max(1, min(lines, 5000))
    source = request.args.get("source", "bot")
    content = _tail_admin_log(lines) if source == "admin" else _tail_log(lines)
    return Response(content, mimetype="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# Routes -- trade detail
# ---------------------------------------------------------------------------
@app.route("/trades/<trade_id>", methods=["GET"])
@require_auth
def trade_detail(trade_id):
    t = _trades().get_trade_by_id(trade_id)
    if not t:
        abort(404, f"No trade found with id '{trade_id}'.")

    is_bull = t["direction"] == "bullish"
    cur = get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL)
    level_word = "Resistance" if is_bull else "Support"
    opposite_word = "Support" if is_bull else "Resistance"

    return _render(
        f"{t['ticker']} — Trade {t['id']}", "dashboard", "trade_detail.html",
        t=t, cur=cur, is_bull=is_bull, level_word=level_word, opposite_word=opposite_word,
        confidence_hex=_confidence_hex(t.get("confidence_level", 0)),
        sources_str=_sources_str,
        has_detail=bool(t.get("explanation") or t.get("target_sources")),
    )


@app.route("/trades/<trade_id>/chart.png", methods=["GET"])
@require_auth
def trade_chart_image(trade_id):
    t = _trades().get_trade_by_id(trade_id)
    if not t:
        abort(404)
    path = regenerate_chart_for_trade(t)
    if not path:
        abort(404, "Could not generate a chart for this trade right now (data fetch may have failed).")

    resp = send_file(path, mimetype="image/png")
    if t["status"] == "open":
        # An open trade's chart can change on every single refresh (price
        # moves, new bars) -- never let the browser reuse a stale copy.
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # Closed trades are deterministic -- the same trade_id always
    # regenerates the identical chart (entry/stop/target/outcome are all
    # frozen), so it's safe to let the browser cache it for a day and skip
    # regenerating the image (a real matplotlib render, not free) on every
    # repeat view of the same trade's detail page.
    resp.headers["Cache-Control"] = "private, max-age=86400"
    try:
        mtime = os.path.getmtime(path)
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
        resp.headers["Last-Modified"] = last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
        ims = request.headers.get("If-Modified-Since")
        if ims:
            ims_dt = datetime.strptime(ims, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
            if last_modified <= ims_dt:
                return Response(status=304)
    except (OSError, ValueError):
        pass
    return resp


@app.route("/trades/<trade_id>/close", methods=["POST"])
@require_auth
def close_trade(trade_id):
    tl = _trades()
    t = tl.get_trade_by_id(trade_id)
    if not t:
        abort(404, f"No trade found with id '{trade_id}'.")
    if t["status"] != "open":
        return redirect(url_for("index", msg="Trade is already closed.", ok=0))
    # Mark as manually closed (no exit price — just status change). Goes
    # through TradeLog's own locked mutator (same one every other writer
    # uses) instead of poking tl._trades directly -- the admin UI and the
    # bot's scan loop are separate processes sharing the same trades.json,
    # so an unlocked read-modify-write here could race a concurrent write
    # from the bot and corrupt or lose data.
    tl.close_trade_manual(trade_id, reason="manual (admin UI)")

    # Queue a Discord notification so the bot posts to DISCORD_CHANNEL_TRADES_HISTORY_ID.
    # The admin UI and bot run in separate processes; we share data via a JSON
    # queue file, same pattern as the scan-trigger flag.
    try:
        # Re-read the trade after closing so we get the updated closed_at / status
        closed_t = tl.get_trade_by_id(trade_id) or {}
        if closed_t:
            existing: list = []
            if os.path.exists(MANUAL_CLOSE_QUEUE):
                try:
                    with open(MANUAL_CLOSE_QUEUE, "r") as _qf:
                        existing = json.load(_qf)
                except Exception:
                    existing = []
            existing.append(closed_t)
            with open(MANUAL_CLOSE_QUEUE, "w") as _qf:
                json.dump(existing, _qf)
    except Exception as _qe:
        log.warning("Could not queue manual-close notification for %s: %s", trade_id, _qe)

    return redirect(url_for("index", msg=f"Trade {t['ticker']} marked as closed.", ok=1))


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


@app.route("/api/ohlcv/<ticker>", methods=["GET"])
def api_ohlcv(ticker):
    """Daily OHLCV bars for the interactive chart (U29's JS). Read-only,
    capped at 1000 bars, defaults to 260 (~1y of trading days).

    Auth is checked inline here rather than via the module's `require_auth`
    decorator: that one redirects an unauthenticated request to the HTML
    /login page (302), which is the right UX for a browser hitting a page
    but wrong for a JSON endpoint a fetch() call hits directly -- it needs
    a bare 401 it can branch on, same contract as api.py's
    `require_auth_json` (not reused directly: that module imports
    ADMIN_USERNAME/ADMIN_PASSWORD by value at its own import time, so it
    goes stale under this test module's ADMIN_USERNAME/PASSWORD
    monkeypatching -- this route reads this module's own live globals
    instead, the same ones `require_auth` and `login_submit` check)."""
    if not _session_authenticated():
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return Response(json.dumps({"error": "auth"}), status=401, mimetype="application/json")
    ticker = ticker.upper()
    try:
        bars = max(1, min(int(request.args.get("bars", 260)), 1000))
    except ValueError:
        bars = 260
    df = _ohlcv_frame(ticker)
    if df is None or not len(df):
        return Response(json.dumps({"error": "no data"}), status=404, mimetype="application/json")
    df = df.tail(bars)
    trade_id = request.args.get("trade_id")
    levels = None
    if trade_id:
        t = _trade_for_levels(trade_id)
        if t:
            levels = {"entry": t.get("entry"), "stop_loss": t.get("stop_loss"),
                      "tp1": t.get("take_profit"), "tp2": t.get("target2_price"),
                      "direction": t.get("direction")}
    payload = {
        "ticker": ticker,
        "bars": [
            {"time": idx.strftime("%Y-%m-%d"), "open": round(float(r["Open"]), 4),
             "high": round(float(r["High"]), 4), "low": round(float(r["Low"]), 4),
             "close": round(float(r["Close"]), 4), "volume": float(r["Volume"])}
            for idx, r in df.iterrows()
        ],
    }
    if levels is not None:
        payload["levels"] = levels
    return Response(json.dumps(payload), mimetype="application/json")


@app.route("/trades/export.csv", methods=["GET"])
@require_auth
def export_trades_csv():
    all_trades = _trades().get_trades(status=None, limit=None)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "ticker", "strategy", "horizon_key", "direction",
        "confidence_level", "confidence_label", "confidence_score",
        "entry", "stop_loss", "take_profit", "target2", "risk_reward_ratio",
        "status", "opened_at", "closed_at", "exit_price", "close_reason",
    ], extrasaction="ignore")
    writer.writeheader()
    for t in (all_trades or []):
        writer.writerow(t)
    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )


# ---------------------------------------------------------------------------
# Routes -- Watchlist
# ---------------------------------------------------------------------------
@app.route("/watchlist", methods=["GET"])
@require_auth
def watchlist_page():
    tickers = load_watchlist()
    # Build per-ticker trade stats -- one read of trades.json (get_trades()
    # re-reads the file from disk every call, see TradeLog.refresh()) instead
    # of one per ticker. With a long watchlist this used to mean dozens of
    # redundant full-file reads+parses on every single page load.
    tl = _trades()
    all_trades = tl.get_trades(status=None, limit=None) or []
    trade_counts = {ticker: {"open": 0, "closed": 0} for ticker in tickers}
    for tr in all_trades:
        counts = trade_counts.get(tr["ticker"])
        if counts is None:
            continue  # trade on a ticker no longer in the watchlist
        counts["open" if tr["status"] == "open" else "closed"] += 1
    # Real company names -- fetched concurrently so yfinance fallbacks for
    # international tickers don't stall the page load sequentially.
    # US-listed tickers are resolved from the local NASDAQ/NYSE directory
    # instantly; only OTC/international symbols hit the network.
    company_names: dict[str, str | None] = {}
    with ThreadPoolExecutor(max_workers=min(10, len(tickers) or 1)) as pool:
        futures = {pool.submit(get_company_name, tk): tk for tk in tickers}
        for fut in as_completed(futures):
            tk = futures[fut]
            try:
                company_names[tk] = fut.result()
            except Exception:
                company_names[tk] = None
    return _render(
        "Watchlist", "watchlist", "watchlist.html",
        tickers=tickers,
        trade_counts=trade_counts,
        company_names=company_names,
    )


@app.route("/watchlist/suggest", methods=["GET"])
@require_auth
def watchlist_suggest():
    """
    Ticker autocomplete for the Add-ticker field -- backed by the cached
    NASDAQ + NYSE/AMEX symbol directory (see core/ticker_directory.py),
    not a live network call per keystroke. Returns a small JSON list of
    {symbol, name} matches for whatever's been typed so far.
    """
    q = request.args.get("q", "")
    return Response(json.dumps(search_tickers(q)), mimetype="application/json")


@app.route("/watchlist/add", methods=["POST"])
@require_auth
def watchlist_add():
    ticker = request.form.get("ticker", "").strip().upper()
    if not ticker:
        return redirect(url_for("watchlist_page", msg="Ticker cannot be empty.", ok=0))
    if len(ticker) > 10 or not ticker.replace(".", "").replace("-", "").isalnum():
        return redirect(url_for("watchlist_page", msg=f"'{ticker}' doesn't look like a valid ticker symbol.", ok=0))
    updated = add_ticker(ticker)
    if ticker in updated:
        ensure_cached_background(ticker)  # non-blocking full-history download
        return redirect(url_for("watchlist_page", msg=f"Added {ticker} to watchlist ({len(updated)} tickers total).", ok=1))
    return redirect(url_for("watchlist_page", msg=f"{ticker} is already in the watchlist.", ok=1))


@app.route("/watchlist/bulk_add", methods=["POST"])
@require_auth
def watchlist_bulk_add():
    """
    Adds many tickers at once from a pasted list (comma/space/newline
    separated) -- mainly a disaster-recovery tool: data/watchlist.json is
    plain app-managed data (not tracked in git, see .gitignore), so it's
    never touched by a `git reset --hard` deploy, but if it's ever lost or
    needs rebuilding from scratch (a fresh server, a manual mistake), typing
    dozens of tickers into the single-ticker "+ Add" box one at a time would
    be painful. This is the same add_ticker() used by the single-add form
    and `!watchlist add`, just called once per pasted symbol.
    """
    raw = request.form.get("tickers", "")
    candidates = [t.strip().upper() for t in re.split(r"[,\s]+", raw) if t.strip()]
    existing_before = set(load_watchlist())

    valid, invalid = [], []
    for ticker in candidates:
        if len(ticker) > 10 or not ticker.replace(".", "").replace("-", "").replace("=", "").isalnum():
            invalid.append(ticker)
        else:
            valid.append(ticker)

    final_list = existing_before
    for ticker in valid:
        final_list = set(add_ticker(ticker))

    newly_added = [t for t in valid if t not in existing_before]
    already_had = [t for t in valid if t in existing_before]

    # Non-blocking full-history download for each newly added ticker; already
    # cached ones return instantly, so re-imports don't refetch.
    for ticker in newly_added:
        ensure_cached_background(ticker)

    parts = []
    if newly_added:
        parts.append(f"{len(newly_added)} added")
    if already_had:
        parts.append(f"{len(already_had)} already present")
    if invalid:
        shown = ', '.join(invalid[:10]) + ('…' if len(invalid) > 10 else '')
        parts.append(f"{len(invalid)} skipped (invalid: {shown})")
    msg = f"Bulk add: {', '.join(parts) if parts else 'nothing to add'} -- {len(final_list)} tickers total."
    return redirect(url_for("watchlist_page", msg=msg, ok=1 if not invalid else 0))


@app.route("/watchlist/remove", methods=["POST"])
@require_auth
def watchlist_remove():
    ticker = request.form.get("ticker", "").strip().upper()
    if not ticker:
        return redirect(url_for("watchlist_page", msg="No ticker specified.", ok=0))
    updated = remove_ticker(ticker)
    return redirect(url_for("watchlist_page", msg=f"Removed {ticker} ({len(updated)} tickers remaining).", ok=1))


# ---------------------------------------------------------------------------
# Routes -- Scan trigger
# ---------------------------------------------------------------------------
@app.route("/scan/trigger", methods=["POST"])
@require_auth
def trigger_scan():
    """Write a trigger file that the bot's config_watcher picks up within 30s."""
    payload = json.dumps({
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "source": "admin_ui",
    })
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(TRIGGER_FILE, "w") as f:
            f.write(payload)
        msg = "Scan queued — the bot will pick it up within 30 seconds and post results to Discord."
        ok = 1
    except Exception as e:
        msg = f"Could not write trigger file: {e}"
        ok = 0
    return redirect(url_for("index", msg=msg, ok=ok))


@app.route("/scan/stop", methods=["POST"])
@require_auth
def stop_scan():
    """Ask the bot to stop whatever scan is currently running. Cooperative --
    takes effect at the scan's next per-ticker checkpoint, not instantly
    (see scan_engine.request_stop()). Different from pause: pause stops
    future automatic scans; this cuts short one already in progress."""
    try:
        request_stop()
        msg = "Stop requested — the running scan will end after finishing its current ticker."
        ok = 1
    except Exception as e:
        msg = f"Could not request stop: {e}"
        ok = 0
    return redirect(url_for("index", msg=msg, ok=ok))


@app.route("/scan/status", methods=["GET"])
@require_auth
def scan_status():
    """Return JSON indicating whether a scan trigger is pending, whether
    the automatic background scan loop is currently paused, whether a
    scan is actively running right now, and whether the bot process
    itself appears to be alive (based on the heartbeat file written by
    session_scan on every tick -- see scanning.py)."""
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

    return Response(
        json.dumps({
            "pending": pending, "triggered_at": mtime, "paused": paused, "paused_at": paused_at,
            "running": running,
            "bot_alive": bot_alive,
            "bot_last_seen": bot_last_seen,
            "bot_session_active": bot_session_active,
            "bot_scan_paused": bot_scan_paused,
        }),
        mimetype="application/json",
    )


@app.route("/scan/pause", methods=["POST"])
@require_auth
def pause_scan():
    """Pause the automatic background scan loop (checked by session_scan
    in commands/scanning.py). Manual !c    in commands/scanning.py). Manual !check / "Run !check now" still work
    while paused -- this only stops the unattended scheduled scanning."""
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(PAUSE_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        msg = "Automatic scanning paused. Manual \"Run !check now\" and Discord's !check still work."
        ok = 1
    except Exception as e:
        msg = f"Could not write pause file: {e}"
        ok = 0
    return redirect(url_for("index", msg=msg, ok=ok))


@app.route("/scan/resume", methods=["POST"])
@require_auth
def resume_scan():
    """Resume the automatic background scan loop after a pause."""
    try:
        if os.path.exists(PAUSE_FILE):
            os.remove(PAUSE_FILE)
        msg = "Automatic scanning resumed."
        ok = 1
    except Exception as e:
        msg = f"Could not remove pause file: {e}"
        ok = 0
    return redirect(url_for("index", msg=msg, ok=ok))


@app.route("/performance", methods=["GET"])
@require_auth
def stats_page():
    tl = _trades()
    stats = tl.get_detailed_stats()
    chart_data_json = json.dumps(tl.get_chart_data())

    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    calibration = (snap or {}).get("calibration", {})
    calibration_chart_json = json.dumps({"deciles": calibration.get("deciles", [])})

    # Local import -- same circularity reasoning as _render_dashboard_fragment
    # above (pages.py imports FROM app.py at its own top).
    from .pages import _heatmap_color, _strategy_horizon_heatmap
    heatmap = _strategy_horizon_heatmap()

    return _render(
        "Performance", "stats", "stats.html", stats=stats, chart_data_json=chart_data_json,
        tiers=calibration.get("tiers", []), drift=calibration.get("drift", []),
        heatmap=heatmap, heatmap_color=_heatmap_color, calibration_chart_json=calibration_chart_json,
    )



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
from . import api as _api  # noqa: E402
app.register_blueprint(_api.api)
from . import pages as _pages  # noqa: E402
app.register_blueprint(_pages.pages)
