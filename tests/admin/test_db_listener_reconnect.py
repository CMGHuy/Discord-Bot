"""A lost LISTEN connection is retried, and the reconnect is announced as one
`resync`, so a notification missed while down is never silently lost (v116)."""
import threading
import time

from swingbot.admin.events.db_listener import DbEventListener
from swingbot.core.db import notify


def _scripted_listen(script):
    """Each call plays one step: 'fail' raises before LISTEN, 'drop' raises
    after LISTEN, 'ok' reports LISTEN and blocks until stopped."""
    calls = []

    def listen(channels, on_event, stop, *, poll, dsn, on_listening=None):
        step = script.pop(0) if script else "ok"
        calls.append(step)
        if step == "fail":
            raise OSError("connection refused")
        on_listening()
        if step == "drop":
            raise OSError("server closed the connection unexpectedly")
        stop.wait(5)

    return listen, calls


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_the_first_connection_emits_no_resync():
    emitted = []
    listen, calls = _scripted_listen(["ok"])
    listener = DbEventListener(emitted.append, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["ok"])
    listener.stop()
    assert emitted == []


def test_a_dropped_connection_reconnects_and_emits_exactly_one_resync():
    emitted = []
    listen, calls = _scripted_listen(["drop", "fail", "fail", "ok"])
    listener = DbEventListener(emitted.append, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "fail", "fail", "ok"])
    listener.stop()
    assert emitted == ["resync"]


def test_stop_during_a_backoff_returns_promptly():
    listen, calls = _scripted_listen(["fail"] * 50)
    listener = DbEventListener(lambda _e: None, listen=listen, backoff=(5.0, 5.0))
    listener.start()
    assert _wait_for(lambda: calls == ["fail"])
    started = time.monotonic()
    listener.stop()
    assert time.monotonic() - started < 1.0


def test_a_raising_emit_on_resync_does_not_kill_the_listener():
    listen, calls = _scripted_listen(["drop", "ok"])

    def boom(_event):
        raise RuntimeError("subscriber exploded")

    listener = DbEventListener(boom, listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "ok"])
    listener.stop()


def test_notify_listen_reports_when_listen_is_active(db_engine):
    stop = threading.Event()
    seen = []

    def on_listening():
        seen.append("up")
        stop.set()

    notify.listen(("trades",), lambda _c: None, stop, poll=0.05,
                  dsn=db_engine.url.render_as_string(hide_password=False),
                  on_listening=on_listening)
    assert seen == ["up"]
