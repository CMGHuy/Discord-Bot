"""v191 ATR-band funnel: Stage -1 census verdicts and Stages 0-3 over
atr_band_replay rows, for one target arm at a time.

Every constant is PRE-REGISTERED (spec § Gate; plan index § Global
Constraints). The gate is the v92 harvest gate (acceptance_harvest), scored
on the FLOOR-MOVED STRATUM ALONE (spec § Not a re-run): a pooled pass the
floor-moved stratum does not carry is a fail. Untouched and ceiling strata
are reported, never selected on. Changing a constant here is a new
pre-registration, not a tuning step.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market.atr_band import (MOVED_CEILING, MOVED_FLOOR, MOVED_UNTOUCHED,
                                           REASON_NO_TARGET, REASON_RR_DROP)

from .acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, delta_expectancy_r, mde_paired,
                         project_target_n, render_json)
from .acceptance_exit_funnel import ELIGIBILITY_CLAUSES, arm_trades
from .acceptance_harvest import evaluate_harvest
from .atr_band_replay import FLOOR_KNOB, K_STEPS, REFERENCE_ACCOUNT, cell_key
from .backtest_wf import PLATEAU_TOLERANCE_R, plateau_report

FOLD_TRAIN = ("2018-06-01", "2022-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
FOLD_YEARS = (2021, 2022, 2023)
FOLD_2023 = ("2023-01-01", "2023-12-31")
MIN_FOLD_N = 30
MIN_POSITIVE_FOLDS = 2
MDE_CEILING_R = 0.10
MDE_POWER = 0.80
CLUSTER = "week"
INSTRUMENT = "v1"
DATA_SOURCE = "alpaca"
HOLM_ALPHA = 0.05
A_BUCKET_PCT = 0.5
#: v139 arm S's ceiling range started past 2% (spec § Not a re-run).
ARM_S_FLOOR_PCT = 2.0
MOVED = (MOVED_FLOOR, MOVED_CEILING, MOVED_UNTOUCHED)


def floor_moved(rows, key) -> list:
    """The decision stratum: rows whose stop the floor moved at this cell."""
    return [r for r in rows if r["moved_by"].get(key) == MOVED_FLOOR]


def _keys(cells) -> list:
    return [cell_key(k) for k in cells]


# --- Stage -1 (plans only) -------------------------------------------------------

def _bucket(a) -> str:
    lo = math.floor(a / A_BUCKET_PCT) * A_BUCKET_PCT
    return f"{lo:.1f}-{lo + A_BUCKET_PCT:.1f}"


def _row_id(row) -> tuple:
    return row["ticker"], row["horizon_key"], row["entry_date"], row["direction"]


def _in_cell(rows, key) -> list:
    return [r for r in rows if r["in_cell"][key]]


def _band_days(rows, key) -> Counter:
    per_day: Counter = Counter()
    for r in _in_cell(rows, key):
        if r["moved_by"][key] is not None:
            per_day.update(pd.bdate_range(r["entry_date"], r["life_end_date"]))
    return per_day


def _concurrency(rows, key) -> dict:
    """Open band plans per business day, signal date to the horizon's hold.
    heat_slots: how many full-budget candidates PORTFOLIO_HEAT_CAP_PCT admits."""
    slots = float(config.PORTFOLIO_HEAT_CAP_PCT) / float(REFERENCE_ACCOUNT["risk_pct"])
    counts = sorted(_band_days(rows, key).values())
    if not counts:
        return {"max": 0, "p95": 0.0, "heat_slots": slots, "days_over_heat_slots": 0}
    return {"max": counts[-1], "p95": float(np.percentile(counts, 95)), "heat_slots": slots,
            "days_over_heat_slots": sum(1 for c in counts if c > slots)}


def _cell_changes(rows, present, key) -> dict:
    dropped = Counter(r["dropped"][key] for r in rows if r["dropped"][key])
    return {"newly_admitted": sum(1 for r in rows if r["newly_admitted"][key]),
            "removed": sum(1 for r in rows if r["in_baseline"] and not r["in_cell"][key]),
            REASON_RR_DROP: dropped.get(REASON_RR_DROP, 0),
            REASON_NO_TARGET: dropped.get(REASON_NO_TARGET, 0),
            "band_size_zero": sum(1 for r in present if r["size_zero"][key])}


def _cell_census(rows, key) -> dict:
    present = _in_cell(rows, key)
    moved = Counter(r["moved_by"][key] for r in present)
    reversals = [r["reversal"] for r in rows if r["reversal"] is not None]
    return {"plans": len(present), **{name: moved.get(name, 0) for name in MOVED},
            **_cell_changes(rows, present, key),
            "baseline_stop_exits": len(reversals),
            "reversal": sum(1 for rev in reversals if rev.get(key)),
            "concurrency": _concurrency(rows, key)}


def _arm_s_overlap(rows) -> int:
    return sum(1 for r in rows if r["in_baseline"] and r["d"] is not None
               and r["atr_pct"] is not None
               and ARM_S_FLOOR_PCT < r["d"] <= 2.0 * r["atr_pct"])


def _atr_buckets(rows) -> dict:
    buckets = Counter(_bucket(r["atr_pct"]) for r in rows if r["atr_pct"] is not None)
    return dict(sorted(buckets.items(), key=lambda kv: float(kv[0].split("-")[0])))


def _census_table(rows, cells) -> dict:
    return {"plans_today": sum(1 for r in rows if r["in_baseline"]),
            "arm_s_overlap": _arm_s_overlap(rows), "atr_buckets": _atr_buckets(rows),
            "atr_missing": sum(1 for r in rows if r["atr_pct"] is None),
            "cells": {key: _cell_census(rows, key) for key in _keys(cells)}}


def _strata(rows) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(f"{row['horizon_key']}/{row['direction']}", []).append(row)
    return out


def _floor_sets(rows, cells) -> dict:
    return {key: frozenset(_row_id(r) for r in _in_cell(rows, key)
                           if r["moved_by"][key] == MOVED_FLOOR) for key in _keys(cells)}


def _identical_adjacent(sets) -> list:
    keys = list(sets)
    return [[a, b] for a, b in zip(keys, keys[1:]) if sets[a] == sets[b]]


def stage_minus1(census_rows, arm, cells=K_STEPS) -> dict:
    """The census verdict, before any outcome is read. A cell whose floor
    moves no plan is refused:zero-diff (it has no decision stratum); the arm
    is REACHABLE when any cell is."""
    cells = tuple(float(k) for k in cells)
    sets = _floor_sets(census_rows, cells)
    verdicts = {key: "REACHABLE" if sets[key] else "refused:zero-diff" for key in sets}
    reachable = [k for k in cells if verdicts[cell_key(k)] == "REACHABLE"]
    return {"stage": -1, "arm": arm, "verdict": "REACHABLE" if reachable else "refused:zero-diff",
            "reachable_cells": reachable, "cell_verdicts": verdicts,
            "cells": _keys(cells), "totals": _census_table(census_rows, cells),
            "by_stratum": {name: _census_table(rows, cells)
                           for name, rows in sorted(_strata(census_rows).items())},
            "identical_adjacent": _identical_adjacent(sets)}


# --- Stage 0 -------------------------------------------------------------------------

def _days(window) -> int:
    start, end = (dt.date.fromisoformat(x) for x in window)
    return (end - start).days + 1


def _paired(rows, key) -> list:
    return [r for r in rows if r["baseline"] is not None and r["cells"][key] is not None]


def _mde_cell(rows, k) -> dict:
    key = cell_key(k)
    stratum = floor_moved(rows, key)
    paired = _paired(stratum, key)
    baseline, component = arm_trades(paired, key)
    observed_n = sum(1 for t in baseline if t.outcome in CLOSED)
    target_n = project_target_n(observed_n=observed_n, observed_days=_days(FOLD_TRAIN),
                                target_days=_days(VALIDATION))
    mde = mde_paired(baseline, component, delta_expectancy_r, observed_n=observed_n,
                     target_n=target_n, power=MDE_POWER, cluster=CLUSTER) if observed_n else None
    return {"cell": key, "k": float(k), "stratum_n": len(stratum), "paired_n": len(paired),
            "newly_admitted_n": sum(1 for r in stratum if r["newly_admitted"][key]),
            "observed_n": observed_n, "target_n": target_n, "mde_r": mde,
            "powered": mde is not None and mde <= MDE_CEILING_R}


def stage0(rows, arm, cells=K_STEPS) -> dict:
    """Paired dExpR MDE on fold-train, per cell, on the floor-moved stratum.
    A cell over the ceiling is refused; the arm is POWERED when any cell is."""
    out = [_mde_cell(rows, k) for k in cells]
    powered = [cell["k"] for cell in out if cell["powered"]]
    return {"stage": 0, "arm": arm, "verdict": "POWERED" if powered else "UNDERPOWERED",
            "powered_cells": powered, "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER,
            "cluster": CLUSTER, "cells": out}


# --- Stage 1 -------------------------------------------------------------------------

def _selection_cell(rows, k, n_resamples, seed) -> dict:
    key = cell_key(k)
    baseline, component = arm_trades(floor_moved(rows, key), key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    eligible = all(result.clause(name).verdict == "PASS" for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "k": float(k), "n_baseline": len(baseline),
            "n_component": len(component), "eligible": eligible,
            "delta_expr": delta_expectancy_r(baseline, component), "gate": render_json(result)}


def _plateau(table, k) -> bool:
    """plateau_report over the whole grid; a neighbour with no dExpR is a spike."""
    grid = list(table)
    i = grid.index(k)
    window = [grid[j] for j in (i - 1, i, i + 1) if 0 <= j < len(grid)]
    if any(table[c]["delta_expr"] is None for c in window):
        return False
    values = [table[c]["delta_expr"] for c in grid]
    return plateau_report(FLOOR_KNOB, grid, values, k)["is_plateau"]


def stage1(rows, arm, cells=K_STEPS, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """Fold-train selection over k. Candidates are `cells` (Stage 0's powered
    cells); every grid cell is a neighbour. Winner: the highest point dExpR
    among candidates whose clauses 1-3 pass and that sit on a plateau."""
    candidates = {float(k) for k in cells}
    table = {float(k): _selection_cell(rows, k, n_resamples, seed) for k in K_STEPS}
    for k, cell in table.items():
        cell["candidate"] = k in candidates
        cell["plateau"] = _plateau(table, k)
    pool = [c for c in table.values() if c["candidate"] and c["eligible"] and c["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["delta_expr"])
        selected = {"cell": best["cell"], "k": best["k"]}
    return {"stage": 1, "arm": arm, "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "tolerance_r": PLATEAU_TOLERANCE_R,
            "cells": list(table.values())}
