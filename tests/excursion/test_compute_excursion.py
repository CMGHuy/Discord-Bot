"""v228 V228-2: compute_excursion -- finest covering frame, entry bar out,
exit bar in, anchors, density, time basis, daily parity."""
from __future__ import annotations

import pandas as pd
import pytest

from swingbot.core.analytics.mfe_mae import (
    BAR_MINUTES, EXCURSION_SOURCES, INTRADAY_SOURCES, coarser_sources,
    compute_excursion, compute_mfe_mae, frame_verdicts, source_rank,
)
from tests.conftest import make_ohlcv

DAY = "2026-11-12"


def _flat(start, end, freq, high=100.5, low=99.5):
    idx = pd.date_range(start, end, freq=freq)
    mid = (high + low) / 2
    return pd.DataFrame({"Open": mid, "High": high, "Low": low, "Close": mid,
                         "Volume": 1000.0}, index=idx)


def _session(freq="5min", start=f"{DAY} 14:30", end=f"{DAY} 20:55"):
    return _flat(start, end, freq)


def _set(df, ts, high=None, low=None):
    if high is not None:
        df.loc[pd.Timestamp(ts), "High"] = high
    if low is not None:
        df.loc[pd.Timestamp(ts), "Low"] = low
    return df


def _trade(**kw):
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 98.0, "exit_price": 101.0,
         "status": "win", "opened_at": f"{DAY}T15:02:00+00:00",
         "closed_at": f"{DAY}T15:31:00+00:00"}
    t.update(kw)
    return t


def _spiky_5min():
    df = _session()
    _set(df, f"{DAY} 15:00", high=110.0, low=90.0)   # holds the fill: pre-fill prices
    _set(df, f"{DAY} 15:30", high=104.0)             # holds the exit: kept
    _set(df, f"{DAY} 15:35", high=120.0, low=80.0)   # after the exit: never read
    return df


def test_constants_and_ranks():
    assert EXCURSION_SOURCES == ("5min", "15min", "hourly", "daily")
    assert INTRADAY_SOURCES == ("5min", "15min", "hourly")
    assert BAR_MINUTES == {"5min": 5, "15min": 15, "hourly": 60}
    assert [source_rank(s) for s in (*EXCURSION_SOURCES, None, "1min")] == [0, 1, 2, 3, 4, 4]
    assert coarser_sources("5min") == ("15min", "hourly", "daily", None)
    assert coarser_sources("15min") == ("hourly", "daily", None)
    assert coarser_sources("daily") == (None,)


def test_entry_bar_is_dropped_and_exit_bar_is_kept():
    m = compute_excursion(_trade(), {"5min": _spiky_5min()})
    assert m == {"mfe_r": 2.0, "mae_r": 0.25, "exit_efficiency": 0.25, "excursion_source": "5min"}


@pytest.mark.parametrize("opened,mfe", [("15:00:00", 5.0), ("15:00:01", 2.0), ("15:01:00", 2.0)])
def test_a_bar_starting_exactly_at_the_fill_is_kept_an_earlier_one_dropped(opened, mfe):
    """The 15:00 bar holds the 110 spike: kept when the fill is at 15:00:00, dropped
    once the bar started before the fill (15:00:01, 15:01)."""
    m = compute_excursion(_trade(opened_at=f"{DAY}T{opened}+00:00"), {"5min": _spiky_5min()})
    assert m["mfe_r"] == mfe


def test_a_trade_inside_one_bar_is_answered_from_its_anchors():
    loss = _trade(opened_at=f"{DAY}T15:31:00+00:00", closed_at=f"{DAY}T15:33:00+00:00",
                  exit_price=99.0, status="loss")
    assert compute_excursion(loss, {"5min": _spiky_5min()}) == {
        "mfe_r": 0.0, "mae_r": 0.5, "exit_efficiency": None, "excursion_source": "5min"}
    win = dict(loss, exit_price=101.2, status="win")
    m = compute_excursion(win, {"5min": _spiky_5min()})
    assert (m["mfe_r"], m["mae_r"], m["exit_efficiency"]) == (0.6, 0.0, 1.0)


def test_anchors_lift_an_excursion_the_bars_understate():
    m = compute_excursion(_trade(exit_price=103.0), {"5min": _session()})
    assert m["mfe_r"] == 1.5 and m["mae_r"] == 0.25


def test_bearish_trades_mirror_every_rule():
    df = _session()
    _set(df, f"{DAY} 15:00", high=110.0, low=90.0)
    _set(df, f"{DAY} 15:30", low=96.0)
    t = _trade(direction="bearish", entry=100.0, stop_loss=102.0, exit_price=99.0)
    m = compute_excursion(t, {"5min": df})
    assert (m["mfe_r"], m["mae_r"], m["exit_efficiency"]) == (2.0, 0.25, 0.25)


def test_coverage_failure_falls_through_each_rung():
    late_5 = _flat(f"{DAY} 15:10", f"{DAY} 20:55", "5min")          # starts after the fill
    short_15 = _flat(f"{DAY} 14:30", f"{DAY} 15:00", "15min")       # ends before the exit
    hourly = _flat(f"{DAY} 14:30", f"{DAY} 20:30", "60min")
    daily = make_ohlcv([100.0], spread_pct=1.0, start=DAY)
    frames = {"5min": late_5, "15min": short_15, "hourly": hourly, "daily": daily}
    assert frame_verdicts(_trade(), frames) == {
        "5min": "coverage", "15min": "coverage", "hourly": "ok", "daily": "ok"}
    assert compute_excursion(_trade(), frames)["excursion_source"] == "hourly"
    frames["hourly"] = None
    assert compute_excursion(_trade(), frames)["excursion_source"] == "daily"



