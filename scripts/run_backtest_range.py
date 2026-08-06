#!/usr/bin/env python3
"""Acceptance harness: runs every strategy x horizon x cached ticker and
pools results per strategy over an entry-date window.

    python scripts/run_backtest_range.py --train        # 1999-01-01 .. 2023-12-31
    python scripts/run_backtest_range.py --validation   # 2024-01-01 .. 2025-12-31 (run ONCE, at the end)

--train covers 25 years as of plan v8 Task V46 (it meant 2020-01-01 before;
the windows now come from swingbot/core/backtest_windows.py). A --train run
is correspondingly ~6x longer than it used to be.
    python scripts/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 --strategy "RSI"

PASS gate is plan v8 V6 Step 3's rule: expectancy_r > 0, N >= 30 (train) / 15
(validation), scratches+timeouts <= 50% of closed trades. Win rate is the
RANKING OBJECTIVE, not a threshold -- the old `win_rate >= 80` bar was voided
by V6 as incompatible with a 2.5% target floor, and removed from the code by
V49 after V16 caught this script still scoring against it."""
import argparse
import json
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.backtest_scenarios import CONFLUENCE_GATES, run_scenario_backtest
from swingbot.core.strategy_types import HORIZONS
from swingbot.core.universe import data_quality_issues, liquidity_reason

from swingbot.core.backtest_windows import TRAIN, VALIDATION      # noqa: E402


def window_trades(summary, date_from, date_to):
    return [t for t in summary.trades if date_from <= t.entry_date <= date_to]


def pool(trades):
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = [t for t in ev if t.outcome == "win"]
    scr = [t for t in trades if t.outcome == "scratch"]
    to = [t for t in trades if t.outcome == "timeout"]
    closed = len(trades)
    return {
        "n_eval": len(ev), "wins": len(wins), "losses": len(ev) - len(wins),
        "scratches": len(scr), "timeouts": len(to), "closed": closed,
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": (len(scr) + len(to)) / closed if closed else 0.0,
        "avg_win_r": float(np.mean([t.r_multiple for t in wins])) if wins else None,
    }


def pooled_max_dd_pct(trades, risk_pct=1.0):
    """Compounded max drawdown %, pooling every ticker/horizon this
    strategy traded into one chronological (entry_date order) equity
    curve at a fixed assumed risk_pct per trade. This is a portfolio-level
    PROXY, not a true concurrent-position-aware curve (overlapping trades
    aren't modeled) -- but it's the standard, defensible way to turn a
    pool of R-multiples into a single max-DD figure without a second full
    backtest run (Task E22; the prior ad hoc attempt at this re-ran the
    whole grid a second time and was abandoned as too slow -- this reuses
    the trades already collected in the same run).
    Returns None (not 0.0) for an empty trade list, so "no trades" isn't
    misread as "no drawdown"."""
    ordered = sorted((t for t in trades if t.r_multiple is not None), key=lambda t: t.entry_date)
    if not ordered:
        return None
    equity = peak = 1.0
    max_dd = 0.0
    for t in ordered:
        equity *= 1 + (risk_pct / 100.0) * t.r_multiple
        peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak * 100.0)
    return max_dd


def _wilson_str(stats):
    """Formatted Wilson lower bound for a stats row. `wins` is carried by
    pool() but not by the scenario adapter, so fall back to deriving it --
    both sides come from integer counts, so the round-trip is exact."""
    n = stats["n_eval"]
    if not n or stats["win_rate"] is None:
        return "n/a"
    wins = stats.get("wins")
    if wins is None:
        wins = round(stats["win_rate"] / 100.0 * n)
    return f"{wilson_lower_bound(wins, n):.1f}"


GATE_LEGEND = "pass: ExpR>0, N>={min_n}, dead<=50% (V6 Step 3; WR is the objective, not a gate)"


def wilson_lower_bound(wins, n, z=1.96):
    """Lower bound of the 95% CI on the win rate, in percent.

    Pre-registered by plan v8 V6 Step 5 and emitted by nothing until V49: a
    headline win rate on a small N is a hypothesis, not a finding, and the
    bound is what tells the two apart. V16's RSI reads 80.3% on N=122 and
    55.2% on the ~12 trades that are actually independent.
    """
    if not n:
        return None
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / den * 100


