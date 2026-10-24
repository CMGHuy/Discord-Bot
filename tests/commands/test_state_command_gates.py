"""v187 D1: every command in the account and trades modules is either
read-only (allowlisted here) or answers only to server administrators.

Driven by the READ-ONLY allowlist, not by a list of state-changing commands:
a command added to either module is gated by default -- forget the gate and
this test fails until the command is gated or deliberately allowlisted.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from swingbot.bot_core import bot
from swingbot.commands import modules

modules.import_bot_command_modules()

GATED_MODULES = ("swingbot.commands.account", "swingbot.commands.trades")
READ_ONLY_COMMANDS = frozenset({
    # prefix (qualified_name): the group callbacks `account`, `trades`, `trade` are the read-only views
    "account", "trades", "trade", "tradecharts", "performance", "pnl", "summary",
    # slash (qualified_name)
    "account show", "trade show",
})   # "trades", "tradecharts", "performance", "pnl", "summary" are shared prefix/slash names

# Every permission except administrator: a has_permissions(administrator=True)
# check refuses it, a check on any lesser permission would let it through.
ALL_BUT_ADMIN = discord.Permissions.all()
ALL_BUT_ADMIN.administrator = False


def _is_admin_gated(cmd) -> bool:
    return any("has_permissions" in getattr(check, "__qualname__", "") for check in cmd.checks)


def _prefix_commands() -> list:
    return [c for c in bot.walk_commands() if c.callback.__module__ in GATED_MODULES]


def _slash_commands() -> list:
    return [c for c in bot.tree.walk_commands()
            if isinstance(c, app_commands.Command) and c.callback.__module__ in GATED_MODULES]


def _violations(cmds) -> list[str]:
    return sorted(c.qualified_name for c in cmds
                  if c.qualified_name not in READ_ONLY_COMMANDS and not _is_admin_gated(c))


def _gated(cmds) -> list:
    return [c for c in cmds if c.qualified_name not in READ_ONLY_COMMANDS]


def _ctx(permissions: discord.Permissions) -> MagicMock:
    ctx = MagicMock()
    ctx.permissions = permissions
    ctx.bot.can_run = AsyncMock(return_value=True)   # the bot registers no global checks
    return ctx


def _interaction(permissions: discord.Permissions) -> MagicMock:
    interaction = MagicMock()
    interaction.permissions = permissions
    return interaction


def test_every_prefix_command_is_read_only_or_admin_gated():
    assert _violations(_prefix_commands()) == []


def test_every_slash_command_is_read_only_or_admin_gated():
    assert _violations(_slash_commands()) == []


def test_the_checker_catches_an_ungated_command():
    fake = SimpleNamespace(qualified_name="trades nuke", checks=[])
    assert _violations([fake]) == ["trades nuke"]


def test_every_allowlisted_name_is_registered_and_open():
    cmds = _prefix_commands() + _slash_commands()
    names = {c.qualified_name for c in cmds}
    assert READ_ONLY_COMMANDS <= names, sorted(READ_ONLY_COMMANDS - names)
    assert [c.qualified_name for c in cmds
            if c.qualified_name in READ_ONLY_COMMANDS and _is_admin_gated(c)] == []


def test_the_expected_commands_are_gated():
    gated = {c.qualified_name for c in _gated(_prefix_commands())}
    assert {"trades clear", "trades clear history", "trade delete", "account risk"} <= gated
    gated = {c.qualified_name for c in _gated(_slash_commands())}
    assert {"trades-clear", "trades-clear-history", "trade delete", "account balance"} <= gated


@pytest.mark.parametrize("cmd", _gated(_prefix_commands()), ids=lambda c: c.qualified_name)
def test_gated_prefix_command_needs_administrator_itself(cmd):
    with pytest.raises(commands.MissingPermissions):
        asyncio.run(cmd.can_run(_ctx(ALL_BUT_ADMIN)))
    assert asyncio.run(cmd.can_run(_ctx(discord.Permissions(administrator=True)))) is True


@pytest.mark.parametrize("cmd", _gated(_slash_commands()), ids=lambda c: c.qualified_name)
def test_gated_slash_command_needs_administrator_itself(cmd):
    with pytest.raises(app_commands.MissingPermissions):
        for check in cmd.checks:
            check(_interaction(ALL_BUT_ADMIN))
    admin = _interaction(discord.Permissions(administrator=True))
    assert all(check(admin) for check in cmd.checks)


def test_only_the_two_top_level_wipes_are_hidden_from_non_admins():
    from swingbot.commands import trades as trades_mod

    admin = discord.Permissions(administrator=True)
    assert trades_mod.slash_trades_clear.default_permissions == admin
    assert trades_mod.slash_trades_clear_history.default_permissions == admin
    assert trades_mod.trade_group.default_permissions is None   # holds the read-only `show`
