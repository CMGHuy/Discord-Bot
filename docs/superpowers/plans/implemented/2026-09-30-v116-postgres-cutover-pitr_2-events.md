# v116 — Part 2: Phase 1, live events

Header, global constraints, revision ids and the full parallelisation map: `_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 1.

**Parallelisation (Phase 1):**
- **Sequential:** V116-11 first — the merge every other task in this phase builds on (`swingbot/core/db/events.py`, `db_listener.py` and `p3_007` exist only after it). V116-12 next — it creates the two tables, their repositories and the `store_db` fixture that V116-13 and V116-14 consume.
- **Group (parallel, after V116-12):** V116-13 (`progress_store.py`, `admin/events/watcher.py`, `tests/admin/test_no_double_watcher.py`), V116-14 (`data_refresh.py`), V116-15 (`admin/events/db_listener.py`, `core/db/notify.py`). Disjoint files; none consumes a symbol another introduces (V116-15 needs only V116-11).
- Phase 1 shares no file with Phase 0 (group A), so the two phases run in parallel.

If the worktree does not exist yet, create it exactly as `_1a-pitr.md` shows. Every command runs from the worktree root. Tests that touch Postgres need `docker compose --profile test up -d db-test`.

---

# Phase 1 — Live events

### Task V116-11: Review and merge the v67 notify-events branch

**Files:**
- No new files. Merges branch `2026-09-30-v67-p3-18-notify-events` (tip `b31835b9`, 10 commits, v67 P3-18…P3-24) into the v116 branch.

**Interfaces:**
- Consumes: the branch as it stands. **Do not rebuild anything it contains.**
- Produces (from the branch, now on the v116 branch): Alembic `p3_007` (head, down `p6_001`); `swingbot/core/db/events.py::TABLE_CHANNELS`; `swingbot/admin/events/db_listener.py::DbEventListener(emit, *, channels=None, debounce=DEBOUNCE, clock=time.monotonic, dsn=None)` with `on_notification`, `flush`, `start`, `stop`, `_run`, `_on_event`; `notify.listen(channels, on_event, stop, *, poll=0.5, dsn=None)` calling `on_event(None)` on quiet polls; `broker._default_watcher` switching on `stages.reads_db("events")`; `watcher._TABLE_BACKED` and `watcher.residual_paths()`; `runstate.scan_paused_at()`, `runstate.trigger_requested_at()`, `runstate.request_trigger(payload=None)`; `app.scan_status_payload()` reading flags through `runstate`.

- [ ] **Step 1: Review the branch**

```bash
git log --oneline main..2026-09-30-v67-p3-18-notify-events
git diff main...2026-09-30-v67-p3-18-notify-events --stat
git merge-tree --write-tree HEAD 2026-09-30-v67-p3-18-notify-events >/dev/null && echo CLEAN
```

Expected: the ten commits `8d31f590 … b31835b9`; 21 files, +1027/−89; `CLEAN` (checked while planning: `main` moved 18 commits since the merge base `68b6c6bd` and touched none of the branch's files). Then read each commit with `git show <sha>` and check, writing one line per item into the merge message:

1. `p3_007` is idempotent (drop-if-exists then create per `TABLE_CHANNELS` table) and its downgrade is a deliberate no-op.
2. `events.TABLE_CHANNELS` names only tables in `schema.METADATA`, and only channels in `notify.CHANNELS`.
3. `DbEventListener` debounces per concern and survives a raising `emit`.
4. `broker._default_watcher` builds `_CompositeWatcher(DbEventListener, FileWatcher(residual_paths()))` only at `events:db`, else a plain `FileWatcher`.
5. `admin/app.py` and `api_v1/system.py` no longer build their own `.flag` paths.
6. The listener does **not** reconnect: `_run` logs "event listener stopped" and exits on any error. (V116-15 adds reconnect and `resync`; this is expected, not a review failure.)

- [ ] **Step 2: Merge**

```bash
git merge --no-ff 2026-09-30-v67-p3-18-notify-events -m "merge(v116): v67 P3-18..P3-24 -- NOTIFY triggers, db listener, runstate flag routing

