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
