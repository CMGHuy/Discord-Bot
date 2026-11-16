# v208 — Benchmark tab, part 1: equity storage (V208-1..V208-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (its *Amendment after the code brief* overrides earlier spec text)
**Index:** [`2026-11-05-v208-benchmark-tab_0-index.md`](2026-11-05-v208-benchmark-tab_0-index.md): Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there and bind every task below.

Scope of this part: the `v208_001` revision (two `equity_samples` columns, the
`benchmark_bars` and `benchmark_refresh` tables), their repositories, the
`EquitySnapshot.open_notional` / `session_trade_pnl` seam with the recorder
writing the column, and the `--open-notional` backfill that fills history.

Order: V208-1 → (V208-2 ‖ V208-3) → V208-4. Every task here reaches Postgres:
run `/replicate-prod-db` once before the first test run of the session (shared
`swing-db` container, port 56789; never print `.env` values).

Conventions used in every task:
- `merge_doc` (`swingbot/core/db/codec.py:61`) **omits NULL promoted columns on
  read**, so a NULL `open_notional` is an *absent* key in `list_rows()` output:
  assert with `row.get("open_notional") is None`, never `row["open_notional"]`.
- `split_doc` leaves a missing promoted key absent, so a write that omits
  `open_notional` leaves the column at SQL NULL.
- Narrow runs only (`python scripts/dev/testrun.py file <test>`); no task runs
  the full suite.

# Phase 1 — Storage

### Task V208-1: `v208_001`: `open_notional` columns, `benchmark_bars`, `benchmark_refresh`

**Model:** opus — an Alembic revision plus the promoted-column contract on a production table (migrations are opus in the rubric).

**Files:**
- Modify: `swingbot/core/db/schema.py` (`equity_samples` at :278-292, `PROMOTION_REASONS["equity_samples"]` at :534-543; new tables after `fx_daily_rates` :323-332)
- Create: `swingbot/core/db/migrations/versions/v208_001_benchmark.py`
- Modify: `swingbot/core/db/repositories/equity_samples.py` (`_prepared` :44-55, new method after `update_realized`)
- Create: `tests/db/test_v208_benchmark_schema.py`
- Modify: `tests/db/test_equity_samples_repository.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (`NOT_REPOSITORY_BACKED` :104-110)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `schema.contract_violations`, `schema.promoted_for`, `events.TABLE_CHANNELS`; `round_money` (equity_samples repo).
- Produces:
  - `equity_samples.open_notional` `Float(53)` NULL, `equity_samples.open_notional_approx` `Boolean` NULL, both appended to the promoted tuple after `"backfill_run"`.
  - `schema.benchmark_bars`: PK (`symbol` Text, `session` Date); `close` Float(53) NULL; `adj_close` Float(53) NULL; `day_pct` Float(53) NULL; `source_symbol` Text NOT NULL; `final` Boolean NOT NULL; `as_of` TIMESTAMPTZ NOT NULL; `*standard_columns()`. Promoted: `("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")`. No index beyond the PK, no SSE channel.
  - `schema.benchmark_refresh`: `symbol` Text PK; `full_refreshed_on` Date NOT NULL; `*standard_columns()`. Promoted: `("symbol", "full_refreshed_on")`. No SSE channel.
  - `EquitySampleRepository.update_open_notional(sample_id: int, open_notional: Decimal | None, approx: bool | None, conn=None) -> None`.
  - `_prepared(row)` rounds `open_notional` once (2 dp, `round_money`) when present and not None; an absent key stays absent.

- [ ] **Step 1: Write the failing schema/migration test** — `tests/db/test_v208_benchmark_schema.py`

```python
"""v208: revision v208_001 -- equity_samples.open_notional/_approx, benchmark_bars,
benchmark_refresh; every new column promoted (schema-evolution.md)."""
import pathlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
BARS = ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")
REFRESH = ("symbol", "full_refreshed_on")
EQUITY_NEW = ("open_notional", "open_notional_approx")


def _cfg():
    return Config(str(REPO / "alembic.ini"))


def test_equity_samples_promotes_both_new_columns_with_reasons():
    promoted = schema.promoted_for("equity_samples")
    assert promoted[-2:] == EQUITY_NEW
    assert set(EQUITY_NEW) <= set(schema.PROMOTION_REASONS["equity_samples"])
    table = schema.equity_samples
    assert isinstance(table.c.open_notional.type, sa.Float) and table.c.open_notional.nullable
    assert isinstance(table.c.open_notional_approx.type, sa.Boolean)
    assert table.c.open_notional_approx.nullable
    assert schema.contract_violations(table) == []


def test_benchmark_bars_is_registered_with_a_composite_key_and_reasons():
    table = schema.METADATA.tables["benchmark_bars"]
    assert schema.promoted_for("benchmark_bars") == BARS
    assert set(schema.PROMOTION_REASONS["benchmark_bars"]) == set(BARS)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["symbol", "session"]
    assert {n for n in BARS if table.c[n].nullable} == {"close", "adj_close", "day_pct"}
    assert isinstance(table.c.session.type, sa.Date)
    assert isinstance(table.c.final.type, sa.Boolean)
    assert table.c.as_of.type.timezone is True
    assert all(isinstance(table.c[n].type, sa.Float) for n in ("close", "adj_close", "day_pct"))
    assert list(table.indexes) == []
    assert "benchmark_bars" not in events.TABLE_CHANNELS


def test_benchmark_refresh_is_one_date_per_symbol():
    table = schema.METADATA.tables["benchmark_refresh"]
    assert schema.promoted_for("benchmark_refresh") == REFRESH
    assert set(schema.PROMOTION_REASONS["benchmark_refresh"]) == set(REFRESH)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["symbol"]
    assert table.c.full_refreshed_on.nullable is False
    assert isinstance(table.c.full_refreshed_on.type, sa.Date)
    assert "benchmark_refresh" not in events.TABLE_CHANNELS


def test_v208_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(_cfg())
    revision = scripts.get_revision("v208_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v208_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_upgrade_leaves_existing_rows_null_and_downgrade_removes_everything(db_engine_empty):
    cfg = _cfg()
    prior = ScriptDirectory.from_config(cfg).get_revision("v208_001").down_revision
    at = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, prior)
        connection.execute(sa.text(
            "INSERT INTO equity_samples (at, realized_balance, unrealized_pnl, equity, open_n, "
            "skipped_n, source, kind) VALUES (:at, 10000, 0, 10000, 0, 0, 'live', 'point')"),
            {"at": at})
        upgrade(cfg, "v208_001")
        row = connection.execute(sa.text(
            "SELECT open_notional, open_notional_approx FROM equity_samples")).one()
        assert (row.open_notional, row.open_notional_approx) == (None, None)
        assert {"benchmark_bars", "benchmark_refresh"} <= set(sa.inspect(connection).get_table_names())
        downgrade(cfg, prior)
        inspector = sa.inspect(connection)
        assert not {"benchmark_bars", "benchmark_refresh"} & set(inspector.get_table_names())
        assert not set(EQUITY_NEW) & {c["name"] for c in inspector.get_columns("equity_samples")}
        upgrade(cfg, "head")
