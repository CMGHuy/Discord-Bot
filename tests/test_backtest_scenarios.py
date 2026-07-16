"""Tests for backtest_scenarios.levels_asof memoization."""
import numpy as np

from swingbot.core import backtest_scenarios as bs
from tests.helpers import make_ohlcv


def _structured_df():
    """Trend up, then a 60-bar consolidation between ~95 and ~105 -- gives
    every level source (rolling S/R, Donchian, pivots, Bollinger, fibs)
    real structure on both sides of price. Local copy of the fixture in
    tests/test_levels_scenarios.py -- same shape, kept independent so each
    test file's fixtures don't couple to one another."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_cache_hits_within_5_bar_bucket(monkeypatch):
    """Cache should return the same result for bar indices in the same 5-bar bucket."""
    calls = {"n": 0}
    real = bs.levels.build_level_map
    def counting(df, h, price):
        calls["n"] += 1
        return real(df, h, price)
    monkeypatch.setattr(bs.levels, "build_level_map", counting)

    df = make_ohlcv([100 + i * 0.3 for i in range(120)])
    cache = {}
    bs.levels_asof("AAPL", df, 100, "4w", cache)
    bs.levels_asof("AAPL", df, 103, "4w", cache)   # same bucket 100//5 == 103//5? yes, both 20
    assert calls["n"] == 1
    bs.levels_asof("AAPL", df, 105, "4w", cache)   # bucket 21 -- recompute
    assert calls["n"] == 2
    bs.levels_asof("MSFT", df, 100, "4w", cache)   # different ticker -- recompute
    assert calls["n"] == 3


def test_slice_never_sees_future_bars():
    """Last bar is a 3x spike; the as-of map at an earlier index must not
    contain any level anywhere near the spike price."""
    closes = [100.0] * 100 + [300.0]
    df = make_ohlcv(closes)
    supports, resistances = bs.levels_asof("AAPL", df, 90, "4w", {})
    all_prices = [lv.price for lv in supports + resistances]
    assert all(p < 200 for p in all_prices), all_prices


GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def test_replay_yields_plans_with_cooldown():
    # Trend + box structure (same fixture family as test_levels_scenarios):
    # many consecutive bars qualify, so without the cooldown the replay
    # would emit a plan nearly every bar.
    df = _structured_df()           # shared via a small conftest helper or copy
    out = bs.replay_scenarios("AAPL", df, "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    seen = {}
    for idx, plan in out:
        assert plan.source == "confluence"
        key = plan.direction
        if key in seen:
            assert idx - seen[key] >= GATES["cooldown_bars"], (idx, seen[key])
        seen[key] = idx


def test_replay_respects_warmup_and_gates():
    df = _structured_df()
    out = bs.replay_scenarios("AAPL", df, "4w",
                              gates=dict(GATES, min_reward_pct=500.0))
    assert out == []                # impossible gate -> nothing
    out2 = bs.replay_scenarios("AAPL", df.iloc[:30], "4w", gates=GATES)
    assert out2 == []               # below MIN_BARS -> nothing


def test_scenario_backtest_stats_shape_and_win():
    df = _structured_df()
    stats = bs.run_scenario_backtest({"AAPL": df}, None, None,
                                     gates=GATES, scale_out=False,
                                     horizons=["4w"])
    assert set(stats) >= {"pooled", "by_horizon"}
    pooled = stats["pooled"]
    for key in ("n", "wins", "losses", "scratches", "timeouts",
                "not_triggered", "win_rate", "expectancy_r"):
        assert key in pooled, key
    assert pooled["n"] >= 1
    assert stats["by_horizon"]["4w"]["n"] == pooled["n"]
