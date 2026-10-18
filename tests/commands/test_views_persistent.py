"""v152 D2: the plan panel survives a restart.

Every plan button is a discord.ui.DynamicItem whose custom_id carries the
plan id (and, for a `!top` panel, the author id), so discord.py can rebuild
the item from the custom_id alone after the process restarts. Pre-v152
alerts carry the old static ids (`plan:chart` ...); LegacyPlanPanel answers
them. No pytest-asyncio here: coroutines run through asyncio.run.
"""
import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands

from swingbot.commands import views
from swingbot.commands.views import (
    FEED_BUTTONS,
    LEGACY_REPLY,
    PLAN_BUTTONS,
    ChartButton,
    LegacyPlanPanel,
    PlanActionView,
    chart_only_view,
    custom_id_for,
    register_persistent_views,
)

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
AUTHOR = 123456789012345678
OTHER = 876543210987654321
#: every DynamicItem the bot registers: the full-alert panel's and the feed's.
ALL_BUTTONS = (*PLAN_BUTTONS, *FEED_BUTTONS)


def _interaction(user_id: int) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _rebuild(button_cls, custom_id: str):
    """What discord.py does on a button press after a restart: fullmatch the
    custom_id against the registered template, then from_custom_id."""
    match = button_cls.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None, custom_id
    return asyncio.run(button_cls.from_custom_id(_interaction(OTHER), MagicMock(), match))


def test_custom_id_carries_the_plan_and_optionally_the_author():
    assert custom_id_for("chart", PID, None) == f"plan:chart:{PID}"
    assert custom_id_for("chart", PID, AUTHOR) == f"plan:chart:{PID}:{AUTHOR}"


def test_every_custom_id_fits_discords_100_char_limit():
    longest = max(len(custom_id_for(cls.ACTION, PID, 10 ** 19)) for cls in ALL_BUTTONS)
    assert longest <= 100


def test_each_button_rebuilds_from_its_custom_id_alone_without_author():
    for cls in ALL_BUTTONS:
        item = _rebuild(cls, custom_id_for(cls.ACTION, PID, None))
        assert isinstance(item, cls)
        assert (item.plan_id, item.author_id) == (PID, None)
        assert item.custom_id == custom_id_for(cls.ACTION, PID, None)


def test_each_button_rebuilds_with_its_author_segment():
    for cls in ALL_BUTTONS:
        item = _rebuild(cls, custom_id_for(cls.ACTION, PID, AUTHOR))
        assert (item.plan_id, item.author_id) == (PID, AUTHOR)


def test_the_top_panel_lock_holds_after_a_rebuild():
    item = _rebuild(ChartButton, custom_id_for("chart", PID, AUTHOR))
    stranger = _interaction(OTHER)
    assert asyncio.run(item.interaction_check(stranger)) is False
    stranger.response.send_message.assert_awaited_once_with("Not your panel.", ephemeral=True)
    assert asyncio.run(item.interaction_check(_interaction(AUTHOR))) is True


def test_an_alert_panel_with_no_author_accepts_anyone_after_a_rebuild():
    item = _rebuild(ChartButton, custom_id_for("chart", PID, None))
    for uid in (AUTHOR, OTHER):
        assert asyncio.run(item.interaction_check(_interaction(uid))) is True


def test_the_legacy_static_ids_match_no_dynamic_template():
    for legacy in ("plan:chart", "plan:breakdown", "plan:watch", "plan:dismiss"):
        assert all(cls.__discord_ui_compiled_template__.fullmatch(legacy) is None
                   for cls in ALL_BUTTONS)


def test_plan_action_view_is_persistent_and_holds_one_button_per_action():
    view = PlanActionView(PID, author_id=None)
    assert view.timeout is None
    assert view.is_persistent()
    assert [type(item) for item in view.children] == list(PLAN_BUTTONS)
    assert [item.custom_id for item in view.children] == [
        custom_id_for(cls.ACTION, PID, None) for cls in PLAN_BUTTONS]


def test_a_malformed_plan_id_posts_an_empty_panel_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="swingbot.commands.views"):
        view = PlanActionView("not-a-uuid", author_id=None)
    assert view.children == []
    assert "persistent custom_id" in caplog.text


def test_chart_only_view_carries_just_the_chart_button():
    view = chart_only_view(PID)
    assert view.timeout is None
    assert [type(item) for item in view.children] == [ChartButton]


def test_legacy_panel_claims_the_four_static_ids_and_is_persistent():
    panel = LegacyPlanPanel()
    assert panel.timeout is None and panel.is_persistent()
    assert sorted(item.custom_id for item in panel.children) == [
        "plan:breakdown", "plan:chart", "plan:dismiss", "plan:watch"]


def test_legacy_chart_breakdown_watch_reply_with_the_predates_line():
    panel = LegacyPlanPanel()
    for custom_id in ("plan:chart", "plan:breakdown", "plan:watch"):
        item = next(i for i in panel.children if i.custom_id == custom_id)
        interaction = _interaction(OTHER)
        asyncio.run(item.callback(interaction))
        interaction.response.send_message.assert_awaited_once_with(LEGACY_REPLY, ephemeral=True)


def test_legacy_dismiss_still_removes_the_panel():
    panel = LegacyPlanPanel()
    item = next(i for i in panel.children if i.custom_id == "plan:dismiss")
    interaction = _interaction(OTHER)
    asyncio.run(item.callback(interaction))
    interaction.response.edit_message.assert_awaited_once_with(view=None)


def test_register_persistent_views_adds_every_dynamic_item_and_the_legacy_panel():
    bot = MagicMock()
    register_persistent_views(bot)
    bot.add_dynamic_items.assert_called_once_with(*PLAN_BUTTONS, *FEED_BUTTONS)
    (legacy,), _ = bot.add_view.call_args
    assert isinstance(legacy, LegacyPlanPanel)


def test_register_persistent_views_is_accepted_by_a_real_bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    register_persistent_views(bot)
    assert any(isinstance(view, LegacyPlanPanel) for view in bot.persistent_views)
    registered = set(bot._connection._view_store._dynamic_items.values())
    assert registered == set(ALL_BUTTONS)


def test_bot_core_setup_hook_registers_the_persistent_views(monkeypatch):
    from swingbot import bot_core
    seen = []
    monkeypatch.setattr(views, "register_persistent_views", seen.append)
    asyncio.run(bot_core.bot.setup_hook())
    assert seen == [bot_core.bot]


def test_button_plan_reads_run_off_the_event_loop():
    for cls in (views.ChartButton, views.BreakdownButton):
        source = inspect.getsource(cls.callback) + inspect.getsource(views._send_chart)
        assert "PlanStore().get(" not in source
        assert "to_thread(_get_plan" in source
