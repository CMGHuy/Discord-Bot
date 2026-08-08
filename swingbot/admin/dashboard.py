"""
View-model builders for the Dashboard page.

This module holds everything the Dashboard needs to *compute*; app.py keeps
only the three thin routes that serve it (`index`, `dashboard_fragment`,
`api_trade_history`). Deliberately not a Flask blueprint: moving the routes
would rename their endpoints (`index` -> `dashboard.index`) and break
`url_for('index')` across every template plus NAV_ITEMS, for no gain.

Nothing here touches `flask.request`. The dashboard mode ("active"/"today"/
"all") arrives as an argument, which is what makes these functions directly
unit-testable without a request context -- the previous single 315-line
`_render_dashboard_fragment()` read `request.args` in its first statement and
so could only ever be exercised through a full HTTP round trip.

Split of responsibilities, top to bottom:
  * formatting//colour helpers shared by several panels
  * closed-trade derivations (P&L, R, holding period) -- also used by
    /api/trade-history, which renders the same row partial
  * `query_closed_trades()` -- scope/filter/sort/slice for Trade History
  * per-panel builders (`build_sizing_note`, `build_open_trade_views`, ...)
  * `build_fragment_context()` -- the one orchestrator the routes call
"""
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.account import compute_position_size, get_daily_summary, load_account_config
from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
from swingbot.core.data import get_currency_symbol, get_current_price, prefetch_prices, is_us_market_active
from swingbot.core.performance import TradeLog, trade_proximity

from .helpers import _confidence_hex, _primary_strategy_label

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None


DASHBOARD_MODES = ("active", "today", "all")
CLOSED_TRADE_STATUSES = ("win", "loss", "closed")

# Rows Trade History renders server-side for its FIRST paint. Later pages come
# from /api/trade-history, so this is a first-paint size, not a cap on how much
# history is reachable.
CLOSED_TRADES_FIRST_PAGE = 25

# Allowed page sizes, mirroring the table's own selector. 0 means "All".
# Clamped server-side: the page size decides how much work a request does, so
# it is never taken on trust from the query string.
ALLOWED_PER_PAGE = (10, 25, 50, 0)


def normalize_mode(value) -> str:
    """Coerce anything (query string, None, junk) to a valid dashboard mode."""
    return value if value in DASHBOARD_MODES else "active"


# ---------------------------------------------------------------------------
# Formatting / colour helpers
# ---------------------------------------------------------------------------
def format_duration_hms(total_seconds: float) -> str:
    """
    Human-readable elapsed-time label with day/hour/MINUTE granularity --
    e.g. "12m", "4h 20m", "1d 5h 32m" -- used everywhere a "how long has this
    been open/how long was this held" figure is shown (Open Trades + Trade
    History "Held" columns, plus the Avg holding period stat card).

    Whole-calendar-days-only reads as "0" for anything opened and closed on the
    same day regardless of whether that was 10 minutes or 23 hours; this is
    precise to the minute, and keeps hours+minutes even once the duration spans
    days rather than dropping them once a coarser unit is available.
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
    return " ".join(parts)


def pos_color(pos_pct: float, entry_pct: float) -> str:
    """Colour for the SL->TP progress bar and percentage text.

    Interpolates red (SL, 0%) -> grey (entry) -> green (TP, 100%) so the bar
    always shows absolute position between stop and target, independent of
    whether the trade is currently profitable.
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


def is_today_berlin(iso_ts: str | None) -> bool:
    """True if the ISO timestamp falls on today's Europe/Berlin calendar day --
    the same day boundary the daily retrospective and account summary use, so
    the dashboard's "Today" mode lines up with them."""
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


# ---------------------------------------------------------------------------
# Closed-trade derivations
# ---------------------------------------------------------------------------
# Pure -- no closure over render state. /api/trade-history renders the same row
# partial and needs the identical callables; duplicating them is how the two
# paths drift.
def closed_pnl(t) -> float | None:
    ex, en = t.get("exit_price"), t.get("entry")
    if not ex or not en:
        return None
    raw = (ex - en) / en * 100
    return round(raw if t["direction"] == "bullish" else -raw, 2)


