"""Fire-once-a-day memory for the recap and weekend scan."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import scheduled_jobs


class ScheduledJobRepository(Repository):
    def __init__(self):
        super().__init__(scheduled_jobs, key="job")

    def fired_on(self, job: str, *, conn=None) -> str | None:
        row = self.get(job, conn=conn)
        return None if row is None else row.get("fired_on")

    def mark(self, job: str, date_iso: str, *, conn=None) -> None:
        self.upsert({"job": job, "fired_on": date_iso}, conn=conn)


_repo: ScheduledJobRepository | None = None


def scheduled_repo() -> ScheduledJobRepository:
    global _repo
    if _repo is None:
        _repo = ScheduledJobRepository()
    return _repo
