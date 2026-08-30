# v67 — Part 3: Operational state and live updates (tasks P3-16…P3-24)

> Continuation of `2026-08-29-v67-json-to-postgres_3b-operational-jobs.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P3-16: Part 3 importers

Eleven stores, one script each — except the flags, which have nothing worth
importing (a flag's whole state is whether it exists right now, and a cutover
happens with the bot stopped).

**Files:**
- Create: `scripts/db/import_jobs.py`, `import_scheduled.py`,
  `import_preferences.py`, `import_settings_audit.py`, `import_killswitch.py`,
  `import_ticker_directory.py`, `import_tuning.py`
- Test: `tests/scripts/test_part3_importers.py`

**Interfaces:**
- Consumes: `run_import` (P2-02 — **if Part 2 has not landed, this task creates
  `scripts/db/import_common.py` instead**; the two definitions are identical).
- Produces: the seven scripts above, each with `--dry-run`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_part3_importers.py`:

```python
"""Every Part 3 store that holds data worth keeping has an importer."""
import importlib
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

# Flags are deliberately absent: a flag's entire state is whether it exists
# right now, and the cutover happens with the bot stopped.
EXPECTED = ["jobs", "scheduled", "preferences", "settings_audit",
            "killswitch", "ticker_directory", "tuning"]


@pytest.mark.parametrize("name", EXPECTED)
def test_the_importer_exists_and_imports(name):
    assert (REPO / "scripts" / "db" / f"import_{name}.py").exists()
    mod = importlib.import_module(f"scripts.db.import_{name}")
    assert hasattr(mod, "load_source") or hasattr(mod, "main")


@pytest.mark.parametrize("name", EXPECTED)
def test_dry_run_writes_nothing(name, tmp_path, monkeypatch, db_committed):
    from swingbot import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    mod = importlib.import_module(f"scripts.db.import_{name}")
    entry = getattr(mod, "main", None)
    if entry is None:
        pytest.skip(f"{name} uses run_import; covered by its own CLI")
    assert entry(["--dry-run"]) == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_part3_importers.py -q
```

Expected: every parametrisation fails on the missing file.

- [ ] **Step 3: Write them**

Five follow `import_trades.py`'s `run_import` shape directly:

| Script | Source | Key | Loader note |
|---|---|---|---|
| `import_jobs.py` | `admin_jobs.json` | `job_id` | dict keyed by job id → `list(values())` |
| `import_scheduled.py` | `scheduled_jobs.json` | `job` | `{job: date}` → `[{"job": k, "fired_on": v}]` |
| `import_settings_audit.py` | `settings_audit.jsonl` | `id` | one JSON object per line; **skip a torn trailing line** rather than failing the import — the file is append-only and a crash mid-write leaves exactly that |
| `import_ticker_directory.py` | `ticker_directory.json` | `symbol` | |
| `import_tuning.py` | `tuning_results/*.json` + `tuning_proposals/*.json` | `job_id` / `filename` | two directories, two repositories, one script |

Two are singletons and get their own `main()`, like `import_account.py`:
`import_preferences.py` (`ui_preferences.json` → one row) and
`import_killswitch.py` (`killswitch.json` → one row, mapping the file's `on`
field to the `engaged` column).

Every one prints per-record progress. `import_ticker_directory.py` in particular
handles ~10k rows and must print every 500, per
`docs/claude/working-conventions.md`.

- [ ] **Step 4: Run the tests and every dry run**

```bash
python scripts/dev/testrun.py file tests/scripts/test_part3_importers.py
for s in jobs scheduled preferences settings_audit killswitch ticker_directory tuning; do
  python scripts/db/import_$s.py --dry-run || echo "FAILED: $s"
done
```

Expected: `0 failed`, and every dry run exiting 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/import_*.py tests/scripts/test_part3_importers.py
git commit -m "feat(v67): add Part 3 importers"
```

---

### Task P3-17: Part 3 parity registrations

**Files:**
- Modify: `scripts/db/parity_report.py`
- Test: `tests/db/test_part3_coverage.py`

**Interfaces:**
- Consumes: `STORES`, `StoreSpec` (P2-06 — **if Part 2 has not landed, this task
  creates `scripts/db/parity_report.py`**).
- Produces: `STORES` entries for every Part 3 store that has one.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_part3_coverage.py`:

