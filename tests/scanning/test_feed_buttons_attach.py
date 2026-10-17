"""v170 §3 / A7 / A8: the feed panel rides on plan-backed feed messages only.

The v2 ticket mirror and every lifecycle instruction (feed send and its
history copy) carry feed_view; strategy-signal and legacy mirrors and the
history-only status embed never do. A button problem never costs a ping.
No pytest-asyncio: coroutines run through asyncio.run.
"""
import ast
import asyncio
import inspect
import types

import discord
import pytest

from swingbot import config
from swingbot.commands import views
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.lifecycle_embeds import notify_plan_events
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
FEED_ORDER = [views.ChartButton, views.BreakdownButton, views.WatchButton, views.PnlNowButton]
PLAN = types.SimpleNamespace(plan_id=PID, ticker="AAPL")


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


def _types(sent: dict) -> list:
    return [type(item) for item in sent["view"].children]


def _boom(plan_id):
    raise RuntimeError("view broke")


# ------------------------------------------------------------ the feed ticket

@pytest.mark.parametrize("kind", [Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE])
def test_the_v2_ticket_mirror_carries_the_feed_panel(kind):
    simple, embed = FakeChannel(), ui.push_embed(kind, "AAPL", "bullish")
    assert asyncio.run(alerts._mirror(simple, embed, PLAN)) is True
    assert _types(simple.sent[0]) == FEED_ORDER
    assert {k: v for k, v in simple.sent[0].items() if k != "view"} == ui.push_kwargs(embed)


@pytest.mark.parametrize("embed, plan", [
    (ui.push_embed(Kind.STRATEGY_SIGNAL, "AAPL", "bullish"), PLAN),
    (ui.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish"), PLAN),
    (discord.Embed(title="plain"), PLAN),
    (ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish"), None),
])
def test_mirrors_without_a_plan_backed_ticket_carry_no_view(embed, plan):
    simple = FakeChannel()
    assert asyncio.run(alerts._mirror(simple, embed, plan)) is True
    assert "view" not in simple.sent[0]


def test_a_ticket_whose_panel_cannot_be_built_still_mirrors(monkeypatch):
    monkeypatch.setattr(views, "feed_view", _boom)
    simple = FakeChannel()
    embed = ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish")
    assert asyncio.run(alerts._mirror(simple, embed, PLAN)) is True
    assert "view" not in simple.sent[0]


def test_a_ticket_for_a_malformed_plan_id_posts_without_a_view():
    simple = FakeChannel()
    embed = ui.push_embed(Kind.TICKET_PLACE, "AAPL", "bullish")
    asyncio.run(alerts._mirror(simple, embed, types.SimpleNamespace(plan_id="p1", ticker="AAPL")))
    assert "view" not in simple.sent[0]


# ------------------------------------------------------- lifecycle messages

@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
    monkeypatch.setattr(lifecycle_embeds, "_last_warned", {})
    channels = {"111": FakeChannel(), "222": FakeChannel()}
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "222")
    bot = types.SimpleNamespace(get_channel=lambda channel_id: channels.get(str(channel_id)))
    for plan_id in (PID, "p1"):
        PlanStore().add(_plan(plan_id=plan_id, status="ACTIVE", entry_price=100.0,
                              stop_loss=95.0, tp1=110.0, working_stop=100.0))
    return bot, channels["111"], channels["222"]


def _post(bot, *events):
    return asyncio.run(notify_plan_events(bot, list(events)))


def _be(plan_id=PID):
    return PlanEvent(plan_id, "be_moved", {"working_stop": 100.0})


def test_the_feed_send_and_its_history_copy_each_carry_their_own_panel(wired):
    bot, feed, history = wired
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert _types(feed.sent[0]) == FEED_ORDER == _types(history.sent[0])
    assert feed.sent[0]["view"] is not history.sent[0]["view"]
    assert "silent" not in feed.sent[0] and history.sent[0]["silent"] is True


def test_history_notifies_with_the_panel_when_the_feed_is_missing(wired, monkeypatch):
    bot, feed, history = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "")
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert _types(history.sent[0]) == FEED_ORDER and "silent" not in history.sent[0]


def test_the_history_only_status_embed_carries_no_panel(wired):
    bot, feed, history = wired
    assert _post(bot, PlanEvent(PID, "pyramid_add", {})) == []
    assert feed.sent == [] and "view" not in history.sent[0]


def test_a_malformed_plan_id_or_a_broken_panel_still_delivers_without_a_view(wired, monkeypatch):
    bot, feed, history = wired
    assert _post(bot, _be("p1")) == [Delivery("p1", "stop", 100.0)]
    monkeypatch.setattr(views, "feed_view", _boom)
    assert _post(bot, _be()) == [Delivery(PID, "stop", 100.0)]
    assert all("view" not in sent for sent in feed.sent + history.sent)


def test_core_never_imports_commands_at_module_level():
    tree = ast.parse(inspect.getsource(lifecycle_embeds))
    names = [node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)]
    names += [alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names]
    assert not [name for name in names if name.startswith("swingbot.commands")]
    assert "from swingbot.commands.views import feed_view" in inspect.getsource(
        lifecycle_embeds._feed_view)
