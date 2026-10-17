# tests/backtesting/test_validate_component_headroom.py
"""--headroom-mechanism: the v135 baseline reading replaces acceptance.py's mechanism
clause, selects on HEADROOM_MIN_R, and breaks a tie toward the smaller h."""
import json

import pytest

from swingbot.core.backtesting.arms.headroom_clauses import Reading
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows, vc
from tests.backtesting.test_validate_component_stamps import _legacy_source  # noqa: F401 v162 pin

NEAR, CLEAR = Reading((0.5, 2.0), 3), Reading(None, 3)   # 0.25R away: inside every grid value


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, '_full_universe', lambda: UNIVERSE)


@pytest.fixture
def losers_blocked(monkeypatch):
    seen = []

    def readings(baseline, scope, window):
        seen.append((scope, window))
        return {t.key: NEAR if t.outcome == 'loss' else CLEAR for t in baseline}
    monkeypatch.setattr(vc, '_baseline_headroom', readings)
    return seen


def stamped(tmp_path, stage, min_r=.75, headroom=True, replacement=True):
    baseline, component = rows()
    baseline = [dict(row, strategy='RSI') for row in baseline]
    component = [dict(row, strategy='RSI') for row in component]
    if replacement:
        component.append(dict(component[0], entry_date='2024-02-01'))
    knobs = {'HEADROOM_SCOPE': 'strategy', 'HEADROOM_MIN_R': min_r} if headroom else {'MIN_REWARD_PCT': 4}
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window,
                        universe=UNIVERSE, horizons=ALL_HORIZONS, engines=('strategy',),
                        knob_delta=knobs, engine_hash_baseline='h', engine_hash_component='h',
                        changed_outcomes=1)
    path = tmp_path / f'arms-{min_r}.json'
    path.write_text(json.dumps({'provenance': stamp, 'baseline': baseline, 'component': component}))
    return path


def args(path, stage='validation'):
    common = ['--stage', stage, '--title', 't', '--window', 'w', '--resamples', '50']
    return common + (['--grid-arms', f'.75={path}'] if stage == 'selection' else ['--arms', str(path)])


def _mechanism(path):
    return next(c for c in json.loads(path.read_text())['clauses'] if c['name'] == 'mechanism')['verdict']


def test_non_subset_validation_replaces_only_mechanism(tmp_path, losers_blocked, capsys):
    path, output = stamped(tmp_path, 'validation'), tmp_path / 'out.json'
    command = args(path) + ['--out-json', str(output)]
    vc.main(command)
    original = json.loads(output.read_text())
    assert _mechanism(output) == 'SKIPPED'
    vc.main(command + ['--headroom-mechanism'])
    changed = json.loads(output.read_text())
    assert _mechanism(output) == 'PASS'
    assert changed['clauses'][:5] == original['clauses'][:5]
    assert changed['split'] == original['split']
    printed = capsys.readouterr().out
    assert '"scope": "strategy"' in printed and '"no_map": 0' in printed
    assert losers_blocked == [('strategy', tuple(STAGES['validation'].signal_window))]


@pytest.mark.parametrize('stage', ['validation', 'selection'])
def test_refuses_an_arm_without_headroom_knobs(tmp_path, capsys, stage):
    path = stamped(tmp_path, stage, headroom=False)
    assert vc.main(args(path, stage) + ['--headroom-mechanism']) == 1
    assert 'refused:not-a-headroom-arm' in capsys.readouterr().err


def test_selection_ties_go_to_the_smaller_h(tmp_path, losers_blocked, capsys):
    command = ['--stage', 'selection', '--title', 'HEADROOM_MIN_R', '--window', 'train',
               '--resamples', '200', '--headroom-mechanism']
    for value in (.5, .75, 1.0):
        command += ['--grid-arms', f'{value}={stamped(tmp_path, "selection", value, replacement=False)}']
    output = tmp_path / 'stage1.json'
    assert vc.main(command + ['--out-json', str(output)]) == 0
    printed = capsys.readouterr().out
    assert all(f'h={value}' in printed for value in (.5, .75, 1.0))
    assert 'selected=0.5' in printed
    assert json.loads(output.read_text())['selected'] == .5


def test_the_two_mechanism_readings_are_mutually_exclusive(tmp_path):
    path = stamped(tmp_path, 'validation')
    with pytest.raises(SystemExit):
        vc.main(args(path) + ['--headroom-mechanism', '--dryup-mechanism'])


def test_selection_axis_defaults_to_v122s():
    import argparse
    assert vc._selection_axis(argparse.Namespace()) == ('PULLBACK_DRYUP_MAX_RATIO', 'd', 'larger')
    assert vc._selection_axis(argparse.Namespace(headroom_mechanism=True)) == ('HEADROOM_MIN_R', 'h', 'smaller')
