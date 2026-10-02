"""v111 §3: the hourly healthcheck cleanup no longer swallows every error.
404 (already gone) is DEBUG, any other Discord HTTP error is WARNING with the
traceback, and a non-HTTP error is a bug that propagates."""
import asyncio
import logging
from types import SimpleNamespace

import discord
import pytest

from swingbot.commands.scanning import presence


def _http_error(cls, status):
    return cls(SimpleNamespace(status=status, reason="x"), "boom")


class _Msg:
    id = 42

    def __init__(self, exc=None):
        self.exc = exc

    async def delete(self):
        if self.exc is not None:
            raise self.exc


def _records(caplog):
    return [r for r in caplog.records if r.name == presence.log.name]


def test_a_message_already_gone_is_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg(_http_error(discord.NotFound, 404))))
    [record] = _records(caplog)
    assert record.levelno == logging.DEBUG


def test_any_other_http_failure_is_a_warning_with_traceback(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg(_http_error(discord.Forbidden, 403))))
    [record] = _records(caplog)
    assert record.levelno == logging.WARNING and record.exc_info is not None


def test_a_successful_delete_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger=presence.log.name):
        asyncio.run(presence._delete_healthcheck(_Msg()))
    assert _records(caplog) == []


def test_a_non_http_error_is_not_swallowed():
    with pytest.raises(RuntimeError):
        asyncio.run(presence._delete_healthcheck(_Msg(RuntimeError("bug"))))
