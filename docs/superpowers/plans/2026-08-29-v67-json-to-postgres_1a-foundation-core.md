# v67 — Part 1: Foundation

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here** — they are implicitly part
> of every task's requirements and are not repeated below.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

Part 1 builds the machinery every later part consumes: the doc/column codec,
the engine, the schema registry, Alembic, the Postgres container, the test
harness, the generic repository, the `DB_STORES` stage resolver, the dual-write
comparator, and `LISTEN/NOTIFY`. Nothing here migrates a store. The one real
table it creates is `trades`, because a codec with no table to round-trip
through is untested machinery, and `trades` is the table the spec specifies in
full DDL. Part 2 builds `TradeRepository` on top of it.

## Parallelisation

**Sequential throughout.** Every task consumes a symbol the previous one
introduces: `codec` → `schema` → Alembic → the test harness → the repository →
everything else. There is no honest parallel group in this part, and saying so
is worth as much as a wide group would be — it stops the next session
re-deriving the graph.

Part 1 must land on `main` in full before any of Parts 2–5 starts.

## Alembic revision ids

Part 1 owns the `p1_*` prefix. Revisions are created with an explicit id:

```bash
alembic revision --rev-id p1_002 -m "create trades"
```

Never `alembic revision --autogenerate` without `--rev-id` — a random hash is
what turns two parallel parts into a silent branch instead of a name clash.

---

# Phase 1 — Foundation

### Task P1-01: The doc/column codec

The one piece of the design everything else depends on. Pure functions, no
database, no imports outside the standard library — so it is fully testable
before Postgres exists anywhere in the repo.

**Files:**
- Create: `swingbot/core/db/__init__.py`
- Create: `swingbot/core/db/codec.py`
- Test: `tests/db/test_codec.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `split_doc(record: Mapping[str, Any], promoted: Sequence[str]) -> tuple[dict, dict]`
  - `merge_doc(row: Mapping[str, Any], promoted: Sequence[str]) -> dict`
  - `RESERVED_KEYS: frozenset[str]` — `{"id", "doc", "updated_at"}`
  - `ReservedKeyError(ValueError)`

**Design decision to honour, not re-open:** `merge_doc` **omits a promoted
column whose value is SQL NULL**, rather than emitting `{"closed_at": None}`.
This makes an absent field round-trip as absent, which is what today's call
sites see. The cost is that a field explicitly set to `None` comes back absent,
so the promotion criteria gain one clause: **promote only a field whose absence
and whose `None` mean the same thing.** Every field promoted in this plan
satisfies that; `doc` fields are unaffected because JSONB stores an explicit
`null` distinctly from a missing key.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/__init__.py` (empty file) and `tests/db/test_codec.py`:

