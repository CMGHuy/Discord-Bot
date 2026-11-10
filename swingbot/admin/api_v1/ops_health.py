"""GET /api/v1/system/health -- v148: provider degradation and swallowed errors.

Three panels on System read this one payload:

* ``providers`` -- the last 20 scan rows of ``scan_telemetry.jsonl``, newest
  first, cut down to ``at``, ``tickers`` and the four v148 provider fields.
  A row written before v148 has none of the four; it is passed through as
  ``null`` (rendered "—"), never back-filled -- no read-time upcasting
  (docs/claude/schema-evolution.md).
* ``swallowed`` -- per-tag counts of errors caught and carried on from. The
  bot's come from the ``swallowed`` key it rewrites on the heartbeat row every
  tick; the admin's are this process's own memory, which is the whole admin
  because it runs one worker (v148 O1). Both start at zero when their process
  starts; ``bot_counts_since`` says when the bot's did.

* ``notifications`` -- the lifecycle notification backlog (pending count, oldest
  pending age, blocked count) from the durable queue. ``null`` means the queue
  could not be read: unknown, never a healthy zero. An empty queue is a real
  ``{0, null, 0}``.

``thresholds`` echoes the two hot-reloadable alert levels, so the provider
panel marks a breach with the same numbers ``ops_watch`` alerts on.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import jsonify

from swingbot import config
from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed

from . import api_v1
from .auth import require_auth

log = logging.getLogger(__name__)

_WINDOW = 20
_PROVIDER_KEYS = ("at", "tickers", "provider_fallback_rate", "old_print_rate",
                  "stale_symbols", "empty_symbols", "empty_rate")


def _provider_rows() -> list[dict]:
    """Newest first; a key the row never had reads as None."""
    from swingbot.core.scanning import telemetry
    rows = telemetry.recent_scan_telemetry(_WINDOW)
    return [{key: row.get(key) for key in _PROVIDER_KEYS} for row in reversed(rows)]


def _swallowed_rows(process: str, counts) -> list[dict]:
    if not isinstance(counts, dict):
        return []
    return [
        {"process": process, "tag": str(tag), "count": int(entry.get("count") or 0),
         "first_at": entry.get("first_at"), "last_at": entry.get("last_at"),
         "last_error": entry.get("last_error")}
        for tag, entry in counts.items() if isinstance(entry, dict)
    ]


def _bot_block() -> dict:
    """The heartbeat's ``swallowed`` block, or {} when absent or malformed."""
    from swingbot.commands.scanning import runstate
    block = runstate._read_heartbeat().get("swallowed")
    return block if isinstance(block, dict) else {}


def _notification_health() -> dict | None:
    try:
        return notify_queue_repo().health(now=datetime.now(timezone.utc))
    except Exception as exc:
        swallowed(log, "ops.notification_health", exc, "notification_health_unavailable",
                  level=logging.ERROR)
        return None


@api_v1.route("/system/health", methods=["GET"])
@require_auth
def get_system_health():
    from . import market_updates
    bot = _bot_block()
    rows = (_swallowed_rows("bot", bot.get("counts"))
            + _swallowed_rows("admin", swallowed_mod.snapshot()))
    rows.sort(key=lambda r: (-r["count"], r["process"], r["tag"]))
    since = bot.get("since")
    return jsonify({
        "providers": _provider_rows(),
        "thresholds": {"fallback_pct": config.PROVIDER_FALLBACK_ALERT_PCT,
                       "empty_pct": config.EMPTY_SYMBOLS_ALERT_PCT},
        "swallowed": rows,
        "bot_counts_since": since if isinstance(since, str) else None,
        "notifications": _notification_health(),
        "refresher": market_updates.refresher_health(),
    })
