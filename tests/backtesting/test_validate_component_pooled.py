"""v180: validate_component.py --wr-statistic pooled (A1 clause 1 and fold rows) and
--train-effect-from-arms (A3: the TRAIN effect is the A1 point on the same arms)."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from tests.backtesting.test_acceptance_pooled_wr import _arms  # noqa: E402

BESPOKE = ["--bespoke-instrument", "v180 unit fixture"]
MDE_ARGS = ["--title", "t", "--window", "w", "--resamples", "200",
            "--observed-days", "365", "--target-days", "730"]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot import config
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def _run(*args):
    return vc.main([*args, *BESPOKE])


def _write_arms(tmp_path, baseline, component):
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def _write_folds(tmp_path, lift):
    folds = []
    for year in ("2021", "2022", "2023"):
        baseline, component = _arms(n_tickers=5, lift=lift)
        folds.append({"test_year": year, "baseline": [asdict(t) for t in baseline],
                      "component": [asdict(t) for t in component]})
    path = tmp_path / "folds.json"
    path.write_text(json.dumps({"folds": folds}), encoding="utf-8")
    return path


def test_pooled_walkforward_passes_an_additive_arm(tmp_path):
    out = tmp_path / "wf.json"
    rc = _run("--stage", "walkforward", "--wr-statistic", "pooled", "--arms",
              str(_write_folds(tmp_path, lift=4)), "--title", "t", "--window", "w",
              "--out-json", str(out))
    assert rc == 0
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["verdict"] == "PASS"
    assert all(row["wr_statistic"] == "pooled" and row["n"] == 50 for row in blob["folds"])


def test_the_standardised_walkforward_cannot_see_the_same_arm(tmp_path):
    assert _run("--stage", "walkforward", "--arms", str(_write_folds(tmp_path, lift=4)),
                "--title", "t", "--window", "w") == 1


def test_pooled_validation_scores_clause_one_on_the_pooled_statistic(tmp_path):
    out = tmp_path / "gate.json"
    rc = _run("--stage", "validation", "--wr-statistic", "pooled",
              "--arms", str(_write_arms(tmp_path, *_arms())), "--title", "t", "--window", "w",
              "--permutation-p", "0.01", "--resamples", "200", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0 and blob["verdict"] == "PASS" and blob["wr_statistic"] == "pooled"
    clause = next(c for c in blob["clauses"] if c["name"] == "win_rate")
    assert clause["verdict"] == "PASS" and clause["detail"].startswith("pooled dWR")


def test_train_effect_from_arms_resolves_a_real_effect(tmp_path, capsys):
    rc = _run("--stage", "mde", "--wr-statistic", "pooled", "--train-effect-from-arms",
              "--arms", str(_write_arms(tmp_path, *_arms(lift=4))), *MDE_ARGS)
    out = capsys.readouterr().out
    assert "train effect (pooled, from --arms): +20.0000pp" in out
    assert rc == 0 and "RESOLVABLE" in out


def test_train_effect_from_arms_refuses_no_effect(tmp_path, capsys):
    rc = _run("--stage", "mde", "--wr-statistic", "pooled", "--train-effect-from-arms",
              "--arms", str(_write_arms(tmp_path, *_arms(lift=0))), *MDE_ARGS)
    out = capsys.readouterr().out
    assert "+0.0000pp" in out
    assert rc == 1 and "REFUSED" in out


def test_pooled_is_refused_with_the_harvest_gate(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run("--stage", "walkforward", "--gate", "harvest", "--wr-statistic", "pooled",
             "--arms", str(_write_folds(tmp_path, lift=4)), "--title", "t", "--window", "w")
    assert exc.value.code == 2
