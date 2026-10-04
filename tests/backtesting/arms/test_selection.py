from dataclasses import replace

import pytest

from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult, evaluate
from swingbot.core.backtesting.arms.selection import (
    NO_ELIGIBLE, SELECTED, SPIKE, evaluate_cell, removed_disclosure,
    select_cell, with_clause,
)


def arms(drop=0, winners=False):
    baseline, component = [], []
    for ticker in range(25):
        for index in range(100):
            win = index < 40
            trade = ArmTrade(f'T{ticker}', 'MACD', '3m', str(index),
                             'win' if win else 'loss', 2.0 if win else -1.0,
                             2.0, 'strategy', 'bullish')
            baseline.append(trade)
            removed = index < drop if winners else 40 <= index < 40 + drop
            if not removed:
                component.append(trade)
    return baseline, component


def cell(value, drop=1, **kwargs):
    return evaluate_cell(value, *arms(drop), resolvable=True,
                         n_resamples=20, seed=42, **kwargs)


def test_eligible_plateau_selects_largest_improvement():
    cells = [cell(.60, 3), cell(.75, 2), cell(.90, 1)]
    assert all(c.eligible for c in cells)
    result = select_cell(cells, 'd')
    assert result.verdict == SELECTED
    assert result.selected == .60
    assert result.plateau['is_plateau']


def test_tie_prefers_larger_value():
    assert select_cell([cell(.75), cell(.90)], 'd').selected == .90


def test_removing_winners_fails_mechanism():
    result = evaluate_cell(.60, *arms(1, winners=True), resolvable=True,
                           n_resamples=20, seed=42)
    assert not result.eligible
    assert 'mechanism' in result.failed


@pytest.mark.parametrize('verdict,eligible', [('FAIL', False), ('PASS', True)])
def test_mechanism_override(verdict, eligible):
    result = cell(.60, mechanism=ClauseResult('mechanism', verdict, 'supplied'))
    assert result.eligible is eligible


def test_with_clause_recomputes_verdict_and_preserves_order():
    result = evaluate(*arms(1), stage='walkforward', n_resamples=20)
    failed = with_clause(result, ClauseResult('mechanism', 'FAIL', 'supplied'))
    assert failed.verdict == 'FAIL'
    restored = with_clause(failed, ClauseResult('mechanism', 'PASS', 'supplied'))
    assert restored.verdict == 'PASS'
    assert [c.name for c in restored.clauses] == [c.name for c in result.clauses]


def test_isolated_eligible_cell_is_a_spike():
    good = cell(.75)
    bad = replace(good, eligible=False, failed=['mde'])
    assert select_cell([replace(bad, value=.60), good, replace(bad, value=.90)], 'd').verdict == SPIKE


def test_no_eligible_cells():
    assert select_cell([replace(cell(.60), eligible=False)], 'd').verdict == NO_ELIGIBLE


def test_mde_refusal_blocks_cell():
    result = evaluate_cell(.60, *arms(1), resolvable=False, n_resamples=20, seed=42)
    assert not result.eligible and 'mde' in result.failed


def test_skipped_mechanism_is_ineligible():
    result = cell(.60, mechanism=ClauseResult('mechanism', 'SKIPPED', 'none'))
    assert not result.eligible and 'mechanism' in result.failed


def replacement_disclosure():
    baseline, _ = arms()
    removed = [t for t in baseline if t.outcome == 'loss'][:30]
    component = [t for t in baseline if t not in removed]
    component.append(replace(baseline[0], ticker='added'))
    return removed_disclosure(baseline, component)


def test_removal_disclosure_counts_replacements():
    disclosure = replacement_disclosure()
    assert disclosure['removed'] == 30
    assert disclosure['added'] == 1 and not disclosure['is_subset']


def test_removal_disclosure_reports_direction_and_concentration():
    disclosure = replacement_disclosure()
    assert disclosure['one_direction'] == 'bullish'
    assert disclosure['top2_horizon_share'] == 1
    assert disclosure['removed_by_direction']['bullish'] == 30
    assert set(disclosure['per_direction']) == {'bullish', 'bearish'}
    assert disclosure['per_direction']['bullish']['n_baseline'] == 2500



def test_eligible_neighbors_with_expectancy_spike_are_refused():
    cells = [replace(cell(.75), expectancy_r=0), replace(cell(.90), expectancy_r=1)]
    assert select_cell(cells, 'd').verdict == SPIKE


def test_missing_neighbor_expectancy_cannot_make_a_plateau():
    cells = [cell(.75), replace(cell(.90), expectancy_r=None)]
    assert select_cell(cells, 'd').verdict == SPIKE
