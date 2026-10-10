# v153 Slash command parity through shared handlers. Implementation Plan, part 1 (foundation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief SP1` or `grep -n "^### Task SP1:" -A 600 docs/superpowers/plans/2026-10-10-v153-slash-command-parity_1-foundation.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`](../specs/2026-10-09-v153-slash-command-parity-design.md) (sections "The `Reply` contract", "Handlers, twins and the tip line", "`SLASH_TWIN`", "Tests / Reply-parity harness", "Parallelisation" R and P)
**Index:** [`2026-10-10-v153-slash-command-parity_0-index.md`](2026-10-10-v153-slash-command-parity_0-index.md): header block (`Bump:`, `Edge:`, `Screen:`), `## Where to work`, `## Global Constraints` (the `Reply` contract is binding), `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 2 to 5.

**Tasks in this part:** SP1, SP2, SP3 (SP4 lives in [`_1b-notify-check`](2026-10-10-v153-slash-command-parity_1b-notify-check.md); split only to stay under 1500 lines). SP1, SP2 and SP3 touch disjoint files and may run in parallel (at most 2 implementers at once). SP4 needs SP1 (`InteractionReply`) and SP3 (both edit `swingbot/commands/slash.py`). SP2 must land before part 2's SP7 (which rewrites `growth.py`).

Conventions (index `## Where to work`): `$R` = `/home/user/Discord-Bot` (main tree, never edited); `$WT` = `$R/.claude/worktrees/2026-10-10-v153-slash-command-parity` (branch of the same name). Never `cd`: use `git -C $WT` and `python $WT/scripts/dev/testrun.py file tests/...`. After every commit `git -C $R status --short` prints nothing new. Every new or changed function stays < 15 (`python -m radon cc -s -n C <files>`). discord.py 2.7.1 must be importable where tests run.

# Phase A: Foundation

### Task SP1: `Reply` contract, `SLASH_TWIN`, tip helpers, reply-parity harness

**Model:** sonnet — one new pure-Python module plus offline fakes, every member pinned by the index's Global Constraints; no cross-package design.

**Files:**
- Create: `swingbot/commands/reply.py`
- Create: `tests/commands/reply_harness.py`
- Create: `tests/commands/parity_cases/__init__.py`
- Create: `tests/commands/parity_cases/reply_selftest.py`
- Create: `tests/commands/test_reply_parity.py`

**Why:** spec "Parallelisation — R": `reply.py` lands first, alone, with its harness edge-case tests; `slash.py` is **not** touched here. Every module task (SP5–SP16) consumes `Reply`, `CtxReply`, `InteractionReply`, `send_prefix_tip`, and adds a `tests/commands/parity_cases/<module>.py` file whose `CASES` the parametrised harness in `test_reply_parity.py` picks up automatically. `reply_selftest.py` gives the harness its own cases so the parametrisation is never empty and the runner is itself proven before any module depends on it.