def passes(stats, min_n):
    """Plan v8 V6 Step 3's acceptance gate.

    The `win_rate >= 80` bar this used to carry is **void** -- V6 retired it
    explicitly ("void under a 2.5% floor") and made win rate the ranking
    OBJECTIVE rather than a threshold, because a 2.5% target floor and an 80%
    win rate are in direct tension. It survived here until V49 found V16's
    report still printing PASS/FAIL against it, which inverted the verdict:
    the stale gate passed 1 of 11 strategies, this one passes 10.

    What remains is V6's actual rule -- positive expectancy, enough sample,
    and no more than half the closed trades dying flat. Ranking by win rate
    is the caller's job (see the sorted report), not this predicate's.
    """
    return (stats["n_eval"] >= min_n
            and stats["expectancy_r"] is not None and stats["expectancy_r"] > 0
            and stats["excluded_share"] <= 0.5)


def _scenario_row_stats(agg):
    """Adapt backtest_scenarios._aggregate's stats shape to the same
    n_eval/win_rate/expectancy_r/excluded_share shape `pool()`/`passes()`
    use, so scenario rows print through the same table format."""
    closed = agg["n"] + agg["scratches"] + agg["timeouts"]
    return {
        "n_eval": agg["n"], "win_rate": agg["win_rate"],
        "expectancy_r": agg["expectancy_r"],
        "scratches": agg["scratches"], "timeouts": agg["timeouts"],
        "excluded_share": (agg["scratches"] + agg["timeouts"]) / closed if closed else 0.0,
    }


def run_scenario_mode(date_from, date_to, min_n, label, *, scale_out, universe=None):
    """--scenarios: replay the confluence scan itself (backtest_scenarios)
    instead of a named strategy, and print per-horizon + pooled rows in the
    standard table with strategy column `confluence/<horizon>`."""
    tickers = _tickers_for_run(universe)
    frames = {}
    excluded_illiquid = []   # [(ticker, reason), ...] -- printed as a header block below
    excluded_bad_data = []   # [(ticker, "; ".join(issues)), ...] -- Task E16, same pattern
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None:
            continue
        reason = liquidity_reason(df)
        if reason is not None:
            excluded_illiquid.append((ticker, reason))
            continue
        issues = data_quality_issues(df, ticker)
        if issues:
            excluded_bad_data.append((ticker, "; ".join(issues)))
            continue
        frames[ticker] = df
    print(f"loaded {len(frames)}/{len(tickers)} cached tickers "
          f"({len(excluded_illiquid)} excluded illiquid, "
          f"{len(excluded_bad_data)} excluded bad data)", flush=True)

    stats = run_scenario_backtest(frames, date_from, date_to,
                                  gates=CONFLUENCE_GATES, scale_out=scale_out,
                                  horizons=list(HORIZONS))

    header = (f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>7s} "
              f"{'Scr':>5s} {'TO':>5s} {'Dead%':>6s}  PASS")
    lines = []
    if excluded_illiquid:
        lines.append(f"-- excluded (illiquid, Task E12): {len(excluded_illiquid)} of {len(tickers)} ticker(s) --")
        lines.extend(f"  {tkr}: {reason}" for tkr, reason in excluded_illiquid)
        lines.append("")
    if excluded_bad_data:
        lines.append(f"-- excluded (bad data, Task E16): {len(excluded_bad_data)} of {len(tickers)} ticker(s) --")
        lines.extend(f"  {tkr}: {reason}" for tkr, reason in excluded_bad_data)
        lines.append("")
    lines.append(f"== {label} {date_from} .. {date_to} | confluence scenario replay | "
                 f"{GATE_LEGEND.format(min_n=min_n)} ==")
    lines.append(header)
    for hk in HORIZONS:
        st = _scenario_row_stats(stats["by_horizon"][hk])
        if st["n_eval"] == 0 and st["scratches"] == 0 and st["timeouts"] == 0:
            continue
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        flag = "PASS" if passes(st, min_n) else "FAIL"
        lines.append(f"{'confluence/' + hk:22s} {st['n_eval']:5d} {wr:>6s} {_wilson_str(st):>6s} {er:>7s} "
                     f"{st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%  {flag}")

    pooled = _scenario_row_stats(stats["pooled"])
    wr = f"{pooled['win_rate']:.1f}" if pooled["win_rate"] is not None else "n/a"
    er = f"{pooled['expectancy_r']:+.3f}" if pooled["expectancy_r"] is not None else "n/a"
    flag = "PASS" if passes(pooled, min_n) else "FAIL"
    lines.append(f"{'confluence/pooled':22s} {pooled['n_eval']:5d} {wr:>6s} {_wilson_str(pooled):>6s} {er:>7s} "
                 f"{pooled['scratches']:5d} {pooled['timeouts']:5d} {pooled['excluded_share']*100:5.0f}%  {flag}")

    report = "\n".join(lines)
    print("\n" + report)
    Path("backtest_range_summary.txt").write_text(report, encoding="utf-8")
    print("\nSaved backtest_range_summary.txt")


