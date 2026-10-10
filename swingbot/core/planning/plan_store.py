"""Persistence for live TradePlanV2 lifecycles (the `plans` table).
Every read goes to the repository and every write is a row-level upsert, so
a PlanStore instance holds no snapshot."""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       plan_from_dict, plan_to_dict)

log = logging.getLogger(__name__)
_LOCK = threading.Lock()

_OPEN_STATUSES = {PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL}


def _normalised(record: dict) -> dict:
    """A plans row with created_at as the ISO string TradePlanV2 stores."""
    if isinstance(record.get("created_at"), datetime):
        record["created_at"] = record["created_at"].isoformat()
    return record


class PlanStore:
    @staticmethod
    def _persist(plan_dict: dict, *, conn=None) -> None:
        """Upsert one plan row."""
        from swingbot.core.db.repositories.plans import plans_repo
        plans_repo().upsert(plan_dict, conn=conn)

    @staticmethod
    def _all() -> dict[str, dict]:
        """Map plan ids to records from the plans table."""
        from swingbot.core.db.repositories.plans import plans_repo
        return {record["plan_id"]: _normalised(record) for record in plans_repo().list_all()}

    def get_record(self, plan_id: str) -> dict | None:
        """The raw plan dict for a plan id, or None."""
        return self._all().get(plan_id)

    def records(self) -> list[dict]:
        """Every raw plan dict."""
        return list(self._all().values())

    def add(self, plan: TradePlanV2) -> None:
        with _LOCK:
            self._persist(plan_to_dict(plan))

    def get(self, plan_id: str) -> TradePlanV2 | None:
        d = self._all().get(plan_id)
        return plan_from_dict(d) if d else None

    def update(self, plan: TradePlanV2, *, conn=None) -> None:
        with _LOCK:
            if plan.plan_id not in self._all():
                raise KeyError(plan.plan_id)
            self._persist(plan_to_dict(plan), conn=conn)

    def open_plans(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._all().values()
                if d.get("status") in _OPEN_STATUSES]

    def all(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._all().values()]

    def for_session(self, day) -> list[TradePlanV2]:
        """v144: the outlook plans valid for one NYSE session (`day`: a date or
        an ISO string), oldest first. One indexed query, not a full scan."""
        from swingbot.core.db.repositories.plans import plans_repo
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        return [plan_from_dict(_normalised(record)) for record in plans_repo().for_session(key)]
