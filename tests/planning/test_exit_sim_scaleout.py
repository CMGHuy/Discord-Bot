"""Tasks 24-26: scale-out (TP1 partial + runner) exit walk tests.

Phase 1 (pre-TP1) is byte-identical to the single-leg walk. The runner
phase's stop starts at the v39 runner floor -- entry + 2/3 x (tp1 - entry),
plan_engine.runner_floor (it started at plain break-even from Task 24 until
v39) -- can exit early at an optional TP2 (Task 25), and otherwise ratchets
via a chandelier ATR trail (Task 26) that only ever moves toward profit.
Task 27 still owes runner-timeout coverage.
"""
import pytest

from swingbot.core.planning.plan_engine import (RUNNER_FLOOR_FRACTION,
                                                runner_floor, simulate_exit)
from tests.planning.test_exit_sim_single import _plan
from tests.helpers import make_ohlcv


def test_bullish_tp1_partial_then_runner_stopped_at_trail():
    # entry 100, stop 95, tp1 110 -> rr = 2. v39 runner floor = 106.666...7.
    # This tape is only 4 bars long, well short of ATR(14)'s warmup, so
    # atr_series.iloc[j] is NaN and _safe_atr_value falls back to a
    # synthetic 2% of entry (2.0) -- the chandelier ratchet (Task 26) is
    # live on that fallback. Bar 2 must stay ABOVE the runner floor (low
    # 108.0 > 106.667) or it would close runner_be there and this test would
    # stop proving anything about the trail; its close of 113.0 lifts the
    # trail to 113.0 - 2.5*2.0 = 108.0, above the floor. Bar 3's low of
    # 107.0 then pierces that ratcheted trail -- and NOT the floor, which
    # 107.0 still clears -- so the exit is unambiguously the trail's.
    df = make_ohlcv([
        100.0,                           # 0: entry bar
        (100.0, 111.0, 99.5, 110.5),     # 1: High 111 >= tp1 110 -- leg 1 banked
        (110.0, 114.0, 108.0, 113.0),    # 2: low above the floor -- ratchets to 108.0
        (113.0, 113.5, 107.0, 108.5),    # 3: Low 107.0 <= ratcheted trail (108.0)
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 2.0
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_trail"
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(1.8)
    assert len(result.legs) == 2
    assert result.legs[0] == {"fraction": 0.5, "exit_price": 110.0,
                              "r": pytest.approx(rr), "reason": "tp1"}
    assert result.legs[1]["exit_price"] == pytest.approx(108.0)
    assert result.legs[1]["r"] == pytest.approx(1.6)
    assert result.legs[1]["reason"] == "runner_trail"
    # The floor is a starting point, not a ceiling: the trail carried the
    # stop strictly above it before the exit.
    assert result.legs[1]["exit_price"] > runner_floor(100.0, 110.0)


def test_bearish_mirror_runner_be():
    # entry 100, stop 105, tp1 90 -> rr = 2. v39 runner floor = 100 +
    # (2/3)*(90-100) = 93.333...3 -- the same formula, no is_bull branch,
    # because (tp1 - entry) is already negative here.
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: Low 89 <= tp1 90 -- leg 1 banked
        (91.0, 100.5, 90.5, 99.5),       # 2: High 100.5 >= runner floor 93.333 -- runner_be
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_be"
    assert result.legs[1]["exit_price"] == pytest.approx(93.33333333333333)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)


def test_pre_tp1_loss_is_identical_to_single_leg():
    df = make_ohlcv([100.0, (100.0, 101.0, 94.0, 95.0)])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "loss" and result.runner_outcome is None
    assert result.legs == [{"fraction": 1.0, "exit_price": 95.0,
                            "r": pytest.approx(-1.0), "reason": "stop"}]


def test_runner_rides_to_tp2():
    # entry 100, stop 95, tp1 110 (rr=2), tp2 = 118 -> leg2 r = 18/5 = 3.6
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 115.0, 109.0, 114.0),    # 2: climbing, runner alive
        (114.0, 119.0, 113.0, 117.0),    # 3: High 119 >= tp2 118 -- runner_tp2
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_tp2"
    assert result.exit_index == 3
    assert result.legs[1]["exit_price"] == 118.0
    assert result.legs[1]["r"] == pytest.approx(3.6)
    assert result.r_total == pytest.approx(0.5 * 2.0 + 0.5 * 3.6)


def test_tp2_none_means_runner_ignores_it():
    # Same tape, tp2=None: bar 3's spike to 119 must NOT close the runner.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),
        (110.0, 115.0, 109.0, 114.0),
        (114.0, 119.0, 113.0, 117.0),
        (117.0, 117.5, 99.0, 100.0),     # 4: collapse to runner stop
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome != "runner_tp2"
    assert result.exit_index == 4


