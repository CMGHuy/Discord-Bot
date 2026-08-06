from swingbot.core.plan_engine import PlanStatus, build_strategy_plan

from tests.helpers import make_ohlcv


def _df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


def test_market_plan_is_active_and_badged():
    df = _df()
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                            horizon_key="4w", direction="bullish")
    assert p.status == PlanStatus.ACTIVE
    assert p.entry_price == df["Close"].iloc[79]
    assert p.stop_loss < p.entry_price < p.tp1
    assert p.badge in ("VALIDATED", "WEAK") and p.badge_stats
    assert p.created_at == df.index[79].date().isoformat()


def test_weak_strategy_still_builds():
    # The point of this test is that a WEAK badge never blocks the build --
    # not which strategy happens to carry one. The exemplar has moved twice
    # (RSI in Tasks 95-97, EMA Crossover in V25, when the emitter stopped
    # scoring against V6's voided `win_rate >= 80`); no registered strategy is
    # WEAK any more, so this uses the unregistered fallback. Strategy name is
    # only a label to build_strategy_plan's EMA path here.
    p = build_strategy_plan(_df(), 79, ticker="AAPL", strategy="EMA9",
                            horizon_key="4w", direction="bullish")
    assert p is not None and p.badge == "WEAK"


def test_elliott_without_structure_returns_none():
    # A linear ramp has no 5-wave structure -> no wave-2 level at the bar.
    p = build_strategy_plan(_df(), 79, ticker="AAPL", strategy="Elliott Wave",
                            horizon_key="4w", direction="bullish")
    assert p is None
