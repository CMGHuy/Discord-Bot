#!/usr/bin/env python3
"""v245 Task 0: where one scan's analysis time goes (spec § Task 0 step 1).

Replays local daily frames through analyze._scan_one under cProfile, twice:
as stored (no forming bar) and with a forming bar synthesised from the last
row (OHLC = last close +/- 0.5 ATR14, live price = that close). Separate
tracemalloc passes give the analysis peak and the bytes of the object the
trendline prefix cache would hold. Shares only: the laptop is not the VM
under cpus: 1.0, so the 0.7 s target is judged from production phases_s.

    python scripts/perf/profile_analysis.py [--tickers AAPL,MSFT] [--horizons 2w,4w]
        [--max-bars 2515] [--journal] [--out logs/v245-profile/profile.json]

Tickers default to the local replica's watchlist (run /replicate-prod-db
first); frames come from training_data.load_daily (data/market_data/daily).
"""
from __future__ import annotations

import argparse
import cProfile
import functools
import importlib
import inspect
import json
import os
import pickle
import pstats
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from swingbot.core.scanning import analyze  # noqa: E402
from swingbot.core.market import trendlines as tl  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

PROD_BARS = 2515      # DEFAULT_HISTORY_PERIOD=10y at about 252 sessions a year
DEFAULT_OUT = os.path.join(ROOT, "logs", "v245-profile", "profile.json")
_SC, _MK, _MD = "swingbot.core.scanning.", "swingbot.core.market.", "swingbot.core.marketdata."

# (label, "module:function") -- spec § Task 0 step 2's candidates and the
# indicator functions under them.
CANDIDATES: tuple[tuple[str, str], ...] = (
    ("_scan_one", _SC + "analyze:_scan_one"),
    ("custom_scanner_levels", _MK + "trendlines:custom_scanner_levels"),
    ("_find_best_trendline", _MK + "trendlines:_find_best_trendline"),
    ("_volume_confirmed_pivots", _MK + "trendlines:_volume_confirmed_pivots"),
    ("zigzag_pivots", _MK + "indicators:zigzag_pivots"),
    ("_score_candidate", _MK + "trendlines:_score_candidate"),
    ("trendline_levels", _MK + "trendlines:trendline_levels"),
    ("_trendln_fallback_levels", _MK + "trendlines:_trendln_fallback_levels"),
    ("_horizon_scenarios", _SC + "analyze:_horizon_scenarios"),
    ("collect_candidate_levels", _MK + "levels:collect_candidate_levels"),
    ("_fvg_candidates", _MK + "levels:_fvg_candidates"),
    ("build_level_map", _MK + "levels:build_level_map"),
    ("_cluster_levels", _MK + "levels:_cluster_levels"),
    ("build_scenarios", _MK + "levels:build_scenarios"),
    ("atr_floor_pct", _MK + "levels:atr_floor_pct"),
    ("count_confirming_strategies", _MK + "levels:count_confirming_strategies"),
    ("score_confidence", _SC + "confidence:score_confidence"),
    ("_build_requirement_checks", _SC + "requirements:_build_requirement_checks"),
    ("get_htf_bias", _SC + "regime:get_htf_bias"),
    ("macro_aligned", _MK + "mtf:macro_aligned"),
    ("adjacent_aligned", _MK + "mtf:adjacent_aligned"),
    ("_rs_pctile", _SC + "analyze:_rs_pctile"),
    ("liquidity_reason (E12)", _MD + "universe:liquidity_reason"),
    ("data_quality_issues (E16)", _MD + "universe:data_quality_issues"),
    ("_apply_pullback_dryup", _SC + "analyze:_apply_pullback_dryup"),
    ("_apply_headroom", _SC + "analyze:_apply_headroom"),
    ("_band_live", _SC + "analyze:_band_live"),
    ("veto_bullish_for", _SC + "analyze:veto_bullish_for"),
    ("track_record (journal)", _SC + "analyze:_live_track_record"),
    ("ema", _MK + "indicators:ema"),
    ("atr", _MK + "indicators:atr"),
    ("rolling_vwap", _MK + "indicators:rolling_vwap"),
    ("fibonacci_levels", _MK + "indicators:fibonacci_levels"),
    ("bollinger_bands", _MK + "volatility:bollinger_bands"),
)


