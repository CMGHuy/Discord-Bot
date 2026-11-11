"""The admin's per-process raw-record snapshot (v218, v205 L2-a/L2-b).

``read_memo`` (L1-c) loads each store once per request. This module keeps the
same loaders' values *between* requests, for ``SNAPSHOT_KEYS`` only, and hands
``read_memo`` the stored value; ``read_memo`` still gives every caller shallow
copies. Raw records only: anything derived from the clock (days held, open
P&L, today) is computed per request by the callers, as before.

Validity: the token ``(store_generation.token(), request_versions())``. The
generations move on every ``trades``/``journal`` NOTIFY, on a listener
(re)connect and on a settings reload; the versions are the plans, trades and
journal ``(count, max(updated_at))``. Neither alone is trusted (V218-1: a
transaction can commit under an older stamp). The token is read before the
lock and before any load, so a value is never filed under a newer token than
the data it was loaded from.

Served only when the key is a snapshot key, a read scope is open, the switch
``ADMIN_STORE_SNAPSHOT`` is ``on``, the snapshot listener is connected and the
version query succeeded; otherwise ``read`` is ``loader()``, Layer 1 exactly.

Installed by the admin app only (``install()`` -> ``read_memo.set_backing``);
the bot and the refresher never import it. One gunicorn worker, 16 threads:
one lock, and one rebuild at a time.
"""
from __future__ import annotations

import contextvars
import logging
import threading
from typing import Callable, TypeVar

from swingbot import config
from swingbot.core.infra import read_memo, store_generation
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

T = TypeVar("T")

SNAPSHOT_KEYS: frozenset[str] = frozenset(
    {read_memo.TRADE_ROWS, read_memo.TRADES, read_memo.PLANS, read_memo.NOTED_IDS})

_TAG = "ops.admin.snapshot"
_OUTSIDE = object()                      # no request armed: versions are read per call
_RANK = {"hit": 0, "miss": 1, "off": 2}  # request_state precedence

_lock = threading.Lock()
_token: tuple | None = None
_values: dict[str, object] = {}

_VERSIONS: contextvars.ContextVar[object] = contextvars.ContextVar(
    "v218_snapshot_versions", default=_OUTSIDE)
_STATE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "v218_snapshot_state", default=None)


def enabled() -> bool:
    """The switch is on and the snapshot listener is LISTENing."""
    return getattr(config, "ADMIN_STORE_SNAPSHOT", "on") == "on" and store_generation.connected()


def _query_versions() -> tuple:
    from swingbot.core.db.repositories.journal import journal_repo
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.db.repositories.trades import trades_repo
    return (plans_repo().version(), trades_repo().version(), journal_repo().version())


def _note(state: str) -> None:
    current = _STATE.get()
    if current is None or _RANK[state] > _RANK[current]:
        _STATE.set(state)


def begin_request() -> None:
    """Arm this request's version cache and state (request_timing._begin)."""
    _VERSIONS.set(None)
    _STATE.set(None)


def end_request() -> None:
    """Disarm them (request_timing._teardown): the thread outlives the request."""
    _VERSIONS.set(_OUTSIDE)
    _STATE.set(None)


def request_versions() -> tuple:
    """The plans, trades and journal versions: once per armed request, else per call."""
    cached = _VERSIONS.get()
    if cached is not None and cached is not _OUTSIDE:
        return cached
    try:
        versions = _query_versions()
    except Exception:
        _note("off")
        raise
    if cached is None:
        _VERSIONS.set(versions)
        _note("hit")
    return versions


def request_state() -> str:
    """off | miss | hit for the current request (Server-Timing ``snap;desc``)."""
    return _STATE.get() or "off"


def read(key: str, loader: Callable[[], T]) -> T:
    """The stored value for ``key`` when the snapshot can vouch for it, else ``loader()``."""
    if key not in SNAPSHOT_KEYS or not read_memo.active():
        return loader()
    if not enabled():
        _note("off")
        return loader()
    try:
        token = (store_generation.token(), request_versions())
    except Exception as exc:
        swallowed(log, "ops.admin.snapshot", exc, "admin snapshot bypassed: version query failed")
        _note("off")
        return loader()
    return _read_valid(key, loader, token)


def _read_valid(key: str, loader: Callable[[], T], token: tuple) -> T:
    global _token
    with _lock:
        if _token != token:
            _values.clear()
            _token = token
        if key in _values:
            _note("hit")
            return _values[key]
        value = loader()                 # a raising loader stores nothing and re-raises
        _values[key] = value
        _note("miss")
        return value


def stored(key: str) -> object | None:
    """Test seam: the stored value for ``key``, or None (never loads)."""
    with _lock:
        return _values.get(key)


def install() -> None:
    """Make ``read_memo`` read through the snapshot. Called once by the admin app."""
    read_memo.set_backing(read)


def reset() -> None:
    """Test seam: drop every stored value and this context's request state."""
    global _token
    with _lock:
        _values.clear()
        _token = None
    end_request()
