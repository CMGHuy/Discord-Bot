"""Tasks 24-26: scale-out (TP1 partial + runner) exit walk tests.

Phase 1 (pre-TP1) is byte-identical to the single-leg walk. The runner
phase's stop starts at break-even (Task 24), can exit early at an optional
TP2 (Task 25), and otherwise ratchets via a chandelier ATR trail (Task 26)
that only ever moves toward profit. Task 27 still owes runner-timeout
coverage.
"""
import pytest

from swingbot.core.plan_engine import simulate_exit
from tests.test_exit_sim_single import _plan
from tests.helpers import make_ohlcv


def test_bullish_tp1_partial_then_runner_stopped_at_trail():
    # entry 100, stop 95, tp1 110 -> rr = 2. Rise through TP1, fall back to entry.
    # This tape is only 4 bars long, well short of ATR(14)'s warmup, so
    # atr_series.iloc[j] is NaN and _safe_atr_value falls back to a
    # synthetic 2% of entry (2.0) -- the chandelier ratchet (Task 26) is
    # still live on that fallback, so by the time bar 3 hits, runner_stop
    # has already ratcheted up from BE (100) to 105.5, above the entry
    # (pre-Task-26 this fixture would have exited flat at BE instead).
    df = make_ohlcv([
        100.0,                           # 0: entry bar
        (100.0, 111.0, 99.5, 110.5),     # 1: High 111 >= tp1 110 -- leg 1 banked
        (110.0, 110.5, 104.0, 105.0),    # 2: above entry -- runner survives, ratchets
        (105.0, 105.5, 99.5, 100.5),     # 3: Low 99.5 <= ratcheted trail (105.5)
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 2.0
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_trail"
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(1.55)
    assert len(result.legs) == 2
    assert result.legs[0] == {"fraction": 0.5, "exit_price": 110.0,
                              "r": pytest.approx(rr), "reason": "tp1"}
    assert result.legs[1]["exit_price"] == pytest.approx(105.5)
    assert result.legs[1]["r"] == pytest.approx(1.1)
    assert result.legs[1]["reason"] == "runner_trail"


def test_bearish_mirror_runner_be():
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: Low 89 <= tp1 90 -- leg 1 banked
        (91.0, 100.5, 90.5, 99.5),       # 2: High 100.5 >= runner stop 100 -- runner_be
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_be"
    assert result.r_total == pytest.approx(2.0 * 0.5)


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
    # Runner bar spans BOTH the runner stop (100, BE) and tp2: stop wins.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 119.0, 99.0, 105.0),     # 2: High >= tp2 118 AND Low <= BE 100
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome == "runner_be"
    assert result.legs[1]["r"] == pytest.approx(0.0)


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
    assert exit_leg["exit_price"] > 100.0            # trail was above entry
    assert exit_leg["r"] > 0.0
    assert result.r_total > 0.5 * 2.0                # better than plain BE runner


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

    from swingbot.core.indicators import atr as atr_indicator
    atr_series = atr_indicator(df, 14)
    trail_from_130 = 130.0 - 2.5 * float(atr_series.iloc[16])
    trail_from_124 = 130.0 - 2.5 * float(atr_series.iloc[17])
    assert trail_from_124 < trail_from_130    # sanity: the would-be lower trail
    # ratchet floor: exit lands on the 130-close bar's trail, never the lower one
    assert result.legs[1]["exit_price"] == pytest.approx(trail_from_130)


def test_chandelier_stop_pure_function():
    from swingbot.core.plan_engine import chandelier_stop
    assert chandelier_stop(130.0, 2.0, 2.5, "bullish") == pytest.approx(125.0)
    assert chandelier_stop(70.0, 2.0, 2.5, "bearish") == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# Task 27: runner-timeout fallthrough + two-leg accounting invariants
# ---------------------------------------------------------------------------

import numpy as np


def test_runner_timeout_marks_leg2_at_last_close():
    # 2w horizon (max_holding_days=14): TP1 on bar 1, then a drift that never
    # touches BE/trail/tp2 -> runner_timeout at entry+14, leg 2 at that close.
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
    # be >= 0.5*rr (leg 1 banked; runner floor is BE) -- the spec §5 invariant.
    rng = np.random.RandomState(42)
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
            if result.r_total < 0.5 * rr * 0.999:
                violations.append((k, result.r_total))
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
    # Clamped to runner_stop (BE = entry_price = 100), not the raw close (96).
    assert result.legs[1]["exit_price"] == pytest.approx(100.0)
    assert result.legs[1]["r"] == pytest.approx(0.0)
    assert result.r_total == pytest.approx(0.5 * rr)
    assert result.r_total >= 0.5 * rr - 1e-9   # the invariant the bug violated


def test_legs_fractions_always_sum_to_one():
    # every terminal ExitResult with legs: fractions sum to 1.0 and
    # r_total == sum(fraction * r) exactly.
    closes = [100.0, (100.0, 111.0, 99.5, 110.5), (110.0, 112.0, 99.0, 100.0)]
    df = make_ohlcv(closes)
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert sum(l["fraction"] for l in result.legs) == pytest.approx(1.0)
    assert result.r_total == pytest.approx(
        sum(l["fraction"] * l["r"] for l in result.legs))
