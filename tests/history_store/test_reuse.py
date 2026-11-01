"""v190 section 2.3: the reused-symbol break test (the MON case), the
series-start/end gaps against membership and the yfinance reference, and
the kept side, which follows the membership spans -- never the break."""
import numpy as np
import pandas as pd
import pytest

from alpaca_history import reuse, store_io

SESSIONS = pd.bdate_range("2016-01-04", "2019-12-31")


def _series(n=600, start="2016-01-04", close=100.0, volume=1e6) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": volume}, index=idx, dtype=float)


def _shift(frame, at: int, *, close=None, volume=None) -> pd.DataFrame:
    """From bar `at` on, the close and/or volume take a new level."""
    out = frame.copy()
    if close is not None:
        out.iloc[at:, out.columns.get_loc("Close")] = close
    if volume is not None:
        out.iloc[at:, out.columns.get_loc("Volume")] = volume
    return out


def _date(frame, i) -> str:
    return frame.index[i].strftime("%Y-%m-%d")


def test_frozen_thresholds():
    t = reuse.THRESHOLDS
    assert (t.break_move, t.break_ratio, t.revert_sessions, t.gap_sessions, t.edge_sessions) == (
        0.50, 10.0, 20, 20, 20)
    assert reuse.MEDIAN_WINDOW == 50
    assert reuse.Thresholds() == reuse.THRESHOLDS


# --- find_breaks ------------------------------------------------------------------------

def test_an_issuer_change_is_a_break():
    """MON: a $100 name trading 1M shares a day becomes an $8 name trading 20k."""
    frame = _shift(_series(), 400, close=8.0, volume=2e4)
    assert reuse.find_breaks(frame) == [reuse.Break(_date(frame, 400), "price+volume")]


def test_volume_alone_or_price_alone_is_enough():
    vol = _shift(_series(), 300, close=45.0, volume=5e4)      # -55%, 20x less volume
    assert reuse.find_breaks(vol) == [reuse.Break(_date(vol, 300), "volume")]
    price = _shift(_series(), 300, close=1000.0)              # 10x the level, same volume
    assert reuse.find_breaks(price) == [reuse.Break(_date(price, 300), "price")]


def test_a_one_bar_spike_reverts_and_is_not_a_break():
    frame = _series()
    frame.iloc[300, frame.columns.get_loc("Close")] = 300.0
    assert reuse.find_breaks(frame) == []
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 0)) == []


def test_a_large_move_without_a_level_shift_is_not_a_break():
    frame = _shift(_series(), 300, close=40.0)                # -60%, price ratio 2.5, same volume
    assert reuse.find_breaks(frame) == []


def test_on_a_flagged_stretch_the_move_alone_counts():
    """Reuse by an issuer of similar size: no 10x shift, so only the stretch scan sees it."""
    frame = _shift(_series(), 300, close=40.0)
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 250)) == [
        reuse.Break(_date(frame, 300), "move")]
    assert reuse.find_breaks(frame, sessions_from=_date(frame, 301)) == []


def test_moves_of_at_most_fifty_percent_are_never_candidates():
    crash = _shift(_series(), 300, close=55.0, volume=2e4)    # -45%, persistent, 50x less volume
    assert reuse.find_breaks(crash) == []
    raw_forward_split = _shift(_series(), 300, close=50.0, volume=2e6)   # exactly -50%
    assert reuse.find_breaks(raw_forward_split, sessions_from=_date(raw_forward_split, 0)) == []


def test_splits_are_adjusted_away_by_the_store():
    """A split never reaches the detector as a jump: the store is fetched with Adjustment.ALL."""
    assert store_io.ADJUSTMENT == "all"
    adjusted = _series()
    adjusted["Close"] = np.linspace(50.0, 60.0, len(adjusted))
    assert reuse.find_breaks(adjusted) == []


def test_breaks_near_either_end_are_edge_breaks():
    early = _shift(_series(), 5, close=8.0, volume=2e4)
    assert reuse.find_breaks(early) == [reuse.Break(_date(early, 5), "edge")]
    late = _shift(_series(), 590, close=8.0, volume=2e4)
    assert reuse.find_breaks(late) == [reuse.Break(_date(late, 590), "edge")]


def test_degenerate_frames_have_no_break():
    assert reuse.find_breaks(None) == []
    assert reuse.find_breaks(_series(n=0)) == []
    assert reuse.find_breaks(_series(n=1)) == []
    frame = _series()
    frame.iloc[300, frame.columns.get_loc("Close")] = np.nan
    assert reuse.find_breaks(frame) == []


# --- series_gaps ------------------------------------------------------------------------

