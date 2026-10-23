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
