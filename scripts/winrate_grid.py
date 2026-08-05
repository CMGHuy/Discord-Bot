"""Chase win rate directly: grid the two knobs that actually set it.

Human-partner directive 2026-08-05: get the win rate to >=70% if any
configuration can, trying every possibility. Recorded because both axes below
were previously gated -- `MAX_LOSS_PCT` by the V19/V51 note ("pre-registration
+ explicit human approval, or not at all"), and the payoff structure generally
by V10, which raised targets deliberately. This directive is that approval.

**Why these two knobs and not the ones earlier tasks swept.** A trade is a win
when TP1 is hit before the stop. All four sizing builders price
`TP1 = entry ± risk_distance * rr`, and the stop at `risk_distance`, so the
*ratio* of target distance to stop distance is `rr` and nothing else. That
makes `rr` the win-rate knob:

  * `MAX_LOSS_PCT` is NOT one. `cap_risk_distance` runs BEFORE the target is
    derived, so widening the cap scales the target and the stop together and
    leaves the ratio -- hence the hit rate -- essentially unchanged. Swept in
    earlier tasks for its expectancy effect, not this.
  * `MIN_TARGET_PCT` matters only as a spoiler: `apply_target_floor` pushes TP1
    back out to the floor, which is exactly why the shipped 2.5% floor sits at
    ~46% win rate. Chasing win rate means lowering it out of the way.

`RR_FLOOR` (0.30) clamps `_rr_for`, so it is swept alongside rr -- otherwise
every rr below 0.30 silently collapses to 0.30 and the grid would report the
same cell five times.

**What the numbers will cost, stated before they exist**, so the report is not
read as free money: `plan_engine.py:31` records that break-even win rate at
rr=0.30 is **76.9%**. Break-even scales roughly as `1/(1+rr)`, so rr=0.20 needs
~83% and rr=0.15 needs ~87%. A configuration can therefore clear 70% observed
win rate and still lose money -- that is the pre-V10 book, which had a 0.85%
median target against a 2.19% stop. Win rate and expectancy are both reported
for every cell, and the ranking is by win rate BECAUSE that is what was asked
for; expectancy is printed beside it so the trade is visible rather than
implied.
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
from swingbot.core import plan_engine                             # noqa: E402
from swingbot.core.backtest import (ALL_STRATEGIES,               # noqa: E402
                                    clear_level_map_memo,
                                    enable_level_map_memo,
                                    run_backtest)
from swingbot.core.backtest_windows import TRAIN                  # noqa: E402
from swingbot.core.strategy_types import HORIZONS                 # noqa: E402
from swingbot.core.universe import (data_quality_issues,          # noqa: E402
                                    liquidity_reason)

# rr: the target/stop ratio. Lower = closer target = higher hit rate.
DEFAULT_RRS = (0.15, 0.20, 0.25, 0.30, 0.35)
# The floor that would otherwise push TP1 back out. 0.0 = out of the way.
DEFAULT_FLOORS = (0.0, 0.5, 1.0)
TARGET_WR = 70.0


def _stats(trades):
    st = pool(trades)
    st["max_dd_pct"] = pooled_max_dd_pct(trades)
    st["wilson_lb"] = wilson_lower_bound(st["wins"], st["n_eval"])
    return st


def _breakeven_wr(rr):
    """Win rate at which `rr` pays for itself, ignoring frictions: a win banks
    rr, a loss costs 1, so p*rr = (1-p) -> p = 1/(1+rr)."""
    return 100.0 / (1.0 + rr)


def _apply(rr, floor):
    """Both knobs are read through module globals at call time, so rebinding
    them here changes every plan the next backtest builds."""
    plan_engine.RR_FLOOR = min(rr, 0.01)          # don't let the clamp mask rr
    plan_engine.STRATEGY_RR_OVERRIDE = {s: rr for s in ALL_STRATEGIES}
    config.MIN_TARGET_PCT = floor
    config.TARGET_FLOOR_ENABLED = floor > 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rrs", default=None)
    ap.add_argument("--floors", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--strategies", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--exit-model", dest="exit_model", default="v2")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true", default=True)
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false")
    ap.add_argument("--tp2", default="levels", choices=["none", "levels"])
    ap.add_argument("--frictions", default="on", choices=["on", "off"])
    args = ap.parse_args()

    rrs = [float(x) for x in args.rrs.split(",")] if args.rrs else list(DEFAULT_RRS)
    floors = ([float(x) for x in args.floors.split(",")] if args.floors
              else list(DEFAULT_FLOORS))
    strategies = ([s.strip() for s in args.strategies.split(",")]
                  if args.strategies else list(ALL_STRATEGIES))
    configs = [(rr, fl) for rr in rrs for fl in floors]

    frames, excluded = {}, []
    for t in _tickers_for_run(None):
        df = load_cached(t)
        if df is None:
            excluded.append(t)
            continue
        if liquidity_reason(df) or data_quality_issues(df, t):
            excluded.append(t)
            continue
        frames[t] = df
    ordered = sorted(frames)
    if args.limit:
        ordered = ordered[:args.limit]

    print(f"win-rate grid | {len(ordered)} tickers x {len(HORIZONS)} horizons x "
          f"{len(strategies)} strategies x {len(configs)} configs "
          f"(rr={rrs} floor={floors}) | exit={args.exit_model} "
          f"scale_out={args.scale_out} frictions={args.frictions}", flush=True)
    print(f"target: observed win rate >= {TARGET_WR}%  "
          f"(break-even WR: " +
          ", ".join(f"rr={rr}->{_breakeven_wr(rr):.1f}%" for rr in rrs) + ")",
          flush=True)

    enable_level_map_memo()
    pooled = defaultdict(list)          # (rr, floor) -> trades
    per_strat = defaultdict(list)       # (rr, floor, strat) -> trades
    base_rr, base_floor = dict(plan_engine.STRATEGY_RR_OVERRIDE), config.MIN_TARGET_PCT
    base_enabled = config.TARGET_FLOOR_ENABLED

    try:
        for ti, ticker in enumerate(ordered, 1):
            df = frames[ticker]
            for hk in HORIZONS:
                for strat in strategies:
                    for (rr, fl) in configs:
                        _apply(rr, fl)
                        try:
                            s = run_backtest(ticker, df, strat, hk,
                                             one_at_a_time=True,
                                             exit_model=args.exit_model,
                                             scale_out=args.scale_out,
                                             tp2_mode=args.tp2,
                                             frictions=(args.frictions == "on"))
                        except Exception as e:               # noqa: BLE001
                            print(f"    ! {ticker}/{strat}/{hk}/rr{rr}/f{fl}: {e}",
                                  flush=True)
                            continue
                        tr = window_trades(s, *TRAIN)
                        pooled[(rr, fl)].extend(tr)
                        per_strat[(rr, fl, strat)].extend(tr)
                clear_level_map_memo()
            best = max(configs, key=lambda c: (_stats(pooled[c])["win_rate"] or 0))
            bs = _stats(pooled[best])
            print(f"[{ti}/{len(ordered)}] {ticker}: best so far rr={best[0]} "
                  f"floor={best[1]}% WR={bs['win_rate']:.1f}% N={bs['n_eval']}",
                  flush=True)
    finally:
        plan_engine.STRATEGY_RR_OVERRIDE = base_rr
        plan_engine.RR_FLOOR = 0.30
        config.MIN_TARGET_PCT, config.TARGET_FLOOR_ENABLED = base_floor, base_enabled

    out = {"configs": [], "per_strategy": {}, "target_wr": TARGET_WR,
           "note": "ranked by observed win rate, per the directive; expectancy "
                   "and break-even WR are reported beside it"}
    hdr = (f"{'rr':>5s} {'floor':>6s} {'N':>7s} {'Win%':>6s} {'WilLB':>6s} "
           f"{'BE-WR%':>7s} {'ExpR':>8s} {'MaxDD%':>8s}")
    print(f"\n{'=' * 78}\n== pooled, all strategies ==\n{hdr}", flush=True)
    for c in sorted(configs, key=lambda c: -(_stats(pooled[c])["win_rate"] or 0)):
        st = _stats(pooled[c])
        wr = st["win_rate"] or 0.0
        be = _breakeven_wr(c[0])
        mark = "  <-- clears 70%" if wr >= TARGET_WR else ""
        profit = "  PROFITABLE" if wr > be else ""
        print(f"{c[0]:>5.2f} {c[1]:>6.2f} {st['n_eval']:>7d} {wr:>6.1f} "
              f"{(st['wilson_lb'] or 0):>6.1f} {be:>7.1f} "
              f"{(st['expectancy_r'] if st['expectancy_r'] is not None else 0):>+8.3f} "
              f"{(st['max_dd_pct'] or 0):>8.1f}{mark}{profit}", flush=True)
        out["configs"].append({"rr": c[0], "floor": c[1], "breakeven_wr": be,
                               "stats": st})

    print(f"\n{'=' * 78}\n== best config per strategy, by observed win rate "
          f"(N >= {MIN_N}) ==", flush=True)
    print(f"{'strategy':22s} {'rr':>5s} {'floor':>6s} {'N':>6s} {'Win%':>6s} "
          f"{'WilLB':>6s} {'BE-WR%':>7s} {'ExpR':>8s}", flush=True)
    for strat in strategies:
        cells = []
        for c in configs:
            st = _stats(per_strat[(c[0], c[1], strat)])
            if st["n_eval"] >= MIN_N:
                cells.append((c, st))
        if not cells:
            print(f"{strat:22s}   (no cell reaches N >= {MIN_N})", flush=True)
            continue
        c, st = max(cells, key=lambda x: x[1]["win_rate"] or 0)
        be = _breakeven_wr(c[0])
        flag = "  <-- 70%" if (st["win_rate"] or 0) >= TARGET_WR else ""
        print(f"{strat:22s} {c[0]:>5.2f} {c[1]:>6.2f} {st['n_eval']:>6d} "
              f"{(st['win_rate'] or 0):>6.1f} {(st['wilson_lb'] or 0):>6.1f} "
              f"{be:>7.1f} "
              f"{(st['expectancy_r'] if st['expectancy_r'] is not None else 0):>+8.3f}"
              f"{flag}", flush=True)
        out["per_strategy"][strat] = {"rr": c[0], "floor": c[1],
                                      "breakeven_wr": be, "stats": st}

    hit = [s for s, v in out["per_strategy"].items()
           if (v["stats"]["win_rate"] or 0) >= TARGET_WR]
    print(f"\nstrategies reaching {TARGET_WR}% observed WR: {hit or 'NONE'}", flush=True)
    paying = [s for s, v in out["per_strategy"].items()
              if (v["stats"]["win_rate"] or 0) > v["breakeven_wr"]]
    print(f"strategies whose best-WR cell also beats its own break-even: "
          f"{paying or 'NONE'}", flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
