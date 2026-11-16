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

    def patch_if_coarser(self, trade_id: str, changes: dict, *,
                         coarser: tuple[str | None, ...], conn=None) -> dict | None:
        """v228: patch an entry only while its stored excursion_source is one
        of ``coarser`` (None = missing or JSON null). The rank guard is part of
        the UPDATE, so the bot's nightly pass and the backfill script cannot
        downgrade each other; fields not in ``changes`` (the note above all)
        are untouched. None when the row is missing or already as fine."""
        allowed = ["" if source is None else source for source in coarser]
        stored = sa.func.coalesce(journal_entries.c.doc["excursion_source"].astext, "")
        return self.patch(trade_id, changes, conn=conn, where=stored.in_(allowed))

    def version(self, *, conn=None) -> tuple[int, str | None]:
        """(row count, newest updated_at) over journal_entries -- the twin of
        PlanRepository.version(); same commit-order caveat (V218-1)."""
        statement = sa.select(sa.func.count(), sa.func.max(journal_entries.c.updated_at))
        with self._tx(conn) as connection:
            count, newest = connection.execute(statement).one()
        return int(count), None if newest is None else newest.isoformat()


_repo: JournalRepository | None = None


def journal_repo() -> JournalRepository:
    global _repo
    if _repo is None:
        _repo = JournalRepository()
    return _repo
