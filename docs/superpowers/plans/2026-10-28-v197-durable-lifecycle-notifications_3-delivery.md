# Durable lifecycle notifications — delivery

**Bump:** bot patch, ui patch
**Edge:** harvest
**Screen:** harvest-headroom docs/superpowers/results/2026-10-28-notification-delivery-evidence.md
**Spec:** [Approved v197 spec](../specs/2026-10-28-v197-durable-lifecycle-notifications.md)

Use the [implementation index](2026-10-28-v197-durable-lifecycle-notifications_0-index.md) for the goal, global constraints, frozen contracts, execution order and parallelisation. This part consumes V197-1 through V197-4b; implementation starts from the merged v194 result (`65de3bc7`). Authoring this document runs no application tests or database operations.

# Phase 3: Deliver immutable snapshots with fenced outcomes

### Task V197-5: Render and send recorded closure and cancellation snapshots
**Model:** sonnet — bounded snapshot adapter with explicit delivery failures.

**Files:** Create `swingbot/core/scanning/lifecycle_notifications.py` and `tests/scanning/test_lifecycle_notifications.py`. Reference, but do not modify, `swingbot/core/scanning/lifecycle_embeds.py`, `swingbot/core/presentation/components.py` and `swingbot/core/presentation/kinds.py`.

**Interfaces:** Consume V197-1 `validate_event(event: dict) -> None` and `make_event(*, transition_id, kind, target_channel_id, occurred_at, payload) -> dict`; existing `build_closed_trade_embed(trade)`, `ui.push_embed`, `ui.push_kwargs`, `ui.apply_chrome`, `Kind.CANCEL` and `Kind.CLOSED_TRADE`. Produce `build_lifecycle_notification(event: dict) -> discord.Embed`, `async send_lifecycle_notification(bot, event: dict) -> str`, and `BlockedDelivery(code: str)` exposing bounded safe `.code`. No persistence, quotes or current trade/plan reads belong here. V197-6 supplies the whole-operation timeout.

- [ ] **Step 1: Add executable snapshot and send regressions.** Put the following in the new test file. These fixtures deliberately contain recorded values; no database is needed by the test body. If project fixtures access the database, run the required replicate-prod-db preflight first.

