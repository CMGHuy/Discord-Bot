"""v113 §1: the strategy-plan reward floor exists on 1w only (2.0%)."""
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.planning import reward_floor as rf


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)
    rf.reset()
    yield
    rf.reset()


def test_only_1w_has_a_floor():
    assert rf.floor_pct("1w") == 2.0
    assert all(rf.floor_pct(hk) is None for hk in LEGACY_HORIZONS)


def test_legacy_horizons_always_clear_and_count_nothing():
    for hk in LEGACY_HORIZONS:
        assert rf.clears(100.0, 100.5, "MACD", hk)
    assert not rf.DROPS and not rf.PASSES


def test_1w_floor_is_two_percent_in_both_directions_and_counted():
    assert rf.clears(100.0, 102.0, "MACD", "1w")
    assert rf.clears(100.0, 98.0, "MACD", "1w")
    assert not rf.clears(100.0, 101.9, "MACD", "1w")
    assert rf.PASSES[("MACD", "1w")] == 2 and rf.DROPS[("MACD", "1w")] == 1
    rf.reset()
    assert not rf.DROPS and not rf.PASSES


def test_the_fade_target_at_m_one_sits_exactly_on_the_floor():
    entry = 187.3899
    stop = entry * 1.02
    assert rf.clears(entry, entry - 1.0 * (stop - entry), "Downtrend Overbought Fade", "1w")


def test_build_strategy_plan_drops_what_the_floor_drops(market_df, monkeypatch):
    from swingbot.core.planning import builders
    kwargs = dict(ticker="X", strategy="RSI Divergence", horizon_key="4w", direction="bullish")
    i = next(i for i in range(400, len(market_df))
             if builders.build_strategy_plan(market_df, i, **kwargs) is not None)
    monkeypatch.setattr(rf, "clears", lambda *args: False)
    assert builders.build_strategy_plan(market_df, i, **kwargs) is None


def test_trade_plan_at_drops_what_the_floor_drops(market_df, monkeypatch):
    from swingbot.core.backtesting import backtest as bt
    series = bt._plan_series(market_df, "RSI Divergence", "4w")
    i = next(i for i in range(400, len(market_df))
             if bt._trade_plan_at(market_df, i, "bullish", "RSI Divergence", "4w", *series) is not None)
    monkeypatch.setattr(rf, "clears", lambda *args: False)
    assert bt._trade_plan_at(market_df, i, "bullish", "RSI Divergence", "4w", *series) is None


def test_every_1w_plan_that_builds_clears_two_percent(market_df):
    from swingbot.core.planning import builders
    built = [p for i in range(400, 700)
             if (p := builders.build_strategy_plan(market_df, i, ticker="X", strategy="RSI Divergence",
                                                   horizon_key="1w", direction="bullish")) is not None]
    assert all(abs(p.tp1 - p.trigger_price) / p.trigger_price * 100 >= 2.0 - 1e-9 for p in built)
    assert built, "fixture must build at least one 1w plan"
    assert rf.PASSES[("RSI Divergence", "1w")] == len(built)   # every built plan was counted once
