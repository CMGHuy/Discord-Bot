# v67 — Part 5: Retrospective, snapshots and the metadata cache (tasks P5-05…P5-08)

> Continuation of `2026-08-29-v67-json-to-postgres_5a-logs.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_5a` file before starting any task here** — the
> Parallelisation map, the Alembic revision-id table and the exit criteria live
> there and are not repeated.
>
> *(2026-09-30: P5-08 moved here from `_5c` when `_5c` crossed the
> 1500-line limit after the re-examination edits; the task is unchanged.)*

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P5-05: Retrospective history

`retrospective.py:48` — a small per-day history the escalation ladder reads to
tell "first time this has happened" from "third day in a row", and to notice
when a suggested config change was actually applied.

> **2026-09-30 re-examination: UPDATED — the entry shape was wrong.**
> - Lines: `_HISTORY_PATH` `:48`, `_load_history` `:63`, `_save_history` `:74`,
>   `_find_day_entry` `:94`, `_consecutive_bad_streak` `:102`; the only
>   writer is the "lessons" section at `:588-615`.
> - **The key is `date`, not `day`**, and an entry is
>   `{"date": "YYYY-MM-DD", "closed_count": int, "win_rate": float,
>   "issues": {issue_key: ...}, "config_snapshot": {...}}` — `issues` is a
>   **dict** (`_consecutive_bad_streak` does `entry.get("issues", {}).get(key)`),
>   and the config snapshot is `config_snapshot`, not `config`. P5-01's column
>   is now `date`; the repository key, the tests and the importer are corrected
>   below.
> - **`_save_history` trims.** It sorts by `date` and keeps the last
>   `RETROSPECTIVE_HISTORY_DAYS` (config, default 60) entries. An upsert-only
>   db branch would grow without bound and `_load_history` would return more
>   than the file ever did. The db branch must also delete the days the trim
>   dropped (`RetrospectiveRepository.keep_only(dates)` below) — which also
>   means P5-13 needs no retention for this table.
> - `_save_history` swallows every exception with `log.exception(...)`, and
>   `_load_history` returns `[]` on any failure. The swallow is pre-existing
>   and the retrospective runs inside `_section(...)` guards; keep it on both
>   branches (the log line is the visible failure), rather than tightening it
>   in a migration task.
> - The existing test file is `tests/tracking/test_retrospective_v2.py`
>   (`tests/tracking/test_retrospective.py` does not exist); Step 4 corrected.

**Files:**
- Create: `swingbot/core/db/repositories/retrospective.py`
- Modify: `swingbot/core/tracking/retrospective.py` (`_load_history` `:63`,
  `_save_history` `:74`)
- Test: `tests/tracking/test_retrospective_history_db.py`

**Interfaces:**
- Consumes: `retrospective_history` (P5-01), `stages`.
- Produces: `RetrospectiveRepository` with `history() -> list[dict]`,
  `put_day(entry)`, `keep_only(dates)`; `retrospective_repo()`.

**Three shape facts to preserve:** `_load_history` returns a **list**, ordered
by `date` (which the ladder walks by day), `_save_history` writes the whole
list, and it **trims to the last `RETROSPECTIVE_HISTORY_DAYS` entries**. The
repository keeps the list contract, upserts per day (so a save no longer
rewrites days that did not change), and deletes the days the trim dropped.

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


def _entry(date, **over):
    # The real shape (retrospective.py:606-612): `date`, `issues` a DICT,
    # `config_snapshot` -- not the day/list/config shape first drafted here.
    e = {"date": date, "closed_count": 3, "win_rate": 33.3,
         "issues": {"low_win_rate": True},
         "config_snapshot": {"MIN_ALERT_CONFIDENCE_LEVEL": 3}}
    e.update(over)
    return e


def test_an_empty_store_reads_as_an_empty_list(any_stage):
    assert retro._load_history() == []


def test_save_then_load(any_stage):
    retro._save_history([_entry("2026-01-02")])
    history = retro._load_history()
    assert len(history) == 1 and history[0]["date"] == "2026-01-02"


