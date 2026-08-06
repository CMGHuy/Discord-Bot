"""Plan v8 V32 Step 4 / cockpit-v3 C17: an admin plan cancel/close must reach
Discord.

`admin/pages.py:_queue_manual_close_notify` appends a
`{"kind": "plan_transition", **asdict(plan)}` entry to the manual-close queue.
`notify_closed_trades` drains that queue -- and used to accept only lowercase
trade statuses ("win"/"loss"/"closed") with no notion of `kind`, while a
TradePlanV2's status is uppercase ("CANCELLED"/"CLOSED"). Every such entry was
skipped. Worse than deferred: `commands/scanning.py` deletes the queue file
before calling this, so the notification was lost outright.
"""
import asyncio
import dataclasses

import pytest

import swingbot.config as config
from swingbot.core.scanning import embeds


def _plan_entry(status="CANCELLED", **kw):
    base = {"kind": "plan_transition", "plan_id": "abcdef1234", "ticker": "AAPL",
            "strategy": "Fibonacci", "horizon_key": "4w", "direction": "bullish",
            "entry_price": 100.0, "trigger_price": 100.0, "stop_loss": 95.0,
            "tp1": 110.0, "badge": "VALIDATED", "status": status}
    base.update(kw)
    return base


class _Channel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embed=None):
        self.sent.append((content, embed))


class _Bot:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, _id):
        return self._channel


@pytest.fixture
def channel(monkeypatch):
    ch = _Channel()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "123")
    return ch


def _drain(channel, entries):
    asyncio.run(embeds.notify_closed_trades(_Bot(channel), entries))
    return channel.sent


def test_a_cancelled_plan_is_posted(channel):
    sent = _drain(channel, [_plan_entry("CANCELLED")])
    assert len(sent) == 1, "the admin's cancel never reached Discord"
    assert "cancelled" in sent[0][1].title.lower()
    assert "AAPL" in sent[0][1].title


def test_a_closed_plan_is_posted(channel):
    sent = _drain(channel, [_plan_entry("CLOSED")])
    assert len(sent) == 1
    assert "closed" in sent[0][1].title.lower()


def test_an_unknown_plan_status_still_posts(channel):
    """The queue is written by a different process. An unrecognised status is
    a reason to post something generic, not to drop the operator's action."""
    sent = _drain(channel, [_plan_entry("SOMETHING_NEW")])
    assert len(sent) == 1


def test_ordinary_trade_entries_are_unchanged(channel):
    """The queue carries raw trade dicts too (app.py's close_trade route).
    Those must keep their existing header + embed exactly."""
    trade = {"id": "t1", "ticker": "MSFT", "status": "win", "strategy": "RSI",
             "direction": "bullish", "entry": 100.0, "exit_price": 110.0,
             "stop_loss": 95.0, "take_profit": 110.0, "horizon_key": "4w",
             "opened_at": "2026-08-01T00:00:00+00:00",
             "closed_at": "2026-08-02T00:00:00+00:00"}
    sent = _drain(channel, [trade])
    assert len(sent) == 1
    assert sent[0][0].startswith("✅ WIN")


def test_a_still_open_trade_is_still_skipped(channel):
    assert _drain(channel, [{"id": "t2", "ticker": "X", "status": "open"}]) == []


def test_a_real_plan_dataclass_round_trips(channel):
    """Guards the actual wire format: whatever `dataclasses.asdict` produces
    for a real TradePlanV2 must render, not just the hand-written dict above."""
    from tests.test_plan_engine_model import _plan
    entry = {"kind": "plan_transition", **dataclasses.asdict(_plan())}
    entry["status"] = "CANCELLED"
    sent = _drain(channel, [entry])
    assert len(sent) == 1
    assert sent[0][1].footer.text.startswith("v2 plan ")
