"""LISTEN/NOTIFY DDL used to replace the admin UI's mtime polling watcher."""
from __future__ import annotations

import logging
import re
import threading  # noqa: F401 -- type annotation only
from typing import Callable, Sequence

import sqlalchemy as sa

from swingbot import config

log = logging.getLogger(__name__)

# These names are the existing SPA event contract.  Keep core/db independent
# from admin/ by copying the contract rather than importing from admin/.
CHANNELS: tuple[str, ...] = (
    "trades", "account", "analytics", "scan",
    "journal", "bot", "risk", "watchlist", "jobs", "settings",
)

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

NOTIFY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION swingbot_notify() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify(TG_ARGV[0], '');
  RETURN NULL;
END;
$$ LANGUAGE plpgsql
"""


def _check_identifier(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(
            f"{name!r} is not a plain lowercase SQL identifier; it is interpolated into DDL"
        )
    return name


def trigger_name(table: str) -> str:
    """The deterministic trigger name for a table."""
    return f"{_check_identifier(table)}_notify_trg"


def trigger_ddl(table: str, channel: str) -> str:
    """Return statement-level notification-trigger DDL for a known concern."""
    _check_identifier(table)
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a known channel")
    return (
        f"CREATE TRIGGER {trigger_name(table)} "
        f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION swingbot_notify('{channel}')"
    )


def drop_trigger_ddl(table: str) -> str:
    """Return safe trigger-removal DDL for a validated table identifier."""
    return f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {_check_identifier(table)}"


def emit(conn: sa.Connection, channel: str, payload: str = "") -> None:
    """Queue an application-level notification; PostgreSQL delivers it on commit."""
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a known channel")
    conn.execute(sa.text("SELECT pg_notify(:channel, :payload)"),
                 {"channel": channel, "payload": payload})


def publish(channel: str) -> None:
    """One NOTIFY outside any store write, for a concern whose source stays a
    file (events.FILE_PUBLISHERS). Never raises: a missed refresh costs one
    stale screen until the next event, a raised one would fail the write."""
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a known channel")
    try:
        from swingbot.core.db.engine import get_engine
        with get_engine().begin() as conn:
            emit(conn, channel)
    except Exception:  # noqa: BLE001
        log.debug("could not publish %s", channel, exc_info=True)


def listen(channels: "Sequence[str]", on_event: "Callable[[str | None], None]",
           stop: "threading.Event", *, poll: float = 0.5,
           dsn: str | None = None,
           on_listening: "Callable[[], None] | None" = None) -> None:
    """Block, calling `on_event(channel)` for every notification received.

    A poll window that passes with no notification calls `on_event(None)` --
    a tick, so a debouncing consumer can flush a burst that ended in silence.

    Uses a raw psycopg connection rather than the SQLAlchemy pool: LISTEN is
    session state, and a pooled connection that gets recycled silently stops
    listening. Returns when `stop` is set.

    `on_listening()` is called once per connection, as soon as LISTEN is
    active -- the moment from which no notification can be missed.
    """
    import psycopg
    from psycopg import sql

    for channel in channels:
        if channel not in CHANNELS:
            raise ValueError(f"{channel!r} is not a known channel")

    url = dsn or config.DATABASE_URL
    # psycopg wants a libpq DSN, not SQLAlchemy's driver-qualified URL.
    conninfo = url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(conninfo, autocommit=True) as conn:
        for channel in channels:
            conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
        log.info("Listening on %s", ", ".join(channels))
        if on_listening is not None:
            on_listening()
        while not stop.is_set():
            # Yields notifications as they arrive and returns when `poll`
            # elapses, so `stop` is checked at least that often.
            got_any = False
            for note in conn.notifies(timeout=poll):
                got_any = True
                _deliver(on_event, note.channel)
                if stop.is_set():
                    break
            if not got_any and not stop.is_set():
                _deliver(on_event, None)   # a tick with nothing to deliver


def _deliver(on_event: "Callable[[str | None], None]", channel: str | None) -> None:
    try:
        on_event(channel)
    except Exception:  # noqa: BLE001
        log.exception("notify handler raised for channel %s", channel)
