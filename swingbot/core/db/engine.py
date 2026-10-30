"""Process-local SQLAlchemy engine for the staged PostgreSQL migration."""
from __future__ import annotations

import logging
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine
from sqlalchemy import exc as sa_exc

from swingbot import config

log = logging.getLogger(__name__)

_engine: Engine | None = None
_POOL_SIZE = 5
_MAX_OVERFLOW = 5
_CONNECT_TIMEOUT_SECONDS = 5

# v189 D3.3: how long a writer waits for a row lock before giving up. The bot's
# poll and scanner skip that plan for one cycle; admin and Discord commands wait
# longer because a person is waiting on the answer.
BOT_LOCK_TIMEOUT_MS = 1000
ADMIN_LOCK_TIMEOUT_MS = 5000
_LOCK_NOT_AVAILABLE = "55P03"     # Postgres SQLSTATE raised when lock_timeout expires


class DatabaseUnavailable(RuntimeError):
    """The database is missing, invalidly configured, or cannot be reached."""


class LockTimeout(Exception):
    """A row lock was not granted within the transaction's lock_timeout.

    Raised out of an owned ``transaction()`` (the whole transaction has already
    rolled back); ``__cause__`` is the driver error."""


def _is_lock_timeout(exc: BaseException) -> bool:
    """True when the driver error is Postgres' lock_not_available (55P03)."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == _LOCK_NOT_AVAILABLE


def _checked_timeout(lock_timeout_ms: int | None) -> int | None:
    """The timeout as a positive int, or None; refuses 0 (which means 'wait forever')."""
    if lock_timeout_ms is None:
        return None
    ms = int(lock_timeout_ms)
    if ms <= 0:
        raise ValueError(f"lock_timeout_ms must be positive, got {lock_timeout_ms!r}")
    return ms


def get_engine() -> Engine:
    """Return the singleton engine, failing clearly for an invalid URL.

    Connection is deliberately lazy: JSON remains the default store stage, so
    starting the bot before a migration is enabled must not open a database
    connection.  Once a DB-backed store opts in, its write path treats an
    unavailable database as fatal rather than silently losing trading state.
    """
    global _engine
    if _engine is not None:
        return _engine

    url = (config.DATABASE_URL or "").strip()
    if not url:
        raise DatabaseUnavailable(
            "DATABASE_URL is not set; expected postgresql+psycopg://user:pass@host:5432/dbname"
        )
    if not url.startswith("postgresql+psycopg://"):
        scheme = url.split("://", 1)[0]
        raise DatabaseUnavailable(
            "DATABASE_URL must start with postgresql+psycopg://; "
            f"got {scheme}://"
        )

    _engine = create_engine(
        url,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )
    log.info("Database engine created for %s", _engine.url.render_as_string(hide_password=True))
    return _engine


def reset_engine() -> None:
    """Dispose the current pool and clear the singleton (tests/controlled reset)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def transaction(conn=None, *, lock_timeout_ms: int | None = None):
    """Yield one transaction for several repository calls.

    An existing connection is passed through, allowing an already-atomic
    caller to compose without opening a second transaction; its owner chose
    the lock timeout and translates a timeout, so nothing is set here.

    An owned transaction with ``lock_timeout_ms`` runs ``SET LOCAL
    lock_timeout`` first (scoped to this transaction only, so a pooled
    connection never carries it on) and raises ``LockTimeout`` when a row lock
    is not granted in time.
    """
    if conn is not None:
        yield conn
        return
    ms = _checked_timeout(lock_timeout_ms)
    try:
        with get_engine().begin() as owned:
            if ms is not None:
                owned.execute(sa.text(f"SET LOCAL lock_timeout = '{ms}ms'"))
            yield owned
    except sa_exc.DBAPIError as exc:
        if _is_lock_timeout(exc):
            raise LockTimeout(f"row lock not granted within {ms}ms") from exc
        raise
