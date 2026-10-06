#!/usr/bin/env python3
"""v124: Fibonacci impulse-leg anchor diagnostic -- read-only.

Spec: docs/superpowers/specs/2026-10-02-v124-fib-impulse-leg-diagnostic-design.md
Extended cache only: run with BACKTEST_CACHE_DIR=data/backtest_cache_ext.

Two windows. The diagnostic reads entries 2015-01-01..2025-12-31 (DIAG_WINDOW,
partner decision 2026-10-02); a trade still open at 2025-12-31 may resolve on
2026 bars (outcome resolution only). First, the v103 reference arm is
re-collected on its own window 2010-01-01..2023-12-31 (REPRO_WINDOW) to prove
the instrument matches v103; the 2015/2025 bounds do not apply to that check.
2026 is the holdout. No VALIDATION budget is spent.

It measures whether each of four Fibonacci-handbook claims shows any signal
in the bot's own trades. It gates nothing. Each arm has one primary split,
fixed in the spec, and an exit rule (EXIT_RULE) that decides only whether the
arm earns its own spec.

Commands (from the repo root):
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-repro --direction bullish --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-fib --direction bullish --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-confluence --tickers A,B,C --out <json>
  python scripts/backtest/measure_fib_anchor_diagnostic.py reproduce --repro <bull json> <bear json>
  python scripts/backtest/measure_fib_anchor_diagnostic.py report --repro <bull> <bear> --fib <bull> <bear> \\
      --confluence <json> [<json> ...] --out <json> --md <md> [--reproduction-note <md>]
"""
from __future__ import annotations

import argparse
import collections
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from funnel import MIN_N_TRAIN, dir_rows, pooled  # noqa: E402
from measure_fib_confluence import TRAIN_EXT, Progress, _load_frames, _write, require_ext_cache  # noqa: E402
import pandas as pd  # noqa: E402

import measure_fib_v103  # noqa: E402
from measure_fib_diagnostic import fib_level, tested_ratio  # noqa: E402
from run_backtest_range import _build_asof_map  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.market.fib_leg import leg_at, origin_strength  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.market.levels import collect_candidate_levels, strategy_family  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.market.structure import PIVOT_K, pivot_confirmations  # noqa: E402

DIRECTIONS = ("bullish", "bearish")
DIAG_WINDOW = ("2015-01-01", "2025-12-31")   # entries + features (partner decision, 2026-10-02)
REPRO_WINDOW = TRAIN_EXT                     # v103's own window, for the reproduction check only
# --- frozen in the spec ---
TOL_ATR = 0.25            # one tolerance, arms 1, 2 and 4
DIVISORS = (4, 6, 8)      # leg-dependent splits reported at every divisor
PRIMARY_DIVISOR = 6       # == fib_leg.ORIGIN_DIVISOR (pinned by a test in V124-4)
MIN_BUCKET_N = MIN_N_TRAIN
MIN_SIGN_DIVISORS = 2
REFERENCE = {"bullish": {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219},
             "bearish": {"n": 169, "win_rate": 23.67, "expectancy_r": -0.1269}}
REFERENCE_UNIVERSE_N = 73
EXIT_RULE = ("An arm proceeds to its own spec only if, on the bullish side, the favourable bucket "
             "has a higher win rate and an ExpR no lower than the rest, with N >= 30 in each bucket. "
             "Arms 1, 2 and 4 must also keep the win-rate sign at two of the three divisors.")


def require_diagnostic_window(window):
    """Refuse a diagnostic window starting before 2015-01-01 or ending after 2025-12-31."""
    start, end = window
    if start < DIAG_WINDOW[0] or end > DIAG_WINDOW[1]:
        raise SystemExit(f"v124 diagnostic window is {DIAG_WINDOW[0]}..{DIAG_WINDOW[1]}: got {start}..{end}")
    return window


