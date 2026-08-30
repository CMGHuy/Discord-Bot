# v67 — Part 3: Operational state (tasks P3-08…P3-15)

> Continuation of `2026-08-29-v67-json-to-postgres_3a-operational-flags.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P3-08: The admin-jobs repository

`admin_jobs.json` holds every job's state and progress, read and rewritten whole
by `_read_jobs`/`_write_jobs` (`admin/jobs.py:106,117`) from a background watcher
thread while the request thread also writes.

**Files:**
- Create: `swingbot/core/db/repositories/jobs.py`
- Test: `tests/db/test_jobs_repository.py`

**Interfaces:**
- Consumes: `admin_jobs` (P3-01).
- Produces: `JobRepository` with `all_jobs() -> dict[str, dict]`,
  `get_job(job_id)`, `put(job_id, record)`, `patch_job(job_id, changes)`,
  `active() -> list[dict]`, `prune(before_ts)`; `jobs_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_jobs_repository.py`:

```python
"""Job state, with progress updates that do not rewrite the world."""
import pytest

from swingbot.core.db.repositories.jobs import JobRepository


@pytest.fixture
def repo():
    return JobRepository()


def _job(job_id="J1", **over):
    base = dict(job_id=job_id, kind="tune", status="running",
                started_at="2026-01-02T15:00:00+00:00",
                pid=1234, args=["--strategy", "RSI"], progress=0)
    base.update(over)
    return base


def test_all_jobs_is_keyed_by_job_id(repo, db_conn):
    repo.put(_job("J1"), conn=db_conn)
    repo.put(_job("J2"), conn=db_conn)
    assert set(repo.all_jobs(conn=db_conn)) == {"J1", "J2"}


def test_progress_updates_do_not_disturb_other_jobs(repo, db_conn):
    """The bug: _write_jobs serialises the whole dict, so the watcher thread's
    progress tick and the request thread's new job race over one file."""
    repo.put(_job("J1"), conn=db_conn)
    repo.put(_job("J2"), conn=db_conn)
    repo.patch_job("J1", {"progress": 55}, conn=db_conn)
    assert repo.get_job("J1", conn=db_conn)["progress"] == 55
    assert repo.get_job("J2", conn=db_conn)["progress"] == 0


def test_patch_preserves_unnamed_fields(repo, db_conn):
    repo.put(_job(), conn=db_conn)
    repo.patch_job("J1", {"progress": 10}, conn=db_conn)
    assert repo.get_job("J1", conn=db_conn)["args"] == ["--strategy", "RSI"]


def test_active_returns_only_running_jobs(repo, db_conn):
    repo.put(_job("J1", status="running"), conn=db_conn)
    repo.put(_job("J2", status="done",
                  finished_at="2026-01-02T16:00:00+00:00"), conn=db_conn)
    assert [j["job_id"] for j in repo.active(conn=db_conn)] == ["J1"]


def test_get_job_returns_none_for_a_missing_id(repo, db_conn):
    assert repo.get_job("nope", conn=db_conn) is None