```python
import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.scanning import lifecycle_notifications as notices

AT = "2026-10-28T12:00:00+00:00"


def event(kind="trade_closed", status="closed", *, linked=False):
    trade = dict(id="T1", ticker="NVDA", direction="bullish", status="closed",
                 entry=100.0, exit_price=110.0, stop_loss=95.0, take_profit=115.0,
                 realized_pnl_amount=25.0, close_reason="manual", opened_at=AT,
                 closed_at=AT, plan_id="P1")
    payload = dict(ticker="NVDA", direction="bullish", plan_id="P1", trade_id=None,
                   prior_status="PENDING" if status == "CANCELLED" else "ACTIVE",
                   new_status=status, reason="manual", occurred_at=AT)
    if kind == "trade_closed" or linked:
        payload.update(trade_id="T1", trade=trade)
    return make_event(transition_id="transition-1", kind=kind, target_channel_id="5",
                      occurred_at=AT, payload=payload)


def fields(embed):
    return {field.name: field.value for field in embed.fields}


def test_trade_preserves_recorded_result_and_existing_chrome():
    original = event()
    before = deepcopy(original)
    expected = notices.build_closed_trade_embed(original["payload"]["trade"])
    actual = notices.build_lifecycle_notification(original)
    assert fields(actual)["Result"] == fields(expected)["Result"]
    assert fields(actual)["Entry"] == fields(expected)["Entry"]
    assert fields(actual)["Exit"] == fields(expected)["Exit"]
    assert expected.footer.text in actual.footer.text
    assert actual.footer.text.endswith("Event " + original["event_id"])
    assert actual.timestamp == datetime.fromisoformat(AT)
    assert actual.push_text == expected.push_text
    assert original == before


@pytest.mark.parametrize("status,linked", [("CLOSED", False), ("CLOSED", True),
                                            ("CANCELLED", False)])
def test_plan_title_context_and_fill_semantics(status, linked):
    notice = event("plan_transition", status, linked=linked)
    built = notices.build_lifecycle_notification(notice)
    assert built.title.startswith("Plan " + status.lower())
    context = fields(built)["Recorded transition"]
    for value in ("NVDA", "bullish", "P1", notice["payload"]["prior_status"], status, AT):
        assert value in context
    assert fields(built)["Transition reason"] == "manual"
    assert built.timestamp == datetime.fromisoformat(AT)
    assert ("Result" in fields(built)) == linked
    if status == "CANCELLED":
        assert "unfilled" in built.description.lower()
        assert "cancelled" in built.push_text.lower()
        assert "Entry" not in fields(built)
    if linked:
        assert "T1" in context
        expected = notices.build_closed_trade_embed(notice["payload"]["trade"])
        assert fields(built)["Result"] == fields(expected)["Result"]


def test_cancellation_never_calls_trade_renderer(monkeypatch):
    renderer = Mock(side_effect=AssertionError("must not price a cancellation"))
    monkeypatch.setattr(notices, "build_closed_trade_embed", renderer)
    notices.build_lifecycle_notification(event("plan_transition", "CANCELLED"))
    renderer.assert_not_called()


def test_footer_preserves_icon_and_event_identity_on_repeat(monkeypatch):
    base = ui.push_embed(notices.Kind.CLOSED_TRADE, "NVDA", "bullish", "Recorded")
    base.set_footer(text="Existing chrome", icon_url="https://example.org/icon.png")
    monkeypatch.setattr(notices, "build_closed_trade_embed", lambda trade: deepcopy(base))
    notice = event()
    first = notices.build_lifecycle_notification(notice)
    second = notices.build_lifecycle_notification(notice)
    assert first.to_dict()["footer"] == second.to_dict()["footer"]
    assert first.footer.icon_url == "https://example.org/icon.png"
    assert first.footer.text == "Existing chrome · Event " + notice["event_id"]


@pytest.mark.parametrize("change", [
    lambda value: value["payload"].pop("reason"),
    lambda value: value["payload"].update(direction="unknown"),
    lambda value: value["payload"]["trade"].update(entry="not-a-price"),
    lambda value: value.update(event_id="changed"),
])
def test_malformed_snapshots_are_blocked(change):
    notice = event()
    change(notice)
    with pytest.raises(notices.BlockedDelivery, match="malformed_payload"):
        notices.build_lifecycle_notification(notice)


@pytest.mark.parametrize("change", [
    lambda trade: trade.update(id="another-trade"),
    lambda trade: trade.update(ticker="MSFT"),
    lambda trade: trade.update(direction="bearish"),
    lambda trade: trade.update(status="open"),
])
def test_linked_plan_trade_snapshot_must_match(change):
    notice = event("plan_transition", "CLOSED", linked=True)
    change(notice["payload"]["trade"])
    with pytest.raises(notices.BlockedDelivery, match="malformed_payload"):
        notices.build_lifecycle_notification(notice)


def test_cancelled_payload_cannot_smuggle_in_a_trade():
    notice = event("plan_transition", "CANCELLED")
    notice["payload"]["trade"] = event()["payload"]["trade"]
    with pytest.raises(notices.BlockedDelivery):
        notices.build_lifecycle_notification(notice)


@pytest.mark.parametrize("cached", [True, False])
def test_sender_uses_frozen_destination_and_returns_real_message_id(monkeypatch, cached):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "999")
    channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=123)))
    bot = SimpleNamespace(get_channel=Mock(return_value=channel if cached else None),
                          fetch_channel=AsyncMock(return_value=channel))
    assert asyncio.run(notices.send_lifecycle_notification(bot, event())) == "123"
    bot.get_channel.assert_called_once_with(5)
    if cached:
        bot.fetch_channel.assert_not_awaited()
    else:
        bot.fetch_channel.assert_awaited_once_with(5)
    sent = channel.send.call_args.kwargs
    assert sent["content"] == sent["embed"].push_text
    assert "view" not in sent


@pytest.mark.parametrize("channel_id", [None, "", "abc", "0"])
def test_missing_destination_is_explicitly_blocked(channel_id):
    notice = event()
    notice["target_channel_id"] = channel_id
    bot = SimpleNamespace(get_channel=Mock())
    with pytest.raises(notices.BlockedDelivery, match="destination_unresolved"):
        asyncio.run(notices.send_lifecycle_notification(bot, notice))
    bot.get_channel.assert_not_called()


@pytest.mark.parametrize("where", ["fetch", "send"])
@pytest.mark.parametrize("error_type,code,status", [
    (discord.Forbidden, "permission_denied", 403),
    (discord.NotFound, "channel_unavailable", 404),
])
def test_known_discord_failures_have_safe_codes(where, error_type, code, status):
    response = SimpleNamespace(status=status, reason="hidden raw response")
    error = error_type(response, "private response detail")
    error.retry_after = 1200
    channel = SimpleNamespace(send=AsyncMock(side_effect=error if where == "send" else None))
    bot = SimpleNamespace(get_channel=lambda value: None if where == "fetch" else channel,
                          fetch_channel=AsyncMock(side_effect=error))
    with pytest.raises(notices.BlockedDelivery) as caught:
        asyncio.run(notices.send_lifecycle_notification(bot, event()))
    assert caught.value.code == code
    assert caught.value.retry_after == 1200
    assert str(caught.value) == code


@pytest.mark.parametrize("channel", [None, SimpleNamespace()])
def test_unavailable_channel_is_blocked(channel):
    bot = SimpleNamespace(get_channel=lambda value: None,
                          fetch_channel=AsyncMock(return_value=channel))
    with pytest.raises(notices.BlockedDelivery, match="channel_unavailable"):
        asyncio.run(notices.send_lifecycle_notification(bot, event()))


@pytest.mark.parametrize("message", [None, SimpleNamespace(), SimpleNamespace(id=None),
                                     SimpleNamespace(id="")])
def test_send_without_message_id_is_not_success(message):
    channel = SimpleNamespace(send=AsyncMock(return_value=message))
    bot = SimpleNamespace(get_channel=lambda value: channel)
    with pytest.raises(RuntimeError, match="missing_message_id"):
        asyncio.run(notices.send_lifecycle_notification(bot, event()))


def test_network_failure_propagates_for_retry():
    channel = SimpleNamespace(send=AsyncMock(side_effect=OSError("private network error")))
    bot = SimpleNamespace(get_channel=lambda value: channel)
    with pytest.raises(OSError):
        asyncio.run(notices.send_lifecycle_notification(bot, event()))
```