def _no_monitor(ticker, df, price=None):
    return [], []


QUIET_IO = analyze.ScanIO(lambda: False, _no_monitor, _no_monitor, lambda base_level: (None, 0))
JOURNAL_IO = analyze.ScanIO(lambda: False, _no_monitor, _no_monitor, analyze._live_track_record)


def resolve(target: str):
    module, _, name = target.partition(":")
    return inspect.unwrap(getattr(importlib.import_module(module), name))


def _code_key(fn) -> tuple:
    code = fn.__code__
    return os.path.normcase(code.co_filename), code.co_firstlineno, code.co_name


def synth_forming_bar(df: pd.DataFrame, atr_mult: float = 0.5) -> pd.DataFrame:
    """`df` plus one forming bar: next business day, last close +/- atr_mult x ATR14."""
    from swingbot.core.market.indicators import atr
    close = float(df["Close"].iloc[-1])
    half = float(atr(df, 14).iloc[-1]) * atr_mult
    half = 0.0 if half != half else half          # NaN ATR on a short frame: a flat bar
    row = df.iloc[[-1]].copy()
    row.index = pd.DatetimeIndex([df.index[-1] + pd.offsets.BDay(1)], name=df.index.name)
    row["Open"], row["High"], row["Low"], row["Close"] = close, close + half, close - half, close
    return pd.concat([df, row])


def load_frames(tickers: list[str]) -> dict[str, pd.DataFrame]:
    from swingbot.core.marketdata import training_data
    frames = {}
    for ticker in tickers:
        df = training_data.load_daily(ticker)
        if df is not None and len(df):
            frames[ticker] = df
    return frames


def profile_scan(frames: dict, horizons: list[str], *, forming: bool,
                 io=QUIET_IO) -> tuple[pstats.Stats, float]:
    inputs = {t: synth_forming_bar(df) if forming else df for t, df in frames.items()}
    live = {t: float(df["Close"].iloc[-1]) for t, df in inputs.items()} if forming else None
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    try:
        for ticker, df in inputs.items():
            analyze._scan_one(ticker, df, list(horizons), None, None, 0, 0,
                              live_prices=live, io=io)
    finally:
        profiler.disable()
    return pstats.Stats(profiler), time.perf_counter() - started


def candidate_shares(stats: pstats.Stats, total_s: float) -> list[dict]:
    index = {(os.path.normcase(f), line, name): row for (f, line, name), row in stats.stats.items()}
    out = []
    for label, target in CANDIDATES:
        row = index.get(_code_key(resolve(target)))
        calls, cum_s = (row[1], row[3]) if row else (0, 0.0)
        out.append({"label": label, "target": target, "calls": calls, "cum_s": round(cum_s, 4),
                    "share": round(cum_s / total_s, 4) if total_s > 0 else 0.0})
    return sorted(out, key=lambda r: r["cum_s"], reverse=True)


