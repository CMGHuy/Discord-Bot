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

import cProfile
import importlib
import inspect
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from swingbot.core.scanning import analyze  # noqa: E402

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
