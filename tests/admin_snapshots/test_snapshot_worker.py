"""v204: the snapshot worker builds on its own thread, under a budget, and lands compare-and-set."""
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot.core.analytics.admin_snapshots import SnapshotResult
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable
from swingbot.core.marketdata.shared import admin_refresh as ar
from swingbot.refresher.snapshot_job import SnapshotWorker

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
KEYS = ["risk", "analytics.snapshot"]


def result(doc, at=T0, stale=False):
    return SnapshotResult(doc=doc, inputs={"computed_at": at.isoformat()}, stale_inputs=stale)


class Rows:
    """Compare-and-set like AdminSnapshotRepository.put: an equal or older computed_at writes nothing."""

    def __init__(self):
        self.rows = {}

    def put(self, key, doc, inputs, *, computed_at, stale_inputs):
        old = self.rows.get(key)
        if old is not None and old["computed_at"] >= computed_at:
            return False
        self.rows[key] = {"doc": doc, "computed_at": computed_at, "stale_inputs": stale_inputs}
        return True


class Marks:
    def __init__(self):
        self.calls = []
        self.broken = False

    def mark(self, keys, *, timeout_s, now=None):
        if self.broken:
            raise RuntimeError("db down")
        self.calls.append(("mark", tuple(keys), timeout_s))

    def clear(self, keys, *, error=None, now=None):
        self.calls.append(("clear", tuple(keys), error))


def make(budget=2.0, publish=None):
    env = SimpleNamespace(rows=Rows(), marks=Marks(), published=[], builders={})
    env.w = SnapshotWorker(builders_fn=lambda: env.builders, repo_fn=lambda: env.rows,
                           marks_fn=lambda: env.marks, publish=publish or env.published.append,
                           budget_fn=lambda: budget, clock=lambda: T0)
    return env


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_landed_keys_are_put_cleared_and_published_once():
    env = make()
    env.builders.update({"risk": lambda: result({"heat": 1}),
                         "analytics.snapshot": lambda: result({"overall": {}})})
    assert env.w.run_batch(KEYS) == KEYS
    timeout = ar.snapshot_mark_timeout_s()
    assert env.marks.calls == [("mark", ("snapshot:risk",), timeout), ("clear", ("snapshot:risk",), None),
                               ("mark", ("snapshot:analytics.snapshot",), timeout),
                               ("clear", ("snapshot:analytics.snapshot",), None)]
    assert env.rows.rows["risk"]["doc"] == {"heat": 1}
    assert env.published == ["market"]
    assert env.w.drain_landed() == KEYS and env.w.drain_landed() == []


def test_failing_build_keeps_previous_row_and_clears_mark_with_error():
    env = make()
    env.rows.put("risk", {"heat": "previous"}, {}, computed_at=T0 - timedelta(minutes=5), stale_inputs=False)

    def unmounted():
        raise DailyCacheUnavailable("daily bar cache /app/market_data is not mounted")
    env.builders["risk"] = unmounted
    assert env.w.run_batch(["risk"]) == []
    assert env.rows.rows["risk"]["doc"] == {"heat": "previous"}
    assert ("clear", ("snapshot:risk",),
            "DailyCacheUnavailable: daily bar cache /app/market_data is not mounted") in env.marks.calls
    assert env.published == ["market"]                 # an error is news for the spinner too


def test_overrun_is_abandoned_and_late_result_cannot_overwrite():
    env = make(budget=0.05)
    release = threading.Event()

    def slow():
        release.wait(5.0)
        return result({"v": "late"}, at=T0)
    env.builders["risk"] = slow
    assert env.w.run_batch(["risk"]) == []
    assert ("clear", ("snapshot:risk",), "budget exceeded after 0.05s") in env.marks.calls
    assert env.w.submit(["risk"]) == []                # its build thread is still alive
    env.rows.put("risk", {"v": "newer"}, {}, computed_at=T0 + timedelta(minutes=1), stale_inputs=False)
    release.set()
    assert wait_until(lambda: not any(t.name == "snapshot-build-risk" for t in threading.enumerate()))
    assert env.rows.rows["risk"]["doc"] == {"v": "newer"}
    assert env.w.submit(["risk"]) == ["risk"]          # thread gone: the key is accepted again


