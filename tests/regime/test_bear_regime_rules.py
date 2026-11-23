"""v239 V239-2: the bear-regime rules on hand-built series whose SMAs are easy
to check by hand. Each series is 260 piecewise-flat bars ending at S, so
SMA200[s] = mean(bars 60..259), SMA200[s-20] = mean(40..239),
SMA50[s] = mean(210..259) and SMA50[s-5] = mean(205..254)."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import bear_regime as br

S = date(2026, 10, 21)          # s, a Wednesday
D = date(2026, 10, 22)          # the session the label is for
NEXT = pd.Timestamp("2026-10-22")

# SMA200 164 (rising from 155), SMA50 196 (falling from 198), C 180.
CORRECTION = [(60, 100), (140, 150), (50, 200), (10, 180)]
# as CORRECTION, but bar s-1 closes 176 (high 177) and C[s] = 180 > H[s-1].
CORRECTION_UP_DAY = [(60, 100), (140, 150), (50, 200), (8, 180), (1, 176), (1, 180)]
# C 170 under SMA200 187 (rising from 177), SMA50 218 above it, falling from 224.
CORRECTION_UNDER_SMA200 = [(60, 100), (100, 150), (90, 230), (10, 170)]
# SMA50 100 < SMA200 175 (still rising from 170), C 100: BEAR by the cross.
BEAR_CROSS = [(60, 50), (150, 200), (50, 100)]
# SMA200 124.55 falling from 135, SMA50 198.2 above it, C 110: BEAR by the slope.
BEAR_SLOPE = [(60, 300), (150, 100), (49, 200), (1, 110)]
# meets every CORRECTION condition and the BEAR cross: BEAR wins.
BEAR_AND_CORRECTION = [(60, 50), (150, 200), (45, 100), (5, 90)]
# CORRECTION's tail, but SMA200 falls (175 -> 164) and C 180 > SMA200: NORMAL.
FALLING_SMA200 = [(60, 300), (140, 150), (50, 200), (10, 180)]
# C 199 above SMA50 196.38: NORMAL.
ABOVE_FAST = [(60, 100), (140, 150), (50, 200), (9, 180), (1, 199)]
# C 175 under SMA50 177.3, but SMA50 rose from 170: NORMAL.
RISING_FAST = [(60, 100), (140, 150), (55, 170), (4, 260), (1, 175)]


def _spy(segments=None, *, closes=None, end=S, tz=None) -> pd.DataFrame:
    if closes is None:
        closes = np.concatenate([np.full(n, float(v)) for n, v in segments])
    closes = np.asarray(closes, dtype=float)
    index = pd.bdate_range(end=pd.Timestamp(end), periods=len(closes), name="Date", tz=tz)
    return pd.DataFrame({"High": closes + 1.0, "Close": closes}, index=index)


def _rising(n=260) -> pd.DataFrame:
    return _spy(closes=np.linspace(100.0, 200.0, n))


def _vix(spy, tail=(), base=15.0) -> pd.DataFrame:
    values = np.full(len(spy), base)
    if tail:
        values[-len(tail):] = tail
    return pd.DataFrame({"Close": values}, index=spy.index)


def _classify(spy, vix=None, **kw):
    return br.classify(spy, vix, last_session=kw.pop("last_session", S),
                       session_date=kw.pop("session_date", D), **kw)


def _with_bar_after_s(frame, value):
    extra = pd.DataFrame({c: [value] for c in frame.columns},
                         index=pd.DatetimeIndex([NEXT], name="Date"))
    return pd.concat([frame, extra])


def test_frozen_constants():
    assert (br.MIN_BARS, br.SMA_FAST, br.SMA_SLOW) == (220, 50, 200)
    assert (br.SLOW_SLOPE_LAG, br.FAST_SLOPE_LAG) == (20, 5)
    assert (br.STRESS_VIX, br.PULLBACK_VIX_RATIO, br.PULLBACK_VIX_WINDOW) == (25.0, 0.85, 5)
    assert br.STATES == ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
    assert (br.SPY, br.VIX, br.VIX_GAP) == ("SPY", "^VIX", "vix_gap")
    assert (br.WOULD_VETO, br.CAUTION, br.PULLBACK_WATCH, br.ALIGNED, br.NONE) == (
        "would_veto", "caution", "pullback_watch", "aligned", "none")


@pytest.mark.parametrize("segments, state", [
    (CORRECTION, br.CORRECTION),
    (CORRECTION_UP_DAY, br.CORRECTION),
    (CORRECTION_UNDER_SMA200, br.CORRECTION),
    (BEAR_CROSS, br.BEAR),
    (BEAR_SLOPE, br.BEAR),
    (BEAR_AND_CORRECTION, br.BEAR),
    (FALLING_SMA200, br.NORMAL),
    (ABOVE_FAST, br.NORMAL),
    (RISING_FAST, br.NORMAL),
])
def test_state_rules(segments, state):
    day = _classify(_spy(segments))
    assert day.state == state and day.unknown_reason is None


def test_a_steady_uptrend_is_normal():
    assert _classify(_rising()).state == br.NORMAL


def test_numbers_are_the_hand_computed_smas():
    day = _classify(_spy(CORRECTION))
    assert day.spy_close == 180.0 and day.spy_high_prev == 181.0
    assert day.sma200 == pytest.approx(164.0) and day.sma200_lag20 == pytest.approx(155.0)
    assert day.sma50 == pytest.approx(196.0) and day.sma50_lag5 == pytest.approx(198.0)
    assert (day.session_date, day.last_bar_date) == (D, S)
    cross = _classify(_spy(BEAR_CROSS))
    assert (cross.sma200, cross.sma200_lag20, cross.sma50) == pytest.approx((175.0, 170.0, 100.0))


def test_no_lookahead_a_bar_after_s_never_changes_the_label():
    spy = _spy(CORRECTION)
    assert _classify(_with_bar_after_s(spy, 1.0)) == _classify(spy)


def test_a_frame_ending_in_a_partial_bar_equals_the_hand_cut_frame():
    partial = _with_bar_after_s(_spy(CORRECTION), 150.0)      # today's forming bar, dated D
    assert _classify(partial) == _classify(partial.iloc[:-1])


def test_a_tz_aware_index_reads_the_wall_date():
    assert _classify(_spy(CORRECTION, tz="UTC")) == _classify(_spy(CORRECTION))


def test_short_history_is_unknown():
    day = _classify(_rising(219))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_SHORT)
    assert _classify(_rising(220)).state == br.NORMAL


@pytest.mark.parametrize("column, pos, value", [
    ("Close", -1, np.nan), ("Close", -100, np.nan), ("Close", -220, np.nan),
    ("High", -2, np.nan), ("Close", -5, np.inf)])
def test_a_non_finite_input_is_unknown(column, pos, value):
    spy = _rising()
    spy.iloc[pos, spy.columns.get_loc(column)] = value
    day = _classify(spy)
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_NAN)


def test_a_nan_outside_the_window_is_ignored():
    spy = _rising()
    spy.iloc[-221, spy.columns.get_loc("Close")] = np.nan
    assert _classify(spy).state == br.NORMAL


def test_a_stale_spy_frame_is_unknown_and_says_which_bar_it_saw():
    day = _classify(_spy(CORRECTION), last_session=date(2026, 10, 22),
                    session_date=date(2026, 10, 23))
    assert (day.state, day.unknown_reason, day.last_bar_date) == (br.UNKNOWN, br.REASON_STALE, S)


@pytest.mark.parametrize("spy", [None, pd.DataFrame({"High": [], "Close": []})])
def test_no_spy_frame_is_stale(spy):
    day = _classify(spy)
    assert (day.state, day.unknown_reason, day.last_bar_date) == (br.UNKNOWN, br.REASON_STALE, None)


def test_an_unknown_day_carries_no_numbers_but_keeps_the_providers():
    spy = _rising(219)
    day = _classify(spy, _vix(spy, tail=(40.0,)), spy_provider="alpaca", vix_provider="yfinance")
    assert day.stress is None and day.pullback_trigger is False
    assert all(getattr(day, f) is None for f in ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
                                                          "spy_high_prev", "vix_close", "vix_max5"))
    assert (day.spy_provider, day.vix_provider) == ("alpaca", "yfinance")


def test_row_round_trip_and_columns():
    day = _classify(_spy(CORRECTION), spy_provider="alpaca", vix_provider="yfinance")
    row = day.to_row()
    assert set(row) == set(br.ROW_COLUMNS) | {"doc"}
    assert "unknown_reason" not in br.ROW_COLUMNS and "computed_at" not in row
    assert row["doc"] == {"unknown_reason": None}
    assert br.RegimeDay.from_row(row) == day


def test_from_row_accepts_iso_dates_decimals_and_extra_keys():
    day = _classify(_rising(219))
    row = {**day.to_row(), "session_date": "2026-10-22", "last_bar_date": datetime(2026, 10, 21),
           "computed_at": "2026-10-22T13:00:00+00:00", "updated_at": None}
    assert br.RegimeDay.from_row(row) == day
    assert br.RegimeDay.from_row(row).unknown_reason == br.REASON_SHORT
    full = _classify(_spy(CORRECTION)).to_row()
    full["sma200"] = Decimal("164.0")
    assert br.RegimeDay.from_row(full).sma200 == 164.0


def test_regime_day_is_frozen():
    day = _classify(_spy(CORRECTION))
    with pytest.raises(FrozenInstanceError):
        day.state = br.BEAR  # type: ignore[misc]
    assert replace(day, state=br.BEAR).state == br.BEAR


@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "America/New_York"])
def test_non_utc_indexes_keep_the_bars_wall_dates(tz):
    assert _classify(_spy(CORRECTION, tz=tz)) == _classify(_spy(CORRECTION))


def test_future_only_frame_is_stale_without_a_last_bar():
    day = _classify(_spy(closes=[180.0], end=D))
    assert (day.state, day.unknown_reason, day.last_bar_date) == (
        br.UNKNOWN, br.REASON_STALE, None)


@pytest.mark.parametrize("stale, reason", [(True, "stale"), (False, "short_history")])
def test_unknown_precedence_over_non_finite_short_history(stale, reason):
    spy = _rising(219)
    spy.iloc[-1, spy.columns.get_loc("Close")] = np.nan
    day = _classify(spy, last_session=D if stale else S)
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, reason)


def test_flat_smas_are_normal_at_the_strict_boundaries():
    day = _classify(_spy(closes=np.full(220, 100.0)))
    assert day.state == br.NORMAL
    assert (day.spy_close, day.sma50, day.sma200,
            day.sma50_lag5, day.sma200_lag20) == (100.0,) * 5


def test_row_column_order_is_the_persistence_contract():
    assert br.ROW_COLUMNS == (
        "session_date", "last_bar_date", "state", "stress", "pullback_trigger",
        "pullback_reason", "spy_close", "sma50", "sma200", "sma50_lag5",
        "sma200_lag20", "spy_high_prev", "vix_close", "vix_max5", "spy_provider",
        "vix_provider")
    row = _classify(_spy(CORRECTION)).to_row()
    assert type(row["session_date"]) is date
    assert type(row["last_bar_date"]) is date
    assert type(row["sma200"]) is float
