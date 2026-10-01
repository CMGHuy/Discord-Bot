# v116 — Part 3: Phase 2, schema-change guarantees

Header, global constraints, revision ids and the full parallelisation map: `_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 2.

The codec (`split_doc`/`merge_doc`) already makes "add a field" a code-only change. This phase stops that eroding.

**Parallelisation (Phase 2, group C — after Phase 1, because the contract test must see `scan_progress` and `market_data_state`):**
- **Group (parallel):** V116-16 (`swingbot/core/db/schema.py`, `tests/db/test_schema_contract.py`) and V116-17 (`tests/db/test_unknown_field_round_trip.py` only).
- **Sequential:** V116-18 after V116-16 — both edit `schema.py`, and V116-18 adds a `PROMOTION_REASONS` entry for a dict V116-16 introduces. V116-19 after V116-18 — it documents the helper names V116-18 creates.
- Group C shares no file with group D (`_4a-readiness.md`), so the two run in parallel.

---

# Phase 2 — Schema-change guarantees

### Task V116-16: Schema contract test and a one-line reason per promoted column

**Files:**
- Modify: `swingbot/core/db/schema.py` (add `contract_violations()` and `PROMOTION_REASONS`)
- Create: `tests/db/test_schema_contract.py`

**Interfaces:**
- Consumes: `schema.METADATA`, `schema.PROMOTED` (main), the two V116-12 tables, Alembic head `v116_001`.
- Produces: `schema.contract_violations(table: sa.Table) -> list[str]`; `schema.PROMOTION_REASONS: dict[str, dict[str, str]]` (table → column → one-line reason). The spec says "its repository's `PROMOTED`"; `PROMOTED` lives in `schema.py` (filled by `register()`), so the reasons live beside it (`_0-index.md` § Spec points, 1). V116-18 adds the `dropped_doc_fields` entry.

- [ ] **Step 1: Write the failing test** — `tests/db/test_schema_contract.py`:

```python
"""The hybrid-schema contract every table keeps (v116 Phase 2).

`doc JSONB NOT NULL DEFAULT '{}'` is what makes "add a field" a code-only
change; `updated_at TIMESTAMPTZ` is what parity, PITR checks and the listener
lean on. A promoted column costs a migration forever after, so each one must
say why it exists. A new table without `doc` fails here."""
import pathlib

import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy.dialects.postgresql import JSONB

from swingbot.core.db import schema

REPO = pathlib.Path(__file__).resolve().parents[2]


def _reflected_columns(engine) -> dict[str, dict[str, dict]]:
    cfg = Config(str(REPO / "alembic.ini"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        inspector = sa.inspect(connection)
        return {name: {col["name"]: col for col in inspector.get_columns(name)}
                for name in schema.METADATA.tables}


def test_every_declared_table_keeps_the_contract():
    problems = [p for table in schema.METADATA.tables.values()
                for p in schema.contract_violations(table)]
    assert problems == []


def test_a_table_without_doc_or_updated_at_fails_the_contract():
    bad = sa.Table("bad", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True))
    assert schema.contract_violations(bad) == ["bad: no doc column", "bad: no updated_at column"]


def test_a_nullable_doc_or_naive_updated_at_fails_the_contract():
    bad = sa.Table("bad2", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True),
                   sa.Column("doc", JSONB, nullable=True),
                   sa.Column("updated_at", sa.TIMESTAMP(timezone=False), nullable=False))
    assert schema.contract_violations(bad) == [
        "bad2: doc must be JSONB NOT NULL DEFAULT '{}'",
        "bad2: updated_at must be TIMESTAMPTZ NOT NULL",
    ]


def test_the_migrated_database_keeps_the_contract(db_engine_empty):
    """Reflects what the Alembic chain actually built, not what schema.py claims."""
    for name, columns in _reflected_columns(db_engine_empty).items():
        doc = columns.get("doc")
        assert doc is not None, f"{name}: no doc column in the database"
        assert isinstance(doc["type"], JSONB), f"{name}.doc is {doc['type']}"
        assert doc["nullable"] is False, f"{name}.doc is nullable"
        assert "'{}'::jsonb" in str(doc["default"]), f"{name}.doc default is {doc['default']}"
        updated = columns.get("updated_at")
        assert updated is not None, f"{name}: no updated_at column in the database"
        assert getattr(updated["type"], "timezone", False), f"{name}.updated_at is not TIMESTAMPTZ"