```

- [ ] **Step 2: Write the failing repository tests** — append to `tests/db/test_equity_samples_repository.py` (reuses its `repo` fixture, `_row`, `OPEN`, `CLOSE`); add `import sqlalchemy as sa` and `from swingbot.core.db.schema import equity_samples` to the imports at the top.

```python
def _columns(db_conn, sample_id):
    table = equity_samples
    return db_conn.execute(sa.select(table.c.open_notional, table.c.open_notional_approx,
                                     table.c.doc).where(table.c.id == sample_id)).one()


def test_open_notional_is_rounded_once_and_lands_in_its_own_column(repo, db_conn):
    sample_id = repo.insert_sample({**_row(OPEN), "open_notional": Decimal("2040.005"),
                                    "open_notional_approx": False}, conn=db_conn)
    stored = _columns(db_conn, sample_id)
    assert (stored.open_notional, stored.open_notional_approx) == (2040.01, False)
    assert "open_notional" not in stored.doc and "open_notional_approx" not in stored.doc
    (row,) = repo.list_rows(conn=db_conn)
    assert (row["open_notional"], row["open_notional_approx"]) == (2040.01, False)


def test_a_row_written_without_open_notional_reads_back_without_it(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    stored = _columns(db_conn, sample_id)
    assert (stored.open_notional, stored.open_notional_approx) == (None, None)
    (row,) = repo.list_rows(conn=db_conn)
    assert row.get("open_notional") is None and row.get("open_notional_approx") is None


def test_update_open_notional_touches_only_the_two_new_columns(repo, db_conn):
    sample_id = repo.insert_sample(_row(CLOSE), conn=db_conn)
    (before,) = repo.list_rows(conn=db_conn)
    repo.update_open_notional(sample_id, Decimal("975.004"), True, conn=db_conn)
    (after,) = repo.list_rows(conn=db_conn)
    assert (after["open_notional"], after["open_notional_approx"]) == (975.0, True)
    keep = ("realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n",
            "source", "kind", "at")
    assert {k: after[k] for k in keep} == {k: before[k] for k in keep}
    repo.update_open_notional(sample_id, None, None, conn=db_conn)       # the rollback shape
    (reset,) = repo.list_rows(conn=db_conn)
    assert reset.get("open_notional") is None and reset.get("open_notional_approx") is None
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v208_benchmark_schema.py`, then `python scripts/dev/testrun.py file tests/db/test_equity_samples_repository.py`
Expected: FAIL — `KeyError: 'benchmark_bars'`, no revision `v208_001`; the repo tests fail on the missing column and `AttributeError: ... update_open_notional`.

- [ ] **Step 4: Add the columns and tables to `swingbot/core/db/schema.py`**

In `equity_samples`, after `sa.Column("backfill_run", sa.Text),` add `sa.Column("open_notional", sa.Float(53)),` and `sa.Column("open_notional_approx", sa.Boolean),`; the promoted tuple ends `..., "backfill_run", "open_notional", "open_notional_approx")`. Add one line to the comment above the table: `v208: open_notional (sum of |open shares x price|, unconverted like unrealized_pnl) feeds the Benchmark tab's exposure and deployed return; open_notional_approx marks values re-derived from daily closes by the backfill.`

`PROMOTION_REASONS["equity_samples"]` gains:
```python
        "open_notional": "the Benchmark tab's exposure and deployed denominator read it per row; "
                         "NULL on rows written before v208 until the backfill fills them",
        "open_notional_approx": "the backfill rollback's WHERE (IS TRUE); recorder rows carry FALSE",
```

After `fx_daily_rates`, add:
```python
# v208: one row per benchmark symbol per NYSE session, written by the refresher's
# `benchmarks` step (swingbot/refresher/benchmarks.py); day_pct is the only return ever
# read. A proxy-sourced row (source_symbol != symbol) leaves close/adj_close NULL.
# benchmark_refresh holds, per symbol, the session day its full adjusted history was
# last rewritten (the once-per-session-day guard). No SSE trigger on either.
benchmark_bars = register(sa.Table("benchmark_bars", METADATA,
    sa.Column("symbol", sa.Text, primary_key=True),
    sa.Column("session", sa.Date, primary_key=True),
    sa.Column("close", sa.Float(53)),
    sa.Column("adj_close", sa.Float(53)),
    sa.Column("day_pct", sa.Float(53)),
    sa.Column("source_symbol", sa.Text, nullable=False),
    sa.Column("final", sa.Boolean, nullable=False),
    sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
    *standard_columns()),
    ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of"))

benchmark_refresh = register(sa.Table("benchmark_refresh", METADATA,
    sa.Column("symbol", sa.Text, primary_key=True),
    sa.Column("full_refreshed_on", sa.Date, nullable=False),
    *standard_columns()),
    ("symbol", "full_refreshed_on"))
```

`PROMOTION_REASONS` gains, after `"fx_daily_rates"`:
```python
    "benchmark_bars": {
        "symbol": "primary key (symbol, session): one bar per benchmark per NYSE session",
        "session": "primary key; the range WHERE and the alignment join to equity sessions",
        "close": "price-index level (^IXIC, ^DJI); NULL on proxy-sourced rows",
        "adj_close": "total-return level (SPY, QQQ); rewritten by the daily full refresh",
        "day_pct": "the only return the tab reads; never recomputed across rows",
        "source_symbol": "NOT NULL; differs from symbol on a proxy day, flagged in the tooltip",
        "final": "NOT NULL; false rows feed only the Today card, never the series or stats",
        "as_of": "NOT NULL time the row was written; the Today card's as-of stamp",
    },
    "benchmark_refresh": {
        "symbol": "primary key: one guard row per benchmark symbol",
        "full_refreshed_on": "NOT NULL; the full history rewrite runs when this is before the "
                             "last completed NYSE session",
    },
```

- [ ] **Step 5: Write the revision** — `swingbot/core/db/migrations/versions/v208_001_benchmark.py`

Run `python -m alembic heads` first and set `down_revision` (and the `Revises:` docstring line) to the head it prints: `v205_001` today, `v207_001` if v207 merged first.

```python
"""v208: equity_samples.open_notional/_approx, benchmark_bars, benchmark_refresh.

Additive: two nullable columns (existing rows stay NULL, no read-time upcasting)
and two new tables. Rollback is this revision's downgrade; leaving them after a
code rollback is also safe (the old code never reads them).

Revision ID: v208_001
Revises: v205_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v208_001"
down_revision = "v205_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.add_column("equity_samples", sa.Column("open_notional", sa.Float(53)))
    op.add_column("equity_samples", sa.Column("open_notional_approx", sa.Boolean))
    op.create_table("benchmark_bars",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("session", sa.Date, primary_key=True),
        sa.Column("close", sa.Float(53)),
        sa.Column("adj_close", sa.Float(53)),
        sa.Column("day_pct", sa.Float(53)),
        sa.Column("source_symbol", sa.Text, nullable=False),
        sa.Column("final", sa.Boolean, nullable=False),
        sa.Column("as_of", _TS, nullable=False),
        *_standard())
    op.create_table("benchmark_refresh",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("full_refreshed_on", sa.Date, nullable=False),
        *_standard())


def downgrade() -> None:
    op.drop_table("benchmark_refresh")
    op.drop_table("benchmark_bars")
    op.drop_column("equity_samples", "open_notional_approx")
    op.drop_column("equity_samples", "open_notional")
```

