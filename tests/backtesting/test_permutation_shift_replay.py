"""v180 A2 CLI: permutation_test.py --arms F --shift-replay --wr-statistic pooled."""
import contextlib
import dataclasses
import io
import json
import runpy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "backtest" / "permutation_test.py"
UNIVERSE = [f"T{n}" for n in range(40)]
ARGV = ["--shift-replay", "--wr-statistic", "pooled", "--n", "50", "--data-source", "yfinance"]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot import config
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def _write(tmp_path, baseline, component, stamped=True):
    blob = {"baseline": [asdict(t) for t in baseline],
            "component": [asdict(t) for t in component]}
    if stamped:
        blob["provenance"] = build_stamp(
            stage="validation", signal_window=STAGES["validation"].signal_window,
            universe=UNIVERSE, horizons=ALL_HORIZONS, engines=("confluence", "strategy"),
            knob_delta={"TURTLE_SOUP_RESEARCH_MODE": "structural"},
            engine_hash_baseline="h", engine_hash_component="h",
            changed_outcomes=len(component) - len(baseline),
            preregistration="synthetic-v180-test")
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


def _added(baseline, component):
    keys = {t.key for t in baseline}
    return [t for t in component if t.key not in keys]


def _no_edge(added):
    def replay(shift):
        if shift == 0:
            return list(added)
        rng = np.random.default_rng(shift)
        return [dataclasses.replace(t, outcome="win" if rng.random() < 0.4 else "loss")
                for t in added]
    return replay


def _run(argv, replay, seen=None):
    main = runpy.run_path(str(SCRIPT))["main"]
    main.__globals__["_full_universe"] = lambda: UNIVERSE
    main.__globals__["_replay_frames"] = lambda universe: {t: None for t in universe}

    def factory(frames, strategy, stamp):
        if seen is not None:
            seen.append((sorted(frames), strategy, stamp["knob_delta"]))
        return replay
    main.__globals__["_shift_replay_for"] = factory
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()


def test_a_real_effect_is_real(tmp_path):
    baseline, component = _arms()
    seen = []
    code, out = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV],
                     _no_edge(_added(baseline, component)), seen)
    blob = json.loads(out)
    assert code == 0 and blob["verdict"] == "REAL" and blob["p_value"] < 0.05
    assert (blob["n"], blob["added"], blob["wr_statistic"], blob["strategy"]) == (
        50, 400, "pooled", "Turtle Soup")
    assert seen == [(sorted(UNIVERSE), "Turtle Soup", {"TURTLE_SOUP_RESEARCH_MODE": "structural"})]


def test_out_json_matches_stdout(tmp_path):
    baseline, component = _arms(n_tickers=5)
    target = tmp_path / "perm.json"
    code, out = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV,
                      "--out-json", str(target)], _no_edge(_added(baseline, component)))
    assert code == 0 and json.loads(target.read_text(encoding="utf-8")) == json.loads(out)


def test_a_non_additive_arm_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component[1:])), *ARGV],
                   _no_edge([]))
    assert code == 1 and "refused:not-additive" in capsys.readouterr().err


def test_two_added_strategies_are_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    component = component + [_trade("T0", "Fibonacci Limit", "2w", 70, "win")]
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV], _no_edge([]))
    assert code == 1 and "refused:not-single-strategy" in capsys.readouterr().err


def test_a_replay_that_misses_the_observed_rows_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV],
                   lambda shift: [])
    assert code == 1 and "refused:replay-mismatch" in capsys.readouterr().err


def test_an_unstamped_arm_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component, stamped=False)), *ARGV],
                   _no_edge(_added(baseline, component)))
    assert code == 1 and "refused:unstamped" in capsys.readouterr().err


def test_shift_replay_needs_arms():
    with pytest.raises(SystemExit) as exc:
        _run(ARGV, _no_edge([]))
    assert exc.value.code == 2
