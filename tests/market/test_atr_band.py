"""V191-7: the ATR band -- raw Wilder ATR14 of completed bars as a percent of
entry, tick rounding away from entry, and the floor / untouched / ceiling stop."""
import pandas as pd
import pytest

from swingbot.core.market import atr_band as ab
from swingbot.core.market import levels
from swingbot.core.risk_limits import planned_loss_pct


def _frame(n=60, close=100.0, half_range=2.0, end="2024-03-28"):
    """Flat closes with a constant high-low range: every true range is
    2 * half_range, so Wilder ATR14 is exactly that from bar 14 on."""
    idx = pd.bdate_range(end=end, periods=n)
    rows = [(close, close + half_range, close - half_range, close, 1_000_000.0)] * n
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


def test_the_frozen_constants():
    assert ab.ATR_PERIOD == 14
    assert ab.BAND_CEILING_ATR == 2.0
    assert ab.FLOOR_GRID == (0.75, 1.0, 1.5)
    assert (ab.MOVED_FLOOR, ab.MOVED_CEILING, ab.MOVED_UNTOUCHED) == ("floor", "ceiling", "untouched")
    assert (ab.REASON_NO_TARGET, ab.REASON_RR_DROP) == ("band_no_target", "band_rr_drop")
    assert (ab.REASON_NO_ATR, ab.REASON_SIZE_ZERO) == ("band_no_atr", "band_size_zero")


def test_raw_atr14_pct_of_a_constant_range_frame():
    assert ab.raw_atr14_pct(_frame(), 100.0) == pytest.approx(4.0)
    assert ab.raw_atr14_pct(_frame(), 50.0) == pytest.approx(8.0)   # a percent of ENTRY


def test_raw_atr_is_not_the_horizon_scaled_floor():
    df = _frame()
    assert levels.atr_floor_pct(df, 100.0, {"atr_stop_multiple": 1.5}) == pytest.approx(6.0)
    assert ab.raw_atr14_pct(df, 100.0) == pytest.approx(4.0)


@pytest.mark.parametrize("df,entry", [
    (None, 100.0),
    (_frame(n=0), 100.0),
    (_frame(n=13), 100.0),                    # Wilder warm-up: NaN before 14 bars
    (_frame(half_range=0.0), 100.0),          # zero range -> ATR 0
    (_frame(), 0.0),
    (_frame(), -1.0),
])
def test_raw_atr14_pct_is_none_when_unusable(df, entry):
    assert ab.raw_atr14_pct(df, entry) is None


def test_raw_atr14_pct_reads_the_last_row_of_the_frame_it_is_given():
    df = _frame(n=61)
    before = ab.raw_atr14_pct(df.iloc[:60], 100.0)
    df.iloc[60, df.columns.get_loc("High")] = 500.0        # the bar after the creating bar
    assert ab.raw_atr14_pct(df.iloc[:60], 100.0) == before
    assert ab.band_for(df.iloc[:60], 100.0, 1.0) == ab.AtrBand(1.0, before)


@pytest.mark.parametrize("price,tick", [(250.0, 0.01), (1.0, 0.01), (0.9999, 0.0001), (0.05, 0.0001)])
def test_tick_size(price, tick):
    assert ab.tick_size(price) == tick


@pytest.mark.parametrize("stop,entry,is_bull,expected", [
    (96.537, 100.0, True, 96.53),            # a long's stop floors
    (103.531, 100.0, False, 103.54),         # a short's stop ceils
    (96.53, 100.0, True, 96.53),             # already on the tick
    (100.0 * (1 - 0.06), 100.0, True, 94.0), # float noise (93.99999999999999) is not a tick
    (0.80756, 0.85, True, 0.8075),           # sub-$1: tick 0.0001
    (0.80751, 0.85, False, 0.8076),
    (0.9690, 1.02, True, 0.96),              # the ENTRY's tick (0.01), not the stop's
])
def test_round_away_from_entry(stop, entry, is_bull, expected):
    assert ab.round_away_from_entry(stop, entry, is_bull) == pytest.approx(expected, abs=1e-12)


