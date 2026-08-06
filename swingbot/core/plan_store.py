"""JSON persistence for live TradePlanV2 lifecycles (data/plans.json).
Atomic writes (temp + os.replace) -- a crash mid-write can never leave a
torn file. Same locking idiom as state.py."""
from __future__ import annotations

import json
import logging
import os
import threading

from swingbot import config
from swingbot.core.plan_engine import (PlanStatus, TradePlanV2,
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

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self._plans.values()), f, indent=2)
        os.replace(tmp, self.path)

    def add(self, plan: TradePlanV2) -> None:
        with _LOCK:
            self._plans[plan.plan_id] = plan_to_dict(plan)
            self._save()

    def get(self, plan_id: str) -> TradePlanV2 | None:
        d = self._plans.get(plan_id)
        return plan_from_dict(d) if d else None

    def update(self, plan: TradePlanV2) -> None:
        with _LOCK:
            if plan.plan_id not in self._plans:
                raise KeyError(plan.plan_id)
            self._plans[plan.plan_id] = plan_to_dict(plan)
            self._save()

    def open_plans(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._plans.values()
                if d.get("status") in _OPEN_STATUSES]

    def all(self) -> list[TradePlanV2]:
        return [plan_from_dict(d) for d in self._plans.values()]
