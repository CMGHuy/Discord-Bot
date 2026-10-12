"""Follower notices and retries remain independent of Discord feed delivery."""
import asyncio
import logging

import pytest

from swingbot.commands.scanning import follow_notify, loops
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.scanning import embeds


@pytest.fixture
def posting(monkeypatch):
    events = [PlanEvent("p1", "be_moved", {"working_stop": 100.0})]
    deliveries = [Delivery("p1", "stop", 100.0)]
    calls = []

    async def feed(bot, received):
        assert bot is loops.bot
        assert received == events
        calls.append("feed")
        return deliveries

    async def followers(bot, received):
        assert bot is loops.bot
        assert received == events
        calls.append("followers")

    def ack(received):
        assert received == deliveries
        calls.append("ack")

    monkeypatch.setattr(embeds, "notify_plan_events", feed)
    monkeypatch.setattr(follow_notify, "notify_followers", followers)
    monkeypatch.setattr(plan_manager, "ack_notified", ack)
    return events, deliveries, calls


def test_feed_then_followers_then_ack(posting):
    events, _, calls = posting
    asyncio.run(loops._post_plan_events(events))
    assert calls == ["feed", "followers", "ack"]


def test_feed_failure_still_notifies_followers_without_ack(monkeypatch, posting, caplog):
    events, _, calls = posting

    async def feed(bot, received):
        calls.append("feed")
        raise RuntimeError("feed unavailable")

    monkeypatch.setattr(embeds, "notify_plan_events", feed)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops._post_plan_events(events))
    assert calls == ["feed", "followers"]
    assert "feed unavailable" in caplog.text


def test_empty_feed_still_notifies_followers(monkeypatch, posting):
    events, _, calls = posting

    async def feed(bot, received):
        calls.append("feed")
        return []

    monkeypatch.setattr(embeds, "notify_plan_events", feed)
    asyncio.run(loops._post_plan_events(events))
    assert calls == ["feed", "followers"]


def test_follower_failure_still_acks_feed(monkeypatch, posting, caplog):
    events, _, calls = posting

    async def followers(bot, received):
        calls.append("followers")
        raise RuntimeError("follower unavailable")

    monkeypatch.setattr(follow_notify, "notify_followers", followers)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops._post_plan_events(events))
    assert calls == ["feed", "followers", "ack"]
    assert "follower unavailable" in caplog.text


def test_ack_failure_is_logged_and_contained(monkeypatch, posting, caplog):
    events, _, calls = posting

    def ack(received):
        raise RuntimeError("ack unavailable")

    monkeypatch.setattr(plan_manager, "ack_notified", ack)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops._post_plan_events(events))
    assert calls == ["feed", "followers"]
    assert "ack unavailable" in caplog.text


def test_post_feed_returns_deliveries(posting):
    events, deliveries, calls = posting
    assert asyncio.run(loops._post_feed(events)) == deliveries
    assert calls == ["feed"]


def test_post_feed_failure_returns_empty(monkeypatch, posting, caplog):
    events, _, _ = posting

    async def feed(bot, received):
        raise RuntimeError("feed unavailable")

    monkeypatch.setattr(embeds, "notify_plan_events", feed)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        assert asyncio.run(loops._post_feed(events)) == []
    assert "feed unavailable" in caplog.text


def _monitor_setup(monkeypatch, events, calls):
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda **kwargs: [])
    monkeypatch.setattr(plan_manager, "run_manager_tick", lambda: events)

    async def retry(bot):
        assert bot is loops.bot
        calls.append("sweep")

    monkeypatch.setattr(follow_notify, "retry_pending_notifications", retry)


def test_empty_monitor_tick_sweeps_once(monkeypatch):
    calls = []
    _monitor_setup(monkeypatch, [], calls)
    asyncio.run(loops.trade_monitor.coro())
    assert calls == ["sweep"]


def test_monitor_posts_feed_followers_then_sweeps(monkeypatch, posting):
    events, _, calls = posting
    _monitor_setup(monkeypatch, events, calls)
    asyncio.run(loops.trade_monitor.coro())
    assert calls == ["feed", "followers", "ack", "sweep"]


def test_retry_failure_is_logged_and_contained(monkeypatch, caplog):
    calls = []
    _monitor_setup(monkeypatch, [], calls)

    async def retry(bot):
        calls.append("sweep")
        raise RuntimeError("retry unavailable")

    monkeypatch.setattr(follow_notify, "retry_pending_notifications", retry)
    with caplog.at_level(logging.WARNING, logger=loops.__name__):
        asyncio.run(loops.trade_monitor.coro())
    assert calls == ["sweep"]
    assert "retry unavailable" in caplog.text
