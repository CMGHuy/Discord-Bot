import asyncio
from unittest.mock import AsyncMock

from swingbot.commands.scanning import lifecycle_delivery, loops


def test_watcher_delegates_to_durable_tick(monkeypatch):
    worker = AsyncMock(return_value=dict(attempted=1, acknowledged=0, retried=1, blocked=0))
    bot = object()
    monkeypatch.setattr(loops, "bot", bot)
    monkeypatch.setattr(lifecycle_delivery, "deliver_lifecycle_tick", worker)
    automatic = AsyncMock(side_effect=AssertionError("automatic path must remain separate"))
    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", automatic)
    asyncio.run(loops._post_manual_close_queue())
    worker.assert_awaited_once_with(bot)
    automatic.assert_not_awaited()
    assert not hasattr(loops, "_take_manual_close_queue")
    assert not hasattr(loops, "_with_trade_id_as_id")
