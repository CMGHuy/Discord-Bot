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
