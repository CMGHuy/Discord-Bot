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
