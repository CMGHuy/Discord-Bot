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
VPN, or just on localhost) -- it's protected by a single HTTP Basic Auth
username/password from the environment, not a full user/permissions
system. Don't expose it to the open internet without putting a reverse
proxy with real auth in front of it.

Page markup lives in templates/*.html (Flask's standard auto-discovered
templates/ folder next to this module) rather than inline Python string
constants -- keeps this file to routes/logic only and lets the HTML be
edited/linted as HTML. Shared CSS lives in static/style.css.
"""
import csv
import io
import json
import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, Response, abort, redirect, render_template, request, send_file, url_for

from swingbot import config
from swingbot.core.performance import TradeLog, trade_proximity
from swingbot.core.scan_engine import is_scan_running, regenerate_chart_for_trade, request_stop
from swingbot.core.data import get_company_name, get_currency_symbol, get_current_price, get_logo_path
from swingbot.core.watchlist import load_watchlist, add_ticker, remove_ticker
from swingbot.core.ticker_directory import search_tickers
# Pure helper functions (.env parsing, Docker container control, confidence-hex,
# log tailing) live in their own module -- see helpers.py's own docstring for why.
from .helpers import (
    BOT_CONTAINER_NAME, FIELDS_BY_KEY, FIELDS_BY_SECTION, docker_sdk,
    _build_env_text, _changed_non_hot_reloadable_fields, _clear_log, _confidence_hex,
    _field_display_value, _get_bot_container, _hot_reload_bot_container, _primary_strategy_label,
    _read_env_values, _restart_bot_container, _sources_str, _tail_log, _write_env_text, get_versions,
)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
TRIGGER_FILE = os.path.join(config.DATA_DIR, "trigger_check.flag")
PAUSE_FILE = os.path.join(config.DATA_DIR, "scan_paused.flag")

NAV_ITEMS = [
    ("dashboard", "🏠", "Dashboard", "index"),
    ("watchlist", "📋", "Watchlist", "watchlist_page"),
    ("settings", "⚙️", "Settings", "settings_page"),
    ("logs", "📜", "Logs", "logs_page"),
]

_SECTION_META = {
    "Discord Connection":    ("🔗", "Token and channel IDs for the Discord bot."),
    "Scanning & Session":    ("⏱", "When the bot scans automatically and how often."),
    "Trade Filters & Risk":  ("🎯", "Hard constraints every scenario must meet before being scored or alerted."),
    "Data & Display":        ("📊", "Data history, currency, and market benchmark settings."),
    "Account Defaults":      ("💰", "Starting account values seeded into data/account.json on first run."),
    "Admin UI":              ("🔐", "Credentials and port for this web UI (requires admin container restart to take effect)."),
}

app = Flask(__name__)


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
def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return Response(
                "Authentication required.", 401,
                {"WWW-Authenticate": 'Basic realm="Swing Bot Admin"'},
            )
        return view(*args, **kwargs)
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
def _render_dashboard_fragment() -> str:
    open_trades = _trades().get_trades(status="open", limit=None, sort_by="confidence")
    stats = _trades().get_stats()
    stats.update(_trades().get_extended_stats())
    # Pre-build a per-ticker currency map so Jinja doesn't call get_currency_symbol
    # (a network round-trip) inline -- lookups are cached after the first call so
    # this is fast for tickers we've seen before.
    cur_map = {t["ticker"]: get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL) for t in open_trades}
    # Trade-health status per open trade: how close its live price is to the
    # stop-loss (red) vs. the target (green), grey near entry. get_current_price
    # is itself cached for 60s, so this only actually hits yfinance once a
    # minute per ticker no matter how often the dashboard's 5s poll calls in --
    # the color simply won't change in between those refreshes.
    # Keyed by trade id, not ticker -- the same ticker can have more than one
    # open trade at once (different strategy/horizon), each with its own
    # entry/stop/target, so they need independent statuses.
    status_map = {}
    price_map = {}   # trade id -> live current price (or None if unresolvable), for the Current Price column
    unrealized_pcts = []   # one entry per open trade with a resolvable live price
    for t in open_trades:
        price = get_current_price(t["ticker"])
        price_map[t["id"]] = price
        if price is None:
            status_map[t["id"]] = {"color": "#5a6275", "proximity": 0.0, "blink_seconds": 2.2, "label": "Price unavailable"}
        else:
            status_map[t["id"]] = trade_proximity(
                t["direction"], t["entry"], t["stop_loss"], t["take_profit"], price
            )
            pct = (price - t["entry"]) / t["entry"] * 100 if t["entry"] else 0.0
            if t["direction"] == "bearish":
                pct = -pct
            unrealized_pcts.append(pct)
    # Equal-weighted average across every open position (no per-trade position
    # sizing is tracked anywhere in this app -- see config.py's Account
    # Defaults docstring), i.e. "if I'd put one unit into each open trade,
    # what's my blended unrealized return right now". None (shown as "--")
    # when there are no open trades or none of their live prices resolved.
    stats["total_unrealized_pct"] = (sum(unrealized_pcts) / len(unrealized_pcts)) if unrealized_pcts else None
    # Highest-score agreed strategy per trade -- see helpers._primary_strategy_label
    # for why this replaces the old always-"S/R Confluence" t.strategy field.
    strategy_map = {t["id"]: _primary_strategy_label(t) for t in open_trades}

    # ── Per-trade P&L / risk metrics ──────────────────────────────────────────
    # Computed here (Python) so the template stays logic-light; all values are
    # None when the live price is unavailable.
    pnl_map: dict = {}   # trade_id → {pnl_pct, to_sl_pct, to_tp_pct, pos_pct, entry_pct}
    days_map: dict = {}  # trade_id → int days open
    now_utc = datetime.now(timezone.utc)

    for t in open_trades:
        tid = t["id"]
        price = price_map.get(tid)
        entry = t.get("entry") or 0
        sl    = t.get("stop_loss") or 0
        tp    = t.get("take_profit") or 0
        is_bull = t.get("direction") == "bullish"

        # Days open
        try:
            opened_dt = datetime.fromisoformat(t["opened_at"])
            days_map[tid] = max(0, (now_utc - opened_dt).days)
        except Exception:
            days_map[tid] = None

        if price and entry:
            raw_pnl = (price - entry) / entry * 100
            pnl_pct = raw_pnl if is_bull else -raw_pnl
            to_sl   = abs(price - sl) / abs(price) * 100 if price else None
            to_tp   = abs(tp - price) / abs(price) * 100 if price else None

            # Position bar: maps SL→TP to 0→100 %.
            # pos_pct  = where current price sits
            # entry_pct = where the original entry sits (anchor marker)
            if is_bull:
                span = tp - sl
            else:
                span = sl - tp
            if span and span > 0:
                cur_pos   = (price - sl) / span * 100 if is_bull else (sl - price) / span * 100
                entry_pos = (entry - sl) / span * 100 if is_bull else (sl - entry) / span * 100
            else:
                cur_pos = entry_pos = 50.0

            pnl_map[tid] = {
                "pnl_pct":    round(pnl_pct, 2),
                "to_sl_pct":  round(to_sl, 1) if to_sl is not None else None,
                "to_tp_pct":  round(to_tp, 1) if to_tp is not None else None,
                "pos_pct":    max(0.0, min(100.0, round(cur_pos, 1))),
                "entry_pct":  max(0.0, min(100.0, round(entry_pos, 1))),
            }
        else:
            pnl_map[tid] = None

    # ── Closed trades (last 25 by closed_at) ─────────────────────────────────
    all_trades_raw = _trades().get_trades(status=None, limit=None, sort_by="opened_at")
    closed_trades = [t for t in all_trades_raw if t["status"] in ("win", "loss", "closed")]
    closed_trades.sort(key=lambda t: t.get("closed_at") or "", reverse=True)
    closed_trades = closed_trades[:25]

    # Per-closed-trade computed fields (passed as helper callables so Jinja
    # can call them like functions: {{ trade_pnl(t) }}).
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

    def _closed_days(t) -> int | None:
        try:
            opened = datetime.fromisoformat(t["opened_at"])
            closed_dt = datetime.fromisoformat(t["closed_at"])
            return max(0, (closed_dt - opened).days)
        except Exception:
            return None

    # Aggregate realized stats for the extra stat cards.
    realized_pnls = [p for p in (_closed_pnl(t) for t in closed_trades) if p is not None]
    stats["total_realized_pct"] = round(sum(realized_pnls) / len(realized_pnls), 2) if realized_pnls else None
    stats["best_trade_pct"]  = round(max(realized_pnls), 2) if realized_pnls else None
    stats["worst_trade_pct"] = round(min(realized_pnls), 2) if realized_pnls else None

    return render_template(
        "dashboard_fragment.html",
        open_trades=open_trades, stats=stats, confidence_hex=_confidence_hex,
        cur_map=cur_map, status_map=status_map, strategy_map=strategy_map,
        price_map=price_map, pnl_map=pnl_map, days_map=days_map,
        closed_trades=closed_trades,
        trade_pnl=_closed_pnl, trade_r=_closed_r, trade_days=_closed_days,
    )


@app.route("/", methods=["GET"])
@require_auth
def index():
    return _render(
        "Dashboard", "dashboard", "dashboard.html",
        fragment=_render_dashboard_fragment(),
        dashboard_refresh_seconds=config.DASHBOARD_REFRESH_SECONDS,
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
    """
    return Response(_render_dashboard_fragment(), mimetype="text/html; charset=utf-8")


@app.route("/trades/clear-open", methods=["POST"])
@require_auth
def clear_open_trades():
    removed = _trades().clear_open()
    msg = f"Cleared {removed} open trade(s). Closed win/loss history was left untouched."
    return redirect(url_for("index", msg=msg, ok=1))



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
    )


@app.route("/settings/save", methods=["POST"])
@require_auth
def save_settings():
    existing = _read_env_values()
    restart_needed_for = _changed_non_hot_reloadable_fields(existing, request.form)

    new_text = _build_env_text(request.form, existing)
    _write_env_text(new_text)

    success, message = _hot_reload_bot_container()
    if restart_needed_for:
        names = ", ".join(restart_needed_for)
        message += f" Note: {names} won't take effect until the bot container is actually restarted (see field help text)."
    return redirect(url_for("settings_page", msg=message, ok=1 if success else 0))


@app.route("/bot/restart", methods=["POST"])
@require_auth
def restart_bot():
    success, message = _restart_bot_container()
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
    return _render(
        "Logs", "logs", "logs.html", log_content=_tail_log(lines), lines=lines, log_path=config.LOG_FILE,
        logs_refresh_seconds=config.LOGS_REFRESH_SECONDS,
    )


@app.route("/logs/clear", methods=["POST"])
@require_auth
def logs_clear():
    success, message = _clear_log()
    return redirect(url_for("logs_page", msg=message, ok=1 if success else 0))


@app.route("/logs/raw", methods=["GET"])
@require_auth
def logs_raw():
    try:
        lines = int(request.args.get("lines", 500))
    except ValueError:
        lines = 500
    lines = max(1, min(lines, 5000))
    return Response(_tail_log(lines), mimetype="text/plain; charset=utf-8")


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
    return send_file(path, mimetype="image/png")


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
    return redirect(url_for("index", msg=f"Trade {t['ticker']} marked as closed.", ok=1))


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
# Route -- ticker logos (used by the Watchlist, Dashboard, and Trade detail
# pages below). Serves from core/data.py's on-disk logo cache, fetching and
# caching on first request if it isn't there yet. Returns 404 (rather than a
# broken image placeholder) when no logo can be found -- the templates below
# add onerror="this.style.display='none'" so a missing logo just quietly
# collapses instead of showing a broken-image icon.
# ---------------------------------------------------------------------------
@app.route("/logo/<ticker>")
@require_auth
def ticker_logo(ticker):
    path = get_logo_path(ticker)
    if not path:
        abort(404)
    return send_file(path, mimetype="image/png", max_age=86400)


# ---------------------------------------------------------------------------
# Routes -- Watchlist
# ---------------------------------------------------------------------------
@app.route("/watchlist", methods=["GET"])
@require_auth
def watchlist_page():
    tickers = load_watchlist()
    # Build per-ticker trade stats
    tl = _trades()
    trade_counts = {}
    for ticker in tickers:
        trades = tl.get_trades(ticker=ticker, status=None, limit=None)
        open_c = sum(1 for tr in (trades or []) if tr["status"] == "open")
        closed_c = len(trades or []) - open_c
        trade_counts[ticker] = {"open": open_c, "closed": closed_c}
    # Real company names (e.g. "Apple Inc." for AAPL) -- cached in-memory
    # after the first lookup per ticker, see core/data.get_company_name.
    company_names = {ticker: get_company_name(ticker) for ticker in tickers}
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
        return redirect(url_for("watchlist_page", msg=f"Added {ticker} to watchlist ({len(updated)} tickers total).", ok=1))
    return redirect(url_for("watchlist_page", msg=f"{ticker} is already in the watchlist.", ok=1))


@app.route("/watchlist/fetchlogos", methods=["POST"])
@require_auth
def watchlist_fetchlogos():
    """
    Pre-downloads and caches the logo for every current watchlist ticker
    (see core/data.get_ticker_logo) so the images above render instantly
    instead of each one lazily fetching on its first page view. Safe to
    re-run any time -- already-cached logos resolve instantly.
    """
    tickers = load_watchlist()
    ok = sum(1 for t in tickers if get_logo_path(t))
    msg = f"Fetched logos for {ok}/{len(tickers)} ticker(s)."
    if ok < len(tickers):
        msg += " Some tickers have no discoverable logo (unusual symbols, indices, futures, etc.)."
    return redirect(url_for("watchlist_page", msg=msg, ok=1))


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
    in commands/scanning.py). Manual !check / "Run !check now" still work
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


@app.route("/scan/stop", methods=["POST"])
@require_auth
def stop_scan():
    """Ask the bot to stop whatever scan is currently running (!check,
    /check, this admin UI's own "Run !check now" trigger, or the
    automatic session scan). Different from pause: pause only stops
    FUTURE automatic scans, this cuts short one already in progress.
    Cooperative -- takes effect at the scan's next per-ticker checkpoint,
    not instantly (see scan_engine.request_stop())."""
    try:
        request_stop()
        msg = "Stop requested — the running scan will end after finishing its current ticker."
        ok = 1
    except Exception as e:
        msg = f"Could not request stop: {e}"
        ok = 0
    return redirect(url_for("index", msg=msg, ok=ok))


def main():
    host = os.getenv("ADMIN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_PORT", 1234))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
