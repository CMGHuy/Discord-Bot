"""v171 D9: in-process call tally, hourly rows flushed to Postgres, worker merge.

Rows are keyed by (hour_iso, provider, kind, asker, outcome). Flushing every
60 s only increments the current hour's rows. A spawned worker never reaches
60 s, so it hands its rows back via ``snapshot_and_clear`` for the parent to
``merge``. Counting never blocks a fetch: a failed flush keeps its rows.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.db.repositories.market_shared import market_shared_repo
from swingbot.core.db.side_engine import side_connection
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared.kinds import OUTCOMES, Asker, DataKind

log = logging.getLogger(__name__)

_FLUSH_INTERVAL_S = 60.0
_monotonic = time.monotonic

_tally: collections.Counter = collections.Counter()
_lock = threading.Lock()
_last_flush = _monotonic()
_warned: dict[tuple[str, str], float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def count(provider: str, kind: DataKind, asker: Asker, outcome: str, n: int = 1) -> None:
    if config.MARKETDATA_LAYER == "off":
        return
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}")
    hour = _now().replace(minute=0, second=0, microsecond=0).isoformat()
    with _lock:
        _tally[(hour, provider, kind.value, asker.value, outcome)] += n


def snapshot_and_clear() -> list[tuple]:
    with _lock:
        rows = [(*key, n) for key, n in _tally.items()]
        _tally.clear()
    return rows


def merge(rows) -> None:
    with _lock:
        for row in rows:
            _tally[tuple(row[:5])] += row[5]


def flush(*, force: bool = False) -> int:
    global _last_flush
    if not force and _monotonic() - _last_flush < _FLUSH_INTERVAL_S:
        return 0
    _last_flush = _monotonic()
    rows = snapshot_and_clear()
    if not rows:
        return 0
    try:
        db_rows = [(datetime.fromisoformat(r[0]), *r[1:]) for r in rows]
        with side_connection() as conn:
            market_shared_repo().add_counts(db_rows, conn=conn)
    except Exception as exc:  # noqa: BLE001 - fail open, keep the rows
        merge(rows)
        swallowed(log, "marketdata.counters.flush", exc, level=logging.DEBUG)
        warn_fail_open("count flush", exc)
        return 0
    return len(rows)


def warn_fail_open(operation: str, exc: BaseException) -> None:
    key = (operation, type(exc).__name__)
    now = _monotonic()
    with _lock:
        last = _warned.get(key)
        if last is not None and now - last < _FLUSH_INTERVAL_S:
            return
        _warned[key] = now
    log.warning("market-data layer: %s failed open (%s: %s)", operation, type(exc).__name__, exc)


def reset() -> None:
    global _last_flush
    with _lock:
        _tally.clear()
        _warned.clear()
    _last_flush = _monotonic()