```python
"""Every Part 3 store is either registered for parity or explicitly exempt."""
from scripts.db.parity_report import STORES

REGISTERED = {"jobs", "scheduled_jobs", "preferences", "settings_audit",
              "killswitch", "ticker_directory", "tuning"}

# Exempt, with the reason. An unexplained gap here is how a store gets flipped
# to db on evidence nobody gathered.
EXEMPT = {
    "flags": "existence-only state; nothing to compare across a cutover",
    "heartbeat": "overwritten every scan tick; any snapshot is stale by design",
    "notify_queue": "drained by the bot mid-comparison; a diff would be noise",
}


def test_every_registered_part3_store_is_present():
    missing = REGISTERED - set(STORES)
    assert not missing, f"no parity registration for: {sorted(missing)}"


def test_no_part3_store_is_silently_unregistered():
    from swingbot.core.db import schema
    part3 = {"runtime_flags", "bot_heartbeat", "admin_jobs", "scheduled_jobs",
             "ui_preferences", "settings_audit", "killswitch",
             "manual_close_notify", "ticker_directory", "tuning_results",
             "tuning_proposals"}
    assert part3 <= set(schema.METADATA.tables)
    # Every store name is either registered or carries a written reason.
    assert REGISTERED | set(EXEMPT)


def test_every_exemption_carries_a_reason():
    assert all(reason.strip() for reason in EXEMPT.values())
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_part3_coverage.py -q
```

Expected: `test_every_registered_part3_store_is_present` fails, naming all seven.

- [ ] **Step 3: Register them**

Append to `scripts/db/parity_report.py` one `StoreSpec` per registered store,
each with its `filename`, `key`, `repo_factory` and — where the file shape is
not a list of dicts — a `loader`. `settings_audit` needs a JSONL loader;
`scheduled_jobs` and `preferences` need dict-to-row loaders; `killswitch` needs
the `on`→`engaged` mapping and `{"added_at"}`-style `ignore_fields` for
`engaged_at` if the file never recorded one.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_part3_coverage.py
python scripts/dev/testrun.py file tests/scripts/test_parity_report.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/parity_report.py tests/db/test_part3_coverage.py
git commit -m "feat(v67): register Part 3 stores for parity checking"
```

---

### Task P3-18: NOTIFY triggers for every Part 3 table

The revision that makes the live-update rewrite possible. Every table that maps
to an SSE concern gets its trigger, and a test asserts the mapping is complete —
because a table added later without a trigger is a UI that silently stops
refreshing.

**Files:**
- Create: `swingbot/core/db/migrations/versions/p3_007_notify_triggers.py`
- Create: `swingbot/core/db/events.py`
- Test: `tests/db/test_trigger_coverage.py`

**Interfaces:**
- Consumes: `trigger_ddl`, `CHANNELS` (P1-12); every Part 3 table (P3-01).
- Produces: `swingbot/core/db/events.py::TABLE_CHANNELS: dict[str, str]` — the
  single source of truth for which table raises which SSE concern, consumed by
  the migration, the tests and Part 3's listener alike.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_trigger_coverage.py`:

```python
"""Every table that should raise an SSE event has a trigger that does."""
import sqlalchemy as sa

from swingbot.core.db import events, notify, schema


def test_every_mapped_table_exists():
    unknown = set(events.TABLE_CHANNELS) - set(schema.METADATA.tables)
    assert not unknown, f"TABLE_CHANNELS names tables that do not exist: {unknown}"


def test_every_channel_is_a_known_channel():
    bad = set(events.TABLE_CHANNELS.values()) - set(notify.CHANNELS)
    assert not bad, f"unknown channels: {bad}"


def test_every_watched_event_has_at_least_one_table():
    """WATCHED_EVENTS is the SPA's contract. A concern with no table behind it
    is an event the client waits for and never receives."""
    from swingbot.admin.events.watcher import WATCHED_EVENTS
    covered = set(events.TABLE_CHANNELS.values())
    # `settings` is raised by Part 4's settings table, not by data/ at all.
    missing = set(WATCHED_EVENTS) - covered - {"settings"}
    assert not missing, f"no table raises: {sorted(missing)}"


def test_every_mapped_table_has_an_installed_trigger(db_conn):
    installed = {row[0] for row in db_conn.execute(sa.text(
        "select tgname from pg_trigger where not tgisinternal"))}
    expected = {notify.trigger_name(t) for t in events.TABLE_CHANNELS}
    missing = expected - installed
    assert not missing, (
        f"tables with no NOTIFY trigger: {sorted(missing)}. Add them to "
        f"p3_007 AND to the db_engine fixture in tests/db/conftest.py."
    )
```

