# v67 — Part 1: Foundation (tasks P1-10…P1-14)

> Continuation of `2026-08-29-v67-json-to-postgres_1b-foundation-harness.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P1-10: The DB_STORES stage resolver

Turns the `DB_STORES` string into a per-store stage. Every store's migration in
Parts 2–5 branches on this, so it lands before any of them.

**Files:**
- Create: `swingbot/core/db/stages.py`
- Test: `tests/db/test_stages.py`

**Interfaces:**
- Consumes: `config.DB_STORES` (P1-02).
- Produces:
  - `JSON = "json"`, `DUAL = "dual"`, `DB = "db"`, `STAGES = (JSON, DUAL, DB)`
  - `parse(raw: str) -> dict[str, str]`
  - `stage_for(store: str) -> str`
  - `writes_json(store) -> bool`, `writes_db(store) -> bool`, `reads_db(store) -> bool`

**Design decision to honour:** a malformed entry is **logged loudly and
ignored**, leaving that store at `json`. It does not raise. A typo must never be
able to promote a store to `db`, and it must never be able to kill the bot on a
config reload either — falling back to today's behavior is the only outcome
that is safe in both directions.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_stages.py`:

```python
"""DB_STORES parsing: a typo must fall back to json, never to db, never raise."""
import pytest

from swingbot import config
from swingbot.core.db import stages


def test_empty_config_means_every_store_is_json(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    assert stages.stage_for("trades") == stages.JSON


def test_a_store_not_listed_defaults_to_json(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert stages.stage_for("plans") == stages.JSON


@pytest.mark.parametrize("raw,expected", [
    ("trades:db", "db"),
    ("plans:dual,trades:db", "db"),
    ("  trades : db , plans:dual ", "db"),
    ("TRADES:DB", "db"),
])
def test_parsing_is_whitespace_and_case_tolerant(monkeypatch, raw, expected):
    monkeypatch.setattr(config, "DB_STORES", raw)
    assert stages.stage_for("trades") == expected


@pytest.mark.parametrize("raw", [
    "trades:postgres",   # not a stage
    "trades",            # no colon
    "trades:db:extra",   # too many parts
    ":db",               # no store
    "trades:",           # no stage
])
def test_a_malformed_entry_falls_back_to_json_and_never_raises(monkeypatch, caplog, raw):
    monkeypatch.setattr(config, "DB_STORES", raw)
    with caplog.at_level("ERROR"):
        assert stages.stage_for("trades") == stages.JSON
    assert "DB_STORES" in caplog.text


def test_one_bad_entry_does_not_discard_the_good_ones(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:nonsense,plans:db")
    assert stages.stage_for("trades") == stages.JSON
    assert stages.stage_for("plans") == stages.DB


@pytest.mark.parametrize("stage,json_w,db_w,db_r", [
    ("json", True, False, False),
    ("dual", True, True, False),
    ("db", False, True, True),
])
def test_the_three_predicates(monkeypatch, stage, json_w, db_w, db_r):
    monkeypatch.setattr(config, "DB_STORES", f"trades:{stage}")
    assert stages.writes_json("trades") is json_w
    assert stages.writes_db("trades") is db_w
    assert stages.reads_db("trades") is db_r


def test_a_later_entry_wins_over_an_earlier_duplicate(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db,trades:json")
    assert stages.stage_for("trades") == stages.JSON
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_stages.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.stages'`.

- [ ] **Step 3: Write the resolver**

Create `swingbot/core/db/stages.py`:

