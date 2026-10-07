"""v103 C builder side: own targets, drop-don't-cap sizing, backtest == live."""
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import _plan_series, _v1_plan_levels
from swingbot.core.planning import builders
from swingbot.core.planning.builders import _fib_continuation_plan, build_strategy_plan
from swingbot.core.planning.params import exit_params_for
from swingbot.core.planning.targets import fib_continuation_targets, select_structural_target
from tests.market.test_fib_continuation import HZ, _frame

C = "Fibonacci Continuation"


def test_targets_use_correct_extension_arithmetic():
    assert fib_continuation_targets(110.0, 10.0, 105.0, "bullish") == pytest.approx([115.0, 112.72, 116.18])
    assert fib_continuation_targets(100.0, 10.0, 105.0, "bearish") == pytest.approx([95.0, 97.28, 93.82])


def test_nearest_target_inside_the_band_is_chosen():
    structure = {"level": 99.5, "impulse": 10.0, "retrace": 95.0, "stop": 99.0}
    stop, tp1 = _fib_continuation_plan(100.0, structure, "bullish", HZ, [102.0, 103.0, 104.0])
    assert stop == 99.0 and tp1 == 102.0


def test_stop_over_the_cap_builds_nothing():
    structure = {"level": 98.5, "impulse": 10.0, "retrace": 95.0, "stop": 97.5}
    assert _fib_continuation_plan(100.0, structure, "bullish", HZ, [105.0]) is None


def test_exit_params_are_the_pre_registered_defaults():
    params = exit_params_for(C)
    assert params["trail_atr_mult"] == 2.5 and params["tp2"] is True


def test_branch_table_routes_continuation():
    assert builders._STRUCTURAL_BRANCHES[C] is builders._fib_continuation_branch


def test_backtest_and_live_build_the_same_plan(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df, index = _frame()
    atr_series, high, low, ratio, entry_levels = _plan_series(df, C, HZ)
    entry, stop, tp1 = _v1_plan_levels(df, index, "bullish", C, HZ, atr_series, high, low, ratio, entry_levels)
    assert entry == 110.5 and stop < 110.0
    expected = select_structural_target(
        entry, stop, True, fib_continuation_targets(110.0, 10.0, 105.0, "bullish"), 1.5, 2.5,
    )
    assert tp1 == pytest.approx(expected)
    plan = build_strategy_plan(df.iloc[:index + 1], index, ticker="TST", strategy=C, horizon_key=HZ, direction="bullish")
    assert plan.stop_loss == stop and plan.tp1 == pytest.approx(tp1)


def test_no_signal_bar_builds_nothing_on_either_path(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df, index = _frame()
    atr_series, high, low, ratio, entry_levels = _plan_series(df, C, HZ)
    assert _v1_plan_levels(df, index + 1, "bullish", C, HZ, atr_series, high, low, ratio, entry_levels) is None
    assert build_strategy_plan(df, index + 1, ticker="TST", strategy=C, horizon_key=HZ, direction="bullish") is None
