"""v152 D1: /notify -- which plan updates mention the caller.

The command is registered explicitly by importing swingbot.commands.notify
(see test_slash_commands.py for why under -n 4). Prefs are real rows on the
per-worker test Postgres. No pytest-asyncio: coroutines run through asyncio.run.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from discord import app_commands

import swingbot.commands.notify as notify
from swingbot.bot_core import bot
from swingbot.commands.scanning.follow_notify import EVENT_LABELS, NOTIFY_EVENTS
from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo

USER = 123456789012345678


def _interaction(user_id: int = USER) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _choice(value: str) -> app_commands.Choice:
    return app_commands.Choice(name=value, value=value)


def _run(**kwargs) -> str:
    interaction = _interaction()
    asyncio.run(notify.slash_notify.callback(interaction, **kwargs))
    interaction.response.send_message.assert_awaited_once()
    args, sent = interaction.response.send_message.call_args
    assert sent.get("ephemeral") is True
    return args[0] if args else sent["content"]


def _line(text: str, event: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"• `{event}`"))


def test_notify_is_registered_with_its_three_options():
    command = bot.tree.get_command("notify")
    assert command is not None
    assert {p.name for p in command.parameters} == {"event", "enabled", "watch_mode"}
    assert [c.value for c in command.get_parameter("event").choices] == [*NOTIFY_EVENTS, "all"]
    assert [c.value for c in command.get_parameter("watch_mode").choices] == ["mention", "silent"]
    assert all(not p.required for p in command.parameters)


def test_the_summary_lists_every_announced_event_with_its_label():
    text = notify._notify_summary({})
    for event in NOTIFY_EVENTS:
        assert EVENT_LABELS[event] in _line(text, event)
    assert "not advice" in text
    assert "only when a plan has a Following follower" in text
    assert "Watch-only plans: mention." in text


def test_the_summary_shows_the_defaults():
    text = notify._notify_summary({})
    assert _line(text, "near_stop").endswith("Following: on · Watch: off")
    assert _line(text, "expired").endswith("Following: on · Watch: off")
    for event in ("tp1", "tp2", "stopped"):
        assert _line(text, event).endswith("Following: on · Watch: on")
    assert _line(text, "closed_other").endswith("Following: on · Watch: never")


def test_the_summary_shows_a_toggle_and_silent_mode():
    text = notify._notify_summary({"tp2": False, "near_stop": True, "watch_mode": "silent"})
    assert _line(text, "tp2").endswith("Following: off · Watch: off")
    assert _line(text, "near_stop").endswith("Following: on · Watch: off")   # silent drops Watch
    assert "Watch-only plans: silent." in text


def test_no_arguments_shows_the_summary_and_stores_nothing():
    text = _run()
    assert _line(text, "tp1")
    assert notify_prefs_repo().prefs(USER) == {}


def test_one_event_toggles_for_the_caller_only():
    text = _run(event=_choice("near_stop"), enabled=True)
    assert notify_prefs_repo().prefs(USER).get("near_stop") is True
    assert notify_prefs_repo().prefs(USER + 1) == {}
    assert _line(text, "near_stop").endswith("Following: on · Watch: on")


def test_all_sets_every_event():
    _run(event=_choice("all"), enabled=False)
    prefs = notify_prefs_repo().prefs(USER)
    assert all(prefs.get(event) is False for event in NOTIFY_EVENTS)


def test_watch_mode_is_stored_and_can_ride_with_a_toggle():
    text = _run(event=_choice("tp1"), enabled=False, watch_mode=_choice("silent"))
    prefs = notify_prefs_repo().prefs(USER)
    assert prefs.get("watch_mode") == "silent" and prefs.get("tp1") is False
    assert "Watch-only plans: silent." in text


def test_a_half_specified_toggle_changes_nothing():
    for kwargs in ({"event": _choice("tp1")}, {"enabled": True}):
        text = _run(**kwargs)
        assert "together" in text
    assert notify_prefs_repo().prefs(USER) == {}


def test_a_store_failure_replies_instead_of_raising(monkeypatch):
    def broken(*args):
        raise RuntimeError("db down")

    monkeypatch.setattr(notify, "_apply_notify_change", broken)
    assert "could not" in _run(event=_choice("tp1"), enabled=True).lower()
