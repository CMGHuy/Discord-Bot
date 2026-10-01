"""One listener per process: a second connection reuses it (v116)."""
from swingbot import config
from swingbot.admin.events.broker import EventBroker
from swingbot.admin.events.db_listener import DbEventListener


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