- [ ] **Step 6: Extend the repository** — `swingbot/core/db/repositories/equity_samples.py`

- `_prepared`: after the `MONEY_FIELDS` loop, when `row.get("open_notional") is not None` set `prepared["open_notional"] = round_money(row["open_notional"])`. An absent key stays absent, an explicit `None` stays `None`. `MONEY_FIELDS` itself is unchanged (its fields are required; this one is optional).
- After `update_realized`, modelled on it: `update_open_notional(self, sample_id: int, open_notional: Decimal | None, approx: bool | None, conn=None) -> None` — one `sa.update(...).where(self.table.c.id == sample_id)` setting `open_notional` (`round_money(value)` or `None`), `open_notional_approx=approx`, `updated_at=sa.func.clock_timestamp()`. Docstring: `"Rewrite one row's open_notional and its approx flag; every other column is kept (the v208 backfill and its rollback)."`
- Module docstring: add `update_open_notional` to the backfill script's writer list.

- [ ] **Step 7: Excuse the new tables in the round-trip test** — `tests/db/test_unknown_field_round_trip.py`, `NOT_REPOSITORY_BACKED` gains:

```python
    "benchmark_bars": "v208: repository lands in V208-2, which moves this entry to CASES",
    "benchmark_refresh": "v208: repository lands in V208-2, which moves this entry to CASES",
```

- [ ] **Step 8: Run the tests to verify they pass**

Run, one at a time:
`python scripts/dev/testrun.py file tests/db/test_v208_benchmark_schema.py`
`python scripts/dev/testrun.py file tests/db/test_equity_samples_repository.py`
`python scripts/dev/testrun.py file tests/db/test_migrations.py`
`python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
`python scripts/dev/testrun.py file tests/db/test_schema_contract.py`
Expected: all PASS (`test_migrations_produce_exactly_the_declared_schema` proves the revision and `schema.py` agree). `python -m alembic heads` prints exactly one line: `v208_001 (head)`.

- [ ] **Step 9: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v208_001_benchmark.py \
        swingbot/core/db/repositories/equity_samples.py tests/db/test_v208_benchmark_schema.py \
        tests/db/test_equity_samples_repository.py tests/db/test_unknown_field_round_trip.py
git commit -m "feat(v208): v208_001 -- equity_samples.open_notional, benchmark_bars, benchmark_refresh"
```

### Task V208-2: `BenchmarkBarRepository` + `BenchmarkRefreshRepository`

**Model:** sonnet — a repository over a composite key, modelled on `FxDailyRateRepository`, fully specified by its tests.

**Files:**
- Create: `swingbot/core/db/repositories/benchmark_bars.py`
- Create: `tests/db/test_benchmark_bars_repository.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (move the two V208-1 entries from `NOT_REPOSITORY_BACKED` to `CASES`)

**Interfaces:**
- Consumes (V208-1): `schema.benchmark_bars`, `schema.benchmark_refresh`; `Repository` (`swingbot/core/db/repositories/base.py`: `_tx`, `_values`, `_record`, `get`, `upsert`, `list_all`).
- Produces (consumed by V208-6 and V208-11):
  - `BAR_KEYS = ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")`
  - `class BenchmarkBarRepository(Repository)` (`key="session"`, like `FxDailyRateRepository` uses `"day"`; the base single-key methods are never used except the overridden `upsert`):
    - `upsert_bars(rows: list[dict], conn=None) -> int` — insert, or on conflict (`symbol`, `session`) overwrite **every** column (NULLs included, so a proxy day clears an older `close`) and `doc`; `updated_at = clock_timestamp()`. Duplicate keys inside one batch: the last row wins (Postgres refuses to update one row twice in a statement). Returns the number of distinct keys written; `[]` writes nothing and returns 0.
    - `upsert(record: dict, *, conn=None) -> dict` — `upsert_bars([record])`, then the stored row in the `list_range` shape (lets the round-trip test drive it).
    - `list_range(symbols: Sequence[str], start: date, end: date, conn=None) -> list[dict]` — rows of `symbols` with `start <= session <= end` (both inclusive), ordered by `symbol`, `session`. **Every `BAR_KEYS` key is present** (NULL columns as `None`, unlike `merge_doc`), plus any unknown `doc` fields; `session` a `date`, `as_of` tz-aware UTC. Empty `symbols` returns `[]` without a query.
    - `last_session(symbol: str, conn=None) -> date | None` — the newest session of `symbol` with `final = true`; an intraday `final = false` row never counts. None when the symbol has no final row.
  - `benchmark_bars_repo() -> BenchmarkBarRepository` (process singleton)
  - `class BenchmarkRefreshRepository(Repository)` (`key="symbol"`):
    - `full_refreshed_on(symbol: str, conn=None) -> date | None`
    - `mark_full_refresh(symbol: str, day: date, conn=None) -> None` — upsert; overwrites the stored date.
  - `benchmark_refresh_repo() -> BenchmarkRefreshRepository` (process singleton)
  - Write validation (`ValueError`): `symbol` or `source_symbol` empty/missing, `final` not a `bool`, `as_of` naive or missing, `session` missing. `session` and `as_of` accept ISO strings (`date.fromisoformat` / `datetime.fromisoformat`).

- [ ] **Step 1: Write the failing tests** — `tests/db/test_benchmark_bars_repository.py`

