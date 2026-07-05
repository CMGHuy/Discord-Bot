#!/usr/bin/env python3
"""
2025 Watchlist Backtest Runner
================================
Run this on your server where yfinance can reach Yahoo Finance:

    cd /app && python3 run_backtest_2025.py

Outputs:
  - backtest_2025_results.json   — full trade-level data
  - backtest_2025_summary.txt    — human-readable digest

The script uses one_at_a_time=True (one open trade per strategy/horizon),
so the numbers reflect realistic capital use rather than stacked overlaps.
"""
import json
import sys
import warnings
from collections import defaultdict
from datetime import datetime

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance not installed: pip install yfinance")

import numpy as np
import pandas as pd

from swingbot.core.backtest import run_backtest, ALL_STRATEGIES
from swingbot.core.strategy import HORIZONS
from swingbot.config import WATCHLIST

# ─── Config ───────────────────────────────────────────────────────────────────
DATE_FROM = "2024-06-01"   # extra warm-up before 2025 so indicators are ready
DATE_TO   = "2025-12-31"
EVAL_FROM = "2025-01-01"   # only count trades whose entry is in 2025
EVAL_TO   = "2025-12-31"
# ──────────────────────────────────────────────────────────────────────────────


def download(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, start=DATE_FROM, end=DATE_TO, auto_adjust=True, progress=False)
        if df.empty or len(df) < 60:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"  ✗ {ticker}: download error — {e}")
        return None


def filter_trades_to_year(summary, date_from: str, date_to: str):
    """Keep only trades whose entry_date is within the evaluation window."""
    from swingbot.core.backtest import BacktestSummary, BacktestTrade
    filtered_trades = [
        t for t in summary.trades
        if t.entry_date and date_from <= t.entry_date <= date_to
    ]
    evaluated = [t for t in filtered_trades if t.outcome in ("win", "loss")]
    wins      = [t for t in evaluated if t.outcome == "win"]
    losses    = [t for t in evaluated if t.outcome == "loss"]
    timeouts  = [t for t in filtered_trades if t.outcome == "timeout"]

    win_rate   = len(wins) / len(evaluated) * 100 if evaluated else None
    avg_ret    = float(np.mean([t.return_pct  for t in evaluated])) if evaluated else None
    avg_r      = float(np.mean([t.r_multiple  for t in evaluated])) if evaluated else None
    avg_hold   = float(np.mean([t.holding_days for t in evaluated])) if evaluated else None
    expectancy = None
    if evaluated:
        p = len(wins) / len(evaluated)
        aw = float(np.mean([t.r_multiple for t in wins]))   if wins   else 0.0
        al = float(np.mean([t.r_multiple for t in losses])) if losses else 0.0
        expectancy = p * aw + (1 - p) * al

    return BacktestSummary(
        ticker=summary.ticker, strategy=summary.strategy, horizon_key=summary.horizon_key,
        total_signals=len(filtered_trades),
        evaluated=len(evaluated), wins=len(wins), losses=len(losses), timeouts=len(timeouts),
        win_rate=win_rate, avg_return_pct=avg_ret, avg_r_multiple=avg_r,
        expectancy_r=expectancy, max_drawdown_pct=summary.max_drawdown_pct,
        avg_holding_days=avg_hold, trades=filtered_trades,
    )