def _tickers_for_run(universe: str | None) -> list:
    """Ticker set for the scan: a named universe (e.g. 'etfs', Task E80)
    when given, else the watchlist -- same override seam as
    backtest_wf._symbols_for_folds/run_folds' tickers= param."""
    if universe:
        from swingbot.core.universe import universe_symbols
        return sorted(universe_symbols(universe))
    return sorted(load_watchlist())


def build_registry_records(summaries, *, source, window, run_date,
                           horizon=None, min_n=15):
    """Turn pooled per-strategy summaries into validation-registry records.

    A record is VALIDATED only when it clears the acceptance gates on the
    window it was measured on; everything else (including tiny-N) is WEAK.

    **Plan v8 V25 (2026-08-06): this used its own `win_rate >= 80` test, the
    gate V6 Step 3 voided.** V49 replaced that rule with `passes()` in this
    same file and fixed the PASS/FAIL report column in five scripts, but the
    registry emitter kept a private copy — so the report and the registry
    disagreed inside one file, the report printing PASS where the registry
    wrote WEAK. That mattered more than the report did: the registry is the
    only one of the two the **live bot reads**, through `registry.get_badge`
    into `WEAK_CAUTION_TEXT` and 20 points of quality score.

    Re-derived against the committed registry, four strategies are WEAK
    solely because of the voided clause — **RSI Divergence (n=1099, WR 75.8%,
    ExpR +0.208)**, MA Ribbon (137, 78.1%, +0.213), Elliott Wave (75, 77.3%,
    +0.064), EMA Crossover (36, 75.0%, +0.061). None of the seven current
    VALIDATED rows loses its badge under the correct rule.

    Note `passes()` needs `excluded_share`, which the old summary shape
    dropped. Callers must carry it; a summary without it cannot be judged and
    raises rather than silently passing a two-of-three test."""
    recs = []
    for s in summaries:
        wr = s.get("win_rate")
        er = s.get("expectancy_r")
        if "excluded_share" not in s:
            raise KeyError(
                f"registry summary for {s.get('strategy')!r} has no "
                "'excluded_share' -- passes() cannot apply V6 Step 3's "
                "dead<=50% criterion, and silently skipping it would "
                "re-introduce a partial gate")
        validated = passes({"n_eval": s["n"], "win_rate": wr,
                            "expectancy_r": er,
                            "excluded_share": s["excluded_share"]}, min_n)
        recs.append({"source": source, "strategy": s["strategy"], "horizon": horizon,
                     "status": "VALIDATED" if validated else "WEAK",
                     "n": s["n"],
                     "win_rate": round(wr, 1) if wr is not None else 0.0,
                     "expectancy_r": round(er, 3) if er is not None else 0.0,
                     "window": window, "run_date": run_date})
    return recs


