# v204 Admin snapshot pages, part 3: snapshot worker, request door and the Risk route

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Index:** [`_0-index.md`](2026-10-29-v204-admin-snapshot-pages_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract (Snapshot job, Request-path door additions, Endpoints, Risk body additions) live there and bind every task below.

Part scope: V204-9 … V204-12. The snapshot worker thread inside the refresher (budget, abandon, compare-and-set landing), its scheduling step and the no-notification guard, the request door that reads snapshot rows and never builds, the `snapshots` fields on `/market/updates` and `/market/refresh`, and the Risk route reading its snapshot with the kill-switch fallback kept.

`<wt>` is the implementation worktree's absolute path. v201 must be merged (index, Global Constraints). Tasks in this part consume part 1 (`admin_refresh` snapshot helpers, `admin_snapshot_repo`) and part 2 (`admin_snapshots.builders`, `SnapshotResult`, `build_inputs`, `stale_inputs_for`, `risk_payload.*`). DB-backed tests need the shared `swing-db` replica (`/replicate-prod-db`) before their first run; every test in this part uses fakes, so none needs it.

# Phase 3: The snapshot worker

### Task V204-9: Snapshot worker thread: budget, abandon, compare-and-set landing, marks, landed event

**Model:** opus — concurrency inside a long-running production process; a wrong abandon rule either stalls snapshots forever or lets a late build overwrite a newer one.

**Files:**
- Create: `swingbot/refresher/snapshot_job.py`
- Test: `tests/admin_snapshots/test_snapshot_worker.py`

**Interfaces:**
- Consumes: V204-3 `admin_refresh.snapshot_mark_key(key)`, `admin_refresh.snapshot_mark_timeout_s()`, config `ADMIN_SNAPSHOT_BUDGET_S`; V204-4 `admin_snapshot_repo().put(key, doc, inputs, *, computed_at, stale_inputs) -> bool` (compare-and-set: an equal or older `computed_at` writes nothing and returns `False`); V204-7/8 `admin_snapshots.SnapshotResult(doc, inputs, stale_inputs)`, `admin_snapshots.builders(now=None) -> dict[str, Callable[[], SnapshotResult]]`; v201 `refresh_mark_repo().mark(keys, *, timeout_s, now=None)` and `.clear(keys, *, error=None, now=None)`, `notify.publish("market")`, `swallowed`.
- Produces (index "Snapshot job", V204-9 rows, exact): `class SnapshotWorker` with `__init__(*, builders_fn=admin_snapshots.builders, repo_fn=admin_snapshot_repo, marks_fn=refresh_mark_repo, publish=notify.publish, budget_fn=lambda: config.ADMIN_SNAPSHOT_BUDGET_S, clock=None)`, `submit(keys: Iterable[str]) -> list[str]`, `start() -> None`, `stop(timeout: float = 5.0) -> None`, `run_batch(keys: list[str]) -> list[str]`, `drain_landed() -> list[str]`. V204-10 appends `due_keys`, `snapshot_step`, `worker()` and `_trades_fingerprint()` to the same module.

**Behaviour fixed here (the tests pin each line):**
- **Module imports.** `snapshot_job.py` imports `config`, `admin_snapshots` (`swingbot.core.analytics`), `notify` (`swingbot.core.db`), `admin_snapshot_repo` (`swingbot.core.db.repositories.admin_snapshots`), `refresh_mark_repo` (`swingbot.core.db.repositories.market_refresh`), `admin_refresh` and `swallowed`. It never imports `discord`, `swingbot.commands` or `swingbot.admin` (V204-10 guards this). `CycleContext` is imported only under `TYPE_CHECKING`, because V204-10's `loop.py` imports this module.
- **State, all guarded by one `threading.Lock`:** `_pending: list[str]` (ordered, unique), `_active: set[str]` (keys taken for a batch and not yet finished), `_abandoned: dict[str, threading.Thread]` (overran keys whose build thread is still alive) and `_landed: list[str]`. Two `threading.Event`s: `_wake` and `_stop`. `_clock = clock or (lambda: datetime.now(timezone.utc))` supplies `now=` for every mark and clear.
- **`submit(keys)`** first drops `_abandoned` entries whose thread is no longer alive. It then accepts, in input order and once each, every key that is not in `_pending`, `_active` or `_abandoned`. It marks the accepted keys in one call, `marks.mark([snapshot_mark_key(k) ...], timeout_s=snapshot_mark_timeout_s(), now=clock())`, **before** it sets `_wake`. A key is therefore never marked again after its own build cleared it, so a stray spinner cannot outlive the build. This is how V204-10's step "marks the accepted ones". A mark error is swallowed (`"refresher.snapshot.mark"`), and the keys are still accepted. `submit` returns the accepted keys and never builds.
- **`start()`** starts one daemon thread named `snapshot-worker`. The thread loops until `_stop` is set: `_wake.wait(1.0)`, `_wake.clear()`, then it moves `_pending` into a batch (and into `_active`) under the lock and calls `run_batch(batch)`. An exception that escapes `run_batch` is swallowed (`"refresher.snapshot.worker"`), so the thread never dies. A second `start()` while the thread is alive does nothing. **`stop(timeout)`** sets `_stop` and `_wake` and joins the thread for `timeout` seconds.
- **`run_batch(keys)`** is the synchronous seam. It reads `builders = builders_fn()` once, adds the keys to `_active`, and runs `_run_one(key, builders.get(key))` for each key in order, discarding each from `_active` when it is done. It extends `_landed` with the keys that landed. After the batch, if any key landed or errored, it calls `publish("market")` once, guarded (`"refresher.notify"`, never raising). It returns the landed keys.
- **`_run_one(key, builder) -> str`** returns `"landed"`, `"kept"` or `"error"`:
  - With no builder, it clears the mark with `error=f"no builder for {key}"` → `"error"`.
  - It re-marks the key (`timeout_s=snapshot_mark_timeout_s()`, no publish). It reads `budget = float(budget_fn())`. It then runs `_build_and_put(key, builder, box)` in a daemon thread named `snapshot-build-<key>` and joins it for `budget` seconds.
  - Still alive after the join: it records the thread in `_abandoned[key]`, clears the mark with `error=f"budget exceeded after {budget:g}s"` and logs a WARNING → `"error"`. The late result can only land through the compare-and-set `put`. It is not added to `_landed` and raises no event of its own; the next cycle's event carries it.
  - The build raised: it clears the mark with `error=f"{type(exc).__name__}: {exc}"`, logs through `swallowed(log, "refresher.snapshot", exc, level=logging.WARNING)` and keeps the previous row → `"error"`.
  - Otherwise it clears the mark with no error. The result is `"landed"` when `put` returned `True`, else `"kept"` (a newer row already stood).
- **`_build_and_put`** calls `res = builder()`, then `repo_fn().put(key, res.doc, res.inputs, computed_at=datetime.fromisoformat(res.inputs["computed_at"]), stale_inputs=res.stale_inputs)`. It stores `written` or the exception in `box`.
- **`drain_landed()`** returns the keys landed since the last call, in order, and empties the list.
- Mark and clear errors are swallowed (`"refresher.snapshot.mark"`) and never stop a build or a batch.

- [ ] **Step 1: Write the failing tests** in `tests/admin_snapshots/test_snapshot_worker.py`

```python
"""v204: the snapshot worker builds on its own thread, under a budget, and lands compare-and-set."""
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot.core.analytics.admin_snapshots import SnapshotResult
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable
from swingbot.core.marketdata.shared import admin_refresh as ar
from swingbot.refresher.snapshot_job import SnapshotWorker

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
KEYS = ["risk", "analytics.snapshot"]


def result(doc, at=T0, stale=False):
    return SnapshotResult(doc=doc, inputs={"computed_at": at.isoformat()}, stale_inputs=stale)


class Rows:
    """Compare-and-set like AdminSnapshotRepository.put: an equal or older computed_at writes nothing."""

    def __init__(self):
        self.rows = {}

    def put(self, key, doc, inputs, *, computed_at, stale_inputs):
        old = self.rows.get(key)
        if old is not None and old["computed_at"] >= computed_at:
            return False
        self.rows[key] = {"doc": doc, "computed_at": computed_at, "stale_inputs": stale_inputs}
        return True


class Marks:
    def __init__(self):
        self.calls = []
        self.broken = False

    def mark(self, keys, *, timeout_s, now=None):
        if self.broken:
            raise RuntimeError("db down")
        self.calls.append(("mark", tuple(keys), timeout_s))

    def clear(self, keys, *, error=None, now=None):
        self.calls.append(("clear", tuple(keys), error))


def make(budget=2.0, publish=None):
    env = SimpleNamespace(rows=Rows(), marks=Marks(), published=[], builders={})
    env.w = SnapshotWorker(builders_fn=lambda: env.builders, repo_fn=lambda: env.rows,
                           marks_fn=lambda: env.marks, publish=publish or env.published.append,
                           budget_fn=lambda: budget, clock=lambda: T0)
    return env


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_landed_keys_are_put_cleared_and_published_once():
    env = make()
    env.builders.update({"risk": lambda: result({"heat": 1}),
                         "analytics.snapshot": lambda: result({"overall": {}})})
    assert env.w.run_batch(KEYS) == KEYS
    timeout = ar.snapshot_mark_timeout_s()
    assert env.marks.calls == [("mark", ("snapshot:risk",), timeout), ("clear", ("snapshot:risk",), None),
                               ("mark", ("snapshot:analytics.snapshot",), timeout),
                               ("clear", ("snapshot:analytics.snapshot",), None)]
    assert env.rows.rows["risk"]["doc"] == {"heat": 1}
    assert env.published == ["market"]
    assert env.w.drain_landed() == KEYS and env.w.drain_landed() == []


def test_failing_build_keeps_previous_row_and_clears_mark_with_error():
    env = make()
    env.rows.put("risk", {"heat": "previous"}, {}, computed_at=T0 - timedelta(minutes=5), stale_inputs=False)

    def unmounted():
        raise DailyCacheUnavailable("daily bar cache /app/market_data is not mounted")
    env.builders["risk"] = unmounted
    assert env.w.run_batch(["risk"]) == []
    assert env.rows.rows["risk"]["doc"] == {"heat": "previous"}
    assert ("clear", ("snapshot:risk",),
            "DailyCacheUnavailable: daily bar cache /app/market_data is not mounted") in env.marks.calls
    assert env.published == ["market"]                 # an error is news for the spinner too


def test_overrun_is_abandoned_and_late_result_cannot_overwrite():
    env = make(budget=0.05)
    release = threading.Event()

    def slow():
        release.wait(5.0)
        return result({"v": "late"}, at=T0)
    env.builders["risk"] = slow
    assert env.w.run_batch(["risk"]) == []
    assert ("clear", ("snapshot:risk",), "budget exceeded after 0.05s") in env.marks.calls
    assert env.w.submit(["risk"]) == []                # its build thread is still alive
    env.rows.put("risk", {"v": "newer"}, {}, computed_at=T0 + timedelta(minutes=1), stale_inputs=False)
    release.set()
    assert wait_until(lambda: not any(t.name == "snapshot-build-risk" for t in threading.enumerate()))
    assert env.rows.rows["risk"]["doc"] == {"v": "newer"}
    assert env.w.submit(["risk"]) == ["risk"]          # thread gone: the key is accepted again


def test_submit_dedupes_marks_accepted_keys_and_never_builds():
    env = make()
    env.builders["risk"] = lambda: pytest.fail("submit built inline")
    assert env.w.submit(["risk", "risk", "analytics.snapshot"]) == KEYS
    assert env.marks.calls == [("mark", ("snapshot:risk", "snapshot:analytics.snapshot"),
                                ar.snapshot_mark_timeout_s())]
    assert env.w.submit(["risk"]) == []                # already pending
    assert env.rows.rows == {}


def test_unknown_key_is_cleared_with_an_error():
    env = make()
    assert env.w.run_batch(["calendar.pnl:2020-01"]) == []
    assert env.marks.calls == [("clear", ("snapshot:calendar.pnl:2020-01",),
                                "no builder for calendar.pnl:2020-01")]


def test_older_result_is_kept_out_and_raises_no_event():
    env = make()
    env.rows.put("risk", {"v": "newer"}, {}, computed_at=T0 + timedelta(minutes=1), stale_inputs=False)
    env.builders["risk"] = lambda: result({"v": "older"}, at=T0)
    assert env.w.run_batch(["risk"]) == []
    assert env.rows.rows["risk"]["doc"] == {"v": "newer"}
    assert env.marks.calls[-1] == ("clear", ("snapshot:risk",), None) and env.published == []


def test_publish_failure_never_raises():
    def broken(channel):
        raise RuntimeError("notify down")
    env = make(publish=broken)
    env.builders["risk"] = lambda: result({"heat": 1})
    assert env.w.run_batch(["risk"]) == ["risk"]


def test_mark_failure_never_stops_the_build():
    env = make()
    env.marks.broken = True
    env.builders["risk"] = lambda: result({"heat": 1})
    assert env.w.submit(["risk"]) == ["risk"]
    assert env.w.run_batch(["risk"]) == ["risk"]


def test_started_worker_builds_submitted_keys_off_the_caller_thread():
    env = make()
    seen = []

    def build():
        seen.append(threading.current_thread().name)
        time.sleep(0.2)
        return result({"heat": 1})
    env.builders["risk"] = build
    env.w.start()
    env.w.start()                                       # a second start is a no-op
    landed = []
    try:
        began = time.monotonic()
        assert env.w.submit(["risk"]) == ["risk"]
        assert time.monotonic() - began < 0.1           # submit never waits for a build
        assert wait_until(lambda: landed.extend(env.w.drain_landed()) or landed == ["risk"])
    finally:
        env.w.stop()
    assert seen == ["snapshot-build-risk"]
    assert not any(t.name == "snapshot-worker" and t.is_alive() for t in threading.enumerate())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_worker.py`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'swingbot.refresher.snapshot_job'`.

- [ ] **Step 3: Implement `SnapshotWorker` in `swingbot/refresher/snapshot_job.py`**

Module docstring: v204. The refresher's snapshot worker runs every build on its own thread under `ADMIN_SNAPSHOT_BUDGET_S`, never inline in the quote cycle. Rows land compare-and-set, so an abandoned build that finishes late cannot overwrite a newer row. The worker feeds the admin SPA only and sends nothing to Discord.

Build it per "Behaviour fixed here". The private helpers are `_describe(exc) -> str`, `_mark(keys)`, `_clear(key, error=None)`, `_announce()`, `_take() -> list[str]`, `_run_one(key, builder) -> str`, `_build_and_put(key, builder, box)` and `_loop()`. Each stays well under complexity 15. `_take` and `submit` hold the lock only for list and set operations, never across a mark, a build or a publish (`submit` collects the accepted keys under the lock, releases it, marks, then sets `_wake`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_worker.py`
Expected: PASS, `0 failed`. Run it twice more to check that the threaded tests are not flaky.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/refresher/snapshot_job.py tests/admin_snapshots/test_snapshot_worker.py
git -C <wt> commit -m "feat(v204): snapshot worker thread with build budget and compare-and-set landing"
```

### Task V204-10: Scheduling: due keys, cadence, trade/scan triggers, queue keys, month prune; loop step; no-notification guard

**Model:** opus — the trigger and retry rules decide whether a closed trade shows on Risk within one cycle or waits out a five-minute cadence, and the guard pins the spec's "no extra notification volume" non-goal.

**Files:**
- Modify: `swingbot/refresher/snapshot_job.py` (append the scheduling half)
- Modify (created by v201 V201-5): `swingbot/refresher/loop.py` (`STEPS` gains `snapshot_job.snapshot_step`)
- Modify (created by v201 V201-5): `swingbot/refresher/__main__.py` (start the worker before `run_forever`, stop it after)
- Test: `tests/admin_snapshots/test_snapshot_schedule.py`, `tests/admin_snapshots/test_no_notification_guard.py`

**Interfaces:**
- Consumes: V204-9 `SnapshotWorker.submit/drain_landed/start/stop`; V204-3 `admin_refresh.snapshot_cadence_s(state)`, `calendar_months(now)`, `calendar_key(month)`, `refresher_on()`; V204-4 `admin_snapshot_repo().prune(prefix, keep) -> int`; V204-8 `admin_snapshots.builders(now) -> dict`; v201 `loop.CycleContext(now, session, symbols, queued_quotes, queued_snapshots, scan_running, report)`, `loop.CycleReport(session, cadence_s, ..., snapshots_written: tuple, error, changed)`, `loop.STEPS` (`[quotes.quote_step, quotes.fx_step]`), `symbols.SymbolSet`, `__main__.main() -> int`, `engine.get_engine()`.
- Produces (index "Snapshot job", V204-10 rows, exact): `due_keys(now: datetime, last_runs: Mapping[str, datetime], *, session: str, builder_keys: Sequence[str], trades_changed: bool, scan_completed: bool, queued: Iterable[str]) -> list[str]`; `snapshot_step(ctx: CycleContext) -> None`, the third entry of `loop.STEPS`; `worker() -> SnapshotWorker` (process singleton); `_trades_fingerprint() -> tuple | None`.

**Behaviour fixed here (the tests pin each line):**
- **`due_keys`**: with `cadence = snapshot_cadence_s(session)` and `force = trades_changed or scan_completed`, a key from `builder_keys` (in that order) is due when `force` is true, when it is absent from `last_runs`, or when `(now - last_runs[k]).total_seconds() >= cadence`. Each queued key that is in `builder_keys` and not already due is then appended, in queue order and once. A queued key without a builder is dropped.
- **`snapshot_step(ctx)`** keeps module state `_last_runs: dict[str, datetime]`, `_trades_fp: tuple | None`, `_was_scanning: bool` and `_pruned_for: tuple[str, str] | None`. In order:
  1. If `not admin_refresh.refresher_on()`, it returns at once. The kill-switch path computes on request, so nothing reads these rows.
  2. `trades_changed, scan_completed = _triggers(ctx)`. `trades_changed` is true when `_trades_fingerprint()` is not `None`, a previous non-`None` value exists, and the two differ. `scan_completed` is `_was_scanning and not ctx.scan_running`. Both states are then updated (a `None` fingerprint leaves `_trades_fp` as it was).
  3. `due = due_keys(ctx.now, _last_runs, session=ctx.session, builder_keys=list(admin_snapshots.builders(ctx.now)), trades_changed=..., scan_completed=..., queued=ctx.queued_snapshots)`.
  4. When `due` is not empty: `accepted = worker().submit(due)`. `submit` marks the accepted keys before the worker can start them (V204-9), so the step itself writes no mark. For each due key, `_last_runs[k] = ctx.now` when it was accepted. Otherwise `_last_runs.pop(k, None)`, so a key that was busy is due again next cycle and a trade-change trigger is never lost. When `accepted` is not empty, it sets `ctx.report.changed = True`, so v201's end-of-cycle publish carries the snapshot marks.
  5. `ctx.report.snapshots_written = tuple(worker().drain_landed())`.
  6. `_prune_months(ctx.now)`: when `calendar_months(ctx.now)` differs from `_pruned_for`, it calls `admin_snapshot_repo().prune("calendar.pnl:", [calendar_key(m) for m in months])` and then stores the months. An error is swallowed (`"refresher.snapshot.prune"`) and retried next cycle.

  The step never calls a builder and never publishes. A cycle's events therefore stay at three: v201's quote marks, v201's end-of-cycle publish, and the worker's one publish per landed batch.
- **`_trades_fingerprint()`** runs `SELECT count(*), max(updated_at) FROM trades` on `engine.get_engine()` and returns `(count, max_updated_at)`. Any error returns `None` (swallowed at DEBUG, `"refresher.snapshot.trades_fp"`).
- **`worker()`** returns the module's one `SnapshotWorker()`, created on first call under a lock.
- **`loop.py`**: `from swingbot.refresher import quotes, snapshot_job` and `STEPS = [quotes.quote_step, quotes.fx_step, snapshot_job.snapshot_step]`. Snapshots therefore see this cycle's FX codes.
- **`__main__.main()`**: `job = snapshot_job.worker()`, `job.start()`, then `loop.run_forever(stop)` inside `try`, with `job.stop()` in `finally`. The worker runs in the refresher process only, never in the admin or bot containers.
- **No-notification guard.** None of these files imports `discord` or `swingbot.commands`: every `swingbot/refresher/*.py`, plus `swingbot/core/analytics/admin_snapshots.py`, `swingbot/core/analytics/risk_payload.py` and `swingbot/core/marketdata/daily_readonly.py`. A runtime check runs one worker batch in a child interpreter where both are unimportable, and asserts neither was loaded.

- [ ] **Step 1: Write the failing schedule tests** in `tests/admin_snapshots/test_snapshot_schedule.py`

```python
"""v204: when the refresher builds snapshots -- cadence, trade and scan triggers, queue, month prune."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.analytics import admin_snapshots
from swingbot.core.db import engine
from swingbot.refresher import __main__ as entry
from swingbot.refresher import loop, snapshot_job
from swingbot.refresher.symbols import SymbolSet

NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)          # Fri 11:00 ET
KEYS = ["risk", "analytics.snapshot"]


class FakeWorker:
    def __init__(self):
        self.submitted, self.busy, self.landed, self.events = [], set(), [], []

    def submit(self, keys):
        keys = list(keys)
        self.submitted.append(keys)
        return [k for k in keys if k not in self.busy]

    def drain_landed(self):
        out, self.landed = self.landed, []
        return out

    def start(self):
        self.events.append("start")

    def stop(self, timeout=5.0):
        self.events.append("stop")


class FakeRows:
    def __init__(self):
        self.pruned = []

    def prune(self, prefix, keep):
        self.pruned.append((prefix, list(keep)))
        return 1


@pytest.fixture
def env(monkeypatch):
    e = SimpleNamespace(worker=FakeWorker(), rows=FakeRows(), fp=(3, "t1"), published=[])

    def no_build():
        raise AssertionError("the step built a snapshot inline")
    monkeypatch.setattr(admin_snapshots, "builders", lambda now=None: {k: no_build for k in KEYS})
    monkeypatch.setattr(snapshot_job, "worker", lambda: e.worker)
    monkeypatch.setattr(snapshot_job, "admin_snapshot_repo", lambda: e.rows)
    monkeypatch.setattr(snapshot_job, "_trades_fingerprint", lambda: e.fp)
    monkeypatch.setattr(snapshot_job.notify, "publish", e.published.append)
    for name, value in (("_last_runs", {}), ("_trades_fp", None), ("_was_scanning", False),
                        ("_pruned_for", None)):
        monkeypatch.setattr(snapshot_job, name, value)
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    return e


def ctx(at=NOW, *, queued=(), scanning=False, session="regular"):
    return loop.CycleContext(now=at, session=session, symbols=SymbolSet((), ()), queued_quotes=[],
                             queued_snapshots=list(queued), scan_running=scanning,
                             report=loop.CycleReport(session=session, cadence_s=30.0))


def due(last, **kw):
    kw.setdefault("session", "regular")
    kw.setdefault("builder_keys", KEYS)
    kw.setdefault("trades_changed", False)
    kw.setdefault("scan_completed", False)
    kw.setdefault("queued", [])
    return snapshot_job.due_keys(NOW, last, **kw)


def test_due_keys_follow_cadence_triggers_and_queue():
    recent = {k: NOW - timedelta(seconds=60) for k in KEYS}
    assert due({}) == KEYS
    assert due(recent) == []
    assert due({k: NOW - timedelta(seconds=300) for k in KEYS}) == KEYS        # regular cadence 300 s
    assert due({k: NOW - timedelta(seconds=400) for k in KEYS}, session="extended") == []   # 900 s
    assert due(recent, trades_changed=True) == KEYS
    assert due(recent, scan_completed=True) == KEYS
    assert due(recent, queued=["analytics.snapshot", "calendar.pnl:2020-01", "analytics.snapshot"]) == [
        "analytics.snapshot"]


def test_step_submits_due_keys_sets_changed_and_reports_landed(env):
    env.worker.landed = ["risk"]
    c = ctx()
    snapshot_job.snapshot_step(c)
    assert env.worker.submitted == [KEYS]
    assert c.report.changed is True and c.report.snapshots_written == ("risk",)
    assert env.published == []                                   # the step itself never publishes


def test_quiet_cycle_submits_nothing_and_changes_nothing(env):
    snapshot_job.snapshot_step(ctx())
    quiet = ctx(NOW + timedelta(seconds=30))
    snapshot_job.snapshot_step(quiet)
    assert env.worker.submitted == [KEYS] and quiet.report.changed is False


def test_trade_change_or_scan_end_rebuilds_inside_the_cadence(env):
    snapshot_job.snapshot_step(ctx(NOW, scanning=True))
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=30), scanning=True))
    assert len(env.worker.submitted) == 1
    env.fp = (4, "t2")                                           # a trade opened or closed
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=60), scanning=True))
    assert env.worker.submitted[-1] == KEYS
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=90), scanning=False))   # scan ended
    assert env.worker.submitted[-1] == KEYS and len(env.worker.submitted) == 3


def test_unknown_fingerprint_never_counts_as_a_trade_change(env):
    snapshot_job.snapshot_step(ctx())
    env.fp = None
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=30)))
    env.fp = (3, "t1")
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=60)))
    assert len(env.worker.submitted) == 1


def test_busy_key_is_retried_next_cycle(env):
    env.worker.busy = {"risk"}
    snapshot_job.snapshot_step(ctx())
    env.worker.busy = set()
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=30)))
    assert env.worker.submitted == [KEYS, ["risk"]]


def test_queued_key_is_built_inside_the_cadence(env):
    snapshot_job.snapshot_step(ctx())
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=10), queued=["risk", "calendar.pnl:2020-01"]))
    assert env.worker.submitted == [KEYS, ["risk"]]


def test_month_rollover_prunes_old_calendar_key(env):
    snapshot_job.snapshot_step(ctx())
    snapshot_job.snapshot_step(ctx(NOW + timedelta(seconds=30)))
    assert env.rows.pruned == [("calendar.pnl:", ["calendar.pnl:2026-10", "calendar.pnl:2026-09"])]
    snapshot_job.snapshot_step(ctx(datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)))
    assert env.rows.pruned[-1] == ("calendar.pnl:", ["calendar.pnl:2026-11", "calendar.pnl:2026-10"])


def test_refresher_off_skips_the_step(env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    c = ctx()
    snapshot_job.snapshot_step(c)
    assert env.worker.submitted == [] and c.report.changed is False


def test_snapshot_step_runs_after_the_quote_and_fx_steps():
    names = [step.__name__ for step in loop.STEPS]
    assert names.index("quote_step") < names.index("fx_step") < names.index("snapshot_step")


def test_main_starts_the_worker_before_the_loop_and_stops_it_after(monkeypatch):
    fake = FakeWorker()
    monkeypatch.setattr(snapshot_job, "worker", lambda: fake)

    def run(stop):
        fake.events.append("run")
        raise RuntimeError("loop died")
    monkeypatch.setattr(entry.loop, "run_forever", run)
    with pytest.raises(RuntimeError):
        entry.main()
    assert fake.events == ["start", "run", "stop"]


def test_trades_fingerprint_fails_open(monkeypatch):
    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(engine, "get_engine", down)
    assert snapshot_job._trades_fingerprint() is None


def test_worker_is_a_process_singleton():
    assert snapshot_job.worker() is snapshot_job.worker()
```

`test_trades_fingerprint_fails_open` needs `_trades_fingerprint` to look `get_engine` up on the `engine` module at call time (`from swingbot.core.db import engine` inside the function, then `engine.get_engine()`).

- [ ] **Step 2: Write the failing guard** in `tests/admin_snapshots/test_no_notification_guard.py`

```python
"""v204: the snapshot job adds no Discord message, alert or push (spec: no extra notification volume)."""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARDED = sorted((ROOT / "swingbot" / "refresher").glob("*.py")) + [
    ROOT / "swingbot" / "core" / "analytics" / "admin_snapshots.py",
    ROOT / "swingbot" / "core" / "analytics" / "risk_payload.py",
    ROOT / "swingbot" / "core" / "marketdata" / "daily_readonly.py",
]
FORBIDDEN = ("discord", "swingbot.commands")


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


@pytest.mark.parametrize("path", GUARDED, ids=lambda p: p.name)
def test_guarded_module_imports_no_discord_sender(path):
    bad = [m for m in _imports(path) if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)]
    assert bad == [], f"{path.relative_to(ROOT)} imports {bad}"


def test_guard_covers_the_refresher_modules():
    names = {p.name for p in GUARDED if p.parent.name == "refresher"}
    assert {"__main__.py", "loop.py", "quotes.py", "snapshot_job.py"} <= names


RUNTIME = '''
import importlib.abc
import sys


class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] == "discord" or name == "swingbot.commands" or name.startswith("swingbot.commands."):
            raise ImportError("blocked: " + name)
        return None


sys.meta_path.insert(0, Block())
from datetime import datetime, timezone

from swingbot.core.analytics.admin_snapshots import SnapshotResult
from swingbot.refresher import loop, snapshot_job  # noqa: F401


class Rows:
    def put(self, *a, **k):
        return True


class Marks:
    def mark(self, *a, **k):
        pass

    def clear(self, *a, **k):
        pass


sent = []
at = datetime(2026, 10, 28, 15, tzinfo=timezone.utc).isoformat()
w = snapshot_job.SnapshotWorker(
    builders_fn=lambda: {"risk": lambda: SnapshotResult({}, {"computed_at": at}, False)},
    repo_fn=Rows, marks_fn=Marks, publish=sent.append, budget_fn=lambda: 5.0)
assert w.run_batch(["risk"]) == ["risk"] and sent == ["market"]
leaked = sorted(m for m in sys.modules if m.split(".")[0] == "discord" or m.startswith("swingbot.commands"))
assert leaked == [], leaked
print("ok")
'''


def test_snapshot_job_runs_with_discord_unimportable():
    proc = subprocess.run([sys.executable, "-c", RUNTIME], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().endswith("ok")
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_schedule.py`, then `... file tests/admin_snapshots/test_no_notification_guard.py`
Expected: the schedule file FAILS (`AttributeError: module 'swingbot.refresher.snapshot_job' has no attribute 'due_keys'` and the missing `_last_runs` globals). In the guard file, the AST tests pass already and the runtime test passes too, because the worker exists. The guard is a regression pin: confirm it bites by temporarily adding `import discord` to `snapshot_job.py`, running the guard file (expect 2 failures), then removing the line.

- [ ] **Step 4: Implement the scheduling half of `snapshot_job.py`**

Append `due_keys`, `snapshot_step`, `worker`, `_trades_fingerprint` and the private `_triggers(ctx) -> tuple[bool, bool]` and `_prune_months(now) -> None`, per "Behaviour fixed here". Module state: `_last_runs: dict[str, datetime] = {}`, `_trades_fp = None`, `_was_scanning = False`, `_pruned_for = None`, `_WORKER: SnapshotWorker | None = None` and `_WORKER_LOCK = threading.Lock()`. `snapshot_step` reads `worker` and `admin_snapshot_repo` as module globals at call time, which the tests patch. Every function stays below complexity 15.

- [ ] **Step 5: Register the step and start the worker**

In `loop.py`, change the import to `from swingbot.refresher import quotes, snapshot_job` and append `snapshot_job.snapshot_step` to `STEPS`. In `__main__.py`, wrap `loop.run_forever(stop)` as described. Add `from swingbot.refresher import snapshot_job` beside the `loop` import.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for `tests/admin_snapshots/test_snapshot_schedule.py`, `tests/admin_snapshots/test_no_notification_guard.py`, `tests/admin_snapshots/test_snapshot_worker.py`, `tests/refresher/test_loop.py` and `tests/refresher/test_quote_cycle.py`
Expected: all PASS, `0 failed`. v201's loop tests patch `loop.STEPS`, so the extra step does not reach them. If one asserts `loop.STEPS == [quote_step, fx_step]` exactly, extend that assertion with `snapshot_job.snapshot_step`; that is the only v201 test edit allowed here. If the runtime guard fails because a v201 module imports `discord` or `swingbot.commands` transitively, stop and report `BLOCKED: <import chain>` (find it with `python -X importtime -c "import swingbot.refresher.loop"`). Never weaken the guard.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/refresher/snapshot_job.py swingbot/refresher/loop.py swingbot/refresher/__main__.py tests/admin_snapshots/test_snapshot_schedule.py tests/admin_snapshots/test_no_notification_guard.py
git -C <wt> commit -m "feat(v204): snapshot scheduling step in the refresher loop; no-notification guard"
```

If Step 6 extended an assertion in `tests/refresher/test_loop.py`, add that path to the same commit.

# Phase 4: The request path

### Task V204-11: Request door for snapshots: `read_snapshot`, `snapshot_meta`, `request_refresh(snapshots=)`

**Model:** sonnet — additive functions on v201's door against fixed contracts, tested with v201's fakes plus one fake snapshot store.

**Files:**
- Modify (created by v201 V201-7): `swingbot/admin/market_values.py` (`read_snapshot`, `snapshot_meta`, `request_refresh(..., snapshots=)`)
- Test: `tests/admin_snapshots/test_snapshot_door.py`

**Interfaces:**
- Consumes: V204-3 `admin_refresh.is_snapshot_key`, `snapshot_mark_key`, `stale_after_s("snapshot", state)`; V204-4 `admin_snapshot_repo().read(key)` (row `{key, doc, inputs, computed_at, stale_inputs, updated_at}`, tz-aware UTC); v201 `market_values._meta`, `_marks`, `_enqueue`, `market_refresh.refresh_queue_repo/refresh_mark_repo`, `session.session_state`, `session.last_regular_close`, `kinds.is_fresh_request`, `PRIORITY_*`, `QUEUE_KIND_QUOTE`, `QUEUE_KIND_SNAPSHOT`; v201 test fixtures `market`, `session_is` (`tests/admin_market/conftest.py`).
- Produces (index "Request-path door additions", exact): `read_snapshot(key: str, *, now: datetime | None = None) -> dict` with keys `key, doc, inputs, computed_at, stale_inputs, refreshing, error`; `snapshot_meta(snap: dict, *, extra_missing: int = 0) -> dict` (a MarketMeta with `source: "snapshot"`); `request_refresh(symbols, *, snapshots: Iterable[str] = (), priority: int = PRIORITY_USER) -> int`. For the V204-11b and V204-12 tests: fixture `snapshot_store` (a `FakeSnapshots` with `rows`, `changed`, `broken`, `read`, `read_many`, `changed_since`) and helper `snapshot_row(key, doc, *, age_s, stale=False, inputs=None) -> dict`, both in `tests/admin_snapshots/test_snapshot_door.py`.

**Behaviour fixed here (the tests pin each line):**
- **Imports.** `market_values` adds the top-level import `from swingbot.core.db.repositories import admin_snapshots as snapshot_store` and calls `snapshot_store.admin_snapshot_repo()` at call time, so the fixture can patch it.
- **`read_snapshot(key, *, now=None)`** never builds. `snapshot_mark_key(key)` validates the key, raising `ValueError` for an unknown one. It reads the row once and the mark once (v201's `_marks`, which fails open). A store error is swallowed (`"admin.market_values.snapshot_read"`): the row is treated as absent and `error = "snapshot store unavailable"`. Then:
  - `refreshing` is `True` when the row is absent or the mark is in flight. `error` is the mark's error, else the read error, else `None`.
  - The enqueue priority, through v201's fail-open `_enqueue(QUEUE_KIND_SNAPSHOT, [key], priority)`: `PRIORITY_FRESH_HINT` under `kinds.is_fresh_request()`; otherwise `PRIORITY_MISSING` when the row is absent, or when it is stale and its mark is not in flight; otherwise nothing.
  - **Stale** means `(now - computed_at).total_seconds() > stale_after_s("snapshot", state)` in regular and extended hours. When closed (`stale_after_s` is `None`), it means `computed_at < session.last_regular_close(now)`. `stale_inputs` alone never enqueues: the bars only move when the scan writes them, so a rebuild cannot fix it and would loop. The SPA shows it as stale instead.
  - It returns `{"key", "doc", "inputs", "computed_at": computed_at.isoformat() | None, "stale_inputs": bool, "refreshing", "error"}`.
- **`snapshot_meta(snap, *, extra_missing=0)`** goes through v201's `_meta`. `missing_count` is the number of unique symbols across `inputs.missing.quotes`, `inputs.missing.fx` and the keys of `inputs.missing.bars`, plus `extra_missing`. `incomplete` is `missing_count > 0`, and `stale_count` is `0`. `as_of` is the earliest of `inputs.oldest_quote_as_of` and `inputs.oldest_fx_as_of`, returned as its original string. A date-only value counts as 00:00 UTC on that date, and a naive datetime counts as UTC. With neither present, `as_of` is `snap["computed_at"]`. `computed_at`, `stale_inputs`, `refreshing` and `error` are copied from `snap`, and `source` is `"snapshot"`. With `inputs` `None`, the count is just `extra_missing`.
- **`request_refresh(symbols, *, snapshots=(), priority=PRIORITY_USER)`** dedupes `snapshots` in order and validates them all with `is_snapshot_key` **before** any enqueue (`ValueError("unknown snapshot keys: [...]")`). It enqueues the symbols exactly as in v201, then the snapshot keys as `QUEUE_KIND_SNAPSHOT` at `priority`. It returns the sum of the inserted counts and touches no queue for an empty list. Like v201, it does not swallow queue errors.

- [ ] **Step 1: Write the failing door tests** in `tests/admin_snapshots/test_snapshot_door.py`

```python
"""v204: the request door serves snapshot rows, never builds, and only enqueues."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin import market_values as mv
from swingbot.core.db.repositories import admin_snapshots as snapshot_repos
from swingbot.core.market import session
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.admin_refresh import (
    PRIORITY_FRESH_HINT, PRIORITY_MISSING, PRIORITY_USER, QUEUE_KIND_QUOTE, QUEUE_KIND_SNAPSHOT)
from tests.admin_market.conftest import market, session_is  # noqa: F401

META_KEYS = {"as_of", "refreshing", "stale_count", "missing_count", "incomplete",
             "computed_at", "stale_inputs", "source", "error"}


def utcnow():
    return datetime.now(timezone.utc)


def snapshot_row(key, doc, *, age_s, stale=False, inputs=None):
    at = utcnow() - timedelta(seconds=age_s)
    return {"key": key, "doc": doc, "inputs": inputs or {"computed_at": at.isoformat()},
            "computed_at": at, "stale_inputs": stale, "updated_at": at}


class FakeSnapshots:
    def __init__(self):
        self.rows, self.changed, self.broken = {}, [], False

    def read(self, key):
        if self.broken:
            raise RuntimeError("db down")
        return self.rows.get(key)

    def read_many(self, keys):
        return {k: self.rows[k] for k in keys if k in self.rows}

    def changed_since(self, since):
        if self.broken:
            raise RuntimeError("db down")
        return list(self.changed)


@pytest.fixture
def snapshot_store(monkeypatch):
    fake = FakeSnapshots()
    monkeypatch.setattr(snapshot_repos, "admin_snapshot_repo", lambda: fake)
    return fake


def test_absent_snapshot_is_refreshing_and_enqueued_once(market, session_is, snapshot_store):
    first = mv.read_snapshot("risk")
    mv.read_snapshot("risk")
    assert (first["doc"], first["computed_at"], first["refreshing"]) == (None, None, True)
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}


def test_fresh_row_is_served_as_stored_without_enqueue(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {"heat": {"open_pct": 1.2}}, age_s=180)
    snap = mv.read_snapshot("risk")
    assert snap["doc"] == {"heat": {"open_pct": 1.2}} and snap["refreshing"] is False
    assert datetime.fromisoformat(snap["computed_at"]).tzinfo is not None
    assert market.queue.pending == {}


def test_stale_row_is_enqueued_unless_in_flight(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=660)          # regular: stale after 600 s
    assert mv.read_snapshot("risk")["refreshing"] is False
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}
    market.queue.pending.clear()
    market.marks.in_flight.add("snapshot:risk")
    assert mv.read_snapshot("risk")["refreshing"] is True
    assert market.queue.pending == {}


@pytest.mark.parametrize("built_hours_after_close, enqueued", [(-1, True), (1, False)])
def test_closed_market_row_built_before_the_last_close_is_stale(market, session_is, snapshot_store,
                                                                monkeypatch, built_hours_after_close,
                                                                enqueued):
    session_is("closed")
    close = utcnow() - timedelta(hours=3)
    monkeypatch.setattr(session, "last_regular_close", lambda now=None: close)
    row = snapshot_row("risk", {}, age_s=0)
    row["computed_at"] = close + timedelta(hours=built_hours_after_close)
    snapshot_store.rows["risk"] = row
    mv.read_snapshot("risk")
    assert ((QUEUE_KIND_SNAPSHOT, "risk") in market.queue.pending) is enqueued


def test_stale_inputs_alone_never_enqueues(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=60, stale=True)
    assert mv.read_snapshot("risk")["stale_inputs"] is True
    assert market.queue.pending == {}


def test_mark_error_is_reported(market, session_is, snapshot_store):
    snapshot_store.rows["risk"] = snapshot_row("risk", {}, age_s=60)
    market.marks.errors_by_key["snapshot:risk"] = "budget exceeded after 90s"
    assert mv.read_snapshot("risk")["error"] == "budget exceeded after 90s"


def test_fresh_hint_enqueues_at_fresh_priority(market, session_is, snapshot_store):
    snapshot_store.rows["analytics.snapshot"] = snapshot_row("analytics.snapshot", {}, age_s=5)
    with kinds.fresh_request():
        mv.read_snapshot("analytics.snapshot")
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "analytics.snapshot"): PRIORITY_FRESH_HINT}


def test_store_failure_fails_open(market, session_is, snapshot_store):
    snapshot_store.broken = True
    snap = mv.read_snapshot("risk")
    assert snap["doc"] is None and snap["error"] == "snapshot store unavailable"


def test_read_snapshot_rejects_unknown_keys(market, session_is, snapshot_store):
    with pytest.raises(ValueError):
        mv.read_snapshot("prices")


def test_snapshot_meta_counts_unique_missing_symbols_and_takes_the_oldest_input():
    inputs = {"oldest_quote_as_of": "2026-10-30T14:58:00+00:00", "oldest_fx_as_of": "2026-10-29",
              "missing": {"quotes": ["NEWX"], "fx": ["SAP.DE"],
                          "bars": {"SAP.DE": "no_file", "XAUUSD": "spot_metal"}}}
    snap = {"key": "risk", "doc": {}, "inputs": inputs, "computed_at": "2026-10-30T15:00:00+00:00",
            "stale_inputs": True, "refreshing": False, "error": None}
    meta = mv.snapshot_meta(snap, extra_missing=1)
    assert set(meta) == META_KEYS
    assert (meta["missing_count"], meta["incomplete"], meta["stale_count"]) == (4, True, 0)
    assert meta["as_of"] == "2026-10-29" and meta["source"] == "snapshot"
    assert (meta["computed_at"], meta["stale_inputs"]) == ("2026-10-30T15:00:00+00:00", True)


def test_snapshot_meta_without_inputs_falls_back_to_computed_at():
    snap = {"key": "risk", "doc": {}, "inputs": {"missing": {"quotes": [], "fx": [], "bars": {}}},
            "computed_at": "2026-10-30T15:00:00+00:00", "stale_inputs": False, "refreshing": False,
            "error": None}
    assert mv.snapshot_meta(snap)["as_of"] == "2026-10-30T15:00:00+00:00"


def test_snapshot_meta_of_an_absent_row():
    snap = {"key": "risk", "doc": None, "inputs": None, "computed_at": None, "stale_inputs": False,
            "refreshing": True, "error": None}
    meta = mv.snapshot_meta(snap)
    assert (meta["as_of"], meta["missing_count"], meta["refreshing"]) == (None, 0, True)


def test_request_refresh_enqueues_snapshot_keys(market):
    assert mv.request_refresh(["msft"], snapshots=["risk", "risk", "calendar.pnl:2026-10"]) == 3
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "MSFT"): PRIORITY_USER,
                                    (QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_USER,
                                    (QUEUE_KIND_SNAPSHOT, "calendar.pnl:2026-10"): PRIORITY_USER}


def test_request_refresh_rejects_an_unknown_key_before_enqueueing(market):
    with pytest.raises(ValueError):
        mv.request_refresh(["MSFT"], snapshots=["risk", "prices"])
    assert market.queue.pending == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_door.py`
Expected: FAIL (`AttributeError: module 'swingbot.admin.market_values' has no attribute 'read_snapshot'`, and `TypeError` on `request_refresh(..., snapshots=...)`).

- [ ] **Step 3: Implement the door additions in `market_values.py`**

Add `read_snapshot`, `snapshot_meta` and the `snapshots` keyword per "Behaviour fixed here". The private helpers are `_snapshot_row(key) -> tuple[dict | None, str | None]`, `_snapshot_stale(computed_at, now) -> bool`, `_snapshot_priority(row, in_flight, now) -> int | None`, `_as_utc(value: str) -> datetime` and `_oldest_as_of(*values) -> str | None`. Each stays below complexity 15. The module docstring gains one sentence: v204 adds snapshot reads, which never build.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_door.py`, then `... file tests/admin_market/test_market_values.py`
Expected: both PASS, `0 failed`.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/admin/market_values.py tests/admin_snapshots/test_snapshot_door.py
git -C <wt> commit -m "feat(v204): snapshot reads through the market door; refresh queues snapshot keys"
```

### Task V204-11b: `snapshots` on `/market/updates` and `/market/refresh`

**Model:** sonnet — two additive fields on v201's endpoints with exact JSON contracts from the index.

**Files:**
- Modify (created by v201 V201-10): `swingbot/admin/api_v1/market_updates.py` (`snapshots` list, `status.stale_snapshot_s`, refresh body)
- Modify (created by v201 V201-10): `tests/admin_market/test_market_updates.py` (one test asserted v204's fields were absent)
- Test: `tests/admin_snapshots/test_market_updates_snapshots.py`

**Interfaces:**
- Consumes: V204-11 `market_values.request_refresh(symbols, *, snapshots=...)`, fixture `snapshot_store`, helper `snapshot_row`; V204-3 `admin_refresh.is_snapshot_key`, `snapshot_mark_key`, `snapshot_key_of`, `stale_after_s("snapshot", state)`; V204-4 `admin_snapshot_repo().read_many(keys)`, `.changed_since(since)`; v201 `market_updates._mark_changes`, `_cache_changes`, `status_block`, `_validated_refresh`, `MAX_REFRESH_SYMBOLS`, `iso`; v201 test fixtures `market`, `session_is`, `on_client`, `network_forbidden`.
- Produces (index "Endpoints", exact): `GET /api/v1/market/updates` gains `"snapshots": [{"key", "computed_at", "stale_inputs", "refreshing", "error"}]` and `status.stale_snapshot_s: float | None`; `POST /api/v1/market/refresh` accepts `{"symbols": [str], "snapshots": [str]}`.

**Behaviour fixed here (the tests pin each line):**
- **`/market/updates`**:
  - The body gains `"snapshots"`, which is `[]` without `since`.
  - With `since`, `_snapshot_updates(since, mark_rows)` takes the union of the keys from `admin_snapshot_repo().changed_since(since)` (a store error is swallowed to `[]`) and `snapshot_key_of(row["key"])` for the changed marks v201's `_mark_changes(since)` returned. Quote marks yield `None` and are skipped.
  - For those keys it reads `read_many` once and the marks once (`active` and `errors` over their `snapshot:` keys, failing open). Each item is `{"key", "computed_at": iso(row computed_at) | None, "stale_inputs": bool, "refreshing": in flight, "error": mark error | None}`, sorted by key.
  - It never enqueues and never builds.
- **`status_block(now)`** gains `"stale_snapshot_s": stale_after_s("snapshot", session)`, which is `None` when closed.
- **`/market/refresh`**:
  - `_validated_refresh(payload)` now returns `(symbols, snapshots)`. Each key defaults to `[]` when absent.
  - Any of the following → `400 invalid`, with nothing enqueued: either value is not a list; an item is not a string; there are more than `MAX_REFRESH_SYMBOLS` symbols; a snapshot key fails `is_snapshot_key`; or both lists are empty.
  - Success → `202 {"queued": request_refresh(symbols, snapshots=snapshots)}`.

- [ ] **Step 1: Write the failing endpoint tests** in `tests/admin_snapshots/test_market_updates_snapshots.py`

```python
"""v204: /market/updates reports snapshot changes; /market/refresh queues snapshot keys."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin.api_v1 import market_updates
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_USER, QUEUE_KIND_SNAPSHOT
from tests.admin_market.conftest import (  # noqa: F401
    _clear_login_limiter, admin_app, auth, client, market, on_client, session_is)
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.admin_snapshots.test_snapshot_door import snapshot_row, snapshot_store  # noqa: F401

NOW = datetime.now(timezone.utc)
SINCE = {"since": (NOW - timedelta(minutes=1)).isoformat()}


@pytest.fixture
def changes(monkeypatch):
    monkeypatch.setattr(market_updates, "_cache_changes", lambda since: [])


def test_without_since_snapshots_are_empty_and_status_carries_the_threshold(on_client, market,
                                                                            snapshot_store, changes,
                                                                            session_is):
    body = on_client.get("/api/v1/market/updates").get_json()
    assert body["snapshots"] == [] and body["status"]["stale_snapshot_s"] == 600.0
    session_is("closed")
    assert on_client.get("/api/v1/market/updates").get_json()["status"]["stale_snapshot_s"] is None


def test_since_lists_changed_rows_and_snapshot_marks(on_client, market, snapshot_store, changes,
                                                     network_forbidden):
    row = snapshot_row("risk", {"heat": {}}, age_s=30, stale=True)
    snapshot_store.rows["risk"] = row
    snapshot_store.changed.append({k: row[k] for k in ("key", "computed_at", "stale_inputs", "updated_at")})
    market.marks.in_flight.add("snapshot:analytics.snapshot")
    market.marks.changed += [
        {"key": "snapshot:analytics.snapshot", "in_flight": True, "error": None, "updated_at": NOW},
        {"key": "quote:NVDA", "in_flight": True, "error": None, "updated_at": NOW}]
    body = on_client.get("/api/v1/market/updates", query_string=SINCE).get_json()
    assert body["snapshots"] == [
        {"key": "analytics.snapshot", "computed_at": None, "stale_inputs": False,
         "refreshing": True, "error": None},
        {"key": "risk", "computed_at": row["computed_at"].isoformat(), "stale_inputs": True,
         "refreshing": False, "error": None}]
    assert market.queue.pending == {}                   # the updates read never enqueues
    assert network_forbidden == []


def test_snapshot_mark_error_reaches_updates(on_client, market, snapshot_store, changes):
    market.marks.errors_by_key["snapshot:risk"] = "DailyCacheUnavailable: not mounted"
    market.marks.changed.append({"key": "snapshot:risk", "in_flight": False,
                                 "error": "DailyCacheUnavailable: not mounted", "updated_at": NOW})
    [item] = on_client.get("/api/v1/market/updates", query_string=SINCE).get_json()["snapshots"]
    assert item["key"] == "risk" and item["error"] == "DailyCacheUnavailable: not mounted"


def test_snapshot_store_failure_fails_open(on_client, market, snapshot_store, changes):
    snapshot_store.broken = True
    resp = on_client.get("/api/v1/market/updates", query_string=SINCE)
    assert resp.status_code == 200 and resp.get_json()["snapshots"] == []


@pytest.mark.parametrize("body, queued", [({"snapshots": ["risk"]}, 1),
                                          ({"symbols": ["msft"], "snapshots": ["risk"]}, 2)])
def test_refresh_accepts_snapshot_keys(on_client, market, body, queued):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 202 and resp.get_json() == {"queued": queued}
    assert market.queue.pending[(QUEUE_KIND_SNAPSHOT, "risk")] == PRIORITY_USER


@pytest.mark.parametrize("body", [
    {"snapshots": "risk"},
    {"snapshots": [1]},
    {"snapshots": ["prices"]},
    {"symbols": [], "snapshots": []},
    {"symbols": ["MSFT"], "snapshots": ["bogus"]},
])
def test_refresh_rejects_bad_snapshot_bodies(on_client, market, body):
    resp = on_client.post("/api/v1/market/refresh", json=body)
    assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "invalid"
    assert market.queue.pending == {}
```

- [ ] **Step 2: Update v201's absence assertions, then run both files to verify they fail**

In `tests/admin_market/test_market_updates.py`, `test_without_since_only_status_is_filled` asserts `"snapshots" not in body` and `"stale_snapshot_s" not in status`. Change them to `body["snapshots"] == []` and `status["stale_snapshot_s"] == 600.0`. Nothing else in that file changes.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_market_updates_snapshots.py`, then `... file tests/admin_market/test_market_updates.py`
Expected: FAIL (`KeyError: 'snapshots'`; the refresh tests answer 400 for a snapshots-only body).

- [ ] **Step 3: Implement the endpoint changes in `market_updates.py`**

Add `_snapshot_updates(since, mark_rows) -> list[dict]` (with `_changed_snapshot_keys(since, mark_rows) -> list[str]` as its helper), the `"snapshots"` body key, `stale_snapshot_s` in `status_block`, and the new `_validated_refresh` return. As in v201, the door and the repositories are imported inside the functions. Every function stays below complexity 15.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for `tests/admin_snapshots/test_market_updates_snapshots.py`, `tests/admin_market/test_market_updates.py` and `tests/admin_snapshots/test_snapshot_door.py`
Expected: all PASS, `0 failed`.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/market_updates.py tests/admin_market/test_market_updates.py tests/admin_snapshots/test_market_updates_snapshots.py
git -C <wt> commit -m "feat(v204): snapshot changes on market updates; refresh accepts snapshot keys"
```

### Task V204-12: Risk reads its snapshot; kill-switch fallback pinned; two-clock metas; lower bounds

**Model:** opus — the Risk route decides whether a stale or partial risk picture can look current and complete; the on/off paths must stay one payload.

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py` (`get_risk` splits into `_risk_from_snapshot` and `_risk_on_request`; new `_meta_keys`, `_request_inputs`, `_lower_bound`, `_account_balance`)
- Modify: `tests/admin/test_api_v1_risk.py` (`test_risk_shape` declares the six new keys; nothing else)
- Test: `tests/admin_snapshots/test_risk_route.py`

**Interfaces:**
- Consumes: V204-11 `market_values.read_snapshot(key)`, `snapshot_meta(snap, *, extra_missing=0)`, fixture `snapshot_store`, helper `snapshot_row`; V204-6 `risk_payload.market_body`, `empty_body`, `RiskMetrics`, `risk._risk_metrics`, `risk._cached`, `risk._fresh_kill`, `risk._scan_health`; V204-7 `admin_snapshots.build_risk`, `stale_inputs_for(per_symbol, now)`, `_fx_inputs(tickers, *, on) -> tuple[dict, list[str]]` (module-private, called here for the off path's FX clock); V204-3 `admin_refresh.SNAPSHOT_RISK`, `refresher_on`; part 1 `golden_book`, `assert_matches_golden`, `GOLDEN_NOW`, `BAR_SYMBOLS`; v201 fixtures `market`, `session_is`, `on_client`, `network_forbidden`.
- Produces (index "Risk body additions", exact, on and off paths alike): `market_meta: MarketMeta`; `computed_at: str | None`; `bars_meta: {"per_symbol", "oldest", "newest", "stale_inputs", "missing": [{"symbol", "reason"}]}`; `fx_meta: {"as_of", "missing"}`; `lower_bound: list[str]`; `account: {"balance": float | None, "currency": str}`.

**Behaviour fixed here (the tests pin each line):**
- **`get_risk()`** returns `jsonify(_risk_from_snapshot())` when `admin_refresh.refresher_on()`, else `jsonify(_risk_on_request())`. The docstring lists the six new keys and both paths.
- **On: `_risk_from_snapshot()`.** It takes `snap = market_values.read_snapshot(SNAPSHOT_RISK)` and `doc = snap["doc"] or risk_payload.empty_body()`, and returns `{**doc, "availability": {**doc["availability"], "killswitch": kill["availability"]}, "killswitch": kill, "scan_health": _scan_health(), **_meta_keys(snap, balance=_account_balance())}` with `kill = _fresh_kill(throttle, {})`. It never calls `collect_portfolio_state`, `_cached`, `_risk_bars`, `_risk_metrics`, `admin_snapshots.build_*` or any fetch. The kill switch and scan health stay live per request, as today.
- **Off: `_risk_on_request()`** is V204-6's `get_risk` body unchanged (`_cached("portfolio_state", collect_portfolio_state)`, `_cached("metrics", _risk_metrics)`, `market_body`, live kill and scan health). It adds `**_meta_keys(snap, balance=state.get("balance"), source="request")`, where `snap` comes from `_request_inputs(state, result, body)`.
- **`_request_inputs(state, result, body) -> dict`** builds a snapshot-shaped dict from the request's own inputs, with no fetch. Let `now = datetime.now(timezone.utc)`. `fx_map, missing_fx` come from `admin_snapshots._fx_inputs(open tickers, on=now.date())`; any exception there gives `({}, [])`, swallowed as `"ops.risk.fx_inputs"`. The dict is `{"key": "risk", "doc": body, "computed_at": now.isoformat(), "stale_inputs": admin_snapshots.stale_inputs_for(result.bars_as_of, now), "refreshing": False, "error": None, "inputs": {...}}`. Its `inputs` holds only the keys `_meta_keys` reads:
  - `oldest_quote_as_of: None` and `fx: fx_map`;
  - `oldest_fx_as_of`, the min of the FX `as_of` values, else `None`;
  - `bars_as_of`, holding `per_symbol` (`result.bars_as_of`) and its min and max;
  - `missing: {"quotes": [], "fx": sorted(set(missing_fx)), "bars": dict(result.missing_bars)}`.
- **`_meta_keys(snap, *, balance, source="snapshot") -> dict`**:
  - `market_meta`: `market_values.snapshot_meta(snap)`, with `source` overridden.
  - `computed_at`: `snap["computed_at"]`.
  - `bars_meta`: `per_symbol`, `oldest` and `newest` from `inputs.bars_as_of`; `stale_inputs` from `snap`; `missing` is `[{"symbol", "reason"}]` from `inputs.missing.bars`, sorted by symbol.
  - `fx_meta`: `{"as_of": inputs.oldest_fx_as_of, "missing": sorted(inputs.missing.fx)}`.
  - `lower_bound`: `_lower_bound(snap["doc"], inputs.missing)`.
  - `account`: `{"balance": balance, "currency": fx.account_currency_code()}`.

  With `inputs` `None` (no row yet), every block is empty: `per_symbol` is `{}`, the dates are `None`, the lists are `[]`, and `stale_inputs` is `False`.
- **`_lower_bound(doc, missing) -> list[str]`** says which figures were computed without at least one held position. `held` is the upper-cased `ticker` of each `doc["positions"]` row (none when `positions` is `None`). The result keeps this fixed order:
  - `"metrics.closed"` when `doc.metrics.max_drawdown_amount.fx_missing_count > 0`;
  - `"metrics.distribution"` when a held ticker is in `missing.bars` or `missing.fx`;
  - `"correlation"` and `"clusters"` when a held ticker is in `missing.bars`.

  A missing benchmark (`SPY`) or any symbol not held never adds a path. The distribution and correlation availability already say so. Heat is trade-based (entry, stop, balance) and is never a lower bound (brief correction).
- **`_account_balance() -> float | None`** reads `account.load_account_config()` (Postgres, never the network) and returns `balance`, falling back to `base_balance`, when it is finite and positive. Otherwise, or on any error (swallowed as `"ops.risk.account_balance"`), it returns `None`. On the snapshot path the balance is therefore today's, while `heat.open_pct` is the snapshot's. Both are shown with their own clock; this is a known simplification.

- [ ] **Step 1: Write the failing route tests** in `tests/admin_snapshots/test_risk_route.py`

```python
"""v204: GET /risk serves its snapshot when the refresher is on, today's code when off."""
from datetime import datetime

import pytest

from swingbot import config
from swingbot.admin.api_v1 import risk
from swingbot.core.analytics import admin_snapshots, risk_payload
from swingbot.core.edge import portfolio_state, throttle
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_MISSING, QUEUE_KIND_SNAPSHOT
from swingbot.core.planning import account as account_module
from tests.admin_market.conftest import (  # noqa: F401
    _clear_login_limiter, admin_app, auth, client, market, on_client, session_is)
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.admin_snapshots.golden_book import (  # noqa: F401
    BAR_SYMBOLS, GOLDEN_NOW, assert_matches_golden, golden_book)
from tests.admin_snapshots.test_snapshot_door import snapshot_row, snapshot_store  # noqa: F401

NEW_KEYS = {"market_meta", "computed_at", "bars_meta", "fx_meta", "lower_bound", "account"}
POSITIONS = [{"trade_id": 7, "ticker": "AAPL"}, {"trade_id": 9, "ticker": "SAP.DE"},
             {"trade_id": 11, "ticker": "XAUUSD"}]


def inputs(*, fx_missing=(), bars_missing=None, per_symbol=None):
    per = per_symbol or {"AAPL": "2026-10-29", "SPY": "2026-10-28"}
    return {"computed_at": "2026-10-30T14:55:00+00:00", "oldest_quote_as_of": None, "quotes": {},
            "fx": {"EUR": {"rate": 1.08, "as_of": "2026-10-29"}}, "oldest_fx_as_of": "2026-10-29",
            "bars_as_of": {"per_symbol": per, "oldest": min(per.values()), "newest": max(per.values())},
            "missing": {"quotes": [], "fx": list(fx_missing),
                        "bars": bars_missing if bars_missing is not None else {"XAUUSD": "spot_metal"}}}


def doc(**extra):
    return {**risk_payload.empty_body(), "positions": POSITIONS, **extra}


@pytest.fixture
def heavy_forbidden(monkeypatch):
    called = []
    for module, name in ((portfolio_state, "collect_portfolio_state"), (admin_snapshots, "build_risk"),
                         (risk, "_risk_bars"), (risk, "_risk_metrics"), (risk, "_cached")):
        def boom(*a, _n=f"{module.__name__}.{name}", **k):
            called.append(_n)
            raise AssertionError(f"{_n} on the snapshot path")
        monkeypatch.setattr(module, name, boom)
    return called


def test_risk_on_serves_the_snapshot_with_a_live_killswitch(on_client, market, snapshot_store,
                                                            heavy_forbidden, network_forbidden,
                                                            monkeypatch):
    row = snapshot_row("risk", doc(heat={"open_pct": 1.2, "cap_pct": 6.0}), age_s=120, stale=True,
                       inputs=inputs())
    snapshot_store.rows["risk"] = row
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": True, "reason": "dd", "at": None})
    body = on_client.get("/api/v1/risk").get_json()
    assert body["heat"] == {"open_pct": 1.2, "cap_pct": 6.0} and body["killswitch"]["on"] is True
    assert body["availability"]["killswitch"]["state"] == "ok"
    assert body["bars_meta"] == {"per_symbol": {"AAPL": "2026-10-29", "SPY": "2026-10-28"},
                                 "oldest": "2026-10-28", "newest": "2026-10-29", "stale_inputs": True,
                                 "missing": [{"symbol": "XAUUSD", "reason": "spot_metal"}]}
    assert body["fx_meta"] == {"as_of": "2026-10-29", "missing": []}
    meta = body["market_meta"]
    assert (meta["source"], meta["stale_inputs"], meta["missing_count"]) == ("snapshot", True, 1)
    assert body["computed_at"] == row["computed_at"].isoformat()
    assert heavy_forbidden == [] and network_forbidden == []


def test_risk_on_with_no_row_returns_empty_body_refreshing(on_client, market, snapshot_store,
                                                          heavy_forbidden, network_forbidden):
    body = on_client.get("/api/v1/risk").get_json()
    assert set(risk_payload.empty_body()) | NEW_KEYS | {"killswitch", "scan_health"} == set(body)
    assert body["positions"] is None and body["computed_at"] is None and body["lower_bound"] == []
    assert body["market_meta"]["refreshing"] is True and body["bars_meta"]["per_symbol"] == {}
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}
    assert heavy_forbidden == [] and network_forbidden == []


def test_risk_lower_bound_names_figures_missing_inputs(on_client, market, snapshot_store):
    metrics = {**risk_payload.empty_body()["metrics"],
               "max_drawdown_amount": {"value": -120.0, "n": 5, "fx_missing_count": 2,
                                       "invalid_date_count": 0}}
    snapshot_store.rows["risk"] = snapshot_row("risk", doc(metrics=metrics), age_s=60,
                                               inputs=inputs(fx_missing=["SAP.DE"]))
    body = on_client.get("/api/v1/risk").get_json()
    assert body["lower_bound"] == ["metrics.closed", "metrics.distribution", "correlation", "clusters"]
    assert body["market_meta"]["missing_count"] == 2 and body["market_meta"]["incomplete"] is True


@pytest.mark.parametrize("missing, expected", [
    ({"fx": ["SAP.DE"], "bars": {}}, ["metrics.distribution"]),
    ({"fx": [], "bars": {"XAUUSD": "spot_metal"}}, ["metrics.distribution", "correlation", "clusters"]),
    ({"fx": [], "bars": {"SPY": "short:9/21"}}, []),          # benchmark only: not a held position
    ({"fx": ["NVDA"], "bars": {}}, []),                        # not held
    ({"fx": [], "bars": {}}, []),
])
def test_lower_bound_counts_only_held_positions(missing, expected):
    assert risk._lower_bound(doc(), missing) == expected


def test_lower_bound_with_no_positions_is_empty():
    assert risk._lower_bound(risk_payload.empty_body(), {"fx": ["AAPL"], "bars": {"AAPL": "no_file"}}) == []


def test_risk_account_carries_balance_and_currency(on_client, market, snapshot_store, monkeypatch):
    monkeypatch.setattr(account_module, "load_account_config", lambda: {"balance": 12_500.0})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    assert on_client.get("/api/v1/risk").get_json()["account"] == {"balance": 12_500.0, "currency": "USD"}


@pytest.mark.parametrize("cfg", [{"balance": float("nan")}, {"balance": 0}, None])
def test_risk_account_balance_unknown_is_null_never_zero(on_client, market, snapshot_store,
                                                         monkeypatch, cfg):
    def load():
        if cfg is None:
            raise RuntimeError("db down")
        return cfg
    monkeypatch.setattr(account_module, "load_account_config", load)
    assert on_client.get("/api/v1/risk").get_json()["account"]["balance"] is None


def test_risk_off_runs_todays_code_and_adds_the_meta_keys(golden_book, monkeypatch):
    calls = []
    real = portfolio_state.collect_portfolio_state
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state",
                        lambda **kw: calls.append(1) or real(**kw))
    body = golden_book.client.get("/api/v1/risk").get_json()
    assert calls == [1]                                          # the kill-switch fallback computes
    assert_matches_golden("risk", body)
    assert NEW_KEYS <= set(body) and body["market_meta"]["source"] == "request"
    assert body["computed_at"] is not None and body["market_meta"]["refreshing"] is False
    assert body["bars_meta"]["per_symbol"] and set(body["bars_meta"]["per_symbol"]) <= set(BAR_SYMBOLS)
    assert golden_book.network_calls == []


def test_snapshot_body_matches_the_off_body_and_the_golden(golden_book, market, snapshot_store,
                                                           session_is, monkeypatch):
    off = golden_book.client.get("/api/v1/risk").get_json()
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(admin_snapshots, "_now", lambda: GOLDEN_NOW)
    res = admin_snapshots.build_risk()
    snapshot_store.rows["risk"] = {"key": "risk", "doc": res.doc, "inputs": res.inputs,
                                   "computed_at": datetime.fromisoformat(res.inputs["computed_at"]),
                                   "stale_inputs": res.stale_inputs, "updated_at": GOLDEN_NOW}
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    on = golden_book.client.get("/api/v1/risk").get_json()
    assert set(on) == set(off)
    assert_matches_golden("risk", on)
    assert on["market_meta"]["source"] == "snapshot" and golden_book.network_calls == []
```

`test_snapshot_body_matches_the_off_body_and_the_golden` is the request half of the anti-fork rule. The snapshot half is V204-7's golden test. If it fails only on `clusters`, `golden_book` serves `data.get_daily_data` differently from the bar files: report `BLOCKED: golden_book cluster bars`, as V204-7 does. Never edit a golden file.

- [ ] **Step 2: Declare the new keys in the admin shape test, then run both files to verify they fail**

In `tests/admin/test_api_v1_risk.py` `test_risk_shape`, add to the first `assert_shape` dict: `"market_meta": dict, "computed_at": (str, type(None)), "bars_meta": dict, "fx_meta": dict, "lower_bound": list, "account": dict`. The admin suite pins `ADMIN_REFRESHER="off"`, so this covers the fallback's shape.
Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_risk_route.py`, then `... file tests/admin/test_api_v1_risk.py`
Expected: FAIL (`KeyError: 'bars_meta'` and the like; `AttributeError: ... '_lower_bound'`; `test_risk_shape` reports the missing keys).

- [ ] **Step 3: Implement the route split in `risk.py`**

Implement `get_risk`, `_risk_from_snapshot`, `_risk_on_request`, `_request_inputs`, `_meta_keys`, `_lower_bound` and `_account_balance` per "Behaviour fixed here". Import `admin_refresh` at module top. Import `market_values`, `admin_snapshots`, `risk_payload`, `fx`, `throttle`, `collect_portfolio_state` and `account` inside the functions, as this module already does. Each module is looked up at call time, so the tests' patches bite. Split `_meta_keys` into `_bars_meta(inputs, stale)` and `_fx_meta(inputs)` to stay below complexity 15. `_risk_on_request` keeps today's comment on the unclamped utilisation (it moved into `market_body` in V204-6) and today's call order.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for `tests/admin_snapshots/test_risk_route.py`, `tests/admin/test_api_v1_risk.py`, `tests/admin_snapshots/test_risk_payload.py`, `tests/admin_snapshots/test_build_risk.py` and `tests/admin_snapshots/test_golden_today.py`
Expected: all PASS, `0 failed`. The golden files are untouched (`git -C <wt> status --short tests/admin_snapshots/golden` prints nothing).
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/risk.py tests/admin/test_api_v1_risk.py tests/admin_snapshots/test_risk_route.py
git -C <wt> commit -m "feat(v204): Risk serves its stored snapshot; kill-switch fallback keeps request compute; clocks and lower bounds"
```

