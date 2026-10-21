# v173 Execution fidelity, part 3c: the verdict store, the one evaluator and the daily loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-26:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §4 (One evaluation: the daily job trigger, the `preregistration_verdicts` row written once in the same transaction as the condition check, frozen) and `## Plan panel review` (Postgres verdict store, the bot's daily job as the only trigger)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints.

Tasks: V173-24, V173-25, V173-26, V173-27 (all new on 2026-10-19), in execution order. V173-24 runs after V173-5 (part 1: `revision = "v173_001"`, its `down_revision`); it touches only `schema.py`, the new revision and its test, so it may run beside the V173-7..V173-10 chain. V173-25 runs after V173-24. V173-26 runs after V173-10 (part 3b: `build_report`, `evaluate_verdict`, `verdict_record`, `counted`, `engine_flags`) and V173-25. V173-27 runs after V173-26. Part 4 (V173-11, V173-12) imports `override_io` from V173-26.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**Database use** (Global Constraints, Tests and the database): V173-24 (`db_engine_empty`), V173-25 (`db_conn`) and V173-27 (the root autouse `_store_database`, for `scheduled_jobs`) use the disposable test database only. Before the first test run of those tasks: run `/replicate-prod-db` (CLAUDE.md) and `docker compose --profile test up -d db-test`. V173-26's tests never touch a database (fake repo, fake engine, injected inputs).

**Traps this part handles** (index § Handoff, Partner decisions and traps):
- The `scheduled_jobs` marker is written **before** the work (`loops.py:981-982` in `gate_counterfactual_resolve`), so a raise after it is not retried that day. The marker only throttles the per-minute tick; the `preregistration_verdicts` primary key is the idempotency authority, and `run_daily_check` returns `"already recorded"` before any replay once a row exists.
- The transaction does not cover the plan read: `PlanStore().all()` opens its own connection. The one `begin()` block covers the existence check and the insert. A concurrent second insert writes nothing (`on_conflict_do_nothing`) and `run_daily_check` reports `"already recorded"`.

# Phase 3: The verdict store and the one evaluator (V173-24..V173-27)

### Task V173-24: `preregistration_verdicts` table: `schema.py` and Alembic `v173_002`

**Model:** opus — a schema migration run on production

**Files:**
- Modify: `swingbot/core/db/schema.py` (the table after `equity_samples`, :278-293; its `PROMOTION_REASONS` entry after the `"equity_samples"` entry, which ends at :411)
- Create: `swingbot/core/db/migrations/versions/v173_002_preregistration_verdicts.py`
- Create: `tests/db/test_v173_002_preregistration_verdicts.py`

**Interfaces:**
- Consumes: V173-5 (part 1): `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py` with `revision = "v173_001"`. On a database holding none of the pinned ids both its `upgrade()` and its `downgrade()` are a logged no-op (`apply(...)` changes nothing), so `upgrade(cfg, "head")` and the downgrades in the tests below pass through it.
- Produces (V173-25 imports it):
  - `schema.preregistration_verdicts` (`sa.Table`), registered with promoted `("ledger_id", "verdict", "recorded_on")`.
  - Columns: `ledger_id Text PRIMARY KEY`, `verdict Text NOT NULL`, `recorded_on Date NOT NULL`, `doc JSONB NOT NULL DEFAULT '{}'`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. No other column, no index, no unique constraint beyond the primary key, no `TABLE_CHANNELS` entry (`swingbot/core/db/events.py:8`).
  - Revision `revision = "v173_002"`, `down_revision = "v173_001"` (always; a later re-chain in V173-17 touches only `v173_001`).

**Why a table and not the jsonl file** (index § Handoff, Postgres verdict store): the container's `docs/` is the image copy with no mount, so a jsonl row written on the VM vanishes at the next deploy and invites a second evaluation. This row is the authority; the jsonl file is the record, filled by a mirror commit (V173-11's standing procedure). Every field beyond the three promoted ones lives in `doc` (`docs/claude/schema-evolution.md` § The four operations: a field first lands in `doc`; promoting one later is a DDL revision with a backfill).

