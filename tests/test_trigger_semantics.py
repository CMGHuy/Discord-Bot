import types

from swingbot.core.plan_engine import (
    fill_price,
    pending_expired,
    pending_invalidated,
    trigger_hit,
)


def _plan(**kw):
    base = dict(direction="bullish", trigger_price=100.0, stop_loss=95.0, expiry_bars=5)
    base.update(kw)
    return types.SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# trigger_hit
# ---------------------------------------------------------------------------

def test_trigger_hit_bullish_true_when_high_exceeds_trigger():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=100.5, bar_low=99.0) is True


def test_trigger_hit_bullish_boundary_equality_counts_as_hit():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=100.0, bar_low=99.0) is True


def test_trigger_hit_bullish_false_when_high_below_trigger():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=99.9, bar_low=99.0) is False


def test_trigger_hit_bearish_true_when_low_below_trigger():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=101.0, bar_low=99.5) is True


def test_trigger_hit_bearish_boundary_equality_counts_as_hit():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=101.0, bar_low=100.0) is True


def test_trigger_hit_bearish_false_when_low_above_trigger():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert trigger_hit(plan, bar_high=101.0, bar_low=100.1) is False


# ---------------------------------------------------------------------------
# fill_price
# ---------------------------------------------------------------------------

def test_fill_price_bullish_gap_above_trigger_fills_at_open():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert fill_price(plan, bar_open=101.0) == 101.0


def test_fill_price_bullish_open_below_trigger_fills_at_trigger():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert fill_price(plan, bar_open=99.0) == 100.0


def test_fill_price_bullish_open_equals_trigger():
    plan = _plan(direction="bullish", trigger_price=100.0)
    assert fill_price(plan, bar_open=100.0) == 100.0


def test_fill_price_bearish_gap_below_trigger_fills_at_open():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert fill_price(plan, bar_open=99.0) == 99.0


def test_fill_price_bearish_open_above_trigger_fills_at_trigger():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert fill_price(plan, bar_open=101.0) == 100.0


def test_fill_price_bearish_open_equals_trigger():
    plan = _plan(direction="bearish", trigger_price=100.0)
    assert fill_price(plan, bar_open=100.0) == 100.0


# ---------------------------------------------------------------------------
# pending_expired
# ---------------------------------------------------------------------------

def test_pending_expired_false_before_expiry():
    plan = _plan(expiry_bars=5)
    assert pending_expired(plan, bars_since_created=4) is False


def test_pending_expired_false_at_exact_expiry_boundary():
    plan = _plan(expiry_bars=5)
    assert pending_expired(plan, bars_since_created=5) is False


def test_pending_expired_true_past_expiry():
    plan = _plan(expiry_bars=5)
    assert pending_expired(plan, bars_since_created=6) is True


# ---------------------------------------------------------------------------
# pending_invalidated
# ---------------------------------------------------------------------------

def test_pending_invalidated_bullish_false_above_stop():
    plan = _plan(direction="bullish", stop_loss=95.0)
    assert pending_invalidated(plan, bar_close=95.5) is False


def test_pending_invalidated_bullish_boundary_equality_counts_as_invalidated():
    plan = _plan(direction="bullish", stop_loss=95.0)
    assert pending_invalidated(plan, bar_close=95.0) is True


def test_pending_invalidated_bullish_true_below_stop():
    plan = _plan(direction="bullish", stop_loss=95.0)
    assert pending_invalidated(plan, bar_close=94.5) is True


def test_pending_invalidated_bearish_false_below_stop():
    plan = _plan(direction="bearish", stop_loss=105.0)
    assert pending_invalidated(plan, bar_close=104.5) is False


def test_pending_invalidated_bearish_boundary_equality_counts_as_invalidated():
    plan = _plan(direction="bearish", stop_loss=105.0)
    assert pending_invalidated(plan, bar_close=105.0) is True


def test_pending_invalidated_bearish_true_above_stop():
    plan = _plan(direction="bearish", stop_loss=105.0)
    assert pending_invalidated(plan, bar_close=105.5) is True
