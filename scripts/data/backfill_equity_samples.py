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
holds that leg. On entry and exit days only the endpoints are used, so the
wick may UNDER-state the real intraday range; it is an estimate, never a
measured value: every candle built from these rows is approx.

Bars are daily bars this script fetches itself (yfinance, auto_adjust=False,
which is still split-adjusted while fills are raw) for traded tickers only, saved under
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

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.db.repositories.equity_samples import equity_samples_repo  # noqa: E402
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar  # noqa: E402
from swingbot.core.tracking import equity  # noqa: E402
from swingbot.core.tracking.performance import expand_trade_legs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DRY_RUN_NOTE = "Dry run only -- pass --apply to write."
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SPLIT_REASON = "bar mismatch (split?)"
GAP_REASONS = ("fetch failed", "no bar", SPLIT_REASON)
BAR_TOLERANCE = 0.05
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


def _outside(price: float | None, bar: Bar) -> bool:
    return price is not None and not (bar.low * (1 - BAR_TOLERANCE) <= price
                                      <= bar.high * (1 + BAR_TOLERANCE))


def _fill_off_bar(pos: dict, bar: Bar, day: date) -> bool:
    """A raw fill far outside its own day's bar: the bar is split-adjusted, the fill is not."""
    return ((pos["entry_day"] == day and _outside(pos["entry"], bar))
            or (pos["exit_day"] == day and _outside(pos["exit_price"], bar)))


def _priceable(pos: dict, frame: pd.DataFrame | None, day: date) -> tuple[str | None, Bar | None]:
    reason = _unpriceable(pos, day)
    if reason:
        return reason, None
    bar = bar_for(frame, day)
    if bar is None:
        return ("fetch failed" if frame is None or frame.empty else "no bar"), None
    if _fill_off_bar(pos, bar, day):
        return SPLIT_REASON, None
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


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_raw_bars(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Daily bars (auto_adjust=False), start..end inclusive (yfinance's `end` is exclusive).
    auto_adjust=False skips dividend adjustment only; prices stay split-adjusted
    while fills are raw, so `_fill_off_bar` flags a fill far outside its day's bar."""
    frame = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                        interval="1d", auto_adjust=False, progress=False)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(_OHLC))
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame[list(_OHLC)]


def _load_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def backfill_days(trades: list[dict], repo, today: date) -> list[date]:
    """NYSE sessions from the earliest entry day to the session before the first live sample."""
    entries = [piece["entry_day"] for trade in equity.main_book(trades) for piece in _slices(trade)]
    if not entries:
        return []
    first_live = repo.earliest_at("live")
    stop = ny_day(first_live) if first_live is not None else today
    return nyse_calendar().sessions(min(entries), stop - timedelta(days=1))


def _spans(trades: list[dict], days: list[date]) -> dict[str, tuple[date, date]]:
    """Per ticker, the first and last backfill day it was held: one fetch each."""
    spans: dict[str, tuple[date, date]] = {}
    for day in days:
        for pos in held_positions(trades, day):
            first, last = spans.get(pos["ticker"], (day, day))
            spans[pos["ticker"]] = (min(first, day), max(last, day))
    return spans


def _fetch_all(spans: dict, bars_fn, out_dir: Path) -> dict[str, pd.DataFrame | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame | None] = {}
    for ticker, (start, end) in sorted(spans.items()):
        try:
            frame = bars_fn(ticker, start, end)
        except Exception as exc:                       # a failed fetch is a coverage gap
            print(f"  {ticker}: fetch failed ({exc})")
            frame = None
        if frame is not None and not frame.empty:
            frame.to_csv(out_dir / f"{ticker}.csv")
        frames[ticker] = frame
    return frames


def _bars_asof(frames: dict) -> str:
    dates = [frame.index.max().date() for frame in frames.values()
             if frame is not None and not frame.empty]
    return max(dates).isoformat() if dates else "none"


def _build_all(days, trades, frames, legs, start, run_tag) -> tuple[list[dict], list[Skip]]:
    rows: list[dict] = []
    skips: list[Skip] = []
    for day in days:
        day_rows, day_skips = build_day_rows(day, held_positions(trades, day), frames, legs,
                                             start, run_tag, allow_gaps=True)
        rows.extend(day_rows)
        skips.extend(day_skips)
    return rows, skips


def _write(repo, rows: list[dict], *, replace: bool) -> int:
    rows = [{**row, "backfill_run": row.get("backfill_run")} for row in rows]   # same keys on every row
    if replace:
        return repo.replace_backfill(rows)
    existing = repo.backfill_session_dates()
    fresh = [row for row in rows if ny_day(row["at"]) not in existing]
    return repo.upsert_many(fresh) if fresh else 0


