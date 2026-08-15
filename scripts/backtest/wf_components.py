"""Run every registerable Phase-E2 component through the anchored walk-forward gate (Task E33).

One component at a time, against the friction-adjusted baseline. The gate
is PRE-REGISTERED (Global Constraints): pooled test expectancy_r improves
in >= 2 of 3 folds, no fold degrades baseline by > 0.05R, N >= 30 per
fold. Components that fail are documented and DROPPED -- no second grid
on the same hypothesis.

Run: python scripts/wf_components.py [--component NAME] [--universe watchlist]
                                     [--out docs/superpowers/results/...md]

WHY THIS SCRIPT AND NOT `wf_run.py` PER COMPONENT: run_backtest_daterange
re-runs the whole backtest for every window and then filters, so driving
3 folds through it does the same work 3 times. Here each (symbol,
strategy, horizon) is backtested ONCE per leg over the full span and the
resulting trades are sliced into folds by entry_date -- identical numbers,
a third of the work. At watchlist scale that is the difference between
hours and most of a day.

REGISTERED vs INERT: only components the backtest can actually observe
are run. Several Edge flags only affect the LIVE path (plan builder,
plan manager, scan loop) and are bit-identical here by construction --
running them would score a meaningless 0.0000 delta and burn their
one-shot pre-registration. They are listed in INERT_COMPONENTS with the
wiring each would need, and are NOT run.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest  # noqa: E402
from swingbot.core.backtest_wf import (ANCHORED_FOLDS, GATE_MAX_DEGRADATION_R,  # noqa: E402
                                       GATE_MIN_IMPROVING_FOLDS,
                                       GATE_MIN_N_PER_FOLD, _apply_overrides,
                                       _frame_for, gate)
from swingbot.core.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.universe import liquidity_ok, universe_symbols  # noqa: E402
from swingbot.core.watchlist import load_watchlist  # noqa: E402

# Components the backtest can actually observe. Verified empirically
# before registering (flip the flag, same windows, compare expectancy):
# under tp2_mode="levels" AVWAP moves the number; under "none" nothing does.
REGISTERED_COMPONENTS = {
    "AVWAP_LEVELS_ENABLED": True,
    "VOLUME_PROFILE_NODES_ENABLED": True,
    # P1 level lifecycle. Observability verified before registering (3 symbols
    # x 2 strategies x 10 horizons): the stop leg moves expectancy in 2 of 3
    # folds, so the harness can see it. Its sibling
    # LEVEL_LIFECYCLE_TARGETS_ENABLED did NOT survive that check -- see
    # INERT_COMPONENTS.
    "LEVEL_LIFECYCLE_STOPS_ENABLED": True,
}

# Flags that CANNOT be measured by this harness -- documented, not run.
INERT_COMPONENTS = {
    "DATA_DRIVEN_STOPS_ENABLED":
        "E31/E32 reach plan_engine.build_strategy_plan only; the backtest "
        "sizes through backtest._trade_plan_at, which takes no stop_mult/"
        "tp2_r. Needs those threaded through run_backtest first.",
    "REGIME_GATES_ENABLED":
        "The wiring objection is FIXED (P0: market_context.attach/get now "
        "supplies entries_for with a ctx_regime series in both the backtest "
        "and the live scan), but the gate is still inert for a second, "
        "stronger reason: its pre-registered TRAIN shot ran on 2026-08-08 and "
        "denied ZERO of 44 (strategy, regime) cells, so REGIME_ALLOW is empty "
        "by evidence rather than by omission. Re-running this without new "
        "bear-regime data would only re-measure a table that is empty on "
        "purpose -- see design doc section 5.5.",
    "LEVEL_LIFECYCLE_TARGETS_ENABLED":
        "Structurally cannot fire, measured 2026-08-08 over 12 symbols x 11 "
        "strategies x 10 horizons: of 428 entry bars, 248 had a gatekeeper in "
        "the path and 180 had none -- and the pull-in was rejected by RR_FLOOR "
        "in 248 of 248. Pulling TP1 just inside a blocker yields median 0.063 "
        "R:R against the frozen 0.30 floor, a 5x gap that no choice of blocker "
        "closes (farthest clears in 0.4% of bars, king in 0%). Blockers sit "
        "adjacent to entry, so the 'realistic' target is too close to be a "
        "trade. Registering it would score exactly 0.0000 -- which is what a "
        "slice run did score. Fix the concept or drop it; do NOT lower "
        "RR_FLOOR to make it fire.",
    "PYRAMIDING_ENABLED":
        "E38 lives in the live plan manager; plan_engine.simulate_exit has "
        "no pyramiding concept, so the backtest cannot observe it.",
    "EARNINGS_BLACKOUT_DAYS":
        "E18's gate was never wired into the scan or backtest path.",
}

FULL_START, FULL_END = ANCHORED_FOLDS[0][0], ANCHORED_FOLDS[-1][3]


def _symbols(universe: str) -> list:
    syms = universe_symbols(universe) or [] if universe != "watchlist" else load_watchlist()
    return sorted(dict.fromkeys(syms))


def _collect_leg(symbols, strategies, horizons, overrides, log) -> list:
    """Every (entry_date, r_multiple) this configuration produces over the
    whole fold span. Backtested once per (symbol, strategy, horizon)."""
    old = _apply_overrides(overrides or {})
    rows = []
    try:
        for n, sym in enumerate(symbols, 1):
            df = _frame_for(sym)
            if df is None or not liquidity_ok(df):
                log(f"    skip {sym} (no frame / illiquid)")
                continue
            for strat in strategies:
                for hk in horizons:
                    try:
                        s = run_backtest(sym, df, strat, hk, exit_model="v2",
                                         scale_out=True, tp2_mode="levels",
                                         frictions=True)
                    except Exception as exc:
                        log(f"    !! {sym}/{strat}/{hk}: {exc}")
                        continue
                    for t in s.trades:
                        if t.r_multiple is not None:
                            rows.append((t.entry_date, float(t.r_multiple)))
            if n % 10 == 0:
                log(f"    ...{n}/{len(symbols)} symbols, {len(rows)} trades so far")
    finally:
        _apply_overrides(old)
    return rows


def _fold_stats(rows, test_start, test_end) -> dict:
    rs = [r for d, r in rows if test_start <= d <= test_end]
    return {"expectancy_r": float(np.mean(rs)) if rs else None, "n": len(rs)}


def _result_for(base_rows, comp_rows) -> dict:
    fold_rows = []
    for _, _, test_start, test_end in ANCHORED_FOLDS:
        base = _fold_stats(base_rows, test_start, test_end)
        comp = _fold_stats(comp_rows, test_start, test_end)
        delta = None
        if base["expectancy_r"] is not None and comp["expectancy_r"] is not None:
            delta = comp["expectancy_r"] - base["expectancy_r"]
        fold_rows.append({"test_years": test_start[:4], "baseline": base,
                          "component": comp, "delta_expectancy_r": delta,
                          "n": min(base["n"], comp["n"])})
    deltas = [f["delta_expectancy_r"] for f in fold_rows if f["delta_expectancy_r"] is not None]
    return {"folds": fold_rows,
            "pooled_delta_expectancy_r": sum(deltas) / len(deltas) if deltas else None}


def _fmt(v, spec="8.4f"):
    return "     n/a" if v is None else format(v, spec)


def _render(results, universe, symbols, strategies, horizons, elapsed) -> str:
    out = [
        "# Edge Engine v4 — Task E33: Phase-E2 component fold decisions",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        f"in {elapsed/60:.1f} min.",
        "",
        "## Pre-registered selection rule (quoted verbatim, fixed before data contact)",
        "",
        "> anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023. "
        "A component passes if pooled test `expectancy_r` improves vs baseline in "
        "**≥ 2 of 3 folds**, no fold degrades baseline expectancy by more than 0.05R, "
        "and N ≥ 30 per fold. Components that fail are documented and dropped — "
        "no second grid on the same hypothesis.",
        "",
        f"Constants as run: improving folds ≥ {GATE_MIN_IMPROVING_FOLDS}, "
        f"max degradation {GATE_MAX_DEGRADATION_R}R, min N {GATE_MIN_N_PER_FOLD}.",
        "",
        "## Setup",
        "",
        f"- Universe: `{universe}` — {len(symbols)} symbols, "
        f"{len(strategies)} strategies × {len(horizons)} horizons",
        "- Exit model: v2 + scale-out, `tp2_mode=levels`, frictions ON "
        "(matches the E22 friction-adjusted baseline tooling's own defaults)",
        "- OHLCV: `data/backtest_cache/` (same cache the E22 baseline was measured on)",
        "- Each (symbol, strategy, horizon) backtested once per leg; folds sliced by entry_date",
        "",
        "## Results",
        "",
    ]
    for name, res in results.items():
        verdict = gate(res)
        out += [f"### {name} — **{verdict}**", "",
                "| fold | N | baseline expR | component expR | delta |",
                "|---|---:|---:|---:|---:|"]
        for f in res["folds"]:
            out.append(f"| {f['test_years']} | {f['n']} | "
                       f"{_fmt(f['baseline']['expectancy_r'])} | "
                       f"{_fmt(f['component']['expectancy_r'])} | "
                       f"{_fmt(f['delta_expectancy_r'], '+8.4f')} |")
        pooled = res["pooled_delta_expectancy_r"]
        out += ["", f"Pooled delta expectancy_r: "
                    f"{'n/a' if pooled is None else format(pooled, '+.4f')}", ""]

    out += ["## Not run — the harness cannot observe these", "",
            "Registering these would score a meaningless 0.0000 delta and burn "
            "their one-shot pre-registration, so they are deliberately NOT run.", ""]
    for name, why in INERT_COMPONENTS.items():
        out.append(f"- **{name}** — {why}")
    out += ["", "## Observations", "",
            "_Written after reading the numbers above; failures are recorded, not fixed._", ""]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--component", action="append", default=None)
    ap.add_argument("--universe", default="watchlist")
    ap.add_argument("--strategy", action="append", default=None)
    ap.add_argument("--horizon", action="append", default=None)
    ap.add_argument("--limit-symbols", type=int, default=None)
    ap.add_argument("--out", default="docs/superpowers/results/2026-07-26-edge-folds.md")
    args = ap.parse_args()

    def log(msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    symbols = _symbols(args.universe)
    if args.limit_symbols:
        symbols = symbols[:args.limit_symbols]
    strategies = args.strategy or list(ALL_STRATEGIES)
    horizons = args.horizon or list(HORIZONS)
    components = args.component or list(REGISTERED_COMPONENTS)

    started = time.time()
    log(f"universe={args.universe} symbols={len(symbols)} "
        f"strategies={len(strategies)} horizons={len(horizons)}")
    log(f"components: {components}")
    log("collecting BASELINE leg (no overrides)")
    base_rows = _collect_leg(symbols, strategies, horizons, {}, log)
    log(f"baseline: {len(base_rows)} trades in {(time.time()-started)/60:.1f} min")

    results = {}
    for name in components:
        value = REGISTERED_COMPONENTS.get(name, True)
        t0 = time.time()
        log(f"collecting COMPONENT leg: {name}={value}")
        comp_rows = _collect_leg(symbols, strategies, horizons, {name: value}, log)
        results[name] = _result_for(base_rows, comp_rows)
        log(f"{name}: {len(comp_rows)} trades, gate={gate(results[name])} "
            f"({(time.time()-t0)/60:.1f} min)")

    elapsed = time.time() - started
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(_render(results, args.universe, symbols, strategies, horizons, elapsed))
    with open(args.out.replace(".md", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"universe": args.universe, "symbols": symbols,
                   "strategies": strategies, "horizons": horizons,
                   "elapsed_sec": elapsed, "inert": INERT_COMPONENTS,
                   "results": {k: {"result": v, "gate": gate(v)}
                               for k, v in results.items()}}, fh, indent=2)
    log(f"DONE in {elapsed/60:.1f} min -> {args.out}")
    for name, res in results.items():
        log(f"  {name}: {gate(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
