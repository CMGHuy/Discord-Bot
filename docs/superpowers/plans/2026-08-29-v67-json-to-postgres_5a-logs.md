# v67 — Part 5: Append-only logs (tasks P5-01…P5-04)

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** Part 1 must be merged to
> `main` before this part begins. Tasks P5-05…P5-07 are in
> `2026-08-29-v67-json-to-postgres_5b-snapshots.md`; P5-08…P5-14 are in
> `2026-08-29-v67-json-to-postgres_5c-caches.md`.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`
(section 3, "Append-only logs" and "Derived / cache").

Two groups with genuinely different rules, and the difference is the reason
this part exists as one part rather than two:

- **Append-only logs** — `scan_telemetry`, `shadow_plans`,
  `retrospective_history`. These are evidence. A lost line is a measurement
  that never happened, so they follow the plan's fail-fast rule in full.
- **Derived / cache** — `analytics_snapshot`, `scan_snapshots`,
  `ticker_meta_cache`, `rs_cache`, `fold_trades`. These are regenerable, so
  their **reads** may fall back to recomputation. Their writes may not fall
  back silently; a write that cannot land is still logged.

`_5a` covers the schema and the two append-only logs; `_5b` covers the
retrospective history and the two snapshot stores; `_5c` covers the caches, the
importers, retention and the verification.

## Alembic revision ids

Part 5 owns `p5_*`, hanging off `p1_003`. Parts 2–5 run concurrently, so this
chain does **not** hang off any of theirs; Part 6's merge revision resolves the
multiple heads.

| Revision | Tables |
|---|---|
| `p5_001` | `scan_telemetry`, `shadow_plans` |
| `p5_002` | `retrospective_history`, `analytics_snapshot`, `scan_snapshots` |
| `p5_003` | `ticker_meta_cache`, `rs_cache`, `fold_trades` |
| `p5_004` | NOTIFY triggers for the tables above |

## Parallelisation

- **Sequential: P5-01 before everything** — the only task that edits
  `schema.py`, for the same reason as P2-01 and P3-01.
- **Group 5a (parallel):** telemetry (P5-02), shadow log (P5-03…P5-04),
  retrospective (P5-05). Disjoint modules: `core/scanning/telemetry.py`,
  `core/backtesting/shadow_log.py` + `scripts/reports/shadow_parity_report.py`,
  `core/tracking/retrospective.py`.
- **Group 5b (parallel):** snapshots (P5-06, P5-07 — **sequential with each
  other only if a task touches both**; they are separate modules, so they are
  genuinely parallel), meta cache (P5-08), rs cache (P5-09), fold trades
  (P5-10).
- **Sequential: P5-11 onward after every store above** — the importers,
  the parity registrations and the retention policy all enumerate the stores.

## Part 5 exit criteria

1. Every log and cache store reads and writes Postgres at the `db` stage.
2. `shadow_parity_report.py` produces the same report from rows as from the
   JSONL.
3. The `analytics` SSE channel has a table behind it (it had none after Part 3).
4. Append-only retention is bounded without a rotation slot that discards data
   silently.
5. `python scripts/dev/testrun.py fast` is green.
6. `DB_STORES` is empty in every committed file.

---

# Phase 5 — Append-only logs and caches

### Task P5-01: Every Part 5 table

**Files:**
- Modify: `swingbot/core/db/schema.py`
- Modify: `swingbot/core/db/events.py`
- Create: `swingbot/core/db/migrations/versions/p5_001_logs.py`
- Create: `swingbot/core/db/migrations/versions/p5_002_snapshots.py`
- Create: `swingbot/core/db/migrations/versions/p5_003_caches.py`
- Create: `swingbot/core/db/migrations/versions/p5_004_notify_triggers.py`
- Modify: `tests/db/conftest.py`
- Test: `tests/db/test_part5_schema.py`

**Interfaces:**
- Consumes: `register`, `standard_columns` (P1-04); `trigger_ddl` (P1-12).
- Produces the tables `scan_telemetry`, `shadow_plans`,
  `retrospective_history`, `analytics_snapshot`, `scan_snapshots`,
  `ticker_meta_cache`, `rs_cache`, `fold_trades`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_part5_schema.py`:

