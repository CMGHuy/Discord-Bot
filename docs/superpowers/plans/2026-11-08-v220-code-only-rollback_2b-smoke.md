# v220 — Code-only rollback, Part 2b: `rollback_smoke` (V220-8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the write-free lifecycle evaluation `swingbot.core.infra.rollback_smoke` that `rollback_code.sh` (V220-9) runs inside v220+ images. It moved here from Part 2 to keep that file under 1500 lines; it shares no file or contract with V220-5..V220-7 and can run at any time (index Parallelisation). Its test reaches Postgres (suite `storage`); narrow runs only, `python scripts/dev/complexity_gate.py` stays green.


# Phase 2b — Smoke

### Task V220-8: `rollback_smoke`: write-free lifecycle evaluation

**Model:** opus — crosses `swingbot/core/infra`, `planning` and `db`

**Files:**
- Create: `swingbot/core/infra/rollback_smoke.py`
- Create: `tests/db/test_rollback_smoke.py`

**Interfaces:**
- Consumes (existing code, verified): `swingbot.core.planning.plan_store.PlanStore` (`get_record`, `records`, `get`, `open_plans`, `all`, `for_session`, `add`, `update`, `lock_for_update`, attribute `lock_timeout_ms`); `swingbot.core.planning.plan_manager.PlanManager(store, price_fn, …, trade_log=None)` and its `_step(plan, price, now=None)`; `swingbot.core.planning.plan_engine.PlanStatus`, `plan_from_dict`, `plan_to_dict`, `record_transition`; `swingbot.core.db.engine.get_engine` (module attribute, so the test conftest's patch reaches it); `swingbot.core.db.repositories.journal.journal_repo().list_all(where=…)`; `swingbot.core.db.schema.journal_entries`, `METADATA`; test helper `tests.planning.test_plan_engine_model._plan`.
- Produces (final, per the ledger; consumed by V220-9 and the V220-18 drill): module `swingbot.core.infra.rollback_smoke` with `OPEN_STATUSES`, `KNOWN_STATUSES`, `KNOWN` (`{"direction": …, "entry_type": …}`); `class ReadOnlyPlanStore(inner: PlanStore | None = None)` (reads delegate, `add`/`update`/`lock_for_update` record the plan id in `.attempted` and never persist; `update` returns `True`); `read_only_session()` (context manager: every new connection of the engine runs `SET SESSION default_transaction_read_only = on`, lifted on exit); `evaluate(plans: list[dict], journal_rows: list[dict], *, manager_factory=None) -> dict` (`plans` are raw open plan records as `PlanStore.records()` returns them; `manager_factory(store) -> manager`); `main(argv: list[str] | None = None) -> int`. Output: one JSON line on stdout `{"plans", "journal", "steps", "errors": [str], "unknown": [str], "attempted": [str]}` (the contract's five keys plus `attempted`, additive); exit 0 pass, 1 fail.

Decisions (spec § Execution step 6; index note "`rollback_smoke`"):
- **Two locks make it write-free.** (1) `ReadOnlyPlanStore` absorbs every plan write the step makes. (2) `read_only_session()` adds a `connect` listener to the engine and disposes its pool, so every connection opened afterwards starts with `SET SESSION default_transaction_read_only = on` (committed, so the setting survives the connect transaction); any writer the step reaches past the store raises instead of writing. On exit the listener is removed and the pool disposed again, so a test's later writes are read-write.
- **No trade-log writes, no network.** `PlanManager(store, price_fn=_no_price, trade_log=None)` with every optional function left `None`: with `trade_log=None` every persist helper (`_persist_fill`, `_persist_partial`, `_persist_terminal`) goes through `self._save` → `store.update` and never opens its own `transaction()`; with `daily_frame_fn`, `atr_fn`, `bar_count_fn`, `hourly_frame_fn`, `runner_bars_fn`, `auction_close_fn` at `None` nothing fetches bars or quotes. The price per plan is its `entry_price`, else its `trigger_price`; a plan with neither is an error.
- **`_step` directly, not `_step_safely`**, which swallows exceptions. Any exception from converting or stepping a plan is an error naming the plan; a write attempt is not an error (the store absorbed it) and is listed in `attempted`. `_on_event` and the bookkeeping in `poll` are not called: they post notices and write the feed.
- **Unknown values:** `status` outside `PlanStatus`'s constants, `direction` outside `bullish`/`bearish`, `entry_type` outside `stop_entry`/`market`/`limit` (the closed sets `TradePlanV2` documents, `plan_types.py`). A plan with an unknown value is reported in `unknown` and not stepped. `strategy`, `source` and `ledger` are already checked against the target tree by check 4 on the host.
- **Journal rows** (`journal_entries` with `closed_at IS NULL`) are read and counted; a row without `trade_id` is an error. The lifecycle code does not step them.
- **Load failure** (database down, unreadable rows) prints the same JSON line with `errors: ["load: …"]` and exits 1, so V220-9 always gets one parseable line. Logging goes to stderr at WARNING; stdout carries only the JSON line.
- Tests reach Postgres: run `/replicate-prod-db` first (the shared `swing-db` on port 56789); the `tests/conftest.py` autouse fixture `_store_database` points `get_engine` at this worker's test database and truncates afterwards.

- [ ] **Step 1: Sync the local replica**

Run `/replicate-prod-db` (skip when a sibling task in this session already did).

- [ ] **Step 2: Write the failing tests**

Create `tests/db/test_rollback_smoke.py`:

```python
"""v220 V220-8: rollback_smoke steps every open plan once and writes nothing."""
from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.journal import journal_repo
from swingbot.core.db.schema import METADATA
from swingbot.core.infra import rollback_smoke as rs
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


def _active(pid: str = "A1"):
    plan = _plan(plan_id=pid, entry_type="market", trigger_price=100.0, entry_price=100.0,
                 stop_loss=95.0, tp1=110.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def _pending(pid: str = "P1", **kw):
    base = dict(plan_id=pid, entry_type="stop_entry", trigger_price=105.0, entry_price=None,
                stop_loss=95.0, tp1=110.0)
    return _plan(**{**base, **kw})


def _journal(trade_id: str, closed_at: str | None) -> dict:
    return dict(trade_id=trade_id, strategy="RSI", outcome=None if closed_at is None else "win",
                closed_at=closed_at, created_at="2026-11-01T10:00:00+00:00", note="")


def _state(engine) -> dict:
    """Row count of every table plus each plans/journal row's updated_at and doc."""
    with engine.connect() as conn:
        counts = {t.name: conn.execute(sa.select(sa.func.count()).select_from(t)).scalar()
                  for t in METADATA.sorted_tables}
        plans = conn.execute(sa.text("SELECT plan_id, status, updated_at, doc FROM plans ORDER BY 1")).all()
        journal = conn.execute(sa.text("SELECT trade_id, updated_at, doc FROM journal_entries ORDER BY 1")).all()
    return {"counts": counts, "plans": [tuple(r) for r in plans], "journal": [tuple(r) for r in journal]}


class _Stub:
    def __init__(self, error: Exception | None = None):
        self.error, self.calls = error, []

    def _step(self, plan, price, now=None):
        self.calls.append((plan.plan_id, price))
        if self.error:
            raise self.error
        return []


def _seed():
    store = PlanStore()
    store.add(_active("A1"))
    store.add(_pending("P1"))
    store.add(_plan(plan_id="C1", status=PlanStatus.CLOSED))
    journal_repo().upsert(_journal("T-open", None))
    journal_repo().upsert(_journal("T-closed", "2026-11-02T10:00:00+00:00"))


def test_main_steps_every_open_plan_and_writes_nothing(db_engine, capsys):
    _seed()
    before = _state(db_engine)
    assert rs.main([]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (out["plans"], out["journal"], out["steps"]) == (2, 1, 2)
    assert out["errors"] == [] and out["unknown"] == []
    assert set(out["attempted"]) <= {"A1", "P1"}
    assert _state(db_engine) == before


def test_unknown_entry_type_fails_main_and_still_writes_nothing(db_engine, capsys):
    PlanStore().add(_pending("P9", entry_type="bracket"))
    before = _state(db_engine)
    assert rs.main([]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["unknown"] == ["P9: entry_type=bracket"] and out["steps"] == 0
    assert _state(db_engine) == before


def test_read_only_session_blocks_writes_and_is_lifted_after(db_engine):
    with rs.read_only_session():
        with pytest.raises(sa.exc.DBAPIError):
            PlanStore().add(_active("X1"))
    assert PlanStore().get("X1") is None
    PlanStore().add(_active("X2"))
    assert PlanStore().get("X2") is not None


def test_read_only_store_absorbs_every_write(db_engine):
    PlanStore().add(_active("A1"))
    store = rs.ReadOnlyPlanStore()
    plan = store.get("A1")
    plan.working_stop = 99.0
    assert store.update(plan) is True
    store.add(plan)
    assert store.lock_for_update("A1", conn=None).plan_id == "A1"
    assert store.attempted == ["A1", "A1", "A1"]
    assert PlanStore().get("A1").working_stop is None
    assert [p.plan_id for p in store.open_plans()] == ["A1"]


def test_unknown_direction_is_reported_and_not_stepped():
    record = plan_to_dict(_active("A1"))
    record["direction"] = "sideways"
    stub = _Stub()
    result = rs.evaluate([record], [], manager_factory=lambda store: stub)
    assert result["unknown"] == ["A1: direction=sideways"] and result["steps"] == 0 and stub.calls == []


def test_step_exception_is_an_error_and_the_price_is_the_entry():
    stub = _Stub(KeyError("boom"))
    result = rs.evaluate([plan_to_dict(_active("A1"))], [], manager_factory=lambda store: stub)
    assert stub.calls == [("A1", 100.0)]
    assert result["errors"] and result["errors"][0].startswith("A1: KeyError") and result["steps"] == 0


def test_pending_plan_steps_at_its_trigger_and_a_priceless_plan_is_an_error():
    stub = _Stub()
    good = plan_to_dict(_pending("P1"))
    bad = plan_to_dict(_pending("P2", trigger_price=0.0))
    result = rs.evaluate([good, bad], [{"trade_id": "T1"}, {}], manager_factory=lambda store: stub)
    assert stub.calls == [("P1", 105.0)] and result["steps"] == 1
    assert any(e.startswith("P2: ValueError") for e in result["errors"])
    assert "journal row without trade_id" in result["errors"]
    assert (result["plans"], result["journal"]) == (2, 2)


def test_load_failure_is_one_failed_json_line(monkeypatch, capsys):
    def boom():
        raise RuntimeError("db is down")
    monkeypatch.setattr(rs, "_open_journal_rows", boom)
    assert rs.main([]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["errors"] == ["load: RuntimeError: db is down"] and out["steps"] == 0
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_rollback_smoke.py`
Expected: FAIL with `ImportError: cannot import name 'rollback_smoke' from 'swingbot.core.infra'` (a skip with the `db-test` start command means the database is not up: start it, do not skip the task).

- [ ] **Step 4: Write the implementation**

Create `swingbot/core/infra/rollback_smoke.py`:

```python
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
```

Notes for the implementer:
- `test_load_failure_is_one_failed_json_line` patches `_open_journal_rows`; `main` must look it up as a module global at call time (as written), not bind it earlier.
- If `PlanManager._step` turns out to reach a writer outside the store for an ordinary open plan (the read-only session then raises), that is a real finding: report it to the controller rather than loosening either lock.
- `test_main_steps_every_open_plan_and_writes_nothing` compares `updated_at` and `doc` of every plans/journal row and the row count of every table before and after; it is the spec's "asserting it writes nothing".
- V220-9 reads the **last** stdout line of `docker compose run --rm --no-deps -T bot python -m swingbot.core.infra.rollback_smoke` as the JSON result and uses the exit code as the verdict.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_rollback_smoke.py`
Then: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py` (the manager the smoke drives is unchanged)
Expected: both `0 failed`.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/infra/rollback_smoke.py tests/db/test_rollback_smoke.py
git commit -m "feat(v220): rollback_smoke -- one write-free lifecycle step per open plan on a read-only session"
```

