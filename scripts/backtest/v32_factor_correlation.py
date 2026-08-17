#!/usr/bin/env python3
"""v32 Task 1: pairwise Spearman correlation between the factors the plan's
reconciliation table calls out as possible duplicates -- ADX/MACD/RSI (three
independent momentum reads) and HTF bias vs MTF alignment (two
higher-timeframe reads). All five are computed directly from the historical
`df` window alone (no scenario/RS-cache/breadth reconstruction needed), so
this samples real TRAIN trade entry bars (NO-LOOKAHEAD: every reading uses
`df.iloc[:i+1]`, never a future bar) via the same windowing pattern
scripts/reports/audit_quality_score.py already uses.

Correlates each function's own graded STRENGTH LABEL (not its eventual point
value -- factors.py doesn't exist yet, Task 1 runs before Task 3 extracts the
point arithmetic), ordinally encoded, since Spearman only needs a monotonic
relationship: strong=3 > moderate=2 > weak=1 > none/opposed=0. MTF alignment
is already an integer 0-3 count, used as-is.

Prints one flushed line per ticker (CLAUDE.md: any script running more than a
couple of minutes must report progress per unit of work).

Run: python scripts/backtest/v32_factor_correlation.py --json data/v32_factor_correlation.json
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.market.volatility import (
    adx_trend_strength, macd_momentum_aligned, rsi_trend_aligned,
)
from swingbot.core.scanning.regime import get_htf_bias
from swingbot.core.edge import factors as rs_factors

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")

_ADX_RANK = {True: 2}          # adx_info["strong"] True -> 2, else see below
_STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1, "none": 0}


def _adx_rank(window: pd.DataFrame) -> int | None:
    info = adx_trend_strength(window)
    if info["adx"] is None:
        return None
    if info["strong"]:
        return 2
    if info["trending"]:
        return 1
    return 0


def _macd_rank(window: pd.DataFrame, direction: str) -> int:
    mom = macd_momentum_aligned(window, direction)
    return _STRENGTH_RANK.get(mom["strength"], 0)


def _rsi_rank(window: pd.DataFrame, direction: str) -> int | None:
    rsi_mom = rsi_trend_aligned(window, direction)
    if rsi_mom["rsi_val"] is None:
        return None
    return _STRENGTH_RANK.get(rsi_mom["strength"], 0)


def _htf_rank(window: pd.DataFrame, horizon_key: str, direction: str) -> float | None:
    htf = get_htf_bias(window, horizon_key)
    if htf is None or htf.get("bias") not in ("bullish", "bearish"):
        return None
    return 1.0 if htf["bias"] == direction else 0.0


def _mtf_rank(window: pd.DataFrame, direction: str) -> int:
    return int(rs_factors.mtf_alignment(window, direction))


def collect_samples() -> list[dict]:
    """One row per TRAIN trade entry bar: the five ordinal factor readings,
    each independently None-safe (Spearman drops NaNs pairwise)."""
    rows = []
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
    for ticker, df in frames.items():
        date_to_idx = {str(d.date()): k for k, d in enumerate(df.index)}
        ticker_rows = 0
        for hk in HORIZONS:
            for strategy in ALL_STRATEGIES:
                s = run_backtest(ticker, df, strategy, hk, exit_model="v2", scale_out=True)
                for t in s.trades:
                    if not (TRAIN[0] <= t.entry_date <= TRAIN[1]):
                        continue
                    i = date_to_idx.get(t.entry_date)
                    if i is None or i < 60:   # ADX/MACD/RSI need real warm-up history
                        continue
                    window = df.iloc[:i + 1]
                    rows.append({
                        "adx": _adx_rank(window),
                        "macd": _macd_rank(window, t.direction),
                        "rsi": _rsi_rank(window, t.direction),
                        "htf": _htf_rank(window, hk, t.direction),
                        "mtf": _mtf_rank(window, t.direction),
                    })
                    ticker_rows += 1
        print(f"{ticker}: {ticker_rows} TRAIN entry-bar samples", flush=True)
    return rows


def correlation_matrix(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    print(f"\nTotal samples: {len(df)}", flush=True)
    for col in df.columns:
        print(f"  {col}: {df[col].notna().sum()} non-null", flush=True)
    return df.corr(method="spearman")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    samples = collect_samples()
    corr = correlation_matrix(samples)
    print("\nSpearman correlation matrix (ordinal strength ranks):")
    print(corr.round(3).to_string())

    if args.json:
        out = {"n_samples": len(samples), "correlation": corr.round(4).to_dict()}
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", flush=True)
