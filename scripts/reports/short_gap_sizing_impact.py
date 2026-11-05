#!/usr/bin/env python3
"""v183/v191 impact: the live book's closed shorts (and, with --side, longs) re-sized under the gap rule.

Read-only and descriptive, never a gate (spec "Measured once, after build").
Each closed bearish paper trade is sized twice at one fixed per-trade risk
(balance x risk_pct / 100; position caps off; OPEX scaling pinned to 1.0):
on the stop, and with the v183 gap floor. The floor is the trade's stored
gap_sizing p99 when it has one, else the p99 of up-gaps over the LOOKBACK
completed daily bars before the trade opened; fewer than MIN_UP_GAPS
up-gaps means no p99 and no change. R is the book's own r_multiple (gap
fills keep their real R); dollar P&L = shares x stop distance x R.

--side long (v191 Part B) re-sizes closed longs with the p99 DOWN-gap (stored
down_gap_p99_pct stamp, else the bars before the open, fewer than MIN_DOWN_GAPS:
no change); --side both writes the short document, then the long one. The
default, short, is byte-identical to the v183 report.

Run locally after /replicate-prod-db, never on production (it has no v183
sizing until deploy). Prints no .env value:
    python scripts/reports/short_gap_sizing_impact.py --db swingbot_prod_replica \
        --out docs/superpowers/results/<run-date>-v183-gap-sizing-impact.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.metrics import r_multiple  # noqa: E402
from swingbot.core.analytics.risk_metrics import max_drawdown_r  # noqa: E402
from swingbot.core.edge import ruin  # noqa: E402
from swingbot.core.edge.gates import gap_stats  # noqa: E402
from swingbot.core.market import opex  # noqa: E402
from swingbot.core.planning.account import compute_position_size  # noqa: E402
from swingbot.core.planning.gap_sizing import LOOKBACK, MIN_DOWN_GAPS, MIN_UP_GAPS  # noqa: E402

log = logging.getLogger("short_gap_sizing_impact")

CLOSED = ("win", "loss", "closed")
NY = "America/New_York"
WORST_N = 5
SPEC = "../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md"

LONG_SPEC = "../specs/implemented/2026-10-24-v191-confluence-atr-band-stops-design.md"
#: A loss past the fixed risk by more than this is an exceedance; less is the
#: rounding noise of 0.01-share sizing.
EXCEED_TOL_DOLLARS = 0.5


class Side(NamedTuple):
    name: str          # "short" | "long"
    direction: str     # the book's direction for this side
    stamp_key: str     # the stored gap_sizing p99 key
    stats_key: str     # the gap_stats p99 key
    count_key: str     # the gap_stats count key
    min_gaps: int      # fewer gaps: no usable p99


SHORT = Side("short", "bearish", "up_gap_p99_pct", "p99_up_gap_pct", "n_up", MIN_UP_GAPS)
LONG = Side("long", "bullish", "down_gap_p99_pct", "p99_down_gap_pct", "n_down", MIN_DOWN_GAPS)
SIDES = {"short": SHORT, "long": LONG}

LIMITS = (
    "- p99 over about 125 up-gaps is roughly the one or two largest up-gaps of the year: noisy, accepted in the spec.\n"
    "- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; "
    "with the live caps the cut is the same or smaller.\n"
    "- Trades opened before v183 shipped carry no stamp; their p99 is recomputed from the cached daily bars "
    "before the open, so a bar-cache gap shows up as `none` (size unchanged).\n"
    "- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); "
    "only dollars move.\n"
)

ROLLBACK_NOTE = (
    "- **No deploy needed:** set `SHORT_GAP_SIZING=false` (and `SHORT_RISK_NOTICE=false` for the notice) in `.env` "
    "or the admin config page; the bot hot-reloads. Plans stamped while the switch was on keep their stamped rule; "
    "plans created after the flip size on the stop exactly as before v183.\n"
    "- **Code rollback** (`scripts/ops/rollback_to.sh`): the `gap_sizing` / `risk_notice` keys on plan docs and "
    "trade records and the `data/short_interest.json` cache are left in place, unread and harmless.\n"
    "- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.\n"
)


LONG_LIMITS = (
    "- p99 over about 125 down-gaps is roughly the one or two largest down-gaps of the year: noisy, "
    "the same limit v183 accepted for shorts.\n"
    "- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; "
    "with the live caps the cut is the same or smaller.\n"
    "- No long carried a down-gap stamp before v191 shipped; its p99 is recomputed from the cached daily bars "
    "before the open, so a bar-cache gap shows up as `none` (size unchanged).\n"
    "- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); "
    "only dollars move.\n"
    "- A gap beyond the ticker's own p99 can still exceed the budget; the exceedance rows count those losses.\n"
)

LONG_ROLLBACK_NOTE = (
    "- **No deploy needed:** set `LONG_GAP_SIZING=false` in `.env` or the admin config page; the bot hot-reloads. "
    "A live `CONFLUENCE_ATR_STOP_FLOOR > 0` is honoured only with `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` "
    "both on, so turning this off also zeroes a live floor (logged at ERROR).\n"
    "- Plans stamped while the switch was on keep their stamped rule; long plans created after the flip "
    "size on the stop exactly as before v191.\n"
    "- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.\n"
)


def _with_db(url: str, name: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def _target(db: str, configured: str) -> tuple[str, str]:
    """(url, database name): --db is a database name on the configured server, or a full URL."""
    from sqlalchemy.engine import make_url
    url = db if "://" in db else _with_db(configured, db)
    return url, make_url(url).database


def closed_side(trades: list[dict], side: Side) -> list[dict]:
    return [t for t in trades if t.get("direction") == side.direction and t.get("status") in CLOSED]


def closed_shorts(trades: list[dict]) -> list[dict]:
    return closed_side(trades, SHORT)


def _opened_session(trade: dict) -> pd.Timestamp:
    ts = pd.Timestamp(trade["opened_at"])
    return pd.Timestamp((ts.tz_convert(NY) if ts.tzinfo is not None else ts).date())


def _bars_p99(trade: dict, bars, side: Side = SHORT) -> float | None:
    if bars is None or bars.empty or not trade.get("opened_at"):
        return None
    idx = pd.DatetimeIndex(bars.index)
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    stats = gap_stats(bars[idx < _opened_session(trade)], lookback=LOOKBACK)
    return stats[side.stats_key] if stats[side.count_key] >= side.min_gaps else None


def trade_p99(trade: dict, bars, side: Side = SHORT) -> tuple[float | None, str]:
    stamp = trade.get("gap_sizing") or {}
    if stamp.get(side.stamp_key) is not None:
        return float(stamp[side.stamp_key]), "stamp"
    p99 = _bars_p99(trade, bars, side)
    return (p99, "bars") if p99 is not None else (None, "none")


def _fixed_cfg(balance: float, risk_pct: float) -> dict:
    return {"balance": balance, "risk_pct": risk_pct, "sizing_mode": "risk_pct",
            "max_position_pct": 1e9, "max_position_value_absolute": 0.0,
            "max_risk_amount_absolute": 0.0}


@contextmanager
def _fixed_risk():
    """OPEX weeks scale risk_pct by the run date; this report fixes per-trade risk."""
    with mock.patch.object(opex, "size_mult", return_value=1.0):
        yield


def resize_trade(trade: dict, bars, cfg: dict, side: Side = SHORT) -> dict | None:
    r = r_multiple(trade)
    if r is None:
        return None
    entry, stop = float(trade["entry"]), float(trade["stop_loss"])
    before = compute_position_size(entry, stop, cfg)
    if before is None:
        return None
    p99, source = trade_p99(trade, bars, side)
    after = before if p99 is None else compute_position_size(entry, stop, cfg, gap_floor_pct=p99)
    dist = abs(entry - stop)
    return {"id": trade.get("id"), "ticker": trade.get("ticker"), "closed_at": trade.get("closed_at") or "",
            "r": r, "p99": p99, "p99_source": source,
            "shares_before": before["shares"], "shares_after": after["shares"],
            "gap_sized": bool(after.get("gap_sized")),
            "pnl_before": round(before["shares"] * dist * r, 2),
            "pnl_after": round(after["shares"] * dist * r, 2)}


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _cut_pct(row: dict) -> float:
    return 100.0 * (1.0 - row["shares_after"] / row["shares_before"]) if row["shares_before"] else 0.0


def _worst(rows: list[dict], key: str) -> list[dict]:
    keep = ("ticker", "closed_at", "r", "pnl_before", "pnl_after")
    return [{k: row[k] for k in keep} for row in sorted(rows, key=lambda x: x[key])[:WORST_N]]


def _side_drawdown(pnls: list[float], unit: float, risk_pct: float) -> dict:
    out = {"max_dd_dollars": max_drawdown_r(pnls), "bootstrap_dd_p50": None, "bootstrap_dd_p95": None}
    if pnls and unit > 0:
        sim = ruin.simulate([p / unit for p in pnls], risk_pct=risk_pct)
        out["bootstrap_dd_p50"], out["bootstrap_dd_p95"] = sim["max_dd_p50"], sim["max_dd_p95"]
    return out


def _drawdowns(rows: list[dict], unit: float, risk_pct: float) -> dict:
    ordered = sorted(rows, key=lambda x: x["closed_at"])
    return {side: _side_drawdown([x[f"pnl_{side}"] for x in ordered], unit, risk_pct)
            for side in ("before", "after")}


def _sizing_measures(rows: list[dict]) -> dict:
    cut = [x for x in rows if x["gap_sized"]]
    return {"n_analysed": len(rows),
            "n_no_p99": sum(x["p99_source"] == "none" for x in rows),
            "n_from_stamp": sum(x["p99_source"] == "stamp" for x in rows),
            "n_gap_sized": len(cut),
            "share_gap_sized_pct": 100.0 * len(cut) / len(rows) if rows else None,
            "mean_cut_pct_gap_sized": _mean([_cut_pct(x) for x in cut]),
            "mean_cut_pct_all": _mean([_cut_pct(x) for x in rows]),
            "mean_r": _mean([x["r"] for x in rows])}


def _summary(rows: list[dict], balance: float, risk_pct: float) -> dict:
    unit = balance * risk_pct / 100.0
    return {**_sizing_measures(rows), "unit": unit,
            "pnl_before": round(sum(x["pnl_before"] for x in rows), 2),
            "pnl_after": round(sum(x["pnl_after"] for x in rows), 2),
            "n_exceed_before": sum(x["pnl_before"] < -(unit + EXCEED_TOL_DOLLARS) for x in rows),
            "n_exceed_after": sum(x["pnl_after"] < -(unit + EXCEED_TOL_DOLLARS) for x in rows),
            "worst_before": _worst(rows, "pnl_before"), "worst_after": _worst(rows, "pnl_after"),
            "drawdown": _drawdowns(rows, unit, risk_pct)}


def resize_closed(trades: list[dict], frames: dict, *, side: Side, balance: float,
                  risk_pct: float) -> dict:
    cfg = _fixed_cfg(balance, risk_pct)
    closed = closed_side(trades, side)
    with _fixed_risk():
        rows = [row for t in closed
                if (row := resize_trade(t, frames.get(t.get("ticker")), cfg, side))]
    return {f"n_closed_{side.name}s": len(closed), "rows": rows,
            "summary": _summary(rows, balance, risk_pct)}


def resize_closed_shorts(trades: list[dict], frames: dict, *, balance: float, risk_pct: float) -> dict:
    return resize_closed(trades, frames, side=SHORT, balance=balance, risk_pct=risk_pct)


# ---------------------------------------------------------------- rendering

def _money(x) -> str:
    if x is None:
        return "n/a"
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def _pct(x, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}%"


def _num(x) -> str:
    return "n/a" if x is None else str(x)


def _r(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}R"


def _worst_table(entries: list[dict]) -> str:
    head = "| Ticker | Closed | R | $ before | $ after |\n|---|---|---|---|---|\n"
    if not entries:
        return head + "| n/a | n/a | n/a | n/a | n/a |\n"
    return head + "".join(
        f"| {e['ticker']} | {str(e['closed_at'])[:10]} | {_r(e['r'])} | "
        f"{_money(e['pnl_before'])} | {_money(e['pnl_after'])} |\n" for e in entries)


def _exceed_rows(s: dict, side: Side) -> list:
    if side is SHORT:
        return []
    return [("Losses past the fixed risk, before", s["n_exceed_before"]),
            ("Losses past the fixed risk, after", s["n_exceed_after"])]


def _result_table(result: dict, s: dict, side: Side = SHORT) -> str:
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    mean_r = "n/a" if s["mean_r"] is None else f"{s['mean_r']:+.3f}R"
    plural = f"{side.name}s"
    rows = [
        (f"Closed {plural} in the book", result[f"n_closed_{plural}"]),
        ("Analysed (R computable)", s["n_analysed"]),
        ("p99 from a stored stamp / from bars / none", f"{s['n_from_stamp']} / {n_bars} / {s['n_no_p99']}"),
        ("Gap-sized (share cut)", f"{s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})"),
        (f"Mean size cut, gap-sized {plural}", _pct(s["mean_cut_pct_gap_sized"])),
        (f"Mean size cut, all analysed {plural}", _pct(s["mean_cut_pct_all"])),
        ("Mean R (identical both sides)", mean_r),
        ("Dollar P&L at fixed risk, before", _money(s["pnl_before"])),
        ("Dollar P&L at fixed risk, after", _money(s["pnl_after"])),
    ] + _exceed_rows(s, side)
    return "| Measure | Value |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)


def _scaled(x, factor: float):
    return None if x is None else x * factor


def _drawdown_table(s: dict, balance: float) -> str:
    b, a = s["drawdown"]["before"], s["drawdown"]["after"]

    def line(label, fn):
        return f"| {label} | {fn(b)} | {fn(a)} |\n"

    return ("| Measure | Before | After |\n|---|---|---|\n"
            + line("Max drawdown, $ in close order", lambda d: _money(d["max_dd_dollars"]))
            + line("Max drawdown, % of balance", lambda d: _pct(_scaled(d["max_dd_dollars"], 100 / balance)))
            + line("Bootstrap max drawdown p50 (ruin.simulate, 1000 trades x 2000 paths)",
                   lambda d: _pct(_scaled(d["bootstrap_dd_p50"], 100)))
            + line("Bootstrap max drawdown p95", lambda d: _pct(_scaled(d["bootstrap_dd_p95"], 100))))


def render_markdown(result: dict, *, run_date: str, db_name: str, balance: float, risk_pct: float) -> str:
    s = result["summary"]
    return (
        "# v183 gap sizing impact: the live book's closed shorts re-sized\n\n"
        f"**Spec:** [v183 design]({SPEC}) § \"Measured once, after build (not a gate)\"\n"
        f"**Run:** {run_date} on `{db_name}` (read-only replica of production), "
        "`scripts/reports/short_gap_sizing_impact.py`\n"
        "**Status:** descriptive, not a gate. The cut stays unvalidated; "
        "`SHORT_GAP_SIZING=false` is the revert path.\n\n"
        "## What is measured\n\n"
        "Each closed short (status win/loss/closed, direction bearish) is sized twice at a fixed risk of "
        f"{_money(s['unit'])} per trade (balance {_money(balance)}, {risk_pct}%): on the stop, and with the gap "
        "floor `max(|entry - stop|, entry x p99_up_gap / 100)`. p99 source: the trade's stored stamp, else the "
        "up-gaps over the 250 completed daily bars before the open (fewer than 60 up-gaps: no p99, no change). "
        "Dollar P&L = shares x stop distance x the book's R.\n\n"
        f"## Result\n\n{_result_table(result, s)}\n"
        "## Worst five dollar losses\n\nBefore (stop sizing):\n\n"
        f"{_worst_table(s['worst_before'])}\nAfter (gap sizing):\n\n{_worst_table(s['worst_after'])}\n"
        f"## Short-book drawdown\n\n{_drawdown_table(s, balance)}\n"
        f"## Limits\n\n{LIMITS}\n## Rollback\n\n{ROLLBACK_NOTE}"
    )


def render_long_markdown(result: dict, *, run_date: str, db_name: str, balance: float,
                         risk_pct: float) -> str:
    s = result["summary"]
    return (
        "# v191 gap sizing impact: the live book's closed longs re-sized\n\n"
        f"**Spec:** [v191 design]({LONG_SPEC}) § \"Part B — gap-aware dollar sizing for longs and shorts\"\n"
        f"**Run:** {run_date} on `{db_name}` (read-only replica of production), "
        "`scripts/reports/short_gap_sizing_impact.py --side long`\n"
        "**Status:** descriptive, not a gate. `LONG_GAP_SIZING=false` is the revert path.\n\n"
        "## What is measured\n\n"
        "Each closed long (status win/loss/closed, direction bullish) is sized twice at a fixed risk of "
        f"{_money(s['unit'])} per trade (balance {_money(balance)}, {risk_pct}%): on the stop, and with the gap "
        "floor `max(|entry - stop|, entry x p99_down_gap / 100)`. p99 source: the trade's stored stamp, else the "
        "down-gaps over the 250 completed daily bars before the open (fewer than 60 down-gaps: no p99, no change). "
        "Dollar P&L = shares x stop distance x the book's R. An exceedance is a dollar loss past the fixed risk.\n\n"
        f"## Result\n\n{_result_table(result, s, LONG)}\n"
        "## Worst five dollar losses\n\nBefore (stop sizing):\n\n"
        f"{_worst_table(s['worst_before'])}\nAfter (gap sizing):\n\n{_worst_table(s['worst_after'])}\n"
        f"## Long-book drawdown\n\n{_drawdown_table(s, balance)}\n"
        f"## Limits\n\n{LONG_LIMITS}\n## Rollback\n\n{LONG_ROLLBACK_NOTE}"
    )


def _render(result: dict, side: Side, **kw) -> str:
    return render_markdown(result, **kw) if side is SHORT else render_long_markdown(result, **kw)

# --------------------------------------------------------------------- main

def _trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status="all", limit=None)


def _csv_frames(tickers, dirs: list[Path]) -> dict:
    """Daily bars from local CSV caches; per ticker the file with the latest last bar wins."""
    out = {}
    for tk in tickers:
        best = None
        for d in dirs:
            p = d / f"{tk}.csv"
            if not p.is_file():
                continue
            df = pd.read_csv(p, index_col=0, parse_dates=True)
            if len(df) and (best is None or df.index[-1] > best.index[-1]):
                best = df
        out[tk] = best
    return out


def _frames(tickers) -> dict:
    from swingbot.core.marketdata.data import get_daily_data
    out = {}
    for tk in tickers:
        try:
            out[tk] = get_daily_data(tk, period="5y")
        except Exception as exc:  # noqa: BLE001 - a cold cache must not abort the report
            log.warning("%s: no daily bars (%s)", tk, exc)
            out[tk] = None
    return out


def _stdout_lines(result: dict, side: Side = SHORT) -> list[str]:
    s = result["summary"]
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    plural = f"{side.name}s"
    lines = [f"closed_{plural}: {result[f'n_closed_{plural}']}", f"analysed: {s['n_analysed']}",
             f"p99_stamp/bars/none: {s['n_from_stamp']}/{n_bars}/{s['n_no_p99']}",
             f"gap_sized: {s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})",
             f"mean_cut_gap_sized: {_pct(s['mean_cut_pct_gap_sized'])}",
             f"mean_cut_all: {_pct(s['mean_cut_pct_all'])}", f"mean_r: {_num(s['mean_r'])}",
             f"pnl_before: {_money(s['pnl_before'])}", f"pnl_after: {_money(s['pnl_after'])}"]
    if side is not SHORT:
        lines.append(f"exceed_before/after: {s['n_exceed_before']}/{s['n_exceed_after']}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="swingbot_prod_replica",
                    help="database name on the configured server, or a full URL (never printed)")
    ap.add_argument("--bars-dir", type=Path, action="append", default=[],
                    help="folder of {TICKER}.csv daily bars (repeatable, freshest file wins); "
                         "default: get_daily_data (network)")
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--side", choices=("short", "long", "both"), default="short",
                    help="which closed trades to re-size (v191 adds long and both; default short, the v183 report)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    from swingbot import config
    from swingbot.core.db import engine
    config.DATABASE_URL, db_name = _target(args.db, config.DATABASE_URL)
    engine.reset_engine()
    sides = [SHORT, LONG] if args.side == "both" else [SIDES[args.side]]
    trades = _trades()
    tickers = sorted({t["ticker"] for side in sides for t in closed_side(trades, side)})
    frames = _csv_frames(tickers, args.bars_dir) if args.bars_dir else _frames(tickers)
    results = [(side, resize_closed(trades, frames, side=side, balance=args.balance,
                                    risk_pct=args.risk_pct)) for side in sides]
    print("\n".join(line for side, result in results for line in _stdout_lines(result, side)))
    if args.out:
        run_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        text = "\n".join(_render(result, side, run_date=run_date, db_name=db_name,
                                 balance=args.balance, risk_pct=args.risk_pct)
                         for side, result in results)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
