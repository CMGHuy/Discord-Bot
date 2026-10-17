#!/usr/bin/env python3
"""Grid sweep of one strategy's tunables over the TRAIN window ONLY
(2020-01-01 .. 2023-12-31). Never point this at the validation window --
that is the whole point of having one.

Selection rule (spec section 9): among configs with WR>=80, ExpR>0, N>=30,
pick max expectancy. If none qualify, the ranking output still shows the
best candidates so the failure policy (gating directions/horizons) can be
applied by hand in Task 19.

--instrument v2 (v158): every config runs over the contract's research span on
its point-in-time universe (membership and a causal liquidity floor checked on
the signal day). The grid table and "best" are in-sample; the verdict
statistic is the pooled out-of-fold ExpR of a per-fold selection made on each
fold's purged train trades only, reported with its watchlist slice. Needs
--exit-model v2."""
import argparse
import itertools
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "data"))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import numpy as np

from fetch_backtest_data import add_data_source_arg, apply_data_source, load_cached, load_watchlist
import run_backtest_range as rbr
from swingbot.core.marketdata import training_data
from swingbot.core.marketdata.history_store import MissingStoreError
import swingbot.core.backtesting.backtest as bt
import swingbot.core.market.entry_filters as ef
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument
from swingbot.core.backtesting.instrument import cli as instrument_cli
from swingbot.core.backtesting.instrument import folds as instrument_folds
from swingbot.core.backtesting.instrument import universe_gate

TRAIN = resolve_instrument("v1").train_window   # v1 contract alias (v158 WC7)

PARAM_GRID = {
    # Rescue (Task 108): grid the new pullback entry-mode gate (Task 107),
    # not rsi_dip/ext_atr (fixed at baseline 45/1.0 -- only the new gate is
    # under test). entry_mode="cross" doesn't use pullback_max_bars at all,
    # so it's held fixed at "pullback" here to avoid 3 redundant baseline
    # rows; the "cross" (current-behavior) baseline is computed once
    # separately and reported alongside these 3 rows in the results doc.
    "EMA Crossover":      {"entry_mode": ["pullback"],
                           "pullback_max_bars": [5, 10, 15]},
    "VWAP":               {"ext_pct": [1.0, 1.5, 2.0], "hold_bars_other": [2, 3]},
    "Fibonacci":          {"ratios": [(0.382, 0.5, 0.618), (0.5, 0.618)],
                           "rsi_bull": [(35, 58), (40, 60)]},
    "Support/Resistance": {"base_atr": [3.0, 4.0, 5.0], "close_frac": [0.3, 0.4, 0.5]},
    "RSI":                {"os_level": [30, 35], "confirm": ["prev_high", "prev_close"]},
    "MACD":               {"ext_atr": [0.75, 1.0, 1.5]},
    # Rescue (Task 105): grid the new strict wave-2 gate, not the old
    # depth_min/depth_max pair (those stay fixed at baseline for this run --
    # only the new gate is under test). w2_min_retrace is held constant at
    # 0.382 (not gridded) via a single-value list -- it must be non-None for
    # the gate to activate at all, but this run isn't tuning it.
    "Elliott Wave":       {"w2_min_retrace": [0.382],
                           "w2_max_retrace": [0.618, 0.786],
                           "w2_max_duration_ratio": [0.75, 1.0]},
    # Rescue (Task 102): grid the new expansion gate, not ext_pct (fixed at
    # baseline for this run -- only the new gate is under test).
    "MA Ribbon":          {"min_width_pctile": [0.3, 0.4, 0.5],
                           "require_expanding": [True, False]},
    "Break & Retest":     {"hold_tol_pct": [0.3, 0.5, 0.8]},
    "RSI Divergence":     {"rsi_reclaim": [38, 40, 45]},
    "Volume Profile":     {"node_share": [6.0, 8.0, 10.0], "prox_pct": [1.0, 1.5, 2.0]},
}