Contract points this task pins in code (all from the index's Global Constraints):

| Point | Where |
|---|---|
| Only non-`None` kwargs reach discord.py (`Webhook.send(view=None)` raises) | `_media_kwargs`; every fake raises `TypeError` on a `None` kwarg |
| `CtxReply.send` passes `content` positionally (existing tests read `call.args[0]`) | `_content_args` |
| `InteractionReply.send`: first send → `response.send_message` + `original_response()`; later → `followup.send(wait=True)` | `InteractionReply.send` |
| After `TOKEN_LIFETIME_S` (14 min) the token may be dead: `send` posts with `interaction.channel.send`, `ephemeral` dropped, `defer` is a no-op | `InteractionReply.stale` |
| `send_error` sends, then sets `failed`; `send_prefix_tip` skips a failed reply | `_ReplyBase.send_error`, `send_prefix_tip` |

- [ ] **Step 0: Create the worktree** (skip if `git -C /home/user/Discord-Bot worktree list` already shows `.claude/worktrees/2026-10-10-v153-slash-command-parity`)

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C /home/user/Discord-Bot worktree add -b 2026-10-10-v153-slash-command-parity /home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity main
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity log --oneline -1
```

- [ ] **Step 1: Write the harness**

Create `$WT/tests/commands/reply_harness.py`:

```python
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
```

- [ ] **Step 2: Write the case package and the self-test cases**

Create `$WT/tests/commands/parity_cases/__init__.py`:

```python
"""Reply-parity cases, one module per command module (v153).

Each module defines `CASES: list[ParityCase]` (see
`tests/commands/reply_harness.py`); `all_cases()` imports every module here.
"""
```

Create `$WT/tests/commands/parity_cases/reply_selftest.py`:

```python
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
```

- [ ] **Step 3: Write the failing tests**

Create `$WT/tests/commands/test_reply_parity.py`:

```python
"""v153: the Reply contract and the reply-parity harness.

Part one: the parametrised parity tests -- every ParityCase in
tests/commands/parity_cases/ runs on CtxReply and InteractionReply and must
send the same content/embed/file/view sequence and take the same error path.
Part two: the contract's edge cases, each its own test (spec "Tests").
"""
import asyncio
import datetime as dt
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from swingbot.commands import reply as reply_mod
from swingbot.commands.reply import (
    CHUNK,
    PREFIX_TIP_UNTIL,
    SLASH_TWIN,
    TOKEN_LIFETIME_S,
    CtxReply,
    InteractionReply,
    Reply,
    prefix_tip,
    send_prefix_tip,
)
from tests.commands.reply_harness import (
    FakeContext,
    FakeInteraction,
    FakeMessage,
    all_cases,
    comparable,
    run_both,
)

CASES = all_cases()
FAILING_CASES = [case for case in CASES if case.fail_stub is not None]

_EXPECT = {
    "send": lambda kinds: "send" in kinds and "edit" not in kinds,
    "edit": lambda kinds: "send" in kinds and "edit" in kinds,
    "multi_send": lambda kinds: kinds.count("send") >= 2 and "edit" not in kinds,
    "error": lambda kinds: "send" in kinds,
}


# ── parametrised parity ─────────────────────────────────────────────────

def test_case_ids_are_unique():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_handler_parity(case, monkeypatch):
    run = run_both(case, monkeypatch)
    assert comparable(run.ctx_events) == comparable(run.inter_events)
    kinds = [event[0] for event in comparable(run.ctx_events)]
    assert _EXPECT[case.expect](kinds), (case.expect, kinds)
    expect_failed = case.expect == "error"
    assert run.ctx_reply.failed is expect_failed
    assert run.inter_reply.failed is expect_failed


@pytest.mark.parametrize("case", FAILING_CASES, ids=[case.id for case in FAILING_CASES])
def test_handler_error_parity(case, monkeypatch):
    if case.stub is not None:
        case.stub(monkeypatch)
    case.fail_stub(monkeypatch)
    run = run_both(case.call, monkeypatch)
    assert comparable(run.ctx_events) == comparable(run.inter_events)
    assert run.ctx_events, "the failure path must answer"
    assert run.ctx_reply.failed and run.inter_reply.failed


# ── contract edge cases ─────────────────────────────────────────────────

def _ctx_and_inter():
    ctx_events, inter_events = [], []
    ctx = FakeContext(ctx_events, author_id=7, channel_id=20)
    inter = FakeInteraction(inter_events, user_id=7, channel_id=20)
    return ctx, inter


def test_both_implementations_satisfy_the_protocol():
    ctx, inter = _ctx_and_inter()
    assert isinstance(CtxReply(ctx), Reply)
    assert isinstance(InteractionReply(inter), Reply)


def test_author_channel_and_stale():
    ctx, inter = _ctx_and_inter()
    ctx_reply, inter_reply = CtxReply(ctx), InteractionReply(inter)
    assert ctx_reply.author is ctx.author and ctx_reply.author.id == 7
    assert ctx_reply.channel is ctx.channel and ctx_reply.channel.id == 20
    assert inter_reply.author is inter.user and inter_reply.author.id == 7
    assert inter_reply.channel is inter.channel and inter_reply.channel.id == 20
    assert ctx_reply.stale is False and inter_reply.stale is False
    assert ctx_reply.failed is False and inter_reply.failed is False


def test_defer_then_send_goes_through_followup_with_wait():
    ctx, inter = _ctx_and_inter()

    async def go(reply):
        await reply.defer()
        return await reply.send("hi")

    inter_handle = asyncio.run(go(InteractionReply(inter)))
    assert inter.calls == ["response.defer", "followup.send"]
    assert inter.defer_kwargs == {"thinking": True, "ephemeral": False}
    assert inter.followup_waits == [True]
    ctx_handle = asyncio.run(go(CtxReply(ctx)))
    assert ctx.calls == ["ctx.send"]
    for handle in (inter_handle, ctx_handle):
        assert isinstance(handle, FakeMessage)
        asyncio.run(handle.edit(content="edited"))
        assert handle.content == "edited"


def test_second_send_after_send_message_uses_followup():
    _, inter = _ctx_and_inter()
    reply = InteractionReply(inter)

    async def go():
        first = await reply.send("one")
        second = await reply.send("two")
        return first, second

    first, second = asyncio.run(go())
    assert inter.calls == ["response.send_message", "original_response", "followup.send"]
    assert first is inter.original
    assert isinstance(second, FakeMessage) and second is not first
    assert inter.followup_waits == [True]


def test_ctx_ephemeral_is_a_plain_message_and_defer_sends_nothing():
    ctx, _ = _ctx_and_inter()
    reply = CtxReply(ctx)

    async def go():
        await reply.defer(ephemeral=True)
        await reply.send("secret", ephemeral=True)

    asyncio.run(go())
    assert ctx.calls == ["ctx.send"]
    assert ctx.events == [("send", "secret", None, (), None, False)]


def test_interaction_defer_after_a_response_is_a_no_op():
    _, inter = _ctx_and_inter()
    reply = InteractionReply(inter)

    async def go():
        await reply.send("first")
        await reply.defer()

    asyncio.run(go())
    assert inter.calls == ["response.send_message", "original_response"]


def test_send_chunks_splits_4500_chars_into_three_messages_on_both():
    ctx, inter = _ctx_and_inter()
    text = "a" * 4500
    for reply, events in ((CtxReply(ctx), ctx.events), (InteractionReply(inter), inter.events)):
        asyncio.run(reply.send_chunks(text))
        sends = [event for event in events if event[0] == "send"]
        assert [len(event[1]) for event in sends] == [CHUNK, CHUNK, 4500 - 2 * CHUNK]
        assert all(len(event[1]) <= 1900 for event in sends)
        assert "".join(event[1] for event in sends) == text


def test_send_chunks_with_empty_text_sends_nothing():
    ctx, _ = _ctx_and_inter()
    asyncio.run(CtxReply(ctx).send_chunks(""))
    assert ctx.calls == []


def test_send_error_sets_failed_and_is_ephemeral_on_the_interaction():
    ctx, inter = _ctx_and_inter()
    ctx_reply, inter_reply = CtxReply(ctx), InteractionReply(inter)
    asyncio.run(ctx_reply.send_error("bad"))
    asyncio.run(inter_reply.send_error("bad"))
    assert ctx.events == [("send", "bad", None, (), None, False)]
    assert inter.events == [("send", "bad", None, (), None, True)]
    assert ctx_reply.failed and inter_reply.failed


def test_reply_never_forwards_none_kwargs():
    """The fakes raise TypeError on any None kwarg, as Webhook.send does for view=None."""
    ctx, inter = _ctx_and_inter()

    async def go(reply):
        await reply.defer()
        await reply.send("a", embed=None, file=None, files=None, view=None)
        await reply.send(None, embed=None)

    asyncio.run(go(CtxReply(ctx)))
    asyncio.run(go(InteractionReply(inter)))
    assert ctx.calls == ["ctx.send", "ctx.send"]
    assert inter.calls == ["response.defer", "followup.send", "followup.send"]


def test_silent_is_forwarded_only_when_set():
    seen = []

    class _Ctx:
        async def send(self, *args, **kw):
            seen.append((args, kw))

    reply = CtxReply(_Ctx())
    asyncio.run(reply.send("loud"))
    asyncio.run(reply.send("quiet", silent=True))
    assert seen == [(("loud",), {}), (("quiet",), {"silent": True})]


def test_stale_interaction_posts_to_the_channel_without_ephemeral():
    _, inter = _ctx_and_inter()
    now = [0.0]
    reply = InteractionReply(inter, clock=lambda: now[0])

    async def go():
        await reply.defer()
        now[0] = TOKEN_LIFETIME_S
        assert reply.stale is True
        await reply.defer()
        return await reply.send("final summary", ephemeral=True)

    handle = asyncio.run(go())
    assert inter.calls == ["response.defer", "channel.send"]
    assert inter.events[-1] == ("send", "final summary", None, (), None, False)
    assert isinstance(handle, FakeMessage)


def test_not_yet_stale_one_second_before_the_lifetime():
    _, inter = _ctx_and_inter()
    now = [100.0]
    reply = InteractionReply(inter, clock=lambda: now[0])
    now[0] = 100.0 + TOKEN_LIFETIME_S - 1
    assert reply.stale is False


# ── SLASH_TWIN and the tip line ─────────────────────────────────────────

def test_slash_twin_is_the_complete_53_row_table():
    assert len(SLASH_TWIN) == 53
    assert sum(" " not in key for key in SLASH_TWIN) == 39
    assert sum(" " in key for key in SLASH_TWIN) == 14
    path = re.compile(r"^[-a-z0-9]{1,32}( [-a-z0-9]{1,32})?$")
    assert all(path.match(value) for value in SLASH_TWIN.values())
    assert len({value.split()[0] for value in SLASH_TWIN.values()}) == 41


@pytest.mark.parametrize("name, twin", [
    ("account", "account show"),
    ("account maxrisk", "account maxrisk"),
    ("commands", "help"),
    ("trades", "trades"),
    ("trades clear", "trades-clear"),
    ("trades clear history", "trades-clear-history"),
    ("trade", "trade show"),
    ("trade delete", "trade delete"),
    ("watchlist", "watchlist show"),
    ("watchlist remove", "watchlist remove"),
    ("scrapeall", "scrapeall"),
])
def test_slash_twin_rows(name, twin):
    assert SLASH_TWIN[name] == twin


def test_prefix_tip_before_on_and_after_the_cutoff():
    day_before = PREFIX_TIP_UNTIL - dt.timedelta(days=1)
    assert prefix_tip("commands", day_before) == "Tip: this is now /help"
    assert prefix_tip("trades clear history", day_before) == "Tip: this is now /trades-clear-history"
    assert prefix_tip("commands", PREFIX_TIP_UNTIL) is None
    assert prefix_tip("commands", PREFIX_TIP_UNTIL + dt.timedelta(days=1)) is None
    assert prefix_tip("no-such-command", day_before) is None


@pytest.fixture
def before_cutoff(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def test_send_prefix_tip_sends_the_twin(before_cutoff):
    events = []
    ctx = FakeContext(events, qualified_name="ping")
    asyncio.run(send_prefix_tip(ctx, CtxReply(ctx)))
    assert events == [("send", "Tip: this is now /ping", None, (), None, False)]


def test_send_prefix_tip_skips_a_failed_reply(before_cutoff):
    events = []
    ctx = FakeContext(events, qualified_name="watchlist add")
    reply = CtxReply(ctx)

    async def go():
        await reply.send_error("Please provide a ticker for add/remove actions.")
        await send_prefix_tip(ctx, reply)

    asyncio.run(go())
    assert [event[1] for event in events] == ["Please provide a ticker for add/remove actions."]


def test_send_prefix_tip_skips_unknown_and_missing_names(before_cutoff):
    for qualified_name in (None, "no-such-command"):
        events = []
        ctx = FakeContext(events, qualified_name=qualified_name)
        asyncio.run(send_prefix_tip(ctx, CtxReply(ctx)))
        assert events == []


def test_send_prefix_tip_skips_a_magicmock_context(before_cutoff):
    """Existing `.callback(MagicMock())` tests must see no extra send."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    asyncio.run(send_prefix_tip(ctx, CtxReply(ctx)))
    ctx.send.assert_not_awaited()


def test_send_prefix_tip_is_silent_after_the_cutoff(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: PREFIX_TIP_UNTIL)
    events = []
    ctx = FakeContext(events, qualified_name="ping")
    asyncio.run(send_prefix_tip(ctx, CtxReply(ctx)))
    assert events == []
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `ModuleNotFoundError: No module named 'swingbot.commands.reply'`.

- [ ] **Step 5: Write `reply.py`**

Create `$WT/swingbot/commands/reply.py`:

```python
"""One answer surface for prefix (`!`) and slash (`/`) commands (v153).

Every command body is an `async def handle_<name>(reply, <typed args>)`
next to its prefix command. The prefix command wraps its `ctx` in
`CtxReply`; the slash twin, defined in the same module, wraps its
`interaction` in `InteractionReply`. A handler answers only through the
`Reply` members below and never touches `ctx` or `interaction`.

Both implementations forward only non-None keyword arguments: discord.py's
`Webhook.send` raises on `view=None` / `file=None`.

`SLASH_TWIN` maps every qualified prefix name, as `bot.walk_commands()`
yields it, to its slash path. The tip line and the parity test
(`tests/commands/test_slash_parity.py`) read it; nothing else maps names.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Callable, Protocol, runtime_checkable

CHUNK = 1900                  # Discord caps a message at 2000 chars
TOKEN_LIFETIME_S = 14 * 60    # interaction tokens die at 15 min; keep a minute's margin
# Deploy day + 90 days; after it `prefix_tip` returns None. Provisional value,
# pinned to the real deploy day by plan v153 SP21.
PREFIX_TIP_UNTIL = dt.date(2027, 1, 8)

SLASH_TWIN: dict[str, str] = {
    # account.py -- `!account` alone runs, so it maps to a `show` subcommand
    "account": "account show",
    "account balance": "account balance",
    "account risk": "account risk",
    "account maxpositions": "account maxpositions",
    "account sizing": "account sizing",
    "account positionpct": "account positionpct",
    "account maxpositionpct": "account maxpositionpct",
    "account maxposition": "account maxposition",
    "account maxrisk": "account maxrisk",
    # backtest.py
    "backtest": "backtest",
    "backtestwatchlist": "backtestwatchlist",
    # data.py
    "charts": "charts",
    "download": "download",
    "cached": "cached",
    "scrapeall": "scrapeall",
    # growth.py
    "growth": "growth",
    "killswitch": "killswitch",
    "portfolio": "portfolio",
    # history.py
    "plans": "plans",
    # info.py
    "strategies": "strategies",
    "confidence": "confidence",
    "ticker": "ticker",
    "strategycharts": "strategycharts",
    "regime": "regime",
    "ping": "ping",
    "commands": "help",
    # plans.py
    "liveplans": "liveplans",
    # scanning/commands.py
    "recap": "recap",
    "check": "check",
    "session": "session",
    "status": "status",
    "pause": "pause",
    "resume": "resume",
    "stop": "stop",
    # stats.py
    "soak": "soak",
    "top": "top",
    "stats": "stats",
    "lessons": "lessons",
    "calibration": "calibration",
    "journal": "journal",
    # trades.py -- `/trades` already exists as a plain command, so the clear
    # subcommands become hyphenated top-level names
    "trades": "trades",
    "trades clear": "trades-clear",
    "trades clear history": "trades-clear-history",
    "trade": "trade show",
    "trade delete": "trade delete",
    "tradecharts": "tradecharts",
    "performance": "performance",
    "pnl": "pnl",
    "summary": "summary",
    # watchlist.py -- `/watchlist` dispatches on its `action` choice
    "watchlist": "watchlist show",
    "watchlist add": "watchlist add",
    "watchlist remove": "watchlist remove",
    "watchlist clear": "watchlist clear",
}


def _content_args(content: str | None) -> tuple:
    """`content` positional when present -- tests read `call.args[0]`."""
    return () if content is None else (content,)


def _media_kwargs(embed: Any, file: Any, files: Any, view: Any, silent: bool) -> dict:
    kw = {name: value for name, value in
          (("embed", embed), ("file", file), ("files", files), ("view", view))
          if value is not None}
    if silent:
        kw["silent"] = True
    return kw


def _chunks(text: str) -> list[str]:
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]


@runtime_checkable
class Reply(Protocol):
    """What a handler may use. `send` returns an editable handle."""

    failed: bool

    @property
    def author(self) -> Any: ...

    @property
    def channel(self) -> Any: ...

    @property
    def stale(self) -> bool: ...

    async def defer(self, ephemeral: bool = False) -> None: ...

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any: ...

    async def send_chunks(self, text: str, *, ephemeral: bool = False) -> None: ...

    async def send_error(self, text: str, *, ephemeral: bool = True) -> Any: ...


class _ReplyBase:
    """`send_chunks` and `send_error`, shared; subclasses implement `send`."""

    def __init__(self) -> None:
        self.failed = False

    async def send(self, content: str | None = None, **kw: Any) -> Any:
        raise NotImplementedError

    async def send_chunks(self, text: str, *, ephemeral: bool = False) -> None:
        for chunk in _chunks(text):
            await self.send(chunk, ephemeral=ephemeral)

    async def send_error(self, text: str, *, ephemeral: bool = True) -> Any:
        handle = await self.send(text, ephemeral=ephemeral)
        self.failed = True
        return handle


class CtxReply(_ReplyBase):
    """A prefix command's answer. `defer` and `ephemeral` are documented
    no-ops: a prefix reply is always a plain channel message, as before."""

    def __init__(self, ctx: Any) -> None:
        super().__init__()
        self._ctx = ctx

    @property
    def author(self) -> Any:
        return self._ctx.author

    @property
    def channel(self) -> Any:
        return self._ctx.channel

    @property
    def stale(self) -> bool:
        return False

    async def defer(self, ephemeral: bool = False) -> None:
        return None

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any:
        kw = _media_kwargs(embed, file, files, view, silent)
        return await self._ctx.send(*_content_args(content), **kw)


class InteractionReply(_ReplyBase):
    """A slash command's answer.

    First send without a defer -> `response.send_message` and the
    `original_response()` handle; every later send -> `followup.send(wait=True)`
    and its `WebhookMessage`. Once `stale` (the 15-minute token may be
    dead), `send` posts with `interaction.channel.send` instead, without
    `ephemeral`, so a long `/scrapeall` loses late progress edits but never
    its result."""

    def __init__(self, interaction: Any, *, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self._interaction = interaction
        self._clock = clock
        self._started = clock()

    @property
    def author(self) -> Any:
        return self._interaction.user

    @property
    def channel(self) -> Any:
        return self._interaction.channel

    @property
    def stale(self) -> bool:
        return self._clock() - self._started >= TOKEN_LIFETIME_S

    async def defer(self, ephemeral: bool = False) -> None:
        response = self._interaction.response
        if self.stale or response.is_done():
            return
        await response.defer(thinking=True, ephemeral=ephemeral)

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any:
        kw = _media_kwargs(embed, file, files, view, silent)
        args = _content_args(content)
        if self.stale:
            return await self._interaction.channel.send(*args, **kw)
        if ephemeral:
            kw["ephemeral"] = True
        response = self._interaction.response
        if not response.is_done():
            await response.send_message(*args, **kw)
            return await self._interaction.original_response()
        return await self._interaction.followup.send(*args, wait=True, **kw)


def _today() -> dt.date:
    """Seam for tests (monkeypatched)."""
    return dt.date.today()


def prefix_tip(qualified_name: str, today: dt.date) -> str | None:
    """The one-line nudge to a prefix command's slash twin, until PREFIX_TIP_UNTIL."""
    twin = SLASH_TWIN.get(qualified_name)
    if twin is None or today >= PREFIX_TIP_UNTIL:
        return None
    return f"Tip: this is now /{twin}"


async def send_prefix_tip(ctx: Any, reply: Reply) -> None:
    """Send the tip after a successful prefix answer.

    Nothing is sent when the reply failed, when the command name is not a
    `str` key of SLASH_TWIN (a MagicMock ctx in older tests), or after the
    cutoff. A handler that raised never reaches this call."""
    name = getattr(getattr(ctx, "command", None), "qualified_name", None)
    if not isinstance(name, str) or reply.failed:
        return
    tip = prefix_tip(name, _today())
    if tip is not None:
        await reply.send(tip)
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: one-line verdict, `0 failed`, `0 xfailed`; the parametrised ids include the seven `selftest-*` cases and `test_handler_error_parity[selftest-lookup]`.

- [ ] **Step 7: Complexity and syntax**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/reply.py $WT/tests/commands/reply_harness.py $WT/tests/commands/parity_cases/reply_selftest.py
python -m py_compile $WT/swingbot/commands/reply.py
```

Expected: radon prints nothing (every block is A or B). Paste the (empty) output into the report.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/reply.py tests/commands/reply_harness.py tests/commands/parity_cases/__init__.py tests/commands/parity_cases/reply_selftest.py tests/commands/test_reply_parity.py
git -C $WT commit -m "feat(v153): Reply contract, SLASH_TWIN, tip helpers and the reply-parity harness (SP1)"
git -C /home/user/Discord-Bot status --short
```

### Task SP2: Move `_collect_portfolio_state` to `core/edge/portfolio_state.py` (spec task P)

**Model:** sonnet — a verbatim function move plus four import/target updates; mechanical, but it crosses `commands`, `core/edge` and `admin`.

**Complexity gate (audit 2026-10-10):** this task moves and renames `_collect_portfolio_state` (22). If `scripts/dev/complexity_gate.py` exists (v149 merged), before the commit hand-rename the key `swingbot.commands.growth:_collect_portfolio_state` → `swingbot.core.edge.portfolio_state:collect_portfolio_state` in `scripts/dev/complexity_baseline.json`, run `python $WT/scripts/dev/complexity_gate.py`, then `--update`, and commit the baseline in this task's commit (verdicts `gone`/`improved` expected; `new`/`risen` never). Index Global Constraints, Complexity bullet.

**Files:**
- Create: `swingbot/core/edge/portfolio_state.py`
- Modify: `swingbot/commands/growth.py`
- Modify: `swingbot/admin/api_v1/risk.py`
- Modify: `swingbot/admin/api_v1/dashboard.py` (docstring/comment text only)
- Modify: `swingbot/core/tracking/retrospective.py` (docstring text only)
- Modify: `tests/edge/test_edge_heat.py`
- Modify: `tests/admin/test_api_v1_dashboard.py`

**Why:** spec "Parallelisation — P": `swingbot/admin/api_v1/risk.py:280` imports `_collect_portfolio_state` from `swingbot.commands.growth`, so the admin process imports a Discord command module (and, after v153, registers its slash twins on an unsynced tree). The collector (`growth.py:102`, radon D 22, legacy) moves **unchanged** to `swingbot.core.edge.portfolio_state.collect_portfolio_state`; `growth.py` re-imports it under its old local name so `portfolio_command` (`growth.py:216-220`) is untouched until SP7 rewrites it. Its body already calls `account_module.load_account_config()` through the module attribute, so `tests/edge/test_edge_heat.py:90`'s monkeypatch of `swingbot.core.planning.account.load_account_config` keeps working. `tests/admin/test_admin_logging.py:52` imports `swingbot.commands.growth` explicitly and is unaffected.

- [ ] **Step 0: Confirm the worktree** — `git -C /home/user/Discord-Bot worktree list` shows `$WT`; if not, run SP1 Step 0 first. SP2 may run in parallel with SP1/SP3 (disjoint files).

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/edge/test_edge_heat.py`, inside `test_collect_portfolio_state_degrades_on_account_config_failure` (line 90), replace the import and the call:

```python
    from swingbot.core.edge.portfolio_state import collect_portfolio_state
```

```python
    state = collect_portfolio_state()
```

and in its docstring (line 93) and in `test_collect_weekly_risk_stats_excludes_self_correlated_singleton`'s docstring (line 131) replace `_collect_portfolio_state` with `collect_portfolio_state` and `(E52, growth.py)` with `(E52, core/edge/portfolio_state.py)`. Then append at the end of the file:

```python
def test_growth_command_reads_the_moved_collector():
    """v153 task P: one collector, re-exported under growth.py's old local name."""
    from swingbot.commands import growth
    from swingbot.core.edge import portfolio_state

    assert growth._collect_portfolio_state is portfolio_state.collect_portfolio_state


def test_admin_never_imports_the_growth_command_module():
    """v153 task P: the admin process reads the collector from core/edge,
    never from swingbot.commands.growth (a Discord command module)."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "swingbot" / "admin"
    hits = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
                if node.module == "swingbot.commands.growth" or (
                        node.module == "swingbot.commands" and "growth" in names):
                    hits.append(f"{path.name}:{node.lineno}")
            elif isinstance(node, ast.Import):
                if any(alias.name == "swingbot.commands.growth" for alias in node.names):
                    hits.append(f"{path.name}:{node.lineno}")
    assert hits == []
```

In `$WT/tests/admin/test_api_v1_dashboard.py`, `test_risk_used_skips_the_full_portfolio_collector` (line 237), replace

```python
    import swingbot.commands.growth as growth
```

with

```python
    import swingbot.core.edge.portfolio_state as portfolio_state
```

and

```python
    monkeypatch.setattr(growth, "_collect_portfolio_state", boom)
```

with

```python
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state", boom)
```

and in the module docstring (line 14) replace `` `_collect_portfolio_state` `` with `` `collect_portfolio_state` ``.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python $WT/scripts/dev/testrun.py file tests/edge/test_edge_heat.py
```

Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.edge.portfolio_state'` (twice) and `test_admin_never_imports_the_growth_command_module` failing with `['risk.py:280']`.

- [ ] **Step 3: Move the function verbatim**

The move is scripted so the body cannot drift. Run:

```bash
python - <<'PY'
import pathlib

wt = pathlib.Path("/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity")
growth = wt / "swingbot/commands/growth.py"
src = growth.read_text(encoding="utf-8")
start = src.index("def _collect_portfolio_state() -> dict:\n")
end = src.index("def portfolio_report(state: dict) -> str:\n")
body = src[start:end].rstrip() + "\n"
assert "\ndef " not in body and "\nasync def " not in body, "exactly one function moves"
header = '''"""Portfolio survival state behind `!portfolio` and GET /api/v1/risk.

Open heat against its cap, sector heat, the drawdown throttle, the kill
switch, the growth path and correlated clusters over the open trades. Every
sub-collector degrades to a safe default on its own.

Moved unchanged out of `swingbot.commands.growth` by v153 (task P), so the
admin process reads it without importing a Discord command module.
"""
from swingbot import config
from swingbot.core.edge.growth import growth_path
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import TradeLog


'''
moved = body.replace("def _collect_portfolio_state() -> dict:",
                     "def collect_portfolio_state() -> dict:", 1)
(wt / "swingbot/core/edge/portfolio_state.py").write_text(header + moved, encoding="utf-8")
growth.write_text(src[:start] + src[end:], encoding="utf-8")
print("moved", body.count("\n"), "lines")
PY
```

Expected: `moved 91 lines` (lines 102-192 of today's `growth.py`, trailing blank line included).

Prove the body is unchanged (only the `def` line may differ):

```bash
diff <(git -C $WT show HEAD:swingbot/commands/growth.py | sed -n '/^def _collect_portfolio_state/,/^def portfolio_report/p' | sed '$d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}') \
     <(sed -n '/^def collect_portfolio_state/,$p' $WT/swingbot/core/edge/portfolio_state.py)
```

Expected: exactly one hunk, `< def _collect_portfolio_state() -> dict:` / `> def collect_portfolio_state() -> dict:`.

- [ ] **Step 4: Re-import it in `growth.py`**

In `$WT/swingbot/commands/growth.py`, after the line `from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path` (line 13), add:

```python
from swingbot.core.edge.portfolio_state import collect_portfolio_state as _collect_portfolio_state
```

`portfolio_command` (`await asyncio.to_thread(_collect_portfolio_state)`) is unchanged. Keep the `TradeLog`, `account_module` and `growth_path` imports: `_collect_stats` still uses them.

- [ ] **Step 5: Point the admin endpoint at the new module**

In `$WT/swingbot/admin/api_v1/risk.py`, `get_risk` (lines 278-282), replace

```python
    from swingbot.commands.growth import _collect_portfolio_state

    state = _collect_portfolio_state()
```

with

```python
    from swingbot.core.edge.portfolio_state import collect_portfolio_state

    state = collect_portfolio_state()
```

Then update the four text mentions (no code change):

```bash
sed -i 's/`_collect_portfolio_state` is the same collector/`collect_portfolio_state` is the same collector/' $WT/swingbot/admin/api_v1/risk.py
sed -i 's/_collect_portfolio_state/collect_portfolio_state/g' $WT/swingbot/admin/api_v1/dashboard.py
sed -i 's/Mirrors _collect_portfolio_state'"'"'s/Mirrors collect_portfolio_state'"'"'s/; s/(Task E52, swingbot\/commands\/growth.py)/(Task E52, swingbot\/core\/edge\/portfolio_state.py)/' $WT/swingbot/core/tracking/retrospective.py
git -C $WT grep -n "_collect_portfolio_state" -- swingbot tests
```

Expected: the last grep prints only `swingbot/commands/growth.py` lines (the re-import at line 14 and the call in `portfolio_command`) and `tests/edge/test_edge_heat.py` (the `growth._collect_portfolio_state is ...` assertion). If `retrospective.py`'s docstring wraps the phrase across lines differently, edit it by hand to name `collect_portfolio_state` in `swingbot/core/edge/portfolio_state.py`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/edge/test_edge_heat.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
python $WT/scripts/dev/testrun.py file tests/commands/test_growth_command.py
python $WT/scripts/dev/testrun.py file tests/admin/test_admin_logging.py
```

Expected: each `0 failed`, `0 xfailed`. Also run `git -C $WT grep -ln "api/v1/risk" -- tests/admin` and run each listed file the same way (the `/risk` endpoint tests).

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/core/edge/portfolio_state.py $WT/swingbot/commands/growth.py $WT/swingbot/admin/api_v1/risk.py
```

Expected: `collect_portfolio_state` D (22) — the legacy score, moved unchanged — and `growth.py`'s `_collect_stats` C (12) as before; nothing new. Paste the output into the report.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/edge/portfolio_state.py swingbot/commands/growth.py swingbot/admin/api_v1/risk.py swingbot/admin/api_v1/dashboard.py swingbot/core/tracking/retrospective.py tests/edge/test_edge_heat.py tests/admin/test_api_v1_dashboard.py
git -C $WT commit -m "refactor(v153): move the portfolio-state collector to core/edge (task P, SP2)"
git -C /home/user/Discord-Bot status --short
```

### Task SP3: `bot.tree.error` handler for app-command check failures

**Model:** sonnet — one small handler and its test in a known module; the discord.py error types are named in the ledger.

**Files:**
- Modify: `swingbot/commands/slash.py`
- Create: `tests/commands/test_slash_error_handler.py`

**Why:** Controller decision 6. No `bot.tree.error` handler exists (brief §0.7), so SP7's `/killswitch` would answer a non-admin with Discord's generic "The application did not respond" when `app_commands.checks.has_permissions` raises `MissingPermissions`. The handler answers the two check failures with an ephemeral one-liner (the prefix side's `on_command_error` already says `🚫 You don't have permission to run that command.`, `bot_core.py:357-359`) and logs and re-raises everything else. It lives in `slash.py`, which `bot.py:52` imports and which keeps it after SP16 empties the file of commands. Replies are a table, not an `if/elif` chain.

- [ ] **Step 0: Confirm the worktree** — as SP2 Step 0. SP3 may run in parallel with SP1/SP2.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/commands/test_slash_error_handler.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_error_handler.py
```

Expected: FAIL, `AttributeError: module 'swingbot.commands.slash' has no attribute 'on_app_command_error'`.

- [ ] **Step 3: Add the handler**

In `$WT/swingbot/commands/slash.py`, after `import asyncio` (line 12) add `import logging`; after the `from swingbot.core.scanning import engine as scan_engine` line add:

```python

log = logging.getLogger(__name__)
```

Then, directly after `PERIOD_CHOICES = ...` (line 62) and before the `# Helper — send long text in chunks` banner, insert:

```python


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
```

(`log.error(..., exc_info=error)` is `log.exception` without needing an active `except` block: the handler is awaited from discord.py's dispatcher, not from inside our own `try`.)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_error_handler.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
```

Expected: both `0 failed`, `0 xfailed` (`test_slash_has_no_direct_colour` still holds).

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/slash.py
```

Expected: no output. Paste it into the report.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/commands/slash.py tests/commands/test_slash_error_handler.py
git -C $WT commit -m "feat(v153): answer slash permission/guild check failures ephemerally (SP3)"
git -C /home/user/Discord-Bot status --short
```
