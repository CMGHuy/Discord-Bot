"""v206 P1-b: a progress read that fails loudly, and the running flag on a given connection.

The admin's event broker reads both once per `scan` event on its fail-fast
side connection, and must tell "nothing publishing" (None) from "could not
read" (raise). `progress_store.read()` folds both into None, so the broker
gets `read_strict`; `read()` keeps its swallowing contract for /system/scan.
DB-free: the repositories are faked.
"""
import pytest

from swingbot.core.db.repositories import scan_progress as repo_module
from swingbot.core.infra.swallowed import reset, snapshot
from swingbot.core.scanning import progress_store, runstate


class _Repo:
    def __init__(self, record=None, error=None):
        self.record, self.error, self.conns = record, error, []

    def read(self, *, conn=None):
        self.conns.append(conn)
        if self.error is not None:
            raise self.error
        return self.record


@pytest.fixture
def repo(monkeypatch):
    def install(**kwargs):
        made = _Repo(**kwargs)
        monkeypatch.setattr(repo_module, "scan_progress_repo", lambda: made)
        return made
    return install


def test_read_strict_returns_the_record_read_on_the_given_connection(repo):
    made = repo(record={"pct": 40, "stage": "crawling data"})
    conn = object()
    assert progress_store.read_strict(conn=conn) == {"pct": 40, "stage": "crawling data"}
    assert made.conns == [conn]


def test_read_strict_is_none_when_nothing_is_publishing(repo):
    repo(record=None)
    assert progress_store.read_strict() is None


def test_read_strict_raises_when_the_read_fails(repo):
    repo(error=RuntimeError("canceling statement due to statement timeout"))
    with pytest.raises(RuntimeError, match="statement timeout"):
        progress_store.read_strict()


def test_read_still_swallows_and_counts_the_same_tag(repo):
    reset()
    made = repo(error=RuntimeError("boom"))
    assert progress_store.read() is None
    assert made.conns == [None]
    assert snapshot()["scan.progress_store.read"]["count"] == 1


def test_read_still_returns_the_record(repo):
    repo(record={"pct": 70})
    assert progress_store.read() == {"pct": 70}


class _Flags:
    def __init__(self, value):
        self.value, self.calls = value, []

    def is_set(self, name, *, conn=None):
        self.calls.append((name, conn))
        return self.value


def test_is_scan_running_reads_the_flag_on_the_given_connection(monkeypatch):
    flags = _Flags(True)
    monkeypatch.setattr(runstate, "_flags", lambda: flags)
    conn = object()
    assert runstate.is_scan_running(conn=conn) is True
    assert flags.calls == [("scan_running", conn)]


def test_is_scan_running_without_a_connection_is_unchanged(monkeypatch):
    flags = _Flags(False)
    monkeypatch.setattr(runstate, "_flags", lambda: flags)
    assert runstate.is_scan_running() is False
    assert flags.calls == [("scan_running", None)]
