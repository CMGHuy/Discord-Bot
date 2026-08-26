"""Regression coverage for bounded historical !check output."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from swingbot.commands import scanning as scanning_mod


def _trade(number: int) -> dict:
    return {
        "id": f"trade-{number}",
        "ticker": f"T{number:03d}",
        "opened_at": "2026-08-01T09:30:00+00:00",
        "horizon_key": "swing",
        "direction": "bullish",
        "status": "open",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "confidence_level": 3,
        "strategy": "breakout",
    }


def test_historical_check_batches_and_caps_large_result_sets(monkeypatch):
    """A broad date range must not turn hundreds of records into 429 pressure."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    monkeypatch.setattr(
        scanning_mod.trade_log, "get_trades", lambda **_kwargs: [_trade(i) for i in range(300)]
    )

    asyncio.run(scanning_mod._check_historical(ctx, "all", "2026-08-01", "2026-08-31"))

    assert ctx.send.await_count <= 10
    messages = [call.args[0] for call in ctx.send.await_args_list]
    assert all(len(message) <= 1900 for message in messages)
    assert any("showing the first" in message.lower() for message in messages)
