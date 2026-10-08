"""v129 acceptance-exit funnel: Stages 0-3 over acceptance_replay rows.

Every constant here is PRE-REGISTERED (spec § Gate and funnel; plan index,
Spec corrections 7 and 8). Changing one is a new pre-registration, not a
tuning step -- see docs/claude/backtest-methodology.md.

The gate is the v92 harvest gate (acceptance_harvest.evaluate_harvest); this
module only decides which cell meets it and in what order the stages run.
"""
from __future__ import annotations

import dataclasses
from collections import Counter

from .acceptance import (
    ArmTrade, BOOTSTRAP_RESAMPLES, CLOSED, bootstrap_delta,
    delta_expectancy_r, expectancy_r, median_planned_rr, project_target_n,
    render_json, win_rate,
)
from .acceptance_harvest import (
    evaluate_harvest, mde_expectancy_r_paired, permutation_p_expectancy,
)
from .acceptance_replay import B_STEPS, CELLS, M_STEPS, cell_key

TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
TRAIN_DAYS, VALIDATION_DAYS = 1460, 730
MDE_CEILING_R = 0.10
MDE_POWER = 0.80
FOLD_YEARS = (2020, 2021, 2022, 2023)
PERMUTATION_N = 200
PERMUTATION_SEED = 42
#: The clauses a TRAIN cell must PASS to be eligible. `permutation` is not
#: among them: it is SKIPPED before the validation stage.
ELIGIBILITY_CLAUSES = ("expectancy_gain", "win_rate_floor", "volume")

_TRADE_FIELDS = tuple(f.name for f in dataclasses.fields(ArmTrade))


def _trade(record) -> ArmTrade:
    return ArmTrade(**{name: record[name] for name in _TRADE_FIELDS})


def arm_trades(rows, key) -> tuple:
    """(baseline, component) ArmTrade lists for one cell. A side that never
    triggered is absent from ITS list only, so population_split reports the
    row as added or removed instead of the row vanishing from both."""
    baseline = [_trade(r["baseline"]) for r in rows if r["baseline"] is not None]
    component = [_trade(r["cells"][key]) for r in rows if r["cells"][key] is not None]
    return baseline, component


# --- Stage 0 ---------------------------------------------------------------

def _mde_cell(rows, key) -> dict:
    baseline, component = arm_trades(rows, key)
    observed_n = sum(1 for t in baseline if t.outcome in CLOSED)
    target_n = project_target_n(observed_n=observed_n, observed_days=TRAIN_DAYS,
                                target_days=VALIDATION_DAYS)
    mde = mde_expectancy_r_paired(baseline, component, target_n=target_n,
                                  power=MDE_POWER)
    return {"cell": key, "observed_n": observed_n, "target_n": target_n,
            "mde_r": mde, "powered": mde is not None and mde <= MDE_CEILING_R}


def stage0(rows, arm) -> dict:
    """Paired MDE precheck on TRAIN rows. Any cell over the ceiling closes
    the arm UNDERPOWERED, because Stage 1 may select any cell."""
    cells = [_mde_cell(rows, cell_key(m, b)) for m, b in CELLS[arm]]
    verdict = "POWERED" if all(c["powered"] for c in cells) else "UNDERPOWERED"
    return {"stage": 0, "arm": arm, "verdict": verdict,
            "mde_ceiling_r": MDE_CEILING_R, "power": MDE_POWER, "cells": cells}


# --- Stage 1 ---------------------------------------------------------------

def _neighbours(arm, m, b) -> list:
    """Grid cells one step away in m or in b. Arm B has one axis, so the
    neighbour of a cell is the other cell."""
    if m is None:
        return [cell for cell in CELLS[arm] if cell != (m, b)]
    mi, bi = M_STEPS.index(m), B_STEPS.index(b)
    out = [(M_STEPS[j], b) for j in (mi - 1, mi + 1) if 0 <= j < len(M_STEPS)]
    out += [(m, B_STEPS[j]) for j in (bi - 1, bi + 1) if 0 <= j < len(B_STEPS)]
    return out


def _selection_cell(rows, m, b, n_resamples, seed) -> dict:
    key = cell_key(m, b)
    baseline, component = arm_trades(rows, key)
    result = evaluate_harvest(baseline, component, stage="walkforward",
                              n_resamples=n_resamples, seed=seed)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed)
    eligible = all(result.clause(name).verdict == "PASS"
                   for name in ELIGIBILITY_CLAUSES)
    return {"cell": key, "m": m, "b": b, "eligible": eligible,
            "delta_expr": boot.point, "lo95": boot.lo, "hi95": boot.hi,
            "gate": render_json(result)}


