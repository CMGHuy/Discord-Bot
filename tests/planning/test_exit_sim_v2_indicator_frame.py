"""v173 (plan panel): walk_v2 can read its runner indicators from a separate frame.

`indicator_df` feeds only ATR(14) and the structure frame; `df` still drives
every stop, target and close check. Omitted, nothing changes. Expected R
figures were taken from walk_v2 on these exact bars under pin_code_defaults
(RUNNER_STRUCTURE_EXIT "off"): 3.691 un-spiked, 3.565 with the wide bar 18,
3.697 for the clamped frame walked on its own (clamped) indicators.
"""
import dataclasses

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.market import indicators
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
STOP_BAR = (96.0, 96.5, 94.0, 95.0)
#: rising[15] sits at bar 18 (entry 0, flat 1, TP1 2, rising from 3).
OV_IDX = 18


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=200.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _bars(*, override_bar=None):
    """TP1 on bar 2, twenty rising bars, then bar 23 opens at 129 and trades
    through the trail, so the runner exits AT the trailing stop (an
    ATR-priced exit). `override_bar` replaces bar 18."""
    rising = [(110.0 + i, 111.0 + i, 109.0 + i, 110.5 + i) for i in range(20)]
    if override_bar is not None:
        rising[15] = override_bar
    return make_ohlcv([ENTRY, FLAT, TP1_BAR, *rising, (129.0, 129.5, 100.0, 101.0)])


SPIKE = (125.0, 150.0, 124.0, 125.5)      # wide high, touches neither trail nor TP2
WICK = (125.0, 126.0, 100.0, 125.5)       # deep low: touches the trail on the real bar


def _clamp(df, i):
    frame = df.copy()
    body = sorted((float(frame["Open"].iat[i]), float(frame["Close"].iat[i])))
    frame.iloc[i, frame.columns.get_loc("Low")] = body[0]
    frame.iloc[i, frame.columns.get_loc("High")] = body[1]
    return frame


def _walk(df, plan=None, *, scale_out=True, instrument=V2, **kw):
    return walk_v2(df, 0, 100.0, plan or _plan(), 28, instrument, scale_out=scale_out, **kw)


def _spy_atr(monkeypatch):
    """Record every frame ATR is computed from (_runner_v2 imports
    indicators.atr at call time, so patching the module attribute reaches it)."""
    seen = []
    real_atr = indicators.atr

    def spy(frame, period=14):
        seen.append(frame)
        return real_atr(frame, period)

    monkeypatch.setattr(indicators, "atr", spy)
    return seen


# --- omitted == the frame itself: byte-identical --------------------------------

@pytest.mark.parametrize("override_bar, r_total", [(None, 3.691), (SPIKE, 3.565)])
def test_omitted_and_the_frame_itself_give_equal_results(override_bar, r_total):
    df = _bars(override_bar=override_bar)
    default, explicit = _walk(df), _walk(df, indicator_df=df)
    assert default == explicit
    assert (default.runner_outcome, default.exit_index, default.r_total) == (
        "runner_trail", 23, r_total)
    assert default.tp1_index == explicit.tp1_index == 2


@pytest.mark.parametrize("bars", [[ENTRY, FLAT, TP1_BAR], [ENTRY, STOP_BAR], [ENTRY, FLAT, FLAT]])
def test_single_leg_walks_ignore_the_indicator_frame(bars):
    df = make_ohlcv(bars)
    plan = _plan(tp1_fraction=1.0, tp2=None)
    assert _walk(df, plan, scale_out=False, instrument=FREE) == _walk(
        df, plan, scale_out=False, instrument=FREE, indicator_df=_clamp(df, 1))


# --- a clamped frame with the real indicators -------------------------------------

def test_the_clamped_frame_reads_atr_from_the_real_bars(monkeypatch):
    seen = _spy_atr(monkeypatch)
    real = _bars(override_bar=SPIKE)
    clamped = _clamp(real, OV_IDX)
    res = _walk(clamped, indicator_df=real)
    assert seen and seen[-1] is real
    assert res.r_total == _walk(real).r_total == 3.565


def test_without_the_keyword_the_clamped_frame_reads_its_own_atr(monkeypatch):
    seen = _spy_atr(monkeypatch)
    clamped = _clamp(_bars(override_bar=SPIKE), OV_IDX)
    res = _walk(clamped)
    assert seen[-1] is clamped
    assert res.r_total == 3.697


def test_the_structure_frame_reads_the_real_bars_too(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    seen = []
    real_frame = exit_sim_v2.runner_structure_frame

    def spy(frame):
        seen.append(frame)
        return real_frame(frame)

    monkeypatch.setattr(exit_sim_v2, "runner_structure_frame", spy)
    real = _bars(override_bar=SPIKE)
    _walk(_clamp(real, OV_IDX), indicator_df=real)
    assert seen and seen[-1] is real


def test_exit_checks_still_read_the_walked_frame():
    """The real bar 18 wicks through the trail; its clamped body does not. With
    real indicators the clamped walk still does not stop on bar 18."""
    real = _bars(override_bar=WICK)
    on_real = _walk(real)
    on_clamped = _walk(_clamp(real, OV_IDX), indicator_df=real)
    assert (on_real.runner_outcome, on_real.exit_index) == ("runner_trail", OV_IDX)
    assert (on_clamped.runner_outcome, on_clamped.exit_index) == ("runner_trail", 23)


# --- the frames must line up --------------------------------------------------------

def test_an_indicator_frame_of_another_length_is_refused():
    df = _bars()
    with pytest.raises(ValueError, match="same index"):
        _walk(df, indicator_df=df.iloc[:-1])


def test_an_indicator_frame_on_other_dates_is_refused():
    df = _bars()
    shifted = df.copy()
    shifted.index = df.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="same index"):
        _walk(df, indicator_df=shifted)


def test_the_check_runs_on_every_path_not_only_the_runner():
    df = make_ohlcv([ENTRY, STOP_BAR])
    with pytest.raises(ValueError, match="same index"):
        _walk(df, _plan(tp1_fraction=1.0, tp2=None), scale_out=False, indicator_df=df.iloc[:1])
