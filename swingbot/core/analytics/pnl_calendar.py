"""Day-level P&L aggregation behind the /calendar admin workspace.

Spec: `docs/superpowers/specs/implemented/2026-08-22-v53-pnl-calendar-design.md`.

**Why this module exists next to `metrics.calendar_returns`.** That function
compounds *percentage* return per calendar MONTH. This one sums *dollars* and
*R* per calendar DAY, and joins the journal in so a day can be drilled into.
They are different granularities over different units and must not be folded
together -- `/analytics/performance` already ships the monthly `calendar`
key, and two functions quietly answering "the calendar figures" in different
units is how the two come to disagree on the same page.

**Pure, and deliberately so.** Every function below takes lists of dicts.
`load_rows()` is the single I/O boundary, and even it accepts injected
stores. Nothing here imports from `swingbot.admin` -- `closed_r()` lives
there and is off limits; `metrics.r_multiple` is the core-layer equivalent
and is the repo's one shared R computation.
"""
from __future__ import annotations

import datetime as _dt

from swingbot.core.analytics import metrics
from swingbot.core.tracking.performance import primary_strategy_label

# The three statuses that mean "this position is over". Matches the filter
# `api_v1/analytics.py` applies before every historical figure it serves.
CLOSED_STATUSES = frozenset({"win", "loss", "closed"})

# The keys a joined row carries. Declared as a constant because the route's
# contract test asserts an exact key set, and a field added here without a
# matching contract update is exactly the undocumented change that test
# exists to catch.
ROW_KEYS = (
    "trade_id", "ticker", "strategy", "horizon", "direction", "day",
    "closed_at", "outcome", "pnl_amount", "r_multiple", "mfe_r", "mae_r",
    "exit_efficiency", "tags", "auto_lesson",
)


def day_of(closed_at: str | None) -> str | None:
    """The calendar day of an ISO close timestamp, as `YYYY-MM-DD`.

    A STRING SLICE, not a timezone conversion -- see the plan's Global
    Constraint 4. `closed_at` is always written as UTC ISO, and
    `metrics.calendar_returns` / `cumulative_pnl_by_strategy` already bucket
    by slicing. Converting to Europe/Berlin here would put a late close on a
    different day than the monthly figures rendered beside it.
    """
    if not closed_at:
        return None
    return closed_at[:10] or None


def _float_or_none(value) -> float | None:
    """`float(value)`, or None for anything non-numeric.

    A record written before a field existed carries None, and a hand-edited
    trades.json can carry a string. Neither should raise in an aggregation
    whose whole job is to survive the archive.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def joined_rows(trades: list[dict], entries: list[dict]) -> list[dict]:
    """One row per closed trade, with its journal entry merged in.

    The join key is asymmetric by construction: the trade side calls it
    `id`, the journal side `trade_id` (set from `trade.get("id")` at
    `journal.py:211`). A trade with no journal entry still produces a row --
    its dollar figure is what colours the grid cell, and dropping it would
    make the calendar disagree with the Dashboard's realized total.
    """
    by_trade_id = {
        e["trade_id"]: e for e in entries if e.get("trade_id")
    }

    rows: list[dict] = []
    for t in trades:
        if t.get("status") not in CLOSED_STATUSES:
            continue
        day = day_of(t.get("closed_at"))
        if day is None:
            continue

        entry = by_trade_id.get(t.get("id")) or {}
        # The journal's r_realized is authoritative when present: it was
        # computed by the same metrics.r_multiple at close time, and reusing
        # it avoids a second answer for one trade.
        r = _float_or_none(entry.get("r_realized"))
        if r is None:
            r = metrics.r_multiple(t)

        rows.append({
            "trade_id": t.get("id"),
            "ticker": t.get("ticker"),
            "strategy": primary_strategy_label(t),
            "horizon": t.get("horizon_key"),
            "direction": t.get("direction"),
            "day": day,
            "closed_at": t.get("closed_at"),
            "outcome": entry.get("outcome") or t.get("status"),
            "pnl_amount": _float_or_none(t.get("realized_pnl_amount")),
            "r_multiple": r,
            "mfe_r": _float_or_none(entry.get("mfe_r")),
            "mae_r": _float_or_none(entry.get("mae_r")),
            "exit_efficiency": _float_or_none(entry.get("exit_efficiency")),
            "tags": list(entry.get("tags") or []),
            "auto_lesson": entry.get("auto_lesson") or None,
        })
    return rows


def filter_rows(rows: list[dict], *, strategy: str | None = None,
                horizon: str | None = None) -> list[dict]:
    """AND-combined strategy/horizon narrowing. `None` means "do not apply"."""
    out = rows
    if strategy:
        out = [r for r in out if r["strategy"] == strategy]
    if horizon:
        out = [r for r in out if r["horizon"] == horizon]
    return out


def available_filters(rows: list[dict]) -> dict:
    """The filter vocabulary, derived from the UNFILTERED row set.

    Callers must pass every row, not the narrowed set -- a dropdown that
    shrinks to only the option already selected cannot be un-selected.
    """
    return {
        "strategies": sorted({r["strategy"] for r in rows if r["strategy"]}),
        "horizons": sorted({r["horizon"] for r in rows if r["horizon"]}),
    }


def load_rows(*, trade_log=None, journal=None) -> list[dict]:
    """The module's one I/O boundary: read both stores and join them.

    Stores are constructed here rather than at import time (Global
    Constraint 1) and are injectable so tests can point them at a tmp_path
    without monkeypatching `config.DATA_DIR`.
    """
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.tracking.performance import TradeLog

    tl = trade_log if trade_log is not None else TradeLog()
    js = journal if journal is not None else JournalStore()

    trades = tl.get_trades(status=None, limit=None) or []
    try:
        entries = js.entries()
    except Exception:
        # Same posture as `api_v1/analytics.py:198-204`: an unreadable
        # journal degrades to "no lessons" rather than failing a page whose
        # dollar figures came from trades.json and are fine.
        entries = []
    return joined_rows(trades, entries)


def _sum_or_none(values: list[float | None]) -> float | None:
    """Sum the computable values, or None if none are.

    `sum([])` is `0`, which is exactly the conflation Global Constraint 5
    forbids -- a day with no computable dollar figure must not render as a
    flat $0 day.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present), 2)


