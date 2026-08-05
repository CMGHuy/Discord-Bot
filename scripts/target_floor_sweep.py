"""Sweep `MIN_TARGET_PCT` above 3.0 and measure the impact (plan v8, V12/V28 follow-up).

V12's instrumented scan proved the V11 reachability screen is inert at
`MIN_TARGET_PCT=2.5`: `build_scenarios` only emits a scenario whose nearest
level ahead is already >= `max(MIN_REWARD_PCT, sr_target_min_pct*0.15)`, which
is >= 3.0% at every horizon, and the screen then tests that same level against
2.5%. So the floor only begins to bind above ~3.0%.

**What this measures, and what it cannot.** `MIN_TARGET_PCT` has two effects:

  (a) `apply_target_floor` pushes TP1 out to the floor on every plan. The
      backtest DOES honor this -- `backtest._trade_plan_at` calls the
      `plan_engine` builders, and each returns
      `apply_target_floor(entry, take_profit, direction)`, which reads
      `config.MIN_TARGET_PCT` globally. This is the effect that moves trade
      outcomes, and it is what this harness measures.
  (b) the reachability screen rejects scenarios whose nearest level ahead sits
      inside the floor. That is scan-side only and has no counterpart in the
      backtest, so **this harness cannot measure it**. Signal-volume impact
      from (b) is a separate scan-side question -- see
      `v12_reachability_probe.py`.

Raising the floor is a *tightening* of the win side: a larger TP1 is harder to
reach, so expect win rate DOWN and per-win R UP. Expectancy is the arbiter,
and it inherits V51's +0.318R daily-bar overstatement exactly as V53/V54 did
-- read any expectancy under that as not distinguishable from zero.

Config is production, pinned to V20/V21/V53/V54 so the numbers are comparable:
exit v2 + scale-out, TP2 `levels`, frictions on, TRAIN 1999-2023.
`STRATEGY_GATES` are left **as shipped** (unlike V53/V54, which disabled them
to see masked cells) -- the question here is what a live config change does,
and the live config has the gates on.

Uses V50's level-map memo: the map depends on (df-up-to-i, horizon, entry) and
on none of the swept values, so it is computed once per (ticker, horizon,
strategy) group and reused across every floor in that group. Without it this
is five full grids instead of one plus change.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_backtest_data import load_cached                       # noqa: E402
from regime_slices import MIN_N                                   # noqa: E402
from run_backtest_range import (_tickers_for_run, pool,           # noqa: E402
                                pooled_max_dd_pct, window_trades,
                                wilson_lower_bound)
from swingbot import config                                       # noqa: E402
from swingbot.core.backtest import (ALL_STRATEGIES,               # noqa: E402
                                    clear_level_map_memo,
                                    enable_level_map_memo,
                                    run_backtest)
from swingbot.core.backtest_windows import TRAIN                  # noqa: E402
from swingbot.core.strategy_types import HORIZONS                 # noqa: E402
from swingbot.core.universe import (data_quality_issues,          # noqa: E402
                                    liquidity_reason)

DEFAULT_FLOORS = (2.5, 3.25, 3.5, 4.0, 5.0)


def _stats(trades):
    st = pool(trades)
    st["max_dd_pct"] = pooled_max_dd_pct(trades)
    st["wilson_lb"] = wilson_lower_bound(st["wins"], st["n_eval"])
    return st


def _row(label, st):
    wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
    lb = f"{st['wilson_lb']:.1f}" if st["wilson_lb"] is not None else "n/a"
    er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
    aw = f"{st['avg_win_r']:+.3f}" if st["avg_win_r"] is not None else "n/a"
    dd = f"{st['max_dd_pct']:.1f}" if st["max_dd_pct"] is not None else "n/a"
    flag = "" if st["n_eval"] >= MIN_N else "  INSUFFICIENT"
    return (f"{label:>10s} {st['n_eval']:7d} {wr:>6s} {lb:>6s} {er:>8s} "
            f"{aw:>8s} {dd:>7s}{flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floors", default=None,
                    help="comma-separated; default 2.5,3.25,3.5,4.0,5.0 "
                         "(2.5 is the shipped baseline)")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--strategies", default=None)
    ap.add_argument("--exit-model", dest="exit_model", default="v2")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true", default=True)
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false")
    ap.add_argument("--tp2", default="levels", choices=["none", "levels"])
    ap.add_argument("--frictions", default="on", choices=["on", "off"])
    args = ap.parse_args()

    floors = ([float(x) for x in args.floors.split(",")] if args.floors
              else list(DEFAULT_FLOORS))
    strategies = ([s.strip() for s in args.strategies.split(",")]
                  if args.strategies else list(ALL_STRATEGIES))

    if not config.TARGET_FLOOR_ENABLED:
        print("WARNING: TARGET_FLOOR_ENABLED is false -- apply_target_floor "
              "returns TP1 unchanged and every floor below would measure the "
              "SAME thing. Forcing it on for this run.", flush=True)
        config.TARGET_FLOOR_ENABLED = True

    frames, excluded = {}, {"illiquid": [], "bad_data": [], "no_data": []}
    for t in _tickers_for_run(None):
        df = load_cached(t)
        if df is None:
            excluded["no_data"].append(t)
            continue
        if liquidity_reason(df):
            excluded["illiquid"].append(t)
            continue
        if data_quality_issues(df, t):
            excluded["bad_data"].append(t)
            continue
        frames[t] = df
    ordered = sorted(frames)
    if args.limit:
        ordered = ordered[:args.limit]

    baseline = config.MIN_TARGET_PCT
    print(f"MIN_TARGET_PCT sweep | {len(ordered)} tickers x {len(HORIZONS)} "
          f"horizons x {len(strategies)} strategies x {len(floors)} floors | "
          f"shipped baseline={baseline} | exit={args.exit_model} "
          f"scale_out={args.scale_out} tp2={args.tp2} "
          f"frictions={args.frictions} | gates AS SHIPPED", flush=True)
    print(f"floors: {floors}", flush=True)

    enable_level_map_memo()
    pooled = defaultdict(list)              # floor -> trades
    per_h = defaultdict(list)               # (floor, horizon) -> trades

    try:
        for ti, ticker in enumerate(ordered, 1):
            df = frames[ticker]
            counts = {f: 0 for f in floors}
            for hk in HORIZONS:
                for strat in strategies:
                    # floors innermost: same (ticker, horizon, strategy) means
                    # the identical level map, so every floor after the first
                    # is a memo hit (V50).
                    for f in floors:
                        config.MIN_TARGET_PCT = f
                        try:
                            s = run_backtest(ticker, df, strat, hk,
                                             one_at_a_time=True,
                                             exit_model=args.exit_model,
                                             scale_out=args.scale_out,
                                             tp2_mode=args.tp2,
                                             frictions=(args.frictions == "on"))
                        except Exception as e:            # noqa: BLE001
                            print(f"    ! {ticker}/{strat}/{hk}/{f}: {e}", flush=True)
                            continue
                        tr = window_trades(s, *TRAIN)
                        pooled[f].extend(tr)
                        per_h[(f, hk)].extend(tr)
                        counts[f] += len(tr)
                clear_level_map_memo()
            print(f"[{ti}/{len(ordered)}] {ticker}: "
                  + " ".join(f"{f}%={counts[f]}" for f in floors), flush=True)
    finally:
        config.MIN_TARGET_PCT = baseline

    hdr = (f"{'floor':>10s} {'N':>7s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>8s} "
           f"{'AvgWinR':>8s} {'MaxDD%':>7s}")
    print(f"\n{'=' * 78}\n== pooled over the whole universe ==\n{hdr}", flush=True)
    out = {"config": {"exit_model": args.exit_model, "scale_out": args.scale_out,
                      "tp2": args.tp2, "frictions": args.frictions,
                      "gates": "as shipped", "train": list(TRAIN),
                      "baseline_floor": baseline},
           "excluded": {k: len(v) for k, v in excluded.items()},
           "floors": {}}
    for f in floors:
        st = _stats(pooled[f])
        tag = f"{f}%" + (" *" if f == baseline else "")
        print(_row(tag, st), flush=True)
        out["floors"][str(f)] = {"pooled": st,
                                 "by_horizon": {hk: _stats(per_h[(f, hk)])
                                                for hk in HORIZONS}}

    print(f"\n{'=' * 78}\n== by horizon (ExpR) ==", flush=True)
    print(f"{'horizon':>8s} " + " ".join(f"{str(f) + '%':>9s}" for f in floors), flush=True)
    for hk in HORIZONS:
        cells = []
        for f in floors:
            st = out["floors"][str(f)]["by_horizon"][hk]
            e = st["expectancy_r"]
            cells.append(f"{e:+9.3f}" if e is not None else f"{'n/a':>9s}")
        print(f"{hk:>8s} " + " ".join(cells), flush=True)

    base = out["floors"][str(baseline)]["pooled"] if str(baseline) in out["floors"] else None
    if base and base["expectancy_r"] is not None:
        print(f"\n== delta vs the shipped {baseline}% baseline ==", flush=True)
        for f in floors:
            if f == baseline:
                continue
            st = out["floors"][str(f)]["pooled"]
            if st["expectancy_r"] is None:
                continue
            d = st["expectancy_r"] - base["expectancy_r"]
            dn = st["n_eval"] - base["n_eval"]
            print(f"  {f}%: ExpR {d:+.3f}R  N {dn:+d} "
                  f"({st['n_eval']} vs {base['n_eval']})", flush=True)
        print("\nRead any expectancy under V51's +0.318R daily-bar "
              "overstatement as NOT distinguishable from zero.", flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
