"""Pre-registered v127 structure-break armed-entry measurement (spec §3.3, §4).

The constants below ARE the pre-registration. None is a config.Field, so
no search can sweep them, and none may change after a number is seen.
Scoring, the selection-rule arithmetic, the fold/arms blobs and the
permutation p are armed_measurement's, reused unchanged; this module adds
only the 12-cell grid, the categorical `trigger` axis and the population
disclosure. v90's grid (armed_measurement.CELLS) is not touched.
"""
from __future__ import annotations

import dataclasses
from collections import Counter

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting.armed_measurement import (  # noqa: F401  (re-exported for the script)
    BASELINE, FOLD_TEST_YEARS, LIMITATIONS, MDE_TARGET_DAYS, NO_ELIGIBLE_CELL,
    PERMUTATION_N, PERMUTATION_SEED, RUN1_WINDOW, SELECTED, SELECTION_OBSERVED_DAYS,
    SELECTION_WINDOW, SPIKE, VALIDATION_WINDOW, Row, Selection, arm_trades, arms_blob,
    folds_blob, in_window, permutation_p,
)
from swingbot.core.backtesting.backtest_wf import plateau_report
from swingbot.core.backtesting.structure_arm import TRIGGERS, StructCell

N_GRID = (5, 10, 15)
K_GRID = (0.25, 0.5)
CELLS = tuple(StructCell(t, n, k) for t in TRIGGERS for n in N_GRID for k in K_GRID)
FUNNEL_COLUMNS = ("armed", "issued", "regated", "cancelled_zone_failed", "expired", "unresolved")

SELECTION_RULE = (
    "A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), "
    "ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible "
    "cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. "
    "The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along N and "
    "along k with the other knobs held; any spike disqualifies. `trigger` is categorical: "
    "both trigger rows at the selected N and k are reported, not plateau-checked."
)


def cell_by_id(cell_id: str) -> StructCell:
    for cell in CELLS:
        if cell.cell_id == cell_id:
            return cell
    raise KeyError(cell_id)


def _plateau(best: StructCell, scores: dict, knob: str, grid) -> dict:
    expectancies = []
    for value in grid:
        score = scores.get(dataclasses.replace(best, **{knob: value}).cell_id)
        value_r = None if score is None else score.component_expectancy_r
        expectancies.append(float("nan") if value_r is None else value_r)
    return plateau_report(f"STRUCT_{knob.upper()}", list(grid), expectancies, getattr(best, knob))


def select_cell(rows, cells=CELLS) -> Selection:
    scores = {cell.cell_id: am.score_cell(rows, cell) for cell in cells}
    eligible = [cell for cell in cells if scores[cell.cell_id].eligible]
    if not eligible:
        return Selection(tuple(scores.values()), None, None, (), NO_ELIGIBLE_CELL)
    best = max(eligible, key=lambda c: (scores[c.cell_id].delta_expectancy_r,
                                        scores[c.cell_id].delta_win_rate_pp, -c.n))
    plateaus = (_plateau(best, scores, "n", N_GRID), _plateau(best, scores, "k", K_GRID))
    on_plateau = all(p["is_plateau"] for p in plateaus)
    return Selection(tuple(scores.values()), best.cell_id if on_plateau else None,
                     best.cell_id, plateaus, SELECTED if on_plateau else SPIKE)


def trigger_rows(selection: Selection) -> list:
    """Both triggers' scores at the rule's pick's N and k (spec §4.1)."""
    if selection.best is None:
        return []
    best = cell_by_id(selection.best)
    wanted = {dataclasses.replace(best, trigger=t).cell_id for t in TRIGGERS}
    return [s for s in selection.scores if s.cell_id in wanted]


def _bucket(status: str) -> str:
    return "regated" if status.startswith("regate_") else status


def funnel(arm_records, window) -> dict:
    """Per cell: arms opened in `window` by how they ended (spec §4.3)."""
    out = {cell.cell_id: Counter() for cell in CELLS}
    for rec in arm_records:
        if window[0] <= rec["arm_date"] <= window[1] and rec["cell"] in out:
            out[rec["cell"]]["armed"] += 1
            out[rec["cell"]][_bucket(rec["status"])] += 1
    return {cell_id: {col: counts.get(col, 0) for col in FUNNEL_COLUMNS}
            for cell_id, counts in out.items()}


def _fmt(value, spec):
    return "n/a" if value is None else format(value, spec)


def _score_line(s) -> str:
    return (f"| {s.cell_id} | {s.baseline_n} | {s.component_n} | {s.volume_cut_pct:+.2f} | "
            f"{_fmt(s.delta_win_rate_pp, '+.2f')} | {_fmt(s.delta_expectancy_r, '+.4f')} | "
            f"{_fmt(s.component_expectancy_r, '+.4f')} | {'yes' if s.eligible else 'no'} | "
            f"{'; '.join(s.reasons)} |")


_SCORE_HEAD = ["| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |",
               "|---|---|---|---|---|---|---|---|---|"]


def _funnel_lines(selection: Selection, funnel_counts: dict) -> list:
    ratios = {s.cell_id: (s.component_n / s.baseline_n if s.baseline_n else None)
              for s in selection.scores}
    lines = ["## Population disclosure (arms opened in the selection window)", "",
             "| cell | " + " | ".join(FUNNEL_COLUMNS) + " | alert-volume ratio |",
             "|---|" + "---|" * (len(FUNNEL_COLUMNS) + 1)]
    for cell_id, counts in funnel_counts.items():
        lines.append(f"| {cell_id} | " + " | ".join(str(counts[c]) for c in FUNNEL_COLUMNS)
                     + f" | {_fmt(ratios.get(cell_id), '.3f')} |")
    return lines


def _plateau_lines(selection: Selection) -> list:
    if not selection.plateaus:
        return []
    lines = ["## Plateau reports (N and k; trigger is categorical)", ""]
    for p in selection.plateaus:
        lines.append(f"- {p['param']}: grid {p['grid']}, expectancies "
                     f"{[round(e, 4) for e in p['expectancies']]}, adopted {p['adopted']}, "
                     f"plateau {p['is_plateau']}")
    lines += ["", "## Both triggers at the pick's N and k (not plateau-checked)", "", *_SCORE_HEAD]
    lines += [_score_line(s) for s in trigger_rows(selection)]
    return lines + [""]


def render_selection_md(selection: Selection, funnel_counts: dict) -> str:
    lines = ["# v127 structure-break armed entries — Stage 1 selection", "",
             f"**Verdict: {selection.verdict}**", "",
             f"Window: {SELECTION_WINDOW[0]}..{SELECTION_WINDOW[1]} (fold-train only).", "",
             "## Pre-registered rule", "", SELECTION_RULE, "", LIMITATIONS, "",
             f"## All {len(selection.scores)} cells", "", *_SCORE_HEAD]
    lines += [_score_line(s) for s in selection.scores]
    lines += ["", f"Rule's pick before the plateau check: {selection.best or 'none'}",
              f"Selected for Stage 0: {selection.selected or 'none'}", ""]
    lines += _plateau_lines(selection)
    lines += _funnel_lines(selection, funnel_counts)
    return "\n".join(lines) + "\n"
