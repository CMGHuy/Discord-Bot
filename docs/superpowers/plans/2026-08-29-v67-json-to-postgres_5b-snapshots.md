# v67 — Part 5: Retrospective and snapshots (tasks P5-05…P5-07)

> Continuation of `2026-08-29-v67-json-to-postgres_5a-logs.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_5a` file before starting any task here** — the
> Parallelisation map, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P5-05: Retrospective history

`retrospective.py:52` — a small per-day history the escalation ladder reads to
tell "first time this has happened" from "third day in a row", and to notice
when a suggested config change was actually applied.

**Files:**
- Create: `swingbot/core/db/repositories/retrospective.py`
- Modify: `swingbot/core/tracking/retrospective.py` (`_load_history` `:67`,
  `_save_history` `:78`)
- Test: `tests/tracking/test_retrospective_history_db.py`

**Interfaces:**
- Consumes: `retrospective_history` (P5-01), `stages`.
- Produces: `RetrospectiveRepository` with `history() -> list[dict]`,
  `put_day(entry)`; `retrospective_repo()`.

**Two shape facts to preserve:** `_load_history` returns a **list**, ordered as
written (which the ladder walks by day), and `_save_history` writes the whole
list. The repository keeps the list contract and upserts per day, so a save no
longer rewrites days that did not change.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_retrospective_history_db.py`:

```python
"""Per-day retrospective memory."""
import os

import pytest

from swingbot import config
from swingbot.core.tracking import retrospective as retro


