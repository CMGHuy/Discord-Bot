"""v220: write-free lifecycle evaluation after a code-only rollback.

`python -m swingbot.core.infra.rollback_smoke` runs inside the target image once
rollback_code.sh has switched code and image. It reads the open plans and the open
journal rows, runs one PlanManager._step per open plan at the plan's own entry price
through a store that never persists, on database connections forced read-only, and
prints one JSON line. Exit 0 pass, 1 fail (any exception or unknown value).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import contextmanager

from sqlalchemy import event

from swingbot.core.db import engine as engine_module
from swingbot.core.planning.plan_engine import PlanStatus, plan_from_dict
from swingbot.core.planning.plan_store import PlanStore

OPEN_STATUSES = (PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL)
KNOWN_STATUSES = frozenset(value for name, value in vars(PlanStatus).items() if name.isupper())
# The closed sets the lifecycle code branches on (TradePlanV2, plan_types.py).
KNOWN = {"direction": frozenset({"bullish", "bearish"}),
         "entry_type": frozenset({"stop_entry", "market", "limit"})}


class ReadOnlyPlanStore:
    """PlanStore reads; every write is recorded in `.attempted` and never persisted."""

    def __init__(self, inner: PlanStore | None = None):
        self._inner = inner if inner is not None else PlanStore()
        self.attempted: list[str] = []
        self.lock_timeout_ms = self._inner.lock_timeout_ms

    def get_record(self, plan_id, *, conn=None, for_update=False):
        return self._inner.get_record(plan_id)      # never a locking read

    def records(self):
        return self._inner.records()

    def get(self, plan_id, *, conn=None, for_update=False):
        return self._inner.get(plan_id)

    def open_plans(self):
        return self._inner.open_plans()

    def all(self):
        return self._inner.all()

    def for_session(self, day):
        return self._inner.for_session(day)

    def add(self, plan) -> None:
        self.attempted.append(plan.plan_id)

    def update(self, plan, *, conn=None) -> bool:
        self.attempted.append(plan.plan_id)
        return True

    def lock_for_update(self, plan_id, *, conn):
        self.attempted.append(plan_id)
        return self._inner.get(plan_id)


def _set_read_only(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET SESSION default_transaction_read_only = on")
    finally:
        cursor.close()
    dbapi_connection.commit()   # a SET inside a rolled-back transaction would not stick


@contextmanager
def read_only_session():
    """Every connection the engine opens inside this block is read-only."""
    engine = engine_module.get_engine()
    event.listen(engine, "connect", _set_read_only)
    engine.dispose()
    try:
        yield engine
    finally:
        event.remove(engine, "connect", _set_read_only)
        engine.dispose()


def _no_price(ticker):
    raise RuntimeError(f"rollback_smoke never fetches a price ({ticker})")


def _default_manager(store):
    from swingbot.core.planning.plan_manager import PlanManager
    return PlanManager(store, price_fn=_no_price, trade_log=None)


def _unknown(record: dict) -> list[str]:
    plan_id = record.get("plan_id", "?")
    found = [] if record.get("status") in KNOWN_STATUSES else [f"{plan_id}: status={record.get('status')}"]
    found += [f"{plan_id}: {field}={record.get(field)}"
              for field, allowed in KNOWN.items() if record.get(field) not in allowed]
    return found


def _price(plan) -> float | None:
    for value in (plan.entry_price, plan.trigger_price):
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _step_one(manager, record: dict, result: dict) -> None:
    plan_id = record.get("plan_id", "?")
    try:
        plan = plan_from_dict(record)
        price = _price(plan)
        if price is None:
            raise ValueError("no entry or trigger price")
        manager._step(plan, price, None)
    except Exception as exc:  # noqa: BLE001 - every failure is the finding
        result["errors"].append(f"{plan_id}: {type(exc).__name__}: {exc}")
        return
    result["steps"] += 1


def _result(plans: int, journal: int) -> dict:
    return {"plans": plans, "journal": journal, "steps": 0, "errors": [], "unknown": [], "attempted": []}


def evaluate(plans: list[dict], journal_rows: list[dict], *, manager_factory=None) -> dict:
    """One _step per open plan record through a ReadOnlyPlanStore; the JSON-line dict."""
    store = ReadOnlyPlanStore()
    manager = (manager_factory or _default_manager)(store)
    result = _result(len(plans), len(journal_rows))
    result["errors"] += ["journal row without trade_id" for row in journal_rows if not row.get("trade_id")]
    for record in plans:
        unknown = _unknown(record)
        result["unknown"] += unknown
        if not unknown:
            _step_one(manager, record, result)
    result["attempted"] = sorted(set(store.attempted))
    return result


def _open_records() -> list[dict]:
    return [record for record in PlanStore().records() if record.get("status") in OPEN_STATUSES]


def _open_journal_rows() -> list[dict]:
    from swingbot.core.db.repositories.journal import journal_repo
    from swingbot.core.db.schema import journal_entries
    return journal_repo().list_all(where=journal_entries.c.closed_at.is_(None))


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    try:
        with read_only_session():
            result = evaluate(_open_records(), _open_journal_rows())
    except Exception as exc:  # noqa: BLE001 - one parseable failure line, always
        result = _result(0, 0)
        result["errors"].append(f"load: {type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True))
    return 1 if result["errors"] or result["unknown"] else 0


if __name__ == "__main__":
    sys.exit(main())
