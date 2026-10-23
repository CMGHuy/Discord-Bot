"""v182 range breakdown: the frozen range, trend and first-break clauses.

Fixture: a 60-bar decline 160 -> 101, a 30-bar range on bars 60..89
(Low 99, High 101, Close 100), the event bar 90, four bars at 97. True range
is exactly 2 on every bar before 90, so ATR14[89] = 2.0, the touch band is
0.5 and the height limit is 10. For t = 90: S = 99, R = 101.
"""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

T = 90


def breakdown_frame(*, event_close=97.0, event_low=None, event_open=None, edit=None,
                    decline=60):
    """The fixture above. ``edit(opens, highs, lows, closes)`` changes bars in
    place before the frame is built; ``decline`` shortens the prefix (the
    event bar is then ``decline + 30``)."""
    closes = np.r_[160.0 - np.arange(decline), np.full(30, 100.0), np.full(5, 97.0)]
    t = decline + 30
    closes[t] = event_close
    opens, highs, lows = closes.copy(), closes + 1.0, closes - 1.0
    if event_low is not None:
        lows[t] = event_low
    if event_open is not None:
        opens[t] = event_open
    if edit is not None:
        edit(opens, highs, lows, closes)
    return frame(closes, opens=opens, highs=highs, lows=lows)


def _setup_bars(df):
    return np.flatnonzero(rb.setup(df).to_numpy()).tolist()


def test_rolling_min_is_the_minimum_over_the_last_n_bars_t_included():
    out = indicators.rolling_min(pd.Series([5.0, 3.0, 4.0, 1.0, 2.0]), 3)
    assert out.iloc[:2].isna().all()
    assert out.iloc[2:].tolist() == [3.0, 1.0, 1.0]


def test_the_definition_is_frozen_at_the_spec_values():
    assert (rb.WINDOW, rb.HEIGHT_ATR, rb.TOUCH_ATR, rb.TOUCH_SPAN) == (30, 5.0, 0.25, 5)
    assert (rb.SMA_LEN, rb.SMA_LAG, rb.WARMUP) == (50, 10, 61)
    assert rb.PARAMS == {"window": 30, "height_atr": 5.0, "touch_atr": 0.25,
                         "touch_span": 5, "sma": 50, "sma_lag": 10, "warmup": 61}
    assert rb.FAMILY == ("range_breakdown_close", "range_breakdown_stop")
    assert rb.SOURCE == ('Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07), '
                         "downswing breakout")


def test_levels_read_the_thirty_bars_before_t():
    df = breakdown_frame()
    assert rb.support(df).iloc[T] == 99.0
    assert rb.resistance(df).iloc[T] == 101.0
    assert rb.prior_atr(df).iloc[T] == 2.0
    inside = breakdown_frame(edit=lambda o, h, l, c: l.__setitem__(60, 98.0))
    outside = breakdown_frame(edit=lambda o, h, l, c: l.__setitem__(59, 50.0))
    assert rb.support(inside).iloc[T] == 98.0       # bar t-30 is in the window
    assert rb.support(outside).iloc[T] == 99.0      # bar t-31 is not


def test_the_fixture_sets_up_on_the_event_bar_only():
    assert _setup_bars(breakdown_frame()) == [T]


def _tall(o, h, l, c):
    h[70] = h[80] = 125.0          # two high touches 10 apart, height 26 > 5 x ATR


def _low_touches(a, b):
    def edit(o, h, l, c):
        l[60:90] = 99.75           # 0.75 above S: outside the 0.25 x ATR band
        l[a] = l[b] = 99.0
    return edit


def _high_touches(a, b):
    def edit(o, h, l, c):
        h[60:90] = 100.25
        h[a] = h[b] = 101.0
    return edit


def _one_low_touch(o, h, l, c):
    l[60:90] = 99.75
    l[75] = 99.0


@pytest.mark.parametrize("edit, expected", [
    (None, True),
    (_tall, False),                     # range too tall
    (_one_low_touch, False),            # one touch of S only
    (_low_touches(75, 79), False),      # touches of S four bars apart
    (_low_touches(75, 80), True),       # five bars apart
    (_high_touches(75, 79), False),     # touches of R four bars apart
    (_high_touches(75, 80), True),
])
def test_range_clauses(edit, expected):
    df = breakdown_frame(edit=edit)
    assert bool(rb.in_range(df).iloc[T]) is expected
    assert bool(rb.setup(df).iloc[T]) is expected


def test_a_tall_range_still_passes_the_trend_only_control():
    df = breakdown_frame(edit=_tall)
    assert not rb.setup(df).iloc[T]
    assert rb.control_setup(df).iloc[T]