def test_history_is_chronological(any_stage):
    retro._save_history([_entry("2026-01-03"), _entry("2026-01-02")])
    assert [e["date"] for e in retro._load_history()] == ["2026-01-02", "2026-01-03"]


def test_saving_the_same_day_twice_keeps_one_entry(any_stage):
    retro._save_history([_entry("2026-01-02", issues={"a": True})])
    retro._save_history([_entry("2026-01-02", issues={"b": True})])
    history = retro._load_history()
    assert len(history) == 1 and history[0]["issues"] == {"b": True}


def test_the_history_window_is_enforced(any_stage, monkeypatch):
    """_save_history keeps the last RETROSPECTIVE_HISTORY_DAYS entries; the
    db branch must drop the rest too, not just upsert."""
    monkeypatch.setattr(config, "RETROSPECTIVE_HISTORY_DAYS", 2)
    retro._save_history([_entry(f"2026-01-0{d}") for d in (2, 5, 6)])
    assert [e["date"] for e in retro._load_history()] == ["2026-01-05", "2026-01-06"]


def test_a_config_snapshot_round_trips(any_stage):
    retro._save_history([_entry("2026-01-02")])
    assert retro._load_history()[0]["config_snapshot"]["MIN_ALERT_CONFIDENCE_LEVEL"] == 3


def test_find_day_entry_still_works(any_stage):
    import datetime as dt
    retro._save_history([_entry("2026-01-02"), _entry("2026-01-03")])
    found = retro._find_day_entry(retro._load_history(), dt.date(2026, 1, 3))
    assert found is not None and found["date"] == "2026-01-03"


def test_the_consecutive_streak_counter_still_works(any_stage):
    import datetime as dt
    # 2026-01-02 is a Friday, 05/06 Mon/Tue: the counter skips the weekend.
    retro._save_history([_entry(f"2026-01-{d:02d}") for d in (2, 5, 6)])
    streak = retro._consecutive_bad_streak(retro._load_history(),
                                           dt.date(2026, 1, 6), "low_win_rate")
    assert streak == 2


def test_no_history_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "retrospective:db":
        pytest.skip("file absence is only asserted at the db stage")
    retro._save_history([_entry("2026-01-02")])
    assert not os.path.exists(os.path.join(tmp_path, "retrospective_history.json"))
```

`_find_day_entry(history, day: dt.date)` and
`_consecutive_bad_streak(history, today: dt.date, issue_key: str)` — signatures
confirmed at `retrospective.py:94` and `:102` on 2026-09-30 (the tests above
match them). They are included because they are the two consumers whose
behaviour a shape change would break silently.

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

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import retrospective_history


class RetrospectiveRepository(Repository):
    def __init__(self):
        super().__init__(retrospective_history, key="date")

    def history(self, *, conn=None) -> list[dict]:
        """Chronological, which is how the ladder walks it."""
        return self.list_all(conn=conn,
                             order_by=retrospective_history.c.date.asc())

    def put_day(self, entry: dict, *, conn=None) -> dict:
        return self.upsert(entry, conn=conn)

    def keep_only(self, dates: set[str], *, conn=None) -> int:
        """Delete every day _save_history's window trimmed away."""
        stmt = sa.delete(retrospective_history).where(
            retrospective_history.c.date.notin_(sorted(dates)))
        with self._tx(conn) as c:
            return c.execute(stmt).rowcount


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
    max_days = int(getattr(app_config, "RETROSPECTIVE_HISTORY_DAYS", 60) or 60)
    history = sorted(history, key=lambda h: h.get("date", ""))[-max_days:]
    if stages.writes_json("retrospective"):
        # ... existing file body (open/json.dump/log.exception), unchanged ...
        pass
    if stages.writes_db("retrospective"):
        try:
            from swingbot.core.db.engine import transaction
            from swingbot.core.db.repositories.retrospective import retrospective_repo
            repo = retrospective_repo()
            # Upsert per day rather than replace-all: a save no longer rewrites
            # days that did not change, which is the same lost-update fix every
            # other store in this plan gets. One transaction, so the window
            # trim and the upserts land together.
            with transaction() as conn:
                for entry in history:
                    repo.put_day(entry, conn=conn)
                repo.keep_only({h["date"] for h in history if h.get("date")},
                               conn=conn)
        except Exception:
            log.exception("retrospective: failed to save history to the database")
```

