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
from swingbot.core.tracking.performance import expand_realized_legs, primary_strategy_label

# The three statuses that mean "this position is over". Matches the filter
# `api_v1/analytics.py` applies before every historical figure it serves.
CLOSED_STATUSES = frozenset({"win", "loss", "closed"})

# The keys a joined row carries. Declared as a constant because the route's
# contract test asserts an exact key set, and a field added here without a
# matching contract update is exactly the undocumented change that test
# exists to catch.
ROW_KEYS = (
    "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction", "day",
    "opened_at", "closed_at", "outcome", "pnl_amount", "r_multiple", "mfe_r", "mae_r",
    "exit_efficiency", "tags", "auto_lesson", "leg_index", "leg_total",
    # v165 D1 -- read from the part, never re-derived (see `_detail_fields`).
    "entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares",
    "held_hours", "return_pct", "exit_reason",
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


def _utc_stamp(value) -> _dt.datetime | None:
    """An ISO timestamp as an aware datetime, a naive one read as UTC.

    Every close the tracker writes is UTC ISO (`day_of`'s premise), so a
    naive stamp is an older record missing its offset, not local time.
    """
    if not value:
        return None
    try:
        stamp = _dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=_dt.timezone.utc)


def held_hours(opened_at: str | None, closed_at: str | None) -> float | None:
    """Hours from open to close, 2 dp -- or None when it cannot be measured.

    None, never 0, when either stamp is missing or unparseable, and when the
    close precedes the open (a hand-edited record): a 0h hold is a real
    answer that a broken record must not be able to fake. Deliberately not
    `api_v1/trades._held_hours` -- core never imports admin.
    """
    opened, closed = _utc_stamp(opened_at), _utc_stamp(closed_at)
    if opened is None or closed is None or closed < opened:
        return None
    return round((closed - opened).total_seconds() / 3600, 2)


# The only two directions a return can be signed for -- the same rule
# `metrics.r_multiple` applies; anything else is None, not a guessed long.
_DIRECTION_SIGN = {"bullish": 1, "bearish": -1}


def return_pct(entry: float | None, exit_price: float | None,
               direction: str | None) -> float | None:
    """Signed % move from entry to exit in the trade's favour, 2 dp.

    A short that fell 10% returns +10. None when entry is missing or 0, the
    exit is missing, or the direction is unknown.
    """
    sign = _DIRECTION_SIGN.get(direction)
    if not entry or exit_price is None or sign is None:
        return None
    return round((exit_price - entry) / entry * 100 * sign, 2)


def _leg_reason(part: dict, trade: dict) -> str | None:
    """The parent trade's recorded reason for this part's leg, or None.

    A leg part carries `legs: None`, so the reason only lives on the parent,
    at the part's own `leg_index` (`expand_trade_legs` emits legs in order).
    """
    legs = trade.get("legs") or []
    index = part.get("leg_index")
    if not isinstance(index, int) or not 0 <= index < len(legs):
        return None
    return legs[index].get("reason")


def row_exit_reason(part: dict, trade: dict) -> str:
    """The EXIT_REASONS bucket of one calendar row.

    A whole trade (`leg_total == 1`) is bucketed like every other exit-quality
    table: `metrics.exit_reason_bucket` on the trade. A leg is bucketed by
    its own recorded reason, text only -- "other" when that names nothing.
    """
    if part.get("leg_total") == 1:
        return metrics.exit_reason_bucket(trade)
    return metrics.exit_reason_bucket_text(_leg_reason(part, trade)) or "other"


def _detail_fields(part: dict, trade: dict) -> dict:
    """The D1 fields, read from the part `expand_realized_legs` built.

    Leg prices, leg shares and the leg's close are already on the part, so
    nothing here re-prices a leg -- a third copy of that maths beside
    `expand_trade_legs` and `api_v1/trades._row_from_leg` is how the three
    start to disagree. Every missing input stays None.
    """
    entry_price = _float_or_none(part.get("entry"))
    exit_price = _float_or_none(part.get("exit_price"))
    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stop_price": _float_or_none(part.get("stop_loss")),
        "tp1": _float_or_none(part.get("take_profit")),
        "tp2": _float_or_none(part.get("target2")),
        "shares": _float_or_none(part.get("shares")),
        "held_hours": held_hours(part.get("opened_at"), part.get("closed_at")),
        "return_pct": return_pct(entry_price, exit_price, part.get("direction")),
        "exit_reason": row_exit_reason(part, trade),
    }

