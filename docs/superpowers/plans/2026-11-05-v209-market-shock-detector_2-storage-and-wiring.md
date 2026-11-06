# v209 — Market-shock detector, part 2: storage and the shock pass

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md)
**Index:** [`2026-11-05-v209-market-shock-detector_0-index.md`](2026-11-05-v209-market-shock-detector_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly carries the index's Global Constraints.

This part builds **V209-5, V209-5b, V209-6 and V209-6a**: the `v209_001`
tables and their migration (V209-5), the one-transaction
`MarketShockRepository` and the nightly prune (V209-5b), and the new
`swingbot/core/scanning/shock_scan.py` pass module with its unit tests —
mode, thresholds, gate, VIX and snapshot (V209-6), then the stepped pass,
`run_shock_pass` and `current_label` (V209-6a, split from V209-6 at the
20 KB task cap; `6a` because `V209-6b` was taken). Wiring the pass into
`run_scan` (`scan_run.py`, `loops.py:252`) is V209-6b in part 3.

Decided choices restated so a task read alone is complete:

- Part 1 (V209-1..V209-4) is merged on the worktree branch first:
  `swingbot/core/market/shock.py` exports `LABELS`, `ShockThresholds`,
  `NameRow(ticker, sector, last, prev_close, atr14, is_equity)`,
  `VixTape(level, chg_pct, as_of)`,
  `ShockSnapshot(as_of, session_date, minutes_since_open, names, spy, qqq, vix)`,
  `ShockReading` (`as_row()`, `from_row()`),
  `measure(snapshot, prev, th=ShockThresholds())`, `ShockState` (`as_row()`,
  `from_row(row | None)`) and `step(state, reading, th=ShockThresholds())`;
  `swingbot/config.py` carries `MARKET_SHOCK_MODE` and the 18
  `SHOCK_*`/`RECOVERY_*` attributes, already cast to `float`/`int`.
- `measure` treats `NameRow.last is None` as "no fresh live quote" and
  `atr14 is None` as "fewer than 15 completed bars"; it applies the VIX
  staleness rule itself. `build_snapshot` (V209-6) is where the quote clock,
  the completed-bar rule and the equity test are applied.
- The db layer imports nothing from `swingbot/core/market` (the
  `equity_samples` precedent), so the repository restates the three labels
  and a test pins them equal to `shock.LABELS`.
- The repository stores the whole `ShockReading.as_row()` in each reading's
  `doc` and `{"state": ShockState.as_row()}` in the state row's `doc`: a
  `None` promoted column would otherwise vanish on merge.
- Under `MARKET_SHOCK_MODE=off`: no reading, no state write, no notice, and
  `current_label()` returns `None`. Unknown mode values read as `off`. The
  nightly prune is retention, not detector behaviour: it trims old rows in
  every mode.
- **Stepping gate:** `session.is_nyse_regular_session(now)` — the spec's
  `is_regular_session` window (09:30–16:00 ET, Mon–Fri) narrowed to skip NYSE
  holidays and stop at a half-day close, because on those days the "live"
  quote is the last close and a zero-move reading would walk SHOCK into
  RECOVERY. Never `data.is_us_market_active()` or `bot_core.in_session()`.
- Tests needing Postgres run `/replicate-prod-db` first (one shared
  `swing-db` container, port 56789, `.env` credentials never printed).
  Every new test file sits in an existing `tests/` directory (`tests/db` →
  `storage`, `tests/scanning` → `scanning`, `tests/commands` → `discord`),
  so `tests/suites.toml` is unchanged.
- Every function written or changed stays below cyclomatic complexity 15;
  `daily_recap` gains one `await` line and no branch.
- Do not commit on `main`: each task's commit step runs on the plan's
  worktree branch.

# Phase 3 — persistence

### Task V209-5: `v209_001` tables, `PROMOTION_REASONS`, migration, schema test

**Model:** opus — a new Alembic revision with a foreign key and a single-row check that must match `schema.py` exactly, plus the single-head and downgrade contract.

**Files:**
- Modify: `swingbot/core/db/schema.py` (two `register(...)` tables immediately above `PROMOTION_REASONS`; two `PROMOTION_REASONS` entries at its end, after `"refresher_heartbeat"`)
- Create: `swingbot/core/db/migrations/versions/v209_001_market_shock.py`
- Create: `tests/db/test_v209_market_shock_schema.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (two `NOT_REPOSITORY_BACKED` entries)

**Interfaces:**
- Consumes: `schema.register(table, promoted)`, `schema.standard_columns()`, `schema.promoted_for`, `schema.contract_violations`, `events.TABLE_CHANNELS` (all existing); Alembic head `v197_001`.
- Produces (V209-5b's repository and plan v210 (V210-2/V210-3) rely on these exact names):
  - `schema.market_shock_readings`: `id` BigInteger PK (identity), `as_of` TIMESTAMPTZ NOT NULL (index `market_shock_readings_as_of_idx`), `session_date` Date NOT NULL, `state_after` Text NOT NULL, `breadth_frac`, `breadth_speed`, `spy_atr_move`, `qqq_atr_move`, `vix_level`, `vix_chg_pct`, `vix_off_high_pct` Float(53) NULL, `sectors_down`, `sectors_total`, `n_names` Integer NOT NULL, `insufficient` Boolean NOT NULL, + `doc`, `updated_at`.
  - `schema.market_shock_state`: `id` SmallInteger PK, no autoincrement, `CHECK (id = 1)`; `label` Text NOT NULL, `since` TIMESTAMPTZ NULL, `session_date` Date NULL, `vix_session_high` Float(53) NULL, `last_reading_id` BigInteger NULL FK → `market_shock_readings.id` ON DELETE SET NULL, `last_notice_at` TIMESTAMPTZ NULL, + `doc`, `updated_at`.
  - `schema.PROMOTION_REASONS["market_shock_readings"]`, `["market_shock_state"]`; Alembic revision `v209_001` (sole head, `down_revision = "v197_001"`).
  - Neither table joins `events.TABLE_CHANNELS` (no SSE trigger).

- [ ] **Step 1: Run `/replicate-prod-db`** (the shared `swing-db` must be up; the `tests/db` files skip silently on the default port).

- [ ] **Step 2: Confirm the Alembic head**

Run: `python -m alembic heads`
Expected: `v197_001 (head)`. If another head appears (a revision merged since this plan was written), use that id as `down_revision` in Step 6 and in the test's `"v197_001"` strings, and say so in the commit message.

- [ ] **Step 3: Write the failing schema test**

`tests/db/test_v209_market_shock_schema.py`:

```python
"""v209: revision v209_001 -- market_shock_readings and market_shock_state."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
READING = ("as_of", "session_date", "state_after", "breadth_frac", "breadth_speed",
           "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_off_high_pct",
           "sectors_down", "sectors_total", "n_names", "insufficient")
STATE = ("label", "since", "session_date", "vix_session_high", "last_reading_id",
         "last_notice_at")


def test_both_tables_registered_with_reasons_contract_and_no_sse():
    for name, promoted in (("market_shock_readings", READING), ("market_shock_state", STATE)):
        table = schema.METADATA.tables[name]
        assert schema.promoted_for(name) == promoted
        assert set(schema.PROMOTION_REASONS[name]) == set(promoted)
        assert schema.contract_violations(table) == []
        assert name not in events.TABLE_CHANNELS


def test_reading_columns_and_index():
    t = schema.market_shock_readings
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.BigInteger)
    for name in ("as_of", "session_date", "state_after", "sectors_down", "sectors_total",
                 "n_names", "insufficient"):
        assert t.c[name].nullable is False
    for name in ("breadth_frac", "breadth_speed", "spy_atr_move", "qqq_atr_move",
                 "vix_level", "vix_chg_pct", "vix_off_high_pct"):
        assert t.c[name].nullable is True and isinstance(t.c[name].type, sa.Float)
    assert t.c.as_of.type.timezone is True
    assert [(i.name, [c.name for c in i.columns]) for i in t.indexes] == [
        ("market_shock_readings_as_of_idx", ["as_of"])]


def test_state_is_one_row_pointing_at_its_last_reading():
    t = schema.market_shock_state
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.SmallInteger) and t.c.id.autoincrement is False
    (fk,) = t.c.last_reading_id.foreign_keys
    assert fk.target_fullname == "market_shock_readings.id" and fk.ondelete == "SET NULL"
    assert t.c.label.nullable is False
    checks = {c.name: str(c.sqltext) for c in t.constraints
              if isinstance(c, sa.CheckConstraint)}
    assert checks == {"market_shock_state_single_row": "id = 1"}


def test_v209_001_sits_on_v197_001_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v209_001").down_revision == "v197_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v209_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_both_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, "v197_001")
        remaining = set(sa.inspect(connection).get_table_names())
        assert not {"market_shock_readings", "market_shock_state"} & remaining
        assert "manual_close_notify" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert {"market_shock_readings", "market_shock_state"} <= set(
            sa.inspect(connection).get_table_names())


def test_the_single_row_check_refuses_a_second_state_row(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        nested = connection.begin_nested()
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text(
                "INSERT INTO market_shock_state (id, label) VALUES (2, 'NORMAL')"))
        nested.rollback()
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_v209_market_shock_schema.py`
Expected: FAIL — `KeyError: 'market_shock_readings'` (and `get_revision("v209_001")` raising a resolution error).

- [ ] **Step 5: Add the two tables to `swingbot/core/db/schema.py`**

Insert immediately above `PROMOTION_REASONS: dict[str, dict[str, str]] = {`:

```python
# v209: the market-shock detector (core/market/shock.py). One reading per stepped
# scan pass and the single current-state row, written together in one transaction
# by repositories/market_shock.py. A reading's doc holds its whole as_row() (null
# promoted columns would otherwise vanish on merge). No SSE trigger.
market_shock_readings = register(sa.Table("market_shock_readings", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("session_date", sa.Date, nullable=False),
    sa.Column("state_after", sa.Text, nullable=False),
    sa.Column("breadth_frac", sa.Float(53)),
    sa.Column("breadth_speed", sa.Float(53)),
    sa.Column("spy_atr_move", sa.Float(53)),
    sa.Column("qqq_atr_move", sa.Float(53)),
    sa.Column("vix_level", sa.Float(53)),
    sa.Column("vix_chg_pct", sa.Float(53)),
    sa.Column("vix_off_high_pct", sa.Float(53)),
    sa.Column("sectors_down", sa.Integer, nullable=False),
    sa.Column("sectors_total", sa.Integer, nullable=False),
    sa.Column("n_names", sa.Integer, nullable=False),
    sa.Column("insufficient", sa.Boolean, nullable=False),
    *standard_columns(),
    sa.Index("market_shock_readings_as_of_idx", "as_of")),
    ("as_of", "session_date", "state_after", "breadth_frac", "breadth_speed",
     "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_off_high_pct",
     "sectors_down", "sectors_total", "n_names", "insufficient"))

market_shock_state = register(sa.Table("market_shock_state", METADATA,
    sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("since", sa.TIMESTAMP(timezone=True)),
    sa.Column("session_date", sa.Date),
    sa.Column("vix_session_high", sa.Float(53)),
    sa.Column("last_reading_id", sa.BigInteger,
              sa.ForeignKey("market_shock_readings.id", ondelete="SET NULL")),
    sa.Column("last_notice_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.CheckConstraint("id = 1", name="market_shock_state_single_row")),
    ("label", "since", "session_date", "vix_session_high", "last_reading_id",
     "last_notice_at"))
```

Append inside `PROMOTION_REASONS`, after the `"refresher_heartbeat"` entry:

```python
    "market_shock_readings": {
        "as_of": "market_shock_readings_as_of_idx: latest_reading's sort key and the prune WHERE",
        "session_date": "NOT NULL US session the reading belongs to; per-session SQL review",
        "state_after": "NOT NULL label after this reading; shadow-log cohort queries",
        "breadth_frac": "headline: share of names down >= SHOCK_ATR_K ATR; NULL when none contribute",
        "breadth_speed": "headline: same-session breadth change; NULL across sessions",
        "spy_atr_move": "headline: SPY move in ATRs; NULL without SPY",
        "qqq_atr_move": "headline: QQQ move in ATRs; NULL without QQQ",
        "vix_level": "headline: fresh ^VIX tape level; NULL when missing or stale",
        "vix_chg_pct": "headline: ^VIX day change %; NULL when missing or stale",
        "vix_off_high_pct": "headline: % below the VIX session high; RECOVERY clause review",
        "sectors_down": "NOT NULL sectors whose median move is down >= SHOCK_ATR_K ATR",
        "sectors_total": "NOT NULL sectors with >= 2 contributing names",
        "n_names": "NOT NULL contributing names; the insufficient test",
        "insufficient": "NOT NULL True when n_names < SHOCK_MIN_NAMES (state held)",
    },
    "market_shock_state": {
        "label": "NOT NULL current NORMAL/SHOCK/RECOVERY label read by every plan stamp",
        "since": "time the current label began; the dwell clocks and the admin badge",
        "session_date": "session of the last stepped reading; the overnight-carry test",
        "vix_session_high": "running VIX high this session; the admin badge",
        "last_reading_id": "FK to market_shock_readings.id (SET NULL on prune); never dangles",
        "last_notice_at": "time of the last market_shock notice; the rate limit",
    },
```

- [ ] **Step 6: Create `swingbot/core/db/migrations/versions/v209_001_market_shock.py`**

```python
"""v209: market_shock_readings and market_shock_state -- the shock detector's log
and its single current-state row.

Additive: rollback is this revision's downgrade (drop both tables); leaving them
after a code rollback is also safe (older code never reads them). An image-only
rollback to an older image must run `alembic downgrade v197_001` from this image
first (docs/deploy/DEPLOY_HETZNER.md).

Revision ID: v209_001
Revises: v197_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v209_001"
down_revision = "v197_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)
_HEADLINES = ("breadth_frac", "breadth_speed", "spy_atr_move", "qqq_atr_move",
              "vix_level", "vix_chg_pct", "vix_off_high_pct")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("market_shock_readings",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("as_of", _TS, nullable=False),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("state_after", sa.Text, nullable=False),
        *[sa.Column(name, sa.Float(53)) for name in _HEADLINES],
        sa.Column("sectors_down", sa.Integer, nullable=False),
        sa.Column("sectors_total", sa.Integer, nullable=False),
        sa.Column("n_names", sa.Integer, nullable=False),
        sa.Column("insufficient", sa.Boolean, nullable=False),
        *_standard())
    op.create_index("market_shock_readings_as_of_idx", "market_shock_readings", ["as_of"])
    op.create_table("market_shock_state",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("since", _TS),
        sa.Column("session_date", sa.Date),
        sa.Column("vix_session_high", sa.Float(53)),
        sa.Column("last_reading_id", sa.BigInteger,
                  sa.ForeignKey("market_shock_readings.id", ondelete="SET NULL")),
        sa.Column("last_notice_at", _TS),
        *_standard(),
        sa.CheckConstraint("id = 1", name="market_shock_state_single_row"))


def downgrade() -> None:
    op.drop_table("market_shock_state")
    op.drop_index("market_shock_readings_as_of_idx", table_name="market_shock_readings")
    op.drop_table("market_shock_readings")
```

- [ ] **Step 7: Excuse both tables in `tests/db/test_unknown_field_round_trip.py`**

Its coverage assertion (`set(schema.METADATA.tables) <= set(CASES) | set(NOT_REPOSITORY_BACKED)`)
fails as soon as Step 5 lands. Add to `NOT_REPOSITORY_BACKED`, after the
`"fx_daily_rates"` entry:

```python
    "market_shock_readings": "written only through MarketShockRepository.record with the whole "
                             "reading in doc; its round trip is tests/db/test_market_shock_repository.py",
    "market_shock_state": "single row (id = 1) upserted by MarketShockRepository.record; its "
                          "round trip is tests/db/test_market_shock_repository.py",
```

(`tests/db/test_market_shock_repository.py` is created by V209-5b.)

- [ ] **Step 8: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/db/test_v209_market_shock_schema.py`
`python scripts/dev/testrun.py file tests/db/test_migrations.py` (schema.py and the revision agree)
`python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
`python scripts/dev/testrun.py file tests/db/test_v205_fx_daily_rates.py` (its single-head test still passes with v209_001 stacked on top)
Expected: PASS, and 0 skipped in each (a skip means the shared `swing-db` is unreachable — fix that, never accept it).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v209_001_market_shock.py \
        tests/db/test_v209_market_shock_schema.py tests/db/test_unknown_field_round_trip.py
git commit -m "feat(v209): market_shock_readings and market_shock_state tables (v209_001)"
```

### Task V209-5b: `MarketShockRepository` + nightly `_prune_shock_readings`

**Model:** opus — a one-transaction write that spans two tables and the v197 queue, and the hybrid-doc trap (null promoted columns vanish on merge).

**Files:**
- Create: `swingbot/core/db/repositories/market_shock.py`
- Modify: `swingbot/commands/scanning/loops.py` (one import; `_prune_shock_readings` directly below `_prune_alert_posts`; one `await _prune_shock_readings()` line in `daily_recap`)
- Create: `tests/db/test_market_shock_repository.py`
- Create: `tests/commands/test_shock_readings_prune.py`

**Interfaces:**
- Consumes: `schema.market_shock_readings`, `schema.market_shock_state` (V209-5); `shock.ShockReading`, `shock.ShockState`, `shock.LABELS` (V209-2/V209-3, tests only); `config.SHOCK_READINGS_KEEP_DAYS` (V209-1); existing `NotifyQueueRepository.enqueue(event, *, conn=None)`, `Repository._tx(conn)`, `codec.sanitise_non_finite`, `lifecycle_events.make_event(...)` (tests).
- Produces (V209-6 and plan v210 (V210-2/V210-3) call these exactly):
  - `market_shock.LABELS = ("NORMAL", "SHOCK", "RECOVERY")` (restated, pinned equal to `shock.LABELS`).
  - `market_shock_repo() -> MarketShockRepository` (module singleton).
  - `record(reading: dict, state: dict, *, state_after: str, notice_event: dict | None = None, conn=None) -> int` — one transaction: insert the reading with its full `as_row()` in `doc`, upsert state row 1 with `last_reading_id` and `doc={"state": state}`, and when `notice_event` is given enqueue it via `NotifyQueueRepository().enqueue(event, conn=)` and set `last_notice_at` from its `queued_at`; returns the reading id. An unknown label, or `state["label"] != state_after`, raises `ValueError` before any write.
  - `current_state(*, conn=None) -> dict | None` — keys `label`, `since`, `session_date`, `vix_session_high`, `last_reading_id`, `last_notice_at`, `updated_at`, `doc` (`doc == {"state": ShockState.as_row()}`).
  - `latest_reading(*, conn=None) -> dict | None` — the stored `ShockReading.as_row()` plus `id` and `state_after` (feed it to `ShockReading.from_row`).
  - `prune_before(cutoff: datetime, *, conn=None) -> int` — deletes readings with `as_of < cutoff`; a naive cutoff raises `ValueError`.
  - `loops._prune_shock_readings() -> None` (async, never raises, runs in every mode).

**The hybrid-doc trap.** `codec.merge_doc` drops a promoted column whose value
is `NULL`, so a reading stored the base `Repository` way would come back
without `breadth_speed=None` and `ShockReading.from_row` would raise
(`_from_row` refuses a row missing a field). Each reading row therefore keeps
the **whole** `as_row()` in `doc` and copies the headline fields into columns
for SQL; reads return `doc`.

- [ ] **Step 1: Run `/replicate-prod-db`** (skip if a sibling task in this session already synced the replica; the `tests/db` files skip silently on the default port).

- [ ] **Step 2: Write the failing repository test**

`tests/db/test_market_shock_repository.py`:

```python
"""v209: MarketShockRepository -- reading + state (+ notice) in one transaction."""
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories import market_shock as ms
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import shock

T0 = datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc)
D0 = date(2026, 11, 5)


def _reading(**over) -> dict:
    base = dict(as_of=T0, session_date=D0, minutes_since_open=75.0, breadth_frac=0.45,
                sectors_down=3, sectors_total=5, breadth_speed=None, spy_atr_move=-1.2,
                qqq_atr_move=None, spy_last=495.0, spy_prev_close=500.0,
                spy_session_low=495.0, spy_new_low=False, spy_retrace=0.0, vix_level=None,
                vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None, n_names=40,
                insufficient=False)
    return shock.ShockReading(**{**base, **over}).as_row()


def _state(label="NORMAL", **over) -> dict:
    return shock.ShockState(label=label, session_date=D0, **over).as_row()


def _notice(transition="t-1", at=T0):
    payload = {"ticker": "AAPL", "direction": "bullish", "prior_status": "PENDING",
               "new_status": "CANCELLED", "reason": "probe", "occurred_at": at.isoformat(),
               "plan_id": "P-1"}
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id="123", occurred_at=at.isoformat(), payload=payload)


@pytest.fixture
def repo():
    return ms.MarketShockRepository()


def test_labels_are_restated_from_the_detector():
    assert ms.LABELS == shock.LABELS


def test_the_singleton_is_reused():
    assert ms.market_shock_repo() is ms.market_shock_repo()


def test_empty_tables_read_as_none(repo, db_conn):
    assert repo.current_state(conn=db_conn) is None
    assert repo.latest_reading(conn=db_conn) is None


def test_a_reading_round_trips_with_its_none_fields(repo, db_conn):
    row = _reading()
    reading_id = repo.record(row, _state(), state_after="NORMAL", conn=db_conn)
    got = repo.latest_reading(conn=db_conn)
    assert got["id"] == reading_id and got["state_after"] == "NORMAL"
    assert shock.ShockReading.from_row(got) == shock.ShockReading.from_row(row)
    assert got["breadth_speed"] is None and got["vix_level"] is None


def test_promoted_columns_copy_the_headline_numbers(repo, db_conn):
    reading_id = repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    row = db_conn.execute(sa.select(schema.market_shock_readings).where(
        schema.market_shock_readings.c.id == reading_id)).one()
    assert row.as_of == T0 and row.session_date == D0 and row.state_after == "NORMAL"
    assert row.breadth_frac == 0.45 and row.spy_atr_move == -1.2 and row.vix_level is None
    assert (row.sectors_down, row.sectors_total, row.n_names, row.insufficient) == (3, 5, 40, False)


def test_the_state_row_is_single_and_points_at_the_last_reading(repo, db_conn):
    repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    later = _reading(as_of=T0 + timedelta(minutes=15))
    second = repo.record(later, _state("SHOCK", since=T0), state_after="SHOCK", conn=db_conn)
    assert db_conn.execute(sa.select(sa.func.count()).select_from(
        schema.market_shock_state)).scalar_one() == 1
    state = repo.current_state(conn=db_conn)
    assert state["label"] == "SHOCK" and state["last_reading_id"] == second
    assert state["since"] == T0 and state["session_date"] == D0
    assert shock.ShockState.from_row(state["doc"]["state"]).label == "SHOCK"
    assert repo.latest_reading(conn=db_conn)["id"] == second


def test_a_notice_is_enqueued_in_the_same_transaction_and_stamps_last_notice_at(repo, db_conn):
    repo.record(_reading(), _state(), state_after="NORMAL", notice_event=_notice(),
                conn=db_conn)
    assert repo.current_state(conn=db_conn)["last_notice_at"] == T0
    assert db_conn.execute(sa.select(sa.func.count()).select_from(
        schema.manual_close_notify)).scalar_one() == 1
    repo.record(_reading(), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.current_state(conn=db_conn)["last_notice_at"] == T0     # kept, not cleared


def test_a_failing_enqueue_writes_nothing(repo, store_db):
    bad = {**_notice(), "event_id": "not-the-identity"}
    with pytest.raises(ValueError):
        repo.record(_reading(), _state(), state_after="NORMAL", notice_event=bad)
    for table in (schema.market_shock_readings, schema.market_shock_state,
                  schema.manual_close_notify):
        assert store_db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 0


@pytest.mark.parametrize("label,after", [("CALM", "CALM"), ("NORMAL", "SHOCK")])
def test_an_unknown_or_mismatched_label_is_refused(repo, db_conn, label, after):
    state = {**_state(), "label": label}
    with pytest.raises(ValueError):
        repo.record(_reading(), state, state_after=after, conn=db_conn)
    assert repo.latest_reading(conn=db_conn) is None


def test_latest_reading_orders_by_as_of_not_insert_order(repo, db_conn):
    newer = repo.record(_reading(as_of=T0 + timedelta(minutes=30)), _state(),
                        state_after="NORMAL", conn=db_conn)
    repo.record(_reading(as_of=T0), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.latest_reading(conn=db_conn)["id"] == newer


def test_prune_deletes_older_rows_and_unhooks_the_state(repo, db_conn):
    repo.record(_reading(as_of=T0 - timedelta(days=200)), _state(), state_after="NORMAL",
                conn=db_conn)
    assert repo.prune_before(T0 - timedelta(days=180), conn=db_conn) == 1
    assert repo.latest_reading(conn=db_conn) is None
    assert repo.current_state(conn=db_conn)["last_reading_id"] is None


def test_prune_keeps_rows_at_or_after_the_cutoff(repo, db_conn):
    repo.record(_reading(as_of=T0), _state(), state_after="NORMAL", conn=db_conn)
    assert repo.prune_before(T0, conn=db_conn) == 0
    assert repo.latest_reading(conn=db_conn) is not None


def test_prune_refuses_a_naive_cutoff(repo, db_conn):
    with pytest.raises(ValueError):
        repo.prune_before(datetime(2026, 1, 1), conn=db_conn)
```

- [ ] **Step 3: Write the failing prune test**

`tests/commands/test_shock_readings_prune.py`:

```python
"""v209: daily_recap trims market_shock_readings after alert_posts; never raises."""
import asyncio
import datetime as dt
import inspect
import logging

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod


class _Repo:
    def __init__(self, fail=False):
        self.cutoffs, self.fail = [], fail

    def prune_before(self, cutoff, *, conn=None):
        if self.fail:
            raise RuntimeError("database is having a day")
        self.cutoffs.append(cutoff)
        return 7


def test_prune_uses_the_keep_days_window(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: repo)
    monkeypatch.setattr(config, "SHOCK_READINGS_KEEP_DAYS", 180)
    before = dt.datetime.now(dt.timezone.utc)
    asyncio.run(loops_mod._prune_shock_readings())
    (cutoff,) = repo.cutoffs
    assert cutoff.tzinfo is not None
    assert abs((before - cutoff) - dt.timedelta(days=180)) < dt.timedelta(minutes=1)


def test_prune_runs_under_every_mode(monkeypatch):
    for mode in ("off", "shadow", "live"):
        repo = _Repo()
        monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: repo)
        monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
        asyncio.run(loops_mod._prune_shock_readings())
        assert len(repo.cutoffs) == 1, mode


def test_a_failing_prune_is_logged_and_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: _Repo(fail=True))
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._prune_shock_readings())
    assert any("market_shock_readings" in r.getMessage() for r in caplog.records)


def test_daily_recap_calls_it_right_after_the_alert_posts_prune():
    lines = [ln.strip() for ln in inspect.getsource(loops_mod.daily_recap.coro).splitlines()]
    i = lines.index("await _prune_alert_posts()")
    assert lines[i + 1] == "await _prune_shock_readings()"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_market_shock_repository.py`
Expected: FAIL — `ImportError: cannot import name 'market_shock'`.
Run: `python scripts/dev/testrun.py file tests/commands/test_shock_readings_prune.py`
Expected: FAIL — `AttributeError: ... has no attribute 'market_shock_repo'` / `'_prune_shock_readings'`.

- [ ] **Step 5: Create `swingbot/core/db/repositories/market_shock.py`**

```python
"""v209: the market-shock detector's store.

Writer: core/scanning/shock_scan.run_shock_pass (one call per stepped scan
pass), which hands over ShockReading.as_row() and ShockState.as_row() dicts.
`record` writes the reading, upserts the single state row and, when given,
enqueues the market_shock notice in ONE transaction, so last_reading_id never
dangles and a notice never outlives a rolled-back reading. Readers: the scan's
current_label() and the admin tape. Pruned nightly by loops.daily_recap.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import sanitise_non_finite
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import market_shock_readings as readings
from swingbot.core.db.schema import market_shock_state as state_table

#: Restated from core/market/shock.LABELS so the db layer imports nothing from
#: core/market (tests pin the two equal).
LABELS = ("NORMAL", "SHOCK", "RECOVERY")
STATE_ROW_ID = 1
_READING_COLUMNS = ("as_of", "session_date", "breadth_frac", "breadth_speed",
                    "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct",
                    "vix_off_high_pct", "sectors_down", "sectors_total", "n_names",
                    "insufficient")
_STATE_KEYS = ("label", "since", "session_date", "vix_session_high", "last_reading_id",
               "last_notice_at", "updated_at")


def _instant(value) -> dt.datetime | None:
    """An aware datetime from a datetime or ISO string; naive is refused."""
    if value is None:
        return None
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timezone_required")
    return stamp


def _day(value) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _check_labels(state: dict, state_after: str) -> None:
    if state.get("label") not in LABELS or state_after not in LABELS:
        raise ValueError(f"unknown shock label {state.get('label')!r}/{state_after!r}")
    if state["label"] != state_after:
        raise ValueError("state_after_mismatch")


def _reading_values(reading: dict, state_after: str) -> dict:
    values = {name: reading[name] for name in _READING_COLUMNS}
    values.update(as_of=_instant(values["as_of"]), session_date=_day(values["session_date"]),
                  state_after=state_after, doc=sanitise_non_finite(dict(reading)))
    return values


def _state_values(state: dict, reading_id: int) -> dict:
    return {"id": STATE_ROW_ID, "label": state["label"], "since": _instant(state.get("since")),
            "session_date": _day(state.get("session_date")),
            "vix_session_high": state.get("vix_session_high"), "last_reading_id": reading_id,
            "doc": {"state": sanitise_non_finite(dict(state))},
            "updated_at": sa.func.clock_timestamp()}


class MarketShockRepository(Repository):
    def __init__(self):
        super().__init__(readings, key="id")
        self._queue = NotifyQueueRepository()

    def record(self, reading: dict, state: dict, *, state_after: str,
               notice_event: dict | None = None, conn=None) -> int:
        """Insert `reading`, upsert state row 1 onto it, enqueue `notice_event`."""
        _check_labels(state, state_after)
        with self._tx(conn) as connection:
            reading_id = connection.execute(sa.insert(readings).values(
                **_reading_values(reading, state_after)).returning(readings.c.id)).scalar_one()
            values = _state_values(state, reading_id)
            if notice_event is not None:
                self._queue.enqueue(notice_event, conn=connection)
                values["last_notice_at"] = _instant(notice_event["queued_at"])
            update = {k: v for k, v in values.items() if k != "id"}
            connection.execute(pg_insert(state_table).values(**values).on_conflict_do_update(
                index_elements=[state_table.c.id], set_=update))
        return reading_id

    def current_state(self, *, conn=None) -> dict | None:
        statement = sa.select(state_table).where(state_table.c.id == STATE_ROW_ID)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        mapping = row._mapping
        return {**{key: mapping[key] for key in _STATE_KEYS}, "doc": dict(mapping["doc"] or {})}

    def latest_reading(self, *, conn=None) -> dict | None:
        statement = (sa.select(readings.c.id, readings.c.state_after, readings.c.doc)
                     .order_by(readings.c.as_of.desc(), readings.c.id.desc()).limit(1))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        return {**dict(row.doc or {}), "id": row.id, "state_after": row.state_after}

    def prune_before(self, cutoff: dt.datetime, *, conn=None) -> int:
        statement = sa.delete(readings).where(readings.c.as_of < _instant(cutoff))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount


_repo: MarketShockRepository | None = None


def market_shock_repo() -> MarketShockRepository:
    global _repo
    if _repo is None:
        _repo = MarketShockRepository()
    return _repo
```

`ShockReading.as_row()` already encodes `as_of`/`session_date` as ISO strings
(the tests build rows through it), so `_instant`/`_day` normally see strings;
they also accept `datetime`/`date` so a hand-built dict works. When
`last_notice_at` is absent from `values` (no notice this pass), the upsert's
`set_` leaves the stored value alone — the "kept, not cleared" test pins it.

- [ ] **Step 6: Wire the nightly prune in `swingbot/commands/scanning/loops.py`**

Add the import beside `from swingbot.core.db import write_failure`:

```python
from swingbot.core.db.repositories.market_shock import market_shock_repo
```

Add directly below `_prune_alert_posts`:

```python
async def _prune_shock_readings() -> None:
    """v209: drop market_shock_readings older than SHOCK_READINGS_KEEP_DAYS. Retention,
    not detector behaviour, so it runs in every MARKET_SHOCK_MODE; idempotent when a
    recap is skipped. A failure is logged, never raised."""
    try:
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=int(config.SHOCK_READINGS_KEEP_DAYS)))
        removed = await asyncio.to_thread(market_shock_repo().prune_before, cutoff)
        log.info("daily_recap: pruned %d market_shock_readings row(s)", removed)
    except Exception:
        log.warning("daily_recap: could not prune market_shock_readings", exc_info=True)
```

In `daily_recap`, directly below `await _prune_alert_posts()` (no branch added):

```python
    await _prune_shock_readings()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/db/test_market_shock_repository.py`
`python scripts/dev/testrun.py file tests/commands/test_shock_readings_prune.py`
`python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py` (the other `daily_recap` prune is undisturbed)
Expected: PASS, and 0 skipped in the `tests/db` file (a skip means the shared `swing-db` is unreachable — fix that, never accept it).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`daily_recap` gains no branch; every new function < 15).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/db/repositories/market_shock.py swingbot/commands/scanning/loops.py \
        tests/db/test_market_shock_repository.py tests/commands/test_shock_readings_prune.py
