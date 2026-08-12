"""NG20 — the data/ file watcher behind the SSE stream.

NG19 TRIAGE: KEEP unchanged. This tests `swingbot/admin/events/watcher.py`,
which has no Jinja involvement at all and survives the cutover untouched.

Spec: `docs/superpowers/specs/2026-08-08-realtime-push-design-v12.md`,
Decisions 2 (never parse; compare `(exists, mtime, size)`) and 4 (250ms
trailing debounce, per event type).

Every test drives the watcher through an injected clock rather than
sleeping. A watcher test that waits on wall-clock time is both slow and
flaky under `-n 4`: the sweep interval is 500ms, so asserting "no event
yet" against real time means racing the scheduler for the right to be
correct. The clock is a constructor parameter for exactly this reason.
"""
import io
import logging
import os

import pytest

from swingbot import config
from swingbot.admin.events import watcher as w


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self, start: float = 1000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def atomic_write(path, text: str = "{}") -> None:
    """Write the way every store in this repo writes -- tmp file, os.replace.

    The watcher's whole safety argument (spec Decision 2) rests on writes
    landing as a rename, so the tests exercise that path rather than a
    plain `open(...).write()` which would tear.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A DATA_DIR the watcher's default path map resolves against."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ENV_PATH", str(tmp_path / ".env"))
    return tmp_path


@pytest.fixture
def recorder():
    events: list[str] = []
    return events


def make_watcher(clock, recorder, **kwargs):
    return w.FileWatcher(recorder.append, clock=clock, **kwargs)


def settle(watcher, clock, recorder):
    """Advance past one sweep + one debounce window and drain."""
    clock.advance(w.INTERVAL)
    watcher.tick()
    clock.advance(w.DEBOUNCE)
    watcher.tick()
    return recorder


# --------------------------------------------------------------------------
# The path map
# --------------------------------------------------------------------------

def test_default_paths_realise_the_spec_taxonomy(data_dir):
    paths = w.default_paths()

    assert set(paths.values()) == w.WATCHED_EVENTS
    assert w.WATCHED_EVENTS == {
        "trades", "account", "analytics", "journal", "scan",
        "bot", "risk", "universe", "jobs", "settings",
    }

    # Several files, one concern -- the client must not learn the storage
    # layout (spec Decision 3, "one event type per concern, not per file").
    trades_paths = {os.path.basename(p) for p, e in paths.items() if e == "trades"}
    assert trades_paths == {"trades.json", "plans.json", "starred_plans.json"}

    scan_paths = {os.path.basename(p) for p, e in paths.items() if e == "scan"}
    assert scan_paths == {
        "scan_running.flag", "scan_paused.flag", "trigger_check.flag",
        "stop_scan.flag", "scan_snapshots.json", "scan_telemetry.jsonl",
    }


def test_default_paths_are_read_from_config_at_call_time(data_dir, tmp_path):
    """No import-time baking -- conftest patches DATA_DIR per test."""
    assert w.default_paths()[str(tmp_path / "trades.json")] == "trades"
    assert w.default_paths()[str(tmp_path / ".env")] == "settings"


def test_env_is_the_only_watched_path_outside_data_dir(data_dir, tmp_path):
    outside = [p for p in w.default_paths() if os.path.dirname(p) != str(tmp_path)]
    assert outside == []
    assert w.default_paths()[config.ENV_PATH] == "settings"


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def test_priming_means_pre_existing_files_raise_nothing(tmp_path, clock, recorder):
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")

    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})
    settle(watcher, clock, recorder)

    assert recorder == []


def test_an_atomic_write_raises_the_mapped_event(tmp_path, clock, recorder):
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    atomic_write(target, '[{"id": 1}]')
    settle(watcher, clock, recorder)

    assert recorder == ["trades"]


def test_a_quiet_sweep_raises_nothing(tmp_path, clock, recorder):
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    for _ in range(4):
        settle(watcher, clock, recorder)

    assert recorder == []


def test_creation_and_deletion_both_raise(tmp_path, clock, recorder):
    flag = tmp_path / "scan_running.flag"
    watcher = make_watcher(clock, recorder, paths={str(flag): "scan"})

    flag.write_text("", encoding="utf-8")
    settle(watcher, clock, recorder)
    assert recorder == ["scan"]

    flag.unlink()
    settle(watcher, clock, recorder)
    assert recorder == ["scan", "scan"]


def test_identical_mtime_with_a_different_size_is_still_detected(
    tmp_path, clock, recorder
):
    """Spec's coarse-mtime risk: bind mounts can round mtime to a second.

    Size is compared *because* of this, so pin it with a write that keeps
    mtime fixed by hand -- otherwise the assertion passes on mtime alone
    and the size comparison could be deleted without a test noticing.
    """
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    frozen = os.stat(target).st_mtime
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    atomic_write(target, '[{"id": 1, "ticker": "AAPL"}]')
    os.utime(target, (frozen, frozen))
    assert os.stat(target).st_mtime == frozen

    settle(watcher, clock, recorder)
    assert recorder == ["trades"]


def test_the_watcher_never_opens_a_watched_file(tmp_path, clock, recorder, monkeypatch):
    """Decision 2: it compares stat output and nothing more.

    A torn `.jsonl` tail or a schema change must be incapable of reaching
    it, and the only way to guarantee that is to never read the bytes.
    The append here leaves the file with a half-written final line -- the
    exact shape that would break a parsing watcher.
    """
    target = tmp_path / "scan_telemetry.jsonl"
    target.write_text('{"a": 1}\n', encoding="utf-8")
    watcher = make_watcher(clock, recorder, paths={str(target): "scan"})

    target.write_text('{"a": 1}\n{"b": 2', encoding="utf-8")  # torn tail, on purpose

    real_open = io.open

    def refuse(path, *args, **kwargs):
        if str(path) == str(target):
            raise AssertionError(f"the watcher opened {path}")
        return real_open(path, *args, **kwargs)

    # Both names: `builtins.open` is `io.open`, but they are separate module
    # attributes and pathlib reaches for the io one.
    monkeypatch.setattr("builtins.open", refuse)
    monkeypatch.setattr(io, "open", refuse)

    settle(watcher, clock, recorder)

    assert recorder == ["scan"]


# --------------------------------------------------------------------------
# Debounce and coalescing
# --------------------------------------------------------------------------

def test_a_burst_across_one_concern_coalesces_to_one_event(
    tmp_path, clock, recorder
):
    """A scan tick writes trades.json, plans.json and starred_plans.json.

    The client should refetch once, not three times.
    """
    paths = {}
    for name in ("trades.json", "plans.json", "starred_plans.json"):
        target = tmp_path / name
        atomic_write(target, "[]")
        paths[str(target)] = "trades"
    watcher = make_watcher(clock, recorder, paths=paths)

    for name in ("trades.json", "plans.json", "starred_plans.json"):
        atomic_write(tmp_path / name, '[{"id": 1}]')
    settle(watcher, clock, recorder)

    assert recorder == ["trades"]


def test_distinct_concerns_are_not_coalesced(tmp_path, clock, recorder):
    trades = tmp_path / "trades.json"
    account = tmp_path / "account.json"
    for target in (trades, account):
        atomic_write(target, "{}")
    watcher = make_watcher(
        clock, recorder, paths={str(trades): "trades", str(account): "account"}
    )

    atomic_write(trades, '[{"id": 1}]')
    atomic_write(account, '{"balance": 1}')
    settle(watcher, clock, recorder)

    assert sorted(recorder) == ["account", "trades"]


def test_the_debounce_is_trailing_not_leading(tmp_path, clock, recorder):
    """Emit when the burst settles, not the instant it starts."""
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    atomic_write(target, '[{"id": 1}]')
    clock.advance(w.INTERVAL)
    watcher.tick()
    assert recorder == [], "emitted on the leading edge"

    clock.advance(w.DEBOUNCE - 0.01)
    watcher.tick()
    assert recorder == [], "emitted before the quiet window elapsed"

    clock.advance(0.02)
    watcher.tick()
    assert recorder == ["trades"]


def test_continued_writes_extend_the_quiet_window(tmp_path, clock, recorder):
    """A write inside the window pushes the deadline out rather than
    emitting on the old one -- that is what 'trailing' means."""
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(
        clock, recorder, paths={str(target): "trades"},
        interval=0.05, debounce=0.25,
    )

    for i in range(4):
        atomic_write(target, "x" * (i + 1))
        clock.advance(0.05)
        watcher.tick()
    assert recorder == []

    clock.advance(0.25)
    watcher.tick()
    assert recorder == ["trades"]


def test_the_sweep_runs_on_the_interval_not_on_every_tick(
    tmp_path, clock, recorder, monkeypatch
):
    """The loop ticks at the debounce granularity so a due event can be
    flushed promptly; the stat() sweep must still cost only 2/second."""
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    sweeps = []
    monkeypatch.setattr(watcher, "sweep", lambda now=None: sweeps.append(now))

    for _ in range(10):
        clock.advance(w.DEBOUNCE)
        watcher.tick()

    # 10 ticks * 250ms = 2.5s of clock, at one sweep per 500ms.
    assert len(sweeps) == 5


# --------------------------------------------------------------------------
# Survival
# --------------------------------------------------------------------------

def test_a_stat_failure_is_survived_and_does_not_raise_an_event(
    tmp_path, clock, recorder, monkeypatch, caplog
):
    """A file replaced mid-stat is normal. So is one the admin cannot read.

    Neither may kill the thread, and neither may be reported as a change:
    the last known signature stands until the path is readable again.
    """
    broken = tmp_path / "killswitch.json"
    healthy = tmp_path / "trades.json"
    atomic_write(broken, "{}")
    atomic_write(healthy, "[]")
    watcher = make_watcher(
        clock, recorder,
        paths={str(broken): "risk", str(healthy): "trades"},
    )

    real_stat = os.stat

    def fail_on_broken(path, *args, **kwargs):
        if str(path) == str(broken):
            raise PermissionError(13, "Permission denied")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", fail_on_broken)

    atomic_write(healthy, '[{"id": 1}]')
    with caplog.at_level(logging.WARNING, logger=w.log.name):
        settle(watcher, clock, recorder)

    assert recorder == ["trades"], "an unreadable path must not look like a change"
    assert any(str(broken) in r.getMessage() for r in caplog.records)


def test_an_unreadable_path_logs_at_most_once_per_minute(
    tmp_path, clock, recorder, monkeypatch, caplog
):
    """A permanently missing path must not flood the log the SPA displays."""
    broken = tmp_path / "killswitch.json"
    atomic_write(broken, "{}")
    watcher = make_watcher(clock, recorder, paths={str(broken): "risk"})

    real_stat = os.stat

    def fail_on_broken(path, *args, **kwargs):
        if str(path) == str(broken):
            raise PermissionError(13, "Permission denied")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", fail_on_broken)

    def complaints():
        return [r for r in caplog.records if r.name == w.log.name]

    with caplog.at_level(logging.WARNING, logger=w.log.name):
        for _ in range(40):  # 20 seconds of sweeps
            clock.advance(w.INTERVAL)
            watcher.tick()
        assert len(complaints()) == 1

        for _ in range(120):  # past the minute
            clock.advance(w.INTERVAL)
            watcher.tick()
        assert len(complaints()) == 2


def test_a_missing_file_is_not_an_error(tmp_path, clock, recorder, caplog):
    """Most watched paths are absent on a fresh install. That is a state,
    not a failure, and it must not log."""
    watcher = make_watcher(
        clock, recorder, paths={str(tmp_path / "never_written.json"): "risk"}
    )
    with caplog.at_level(logging.WARNING, logger=w.log.name):
        for _ in range(10):
            settle(watcher, clock, recorder)

    assert recorder == []
    assert [r for r in caplog.records if r.name == w.log.name] == []


def test_a_failing_subscriber_does_not_stop_later_events(tmp_path, clock):
    """Fan-out is someone else's problem (NG21); the watcher must not die
    because one consumer did."""
    delivered = []

    def emit(event):
        delivered.append(event)
        if len(delivered) == 1:
            raise RuntimeError("subscriber exploded")

    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = w.FileWatcher(emit, paths={str(target): "trades"}, clock=clock)

    atomic_write(target, '[{"id": 1}]')
    settle(watcher, clock, delivered)
    atomic_write(target, '[{"id": 2}]')
    settle(watcher, clock, delivered)

    assert delivered == ["trades", "trades"]


def test_the_run_loop_survives_a_tick_exception(tmp_path, clock, recorder, monkeypatch):
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    calls = {"n": 0}
    real_tick = watcher.tick

    def flaky(now=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient")
        if calls["n"] >= 3:
            watcher.stop()
        return real_tick(now)

    monkeypatch.setattr(watcher, "tick", flaky)
    watcher.run(sleep=lambda _seconds: None)

    assert calls["n"] >= 3, "the loop died on the first exception"


def test_start_returns_a_running_daemon_thread(tmp_path, clock, recorder):
    """Spec Decision 5: daemon, so it cannot hold the admin process open."""
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    thread = watcher.start()
    try:
        assert thread.daemon is True
        assert thread.is_alive()
    finally:
        watcher.stop()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_start_is_idempotent(tmp_path, clock, recorder):
    """NG21 starts the watcher lazily on the first connection; a race
    between two connections must not produce two stat loops."""
    target = tmp_path / "trades.json"
    atomic_write(target, "[]")
    watcher = make_watcher(clock, recorder, paths={str(target): "trades"})

    first = watcher.start()
    try:
        assert watcher.start() is first
    finally:
        watcher.stop()
        first.join(timeout=5)
