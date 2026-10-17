"""v139 arm S funnel: Stage -1 census verdicts and Stages 0-3 over
confluence_stop_replay rows.

Every constant is PRE-REGISTERED (spec § Arm S; plan index, Spec correction
10). The gate is the v92 harvest gate run exactly as v129 ran it -- its
constants and its cell-key-generic helpers are imported from
acceptance_exit_funnel on purpose -- except that the bootstrap clusters by
ISO week of entry date (instrument v2), as the v139 spec requires.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter

from .acceptance import (BOOTSTRAP_RESAMPLES, bootstrap_delta, delta_expectancy_r,
                         expectancy_r, median_planned_rr, render_json, win_rate)
from .acceptance_exit_funnel import (ELIGIBILITY_CLAUSES, MDE_CEILING_R, MDE_POWER, TRAIN,
                                     VALIDATION, _flips, _mde_cell, _pp, _sides,
                                     _triggered_once, arm_trades, sign_flip_p)
from .acceptance_exit_funnel import stage2 as _v129_stage2
from .acceptance_harvest import evaluate_harvest
from .confluence_stop_replay import C_STEPS, cell_key

__all__ = ["ARM", "CLUSTER", "C_STEPS", "TRAIN", "VALIDATION", "stage_minus1", "stage0",
           "stage1", "stage2", "stage3", "report"]

ARM = "S"
#: Instrument v2 (v136 §4): the bootstrap resamples ISO weeks of entry date.
CLUSTER = "week"
D_BUCKET_PCT = 0.5


# --- Stage -1 (plans only) -------------------------------------------------------

def _bucket(d) -> str:
    lo = math.floor(d / D_BUCKET_PCT) * D_BUCKET_PCT
    return f"{lo:.1f}-{lo + D_BUCKET_PCT:.1f}"


def _row_id(row) -> tuple:
    return row["ticker"], row["horizon_key"], row["entry_date"], row["direction"]


def _dropped(row, c) -> bool:
    """Arm D's rule on the baseline plan: d > c."""
    return row["d"] is not None and row["d"] > float(c) + 1e-9


def _arm_s_counts(rows, key) -> dict:
    changed = sum(1 for r in rows if r["changed"][key])
    rollback = sum(1 for r in rows if r["rollback"][key])
    return {"applies": changed + rollback, "changed": changed, "rollback": rollback}


def _stratum(rows, cells) -> dict:
    clamped = [r for r in rows if r["clamped"]]
    buckets = Counter(_bucket(r["d"]) for r in clamped)
    return {"plans": len(rows), "clamped": len(clamped),
            "d_buckets": dict(sorted(buckets.items(), key=lambda kv: float(kv[0].split("-")[0]))),
            "arm_s": {cell_key(c): _arm_s_counts(rows, cell_key(c)) for c in cells},
            "arm_d": {cell_key(c): {"dropped": sum(1 for r in rows if _dropped(r, c))}
                      for c in cells}}


def _sets(rows, cells) -> dict:
    return {"arm_s": {cell_key(c): frozenset(_row_id(r) for r in rows if r["changed"][cell_key(c)])
                      for c in cells},
            "arm_d": {cell_key(c): frozenset(_row_id(r) for r in rows if _dropped(r, c))
                      for c in cells}}


def _identical_adjacent(by_key) -> list:
    keys = list(by_key)
    return [[a, b] for a, b in zip(keys, keys[1:]) if by_key[a] == by_key[b]]


def _strata(rows) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(f"{row['horizon_key']}/{row['direction']}", []).append(row)
    return out


def stage_minus1(rows, cells=C_STEPS) -> dict:
    """The census verdict. An arm whose every cell changes no plan is
    refused:zero-diff (the v123 precedent). `identical_adjacent` names grid
    neighbours that change the identical plan set -- a degenerate axis is
    reported before any outcome is read, never discovered after."""
    cells = tuple(cells)
    sets = _sets(rows, cells)
    verdicts = {arm: "REACHABLE" if any(sets[name].values()) else "refused:zero-diff"
                for arm, name in (("S", "arm_s"), ("D", "arm_d"))}
    return {"stage": -1, "arm": ARM, "verdict": verdicts["S"], "verdicts": verdicts,
            "cells": [cell_key(c) for c in cells], "totals": _stratum(rows, cells),
            "by_stratum": {k: _stratum(v, cells) for k, v in sorted(_strata(rows).items())},
            "identical_adjacent": {name: _identical_adjacent(sets[name]) for name in sets}}