Reviewed for v116 Phase 1:
1. <item 1 finding>
...
6. <item 6 finding>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: One Alembic head**

Run: `python -m alembic heads`
Expected: `p3_007 (head)`.

- [ ] **Step 4: Re-run the branch's own tests**

```bash
docker compose --profile test up -d db-test
python scripts/dev/testrun.py file tests/admin/test_broker_db_listener.py tests/admin/test_db_listener.py tests/admin/test_live_updates_e2e.py tests/admin/test_no_double_watcher.py tests/admin/test_scan_flags_stage.py tests/admin/test_sse_contract.py tests/admin/test_api_v1_system_scan.py tests/db/test_notify_delivery.py tests/db/test_part3_exit.py tests/db/test_trigger_coverage.py tests/db/test_migrations.py
```

Expected: `0 failed`, `0 xfailed`, and no skips among the DB tests (a skip means `db-test` is not up).

- [ ] **Step 5: The fast tier, because the merge reaches code `main` changed since**

Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`. A failure here is fixed forward in its own commit on the v116 branch (`fix(v116): …`), never by editing the v67 branch. **Do not delete the v67 branch or its worktree** (`_0-index.md` § Global Constraints).

---

### Task V116-12: `scan_progress` and `market_data_state` tables, repositories and migration

**Files:**
- Modify: `swingbot/core/db/schema.py` (append two tables)
- Create: `swingbot/core/db/migrations/versions/v116_001_live_state_tables.py`
- Modify: `swingbot/core/db/events.py` (`TABLE_CHANNELS`: two entries)
- Create: `swingbot/core/db/repositories/scan_progress.py`, `swingbot/core/db/repositories/market_data_state.py`
- Modify: `tests/db/test_migrations.py` (`ID_RE`)
- Modify: `tests/db/conftest.py` (new `store_db` fixture), `tests/conftest.py` (import it)
- Create: `tests/db/test_v116_live_state_tables.py`

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `Repository`, `engine.transaction`, `notify.trigger_ddl`/`drop_trigger_ddl` (all on `main`); `events.TABLE_CHANNELS`, Alembic head `p3_007` (V116-11).
- Produces: tables `scan_progress` and `market_data_state` (`id`, `key TEXT UNIQUE NOT NULL`, `doc`, `updated_at`; promoted `("key",)`); revision `v116_001`; `ScanProgressRepository` with `publish(record, *, conn=None)`, `read(*, conn=None) -> dict | None`, `clear(*, conn=None)`, singleton `scan_progress_repo()`, `KEY = "current"`; `MarketDataStateRepository` with `load(*, conn=None) -> dict[str, dict]`, `save(state, *, conn=None)`, singleton `market_data_state_repo()`; fixture `store_db` (points `config.DATABASE_URL` at the test database, resets the engine, yields the committing connection, truncates after). V116-13/14/16/17/20/21/22/23/25 use these.

- [ ] **Step 1: Write the failing tests**

In `tests/db/test_migrations.py`, change the pattern and add a test:

```python
ID_RE = re.compile(r"^(p[1-6]|v\d+)_\d{3}$")


def test_plan_prefixed_ids_are_accepted_and_malformed_ones_are_not():
    assert ID_RE.match("v116_001") and ID_RE.match("p3_007")
    assert not ID_RE.match("v116_1") and not ID_RE.match("x1_001") and not ID_RE.match("v_001")
```

Create `tests/db/test_v116_live_state_tables.py`:

```python
"""scan_progress and market_data_state: the last files that drive live
updates, as tables (v116 Phase 1). Ephemeral: at `db` they start empty."""
from swingbot.core.db import events, schema
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository


def test_both_tables_promote_only_a_unique_key():
    for name in ("scan_progress", "market_data_state"):
        table = schema.METADATA.tables[name]
        assert table.c.key.unique is True and table.c.key.nullable is False
        assert schema.promoted_for(name) == ("key",)


def test_both_raise_the_concern_whose_screen_shows_them():
    assert events.TABLE_CHANNELS["scan_progress"] == "scan"
    assert events.TABLE_CHANNELS["market_data_state"] == "watchlist"