def test_prune_drops_finished_jobs_older_than_a_cutoff(repo, db_conn):
    repo.put(_job("OLD", status="done",
                  finished_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.put(_job("NEW", status="done",
                  finished_at="2026-02-01T00:00:00+00:00"), conn=db_conn)
    assert repo.prune("2026-01-15T00:00:00+00:00", conn=db_conn) == 1
    assert set(repo.all_jobs(conn=db_conn)) == {"NEW"}


def test_prune_never_drops_a_running_job(repo, db_conn):
    repo.put(_job("RUNNING", status="running"), conn=db_conn)
    assert repo.prune("2030-01-01T00:00:00+00:00", conn=db_conn) == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_jobs_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `swingbot/core/db/repositories/jobs.py`:

```python
"""Admin job state.

patch_job() is why this table matters: JobManager's watcher thread ticks
progress while the request thread may be starting another job, and _write_jobs
serialises the entire dict on every one of those writes.
"""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import admin_jobs

ACTIVE_STATUSES = ("running", "starting")


class JobRepository(Repository):
    def __init__(self):
        super().__init__(admin_jobs, key="job_id")

    def all_jobs(self, *, conn=None) -> dict[str, dict]:
        return {j["job_id"]: j for j in self.list_all(
            conn=conn, order_by=admin_jobs.c.started_at.desc())}

    def get_job(self, job_id: str, *, conn=None) -> dict | None:
        return self.get(job_id, conn=conn)

    def put(self, record: dict, *, conn=None) -> dict:
        return self.upsert(record, conn=conn)

    def patch_job(self, job_id: str, changes: dict, *, conn=None) -> dict | None:
        return self.patch(job_id, changes, conn=conn)

    def active(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn,
                             where=admin_jobs.c.status.in_(ACTIVE_STATUSES),
                             order_by=admin_jobs.c.started_at.desc())

    def prune(self, before_ts: str, *, conn=None) -> int:
        """Drop finished jobs that ended before `before_ts`. A running job is
        never pruned regardless of its start time -- a long backtest can run
        for hours and pruning it would orphan a live process."""
        stmt = sa.delete(admin_jobs).where(sa.and_(
            admin_jobs.c.status.notin_(ACTIVE_STATUSES),
            admin_jobs.c.finished_at.isnot(None),
            admin_jobs.c.finished_at < before_ts,
        ))
        with self._tx(conn) as c:
            return c.execute(stmt).rowcount


_repo: JobRepository | None = None


def jobs_repo() -> JobRepository:
    global _repo
    if _repo is None:
        _repo = JobRepository()
    return _repo
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_jobs_repository.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/jobs.py tests/db/test_jobs_repository.py
git commit -m "feat(v67): add the admin-jobs repository"
```

---

### Task P3-09: JobManager uses the repository

**Files:**
- Modify: `swingbot/admin/jobs.py` (`_read_jobs` `:106`, `_write_jobs` `:117`,
  `JobManager` `:152`)
- Test: `tests/admin/test_jobs_db.py`

**Interfaces:**
- Consumes: `jobs_repo` (P3-08), `stages`.
- Produces: no new public symbols. `JobManager.start`, `.status`, `.tail`,
  `.all` keep their signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_jobs_db.py`:

```python
"""JobManager at each stage."""
import os

import pytest

from swingbot import config
from swingbot.admin import jobs as jobs_mod
from swingbot.core.db.repositories.jobs import JobRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    jobs_mod._write_jobs({"J1": {"job_id": "J1", "kind": "tune",
                                 "status": "done",
                                 "started_at": "2026-01-02T15:00:00+00:00"}})
    assert os.path.exists(os.path.join(data_dir, "admin_jobs.json"))
    assert JobRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "jobs:dual")
    jobs_mod._write_jobs({"J1": {"job_id": "J1", "kind": "tune",
                                 "status": "done",
                                 "started_at": "2026-01-02T15:00:00+00:00"}})
    assert os.path.exists(os.path.join(data_dir, "admin_jobs.json"))
    assert JobRepository().get_job("J1", conn=db_committed) is not None


def test_db_stage_reads_rows(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "jobs:db")
    JobRepository().put({"job_id": "J1", "kind": "tune", "status": "running",
                         "started_at": "2026-01-02T15:00:00+00:00"})
    assert "J1" in jobs_mod._read_jobs()
    assert not os.path.exists(os.path.join(data_dir, "admin_jobs.json"))


def test_a_write_of_one_job_does_not_drop_another(data_dir, monkeypatch,
                                                  db_committed):
    """At the db stage _write_jobs upserts each job rather than replacing the
    whole set -- so two threads writing different jobs both keep theirs."""
    monkeypatch.setattr(config, "DB_STORES", "jobs:db")
    repo = JobRepository()
    repo.put({"job_id": "OTHER", "kind": "backtest", "status": "running",
              "started_at": "2026-01-02T14:00:00+00:00"})
    jobs_mod._write_jobs({"J1": {"job_id": "J1", "kind": "tune",
                                 "status": "running",
                                 "started_at": "2026-01-02T15:00:00+00:00"}})
    assert set(repo.all_jobs()) == {"OTHER", "J1"}


def test_status_reads_through(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "jobs:db")
    JobRepository().put({"job_id": "J1", "kind": "tune", "status": "running",
                         "started_at": "2026-01-02T15:00:00+00:00"})
    assert jobs_mod.JobManager().status("J1")["status"] == "running"
```

`test_a_write_of_one_job_does_not_drop_another` pins a **deliberate semantic
change**: `_write_jobs(jobs)` used to mean "these are all the jobs". At the db
stage it means "upsert these jobs". That is what removes the lost update, and it
is safe because no caller uses `_write_jobs` to delete — deletion goes through
`prune`.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_jobs_db.py -q
```

Expected: `test_dual_stage_writes_both` fails.

- [ ] **Step 3: Branch the two funnels**

```python
def _read_jobs() -> dict:
    from swingbot.core.db import stages
    if stages.reads_db("jobs"):
        from swingbot.core.db.repositories.jobs import jobs_repo
        return jobs_repo().all_jobs()
    # ... existing file body unchanged ...


def _write_jobs(jobs: dict) -> None:
    """Persist job state.

    At the db stage this UPSERTS each job rather than replacing the whole set.
    That is a deliberate semantic change and it is what removes the lost
    update: the watcher thread ticking one job's progress no longer serialises
    a snapshot that predates another thread's new job. Nothing deletes through
    this function -- deletion is JobRepository.prune -- so "upsert" and
    "replace" differ only in the failure case.
    """
    from swingbot.core.db import stages
    if stages.writes_json("jobs"):
        # ... existing file body unchanged ...
        pass
    if stages.writes_db("jobs"):
        from swingbot.core.db.repositories.jobs import jobs_repo
        repo = jobs_repo()
        for record in jobs.values():
            repo.put(record)
```

`JobManager`'s methods all go through `_read_jobs`/`_write_jobs` already, so
they need no edit — confirm with
`grep -n "_read_jobs\|_write_jobs\|json.load\|json.dump" swingbot/admin/jobs.py`
that no method opens the file directly.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_jobs_db.py
python scripts/dev/testrun.py file tests/admin/test_jobs.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/jobs.py tests/admin/test_jobs_db.py
git commit -m "feat(v67): back admin jobs with postgres"
```

---

### Task P3-10: Scheduled-job memory

`loops.py:556-570`: three functions over a `{job: "YYYY-MM-DD"}` dict, which is
how the daily recap and weekend scan avoid firing twice.

**Files:**
- Create: `swingbot/core/db/repositories/scheduled.py`
- Modify: `swingbot/commands/scanning/loops.py:556-570`
- Test: `tests/commands/test_scheduled_jobs_db.py`

**Interfaces:**
- Consumes: `scheduled_jobs` (P3-01), `stages`.
- Produces: `ScheduledJobRepository` with `fired_on(job) -> str | None`,
  `mark(job, date_iso)`; `scheduled_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_scheduled_jobs_db.py`:

```python
"""Fire-once-a-day memory, across a restart and across both containers."""
import datetime as dt
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import loops


@pytest.fixture(params=["", "scheduled_jobs:dual", "scheduled_jobs:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


TODAY = dt.date(2026, 1, 2)
TOMORROW = dt.date(2026, 1, 3)


def test_a_job_has_not_fired_initially(any_stage):
    assert loops._scheduled_job_already_fired("recap", TODAY) is False


def test_marking_then_checking(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TODAY) is True


def test_a_new_day_resets_it(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TOMORROW) is False


def test_jobs_are_independent(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("weekend_scan", TODAY) is False


def test_marking_twice_is_idempotent(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TODAY) is True


def test_no_scheduled_jobs_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "scheduled_jobs:db":
        pytest.skip("file absence is only asserted at the db stage")
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert not os.path.exists(os.path.join(tmp_path, "scheduled_jobs.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/commands/test_scheduled_jobs_db.py -q
```

Expected: the `db` parametrisations fail.

- [ ] **Step 3: Write the repository and branch**

Create `swingbot/core/db/repositories/scheduled.py`:

```python
"""Fire-once-a-day memory for the recap and weekend scan."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import scheduled_jobs


class ScheduledJobRepository(Repository):
    def __init__(self):
        super().__init__(scheduled_jobs, key="job")

    def fired_on(self, job: str, *, conn=None) -> str | None:
        row = self.get(job, conn=conn)
        return None if row is None else row.get("fired_on")

    def mark(self, job: str, date_iso: str, *, conn=None) -> None:
        self.upsert({"job": job, "fired_on": date_iso}, conn=conn)


_repo: ScheduledJobRepository | None = None


def scheduled_repo() -> ScheduledJobRepository:
    global _repo
    if _repo is None:
        _repo = ScheduledJobRepository()
    return _repo
```

Branch the two functions in `loops.py`:

```python
def _scheduled_job_already_fired(job: str, today: dt.date) -> bool:
    from swingbot.core.db import stages
    if stages.reads_db("scheduled_jobs"):
        from swingbot.core.db.repositories.scheduled import scheduled_repo
        return scheduled_repo().fired_on(job) == today.isoformat()
    data = read_json(_scheduled_jobs_path(), {})
    return isinstance(data, dict) and data.get(job) == today.isoformat()


def _mark_scheduled_job_fired(job: str, today: dt.date) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("scheduled_jobs"):
        data = read_json(_scheduled_jobs_path(), {})
        if not isinstance(data, dict):
            data = {}
        data[job] = today.isoformat()
        atomic_write_json(_scheduled_jobs_path(), data)
    if stages.writes_db("scheduled_jobs"):
        from swingbot.core.db.repositories.scheduled import scheduled_repo
        scheduled_repo().mark(job, today.isoformat())
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs_db.py
python scripts/dev/testrun.py file tests/commands/test_scanning_loops.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/scheduled.py \
        swingbot/commands/scanning/loops.py tests/commands/test_scheduled_jobs_db.py
git commit -m "feat(v67): move scheduled-job memory to postgres"
```

---

### Task P3-11: UI preferences

`system.py:516` — a per-user blob, capped at 64 KB, deliberately not a
`config.Field`. The cap and the reasoning both survive.

**Files:**
- Create: `swingbot/core/db/repositories/preferences.py`
- Modify: `swingbot/admin/api_v1/system.py` (`_preferences_path` `:516` and its
  two endpoints)
- Test: `tests/admin/test_preferences_db.py`

**Interfaces:**
- Consumes: `ui_preferences` (P3-01), `stages`.
- Produces: `PreferencesRepository` with `load(owner="admin") -> dict`,
  `save(prefs, owner="admin")`; `preferences_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_preferences_db.py`:

```python
"""UI preferences at each stage, with the size cap intact."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.preferences import PreferencesRepository


@pytest.fixture
def client_at(tmp_path, monkeypatch):
    """An authenticated admin test client with DATA_DIR isolated."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    def _make(stage):
        monkeypatch.setattr(config, "DB_STORES", stage)
        from tests.admin.conftest import authed_client   # existing helper
        return authed_client()
    return _make


def test_json_stage_writes_the_file(client_at, tmp_path, db_conn):
    c = client_at("")
    c.post("/api/v1/system/preferences", json={"columns": ["ticker", "r"]})
    assert os.path.exists(os.path.join(tmp_path, "ui_preferences.json"))
    assert PreferencesRepository().count(conn=db_conn) == 0


def test_db_stage_round_trips_through_a_row(client_at, tmp_path, db_committed):
    c = client_at("preferences:db")
    c.post("/api/v1/system/preferences", json={"columns": ["ticker", "r"]})
    got = c.get("/api/v1/system/preferences").get_json()
    assert got["columns"] == ["ticker", "r"]
    assert not os.path.exists(os.path.join(tmp_path, "ui_preferences.json"))


def test_the_64kb_cap_still_refuses(client_at, db_committed):
    c = client_at("preferences:db")
    huge = {"blob": "x" * (64 * 1024 + 1)}
    resp = c.post("/api/v1/system/preferences", json=huge)
    assert resp.status_code >= 400
    assert PreferencesRepository().load(conn=db_committed) == {}


def test_an_empty_store_reads_as_an_empty_dict(db_conn):
    assert PreferencesRepository().load(conn=db_conn) == {}


def test_saving_twice_keeps_one_row(db_conn):
    repo = PreferencesRepository()
    repo.save({"a": 1}, conn=db_conn)
    repo.save({"a": 2}, conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.load(conn=db_conn) == {"a": 2}
```

`tests/admin/conftest.py`'s existing authenticated-client helper is named in the
import above — check its actual name with
`grep -n "^def \|^@pytest.fixture" tests/admin/conftest.py` and use that one.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_preferences_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository and branch the endpoints**

Create `swingbot/core/db/repositories/preferences.py`:

```python
"""Per-user UI state: column-picker visibility, and whatever follows.

Still deliberately NOT a config.Field -- see the reasoning in
admin/api_v1/system.py's get_preferences docstring, which the move to Postgres
does not change. What it does change is that a row does not need the whole .env
rewritten to toggle one column.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ui_preferences

DEFAULT_OWNER = "admin"


class PreferencesRepository(Repository):
    def __init__(self):
        super().__init__(ui_preferences, key="owner")

    def load(self, owner: str = DEFAULT_OWNER, *, conn=None) -> dict:
        row = self.get(owner, conn=conn)
        if row is None:
            return {}
        return {k: v for k, v in row.items() if k != "owner"}

    def save(self, prefs: dict, owner: str = DEFAULT_OWNER, *, conn=None) -> None:
        self.upsert({"owner": owner, **prefs}, conn=conn)


_repo: PreferencesRepository | None = None


def preferences_repo() -> PreferencesRepository:
    global _repo
    if _repo is None:
        _repo = PreferencesRepository()
    return _repo
```

Branch the two endpoints in `system.py` on `stages.reads_db("preferences")` /
`writes_db("preferences")`. **Leave the `_PREFERENCES_MAX_BYTES` check exactly
where it is**, before either write — the reason it exists ("someone using the
admin as a key-value store") is unchanged by the storage, and moving it below the
branch would let the db path accept what the file path refuses.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_preferences_db.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/preferences.py \
        swingbot/admin/api_v1/system.py tests/admin/test_preferences_db.py
git commit -m "feat(v67): move UI preferences to postgres"
```

---

### Task P3-12: The settings audit log

`helpers.py:181-215` — append-only JSONL, read tail-first.

**Files:**
- Create: `swingbot/core/db/repositories/settings_audit.py`
- Modify: `swingbot/admin/helpers.py` (`append_settings_audit`,
  `read_settings_audit`)
- Test: `tests/admin/test_settings_audit_db.py`

**Interfaces:**
- Consumes: `settings_audit` (P3-01), `stages`.
- Produces: `SettingsAuditRepository` with `append(changes: list)`,
  `recent(n=20) -> list[dict]`; `settings_audit_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_settings_audit_db.py`:

```python
"""The audit log: append-only, newest first, never lossy."""
import os

import pytest

from swingbot import config
from swingbot.admin import helpers
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository


@pytest.fixture(params=["", "settings_audit:dual", "settings_audit:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


DIFF = [{"key": "MIN_ALERT_CONFIDENCE_LEVEL", "old": "3", "new": "4"}]


def test_an_empty_diff_writes_nothing(any_stage):
    helpers.append_settings_audit([])
    assert helpers.read_settings_audit() == []


def test_append_then_read(any_stage):
    helpers.append_settings_audit(DIFF)
    rows = helpers.read_settings_audit()
    assert len(rows) == 1
    assert rows[0]["changes"][0]["key"] == "MIN_ALERT_CONFIDENCE_LEVEL"


def test_entries_are_newest_first(any_stage):
    helpers.append_settings_audit([{"key": "A", "old": "1", "new": "2"}])
    helpers.append_settings_audit([{"key": "B", "old": "1", "new": "2"}])
    rows = helpers.read_settings_audit()
    assert [r["changes"][0]["key"] for r in rows] == ["B", "A"]


def test_n_limits_the_tail(any_stage):
    for i in range(5):
        helpers.append_settings_audit([{"key": f"K{i}", "old": "1", "new": "2"}])
    assert len(helpers.read_settings_audit(n=2)) == 2


def test_two_identical_changes_are_two_entries(any_stage):
    helpers.append_settings_audit(DIFF)
    helpers.append_settings_audit(DIFF)
    assert len(helpers.read_settings_audit()) == 2


def test_no_jsonl_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "settings_audit:db":
        pytest.skip("file absence is only asserted at the db stage")
    helpers.append_settings_audit(DIFF)
    assert not os.path.exists(os.path.join(tmp_path, "settings_audit.jsonl"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_settings_audit_db.py -q
```

Expected: the `db` parametrisations fail.

- [ ] **Step 3: Write the repository and branch**

Create `swingbot/core/db/repositories/settings_audit.py`:

```python
"""Append-only settings audit log."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import settings_audit


class SettingsAuditRepository(Repository):
    def __init__(self):
        # Keyed by the surrogate id: two identical changes a minute apart are
        # two entries, so there is no natural key to use.
        super().__init__(settings_audit, key="id")

    def append(self, changes: list, *, conn=None) -> dict:
        return self.insert({
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "changes": changes,
        }, conn=conn)

    def recent(self, n: int = 20, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn,
                             order_by=settings_audit.c.ts.desc(), limit=n)


_repo: SettingsAuditRepository | None = None


def settings_audit_repo() -> SettingsAuditRepository:
    global _repo
    if _repo is None:
        _repo = SettingsAuditRepository()
    return _repo
```

`append_settings_audit(diff)` keeps its `if not diff: return` guard at the top —
before either branch — and then writes per stage. `read_settings_audit(n)` gains
the `reads_db` branch.

One shape difference to preserve: the file version stores `{"ts", "changes"}`
where `changes` is a list of `{key, old, new}` dicts built from `diff`. The
repository stores the same thing, so `read_settings_audit`'s callers see an
identical structure at either stage. Build the `changes` list once, above the
branch, exactly as P2-18 stamps `created_at` once.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_settings_audit_db.py
python scripts/dev/testrun.py file tests/admin/test_helpers.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/settings_audit.py swingbot/admin/helpers.py \
        tests/admin/test_settings_audit_db.py
git commit -m "feat(v67): move the settings audit log to postgres"
```

---

### Task P3-13: The ticker directory

`ticker_directory.py` caches ~10k NASDAQ/NYSE rows for a week, with a module
global (`_directory`, `_symbol_map`, `_loaded_at`) in front of it. The cache is
regenerable, so this is one of the two stores whose **read** may fall back to
recomputation.

**Files:**
- Create: `swingbot/core/db/repositories/ticker_directory.py`
- Modify: `swingbot/core/marketdata/ticker_directory.py` (`_save_cache` `:103`,
  `_load_cache` `:113`)
- Test: `tests/marketdata/test_ticker_directory_db.py`

**Interfaces:**
- Consumes: `ticker_directory` (P3-01), `stages`.
- Produces: `TickerDirectoryRepository` with `replace(rows)`,
  `all_rows() -> list[dict]`, `loaded_at() -> float`, `search(query, limit)`;
  `ticker_directory_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_ticker_directory_db.py`:

```python
"""A regenerable cache: reads may fall back, writes still go where the stage
says."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
from swingbot.core.marketdata import ticker_directory as td


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "ticker_directory:db")
    monkeypatch.setattr(td, "_directory", None)
    monkeypatch.setattr(td, "_symbol_map", {})
    monkeypatch.setattr(td, "_loaded_at", 0.0)


ROWS = [{"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corporation"},
        {"symbol": "MSTR", "name": "MicroStrategy Inc."}]


def test_replace_then_read_back(db_stage):
    repo = TickerDirectoryRepository()
    repo.replace(ROWS)
    assert {r["symbol"] for r in repo.all_rows()} == {"AAPL", "MSFT", "MSTR"}


def test_replace_removes_delisted_symbols(db_stage):
    repo = TickerDirectoryRepository()
    repo.replace(ROWS)
    repo.replace([{"symbol": "AAPL", "name": "Apple Inc."}])
    assert [r["symbol"] for r in repo.all_rows()] == ["AAPL"]


def test_lookup_name_reads_rows(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert td.lookup_name("AAPL") == "Apple Inc."


def test_lookup_name_is_none_for_an_unknown_symbol(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert td.lookup_name("NOTREAL") is None


def test_search_matches_symbol_prefix(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    hits = {h["symbol"] for h in td.search_tickers("MS", limit=10)}
    assert {"MSFT", "MSTR"} <= hits


def test_search_matches_company_name(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    hits = {h["symbol"] for h in td.search_tickers("Apple", limit=10)}
    assert "AAPL" in hits


def test_search_honours_the_limit(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert len(td.search_tickers("M", limit=1)) == 1


def test_an_unreachable_database_degrades_to_a_refetch_not_a_crash(
        db_stage, monkeypatch):
    """The spec's one read-side exemption: a regenerable cache may fall back to
    recomputation. Trading state may not."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    monkeypatch.setattr(td, "_build_directory", lambda: ROWS)
    assert td.lookup_name("AAPL") == "Apple Inc."
    dbengine.reset_engine()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/marketdata/test_ticker_directory_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/ticker_directory.py`:

```python
"""The NASDAQ/NYSE symbol directory. Regenerable, so reads may fall back."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ticker_directory


class TickerDirectoryRepository(Repository):
    def __init__(self):
        super().__init__(ticker_directory, key="symbol")

    def replace(self, rows: list[dict], *, conn=None) -> None:
        """Swap the whole directory in one transaction.

        A weekly refresh drops delisted symbols, so this is a replace rather
        than an upsert sweep -- and it is one transaction so a concurrent
        lookup never sees an empty directory.
        """
        with transaction(conn) as c:
            c.execute(sa.delete(ticker_directory))
            for row in rows:
                self.insert(row, conn=c)

    def all_rows(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, order_by=ticker_directory.c.symbol.asc())

    def loaded_at(self, *, conn=None) -> float:
        """Newest updated_at as a unix timestamp, or 0.0 when empty --
        the shape _ensure_loaded's staleness check already expects."""
        stmt = sa.select(sa.func.max(ticker_directory.c.updated_at))
        with self._tx(conn) as c:
            newest = c.execute(stmt).scalar_one_or_none()
        return newest.timestamp() if newest is not None else 0.0

    def search(self, query: str, limit: int = 15, *, conn=None) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        pattern = f"{q}%"
        contains = f"%{q}%"
        return self.list_all(
            conn=conn,
            where=sa.or_(ticker_directory.c.symbol.ilike(pattern),
                         ticker_directory.c.name.ilike(contains)),
            # Symbol prefix matches first, then name matches -- the ordering
            # search_tickers() produces today.
            order_by=(sa.case((ticker_directory.c.symbol.ilike(pattern), 0),
                              else_=1),
                      ticker_directory.c.symbol.asc()),
            limit=limit,
        )


_repo: TickerDirectoryRepository | None = None


def ticker_directory_repo() -> TickerDirectoryRepository:
    global _repo
    if _repo is None:
        _repo = TickerDirectoryRepository()
    return _repo
```

- [ ] **Step 4: Branch the cache functions with a fallback**

```python
def _save_cache(rows: list[dict]) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("ticker_directory"):
        # ... existing file body ...
        pass
    if stages.writes_db("ticker_directory"):
        from swingbot.core.db.repositories.ticker_directory import ticker_directory_repo
        ticker_directory_repo().replace(rows)


def _load_cache() -> tuple[list[dict], float]:
    """Returns (rows, loaded_at).

    This is one of the TWO stores whose read may fall back (the other is
    rs_cache, Part 5). The spec's fail-fast rule protects trading state; a
    directory of listed symbols is regenerable from the exchange in seconds,
    and refusing to start the bot because a cache was unreachable would be
    strictly worse than re-downloading it.
    """
    from swingbot.core.db import stages
    if stages.reads_db("ticker_directory"):
        try:
            from swingbot.core.db.repositories.ticker_directory import (
                ticker_directory_repo)
            repo = ticker_directory_repo()
            return repo.all_rows(), repo.loaded_at()
        except Exception:
            log.warning("ticker directory cache unreadable from the database; "
                        "will re-download", exc_info=True)
            return [], 0.0
    # ... existing file body ...
```

`lookup_name` and `search_tickers` go through `_ensure_loaded()`, which uses
`_load_cache()`, so they need no edit. Except `search_tickers` — at the db stage
it should use `repo.search()` rather than scanning the in-memory list, so the
`ticker_directory_name_idx` earns its keep. Branch it too.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/marketdata/test_ticker_directory_db.py
python scripts/dev/testrun.py file tests/marketdata/test_ticker_directory.py
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/ticker_directory.py \
        swingbot/core/marketdata/ticker_directory.py \
        tests/marketdata/test_ticker_directory_db.py
git commit -m "feat(v67): move the ticker directory to postgres"
```

---

### Task P3-14: Tuning results

`queries.py:271` reads `data/tuning_results/<job_id>.json`, with the `job_id`
flowing straight from a query parameter into a filesystem path — guarded by
`_JOB_ID_RE`. As a row that guard's *purpose* disappears (there is no path to
traverse), so the check stays as validation rather than as a security boundary,
and the comment must say which it now is.

**Files:**
- Create: `swingbot/core/db/repositories/tuning.py`
- Modify: `swingbot/admin/queries.py:267-278` (`_load_result`)
- Modify: `swingbot/admin/jobs.py:209` (the result-file write)
- Test: `tests/admin/test_tuning_results_db.py`

**Interfaces:**
- Consumes: `tuning_results` (P3-01), `stages`.
- Produces: `TuningRepository` with `save_result(job_id, payload)`,
  `result(job_id) -> dict | None`; `tuning_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_tuning_results_db.py`:

```python
"""Tuning results as rows, and the job-id guard that outlives its reason."""
import pytest

from swingbot import config
from swingbot.admin import queries
from swingbot.core.db.repositories.tuning import TuningRepository


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "tuning:db")


PAYLOAD = {"strategy": "RSI", "rows": [{"n_eval": 42, "win_rate": 81.0}]}


def test_save_then_load(db_stage):
    TuningRepository().save_result("job-abc123", PAYLOAD)
    assert queries._load_result("job-abc123")["strategy"] == "RSI"


def test_a_missing_job_returns_none(db_stage):
    assert queries._load_result("job-nope") is None


def test_a_malformed_job_id_is_still_refused(db_stage):
    """The regex existed because job_id reached a filesystem path. It no
    longer does -- and it stays, now as input validation rather than as a
    traversal guard, because a client sending nonsense is still a bug worth
    refusing rather than turning into a query."""
    assert queries._load_result("../../etc/passwd") is None
    assert queries._load_result("job abc") is None


def test_saving_twice_replaces(db_stage):
    repo = TuningRepository()
    repo.save_result("job-abc123", {"strategy": "RSI"})
    repo.save_result("job-abc123", {"strategy": "MACD"})
    assert repo.count() == 1
    assert repo.result("job-abc123")["strategy"] == "MACD"


def test_a_large_result_round_trips(db_stage):
    big = {"rows": [{"i": i, "win_rate": 50.0 + i} for i in range(2000)]}
    TuningRepository().save_result("job-big00", big)
    assert len(queries._load_result("job-big00")["rows"]) == 2000
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_tuning_results_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository and branch both ends**

Create `swingbot/core/db/repositories/tuning.py`:

```python
"""Grid-tuning results and proposals."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import tuning_proposals, tuning_results


class TuningRepository(Repository):
    def __init__(self):
        super().__init__(tuning_results, key="job_id")

    def save_result(self, job_id: str, payload: dict, *, conn=None) -> dict:
        return self.upsert({
            "job_id": job_id,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **payload,
        }, conn=conn)

    def result(self, job_id: str, *, conn=None) -> dict | None:
        row = self.get(job_id, conn=conn)
        if row is None:
            return None
        return {k: v for k, v in row.items()
                if k not in ("job_id", "created_at")}


_repo: TuningRepository | None = None


def tuning_repo() -> TuningRepository:
    global _repo
    if _repo is None:
        _repo = TuningRepository()
    return _repo
```

`_load_result` keeps the `_JOB_ID_RE` check — rewrite only its comment:

```python
def _load_result(job_id: str) -> dict | None:
    if not _JOB_ID_RE.match(job_id):
        # Input validation, not a traversal guard. It was a traversal guard
        # when job_id was interpolated into a filesystem path; at the db stage
        # it is a parameterised query and there is no path to escape. Kept
        # because a client sending a malformed id is still a bug, and refusing
        # it is cheaper than looking it up.
        return None
    from swingbot.core.db import stages
    if stages.reads_db("tuning"):
        from swingbot.core.db.repositories.tuning import tuning_repo
        return tuning_repo().result(job_id)
    # ... existing file body ...
```

`admin/jobs.py:209` writes `results_dir/<job_id>.json` when a job finishes; add
the `writes_db("tuning")` branch calling `tuning_repo().save_result(job_id, payload)`.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_tuning_results_db.py
python scripts/dev/testrun.py file tests/admin/test_queries.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/tuning.py swingbot/admin/queries.py \
        swingbot/admin/jobs.py tests/admin/test_tuning_results_db.py
git commit -m "feat(v67): move tuning results to postgres"
```

---

### Task P3-15: Tuning proposals

`queries.py:294` lists `data/tuning_proposals/*.json` sorted reverse by
filename — which is how "newest first" was implemented, because the filenames
are timestamps. As rows that becomes an `ORDER BY created_at DESC`, and the
filename stays only as the identity it already is.

**Files:**
- Modify: `swingbot/core/db/repositories/tuning.py` (add `ProposalRepository`)
- Modify: `swingbot/admin/queries.py:294` (`_list_proposals`)
- Test: `tests/admin/test_tuning_proposals_db.py`

**Interfaces:**
- Consumes: `tuning_proposals` (P3-01), `stages`.
- Produces: `ProposalRepository` with `save(filename, payload)`,
  `all_proposals() -> list[dict]`; `proposals_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_tuning_proposals_db.py`:

```python
"""Proposals: newest first, filename preserved as identity."""
import pytest

from swingbot import config
from swingbot.admin import queries
from swingbot.core.db.repositories.tuning import ProposalRepository


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "tuning:db")


def test_an_empty_store_lists_nothing(db_stage):
    assert queries._list_proposals() == []


def test_each_row_keeps_its_filename(db_stage):
    ProposalRepository().save("2026-01-02-rsi.json", {"strategy": "RSI"})
    rows = queries._list_proposals()
    assert rows[0]["filename"] == "2026-01-02-rsi.json"
    assert rows[0]["strategy"] == "RSI"


def test_newest_first(db_stage):
    repo = ProposalRepository()
    repo.save("2026-01-01-a.json", {"strategy": "A"},
              created_at="2026-01-01T00:00:00+00:00")
    repo.save("2026-02-01-b.json", {"strategy": "B"},
              created_at="2026-02-01T00:00:00+00:00")
    assert [r["strategy"] for r in queries._list_proposals()] == ["B", "A"]


def test_saving_the_same_filename_twice_replaces(db_stage):
    repo = ProposalRepository()
    repo.save("p.json", {"strategy": "A"})
    repo.save("p.json", {"strategy": "B"})
    assert repo.count() == 1
    assert queries._list_proposals()[0]["strategy"] == "B"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_tuning_proposals_db.py -q
```

Expected: `ImportError: cannot import name 'ProposalRepository'`.

- [ ] **Step 3: Add the repository and branch the lister**

Append to `swingbot/core/db/repositories/tuning.py`:

```python
class ProposalRepository(Repository):
    def __init__(self):
        super().__init__(tuning_proposals, key="filename")

    def save(self, filename: str, payload: dict, *,
             created_at: str | None = None, conn=None) -> dict:
        return self.upsert({
            "filename": filename,
            "created_at": created_at or dt.datetime.now(dt.timezone.utc).isoformat(),
            **payload,
        }, conn=conn)

    def all_proposals(self, *, conn=None) -> list[dict]:
        """Newest first. The file version got this from sorted(..., reverse=True)
        over timestamp-shaped filenames, which is the same ordering as long as
        the naming convention holds. created_at does not depend on it."""
        return self.list_all(conn=conn,
                             order_by=tuning_proposals.c.created_at.desc())
```

`_list_proposals()` gains the `reads_db("tuning")` branch returning
`proposals_repo().all_proposals()`. The returned dicts already carry `filename`,
which is the shape the existing caller expects (`{"filename": fname, **data}`).

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_tuning_proposals_db.py
python scripts/dev/testrun.py file tests/admin/test_queries.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/tuning.py swingbot/admin/queries.py \
        tests/admin/test_tuning_proposals_db.py
git commit -m "feat(v67): move tuning proposals to postgres"
```

---

