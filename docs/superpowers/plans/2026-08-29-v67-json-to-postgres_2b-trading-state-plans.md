# v67 — Part 2: Live trading state (tasks P2-06…P2-12)

> Continuation of `2026-08-29-v67-json-to-postgres_2a-trading-state-trades.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P2-06: Trades parity report

Before flipping `trades` to `db` in production, evidence. This script reads both
backends and reports divergence — the same comparison the dual-write logging
does, run deliberately over the whole store rather than one record at a time.

**Files:**
- Create: `scripts/db/parity_report.py`
- Test: `tests/scripts/test_parity_report.py`

**Interfaces:**
- Consumes: `diff_records` (P1-11), `compare` (P2-02), `TradeRepository`.
- Produces: `parity(store: str) -> ImportReport` and a CLI
  `python scripts/db/parity_report.py --store trades`, reusable by every later
  part.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_parity_report.py`:

```python
"""The evidence a store is safe to flip to db."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.infra.jsonio import atomic_write_json
from scripts.db.parity_report import STORES, parity


def _rec(trade_id, **over):
    r = dict(trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
             direction="bullish", status="open",
             opened_at="2026-01-02T15:00:00+00:00")
    r.update(over)
    return r


@pytest.fixture
def isolated(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_every_registered_store_names_a_real_file_and_repository():
    for name, spec in STORES.items():
        assert spec.filename, name
        assert spec.key, name
        assert callable(spec.repo_factory), name


def test_matching_backends_report_ok(isolated):
    rows = [_rec("T1"), _rec("T2")]
    atomic_write_json(os.path.join(isolated, "trades.json"), rows)
    for r in rows:
        TradeRepository().upsert(r)
    assert parity("trades").ok


def test_a_row_only_in_the_file_is_reported_missing(isolated):
    atomic_write_json(os.path.join(isolated, "trades.json"), [_rec("T1")])
    assert parity("trades").missing == ["T1"]


def test_a_row_only_in_the_database_is_reported_extra(isolated):
    atomic_write_json(os.path.join(isolated, "trades.json"), [])
    TradeRepository().upsert(_rec("T9"))
    assert parity("trades").extra == ["T9"]


def test_a_diverged_field_is_reported(isolated):
    atomic_write_json(os.path.join(isolated, "trades.json"),
                      [_rec("T1", entry=100.0)])
    TradeRepository().upsert(_rec("T1", entry=101.0))
    assert parity("trades").mismatched == ["T1"]


def test_an_unknown_store_raises_rather_than_reporting_clean(isolated):
    with pytest.raises(KeyError):
        parity("not-a-store")
```

`test_an_unknown_store_raises_rather_than_reporting_clean` is the important one:
a typo'd store name that returned an empty, passing report would be the exact
way someone flips a store to `db` on evidence that was never gathered.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/scripts/test_parity_report.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.db.parity_report'`.

- [ ] **Step 3: Write the report**

Create `scripts/db/parity_report.py`:

```python
#!/usr/bin/env python3
"""Compare a store's JSON file against its Postgres table.

Run this at the dual stage, over real data, before flipping a store to db.
The dual-write logging catches divergence one record at a time as it happens;
this catches it in aggregate, on demand, which is what a go/no-go needs.

    python scripts/db/parity_report.py --store trades
    python scripts/db/parity_report.py --all
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from swingbot import config                              # noqa: E402
from swingbot.core.infra.jsonio import read_json         # noqa: E402
from scripts.db.import_common import ImportReport, compare  # noqa: E402


@dataclass(frozen=True)
class StoreSpec:
    filename: str
    key: str
    repo_factory: Callable[[], object]


def _trades_repo():
    from swingbot.core.db.repositories.trades import TradeRepository
    return TradeRepository()


#: Every migrated store. Later parts append their own entries here; this dict
#: is what --all iterates, so a store missing from it is a store nobody checks.
STORES: dict[str, StoreSpec] = {
    "trades": StoreSpec("trades.json", "trade_id", _trades_repo),
}


def parity(store: str) -> ImportReport:
    spec = STORES[store]           # KeyError on a typo, deliberately
    rows = read_json(os.path.join(config.DATA_DIR, spec.filename), [])
    if isinstance(rows, dict):     # plans.json-shaped stores index by key
        rows = list(rows.values())
    return compare(rows, spec.repo_factory().list_all(), key=spec.key)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", choices=sorted(STORES))
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    if not (args.store or args.all):
        ap.error("pass --store <name> or --all")

    names = sorted(STORES) if args.all else [args.store]
    failed = 0
    for name in names:
        report = parity(name)
        print(f"[{name}]")
        print(report.render())
        failed += 0 if report.ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_parity_report.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/parity_report.py tests/scripts/test_parity_report.py
git commit -m "feat(v67): add the store parity report"
```

