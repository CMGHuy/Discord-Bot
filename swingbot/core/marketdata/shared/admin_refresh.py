"""v201: the one contract the refresher, the request door and the SPA payloads share.

Cadences and staleness thresholds are read from ``swingbot.config`` at call
time, so a hot reload takes effect on the next cycle. Imports nothing but
config, datetime and the session clock.
"""
from __future__ import annotations

from datetime import datetime, timezone

from swingbot import config
from swingbot.core.market import session

#: Refresh-queue priorities: lower runs first.
PRIORITY_USER = 0
PRIORITY_FRESH_HINT = 1
PRIORITY_MISSING = 2

QUEUE_KIND_QUOTE = "quote"
QUEUE_KIND_SNAPSHOT = "snapshot"

HEARTBEAT_KEY = "refresher"
QUEUE_RETENTION_S = 3600

_CADENCE_ATTR = {
    session.SESSION_REGULAR: "ADMIN_REFRESH_REGULAR_S",
    session.SESSION_EXTENDED: "ADMIN_REFRESH_EXTENDED_S",
    session.SESSION_CLOSED: "ADMIN_REFRESH_CLOSED_S",
}
_STALE_ATTR = {
    ("price", session.SESSION_REGULAR): "ADMIN_STALE_PRICE_REGULAR_S",
    ("price", session.SESSION_EXTENDED): "ADMIN_STALE_PRICE_EXTENDED_S",
}


def refresher_on() -> bool:
    return config.ADMIN_REFRESHER == "on" and config.MARKETDATA_LAYER == "on"


def cadence_s(state: str) -> float:
    attr = _CADENCE_ATTR.get(state)
    if attr is None:
        raise ValueError(f"unknown session state {state!r}")
    return float(getattr(config, attr))


def stale_after_s(kind: str, state: str) -> float | None:
    """Absolute threshold; None when closed (labelled closed, never stale)."""
    if state == session.SESSION_CLOSED:
        return None
    attr = _STALE_ATTR.get((kind, state))
    if attr is None:
        raise ValueError(f"unknown staleness kind/state {kind!r}/{state!r}")
    return float(getattr(config, attr))


def heartbeat_stalled(beat_at: datetime | None, cadence: float,
                      now: datetime | None = None) -> bool:
    if beat_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - beat_at).total_seconds() > 3 * float(cadence)


def quote_mark_key(symbol: str) -> str:
    return f"quote:{str(symbol).upper().strip()}"
