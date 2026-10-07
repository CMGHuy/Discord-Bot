"""v128: --gate harvest at walkforward/validation, and --mechanism-json for v72 clause 6."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting.acceptance import ClauseResult, evaluate  # noqa: E402
from tests.backtesting.test_validate_component_cli import write_arms, write_folds  # noqa: E402

BESPOKE = ["--bespoke-instrument", "v128 unit fixture"]


def _run(*args):
    return vc.main([*args, *BESPOKE])


def test_harvest_walkforward_passes_when_expectancy_improves_every_fold(tmp_path, capsys):
    out = tmp_path / "wf.json"
    rc = _run("--stage", "walkforward", "--gate", "harvest", "--arms", str(write_folds(tmp_path, "improving")),
              "--title", "t", "--window", "w", "--out-json", str(out))
    assert rc == 0
    assert "harvest expectancy fold gate (backtest_wf.gate)" in capsys.readouterr().out
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["gate"] == "harvest"
    assert all(fold["delta_expectancy_r"] > 0 and fold["n"] >= 30 for fold in blob["folds"])


def test_harvest_walkforward_fails_when_expectancy_degrades(tmp_path):
    assert _run("--stage", "walkforward", "--gate", "harvest", "--arms",
                str(write_folds(tmp_path, "degrading")), "--title", "t", "--window", "w") == 1


def test_win_rate_walkforward_json_is_unchanged(tmp_path):
    out = tmp_path / "wf.json"
    _run("--stage", "walkforward", "--arms", str(write_folds(tmp_path, "improving")), "--title", "t",
         "--window", "w", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert set(blob) == {"verdict", "folds"}
    assert list(blob["folds"][0]) == ["test_years", "delta_win_rate_pp", "n"]


def test_harvest_validation_runs_the_v92_clauses_and_fails_without_a_permutation_p(tmp_path):
    out = tmp_path / "v.json"
    rc = _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
              "--title", "t", "--window", "w", "--resamples", "200", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1 and blob["acceptance_version"] == 1
    assert [c["name"] for c in blob["clauses"]] == ["expectancy_gain", "win_rate_floor", "volume", "permutation"]
    assert next(c for c in blob["clauses"] if c["name"] == "permutation")["verdict"] == "FAIL"


def test_harvest_validation_passes_with_a_permutation_p(tmp_path):
    assert _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
                "--title", "t", "--window", "w", "--resamples", "200", "--permutation-p", "0.01") == 0


def test_mechanism_json_replaces_clause_6(tmp_path):
    injected = tmp_path / "mechanism.json"
    injected.write_text(json.dumps({"name": "mechanism", "verdict": "FAIL", "detail": "v128 injected",
                                    "value": None, "threshold": None}), encoding="utf-8")
    out = tmp_path / "v.json"
    rc = _run("--stage", "validation", "--arms", str(write_arms(tmp_path)), "--title", "t", "--window", "w",
              "--permutation-p", "0.01", "--resamples", "200", "--mechanism-json", str(injected),
              "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    mechanism = next(c for c in blob["clauses"] if c["name"] == "mechanism")
    assert (rc, blob["verdict"], mechanism["detail"]) == (1, "FAIL", "v128 injected")


def test_with_mechanism_clause_recomputes_the_verdict(tmp_path):
    baseline, component = vc.load_arms(write_arms(tmp_path))
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200)
    swapped = vc.with_mechanism_clause(result, ClauseResult("mechanism", "FAIL", "x"))
    assert swapped.verdict == "FAIL"
    assert [c.name for c in swapped.clauses] == [c.name for c in result.clauses]
    with pytest.raises(ValueError):
        vc.with_mechanism_clause(result, ClauseResult("volume", "PASS", "x"))


def test_mechanism_json_with_the_harvest_gate_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
             "--title", "t", "--window", "w", "--mechanism-json", str(tmp_path / "m.json"))
    assert exc.value.code == 2