# entry 100, a = 4.0, k = 1.0 -> lo 4.0%, hi 8.0%
@pytest.mark.parametrize("level,stop,moved", [
    (99.0, 96.0, "floor"),         # d 1.0 < lo
    (96.0, 96.0, "untouched"),     # d exactly lo
    (94.537, 94.537, "untouched"), # inside: the level itself, never rounded
    (92.0, 92.0, "untouched"),     # d exactly hi
    (90.0, 92.0, "ceiling"),       # d 10.0 > hi
])
def test_band_stop_bullish(level, stop, moved):
    got = ab.band_stop(100.0, level, True, 4.0, 1.0)
    assert got.stop == pytest.approx(stop) and got.moved_by == moved
    assert (got.lo_pct, got.hi_pct) == pytest.approx((4.0, 8.0))
    assert got.distance_pct == pytest.approx(planned_loss_pct(100.0, got.stop))


@pytest.mark.parametrize("level,stop,moved", [
    (101.0, 104.0, "floor"),
    (104.0, 104.0, "untouched"),
    (105.463, 105.463, "untouched"),
    (108.0, 108.0, "untouched"),
    (110.0, 108.0, "ceiling"),
])
def test_band_stop_bearish_mirror(level, stop, moved):
    got = ab.band_stop(100.0, level, False, 4.0, 1.0)
    assert got.stop == pytest.approx(stop) and got.moved_by == moved


def test_a_moved_stop_rounds_away_from_entry_so_the_band_is_never_tighter():
    bull = ab.band_stop(100.0, 99.0, True, 4.123, 0.75)       # lo 3.09225% -> 96.90775
    bear = ab.band_stop(100.0, 101.0, False, 4.123, 0.75)
    assert bull.stop == pytest.approx(96.90) and bull.distance_pct >= bull.lo_pct
    assert bear.stop == pytest.approx(103.10) and bear.distance_pct >= bear.lo_pct
    ceiling = ab.band_stop(100.0, 80.0, True, 4.123, 0.75)     # hi 8.246% -> 91.754
    assert ceiling.stop == pytest.approx(91.75)                # past hi by under one tick
    assert ceiling.hi_pct < ceiling.distance_pct < ceiling.hi_pct + 0.01


def test_a_sub_dollar_floor_stop_uses_the_small_tick():
    got = ab.band_stop(0.85, 0.84, True, 5.0, 1.0)            # lo 5% -> 0.8075
    assert got.stop == pytest.approx(0.8075) and got.moved_by == "floor"


@pytest.mark.parametrize("k", ab.FLOOR_GRID)
def test_lo_is_below_hi_for_every_grid_cell(k):
    got = ab.band_stop(100.0, 99.0, True, 4.0, k)
    assert got.lo_pct < got.hi_pct


def test_a_floor_at_or_past_the_ceiling_multiple_is_refused():
    with pytest.raises(ValueError):
        ab.band_stop(100.0, 99.0, True, 4.0, 2.0)


@pytest.mark.parametrize("entry,level,is_bull,atr_pct,k", [
    (100.0, 99.0, True, 4.0, 0.0),       # floor off
    (100.0, 99.0, True, None, 1.0),      # no ATR
    (100.0, 99.0, True, 0.0, 1.0),
    (0.0, 99.0, True, 4.0, 1.0),
    (100.0, None, True, 4.0, 1.0),
    (100.0, 101.0, True, 4.0, 1.0),      # a long's level above entry
    (100.0, 99.0, False, 4.0, 1.0),      # a short's level below entry
])
def test_band_stop_is_none_when_it_cannot_apply(entry, level, is_bull, atr_pct, k):
    assert ab.band_stop(entry, level, is_bull, atr_pct, k) is None


def test_band_for():
    assert ab.band_for(_frame(), 100.0, 0.0) is None
    assert ab.band_for(_frame(), 100.0, 1.0) == ab.AtrBand(1.0, pytest.approx(4.0))
    assert ab.band_for(_frame(n=10), 100.0, 1.0) == ab.AtrBand(1.0, None)
