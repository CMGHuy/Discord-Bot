from swingbot.core import levels
from swingbot.core.strategy_types import HORIZONS
from tests.helpers import make_ohlcv

def test_cluster_merges_within_tolerance():
    # 100.0 and 100.5 are within 1.5% -> one cluster; 110 stands alone.
    clusters = levels._cluster_levels([(100.0, "EMA21"), (100.5, "VWAP"),
                                       (110.0, "Fib 61.8%")])
    assert len(clusters) == 2
    merged = clusters[0]
    assert merged.price == 100.25                      # mean of the bucket
    assert sorted(merged.sources) == ["EMA21", "VWAP"]  # sources preserved

def test_cluster_empty_and_singleton():
    assert levels._cluster_levels([]) == []
    [only] = levels._cluster_levels([(50.0, "VWAP")])
    assert only.price == 50.0 and only.sources == ["VWAP"]

def test_strategy_family_collapses_raw_labels():
    assert levels.strategy_family("Fib 61.8%") == "Fibonacci"
    assert levels.strategy_family("Swing high") == "Fibonacci"
    assert levels.strategy_family("EMA21") == "EMA"
    assert levels.strategy_family("Floor R2") == "Floor Pivot"
    assert levels.strategy_family("Donchian high") == "Donchian Channel"

def test_confluence_count_monotone_in_agreeing_levels():
    # Same frame, widening tolerance can only ADD families, never remove.
    df = make_ohlcv([100 + i * 0.4 for i in range(150)])
    h = HORIZONS["4w"]
    price = float(df["Close"].iloc[-1])
    target = price * 1.05
    n_tight, fam_tight = levels.count_confirming_strategies(df, h, price, target, 1.0)
    n_loose, fam_loose = levels.count_confirming_strategies(df, h, price, target, 8.0)
    assert n_loose >= n_tight
    assert set(fam_tight) <= set(fam_loose)

def test_confluence_count_falsy_target_is_zero():
    df = make_ohlcv([100.0] * 60)
    assert levels.count_confirming_strategies(df, HORIZONS["4w"], 100.0, 0.0, 5.0) == (0, [])
