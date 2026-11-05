"""v190 section 2.1: coverage cuts at date level, never a span-level verdict.
A run of more than 5 missing sessions is cut; a signal date needs 95% of its
trailing 60 sessions present -- decided from bars on or before the date, so
a delisted name's ragged tail never removes its earlier history."""
import pandas as pd
import pytest

from alpaca_history import pit_coverage as pc

SESSIONS = pd.bdate_range("2017-01-02", "2017-12-29")     # the fixture calendar
SPAN = ("2017-01-02", "2018-01-01")


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _without(*ranges) -> pd.DatetimeIndex:
    """SESSIONS minus the inclusive date ranges given."""
    keep = SESSIONS
    for start, end in ranges:
        keep = keep[(keep < pd.Timestamp(start)) | (keep > pd.Timestamp(end))]
    return keep


def _days(runs) -> set[str]:
    """Every calendar session inside the (start, end_excl, ...) runs."""
    out = set()
    for run in runs:
        inside = SESSIONS[(SESSIONS >= pd.Timestamp(run[0])) & (SESSIONS < pd.Timestamp(run[1]))]
        out |= {_iso(d) for d in inside}
    return out


def test_frozen_values():
    assert (pc.STORE_START, pc.STORE_END, pc.STORE_END_EXCL) == ("2016-01-04", "2025-12-31", "2026-01-01")
    assert (pc.MAX_MISSING_RUN, pc.TRAILING_SESSIONS, pc.MIN_TRAILING_SHARE) == (5, 60, 0.95)
    assert pc.RUN_REASON.format(n=9) == "missing run of 9 sessions"
    assert pc.TRAILING_REASON == "trailing 60-session coverage under 95%"


# --- the calendar and the window --------------------------------------------------------

def test_expected_sessions_are_spys_dates_inside_the_store_window():
    idx = pd.date_range("2015-12-28", "2026-01-09", freq="B")
    spy = pd.DataFrame({"Close": 1.0}, index=idx)
    got = pc.expected_sessions(spy)
    assert got.min() == pd.Timestamp("2016-01-04") and got.max() == pd.Timestamp("2025-12-31")
    stamped = pd.DataFrame({"Close": 1.0}, index=pd.DatetimeIndex(
        ["2016-01-05 16:00", "2016-01-04 16:00", "2016-01-05 16:00"]))
    assert list(pc.expected_sessions(stamped)) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]


@pytest.mark.parametrize("spy", [None, pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([])),
                                 pd.DataFrame({"Close": 1.0}, index=pd.bdate_range("2014-01-02", "2015-12-31"))])
def test_no_spy_calendar_is_refused(spy):
    with pytest.raises(ValueError, match="SPY"):
        pc.expected_sessions(spy)


def test_clip_span():
    assert pc.clip_span(("2010-01-01", "9999-12-31")) == ("2016-01-04", "2026-01-01")
    assert pc.clip_span(("2018-03-01", "2019-01-02")) == ("2018-03-01", "2019-01-02")
    assert pc.clip_span(("2012-01-03", "2015-06-01")) is None
    assert pc.clip_span(("2026-02-02", "9999-12-31")) is None


# --- missing runs -----------------------------------------------------------------------

def test_every_missing_run_is_listed_with_its_length():
    bars = _without(("2017-03-01", "2017-03-13"), ("2017-04-03", "2017-04-04"))
    assert pc.missing_runs(bars, SESSIONS, SPAN) == [
        ("2017-03-01", "2017-03-14", 9), ("2017-04-03", "2017-04-05", 2)]


def test_a_run_reaching_the_span_end_ends_at_the_span_end():
    bars = _without(("2017-06-16", "2017-12-29"))
    span = ("2017-01-02", "2017-07-01")
    runs = pc.missing_runs(bars, SESSIONS, span)
    assert runs[-1][:2] == ("2017-06-16", "2017-07-01")
    assert runs[-1][2] == len(SESSIONS[(SESSIONS >= "2017-06-16") & (SESSIONS < "2017-07-01")])


def test_missing_runs_ignore_sessions_outside_the_span():
    bars = _without(("2017-01-02", "2017-02-28"))
    assert pc.missing_runs(bars, SESSIONS, ("2017-03-01", "2018-01-01")) == []


# --- the trailing-60 rule ---------------------------------------------------------------

def test_three_missing_sessions_in_sixty_pass():
    bars = _without(("2017-06-01", "2017-06-05"))           # Thu, Fri, Mon: 3 sessions
    assert pc.trailing_failures(bars, SESSIONS, SPAN) == []


def test_four_missing_fail_until_the_first_leaves_the_window():
    bars = _without(("2017-06-01", "2017-06-06"))           # 4 sessions
    m = SESSIONS.get_loc(pd.Timestamp("2017-06-01"))
    assert pc.trailing_failures(bars, SESSIONS, SPAN) == [(_iso(SESSIONS[m + 3]), _iso(SESSIONS[m + 60]))]


