"""v201: the one contract the refresher, the request door and the SPA payloads share.

Cadences and staleness thresholds are read from ``swingbot.config`` at call
time, so a hot reload takes effect on the next cycle. Imports nothing but
config, datetime and the session clock. v204 adds the snapshot staleness
kind, cadence and key shapes.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

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
    ("snapshot", session.SESSION_REGULAR): "ADMIN_STALE_SNAPSHOT_REGULAR_S",
    ("snapshot", session.SESSION_EXTENDED): "ADMIN_STALE_SNAPSHOT_EXTENDED_S",
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


SNAPSHOT_RISK = "risk"
SNAPSHOT_ANALYTICS = "analytics.snapshot"
#: scope.LEDGERS, restated so marketdata imports nothing from analytics (pinned by test).
_LEDGERS = ("main", "weak", "both")
_SNAPSHOT_CADENCE_ATTR = {
    session.SESSION_REGULAR: "ADMIN_SNAPSHOT_REGULAR_S",
    session.SESSION_EXTENDED: "ADMIN_SNAPSHOT_EXTENDED_S",
    session.SESSION_CLOSED: "ADMIN_SNAPSHOT_CLOSED_S",
}
_MONTH = r"\d{4}-(?:0[1-9]|1[0-2])"
_LEDGER = "|".join(_LEDGERS)
_SNAPSHOT_KEY = re.compile(
    rf"(?:risk|analytics\.snapshot|analytics\.(?:performance|equity_curve):(?:{_LEDGER})"
    rf"|calendar\.pnl:{_MONTH})")
_MARK_PREFIX = "snapshot:"


def snapshot_cadence_s(state: str) -> float:
    attr = _SNAPSHOT_CADENCE_ATTR.get(state)
    if attr is None:
        raise ValueError(f"unknown session state {state!r}")
    return float(getattr(config, attr))


def snapshot_mark_timeout_s() -> float:
    return float(config.ADMIN_SNAPSHOT_BUDGET_S) + 30.0


def _checked_ledger(ledger: str) -> str:
    if ledger not in _LEDGERS:
        raise ValueError(f"unknown ledger {ledger!r}")
    return ledger


def performance_key(ledger: str) -> str:
    return f"analytics.performance:{_checked_ledger(ledger)}"


def equity_curve_key(ledger: str) -> str:
    return f"analytics.equity_curve:{_checked_ledger(ledger)}"


def calendar_key(month: str) -> str:
    if not re.fullmatch(_MONTH, str(month)):
        raise ValueError(f"not a YYYY-MM month: {month!r}")
    return f"calendar.pnl:{month}"


def is_snapshot_key(key) -> bool:
    return isinstance(key, str) and _SNAPSHOT_KEY.fullmatch(key) is not None


def snapshot_mark_key(key: str) -> str:
    if not is_snapshot_key(key):
        raise ValueError(f"not a snapshot key: {key!r}")
    return _MARK_PREFIX + key


def snapshot_key_of(mark_key: str) -> str | None:
    if not isinstance(mark_key, str) or not mark_key.startswith(_MARK_PREFIX):
        return None
    key = mark_key[len(_MARK_PREFIX):]
    return key if is_snapshot_key(key) else None


def calendar_months(now: datetime | None = None) -> tuple[str, str]:
    d = session.now_et(now).date()
    return (f"{d:%Y-%m}", f"{d.replace(day=1) - timedelta(days=1):%Y-%m}")
