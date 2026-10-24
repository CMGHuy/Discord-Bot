"""v182 descriptive maths: depth summary and check 5 (outcome-blind, never reads R)."""
from swingbot.core.backtesting.screen import descriptive


def test_the_check_5_limits_are_the_spec_values():
    assert descriptive.DEPTH_MEDIAN_TOL == 0.05
    assert descriptive.NULL_UNFILLED_MAX == 0.20


def test_depth_summary_gives_quartiles_median_and_the_gap_fill_share():
    assert descriptive.depth_summary([0.0, 0.0, 0.5, 1.0, 2.0]) == {
        "n": 5, "q1": 0.0, "median": 0.5, "q3": 1.0, "gap_share": 0.4}


def test_depth_summary_of_nothing_is_empty():
    assert descriptive.depth_summary([]) == {
        "n": 0, "q1": None, "median": None, "q3": None, "gap_share": None}


def test_check_5_passes_inside_both_limits_and_at_the_unfilled_limit():
    # medians 0.25 vs 0.2734375 (|d| = 0.0234375); 20 of 100 unfilled = 20 %
    ok, lines = descriptive.check_fill_depth(
        [0.0, 0.25, 0.5], [0.0, 0.25, 0.296875, 0.5], null_slots=100, null_unfilled=20)
    assert ok is True
    assert lines == [
        "median depth: events 0.250 ATR, null 0.273 ATR, |difference| 0.023 <= 0.05 -> pass",
        "null_unfilled: 20 of 100 null slots (20.0%) <= 20% -> pass"]


def test_check_5_fails_on_a_median_gap_above_the_tolerance():
    ok, lines = descriptive.check_fill_depth([0.25], [0.3125], null_slots=10, null_unfilled=0)
    assert ok is False
    assert lines[0] == ("median depth: events 0.250 ATR, null 0.312 ATR, "
                        "|difference| 0.062 > 0.05 -> FAIL")
    assert lines[1].endswith("-> pass")


def test_check_5_fails_when_more_than_a_fifth_of_null_slots_go_unfilled():
    ok, lines = descriptive.check_fill_depth([0.25], [0.25], null_slots=100, null_unfilled=21)
    assert ok is False
    assert lines[1] == "null_unfilled: 21 of 100 null slots (21.0%) > 20% -> FAIL"


def test_check_5_fails_with_no_event_depth_no_null_fill_or_no_slots():
    assert descriptive.check_fill_depth([], [0.1], 10, 0) == (
        False, ["median depth: no event depths -> FAIL",
                "null_unfilled: 0 of 10 null slots (0.0%) <= 20% -> pass"])
    ok, lines = descriptive.check_fill_depth([0.1], [], 10, 10)
    assert ok is False and lines[0] == "median depth: no filled null -> FAIL"
    ok, lines = descriptive.check_fill_depth([0.1], [0.1], 0, 0)
    assert ok is False and lines[1] == "null_unfilled: no null slots -> FAIL"


# --- v182 V182-17: results-doc blocks (descriptive, never gating) ------------
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from tests.backtesting.screen.helpers import frame  # noqa: E402


def test_event_overlap_counts_each_side_and_the_shared_bars():
    own = np.array([True, True, False, False, True])
    other = np.array([True, False, True, False, True])
    assert descriptive.event_overlap(own, other) == {"own": 3, "other": 3, "both": 2}


def test_event_overlap_of_a_nested_pair_shares_every_inner_bar():
    own = np.array([True, False, True, False])
    other = np.array([True, True, True, False])
    assert descriptive.event_overlap(own, other) == {"own": 2, "other": 3, "both": 2}


def test_event_overlap_refuses_unequal_lengths():
    with pytest.raises(ValueError):
        descriptive.event_overlap(np.ones(3, dtype=bool), np.ones(4, dtype=bool))


def test_spy_above_200_starts_where_the_average_exists():
    assert descriptive.SPY_SMA == 200
    spy = frame([100.0] * 200 + [101.0, 99.0, 100.0])
    above = descriptive.spy_above_200(spy)
    # SMA200 at bars 199..202: 100, 100.005, 100, 100 (integer sums, exact)
    assert above.index.equals(spy.index[199:])
    assert above.tolist() == [False, True, False, False]


def _r(day, r_event, r_null):
    return {"entry_date": day, "r_event": r_event, "r_null": r_null}


def test_paired_delta_is_the_mean_event_minus_null():
    assert descriptive.paired_delta([_r("2015-01-06", 1.0, 0.5), _r("2015-01-07", -1.0, 0.0)]) \
        == (2, -0.25)
    assert descriptive.paired_delta([]) == (0, None)


def test_regime_split_reads_the_last_spy_close_before_entry():
    above = pd.Series([True, False, True],
                      index=pd.to_datetime(["2015-01-05", "2015-01-06", "2015-01-07"]))
    rows = [_r("2015-01-06", 1.0, 0.5),     # last close before: 01-05, above
            _r("2015-01-10", 0.0, 0.25),    # a Saturday: 01-07, above
            _r("2015-01-07", -1.0, 0.0),    # 01-06, below (never the entry day's own close)
            _r("2015-01-05", 2.0, 0.0)]     # no SPY close before: unknown
    assert descriptive.regime_split(rows, above) == {
        "above": (2, 0.125), "below": (1, -1.0), "unknown": 1}


def test_regime_split_of_no_events():
    above = pd.Series([True], index=pd.to_datetime(["2015-01-05"]))
    assert descriptive.regime_split([], above) == {
        "above": (0, None), "below": (0, None), "unknown": 0}