def test_every_promoted_column_has_exactly_one_one_line_reason():
    expected = {(t, c) for t, cols in schema.PROMOTED.items() for c in cols}
    given = {(t, c) for t, cols in schema.PROMOTION_REASONS.items() for c in cols}
    assert given == expected, {"missing": expected - given, "stale": given - expected}
    for table, reasons in schema.PROMOTION_REASONS.items():
        for column, reason in reasons.items():
            assert reason.strip() and "\n" not in reason and len(reason) <= 100, (table, column)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_schema_contract.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.db.schema' has no attribute 'contract_violations'`.

- [ ] **Step 3: Add `contract_violations`** — in `swingbot/core/db/schema.py`, after `promoted_for`:

```python
def _doc_ok(column: sa.Column) -> bool:
    return (isinstance(column.type, JSONB) and not column.nullable
            and column.server_default is not None)


def contract_violations(table: sa.Table) -> list[str]:
    """What a table breaks of the hybrid contract (docs/claude/schema-evolution.md):
    a `doc JSONB NOT NULL DEFAULT '{}'` and an `updated_at TIMESTAMPTZ NOT NULL`."""
    problems = []
    doc = table.c.get("doc")
    if doc is None:
        problems.append(f"{table.name}: no doc column")
    elif not _doc_ok(doc):
        problems.append(f"{table.name}: doc must be JSONB NOT NULL DEFAULT '{{}}'")
    updated = table.c.get("updated_at")
    if updated is None:
        problems.append(f"{table.name}: no updated_at column")
    elif not getattr(updated.type, "timezone", False) or updated.nullable:
        problems.append(f"{table.name}: updated_at must be TIMESTAMPTZ NOT NULL")
    return problems
```

- [ ] **Step 4: Add `PROMOTION_REASONS`** — at the end of `swingbot/core/db/schema.py`:

