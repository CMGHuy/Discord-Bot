"""One listener per process: a second connection reuses it (v116)."""
from swingbot import config
from swingbot.admin.events.broker import EventBroker
from swingbot.admin.events import snapshot_listener
from swingbot.admin.events.db_listener import DbEventListener
from tests.admin.test_db_listener_reconnect import _scripted_listen


def test_a_subscribed_broker_has_one_db_listener_that_a_second_connection_reuses(
        monkeypatch, tmp_path, db_engine):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    broker = EventBroker()
    with broker.subscribe():
        first = broker._watcher
        assert isinstance(first, DbEventListener)
        with broker.subscribe():
            assert broker.connection_count == 2
            assert broker._watcher is first
        assert broker._watcher is first


def test_the_snapshot_listener_is_a_separate_singleton_the_broker_never_touches(
        monkeypatch, tmp_path, db_engine):
    """v218: the broker still owns exactly one watcher; the snapshot's listener is
    not it, and a broker subscribe/release neither starts nor stops it."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    listen, _calls = _scripted_listen([])
    snap = snapshot_listener.ensure_started(
        factory=lambda: snapshot_listener.SnapshotListener(listen=listen))
    try:
        broker = EventBroker()
        with broker.subscribe():
            assert broker._watcher is not snap
            assert not isinstance(broker._watcher, snapshot_listener.SnapshotListener)
        assert broker._watcher is None
        assert snapshot_listener.ensure_started() is snap
        assert snap._thread is not None
    finally:
        snapshot_listener.stop()
