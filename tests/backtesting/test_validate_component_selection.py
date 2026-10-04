import json

import pytest

from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows, vc
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, '_full_universe', lambda: UNIVERSE)


def stamped(tmp_path, value, stage='selection'):
    baseline, component = rows()
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window,
                        universe=UNIVERSE, horizons=ALL_HORIZONS, engines=('strategy',),
                        knob_delta={'MIN_REWARD_PCT': value}, engine_hash_baseline='h',
                        engine_hash_component='h', changed_outcomes=0)
    path = tmp_path / f'{value}.json'
    path.write_text(json.dumps({'provenance': stamp, 'baseline': baseline, 'component': component}))
    return path


def selection_args(tmp_path, stage='selection'):
    args = ['--stage', 'selection', '--title', 't', '--window', 'train', '--resamples', '200']
    for value in (.60, .75, .90):
        args += ['--grid-arms', f'{value}={stamped(tmp_path, value, stage)}']
    return args


def test_selection_prints_cells_and_verdict(tmp_path, capsys):
    output = tmp_path / 'out.json'
    assert vc.main(selection_args(tmp_path) + ['--out-json', str(output)]) == 0
    printed = capsys.readouterr().out
    assert all(f'd={value}' in printed for value in (.60, .75, .90))
    assert 'selected' in printed and 'selected=0.9' in printed
    assert json.loads(output.read_text())['selected'] == .90


@pytest.mark.parametrize('stage', ['pilot', 'validation'])
def test_selection_refuses_wrong_stage(tmp_path, capsys, stage):
    assert vc.main(selection_args(tmp_path, stage)) == 1
    assert 'refused:stage-mismatch' in capsys.readouterr().err


def test_selection_mde_refusal_and_malformed_grid(tmp_path, capsys):
    args = selection_args(tmp_path)
    assert vc.main(args + ['--mde-refused', '.60', '--mde-refused', '.75', '--mde-refused', '.90']) == 1
    assert 'no-eligible-cell' in capsys.readouterr().out
    assert vc.main(['--stage', 'selection', '--title', 't', '--window', 'w', '--grid-arms', 'bad']) == 1
    assert 'refused:' in capsys.readouterr().err


def test_selection_requires_grid(capsys):
    assert vc.main(['--stage', 'selection', '--title', 't', '--window', 'w']) == 1
    assert 'refused:' in capsys.readouterr().err


def test_reachability_prints_population_split(tmp_path, capsys):
    path = stamped(tmp_path, .60, 'pilot')
    assert vc.main(['--stage', 'reachability', '--arms', str(path), '--title', 't', '--window', 'w']) == 0
    assert 'split removed=' in capsys.readouterr().out


@pytest.mark.parametrize('stage', ['reachability', 'mde', 'walkforward', 'validation'])
def test_other_stages_require_arms(stage):
    with pytest.raises(SystemExit) as error:
        vc.main(['--stage', stage, '--title', 't', '--window', 'w'])
    assert error.value.code == 2


@pytest.mark.parametrize('values', [('.6', '.60'), ('nan', '.75'), ('inf', '.75'), ('-inf', '.75')])
def test_selection_refuses_duplicate_or_nonfinite_grid_before_reading(tmp_path, capsys, values):
    args = ['--stage', 'selection', '--title', 't', '--window', 'w']
    for value in values:
        args += [f'--grid-arms={value}={tmp_path / "absent.json"}']
    assert vc.main(args) == 1
    error = capsys.readouterr().err
    assert 'refused:malformed-grid' in error and 'Budget intact.' in error


@pytest.mark.parametrize('kind', ['missing', 'directory', 'json', 'stamp', 'window', 'hash', 'universe', 'rows'])
def test_selection_refuses_unreadable_or_malformed_arm_input(tmp_path, capsys, kind):
    path = malformed_input(tmp_path, kind)
    assert vc.main(['--stage', 'selection', '--title', 't', '--window', 'w',
                    '--grid-arms', f'.6={path}']) == 1
    error = capsys.readouterr().err
    assert 'refused:' in error and 'Budget intact.' in error


def malformed_input(tmp_path, kind):
    path = stamped(tmp_path, .60)
    if kind == 'missing':
        path.unlink()
    elif kind == 'directory':
        path = tmp_path
    elif kind == 'json':
        path.write_text('{broken')
    else:
        blob = json.loads(path.read_text())
        if kind == 'stamp':
            blob['provenance'] = []
        elif kind == 'window':
            blob['provenance']['signal_window'] = [None]
        elif kind == 'hash':
            blob['provenance']['engine_hash'] = ['h']
        elif kind == 'universe':
            blob['provenance']['universe'] = 12
        else:
            blob['baseline'] = [{'invalid': True}]
        path.write_text(json.dumps(blob))
    return path


def test_selection_refuses_string_signal_window(tmp_path, capsys):
    path = stamped(tmp_path, .6)
    blob = json.loads(path.read_text())
    blob['provenance']['signal_window'] = '10'
    path.write_text(json.dumps(blob))
    assert vc.main(['--stage', 'selection', '--title', 't', '--window', 'w',
                    '--grid-arms', f'.6={path}']) == 1
    assert 'refused:' in capsys.readouterr().err


def test_selection_does_not_hide_universe_resolution_errors(tmp_path, monkeypatch):
    path = stamped(tmp_path, .6)

    def broken_universe():
        raise ValueError('universe resolution failed')

    monkeypatch.setattr(vc, '_full_universe', broken_universe)
    with pytest.raises(ValueError, match='universe resolution failed'):
        vc.main(['--stage', 'selection', '--title', 't', '--window', 'w',
                 '--grid-arms', f'.6={path}'])