- [ ] **Step 1: Confirm the chain this revision sits on**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "^revision\|^down_revision" -- swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n 'down_revision = "v173_001"' -- swingbot/core/db/migrations/versions/
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "preregistration_verdicts" -- swingbot/ tests/
```

Expected: the first prints `revision = "v173_001"` and its `down_revision` line; the second and third print nothing. If `v173_001` is missing, V173-5 is not on the branch: stop and report, never write `v173_002` on another head (two heads fail `tests/db/test_migrations.py::test_exactly_one_head`).

- [ ] **Step 2: Write the failing test** `tests/db/test_v173_002_preregistration_verdicts.py`

It mirrors `tests/db/test_v172_tables.py`: the first four tests need no database; the last uses `db_engine_empty` (the session-scoped empty database the migration tests share) and leaves it at head.

```python
"""v173: preregistration_verdicts, revision v173_002 -- the frozen verdict of a
pre-registration, written once by the bot's daily check (V173-26), keyed by
ledger_id so a second insert is impossible."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
TABLE = "preregistration_verdicts"
PROMOTED = ("ledger_id", "verdict", "recorded_on")


def test_the_table_is_registered_with_its_promoted_columns_and_reasons():
    table = schema.METADATA.tables[TABLE]
    assert schema.promoted_for(TABLE) == PROMOTED
    assert set(schema.PROMOTION_REASONS[TABLE]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert set(table.c.keys()) == {*PROMOTED, "doc", "updated_at"}
    for column in PROMOTED:
        assert table.c[column].nullable is False, column


def test_ledger_id_is_the_text_primary_key_and_recorded_on_a_date():
    table = schema.preregistration_verdicts
    assert [column.name for column in table.primary_key.columns] == ["ledger_id"]
    assert isinstance(table.c.ledger_id.type, sa.Text)
    assert isinstance(table.c.verdict.type, sa.Text)
    assert isinstance(table.c.recorded_on.type, sa.Date)
    assert not isinstance(table.c.recorded_on.type, sa.DateTime)
    assert isinstance(table.c.doc.type, JSONB)
    assert list(table.indexes) == []
    assert not [c for c in table.constraints if isinstance(c, sa.UniqueConstraint)]


def test_the_table_raises_no_sse_event():
    assert TABLE not in events.TABLE_CHANNELS


def test_v173_002_sits_on_v173_001_and_is_the_single_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v173_002")
    assert revision.down_revision == "v173_001"
    assert scripts.get_heads() == ["v173_002"]


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v173_002_downgrade_drops_only_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert TABLE in _tables(connection)
        downgrade(cfg, "v173_001")
        remaining = _tables(connection)
        assert TABLE not in remaining
        assert {"plans", "trades", "equity_samples", "scheduled_jobs"} <= remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert TABLE in _tables(connection)
```

`test_v173_002_sits_on_v173_001_and_is_the_single_head` pins the head to `v173_002`. If V173-17 finds a newer revision on `main` and re-chains `v173_001` above it, `v173_002` stays the head and the test stays true; only a revision written *after* `v173_002` changes it, and that is a later plan's edit.

- [ ] **Step 3: Run it to verify it fails**

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/docker-compose.yml --profile test up -d db-test
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_002_preregistration_verdicts.py
```

Expected: FAIL, `KeyError: 'preregistration_verdicts'` from `schema.METADATA.tables`, `AttributeError` on `schema.preregistration_verdicts`, and an Alembic error for the unknown revision `v173_002`. A `skipped` result naming `db-test` means the container is not up: start it, never mark the task done on skips.

- [ ] **Step 4: Declare the table in `swingbot/core/db/schema.py`**

After the `equity_samples = register(...)` block:

```python
# v173: the frozen verdict of a pre-registration, written once by the bot's daily
# check (analytics/override_io.run_daily_check). The primary key is the idempotency
# authority: a second insert on the same ledger_id is impossible. Everything but the
# key, the verdict and its date lives in doc (n, weeks, CI, engine flags, the counted
# rows). No SSE event (not in TABLE_CHANNELS); never updated or deleted by code.
preregistration_verdicts = register(sa.Table("preregistration_verdicts", METADATA,
    sa.Column("ledger_id", sa.Text, primary_key=True),
    sa.Column("verdict", sa.Text, nullable=False),
    sa.Column("recorded_on", sa.Date, nullable=False),
    *standard_columns()),
    ("ledger_id", "verdict", "recorded_on"))
```

In `PROMOTION_REASONS`, after the `"equity_samples": {...},` entry (reasons verbatim from the index's Global Constraints):

```python
    "preregistration_verdicts": {
        "ledger_id": "primary key: one row per pre-registration, so a second insert is impossible",
        "verdict": "NOT NULL frozen outcome",
        "recorded_on": "NOT NULL date the verdict was recorded",
    },
```

`tests/db/test_schema_contract.py::test_every_promoted_column_has_exactly_one_one_line_reason` requires one single-line reason per promoted column; each of these is one line.

- [ ] **Step 5: Write the revision** `swingbot/core/db/migrations/versions/v173_002_preregistration_verdicts.py`

Types, nullability, `server_default`s and names must equal `schema.py` exactly: `tests/db/test_migrations.py::test_migrations_produce_exactly_the_declared_schema` compares the migrated database with `METADATA`. The primary key carries no explicit name in either place (Postgres names it `preregistration_verdicts_pkey` in both).

```python
"""preregistration_verdicts: the frozen verdict of a pre-registration (v173).

Written once by the bot's daily check (analytics/override_io.run_daily_check);
the primary key ledger_id makes a second insert impossible. Additive: rollback
is this revision's downgrade (drop the table); leaving the table in place after
a code rollback is also safe. A verdict row is the frozen record: print it with
`execution_fidelity_report.py --production --mirror-row` before any downgrade.

Revision ID: v173_002
Revises: v173_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v173_002"
down_revision = "v173_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preregistration_verdicts",
        sa.Column("ledger_id", sa.Text, primary_key=True),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("recorded_on", sa.Date, nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("preregistration_verdicts")
```

- [ ] **Step 6: Run the new test and the migration and contract tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_002_preregistration_verdicts.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_migrations.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_schema_contract.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v172_tables.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_manual_bulk_retag.py
```

Expected: all PASS, `0 failed`, `0 xfailed`, no skips. `test_migrations_produce_exactly_the_declared_schema` passing is the proof that the revision equals `schema.py`; if it lists a diff, fix the revision or the declaration until both agree, never add an ignore. `test_v172_tables.py` downgrades past `v173_002` and `v173_001` and back up, so it passing shows both new downgrades run on an empty database.

- [ ] **Step 7: Head check through Alembic itself**

```bash
python -m alembic -c E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/alembic.ini heads
```

Expected: exactly one line, `v173_002 (head)`.

- [ ] **Step 8: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v173_002_preregistration_verdicts.py tests/db/test_v173_002_preregistration_verdicts.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): preregistration_verdicts table, revision v173_002 on v173_001"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-25: Verdict repository: insert once, read the record

**Model:** sonnet — a store module following `equity_samples.py`

**Files:**
- Create: `swingbot/core/db/repositories/preregistration_verdicts.py`
- Create: `tests/db/test_preregistration_verdicts_repository.py`