def test_submit_dedupes_marks_accepted_keys_and_never_builds():
    env = make()
    env.builders["risk"] = lambda: pytest.fail("submit built inline")
    assert env.w.submit(["risk", "risk", "analytics.snapshot"]) == KEYS
    assert env.marks.calls == [("mark", ("snapshot:risk", "snapshot:analytics.snapshot"),
                                ar.snapshot_mark_timeout_s())]
    assert env.w.submit(["risk"]) == []                # already pending
    assert env.rows.rows == {}


def test_unknown_key_is_cleared_with_an_error():
    env = make()
    assert env.w.run_batch(["calendar.pnl:2020-01"]) == []
    assert env.marks.calls == [("clear", ("snapshot:calendar.pnl:2020-01",),
                                "no builder for calendar.pnl:2020-01")]


def test_older_result_is_kept_out_and_raises_no_event():
    env = make()
    env.rows.put("risk", {"v": "newer"}, {}, computed_at=T0 + timedelta(minutes=1), stale_inputs=False)
    env.builders["risk"] = lambda: result({"v": "older"}, at=T0)
    assert env.w.run_batch(["risk"]) == []
    assert env.rows.rows["risk"]["doc"] == {"v": "newer"}
    assert env.marks.calls[-1] == ("clear", ("snapshot:risk",), None) and env.published == []


def test_publish_failure_never_raises():
    def broken(channel):
        raise RuntimeError("notify down")
    env = make(publish=broken)
    env.builders["risk"] = lambda: result({"heat": 1})
    assert env.w.run_batch(["risk"]) == ["risk"]


def test_mark_failure_never_stops_the_build():
    env = make()
    env.marks.broken = True
    env.builders["risk"] = lambda: result({"heat": 1})
    assert env.w.submit(["risk"]) == ["risk"]
    assert env.w.run_batch(["risk"]) == ["risk"]


def test_started_worker_builds_submitted_keys_off_the_caller_thread():
    env = make()
    seen = []

    def build():
        seen.append(threading.current_thread().name)
        time.sleep(0.2)
        return result({"heat": 1})
    env.builders["risk"] = build
    env.w.start()
    env.w.start()                                       # a second start is a no-op
    landed = []
    try:
        began = time.monotonic()
        assert env.w.submit(["risk"]) == ["risk"]
        assert time.monotonic() - began < 0.1           # submit never waits for a build
        assert wait_until(lambda: landed.extend(env.w.drain_landed()) or landed == ["risk"])
    finally:
        env.w.stop()
    assert seen == ["snapshot-build-risk"]
    assert not any(t.name == "snapshot-worker" and t.is_alive() for t in threading.enumerate())


def _worker_alive():
    return any(t.name == "snapshot-worker" and t.is_alive() for t in threading.enumerate())


def test_timed_poll_never_takes_a_key_whose_mark_is_still_in_flight(monkeypatch):
    from swingbot.refresher import snapshot_job
    monkeypatch.setattr(snapshot_job, "WAKE_POLL_S", 0.01)
    env = make()
    entered, release = threading.Event(), threading.Event()
    plain_mark = env.marks.mark

    def slow_mark(keys, *, timeout_s, now=None):
        if not entered.is_set():                        # only submit's mark blocks
            entered.set()
            release.wait(5.0)
        plain_mark(keys, timeout_s=timeout_s, now=now)
    env.marks.mark = slow_mark
    built = []
    env.builders["risk"] = lambda: built.append(1) or result({"heat": 1})
    env.w.start()
    try:
        submitter = threading.Thread(target=env.w.submit, args=(["risk"],))
        submitter.start()
        assert entered.wait(5.0)
        time.sleep(0.1)                                 # many timed polls pass while mark blocks
        assert built == []
        release.set()
        submitter.join(5.0)
        assert wait_until(lambda: env.w.drain_landed() == ["risk"])
    finally:
        env.w.stop()
    assert env.marks.calls[0][0] == "mark" and env.marks.calls[-1] == ("clear", ("snapshot:risk",), None)


