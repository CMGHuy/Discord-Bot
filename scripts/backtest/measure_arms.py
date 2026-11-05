#!/usr/bin/env python3
"""Produce stamped baseline/component replay arms for the v100 funnel.

v147: `--record-blocked PATH [--from --to]` writes TRAIN compression gate rows instead (see `record_blocked_main`).
v180: --knob TURTLE_SOUP_RESEARCH_MODE=structural also writes <out stem>.turtle_soup.json (see turtle_soup_sidecar).
v192: --baseline-knob ATTR=value runs the BASELINE arm under its own delta (stamped as baseline_knob_delta).
v192: --knob GAP_RECLAIM_ATR=g (> 0) also writes <out stem>.gap_reclaim.json, the census (see gap_reclaim_sidecar).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting.arms import reachability, windows  # noqa: E402
from swingbot.core.backtesting.arms.engine import (DEFAULT_ENGINES, get_population_engine,  # noqa: E402
                                                   population_engine_for, run_arm)
from swingbot.core.backtesting.arms.knobs import apply_knobs, parse_knob  # noqa: E402
from swingbot.core.backtesting.arms.pairing import changed_outcomes  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp, code_hash  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

LOG_DIR = ROOT / "logs"


#: v139: where the arm universe comes from. "watchlist" (the default, unchanged)
#: is the Postgres watchlist filtered to cached frames. "cache" is every ticker
#: the training data holds (v162: training_data.available_tickers()), for a worktree where Postgres is unreachable
#: (the v129 precedent, partner-approved 2026-10-08). The stamp records the list
#: either way, and validate_component / permutation_test call this same function,
#: so a producer run and its judge agree.
UNIVERSE_ENV = "MEASURE_ARMS_UNIVERSE"
UNIVERSE_SOURCES = ("watchlist", "cache")


def cache_listing() -> list[str]:
    """Every ticker the selected training data holds, sorted (v162). Under
    yfinance that is the CSV stems of backtest_cache.CACHE_DIR, as before."""
    return training_data.available_tickers()


def _available() -> set[str]:
    return set(training_data.available_tickers())


def _in_training_data(symbol: str, available: set[str]) -> bool:
    """A ticker, or its yfinance file stem (=, ^ and / become _), is served."""
    from swingbot.core.marketdata.backtest_cache import cache_path
    return symbol in available or cache_path(symbol).stem in available


def cached_universe() -> list[str]:
    source = (os.environ.get(UNIVERSE_ENV) or "watchlist").strip().lower()
    if source not in UNIVERSE_SOURCES:
        raise ValueError(f"{UNIVERSE_ENV} must be one of {UNIVERSE_SOURCES}, got {source!r}")
    if source == "cache":
        return cache_listing()
    from run_backtest_range import _tickers_for_run
    available = _available()
    return sorted(ticker for ticker in _tickers_for_run(None) if _in_training_data(ticker, available))


def load_frame(ticker):
    from fetch_backtest_data import load_cached
    return load_cached(ticker)


def static_refusal(delta: dict):
    for attr in delta:
        classification = reachability.classify(attr)
        if classification != reachability.REACHABLE:
            return f"refused:unreachable:{classification}", reachability.reason(attr)
    return None


def population_refusal(delta: dict):
    """A knob only a whole-scan engine observes is refused when that engine is absent."""
    engine_id = population_engine_for(delta)
    if engine_id is None:
        return None
    try:
        get_population_engine(engine_id)
    except (KeyError, ImportError) as exc:
        return "refused:no-population-engine", f"{engine_id} is not available ({exc!r})."
    return None


def _baseline_population_refusal(delta: dict, baseline_delta: dict):
    """v192: the population path runs the baseline under the component's engine, so a baseline
    delta that would route to a different whole-scan engine cannot be honoured."""
    engine_id = population_engine_for(baseline_delta)
    if engine_id is None or engine_id == population_engine_for(delta):
        return None
    return "refused:baseline-population-mismatch", (
        f"the baseline delta routes to {engine_id}, the component to {population_engine_for(delta)}.")


def _refusal(delta: dict, baseline_delta: dict):
    """The first static or population refusal over the component delta, then the baseline delta."""
    return (static_refusal(delta) or population_refusal(delta) or static_refusal(baseline_delta)
            or population_refusal(baseline_delta) or _baseline_population_refusal(delta, baseline_delta))


def _unclassified(knobs) -> str | None:
    return next((knob.partition("=")[0] for knob in knobs
                 if reachability.classify(knob.partition("=")[0]) == reachability.UNCLASSIFIED), None)


def _deltas(args):
    """(component delta, baseline delta) parsed from --knob / --baseline-knob, or exit code 1 with
    the refusal on stderr when a knob is unknown or its value does not cast."""
    try:
        delta = dict(parse_knob(knob) for knob in args.knob)
        baseline_delta = dict(parse_knob(knob) for knob in args.baseline_knob)
    except ValueError as exc:
        unknown = _unclassified([*args.knob, *args.baseline_knob])
        print(f"{'refused:unreachable:unclassified' if unknown else 'refused:bad-knob'} -- {exc}", file=sys.stderr)
        return 1
    return delta, baseline_delta


def _worker(task):
    ticker, engine_ids, horizons, signal_window, delta = task
    try:
        frame = load_frame(ticker)
        if frame is None:
            raise RuntimeError("no cached frame")
        trades = run_arm(ticker, frame, engine_ids, horizons, signal_window, delta)
    except Exception as exc:
        raise RuntimeError(f"{ticker}: {exc!r}") from exc
    return ticker, trades


def _write_progress(path, done, total):
    if path is not None:
        try:
            Path(path).write_text(f"{done}/{total} ticker-arms ({done / total * 100:.0f}%)\n", encoding="utf-8")
        except OSError:
            pass


def _run_arm_all(label, universe, engines, horizons, signal_window, delta, workers, progress_path, counter, total):
    tasks = [(ticker, tuple(engines), tuple(horizons), signal_window, delta) for ticker in universe]
    by_ticker = {}

    def record(ticker, trades):
        by_ticker[ticker] = trades
        counter[0] += 1
        print(f"  [{label}] {counter[0]}/{total} {ticker}: {len(trades)} trades", flush=True)
        _write_progress(progress_path, counter[0], total)

    if workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=training_data.select,
                                 initargs=training_data.selection_args()) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    return [trade for ticker in sorted(by_ticker) for trade in by_ticker[ticker]]


def _rows(trades, start, end):
    return [dataclasses.asdict(trade) for trade in trades if start <= trade.entry_date <= end]


def population_symbols() -> list[str]:
    """v118: every symbol a whole-scan replay may need -- the cached universe, the
    point-in-time S&P 500 members that the training data holds, the benchmark and the
    sector ETFs. A member with no cached frame is simply absent (counted by the
    replay as missing_frame): Yahoo keeps no history for most delisted names."""
    from swingbot import config
    from swingbot.core.marketdata import universe as universe_mod
    from swingbot.core.marketdata.pit_membership import load_intervals
    members = load_intervals(str(Path(universe_mod.UNIVERSE_DIR) / "sp500_membership.csv"))
    etfs = universe_mod.sector_map("etfs")
    wanted = set(cached_universe()) | set(members) | set(etfs) | {config.MARKET_REGIME_TICKER}
    available = _available()
    return sorted(symbol for symbol in wanted if _in_training_data(symbol, available))


def _population_arm(engine_id, frames, universe, horizons, window, delta) -> list:
    """One arm of a population engine, its config delta applied for the whole pass."""
    from swingbot import config
    from swingbot.scan_params import ScanParams
    with apply_knobs(delta):
        params = ScanParams.from_config()
        engine = get_population_engine(engine_id, base_tickers=universe, horizons=horizons)
        return engine.run_population(frames, window, params, mode=config.SHORT_UNIVERSE_RESEARCH_MODE)


def _produce_population(engine_id, universe, horizons, signal_window, delta, baseline_delta=None) -> tuple:
    """Load each frame once, then baseline (``baseline_delta``, by default none: the knob off) and
    component (the knob applied) over the identical frames. One process: the
    replay is cross-sectional per decision date, not per ticker."""
    frames = {symbol: frame for symbol in population_symbols()
              if (frame := load_frame(symbol)) is not None}
    baseline_hash = code_hash()
    baseline = _population_arm(engine_id, frames, universe, horizons, signal_window, dict(baseline_delta or {}))
    print(f"  [baseline] {len(baseline)} trades", flush=True)
    component_hash = code_hash()
    component = _population_arm(engine_id, frames, universe, horizons, signal_window, delta)
    print(f"  [component] {len(component)} trades", flush=True)
    return baseline_hash, baseline, component_hash, component


def produce(stage, delta, *, universe, baseline_delta=None, spec=None, horizons=None, engines=DEFAULT_ENGINES,
            workers=None, progress_path=None, preregistration=None) -> dict:
    """v192: ``baseline_delta`` is the baseline arm's own config delta (default none, today's
    baseline); the stamp records it as ``baseline_knob_delta`` when non-empty."""
    spec = spec or windows.resolve(stage)
    horizons = tuple(horizons or windows.ALL_HORIZONS)
    baseline_delta = dict(baseline_delta or {})
    population = population_engine_for(delta)
    if population is not None:
        engines = (population,)
        baseline_hash, baseline, component_hash, component = _produce_population(
            population, universe, horizons, spec.signal_window, delta, baseline_delta)
    else:
        workers = _resolve_replay_workers(workers)
        total, counter = 2 * len(universe), [0]
        baseline_hash = code_hash()
        baseline = _run_arm_all("baseline", universe, engines, horizons, spec.signal_window, baseline_delta, workers, progress_path, counter, total)
        component_hash = code_hash()
        component = _run_arm_all("component", universe, engines, horizons, spec.signal_window, delta, workers, progress_path, counter, total)
    stamp = build_stamp(stage=stage, signal_window=spec.signal_window, universe=universe, horizons=horizons,
                        engines=engines, knob_delta=delta, engine_hash_baseline=baseline_hash,
                        engine_hash_component=component_hash, changed_outcomes=changed_outcomes(baseline, component),
                        preregistration=preregistration, baseline_knob_delta=baseline_delta)
    blob: dict = {"provenance": stamp}
    if spec.fold_key != "folds":
        blob["baseline"], blob["component"] = _rows(baseline, *spec.signal_window), _rows(component, *spec.signal_window)
    if spec.folds:
        blob[spec.fold_key] = [{spec.fold_label_key: label, "baseline": _rows(baseline, start, end),
                                "component": _rows(component, start, end)} for label, start, end in spec.folds]
    if progress_path is not None:
        Path(progress_path).unlink(missing_ok=True)
    return blob


COMPRESSION_KNOB = "COMPRESSION_SHORT_RESEARCH_MODE"


def compression_sidecar(blob, delta, universe, spec) -> dict | None:
    """v119: the compression short's per-mode diagnostics for this run (signal/entry/exit dates, mode,
    excluded candidates with reasons, exit reasons, daily_close_proxy label), replayed through the same
    StrategyEngine and offline as-of context the component arm used. None without the knob. The stamped
    arm rows are never touched; this is written beside them."""
    mode = delta.get(COMPRESSION_KNOB)
    if mode in (None, "off"):
        return None
    from swingbot.core.backtesting.arms import compression_research as cr
    frames = {ticker: frame for ticker in universe if (frame := load_frame(ticker)) is not None}
    measured = cr.measure_compression_short(frames, spec.signal_window, mode=mode, context=cr.offline_context())
    return cr.sidecar_record(measured, signal_window=spec.signal_window, universe=universe,
                             component_rows=blob.get("component"))


TURTLE_SOUP_KNOB = "TURTLE_SOUP_RESEARCH_MODE"


def _sp500_intervals() -> dict:
    """The PIT S&P 500 membership spans; {} when the file is missing (the universe block then says None)."""
    from swingbot.core.marketdata import universe as universe_mod
    from swingbot.core.marketdata.pit_membership import load_intervals
    return load_intervals(str(Path(universe_mod.UNIVERSE_DIR) / "sp500_membership.csv"))


def _component_and_spans(blob, spec) -> tuple[list, list]:
    """The stamped component rows and the signal spans they cover: the whole window, or each fold."""
    if "component" in blob:
        return blob["component"], [tuple(spec.signal_window)]
    component = [row for fold in blob.get(spec.fold_key) or [] for row in fold["component"]]
    return component, [(start, end) for _, start, end in spec.folds]


def _matches_component_rows(rows, blob, spec) -> bool:
    """The sidecar's trades are exactly the stamped component's Turtle Soup rows, by (ticker, signal date)."""
    from swingbot.core.market.strategy_types import TURTLE_SOUP
    component, spans = _component_and_spans(blob, spec)
    stamped = sorted((r["ticker"], r["entry_date"]) for r in component if r["strategy"] == TURTLE_SOUP)
    traded = sorted((r["ticker"], r["signal_date"]) for r in rows
                    if r["status"] == "trade" and any(s <= r["signal_date"] <= e for s, e in spans))
    return stamped == traded


def turtle_soup_sidecar(blob, delta, universe, spec) -> dict | None:
    """v180's descriptive Turtle Soup diagnostics, replayed through a Turtle-Soup-only StrategyEngine under
    the same delta. The stamped arm rows are never touched. None without the knob."""
    if delta.get(TURTLE_SOUP_KNOB) in (None, "off"):
        return None
    from swingbot import config
    from swingbot.core.backtesting.arms import turtle_soup_report
    from swingbot.scan_params import ScanParams
    frames = {ticker: frame for ticker in universe if (frame := load_frame(ticker)) is not None}
    spy = load_frame(config.MARKET_REGIME_TICKER)
    with apply_knobs(delta):
        measured = turtle_soup_report.measure(frames, spec.signal_window, ScanParams.from_config(),
                                              spy=spy, intervals=_sp500_intervals())
    return {**measured, "knob_delta": dict(delta), "universe_count": len(universe),
            "matches_component_rows": _matches_component_rows(measured["rows"], blob, spec)}


GAP_RECLAIM_KNOB = "GAP_RECLAIM_ATR"


def gap_reclaim_sidecar(blob, delta, universe, spec) -> dict | None:
    """v192: every next-open market decision of the component arm (the census), replayed under
    the same delta. None unless the component sets GAP_RECLAIM_ATR > 0 (the next-open basis run
    has nothing to label). The stamped arm rows are never touched."""
    if not float(delta.get(GAP_RECLAIM_KNOB) or 0.0) > 0.0:
        return None
    from swingbot.core.backtesting.arms import gap_reclaim_census as grc
    stamp = blob.get("provenance") or {}
    rows = grc.census(universe, stamp.get("engines") or DEFAULT_ENGINES,
                      stamp.get("horizons") or windows.ALL_HORIZONS, tuple(spec.signal_window), delta,
                      workers=_resolve_replay_workers(None))
    component, _ = _component_and_spans(blob, spec)
    stamped = {grc.row_key(dict(row, signal_date=row["entry_date"])) for row in component}
    repriced = grc.repriced_keys(rows)
    return {"knob_delta": dict(delta), "baseline_knob_delta": stamp.get("baseline_knob_delta") or {},
            "signal_window": list(spec.signal_window), "universe_count": len(universe),
            "summary": grc.reachability_summary(rows),
            "repriced_in_component": len(repriced & stamped),
            "repriced_absent_from_component": len(repriced - stamped), "rows": rows}


#: (file suffix, builder name) per sidecar; looked up by name so a test can monkeypatch the builder.
#: "gap_reclaim" is gap_reclaim_census.SIDECAR_SUFFIX (pinned by test_gap_reclaim_census.py).
_SIDECARS = (("diagnostics", "compression_sidecar"), ("turtle_soup", "turtle_soup_sidecar"),
             ("gap_reclaim", "gap_reclaim_sidecar"))


def _write_sidecar(out: Path, sidecar, suffix: str = "diagnostics") -> None:
    if sidecar is not None:
        out.with_name(f"{out.stem}.{suffix}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _write_sidecar_or_warn(out: Path, blob, delta, universe, spec) -> None:
    """Each sidecar is diagnostics only: a failure here warns and never pre-empts the zero-diff refusal
    (or turns a spent one-shot stage into a traceback that invites a re-run)."""
    for suffix, builder in _SIDECARS:
        try:
            sidecar = globals()[builder](blob, delta, universe, spec)
            if sidecar is not None:
                _write_sidecar(out, sidecar, suffix)
        except Exception as exc:    # noqa: BLE001
            print(f"warning: {suffix} sidecar not written ({type(exc).__name__}: {exc}); the arm file is intact.",
                  file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knob", action="append", required=True)
    parser.add_argument("--baseline-knob", action="append", default=[],
                        help="v192: ATTR=value the BASELINE arm runs under (repeatable; default none)")
    parser.add_argument("--stage", required=True, choices=sorted(windows.STAGES))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--preregistration", type=Path, default=None)
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    add_data_source_arg(parser)
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_arms.py",
                              "phase 5 (v2 stage table)")
    apply_data_source(args)
    deltas = _deltas(args)
    if isinstance(deltas, int):
        return deltas
    delta, baseline_delta = deltas
    refusal = _refusal(delta, baseline_delta)
    if refusal:
        print(f"{refusal[0]} -- {refusal[1]} Budget intact.", file=sys.stderr)
        return 1
    if args.stage == "validation" and not (args.preregistration and args.preregistration.exists()):
        print("refused:no-preregistration -- --stage validation needs --preregistration <committed doc>. This is the one shot.", file=sys.stderr)
        return 1
    universe = windows.universe_for(args.stage, cached_universe())
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_arms.{uuid.uuid4().hex[:8]}.progress"
    blob = produce(args.stage, delta, universe=universe, baseline_delta=baseline_delta, workers=args.workers,
                   progress_path=progress, preregistration=str(args.preregistration) if args.preregistration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob), encoding="utf-8")
    training_data.write_provenance(args.out)
    _write_sidecar_or_warn(args.out, blob, delta, universe, windows.resolve(args.stage))
    if args.stage == "pilot" and blob["provenance"]["changed_outcomes"] == 0:
        print("refused:zero-diff -- the component changed no trade on the pilot slice. Budget intact.", file=sys.stderr)
        return 1
    return 0


def record_blocked_main(argv) -> int:
    """v147: TRAIN compression gate rows (blocked + taken) through StrategyEngine, one JSONL file.

    TRAIN window only (2020-01-01..2023-12-31); bars come from the backtest cache via `load_frame`.
    Flushed per-ticker progress; refusals exit 2 before any data is read."""
    from swingbot.core.backtesting.arms import compression_research as cr
    from swingbot.core.backtesting.blocked_recorder import TRAIN_WINDOW, require_train_window, write_gate_rows
    parser = argparse.ArgumentParser(description="v147: TRAIN compression gate rows through StrategyEngine")
    parser.add_argument("--record-blocked", dest="record_blocked", required=True, type=Path)
    parser.add_argument("--from", dest="date_from", default=TRAIN_WINDOW[0])
    parser.add_argument("--to", dest="date_to", default=TRAIN_WINDOW[1])
    parser.add_argument("--validation", action="store_true", help="refused: --record-blocked is TRAIN-only")
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_arms.py --record-blocked",
                              "phase 5 (scan replay under v2)")
    require_train_window(args.date_from, args.date_to, validation=args.validation)
    context = cr.offline_context()
    universe = cached_universe()
    rows: list = []
    for done, ticker in enumerate(universe, 1):
        frame = load_frame(ticker)
        if frame is not None:
            rows.extend(cr.record_blocked_compression({ticker: frame}, (args.date_from, args.date_to),
                                                      context=context))
        print(f"  [record-blocked] {done}/{len(universe)} ({done * 100 // len(universe)}%) {ticker}: "
              f"{len(rows)} rows", flush=True)
    args.record_blocked.parent.mkdir(parents=True, exist_ok=True)
    count = write_gate_rows(rows, args.record_blocked)
    print(f"Wrote {count} compression gate rows to {args.record_blocked}", flush=True)
    return 0


def cli(argv=None) -> int:
    """Script entry: `--record-blocked` dispatches before `main` parses its required arm flags."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg.split("=", 1)[0] == "--record-blocked" for arg in argv):
        return record_blocked_main(argv)
    return main(argv)


if __name__ == "__main__":
    sys.exit(cli())
