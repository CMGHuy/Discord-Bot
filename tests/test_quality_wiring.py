from swingbot.core.plan_engine import build_strategy_plan
from tests.helpers import make_ohlcv

QI = dict(regime="bullish", htf_bias="bullish", confluence_count=3,
          volume_ratio=1.5, atr_pct=0.4, trigger_distance_pct=0.3)


def test_quality_inputs_fill_score_tier_breakdown():
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                            horizon_key="4w", direction="bullish",
                            quality_inputs=QI)
    assert p.quality_score > 0
    assert p.tier in ("A", "B", "C")
    assert len(p.quality_breakdown) == 7


def test_no_quality_inputs_stays_zero_c_and_never_crashes():
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                            horizon_key="4w", direction="bullish")
    assert p.quality_score == 0 and p.tier == "C" and p.quality_breakdown == []