def run_config(strategy, dfs, exit_model="v1", scale_out=False):
    tp2_mode = "levels" if exit_model == "v2" else "none"
    trades = []
    for ticker, df in dfs.items():
        for hk in LEGACY_HORIZONS:
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model=exit_model, scale_out=scale_out,
                                    tp2_mode=tp2_mode)
            except Exception:
                continue
            trades.extend(t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1])
    return _stats(trades)


def _stats(trades) -> dict:
    """The tuner's four numbers over one trade list: run_config's tail, moved
    here unchanged so v2's per-fold selection scores trades exactly as v1 does."""
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))
    return {
        "n_eval": len(ev),
        "win_rate": wins / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }


def _qualifies(stats) -> bool:
    """The selection rule's gate (module docstring): WR>=80, ExpR>0, N>=30, excl<=50%."""
    return (stats["n_eval"] >= 30 and (stats["win_rate"] or 0) >= 80
            and (stats["expectancy_r"] or 0) > 0 and stats["excluded_share"] <= 0.5)


def _rank(rows) -> list:
    """(key, stats) rows best first: the qualifying rows by ExpR, else every row
    (the UNGATED full-grid argmax). sorted() is stable, so ties keep grid order."""
    qualifying = [row for row in rows if _qualifies(row[1])]
    return sorted(qualifying or rows, key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)


def _instrument_guards(args, spec) -> None:
    """Under v2, check run_backtest's v2 refusals ONCE, before any ticker loads:
    run_config-style loops swallow every per-run exception, so a refusal there
    would silently empty the grid. v2 runs tp2_mode="none" (TP2 built as live).
    Under v1: no-op."""
    if spec.version == "v1":
        return
    try:
        bt._uses_live_constructor(spec, args.exit_model, "none")
    except ValueError as exc:
        raise SystemExit(f"--instrument {spec.version}: {exc}") from None


def _load_universe(spec) -> tuple[dict, dict]:
    """(frames, spans). v1: today's watchlist frames, no spans. v2: the
    contract's point-in-time universe through run_backtest_range's seams, minus
    missing frames and frames failing its data-quality checks (the non-causal
    liquidity floor is skipped for PIT runs there), with membership spans."""
    if spec.version == "v1":
        return {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}, {}
    tickers = rbr._tickers_for_run(spec.universe)
    membership = rbr._membership_for_run(spec.universe, tickers)
    frames, spans = {}, {}
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None or rbr._exclusion_reason(df, ticker, pit=membership is not None):
            continue
        frames[ticker], spans[ticker] = df, rbr._spans_for(membership, ticker)
    return frames, spans


def _v2_trades(strategy, frames, spans, spec, scale_out) -> list:
    """(ticker, trade) rows of the current config under v2: entry date inside
    the research span, then PIT membership and the causal liquidity floor on
    the SIGNAL day (universe_gate, v136 section 1). Each frame is cut at
    research_end first, so no trade -- test-fold trades included -- reads a
    sealed-holdout bar (folds.out_of_fold's caller rule)."""
    date_from, date_to = instrument_cli.window_for(spec, "train")
    rows = []
    for ticker, full in frames.items():
        df = rbr._instrument_frame(full, spec)     # no bar past research_end (WC4)
        for hk in LEGACY_HORIZONS:
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model="v2", scale_out=scale_out, tp2_mode="none",
                                    instrument=spec)
            except Exception:
                continue
            kept = universe_gate.eligible_trades(rbr.window_trades(s, date_from, date_to),
                                                 spans.get(ticker), df, spec.liquidity_floor)
            rows.extend((ticker, t) for t in kept)
    return rows


def _evaluate(strategy, universe, args, spec) -> tuple[dict, list | None]:
    """(stats, rows) for the current DEFAULT_PARAMS. v1: run_config exactly as
    today and no rows kept. v2: research-span stats and the (ticker, trade) rows."""
    frames, spans = universe
    if spec.version == "v1":
        return run_config(strategy, frames, exit_model=args.exit_model,
                          scale_out=args.scale_out), None
    rows = _v2_trades(strategy, frames, spans, spec, args.scale_out)
    return _stats([t for _, t in rows]), rows