git commit -m "feat(v209): one-transaction MarketShockRepository and nightly readings prune"
```


# Phase 4 — the shock pass

### Task V209-6: `shock_scan.py`: mode, thresholds, gate, VIX, snapshot

**Model:** opus — the regular-hours gate, the live-quote clock and the completed-bar rule decide what the detector sees; a wrong choice silently feeds stale bars into the state machine.

V209-6 was split at the 20 KB task cap: this task builds the pure-ish half
of `shock_scan.py` (no repository, no fetch); **V209-6a** appends the
stepped pass, `run_shock_pass` and `current_label`, and must run straight
after it, before V209-6b.

**Files:**
- Create: `swingbot/core/scanning/shock_scan.py`
- Create: `tests/scanning/test_shock_scan.py`

**Interfaces:**
- Consumes: `shock.ShockThresholds`, `NameRow`, `VixTape`, `ShockSnapshot` (V209-2); `config.MARKET_SHOCK_MODE` and the 17 threshold attrs (V209-1); existing `session.is_nyse_regular_session`, `session.market_today`, `session.now_et`, `session.RTH_OPEN`, `indicators.atr(df, 14)`, `asset_class.classify`, `tape.read_tape`, `tape.TapeEntry`, `swallowed(log, tag, exc, msg, *args, ...)`.
- Produces (V209-6a, V209-6b, V209-8, V209-12 and plan v210 (V210-2/V210-3) call these exactly):
  - `MODES = ("off", "shadow", "live")`; `shock_mode() -> str` (anything else → `"off"`).
  - `THRESHOLD_ATTRS: dict[str, str]` (`ShockThresholds` field → config attr); `thresholds_from_config() -> ShockThresholds`.
  - `read_vix(now: datetime, th: ShockThresholds) -> VixTape` — empty `VixTape(None, None, None)` when the `^VIX` row is missing, a proxy, priceless, older than `th.vix_max_age_s`, or the read fails.
  - `build_snapshot(frames, live_prices, sector_of, *, now, quotes_at, vix, th, spy_ticker, spy_df=None, qqq_ticker="QQQ") -> ShockSnapshot`.
  - `should_step(step_shock: bool, now: datetime) -> bool` (`step_shock and shock_mode() != "off" and session.is_nyse_regular_session(now)`).
  - Private helpers V209-6a reuses: `_number(value) -> float | None`, `_quote(quotes, ticker) -> float | None`, `_fresh_quotes(live_prices, quotes_at, now, th) -> Mapping`.

Rules this task applies (spec § The reading, § Units; index Global Constraints):

- **Last** is the pass's live quote, never the frame's last bar. `live_prices`
  carry no per-quote time, so all quotes share `quotes_at`; when
  `quotes_at is None` or `now − quotes_at > th.quote_max_age_s` every quote
  is absent and those names leave the reading (`NameRow.last = None`).
- **prev_close** is the close of the last **completed** session's bar:
  bar[-2] when bar[-1] is dated today (`session.market_today(now)`, ET), else
  bar[-1]. **atr14** is `indicators.atr(completed, 14)`'s last value, and
  `None` with fewer than 15 completed bars.
- **is_equity** is `asset_class.classify(ticker) == "equity"`; ETFs, indices,
  futures, FX and crypto never count. SPY and QQQ rows are benchmarks
  (`is_equity=False`). The SPY frame is `spy_df` when given, else
  `frames[spy_ticker]`; QQQ only when it is in `frames`.
- **VIX** comes from the tape's `^VIX` row only. A proxy row (another
  symbol's price standing in for `^VIX`) is not a VIX level and reads as
  missing.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_shock_scan.py`:

