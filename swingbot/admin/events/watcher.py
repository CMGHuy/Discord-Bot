"""The `data/` file watcher — modification in, named event type out.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v12-realtime-push-design.md`,
Decisions 1, 2, 4 and 5.

This is a polling loop wearing a push costume, and the spec says so out
loud rather than hiding it: the admin `stat()`s ~19 paths twice a second
and the browser gets a push. What that buys is the interval dropping from
the current 5 seconds to sub-second, because a `stat()` sweep is three
orders of magnitude cheaper than the server-rendered HTML fragment the
Jinja UI re-fetches today.

Two properties are load-bearing and easy to erode later, so they are
stated here as well as in the spec:

**It never opens a watched file.** The signature is `(mtime_ns, size)`, or
`None` for absent. That is what makes it immune to a torn trailing line in
an append-only `.jsonl`, to every schema change in the JSON it watches,
and to reading a file mid-write. Adding a parse here to produce a richer
event would trade all of that away -- and the client refetches through the
v1 API anyway, so there is nothing to learn from the bytes.

**Size is compared as well as mtime.** Not redundant: the volume is bind-
mounted (from a Windows host in development, from the host filesystem in
production) and bind mounts can report mtime at one-second granularity.
Two writes inside one granule would otherwise look like none.

`inotify`/`watchdog` were rejected for that same bind-mount reason -- see
the spec. Do not "upgrade" this to them without re-reading Decision 1.

As of v67 this is the FALLBACK, not the mechanism: at the db stage the admin
subscribes to Postgres LISTEN/NOTIFY (admin/events/db_listener.py) and this
watcher runs only over residual_paths() -- the files no table replaces yet
(scan snapshots/telemetry, the analytics snapshot, .env). This module
survives only while any watched file has no table, and Part 6 of that plan
deletes it. Prefer a table in swingbot/core/db/events.py's TABLE_CHANNELS over
a new _DATA_PATHS entry; a new entry here that is table-backed must also go in
_TABLE_BACKED, or it is stat()ed and NOTIFYed twice.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Mapping

from swingbot import config

log = logging.getLogger(__name__)

#: Seconds between `stat()` sweeps. Deliberately not configurable -- spec
#: Decision 1: a knob here is a decision deferred to the user, which is the
#: root cause the design-system sub-project was created to fix.
INTERVAL = 0.5

#: Trailing debounce per event type. A scan tick writes several files in
#: quick succession and the client should refetch once, when the burst
#: settles, rather than on its leading edge.
DEBOUNCE = 0.25

#: A path that cannot be stat-ed complains at most this often, so a
#: permanently broken path cannot flood the log the SPA displays.
LOG_INTERVAL = 60.0

# One event type per *concern*, not per file: several files raise the same
# event and the client never learns the storage layout. Spec v12's taxonomy
# table is the source of truth for this map; `resync` and `ping` are absent
# because the stream raises them, not the filesystem.
_DATA_PATHS: tuple[tuple[str, str], ...] = (
    ("trades.json", "trades"),
    ("plans.json", "trades"),
    ("starred_plans.json", "trades"),
    ("account.json", "account"),
    ("state.json", "account"),
    ("analytics_snapshot.json", "analytics"),
    ("journal.json", "journal"),
    ("scan_running.flag", "scan"),
    ("scan_paused.flag", "scan"),
    ("trigger_check.flag", "scan"),
    ("stop_scan.flag", "scan"),
    ("scan_snapshots.json", "scan"),
    ("scan_telemetry.jsonl", "scan"),
    # Rewritten roughly once a second for the life of a scan and deleted when
    # it ends, so this is the one watched path that moves continuously -- and
    # the debounce below is what keeps that to one event per settled burst.
    ("scan_progress.json", "scan"),
    ("bot_heartbeat.json", "bot"),
    ("killswitch.json", "risk"),
    ("watchlist.json", "watchlist"),
    ("ticker_directory.json", "watchlist"),
    ("admin_jobs.json", "jobs"),
    # A directory. Its mtime moves when a result file is created or removed,
    # which is the whole lifecycle of a tuning result -- an in-place rewrite
    # of one would not move it, but job *progress* lives in admin_jobs.json
    # above, which is watched as a file.
    ("tuning_results", "jobs"),
)

#: Every event type the watcher can raise. The stream adds `resync` and
#: `ping`, which have no file behind them.
WATCHED_EVENTS = frozenset(event for _name, event in _DATA_PATHS) | {"settings"}

# Returned by `_signature` when a path exists but could not be read. Distinct
# from `None`, which means "confirmed absent" and is a legitimate state worth
# raising an event for.
_UNREADABLE = object()


def default_paths() -> dict[str, str]:
    """Absolute path -> event type, resolved against `config` *now*.

    Built per call rather than at import time on purpose: the admin test
    suite points `config.DATA_DIR` at a fresh `tmp_path` per test, and a
    module-level constant would still name whatever directory was
    configured when this module was first imported -- which is how a test
    ends up watching, or writing to, the real project's `data/`.
    """
    paths = {
        os.path.join(config.DATA_DIR, name): event for name, event in _DATA_PATHS
    }
    # The one watched path outside data/. It is what makes the SPA notice
    # that another admin tab, or a hand edit on the server, changed
    # configuration underneath it -- the Jinja UI silently overwrites.
    paths[config.ENV_PATH] = "settings"
    return paths


#: `_DATA_PATHS` names whose store has a `TABLE_CHANNELS` table, so at the
#: `events:db` stage a NOTIFY trigger raises their concern and stat()-ing the
#: file would only duplicate it. Listed explicitly -- not derived -- so a file
#: added to `_DATA_PATHS` later defaults to *residual* (still watched), never
#: to silently dropped. Parts 4/5 shrink the residual set as their tables
#: land; Part 6 deletes it along with this watcher.
_TABLE_BACKED: frozenset[str] = frozenset({
    "trades.json",            # trades
    "plans.json",             # plans
    "starred_plans.json",     # starred_plans
    "account.json",           # account
    "state.json",             # signal_state
    "journal.json",           # journal_entries
    "scan_running.flag",      # runtime_flags
    "scan_paused.flag",       # runtime_flags
    "trigger_check.flag",     # runtime_flags
    "stop_scan.flag",         # runtime_flags
    "bot_heartbeat.json",     # bot_heartbeat
    "killswitch.json",        # killswitch
    "watchlist.json",         # watchlist
    "ticker_directory.json",  # ticker_directory
    "admin_jobs.json",        # admin_jobs
    "tuning_results",         # tuning_results
    "scan_progress.json",     # scan_progress (v116)
})


def residual_paths() -> dict[str, str]:
    """`default_paths()` minus every path a NOTIFY trigger already covers.

    What the file watcher still has to watch beside a `DbEventListener`:
    scan snapshots/telemetry, the analytics snapshot and `.env`,
    none of which has a table yet.

    Drops every `_TABLE_BACKED` file unconditionally -- it does not consult
    each store's own stage. So it is only correct once all those stores are
    at `db`; a store still writing JSON only (e.g. `trades:json`) raises no
    NOTIFY and would go silent. The broker's `_default_watcher` states the
    same ordering constraint for `events:db`.
    """
    table_backed = {os.path.join(config.DATA_DIR, name) for name in _TABLE_BACKED}
    return {
        path: event for path, event in default_paths().items()
        if path not in table_backed
    }


class FileWatcher:
    """Watch a fixed set of paths and emit an event type when one moves.

    `emit` is called with a single event-type string, from the watcher's
    own thread, once per debounced burst. It must not block and must not
    raise -- but a raise is survived and logged, because the fan-out on the
    other end (NG21) has consumers the watcher does not control.

    The clock is injectable so tests can drive the interval and the
    debounce without sleeping; nothing in production passes it.
    """

    def __init__(
        self,
        emit: Callable[[str], None],
        *,
        paths: Mapping[str, str] | None = None,
        interval: float = INTERVAL,
        debounce: float = DEBOUNCE,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._emit = emit
        self._paths = dict(paths) if paths is not None else default_paths()
        self._interval = interval
        self._debounce = debounce
        self._clock = clock

        self._signatures: dict[str, object] = {}
        self._pending: dict[str, float] = {}   # event type -> emit-after
        self._complained_at: dict[str, float] = {}
        self._next_sweep = self._clock()

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self.prime()

    # -- state -----------------------------------------------------------

    def prime(self) -> None:
        """Record the current state without emitting anything.

        Called from `__init__` so that the files already on disk at startup
        -- which is all of them, normally -- do not arrive at the browser as
        a burst of "everything changed" the moment a tab connects.
        """
        self._signatures = {path: self._signature(path) for path in self._paths}
        self._pending.clear()

    def _signature(self, path: str):
        try:
            st = os.stat(path)
        except FileNotFoundError:
            # Most watched paths are absent on a fresh install, and flag
            # files spend most of their life that way. A state, not a fault.
            return None
        except OSError as exc:
            self._complain(path, exc)
            return _UNREADABLE
        return (st.st_mtime_ns, st.st_size)

    def _complain(self, path: str, exc: BaseException) -> None:
        now = self._clock()
        last = self._complained_at.get(path)
        if last is None or now - last >= LOG_INTERVAL:
            self._complained_at[path] = now
            log.warning("event watcher could not stat %s: %s", path, exc, exc_info=exc)

    # -- the two halves of a tick ----------------------------------------

    def sweep(self, now: float | None = None) -> set[str]:
        """`stat()` every path; arm the debounce for each changed concern."""
        now = self._clock() if now is None else now
        dirty: set[str] = set()
        for path, event in self._paths.items():
            signature = self._signature(path)
            if signature is _UNREADABLE:
                # Keep the last known signature. Treating an unreadable path
                # as a change would turn a permissions problem into an
                # endless refetch loop in every open tab.
                continue
            if signature != self._signatures.get(path):
                self._signatures[path] = signature
                dirty.add(event)
        for event in dirty:
            self._pending[event] = now + self._debounce   # trailing: pushed out
        return dirty

    def flush(self, now: float | None = None) -> list[str]:
        """Emit every event whose quiet window has elapsed."""
        now = self._clock() if now is None else now
        due = sorted(
            event for event, deadline in self._pending.items() if deadline <= now
        )
        for event in due:
            del self._pending[event]
            try:
                self._emit(event)
            except Exception:
                log.exception("event watcher subscriber failed on %r", event)
        return due

    def tick(self, now: float | None = None) -> list[str]:
        """One loop iteration: sweep if due, then flush what has settled.

        The two run at different cadences on purpose. Sweeping is the
        expensive half and stays on `INTERVAL`; flushing is free and runs
        every iteration so a settled event is not held back until the next
        sweep, which would put the latency floor at two intervals.
        """
        now = self._clock() if now is None else now
        if now >= self._next_sweep:
            self._next_sweep = now + self._interval
            self.sweep(now)
        return self.flush(now)

    # -- the thread ------------------------------------------------------

    def run(self, *, sleep: Callable[[float], object] | None = None) -> None:
        """Loop until `stop()`. Nothing that happens inside ends it early."""
        if sleep is None:
            sleep = self._stop.wait
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                # A file replaced as it is stat-ed is normal operation. The
                # watcher exiting on it is not: the UI would keep looking
                # live while going permanently stale, which spec v12 names
                # as the worst available outcome.
                log.exception("event watcher tick failed")
            sleep(self._debounce)

    def start(self) -> threading.Thread:
        """Start the loop, or return the thread already running it.

        Idempotent because the broker starts the watcher lazily on the
        first SSE connection: two connections arriving together must not
        produce two `stat()` loops.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._thread
            self._stop.clear()
            # Daemon: an admin shutdown must not wait on this loop, and it
            # holds nothing that needs unwinding.
            self._thread = threading.Thread(
                target=self.run, name="admin-event-watcher", daemon=True
            )
            self._thread.start()
            return self._thread

    def stop(self) -> None:
        self._stop.set()
