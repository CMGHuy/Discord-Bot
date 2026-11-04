"""v205 V205-6: the opt-in per-request read memo (index "Read memo")."""
import ast
import sys
import threading
from pathlib import Path

import pytest

from swingbot.core.infra import read_memo

SOURCE = Path(read_memo.__file__)


class _Loader:
    """Counts its calls; returns fresh nested records each time, like a repository."""

    def __init__(self):
        self.calls = 0

    def rows(self):
        self.calls += 1
        return [{"id": "a", "legs": [{"r": 1.0}]}, {"id": "b", "legs": []}]

    def by_id(self):
        return {row["id"]: row for row in self.rows()}


def test_outside_a_scope_every_call_is_the_loader_itself():
    loader = _Loader()
    first = read_memo.records(read_memo.TRADES, loader.rows)
    second = read_memo.records(read_memo.TRADES, loader.rows)
    assert loader.calls == 2 and first == second
    assert read_memo.active() is False and read_memo.peek(read_memo.TRADES) is None


def test_outside_a_scope_the_loaders_own_objects_come_back():
    stored = [{"id": "a"}]
    assert read_memo.records(read_memo.TRADES, lambda: stored) is stored
    mapping = {"a": {"id": "a"}}
    assert read_memo.mapping(read_memo.PLANS, lambda: mapping) is mapping


def test_inside_a_scope_the_loader_runs_once_per_key():
    loader = _Loader()
    with read_memo.scope():
        assert read_memo.active() is True
        first = read_memo.records(read_memo.TRADES, loader.rows)
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert loader.calls == 1 and first == second
        read_memo.records(read_memo.TRADE_ROWS, loader.rows)
        assert loader.calls == 2                     # a second key loads on its own
    assert read_memo.active() is False


def test_each_call_gets_its_own_top_level_copies():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.records(read_memo.TRADES, loader.rows)
        first[0]["id"] = "changed"
        first.append({"id": "extra"})
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert [row["id"] for row in second] == ["a", "b"]
        assert first[1] is not second[1]
        stored = read_memo.peek(read_memo.TRADES)
        assert all(row is not stored_row for row, stored_row in zip(second, stored))


def test_copies_are_shallow_by_contract():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.records(read_memo.TRADES, loader.rows)
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert first[0]["legs"] is second[0]["legs"]  # V205-8 proves no reader writes here


def test_mapping_copies_each_value():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.mapping(read_memo.PLANS, loader.by_id)
        first["a"]["id"] = "changed"
        del first["b"]
        second = read_memo.mapping(read_memo.PLANS, loader.by_id)
        assert loader.calls == 1
        assert list(second) == ["a", "b"] and second["a"]["id"] == "a"


def test_a_nested_scope_reuses_and_keeps_the_outer_memo():
    loader = _Loader()
    with read_memo.scope():
        read_memo.records(read_memo.TRADES, loader.rows)
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, loader.rows)
            assert loader.calls == 1
        assert read_memo.active() is True
        assert read_memo.peek(read_memo.TRADES) is not None
        read_memo.records(read_memo.TRADES, loader.rows)
        assert loader.calls == 1
    assert read_memo.active() is False


def test_a_raising_body_still_resets_the_scope():
    with pytest.raises(RuntimeError):
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, _Loader().rows)
            raise RuntimeError("view failed")
    assert read_memo.active() is False and read_memo.peek(read_memo.TRADES) is None


def test_a_raising_loader_stores_nothing():
    loader = _Loader()

    def broken():
        raise ConnectionError("db down")

    with read_memo.scope():
        with pytest.raises(ConnectionError):
            read_memo.records(read_memo.TRADES, broken)
        assert read_memo.peek(read_memo.TRADES) is None
        assert len(read_memo.records(read_memo.TRADES, loader.rows)) == 2
        assert loader.calls == 1


def test_two_threads_never_share_a_memo():
    barrier = threading.Barrier(2)
    seen: dict[str, list[str]] = {}

    def request(tag):
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, lambda: [{"id": tag}])
            barrier.wait(timeout=5)                  # both scopes are open at once
            seen[tag] = [row["id"] for row in read_memo.records(read_memo.TRADES, lambda: [])]

    threads = [threading.Thread(target=request, args=(tag,)) for tag in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert seen == {"one": ["one"], "two": ["two"]}


def test_peek_of_a_key_never_loaded_is_none():
    with read_memo.scope():
        assert read_memo.peek(read_memo.PLANS) is None


def test_it_is_a_leaf_module():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