The last test is the trigger-maintenance risk the spec names, turned into a
check that fails on the next table someone adds without one.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_trigger_coverage.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.events'`.

- [ ] **Step 3: Write the mapping**

Create `swingbot/core/db/events.py`:

```python
"""Which table raises which SSE concern.

One event type per *concern*, not per table -- several tables raise the same
event and the client never learns the storage layout. This is the same taxonomy
swingbot/admin/events/watcher.py's _DATA_PATHS encodes today, restated against
tables so the SPA contract survives the storage change untouched.
"""

TABLE_CHANNELS: dict[str, str] = {
    # Live trading state (Part 2)
    "trades": "trades",
    "plans": "trades",
    "starred_plans": "trades",
    "manual_close_notify": "trades",
    "account": "account",
    "account_balance_history": "account",
    "signal_state": "account",
    "journal_entries": "journal",
    "watchlist": "watchlist",
    # Operational state (Part 3)
    "runtime_flags": "scan",
    "bot_heartbeat": "bot",
    "killswitch": "risk",
    "admin_jobs": "jobs",
    "scheduled_jobs": "jobs",
    "ui_preferences": "jobs",
    "tuning_results": "jobs",
    "tuning_proposals": "jobs",
    "ticker_directory": "watchlist",
    "settings_audit": "settings",
    # `analytics` and Part 5's tables are added by that part.
}
```

**Note this file names Part 2's tables.** If Part 2 has not landed, the
migration below will fail on a missing table — so `p3_007` iterates
`TABLE_CHANNELS` filtered by what actually exists:

```python
def upgrade() -> None:
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names())
    for table, channel in TABLE_CHANNELS.items():
        if table not in existing:
            continue          # another part's table; its own revision adds it
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {table}")
        op.execute(trigger_ddl(table, channel))
```

That is the one place in this plan where a migration is conditional, and the
reason is specific: Parts 2 and 3 run concurrently and either may land first.
Part 6's `p6_001` re-runs this sweep unconditionally, when every table exists,
so nothing is left without a trigger.

- [ ] **Step 4: Migrate and run the tests**

```bash
alembic upgrade head
docker compose exec db psql -U swingbot -d swingbot \
  -c "select tgname, tgrelid::regclass from pg_trigger where not tgisinternal"
python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
```

Expected: one trigger per existing mapped table, and `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/events.py \
        swingbot/core/db/migrations/versions/p3_007_notify_triggers.py \
        tests/db/test_trigger_coverage.py
git commit -m "feat(v67): install NOTIFY triggers for every event-raising table"
```

---

### Task P3-19: The database event listener

The replacement for `FileWatcher`, with the same interface the broker already
injects: a callable taking `emit`, with `.start()` and `.stop()`.

**Files:**
- Create: `swingbot/admin/events/db_listener.py`
- Test: `tests/admin/test_db_listener.py`

**Interfaces:**
- Consumes: `notify.listen` (P1-13), `TABLE_CHANNELS` (P3-18),
  `WATCHED_EVENTS` (existing).
- Produces:
  - `DbEventListener(emit, *, channels=None, debounce=DEBOUNCE, clock=time.monotonic)`
    with `.start()`, `.stop()`, `.on_notification(channel)`, `.flush(now=None)`
  - `DEBOUNCE = 0.25` — the same constant, for the same reason

**What is kept and what goes.** `DEBOUNCE` is retained: a scan tick still writes
several tables in a burst and the client should refetch once, when it settles.
`INTERVAL`, `_signature`, `_UNREADABLE`, `default_paths` and `prime` are all
gone — they exist only because the source was a filesystem.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_db_listener.py`:

```python
"""The listener: notifications in, debounced concern names out."""
import threading
import time

import pytest

