"""Grid-tuning results and proposals."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import tuning_proposals, tuning_results


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


class TuningRepository(Repository):
    def __init__(self):
        super().__init__(tuning_results, key="job_id")

    def save_result(self, job_id: str, payload: dict, *, conn=None) -> dict:
        return self.upsert({
            "job_id": job_id,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **payload,
        }, conn=conn)

    def result(self, job_id: str, *, conn=None) -> dict | None:
        row = self.get(job_id, conn=conn)
        if row is None:
            return None
        return {k: v for k, v in row.items()
                if k not in ("job_id", "created_at")}


class ProposalRepository(Repository):
    def __init__(self):
        super().__init__(tuning_proposals, key="filename")

    def save(self, filename: str, payload: dict, *,
             created_at: str | None = None, conn=None) -> dict:
        return self.upsert({
            "filename": filename,
            "created_at": created_at or dt.datetime.now(dt.timezone.utc).isoformat(),
            **payload,
        }, conn=conn)

    def all_proposals(self, *, conn=None) -> list[dict]:
        """Newest first. The file version got this from sorted(..., reverse=True)
        over timestamp-shaped filenames, which is the same ordering as long as
        the naming convention holds. created_at does not depend on it."""
        rows = self.list_all(conn=conn,
                             order_by=tuning_proposals.c.created_at.desc())
        return [{**row, "created_at": _iso(row.get("created_at"))} for row in rows]


_repo: TuningRepository | None = None
_proposals: ProposalRepository | None = None


def tuning_repo() -> TuningRepository:
    global _repo
    if _repo is None:
        _repo = TuningRepository()
    return _repo


def proposals_repo() -> ProposalRepository:
    global _proposals
    if _proposals is None:
        _proposals = ProposalRepository()
    return _proposals