```python
#: Why each promoted column is a column and not a `doc` field. A promotion
#: costs a migration forever after, so each names what needs it: identity,
#: a foreign key, an index a hot query uses, or a NOT NULL the database must
#: enforce. tests/db/test_schema_contract.py requires exactly one line per
#: PROMOTED entry -- promoting a column means adding its reason here.
PROMOTION_REASONS: dict[str, dict[str, str]] = {
    "trades": {
        "trade_id": "natural key; unique lookup from every command and the admin",
        "ticker": "trades_ticker_opened_idx; per-ticker open-trade checks",
        "strategy": "per-strategy filters in analytics",
        "horizon": "one-trade-per-ticker-and-horizon check",
        "direction": "NOT NULL invariant every consumer relies on",
        "status": "trades_status_idx; open/closed filter on every read",
        "opened_at": "trades_ticker_opened_idx ordering; NOT NULL",
        "closed_at": "closed-trade date ranges in analytics",
        "entry": "numeric column for SQL-side P&L queries",
        "stop_loss": "numeric column for SQL-side risk queries",
    },
    "plans": {
        "plan_id": "natural key; foreign-key target of starred_plans",
        "ticker": "plans_ticker_idx; per-ticker plan lookup",
        "strategy": "per-strategy plan filters",
        "horizon_key": "per-horizon plan filters",
        "status": "plans_status_idx; open-plan polling every tick",
        "created_at": "age ordering on the Plans screen; NOT NULL",
    },
    "starred_plans": {"plan_id": "unique key and cascading foreign key into plans"},
    "account": {"key": "singleton key ('config')"},
    "account_balance_history": {
        "ts": "unique key; chronological balance history",
        "balance": "numeric column for the equity curve",
    },
    "journal_entries": {
        "trade_id": "natural key; one entry per trade",
        "strategy": "per-strategy journal filters",
        "outcome": "win/loss filters",
        "closed_at": "journal_entries_closed_idx ordering",
        "created_at": "NOT NULL creation time",
    },
    "signal_state": {"key": "natural key of the confirmation state machine"},
    "watchlist": {
        "ticker": "natural key; one row per ticker",
        "added_at": "NOT NULL insertion time for ordering",
    },
    "runtime_flags": {
        "name": "natural key; one row per flag",
        "set_at": "when the flag was raised; shown by the admin",
    },
    "bot_heartbeat": {"key": "singleton key ('bot')", "ts": "liveness age computed in SQL"},
    "admin_jobs": {
        "job_id": "natural key",
        "kind": "filter by job type",
        "status": "admin_jobs_status_idx; active-job lookup",
        "started_at": "newest-first ordering; NOT NULL",
        "finished_at": "age-based prune of finished jobs",
    },
    "scheduled_jobs": {"job": "natural key", "fired_on": "NOT NULL fire-once-a-day date"},
    "ui_preferences": {"owner": "natural key; one row per user"},
    "settings_audit": {"ts": "settings_audit_ts_idx; newest-first audit list"},
    "killswitch": {
        "key": "singleton key ('global')",
        "engaged": "NOT NULL on/off that every issuance checks",
        "engaged_at": "when it engaged; shown to the partner",
    },
    "manual_close_notify": {"queued_at": "manual_close_notify_queued_idx; drain order"},
    "ticker_directory": {"symbol": "natural key", "name": "ticker_directory_name_idx; name search"},
    "tuning_results": {"job_id": "natural key; one result per job", "created_at": "NOT NULL creation time"},
    "tuning_proposals": {
        "filename": "natural key",
        "created_at": "tuning_proposals_created_idx; newest-first list",
    },
    "scan_progress": {"key": "singleton key ('current')"},
    "market_data_state": {"key": "natural key 'SYMBOL|timeframe'"},
}
```

- [ ] **Step 5: Run the contract test and the existing schema tests**

Run: `python scripts/dev/testrun.py file tests/db/test_schema_contract.py tests/db/test_schema.py tests/db/test_migrations.py`
Expected: PASS. If `test_every_promoted_column_has_exactly_one_one_line_reason` reports `missing`, a table was registered after this plan was written: add its reason, never loosen the test.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/db/schema.py` — no output.

```bash
git add swingbot/core/db/schema.py tests/db/test_schema_contract.py
git commit -m "test(v116): pin the doc/updated_at contract on every table; a reason per promoted column

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-17: A field no code has ever seen round-trips through every repository

**Files:**
- Create: `tests/db/test_unknown_field_round_trip.py`

