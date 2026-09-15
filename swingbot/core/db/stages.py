"""Per-store PostgreSQL migration stages read from ``config.DB_STORES``.

Stage selection stays dynamic so changing the setting through the existing
hot-reload path takes effect without a process restart.
"""
from __future__ import annotations

import logging

from swingbot import config

log = logging.getLogger(__name__)

JSON = "json"
DUAL = "dual"
DB = "db"
STAGES = (JSON, DUAL, DB)


def parse(raw: str) -> dict[str, str]:
    """Parse ``name:stage`` entries, logging and ignoring malformed ones."""
    out: dict[str, str] = {}
    for chunk in (raw or "").split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = [part.strip().lower() for part in entry.split(":")]
        if len(parts) != 2 or not parts[0] or parts[1] not in STAGES:
            log.error(
                "DB_STORES: ignoring malformed entry %r (expected name:stage "
                "with stage in %s); that store remains on json",
                entry,
                "/".join(STAGES),
            )
            continue
        out[parts[0]] = parts[1]
    return out


def stage_for(store: str) -> str:
    """Return a store's migration stage, defaulting safely to JSON."""
    return parse(config.DB_STORES).get(store.lower(), JSON)


def writes_json(store: str) -> bool:
    """Whether the store must still commit its JSON representation."""
    return stage_for(store) in (JSON, DUAL)


def writes_db(store: str) -> bool:
    """Whether the store must commit a PostgreSQL representation."""
    return stage_for(store) in (DUAL, DB)


def reads_db(store: str) -> bool:
    """Whether reads have crossed the reversible cutover to PostgreSQL."""
    return stage_for(store) == DB