```python
"""The doc/column codec: the contract that lets call sites keep flat dicts."""
import pytest

from swingbot.core.db.codec import (
    ReservedKeyError,
    merge_doc,
    split_doc,
)

PROMOTED = ("trade_id", "ticker", "status", "closed_at")


def test_split_sends_promoted_to_columns_and_rest_to_doc():
    cols, doc = split_doc(
        {"trade_id": "T1", "ticker": "AAPL", "status": "open",
         "confidence": 4, "notes": {"why": "breakout"}},
        PROMOTED,
    )
    assert cols == {"trade_id": "T1", "ticker": "AAPL", "status": "open"}
    assert doc == {"confidence": 4, "notes": {"why": "breakout"}}


def test_split_omits_promoted_keys_the_record_does_not_have():
    cols, doc = split_doc({"trade_id": "T1"}, PROMOTED)
    assert cols == {"trade_id": "T1"}
    assert "closed_at" not in cols


def test_split_rejects_a_record_using_a_reserved_key():
    for key in ("id", "doc", "updated_at"):
        with pytest.raises(ReservedKeyError) as exc:
            split_doc({"trade_id": "T1", key: "x"}, PROMOTED)
        assert key in str(exc.value)


def test_merge_rebuilds_one_flat_dict():
    row = {"id": 7, "trade_id": "T1", "ticker": "AAPL", "status": "open",
           "closed_at": None, "doc": {"confidence": 4}, "updated_at": "2026-01-01"}
    assert merge_doc(row, PROMOTED) == {
        "trade_id": "T1", "ticker": "AAPL", "status": "open", "confidence": 4,
    }


def test_merge_drops_infrastructure_columns():
    row = {"id": 7, "trade_id": "T1", "doc": {}, "updated_at": "2026-01-01"}
    out = merge_doc(row, PROMOTED)
    assert out == {"trade_id": "T1"}


def test_merge_tolerates_a_null_doc():
    row = {"trade_id": "T1", "doc": None}
    assert merge_doc(row, PROMOTED) == {"trade_id": "T1"}


def test_promoted_column_wins_over_a_stale_doc_copy():
    # A backfill that promoted a field may leave the old copy behind in doc.
    # The column is the source of truth from that moment on.
    row = {"trade_id": "T1", "status": "closed", "doc": {"status": "open"}}
    assert merge_doc(row, PROMOTED)["status"] == "closed"


@pytest.mark.parametrize("record", [
    {"trade_id": "T1", "ticker": "AAPL", "confidence": 4, "legs": [1, 2]},
    {"trade_id": "T2", "nested": {"a": {"b": [1, {"c": None}]}}},
    {"trade_id": "T3"},
])
def test_round_trip_is_lossless(record):
    cols, doc = split_doc(record, PROMOTED)
    row = {**cols, "id": 1, "doc": doc, "updated_at": "2026-01-01"}
    assert merge_doc(row, PROMOTED) == record
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_codec.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'swingbot.core.db'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/db/__init__.py`:

```python
"""PostgreSQL persistence layer.

Nothing outside this package imports SQLAlchemy. Store classes call
repositories; repositories return plain dicts. See
docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md.
"""
```

Create `swingbot/core/db/codec.py`:

```python
"""Split a flat record into promoted columns + a JSONB doc, and back.

This is what keeps schema change as cheap as editing a Python dict: adding a
field is `record["gamma_flip"] = x` with no migration, and promoting one later
is ADD COLUMN + backfill + one name in PROMOTED, with no call site touched --
call sites never read columns directly, only the merged flat dict.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

# Columns every table has for infrastructure reasons. They are not part of any
# record's flat contract, so a record may not use these names and merge_doc
# never emits them.
RESERVED_KEYS = frozenset({"id", "doc", "updated_at"})


class ReservedKeyError(ValueError):
    """A record used a key reserved for an infrastructure column."""


def split_doc(record: Mapping[str, Any],
              promoted: Sequence[str]) -> tuple[dict, dict]:
    """Return (columns, doc) for `record`.

    Keys named in `promoted` become column values; everything else goes to
    doc. A promoted key the record does not carry is simply absent from
    `columns`, so the column's own default (or NULL) applies.
    """
    clash = RESERVED_KEYS.intersection(record)
    if clash:
        raise ReservedKeyError(
            f"record uses reserved key(s) {sorted(clash)}; rename the field "
            f"-- these names belong to infrastructure columns"
        )
    promoted_set = set(promoted)
    columns: dict[str, Any] = {}
    doc: dict[str, Any] = {}
    for key, value in record.items():
        if key in promoted_set:
            columns[key] = value
        else:
            doc[key] = value
    return columns, doc


def merge_doc(row: Mapping[str, Any], promoted: Sequence[str]) -> dict:
    """Return one flat dict from a database row.

    Promoted columns are merged OVER doc, so a stale doc copy left behind by a
    backfill loses to the column. A promoted column that is NULL is OMITTED
    rather than emitted as None -- an absent field must round-trip as absent.
    That is why the promotion criteria require a field whose absence and whose
    None mean the same thing.
    """
    out = dict(row.get("doc") or {})
    for key in promoted:
        if key in row and row[key] is not None:
            out[key] = row[key]
    for key in RESERVED_KEYS:
        out.pop(key, None)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/db/test_codec.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/__init__.py swingbot/core/db/codec.py tests/db/__init__.py tests/db/test_codec.py
git commit -m "feat(v67): add the doc/column codec"
```

