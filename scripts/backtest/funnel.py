"""Grid-agnostic measurement funnel shared by v102, v103 and v104."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from swingbot.core.backtesting import acceptance, arm_rule

WR_FLOOR = 50.0
MIN_N_TRAIN = 30
MIN_N_VALIDATION = 15
MAX_SCRATCH_SHARE = 0.5
FOLD_MIN_N = 15
FOLD_POSITIVE_SHARE = 2 / 3
MIN_QUALIFYING_FOLDS = 3
TRAIN_START_YEAR = 2010
FOLD_YEARS = tuple(range(2013, 2024))
BOOTSTRAP_SEED = 42


def cell_key(value) -> str:
    return f"{float(value):g}"


def pooled(rows):
    return arm_rule.pooled_stats([SimpleNamespace(**row) for row in rows])


def dir_rows(rows, direction):
    return [row for row in rows if row["direction"] == direction]


def year_rows(rows, first, last):
    return [row for row in rows if first <= int(row["entry_date"][:4]) <= last]


def _floors(stats, min_n):
    return {
        "n": (stats.get("n") or 0) >= min_n,
        "scratch": (stats.get("scratch_timeout_share") is not None
                    and stats["scratch_timeout_share"] <= MAX_SCRATCH_SHARE),
    }


def badge_verdict(stats, min_n):
    clauses = {
        "wr": stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR,
        "exp_r": stats.get("expectancy_r") is not None and stats["expectancy_r"] > 0,
        **_floors(stats, min_n),
    }
    return {"clears": all(clauses.values()), "clauses": clauses}


def expr_lower_bound(rows, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
                     cluster="ticker"):
    trades = [SimpleNamespace(**row) for row in rows]
    draws = acceptance.cluster_bootstrap(
        [], trades, lambda _baseline, component: acceptance.expectancy_r(component),
        n_resamples=n_resamples, seed=seed, cluster=cluster,
    )
    if draws.size == 0:
        return None
    return float(np.percentile(draws, 100 * acceptance.ALPHA / 2))


def tier2_verdict(stats, lower_bound, min_n):
    clauses = {
        "exp_r": stats.get("expectancy_r") is not None and stats["expectancy_r"] > 0,
        "lower_bound": lower_bound is not None and lower_bound > 0,
        **_floors(stats, min_n),
    }
    return {"clears": all(clauses.values()), "clauses": clauses}


def score_cell(rows, min_n, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED,
               cluster="ticker"):
    stats = pooled(rows)
    lower_bound = (expr_lower_bound(rows, n_resamples=n_resamples, seed=seed, cluster=cluster)
                   if rows else None)
    tier1 = badge_verdict(stats, min_n)
    tier2 = tier2_verdict(stats, lower_bound, min_n)
    tier = 1 if tier1["clears"] else (2 if tier2["clears"] else None)
    return {"stats": stats, "lower_bound": lower_bound, "tier1": tier1, "tier2": tier2, "tier": tier}


def plateau_ok(passes, grid, value):
    index = list(grid).index(value)
    neighbours = [grid[i] for i in (index - 1, index + 1) if 0 <= i < len(grid)]
    return bool(passes[value]) and all(passes[neighbour] for neighbour in neighbours)


def _pick_winner(cells, plateau1, plateau2):
    for tier, plateau in ((1, plateau1), (2, plateau2)):
        if plateau:
            return max(plateau, key=lambda value: cells[value]["stats"]["expectancy_r"]), tier
    return None, None


def stage1(rows_by_cell, direction, grid, *, n_resamples=acceptance.BOOTSTRAP_RESAMPLES,
           seed=BOOTSTRAP_SEED, cluster="ticker"):
    cells = {
        value: score_cell(dir_rows(rows_by_cell[cell_key(value)], direction), MIN_N_TRAIN,
                          n_resamples=n_resamples, seed=seed, cluster=cluster)
        for value in grid
    }
    tier1 = {value: cells[value]["tier1"]["clears"] for value in grid}
    tier2 = {value: cells[value]["tier2"]["clears"] for value in grid}
    plateau1 = [value for value in grid if plateau_ok(tier1, grid, value)]
    plateau2 = [value for value in grid if plateau_ok(tier2, grid, value)]
    winner, winner_tier = _pick_winner(cells, plateau1, plateau2)
    return {"cells": {cell_key(value): cell for value, cell in cells.items()},
            "plateau_tier1": plateau1, "plateau_tier2": plateau2,
            "winner": winner, "winner_tier": winner_tier}


def fold_pick(rows_by_cell, direction, year, grid):
    best = None
    for value in grid:
        stats = pooled(dir_rows(year_rows(rows_by_cell[cell_key(value)], TRAIN_START_YEAR, year - 1), direction))
        if stats["n"] < MIN_N_TRAIN or stats["expectancy_r"] is None:
            continue
        if best is None or stats["expectancy_r"] > best[1]:
            best = (value, stats["expectancy_r"])
    return None if best is None else best[0]


def fold_verdict(folds):
    qualifying = [fold for fold in folds if fold["stats"] is not None and fold["stats"]["n"] >= FOLD_MIN_N]
    positive = sum(1 for fold in qualifying if fold["stats"]["expectancy_r"] is not None and fold["stats"]["expectancy_r"] > 0)
    clears = len(qualifying) >= MIN_QUALIFYING_FOLDS and positive >= FOLD_POSITIVE_SHARE * len(qualifying)
    return {"clears": clears, "qualifying": len(qualifying), "positive": positive,
            "unselected": sum(1 for fold in folds if fold["tol"] is None)}


def stage2(rows_by_cell, direction, grid, fold_years=FOLD_YEARS):
    folds = []
    for year in fold_years:
        value = fold_pick(rows_by_cell, direction, year, grid)
        stats = pooled(dir_rows(year_rows(rows_by_cell[cell_key(value)], year, year), direction)) if value is not None else None
        folds.append({"test_year": year, "tol": value, "stats": stats})
    return {"folds": folds, "verdict": fold_verdict(folds)}


def fixed_folds(rows, fold_years):
    """Return per-year stats for one fixed arm without re-selecting a grid."""
    return [{"test_year": year, "tol": "fixed", "stats": pooled(year_rows(rows, year, year))}
            for year in fold_years]


def assert_rows_before(rows, last_date):
    """Refuse rows entered after ``last_date`` to prevent a holdout leak."""
    late = [row["entry_date"] for row in rows if row["entry_date"] > last_date]
    if late:
        raise SystemExit(f"{len(late)} row(s) after {last_date} (first {min(late)}): holdout leak refused")