```python
"""v208: benchmark_bars (one bar per symbol per NYSE session, day_pct the only
return read) and benchmark_refresh (the once-per-session-day full-refresh guard)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.db.repositories import benchmark_bars as bb

AS_OF = datetime(2026, 11, 4, 21, 5, tzinfo=timezone.utc)
MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)


def _bar(symbol, session, *, close=None, adj=None, pct=None, source=None, final=True, at=AS_OF):
    return {"symbol": symbol, "session": session, "close": close, "adj_close": adj,
            "day_pct": pct, "source_symbol": source or symbol, "final": final, "as_of": at}


@pytest.fixture
def bars():
    return bb.BenchmarkBarRepository()


def test_upsert_then_list_range_returns_every_key_nulls_included(bars, db_conn):
    assert bars.upsert_bars([_bar("SPY", TUE, close=580.0, adj=579.1, pct=0.004),
                             _bar("^DJI", TUE, pct=-0.002, source="DIA")], conn=db_conn) == 2
    rows = bars.list_range(["SPY", "^DJI"], MON, WED, conn=db_conn)
    assert [(r["symbol"], r["session"]) for r in rows] == [("SPY", TUE), ("^DJI", TUE)]
    assert all(set(bb.BAR_KEYS) <= set(r) for r in rows)
    dji = rows[1]
    assert (dji["close"], dji["adj_close"], dji["day_pct"], dji["source_symbol"]) == (
        None, None, -0.002, "DIA")
    assert rows[0]["as_of"] == AS_OF and rows[0]["as_of"].utcoffset() == timedelta(0)


def test_a_proxy_day_overwrites_a_level_day_and_clears_its_close(bars, db_conn):
    bars.upsert_bars([_bar("^IXIC", WED, close=18500.0, pct=0.01, final=False)], conn=db_conn)
    bars.upsert_bars([_bar("^IXIC", WED, pct=0.009, source="ONEQ")], conn=db_conn)
    (row,) = bars.list_range(["^IXIC"], WED, WED, conn=db_conn)
    assert (row["close"], row["day_pct"], row["source_symbol"], row["final"]) == (
        None, 0.009, "ONEQ", True)


def test_a_duplicate_key_inside_one_batch_keeps_the_last_row(bars, db_conn):
    written = bars.upsert_bars([_bar("SPY", WED, adj=1.0, pct=0.001, final=False),
                                _bar("SPY", WED, adj=2.0, pct=0.002)], conn=db_conn)
    assert written == 1
    (row,) = bars.list_range(["SPY"], WED, WED, conn=db_conn)
    assert (row["adj_close"], row["day_pct"], row["final"]) == (2.0, 0.002, True)


def test_nothing_to_write_writes_nothing(bars, db_conn):
    assert bars.upsert_bars([], conn=db_conn) == 0
    assert bars.list_range([], MON, WED, conn=db_conn) == []


def test_list_range_is_inclusive_filtered_and_ordered(bars, db_conn):
    bars.upsert_bars([_bar("QQQ", WED, pct=0.0), _bar("QQQ", MON, pct=0.0),
                      _bar("SPY", TUE, pct=0.0), _bar("QQQ", TUE, pct=0.0)], conn=db_conn)
    rows = bars.list_range(["QQQ"], MON, TUE, conn=db_conn)
    assert [(r["symbol"], r["session"]) for r in rows] == [("QQQ", MON), ("QQQ", TUE)]


def test_last_session_counts_final_rows_of_that_symbol_only(bars, db_conn):
    assert bars.last_session("SPY", conn=db_conn) is None
    bars.upsert_bars([_bar("SPY", TUE, pct=0.0), _bar("SPY", WED, pct=0.0, final=False),
                      _bar("QQQ", WED, pct=0.0)], conn=db_conn)
    assert bars.last_session("SPY", conn=db_conn) == TUE


def test_iso_strings_are_accepted_for_session_and_as_of(bars, db_conn):
    bars.upsert_bars([_bar("SPY", "2026-11-04", pct=0.0, at="2026-11-04T21:05:00+00:00")],
                     conn=db_conn)
    (row,) = bars.list_range(["SPY"], WED, WED, conn=db_conn)
    assert (row["session"], row["as_of"]) == (WED, AS_OF)


@pytest.mark.parametrize("bad", [{"source_symbol": ""}, {"symbol": None}, {"final": "yes"},
                                 {"as_of": datetime(2026, 11, 4, 21, 5)}, {"session": None}])
def test_a_bad_row_is_refused(bars, db_conn, bad):
    with pytest.raises(ValueError):
        bars.upsert_bars([{**_bar("SPY", WED, pct=0.0), **bad}], conn=db_conn)


def test_upsert_returns_the_stored_row(bars, db_conn):
    stored = bars.upsert({**_bar("SPY", WED, pct=0.003), "note": "x"}, conn=db_conn)
    assert (stored["session"], stored["day_pct"], stored["note"]) == (WED, 0.003, "x")


def test_the_refresh_guard_is_one_overwritable_date_per_symbol(db_conn):
    guard = bb.BenchmarkRefreshRepository()
    assert guard.full_refreshed_on("SPY", conn=db_conn) is None
    guard.mark_full_refresh("SPY", TUE, conn=db_conn)
    guard.mark_full_refresh("SPY", WED, conn=db_conn)
    assert guard.full_refreshed_on("SPY", conn=db_conn) == WED
    assert guard.full_refreshed_on("QQQ", conn=db_conn) is None


def test_the_accessors_are_singletons():
    assert bb.benchmark_bars_repo() is bb.benchmark_bars_repo()
    assert bb.benchmark_refresh_repo() is bb.benchmark_refresh_repo()
    assert isinstance(bb.benchmark_refresh_repo(), bb.BenchmarkRefreshRepository)
```

- [ ] **Step 2: Move the round-trip entries** — `tests/db/test_unknown_field_round_trip.py`

Delete the two V208-1 lines from `NOT_REPOSITORY_BACKED`; add the import
`from swingbot.core.db.repositories.benchmark_bars import (BenchmarkBarRepository, BenchmarkRefreshRepository)`
and, at the end of `CASES` (after `"refresher_heartbeat"`):

```python
    # v208: the Benchmark tab's tables. BenchmarkBarRepository.upsert is its upsert_bars.
    "benchmark_bars": (BenchmarkBarRepository,
                       {"symbol": "SPY", "session": "2026-11-04", "source_symbol": "SPY",
                        "final": True, "as_of": TS}),
    "benchmark_refresh": (BenchmarkRefreshRepository,
                          {"symbol": "SPY", "full_refreshed_on": "2026-11-04"}),
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_benchmark_bars_repository.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.benchmark_bars'`.

- [ ] **Step 4: Implement `swingbot/core/db/repositories/benchmark_bars.py`**

Module docstring: writer is the refresher's `benchmarks` step (`swingbot/refresher/benchmarks.py`), reader is `admin/api_v1/benchmark.py`; no SSE event; every `updated_at` is `clock_timestamp()`. Imports only `swingbot.core.db.*` (core/db imports nothing from core/marketdata).

