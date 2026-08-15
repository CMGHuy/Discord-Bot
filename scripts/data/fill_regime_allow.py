#!/usr/bin/env python3
"""Fill strategy_types.REGIME_ALLOW from TRAIN evidence (P2a).

    python scripts/fill_regime_allow.py                       # watchlist
    python scripts/fill_regime_allow.py --universe sp500
    python scripts/fill_regime_allow.py --json out.json

THE PRE-REGISTERED SELECTION RULE
---------------------------------
Fixed in docs/superpowers/specs/2026-08-08-market-context-and-level-lifecycle-
design-v17.md BEFORE any fold was run, and encoded here so it cannot quietly be
re-read later:

    Deny (strategy, regime) only if ALL THREE hold on TRAIN:
      1. N_cell >= 30
      2. expectancy_r < 0
      3. the negative sign holds in >= 3 of the 4 sub-folds (2020..2023)
    Otherwise the cell stays ALLOWED.

    A cell whose N falls below 30 WITHIN a sub-fold counts as "sign does not
    hold" for that fold rather than dropping out of the denominator --
    otherwise a cell with one populated year could clear "3 of 4" on a single
    year's evidence.

Default-allow is deliberate. Every denial removes trades, so a gate pays only
if the effect is real; if it is noise we have cut sample for nothing.

SELECTION IS ON EXPECTANCY, NOT WIN RATE. Win rate is trivially gameable by
gating -- deny enough cells and it rises while total expectancy falls, because
winners are cut alongside losers. Win rate is reported, never selected on. A
config that raises win rate while lowering expectancy is a FAIL.

Regimes are read from market_context's ctx_regime, i.e. the same column the
live gate reads, so the evidence and the mechanism cannot drift apart. The
gate itself must be OFF while measuring -- we need ungated per-regime
behaviour to decide what to deny -- and this script asserts that.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
from swingbot import config
from swingbot.core import market_context
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.edge.regime2 import REGIMES
from swingbot.core.strategy_types import HORIZONS
from swingbot.core.universe import data_quality_issues, liquidity_reason, universe_symbols

TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"
SUB_FOLDS = ("2020", "2021", "2022", "2023")

MIN_N_CELL = 30           # rule 1
MIN_N_SUBFOLD = 30        # rule 3's within-fold floor
MIN_FOLD_AGREEMENT = 3    # rule 3


def _expectancy(trades) -> float | None:
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    return float(np.mean(rs)) if rs else None


def _win_rate(trades) -> float | None:
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    if not ev:
        return None
    return sum(1 for t in ev if t.outcome == "win") / len(ev) * 100


def collect(tickers, strategies, spy_df, *, quiet=False):
    """{(strategy, regime): [trades]} plus the same split by sub-fold year."""
    pooled = defaultdict(list)
    by_fold = defaultdict(lambda: defaultdict(list))
    regime_of = {}

    total = len(tickers)
    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        if liquidity_reason(df) is not None or data_quality_issues(df, ticker):
            if not quiet:
                print(f"[{ti}/{total}] {ticker}: excluded (liquidity/data quality)", flush=True)
            continue

        df = market_context.attach(df, spy_df=spy_df)
        # Entry-date -> regime, straight off the column the live gate reads.
        regime_of = {d.date().isoformat(): r for d, r in df["ctx_regime"].items()}

        n_trades = 0
        for strategy in strategies:
            for hk in HORIZONS:
                try:
                    summary = run_backtest(ticker, df, strategy, hk, one_at_a_time=True)
                except Exception:
                    continue
                for tr in summary.trades:
                    if not (TRAIN_FROM <= tr.entry_date <= TRAIN_TO):
                        continue
                    regime = regime_of.get(tr.entry_date)
                    if regime is None or (isinstance(regime, float) and np.isnan(regime)):
                        continue
                    pooled[(strategy, regime)].append(tr)
                    by_fold[(strategy, regime)][tr.entry_date[:4]].append(tr)
                    n_trades += 1

        # One flushed line per ticker: this run is long enough that silence
        # would make a stall indistinguishable from progress.
        if not quiet:
            print(f"[{ti}/{total}] {ticker}: {n_trades} TRAIN trades", flush=True)

    return pooled, by_fold


def decide(pooled, by_fold, strategies):
    """Apply the pre-registered rule. Returns (allow_table, rows)."""
    rows = []
    denied = defaultdict(set)

    for strategy in strategies:
        for regime in REGIMES:
            trades = pooled.get((strategy, regime), [])
            n = len(trades)
            exp = _expectancy(trades)
            wr = _win_rate(trades)

            folds_negative = 0
            fold_detail = []
            for year in SUB_FOLDS:
                ft = by_fold.get((strategy, regime), {}).get(year, [])
                fexp = _expectancy(ft)
                # Below the within-fold floor counts as "sign does not hold".
                holds = len(ft) >= MIN_N_SUBFOLD and fexp is not None and fexp < 0
                folds_negative += bool(holds)
                fold_detail.append(f"{year}:{len(ft)}{'-' if holds else '.'}")

            rule_n = n >= MIN_N_CELL
            rule_exp = exp is not None and exp < 0
            rule_folds = folds_negative >= MIN_FOLD_AGREEMENT
            deny = rule_n and rule_exp and rule_folds
            if deny:
                denied[strategy].add(regime)

            rows.append({
                "strategy": strategy, "regime": regime, "n": n,
                "expectancy_r": exp, "win_rate": wr,
                "folds_negative": folds_negative, "fold_detail": " ".join(fold_detail),
                "rule_n": rule_n, "rule_exp": rule_exp, "rule_folds": rule_folds,
                "deny": deny,
            })

    # REGIME_ALLOW lists what IS allowed. A strategy with no denials is left
    # out of the table entirely -- apply_regime_gate treats a missing key as
    # "unrestricted", which is what we want; an empty tuple would mean
    # "nothing allowed" and silence the strategy completely.
    allow = {}
    for strategy in strategies:
        if denied[strategy]:
            allow[strategy] = tuple(r for r in REGIMES if r not in denied[strategy])
    return allow, rows


def render(rows, allow, tickers, strategies):
    out = []
    out.append(f"== REGIME_ALLOW evidence | TRAIN {TRAIN_FROM}..{TRAIN_TO} | "
               f"{len(tickers)} tickers x {len(strategies)} strategies x {len(HORIZONS)} horizons ==")
    out.append("")
    out.append("Pre-registered rule: deny (strategy, regime) iff N>=30 AND expectancy_r<0 "
               "AND negative in >=3 of 4 sub-folds (a sub-fold with N<30 counts as 'not negative').")
    out.append("Selection is on expectancy. Win rate is reported, never selected on.")
    out.append("")
    hdr = (f"{'Strategy':22s} {'Regime':16s} {'N':>5s} {'ExpR':>8s} {'Win%':>6s} "
           f"{'Folds-':>7s}  {'fold N (- = negative & N>=30)':32s} {'DENY':>5s}")
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        exp = f"{r['expectancy_r']:+.3f}" if r["expectancy_r"] is not None else "    --"
        wr = f"{r['win_rate']:.1f}" if r["win_rate"] is not None else "  --"
        out.append(f"{r['strategy']:22s} {r['regime']:16s} {r['n']:5d} {exp:>8s} {wr:>6s} "
                   f"{r['folds_negative']:>7d}  {r['fold_detail']:32s} {'DENY' if r['deny'] else '':>5s}")

    out.append("")
    if allow:
        out.append("REGIME_ALLOW: dict[str, tuple] = {")
        for k, v in sorted(allow.items()):
            out.append(f"    {k!r}: {v!r},")
        out.append("}")
    else:
        out.append("REGIME_ALLOW: dict[str, tuple] = {}   # no cell cleared the rule")
        out.append("")
        out.append("NO GATE JUSTIFIED. This is a legitimate recorded outcome, not a prompt")
        out.append("to loosen the thresholds and retry -- that is precisely what the")
        out.append("one-shot validation budget exists to prevent.")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--universe", default=None, help="named universe; default = watchlist")
    p.add_argument("--strategy", action="append", default=None, help="repeatable; default = all")
    p.add_argument("--json", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="write the report here too")
    args = p.parse_args(argv)

    # Measuring must happen ungated: we need the ungated per-regime behaviour
    # in order to decide what to gate.
    if getattr(config, "REGIME_GATES_ENABLED", False):
        print("REFUSING: REGIME_GATES_ENABLED is on. The evidence run must measure "
              "UNGATED behaviour, or it measures the gate it is trying to justify.",
              flush=True)
        return 2

    tickers = universe_symbols(args.universe) if args.universe else load_watchlist()
    benchmark = config.MARKET_REGIME_TICKER
    tickers = [t for t in tickers if t != benchmark]
    strategies = args.strategy or list(ALL_STRATEGIES)

    spy_df = load_cached(benchmark)
    if spy_df is None:
        print(f"REFUSING: {benchmark} is not cached; run scripts/fetch_backtest_data.py first.",
              flush=True)
        return 2

    cached = [t for t in tickers if load_cached(t) is not None]
    print(f"{len(cached)}/{len(tickers)} tickers cached | {len(strategies)} strategies | "
          f"{len(HORIZONS)} horizons", flush=True)

    pooled, by_fold = collect(cached, strategies, spy_df)
    allow, rows = decide(pooled, by_fold, strategies)
    report = render(rows, allow, cached, strategies)
    print("\n" + report, flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps({"allow": {k: list(v) for k, v in allow.items()},
                                         "rows": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