def closed_r(t) -> float | None:
    ex, en, sl_v = t.get("exit_price"), t.get("entry"), t.get("stop_loss")
    if not ex or not en or not sl_v:
        return None
    risk = abs(en - sl_v)
    if not risk:
        return None
    realized = (ex - en) if t["direction"] == "bullish" else (en - ex)
    return round(realized / risk, 2)


def closed_days(t) -> dict | None:
    """{label, total_hours} -- the full day/hour/minute holding period label
    plus a raw sortable figure, for Trade History's Held column."""
    try:
        elapsed = (
            datetime.fromisoformat(t["closed_at"]) -
            datetime.fromisoformat(t["opened_at"])
        )
        total_seconds = max(0.0, elapsed.total_seconds())
        return {
            "label": format_duration_hms(total_seconds),
            "total_hours": total_seconds / 3600.0,
        }
    except Exception:
        return None


# Query-string filter name -> how to read the matching value off a trade.
# These MUST stay in step with the data-* attributes the row partial emits,
# since both describe the same six Trade History dropdowns.
FILTER_FIELDS = {
    "outcome":  lambda t: t.get("status"),
    "ticker":   lambda t: t.get("ticker"),
    "strategy": _primary_strategy_label,
    "horizon":  lambda t: t.get("horizon_key"),
    "dir":      lambda t: t.get("direction"),
    "conf":     lambda t: t.get("confidence_level"),
}


def _sortable(fn, missing):
    """Sort key that calls `fn` ONCE per row and substitutes `missing` for
    None, so rows without the value sort to one end instead of raising."""
    def key(t):
        v = fn(t)
        return missing if v is None else v
    return key


# Sortable columns -> how to read the sort value, keyed by the `data-col-id`
# the table header uses. Sorting is server-side for the same reason filtering
# is: with paged responses a client-side sort would only reorder the page you
# happen to be looking at.
SORT_KEYS = {
    "outcome":  lambda t: t.get("status") or "",
    "ticker":   lambda t: t.get("ticker") or "",
    "strategy": lambda t: _primary_strategy_label(t) or "",
    "horizon":  lambda t: t.get("horizon_key") or "",
    "dir":      lambda t: t.get("direction") or "",
    "conf":     lambda t: t.get("confidence_level") or 0,
    "entry":    lambda t: t.get("entry") or 0.0,
    "exit":     lambda t: t.get("exit_price") or -1.0,
    "pnlpct":   _sortable(closed_pnl, -999999),
    "gainloss": _sortable(lambda t: t.get("realized_pnl_amount"), -999999),
    "r":        _sortable(closed_r, -999999),
    "days":     lambda t: (closed_days(t) or {}).get("total_hours", -1),
    "opened":   lambda t: t.get("opened_at") or "",
    "closed":   lambda t: t.get("closed_at") or "",
}


def query_closed_trades(all_raw, *, mode="all", filters=None, page=1, per_page=25,
                        sort_by=None, sort_dir="desc"):
    """Scope -> filter -> sort -> slice the closed-trade history, in that order.

    Returns ``(rows, total)`` where *total* is the count after scoping and
    filtering but BEFORE slicing, so the pager can work out how many pages
    exist without a second pass.

    `mode` follows the dashboard toggle: "today" and "active" both narrow to
    trades CLOSED today (Europe/Berlin). Those two modes are deliberately
    identical here -- the only thing separating them is whether still-open
    positions from other days show, and this table never contains open trades.
    """
    rows = scoped_closed_trades(all_raw, mode)

    for key, value in (filters or {}).items():
        if not value:
            continue                      # absent/blank means "no filter"
        getter = FILTER_FIELDS.get(key)
        if getter is None:
            continue
        rows = [t for t in rows if str(getter(t) or "") == str(value)]

    # Default: newest close first, matching the table's pre-paging behaviour.
    key = SORT_KEYS.get(sort_by or "", SORT_KEYS["closed"])
    # str() the key so a column holding mixed types (a None exit price beside
    # floats, say) can't raise TypeError mid-sort and 500 the whole table.
    try:
        rows.sort(key=key, reverse=(sort_dir != "asc"))
    except TypeError:
        rows.sort(key=lambda t: str(key(t)), reverse=(sort_dir != "asc"))
    total = len(rows)

    if per_page:
        page = max(1, int(page or 1))
        start = (page - 1) * per_page
        rows = rows[start:start + per_page]
    return rows, total