Shape (bodies are the implementer's; keep every function < 15 complexity):

```python
BAR_KEYS = ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")
_LEVELS = ("close", "adj_close", "day_pct")          # nullable; absent -> None


def _as_date(value) -> date: ...          # date passes; ISO string -> date.fromisoformat; else ValueError
def _as_utc(value) -> datetime: ...       # aware datetime or ISO string -> UTC; naive/None -> ValueError
def _prepared(row: dict) -> dict: ...     # validated copy: every BAR_KEYS key present, levels default None


class BenchmarkBarRepository(Repository):
    def __init__(self):
        super().__init__(benchmark_bars, key="session")

    def _bar(self, row) -> dict:              # {**self._record(row), **{k: row._mapping[k] for k in BAR_KEYS}}, as_of -> UTC
    def upsert_bars(self, rows, conn=None) -> int
    def upsert(self, record, *, conn=None) -> dict
    def list_range(self, symbols, start, end, conn=None) -> list[dict]
    def last_session(self, symbol, conn=None) -> date | None


class BenchmarkRefreshRepository(Repository):
    def __init__(self):
        super().__init__(benchmark_refresh, key="symbol")

    def full_refreshed_on(self, symbol, conn=None) -> date | None   # self.get(symbol)["full_refreshed_on"]
    def mark_full_refresh(self, symbol, day, conn=None) -> None      # self.upsert({"symbol": symbol, "full_refreshed_on": day})
```

`upsert_bars`: run `_prepared` on every row first (a bad row raises before anything is written), then dedupe with a dict keyed `(symbol, session)` (insertion order, last wins), `values = [self._values(row) for row in deduped]`, then
`pg_insert(self.table).values(values).on_conflict_do_update(index_elements=["symbol", "session"], set_={name: stmt.excluded[name] for name in values[0] if name not in ("symbol", "session")} | {"updated_at": sa.func.clock_timestamp()})`. Every prepared row carries the same keys (all `BAR_KEYS` plus `doc`), so `values[0]` names every column. `last_session`: `sa.select(sa.func.max(t.c.session)).where(t.c.symbol == symbol, t.c.final.is_(True))`.

- [ ] **Step 5: Run the tests to verify they pass**

Run, one at a time:
`python scripts/dev/testrun.py file tests/db/test_benchmark_bars_repository.py`
`python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: PASS (the round-trip test now covers both tables through their repositories).

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/repositories/benchmark_bars.py tests/db/test_benchmark_bars_repository.py \
        tests/db/test_unknown_field_round_trip.py
git commit -m "feat(v208): benchmark_bars and benchmark_refresh repositories"
```

# Phase 2 — Equity seam

### Task V208-3: `EquitySnapshot.open_notional`, `session_trade_pnl`, recorder writes the column

**Model:** sonnet — a defaulted dataclass field and two small pure functions in the one equity definition, pinned by hand-computed tests.

**Files:**
- Modify: `swingbot/core/tracking/equity.py` (`EquitySnapshot` :214-220, `snapshot_at` :245-252; two new functions)
- Modify: `swingbot/commands/scanning/equity_recorder.py` (`_row` :63-67, module docstring)
- Modify: `tests/tracking/test_equity_definition.py` (`test_snapshot_realizes_the_tp1_leg_and_prices_only_the_runner` :178-184, new tests)
- Modify: `tests/commands/test_equity_recorder.py`
- Create: `tests/tracking/test_equity_candles_unchanged_v208.py`

**Interfaces:**
- Consumes: `equity.unrealized_decimal`, `equity._price_of`, `equity.to_decimal`, `equity.live_open_positions`, `equity.RealizedLeg(at, amount, trade_id)`; `equity_candles.mtm_candles(rows, "1D")` (unchanged); V208-1's `equity_samples.open_notional` / `open_notional_approx` columns.
- Produces (consumed by V208-4 and V208-9):
  - `EquitySnapshot.open_notional: Decimal = Decimal("0")` — the **last** field, defaulted, so every existing constructor keeps working.
  - `equity.open_notional_of(positions: list[dict], prices: dict[str, float]) -> Decimal` — Σ `|shares × price|` over exactly the positions `_unrealized_total` counts (a position is counted iff `unrealized_decimal(entry, direction, shares, _price_of(prices, ticker))` is not None); shorts count positively; unpriced, unsized or entry-less positions add nothing. Unrounded `Decimal`; unconverted (quote currency, like `unrealized_pnl`).
  - `equity.session_trade_pnl(legs: list[RealizedLeg], prev_at: datetime, at: datetime, prev_unrealized: Decimal, unrealized: Decimal) -> Decimal` — Σ `leg.amount` for `prev_at < leg.at <= at`, plus `unrealized - prev_unrealized`. It never reads a balance, so a `base_balance` edit cannot enter it.
  - Recorder rows carry `"open_notional": snapshot.open_notional` and `"open_notional_approx": False`.

- [ ] **Step 1: Write the failing equity tests** — `tests/tracking/test_equity_definition.py`

Update the existing equality at :182 (the runner is 5 shares at 112):

```python
    assert snap == equity.EquitySnapshot(realized_balance=Decimal("1050.0"),
                                         unrealized_pnl=Decimal("60.00"),
                                         equity=Decimal("1110.00"), open_n=1, skipped_n=0,
                                         open_notional=Decimal("560.0"))
```

Append (uses the file's `_trade`, `_at`):

```python
# --- v208: open notional and the session's trade P&L -------------------------

def _pos(ticker, direction, shares, entry):
    return {"ticker": ticker, "direction": direction, "shares": shares, "entry": entry}


def test_open_notional_counts_shorts_positively_and_skips_what_is_not_priced():
    positions = [_pos("AAPL", "bullish", 10, 100.0), _pos("MSFT", "bearish", 5, 200.0),
                 _pos("NVDA", "bullish", 3, 50.0),          # no price
                 _pos("TSLA", "bullish", None, 10.0),       # unsized
                 _pos("AMD", "bullish", 4, None)]           # no entry
    prices = {"AAPL": 110.0, "MSFT": 195.0, "TSLA": 12.0, "AMD": 150.0, "NVDA": 0.0}
    assert equity.open_notional_of(positions, prices) == Decimal("2075")    # 1100 + 975


def test_open_notional_of_nothing_is_zero():
    assert equity.open_notional_of([], {"AAPL": 1.0}) == Decimal("0")


def test_snapshot_carries_the_open_notional_of_a_short():
    trade = _trade("s1", direction="bearish", shares=5, entry=200.0)
    snap = equity.snapshot_at([trade], {}, {"AAPL": 190.0}, _at("2026-08-03T16:00:00+00:00"),
                              Decimal("1000"))
    assert (snap.unrealized_pnl, snap.open_notional, snap.open_n) == (
        Decimal("50"), Decimal("950"), 1)


def test_the_snapshot_default_open_notional_is_zero():
    snap = equity.EquitySnapshot(realized_balance=Decimal("1"), unrealized_pnl=Decimal("0"),
                                 equity=Decimal("1"), open_n=0, skipped_n=0)
    assert snap.open_notional == Decimal("0")


T0, T1 = _at("2026-10-14T20:00:00+00:00"), _at("2026-10-15T20:00:00+00:00")


def _leg(at, amount):
    return equity.RealizedLeg(at=at, amount=Decimal(str(amount)), trade_id="t")


def test_session_trade_pnl_is_legs_in_the_half_open_window_plus_the_unrealized_change():
    legs = [_leg(T0, 100), _leg(_at("2026-10-15T15:00:00+00:00"), 50), _leg(T1, -20),
            _leg(_at("2026-10-15T20:01:00+00:00"), 999)]
    assert equity.session_trade_pnl(legs, T0, T1, Decimal("30"), Decimal("45")) == Decimal("45")


def test_session_trade_pnl_with_no_trading_is_zero_whatever_the_balance():
    assert equity.session_trade_pnl([], T0, T1, Decimal("12.5"), Decimal("12.5")) == Decimal("0")
```

- [ ] **Step 2: Write the failing pin test** — `tests/tracking/test_equity_candles_unchanged_v208.py`

```python
"""v208: the Dashboard's equity candles and every existing EquitySnapshot field
are unchanged by the new open_notional column (spec: seam pinned on a fixture)."""
from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal

from swingbot.commands.scanning import equity_recorder
from swingbot.core.tracking import equity
from swingbot.core.tracking.equity_candles import mtm_candles

UTC = timezone.utc


def _sample(i, at, value, *, source="live"):
    return {"id": i, "at": at, "equity": value, "kind": "point", "source": source,
            "skipped_n": 0, "realized_balance": 10000.0, "unrealized_pnl": value - 10000.0,
            "open_n": 1}


ROWS = [_sample(1, datetime(2026, 10, 14, 13, 35, tzinfo=UTC), 10000.0),
        _sample(2, datetime(2026, 10, 14, 15, 0, tzinfo=UTC), 10050.0),
        _sample(3, datetime(2026, 10, 14, 19, 55, tzinfo=UTC), 10020.0),
        _sample(4, datetime(2026, 10, 15, 13, 35, tzinfo=UTC), 10020.0),
        _sample(5, datetime(2026, 10, 15, 19, 55, tzinfo=UTC), 9990.0)]


def test_existing_snapshot_fields_are_unchanged_and_open_notional_is_appended():
    assert [f.name for f in fields(equity.EquitySnapshot)] == [
        "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n", "open_notional"]


def test_daily_candles_ignore_the_new_columns():
    plain = mtm_candles([dict(r) for r in ROWS], "1D")
    tagged = mtm_candles([{**r, "open_notional": 2040.0, "open_notional_approx": True}
                          for r in ROWS], "1D")
    assert tagged == plain
    assert [(c["t"], float(c["c"])) for c in plain] == [("2026-10-14", 10020.0),
                                                        ("2026-10-15", 9990.0)]


def test_the_recorder_row_keeps_every_v172_key():
    snap = equity.EquitySnapshot(realized_balance=Decimal("1"), unrealized_pnl=Decimal("0"),
                                 equity=Decimal("1"), open_n=0, skipped_n=0)
    row = equity_recorder._row(snap, datetime(2026, 10, 14, 15, 0, tzinfo=UTC))
    assert set(row) == {"at", "realized_balance", "unrealized_pnl", "equity", "open_n",
                        "skipped_n", "source", "kind", "backfill_run",
                        "open_notional", "open_notional_approx"}
```

- [ ] **Step 3: Write the failing recorder tests** — append to `tests/commands/test_equity_recorder.py` (uses its `repo`, `account`, `_trade`, `_patch_book`, `IN_SESSION`, `BASE`; `_trade`'s `**extra` overrides `direction`)

```python
def test_the_recorder_writes_open_notional_with_shorts_counted_positively(
        monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL"),
                              _trade("t2", "MSFT", shares=5.0, entry=200.0, direction="bearish"),
                              _trade("t3", "NVDA")])                      # unpriced
    assert equity_recorder.record_sample({"AAPL": 110.0, "MSFT": 190.0},
                                         now=IN_SESSION, repo=repo) is True
    (row,) = repo.list_rows()
    assert (row["unrealized_pnl"], row["open_n"], row["skipped_n"]) == (150.0, 2, 1)
    assert (row["open_notional"], row["open_notional_approx"]) == (2050.0, False)   # 1100 + 950


def test_a_flat_book_records_zero_open_notional(monkeypatch, repo, account):
    _patch_book(monkeypatch, [])
    assert equity_recorder.record_sample({}, now=IN_SESSION, repo=repo) is True
    (row,) = repo.list_rows()
    assert (row["open_notional"], row["open_notional_approx"]) == (0.0, False)
    assert row["equity"] == BASE
```

- [ ] **Step 4: Run the tests to verify they fail**

Run, one at a time:
`python scripts/dev/testrun.py file tests/tracking/test_equity_definition.py`
`python scripts/dev/testrun.py file tests/tracking/test_equity_candles_unchanged_v208.py`
`python scripts/dev/testrun.py file tests/commands/test_equity_recorder.py`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'open_notional'`, `AttributeError: ... has no attribute 'open_notional_of'` / `'session_trade_pnl'`, and the recorder rows lack `open_notional`.

- [ ] **Step 5: Implement in `swingbot/core/tracking/equity.py`**

- `EquitySnapshot` gains `open_notional: Decimal = Decimal("0")` as its last field.
- `open_notional_of(positions, prices) -> Decimal` after `_unrealized_total`: loop the positions, skip one whenever `unrealized_decimal(...)` with `_price_of(prices, ticker)` is None (the same skip rule as `_unrealized_total`, so `open_n` and the notional count the same positions), else add `abs(to_decimal(shares) * to_decimal(price))`. Docstring: absolute notional, shorts positive, quote currency unconverted like `unrealized_pnl` (v208 is USD-only).
- `session_trade_pnl(legs, prev_at, at, prev_unrealized, unrealized) -> Decimal` after `realized_balance_at`. Docstring: the Bot · deployed numerator; trade P&L only (legs in `(prev_at, at]` plus the unrealized change), never a balance, so `base_balance` edits never enter it.
- `snapshot_at`: compute `positions = live_open_positions(trades, plans_by_id)` once, pass it to `_unrealized_total` and `open_notional_of`, and set `open_notional=` on the returned snapshot.
- Module docstring: one bullet — `**Open notional (v208):** Σ |open shares × price| over the priced positions; capital at work, not net delta.`

- [ ] **Step 6: Implement in `swingbot/commands/scanning/equity_recorder.py`**

`_row` adds `"open_notional": snapshot.open_notional, "open_notional_approx": False`. Module docstring: one line under the rules — `v208: every row carries open_notional (measured at this tick's prices, open_notional_approx = False); the backfill's re-derived rows carry True.` The recorder's weekday-only `is_regular_session` stays as it is (spec amendment 3).

- [ ] **Step 7: Run the tests to verify they pass**

Run, one at a time:
`python scripts/dev/testrun.py file tests/tracking/test_equity_definition.py`
`python scripts/dev/testrun.py file tests/tracking/test_equity_candles_unchanged_v208.py`
`python scripts/dev/testrun.py file tests/commands/test_equity_recorder.py`
`python scripts/dev/testrun.py file tests/admin/test_api_v1_equity.py`
Expected: all PASS (the last proves the Dashboard endpoint is untouched).

- [ ] **Step 8: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/tracking/equity.py swingbot/commands/scanning/equity_recorder.py \
        tests/tracking/test_equity_definition.py tests/tracking/test_equity_candles_unchanged_v208.py \
        tests/commands/test_equity_recorder.py
git commit -m "feat(v208): EquitySnapshot.open_notional, session_trade_pnl; recorder writes open_notional"
```

### Task V208-4: Backfill `--open-notional` (dry-run default, targeted UPDATE)

**Model:** sonnet — extends an existing CLI with one mode modelled on `--recompute-realized`; every number is hand-computed in the tests.

**Files:**
- Modify: `scripts/data/backfill_equity_samples.py` (module docstring, `_row` :242-246, `_price_positions` :225-239, `build_day_rows` :249-262, `_parse` :364-376, `main` :423-441; new helpers)
- Modify: `tests/scripts/test_backfill_equity_samples.py`

**Interfaces:**
- Consumes: V208-1 `EquitySampleRepository.update_open_notional(sample_id, open_notional, approx, conn=None)`; V208-3 semantics of `open_notional` (Σ `|shares × price|`, shorts positive); script helpers `bar_for`, `session_bounds`, `ny_day`, `filled_trades`, `_fetch_all`, `fetch_raw_bars`, `DRY_RUN_NOTE`; `equity.main_book`, `equity.parse_ts`, `expand_trade_legs`.
- Produces:
  - CLI `--open-notional [--apply]`, mutually exclusive with `--recompute-realized` (argparse group: both → exit 2).
  - `class OpenNotionalReport(NamedTuple)`: `seen: int, filled: int, backfill_rows: int, live_rows: int, unpriced: int`.
  - `rows_to_fill(repo) -> list[dict]` — every `kind == "point"` row (both sources) whose `open_notional` is NULL (`row.get("open_notional") is None`); `day_high`/`day_low` rows are never filled.
  - `fill_open_notional(repo, trades: list[dict], bars: dict, *, apply: bool) -> OpenNotionalReport` — `trades` are `filled_trades(...)` output. Per row: the slices held **at that instant** (trade `opened_at <= at` and, for a closed leg, its `closed_at > at`), each priced from its ticker's daily bar for the row's New York day: **the bar's open when `at` is that day's 09:30 session open, else the bar's close** (the spec's accepted approximation). A row with no held slice fills `0`. A row with any held slice that has no bar or no size stays NULL and counts in `unpriced` (never a partial notional). With `apply`, each filled row is written with `repo.update_open_notional(row["id"], value, True)`; nothing else is touched.
  - Output: dry run `open_notional: would fill <filled> rows (<backfill_rows> backfill, <live_rows> live), <unpriced> unpriced` then `DRY_RUN_NOTE`; apply `open_notional: filled <filled> rows (<backfill_rows> backfill, <live_rows> live), <unpriced> unpriced`. `main` returns `{**_summary(run_id), "open_notional": report._asdict()}`.
  - `build_day_rows` rows carry `open_notional`: the open point = Σ `|shares × bar.open|` over slices held at the open (`entry_day < day`), the close point = Σ `|shares × bar.close|` over slices still held at the close (`exit_day != day`), `open_notional_approx = True` on both; `day_high`/`day_low` rows carry `open_notional = None`, `open_notional_approx = None`. A day with any skipped slice carries `None`/`None` on all four rows.

- [ ] **Step 1: Write the failing day-row tests** — append to `tests/scripts/test_backfill_equity_samples.py` after the V172-6 block (before `# --- V172-7: the CLI`); no DB needed

```python
# --- V208-4: open notional ------------------------------------------------------

@pytest.mark.parametrize("day, at_open, at_close", [
    (MON, 0, 1020),            # AAPL entered Mon: not held at the open; 10 x 102 at the close
    (TUE, 1020, 2040),         # AAPL 10 x 102 open; close 10 x 105 + MSFT short 5 x 198
    (WED, 2040, 975),          # open 10 x 105 + 5 x 198; AAPL exited Wed, MSFT 5 x 195
])
def test_day_rows_carry_open_notional_on_the_two_points(day, at_open, at_close):
    rows, _ = _rows(day)
    assert [(r["kind"], r["open_notional"]) for r in rows] == [
        ("point", at_open), ("day_high", None), ("day_low", None), ("point", at_close)]
    assert [r["open_notional_approx"] for r in rows] == [True, None, None, True]


def test_a_day_with_a_skipped_slice_has_no_open_notional():
    rows, skips = _rows(TUE, bars={"AAPL": BARS["AAPL"]}, allow_gaps=True)
    assert [s.ticker for s in skips] == ["MSFT"]
    assert {(r["open_notional"], r["open_notional_approx"]) for r in rows} == {(None, None)}
```

- [ ] **Step 2: Write the failing fill and CLI tests** — append at the end of the file (uses `repo`, `account`, `_main`, `_live`, `_frame`, `BARS`, `TRADES`, `MON`, `TUE`, `WED`)

```python
UTC = timezone.utc
MON_LIVE = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)    # 10:30 NY: AAPL held (opened 14:00 UTC)
TUE_LIVE = datetime(2026, 10, 6, 16, 0, tzinfo=UTC)     # 12:00 NY: AAPL + MSFT held
WED_LIVE = datetime(2026, 10, 7, 19, 0, tzinfo=UTC)     # 15:00 NY: AAPL closed 18:00 UTC
FILLED_AT = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)    # a recorder row: never touched


def _seed_unfilled(repo):
    for at in (MON_LIVE, TUE_LIVE, WED_LIVE):
        repo.insert_sample(_live(at, 10000, 0))
    old = {"source": "backfill", "backfill_run": "old@bars-asof-x"}
    repo.upsert_many([{**_live(bes.session_bounds(MON)[0], 10000, 0), **old},
                      {**_live(bes.session_bounds(TUE)[0], 10000, 0), **old},
                      {**_live(bes.session_bounds(MON)[0], 10000, 0), **old, "kind": "day_high"}])
    repo.insert_sample({**_live(FILLED_AT, 10000, 0), "open_notional": Decimal("1"),
                        "open_notional_approx": False})


def _notional_by_at(repo):
    return {(r["at"], r["kind"]): (r.get("open_notional"), r.get("open_notional_approx"))
            for r in repo.list_rows()}


def test_fill_prices_what_was_held_at_each_instant(repo, account):
    _seed_unfilled(repo)
    report = bes.fill_open_notional(repo, TRADES, BARS, apply=True)
    assert report == bes.OpenNotionalReport(seen=5, filled=5, backfill_rows=2, live_rows=3,
                                            unpriced=0)
    got = _notional_by_at(repo)
    assert got[(MON_LIVE, "point")] == (1020.0, True)            # 10 x Mon close 102
    assert got[(TUE_LIVE, "point")] == (2040.0, True)            # 10 x 105 + 5 x 198
    assert got[(WED_LIVE, "point")] == (975.0, True)             # MSFT 5 x 195 only
    assert got[(bes.session_bounds(MON)[0], "point")] == (0.0, True)       # nothing held yet
    assert got[(bes.session_bounds(TUE)[0], "point")] == (1020.0, True)    # 10 x Tue open 102
    assert got[(bes.session_bounds(MON)[0], "day_high")] == (None, None)
    assert got[(FILLED_AT, "point")] == (1.0, False)


def test_a_row_with_an_unpriced_held_slice_stays_null(repo, account):
    _seed_unfilled(repo)
    report = bes.fill_open_notional(repo, TRADES, {"AAPL": BARS["AAPL"]}, apply=True)
    assert (report.filled, report.backfill_rows, report.live_rows, report.unpriced) == (3, 2, 1, 2)
    got = _notional_by_at(repo)
    assert got[(TUE_LIVE, "point")] == (None, None) and got[(WED_LIVE, "point")] == (None, None)


def test_the_fill_never_touches_the_equity_columns(repo, account):
    _seed_unfilled(repo)
    before = {(r["at"], r["kind"]): (r["equity"], r["realized_balance"], r["unrealized_pnl"])
              for r in repo.list_rows()}
    bes.fill_open_notional(repo, TRADES, BARS, apply=True)
    after = {(r["at"], r["kind"]): (r["equity"], r["realized_balance"], r["unrealized_pnl"])
             for r in repo.list_rows()}
    assert after == before


def test_open_notional_dry_run_counts_and_writes_nothing(monkeypatch, repo, account, tmp_path, capsys):
    _seed_unfilled(repo)
    calls = []
    summary = _main(monkeypatch, ["--open-notional"], repo, tmp_path, calls=calls)
    assert summary["open_notional"] == {"seen": 5, "filled": 5, "backfill_rows": 2,
                                        "live_rows": 3, "unpriced": 0}
    out = capsys.readouterr().out
    assert "open_notional: would fill 5 rows (2 backfill, 3 live), 0 unpriced" in out
    assert "Dry run only -- pass --apply to write." in out
    assert sorted(calls) == [("AAPL", MON, TUE), ("MSFT", TUE, WED)]   # held days only
    assert _notional_by_at(repo)[(TUE_LIVE, "point")] == (None, None)


def test_open_notional_apply_then_a_rerun_finds_nothing(monkeypatch, repo, account, tmp_path, capsys):
    _seed_unfilled(repo)
    _main(monkeypatch, ["--open-notional", "--apply"], repo, tmp_path)
    assert "open_notional: filled 5 rows (2 backfill, 3 live), 0 unpriced" in capsys.readouterr().out
    again = _main(monkeypatch, ["--open-notional", "--apply"], repo, tmp_path)
    assert again["open_notional"]["seen"] == 0 and again["open_notional"]["filled"] == 0


def test_open_notional_and_recompute_realized_are_exclusive(monkeypatch, repo, tmp_path):
    with pytest.raises(SystemExit):
        _main(monkeypatch, ["--open-notional", "--recompute-realized"], repo, tmp_path)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: FAIL — `KeyError: 'open_notional'` on day rows, `AttributeError: ... 'fill_open_notional'` / `'OpenNotionalReport'`, argparse `unrecognized arguments: --open-notional`.

- [ ] **Step 4: Day rows carry `open_notional`** — `scripts/data/backfill_equity_samples.py`

- `position_notional(pos: dict, bar: Bar, day: date) -> tuple[Decimal, Decimal]` next to `position_day`: `(|shares × bar.open| if pos["entry_day"] != day else 0, |shares × bar.close| if pos["exit_day"] != day else 0)`, `Decimal` via `equity.to_decimal`.
- `_price_positions` also sums `position_notional` into two more totals (`open_x`, `close_x`) for counted slices; keep `position_day`'s return dict unchanged (pinned by `test_position_day_*`).
- `_row(...)` gains a keyword `notional: Decimal | None = None`, writing `"open_notional": notional, "open_notional_approx": None if notional is None else True`.
- `build_day_rows`: pass `notional=` the open total to the open point and the close total to the close point when `skips` is empty, else `None`; `day_high`/`day_low` get `None`.

- [ ] **Step 5: The fill mode**

- `OpenNotionalReport(NamedTuple)` and `rows_to_fill(repo)` as in Interfaces.
- `_held_at(trades: list[dict], at: datetime) -> list[dict]`: for each `equity.main_book(trades)` trade and each `expand_trade_legs(trade)` row with status in `_HELD_STATUSES`: `opened = equity.parse_ts(trade["opened_at"])`, `closed = None if status == "open" else equity.parse_ts(row.get("closed_at"))`; keep `{"ticker": trade["ticker"], "shares": row.get("shares")}` when `opened is not None and opened <= at and (status == "open" or (closed is not None and closed > at))`.
- `_row_notional(row: dict, trades: list[dict], bars: dict) -> Decimal | None`: `day = ny_day(row["at"])`; `use_open = row["at"] == session_bounds(day)[0]`; for each held slice, `bar = bar_for(bars.get(ticker), day)`; no bar or falsy shares → return None; else add `abs(shares × (bar.open if use_open else bar.close))`. Empty slice list → `Decimal("0")`.
- `fill_open_notional(...)`: loop `rows_to_fill(repo)`, count `seen`, compute `_row_notional`, tally `filled`/`backfill_rows`/`live_rows`/`unpriced`, and when `apply` call `repo.update_open_notional(row["id"], value, True)`.
- `_notional_spans(trades: list[dict], rows: list[dict]) -> dict[str, tuple[date, date]]`: per ticker, the first and last New York day it is held in `_held_at(trades, row["at"])` over `rows` (one fetch per ticker, held days only).
- `_run_open_notional(args, repo, trades, bars_fn, out_dir) -> OpenNotionalReport`: `rows = rows_to_fill(repo)`, `frames = _fetch_all(_notional_spans(trades, rows), bars_fn, out_dir)`, `fill_open_notional(repo, trades, frames, apply=args.apply)`, then print the line from Interfaces (`would fill` without `--apply`, `filled` with it), and `DRY_RUN_NOTE` on a dry run.
- `_parse`: put `--recompute-realized` and a new `--open-notional` (help: `Fill open_notional on point rows that lack it (re-derived from daily bars, open_notional_approx = TRUE). Touches no other column.`) in one `add_mutually_exclusive_group()`.
- `main`: right after `trades = ...`, `if args.open_notional:` compute `filled = filled_trades(trades, (plans_fn or equity.load_plans_by_id)())`, run `_run_open_notional(args, repo, filled, bars_fn or fetch_raw_bars, out_dir or ROOT / "data" / "backfill_equity_samples" / run_id)` and return `{**_summary(run_id), "open_notional": report._asdict()}`. Keep `main` under complexity 15 (move the branch into a helper if needed).
- Module docstring usage block gains
  `python scripts/data/backfill_equity_samples.py --open-notional [--apply]   # v208: fill open_notional (approx = TRUE)`
  and a v208 production paragraph: dry run on the replica first, then the PITR check, then
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional --apply"`;
  rollback `UPDATE equity_samples SET open_notional = NULL, open_notional_approx = NULL WHERE open_notional_approx IS TRUE` (recorder rows carry FALSE and keep their values).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: PASS — the V172 tests unchanged (`test_dry_run_reports_coverage_and_writes_nothing` still sees its exact summary dict, since only the `--open-notional` mode adds a key), plus the eight new ones.

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add scripts/data/backfill_equity_samples.py tests/scripts/test_backfill_equity_samples.py
git commit -m "feat(v208): backfill --open-notional -- dry-run default, targeted update, approx flag"
```

