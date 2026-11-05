"""v201: the refresher's cycle and its lock loop.

One cycle = build a ``CycleContext`` (session, symbol set, queued keys, scan
flag), run ``STEPS`` in order (each failure recorded in ``report.error``, never
stopping the others), prune the queue, write the heartbeat. Nothing here ever
raises out of ``run_cycle``: a database error -- missing v201 tables included,
since ``deploy.sh`` starts containers before ``alembic upgrade`` -- becomes
``report.error`` and the heartbeat's ``last_error``, so a dead refresher never
looks like a quiet market.

A full cycle (the whole symbol set) runs once per session cadence; a cycle in
between carries ``SymbolSet((), ())`` and only the queued keys, so a user's
Refresh is served within ``QUEUE_POLL_S`` without refetching everything.
``STEPS`` runs the quote and FX steps (``quotes``), then the snapshot step
(``snapshot_job``, v204), so snapshots see this cycle's FX codes; a cycle that
changed something raises one ``market`` NOTIFY at its end.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import engine, notify
from swingbot.core.db.repositories.market_refresh import (refresh_queue_repo,
                                                          refresher_heartbeat_repo)
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.refresher import lock, quotes, snapshot_job
from swingbot.refresher.symbols import SymbolSet, symbol_set

log = logging.getLogger(__name__)

LOCK_RETRY_S = 30.0
QUEUE_POLL_S = 5.0
QUEUE_TAKE_LIMIT = 500


@dataclass
class CycleReport:
    session: str
    cadence_s: float
    quotes_ok: tuple[str, ...] = ()
    quotes_missed: tuple[str, ...] = ()
    fallback_used: int = 0
    snapshots_written: tuple[str, ...] = ()
    error: str | None = None
    changed: bool = False


@dataclass
class CycleContext:
    now: datetime
    session: str
    symbols: SymbolSet
    queued_quotes: list[str]
    queued_snapshots: list[str]
    scan_running: bool
    report: CycleReport = field(repr=False)
    marks_announced: bool = False


STEPS: list[Callable[[CycleContext], None]] = [quotes.quote_step, quotes.fx_step,
                                               snapshot_job.snapshot_step]

_last_full: datetime | None = None


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _guard(tag: str, fn: Callable[[], object]) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - housekeeping never kills a cycle
        swallowed(log, "ops.refresher.guard", exc, "refresher step %s failed: %s", tag, exc,
                  level=logging.WARNING)


def _scan_running() -> bool:
    try:
        from swingbot.core.scanning import runstate
        return bool(runstate.is_scan_running())
    except Exception as exc:  # noqa: BLE001 - unknown reads as "not running"
        swallowed(log, "ops.refresher.scan_running", exc, level=logging.DEBUG)
        return False


def _context(now: datetime, state: str, report: CycleReport, *, full: bool) -> CycleContext:
    # Symbols first: a failure here must leave the queue untaken, never lost.
    symbols = symbol_set() if full else SymbolSet((), ())
    taken = refresh_queue_repo().take(QUEUE_TAKE_LIMIT)
    quotes = [r["key"] for r in taken if r.get("kind") == admin_refresh.QUEUE_KIND_QUOTE]
    snaps = [r["key"] for r in taken if r.get("kind") == admin_refresh.QUEUE_KIND_SNAPSHOT]
    return CycleContext(now=now, session=state, symbols=symbols, queued_quotes=quotes,
                        queued_snapshots=snaps, scan_running=_scan_running(), report=report)


def _run_steps(ctx: CycleContext) -> None:
    for step in list(STEPS):
        try:
            step(ctx)
        except Exception as exc:  # noqa: BLE001 - one step never stops the others
            if ctx.report.error is None:
                ctx.report.error = _describe(exc)
            swallowed(log, "ops.refresher.step", exc, level=logging.WARNING)


def run_cycle(now: datetime | None = None) -> CycleReport:
    global _last_full
    now = now or datetime.now(timezone.utc)
    state = session.session_state(now)
    report = CycleReport(session=state, cadence_s=admin_refresh.cadence_s(state))
    started = time.monotonic()
    try:
        if admin_refresh.refresher_on():
            full = _last_full is None or (now - _last_full).total_seconds() >= report.cadence_s - 1.0
            ctx = _context(now, state, report, full=full)
            if full:
                _last_full = now
            _run_steps(ctx)
        else:
            # Kill switch (ADMIN_REFRESHER / MARKETDATA_LAYER off): no fetch and
            # no queue drain, but the heartbeat below still beats; the next
            # cycle after a .env hot-reload resumes with a full pass.
            _last_full = None
    except Exception as exc:  # noqa: BLE001 - a cycle never kills the process
        report.error = _describe(exc)
        swallowed(log, "ops.refresher.cycle", exc, level=logging.WARNING)
    _guard("prune", lambda: refresh_queue_repo().prune(
        now - timedelta(seconds=admin_refresh.QUEUE_RETENTION_S)))
    _guard("heartbeat", lambda: refresher_heartbeat_repo().beat(
        cadence_s=report.cadence_s, session=state, last_error=report.error, now=now,
        cycle_ms=int((time.monotonic() - started) * 1000)))
    if report.changed:
        _guard("notify", lambda: notify.publish("market"))
    return report


def _wait(stop: threading.Event, seconds: float) -> None:
    stop.wait(seconds)


def _reload_if_env_changed() -> None:
    """No SIGHUP reaches this container from ``scripts/ops/env_set.py``, so
    every inner tick compares the .env signature ``config.reload`` stored."""
    try:
        if config._env_signature() != config._ENV_MTIME:
            config.reload()
    except Exception as exc:  # noqa: BLE001 - a bad .env keeps the old values
        swallowed(log, "ops.refresher.env_reload", exc, level=logging.WARNING)


def _queue_pending() -> bool:
    try:
        with engine.get_engine().connect() as conn:
            return bool(conn.execute(sa.text(
                "SELECT EXISTS (SELECT 1 FROM market_refresh_queue WHERE taken_at IS NULL)"
            )).scalar())
    except Exception as exc:  # noqa: BLE001 - a missing table reads as "nothing queued"
        swallowed(log, "ops.refresher.queue_pending", exc, level=logging.DEBUG)
        return False


def _cadence_now() -> float:
    try:
        return admin_refresh.cadence_s(session.session_state())
    except Exception as exc:  # noqa: BLE001 - fall back to the poll interval
        swallowed(log, "ops.refresher.cadence", exc, level=logging.WARNING)
        return QUEUE_POLL_S


def _sleep_until_due(stop: threading.Event, started: float) -> None:
    """Tick every ``QUEUE_POLL_S``: reload a changed .env, then return once the
    queue has work or the (re-read) cadence has elapsed since ``started``."""
    while not stop.is_set():
        _wait(stop, QUEUE_POLL_S)
        _reload_if_env_changed()
        if _queue_pending() or time.monotonic() - started >= _cadence_now():
            return


def _serve(stop: threading.Event) -> None:
    while not stop.is_set():
        started = time.monotonic()
        run_cycle()
        _sleep_until_due(stop, started)


def run_forever(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with lock.single_instance() as held:
                if not held:
                    log.info("another refresher holds lock %s; retrying", lock.ADVISORY_LOCK_KEY)
                    _wait(stop, LOCK_RETRY_S)
                    continue
                _serve(stop)
        except Exception as exc:  # noqa: BLE001 - DB down at start: back off, retry
            swallowed(log, "ops.refresher.lock", exc, level=logging.WARNING)
            _wait(stop, LOCK_RETRY_S)
