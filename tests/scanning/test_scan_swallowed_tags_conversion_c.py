"""v148 OH11: lifecycle_embeds, short_run, outlook_run, progress_store count swallowed errors."""
import asyncio
import types

import pytest

from swingbot import config
from swingbot.core.db.repositories import scan_progress
from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import lifecycle_embeds, outlook_run, progress_store, short_run


@pytest.fixture(autouse=True)
def _clean():
    sw.reset()
    yield
    sw.reset()


def _boom(*a, **k):
    raise RuntimeError("probe")


async def _aboom(*a, **k):
    raise RuntimeError("probe")


def test_converted_handlers_count_under_their_tags(monkeypatch):
    monkeypatch.setattr(outlook_run.data_store, "load_from_disk", _boom)
    assert outlook_run._hourly("AAPL") is None
    monkeypatch.setattr(short_run, "fit_trendline", _boom)
    assert short_run._fit_trendline(object(), types.SimpleNamespace(entry=1.0), {}, "bullish") is None
    monkeypatch.setattr(scan_progress, "scan_progress_repo", _boom)
    assert progress_store._read_row() is None
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "1")
    bot = types.SimpleNamespace(get_channel=lambda _id: None, fetch_channel=_aboom)
    assert asyncio.run(lifecycle_embeds.notify_near_close(bot, [{"trade": {}}])) is None
    snap = sw.snapshot()
    for tag in ("scan.outlook_run.hourly", "scan.short_run.fit_trendline",
                "scan.progress_store.read", "scan.notify_near_close.channel"):
        assert snap[tag]["count"] == 1 and snap[tag]["last_error"] == "RuntimeError: probe", snap