def _fold_select(train) -> int:
    """One fold's config index, chosen on that fold's train trades only, by the
    same rule the in-sample ranking uses."""
    return _rank([(i, _stats(trades)) for i, trades in sorted(train.items())])[0][0]


def _out_of_fold(rows_by_config, spec):
    """Per-fold selection and the pooled out-of-fold trades (v136 section 1).
    One config means nothing was tuned: its research-span trades are its
    out-of-fold trades and the folds are skipped. The tuner pools every
    horizon, so the embargo is the contract's global maximum (decision 2)."""
    trades_by_config = {i: [t for _, t in rows] for i, rows in rows_by_config.items()}
    if len(trades_by_config) == 1:
        (only,) = trades_by_config.values()
        return instrument_folds.OutOfFold(choices=(), trades=only)
    return instrument_folds.out_of_fold(trades_by_config, instrument_folds.anchored_folds(spec),
                                        _fold_select, embargo_days=spec.embargo_days,
                                        purge=spec.purge)


def _watchlist_slice(trades, rows_by_config) -> dict:
    """The out-of-fold pool's watchlist slice and its verdict (v136 section 1)."""
    owner = {id(t): ticker for rows in rows_by_config.values() for ticker, t in rows}
    members = set(load_watchlist())
    stats = _stats([t for t in trades if owner[id(t)] in members])
    verdict = universe_gate.watchlist_slice_verdict(stats["n_eval"], stats["expectancy_r"])
    return {"status": verdict.status, "n": verdict.n, "expectancy_r": verdict.expectancy_r}


def _fmt(value, fmt: str) -> str:
    return "n/a" if value is None else format(value, fmt)


def _fold_report(rows, rows_by_config, spec) -> dict:
    """Print the v2 verdict block and return its JSON keys. v1: {} and silent,
    so v1's stdout and JSON stay byte-identical."""
    if spec.version == "v1":
        return {}
    oof = _out_of_fold(rows_by_config, spec)
    stats = _stats(oof.trades)
    folds = [{"test_year": year, "params": rows[i][0]} for year, i in oof.choices]
    slice_ = _watchlist_slice(oof.trades, rows_by_config)
    start, end = spec.research_span
    print(f"\n== instrument {spec.version}: research span {start}..{end}, universe "
          f"{spec.universe}; PIT membership and the causal liquidity floor on the signal day")
    print("The grid and 'best' above are in-sample over the research span; the verdict "
          "statistic is the pooled out-of-fold ExpR below.")
    if not folds:
        print("Nothing tuned (one config): its research-span trades are its out-of-fold trades.")
    for fold in folds:
        print(f"  fold {fold['test_year']}: selected on train data only -> {fold['params']}")
    print(f"Pooled out-of-fold: N={stats['n_eval']} WR={_fmt(stats['win_rate'], '.1f')} "
          f"ExpR={_fmt(stats['expectancy_r'], '+.3f')} "
          f"(purge={spec.purge}, embargo={spec.embargo_days}d)")
    print(f"Watchlist slice of the out-of-fold pool: N={slice_['n']} "
          f"ExpR={_fmt(slice_['expectancy_r'], '+.3f')} -> {slice_['status'].upper()} "
          f"(ExpR < 0 with N >= {universe_gate.WATCHLIST_SLICE_MIN_N} fails the verdict; "
          f"fewer is THIN)")
    return {"instrument": spec.version, "research_span": [start, end],
            "out_of_fold": {"folds": folds, **stats}, "watchlist_slice": slice_}

def _parse_grid_value(s: str):
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("none", "null"):
        return None
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def report_gate(rows: list, qualifying: list) -> dict:
    """Report whether the acceptance gate selected any grid cell."""
    gated = bool(qualifying)
    headline = f"{len(qualifying)}/{len(rows)} configs qualify (WR>=80, ExpR>0, N>=30, excl<=50%)"
    if not gated:
        headline += " ***UNGATED***: no config cleared the gate; ranking is the full-grid argmax."
    return {"gated": gated, "n_qualifying": len(qualifying), "n_rows": len(rows), "headline": headline}


