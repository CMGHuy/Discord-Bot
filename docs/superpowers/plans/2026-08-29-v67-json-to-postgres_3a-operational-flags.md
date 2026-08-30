# v67 — Part 3: Operational state and live updates

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** Part 1 must be merged to
> `main` before this part begins.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

Everything the two containers use to coordinate: job state, scheduled-job
memory, UI preferences, the kill switch, the heartbeat, the manual-close queue,
the settings audit log, the ticker directory, tuning results and proposals, and
the four `.flag` files. Then the payoff — the admin's `stat()`-based watcher is
replaced by a `LISTEN/NOTIFY` listener, and the SPA does not change at all.

The flags are the interesting half. They are cross-container IPC, not data:
`scan_running`, `scan_paused`, `trigger_check`, `stop_scan`. As files, the bot
notices a flag on its next poll. As rows with a `NOTIFY` trigger, it reacts
immediately.

## Alembic revision ids

Part 3 owns `p3_*`, hanging off `p1_003` (**not** off Part 2 — the two parts run
concurrently, and a `down_revision` pointing at a sibling part's head is the
branch this scheme exists to prevent):

| Revision | Tables |
|---|---|
| `p3_001` | `runtime_flags`, `bot_heartbeat` |
| `p3_002` | `admin_jobs`, `scheduled_jobs` |
| `p3_003` | `ui_preferences`, `settings_audit` |
| `p3_004` | `killswitch`, `manual_close_notify` |
| `p3_005` | `ticker_directory` |
| `p3_006` | `tuning_results`, `tuning_proposals` |
| `p3_007` | NOTIFY triggers for every table above |

If Parts 2 and 3 both land and `alembic heads` shows two, resolve it with
`alembic merge -m "merge p2 and p3" --rev-id p6_000 <head1> <head2>` in Part 6.
**Never** by editing a `down_revision` that has already run anywhere.

## Parallelisation

- **Sequential: P3-01 before everything.** It is the only task that edits
  `schema.py`, for the same reason as P2-01.
- **Group 3a (parallel):** the flags chain (P3-02…P3-06), the jobs chain
  (P3-08…P3-10), the admin-state chain (P3-11, P3-12). Disjoint modules:
  `core/scanning/runstate.py` + `commands/scanning/runstate.py`,
  `admin/jobs.py` + `commands/scanning/loops.py`, `admin/api_v1/system.py` +
  `admin/helpers.py`.
- **Group 3b (parallel):** P3-07 (killswitch, `core/edge/throttle.py`), P3-13
  (`core/marketdata/ticker_directory.py`), P3-14/P3-15 (`admin/queries.py` — these
  two are sequential *with each other*, same file).
- **Sequential: P3-18 through P3-24 after every store above.** The watcher
  rewrite's tests assert against tables those tasks create; running them earlier
  fails for the right reason at the wrong time.
- **`scripts/db/parity_report.py` is shared.** Every chain registers its stores
  there. Register them all at once in P3-17, not per chain.

---

# Phase 3 — Operational state

### Task P3-01: Every Part 3 table

Eleven tables in one task, because `schema.py` is the file two parallel chains
would otherwise both edit.

**Files:**
- Modify: `swingbot/core/db/schema.py`
- Create: `swingbot/core/db/migrations/versions/p3_001_flags_and_heartbeat.py`
- Create: `swingbot/core/db/migrations/versions/p3_002_jobs.py`
- Create: `swingbot/core/db/migrations/versions/p3_003_admin_state.py`
- Create: `swingbot/core/db/migrations/versions/p3_004_killswitch_and_queue.py`
- Create: `swingbot/core/db/migrations/versions/p3_005_ticker_directory.py`
- Create: `swingbot/core/db/migrations/versions/p3_006_tuning.py`
- Modify: `tests/db/conftest.py`
- Test: `tests/db/test_part3_schema.py`

**Interfaces:**
- Consumes: `register`, `standard_columns`, `METADATA` (P1-04).
- Produces the tables `runtime_flags`, `bot_heartbeat`, `admin_jobs`,
  `scheduled_jobs`, `ui_preferences`, `settings_audit`, `killswitch`,
  `manual_close_notify`, `ticker_directory`, `tuning_results`,
  `tuning_proposals`.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_part3_schema.py`:

```python
"""Shapes that later Part 3 tasks depend on."""
import pytest
import sqlalchemy as sa

from swingbot.core.db import schema

PART3_TABLES = ("runtime_flags", "bot_heartbeat", "admin_jobs",
                "scheduled_jobs", "ui_preferences", "settings_audit",
                "killswitch", "manual_close_notify", "ticker_directory",
                "tuning_results", "tuning_proposals")


@pytest.mark.parametrize("name", PART3_TABLES)
def test_table_exists_and_is_registered(name):
    assert name in schema.METADATA.tables
    assert name in schema.PROMOTED