- [ ] **Step 2: Run the narrow red test.** Run `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_notifications.py`. Expect the new module import to fail until the implementation exists; do not run the full suite.

- [ ] **Step 3: Implement the complete snapshot adapter below.** It wraps the existing closure builder without changing that complexity-17 function. A plan with a linked closure gets recorded result fields and a distinct plan title. An unlinked plan does not fabricate entry, exit, result or a filled position. Destination validation is separate from snapshot validation so an unresolved target has the right blocked cause. Permission and not-found exceptions preserve only numeric retry metadata for the worker; no exception message is retained.

```python
"""Render persisted lifecycle snapshots and return actual Discord acceptance IDs."""
from copy import deepcopy
from datetime import datetime

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.infra.lifecycle_events import validate_event
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning.lifecycle_embeds import build_closed_trade_embed

_BLOCKED_CODES = frozenset(("destination_unresolved", "channel_unavailable",
                            "permission_denied", "malformed_payload"))


class BlockedDelivery(Exception):
    def __init__(self, code: str):
        self.code = code if code in _BLOCKED_CODES else "malformed_payload"
        self.retry_after = None
        super().__init__(self.code)


def _recorded_trade(payload):
    trade = payload.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("missing_trade")
    pairs = (("id", "trade_id"), ("ticker", "ticker"), ("direction", "direction"))
    if any(not trade.get(a) or trade[a] != payload.get(b) for a, b in pairs):
        raise ValueError("inconsistent_trade")
    if trade.get("status") not in ("win", "loss", "closed") or "entry" not in trade:
        raise ValueError("incomplete_trade")
    return deepcopy(trade)


def _plan_embed(payload):
    cancelled = payload["new_status"] == "CANCELLED"
    kind = Kind.CANCEL if cancelled else Kind.CLOSED_TRADE
    label = "Plan cancelled" if cancelled else "Plan closed"
    if "trade" in payload:
        embed = build_closed_trade_embed(_recorded_trade(payload))
    else:
        description = ("This unfilled plan was cancelled. No position was filled."
                       if cancelled else "This plan was closed. No linked trade result was recorded.")
        embed = ui.push_embed(kind, payload["ticker"], payload["direction"], label,
                              description=description)
        ui.apply_chrome(embed, kind=kind, plan_id=payload["plan_id"],
                        link_base=config.ADMIN_PUBLIC_URL)
    embed.title = f"{label} · {payload['ticker']}"
    embed.push_text = kinds.content_line(kind, payload["ticker"], payload["direction"], label)
    return embed


def _append_transition(embed, event):
    payload = event["payload"]
    context = (f"{payload['ticker']} · {payload['direction']}\n"
               f"Plan: {payload.get('plan_id') or 'Not linked'}\n"
               f"Trade: {payload.get('trade_id') or 'Not linked'}\n"
               f"{payload['prior_status']} → {payload['new_status']}\n"
               f"Recorded: {payload['occurred_at']}")
    embed.add_field(name="Recorded transition", value=context, inline=False)
    reason = payload["reason"]
    embed.add_field(name="Transition reason", value=reason[:1021] + "…" if len(reason) > 1024
                    else reason, inline=False)
    footer = dict(embed.to_dict().get("footer", {}))
    prefix = footer.get("text", "")
    footer["text"] = f"{prefix} · Event {event['event_id']}" if prefix else f"Event {event['event_id']}"
    embed.set_footer(**footer)
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed


def build_lifecycle_notification(event: dict) -> discord.Embed:
    try:
        validate_event(event)
        payload = event["payload"]
        embed = (build_closed_trade_embed(_recorded_trade(payload))
                 if event["kind"] == "trade_closed" else _plan_embed(payload))
        return _append_transition(embed, event)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        raise BlockedDelivery("malformed_payload") from None


def _channel_id(event):
    value = event.get("target_channel_id")
    if not isinstance(value, str) or not value.isdecimal() or int(value) <= 0:
        raise BlockedDelivery("destination_unresolved")
    return int(value)


def _blocked_from_discord(error, code):
    blocked = BlockedDelivery(code)
    blocked.retry_after = getattr(error, "retry_after", None)
    return blocked


async def send_lifecycle_notification(bot, event: dict) -> str:
    embed = build_lifecycle_notification(event)
    channel_id = _channel_id(event)
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        if not callable(getattr(channel, "send", None)):
            raise BlockedDelivery("channel_unavailable")
        message = await channel.send(**ui.push_kwargs(embed))
    except discord.Forbidden as error:
        raise _blocked_from_discord(error, "permission_denied") from None
    except discord.NotFound as error:
        raise _blocked_from_discord(error, "channel_unavailable") from None
    message_id = getattr(message, "id", None)
    if message_id is None or not str(message_id).strip():
        raise RuntimeError("missing_message_id")
    return str(message_id)
```

