# tests/backtesting/test_acceptance_records.py
"""ArmTrade is the neutral record every acceptance clause reads.

It exists so acceptance.py depends on neither BacktestTrade nor any
measurement script's private row dialect -- measure_dcb_veto's rows, for
one, carry no `strategy` and no geometry at all.
"""
from swingbot.core.backtesting.acceptance import (
    ArmTrade, arm_trade_from_backtest, arm_trade_from_plan, planned_rr,
)


def _trade(**kw):
    base = dict(ticker="AAPL", strategy="MACD", horizon_key="3m",
                entry_date="2021-03-01", outcome="win", r_multiple=1.5,
                planned_rr=2.0)
    base.update(kw)
    return ArmTrade(**base)


def test_key_is_the_pairing_tuple():
    t = _trade()
    assert t.key == ("AAPL", "MACD", "3m", "2021-03-01")


def test_stratum_is_strategy_by_horizon():
    assert _trade().stratum == ("MACD", "3m")


def test_planned_rr_is_reward_over_risk():
    # entry 100, stop 95 -> risk 5; target 110 -> reward 10; RR 2.0
    assert planned_rr(100.0, 95.0, 110.0) == 2.0


def test_planned_rr_is_direction_agnostic():
    # A bearish plan: entry 100, stop 105, target 90. Same 2.0.
    assert planned_rr(100.0, 105.0, 90.0) == 2.0


def test_planned_rr_is_none_on_zero_risk():
    assert planned_rr(100.0, 100.0, 110.0) is None


def test_from_plan_prefers_entry_price_over_trigger():
    class _Plan:
        ticker, strategy, horizon_key = "MSFT", "VWAP", "4w"
        entry_price, trigger_price = 50.0, 49.0
        stop_loss, tp1 = 45.0, 60.0
    t = arm_trade_from_plan(_Plan(), entry_date="2021-06-02",
                            outcome="loss", r_multiple=-1.0)
    assert t.ticker == "MSFT" and t.strategy == "VWAP"
    assert t.entry_date == "2021-06-02"
    assert t.planned_rr == 2.0        # |60-50| / |50-45|


def test_from_plan_falls_back_to_trigger_price():
    class _Plan:
        ticker, strategy, horizon_key = "MSFT", "VWAP", "4w"
        entry_price, trigger_price = None, 50.0
        stop_loss, tp1 = 45.0, 60.0
    assert arm_trade_from_plan(_Plan(), entry_date="2021-06-02",
                               outcome="win", r_multiple=2.0).planned_rr == 2.0


def test_from_backtest_takes_context_the_trade_does_not_carry():
    class _BT:
        entry_date, entry, stop_loss, take_profit = "2022-01-04", 10.0, 9.0, 12.0
        outcome, r_multiple = "win", 2.0
    t = arm_trade_from_backtest(_BT(), ticker="SPY", strategy="RSI",
                                horizon_key="2m")
    assert t.stratum == ("RSI", "2m")
    assert t.planned_rr == 2.0