---

### Task P1-02: Dependencies, config fields and the engine

Adds the three runtime dependencies, the three `.env` fields this plan
introduces, and the fail-fast engine factory. Config fields land here rather
than in a later task because `engine.py` cannot resolve a URL that `FIELDS`
does not define.

**Files:**
- Modify: `requirements.txt` (append a new pinned block)
- Modify: `swingbot/config.py` (append three `Field` entries to `FIELDS`)
- Create: `swingbot/core/db/engine.py`
- Test: `tests/db/test_engine.py`

**Interfaces:**
- Consumes: `swingbot.core.db.codec` (P1-01) — only as a sibling module, no symbols.
- Produces:
  - `get_engine() -> sqlalchemy.Engine` — process-wide singleton
  - `reset_engine() -> None` — disposes and clears the singleton (tests, and
    `config.reload()` when `DATABASE_URL` changes)
  - `DatabaseUnavailable(RuntimeError)`
  - `config.DATABASE_URL`, `config.POSTGRES_PASSWORD`, `config.DB_STORES`

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_engine.py`:

```python
"""Engine construction: fail fast, and never build two pools."""
import pytest

from swingbot import config
from swingbot.core.db import engine as dbengine


@pytest.fixture(autouse=True)
def _clean_engine():
    dbengine.reset_engine()
    yield
    dbengine.reset_engine()