- [ ] **Step 4: Verify narrowly.** Run `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_notifications.py` and `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_push.py`; require 0 failed and 0 xfailed. Run `python scripts/dev/complexity_gate.py`; new helpers must stay below 15. Check the diff contains no modification to `notify_closed_trades`, automatic monitor callers, or `embeds.py` re-exports. Existing automatic sender tests intentionally accept a fake send with no message ID; only the new durable sender requires one.

- [ ] **Step 5: Commit the verified adapter.** After controller review and freshness checks, stage `swingbot/core/scanning/lifecycle_notifications.py` and `tests/scanning/test_lifecycle_notifications.py`; commit `feat(v197): render recorded lifecycle notifications and return message IDs`. The plan author does not execute this step.

### Task V197-6: Replace destructive drain with bounded durable delivery ticks
**Model:** sonnet — isolated worker integration over the frozen lease and sender contracts.

**Files:** Create `swingbot/commands/scanning/lifecycle_delivery.py` and `tests/commands/test_lifecycle_delivery.py`. V197-6b wires the verified worker into the watcher and replaces the old destructive-drain tests; keep this task independently reviewable.

**Interfaces:** Consume V197-5 `send_lifecycle_notification(bot, event) -> str` and `BlockedDelivery(code)`; V197-2/2b `notify_queue_repo()`, `claim_one(owner, *, now, conn=None)`, `acknowledge(event_id, token, message_id, *, now, conn=None)`, `reschedule(event_id, token, *, now, delay_s, error_code, blocked, conn=None)`, and `prune_delivered(*, now, conn=None)`. Produce `async deliver_lifecycle_tick(bot, *, repo=None, now=None) -> dict[str, int]`; optional `now` is a zero-argument aware datetime clock, not one frozen datetime. Count keys are `attempted`, `acknowledged`, `retried`, `blocked`. Only attempted overlaps an outcome count; outcome categories are mutually exclusive. No outcome is counted when fenced persistence returns False or raises.

- [ ] **Step 1: Add the worker unit tests.** The fake repository below checks sequencing and counter semantics only. Real lease fencing, independent-connection concurrency, restart and acknowledgement-after-send failure coverage remain in V197-2 and final V197-8; do not replace those with this fake.