def recompute_realized(repo, trades: list[dict], *, apply: bool) -> int:
    """Live rows whose stored realized balance differs from today's trade log;
    with `apply`, rewrite realized_balance and equity, keeping unrealized_pnl."""
    legs, start, changed = equity.realized_legs(trades), equity.starting_balance(), 0
    for row in repo.list_rows(sources=("live",)):
        realized = equity.realized_balance_at(start, legs, row["at"])
        if float(realized.quantize(Decimal("0.01"), ROUND_HALF_UP)) == row.get("realized_balance"):
            continue
        changed += 1
        if apply:
            repo.update_realized(row["id"], realized,
                                 realized + Decimal(str(row.get("unrealized_pnl") or 0)))
    return changed


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Write. Default is a dry run that only reports.")
    parser.add_argument("--replace", action="store_true",
                        help="With --apply: delete every backfill row and rewrite them, one transaction.")
    parser.add_argument("--allow-gaps", action="store_true",
                        help="With --apply: write despite missing bars (left out, counted in skipped_n).")
    parser.add_argument("--recompute-realized", action="store_true",
                        help="Rewrite realized_balance/equity on live rows from the current trade log.")
    return parser.parse_args(argv)


def _summary(run_id: str, **values) -> dict:
    return {"run_id": run_id, "bars_asof": None, "days": 0, "rows": 0, "written": 0,
            "gaps": 0, "skipped": 0, "recomputed": 0, **values}


def _run_recompute(args, repo, trades, run_id: str) -> dict:
    count = recompute_realized(repo, trades, apply=args.apply)
    print(f"{'APPLIED' if args.apply else 'DRY RUN'}: recompute-realized changed={count}")
    if not args.apply:
        print(DRY_RUN_NOTE)
    return _summary(run_id, recomputed=count)


def _report(summary: dict, days: list[date], skips: list[Skip]) -> None:
    print(f"run id: {summary['run_id']}")
    print(f"bars as-of: {summary['bars_asof']}")
    span = f"{days[0]}..{days[-1]}" if days else "none"
    print(f"days covered: {summary['days']} ({span})")
    for skip in skips:
        print(f"  skipped {skip.day} {skip.ticker} trade {skip.trade_id}: {skip.reason}")


def _apply(args, repo, rows: list[dict], gaps: int) -> int:
    if gaps and not args.allow_gaps:
        print(f"REFUSED: {gaps} coverage gap(s). Re-run the dry run (a fetch can fail "
              "transiently) before considering --allow-gaps.")
        return 0
    if args.replace and not rows:
        print("REFUSED: --replace built no rows; it would delete every backfill row "
              "and insert nothing.")
        return 0
    written = _write(repo, rows, replace=args.replace)
    print(f"APPLIED: written={written}")
    return written


def _finish(args, repo, summary: dict, rows: list[dict]) -> dict:
    if args.apply:
        summary["written"] = _apply(args, repo, rows, summary["gaps"])
    else:
        print(f"DRY RUN: rows={len(rows)} gaps={summary['gaps']} skipped={summary['skipped']}")
        print(DRY_RUN_NOTE)
    return summary


def main(argv: list[str] | None = None, *, bars_fn=None, repo=None, trades_fn=None,
         plans_fn=None, today: date | None = None, out_dir: Path | None = None) -> dict:
    args = _parse(argv)
    repo = repo or equity_samples_repo()
    run_id = new_run_id()
    trades = (trades_fn or _load_trades)()
    if args.recompute_realized:
        return _run_recompute(args, repo, trades, run_id)
    filled = filled_trades(trades, (plans_fn or equity.load_plans_by_id)())   # drops PENDING placeholders
    days = backfill_days(filled, repo, today or datetime.now(US_MARKET_TZ).date())
    frames = _fetch_all(_spans(filled, days), bars_fn or fetch_raw_bars,
                        out_dir or ROOT / "data" / "backfill_equity_samples" / run_id)
    bars_asof = _bars_asof(frames)
    rows, skips = _build_all(days, filled, frames, equity.realized_legs(trades),
                             equity.starting_balance(), f"{run_id}@bars-asof-{bars_asof}")
    gaps = sum(1 for skip in skips if skip.reason in GAP_REASONS)
    summary = _summary(run_id, bars_asof=bars_asof, days=len(days), rows=len(rows),
                       gaps=gaps, skipped=len(skips))
    _report(summary, days, skips)
    return _finish(args, repo, summary, rows)


if __name__ == "__main__":
    main()