```python
"""Per-store migration stage, read from config.DB_STORES.

Stage selection is per store, not a global switch, so a store mid-migration
does not block the others and a rollback is one .env edit plus a reload rather
than a redeploy.
"""
from __future__ import annotations

import logging

from swingbot import config

log = logging.getLogger(__name__)

JSON = "json"
DUAL = "dual"
DB = "db"
STAGES = (JSON, DUAL, DB)


def parse(raw: str) -> dict[str, str]:
    """Parse a `name:stage,name:stage` string.

    A malformed entry is logged and skipped, leaving that store at the json
    default. It does not raise: a typo must be unable to promote a store to db
    AND unable to kill the process on a hot reload, and falling back to today's
    behavior is the only outcome that is safe in both directions.
    """
    out: dict[str, str] = {}
    for chunk in (raw or "").split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = [p.strip().lower() for p in entry.split(":")]
        if len(parts) != 2 or not parts[0] or parts[1] not in STAGES:
            log.error(
                "DB_STORES: ignoring malformed entry %r (expected name:stage "
                "with stage in %s) -- that store stays on json",
                entry, "/".join(STAGES),
            )
            continue
        out[parts[0]] = parts[1]
    return out


def stage_for(store: str) -> str:
    """The stage for `store`; json for anything not listed."""
    return parse(config.DB_STORES).get(store.lower(), JSON)


def writes_json(store: str) -> bool:
    return stage_for(store) in (JSON, DUAL)


def writes_db(store: str) -> bool:
    return stage_for(store) in (DUAL, DB)


def reads_db(store: str) -> bool:
    return stage_for(store) == DB
```

`parse()` re-reads `config.DB_STORES` on every call rather than caching. That is
a handful of string splits against a value that is hot-reloadable — caching it
would mean a stage change needing a restart, which is exactly the property the
strangler is built to avoid.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/db/test_stages.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/stages.py tests/db/test_stages.py
git commit -m "feat(v67): add the DB_STORES per-store stage resolver"
```

---

### Task P1-11: The dual-write divergence comparator

At the `dual` stage a store writes both and reads files. This is what turns that
stage into evidence rather than hope: it compares the two records field by field
and logs what differs. It never raises — at `dual` the file is still the source
of truth, and killing the bot over a formatting difference in the shadow copy
would be a self-inflicted outage.

**Files:**
- Create: `swingbot/core/db/dual.py`
- Test: `tests/db/test_dual.py`

**Interfaces:**
- Consumes: nothing beyond the standard library.
- Produces:
  - `normalise(value) -> Any` — comparison-normal form
  - `diff_records(json_record: dict, db_record: dict) -> list[str]` — differing
    field names, sorted
  - `compare_and_log(store: str, key: str, json_record: dict, db_record: dict | None) -> list[str]`

**Why a normaliser at all:** the two paths cannot produce byte-identical
records, and pretending otherwise would make every dual-write log noise nobody
reads. `Decimal("1.50")` from a `NUMERIC` column and `1.5` from JSON are the
same number; a `datetime` and its ISO string are the same instant; a tuple
round-trips through JSONB as a list. Those four are normalised. **Everything
else that differs is reported** — the normaliser exists to remove
representation noise, never to hide a real divergence.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_dual.py`:

