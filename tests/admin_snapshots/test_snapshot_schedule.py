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
