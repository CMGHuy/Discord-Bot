"""v103 A builder side: the level-stop is used verbatim, or no plan is built."""
import math

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import _plan_series, _trade_plan_at
from swingbot.core.market import entry_filters as ef
from swingbot.core.planning.builders import _fibonacci_plan, build_strategy_plan
from tests.market.test_fib_sr_confluence import _bull_signal_frame


def test_level_stop_is_used_verbatim():
    stop, tp1 = _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w",
        candidate_levels=[105.0], level_stop=99.0,
    )
    assert stop == 99.0 and tp1 == pytest.approx(102.5)


def test_level_stop_over_the_cap_builds_nothing():
    assert _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w",
        candidate_levels=[105.0], level_stop=97.9,
    ) is None


def test_level_stop_on_the_wrong_side_or_nan_builds_nothing():
    keyword_args = dict(candidate_levels=[105.0, 95.0])
    assert _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w", level_stop=100.5, **keyword_args,
    ) is None
    assert _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w", level_stop=math.nan, **keyword_args,
    ) is None
    assert _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bearish", "4w", level_stop=99.5, **keyword_args,
    ) is None


def test_no_level_stop_keeps_the_swing_stop():
    legacy = _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w", candidate_levels=[105.0],
    )
    same = _fibonacci_plan(
        100.0, 1.0, 110.0, 90.0, "bullish", "4w",
        candidate_levels=[105.0], level_stop=None,
    )
    assert legacy == same and legacy[0] == pytest.approx(98.0)


def test_backtest_and_live_build_the_same_level_stop_plan(monkeypatch):
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_ATR", 0.1, raising=False)
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_DIRECTIONS", "bullish", raising=False)
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df = _bull_signal_frame()
    helper = ef.fib_level_stop_series(df, "4w", "bullish", 0.1)
    atr_series, swing_high, swing_low, volume_ratio, entry_levels = _plan_series(
        df, "Fibonacci", "4w",
    )
    checked = 0
    for index in [i for i in range(len(df)) if not math.isnan(helper.iloc[i])]:
        backtest_plan = _trade_plan_at(
            df, index, "bullish", "Fibonacci", "4w", atr_series, swing_high,
            swing_low, volume_ratio, entry_levels,
        )
        if backtest_plan is None:
            continue
        _, backtest_stop, backtest_tp = backtest_plan
        assert backtest_stop == helper.iloc[index]
        plan = build_strategy_plan(
            df.iloc[:index + 1], index, ticker="TST", strategy="Fibonacci",
            horizon_key="4w", direction="bullish",
        )
        assert plan is not None and plan.stop_loss == backtest_stop
        assert plan.tp1 == pytest.approx(backtest_tp)
        checked += 1
        if checked == 5:
            break
    assert checked > 0, "the frame must yield at least one eligible level-stop plan"
