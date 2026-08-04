#!/usr/bin/env python3
"""Plan v8 Task V20 -- report the shipped config separately per market regime.

WHY THIS EXISTS AS ITS OWN SCRIPT. `run_backtest_range.py` slices its trades by
`entry_date` (window_trades) only AFTER `run_backtest()` has produced the full
per-ticker/horizon/strategy summaries -- and that call is essentially all of the
runtime. Running V20's seven windows as seven `run_backtest_range.py`
invocations would therefore recompute the identical backtest seven times and
throw away six of the results. This runs the grid ONCE and accumulates into all
seven windows in the same pass. Same recomputation trap V50 found in the sizing
grid (~29/30ths waste there, 6/7ths here).

Everything expensive or statistical is imported from run_backtest_range rather
than reimplemented, so the numbers here cannot drift from that harness's.

Windows and the rejection rule are pre-registered in
`docs/superpowers/results/2026-08-04-v20-regime-slices.md` -- do not edit them
here without editing that file first.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_backtest_data import load_cached                       # noqa: E402
from run_backtest_range import (_tickers_for_run, pool,           # noqa: E402
                                pooled_max_dd_pct, window_trades)
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest   # noqa: E402
from swingbot.core.strategy_types import HORIZONS                 # noqa: E402
from swingbot.core.universe import (data_quality_issues,          # noqa: E402
                                    liquidity_reason)

# Pre-registered 2026-08-04. Peak-to-trough for each drawdown; all inside
# TRAIN (1999-01-01..2023-12-31), so no validation budget is spent.
REGIMES = [
    ("dotcom_bust", "2000-03-10", "2001-12-31"),
    ("bear_2002",   "2002-01-01", "2002-10-09"),
    ("gfc",         "2007-10-09", "2009-03-09"),
    ("y2011",       "2011-05-02", "2011-10-03"),
    ("y2015_16",    "2015-05-21", "2016-02-11"),
    ("covid",       "2020-02-19", "2020-03-23"),
    ("bear_2022",   "2022-01-03", "2022-10-12"),
]

# A window below this many closed trades is reported but excluded from the
# rejection test -- it is not evidence either way. Pre-registered.
MIN_N = 30

POST_2020 = {"covid", "bear_2022"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--strategy", default=None,
                    help="restrict to one strategy (debugging; the real run is all)")
    ap.add_argument("--exit-model", dest="exit_model", default="v2",
                    choices=["v1", "v2"])
    ap.add_argument("--scale-out", dest="scale_out", action="store_true", default=True)
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false")
    ap.add_argument("--tp2", default="levels", choices=["none", "levels"])
    ap.add_argument("--frictions", default="on", choices=["on", "off"])
    args = ap.parse_args()

    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    tp2_mode = args.tp2 if args.exit_model == "v2" else "none"
    tickers = _tickers_for_run(None)

    # regime -> strategy -> [BacktestTrade]
    buckets = {name: defaultdict(list) for name, _, _ in REGIMES}
    excluded = {"illiquid": [], "bad_data": [], "no_data": []}

    print(f"V20 regime slices | {len(tickers)} tickers x {len(HORIZONS)} horizons "
          f"x {len(strategies)} strategies | exit={args.exit_model} "
          f"scale_out={args.scale_out} tp2={tp2_mode} frictions={args.frictions}",
          flush=True)
    print(f"{len(REGIMES)} windows in ONE pass: "
          f"{', '.join(n for n, _, _ in REGIMES)}", flush=True)

    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            excluded["no_data"].append(ticker)
            print(f"[{ti}/{len(tickers)}] {ticker}: no cached data", flush=True)
            continue
        reason = liquidity_reason(df)
        if reason is not None:
            excluded["illiquid"].append((ticker, reason))
            print(f"[{ti}/{len(tickers)}] {ticker}: excluded (illiquid) -- {reason}",
                  flush=True)
            continue
        issues = data_quality_issues(df, ticker)
        if issues:
            excluded["bad_data"].append((ticker, "; ".join(issues)))
            print(f"[{ti}/{len(tickers)}] {ticker}: excluded (bad data)", flush=True)
            continue

        n_tr = 0
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                     exit_model=args.exit_model,
                                     scale_out=args.scale_out, tp2_mode=tp2_mode,
                                     frictions=(args.frictions == "on"))
                except Exception as e:                      # noqa: BLE001
                    print(f"    ! {strat}/{hk}: {e}", flush=True)
                    continue
                # ONE backtest, sliced seven ways -- this is the whole point.
                for name, d_from, d_to in REGIMES:
                    tr = window_trades(s, d_from, d_to)
                    if tr:
                        buckets[name][strat].extend(tr)
                        n_tr += len(tr)
        print(f"[{ti}/{len(tickers)}] {ticker}: +{n_tr} in-window trades", flush=True)

    # -- report ------------------------------------------------------------
    out = {"config": {"exit_model": args.exit_model, "scale_out": args.scale_out,
                      "tp2": tp2_mode, "frictions": args.frictions,
                      "min_n": MIN_N},
           "regimes": {}}

    print("\n== V20 regime slices ==", flush=True)
    print(f"{'Regime':14s} {'Window':25s} {'N':>6s} {'Win%':>6s} {'ExpR':>8s} {'Verdict':>12s}")
    for name, d_from, d_to in REGIMES:
        all_tr = [t for trs in buckets[name].values() for t in trs]
        st = pool(all_tr)
        st["max_dd_pct"] = pooled_max_dd_pct(all_tr)
        n = st["n_eval"]
        verdict = "INSUFFICIENT" if n < MIN_N else ("pos" if (st["expectancy_r"] or 0) > 0
                                                    else "non-pos")
        per_strat = {}
        for strat, trs in buckets[name].items():
            ss = pool(trs)
            ss["max_dd_pct"] = pooled_max_dd_pct(trs)
            per_strat[strat] = ss
        out["regimes"][name] = {"from": d_from, "to": d_to, "pooled": st,
                                "verdict": verdict, "by_strategy": per_strat}
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        print(f"{name:14s} {d_from}..{d_to} {n:6d} {wr:>6s} {er:>8s} {verdict:>12s}",
              flush=True)

    # Pre-registered rejection rule, applied mechanically.
    pre = {n: out["regimes"][n] for n, _, _ in REGIMES if n not in POST_2020}
    post = {n: out["regimes"][n] for n in POST_2020}
    suff_pre = {n: r for n, r in pre.items() if r["verdict"] != "INSUFFICIENT"}
    # `all()` over an empty sequence is True, so without the bool() guard a run
    # where BOTH post-2020 windows come back INSUFFICIENT would satisfy
    # "expectancy > 0 in the post-2020 windows" vacuously and could fire a
    # regime-fragile rejection on no post-2020 evidence at all. Reachable: the
    # COVID window is ~23 trading days, and the RSI-only check had both post
    # windows under N=30. The rule as pre-registered requires the post-2020
    # side to be *measured* positive, which needs at least one sufficient
    # window. Corrected 2026-08-04 BEFORE the full grid's numbers existed.
    suff_post = {n: r for n, r in post.items() if r["verdict"] != "INSUFFICIENT"}
    post_positive = bool(suff_post) and all(
        (r["pooled"]["expectancy_r"] or 0) > 0 for r in suff_post.values())
    pre_all_nonpos = bool(suff_pre) and all(
        (r["pooled"]["expectancy_r"] or 0) <= 0 for r in suff_pre.values())
    rejected = bool(post_positive and pre_all_nonpos)
    out["rejection_test"] = {
        "rule": "reject if post-2020 expectancy > 0 AND every sufficient "
                "pre-2020 window <= 0",
        "sufficient_pre_2020": sorted(suff_pre),
        "sufficient_post_2020": sorted(suff_post),
        "post_2020_all_positive": post_positive,
        "pre_2020_all_non_positive": pre_all_nonpos,
        "REJECTED_AS_REGIME_FRAGILE": rejected,
    }
    print(f"\nrejection test -> REJECTED={rejected} "
          f"(sufficient pre-2020 windows: {sorted(suff_pre) or 'none'})", flush=True)
    if not suff_pre:
        print("  NOTE: no pre-2020 window reached N>=%d, so the rejection test "
              "could not be evaluated -- that is an absence of evidence, not a pass."
              % MIN_N, flush=True)
    if not suff_post:
        print("  NOTE: no post-2020 window reached N>=%d either, so the "
              "post-2020 side of the rule is unmeasured -- rejection cannot "
              "fire on it, in either direction." % MIN_N, flush=True)

    out["excluded"] = {"illiquid": excluded["illiquid"],
                       "bad_data": excluded["bad_data"],
                       "no_data": excluded["no_data"]}
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
