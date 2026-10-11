"""
Shared slash-command (/command) building blocks.

Since v153 every slash command lives next to its prefix (!) twin, in the
same module, and both call one shared handle_<name>(reply, ...) handler
(swingbot/commands/reply.py). This module keeps only what several of them
share: the choice lists, and the bot.tree error handler for app-command
check failures. It must never import a command module (they import it).

The tree is synced to Discord once per process start, in on_ready
(swingbot/commands/scanning/loops.py).
"""
import logging

import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.core.market.strategy import live_horizons

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Choice lists
# ──────────────────────────────────────────────

HORIZON_CHOICES = [app_commands.Choice(name=k, value=k) for k in live_horizons()] + [
    app_commands.Choice(name="all", value="all")
]

STRATEGY_CHOICES = [
    app_commands.Choice(name="All strategies",    value="all"),
    app_commands.Choice(name="EMA Crossover",     value="ema"),
    app_commands.Choice(name="VWAP",              value="vwap"),
    app_commands.Choice(name="Fibonacci",         value="fib"),
    app_commands.Choice(name="Support/Resistance",value="sr"),
    app_commands.Choice(name="RSI",               value="rsi"),
    app_commands.Choice(name="MACD",              value="macd"),
    app_commands.Choice(name="Elliott Wave",      value="elliott"),
    app_commands.Choice(name="MA Ribbon",         value="ribbon"),
    app_commands.Choice(name="Break & Retest",    value="bnr"),
    app_commands.Choice(name="RSI Divergence",    value="rsidiv"),
    app_commands.Choice(name="Volume Profile",    value="volprofile"),
]

TRADE_FILTER_CHOICES = [
    app_commands.Choice(name="All",  value="all"),
    app_commands.Choice(name="Open", value="open"),
    app_commands.Choice(name="Win",  value="win"),
    app_commands.Choice(name="Loss", value="loss"),
]

STATUS_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")]
# v32 Task 11: tier (A/B/C) retired in favour of confidence level (1-5).
LEVEL_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "1", "2", "3", "4", "5")]
PERIOD_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("7d", "30d", "90d", "ytd", "all")]


# ──────────────────────────────────────────────
# App-command errors (v153 SP3)
# ──────────────────────────────────────────────

# Check failures get a one-line ephemeral answer, matching the prefix side's
# on_command_error (bot_core.py); anything else is logged and re-raised.
APP_CHECK_REPLIES: dict[type, str] = {
    app_commands.MissingPermissions: "🚫 You don't have permission to run that command.",
    app_commands.NoPrivateMessage: "This command only works in a server.",
}


def _check_reply(error: Exception) -> str | None:
    for kind, text in APP_CHECK_REPLIES.items():
        if isinstance(error, kind):
            return text
    return None


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError) -> None:
    text = _check_reply(error)
    if text is None:
        name = getattr(interaction.command, "qualified_name", "?")
        log.error("Unhandled slash command error in /%s: %s", name, error, exc_info=error)
        raise error
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
