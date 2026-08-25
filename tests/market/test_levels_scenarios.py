import numpy as np
import pytest
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv

def _structured_df():
    """Trend up, then a 60-bar consolidation between ~95 and ~105 -- gives
    every level source (rolling S/R, Donchian, pivots, Bollinger, fibs)
    real structure on both sides of price."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)

def test_build_level_map_accepts_precomputed_candidates():
    # engine.py computes collect_candidate_levels() once per ticker/horizon
    # and passes it in here rather than letting build_level_map recompute
    # it -- must produce the identical (supports, resistances) either way.
    df = _structured_df()
    h = HORIZONS["4w"]
    price = float(df["Close"].iloc[-1])
    candidates = levels.collect_candidate_levels(df, h, price)
    supports_pre, resistances_pre = levels.build_level_map(df, h, price, candidates=candidates)
    supports, resistances = levels.build_level_map(df, h, price)
    assert [s.price for s in supports_pre] == [s.price for s in supports]
    assert [r.price for r in resistances_pre] == [r.price for r in resistances]

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


def test_target_candidates_returns_the_direction_side_nearest_first(scenario_env):
    df, price, _ = scenario_env
    h = HORIZONS["4w"]
    supports, resistances = levels.build_level_map(df, h, price)
    assert supports and resistances, "fixture must have levels on both sides"

    bullish = levels.target_candidates(supports, resistances, "bullish")
    assert all(p > price for p in bullish)
    assert bullish == sorted(bullish)

    bearish = levels.target_candidates(supports, resistances, "bearish")
    assert all(p < price for p in bearish)
    assert bearish == sorted(bearish, reverse=True)


def test_target_candidates_preserves_build_level_map_order(scenario_env):
    df, price, _ = scenario_env
    h = HORIZONS["4w"]
    supports, resistances = levels.build_level_map(df, h, price)

    assert levels.target_candidates(supports, resistances, "bullish") == \
        [lv.price for lv in resistances]
    assert levels.target_candidates(supports, resistances, "bearish") == \
        [lv.price for lv in supports]


def test_scenario_source_lists_are_not_shared_between_directions():
    """A bullish scenario's `target_sources` and a bearish scenario's
    `stop_sources` are both built from `resistances[0].sources`. Confidence
    scoring appends labels to `target_sources` IN PLACE (confidence.py's
    "Bollinger Squeeze Breakout" / "Candlestick: ..." appends), so handing
    both scenarios the same list object lets a bullish-only label leak onto
    the bearish trade's STOP sources -- and onto the shared Level itself,
    which the admin chart later reads to pick an overlay."""
    price = 100.0
    supports = [levels.Level(price=95.0, sources=["S-a"]),
                levels.Level(price=90.0, sources=["S-b"])]
    resistances = [levels.Level(price=105.0, sources=["R-a"]),
                   levels.Level(price=110.0, sources=["R-b"])]
    scenarios = levels.build_scenarios(price, supports, resistances,
                                       min_reward_pct=1.0, atr_floor=0.0,
                                       min_stop_distance_pct=0.5,
                                       max_stop_distance_pct=15.0,
                                       min_risk_reward=0.0)
    bull = next(s for s in scenarios if s.direction == "bullish")
    bear = next(s for s in scenarios if s.direction == "bearish")

    bull.target_sources.append("Candlestick: Hammer")

    assert "Candlestick: Hammer" not in bear.stop_sources, \
        "bullish target label leaked onto the bearish scenario's stop sources"
    assert "Candlestick: Hammer" not in resistances[0].sources, \
        "scoring mutated the shared Level's own source list"
