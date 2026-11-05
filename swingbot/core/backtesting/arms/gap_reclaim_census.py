"""v192: the gap-reclaim census -- one row per next-open market decision the component replay makes.

The arm rows (ArmTrade) carry no fill price and no cancel reason, so the strata the v192 gate is
frozen on (removed / re-priced / added / unchanged; spec § Gate) cannot be read from them: a
reclaimed trade pairs on the same key as its baseline twin. This module replays the component
arm once more under ``market_next_open.observing`` and keeps every ``NextOpenDecision``, keyed
exactly as ``ArmTrade.key``. measure_arms writes the rows beside the stamped arms as
``<out stem>.gap_reclaim.json``; the stamped rows are never touched.

``observing`` is in-process, so each worker observes its own replay and returns plain dicts.
Descriptive input to the judges (V192-16..V192-18); it decides nothing by itself.
"""
from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.marketdata import training_data
from swingbot.core.planning import gap_reclaim, market_next_open

SIDECAR_SUFFIX = "gap_reclaim"
REACHABLE = "REACHABLE"
ZERO_DIFF = "refused:zero-diff"
KEY_FIELDS = ("ticker", "strategy", "horizon_key", "signal_date", "source", "direction")
#: The pre-registered g grid (spec § Definitions); the gap/ATR shares are reported against it.
GAP_GRID = (0.10, 0.25, 0.50)
GAP_ATR_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

#: The daily-bar loader (the store measure_arms.load_frame reads); module-level so a test can swap it.
load_frame = training_data.load_daily


def row_key(row: dict) -> tuple:
    """The census row's pairing key, equal to ArmTrade.key of the trade the same plan produced
    (v1 writes the signal date as ArmTrade.entry_date)."""
    return tuple(row[field] for field in KEY_FIELDS)


def census_ticker(ticker, df, engines, horizons, signal_window, delta) -> list[dict]:
    """Every next-open market decision ``run_arm`` makes for one ticker under ``delta``, as dicts,
    limited to signal dates inside ``signal_window`` (the arm rows' own window rule)."""
    seen: list = []
    with market_next_open.observing(seen.append):
        run_arm(ticker, df, tuple(engines), tuple(horizons), tuple(signal_window), delta)
    start, end = signal_window
    return [dataclasses.asdict(item) for item in seen if start <= item.signal_date <= end]


def _census_task(task) -> tuple[str, list]:
    ticker, engines, horizons, signal_window, delta = task
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    return ticker, census_ticker(ticker, frame, engines, horizons, signal_window, delta)


def _results(tasks, workers):
    if not workers or workers <= 1 or len(tasks) <= 1:
        yield from map(_census_task, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers, initializer=training_data.select,
                             initargs=(training_data.active(),)) as pool:
        for future in as_completed([pool.submit(_census_task, task) for task in tasks]):
            yield future.result()


def census(universe, engines, horizons, signal_window, delta, *, workers=None) -> list[dict]:
    """The census over ``universe``: rows sorted by ticker, then replay order. ``workers`` > 1
    runs one task per ticker in a process pool; None or 1 runs in this process. A ticker with
    no frame contributes nothing (measure_arms has already failed the run on it)."""
    tasks = [(ticker, tuple(engines), tuple(horizons), tuple(signal_window), dict(delta))
             for ticker in universe]
    by_ticker: dict = {}
    for done, (ticker, rows) in enumerate(_results(tasks, workers), 1):
        by_ticker[ticker] = rows
        print(f"  [census] {done}/{len(tasks)} ({done * 100 // len(tasks)}%) {ticker}: "
              f"{len(rows)} decisions", flush=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def _count(rows, decision: str) -> int:
    return sum(1 for row in rows if row["decision"] == decision)


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _cell(rows) -> dict:
    armed = _count(rows, gap_reclaim.RECLAIM_WAIT)
    reclaimed = sum(1 for row in rows if row["reclaimed"])
    ambiguous = sum(1 for row in rows if row["ambiguous"])
    return {"market_plans": len(rows), "filled_at_open": _count(rows, gap_reclaim.FILL_OPEN),
            "armed": armed, "reclaimed": reclaimed, "ambiguous": ambiguous,
            "gap_no_reclaim": armed - reclaimed,
            "open_through_stop": _count(rows, gap_reclaim.OPEN_THROUGH_STOP),
            "risk_cap": _count(rows, gap_reclaim.RISK_CAP),
            "no_bar": _count(rows, market_next_open.NO_BAR),
            "reclaim_rate": _ratio(reclaimed, armed), "ambiguous_share": _ratio(ambiguous, reclaimed)}


def _gap_distribution(rows) -> dict:
    gaps = [row["gap_atr"] for row in rows if row["gap_atr"] is not None]
    if not gaps:
        return {"n": 0, "share_at_or_above": {}}
    quantiles = {f"q{round(q * 100):02d}": float(np.quantile(gaps, q)) for q in GAP_ATR_QUANTILES}
    shares = {str(g): sum(1 for gap in gaps if gap >= g) / len(gaps) for g in GAP_GRID}
    return {"n": len(gaps), **quantiles, "share_at_or_above": shares}


def reachability_summary(rows: list[dict]) -> dict:
    """Stage -1: per (horizon, direction) and in total, how many market plans the replay decided,
    how many armed the veto, reclaimed, were ambiguous, or cancelled at the open; the gap/ATR
    distribution (so a grid outside the real gap range shows as zero-diff, not a quiet no-op).
    No armed plan means the veto changed nothing: ``refused:zero-diff``."""
    by_cell = defaultdict(list)
    for row in rows:
        by_cell[(row["horizon_key"], row["direction"])].append(row)
    total = _cell(rows)
    return {"cells": [{"horizon_key": horizon, "direction": direction, **_cell(cell)}
                      for (horizon, direction), cell in sorted(by_cell.items())],
            "total": total, "gap_atr": _gap_distribution(rows),
            "verdict": REACHABLE if total["armed"] else ZERO_DIFF}


def repriced_keys(rows) -> set[tuple]:
    """Keys of the plans the veto filled on a same-session reclaim (the re-priced stratum)."""
    return {row_key(row) for row in rows if row["reclaimed"]}


def ambiguous_keys(rows) -> set[tuple]:
    """Keys of reclaim fills whose bar also reached the stop (booked -1R; the sensitivity set)."""
    return {row_key(row) for row in rows if row["ambiguous"]}


def sidecar_path(arms_path) -> Path:
    path = Path(arms_path)
    return path.with_name(f"{path.stem}.{SIDECAR_SUFFIX}.json")


def load_sidecar(arms_path) -> dict | None:
    """The census sidecar written beside ``arms_path``, or None when there is none."""
    path = sidecar_path(arms_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
