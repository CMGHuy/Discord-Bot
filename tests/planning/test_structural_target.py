"""Unit tests for select_structural_target() -- v31 Task 2.

Pure function, no fixtures, no data cache. Names the AXON regression that
motivated the whole plan (entry 617.38, stop 604.59): the old
entry +/- risk * rr arithmetic priced targets that risked ~3x what they
stood to make.
"""
import pytest

from swingbot.core.planning.plan_engine import select_structural_target


def test_picks_nearest_qualifying_not_farthest():
    # entry 100, stop 96 -> risk 4; min 1.5/max 2.5 -> band [106, 110]
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[102, 107, 109], min_rr=1.5, max_rr=2.5,
    )
    assert result == 107


def test_skips_candidates_under_the_floor():
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[101, 102, 103], min_rr=1.5, max_rr=2.5,
    )
    assert result is None


def test_caps_instead_of_skipping_or_searching_on():
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[130], min_rr=1.5, max_rr=2.5,
    )
    assert result == 110.0
    assert result != 130
    assert result is not None


def test_a_level_exactly_at_the_floor_qualifies():
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[106.0], min_rr=1.5, max_rr=2.5,
    )
    assert result == 106.0

    # Repeat at real prices (AXON risk: entry 617.38, stop 604.59) to prove
    # the epsilon holds when float arithmetic doesn't land exactly.
    entry, stop = 617.38, 604.59
    risk = entry - stop
    floor = entry + risk * 1.5
    result2 = select_structural_target(
        entry=entry, stop_loss=stop, is_bull=True,
        candidate_levels=[floor], min_rr=1.5, max_rr=2.5,
    )
    assert result2 == pytest.approx(floor)


def test_bearish_mirrors_exactly():
    # entry 100, stop 104 -> risk 4; min 1.5/max 2.5 -> band [94, 90]
    #
    # PLAN DEFECT corrected: the plan's own text asserted candidates
    # [98, 93, 91] -> 94.0 "(cap)". 94.0 is the FLOOR boundary here (no
    # candidate sits there), and the actual cap price is entry - cap_dist =
    # 90.0 -- neither matches. Independently re-derived by mirroring the
    # bullish nearest-qualifying case (entry 100/stop 96, candidates
    # [102, 107, 109] -> 107; mirrored about entry that's 93) and confirmed
    # by running the verbatim-transcribed production code: 93.0, not 94.0.
    # Corrected the assertion and added a genuine bearish cap sub-case
    # (single far candidate) for symmetry with test_caps_instead_of_...
    result = select_structural_target(
        entry=100, stop_loss=104, is_bull=False,
        candidate_levels=[98, 93, 91], min_rr=1.5, max_rr=2.5,
    )
    assert result == 93.0

    result2 = select_structural_target(
        entry=100, stop_loss=104, is_bull=False,
        candidate_levels=[98, 93], min_rr=1.5, max_rr=2.5,
    )
    assert result2 == 93

    result3 = select_structural_target(
        entry=100, stop_loss=104, is_bull=False,
        candidate_levels=[50], min_rr=1.5, max_rr=2.5,
    )
    assert result3 == 90.0


def test_candidates_on_the_wrong_side_of_entry_are_ignored():
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[80, 70], min_rr=1.5, max_rr=2.5,
    )
    assert result is None


def test_zero_or_inverted_risk_returns_none():
    result = select_structural_target(
        entry=100, stop_loss=100, is_bull=True,
        candidate_levels=[110], min_rr=1.5, max_rr=2.5,
    )
    assert result is None


def test_max_below_min_raises():
    with pytest.raises(ValueError):
        select_structural_target(
            entry=100, stop_loss=96, is_bull=True,
            candidate_levels=[110], min_rr=2.5, max_rr=1.5,
        )


def test_no_candidates_at_all_returns_none():
    result = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[], min_rr=1.5, max_rr=2.5,
    )
    assert result is None

    result2 = select_structural_target(
        entry=100, stop_loss=96, is_bull=True,
        candidate_levels=[None, 0, False], min_rr=1.5, max_rr=2.5,
    )
    assert result2 is None


def test_the_axon_case():
    # The regression that names the bug: old entry +/- risk*rr arithmetic
    # posted TP 621.85 / SL 604.59 on entry 617.38 -- reward 4.47 against
    # risk 12.79. 621.85 is only 0.35R and must be rejected; 640 is 1.77R.
    result = select_structural_target(
        entry=617.38, stop_loss=604.59, is_bull=True,
        candidate_levels=[621.85, 640.0, 700.0], min_rr=1.5, max_rr=2.5,
    )
    assert result == 640.0
