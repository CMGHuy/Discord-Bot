"""v204 V204-13: no request-time caller rebuilds the analytics snapshot while the refresher is on.

Spec Panel amendments and Brief corrections: the guard names every request-time
caller -- api_v1/analytics.py `_snapshot`, api_v1/dashboard.py `_equity_30d`
and queries.py `_registry_rows` -- and an AST scan fails on any new one."""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot import config
from swingbot.admin import market_values, queries

ROOT = Path(__file__).resolve().parents[2]
GUARDED = [
    ("swingbot.admin.api_v1.analytics", "_snapshot", {}),
    ("swingbot.admin.api_v1.analytics", "_snapshot", {"fresh": True}),
    ("swingbot.admin.api_v1.dashboard", "_equity_30d", {}),
    ("swingbot.admin.queries", "_registry_rows", {}),
]
REBUILDERS = [
    ("swingbot.core.analytics.snapshots", "refresh_snapshot"),
    ("swingbot.core.analytics.snapshots", "compute_snapshot"),
    ("swingbot.admin.queries", "refresh_snapshot"),
    ("swingbot.core.analytics.admin_snapshots", "build_analytics_snapshot"),
]


@pytest.fixture
def rebuilds(monkeypatch):
    calls: list[str] = []
    for module, name in REBUILDERS:
        def boom(*a, _n=f"{module}.{name}", **k):
            calls.append(_n)
            raise AssertionError(f"request-time snapshot rebuild: {_n}")
        monkeypatch.setattr(importlib.import_module(module), name, boom)
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")  # refresher_on() needs both
    monkeypatch.setattr(market_values, "read_snapshot", lambda key, *, now=None: {
        "key": key, "doc": None, "inputs": None, "computed_at": None,
        "stale_inputs": False, "refreshing": True, "error": None})
    monkeypatch.setattr(market_values, "request_refresh", lambda *a, **k: 0)
    monkeypatch.setattr(queries, "load_registry", lambda: [])
    return calls


@pytest.mark.parametrize("module, name, kwargs", GUARDED)
def test_request_time_caller_never_rebuilds_when_on(rebuilds, module, name, kwargs):
    getattr(importlib.import_module(module), name)(**kwargs)
    assert rebuilds == []


def _functions_naming(path: Path, symbol: str) -> set[str]:
    found = set()
    for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Name) and node.id == symbol) or \
               (isinstance(node, ast.Attribute) and node.attr == symbol) or \
               (isinstance(node, ast.alias) and node.name == symbol):
                found.add(fn.name)
    return found


def test_only_the_kill_switch_reader_names_refresh_snapshot_in_the_admin_package():
    hits = {}
    for path in sorted((ROOT / "swingbot" / "admin").rglob("*.py")):
        names = _functions_naming(path, "refresh_snapshot")
        if names:
            hits[path.relative_to(ROOT).as_posix()] = names
    assert hits == {"swingbot/admin/queries.py": {"_snapshot_read_off"}}


def test_the_shared_reader_branches_on_the_kill_switch():
    source = inspect.getsource(queries.analytics_snapshot_read)
    assert "refresher_on()" in source and "_snapshot_read_off" in source
