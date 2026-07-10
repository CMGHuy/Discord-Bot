#!/usr/bin/env python3
"""Acceptance harness: runs every strategy x horizon x cached ticker and
pools results per strategy over an entry-date window.

    python scripts/run_backtest_range.py --train        # 2020-01-01 .. 2023-12-31
    python scripts/run_backtest_range.py --validation   # 2024-01-01 .. 2025-12-31 (run ONCE, at the end)
    python scripts/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 --strategy "RSI"

PASS gate per spec: win_rate >= 80, expectancy_r > 0, N >= 30 (train) / 15
(validation), scratches+timeouts <= 50% of closed trades."""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")


def window_trades(summary, date_from, date_to):
    return [t for t in summary.trades if date_from <= t.entry_date <= date_to]


def pool(trades):
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = [t for t in ev if t.outcome == "win"]
    scr = [t for t in trades if t.outcome == "scratch"]
    to = [t for t in trades if t.outcome == "timeout"]
    closed = len(trades)
    return {
        "n_eval": len(ev), "wins": len(wins), "losses": len(ev) - len(wins),
        "scratches": len(scr), "timeouts": len(to), "closed": closed,
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": (len(scr) + len(to)) / closed if closed else 0.0,
    }


def passes(stats, min_n):
    return (stats["n_eval"] >= min_n
            and stats["win_rate"] is not None and stats["win_rate"] >= 80
            and stats["expectancy_r"] is not None and stats["expectancy_r"] > 0
            and stats["excluded_share"] <= 0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    if args.train:
        date_from, date_to, min_n, label = *TRAIN, 30, "TRAIN"
    elif args.validation:
        date_from, date_to, min_n, label = *VALIDATION, 15, "VALIDATION"
    else:
        if not (args.date_from and args.date_to):
            ap.error("need --train, --validation, or --from/--to")
        date_from, date_to, min_n, label = args.date_from, args.date_to, 15, "CUSTOM"

    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    by_strategy = defaultdict(list)
    by_combo = defaultdict(list)

    tickers = sorted(load_watchlist())
    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True)
                except Exception as e:
                    print(f"    ! {strat}/{hk}: {e}")
                    continue
                tr = window_trades(s, date_from, date_to)
                by_strategy[strat].extend(tr)
                by_combo[(strat, hk)].extend(tr)

    lines = [f"== {label} {date_from} .. {date_to} | pass: WR>=80, ExpR>0, N>={min_n}, excl<=50% ==",
             f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s} {'Scr':>5s} {'TO':>5s} {'Excl%':>6s}  PASS"]
    results = {}
    for strat in strategies:
        st = pool(by_strategy[strat])
        results[strat] = st
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        flag = "PASS" if passes(st, min_n) else "FAIL"
        lines.append(f"{strat:22s} {st['n_eval']:5d} {wr:>6s} {er:>7s} {st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%  {flag}")

    lines.append("\n-- per strategy x horizon (for gating decisions) --")
    lines.append(f"{'Strategy':22s} {'Horiz':6s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s}")
    for (strat, hk), tr in sorted(by_combo.items()):
        st = pool(tr)
        if st["closed"] == 0:
            continue
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        lines.append(f"{strat:22s} {hk:6s} {st['n_eval']:5d} {wr:>6s} {er:>7s}")

    report = "\n".join(lines)
    print("\n" + report)
    Path("backtest_range_summary.txt").write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}, indent=2))
    print("\nSaved backtest_range_summary.txt")


if __name__ == "__main__":
    main()
