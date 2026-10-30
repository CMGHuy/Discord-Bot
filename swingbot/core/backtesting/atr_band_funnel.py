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
import statistics
from collections import Counter

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market.atr_band import (MOVED_CEILING, MOVED_FLOOR, MOVED_UNTOUCHED,
                                           REASON_NO_TARGET, REASON_RR_DROP)

from swingbot.core.backtesting.instrument.stats import ledger_qvalues

from .acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, bootstrap_delta, delta_expectancy_r,
                         expectancy_r, mde_paired, median_planned_rr, project_target_n,
                         render_json, win_rate)
from .acceptance_exit_funnel import (ELIGIBILITY_CLAUSES, PERMUTATION_N, _flips, _pp, _sides,
                                     _triggered_once, arm_trades, sign_flip_p)
from .acceptance_harvest import evaluate_harvest
from .atr_band_replay import FLOOR_KNOB, K_STEPS, REFERENCE_ACCOUNT, cell_key
from .backtest_wf import PLATEAU_TOLERANCE_R, plateau_report
from .giveback_levels_funnel import holm

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


#: The Holm family (spec § Gate): arm K primary, arm R second, never pooled.
FAMILY = ("K", "R")
PRIMARY_ARM = "K"


# --- Stage 2 -------------------------------------------------------------------------

def _fold(rows, key, year) -> dict:
    baseline, component = arm_trades(floor_moved(rows, key), key)
    n = sum(1 for t in component if t.outcome in CLOSED)
    delta = delta_expectancy_r(baseline, component)
    measurable = n >= MIN_FOLD_N and delta is not None
    return {"year": year, "n": n, "delta_expr": delta, "measurable": measurable,
            "positive": measurable and delta > 0}


def stage2(rows_by_year: dict, arm, key) -> dict:
    """Walk-forward folds 2021 / 2022 / 2023 for the selected cell: PASS when
    at least MIN_POSITIVE_FOLDS folds carry N >= MIN_FOLD_N and dExpR > 0."""
    folds = [_fold(rows_by_year.get(year, []), key, year) for year in FOLD_YEARS]
    positive = sum(1 for fold in folds if fold["positive"])
    return {"stage": 2, "arm": arm, "cell": key,
            "verdict": "PASS" if positive >= MIN_POSITIVE_FOLDS else "FAIL",
            "positive": positive, "min_positive": MIN_POSITIVE_FOLDS,
            "min_fold_n": MIN_FOLD_N, "folds": folds}


# --- Stage 3 -------------------------------------------------------------------------