def object_bytes(obj) -> int:
    return len(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def traced_build(build) -> tuple[object, int]:
    """`build()` and the bytes it allocated that are still alive afterwards."""
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        obj = build()
        retained = tracemalloc.get_traced_memory()[0] - base
    finally:
        tracemalloc.stop()
    return obj, retained


def _touches(slope: float, intercept: float, pivots: tuple) -> tuple:
    out = []
    for bar, price, vol in pivots:
        line = slope * bar + intercept
        if line > 0 and abs(price - line) / line * 100 <= tl.TOUCH_TOLERANCE_PCT:
            out.append((bar, price, vol))
    return tuple(out)


def trendline_prefix_estimate(df: pd.DataFrame, side: str) -> tuple:
    """(side, m, confirmed pivots, pairs): the shape V245-8's TrendlinePrefix holds."""
    trimmed = df.tail(tl.MAX_PIVOT_SCAN_BARS).iloc[:-1]
    pivots = tuple(tl._volume_confirmed_pivots(trimmed, "low" if side == "support" else "high"))
    pairs = []
    for i, (x0, y0, _) in enumerate(pivots):
        row = []
        for x1, y1, _ in pivots[i + 1:]:
            if x1 == x0 or y0 <= 0 or y1 <= 0:
                row.append(None)
                continue
            slope = (y1 - y0) / (x1 - x0)
            intercept = y0 - slope * x0
            row.append((slope, intercept, _touches(slope, intercept, pivots)))
        pairs.append(tuple(row))
    return side, len(trimmed), pivots, tuple(pairs)


def _dist(values: list) -> dict:
    if not values:
        return {"median": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"median": statistics.median(ordered), "p95": p95, "max": ordered[-1]}


def _per_ticker_bytes(frames: dict) -> dict:
    per_ticker = {}
    for ticker, df in frames.items():
        row = {"pickled": 0, "retained": 0, "pivots": {}}
        for side in ("support", "resistance"):
            obj, retained = traced_build(functools.partial(trendline_prefix_estimate, df, side))
            row["pickled"] += object_bytes(obj)
            row["retained"] += retained
            row["pivots"][side] = len(obj[2])
        per_ticker[ticker] = row
    return per_ticker


def _analysis_peak_mb(frames: dict, horizons: list[str], io) -> float:
    tracemalloc.start()
    try:
        for ticker, df in frames.items():
            analyze._scan_one(ticker, df, list(horizons), None, None, 0, 0, io=io)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return round(peak / 1e6, 2)


def _run(frames: dict, horizons: list[str], *, forming: bool, io, prof_stem: str) -> dict:
    stats, total_s = profile_scan(frames, horizons, forming=forming, io=io)
    stats.dump_stats(f"{prof_stem}-{'forming' if forming else 'completed'}.prof")
    return {"total_s": round(total_s, 3), "per_ticker_s": round(total_s / max(len(frames), 1), 4),
            "candidates": candidate_shares(stats, total_s)}


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="v245 analysis profiler (shares only)")
    parser.add_argument("--tickers", help="comma-separated; default: the local replica's watchlist")
    parser.add_argument("--horizons", default=",".join(LEGACY_HORIZONS))
    parser.add_argument("--max-bars", type=int, default=PROD_BARS)
    parser.add_argument("--journal", action="store_true",
                        help="read the confidence track record from the local journal (read-only)")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def _tickers(arg: str | None) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    from swingbot.core.marketdata.watchlist import load_watchlist
    return [t.upper() for t in load_watchlist()]


def _print_summary(report: dict, out: str) -> None:
    print(f"{report['tickers']} tickers ({len(report['missing'])} without a local frame) -> {out}")
    for name, run in report["runs"].items():
        print(f"  {name}: {run['per_ticker_s']} s/ticker")
        for row in run["candidates"][:12]:
            print(f"    {row['share']:7.2%}  {row['calls']:7d}  {row['label']}")


def _memory(frames: dict, horizons: list[str], io) -> dict:
    per_ticker = _per_ticker_bytes(frames)
    return {"analysis_peak_mb": _analysis_peak_mb(frames, horizons, io),
            "trendline_bytes_per_ticker": {
                "pickled": _dist([r["pickled"] for r in per_ticker.values()]),
                "retained": _dist([r["retained"] for r in per_ticker.values()])},
            "per_ticker": per_ticker}


def main(argv=None) -> int:
    args = _parse(argv)
    tickers = _tickers(args.tickers)
    frames = {t: df.tail(args.max_bars) for t, df in load_frames(tickers).items()}
    if not frames:
        print("no local frames for any ticker (data/market_data/daily)", file=sys.stderr)
        return 1
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    io = JOURNAL_IO if args.journal else QUIET_IO
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    stem = os.path.splitext(out)[0]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": len(frames), "missing": sorted(set(tickers) - set(frames)),
        "bars": _dist([len(df) for df in frames.values()]), "horizons": horizons,
        "journal": args.journal,
        "runs": {"completed": _run(frames, horizons, forming=False, io=io, prof_stem=stem),
                 "forming": _run(frames, horizons, forming=True, io=io, prof_stem=stem)},
        "memory": _memory(frames, horizons, io),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    _print_summary(report, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
