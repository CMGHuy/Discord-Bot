# Durable lifecycle notifications — part 1: storage

**Bump:** bot patch, ui patch
**Edge:** harvest
**Spec:** [Approved v197 spec](../specs/2026-10-28-v197-durable-lifecycle-notifications.md)

Read the [index](2026-10-28-v197-durable-lifecycle-notifications_0-index.md) for the goal, frozen contracts, execution prerequisite and complete task ledger.

## Parallelisation

V197-1 → V197-1b → V197-2 → V197-2b: the migration freezes the event contract; the repository consumes the migrated schema; operational methods extend that same repository and test file. Follow the index's global constraints and sequential execution policy. Implementation starts after v194 merges; this document authorizes no database or production operation.

# Phase 1 — Durable event storage

### Task V197-1: Define immutable lifecycle event snapshots
**Model:** sonnet — the task defines a pure event contract without persistence changes.

**Files:**
- Create: `swingbot/core/infra/lifecycle_events.py`
- Create: `tests/infra/test_lifecycle_events.py`

**Interfaces:** Creates `make_event(*, transition_id, kind, target_channel_id, occurred_at, payload) -> dict` and `validate_event(event: dict) -> None`. V197-1b freezes equivalent historical conversion in its revision, and V197-2 consumes the runtime contract. Confirm v194 is merged before implementation.

- [ ] **Step 1: Write failing event tests.** Write `tests/infra/test_lifecycle_events.py`:


```python
from copy import deepcopy
import pytest
from swingbot.core.infra.lifecycle_events import make_event, validate_event

AT = "2026-10-28T12:00:00+00:00"


def payload(status="CANCELLED"):
    return dict(ticker="AAPL", direction="bullish", plan_id="P-1", trade_id=None,
                prior_status="PENDING", new_status=status, reason="manual",
                occurred_at=AT)


def event(transition="transition-1", channel="5"):
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id=channel, occurred_at=AT, payload=payload())


def test_identity_belongs_to_transition_and_payload_is_copied():
    data = payload()
    result = make_event(transition_id="a", kind="plan_transition",
                        target_channel_id="5", occurred_at=AT, payload=data)
    data["reason"] = "changed later"
    assert result["payload"]["reason"] == "manual"
    assert event()["event_id"] == event()["event_id"]
    assert event("another")["event_id"] != event()["event_id"]
    assert result["attempt_count"] == 0
    assert result["next_attempt_at"] == AT
    assert result["delivered_at"] is None


def test_missing_destination_is_durable_and_blocked():
    result = event(channel=None)
    assert result["blocked"] is True
    assert result["last_error"] == "destination_unresolved"
    validate_event(result)  # destination resolution is a delivery concern


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"payload": {}}, {"event_id": "wrong"},
    {"payload": {**payload(), "occurred_at": "2026-10-28T12:00:00"}},
    {"payload": {**payload(), "trade": {"exit_price": 42}}},
])
def test_bad_contract_is_rejected(change):
    result = deepcopy(event())
    result.update(change)
    with pytest.raises(ValueError):
        validate_event(result)
```

- [ ] **Step 2: Confirm the narrow red test.** Run `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events.py`; expect the new module to be missing.

- [ ] **Step 3: Implement the event contract.** Write `swingbot/core/infra/lifecycle_events.py`:

```python
"""Immutable lifecycle rendering snapshots; no database or network access."""
from copy import deepcopy
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5


def _identity(transition_id, kind):
    return str(uuid5(NAMESPACE_URL, f"swingbot:lifecycle:{transition_id}:{kind}"))


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_transition_time") from None
    if parsed.tzinfo is None:
        raise ValueError("invalid_transition_time")


def _validate_trade(payload):
    trade = payload.get("trade")
    if not isinstance(trade, dict):
        raise ValueError("missing_trade_snapshot")
    pairs = (("id", "trade_id"), ("ticker", "ticker"), ("direction", "direction"),
             ("status", "new_status"))
    if any(not trade.get(a) or trade[a] != payload.get(b) for a, b in pairs):
        raise ValueError("inconsistent_trade_snapshot")
    if trade["status"] not in ("win", "loss", "closed") or "entry" not in trade:
        raise ValueError("invalid_trade_snapshot")


def _validate_payload(kind, payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    required = ("ticker", "direction", "prior_status", "new_status", "reason", "occurred_at")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
        raise ValueError("incomplete_payload")
    if payload["direction"] not in ("bullish", "bearish"):
        raise ValueError("invalid_direction")
    _aware(payload["occurred_at"])
    if kind == "trade_closed":
        _validate_trade(payload)
        return
    if not payload.get("plan_id") or payload["new_status"] not in ("CLOSED", "CANCELLED"):
        raise ValueError("invalid_plan_transition")
    if payload["new_status"] == "CANCELLED" and "trade" in payload:
        raise ValueError("cancelled_plan_has_fill")


def validate_event(event: dict) -> None:
    kind = event.get("kind")
    if kind not in ("trade_closed", "plan_transition") or not event.get("transition_id"):
        raise ValueError("invalid_event_kind_or_identity")
    if event.get("event_id") != _identity(event["transition_id"], kind):
        raise ValueError("invalid_event_identity")
    _aware(event.get("queued_at"))
    _validate_payload(kind, event.get("payload"))


def make_event(*, transition_id, kind, target_channel_id, occurred_at, payload) -> dict:
    channel = str(target_channel_id) if target_channel_id is not None else None
    if channel is not None and (not channel.isdecimal() or int(channel) <= 0):
        channel = None
    result = dict(event_id=_identity(transition_id, kind), transition_id=transition_id,
                  kind=kind, target_channel_id=channel, queued_at=occurred_at,
                  payload=deepcopy(payload), attempt_count=0, next_attempt_at=occurred_at,
                  lease_token=None, lease_owner=None, lease_until=None,
                  last_error=None if channel else "destination_unresolved", blocked=not bool(channel),
                  delivered_message_id=None, delivered_at=None, retarget_history=[])
    validate_event(result)
    return result
```

