#!/usr/bin/env python3
"""v172: one-off backfill of daily equity samples from raw daily bars.

Rebuilds `equity_samples` rows (source="backfill") for every NYSE session
day from the first main-book trade to the session before the first live
sample, four rows a day (spec v172 § 3):

    point    @ 09:30 NY   realized(D-1) + sum of unrealized at the bar open
    day_high @ 09:30 NY   realized(D)   + sum of favourable extremes
    day_low  @ 09:30 NY   realized(D)   + sum of adverse extremes
    point    @ 16:00 NY   realized(D)   + sum of unrealized at the bar close

Each realized leg and each open remainder is one slice. Its extremes are
clamped to the time it was held: entry day = entry price .. bar close; exit
day = bar open .. exit price (realized at the close); a same-day round trip
= entry .. exit; other days = the bar's O/H/L/C. On an exit day the
extremes are measured net of the exit price, because realized(D) already
holds that leg. The high and low are outer bounds, never measured values:
every candle built from these rows is approx.

Bars are UNADJUSTED daily bars this script fetches itself (yfinance,
auto_adjust=False) for traded tickers only, saved under
data/backfill_equity_samples/<run_id>/<TICKER>.csv. Never read here:
backtest_cache.py (adjusted), market_data/, training_data.load_daily,
fetch_backtest_data.load_cached.

    python scripts/data/backfill_equity_samples.py                       # dry run: coverage report
    python scripts/data/backfill_equity_samples.py --apply               # write days with no backfill rows
    python scripts/data/backfill_equity_samples.py --apply --replace     # rewrite every backfill row
    python scripts/data/backfill_equity_samples.py --apply --allow-gaps  # write despite missing bars
    python scripts/data/backfill_equity_samples.py --recompute-realized [--apply]

Production (after the v172 deploy):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py"
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --apply"
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import NamedTuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402
from swingbot.core.tracking import equity  # noqa: E402
from swingbot.core.tracking.performance import expand_trade_legs  # noqa: E402

SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
GAP_REASONS = ("fetch failed", "no bar")
ZERO = Decimal("0")
_HELD_STATUSES = ("open", "win", "loss", "closed")
_LIVE_PLAN_STATUSES = ("ACTIVE", "PARTIAL")
_OHLC = ("Open", "High", "Low", "Close")


class Bar(NamedTuple):
    open: float
    high: float
    low: float
    close: float


class Skip(NamedTuple):
    day: date
    trade_id: object
    ticker: str
    reason: str


class CoverageGap(Exception):
    """A slice has no bar for a day and gaps were not allowed."""


def session_bounds(day: date) -> tuple[datetime, datetime]:
    """09:30 and 16:00 New York on `day`, in UTC."""
    def at(clock: time) -> datetime:
        return datetime.combine(day, clock, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)
    return at(SESSION_OPEN), at(SESSION_CLOSE)


def _day_end(day: date) -> datetime:
    """The last instant of New York calendar day `day`, in UTC."""
    midnight = datetime.combine(day + timedelta(days=1), time(0), tzinfo=US_MARKET_TZ)
    return midnight.astimezone(timezone.utc) - timedelta(microseconds=1)


def ny_day(value) -> date | None:
    moment = equity.parse_ts(value)
    return None if moment is None else moment.astimezone(US_MARKET_TZ).date()


def filled_trades(trades: list[dict], plans_by_id: dict) -> list[dict]:
    """Main-book trades that were really filled: an open trade whose plan is
    neither ACTIVE nor PARTIAL is a PENDING placeholder and is dropped."""
    kept = []
    for trade in equity.main_book(trades):
        plan = plans_by_id.get(trade.get("plan_id"))
        if (trade.get("status") == "open" and plan is not None
                and plan.get("status") not in _LIVE_PLAN_STATUSES):
            continue
        kept.append(trade)
    return kept


def _slice(trade: dict, row: dict, entry_day: date) -> dict | None:
    status = row.get("status")
    if status not in _HELD_STATUSES:
        return None
    exit_day = None if status == "open" else ny_day(row.get("closed_at"))
    if status != "open" and exit_day is None:
        return None                       # a close with no time cannot be placed on a day
    return {"trade_id": trade.get("id"), "ticker": trade.get("ticker"),
            "direction": trade.get("direction"), "entry": trade.get("entry"),
            "shares": row.get("shares"), "entry_day": entry_day, "exit_day": exit_day,
            "exit_price": None if status == "open" else row.get("exit_price")}


def _slices(trade: dict) -> list[dict]:
    """One slice per realized leg plus the open remainder (expand_trade_legs)."""
    entry_day = ny_day(trade.get("opened_at"))
    if entry_day is None:
        return []
    slices = (_slice(trade, row, entry_day) for row in expand_trade_legs(trade))
    return [piece for piece in slices if piece is not None]


def _held_on(piece: dict, day: date) -> bool:
    return piece["entry_day"] <= day and (piece["exit_day"] is None or piece["exit_day"] >= day)


def held_positions(trades: list[dict], day: date) -> list[dict]:
    """Every main-book slice open at any point on `day` (pass `filled_trades` output)."""
    return [piece for trade in equity.main_book(trades) for piece in _slices(trade)
            if _held_on(piece, day)]


def bar_for(frame: pd.DataFrame | None, day: date) -> Bar | None:
    """The daily bar dated `day`, or None when absent or holding a NaN."""
    if frame is None or frame.empty:
        return None
    hit = frame[frame.index.date == day]
    if hit.empty:
        return None
    values = [hit.iloc[0].get(column) for column in _OHLC]
    if any(value is None or pd.isna(value) for value in values):
        return None
    return Bar(*(float(value) for value in values))


def _path(pos: dict, bar: Bar, day: date) -> tuple[list[float], float | None, float | None]:
    """(prices the slice was exposed to on `day`, its open price, its close price).

    No lookahead: the entry day never reads the bar's open/high/low, the exit
    day never its high/low/close."""
    entered, exited = pos["entry_day"] == day, pos["exit_day"] == day
    first = pos["entry"] if entered else bar.open
    last = pos["exit_price"] if exited else bar.close
    inner = [] if entered or exited else [bar.high, bar.low]
    return [first, *inner, last], (None if entered else bar.open), (None if exited else bar.close)


def position_day(pos: dict, bar: Bar, day: date) -> dict:
    """One slice's unrealized amounts on `day`: at the open, its favourable and
    adverse extremes, and at the close (Decimals, unrounded)."""
    def pnl(price: float) -> Decimal:
        return equity.unrealized_decimal(pos["entry"], pos["direction"], pos["shares"], price)

    path, open_price, close_price = _path(pos, bar, day)
    banked = pnl(pos["exit_price"]) if pos["exit_day"] == day else ZERO
    values = [pnl(price) - banked for price in path]
    return {"open_u": ZERO if open_price is None else pnl(open_price),
            "high_u": max(values), "low_u": min(values),
            "close_u": ZERO if close_price is None else pnl(close_price)}


def _unpriceable(pos: dict, day: date) -> str | None:
    if not pos["shares"]:
        return "no size"
    if pos["entry"] is None:
        return "no entry"
    if pos["exit_day"] == day and pos["exit_price"] is None:
        return "no exit price"
    return None


def _priceable(pos: dict, frame: pd.DataFrame | None, day: date) -> tuple[str | None, Bar | None]:
    reason = _unpriceable(pos, day)
    if reason:
        return reason, None
    bar = bar_for(frame, day)
    if bar is None:
        return ("fetch failed" if frame is None or frame.empty else "no bar"), None
    return None, bar


def _price_positions(day: date, positions: list[dict], bars: dict, *,
                     allow_gaps: bool) -> tuple[dict, int, list[Skip]]:
    totals = dict.fromkeys(("open_u", "high_u", "low_u", "close_u"), ZERO)
    counted, skips = 0, []
    for pos in positions:
        reason, bar = _priceable(pos, bars.get(pos["ticker"]), day)
        if reason in GAP_REASONS and not allow_gaps:
            raise CoverageGap(f"{pos['ticker']} on {day}: {reason}")
        if reason:
            skips.append(Skip(day, pos["trade_id"], pos["ticker"], reason))
            continue
        for key, value in position_day(pos, bar, day).items():
            totals[key] += value
        counted += 1
    return totals, counted, skips


def _row(at: datetime, kind: str, realized: Decimal, unrealized: Decimal, counted: int,
         skipped: int, run_tag: str) -> dict:
    return {"at": at, "realized_balance": realized, "unrealized_pnl": unrealized,
            "equity": realized + unrealized, "open_n": counted, "skipped_n": skipped,
            "source": "backfill", "kind": kind, "backfill_run": run_tag}


def build_day_rows(day: date, positions: list[dict], bars: dict[str, pd.DataFrame],
                   legs: Sequence[equity.RealizedLeg], start: Decimal, run_tag: str, *,
                   allow_gaps: bool) -> tuple[list[dict], list[Skip]]:
    """The four backfill rows for session `day`, and the slices left out."""
    totals, counted, skips = _price_positions(day, positions, bars, allow_gaps=allow_gaps)
    open_at, close_at = session_bounds(day)
    before = equity.realized_balance_at(start, legs, _day_end(day - timedelta(days=1)))
    after = equity.realized_balance_at(start, legs, _day_end(day))
    common = (counted, len(skips), run_tag)
    return [
        _row(open_at, "point", before, totals["open_u"], *common),
        _row(open_at, "day_high", after, totals["high_u"], *common),
        _row(open_at, "day_low", after, totals["low_u"], *common),
        _row(close_at, "point", after, totals["close_u"], *common),
    ], skips