def merge_registry(path, new_records):
    """Merge records into the registry JSON, replacing same-key entries."""
    path = Path(path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    new_keys = {(r["source"], r["strategy"], r.get("horizon")) for r in new_records}
    kept = [r for r in existing
            if (r["source"], r["strategy"], r.get("horizon")) not in new_keys]
    merged = sorted(kept + new_records,
                    key=lambda r: (r["source"], r["strategy"], str(r.get("horizon"))))
    path.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--universe", default=None,
                    help="scope tickers to a named universe (e.g. 'etfs', Task E80) via "
                         "swingbot.core.universe.universe_symbols, instead of the watchlist")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--emit-registry", dest="emit_registry", default=None,
                    help="path to validation_registry.json to merge records into")
    ap.add_argument("--run-date", dest="run_date", default=None,
                    help="YYYY-MM-DD stamped on emitted registry records "
                         "(required with --emit-registry; explicit for reproducibility)")
    ap.add_argument("--exit-model", dest="exit_model", choices=["v1", "v2"], default="v1")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true")
    ap.add_argument("--frictions", dest="frictions", choices=["on", "off"], default="on",
                    help="v1-only slippage+commission realism (Task E11). 'on' (default) is the "
                         "honest baseline every later Edge-plan component must beat; 'off' "
                         "reproduces the pre-E11 frictionless arithmetic.")
    ap.add_argument("--tp2", dest="tp2", choices=["none", "levels"], default="levels",
                    help="TP2 source for scale-out runs (v2 only)")
    ap.add_argument("--scenarios", action="store_true",
                    help="replay the confluence scan itself (backtest_scenarios."
                         "run_scenario_backtest) instead of the named-strategy loop")
    ap.add_argument("--from-json", dest="from_json", default=None,
                    help="replay per-strategy summaries from a previous --json "
                         "output instead of running the backtest (honors the "
                         "run-once validation budget); requires --emit-registry")
    args = ap.parse_args()
    if args.emit_registry and not args.run_date:
        ap.error("--emit-registry requires --run-date")

    if args.train:
        date_from, date_to, min_n, label = *TRAIN, 30, "TRAIN"
    elif args.validation:
        date_from, date_to, min_n, label = *VALIDATION, 15, "VALIDATION"
    else:
        if not (args.date_from and args.date_to):
            ap.error("need --train, --validation, or --from/--to")
        date_from, date_to, min_n, label = args.date_from, args.date_to, 15, "CUSTOM"

    if args.from_json:
        # Registry regeneration WITHOUT re-running the window (run-once
        # validation discipline). Reads the {strategy: stats} shape --json
        # writes, not a fresh backtest.
        if not args.emit_registry:
            ap.error("--from-json only makes sense with --emit-registry")
        with open(args.from_json, encoding="utf-8") as f:
            results = json.load(f)
        summaries = [{"strategy": k, "n": v["n_eval"], "win_rate": v["win_rate"],
                      "expectancy_r": v["expectancy_r"],
                      # V25: passes() needs the dead<=50% criterion too.
                      # Forwarded only if present rather than defaulted to
                      # 0.0 -- defaulting a MISSING one asserts "no dead
                      # trades", the most permissive possible answer, for a
                      # shape that cannot answer. build_registry_records
                      # raises on the gap instead of half-applying the gate.
                      **({"excluded_share": v["excluded_share"]}
                         if "excluded_share" in v else {})}
                     for k, v in results.items()]
        merge_registry(args.emit_registry, build_registry_records(
            summaries, source="strategy", window=f"{date_from}..{date_to}",
            run_date=args.run_date, min_n=min_n))
        print(f"Merged {len(summaries)} records into {args.emit_registry} "
              f"(replayed from {args.from_json}, no backtest run)")
        return

    if args.scenarios:
        run_scenario_mode(date_from, date_to, min_n, label, scale_out=args.scale_out,
                          universe=args.universe)
        return

    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    by_strategy = defaultdict(list)
    by_combo = defaultdict(list)
    # Runner sub-outcome counts (v2 + scale-out only). `runner_outcome` is
    # stamped per-trade on BacktestTrade (v2 branch only), so these ARE
    # filtered to the date window exactly like by_strategy/by_combo above --
    # derived from `tr` (window_trades' output), not from the unfiltered
    # BacktestSummary.runner_tp2/trail/be/timeout run-level aggregates.
    runner_by_strategy = defaultdict(lambda: {"tp2": 0, "trail": 0, "be": 0, "timeout": 0, "wins": 0})
    show_runner_cols = args.exit_model == "v2" and args.scale_out
    tp2_mode = args.tp2 if args.exit_model == "v2" else "none"

    tickers = _tickers_for_run(args.universe)
    excluded_illiquid = []   # [(ticker, reason), ...] -- printed as a header block in the final report
    excluded_bad_data = []   # [(ticker, "; ".join(issues)), ...] -- Task E16, same pattern
    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        reason = liquidity_reason(df)
        if reason is not None:
            excluded_illiquid.append((ticker, reason))
            print(f"[{ti}/{len(tickers)}] {ticker}: excluded (illiquid) -- {reason}", flush=True)
            continue
        issues = data_quality_issues(df, ticker)
        if issues:
            excluded_bad_data.append((ticker, "; ".join(issues)))
            print(f"[{ti}/{len(tickers)}] {ticker}: excluded (bad data) -- {'; '.join(issues)}", flush=True)
            continue
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model=args.exit_model, scale_out=args.scale_out,
                                      tp2_mode=tp2_mode, frictions=(args.frictions == "on"))
                except Exception as e:
                    print(f"    ! {strat}/{hk}: {e}")
                    continue
                tr = window_trades(s, date_from, date_to)
                by_strategy[strat].extend(tr)
                by_combo[(strat, hk)].extend(tr)
                if show_runner_cols:
                    rb = runner_by_strategy[strat]
                    rb["tp2"] += sum(1 for t in tr if t.runner_outcome == "runner_tp2")
                    rb["trail"] += sum(1 for t in tr if t.runner_outcome == "runner_trail")
                    rb["be"] += sum(1 for t in tr if t.runner_outcome == "runner_be")
                    rb["timeout"] += sum(1 for t in tr if t.runner_outcome == "runner_timeout")
                    rb["wins"] += sum(1 for t in tr if t.outcome == "win")

    header = f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'WilLB':>6s} {'ExpR':>7s} {'MaxDD%':>7s}"
    if show_runner_cols:
        header += f" {'AvgWinR':>7s}"
    # "Dead%", not "Excl%": this is (scratches+timeouts)/closed, the share of
    # CLOSED TRADES that resolved as neither win nor loss. It has nothing to do
    # with the excluded-ticker blocks printed above, and the old name caused a
    # misreading in V16's write-up before V49 renamed it.
    header += f" {'Scr':>5s} {'TO':>5s} {'Dead%':>6s}"
    if show_runner_cols:
        header += f" {'tp2%':>6s} {'trail%':>6s} {'be%':>6s} {'rto%':>6s}"
    header += "  PASS"
    lines = []
    if excluded_illiquid:
        lines.append(f"-- excluded (illiquid, Task E12): {len(excluded_illiquid)} of {len(tickers)} ticker(s) --")
        lines.extend(f"  {tkr}: {reason}" for tkr, reason in excluded_illiquid)
        lines.append("")
    if excluded_bad_data:
        lines.append(f"-- excluded (bad data, Task E16): {len(excluded_bad_data)} of {len(tickers)} ticker(s) --")
        lines.extend(f"  {tkr}: {reason}" for tkr, reason in excluded_bad_data)
        lines.append("")
    lines.append(f"== {label} {date_from} .. {date_to} | {GATE_LEGEND.format(min_n=min_n)} ==")
    lines.append(header)
    results = {}
    for strat in strategies:
        st = pool(by_strategy[strat])
        st["max_dd_pct"] = pooled_max_dd_pct(by_strategy[strat])
        results[strat] = dict(st)
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        dd = f"{st['max_dd_pct']:.1f}" if st["max_dd_pct"] is not None else "n/a"
        flag = "PASS" if passes(st, min_n) else "FAIL"
        row = f"{strat:22s} {st['n_eval']:5d} {wr:>6s} {_wilson_str(st):>6s} {er:>7s} {dd:>7s}"
        if show_runner_cols:
            awr = f"{st['avg_win_r']:+.3f}" if st["avg_win_r"] is not None else "n/a"
            row += f" {awr:>7s}"
        row += f" {st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%"
        if show_runner_cols:
            rb = runner_by_strategy[strat]

            def runner_pct(count, _rb=rb):
                return f"{count / _rb['wins'] * 100:5.1f}%" if _rb["wins"] else "n/a"

            tp2_pct, trail_pct, be_pct, rto_pct = (
                runner_pct(rb["tp2"]), runner_pct(rb["trail"]),
                runner_pct(rb["be"]), runner_pct(rb["timeout"]))
            row += f" {tp2_pct:>6s} {trail_pct:>6s} {be_pct:>6s} {rto_pct:>6s}"
            results[strat].update({
                "runner_tp2_pct": (rb["tp2"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_trail_pct": (rb["trail"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_be_pct": (rb["be"] / rb["wins"] * 100) if rb["wins"] else None,
                "runner_timeout_pct": (rb["timeout"] / rb["wins"] * 100) if rb["wins"] else None,
            })
        row += f"  {flag}"
        lines.append(row)

    lines.append("\n-- per strategy x horizon (for gating decisions) --")
    lines.append(f"{'Strategy':22s} {'Horiz':6s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s}")
    for (strat, hk), tr in sorted(by_combo.items()):
        st = pool(tr)
        if st["closed"] == 0:
            continue
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        lines.append(f"{strat:22s} {hk:6s} {st['n_eval']:5d} {wr:>6s} {er:>7s}")

    # V49 Step 3: the strategy-level N above is the SUM over horizons. That is
    # honest only when a strategy's entries actually differ per horizon. Some
    # ignore the horizon entirely and emit the identical signal set ten times,
    # in which case the summed N -- and every sample-size gate resting on it --
    # overstates the independent evidence tenfold. V16 found RSI reading N=122
    # on ~12 real trades. Detected here rather than assumed: two horizons are
    # the same run if their (date, entry, direction) signatures match exactly.
    # Compare DISTINCT entry signals against the summed count rather than
    # testing horizons for exact equality: a horizon-invariant strategy still
    # resolves a few trades differently at the window edge (a 9m hold may not
    # close where a 2m one does), so exact equality gives a false negative --
    # it did, for RSI, the strategy that motivated this check.
    invariant = []
    for strat in strategies:
        per_hz = {hk: {(t.entry_date, t.entry, t.direction) for t in by_combo[(strat, hk)]}
                  for hk in HORIZONS if by_combo[(strat, hk)]}
        if len(per_hz) < 2:
            continue
        distinct = set().union(*per_hz.values())
        summed = sum(len(s) for s in per_hz.values())
        if not distinct:
            continue
        ratio = summed / len(distinct)
        results[strat]["n_distinct_signals"] = len(distinct)
        results[strat]["horizon_overcount"] = round(ratio, 2)
        if ratio >= 1.5:      # anything near 1.0 is genuinely horizon-specific
            n_indep = round(results[strat]["n_eval"] / ratio)
            results[strat]["n_independent"] = n_indep
            invariant.append((strat, len(per_hz), ratio, n_indep))
    for strat in results:
        results[strat].setdefault("n_independent", results[strat]["n_eval"])

    if invariant:
        lines.append("\n-- WARNING: signals reused across horizons (summed N overstates evidence) --")
        for strat, n_hz, ratio, n_indep in sorted(invariant):
            st = results[strat]
            lb = wilson_lower_bound(round((st["win_rate"] or 0) / 100.0 * n_indep), n_indep)
            lb_s = f"{lb:.1f}%" if lb is not None else "n/a"
            lines.append(
                f"  {strat}: the same signals recur across {n_hz} horizons "
                f"({st['n_distinct_signals']} distinct, counted {ratio:.1f}x over). "
                f"Reported N={st['n_eval']} is ~{n_indep} independent trades; "
                f"Wilson LB on the real sample {lb_s}, not {_wilson_str(st)}%.")
        lines.append("  Do NOT satisfy an N>=15/30 gate with these numbers -- see plan v8 V16/V49.")

    report = "\n".join(lines)
    print("\n" + report)
    Path("backtest_range_summary.txt").write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}, indent=2))
    if args.emit_registry:
        summaries = [{"strategy": k, "n": v["n_eval"], "win_rate": v["win_rate"],
                      "expectancy_r": v["expectancy_r"],
                      # V25: passes() needs the dead<=50% criterion too.
                      # Forwarded only if present rather than defaulted to
                      # 0.0 -- defaulting a MISSING one asserts "no dead
                      # trades", the most permissive possible answer, for a
                      # shape that cannot answer. build_registry_records
                      # raises on the gap instead of half-applying the gate.
                      **({"excluded_share": v["excluded_share"]}
                         if "excluded_share" in v else {})}
                     for k, v in results.items()]
        merge_registry(args.emit_registry, build_registry_records(
            summaries, source="strategy", window=f"{date_from}..{date_to}",
            run_date=args.run_date, min_n=min_n))
        print(f"Merged {len(summaries)} records into {args.emit_registry}")
    print("\nSaved backtest_range_summary.txt")


if __name__ == "__main__":
    main()