```python
"""Dual-stage comparison: representation noise is normalised away, real
differences are reported, nothing raises."""
import datetime as dt
import logging
from decimal import Decimal

from swingbot.core.db import dual


def test_identical_records_differ_in_nothing():
    rec = {"trade_id": "T1", "entry": 1.5, "notes": {"a": 1}}
    assert dual.diff_records(rec, dict(rec)) == []


def test_decimal_and_float_are_the_same_number():
    assert dual.diff_records({"entry": 1.5}, {"entry": Decimal("1.50")}) == []


def test_datetime_and_its_iso_string_are_the_same_instant():
    when = dt.datetime(2026, 1, 2, 15, 0, tzinfo=dt.timezone.utc)
    assert dual.diff_records({"opened_at": when.isoformat()},
                             {"opened_at": when}) == []


def test_a_tuple_and_a_list_are_equal_after_a_jsonb_round_trip():
    assert dual.diff_records({"legs": (1, 2)}, {"legs": [1, 2]}) == []


def test_a_real_value_difference_is_reported():
    assert dual.diff_records({"entry": 1.5}, {"entry": 1.6}) == ["entry"]


def test_a_missing_field_on_either_side_is_reported():
    assert dual.diff_records({"a": 1, "b": 2}, {"a": 1}) == ["b"]
    assert dual.diff_records({"a": 1}, {"a": 1, "b": 2}) == ["b"]


def test_nested_differences_are_reported_by_top_level_field():
    assert dual.diff_records({"notes": {"a": 1}}, {"notes": {"a": 2}}) == ["notes"]


def test_float_comparison_tolerates_round_trip_precision():
    assert dual.diff_records({"entry": 0.1 + 0.2}, {"entry": 0.3}) == []
    assert dual.diff_records({"entry": 1.0}, {"entry": 1.000001}) == ["entry"]


def test_compare_and_log_reports_and_returns(caplog):
    with caplog.at_level(logging.WARNING):
        out = dual.compare_and_log("trades", "T1", {"entry": 1.5}, {"entry": 1.6})
    assert out == ["entry"]
    assert "trades" in caplog.text and "T1" in caplog.text and "entry" in caplog.text


def test_compare_and_log_is_quiet_when_they_match(caplog):
    with caplog.at_level(logging.WARNING):
        assert dual.compare_and_log("trades", "T1", {"a": 1}, {"a": 1}) == []
    assert caplog.text == ""


def test_a_missing_db_record_is_reported_not_raised(caplog):
    with caplog.at_level(logging.WARNING):
        out = dual.compare_and_log("trades", "T1", {"a": 1}, None)
    assert out == ["<missing from db>"]
    assert "T1" in caplog.text


def test_comparison_never_raises_on_an_unserialisable_value(caplog):
    class Weird:
        def __eq__(self, other): raise RuntimeError("boom")
        def __hash__(self): return 0
    with caplog.at_level(logging.WARNING):
        out = dual.compare_and_log("trades", "T1", {"x": Weird()}, {"x": 1})
    assert out == ["x"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_dual.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.dual'`.

- [ ] **Step 3: Write the comparator**

Create `swingbot/core/db/dual.py`:

```python
"""Compare a JSON-store record against its Postgres shadow at the dual stage.

This is what makes `dual` evidence rather than hope. It logs; it never raises.
At the dual stage the file is still the source of truth, so an exception here
would be a self-inflicted outage over a shadow copy.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from decimal import Decimal
from typing import Any

log = logging.getLogger(__name__)

# Relative tolerance for float comparison. A NUMERIC column round-tripping
# through float and a JSON float differ in the last bits; 1e-9 is far tighter
# than any price, size or R-multiple this repo records and far looser than
# representation noise.
_REL_TOL = 1e-9

MISSING = "<missing from db>"


def normalise(value: Any) -> Any:
    """Comparison-normal form.

    Removes representation noise only -- Decimal/float, datetime/ISO string,
    tuple/list, and dict values recursively. It must never collapse two values
    that are genuinely different; anything not listed here is returned as-is
    and compared with ==.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in value.items()}
    return value


def _equal(a: Any, b: Any) -> bool:
    a, b = normalise(a), normalise(b)
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=_REL_TOL, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    try:
        return bool(a == b)
    except Exception:  # noqa: BLE001 -- a comparison that raises is a difference
        return False


def diff_records(json_record: dict, db_record: dict) -> list[str]:
    """Field names that differ between the two records, sorted."""
    sentinel = object()
    keys = set(json_record) | set(db_record)
    out = []
    for key in keys:
        a = json_record.get(key, sentinel)
        b = db_record.get(key, sentinel)
        if a is sentinel or b is sentinel or not _equal(a, b):
            out.append(key)
    return sorted(out)


def compare_and_log(store: str, key: str, json_record: dict,
                    db_record: dict | None) -> list[str]:
    """Compare and log. Returns the differing field names."""
    if db_record is None:
        log.warning("dual[%s] %s: record missing from the database", store, key)
        return [MISSING]
    differing = diff_records(json_record, db_record)
    if differing:
        log.warning(
            "dual[%s] %s: %d field(s) diverge: %s",
            store, key, len(differing), ", ".join(differing),
        )
    return differing
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/db/test_dual.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/dual.py tests/db/test_dual.py
git commit -m "feat(v67): add the dual-write divergence comparator"
```

