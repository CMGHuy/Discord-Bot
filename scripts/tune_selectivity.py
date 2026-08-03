#!/usr/bin/env python3
"""TRAIN-only selectivity search -- plan v8 Task V52 Step 1.

V17 established that sizing is exhausted: the full 1188-config sizing grid tops
out at 49.6% win rate against a 43.4% no-skill floor. The remaining lever is
WHICH TRADES ARE TAKEN AT ALL, which is what this grids.

Selection rule (PRE-REGISTERED, plan v8 V6 Step 3b, quoted verbatim in
docs/superpowers/results/2026-08-03-v52-selectivity-ladder.md before this ran):

    OBJECTIVE   maximise expectancy_r
    SUBJECT TO  win_rate >= 80%          <- hard constraint
                every win >= 2.5%
                every loss <= 1.75%
                scratches + timeouts <= 50% of closed trades
    NO CEILING  no maximum on profit -- winners run on the trail, no fixed tp2
    FLOOR       reject any config with win_rate < 80% regardless of expectancy

Climbed in three gated stages on the WILSON LOWER BOUND over the INDEPENDENT
sample: Stage 1 LB>60, Stage 2 LB>70, Stage 3 LB>80. Never on the point
estimate -- V6 Step 5's math is that proving >80% needs N>=29 at 95% observed,
64 at 90%, 256 at 85%.

Why one backtest yields thousands of cells: every selectivity axis is evaluated
at the SIGNAL BAR (the G91 gatekeeper annotation) and so is independent of the
exit. One run per (strategy, cut-flag combo) therefore produces the whole
score x tier x confluence x regime lattice as in-memory slices. Only V51's
three cut-loss flags change the exit, so only those need separate runs: 2^3 = 8.

Never point this at the validation window. `gate_eval=True` makes
backtest.assert_train_only raise on any frame reaching past 2023-12-31, so this
cannot silently score 2024-2025 even if asked to.
"""
import argparse
import itertools
import json
import statistics
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
from swingbot.core.backtest_windows import TRAIN
from swingbot.core.edge import regime2
from swingbot.core.gate.wr_math import wilson_lower_bound
from swingbot.core.strategy_types import HORIZONS

ALL_STRATEGIES = [
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest",
    "RSI Divergence", "Volume Profile",
]

# V51 Step 3's three predicates, crossed as a full 2^3. Names are the config
# Fields; all three ship default-off, so combo (False, False, False) is the
# pre-V51 exit path byte-identical and acts as this grid's control.
CUT_FLAGS = ("EARLY_CUT_THESIS_ENABLED", "EARLY_CUT_TIME_ENABLED",
             "EARLY_CUT_MAE_ENABLED")

SCORE_CUTS = list(range(0, 100, 10))
TIERS = ("A+", "A", "B", "C")
CONFLUENCE_CUTS = list(range(0, 7))

REUSE_FLAG_RATIO = 1.5   # the threshold V49 pinned, reused unchanged
MIN_CELL_N = 20          # below this a cell is reported but never adopted


def _num(x):
    """Coerce numpy scalars to plain Python. `runner_holding_days` arrives as
    a numpy int64 (it is a difference of positional indices), which json
    refuses -- and it refuses at write time, after the whole sweep has run."""
    if x is None:
        return None
    return x.item() if hasattr(x, "item") else x