```python
"""v209: shock_scan -- mode, thresholds, regular-hours gate, VIX, snapshot."""
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.marketdata.shared.tape import TapeEntry
from swingbot.core.scanning import shock_scan

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST (UTC-5)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, 30 min after the open
TH = shock.ShockThresholds(min_names=2)
CLASSES = {"GLD": "etf", "XAUUSD": "fx", "SPY": "etf", "QQQ": "etf"}


def _frame(last_day=D0, n=30, close=100.0, partial=None):
    idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=n)
    df = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                       "Close": close, "Volume": 1e6}, index=idx)
    if partial is not None:
        df.iloc[-1, df.columns.get_loc("Close")] = partial
    return df


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(shock_scan.asset_class, "classify", lambda t: CLASSES.get(t, "equity"))
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})


@pytest.mark.parametrize("raw,mode", [("off", "off"), ("shadow", "shadow"), ("LIVE", "live"),
                                      ("bogus", "off"), ("", "off")])
def test_mode_reads_config_and_anything_unknown_is_off(monkeypatch, raw, mode):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", raw)
    assert shock_scan.shock_mode() == mode


def test_thresholds_map_every_field_and_keep_ints_int(monkeypatch):
    assert set(shock_scan.THRESHOLD_ATTRS) == {f.name for f in fields(shock.ShockThresholds)}
    assert len(set(shock_scan.THRESHOLD_ATTRS.values())) == 17
    monkeypatch.setattr(config, "SHOCK_ATR_K", 1.5)
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 7.0)
    th = shock_scan.thresholds_from_config()
    assert th.atr_k == 1.5 and th.min_names == 7 and isinstance(th.min_names, int)


@pytest.mark.parametrize("step_shock,mode,now,expected", [
    (True, "shadow", NOW, True),
    (True, "live", NOW, True),
    (False, "shadow", NOW, False),                                        # !check, recap, admin
    (True, "off", NOW, False),
    (True, "shadow", datetime(2026, 11, 5, 13, 0, tzinfo=UTC), False),    # 08:00 ET pre-market
    (True, "shadow", datetime(2026, 11, 5, 21, 0, tzinfo=UTC), False),    # 16:00 ET close
    (True, "shadow", datetime(2026, 11, 7, 15, 0, tzinfo=UTC), False),    # Saturday
    (True, "shadow", datetime(2026, 11, 26, 15, 0, tzinfo=UTC), False),   # Thanksgiving
    (True, "shadow", datetime(2026, 11, 27, 17, 0, tzinfo=UTC), True),    # half day, 12:00 ET
    (True, "shadow", datetime(2026, 11, 27, 18, 30, tzinfo=UTC), False),  # after the 13:00 close
])
def test_only_a_flagged_pass_in_the_nyse_regular_session_steps(monkeypatch, step_shock, mode,
                                                                 now, expected):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
    assert shock_scan.should_step(step_shock, now) is expected


def _vix(monkeypatch, entry):
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {"^VIX": entry})


def test_a_fresh_vix_row_is_read(monkeypatch):
    at = NOW - timedelta(seconds=60)
    _vix(monkeypatch, TapeEntry("^VIX", 21.13, 27.21, False, None, at))
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(21.13, 27.21, at)


@pytest.mark.parametrize("entry", [
    None,
    TapeEntry("^VIX", 21.0, 5.0, False, None, NOW - timedelta(seconds=601)),   # stale
    TapeEntry("^VIX", 21.0, 5.0, True, "VIXY", NOW),                           # proxy, not ^VIX
    TapeEntry("^VIX", None, None, False, None, NOW),                           # no price
    TapeEntry("^VIX", 21.0, 5.0, False, None, None),                           # no time
])
def test_missing_stale_or_proxy_vix_is_empty(monkeypatch, entry):
    _vix(monkeypatch, entry)
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(None, None, None)


def test_a_failing_tape_read_is_empty(monkeypatch):
    def boom(symbols):
        raise RuntimeError("layer down")
    monkeypatch.setattr(shock_scan.tape, "read_tape", boom)
    assert shock_scan.read_vix(NOW, TH) == shock.VixTape(None, None, None)


def _snap(frames, quotes, *, quotes_at=NOW, sector_of=None, spy_df=None):
    return shock_scan.build_snapshot(frames, quotes, sector_of or {}, now=NOW,
                                     quotes_at=quotes_at, vix=shock.VixTape(None, None, None),
                                     th=TH, spy_ticker="SPY", spy_df=spy_df)


def test_prev_close_is_the_last_completed_bar_and_last_is_the_live_quote():
    frames = {"AAA": _frame(partial=95.0), "BBB": _frame(last_day=D0 - timedelta(days=1))}
    snap = _snap(frames, {"AAA": 94.0}, sector_of={"AAA": "Tech"})
    aaa, bbb = snap.names
    assert (aaa.prev_close, aaa.last, aaa.sector, aaa.is_equity) == (100.0, 94.0, "Tech", True)
    assert aaa.atr14 == pytest.approx(2.0)
    assert bbb.prev_close == 100.0 and bbb.last is None and bbb.sector is None   # no quote


def test_fewer_than_fifteen_completed_bars_has_no_atr():
    frames = {"AAA": _frame(n=15), "BBB": _frame(last_day=D0 - timedelta(days=1), n=15)}
    aaa, bbb = _snap(frames, {"AAA": 99.0, "BBB": 99.0}).names
    assert aaa.atr14 is None and bbb.atr14 == pytest.approx(2.0)


@pytest.mark.parametrize("quotes_at", [None, NOW - timedelta(seconds=301)])
def test_stale_or_untimed_quotes_drop_every_last(quotes_at):
    snap = _snap({"AAA": _frame()}, {"AAA": 94.0}, quotes_at=quotes_at)
    assert snap.names[0].last is None


@pytest.mark.parametrize("bad", [0.0, -3.0, float("nan"), None, "n/a"])
def test_a_non_positive_or_garbage_quote_is_absent(bad):
    assert _snap({"AAA": _frame()}, {"AAA": bad}).names[0].last is None


def test_empty_frames_are_skipped():
    snap = _snap({"AAA": _frame(), "EMPTY": _frame().iloc[0:0], "NONE": None}, {})
    assert [r.ticker for r in snap.names] == ["AAA"]


def test_non_equities_are_flagged_and_benchmarks_come_from_spy_df_and_frames():
    frames = {"GLD": _frame(), "XAUUSD": _frame(), "SPY": _frame(close=1.0),
              "QQQ": _frame(close=400.0)}
    snap = _snap(frames, {"SPY": 495.0, "QQQ": 396.0}, spy_df=_frame(close=500.0))
    equity = {r.ticker: r.is_equity for r in snap.names}
    assert equity["GLD"] is False and equity["XAUUSD"] is False
    assert (snap.spy.prev_close, snap.spy.last, snap.spy.is_equity) == (500.0, 495.0, False)
    assert (snap.qqq.prev_close, snap.qqq.last) == (400.0, 396.0)
    assert snap.as_of == NOW and snap.session_date == D0
    assert snap.minutes_since_open == pytest.approx(30.0)


def test_the_spy_frame_falls_back_to_frames_and_missing_benchmarks_are_none():
    assert _snap({"SPY": _frame(close=480.0)}, {}).spy.prev_close == 480.0
    snap = _snap({"AAA": _frame()}, {})
    assert snap.spy is None and snap.qqq is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_scan.py`
