"""Pre-registered v88 armed-entry measurement arithmetic (spec §3.5, §4).

Every stage decision is computed here from replay rows; the script
(scripts/backtest/measure_armed_entries.py) only moves rows between the
replay and disk. The constants below ARE the pre-registration. None is a
config.Field, so no search can sweep them, and none may change after a
number is seen -- a failed selection closes the measurement.
"""
from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass

import numpy as np

from swingbot.core.backtesting.acceptance import (
    NON_INFERIORITY_R, VOLUME_MAX_CUT_PCT, ArmTrade, delta_expectancy_r,
    delta_standardised_win_rate, expectancy_r,
)
from swingbot.core.backtesting.armed_replay import Cell
from swingbot.core.backtesting.backtest_wf import plateau_report

N_GRID = (3, 5, 10)
K_GRID = (0.25, 0.5)
B_GRID = (0.00, 0.05, 0.10, 0.15, 0.20)
CELLS = tuple(Cell(n, k, b) for n in N_GRID for k in K_GRID for b in B_GRID)
BASELINE = "baseline"

RUN1_WINDOW = ("2018-06-01", "2023-12-31")
SELECTION_WINDOW = ("2018-06-01", "2020-12-31")   # precedes every fold-test year
SELECTION_OBSERVED_DAYS, MDE_TARGET_DAYS = 945, 730
FOLD_TEST_YEARS = ("2021", "2022", "2023")
VALIDATION_WINDOW = ("2024-01-01", "2025-12-31")
PERMUTATION_N, PERMUTATION_SEED = 200, 42

SELECTED, NO_ELIGIBLE_CELL, SPIKE = "SELECTED", "NO_ELIGIBLE_CELL", "SPIKE"

SELECTION_RULE = (
    "A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), "
    "ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible "
    "cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. "
    "The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along each "
    "of N, k and b with the other knobs held; any spike disqualifies."
)

# Spec §4.3: quoted in every results doc this measurement writes.
LIMITATIONS = (
    "Recorded limitations: daily-bar ordering is conservative (stop before target on the "
    "same bar); the universe is today's cached tickers (survivorship)."
)


@dataclass(frozen=True)
class Row:
    arm: str                  # BASELINE or a Cell.cell_id
    trade: ArmTrade
    reaction: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "Row":
        return cls(value["arm"], ArmTrade(**value["trade"]), value.get("reaction"))


def cell_by_id(cell_id: str) -> Cell:
    for cell in CELLS:
        if cell.cell_id == cell_id:
            return cell
    raise KeyError(cell_id)


def in_window(rows, window):
    return [row for row in rows if window[0] <= row.trade.entry_date <= window[1]]


def in_year(rows, year):
    return [row for row in rows if row.trade.entry_date.startswith(year)]


def arm_trades(rows, arm) -> list[ArmTrade]:
    return [row.trade for row in rows if row.arm == arm]


V88_B_GRID = (0.10, 0.25)      # the b values v88 actually ran, for the overlap only


def _trade_key(trade) -> tuple:
    return (trade.ticker, trade.strategy, trade.horizon_key, trade.entry_date)


def overlap_report(rows, v88_rows) -> list[dict]:
    """Spec §3.3: how much of each cell's confirmed population is the same
    trades v88 already showed as R1, and how much the released R2/R3
    cooldown added. `v88_rows` carry v88's mode-bearing cell ids; a v90
    cell whose `b` v88 never ran has no counterpart and reports None.
    """
    v88_by_cell: dict = {}
    for row in v88_rows:
        if row.reaction == "R1":
            v88_by_cell.setdefault(row.arm, set()).add(_trade_key(row.trade))
    out = []
    for cell in CELLS:
        mine = {_trade_key(row.trade) for row in rows if row.arm == cell.cell_id}
        if cell.b not in V88_B_GRID:
            out.append({"cell_id": cell.cell_id, "n": len(mine), "v88_r1_n": None,
                        "shared": None, "new_here": None, "only_in_v88": None})
            continue
        theirs: set = set()
        for mode in ("M1", "M2"):
            theirs |= v88_by_cell.get(f"{mode}-{cell.cell_id}", set())
        out.append({"cell_id": cell.cell_id, "n": len(mine), "v88_r1_n": len(theirs),
                    "shared": len(mine & theirs), "new_here": len(mine - theirs),
                    "only_in_v88": len(theirs - mine)})
    return out


@dataclass(frozen=True)
class CellScore:
    cell_id: str
    baseline_n: int
    component_n: int
    volume_cut_pct: float
    delta_win_rate_pp: float | None
    delta_expectancy_r: float | None
    component_expectancy_r: float | None
    eligible: bool
    reasons: tuple[str, ...]


def score_cell(rows, cell: Cell) -> CellScore:
    baseline, component = arm_trades(rows, BASELINE), arm_trades(rows, cell.cell_id)
    cut = 100.0 * (len(baseline) - len(component)) / len(baseline) if baseline else 100.0
    dwr = delta_standardised_win_rate(baseline, component)
    dexpr = delta_expectancy_r(baseline, component)
    reasons = []
    if cut > VOLUME_MAX_CUT_PCT:
        reasons.append(f"volume: cut {cut:.2f}% > {VOLUME_MAX_CUT_PCT}%")
    if dexpr is None or dexpr < NON_INFERIORITY_R:
        reasons.append(f"profit: dExpR below {NON_INFERIORITY_R}R")
    if dwr is None or dwr <= 0:
        reasons.append("win rate: standardised dWR not above 0")
    return CellScore(cell.cell_id, len(baseline), len(component), cut, dwr, dexpr,
                     expectancy_r(component), not reasons, tuple(reasons))


