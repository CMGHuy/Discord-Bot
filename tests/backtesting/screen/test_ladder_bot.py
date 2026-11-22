"""v238 rung 3: the bot's stop on the event bar, sized not dropped, no lookahead."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.backtesting.screen import ladder_bot as lb
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import builders
from swingbot.core.planning.targets import _safe_atr_value, atr_target_candidates
from swingbot.core.risk_limits import planned_loss_pct
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

BAND = SimpleNamespace(min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _calm():
    """Price near 1000, High/Low +-1: ATR about 2, so 2 ATR is about 0.4%."""
    return frame(np.linspace(1000.0, 1010.0, 80), start="2017-03-01")


def test_bot_shape_names_its_stand_ins():
    assert set(lb.BOT_SHAPE) == {"stop_entry_point", "target_entry_point", "strategy",
                                 "horizon_key", "why"}
    assert lb.BOT_SHAPE["horizon_key"] in HORIZONS
    assert lb.BOT_SHAPE["strategy"] not in builders._STRUCTURAL_BRANCHES   # sizes via _atr_branch
    assert all(isinstance(v, str) and v.strip() for v in lb.BOT_SHAPE.values())


def test_bot_stop_is_the_live_atr_plan_stop_when_inside_the_cap():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    atr_val = _safe_atr_value(close, float(atr_indicator(df.iloc[: t + 1], 14).iloc[t]))
    live = builders._atr_plan(close, atr_val, "bullish", "2w", "RSI",
                              candidate_levels=atr_target_candidates(close, atr_val, "bullish"),
                              params=BAND)
    assert lb.bot_stop(df, t, direction="long") == pytest.approx(live[0])


def test_a_wide_stop_is_kept_and_flagged_not_capped():
    df, t = random_walk(200, seed=3), 150
    close = float(df["Close"].iloc[t])
    stop = lb.bot_stop(df, t, direction="long")
    atr_val = float(atr_indicator(df.iloc[: t + 1], 14).iloc[t])
    assert stop == pytest.approx(close - HORIZONS["2w"]["atr_stop_multiple"] * atr_val)
    assert planned_loss_pct(close, stop) > 2.0          # ~1.5% daily vol: 2 ATR is ~4%
    assert lb.clamp_would_drop(close, stop, direction="long")


def test_short_stop_mirrors_the_long_stop():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    long_stop = lb.bot_stop(df, t, direction="long")
    assert lb.bot_stop(df, t, direction="short") == pytest.approx(2 * close - long_stop)


def test_missing_atr_uses_the_live_two_percent_fallback():
    df = _calm()
    close = float(df["Close"].iloc[0])
    assert lb.bot_stop(df, 0, direction="long") == pytest.approx(close - 2.0 * 0.02 * close)


def test_rung3_target_keeps_two_r_from_the_signal_close():
    df, t = _calm(), 60
    close = float(df["Close"].iloc[t])
    for direction in ("long", "short"):
        stop, target = lb.rung3_levels(df, t, direction=direction)
        assert stop == pytest.approx(lb.bot_stop(df, t, direction=direction))
        assert abs(target - close) == pytest.approx(2.0 * abs(close - stop))
        assert (target > close) == (direction == "long")


@pytest.mark.parametrize("entry, stop, direction, dropped", [
    (100.0, 98.0, "long", False), (100.0, 97.99, "long", True),
    (100.0, 102.0, "short", False), (100.0, 102.01, "short", True),
])
def test_clamp_would_drop_at_the_two_percent_boundary(entry, stop, direction, dropped):
    assert lb.clamp_would_drop(entry, stop, direction=direction) is dropped


def test_bad_inputs_are_refused():
    df = _calm()
    with pytest.raises(ValueError):
        lb.bot_stop(df, 10, direction="bullish")
    with pytest.raises(ValueError):
        lb.clamp_would_drop(100.0, 98.0, direction="up")
    with pytest.raises(IndexError):
        lb.bot_stop(df, len(df), direction="long")


def test_stop_and_target_never_read_a_bar_after_the_signal():
    df = random_walk(260, seed=5)
    for t in (20, 120, 200):
        altered = df.copy()
        altered.iloc[t + 1:] = altered.iloc[t + 1:] * 3.0
        for direction in ("long", "short"):
            full = lb.rung3_levels(df, t, direction=direction)
            assert lb.rung3_levels(df.iloc[: t + 1], t, direction=direction) == full
            assert lb.rung3_levels(altered, t, direction=direction) == full

    def stops(d):
        return [lb.bot_stop(d, i, direction="long") for i in range(len(d))]

    assert_prefix_stable(stops, df, [30, 150])