Expected: FAIL — `ImportError: cannot import name 'shock_scan'`.

- [ ] **Step 3: Create `swingbot/core/scanning/shock_scan.py`**

```python
"""v209: the market-shock pass -- every wiring decision of the detector.

`run_shock_pass` (V209-6a) is called once per scan pass by
scan_run._sync_run_scan (V209-6b). Only the scheduled session scan passes
step_shock=True, and only inside the NYSE regular session (holiday and half-day
aware) does it measure, step and record a reading; every other pass only reads
the stored label for the plan stamp. "Last" is the pass's live quote; prev_close
and ATR14 come from completed daily bars only. A failure never fails the scan.

Spec: docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md
"""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone

import pandas as pd

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import indicators, session, shock
from swingbot.core.marketdata import asset_class
from swingbot.core.marketdata.shared import tape

log = logging.getLogger(__name__)

MODES = ("off", "shadow", "live")
VIX_SYMBOL = "^VIX"
MIN_COMPLETED_BARS = 15
_NO_VIX = shock.VixTape(None, None, None)

#: ShockThresholds field -> config attribute (V209-1). SHOCK_READINGS_KEEP_DAYS is
#: retention, read by loops._prune_shock_readings, not a threshold.
THRESHOLD_ATTRS = {
    "atr_k": "SHOCK_ATR_K", "breadth_enter": "SHOCK_BREADTH_ENTER",
    "sectors_frac": "SHOCK_SECTORS_FRAC", "breadth_fast": "SHOCK_BREADTH_FAST",
    "speed_enter": "SHOCK_SPEED_ENTER", "vix_spike_pct": "SHOCK_VIX_SPIKE_PCT",
    "vix_relief": "SHOCK_VIX_RELIEF", "breadth_reenter": "SHOCK_BREADTH_REENTER",
    "breadth_exit": "SHOCK_BREADTH_EXIT",
    "recovery_vix_off_high_pct": "RECOVERY_VIX_OFF_HIGH_PCT",
    "recovery_spy_retrace": "RECOVERY_SPY_RETRACE", "min_dwell_min": "SHOCK_MIN_DWELL_MIN",
    "recovery_min_dwell_min": "RECOVERY_MIN_DWELL_MIN", "min_names": "SHOCK_MIN_NAMES",
    "vix_max_age_s": "SHOCK_VIX_MAX_AGE_S", "open_settle_min": "SHOCK_OPEN_SETTLE_MIN",
    "quote_max_age_s": "SHOCK_QUOTE_MAX_AGE_S",
}


def shock_mode() -> str:
    mode = str(getattr(config, "MARKET_SHOCK_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"


def thresholds_from_config() -> shock.ShockThresholds:
    defaults = shock.ShockThresholds()
    values = {}
    for name, attr in THRESHOLD_ATTRS.items():
        default = getattr(defaults, name)
        values[name] = type(default)(getattr(config, attr, default))
    return shock.ShockThresholds(**values)


def _number(value) -> float | None:
    """A finite float, or None for None/NaN/inf/garbage."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _aware(stamp: datetime) -> datetime:
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def read_vix(now: datetime, th: shock.ShockThresholds) -> shock.VixTape:
    """The ^VIX tape row (never fetches); empty when missing, a proxy, or stale."""
    try:
        entry = tape.read_tape([VIX_SYMBOL]).get(VIX_SYMBOL)
    except Exception as exc:
        swallowed(log, "scan.shock.vix", exc, "shock: ^VIX tape read failed: %s", exc)
        return _NO_VIX
    if entry is None or entry.is_proxy or _number(entry.price) is None or entry.as_of is None:
        return _NO_VIX
    as_of = _aware(entry.as_of)
    if (now - as_of).total_seconds() > th.vix_max_age_s:
        return _NO_VIX
    return shock.VixTape(_number(entry.price), _number(entry.change_pct), as_of)


def _completed(df: pd.DataFrame | None, today: date) -> pd.DataFrame | None:
    """Completed daily bars: drop bar[-1] when it is dated today (ET)."""
    if df is None or len(df) == 0:
        return None
    return df.iloc[:-1] if pd.Timestamp(df.index[-1]).date() >= today else df


def _name_row(ticker: str, df, last, sector, today: date, is_equity: bool) -> shock.NameRow:
    done = _completed(df, today)
    prev_close = _number(done["Close"].iloc[-1]) if done is not None and len(done) else None
    atr14 = None
    if done is not None and len(done) >= MIN_COMPLETED_BARS:
        atr14 = _number(indicators.atr(done, 14).iloc[-1])
    return shock.NameRow(ticker, sector, last, prev_close, atr14, is_equity)


def _quote(quotes: Mapping[str, float], ticker: str) -> float | None:
    value = _number(quotes.get(ticker))
    return value if value is not None and value > 0 else None


def _fresh_quotes(live_prices, quotes_at, now, th) -> Mapping[str, float]:
    if quotes_at is None or (now - quotes_at).total_seconds() > th.quote_max_age_s:
        return {}
    return live_prices or {}


def _benchmark(ticker: str, df, quotes, today: date) -> shock.NameRow | None:
    if df is None or len(df) == 0:
        return None
    return _name_row(ticker, df, _quote(quotes, ticker), None, today, False)


def _minutes_since_open(now: datetime) -> float:
    et = session.now_et(now)
    opened = datetime.combine(et.date(), session.RTH_OPEN, tzinfo=et.tzinfo)
    return (et - opened).total_seconds() / 60.0


def build_snapshot(frames, live_prices, sector_of, *, now, quotes_at, vix, th, spy_ticker,
                   spy_df=None, qqq_ticker="QQQ") -> shock.ShockSnapshot:
    today = session.market_today(now)
    quotes = _fresh_quotes(live_prices, quotes_at, now, th)
    names = tuple(
        _name_row(t, df, _quote(quotes, t), sector_of.get(t), today,
                  asset_class.classify(t) == "equity")
        for t, df in list(frames.items()) if df is not None and len(df))
    spy_frame = spy_df if spy_df is not None else frames.get(spy_ticker)
    return shock.ShockSnapshot(
        as_of=now, session_date=today, minutes_since_open=_minutes_since_open(now),
        names=names, spy=_benchmark(spy_ticker, spy_frame, quotes, today),
        qqq=_benchmark(qqq_ticker, frames.get(qqq_ticker), quotes, today), vix=vix)


def should_step(step_shock: bool, now: datetime) -> bool:
    return bool(step_shock) and shock_mode() != "off" and session.is_nyse_regular_session(now)
```

