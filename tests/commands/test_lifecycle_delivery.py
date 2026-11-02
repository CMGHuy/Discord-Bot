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