The trim moves above the stage branch so both sides keep the same window.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/tracking/test_retrospective_history_db.py
python scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py
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

> **2026-09-30 re-examination: UPDATED — `built_at` handling was wrong.**
> - Lines: `DEFAULT_PATH` `:20`, `build_snapshot` `:25`, `save_snapshot` `:79`,
>   `load_snapshot` `:83`, `refresh_snapshot` `:103`.
> - **`built_at` is already inside the snapshot** — `build_snapshot` stamps it
>   (`:67`), the file-side `load_snapshot` reads `snap["built_at"]` and returns
>   `None` without it, `commands/stats.py:228` reads `snap["built_at"]`, and the
>   SPA model (`frontend/src/app/api/models.ts:362`) types it. The repository
>   below originally overwrote it with "now" on save and **stripped it on
>   load** — a `KeyError` in `!stats` at the db stage. Corrected: `save` keeps
>   the snapshot's own `built_at` (falls back to now only if absent), and
>   `load` returns it, re-stringified with `.isoformat()` (promoted
>   `TIMESTAMP` → `datetime`, status-block finding 4).
> - The tests saved `SNAP` without a `built_at`, so every json-stage
>   parametrisation would have loaded `None`. `SNAP` now carries one.
> - The snapshot has grown since 2026-08-29: top-level keys are `built_at`,
>   `overall`, `equity_curve`, `drawdown`, `rolling_wr`, `by` (incl. v93's
>   `by["ledger"]`), `weak` (v93 main/weak ledger), `calibration`,
>   `r_multiples` — all in `doc`, no schema change. `overall.profit_factor`
>   can be `inf` and `sharpe`/`sortino` `NaN`; the codec stores those as `null`
>   (v91), so the cross-backend identity test compares after
>   `codec.sanitise_non_finite` on the file side.
> - Readers: `admin/api_v1/analytics.py:38-43`, `admin/api_v1/dashboard.py:52`,
>   `admin/queries.py:210`, `commands/growth.py:22`, `commands/stats.py:208`,
>   `scripts/reports/export_analytics.py:69` — all through `load_snapshot`, so
>   no edit. The writer is `refresh_snapshot` (`loops.py:116-119`).
> - Watcher: `analytics_snapshot.json` is one of P3-20's residual watched files;
>   once this store is at `db`, the `analytics_snapshot` trigger raises the
>   event instead — P5-12 removes the path from the residual set.

**Files:**
- Create: `swingbot/core/db/repositories/snapshots.py`
- Modify: `swingbot/core/analytics/snapshots.py` (`save_snapshot` `:79`,
  `load_snapshot` `:83`)
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


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# build_snapshot always stamps built_at, and the file-side load_snapshot
# returns None without one -- so the fixture carries it too.
SNAP = {"built_at": _now(),
        "overall": {"n": 12, "win_rate": 58.3, "expectancy_r": 0.42},
        "by_strategy": {"RSI": {"n": 7}}}


def test_an_empty_store_loads_as_none(any_stage):
    assert snapshots.load_snapshot() is None


def test_save_then_load(any_stage):
    snapshots.save_snapshot(dict(SNAP))
    loaded = snapshots.load_snapshot()
    assert loaded["overall"]["expectancy_r"] == 0.42


def test_built_at_survives_as_a_string(any_stage):
    """commands/stats.py:228 reads snap["built_at"]; stripping it or handing
    back a datetime breaks !stats at the db stage."""
    snapshots.save_snapshot(dict(SNAP))
    assert isinstance(snapshots.load_snapshot()["built_at"], str)


