"""v174 context hook: point-in-time r5, trailing z, gates and exact-date alignment."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import context
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk


def _closes(values, start="2010-01-04"):
    return pd.Series(np.asarray(values, dtype=float),
                     index=pd.bdate_range(start, periods=len(values)))


# --- frozen constants -------------------------------------------------------

def test_the_frozen_constants():
    assert context.CONTEXT_START == "2009-06-01"
    assert (context.LOOKBACK, context.Z_WINDOW) == (5, 252)
    assert context.STD_FLOOR == 1e-12


# --- r_lookback -------------------------------------------------------------

def test_r_lookback_is_a_row_offset_return():
    r = context.r_lookback(_closes([100.0, 110.0, 121.0, 60.5]), lookback=1)
    assert np.isnan(r.iloc[0])
    assert r.iloc[1:].tolist() == pytest.approx([0.1, 0.1, -0.5])


def test_r_lookback_defaults_to_five_bars():
    close = _closes(np.arange(1.0, 12.0))
    r = context.r_lookback(close)
    assert r.iloc[:5].isna().all()
    assert r.iloc[5] == pytest.approx(6.0 / 1.0 - 1.0)
    assert r.iloc[10] == pytest.approx(11.0 / 6.0 - 1.0)


# --- trailing_z: hand-computed values ---------------------------------------

def test_trailing_z_matches_hand_computed_values_and_excludes_t():
    # lookback 1: r = [nan, 1, 1, 0, -0.5, 2]
    z = context.trailing_z(_closes([1.0, 2.0, 4.0, 4.0, 2.0, 6.0]), lookback=1, window=3)
    # t = 4: W = r[1..3] = [1, 1, 0] (t itself is NOT in W)
    w4 = np.array([1.0, 1.0, 0.0])
    assert z.iloc[4] == pytest.approx((-0.5 - w4.mean()) / w4.std(ddof=0))
    assert z.iloc[4] == pytest.approx((-0.5 - 2.0 / 3.0) / np.sqrt(2.0 / 9.0))
    # t = 5: W = r[2..4] = [1, 0, -0.5]
    w5 = np.array([1.0, 0.0, -0.5])
    assert z.iloc[5] == pytest.approx((2.0 - w5.mean()) / w5.std(ddof=0))
    # had t been inside W, z(5) would use [0, -0.5, 2]: a different number
    inside = np.array([0.0, -0.5, 2.0])
    assert z.iloc[5] != pytest.approx((2.0 - inside.mean()) / inside.std(ddof=0))
    # t <= 3: W reaches the NaN r(0) or is short
    assert z.iloc[:4].isna().all()


def test_trailing_z_is_float_named_z_on_the_close_index():
    close = random_walk(300)["Close"]
    z = context.trailing_z(close)
    assert z.dtype == float and z.name == "z"
    assert z.index.equals(close.index)


# --- trailing_z: every undefined case is NaN --------------------------------

def test_fewer_than_252_window_values_give_nan():
    z = context.trailing_z(random_walk(300)["Close"])
    # r5 is defined from bar 5; W = r5[t-252..t-1] is full from t = 257
    assert z.iloc[:257].isna().all()
    assert z.iloc[257:].notna().all()


def test_a_nan_inside_the_window_gives_nan():
    close = random_walk(700)["Close"].copy()
    close.iloc[400] = np.nan                  # r5 is NaN at bars 400 and 405
    z = context.trailing_z(close)
    assert z.iloc[300:400].notna().all()      # W ends at 399: clean
    assert z.iloc[401:658].isna().all()       # W holds r5(400) or r5(405)
    assert z.iloc[658:].notna().all()         # W = r5[406..657]: clean again


def test_a_nan_r_at_t_gives_nan():
    close = random_walk(400)["Close"].copy()
    close.iloc[350] = np.nan
    z = context.trailing_z(close)
    assert np.isnan(z.iloc[350])              # r5(350) is NaN
    assert np.isnan(z.iloc[355])              # r5(355) reads close(350)


def test_a_flat_window_gives_nan_even_on_a_jump():
    values = np.full(300, 100.0)
    values[280:] = 150.0                      # r5(280) = 0.5, W before it is all 0
    z = context.trailing_z(_closes(values))
    assert np.isnan(z.iloc[280])
    assert z.iloc[257:281].isna().all()       # std(W) == 0 on the flat stretch


# --- z_gate -----------------------------------------------------------------

def test_z_gate_reads_the_sign_of_the_threshold():
    z = pd.Series([2.5, 2.0, 1.9, np.nan, -2.0, -2.1])
    assert context.z_gate(z, 2.0).tolist() == [True, True, False, False, False, False]
    assert context.z_gate(z, -2.0).tolist() == [False, False, False, False, True, True]


def test_z_gate_is_bool_and_nan_is_false():
    gate = context.z_gate(pd.Series([np.nan, np.nan]), 2.0)
    assert gate.dtype == bool and not gate.any()


# --- context_on -------------------------------------------------------------

def test_context_on_matches_exact_dates():
    days = pd.to_datetime(["2012-03-05", "2012-03-06", "2012-03-07"])
    series = pd.Series([True, False, True], index=days)
    out = context.context_on(days, series)
    assert out.tolist() == [True, False, True]
    assert out.dtype == bool and out.index.equals(days)


def test_a_stock_date_missing_from_the_context_is_false_never_forward_filled():
    series = pd.Series([True], index=pd.to_datetime(["2012-03-05"]))
    stock = pd.to_datetime(["2012-03-05", "2012-03-06"])
    assert context.context_on(stock, series).tolist() == [True, False]


def test_a_context_only_date_is_ignored():
    series = pd.Series([True, True], index=pd.to_datetime(["2012-03-05", "2012-03-06"]))
    stock = pd.to_datetime(["2012-03-06"])
    out = context.context_on(stock, series)
    assert out.index.equals(stock) and out.tolist() == [True]


def test_context_on_matches_dates_exactly_not_by_day():
    series = pd.Series([True], index=pd.to_datetime(["2012-03-05 16:00"]))
    assert context.context_on(pd.to_datetime(["2012-03-05"]), series).tolist() == [False]


# --- no lookahead -----------------------------------------------------------

def test_trailing_z_and_its_gate_are_prefix_stable():
    df = random_walk(700, seed=3)
    checkpoints = [257, 300, 451, 699]
    assert_prefix_stable(lambda d: context.trailing_z(d["Close"]), df, checkpoints)
    assert_prefix_stable(lambda d: context.z_gate(context.trailing_z(d["Close"]), 1.0),
                         df, checkpoints)


def test_changing_a_context_bar_after_t_never_changes_the_event_at_t():
    ctx = random_walk(800, seed=5, start="2009-06-01")
    stock = ctx.index[::2]                    # a stock calendar inside the context calendar

    def event(frame):
        return context.context_on(stock, context.z_gate(context.trailing_z(frame["Close"]), 1.0))

    before = event(ctx)
    assert before.any()                       # the test has events to protect
    t = ctx.index[600]
    later = ctx.copy()
    later.loc[later.index > t, "Close"] *= 3.0
    after = event(later)
    pd.testing.assert_series_equal(before[before.index <= t], after[after.index <= t])
    assert not before[before.index > t].equals(after[after.index > t])


# --- near_mask --------------------------------------------------------------

def test_near_mask_marks_bars_closer_than_cap_to_a_shock():
    raw = np.zeros(10, dtype=bool)
    raw[4] = True
    assert np.flatnonzero(context.near_mask(raw, 3)).tolist() == [2, 3, 4, 5, 6]
    assert np.flatnonzero(context.near_mask(raw, 1)).tolist() == [4]


def test_near_mask_unions_shocks_and_clips_at_the_edges():
    raw = np.zeros(8, dtype=bool)
    raw[[0, 7]] = True
    assert np.flatnonzero(context.near_mask(raw, 2)).tolist() == [0, 1, 6, 7]


def test_near_mask_without_shocks_is_all_false():
    out = context.near_mask(np.zeros(5, dtype=bool), 10)
    assert out.dtype == bool and not out.any() and len(out) == 5


def test_near_mask_keeps_the_input_length_when_cap_exceeds_it():
    raw = np.zeros(5, dtype=bool)
    raw[2] = True
    out = context.near_mask(raw, 10)
    assert len(out) == 5 and out.all()
