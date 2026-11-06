"""One-at-a-time delivery of durable lifecycle notifications."""
import asyncio
import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

import discord

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.scanning.lifecycle_notifications import (
    BlockedDelivery, send_lifecycle_notification,
)

log = logging.getLogger(__name__)
_DELAYS = (5, 15, 60, 300, 900)


def _failure(error):
    if isinstance(error, BlockedDelivery):
        return error.code, True
    if isinstance(error, TimeoutError):
        return "send_timeout", False
    if isinstance(error, OSError):
        return "network_error", False
    if isinstance(error, discord.HTTPException):
        return "discord_http_error", False
    return "send_failed", False


def _delay(event, error, blocked):
    attempt = max(1, int(event.get("attempt_count", 1)))
    base = 900 if blocked else _DELAYS[min(attempt - 1, len(_DELAYS) - 1)]
    hint = getattr(error, "retry_after", None)
    if isinstance(hint, bool) or not isinstance(hint, (int, float)):
        return base
    return max(base, hint) if math.isfinite(hint) else base


def _prune(repo, clock):
    try:
        repo.prune_delivered(now=clock())
    except Exception as exc:
        swallowed(log, "ops.lifecycle_prune", exc, "lifecycle delivery cause=prune_storage_failed",
                  level=logging.ERROR)


def _claim(repo, owner, clock):
    try:
        return repo.claim_one(owner, now=clock())
    except Exception as exc:
        swallowed(log, "ops.lifecycle_claim", exc, "lifecycle delivery cause=claim_storage_failed",
                  level=logging.ERROR)
        return None


def _acknowledge(repo, event, message_id, clock):
    try:
        committed = repo.acknowledge(event["event_id"], event["lease_token"],
                                     message_id, now=clock())
    except Exception as exc:
        swallowed(log, "ops.lifecycle_ack", exc,
                  "lifecycle delivery event=%s cause=ack_storage_failed", event["event_id"],
                  level=logging.ERROR)
        return None
    if not committed:
        log.warning("lifecycle delivery event=%s cause=stale_ack", event["event_id"])
        return None
    return "acknowledged"


def _reschedule(repo, event, error, clock):
    code, blocked = _failure(error)
    try:
        committed = repo.reschedule(event["event_id"], event["lease_token"], now=clock(),
                                    delay_s=_delay(event, error, blocked),
                                    error_code=code, blocked=blocked)
    except Exception as exc:
        swallowed(log, "ops.lifecycle_retry", exc,
                  "lifecycle delivery event=%s cause=retry_storage_failed", event["event_id"],
                  level=logging.ERROR)
        return None
    if not committed:
        log.warning("lifecycle delivery event=%s cause=stale_retry", event["event_id"])
        return None
    return "blocked" if blocked else "retried"


async def _deliver_one(bot, repo, event, clock):
    try:
        message_id = await asyncio.wait_for(send_lifecycle_notification(bot, event), timeout=30)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        swallowed(log, "ops.lifecycle_send", error, "lifecycle delivery event=%s send failed",
                  event["event_id"])
        return _reschedule(repo, event, error, clock)
    return _acknowledge(repo, event, message_id, clock)


async def deliver_lifecycle_tick(bot, *, repo=None, now=None) -> dict[str, int]:
    queue = notify_queue_repo() if repo is None else repo
    clock = now if now is not None else lambda: datetime.now(timezone.utc)
    owner = str(uuid4())
    counts = dict(attempted=0, acknowledged=0, retried=0, blocked=0)
    _prune(queue, clock)
    try:
        for _ in range(20):
            event = _claim(queue, owner, clock)
            if event is None:
                break
            counts["attempted"] += 1
            outcome = await _deliver_one(bot, queue, event, clock)
            if outcome is not None:
                counts[outcome] += 1
    finally:
        log.info("lifecycle delivery attempted=%d acknowledged=%d retried=%d blocked=%d",
                 counts["attempted"], counts["acknowledged"], counts["retried"], counts["blocked"])
    return counts
