"""v122 arm-pair permutation extension and unchanged fold-path witness."""

import json
import runpy
import sys
from pathlib import Path

import numpy as np

from swingbot.core.backtesting import backtest_wf
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms.provenance import build_stamp


ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "backtest" / "permutation_test.py"
WITNESS = ROOT / "tests" / "fixtures" / "v122" / "permutation_fold_witness.json"
FOLD_ARGV = ["permutation_test.py", "--component-json", '{"X": 1}', "--n", "50"]


def fake_run_folds(overrides):
    from swingbot.core.backtesting import backtest as bt

    shift = bt.ENTRY_SHIFT
    return {"folds": [{"component": {"expectancy_r": 0.10 if shift == 0 else 0.001 * shift}},
                      {"component": {"expectancy_r": None}}]}


def run_script(argv) -> str:
    """Run the script as __main__, accepting a successful SystemExit after refactor."""
    import contextlib
    import io

    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = list(argv)
    try:
        with contextlib.redirect_stdout(buffer):
            try:
                runpy.run_path(str(SCRIPT), run_name="__main__")
            except SystemExit as exc:
                assert exc.code in (0, None), exc.code
    finally:
        sys.argv = saved
    return buffer.getvalue()


def test_fold_path_output_is_unchanged(monkeypatch):
    monkeypatch.setattr(backtest_wf, "run_folds", fake_run_folds)
    assert run_script(FOLD_ARGV) == WITNESS.read_text(encoding="utf-8")


def _arm_pair(remove_outcome):
    """Aperiodic outcomes with removals in the second half and one replacement per ticker."""
    baseline, component = [], []
    for ticker_number in range(25):
        wins = np.random.default_rng(ticker_number).random(40) < 0.4
        for index in range(40):
            outcome = "win" if wins[index] else "loss"
            trade = ArmTrade(
                f"T{ticker_number}", "Fibonacci", "4w",
                f"2024-{1 + index // 28:02d}-{1 + index % 28:02d}", outcome,
                2.0 if wins[index] else -1.0, 2.0, "strategy", "bullish")
            baseline.append(trade)
            if not (index >= 20 and outcome == remove_outcome):
                component.append(trade)
        component.append(ArmTrade(
            f"T{ticker_number}", "Fibonacci", "4w", "2024-03-20", "win",
            2.0, 2.0, "confluence", "bullish"))
    return baseline, component


def _write(tmp_path, baseline, component, stamped=True):
    from dataclasses import asdict

    blob = {"baseline": [asdict(trade) for trade in baseline],
            "component": [asdict(trade) for trade in component]}
    if stamped:
        blob["provenance"] = build_stamp(
            stage="validation", signal_window=("2024-01-01", "2025-12-31"),
            universe=["T0"], horizons=("4w",), engines=("strategy",),
            knob_delta={}, engine_hash_baseline="h", engine_hash_component="h",
            changed_outcomes=1)
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


def _load_script():
    return runpy.run_path(str(SCRIPT))


def test_removing_losers_is_distinguishable_from_luck():
    result = _load_script()["arm_pair_permutation"](*_arm_pair("loss"), n_perm=200, seed=42)
    assert result["observed_delta_win_rate_pp"] > 0 and result["p_value"] < 0.05
    assert (result["n"], result["seed"], result["added"]) == (200, 42, 25)


def test_removing_winners_is_not_distinguishable():
    result = _load_script()["arm_pair_permutation"](*_arm_pair("win"), n_perm=200, seed=42)
    assert result["p_value"] > 0.05


def test_seeded_arm_pair_permutation_is_reproducible():
    function = _load_script()["arm_pair_permutation"]
    arms = _arm_pair("loss")
    assert function(*arms) == function(*arms)


def test_cli_arms_mode(tmp_path):
    path = _write(tmp_path, *_arm_pair("loss"))
    result = json.loads(run_script(["permutation_test.py", "--arms", str(path)]))
    assert result["verdict"] == "REAL" and result["n"] == 200


def test_cli_refuses_unstamped_arms(tmp_path, capsys):
    path = _write(tmp_path, *_arm_pair("loss"), stamped=False)
    assert _load_script()["main"](["--arms", str(path)]) == 1
    assert "refused:unstamped" in capsys.readouterr().err
