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
# from admin/ by copying the contract rather than importing the watcher.
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


def listen(channels: "Sequence[str]", on_event: "Callable[[str], None]",
           stop: "threading.Event", *, poll: float = 0.5,
           dsn: str | None = None) -> None:
    """Block, calling `on_event(channel)` for every notification received.

    Uses a raw psycopg connection rather than the SQLAlchemy pool: LISTEN is
    session state, and a pooled connection that gets recycled silently stops
    listening. Returns when `stop` is set.
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
        while not stop.is_set():
            # Yields notifications as they arrive and returns when `poll`
            # elapses, so `stop` is checked at least that often.
            for note in conn.notifies(timeout=poll):
                try:
                    on_event(note.channel)
                except Exception:  # noqa: BLE001
                    log.exception("notify handler raised for channel %s", note.channel)
                if stop.is_set():
                    break
