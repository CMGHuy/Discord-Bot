"""The CLI is thin on purpose: every decision lives in acceptance.py, so a
measurement script cannot quietly pick its own bar.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CLI = ROOT / "scripts" / "backtest" / "validate_component.py"


def write_arms(tmp_path, n_tickers=25, drop_from=8):
    rows = {"baseline": [], "component": []}
    for t in range(n_tickers):
        for i in range(10):
            row = {"ticker": f"T{t}", "strategy": "MACD", "horizon_key": "3m",
                   "entry_date": f"2021-03-{i + 1:02d}",
                   "outcome": "win" if i < 4 else "loss",
                   "r_multiple": 2.0 if i < 4 else -1.0, "planned_rr": 2.0}
            rows["baseline"].append(row)
            if i < drop_from:
                rows["component"].append(row)
    p = tmp_path / "arms.json"
    p.write_text(json.dumps(rows))
    return p


def run(*args):
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True)


def test_validation_stage_emits_a_verdict_and_a_results_doc(tmp_path):
    arms = write_arms(tmp_path)
    out_md = tmp_path / "result.md"
    out_json = tmp_path / "result.json"
    r = run("--stage", "validation", "--arms", str(arms),
            "--title", "v99 demo", "--window", "2024-01-01..2025-12-31",
            "--permutation-p", "0.01", "--resamples", "200",
            "--out-md", str(out_md), "--out-json", str(out_json))
    assert r.returncode in (0, 1), r.stderr
    assert out_md.exists() and out_json.exists()
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert blob["verdict"] in ("PASS", "FAIL")
    assert blob["acceptance_version"] == 2
    md_text = out_md.read_text(encoding="utf-8")
    assert "win_rate" in md_text


def test_exit_code_is_one_on_a_failing_component(tmp_path):
    """A FAIL is a legitimate outcome, but the shell must be able to see it
    -- a gate that always exits 0 cannot gate anything in CI."""
    arms = write_arms(tmp_path, drop_from=2)     # a 80% alert cut
    r = run("--stage", "validation", "--arms", str(arms), "--title", "t",
            "--window", "w", "--permutation-p", "0.01", "--resamples", "200",
            "--out-md", str(tmp_path / "m.md"),
            "--out-json", str(tmp_path / "j.json"))
    assert r.returncode == 1
    assert "FAIL" in r.stdout


def test_mde_stage_prints_a_refusal_when_the_effect_is_too_small(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "mde", "--arms", str(arms), "--title", "t",
            "--window", "w", "--train-effect-pp", "0.01",
            "--target-days", "730", "--observed-days", "365")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout


def test_mde_stage_allows_a_resolvable_effect(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "mde", "--arms", str(arms), "--title", "t",
            "--window", "w", "--train-effect-pp", "40.0",
            "--target-days", "730", "--observed-days", "365")
    assert r.returncode == 0
    assert "RESOLVABLE" in r.stdout


def test_unknown_stage_is_rejected(tmp_path):
    arms = write_arms(tmp_path)
    r = run("--stage", "nonsense", "--arms", str(arms), "--title", "t",
            "--window", "w")
    assert r.returncode != 0
    assert "invalid choice" in r.stderr


def write_folds(tmp_path, deltas_pattern="improving"):
    """3 folds; `deltas_pattern` controls whether the component's win rate
    improves (component keeps more wins) or degrades (component keeps more
    losses) relative to baseline, in each fold."""
    folds = []
    for year in ("2021", "2022", "2023"):
        baseline, component = [], []
        for t in range(35):
            for i in range(10):
                outcome = "win" if i < 4 else "loss"
                row = {"ticker": f"T{t}", "strategy": "MACD",
                       "horizon_key": "3m", "entry_date": f"{year}-03-{i + 1:02d}",
                       "outcome": outcome, "r_multiple": 2.0 if outcome == "win" else -1.0,
                       "planned_rr": 2.0}
                baseline.append(row)
                keep = (outcome == "win") if deltas_pattern == "improving" else (outcome == "loss")
                if keep or i >= 6:
                    component.append(row)
        folds.append({"test_year": year, "baseline": baseline, "component": component})
    p = tmp_path / "folds.json"
    p.write_text(json.dumps({"folds": folds}))
    return p


def test_walkforward_stage_passes_when_folds_improve(tmp_path):
    arms = write_folds(tmp_path, "improving")
    r = run("--stage", "walkforward", "--arms", str(arms), "--title", "t",
            "--window", "fold-test 2021-2023")
    assert r.returncode == 0
    assert "PASS" in r.stdout


def test_walkforward_stage_fails_when_folds_degrade(tmp_path):
    arms = write_folds(tmp_path, "degrading")
    r = run("--stage", "walkforward", "--arms", str(arms), "--title", "t",
            "--window", "fold-test 2021-2023")
    assert r.returncode == 1
    assert "FAIL" in r.stdout


def test_validation_stage_writes_a_pending_skeleton_before_the_verdict_is_known(tmp_path, monkeypatch):
    """The skeleton write happens before evaluate() -- assert this by making
    evaluate() raise, and confirming the skeleton file still landed on disk
    with a PENDING verdict and the real clause thresholds, even though the
    run itself never completed."""
    import scripts.backtest.validate_component as vc
    arms = write_arms(tmp_path)
    out_md = tmp_path / "result.md"

    def boom(*a, **k):
        raise RuntimeError("simulated crash after skeleton, before verdict")

    monkeypatch.setattr(vc, "evaluate", boom)
    with pytest.raises(RuntimeError):
        vc._run_gate(
            type("Args", (), {"arms": arms, "title": "t", "window": "w",
                              "permutation_p": 0.01, "resamples": 200,
                              "seed": 7, "notes": None,
                              "out_md": str(out_md), "out_json": None})(),
            "validation")
    assert out_md.exists()
    text = out_md.read_text(encoding="utf-8")
    assert "PENDING" in text
    assert "win_rate" in text and "geometry" in text
    assert "bootstrap seed 7" in text  # the pre-registered skeleton names the
                                       # ACTUAL --seed, not the dataclass default


def test_walkforward_stage_rejects_a_fold_count_other_than_three(tmp_path):
    """gate_win_rate's '>=2 of 3' rule presumes exactly 3 folds -- 2 folds
    silently becomes '2 of 2' and a duplicated test_year hides a missing
    third year. The CLI must refuse rather than silently score whichever
    folds it was handed."""
    arms = write_folds(tmp_path, "improving")
    blob = json.loads(arms.read_text(encoding="utf-8"))
    blob["folds"] = blob["folds"][:2]          # only 2 of the 3 folds
    arms.write_text(json.dumps(blob), encoding="utf-8")
    r = run("--stage", "walkforward", "--arms", str(arms), "--title", "t",
            "--window", "fold-test 2021-2023")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
