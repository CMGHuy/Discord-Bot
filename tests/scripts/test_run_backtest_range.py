"""run_backtest_range.py's pooled per-strategy max-DD helper (Task E22)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

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


def test_tickers_for_run_uses_named_universe(monkeypatch):
    import swingbot.core.marketdata.universe as universe

    def boom():
        raise AssertionError("load_watchlist should not be called when a universe is given")

    monkeypatch.setattr(rbr, "load_watchlist", boom)
    monkeypatch.setattr(universe, "universe_symbols", lambda name: ["QQQ", "SPY"])
    assert rbr._tickers_for_run("etfs") == ["QQQ", "SPY"]


def test_tickers_for_run_defaults_to_watchlist(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["ZZZ", "AAA"])
    assert rbr._tickers_for_run(None) == ["AAA", "ZZZ"]
