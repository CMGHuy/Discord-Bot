import numpy as np
import pytest
from swingbot.core import levels
from swingbot.core.strategy_types import HORIZONS
from tests.helpers import make_ohlcv

def _structured_df():
    """Trend up, then a 60-bar consolidation between ~95 and ~105 -- gives
    every level source (rolling S/R, Donchian, pivots, Bollinger, fibs)
    real structure on both sides of price."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)

@pytest.fixture(scope="module")
def scenario_env():
    df = _structured_df()
    h = HORIZONS["4w"]
    price = float(df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(df, h, price)
    floor_pct = levels.atr_floor_pct(df, price, h)
    scenarios = levels.build_scenarios(price, supports, resistances,
                                       min_reward_pct=1.0, atr_floor=floor_pct,
                                       min_stop_distance_pct=0.5,
                                       max_stop_distance_pct=15.0,
                                       min_risk_reward=0.0)
    return df, price, scenarios

def test_scenarios_anchor_at_current_price(scenario_env):
    _, price, scenarios = scenario_env
    assert scenarios, "fixture must qualify at least one scenario"
    for s in scenarios:
        assert s.entry == price and s.market_price == price

def test_stop_and_target_on_opposite_sides(scenario_env):
    _, price, scenarios = scenario_env
    for s in scenarios:
        if s.direction == "bullish":
            assert s.stop_loss < price < s.take_profit
        else:
            assert s.take_profit < price < s.stop_loss

def test_sources_populated_and_constraints_all_true(scenario_env):
    _, _, scenarios = scenario_env
    for s in scenarios:
        assert s.target_sources and s.stop_sources
        assert s.meets_all_own_constraints   # failing scenarios are never built

def test_target2_leg_cap_respected(scenario_env):
    _, price, scenarios = scenario_env
    for s in scenarios:
        if s.target2_price is None:
            continue
        leg1 = abs(s.take_profit - price)
        leg2 = abs(s.target2_price - s.take_profit)
        assert leg2 <= leg1 * levels.MAX_TARGET2_LEG_MULTIPLE + 1e-9

def test_hard_requirements_are_hard():
    # An impossible min_reward must yield zero scenarios -- no soft fallback.
    df = _structured_df()
    h = HORIZONS["4w"]
    price = float(df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(df, h, price)
    assert levels.build_scenarios(price, supports, resistances,
                                  min_reward_pct=500.0) == []