Validation rejects invented defaults in fresh producers. The allowed null destination is deliberate: an otherwise successful admin transaction records a blocked notification which can be explicitly retargeted. Snapshot validation during delivery is strict; the migration may preserve incomplete records which that validation will refuse to send.

- [ ] **Step 4: Verify the contract.** Run `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events.py`; require zero failures/xfailed. Run `python scripts/dev/complexity_gate.py`; every new function remains below 15. No DB test or full suite belongs to this pure-contract task.

- [ ] **Step 5: Commit the verified event contract.** After normal controller review and freshness checks, stage `swingbot/core/infra/lifecycle_events.py` and `tests/infra/test_lifecycle_events.py`; commit `feat(v197): define immutable lifecycle event snapshots`. The plan author does not execute this step.

### Task V197-1b: Preserve legacy queue rows through schema upgrade and downgrade
**Model:** opus — the task changes the Postgres schema and migrates historical delivery intent.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v197_001_lifecycle_notifications.py`
- Create: `tests/db/test_v197_lifecycle_migration.py`
- Modify: `swingbot/core/db/schema.py`
- Modify: `tests/db/test_unknown_field_round_trip.py`

**Interfaces:** Consumes V197-1's event contract and creates the promoted schema consumed by V197-2. Historical conversion is frozen within the revision, never a runtime upcaster.

- [ ] **Step 1: Establish the prerequisite and write failing migration tests.** Read schema-change before implementation; run `python -m alembic heads` and use the sole merged head as parent (the brief observed `v173_002`). Invoke replicate-prod-db before this task's first DB run using the shared infrastructure; do not start a new container or manually create a task database. Write `tests/db/test_v197_lifecycle_migration.py`. A transaction-local temporary table shadows the real queue, so revision tests cannot drop another test's queue or the replicated book. Existing `db_conn` owns rollback; no manual commit is permitted in these tests.

```python
import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic.migration import MigrationContext
from alembic.operations import Operations

FILE = (Path(__file__).resolve().parents[2] / "swingbot/core/db/migrations/versions"
        / "v197_001_lifecycle_notifications.py")
AT = "2026-10-28T12:00:00+00:00"