---

### Task P1-12: NOTIFY triggers

The DDL half of the live-updates replacement: one shared trigger function
parameterised by channel, plus a helper that emits a notification from
application code. Part 3 replaces the mtime watcher with the listener half.

**Files:**
- Create: `swingbot/core/db/notify.py`
- Create: `swingbot/core/db/migrations/versions/p1_003_notify_function.py`
- Test: `tests/db/test_notify_ddl.py`

**Interfaces:**
- Consumes: `get_engine` (P1-02), `db_conn` (P1-07).
- Produces:
  - `NOTIFY_FUNCTION_SQL: str` — `CREATE OR REPLACE FUNCTION swingbot_notify()`
  - `trigger_ddl(table: str, channel: str) -> str`
  - `drop_trigger_ddl(table: str) -> str`
  - `trigger_name(table: str) -> str`
  - `emit(conn, channel: str, payload: str = "") -> None`
  - `CHANNELS: tuple[str, ...]` — the nine SSE concerns, copied from
    `swingbot/admin/events/watcher.py`: `trades`, `account`, `analytics`,
    `scan`, `journal`, `bot`, `risk`, `watchlist`, `jobs`

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_notify_ddl.py`:

```python
"""Trigger DDL. The listening half is Part 3; this is what fires."""
import pytest
import sqlalchemy as sa

from swingbot.core.db import notify


def test_channels_match_the_watcher_concerns():
    # The SPA contract does not change: same event names, same semantics.
    assert notify.CHANNELS == (
        "trades", "account", "analytics", "scan",
        "journal", "bot", "risk", "watchlist", "jobs",
    )


def test_trigger_ddl_names_the_table_and_the_channel():
    sql = notify.trigger_ddl("trades", "trades")
    assert "AFTER INSERT OR UPDATE OR DELETE ON trades" in sql
    assert "FOR EACH STATEMENT" in sql
    assert "swingbot_notify('trades')" in sql


def test_trigger_ddl_rejects_an_unknown_channel():
    with pytest.raises(ValueError, match="not a known channel"):
        notify.trigger_ddl("trades", "made_up")


@pytest.mark.parametrize("bad", ["tra des", "trades; drop table x", "'x'"])
def test_trigger_ddl_rejects_a_non_identifier_table(bad):
    # These strings are interpolated into DDL. An identifier check is the only
    # thing between this helper and a table name that carries a semicolon.
    with pytest.raises(ValueError, match="identifier"):
        notify.trigger_ddl(bad, "trades")


def test_the_function_and_trigger_install_and_fire(db_conn):
    from swingbot.core.db.schema import trades as trades_table

    db_conn.execute(sa.text(notify.NOTIFY_FUNCTION_SQL))
    db_conn.execute(sa.text(notify.trigger_ddl("trades", "trades")))
    db_conn.execute(sa.text("LISTEN trades"))
    db_conn.execute(sa.insert(trades_table).values(
        trade_id="N1", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="LONG", status="open", opened_at="2026-01-02T15:00:00+00:00"))
    # No commit here, so nothing is DELIVERED -- NOTIFY queues until commit.
    # What this asserts is that the trigger EXECUTED without error, which is
    # the failure mode a typo in the DDL produces. Delivery is P1-13's test.
    installed = db_conn.execute(sa.text(
        "select count(*) from pg_trigger where tgname = :n"
    ), {"n": notify.trigger_name("trades")}).scalar_one()
    assert installed == 1


