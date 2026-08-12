"""One watcher, many browsers — fan-out, sequencing, and the connection cap.

Spec: `docs/superpowers/specs/2026-08-08-realtime-push-design-v12.md`,
Decisions 4 and 5.

The watcher (NG20) knows how to turn a file modification into an event
type. This module is what stands between it and the SSE endpoint (NG22),
and it exists for one structural reason: **the stat() load must not scale
with the number of open tabs.** A watcher per connection would be the
obvious wiring and would multiply the sweep by every tab the user left
open. So there is one watcher for the process, started lazily on the first
connection, fanning out to a queue per connection.

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
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot.admin.api_v1 import ApiError, iso

from .watcher import FileWatcher

log = logging.getLogger("swing-bot.admin.events")

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

    def data(self) -> dict:
        """The SSE `data:` body -- what changed is the event *name*.

        Deliberately excludes the name itself: it travels in the `event:`
        field, and repeating it here would invite a client to read it from
        the body instead, which breaks `addEventListener` dispatch.
        """
        return {"seq": self.seq, "at": self.at}


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
    """

    def __init__(
        self,
        *,
        watcher_factory=None,
        max_connections: int = MAX_CONNECTIONS,
        queue_limit: int = QUEUE_LIMIT,
    ):
        self._watcher_factory = watcher_factory or (lambda emit: FileWatcher(emit))
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

        Restarting builds a *new* watcher rather than reviving this one.
        A FileWatcher primes itself in `__init__`, so a fresh instance both
        re-reads the disk state that moved while nobody was connected, and
        avoids racing a thread that is still winding down from `stop()`.
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
        """
        with self._lock:
            self._seq += 1
            stamped = Event(
                seq=self._seq,
                event=event,
                at=iso(datetime.now(timezone.utc)),
            )
            targets = list(self._subscriptions)

        for subscription in targets:
            try:
                subscription._offer(stamped)
            except Exception:
                log.exception("failed to deliver %r to an event connection", event)


_BROKER: EventBroker | None = None
_BROKER_LOCK = threading.Lock()


def get_broker() -> EventBroker:
    """The process's broker. One, so there is one watcher."""
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            _BROKER = EventBroker()
        return _BROKER