```python
import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from swingbot.commands.scanning import lifecycle_delivery as delivery
from swingbot.core.scanning.lifecycle_notifications import BlockedDelivery

AT = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def claimed(index=1, attempt=1):
    return dict(event_id=f"E{index}", kind="trade_closed", lease_token=f"token{index}",
                queued_at=AT.isoformat(), attempt_count=attempt)


class Repo:
    def __init__(self, events=()):
        self.events = deque(events)
        self.trace = []
        self.acks = []
        self.retries = []
        self.claims = []
        self.prunes = []
        self.ack_result = True
        self.retry_result = True

    def claim_one(self, owner, *, now):
        self.claims.append((owner, now))
        event = self.events.popleft() if self.events else None
        self.trace.append(("claim", None if event is None else event["event_id"]))
        return event

    def acknowledge(self, event_id, token, message_id, *, now):
        self.trace.append(("ack", event_id))
        self.acks.append((event_id, token, message_id, now))
        if isinstance(self.ack_result, Exception):
            raise self.ack_result
        return self.ack_result

    def reschedule(self, event_id, token, *, now, delay_s, error_code, blocked):
        self.trace.append(("retry", event_id))
        self.retries.append(dict(event_id=event_id, token=token, now=now, delay_s=delay_s,
                                 error_code=error_code, blocked=blocked))
        if isinstance(self.retry_result, Exception):
            raise self.retry_result
        return self.retry_result

    def prune_delivered(self, *, now):
        self.prunes.append(now)
        return 0


def run(repo, monkeypatch, sender, *, clock=lambda: AT):
    monkeypatch.setattr(delivery, "send_lifecycle_notification", sender)
    return asyncio.run(delivery.deliver_lifecycle_tick(object(), repo=repo, now=clock))


def test_empty_tick_prunes_once_and_logs_distinct_counts(monkeypatch, caplog):
    repo = Repo()
    sender = AsyncMock()
    with caplog.at_level(logging.INFO, logger=delivery.__name__):
        counts = run(repo, monkeypatch, sender)
    assert counts == dict(attempted=0, acknowledged=0, retried=0, blocked=0)
    assert len(repo.prunes) == 1
    sender.assert_not_awaited()
    assert "attempted=0 acknowledged=0 retried=0 blocked=0" in caplog.text


def test_claim_send_ack_order_and_twenty_event_bound(monkeypatch):
    repo = Repo(claimed(index) for index in range(21))

    async def send(bot, event):
        repo.trace.append(("send", event["event_id"]))
        return "discord-" + event["event_id"]

    counts = run(repo, monkeypatch, send)
    assert counts == dict(attempted=20, acknowledged=20, retried=0, blocked=0)
    assert len(repo.events) == 1
    assert len(repo.claims) == 20
    assert len({owner for owner, at in repo.claims}) == 1
    for index in range(20):
        assert repo.trace[index * 3:index * 3 + 3] == [
            ("claim", f"E{index}"), ("send", f"E{index}"), ("ack", f"E{index}")]
    assert repo.acks[0][:3] == ("E0", "token0", "discord-E0")


def test_tick_identity_and_completion_clock_are_fresh(monkeypatch):
    repo = Repo([claimed()])
    times = iter(AT + timedelta(seconds=value) for value in range(10))
    run(repo, monkeypatch, AsyncMock(return_value="42"), clock=lambda: next(times))
    assert repo.acks[0][3] > repo.claims[0][1]
    owner = repo.claims[0][0]
    second = Repo()
    run(second, monkeypatch, AsyncMock())
    assert second.claims[0][0] != owner


@pytest.mark.parametrize("attempt,delay", [(1, 5), (2, 15), (3, 60), (4, 300),
                                           (5, 900), (1000, 900)])
def test_retry_schedule_uses_persisted_attempt_count(monkeypatch, attempt, delay):
    repo = Repo([claimed(attempt=attempt)])
    counts = run(repo, monkeypatch, AsyncMock(side_effect=OSError("private details")))
    assert counts == dict(attempted=1, acknowledged=0, retried=1, blocked=0)
    assert repo.retries[0]["delay_s"] == delay
    assert repo.retries[0]["error_code"] == "network_error"
    assert repo.retries[0]["token"] == "token1"
    assert not repo.acks


@pytest.mark.parametrize("blocked,expected", [(False, 1500), (True, 1500)])
def test_long_retry_after_wins_even_for_blocked_events(monkeypatch, blocked, expected):
    error = BlockedDelivery("permission_denied") if blocked else OSError("private")
    error.retry_after = 1500
    repo = Repo([claimed()])
    counts = run(repo, monkeypatch, AsyncMock(side_effect=error))
    assert repo.retries[0]["delay_s"] == expected
    assert counts["blocked" if blocked else "retried"] == 1


@pytest.mark.parametrize("hint", [None, "1200", True, -3, float("inf"), float("nan")])
def test_invalid_retry_hint_cannot_corrupt_schedule(monkeypatch, hint):
    error = OSError("private")
    error.retry_after = hint
    repo = Repo([claimed()])
    run(repo, monkeypatch, AsyncMock(side_effect=error))
    assert repo.retries[0]["delay_s"] == 5


def test_blocked_event_is_retained_and_next_event_still_sends(monkeypatch):
    repo = Repo([claimed(1), claimed(2)])
    sender = AsyncMock(side_effect=[BlockedDelivery("permission_denied"), "42"])
    counts = run(repo, monkeypatch, sender)
    assert counts == dict(attempted=2, acknowledged=1, retried=0, blocked=1)
    assert repo.retries[0]["delay_s"] == 900
    assert repo.retries[0]["blocked"] is True
    assert repo.acks[0][0] == "E2"


@pytest.mark.parametrize("result", [False, RuntimeError("private db password")])
def test_failed_ack_does_not_reschedule_or_claim_success(monkeypatch, caplog, result):
    repo = Repo([claimed(1), claimed(2)])
    repo.ack_result = result
    counts = run(repo, monkeypatch, AsyncMock(return_value="42"))
    assert counts == dict(attempted=2, acknowledged=0, retried=0, blocked=0)
    assert len(repo.acks) == 2
    assert not repo.retries  # leave intent leased for expiration after ambiguous acceptance
    assert "private db password" not in caplog.text
    if isinstance(result, Exception):
        assert "ack_storage_failed" in caplog.text


@pytest.mark.parametrize("result", [False, RuntimeError("private db password")])
def test_failed_reschedule_is_isolated_and_not_counted(monkeypatch, caplog, result):
    repo = Repo([claimed(1), claimed(2)])
    repo.retry_result = result
    counts = run(repo, monkeypatch, AsyncMock(side_effect=[OSError("private"), "42"]))
    assert counts == dict(attempted=2, acknowledged=1, retried=0, blocked=0)
    assert "private db password" not in caplog.text


def test_entire_sender_is_wrapped_in_thirty_second_timeout(monkeypatch):
    repo = Repo([claimed()])
    observed = []

    async def timeout(awaitable, *, timeout):
        observed.append(timeout)
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(delivery.asyncio, "wait_for", timeout)
    counts = run(repo, monkeypatch, AsyncMock(return_value="42"))
    assert observed == [30]
    assert counts["retried"] == 1
    assert repo.retries[0]["error_code"] == "send_timeout"
    assert not repo.acks


def test_cancellation_propagates_and_leaves_claim_unsettled(monkeypatch):
    repo = Repo([claimed()])
    with pytest.raises(asyncio.CancelledError):
        run(repo, monkeypatch, AsyncMock(side_effect=asyncio.CancelledError()))
    assert not repo.acks and not repo.retries


def test_claim_storage_outage_stops_tick_without_raw_error(monkeypatch, caplog):
    repo = Repo()

    def fail(owner, *, now):
        raise RuntimeError("private DSN")

    monkeypatch.setattr(repo, "claim_one", fail)
    sender = AsyncMock()
    counts = run(repo, monkeypatch, sender)
    assert counts["attempted"] == 0
    sender.assert_not_awaited()
    assert "claim_storage_failed" in caplog.text and "private DSN" not in caplog.text


def test_prune_storage_outage_does_not_block_delivery(monkeypatch, caplog):
    repo = Repo([claimed()])

    def fail(*, now):
        raise RuntimeError("private DSN")

    monkeypatch.setattr(repo, "prune_delivered", fail)
    counts = run(repo, monkeypatch, AsyncMock(return_value="42"))
    assert counts["acknowledged"] == 1
    assert "prune_storage_failed" in caplog.text and "private DSN" not in caplog.text
```

