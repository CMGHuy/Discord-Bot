"""v122 arm-pair permutation extension and unchanged fold-path witness."""

import runpy
import sys
from pathlib import Path

from swingbot.core.backtesting import backtest_wf


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