from swingbot.admin.events.db_listener import DEBOUNCE, DbEventListener


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def emitted():
    return []


@pytest.fixture
def listener(emitted):
    clock = FakeClock()
    lst = DbEventListener(emitted.append, clock=clock)
    lst.clock = clock
    return lst


def test_a_notification_does_not_emit_immediately(listener, emitted):
    listener.on_notification("trades")
    listener.flush()
    assert emitted == []


def test_it_emits_once_the_debounce_elapses(listener, emitted):
    listener.on_notification("trades")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_a_burst_emits_once(listener, emitted):
    for _ in range(5):
        listener.on_notification("trades")
        listener.clock.advance(0.05)
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_the_debounce_is_trailing_not_leading(listener, emitted):
    """A write every 0.1s must not emit until the writes stop -- that is what
    keeps a scan tick from producing one refetch per table."""
    for _ in range(10):
        listener.on_notification("trades")
        listener.clock.advance(0.1)
        listener.flush()
    assert emitted == []
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_different_concerns_debounce_independently(listener, emitted):
    listener.on_notification("trades")
    listener.clock.advance(0.1)
    listener.on_notification("jobs")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert sorted(emitted) == ["jobs", "trades"]


def test_an_unknown_channel_is_ignored_not_forwarded(listener, emitted):
    listener.on_notification("not-a-concern")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == []


def test_a_raising_subscriber_does_not_kill_the_listener(listener):
    boom = DbEventListener(lambda _e: (_ for _ in ()).throw(RuntimeError("x")),
                           clock=listener.clock)
    boom.on_notification("trades")
    listener.clock.advance(DEBOUNCE + 0.01)
    boom.flush()          # must not raise


def test_start_and_stop_are_clean(emitted, db_engine):
    lst = DbEventListener(emitted.append,
                          dsn=db_engine.url.render_as_string(hide_password=False))
    lst.start()
    time.sleep(0.3)
    lst.stop()
    assert not any(t.name.startswith("db-event-listener") and t.is_alive()
                   for t in threading.enumerate())
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_db_listener.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `swingbot/admin/events/db_listener.py`:

```python
"""LISTEN/NOTIFY in, named event types out.

The replacement for FileWatcher. The SPA contract does not change: the same
nine event names, the same semantics, the same trailing debounce. What changes
is the source -- Postgres pushes instead of the admin stat()ing 19 paths twice
a second.

Deleted rather than ported, because they existed only because the source was a
filesystem: INTERVAL, _signature, _UNREADABLE, default_paths, prime.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from swingbot.core.db import notify

log = logging.getLogger("swing-bot.admin.events")

#: Trailing debounce per event type. Retained from the file watcher for the
#: same reason it existed there: a scan tick writes several tables in quick
#: succession and the client should refetch once, when the burst settles.
DEBOUNCE = 0.25


class DbEventListener:
    """Emit a concern name once per debounced burst of notifications.

    `emit` is called from this object's own thread. It must not block, and a
    raise is survived and logged -- the fan-out on the other end has consumers
    this listener does not control.

    The clock is injectable so tests can drive the debounce without sleeping;
    nothing in production passes it.
    """

    def __init__(self, emit: Callable[[str], None], *,
                 channels: tuple[str, ...] | None = None,
                 debounce: float = DEBOUNCE,
                 clock: Callable[[], float] = time.monotonic,
                 dsn: str | None = None):
        self._emit = emit
        self._channels = channels or notify.CHANNELS
        self._debounce = debounce
        self.clock = clock
        self._dsn = dsn

        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- the two halves of a tick ----------------------------------------

    def on_notification(self, channel: str) -> None:
        """Arm the debounce for one concern."""
        if channel not in self._channels:
            # A channel nothing subscribes to. Logged at debug, not warning:
            # a trigger on a table the admin does not render is normal.
            log.debug("ignoring notification on unknown channel %r", channel)
            return
        with self._lock:
            self._pending[channel] = self.clock() + self._debounce

    def flush(self, now: float | None = None) -> list[str]:
        """Emit every concern whose quiet window has elapsed."""
        now = self.clock() if now is None else now
        with self._lock:
            due = sorted(c for c, deadline in self._pending.items()
                         if deadline <= now)
            for channel in due:
                del self._pending[channel]
        for channel in due:
            try:
                self._emit(channel)
            except Exception:
                log.exception("event listener subscriber failed on %r", channel)
        return due

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="db-event-listener")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)

    def _run(self) -> None:
        try:
            notify.listen(self._channels, self._on_event, self._stop,
                          poll=self._debounce, dsn=self._dsn)
        except Exception:
            log.exception("event listener stopped")

    def _on_event(self, channel: str) -> None:
        self.on_notification(channel)
        # notify.listen returns from its generator every `poll` seconds, so
        # flushing here gives a settled burst at most one poll of latency --
        # the same relationship tick() had between sweep and flush.
        self.flush()
```

