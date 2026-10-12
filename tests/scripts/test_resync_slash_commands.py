"""scripts/ops/resync_slash_commands.py (v153 rollback remedy): offline.

A fake bot stands in for discord's Client: no login, no HTTP."""
import asyncio
import inspect
import sys
from pathlib import Path

import discord
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import resync_slash_commands as rs  # noqa: E402


class _FakeTree:
    def __init__(self, calls: list, count: int):
        self._calls = calls
        self._count = count

    async def sync(self):
        self._calls.append("sync")
        return [object()] * self._count


class _FakeBot:
    def __init__(self, count: int = 41, login_error: Exception | None = None):
        self.calls: list[str] = []
        self.tree = _FakeTree(self.calls, count)
        self._login_error = login_error

    async def __aenter__(self):
        self.calls.append("enter")
        return self

    async def __aexit__(self, *exc):
        self.calls.append("close")

    async def login(self, token: str):
        self.calls.append(f"login:{token}")
        if self._login_error is not None:
            raise self._login_error


def test_resync_logs_in_then_syncs_then_closes():
    bot = _FakeBot(41)
    assert asyncio.run(rs.resync(bot, "tok")) == 41
    assert bot.calls == ["enter", "login:tok", "sync", "close"]


def test_resync_closes_the_client_when_login_fails():
    bot = _FakeBot(login_error=discord.LoginFailure("Improper token has been passed."))
    with pytest.raises(discord.LoginFailure):
        asyncio.run(rs.resync(bot, "tok"))
    assert bot.calls == ["enter", "login:tok", "close"]


def test_main_without_a_token_syncs_nothing(monkeypatch, capsys):
    from swingbot import config

    monkeypatch.setattr(config, "TOKEN", "")
    called = []
    monkeypatch.setattr(rs, "resync", lambda *args: called.append(args))
    assert rs.main() == 2
    assert called == []
    assert "DISCORD_TOKEN" in capsys.readouterr().err


def test_main_imports_bot_py_modules_and_prints_the_count(monkeypatch, capsys):
    from swingbot import config
    from swingbot.bot_core import bot
    import swingbot.commands.modules as modules

    imported = []
    monkeypatch.setattr(config, "TOKEN", "tok")
    monkeypatch.setattr(modules, "import_bot_command_modules", lambda: imported.append(1) or ["m"] * 12)
    seen = {}

    async def fake_resync(the_bot, token):
        seen.update(bot=the_bot, token=token)
        return 41

    monkeypatch.setattr(rs, "resync", fake_resync)
    assert rs.main() == 0
    assert imported == [1]
    assert seen == {"bot": bot, "token": "tok"}
    assert "Synced 41 slash command(s) to Discord from 12 command modules." in capsys.readouterr().out


def test_main_reports_a_rejected_login(monkeypatch, capsys):
    from swingbot import config
    import swingbot.commands.modules as modules

    monkeypatch.setattr(config, "TOKEN", "bad")
    monkeypatch.setattr(modules, "import_bot_command_modules", lambda: [])

    async def failing_resync(the_bot, token):
        raise discord.LoginFailure("Improper token has been passed.")

    monkeypatch.setattr(rs, "resync", failing_resync)
    assert rs.main() == 1
    assert "Sync failed: Improper token has been passed." in capsys.readouterr().err


def test_installed_discord_login_sets_the_application_id_sync_needs():
    """tree.sync() raises MissingApplicationID unless login() set it. Pinned
    against the installed discord.py so an upgrade cannot silently break the
    rollback remedy."""
    source = inspect.getsource(discord.Client.login)
    assert "self._connection.application_id = self._application.id" in source