def test_runtime_flags_is_keyed_by_name(db_conn):
    schema  # noqa: B018 -- imported for the table below
    db_conn.execute(sa.insert(schema.runtime_flags).values(
        name="scan_running", set_at="2026-01-02T15:00:00+00:00"))
    with pytest.raises(sa.exc.IntegrityError):
        db_conn.execute(sa.insert(schema.runtime_flags).values(
            name="scan_running", set_at="2026-01-02T15:01:00+00:00"))


def test_heartbeat_is_a_singleton(db_conn):
    db_conn.execute(sa.insert(schema.bot_heartbeat).values(
        key="bot", ts="2026-01-02T15:00:00+00:00"))
    with pytest.raises(sa.exc.IntegrityError):
        db_conn.execute(sa.insert(schema.bot_heartbeat).values(
            key="bot", ts="2026-01-02T15:01:00+00:00"))


def test_manual_close_notify_is_a_queue_not_a_keyed_store(db_conn):
    # Two identical payloads are two queue entries. A unique key here would
    # silently drop the second manual close of the same trade.
    for _ in range(2):
        db_conn.execute(sa.insert(schema.manual_close_notify).values(
            queued_at="2026-01-02T15:00:00+00:00", doc={"trade_id": "T1"}))
    count = db_conn.execute(
        sa.select(sa.func.count()).select_from(schema.manual_close_notify)
    ).scalar_one()
    assert count == 2


