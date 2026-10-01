"""At the db stage nothing stat()s a table-backed file in data/ any more."""
import os
import threading
import time

from swingbot import config
from swingbot.admin.events import watcher
from swingbot.admin.events.broker import EventBroker


def _db_stage(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))


def test_no_stat_calls_on_table_backed_paths_at_the_db_stage(monkeypatch, tmp_path,
                                                              db_engine):
    _db_stage(monkeypatch, tmp_path, db_engine)
    table_backed, residual = [], []
    real_stat = os.stat
    # Threads leaked by earlier tests (an admin job's _watch poller reads
    # admin_jobs.json under whatever DATA_DIR is patched now) are not this
    # broker's doing; only threads born during the test count.
    preexisting = set(threading.enumerate())

    def spy(path, *a, **kw):
        if threading.current_thread() in preexisting:
            return real_stat(path, *a, **kw)
        # _TABLE_BACKED holds the same basenames as _DATA_PATHS, so matching
        # on the basename inside tmp_path is exact, not vacuous.
        if str(tmp_path) in str(path):
            name = os.path.basename(str(path))
            (table_backed if name in watcher._TABLE_BACKED else residual).append(
                str(path))
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(os, "stat", spy)
    broker = EventBroker()
    with broker.subscribe():
        time.sleep(1.5)          # three file-watcher intervals' worth
    assert table_backed == [], f"something still polls data/: {table_backed[:5]}"
    # The spy is live: the residual FileWatcher legitimately stats these.
    assert any(p.endswith("scan_snapshots.json") for p in residual), residual


def test_only_one_watcher_object_exists(monkeypatch, tmp_path, db_engine):
    _db_stage(monkeypatch, tmp_path, db_engine)
    broker = EventBroker()
    with broker.subscribe():
        first = broker._watcher
        with broker.subscribe():
            assert broker.connection_count == 2
            # A second connection must not build a second watcher.
            assert broker._watcher is first
        assert broker._watcher is first
