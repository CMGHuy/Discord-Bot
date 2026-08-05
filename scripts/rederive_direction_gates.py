"""Re-derive `STRATEGY_GATES` for the strategies V21 failed (plan v8, V21 follow-up).

V21 (`docs/superpowers/results/2026-08-05-v21-direction-survivorship.md`) found
five gated strategies whose bullish-only premise is contradicted in the seven
drawdown windows: Fibonacci, MA Ribbon, MACD, VWAP, Volume Profile. Their masks
were fitted on the 2020-2023 bull window under an acceptance bar (`WR >= 80`)
that plan v8 Task V6 has since **voided** — it was set when a "win" meant
touching a ~0.85% target, and under the 2.5% floor it measures a different
event. So the masks cannot simply be re-fitted with the old rule.

This runs the ticker x horizon x strategy grid **once** with `STRATEGY_GATES`
patched off (a masked strategy cannot show you the arm it masks) and takes
every slice off that single pass — the V50/V20 recomputation trap.

The decision rule is pre-registered in
`docs/superpowers/results/2026-08-05-v53-gate-rederivation.md` and applied
here mechanically, mildest-gate-first, mirroring the shape of the original
derivation (`2026-07-train-tuning.md` Step 4) with the voided WR bar replaced
by expectancy — the objective V6 Step 3b made primary:

  1. UNGATED      pooled over both directions and all horizons, ExpR > 0 at
                  N >= MIN_N  ->  no mask at all (mildest possible gate)
  2. DIRECTION    else the single direction arm with ExpR > 0 at N >= MIN_N
  3. DIR+HORIZON  else, within the better-ExpR direction, the horizons with
                  ExpR > 0 and N >= MIN_N_HORIZON, if the pooled subset
                  itself clears ExpR > 0 at N >= MIN_N
  4. FAILING      else no mask reaches positive TRAIN expectancy -> the gate
                  is REMOVED and the strategy recorded as failing, exactly as
                  the original derivation handled EMA Crossover / Elliott Wave

Rule 4 removes rather than keeps: a mask that no longer has evidence behind it
is not made safer by being left in place, and leaving it would preserve the
2020-2023 fit this task exists to retire.

Every selected mask also gets its expectancy reported across V20's seven
drawdown windows. That is a **mandatory disclosure, not a rejection rule** —
selecting on TRAIN and rejecting on the same regimes that motivated the task
would be double-dipping. It exists so the next reader can see whether the new
mask is once again a bull-majority artifact.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_backtest_data import load_cached                       # noqa: E402
from regime_slices import MIN_N, REGIMES                          # noqa: E402
from run_backtest_range import (_tickers_for_run, pool,           # noqa: E402
                                pooled_max_dd_pct, window_trades,
                                wilson_lower_bound)
from swingbot.core import entry_filters                           # noqa: E402
from swingbot.core.backtest import run_backtest                   # noqa: E402
from swingbot.core.backtest_windows import TRAIN                  # noqa: E402
from swingbot.core.strategy_types import HORIZONS, STRATEGY_GATES  # noqa: E402
from swingbot.core.universe import (data_quality_issues,          # noqa: E402
                                    liquidity_reason)

# --- pre-registered 2026-08-05, before the grid ran ----------------------
# The five V21 failures. RSI (INSUFFICIENT, N=20/10) and Support/Resistance
# (SURVIVES on +0.014R) are NOT in scope: V21's rule did not fail them, and
# re-deriving a gate the audit did not condemn would be scope creep.
FAILING = ["Fibonacci", "MA Ribbon", "MACD", "VWAP", "Volume Profile"]

MIN_N_HORIZON = 30      # per-horizon floor for rule 3. The original derivation
                        # used N>=10 here; V6's sample-size clause calls that
                        # too thin to select on, and selecting 10 horizons x 2
                        # directions off N=10 cells is how the current masks
                        # were overfitted in the first place.
DIRECTIONS = ("bullish", "bearish")


def _stats(trades):
    st = pool(trades)
    st["max_dd_pct"] = pooled_max_dd_pct(trades)
    st["wilson_lb"] = wilson_lower_bound(st["wins"], st["n_eval"])
    return st


def _ok(st):
    """The sufficiency + sign test every rule below reads."""
    return (st["n_eval"] >= MIN_N and st["expectancy_r"] is not None
            and st["expectancy_r"] > 0)


def _row(label, st, width=30):
    wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
    lb = f"{st['wilson_lb']:.1f}" if st["wilson_lb"] is not None else "n/a"
    er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
    flag = "" if st["n_eval"] >= MIN_N else "  INSUFFICIENT"
    return f"{label:{width}s} {st['n_eval']:6d} {wr:>6s} {lb:>6s} {er:>8s}{flag}"


def derive(strat, pooled, by_dir, by_dir_hz):
    """Apply the pre-registered ladder. Returns (mask, rule, why)."""
    if _ok(pooled):
        return None, "1-UNGATED", (
            f"pooled both directions ExpR={pooled['expectancy_r']:+.3f} "
            f"at N={pooled['n_eval']} -- no mask needed")

    positive = [d for d in DIRECTIONS if _ok(by_dir[d])]
    if len(positive) == 1:
        d = positive[0]
        return ({"directions": (d,)}, "2-DIRECTION",
                f"{d} ExpR={by_dir[d]['expectancy_r']:+.3f} at "
                f"N={by_dir[d]['n_eval']}; other arm not positive at N>={MIN_N}")
    if len(positive) == 2:
        # Both arms positive but the pool is not -> arithmetically impossible
        # (the pool is their N-weighted mean). Guard rather than assume.
        return None, "1-UNGATED", "both arms positive; pooled follows"

    best = max(DIRECTIONS,
               key=lambda d: (by_dir[d]["expectancy_r"]
                              if by_dir[d]["expectancy_r"] is not None else -9e9))
    keep = sorted(hk for hk in HORIZONS if _ok_h(by_dir_hz[(best, hk)]))
    if keep:
        subset = _stats([t for hk in keep for t in by_dir_hz[(best, hk)]["_trades"]])
        if _ok(subset):
            return ({"directions": (best,), "horizons": tuple(keep)},
                    "3-DIR+HORIZON",
                    f"{best} + {keep}: ExpR={subset['expectancy_r']:+.3f} "
                    f"at N={subset['n_eval']}")
        return None, "4-FAILING", (
            f"{best} + {keep} pooled to ExpR="
            f"{subset['expectancy_r']:+.3f} at N={subset['n_eval']} -- "
            f"the per-horizon subset does not survive pooling")
    return None, "4-FAILING", (
        f"no direction and no horizon subset of the better arm ({best}) "
        f"reaches ExpR > 0 at N >= {MIN_N_HORIZON}")


def _ok_h(st):
    return (st["n_eval"] >= MIN_N_HORIZON and st["expectancy_r"] is not None
            and st["expectancy_r"] > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--strategies", default=None,
                    help="comma-separated; default is V21's five failures")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--exit-model", dest="exit_model", default="v2")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true", default=True)
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false")
    ap.add_argument("--tp2", default="levels", choices=["none", "levels"])
    ap.add_argument("--frictions", default="on", choices=["on", "off"])
    args = ap.parse_args()

    strategies = ([s.strip() for s in args.strategies.split(",")]
                  if args.strategies else list(FAILING))

    tickers = _tickers_for_run(None)
    if args.limit:
        tickers = tickers[:args.limit]
    frames, excluded = {}, {"illiquid": [], "bad_data": [], "no_data": []}
    for t in tickers:
        df = load_cached(t)
        if df is None:
            excluded["no_data"].append(t)
            continue
        r = liquidity_reason(df)
        if r:
            excluded["illiquid"].append((t, r))
            continue
        iss = data_quality_issues(df, t)
        if iss:
            excluded["bad_data"].append((t, "; ".join(iss)))
            continue
        frames[t] = df

    entry_filters.STRATEGY_GATES = {}
    print("STRATEGY_GATES DISABLED -- a bullish-only strategy cannot show you "
          "the arm it masks, and both arms are what the rule reads.", flush=True)
    print(f"\ngate re-derivation | {len(frames)} tickers x {len(HORIZONS)} "
          f"horizons x {len(strategies)} strategies | exit={args.exit_model} "
          f"scale_out={args.scale_out} tp2={args.tp2} "
          f"frictions={args.frictions}", flush=True)
    print(f"current masks: "
          + "; ".join(f"{s}={STRATEGY_GATES.get(s)}" for s in strategies), flush=True)

    t_pooled = defaultdict(list)          # strat
    t_dir = defaultdict(list)             # (strat, direction)
    t_dir_hz = defaultdict(list)          # (strat, direction, horizon)
    t_dir_regime = defaultdict(list)      # (strat, direction, regime)

    for ti, ticker in enumerate(sorted(frames), 1):
        df = frames[ticker]
        n = 0
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                     exit_model=args.exit_model,
                                     scale_out=args.scale_out,
                                     tp2_mode=args.tp2,
                                     frictions=(args.frictions == "on"))
                except Exception as e:                        # noqa: BLE001
                    print(f"    ! {strat}/{hk}: {e}", flush=True)
                    continue
                for tr in window_trades(s, *TRAIN):
                    t_pooled[strat].append(tr)
                    t_dir[(strat, tr.direction)].append(tr)
                    t_dir_hz[(strat, tr.direction, hk)].append(tr)
                    n += 1
                for name, d_from, d_to in REGIMES:
                    for tr in window_trades(s, d_from, d_to):
                        t_dir_regime[(strat, tr.direction, name)].append(tr)
        print(f"[{ti}/{len(frames)}] {ticker}: +{n} TRAIN trades", flush=True)

    out = {"config": {"exit_model": args.exit_model, "scale_out": args.scale_out,
                      "tp2": args.tp2, "frictions": args.frictions,
                      "gates": "off", "min_n": MIN_N,
                      "min_n_horizon": MIN_N_HORIZON, "train": list(TRAIN)},
           "excluded": excluded, "strategies": {}}

    hdr = f"{'':30s} {'N':>6s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>8s}"
    for strat in strategies:
        print(f"\n{'=' * 72}\n== {strat} ==", flush=True)
        print(hdr, flush=True)
        pooled = _stats(t_pooled[strat])
        by_dir = {d: _stats(t_dir[(strat, d)]) for d in DIRECTIONS}
        print(_row("pooled (ungated)", pooled), flush=True)
        for d in DIRECTIONS:
            print(_row(f"  {d}", by_dir[d]), flush=True)

        by_dir_hz = {}
        for d in DIRECTIONS:
            for hk in HORIZONS:
                st = _stats(t_dir_hz[(strat, d, hk)])
                st["_trades"] = t_dir_hz[(strat, d, hk)]
                by_dir_hz[(d, hk)] = st
        for d in DIRECTIONS:
            for hk in HORIZONS:
                st = by_dir_hz[(d, hk)]
                if st["n_eval"]:
                    print(_row(f"    {d}/{hk}", st), flush=True)

        mask, rule, why = derive(strat, pooled, by_dir, by_dir_hz)
        print(f"\n  RULE {rule}: {why}", flush=True)
        print(f"  current : {STRATEGY_GATES.get(strat)}", flush=True)
        print(f"  proposed: {mask}", flush=True)

        # Mandatory disclosure: how the SELECTED mask behaves in V20's seven
        # drawdowns. Reported, never read by the rule.
        dirs = mask["directions"] if mask else DIRECTIONS
        regimes = {}
        for name, _f, _t in REGIMES:
            trades = [tr for d in dirs for tr in t_dir_regime[(strat, d, name)]]
            st = _stats(trades)
            regimes[name] = {k: v for k, v in st.items() if not k.startswith("_")}
            print(_row(f"    [regime] {name}", st), flush=True)

        out["strategies"][strat] = {
            "current_mask": STRATEGY_GATES.get(strat),
            "proposed_mask": mask, "rule": rule, "why": why,
            "pooled": pooled,
            "by_direction": by_dir,
            "by_direction_horizon": {f"{d}/{hk}": {k: v for k, v in
                                                   by_dir_hz[(d, hk)].items()
                                                   if not k.startswith("_")}
                                     for d in DIRECTIONS for hk in HORIZONS},
            "selected_mask_by_regime": regimes,
        }

    print(f"\n{'=' * 72}\n== proposed STRATEGY_GATES changes ==", flush=True)
    for strat in strategies:
        r = out["strategies"][strat]
        print(f"  {strat:22s} {str(r['current_mask']):58s}"
              f"\n  {'':22s} -> {r['proposed_mask']}  [{r['rule']}]", flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
