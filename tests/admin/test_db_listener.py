"""The listener: notifications in, debounced concern names out."""
import threading
import time

import pytest

from swingbot.admin.events.db_listener import DEBOUNCE, DbEventListener


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def emitted():
    return []


@pytest.fixture
def listener(emitted):
    clock = FakeClock()
    lst = DbEventListener(emitted.append, clock=clock)
    lst.clock = clock
    return lst


def test_a_notification_does_not_emit_immediately(listener, emitted):
    listener.on_notification("trades")
    listener.flush()
    assert emitted == []


def test_it_emits_once_the_debounce_elapses(listener, emitted):
    listener.on_notification("trades")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_a_burst_emits_once(listener, emitted):
    for _ in range(5):
        listener.on_notification("trades")
        listener.clock.advance(0.05)
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_the_debounce_is_trailing_not_leading(listener, emitted):
    """A write every 0.1s must not emit until the writes stop -- that is what
    keeps a scan tick from producing one refetch per table."""
    for _ in range(10):
        listener.on_notification("trades")
        listener.clock.advance(0.1)
        listener.flush()
    assert emitted == []
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == ["trades"]


def test_different_concerns_debounce_independently(listener, emitted):
    listener.on_notification("trades")
    listener.clock.advance(0.1)
    listener.on_notification("jobs")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert sorted(emitted) == ["jobs", "trades"]


def test_an_unknown_channel_is_ignored_not_forwarded(listener, emitted):
    listener.on_notification("not-a-concern")
    listener.clock.advance(DEBOUNCE + 0.01)
    listener.flush()
    assert emitted == []


def test_a_raising_subscriber_does_not_kill_the_listener(listener):
    boom = DbEventListener(lambda _e: (_ for _ in ()).throw(RuntimeError("x")),
                           clock=listener.clock)
    boom.on_notification("trades")
    listener.clock.advance(DEBOUNCE + 0.01)
    boom.flush()          # must not raise


def test_an_empty_tick_flushes_a_settled_burst(listener, emitted):
    """notify.listen calls on_event(None) when a poll window passes quietly;
    that is the only thing that flushes a burst ending in silence."""
    listener._on_event("trades")
    assert emitted == []
    listener.clock.advance(DEBOUNCE + 0.01)
    listener._on_event(None)
    assert emitted == ["trades"]


def test_start_and_stop_are_clean(emitted, db_engine):
    lst = DbEventListener(emitted.append,
                          dsn=db_engine.url.render_as_string(hide_password=False))
    lst.start()
    time.sleep(0.3)
    lst.stop()
    assert not any(t.name.startswith("db-event-listener") and t.is_alive()
                   for t in threading.enumerate())
