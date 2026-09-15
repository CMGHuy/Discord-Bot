import pandas as pd

from scripts.backtest.emit_cohort_registry import aggregate_cells


def _regimes():
    index = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    return pd.Series(["bull_quiet", "bear_volatile", "bear_volatile"], index=index)


def test_aggregate_buckets_by_direction_and_regime():
    trades = [
        {"created_at": "2026-01-02", "direction": "bullish", "r_realized": 1.0},
        {"created_at": "2026-01-05", "direction": "bearish", "r_realized": -1.0},
        {"created_at": "2026-01-06", "direction": "bearish", "r_realized": -1.0},
    ]

    cells = aggregate_cells(trades, _regimes())

    assert cells["bullish|bull_quiet"]["n"] == 1
    assert cells["bearish|bear_volatile"]["n"] == 2
    assert cells["bearish|bear_volatile"]["win_rate"] == 0.0
    assert cells["bearish|bear_volatile"]["expectancy_r"] == -1.0


def test_trade_with_no_regime_for_its_date_is_dropped_not_guessed():
    trades = [{"created_at": "2019-01-01", "direction": "bullish", "r_realized": 1.0}]
    assert aggregate_cells(trades, _regimes()) == {}


def test_trade_missing_r_realized_is_dropped():
    trades = [{"created_at": "2026-01-02", "direction": "bullish", "r_realized": None}]
    assert aggregate_cells(trades, _regimes()) == {}