```python
"""Shapes later Part 5 tasks depend on."""
import pytest
import sqlalchemy as sa

from swingbot.core.db import events, schema

PART5_TABLES = ("scan_telemetry", "shadow_plans", "retrospective_history",
                "analytics_snapshot", "scan_snapshots", "ticker_meta_cache",
                "rs_cache", "fold_trades")


@pytest.mark.parametrize("name", PART5_TABLES)
def test_table_exists_and_is_registered(name):
    assert name in schema.METADATA.tables
    assert name in schema.PROMOTED


def test_scan_telemetry_is_append_only_shaped(db_conn):
    """No natural key: two scans with identical stats are two rows."""
    for _ in range(2):
        db_conn.execute(sa.insert(schema.scan_telemetry).values(
            at="2026-01-02T15:00:00+00:00", duration_s=12.5, doc={}))
    n = db_conn.execute(sa.select(sa.func.count())
                        .select_from(schema.scan_telemetry)).scalar_one()
    assert n == 2


def test_shadow_plans_is_append_only_shaped(db_conn):
    for _ in range(2):
        db_conn.execute(sa.insert(schema.shadow_plans).values(
            ts_scan="2026-01-02T15:00:00+00:00", ticker="AAPL",
            horizon="2w", doc={}))
    n = db_conn.execute(sa.select(sa.func.count())
                        .select_from(schema.shadow_plans)).scalar_one()
    assert n == 2


def test_retrospective_history_is_one_row_per_day(db_conn):
    db_conn.execute(sa.insert(schema.retrospective_history).values(
        day="2026-01-02", doc={}))
    with pytest.raises(sa.exc.IntegrityError):
        db_conn.execute(sa.insert(schema.retrospective_history).values(
            day="2026-01-02", doc={}))


def test_analytics_snapshot_is_a_singleton(db_conn):
    db_conn.execute(sa.insert(schema.analytics_snapshot).values(
        key="current", built_at="2026-01-02T15:00:00+00:00", doc={}))
    with pytest.raises(sa.exc.IntegrityError):
        db_conn.execute(sa.insert(schema.analytics_snapshot).values(
            key="current", built_at="2026-01-02T16:00:00+00:00", doc={}))


def test_fold_trades_is_keyed_by_strategy(db_conn):
    db_conn.execute(sa.insert(schema.fold_trades).values(
        strategy="RSI", doc={"outcomes": []}))
    with pytest.raises(sa.exc.IntegrityError):
        db_conn.execute(sa.insert(schema.fold_trades).values(
            strategy="RSI", doc={}))


def test_the_analytics_channel_finally_has_a_table():
    """After Part 3, `analytics` was the one SSE concern nothing raised."""
    assert events.TABLE_CHANNELS["analytics_snapshot"] == "analytics"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_part5_schema.py -q
```

Expected: `AttributeError: module 'swingbot.core.db.schema' has no attribute 'scan_telemetry'`.

- [ ] **Step 3: Declare the tables**

Append to `swingbot/core/db/schema.py`:

```python
# One row per scan. Append-only: no natural key, because two scans with
# identical stats are two scans. `duration_s` is promoted because
# scan_slowdown() reads it and nothing else, on every scan.
scan_telemetry = register(
    sa.Table(
        "scan_telemetry", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("duration_s", sa.Numeric),
        *standard_columns(),
        sa.Index("scan_telemetry_at_idx", sa.text("at DESC")),
    ),
    ("at", "duration_s"),
)

# One row per shadow-mode scan item. shadow_parity_report.py reads this for
# the v2 cutover decision, and E40's forward-gate cohorts filter on
# component/variant -- promoted for that reason, not on principle.
shadow_plans = register(
    sa.Table(
        "shadow_plans", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ts_scan", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("component", sa.Text),
        sa.Column("variant", sa.Text),
        *standard_columns(),
        sa.Index("shadow_plans_ts_idx", sa.text("ts_scan DESC")),
        sa.Index("shadow_plans_cohort_idx", "component", "variant"),
        sa.Index("shadow_plans_doc_gin", "doc", postgresql_using="gin"),
    ),
    ("ts_scan", "ticker", "horizon", "component", "variant"),
)

# One row per trading day. The escalation ladder asks "has this happened
# before", which is a lookup by day.
retrospective_history = register(
    sa.Table(
        "retrospective_history", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("day", sa.Text, nullable=False, unique=True),
        *standard_columns(),
        sa.Index("retrospective_history_day_idx", sa.text("day DESC")),
    ),
    ("day",),
)

# Singleton, key='current'. The pre-built blob every UI reads instead of
# recomputing. Regenerable from closed trades, so reads may fall back.
analytics_snapshot = register(
    sa.Table(
        "analytics_snapshot", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        sa.Column("built_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
    ),
    ("key", "built_at"),
)

# ticker|horizon|direction -> the last presented scenario, for the diff line.
scan_snapshots = register(
    sa.Table(
        "scan_snapshots", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        *standard_columns(),
    ),
    ("key",),
)

# Two dicts in one file today (currency_symbols, company_names). One row per
# symbol here, because the file was rewritten whole on every new lookup.
ticker_meta_cache = register(
    sa.Table(
        "ticker_meta_cache", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, nullable=False, unique=True),
        *standard_columns(),
    ),
    ("symbol",),
)

# Universe relative-strength, one row per symbol plus an as_of stamp.
rs_cache = register(
    sa.Table(
        "rs_cache", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, nullable=False, unique=True),
        sa.Column("as_of", sa.Text, nullable=False),
        sa.Column("rel", sa.Numeric),
        *standard_columns(),
    ),
    ("symbol", "as_of", "rel"),
)

# E39's per-strategy fold outcomes. One file per strategy today; one row here.
fold_trades = register(
    sa.Table(
        "fold_trades", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("strategy", sa.Text, nullable=False, unique=True),
        *standard_columns(),
    ),
    ("strategy",),
)
```

