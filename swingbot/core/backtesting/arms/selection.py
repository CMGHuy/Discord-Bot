"""Fold-train selection: eligibility, neighbouring plateaus and disclosure."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from swingbot.core.backtesting import acceptance, backtest_wf

SELECTED = 'selected'
NO_ELIGIBLE = 'no-eligible-cell'
SPIKE = 'spike'
ELIGIBILITY_CLAUSES = ('profit_floor', 'geometry', 'volume', 'mechanism')


@dataclass(frozen=True)
class CellEval:
    value: float
    eligible: bool
    delta_win_rate_pp: float | None
    expectancy_r: float | None
    failed: list
    disclosure: dict


@dataclass(frozen=True)
class Selection:
    cells: list
    selected: float | None
    plateau: dict | None
    verdict: str


def with_clause(result, clause):
    """Replace one clause without changing the acceptance clause order."""
    clauses = tuple(clause if item.name == clause.name else item for item in result.clauses)
    verdict = 'FAIL' if any(item.verdict == 'FAIL' for item in clauses) else 'PASS'
    return replace(result, clauses=clauses, verdict=verdict)


def _direction_disclosure(baseline, component, direction):
    before = [trade for trade in baseline if trade.direction == direction]
    after = [trade for trade in component if trade.direction == direction]
    return {'n_baseline': len(before), 'n_component': len(after),
            'delta_win_rate_pp': acceptance.delta_standardised_win_rate(before, after),
            'delta_expectancy_r': acceptance.delta_expectancy_r(before, after)}


def removed_disclosure(baseline, component):
    """Describe removals separately from added entries and changed outcomes."""
    split = acceptance.population_split(baseline, component)
    removed = split['removed']
    directions = Counter(trade.direction for trade in removed)
    horizons = Counter(trade.horizon_key for trade in removed)
    dominant = next((direction for direction, count in directions.items()
                     if count > .8 * len(removed)), None)
    return {'removed': len(removed), 'added': len(split['added']),
            'changed': len(split['changed']), 'is_subset': split['is_subset'],
            'removed_by_direction': dict(directions),
            'top2_horizon_share': sum(count for _, count in horizons.most_common(2)) / len(removed) if removed else 0.0,
            'one_direction': dominant,
            'per_direction': {direction: _direction_disclosure(baseline, component, direction)
                              for direction in ('bullish', 'bearish')}}


def evaluate_cell(value, baseline, component, *, resolvable, n_resamples, seed,
                  mechanism=None):
    """Score only clauses 2–4 and 6 plus the preceding MDE refusal."""
    result = acceptance.evaluate(baseline, component, stage='walkforward',
                                 n_resamples=n_resamples, seed=seed)
    if mechanism is not None:
        result = with_clause(result, mechanism)
    failed = [name for name in ELIGIBILITY_CLAUSES if result.clause(name).verdict != 'PASS']
    if not resolvable:
        failed.append('mde')
    return CellEval(value, not failed, acceptance.delta_standardised_win_rate(baseline, component),
                    acceptance.expectancy_r(component), failed, removed_disclosure(baseline, component))


def _has_eligible_neighbor(cells, index):
    return any(cells[neighbor].eligible for neighbor in (index - 1, index + 1)
               if 0 <= neighbor < len(cells))


def _plateau_candidates(cells, param_name):
    grid = [cell.value for cell in cells]
    expectancies = [float('nan') if cell.expectancy_r is None else cell.expectancy_r for cell in cells]
    candidates = []
    for index, cell in enumerate(cells):
        if not cell.eligible or not _has_eligible_neighbor(cells, index):
            continue
        plateau = backtest_wf.plateau_report(param_name, grid, expectancies, cell.value)
        if plateau['is_plateau']:
            candidates.append((cell, plateau))
    return candidates


def _selection_rank(candidate):
    cell, _ = candidate
    improvement = float('-inf') if cell.delta_win_rate_pp is None else cell.delta_win_rate_pp
    return improvement, cell.value


def select_cell(cells, param_name):
    """Select maximum dWR among eligible adjacent plateaus; ties cut less."""
    ordered = sorted(cells, key=lambda cell: cell.value)
    if not any(cell.eligible for cell in ordered):
        return Selection(ordered, None, None, NO_ELIGIBLE)
    candidates = _plateau_candidates(ordered, param_name)
    if not candidates:
        return Selection(ordered, None, None, SPIKE)
    chosen, plateau = max(candidates, key=_selection_rank)
    return Selection(ordered, chosen.value, plateau, SELECTED)
