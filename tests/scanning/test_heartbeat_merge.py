"""v148 O3/O5: heartbeat writes are key-level merges (doc || patch), so the
bot and the admin never drop each other's keys, and a failed heartbeat
read or write is counted instead of vanishing."""
import logging

import pytest

from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories import heartbeat as heartbeat_mod
from swingbot.core.db.repositories.heartbeat import KEY, HeartbeatRepository
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


class _Broken:
    """A heartbeat repository whose database is gone."""

    def merge(self, fields, *, conn=None):
        raise RuntimeError("db down")

    def last(self, *, conn=None):
        raise RuntimeError("db down")


def test_merge_creates_the_row_when_absent():
    HeartbeatRepository().merge({"a": 1})

    last = HeartbeatRepository().last()
    assert last["a"] == 1 and last["ts"]


def test_merge_touches_only_its_own_keys_and_bumps_ts():
    repo = HeartbeatRepository()
    repo.beat({"a": 1, "b": 2})
    first_ts = repo.last()["ts"]

    repo.merge({"b": 3})

    last = repo.last()
    assert (last["a"], last["b"]) == (1, 3)
    assert last["ts"] >= first_ts
    assert repo.count() == 1


def test_two_writers_with_disjoint_keys_both_survive():
    runstate.set_alert_active(True)                      # bot: tick outcome
    runstate._update_heartbeat({"store_write_failure": None})   # admin: unpause
    runstate._write_heartbeat()                          # bot: next tick's liveness

    state = runstate._read_heartbeat()
    assert state["alert_active"] is True
    assert "store_write_failure" in state and state["store_write_failure"] is None
    assert "timestamp" in state and "swallowed" in state


def test_update_does_not_read_the_row_first(monkeypatch):
    """A writer holding a stale whole-doc view used to write it back over
    the other process's keys. A write that reads nothing cannot."""
    runstate.set_alert_active(True)

    def no_reads(self, *, conn=None):
        raise AssertionError("_update_heartbeat must not read the row")

    monkeypatch.setattr(HeartbeatRepository, "last", no_reads)
    runstate._update_heartbeat({"scan_paused": True})

    row = HeartbeatRepository().get(KEY)
    assert row["alert_active"] is True and row["scan_paused"] is True
    assert "runstate.update_heartbeat" not in swallowed_mod.snapshot()


def test_a_failed_write_is_counted_and_logged_at_warning(monkeypatch, caplog):
    monkeypatch.setattr(heartbeat_mod, "heartbeat_repo", lambda: _Broken())

    with caplog.at_level(logging.DEBUG, logger=runstate.log.name):
        runstate._update_heartbeat({"timestamp": "2026-10-01T00:00:00+00:00"})

    entry = swallowed_mod.snapshot()["runstate.update_heartbeat"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: db down"
    [record] = [r for r in caplog.records if r.name == runstate.log.name]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "heartbeat write failed"


def test_a_failed_read_is_counted_and_reads_as_unknown(monkeypatch, caplog):
    monkeypatch.setattr(heartbeat_mod, "heartbeat_repo", lambda: _Broken())

    with caplog.at_level(logging.DEBUG, logger=runstate.log.name):
        assert runstate._read_heartbeat() == {}
        assert runstate.get_stale_alert_active() is False

    assert swallowed_mod.snapshot()["runstate.read_heartbeat"]["count"] == 2
    assert {r.levelno for r in caplog.records if r.name == runstate.log.name} == {logging.DEBUG}


def test_the_tick_heartbeat_carries_the_swallowed_counts():
    swallowed(logging.getLogger("tests.heartbeat_probe"), "probe.heartbeat",
              ValueError("v"), level=logging.DEBUG)

    runstate._write_heartbeat()

    flushed = runstate._read_heartbeat()["swallowed"]
    assert flushed["since"] == swallowed_mod.STARTED_AT
    assert flushed["counts"]["probe.heartbeat"]["count"] == 1
    assert flushed["counts"]["probe.heartbeat"]["last_error"] == "ValueError: v"


def test_stale_and_provider_alert_flags_round_trip():
    assert runstate.get_stale_alert_active() is False
    assert runstate.get_provider_alert_active() is False

    runstate.set_stale_alert_active(True)
    runstate.set_provider_alert_active(True)
    runstate.set_stale_alert_active(False)

    assert runstate.get_stale_alert_active() is False
    assert runstate.get_provider_alert_active() is True
    assert runstate.get_alert_active() is False