Add to `swingbot/core/db/events.py`'s `TABLE_CHANNELS`:

```python
    "scan_telemetry": "scan",
    "scan_snapshots": "scan",
    "analytics_snapshot": "analytics",
    # shadow_plans, retrospective_history and the three caches raise nothing:
    # no admin panel renders them live, and a NOTIFY per shadow line would be
    # one per scan item.
```

That comment is load-bearing — `test_every_mapped_table_exists` in Part 3 only
checks the tables that *are* mapped, so a table's absence from the map has to
be a stated decision rather than an oversight.

- [ ] **Step 4: Write the four migrations**

Same shape as `p2_001`: explicit `op.create_table` per table with a local
`_standard()` helper, chained `p1_003 → p5_001 → p5_002 → p5_003 → p5_004`.
`p5_004` installs triggers for the three mapped tables only, using the same
`existing = set(sa.inspect(conn).get_table_names())` guard Part 3's `p3_007`
uses — Parts 3 and 5 may land in either order.

Add the three mapped tables to the trigger loop in `tests/db/conftest.py`.

- [ ] **Step 5: Migrate and run**

```bash
alembic upgrade head
alembic downgrade p1_003 && alembic upgrade head
python scripts/dev/testrun.py file tests/db/test_part5_schema.py
python scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/events.py \
        swingbot/core/db/migrations/versions/p5_00*.py \
        tests/db/conftest.py tests/db/test_part5_schema.py
git commit -m "feat(v67): declare every Part 5 table"
```

---

### Task P5-02: Scan telemetry

`telemetry.py` is 40 lines and three functions. `recent_telemetry` reads the
whole file into memory to take the last N lines, which is fine at today's size
and stops being fine eventually; as a table it is an `ORDER BY at DESC LIMIT n`.

**Files:**
- Create: `swingbot/core/db/repositories/telemetry.py`
- Modify: `swingbot/core/scanning/telemetry.py`
- Test: `tests/scanning/test_telemetry_db.py`

**Interfaces:**
- Consumes: `scan_telemetry` (P5-01), `stages`.
- Produces: `TelemetryRepository` with `append(row)`, `recent(n=50)`,
  `prune(before_ts)`; `telemetry_repo()`.

**The contract that must not move:** `recent_telemetry(n)` returns rows
**oldest-first**, because `scan_slowdown()` does `rows[:-1]` for the prior
window and `rows[-1]` for the latest. Returning newest-first would invert the
comparison and silently make the slowdown alarm fire on fast scans.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_telemetry_db.py`:

```python
"""Scan telemetry, and the ordering scan_slowdown depends on."""
import os

import pytest

from swingbot import config
from swingbot.core.scanning import telemetry


