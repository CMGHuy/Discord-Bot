"""V19 (plan v8): is `atr_stop_multiple` still a live knob under V51's cap?

Every ATR-sized plan prices its stop in `plan_engine._atr_plan`:

    risk_distance = h["atr_stop_multiple"] * atr_val
    if stop_mult is not None:            # E31 MAE-informed factor, 0.8-1.3x
        risk_distance *= stop_mult
    risk_distance = min(risk_distance, entry * max_risk_pct/100)
    risk_distance = cap_risk_distance(entry, risk_distance)   # MAX_LOSS_PCT

`max_risk_pct` runs 3-11% by horizon and `MAX_LOSS_PCT` is 1.75%, so the cap
is always the tighter of the two percentage limits. The multiple therefore
only moves the stop where `mult * ATR14 < MAX_LOSS_PCT * entry`. Both V19
steps -- retuning the multiple (Step 1) and the MAE-informed `stop_mult`
(Step 2) -- live inside that same capped expression, so this measures how
often anything upstream of the cap can reach the outcome at all.

Two passes, because they answer different halves of the question:

  --bars     ATR14% over every TRAIN bar. Cheap, no backtest. Tells you what
             the cap does to a random bar.
  --entries  runs the real harness and reads the stop distance the plan
             builder actually produced (|entry - stop_loss| / entry). Entries
             are strategy-selected, not random bars, so this is the number
             that governs -- the bar pass is a fast proxy for it.

Default runs both. Neither writes anything; this is a measurement, not a tune.
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd                                            # noqa: E402

from fetch_backtest_data import load_cached                    # noqa: E402
from run_backtest_range import _tickers_for_run, window_trades  # noqa: E402
from swingbot import config                                    # noqa: E402
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest  # noqa: E402
from swingbot.core.backtest_windows import TRAIN               # noqa: E402
from swingbot.core.indicators import atr                       # noqa: E402
from swingbot.core.strategy_types import HORIZONS              # noqa: E402
from swingbot.core.universe import (data_quality_issues,       # noqa: E402
                                    liquidity_reason)

# tune_sizing.py's grid for this axis, and the E31 clamp from
# edge/stops.py:mae_informed_stop_mult -- the two things V19 would move.
GRID = [1.5, 2.0, 2.5]
STOP_MULT_CLAMP = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
SHIPPED = 2.0
EPS = 0.02          # within this of the cap counts as "at the cap"


def _screened_tickers(limit=None):
    out = []
    for t in _tickers_for_run(None):
        df = load_cached(t)
        if df is None or liquidity_reason(df) or data_quality_issues(df, t):
            continue
        out.append((t, df))
        if limit and len(out) >= limit:
            break
    return out


def bar_pass(cap):
    rows = []
    for t, df in _screened_tickers():
        d = df.loc[(df.index >= TRAIN[0]) & (df.index <= TRAIN[1])]
        if len(d) < 60:
            continue
        a = (atr(d, 14) / d["Close"] * 100).dropna()
        if not a.empty:
            rows.append(a)
    s = pd.concat(rows, ignore_index=True)
    print(f"\n== bar pass: {len(s):,} TRAIN ticker-bars ==", flush=True)
    print(f"median ATR14 = {s.median():.3f}% of close; deciles "
          + " ".join(f"{s.quantile(q):.2f}" for q in
                     [.1, .2, .3, .4, .5, .6, .7, .8, .9]), flush=True)

    print(f"\natr_stop_multiple vs the {cap}% cap:", flush=True)
    print(f"{'mult':>6} {'capped':>9} {'multiple binds':>16}", flush=True)
    for m in GRID:
        live = (s * m < cap).mean()
        print(f"{m:>6} {1 - live:>8.1%} {live:>16.1%}", flush=True)

    print(f"\nE31 stop_mult clamp at the shipped {SHIPPED} multiple:", flush=True)
    print(f"{'stop_mult':>10} {'effective':>10} {'binds':>8}", flush=True)
    for sm in STOP_MULT_CLAMP:
        eff = SHIPPED * sm
        print(f"{sm:>10} {eff:>10.2f} {(s * eff < cap).mean():>8.1%}", flush=True)


def entry_pass(cap, limit):
    tickers = _screened_tickers(limit)
    print(f"\n== entry pass: {len(tickers)} tickers x {len(HORIZONS)} horizons "
          f"x {len(ALL_STRATEGIES)} strategies ==", flush=True)
    dists, by_strat = [], defaultdict(list)
    for i, (ticker, df) in enumerate(tickers, 1):
        n = 0
        for hk in HORIZONS:
            for strat in ALL_STRATEGIES:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                     exit_model="v2", scale_out=True,
                                     tp2_mode="levels", frictions=True)
                except Exception as e:                        # noqa: BLE001
                    print(f"    ! {strat}/{hk}: {e}", flush=True)
                    continue
                for tr in window_trades(s, *TRAIN):
                    if not tr.entry:
                        continue
                    d = abs(tr.entry - tr.stop_loss) / tr.entry * 100
                    dists.append(d)
                    by_strat[strat].append(d)
                    n += 1
        print(f"[{i}/{len(tickers)}] {ticker}: +{n} entries", flush=True)

    if not dists:
        print("no trades", flush=True)
        return
    dists.sort()
    n = len(dists)

    def q(p):
        return dists[min(int(p * n), n - 1)]

    at_cap = sum(1 for d in dists if d >= cap - EPS) / n
    print(f"\n{n:,} TRAIN entries", flush=True)
    print(f"stop distance %: p10={q(.1):.3f} p25={q(.25):.3f} median={q(.5):.3f} "
          f"p75={q(.75):.3f} p90={q(.9):.3f} max={dists[-1]:.3f}", flush=True)
    print(f"\nAT the {cap}% cap (the multiple did NOT set the stop): {at_cap:.1%}",
          flush=True)
    print(f"BELOW it (atr_stop_multiple binding):                    "
          f"{1 - at_cap:.1%}", flush=True)
    print("\nper strategy, share of entries at the cap:", flush=True)
    for s in sorted(by_strat, key=lambda s: -len(by_strat[s])):
        v = by_strat[s]
        c = sum(1 for d in v if d >= cap - EPS) / len(v)
        print(f"  {s:22s} N={len(v):6d}  at cap {c:6.1%}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", action="store_true", help="bar pass only")
    ap.add_argument("--entries", action="store_true", help="entry pass only")
    ap.add_argument("--limit", type=int, default=12,
                    help="tickers for the entry pass (default 12; the full "
                         "watchlist is ~30x the runtime for the same answer)")
    args = ap.parse_args()

    cap = config.MAX_LOSS_PCT
    print(f"MAX_LOSS_PCT={cap}% MAX_LOSS_CAP_ENABLED={config.MAX_LOSS_CAP_ENABLED} "
          f"shipped atr_stop_multiple={SHIPPED} (flat across all "
          f"{len(HORIZONS)} horizons)", flush=True)
    if not config.MAX_LOSS_CAP_ENABLED:
        print("NOTE: the cap is OFF in this environment -- these numbers "
              "describe a config that is not shipped.", flush=True)

    both = not (args.bars or args.entries)
    if args.bars or both:
        bar_pass(cap)
    if args.entries or both:
        entry_pass(cap, args.limit)


if __name__ == "__main__":
    main()
