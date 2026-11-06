"""One listener, many browsers — fan-out, sequencing, and the connection cap.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v12-realtime-push-design.md`,
Decisions 4 and 5.

The listener (`DbEventListener`) turns Postgres NOTIFYs into event types.
This module is what stands between it and the SSE endpoint (NG22), and it
exists for one structural reason: **the database load must not scale with
the number of open tabs.** A listener per connection would be the obvious
wiring and would hold a Postgres connection per tab. So there is one
listener for the process, started lazily on the first connection, fanning
out to a queue per connection.

The three responsibilities, none of which belong in either neighbour:

- **Lifecycle.** The watcher starts when the first connection arrives and
  stops when the last one leaves, so an admin nobody is looking at costs
  nothing.
- **The sequence counter.** Process-wide and monotonic, incremented once
  per event rather than once per delivery, so two tabs watching the same
  change see the same `id:` and neither sees a gap.
- **The cap.** Eight concurrent connections, because on Werkzeug's threaded
  dev server -- which spec Decision 5 accepts as a pre-existing condition --
  each open stream holds a thread for its whole lifetime.

Nothing here imports Flask. The one HTTP-shaped thing it does is raise
`ApiError` when the cap is hit, which is explained where it happens.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot.admin.api_v1 import ApiError, iso

from .db_listener import DbEventListener
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)


def _default_watcher(emit):
    """One listener per process: LISTEN/NOTIFY for every concern (v116).

    The broker has always taken an injectable factory (for tests that drive
    publish by hand); this is the default. The four sources that stay files
    raise their own NOTIFY (`events.FILE_PUBLISHERS`), so nothing stat()s
    `data/` any more.
    """
    return DbEventListener(emit)


#: Swallowed-error tag for a failed progress read on a `scan` event (v206 P1-b).
SCAN_PROGRESS_TAG = "ops.admin.events.scan_progress"   # = the literal swallowed() call below

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


#: Concurrent event connections. Spec Decision 5: the cap exists so that a
#: reconnect bug in the client leaks visibly and boundedly instead of
#: exhausting the process's threads.
MAX_CONNECTIONS = 8

#: Events held for one connection before its backlog collapses to a single
#: `resync`. Events are thin and debounced at 250ms, so a consumer this far
#: behind is not slow -- it is gone.
QUEUE_LIMIT = 64


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


class Subscription:
    """One connection's queue, plus the broker bookkeeping it owns.

    A context manager because the alternative -- an endpoint remembering to
    close in a `finally` -- is exactly the mistake the connection cap makes
    expensive: eight leaked subscriptions and the admin refuses to stream at
    all until it restarts.
    """

    def __init__(self, broker: "EventBroker", limit: int = QUEUE_LIMIT):
        self._broker = broker
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=limit)
        self._closed = False

    # -- consumer side ---------------------------------------------------

    def get(self, timeout: float | None = None) -> Event | None:
        """The next event, or None if the wait elapsed first.

        `None` rather than raising `queue.Empty`, because the caller (NG22)
        is a generator whose whole loop is "wait a bit, send a ping if
        nothing arrived" -- the empty case is its normal path, not an error.
        """
        try:
            return self._queue.get(timeout=timeout) if timeout else self._queue.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        """Release the slot. Idempotent: the endpoint closes in a `finally`
        and Flask may also close the generator, and the second close must
        not release a slot the *next* connection is already using."""
        if self._closed:
            return
        self._closed = True
        self._broker._release(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- producer side ---------------------------------------------------

    def _offer(self, event: Event) -> None:
        """Queue an event, or collapse the backlog to a `resync`.

        Spec Decision 4 says recovery is a resync and not a replay, and a
        consumer that has fallen this far behind is in precisely the
        position of one that reconnected: its data is stale, and *how* stale
        does not matter, because the events are thin and a refetch fixes any
        amount of it.

        So the two obvious alternatives are both wrong here. Growing the
        queue postpones the problem and adds unbounded memory to a process
        that must not have any. Dropping the newest event silently is worse
        than useless -- the client would be left believing it is current
        while missing the one event that mattered.
        """
        try:
            self._queue.put_nowait(event)
            return
        except queue.Full:
            pass

        drained = 0
        while True:
            try:
                self._queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        try:
            self._queue.put_nowait(Event(seq=event.seq, event="resync", at=event.at))
        except queue.Full:  # pragma: no cover - the queue was just emptied
            pass
        log.warning(
            "event connection fell %d events behind; collapsed to a resync", drained
        )


class EventBroker:
    """The process's single watcher, fanned out to per-connection queues.

    `watcher_factory` is injectable so tests can drive `publish` by hand
    instead of touching the filesystem; nothing in production passes it.
    `progress_reader` and `clock` (v206) are injectable for the same reason.
    """

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

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    @property
    def seq(self) -> int:
        """The last issued sequence number -- a high-water mark, not a claim.

        Read by the stream (NG22) to stamp the `resync` it sends on connect,
        which means "your data is current as of here". It deliberately does
        NOT consume a number: a resync goes to one connection, so issuing a
        fresh seq for it would burn an id every other open connection never
        sees, putting a permanent gap in their streams.
        """
        with self._lock:
            return self._seq

    # -- connections -----------------------------------------------------

    def subscribe(self) -> Subscription:
        """Register a connection and start the watcher if it is the first.

        Raises `ApiError(503, "unavailable")` when the cap is reached.

        That is an HTTP shape in a module that otherwise knows nothing about
        HTTP, and it is deliberate: the cap exists *because* of an HTTP
        constraint (a thread per open stream), and `ApiError` is the one
        exception the v1 app already renders into the spec's error body from
        anywhere in a request. A private `BrokerFull` would need translating
        at the endpoint, and the failure mode of forgetting that translation
        is an HTML 500 delivered to a client that only parses JSON.
        """
        with self._lock:
            if len(self._subscriptions) >= self._max_connections:
                # Logged at warning: with a cap of 8 and a single user, this
                # firing at all means a client reconnect bug, which is the
                # scenario the cap was put here to make visible.
                log.warning(
                    "refusing event connection: %d already open",
                    len(self._subscriptions),
                )
                raise ApiError(
                    "unavailable",
                    f"too many open event connections (limit {self._max_connections})",
                    503,
                )

            subscription = Subscription(self, limit=self._queue_limit)
            self._subscriptions.add(subscription)
            if self._watcher is None:
                self._watcher = self._watcher_factory(self.publish)
                self._watcher.start()
            return subscription

    def _release(self, subscription: Subscription) -> None:
        """Drop a connection, stopping the watcher if it was the last.

        Restarting builds a *new* watcher rather than reviving this one, so
        the restart never races a thread still winding down from `stop()`.
        A DbEventListener has nothing to prime from (a notification sent while
        nobody listened is gone), and the resync every new connection
        receives covers that gap instead.
        """
        with self._lock:
            self._subscriptions.discard(subscription)
            if self._subscriptions or self._watcher is None:
                return
            watcher, self._watcher = self._watcher, None
        watcher.stop()

    # -- events ----------------------------------------------------------

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
        swallowed(log, "ops.admin.events.scan_progress", exc,
                  "scan event sent without progress: the progress read failed",
                  level=logging.WARNING if loud else logging.DEBUG)


_BROKER: EventBroker | None = None
_BROKER_LOCK = threading.Lock()


def get_broker() -> EventBroker:
    """The process's broker. One, so there is one watcher."""
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            _BROKER = EventBroker()
        return _BROKER
