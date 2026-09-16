"""Per-trade lessons journal queries."""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import journal_entries


class JournalRepository(Repository):
    """Journal entries with the same filters as the JSON JournalStore."""

    def __init__(self):
        super().__init__(journal_entries, key="trade_id")

    def entries(self, *, strategy: str | None = None, tag: str | None = None,
                outcome: str | None = None, since: str | None = None,
                has_note: bool | None = None, conn=None) -> list[dict]:
        clauses = []
        if strategy is not None:
            clauses.append(journal_entries.c.strategy == strategy)
        if outcome is not None:
            clauses.append(journal_entries.c.outcome == outcome)
        if since is not None:
            clauses.append(journal_entries.c.closed_at >= datetime.fromisoformat(since))
        if tag is not None:
            clauses.append(journal_entries.c.doc["tags"].contains([tag]))
        if has_note is not None:
            note = sa.func.btrim(
                sa.func.coalesce(journal_entries.c.doc["note"].astext, "")
            )
            clauses.append(note != "" if has_note else note == "")
        return self.list_all(
            conn=conn,
            where=sa.and_(*clauses) if clauses else None,
            order_by=sa.desc(sa.func.coalesce(
                journal_entries.c.closed_at, journal_entries.c.created_at)),
        )


_repo: JournalRepository | None = None


def journal_repo() -> JournalRepository:
    global _repo
    if _repo is None:
        _repo = JournalRepository()
    return _repo
