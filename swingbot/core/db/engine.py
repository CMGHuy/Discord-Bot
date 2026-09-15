"""Process-local SQLAlchemy engine for the staged PostgreSQL migration."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine

from swingbot import config

log = logging.getLogger(__name__)

_engine: Engine | None = None
_POOL_SIZE = 5
_MAX_OVERFLOW = 5
_CONNECT_TIMEOUT_SECONDS = 5


class DatabaseUnavailable(RuntimeError):
    """The database is missing, invalidly configured, or cannot be reached."""


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
def transaction(conn=None):
    """Yield one transaction for several repository calls.

    An existing connection is passed through, allowing an already-atomic
    caller to compose without opening a second transaction.
    """
    if conn is not None:
        yield conn
        return
    with get_engine().begin() as owned:
        yield owned