def test_scan_progress_is_one_row_published_read_and_cleared(db_conn):
    repo = ScanProgressRepository()
    assert repo.read(conn=db_conn) is None
    repo.publish({"pct": 10, "stage": "crawling data"}, conn=db_conn)
    repo.publish({"pct": 55, "stage": "analyzing"}, conn=db_conn)
    assert repo.read(conn=db_conn) == {"pct": 55, "stage": "analyzing"}
    assert repo.count(conn=db_conn) == 1
    repo.clear(conn=db_conn)
    assert repo.read(conn=db_conn) is None


def test_market_data_state_save_replaces_the_whole_map(db_conn):
    repo = MarketDataStateRepository()
    repo.save({"AAPL|daily": {"last_status": "fresh", "fail_count": 0},
               "MSFT|daily": {"last_status": "failed", "fail_count": 2, "last_error": "x"}},
              conn=db_conn)
    repo.save({"AAPL|daily": {"last_status": "incremental", "fail_count": 0}}, conn=db_conn)
    assert repo.load(conn=db_conn) == {
        "AAPL|daily": {"last_status": "incremental", "fail_count": 0}}


def test_saving_an_empty_map_empties_the_table(db_conn):
    repo = MarketDataStateRepository()
    repo.save({"AAPL|daily": {"last_status": "fresh"}}, conn=db_conn)
    repo.save({}, conn=db_conn)
    assert repo.load(conn=db_conn) == {}


def test_store_db_points_the_app_engine_at_the_test_database(store_db):
    from swingbot.core.db.engine import get_engine
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("select 1").scalar() == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v116_live_state_tables.py tests/db/test_migrations.py`
Expected: FAIL — `ModuleNotFoundError: ...repositories.market_data_state`, `fixture 'store_db' not found`.

- [ ] **Step 3: Declare the tables** — append to `swingbot/core/db/schema.py`:

```python
# v116 Phase 1: the last two files that drove live updates. Ephemeral state --
# nothing is imported, and at the db stage both start empty.
scan_progress = register(sa.Table("scan_progress", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns()), ("key",))
market_data_state = register(sa.Table("market_data_state", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("key", sa.Text, nullable=False, unique=True), *standard_columns()), ("key",))
```

- [ ] **Step 4: The migration** — `swingbot/core/db/migrations/versions/v116_001_live_state_tables.py`:

```python
"""scan_progress and market_data_state, with their NOTIFY triggers

Revision ID: v116_001
Revises: p3_007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from swingbot.core.db.notify import drop_trigger_ddl, trigger_ddl

revision = "v116_001"
down_revision = "p3_007"
branch_labels = None
depends_on = None

# Restated rather than read from events.TABLE_CHANNELS: a revision is frozen
# at the moment it was written, and a later edit to the map must not change
# what this revision did.
_TABLES = (("scan_progress", "scan"), ("market_data_state", "watchlist"))


def _std():
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    for table, channel in _TABLES:
        op.create_table(table, sa.Column("id", sa.BigInteger, primary_key=True),
                        sa.Column("key", sa.Text, nullable=False, unique=True), *_std())
        op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    for table, _channel in reversed(_TABLES):
        op.execute(drop_trigger_ddl(table))
        op.drop_table(table)
```

- [ ] **Step 5: Map them to their concerns** — in `swingbot/core/db/events.py`, before the closing comment of `TABLE_CHANNELS`:

```python
    # v116 Phase 1. market_data_state drove no event as a file; its trigger
    # raises `watchlist`, the concern whose rows show data freshness.
    "scan_progress": "scan",
    "market_data_state": "watchlist",
```

- [ ] **Step 6: The repositories**

`swingbot/core/db/repositories/scan_progress.py`:

```python
"""The running scan's progress record: one row keyed `current` (v116).

A display artefact, deleted when the scan ends -- see progress_store.py."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import scan_progress

KEY = "current"


class ScanProgressRepository(Repository):
    def __init__(self):
        super().__init__(scan_progress, key="key")

    def publish(self, record: dict, *, conn=None) -> None:
        self.upsert({"key": KEY, **record}, conn=conn)

    def read(self, *, conn=None) -> dict | None:
        row = self.get(KEY, conn=conn)
        if row is None:
            return None
        return {name: value for name, value in row.items() if name != "key"}

    def clear(self, *, conn=None) -> None:
        self.delete(KEY, conn=conn)


