"""Tests for backtest_scenarios.levels_asof memoization."""
import numpy as np

from swingbot.core.backtesting import backtest_scenarios as bs
from tests.helpers import make_ohlcv
import pytest

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


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


def test_replayed_plans_carry_no_issued_at():
    """v87: a replayed plan has no wall-clock issuance. issued_at is stamped
    by analyze.attach_plan_v2 only; a backtest plan carrying one would pool
    fabricated timestamps into any later entry-timing study."""
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    assert all(plan.issued_at is None for _, plan in out)


def test_bucket_bar_is_the_first_bar_the_replay_visits_in_the_bucket():
    from swingbot.core.market.strategy_types import MIN_BARS

    warmup = MIN_BARS["4w"]
    first_full = (warmup // bs.LEVEL_REFRESH_BARS + 1) * bs.LEVEL_REFRESH_BARS
    assert bs.bucket_bar(first_full, "4w") == first_full
    assert bs.bucket_bar(first_full + 4, "4w") == first_full
    assert bs.bucket_bar(first_full + 5, "4w") == first_full + 5
    assert bs.bucket_bar(warmup, "4w") == warmup          # never before warm-up
    assert bs.bucket_bar(warmup + 1, "4w") >= warmup


def test_scenarios_at_rebuilds_what_the_replay_saw_at_each_plan_bar():
    from swingbot.scan_params import ScanParams
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    frame = load_v74_fixture()["AAPL"]
    params = ScanParams.from_config()
    plans = bs.replay_scenarios("AAPL", frame, "4w", params=params)
    assert plans, "fixture must produce confluence plans or the test proves nothing"
    for index, plan in plans[:20]:
        cache = {}
        bs.levels_asof("AAPL", frame, bs.bucket_bar(index, "4w"), "4w", cache)   # prime the bucket
        window, price, supports, resistances, scenarios = bs.scenarios_at(
            "AAPL", frame, index, "4w", params, cache)
        assert len(window) == index + 1
        assert price == float(frame["Close"].iloc[index])
        assert all(level.price < price for level in supports)
        assert all(level.price > price for level in resistances)
        assert any(scenario.direction == plan.direction for scenario in scenarios)


def test_scenarios_at_ignores_every_later_bar():
    """NO-LOOKAHEAD: rewriting the frame after bar i leaves bar i's scenarios unchanged."""
    from swingbot.scan_params import ScanParams
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    frame, params, index = load_v74_fixture()["AAPL"], ScanParams.from_config(), 300
    poisoned = frame.copy()
    poisoned.iloc[index + 1:] = poisoned.iloc[index + 1:] * 10.0
    clean = bs.scenarios_at("AAPL", frame, index, "4w", params, {})
    dirty = bs.scenarios_at("AAPL", poisoned, index, "4w", params, {})
    assert clean[1:] == dirty[1:]
