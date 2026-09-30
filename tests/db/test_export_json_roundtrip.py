"""Real-Postgres round trip: import a JSON source, export it, compare.

Skips (via the db_conn fixture) when the disposable test database is not
reachable. Repositories open their own transactions, so the engine they see is
redirected onto the rolled-back test connection.
"""
import contextlib
import json

import pytest

from scripts.db import export_json, import_common
from scripts.db.parity_report import STORES
from tests.scripts.test_export_json import (IMPORTERS, SOURCES, _import_store, _read,
                                            _semantic_rows, _write)


class _ConnEngine:
    def __init__(self, conn):
        self._conn = conn

    @contextlib.contextmanager
    def begin(self):
        yield self._conn


@pytest.fixture
def routed(db_conn, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.base.get_engine",
                        lambda: _ConnEngine(db_conn))
    return db_conn


@pytest.fixture
def db_imported(routed, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    # plans first: starred_plans has an FK to plans.
    for name in ("plans", "trades", "journal", "state", "watchlist", "starred_plans", "account"):
        _import_store(name, _write(src / STORES[name].filename, SOURCES[name]))
    return src


@pytest.mark.parametrize("name", sorted(IMPORTERS))
def test_db_export_matches_source(name, db_imported, tmp_path):
    out = tmp_path / "out"
    export_json.run_export([name], str(out), dry_run=False, force=False)
    report = import_common.compare(
        _semantic_rows(name, _read(db_imported / STORES[name].filename)),
        _semantic_rows(name, _read(out / STORES[name].filename)), key=STORES[name].key)
    assert report.ok, report.render()


def test_db_export_account_round_trips(db_imported, tmp_path):
    export_json.run_export(["account"], str(tmp_path), dry_run=False, force=False)
    exported = json.loads((tmp_path / "account.json").read_text(encoding="utf-8"))
    assert exported == SOURCES["account"]