def test_same_bar_runner_stop_and_tp2_is_conservative_stop_first():
    # Runner bar spans BOTH the runner floor (106.666...7) and tp2 (118):
    # stop wins. Low 99.0 is far below the floor, so the ordering -- not the
    # exact level -- is what this fixture probes.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 119.0, 99.0, 105.0),     # 2: High >= tp2 118 AND Low <= floor 106.667
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome == "runner_be"
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)


def test_chandelier_trail_locks_in_runner_profit():
    # Flat-spread bars (make_ohlcv floats: High=c*1.01, Low=c*0.99) keep
    # ATR(14) close to 2% of price during warmup. entry 100, stop 95,
    # tp1 110, no tp2, trail_atr_mult=2.5. A strong rally lifts the trail
    # well above entry; the later plunge pierces the trail but stays above
    # entry -- exit at the trail level, r_total > 0.5*rr.
    closes = ([100.0] * 15                  # ATR warmup
              + [111.0]                     # TP1 banked here
              + [115.0, 120.0, 126.0, 132.0, 138.0]   # rally ratchets the trail
              + [120.0])                    # plunge through the trail
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=14, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_trail"
    exit_leg = result.legs[1]
    assert exit_leg["exit_price"] > runner_floor(100.0, 110.0)   # trail beat the floor
    assert exit_leg["r"] > 0.0
    assert result.r_total > (0.5 + 0.5 * RUNNER_FLOOR_FRACTION) * 2.0  # better than the floor


def test_trail_never_ratchets_backwards():
    # After a big up-close ratchets the trail, a down-close must NOT lower it:
    # the pullback bar that would survive a re-lowered trail must still exit
    # against the higher trail set by the 130-close bar, not a lower trail
    # implied by the 124-close bar's (larger, since ATR widens on the gap)
    # ATR reading.
    closes = ([100.0] * 15 + [111.0]
              + [130.0]        # trail jumps to 130 - 2.5*ATR(bar16)
              + [124.0]        # down-close: trail must NOT drop
              + [118.0])       # pierces the ratcheted trail -> exit
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=14, plan=plan, scale_out=True)
    assert result.runner_outcome == "runner_trail"

    from swingbot.core.market.indicators import atr as atr_indicator
    atr_series = atr_indicator(df, 14)
    trail_from_130 = 130.0 - 2.5 * float(atr_series.iloc[16])
    trail_from_124 = 130.0 - 2.5 * float(atr_series.iloc[17])
    assert trail_from_124 < trail_from_130    # sanity: the would-be lower trail
    # ratchet floor: exit lands on the 130-close bar's trail, never the lower one
    assert result.legs[1]["exit_price"] == pytest.approx(trail_from_130)


def test_chandelier_stop_pure_function():
    from swingbot.core.planning.plan_engine import chandelier_stop
    assert chandelier_stop(130.0, 2.0, 2.5, "bullish") == pytest.approx(125.0)
    assert chandelier_stop(70.0, 2.0, 2.5, "bearish") == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# Task 27: runner-timeout fallthrough + two-leg accounting invariants
# ---------------------------------------------------------------------------

import numpy as np


def test_runner_timeout_marks_leg2_at_last_close():
    # 2w horizon (max_holding_days=14): TP1 on bar 1, then a drift that never
    # touches the floor/trail/tp2 -> runner_timeout at entry+14, leg 2 at that
    # close. The drift bars' low of 107.0 deliberately clears the v39 runner
    # floor (106.666...7) -- a lower low would close this as runner_be on the
    # first drift bar and it would stop testing the timeout at all.
    closes = [100.0, (100.0, 111.0, 99.5, 110.5)] + [(108.0, 109.0, 107.0, 108.0)] * 20
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None,
                 horizon_key="2w", trail_atr_mult=50.0)   # trail parked far away
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_timeout"
    assert result.exit_index == 14
    assert result.legs[1]["exit_price"] == 108.0
    assert result.legs[1]["r"] == pytest.approx((108.0 - 100.0) / 5.0)


