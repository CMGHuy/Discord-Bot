import json

import pytest

from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows, vc
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, '_full_universe', lambda: UNIVERSE)


def stamped(tmp_path, stage, dryup=True):
    baseline, component = rows()
    baseline = [dict(row, strategy='RSI') for row in baseline]
    component = [dict(row, strategy='RSI') for row in component]
    component.append(dict(component[0], entry_date='2024-02-01'))
    knobs = {'PULLBACK_DRYUP_SCOPE': 'strategy', 'PULLBACK_DRYUP_MAX_RATIO': .75} if dryup else {'MIN_REWARD_PCT': 4}
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window,
                        universe=UNIVERSE, horizons=ALL_HORIZONS, engines=('strategy',),
                        knob_delta=knobs, engine_hash_baseline='h', engine_hash_component='h', changed_outcomes=1)
    path = tmp_path / 'arms.json'
    path.write_text(json.dumps({'provenance': stamp, 'baseline': baseline, 'component': component}))
    return path


def args(path, stage='validation'):
    common = ['--stage', stage, '--title', 't', '--window', 'w', '--resamples', '50']
    return common + (['--grid-arms', f'.75={path}'] if stage == 'selection' else ['--arms', str(path)])


def test_non_subset_validation_replaces_only_mechanism(tmp_path, monkeypatch, capsys):
    path = stamped(tmp_path, 'validation')
    output = tmp_path / 'out.json'
    command = args(path) + ['--out-json', str(output)]
    vc.main(command)
    original = json.loads(output.read_text())
    assert next(c for c in original['clauses'] if c['name'] == 'mechanism')['verdict'] == 'SKIPPED'
    monkeypatch.setattr(vc, '_baseline_ratios', lambda baseline, scope:
                        {t.key: 1.0 if t.outcome == 'loss' else .5 for t in baseline})
    vc.main(command + ['--dryup-mechanism'])
    changed = json.loads(output.read_text())
    assert next(c for c in changed['clauses'] if c['name'] == 'mechanism')['verdict'] == 'PASS'
    assert changed['clauses'][:5] == original['clauses'][:5]
    assert changed['split'] == original['split']
    assert '"scope": "strategy"' in capsys.readouterr().out


@pytest.mark.parametrize('stage', ['validation', 'selection'])
def test_refuses_non_dryup_arm(tmp_path, capsys, stage):
    assert vc.main(args(stamped(tmp_path, stage, False), stage) + ['--dryup-mechanism']) == 1
    assert 'refused:not-a-dryup-arm' in capsys.readouterr().err


def test_selection_reads_baseline_mechanism(tmp_path, monkeypatch, capsys):
    path = stamped(tmp_path, 'selection')
    monkeypatch.setattr(vc, '_baseline_ratios', lambda baseline, scope:
                        {t.key: 1.0 if t.outcome == 'loss' else .5 for t in baseline})
    assert vc.main(args(path, 'selection') + ['--dryup-mechanism']) == 1
    printed = capsys.readouterr().out
    assert '"none": 0' in printed
    assert "'mechanism'" not in printed
    assert 'spike' in printed