- [ ] **Step 2: Run the narrow red tests.** Run `python scripts/dev/testrun.py file tests/commands/test_lifecycle_delivery.py`; expect the new module import failure. If test fixtures access the database, invoke replicate-prod-db and point `DATABASE_URL` at the shared replica as required by the index. Never execute that preflight while merely authoring the plan.

- [ ] **Step 3: Create the bounded worker.** Use these complete helpers in `swingbot/commands/scanning/lifecycle_delivery.py`. Repository calls do not receive `conn`: each method owns and commits its short transaction before returning. No claim transaction encloses a Discord await. Logging deliberately avoids `exc_info`, exception interpolation and payloads. Repository `reschedule` owns blocked-transition ERROR logging; do not duplicate it on every already-blocked retry.

```python
"""One-at-a-time delivery of durable lifecycle notifications."""
import asyncio
import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

import discord

from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.scanning.lifecycle_notifications import (
    BlockedDelivery, send_lifecycle_notification,
)

log = logging.getLogger(__name__)
_DELAYS = (5, 15, 60, 300, 900)


def _failure(error):
    if isinstance(error, BlockedDelivery):
        return error.code, True
    if isinstance(error, TimeoutError):
        return "send_timeout", False
    if isinstance(error, OSError):
        return "network_error", False
    if isinstance(error, discord.HTTPException):
        return "discord_http_error", False
    return "send_failed", False


def _delay(event, error, blocked):
    attempt = max(1, int(event.get("attempt_count", 1)))
    base = 900 if blocked else _DELAYS[min(attempt - 1, len(_DELAYS) - 1)]
    hint = getattr(error, "retry_after", None)
    if isinstance(hint, bool) or not isinstance(hint, (int, float)):
        return base
    return max(base, hint) if math.isfinite(hint) else base


def _prune(repo, clock):
    try:
        repo.prune_delivered(now=clock())
    except Exception:
        log.error("lifecycle delivery cause=prune_storage_failed")


def _claim(repo, owner, clock):
    try:
        return repo.claim_one(owner, now=clock())
    except Exception:
        log.error("lifecycle delivery cause=claim_storage_failed")
        return None


def _acknowledge(repo, event, message_id, clock):
    try:
        committed = repo.acknowledge(event["event_id"], event["lease_token"],
                                     message_id, now=clock())
    except Exception:
        log.error("lifecycle delivery event=%s cause=ack_storage_failed", event["event_id"])
        return None
    if not committed:
        log.warning("lifecycle delivery event=%s cause=stale_ack", event["event_id"])
        return None
    return "acknowledged"


def _reschedule(repo, event, error, clock):
    code, blocked = _failure(error)
    try:
        committed = repo.reschedule(event["event_id"], event["lease_token"], now=clock(),
                                    delay_s=_delay(event, error, blocked),
                                    error_code=code, blocked=blocked)
    except Exception:
        log.error("lifecycle delivery event=%s cause=retry_storage_failed", event["event_id"])
        return None
    if not committed:
        log.warning("lifecycle delivery event=%s cause=stale_retry", event["event_id"])
        return None
    return "blocked" if blocked else "retried"


async def _deliver_one(bot, repo, event, clock):
    try:
        message_id = await asyncio.wait_for(send_lifecycle_notification(bot, event), timeout=30)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return _reschedule(repo, event, error, clock)
    return _acknowledge(repo, event, message_id, clock)


async def deliver_lifecycle_tick(bot, *, repo=None, now=None) -> dict[str, int]:
    queue = notify_queue_repo() if repo is None else repo
    clock = now if now is not None else lambda: datetime.now(timezone.utc)
    owner = str(uuid4())
    counts = dict(attempted=0, acknowledged=0, retried=0, blocked=0)
    _prune(queue, clock)
    try:
        for _ in range(20):
            event = _claim(queue, owner, clock)
            if event is None:
                break
            counts["attempted"] += 1
            outcome = await _deliver_one(bot, queue, event, clock)
            if outcome is not None:
                counts[outcome] += 1
    finally:
        log.info("lifecycle delivery attempted=%d acknowledged=%d retried=%d blocked=%d",
                 counts["attempted"], counts["acknowledged"], counts["retried"], counts["blocked"])
    return counts
```

