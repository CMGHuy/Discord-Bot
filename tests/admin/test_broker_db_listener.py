"""The broker's default watcher is the Postgres listener (v116)."""
from swingbot import config
from swingbot.admin.events.broker import EventBroker
from swingbot.admin.events.db_listener import DbEventListener


def _point_at_test_db(monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))


def test_the_default_watcher_is_a_db_listener(monkeypatch, tmp_path, db_engine):
    _point_at_test_db(monkeypatch, tmp_path, db_engine)
    broker = EventBroker()
    with broker.subscribe():
        assert isinstance(broker._watcher, DbEventListener)


def test_an_injected_factory_still_wins():
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


def test_the_listener_stops_when_the_last_connection_leaves(monkeypatch,
                                                            tmp_path, db_engine):
    _point_at_test_db(monkeypatch, tmp_path, db_engine)
    broker = EventBroker()
    sub = broker.subscribe()
    listener = broker._watcher
    assert listener is not None
    sub.close()
    assert broker._watcher is None
    assert listener._stop.is_set()
