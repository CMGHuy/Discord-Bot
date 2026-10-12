"""Offline fakes and the reply-parity runner (v153 SP1).

Every handler answers through a `Reply`. This module drives one handler
through both implementations -- `CtxReply(FakeContext)` and
`InteractionReply(FakeInteraction)` -- and records what each surface sent
into one normalised event list:

    (kind, content, embed.to_dict(), file names, view type name, ephemeral)

`kind` is "send", "edit" or "defer". No gateway, no HTTP.

Module tasks add a `tests/commands/parity_cases/<module>.py` whose `CASES`
list holds `ParityCase`s; `all_cases()` collects them for the parametrised
tests in `test_reply_parity.py`. A case's `stub` must be idempotent: the
handler runs twice (Context first, then Interaction) under one monkeypatch.
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest

from swingbot.commands.reply import CtxReply, InteractionReply

Event = tuple[str, "str | None", "dict | None", tuple[str, ...], "str | None", bool]

EXPECT_KINDS = ("send", "edit", "multi_send", "error")


def _reject_none(method: str, kw: dict) -> None:
    """discord.py's Webhook.send / send_message reject view=None, file=None."""
    bad = sorted(k for k, v in kw.items() if v is None)
    if bad:
        raise TypeError(f"{method} got None for {bad}; Reply must drop None kwargs")


def _file_names(kw: dict) -> tuple[str, ...]:
    files = []
    if kw.get("file") is not None:
        files.append(kw["file"])
    files.extend(kw.get("files") or [])
    files.extend(kw.get("attachments") or [])
    return tuple(getattr(f, "filename", str(f)) for f in files)


def make_event(kind: str, content: Any, kw: dict) -> Event:
    embed = kw.get("embed")
    view = kw.get("view")
    return (
        kind,
        content,
        embed.to_dict() if embed is not None else None,
        _file_names(kw),
        type(view).__name__ if view is not None else None,
        bool(kw.get("ephemeral", False)),
    )


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id
        self.name = f"user{user_id}"
        self.display_name = self.name
        self.mention = f"<@{user_id}>"

    def __str__(self) -> str:
        return self.name


class FakeMessage:
    """The handle `send` returns; `edit` records an "edit" event."""

    def __init__(self, events: list, content: Any = None, message_id: int = 0):
        self._events = events
        self.content = content
        self.id = message_id
        self.edits: list[dict] = []

    async def edit(self, **kw):
        self.edits.append(kw)
        self._events.append(make_event("edit", kw.get("content"), kw))
        if "content" in kw:
            self.content = kw["content"]
        return self


class FakeChannel:
    def __init__(self, events: list, channel_id: int, calls: list):
        self._events = events
        self.id = channel_id
        self.name = f"channel{channel_id}"
        self.calls = calls

    async def send(self, content=None, **kw):
        _reject_none("channel.send", kw)
        self.calls.append("channel.send")
        self._events.append(make_event("send", content, kw))
        return FakeMessage(self._events, content, len(self._events))


class FakeContext:
    """Stands in for `commands.Context`. `qualified_name=None` -> `command` is None."""

    def __init__(self, events: list, *, author_id: int = 1, channel_id: int = 10,
                 qualified_name: str | None = None):
        self.events = events
        self.calls: list[str] = []
        self.author = FakeUser(author_id)
        self.channel = FakeChannel(events, channel_id, self.calls)
        self.command = _FakeCommand(qualified_name) if qualified_name else None

    async def send(self, content=None, **kw):
        _reject_none("ctx.send", kw)
        self.calls.append("ctx.send")
        self.events.append(make_event("send", content, kw))
        return FakeMessage(self.events, content, len(self.events))


class _FakeCommand:
    def __init__(self, qualified_name: str):
        self.qualified_name = qualified_name


