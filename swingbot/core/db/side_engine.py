"""The shared market-data layer's own tiny, fail-fast connection pool (v171 D1).

The layer never borrows the main pool: a cache read, lease or budget take must
cost at most ``MARKETDATA_PG_TIMEOUT_MS`` and must fail open, so it runs on this
separate engine with ``statement_timeout``/``lock_timeout`` set per connection,
autocommit (one statement per call, no transaction held), no pre-ping and a pool
timeout equal to the statement timeout (a busy pool fails open, never queues).

Connection budget: ``pool_size=1, max_overflow=1`` in the bot and admin processes,
``pool_size=1, max_overflow=0`` in spawned workers -- bot 2 + 2 live workers +
admin 2 = at most 7 side connections beside the main pools. Opened lazily.

After a refused connect the engine backs off for ``_DOWN_BACKOFF_S`` and raises
``DatabaseUnavailable`` at once, so a down database costs one connect timeout,
not one per call. Nothing outside ``swingbot/core/db`` imports this module's
SQLAlchemy objects: callers only enter ``side_connection()`` and pass the
``conn`` back to the repository.
"""
from __future__ import annotations

import multiprocessing
import threading
import time
from contextlib import contextmanager
from typing import Iterator

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from swingbot import config
from swingbot.core.db.engine import DatabaseUnavailable

_CONNECT_TIMEOUT_S = 2
_DOWN_BACKOFF_S = 30.0

_engine: Engine | None = None
_engine_sig: tuple | None = None
_down_until = 0.0
_lock = threading.Lock()


def pool_limits() -> tuple[int, int]:
    """``(pool_size, max_overflow)``: one spare connection only outside spawned workers."""
    if multiprocessing.parent_process() is not None:
        return (1, 0)
    return (1, 1)


def _url() -> str:
    url = (config.DATABASE_URL or "").strip()
    if not url:
        raise DatabaseUnavailable("DATABASE_URL is not set")
    if not url.startswith("postgresql+psycopg://"):
        raise DatabaseUnavailable("DATABASE_URL must start with postgresql+psycopg://")
    return url


def _build(url: str, ms: int, size: int, overflow: int) -> Engine:
    return create_engine(
        url, pool_size=size, max_overflow=overflow,
        pool_timeout=max(ms / 1000.0, 0.05),   # a busy pool fails open, never queues
        pool_pre_ping=False,                   # one statement per cache hit, no ping
        pool_recycle=300, isolation_level="AUTOCOMMIT", future=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_S,
                      "options": f"-c statement_timeout={ms} -c lock_timeout={ms}"})


def _get() -> Engine:
    """The engine for the current (url, timeout, pool limits); rebuilt when any changed."""
    global _engine, _engine_sig
    url = _url()
    ms = int(config.MARKETDATA_PG_TIMEOUT_MS)
    limits = pool_limits()
    sig = (url, ms, limits)
    with _lock:
        if _engine is None or _engine_sig != sig:
            if _engine is not None:
                _engine.dispose()
            _engine = _build(url, ms, *limits)
            _engine_sig = sig
        return _engine


@contextmanager
def side_connection() -> Iterator[sa.Connection]:
    """An autocommit connection with the layer's statement timeout; fails fast when down.

    Only the connect is guarded: a statement error propagates to the caller,
    which fails open.
    """
    global _down_until
    if time.monotonic() < _down_until:
        raise DatabaseUnavailable("side engine backing off")
    engine = _get()
    try:
        conn = engine.connect()
    except (sa.exc.OperationalError, sa.exc.InterfaceError):
        _down_until = time.monotonic() + _DOWN_BACKOFF_S
        raise
    with conn:
        yield conn


def reset() -> None:
    """Dispose the engine and forget the back-off (tests, config reload)."""
    global _engine, _engine_sig, _down_until
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_sig = None
        _down_until = 0.0
