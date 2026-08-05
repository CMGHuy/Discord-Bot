"""Strictest-gate-first re-derivation of `STRATEGY_GATES`, held out (plan v8 V54).

V53 re-derived five gates under a **mildest**-gate-first ladder and returned
five masks, every one looser than what it replaced. That was structural: a
mildest-first ladder starts at the loosest mask and stops at the first rung
that passes, so it cannot return anything stricter than the status quo.

This inverts it, and folds the non-loosening requirement into the rule instead
of applying it afterwards as V53 had to:

  A  admissible cell   = (direction, horizon) ALREADY ADMITTED BY THE CURRENT
                         MASK, with ExpR > 0 at N >= MIN_N on the FIT half
  B  candidate mask    = cross-product closure of the admissible cells
                         (STRATEGY_GATES cannot express arbitrary pairs), which
                         must itself clear ExpR > 0 at N >= MIN_N on FIT
  C  non-loosening     = candidate's whole-universe TRAIN signal count must be
                         <= the current mask's. Step A restricting to currently
                         admitted cells makes the candidate a SUBSET of the
                         current mask, so this holds by construction; C stays
                         as a defensive assertion. (Drawn from all 20 cells
                         instead, the closure spans every admissible horizon
                         and so *loosens* any already-tight mask -- the ladder
                         could then only ever say KEEP, never tighten. Found in
                         a 6-ticker smoke test before the rule was committed.)
  D  confirmation      = candidate clears ExpR > 0 at N >= MIN_N on CONFIRM,
                         the half no selection step reads

  ADOPT iff B, C and D pass.  OTHERWISE KEEP THE CURRENT MASK.

Failure keeps the current mask and never removes one -- the exact inversion of
V53's rule 4, and what makes this ladder non-loosening *by construction*.

The FIT/CONFIRM split is by ticker, not by time. V21 established that direction
edge here is regime-conditional, so a time split would confound "the selection
was noise" with "the regime changed", and only the first is what the guard is
for. A ticker split gives both halves the same 25 years and the same seven
drawdowns. Membership is published in the pre-registration.

Full rule, disclosures and limits:
`docs/superpowers/results/2026-08-05-v54-strictest-gate-ladder.md`.
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

DIRECTIONS = ("bullish", "bearish")


def _stats(trades):
    st = pool(trades)
    st["max_dd_pct"] = pooled_max_dd_pct(trades)
    st["wilson_lb"] = wilson_lower_bound(st["wins"], st["n_eval"])
    return st


def _ok(st):
    return (st["n_eval"] >= MIN_N and st["expectancy_r"] is not None
            and st["expectancy_r"] > 0)


def _row(label, st, width=30):
    wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
    lb = f"{st['wilson_lb']:.1f}" if st["wilson_lb"] is not None else "n/a"
    er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
    flag = "" if st["n_eval"] >= MIN_N else "  INSUFFICIENT"
    return f"{label:{width}s} {st['n_eval']:6d} {wr:>6s} {lb:>6s} {er:>8s}{flag}"


def _admits(mask, direction, horizon):
    """Does `mask` (None = ungated) admit this cell? Mirrors entry_filters."""
    if not mask:
        return True
    dirs = mask.get("directions")
    hzs = mask.get("horizons")
    if dirs and direction not in dirs:
        return False
    if hzs and horizon not in hzs:
        return False
    return True


def _mask_n(mask, cells):
    """Whole-universe TRAIN signal count a mask would admit."""
    return sum(len(cells[(d, hk)]) for d in DIRECTIONS for hk in HORIZONS
               if _admits(mask, d, hk))


def derive(strat, fit_cells, conf_cells, all_cells):
    """The pre-registered strictest-first ladder. Returns a verdict dict.

    Applied mechanically -- no judgement between running the grid and reading
    the verdict.
    """
    current = STRATEGY_GATES.get(strat)
    out = {"current_mask": current}

    # -- A: admissible cells, selected on FIT only, and only among the cells
    # the CURRENT mask already admits -- which is what makes the candidate a
    # subset of what ships, hence tightening-or-keeping by construction.
    admissible = [(d, hk) for d in DIRECTIONS for hk in HORIZONS
                  if _admits(current, d, hk) and _ok(_stats(fit_cells[(d, hk)]))]
    out["admissible_cells_fit"] = [f"{d}/{hk}" for d, hk in admissible]
    if not admissible:
        out.update(verdict="KEEP (no admissible cell)", adopted=False,
                   proposed_mask=None,
                   why="no (direction, horizon) cell clears ExpR > 0 at "
                       f"N >= {MIN_N} on FIT -- reported for a human decision "
                       "about dropping the strategy, not auto-disabled")
        return out

    # -- B: tightest expressible mask (cross-product closure) --------------
    dirs = tuple(d for d in DIRECTIONS if any(c[0] == d for c in admissible))
    hzs = tuple(hk for hk in HORIZONS if any(c[1] == hk for c in admissible))
    candidate = {"directions": dirs}
    # A mask listing every horizon is the same as listing none; keep it
    # canonical so the diff against the shipped dict is readable.
    if len(hzs) < len(HORIZONS):
        candidate["horizons"] = hzs
    out["candidate_mask"] = candidate

    fit_pool = _stats([t for d in DIRECTIONS for hk in HORIZONS
                       if _admits(candidate, d, hk)
                       for t in fit_cells[(d, hk)]])
    out["candidate_fit"] = {k: v for k, v in fit_pool.items()}
    if not _ok(fit_pool):
        out.update(verdict="KEEP (closure fails on FIT)", adopted=False,
                   proposed_mask=None,
                   why=f"closure pooled to ExpR={fit_pool['expectancy_r']} at "
                       f"N={fit_pool['n_eval']} on FIT -- the cross-product "
                       "re-admits cells that were not admissible")
        return out

    # -- C: non-loosening, on the whole universe ---------------------------
    n_cur = _mask_n(current, all_cells)
    n_cand = _mask_n(candidate, all_cells)
    out["signal_count"] = {"current": n_cur, "candidate": n_cand}
    if n_cand > n_cur:
        # Unreachable while step A draws only from currently-admitted cells;
        # kept as a defensive assertion so a later edit to A cannot silently
        # turn this ladder into a loosening one.
        out.update(verdict="KEEP (would loosen -- BUG)", adopted=False,
                   proposed_mask=None,
                   why=f"candidate admits {n_cand} TRAIN signals vs the "
                       f"current mask's {n_cur}; step A should have made this "
                       "impossible -- investigate before trusting any verdict")
        return out

    # -- D: held-out confirmation ------------------------------------------
    conf_pool = _stats([t for d in DIRECTIONS for hk in HORIZONS
                        if _admits(candidate, d, hk)
                        for t in conf_cells[(d, hk)]])
    out["candidate_confirm"] = {k: v for k, v in conf_pool.items()}
    if not _ok(conf_pool):
        out.update(verdict="KEEP (fails CONFIRM)", adopted=False,
                   proposed_mask=None,
                   why=f"CONFIRM ExpR={conf_pool['expectancy_r']} at "
                       f"N={conf_pool['n_eval']} -- the FIT selection did not "
                       "generalise past the tickers it was chosen on")
        return out

    out.update(verdict="ADOPT", adopted=True, proposed_mask=candidate,
               why=f"FIT ExpR={fit_pool['expectancy_r']:+.3f} "
                   f"(N={fit_pool['n_eval']}), CONFIRM "
                   f"ExpR={conf_pool['expectancy_r']:+.3f} "
                   f"(N={conf_pool['n_eval']}), signals {n_cand} <= {n_cur}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--strategies", default=None,
                    help="comma-separated; default is all 11")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--exit-model", dest="exit_model", default="v2")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true", default=True)
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false")
    ap.add_argument("--tp2", default="levels", choices=["none", "levels"])
    ap.add_argument("--frictions", default="on", choices=["on", "off"])
    args = ap.parse_args()

    strategies = ([s.strip() for s in args.strategies.split(",")]
                  if args.strategies else list(ALL_STRATEGIES))

    frames, excluded = {}, {"illiquid": [], "bad_data": [], "no_data": []}
    for t in _tickers_for_run(None):
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

    # The published split: screened tickers sorted, even -> FIT, odd -> CONFIRM.
    # Deterministic and fixed in the pre-registration so it cannot be re-cut.
    ordered = sorted(frames)
    if args.limit:
        ordered = ordered[:args.limit]
    fit_t = {t for i, t in enumerate(ordered) if i % 2 == 0}
    conf_t = {t for i, t in enumerate(ordered) if i % 2 == 1}

    entry_filters.STRATEGY_GATES = {}
    print("STRATEGY_GATES DISABLED -- a masked strategy cannot show you the "
          "cells it masks, and all 20 are what the rule reads.", flush=True)
    print(f"\nV54 strictest-gate ladder | {len(ordered)} tickers "
          f"(FIT {len(fit_t)} / CONFIRM {len(conf_t)}) x {len(HORIZONS)} "
          f"horizons x {len(strategies)} strategies | exit={args.exit_model} "
          f"scale_out={args.scale_out} tp2={args.tp2} "
          f"frictions={args.frictions}", flush=True)
    print(f"FIT:     {' '.join(sorted(fit_t))}", flush=True)
    print(f"CONFIRM: {' '.join(sorted(conf_t))}", flush=True)

    fit = defaultdict(list)       # (strat, dir, hz)
    conf = defaultdict(list)
    allc = defaultdict(list)
    regime = defaultdict(list)    # (strat, dir, regime)

    for ti, ticker in enumerate(ordered, 1):
        df = frames[ticker]
        half = fit if ticker in fit_t else conf
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
                    half[(strat, tr.direction, hk)].append(tr)
                    allc[(strat, tr.direction, hk)].append(tr)
                    n += 1
                for name, d_from, d_to in REGIMES:
                    for tr in window_trades(s, d_from, d_to):
                        regime[(strat, tr.direction, name)].append(tr)
        tag = "FIT" if ticker in fit_t else "CONFIRM"
        print(f"[{ti}/{len(ordered)}] {ticker} [{tag}]: +{n} TRAIN trades",
              flush=True)

    out = {"config": {"exit_model": args.exit_model, "scale_out": args.scale_out,
                      "tp2": args.tp2, "frictions": args.frictions,
                      "gates": "off", "min_n": MIN_N, "train": list(TRAIN)},
           "split": {"fit": sorted(fit_t), "confirm": sorted(conf_t)},
           "excluded": excluded, "strategies": {}}

    hdr = f"{'':30s} {'N':>6s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>8s}"
    for strat in strategies:
        print(f"\n{'=' * 72}\n== {strat} ==", flush=True)
        print(hdr, flush=True)
        fc = {(d, hk): fit[(strat, d, hk)] for d in DIRECTIONS for hk in HORIZONS}
        cc = {(d, hk): conf[(strat, d, hk)] for d in DIRECTIONS for hk in HORIZONS}
        ac = {(d, hk): allc[(strat, d, hk)] for d in DIRECTIONS for hk in HORIZONS}

        cells = {}
        for d in DIRECTIONS:
            for hk in HORIZONS:
                stf = _stats(fc[(d, hk)])
                if stf["n_eval"]:
                    print(_row(f"  FIT {d}/{hk}", stf), flush=True)
                cells[f"{d}/{hk}"] = {
                    "fit": stf, "confirm": _stats(cc[(d, hk)]),
                    "all": _stats(ac[(d, hk)])}

        v = derive(strat, fc, cc, ac)
        print(f"\n  admissible on FIT: {v['admissible_cells_fit'] or 'NONE'}",
              flush=True)
        print(f"  current : {v['current_mask']}", flush=True)
        print(f"  proposed: {v.get('proposed_mask')}", flush=True)
        print(f"  VERDICT {v['verdict']}: {v['why']}", flush=True)

        dirs = ((v["proposed_mask"] or {}).get("directions")
                if v["adopted"] else None) or DIRECTIONS
        regs = {}
        for name, _f, _t in REGIMES:
            st = _stats([t for d in dirs for t in regime[(strat, d, name)]])
            regs[name] = st
            print(_row(f"    [regime] {name}", st), flush=True)
        for name, _f, _t in REGIMES:
            for d in DIRECTIONS:
                regs[f"{d}/{name}"] = _stats(regime[(strat, d, name)])

        v["cells"] = cells
        v["selected_mask_by_regime"] = regs
        out["strategies"][strat] = v

    print(f"\n{'=' * 72}\n== verdicts ==", flush=True)
    for strat in strategies:
        v = out["strategies"][strat]
        print(f"  {strat:22s} {v['verdict']:28s} "
              f"{v['current_mask']} -> {v.get('proposed_mask')}", flush=True)
    adopted = [s for s in strategies if out["strategies"][s]["adopted"]]
    print(f"\nADOPTED: {adopted or 'none'}", flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