`list(frames.items())` copies first: the scan's `fetch.LRUFrames` is an
`OrderedDict` subclass, and iterating a snapshot keeps the pass from
reordering it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_scan.py`
Expected: PASS (no database and no network: the tape read and `classify` are stubbed).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`read_vix` is the largest new function, CC about 8).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/shock_scan.py tests/scanning/test_shock_scan.py
git commit -m "feat(v209): shock_scan snapshot -- regular-hours gate, live-quote clock, VIX tape"
```

### Task V209-6a: `shock_scan.py`: `run_shock_pass`, `current_label`

**Model:** opus — the stepped pass reads the prior reading and state, measures, steps and records in one call, and its failure fallback decides what label every plan of the pass is stamped with.

Second half of V209-6 (split at the 20 KB task cap; the id is `6a` because
`V209-6b` is already the scan-wiring task). Runs straight after V209-6 on the
same branch and before V209-6b.

**Files:**
- Modify: `swingbot/core/scanning/shock_scan.py` (one import; append `_load_prior`, `_stepped_pass`, `run_shock_pass`, `current_label`)
- Create: `tests/scanning/test_shock_pass.py`

**Interfaces:**
- Consumes: from V209-6 `shock_mode()`, `thresholds_from_config()`, `read_vix(now, th)`, `build_snapshot(...)` (it filters `live_prices` for freshness against `quotes_at` itself), `should_step(step_shock, now)`; `shock.NORMAL`, `shock.LABELS`, `ShockReading.from_row`, `ShockState.from_row`, `measure`, `step` (V209-2..V209-4); `market_shock_repo()`, `record(...)`, `current_state()`, `latest_reading()` (V209-5b); existing `config.MARKET_REGIME_TICKER`.
- Produces (V209-6b, V209-8 and plan v210's V210-2/V210-3 call these exactly):
  - `run_shock_pass(*, step_shock: bool, frames, live_prices, sector_of, quotes_at, spy_df: pd.DataFrame | None = None, now: datetime | None = None, repo=None) -> str | None` — the label planning stamps this pass; `None` under `off`; an unstepped pass returns `current_label(repo=repo)` and never writes; a stepped pass runs measure → step → `repo.record(...)` on the quotes it was handed; **no branch ever fetches a quote**; any failure goes through `swallowed(log, "scan.shock.pass", ...)` and returns `current_label(repo=repo)`.
  - `current_label(*, repo=None) -> str | None` — `None` under `off` or when the store cannot be read; `"NORMAL"` before the first state row; else the stored label.
  - Private `_load_prior(repo) -> tuple[ShockReading | None, ShockState]` and `_stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now, repo) -> str`, which plan v210's V210-2b extends to build and pass `notice_event`.

**The pass never fetches (index Global Constraints, "LONG issuing is
unchanged", (b)).** SPY and QQQ quotes arrive in `live_prices` because
V209-6b adds them to the scan's one existing batched live-price fetch on
stepped passes. When SPY (or QQQ) is still absent from the fresh
`live_prices` (a chunk timed out, the provider skipped it),
`build_snapshot`'s `_benchmark` row carries `last=None`, so `measure` leaves
`spy_atr_move`, `spy_last`, `spy_session_low` and `spy_retrace` `None`
(`qqq_atr_move` likewise), exactly as part 1's "no SPY" case already
handles. The reading is still recorded from breadth, sectors and VIX; an
SPY-less reading leaves the RECOVERY SPY-retrace clause unmet (V209-4) and
does not block entry, which rests on breadth and sectors. `shock_scan.py`
imports nothing from `swingbot.core.scanning.fetch`.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_shock_pass.py`:

```python
"""v209: shock_scan.run_shock_pass and current_label -- the stepped pass."""
import inspect
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.scanning import fetch, shock_scan

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST (UTC-5)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, 30 min after the open
PRE_MARKET = datetime(2026, 11, 5, 13, 0, tzinfo=UTC)   # 08:00 ET
SECTORS = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech"}
CRASH_QUOTES = {"AAA": 94.0, "BBB": 94.0, "CCC": 94.0, "SPY": 490.0}   # -3 ATR each


def _frame(close=100.0, partial=None, n=30):
    idx = pd.bdate_range(end=pd.Timestamp(D0), periods=n)
    df = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                       "Close": close, "Volume": 1e6}, index=idx)
    if partial is not None:
        df.iloc[-1, df.columns.get_loc("Close")] = partial
    return df