def test_emit_sends_a_notification_without_a_trigger(db_conn):
    notify.emit(db_conn, "scan", "tick")
    # Same caveat as above: queued, not delivered, until commit.
    assert db_conn.execute(sa.text("select 1")).scalar_one() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/db/test_notify_ddl.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.notify'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/db/notify.py`:

```python
"""LISTEN/NOTIFY: the replacement for the admin UI's mtime watcher.

The watcher stat()s 19 paths every 0.5s and emits one event per concern. Those
concern names are the SPA's contract and do not change -- triggers fire on the
same nine channels, and Part 3 swaps the polling loop for a listener.
"""
from __future__ import annotations

import re

import sqlalchemy as sa

# The nine concerns swingbot/admin/events/watcher.py emits. Copied, not
# imported: admin/ must not become a dependency of core/db/, and a test in
# Part 3 asserts the two lists stay identical.
CHANNELS: tuple[str, ...] = (
    "trades", "account", "analytics", "scan",
    "journal", "bot", "risk", "watchlist", "jobs",
)

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

# One function for every table, with the channel passed as a trigger argument.
# STATEMENT-level, not ROW-level: a scan tick writes many rows in one statement
# and the client should refetch once. The 0.25s debounce on the listener side
# handles the rest.
NOTIFY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION swingbot_notify() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify(TG_ARGV[0], '');
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


def _check_identifier(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(
            f"{name!r} is not a plain lowercase SQL identifier; it is "
            f"interpolated into DDL and must not be user input"
        )
    return name


def trigger_name(table: str) -> str:
    return f"{_check_identifier(table)}_notify_trg"


def trigger_ddl(table: str, channel: str) -> str:
    """DDL installing the notify trigger on `table`, firing on `channel`."""
    _check_identifier(table)
    if channel not in CHANNELS:
        raise ValueError(
            f"{channel!r} is not a known channel; expected one of "
            f"{', '.join(CHANNELS)}"
        )
    return (
        f"CREATE TRIGGER {trigger_name(table)} "
        f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION swingbot_notify('{channel}')"
    )


def drop_trigger_ddl(table: str) -> str:
    return f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {_check_identifier(table)}"


def emit(conn: sa.Connection, channel: str, payload: str = "") -> None:
    """Emit a notification from application code, for the cases with no table
    write behind them. Delivered on commit, like any NOTIFY."""
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a known channel")
    conn.execute(sa.text("SELECT pg_notify(:c, :p)"), {"c": channel, "p": payload})
```

- [ ] **Step 4: Write the migration**

Create `swingbot/core/db/migrations/versions/p1_003_notify_function.py`:

```python
"""install the shared swingbot_notify() trigger function

Revision ID: p1_003
Revises: p1_002

The function only; per-table triggers are installed by the migration that
creates each table, in the part that owns it.
"""
from alembic import op

from swingbot.core.db.notify import NOTIFY_FUNCTION_SQL, trigger_ddl

revision = "p1_003"
down_revision = "p1_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(NOTIFY_FUNCTION_SQL)
    op.execute(trigger_ddl("trades", "trades"))


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trades_notify_trg ON trades")
    op.execute("DROP FUNCTION IF EXISTS swingbot_notify()")
```

- [ ] **Step 5: Run it and the tests**

```bash
alembic upgrade head
docker compose exec db psql -U swingbot -d swingbot -c "\df swingbot_notify"
python scripts/dev/testrun.py file tests/db/test_notify_ddl.py
```

Expected: the function listed, and `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/notify.py swingbot/core/db/migrations/versions/p1_003_notify_function.py tests/db/test_notify_ddl.py
git commit -m "feat(v67): add NOTIFY trigger DDL and the shared function"
```

---

### Task P1-13: The listener, and the committing test tier

