"""scripts/ops/data_sources_check.py: decision logic only -- no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import data_sources_check as dsc  # noqa: E402


def _frame(n=300, scale=1.0, start=100.0):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({"Close": (start + np.arange(n, dtype="float64")) * scale}, index=idx)


def test_probe_ok_records_rows_and_last_close():
    p = dsc.probe("alpaca", "daily", lambda: _frame(10))
    assert p.ok and p.rows == 10 and p.last_close == 109.0


def test_probe_scalar_price_is_ok():
    assert dsc.probe("yfinance", "price", lambda: 190.5).last_close == 190.5


def test_probe_exception_is_a_fail_not_a_raise():
    def boom():
        raise TimeoutError("slow")
    p = dsc.probe("alpaca", "daily", boom)
    assert not p.ok and "TimeoutError: slow" in p.error


def test_probe_empty_and_none_fail():
    assert not dsc.probe("alpaca", "daily", lambda: _frame(0)).ok
    assert not dsc.probe("alpaca", "price", lambda: None).ok


def test_agreeing_frames_pass():
    ok, _ = dsc.compare_frames(_frame(), _frame(scale=1.001))
    assert ok


def test_a_split_sized_disagreement_fails():
    ok, detail = dsc.compare_frames(_frame(), _frame(scale=1.02))
    assert not ok and "median ratio" in detail


def test_last_close_disagreement_fails_even_if_history_agrees():
    other = _frame()
    other.iloc[-1, 0] *= 1.02
    ok, _ = dsc.compare_frames(_frame(), other)
    assert not ok


def test_missing_or_barely_overlapping_frames_fail():
    assert not dsc.compare_frames(None, _frame())[0]
    assert not dsc.compare_frames(_frame(10), _frame())[0]


def test_depth_requires_router_frame_at_least_as_deep_as_cache():
    assert dsc.depth_ok(_frame(300), _frame(300))[0]
    assert not dsc.depth_ok(_frame(250), _frame(300))[0]
    assert dsc.depth_ok(_frame(250), None)[0]
    assert not dsc.depth_ok(None, None)[0]


def test_decide_exit_codes_and_messages():
    good = dsc.Probe("alpaca", "daily", True, 1.0, 5, 1.0)
    bad = dsc.Probe("yfinance", "daily", False, 1.0, error="empty result")
    assert dsc.decide([good], [("AAPL", True, "")], [("AAPL", True, "")]) == (0, [])
    code, msgs = dsc.decide([good, bad], [("AAPL", False, "x")], [("AAPL", False, "y")])
    assert code == 1 and len(msgs) == 3


def test_format_probe_shows_latency_rows_and_verdict():
    line = dsc.format_probe("AAPL", dsc.Probe("alpaca", "daily", True, 1.234, 500, 190.0))
    assert "1.23s" in line and "rows=500" in line and line.endswith("OK")