@pytest.fixture(params=["", "retrospective:dual", "retrospective:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(retro, "_HISTORY_PATH",
                        os.path.join(tmp_path, "retrospective_history.json"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def _entry(day, **over):
    e = {"day": day, "issues": ["low_win_rate"],
         "config": {"MIN_ALERT_CONFIDENCE_LEVEL": 3}}
    e.update(over)
    return e


def test_an_empty_store_reads_as_an_empty_list(any_stage):
    assert retro._load_history() == []


def test_save_then_load(any_stage):
    retro._save_history([_entry("2026-01-02")])
    history = retro._load_history()
    assert len(history) == 1 and history[0]["day"] == "2026-01-02"


def test_history_is_chronological(any_stage):
    retro._save_history([_entry("2026-01-02"), _entry("2026-01-03")])
    assert [e["day"] for e in retro._load_history()] == ["2026-01-02", "2026-01-03"]


def test_saving_the_same_day_twice_keeps_one_entry(any_stage):
    retro._save_history([_entry("2026-01-02", issues=["a"])])
    retro._save_history([_entry("2026-01-02", issues=["b"])])
    history = retro._load_history()
    assert len(history) == 1 and history[0]["issues"] == ["b"]


def test_a_config_snapshot_round_trips(any_stage):
    retro._save_history([_entry("2026-01-02")])
    assert retro._load_history()[0]["config"]["MIN_ALERT_CONFIDENCE_LEVEL"] == 3


def test_find_day_entry_still_works(any_stage):
    import datetime as dt
    retro._save_history([_entry("2026-01-02"), _entry("2026-01-03")])
    found = retro._find_day_entry(retro._load_history(), dt.date(2026, 1, 3))
    assert found is not None and found["day"] == "2026-01-03"


def test_the_consecutive_streak_counter_still_works(any_stage):
    import datetime as dt
    retro._save_history([_entry(f"2026-01-{d:02d}") for d in (2, 5, 6)])
    streak = retro._consecutive_bad_streak(retro._load_history(),
                                           dt.date(2026, 1, 6), "low_win_rate")
    assert streak >= 1


def test_no_history_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "retrospective:db":
        pytest.skip("file absence is only asserted at the db stage")
    retro._save_history([_entry("2026-01-02")])
    assert not os.path.exists(os.path.join(tmp_path, "retrospective_history.json"))
```

`_find_day_entry` and `_consecutive_bad_streak` take a history list and a date —
**read their real signatures at `retrospective.py:98` and `:106` before writing
these two tests** and match them. They are included because they are the two
consumers whose behaviour a shape change would break silently.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/tracking/test_retrospective_history_db.py -q
```

Expected: the `db` parametrisations fail.

- [ ] **Step 3: Write the repository and branch**

Create `swingbot/core/db/repositories/retrospective.py`:

```python
"""Per-day retrospective memory for the escalation ladder."""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import retrospective_history


class RetrospectiveRepository(Repository):
    def __init__(self):
        super().__init__(retrospective_history, key="day")

    def history(self, *, conn=None) -> list[dict]:
        """Chronological, which is how the ladder walks it."""
        return self.list_all(conn=conn,
                             order_by=retrospective_history.c.day.asc())

    def put_day(self, entry: dict, *, conn=None) -> dict:
        return self.upsert(entry, conn=conn)


_repo: RetrospectiveRepository | None = None


def retrospective_repo() -> RetrospectiveRepository:
    global _repo
    if _repo is None:
        _repo = RetrospectiveRepository()
    return _repo
```

`_load_history()` gains a `reads_db("retrospective")` branch returning
`retrospective_repo().history()`; `_save_history(history)` writes the file per
stage and, on the db side, upserts each entry:

```python
def _save_history(history: list[dict]) -> None:
    from swingbot.core.db import stages
    if stages.writes_json("retrospective"):
        # ... existing file body, unchanged ...
        pass
    if stages.writes_db("retrospective"):
        from swingbot.core.db.repositories.retrospective import retrospective_repo
        repo = retrospective_repo()
        # Upsert per day rather than replace-all: a save no longer rewrites
        # days that did not change, which is the same lost-update fix every
        # other store in this plan gets.
        for entry in history:
            repo.put_day(entry)
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/tracking/test_retrospective_history_db.py
python scripts/dev/testrun.py file tests/tracking/test_retrospective.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/retrospective.py \
        swingbot/core/tracking/retrospective.py \
        tests/tracking/test_retrospective_history_db.py
git commit -m "feat(v67): move retrospective history to postgres"
```

---

### Task P5-06: The analytics snapshot

`analytics_snapshot.json` is the pre-built blob every UI reads instead of
recomputing. It is derived, so its **read** may fall back — but the fallback is
not "recompute silently", it is `load_snapshot()`'s existing `None` return,
which callers already handle by rebuilding.

**Files:**
- Create: `swingbot/core/db/repositories/snapshots.py`
- Modify: `swingbot/core/analytics/snapshots.py` (`save_snapshot` `:70`,
  `load_snapshot` `:74`)
- Test: `tests/analytics/test_analytics_snapshot_db.py`

**Interfaces:**
- Consumes: `analytics_snapshot` (P5-01), `stages`.
- Produces: `AnalyticsSnapshotRepository` with `save(snapshot)`,
  `load(max_age_seconds=3600) -> dict | None`; `analytics_snapshot_repo()`.

**The staleness contract is the whole point of this store.** `load_snapshot`
takes `max_age_seconds=3600` and returns `None` past it — a screen that hides
how stale its data is has a correctness bug, and this is where that is enforced.
The `built_at` column carries the age, so the check is a `WHERE`, not a file
mtime.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_analytics_snapshot_db.py`:

```python
"""The snapshot, and the staleness rule that makes it safe to read."""
import datetime as dt
import os

import pytest

from swingbot import config
from swingbot.core.analytics import snapshots


@pytest.fixture(params=["", "analytics:dual", "analytics:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(snapshots, "DEFAULT_PATH",
                        os.path.join(tmp_path, "analytics_snapshot.json"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


SNAP = {"overall": {"n": 12, "win_rate": 58.3, "expectancy_r": 0.42},
        "by_strategy": {"RSI": {"n": 7}}}


def test_an_empty_store_loads_as_none(any_stage):
    assert snapshots.load_snapshot() is None


def test_save_then_load(any_stage):
    snapshots.save_snapshot(dict(SNAP))
    loaded = snapshots.load_snapshot()
    assert loaded["overall"]["expectancy_r"] == 0.42


def test_saving_twice_keeps_one_snapshot(any_stage):
    snapshots.save_snapshot({"overall": {"n": 1}})
    snapshots.save_snapshot({"overall": {"n": 2}})
    assert snapshots.load_snapshot()["overall"]["n"] == 2


def test_a_stale_snapshot_loads_as_none(any_stage):
    """Not 'loads with a warning' -- None, so the caller rebuilds. A screen
    that shows stale numbers without saying so has a correctness bug."""
    snapshots.save_snapshot(dict(SNAP))
    assert snapshots.load_snapshot(max_age_seconds=0) is None


def test_a_fresh_snapshot_loads_within_its_window(any_stage):
    snapshots.save_snapshot(dict(SNAP))
    assert snapshots.load_snapshot(max_age_seconds=3600) is not None


def test_nested_numbers_survive_the_round_trip(any_stage):
    snapshots.save_snapshot(dict(SNAP))
    assert snapshots.load_snapshot()["by_strategy"]["RSI"]["n"] == 7


def test_the_snapshot_is_numerically_identical_across_backends(
        any_stage, tmp_path, monkeypatch, db_committed):
    """Success criterion 3, for this store."""
    monkeypatch.setattr(config, "DB_STORES", "")
    snapshots.save_snapshot(dict(SNAP))
    from_file = snapshots.load_snapshot()
    monkeypatch.setattr(config, "DB_STORES", "analytics:db")
    snapshots.save_snapshot(dict(SNAP))
    assert snapshots.load_snapshot() == from_file


def test_no_snapshot_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "analytics:db":
        pytest.skip("file absence is only asserted at the db stage")
    snapshots.save_snapshot(dict(SNAP))
    assert not os.path.exists(os.path.join(tmp_path, "analytics_snapshot.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/analytics/test_analytics_snapshot_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/snapshots.py`:

```python
"""The pre-built analytics snapshot, and the scan-to-scan presentation cache."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import analytics_snapshot, scan_snapshots

CURRENT = "current"


class AnalyticsSnapshotRepository(Repository):
    def __init__(self):
        super().__init__(analytics_snapshot, key="key")

    def save(self, snapshot: dict, *, conn=None) -> dict:
        return self.upsert({
            "key": CURRENT,
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **snapshot,
        }, conn=conn)

    def load(self, max_age_seconds: int = 3600, *, conn=None) -> dict | None:
        """The snapshot, or None if it is older than max_age_seconds.

        None rather than a stale blob with a warning: every caller already
        handles None by rebuilding, and a screen that renders stale numbers
        without saying so is the bug this window exists to prevent.
        """
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(seconds=max_age_seconds))
        rows = self.list_all(conn=conn, where=sa.and_(
            analytics_snapshot.c.key == CURRENT,
            analytics_snapshot.c.built_at >= cutoff,
        ), limit=1)
        if not rows:
            return None
        return {k: v for k, v in rows[0].items() if k not in ("key", "built_at")}


class ScanSnapshotRepository(Repository):
    def __init__(self):
        super().__init__(scan_snapshots, key="key")

    def all_snapshots(self, *, conn=None) -> dict[str, dict]:
        return {r["key"]: {k: v for k, v in r.items() if k != "key"}
                for r in self.list_all(conn=conn)}

    def put(self, key: str, snapshot: dict, *, conn=None) -> None:
        self.upsert({"key": key, **snapshot}, conn=conn)


_analytics: AnalyticsSnapshotRepository | None = None
_scan: ScanSnapshotRepository | None = None


def analytics_snapshot_repo() -> AnalyticsSnapshotRepository:
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsSnapshotRepository()
    return _analytics


def scan_snapshot_repo() -> ScanSnapshotRepository:
    global _scan
    if _scan is None:
        _scan = ScanSnapshotRepository()
    return _scan
```

- [ ] **Step 4: Branch save and load**

`save_snapshot(snap, path=None)` writes the file when
`path is not None or stages.writes_json("analytics")`, and the row when
`path is None and stages.writes_db("analytics")`. `load_snapshot(path=None,
max_age_seconds=3600)` reads the row when `path is None and
stages.reads_db("analytics")`, keeping its existing mtime-based file body below
the branch. `refresh_snapshot()` needs no edit — it goes through both.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/analytics/test_analytics_snapshot_db.py
python scripts/dev/testrun.py file tests/analytics/test_snapshots.py
```

Expected: `0 failed` for both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/snapshots.py \
        swingbot/core/analytics/snapshots.py \
        tests/analytics/test_analytics_snapshot_db.py
git commit -m "feat(v67): move the analytics snapshot to postgres"
```

---

### Task P5-07: Scan presentation snapshots

`core/scanning/snapshots.py` keys the last presented scenario by ticker +
horizon + direction, so the next scan can render a "changed since last time"
line. `_save_scan_snapshots` swallows `OSError` — this store has never been
allowed to break a scan, and that survives.

**Files:**
- Modify: `swingbot/core/scanning/snapshots.py` (`_load_scan_snapshots` `:10`,
  `_save_scan_snapshots` `:20`)
- Test: `tests/scanning/test_scan_snapshots_db.py`

**Interfaces:**
- Consumes: `scan_snapshot_repo` (P5-06), `stages`.
- Produces: no new public symbols.

**Fourth documented exception to fail-fast, and the reasoning is the same shape
as the heartbeat's:** this store exists to add one cosmetic line to an alert. A
write failure here taking the scan down would mean no alert at all, which is
strictly worse than an alert without its diff line. The existing bare `except
OSError: pass` is preserved and widened to cover the database write.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_scan_snapshots_db.py`:

```python
"""Presentation snapshots: cosmetic, and never allowed to break a scan."""
import os

import pytest

from swingbot import config
from swingbot.core.scanning import snapshots as snaps


@pytest.fixture(params=["", "scan_snapshots:dual", "scan_snapshots:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(snaps, "_SNAPSHOT_PATH",
                        os.path.join(tmp_path, "scan_snapshots.json"))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


ENTRY = {"entry": 100.0, "stop_loss": 95.0, "target": 110.0, "confidence": 4}


def test_an_empty_store_loads_as_an_empty_dict(any_stage):
    assert snaps._load_scan_snapshots() == {}


def test_save_then_load(any_stage):
    snaps._save_scan_snapshots({"AAPL|2w|bullish": ENTRY})
    loaded = snaps._load_scan_snapshots()
    assert loaded["AAPL|2w|bullish"]["entry"] == 100.0


def test_keys_are_independent(any_stage):
    snaps._save_scan_snapshots({"AAPL|2w|bullish": ENTRY,
                                "MSFT|2w|bearish": dict(ENTRY, entry=50.0)})
    loaded = snaps._load_scan_snapshots()
    assert loaded["MSFT|2w|bearish"]["entry"] == 50.0


def test_saving_the_same_key_twice_replaces_it(any_stage):
    snaps._save_scan_snapshots({"K": dict(ENTRY, entry=1.0)})
    snaps._save_scan_snapshots({"K": dict(ENTRY, entry=2.0)})
    assert snaps._load_scan_snapshots()["K"]["entry"] == 2.0


def test_a_write_failure_never_raises(any_stage, monkeypatch):
    """Fourth documented exception to fail-fast. This store adds one cosmetic
    line to an alert; a failure here taking the scan down would mean no alert
    at all, which is strictly worse."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    snaps._save_scan_snapshots({"K": ENTRY})      # must not raise
    dbengine.reset_engine()


def test_a_read_failure_degrades_to_an_empty_dict(any_stage, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    assert snaps._load_scan_snapshots() == {}
    dbengine.reset_engine()


def test_no_snapshots_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "scan_snapshots:db":
        pytest.skip("file absence is only asserted at the db stage")
    snaps._save_scan_snapshots({"K": ENTRY})
    assert not os.path.exists(os.path.join(tmp_path, "scan_snapshots.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scanning/test_scan_snapshots_db.py -q
```

Expected: the `db` parametrisations fail.

- [ ] **Step 3: Branch both, preserving the swallow**

```python
def _load_scan_snapshots() -> dict:
    from swingbot.core.db import stages
    if stages.reads_db("scan_snapshots"):
        try:
            from swingbot.core.db.repositories.snapshots import scan_snapshot_repo
            return scan_snapshot_repo().all_snapshots()
        except Exception:
            # Derived and regenerable: the next scan rewrites every key it
            # touches, so an empty read costs one missing diff line.
            return {}
    if not os.path.exists(_SNAPSHOT_PATH):
        return {}
    try:
        with open(_SNAPSHOT_PATH, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_scan_snapshots(data: dict) -> None:
    """Never raises. This store adds one cosmetic 'changed since last scan'
    line to an alert; a write failure taking the scan down would mean no alert
    at all. The bare except predates this migration and is preserved on
    purpose -- see the spec's failure-behavior section for why trading state
    gets the opposite rule."""
    from swingbot.core.db import stages
    if stages.writes_json("scan_snapshots"):
        try:
            with open(_SNAPSHOT_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
    if stages.writes_db("scan_snapshots"):
        try:
            from swingbot.core.db.repositories.snapshots import scan_snapshot_repo
            repo = scan_snapshot_repo()
            for key, entry in data.items():
                repo.put(key, entry)
        except Exception:
            pass
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_scan_snapshots_db.py
python scripts/dev/testrun.py file tests/scanning/test_snapshots.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/snapshots.py tests/scanning/test_scan_snapshots_db.py
git commit -m "feat(v67): move scan presentation snapshots to postgres"
```

---


**Continue with `2026-08-29-v67-json-to-postgres_5c-caches.md`** (P5-08…P5-14):
the ticker-meta and RS caches, fold trades, importers, parity registration,
retention, and Part 5's verification.
