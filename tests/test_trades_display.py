import ast
import pathlib

from swingbot.commands.trades import _build_trade_detail_embed, format_trade_row
from swingbot.core.presentation import tokens as tk


MODULE = pathlib.Path("swingbot/commands/trades.py")


def _winning_trade():
    return {
        "id": "trade-win", "ticker": "PENNY", "direction": "bullish",
        "status": "win", "entry": 0.12345, "stop_loss": 0.1,
        "take_profit": 0.2, "target2": None, "opened_at": "2026-08-28T12:00:00+00:00",
        "closed_at": "2026-08-28T14:00:00+00:00", "exit_price": 0.2,
        "confidence_label": "High", "confidence_level": 4,
        "strategy": "RSI Pullback", "horizon_key": "2w",
        "risk_reward_ratio": 2.5, "realized_pnl_amount": 15.0,
    }


def test_no_direct_colour_remains():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    hits = [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour")]
    assert not hits, f"discord.Color still set at lines {hits}"


def test_a_winning_trade_embed_takes_the_ramps_green():
    embed = _build_trade_detail_embed(_winning_trade())
    assert embed.color.value == tk.ACCENT_RAMP[5]


def test_trade_detail_embed_carries_shared_chrome():
    embed = _build_trade_detail_embed(_winning_trade())
    assert embed.footer.text and tk.DISCLAIMER in embed.footer.text
    assert embed.timestamp is not None


def test_trade_detail_prices_render_through_the_kit():
    embed = _build_trade_detail_embed(_winning_trade())
    entry = next(field.value for field in embed.fields if field.name == "Entry")
    assert tk.fmt_price(0.12345) in entry


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