def _select_source(args) -> str:
    """Pick the training bars before any is read. A missing Alpaca store stops
    the grid with an error naming the path (spec §3), never a zero-ticker grid."""
    try:
        return apply_data_source(args)
    except MissingStoreError as exc:
        raise SystemExit(f"error: {exc}") from exc


def _report_exclusions() -> None:
    for line in training_data.exclusion_lines():
        print(line, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--be-trigger", type=float, default=None)
    ap.add_argument("--grid", nargs="+", default=None, metavar="KEY=V1,V2",
                    help="override the built-in grid, e.g. "
                         "--grid max_adx=20,25,30 require_bb_range=true,false "
                         "(sweeps ONLY these keys; other params stay at "
                         "DEFAULT_PARAMS)")
    ap.add_argument("--exit-model", dest="exit_model", choices=["v1", "v2"],
                    default="v1")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true")
    ap.add_argument("--json", type=str, default=None,
                    help="Write results (grid + best) as JSON to this path.")
    add_data_source_arg(ap)
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args(argv)
    instrument = instrument_cli.spec_from_args(args)
    _instrument_guards(args, instrument)
    data_source = _select_source(args)
    strategy = args.strategy
    if args.grid:
        grid_override = {}
        for spec in args.grid:
            key, _, vals = spec.partition("=")
            if not vals:
                ap.error(f"bad --grid spec {spec!r}, expected KEY=V1,V2,...")
            grid_override[key] = [_parse_grid_value(v) for v in vals.split(",")]
        PARAM_GRID[strategy] = grid_override
    if strategy not in PARAM_GRID:
        ap.error(f"unknown strategy {strategy!r}; one of {list(PARAM_GRID)}")
    if args.be_trigger is not None:
        bt.BREAKEVEN_TRIGGER_FRACTION = args.be_trigger

    universe = _load_universe(instrument)
    print(f"{len(universe[0])} tickers loaded from {data_source} training data")
    _report_exclusions()

    grid = PARAM_GRID[strategy]
    keys = list(grid)
    baseline = dict(ef.DEFAULT_PARAMS[strategy])
    rows, rows_by_config = [], {}
    try:
        for combo in itertools.product(*(grid[k] for k in keys)):
            params = dict(zip(keys, combo))
            ef.DEFAULT_PARAMS[strategy].update(params)
            stats, trade_rows = _evaluate(strategy, universe, args, instrument)
            rows_by_config[len(rows)] = trade_rows
            rows.append((params, stats))
            wr = f"{stats['win_rate']:.1f}" if stats["win_rate"] is not None else "n/a"
            er = f"{stats['expectancy_r']:+.3f}" if stats["expectancy_r"] is not None else "n/a"
            print(f"  {params} -> N={stats['n_eval']} WR={wr} ExpR={er} excl={stats['excluded_share']*100:.0f}%")
    finally:
        ef.DEFAULT_PARAMS[strategy] = baseline

    qualifying = [(p, s) for p, s in rows if _qualifies(s)]
    gate_report = report_gate(rows, qualifying)
    print("\n" + gate_report["headline"])
    ranked = _rank(rows)
    print("Top 5:")
    for p, s in ranked[:5]:
        print(f"  {p} -> N={s['n_eval']} WR={s['win_rate'] and round(s['win_rate'],1)} ExpR={s['expectancy_r'] and round(s['expectancy_r'],3)}")

    fold_json = _fold_report(rows, rows_by_config, instrument)

    if args.json:
        best = ranked[0] if ranked else None
        payload = {
            "strategy": strategy,
            "gate": gate_report,
            "grid": [{"params": p, **s} for p, s in rows],
            "best": ({"params": best[0], **best[1]} if best else None),
            **fold_json,
            "data_source": data_source,
            "provenance": training_data.provenance(),
        }
        Path(args.json).write_text(json.dumps(payload, indent=2))
        training_data.write_provenance(args.json)
        print(f"Wrote results to {args.json}")


if __name__ == "__main__":
    main()
