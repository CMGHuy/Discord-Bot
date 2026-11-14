"""v218 V218-3: the snapshot's own LISTEN connection drives the store generations
(v205 L2-b; index Handoff 1). It runs whether or not an SSE tab is open."""
import threading

import pytest
from flask import Flask

from swingbot import config
from swingbot.admin.events import snapshot_listener as sl
from swingbot.admin.events.db_listener import DbEventListener
from swingbot.core.infra import store_generation as sg
from tests.admin.test_db_listener_reconnect import _scripted_listen, _wait_for


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _clean():
    sl.stop()
    sg.reset()
    yield
    sl.stop()
    sg.reset()


def test_the_base_listener_reports_connected_and_calls_the_disconnect_hook():
    downs = []

    class Recording(DbEventListener):
        def _on_disconnected(self):
            downs.append(self.connected)

    listen, calls = _scripted_listen(["drop", "ok"])
    listener = Recording(lambda _e: None, listen=listen, backoff=(0.01, 0.05))
    assert listener.connected is False
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "ok"] and listener.connected)
    listener.stop()
    assert listener.connected is False
    assert downs == [False, False]          # the drop, then stop(); each already marked down


def test_a_notification_bumps_its_generation_before_the_debounce():
    listener = sl.SnapshotListener(clock=FakeClock())
    listener.on_notification("trades")
    assert sg.token() == (1, 0, 0)          # no flush yet
    listener.on_notification("journal")
    listener.on_notification("journal")
    assert sg.token() == (1, 2, 0)


def test_a_channel_outside_the_snapshot_is_ignored():
    listener = sl.SnapshotListener(clock=FakeClock())
    listener.on_notification("account")
    listener.on_notification("settings")    # the settings concern moves only on config.reload()
    assert sg.token() == (0, 0, 0)


def test_the_debounced_emit_is_a_no_op():
    clock = FakeClock()
    listener = sl.SnapshotListener(clock=clock)
    listener.on_notification("trades")
    clock.now = 10.0
    assert listener.flush() == ["trades"]


def test_listens_on_trades_and_journal_only():
    assert sl.SNAPSHOT_CHANNELS == ("trades", "journal")
    assert sl.SnapshotListener()._channels == sl.SNAPSHOT_CHANNELS


def test_connect_bumps_everything_and_a_drop_bypasses_until_the_reconnect():
    listen, calls = _scripted_listen(["drop", "fail", "ok"])
    listener = sl.SnapshotListener(listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "fail", "ok"] and sg.connected())
    assert sg.token() == (2, 2, 2)          # one bump_all per successful LISTEN
    listener.stop()
    assert sg.connected() is False


def test_ensure_started_is_one_singleton_until_stop():
    built = []

    def factory():
        listen, _calls = _scripted_listen([])
        built.append(sl.SnapshotListener(listen=listen, backoff=(0.01, 0.05)))
        return built[-1]

    first = sl.ensure_started(factory=factory)
    assert sl.ensure_started(factory=factory) is first
    assert built == [first]
    assert _wait_for(sg.connected)
    sl.stop()
    assert sg.connected() is False
    assert sl.ensure_started(factory=factory) is not first
    assert len(built) == 2


def test_concurrent_first_requests_start_one_listener():
    built = []
    gate = threading.Barrier(8)

    def factory():
        listen, _calls = _scripted_listen([])
        built.append(sl.SnapshotListener(listen=listen))
        return built[-1]

    def worker():
        gate.wait()
        sl.ensure_started(factory=factory)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(built) == 1


def test_a_failing_start_is_swallowed_and_retried_next_request():
    def factory():
        raise OSError("no database")

    assert sl.ensure_started(factory=factory) is None
    assert sl._listener is None


def _app(testing: bool) -> Flask:
    app = Flask(__name__)
    app.testing = testing
    app.add_url_rule("/x", "x", lambda: "ok")
    sl.install(app)
    return app


@pytest.mark.parametrize("testing, switch, expected", [
    (False, "on", 1), (True, "on", 0), (False, "off", 0)])
def test_install_starts_the_listener_on_a_real_request_only(monkeypatch, testing, switch, expected):
    started = []
    monkeypatch.setattr(sl, "ensure_started", lambda **_kw: started.append(1))
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", switch, raising=False)
    client = _app(testing).test_client()
    client.get("/x")
    assert len(started) == expected


def test_the_admin_app_installs_it(admin_app):
    assert sl._start_on_first_request in admin_app.before_request_funcs[None]
