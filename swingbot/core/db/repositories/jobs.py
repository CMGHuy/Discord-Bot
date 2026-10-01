"""Admin job state with per-job progress updates."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import admin_jobs


ACTIVE_STATUSES = ("running", "starting")


class JobRepository(Repository):
    def __init__(self):
        super().__init__(admin_jobs, key="job_id")

    def all_jobs(self, *, conn=None) -> dict[str, dict]:
        return {job["job_id"]: self._legacy(job) for job in self.list_all(
            conn=conn, order_by=admin_jobs.c.started_at.desc())}

    @staticmethod
    def _storage(record: dict) -> dict:
        record = dict(record)
        # The JSON job record is keyed by `id` and never carries `job_id`; the
        # table's natural key is `job_id`, and `id` is its surrogate column.
        legacy_id = record.pop("id", None)
        if legacy_id is not None:
            record.setdefault("job_id", legacy_id)
        if "state" in record:
            # `state` is the field callers edit; a record read back from the table
            # carries both, and the edited `state` must win.
            record["status"] = record["state"]
        return record

    @staticmethod
    def _legacy(record: dict | None) -> dict | None:
        if record is None:
            return None
        record = dict(record)
        if "status" in record:
            record["state"] = record["status"]
        record["id"] = record["job_id"]
        return record

    def get_job(self, job_id: str, *, conn=None) -> dict | None:
        return self._legacy(self.get(job_id, conn=conn))

    def put(self, record: dict, *, conn=None) -> dict:
        return self._legacy(self.upsert(self._storage(record), conn=conn))

    def patch_job(self, job_id: str, changes: dict, *, conn=None) -> dict | None:
        return self._legacy(self.patch(job_id, self._storage(changes), conn=conn))

    def active(self, *, conn=None) -> list[dict]:
        return [self._legacy(job) for job in self.list_all(
            conn=conn,
            where=admin_jobs.c.status.in_(ACTIVE_STATUSES),
            order_by=admin_jobs.c.started_at.desc(),
        )]

    def prune(self, before_ts: str, *, conn=None) -> int:
        """Drop finished, old jobs but never a live process record."""
        stmt = sa.delete(admin_jobs).where(sa.and_(
            admin_jobs.c.status.notin_(ACTIVE_STATUSES),
            admin_jobs.c.finished_at.isnot(None),
            admin_jobs.c.finished_at < before_ts,
        ))
        with self._tx(conn) as connection:
            return connection.execute(stmt).rowcount


_repo: JobRepository | None = None


def jobs_repo() -> JobRepository:
    global _repo
    if _repo is None:
        _repo = JobRepository()
    return _repo