- [ ] **Step 4: Verify the worker narrowly.** Run `python scripts/dev/testrun.py file tests/commands/test_lifecycle_delivery.py`; require 0 failed and 0 xfailed. Run `python scripts/dev/complexity_gate.py`; helpers must remain below 15. The worker makes no caller-connection repository calls and no network operation occurs inside its claim transaction. Do not run a full suite here.

- [ ] **Step 5: Commit the verified delivery worker.** After controller review and freshness checks, stage `swingbot/commands/scanning/lifecycle_delivery.py` and `tests/commands/test_lifecycle_delivery.py`; commit `feat(v197): deliver lifecycle events with fenced outcomes`. The plan author does not execute this step.

### Task V197-6b: Wire durable delivery into the existing watcher
**Model:** sonnet — narrow watcher adapter and replacement of destructive-drain regressions.

**Files:** Modify `swingbot/commands/scanning/loops.py`, `tests/commands/test_manual_close_queue_db.py`, and `tests/commands/test_manual_close_queue_dual.py`.

**Interfaces:** Consume V197-6 `async deliver_lifecycle_tick(bot, *, repo=None, now=None) -> dict[str, int]`; V197-1 `make_event(*, transition_id, kind, target_channel_id, occurred_at, payload)`; V197-2 `NotifyQueueRepository.enqueue`, `claim_one`, `acknowledge`, `pending`, and inherited `count`. Retain `_post_manual_close_queue() -> None` as the current watcher seam. Remove `_take_manual_close_queue` and `_with_trade_id_as_id`, both obsolete after immutable nested snapshots replace flat legacy rows. V197-2 already removed the repository drain method.

- [ ] **Step 1: Replace destructive-drain regressions with retained intent and wiring checks.** Replace the contents of `tests/commands/test_manual_close_queue_db.py` with the following DB-backed tests. They use caller connections for rollback isolation; the runtime worker never does so. Deduplication tests distinguish a replay of one transition from two distinct transitions on the same trade.