def test_missing_url_raises_rather_than_returning_none(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    with pytest.raises(dbengine.DatabaseUnavailable) as exc:
        dbengine.get_engine()
    assert "DATABASE_URL" in str(exc.value)


def test_engine_is_a_singleton(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@localhost:5432/db")
    assert dbengine.get_engine() is dbengine.get_engine()


def test_reset_engine_forces_a_rebuild(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@localhost:5432/db")
    first = dbengine.get_engine()
    dbengine.reset_engine()
    assert dbengine.get_engine() is not first


def test_url_must_use_the_psycopg_driver(monkeypatch):
    # psycopg2 is not a dependency here; a bare postgresql:// URL would make
    # SQLAlchemy reach for it and fail with a confusing ImportError.
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@localhost/db")
    with pytest.raises(dbengine.DatabaseUnavailable) as exc:
        dbengine.get_engine()
    assert "postgresql+psycopg://" in str(exc.value)


def test_the_three_new_fields_are_registered():
    keys = {f.key: f for f in config.FIELDS}
    assert keys["DATABASE_URL"].sensitive is True
    assert keys["DATABASE_URL"].hot_reloadable is False
    assert keys["POSTGRES_PASSWORD"].sensitive is True
    assert keys["DB_STORES"].sensitive is False
    assert keys["DB_STORES"].hot_reloadable is True
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_engine.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.engine'`.

- [ ] **Step 3: Install the dependencies**

Append to `requirements.txt`, matching the file's existing style — an exact pin
and a comment saying why the package is there:

```
# PostgreSQL persistence (swingbot/core/db/). SQLAlchemy is used as Core only
# -- Table/select/insert -- never as an ORM: repositories return plain dicts so
# call sites keep the flat-dict contract they had when this was JSON files.
# Unlike every other dependency here, this one does NOT degrade gracefully: a
# write that cannot reach Postgres raises, on purpose (see the spec's "Failure
# behavior" section -- a bot that posts alerts while recording none of them is
# worse than one that is visibly down).
SQLAlchemy==2.0.44
# Postgres driver. The [binary] extra ships prebuilt wheels, so no libpq
# headers or compiler are needed in the Docker build or on a dev machine.
psycopg[binary]==3.2.12
# Schema migrations. Revision ids are always explicit and part-prefixed
# (alembic revision --rev-id p1_002), never autogenerated hashes -- see the
# plan index's Parallelisation section for why.
alembic==1.16.6
```

Then:

```bash
python -m pip install -r requirements.txt
```

- [ ] **Step 4: Register the three config fields**

In `swingbot/config.py`, append a new section to the end of the `FIELDS` list
(keep the existing `# --- Section ---` comment style):

```python
    # --- Database ---
    Field("DATABASE_URL", "DATABASE_URL", "Database", "Postgres connection URL",
          type="password", sensitive=True, hot_reloadable=False,
          default="postgresql+psycopg://swingbot:swingbot@db:5432/swingbot",
          help="SQLAlchemy URL for the Postgres instance. Must use the "
               "postgresql+psycopg:// driver prefix. Changing this needs a "
               "container restart -- the connection pool is built once at "
               "first use and is not swapped live."),
    Field("POSTGRES_PASSWORD", "POSTGRES_PASSWORD", "Database", "Postgres password",
          type="password", sensitive=True, hot_reloadable=False,
          help="Consumed by the db container at first start to initialise the "
               "swingbot role. Must match the password inside DATABASE_URL. "
               "Changing it after the volume is initialised does NOT change "
               "the role's password -- use ALTER ROLE, or recreate the volume."),
    Field("DB_STORES", "DB_STORES", "Database", "Per-store migration stages",
          default="",
          help="Comma-separated name:stage pairs selecting where each store "
               "reads and writes: json (files only), dual (write both, read "
               "files), db (Postgres only). Any store not listed defaults to "
               "json. Example: trades:db,plans:dual,journal:json. A store "
               "rolls back one stage by editing this value and reloading -- "
               "no redeploy."),
```

- [ ] **Step 5: Write the engine**

Create `swingbot/core/db/engine.py`:

```python
"""Engine and pool, built once per process from config.DATABASE_URL.

Fail-fast policy, deliberately the reverse of jsonio.py's degrade-don't-crash
one: a corrupt JSON file was a local, recoverable condition worth surviving,
whereas an unreachable local database means something is genuinely wrong.
Docker's `restart: unless-stopped` is the recovery mechanism, not a try/except.
"""
from __future__ import annotations

import logging

from sqlalchemy import Engine, create_engine

from swingbot import config

log = logging.getLogger(__name__)

_engine: Engine | None = None

# Both containers plus the odd script share one small Postgres. Five pooled
# connections each with five of overflow is far more than this write volume
# needs and far less than Postgres' default 100-connection ceiling.
_POOL_SIZE = 5
_MAX_OVERFLOW = 5


class DatabaseUnavailable(RuntimeError):
    """The database cannot be reached or is not configured."""


def get_engine() -> Engine:
    """Return the process-wide Engine, building it on first use."""
    global _engine
    if _engine is not None:
        return _engine

    url = (config.DATABASE_URL or "").strip()
    if not url:
        raise DatabaseUnavailable(
            "DATABASE_URL is not set. Set it in .env "
            "(postgresql+psycopg://user:pass@host:5432/dbname)."
        )
    if not url.startswith("postgresql+psycopg://"):
        raise DatabaseUnavailable(
            f"DATABASE_URL must start with postgresql+psycopg:// -- got "
            f"{url.split('://', 1)[0]}://. A bare postgresql:// URL makes "
            f"SQLAlchemy reach for psycopg2, which is not installed here."
        )

    _engine = create_engine(
        url,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        # A pooled connection can be dead after a db container restart. One
        # cheap round trip on checkout beats a spurious OperationalError on
        # the first write after every deploy.
        pool_pre_ping=True,
        future=True,
    )
    log.info("Database engine created for %s", _engine.url.render_as_string(hide_password=True))
    return _engine


def reset_engine() -> None:
    """Dispose the pool and drop the singleton. For tests, and for a
    DATABASE_URL change that a restart has not yet picked up."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/db/test_engine.py
```

Expected: `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt swingbot/config.py swingbot/core/db/engine.py tests/db/test_engine.py
git commit -m "feat(v67): add db dependencies, config fields and the engine"
```

---

### Task P1-03: The Postgres container

One added service, a named volume, and both application services waiting on its
health check. Docs land in this task because a compose change nobody documented
is the thing the next deploy trips over.

**Files:**
- Modify: `docker-compose.yml` (add the `db` service; add `depends_on` to `bot`
  and `admin`; add a top-level `volumes:` section — the file has none today)
- Modify: `.env.example` (append a Database section)
- Modify: `docs/deploy/DOCKER.md`
- Test: `tests/db/test_compose.py`

**Interfaces:**
- Consumes: `config.DATABASE_URL`, `config.POSTGRES_PASSWORD` (P1-02).
- Produces: a reachable Postgres 18 on the compose network at host `db`, port
  `5432`; the named volume `pgdata`.

- [ ] **Step 1: Write the failing test**

The point of a test over a compose file is narrow and worth being honest about:
it does not prove the container runs. It pins the four facts a later edit could
silently break — the pinned image, the healthcheck gate, the named volume, and
that neither app service starts before the database is healthy.

Create `tests/db/test_compose.py`:

```python
"""Pins the compose facts a careless edit could silently break."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

COMPOSE = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_db_service_pins_postgres_18_alpine(compose):
    assert compose["services"]["db"]["image"] == "postgres:18-alpine"


def test_db_data_lives_on_a_named_volume_not_a_bind_mount(compose):
    # A bind mount for PGDATA is the classic way to lose a database to host
    # filesystem semantics. The named volume is also what the backup drill
    # in Part 6 restores into.
    assert "pgdata" in compose["volumes"]
    assert any(v.startswith("pgdata:") for v in compose["services"]["db"]["volumes"])


def test_db_has_a_pg_isready_healthcheck(compose):
    test = compose["services"]["db"]["healthcheck"]["test"]
    assert any("pg_isready" in str(part) for part in test)


@pytest.mark.parametrize("service", ["bot", "admin"])
def test_app_services_wait_for_a_healthy_database(compose, service):
    assert compose["services"][service]["depends_on"]["db"] == {
        "condition": "service_healthy"
    }
```

`pyyaml` arrives transitively with `docker==7.1.0`; `importorskip` keeps the
test honest if that ever stops being true rather than failing for the wrong
reason.

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/db/test_compose.py -q
```

Expected: `KeyError: 'db'`.

- [ ] **Step 3: Add the service**

In `docker-compose.yml`, insert this **before** the `bot:` service so the
dependency reads top-to-bottom:

```yaml
  db:
    # Pinned exactly, like every other image here. A Postgres major-version
    # jump rewrites the on-disk format and will refuse to start against a
    # volume initialised by an older major -- so this pin is load-bearing,
    # not hygiene.
    image: postgres:18-alpine
    container_name: swing-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: swingbot
      POSTGRES_DB: swingbot
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}
    volumes:
      # NAMED volume, not ./data/pg. PGDATA on a bind mount inherits the host
      # filesystem's ownership and fsync semantics; a named volume is managed
      # by Docker and is what the Part 6 restore drill targets.
      - pgdata:/var/lib/postgresql/data
    # No `ports:` on purpose. Nothing outside the compose network needs to
    # reach this, and publishing 5432 on a public VM is how a Postgres ends up
    # in someone else's botnet. Use `docker compose exec db psql -U swingbot`.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U swingbot -d swingbot"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
```

On the `bot` service, add:

```yaml
    depends_on:
      db:
        condition: service_healthy
```

On the `admin` service, extend the existing `depends_on` (it already waits on
`bot`) to:

```yaml
    depends_on:
      bot:
        condition: service_healthy
      db:
        condition: service_healthy
```

Append a top-level section at the end of the file — `docker-compose.yml` has no
`volumes:` block today, so this is a new top-level key, at column 0:

```yaml
volumes:
  # Postgres data directory. Survives `docker compose down`; removed only by
  # `docker compose down -v`, which is the command that deletes the trade
  # history. Part 6's backup drill exists so that is survivable.
  pgdata:
```

- [ ] **Step 4: Document it**

Append to `.env.example`:

```
# --- Database ---

# Postgres connection URL used by both the bot and the admin container. The
# host is the compose service name, not localhost -- inside the network `db`
# resolves to the database container. The password here must match
# POSTGRES_PASSWORD below.
DATABASE_URL=postgresql+psycopg://swingbot:change-me@db:5432/swingbot

# Consumed by the db container the FIRST time it starts, to create the
# swingbot role. Changing it later does not change the existing role's
# password -- ALTER ROLE, or delete the pgdata volume and re-import.
POSTGRES_PASSWORD=change-me

# Per-store migration stages: name:stage pairs, comma separated.
#   json  files only (today's behavior; the default for any store not listed)
#   dual  write both, read files, log divergence
#   db    Postgres only
# Example: DB_STORES=trades:db,plans:dual
DB_STORES=
```

In `docs/deploy/DOCKER.md`, add a section documenting the `db` service:
the image pin and why a major-version jump needs a dump/restore rather than a
restart; that PGDATA is a named volume and `down -v` destroys it; that the port
is deliberately unpublished and `docker compose exec db psql -U swingbot
swingbot` is the way in; and that `POSTGRES_PASSWORD` is only read on first
initialisation.

- [ ] **Step 5: Verify the service actually starts**

```bash
docker compose config >/dev/null && echo "compose file valid"
docker compose up -d db
docker compose exec db pg_isready -U swingbot -d swingbot
docker compose exec db psql -U swingbot -d swingbot -c "select version();"
```

Expected: `accepting connections`, and a `PostgreSQL 18.x` version string.
Leave the container running — the next tasks need it.

- [ ] **Step 6: Run the test to verify it passes**

```bash
python scripts/dev/testrun.py file tests/db/test_compose.py
```

Expected: `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example docs/deploy/DOCKER.md tests/db/test_compose.py
git commit -m "feat(v67): add the postgres service, volume and health gate"
```

---

### Task P1-04: Schema registry and the trades table

`schema.py` holds SQLAlchemy Core `Table` definitions and the `PROMOTED` tuple
that goes with each one. A registration helper keeps the two in lockstep, so a
table can never exist with no promoted set and a promoted set can never name a
column that is not there.

**Files:**
- Create: `swingbot/core/db/schema.py`
- Test: `tests/db/test_schema.py`

**Interfaces:**
- Consumes: `RESERVED_KEYS` from `codec` (P1-01).
- Produces:
  - `METADATA: sqlalchemy.MetaData`
  - `standard_columns() -> list[Column]` — the `doc` + `updated_at` pair
  - `register(table: Table, promoted: Sequence[str]) -> Table`
  - `PROMOTED: dict[str, tuple[str, ...]]` — keyed by table name
  - `promoted_for(table_name: str) -> tuple[str, ...]`
  - `trades: Table`

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_schema.py`:

```python
"""The schema registry keeps Table definitions and PROMOTED in lockstep."""
import pytest
import sqlalchemy as sa

from swingbot.core.db import schema


def test_every_registered_table_has_the_standard_columns():
    for name, table in schema.METADATA.tables.items():
        assert "doc" in table.c, f"{name} has no doc column"
        assert "updated_at" in table.c, f"{name} has no updated_at column"
        assert table.c.doc.nullable is False
        assert table.c.updated_at.nullable is False


def test_every_registered_table_has_a_promoted_entry():
    assert set(schema.METADATA.tables) == set(schema.PROMOTED)


def test_promoted_names_all_exist_as_columns():
    for name, promoted in schema.PROMOTED.items():
        cols = set(schema.METADATA.tables[name].c.keys())
        assert set(promoted) <= cols, f"{name}: {set(promoted) - cols} not columns"


def test_promoted_never_includes_an_infrastructure_column():
    from swingbot.core.db.codec import RESERVED_KEYS
    for name, promoted in schema.PROMOTED.items():
        assert not RESERVED_KEYS.intersection(promoted), name


def test_register_rejects_a_promoted_name_that_is_not_a_column():
    meta = sa.MetaData()
    t = sa.Table("bogus", meta, sa.Column("a", sa.Text), *schema.standard_columns())
    with pytest.raises(ValueError, match="not a column"):
        schema.register(t, ("a", "nope"))


def test_trades_table_shape():
    t = schema.trades
    assert t.name == "trades"
    assert t.c.trade_id.unique is True
    assert t.c.trade_id.nullable is False
    for col in ("ticker", "strategy", "horizon", "direction", "status", "opened_at"):
        assert t.c[col].nullable is False, col
    assert t.c.closed_at.nullable is True
    assert schema.promoted_for("trades") == (
        "trade_id", "ticker", "strategy", "horizon", "direction",
        "status", "opened_at", "closed_at", "entry", "stop_loss",
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_schema.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.schema'`.

- [ ] **Step 3: Write the schema module**

Create `swingbot/core/db/schema.py`:

```python
"""Table definitions and their promoted-column sets.

Promotion criteria, so the choice is not made by taste -- promote a field only
when it is filtered or sorted on in a hot path, needs a NOT NULL/CHECK
constraint, or participates in a foreign key. Everything else stays in doc
indefinitely: under-promoting costs a slow query, over-promoting costs a
migration, and only the first is cheap to fix.

One further clause, from codec.merge_doc: promote only a field whose absence
and whose None mean the same thing, because a NULL promoted column comes back
as an absent key.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from swingbot.core.db.codec import RESERVED_KEYS

METADATA = sa.MetaData()

# table name -> promoted column names, in declaration order.
PROMOTED: dict[str, tuple[str, ...]] = {}


def standard_columns() -> list[sa.Column]:
    """The two columns every table in this schema carries."""
    return [
        sa.Column("doc", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def register(table: sa.Table, promoted: Sequence[str]) -> sa.Table:
    """Record `table`'s promoted set, validating it against the columns."""
    columns = set(table.c.keys())
    missing = [name for name in promoted if name not in columns]
    if missing:
        raise ValueError(f"{table.name}: {missing} not a column on this table")
    clash = RESERVED_KEYS.intersection(promoted)
    if clash:
        raise ValueError(
            f"{table.name}: {sorted(clash)} are infrastructure columns and "
            f"must never be promoted -- they are not part of a record"
        )
    PROMOTED[table.name] = tuple(promoted)
    return table


def promoted_for(table_name: str) -> tuple[str, ...]:
    return PROMOTED[table_name]


trades = register(
    sa.Table(
        "trades", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        # The application's own identifier, carried in every record since long
        # before this migration. The surrogate id exists only so the primary
        # key is never something a record can change.
        sa.Column("trade_id", sa.Text, nullable=False, unique=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("entry", sa.Numeric),
        sa.Column("stop_loss", sa.Numeric),
        *standard_columns(),
        # Every analytics read filters by ticker and orders by open date; the
        # GIN index makes doc->>'anything' searchable without promoting it,
        # which is what keeps adding a field free.
        sa.Index("trades_ticker_opened_idx", "ticker", sa.text("opened_at DESC")),
        sa.Index("trades_status_idx", "status"),
        sa.Index("trades_doc_gin", "doc", postgresql_using="gin"),
    ),
    ("trade_id", "ticker", "strategy", "horizon", "direction",
     "status", "opened_at", "closed_at", "entry", "stop_loss"),
)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/db/test_schema.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/schema.py tests/db/test_schema.py
git commit -m "feat(v67): add the schema registry and the trades table"
```

---