def scoped_closed_trades(all_raw, mode: str) -> list:
    """Closed trades within the mode's date scope. Single source of truth for
    that scoping -- both Trade History and the realized stat cards use it, and
    they disagreed before (the cards were computed off page 1 only)."""
    rows = [t for t in all_raw if t.get("status") in CLOSED_TRADE_STATUSES]
    if mode in ("today", "active"):
        rows = [t for t in rows if is_today_berlin(t.get("closed_at"))]
    return rows


def scoped_trades(all_raw, mode: str):
    """Trades the mode's stat cards summarize.

    Returns None for "all" -- TradeLog.get_stats()/get_extended_stats() treat
    None as "use the full trade set", so this avoids materialising a copy.

      * "active" (default): today's new trades PLUS every still-open position
        regardless of which day it was opened -- "what needs attention now".
        The only mode that mixes days: an old open swing from last week still
        shows (it is still live risk), but closed-trade stats only count
        today's closes.
      * "today": strictly today's Europe/Berlin activity -- opened today or
        closed today. An old open trade is NOT shown even though it is open.
      * "all": every trade, no date filtering.
    """
    if mode == "today":
        return [
            t for t in all_raw
            if is_today_berlin(t.get("opened_at")) or is_today_berlin(t.get("closed_at"))
        ]
    if mode == "active":
        return [
            t for t in all_raw
            if t["status"] == "open"
            or is_today_berlin(t.get("opened_at"))
            or is_today_berlin(t.get("closed_at"))
        ]
    return None


# ---------------------------------------------------------------------------
# Per-panel builders
# ---------------------------------------------------------------------------
def build_sizing_note(account_cfg: dict) -> dict:
    """"What does a trade actually cost right now" for the Position premium
    card -- answers the recurring question of why unrealized P&L on open
    positions doesn't match a naive "balance x position %" guess.

    In Account % mode the premium IS that exact fixed number every time. In
    Risk % mode (the default) there is no single fixed premium -- position
    value varies per trade with how far away its stop is, up to the Max
    position size % cap -- so the worked-out range is surfaced instead.

    Every figure is also run through the two absolute caps
    (max_position_value_absolute / max_risk_amount_absolute -- see
    compute_position_size() in core/account.py), taking whichever is tighter.
    Applying only the %-based caps let this card show a stale "up to" figure
    no real trade could reach: balance x max_position_pct coming out at
    $50,000 while every trade was actually capped at the $1,000 absolute limit.

    Reflects TODAY's settings only: a trade opened under a different
    balance/risk/mode has its own shares snapshotted at open time and won't
    retroactively match this.
    """
    balance = float(account_cfg.get("balance", 0))
    max_pos_abs = float(account_cfg.get("max_position_value_absolute", 0) or 0)
    max_risk_abs = float(account_cfg.get("max_risk_amount_absolute", 0) or 0)

    if account_cfg.get("sizing_mode") == "account_pct":
        premium = balance * float(account_cfg.get("position_pct", 0)) / 100.0
        if account_cfg.get("max_position_pct"):
            premium = min(premium, balance * float(account_cfg["max_position_pct"]) / 100.0)
        if max_pos_abs > 0:
            premium = min(premium, max_pos_abs)
        return {
            "mode": "account_pct",
            "premium": round(premium, 2),
            "position_pct": account_cfg.get("position_pct", 0),
        }

    risk_amount = balance * float(account_cfg.get("risk_pct", 0)) / 100.0
    if max_risk_abs > 0:
        risk_amount = min(risk_amount, max_risk_abs)
    max_position = balance * float(account_cfg.get("max_position_pct", 0)) / 100.0
    if max_pos_abs > 0:
        max_position = min(max_position, max_pos_abs)
    return {
        "mode": "risk_pct",
        "risk_amount": round(risk_amount, 2),
        "risk_pct": account_cfg.get("risk_pct", 0),
        "max_position": round(max_position, 2),
        "max_position_pct": account_cfg.get("max_position_pct", 0),
        "max_position_value_absolute": max_pos_abs,
        "max_risk_amount_absolute": max_risk_abs,
    }


