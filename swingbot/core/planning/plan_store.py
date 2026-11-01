"""Persistence for live TradePlanV2 lifecycles (the `plans` table).
Every read goes to the repository and every write is a row-level upsert, so
a PlanStore instance holds no snapshot.

v189 D3.3: `update` is the one guarded write. It takes the plan row lock
(`SELECT ... FOR UPDATE`, waiting at most `lock_timeout_ms`), refuses to
overwrite a CLOSED/CANCELLED plan with a stale copy, and never loosens the
stop of an ACTIVE/PARTIAL plan. The row lock, not the process-local `_LOCK`,
is what serialises the bot and admin processes; `update` never holds `_LOCK`
while waiting on the row."""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.planning.exit_sim import tighter_stop
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       plan_from_dict, plan_to_dict)

log = logging.getLogger(__name__)
_LOCK = threading.Lock()

_OPEN_STATUSES = {PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL}
_TERMINAL_STATUSES = {PlanStatus.CLOSED, PlanStatus.CANCELLED}
_STOP_BEARING = {PlanStatus.ACTIVE, PlanStatus.PARTIAL}


def _refuses(stored_status: str | None, incoming_status: str) -> bool:
    """A stale copy may never overwrite a terminal plan; the same terminal
    write (a notice or ack on a plan this process just closed) is allowed."""
    return stored_status in _TERMINAL_STATUSES and incoming_status != stored_status


def _merged_stop(stored: float | None, incoming: float | None, is_bull: bool) -> float | None:
    """The tighter of two stops; a missing one never loosens the other."""
    if incoming is None:
        return stored
    if stored is None:
        return incoming
    return tighter_stop(float(incoming), float(stored), is_bull)


def _keep_tighter_stops(stored: dict, plan: TradePlanV2) -> None:
    """For a stop-bearing plan, write back the tighter of the stored and the
    incoming stop_loss and working_stop onto ``plan`` (so the caller's copy
    and the row agree). Other statuses are written as given."""
    if stored.get("status") not in _STOP_BEARING or plan.status not in _STOP_BEARING:
        return
    is_bull = plan.direction == "bullish"
    plan.stop_loss = _merged_stop(stored.get("stop_loss"), plan.stop_loss, is_bull)
    plan.working_stop = _merged_stop(stored.get("working_stop"), plan.working_stop, is_bull)


def _normalised(record: dict) -> dict:
    """A plans row with created_at as the ISO string TradePlanV2 stores."""
    if isinstance(record.get("created_at"), datetime):
        record["created_at"] = record["created_at"].isoformat()
    return record


class PlanStore:
    def __init__(self, *, lock_timeout_ms: int = ADMIN_LOCK_TIMEOUT_MS):
        # How long update() waits on the plan row lock in a transaction it owns.
        # The plan manager lowers this to BOT_LOCK_TIMEOUT_MS on its own store.
        self.lock_timeout_ms = lock_timeout_ms

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

    def lock_for_update(self, plan_id: str, *, conn) -> TradePlanV2 | None:
        """Lock the plan row inside the caller's transaction and return the plan
        as stored, or None when it does not exist."""
        from swingbot.core.db.repositories.plans import plans_repo
        record = plans_repo().get_for_update(plan_id, conn=conn)
        return plan_from_dict(_normalised(record)) if record else None

    def update(self, plan: TradePlanV2, *, conn=None) -> bool:
        """Write the whole plan under its row lock. False (and nothing written)
        when the stored plan is terminal and this copy is not the same terminal
        write; raises KeyError when the row is absent. LockTimeout propagates
        from a transaction this call owns."""
        from swingbot.core.db.repositories.plans import plans_repo
        with transaction(conn, lock_timeout_ms=self.lock_timeout_ms) as tx:
            stored = plans_repo().get_for_update(plan.plan_id, conn=tx)
            if stored is None:
                raise KeyError(plan.plan_id)
            if _refuses(stored.get("status"), plan.status):
                log.info("plan store: refused stale write to %s (stored %s, incoming %s)",
                         plan.plan_id, stored.get("status"), plan.status)
                return False
            _keep_tighter_stops(stored, plan)
            self._persist(plan_to_dict(plan), conn=tx)
        return True

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
