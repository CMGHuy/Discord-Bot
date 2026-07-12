"""Task 21: single-leg exit-walk tests for the shared exit simulator.

Only the win/loss single-leg (scale_out=False) path is in scope here.
Most golden fixtures use a market entry (fills at signal bar's close) so
the entry phase is unambiguous, then walk straight to either TP1 (win) or
the stop (loss) with no break-even trigger involved. Scratch/timeout/
same-bar ordering are Task 22's scope, not tested here.

One additional fixture (below) covers a stop_entry plan's fill flowing
into this same single-leg walk -- the fill bar establishes entry_index/
entry_price per Task 18's trigger_hit/fill_price semantics, and the walk
then proceeds exactly as it would for a market entry starting at
entry_index+1.
"""
import pytest

from swingbot.core.plan_engine import TradePlanV2, PlanStatus, simulate_exit
from tests.helpers import make_ohlcv


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="strategy",
        strategy="Fibonacci", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


# ---------------------------------------------------------------------------
# bullish
# ---------------------------------------------------------------------------

def test_bullish_market_straight_run_to_tp1_is_a_win():
    # entry fills at bar 0's close (100.0). stop=95.0, tp1=110.0 -> risk=5, rr=2.
    df = make_ohlcv([
        100.0,                          # 0: signal/entry bar, entry_price=100.0
        (100.0, 103.0, 99.0, 102.0),    # 1: no stop/target touch
        (102.0, 106.0, 101.0, 105.0),   # 2: no stop/target touch
        (105.0, 111.0, 104.0, 108.0),   # 3: High 111 >= tp1 110 -- win
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0)

    result = simulate_exit(df, signal_index=0, plan=plan)

    risk = 100.0 - 95.0
    rr = (110.0 - 100.0) / risk
    assert result.outcome == "win"
    assert result.entry_index == 0
    assert result.entry_price == 100.0
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(rr)
    assert len(result.legs) == 1
    assert result.legs[0]["exit_price"] == 110.0
    assert result.legs[0]["fraction"] == pytest.approx(1.0)
    assert result.legs[0]["r"] == pytest.approx(rr)


def test_bullish_market_straight_drop_to_stop_is_a_loss():
    # entry fills at bar 0's close (100.0). stop=95.0 -- straight drop, no BE trigger.
    df = make_ohlcv([
        100.0,                          # 0: signal/entry bar, entry_price=100.0
        (100.0, 101.0, 98.0, 99.0),     # 1: no touch (favorable excursion small)
        (99.0, 100.0, 96.0, 97.0),      # 2: no touch
        (97.0, 98.0, 94.0, 95.5),       # 3: Low 94 <= stop 95 -- loss
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0)

    result = simulate_exit(df, signal_index=0, plan=plan)

    assert result.outcome == "loss"
    assert result.entry_index == 0
    assert result.entry_price == 100.0
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(-1.0)
    assert len(result.legs) == 1
    assert result.legs[0]["exit_price"] == 95.0
    assert result.legs[0]["fraction"] == pytest.approx(1.0)
    assert result.legs[0]["r"] == pytest.approx(-1.0)


def test_bullish_zero_risk_is_no_trade():
    # stop_loss == entry_price -- risk is non-positive, so the legacy loop
    # this was ported from skips the signal entirely: no trade recorded.
    df = make_ohlcv([
        100.0,                          # 0: signal/entry bar, entry_price=100.0
        (100.0, 103.0, 99.0, 102.0),    # 1: irrelevant, walk should never start
    ])
    plan = _plan(direction="bullish", stop_loss=100.0, tp1=110.0)

    result = simulate_exit(df, signal_index=0, plan=plan)

    assert result.outcome == "no_trade"
    assert result.r_total == 0.0
    assert result.legs == []


# ---------------------------------------------------------------------------
# stop_entry fill flowing into the single-leg walk
# ---------------------------------------------------------------------------

def test_bullish_stop_entry_fill_flows_into_single_leg_walk_to_tp1_win():
    # Bar 1 doesn't yet reach the trigger; bar 2 gaps above it and fills at
    # max(open, trigger) = 106.0 (Task 18 semantics). risk = 106-101 = 5,
    # target_dist = 116-106 = 10 -> rr = 2. The walk then starts at
    # entry_index+1 (bar 3), same as a market entry would, and runs to a
    # clean TP1 win -- the fill bar itself is never re-checked for stop/tp1.
    df = make_ohlcv([
        100.0,                          # 0: signal bar
        (100.0, 104.0, 99.0, 103.0),    # 1: High 104 < trigger 105 -- no fill
        (106.0, 107.0, 105.5, 106.5),   # 2: gaps above trigger -- fills at Open=106.0
        (106.0, 109.0, 105.0, 108.0),   # 3: no stop/target touch, BE trigger (111) not reached
        (108.0, 112.0, 107.0, 111.0),   # 4: no stop/target touch, High 112 >= BE trigger 111 -- stop moves
        (111.0, 117.0, 110.0, 114.0),   # 5: High 117 >= tp1 116 -- win
    ])
    plan = _plan(entry_type="stop_entry", direction="bullish",
                 trigger_price=105.0, stop_loss=101.0, tp1=116.0, expiry_bars=5)

    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=False)

    risk = 106.0 - 101.0
    rr = (116.0 - 106.0) / risk
    assert result.outcome == "win"
    assert result.entry_index == 2
    assert result.entry_price == 106.0
    assert result.exit_index == 5
    assert result.r_total == pytest.approx(rr)
    assert len(result.legs) == 1
    assert result.legs[0]["exit_price"] == 116.0
    assert result.legs[0]["fraction"] == pytest.approx(1.0)
    assert result.legs[0]["r"] == pytest.approx(rr)


# ---------------------------------------------------------------------------
# bearish
# ---------------------------------------------------------------------------

def test_bearish_market_straight_run_to_tp1_is_a_win():
    # entry fills at bar 0's close (100.0). stop=105.0, tp1=90.0 -> risk=5, rr=2.
    df = make_ohlcv([
        100.0,                          # 0: signal/entry bar, entry_price=100.0
        (100.0, 101.0, 97.0, 98.0),     # 1: no stop/target touch
        (98.0, 99.0, 94.0, 95.0),       # 2: no stop/target touch
        (95.0, 96.0, 89.0, 92.0),       # 3: Low 89 <= tp1 90 -- win
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0)

    result = simulate_exit(df, signal_index=0, plan=plan)

    risk = 105.0 - 100.0
    rr = abs(90.0 - 100.0) / risk
    assert result.outcome == "win"
    assert result.entry_index == 0
    assert result.entry_price == 100.0
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(rr)
    assert len(result.legs) == 1
    assert result.legs[0]["exit_price"] == 90.0
    assert result.legs[0]["fraction"] == pytest.approx(1.0)
    assert result.legs[0]["r"] == pytest.approx(rr)


def test_bearish_market_straight_rally_to_stop_is_a_loss():
    # entry fills at bar 0's close (100.0). stop=105.0 -- straight rally, no BE trigger.
    df = make_ohlcv([
        100.0,                          # 0: signal/entry bar, entry_price=100.0
        (100.0, 102.0, 99.0, 101.0),    # 1: no touch (favorable excursion small)
        (101.0, 103.0, 100.0, 102.5),   # 2: no touch
        (102.5, 106.0, 102.0, 104.5),   # 3: High 106 >= stop 105 -- loss
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0)

    result = simulate_exit(df, signal_index=0, plan=plan)

    assert result.outcome == "loss"
    assert result.entry_index == 0
    assert result.entry_price == 100.0
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(-1.0)
    assert len(result.legs) == 1
    assert result.legs[0]["exit_price"] == 105.0
    assert result.legs[0]["fraction"] == pytest.approx(1.0)
    assert result.legs[0]["r"] == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Task 22: scratch, timeout, same-bar ordering
# ---------------------------------------------------------------------------

def test_bullish_scratch_after_breakeven_move():
    # entry 100, stop 95, tp1 110 -> BE trigger = 100 + 0.5*10 = 105.
    # Bar 1 reaches 106 (arms the BE move; original stop still governs that
    # bar), bar 2 falls back through entry -> stop at 100.0, scratch, 0R.
    df = make_ohlcv([
        100.0,                          # 0: entry bar
        (100.0, 106.0, 99.5, 105.0),    # 1: High 106 >= 105 -- BE armed
        (104.0, 104.5, 99.0, 100.5),    # 2: Low 99 <= moved stop 100 -- scratch
    ])
    result = simulate_exit(df, signal_index=0,
                           plan=_plan(direction="bullish", stop_loss=95.0, tp1=110.0))
    assert result.outcome == "scratch"
    assert result.exit_index == 2
    assert result.r_total == pytest.approx(0.0, abs=1e-9)
    assert result.legs[0]["exit_price"] == 100.0
    assert result.legs[0]["reason"] == "breakeven_stop"


def test_original_stop_governs_the_bar_that_arms_the_be_move():
    # The SAME bar reaches the BE trigger AND falls back through entry: the
    # moved stop only protects SUBSEQUENT bars, so this is NOT a scratch --
    # the walk continues (no touch of original stop 95 / tp1 110 that bar).
    df = make_ohlcv([
        100.0,
        (100.0, 106.0, 99.0, 100.5),    # 1: arms BE AND trades below entry -- no exit
        (100.0, 100.5, 99.5, 100.0),    # 2: Low 99.5 <= moved stop 100 -- scratch here
    ])
    result = simulate_exit(df, signal_index=0,
                           plan=_plan(direction="bullish", stop_loss=95.0, tp1=110.0))
    assert result.outcome == "scratch" and result.exit_index == 2


def test_timeout_marks_to_market_at_last_scanned_close():
    # 2w horizon: max_holding_days=14. Sideways drift, never touching
    # stop/target/BE-trigger -> timeout at bar entry+14, r = drift/risk.
    closes = [100.0] + [(99.8, 100.4, 99.4, 99.8)] * 20
    df = make_ohlcv(closes)
    result = simulate_exit(df, signal_index=0,
                           plan=_plan(direction="bullish", stop_loss=95.0, tp1=110.0,
                                      horizon_key="2w"))
    assert result.outcome == "timeout"
    assert result.exit_index == 14                       # entry_index + max_holding_days
    assert result.r_total == pytest.approx((99.8 - 100.0) / 5.0)
    assert result.legs[0]["reason"] == "timeout"


def test_same_bar_stop_and_target_is_conservative_loss():
    # One bar spans BOTH stop and tp1 pre-BE: stop is checked first -> loss.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 94.0, 100.0),    # 1: High >= 110 AND Low <= 95
    ])
    result = simulate_exit(df, signal_index=0,
                           plan=_plan(direction="bullish", stop_loss=95.0, tp1=110.0))
    assert result.outcome == "loss"
    assert result.r_total == pytest.approx(-1.0)


def test_bearish_scratch_mirror():
    # entry 100, stop 105, tp1 90 -> BE trigger = 100 - 0.5*10 = 95.
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 94.0, 95.5),     # 1: Low 94 <= 95 -- BE armed
        (96.0, 100.5, 95.5, 100.2),     # 2: High 100.5 >= moved stop 100 -- scratch
    ])
    result = simulate_exit(df, signal_index=0,
                           plan=_plan(direction="bearish", stop_loss=105.0, tp1=90.0))
    assert result.outcome == "scratch"
    assert result.r_total == pytest.approx(0.0, abs=1e-9)