@pytest.fixture(params=["", "telemetry:dual", "telemetry:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH",
                        os.path.join(tmp_path, "scan_telemetry.jsonl"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def _log(duration, **extra):
    telemetry.log_scan_telemetry({"duration_s": duration, "tickers": 100,
                                  "errors": 0, **extra})


def test_an_empty_store_reads_as_an_empty_list(any_stage):
    assert telemetry.recent_telemetry() == []


def test_append_then_read(any_stage):
    _log(12.5)
    rows = telemetry.recent_telemetry()
    assert len(rows) == 1
    assert rows[0]["duration_s"] == 12.5
    assert "at" in rows[0]


def test_rows_are_oldest_first(any_stage):
    """scan_slowdown does rows[:-1] for the prior window and rows[-1] for the
    latest. Newest-first would invert the comparison silently."""
    for i in range(3):
        _log(float(i))
    assert [r["duration_s"] for r in telemetry.recent_telemetry()] == [0.0, 1.0, 2.0]


def test_n_takes_the_most_recent(any_stage):
    for i in range(5):
        _log(float(i))
    assert [r["duration_s"] for r in telemetry.recent_telemetry(2)] == [3.0, 4.0]


def test_arbitrary_stats_survive(any_stage):
    _log(1.0, signals=7, alerts=2, open_heat=3.5)
    row = telemetry.recent_telemetry()[0]
    assert row["signals"] == 7 and row["open_heat"] == 3.5


def test_scan_slowdown_is_false_below_the_sample_floor(any_stage):
    for i in range(4):
        _log(1.0)
    assert telemetry.scan_slowdown() is False


def test_scan_slowdown_fires_on_a_real_slowdown(any_stage):
    for _ in range(10):
        _log(10.0)
    _log(30.0)
    assert telemetry.scan_slowdown() is True


def test_scan_slowdown_is_quiet_on_noise(any_stage):
    for _ in range(10):
        _log(10.0)
    _log(12.0)
    assert telemetry.scan_slowdown() is False


def test_no_jsonl_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "telemetry:db":
        pytest.skip("file absence is only asserted at the db stage")
    _log(1.0)
    assert not os.path.exists(os.path.join(tmp_path, "scan_telemetry.jsonl"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scanning/test_telemetry_db.py -q
```

Expected: the `db` parametrisations fail.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/telemetry.py`:

```python
"""Append-only scan telemetry."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import scan_telemetry


class TelemetryRepository(Repository):
    def __init__(self):
        super().__init__(scan_telemetry, key="id")

    def append(self, row: dict, *, conn=None) -> dict:
        return self.insert(row, conn=conn)

    def recent(self, n: int = 50, *, conn=None) -> list[dict]:
        """The last n rows, OLDEST FIRST.

        The ordering is the contract, not a detail: scan_slowdown() compares
        rows[-1] against the median of rows[:-1], so a newest-first list would
        make the alarm fire on fast scans and stay quiet on slow ones.
        """
        newest = self.list_all(conn=conn,
                               order_by=scan_telemetry.c.at.desc(), limit=n)
        return list(reversed(newest))

    def prune(self, before_ts: str, *, conn=None) -> int:
        stmt = sa.delete(scan_telemetry).where(scan_telemetry.c.at < before_ts)
        with self._tx(conn) as c:
            return c.execute(stmt).rowcount


_repo: TelemetryRepository | None = None


def telemetry_repo() -> TelemetryRepository:
    global _repo
    if _repo is None:
        _repo = TelemetryRepository()
    return _repo
```

- [ ] **Step 4: Branch the two I/O functions**

```python
def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    """Task E82: one record per scan (at, duration_s, tickers, errors,
    data_skips, signals, alerts, open_heat) -- cheap append-only history for
    scan_slowdown()'s alarm and the admin risk page's duration sparkline.

    An explicit `path` always means the file, so the tests that pass one stay
    isolated from the database exactly as they were from data/.
    """
    import datetime as dt
    from swingbot.core.db import stages
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **stats}
    if path is not None or stages.writes_json("telemetry"):
        with open(path or TELEMETRY_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(row) + "\n")
    if path is None and stages.writes_db("telemetry"):
        from swingbot.core.db.repositories.telemetry import telemetry_repo
        telemetry_repo().append(row)


def recent_telemetry(n: int = 50, path: str | None = None) -> list:
    from swingbot.core.db import stages
    if path is None and stages.reads_db("telemetry"):
        from swingbot.core.db.repositories.telemetry import telemetry_repo
        return telemetry_repo().recent(n)
    try:
        with open(path or TELEMETRY_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [_json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []
```

`scan_slowdown` needs no edit — it goes through `recent_telemetry`.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_telemetry_db.py
python scripts/dev/testrun.py file tests/scanning/test_telemetry.py
```

Expected: `0 failed` for both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/telemetry.py \
        swingbot/core/scanning/telemetry.py tests/scanning/test_telemetry_db.py
git commit -m "feat(v67): move scan telemetry to postgres"
```

---

### Task P5-03: The shadow-plan log

`shadow_log.append` (`shadow_log.py:19`) rotates at 50 MB into a **single** slot
(`path + ".1"`), which means the second rotation destroys the first archive.
Rows have no such limit, and P5-13 replaces the rotation with a real retention
policy.

**Files:**
- Create: `swingbot/core/db/repositories/shadow.py`
- Modify: `swingbot/core/backtesting/shadow_log.py` (`append` `:19`,
  `backfill_forward_returns` `:64`)
- Test: `tests/backtesting/test_shadow_log_db.py`

**Interfaces:**
- Consumes: `shadow_plans` (P5-01), `stages`, `plan_to_dict` (existing).
- Produces: `ShadowRepository` with `append(record)`, `all_lines()`,
  `cohort(component, variant)`, `pending_forward_returns()`,
  `set_forward_return(row_id, value)`; `shadow_repo()`.

**The untagged-line rule survives.** `component`/`variant` are written only when
supplied, because `shadow_parity_report.py` already reads this log for the v2
cutover decision and an untagged line has to stay what it was. As columns they
are simply NULL when absent, and `codec.merge_doc` omits a NULL promoted column
— so an untagged row round-trips to a dict with no `component` key, exactly like
an untagged JSONL line.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_shadow_log_db.py`:

```python
"""The shadow log: append-only evidence for the v2 cutover decision."""
import os

import pytest

from swingbot import config
from swingbot.core.backtesting import shadow_log


@pytest.fixture(params=["", "shadow:dual", "shadow:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


class _Plan:
    """Minimal stand-in matching what append() reads off a plan."""
    ticker = "AAPL"
    horizon_key = "2w"
    plan_id = "P1"
    strategy = "RSI"
    status = "pending"
    created_at = "2026-01-02T15:00:00+00:00"


@pytest.fixture(autouse=True)
def _stub_plan_to_dict(monkeypatch):
    monkeypatch.setattr(shadow_log, "plan_to_dict",
                        lambda p: {"plan_id": p.plan_id, "ticker": p.ticker})


LEGACY = {"entry": 100.0, "stop": 95.0, "target": 110.0}


def _read(stage):
    from swingbot.core.db.repositories.shadow import ShadowRepository
    if stage == "shadow:db":
        return ShadowRepository().all_lines()
    import json
    path = shadow_log._default_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_append_then_read(any_stage):
    shadow_log.append(_Plan(), LEGACY)
    rows = _read(any_stage)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["legacy"] == LEGACY
    assert "ts_scan" in rows[0]


def test_an_untagged_line_has_no_component_key(any_stage):
    """shadow_parity_report.py already reads this log; an untagged line has to
    stay byte-for-byte what it was."""
    shadow_log.append(_Plan(), LEGACY)
    assert "component" not in _read(any_stage)[0]
    assert "fwd_return_10d" not in _read(any_stage)[0]


def test_a_tagged_line_carries_its_cohort(any_stage):
    shadow_log.append(_Plan(), LEGACY, component="entry", variant="b")
    row = _read(any_stage)[0]
    assert row["component"] == "entry" and row["variant"] == "b"
    assert row["fwd_return_10d"] is None


def test_two_appends_are_two_lines(any_stage):
    shadow_log.append(_Plan(), LEGACY)
    shadow_log.append(_Plan(), LEGACY)
    assert len(_read(any_stage)) == 2


def test_cohort_filters_at_the_db_stage(any_stage):
    if any_stage != "shadow:db":
        pytest.skip("cohort filtering is a db-stage query")
    from swingbot.core.db.repositories.shadow import ShadowRepository
    shadow_log.append(_Plan(), LEGACY, component="entry", variant="a")
    shadow_log.append(_Plan(), LEGACY, component="entry", variant="b")
    shadow_log.append(_Plan(), LEGACY)
    rows = ShadowRepository().cohort("entry", "b")
    assert len(rows) == 1 and rows[0]["variant"] == "b"


def test_pending_forward_returns_excludes_untagged_and_resolved(any_stage):
    if any_stage != "shadow:db":
        pytest.skip("db-stage query")
    from swingbot.core.db.repositories.shadow import ShadowRepository
    repo = ShadowRepository()
    shadow_log.append(_Plan(), LEGACY)                                  # untagged
    shadow_log.append(_Plan(), LEGACY, component="entry", variant="a")  # pending
    pending = repo.pending_forward_returns()
    assert len(pending) == 1
    repo.set_forward_return(pending[0]["id"], 0.031)
    assert repo.pending_forward_returns() == []


def test_no_jsonl_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "shadow:db":
        pytest.skip("file absence is only asserted at the db stage")
    shadow_log.append(_Plan(), LEGACY)
    assert not os.path.exists(os.path.join(tmp_path, "shadow_plans.jsonl"))
```

`pending_forward_returns` returns rows carrying an `id`, which the codec
normally strips as an infrastructure column. Have the repository re-attach it
explicitly for this one method — a caller that must update a specific row needs
its identity, and `ts_scan` is not unique.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/backtesting/test_shadow_log_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/shadow.py`:

```python
"""Shadow-mode plan log.

Append-only evidence: shadow_parity_report.py reads it for the v2 cutover
decision, and E40's forward-gate reads the tagged subset. The file version
rotated at 50 MB into a SINGLE slot, so a second rotation destroyed the first
archive. Rows have no such limit; P5-13 adds a real retention policy.
"""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import shadow_plans


class ShadowRepository(Repository):
    def __init__(self):
        super().__init__(shadow_plans, key="id")

    def append(self, record: dict, *, conn=None) -> dict:
        return self.insert(record, conn=conn)

    def all_lines(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, order_by=shadow_plans.c.id.asc())

    def cohort(self, component: str, variant: str, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, where=sa.and_(
            shadow_plans.c.component == component,
            shadow_plans.c.variant == variant,
        ), order_by=shadow_plans.c.id.asc())

    def pending_forward_returns(self, *, conn=None) -> list[dict]:
        """Tagged rows whose 10-bar window has not been resolved yet.

        These carry their `id`, which merge_doc normally strips: a caller that
        must update one specific row needs its identity, and ts_scan is not
        unique.
        """
        stmt = (sa.select(shadow_plans)
                .where(sa.and_(shadow_plans.c.component.isnot(None),
                               shadow_plans.c.doc["fwd_return_10d"].astext.is_(None)))
                .order_by(shadow_plans.c.id.asc()))
        with self._tx(conn) as c:
            rows = c.execute(stmt).all()
        return [{**self._row_to_record(r), "id": r._mapping["id"]} for r in rows]

    def set_forward_return(self, row_id: int, value: float | None, *,
                           conn=None) -> None:
        stmt = (sa.update(shadow_plans)
                .where(shadow_plans.c.id == row_id)
                .values(doc=shadow_plans.c.doc.op("||")(
                    sa.cast(sa.literal({"fwd_return_10d": value}, sa.JSON),
                            sa.dialects.postgresql.JSONB))))
        with self._tx(conn) as c:
            c.execute(stmt)


_repo: ShadowRepository | None = None


def shadow_repo() -> ShadowRepository:
    global _repo
    if _repo is None:
        _repo = ShadowRepository()
    return _repo
```

- [ ] **Step 4: Branch `append` and `backfill_forward_returns`**

In `shadow_log.py`, build the record once — above the branch, as P2-18 does with
`created_at` — then write it per stage. The rotation block runs only on the file
side. `backfill_forward_returns` gains a db branch iterating
`shadow_repo().pending_forward_returns()` and calling `set_forward_return`,
replacing its rewrite-the-whole-file pass.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_shadow_log_db.py
python scripts/dev/testrun.py file tests/backtesting/test_shadow_log.py
```

Expected: `0 failed` for both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/shadow.py \
        swingbot/core/backtesting/shadow_log.py \
        tests/backtesting/test_shadow_log_db.py
git commit -m "feat(v67): move the shadow-plan log to postgres"
```

---

### Task P5-04: shadow_parity_report reads rows

`scripts/reports/shadow_parity_report.py` is the script the v2 cutover decision
is made on. Its output must be identical from either backend, and this task is
where that is proven rather than assumed.

**Files:**
- Modify: `scripts/reports/shadow_parity_report.py`
- Test: `tests/scripts/test_shadow_parity_report_db.py`

**Interfaces:**
- Consumes: `shadow_repo` (P5-03), `stages`.
- Produces: `load_lines(path=None) -> list[dict]` — extracted from wherever the
  script currently opens the file, so there is one read seam to branch.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_shadow_parity_report_db.py`:

```python
"""Same evidence, same report, either backend.

This script is what a cutover decision gets made on. A report that differs by
backend is a decision made on the storage layer.
"""
import json
import os

import pytest

from swingbot import config
from scripts.reports import shadow_parity_report as report


def _line(i, component=None, variant=None):
    row = {"ts_scan": f"2026-01-{i + 1:02d}T15:00:00+00:00",
           "ticker": ["AAPL", "MSFT"][i % 2], "horizon": "2w",
           "plan": {"plan_id": f"P{i}", "entry": 100.0 + i, "stop_loss": 95.0},
           "legacy": {"entry": 100.5 + i, "stop": 95.5}}
    if component is not None:
        row.update(component=component, variant=variant, fwd_return_10d=0.01 * i)
    return row


@pytest.fixture
def both(tmp_path, monkeypatch, db_committed):
    lines = [_line(i) for i in range(6)] + \
            [_line(i, "entry", "ab"[i % 2]) for i in range(6, 12)]
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    path = os.path.join(tmp_path, "shadow_plans.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row) + "\n")
    from swingbot.core.db.repositories.shadow import ShadowRepository
    repo = ShadowRepository()
    for row in lines:
        repo.append(row)
    return lines


def test_load_lines_returns_the_same_records(both, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    from_file = report.load_lines()
    monkeypatch.setattr(config, "DB_STORES", "shadow:db")
    from_db = report.load_lines()
    assert len(from_db) == len(from_file)
    for a, b in zip(from_file, from_db):
        assert a["ticker"] == b["ticker"]
        assert a["plan"] == b["plan"]
        assert a["legacy"] == b["legacy"]


def test_an_untagged_line_stays_untagged_from_the_database(both, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "shadow:db")
    assert "component" not in report.load_lines()[0]


def test_an_explicit_path_still_reads_that_file(both, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_STORES", "shadow:db")
    path = os.path.join(tmp_path, "other.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(_line(99)) + "\n")
    assert len(report.load_lines(path)) == 1


def test_a_torn_trailing_line_is_skipped_not_fatal(both, monkeypatch, tmp_path):
    """A crash mid-append leaves exactly this. The file path must survive it,
    and the db path cannot produce it."""
    monkeypatch.setattr(config, "DB_STORES", "")
    with open(os.path.join(tmp_path, "shadow_plans.jsonl"), "a",
              encoding="utf-8") as f:
        f.write('{"ts_scan": "2026-01-')
    assert len(report.load_lines()) == 12
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_shadow_parity_report_db.py -q
```

Expected: `AttributeError: module ... has no attribute 'load_lines'`.

- [ ] **Step 3: Extract and branch the read seam**

In `scripts/reports/shadow_parity_report.py`, replace the inline file read with:

```python
def load_lines(path: str | None = None) -> list[dict]:
    """Every shadow line, oldest first.

    One read seam so the storage branch lives in one place. A torn trailing
    line is skipped rather than fatal: the file is append-only and a crash
    mid-write leaves exactly that. The database path cannot produce one.
    """
    from swingbot.core.db import stages
    if path is None and stages.reads_db("shadow"):
        from swingbot.core.db.repositories.shadow import shadow_repo
        return shadow_repo().all_lines()
    target = path or os.path.join(config.DATA_DIR, "shadow_plans.jsonl")
    if not os.path.exists(target):
        return []
    out = []
    with open(target, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
```

Every existing read in the script routes through it. Confirm with
`grep -n "shadow_plans.jsonl\|json.loads" scripts/reports/shadow_parity_report.py`
that no other read remains.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_shadow_parity_report_db.py
python scripts/dev/testrun.py file tests/scripts/test_shadow_parity_report.py
python scripts/reports/shadow_parity_report.py
```

Expected: `0 failed`, and the script running against local data without error.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/shadow_parity_report.py \
        tests/scripts/test_shadow_parity_report_db.py
git commit -m "feat(v67): read the shadow parity report from either backend"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_5b-snapshots.md`**
(P5-05…P5-07): retrospective history, the analytics snapshot, and the scan
presentation snapshots.
