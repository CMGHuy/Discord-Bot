"""Tests for backtest_scenarios.levels_asof memoization."""
from swingbot.core import backtest_scenarios as bs
from tests.helpers import make_ohlcv


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
