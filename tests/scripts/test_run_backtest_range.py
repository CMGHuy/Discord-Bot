"""run_backtest_range.py's pooled per-strategy max-DD helper (Task E22)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_backtest_range as rbr  # noqa: E402


def _trade(entry_date, r_multiple):
    return SimpleNamespace(entry_date=entry_date, r_multiple=r_multiple)


def test_pooled_max_dd_pct_golden():
    # 1% risk per trade, compounding: 1.0 -> 1.01 -> 1.0908 (peak) -> 0.98172
    # dd from peak = (0.98172 - 1.0908) / 1.0908 * 100 = -10.0%
    trades = [
        _trade("2020-01-01", 1.0),
        _trade("2020-01-02", 8.0),
        _trade("2020-01-03", -10.0),
    ]
    dd = rbr.pooled_max_dd_pct(trades, risk_pct=1.0)
    assert dd == pytest.approx(-10.0)


def test_pooled_max_dd_pct_sorts_by_entry_date():
    # Same trades, passed out of order -- result must be order-independent
    # of input list order (sorted internally by entry_date).
    trades = [
        _trade("2020-01-03", -10.0),
        _trade("2020-01-01", 1.0),
        _trade("2020-01-02", 8.0),
    ]
    assert rbr.pooled_max_dd_pct(trades, risk_pct=1.0) == pytest.approx(-10.0)


def test_pooled_max_dd_pct_no_drawdown_is_zero_not_none():
    trades = [_trade("2020-01-01", 1.0), _trade("2020-01-02", 2.0)]
    assert rbr.pooled_max_dd_pct(trades) == 0.0


def test_pooled_max_dd_pct_empty_is_none():
    assert rbr.pooled_max_dd_pct([]) is None


def test_pooled_max_dd_pct_skips_trades_with_no_r_multiple():
    trades = [_trade("2020-01-01", None), _trade("2020-01-02", None)]
    assert rbr.pooled_max_dd_pct(trades) is None