def test_win_never_goes_negative_property():
    # 50 seeded random walks: whenever scale_out reports a win, r_total must
    # be >= (tp1_fraction + runner_fraction * RUNNER_FLOOR_FRACTION) * rr --
    # leg 1 banked at TP1, the runner leg floored at the v39 runner floor
    # rather than at breakeven. That is 0.8333*rr, up from the pre-v39
    # 0.5*rr. The 0.002 slack absorbs plan_engine's round(..., 3) on each
    # leg (measured worst case across these 50 seeds: -0.00067).
    rng = np.random.RandomState(42)
    floor_multiple = 0.5 + 0.5 * RUNNER_FLOOR_FRACTION
    violations = []
    for k in range(50):
        closes = list(100.0 * np.cumprod(1 + rng.normal(0.001, 0.02, 60)))
        df = make_ohlcv(closes)
        plan = _plan(direction="bullish",
                     stop_loss=closes[0] * 0.95, tp1=closes[0] * 1.04,
                     trigger_price=closes[0], tp2=None, horizon_key="4w")
        result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
        if result.outcome == "win":
            rr = (plan.tp1 - closes[0]) / (closes[0] - plan.stop_loss)
            if result.r_total < floor_multiple * rr - 0.002:
                violations.append((k, result.r_total, floor_multiple * rr))
    assert not violations, violations


def test_runner_timeout_floors_at_protective_stop_when_tp1_on_last_bar():
    # Degenerate edge case (Task 27 review fix): TP1 is touched on the LAST
    # bar of the holding window (tp1_index == end), so the runner-phase loop
    # `for j in range(tp1_index + 1, end + 1)` is empty and runner_stop is
    # never ratcheted past its initial BE value. Before the fix, the
    # runner-timeout fallthrough used close[end] unclamped -- and close[end]
    # is the TP1 bar's own close, never checked against any stop. Here it
    # closes BELOW entry (96 < 100), which would have made leg 2's r
    # negative and violated the "win never turns negative" invariant
    # (r_total would be 0.6, below the 0.5*rr=1.0 floor).
    # entry=100, stop=95, tp1=110 (rr=2), 2w horizon (max_holding_days=14).
    closes = ([100.0]                        # 0: entry bar
              + [100.0] * 13                 # 1-13: flat, no stop/target touch
              + [(100.0, 110.0, 96.0, 96.0)]) # 14: last bar -- touches tp1,
                                              #     low stays above stop, close < entry
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None,
                 horizon_key="2w")
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 2.0
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_timeout"
    assert result.exit_index == 14
    # Clamped to runner_stop -- the v39 runner floor (106.666...7), which the
    # empty runner loop never ratcheted -- not the raw close (96).
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)
    assert result.r_total >= 0.5 * rr - 1e-9   # the invariant the bug violated


def test_runner_timeout_uses_checked_stop_not_post_ratchet_trail():
    # Second-order bug found in review of the first Task 27 fix (commit
    # ab86151): the runner-timeout clamp used the POST-ratchet runner_stop
    # (computed from the final bar's own close/ATR, which is never checked
    # against that bar's low/high -- there's no next iteration to check it
    # in) instead of the stop level actually CHECKED against that bar. When
    # ATR narrows late in the window, the post-ratchet trail can climb
    # ABOVE the bar's actual close, inflating the reported exit price past
    # a level the bar never validated as a trigger.
    #
    # Fixture: extreme_close peaks at 108 right after TP1 (bar 1), then a
    # gradual quiet decline (small per-bar ranges, so no ATR spike) brings
    # price down to the final bar, which closes at 104.0 with a low of
    # 103.5. The dataframe is exactly 14 rows, so `end` is capped at index
    # 13 by `n - 1` (not by the 2w horizon's max_holding_days=14): bar 13
    # is both the last bar walked AND the first bar where real ATR(14)
    # stops being NaN (the fallback-ATR-based ratchet floors runner_stop
    # at 108 - 2.5*2.0 = 103.0 through bars 2-12 -- that 103.0 is
    # "checked_stop", the value actually checked against bar 13's low).
    # Bar 13's own end-of-iteration ratchet uses the now-real ATR(14),
    # computed below directly via swingbot.core.market.indicators.atr (not
    # hand-waved): atr(14)[13] == 1.488244065325937, giving a POST-ratchet
    # trail of 108 - 2.5*1.488244065325937 == 104.27938983668516 -- ABOVE
    # the bar's actual close (104.0) and never checked against any
    # subsequent bar (there isn't one). Pre-fix, the clamp reported
    # 104.27938983668516 (a price the bar never closed at); post-fix it
    # must report the real close, 104.0.
    from swingbot.core.market.indicators import atr as atr_indicator

    decline = [108.0 - 0.4 * k for k in range(1, 12)]   # 11 bars: 107.6 .. 103.6
    closes = ([100.0, (100.0, 111.0, 99.5, 108.0)]              # 0: entry, 1: TP1 touch (peak close=108)
              + [(c, c * 1.002, c * 0.998, c) for c in decline]  # 2-12: gradual quiet decline
              + [(103.7, 104.5, 103.5, 104.0)])                 # 13 (=end, n=14 rows): timeout bar
    df = make_ohlcv(closes)
    assert len(df) == 14

    # Verify the real ATR(14) value driving the post-ratchet (buggy) trail
    # on this exact constructed df, rather than hand-waving the arithmetic.
    atr13 = float(atr_indicator(df, 14).iloc[13])
    assert atr13 == pytest.approx(1.488244065325937)
    checked_stop = 108.0 - 2.5 * 2.0          # fallback-ATR ratchet, pinned through bars 2-12
    post_ratchet_trail = 108.0 - 2.5 * atr13  # the buggy (unchecked) value
    assert checked_stop == pytest.approx(103.0)
    assert post_ratchet_trail == pytest.approx(104.27938983668516)
    assert checked_stop < 104.0 < post_ratchet_trail   # close sits strictly between the two

    # v39: tp1 is 102, not 110, ON PURPOSE. The runner floor is
    # runner_floor(100, 102) == 101.333, comfortably BELOW checked_stop
    # (103.0), so this fixture's quiet decline still survives to the bar-13
    # timeout and the clamp -- not the floor -- is what it probes. With
    # tp1=110 the floor would be 106.667, above the entire decline, and the
    # runner would close runner_be on bar 4 instead.
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=102.0, tp2=None,
                 horizon_key="2w")
    assert runner_floor(100.0, 102.0) < checked_stop
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 0.4                                   # (102 - 100) / 5
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_timeout"
    assert result.exit_index == 13
    # Fixed: reports the bar's real close (104.0), NOT the inflated
    # post-ratchet trail (104.27938983668516) that was never checked.
    assert result.legs[0]["exit_price"] == pytest.approx(102.0)
    assert result.legs[0]["r"] == pytest.approx(rr)
    assert result.legs[1]["exit_price"] == pytest.approx(104.0)
    assert result.legs[1]["r"] == pytest.approx(0.8)
    assert result.r_total == pytest.approx(0.6)


