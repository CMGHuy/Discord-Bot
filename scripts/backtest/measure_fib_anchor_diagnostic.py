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
import json
import math
import subprocess
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
from swingbot.core.market.levels import collect_candidate_levels, strategy_family, target_candidates  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS, MIN_BARS  # noqa: E402
from swingbot.core.market.structure import PIVOT_K, pivot_confirmations  # noqa: E402
from swingbot.core.backtesting.arms.confluence_engine import SKIPPED  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import (  # noqa: E402
    LEVEL_REFRESH_BARS, levels_asof, replay_scenarios)
from swingbot.core.planning.builders import _clamp_stop_to_hard_cap  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402
from swingbot.core.planning.targets import select_structural_target  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

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


FIB_FAMILY = "Fibonacci"
LEG_PRICE_KEYS = ("origin_price", "level_382", "level_500", "level_618", "end_price")
ALL_HZ = tuple(LEGACY_HORIZONS)


def bucket_bar(index, horizon_key) -> int:
    """The bar replay_scenarios built its cached level map at: the first bar of
    index's LEVEL_REFRESH_BARS bucket the replay visited (never before warm-up)."""
    return max(MIN_BARS[horizon_key], (index // LEVEL_REFRESH_BARS) * LEVEL_REFRESH_BARS)


def scenario_map(ticker, frame, index, horizon_key, *, levels_fn=levels_asof):
    """(supports, resistances) the replay handed build_confluence_plan at ``index``:
    the as-of map for the bucket bar, re-split against Close[index], nearest first."""
    supports, resistances = levels_fn(ticker, frame, bucket_bar(index, horizon_key), horizon_key, {})
    price = float(frame["Close"].iloc[index])
    ordered = sorted(supports + resistances, key=lambda level: level.price)
    return [level for level in ordered if level.price < price][::-1], [level for level in ordered if level.price > price]


def map_pair(level_map, direction):
    """(stop-side level, target-1 level) of a re-split map, or None when one side is empty."""
    below, above = level_map
    if not below or not above:
        return None
    return (below[0], above[0]) if direction == "bullish" else (above[0], below[0])


def scenario_levels(ticker, frame, index, horizon_key, direction, *, levels_fn=levels_asof):
    return map_pair(scenario_map(ticker, frame, index, horizon_key, levels_fn=levels_fn), direction)


def derived_tp1(plan, candidates, params):
    """tp1 exactly as build_confluence_plan derives it: select_structural_target over
    the re-split map's target candidates, using the plan's own (clamped) stop."""
    return select_structural_target(plan.trigger_price, plan.stop_loss, plan.direction == "bullish",
                                    candidates, params.min_risk_reward_ratio, params.max_risk_reward_ratio)


def _same(a, b) -> bool:
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def is_identified(plan, stop_level, candidates, params=None) -> bool:
    """The rebuild is right only if it reproduces the plan's own (clamped) stop AND
    its tp1 as build_confluence_plan derives it from the rebuilt candidates (the stop
    alone is blind to a wrong map once the hard cap snaps it)."""
    if plan.stop_loss is None or plan.tp1 is None:
        return False
    params = params or ScanParams.from_config()
    expected = _clamp_stop_to_hard_cap(plan.trigger_price, stop_level.price, plan.direction == "bullish")
    return _same(plan.stop_loss, expected) and _same(plan.tp1, derived_tp1(plan, candidates, params))


def fib_labels(pair) -> set:
    return {label for level in pair for label in level.sources if strategy_family(label) == FIB_FAMILY}


def fib_candidate_prices(candidates, labels) -> list:
    return [float(price) for price, label in candidates if label in labels]


def arm4_cell(leg, prices, atr_value) -> dict:
    """Arm 4 primary: a Fibonacci candidate within 0.25 ATR of a leg price."""
    return {"has_leg": bool(np.isfinite(leg["origin_price"])),
            "fib_on_leg": any(near(price, leg[key], atr_value) for price in prices for key in LEG_PRICE_KEYS)}


def _fib_prices_at(frame, index, horizon_key, labels, candidates_fn):
    prefix = frame.iloc[:bucket_bar(index, horizon_key) + 1]
    candidates = candidates_fn(prefix, HORIZONS[horizon_key], float(prefix["Close"].iloc[-1]))
    return fib_candidate_prices(candidates, labels)


def _arm4_cells(prefix, horizon_key, direction, prices) -> dict:
    atr_value = atr_at(prefix)
    return {f"d{d}": arm4_cell(leg_at(prefix, direction, origin_strength(horizon_key, d)), prices, atr_value)
            for d in DIVISORS}


def confluence_row(ticker, frame, horizon_key, index, plan, result, *, levels_fn=levels_asof,
                   candidates_fn=collect_candidate_levels) -> dict:
    row = {"ticker": ticker, "horizon_key": horizon_key, "direction": plan.direction,
           "entry_date": str(frame.index[index].date()), "outcome": result.outcome,
           "r_multiple": result.r_total}
    level_map = scenario_map(ticker, frame, index, horizon_key, levels_fn=levels_fn)
    pair = map_pair(level_map, plan.direction)
    row["identified"] = pair is not None and is_identified(
        plan, pair[0], target_candidates(*level_map, plan.direction))
    labels = fib_labels(pair) if row["identified"] else set()
    row["has_fib"] = bool(labels)
    if labels:
        prices = _fib_prices_at(frame, index, horizon_key, labels, candidates_fn)
        row.update(_arm4_cells(frame.iloc[:index + 1], horizon_key, plan.direction, prices))
    return row


def confluence_trades(ticker, frame, horizon_key, window, *, replay_fn=replay_scenarios,
                      exit_fn=simulate_exit) -> list:
    """Mirror of ConfluenceEngine.run_ticker that keeps (index, plan, result)."""
    start, end = require_diagnostic_window(window)
    out = []
    for index, plan in replay_fn(ticker, frame.loc[:end], horizon_key):
        if str(frame.index[index].date()) < start:
            continue
        result = exit_fn(frame, index, plan, scale_out=True)
        if result.outcome not in SKIPPED:
            out.append((index, plan, result))
    return out


def collect_confluence(frames, window=DIAG_WINDOW, *, horizons=ALL_HZ, replay_fn=replay_scenarios,
                       exit_fn=simulate_exit, levels_fn=levels_asof,
                       candidates_fn=collect_candidate_levels) -> list:
    require_diagnostic_window(window)
    progress, rows = Progress(len(frames) * len(horizons)), []
    for ticker, frame in sorted(frames.items()):
        for horizon_key in horizons:
            progress.tick(f"confluence {ticker} {horizon_key}")
            for index, plan, result in confluence_trades(ticker, frame, horizon_key, window,
                                                         replay_fn=replay_fn, exit_fn=exit_fn):
                rows.append(confluence_row(ticker, frame, horizon_key, index, plan, result,
                                           levels_fn=levels_fn, candidates_fn=candidates_fn))
    return rows


def _cmd_collect_confluence(args):
    require_diagnostic_window(DIAG_WINDOW)
    require_ext_cache()
    started = time.monotonic()
    frames = _load_frames(args.universe, args.tickers)
    rows = collect_confluence(frames, DIAG_WINDOW)
    _write(args.out, {"kind": "confluence", "window": DIAG_WINDOW, "tickers": sorted(frames),
                      "universe_n": len(frames), "avwap_levels_enabled": bool(config.AVWAP_LEVELS_ENABLED),
                      "rows": rows, "elapsed_s": round(time.monotonic() - started, 1)})


def _primary(row):
    return row[f"d{PRIMARY_DIVISOR}"]


def fib_tables(rows, direction) -> dict:
    rows = dir_rows(rows, direction)
    leg_atr = quintile_key(rows, lambda row: _primary(row)["leg_atr"])
    return {
        "arm1": divisor_buckets(rows, "anchored"),
        "arm1_described": {"rolling_origin_is_fractal": describe(rows, lambda row: row["anchor_fractal"]),
                           "broke_structure": describe(rows, lambda row: _primary(row)["broke_structure"]),
                           "leg_atr_quintile": describe(rows, leg_atr)},
        "arm2": divisor_buckets(rows, "zone_confluence"),
        "arm2_described": {"zone_touch": describe(rows, lambda row: _primary(row)["zone_touch"]),
                           "close_in_zone": describe(rows, lambda row: _primary(row)["close_in_zone"]),
                           "tested_ratio": describe(rows, lambda row: row["tested_ratio"]),
                           "rolling_level_confluence": describe(rows, lambda row: row["rolling_level_confluence"])},
        "arm3": bucket(rows, lambda row: row["confirm_close"]),
        "arm3_described": {"rejection_wick_half_range": describe(rows, lambda row: row["confirm_wick"])},
    }


def confluence_tables(rows) -> dict:
    unidentified = sum(not row["identified"] for row in rows)
    population = [row for row in rows if row["has_fib"]]
    return {"population": {d: pooled(dir_rows(rows, d)) for d in DIRECTIONS},
            "unidentified": unidentified, "fib_population_n": len(population),
            "measurable": bool(rows) and unidentified == 0,
            "arm4": {d: divisor_buckets(dir_rows(population, d), "fib_on_leg") for d in DIRECTIONS}}


def verdicts(fib, confluence) -> dict:
    bull = fib["bullish"]
    arm4 = (leg_arm_verdict(confluence["arm4"]["bullish"]) if confluence["measurable"]
            else {"proceeds": False, "not_measurable": True})
    return {"arm1": leg_arm_verdict(bull["arm1"]), "arm2": leg_arm_verdict(bull["arm2"]),
            "arm3": single_split_verdict(bull["arm3"]), "arm4": arm4}


def _require_kind(payloads, kind):
    for payload in payloads:
        if payload.get("kind") != kind:
            raise SystemExit(f"expected a {kind} payload, got kind={payload.get('kind')!r}")


def _by_direction(payloads, kind):
    directions = [payload["direction"] for payload in payloads]
    duplicates = sorted({d for d in directions if directions.count(d) > 1})
    if duplicates:
        raise SystemExit(f"duplicate {kind} payload for {', '.join(duplicates)}: "
                         "one job per direction (only collect-confluence is chunked)")
    found = {payload["direction"]: payload for payload in payloads}
    missing = [d for d in DIRECTIONS if d not in found]
    if missing:
        raise SystemExit(f"no {kind} payload for {', '.join(missing)}")
    return found


def reproductions(repro_payloads) -> dict:
    """Reproduction on REPRO_WINDOW only; refuses a payload from any other window."""
    _require_kind(repro_payloads, "repro")
    for payload in repro_payloads:
        require_repro_window(payload["window"])
    found = _by_direction(repro_payloads, "collect-repro")
    return {d: reproduction(found[d]["rows"], d, found[d]["universe_n"]) for d in DIRECTIONS}


def _require_consistent(fib_payloads, confluence_payloads):
    seen = set()
    for payload in confluence_payloads:
        overlap = seen & set(payload["tickers"])
        if overlap:
            raise SystemExit(f"confluence chunks overlap on {', '.join(sorted(overlap))}")
        seen |= set(payload["tickers"])
    flags = {p["avwap_levels_enabled"] for p in fib_payloads + confluence_payloads}
    if len(flags) > 1:
        raise SystemExit(f"mixed avwap_levels_enabled across payloads: {sorted(flags)}")


def build_report(fib_payloads, confluence_payloads, repro_payloads) -> dict:
    _require_kind(fib_payloads, "fib")
    _require_kind(confluence_payloads, "confluence")
    for payload in fib_payloads + confluence_payloads:
        window = tuple(payload["window"])
        require_diagnostic_window(window)
        if window != DIAG_WINDOW:
            raise SystemExit(f"diagnostic window must be exactly {DIAG_WINDOW}, got {window}")
    _require_consistent(fib_payloads, confluence_payloads)
    by_direction = _by_direction(fib_payloads, "collect-fib")
    fib = {d: fib_tables(by_direction[d]["rows"], d) for d in DIRECTIONS}
    confluence = confluence_tables([row for payload in confluence_payloads for row in payload["rows"]])
    return {"window": list(DIAG_WINDOW), "repro_window": list(REPRO_WINDOW), "exit_rule": EXIT_RULE,
            "avwap_levels_enabled": sorted({p["avwap_levels_enabled"] for p in fib_payloads + confluence_payloads}),
            "reproduction": reproductions(repro_payloads),
            "fib": fib, "confluence": confluence, "verdicts": verdicts(fib, confluence)}


# --- markdown ---------------------------------------------------------------

ARM_SECTIONS = (("arm1", "Arm 1 anchored entry", True), ("arm2", "Arm 2 zone + confluence", True),
                ("arm3", "Arm 3 confirmation", False))


def _stats_line(name, stats) -> str:
    wr = "n/a" if stats["win_rate"] is None else f"{stats['win_rate']:.2f}%"
    exp = "n/a" if stats["expectancy_r"] is None else f"{stats['expectancy_r']:+.3f}"
    return f"| {name} | {stats['n']} | {wr} | {exp} |"


def _table(title, named_stats) -> list:
    lines = [f"#### {title}", "", "| bucket | N | WR | ExpR |", "|---|---|---|---|"]
    return lines + [_stats_line(name, stats) for name, stats in named_stats.items()] + [""]


def _divisor_rows(by_divisor) -> dict:
    return {f"d={d} {side}": by_divisor[str(d)][side] for d in DIVISORS for side in ("favourable", "rest")}


def _arm_lines(tables, key, title, by_divisor) -> list:
    primary = _divisor_rows(tables[key]) if by_divisor else tables[key]
    lines = _table(f"{title} -- primary split", primary)
    for name, groups in tables[f"{key}_described"].items():
        lines += _table(f"{title} -- described: {name}", groups)
    return lines


def _reproduction_lines(reproductions) -> list:
    lines = ["## Baseline reproduction (v103 reference arm, b=0, on 2010-01-01..2023-12-31)", "",
             "| direction | N | WR | ExpR | universe | reference N / WR / ExpR / universe | matches |",
             "|---|---|---|---|---|---|---|"]
    for direction, item in reproductions.items():
        obs, ref = item["observed"], item["reference"]
        wr = "n/a" if obs["win_rate"] is None else f"{obs['win_rate']:.2f}%"
        exp = "n/a" if obs["expectancy_r"] is None else f"{obs['expectancy_r']:+.4f}"
        lines.append(f"| {direction} | {obs['n']} | {wr} | {exp} | {item['universe_n']} | "
                     f"{ref['n']} / {ref['win_rate']}% / {ref['expectancy_r']:+.4f} / "
                     f"{item['reference_universe_n']} | {item['matches']} |")
    return lines + [""]


def _verdict_lines(verdict_map) -> list:
    lines = ["## Verdicts (bullish only)", "", "| arm | primary passes | WR-sign divisors | proceeds |",
             "|---|---|---|---|"]
    for arm, item in verdict_map.items():
        primary = "not measurable" if item.get("not_measurable") else item["primary_passes"]
        lines.append(f"| {arm} | {primary} | {item.get('wr_sign_divisors', '-')} | {item['proceeds']} |")
    return lines + [""]


def _confluence_lines(confluence) -> list:
    lines = ["## Confluence (arm 4)", ""] + _table("Whole confluence population (described)",
                                                   confluence["population"])
    lines += [f"Unidentified trades: {confluence['unidentified']}. "
              f"Trades with a Fibonacci-family source: {confluence['fib_population_n']}.", ""]
    if not confluence["measurable"]:
        return lines + ["Arm 4 is **not measurable with this instrument**.", ""]
    for direction in DIRECTIONS:
        lines += _table(f"Arm 4 {direction} -- primary split", _divisor_rows(confluence["arm4"][direction]))
    return lines


def render_markdown(report) -> str:
    start, end = report["window"]
    lines = ["# v124 Fibonacci anchor diagnostic -- generated tables", "",
             f"Diagnostic window {start}..{end} (entries and features; 2026 is the holdout). "
             f"AVWAP_LEVELS_ENABLED: {report['avwap_levels_enabled']}.", "",
             "## Exit rule (fixed in the spec)", "", f"> {report['exit_rule']}", ""]
    lines += _reproduction_lines(report["reproduction"]) + _verdict_lines(report["verdicts"])
    for direction in DIRECTIONS:
        suffix = " (description only)" if direction == "bearish" else ""
        lines += [f"## Fibonacci {direction}{suffix}", ""]
        for key, title, by_divisor in ARM_SECTIONS:
            lines += _arm_lines(report["fib"][direction], key, title, by_divisor)
    lines += _confluence_lines(report["confluence"])
    return "\n".join(lines) + "\n"


# --- CLI ----------------------------------------------------------------------

def _load(paths) -> list:
    return [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]


def _cmd_reproduce(args):
    print(json.dumps(reproductions(_load(args.repro)), indent=1), flush=True)


def _git(path, *args):
    return subprocess.run(["git", "-C", str(Path(path).resolve().parent), *args],
                          capture_output=True, text=True, check=False)


def _note_is_tracked(path) -> bool:
    """True when the note is committed and unmodified; True too when not in a repo or git is missing."""
    name = Path(path).resolve().name
    try:
        if _git(path, "rev-parse", "--is-inside-work-tree").returncode != 0:
            return True
        return (_git(path, "ls-files", "--error-unmatch", name).returncode == 0
                and bool(_git(path, "log", "-1", "--format=%H", "--", name).stdout.strip())
                and _git(path, "diff", "--quiet", "HEAD", "--", name).returncode == 0)
    except OSError:
        return True


def _note_ok(note) -> bool:
    path = Path(note) if note else None
    return bool(path and path.is_file() and path.read_text(encoding="utf-8").strip()
                and _note_is_tracked(path))


def _cmd_report(args):
    report = build_report(_load(args.fib), _load(args.confluence), _load(args.repro))
    note = args.reproduction_note
    if not report["reproduction"]["bullish"]["matches"] and not _note_ok(note):
        raise SystemExit("bullish baseline does not reproduce v103 on 2010-01-01..2023-12-31 "
                         "(N=815, WR 36.81%, ExpR +0.2219, universe 73): "
                         "explain the difference in a committed, non-empty note, then pass --reproduction-note <path>")
    report["reproduction_note"] = note
    _write(args.out, report)
    Path(args.md).write_text(render_markdown(report), encoding="utf-8")


def _parser():
    parser = argparse.ArgumentParser(description="v124 Fibonacci impulse-leg anchor diagnostic (2015-2025)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    repro = sub.add_parser("collect-repro")
    fib = sub.add_parser("collect-fib")
    for command in (repro, fib):
        command.add_argument("--direction", required=True, choices=DIRECTIONS)
    confluence = sub.add_parser("collect-confluence")
    for command in (repro, fib, confluence):
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated subset: chunks and smoke runs")
    reproduce = sub.add_parser("reproduce")
    reproduce.add_argument("--repro", nargs=2, required=True)
    report = sub.add_parser("report")
    report.add_argument("--repro", nargs=2, required=True)
    report.add_argument("--fib", nargs=2, required=True)
    report.add_argument("--confluence", nargs="+", required=True)
    report.add_argument("--out", required=True)
    report.add_argument("--md", required=True)
    report.add_argument("--reproduction-note")
    return parser


COMMANDS = {"collect-repro": _cmd_collect_repro, "collect-fib": _cmd_collect_fib,
            "collect-confluence": _cmd_collect_confluence,
            "reproduce": _cmd_reproduce, "report": _cmd_report}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v124 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
