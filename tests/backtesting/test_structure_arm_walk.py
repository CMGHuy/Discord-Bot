import numpy as np
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import reaction as rx
from tests.backtesting.structure_arm_fixtures import (
    CANCEL_FRAME, HL_FRAME, MSB_FRAME, PIVOT_LAG_FRAME, TEST, bear_cand, cand, frame, walk,
)

MSB5, MSB10 = sa.StructCell(sa.MSB, 5, 0.25), sa.StructCell(sa.MSB, 10, 0.25)
HL5, HL10 = sa.StructCell(sa.HL, 5, 0.25), sa.StructCell(sa.HL, 10, 0.25)


def test_cell_id_and_frozen_constants():
    assert sa.StructCell(sa.MSB, 10, 0.25).cell_id == "MSB-N10-k0.25"
    assert sa.StructCell(sa.HL, 5, 0.5).cell_id == "HL-N5-k0.50"
    assert sa.TRIGGERS == ("MSB", "HL")
    assert sa.STOP_BUFFER_ATR == 0.10 and sa.ZONE_FAIL_ATR == 0.10


def test_plan_cell_carries_the_frozen_stop_buffer():
    assert sa.StructCell(sa.HL, 15, 0.5).plan_cell() == ar.Cell(15, 0.5, 0.10)


def test_pivots_come_from_confirmed_pivots():
    pivots = sa.Pivots.from_frame(frame(HL_FRAME))
    assert np.isnan(pivots.sh[22]) and pivots.sh[23] == 101.6 and pivots.sh_pos[23] == 20
    assert pivots.sh[31] == 101.9 and pivots.sh_pos[31] == 28
    assert pivots.sl[28] == 98.6 and pivots.sl_pos[28] == 25
    assert pivots.sl[33] == 98.8 and pivots.sl_pos[33] == 30


def test_msb_triggers_at_the_first_close_above_the_confirmed_swing_high():
    assert walk(frame(MSB_FRAME)) == ar.ArmOutcome("triggered", 28, "MSB", 25)


def test_hl_ignores_the_break_without_a_higher_low_then_triggers_once_confirmed():
    """Bar 28 breaks 101.6, but the only swing low after the test is the
    touch low itself (bar 25, not > i). The higher low at 30 is confirmed
    at 33; bar 34 then closes above the newer swing high 101.9."""
    assert walk(frame(HL_FRAME), cell=MSB5) == ar.ArmOutcome("triggered", 28, "MSB", 25)
    assert walk(frame(HL_FRAME), cell=HL5) == ar.ArmOutcome("expired", 30)
    assert walk(frame(HL_FRAME), cell=HL10) == ar.ArmOutcome("triggered", 34, "HL", 25)


def test_a_close_below_the_touch_low_minus_the_buffer_cancels():
    assert walk(frame(CANCEL_FRAME)) == ar.ArmOutcome("cancelled_zone_failed", 27)


def test_the_cancel_reads_the_touch_low_before_the_bar():
    """Close 98.55 is above 98.6 - 0.10 = 98.5: no cancel, though the bar's
    own low 98.0 is the new touch low."""
    df = frame({25: TEST, 27: (99.0, 99.2, 98.0, 98.55)})
    assert walk(df) == ar.ArmOutcome("expired", 30)


def test_no_trigger_by_i_plus_n_expires_and_a_short_frame_is_unresolved():
    assert walk(frame({25: TEST})) == ar.ArmOutcome("expired", 30)
    assert walk(frame({25: TEST}, n=28)) == ar.ArmOutcome("unresolved", None)


@pytest.mark.parametrize("overrides, cell, expected", [
    (MSB_FRAME, MSB5, ar.ArmOutcome("triggered", 28, "MSB", 25)),
    (HL_FRAME, HL5, ar.ArmOutcome("expired", 30)),
    (HL_FRAME, HL10, ar.ArmOutcome("triggered", 34, "HL", 25)),
    (CANCEL_FRAME, MSB5, ar.ArmOutcome("cancelled_zone_failed", 27)),
    ({25: TEST}, MSB5, ar.ArmOutcome("expired", 30)),
])
def test_bearish_mirrors(overrides, cell, expected):
    assert walk(frame(overrides, bearish=True), c=bear_cand(), cell=cell) == expected


def test_a_swing_high_cannot_trigger_before_it_is_confirmed():
    """Bar 29 closes 102.0 above bar 27's 101.8, but bar 27 is never a
    pivot (bar 29's high beats it). Bar 29 itself is confirmed at 32; the
    first close above 102.2 is bar 33."""
    df = frame(PIVOT_LAG_FRAME)
    out = walk(df, cell=MSB10)
    assert out == ar.ArmOutcome("triggered", 33, "MSB", 25)
    pivots = sa.Pivots.from_frame(df)
    assert np.isnan(pivots.sh[31]) and pivots.sh_pos[32] == 29
    assert out.resolved_index >= pivots.sh_pos[out.resolved_index] + 3


@pytest.mark.parametrize("overrides, cell", [(MSB_FRAME, MSB5), (HL_FRAME, HL10),
                                             (CANCEL_FRAME, MSB5), (PIVOT_LAG_FRAME, MSB10)])
def test_every_outcome_is_identical_on_every_truncation_past_it(overrides, cell):
    """NO-LOOKAHEAD: full.iloc[:t + 1] decides the same as the full frame
    for every t at or after the deciding bar."""
    df = frame(overrides)
    full = walk(df, cell=cell)
    for t in range(full.resolved_index, len(df)):
        assert walk(df.iloc[:t + 1], cell=cell) == full, t


def test_a_cancel_on_the_same_bar_as_a_break_wins():
    """Review focus: the cancel is checked before the trigger. Hand-built
    pivots put a swing high (97.0) under the zone so bar 27 both breaks it
    and fails the zone."""
    df = frame(CANCEL_FRAME)
    n = len(df)
    sh = np.full(n, np.nan)
    sh[27:] = 97.0
    pivots = sa.Pivots(sh, np.where(np.isnan(sh), np.nan, 10.0), np.full(n, np.nan), np.full(n, np.nan))
    out = sa.walk_structure_arm(rx.Bars.from_frame(df), np.full(n, 1.0), pivots, cand(), MSB5)
    assert out == ar.ArmOutcome("cancelled_zone_failed", 27)


def test_a_nan_atr_bar_neither_cancels_nor_crashes():
    """Review focus: ATR14 is NaN early in a frame. NaN comparisons are
    False, so the zone cannot fail on that bar."""
    atr_values = np.full(40, 1.0)
    atr_values[27] = np.nan
    assert walk(frame(CANCEL_FRAME), atr_values=atr_values) == ar.ArmOutcome("expired", 30)
