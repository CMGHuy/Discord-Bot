"""v189 A6: `!trades clear history [force]` and `/trades-clear-history force:`
run the archived reset and reply with its description; a refusal or a failed
archive is an error reply."""
import asyncio

import pytest

from swingbot.commands import trades as trades_mod
from swingbot.core.tracking import account_reset

RESULT = account_reset.ResetResult(
    removed_trades=2, removed_plans=1,
    archive_path="/app/data/archives/account-reset-20261023T150000Z.json",
    throttle_multiplier=1.0, throttle_paused=False, kill_on=False,
    base_balance=10_000.0, reset_at="2026-10-23T15:00:00+00:00")
ARCHIVE_FAILED = ("Reset aborted: the archive account-reset-x.json could not be written "
                  "(disk full). Nothing was deleted.")


class _Reply:
    def __init__(self):
        self.sent, self.errors = [], []

    async def send(self, content=None, **kw):
        self.sent.append(content)

    async def send_error(self, text, *, ephemeral=True):
        self.errors.append(text)


def _patch_reset(monkeypatch, outcome):
    calls = []

    def fake(*, force=False, now=None):
        calls.append(force)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(account_reset, "reset_closed_history", fake)
    return calls


def _capture_handler(monkeypatch):
    seen = []

    async def handler(reply, force=False):
        seen.append(force)

    monkeypatch.setattr(trades_mod, "handle_trades_clear_history", handler)
    return seen


@pytest.mark.parametrize("force", [False, True])
def test_the_handler_runs_the_reset_and_replies_with_its_description(monkeypatch, force):
    calls = _patch_reset(monkeypatch, RESULT)
    reply = _Reply()
    asyncio.run(trades_mod.handle_trades_clear_history(reply, force=force))
    assert calls == [force]
    assert reply.sent == [account_reset.describe_reset(RESULT)]
    assert reply.errors == []


@pytest.mark.parametrize("error, text", [
    (account_reset.ResetRefused(account_reset.REFUSED_TEXT), account_reset.REFUSED_TEXT),
    (account_reset.ArchiveFailed(ARCHIVE_FAILED), ARCHIVE_FAILED),
], ids=["refused", "archive-failed"])
def test_a_refusal_or_a_failed_archive_is_an_error_reply(monkeypatch, error, text):
    _patch_reset(monkeypatch, error)
    reply = _Reply()
    asyncio.run(trades_mod.handle_trades_clear_history(reply))
    assert reply.errors == [text]
    assert reply.sent == []


@pytest.mark.parametrize("mode, force", [("", False), ("force", True), ("FORCE", True),
                                         ("forse", False)])
def test_the_prefix_word_force_maps_to_force(monkeypatch, mode, force):
    seen = _capture_handler(monkeypatch)

    async def no_tip(ctx, reply):
        return None

    monkeypatch.setattr(trades_mod, "CtxReply", lambda ctx: object())
    monkeypatch.setattr(trades_mod, "send_prefix_tip", no_tip)
    asyncio.run(trades_mod.trades_clear_history.callback(None, mode))
    assert seen == [force]


def test_the_slash_option_reaches_the_handler(monkeypatch):
    seen = _capture_handler(monkeypatch)
    monkeypatch.setattr(trades_mod, "InteractionReply", lambda interaction: object())
    asyncio.run(trades_mod.slash_trades_clear_history.callback(None, True))
    assert seen == [True]


def test_the_slash_command_describes_its_force_option():
    command = trades_mod.slash_trades_clear_history
    assert command.description == (
        "Archive closed history, then reset realized P&L and drawdown (open trades kept)")
    [param] = command.parameters
    assert (param.name, param.required) == ("force", False)
    assert param.description == "Reset even while the kill switch is tripped (it stays tripped)"