def test_a_hole_inside_the_hold_skips_the_frame():
    holed = _session().drop(pd.date_range(f"{DAY} 15:05", f"{DAY} 15:20", freq="5min"))
    frames = {"5min": holed, "15min": _session("15min", end=f"{DAY} 20:45")}
    assert frame_verdicts(_trade(), frames)["5min"] == "density"
    assert compute_excursion(_trade(), frames)["excursion_source"] == "15min"


def test_a_gap_of_exactly_four_bars_is_dense_enough():
    gap = _session().drop(pd.date_range(f"{DAY} 15:05", f"{DAY} 15:15", freq="5min"))  # 15:00 -> 15:20
    assert frame_verdicts(_trade(), {"5min": gap}) == {"5min": "ok"}



def test_time_basis_aware_index_and_offset_trade_times_match_naive_utc():
    naive = compute_excursion(_trade(), {"5min": _spiky_5min()})
    aware = _spiky_5min().tz_localize("UTC")
    assert compute_excursion(_trade(), {"5min": aware}) == naive
    new_york = _trade(opened_at=f"{DAY}T10:02:00-05:00", closed_at=f"{DAY}T10:31:00-05:00")
    assert compute_excursion(new_york, {"5min": _spiky_5min()}) == naive


def test_last_bar_tolerance_is_one_bar_length():
    df = _flat(f"{DAY} 14:30", f"{DAY} 15:25", "5min")  # last start 15:25 vs close 15:31
    assert frame_verdicts(_trade(), {"5min": df}) == {"5min": "coverage"}
    df = _flat(f"{DAY} 14:30", f"{DAY} 15:26", "1min").resample("5min").last()  # last start 15:25
    assert frame_verdicts(_trade(closed_at=f"{DAY}T15:30:00+00:00"), {"5min": df}) == {"5min": "ok"}


def test_the_overnight_gap_between_sessions_is_not_a_hole():
    two_days = pd.concat([_session(), _session(start="2026-11-13 14:30", end="2026-11-13 20:55")])
    t = _trade(closed_at="2026-11-13T15:31:00+00:00")
    assert frame_verdicts(t, {"5min": two_days}) == {"5min": "ok"}


def test_mapping_order_does_not_matter_and_unknown_frames_are_skipped():
    daily = make_ohlcv([100.0], spread_pct=1.0, start=DAY)
    frames = {"1min": _session("1min"), "daily": daily, "5min": _spiky_5min()}
    assert compute_excursion(_trade(), frames)["excursion_source"] == "5min"
    assert frame_verdicts(_trade(), frames) == {"5min": "ok", "daily": "ok", "1min": "unsupported"}


def test_daily_keeps_todays_arithmetic_without_anchors():
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    assert compute_excursion(t, {"daily": df}) == {
        "mfe_r": 2.0, "mae_r": 0.5, "exit_efficiency": 0.5, "excursion_source": "daily"}
    beyond = make_ohlcv([100, 101], spread_pct=0.0, start="2026-03-02")
    t2 = dict(t, closed_at="2026-03-03T15:00:00+00:00")
    assert compute_excursion(t2, {"daily": beyond})["mfe_r"] == 0.25   # exit 104 is NOT an anchor


def test_compute_mfe_mae_is_the_daily_wrapper():
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00"}
    assert compute_mfe_mae(t, df) == {"mfe_r": 2.0, "mae_r": 0.5, "exit_efficiency": 0.5}
    assert compute_mfe_mae(t, None) is None
    outside = dict(t, opened_at="2027-01-04T15:00:00+00:00", closed_at="2027-01-05T15:00:00+00:00")
    assert compute_mfe_mae(outside, df) is None


@pytest.mark.parametrize("frames", [{}, {"5min": None, "daily": None},
                                    {"5min": pd.DataFrame(), "daily": pd.DataFrame()}])
def test_no_bars_at_all_gives_no_answer(frames):
    assert compute_excursion(_trade(), frames) is None


def test_an_empty_finer_frame_falls_to_the_next():
    frames = {"5min": pd.DataFrame(), "15min": _session("15min", end=f"{DAY} 20:45")}
    assert frame_verdicts(_trade(), frames)["5min"] == "empty"
    assert compute_excursion(_trade(), frames)["excursion_source"] == "15min"


@pytest.mark.parametrize("bad", [{"stop_loss": 100.0}, {"stop_loss": None}, {"entry": None},
                                 {"opened_at": None}, {"closed_at": "not a date"}])
def test_unusable_trades_give_none_and_no_verdicts(bad):
    t = _trade(**bad)
    assert compute_excursion(t, {"5min": _session()}) is None
    assert frame_verdicts(t, {"5min": _session()}) == {}


def test_rounding_and_efficiency_clamp():
    df = _session()
    _set(df, f"{DAY} 15:10", high=101.0)
    m = compute_excursion(_trade(stop_loss=97.0, exit_price=100.0), {"5min": df})
    assert m["mfe_r"] == 0.3333 and m["mae_r"] == 0.1667 and m["exit_efficiency"] == 0.0
    clamp = compute_excursion(_trade(exit_price=96.0, status="loss"), {"5min": _session()})
    assert clamp["mfe_r"] == 0.25 and clamp["mae_r"] == 2.0 and clamp["exit_efficiency"] == -5.0
