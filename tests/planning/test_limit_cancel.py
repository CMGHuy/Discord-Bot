"""v131: strict trade-through fills and the pre-fill cancel for a resting buy limit."""
import pytest

from swingbot.core.planning import lifecycle
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

SIGNAL = (101.5, 102.0, 101.0, 101.5)    # bar t: the arming bar
ABOVE = (101.0, 101.5, 100.5, 101.0)     # stays above the 100 limit and under the 105 cancel
LIMIT, STOP, TP1, CANCEL = 100.0, 98.0, 103.0, 105.0


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="limit", trigger_price=LIMIT, entry_price=None, expiry_bars=5,
        stop_loss=STOP, tp1=TP1, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=3.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
        limit_cancel_level=CANCEL, limit_strict_fill=True,
    )
    base.update(kw)
    return TradePlanV2(**base)


def _df(*bars):
    return make_ohlcv([SIGNAL, *bars])


def test_an_exact_touch_does_not_fill():
    df = _df((100.5, 101.0, 100.0, 100.6), *[ABOVE] * 6)
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


def test_a_trade_through_fills_at_the_limit():
    df = _df((100.5, 101.0, 99.9, 100.6), (101.0, 103.2, 100.8, 103.0))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_index, res.entry_price, res.exit_index) == ("win", 1, 100.0, 2)
    assert res.r_total == pytest.approx(1.5)


def test_a_gap_down_fills_at_the_open_and_r_is_measured_from_the_fill():
    df = _df((99.5, 99.8, 99.0, 99.6), (100.0, 103.2, 99.8, 103.0))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_price) == ("win", 99.5)
    assert res.r_total == pytest.approx((TP1 - 99.5) / (99.5 - STOP), abs=1e-3)


def test_a_new_high_before_any_fill_cancels():
    df = _df(ABOVE, (104.0, 105.5, 102.0, 105.2), (100.5, 101.0, 99.0, 99.5))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.cancel_reason, res.entry_index) == ("not_triggered", "cancelled", None)


def test_a_high_equal_to_the_cancel_level_does_not_cancel():
    df = _df((104.0, 105.0, 102.0, 104.5), (100.5, 101.0, 99.5, 100.2), (100.2, 103.5, 100.0, 103.2))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_index) == ("win", 2)


def test_the_same_bar_new_high_and_trade_through_is_a_fill():
    df = _df((101.0, 105.5, 99.8, 104.0), (104.0, 104.5, 103.5, 104.2))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.entry_index, res.entry_price, res.outcome) == (1, 100.0, "win")


def test_the_same_bar_new_high_and_fill_still_takes_the_fill_bar_stop():
    df = _df((101.0, 105.5, 97.5, 98.5), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)


def test_expiry_without_a_fill():
    df = _df(*[ABOVE] * 5, (100.0, 100.2, 95.0, 96.0))   # the trade-through is bar t+6
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


def test_a_fill_at_or_beyond_the_stop_scores_a_scratch():
    df = _df((97.5, 98.0, 97.0, 97.8), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_price, res.r_total) == ("scratch", 97.5, 0.0)
    assert res.legs[0]["reason"] == "gap_through_stop"


def test_a_stop_touch_on_the_fill_bar_is_a_full_loss():
    df = _df((100.5, 100.8, 97.9, 98.5), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)
    assert res.legs[0]["exit_price"] == STOP


def test_the_target_is_not_checked_on_the_fill_bar():
    df = _df((100.5, 103.5, 99.9, 103.2), *[ABOVE] * 3)
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert res.entry_index == 1 and res.outcome != "win"


def test_a_plan_without_a_cancel_level_keeps_the_v113_rules():
    """The v113 fade's limit: touch fills, never cancels, reason-less no-fill."""
    plain = _plan(limit_cancel_level=None, limit_strict_fill=False)
    touch = _df((100.5, 101.0, 100.0, 100.6), (101.0, 103.2, 100.8, 103.0))
    assert simulate_exit(touch, 0, plain, scale_out=False).entry_price == 100.0
    run_away = _df((104.0, 106.0, 102.0, 105.5), *[ABOVE] * 5)
    res = simulate_exit(run_away, 0, plain, scale_out=False)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def test_truncating_after_the_cancel_bar_changes_nothing():
    full = _df(ABOVE, (104.0, 105.5, 102.0, 105.2), (100.5, 101.0, 99.0, 99.5))
    a = simulate_exit(full, 0, _plan(), scale_out=True)
    b = simulate_exit(full.iloc[:3], 0, _plan(), scale_out=True)
    assert (a.outcome, a.cancel_reason) == (b.outcome, b.cancel_reason)


def test_lifecycle_helpers():
    strict, plain = _plan(), _plan(limit_cancel_level=None, limit_strict_fill=False)
    assert not lifecycle.limit_hit(strict, 101.0, 100.0) and lifecycle.limit_hit(strict, 101.0, 99.99)
    assert lifecycle.limit_hit(plain, 101.0, 100.0)
    assert lifecycle.limit_cancelled(strict, 105.01, 101.0)
    assert not lifecycle.limit_cancelled(strict, 105.0, 101.0)
    assert not lifecycle.limit_cancelled(plain, 999.0, 101.0)
    short = _plan(direction="bearish", trigger_price=100.0, stop_loss=102.0, tp1=97.0,
                  limit_cancel_level=95.0)
    assert not lifecycle.limit_hit(short, 100.0, 99.0) and lifecycle.limit_hit(short, 100.01, 99.0)
    assert lifecycle.limit_cancelled(short, 99.0, 94.99) and not lifecycle.limit_cancelled(short, 99.0, 95.0)