`NOTIFY` is delivered on commit, so this is the one thing rollback isolation
cannot test. It gets the `slow` marker and the `db_committed` fixture.

**Files:**
- Modify: `swingbot/core/db/notify.py` (add `listen`)
- Test: `tests/db/test_notify_delivery.py`

**Interfaces:**
- Consumes: `CHANNELS`, `emit` (P1-12); `db_committed` (P1-07);
  `config.DATABASE_URL` (P1-02).
- Produces:
  - `listen(channels: Sequence[str], on_event: Callable[[str], None], stop: threading.Event, *, poll: float = 0.5, dsn: str | None = None) -> None`
    — blocks until `stop` is set, calling `on_event(channel)` per notification.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_notify_delivery.py`:

```python
"""Delivery only happens on commit, so these tests commit -- and are slow."""
import threading
import time

import pytest
import sqlalchemy as sa

from swingbot.core.db import notify
from swingbot.core.db.schema import trades

pytestmark = pytest.mark.slow


def _run_listener(channels, seen, stop, dsn):
    notify.listen(channels, seen.append, stop, poll=0.1, dsn=dsn)


@pytest.fixture
def listener(db_engine):
    seen: list[str] = []
    stop = threading.Event()
    dsn = db_engine.url.render_as_string(hide_password=False)
    thread = threading.Thread(
        target=_run_listener, args=(["trades", "scan"], seen, stop, dsn), daemon=True)
    thread.start()
    time.sleep(0.5)   # let LISTEN register before the first write
    yield seen
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "listener did not stop when asked"