**Interfaces:**
- Consumes: V173-24: `swingbot.core.db.schema.preregistration_verdicts` (promoted `ledger_id`, `verdict`, `recorded_on`; primary key `ledger_id`). Existing: `swingbot.core.db.repositories.base.Repository` (`__init__(table, key)`, `_tx(conn)`, `_values(record)`, `get(key_value, *, conn=None)`), `sqlalchemy.dialects.postgresql.insert as pg_insert`.
- Produces (V173-26 and, through `override_io`, V173-11 and V173-12 rely on these):
  - `class PreregistrationVerdictRepository(Repository)`, `key="ledger_id"`.
  - `insert_once(record: dict, *, conn=None) -> bool`: one `pg_insert(...).on_conflict_do_nothing(index_elements=["ledger_id"]).returning(table.c.ledger_id)`; `True` when the row was written, `False` when a row with that `ledger_id` already existed (nothing written, nothing updated). `record["recorded_on"]` may be a `date` or an ISO `YYYY-MM-DD` string; anything else, or a missing or empty `ledger_id`/`verdict`, raises `ValueError` before any SQL.
  - `recorded(ledger_id: str, *, conn=None) -> dict | None`: the stored record as written (`doc` merged back with the promoted columns), `recorded_on` as ISO text; `None` when no row exists.
  - `upsert(...)` and `insert(...)` (inherited) are overridden to raise `TypeError`: no code updates a verdict, and the only insert is `insert_once`.
  - `verdict_repo() -> PreregistrationVerdictRepository`: lazy module singleton (the `scheduled_repo()` idiom, `repositories/scheduled.py:22-26`).

The record's shape (the index's Global Constraints, Stored verdict record) is built only by `override_verdict.verdict_record` (V173-10); this module stores whatever dict it is given and adds no field.

- [ ] **Step 1: Write the failing test** `tests/db/test_preregistration_verdicts_repository.py`

Every test except the last two takes `db_conn` (a rolled-back transaction on the disposable test database, `tests/db/conftest.py:138`) and passes `conn=db_conn`, as `tests/db/test_equity_samples_repository.py` does.

```python
"""v173: PreregistrationVerdictRepository -- a verdict is written once, keyed by
ledger_id; a second insert writes nothing and never updates; the record reads
back exactly, with recorded_on as ISO text."""
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from swingbot.core.db.repositories.preregistration_verdicts import (
    PreregistrationVerdictRepository, verdict_repo)

LEDGER_ID = "v173-override-fidelity"


@pytest.fixture
def repo():
    return PreregistrationVerdictRepository()


def _record(verdict="COST", *, recorded_on="2026-12-04", mean=-0.212):
    return {"ledger_id": LEDGER_ID, "verdict": verdict, "recorded_on": recorded_on,
            "n": 31, "weeks": 12, "mean_delta_r": mean, "mean_delta_r_gross": -0.187,
            "ci": [-0.401, -0.033], "sum_delta_r": -6.572, "sum_delta_usd": -1314.4,
            "bar_close_n": 2, "excluded_share": 0.114,
            "engine_flags": {"stall_exit_enabled": True, "runner_structure_exit": "off"},
            "rows": [{"plan_id": "p1", "delta_r": -0.5, "close_date": "2026-09-01"},
                     {"plan_id": "p2", "delta_r": 0.25, "close_date": "2026-09-09"}]}


def test_the_first_insert_writes_the_row(repo, db_conn):
    assert repo.insert_once(_record(), conn=db_conn) is True
    row = db_conn.execute(sa.text(
        "SELECT ledger_id, verdict, recorded_on, doc->>'n' AS n FROM preregistration_verdicts"
    )).one()
    assert (row.ledger_id, row.verdict, row.recorded_on, row.n) == (
        LEDGER_ID, "COST", date(2026, 12, 4), "31")


def test_a_second_insert_on_the_same_ledger_id_writes_nothing_and_keeps_the_first(repo, db_conn):
    assert repo.insert_once(_record(), conn=db_conn) is True
    later = _record("SAVED", recorded_on="2026-12-11", mean=0.4)
    assert repo.insert_once(later, conn=db_conn) is False
    assert repo.recorded(LEDGER_ID, conn=db_conn) == _record()
    count = db_conn.execute(sa.text("SELECT count(*) FROM preregistration_verdicts")).scalar_one()
    assert count == 1


def test_recorded_round_trips_the_record_with_recorded_on_as_iso_text(repo, db_conn):
    repo.insert_once(_record(recorded_on=date(2026, 12, 4)), conn=db_conn)
    stored = repo.recorded(LEDGER_ID, conn=db_conn)
    assert stored == _record()                     # recorded_on back as "2026-12-04"
    assert isinstance(stored["recorded_on"], str)
    assert stored["ci"] == [-0.401, -0.033] and stored["rows"][1]["delta_r"] == 0.25


def test_recorded_is_none_when_no_row_exists(repo, db_conn):
    assert repo.recorded(LEDGER_ID, conn=db_conn) is None
    assert repo.recorded("v999-other", conn=db_conn) is None


def test_a_plain_second_insert_fails_on_the_primary_key(repo, db_conn):
    repo.insert_once(_record(), conn=db_conn)
    savepoint = db_conn.begin_nested()
    with pytest.raises(IntegrityError):
        db_conn.execute(sa.text(
            "INSERT INTO preregistration_verdicts (ledger_id, verdict, recorded_on) "
            "VALUES (:id, 'SAVED', DATE '2026-12-11')"), {"id": LEDGER_ID})
    savepoint.rollback()
    assert repo.recorded(LEDGER_ID, conn=db_conn)["verdict"] == "COST"


@pytest.mark.parametrize("bad", [
    {"ledger_id": ""}, {"ledger_id": None}, {"verdict": ""},
    {"recorded_on": "04.12.2026"}, {"recorded_on": None},
])
def test_a_malformed_record_is_refused_before_any_sql(repo, bad):
    with pytest.raises(ValueError):
        repo.insert_once({**_record(), **bad}, conn=object())   # a fake conn: never reached


def test_no_code_path_updates_or_plain_inserts_a_verdict(repo):
    with pytest.raises(TypeError):
        repo.upsert(_record())
    with pytest.raises(TypeError):
        repo.insert(_record())


def test_verdict_repo_is_one_shared_instance():
    assert verdict_repo() is verdict_repo()
    assert isinstance(verdict_repo(), PreregistrationVerdictRepository)
```

`test_a_malformed_record_is_refused_before_any_sql` passes `conn=object()`: if validation ran after `_tx(conn)`, the fake connection's missing `execute` would raise `AttributeError`, not `ValueError`, and the test would fail.

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/docker-compose.yml --profile test up -d db-test
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_preregistration_verdicts_repository.py
```

Expected: FAIL at collection, `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.preregistration_verdicts'`.