def require_repro_window(window):
    """The v103 reproduction runs on exactly REPRO_WINDOW, nothing else."""
    if tuple(window) != REPRO_WINDOW:
        raise SystemExit(f"the v103 reproduction runs on {REPRO_WINDOW[0]}..{REPRO_WINDOW[1]} only: got {window}")
    return tuple(window)


def bucket(rows, favourable) -> dict:
    fav, rest = [], []
    for row in rows:
        (fav if favourable(row) else rest).append(row)
    return {"favourable": pooled(fav), "rest": pooled(rest)}


def _comparable(stats) -> bool:
    return (stats["n"] >= MIN_BUCKET_N and stats["win_rate"] is not None
            and stats["expectancy_r"] is not None)


def split_passes(buckets) -> bool:
    """Spec exit rule for one split: higher WR, ExpR no lower, N >= 30 in each bucket."""
    fav, rest = buckets["favourable"], buckets["rest"]
    if not (_comparable(fav) and _comparable(rest)):
        return False
    return fav["win_rate"] > rest["win_rate"] and fav["expectancy_r"] >= rest["expectancy_r"]


def wr_sign_positive(buckets) -> bool:
    fav, rest = buckets["favourable"]["win_rate"], buckets["rest"]["win_rate"]
    return fav is not None and rest is not None and fav > rest


def divisor_buckets(rows, cell_key) -> dict:
    return {str(d): bucket(rows, lambda row, d=d: bool(row[f"d{d}"][cell_key])) for d in DIVISORS}


def leg_arm_verdict(by_divisor) -> dict:
    primary = split_passes(by_divisor[str(PRIMARY_DIVISOR)])
    signs = sum(wr_sign_positive(by_divisor[str(d)]) for d in DIVISORS)
    return {"primary_passes": primary, "wr_sign_divisors": signs,
            "proceeds": primary and signs >= MIN_SIGN_DIVISORS}


def single_split_verdict(buckets) -> dict:
    primary = split_passes(buckets)
    return {"primary_passes": primary, "proceeds": primary}


def describe(rows, key) -> dict:
    """Description only: pooled stats per label. Never feeds a verdict."""
    groups = collections.defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name: pooled(members) for name, members in sorted(groups.items())}


def quintile_key(rows, value_key):
    """Label function: Q1..Q5 over this population's own values, 'no leg' for None."""
    values = [value for value in map(value_key, rows) if value is not None]
    if not values:
        return lambda row: "no leg"
    edges = np.quantile(values, [0.2, 0.4, 0.6, 0.8])

    def label(row):
        value = value_key(row)
        return "no leg" if value is None else f"Q{int(np.searchsorted(edges, value, side='right')) + 1}"
    return label


def reproduction(rows, direction, universe_n, reference=None) -> dict:
    """v103 reference arm on REPRO_WINDOW: N exact, WR at 2 dp, ExpR at 4 dp, universe exact."""
    observed, want = pooled(dir_rows(rows, direction)), (reference or REFERENCE)[direction]
    same = (observed["n"] == want["n"] and observed["win_rate"] is not None
            and observed["expectancy_r"] is not None
            and round(observed["win_rate"], 2) == want["win_rate"]
            and round(observed["expectancy_r"], 4) == want["expectancy_r"])
    return {"observed": observed, "reference": want, "universe_n": universe_n,
            "reference_universe_n": REFERENCE_UNIVERSE_N,
            "matches": bool(same and universe_n == REFERENCE_UNIVERSE_N)}


ZONE_FAMILIES = frozenset({"Volume Profile", "AVWAP"})   # Rolling S/R closed by v102; Zigzag redundant (v49)


def atr_at(prefix) -> float:
    return float(atr(prefix).iloc[-1]) if len(prefix) else float("nan")


def near(a, b, atr_value) -> bool:
    return bool(np.isfinite(a) and np.isfinite(b) and atr_value > 0 and abs(a - b) <= TOL_ATR * atr_value)


