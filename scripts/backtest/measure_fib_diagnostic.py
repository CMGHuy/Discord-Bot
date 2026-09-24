#!/usr/bin/env python3
"""v101 Phase A: can a new mechanism lift Fibonacci to WR >= 50 at N >= 30?

TRAIN only (2020-01-01..2023-12-31); never spends VALIDATION. Measures, per
direction, three mechanisms the closed rows never tried:

  #1 structural-stop filter -- drop plans whose stop the max_risk_pct cap
     pulled in from the swing extreme (real v2 backtest outcomes, a pure
     partition of the baseline trades).
  #2 deeper-ratio stop -- stop one buffer beyond the next deeper fib ratio
     instead of the swing extreme, target re-selected for the new risk.
  #4 reclaim entry -- enter on the first close back beyond the signal bar's
     extreme within RECLAIM_WINDOW bars, same stop, target re-selected.

#2 and #4 change the geometry, so they are compared PAIRED against the same
trades' baseline under one first-touch simulator (simulate_first_touch).
Its absolute numbers are not the backtest's; its deltas are the signal.

Mechanism #3 (horizon split) is closed by v31 and the bearish baseline by v93
(docs/claude/backtest-methodology.md). Per-horizon rows are printed as
description only, and the bearish baseline must reproduce v93 exactly.

Run:
  python scripts/backtest/measure_fib_diagnostic.py \\
      --out docs/superpowers/results/<date>-v101-fib-diagnostic.json \\
      --md  docs/superpowers/results/<date>-v101-fib-diagnostic-table.md
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR  # noqa: E402
from swingbot.core.risk_limits import capped_planned_loss_pct  # noqa: E402
from swingbot.core.backtesting import arm_rule  # noqa: E402
from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS  # noqa: E402
from swingbot.core.planning.targets import fib_target_candidates, select_structural_target  # noqa: E402

STRATEGY = "Fibonacci"
ENTRY_RATIOS = (0.382, 0.5, 0.618)              # DEFAULT_PARAMS["Fibonacci"]["ratios"]
RATIO_LADDER = (0.382, 0.5, 0.618, 0.786, 1.0)  # fixed before the run; 1.0 == the swing extreme
RECLAIM_WINDOW = 5                              # fixed before the run
WR_FLOOR = 50.0                                 # badge clause, spec "Success bar"
MIN_N = 30                                      # TRAIN decided-trade floor, spec "Success bar"
MAX_SCRATCH_SHARE = 0.5


def fib_level(swing_high, swing_low, ratio, direction):
    """Retracement level of the impulse being traded: measured down from the
    high for a bullish (up-impulse) pullback, up from the low for bearish."""
    rng = swing_high - swing_low
    return swing_high - ratio * rng if direction == "bullish" else swing_low + ratio * rng


def tested_ratio(close, swing_high, swing_low, direction, ratios=ENTRY_RATIOS):
    return min(ratios, key=lambda r: abs(close - fib_level(swing_high, swing_low, r, direction)))


def structural_stop(swing_high, swing_low, atr_val, direction):
    """The stop _fibonacci_plan builds before the risk cap (builders.py)."""
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return swing_low - buf if direction == "bullish" else swing_high + buf


def deeper_ratio_stop(close, swing_high, swing_low, atr_val, direction):
    ratio = tested_ratio(close, swing_high, swing_low, direction)
    deeper = RATIO_LADDER[RATIO_LADDER.index(ratio) + 1]
    level = fib_level(swing_high, swing_low, deeper, direction)
    buf = STRUCTURE_BUFFER_ATR * atr_val
    return level - buf if direction == "bullish" else level + buf


def cap_distance(entry, horizon_key):
    """Max risk per share, the same arithmetic _fibonacci_plan applies."""
    return entry * (capped_planned_loss_pct(HORIZONS[horizon_key]["max_risk_pct"]) / 100)


def apply_cap(entry, stop, direction, cap):
    if abs(entry - stop) > cap:
        return (entry - cap if direction == "bullish" else entry + cap), True
    return stop, False


def simulate_first_touch(high, low, close, start, entry, stop, target, direction, max_hold):
    """Walk bars start+1 .. start+max_hold. The stop is checked before the
    target on the same bar (the conservative ordering the badge uses).
    No scale-out, no trailing: a paired yardstick, not the v2 engine."""
    risk = abs(entry - stop)
    last = min(start + max_hold, len(close) - 1)
    if last <= start or risk <= 0:
        return "open", None
    bull = direction == "bullish"
    for j in range(start + 1, last + 1):
        if bull:
            if low[j] <= stop:
                return "loss", -1.0
            if high[j] >= target:
                return "win", (target - entry) / risk
        else:
            if high[j] >= stop:
                return "loss", -1.0
            if low[j] <= target:
                return "win", (entry - target) / risk
    r = (close[last] - entry) / risk if bull else (entry - close[last]) / risk
    return "timeout", r


def reclaim_bar(high, low, close, i, direction, window=RECLAIM_WINDOW):
    """First bar j in (i, i+window] closing beyond the signal bar's extreme.
    Reads only bars <= j, so an entry at j's close is knowable at j."""
    for j in range(i + 1, min(i + window, len(close) - 1) + 1):
        if direction == "bullish" and close[j] > high[i]:
            return j
        if direction == "bearish" and close[j] < low[i]:
            return j
    return None


DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)


def trade_features(frame, i, horizon_key, trade, atr_val, swing_high, swing_low, cap, min_rr, max_rr):
    """Everything the three mechanisms need about one baseline trade.

    Geometry (cap flag, ratio, stop distance, re-selected targets) reads bars
    <= i, or <= j for the reclaim entry. Only simulate_first_touch walks
    forward, which is an exit, the same as run_backtest."""
    h = HORIZONS[horizon_key]
    direction, entry = trade.direction, trade.entry
    is_bull = direction == "bullish"
    high, low, close = frame["High"].values, frame["Low"].values, frame["Close"].values
    hold = h["max_holding_days"]

    struct = structural_stop(swing_high, swing_low, atr_val, direction)
    expected_stop, capped = apply_cap(entry, struct, direction, cap)
    # The builder's own stop should equal expected_stop; a mismatch means the
    # diagnostic's geometry drifted from _fibonacci_plan and #1 is unreliable.
    stop_mismatch = abs(trade.stop_loss - expected_stop) > 1e-6 * entry

    base = simulate_first_touch(high, low, close, i, entry, trade.stop_loss,
                                trade.take_profit, direction, hold)

    # #2: stop beyond the next deeper ratio (still risk-capped), new target.
    deep_stop, _ = apply_cap(entry, deeper_ratio_stop(close[i], swing_high, swing_low, atr_val, direction),
                             direction, cap)
    deep_target = select_structural_target(entry, deep_stop, is_bull,
                                           fib_target_candidates(frame, i, h, entry), min_rr, max_rr)
    deeper = (simulate_first_touch(high, low, close, i, entry, deep_stop, deep_target, direction, hold)
              if deep_target is not None else ("no_target", None))

    # #4: enter on the reclaim close, same stop, target re-selected at j.
    j = reclaim_bar(high, low, close, i, direction)
    if j is None:
        reclaim = ("no_reclaim", None)
    else:
        entry_j = float(close[j])
        still_valid = entry_j > trade.stop_loss if is_bull else entry_j < trade.stop_loss
        target_j = (select_structural_target(entry_j, trade.stop_loss, is_bull,
                                             fib_target_candidates(frame, j, h, entry_j), min_rr, max_rr)
                    if still_valid else None)
        reclaim = (simulate_first_touch(high, low, close, j, entry_j, trade.stop_loss, target_j, direction, hold)
                   if target_j is not None else ("no_target", None))

    return {
        "capped": bool(capped),
        "stop_mismatch": bool(stop_mismatch),
        "tested_ratio": tested_ratio(close[i], swing_high, swing_low, direction),
        "stop_atr": abs(entry - trade.stop_loss) / atr_val if atr_val else None,
        "base_simple": base,
        "deeper": deeper,
        "reclaim": reclaim,
    }


