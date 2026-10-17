"""Count every swallowed exception per call-site tag (v148 O5).

A leaf module: it imports nothing from ``swingbot``, so any module -- a
spawned fetch child included -- can import it without closing a cycle.

``swallowed()`` replaces the body of an ``except Exception`` handler that does
not re-raise. It logs through the *caller's* logger, at the caller's level,
with the caller's message and ``exc_info`` -- so converting a site changes no
log line -- tags the record with ``extra={"swallowed_tag": tag}``, and counts
the tag. Counts live in this process only: ``fetch._counted_call`` carries a
spawned child's ``snapshot()`` back to the parent, which ``merge()``s it, and
the bot flushes its snapshot into the heartbeat row every tick
(``runstate._write_heartbeat``). Tags are ``<area>.<function>`` string
literals, unique per site (``tests/infra/test_swallowed_ratchet.py``).
"""
from __future__ import annotations

import datetime as dt
import functools
import logging
import threading

_LAST_ERROR_MAX = 200

#: Process boot (UTC ISO): the "since" of every count this process holds.
STARTED_AT: str = dt.datetime.now(dt.timezone.utc).isoformat()

_lock = threading.Lock()
_counts: dict[str, dict] = {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _describe(exc: BaseException) -> str:
    """``Type: message``, capped -- no traceback, no locals."""
    return f"{type(exc).__name__}: {exc}"[:_LAST_ERROR_MAX]


def _emitter(log: logging.Logger, level: int):
    """The logger's own level method (``log.warning`` for WARNING, ...), so a
    test that patches ``log.warning`` still sees a converted site's call.
    ``partial(log.log, level)`` for a non-standard level: a partial adds no
    Python frame, so ``stacklevel=2`` still names the caller."""
    method = getattr(log, logging.getLevelName(level).lower(), None)
    return method if method is not None else functools.partial(log.log, level)


def _count(tag: str, error: str) -> None:
    now = _now()
    with _lock:
        entry = _counts.get(tag)
        if entry is None:
            _counts[tag] = {"count": 1, "first_at": now, "last_at": now, "last_error": error}
            return
        entry["count"] += 1
        entry["last_at"] = now
        entry["last_error"] = error


def swallowed(log: logging.Logger, tag: str, exc: BaseException, msg: str = "", *args,
              level: int = logging.WARNING, exc_info: bool = False) -> None:
    """Count `tag` and log `msg % args` exactly as the handler did before.

    ``log.exception(m, *a)`` becomes ``level=logging.ERROR, exc_info=True``.
    With no `msg` (a handler that logged nothing) it logs the tag and error.
    """
    error = _describe(exc)
    _count(tag, error)
    if not msg:
        msg, args = "swallowed %s: %s", (tag, error)
    _emitter(log, level)(msg, *args, exc_info=exc_info or None,
                         extra={"swallowed_tag": tag}, stacklevel=2)


def snapshot() -> dict[str, dict]:
    """A deep-enough copy: tag -> {count, first_at, last_at, last_error}."""
    with _lock:
        return {tag: dict(entry) for tag, entry in _counts.items()}


def _merge_one(tag: str, other: dict) -> None:
    mine = _counts.get(tag)
    if mine is None:
        _counts[tag] = dict(other)
        return
    mine["count"] += int(other.get("count") or 0)
    mine["first_at"] = min(mine["first_at"], other.get("first_at") or mine["first_at"])
    if (other.get("last_at") or "") > mine["last_at"]:
        mine["last_at"] = other["last_at"]
        mine["last_error"] = other.get("last_error", mine["last_error"])


def merge(counts: dict[str, dict] | None) -> None:
    """Add another process's snapshot (a spawned child's delta) to ours.
    ISO-8601 UTC strings compare correctly as text."""
    if not counts:
        return
    with _lock:
        for tag, other in counts.items():
            _merge_one(tag, other)


def reset() -> None:
    """Tests only."""
    with _lock:
        _counts.clear()