def _row_for(part: dict, entry: dict, trade: dict) -> dict | None:
    """One calendar row for one realized part of a trade.

    `part` is a row of `performance.expand_realized_legs`: the trade itself
    when it never scaled out, else one realized leg. A leg is counted as an
    individual trade -- its own day, its own win/loss, its own R -- which is
    how the Dashboard's Trades table and its chips count it too.

    For a whole trade the journal's r_realized is authoritative when
    present: it was computed by the same metrics.r_multiple at close time,
    and reusing it avoids a second answer for one trade. A leg's R is the
    leg's own (`metrics.r_multiple` on a leg row prices that leg's exit); the
    journal only ever recorded the blended R of the whole position.

    `trade` is the part's parent record: a leg part has `legs: None`, and its
    exit reason only lives in `trade["legs"]` (see `row_exit_reason`).
    """
    day = day_of(part.get("closed_at"))
    if day is None:
        return None
    whole = part["leg_total"] == 1
    r = _float_or_none(entry.get("r_realized")) if whole else None
    if r is None:
        r = metrics.r_multiple(part)
    return {
        "trade_id": part.get("id"),
        # The Trades detail route is keyed by plan id when the trade has
        # one (that is the id the Trades list shows), else by trade id.
        "plan_id": part.get("plan_id"),
        "ticker": part.get("ticker"),
        "strategy": primary_strategy_label(part),
        "horizon": part.get("horizon_key"),
        "direction": part.get("direction"),
        "day": day,
        "opened_at": part.get("opened_at"),
        "closed_at": part.get("closed_at"),
        "outcome": (entry.get("outcome") if whole else None) or part.get("status"),
        "pnl_amount": _float_or_none(part.get("realized_pnl_amount")),
        "r_multiple": r,
        "mfe_r": _float_or_none(entry.get("mfe_r")),
        "mae_r": _float_or_none(entry.get("mae_r")),
        "exit_efficiency": _float_or_none(entry.get("exit_efficiency")),
        "tags": list(entry.get("tags") or []),
        "auto_lesson": entry.get("auto_lesson") or None,
        "leg_index": part["leg_index"],
        "leg_total": part["leg_total"],
        **_detail_fields(part, trade),
    }


def joined_rows(trades: list[dict], entries: list[dict]) -> list[dict]:
    """One row per closed trade -- or per realized leg of a scaled-out
    one -- with its journal entry merged in.

    The join key is asymmetric by construction: the trade side calls it
    `id`, the journal side `trade_id` (set from `trade.get("id")` at
    `journal.py:211`). A trade with no journal entry still produces a row --
    its dollar figure is what colours the grid cell, and dropping it would
    make the calendar disagree with the Dashboard's realized total.

    A scaled-out trade is split by `expand_realized_legs`, so a TP1 partial
    counts on the day it banked -- even while its runner is still open --
    rather than vanishing into the runner's close. Its legs' dollars sum to
    the trade's own realized total.
    """
    by_trade_id = {
        e["trade_id"]: e for e in entries if e.get("trade_id")
    }

    rows: list[dict] = []
    for t in trades:
        entry = by_trade_id.get(t.get("id")) or {}
        for part in expand_realized_legs(t):
            if (row := _row_for(part, entry, t)) is not None:
                rows.append(row)
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

    from swingbot.core.tracking.origin import is_regular
    trades = [t for t in (tl.get_trades(status=None, limit=None) or []) if is_regular(t)]
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


# --- v165 D2: how one day compares with the rest of the book ---------------

# Below this many other trading days a percentile is not shown at all: one
# step of a 10-day percentile is 10 points, which reads as precision it is
# not. The page bands it below 60 (CD8); the server only ever returns the
# exact figure or None.
PERCENTILE_MIN_DAYS = 20


def _weekday_of(day: str) -> int | None:
    try:
        return _dt.date.fromisoformat(day).weekday()
    except (TypeError, ValueError):
        return None


def _percentile(value: float, others: list[float]) -> float | None:
    """Share of `others` strictly below `value`, ties counting half, x 100."""
    if len(others) < PERCENTILE_MIN_DAYS:
        return None
    below = sum(1 for other in others if other < value)
    ties = sum(1 for other in others if other == value)
    return round((below + 0.5 * ties) / len(others) * 100, 1)


def _delta(value: float | None, others: list[float]) -> float | None:
    if value is None or not others:
        return None
    return round(value - sum(others) / len(others), 2)


def _deltas(own: dict, reference: list[dict]) -> dict:
    """This day's net minus the reference days' mean, P&L and R apiece.

    `reference` already excludes null-P&L days; a day with a null net R is
    dropped from the R mean only.
    """
    pnl = [s["net_pnl_amount"] for s in reference]
    r = [s["net_r"] for s in reference if s["net_r"] is not None]
    return {"pnl_amount": _delta(own["net_pnl_amount"], pnl),
            "r": _delta(own["net_r"], r)}