```python
from datetime import datetime, timedelta, timezone

from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.infra.lifecycle_events import make_event

AT = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def event(transition="transition-1", at=AT):
    payload = dict(ticker="NVDA", direction="bullish", plan_id="P1", trade_id=None,
                   prior_status="PENDING", new_status="CANCELLED", reason="manual",
                   occurred_at=at.isoformat())
    return make_event(transition_id=transition, kind="plan_transition", target_channel_id="5",
                      occurred_at=at.isoformat(), payload=payload)


def test_empty_queue_has_nothing_to_claim(db_conn):
    repo = NotifyQueueRepository()
    assert repo.claim_one("worker", now=AT, conn=db_conn) is None
    assert repo.pending(conn=db_conn) == 0
    assert not hasattr(repo, "drain")


def test_claim_retains_pending_until_acknowledged(db_conn):
    repo = NotifyQueueRepository()
    notice = event()
    repo.enqueue(notice, conn=db_conn)
    claimed = repo.claim_one("worker", now=AT, conn=db_conn)
    assert claimed["event_id"] == notice["event_id"]
    assert repo.pending(conn=db_conn) == 1
    assert repo.claim_one("another", now=AT, conn=db_conn) is None
    assert repo.acknowledge(claimed["event_id"], claimed["lease_token"], "42",
                            now=AT + timedelta(seconds=1), conn=db_conn)
    assert repo.pending(conn=db_conn) == 0
    assert repo.count(conn=db_conn) == 1  # retained receipt, not DELETE-on-send


def test_same_transition_deduplicates_distinct_transitions_do_not(db_conn):
    repo = NotifyQueueRepository()
    repo.enqueue(event(), conn=db_conn)
    repo.enqueue(event(), conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    repo.enqueue(event("transition-2"), conn=db_conn)
    assert repo.pending(conn=db_conn) == 2


def test_due_events_are_claimed_oldest_first(db_conn):
    repo = NotifyQueueRepository()
    newest = event("new", AT + timedelta(seconds=1))
    oldest = event("old", AT)
    repo.enqueue(newest, conn=db_conn)
    repo.enqueue(oldest, conn=db_conn)
    first = repo.claim_one("worker", now=AT + timedelta(seconds=2), conn=db_conn)
    second = repo.claim_one("worker", now=AT + timedelta(seconds=2), conn=db_conn)
    assert [first["event_id"], second["event_id"]] == [oldest["event_id"], newest["event_id"]]
    assert repo.pending(conn=db_conn) == 2
```

Replace `tests/commands/test_manual_close_queue_dual.py` with these focused adapter checks. Real producer-to-Discord integration is V197-8's responsibility; this module proves that the old watcher delegates and cannot call the destructive or automatic path.

```python
import asyncio
from unittest.mock import AsyncMock

from swingbot.commands.scanning import lifecycle_delivery, loops


def test_watcher_delegates_to_durable_tick(monkeypatch):
    worker = AsyncMock(return_value=dict(attempted=1, acknowledged=0, retried=1, blocked=0))
    bot = object()
    monkeypatch.setattr(loops, "bot", bot)
    monkeypatch.setattr(lifecycle_delivery, "deliver_lifecycle_tick", worker)
    automatic = AsyncMock(side_effect=AssertionError("automatic path must remain separate"))
    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", automatic)
    asyncio.run(loops._post_manual_close_queue())
    worker.assert_awaited_once_with(bot)
    automatic.assert_not_awaited()
    assert not hasattr(loops, "_take_manual_close_queue")
    assert not hasattr(loops, "_with_trade_id_as_id")
```

- [ ] **Step 2: Run the narrow red adapter test.** Run `python scripts/dev/testrun.py file tests/commands/test_manual_close_queue_dual.py`; the old adapter must fail the delegation and no-destructive-path assertions. Before DB-backed tests, invoke replicate-prod-db into shared swing-db and use its replica DATABASE_URL. Do not execute database preflight while authoring this plan.

- [ ] **Step 3: Replace the consumer adapter.** Replace only the complete `_with_trade_id_as_id`, `_take_manual_close_queue`, and `_post_manual_close_queue` block in `swingbot/commands/scanning/loops.py` with the following. Keep `config_watcher`'s current call and cadence. The immutable nested trade retains its own `id`, so the old infrastructure-ID adapter is obsolete. Do not route automatic monitor notifications through this worker.

```python
async def _post_manual_close_queue() -> None:
    from swingbot.commands.scanning.lifecycle_delivery import deliver_lifecycle_tick
    await deliver_lifecycle_tick(bot)
```

- [ ] **Step 4: Verify the adapter narrowly.** Run `python scripts/dev/testrun.py file tests/commands/test_manual_close_queue_db.py` and `python scripts/dev/testrun.py file tests/commands/test_manual_close_queue_dual.py`; require 0 failed and 0 xfailed. Run `python scripts/dev/complexity_gate.py`. Search `git grep -n -E '_take_manual_close_queue|_with_trade_id_as_id|notify_queue_repo\(\)\.drain|Posted .*manually-closed' -- swingbot`; expect no match (exit 1). Inspect the consumer diff to confirm the automatic monitor callsites and 30-second watcher cadence are unchanged. Do not run a full suite here.

- [ ] **Step 5: Commit the verified watcher integration.** After controller review and freshness checks, stage `swingbot/commands/scanning/loops.py`, `tests/commands/test_manual_close_queue_db.py`, and `tests/commands/test_manual_close_queue_dual.py`; commit `feat(v197): replace destructive watcher drain with durable delivery`. The plan author does not execute this step.