- [ ] **Step 3: Write `swingbot/core/db/repositories/preregistration_verdicts.py`**

```python
"""v173: frozen pre-registration verdicts (`preregistration_verdicts`).

Writer: analytics/override_io.run_daily_check (`insert_once`, the only write,
inside the transaction that checked no row exists). Readers: override_io
(`recorded`), and through it the report script and the admin API. A verdict is
never updated or deleted: `upsert`/`insert` are refused, and a second insert on
the same ledger_id writes nothing (the primary key is the idempotency authority).
The table raises no SSE event.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import preregistration_verdicts

_WRITE_ONCE = "a verdict is written once: use insert_once"
```

Then:
- `_recorded_on(value) -> dt.date`: a `dt.date` that is not a `dt.datetime` is returned as is; a `str` goes through `dt.date.fromisoformat` and must also equal its own `isoformat()` (so `"2026-12-4"` and `"04.12.2026"` fail); anything else raises `ValueError("recorded_on must be a date or YYYY-MM-DD")`.
- `_prepared(record: dict) -> dict`: `ValueError` when `record.get("ledger_id")` or `record.get("verdict")` is falsy; returns `{**record, "recorded_on": _recorded_on(record.get("recorded_on"))}`.
- The class:

```python
class PreregistrationVerdictRepository(Repository):
    def __init__(self):
        super().__init__(preregistration_verdicts, key="ledger_id")

    def insert_once(self, record: dict, *, conn=None) -> bool:
        """Write `record` unless its ledger_id already has a row; True when written."""
        statement = (pg_insert(self.table).values(**self._values(_prepared(record)))
                     .on_conflict_do_nothing(index_elements=["ledger_id"])
                     .returning(self.table.c.ledger_id))
        with self._tx(conn) as connection:
            inserted = connection.execute(statement).first()
        return inserted is not None

    def recorded(self, ledger_id: str, *, conn=None) -> dict | None:
        """The stored record, recorded_on as ISO text; None when absent."""
        record = self.get(ledger_id, conn=conn)
        if record is None:
            return None
        return {**record, "recorded_on": record["recorded_on"].isoformat()}

    def upsert(self, record: dict, *, conn=None) -> dict:
        raise TypeError(_WRITE_ONCE)

    def insert(self, record: dict, *, conn=None) -> dict:
        raise TypeError(_WRITE_ONCE)
```

and the `_repo` / `verdict_repo()` singleton exactly as `repositories/scheduled.py:22-26`. `_prepared` is called while building `statement`, before `_tx(conn)` is entered, which is what the malformed-record test pins.

- [ ] **Step 4: Run the test and the neighbouring store tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_preregistration_verdicts_repository.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_002_preregistration_verdicts.py
```

Expected: both PASS, `0 failed`, `0 xfailed`, no skips.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/repositories/preregistration_verdicts.py
```

Expected: no output (every function below C).

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/db/repositories/preregistration_verdicts.py tests/db/test_preregistration_verdicts_repository.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): verdict repository, written once by ledger_id and never updated"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-26: `override_io`: inputs, stored verdict and the one evaluation

**Model:** opus — writes the frozen pre-registration exactly once

**Files:**
- Create: `swingbot/core/analytics/override_io.py`
- Create: `tests/analytics/test_override_io.py`

**Interfaces:**
- Consumes:
  - V173-7 (`swingbot.core.analytics.override_fidelity`, imported as `of`): `LEDGER_ID = "v173-override-fidelity"`, `latest_completed_session(now: datetime) -> date`, `OverrideRow` (20 fields, `to_dict()` writes `close_date` as ISO text), `STATUSES`.
  - V173-10 (`swingbot.core.analytics.override_verdict`, imported as `ov`): `build_report(plans, trades_by_plan, bars_fn, asof, recorded: dict | None, currency_symbol) -> dict` (keys `rows, summary, verdict, engine_flags, asof, currency_symbol`; `rows` in `to_dict()` form; `verdict["evaluable"]` live), `counted(rows) -> list`, `evaluate_verdict(rows) -> dict` (`ValueError` unless evaluable), `verdict_record(verdict: dict, rows: list, engine_flags: dict, *, recorded_on: date) -> dict`, `RESULTS_RECORD`, `COST`, `SAVED`, `INCONCLUSIVE`.
  - V173-25: `verdict_repo()`, `PreregistrationVerdictRepository.recorded(ledger_id, *, conn=None)`, `.insert_once(record, *, conn=None) -> bool`.
  - Existing: `swingbot.core.db.engine.get_engine()`; `swingbot.core.analytics.runner_path.cached_daily_bars(ticker)` (`runner_path.py:191`, disk only); `PlanStore().all()` (`plan_store.py:65`); `TradeLog().get_trades(status=None, limit=None, ledger=None)` (`performance.py:1204`); `config.CURRENCY_SYMBOL`.
