"""JSON persistence for live TradePlanV2 lifecycles (data/plans.json).
Atomic writes (temp + os.replace) -- a crash mid-write can never leave a
torn file. Same locking idiom as state.py."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       plan_from_dict, plan_to_dict)

log = logging.getLogger("swing-bot.plan_store")
_LOCK = threading.Lock()

_OPEN_STATUSES = {PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL}


class PlanStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "plans.json")
        self._plans: dict[str, dict] = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                records = json.load(f)
            return {r["plan_id"]: r for r in records}
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            log.warning("plans.json unreadable (%s); starting empty", exc)
            return {}

    def reload(self) -> None:
        """Re-read plans.json from disk into `self._plans`.

        Every OTHER call site makes a fresh `PlanStore()` per use, so its
        `__init__` load is always current. `plan_manager.run_manager_tick()`
        is the one exception: it builds a single `PlanManager` the first
        time it runs and keeps it (and the `PlanStore` instance handed to
        it) for the life of the process, so without an explicit reload here
        its `_plans` snapshot is forever whatever existed at that first
        tick. Any plan added afterward (every new Discord alert, via
        `engine.py`'s own fresh `PlanStore().add()`) is invisible to
        `poll()` -- it never fills, never gets checked against its
        SL/TP, and never closes -- and worse, the NEXT unrelated plan this
        stale instance `update()`s serializes `list(self._plans.values())`
        and clobbers plans.json, erasing the newer plan from disk entirely.
        Call this before every poll so the tick always acts on -- and
        writes back -- current state rather than a point-in-time snapshot.
        """
        from swingbot.core.db import stages
        if stages.reads_db("plans"):
            return
        with _LOCK:
            self._plans = self._load()

    def _save(self) -> None:
        # Through jsonio rather than a second copy of the tmp+replace dance.
        # The duplicate was missing the fsync AND the Windows retry, so this
        # store was the one most likely to lose a write -- and it is the store
        # the scan loop writes to most often.
        atomic_write_json(self.path, list(self._plans.values()))

    def _persist(self, plan_dict: dict | None = None, *, conn=None) -> None:
        """Write through to the backends selected for the plans store."""
        from swingbot.core.db import stages
        if stages.writes_json("plans"):
            self._save()
        if not stages.writes_db("plans"):
            return
        from swingbot.core.db.repositories.plans import plans_repo
        repository = plans_repo()
        if plan_dict is not None:
            repository.upsert(plan_dict, conn=conn)
        else:
            for record in self._plans.values():
                repository.upsert(record, conn=conn)

    def _all(self) -> dict[str, dict]:
        """Map plan ids to records from the backend selected for reads."""
        from swingbot.core.db import stages
        if not stages.reads_db("plans"):
            return self._plans
        from swingbot.core.db.repositories.plans import plans_repo
        records = plans_repo().list_all()
        for record in records:
            if isinstance(record.get("created_at"), datetime):
                record["created_at"] = record["created_at"].isoformat()
        return {record["plan_id"]: record for record in records}

    def add(self, plan: TradePlanV2) -> None:
        with _LOCK:
            self._plans[plan.plan_id] = plan_to_dict(plan)
            self._persist(self._plans[plan.plan_id])

    def get(self, plan_id: str) -> TradePlanV2 | None:
        d = self._all().get(plan_id)
        return plan_from_dict(d) if d else None

    def update(self, plan: TradePlanV2, *, conn=None) -> None:
        with _LOCK:
            if plan.plan_id not in self._all():
                raise KeyError(plan.plan_id)
            self._plans[plan.plan_id] = plan_to_dict(plan)
            self._persist(self._plans[plan.plan_id], conn=conn)

    def open_plans(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._all().values()
                if d.get("status") in _OPEN_STATUSES]

    def all(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._all().values()]
