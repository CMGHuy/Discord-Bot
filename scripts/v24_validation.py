#!/usr/bin/env python3
"""Plan v8 Task V24 -- the one pre-registered validation run.

**Window changed by human-partner directive 2026-08-03** from
2024-01-01..2025-12-31 to **1999-01-01..2026-08-03**.

READ THIS BEFORE QUOTING ANY NUMBER THIS PRINTS. The directed window contains
TRAIN (1999-01-01..2023-12-31) in its entirety, so the `full` row is an
IN-SAMPLE number over ~90% of its span: every strategy gate, exit parameter and
sizing choice in this plan was fitted on that data. It is not out-of-sample
evidence and nothing downstream (V26, V28, promotion) may cite it as such.

So this reports three slices, never one:

    full            1999-01-01 .. 2026-08-03   the directed headline; IN-SAMPLE
    in_sample       1999-01-01 .. 2023-12-31   = TRAIN, for reference
    out_of_sample   2024-01-01 .. 2026-08-03   THE ONLY UNSEEN DATA

**Adoption decisions read `out_of_sample`.**

One backtest, sliced three ways -- not three runs. `window_trades()` filters an
already-collected trade list by entry_date, so the slices cannot drift apart
the way three separate invocations could.

One-shot: pass --once-guard pointing at the results doc. It refuses to run if
that file already has a `## Result` section, so the window cannot be spent
twice from two sessions.
"""
import argparse
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_backtest_data import load_cached, load_watchlist
import swingbot.core.backtest as bt
from swingbot import config
from swingbot.core.gate.wr_math import wilson_lower_bound
from swingbot.core.strategy_types import HORIZONS
from run_backtest_range import pool, pooled_max_dd_pct

FULL = ("1999-01-01", "2026-08-03")
IN_SAMPLE = ("1999-01-01", "2023-12-31")
OUT_OF_SAMPLE = ("2024-01-01", "2026-08-03")
SLICES = (("full", FULL), ("in_sample", IN_SAMPLE), ("out_of_sample", OUT_OF_SAMPLE))

ALL_STRATEGIES = [
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest",
    "RSI Divergence", "Volume Profile",
]


def _reuse_corrected(trades):
    """V49's horizon-reuse correction, same threshold (1.5x) the rest of the
    plan uses. A pooled N summed over ten horizons overstates the evidence
    whenever the horizons fire on the same signal."""
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    if not ev:
        return 0, 1.0
    sigs = {(t.entry_date, t.entry, t.direction) for t in ev}
    ratio = len(ev) / len(sigs)
    return (round(len(ev) / ratio) if ratio >= 1.5 else len(ev)), round(ratio, 2)


