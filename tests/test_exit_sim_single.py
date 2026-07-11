"""Task 21: single-leg exit-walk tests for the shared exit simulator.

Only the win/loss single-leg (scale_out=False) path is in scope here.
Golden fixtures use a market entry (fills at signal bar's close) so the
entry phase is unambiguous, then walk straight to either TP1 (win) or the
stop (loss) with no break-even trigger involved. Scratch/timeout/same-bar
ordering are Task 22's scope, not tested here.
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
