from types import SimpleNamespace

from swingbot.commands.history import _format_generated_plan


def test_format_generated_plan_timeout_line_text():
    """The timeout line's f-string has no {} placeholders -- the f prefix
    was a no-op. Pin the literal text so a future edit can't silently
    reintroduce a missing placeholder either."""
    trade = SimpleNamespace(direction="bullish", outcome="timeout",
                             r_multiple=None, exit_date=None, holding_days=None,
                             entry_date="2026-08-20", entry=100.0,
                             stop_loss=99.0, take_profit=102.0)
    line = _format_generated_plan("RSI", "4w", trade, "$")
    assert "→ ⏳ timed out (no exit within max hold)" in line