def _wait_for(seen, channel, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if channel in seen:
            return True
        time.sleep(0.05)
    return False


def test_a_committed_insert_delivers_on_the_table_channel(listener, db_committed):
    with db_committed.begin():
        db_committed.execute(sa.insert(trades).values(
            trade_id="NOTIFY-1", ticker="AAPL", strategy="RSI", horizon="2w",
            direction="LONG", status="open",
            opened_at="2026-01-02T15:00:00+00:00"))
    assert _wait_for(listener, "trades"), f"no 'trades' notification; saw {listener}"


def test_an_explicit_emit_delivers(listener, db_committed):
    with db_committed.begin():
        notify.emit(db_committed, "scan")
    assert _wait_for(listener, "scan"), f"no 'scan' notification; saw {listener}"


def test_a_rolled_back_write_delivers_nothing(listener, db_conn):
    db_conn.execute(sa.insert(trades).values(
        trade_id="NOTIFY-2", ticker="MSFT", strategy="RSI", horizon="2w",
        direction="LONG", status="open", opened_at="2026-01-02T15:00:00+00:00"))
    # db_conn rolls back at teardown; give delivery a chance to be wrong.
    time.sleep(0.5)
    assert "trades" not in listener


def test_listen_rejects_an_unknown_channel(db_engine):
    with pytest.raises(ValueError, match="not a known channel"):
        notify.listen(["made_up"], lambda _c: None, threading.Event(),
                      dsn=db_engine.url.render_as_string(hide_password=False))
```

`test_a_committed_insert_delivers_on_the_table_channel` requires the trigger
from P1-12's migration on the test database. `db_engine` builds the schema from
`METADATA`, which carries no triggers — so add the function and trigger to the
`db_engine` fixture in `tests/db/conftest.py`, right after `METADATA.create_all`:

```python
    from swingbot.core.db.notify import NOTIFY_FUNCTION_SQL, trigger_ddl
    with engine.begin() as conn:
        conn.execute(sa.text(NOTIFY_FUNCTION_SQL))
        conn.execute(sa.text(trigger_ddl("trades", "trades")))
```

Each part adds its own tables' triggers to this block as it creates them.

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/db/test_notify_delivery.py -q
```

Expected: `AttributeError: module 'swingbot.core.db.notify' has no attribute 'listen'`.

- [ ] **Step 3: Write the listener**

Append to `swingbot/core/db/notify.py`:

```python
def listen(channels: "Sequence[str]", on_event: "Callable[[str], None]",
           stop: "threading.Event", *, poll: float = 0.5,
           dsn: str | None = None) -> None:
    """Block, calling `on_event(channel)` for every notification received.

    Uses a raw psycopg connection rather than the SQLAlchemy pool: LISTEN is
    session state, and a pooled connection that gets recycled silently stops
    listening. Returns when `stop` is set.
    """
    import psycopg
    from psycopg import sql

    for channel in channels:
        if channel not in CHANNELS:
            raise ValueError(f"{channel!r} is not a known channel")

    url = dsn or config.DATABASE_URL
    # psycopg wants a libpq DSN, not SQLAlchemy's driver-qualified URL.
    conninfo = url.replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(conninfo, autocommit=True) as conn:
        for channel in channels:
            conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
        log.info("Listening on %s", ", ".join(channels))
        while not stop.is_set():
            # Yields notifications as they arrive and returns when `poll`
            # elapses, so `stop` is checked at least that often.
            for note in conn.notifies(timeout=poll):
                try:
                    on_event(note.channel)
                except Exception:  # noqa: BLE001
                    log.exception("notify handler raised for channel %s", note.channel)
                if stop.is_set():
                    break
```

Add to the module's imports:

```python
import logging
import threading  # noqa: F401 -- type annotation only
from typing import Callable, Sequence

from swingbot import config

log = logging.getLogger(__name__)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/db/test_notify_delivery.py -q
```

Expected: `0 failed`. These carry `slow`, so `testrun.py fast` skips them —
which is why this step names raw pytest.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/notify.py tests/db/conftest.py tests/db/test_notify_delivery.py
git commit -m "feat(v67): add the NOTIFY listener and its committing test tier"
```

---

### Task P1-14: The lost-update regression, and the architecture entry

Success criterion 7, and the reason this plan exists. The test proves the DB
path is safe **and** that the file path is not, in the same file, so nobody has
to take the spec's word for the bug.

Neither half is `xfail`: an `xfail` would break this repo's `0 xfailed` gate,
and asserting the loss is the stronger statement anyway — it says the current
behavior is known and characterised, not merely expected to fail.

The `docs/claude/architecture.md` entry lands here because Part 1 is finished at
this point and there is now something true to write about `core/db/`.

**Files:**
- Create: `tests/db/test_lost_update.py`
- Modify: `docs/claude/architecture.md`

**Interfaces:**
- Consumes: `Repository` (P1-09), `trades` (P1-04), `db_engine`/`db_committed`
  (P1-07), `swingbot.core.infra.jsonio` (existing).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the test**

Create `tests/db/test_lost_update.py`:

```python
"""Two writers, one record.

The file half characterises the bug this plan exists to fix: TradeLog._save()
and PlanStore._save() serialise an entire in-memory list over the whole file on
every write, guarded only by a module-level threading.Lock -- which protects
nothing across processes, and the bot and admin are separate containers sharing
a bind-mounted data/.

The database half proves the replacement does not have that property.
"""
import json
import os
import threading

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades
from swingbot.core.infra.jsonio import atomic_write_json, read_json

RECORD = dict(trade_id="RACE-1", ticker="AAPL", strategy="RSI", horizon="2w",
              direction="LONG", status="open",
              opened_at="2026-01-02T15:00:00+00:00",
              confidence=4, notes="original")


def test_the_file_store_loses_one_of_two_concurrent_updates(tmp_path):
    """Characterises current behavior. This is the bug, asserted."""
    path = os.path.join(tmp_path, "trades.json")
    atomic_write_json(path, [dict(RECORD)])

    # Both writers read the same snapshot -- the window reload() narrows but
    # cannot close, because there is no lock the other container can see.
    snapshot_a = read_json(path, [])
    snapshot_b = read_json(path, [])

    snapshot_a[0]["status"] = "closed"
    atomic_write_json(path, snapshot_a)

    snapshot_b[0]["confidence"] = 5
    atomic_write_json(path, snapshot_b)      # whole-file rewrite

    final = read_json(path, [])[0]
    assert final["confidence"] == 5          # the second writer's change
    assert final["status"] == "open", (
        "the file store unexpectedly kept both writes -- if this now passes as "
        "'closed', the JSON path changed and this characterisation is stale"
    )


def test_the_repository_keeps_both_concurrent_updates(db_conn):
    repo = Repository(trades, key="trade_id")
    repo.insert(dict(RECORD), conn=db_conn)

    # Two patches, each naming only its own field. No read-modify-write, so
    # there is no snapshot to go stale.
    repo.patch("RACE-1", {"status": "closed"}, conn=db_conn)
    repo.patch("RACE-1", {"confidence": 5}, conn=db_conn)

    final = repo.get("RACE-1", conn=db_conn)
    assert final["status"] == "closed"
    assert final["confidence"] == 5
    assert final["notes"] == "original"


@pytest.mark.slow
def test_two_real_connections_do_not_lose_an_update(db_engine, db_committed):
    """The same claim, but with two genuine connections committing
    independently -- the shape the bot and admin containers actually have."""
    repo = Repository(trades, key="trade_id")
    with db_committed.begin():
        repo.insert(dict(RECORD), conn=db_committed)

    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []

    def writer(changes):
        try:
            with db_engine.begin() as conn:
                barrier.wait()
                Repository(trades, key="trade_id").patch("RACE-1", changes, conn=conn)
        except BaseException as exc:       # noqa: BLE001 -- reported, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=({"status": "closed"},)),
               threading.Thread(target=writer, args=({"confidence": 5},))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"a writer raised: {errors}"
    final = repo.get("RACE-1", conn=db_committed)
    assert final["status"] == "closed"
    assert final["confidence"] == 5
```

- [ ] **Step 2: Run the tests**

```bash
python -m pytest tests/db/test_lost_update.py -q
```

Expected: `0 failed`, 3 passed. If the file half fails, the JSON stores changed
since the spec was written — update the characterisation and say so in the
commit; do not delete the test.

- [ ] **Step 3: Document the package**

In `docs/claude/architecture.md`, add a `swingbot/core/db/` section to the
module map covering: the doc/column codec and why call sites still see flat
dicts; that nothing outside `core/db/` imports SQLAlchemy; the fail-fast policy
and how it differs from `jsonio.py`'s; `DB_STORES` and the three stages; and
that Alembic revision ids are explicit and part-prefixed.

Keep it to the length of the neighbouring package entries — this file is read
before touching `swingbot/core`, so it is a map, not a manual. The manual is
the spec.

- [ ] **Step 4: Verify the whole part's tests together**

This is the one place in Part 1 where the blast radius genuinely crosses files,
so the fast tier is the right call rather than a single file:

```bash
python scripts/dev/testrun.py fast
```

Expected: `0 failed`, `0 xfailed`. **Not** `full` — that is P6-12's job.

- [ ] **Step 5: Commit**

```bash
git add tests/db/test_lost_update.py docs/claude/architecture.md
git commit -m "test(v67): pin the lost-update bug and its fix"
```

---

## Part 1 exit criteria

Before any of Parts 2–5 starts, all of these must hold:

1. `docker compose up -d db` and `docker compose --profile test up -d db-test`
   both come up healthy.
2. `alembic upgrade head` runs clean on an empty database, and
   `alembic downgrade base` reverses it.
3. `alembic heads` returns exactly one head: `p1_003`.
4. `python scripts/dev/testrun.py fast` is green.
5. `python -m pytest tests/db/ -q` is green, including the `slow` tier.
6. Part 1 is merged to `main` — Parts 2–5 branch from it, not from each other.