def stage1(rows, arm, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """TRAIN plateau selection: the eligible cell with the highest lower-95%
    dExpR whose grid neighbours are all eligible. A tie goes to the earlier
    cell in CELLS order (max() keeps the first maximum)."""
    table = {(m, b): _selection_cell(rows, m, b, n_resamples, seed)
             for m, b in CELLS[arm]}
    for (m, b), cell in table.items():
        cell["plateau"] = cell["eligible"] and all(
            table[other]["eligible"] for other in _neighbours(arm, m, b))
    pool = [cell for cell in table.values() if cell["plateau"]]
    selected = None
    if pool:
        best = max(pool, key=lambda cell: cell["lo95"])
        selected = {"cell": best["cell"], "m": best["m"], "b": best["b"]}
    return {"stage": 1, "arm": arm,
            "verdict": "SELECTED" if selected else "NO_ELIGIBLE_CELL",
            "selected": selected, "cells": list(table.values())}


# --- Stage 2 ---------------------------------------------------------------

def _fold(rows, key, year) -> dict:
    fold_rows = [r for r in rows if r["entry_date"][:4] == str(year)]
    delta = delta_expectancy_r(*arm_trades(fold_rows, key))
    return {"year": year, "n": len(fold_rows), "delta_expr": delta,
            "reversed": delta is not None and delta < 0}


def stage2(rows, arm, key) -> dict:
    """Free walk-forward folds: one per TRAIN calendar year, for the selected
    cell. FAIL when more than half the measurable folds reverse sign, or when
    no fold is measurable."""
    folds = [_fold(rows, key, year) for year in FOLD_YEARS]
    measurable = [f for f in folds if f["delta_expr"] is not None]
    reversed_n = sum(1 for f in measurable if f["reversed"])
    ok = bool(measurable) and reversed_n <= len(measurable) / 2
    return {"stage": 2, "arm": arm, "cell": key, "verdict": "PASS" if ok else "FAIL",
            "measurable": len(measurable), "reversed": reversed_n, "folds": folds}


# --- Stage 3 ---------------------------------------------------------------

def sign_flip_p(baseline, component, *, n_perm: int = PERMUTATION_N,
                seed: int = PERMUTATION_SEED) -> float | None:
    """The not_luck instrument: swap the arm labels of a random half of the
    tickers and recompute dExpR. v123 already ships it as
    permutation_p_expectancy; this is the v129-pinned (200, 42) wrapper."""
    return permutation_p_expectancy(baseline, component, n_perm=n_perm, seed=seed)


def stage3(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest
    clauses, with the permutation p from sign_flip_p."""
    baseline, component = arm_trades(rows, key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation",
                              permutation_p=p, n_resamples=n_resamples, seed=seed)
    return {"stage": 3, "arm": arm, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "gate": render_json(result)}


# --- disclosures (spec § Reporting) ----------------------------------------

def _flips(rows, key) -> dict:
    out = {"win_to_loss": 0, "loss_to_win": 0, "other": 0}
    for r in rows:
        base, cell = r["baseline"], r["cells"][key]
        if base is None or cell is None or base["outcome"] == cell["outcome"]:
            continue
        pair = (base["outcome"], cell["outcome"])
        name = {("win", "loss"): "win_to_loss", ("loss", "win"): "loss_to_win"}.get(pair, "other")
        out[name] += 1
    return out


def _sides(rows, key) -> tuple:
    baseline = [r["baseline"] for r in rows if r["baseline"] is not None]
    component = [r["cells"][key] for r in rows if r["cells"][key] is not None]
    return baseline, component


def _triggered_once(rows, key) -> tuple:
    only_base = sum(1 for r in rows if r["baseline"] is not None and r["cells"][key] is None)
    only_cell = sum(1 for r in rows if r["baseline"] is None and r["cells"][key] is not None)
    return only_base, only_cell


def _pp(component, baseline) -> float | None:
    return None if component is None or baseline is None else component - baseline


def report(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES,
           seed: int = 42) -> dict:
    """Everything the spec asks to be reported for one cell. Informational:
    nothing here gates."""
    baseline, component = arm_trades(rows, key)
    base_records, cell_records = _sides(rows, key)
    boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                           n_resamples=n_resamples, seed=seed)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    only_base, only_cell = _triggered_once(rows, key)
    return {
        "arm": arm, "cell": key,
        "n_baseline": len(baseline), "n_component": len(component),
        "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
        "delta_expr": boot.point, "delta_expr_lo95": boot.lo, "delta_expr_hi95": boot.hi,
        "wr_baseline": wr_base, "wr_component": wr_cell,
        "delta_wr_pp": _pp(wr_cell, wr_base),
        "flips": _flips(rows, key),
        "exit_mix": {"baseline": dict(Counter(r["exit_mix"] for r in base_records)),
                     "component": dict(Counter(r["exit_mix"] for r in cell_records))},
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        "not_eligible": sum(1 for r in rows if not r["eligible"]),
        "gap_through": {"baseline": sum(1 for r in base_records if r["gap_through"]),
                        "component": sum(1 for r in cell_records if r["gap_through"])},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
        "per_horizon_n": dict(Counter(r["horizon_key"] for r in rows)),
    }