def test_another_submits_wake_never_takes_a_key_whose_mark_is_in_flight():
    env = make()
    entered, release = threading.Event(), threading.Event()
    plain_mark = env.marks.mark

    def slow_mark(keys, *, timeout_s, now=None):
        if keys == ["snapshot:risk"] and not entered.is_set():
            entered.set()
            release.wait(5.0)
        plain_mark(keys, timeout_s=timeout_s, now=now)
    env.marks.mark = slow_mark
    built = []
    env.builders["risk"] = lambda: built.append("risk") or result({"heat": 1})
    env.builders["analytics.snapshot"] = lambda: built.append("a") or result({"overall": {}})
    env.w.start()
    try:
        submitter = threading.Thread(target=env.w.submit, args=(["risk"],))
        submitter.start()
        assert entered.wait(5.0)
        assert env.w.submit(["risk", "analytics.snapshot"]) == ["analytics.snapshot"]
        assert wait_until(lambda: "analytics.snapshot" in env.rows.rows)
        assert built == ["a"]                           # the woken batch left "risk" alone
        release.set()
        submitter.join(5.0)
        assert wait_until(lambda: "risk" in env.rows.rows)
    finally:
        env.w.stop()


def test_escape_mid_batch_clears_unfinished_marks_and_keeps_landed():
    rows, marks, published = Rows(), Marks(), []
    reads = []

    def budget():
        reads.append(1)
        if len(reads) > 1:                              # the second key's budget read escapes
            raise RuntimeError("budget unreadable")
        return 2.0
    a, b, c = "risk", "analytics.snapshot", "calendar.pnl:2026-10"
    builders = {k: (lambda: result({"ok": 1})) for k in (a, b, c)}
    w = SnapshotWorker(builders_fn=lambda: builders, repo_fn=lambda: rows, marks_fn=lambda: marks,
                       publish=published.append, budget_fn=budget, clock=lambda: T0)
    with pytest.raises(RuntimeError):
        w.run_batch([a, b, c])
    assert w.drain_landed() == [a] and published == ["market"]
    clears = [call for call in marks.calls if call[0] == "clear"]
    assert clears == [("clear", ("snapshot:risk",), None),
                      ("clear", ("snapshot:analytics.snapshot",), "RuntimeError: budget unreadable"),
                      ("clear", ("snapshot:calendar.pnl:2026-10",), "RuntimeError: budget unreadable")]
    assert w.submit([a, b, c]) == [a, b, c]             # nothing left stuck as active


def test_worker_survives_a_raising_batch_and_accepts_the_key_again():
    env = make()
    env.builders["risk"] = lambda: result({"heat": 1})
    calls = []

    def flaky_builders():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("builders boom")
        return env.builders
    env.w._builders_fn = flaky_builders
    env.w.start()
    try:
        assert env.w.submit(["risk"]) == ["risk"]
        assert wait_until(lambda: ("clear", ("snapshot:risk",), "RuntimeError: builders boom")
                          in env.marks.calls)
        assert wait_until(lambda: env.w.submit(["risk"]) == ["risk"])
        assert wait_until(lambda: env.w.drain_landed() == ["risk"])
        assert _worker_alive()
    finally:
        env.w.stop()


def test_stop_then_start_runs_again():
    env = make()
    env.builders["risk"] = lambda: result({"heat": 1})
    env.w.start()
    env.w.stop()
    env.w.start()
    try:
        assert env.w.submit(["risk"]) == ["risk"]
        assert wait_until(lambda: env.w.drain_landed() == ["risk"])
    finally:
        env.w.stop()


def test_start_after_a_stop_that_timed_out_mid_build_keeps_a_live_worker():
    env = make()
    building, release = threading.Event(), threading.Event()

    def gated():
        building.set()
        release.wait(5.0)
        return result({"v": 1})
    env.builders["slow"] = gated
    env.builders["risk"] = lambda: result({"heat": 1}, at=T0 + timedelta(seconds=1))
    env.w.start()
    assert env.w.submit(["slow"]) == ["slow"]
    assert building.wait(5.0)
    env.w.stop(timeout=0.05)                            # returns with the batch still running
    starter = threading.Thread(target=env.w.start)
    starter.start()
    release.set()
    starter.join(5.0)
    try:
        assert not starter.is_alive()
        assert wait_until(lambda: "slow" in env.rows.rows)
        assert env.w.submit(["risk"]) == ["risk"]
        assert wait_until(lambda: "risk" in env.rows.rows)
        assert _worker_alive()
    finally:
        env.w.stop()