def test_legs_fractions_always_sum_to_one():
    # every terminal ExitResult with legs: fractions sum to 1.0 and
    # r_total == sum(fraction * r), each side rounded to 3dp independently
    # (r_total from the unrounded blend, the recomputation from the
    # already-rounded per-leg r) -- v39's floor (106.666...7 here, vs. the
    # pre-v39 exact-breakeven 100.0) makes leg 2's r a repeating decimal
    # (1.333...) rather than 0.0, so the two independently-rounded sides can
    # differ by up to a thousandth. abs=0.001 absorbs exactly that, not a
    # real mismatch.
    closes = [100.0, (100.0, 111.0, 99.5, 110.5), (110.0, 112.0, 99.0, 100.0)]
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert sum(l["fraction"] for l in result.legs) == pytest.approx(1.0)
    assert result.r_total == pytest.approx(
        sum(l["fraction"] * l["r"] for l in result.legs), abs=0.001)


# ---------------------------------------------------------------------------
# v39: the runner floor. The formula itself, both directions, and the
# boundary guard proving the stop is no longer plain breakeven.
# ---------------------------------------------------------------------------

def test_runner_floor_is_two_thirds_of_the_tp1_move():
    # One formula, no is_bull branch: (tp1 - entry) carries the sign.
    assert RUNNER_FLOOR_FRACTION == pytest.approx(2.0 / 3.0)
    assert runner_floor(100.0, 110.0) == pytest.approx(106.66666666666667)
    assert runner_floor(100.0, 90.0) == pytest.approx(93.33333333333333)
    # A degenerate plan whose tp1 sits on entry floors at entry, exactly as
    # the pre-v39 model did. (_scale_out_exit_walk returns "no_trade" before
    # ever reaching phase 2 when risk <= 0, so that case never gets here.)
    assert runner_floor(100.0, 100.0) == pytest.approx(100.0)


def test_bullish_runner_stops_at_the_floor_not_at_plain_breakeven():
    # Bar 2 dips to 103.0 -- ABOVE the old breakeven floor (entry 100) and
    # BELOW the v39 floor (106.666...7). Pre-v39 this bar survived and the
    # trade timed out at that bar's close (104.0, r_total 1.4); now it must
    # close at the floor. This is the regression guard: if the boundary
    # silently reverted to entry, this test fails.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 110.5, 103.0, 104.0),    # 2: low between old BE and the new floor
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_be"
    assert result.exit_index == 2
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)


def test_bearish_runner_stops_at_the_floor_not_at_plain_breakeven():
    # Mirror image: bar 2 rallies to 97.0 -- BELOW the old breakeven floor
    # (entry 100) and ABOVE the v39 floor (93.333...3). Pre-v39 this
    # survived to a 96.0 timeout (r_total 1.4).
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: TP1 banked
        (91.0, 97.0, 90.5, 96.0),        # 2: high between the new floor and old BE
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_be"
    assert result.exit_index == 2
    assert result.legs[1]["exit_price"] == pytest.approx(93.33333333333333)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)
