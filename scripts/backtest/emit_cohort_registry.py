#!/usr/bin/env python3
"""Emit the frozen v86 cohort registry from closed live and replay trades.

The file stores each source's raw measurements.  Shrinkage belongs solely in
``cohort_registry.get_cohort`` so every consumer applies the same prior.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from swingbot.core.backtesting.cohort_registry import cohort_key  # noqa: E402


def aggregate_cells(trades: list[dict], regimes: pd.Series) -> dict:
    """Return raw outcome statistics grouped by direction and causal regime.

    Trades outside the regime series' available history are deliberately
    omitted.  Assigning them an inferred regime would introduce fabricated
    evidence into the frozen registry.
    """
    buckets: dict[str, list[float]] = {}
    normalized_index = regimes.index.normalize()
    for trade in trades:
        realized_r = trade.get("r_realized")
        if realized_r is None:
            continue
        try:
            day = pd.Timestamp(trade["created_at"]).normalize()
            direction = trade["direction"]
        except (KeyError, TypeError, ValueError):
            continue
        matches = regimes[normalized_index == day]
        if matches.empty:
            continue
        buckets.setdefault(cohort_key(direction, str(matches.iloc[0])), []).append(
            float(realized_r)
        )

    cells = {}
    for key, realized_rs in buckets.items():
        wins = sum(realized_r > 0 for realized_r in realized_rs)
        cells[key] = {
            "n": len(realized_rs),
            "win_rate": round(100.0 * wins / len(realized_rs), 4),
            "expectancy_r": round(sum(realized_rs) / len(realized_rs), 6),
        }
    return cells


def _merge(live_cells: dict, backtest_cells: dict) -> dict:
    merged = {}
    for key in set(live_cells) | set(backtest_cells):
        live, backtest = live_cells.get(key, {}), backtest_cells.get(key, {})
        merged[key] = {
            "n_live": live.get("n", 0),
            "win_rate_live": live.get("win_rate"),
            "expectancy_r_live": live.get("expectancy_r"),
            "n_backtest": backtest.get("n", 0),
            "win_rate_backtest": backtest.get("win_rate", 0.0),
            "expectancy_r_backtest": backtest.get("expectancy_r", 0.0),
        }
    return merged


def _pool_mean_r(live: list[dict], backtest: list[dict]) -> float:
    realized_rs = [
        float(trade["r_realized"])
        for trade in live + backtest
        if trade.get("r_realized") is not None
    ]
    return round(sum(realized_rs) / len(realized_rs), 6) if realized_rs else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", required=True, help="data/trades.json")
    parser.add_argument("--backtest", required=True, help="confluence replay trades JSON")
    parser.add_argument("--spy", default="market_data/SPY.csv")
    parser.add_argument("--out", default="swingbot/core/backtesting/cohort_registry.json")
    args = parser.parse_args()

    from swingbot.core.edge.regime2 import regime_series

    spy = pd.read_csv(args.spy, index_col=0, parse_dates=True)
    regimes = regime_series(spy)
    live = [
        trade
        for trade in json.loads(Path(args.live).read_text(encoding="utf-8"))
        if trade.get("source") == "confluence" and trade.get("status") == "CLOSED"
    ]
    backtest = json.loads(Path(args.backtest).read_text(encoding="utf-8"))
    print(f"live closed confluence trades: {len(live)}", flush=True)
    print(f"backtest replay trades: {len(backtest)}", flush=True)

    payload = {
        "run_date": dt.date.today().isoformat(),
        "window": "backtest TRAIN+VALIDATION replay, live book to run_date",
        "pool_mean_r": _pool_mean_r(live, backtest),
        "cells": _merge(aggregate_cells(live, regimes), aggregate_cells(backtest, regimes)),
    }
    output = Path(args.out)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {output}: {len(payload['cells'])} cells, pool_mean_r={payload['pool_mean_r']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