def rolling_anchor(prefix, lookback):
    """The swing low/high fibonacci_entries draws at the last bar: min Low / max
    High over the trailing ``lookback`` bars (first occurrence). None when short."""
    if len(prefix) < lookback:
        return None
    lows = prefix["Low"].to_numpy(float)[-lookback:]
    highs = prefix["High"].to_numpy(float)[-lookback:]
    base = len(prefix) - lookback
    return {"low": float(lows.min()), "low_pos": base + int(np.argmin(lows)),
            "high": float(highs.max()), "high_pos": base + int(np.argmax(highs))}


def anchored_split(anchor, leg, atr_value, direction) -> bool:
    """Arm 1 primary: the rolling origin-side extreme within 0.25 ATR of the leg
    origin AND the other extreme within 0.25 ATR of the leg end."""
    if anchor is None:
        return False
    origin, end = (anchor["low"], anchor["high"]) if direction == "bullish" else (anchor["high"], anchor["low"])
    return near(origin, leg["origin_price"], atr_value) and near(end, leg["end_price"], atr_value)


def anchor_is_fractal(prefix, anchor, direction):
    """Arm 1 described: is the rolling origin-side extreme a k=3 fractal confirmed by now?"""
    if anchor is None:
        return None
    sh, sl = pivot_confirmations(prefix, PIVOT_K)
    flags, pos = (sl, anchor["low_pos"]) if direction == "bullish" else (sh, anchor["high_pos"])
    confirm = pos + PIVOT_K
    return bool(confirm < len(prefix) and flags[confirm])


def _zone_prices(candidates):
    return [price for price, label in candidates if strategy_family(label) in ZONE_FAMILIES]


def zone_confluence(candidates, leg, atr_value) -> bool:
    """Arm 2 primary: a Volume Profile or AVWAP price inside the leg's 0.5-0.618
    zone widened by 0.25 ATR each side. False when there is no leg."""
    lo, hi = sorted((leg["level_500"], leg["level_618"]))
    if not (np.isfinite(lo) and atr_value > 0):
        return False
    pad = TOL_ATR * atr_value
    return any(lo - pad <= price <= hi + pad for price in _zone_prices(candidates))


def level_confluence(candidates, level, atr_value) -> bool:
    """Arm 2 described: the same families within 0.25 ATR of the rolling tested level."""
    return any(near(price, level, atr_value) for price in _zone_prices(candidates))


def close_in_zone(leg, close) -> bool:
    lo, hi = sorted((leg["level_500"], leg["level_618"]))
    return bool(np.isfinite(lo) and lo <= close <= hi)


def confirm_close(prefix, direction) -> bool:
    """Arm 3 primary: Close[t] > High[t-1] (bullish) / Close[t] < Low[t-1] (bearish)."""
    if len(prefix) < 2:
        return False
    close, prior = float(prefix["Close"].iloc[-1]), prefix.iloc[-2]
    return close > float(prior["High"]) if direction == "bullish" else close < float(prior["Low"])


def confirm_wick(prefix, direction) -> bool:
    """Arm 3 described: rejection wick (lower bullish / upper bearish) >= half the range."""
    bar = prefix.iloc[-1]
    high, low = float(bar["High"]), float(bar["Low"])
    body_lo, body_hi = sorted((float(bar["Open"]), float(bar["Close"])))
    span = high - low
    if not span > 0:
        return False
    wick = body_lo - low if direction == "bullish" else high - body_hi
    return wick >= 0.5 * span


def tri(value):
    return None if not np.isfinite(value) else bool(value)


def num(value):
    return round(float(value), 6) if np.isfinite(value) else None


def leg_cell(leg, anchor, candidates, atr_value, direction, close) -> dict:
    return {"has_leg": bool(np.isfinite(leg["origin_price"])),
            "anchored": anchored_split(anchor, leg, atr_value, direction),
            "zone_confluence": zone_confluence(candidates, leg, atr_value),
            "zone_touch": tri(leg["zone_touch"]),
            "close_in_zone": close_in_zone(leg, close),
            "broke_structure": tri(leg["broke_structure"]),
            "leg_atr": num(leg["leg_atr"])}


