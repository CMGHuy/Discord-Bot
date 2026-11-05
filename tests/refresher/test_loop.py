"""v201: one refresher cycle -- context, steps, heartbeat, prune -- and the lock loop."""
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot.core.db.repositories import market_refresh
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.refresher import __main__ as entry
from swingbot.refresher import loop
from swingbot.refresher.symbols import SymbolSet

UTC = timezone.utc
REGULAR = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


class FakeQueue:
    def __init__(self):
        self.rows, self.pruned = [], []

    def take(self, limit, *, conn=None):
        out, self.rows = self.rows[:limit], self.rows[limit:]
        return out

    def prune(self, older_than, *, conn=None):
        self.pruned.append(older_than)
        return 0


class FakeBeat:
    def __init__(self):
        self.beats = []

    def beat(self, **kw):
        self.beats.append(kw)


@pytest.fixture
def env(monkeypatch):
    queue, beat = FakeQueue(), FakeBeat()
    monkeypatch.setattr(loop, "refresh_queue_repo", lambda: queue)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", lambda: beat)
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet(("AAPL",), ("^GSPC",)))
    monkeypatch.setattr(loop, "_scan_running", lambda: False)
    monkeypatch.setattr(loop, "STEPS", [])
    monkeypatch.setattr(loop, "_last_full", None)
    monkeypatch.setattr(loop.config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(loop.config, "MARKETDATA_LAYER", "on")
    return SimpleNamespace(queue=queue, beat=beat)


def test_cycle_builds_its_context_runs_steps_beats_and_prunes(env):
    env.queue.rows = [{"kind": "quote", "key": "NEW", "priority": 0},
                      {"kind": "snapshot", "key": "risk", "priority": 0}]
    seen = []
    loop.STEPS.append(seen.append)
    report = loop.run_cycle(REGULAR)
    [ctx] = seen
    assert (ctx.session, ctx.symbols.quotes, ctx.symbols.index) == ("regular", ("AAPL",), ("^GSPC",))
    assert (ctx.queued_quotes, ctx.queued_snapshots, ctx.scan_running) == (["NEW"], ["risk"], False)
    assert ctx.report is report and report.cadence_s == 30.0 and report.error is None
    [beat] = env.beat.beats
    assert (beat["session"], beat["cadence_s"], beat["last_error"]) == ("regular", 30.0, None)
    assert env.queue.pruned == [REGULAR - timedelta(seconds=3600)]


def test_a_failing_step_is_recorded_and_later_steps_still_run(env):
    ran = []

    def bad(ctx):
        raise RuntimeError("provider down")
    loop.STEPS.extend([bad, ran.append])
    report = loop.run_cycle(REGULAR)
    assert ran and report.error == "RuntimeError: provider down"
    assert env.beat.beats[-1]["last_error"] == "RuntimeError: provider down"


def test_between_full_cycles_only_the_queue_is_served(env):
    seen = []
    loop.STEPS.append(seen.append)
    for offset in (0, 5, 30):
        loop.run_cycle(REGULAR + timedelta(seconds=offset))
    assert [c.symbols for c in seen] == [
        SymbolSet(("AAPL",), ("^GSPC",)), SymbolSet((), ()), SymbolSet(("AAPL",), ("^GSPC",))]


def test_cadence_follows_the_session(env):
    assert loop.run_cycle(datetime(2026, 10, 31, 15, 0, tzinfo=UTC)).cadence_s == 1800.0
    assert loop.run_cycle(datetime(2026, 10, 28, 12, 0, tzinfo=UTC)).session == "extended"


def test_db_down_still_returns_a_report(env, monkeypatch):
    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(loop, "symbol_set", down)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", down)
    report = loop.run_cycle(REGULAR)
    assert report.error == "RuntimeError: db down" and report.session == "regular"


def test_missing_tables_never_end_the_cycle(env, monkeypatch):
    import sqlalchemy as sa

    def no_table(*_a, **_k):
        raise sa.exc.ProgrammingError("SELECT", {}, Exception('relation "market_refresh_queue" does not exist'))
    monkeypatch.setattr(env.queue, "take", no_table)
    monkeypatch.setattr(env.queue, "prune", no_table)
    report = loop.run_cycle(REGULAR)
    assert report.error.startswith("ProgrammingError") and env.beat.beats


def test_inner_tick_reloads_env_and_returns_when_the_queue_has_work(monkeypatch):
    import time
    reloads, ticks = [], []
    pending = iter([False, False, True])
    monkeypatch.setattr(loop, "_reload_if_env_changed", lambda: reloads.append(1))
    monkeypatch.setattr(loop, "_queue_pending", lambda: next(pending))
    monkeypatch.setattr(loop, "_wait", lambda stop, seconds: ticks.append(seconds))
    monkeypatch.setattr(loop.session, "session_state", lambda now=None: "closed")   # 1800 s cadence
    loop._sleep_until_due(threading.Event(), time.monotonic())
    assert ticks == [loop.QUEUE_POLL_S] * 3 and len(reloads) == 3


def test_second_instance_does_not_fetch(monkeypatch):
    cycles, waits = [], []

    @contextmanager
    def refused():
        yield False
    monkeypatch.setattr(loop.lock, "single_instance", refused)
    monkeypatch.setattr(loop, "run_cycle", lambda now=None: cycles.append(now))
    monkeypatch.setattr(loop, "_wait", lambda stop, seconds: (waits.append(seconds), stop.set()))
    loop.run_forever(threading.Event())
    assert cycles == [] and waits == [loop.LOCK_RETRY_S]


def test_heartbeat_key_matches_the_contract():
    assert market_refresh.HEARTBEAT_KEY == admin_refresh.HEARTBEAT_KEY == "refresher"


def test_main_runs_the_loop_with_a_stop_event(monkeypatch):
    got = []
    monkeypatch.setattr(entry.loop, "run_forever", got.append)
    assert entry.main() == 0 and isinstance(got[0], threading.Event)


def test_cycle_report_carries_the_ledger_fields_and_defaults():
    import dataclasses
    report = loop.CycleReport("regular", 30.0)
    assert [f.name for f in dataclasses.fields(report)] == [
        "session", "cadence_s", "quotes_ok", "quotes_missed", "fallback_used",
        "snapshots_written", "error", "changed"]
    assert (report.quotes_ok, report.quotes_missed, report.fallback_used,
            report.snapshots_written, report.error, report.changed) == ((), (), 0, (), None, False)


def test_symbol_set_failure_leaves_the_queue_untouched(env, monkeypatch):
    env.queue.rows = [{"kind": "quote", "key": "NEW", "priority": 0}]

    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(loop, "symbol_set", down)
    report = loop.run_cycle(REGULAR)
    assert report.error == "RuntimeError: db down"
    assert env.queue.rows == [{"kind": "quote", "key": "NEW", "priority": 0}]


@pytest.mark.parametrize("attr,value", [("ADMIN_REFRESHER", "off"), ("MARKETDATA_LAYER", "off")])
def test_kill_switch_idles_the_cycle_but_keeps_the_heartbeat(env, monkeypatch, attr, value):
    monkeypatch.setattr(loop.config, attr, value)
    env.queue.rows = [{"kind": "quote", "key": "NEW", "priority": 0}]
    seen = []
    loop.STEPS.append(seen.append)
    report = loop.run_cycle(REGULAR)
    assert seen == []
    assert len(env.queue.rows) == 1  # the queue is not drained
    assert len(env.beat.beats) == 1 and report.error is None


def test_flipping_the_kill_switch_back_on_resumes_the_steps(env, monkeypatch):
    seen = []
    loop.STEPS.append(seen.append)
    monkeypatch.setattr(loop.config, "ADMIN_REFRESHER", "off")
    loop.run_cycle(REGULAR)
    assert seen == []
    monkeypatch.setattr(loop.config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(loop.config, "MARKETDATA_LAYER", "on")
    loop.run_cycle(REGULAR + timedelta(seconds=1))
    assert len(seen) == 1
