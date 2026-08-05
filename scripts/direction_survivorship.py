#!/usr/bin/env python3
"""Plan v8 Task V21 -- direction & survivorship audit of the bullish-only gates.

WHAT IS UNDER TEST. `STRATEGY_GATES` (strategy_types.py:250-263) restricts
seven of eleven strategies to `directions=("bullish",)`. Those masks were
fitted on the 2020-2023 TRAIN window -- four bull years -- and the module's own
comment says so. V21 asks two questions the fit cannot answer about itself:
does the long side actually beat the short side once you leave that window
(Step 1), and is the long-side edge an artifact of running 25 years of
backtest over a watchlist made of today's survivors (Step 2)?

THE GATES ARE THEREFORE RUN OFF. A bullish-only strategy emits zero bearish
signals by construction, so a gated run cannot compare the two arms -- the
comparison would be against an empty set. `--gates on` exists for a
shipped-config contrast; the pre-registered run is `--gates off` (the
default). This patches `entry_filters.STRATEGY_GATES`, the one binding
`entries_for` actually reads (backtest.py imports the name but never uses it,
checked 2026-08-05).

SINGLE PASS, MANY SLICES -- the V50/V20 trap. `run_backtest` is essentially
all of the runtime and is identical no matter how the resulting trades are
later bucketed, so this runs the ticker x horizon x strategy grid ONCE and
accumulates every slice (7 regimes x direction, TRAIN x direction x tercile,
...) from that single pass. Slicing by re-invoking a range script once per
bucket would recompute the identical backtest tens of times.

Windows, tercile membership and all three decision rules are pre-registered in
`docs/superpowers/results/2026-08-05-v21-direction-survivorship.md` -- do not
edit them here without editing that file first. REGIMES and MIN_N are imported
from the V20 harness rather than copied so the two cannot drift.
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
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest   # noqa: E402
from swingbot.core.backtest_windows import TRAIN                  # noqa: E402
from swingbot.core.strategy_types import HORIZONS, STRATEGY_GATES  # noqa: E402
from swingbot.core.universe import (data_quality_issues,          # noqa: E402
                                    liquidity_reason)

# --- pre-registered 2026-08-05 -------------------------------------------
# Ranking substrate for the survivorship probe: CAGR of the adjusted close
# over the ticker's own TRAIN-overlapping history. Adjusted (auto_adjust=True
# in the cache builder), so this is total return, not price return.
MIN_RANK_BARS = 252          # < 1 TRAIN year of bars -> UNRANKED, not forced into a tercile

# Survivorship-free by construction: a commodity future cannot be delisted for
# performance, and neither was picked for having gone up. The only two
# non-equity members of the watchlist.
NON_EQUITY = {"GC=F", "SI=F"}

# A ticker already listed when the cache opens was not added to the watchlist
# for becoming notable later -- it was there to be picked. Anything later is a
# "late lister". NOTE the cutoff is 2001, not 2000: TRAIN nominally opens
# 1999-01-01 but the deepest cached series starts **2000-01-03**, so no ticker
# has a 1999 bar and a 2000-01-01 cutoff classifies the entire universe as
# late. Measured 2026-08-05, before the run.
COHORT_CUTOFF = "2001-01-01"

# Test B's confound, found in the ranking pass before any backtest ran: TRAIN
# CAGR over 490 bars (CEG) is not the same measurement as over 6037 (AAPL),
# and the raw top tercile is mostly short-history late listers whose CAGR is
# really a 2021-2023 regime reading. B2 re-ranks inside the subsample that
# spans the whole window, so tercile varies with eventual performance and
# nothing else. B2 is the rule-bearing arm; B1 is reported beside it.
FULL_HISTORY_BARS = 5000
# -------------------------------------------------------------------------


def train_cagr(df):
    """CAGR of the adjusted close across this ticker's TRAIN-overlapping bars.

    Returns (cagr, n_bars, first_date) or (None, n_bars, first_date) when the
    ticker has too little TRAIN history to rank. 252 bars/year rather than
    calendar days so a ticker with gaps is not flattered."""
    d = df.loc[(df.index >= TRAIN[0]) & (df.index <= TRAIN[1])]
    n = len(d)
    first_date = d.index[0].strftime("%Y-%m-%d") if n else None
    if n < MIN_RANK_BARS:
        return None, n, first_date
    first, last = float(d["Close"].iloc[0]), float(d["Close"].iloc[-1])
    if first <= 0 or last <= 0:
        return None, n, first_date
    return (last / first) ** (252.0 / n) - 1.0, n, first_date


def assign_terciles(cagrs):
    """Rank tickers by TRAIN CAGR into three equal-count buckets.

    Equal COUNT, not equal width: the CAGR distribution is heavily
    right-skewed (a 1999-cohort mega-cap compounds several hundred-fold), so
    equal-width bins would put ~70 tickers in one bucket and defeat the probe.
    Ties broken by ticker name for determinism -- the membership table is
    committed in the pre-registration and must reproduce exactly."""
    ranked = sorted((t for t, c in cagrs.items() if c is not None),
                    key=lambda t: (cagrs[t], t))
    n = len(ranked)
    out = {t: "unranked" for t in cagrs}
    for i, t in enumerate(ranked):
        # i*3//n gives 0/1/2 with the remainder landing in the upper buckets.
        out[t] = ("bottom", "middle", "top")[i * 3 // n]
    return out


def _stats(trades):
    """pool() plus the two figures every decision rule in the pre-registration
    reads. Wilson LB is on the win rate, per V6 Step 5 -- never a point
    estimate on its own."""
    st = pool(trades)
    st["max_dd_pct"] = pooled_max_dd_pct(trades)
    # wilson_lower_bound already returns percent -- do not rescale.
    st["wilson_lb"] = wilson_lower_bound(st["wins"], st["n_eval"])
    return st


def _row(label, st, width=26):
    wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
    lb = f"{st['wilson_lb']:.1f}" if st["wilson_lb"] is not None else "n/a"
    er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
    flag = "" if st["n_eval"] >= MIN_N else "  INSUFFICIENT"
    return f"{label:{width}s} {st['n_eval']:6d} {wr:>6s} {lb:>6s} {er:>8s}{flag}"


def _delta(long_st, short_st):
    """long minus short, and whether both arms cleared the sufficiency bar.

    The DIFFERENCE is the quantity the rules read, not either level. V51
    measured daily bars overstating expectancy by +0.318R/trade
    (`2026-08-02-v51-hourly-fidelity.md`); that bias sits on both arms of a
    long-vs-short comparison, so a difference survives a correction that no
    absolute ExpR here survives. This is an assumption about the bias being
    roughly direction-symmetric, not a measurement of it -- the hourly run
    was never sliced by direction. Recorded as an assumption in the results
    file."""
    ok = long_st["n_eval"] >= MIN_N and short_st["n_eval"] >= MIN_N
    if long_st["expectancy_r"] is None or short_st["expectancy_r"] is None:
        return None, ok
    return long_st["expectancy_r"] - short_st["expectancy_r"], ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--strategy", default=None,
                    help="restrict to one strategy (debugging; the real run is all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N tickers only (debugging/timing probe)")
    ap.add_argument("--gates", default="off", choices=["off", "on"],
                    help="off (pre-registered): STRATEGY_GATES disabled so both "
                         "directions emit. on: shipped config, for contrast only.")
    ap.add_argument("--terciles-only", action="store_true",
                    help="print the survivorship ranking and exit -- no backtest. "
                         "Used to commit the membership BEFORE the run.")
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
    if args.limit:
        tickers = tickers[:args.limit]

    # -- survivorship ranking: price data only, no backtest, no outcomes ----
    cagrs, meta, frames = {}, {}, {}
    excluded = {"illiquid": [], "bad_data": [], "no_data": []}
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None:
            excluded["no_data"].append(ticker)
            continue
        reason = liquidity_reason(df)
        if reason is not None:
            excluded["illiquid"].append((ticker, reason))
            continue
        issues = data_quality_issues(df, ticker)
        if issues:
            excluded["bad_data"].append((ticker, "; ".join(issues)))
            continue
        c, nbars, first_date = train_cagr(df)
        cagrs[ticker] = c
        meta[ticker] = {"train_bars": nbars, "first_train_bar": first_date,
                        "train_cagr": c}
        frames[ticker] = df

    tercile = assign_terciles(cagrs)
    # B2: re-rank inside the full-history subsample only. Everything else is
    # "excluded_b2" rather than being folded into a bucket it cannot inform.
    full_hist = {t: c for t, c in cagrs.items()
                 if meta[t]["train_bars"] >= FULL_HISTORY_BARS}
    tercile_b2 = assign_terciles(full_hist)
    for t in meta:
        meta[t]["tercile"] = tercile[t]
        meta[t]["tercile_b2"] = tercile_b2.get(t, "excluded_b2")
        meta[t]["full_history"] = meta[t]["train_bars"] >= FULL_HISTORY_BARS
        meta[t]["asset_class"] = "non_equity" if t in NON_EQUITY else "equity"
        fd = meta[t]["first_train_bar"]
        meta[t]["cohort"] = ("listed_at_cache_open" if fd and fd < COHORT_CUTOFF
                             else "late_lister")

    print(f"V21 survivorship ranking | {len(frames)} tickers ranked by TRAIN CAGR "
          f"({TRAIN[0]}..{TRAIN[1]}), min {MIN_RANK_BARS} bars", flush=True)
    for t in sorted(meta, key=lambda t: (-(meta[t]["train_cagr"] or -9e9), t)):
        m = meta[t]
        cg = f"{m['train_cagr'] * 100:+8.2f}%" if m["train_cagr"] is not None else "  UNRANKED"
        print(f"  {t:6s} {cg} B1={m['tercile']:9s} B2={m['tercile_b2']:12s} "
              f"{m['cohort']:20s} {m['asset_class']:10s} "
              f"bars={m['train_bars']:5d} from={m['first_train_bar']}", flush=True)
    print(f"  -- B2 subsample: {sum(1 for m in meta.values() if m['full_history'])}"
          f" tickers with >={FULL_HISTORY_BARS} TRAIN bars", flush=True)
    for key in ("illiquid", "bad_data", "no_data"):
        if excluded[key]:
            names = [e if isinstance(e, str) else e[0] for e in excluded[key]]
            print(f"  -- excluded ({key}): {', '.join(sorted(names))}", flush=True)
    if args.terciles_only:
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump({"tickers": meta, "excluded": excluded}, f, indent=2,
                          default=str)
            print(f"\nwrote {args.json_out}", flush=True)
        return

    # -- the object under test ---------------------------------------------
    if args.gates == "off":
        entry_filters.STRATEGY_GATES = {}
        print("\nSTRATEGY_GATES DISABLED for this run -- the gates are what V21 "
              "audits, and a bullish-only strategy cannot be compared against "
              "its own empty short arm.", flush=True)
    else:
        print("\nSTRATEGY_GATES LIVE (shipped config) -- contrast run; the "
              "bearish arm of 7/11 strategies is empty BY CONSTRUCTION and "
              "means nothing.", flush=True)
    gated_strats = sorted(STRATEGY_GATES)

    # bucket -> [BacktestTrade]. Trades are stored once and referenced from
    # every bucket they belong to, so N buckets cost pointers, not copies.
    regime_dir = defaultdict(list)        # (regime, direction)
    bear_dir_strat = defaultdict(list)    # (direction, strategy) pooled over all 7
    train_dir = defaultdict(list)         # direction
    train_dir_strat = defaultdict(list)   # (direction, strategy)
    train_dir_terc = defaultdict(list)    # (direction, tercile)          B1
    train_dir_terc2 = defaultdict(list)   # (direction, tercile_b2)       B2
    train_dir_class = defaultdict(list)   # (direction, asset_class)
    train_dir_cohort = defaultdict(list)  # (direction, cohort)

    print(f"\nV21 grid | {len(frames)} tickers x {len(HORIZONS)} horizons x "
          f"{len(strategies)} strategies | exit={args.exit_model} "
          f"scale_out={args.scale_out} tp2={tp2_mode} frictions={args.frictions} "
          f"gates={args.gates}", flush=True)

    for ti, ticker in enumerate(sorted(frames), 1):
        df = frames[ticker]
        m = meta[ticker]
        n_tr = n_bear = 0
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
                # ONE backtest, every slice taken off it -- the whole point.
                for t in window_trades(s, *TRAIN):
                    d = t.direction
                    train_dir[d].append(t)
                    train_dir_strat[(d, strat)].append(t)
                    train_dir_terc[(d, m["tercile"])].append(t)
                    train_dir_terc2[(d, m["tercile_b2"])].append(t)
                    train_dir_class[(d, m["asset_class"])].append(t)
                    train_dir_cohort[(d, m["cohort"])].append(t)
                    n_tr += 1
                    if d == "bearish":
                        n_bear += 1
                for name, d_from, d_to in REGIMES:
                    for t in window_trades(s, d_from, d_to):
                        regime_dir[(name, t.direction)].append(t)
                        bear_dir_strat[(t.direction, strat)].append(t)
        print(f"[{ti}/{len(frames)}] {ticker}: +{n_tr} TRAIN trades "
              f"({n_bear} bearish) [{m['tercile']}]", flush=True)

    # -- report -------------------------------------------------------------
    out = {"config": {"exit_model": args.exit_model, "scale_out": args.scale_out,
                      "tp2": tp2_mode, "frictions": args.frictions,
                      "gates": args.gates, "min_n": MIN_N,
                      "train": list(TRAIN), "min_rank_bars": MIN_RANK_BARS},
           "tickers": meta, "excluded": excluded}

    hdr = f"{'':26s} {'N':>6s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>8s}"

    # Step 1: long vs short per regime.
    print("\n== V21 Step 1: long vs short expectancy per regime ==", flush=True)
    print(hdr, flush=True)
    out["step1_regimes"] = {}
    for name, d_from, d_to in REGIMES:
        lo, sh = _stats(regime_dir[(name, "bullish")]), _stats(regime_dir[(name, "bearish")])
        d, ok = _delta(lo, sh)
        out["step1_regimes"][name] = {"from": d_from, "to": d_to, "long": lo,
                                      "short": sh, "long_minus_short_r": d,
                                      "both_sufficient": ok}
        print(_row(f"{name} long", lo), flush=True)
        print(_row(f"{name} short", sh), flush=True)
        ds = f"{d:+.3f}" if d is not None else "n/a"
        print(f"{'  -> long-short ExpR':26s} {ds:>29s}"
              f"{'' if ok else '   (one arm INSUFFICIENT)'}", flush=True)

    lo, sh = _stats(train_dir["bullish"]), _stats(train_dir["bearish"])
    d_train, ok_train = _delta(lo, sh)
    out["step1_train"] = {"long": lo, "short": sh, "long_minus_short_r": d_train,
                          "both_sufficient": ok_train}
    print("\n-- full TRAIN, for reference (not a regime) --", flush=True)
    print(_row("TRAIN long", lo), flush=True)
    print(_row("TRAIN short", sh), flush=True)

    # Step 2 / Test A: does each gated strategy's bullish-only premise hold in
    # the seven drawdowns, where a bullish-only mask is most exposed?
    print("\n== V21 Step 2 / Test A: gated strategies, long vs short, "
          "all 7 drawdown windows pooled ==", flush=True)
    print(hdr, flush=True)
    out["test_a_gated_strategies"] = {}
    a_fail, a_pass, a_insuff = [], [], []
    for strat in strategies:
        lo, sh = _stats(bear_dir_strat[("bullish", strat)]), _stats(bear_dir_strat[("bearish", strat)])
        d, ok = _delta(lo, sh)
        verdict = ("INSUFFICIENT" if not ok
                   else "SURVIVES" if (d or 0) >= 0 else "FAILS")
        is_gated = strat in STRATEGY_GATES
        out["test_a_gated_strategies"][strat] = {
            "gated_bullish_only": is_gated, "long": lo, "short": sh,
            "long_minus_short_r": d, "verdict": verdict}
        if is_gated:
            (a_insuff if verdict == "INSUFFICIENT"
             else a_pass if verdict == "SURVIVES" else a_fail).append(strat)
        mark = "GATED" if is_gated else "     "
        print(_row(f"{mark} {strat} long", lo, 30), flush=True)
        print(_row(f"{mark} {strat} short", sh, 30), flush=True)
        ds = f"{d:+.3f}" if d is not None else "n/a"
        print(f"{'      -> long-short':30s} {ds:>29s}   {verdict}", flush=True)

    # Step 2 / Test B: the survivorship probe. B2 carries the rule; B1 is the
    # same cut over every ranked ticker and is confounded by history length.
    def _terciles(buckets, meta_key, keys):
        block = {}
        for terc in keys:
            lo = _stats(buckets[("bullish", terc)])
            sh = _stats(buckets[("bearish", terc)])
            d, ok = _delta(lo, sh)
            block[terc] = {"long": lo, "short": sh, "long_minus_short_r": d,
                           "both_sufficient": ok,
                           "members": sorted(t for t in meta
                                             if meta[t][meta_key] == terc)}
            print(_row(f"{terc} long", lo), flush=True)
            print(_row(f"{terc} short", sh), flush=True)
        return block

    print("\n== V21 Step 2 / Test B2 (RULE-BEARING): long-side edge by TRAIN-CAGR "
          f"tercile, full-history subsample only (>={FULL_HISTORY_BARS} bars) ==",
          flush=True)
    print(hdr, flush=True)
    out["test_b2_terciles"] = _terciles(train_dir_terc2, "tercile_b2",
                                        ("bottom", "middle", "top", "excluded_b2"))

    print("\n== V21 Step 2 / Test B1 (reported, confounded by history length): "
          "same cut over every ranked ticker ==", flush=True)
    print(hdr, flush=True)
    out["test_b1_terciles"] = _terciles(train_dir_terc, "tercile",
                                        ("bottom", "middle", "top", "unranked"))

    bot_l = out["test_b2_terciles"]["bottom"]["long"]
    top_l = out["test_b2_terciles"]["top"]["long"]
    b_evaluable = (bot_l["n_eval"] >= MIN_N and top_l["n_eval"] >= MIN_N)
    b_artifact = bool(b_evaluable
                      and (bot_l["expectancy_r"] or 0) <= 0
                      and (top_l["expectancy_r"] or 0) > 0)
    out["test_b_verdict"] = {
        "rule": "read on B2 (full-history subsample): the long-side edge is a "
                "survivorship artifact if bottom-tercile long ExpR <= 0 while "
                "top-tercile long ExpR > 0, both at N>=%d" % MIN_N,
        "evaluable": b_evaluable,
        "ARTIFACT": b_artifact,
        "asymmetry": "firing CONFIRMS the artifact; not firing CANNOT CLEAR it -- "
                     "every ticker in this universe survived to 2026, so the "
                     "sample is truncated before the test begins",
    }

    # Step 2 / Test C: the two survivorship-free members, and the listing cohort.
    print("\n== V21 Step 2 / Test C: survivorship-free control + listing cohort ==",
          flush=True)
    print(hdr, flush=True)
    out["test_c_controls"] = {}
    for key, buckets in (("asset_class", train_dir_class), ("cohort", train_dir_cohort)):
        for grp in sorted({k[1] for k in buckets}):
            lo, sh = _stats(buckets[("bullish", grp)]), _stats(buckets[("bearish", grp)])
            d, ok = _delta(lo, sh)
            out["test_c_controls"][grp] = {"axis": key, "long": lo, "short": sh,
                                           "long_minus_short_r": d,
                                           "both_sufficient": ok}
            print(_row(f"{grp} long", lo), flush=True)
            print(_row(f"{grp} short", sh), flush=True)

    # -- pre-registered verdicts, applied mechanically ----------------------
    out["verdicts"] = {
        "test_a_gated_failing": sorted(a_fail),
        "test_a_gated_surviving": sorted(a_pass),
        "test_a_gated_insufficient": sorted(a_insuff),
        "test_a_all_gated": gated_strats,
        "test_b_artifact": b_artifact,
    }
    print("\n== pre-registered verdicts ==", flush=True)
    print(f"Test A  gates whose bullish-only premise FAILS in drawdowns: "
          f"{sorted(a_fail) or 'none'}", flush=True)
    print(f"Test A  premise survives: {sorted(a_pass) or 'none'}", flush=True)
    print(f"Test A  insufficient N: {sorted(a_insuff) or 'none'}", flush=True)
    print(f"Test B  long edge is a survivorship artifact: {b_artifact} "
          f"(evaluable={b_evaluable})", flush=True)
    if not b_evaluable:
        print("  NOTE: Test B could not be evaluated at N>=%d -- absence of "
              "evidence, not a pass." % MIN_N, flush=True)
    print("  Test B is one-directional: it can confirm the artifact, never "
          "clear it. The universe is 78 tickers that all survived to 2026.",
          flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
