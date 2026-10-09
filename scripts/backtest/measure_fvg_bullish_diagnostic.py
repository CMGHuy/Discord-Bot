#!/usr/bin/env python3
"""v143 FVG (bullish) badge diagnostic: the one TRAIN replay and its tables.

Read-only. Replays the baseline confluence book on TRAIN 2020-01-01..2023-12-31
(signal date) over every cached ticker and all ten LEGACY_HORIZONS, keeps the
plans whose primary strategy is "FVG (bullish)" and whose exit triggers, and
writes one results document. VALIDATION is never read; nothing live changes.
All arithmetic lives in swingbot/core/backtesting/fvg_diagnostic.py.

replay_scenarios is not changed. Gap matching and the replay quality score
need each plan's SCENARIO (its clustered target and stop levels and their
sources; plan.tp1 is re-selected structurally and may differ), which
replay_scenarios does not return, and the bar its cached level map was built
on (levels_asof reuses one map for up to LEVEL_REFRESH_BARS bars). So
`replay_with_scenarios` wraps backtest_scenarios.build_confluence_plan and
backtest_scenarios.levels_asof for the one call and records both -- the
acceptance_replay._break_retest_plans pattern.

The replay runs ONCE (about 70 minutes at 6 workers). Its rows are saved to
logs/v143-fvg-bullish-rows.json before anything is rendered, so a crash while
rendering is repaired with --from-rows, never with a second replay.

PROGRESS: a flushed line per ticker, plus
logs/measure_fvg_bullish_diagnostic.progress (percent, rewritten per ticker,
deleted on completion).

Run: python scripts/backtest/measure_fvg_bullish_diagnostic.py --date 2026-10-10 --earnings-dir <dir>
Smoke: ... --tickers 2 --out-dir <scratch dir>   (never the results directory)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting import fvg_diagnostic as fd  # noqa: E402
from swingbot.core.market.earnings_calendar import EARNINGS_CSV_DIR, CsvSource  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402
from swingbot.core.planning.acceptance_levels import enabled_arms  # noqa: E402
from swingbot.core.planning.exit_sim import simulate_exit  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results"
LOG_DIR = ROOT / "logs"
PROGRESS = LOG_DIR / "measure_fvg_bullish_diagnostic.progress"
ROWS_NAME = "v143-fvg-bullish-rows.json"
DOC_SUFFIX = "v143-fvg-bullish-diagnostic.md"
#: Triggered confluence plans of every primary on TRAIN (spec § Why). Printed
#: beside the measured figure as a disclosure; only EXPECTED_N gates.
EXPECTED_ALL = 8089


# --- replay ------------------------------------------------------------------

def replay_with_scenarios(ticker, frame, horizon_key, **replay_kwargs) -> list:
    """(signal_index, plan, scenario, map_bar) for every plan replay_scenarios
    emits. `map_bar` is the bar the level map behind the plan was built on:
    the last bar whose levels_asof call ADDED a map to the replay's cache, so
    it follows the real cache whatever the warm-up or bucket alignment. Both
    are captured by wrapping the two module attributes for this one call; the
    replay itself runs unchanged."""
    captured: dict = {}
    state = {"map_bar": None}
    build, asof = bs.build_confluence_plan, bs.levels_asof

    def recording_asof(ticker_, df, bar_index, horizon_key_, cache):
        before = len(cache)
        result = asof(ticker_, df, bar_index, horizon_key_, cache)
        if len(cache) > before:
            state["map_bar"] = bar_index
        return result

    def recording_build(scenario, window, **kwargs):
        plan = build(scenario, window, **kwargs)
        if plan is not None:
            captured[id(plan)] = (scenario, state["map_bar"])
        return plan

    bs.build_confluence_plan, bs.levels_asof = recording_build, recording_asof
    try:
        plans = bs.replay_scenarios(ticker, frame, horizon_key, **replay_kwargs)
    finally:
        bs.build_confluence_plan, bs.levels_asof = build, asof
    return [(i, plan, *captured[id(plan)]) for i, plan in plans]


def signal_context(frame, i, plan, captured, ticker_context) -> fd.SignalContext:
    """The scenario's levels and sources, the map bar, and this trade's two
    readings. `captured` is (scenario, map_bar)."""
    scenario, map_bar = captured
    positions, calendar, tolerance_pct = ticker_context
    signal = frame.index[i].date()
    return fd.SignalContext(
        target=scenario.take_profit, target_sources=tuple(scenario.target_sources or ()),
        stop=scenario.stop_loss, stop_sources=tuple(scenario.stop_sources or ()),
        tolerance_pct=tolerance_pct, map_bar=map_bar,
        earnings_distance=fd.earnings_distance(
            calendar.position_on_or_before(signal), positions),
        confluence_count=fd.target_confluence_count(
            frame, i, plan.horizon_key, scenario.take_profit, tolerance_pct))


def ticker_rows(ticker, frame, positions, calendar, tolerance_pct,
                horizons=LEGACY_HORIZONS) -> tuple:
    """(FVG (bullish) trade rows, count of other triggered plans) for one
    ticker, signal dates inside TRAIN. The exit walk may run past the window,
    the run_backtest_range convention."""
    rows, others = [], 0
    context = (positions, calendar, tolerance_pct)
    for horizon_key in horizons:
        for i, plan, *captured in replay_with_scenarios(ticker, frame, horizon_key):
            if not fd.TRAIN[0] <= str(frame.index[i].date()) <= fd.TRAIN[1]:
                continue
            if plan.strategy != fd.STRATEGY:
                result = simulate_exit(frame, i, plan, scale_out=True)
                others += result.outcome not in fd.UNTRIGGERED
                continue
            row = fd.trade_row(frame, i, plan,
                               signal_context(frame, i, plan, captured, context))
            if row is not None:
                rows.append(row)
    return rows, others


def _worker(task) -> tuple:
    """One ticker, every horizon -- the process-pool entry point."""
    ticker, earnings_dir, tolerance_pct = task
    from measure_arms import load_frame
    from measure_earnings_blackout import load_calendar, reaction_positions
    from swingbot.core.marketdata import backtest_cache
    from swingbot.core.marketdata.universe import is_etf
    frame = load_frame(ticker)
    if frame is None:
        return ticker, [], 0
    calendar = load_calendar(backtest_cache.CACHE_DIR)
    positions = [] if is_etf(ticker) else reaction_positions(
        ticker, CsvSource(earnings_dir), calendar)
    rows, others = ticker_rows(ticker, frame, positions, calendar, tolerance_pct)
    return ticker, rows, others


def _write_progress(done, total) -> None:
    try:
        PROGRESS.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                            encoding="utf-8")
    except OSError:
        pass


def run_replay(universe, earnings_dir, workers=None) -> dict:
    """Replay `universe` and return {"rows", "other_triggered", "tickers",
    "confluence_tolerance_pct"}, rows in ticker order so the output is
    identical whatever order the pool finishes in."""
    tolerance_pct = float(ScanParams.from_config().confluence_deviation_pct)
    tasks = [(ticker, str(earnings_dir), tolerance_pct) for ticker in universe]
    LOG_DIR.mkdir(exist_ok=True)
    by_ticker: dict = {}

    def record(ticker, rows, others):
        by_ticker[ticker] = (rows, others)
        print(f"  [v143 {fd.TRAIN[0]}..{fd.TRAIN[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(rows)} FVG (bullish) trades, {others} other", flush=True)
        _write_progress(len(by_ticker), len(tasks))

    n_workers = bs._resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    PROGRESS.unlink(missing_ok=True)
    ordered = sorted(by_ticker)
    return {"rows": [row for ticker in ordered for row in by_ticker[ticker][0]],
            "other_triggered": sum(by_ticker[ticker][1] for ticker in ordered),
            "tickers": len(ordered), "confluence_tolerance_pct": tolerance_pct}


# --- CLI ---------------------------------------------------------------------

def rows_path(out_dir) -> Path:
    """The committed results directory never holds the rows file: a full run
    keeps it under logs/ (gitignored), a smoke run beside its scratch doc."""
    out_dir = Path(out_dir)
    return LOG_DIR / ROWS_NAME if out_dir.resolve() == RESULTS.resolve() else out_dir / ROWS_NAME


def doc_path(out_dir, run_date) -> Path:
    return Path(out_dir) / f"{run_date}-{DOC_SUFFIX}"


def _replay_refusal(args) -> str | None:
    if enabled_arms():
        return ("refused:acceptance-exit-enabled -- ACCEPTANCE_EXIT_ENABLED must be off: "
                "the baseline book is measured with today's exits")
    if not any(Path(args.earnings_dir).glob("*.csv")):
        return (f"refused:no-earnings -- no earnings CSVs in {args.earnings_dir}; "
                "pass --earnings-dir <main tree>/market_data/earnings")
    if rows_path(args.out_dir).exists():
        return (f"refused:already-run -- {rows_path(args.out_dir)} exists; the replay "
                "runs once. Re-render with --from-rows")
    return None


def cli_refusal(args) -> str | None:
    """Why this invocation must not run, or None."""
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if doc_path(args.out_dir, args.date).exists():
        return f"refused:already-written -- {doc_path(args.out_dir, args.date)} exists"
    if args.from_rows:
        return None if args.from_rows.exists() else f"refused:no-rows -- {args.from_rows} is missing"
    return _replay_refusal(args)


def load_or_replay(args) -> dict:
    """The saved rows (--from-rows) or one fresh replay, saved before rendering."""
    if args.from_rows:
        return json.loads(args.from_rows.read_text(encoding="utf-8"))
    from measure_acceptance_exits import cache_universe
    universe = cache_universe()
    blob = run_replay(universe[:args.tickers] if args.tickers else universe,
                      args.earnings_dir, args.workers)
    target = rows_path(args.out_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(blob), encoding="utf-8")
    return blob


def coverage_line(report) -> str:
    """Role split, open/filled split and every feature's computable share."""
    split = report["gap_split"]
    shares = ", ".join(f"{key} {cov['share'] * 100:.1f}%" + ("" if cov["tested"] else " NOT TESTED")
                       for key, cov in report["coverage"].items())
    return (f"coverage: unidentified={report['unidentified']} of {report['n']}; "
            f"role target={split['target']} stop={split['stop']}; "
            f"gap open={split['open']} filled={split['filled']}; computable: {shares}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--earnings-dir", type=Path, default=EARNINGS_CSV_DIR)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--from-rows", type=Path, default=None)
    args = parser.parse_args(argv)
    refusal = cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    blob = load_or_replay(args)
    rows = blob["rows"]
    print(f"population: N={len(rows)} FVG (bullish) of {len(rows) + blob['other_triggered']} "
          f"triggered confluence plans, {blob['tickers']} tickers "
          f"(expected {fd.EXPECTED_N} of {EXPECTED_ALL})", flush=True)
    if not args.tickers and not fd.population_ok(len(rows)):
        print(f"refused:population -- N={len(rows)} is more than 2% from {fd.EXPECTED_N}; "
              "the engine moved. No results document written.", file=sys.stderr)
        return 2
    report = fd.build_report(rows)
    print(coverage_line(report), flush=True)
    target = doc_path(args.out_dir, args.date)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fd.render(report, run_date=args.date, tickers=blob["tickers"],
                                tolerance_pct=blob.get("confluence_tolerance_pct")),
                      encoding="utf-8")
    print(f"v143: {len(report['candidates'])} candidate(s) of {len(report['cells'])} looks, "
          f"N={report['n']}, unidentified={report['unidentified']} -> {target}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