# --- Stage 0 -------------------------------------------------------------------

def stage0(rows, cells=C_STEPS) -> dict:
    """Paired MDE precheck on TRAIN rows (v129's _mde_cell). Any cell over the
    ceiling closes the arm UNDERPOWERED, because Stage 1 may select any cell."""
    out = [_mde_cell(rows, cell_key(c)) for c in cells]
    verdict = "POWERED" if all(cell["powered"] for cell in out) else "UNDERPOWERED"
    return {"stage": 0, "arm": ARM, "verdict": verdict,
            "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER, "cells": out}


# --- Stage 1 -------------------------------------------------------------------

def _neighbours(c, cells) -> list:
    index = cells.index(c)
    return [cells[j] for j in (index - 1, index + 1) if 0 <= j < len(cells)]


def _selection_cell(rows, c, n_resamples, seed) -> dict:
    key = cell_key(c)
    baseline, component = arm_trades(rows, key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    eligible = all(result.clause(name).verdict == "PASS" for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "c": float(c), "eligible": eligible, "delta_expr": boot.point,
            "lo95": boot.lo, "hi95": boot.hi, "gate": render_json(result)}


def stage1(rows, cells=C_STEPS, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """TRAIN plateau selection: the eligible cell with the highest lower-95%
    dExpR whose +/-1-step neighbours in c are all eligible. A tie goes to the
    smaller c (max() keeps the first maximum)."""
    cells = tuple(float(c) for c in cells)
    table = {c: _selection_cell(rows, c, n_resamples, seed) for c in cells}
    for c, cell in table.items():
        cell["plateau"] = cell["eligible"] and all(
            table[other]["eligible"] for other in _neighbours(c, cells))
    pool = [cell for cell in table.values() if cell["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["lo95"])
        selected = {"cell": best["cell"], "c": best["c"]}
    return {"stage": 1, "arm": ARM, "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "cells": list(table.values())}


# --- Stage 2 -------------------------------------------------------------------

def stage2(rows, key) -> dict:
    """v129's free walk-forward folds (four TRAIN calendar years) for the
    selected cell: FAIL when more than half the measurable folds reverse."""
    return _v129_stage2(rows, ARM, key)


# --- Stage 3 -------------------------------------------------------------------

def stage3(rows, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest clauses,
    week-clustered, with v129's per-ticker label-swap permutation p."""
    baseline, component = arm_trades(rows, key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation", permutation_p=p,
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"stage": 3, "arm": ARM, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "gate": render_json(result)}


# --- disclosures (spec § Reporting) --------------------------------------------------

def _median_d_changed(rows, key):
    ds = [r["d"] for r in rows if r["changed"][key] and r["d"] is not None]
    return statistics.median(ds) if ds else None


def _sided_count(records, field) -> int:
    return sum(1 for record in records if record[field])


def _arm_s_disclosures(rows, key, base_records, cell_records) -> dict:
    only_base, only_cell = _triggered_once(rows, key)
    return {
        "changed": sum(1 for r in rows if r["changed"][key]),
        "rollback": sum(1 for r in rows if r["rollback"][key]),
        "median_d_changed": _median_d_changed(rows, key),
        "gap_through": {"baseline": _sided_count(base_records, "gap_through"),
                        "component": _sided_count(cell_records, "gap_through")},
        "fill_beyond_ceiling": {"baseline": _sided_count(base_records, "fill_beyond_ceiling"),
                                "component": _sided_count(cell_records, "fill_beyond_ceiling")},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
        "per_horizon_n": dict(Counter(r["horizon_key"] for r in rows)),
    }


def report(rows, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """Everything the spec asks to be reported for one cell. Informational:
    nothing here gates."""
    baseline, component = arm_trades(rows, key)
    base_records, cell_records = _sides(rows, key)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    return {
        "arm": ARM, "cell": key,
        "n_baseline": len(baseline), "n_component": len(component),
        "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
        "delta_expr": boot.point, "delta_expr_lo95": boot.lo, "delta_expr_hi95": boot.hi,
        "wr_baseline": wr_base, "wr_component": wr_cell, "delta_wr_pp": _pp(wr_cell, wr_base),
        "flips": _flips(rows, key),
        "exit_mix": {"baseline": dict(Counter(r["exit_mix"] for r in base_records)),
                     "component": dict(Counter(r["exit_mix"] for r in cell_records))},
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        **_arm_s_disclosures(rows, key, base_records, cell_records),
    }
