#!/usr/bin/env python3
"""v183 impact: the live book's closed shorts re-sized under the gap rule.

Read-only and descriptive, never a gate (spec "Measured once, after build").
Each closed bearish paper trade is sized twice at one fixed per-trade risk
(balance x risk_pct / 100; position caps off; OPEX scaling pinned to 1.0):
on the stop, and with the v183 gap floor. The floor is the trade's stored
gap_sizing p99 when it has one, else the p99 of up-gaps over the LOOKBACK
completed daily bars before the trade opened; fewer than MIN_UP_GAPS
up-gaps means no p99 and no change. R is the book's own r_multiple (gap
fills keep their real R); dollar P&L = shares x stop distance x R.

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
from swingbot.core.planning.gap_sizing import LOOKBACK, MIN_UP_GAPS  # noqa: E402

log = logging.getLogger("short_gap_sizing_impact")

CLOSED = ("win", "loss", "closed")
NY = "America/New_York"
WORST_N = 5
SPEC = "../specs/2026-10-21-v183-short-gap-sizing-and-squeeze-notice-design.md"

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


def _with_db(url: str, name: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def closed_shorts(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("direction") == "bearish" and t.get("status") in CLOSED]


def _opened_session(trade: dict) -> pd.Timestamp:
    ts = pd.Timestamp(trade["opened_at"])
    return pd.Timestamp((ts.tz_convert(NY) if ts.tzinfo is not None else ts).date())


def _bars_p99(trade: dict, bars) -> float | None:
    if bars is None or bars.empty or not trade.get("opened_at"):
        return None
    idx = pd.DatetimeIndex(bars.index)
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    stats = gap_stats(bars[idx < _opened_session(trade)], lookback=LOOKBACK)
    return stats["p99_up_gap_pct"] if stats["n_up"] >= MIN_UP_GAPS else None


def trade_p99(trade: dict, bars) -> tuple[float | None, str]:
    stamp = trade.get("gap_sizing") or {}
    if stamp.get("up_gap_p99_pct") is not None:
        return float(stamp["up_gap_p99_pct"]), "stamp"
    p99 = _bars_p99(trade, bars)
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


def resize_trade(trade: dict, bars, cfg: dict) -> dict | None:
    r = r_multiple(trade)
    if r is None:
        return None
    entry, stop = float(trade["entry"]), float(trade["stop_loss"])
    before = compute_position_size(entry, stop, cfg)
    if before is None:
        return None
    p99, source = trade_p99(trade, bars)
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


def _summary(rows: list[dict], balance: float, risk_pct: float) -> dict:
    cut = [x for x in rows if x["gap_sized"]]
    unit = balance * risk_pct / 100.0
    return {"n_analysed": len(rows), "unit": unit,
            "n_no_p99": sum(x["p99_source"] == "none" for x in rows),
            "n_from_stamp": sum(x["p99_source"] == "stamp" for x in rows),
            "n_gap_sized": len(cut),
            "share_gap_sized_pct": 100.0 * len(cut) / len(rows) if rows else None,
            "mean_cut_pct_gap_sized": _mean([_cut_pct(x) for x in cut]),
            "mean_cut_pct_all": _mean([_cut_pct(x) for x in rows]),
            "mean_r": _mean([x["r"] for x in rows]),
            "pnl_before": round(sum(x["pnl_before"] for x in rows), 2),
            "pnl_after": round(sum(x["pnl_after"] for x in rows), 2),
            "worst_before": _worst(rows, "pnl_before"), "worst_after": _worst(rows, "pnl_after"),
            "drawdown": _drawdowns(rows, unit, risk_pct)}


def resize_closed_shorts(trades: list[dict], frames: dict, *, balance: float, risk_pct: float) -> dict:
    cfg = _fixed_cfg(balance, risk_pct)
    shorts = closed_shorts(trades)
    with _fixed_risk():
        rows = [row for t in shorts if (row := resize_trade(t, frames.get(t.get("ticker")), cfg))]
    return {"n_closed_shorts": len(shorts), "rows": rows, "summary": _summary(rows, balance, risk_pct)}


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


def _result_table(result: dict, s: dict) -> str:
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    mean_r = "n/a" if s["mean_r"] is None else f"{s['mean_r']:+.3f}R"
    rows = [
        ("Closed shorts in the book", result["n_closed_shorts"]),
        ("Analysed (R computable)", s["n_analysed"]),
        ("p99 from a stored stamp / from bars / none", f"{s['n_from_stamp']} / {n_bars} / {s['n_no_p99']}"),
        ("Gap-sized (share cut)", f"{s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})"),
        ("Mean size cut, gap-sized shorts", _pct(s["mean_cut_pct_gap_sized"])),
        ("Mean size cut, all analysed shorts", _pct(s["mean_cut_pct_all"])),
        ("Mean R (identical both sides)", mean_r),
        ("Dollar P&L at fixed risk, before", _money(s["pnl_before"])),
        ("Dollar P&L at fixed risk, after", _money(s["pnl_after"])),
    ]
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


# --------------------------------------------------------------------- main

def _trades() -> list[dict]:
    from swingbot.core.performance import TradeLog
    return TradeLog().get_trades(status="all", limit=None)


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


def _stdout_lines(result: dict) -> list[str]:
    s = result["summary"]
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    return [f"closed_shorts: {result['n_closed_shorts']}", f"analysed: {s['n_analysed']}",
            f"p99_stamp/bars/none: {s['n_from_stamp']}/{n_bars}/{s['n_no_p99']}",
            f"gap_sized: {s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})",
            f"mean_cut_gap_sized: {_pct(s['mean_cut_pct_gap_sized'])}",
            f"mean_cut_all: {_pct(s['mean_cut_pct_all'])}", f"mean_r: {_num(s['mean_r'])}",
            f"pnl_before: {_money(s['pnl_before'])}", f"pnl_after: {_money(s['pnl_after'])}"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="swingbot_prod_replica")
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    from swingbot import config
    from swingbot.core.db import engine
    config.DATABASE_URL = _with_db(config.DATABASE_URL, args.db)
    engine.reset_engine()
    trades = _trades()
    frames = _frames(sorted({t["ticker"] for t in closed_shorts(trades)}))
    result = resize_closed_shorts(trades, frames, balance=args.balance, risk_pct=args.risk_pct)
    print("\n".join(_stdout_lines(result)))
    if args.out:
        text = render_markdown(result, run_date=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
                               db_name=args.db, balance=args.balance, risk_pct=args.risk_pct)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
