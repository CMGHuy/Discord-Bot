from swingbot.commands.trades import format_trade_row


def _legs_trade(status="open", legs=None):
    return {"id": "t1", "ticker": "AAPL", "direction": "bullish",
            "status": status, "entry": 100.0, "stop_loss": 99.0,
            "take_profit": 100.35, "shares": 100.0, "plan_id": "p1",
            "horizon_key": "4w", "confidence_level": None,
            "realized_pnl_amount": 17.50 if status != "open" else None,
            "legs": legs or []}


def test_half_closed_trade_shows_banked_leg_and_open_runner():
    t = _legs_trade(legs=[{"fraction": 0.5, "exit_price": 100.35,
                           "r": 0.35, "reason": "tp1"}])
    row = format_trade_row(t, currency="$")
    assert "+$17.50 (TP1 50%)" in row and "runner open" in row


def test_closed_two_leg_trade_shows_combined_realized():
    t = _legs_trade(status="win", legs=[
        {"fraction": 0.5, "exit_price": 100.35, "r": 0.35, "reason": "tp1"},
        {"fraction": 0.5, "exit_price": 100.0, "r": 0.0, "reason": "tp1_runner_be"}])
    row = format_trade_row(t, currency="$")
    assert "+$17.50" in row                # summed realized, no recomputation


def test_legacy_trade_row_unchanged():
    t = {"id": "t2", "ticker": "MSFT", "direction": "bullish", "status": "win",
         "entry": 50.0, "exit_price": 52.0, "stop_loss": 48.0,
         "take_profit": 52.0, "realized_pnl_amount": 40.0,
         "horizon_key": "4w", "confidence_level": 4}
    assert "legs" not in format_trade_row(t, currency="$").lower()
