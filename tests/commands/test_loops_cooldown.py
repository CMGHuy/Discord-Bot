"""v152 D3 in the scheduler: only the scheduled scan applies the cooldown,
it posts one silent ops line when it held alerts, and daily_recap prunes
alert_posts once a day. The halt re-post, the admin-UI scan, !check and the
outlook post never pass apply_cooldown."""
import asyncio
import datetime as dt
import inspect
import logging
import threading
import types

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import commands, cooldown, outlook, presence, runstate
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db import write_failure
from swingbot.core.scanning import engine as scan_engine


class FakeChannel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


def _plan(ticker="AAPL"):
    return types.SimpleNamespace(plan_id="9d4c3b2a-1f0e-4d8c-b7a6-5e4f3a2b1c0d", ticker=ticker,
                                 direction="bullish", horizon_key="4w")


@pytest.fixture(autouse=True)
def _hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 24.0, raising=False)


def _scan_tick_env(monkeypatch, send_then_short):
    raw = FakeChannel()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "123", raising=False)
    monkeypatch.setattr(loops_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: raw), raising=False)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: False, raising=False)
    monkeypatch.setattr(loops_mod, "in_session", lambda: True, raising=False)
    monkeypatch.setattr(runstate, "_write_heartbeat", lambda: None, raising=False)

    async def _noop(*args, **kwargs):
        pass

    async def fake_run_scan(**kwargs):
        return [(types.SimpleNamespace(title="AAPL setup", footer=None), None, None)]

    monkeypatch.setattr(presence, "_check_session_transition", _noop, raising=False)
    monkeypatch.setattr(presence, "_refresh_presence", _noop, raising=False)
    monkeypatch.setattr(presence, "_post_healthcheck", _noop, raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_snapshot_safely", lambda: None, raising=False)
    monkeypatch.setattr(scan_engine, "run_scan", fake_run_scan, raising=False)
    monkeypatch.setattr(loops_mod, "send_then_short", send_then_short)


def test_the_scheduled_tick_applies_the_cooldown_and_posts_its_note(monkeypatch):
    held_plan, calls, notes = _plan(), [], []

    async def fake_send_then_short(channel, alerts, **kwargs):
        calls.append(kwargs)
        return [held_plan]

    async def fake_note(held):
        notes.append(held)

    _scan_tick_env(monkeypatch, fake_send_then_short)
    monkeypatch.setattr(loops_mod, "_post_cooldown_note", fake_note)
    asyncio.run(loops_mod._session_scan_tick())
    assert calls == [{"bot": loops_mod.bot, "require_confirmation": True,
                      "route_by_confidence": True, "apply_cooldown": True}]
    assert notes == [[held_plan]]


def test_the_scheduled_tick_refreshes_the_snapshot_off_the_event_loop(monkeypatch):
    """build_snapshot runs ~22 bootstrap rows; it must never block the bot loop."""
    seen = {}

    async def fake_send_then_short(channel, alerts, **kwargs):
        seen["loop_thread"] = threading.get_ident()
        return []

    async def no_note(held):
        pass

    _scan_tick_env(monkeypatch, fake_send_then_short)
    monkeypatch.setattr(loops_mod, "_post_cooldown_note", no_note)
    monkeypatch.setattr(loops_mod, "_refresh_snapshot_safely",
                        lambda: seen.update(refresh_thread=threading.get_ident()))
    asyncio.run(loops_mod._session_scan_tick())
    assert "refresh_thread" in seen
    assert seen["refresh_thread"] != seen["loop_thread"]


def test_the_halt_repost_never_applies_the_cooldown_and_still_raises(monkeypatch):
    seen = []

    async def fake_send(channel, alerts, route_by_confidence=False, **kwargs):
        seen.append(kwargs)
        return []

    async def halted(**kwargs):
        raise write_failure.StoreWriteHalt("plan P2", alerts=["alert-1"])

    monkeypatch.setattr(loops_mod, "_send_alerts", fake_send)
    monkeypatch.setattr(loops_mod.scan_engine, "run_scan", halted)
    with pytest.raises(write_failure.StoreWriteHalt):
        asyncio.run(loops_mod._run_scan_posting_partial("chan", require_confirmation=True))
    assert seen == [{}]


def test_only_the_scheduled_tick_passes_apply_cooldown():
    assert inspect.getsource(loops_mod).count("apply_cooldown=True") == 1
    assert "apply_cooldown=True" in inspect.getsource(loops_mod._session_scan_tick)
    assert "apply_cooldown" not in inspect.getsource(loops_mod._run_scan_posting_partial)
    assert "apply_cooldown" not in inspect.getsource(loops_mod.config_watcher.coro)
    assert "apply_cooldown" not in inspect.getsource(commands)
    assert "apply_cooldown" not in inspect.getsource(outlook)


def test_no_held_alerts_post_no_note(monkeypatch):
    looked_up = []
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: looked_up.append(1))
    asyncio.run(loops_mod._post_cooldown_note([]))
    assert looked_up == []


def test_held_alerts_post_one_silent_line_on_the_ops_channel(monkeypatch):
    chan = FakeChannel()
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    held = [_plan(), _plan("MSFT")]
    asyncio.run(loops_mod._post_cooldown_note(held))
    assert chan.sent == [{"content": cooldown.held_note(held), "silent": True}]
    assert chan.sent[0]["content"].startswith("Cooldown held 2 alert(s) this scan: AAPL long 4w")


def test_a_failing_note_warns_and_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: FakeChannel(fail=True))
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_cooldown_note([_plan()]))
    assert any("held-alerts note" in r.getMessage() for r in caplog.records)


def test_no_ops_channel_posts_nothing_quietly(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: None)
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_cooldown_note([_plan()]))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _recap_at_trigger(monkeypatch, order, prune):
    now = dt.datetime(2026, 8, 24, 23, 15)        # Monday, at the recap trigger

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    async def post():
        order.append("retrospective")

    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    monkeypatch.setattr(cooldown, "prune", prune)


def test_daily_recap_prunes_alert_posts_once_after_the_retrospective(monkeypatch):
    order = []

    def prune(now=None):
        order.append("prune")
        return 3

    _recap_at_trigger(monkeypatch, order, prune)
    asyncio.run(scanning_mod.daily_recap.coro())
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    asyncio.run(scanning_mod.daily_recap.coro())          # same day: already fired
    assert order == ["retrospective", "prune"]


def test_a_failing_prune_is_logged_and_never_raises(monkeypatch, caplog):
    order = []

    def prune(now=None):
        raise RuntimeError("database is having a day")

    _recap_at_trigger(monkeypatch, order, prune)
    with caplog.at_level(logging.WARNING):
        asyncio.run(scanning_mod.daily_recap.coro())
    assert order == ["retrospective"]
    assert any("prune alert_posts" in r.getMessage() for r in caplog.records)
