"""
DISCORD_CHANNEL_TRADES_ID never notifies.

The policy is enforced by wrapping the resolved channel in SilentChannel
(swingbot/core/infra/silent_channel.py) rather than by passing silent=True at each
send site, so these tests cover both halves:

  * the proxy itself -- forces the flag on, overrides a caller that asked for
    silent=False, and is otherwise transparent (attribute delegation, the
    real Message comes back);
  * the wiring -- the alerts channel that _session_scan_tick resolves is
    wrapped, so a fully-charted alert posted through it is silent even when
    the simple mirror (which normally decides that) is switched off.

No pytest-asyncio in this repo (see tests/test_views.py) -- coroutines are
driven with asyncio.run().
"""
import asyncio
import types

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import _send_alerts
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import runstate
from swingbot.commands.scanning import presence
from swingbot.core.infra.silent_channel import SilentChannel, silence
from swingbot.core.scanning import engine as scan_engine


class FakeChannel:
    """Records the kwargs of every send and hands back a message stand-in."""

    def __init__(self, name="chan"):
        self.name = name
        self.id = 4242
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append({"args": args, "kwargs": kwargs})
        return types.SimpleNamespace(id=1)


# --------------------------------------------------------------------------
# SilentChannel
# --------------------------------------------------------------------------

def test_send_through_the_proxy_sets_the_suppress_notifications_flag():
    raw = FakeChannel()
    asyncio.run(SilentChannel(raw).send("hello"))

    assert raw.sent[0]["args"] == ("hello",)
    assert raw.sent[0]["kwargs"]["silent"] is True


def test_a_caller_asking_for_a_notification_is_overridden():
    """The whole contract is "nothing sent here pings" -- an explicit
    silent=False from a call site must not be able to punch through it."""
    raw = FakeChannel()
    asyncio.run(SilentChannel(raw).send("hello", silent=False))

    assert raw.sent[0]["kwargs"]["silent"] is True


def test_send_returns_the_real_message_object():
    """Callers keep the return value to edit or delete it later (the admin-UI
    progress message, the hourly healthcheck cleanup)."""
    msg = asyncio.run(SilentChannel(FakeChannel()).send("hi"))
    assert msg.id == 1


def test_every_other_attribute_delegates_to_the_wrapped_channel():
    raw = FakeChannel("alerts")
    wrapped = SilentChannel(raw)

    assert wrapped.id == 4242
    assert wrapped.name == "alerts"
    with pytest.raises(AttributeError):
        wrapped.definitely_not_a_channel_attribute


def test_a_wrapped_channel_still_compares_equal_to_the_raw_one():
    raw = FakeChannel()
    assert SilentChannel(raw) == raw


# --------------------------------------------------------------------------
# silence()
# --------------------------------------------------------------------------

def test_silence_passes_none_straight_through():
    """Call sites all branch on `channel is None` to log their own
    "channel not found" warning -- wrapping None would break every one."""
    assert silence(None) is None


def test_silence_is_idempotent():
    once = silence(FakeChannel())
    assert silence(once) is once


# --------------------------------------------------------------------------
# Wiring: the alerts channel is resolved through silence()
# --------------------------------------------------------------------------

def test_alerts_channel_is_silent_even_with_no_simple_mirror(monkeypatch):
    """Without the wrapper this is the case that would ping: no mirror
    configured means _send_alerts builds silent=False."""
    raw = FakeChannel("alerts")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)

    asyncio.run(_send_alerts(silence(raw), [("EMBED", None, None, "SIMPLE-TEXT")]))

    assert len(raw.sent) == 1
    assert raw.sent[0]["kwargs"]["silent"] is True


def test_a_non_alerts_destination_keeps_the_mirror_driven_policy(monkeypatch):
    """A user's own !check posts back to their ctx, which is NOT the alerts
    channel and must still notify when nothing else did."""
    ctx = FakeChannel("ctx")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)

    asyncio.run(_send_alerts(ctx, [("EMBED", None, None, "SIMPLE-TEXT")]))

    assert ctx.sent[0]["kwargs"]["silent"] is False


def test_the_scan_tick_wraps_the_channel_it_resolves(monkeypatch):
    """_session_scan_tick resolves DISCORD_CHANNEL_TRADES_ID once and hands
    the object to the session transition, the healthcheck and _send_alerts --
    so the wrap has to happen there, not at each of those call sites."""
    raw = FakeChannel("alerts")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "123", raising=False)
    monkeypatch.setattr(loops_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: raw), raising=False)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: True, raising=False)

    captured = {}

    async def _capture(channel):
        captured["channel"] = channel

    monkeypatch.setattr(presence, "_check_session_transition", _capture, raising=False)
    monkeypatch.setattr(presence, "_refresh_presence", lambda: asyncio.sleep(0), raising=False)
    monkeypatch.setattr(runstate, "_write_heartbeat", lambda: None, raising=False)

    asyncio.run(loops_mod._session_scan_tick())

    assert isinstance(captured["channel"], SilentChannel)


def test_the_scan_tick_actually_delivers_a_built_alert(monkeypatch):
    """Production incident (2026-08-28 -> 2026-09-02, five trading days with
    zero new alerts): the v61 refactor that moved _session_scan_tick into
    loops.py never carried an import of _send_alerts along with it. `from .
    import alerts` (the submodule) IS imported at module scope, but the local
    `alerts = await scan_engine.run_scan(...)` variable inside this function
    shadows that import, so even `alerts._send_alerts(...)` would have failed
    -- every tick that reached this point raised NameError, was swallowed by
    session_scan()'s outer try/except, and silently dropped the alert.

    Unlike test_the_scan_tick_wraps_the_channel_it_resolves above (which
    stops at the is_scan_paused() early return, before this line ever runs),
    this test drives the tick all the way through a scan that finds a
    scenario and asserts the alert actually reaches the channel."""
    raw = FakeChannel("alerts")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "123", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(loops_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: raw), raising=False)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: False, raising=False)
    monkeypatch.setattr(loops_mod, "in_session", lambda: True, raising=False)
    monkeypatch.setattr(runstate, "_write_heartbeat", lambda: None, raising=False)

    async def _noop(*args, **kwargs):
        pass

    monkeypatch.setattr(presence, "_check_session_transition", _noop, raising=False)
    monkeypatch.setattr(presence, "_refresh_presence", _noop, raising=False)
    monkeypatch.setattr(presence, "_post_healthcheck", _noop, raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_snapshot_safely", lambda: None, raising=False)

    built_alert = (types.SimpleNamespace(title="AAPL setup", footer=None), None, None, "SIMPLE-TEXT")

    async def fake_run_scan(**kwargs):
        return [built_alert]

    monkeypatch.setattr(scan_engine, "run_scan", fake_run_scan, raising=False)

    asyncio.run(loops_mod._session_scan_tick())

    assert len(raw.sent) == 1, (
        "the scenario the scan found must reach _send_alerts and get posted, "
        "not die to a NameError on '_send_alerts'"
    )
