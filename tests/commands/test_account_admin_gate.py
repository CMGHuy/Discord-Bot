"""v187 D1: the eight account setters answer only to server administrators.

Prefix: `Command.invoke` runs `can_run` (and so the has_permissions check)
before the callback, so a refused invoke never reaches the setter. Slash:
the checks are predicates on `interaction.permissions`, run by discord.py
before the callback. `!account` / `/account show` stay open.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from swingbot import bot_core
from swingbot.commands import account as account_mod
from swingbot.commands.slash import APP_CHECK_REPLIES

DENIED = "🚫 You don't have permission to run that command."

# (prefix command, its slash twin, the setter name it calls)
GATED = [
    (account_mod.account_balance, account_mod.slash_account_balance, "set_balance"),
    (account_mod.account_risk, account_mod.slash_account_risk, "set_risk_pct"),
    (account_mod.account_maxpositions, account_mod.slash_account_maxpositions, "set_max_open_positions"),
    (account_mod.account_sizing, account_mod.slash_account_sizing, "set_sizing_mode"),
    (account_mod.account_positionpct, account_mod.slash_account_positionpct, "set_position_pct"),
    (account_mod.account_maxpositionpct, account_mod.slash_account_maxpositionpct, "set_max_position_pct"),
    (account_mod.account_maxposition, account_mod.slash_account_maxposition,
     "set_max_position_value_absolute"),
    (account_mod.account_maxrisk, account_mod.slash_account_maxrisk, "set_max_risk_amount_absolute"),
]
_IDS = [prefix.qualified_name for prefix, _slash, _setter in GATED]


def _ctx(permissions: discord.Permissions) -> MagicMock:
    ctx = MagicMock()
    ctx.permissions = permissions
    ctx.bot.can_run = AsyncMock(return_value=True)   # the bot registers no global checks
    return ctx


def _interaction(permissions: discord.Permissions) -> MagicMock:
    interaction = MagicMock()
    interaction.permissions = permissions
    return interaction


def _spy_setters(monkeypatch) -> list:
    calls = []
    for _prefix, _slash, setter in GATED:
        monkeypatch.setattr(account_mod, setter,
                            lambda *a, _name=setter, **k: calls.append(_name) or {})
    return calls


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_prefix_setter_refuses_a_non_admin_and_saves_nothing(prefix, slash, setter, monkeypatch):
    calls = _spy_setters(monkeypatch)
    with pytest.raises(commands.MissingPermissions):
        asyncio.run(prefix.invoke(_ctx(discord.Permissions.none())))
    assert calls == []


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_prefix_setter_admits_an_administrator(prefix, slash, setter):
    assert asyncio.run(prefix.can_run(_ctx(discord.Permissions(administrator=True)))) is True


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_slash_setter_refuses_a_non_admin(prefix, slash, setter):
    assert slash.checks, f"/{slash.qualified_name} has no checks"
    with pytest.raises(app_commands.MissingPermissions):
        for check in slash.checks:
            check(_interaction(discord.Permissions.none()))


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_slash_setter_admits_an_administrator(prefix, slash, setter):
    admin = _interaction(discord.Permissions(administrator=True))
    assert all(check(admin) for check in slash.checks)


def test_account_group_carries_no_default_permissions():
    # discord.py allows default_permissions only on top-level commands, and the
    # group holds the read-only `show` -- the subcommand checks are the gate.
    assert account_mod.account_group.default_permissions is None


def test_read_only_account_views_stay_open_to_a_non_admin():
    member = discord.Permissions.none()
    assert asyncio.run(account_mod.account_cmd.can_run(_ctx(member))) is True
    assert account_mod.slash_account_show.checks == []


def test_prefix_refusal_uses_the_existing_permission_reply():
    sent = []

    class _Ctx:
        command = None

        async def send(self, content=None, **kw):
            sent.append(content)

    asyncio.run(bot_core.on_command_error(_Ctx(), commands.MissingPermissions(["administrator"])))
    assert sent == [DENIED]


def test_slash_refusal_uses_the_existing_ephemeral_reply():
    assert APP_CHECK_REPLIES[app_commands.MissingPermissions] == DENIED