---

### Task P2-07: The plans repository and importer

`plans.json` is the store the scan loop writes most often, and `PlanStore._save()`
serialises `list(self._plans.values())` on every `add()` and `update()`.

**Files:**
- Create: `swingbot/core/db/repositories/plans.py`
- Create: `scripts/db/import_plans.py`
- Modify: `scripts/db/parity_report.py` (register `plans`)
- Test: `tests/db/test_plans_repository.py`

**Interfaces:**
- Consumes: `Repository` (P1-09), `plans` table (P2-01), `run_import` (P2-02),
  `StoreSpec`/`STORES` (P2-06).
- Produces: `PlanRepository` with `open_plans()`, `by_ticker(ticker)`; and
  `plans_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_plans_repository.py`:

```python
"""PlanRepository. The status set that counts as open comes from plan_engine."""
import pytest

from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus


@pytest.fixture
def repo():
    return PlanRepository()


def _p(plan_id, status=PlanStatus.PENDING, **over):
    base = dict(plan_id=plan_id, ticker="AAPL", strategy="RSI", horizon_key="2w",
                status=status, created_at="2026-01-02T15:00:00+00:00",
                entry=100.0, stop_loss=95.0)
    base.update(over)
    return base


def test_open_plans_covers_pending_active_and_partial(repo, db_conn):
    for i, status in enumerate((PlanStatus.PENDING, PlanStatus.ACTIVE,
                                PlanStatus.PARTIAL)):
        repo.insert(_p(f"P{i}", status=status), conn=db_conn)
    repo.insert(_p("PCLOSED", status=PlanStatus.CLOSED), conn=db_conn)
    assert {p["plan_id"] for p in repo.open_plans(conn=db_conn)} == {"P0", "P1", "P2"}


def test_open_statuses_match_plan_store(repo):
    from swingbot.core.planning.plan_store import _OPEN_STATUSES
    assert set(repo.OPEN_STATUSES) == set(_OPEN_STATUSES)


def test_by_ticker(repo, db_conn):
    repo.insert(_p("P1", ticker="AAPL"), conn=db_conn)
    repo.insert(_p("P2", ticker="MSFT"), conn=db_conn)
    assert [p["plan_id"] for p in repo.by_ticker("aapl", conn=db_conn)] == ["P1"]


def test_the_full_plan_dict_round_trips(repo, db_conn):
    from swingbot.core.db.dual import diff_records
    rec = _p("P1", legs=[{"fraction": 0.5, "r": 1.0}], take_profit=110.0,
             confidence={"level": 4, "score": 71})
    repo.insert(rec, conn=db_conn)
    assert diff_records(rec, repo.get("P1", conn=db_conn)) == []
```