def test_saving_twice_keeps_one_snapshot(any_stage):
    snapshots.save_snapshot({"built_at": _now(), "overall": {"n": 1}})
    snapshots.save_snapshot({"built_at": _now(), "overall": {"n": 2}})
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
    from_db = snapshots.load_snapshot()
    # built_at: same instant, but a TIMESTAMP round trip may re-render the
    # offset; compare it as a datetime and everything else exactly.
    assert (dt.datetime.fromisoformat(from_db.pop("built_at"))
            == dt.datetime.fromisoformat(from_file.pop("built_at")))
    assert from_db == from_file


def test_non_finite_metrics_become_null_not_an_error(any_stage):
    """profit_factor is inf with no losses; sharpe is NaN on one trade. v91's
    codec narrows both to None; the file keeps them. Neither side may raise."""
    snapshots.save_snapshot({"built_at": _now(),
                             "overall": {"profit_factor": float("inf"),
                                         "sharpe": float("nan")}})
    assert snapshots.load_snapshot() is not None


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
        # build_snapshot already stamped built_at; keep it. "now" is only the
        # fallback for a hand-built dict, never an override.
        return self.upsert({
            **snapshot,
            "key": CURRENT,
            "built_at": snapshot.get("built_at")
                        or dt.datetime.now(dt.timezone.utc).isoformat(),
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
        snap = {k: v for k, v in rows[0].items() if k != "key"}
        # built_at stays: commands/stats.py and the SPA read it. It comes back
        # from its TIMESTAMP column as a datetime; the file shape is a string.
        if hasattr(snap.get("built_at"), "isoformat"):
            snap["built_at"] = snap["built_at"].isoformat()
        return snap


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

> **2026-09-30 re-examination: UPDATED (lines valid; test names and entry
> shape corrected; one uncovered neighbour recorded).**
> - `_SNAPSHOT_PATH` `:9`, `_load_scan_snapshots` `:10`, `_save_scan_snapshots`
>   `:20` match `main`. The only caller is `_snapshot_and_diff` (`:47`), which
>   loads the whole dict, replaces **one** key and saves the whole dict — so the
>   db branch as written upserts every key on every alert. That is O(keys) per
>   alert and harmless at today's size; if it shows up in scan timing
>   (`phases_s["building alerts"]`), give `_snapshot_and_diff` a
>   `_put_scan_snapshot(key, entry)` that upserts only the changed key.
> - Real entry shape (`:66-68`): `{"entry", "stop_loss", "take_profit",
>   "confidence_level", "risk_reward_ratio", "ts"}` — the test's `ENTRY` is
>   corrected to it.
> - Existing tests: `tests/scanning/test_snapshots.py` does not exist; the
>   store is exercised by `tests/scanning/test_embeds_v3.py` and
>   `tests/test_stats_commands.py`. Step 4 corrected.
> - Watcher: `scan_snapshots.json` is a P3-20 residual watched path (`scan`);
>   P5-12 removes it from the residual set once this table is mapped.
> - **Uncovered neighbour, deliberately left a file: `data/scan_progress.json`**
>   (`core/scanning/progress_store.py`, 2026-09-16). It is a transient
>   progress record republished ~once a second during a scan and deleted by
>   `clear()` when the scan ends — no history, nothing to import, nothing to
>   query. A table would turn a 1 Hz file replace into a 1 Hz `UPDATE` +
>   `NOTIFY`, for no reader that needs it. It stays under P3-20's residual
>   `FileWatcher`; Part 6's watcher removal is where its fate is decided
>   (P3-20 records giving it a table as the partner's call).

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


# The shape _snapshot_and_diff writes (snapshots.py:66-68).
ENTRY = {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "confidence_level": 4, "risk_reward_ratio": 2.0,
         "ts": "2026-01-02T15:00:00+00:00"}


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
python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
python scripts/dev/testrun.py file tests/test_stats_commands.py
```

Expected: `0 failed` for all three.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/snapshots.py tests/scanning/test_scan_snapshots_db.py
git commit -m "feat(v67): move scan presentation snapshots to postgres"
```

---


### Task P5-08: The ticker metadata cache

`data.py:311-363` holds two dicts (`currency_symbols`, `company_names`) in one
file, rewritten whole on every new lookup, and **loaded at import time**
(`data.py:363`). It is regenerable from Yahoo, so reads may fall back — this is
the second of the spec's two named read-fallback stores.

> **2026-09-30 re-examination: UPDATED — lines moved, a negative-cache bug in
> the draft, and one uncovered store folded in.**
> - Lines on `main`: `_currency_cache` `:311`, `_company_name_cache` `:316`,
>   `_TICKER_META_CACHE_PATH = None` `:331` (now **lazy** — resolved by
>   `_ticker_meta_cache_path()` `:334`), `_load_ticker_meta_cache` `:342`,
>   `_save_ticker_meta_cache` `:351`, **import-time call `:363`** (still
>   there — the hazard below is real), writers `get_company_name` `:400-401`
>   and `get_currency_symbol` `:438-439`. The load now uses `read_json` and the
>   save `atomic_write_json`, both swallowing into a debug log. Monkeypatching
>   `mkt._TICKER_META_CACHE_PATH` in the tests still works (the lazy getter
>   only fills it when `None`).
> - **Negative cache.** `get_company_name` stores `None` for a symbol no source
>   could name (`_company_name_cache[ticker_key] = name` with `name=None`), and
>   the membership test `if ticker_key in _company_name_cache` is what stops a
>   yfinance call per unresolvable symbol per restart. The draft `put()` skipped
>   `None` and `load_all()` dropped it — that would re-open exactly the slow
>   Watchlist page the file was created to fix. Corrected: `put()` takes
>   explicit field presence and stores `name: null`; `load_all()` restores any
>   `name` key that is *present*, `None` included.
> - `_save_ticker_meta_cache()` takes no arguments and writes both dicts whole.
>   The db branch should write only the symbol that changed: give it an
>   optional `symbol` argument, passed by the two call sites, and fall back to
>   upserting every symbol when it is omitted.
> - Existing tests: `tests/marketdata/test_data.py` exists. No existing test
>   references `ticker_meta_cache` directly.
> - **Folded-in uncovered store: `data/earnings_history.json`**
>   (`core/market/earnings_history.py`, 2026-09-14, written weekly by
>   `weekly_earnings_refresh` via `commands/scanning/loops.py:708`). It is a
>   per-symbol cache of the same kind as this one —
>   `{"updated_at": iso, "symbols": {SYM: {"next": iso|None, "past": [iso]}}}`
>   — but, unlike this one, **not regenerable**: `past` accumulates dates the
>   provider later stops returning. It has **no reader in the codebase yet**
>   (write-only ledger) — that is a measured state, not a stub; do not invent a
>   reader here. Scope added to this task (Step 4b below): an
>   `EarningsHistoryRepository` over P5-01's `earnings_history` table (one row
>   per symbol — the top-level `updated_at` is a codec `RESERVED_KEY`, so the
>   blob shape cannot be stored as-is; it becomes the row's own `updated_at`),
>   and a stage branch in `refresh_watchlist_earnings` (store name
>   `earnings`) around its `read_json(_path(), {})` / `atomic_write_json`
>   pair. Its importer is added to P5-11 because the history is not
>   reproducible.

**Files:**
- Create: `swingbot/core/db/repositories/meta_cache.py`
- Create: `swingbot/core/db/repositories/earnings_history.py` *(2026-09-30)*
- Modify: `swingbot/core/marketdata/data.py` (`_load_ticker_meta_cache` `:342`,
  `_save_ticker_meta_cache` `:351`, and the import-time call at `:363`)
- Modify: `swingbot/core/market/earnings_history.py` (`refresh_watchlist_earnings` `:27`) *(2026-09-30)*
- Test: `tests/marketdata/test_ticker_meta_cache_db.py`
- Test: `tests/market/test_earnings_history_db.py` *(2026-09-30)*

**Interfaces:**
- Consumes: `ticker_meta_cache`, `earnings_history` (P5-01), `stages`.
- Produces: `MetaCacheRepository` with `load_all() -> tuple[dict, dict]`,
  `put(symbol, **fields)`; `meta_cache_repo()`.
  `EarningsHistoryRepository` with `load() -> dict` (the file's
  `{"updated_at", "symbols"}` shape) and `put_many(entries: dict)`;
  `earnings_history_repo()`.

**The import-time call is the hazard here**, and it is a real one: `data.py`
calls `_load_ticker_meta_cache()` at module scope, so at the db stage importing
`data.py` would open a database connection during import — in every process,
including `scripts/` that never touch a ticker. The fix is to make the load
**lazy**, triggered by the first lookup rather than by the import.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_ticker_meta_cache_db.py`:

```python
"""The metadata cache, and the import-time load that must become lazy."""
import os

import pytest

from swingbot import config
from swingbot.core.marketdata import data as mkt


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "meta_cache:db")
    monkeypatch.setattr(mkt, "_TICKER_META_CACHE_PATH",
                        os.path.join(tmp_path, "ticker_meta_cache.json"))
    monkeypatch.setattr(mkt, "_currency_cache", {})
    monkeypatch.setattr(mkt, "_company_name_cache", {})
    monkeypatch.setattr(mkt, "_meta_cache_loaded", False)


def test_save_then_load(db_stage):
    mkt._currency_cache["AAPL"] = "$"
    mkt._company_name_cache["AAPL"] = "Apple Inc."
    mkt._save_ticker_meta_cache()

    mkt._currency_cache.clear()
    mkt._company_name_cache.clear()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()

    assert mkt._currency_cache["AAPL"] == "$"
    assert mkt._company_name_cache["AAPL"] == "Apple Inc."


def test_a_symbol_with_only_one_half_round_trips(db_stage):
    mkt._currency_cache["MSFT"] = "$"
    mkt._save_ticker_meta_cache()
    mkt._currency_cache.clear()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()
    assert mkt._currency_cache["MSFT"] == "$"
    assert "MSFT" not in mkt._company_name_cache


def test_an_unresolvable_name_stays_negatively_cached(db_stage):
    """get_company_name stores None for a symbol nothing could name, and the
    `in` check is what stops a yfinance call per restart. Dropping the None
    would bring back the slow Watchlist page this file exists to prevent."""
    mkt._company_name_cache["ZZZZ"] = None
    mkt._save_ticker_meta_cache()
    mkt._company_name_cache.clear()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()
    assert "ZZZZ" in mkt._company_name_cache
    assert mkt._company_name_cache["ZZZZ"] is None


def test_saving_twice_keeps_one_row_per_symbol(db_stage):
    from swingbot.core.db.repositories.meta_cache import MetaCacheRepository
    mkt._currency_cache["AAPL"] = "$"
    mkt._save_ticker_meta_cache()
    mkt._company_name_cache["AAPL"] = "Apple Inc."
    mkt._save_ticker_meta_cache()
    assert MetaCacheRepository().count() == 1


def test_an_unreachable_database_degrades_to_an_empty_cache(db_stage,
                                                             monkeypatch):
    """Regenerable from Yahoo: an empty cache costs a network call, not
    correctness."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()            # must not raise
    assert mkt._currency_cache == {}
    dbengine.reset_engine()


def test_importing_data_py_opens_no_connection(monkeypatch):
    """The import-time load must be lazy. Every script that imports data.py
    would otherwise connect to Postgres just to be imported."""
    import importlib
    import sys

    monkeypatch.setattr(config, "DB_STORES", "meta_cache:db")
    opened = []
    from swingbot.core.db import engine as dbengine
    monkeypatch.setattr(dbengine, "get_engine",
                        lambda: opened.append(1) or (_ for _ in ()).throw(
                            AssertionError("connected during import")))
    sys.modules.pop("swingbot.core.marketdata.data", None)
    importlib.import_module("swingbot.core.marketdata.data")
    assert opened == []


def test_no_meta_cache_json_at_the_db_stage(db_stage, tmp_path):
    mkt._currency_cache["AAPL"] = "$"
    mkt._save_ticker_meta_cache()
    assert not os.path.exists(os.path.join(tmp_path, "ticker_meta_cache.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/marketdata/test_ticker_meta_cache_db.py -q
```

Expected: `ModuleNotFoundError`, and — after the module exists —
`test_importing_data_py_opens_no_connection` failing on the import-time call.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/meta_cache.py`:

```python
"""Ticker currency symbols and company names.

One row per symbol, not two dicts in one blob: the file was rewritten whole on
every new lookup, and lookups happen one ticker at a time.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ticker_meta_cache


class MetaCacheRepository(Repository):
    def __init__(self):
        super().__init__(ticker_meta_cache, key="symbol")

    def load_all(self, *, conn=None) -> tuple[dict, dict]:
        """(currency_symbols, company_names), each keyed by symbol.

        Presence, not truthiness: a `name` stored as null is the negative cache
        ("nothing could name this symbol") and must come back as None, or every
        restart re-pays a yfinance call for it. `name`/`currency` live in `doc`
        (not promoted), where merge_doc keeps an explicit null.
        """
        currencies, names = {}, {}
        for row in self.list_all(conn=conn):
            symbol = row["symbol"]
            if "currency" in row:
                currencies[symbol] = row["currency"]
            if "name" in row:
                names[symbol] = row["name"]
        return currencies, names

    def put(self, symbol: str, *, conn=None, **fields) -> None:
        """Patch, not upsert: the two halves are learned at different times,
        and a currency lookup must not erase a name already cached. Pass only
        the fields you know -- `name=None` is a real value (negative cache)."""
        changes = {k: v for k, v in fields.items() if k in ("currency", "name")}
        if not changes:
            return
        if self.get(symbol, conn=conn) is None:
            self.insert({"symbol": symbol, **changes}, conn=conn)
        else:
            self.patch(symbol, changes, conn=conn)


_repo: MetaCacheRepository | None = None


def meta_cache_repo() -> MetaCacheRepository:
    global _repo
    if _repo is None:
        _repo = MetaCacheRepository()
    return _repo
```

- [ ] **Step 4: Make the load lazy and branch both functions**

In `swingbot/core/marketdata/data.py`, replace the import-time call at `:363`:

```python
_meta_cache_loaded = False


def _ensure_meta_cache_loaded() -> None:
    """Load the metadata cache on first use, not at import.

    This used to be a bare `_load_ticker_meta_cache()` at module scope. At the
    db stage that would open a Postgres connection just to IMPORT this module
    -- in every process, including the scripts that never look up a ticker.
    """
    global _meta_cache_loaded
    if _meta_cache_loaded:
        return
    _meta_cache_loaded = True
    _load_ticker_meta_cache()
```

Call `_ensure_meta_cache_loaded()` at the top of `get_company_name` and
`get_currency_symbol` (and any other reader of the two dicts — find them with
`grep -n "_currency_cache\|_company_name_cache" swingbot/core/marketdata/data.py`).

`_load_ticker_meta_cache` gains a `reads_db("meta_cache")` branch calling
`meta_cache_repo().load_all()` inside the existing `try/except Exception` —
which already degrades to an empty cache and logs at debug, exactly the
behaviour the fallback needs. *(2026-09-30: on `main` the load is a bare
`read_json` with no `try`; wrap the db branch in `try/except Exception:
log.debug(..., exc_info=True)` yourself.)* `_save_ticker_meta_cache(symbol=None)`
writes per stage, using `put()` on the db side — for `symbol` only when given
(the two call sites pass it), for every symbol when not. Build the `put`
kwargs from dict membership (`if sym in _company_name_cache:
fields["name"] = _company_name_cache[sym]`) so a `None` name is written.

- [ ] **Step 4b (2026-09-30): the earnings ledger**

Create `tests/market/test_earnings_history_db.py` first:

```python
"""The weekly earnings ledger. Not regenerable: `past` accumulates."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import earnings_history as eh


@pytest.fixture(params=["", "earnings:dual", "earnings:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


NOW = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)


def _dates(*isos):
    return [dt.datetime.fromisoformat(s) for s in isos]


def test_past_dates_accumulate_across_refreshes(any_stage, monkeypatch):
    monkeypatch.setattr(eh, "get_earnings_datetimes",
                        lambda s, refresh=True: _dates("2026-07-30T20:00:00+00:00",
                                                       "2026-10-29T20:00:00+00:00"))
    eh.refresh_watchlist_earnings(["AAPL"], now=NOW)
    # The provider forgets July; the ledger must not.
    monkeypatch.setattr(eh, "get_earnings_datetimes",
                        lambda s, refresh=True: _dates("2026-10-29T20:00:00+00:00"))
    snap = eh.refresh_watchlist_earnings(["AAPL"], now=NOW)
    assert "2026-07-30T20:00:00+00:00" in snap["symbols"]["AAPL"]["past"]


def test_a_failed_lookup_keeps_the_previous_entry(any_stage, monkeypatch):
    monkeypatch.setattr(eh, "get_earnings_datetimes",
                        lambda s, refresh=True: _dates("2026-10-29T20:00:00+00:00"))
    eh.refresh_watchlist_earnings(["AAPL"], now=NOW)
    monkeypatch.setattr(eh, "get_earnings_datetimes", lambda s, refresh=True: [])
    snap = eh.refresh_watchlist_earnings(["AAPL"], now=NOW)
    assert snap["symbols"]["AAPL"]["next"] == "2026-10-29T20:00:00+00:00"
```

Then `swingbot/core/db/repositories/earnings_history.py`:

```python
"""Weekly earnings ledger, one row per symbol.

The file is {"updated_at", "symbols": {SYM: {"next", "past"}}}. `updated_at`
is a codec RESERVED_KEY, so the blob cannot be one row; per-symbol rows carry
it as their own infrastructure column instead, and load() rebuilds the shape.
"""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import earnings_history


class EarningsHistoryRepository(Repository):
    def __init__(self):
        super().__init__(earnings_history, key="symbol")

    def load(self, *, conn=None) -> dict:
        with self._tx(conn) as c:
            rows = c.execute(sa.select(earnings_history)).all()
        if not rows:
            return {}
        newest = max(r._mapping["updated_at"] for r in rows)
        return {"updated_at": newest.isoformat(),
                "symbols": {r._mapping["symbol"]: self._record(r) for r in rows}}

    def put_many(self, entries: dict, *, conn=None) -> None:
        with transaction(conn) as c:
            for symbol, entry in entries.items():
                self.upsert({"symbol": symbol, **entry}, conn=c)


_repo: EarningsHistoryRepository | None = None


def earnings_history_repo() -> EarningsHistoryRepository:
    global _repo
    if _repo is None:
        _repo = EarningsHistoryRepository()
    return _repo
```

In `refresh_watchlist_earnings`, read `previous` from the repository when
`stages.reads_db("earnings")`, else `read_json(_path(), {})`; write the file when
`stages.writes_json("earnings")` and `earnings_history_repo().put_many(next_entries)`
when `stages.writes_db("earnings")`. The returned `snapshot` is unchanged. No
reader exists, so nothing else changes — and none is to be added here.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/marketdata/test_ticker_meta_cache_db.py
python scripts/dev/testrun.py file tests/market/test_earnings_history_db.py
python scripts/dev/testrun.py file tests/marketdata/test_data.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because making the load lazy changes
`data.py`'s import behaviour, and `data.py` is imported nearly everywhere.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/meta_cache.py \
        swingbot/core/db/repositories/earnings_history.py \
        swingbot/core/marketdata/data.py swingbot/core/market/earnings_history.py \
        tests/marketdata/test_ticker_meta_cache_db.py \
        tests/market/test_earnings_history_db.py
git commit -m "feat(v67): move the ticker metadata cache and earnings ledger to postgres"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_5c-caches.md`** (P5-09…P5-14):
the RS cache, fold trades, importers, parity registration,
retention, and Part 5's verification.