def test_series_running_past_membership_and_reference_are_flagged():
    frame = _series(n=len(SESSIONS))                         # 2016-01-04 .. 2019-12-31
    gaps = reuse.series_gaps(frame, [("2017-01-03", "2018-06-08")], "2018-06-07", SESSIONS)
    assert [g["kind"] for g in gaps] == ["start", "end", "reference-end"]
    start, end, ref = gaps
    assert (start["from"], start["to"]) == ("2016-01-04", "2017-01-03")
    assert start["sessions"] == len(SESSIONS[SESSIONS < "2017-01-03"])
    assert (end["from"], end["to"]) == ("2018-06-08", "2020-01-01")
    assert (ref["from"], ref["to"]) == ("2018-06-08", "2020-01-01")


def test_the_gap_threshold_is_more_than_twenty_sessions():
    span_start = SESSIONS[100].strftime("%Y-%m-%d")
    twenty = _series(n=400, start=SESSIONS[80].strftime("%Y-%m-%d"))
    assert reuse.series_gaps(twenty, [(span_start, "9999-12-31")], None, SESSIONS) == []
    twenty_one = _series(n=400, start=SESSIONS[79].strftime("%Y-%m-%d"))
    assert [g["sessions"] for g in reuse.series_gaps(
        twenty_one, [(span_start, "9999-12-31")], None, SESSIONS)] == [21]


def test_no_gap_for_an_open_span_or_without_spans():
    frame = _series(n=len(SESSIONS))
    assert reuse.series_gaps(frame, [("2016-01-04", "9999-12-31")], None, SESSIONS) == []
    assert reuse.series_gaps(frame, [], None, SESSIONS) == []
    assert reuse.series_gaps(None, [("2016-01-04", "9999-12-31")], "2017-01-03", SESSIONS) == []


# --- resolve: the kept side follows the spans --------------------------------------------

MON_SPANS = [("2010-01-04", "2018-06-08")]


def test_a_break_after_the_last_membership_end_keeps_the_bars_before_it():
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2018-09-04", "price+volume")], MON_SPANS, frame)
    assert got == {"trim": {"keep_from": None, "keep_before": "2018-09-04",
                            "reason": "break after last membership end"},
                   "breaks": [{"date": "2018-09-04", "kind": "price+volume", "resolution": "trim_after"}]}


def test_a_break_before_the_first_membership_start_keeps_the_bars_after_it():
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2016-06-01", "volume")], [("2017-01-03", "9999-12-31")], frame)
    assert got["trim"] == {"keep_from": "2016-06-01", "keep_before": None,
                           "reason": "break before first membership start"}
    assert got["breaks"][0]["resolution"] == "trim_before"


def test_a_break_inside_or_between_spans_is_left_for_the_builder():
    frame = _series(n=len(SESSIONS))
    for spans in (MON_SPANS, [("2010-01-04", "2017-01-03"), ("2017-06-01", "2018-06-08")]):
        got = reuse.resolve([reuse.Break("2017-03-01", "price")], spans, frame)
        assert got["trim"] is None and got["breaks"][0]["resolution"] == "in_span"


def test_edge_breaks_resolve_by_side_or_stay_unresolved():
    frame = _series(n=len(SESSIONS))
    last = frame.index[-3].strftime("%Y-%m-%d")
    after = reuse.resolve([reuse.Break(last, "edge")], MON_SPANS, frame)
    assert after["breaks"][0]["resolution"] == "trim_after" and after["trim"]["keep_before"] == last
    inside = reuse.resolve([reuse.Break(last, "edge")], [("2010-01-04", "9999-12-31")], frame)
    assert inside["trim"] is None and inside["breaks"][0]["resolution"] == "unresolved"


def test_several_breaks_keep_the_innermost_bars():
    frame = _series(n=len(SESSIONS))
    breaks = [reuse.Break("2019-03-01", "price"), reuse.Break("2016-03-01", "volume"),
              reuse.Break("2018-09-04", "price"), reuse.Break("2016-09-01", "price")]
    got = reuse.resolve(breaks, [("2017-01-03", "2018-06-08")], frame)
    assert got["trim"] == {"keep_from": "2016-09-01", "keep_before": "2018-09-04",
                           "reason": "break before first membership start; break after last membership end"}
    assert [b["date"] for b in got["breaks"]] == ["2016-03-01", "2016-09-01", "2018-09-04", "2019-03-01"]


def test_without_spans_every_break_needs_the_builder():
    """A context symbol (SPY, an ETF) has no membership: no side can be kept automatically."""
    frame = _series(n=len(SESSIONS))
    got = reuse.resolve([reuse.Break("2017-03-01", "price"),
                         reuse.Break(frame.index[-2].strftime("%Y-%m-%d"), "edge")], [], frame)
    assert got["trim"] is None
    assert [b["resolution"] for b in got["breaks"]] == ["in_span", "unresolved"]


def test_no_break_no_trim():
    assert reuse.resolve([], MON_SPANS, _series()) == {"trim": None, "breaks": []}
