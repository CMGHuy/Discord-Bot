"""v81 execution-feed routing and delivery acknowledgement evidence."""
import asyncio
import types

import pytest

from swingbot import config
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.lifecycle_embeds import notify_plan_events
from tests.planning.test_plan_engine_model import _plan


class FakeChannel:
    def __init__(self):
        self.sent = []
        self.fail = False

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(lifecycle_embeds, "_last_warned", {})
    channels = {"111": FakeChannel(), "222": FakeChannel(), "333": FakeChannel()}
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "222")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "333")
    bot = types.SimpleNamespace(get_channel=lambda channel_id: channels.get(str(channel_id)))
    PlanStore().add(_plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0,
                          tp1=110.0, working_stop=100.0))
    return bot, channels["111"], channels["222"], channels["333"]


def _post(bot, *events):
    return asyncio.run(notify_plan_events(bot, list(events)))


BE = PlanEvent("p1", "be_moved", {"working_stop": 100.0})


def test_feed_pings_and_history_is_silent(wired):
    bot, feed, history, _ = wired
    assert _post(bot, BE) == [Delivery("p1", "stop", 100.0)]
    assert "silent" not in feed.sent[0]
    assert history.sent[0]["silent"] is True
    assert feed.sent[0]["embed"].title == history.sent[0]["embed"].title


def test_history_notifies_when_feed_missing_or_failing(wired, monkeypatch):
    bot, feed, history, _ = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "")
    assert _post(bot, BE) == [Delivery("p1", "stop", 100.0)]
    assert "silent" not in history.sent[0]
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    feed.fail = True
    assert _post(bot, BE) == [Delivery("p1", "stop", 100.0)]
    assert "silent" not in history.sent[1]


def test_no_channel_means_no_delivery_and_later_events_survive(wired):
    bot, feed, history, _ = wired
    feed.fail = history.fail = True
    assert _post(bot, BE) == []
    feed.fail = history.fail = False
    broken = PlanEvent("p1", "stop_moved", {})
    assert _post(bot, broken, BE) == [Delivery("p1", "stop", 100.0)]


def test_fill_uses_feed_not_alerts_and_close_is_notice(wired):
    bot, feed, _, alerts = wired
    fill = PlanEvent("p1", "filled", {"entry_price": 100.0})
    assert _post(bot, fill) == [Delivery("p1", "notice", "filled")]
    assert alerts.sent == []
    assert feed.sent[0]["embed"].title.endswith("— FILLED")
    close = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 94.5,
                       "session": "regular", "notified_stop": 95.0, "bot_stop": 95.0})
    assert _post(bot, close) == [Delivery("p1", "notice", "closed")]


def test_non_feed_events_stay_history_only(wired):
    bot, feed, history, _ = wired
    assert _post(bot, PlanEvent("p1", "pyramid_add", {})) == []
    assert feed.sent == []
    assert len(history.sent) == 1