def simple_stats(pairs):
    closed = [(o, r) for o, r in pairs if o in ("win", "loss", "timeout")]
    decided = [o for o, _ in closed if o in ("win", "loss")]
    wins = sum(o == "win" for o in decided)
    returns = [r for _, r in closed if r is not None]
    return {"n": len(decided),
            "win_rate": wins / len(decided) * 100 if decided else None,
            "expectancy_r": sum(returns) / len(returns) if returns else None,
            "closed": len(closed),
            "dropped": len(pairs) - len(closed)}


def _real(rows):
    """Real v2 backtest outcomes, pooled plus the anchored test-year folds
    the v93 Stage 1 rule reads."""
    trades = [r["trade"] for r in rows]
    pooled = arm_rule.pooled_stats(trades)
    folds = [{"test_year": start[:4],
              "stats": arm_rule.pooled_stats([r["trade"] for r in rows
                                              if start <= r["trade"].entry_date <= end])}
             for _, _, start, end in ANCHORED_FOLDS]
    return {"pooled": pooled, "folds": folds, "verdict": arm_rule.stage1_verdict(pooled, folds)}


def _deeper_stop_summary(rows):
    """Mechanism #2 metrics: base_simple from all rows, arm from deeper stops."""
    return {
        "base_simple": simple_stats([r["features"]["base_simple"] for r in rows]),
        "arm": simple_stats([r["features"]["deeper"] for r in rows]),
    }


def _reclaim_summary(rows):
    """Mechanism #4 metrics: reclaim entry rate and paired stats."""
    reclaimed = [r for r in rows if r["features"]["reclaim"][0] != "no_reclaim"]
    return {
        "reclaim_rate": len(reclaimed) / len(rows) if rows else None,
        "base_simple": simple_stats([r["features"]["base_simple"] for r in reclaimed]),
        "arm": simple_stats([r["features"]["reclaim"] for r in reclaimed]),
    }


def _horizons_summary(rows, structural):
    """Per-horizon baseline and structural-only pooled stats."""
    return {h: {"baseline": arm_rule.pooled_stats([r["trade"] for r in rows if r["horizon_key"] == h]),
                "structural_only": arm_rule.pooled_stats([r["trade"] for r in structural
                                                          if r["horizon_key"] == h])}
            for h in ALL_HZ}


def direction_summary(rows):
    structural = [r for r in rows if not r["features"]["capped"]]
    capped = [r for r in rows if r["features"]["capped"]]
    return {
        "n_rows": len(rows),
        "baseline": _real(rows),
        "cap_rate": len(capped) / len(rows) if rows else None,
        "structural_only": _real(structural),
        "capped_only": _real(capped),
        "deeper_stop": _deeper_stop_summary(rows),
        "reclaim": _reclaim_summary(rows),
        "stop_mismatch": sum(r["features"]["stop_mismatch"] for r in rows),
        "horizons": _horizons_summary(rows, structural),
    }


def _clears(stats):
    return (stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR
            and (stats.get("n") or 0) >= MIN_N)


def phase_a_candidates(summary):
    """The spec's Phase A exit rule: pooled per-direction cells only."""
    out = []
    for d in DIRECTIONS:
        s = summary[d]
        cells = {"#1 structural_only": s["structural_only"]["pooled"],
                 "#2 deeper_stop": s["deeper_stop"]["arm"],
                 "#4 reclaim": s["reclaim"]["arm"]}
        out.extend({"direction": d, "mechanism": k, "stats": v} for k, v in cells.items() if _clears(v))
    return out


def summarise(records):
    out = {d: direction_summary([r for r in records if r["trade"].direction == d]) for d in DIRECTIONS}
    out["candidates"] = phase_a_candidates(out)
    return out
