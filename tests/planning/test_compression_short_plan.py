"""V119-5: First Bearish Compression Release -- resting stop-entry trigger, structural
stop above the release high, one confirmed lower-support target (no ATR fallback)."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.levels import Level
from swingbot.core.market.short_entries import COMPRESSION_SHORT
from swingbot.core.market.indicators import atr
from swingbot.core.planning import short_builders as sb
from swingbot.core.planning.builders import (build_strategy_plan,
                                             strategy_entry_reference)
from swingbot.core.planning.params import EXIT_V2_PARAMS, PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.scan_params import ScanParams
from tests.market.test_squeeze_release_series import _frame

HZ = "2w"
LOW = 95.95       # release bar: Close 96, Low 95.95, High 96.05
TRIGGER = 95.94   # one $0.01 tick below the release low


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)


@pytest.fixture
def frame():
    return _frame([96])


def _levels(*prices):
    return [Level(price=p, sources=["Swing low", "Pivot low"]) for p in prices], []


def _plan(df, level_map, index=None):
    return build_strategy_plan(df, len(df) - 1 if index is None else index, ticker="ABC",
                               strategy=COMPRESSION_SHORT, horizon_key=HZ,
                               direction="bearish", level_map=level_map)


def _atr(df):
    return float(atr(df, 14).iloc[-1])


def test_plan_is_a_resting_stop_entry_below_the_release_low(frame):
    plan = _plan(frame, _levels(95.40))
    assert plan.trigger_price == TRIGGER != float(frame["Close"].iloc[-1])
    assert (plan.entry_type, plan.entry_price, plan.status) == ("stop_entry", None, PlanStatus.PENDING)
    assert plan.stop_loss > float(frame["High"].iloc[-1])
    assert plan.stop_loss == pytest.approx(float(frame["High"].iloc[-1]) + 0.25 * _atr(frame))
    assert plan.tp1 == 95.40 < plan.trigger_price
    assert (plan.tp1_fraction, plan.tp2, plan.expiry_bars, plan.hold_cap_bars) == (1.0, None, 1, 10)
    assert plan.breakeven_trigger_fraction == 1.0


@pytest.mark.parametrize("low, expected", [(95.95, 95.94), (95.955, 95.94), (95.9, 95.89),
                                           (10.07, 10.06), (10.0, 9.99)])
def test_trigger_is_one_valid_penny_tick_below_the_low(frame, low, expected):
    frame.iloc[-1, frame.columns.get_loc("Low")] = low
    assert strategy_entry_reference(frame, len(frame) - 1, COMPRESSION_SHORT) == expected


def test_other_strategies_keep_the_signal_close(frame):
    assert strategy_entry_reference(frame, len(frame) - 1, "RSI") == float(frame["Close"].iloc[-1])


def test_stop_beyond_the_ceiling_rejects_never_clamps(frame):
    frame.iloc[-1, frame.columns.get_loc("High")] = 100.0   # ~4.6% above the trigger, 2w ceiling 3%
    assert _plan(frame, _levels(95.40)) is None
    atr_val = _atr(frame)
    assert sb.compression_structure(frame, len(frame) - 1, trigger=TRIGGER, atr_val=atr_val,
                                    horizon_key=HZ, level_map=_levels(95.40),
                                    scan_params=ScanParams.from_config()) is None


def test_nearest_support_inside_the_rr_band_is_the_target(frame):
    # 95.80 pays 0.55R (too near); 95.40 and 95.30 pay ~2.1R / 2.5R; 93.0 is past max RR.
    plan = _plan(frame, _levels(95.80, 95.40, 95.30, 93.0))
    assert plan.tp1 == 95.40


def test_no_lower_support_yields_no_plan(frame):
    assert _plan(frame, ([], [])) is None
    assert _plan(frame, _levels(97.5)) is None   # a level above the trigger is not a target


def test_a_support_beyond_max_rr_is_not_capped_into_a_synthetic_target(frame):
    assert _plan(frame, _levels(93.0)) is None


def test_a_support_inside_min_rr_yields_no_plan(frame):
    assert _plan(frame, _levels(95.80)) is None


def test_risk_and_rr_are_measured_from_the_trigger_not_the_close(frame):
    index, atr_val, params = len(frame) - 1, _atr(frame), ScanParams.from_config()
    close = float(frame["Close"].iloc[-1])
    kw = dict(atr_val=atr_val, horizon_key=HZ, level_map=_levels(95.50), scan_params=params)
    from_trigger = sb.compression_structure(frame, index, trigger=TRIGGER, **kw)
    from_close = sb.compression_structure(frame, index, trigger=close, **kw)
    assert from_trigger is not None and from_trigger[1] == 95.50   # 1.72R off the trigger
    assert from_close is None                                      # 2.55R off the close: past 2.5


def test_the_level_map_is_built_as_of_the_signal_bar(frame, monkeypatch):
    seen = []

    def spy(window, horizon, price, *a, **k):
        seen.append(window)
        return _levels(95.40)

    monkeypatch.setattr(levels_mod, "build_level_map", spy)
    release_index = len(frame) - 1
    tomorrow = frame.iloc[[-1]].copy()
    tomorrow.index = [frame.index[-1] + pd.offsets.BDay(1)]
    tomorrow[["Open", "High", "Low", "Close"]] = [90.0, 90.5, 60.0, 61.0]   # a huge swing low tomorrow
    extended = pd.concat([frame, tomorrow])

    plan_now, plan_later = _plan(frame, None), _plan(extended, None, index=release_index)
    assert seen, "level map must be built by the builder when the caller supplies none"
    assert all(len(w) == release_index + 1 and w.index[-1] == frame.index[-1] for w in seen)
    assert (plan_now.tp1, plan_now.stop_loss) == (plan_later.tp1, plan_later.stop_loss) == (95.40, plan_now.stop_loss)


def test_params_rows():
    assert PLAN_SHAPES[COMPRESSION_SHORT] == {"entry_type": "stop_entry", "expiry_bars": 1,
                                              "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0,
                                              "hold_cap_bars": 10}
    assert EXIT_V2_PARAMS[COMPRESSION_SHORT]["tp2"] is False


def test_other_strategies_never_get_a_hold_cap():
    from tests.market.test_fade_entries import HZ as FADE_HZ, fade_df
    from swingbot.core.market.short_entries import FADE
    df, t = fade_df()
    plan = build_strategy_plan(df, t, ticker="T", strategy=FADE, horizon_key=FADE_HZ, direction="bearish")
    assert plan.hold_cap_bars is None


def test_the_level_lifecycle_never_moves_the_compression_stop_or_target(frame, monkeypatch):
    from swingbot.core.planning import builders
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", True, raising=False)
    calls = []

    def widener(*a, stop, tp1, **k):   # what a tested resistance above the high would do
        calls.append(1)
        return stop + 0.1, tp1 - 0.1, {"lifecycle_stop": {}}

    monkeypatch.setattr(builders, "apply_level_lifecycle", widener)
    plan = _plan(frame, _levels(95.40))
    assert not calls
    assert plan.stop_loss == pytest.approx(float(frame["High"].iloc[-1]) + 0.25 * _atr(frame))
    assert plan.tp1 == 95.40


def test_reward_floor_is_checked_on_the_trigger_and_target(frame, monkeypatch):
    from swingbot.core.planning import reward_floor
    seen = []
    monkeypatch.setattr(reward_floor, "clears", lambda *a: seen.append(a) or False)
    assert _plan(frame, _levels(95.40)) is None
    assert seen == [(TRIGGER, 95.40, COMPRESSION_SHORT, HZ)]