def bucket_by_day(rows: list[dict]) -> dict[str, list[dict]]:
    """`{"YYYY-MM-DD": [row, ...]}`. Days with no rows simply have no key."""
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["day"], []).append(row)
    return buckets


def day_summary(day: str, rows: list[dict]) -> dict:
    """One grid cell: net dollars, net R, count, win rate.

    `win_rate` delegates to `metrics.win_rate` rather than counting inline,
    so a "closed" exit with no win/loss verdict is excluded from both
    numerator and denominator here exactly as it is everywhere else.
    """
    return {
        "date": day,
        "net_pnl_amount": _sum_or_none([r["pnl_amount"] for r in rows]),
        "net_r": _sum_or_none([r["r_multiple"] for r in rows]),
        "trade_count": len(rows),
        "win_rate": metrics.win_rate(
            [{"status": r["outcome"]} for r in rows]
        ),
    }


def month_grid(rows: list[dict], month: str) -> dict:
    """Every day of `month` (`YYYY-MM`) that had a close, plus the totals.

    Days are ascending. The totals are computed over the month's rows as one
    pool rather than by averaging the per-day summaries -- a 1-trade day and
    a 9-trade day must not carry equal weight in the month's win rate.
    """
    scoped = [r for r in rows if r["day"][:7] == month]
    buckets = bucket_by_day(scoped)
    days = [day_summary(day, buckets[day]) for day in sorted(buckets)]
    totals = day_summary(month, scoped)
    # `date` on a month total would invite reading it as a day.
    totals.pop("date", None)
    return {"month": month, "days": days, "totals": totals}


# Monday-first, and only the five days a US-market swing bot can close on.
# Saturday and Sunday are not modelled: a weekend cell is rendered inert by
# the frontend rather than reported as a zero here.
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def _avg_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 2)


def day_of_week_breakdown(rows: list[dict]) -> list[dict]:
    """Per-weekday averages across every row given, Mon..Fri.

    Averaged PER TRADE, not per day: "what does a Monday trade typically
    do" is the question, and averaging day-averages would let a Monday with
    one trade outweigh a Monday with eight.

    All five weekdays are always present, even at n=0, so the table keeps
    its shape as a strategy/horizon filter narrows the set.
    """
    by_weekday: dict[str, list[dict]] = {name: [] for name in WEEKDAYS}
    for row in rows:
        try:
            index = _dt.date.fromisoformat(row["day"]).weekday()
        except ValueError:
            continue
        if index < len(WEEKDAYS):     # 5 and 6 are Sat/Sun -- see WEEKDAYS.
            by_weekday[WEEKDAYS[index]].append(row)

    return [
        {
            "weekday": name,
            "avg_pnl_amount": _avg_or_none([r["pnl_amount"] for r in group]),
            "avg_r": _avg_or_none([r["r_multiple"] for r in group]),
            "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in group]),
            "trade_count": len(group),
        }
        for name, group in ((n, by_weekday[n]) for n in WEEKDAYS)
    ]


def best_worst_days(rows: list[dict]) -> dict:
    """The single best and worst DAY by net dollars, each a full summary.

    A day, not a trade: the worst day in the book is often several ordinary
    losses rather than one spectacular one, and that is the fact worth
    surfacing. Days with no computable dollar total are excluded from the
    ranking rather than sorted as zero.
    """
    buckets = bucket_by_day(rows)
    summaries = [day_summary(day, buckets[day]) for day in sorted(buckets)]
    ranked = [s for s in summaries if s["net_pnl_amount"] is not None]
    if not ranked:
        return {"best": None, "worst": None}
    return {
        "best": max(ranked, key=lambda s: s["net_pnl_amount"]),
        "worst": min(ranked, key=lambda s: s["net_pnl_amount"]),
    }


def day_streak(rows: list[dict]) -> dict:
    """The current run of same-signed days, counted back from the latest.

    Only days that actually had closes participate. A gap -- a weekend, a
    holiday, a quiet Wednesday -- is an absence of evidence and does NOT
    break the run; treating it as a break would cap almost every streak at
    five and make the figure meaningless.

    A zero-dollar day is its own `"flat"` direction rather than being folded
    into either side, and ends whatever run was building.
    """
    buckets = bucket_by_day(rows)
    summaries = [day_summary(day, buckets[day]) for day in sorted(buckets, reverse=True)]
    ranked = [s for s in summaries if s["net_pnl_amount"] is not None]
    if not ranked:
        return {"direction": None, "days": 0}

    def _sign(summary: dict) -> str:
        amount = summary["net_pnl_amount"]
        if amount > 0:
            return "winning"
        if amount < 0:
            return "losing"
        return "flat"

    direction = _sign(ranked[0])
    if direction == "flat":
        return {"direction": "flat", "days": 1}

    days = 0
    for summary in ranked:
        if _sign(summary) != direction:
            break
        days += 1
    return {"direction": direction, "days": days}