def score(trades):
    s = pool(trades)
    n_ind, ratio = _reuse_corrected(trades)
    s["n_independent"] = n_ind
    s["horizon_overcount"] = ratio
    if s["win_rate"] is not None and n_ind:
        wins_ind = round(s["win_rate"] / 100.0 * n_ind)
        s["wilson_lb"] = round(wilson_lower_bound(wins_ind, n_ind) * 100, 2)
    else:
        s["wilson_lb"] = None
    s["max_dd_pct"] = pooled_max_dd_pct(trades)
    # The runner leg, per V51 Step 2 -- a blended expectancy cannot say whether
    # the economics work when tp1_fraction is frozen at 0.5.
    rr = [t.runner_r for t in trades if t.runner_r is not None]
    s["n_runners"] = len(rr)
    s["runner_r_mean"] = round(sum(rr) / len(rr), 4) if rr else None
    s["runner_r_median"] = round(sorted(rr)[len(rr) // 2], 3) if rr else None
    losses = [-t.return_pct for t in trades
              if t.outcome == "loss" and t.return_pct is not None]
    s["loss_pct_max"] = round(max(losses), 3) if losses else None
    s["loss_over_cap_share"] = (
        round(sum(1 for x in losses if x > config.MAX_LOSS_PCT + 1e-9) / len(losses), 4)
        if losses else None)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--once-guard", default=None,
                    help="markdown file that must NOT already contain a "
                         "'## Result' heading; refuses to run if it does")
    ap.add_argument("--max-tickers", type=int, default=None)
    args = ap.parse_args()

    if args.once_guard and os.path.exists(args.once_guard):
        with open(args.once_guard, encoding="utf-8") as fh:
            if re.search(r"(?m)^## Result\s*$", fh.read()):
                print(f"REFUSING TO RUN: {args.once_guard} already has a "
                      f"'## Result' section. This is the pre-registered one-shot "
                      f"validation -- no re-runs.", file=sys.stderr)
                return 1

    tickers = load_watchlist()
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
    dfs = {}
    for t in tickers:
        d = load_cached(t)
        if d is None:
            continue
        w = d[(d.index >= FULL[0]) & (d.index <= FULL[1])]
        if len(w) >= 200:
            dfs[t] = w
    last = max((str(d.index.max())[:10] for d in dfs.values()), default="n/a")
    print(f"{len(dfs)} tickers | window {FULL[0]}..{FULL[1]} | latest bar on disk {last}",
          flush=True)
    print(f"exit=v2 scale_out=True tp2=none | MAX_LOSS_PCT={config.MAX_LOSS_PCT} "
          f"cap={config.MAX_LOSS_CAP_ENABLED} | MIN_TARGET_PCT={config.MIN_TARGET_PCT} "
          f"floor={config.TARGET_FLOOR_ENABLED}", flush=True)
    print("SLICES: full (IN-SAMPLE, contains TRAIN) | in_sample | out_of_sample "
          "<- adoption reads this one\n", flush=True)

    out = {"window": list(FULL), "slices": {k: list(v) for k, v in SLICES},
           "n_tickers": len(dfs), "latest_bar": last,
           "config": {"max_loss_pct": config.MAX_LOSS_PCT,
                      "max_loss_cap_enabled": config.MAX_LOSS_CAP_ENABLED,
                      "min_target_pct": config.MIN_TARGET_PCT,
                      "target_floor_enabled": config.TARGET_FLOOR_ENABLED},
           "per_strategy": {}, "pooled": {}}
    all_trades = []

    for si, strategy in enumerate(ALL_STRATEGIES, 1):
        t0 = time.time()
        trades = []
        for hk in HORIZONS:
            for ticker, df in dfs.items():
                try:
                    s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                        exit_model="v2", scale_out=True, tp2_mode="none")
                except Exception:
                    continue
                trades.extend(s.trades)
        all_trades.extend(trades)
        rows = {name: score(window_trades_list(trades, lo, hi))
                for name, (lo, hi) in SLICES}
        out["per_strategy"][strategy] = rows
        oos = rows["out_of_sample"]
        print(f"[{si}/{len(ALL_STRATEGIES)}] {strategy:<20} "
              f"full N={rows['full']['n_eval']:<6} "
              f"OOS N={oos['n_eval']:<5} "
              f"OOS WR={_f(oos['win_rate'])} LB={_f(oos['wilson_lb'])} "
              f"OOS ExpR={_fr(oos['expectancy_r'])} ({time.time() - t0:.0f}s)",
              flush=True)

    for name, (lo, hi) in SLICES:
        out["pooled"][name] = score(window_trades_list(all_trades, lo, hi))
    print("\nPOOLED")
    for name, _ in SLICES:
        p = out["pooled"][name]
        print(f"  {name:<14} N={p['n_eval']:<6} Nind={p['n_independent']:<6} "
              f"WR={_f(p['win_rate'])} LB={_f(p['wilson_lb'])} "
              f"ExpR={_fr(p['expectancy_r'])} maxDD={_fr(p['max_dd_pct'])}%",
              flush=True)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=1, default=float))
        print(f"\nWrote {args.json_out}", flush=True)
    return 0


def window_trades_list(trades, lo, hi):
    """Same predicate as run_backtest_range.window_trades, against a bare list
    rather than a summary object."""
    return [t for t in trades if lo <= t.entry_date <= hi]


def _f(v):
    return "n/a" if v is None else f"{v:.1f}%"


def _fr(v):
    return "n/a" if v is None else f"{v:+.3f}"


if __name__ == "__main__":
    sys.exit(main())