_repo: ScanProgressRepository | None = None


def scan_progress_repo() -> ScanProgressRepository:
    global _repo
    if _repo is None:
        _repo = ScanProgressRepository()
    return _repo
```

`swingbot/core/db/repositories/market_data_state.py`:

```python
"""Market-data refresh bookkeeping, one row per `SYMBOL|timeframe` (v116).

The whole map is saved at once, exactly like the JSON file it replaces, so a
pair the refresh no longer tracks disappears from the table too."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import market_data_state


class MarketDataStateRepository(Repository):
    def __init__(self):
        super().__init__(market_data_state, key="key")

    def load(self, *, conn=None) -> dict[str, dict]:
        state: dict[str, dict] = {}
        for row in self.list_all(conn=conn):
            key = row.pop("key")
            state[key] = row
        return state

    def save(self, state: dict[str, dict], *, conn=None) -> None:
        with transaction(conn) as connection:
            connection.execute(sa.delete(market_data_state)
                               .where(market_data_state.c.key.notin_(list(state))))
            for key, record in state.items():
                self.upsert({**record, "key": key}, conn=connection)


_repo: MarketDataStateRepository | None = None


def market_data_state_repo() -> MarketDataStateRepository:
    global _repo
    if _repo is None:
        _repo = MarketDataStateRepository()
    return _repo
```

- [ ] **Step 7: The `store_db` fixture**

Append to `tests/db/conftest.py`:

```python
@pytest.fixture
def store_db(db_committed, db_engine, monkeypatch):
    """Stage-aware code under test reaches the test database through the
    app's own engine (config.DATABASE_URL); every table is truncated after
    the test by db_committed. Yields the committing connection for asserts."""
    from swingbot import config
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield db_committed
    reset_engine()
```

In `tests/conftest.py`, change the import line to:

```python
from tests.db.conftest import db_committed, db_conn, db_engine, db_engine_empty, store_db  # noqa: F401
```

- [ ] **Step 8: Run the tests, plus every schema/migration/trigger test**

Run: `python scripts/dev/testrun.py file tests/db/test_v116_live_state_tables.py tests/db/test_migrations.py tests/db/test_trigger_coverage.py tests/db/test_schema.py tests/db/test_part3_exit.py tests/db/test_notify_ddl.py`
Expected: PASS (`test_migrations_produce_exactly_the_declared_schema` proves `schema.py` and `v116_001` agree; `test_trigger_coverage` proves both triggers exist). `python -m alembic heads` → `v116_001 (head)`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v116_001_live_state_tables.py swingbot/core/db/events.py swingbot/core/db/repositories/scan_progress.py swingbot/core/db/repositories/market_data_state.py tests/db/test_migrations.py tests/db/conftest.py tests/conftest.py tests/db/test_v116_live_state_tables.py
git commit -m "feat(v116): scan_progress and market_data_state tables with NOTIFY triggers (v116_001)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-13: Scan progress goes through `stages`

**Files:**
- Modify: `swingbot/core/scanning/progress_store.py` (`publish`, `read`, `clear`; new `_write_file`, `_write_row`, `_read_file`, `_read_row`)
- Modify: `swingbot/admin/events/watcher.py` (`_TABLE_BACKED` gains `scan_progress.json`; two docstrings)
- Modify: `tests/admin/test_no_double_watcher.py` (the residual example)
- Create: `tests/scanning/test_progress_store_db.py`

**Interfaces:**
- Consumes: `scan_progress_repo()` and `store_db` (V116-12); `stages` (main).
- Produces: `progress_store.publish/read/clear` honour stage `scan_progress`. Unchanged contract: none of them ever raises (a progress bar never ends a scan and never 500s the admin). The admin's `scan_status_payload()["progress"]` is read through `progress_store.read()` and needs no change.

- [ ] **Step 1: Write the failing tests** — `tests/scanning/test_progress_store_db.py`:

```python
"""progress_store at each stage (v116 Phase 1). The record stays a display
artefact: no stage may raise into the scan or the admin."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository
from swingbot.core.scanning import progress_store
from swingbot.core.scanning.scan_run import ScanProgress


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _progress() -> ScanProgress:
    progress = ScanProgress()
    progress.stage, progress.total, progress.done = "analyzing", 10, 5
    return progress


