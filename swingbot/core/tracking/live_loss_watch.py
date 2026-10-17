"""v164 D3: the live loss watch's population loader and its latch.

Shared by retrospective Part 11 (the Sunday digest, which clears latches) and
loops.daily_recap (the instant ops-channel flag, which marks them), so neither
of those modules imports the other.

Population: closed trades (win / loss / manual close) of BOTH ledgers, split
exactly as snapshots.refresh_snapshot splits them, so the digest, the flag and
the admin Edge tab judge the same trades. calibration.live_loss_watch applies
the regular-origin and start-date rules on top.

Latch: one scheduled_jobs row per registry row, job
``live_loss_watch:<source>/<strategy>/<horizon or "pooled">``; ``fired_on``
holds the Berlin date the row was flagged, or the literal ``"cleared"``
(sa.Text, no migration). Report-only: nothing here writes the registry, a
badge or a plan.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking.ledger import split_by_ledger

log = logging.getLogger(__name__)

LATCH_PREFIX = "live_loss_watch:"
LATCH_CLEARED = "cleared"
_CLOSED_STATUSES = ("win", "loss", "closed")


def latch_job(row: dict) -> str:
    """The scheduled_jobs key of one registry row's latch."""
    horizon = row.get("horizon") or "pooled"
    return f"{LATCH_PREFIX}{row['source']}/{row['strategy']}/{horizon}"


def is_latched(row: dict) -> bool:
    """True while a flag for this row is open (posted and not yet cleared)."""
    return scheduled_repo().fired_on(latch_job(row)) not in (None, LATCH_CLEARED)


def mark_latched(row: dict, today: dt.date) -> None:
    """Open the latch. Call only after the flag's send returned a message."""
    scheduled_repo().mark(latch_job(row), today.isoformat())


def _recovered(row: dict) -> bool:
    bound = row.get("bound_upper")
    return bound is not None and bound >= 0


def clear_latches(rows: list[dict]) -> list[str]:
    """Re-arm every latched row whose upper bound is back at or above zero.

    Called only by the Sunday digest built for the real Berlin today. A row
    with no bound stays latched: no bound is not evidence of recovery."""
    cleared = []
    for row in rows:
        if _recovered(row) and is_latched(row):
            job = latch_job(row)
            scheduled_repo().mark(job, LATCH_CLEARED)
            cleared.append(job)
    if cleared:
        log.info("live loss watch: cleared latches %s", ", ".join(cleared))
    return cleared


def _all_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status="all", limit=None)


def _registry_entries() -> list[dict]:
    from swingbot.core.backtesting import registry
    return registry.load_registry()


def load_watch(*, n_resamples: int = calibration.EXPR_WATCH_RESAMPLES) -> dict:
    """The live loss watch over both ledgers: ``{"rows": [...], "counts": {...}}``."""
    closed = [trade for trade in _all_trades() if trade.get("status") in _CLOSED_STATUSES]
    main, weak = split_by_ledger(closed)
    return calibration.live_loss_watch([*main, *weak], _registry_entries(), n_resamples=n_resamples)