def _crash_frames():
    return {t: _frame(partial=95.0) for t in SECTORS} | {"SPY": _frame(close=500.0)}


class _Repo:
    def __init__(self, state=None, fail=False):
        self.state, self.latest, self.fail, self.recorded = state, None, fail, []

    def current_state(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.state

    def latest_reading(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.latest

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.recorded.append((reading, state, state_after))
        self.latest = {**reading, "id": len(self.recorded), "state_after": state_after}
        self.state = {"label": state_after, "doc": {"state": state}}
        return len(self.recorded)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 2)
    monkeypatch.setattr(shock_scan.asset_class, "classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})
    # The pass never fetches a quote (LONG issuing unchanged, (b)): any call fails the test.
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))


def _pass(repo, *, step=True, now=NOW, quotes=CRASH_QUOTES, quotes_at=None):
    return shock_scan.run_shock_pass(step_shock=step, frames=_crash_frames(), live_prices=quotes,
                                     sector_of=SECTORS, quotes_at=quotes_at or now, now=now,
                                     repo=repo)


def _without_spy():
    return {k: v for k, v in CRASH_QUOTES.items() if k != "SPY"}


def test_off_returns_none_and_never_touches_the_repo(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "off")
    repo = _Repo(fail=True)
    assert _pass(repo) is None and repo.recorded == []
    assert shock_scan.current_label(repo=repo) is None


