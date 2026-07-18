from swingbot.core.analytics.metrics import win_rate, expectancy_r, r_multiple, profit_factor


def _win():
    return {"status": "win", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0, "realized_pnl_amount": 80.0}


def _loss():
    return {"status": "loss", "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
            "exit_price": 106.0, "realized_pnl_amount": -40.0}


def _still_open_unsized():
    # No exit_price/stop -- must be skipped everywhere without raising,
    # per the Global Constraint "missing keys degrade gracefully".
    return {"status": "open", "direction": "bullish", "entry": 100.0}


def test_r_multiple_bullish_win_and_bearish_loss():
    assert r_multiple(_win()) == 0.8      # (104-100)/(100-95)
    assert r_multiple(_loss()) == -1.2    # (100-106)/(100-105) = -6/-5... sign-adjusted: -1.2


def test_r_multiple_none_on_zero_risk_or_missing_fields():
    assert r_multiple({"entry": 100.0, "stop_loss": 100.0, "exit_price": 105.0,
                       "direction": "bullish"}) is None
    assert r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish"}) is None


def test_expectancy_and_win_rate_and_profit_factor():
    closed = [_win(), _loss(), _still_open_unsized()]
    assert win_rate(closed) == 50.0
    assert round(expectancy_r(closed), 4) == -0.2   # mean(0.8, -1.2); open trade excluded (no exit_price)
    assert profit_factor(closed) == 2.0              # 80 / 40


def test_win_rate_and_expectancy_empty_or_no_losses():
    assert win_rate([]) is None
    assert expectancy_r([]) is None
    assert profit_factor([_win()]) is None  # no losing amount -- undefined, not infinite


def test_r_multiple_none_on_missing_direction():
    """r_multiple gracefully returns None when direction key is missing,
    rather than silently defaulting to bearish formula."""
    trade_no_direction = {"entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0}
    assert r_multiple(trade_no_direction) is None


def test_r_multiple_none_on_invalid_direction():
    """r_multiple gracefully returns None when direction has an invalid
    value (misspelled, wrong enum, etc), rather than silently defaulting
    to bearish formula."""
    trade_invalid_direction = {"direction": "long", "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0}
    assert r_multiple(trade_invalid_direction) is None
