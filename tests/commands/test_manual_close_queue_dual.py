"""notify_queue at dual: the file is the truth and the table its shadow, so
both are drained together and the db flip replays nothing (v116)."""
import asyncio
import json

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository

RECORD = {"trade_id": "T1", "ticker": "AAPL"}


@pytest.fixture
def posted(tmp_path, store_db, monkeypatch):
    sent = []

    async def fake_notify(_bot, records):
        sent.extend(records)

    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", fake_notify)
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE",
                        str(tmp_path / "manual_close_notify.json"))
    return sent


def _queue_both(tmp_path):
    (tmp_path / "manual_close_notify.json").write_text(json.dumps([RECORD]))
    NotifyQueueRepository().enqueue(dict(RECORD))


def test_dual_posts_the_file_once_and_drains_the_shadow(tmp_path, posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:dual")
    _queue_both(tmp_path)
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]
    assert NotifyQueueRepository().pending() == 0
    assert not (tmp_path / "manual_close_notify.json").exists()


def test_flipping_to_db_after_a_dual_soak_replays_nothing(tmp_path, posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:dual")
    _queue_both(tmp_path)
    asyncio.run(loops._post_manual_close_queue())
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:db")
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]


def test_the_db_stage_drains_the_table(posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:db")
    NotifyQueueRepository().enqueue(dict(RECORD))
    asyncio.run(loops._post_manual_close_queue())
    # The embeds read the trade as `id`; the table stores it as `trade_id`.
    assert posted == [{"id": "T1", "ticker": "AAPL"}]