@pytest.mark.parametrize("step,now", [(False, NOW), (True, PRE_MARKET)])
def test_an_unstepped_pass_reads_the_label_and_writes_nothing(step, now):
    repo = _Repo(state={"label": "SHOCK", "doc": {}})
    assert _pass(repo, step=step, now=now, quotes=_without_spy()) == "SHOCK"
    assert repo.recorded == []


def test_two_stepped_crash_readings_enter_shock_and_record_each():
    repo = _Repo()
    assert _pass(repo) == "NORMAL"                                  # first qualifying reading
    reading, state, after = repo.recorded[0]
    assert after == "NORMAL" == state["label"]
    assert reading["n_names"] == 3 and reading["breadth_frac"] == pytest.approx(1.0)
    assert (reading["sectors_down"], reading["sectors_total"]) == (1, 1)
    assert reading["spy_last"] == 490.0 and reading["spy_prev_close"] == 500.0
    assert _pass(repo, now=NOW + timedelta(minutes=15)) == "SHOCK"
    assert len(repo.recorded) == 2 and repo.recorded[1][2] == "SHOCK"


def test_the_previous_reading_feeds_breadth_speed_within_the_session():
    repo = _Repo()
    _pass(repo)
    _pass(repo, now=NOW + timedelta(minutes=15))
    assert repo.recorded[0][0]["breadth_speed"] is None
    assert repo.recorded[1][0]["breadth_speed"] == pytest.approx(0.0)


