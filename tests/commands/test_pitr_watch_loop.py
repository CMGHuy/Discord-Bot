"""The PITR alarm loop posts to the ops channel once per episode."""
import asyncio
import datetime as dt

from swingbot.commands.scanning import loops
from swingbot.core.infra import pitr_watch

T = dt.datetime(2026, 10, 1, 10, 0, tzinfo=dt.timezone.utc)


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append({"content": content, **kw})


def _arm(monkeypatch, sample, used):
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops, "_PITR_WATCH", pitr_watch.PitrWatch())
    monkeypatch.setattr(pitr_watch, "read_archiver", lambda: sample)
    monkeypatch.setattr(pitr_watch, "disk_used_pct", lambda _path: used)
    return channel


def test_a_failing_archiver_posts_one_health_alert(monkeypatch):
    channel = _arm(monkeypatch, pitr_watch.ArchiverSample(4, T, T - dt.timedelta(minutes=9)), 20.0)
    asyncio.run(loops.pitr_watch_loop.coro())
    asyncio.run(loops.pitr_watch_loop.coro())
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "WAL archiving failing" in channel.sent[0]["embed"].title


def test_a_healthy_tick_posts_nothing(monkeypatch):
    channel = _arm(monkeypatch, pitr_watch.ArchiverSample(0, None, T), 20.0)
    asyncio.run(loops.pitr_watch_loop.coro())
    assert channel.sent == []


def test_the_loop_is_started_with_the_others():
    assert loops.pitr_watch_loop in loops._always_on_loops()
