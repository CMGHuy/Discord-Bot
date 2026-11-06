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