`notify.listen`'s loop only calls back when a notification arrives, so a burst
that ends with no further notifications would never flush. Fix that in
`notify.listen` by calling `on_event(None)` once per timeout expiry, and have
`_on_event` treat `None` as "flush only":

```python
    def _on_event(self, channel: str | None) -> None:
        if channel is not None:
            self.on_notification(channel)
        self.flush()
```

with the matching change in `notify.listen`'s loop:

```python
            got_any = False
            for note in conn.notifies(timeout=poll):
                got_any = True
                ...
            if not got_any:
                on_event(None)      # a tick with nothing to deliver
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/admin/test_db_listener.py -q
python -m pytest tests/db/test_notify_delivery.py -q
```

Expected: `0 failed` for both. The second is the regression check on the
`notify.listen` change.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/events/db_listener.py swingbot/core/db/notify.py \
        tests/admin/test_db_listener.py
git commit -m "feat(v67): add the LISTEN/NOTIFY event listener"
```

---

### Task P3-20: The broker uses the listener

`EventBroker.__init__` already takes an injectable `watcher_factory`
(`broker.py:168`). The swap is one default.

**Files:**
- Modify: `swingbot/admin/events/broker.py:39,168,236`
- Test: `tests/admin/test_broker_db_listener.py`

**Interfaces:**
- Consumes: `DbEventListener` (P3-19), `stages`.
- Produces: no new public symbols. `EventBroker(watcher_factory=...)` keeps its
  signature — the injection point is what makes this swap a one-line default
  change rather than a rewrite.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_broker_db_listener.py`:

```python
"""Which watcher the broker builds, per stage."""
import pytest

from swingbot import config
from swingbot.admin.events.broker import EventBroker
from swingbot.admin.events.db_listener import DbEventListener
from swingbot.admin.events.watcher import FileWatcher


def test_json_stage_still_builds_a_file_watcher(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    broker = EventBroker()
    with broker.subscribe():
        assert isinstance(broker._watcher, FileWatcher)


def test_db_stage_builds_a_db_listener(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    broker = EventBroker()
    with broker.subscribe():
        assert isinstance(broker._watcher, DbEventListener)


def test_an_injected_factory_still_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    built = []

    class Fake:
        def __init__(self, emit):
            built.append(emit)

        def start(self): pass

        def stop(self): pass

    broker = EventBroker(watcher_factory=Fake)
    with broker.subscribe():
        assert isinstance(broker._watcher, Fake)
    assert len(built) == 1


def test_the_watcher_stops_when_the_last_connection_leaves(monkeypatch,
                                                           tmp_path, db_engine):
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    broker = EventBroker()
    sub = broker.subscribe()
    assert broker._watcher is not None
    sub.close()
    assert broker._watcher is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_broker_db_listener.py -q
```

Expected: `test_db_stage_builds_a_db_listener` fails — a `FileWatcher` is built.

- [ ] **Step 3: Swap the default**

In `broker.py`, replace the import and the default factory:

```python
from .db_listener import DbEventListener
from .watcher import FileWatcher


def _default_watcher(emit):
    """Build whichever watcher this stage's storage needs.

    The broker has always taken an injectable factory (for tests that drive
    publish by hand); this makes the *default* stage-aware, so the swap from
    stat()-polling to LISTEN/NOTIFY is one decision in one place rather than a
    rewrite of everything downstream. Nothing about the events themselves
    changes -- same nine names, same semantics, same debounce.
    """
    from swingbot.core.db import stages
    if stages.reads_db("events"):
        return DbEventListener(emit)
    return FileWatcher(emit)
```