def test_json_stage_writes_only_the_file(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    progress_store.publish(_progress())
    assert os.path.exists(data_dir / "scan_progress.json")
    assert progress_store.read()["pct"] == 66


def test_dual_writes_both_and_reads_the_file(data_dir, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:dual")
    progress_store.publish(_progress())
    assert os.path.exists(data_dir / "scan_progress.json")
    assert ScanProgressRepository().read(conn=store_db)["pct"] == 66
    progress_store.clear()
    assert ScanProgressRepository().read(conn=store_db) is None
    assert not os.path.exists(data_dir / "scan_progress.json")


def test_db_stage_writes_and_reads_only_the_row(data_dir, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:db")
    progress_store.publish(_progress())
    assert not os.path.exists(data_dir / "scan_progress.json")
    assert progress_store.read()["stage"] == "analyzing"
    progress_store.clear()
    assert progress_store.read() is None


def test_an_unreachable_database_never_raises(data_dir, monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:db")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        progress_store.publish(_progress())
        assert progress_store.read() is None
        progress_store.clear()
    finally:
        reset_engine()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_progress_store_db.py`
Expected: FAIL — the dual/db tests find no row / find the file.

- [ ] **Step 3: Branch the store** — in `swingbot/core/scanning/progress_store.py`, replace `publish`, `read` and `clear` with:

```python
def _write_file(record: dict) -> None:
    target = path()
    tmp = target + ".tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w") as handle:
            json.dump(record, handle)
        # Atomic on both platforms: the admin reads this on a request thread
        # while the bot rewrites it roughly once a second.
        os.replace(tmp, target)
    except OSError:
        log.debug("Could not publish scan progress", exc_info=True)


def _write_row(record: dict) -> None:
    # The one store besides the heartbeat allowed to swallow a DB write
    # failure: it is a progress bar, and the fail-fast rule exists to protect
    # trading state, not a display artefact.
    try:
        from swingbot.core.db.repositories.scan_progress import scan_progress_repo
        scan_progress_repo().publish(record)
    except Exception:  # noqa: BLE001
        log.debug("Could not publish scan progress to the database", exc_info=True)


def publish(progress) -> None:
    """Write `progress`'s record to the stage's backend(s). Never raises."""
    from swingbot.core.db import stages
    record = snapshot(progress)
    if stages.writes_json("scan_progress"):
        _write_file(record)
    if stages.writes_db("scan_progress"):
        _write_row(record)


def _read_file() -> dict | None:
    try:
        with open(path()) as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _read_row() -> dict | None:
    try:
        from swingbot.core.db.repositories.scan_progress import scan_progress_repo
        return scan_progress_repo().read()
    except Exception:  # noqa: BLE001
        log.debug("Could not read scan progress from the database", exc_info=True)
        return None


def read() -> dict | None:
    """The current record, or None when no scan is publishing one.

    Unreadable reads as absent rather than raising -- the caller is the
    admin's scan-status endpoint, and a progress bar is never worth a 500.
    """
    from swingbot.core.db import stages
    return _read_row() if stages.reads_db("scan_progress") else _read_file()


def clear() -> None:
    """Remove the record. Idempotent -- a scan that never published is normal."""
    from swingbot.core.db import stages
    if stages.writes_json("scan_progress"):
        for candidate in (path(), path() + ".tmp"):
            try:
                os.remove(candidate)
            except OSError:
                pass
    if stages.writes_db("scan_progress"):
        try:
            from swingbot.core.db.repositories.scan_progress import scan_progress_repo
            scan_progress_repo().clear()
        except Exception:  # noqa: BLE001
            log.debug("Could not clear scan progress in the database", exc_info=True)
```

Also update the module docstring's second paragraph: "written to a file the admin's watcher already `stat()`s" → "written where the admin can see it: `data/scan_progress.json`, or at stage `scan_progress:db` the `scan_progress` table, whose trigger raises the same `scan` event".

- [ ] **Step 4: The watcher stops stat()-ing it at `events:db`**

In `swingbot/admin/events/watcher.py`, add to `_TABLE_BACKED` (after `"tuning_results"`):

```python
    "scan_progress.json",     # scan_progress (v116)
```

and in the module docstring and in `residual_paths()`'s docstring, replace `scan progress/snapshots/telemetry` with `scan snapshots/telemetry`.

In `tests/admin/test_no_double_watcher.py`, the last assertion of `test_no_stat_calls_on_table_backed_paths_at_the_db_stage` becomes:

```python
    # The spy is live: the residual FileWatcher legitimately stats these.
    assert any(p.endswith("scan_snapshots.json") for p in residual), residual
```

- [ ] **Step 5: Run the new and existing progress/watcher tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_progress_store_db.py tests/scanning/test_progress_store.py tests/admin/test_no_double_watcher.py tests/admin/test_api_v1_system_scan.py`
Expected: PASS.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/progress_store.py` — no output.

```bash
git add swingbot/core/scanning/progress_store.py swingbot/admin/events/watcher.py tests/admin/test_no_double_watcher.py tests/scanning/test_progress_store_db.py
git commit -m "feat(v116): scan progress goes through stages (scan_progress)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-14: Market-data refresh bookkeeping goes through `stages`

**Files:**
- Modify: `swingbot/core/marketdata/data_refresh.py:70-103` (`load_state`, `save_state`)
- Create: `tests/marketdata/test_market_data_state_db.py`

**Interfaces:**
- Consumes: `market_data_state_repo()` and `store_db` (V116-12).
- Produces: `data_refresh.load_state()` / `save_state(state)` honour stage `market_data_state`. Neither raises: bookkeeping never breaks a refresh (unchanged rule, now also for the database). `STATE_FILE` stays until Phase 4.

- [ ] **Step 1: Write the failing tests** — `tests/marketdata/test_market_data_state_db.py`:

```python
"""market_data_state at each stage (v116 Phase 1)."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.marketdata import data_refresh

STATE = {"AAPL|daily": {"last_status": "failed", "fail_count": 2, "last_error": "timeout"}}


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "market_data_state.json"
    monkeypatch.setattr(data_refresh, "STATE_FILE", str(path))
    return path


def test_json_stage_uses_only_the_file(state_file, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    data_refresh.save_state(STATE)
    assert json.loads(state_file.read_text()) == STATE
    assert data_refresh.load_state() == STATE


def test_dual_writes_both_and_reads_the_file(state_file, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:dual")
    data_refresh.save_state(STATE)
    assert json.loads(state_file.read_text()) == STATE
    assert MarketDataStateRepository().load(conn=store_db) == STATE


def test_db_stage_uses_only_the_table(state_file, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    data_refresh.save_state(STATE)
    assert not os.path.exists(state_file)
    assert data_refresh.load_state() == STATE
    assert data_refresh.pending_gaps() == [("AAPL", "daily", 2, "timeout")]


def test_db_stage_starts_empty_without_an_import(state_file, store_db, monkeypatch):
    state_file.write_text(json.dumps(STATE))
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    assert data_refresh.load_state() == {}


def test_an_unreachable_database_never_breaks_a_refresh(state_file, monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DB_STORES", "market_data_state:db")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        data_refresh.save_state(STATE)
        assert data_refresh.load_state() == {}
    finally:
        reset_engine()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_market_data_state_db.py`
Expected: FAIL — the dual/db tests see only the file.

- [ ] **Step 3: Branch the two functions** — replace `load_state` and `save_state` in `swingbot/core/marketdata/data_refresh.py`:

```python
def load_state() -> dict:
    """Per-(symbol,timeframe) coverage + failure record. Survives restarts so
    an unresolved gap keeps being retried across bot sessions. At stage
    `market_data_state:db` it lives in its table, which starts empty (v116:
    ephemeral, no import) -- an empty map only means every gap is retried on
    its normal staleness window once."""
    from swingbot.core.db import stages
    if not stages.reads_db("market_data_state"):
        return read_json(STATE_FILE, {}) or {}
    try:
        from swingbot.core.db.repositories.market_data_state import market_data_state_repo
        return market_data_state_repo().load()
    except Exception as exc:            # never let bookkeeping break a refresh
        log.warning("could not read market-data state: %s", exc, exc_info=True)
        return {}


def save_state(state: dict) -> None:
    from swingbot.core.db import stages
    try:
        if stages.writes_json("market_data_state"):
            atomic_write_json(STATE_FILE, state)
        if stages.writes_db("market_data_state"):
            from swingbot.core.db.repositories.market_data_state import market_data_state_repo
            market_data_state_repo().save(state)
    except Exception as exc:            # never let bookkeeping break a refresh
        log.warning("could not save market-data state: %s", exc, exc_info=True)
```

- [ ] **Step 4: Run the new and existing refresh tests**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_market_data_state_db.py tests/marketdata/test_data_refresh.py tests/test_market_data_refresh_task.py`
Expected: PASS.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/data_refresh.py` — nothing new.

```bash
git add swingbot/core/marketdata/data_refresh.py tests/marketdata/test_market_data_state_db.py
git commit -m "feat(v116): market-data refresh bookkeeping goes through stages (market_data_state)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-15: The listener reconnects with backoff and emits one `resync`

**Files:**
- Modify: `swingbot/core/db/notify.py` (`listen` gains `on_listening`)
- Modify: `swingbot/admin/events/db_listener.py` (`__init__` gains `listen`, `backoff`; `_run` loops; new `_on_listening`)
- Create: `tests/admin/test_db_listener_reconnect.py`

**Interfaces:**
- Consumes: `DbEventListener`, `notify.listen` (V116-11).
- Produces: `notify.listen(channels, on_event, stop, *, poll=0.5, dsn=None, on_listening=None)` — calls `on_listening()` once LISTEN is active on each connection. `db_listener.RECONNECT_INITIAL = 1.0`, `RECONNECT_MAX = 30.0`; `DbEventListener(..., listen=None, backoff=(RECONNECT_INITIAL, RECONNECT_MAX))`. After any lost connection it retries with doubling backoff, and on the first successful LISTEN after a loss it calls `emit("resync")` once, bypassing the debounce. The SPA already refetches everything on `resync` (`frontend/src/app/api/event-stream.ts:101`); the broker forwards it as a normal event name.

- [ ] **Step 1: Write the failing tests** — `tests/admin/test_db_listener_reconnect.py`:

```python
"""A lost LISTEN connection is retried, and the reconnect is announced as one
`resync`, so a notification missed while down is never silently lost (v116)."""
import threading
import time

from swingbot.admin.events.db_listener import DbEventListener
from swingbot.core.db import notify


def _scripted_listen(script):
    """Each call plays one step: 'fail' raises before LISTEN, 'drop' raises
    after LISTEN, 'ok' reports LISTEN and blocks until stopped."""
    calls = []

    def listen(channels, on_event, stop, *, poll, dsn, on_listening=None):
        step = script.pop(0) if script else "ok"
        calls.append(step)
        if step == "fail":
            raise OSError("connection refused")
        on_listening()
        if step == "drop":
            raise OSError("server closed the connection unexpectedly")
        stop.wait(5)

    return listen, calls


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_the_first_connection_emits_no_resync():
    emitted = []
    listen, calls = _scripted_listen(["ok"])
    listener = DbEventListener(emitted.append, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["ok"])
    listener.stop()
    assert emitted == []


def test_a_dropped_connection_reconnects_and_emits_exactly_one_resync():
    emitted = []
    listen, calls = _scripted_listen(["drop", "fail", "fail", "ok"])
    listener = DbEventListener(emitted.append, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "fail", "fail", "ok"])
    listener.stop()
    assert emitted == ["resync"]


def test_stop_during_a_backoff_returns_promptly():
    listen, calls = _scripted_listen(["fail"] * 50)
    listener = DbEventListener(lambda _e: None, listen=listen, backoff=(5.0, 5.0))
    listener.start()
    assert _wait_for(lambda: calls == ["fail"])
    started = time.monotonic()
    listener.stop()
    assert time.monotonic() - started < 1.0


def test_a_raising_emit_on_resync_does_not_kill_the_listener():
    listen, calls = _scripted_listen(["drop", "ok"])

    def boom(_event):
        raise RuntimeError("subscriber exploded")

    listener = DbEventListener(boom, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "ok"])
    listener.stop()


def test_notify_listen_reports_when_listen_is_active(db_engine):
    stop = threading.Event()
    seen = []

    def on_listening():
        seen.append("up")
        stop.set()

    notify.listen(("trades",), lambda _c: None, stop, poll=0.05,
                  dsn=db_engine.url.render_as_string(hide_password=False),
                  on_listening=on_listening)
    assert seen == ["up"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_db_listener_reconnect.py`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'listen'`.

- [ ] **Step 3: `notify.listen` reports LISTEN** — in `swingbot/core/db/notify.py`, change the signature and add the call after the `LISTEN` loop:

```python
def listen(channels: "Sequence[str]", on_event: "Callable[[str | None], None]",
           stop: "threading.Event", *, poll: float = 0.5,
           dsn: str | None = None,
           on_listening: "Callable[[], None] | None" = None) -> None:
```

```python
    with psycopg.connect(conninfo, autocommit=True) as conn:
        for channel in channels:
            conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
        log.info("Listening on %s", ", ".join(channels))
        if on_listening is not None:
            on_listening()
        while not stop.is_set():
```

Add to the docstring: "`on_listening()` is called once per connection, as soon as LISTEN is active — the moment from which no notification can be missed."

- [ ] **Step 4: Reconnect with backoff** — in `swingbot/admin/events/db_listener.py`:

Module constants after `DEBOUNCE`:

```python
#: Reconnect backoff in seconds: the first wait, and the cap. Doubles per
#: failed attempt and resets once LISTEN is active again.
RECONNECT_INITIAL = 1.0
RECONNECT_MAX = 30.0
```

`__init__` gains two keyword arguments and three attributes:

```python
    def __init__(self, emit: Callable[[str], None], *,
                 channels: tuple[str, ...] | None = None,
                 debounce: float = DEBOUNCE,
                 clock: Callable[[], float] = time.monotonic,
                 dsn: str | None = None,
                 listen: Callable[..., None] | None = None,
                 backoff: tuple[float, float] = (RECONNECT_INITIAL, RECONNECT_MAX)):
        self._emit = emit
        self._channels = channels or notify.CHANNELS
        self._debounce = debounce
        self.clock = clock
        self._dsn = dsn
        self._listen = listen or notify.listen
        self._backoff = backoff
        self._delay = backoff[0]
        self._connected_before = False

        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
```

Replace `_run` and add `_on_listening`:

```python
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen(self._channels, self._on_event, self._stop,
                             poll=self._debounce, dsn=self._dsn,
                             on_listening=self._on_listening)
                return                      # stop() was called
            except Exception:
                log.warning("event listener lost its database connection; "
                            "reconnecting in %.1fs", self._delay, exc_info=True)
            if self._stop.wait(self._delay):
                return
            self._delay = min(self._delay * 2, self._backoff[1])

    def _on_listening(self) -> None:
        """LISTEN is active. After a reconnect, whatever was NOTIFYed while the
        connection was down is gone for good -- so tell every client to
        refetch (spec: recovery is a resync, never a replay)."""
        self._delay = self._backoff[0]
        if self._connected_before:
            try:
                self._emit("resync")
            except Exception:
                log.exception("event listener subscriber failed on 'resync'")
        self._connected_before = True
```

Update the module docstring's last paragraph: add "Reconnect: a lost connection is retried with doubling backoff (1 s to 30 s) and announced with one `resync`."

- [ ] **Step 5: Run the new and existing listener/broker tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_db_listener_reconnect.py tests/admin/test_db_listener.py tests/admin/test_broker_db_listener.py tests/admin/test_live_updates_e2e.py tests/db/test_notify_delivery.py`
Expected: PASS.

- [ ] **Step 6: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/admin/events/db_listener.py swingbot/core/db/notify.py` — no output.

```bash
git add swingbot/core/db/notify.py swingbot/admin/events/db_listener.py tests/admin/test_db_listener_reconnect.py
git commit -m "feat(v116): the db event listener reconnects with backoff and emits one resync

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