def _pct(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return round(_num(s[k]), 3)


def score_cell(trades) -> dict:
    """Everything V52 Step 1 requires per cell, including the two things a
    blended expectancy hides: the runner-leg R distribution and the realised
    loss distribution against the 1.75% cap."""
    closed = list(trades)
    ev = [t for t in closed if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    excl = sum(1 for t in closed if t.outcome in ("scratch", "timeout"))
    n_eval = len(ev)
    if n_eval == 0:
        return {"n_eval": 0, "n_independent": 0, "win_rate": None,
                "wilson_lb": 0.0, "expectancy_r": None, "excluded_share": 0.0,
                "horizon_overcount": 1.0}

    # V49 Step 3, applied to the cohort actually being scored -- a selective
    # cohort is MORE exposed to horizon reuse, not less, so this is corrected
    # per cell rather than inherited from the strategy-level ratio.
    sigs = {(t.entry_date, t.entry, t.direction) for t in ev}
    ratio = n_eval / len(sigs) if sigs else 1.0
    n_indep = round(n_eval / ratio) if ratio >= REUSE_FLAG_RATIO else n_eval

    wr = wins / n_eval * 100
    lb = wilson_lower_bound(round(wr / 100.0 * n_indep), n_indep) * 100

    # Realised loss against the cap. return_pct is signed and already the
    # fraction-weighted realised return, so a loss is simply a negative one.
    losses = [-t.return_pct for t in closed
              if t.outcome == "loss" and t.return_pct is not None]
    # The runner leg on its own (V51 Step 2: break-even WR swings 41.2->58.3
    # on this alone, which straddles the 43.4% no-skill floor).
    runner_rs = [t.runner_r for t in closed if t.runner_r is not None]
    runner_holds = [t.runner_holding_days for t in closed
                    if t.runner_holding_days is not None]
    rs = [t.r_multiple for t in closed if t.r_multiple is not None]

    return {
        "n_eval": n_eval,
        "n_independent": n_indep,
        "horizon_overcount": round(ratio, 2),
        "win_rate": round(_num(wr), 2),
        "wilson_lb": round(_num(lb), 2),
        "expectancy_r": round(_num(sum(rs) / len(rs)), 4) if rs else None,
        "excluded_share": round(excl / len(closed), 4) if closed else 0.0,
        "loss_pct_median": _pct(losses, 0.5),
        "loss_pct_p95": _pct(losses, 0.95),
        "loss_pct_max": round(_num(max(losses)), 3) if losses else None,
        "loss_over_cap_share": (
            round(sum(1 for x in losses if x > config.MAX_LOSS_PCT + 1e-9)
                  / len(losses), 4) if losses else None),
        "n_runners": len(runner_rs),
        "runner_r_median": _pct(runner_rs, 0.5),
        "runner_r_mean": round(_num(statistics.fmean(runner_rs)), 4) if runner_rs else None,
        "runner_r_p25": _pct(runner_rs, 0.25),
        "runner_r_p75": _pct(runner_rs, 0.75),
        "runner_hold_median": _pct(runner_holds, 0.5),
    }


def collect(strategy, dfs, regimes) -> list:
    """One full sweep for the CURRENT cut-flag settings. Returns every trade
    annotated well enough to slice on afterwards."""
    out = []
    for hk in HORIZONS:
        for ticker, df in dfs.items():
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model="v2", scale_out=True,
                                    tp2_mode="none", gate_eval=True)
            except Exception:
                continue
            for t in s.trades:
                # Regime alignment: the SPY regime label at the entry bar vs
                # the trade's own direction. Computed here rather than in the
                # engine -- it is a property of the market, not of the plan.
                lab = regimes.get(t.entry_date)
                t._regime = lab
                t._aligned = (None if lab is None else
                              (lab.startswith("bull")) == (t.direction == "bullish"))
                out.append(t)
    return out


def cells(trades) -> dict:
    """Every pre-registered slice of one trade set. Keys are stable strings so
    the aggregator never has to re-derive the lattice."""
    out = {}
    for cut in SCORE_CUTS:
        out[f"score>={cut}"] = [t for t in trades
                                if t.gate_score is not None and t.gate_score >= cut]
    for tier in TIERS:
        out[f"tier={tier}"] = [t for t in trades if t.gate_tier == tier]
    # Tier is a ladder, so "at least" is the cut production would actually make.
    order = {"A+": 0, "A": 1, "B": 2, "C": 3}
    for tier in TIERS:
        out[f"tier<={tier}"] = [t for t in trades if t.gate_tier in order
                                and order[t.gate_tier] <= order[tier]]
    for c in CONFLUENCE_CUTS:
        out[f"confluence>={c}"] = [t for t in trades
                                   if t.confluence_count is not None
                                   and t.confluence_count >= c]
    out["regime=aligned"] = [t for t in trades if t._aligned is True]
    out["regime=opposed"] = [t for t in trades if t._aligned is False]
    out["all"] = list(trades)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--max-tickers", type=int, default=None)
    args = ap.parse_args()

    tickers = load_watchlist()
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
    dfs = {}
    for t in tickers:
        d = load_cached(t)
        if d is None:
            continue
        # Sliced to TRAIN before the engine sees it: gate_eval asserts on any
        # frame reaching past 2023-12-31, which is the guard, not a nuisance.
        w = d[(d.index >= TRAIN[0]) & (d.index <= TRAIN[1])]
        if len(w) >= 200:
            dfs[t] = w
    print(f"{len(dfs)} tickers loaded | strategy={args.strategy} "
          f"| exit=v2 scale_out=True tp2=none | cap={config.MAX_LOSS_PCT}%",
          flush=True)

    spy = load_cached("SPY")
    regimes = {}
    if spy is not None:
        w = spy[(spy.index >= TRAIN[0]) & (spy.index <= TRAIN[1])]
        ser = regime2.regime_series(w)
        regimes = {str(ix.date()): v for ix, v in ser.items()}
    print(f"regime labels for {len(regimes)} SPY bars", flush=True)

    combos = list(itertools.product([False, True], repeat=len(CUT_FLAGS)))
    print(f"TRAIN {TRAIN[0]}..{TRAIN[1]} | {len(combos)} cut-flag combos "
          f"x {len(SCORE_CUTS) + 2 * len(TIERS) + len(CONFLUENCE_CUTS) + 3} cells",
          flush=True)
    print("rule: max ExpR s.t. WR>=80%; ladder gates on Wilson LB over "
          "INDEPENDENT N (60 -> 70 -> 80). Plan v8 V6 Step 3b.", flush=True)

    saved = {f: getattr(config, f) for f in CUT_FLAGS}
    rows = []
    try:
        for ci, combo in enumerate(combos, 1):
            for flag, val in zip(CUT_FLAGS, combo):
                setattr(config, flag, val)
            t0 = time.time()
            trades = collect(args.strategy, dfs, regimes)
            label = ",".join(f.replace("EARLY_CUT_", "").replace("_ENABLED", "").lower()
                             for f, v in zip(CUT_FLAGS, combo) if v) or "none"
            for cell_name, sub in cells(trades).items():
                s = score_cell(sub)
                s["cuts"] = label
                s["cell"] = cell_name
                rows.append(s)
            best = max((r for r in rows if r["cuts"] == label
                        and r["n_independent"] >= MIN_CELL_N),
                       key=lambda r: r["wilson_lb"], default=None)
            print(f"[{ci}/{len(combos)}] cuts={label:<28} "
                  f"trades={len(trades):<6} best LB="
                  f"{best['wilson_lb'] if best else float('nan'):5.1f} "
                  f"({best['cell'] if best else 'n/a'}) ({time.time() - t0:.0f}s)",
                  flush=True)
    finally:
        for f, v in saved.items():
            setattr(config, f, v)

    payload = {
        "strategy": args.strategy,
        "train_window": list(TRAIN),
        "exit_model": "v2", "scale_out": True, "tp2_mode": "none",
        "max_loss_pct": config.MAX_LOSS_PCT,
        "min_target_pct": config.MIN_TARGET_PCT,
        "n_tickers": len(dfs),
        "cut_flags": list(CUT_FLAGS),
        "min_cell_n": MIN_CELL_N,
        "rows": rows,
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=1))
        print(f"Wrote results to {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
