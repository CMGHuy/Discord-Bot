"""v204: the refresher's snapshot worker.

Every snapshot build runs on its own thread under ``ADMIN_SNAPSHOT_BUDGET_S``,
never inline in the quote cycle. Rows land compare-and-set
(``AdminSnapshotRepository.put``), so an abandoned build that finishes late
cannot overwrite a newer row. The worker feeds the admin SPA only and sends
nothing to Discord.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Iterable

from swingbot import config
from swingbot.core.analytics import admin_snapshots
from swingbot.core.db import notify
from swingbot.core.db.repositories.admin_snapshots import admin_snapshot_repo
from swingbot.core.db.repositories.market_refresh import refresh_mark_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared import admin_refresh

if TYPE_CHECKING:  # loop.py imports this module
    from swingbot.refresher.loop import CycleContext  # noqa: F401

log = logging.getLogger(__name__)

WAKE_POLL_S = 1.0


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


@dataclass
class _Progress:
    """How far one batch got: keys finished (in order), keys landed, news to announce."""
    done: list[str] = field(default_factory=list)
    landed: list[str] = field(default_factory=list)
    news: bool = False


class SnapshotWorker:
    """Builds submitted snapshot keys on a background thread, one batch at a time."""

    def __init__(self, *, builders_fn: Callable[[], dict] = admin_snapshots.builders,
                 repo_fn: Callable = admin_snapshot_repo, marks_fn: Callable = refresh_mark_repo,
                 publish: Callable[[str], None] = notify.publish,
                 budget_fn: Callable[[], float] = lambda: config.ADMIN_SNAPSHOT_BUDGET_S,
                 clock: Callable[[], datetime] | None = None) -> None:
        self._builders_fn = builders_fn
        self._repo_fn = repo_fn
        self._marks_fn = marks_fn
        self._publish = publish
        self._budget_fn = budget_fn
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._pending: list[str] = []
        self._active: set[str] = set()
        self._marking: set[str] = set()
        self._abandoned: dict[str, threading.Thread] = {}
        self._landed: list[str] = []
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()  # never self._lock: start() may join the old thread

    # -- public seam -------------------------------------------------------

    def submit(self, keys: Iterable[str]) -> list[str]:
        """Queue every key not already pending, building or abandoned; mark them, then wake.

        Accepted keys sit in ``_marking`` (busy, but not takeable) until their
        mark is written, so no batch can build and clear a key before its mark.
        """
        with self._lock:
            self._abandoned = {k: t for k, t in self._abandoned.items() if t.is_alive()}
            busy = (set(self._pending) | self._active | set(self._abandoned)
                    | self._marking)
            accepted = [k for k in dict.fromkeys(keys) if k not in busy]
            self._marking.update(accepted)
        if accepted:
            self._mark(accepted)
            with self._lock:
                self._marking.difference_update(accepted)
                self._pending.extend(accepted)
            self._wake.set()
        return accepted

    def start(self) -> None:
        """Start the worker thread. A thread a timed-out ``stop`` left finishing
        its batch is joined first (it would exit right after), never reused."""
        with self._start_lock:
            old = self._thread
            if old is not None and old.is_alive():
                if not self._stop.is_set():
                    return
                old.join()
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="snapshot-worker", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def run_batch(self, keys: list[str]) -> list[str]:
        """Build `keys` in order, synchronously; return the ones that landed.

        Anything escaping mid-batch clears the unfinished keys' marks with the
        error and re-raises; keys that landed before it still count and announce.
        """
        progress = _Progress()
        try:
            self._run_keys(keys, progress)
        except Exception as exc:
            self._fail(keys[len(progress.done):], exc)
            progress.news = True
            raise
        finally:
            with self._lock:
                self._landed.extend(progress.landed)
            if progress.news:
                self._announce()
        return progress.landed

    def _run_keys(self, keys: list[str], progress: "_Progress") -> None:
        builders = self._builders_fn()
        with self._lock:
            self._active.update(keys)
        for key in keys:
            outcome = self._run_one(key, builders.get(key))
            with self._lock:
                self._active.discard(key)
            progress.done.append(key)
            if outcome == "landed":
                progress.landed.append(key)
            progress.news = progress.news or outcome != "kept"

    def _fail(self, keys: list[str], exc: BaseException) -> None:
        with self._lock:
            self._active.difference_update(keys)
        for key in keys:
            self._clear(key, error=_describe(exc))

    def drain_landed(self) -> list[str]:
        with self._lock:
            landed, self._landed = self._landed, []
        return landed

    # -- helpers -----------------------------------------------------------

    def _mark(self, keys: list[str]) -> None:
        try:
            self._marks_fn().mark([admin_refresh.snapshot_mark_key(k) for k in keys],
                                  timeout_s=admin_refresh.snapshot_mark_timeout_s(),
                                  now=self._clock())
        except Exception as exc:  # noqa: BLE001 - a lost spinner never stops a build
            swallowed(log, "refresher.snapshot.mark", exc)

    def _clear(self, key: str, error: str | None = None) -> None:
        try:
            self._marks_fn().clear([admin_refresh.snapshot_mark_key(key)], error=error,
                                   now=self._clock())
        except Exception as exc:  # noqa: BLE001
            swallowed(log, "refresher.snapshot.mark", exc)

    def _announce(self) -> None:
        try:
            self._publish("market")
        except Exception as exc:  # noqa: BLE001 - a missed NOTIFY costs one stale screen
            swallowed(log, "refresher.notify", exc)

    def _take(self) -> list[str]:
        with self._lock:
            batch, self._pending = self._pending, []
            self._active.update(batch)
        return batch

    def _run_one(self, key: str, builder) -> str:
        if builder is None:
            self._clear(key, error=f"no builder for {key}")
            return "error"
        self._mark([key])
        budget = float(self._budget_fn())
        box: dict = {}
        thread = threading.Thread(target=self._build_and_put, args=(key, builder, box),
                                  name=f"snapshot-build-{key}", daemon=True)
        thread.start()
        thread.join(budget)
        if thread.is_alive():
            with self._lock:
                self._abandoned[key] = thread
            self._clear(key, error=f"budget exceeded after {budget:g}s")
            log.warning("snapshot %s abandoned: budget exceeded after %gs", key, budget)
            return "error"
        if "exc" in box:
            exc = box["exc"]
            self._clear(key, error=_describe(exc))
            swallowed(log, "refresher.snapshot", exc, level=logging.WARNING)
            return "error"
        self._clear(key)
        return "landed" if box.get("written") else "kept"

    def _build_and_put(self, key: str, builder, box: dict) -> None:
        try:
            res = builder()
            box["written"] = self._repo_fn().put(
                key, res.doc, res.inputs,
                computed_at=datetime.fromisoformat(res.inputs["computed_at"]),
                stale_inputs=res.stale_inputs)
        except Exception as exc:  # noqa: BLE001 - reported by _run_one
            box["exc"] = exc

    def _loop(self) -> None:
        while not self._stop.is_set():
            # Only submit's _wake.set(), sent after its mark landed, starts a batch:
            # a timed poll taking a key mid-mark would let that mark outlive the build.
            if not self._wake.wait(WAKE_POLL_S):
                continue
            self._wake.clear()
            if self._stop.is_set():
                break
            batch = self._take()
            if not batch:
                continue
            try:
                self.run_batch(batch)
            except Exception as exc:  # noqa: BLE001 - the worker thread never dies
                swallowed(log, "refresher.snapshot.worker", exc)
                with self._lock:  # never leave a key stuck as active
                    self._active.difference_update(batch)