def _rolling_tested(anchor, close, direction):
    if anchor is None:
        return None, None
    ratio = tested_ratio(close, anchor["high"], anchor["low"], direction)
    return ratio, fib_level(anchor["high"], anchor["low"], ratio, direction)


def fib_trade_features(frame, horizon_key, direction, entry_date, *, candidates_fn=collect_candidate_levels) -> dict:
    """Arm 1-3 features at the entry bar t, from frame.iloc[:t+1] only."""
    t = frame.index.get_loc(pd.Timestamp(entry_date))
    prefix = frame.iloc[:t + 1]
    close, atr_value, h = float(prefix["Close"].iloc[-1]), atr_at(prefix), HORIZONS[horizon_key]
    anchor = rolling_anchor(prefix, h["fib_lookback"])
    candidates = candidates_fn(prefix, h, close)
    ratio, tested_level = _rolling_tested(anchor, close, direction)
    out = {"confirm_close": confirm_close(prefix, direction), "confirm_wick": confirm_wick(prefix, direction),
           "anchor_fractal": anchor_is_fractal(prefix, anchor, direction), "tested_ratio": ratio,
           "rolling_level_confluence": tested_level is not None and level_confluence(candidates, tested_level, atr_value)}
    for divisor in DIVISORS:
        leg = leg_at(prefix, direction, origin_strength(horizon_key, divisor))
        out[f"d{divisor}"] = leg_cell(leg, anchor, candidates, atr_value, direction, close)
    return out


def collect_repro(frames, asof_map, direction, *, run_fn=None, progress=None) -> list:
    """The v103 reference arm (b=0) on REPRO_WINDOW, trade rows only: the
    instrument check. The diagnostic window's 2015/2025 bounds do not apply."""
    window = require_repro_window(REPRO_WINDOW)
    return measure_fib_v103.collect_trades("A", frames, asof_map, 0.0, window, directions=(direction,),
                                           run_fn=run_fn, progress=progress)


def collect_fib(frames, asof_map, direction, window=DIAG_WINDOW, *, run_fn=None, progress=None,
                candidates_fn=collect_candidate_levels) -> list:
    """Today's Fibonacci trades (the v103 reference arm, b=0) with features.
    Bearish is unmasked inside v103's collector through gate_override."""
    require_diagnostic_window(window)
    rows = measure_fib_v103.collect_trades("A", frames, asof_map, 0.0, window, directions=(direction,),
                                           run_fn=run_fn, progress=progress)
    ticks, out = Progress(len(rows)), []
    for row in rows:
        ticks.tick(f"features {direction} {row['ticker']} {row['entry_date']}")
        out.append({**row, **fib_trade_features(frames[row["ticker"]], row["horizon_key"], direction,
                                                row["entry_date"], candidates_fn=candidates_fn)})
    return out


def _frames_and_asof(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_collect_repro(args):
    started = time.monotonic()
    frames, asof_map = _frames_and_asof(args)
    rows = collect_repro(frames, asof_map, args.direction)
    _write(args.out, {"kind": "repro", "direction": args.direction, "window": REPRO_WINDOW,
                      "universe_n": len(frames), "rows": rows,
                      "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_collect_fib(args):
    require_diagnostic_window(DIAG_WINDOW)
    started = time.monotonic()
    frames, asof_map = _frames_and_asof(args)
    rows = collect_fib(frames, asof_map, args.direction, DIAG_WINDOW)
    _write(args.out, {"kind": "fib", "direction": args.direction, "window": DIAG_WINDOW,
                      "universe_n": len(frames), "avwap_levels_enabled": bool(config.AVWAP_LEVELS_ENABLED),
                      "rows": rows, "elapsed_s": round(time.monotonic() - started, 1)})