- Produces (V173-27 calls `run_daily_check`; V173-11 imports `load_inputs` and `stored_verdict`; V173-12's seams `_override_inputs`/`_override_verdict` delegate to them):
  - `load_inputs() -> tuple[list, dict[str, dict]]`: every plan from `PlanStore().all()`; every trade from `TradeLog().get_trades(status=None, limit=None, ledger=None)` keyed by `plan_id` (first record wins; trades without a `plan_id` are skipped).
  - `stored_verdict(repo=None) -> dict | None`: `(repo or verdict_repo()).recorded(of.LEDGER_ID)`.
  - `run_daily_check(now: datetime, *, inputs_fn=None, bars_fn=None, repo=None, engine=None) -> str`, returning one of `RESULT_RECORDED = "recorded"`, `RESULT_ALREADY = "already recorded"`, `RESULT_WAITING = "waiting"`.
  - `RECORDED_LOG`: the `%`-format WARNING text logged once when a verdict is written, naming the standing mirror procedure.

**Why this shape** (index Global Constraints, The one evaluator, and § Handoff traps): the bot's daily job is the only trigger, so nobody picks the moment after seeing the sums; `run_daily_check` is the only caller of `evaluate_verdict` and `insert_once` in the codebase. The existence check and the insert share one `begin()` transaction; the plan read inside it opens its own connection (`PlanStore().all()`), which is fine because a concurrent second insert writes nothing (`on_conflict_do_nothing`) and is reported `"already recorded"`. A row that exists returns `"already recorded"` before any input is read, so a recorded verdict is never recomputed.

- [ ] **Step 1: Write the failing test** `tests/analytics/test_override_io.py`

No database: a fake repo and a fake engine stand in, and the inputs are injected. `build_report` is replaced by a fake that returns rows the test builds through `OverrideRow(...).to_dict()`; `evaluate_verdict`, `counted` and `verdict_record` stay real, so the stored record's shape is the one V173-10 defines.

```python
"""v173: override_io -- the one evaluation (fires only when the floors hold,
writes once, never recomputes), the stored-verdict read and the inputs."""
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov

BERLIN = ZoneInfo("Europe/Berlin")
FRIDAY_SLOT = datetime(2026, 12, 4, 23, 50, tzinfo=BERLIN)     # after the 16:00 ET close
FRIDAY = date(2026, 12, 4)
RECORD_KEYS = {"ledger_id", "verdict", "recorded_on", "n", "weeks", "mean_delta_r",
               "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n",
               "excluded_share", "engine_flags", "rows"}
FLAGS = {"stall_exit_enabled": True, "runner_structure_exit": "off"}


class FakeEngine:
    def __init__(self):
        self.conns = []

    @contextmanager
    def begin(self):
        conn = object()
        self.conns.append(conn)
        yield conn


class FakeRepo:
    def __init__(self, stored=None, accept=True):
        self.stored, self.accept = stored, accept
        self.inserted, self.conns = [], []

    def recorded(self, ledger_id, *, conn=None):
        assert ledger_id == of.LEDGER_ID
        self.conns.append(conn)
        return self.stored

    def insert_once(self, record, *, conn=None):
        self.conns.append(conn)
        self.inserted.append(record)
        return self.accept


def _row(i: int, *, delta_r: float, price_source: str = "quote") -> dict:
    close = date(2026, 9, 1) + timedelta(days=7 * (i % 12) + i // 12)
    return of.OverrideRow(
        plan_id=f"p{i}", ticker="AAPL", horizon="swing", direction="bullish",
        state_at_close="ACTIVE", close_date=close, bulk=False, approx=False,
        price_source=price_source, status="resolved", actual_r=0.4 + delta_r, engine_r=0.4,
        delta_r=delta_r, delta_r_gross=delta_r + 0.02, actual_usd=None, engine_usd=None,
        delta_usd=round(delta_r * 200, 2), engine_exit_reason="stop", outcome="hurt",
    ).to_dict()


def _costly_rows(n: int = 31) -> list[dict]:
    """n counted rows over 12 ISO weeks, every delta clearly negative: COST."""
    return [_row(i, delta_r=-0.2 - 0.01 * (i % 5),
                 price_source="bar_close" if i < 2 else "quote") for i in range(n)]


@pytest.fixture
def report(monkeypatch):
    """Replace build_report; record its arguments; evaluable unless told otherwise."""
    seen = {}

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        seen.update(plans=plans, trades=trades, bars_fn=bars_fn, asof=asof,
                    recorded=recorded, currency_symbol=currency_symbol)
        return {"rows": seen.get("rows", _costly_rows()), "summary": {},
                "verdict": {"evaluable": seen.get("evaluable", True)},
                "engine_flags": FLAGS, "asof": asof.isoformat(),
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    return seen


def _inputs():
    return (["plan-a"], {"a": {"shares": 5}})


def test_records_once_with_the_exact_record_shape_and_recorded_on_asof(report, caplog):
    repo, engine = FakeRepo(), FakeEngine()
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, bars_fn=lambda t: None,
                                    repo=repo, engine=engine)
    assert result == oio.RESULT_RECORDED == "recorded"
    (record,) = repo.inserted
    assert set(record) == RECORD_KEYS
    assert (record["ledger_id"], record["verdict"]) == (of.LEDGER_ID, ov.COST)
    assert record["recorded_on"] == FRIDAY.isoformat()
    assert (record["n"], record["weeks"], record["bar_close_n"]) == (31, 12, 2)
    assert record["engine_flags"] == FLAGS
    assert record["rows"] == _costly_rows()
    assert report["asof"] == FRIDAY and report["recorded"] is None
    assert report["currency_symbol"] == config.CURRENCY_SYMBOL
    assert report["plans"] == ["plan-a"]
    (conn,) = engine.conns                                # one transaction ...
    assert repo.conns == [conn, conn]                     # ... for the check and the insert
    (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "--mirror-row" in warning.getMessage()
    assert ov.RESULTS_RECORD in warning.getMessage()


def test_asof_is_the_latest_completed_session_not_the_wall_date(report):
    before_close = datetime(2026, 12, 4, 21, 0, tzinfo=BERLIN)   # 15:00 ET Friday
    repo = FakeRepo()
    oio.run_daily_check(before_close, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert report["asof"] == date(2026, 12, 3)
    assert repo.inserted[0]["recorded_on"] == "2026-12-03"


def test_waiting_when_the_floors_do_not_hold_and_nothing_is_inserted(report, caplog):
    report["evaluable"] = False
    report["rows"] = _costly_rows(29)
    repo = FakeRepo()
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert result == oio.RESULT_WAITING == "waiting"
    assert repo.inserted == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_waiting_on_an_empty_book_with_the_real_report(monkeypatch):
    repo = FakeRepo()
    result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=lambda: ([], {}),
                                bars_fn=lambda t: pytest.fail("no plan, no bars read"),
                                repo=repo, engine=FakeEngine())
    assert result == "waiting" and repo.inserted == []


def test_a_recorded_verdict_returns_before_any_input_is_read(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("a recorded verdict is never recomputed")

    monkeypatch.setattr(ov, "build_report", never)
    monkeypatch.setattr(ov, "evaluate_verdict", never)
    repo = FakeRepo(stored={"ledger_id": of.LEDGER_ID, "verdict": "SAVED"})
    result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=never, bars_fn=never,
                                repo=repo, engine=FakeEngine())
    assert result == oio.RESULT_ALREADY == "already recorded"
    assert repo.inserted == []


def test_losing_the_insert_race_reports_already_recorded_without_the_warning(report, caplog):
    repo = FakeRepo(accept=False)            # a concurrent check inserted first
    with caplog.at_level(logging.WARNING, logger=oio.log.name):
        result = oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert result == "already recorded"
    assert len(repo.inserted) == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_failing_evaluation_writes_nothing_and_raises(report, monkeypatch):
    def boom(rows):
        raise RuntimeError("bootstrap failed")

    monkeypatch.setattr(ov, "evaluate_verdict", boom)
    repo = FakeRepo()
    with pytest.raises(RuntimeError):
        oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert repo.inserted == []


def test_only_counted_rows_are_stored(report):
    bulk = {**_row(40, delta_r=1.5), "bulk": True}
    report["rows"] = _costly_rows() + [bulk]
    repo = FakeRepo()
    oio.run_daily_check(FRIDAY_SLOT, inputs_fn=_inputs, repo=repo, engine=FakeEngine())
    assert bulk not in repo.inserted[0]["rows"]
    assert len(repo.inserted[0]["rows"]) == 31


def test_stored_verdict_reads_the_ledger_id(monkeypatch):
    stored = {"ledger_id": of.LEDGER_ID, "verdict": "INCONCLUSIVE", "recorded_on": "2026-12-04"}
    assert oio.stored_verdict(FakeRepo(stored=stored)) == stored
    assert oio.stored_verdict(FakeRepo()) is None
    monkeypatch.setattr(oio, "verdict_repo", lambda: FakeRepo(stored=stored))
    assert oio.stored_verdict() == stored


def test_load_inputs_keys_trades_by_plan_id(monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.tracking import performance

    class FakeStore:
        def all(self):
            return ["plan-a", "plan-b"]

    class FakeLog:
        def get_trades(self, status=None, limit=None, ledger=None):
            assert (status, limit, ledger) == (None, None, None)   # every trade, every ledger
            return [{"id": "t1", "plan_id": "a", "shares": 5},
                    {"id": "t2", "plan_id": None},
                    {"id": "t3", "plan_id": "a", "shares": 9}]

    monkeypatch.setattr(plan_store, "PlanStore", FakeStore)
    monkeypatch.setattr(performance, "TradeLog", FakeLog)
    plans, trades = oio.load_inputs()
    assert plans == ["plan-a", "plan-b"]
    assert trades == {"a": {"id": "t1", "plan_id": "a", "shares": 5}}
```

Row dates: `_row(i)` spreads `i` over 12 Tuesdays from 2026-09-01 (`7 * (i % 12)` days, plus `i // 12` days so rows in one week differ), so 31 rows give 12 distinct ISO weeks. If V173-10's `evaluate_verdict` reads a field these rows lack (it must not: rows are in `to_dict()` form, the 20 `ROW_FIELDS`), fix `_row`, never `evaluate_verdict`.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_io.py
```

Expected: FAIL at collection, `ImportError: cannot import name 'override_io'`. Any other import error (`override_verdict`, `verdict_repo`) means V173-10 or V173-25 is not on the branch: stop and report.

- [ ] **Step 3: Write `swingbot/core/analytics/override_io.py`**

```python
"""v173: the I/O around the override-fidelity report -- the inputs, the stored
verdict, and the one evaluation.

`run_daily_check` is the only code that evaluates the frozen pre-registration
and the only writer of its verdict row; the bot's daily loop
(commands/scanning/loops.py:override_verdict_check) is its only caller. The
report script and the admin API import `load_inputs` and `stored_verdict` and
never evaluate. The primary key of `preregistration_verdicts` is the
idempotency authority: once a row exists, nothing is replayed or recomputed.
"""
from __future__ import annotations

import logging
from datetime import datetime

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import get_engine
from swingbot.core.db.repositories.preregistration_verdicts import verdict_repo

log = logging.getLogger(__name__)

RESULT_RECORDED = "recorded"
RESULT_ALREADY = "already recorded"
RESULT_WAITING = "waiting"
RECORDED_LOG = ("override_verdict_check: %s verdict %s recorded on %s and frozen. "
                "Mirror it into docs/superpowers/results/preregistration-ledger.jsonl: run "
                "scripts/reports/execution_fidelity_report.py --production --mirror-row on the VM, "
                "append the printed line on main and commit (standing procedure in %s).")
```

Functions:
- `load_inputs()`: imports `PlanStore` (`swingbot.core.planning.plan_store`) and `TradeLog` (`swingbot.core.tracking.performance`) **inside the function** (the existing analytics modules do the same, e.g. `expectancy_attribution.py:547`, to keep `core/analytics` free of import cycles; the test patches the source modules). Body as described in Interfaces; `get_trades(...) or []`.
- `stored_verdict(repo=None)`: one line, as in Interfaces.
- `run_daily_check(...)`: the order below is the contract; keep it in two named helpers so the function stays far below complexity 15:

```python
def run_daily_check(now: datetime, *, inputs_fn=None, bars_fn=None, repo=None,
                    engine=None) -> str:
    """Evaluate and record the verdict the first time the floors hold; once.
    The existence check and the insert share one transaction; the plan read
    inside it opens its own connection, which is fine: a concurrent second
    insert writes nothing and reports "already recorded"."""
    repo = repo or verdict_repo()
    asof = of.latest_completed_session(now)
    with (engine or get_engine()).begin() as conn:
        if repo.recorded(of.LEDGER_ID, conn=conn) is not None:
            return RESULT_ALREADY
        record = _evaluate(asof, inputs_fn or load_inputs, bars_fn or rp.cached_daily_bars)
        if record is None:
            return RESULT_WAITING
        if not repo.insert_once(record, conn=conn):
            return RESULT_ALREADY
    log.warning(RECORDED_LOG, record["verdict"], of.LEDGER_ID, record["recorded_on"],
                ov.RESULTS_RECORD)
    return RESULT_RECORDED
```

- `_evaluate(asof, inputs_fn, bars_fn) -> dict | None`: `plans, trades = inputs_fn()`; `report = ov.build_report(plans, trades, bars_fn, asof, None, config.CURRENCY_SYMBOL)`; `None` unless `report["verdict"]["evaluable"]`; else `verdict = ov.evaluate_verdict(report["rows"])` (all rows: eligibility and the excluded share need them) and `return ov.verdict_record(verdict, ov.counted(report["rows"]), report["engine_flags"], recorded_on=asof)` (`counted` makes the stored rows the counted ones whether or not `verdict_record` filters again; `counted` of counted rows is the same list).

`ov.build_report`, `ov.evaluate_verdict` and `rp.cached_daily_bars` are looked up through their modules at call time (the tests patch them there); `bars_fn or rp.cached_daily_bars` is evaluated inside the call, never bound as a default argument. `recorded=None` is passed to `build_report` because the check runs only when no row exists. An exception anywhere inside the `with` block rolls the transaction back and propagates; the loop (V173-27) logs it.

- [ ] **Step 4: Run the test and the verdict tests it leans on**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_io.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
```

Expected: both PASS, `0 failed`, `0 xfailed`. If `test_records_once_with_the_exact_record_shape_and_recorded_on_asof` finds `record["verdict"] != "COST"` on 31 rows whose deltas all lie in `[-0.24, -0.2]`, the bootstrap interval is not being read as V173-10 states (`hi < 0` gives `COST`): the defect is in V173-10, report it, never edit the rows to fit.

- [ ] **Step 5: One evaluator, and complexity**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "evaluate_verdict(\|insert_once(" -- swingbot/ scripts/
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_io.py
```

Expected: the grep shows `evaluate_verdict(` only at its definition in `override_verdict.py` and its call in `override_io.py`, and `insert_once(` only at its definition in `repositories/preregistration_verdicts.py` and its call in `override_io.py`. The `radon` call prints nothing.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_io.py tests/analytics/test_override_io.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override_io, the one evaluation of the override verdict, written once"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-27: Daily loop `override_verdict_check` in the bot scheduler

**Model:** sonnet — a loop following `gate_counterfactual_resolve`

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (the global beside `_gate_resolve_fired_date` at :714; the loop right after `gate_counterfactual_resolve`, which ends at :992; `_always_on_loops()` at :1100)
- Create: `tests/commands/test_override_verdict_loop.py`

**Interfaces:**
- Consumes: V173-26: `swingbot.core.analytics.override_io.run_daily_check(now: datetime, *, inputs_fn=None, bars_fn=None, repo=None, engine=None) -> str` (`"recorded"` / `"already recorded"` / `"waiting"`; raises on failure, writing nothing). Existing in `loops.py`: `SESSION_TZ` (Europe/Berlin, from `swingbot.bot_core`), `config.SESSION_END_HOUR` (Berlin hour, default 23), `_scheduled_job_already_fired(job, today) -> bool` (:717), `_mark_scheduled_job_fired(job, today) -> None` (:722), `log`.
- Produces (V173-16 runs its test, V173-18 checks the loop started on the VM):
  - `@tasks.loop(minutes=1) async def override_verdict_check()`, job name `"override_verdict_check"` in `scheduled_jobs`.
  - Process-local global `_override_verdict_fired_date: dt.date | None = None`.
  - `_always_on_loops()` ends with `override_verdict_check` (appended after `next_session_wrapup`).

**The slot and what decides "once"** (index Global Constraints, The one evaluator; § Handoff traps): weekdays, `now.hour == config.SESSION_END_HOUR and now.minute >= 50` in Europe/Berlin, i.e. 23:50 with the default, after the US close in every DST combination and after the resolver's :45 slot. The `scheduled_jobs` marker is written **before** the work, exactly as `gate_counterfactual_resolve` does at `loops.py:981-982`, so a raise after it is not retried that day: the check simply runs again the next weekday. The marker only throttles the per-minute tick; whether a verdict is ever written twice is decided by the `preregistration_verdicts` primary key inside `run_daily_check`, which answers `"already recorded"` before any replay once a row exists. So the loop runs every weekday for the life of the bot, cheaply after the verdict is recorded. There is no config flag: the evaluation cannot be switched off (Global Constraints).

One deliberate difference from `gate_counterfactual_resolve`: the marker read and write sit **inside** the `try`, so a database outage at the slot is logged, not raised. An exception escaping a `tasks.loop` coroutine stops that loop until the next restart, and this loop's whole purpose is to be there on the day the floors first hold.

- [ ] **Step 1: Write the failing test** `tests/commands/test_override_verdict_loop.py`

It follows `tests/commands/test_gate_resolver_loop.py` (frozen clock through `loops_mod.dt.datetime`, the process-local global reset, `asyncio.run(loop.coro())`). The `scheduled_jobs` marker goes to the disposable test database through the root autouse `_store_database` fixture (`tests/conftest.py:173`); the worker is a recorder, so nothing reads the book.

```python
"""v173 V173-27: the daily override-verdict check, weekdays at SESSION_END_HOUR:50 Berlin."""
import asyncio
import datetime as dt
import logging
import threading

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.analytics import override_io
from swingbot.core.db.repositories.scheduled import scheduled_repo

JOB = "override_verdict_check"
_DT = dt.datetime  # captured before _tick patches dt.datetime on the shared module
MONDAY = dt.date(2026, 10, 12)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_check(now, **kwargs):
        seen.append((now, threading.current_thread() is threading.main_thread()))
        return "waiting"

    monkeypatch.setattr(override_io, "run_daily_check", fake_check)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod, "_override_verdict_fired_date", None)
    return seen


def _tick(monkeypatch, now: _DT, *, restart: bool = False) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    if restart:
        monkeypatch.setattr(loops_mod, "_override_verdict_fired_date", None)
    asyncio.run(loops_mod.override_verdict_check.coro())


def test_fires_once_at_the_2350_slot_off_the_event_loop(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 49))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 51))
    assert len(calls) == 1
    now, on_main_thread = calls[0]
    assert on_main_thread is False                    # asyncio.to_thread
    assert now == _DT(2026, 10, 12, 23, 50, tzinfo=loops_mod.SESSION_TZ)
    assert scheduled_repo().fired_on(JOB) == MONDAY.isoformat()


