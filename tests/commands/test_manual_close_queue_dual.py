"""The manual-close queue is the notify_queue table (v116)."""
import asyncio

import pytest

from swingbot.commands.scanning import loops
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository

RECORD = {"trade_id": "T1", "ticker": "AAPL"}


@pytest.fixture
def posted(store_db, monkeypatch):
    sent = []

    async def fake_notify(_bot, records):
        sent.extend(records)

    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", fake_notify)
    return sent


def test_the_queue_is_drained_from_the_table(posted):
    NotifyQueueRepository().enqueue(dict(RECORD))
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]
    assert NotifyQueueRepository().pending() == 0