def revision():
    spec = importlib.util.spec_from_file_location("v197_migration", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy(db_conn):
    db_conn.execute(sa.text("""
        CREATE TEMP TABLE manual_close_notify (
          id BIGSERIAL PRIMARY KEY, queued_at TIMESTAMPTZ NOT NULL,
          doc JSONB NOT NULL DEFAULT '{}',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        ) ON COMMIT DROP
    """))
    db_conn.execute(sa.text("""
        CREATE INDEX manual_close_notify_queued_idx
        ON manual_close_notify(queued_at)
    """))
    return db_conn


def insert(conn, document):
    table = sa.table("manual_close_notify", sa.column("queued_at", sa.DateTime(True)),
                     sa.column("doc", JSONB))
    conn.execute(table.insert().values(queued_at=AT, doc=document))


def rows(conn):
    return conn.execute(sa.text("SELECT * FROM manual_close_notify ORDER BY id")).mappings().all()


def run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def test_upgrade_preserves_legacy_rows_and_marks_unknown_plan_blocked(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: "5")
    trade = dict(trade_id="T1", ticker="AAPL", direction="bullish", status="closed",
                 entry=100, exit_price=102, closed_at=AT, close_reason="manual")
    plan = dict(kind="plan_transition", plan_id="P1", ticker="MSFT", status="CANCELLED")
    insert(legacy, trade)
    insert(legacy, plan)
    run(legacy, mig.upgrade)
    first, second = rows(legacy)
    assert first["doc"]["kind"] == "trade_closed"
    assert first["doc"]["payload"]["trade"]["exit_price"] == 102
    assert first["doc"]["legacy_payload"] == trade
    assert second["doc"]["kind"] == "plan_transition"
    assert second["doc"]["payload"]["new_status"] == "CANCELLED"
    assert second["doc"]["blocked"] is True
    assert second["doc"]["last_error"] == "legacy_snapshot_incomplete"
    assert second["doc"]["legacy_payload"] == plan
    assert "trade" not in second["doc"]["payload"]
    assert first["event_id"] != second["event_id"]


def test_downgrade_reupgrade_preserves_identity_payload_and_pending(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: None)
    insert(legacy, dict(kind="plan_transition", plan_id="P1", status="CLOSED"))
    run(legacy, mig.upgrade)
    before = dict(rows(legacy)[0])
    run(legacy, mig.downgrade)
    down = rows(legacy)[0]
    assert down["doc"]["event_id"] == before["event_id"]
    assert down["doc"]["payload"] == before["doc"]["payload"]
    assert down["doc"]["delivered_at"] is None
    monkeypatch.setattr(mig, "_destination", lambda: "99")
    run(legacy, mig.upgrade)
    after = rows(legacy)[0]
    assert after["event_id"] == before["event_id"]
    assert after["doc"] == before["doc"]  # no implicit destination reassignment


def test_downgrade_copies_current_columns_over_stale_doc(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: None)
    insert(legacy, dict(trade_id="T1", ticker="AAPL", status="closed"))
    run(legacy, mig.upgrade)
    legacy.execute(sa.text("""UPDATE manual_close_notify SET
        lease_token = 'token', lease_until = queued_at + interval '120 seconds',
        next_attempt_at = queued_at + interval '900 seconds'"""))
    run(legacy, mig.downgrade)
    doc = rows(legacy)[0]["doc"]
    assert doc["lease_token"] == "token"
    assert doc["lease_until"] is not None
    assert doc["next_attempt_at"] != doc["queued_at"]
```

- [ ] **Step 2: Confirm the narrow red test.** Run `python scripts/dev/testrun.py file tests/db/test_v197_lifecycle_migration.py`; expect the new revision/schema to be missing. An unreachable DB skip is not behavioral red evidence.

- [ ] **Step 3: Promote only indexed/ownership state and write the revision.** Replace the existing queue declaration in `schema.py` with:

```python
manual_close_notify = register(sa.Table("manual_close_notify", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("event_id", sa.Text, nullable=False),
    sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("lease_token", sa.Text),
    sa.Column("lease_until", sa.TIMESTAMP(timezone=True)),
    sa.Column("delivered_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("manual_close_notify_queued_idx", "queued_at"),
    sa.Index("manual_close_notify_event_uidx", "event_id", unique=True),
    sa.Index("manual_close_notify_due_idx", "next_attempt_at", "queued_at",
             postgresql_where=sa.text("delivered_at IS NULL")),
    sa.Index("manual_close_notify_delivered_idx", "delivered_at",
             postgresql_where=sa.text("delivered_at IS NOT NULL"))),
    ("queued_at", "event_id", "next_attempt_at", "lease_token", "lease_until", "delivered_at"))
```

Replace its `PROMOTION_REASONS` entry, preserving all other table entries:

```python
"manual_close_notify": {
    "queued_at": "manual_close_notify_queued_idx; oldest pending age and ordering",
    "event_id": "manual_close_notify_event_uidx; immutable event deduplication and lookup",
    "next_attempt_at": "manual_close_notify_due_idx; due event selection",
    "lease_token": "fenced completion ownership comparison",
    "lease_until": "expired lease selection and fenced completion expiry",
    "delivered_at": "pending partial index and acknowledged retention index",
},
```

In `tests/db/test_unknown_field_round_trip.py`, change only the queue's required fixture to `{"queued_at": TS, "event_id": "round-trip", "next_attempt_at": TS}`. This generic repository test deliberately tests unknown-field preservation rather than lifecycle validation.

Write the following revision. `down_revision` is `v173_002` only if Step 1 still reports that sole head; substitute the actual merged head otherwise and record the change. The revision never imports the mutable runtime event module.

```python
"""Durable lifecycle intent; preserves pending work on upgrade and downgrade."""
from copy import deepcopy
from datetime import datetime, timezone
import logging
from uuid import NAMESPACE_URL, uuid5
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import context, op

revision = "v197_001"
down_revision = "v173_002"
branch_labels = None
depends_on = None
FIELDS = ("event_id", "next_attempt_at", "lease_token", "lease_until", "delivered_at")
TIMES = frozenset(("next_attempt_at", "lease_until", "delivered_at"))


def _destination():
    value = context.get_x_argument(as_dictionary=True).get("lifecycle_channel_id")
    return value if value and value.isdecimal() and int(value) > 0 else None


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _complete(payload, kind):
    required = ("ticker", "direction", "prior_status", "new_status", "reason", "occurred_at")
    if not all(payload.get(key) for key in required):
        return False
    if kind == "plan_transition":
        return bool(payload.get("plan_id")) and payload["new_status"] in ("CLOSED", "CANCELLED")
    trade = payload.get("trade", {})
    return bool(trade.get("id")) and "entry" in trade and trade.get("status") in ("closed", "win", "loss")


def _payload(old, kind):
    result = {key: old.get(key) for key in ("ticker", "direction", "plan_id", "trade_id")}
    result.update(prior_status=old.get("prior_status"), new_status=old.get("status"),
                  reason=old.get("reason") or old.get("close_reason"),
                  occurred_at=old.get("occurred_at") or old.get("closed_at"))
    if kind == "trade_closed":
        trade = deepcopy(old)
        trade["id"] = trade.pop("trade_id", None)
        result["trade"] = trade
    return result


def _upgrade_record(row, destination):
    old = deepcopy(row["doc"])
    if old.get("event_id") and old.get("transition_id") and "payload" in old:
        return old  # this revision's demoted shape, including delivered/leased state
    kind = "plan_transition" if old.get("kind") == "plan_transition" else "trade_closed"
    transition_id = f"legacy-manual-close-notify:{row['id']}"
    event_id = str(uuid5(NAMESPACE_URL, f"swingbot:lifecycle:{transition_id}:{kind}"))
    payload = _payload(old, kind)
    error = None if destination else "destination_unresolved"
    if not _complete(payload, kind):
        error = "legacy_snapshot_incomplete"
    at = _iso(row["queued_at"])
    return dict(event_id=event_id, transition_id=transition_id, kind=kind,
                target_channel_id=destination, queued_at=at, payload=payload,
                attempt_count=0, next_attempt_at=at, lease_token=None,
                lease_owner=None, lease_until=None, last_error=error, blocked=bool(error),
                delivered_message_id=None, delivered_at=None, retarget_history=[],
                legacy_payload=old)


def _table():
    return sa.Table("manual_close_notify", sa.MetaData(), autoload_with=op.get_bind())


def _columns(record):
    result = {name: record.get(name) for name in FIELDS}
    for name in TIMES:
        if isinstance(result[name], str):
            result[name] = datetime.fromisoformat(result[name])
    return result


def upgrade():
    for name in FIELDS:
        kind = sa.TIMESTAMP(timezone=True) if name in TIMES else sa.Text()
        op.add_column("manual_close_notify", sa.Column(name, kind, nullable=True))
    table = _table()
    conn = op.get_bind()
    destination = _destination()
    for row in conn.execute(sa.select(table)).mappings():
        record = _upgrade_record(row, destination)
        conn.execute(table.update().where(table.c.id == row["id"])
                     .values(doc=record, **_columns(record)))
        if record.get("blocked") and not row["doc"].get("event_id"):
            age = max(0.0, (datetime.now(timezone.utc) - row["queued_at"]).total_seconds())
            logging.getLogger("alembic.runtime.migration").error(
                "lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                record["event_id"], record["kind"], age, record["last_error"])
    op.alter_column("manual_close_notify", "event_id", nullable=False)
    op.alter_column("manual_close_notify", "next_attempt_at", nullable=False)
    op.create_index("manual_close_notify_event_uidx", "manual_close_notify", ["event_id"], unique=True)
    op.create_index("manual_close_notify_due_idx", "manual_close_notify",
                    ["next_attempt_at", "queued_at"], postgresql_where=sa.text("delivered_at IS NULL"))
    op.create_index("manual_close_notify_delivered_idx", "manual_close_notify", ["delivered_at"],
                    postgresql_where=sa.text("delivered_at IS NOT NULL"))


def downgrade():
    table = _table()
    conn = op.get_bind()
    for row in conn.execute(sa.select(table)).mappings():
        record = deepcopy(row["doc"])
        record.update({name: _iso(row[name]) for name in (*FIELDS, "queued_at")})
        conn.execute(table.update().where(table.c.id == row["id"]).values(doc=record))
    for name in ("delivered_idx", "due_idx", "event_uidx"):
        op.drop_index(f"manual_close_notify_{name}", table_name="manual_close_notify")
    for name in reversed(FIELDS):
        op.drop_column("manual_close_notify", name)
```

The timestamp copied by downgrade may use `+00:00` while PostgreSQL JSON output uses a different equivalent representation; tests compare semantic instants where relevant. The complete original legacy snapshot stays in `legacy_payload`, including unknown fields. Legacy snapshots with unknown prior status are retained blocked, even when a subset of closure result fields exists. Upgrade/downgrade requires consumers stopped and must not be run on production during implementation.

- [ ] **Step 4: Verify preservation and schema parity.** Run `python scripts/dev/testrun.py file tests/db/test_v197_lifecycle_migration.py`, `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`, `python scripts/dev/testrun.py file tests/db/test_schema_contract.py`, and `python scripts/dev/testrun.py file tests/db/test_migrations.py`. Require zero failures/xfailed, actual DB execution, one Alembic head and schema parity. Run `python scripts/dev/complexity_gate.py`; repair violations in changed functions rather than hiding them in the baseline.

- [ ] **Step 5: Commit the verified migration.** After normal controller review and freshness checks, stage this task's four paths and commit `feat(v197): preserve lifecycle intent across queue migration`. The author does not execute the commit. Never deploy this intermediate migration while an old drain consumer is running.

### Task V197-2: Implement fenced enqueue, lease, acknowledgement and retry persistence
**Model:** opus — the repository owns concurrent claims, fencing and queue-preserving transaction semantics.

**Files:**
- Modify: `swingbot/core/db/repositories/notify_queue.py`
- Create: `tests/db/test_notify_queue_delivery.py`

**Interfaces:** Consumes V197-1's canonical event, promoted schema and `validate_event`. Implements enqueue, pending, claim, acknowledge and reschedule; V197-2b adds health, pruning and explicit retargeting. `claim_one` returns the canonical record with its persisted token; completion requires that same token and a live lease. New consumer code in V197-6 must use internally owned transactions (omit conn) so claim/ack commits occur before return. The conn option exists for tests and atomic enqueue; a caller supplying conn owns commit and must never send while it remains open.

- [ ] **Step 1: Write real Postgres state-machine tests.** Read schema-change before implementation and invoke replicate-prod-db before this task's first DB run. Write `tests/db/test_notify_queue_delivery.py`; concurrency must use separate real connections. Existing db fixtures own their normal test infrastructure; never create a bespoke task container/database.

```python
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
import sqlalchemy as sa
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import manual_close_notify as queue
from swingbot.core.infra.lifecycle_events import make_event

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def fresh(identity=None, channel="5"):
    stamp = NOW.isoformat()
    return make_event(transition_id=identity or str(uuid4()), kind="plan_transition",
        target_channel_id=channel, occurred_at=stamp,
        payload=dict(ticker="AAPL", direction="bullish", plan_id="P1", trade_id=None,
                     prior_status="PENDING", new_status="CANCELLED", reason="manual",
                     occurred_at=stamp))


def record(repo, conn, event):
    return repo.list_all(conn=conn, where=queue.c.event_id == event["event_id"])[0]


def test_enqueue_uses_outer_transaction_and_rejects_conflicting_identity(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    nested = db_conn.begin_nested()
    repo.enqueue(event, conn=db_conn)
    repo.enqueue(event, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    conflicting = {**event, "payload": {**event["payload"], "reason": "different"}}
    with pytest.raises(ValueError, match="conflicting_event"):
        repo.enqueue(conflicting, conn=db_conn)
    nested.rollback()
    assert repo.pending(conn=db_conn) == 0


def test_claim_expiry_stale_ack_and_acknowledgement(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    first = repo.claim_one("worker-a", now=NOW, conn=db_conn)
    assert first["attempt_count"] == 1
    assert repo.claim_one("worker-b", now=NOW, conn=db_conn) is None
    later = NOW + timedelta(seconds=121)
    second = repo.claim_one("worker-b", now=later, conn=db_conn)
    assert second["lease_token"] != first["lease_token"]
    assert second["event_id"] == first["event_id"]
    assert not repo.acknowledge(event["event_id"], first["lease_token"], "111",
                                now=later, conn=db_conn)
    assert not repo.reschedule(event["event_id"], first["lease_token"], now=later,
                               delay_s=5, error_code="timeout", blocked=False, conn=db_conn)
    assert repo.acknowledge(event["event_id"], second["lease_token"], "222",
                            now=later, conn=db_conn)
    assert repo.pending(conn=db_conn) == 0
    assert record(repo, db_conn, event)["delivered_message_id"] == "222"


def test_retry_and_blocked_are_pending_with_no_destination_rerouting(db_conn, caplog):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    with caplog.at_level("ERROR"):
        assert repo.reschedule(event["event_id"], claim["lease_token"], now=NOW,
            delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert event["event_id"] in caplog.text
    assert "permission_denied" in caplog.text
    assert repo.claim_one("w", now=NOW + timedelta(seconds=899), conn=db_conn) is None
    assert record(repo, db_conn, event)["target_channel_id"] == "5"


def test_failed_ack_rolls_back_but_intent_survives(db_conn, monkeypatch):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    original = repo._write
    def fail_after_write(conn, value):
        original(conn, value)
        raise RuntimeError("injected persistence failure")
    monkeypatch.setattr(repo, "_write", fail_after_write)
    with pytest.raises(RuntimeError), db_conn.begin_nested():
        repo.acknowledge(event["event_id"], claim["lease_token"], "123", now=NOW, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    assert record(repo, db_conn, event)["delivered_message_id"] is None


@pytest.fixture
def committed_queue(db_engine, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.base.get_engine", lambda: db_engine)
    repo = NotifyQueueRepository()
    events = [fresh(), fresh()]
    for event in events:
        repo.enqueue(event)  # internally committed, visible to both connections
    yield repo, db_engine, events
    with db_engine.begin() as conn:
        conn.execute(queue.delete().where(queue.c.event_id.in_([e["event_id"] for e in events])))


def test_concurrent_claim_skips_locked_row(committed_queue):
    repo, engine, events = committed_queue
    with engine.connect() as one, engine.connect() as two:
        with one.begin(), two.begin():
            first = repo.claim_one("one", now=NOW, conn=one)
            second = repo.claim_one("two", now=NOW, conn=two)
            assert first["event_id"] != second["event_id"]
            assert {first["event_id"], second["event_id"]} == {e["event_id"] for e in events}
    assert repo.claim_one("three", now=NOW) is None


def test_ack_failure_owned_transaction_preserves_committed_claim(committed_queue, monkeypatch):
    repo, engine, events = committed_queue
    claim = repo.claim_one("one", now=NOW)
    original = repo._write
    def fail_after_write(conn, value):
        original(conn, value)
        raise RuntimeError("ack connection lost")
    monkeypatch.setattr(repo, "_write", fail_after_write)
    with pytest.raises(RuntimeError):
        repo.acknowledge(claim["event_id"], claim["lease_token"], "999", now=NOW)
    with engine.connect() as conn:
        saved = record(repo, conn, claim)
    assert saved["lease_token"] == claim["lease_token"]
    assert saved["delivered_at"] is None
```

- [ ] **Step 2: Run the narrow red test.** Run `python scripts/dev/testrun.py file tests/db/test_notify_queue_delivery.py`. Expected failures name missing claim/acknowledgement APIs or old `pending` semantics; database unavailability is not a behavioral red test.

- [ ] **Step 3: Replace the queue repository with fenced transitions.** Keep the existing singleton factory name. The existing generic Repository and schema symbols are verified in the brief. All additional helpers below are created by this task. Use this complete repository module:

```python
"""Durable manual lifecycle events with fenced, expiring delivery claims."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging
import re
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from swingbot.core.db.codec import normalise
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import manual_close_notify as queue
from swingbot.core.infra.lifecycle_events import validate_event

log = logging.getLogger(__name__)


def _instant(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _check_now(now):
    if now.tzinfo is None:
        raise ValueError("timezone_required")


def _age(event, now):
    return max(0.0, (now - _instant(event["queued_at"])).total_seconds())


def _clear_lease(event):
    event.update(lease_token=None, lease_owner=None, lease_until=None)


class NotifyQueueRepository(Repository):
    def __init__(self):
        super().__init__(queue, key="id")

    def _record(self, row):
        return normalise(super()._record(row))

    def _values(self, record):
        values = super()._values(record)
        values["doc"].update({key: normalise(record[key]) for key in self.promoted if key in record})
        for key in ("queued_at", "next_attempt_at", "lease_until", "delivered_at"):
            if values.get(key) is not None:
                values[key] = _instant(values[key])
        return values

    def _write(self, connection, record):
        values = self._values(record)
        values["updated_at"] = sa.func.clock_timestamp()
        connection.execute(queue.update().where(queue.c.event_id == record["event_id"]).values(**values))

    def enqueue(self, event: dict, *, conn=None) -> None:
        validate_event(event)
        values = self._values(event)
        statement = pg_insert(queue).values(**values).on_conflict_do_nothing(
            index_elements=[queue.c.event_id])
        with self._tx(conn) as connection:
            inserted = connection.execute(statement.returning(queue.c.event_id)).scalar_one_or_none()
            row = connection.execute(sa.select(queue).where(
                queue.c.event_id == event["event_id"])).one()
            saved = self._record(row)
            keys = ("transition_id", "kind", "target_channel_id", "payload")
            if any(saved.get(key) != event.get(key) for key in keys):
                raise ValueError("conflicting_event")
        if inserted is not None and event.get("blocked"):
            log.error("lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                      event["event_id"], event["kind"], _age(event, datetime.now(timezone.utc)),
                      event.get("last_error") or "destination_unresolved")

    def pending(self, *, conn=None) -> int:
        return self.count(conn=conn, where=queue.c.delivered_at.is_(None))

    def claim_one(self, owner: str, *, now, conn=None) -> dict | None:
        _check_now(now)
        if not owner:
            raise ValueError("owner_required")
        available = sa.and_(queue.c.delivered_at.is_(None), queue.c.next_attempt_at <= now,
            sa.or_(queue.c.lease_until.is_(None), queue.c.lease_until <= now))
        statement = sa.select(queue).where(available).order_by(
            queue.c.next_attempt_at, queue.c.queued_at, queue.c.event_id
        ).limit(1).with_for_update(skip_locked=True)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
            if row is None:
                return None
            event = self._record(row)
            event.update(lease_token=str(uuid4()), lease_owner=owner,
                         lease_until=(now + timedelta(seconds=120)).isoformat(),
                         attempt_count=int(event.get("attempt_count", 0)) + 1)
            self._write(connection, event)
        return event

    def _owned(self, connection, event_id, token, now):
        statement = sa.select(queue).where(
            queue.c.event_id == event_id, queue.c.lease_token == token,
            queue.c.lease_until > now, queue.c.delivered_at.is_(None)
        ).with_for_update()
        row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)

    def acknowledge(self, event_id, token, message_id, *, now, conn=None) -> bool:
        _check_now(now)
        if not token or not message_id:
            raise ValueError("ack_identity_required")
        with self._tx(conn) as connection:
            event = self._owned(connection, event_id, token, now)
            if event is None:
                return False
            event.update(delivered_message_id=str(message_id), delivered_at=now.isoformat(),
                         blocked=False, last_error=None)
            _clear_lease(event)
            self._write(connection, event)
        return True

    def reschedule(self, event_id, token, *, now, delay_s, error_code, blocked, conn=None) -> bool:
        _check_now(now)
        if not token or delay_s < 0 or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code):
            raise ValueError("invalid_retry_state")
        with self._tx(conn) as connection:
            event = self._owned(connection, event_id, token, now)
            if event is None:
                return False
            changed = blocked and (not event.get("blocked") or event.get("last_error") != error_code)
            event.update(next_attempt_at=(now + timedelta(seconds=delay_s)).isoformat(),
                         last_error=error_code, blocked=bool(blocked))
            _clear_lease(event)
            self._write(connection, event)
        if changed:
            log.error("lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                      event_id, event["kind"], _age(event, now), error_code)
        return True



_repo: NotifyQueueRepository | None = None


def notify_queue_repo() -> NotifyQueueRepository:
    global _repo
    if _repo is None:
        _repo = NotifyQueueRepository()
    return _repo
```

The full canonical record is written under a row lock for every transition. Promoted nulls are also copied to doc, so the generic merge rule cannot revive a stale lease or delivered timestamp. SQL row locking, not Python locks, supplies concurrency control. No acknowledgement or retry can overwrite a new token, an expired token or an already delivered record. Invalid timestamps and database errors propagate to the worker rather than looking like an empty queue.

`drain` is deliberately absent in the final repository. The old loop adapter will be replaced in V197-6, so this intermediate commit must not be deployed. The existing automatic notification paths do not call this repository. Enqueue and claim do not rewrite payload or event identity. A delivered event is never resurrected by duplicate enqueue. V197-2b adds the retention tests.

When passing an external conn to `reschedule`, the caller owns transaction completion and must not interpret the returned boolean as a committed outcome. Production delivery uses internally owned transactions; only those return after commit.

- [ ] **Step 4: Extend the meaningful edge tests and run green.** Add these to the same test file:

```python

def test_expired_token_cannot_complete_without_a_new_claim(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    expiry = NOW + timedelta(seconds=120)
    assert not repo.acknowledge(event["event_id"], claim["lease_token"], "42",
                                now=expiry, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1


def test_blocked_log_only_on_state_or_cause_change(db_conn, caplog):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    with caplog.at_level("ERROR"):
        for offset in (0, 900):
            tick = NOW + timedelta(seconds=offset)
            claim = repo.claim_one("w", now=tick, conn=db_conn)
            assert repo.reschedule(event["event_id"], claim["lease_token"], now=tick,
                delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert len([r for r in caplog.records if "lifecycle blocked" in r.message]) == 1
```

Run `python scripts/dev/testrun.py file tests/db/test_notify_queue_delivery.py`, then `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`. Read actual output: zero failed/xfailed, and no connectivity skips for queue scenarios. Run `python scripts/dev/complexity_gate.py`; functions in this implementation must remain below 15. Do not run a full suite here. V197-6 owns the obsolete destructive-consumer regressions; V197-8 owns integrated crash recovery and final full verification.

- [ ] **Step 5: Commit the tested queue transitions.** After the controller's normal review and freshness checks, stage only `swingbot/core/db/repositories/notify_queue.py` and `tests/db/test_notify_queue_delivery.py`; commit `feat(v197): fence lifecycle delivery claims and acknowledgements`. The plan writer does not execute the commit. Record that deployment remains blocked until all producer/consumer tasks are integrated and consumers are stopped for migration.

### Task V197-2b: Expose backlog truth, acknowledged retention and audited retargeting
**Model:** sonnet — the task extends one repository using the established locked event contract.

**Files:**
- Modify: `swingbot/core/db/repositories/notify_queue.py`
- Modify: `tests/db/test_notify_queue_delivery.py`

**Interfaces:** Consumes V197-2's `_record`, `_write`, `_clear_lease` and fenced queue shape. Creates the index's `health(*, now, conn=None)`, `prune_delivered(*, now, conn=None)` and `retarget(event_id, channel_id, *, actor, reason, now, conn=None)` contracts. V197-6 consumes pruning and V197-7 consumes health. Read schema-change and invoke replicate-prod-db before this task's first DB test.

- [ ] **Step 1: Add failing operational-state tests.** Append to `tests/db/test_notify_queue_delivery.py`, using `NOW`, `fresh` and `record` created in V197-2:

```python
def test_retarget_audits_and_refuses_live_lease_or_delivered(db_conn):
    repo = NotifyQueueRepository()
    event = fresh(channel=None)
    repo.enqueue(event, conn=db_conn)
    assert repo.retarget(event["event_id"], "9", actor="operator", reason="channel repair",
                         now=NOW, conn=db_conn)
    changed = record(repo, db_conn, event)
    assert changed["payload"] == event["payload"]
    assert changed["event_id"] == event["event_id"]
    assert changed["target_channel_id"] == "9"
    assert changed["retarget_history"][0]["from_channel_id"] is None
    assert changed["retarget_history"][0]["actor"] == "operator"
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    assert not repo.retarget(event["event_id"], "10", actor="operator", reason="repair",
                             now=NOW, conn=db_conn)
    repo.acknowledge(event["event_id"], claim["lease_token"], "123", now=NOW, conn=db_conn)
    assert not repo.retarget(event["event_id"], "10", actor="operator", reason="repair",
                             now=NOW, conn=db_conn)


def test_empty_health_is_known_zero_but_age_unknown(db_conn):
    assert NotifyQueueRepository().health(now=NOW, conn=db_conn) == dict(
        pending_count=0, oldest_pending_age_seconds=None, blocked_count=0)


def test_retarget_does_not_clear_malformed_payload_block(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    event.update(blocked=True, last_error="legacy_snapshot_incomplete")
    repo.insert(event, conn=db_conn)  # migration-shaped blocked record
    assert repo.retarget(event["event_id"], "8", actor="operator", reason="repair",
                         now=NOW, conn=db_conn)
    saved = record(repo, db_conn, event)
    assert saved["blocked"] is True
    assert saved["last_error"] == "legacy_snapshot_incomplete"


def test_missing_message_id_is_never_pruned(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    event["delivered_at"] = NOW.isoformat()
    repo.insert(event, conn=db_conn)  # damaged acknowledgement retains evidence
    assert repo.prune_delivered(now=NOW + timedelta(days=8), conn=db_conn) == 0


def test_health_includes_blocked_and_leased_but_excludes_acknowledged(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    assert repo.health(now=NOW, conn=db_conn)["pending_count"] == 1
    repo.reschedule(event["event_id"], claim["lease_token"], now=NOW,
                    delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert repo.health(now=NOW + timedelta(seconds=901), conn=db_conn) == dict(
        pending_count=1, oldest_pending_age_seconds=901.0, blocked_count=1)
    assert repo.prune_delivered(now=NOW + timedelta(days=100), conn=db_conn) == 0
    later = NOW + timedelta(seconds=901)
    claim = repo.claim_one("w", now=later, conn=db_conn)
    repo.acknowledge(event["event_id"], claim["lease_token"], "222", now=later, conn=db_conn)
    assert repo.health(now=later, conn=db_conn) == dict(
        pending_count=0, oldest_pending_age_seconds=None, blocked_count=0)
    assert repo.prune_delivered(now=later + timedelta(days=6), conn=db_conn) == 0
    assert repo.prune_delivered(now=later + timedelta(days=8), conn=db_conn) == 1

```

- [ ] **Step 2: Confirm the narrow red test.** Run `python scripts/dev/testrun.py file tests/db/test_notify_queue_delivery.py`; expect missing health/prune/retarget methods. Connectivity skips do not establish behavior.

- [ ] **Step 3: Implement the operational transitions.** Add the following constant immediately below the repository module's logger:

```python
DESTINATION_ERRORS = frozenset(("destination_unresolved", "channel_unavailable", "permission_denied"))
```

Add these methods inside `NotifyQueueRepository`, after `reschedule` and before the module-level singleton:

```python
    def health(self, *, now, conn=None) -> dict:
        _check_now(now)
        statement = sa.select(sa.func.count(), sa.func.min(queue.c.queued_at),
            sa.func.count().filter(queue.c.doc["blocked"].as_boolean().is_(True))
        ).select_from(queue).where(queue.c.delivered_at.is_(None))
        with self._tx(conn) as connection:
            pending, oldest, blocked = connection.execute(statement).one()
        age = None if oldest is None else max(0.0, (now - oldest).total_seconds())
        return dict(pending_count=int(pending), oldest_pending_age_seconds=age, blocked_count=int(blocked))

    def prune_delivered(self, *, now, conn=None) -> int:
        _check_now(now)
        statement = queue.delete().where(
            queue.c.delivered_at < now - timedelta(days=7),
            queue.c.doc["delivered_message_id"].astext.is_not(None),
            queue.c.doc["delivered_message_id"].astext != "")
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount

    def retarget(self, event_id, channel_id, *, actor, reason, now, conn=None) -> bool:
        _check_now(now)
        channel = str(channel_id)
        if not actor or not reason or not channel.isdecimal() or int(channel) <= 0:
            raise ValueError("invalid_retarget")
        statement = sa.select(queue).where(queue.c.event_id == event_id,
            queue.c.delivered_at.is_(None),
            sa.or_(queue.c.lease_until.is_(None), queue.c.lease_until <= now)
        ).with_for_update()
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
            if row is None:
                return False
            event = self._record(row)
            event.setdefault("retarget_history", []).append(dict(at=now.isoformat(), actor=actor,
                reason=reason, from_channel_id=event.get("target_channel_id"), to_channel_id=channel))
            event.update(target_channel_id=channel, next_attempt_at=now.isoformat())
            _clear_lease(event)
            if event.get("last_error") in DESTINATION_ERRORS:
                event.update(blocked=False, last_error=None)
            self._write(connection, event)
        log.info("lifecycle retarget event=%s channel=%s audit=retarget_history", event_id, channel)
        return True

```

The final health projection counts every pending row, including leased and blocked records. No pending row is expired or deleted by retention. The new endpoint catches query failures as unknown in V197-7. Retarget history is the durable audit and rolls back with the destination; stdout logging omits free-form actor/reason, which may contain sensitive strings. Retarget refuses delivered/live-leased work and never alters payload or event identity. Missing or malformed historical payloads stay blocked after channel repair.

Documented operator retargeting omits conn so success returns only after commit. With a supplied conn, the caller owns commit and the returned boolean is only an accepted in-transaction change. The history record and retarget both disappear if the caller rolls back; no standalone log line is proof of a committed operation.

- [ ] **Step 4: Run narrow verification.** Run `python scripts/dev/testrun.py file tests/db/test_notify_queue_delivery.py` and require zero failures/xfailed with actual DB execution. Run `python scripts/dev/complexity_gate.py`; every changed function must stay below 15. No full suite here. V197-8 verifies integration and records rollout readiness.

- [ ] **Step 5: Commit the verified operational repository features.** After normal controller review and freshness checks, stage the two named paths and commit `feat(v197): expose notification backlog and audited recovery`. The author does not execute this commit or any production action.
