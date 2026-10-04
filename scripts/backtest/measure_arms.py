#!/usr/bin/env python3
"""Produce stamped baseline/component replay arms for the v100 funnel."""
from __future__ import annotations

import argparse
import dataclasses
import json
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

LOG_DIR = ROOT / "logs"


def cached_universe() -> list[str]:
    from swingbot.core.marketdata.backtest_cache import cache_path
    from run_backtest_range import _tickers_for_run
    return sorted(ticker for ticker in _tickers_for_run(None) if cache_path(ticker).exists())


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
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    return [trade for ticker in sorted(by_ticker) for trade in by_ticker[ticker]]


def _rows(trades, start, end):
    return [dataclasses.asdict(trade) for trade in trades if start <= trade.entry_date <= end]


def population_symbols() -> list[str]:
    """v118: every symbol a whole-scan replay may need -- the cached universe, the
    point-in-time S&P 500 members that have a cached frame, the benchmark and the
    sector ETFs. A member with no cached frame is simply absent (counted by the
    replay as missing_frame): Yahoo keeps no history for most delisted names."""
    from swingbot import config
    from swingbot.core.marketdata import universe as universe_mod
    from swingbot.core.marketdata.backtest_cache import cache_path
    from swingbot.core.marketdata.pit_membership import load_intervals
    members = load_intervals(str(Path(universe_mod.UNIVERSE_DIR) / "sp500_membership.csv"))
    etfs = universe_mod.sector_map("etfs")
    wanted = set(cached_universe()) | set(members) | set(etfs) | {config.MARKET_REGIME_TICKER}
    return sorted(symbol for symbol in wanted if cache_path(symbol).exists())


def _population_arm(engine_id, frames, universe, horizons, window, delta) -> list:
    """One arm of a population engine, its config delta applied for the whole pass."""
    from swingbot import config
    from swingbot.scan_params import ScanParams
    with apply_knobs(delta):
        params = ScanParams.from_config()
        engine = get_population_engine(engine_id, base_tickers=universe, horizons=horizons)
        return engine.run_population(frames, window, params, mode=config.SHORT_UNIVERSE_RESEARCH_MODE)


def _produce_population(engine_id, universe, horizons, signal_window, delta) -> tuple:
    """Load each frame once, then baseline (the knob at its default, i.e. off) and
    component (the knob applied) over the identical frames. One process: the
    replay is cross-sectional per decision date, not per ticker."""
    frames = {symbol: frame for symbol in population_symbols()
              if (frame := load_frame(symbol)) is not None}
    baseline_hash = code_hash()
    baseline = _population_arm(engine_id, frames, universe, horizons, signal_window, {})
    print(f"  [baseline] {len(baseline)} trades", flush=True)
    component_hash = code_hash()
    component = _population_arm(engine_id, frames, universe, horizons, signal_window, delta)
    print(f"  [component] {len(component)} trades", flush=True)
    return baseline_hash, baseline, component_hash, component


def produce(stage, delta, *, universe, spec=None, horizons=None, engines=DEFAULT_ENGINES,
            workers=None, progress_path=None, preregistration=None) -> dict:
    spec = spec or windows.resolve(stage)
    horizons = tuple(horizons or windows.ALL_HORIZONS)
    population = population_engine_for(delta)
    if population is not None:
        engines = (population,)
        baseline_hash, baseline, component_hash, component = _produce_population(
            population, universe, horizons, spec.signal_window, delta)
    else:
        workers = _resolve_replay_workers(workers)
        total, counter = 2 * len(universe), [0]
        baseline_hash = code_hash()
        baseline = _run_arm_all("baseline", universe, engines, horizons, spec.signal_window, {}, workers, progress_path, counter, total)
        component_hash = code_hash()
        component = _run_arm_all("component", universe, engines, horizons, spec.signal_window, delta, workers, progress_path, counter, total)
    stamp = build_stamp(stage=stage, signal_window=spec.signal_window, universe=universe, horizons=horizons,
                        engines=engines, knob_delta=delta, engine_hash_baseline=baseline_hash,
                        engine_hash_component=component_hash, changed_outcomes=changed_outcomes(baseline, component),
                        preregistration=preregistration)
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


def _write_sidecar(out: Path, sidecar) -> None:
    if sidecar is not None:
        out.with_name(f"{out.stem}.diagnostics.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _write_sidecar_or_warn(out: Path, blob, delta, universe, spec) -> None:
    """The sidecar is diagnostics only: a failure here warns and never pre-empts the zero-diff refusal
    (or turns a spent one-shot stage into a traceback that invites a re-run)."""
    try:
        _write_sidecar(out, compression_sidecar(blob, delta, universe, spec))
    except Exception as exc:    # noqa: BLE001
        print(f"warning: diagnostics sidecar not written ({type(exc).__name__}: {exc}); the arm file is intact.",
              file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knob", action="append", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(windows.STAGES))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--preregistration", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        delta = dict(parse_knob(knob) for knob in args.knob)
    except ValueError as exc:
        unknown = next((knob.partition("=")[0] for knob in args.knob if reachability.classify(knob.partition("=")[0]) == reachability.UNCLASSIFIED), None)
        print(f"{'refused:unreachable:unclassified' if unknown else 'refused:bad-knob'} -- {exc}", file=sys.stderr)
        return 1
    refusal = static_refusal(delta) or population_refusal(delta)
    if refusal:
        print(f"{refusal[0]} -- {refusal[1]} Budget intact.", file=sys.stderr)
        return 1
    if args.stage == "validation" and not (args.preregistration and args.preregistration.exists()):
        print("refused:no-preregistration -- --stage validation needs --preregistration <committed doc>. This is the one shot.", file=sys.stderr)
        return 1
    universe = windows.universe_for(args.stage, cached_universe())
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_arms.{uuid.uuid4().hex[:8]}.progress"
    blob = produce(args.stage, delta, universe=universe, workers=args.workers, progress_path=progress,
                   preregistration=str(args.preregistration) if args.preregistration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob), encoding="utf-8")
    _write_sidecar_or_warn(args.out, blob, delta, universe, windows.resolve(args.stage))
    if args.stage == "pilot" and blob["provenance"]["changed_outcomes"] == 0:
        print("refused:zero-diff -- the component changed no trade on the pilot slice. Budget intact.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