`test_open_statuses_match_plan_store` is what stops the two definitions drifting
when a later plan adds a status.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_plans_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/plans.py`:

```python
"""Live TradePlanV2 lifecycles."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plans


class PlanRepository(Repository):
    # Imported from plan_store rather than restated, so the two cannot drift.
    # A status added by a later plan reaches both at once.
    @property
    def OPEN_STATUSES(self):
        from swingbot.core.planning.plan_store import _OPEN_STATUSES
        return tuple(_OPEN_STATUSES)

    def __init__(self):
        super().__init__(plans, key="plan_id")

    def open_plans(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn,
                             where=plans.c.status.in_(self.OPEN_STATUSES),
                             order_by=plans.c.created_at.desc())

    def by_ticker(self, ticker: str, *, conn=None) -> list[dict]:
        return self.list_all(
            conn=conn,
            where=sa.func.upper(plans.c.ticker) == (ticker or "").upper(),
            order_by=plans.c.created_at.desc(),
        )


_repo: PlanRepository | None = None


def plans_repo() -> PlanRepository:
    global _repo
    if _repo is None:
        _repo = PlanRepository()
    return _repo
```

- [ ] **Step 4: Write the importer and register the store**

Create `scripts/db/import_plans.py`, copying `import_trades.py`'s shape with
`load_source` returning `read_json(path or data/plans.json, [])`,
`key="plan_id"`, `name="plans"`, and `repo=PlanRepository()`.

In `scripts/db/parity_report.py`, add:

```python
def _plans_repo():
    from swingbot.core.db.repositories.plans import PlanRepository
    return PlanRepository()


STORES["plans"] = StoreSpec("plans.json", "plan_id", _plans_repo)
```

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_plans_repository.py
python scripts/dev/testrun.py file tests/scripts/test_parity_report.py
python scripts/db/import_plans.py --dry-run
```

Expected: `0 failed`, and a dry run reporting the local record count.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/plans.py scripts/db/import_plans.py \
        scripts/db/parity_report.py tests/db/test_plans_repository.py
git commit -m "feat(v67): add the plans repository and importer"
```

---

### Task P2-08: PlanStore writes both

**Files:**
- Modify: `swingbot/core/planning/plan_store.py`
- Test: `tests/planning/test_plan_store_dual.py`

**Interfaces:**
- Consumes: `stages` (P1-10), `plans_repo` (P2-07), `plan_to_dict` (existing).
- Produces on `PlanStore`: `_persist(plan_dict: dict | None = None) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_store_dual.py`:

```python
"""PlanStore at each stage."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _plan(plan_id="P1"):
    """Build a real TradePlanV2 through the same path the scan uses."""
    from swingbot.core.planning.plan_engine import plan_from_dict
    return plan_from_dict({
        "plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
        "horizon_key": "2w", "status": PlanStatus.PENDING,
        "created_at": "2026-01-02T15:00:00+00:00",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "direction": "bullish",
    })