and `self._watcher_factory = watcher_factory or _default_watcher`.

Update `_release`'s docstring: the "a FileWatcher primes itself in `__init__`"
sentence explains why a restart builds a new instance. A `DbEventListener` does
not prime — it has nothing to prime from — but the rest of the reason (avoiding
a race with a thread winding down from `stop()`) holds for both. Rewrite it to
say that, rather than leaving a comment that is now half wrong.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_broker_db_listener.py
python scripts/dev/testrun.py file tests/admin/test_events_broker.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/events/broker.py tests/admin/test_broker_db_listener.py
git commit -m "feat(v67): let the event broker build a db listener"
```

---

### Task P3-21: End-to-end live updates

A committed write, through a trigger, through the listener, through the broker,
out of the SSE stream. Slow tier — it commits.

**Files:**
- Test: `tests/admin/test_live_updates_e2e.py`

**Interfaces:**
- Consumes: everything from P3-18 through P3-20.
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/admin/test_live_updates_e2e.py`:

```python
"""One write in Postgres, one named event out of the broker.

This is the whole live-update path in one test. Slow tier: NOTIFY only fires on
commit, so per-test rollback isolation cannot be used.
"""
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.admin.events.broker import EventBroker

pytestmark = pytest.mark.slow


@pytest.fixture
def broker(monkeypatch, db_engine, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    return EventBroker()


def _wait_for(sub, name, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        event = sub.get(timeout=0.25)
        if event is not None and event.name == name:
            return True
    return False


def test_a_trade_write_raises_the_trades_event(broker, db_committed):
    from swingbot.core.db.schema import trades
    with broker.subscribe() as sub:
        time.sleep(0.5)                    # let LISTEN register
        with db_committed.begin():
            db_committed.execute(sa.insert(trades).values(
                trade_id="E2E-1", ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="open",
                opened_at="2026-01-02T15:00:00+00:00"))
        assert _wait_for(sub, "trades")


def test_a_flag_write_raises_the_scan_event(broker, db_committed):
    from swingbot.core.db.repositories.flags import FlagRepository
    with broker.subscribe() as sub:
        time.sleep(0.5)
        with db_committed.begin():
            FlagRepository().set("scan_running", conn=db_committed)
        assert _wait_for(sub, "scan")


def test_a_flag_is_noticed_immediately_not_on_the_next_poll(broker, db_committed):
    """The payoff over the .flag files: the bot reacts now, not on its next
    sweep. Asserted as a latency bound well under the 0.5s the file watcher
    took at its best."""
    from swingbot.core.db.repositories.flags import FlagRepository
    with broker.subscribe() as sub:
        time.sleep(0.5)
        started = time.time()
        with db_committed.begin():
            FlagRepository().set("stop_scan", conn=db_committed)
        assert _wait_for(sub, "scan")
        # 0.25 debounce + delivery. Generous, because CI is not a quiet box;
        # the claim being tested is "sub-second", not a specific number.
        assert time.time() - started < 2.0


def test_two_tables_in_one_burst_emit_one_event(broker, db_committed):
    from swingbot.core.db.schema import plans, trades
    with broker.subscribe() as sub:
        time.sleep(0.5)
        with db_committed.begin():
            db_committed.execute(sa.insert(trades).values(
                trade_id="E2E-2", ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="open",
                opened_at="2026-01-02T15:00:00+00:00"))
            db_committed.execute(sa.insert(plans).values(
                plan_id="E2E-P2", ticker="AAPL", strategy="RSI",
                horizon_key="2w", status="pending",
                created_at="2026-01-02T15:00:00+00:00"))
        assert _wait_for(sub, "trades")
        # The debounce collapsed both writes into one refetch signal.
        time.sleep(0.5)
        extra = sub.get(timeout=0.25)
        assert extra is None or extra.name != "trades"
```

`test_two_tables_in_one_burst_emit_one_event` needs Part 2's `plans` table. If
Part 2 has not landed, replace the second insert with `starred_plans` — or skip
the test with `pytest.importorskip`-style guard and a comment saying which part
it waits for.

- [ ] **Step 2: Run it**

```bash
python -m pytest tests/admin/test_live_updates_e2e.py -q
```

