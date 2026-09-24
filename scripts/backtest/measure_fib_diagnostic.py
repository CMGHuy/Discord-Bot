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
