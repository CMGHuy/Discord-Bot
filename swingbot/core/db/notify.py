"""LISTEN/NOTIFY DDL used to replace the admin UI's mtime polling watcher."""
from __future__ import annotations

import re

import sqlalchemy as sa

# These names are the existing SPA event contract.  Keep core/db independent
# from admin/ by copying the contract rather than importing the watcher.
CHANNELS: tuple[str, ...] = (
    "trades", "account", "analytics", "scan",
    "journal", "bot", "risk", "watchlist", "jobs",
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
