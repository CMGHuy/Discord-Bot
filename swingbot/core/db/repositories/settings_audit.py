"""Append-only settings audit log."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import settings_audit


class SettingsAuditRepository(Repository):
    def __init__(self):
        # Keyed by the surrogate id: two identical changes a minute apart are
        # two entries, so there is no natural key to use.
        super().__init__(settings_audit, key="id")

    def append(self, changes: list, ts: str | None = None, *, conn=None) -> dict:
        return self.insert({
            "ts": ts or dt.datetime.now(dt.timezone.utc).isoformat(),
            "changes": changes,
        }, conn=conn)

    def recent(self, n: int = 20, *, conn=None) -> list[dict]:
        """Newest first, in the file version's ``{"ts", "changes"}`` shape."""
        rows = self.list_all(conn=conn, order_by=settings_audit.c.id.desc(), limit=n)
        return [{"ts": _iso(r.get("ts")), "changes": r.get("changes", [])} for r in rows]


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


_repo: SettingsAuditRepository | None = None


def settings_audit_repo() -> SettingsAuditRepository:
    global _repo
    if _repo is None:
        _repo = SettingsAuditRepository()
    return _repo
