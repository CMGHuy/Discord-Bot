"""Harness self-test cases: tiny handlers that exercise every Reply member,
so the parametrised parity tests are proven before any module uses them."""
import io
import sys

import discord

from tests.commands.reply_harness import ParityCase

_THIS = sys.modules[__name__]


class SelftestView(discord.ui.View):
    pass


def _source() -> str | None:
    return "ok"


async def _hello(reply):
    await reply.send("hello")


async def _embed_file_view(reply):
    embed = discord.Embed(title="Selftest", description="embed body")
    file = discord.File(io.BytesIO(b"png"), filename="chart.png")
    await reply.send("chart", embed=embed, file=file, view=SelftestView())


async def _ephemeral_and_silent(reply):
    await reply.send("only you", ephemeral=True)
    await reply.send("quiet", silent=True)


async def _progress(reply):
    await reply.defer()
    handle = await reply.send("working… 0%")
    await handle.edit(content="working… 50%")
    await handle.edit(content="done")


async def _chunks(reply):
    await reply.send_chunks("x" * 4500)


async def _refuse(reply):
    await reply.send_error("⚠️ nope")


async def _lookup(reply):
    value = _THIS._source()
    if value is None:
        await reply.send_error("⚠️ source down")
        return
    await reply.send(f"value: {value}")


def _source_ok(monkeypatch):
    monkeypatch.setattr(_THIS, "_source", lambda: "ok")


def _source_down(monkeypatch):
    monkeypatch.setattr(_THIS, "_source", lambda: None)


CASES = [
    ParityCase("selftest-hello", _hello),
    ParityCase("selftest-embed-file-view", _embed_file_view),
    ParityCase("selftest-ephemeral-silent", _ephemeral_and_silent, expect="multi_send"),
    ParityCase("selftest-progress-edit", _progress, expect="edit"),
    ParityCase("selftest-chunks", _chunks, expect="multi_send"),
    ParityCase("selftest-refuse", _refuse, expect="error"),
    ParityCase("selftest-lookup", _lookup, stub=_source_ok, fail_stub=_source_down),
]
