import math

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import (prev_post_entry_pivot, progress_stall_fires,
                                             runner_structure_step, structural_runner_stop)

NAN = math.nan


def _row(**kw):
    base = dict(sh_i=NAN, sh_px=NAN, sh_prev_i=NAN, sh_prev_px=NAN, sl_i=NAN, sl_px=NAN,
                sl_prev_i=NAN, sl_prev_px=NAN, range_trend_10_50=0.5, vol_trend_10_50=0.8)
    base.update(kw)
    return pd.Series(base, dtype=float)


def test_hl_candidate_is_post_entry_swing_low_minus_buffer():
    row = _row(sl_i=12, sl_px=104.0)
    assert structural_runner_stop(row, 2.0, 0.25, "bullish", entry_index=10) == pytest.approx(103.5)


def test_pre_entry_or_missing_pivot_gives_no_stop():
    assert structural_runner_stop(_row(sl_i=10, sl_px=104.0), 2.0, 0.0, "bullish", 10) is None
    assert structural_runner_stop(_row(), 2.0, 0.0, "bullish", 10) is None


def test_bearish_mirror_uses_swing_high_plus_buffer():
    row = _row(sh_i=15, sh_px=96.0)
    assert structural_runner_stop(row, 2.0, 0.5, "bearish", 10) == pytest.approx(97.0)


def _stall(**kw):
    return _row(sh_i=17, sh_px=110.0, sh_prev_i=12, sh_prev_px=111.0, **kw)


def test_stall_fires_only_with_all_four():
    j = 20
    assert progress_stall_fires(_stall(), 111.0, _stall(), 0.7, "bullish", 10, j)
    assert not progress_stall_fires(_stall(), 111.0, _stall(), 0.7, "bullish", 10, j + 1)  # not new
    assert not progress_stall_fires(_stall(), 109.0, _stall(), 0.7, "bullish", 10, j)      # HH held
    hot = _stall(range_trend_10_50=0.9)
    assert not progress_stall_fires(hot, 111.0, hot, 0.7, "bullish", 10, j)                # range
    loud = _stall(vol_trend_10_50=1.2)
    assert not progress_stall_fires(loud, 111.0, loud, 1.0, "bullish", 10, j)              # volume


def test_stall_ignores_nan_ratios_and_missing_prior():
    short = _stall(range_trend_10_50=NAN)
    assert not progress_stall_fires(short, 111.0, short, 1.0, "bullish", 10, 20)
    assert not progress_stall_fires(_stall(), None, _stall(), 1.0, "bullish", 10, 20)


def test_nan_pivot_never_yields_a_stop_or_stall():
    assert structural_runner_stop(_row(sl_i=NAN, sl_px=104.0), 2.0, 0.0, "bullish", 10) is None
    assert not progress_stall_fires(_row(), 111.0, _row(), 1.0, "bullish", 10, 20)


def test_prior_pivot_must_be_post_entry():
    assert prev_post_entry_pivot(_stall(), "bullish", 10) == 111.0
    assert prev_post_entry_pivot(_stall(), "bullish", 12) is None
    bear = _row(sl_i=17, sl_px=90.0, sl_prev_i=13, sl_prev_px=89.0)
    assert prev_post_entry_pivot(bear, "bearish", 10) == 89.0
    assert progress_stall_fires(bear, 89.0, bear, 0.7, "bearish", 10, 20)   # LL failed: 90 >= 89


def test_step_never_loosens_and_off_is_inert(monkeypatch):
    frame = pd.DataFrame([_row(sl_i=12, sl_px=104.0)])
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    kw = dict(entry_index=10, direction="bullish", atr_value=2.0)
    assert runner_structure_step(frame, 0, runner_stop=103.0, **kw) == (104.0, False)
    assert runner_structure_step(frame, 0, runner_stop=105.0, **kw) == (105.0, False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    assert runner_structure_step(frame, 0, runner_stop=103.0, **kw) == (103.0, False)


def test_step_in_progress_stall_mode_wires_prior_pivot_and_range_knob(monkeypatch):
    frame = pd.DataFrame([_row()] * 20 + [_stall(), _stall()]).reset_index(drop=True)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.7)
    kw = dict(entry_index=10, direction="bullish", runner_stop=105.0, atr_value=2.0)
    assert runner_structure_step(frame, 20, **kw) == (105.0, True)
    assert runner_structure_step(frame, 21, **kw) == (105.0, False)       # pivot not new at 21
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.4)            # range 0.5 now too hot
    assert runner_structure_step(frame, 20, **kw) == (105.0, False)
    assert runner_structure_step(frame, 20, **{**kw, "entry_index": 12}) == (105.0, False)  # prior pre-entry


def test_bearish_step_never_loosens(monkeypatch):
    frame = pd.DataFrame([_row(sh_i=12, sh_px=96.0)])
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    kw = dict(entry_index=10, direction="bearish", atr_value=2.0)
    assert runner_structure_step(frame, 0, runner_stop=97.0, **kw) == (96.0, False)
    assert runner_structure_step(frame, 0, runner_stop=95.0, **kw) == (95.0, False)
