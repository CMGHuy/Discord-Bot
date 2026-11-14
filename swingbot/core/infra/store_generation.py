"""Process-wide change generations for the admin's store snapshot (v218, v205 L2-b).

A leaf module: it imports nothing from ``swingbot`` (or flask), so ``config``
and core stores can import it without a cycle.

Three counters, one per concern whose change must invalidate the admin's
cross-request snapshot and its ETags:

* ``trades``   -- bumped by the snapshot listener on every ``trades`` NOTIFY
  (the trades, plans and starred_plans triggers fire that channel);
* ``journal``  -- bumped on every ``journal`` NOTIFY (journal_entries);
* ``settings`` -- bumped by ``config.reload()`` whenever a value changed.

``connected`` says whether the snapshot listener is LISTENing right now. While
it is False no NOTIFY can bump a counter, so the snapshot is bypassed
(``store_snapshot.enabled()``). It starts False: nothing is served from the
snapshot until the listener has connected once.

The admin runs one gunicorn worker with 16 threads; a lock guards the counters.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

CONCERNS: tuple[str, ...] = ("trades", "journal", "settings")

_lock = threading.Lock()
_counts: dict[str, int] = dict.fromkeys(CONCERNS, 0)
_connected = False


def bump(concern: str) -> int:
    """Advance one concern; return its new value. ``KeyError`` for an unknown concern."""
    with _lock:
        if concern not in _counts:
            _unknown(concern)
        _counts[concern] += 1
        return _counts[concern]


def _unknown(concern: str) -> int:
    raise KeyError(f"unknown store generation concern {concern!r}; expected one of {CONCERNS}")


def bump_all() -> None:
    """Advance every concern: after a (re)connect, missed NOTIFYs are unknowable."""
    with _lock:
        for concern in CONCERNS:
            _counts[concern] += 1


def generation(concern: str) -> int:
    with _lock:
        if concern not in _counts:
            _unknown(concern)
        return _counts[concern]


def token() -> tuple[int, int, int]:
    """Every generation, in ``CONCERNS`` order."""
    with _lock:
        return tuple(_counts[concern] for concern in CONCERNS)


def set_connected(flag: bool) -> None:
    """Record the listener's state; log only when it changes (no per-request noise)."""
    global _connected
    flag = bool(flag)
    with _lock:
        changed, _connected = _connected != flag, flag
    if not changed:
        return
    if flag:
        log.info("store snapshot listener connected; the admin snapshot may serve reads")
    else:
        log.warning("store snapshot listener disconnected; the admin snapshot is bypassed")


def connected() -> bool:
    return _connected


def reset() -> None:
    """Test seam: every counter back to 0, ``connected`` False."""
    global _connected
    with _lock:
        for concern in CONCERNS:
            _counts[concern] = 0
        _connected = False