@dataclass(frozen=True)
class Selection:
    scores: tuple[CellScore, ...]
    selected: str | None      # the cell that goes on to Stage 0; None unless SELECTED
    best: str | None          # the rule's pick before the plateau check
    plateaus: tuple[dict, ...]
    verdict: str


def select_cell(rows, cells=CELLS) -> Selection:
    scores = {cell.cell_id: score_cell(rows, cell) for cell in cells}
    eligible = [cell for cell in cells if scores[cell.cell_id].eligible]
    if not eligible:
        return Selection(tuple(scores.values()), None, None, (), NO_ELIGIBLE_CELL)
    best = max(eligible, key=lambda c: (scores[c.cell_id].delta_expectancy_r,
                                        scores[c.cell_id].delta_win_rate_pp, -c.n))
    plateaus = []
    for knob, grid in (("n", N_GRID), ("k", K_GRID), ("b", B_GRID)):
        variants = [dataclasses.replace(best, **{knob: value}) for value in grid]
        expectancies = []
        for variant in variants:
            score = scores.get(variant.cell_id)
            value = None if score is None else score.component_expectancy_r
            expectancies.append(float("nan") if value is None else value)
        plateaus.append(plateau_report(f"ARMED_{knob.upper()}", list(grid), expectancies,
                                       getattr(best, knob)))
    on_plateau = all(p["is_plateau"] for p in plateaus)
    return Selection(tuple(scores.values()), best.cell_id if on_plateau else None,
                     best.cell_id, tuple(plateaus), SELECTED if on_plateau else SPIKE)


def arms_blob(rows, cell_id: str) -> dict:
    return {"baseline": [asdict(t) for t in arm_trades(rows, BASELINE)],
            "component": [asdict(t) for t in arm_trades(rows, cell_id)]}


def folds_blob(rows, cell_id: str) -> dict:
    return {"folds": [{"test_year": year, **arms_blob(in_year(rows, year), cell_id)}
                      for year in FOLD_TEST_YEARS]}


def permutation_p(baseline, real_component, permuted_components) -> dict:
    """Spec §4.2: p = share of permuted mix-standardised ΔWR >= the real ΔWR."""
    real = delta_standardised_win_rate(baseline, real_component)
    permuted = [delta_standardised_win_rate(baseline, c) for c in permuted_components]
    valid = [value for value in permuted if value is not None]
    p_value = None if real is None or not valid else float(np.mean([v >= real for v in valid]))
    return {"real_delta_win_rate_pp": real, "p_value": p_value,
            "n": len(permuted), "n_valid": len(valid)}


def _fmt(value, spec):
    return "n/a" if value is None else format(value, spec)


def render_selection_md(selection: Selection, overlap: list | None = None) -> str:
    lines = ["# v90 rejection-only armed entries — Stage 1 selection", "",
             f"**Verdict: {selection.verdict}**", "",
             f"Window: {SELECTION_WINDOW[0]}..{SELECTION_WINDOW[1]} (fold-train only).", "",
             "## Pre-registered rule", "", SELECTION_RULE, "", LIMITATIONS, "",
             "## All 30 cells", "",
             "| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in selection.scores:
        lines.append(f"| {s.cell_id} | {s.baseline_n} | {s.component_n} | {s.volume_cut_pct:+.2f} | "
                     f"{_fmt(s.delta_win_rate_pp, '+.2f')} | {_fmt(s.delta_expectancy_r, '+.4f')} | "
                     f"{_fmt(s.component_expectancy_r, '+.4f')} | {'yes' if s.eligible else 'no'} | "
                     f"{'; '.join(s.reasons)} |")
    lines += ["", f"Rule's pick before the plateau check: {selection.best or 'none'}",
              f"Selected for Stage 0: {selection.selected or 'none'}", ""]
    if selection.plateaus:
        lines += ["## Plateau reports", ""]
        for p in selection.plateaus:
            lines.append(f"- {p['param']}: grid {p['grid']}, expectancies "
                         f"{[round(e, 4) for e in p['expectancies']]}, adopted {p['adopted']}, "
                         f"plateau {p['is_plateau']}")
    if overlap:
        lines += ["", "## Overlap with v88's R1 rows (spec §3.3)", "",
                  "This mechanism is not a re-label of v88's R1 population: dropping the "
                  "R2/R3 issuances releases arms their 5-bar cooldown suppressed, and those "
                  "arms shift later ones in turn. `n/a` means v88 never ran that `b`.", "",
                  "| cell | n | v88 R1 n | shared | new here | only in v88 |",
                  "|---|---|---|---|---|---|"]
        for row in overlap:
            lines.append(
                f"| {row['cell_id']} | {row['n']} | "
                + " | ".join("n/a" if row[key] is None else str(row[key])
                             for key in ("v88_r1_n", "shared", "new_here", "only_in_v88"))
                + " |")
    return "\n".join(lines) + "\n"
