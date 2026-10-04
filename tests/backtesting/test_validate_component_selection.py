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