**Interfaces:**
- Consumes: every repository class under `swingbot/core/db/repositories/` (18 on `main` plus V116-12's two), `db_conn`.
- Produces: the coverage rule "every table in `schema.METADATA` has a repository case or a stated reason not to" (`NOT_REPOSITORY_BACKED`), which V116-18's side table relies on.

- [ ] **Step 1: Write the test**

```python
"""A record carrying a field no code has ever seen is written through every
repository and read back unchanged -- nested objects and lists included
(v116 Phase 2). This is the property that makes "add a field" a code-only
change; a repository that drops or mangles unknown keys breaks it."""
import pytest

from swingbot.core.db import schema
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.flags import FlagRepository
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
from swingbot.core.db.repositories.jobs import JobRepository
from swingbot.core.db.repositories.journal import JournalRepository
from swingbot.core.db.repositories.killswitch import KillswitchRepository
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.preferences import PreferencesRepository
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository
from swingbot.core.db.repositories.scheduled import ScheduledJobRepository
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
from swingbot.core.db.repositories.signal_state import SignalStateRepository
from swingbot.core.db.repositories.starred import StarredRepository
from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository
from swingbot.core.db.repositories.watchlist import WatchlistRepository

TS = "2026-10-01T10:00:00+00:00"
PROBE = {"nested": {"list": [1, {"deep": "x"}, None], "flag": True},
         "tags": ["a", "b"], "ratio": 0.125, "empty": {}}
PLAN = {"plan_id": "P-probe", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
        "status": "pending", "created_at": TS}

#: table -> (repository factory, the NOT NULL promoted values a row needs)
CASES = {
    "trades": (TradeRepository, {"trade_id": "T-probe", "ticker": "AAPL", "strategy": "RSI",
                                 "horizon": "2w", "direction": "bullish", "status": "open",
                                 "opened_at": TS}),
    "plans": (PlanRepository, PLAN),
    "starred_plans": (StarredRepository, {"plan_id": "P-probe"}),
    "account": (AccountRepository, {"key": "config"}),
    "account_balance_history": (lambda: AccountRepository()._history, {"ts": TS, "balance": 1000.0}),
    "journal_entries": (JournalRepository, {"trade_id": "T-probe", "created_at": TS}),
    "signal_state": (SignalStateRepository, {"key": "AAPL|RSI|2w"}),
    "watchlist": (WatchlistRepository, {"ticker": "AAPL", "added_at": TS}),
    "runtime_flags": (FlagRepository, {"name": "scan_paused", "set_at": TS}),
    "bot_heartbeat": (HeartbeatRepository, {"key": "bot", "ts": TS}),
    "admin_jobs": (JobRepository, {"job_id": "J-probe", "kind": "tune", "status": "done",
                                   "started_at": TS}),
    "scheduled_jobs": (ScheduledJobRepository, {"job": "recap", "fired_on": "2026-10-01"}),
    "ui_preferences": (PreferencesRepository, {"owner": "admin"}),
    "settings_audit": (SettingsAuditRepository, {"ts": TS}),
    "killswitch": (KillswitchRepository, {"key": "global", "engaged": False}),
    "manual_close_notify": (NotifyQueueRepository, {"queued_at": TS}),
    "ticker_directory": (TickerDirectoryRepository, {"symbol": "AAPL", "name": "Apple"}),
    "tuning_results": (TuningRepository, {"job_id": "J-probe", "created_at": TS}),
    "tuning_proposals": (ProposalRepository, {"filename": "p.json", "created_at": TS}),
    "scan_progress": (ScanProgressRepository, {"key": "current"}),
    "market_data_state": (MarketDataStateRepository, {"key": "AAPL|daily"}),
}

#: Tables with no repository, and why. Anything else must be in CASES.
NOT_REPOSITORY_BACKED = {
    "dropped_doc_fields": "written only by swingbot.core.db.doc_fields inside Alembic revisions",
}


def _write(repo, record, conn):
    # Surrogate-keyed tables (append-only) insert; natural keys upsert.
    if repo.key == "id":
        return repo.insert(record, conn=conn)
    return repo.upsert(record, conn=conn)


@pytest.mark.parametrize("table", sorted(CASES))
def test_an_unseen_field_round_trips_unchanged(table, db_conn):
    factory, required = CASES[table]
    if table == "starred_plans":
        PlanRepository().upsert(dict(PLAN), conn=db_conn)   # its foreign key
    repo = factory()
    assert repo.table.name == table
    _write(repo, {**required, "_v116_probe": PROBE}, db_conn)
    rows = [row for row in repo.list_all(conn=db_conn) if "_v116_probe" in row]
    assert len(rows) == 1
    assert rows[0]["_v116_probe"] == PROBE


def test_every_table_is_covered_or_excused():
    assert set(schema.METADATA.tables) <= set(CASES) | set(NOT_REPOSITORY_BACKED)
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: PASS for all 21 cases. This test encodes a property the codec already has, so it passes on first run; a failure is a real finding — stop and report which repository dropped or changed the probe instead of editing the probe.

- [ ] **Step 3: Prove it can fail**

Temporarily change `merge_doc` in `swingbot/core/db/codec.py` to `out = {k: v for k, v in dict(row.get("doc") or {}).items() if not k.startswith("_")}`, run the test, see 21 failures, and revert with `git checkout -- swingbot/core/db/codec.py`. Confirm `git status` shows only the new test file.

- [ ] **Step 4: Commit**

```bash
git add tests/db/test_unknown_field_round_trip.py
git commit -m "test(v116): an unseen nested field round-trips through every repository

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-18: `rename_doc_field` / `drop_doc_field` helpers and their side table

**Files:**
- Create: `swingbot/core/db/doc_fields.py`
- Modify: `swingbot/core/db/schema.py` (table `dropped_doc_fields`; its `PROMOTION_REASONS` entry)
- Create: `swingbot/core/db/migrations/versions/v116_002_dropped_doc_fields.py`
- Create: `tests/db/test_doc_fields.py`

**Interfaces:**
- Consumes: `PROMOTION_REASONS` and `contract_violations` (V116-16); head `v116_001` (V116-12).
- Produces: `doc_fields.SIDE_TABLE = "dropped_doc_fields"`; `DocFieldConflict(RuntimeError)`; `rename_doc_field(table, old, new, *, conn=None) -> int` (rows changed; its downgrade is the same call reversed); `drop_doc_field(table, name, *, conn=None) -> int` (snapshots every present value, then removes the key); `restore_doc_field(table, name, *, conn=None) -> int` (the drop's downgrade). `conn=None` means `alembic.op.get_bind()`. Table `dropped_doc_fields(id, table_name, field, row_id, doc, updated_at)` with unique `(table_name, field, row_id)`, `doc = {"value": <dropped value>}`. V116-19 documents all of it.

- [ ] **Step 1: Write the failing tests** — `tests/db/test_doc_fields.py`:

```python
"""Rename and drop helpers for Alembic data revisions, up and down (v116)."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

from swingbot.core.db import doc_fields
from swingbot.core.db.repositories.plans import PlanRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
TS = "2026-10-01T10:00:00+00:00"


def _plan(conn, plan_id, **doc):
    PlanRepository().upsert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "pending", "created_at": TS,
                             **doc}, conn=conn)


def _get(conn, plan_id):
    return PlanRepository().get(plan_id, conn=conn)


def test_rename_moves_the_value_and_the_reverse_call_moves_it_back(db_conn):
    _plan(db_conn, "P1", old_name={"a": [1, 2]})
    _plan(db_conn, "P2")
    assert doc_fields.rename_doc_field("plans", "old_name", "new_name", conn=db_conn) == 1
    p1 = _get(db_conn, "P1")
    assert "old_name" not in p1 and p1["new_name"] == {"a": [1, 2]}
    assert "new_name" not in _get(db_conn, "P2")
    doc_fields.rename_doc_field("plans", "new_name", "old_name", conn=db_conn)
    assert _get(db_conn, "P1")["old_name"] == {"a": [1, 2]}


def test_rename_refuses_a_row_carrying_both_names_and_changes_nothing(db_conn):
    _plan(db_conn, "P1", old_name=1, new_name=2)
    with pytest.raises(doc_fields.DocFieldConflict, match="both"):
        doc_fields.rename_doc_field("plans", "old_name", "new_name", conn=db_conn)
    p1 = _get(db_conn, "P1")
    assert (p1["old_name"], p1["new_name"]) == (1, 2)


def test_drop_snapshots_first_and_restore_puts_every_value_back(db_conn):
    _plan(db_conn, "P1", legacy=3.5)
    _plan(db_conn, "P2", legacy=None)        # an explicit null is a value too
    _plan(db_conn, "P3")
    assert doc_fields.drop_doc_field("plans", "legacy", conn=db_conn) == 2
    assert all("legacy" not in _get(db_conn, p) for p in ("P1", "P2", "P3"))
    side = db_conn.execute(sa.text("SELECT count(*) FROM dropped_doc_fields")).scalar_one()
    assert side == 2
    assert doc_fields.restore_doc_field("plans", "legacy", conn=db_conn) == 2
    assert _get(db_conn, "P1")["legacy"] == 3.5
    raw = db_conn.execute(sa.text(
        "SELECT doc ? 'legacy' FROM plans WHERE plan_id = 'P2'")).scalar_one()
    assert raw is True
    assert "legacy" not in _get(db_conn, "P3")
    assert db_conn.execute(sa.text("SELECT count(*) FROM dropped_doc_fields")).scalar_one() == 0


def test_a_repeated_drop_overwrites_its_snapshot_instead_of_failing(db_conn):
    _plan(db_conn, "P1", legacy=1)
    doc_fields.drop_doc_field("plans", "legacy", conn=db_conn)
    _plan(db_conn, "P1", legacy=2)
    doc_fields.drop_doc_field("plans", "legacy", conn=db_conn)
    doc_fields.restore_doc_field("plans", "legacy", conn=db_conn)
    assert _get(db_conn, "P1")["legacy"] == 2


def test_the_table_name_is_validated_before_it_reaches_sql(db_conn):
    with pytest.raises(ValueError, match="identifier"):
        doc_fields.drop_doc_field("plans; DROP TABLE trades", "x", conn=db_conn)


def test_inside_a_revision_the_helpers_use_the_alembic_bind(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        _plan(connection, "P-op", before=1)
        with Operations.context(MigrationContext.configure(connection)):
            assert doc_fields.rename_doc_field("plans", "before", "after") == 1
        assert _get(connection, "P-op")["after"] == 1
        connection.execute(sa.text("DELETE FROM plans WHERE plan_id = 'P-op'"))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_doc_fields.py`
Expected: FAIL — `ImportError: cannot import name 'doc_fields'`.

- [ ] **Step 3: Declare the side table** — in `swingbot/core/db/schema.py`, before `PROMOTION_REASONS`:

```python
# v116 Phase 2: where doc_fields.drop_doc_field keeps what it removed, so the
# revision's downgrade can put it back. Written only inside Alembic revisions.
dropped_doc_fields = register(sa.Table("dropped_doc_fields", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("table_name", sa.Text, nullable=False),
    sa.Column("field", sa.Text, nullable=False),
    sa.Column("row_id", sa.BigInteger, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("table_name", "field", "row_id", name="dropped_doc_fields_row_uq")),
    ("table_name", "field", "row_id"))
```

and add to `PROMOTION_REASONS`:

```python
    "dropped_doc_fields": {
        "table_name": "which table a dropped value came from; restore filter",
        "field": "which doc field was dropped; restore filter",
        "row_id": "the source row's id; restore join key",
    },
```

- [ ] **Step 4: The migration** — `swingbot/core/db/migrations/versions/v116_002_dropped_doc_fields.py`:

```python
"""dropped_doc_fields: the side table drop_doc_field snapshots into

Revision ID: v116_002
Revises: v116_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v116_002"
down_revision = "v116_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dropped_doc_fields",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("table_name", sa.Text, nullable=False),
        sa.Column("field", sa.Text, nullable=False),
        sa.Column("row_id", sa.BigInteger, nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("table_name", "field", "row_id", name="dropped_doc_fields_row_uq"),
    )


def downgrade() -> None:
    op.drop_table("dropped_doc_fields")
```

- [ ] **Step 5: The helpers** — `swingbot/core/db/doc_fields.py`:

```python
"""Rename and drop a `doc` field inside an Alembic data revision (v116 Phase 2).

    from swingbot.core.db.doc_fields import drop_doc_field, rename_doc_field, restore_doc_field

    def upgrade():   rename_doc_field("trades", "tp1_hit", "target1_hit")
    def downgrade(): rename_doc_field("trades", "target1_hit", "tp1_hit")

    def upgrade():   drop_doc_field("plans", "legacy_score")
    def downgrade(): restore_doc_field("plans", "legacy_score")

A shape change is applied once, by a revision: nothing upcasts at read time,
so there is one code path per field (docs/claude/schema-evolution.md).
Promoted columns are not doc fields; changing one is a normal DDL revision.
"""
from __future__ import annotations

import re

import sqlalchemy as sa

SIDE_TABLE = "dropped_doc_fields"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class DocFieldConflict(RuntimeError):
    """A rename would overwrite a value already stored under the new name."""


def _table(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"{name!r} is not a plain lowercase SQL identifier; "
                         "it is interpolated into SQL")
    return name


def _bind(conn):
    if conn is not None:
        return conn
    from alembic import op
    return op.get_bind()


def rename_doc_field(table: str, old: str, new: str, *, conn=None) -> int:
    """Move `old` to `new` in every row carrying it. Reversed by swapping names."""
    c, t = _bind(conn), _table(table)
    params = {"old": old, "new": new}
    clash = c.execute(sa.text(
        f"SELECT count(*) FROM {t} WHERE doc ? CAST(:old AS text) AND doc ? CAST(:new AS text)"),
        params).scalar_one()
    if clash:
        raise DocFieldConflict(f"{t}: {clash} row(s) carry both {old!r} and {new!r}; "
                               "resolve them in a revision before renaming")
    return c.execute(sa.text(
        f"UPDATE {t} SET doc = (doc - CAST(:old AS text)) "
        f"|| jsonb_build_object(CAST(:new AS text), doc -> CAST(:old AS text)) "
        f"WHERE doc ? CAST(:old AS text)"), params).rowcount


def drop_doc_field(table: str, name: str, *, conn=None) -> int:
    """Snapshot every present `name` value into the side table, then remove it."""
    c, t = _bind(conn), _table(table)
    params = {"t": t, "f": name}
    c.execute(sa.text(
        f"INSERT INTO {SIDE_TABLE} (table_name, field, row_id, doc) "
        f"SELECT :t, CAST(:f AS text), id, jsonb_build_object('value', doc -> CAST(:f AS text)) "
        f"FROM {t} WHERE doc ? CAST(:f AS text) "
        f"ON CONFLICT (table_name, field, row_id) "
        f"DO UPDATE SET doc = EXCLUDED.doc, updated_at = clock_timestamp()"), params)
    return c.execute(sa.text(
        f"UPDATE {t} SET doc = doc - CAST(:f AS text) WHERE doc ? CAST(:f AS text)"),
        params).rowcount


def restore_doc_field(table: str, name: str, *, conn=None) -> int:
    """The drop's downgrade: put every snapshotted value back, then forget it."""
    c, t = _bind(conn), _table(table)
    params = {"t": t, "f": name}
    restored = c.execute(sa.text(
        f"UPDATE {t} AS target "
        f"SET doc = target.doc || jsonb_build_object(CAST(:f AS text), side.doc -> 'value') "
        f"FROM {SIDE_TABLE} AS side WHERE side.table_name = :t "
        f"AND side.field = CAST(:f AS text) AND side.row_id = target.id"), params).rowcount
    c.execute(sa.text(
        f"DELETE FROM {SIDE_TABLE} WHERE table_name = :t AND field = CAST(:f AS text)"), params)
    return restored
```

- [ ] **Step 6: Run the helpers, contract, round-trip and migration tests**

Run: `python scripts/dev/testrun.py file tests/db/test_doc_fields.py tests/db/test_schema_contract.py tests/db/test_unknown_field_round_trip.py tests/db/test_migrations.py tests/db/test_schema.py`
Expected: PASS; `python -m alembic heads` → `v116_002 (head)`.

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/db/doc_fields.py swingbot/core/db/schema.py` — no output.

```bash
git add swingbot/core/db/doc_fields.py swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v116_002_dropped_doc_fields.py tests/db/test_doc_fields.py
git commit -m "feat(v116): rename/drop doc-field helpers for data revisions, reversible (v116_002)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-19: `docs/claude/schema-evolution.md`, its `CLAUDE.md` row and the Codex mirror

**Files:**
- Create: `docs/claude/schema-evolution.md`
- Modify: `CLAUDE.md` (Reference docs table: one row)
- Modify: `AGENTS.md` (reference list: one line)

**Interfaces:**
- Consumes: `doc_fields.rename_doc_field/drop_doc_field/restore_doc_field`, `schema.PROMOTION_REASONS`, `schema.contract_violations` (V116-16, V116-18).
- Produces: the recipe doc V116-40's docs sweep and the `schema-change` skill point at.

- [ ] **Step 1: Write `docs/claude/schema-evolution.md`**

```markdown
# Schema evolution — add, rename, drop, promote

Referenced from the root `CLAUDE.md`. **Read before changing a table's shape or
the fields a stored record carries.**

Every table is hybrid: a few **promoted** columns (keys, foreign keys, indexed
or NOT NULL fields) plus `doc JSONB NOT NULL DEFAULT '{}'` holding every other
field, and `updated_at TIMESTAMPTZ`. `split_doc`/`merge_doc`
(`swingbot/core/db/codec.py`) move a flat record across that boundary. The data
model changes about once per plan (v39, v50, v52, v58 reshaped trades and
plans); this layout is what keeps that cheap. Three tests keep it that way:

| Test | Guards |
|---|---|
| `tests/db/test_schema_contract.py` | every table has `doc` and `updated_at`; every promoted column has a one-line reason in `schema.PROMOTION_REASONS` |
| `tests/db/test_unknown_field_round_trip.py` | a field no code has seen, nested, survives every repository |
| `tests/db/test_doc_fields.py` | rename and drop run up and down |

## The four operations

| Operation | What you do | Migration? |
|---|---|---|
| **add** | Write the field. It lands in `doc`. | None. |
| **rename** | A data revision: `rename_doc_field(table, old, new)` in `upgrade()`, the same call with the names swapped in `downgrade()`. It refuses (`DocFieldConflict`) if any row carries both names. | Data revision. |
| **drop** | A data revision: `drop_doc_field(table, name)` in `upgrade()`, `restore_doc_field(table, name)` in `downgrade()`. The drop first snapshots every value into `dropped_doc_fields`, so the downgrade restores them exactly (explicit nulls included). | Data revision. |
| **promote** | `op.add_column`, a backfill `UPDATE t SET col = (doc->>'field')::type`, the column in `register(...)`'s tuple **and** a reason in `PROMOTION_REASONS`. Keep the `doc` copy: `merge_doc` lets a non-null column win, so both agree and a later demote is a column drop. | DDL revision. |

The helpers live in `swingbot/core/db/doc_fields.py`. Inside a revision they use
`alembic.op.get_bind()`; tests pass `conn=`.

## No read-time upcasting

A shape change is applied **once, by a revision**. Never add code that reads a
field under its old name "just in case": that is a second code path per field
forever, and it is how v58's `tp1_hit`/`target1_hit` confusion started. If old
rows exist, the revision converts them.

## Revision ids

`p[1-6]_NNN` for v67's parts, `v<plan>_NNN` for later plans (`v116_001`).
`tests/db/test_migrations.py` requires one of those shapes and exactly one
head. A new revision's `down_revision` is the current head
(`python -m alembic heads`).

## Before running a data revision on production

A drop or rename touches every row. Check the last PITR drill passed
(`docs/deploy/DB_RESTORE.md`) — the rollback is `scripts/ops/rollback_to.sh`
to the second before the revision ran.
```

- [ ] **Step 2: Add the `CLAUDE.md` row and check the size rule**

In `CLAUDE.md`'s Reference docs table, after the `code-complexity.md` row, add:

```markdown
| `schema-evolution.md` | changing a table's shape or a stored record's fields — add, rename, drop, promote; no read-time upcasting |
```

Run: `wc -l CLAUDE.md` — must stay under 200 (159 + 1 when planned).

- [ ] **Step 3: Mirror it in `AGENTS.md`**

In `AGENTS.md`'s reference list (after the `code-complexity.md` line, currently line 170):

```markdown
- `docs/claude/schema-evolution.md` before changing a table's shape or the
  fields a stored record carries (add, rename, drop, promote).
```

- [ ] **Step 4: Run the mirror and hook tests**

Run: `python scripts/dev/sync_codex.py --check` then `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: no problems; PASS.

- [ ] **Step 5: Commit (Claude doc and its Codex mirror together)**

```bash
git add docs/claude/schema-evolution.md CLAUDE.md AGENTS.md
git commit -m "docs(v116): schema-evolution recipe -- add, rename, drop, promote; Codex mirror

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