def build_open_trade_views(open_trades: list, account_cfg: dict) -> dict:
    """One pass over open trades producing every per-trade map the table needs:
    price, status dot, P&L + SL/TP progress + position bar, holding period, and
    position sizing.

    Returns {status, price, pnl, days, sizing, unrealized_pcts} -- the first
    five keyed by trade id, the last a flat list for the Open P&L stat card.
    """
    status_map: dict = {}
    price_map: dict = {}
    pnl_map: dict = {}
    days_map: dict = {}
    sizing_map: dict = {}
    unrealized_pcts: list = []
    now_utc = datetime.now(timezone.utc)

    # Fetch all prices concurrently so the loop below hits the in-memory cache
    # and never blocks on a sequential network call per ticker.
    prefetch_prices([t["ticker"] for t in open_trades])

    for t in open_trades:
        tid     = t["id"]
        price   = get_current_price(t["ticker"])
        entry   = t.get("entry")       or 0.0
        sl      = t.get("stop_loss")   or 0.0
        tp      = t.get("take_profit") or 0.0
        is_bull = t.get("direction") == "bullish"

        price_map[tid] = price

        if price is None:
            status_map[tid] = {
                "color": "#5a6275", "proximity": 0.0,
                "blink_seconds": 2.2, "label": "Price unavailable",
            }
        else:
            status_map[tid] = trade_proximity(t["direction"], entry, sl, tp, price)

        try:
            elapsed = now_utc - datetime.fromisoformat(t["opened_at"])
            total_hours = max(0, elapsed.total_seconds() / 3600.0)
            days_map[tid] = {
                "days": int(total_hours // 24),   # whole days, for the >30-day aging colour
                "total_hours": total_hours,        # for sorting
                "label": format_duration_hms(total_hours * 3600),
            }
        except Exception:
            days_map[tid] = None

        if price and entry:
            raw_pnl = (price - entry) / entry * 100
            pnl_pct = raw_pnl if is_bull else -raw_pnl
            unrealized_pcts.append(pnl_pct)

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

            p  = max(0.0, min(100.0, round(cur_pos, 1)))
            ep = max(0.0, min(100.0, round(entry_pos, 1)))
            pnl_map[tid] = {
                "pnl_pct":   round(pnl_pct, 2),
                "to_sl_pct": round(max(0.0, sl_raw), 1),
                "to_tp_pct": round(max(0.0, tp_raw), 1),
                "pos_pct":   p,
                "entry_pct": ep,
                "pos_color": pos_color(p, ep),
            }
        else:
            pnl_map[tid] = None

        sizing_map[tid] = compute_position_size(entry=entry, stop_loss=sl, account_cfg=account_cfg)

    return {
        "status": status_map, "price": price_map, "pnl": pnl_map,
        "days": days_map, "sizing": sizing_map, "unrealized_pcts": unrealized_pcts,
    }


def build_equity_curve() -> dict:
    """{svg, change_pct} for the Equity (30d) card.

    snap["equity_curve"] is {"points": [...], "skipped_n": ...} (see
    metrics.equity_curve), not a bare list; each point's balance key is
    "date"/"balance". Balances are raw account-currency figures (e.g. 10000+),
    not the 0-100 scale _sparkline_svg assumes (it is shared with the win-rate
    sparkline), so they are min-max normalized purely for the sparkline's shape.

    `change_pct` is the first->last move across the window. The card used to
    show the current account balance as its headline, which was the identical
    number already shown by the Account balance card immediately to its left;
    the period change is what a 30-day curve is actually there to tell you.
    """
    # Local import: pages.py does `from .app import ...` at its own top, and
    # app.py imports this module, so a module-level import here would close the
    # circle. Everything is fully loaded by request time.
    from .pages import _sparkline_svg

    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    raw = [
        p["balance"] for p in ((snap or {}).get("equity_curve") or {}).get("points", [])[-30:]
    ]
    if not raw:
        return {"svg": "&mdash;", "change_pct": None}

    lo, hi = min(raw), max(raw)
    span = hi - lo
    svg = _sparkline_svg([(v - lo) / span * 100.0 if span else 50.0 for v in raw], ref=None)
    first = raw[0]
    change = round((raw[-1] - first) / first * 100.0, 2) if first else None
    return {"svg": svg, "change_pct": change}


def build_filter_options(all_raw: list) -> dict:
    """Ticker/strategy/horizon options for Trade History's filter dropdowns.

    Built from the COMPLETE history, not the rows currently on screen: a
    ticker that only appears in an old trade is still a perfectly real
    filterable value. Rendered once by the page shell -- these belong to
    markup that never re-renders, so recomputing them per poll was pure waste.
    """
    closed = [t for t in all_raw if t.get("status") in CLOSED_TRADE_STATUSES]
    return {
        "ticker":   sorted({t["ticker"] for t in closed if t.get("ticker")}),
        "strategy": sorted({_primary_strategy_label(t) for t in closed}),
        "horizon":  sorted({t.get("horizon_key") for t in closed if t.get("horizon_key")}),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def build_fragment_context(mode: str) -> dict:
    """Everything dashboard_fragment.html needs, for one dashboard mode.

    The fragment covers the session banner, lifecycle strip, stat cards and
    Open Trades table -- the panels that genuinely change every few seconds.
    Trade History is NOT here: it lives in the page shell and is driven
    entirely by /api/trade-history after first paint, so re-rendering its rows
    and dropdowns on every 5s poll only ever produced markup the browser threw
    away.
    """
    mode = normalize_mode(mode)

    # Single TradeLog read for the whole render -- avoids re-reading trades.json
    # separately for get_stats(), get_extended_stats(), and the trade lists.
    tl = TradeLog()
    all_raw = tl.get_trades(status=None, limit=None, sort_by="opened_at")
    scoped = scoped_trades(all_raw, mode)

    if scoped is None:
        open_trades = tl.get_trades(status="open", limit=None, sort_by="confidence")
    else:
        open_trades = sorted(
            [t for t in scoped if t["status"] == "open"],
            key=lambda t: (t.get("confidence_level") or 0, t.get("confidence_score") or 0),
            reverse=True,
        )

    stats = tl.get_stats(trades=scoped)
    stats.update(tl.get_extended_stats(trades=scoped))
    stats["avg_holding_label"] = (
        format_duration_hms(stats["avg_holding_days"] * 86400)
        if stats.get("avg_holding_days") is not None else None
    )

    account_cfg = load_account_config()
    views = build_open_trade_views(open_trades, account_cfg)

    # Equal-weighted average unrealized return across open positions with a
    # live price (None -> "—" in the stat card).
    pcts = views["unrealized_pcts"]
    stats["total_unrealized_pct"] = sum(pcts) / len(pcts) if pcts else None

    # Realized stat cards, over the mode's WHOLE closed set. These used to be
    # computed from the first page of Trade History only, which quietly made
    # "Best trade" mean "best of the 25 most recently closed".
    closed_scoped = scoped_closed_trades(all_raw, mode)
    realized = [p for p in (closed_pnl(t) for t in closed_scoped) if p is not None]
    stats["total_realized_pct"] = round(sum(realized) / len(realized), 2) if realized else None
    stats["best_trade_pct"]     = round(max(realized), 2) if realized else None
    stats["worst_trade_pct"]    = round(min(realized), 2) if realized else None
    stats["realized_count"]     = len(realized)

    # Recomputed on every fragment render, so with the auto-refresh poll this
    # card updates on its own the moment a trade closes and settles into the
    # balance (see performance.py's _settle_account_balance).
    stats["account"] = get_daily_summary()

    from .pages import _plan_rows

    return {
        "open_trades": open_trades,
        "stats": stats,
        "confidence_hex": _confidence_hex,
        "cur_map": {t["ticker"]: get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL)
                    for t in open_trades},
        # Account-currency symbol for the sizing card. Its figures are account
        # balance/risk amounts, not per-ticker prices, so config's symbol is
        # the right one -- the template used to reach for "whatever currency
        # the first ticker on the page happens to trade in", which was only
        # ever accidentally correct.
        "currency_symbol": config.CURRENCY_SYMBOL,
        "status_map": views["status"],
        "price_map": views["price"],
        "pnl_map": views["pnl"],
        "days_map": views["days"],
        "sizing_map": views["sizing"],
        "strategy_map": {t["id"]: _primary_strategy_label(t) for t in open_trades},
        "account_cfg": account_cfg,
        "sizing_note": build_sizing_note(account_cfg),
        "is_market_active": is_us_market_active(),
        "dashboard_mode": mode,
        "plan_counts": _plan_rows()["counts"],
        "equity": build_equity_curve(),
    }