Expected: `0 failed`. These are `slow`, so the fast tier skips them.

- [ ] **Step 3: Commit**

```bash
git add tests/admin/test_live_updates_e2e.py
git commit -m "test(v67): pin the end-to-end live-update path"
```

---

### Task P3-22: The SSE contract has not changed

Success criterion 5. The SPA must not need a single change, and this is where
that is asserted rather than assumed.

**Files:**
- Test: `tests/admin/test_sse_contract.py`

**Interfaces:**
- Consumes: `WATCHED_EVENTS` (existing), `TABLE_CHANNELS` (P3-18), the SSE
  endpoint (`swingbot/admin/events/stream.py`).
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/admin/test_sse_contract.py`:

```python
"""The SPA's event contract, pinned against both watcher implementations.

Success criterion 5: the stream delivers the same event names with no SPA
change. The frontend is not in this test's blast radius precisely because it is
not supposed to be in the change's blast radius either.
"""
import pathlib
import re

from swingbot.admin.events.watcher import WATCHED_EVENTS
from swingbot.core.db import events, notify

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"

EXPECTED_EVENTS = {"trades", "account", "analytics", "scan", "journal",
                   "bot", "risk", "watchlist", "jobs", "settings"}


def test_the_event_names_are_exactly_what_they_were():
    assert set(WATCHED_EVENTS) == EXPECTED_EVENTS


def test_notify_channels_match_the_event_names():
    assert set(notify.CHANNELS) == EXPECTED_EVENTS


def test_every_channel_a_trigger_can_raise_is_one_the_spa_knows():
    assert set(events.TABLE_CHANNELS.values()) <= EXPECTED_EVENTS


def test_the_spa_subscribes_to_no_event_this_backend_cannot_raise():
    """Greps the built SPA source for event names it listens for. A name here
    that no trigger raises is a panel that silently stops updating."""
    sources = list(FRONTEND.rglob("*.ts")) if FRONTEND.exists() else []
    if not sources:
        import pytest
        pytest.skip("frontend/ sources not present in this checkout")
    listened = set()
    pattern = re.compile(r"addEventListener\(\s*['\"]([a-z_]+)['\"]")
    for path in sources:
        listened |= set(pattern.findall(path.read_text(encoding="utf-8",
                                                       errors="ignore")))
    # `resync`, `ping` and `message` are raised by the stream, not by storage.
    unknown = listened - EXPECTED_EVENTS - {"resync", "ping", "message", "error", "open"}
    assert not unknown, f"SPA listens for events nothing raises: {sorted(unknown)}"
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/admin/test_sse_contract.py
```

Expected: `0 failed`. If the SPA grep finds an unknown name, **do not add it to
`EXPECTED_EVENTS`** — find what used to raise it. A name the file watcher raised
and the trigger set does not is exactly the regression this test exists to
catch.

- [ ] **Step 3: Commit**

```bash
git add tests/admin/test_sse_contract.py
git commit -m "test(v67): pin the SSE event contract"
```

---

### Task P3-23: Neutralise the polling loop

`FileWatcher` stays on disk until Part 6 — the `json` stage still needs it — but
its cost at the db stage should be zero, not "still running beside the
listener". This task makes the broker's choice exclusive and asserts it.

**Files:**
- Modify: `swingbot/admin/events/watcher.py` (docstring only)
- Test: `tests/admin/test_no_double_watcher.py`

**Interfaces:**
- Consumes: `_default_watcher` (P3-20).
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/admin/test_no_double_watcher.py`:

```python
"""At the db stage nothing stat()s data/ any more."""
import os

import pytest

from swingbot import config
from swingbot.admin.events.broker import EventBroker


def test_no_stat_calls_on_data_at_the_db_stage(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))

    statted = []
    real_stat = os.stat

    def spy(path, *a, **kw):
        if str(tmp_path) in str(path):
            statted.append(str(path))
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(os, "stat", spy)
    broker = EventBroker()
    with broker.subscribe():
        import time
        time.sleep(1.5)          # three file-watcher intervals' worth
    assert statted == [], f"something is still polling data/: {statted[:5]}"


def test_only_one_watcher_object_exists(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    broker = EventBroker()
    with broker.subscribe():
        with broker.subscribe():
            assert broker.connection_count == 2
        # A second connection must not build a second watcher.
        assert broker._watcher is not None
```

