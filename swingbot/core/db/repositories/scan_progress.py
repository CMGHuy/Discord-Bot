"""The running scan's progress record: one row keyed `current` (v116).

A display artefact, deleted when the scan ends -- see progress_store.py."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import scan_progress

KEY = "current"


class ScanProgressRepository(Repository):
    def __init__(self):
        super().__init__(scan_progress, key="key")

    def publish(self, record: dict, *, conn=None) -> None:
        self.upsert({"key": KEY, **record}, conn=conn)

    def read(self, *, conn=None) -> dict | None:
        row = self.get(KEY, conn=conn)
        if row is None:
            return None
        return {name: value for name, value in row.items() if name != "key"}

    def clear(self, *, conn=None) -> None:
        self.delete(KEY, conn=conn)


_repo: ScanProgressRepository | None = None


def scan_progress_repo() -> ScanProgressRepository:
    global _repo
    if _repo is None:
        _repo = ScanProgressRepository()
    return _repo