def _file_plans(data_dir):
    path = os.path.join(data_dir, "plans.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_json_stage_writes_only_the_file(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    PlanStore().add(_plan())
    assert len(_file_plans(data_dir)) == 1
    assert PlanRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    PlanStore().add(_plan())
    assert len(_file_plans(data_dir)) == 1
    assert PlanRepository().get("P1", conn=db_committed) is not None


def test_update_writes_the_row(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    store = PlanStore()
    plan = _plan()
    store.add(plan)
    plan.status = PlanStatus.ACTIVE
    store.update(plan)
    assert PlanRepository().get("P1", conn=db_committed)["status"] == PlanStatus.ACTIVE


def test_update_of_an_unknown_plan_still_raises_keyerror(data_dir, monkeypatch,
                                                         db_committed):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    with pytest.raises(KeyError):
        PlanStore().update(_plan("MISSING"))


def test_the_plan_dict_round_trips_through_the_row(data_dir, monkeypatch,
                                                   db_committed):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    from swingbot.core.db.dual import diff_records
    from swingbot.core.planning.plan_engine import plan_to_dict
    plan = _plan()
    PlanStore().add(plan)
    stored = PlanRepository().get("P1", conn=db_committed)
    assert diff_records(plan_to_dict(plan), stored) == []
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/planning/test_plan_store_dual.py -q
```

Expected: `test_dual_stage_writes_both` fails.

- [ ] **Step 3: Add the write path**

In `swingbot/core/planning/plan_store.py`:

```python
    def _persist(self, plan_dict: dict | None = None) -> None:
        """Write through to whichever backends this stage uses."""
        from swingbot.core.db import stages
        if stages.writes_json("plans"):
            self._save()
        if not stages.writes_db("plans"):
            return
        from swingbot.core.db.repositories.plans import plans_repo
        repo = plans_repo()
        if plan_dict is not None:
            repo.upsert(plan_dict)
        else:
            for d in self._plans.values():
                repo.upsert(d)
```

In `add()` and `update()`, replace `self._save()` with
`self._persist(self._plans[plan.plan_id])`. Keep `update()`'s existing
`KeyError` guard exactly where it is — it fires before any write, at every
stage, and the test above pins that.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_store_dual.py
python scripts/dev/testrun.py file tests/planning/test_plan_store.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_store.py tests/planning/test_plan_store_dual.py
git commit -m "feat(v67): dual-write plans to postgres"
```

---

### Task P2-09: PlanStore reads from Postgres

**Files:**
- Modify: `swingbot/core/planning/plan_store.py`
- Test: `tests/planning/test_plan_store_db_reads.py`

**Interfaces:**
- Consumes: `plans_repo` (P2-07), `_persist` (P2-08).
- Produces on `PlanStore`: `_all(self) -> dict[str, dict]` — plan_id → record,
  the single read seam.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_store_db_reads.py`:

```python
"""At the db stage, plans.json is not consulted."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    return tmp_path


def _seed(plan_id="P1", status=PlanStatus.PENDING):
    PlanRepository().upsert(dict(
        plan_id=plan_id, ticker="AAPL", strategy="RSI", horizon_key="2w",
        status=status, created_at="2026-01-02T15:00:00+00:00",
        entry=100.0, stop_loss=95.0, take_profit=110.0, direction="bullish"))


def test_get_reads_a_row(db_stage):
    _seed()
    assert PlanStore().get("P1").plan_id == "P1"


def test_get_returns_none_for_a_missing_plan(db_stage):
    assert PlanStore().get("nope") is None


def test_open_plans_filters_by_status(db_stage):
    _seed("P1", PlanStatus.ACTIVE)
    _seed("P2", PlanStatus.CLOSED)
    assert [p.plan_id for p in PlanStore().open_plans()] == ["P1"]


def test_all_returns_every_plan(db_stage):
    _seed("P1")
    _seed("P2")
    assert {p.plan_id for p in PlanStore().all()} == {"P1", "P2"}


def test_no_plans_json_is_written(db_stage):
    from swingbot.core.planning.plan_engine import plan_from_dict
    PlanStore().add(plan_from_dict({
        "plan_id": "NEW", "ticker": "MSFT", "strategy": "RSI",
        "horizon_key": "2w", "status": PlanStatus.PENDING,
        "created_at": "2026-01-02T15:00:00+00:00", "entry": 1.0,
        "stop_loss": 0.5, "take_profit": 2.0, "direction": "bullish"}))
    assert not os.path.exists(os.path.join(db_stage, "plans.json"))


def test_a_long_lived_store_sees_a_plan_added_elsewhere(db_stage):
    """run_manager_tick()'s PlanStore lives for the process. This is the
    stale-snapshot bug reload() was written to narrow."""
    long_lived = PlanStore()
    assert long_lived.all() == []
    _seed("LATER")
    assert [p.plan_id for p in long_lived.all()] == ["LATER"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/planning/test_plan_store_db_reads.py -q
```

Expected: `test_get_reads_a_row` fails with `AttributeError: 'NoneType' object
has no attribute 'plan_id'`.

- [ ] **Step 3: Add the read seam and neutralise reload()**

```python
    def _all(self) -> dict[str, dict]:
        """plan_id -> record, from whichever backend this stage reads."""
        from swingbot.core.db import stages
        if not stages.reads_db("plans"):
            return self._plans
        from swingbot.core.db.repositories.plans import plans_repo
        return {p["plan_id"]: p for p in plans_repo().list_all()}
```

Route `get`, `open_plans` and `all` through `_all()`. `update()`'s membership
check becomes `if plan.plan_id not in self._all():`.

Guard `reload()` the same way P2-05 guards `TradeLog.reload()`, with the same
docstring addition — it exists only to narrow the whole-file clobber window, and
that window is gone at the db stage. Part 6 deletes it.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_store_db_reads.py
python scripts/dev/testrun.py file tests/planning/test_plan_store.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager.py
```

Expected: `0 failed` for all three. The third is the regression check on the
long-lived `_MANAGER` singleton this task changes the behaviour of.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_store.py tests/planning/test_plan_store_db_reads.py
git commit -m "feat(v67): read plans from postgres at the db stage"
```

---

### Task P2-10: The plans/trades cross-store invariant

`close_plan_trade` writes a trade row keyed on a plan's id, and the plan's own
status changes in the same tick. At the json stage those were two file writes
that could half-happen. This task proves they cannot at the db stage.

**Files:**
- Create: `tests/planning/test_plan_trade_atomicity.py`
- Modify: `swingbot/core/planning/plan_manager.py` (wrap the lifecycle write in
  one transaction)

**Interfaces:**
- Consumes: `get_engine` (P1-02), `trades_repo` (P2-01), `plans_repo` (P2-07).
- Produces: `swingbot/core/db/engine.py::transaction()` — a context manager
  yielding one connection, for a caller that needs several repository writes to
  land together.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_trade_atomicity.py`:

```python
"""A plan close and its trade close are one write, or neither."""
import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db,plans:db")


def _seed(db_committed):
    with db_committed.begin():
        PlanRepository().insert(dict(
            plan_id="P1", ticker="AAPL", strategy="RSI", horizon_key="2w",
            status="active", created_at="2026-01-02T15:00:00+00:00"),
            conn=db_committed)
        TradeRepository().insert(dict(
            trade_id="T1", ticker="AAPL", strategy="RSI", horizon="2w",
            direction="bullish", status="open",
            opened_at="2026-01-02T15:00:00+00:00", plan_id="P1"),
            conn=db_committed)


def test_both_writes_land_together(db_stage, db_committed):
    _seed(db_committed)
    with transaction() as conn:
        PlanRepository().patch("P1", {"status": "closed"}, conn=conn)
        TradeRepository().patch("T1", {"status": "win"}, conn=conn)
    assert PlanRepository().get("P1", conn=db_committed)["status"] == "closed"
    assert TradeRepository().get("T1", conn=db_committed)["status"] == "win"


def test_a_failure_rolls_back_both(db_stage, db_committed):
    _seed(db_committed)
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            PlanRepository().patch("P1", {"status": "closed"}, conn=conn)
            raise RuntimeError("the trade write blew up")
    # The half-write is what the file stores could not prevent.
    assert PlanRepository().get("P1", conn=db_committed)["status"] == "active"


def test_transaction_reuses_one_connection():
    with transaction() as a:
        with transaction(a) as b:
            assert b is a
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/planning/test_plan_trade_atomicity.py -q
```

Expected: `ImportError: cannot import name 'transaction'`.

- [ ] **Step 3: Add `transaction()`**

Append to `swingbot/core/db/engine.py`:

```python
@contextmanager
def transaction(conn: Engine | None = None):
    """One connection and one transaction for several repository calls.

    Pass the result as each repository method's `conn=` and they commit or roll
    back together. Passing an existing connection is a no-op pass-through, so a
    caller that is already inside a transaction joins it rather than opening a
    second one and deadlocking against itself.
    """
    if conn is not None:
        yield conn
        return
    with get_engine().begin() as owned:
        yield owned
```

with `from contextlib import contextmanager` added to the imports.

- [ ] **Step 4: Use it in the plan lifecycle**

In `swingbot/core/planning/plan_manager.py`, find the place where a plan's
status change and its trade's close are written in the same tick
(`grep -n "close_plan_trade\|store.update" swingbot/core/planning/plan_manager.py`).
Wrap the pair:

```python
        from swingbot.core.db import stages
        from swingbot.core.db.engine import transaction
        if stages.reads_db("plans") and stages.reads_db("trades"):
            with transaction() as conn:
                self._close_plan_and_trade(plan, leg, status, conn=conn)
        else:
            self._close_plan_and_trade(plan, leg, status)
```

The stage guard is not optional: at the json stage there is no connection to
open, and opening one would make a store that has not migrated depend on a
database being reachable.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_trade_atomicity.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager.py
python scripts/dev/testrun.py file tests/db/test_engine.py
```

Expected: `0 failed` for all three.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/engine.py swingbot/core/planning/plan_manager.py \
        tests/planning/test_plan_trade_atomicity.py
git commit -m "feat(v67): make a plan close and its trade close one transaction"
```

---

### Task P2-11: starred_plans repository, importer and dual write

The smallest store in the plan: a JSON array of plan ids, read and rewritten
whole on every star and unstar.

**Files:**
- Create: `swingbot/core/db/repositories/starred.py`
- Create: `scripts/db/import_starred.py`
- Modify: `swingbot/commands/views.py:30-46` (`starred_ids`, `star_plan`,
  `unstar_plan`)
- Modify: `scripts/db/parity_report.py`
- Test: `tests/commands/test_starred_plans_db.py`

**Interfaces:**
- Consumes: `Repository`, `starred_plans` table (P2-01), `stages`.
- Produces: `StarredRepository` with `ids() -> set[str]`, `star(plan_id)`,
  `unstar(plan_id)`; `starred_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_starred_plans_db.py`:

```python
"""Starring a plan, at each stage."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.starred import StarredRepository
from swingbot.commands import views


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(views, "_STARRED_PATH",
                        os.path.join(tmp_path, "starred_plans.json"))
    return tmp_path


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:dual")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().ids(conn=db_committed) == {"P1"}


def test_db_stage_reads_rows(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    views.star_plan("P1")
    views.star_plan("P2")
    assert views.starred_ids() == {"P1", "P2"}
    assert not os.path.exists(os.path.join(data_dir, "starred_plans.json"))


def test_unstar_removes_the_row(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    views.star_plan("P1")
    views.unstar_plan("P1")
    assert views.starred_ids() == set()


def test_starring_twice_is_idempotent(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    views.star_plan("P1")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().count(conn=db_committed) == 1


def test_unstarring_something_unstarred_is_not_an_error(data_dir, monkeypatch,
                                                        db_committed):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    views.unstar_plan("never-starred")
    assert views.starred_ids() == set()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/commands/test_starred_plans_db.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.starred'`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/starred.py`:

```python
"""Starred plan ids. A set, not a record store."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import starred_plans


class StarredRepository(Repository):
    def __init__(self):
        super().__init__(starred_plans, key="plan_id")

    def ids(self, *, conn=None) -> set[str]:
        return {row["plan_id"] for row in self.list_all(conn=conn)}

    def star(self, plan_id: str, *, conn=None) -> None:
        # upsert, so starring an already-starred plan is a no-op rather than a
        # unique-violation the caller would have to catch.
        self.upsert({"plan_id": plan_id}, conn=conn)

    def unstar(self, plan_id: str, *, conn=None) -> None:
        self.delete(plan_id, conn=conn)


_repo: StarredRepository | None = None


def starred_repo() -> StarredRepository:
    global _repo
    if _repo is None:
        _repo = StarredRepository()
    return _repo
```

- [ ] **Step 4: Wire the three functions**

In `swingbot/commands/views.py`, replace the three functions at `:30-46`:

```python
def starred_ids() -> set:
    from swingbot.core.db import stages
    if stages.reads_db("starred_plans"):
        from swingbot.core.db.repositories.starred import starred_repo
        return starred_repo().ids()
    return set(read_json(_STARRED_PATH, []))


def star_plan(plan_id: str) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("starred_plans"):
        ids = set(read_json(_STARRED_PATH, []))
        ids.add(plan_id)
        atomic_write_json(_STARRED_PATH, sorted(ids))
    if stages.writes_db("starred_plans"):
        from swingbot.core.db.repositories.starred import starred_repo
        starred_repo().star(plan_id)


def unstar_plan(plan_id: str) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("starred_plans"):
        ids = set(read_json(_STARRED_PATH, []))
        ids.discard(plan_id)
        atomic_write_json(_STARRED_PATH, sorted(ids))
    if stages.writes_db("starred_plans"):
        from swingbot.core.db.repositories.starred import starred_repo
        starred_repo().unstar(plan_id)
```

Note the file branch reads through `read_json` directly rather than calling
`starred_ids()` — at the db stage `starred_ids()` no longer reads the file, so
reusing it would make the dual stage write an empty file over a real one.

- [ ] **Step 5: Importer and parity registration**

Create `scripts/db/import_starred.py` whose `load_source` maps the flat id list
into records: `[{"plan_id": pid} for pid in read_json(path, [])]`, with
`key="plan_id"`, `name="starred_plans"`.

Register it in `scripts/db/parity_report.py`. Because the source file is a flat
list of strings rather than a list of dicts, `parity()` needs a per-store
loader; add an optional `loader` field to `StoreSpec` defaulting to `None`, and
use it when present:

```python
@dataclass(frozen=True)
class StoreSpec:
    filename: str
    key: str
    repo_factory: Callable[[], object]
    loader: Callable[[object], list[dict]] | None = None
```

and in `parity()`:

```python
    raw = read_json(os.path.join(config.DATA_DIR, spec.filename), [])
    rows = spec.loader(raw) if spec.loader else raw
```

- [ ] **Step 6: Run the tests**

```bash
python scripts/dev/testrun.py file tests/commands/test_starred_plans_db.py
python scripts/dev/testrun.py file tests/scripts/test_parity_report.py
```

Expected: `0 failed` for both.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/repositories/starred.py swingbot/commands/views.py \
        scripts/db/import_starred.py scripts/db/parity_report.py \
        tests/commands/test_starred_plans_db.py
git commit -m "feat(v67): migrate starred plans to postgres"
```

---

### Task P2-12: The starred/plans referential check

`starred_plans` holds ids that must exist in `plans`. As files there was nothing
to enforce that and nothing to notice when a starred plan was deleted.

**Files:**
- Create: `swingbot/core/db/migrations/versions/p2_006_starred_fk.py`
- Test: `tests/db/test_starred_referential.py`

**Interfaces:**
- Consumes: `plans`, `starred_plans` (P2-01).
- Produces: revision `p2_006` — a foreign key from `starred_plans.plan_id` to
  `plans.plan_id` with `ON DELETE CASCADE`.

**Why a real FK and not a check in Python:** the spec's promotion criteria name
foreign-key participation as one of the three reasons to promote a column, and
`plan_id` is already promoted on both tables. The cascade is the behaviour the
file version silently lacked — deleting a plan left its star behind forever, and
`starred_ids()` returned an id nothing could resolve.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_starred_referential.py`:

```python
"""A star cannot outlive its plan."""
import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.starred import StarredRepository


def _plan(plan_id="P1"):
    return dict(plan_id=plan_id, ticker="AAPL", strategy="RSI",
                horizon_key="2w", status="pending",
                created_at="2026-01-02T15:00:00+00:00")


def test_starring_an_existing_plan_works(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    StarredRepository().star("P1", conn=db_conn)
    assert StarredRepository().ids(conn=db_conn) == {"P1"}


def test_starring_a_plan_that_does_not_exist_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        StarredRepository().star("GHOST", conn=db_conn)


def test_deleting_a_plan_removes_its_star(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    StarredRepository().star("P1", conn=db_conn)
    PlanRepository().delete("P1", conn=db_conn)
    assert StarredRepository().ids(conn=db_conn) == set()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_starred_referential.py -q
```

Expected: `test_starring_a_plan_that_does_not_exist_is_rejected` fails — no
constraint yet, so the insert succeeds.

- [ ] **Step 3: Add the constraint to `schema.py` and a migration**

In `schema.py`, change `starred_plans`' `plan_id` column to:

```python
        sa.Column("plan_id", sa.Text,
                  sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
```

Create `swingbot/core/db/migrations/versions/p2_006_starred_fk.py`:

```python
"""starred_plans.plan_id references plans.plan_id

Revision ID: p2_006
Revises: p2_005
"""
from alembic import op

revision = "p2_006"
down_revision = "p2_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Any star whose plan no longer exists is exactly the orphan this
    # constraint exists to prevent, and it cannot be repaired -- the plan it
    # pointed at is gone. Drop them, then constrain.
    op.execute("DELETE FROM starred_plans s "
               "WHERE NOT EXISTS (SELECT 1 FROM plans p WHERE p.plan_id = s.plan_id)")
    op.create_foreign_key("starred_plans_plan_id_fkey", "starred_plans", "plans",
                          ["plan_id"], ["plan_id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("starred_plans_plan_id_fkey", "starred_plans",
                       type_="foreignkey")
```

The `DELETE` before the constraint is load-bearing on the production import: the
VM's `starred_plans.json` predates any referential rule, so it may well hold ids
whose plans were cleared. Without the delete the migration fails on real data.

- [ ] **Step 4: Order the importers**

Add a note at the top of `scripts/db/import_starred.py`:

```python
# Run AFTER import_plans.py. starred_plans.plan_id is a foreign key into
# plans.plan_id (revision p2_006), so importing stars first fails every row.
```

- [ ] **Step 5: Migrate and run the tests**

```bash
alembic upgrade head
python scripts/dev/testrun.py file tests/db/test_starred_referential.py
python scripts/dev/testrun.py file tests/commands/test_starred_plans_db.py
```

Expected: `0 failed`. The second is the check that P2-11's tests still pass —
they seed stars without plans, so **they will need plan rows added**. Fix them
by seeding a plan in each test's setup; do not weaken the constraint.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/schema.py \
        swingbot/core/db/migrations/versions/p2_006_starred_fk.py \
        scripts/db/import_starred.py tests/db/test_starred_referential.py \
        tests/commands/test_starred_plans_db.py
git commit -m "feat(v67): constrain starred plans to real plans"
```

---