def test_settings_audit_is_append_only_shaped(db_conn):
    for i in range(3):
        db_conn.execute(sa.insert(schema.settings_audit).values(
            ts=f"2026-01-02T15:0{i}:00+00:00", doc={"changes": []}))
    count = db_conn.execute(
        sa.select(sa.func.count()).select_from(schema.settings_audit)
    ).scalar_one()
    assert count == 3
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_part3_schema.py -q
```

Expected: `AttributeError: module 'swingbot.core.db.schema' has no attribute 'runtime_flags'`.

- [ ] **Step 3: Declare the tables**

Append to `swingbot/core/db/schema.py`:

```python
# The four .flag files. They are cross-container IPC, not data: a flag exists
# or it does not, and its content was never read. A row per flag plus a NOTIFY
# trigger turns "the bot notices on its next poll" into "the bot reacts now".
runtime_flags = register(
    sa.Table(
        "runtime_flags", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("set_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
    ),
    ("name", "set_at"),
)

# Singleton, key='bot'. Written on every scan tick including paused ones --
# the dot goes red only when the process stops responding.
bot_heartbeat = register(
    sa.Table(
        "bot_heartbeat", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
    ),
    ("key", "ts"),
)

admin_jobs = register(
    sa.Table(
        "admin_jobs", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("job_id", sa.Text, nullable=False, unique=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        *standard_columns(),
        sa.Index("admin_jobs_status_idx", "status"),
    ),
    ("job_id", "kind", "status", "started_at", "finished_at"),
)

# job name -> the ISO date it last fired. One row per named job.
scheduled_jobs = register(
    sa.Table(
        "scheduled_jobs", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("job", sa.Text, nullable=False, unique=True),
        sa.Column("fired_on", sa.Text, nullable=False),
        *standard_columns(),
    ),
    ("job", "fired_on"),
)

# Singleton today (one admin user), keyed so a second user is an INSERT rather
# than a schema change.
ui_preferences = register(
    sa.Table(
        "ui_preferences", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("owner", sa.Text, nullable=False, unique=True),
        *standard_columns(),
    ),
    ("owner",),
)

# Append-only. No natural key: two identical settings changes a minute apart
# are two audit entries.
settings_audit = register(
    sa.Table(
        "settings_audit", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
        sa.Index("settings_audit_ts_idx", sa.text("ts DESC")),
    ),
    ("ts",),
)

killswitch = register(
    sa.Table(
        "killswitch", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        sa.Column("engaged", sa.Boolean, nullable=False),
        sa.Column("engaged_at", sa.TIMESTAMP(timezone=True)),
        *standard_columns(),
    ),
    ("key", "engaged", "engaged_at"),
)

# A queue the admin writes and the bot drains. No unique key on purpose --
# closing the same trade twice is two notifications, not one silently dropped.
manual_close_notify = register(
    sa.Table(
        "manual_close_notify", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
        sa.Index("manual_close_notify_queued_idx", "queued_at"),
    ),
    ("queued_at",),
)

ticker_directory = register(
    sa.Table(
        "ticker_directory", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text),
        *standard_columns(),
        # search_tickers() prefix-matches on both columns.
        sa.Index("ticker_directory_name_idx", "name"),
    ),
    ("symbol", "name"),
)

tuning_results = register(
    sa.Table(
        "tuning_results", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("job_id", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
    ),
    ("job_id", "created_at"),
)

tuning_proposals = register(
    sa.Table(
        "tuning_proposals", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("filename", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *standard_columns(),
        sa.Index("tuning_proposals_created_idx", sa.text("created_at DESC")),
    ),
    ("filename", "created_at"),
)
```

- [ ] **Step 4: Write the six migrations**

Same shape as `p2_001`: an explicit `op.create_table` mirroring each `sa.Table`,
with a local `_standard()` helper rather than an import from `schema.py`.
Chain them `p1_003 → p3_001 → … → p3_006`. Triggers land separately in `p3_007`
(P3-18), so a table added here without a trigger is a visible gap rather than a
silent one.

- [ ] **Step 5: Extend the test harness**

Add all eleven tables to the trigger block in `tests/db/conftest.py`'s
`db_engine` fixture, with these channels — taken from `watcher.py`'s
`_DATA_PATHS`, which is the SPA's existing contract:

```python
            ("runtime_flags", "scan"), ("bot_heartbeat", "bot"),
            ("admin_jobs", "jobs"), ("scheduled_jobs", "jobs"),
            ("ui_preferences", "jobs"), ("settings_audit", "settings"),
            ("killswitch", "risk"), ("manual_close_notify", "trades"),
            ("ticker_directory", "watchlist"),
            ("tuning_results", "jobs"), ("tuning_proposals", "jobs"),
```

`settings_audit` maps to `settings`, which `WATCHED_EVENTS` already includes
(the watcher raises it from `config.ENV_PATH`, not from `data/`). Add
`"settings"` to `notify.CHANNELS` in `swingbot/core/db/notify.py` — it is the
tenth channel, and `trigger_ddl` rejects anything not listed.

- [ ] **Step 6: Migrate and run**

```bash
alembic upgrade head
alembic downgrade p1_003 && alembic upgrade head
python scripts/dev/testrun.py file tests/db/test_part3_schema.py
python scripts/dev/testrun.py file tests/db/test_notify_ddl.py
python scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `0 failed`. `test_notify_ddl.py` will fail on
`test_channels_match_the_watcher_concerns` until you add `settings` to its
expected tuple — do that, since the tenth channel is a real addition.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/notify.py \
        swingbot/core/db/migrations/versions/p3_00*.py \
        tests/db/conftest.py tests/db/test_part3_schema.py tests/db/test_notify_ddl.py
git commit -m "feat(v67): declare every Part 3 table"
```

---

### Task P3-02: The runtime-flags repository

**Files:**
- Create: `swingbot/core/db/repositories/flags.py`
- Test: `tests/db/test_flags_repository.py`

**Interfaces:**
- Consumes: `runtime_flags` (P3-01).
- Produces: `FlagRepository` with `is_set(name) -> bool`, `set(name)`,
  `clear(name)`, `set_at(name) -> str | None`; `flags_repo()`; and the constant
  tuple `FLAGS = ("scan_running", "scan_paused", "trigger_check", "stop_scan")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_flags_repository.py`:

```python
"""Flags are set/absent, exactly as the .flag files were."""
import pytest

from swingbot.core.db.repositories.flags import FLAGS, FlagRepository


@pytest.fixture
def repo():
    return FlagRepository()


def test_the_four_flags_are_the_four_flag_files():
    assert FLAGS == ("scan_running", "scan_paused", "trigger_check", "stop_scan")


def test_an_unset_flag_reads_false(repo, db_conn):
    assert repo.is_set("scan_running", conn=db_conn) is False


def test_set_then_is_set(repo, db_conn):
    repo.set("scan_running", conn=db_conn)
    assert repo.is_set("scan_running", conn=db_conn) is True


def test_setting_twice_is_idempotent(repo, db_conn):
    repo.set("scan_running", conn=db_conn)
    repo.set("scan_running", conn=db_conn)
    assert repo.count(conn=db_conn) == 1


def test_setting_twice_moves_set_at(repo, db_conn):
    repo.set("scan_running", conn=db_conn)
    first = repo.set_at("scan_running", conn=db_conn)
    repo.set("scan_running", conn=db_conn)
    assert repo.set_at("scan_running", conn=db_conn) >= first


def test_clear_removes_it(repo, db_conn):
    repo.set("scan_running", conn=db_conn)
    repo.clear("scan_running", conn=db_conn)
    assert repo.is_set("scan_running", conn=db_conn) is False


def test_clearing_something_unset_is_not_an_error(repo, db_conn):
    repo.clear("scan_running", conn=db_conn)      # the os.remove/OSError pass
    assert repo.is_set("scan_running", conn=db_conn) is False


def test_flags_are_independent(repo, db_conn):
    repo.set("scan_running", conn=db_conn)
    assert repo.is_set("scan_paused", conn=db_conn) is False


def test_an_unknown_flag_name_raises(repo, db_conn):
    # A typo'd flag name as a file was a file nobody ever created and nobody
    # ever noticed. Here it is a loud error.
    with pytest.raises(ValueError, match="not a known flag"):
        repo.set("scan_runnning", conn=db_conn)


def test_set_at_is_none_for_an_unset_flag(repo, db_conn):
    assert repo.set_at("stop_scan", conn=db_conn) is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_flags_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `swingbot/core/db/repositories/flags.py`:

```python
"""The four cross-container flags.

As files these were existence checks -- os.path.exists() -- and their contents
were written but never read. That is preserved: a flag is set or it is not.
What changes is that a NOTIFY trigger fires on the write, so the other
container reacts immediately instead of on its next poll.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import runtime_flags

#: The four data/*.flag files this replaces. A name outside this tuple is a
#: typo -- as a file it silently created a flag nobody checked, which is
#: exactly the class of bug that survives for months.
FLAGS = ("scan_running", "scan_paused", "trigger_check", "stop_scan")


class FlagRepository(Repository):
    def __init__(self):
        super().__init__(runtime_flags, key="name")

    @staticmethod
    def _check(name: str) -> str:
        if name not in FLAGS:
            raise ValueError(f"{name!r} is not a known flag; expected one of "
                             f"{', '.join(FLAGS)}")
        return name

    def is_set(self, name: str, *, conn=None) -> bool:
        return self.get(self._check(name), conn=conn) is not None

    def set(self, name: str, *, conn=None) -> None:
        self.upsert({"name": self._check(name),
                     "set_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    conn=conn)

    def clear(self, name: str, *, conn=None) -> None:
        self.delete(self._check(name), conn=conn)

    def set_at(self, name: str, *, conn=None) -> str | None:
        row = self.get(self._check(name), conn=conn)
        return None if row is None else row.get("set_at")


_repo: FlagRepository | None = None


def flags_repo() -> FlagRepository:
    global _repo
    if _repo is None:
        _repo = FlagRepository()
    return _repo
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_flags_repository.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/flags.py tests/db/test_flags_repository.py
git commit -m "feat(v67): add the runtime-flags repository"
```

---

### Task P3-03: stop_scan and scan_running

`core/scanning/runstate.py` is five functions over two flag files, shared by the
bot and the admin.

**Files:**
- Modify: `swingbot/core/scanning/runstate.py`
- Test: `tests/scanning/test_runstate_db.py`

**Interfaces:**
- Consumes: `flags_repo` (P3-02), `stages`.
- Produces: no new public symbols. `is_stop_requested()`, `request_stop()`,
  `_clear_stop()`, `is_scan_running()`, `_mark_running(bool)` keep their
  signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_runstate_db.py`:

```python
"""Scan run state at each stage."""
import os

import pytest

from swingbot import config
from swingbot.core.scanning import runstate


@pytest.fixture(params=["", "flags:dual", "flags:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def test_stop_is_not_requested_initially(any_stage):
    assert runstate.is_stop_requested() is False


def test_request_then_clear(any_stage):
    runstate.request_stop()
    assert runstate.is_stop_requested() is True
    runstate._clear_stop()
    assert runstate.is_stop_requested() is False


def test_clearing_twice_is_not_an_error(any_stage):
    runstate._clear_stop()
    runstate._clear_stop()


def test_mark_running_toggles(any_stage):
    assert runstate.is_scan_running() is False
    runstate._mark_running(True)
    assert runstate.is_scan_running() is True
    runstate._mark_running(False)
    assert runstate.is_scan_running() is False


def test_the_two_flags_are_independent(any_stage):
    runstate.request_stop()
    assert runstate.is_scan_running() is False


def test_no_flag_files_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "flags:db":
        pytest.skip("file absence is only asserted at the db stage")
    runstate.request_stop()
    runstate._mark_running(True)
    assert not os.path.exists(os.path.join(tmp_path, "stop_scan.flag"))
    assert not os.path.exists(os.path.join(tmp_path, "scan_running.flag"))


def test_the_admin_sees_the_bots_flag_at_the_db_stage(any_stage):
    """Two processes, one flag. This is what the bind-mounted files were for
    and what the NOTIFY trigger makes immediate."""
    if any_stage != "flags:db":
        pytest.skip("cross-process visibility is the db stage's property")
    from swingbot.core.db.repositories.flags import FlagRepository
    FlagRepository().set("scan_running")          # "the bot"
    assert runstate.is_scan_running() is True     # "the admin"
```

All four flags share one store name, `flags` — they are one table and they
migrate together. A per-flag stage would let `scan_running` be a row while
`stop_scan` was still a file, and the two are read in the same loop.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scanning/test_runstate_db.py -q
```

Expected: the `flags:db` parametrisation of `test_no_flag_files_at_the_db_stage`
fails — the file is still written.

- [ ] **Step 3: Branch the five functions**

```python
def _flags():
    """(use_db, repo_or_None) for this stage."""
    from swingbot.core.db import stages
    if not (stages.writes_db("flags") or stages.reads_db("flags")):
        return False, None
    from swingbot.core.db.repositories.flags import flags_repo
    return True, flags_repo()


def is_stop_requested() -> bool:
    from swingbot.core.db import stages
    if stages.reads_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        return flags_repo().is_set("stop_scan")
    return os.path.exists(_STOP_FILE)


def request_stop() -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_STOP_FILE, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        flags_repo().set("stop_scan")
```

`_clear_stop`, `is_scan_running` and `_mark_running` follow the same shape
against `stop_scan` and `scan_running`. Note `_STOP_FILE` and `_RUNNING_FILE`
are module-level constants built from `config.DATA_DIR` at import time — leave
them alone, they are the json-stage path and Part 6 deletes them; the tests
above monkeypatch `config.DATA_DIR` and so exercise the db branch, which does
not read them.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_runstate_db.py
python scripts/dev/testrun.py file tests/scanning/test_scan_run.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/runstate.py tests/scanning/test_runstate_db.py
git commit -m "feat(v67): move stop/running flags to postgres"
```

---

### Task P3-04: scan_paused and trigger_check

`commands/scanning/runstate.py` owns the other two flags plus the heartbeat and
the manual-close queue. This task takes the two flags; P3-05 and P3-06 take the
rest.

**Files:**
- Modify: `swingbot/commands/scanning/runstate.py` (`is_scan_paused`,
  `set_scan_paused`, and the `_TRIGGER_FILE` readers)
- Test: `tests/commands/test_scan_paused_db.py`

**Interfaces:**
- Consumes: `flags_repo` (P3-02), `stages`.
- Produces: `is_trigger_requested() -> bool` and `clear_trigger() -> None` —
  **new named functions replacing inline `os.path.exists(_TRIGGER_FILE)` /
  `os.remove` at every call site.** Find them with
  `git grep -n "_TRIGGER_FILE" -- swingbot`.

Naming the trigger operations is not incidental tidying: an inline
`os.path.exists` cannot be stage-branched without editing every caller, and the
whole strangler depends on there being one place per flag to branch.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_scan_paused_db.py`:

```python
"""Pause and trigger flags at each stage."""
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture(params=["", "flags:dual", "flags:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def test_not_paused_initially(any_stage):
    assert runstate.is_scan_paused() is False


def test_pause_then_resume(any_stage):
    runstate.set_scan_paused(True)
    assert runstate.is_scan_paused() is True
    runstate.set_scan_paused(False)
    assert runstate.is_scan_paused() is False


def test_resuming_twice_is_not_an_error(any_stage):
    runstate.set_scan_paused(False)
    runstate.set_scan_paused(False)


def test_trigger_request_and_clear(any_stage):
    assert runstate.is_trigger_requested() is False
    runstate.request_trigger()
    assert runstate.is_trigger_requested() is True
    runstate.clear_trigger()
    assert runstate.is_trigger_requested() is False


def test_pause_and_trigger_are_independent(any_stage):
    runstate.set_scan_paused(True)
    assert runstate.is_trigger_requested() is False


def test_no_flag_files_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "flags:db":
        pytest.skip("file absence is only asserted at the db stage")
    runstate.set_scan_paused(True)
    runstate.request_trigger()
    assert not os.path.exists(os.path.join(tmp_path, "scan_paused.flag"))
    assert not os.path.exists(os.path.join(tmp_path, "trigger_check.flag"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/commands/test_scan_paused_db.py -q
```

Expected: `AttributeError: module ... has no attribute 'is_trigger_requested'`.

- [ ] **Step 3: Add the named trigger functions and branch all four**

In `swingbot/commands/scanning/runstate.py`:

```python
def is_scan_paused() -> bool:
    """Whether the automatic background scan loop is currently paused (via the
    admin UI toggle or the !pause command). Manual scans (!check, and the admin
    UI's "Run !check now" trigger) are NOT affected -- pausing only stops the
    unattended, scheduled scanning so the user can still check on demand."""
    from swingbot.core.db import stages
    if stages.reads_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        return flags_repo().is_set("scan_paused")
    return os.path.exists(_PAUSE_FILE)


def set_scan_paused(paused: bool) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        if paused:
            with open(_PAUSE_FILE, "w") as f:
                f.write(dt.datetime.now(dt.timezone.utc).isoformat())
        else:
            try:
                os.remove(_PAUSE_FILE)
            except OSError:
                pass  # already resumed by a parallel caller
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        repo = flags_repo()
        repo.set("scan_paused") if paused else repo.clear("scan_paused")


def is_trigger_requested() -> bool:
    """Whether a manual scan has been requested by the admin UI.

    Named rather than inlined as os.path.exists(_TRIGGER_FILE) at each call
    site: a stage branch needs exactly one place per flag to live, and an
    inline existence check has as many places as it has callers.
    """
    from swingbot.core.db import stages
    if stages.reads_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        return flags_repo().is_set("trigger_check")
    return os.path.exists(_TRIGGER_FILE)


def request_trigger() -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_TRIGGER_FILE, "w") as f:
            f.write(dt.datetime.now(dt.timezone.utc).isoformat())
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        flags_repo().set("trigger_check")


def clear_trigger() -> None:
    from swingbot.core.db import stages
    if stages.writes_json("flags"):
        try:
            os.remove(_TRIGGER_FILE)
        except OSError:
            pass  # already drained
    if stages.writes_db("flags"):
        from swingbot.core.db.repositories.flags import flags_repo
        flags_repo().clear("trigger_check")
```

- [ ] **Step 4: Route every existing call site through them**

```bash
git grep -n "_TRIGGER_FILE" -- swingbot
```

Every hit outside this module becomes `is_trigger_requested()`,
`request_trigger()` or `clear_trigger()`. The count outside
`commands/scanning/runstate.py` must reach zero.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/commands/test_scan_paused_db.py
python scripts/dev/testrun.py file tests/commands/test_scanning_loops.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier here because renaming call sites crosses
files.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/runstate.py swingbot \
        tests/commands/test_scan_paused_db.py
git commit -m "feat(v67): move pause/trigger flags to postgres"
```

---

### Task P3-05: The bot heartbeat

`_write_heartbeat()` is wrapped in a bare `except Exception: pass` — the
heartbeat must never take the scan loop down. That stays true at the db stage,
and it is the one place in this plan where the fail-fast rule is deliberately
not applied.

**Files:**
- Create: `swingbot/core/db/repositories/heartbeat.py`
- Modify: `swingbot/commands/scanning/runstate.py` (`_write_heartbeat`)
- Modify: `swingbot/admin/api_v1/system.py` (the heartbeat reader — find it with
  `git grep -n "bot_heartbeat" -- swingbot/admin`)
- Test: `tests/commands/test_heartbeat_db.py`

**Interfaces:**
- Consumes: `bot_heartbeat` (P3-01), `stages`.
- Produces: `HeartbeatRepository` with `beat(session_active, scan_paused)` and
  `last() -> dict | None`; `heartbeat_repo()`.

**Why the exception rule differs here:** the spec's fail-fast policy exists so a
bot that cannot record trades goes visibly down rather than silently posting
alerts it never logs. The heartbeat records nothing — it is a liveness signal
*about* the bot. Killing the scan loop because the liveness dot could not be
updated inverts the whole point of the dot.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_heartbeat_db.py`:

```python
"""The heartbeat is the one store allowed to swallow a write failure."""
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_json_stage_writes_the_file(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate._write_heartbeat()
    assert os.path.exists(os.path.join(data_dir, "bot_heartbeat.json"))


def test_db_stage_writes_a_row(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    last = HeartbeatRepository().last(conn=db_committed)
    assert last is not None and "ts" in last
    assert "session_active" in last and "scan_paused" in last


def test_beating_twice_keeps_one_row(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    runstate._write_heartbeat()
    assert HeartbeatRepository().count(conn=db_committed) == 1


def test_the_timestamp_advances(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    runstate._write_heartbeat()
    first = HeartbeatRepository().last(conn=db_committed)["ts"]
    runstate._write_heartbeat()
    assert HeartbeatRepository().last(conn=db_committed)["ts"] >= first


def test_a_database_failure_does_not_take_down_the_scan_loop(
        data_dir, monkeypatch):
    """The one deliberate exception to the fail-fast rule. A liveness signal
    that kills the process it reports on is worse than no signal."""
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    runstate._write_heartbeat()       # must not raise
    dbengine.reset_engine()


def test_last_is_none_on_an_empty_table(db_conn):
    assert HeartbeatRepository().last(conn=db_conn) is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/commands/test_heartbeat_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository and branch the writer**

Create `swingbot/core/db/repositories/heartbeat.py`:

```python
"""Bot liveness. One row, key='bot'."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import bot_heartbeat

KEY = "bot"


class HeartbeatRepository(Repository):
    def __init__(self):
        super().__init__(bot_heartbeat, key="key")

    def beat(self, *, session_active: bool, scan_paused: bool, conn=None) -> None:
        self.upsert({"key": KEY,
                     "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "session_active": session_active,
                     "scan_paused": scan_paused}, conn=conn)

    def last(self, *, conn=None) -> dict | None:
        row = self.get(KEY, conn=conn)
        if row is None:
            return None
        return {k: v for k, v in row.items() if k != "key"}


_repo: HeartbeatRepository | None = None


def heartbeat_repo() -> HeartbeatRepository:
    global _repo
    if _repo is None:
        _repo = HeartbeatRepository()
    return _repo
```

In `_write_heartbeat()`, add the db branch **inside** the existing
`try/except Exception: pass`:

```python
def _write_heartbeat() -> None:
    """Stamps the liveness signal the admin UI's Dashboard dot reads. Written
    on every session_scan tick (including off-hours / paused ticks) so the dot
    goes red only when the bot process itself stops responding.

    The bare except is deliberate and survives the Postgres migration: this is
    the ONE store exempt from the plan's fail-fast rule, because a liveness
    signal that kills the process it reports on inverts its own purpose.
    """
    from swingbot.core.db import stages
    try:
        if stages.writes_json("heartbeat"):
            os.makedirs(config.DATA_DIR, exist_ok=True)
            with open(_HEARTBEAT_FILE, "w") as fh:
                json.dump({
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "session_active": in_session(),
                    "scan_paused": is_scan_paused(),
                }, fh)
        if stages.writes_db("heartbeat"):
            from swingbot.core.db.repositories.heartbeat import heartbeat_repo
            heartbeat_repo().beat(session_active=in_session(),
                                  scan_paused=is_scan_paused())
    except Exception:
        pass
```

Note the file writes `timestamp` and the row writes `ts`. The admin reader must
accept both while any stage is live — branch it on `stages.reads_db("heartbeat")`
rather than trying to normalise, so neither shape has to change.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/commands/test_heartbeat_db.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/heartbeat.py \
        swingbot/commands/scanning/runstate.py swingbot/admin/api_v1/system.py \
        tests/commands/test_heartbeat_db.py
git commit -m "feat(v67): move the bot heartbeat to postgres"
```

---

### Task P3-06: The manual-close notification queue

`manual_close_notify.json` is a JSONL file the admin appends to and the bot
drains and deletes. As a table it becomes a real queue, and the drain becomes
atomic — today a bot that crashes mid-drain re-posts every entry.

**Files:**
- Create: `swingbot/core/db/repositories/notify_queue.py`
- Modify: `swingbot/commands/scanning/runstate.py` (the queue drain)
- Modify: the admin writer (`git grep -n "manual_close_notify" -- swingbot/admin`)
- Test: `tests/commands/test_manual_close_queue_db.py`

**Interfaces:**
- Consumes: `manual_close_notify` (P3-01), `transaction` (P2-10 — **if Part 2
  has not landed, add `transaction()` to `engine.py` here instead**; the two
  definitions are identical and whichever part lands second finds it already
  there).
- Produces: `NotifyQueueRepository` with `enqueue(payload)`, `drain() ->
  list[dict]`, `pending() -> int`; `notify_queue_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_manual_close_queue_db.py`:

```python
"""A queue the admin writes and the bot drains, exactly once."""
import pytest

from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository


@pytest.fixture
def repo():
    return NotifyQueueRepository()


def test_an_empty_queue_drains_to_nothing(repo, db_conn):
    assert repo.drain(conn=db_conn) == []


def test_enqueue_then_drain(repo, db_conn):
    repo.enqueue({"trade_id": "T1", "reason": "manual"}, conn=db_conn)
    drained = repo.drain(conn=db_conn)
    assert [d["trade_id"] for d in drained] == ["T1"]


def test_draining_removes_the_entries(repo, db_conn):
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    repo.drain(conn=db_conn)
    assert repo.drain(conn=db_conn) == []


def test_the_same_trade_can_be_queued_twice(repo, db_conn):
    # Two manual closes of the same trade are two notifications. A unique key
    # here would silently drop the second.
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    assert len(repo.drain(conn=db_conn)) == 2


def test_drain_is_oldest_first(repo, db_conn):
    for i in range(3):
        repo.enqueue({"trade_id": f"T{i}"}, conn=db_conn)
    assert [d["trade_id"] for d in repo.drain(conn=db_conn)] == ["T0", "T1", "T2"]


def test_pending_counts_without_draining(repo, db_conn):
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    assert repo.pending(conn=db_conn) == 1


def test_an_entry_queued_during_a_drain_survives_it(repo, db_conn):
    """DELETE ... RETURNING takes a snapshot; anything written after it is
    still there afterwards. The file version deleted the whole file and lost
    whatever the admin appended in between."""
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    drained = repo.drain(conn=db_conn)
    repo.enqueue({"trade_id": "T2"}, conn=db_conn)
    assert [d["trade_id"] for d in drained] == ["T1"]
    assert repo.pending(conn=db_conn) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/commands/test_manual_close_queue_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/notify_queue.py`:

```python
"""Manual-close notifications: the admin enqueues, the bot drains.

`drain()` is DELETE ... RETURNING -- one statement, so a crash between reading
and deleting cannot exist. The file version read the whole file, posted, then
unlinked it: a crash after posting and before the unlink re-posted everything
on the next tick, and a crash before posting lost nothing but a write from the
admin in between was deleted unread.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import manual_close_notify


class NotifyQueueRepository(Repository):
    def __init__(self):
        super().__init__(manual_close_notify, key="id")

    def enqueue(self, payload: dict, *, conn=None) -> None:
        self.insert({"queued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     **payload}, conn=conn)

    def pending(self, *, conn=None) -> int:
        return self.count(conn=conn)

    def drain(self, *, conn=None) -> list[dict]:
        stmt = (sa.delete(manual_close_notify)
                .returning(manual_close_notify))
        with self._tx(conn) as c:
            rows = c.execute(stmt).all()
        records = [self._row_to_record(r) for r in rows]
        records.sort(key=lambda r: r.get("queued_at") or "")
        for r in records:
            r.pop("queued_at", None)
        return records
```

`queued_at` is stripped on the way out so the drained payload is byte-identical
to what the admin enqueued — the bot formats it into a Discord message and an
extra key would show up there.

- [ ] **Step 4: Branch the writer and the drain**

The admin's writer appends a JSON line; add
`if stages.writes_db("notify_queue"): notify_queue_repo().enqueue(record)`
beside it, guarded by `stages.writes_json("notify_queue")` on the file side.

The bot's drain, in `commands/scanning/runstate.py`, gains the read branch:
at `reads_db("notify_queue")` it calls `notify_queue_repo().drain()` and skips
the file entirely.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/commands/test_manual_close_queue_db.py
python scripts/dev/testrun.py file tests/commands/test_scanning_loops.py
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/notify_queue.py \
        swingbot/commands/scanning/runstate.py swingbot/admin \
        tests/commands/test_manual_close_queue_db.py
git commit -m "feat(v67): make the manual-close queue a real queue"
```

---

### Task P3-07: The kill switch

`throttle.py:81-104`. It auto-*engages* but never auto-releases — resuming needs
a human. That asymmetry is the whole safety property and must survive.

**Files:**
- Create: `swingbot/core/db/repositories/killswitch.py`
- Modify: `swingbot/core/edge/throttle.py` (`kill_state` `:87`, `set_kill` `:93`)
- Test: `tests/edge/test_killswitch_db.py`

**Interfaces:**
- Consumes: `killswitch` (P3-01), `stages`.
- Produces: `KillswitchRepository` with `state() -> dict`, `engage(reason)`,
  `release(reason)`; `killswitch_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/edge/test_killswitch_db.py`:

```python
"""The kill switch engages automatically and releases only by hand."""
import os

import pytest

from swingbot import config
from swingbot.core.edge import throttle


@pytest.fixture(params=["", "killswitch:dual", "killswitch:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH",
                        os.path.join(tmp_path, "killswitch.json"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def test_default_state_is_disengaged(any_stage):
    assert throttle.kill_state().get("on") in (False, None)


def test_engage_then_read_back(any_stage):
    throttle.set_kill(True, reason="drawdown")
    state = throttle.kill_state()
    assert state["on"] is True
    assert state["reason"] == "drawdown"


def test_release(any_stage):
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(False, reason="manual")
    assert throttle.kill_state()["on"] is False


def test_engaging_twice_keeps_the_first_reason(any_stage):
    """An auto-trigger firing again while already engaged must not overwrite
    why it engaged in the first place -- that reason is what the human reads
    before deciding to release."""
    throttle.set_kill(True, reason="drawdown")
    throttle.set_kill(True, reason="spy_move")
    assert throttle.kill_state()["reason"] == "drawdown"


def test_check_kill_triggers_engages_but_never_releases(any_stage):
    throttle.set_kill(True, reason="drawdown")
    # Benign inputs: nothing should trip, and nothing should un-trip either.
    throttle.check_kill_triggers(dd_pct=0.0, spy_move_pct=0.0,
                                 consecutive_losses=0)
    assert throttle.kill_state()["on"] is True


def test_no_killswitch_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "killswitch:db":
        pytest.skip("file absence is only asserted at the db stage")
    throttle.set_kill(True, reason="drawdown")
    assert not os.path.exists(os.path.join(tmp_path, "killswitch.json"))
```

`test_check_kill_triggers_engages_but_never_releases` calls
`check_kill_triggers` with whatever signature it actually has — read
`throttle.py:104` and match it exactly before writing this test.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/edge/test_killswitch_db.py -q
```

Expected: the `killswitch:db` parametrisations fail.

- [ ] **Step 3: Write the repository and branch the two functions**

Create `swingbot/core/db/repositories/killswitch.py`:

```python
"""The kill switch. Engages automatically; releases only by hand."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import killswitch

KEY = "global"


class KillswitchRepository(Repository):
    def __init__(self):
        super().__init__(killswitch, key="key")

    def state(self, *, conn=None) -> dict:
        row = self.get(KEY, conn=conn)
        if row is None:
            return {"on": False}
        out = {k: v for k, v in row.items() if k != "key"}
        out["on"] = bool(out.pop("engaged", False))
        return out

    def engage(self, reason: str, *, conn=None) -> dict:
        """Idempotent: engaging an already-engaged switch keeps the ORIGINAL
        reason. That reason is what the human reads before releasing, and an
        auto-trigger re-firing must not overwrite it."""
        current = self.state(conn=conn)
        if current.get("on"):
            return current
        self.upsert({"key": KEY, "engaged": True, "reason": reason,
                     "engaged_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    conn=conn)
        return self.state(conn=conn)

    def release(self, reason: str, *, conn=None) -> dict:
        self.upsert({"key": KEY, "engaged": False, "reason": reason,
                     "engaged_at": None}, conn=conn)
        return self.state(conn=conn)


_repo: KillswitchRepository | None = None


def killswitch_repo() -> KillswitchRepository:
    global _repo
    if _repo is None:
        _repo = KillswitchRepository()
    return _repo
```

`kill_state()` gains a `reads_db("killswitch")` branch returning
`killswitch_repo().state()`; `set_kill(on, reason)` writes both sides per stage,
calling `engage(reason)` or `release(reason)`.

**The engage-idempotence must also hold on the file side at the dual stage.**
Check `set_kill`'s current behaviour first: if the file version overwrites the
reason, the two backends diverge at `dual` and the comparator will say so. Make
the file side match the repository's rule rather than the other way round —
keeping the first reason is the correct behaviour, and the file version having
been wrong is a bug this migration fixes.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/edge/test_killswitch_db.py
python scripts/dev/testrun.py file tests/edge/test_throttle.py
```

Expected: `0 failed`. If `test_throttle.py` fails on the reason-overwrite
change, that is the bug being fixed — update the existing test and say so in the
commit.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/killswitch.py swingbot/core/edge/throttle.py \
        tests/edge/test_killswitch_db.py tests/edge/test_throttle.py
git commit -m "feat(v67): move the kill switch to postgres"
```

---