def test_not_at_2349_and_not_outside_the_end_hour(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 49))
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 55))
    assert calls == []
    assert scheduled_repo().fired_on(JOB) is None


def test_a_restart_on_the_same_day_does_not_fire_again(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 55), restart=True)
    assert len(calls) == 1


def test_it_runs_again_the_next_weekday(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 13, 23, 50))
    assert [now.date() for now, _ in calls] == [MONDAY, dt.date(2026, 10, 13)]


@pytest.mark.parametrize("day", [17, 18])           # Saturday, Sunday
def test_never_fires_on_a_weekend(monkeypatch, calls, day):
    _tick(monkeypatch, _DT(2026, 10, day, 23, 50))
    assert calls == []


def test_a_failing_check_is_logged_never_raised(monkeypatch, calls, caplog):
    def boom(now, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(override_io, "run_daily_check", boom)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert any(JOB in r.getMessage() for r in caplog.records)


def test_a_failing_marker_read_is_logged_never_raised(monkeypatch, calls, caplog):
    def down(job, today):
        raise RuntimeError("scheduled_jobs unreachable")

    monkeypatch.setattr(loops_mod, "_scheduled_job_already_fired", down)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert calls == []
    assert any(JOB in r.getMessage() for r in caplog.records)


def test_the_result_is_logged(monkeypatch, calls, caplog):
    with caplog.at_level(logging.INFO, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert any(r.getMessage() == "override_verdict_check: waiting" for r in caplog.records)


def test_the_loop_starts_with_the_bot_last_in_order():
    loops = loops_mod._always_on_loops()
    assert loops[-1] is loops_mod.override_verdict_check
    assert loops_mod.gate_counterfactual_resolve in loops          # nothing else dropped
```

`test_a_failing_marker_read_is_logged_never_raised` pins the one difference from the resolver loop (marker calls inside the `try`).

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose -f E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/docker-compose.yml --profile test up -d db-test
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/commands/test_override_verdict_loop.py
```

Expected: FAIL, `AttributeError: ... has no attribute '_override_verdict_fired_date'` from the `calls` fixture (and `override_verdict_check` in the last test). A `skipped` result naming `db-test` means the container is not up.

- [ ] **Step 3: Add the global, the loop and the tuple entry in `swingbot/commands/scanning/loops.py`**

Global, after `_gate_resolve_fired_date: dt.date | None = None` (:714):

```python
_override_verdict_fired_date: dt.date | None = None
```

Loop, directly after `gate_counterfactual_resolve` (ends :992):

```python
@tasks.loop(minutes=1)
async def override_verdict_check():
    """v173: the one evaluation of the override-fidelity pre-registration, checked
    once per weekday at SESSION_END_HOUR:50 Berlin (after the US close and the
    resolver's :45 slot). Off the event loop (`asyncio.to_thread`).

    The scheduled_jobs marker is written before the work (as in
    gate_counterfactual_resolve), so a failure is not retried until the next
    weekday. It only throttles this tick: whether a verdict is written twice is
    decided by the preregistration_verdicts primary key inside run_daily_check,
    which returns "already recorded" before any replay once a row exists. The
    marker calls sit inside the try so a database outage is logged, never raised
    (an escaping exception would stop this loop until a restart)."""
    global _override_verdict_fired_date
    now = dt.datetime.now(SESSION_TZ)
    if now.weekday() > 4 or now.hour != config.SESSION_END_HOUR or now.minute < 50:
        return
    today = now.date()
    if _override_verdict_fired_date == today:
        return
    try:
        if _scheduled_job_already_fired('override_verdict_check', today):
            _override_verdict_fired_date = today
            return
        _override_verdict_fired_date = today
        _mark_scheduled_job_fired('override_verdict_check', today)
        from swingbot.core.analytics import override_io
        result = await asyncio.to_thread(override_io.run_daily_check, now)
        log.info("override_verdict_check: %s", result)
    except Exception:
        log.exception("override_verdict_check: daily check failed")
```

When the marker read raises, `_override_verdict_fired_date` stays unset, so the next minute's tick inside the slot tries again; once the marker is written, the process-local date stops further ticks that day. `override_io` is imported inside the `try`, as the resolver imports `gate_resolver`, so the bot's import graph does not grow at start-up and an import failure is logged like any other.

`_always_on_loops()` (:1100): append `override_verdict_check` after `next_session_wrapup` and keep every existing entry and its order:

```python
    return (session_scan, heartbeat, config_watcher, trade_monitor, daily_recap,
            weekend_deep_scan_task, weekly_earnings_refresh, gate_counterfactual_resolve,
            pitr_watch_loop, ops_watch.scan_watchdog, next_session_scan,
            next_session_wrapup, override_verdict_check)
```

- [ ] **Step 4: Run the new test and the neighbouring loop tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/commands/test_override_verdict_loop.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/commands/test_gate_resolver_loop.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/commands/test_outlook_loops.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py
```

Expected: all PASS, `0 failed`, `0 xfailed`, no skips.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/commands/scanning/loops.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/complexity_gate.py
```

Expected: `override_verdict_check` is not listed by `radon` (it is about B(7)); any function listed is a pre-existing one already in `complexity_baseline.json`, and `complexity_gate.py` exits 0.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/commands/scanning/loops.py tests/commands/test_override_verdict_loop.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): daily override_verdict_check loop at SESSION_END_HOUR:50 Berlin"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.