def test_stale_quotes_make_an_insufficient_reading_that_holds_the_state():
    repo = _Repo()
    label = _pass(repo, quotes_at=NOW - timedelta(seconds=301))
    reading = repo.recorded[0][0]
    assert label == "NORMAL" and reading["insufficient"] is True and reading["n_names"] == 0
    assert reading["spy_last"] is None                    # stale SPY is absent too, never re-quoted


def test_a_missing_spy_quote_records_the_reading_from_breadth_and_vix():
    repo = _Repo()
    assert _pass(repo, quotes=_without_spy()) == "NORMAL"
    reading = repo.recorded[0][0]
    assert reading["n_names"] == 3 and reading["breadth_frac"] == pytest.approx(1.0)
    assert reading["insufficient"] is False
    assert (reading["spy_last"], reading["spy_atr_move"], reading["spy_retrace"]) == (None, None, None)


def test_a_missing_spy_quote_still_enters_shock_on_breadth():
    repo = _Repo()
    _pass(repo, quotes=_without_spy())
    assert _pass(repo, now=NOW + timedelta(minutes=15), quotes=_without_spy()) == "SHOCK"


def test_the_spy_df_argument_wins_over_frames():
    repo = _Repo()
    shock_scan.run_shock_pass(step_shock=True, frames=_crash_frames(), live_prices=CRASH_QUOTES,
                              sector_of=SECTORS, quotes_at=NOW, now=NOW, repo=repo,
                              spy_df=_frame(close=520.0))
    assert repo.recorded[0][0]["spy_prev_close"] == 520.0


def test_a_failing_step_falls_back_to_the_stored_label(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError("bad reading")
    monkeypatch.setattr(shock_scan.shock, "measure", boom)
    repo = _Repo(state={"label": "RECOVERY", "doc": {}})
    assert _pass(repo) == "RECOVERY" and repo.recorded == []
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.pass" for r in caplog.records)


def test_a_dead_store_never_fails_the_pass():
    assert _pass(_Repo(fail=True)) is None


BRANCHES = {
    "off": dict(mode="off"),
    "unstepped": dict(step=False),
    "pre_market": dict(now=PRE_MARKET),
    "stepped": dict(),
    "stale_quotes": dict(quotes_at=NOW - timedelta(seconds=301)),
    "spy_missing": dict(quotes=_without_spy()),
    "no_quotes": dict(quotes={}),
    "dead_store": dict(fail=True),
}


@pytest.mark.parametrize("branch", sorted(BRANCHES))
def test_no_branch_of_the_pass_fetches_a_quote(monkeypatch, branch):
    over = dict(BRANCHES[branch])
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", over.pop("mode", "shadow"))
    _pass(_Repo(fail=over.pop("fail", False)), **over)    # the autouse stub fails on any fetch


def test_shock_scan_has_no_quote_fetch_in_its_source():
    src = inspect.getsource(shock_scan)
    assert "_fetch_live_prices(" not in src and "import fetch" not in src
    assert not hasattr(shock_scan, "fetch")


def test_current_label_defaults_to_normal_and_survives_a_db_failure():
    assert shock_scan.current_label(repo=_Repo()) == "NORMAL"
    assert shock_scan.current_label(repo=_Repo(state={"label": "SHOCK", "doc": {}})) == "SHOCK"
    assert shock_scan.current_label(repo=_Repo(state={"label": "CALM", "doc": {}})) is None
    assert shock_scan.current_label(repo=_Repo(fail=True)) is None
```

`test_a_missing_spy_quote_still_enters_shock_on_breadth` relies on part 1's
entry rule resting on breadth and sectors (an SPY move is never required);
if V209-3's `entry_condition` turns out to need one, stop and report rather
than changing either side.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_pass.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.shock_scan' has no attribute 'run_shock_pass'`.

- [ ] **Step 3: Append the stepped pass to `swingbot/core/scanning/shock_scan.py`**

Add to the imports (alphabetical with the existing ones; no `fetch` import):

```python
from swingbot.core.db.repositories.market_shock import market_shock_repo
```

Append at the end of the module:

```python
def _load_prior(repo) -> tuple[shock.ShockReading | None, shock.ShockState]:
    row = repo.latest_reading()
    prev = shock.ShockReading.from_row(row) if row else None
    stored = repo.current_state() or {}
    return prev, shock.ShockState.from_row((stored.get("doc") or {}).get("state"))


def _stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now, repo) -> str:
    """One reading from the quotes the scan already holds. Never fetches: a
    benchmark absent from live_prices gives a NameRow with last=None."""
    th = thresholds_from_config()
    snapshot = build_snapshot(frames, live_prices, sector_of, now=now, quotes_at=quotes_at,
                              vix=read_vix(now, th), th=th,
                              spy_ticker=str(config.MARKET_REGIME_TICKER), spy_df=spy_df)
    prev, state = _load_prior(repo)
    reading = shock.measure(snapshot, prev, th)
    new_state = shock.step(state, reading, th)
    repo.record(reading.as_row(), new_state.as_row(), state_after=new_state.label)
    return new_state.label


def run_shock_pass(*, step_shock, frames, live_prices, sector_of, quotes_at, spy_df=None,
                   now=None, repo=None) -> str | None:
    """The label planning stamps this pass; None under `off`."""
    if shock_mode() == "off":
        return None
    now = now or datetime.now(timezone.utc)
    if not should_step(step_shock, now):
        return current_label(repo=repo)
    try:
        return _stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now,
                             repo or market_shock_repo())
    except Exception as exc:
        swallowed(log, "scan.shock.pass", exc, "shock pass failed; stamping the stored label: %s",
                  exc, exc_info=True)
        return current_label(repo=repo)


def current_label(*, repo=None) -> str | None:
    """The stored label: NORMAL before the first reading, None under `off` or when
    the store cannot be read (the plan then carries no shock_state key)."""
    if shock_mode() == "off":
        return None
    try:
        stored = (repo or market_shock_repo()).current_state()
    except Exception as exc:
        swallowed(log, "scan.shock.label", exc, "shock: stored label unreadable: %s", exc)
        return None
    if not stored:
        return shock.NORMAL
    label = stored.get("label")
    return label if label in shock.LABELS else None
```

A dead store makes `current_label()` return `None`, so that pass's plans
carry no `shock_state` key rather than a guessed `NORMAL`; the
`scan.shock.label` swallow counter records it. Keep every docstring and
comment in this module free of the literals `_fetch_live_prices(` and
`import fetch`, so the source pin stays meaningful.

- [ ] **Step 4: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_pass.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_scan.py` (V209-6's half is undisturbed)
Expected: PASS (no database and no network: every test passes a fake repository, and the quote fetch is stubbed to fail).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (every new function below CC 6).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/shock_scan.py tests/scanning/test_shock_pass.py
git commit -m "feat(v209): run_shock_pass -- stepped measure/step/record, no quote fetch, stored-label fallback"
```
