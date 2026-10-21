"""v173 plan panel review: data admission -- trim to asof, NYSE calendar
gaps, and the adjustment basis of the auto_adjust daily cache.

Same frames as test_override_fidelity_replay: 15 warm-up bars, the fill at
index 15 (Mon 2026-10-05), the override at index 17 (Wed 2026-10-07), the
last bar at index 25 (Mon 2026-10-19). Index 20 is Mon 2026-10-12 (an NYSE
session), index 24 is Fri 2026-10-16. Hold cap 8 unless a test says so.
"""
from datetime import date

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from tests.analytics.test_override_fidelity_replay import (FILL_IDX, FLAT, LAST_DAY, OV_IDX,
                                                           UNSTAMPED, frame, plan, replay)
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

FRI = date(2026, 10, 16)        # index 24
GAP_DAY = date(2026, 10, 12)    # index 20
HALVED = {i: tuple(v / 2 for v in FLAT) for i in range(20, 26)}   # a 2:1 seam at index 20


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


# -- trim_to_asof ------------------------------------------------------------

def test_trim_keeps_bars_on_or_before_asof_only():
    df = frame()
    out = of.trim_to_asof(df, FRI)
    assert out.index[-1].date() == FRI
    assert out.equals(df.iloc[:25])
    assert len(df) == 26                                   # the input is not mutated
    assert of.trim_to_asof(df, LAST_DAY).equals(df)
    assert of.trim_to_asof(df, date(2026, 9, 1)).empty


def test_a_bar_dated_after_asof_never_reaches_the_walk(monkeypatch):
    """The cache can hold a half-formed bar for today (data_refresh.py:160-170).
    Here Monday's bar runs through the stop; with asof = Friday no frame the
    replay walks (real, engine, or the indicator frame) reaches it."""
    seen = []
    walk = of.engine_path

    def spy(p, df, fill_idx, *, indicator_df=None):
        seen.append(df.index[-1].date())
        if indicator_df is not None:
            seen.append(indicator_df.index[-1].date())
        return walk(p, df, fill_idx, indicator_df=indicator_df)

    monkeypatch.setattr(of, "engine_path", spy)
    row = replay(plan(), frame({25: (101.0, 102.0, 94.0, 95.0)}), when=FRI)
    assert seen and max(seen) == FRI
    assert (row.status, row.engine_exit_reason) == ("resolved", "timeout")


def test_the_trim_decides_open_against_the_hold_cap():
    """Hold cap 10 from the fill at 15 ends at index 25. Trimmed to Friday
    (index 24) the walk clips at the data end: still open. With Monday
    settled, the same plan times out on the hold cap: resolved."""
    assert replay(plan(hold_cap_bars=10), frame(), when=FRI).status == "open"
    assert replay(plan(hold_cap_bars=10), frame(), when=LAST_DAY).status == "resolved"


def test_asof_before_every_bar_is_unreplayable():
    assert replay(plan(), frame(), when=date(2026, 9, 1)).status == "unreplayable"


# -- missing_sessions and stale ----------------------------------------------

def test_missing_sessions_lists_calendar_sessions_absent_from_the_frame():
    df = frame()
    gap = df.drop(df.index[20])
    assert of.missing_sessions(df, date(2026, 10, 5)) == []
    assert of.missing_sessions(gap, date(2026, 10, 5)) == [GAP_DAY]
    assert of.missing_sessions(gap, date(2026, 10, 13)) == []      # the gap is before start
    assert of.missing_sessions(df, date(2026, 10, 10)) == []       # a Saturday start
    assert of.missing_sessions(gap.iloc[0:0], date(2026, 10, 5)) == []
    assert of.missing_sessions(None, date(2026, 10, 5)) == []


@pytest.mark.parametrize("missing", [16, OV_IDX, 20],
                         ids=["after-fill", "override-session", "after-override"])
def test_a_missing_session_from_the_fill_on_is_stale(missing):
    df = frame()
    row = replay(plan(), df.drop(df.index[missing]), when=LAST_DAY)
    assert row.status == "stale"
    assert (row.engine_r, row.delta_r, row.outcome) == (None, None, None)


def test_a_pre_v173_row_missing_its_override_session_stays_unreplayable():
    df = frame()
    gap = df.drop(df.index[OV_IDX])
    assert replay(plan(override=UNSTAMPED), gap, when=LAST_DAY).status == "unreplayable"


def test_a_gap_before_the_fill_does_not_matter():
    df = frame()
    assert replay(plan(), df.drop(df.index[5]), when=LAST_DAY).status == "resolved"


def test_a_stamped_close_after_the_last_settled_bar_is_stale():
    """Report run on the close day itself: asof is the previous session, so
    the settled bars stop before the override session."""
    assert replay(plan(), frame(), when=date(2026, 10, 6)).status == "stale"


# -- split_suspect -----------------------------------------------------------

def test_a_two_for_one_seam_after_the_fill_is_split_affected():
    df = frame(HALVED)
    assert of._split_band(plan(), df, FILL_IDX) is False       # the fill bar itself agrees
    assert of.split_suspect(plan(), df, FILL_IDX) is True
    row = replay(plan(), df)
    assert row.status == "split_affected"
    assert (row.engine_r, row.delta_r) == (None, None)


def test_the_fill_bar_band_still_marks_split_suspect():
    assert of.split_suspect(plan(), frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)}), FILL_IDX) is True
    assert of.split_suspect(plan(), frame(), FILL_IDX) is False


def test_a_seam_before_the_fill_is_not_split_affected():
    df = frame({i: (200.0, 201.0, 199.0, 200.0) for i in range(10)})   # seam at index 10
    assert of.split_suspect(plan(), df, FILL_IDX) is False
    assert replay(plan(), df).status == "resolved"


def test_a_dividend_sized_drift_inside_two_percent_stays_resolved():
    """auto_adjust rescales history before an ex-date: a 1% dividend on
    Mon 2026-10-12 scales every earlier bar, the fill bar included, by 0.99.
    The raw entry (100) sits inside the fill bar's 2% band (99.99 x 1.02)
    and a 1% step is no seam."""
    df = frame()
    df.iloc[:20, :4] = df.iloc[:20, :4] * 0.99
    assert of.split_suspect(plan(), df, FILL_IDX) is False
    assert replay(plan(), df).status == "resolved"


def test_stale_beats_a_seam():
    assert replay(plan(), frame(HALVED), when=date(2026, 10, 20)).status == "stale"
