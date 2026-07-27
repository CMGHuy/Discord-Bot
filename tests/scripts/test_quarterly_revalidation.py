"""scripts/quarterly_revalidation.py's pure diffing logic (Task E96).

Only diff_and_verdict is tested directly -- everything else in the script
is subprocess orchestration (cache refresh, wf_run.py, permutation_test.py),
matching this codebase's established convention of testing the pure logic
a script wraps, not the orchestration itself (see test_run_backtest_range.py).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import quarterly_revalidation as qr  # noqa: E402


def _result(**wf_result):
    return {"at": "2026-07-27T00:00:00+00:00", "adopted_components": {}, "wf_result": wf_result}


def test_diff_and_verdict_baseline_when_no_history():
    verdict = qr.diff_and_verdict([], _result(pooled_delta_expectancy_r=0.05))
    assert verdict == "BASELINE (no prior quarter to compare)"


def test_diff_and_verdict_pass_when_stable():
    history = [_result(pooled_delta_expectancy_r=0.05, p_ruin=0.02, p_10x=0.60)]
    latest = _result(pooled_delta_expectancy_r=0.06, p_ruin=0.02, p_10x=0.61)
    assert qr.diff_and_verdict(history, latest) == "PASS"


def test_diff_and_verdict_degraded_on_expectancy_drop():
    history = [_result(pooled_delta_expectancy_r=0.05)]
    # Drop bigger than DEGRADE_TOLERANCE["pooled_delta_expectancy_r"] (0.03)
    latest = _result(pooled_delta_expectancy_r=-0.01)
    assert qr.diff_and_verdict(history, latest) == "DEGRADED"


def test_diff_and_verdict_degraded_on_p10x_drop():
    history = [_result(p_10x=0.60)]
    # p_10x dropping is a degrade even though the raw delta is negative
    # (DEGRADE_TOLERANCE["p_10x"] is itself negative -- a >5pt drop flags)
    latest = _result(p_10x=0.50)
    assert qr.diff_and_verdict(history, latest) == "DEGRADED"


def test_diff_and_verdict_ignores_missing_keys():
    history = [_result(pooled_delta_expectancy_r=0.05)]
    latest = _result()   # no wf_result keys at all this run
    assert qr.diff_and_verdict(history, latest) == "PASS"


def test_diff_and_verdict_uses_most_recent_history_entry():
    history = [_result(pooled_delta_expectancy_r=-0.5), _result(pooled_delta_expectancy_r=0.05)]
    latest = _result(pooled_delta_expectancy_r=0.06)
    assert qr.diff_and_verdict(history, latest) == "PASS"
