"""v184: the trade monitor stamps its own liveness.

The scan loop's heartbeat (runstate._write_heartbeat) says nothing about the
60-second trade monitor: in August 2026 the monitor stalled for ~26 h while
that stamp stayed fresh, and four -1R stops filled at -3.3R to -6.0R. Each
monitor tick now ends by merging one key, ``monitor``, into the heartbeat row,
and scripts/ops/heartbeat_watch.sh alerts on it (monitor_stale,
stops_unchecked).

Only the monitor writes this key, and it always writes the whole object (the
merge is a shallow ``doc || fields``). ``started_at`` and ``priced_at`` live
in this process only and are never read back from the row: after a restart
``priced_at`` is null until the first fully priced tick, so a wedge followed
by a restart never reads as fresh.

The stamp adds no quote fetch and no quote-cache read: every field comes from
what the tick already did (live/replay parity).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session

from . import runstate

if TYPE_CHECKING:
    from swingbot.core.planning.plan_manager import PollDemand

log = logging.getLogger(__name__)

#: At most one write per this many seconds unless something material changes:
#: every bot_heartbeat write raises the admin's undebounced `bot` SSE event.
WRITE_INTERVAL_S = 120
#: `unquoted` names in the doc; `unquoted_count` carries the full number.
UNQUOTED_CAP = 20
#: The `check_errors` entry for a raised plan-manager tick.
PLAN_MANAGER_ERROR = "<plan manager>"


@dataclass
class TickRecord:
    """What one monitor tick did. Every field starts at "unknown": a tick that
    raises part-way leaves the rest unknown, never zero."""
    outcome: str = "raised"                     # "ok" only once the tick body returned
    trade_tickers: list[str] | None = None      # None = the trade read did not complete
    live_prices: dict[str, float] | None = None
    plan_demand: PollDemand | None = None       # None = the manager demanded nothing
    manager_raised: bool = False
    check_errors: list[str] = field(default_factory=list)
    fetch_failed: bool = False


def positions_of(rec: TickRecord) -> list[str] | None:
    """The stops the monitor is responsible for this tick, or None (unknown)."""
    if rec.trade_tickers is None or rec.manager_raised:
        return None
    plan = rec.plan_demand.demanded if rec.plan_demand is not None else ()
    return sorted(set(rec.trade_tickers) | set(plan))


def _unpriced_trade_tickers(rec: TickRecord) -> list[str]:
    """Trade tickers the close call skipped: its own `not live or live <= 0`."""
    prices = rec.live_prices or {}
    out = []
    for ticker in rec.trade_tickers or ():
        live = prices.get(ticker)
        if not live or live <= 0:
            out.append(ticker)
    return out


def unquoted_of(rec: TickRecord) -> list[str]:
    """Sorted, uncapped: trade tickers without a usable price plus the plan
    tickers poll() demanded and did not price."""
    plan = rec.plan_demand.unpriced if rec.plan_demand is not None else ()
    return sorted(set(_unpriced_trade_tickers(rec)) | set(plan))


def check_errors_of(rec: TickRecord) -> list[str]:
    """Tickers whose close checks raised, plus the plan-manager marker."""
    errors = list(rec.check_errors)
    if rec.manager_raised:
        errors.append(PLAN_MANAGER_ERROR)
    return errors


def _iso(moment: dt.datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _signature(doc: dict) -> tuple:
    """The fields whose change is written at once, throttle or not."""
    return (doc["outcome"], tuple(doc["unquoted"]), doc["fetch_failed"],
            tuple(doc["check_errors"]))


class MonitorLiveness:
    """Process-local source of truth for `started_at` and `priced_at`."""

    def __init__(self, started_at: dt.datetime | None = None) -> None:
        self.started_at = started_at or dt.datetime.now(dt.timezone.utc)
        self.priced_at: dt.datetime | None = None
        self._signature: tuple | None = None
        self._written_at: dt.datetime | None = None

    def build(self, rec: TickRecord, now: dt.datetime) -> dict:
        """The full `monitor` doc for this tick; advances `priced_at` to `now`
        on a clean tick (ok, positions known, nothing unquoted, no errors)."""
        positions = positions_of(rec)
        unquoted = unquoted_of(rec)
        errors = check_errors_of(rec)
        if rec.outcome == "ok" and positions is not None and not unquoted and not errors:
            self.priced_at = max(self.priced_at, now) if self.priced_at is not None else now
        return {
            "started_at": _iso(self.started_at),
            "tick_at": _iso(now),
            "outcome": rec.outcome,
            "positions": positions,
            "unquoted": unquoted[:UNQUOTED_CAP],
            "unquoted_count": len(unquoted),
            "fetch_failed": bool(rec.fetch_failed),
            "check_errors": errors,
            "priced_at": _iso(self.priced_at),
            "market_open": session.is_nyse_regular_session(now),
        }

    def due(self, doc: dict, now: dt.datetime) -> bool:
        if self._written_at is None or _signature(doc) != self._signature:
            return True
        return (now - self._written_at).total_seconds() >= WRITE_INTERVAL_S

    def written(self, doc: dict, now: dt.datetime) -> None:
        self._signature = _signature(doc)
        self._written_at = now


#: Created at import, which is process start (loops.py imports this module).
_STATE = MonitorLiveness()


def _write(doc: dict) -> None:
    runstate._update_heartbeat({"monitor": doc})


async def stamp_tick(rec: TickRecord, *, now: dt.datetime | None = None) -> bool:
    """Build this tick's doc and write it when due. Never raises; True when
    a write was handed to the database."""
    try:
        moment = now or dt.datetime.now(dt.timezone.utc)
        doc = _STATE.build(rec, moment)
        if not _STATE.due(doc, moment):
            return False
        await asyncio.to_thread(_write, doc)
        _STATE.written(doc, moment)
        return True
    except Exception as exc:  # noqa: BLE001 -- the stamp must never break the monitor
        swallowed(log, "ops.monitor_stamp", exc,
                  "trade_monitor: liveness stamp failed: %s", exc,
                  level=logging.WARNING, exc_info=True)
        return False
