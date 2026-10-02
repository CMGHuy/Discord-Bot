"""LISTEN/NOTIFY in, named event types out.

The replacement for the file watcher. The SPA contract does not change: the same
ten event names, the same semantics, the same trailing debounce. What changes
is the source -- Postgres pushes instead of the admin stat()ing 19 paths twice
a second.

Reconnect: a lost connection is retried with doubling backoff (1 s to 30 s) and
announced with one `resync`.

Deleted rather than ported, because they existed only because the source was a
filesystem: INTERVAL, _signature, _UNREADABLE, default_paths, prime.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from swingbot.core.db import notify

log = logging.getLogger(__name__)   # v111: no literal logger names

#: Trailing debounce per event type. Retained from the file watcher for the
#: same reason it existed there: a scan tick writes several tables in quick
#: succession and the client should refetch once, when the burst settles.
DEBOUNCE = 0.25

#: Reconnect backoff in seconds: the first wait, and the cap. Doubles per
#: failed attempt and resets once LISTEN is active again.
RECONNECT_INITIAL = 1.0
RECONNECT_MAX = 30.0


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
                 dsn: str | None = None,
                 listen: Callable[..., None] | None = None,
                 backoff: tuple[float, float] = (RECONNECT_INITIAL, RECONNECT_MAX)):
        self._emit = emit
        self._channels = channels or notify.CHANNELS
        self._debounce = debounce
        self.clock = clock
        self._dsn = dsn
        self._listen = listen or notify.listen
        self._backoff = backoff
        self._delay = backoff[0]
        self._connected_before = False

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
        while not self._stop.is_set():
            try:
                self._listen(self._channels, self._on_event, self._stop,
                             poll=self._debounce, dsn=self._dsn,
                             on_listening=self._on_listening)
                return                      # stop() was called
            except Exception:
                log.warning("event listener lost its database connection; "
                            "reconnecting in %.1fs", self._delay, exc_info=True)
            if self._stop.wait(self._delay):
                return
            self._delay = min(self._delay * 2, self._backoff[1])

    def _on_listening(self) -> None:
        """LISTEN is active. After a reconnect, whatever was NOTIFYed while the
        connection was down is gone for good -- so tell every client to
        refetch (spec: recovery is a resync, never a replay)."""
        self._delay = self._backoff[0]
        if self._connected_before:
            try:
                self._emit("resync")
            except Exception:
                log.exception("event listener subscriber failed on 'resync'")
        self._connected_before = True

    def _on_event(self, channel: str | None) -> None:
        # notify.listen calls back with None once per quiet poll window, so
        # flushing here gives a settled burst at most one poll of latency --
        # the same relationship tick() had between sweep and flush.
        if channel is not None:
            self.on_notification(channel)
        self.flush()