def day_context(rows: list[dict], date: str) -> dict:
    """How `date` sits against every other trading day under the filter.

    `rows` is the filtered ALL-HISTORY row set -- the same scope the weekday
    table uses -- and each day's net is `day_summary`'s, the calendar cell's
    own rule, so this can never disagree with the grid.

    The reference set is the OTHER trading days with a known net P&L: a day
    in its own reference set inflates its percentile, and a null-dollar day
    counted as $0 drags every mean toward flat. When this day's own dollars
    are unknown the whole context is None -- there is nothing to compare.
    """
    buckets = bucket_by_day(rows)
    own = day_summary(date, buckets.get(date, []))
    reference = [day_summary(day, group) for day, group in buckets.items()
                 if day != date]
    reference = [s for s in reference if s["net_pnl_amount"] is not None]
    weekday = _weekday_of(date)
    same_weekday = [s for s in reference
                    if weekday is not None and _weekday_of(s["date"]) == weekday]
    if own["net_pnl_amount"] is None:
        nothing = {"pnl_amount": None, "r": None}
        return {"percentile": None, "history_days": len(reference),
                "vs_avg_day": dict(nothing), "vs_weekday_avg": dict(nothing)}
    return {
        "percentile": _percentile(own["net_pnl_amount"],
                                  [s["net_pnl_amount"] for s in reference]),
        "history_days": len(reference),
        "vs_avg_day": _deltas(own, reference),
        "vs_weekday_avg": _deltas(own, same_weekday),
    }


# --- v165 D3: what drove one day --------------------------------------------

# The four ways the day page splits a day. Order is the page's tab order.
BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "direction", "exit_reason")


def _breakdown_group(key: str, group: list[dict]) -> dict:
    """One breakdown row: count, summed dollars and R, win rate.

    Same rules as the day's tiles -- `_sum_or_none` (all-null is None, not
    $0) and `metrics.win_rate` over outcomes (no decided row is None, not
    0%) -- so the rows of a dimension add back up to the tiles.
    """
    return {
        "key": key,
        "n": len(group),
        "pnl_amount": _sum_or_none([r["pnl_amount"] for r in group]),
        "r": _sum_or_none([r["r_multiple"] for r in group]),
        "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in group]),
    }


def _breakdown_order(group: dict) -> tuple:
    """P&L descending, unknown P&L last, then key -- deterministic on ties."""
    pnl = group["pnl_amount"]
    return (pnl is None, -(pnl or 0.0), group["key"])


def day_breakdown(rows: list[dict]) -> dict[str, list[dict]]:
    """The day split by strategy, horizon, direction and exit reason.

    `rows` must be exactly the day's `trades` list, so each dimension's `n`
    sums to `trade_count` and its non-null P&L / R to the tiles' totals. Not
    `/analytics/by-dimension`: that scopes by trade, and on a scale-out day
    it would disagree with these per-leg rows. A missing key is "unknown".
    """
    out: dict[str, list[dict]] = {}
    for dimension in BREAKDOWN_DIMENSIONS:
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(row.get(dimension) or "unknown", []).append(row)
        out[dimension] = sorted(
            (_breakdown_group(key, group) for key, group in groups.items()),
            key=_breakdown_order,
        )
    return out


# --- v165 D4: the day drawer's / day page's summary tiles -------------------


def _leaders(rows: list[dict]) -> list[dict]:
    """The five rows with the largest |R|, as `{ticker, r}`."""
    return [
        {"ticker": row["ticker"], "r": row["r_multiple"]}
        for row in sorted(rows, key=lambda row: abs(row["r_multiple"]), reverse=True)[:5]
    ]


def _worst_drawdown_r(measured: list[float]) -> float | None:
    """Deepest peak-to-trough fall of the running R, walked in close order."""
    if not measured:
        return None
    running = peak = worst = 0.0
    for value in measured:
        running += value
        peak = max(peak, running)
        worst = max(worst, peak - running)
    return round(worst, 2)


def day_totals(day_rows: list[dict]) -> dict:
    """The day's summary tiles, over exactly the rows the day lists.

    Lifted verbatim from `api_v1/calendar.calendar_pnl_day` (v165) so the
    route stays below complexity 15 and this module stays the one place the
    calendar's arithmetic lives. `day_rows` must be in close order -- the
    drawdown walks them as the day happened.
    """
    measured_rows = [r for r in day_rows if r["r_multiple"] is not None]
    measured = [r["r_multiple"] for r in measured_rows]
    winners = [r for r in measured_rows if r["r_multiple"] > 0]
    losers = [r for r in measured_rows if r["r_multiple"] < 0]
    return {
        # `trades` stays the route's list contract; this is its numeric
        # companion for the tiles.
        "trade_count": len(day_rows),
        "winners": len(winners),
        "losers": len(losers),
        "total_r": _sum_or_none(measured),
        "total_ccy": _sum_or_none([r["pnl_amount"] for r in day_rows]),
        "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in day_rows]),
        "avg_trade_r": _avg_or_none(measured),
        "worst_drawdown_r": _worst_drawdown_r(measured),
        "contributors": _leaders(winners),
        "detractors": _leaders(losers),
    }
