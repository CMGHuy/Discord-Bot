"""Publish a running scan's progress where the admin process can see it.

The bot and the admin are separate containers sharing only `data/`, exactly
as `runstate.py` describes -- so a progress bar in the SPA needs the scan's
in-memory `ScanProgress` written to a file the admin's watcher already
`stat()`s. Nothing here is authoritative: the record is a display artefact,
deleted when the scan ends, and losing it costs a progress bar and nothing
else.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from datetime import datetime, timezone

from swingbot import config

log = logging.getLogger("swing-bot.scan_engine")

#: The published record's filename under `config.DATA_DIR`. Watched by
#: `swingbot/admin/events/watcher.py`, which turns each write into the `scan`
#: SSE event the SPA already listens to.
FILENAME = "scan_progress.json"

#: Seconds between republishes. Comfortably finer than the admin watcher's
#: 0.5s `stat()` sweep plus its 0.25s debounce, so the bar's resolution is
#: set by the watcher rather than by this -- and coarse enough that a scan
#: touching a bind-mounted volume writes once a second, not once a ticker.
INTERVAL = 1.0

#: Each scan phase's slice of one 0-100 scale, as `stage -> (start, end)`.
#:
#: `ScanProgress.done`/`total` are reset at the top of every phase (`fetch.py`
#: for the crawl, `scan_run.py` for the analysis and the alert build), so the
#: tracker's own `pct` runs 0->100 three times per scan. Mapping each phase's
#: local ratio into a band is what turns those three ramps into one bar that
#: only moves forward.
#:
#: The widths are a fixed guess at the phases' relative cost, not a measured
#: one. `_sync_run_scan` already records real per-phase durations into
#: `data/scan_telemetry.jsonl` (see `_finish_phase`), which is where to
#: re-derive these from if the bar's pacing ever looks wrong.
PHASE_BANDS: dict[str, tuple[int, int]] = {
    "crawling data": (0, 40),
    "analyzing": (40, 92),
    "building alerts": (92, 100),
}


def _phase_counts(progress) -> tuple[int, int]:
    """`(done, total)` within the *current* phase, whichever phase that is.

    The alert build keeps its own pair: nothing resets `done`/`total` when
    that phase begins, so they still hold the analysis figures throughout it.
    """
    if progress.stage == "building alerts":
        return progress.alerts_done, progress.alerts_total
    return progress.done, progress.total


def _phase_ratio(progress) -> float:
    """How far through its *own* phase the scan is, in 0..1."""
    done, total = _phase_counts(progress)
    if not total:
        return 0.0
    return min(1.0, done / total)


def snapshot(progress) -> dict:
    """One published record for a `ScanProgress`."""
    start, end = PHASE_BANDS.get(progress.stage, (0, 0))
    done, total = _phase_counts(progress)
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "pct": round(start + _phase_ratio(progress) * (end - start)),
        "stage": progress.stage,
        "current_ticker": progress.current_ticker,
        "done": done,
        "total": total,
        "qualifying_found": progress.qualifying_found,
    }


def path() -> str:
    """Resolved per call, never at import.

    `config.DATA_DIR` is monkeypatched per test and hot-reloaded in
    production; a module-level constant would name whichever directory was
    configured when this module was first imported.
    """
    return os.path.join(config.DATA_DIR, FILENAME)


def publish(progress) -> None:
    """Write `progress`'s record atomically, or log and carry on.

    Never raises: this is called from a background thread beside a scan
    that matters, and a failed progress write must not end that scan.
    """
    target = path()
    tmp = target + ".tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w") as handle:
            json.dump(snapshot(progress), handle)
        # Atomic on both platforms: the admin reads this on a request thread
        # while the bot rewrites it roughly once a second, and a truncating
        # write would give it an empty file to parse.
        os.replace(tmp, target)
    except OSError:
        log.debug("Could not publish scan progress", exc_info=True)


def read() -> dict | None:
    """The current record, or None when no scan is publishing one.

    A corrupt file reads as absent rather than raising -- the caller is the
    admin's scan-status endpoint, and a progress bar is never worth a 500.
    """
    try:
        with open(path()) as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def clear() -> None:
    """Remove the record. Idempotent -- a scan that never published is normal."""
    for candidate in (path(), path() + ".tmp"):
        try:
            os.remove(candidate)
        except OSError:
            pass


@contextlib.contextmanager
def publishing(progress, *, interval: float = INTERVAL):
    """Publish `progress` on a background thread for the life of the block.

    A thread rather than a write at each `progress.done += 1`: those happen
    on the analysis worker threads (`analyze.py`), and putting file I/O
    there would move the scan's hot path onto the disk. Snapshotting from
    outside also needs no lock -- every field is a plain attribute write
    under the GIL, and a torn read costs one stale frame of a progress bar.

    `progress` may be None (`run_scan(progress=None)` is a supported call),
    which makes this a no-op so the call site needs no branch.
    """
    if progress is None:
        yield
        return

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval):
            publish(progress)

    # Before the thread starts, so the record exists the instant the scan
    # does -- the opening crawl is the slowest part and the bar should be up
    # for it, not appear one interval late.
    publish(progress)
    thread = threading.Thread(
        target=_loop, name="scan-progress-publisher", daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval + 1.0)
        # Cleared even when the scan raised: a frozen record left behind is
        # a progress bar that never finishes.
        clear()
