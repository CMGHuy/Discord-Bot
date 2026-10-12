"""v153 SP3: the app-command error handler on bot.tree."""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands import slash

DENIED = "🚫 You don't have permission to run that command."
GUILD_ONLY = "This command only works in a server."


def _interaction(done: bool = False) -> MagicMock:
    interaction = MagicMock()
    interaction.response.is_done = MagicMock(return_value=done)
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.command.qualified_name = "killswitch"
    return interaction


def test_handler_is_registered_on_the_tree():
    assert bot.tree.on_error is slash.on_app_command_error


@pytest.mark.parametrize("error, text", [
    (app_commands.MissingPermissions(["administrator"]), DENIED),
    (app_commands.NoPrivateMessage(), GUILD_ONLY),
])
def test_check_failures_answer_ephemeral(error, text):
    interaction = _interaction()
    asyncio.run(slash.on_app_command_error(interaction, error))
    interaction.response.send_message.assert_awaited_once_with(text, ephemeral=True)
    interaction.followup.send.assert_not_awaited()


def test_after_a_response_the_answer_is_a_followup():
    interaction = _interaction(done=True)
    asyncio.run(slash.on_app_command_error(
        interaction, app_commands.MissingPermissions(["administrator"])))
    interaction.followup.send.assert_awaited_once_with(DENIED, ephemeral=True)
    interaction.response.send_message.assert_not_awaited()


def test_other_errors_are_logged_and_reraised(caplog):
    interaction = _interaction()
    error = app_commands.AppCommandError("boom")
    with caplog.at_level(logging.ERROR, logger="swingbot.commands.slash"):
        with pytest.raises(app_commands.AppCommandError, match="boom"):
            asyncio.run(slash.on_app_command_error(interaction, error))
    assert "Unhandled slash command error in /killswitch" in caplog.text
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()
