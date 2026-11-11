"""v218 V218-4: the admin's cross-request raw-record snapshot (v205 L2-a/L2-b)."""
import ast
import logging
import pathlib
import threading

import pytest

from swingbot import config
from swingbot.core.infra import read_memo, store_generation as sg, store_snapshot as ss

PLANS, TRADES = read_memo.PLANS, read_memo.TRADES


class Versions:
    """A fake ``_query_versions``: a mutable tuple and a call counter."""

    def __init__(self):
        self.value = ((2, "a"), (5, "b"), (1, "c"))
        self.calls = 0
        self.fail = False

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("database down")
        return self.value


@pytest.fixture
def versions(monkeypatch):
    fake = Versions()
    monkeypatch.setattr(ss, "_query_versions", fake)
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "on", raising=False)
    ss.reset()
    sg.reset()
    sg.set_connected(True)
    yield fake
    ss.end_request()
    ss.reset()
    sg.reset()


def _loader(calls, value):
    def load():
        calls.append(1)
        return value
    return load


def _request(key, loader):
    """One admin request: armed per-request state, one read scope, the state at the end."""
    ss.begin_request()
    try:
        with read_memo.scope():
            value = ss.read(key, loader)
        return value, ss.request_state()
    finally:
        ss.end_request()


def test_the_snapshot_keys_are_the_four_memo_keys():
    assert ss.SNAPSHOT_KEYS == frozenset({read_memo.TRADE_ROWS, TRADES, PLANS, read_memo.NOTED_IDS})


def test_a_second_request_is_a_hit_on_the_same_stored_value(versions):
    calls, value = [], {"p1": {"status": "ACTIVE"}}
    first, state1 = _request(PLANS, _loader(calls, value))
    second, state2 = _request(PLANS, _loader(calls, value))
    assert (state1, state2) == ("miss", "hit")
    assert calls == [1] and first is second is value
    assert ss.stored(PLANS) is value


@pytest.mark.parametrize("concern", sg.CONCERNS)
def test_any_generation_bump_clears_every_key(versions, concern):
    calls = []
    _request(PLANS, _loader(calls, {}))
    _request(TRADES, _loader(calls, []))
    sg.bump(concern)
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"
    assert ss.stored(TRADES) is None
    assert len(calls) == 3


def test_a_version_change_clears_the_snapshot_with_unchanged_generations(versions):
    calls = []
    _request(PLANS, _loader(calls, {}))
    versions.value = ((3, "a2"), (5, "b"), (1, "c"))
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"
    assert len(calls) == 2


def test_versions_are_read_once_per_request(versions):
    ss.begin_request()
    with read_memo.scope():
        for key in ss.SNAPSHOT_KEYS:
            ss.read(key, lambda: [])
    ss.end_request()
    assert versions.calls == 1
    _request(PLANS, lambda: {})
    assert versions.calls == 2


def test_outside_a_request_versions_are_read_per_call(versions):
    ss.request_versions()
    ss.request_versions()
    assert versions.calls == 2


@pytest.mark.parametrize("switch, connected", [("off", True), ("on", False)])
def test_switch_off_or_listener_down_loads_directly(versions, monkeypatch, switch, connected):
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", switch)
    sg.set_connected(connected)
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "off"
    _request(PLANS, _loader(calls, {}))
    assert len(calls) == 2 and ss.stored(PLANS) is None
    assert versions.calls == 0 and ss.enabled() is False


def test_outside_a_read_scope_or_for_another_key_it_is_the_loader(versions):
    calls = []
    ss.read(PLANS, _loader(calls, {}))                      # no read_memo.scope()
    with read_memo.scope():
        ss.read("watchlist", _loader(calls, []))
    assert len(calls) == 2 and ss.stored(PLANS) is None and versions.calls == 0


def test_a_failing_version_query_loads_directly_and_is_logged(versions, caplog):
    caplog.set_level(logging.WARNING)
    versions.fail = True
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "off"
    assert calls == [1] and ss.stored(PLANS) is None
    assert any("admin snapshot bypassed" in r.getMessage() for r in caplog.records)


def test_a_raising_loader_stores_nothing_and_re_raises(versions):
    def boom():
        raise RuntimeError("loader failed")

    with pytest.raises(RuntimeError, match="loader failed"):
        _request(PLANS, boom)
    assert ss.stored(PLANS) is None
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"


def test_concurrent_readers_wait_for_one_rebuild(versions):
    started, release, calls, results = threading.Event(), threading.Event(), [], []
    value = {"p1": {}}

    def slow():
        calls.append(1)
        started.set()
        release.wait(2)
        return value

    def worker():
        with read_memo.scope():                             # each thread its own context
            results.append(ss.read(PLANS, slow))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    assert started.wait(2)
    release.set()
    for thread in threads:
        thread.join()
    assert calls == [1]
    assert len(results) == 6 and all(result is value for result in results)


def test_state_precedence_within_one_request(versions):
    _request(PLANS, lambda: {})                             # PLANS now stored
    ss.begin_request()
    with read_memo.scope():
        ss.read(PLANS, lambda: {})                          # hit
        ss.read(TRADES, lambda: [])                         # miss
    assert ss.request_state() == "miss"
    ss.end_request()


def test_a_request_that_reads_only_the_versions_is_a_hit(versions):
    ss.begin_request()
    ss.request_versions()                                   # what V218-8's 304 path does
    assert ss.request_state() == "hit"
    ss.end_request()


def test_a_request_that_touches_nothing_is_off(versions):
    ss.begin_request()
    assert ss.request_state() == "off"
    ss.end_request()


def test_end_request_drops_the_cached_versions(versions):
    ss.begin_request()
    ss.request_versions()
    ss.end_request()
    ss.request_versions()
    assert versions.calls == 2


def test_reset_drops_every_stored_value(versions):
    _request(PLANS, lambda: {"p": {}})
    ss.reset()
    assert ss.stored(PLANS) is None


def test_the_module_imports_no_flask_or_admin_code():
    tree = ast.parse(pathlib.Path(ss.__file__).read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {name for name in names if name.startswith(("flask", "swingbot.admin"))}
