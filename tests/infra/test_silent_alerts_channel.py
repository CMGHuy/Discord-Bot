"""
DISCORD_CHANNEL_TRADES_ID never notifies.

The policy is enforced by wrapping the resolved channel in SilentChannel
(swingbot/core/silent_channel.py) rather than by passing silent=True at each
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
from swingbot.core.infra.silent_channel import SilentChannel, silence


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
    monkeypatch.setattr(scanning_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: raw), raising=False)
    monkeypatch.setattr(scanning_mod, "is_scan_paused", lambda: True, raising=False)

    captured = {}

    async def _capture(channel):
        captured["channel"] = channel

    monkeypatch.setattr(scanning_mod, "_check_session_transition", _capture, raising=False)
    monkeypatch.setattr(scanning_mod, "_refresh_presence", lambda: asyncio.sleep(0), raising=False)
    monkeypatch.setattr(scanning_mod, "_write_heartbeat", lambda: None, raising=False)

    asyncio.run(scanning_mod._session_scan_tick())

    assert isinstance(captured["channel"], SilentChannel)