class _FakeResponse:
    def __init__(self, owner: "FakeInteraction"):
        self._owner = owner
        self._done = False

    def is_done(self) -> bool:
        return self._done

    def _claim(self, method: str) -> None:
        if self._done:
            raise RuntimeError(f"{method}: interaction already responded to")
        self._done = True
        self._owner.calls.append(method)

    async def send_message(self, content=None, **kw):
        _reject_none("response.send_message", kw)
        self._claim("response.send_message")
        self._owner.events.append(make_event("send", content, kw))
        self._owner.original = FakeMessage(self._owner.events, content, len(self._owner.events))

    async def defer(self, *, thinking: bool = False, ephemeral: bool = False):
        self._claim("response.defer")
        self._owner.defer_kwargs = {"thinking": thinking, "ephemeral": ephemeral}
        self._owner.events.append(("defer", None, None, (), None, ephemeral))


class _FakeFollowup:
    def __init__(self, owner: "FakeInteraction"):
        self._owner = owner

    async def send(self, content=None, *, wait: bool = False, **kw):
        _reject_none("followup.send", kw)
        if not self._owner.response.is_done():
            raise RuntimeError("followup.send before the initial response (Unknown Webhook)")
        self._owner.calls.append("followup.send")
        self._owner.followup_waits.append(wait)
        self._owner.events.append(make_event("send", content, kw))
        if wait:
            return FakeMessage(self._owner.events, content, len(self._owner.events))
        return None


class FakeInteraction:
    """Stands in for `discord.Interaction`. `.calls` lists the raw methods hit."""

    def __init__(self, events: list, *, user_id: int = 1, channel_id: int = 10):
        self.events = events
        self.calls: list[str] = []
        self.user = FakeUser(user_id)
        self.channel = FakeChannel(events, channel_id, self.calls)
        self.response = _FakeResponse(self)
        self.followup = _FakeFollowup(self)
        self.original: FakeMessage | None = None
        self.defer_kwargs: dict | None = None
        self.followup_waits: list[bool] = []

    async def original_response(self):
        self.calls.append("original_response")
        if self.original is None:
            raise RuntimeError("original_response before send_message")
        return self.original


@dataclass
class ParityCase:
    """One canned call of one handler. `expect`: "send" (>= 1 send, no edit),
    "edit" (the send handle is edited), "multi_send" (>= 2 sends, no edit),
    "error" (the canned call itself ends in `send_error`). `fail_stub`, when
    set, forces the handler's failure path on top of `stub`."""

    id: str
    handler: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    stub: Callable[[pytest.MonkeyPatch], None] | None = None
    fail_stub: Callable[[pytest.MonkeyPatch], None] | None = None
    expect: str = "send"

    def __post_init__(self) -> None:
        if self.expect not in EXPECT_KINDS:
            raise ValueError(f"{self.id}: expect must be one of {EXPECT_KINDS}")

    def call(self, reply):
        return self.handler(reply, *self.args, **self.kwargs)


@dataclass
class BothRun:
    ctx_events: list
    inter_events: list
    ctx_reply: CtxReply
    inter_reply: InteractionReply


def run_both(case_or_call, monkeypatch: pytest.MonkeyPatch) -> BothRun:
    """Run one handler call on CtxReply, then on InteractionReply.

    A `ParityCase` has its `stub` applied first; a plain callable
    `call(reply) -> awaitable` is run as is (stubs are the caller's job)."""
    call = case_or_call
    if isinstance(case_or_call, ParityCase):
        if case_or_call.stub is not None:
            case_or_call.stub(monkeypatch)
        call = case_or_call.call
    ctx_events: list = []
    ctx_reply = CtxReply(FakeContext(ctx_events))
    asyncio.run(call(ctx_reply))
    inter_events: list = []
    inter_reply = InteractionReply(FakeInteraction(inter_events))
    asyncio.run(call(inter_reply))
    return BothRun(ctx_events, inter_events, ctx_reply, inter_reply)


def comparable(events: list) -> list:
    """Drop `defer` events and the ephemeral field: both are no-ops on Context."""
    return [event[:5] for event in events if event[0] != "defer"]


def all_cases() -> list[ParityCase]:
    """Every `CASES` entry of every module in `tests.commands.parity_cases`."""
    import tests.commands.parity_cases as package

    cases: list[ParityCase] = []
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        cases.extend(getattr(module, "CASES", []))
    return cases
