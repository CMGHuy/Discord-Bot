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
        "avg_win_r": float(np.mean([t.r_multiple for t in wins])) if wins else None,
    }


def passes(stats, min_n):
    return (stats["n_eval"] >= min_n
            and stats["win_rate"] is not None and stats["win_rate"] >= 80
            and stats["expectancy_r"] is not None and stats["expectancy_r"] > 0
            and stats["excluded_share"] <= 0.5)


def build_registry_records(summaries, *, source, window, run_date,
                           horizon=None, pass_wr=80.0, min_n=15):
    """Turn pooled per-strategy summaries into validation-registry records.

    A record is VALIDATED only when it clears the acceptance gates on the
    window it was measured on; everything else (including tiny-N) is WEAK.
    """
    recs = []
    for s in summaries:
        wr = s.get("win_rate")
        er = s.get("expectancy_r")
        validated = (wr is not None and wr >= pass_wr
                     and er is not None and er > 0
                     and s["n"] >= min_n)
        recs.append({"source": source, "strategy": s["strategy"], "horizon": horizon,
                     "status": "VALIDATED" if validated else "WEAK",
                     "n": s["n"],
                     "win_rate": round(wr, 1) if wr is not None else 0.0,
                     "expectancy_r": round(er, 3) if er is not None else 0.0,
                     "window": window, "run_date": run_date})
    return recs


def merge_registry(path, new_records):
    """Merge records into the registry JSON, replacing same-key entries."""
    path = Path(path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    new_keys = {(r["source"], r["strategy"], r.get("horizon")) for r in new_records}
    kept = [r for r in existing
            if (r["source"], r["strategy"], r.get("horizon")) not in new_keys]
    merged = sorted(kept + new_records,
                    key=lambda r: (r["source"], r["strategy"], str(r.get("horizon"))))
    path.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--emit-registry", dest="emit_registry", default=None,
                    help="path to validation_registry.json to merge records into")
    ap.add_argument("--run-date", dest="run_date", default=None,
                    help="YYYY-MM-DD stamped on emitted registry records "
                         "(required with --emit-registry; explicit for reproducibility)")
    ap.add_argument("--exit-model", dest="exit_model", choices=["v1", "v2"], default="v1")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true")
    ap.add_argument("--tp2", dest="tp2", choices=["none", "levels"], default="levels",
                    help="TP2 source for scale-out runs (v2 only)")
    args = ap.parse_args()
    if args.emit_registry and not args.run_date:
        ap.error("--emit-registry requires --run-date")

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
    # Runner sub-outcome counts (v2 + scale-out only). `runner_outcome` is
    # stamped per-trade on BacktestTrade (v2 branch only), so these ARE
    # filtered to the date window exactly like by_strategy/by_combo above --
    # derived from `tr` (window_trades' output), not from the unfiltered
    # BacktestSummary.runner_tp2/trail/be/timeout run-level aggregates.
    runner_by_strategy = defaultdict(lambda: {"tp2": 0, "trail": 0, "be": 0, "timeout": 0, "wins": 0})
    show_runner_cols = args.exit_model == "v2" and args.scale_out
    tp2_mode = args.tp2 if args.exit_model == "v2" else "none"

    tickers = sorted(load_watchlist())
    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model=args.exit_model, scale_out=args.scale_out,
                                      tp2_mode=tp2_mode)
                except Exception as e:
                    print(f"    ! {strat}/{hk}: {e}")
                    continue
                tr = window_trades(s, date_from, date_to)
                by_strategy[strat].extend(tr)
                by_combo[(strat, hk)].extend(tr)
                if show_runner_cols:
                    rb = runner_by_strategy[strat]
                    rb["tp2"] += sum(1 for t in tr if t.runner_outcome == "runner_tp2")
                    rb["trail"] += sum(1 for t in tr if t.runner_outcome == "runner_trail")
                    rb["be"] += sum(1 for t in tr if t.runner_outcome == "runner_be")
                    rb["timeout"] += sum(1 for t in tr if t.runner_outcome == "runner_timeout")
                    rb["wins"] += sum(1 for t in tr if t.outcome == "win")

    header = f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s}"
    if show_runner_cols:
        header += f" {'AvgWinR':>7s}"
    header += f" {'Scr':>5s} {'TO':>5s} {'Excl%':>6s}"
    if show_runner_cols:
        header += f" {'tp2%':>6s} {'trail%':>6s} {'be%':>6s} {'rto%':>6s}"
    header += "  PASS"
    lines = [f"== {label} {date_from} .. {date_to} | pass: WR>=80, ExpR>0, N>={min_n}, excl<=50% ==",
             header]
    results = {}
    for strat in strategies:
        st = pool(by_strategy[strat])
        results[strat] = dict(st)
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        flag = "PASS" if passes(st, min_n) else "FAIL"
        row = f"{strat:22s} {st['n_eval']:5d} {wr:>6s} {er:>7s}"
        if show_runner_cols:
            awr = f"{st['avg_win_r']:+.3f}" if st["avg_win_r"] is not None else "n/a"
            row += f" {awr:>7s}"
        row += f" {st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%"
        if show_runner_cols:
            rb = runner_by_strategy[strat]

            def runner_pct(count, _rb=rb):
                return f"{count / _rb['wins'] * 100:5.1f}%" if _rb["wins"] else "n/a"

            tp2_pct, trail_pct, be_pct, rto_pct = (
                runner_pct(rb["tp2"]), runner_pct(rb["trail"]),
                runner_pct(rb["be"]), runner_pct(rb["timeout"]))
            row += f" {tp2_pct:>6s} {trail_pct:>6s} {be_pct:>6s} {rto_pct:>6s}"
            results[strat].update({
                "runner_tp2_pct": (rb["tp2"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_trail_pct": (rb["trail"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_be_pct": (rb["be"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_timeout_pct": (rb["timeout"] / rb["wins"] * 100) if rb["wins"] else None,
            })
        row += f"  {flag}"
        lines.append(row)

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
    if args.emit_registry:
        summaries = [{"strategy": k, "n": v["n_eval"], "win_rate": v["win_rate"],
                      "expectancy_r": v["expectancy_r"]} for k, v in results.items()]
        merge_registry(args.emit_registry, build_registry_records(
            summaries, source="strategy", window=f"{date_from}..{date_to}",
            run_date=args.run_date, min_n=min_n))
        print(f"Merged {len(summaries)} records into {args.emit_registry}")
    print("\nSaved backtest_range_summary.txt")


if __name__ == "__main__":
    main()