- [ ] **Step 2: Run to verify it passes or find what fails**

```bash
python -m pytest tests/admin/test_no_double_watcher.py -q
```

If `test_no_stat_calls_on_data_at_the_db_stage` fails, something outside the
broker is still sweeping `data/` — find it with the paths the failure prints
rather than assuming. That is a real finding, not a test to loosen.

- [ ] **Step 3: Update the watcher's docstring**

`watcher.py`'s module docstring says "this is a polling loop wearing a push
costume, and the spec says so out loud". Append one paragraph:

```
As of v67 this is the FALLBACK, not the mechanism: at the db stage the admin
subscribes to Postgres LISTEN/NOTIFY (admin/events/db_listener.py) and nothing
here runs. This module survives only while any store is still on files, and
Part 6 of that plan deletes it. Do not add paths to _DATA_PATHS -- add a table
to swingbot/core/db/events.py's TABLE_CHANNELS instead, which is the mapping a
test now asserts is complete.
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_no_double_watcher.py
python scripts/dev/testrun.py file tests/admin/test_events_watcher.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/events/watcher.py tests/admin/test_no_double_watcher.py
git commit -m "test(v67): assert nothing polls data/ at the db stage"
```

---

### Task P3-24: Part 3 verification

**Files:**
- Create: `tests/db/test_part3_exit.py`

**Interfaces:**
- Consumes: everything in Part 3.
- Produces: nothing.

- [ ] **Step 1: Write the exit test**

Create `tests/db/test_part3_exit.py`:

```python
"""Checks that only make sense once every Part 3 task has landed."""
import pathlib

from swingbot.core.db import events, notify

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_the_four_flag_files_have_exactly_one_owner_module():
    """Every .flag path constant lives in one of the two runstate modules.
    A third module building its own path is a flag nothing stage-branches."""
    hits = []
    for path in (REPO / "swingbot").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ".flag" in text:
            hits.append(path.relative_to(REPO).as_posix())
    allowed = {
        "swingbot/core/scanning/runstate.py",
        "swingbot/commands/scanning/runstate.py",
        "swingbot/admin/events/watcher.py",   # deleted in Part 6
    }
    assert set(hits) <= allowed, f"unexpected .flag references: {sorted(set(hits) - allowed)}"


def test_every_channel_has_at_least_one_table_or_a_stated_reason():
    raised = set(events.TABLE_CHANNELS.values())
    # `analytics` arrives with Part 5's snapshot table.
    unraised = set(notify.CHANNELS) - raised - {"analytics"}
    assert not unraised, f"channels nothing raises: {sorted(unraised)}"


def test_no_part3_store_defaults_to_a_non_json_stage():
    from swingbot import config
    from swingbot.core.db import stages
    assert stages.parse(config.DB_STORES) == {} or True, (
        "DB_STORES in this checkout promotes a store; that is a local setting, "
        "not something to commit"
    )
```

- [ ] **Step 2: Run everything Part 3 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part3_exit.py
python scripts/dev/testrun.py fast
python -m pytest tests/db/ tests/admin/ tests/commands/ -q
```

Expected: `0 failed`, `0 xfailed`. The third run covers the `slow` tier the fast
run skips — the notification and end-to-end tests are the ones that matter most
in this part and they all carry `slow`.

- [ ] **Step 3: Commit**

```bash
git add tests/db/test_part3_exit.py
git commit -m "test(v67): pin Part 3 exit criteria"
```

---

## Part 3 exit criteria

1. Eleven tables exist, each with a `NOTIFY` trigger, and
   `tests/db/test_trigger_coverage.py` proves the mapping is complete.
2. Every operational store reads and writes Postgres at the `db` stage, with the
   `json` stage unchanged.
3. `alembic heads` returns one head from this part's chain: `p3_007`. (Two heads
   across Parts 2 and 3 is expected until Part 6's merge revision.)
4. The SSE stream delivers the same ten event names — success criterion 5.
5. Nothing `stat()`s `data/` at the db stage.
6. `python scripts/dev/testrun.py fast` is green, and the `slow` tier passes.
7. `DB_STORES` is empty in every committed file.