def test_a_short_window_at_the_calendar_start_is_judged_on_what_exists():
    assert pc.trailing_failures(SESSIONS, SESSIONS, SPAN) == []
    first_missing = SESSIONS[1:]                            # 1 of the first 2 sessions missing
    assert pc.trailing_failures(first_missing, SESSIONS, SPAN)[0][0] == "2017-01-02"


def test_the_verdict_on_a_date_never_reads_a_later_bar():
    """Causality: dropping every bar after d leaves the verdict on dates <= d unchanged."""
    bars = _without(("2017-03-06", "2017-03-08"), ("2017-05-01", "2017-05-12"), ("2017-09-11", "2017-09-12"))
    full = _days(pc.trailing_failures(bars, SESSIONS, SPAN))
    for cut in ("2017-03-07", "2017-05-05", "2017-08-31", "2017-09-12"):
        early = _days(pc.trailing_failures(bars[bars <= cut], SESSIONS, SPAN))
        assert {d for d in early if d <= cut} == {d for d in full if d <= cut}, cut


def test_an_ipo_inside_a_span_is_cut_until_its_trailing_window_fills():
    listing = pd.Timestamp("2017-05-01")
    bars = SESSIONS[SESSIONS >= listing]
    runs = pc.trailing_failures(bars, SESSIONS, ("2017-05-01", "2018-01-01"))
    k = SESSIONS.get_loc(listing)
    assert runs == [("2017-05-01", _iso(SESSIONS[k + 56]))]   # the 57th session: 57 of 60 = 95%


# --- coverage_entry ---------------------------------------------------------------------

def test_full_coverage_has_no_cut():
    coverage, cuts = pc.coverage_entry(SESSIONS, SESSIONS, [SPAN])
    assert cuts == []
    assert coverage == [{"span": ["2017-01-02", "2018-01-01"], "expected": len(SESSIONS),
                         "present": len(SESSIONS), "missing_runs": []}]


def test_a_long_run_gives_a_run_cut_and_trailing_cuts():
    bars = _without(("2017-03-01", "2017-03-13"))
    coverage, cuts = pc.coverage_entry(bars, SESSIONS, [SPAN])
    assert ("2017-03-01", "2017-03-14", "missing run of 9 sessions") in cuts
    assert any(reason == pc.TRAILING_REASON for _, _, reason in cuts)
    assert cuts == sorted(cuts)
    assert coverage[0]["present"] == len(SESSIONS) - 9
    assert coverage[0]["missing_runs"] == [["2017-03-01", "2017-03-14", 9]]


def test_a_short_run_is_listed_but_not_cut_as_a_run():
    bars = _without(("2017-04-03", "2017-04-04"))
    coverage, cuts = pc.coverage_entry(bars, SESSIONS, [SPAN])
    assert coverage[0]["missing_runs"] == [["2017-04-03", "2017-04-05", 2]]
    assert cuts == []


def test_a_zero_coverage_span_is_cut_whole():
    span = ("2017-02-01", "2017-05-01")
    coverage, cuts = pc.coverage_entry(None, SESSIONS, [span])
    inside = {_iso(d) for d in SESSIONS[(SESSIONS >= span[0]) & (SESSIONS < span[1])]}
    assert coverage[0]["present"] == 0 and coverage[0]["expected"] == len(inside)
    assert _days(cuts) >= inside
    assert {reason for _, _, reason in cuts} == {pc.RUN_REASON.format(n=len(inside)), pc.TRAILING_REASON}


def test_a_delisted_names_ragged_tail_never_cuts_its_earlier_history():
    bars = SESSIONS[SESSIONS <= "2017-06-15"]                # stops 11 sessions before its exit
    _, cuts = pc.coverage_entry(bars, SESSIONS, [("2017-01-02", "2017-07-01")])
    assert cuts and min(start for start, _, _ in cuts) >= "2017-06-16"


def test_spans_outside_the_store_window_produce_nothing():
    assert pc.coverage_entry(SESSIONS, SESSIONS, [("2012-01-03", "2015-06-01")]) == ([], [])
    coverage, _ = pc.coverage_entry(SESSIONS, SESSIONS, [("2012-01-03", "2015-06-01"), SPAN])
    assert [c["span"] for c in coverage] == [["2017-01-02", "2018-01-01"]]


def test_intraday_timestamps_count_as_their_date():
    stamped = pd.DatetimeIndex([d + pd.Timedelta(hours=15, minutes=30) for d in SESSIONS])
    assert pc.coverage_entry(stamped, SESSIONS, [SPAN])[1] == []
