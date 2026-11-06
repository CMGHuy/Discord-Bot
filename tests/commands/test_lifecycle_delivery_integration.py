import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from swingbot import config
# Import the Flask app first: api_v1 modules import each other circularly otherwise.
import swingbot.admin.app  # noqa: F401
from swingbot.admin.api_v1 import lifecycle_commands as commands
from swingbot.admin.api_v1 import trade_commands
from swingbot.commands.scanning.lifecycle_delivery import deliver_lifecycle_tick
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade

PLAN = "19700000-0000-4000-8000-000000000001"
TRADE = "v197-integration-trade"


@pytest.fixture
def book(store_db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(trade_commands, "_override_stamp",
                        lambda ticker: {"exit_price": 102.0, "price_source": "quote"})
    monkeypatch.setattr(commands, "_manual_close_quote", lambda ticker: 102.0)
    monkeypatch.setattr(commands.rp, "cached_daily_bars", lambda ticker: None)
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", lambda self, trade: None)
    AccountRepository().save(dict(base_balance=1000.0, balance=1000.0))
    return NotifyQueueRepository()


def produce(kind):
    if kind == "cancel":
        PlanRepository().insert(_plan(PLAN, status="PENDING"))
        commands.cancel_plan_atomic(PLAN)
        return
    if kind == "plan_close":
        PlanRepository().insert(_plan(PLAN, status="ACTIVE"))
        TradeRepository().insert(performance._db_record(_trade(TRADE, plan_id=PLAN)))
        commands.close_plan_atomic(PLAN)
        return
    TradeRepository().insert(performance._db_record(_trade(TRADE)))
    commands.close_legacy_atomic(TRADE)


class Channel:
    def __init__(self, error=None):
        self.sent = []
        self.error = error

    async def send(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)
        return SimpleNamespace(id=1000 + len(self.sent))


def bot(channel):
    async def fetch(channel_id):
        return channel

    return SimpleNamespace(get_channel=lambda channel_id: channel, fetch_channel=fetch)


def row(repo):
    rows = repo.list_all()
    assert len(rows) == 1
    return rows[0]


def tick(repo, channel, now):
    return asyncio.run(deliver_lifecycle_tick(bot(channel), repo=repo, now=lambda: now))


def instant(event):
    return datetime.fromisoformat(event["queued_at"])


def assert_notification_snapshot(channel, original, kind, title):
    assert len(channel.sent) == 1
    embed = channel.sent[0]["embed"]
    assert channel.sent[0]["content"] == embed.push_text
    assert embed.footer.text.endswith("Event " + original["event_id"])
    if title is not None:
        assert embed.title.startswith(title)
    if kind == "cancel":
        assert "Result" not in {field.name for field in embed.fields}
        assert "unfilled" in embed.description.lower()
        assert AccountRepository().load()["balance"] == 1000.0


def assert_delivery_receipt(book, original):
    receipt = row(book)
    assert receipt["payload"] == original["payload"]
    assert receipt["delivered_message_id"] == "1001"
    assert receipt["delivered_at"] is not None
    assert book.pending() == 0
    assert book.count() == 1


@pytest.mark.parametrize("kind,title", [("cancel", "Plan cancelled"),
                                        ("plan_close", "Plan closed"), ("legacy_close", None)])
def test_committed_action_reaches_discord_once_and_keeps_receipt(book, kind, title):
    produce(kind)
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel()
    counts = tick(book, channel, now)
    assert counts == dict(attempted=1, acknowledged=1, retried=0, blocked=0)
    assert_notification_snapshot(channel, original, kind, title)
    assert_delivery_receipt(book, original)
    assert tick(book, channel, now + timedelta(seconds=1))["attempted"] == 0
    assert len(channel.sent) == 1


def test_transient_send_failure_retries_the_same_recorded_snapshot(book):
    produce("legacy_close")
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel(OSError("private socket details"))
    first = tick(book, channel, now)
    assert first == dict(attempted=1, acknowledged=0, retried=1, blocked=0)
    pending = row(book)
    assert pending["payload"] == original["payload"]
    assert pending["event_id"] == original["event_id"]
    assert pending["last_error"] == "network_error"
    assert book.pending() == 1
    assert tick(book, channel, now + timedelta(seconds=4))["attempted"] == 0
    # A later edit of the source trade must never alter the queued snapshot.
    TradeRepository().patch(TRADE, {"exit_price": 999.0})
    channel.error = None
    assert tick(book, channel, now + timedelta(seconds=5))["acknowledged"] == 1
    fields = {field.name: field.value for field in channel.sent[0]["embed"].fields}
    assert "102.00" in fields["Exit"] and "999" not in fields["Exit"]
    assert row(book)["payload"] == original["payload"]
    assert row(book)["attempt_count"] == 2


def test_crash_after_claim_recovers_on_lease_expiry(book):
    produce("cancel")
    original = row(book)
    now = instant(original)
    abandoned = book.claim_one("dead-process", now=now)
    channel = Channel()
    assert tick(book, channel, now + timedelta(seconds=119))["attempted"] == 0
    assert book.pending() == 1
    assert tick(book, channel, now + timedelta(seconds=121))["acknowledged"] == 1
    assert row(book)["attempt_count"] == 2
    assert channel.sent[0]["embed"].footer.text.endswith("Event " + abandoned["event_id"])
    assert not book.acknowledge(abandoned["event_id"], abandoned["lease_token"], "stale",
                                now=now + timedelta(seconds=122))
    assert row(book)["delivered_message_id"] == "1001"


def test_database_failure_after_discord_acceptance_repeats_identifiable_event(book, monkeypatch):
    produce("plan_close")
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel()
    write = book._write

    def fail_ack(connection, event):
        write(connection, event)
        if event.get("delivered_at"):
            connection.execute(sa.text("SELECT 1 / 0"))

    with monkeypatch.context() as scoped:
        scoped.setattr(book, "_write", fail_ack)
        first = tick(book, channel, now)
    assert first == dict(attempted=1, acknowledged=0, retried=0, blocked=0)
    assert len(channel.sent) == 1
    pending = row(book)
    assert pending["delivered_at"] is None
    assert pending["delivered_message_id"] is None
    assert pending["lease_token"] is not None
    assert pending["payload"] == original["payload"]
    assert tick(book, channel, now + timedelta(seconds=119))["attempted"] == 0
    second = tick(book, channel, now + timedelta(seconds=121))
    assert second["acknowledged"] == 1 and len(channel.sent) == 2
    footers = [sent["embed"].footer.text for sent in channel.sent]
    assert footers[0] == footers[1]
    assert footers[0].endswith("Event " + original["event_id"])
    assert row(book)["delivered_message_id"] == "1002"
    assert row(book)["payload"] == original["payload"]


def test_unavailable_channel_stays_blocked_until_repaired(book):
    produce("cancel")
    now = instant(row(book))
    assert tick(book, None, now)["blocked"] == 1
    assert book.health(now=now) == dict(pending_count=1, oldest_pending_age_seconds=0.0,
                                       blocked_count=1)
    assert row(book)["last_error"] == "channel_unavailable"
    channel = Channel()
    assert tick(book, channel, now + timedelta(seconds=899))["attempted"] == 0
    assert tick(book, channel, now + timedelta(seconds=900))["acknowledged"] == 1
    assert row(book)["blocked"] is False
    assert book.health(now=now + timedelta(seconds=900))["pending_count"] == 0