def test_a_rising_prefix_is_not_a_downtrend():
    def rising(o, h, l, c):
        c[:60] = 41.0 + np.arange(60)
        o[:60], h[:60], l[:60] = c[:60], c[:60] + 1.0, c[:60] - 1.0
    df = breakdown_frame(edit=rising)
    assert not rb.downtrend(df).iloc[T]
    assert not rb.setup(df).iloc[T] and not rb.control_setup(df).iloc[T]


@pytest.mark.parametrize("closes, expected", [
    (np.r_[200.0 - np.arange(100), 99.0, 99.0], True),     # SMA50 falling, close below
    (np.r_[200.0 - np.arange(100), 200.0, 99.0], False),   # falling, close above
    (np.r_[100.0 + np.arange(100), 50.0, 50.0], False),    # rising, close below
])
def test_downtrend_needs_a_falling_sma50_and_the_prior_close_below_it(closes, expected):
    assert bool(rb.downtrend(frame(closes)).iloc[101]) is expected


@pytest.mark.parametrize("close89, low89, expected", [
    (99.0, 99.0, True),           # prior close exactly at its own support S[t-1] = 99
    (98.9375, 98.875, False),     # prior close already below S[t-1]
])
def test_first_break_compares_the_prior_close_with_its_own_support(close89, low89, expected):
    """Consistent bars only (Low <= Close): S[t-1] is the support of bar t-1's
    window (t-31..t-2), so bar t-1's own Low is not part of it."""
    def edit(o, h, l, c):
        c[89], o[89], l[89] = close89, close89, low89
    df = breakdown_frame(edit=edit)
    assert rb.support(df).shift(1).iloc[T] == 99.0
    assert bool(rb.first_break(df).iloc[T]) is expected
    assert bool(rb.setup(df).iloc[T]) is expected


def test_a_second_consecutive_breakdown_bar_does_not_fire():
    """Bar 90 closes below S = 99 (low 98.875); bar 91 closes lower still.
    Bar 91 meets every other clause (its window now holds 98.875 as S, the
    99 lows touch it), but its prior close was already below its own support,
    so only the first break sets up."""
    df = breakdown_frame(event_close=98.9375, event_low=98.875)
    assert rb.setup(df).iloc[T]
    nxt = T + 1
    assert rb.in_range(df).iloc[nxt] and rb.downtrend(df).iloc[nxt]
    assert df["Close"].iloc[nxt] < rb.support(df).iloc[nxt]       # a breakdown bar again
    assert not rb.first_break(df).iloc[nxt]
    assert not rb.setup(df).iloc[nxt] and not rb.control_setup(df).iloc[nxt]
    assert _setup_bars(df) == [T]


def test_warm_up_needs_61_bars_before_the_event():
    early = breakdown_frame(decline=30)      # event bar 60
    assert rb.in_range(early).iloc[60] and rb.downtrend(early).iloc[60]
    assert not rb.setup(early).iloc[60]
    assert _setup_bars(breakdown_frame(decline=31)) == [61]


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan])
def test_a_zero_negative_or_nan_prior_atr_gives_no_setup(monkeypatch, value):
    df = breakdown_frame()
    monkeypatch.setattr(rb, "prior_atr", lambda frame_: pd.Series(value, index=frame_.index))
    assert not rb.setup(df).any()
    assert not rb.control_setup(df).any()


def test_every_clause_is_a_clean_bool_series():
    walk = random_walk(400)
    for fn in (rb.in_range, rb.downtrend, rb.first_break, rb.setup, rb.control_setup):
        out = fn(walk)
        assert out.dtype == bool and out.index.equals(walk.index), fn.__name__


def test_setup_at_t_never_reads_bar_t():
    df = breakdown_frame()
    wild = df.copy()
    wild.iloc[T] = [50.0, 300.0, 10.0, 20.0, 1e6]
    for fn in (rb.support, rb.resistance, rb.prior_atr):
        assert fn(wild).iloc[T] == fn(df).iloc[T]
    assert rb.setup(wild).iloc[T] and rb.control_setup(wild).iloc[T]


def test_setup_reads_no_later_bar():
    assert _setup_bars(breakdown_frame()) == [T]                   # non-vacuous
    assert_prefix_stable(rb.setup, breakdown_frame(), [60, 89, 90, 91, 94])
    walk = random_walk(3000)
    assert rb.setup(walk).any()
    assert_prefix_stable(rb.setup, walk, [100, 1500, 2999])
    assert_prefix_stable(rb.control_setup, walk, [100, 1500, 2999])
