# v206 Plan 1, part 1b — raising progress read and the broker's `scan` payload

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md)
**Index:** [`2026-11-05-v206-admin-under-load_0-index.md`](2026-11-05-v206-admin-under-load_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V206-5..V206-6 (index group C, ledger part 1). They sit in their own file because part 1 (`_1-probe-and-broker.md`, V206-1..V206-4) would otherwise pass the 1500-line cap; a task is never split across files. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v206-admin-under-load`; every command runs with that path, never in the main tree. Python tests run narrow (`cd "<wt>" && python scripts/dev/testrun.py file <test>`); no task runs the full suite.

# Phase C — the broker carries scan progress

### Task V206-5: Raising progress read + `conn=` on the running flag

**Model:** sonnet — two small additive functions in `core/scanning` with DB-free fakes; the existing swallowing read keeps its behaviour.

**Files:**
- Modify: `swingbot/core/scanning/progress_store.py`
- Modify: `swingbot/core/scanning/runstate.py`
- Create: `tests/scanning/test_progress_store_strict.py`

**Interfaces:**
- Consumes: `ScanProgressRepository.read(self, *, conn=None)` (`core/db/repositories/scan_progress.py:19`), `FlagRepository.is_set(name, *, conn=None)` (`core/db/repositories/flags.py:17`); both exist.
- Produces (V206-6's default progress reader calls both on one side connection):
  - `progress_store.read_strict(*, conn=None) -> dict | None`: the record, `None` when nothing is publishing, **raises** when the read fails.
  - `runstate.is_scan_running(*, conn=None) -> bool`: unchanged without `conn`.

Spec P1-b ("Failure must be visible"): `progress_store.read()` swallows every error and returns `None`, which is also the legitimate "nothing publishing" value, so the broker could never tell a failed read from an idle bot. `read_strict` is the raising variant for that caller only. `read()` keeps its contract (and its swallowed tag `scan.progress_store.read`) for `/system/scan`, by delegating to `read_strict()` inside its existing `try`. Every existing caller of `is_scan_running()` passes no argument (`admin/app.py:396`, `refresher/loop.py:90`, `commands/scanning/commands.py:427`), so the keyword-only `conn` changes nothing for them. `tests/scanning/` is already in suite `scanning`.

- [ ] **Step 1: Measure complexity before**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; `_read_row`, `read` and `is_scan_running` are each 1–2.

- [ ] **Step 2: Write the failing tests**

Create `tests/scanning/test_progress_store_strict.py`:

```python
"""v206 P1-b: a progress read that fails loudly, and the running flag on a given connection.

The admin's event broker reads both once per `scan` event on its fail-fast
side connection, and must tell "nothing publishing" (None) from "could not
read" (raise). `progress_store.read()` folds both into None, so the broker
gets `read_strict`; `read()` keeps its swallowing contract for /system/scan.
DB-free: the repositories are faked.
"""
import pytest

from swingbot.core.db.repositories import scan_progress as repo_module
from swingbot.core.infra.swallowed import reset, snapshot
from swingbot.core.scanning import progress_store, runstate


class _Repo:
    def __init__(self, record=None, error=None):
        self.record, self.error, self.conns = record, error, []

    def read(self, *, conn=None):
        self.conns.append(conn)
        if self.error is not None:
            raise self.error
        return self.record


@pytest.fixture
def repo(monkeypatch):
    def install(**kwargs):
        made = _Repo(**kwargs)
        monkeypatch.setattr(repo_module, "scan_progress_repo", lambda: made)
        return made
    return install


def test_read_strict_returns_the_record_read_on_the_given_connection(repo):
    made = repo(record={"pct": 40, "stage": "crawling data"})
    conn = object()
    assert progress_store.read_strict(conn=conn) == {"pct": 40, "stage": "crawling data"}
    assert made.conns == [conn]


def test_read_strict_is_none_when_nothing_is_publishing(repo):
    repo(record=None)
    assert progress_store.read_strict() is None


def test_read_strict_raises_when_the_read_fails(repo):
    repo(error=RuntimeError("canceling statement due to statement timeout"))
    with pytest.raises(RuntimeError, match="statement timeout"):
        progress_store.read_strict()


def test_read_still_swallows_and_counts_the_same_tag(repo):
    reset()
    made = repo(error=RuntimeError("boom"))
    assert progress_store.read() is None
    assert made.conns == [None]
    assert snapshot()["scan.progress_store.read"]["count"] == 1


def test_read_still_returns_the_record(repo):
    repo(record={"pct": 70})
    assert progress_store.read() == {"pct": 70}


class _Flags:
    def __init__(self, value):
        self.value, self.calls = value, []

    def is_set(self, name, *, conn=None):
        self.calls.append((name, conn))
        return self.value


def test_is_scan_running_reads_the_flag_on_the_given_connection(monkeypatch):
    flags = _Flags(True)
    monkeypatch.setattr(runstate, "_flags", lambda: flags)
    conn = object()
    assert runstate.is_scan_running(conn=conn) is True
    assert flags.calls == [("scan_running", conn)]


def test_is_scan_running_without_a_connection_is_unchanged(monkeypatch):
    flags = _Flags(False)
    monkeypatch.setattr(runstate, "_flags", lambda: flags)
    assert runstate.is_scan_running() is False
    assert flags.calls == [("scan_running", None)]
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scanning/test_progress_store_strict.py`
Expected: `AttributeError: module 'swingbot.core.scanning.progress_store' has no attribute 'read_strict'` and `TypeError: is_scan_running() got an unexpected keyword argument 'conn'`.

- [ ] **Step 4: Add `read_strict` and route `read()` through it**

In `swingbot/core/scanning/progress_store.py`, replace `_read_row` (lines ~94-102) with:

```python
def read_strict(*, conn=None) -> dict | None:
    """The current record, None when no scan is publishing one -- and RAISES
    when the read fails.

    For the admin's event broker (v206 P1-b), which must tell "nothing
    publishing" apart from "could not read": the first sends `progress: null`
    inside the payload, the second sends the event thin and counts it.
    `conn` lets it read on its fail-fast side connection.
    """
    from swingbot.core.db.repositories.scan_progress import scan_progress_repo
    return scan_progress_repo().read(conn=conn)


def _read_row() -> dict | None:
    try:
        return read_strict()
    except Exception as exc:  # noqa: BLE001
        swallowed(log, "scan.progress_store.read", exc,
                  "Could not read scan progress from the database",
                  level=logging.DEBUG, exc_info=True)
        return None
```

Leave `read()` as it is (it calls `_read_row()`).

- [ ] **Step 5: Give `is_scan_running` a connection**

In `swingbot/core/scanning/runstate.py`, replace `is_scan_running` with:

```python
def is_scan_running(*, conn=None) -> bool:
    """Whether a scan (manual !check/`/check`, admin-UI-triggered, or the
    automatic session scan) is currently executing. Used by the admin UI
    to enable/disable its "Stop scan" button.

    `conn` (v206): read on the caller's connection. The admin's event broker
    passes its fail-fast side connection; every other caller passes nothing.
    """
    return _flags().is_set("scan_running", conn=conn)
```

- [ ] **Step 6: Run the new tests and the existing progress-store tests**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scanning/test_progress_store_strict.py`
Expected: all pass, `0 failed`.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/scanning/test_progress_store.py`
Expected: all pass, `0 failed` (`test_an_unreadable_record_reads_as_absent_rather_than_raising` patches `scan_progress_repo` on the module, which `read_strict` looks up at call time). This file reads through the database: if the shared `swing-db` is not up in this session, run `/replicate-prod-db` first.

- [ ] **Step 7: Complexity after**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; `read_strict` is 1, `_read_row` 2, `is_scan_running` 1.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/core/scanning/progress_store.py swingbot/core/scanning/runstate.py tests/scanning/test_progress_store_strict.py
git -C "<wt>" commit -m "feat(v206): raising progress read and is_scan_running(conn=) for the event broker (V206-5)"
```

### Task V206-6: Broker: `scan` events carry progress

**Model:** opus — threading and the listener's must-not-block contract on a fan-out every admin tab depends on; the wire shape is the plan's one cross-language contract.

**Files:**
- Modify: `swingbot/admin/events/broker.py`
- Modify: `tests/admin/test_event_broker.py`
- Modify: `tests/admin/test_event_stream.py` (fixture injects a DB-free reader, plus one wire test; not in the index ledger's file list, test-only)

**Interfaces:**
- Consumes (V206-5): `progress_store.read_strict(*, conn=None)` and `runstate.is_scan_running(*, conn=None)`; `side_engine.side_connection()` (exists, `core/db/side_engine.py:86`); `swallowed(log, tag, exc, msg, *args, level=...)` (exists, `core/infra/swallowed.py:62`).
- Produces (part 2's `parseScanEventProgress` and `EventStream.payload('scan')` read this frame):
  - `Event.progress: dict | None = None`; `Event.data()` adds `"progress"` **only when set**.
  - `EventBroker(*, watcher_factory=None, progress_reader=None, clock=time.monotonic, max_connections=MAX_CONNECTIONS, queue_limit=QUEUE_LIMIT)`.
  - `progress_reader() -> dict | None` returning `{"running": bool, "progress": dict | None}` (the subset of `/system/scan` the progress strip reads); raising or returning `None` means a thin event.
  - `SCAN_PROGRESS_TAG = "admin.events.scan_progress"`, `PROGRESS_LOG_INTERVAL_S = 60.0`, `_default_progress_reader()`.
  - Wire frame for `scan`: `{"seq": int, "at": str, "progress": {"running": bool, "progress": {...} | null}}`; every other frame stays `{"seq", "at"}`.

Rules from spec P1-b and the Global Constraints:
- `publish` runs on the `db-event-listener` thread, whose `emit` must not block (`db_listener.py:36-42`). The read is the narrow one (running flag + progress row, never `scan_status_payload`), through the fail-fast `side_connection()` (`MARKETDATA_PG_TIMEOUT_MS` statement timeout, 250 ms by default; backs off 30 s after a refused connect).
- The read runs **outside `self._lock`**, **once per publish** (never per connection), **only for `scan`**, and only when at least one connection is open (with none, nobody would see it).
- A read that raises sends the event **thin**: no `progress` key, never `"progress": null`. It is counted under `admin.events.scan_progress` every time and logged at WARNING at most once per 60 s (DEBUG otherwise), on the injectable clock.
- The backlog collapse in `Subscription._offer` still builds a bare `Event(seq, "resync", at)`: `progress` defaults to `None`, so the resync stays `{seq, at}`.
- Every `scan` source (`scan_progress`, `runtime_flags`, `scan_snapshots`, `scan_telemetry`) goes through `publish`, so all of them carry the read with no change elsewhere. `stream.py` json-dumps `event.data()`, so the nested dict needs no stream change; the progress record is JSONB from the row, so it serialises as is.
- `publish` gets named helpers (`_scan_progress`, `_note_progress_failure`), not new branches.

- [ ] **Step 1: Measure complexity before**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; `publish` is 3, `Event.data` 1, `_offer` 5 (brief, radon).

- [ ] **Step 2: Keep the existing broker tests DB-free**

In `tests/admin/test_event_broker.py`, change the `make_broker` fixture's factory to inject a reader that needs no database (the existing `test_the_event_carries_its_name_and_a_timestamp` publishes `scan` and asserts the thin body; a `None` read keeps it true):

```python
@pytest.fixture
def make_broker(watchers):
    def factory(**kwargs):
        def build(emit):
            watcher = FakeWatcher(emit)
            watchers.append(watcher)
            return watcher

        # v206: no database here. Tests of the progress read inject their own.
        kwargs.setdefault("progress_reader", lambda: None)
        return b.EventBroker(watcher_factory=build, **kwargs)

    return factory
```

In `tests/admin/test_event_stream.py`, change the `broker` fixture's construction to:

```python
    made = b.EventBroker(watcher_factory=lambda emit: FakeWatcher(emit), progress_reader=lambda: None)
```

- [ ] **Step 3: Write the failing tests**

Add `import json` and `import logging` to the imports of `tests/admin/test_event_broker.py`, plus:

```python
from contextlib import contextmanager

from sqlalchemy import exc as sa_exc

from swingbot.core.db.engine import DatabaseUnavailable
from swingbot.core.infra.swallowed import reset, snapshot
```

Append to `tests/admin/test_event_broker.py`:

```python
# --------------------------------------------------------------------------
# v206 P1-b: scan events carry the progress the strip reads
# --------------------------------------------------------------------------

PROGRESS = {"running": True, "progress": {
    "at": "2026-11-05T15:20:00+00:00", "pct": 40, "stage": "crawling data",
    "current_ticker": "NVDA", "done": 12, "total": 30, "qualifying_found": 1}}


class CountingReader:
    def __init__(self, result=PROGRESS, error=None):
        self.result, self.error, self.calls = result, error, 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_a_scan_event_carries_the_progress_it_read(make_broker, watchers):
    broker = make_broker(progress_reader=CountingReader())
    with broker.subscribe() as subscription:
        watchers[0].emit("scan")
        event = subscription.get(timeout=0)

    assert event.data() == {"seq": event.seq, "at": event.at, "progress": PROGRESS}
    json.dumps(event.data())  # the stream json-dumps it


def test_other_events_stay_byte_identical_and_never_read(make_broker, watchers):
    reader = CountingReader()
    broker = make_broker(progress_reader=reader)
    with broker.subscribe() as subscription:
        for name in ("trades", "bot", "risk"):
            watchers[0].emit(name)
        events = [subscription.get(timeout=0) for _ in range(3)]

    assert reader.calls == 0
    for event in events:
        assert json.dumps(event.data()) == json.dumps({"seq": event.seq, "at": event.at})


def test_one_publish_reads_once_whatever_the_number_of_connections(make_broker, watchers):
    reader = CountingReader()
    broker = make_broker(progress_reader=reader)
    with broker.subscribe() as one, broker.subscribe() as two, broker.subscribe() as three:
        watchers[0].emit("scan")
        events = [s.get(timeout=0) for s in (one, two, three)]

    assert reader.calls == 1
    assert all(event.progress == PROGRESS for event in events)
    assert len({event.seq for event in events}) == 1


def test_nobody_listening_means_no_read(make_broker):
    reader = CountingReader()
    broker = make_broker(progress_reader=reader)
    broker.publish("scan")
    assert reader.calls == 0


def test_the_read_runs_outside_the_broker_lock(make_broker, watchers):
    held = []
    box = {}

    def reader():
        held.append(box["broker"]._lock.locked())
        return PROGRESS

    box["broker"] = broker = make_broker(progress_reader=reader)
    with broker.subscribe():
        watchers[0].emit("scan")
    assert held == [False]


@pytest.mark.parametrize("error", [
    RuntimeError("boom"),
    DatabaseUnavailable("side engine backing off"),
    sa_exc.OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout")),
])
def test_a_failed_read_sends_a_thin_event_and_counts_it(make_broker, watchers, error):
    reset()
    broker = make_broker(progress_reader=CountingReader(error=error))
    with broker.subscribe() as subscription:
        watchers[0].emit("scan")
        event = subscription.get(timeout=0)

    assert event.event == "scan"
    assert event.data() == {"seq": event.seq, "at": event.at}  # thin, never "progress": None
    assert snapshot()[b.SCAN_PROGRESS_TAG]["count"] == 1


def test_a_failing_read_logs_at_most_once_a_minute(make_broker, watchers, caplog):
    reset()
    now = [1000.0]
    broker = make_broker(progress_reader=CountingReader(error=RuntimeError("boom")), clock=lambda: now[0])
    caplog.set_level(logging.DEBUG, logger=b.log.name)
    with broker.subscribe() as subscription:
        for t in (1000.0, 1030.0, 1059.9, 1060.0, 1100.0):
            now[0] = t
            watchers[0].emit("scan")
        assert len(drain(subscription)) == 5

    loud = [r for r in caplog.records if r.name == b.log.name and r.levelno >= logging.WARNING]
    assert len(loud) == 2  # 1000.0 and 1060.0
    assert snapshot()[b.SCAN_PROGRESS_TAG]["count"] == 5


def test_the_backlog_collapse_is_still_a_bare_resync(make_broker, watchers):
    broker = make_broker(progress_reader=CountingReader(), queue_limit=1)
    with broker.subscribe() as subscription:
        watchers[0].emit("scan")
        watchers[0].emit("scan")  # queue full: collapse
        event = subscription.get(timeout=0)

    assert event.event == "resync"
    assert event.data() == {"seq": event.seq, "at": event.at}


def test_a_reader_returning_none_sends_the_event_thin(make_broker, watchers):
    broker = make_broker(progress_reader=lambda: None)
    with broker.subscribe() as subscription:
        watchers[0].emit("scan")
        assert "progress" not in subscription.get(timeout=0).data()


def test_the_default_reader_reads_both_facts_on_one_side_connection(monkeypatch):
    from swingbot.core.db import side_engine
    from swingbot.core.scanning import progress_store, runstate

    conn, seen = object(), []

    @contextmanager
    def fake_side_connection():
        yield conn

    monkeypatch.setattr(side_engine, "side_connection", fake_side_connection)
    monkeypatch.setattr(runstate, "is_scan_running",
                        lambda *, conn=None: seen.append(("running", conn)) or True)
    monkeypatch.setattr(progress_store, "read_strict",
                        lambda *, conn=None: seen.append(("progress", conn)) or PROGRESS["progress"])

    assert b._default_progress_reader() == PROGRESS
    assert seen == [("running", conn), ("progress", conn)]


def test_the_default_reader_raises_when_the_side_engine_is_down(monkeypatch):
    from swingbot.core.db import side_engine

    @contextmanager
    def down():
        raise DatabaseUnavailable("side engine backing off")
        yield  # pragma: no cover

    monkeypatch.setattr(side_engine, "side_connection", down)
    with pytest.raises(DatabaseUnavailable):
        b._default_progress_reader()


def test_production_brokers_use_the_default_reader():
    assert b.EventBroker()._progress_reader is b._default_progress_reader
```

Append to `tests/admin/test_event_stream.py`, after `test_every_connection_gets_its_own_stream`:

```python
def test_a_scan_event_carries_its_progress_on_the_wire(client, auth, monkeypatch):
    """v206 P1-b: the frame part 2's client parses. Other events stay {seq, at}."""
    progress = {"running": True, "progress": None}
    made = b.EventBroker(watcher_factory=lambda emit: FakeWatcher(emit), progress_reader=lambda: progress)
    monkeypatch.setattr(b, "_BROKER", made)
    monkeypatch.setattr(s, "get_broker", lambda: made)

    response = client.get("/api/v1/events", headers=auth)
    made.publish("scan")
    event = take(response, 2)[1]

    assert event["name"] == "scan"
    assert event["data"] == {"seq": made.seq, "at": event["data"]["at"], "progress": progress}
```

- [ ] **Step 4: Run the tests to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_broker.py`
Expected: `TypeError: EventBroker.__init__() got an unexpected keyword argument 'progress_reader'` across the file (the fixture now passes it).

- [ ] **Step 5: Implement the payload in the broker**

In `swingbot/admin/events/broker.py`:

Add `import time` to the standard-library imports and, below `from .db_listener import DbEventListener`:

```python
from swingbot.core.infra.swallowed import swallowed
```

Below `_default_watcher`, add:

```python
#: Swallowed-error tag for a failed progress read on a `scan` event (v206 P1-b).
SCAN_PROGRESS_TAG = "admin.events.scan_progress"

#: A failing read is counted every time but logged at WARNING at most this often.
PROGRESS_LOG_INTERVAL_S = 60.0


def _default_progress_reader() -> dict:
    """What the progress strip reads from `/system/scan`: `running` and `progress`.

    Runs on the listener thread, whose `emit` must not block
    (`db_listener.py`), so it is the narrow read -- the running flag and the
    progress row, never `scan_status_payload` -- on the fail-fast side
    connection (`MARKETDATA_PG_TIMEOUT_MS` statement timeout; it backs off
    after a refused connect). Raises on any failure; `publish` then sends
    the event thin.
    """
    from swingbot.core.db import side_engine
    from swingbot.core.scanning import progress_store, runstate

    with side_engine.side_connection() as conn:
        return {"running": runstate.is_scan_running(conn=conn),
                "progress": progress_store.read_strict(conn=conn)}
```

Replace the `Event` class body with:

```python
@dataclass(frozen=True)
class Event:
    """One notification, on its way to one or more browsers."""

    seq: int
    event: str
    at: str
    #: v206: `{running, progress}` on a `scan` event whose read succeeded; else None.
    progress: dict | None = None

    def data(self) -> dict:
        """The SSE `data:` body -- what changed is the event *name*.

        Deliberately excludes the name itself: it travels in the `event:`
        field, and repeating it here would invite a client to read it from
        the body instead, which breaks `addEventListener` dispatch.

        v206: a `scan` event carries `progress` when the broker read it, so
        the progress strip patches without a request. Only when set: every
        other frame stays `{seq, at}` byte for byte, and a failed read sends
        the event thin, never `"progress": null`.
        """
        body = {"seq": self.seq, "at": self.at}
        if self.progress is not None:
            body["progress"] = self.progress
        return body
```

Replace `EventBroker.__init__` with:

```python
    def __init__(
        self,
        *,
        watcher_factory=None,
        progress_reader=None,
        clock=time.monotonic,
        max_connections: int = MAX_CONNECTIONS,
        queue_limit: int = QUEUE_LIMIT,
    ):
        self._watcher_factory = watcher_factory or _default_watcher
        # v206: injectable beside the watcher so tests need no database.
        self._progress_reader = progress_reader or _default_progress_reader
        self._clock = clock
        self._progress_logged_at: float | None = None
        self._max_connections = max_connections
        self._queue_limit = queue_limit

        self._lock = threading.Lock()
        self._subscriptions: set[Subscription] = set()
        self._watcher = None
        self._seq = 0
```

Extend the class docstring with: ``"`progress_reader` and `clock` (v206) are injectable for the same reason."``

Replace `publish` with the following and add the two helpers below it:

```python
    def publish(self, event: str) -> None:
        """Stamp an event and hand it to every open connection.

        Called from the watcher's thread. It must not raise: the watcher
        survives a subscriber exception, but a raise here would abandon the
        remaining connections mid-fan-out, so each delivery is isolated.

        v206: a `scan` event reads the scan progress once, here -- outside
        the lock, never per connection, and only when someone is listening.
        """
        with self._lock:
            self._seq += 1
            seq, at = self._seq, iso(datetime.now(timezone.utc))
            targets = list(self._subscriptions)

        progress = self._scan_progress() if event == "scan" and targets else None
        stamped = Event(seq=seq, event=event, at=at, progress=progress)
        for subscription in targets:
            try:
                subscription._offer(stamped)
            except Exception:
                log.exception("failed to deliver %r to an event connection", event)

    def _scan_progress(self) -> dict | None:
        """The `scan` payload, or None (a thin event) when the read fails. Never raises."""
        try:
            return self._progress_reader()
        except Exception as exc:  # noqa: BLE001 -- a broken read must never stop events
            self._note_progress_failure(exc)
            return None

    def _note_progress_failure(self, exc: Exception) -> None:
        """Count every failure; log at WARNING at most once per PROGRESS_LOG_INTERVAL_S.

        Only the listener thread publishes, so `_progress_logged_at` needs no lock.
        """
        now = self._clock()
        last = self._progress_logged_at
        loud = last is None or now - last >= PROGRESS_LOG_INTERVAL_S
        if loud:
            self._progress_logged_at = now
        swallowed(log, SCAN_PROGRESS_TAG, exc,
                  "scan event sent without progress: the progress read failed",
                  level=logging.WARNING if loud else logging.DEBUG)
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_broker.py`
Expected: all pass, `0 failed`.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_event_stream.py`
Expected: all pass, `0 failed` (the admin `client` fixture seeds the account store: the shared `swing-db` must be up; run `/replicate-prod-db` first if no task in this session has).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_broker_db_listener.py`
Expected: all pass, `0 failed`. These build `EventBroker()` with the default reader against the test database; a `scan` read there either succeeds or goes thin, and no assertion depends on which.

- [ ] **Step 7: Complexity after**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: passes; `publish` ~5, `_scan_progress` 2, `_note_progress_failure` 3, `Event.data` 2, `_default_progress_reader` 1.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/admin/events/broker.py tests/admin/test_event_broker.py tests/admin/test_event_stream.py
git -C "<wt>" commit -m "feat(v206): scan events carry the progress strip's payload, read once per publish (V206-6)"
```