def stage3(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest
    clauses on the floor-moved stratum, week-clustered, permutation n = 200."""
    baseline, component = arm_trades(floor_moved(rows, key), key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation", permutation_p=p,
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"stage": 3, "arm": arm, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "n_permutations": PERMUTATION_N, "gate": render_json(result)}


# --- the family ----------------------------------------------------------------------

def _family_p(out) -> float:
    p = None if out is None else out.get("permutation_p")
    return 1.0 if p is None else float(p)


def _family_arm(out, p, p_holm, q) -> dict:
    verdict = None if out is None else out.get("verdict")
    return {"reached_stage3": out is not None, "stage3_verdict": verdict, "p": p,
            "p_holm": p_holm, "q_bh": q, "pass": verdict == "PASS" and p_holm < HOLM_ALPHA}


def holm_family(stage3_by_arm: dict) -> dict:
    """Holm across the two arms' Stage 3 permutation p. An arm that never
    reached Stage 3 (or carries no p) enters as p = 1.0. BH q is reported."""
    pvalues = {arm: _family_p(stage3_by_arm.get(arm)) for arm in FAMILY}
    adjusted = holm(pvalues)
    qvalues = ledger_qvalues([{"id": arm, "p": p} for arm, p in pvalues.items()])
    arms = {arm: _family_arm(stage3_by_arm.get(arm), pvalues[arm], adjusted[arm], qvalues[arm])
            for arm in FAMILY}
    return {"stage": "family", "method": "holm", "alpha": HOLM_ALPHA, "primary": PRIMARY_ARM,
            "arms": arms, "passed": [arm for arm in FAMILY if arms[arm]["pass"]]}


# --- report (spec § Reporting; informational, nothing gates) -----------------------------

def _median(values) -> float | None:
    vals = [v for v in values if v is not None]
    return float(statistics.median(vals)) if vals else None


def _summary(rows, key, n_resamples, seed, *, interval=True) -> dict:
    baseline, component = arm_trades(rows, key)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    out = {"n_rows": len(rows), "n_baseline": len(baseline), "n_component": len(component),
           "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
           "delta_expr": delta_expectancy_r(baseline, component),
           "delta_expr_lo95": None, "delta_expr_hi95": None,
           "wr_baseline": wr_base, "wr_component": wr_cell, "delta_wr_pp": _pp(wr_cell, wr_base),
           "flips": _flips(rows, key)}
    if interval and baseline and component:
        boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                               n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
        out["delta_expr_lo95"], out["delta_expr_hi95"] = boot.lo, boot.hi
    return out


def _groups(rows, name_of) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(str(name_of(row)), []).append(row)
    return dict(sorted(out.items()))


def _by(rows, key, n_resamples, seed, name_of, *, interval=True) -> dict:
    return {name: _summary(group, key, n_resamples, seed, interval=interval)
            for name, group in _groups(rows, name_of).items()}


def _regime_of(key):
    def name(row):
        record = row["cells"][key] or row["baseline"] or {}
        return record.get("regime2_state") or "unknown"
    return name


def _top_two_share(rows, key) -> float | None:
    counts = Counter(r["horizon_key"] for r in rows if r["cells"][key] is not None)
    total = sum(counts.values())
    return sum(n for _, n in counts.most_common(2)) / total if total else None


def _dollar_side(records) -> dict:
    out = {"pnl": round(sum(r["dollar_pnl"] for r in records), 2)}
    for direction in ("bullish", "bearish"):
        out[f"exceed_{direction}"] = sum(1 for r in records if r["direction"] == direction
                                         and r["dollar_exceeds_budget"])
    return out


def _dollars(rows, key) -> dict:
    base, comp = _sides(rows, key)
    budget = REFERENCE_ACCOUNT["balance"] * REFERENCE_ACCOUNT["risk_pct"] / 100.0
    return {"budget": budget, "baseline": _dollar_side(base), "component": _dollar_side(comp)}


def _two_sided_median(base, comp, field, horizon=None) -> dict:
    def pick(records):
        return _median(r[field] for r in records if horizon is None or r["horizon_key"] == horizon)
    return {"baseline": pick(base), "component": pick(comp)}


def _stop_distance(rows, key) -> dict:
    base, comp = _sides(rows, key)
    horizons = sorted({r["horizon_key"] for r in base + comp})
    return {"median_pct": _two_sided_median(base, comp, "stop_distance_pct"),
            "median_atr": _two_sided_median(base, comp, "stop_distance_atr"),
            "median_pct_by_horizon": {h: _two_sided_median(base, comp, "stop_distance_pct", h)
                                      for h in horizons}}


def _newly(rows, key) -> dict:
    new = [r for r in rows if r["newly_admitted"][key]]
    per_day = Counter(r["entry_date"] for r in new)
    return {"n": len(new), "alert_days": len(per_day),
            "max_per_day": max(per_day.values(), default=0),
            "mean_per_day": len(new) / len(per_day) if per_day else None,
            "median_adv_dollars": _median(r["adv_dollars"] for r in new)}


def _mean_gap_overshoot(records) -> float | None:
    overshoots = [r["gap_overshoot_r"] for r in records
                  if r["gap_through"] and r["gap_overshoot_r"] is not None]
    return sum(overshoots) / len(overshoots) if overshoots else None


def _exit_side(records) -> dict:
    return {"exit_mix": dict(Counter(r["exit_mix"] for r in records)),
            "early_stops": sum(1 for r in records if r["early_stop"]),
            "gap_through": sum(1 for r in records if r["gap_through"]),
            "mean_gap_overshoot_r": _mean_gap_overshoot(records),
            "fill_beyond_ceiling": sum(1 for r in records if r["fill_beyond_ceiling"])}


def _exits(rows, key) -> dict:
    base, comp = _sides(rows, key)
    return {"baseline": _exit_side(base), "component": _exit_side(comp)}


def _volume(rows, key, baseline, component) -> dict:
    n_base = sum(1 for t in baseline if t.outcome in CLOSED)
    n_comp = sum(1 for t in component if t.outcome in CLOSED)
    return {"n_baseline": n_base, "n_component": n_comp,
            "change_pct": (n_comp - n_base) / n_base * 100.0 if n_base else None,
            "removed_rows": sum(1 for r in rows
                                if r["baseline"] is not None and r["cells"][key] is None)}


def report(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """Everything spec § Reporting asks for one arm and cell. The decision
    stratum is floor-moved; the moved_by split covers every row."""
    stratum = floor_moved(rows, key)
    baseline, component = arm_trades(stratum, key)
    only_base, only_cell = _triggered_once(stratum, key)
    return {
        "arm": arm, "cell": key, "decision_stratum": MOVED_FLOOR,
        "floor_moved": _summary(stratum, key, n_resamples, seed),
        "by_moved_by": _by(rows, key, n_resamples, seed, lambda r: r["moved_by"].get(key)),
        "by_direction": _by(stratum, key, n_resamples, seed, lambda r: r["direction"]),
        "by_horizon": _by(stratum, key, n_resamples, seed, lambda r: r["horizon_key"]),
        "top_two_horizon_share": _top_two_share(stratum, key),
        "regime2": _by(stratum, key, n_resamples, seed, _regime_of(key), interval=False),
        "dollars": _dollars(stratum, key),
        "stop_distance": _stop_distance(stratum, key),
        "newly_admitted": _newly(stratum, key),
        "exits": _exits(stratum, key),
        "volume": _volume(stratum, key, baseline, component),
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
    }
