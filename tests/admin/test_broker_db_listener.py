"""Which watcher the broker builds, per stage."""
import os

from swingbot import config
from swingbot.admin.events import watcher as watcher_mod
from swingbot.admin.events.broker import EventBroker
from swingbot.admin.events.db_listener import DbEventListener
from swingbot.admin.events.watcher import FileWatcher, default_paths, residual_paths


def _db_stage(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))


def test_json_stage_still_builds_a_file_watcher(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    broker = EventBroker()
    with broker.subscribe():
        assert isinstance(broker._watcher, FileWatcher)
        # The json stage watches everything, as it always has.
        assert broker._watcher._paths == default_paths()


def test_db_stage_builds_a_db_listener(monkeypatch, tmp_path, db_engine):
    _db_stage(monkeypatch, tmp_path, db_engine)
    broker = EventBroker()
    with broker.subscribe():
        parts = broker._watcher.watchers
        listeners = [w for w in parts if isinstance(w, DbEventListener)]
        files = [w for w in parts if isinstance(w, FileWatcher)]
        assert len(listeners) == 1 and len(files) == 1
        watched = set(files[0]._paths)
        assert os.path.join(str(tmp_path), "scan_progress.json") in watched
        assert os.path.join(str(tmp_path), "trades.json") not in watched


def test_residual_paths_exclude_every_table_backed_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    residual = residual_paths()
    for name in watcher_mod._TABLE_BACKED:
        assert os.path.join(str(tmp_path), name) not in residual
    # Everything not declared table-backed is still watched -- a new file in
    # _DATA_PATHS defaults to residual, never to silently dropped.
    expected = {p: e for p, e in default_paths().items()
                if os.path.basename(p) not in watcher_mod._TABLE_BACKED
                or p == config.ENV_PATH}
    assert residual == expected
    assert config.ENV_PATH in residual
    for name in ("scan_progress.json", "scan_snapshots.json",
                 "scan_telemetry.jsonl", "analytics_snapshot.json"):
        assert os.path.join(str(tmp_path), name) in residual


def test_table_backed_names_are_all_watched_paths():
    # A typo in _TABLE_BACKED would silently keep a file residual; catch it.
    names = {name for name, _event in watcher_mod._DATA_PATHS}
    assert watcher_mod._TABLE_BACKED <= names


def test_an_injected_factory_still_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    built = []

    class Fake:
        def __init__(self, emit):
            built.append(emit)

        def start(self): pass

        def stop(self): pass

    broker = EventBroker(watcher_factory=Fake)
    with broker.subscribe():
        assert isinstance(broker._watcher, Fake)
    assert len(built) == 1


def test_the_watcher_stops_when_the_last_connection_leaves(monkeypatch,
                                                           tmp_path, db_engine):
    _db_stage(monkeypatch, tmp_path, db_engine)
    broker = EventBroker()
    sub = broker.subscribe()
    composite = broker._watcher
    assert composite is not None
    sub.close()
    assert broker._watcher is None
    for part in composite.watchers:
        assert part._stop.is_set()