def run_all():
    print(f"\n{'='*60}")
    print(f"  2025 Backtest — {len(WATCHLIST)} tickers × {len(ALL_STRATEGIES)} strategies × {len(HORIZONS)} horizons")
    print(f"  Eval window: {EVAL_FROM} → {EVAL_TO}")
    print(f"{'='*60}\n")

    all_summaries = []
    failed = []

    for ticker in sorted(WATCHLIST):
        print(f"  Downloading {ticker}...", end=" ", flush=True)
        df = download(ticker)
        if df is None:
            print("SKIP (no data)")
            failed.append(ticker)
            continue
        print(f"{len(df)} bars", end=" ", flush=True)

        ticker_results = []
        for horizon_key in HORIZONS:
            for strategy in ALL_STRATEGIES:
                try:
                    s = run_backtest(ticker, df, strategy, horizon_key, one_at_a_time=True)
                    s = filter_trades_to_year(s, EVAL_FROM, EVAL_TO)
                    ticker_results.append(s)
                except Exception as e:
                    pass  # skip silently; individual strategy failures are normal
        all_summaries.extend(ticker_results)
        done = sum(1 for s in ticker_results if s.evaluated > 0)
        print(f"→ {done}/{len(ticker_results)} combos had evaluated trades")

    # ─── Aggregate: by horizon ─────────────────────────────────────────────
    by_horizon = defaultdict(lambda: {"wins": 0, "losses": 0, "timeouts": 0, "exp_r": []})
    for s in all_summaries:
        bh = by_horizon[s.horizon_key]
        bh["wins"]     += s.wins
        bh["losses"]   += s.losses
        bh["timeouts"] += s.timeouts
        if s.expectancy_r is not None:
            bh["exp_r"].append(s.expectancy_r)

    # ─── Aggregate: by strategy ────────────────────────────────────────────
    by_strategy = defaultdict(lambda: {"wins": 0, "losses": 0, "timeouts": 0, "exp_r": []})
    for s in all_summaries:
        bs = by_strategy[s.strategy]
        bs["wins"]     += s.wins
        bs["losses"]   += s.losses
        bs["timeouts"] += s.timeouts
        if s.expectancy_r is not None:
            bs["exp_r"].append(s.expectancy_r)

    # ─── Best horizon/strategy combos (min 20 evaluated trades) ───────────
    combo_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "exp_r": []})
    for s in all_summaries:
        if s.evaluated >= 1:
            key = (s.strategy, s.horizon_key)
            combo_stats[key]["wins"]   += s.wins
            combo_stats[key]["losses"] += s.losses
            if s.expectancy_r is not None:
                combo_stats[key]["exp_r"].append(s.expectancy_r)

    # ─── Build report ──────────────────────────────────────────────────────
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  2025 BACKTEST RESULTS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  Tickers: {len(WATCHLIST)}   Failed downloads: {len(failed)}")
    lines.append(f"  Mode: one-trade-at-a-time per (strategy, horizon)")
    lines.append(f"{'='*70}\n")

    lines.append("── BY HORIZON ──────────────────────────────────────────────────────────")
    lines.append(f"  {'Horizon':<8} {'W':>5} {'L':>5} {'TO':>5} {'WinRate':>8} {'AvgExpR':>9}")
    lines.append(f"  {'-'*50}")
    for hk in HORIZONS:
        bh = by_horizon[hk]
        total = bh["wins"] + bh["losses"]
        wr    = f"{bh['wins']/total*100:.0f}%" if total else "—"
        er    = f"{float(np.mean(bh['exp_r'])):.2f}R" if bh["exp_r"] else "—"
        lines.append(f"  {hk:<8} {bh['wins']:>5} {bh['losses']:>5} {bh['timeouts']:>5} {wr:>8} {er:>9}")

    lines.append("")
    lines.append("── BY STRATEGY ─────────────────────────────────────────────────────────")
    lines.append(f"  {'Strategy':<22} {'W':>5} {'L':>5} {'TO':>5} {'WinRate':>8} {'AvgExpR':>9}")
    lines.append(f"  {'-'*60}")
    for strat in ALL_STRATEGIES:
        bs = by_strategy[strat]
        total = bs["wins"] + bs["losses"]
        wr    = f"{bs['wins']/total*100:.0f}%" if total else "—"
        er    = f"{float(np.mean(bs['exp_r'])):.2f}R" if bs["exp_r"] else "—"
        lines.append(f"  {strat:<22} {bs['wins']:>5} {bs['losses']:>5} {bs['timeouts']:>5} {wr:>8} {er:>9}")

    lines.append("")
    lines.append("── TOP 20 STRATEGY × HORIZON COMBOS (by win rate, min 10 evaluated) ───")
    lines.append(f"  {'Strategy':<22} {'Horiz':<6} {'W':>4} {'L':>4} {'WinRate':>8} {'AvgExpR':>9}")
    lines.append(f"  {'-'*60}")
    ranked = []
    for (strat, hk), cs in combo_stats.items():
        total = cs["wins"] + cs["losses"]
        if total < 10:
            continue
        wr = cs["wins"] / total
        er = float(np.mean(cs["exp_r"])) if cs["exp_r"] else 0.0
        ranked.append((strat, hk, cs["wins"], cs["losses"], wr, er))
    ranked.sort(key=lambda x: x[4], reverse=True)
    for strat, hk, w, l, wr, er in ranked[:20]:
        lines.append(f"  {strat:<22} {hk:<6} {w:>4} {l:>4} {wr*100:>7.0f}% {er:>8.2f}R")

    if failed:
        lines.append(f"\n  Failed tickers: {', '.join(failed)}")

    report = "\n".join(lines)
    print(report)

    # ─── Save outputs ──────────────────────────────────────────────────────
    with open("backtest_2025_summary.txt", "w") as f:
        f.write(report)
    print(f"\n  ✓ Summary saved to backtest_2025_summary.txt")

    # JSON: condensed (no trade-level detail for space)
    json_out = []
    for s in all_summaries:
        if s.evaluated == 0 and s.wins == 0 and s.losses == 0:
            continue
        json_out.append({
            "ticker": s.ticker, "strategy": s.strategy, "horizon": s.horizon_key,
            "wins": s.wins, "losses": s.losses, "timeouts": s.timeouts,
            "win_rate": round(s.win_rate, 1) if s.win_rate is not None else None,
            "avg_r": round(s.avg_r_multiple, 3) if s.avg_r_multiple is not None else None,
            "expectancy_r": round(s.expectancy_r, 3) if s.expectancy_r is not None else None,
            "avg_hold_days": round(s.avg_holding_days, 1) if s.avg_holding_days is not None else None,
        })
    with open("backtest_2025_results.json", "w") as f:
        json.dump(json_out, f, indent=2)
    print(f"  ✓ Full results saved to backtest_2025_results.json\n")


if __name__ == "__main__":
    run_all()
