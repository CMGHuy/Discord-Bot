"""Immutable lifecycle rendering snapshots; no database or network access."""
from copy import deepcopy
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from swingbot.core.market.shock import LABELS, SHOCK

#: v210: the v197 queue's event kinds; market_shock is a status notice, not a lifecycle event.
KINDS = ("trade_closed", "plan_transition", "market_shock")


def _identity(transition_id, kind):
    return str(uuid5(NAMESPACE_URL, f"swingbot:lifecycle:{transition_id}:{kind}"))


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_transition_time") from None
    if parsed.tzinfo is None:
        raise ValueError("invalid_transition_time")


def _validate_trade(payload):
    trade = payload.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("missing_trade_snapshot")
    pairs = (("id", "trade_id"), ("ticker", "ticker"), ("direction", "direction"),
             ("status", "new_status"))
    if any(not trade.get(a) or trade[a] != payload.get(b) for a, b in pairs):
        raise ValueError("inconsistent_trade_snapshot")
    if trade["status"] not in ("win", "loss", "closed") or "entry" not in trade:
        raise ValueError("invalid_trade_snapshot")


def _validate_payload(kind, payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    if kind == "market_shock":
        _validate_shock_payload(payload)
        return
    required = ("ticker", "direction", "prior_status", "new_status", "reason", "occurred_at")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
        raise ValueError("incomplete_payload")
    if payload["direction"] not in ("bullish", "bearish"):
        raise ValueError("invalid_direction")
    _aware(payload["occurred_at"])
    if kind == "trade_closed":
        _validate_trade(payload)
        return
    _validate_plan_transition(payload)


def _validate_plan_transition(payload):
    if not payload.get("plan_id") or payload["new_status"] not in ("CLOSED", "CANCELLED"):
        raise ValueError("invalid_plan_transition")
    if payload["new_status"] == "CANCELLED" and "trade" in payload:
        raise ValueError("cancelled_plan_has_fill")


def _validate_shock_payload(payload):
    """v210: a market-state transition notice (shock_notices.notice_payload)."""
    label, prior = payload.get("label"), payload.get("prior_label")
    if label not in LABELS or prior not in LABELS:
        raise ValueError("invalid_shock_label")
    if label == prior:
        raise ValueError("shock_notice_without_transition")
    _aware(payload.get("occurred_at"))
    if not isinstance(payload.get("reading"), dict):
        raise ValueError("invalid_shock_reading")
    unavailable = payload.get("open_longs_unavailable", False)
    if not isinstance(payload.get("open_longs"), list) or not isinstance(unavailable, bool):
        raise ValueError("invalid_open_longs")
    entry = payload.get("entry_into_shock")
    if not isinstance(entry, bool) or entry != (label == SHOCK):
        raise ValueError("invalid_entry_flag")


def validate_event(event: dict) -> None:
    kind = event.get("kind")
    if kind not in KINDS or not event.get("transition_id"):
        raise ValueError("invalid_event_kind_or_identity")
    if event.get("event_id") != _identity(event["transition_id"], kind):
        raise ValueError("invalid_event_identity")
    _aware(event.get("queued_at"))
    _validate_payload(kind, event.get("payload"))


def make_event(*, transition_id, kind, target_channel_id, occurred_at, payload) -> dict:
    channel = str(target_channel_id) if target_channel_id is not None else None
    if channel is not None and (not channel.isdecimal() or int(channel) <= 0):
        channel = None
    result = dict(event_id=_identity(transition_id, kind), transition_id=transition_id,
                  kind=kind, target_channel_id=channel, queued_at=occurred_at,
                  payload=deepcopy(payload), attempt_count=0, next_attempt_at=occurred_at,
                  lease_token=None, lease_owner=None, lease_until=None,
                  last_error=None if channel else "destination_unresolved", blocked=not bool(channel),
                  delivered_message_id=None, delivered_at=None, retarget_history=[])
    validate_event(result)
    return result
