"""NG21 — the event broker: one watcher, many connections.

NG19 TRIAGE: KEEP unchanged. This tests `swingbot/admin/events/broker.py`,
which has no Jinja involvement at all and survives the cutover untouched.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v12-realtime-push-design.md`,
Decisions 4 (process-wide monotonic `seq`) and 5 (one watcher per process
started lazily; cap of 8 concurrent connections).

The watcher is faked throughout. NG20 already pins the `stat()` behaviour
against real files, and re-testing it here would only make these tests slow
and coupled to the filesystem -- what NG21 owns is the fan-out, the
counter, and the cap, none of which care where an event came from.
"""
import threading

import pytest

from swingbot.admin.api_v1 import ApiError
from swingbot.admin.events import broker as b


class FakeWatcher:
    """Stands in for FileWatcher: records lifecycle, emits on demand."""

    def __init__(self, emit):
        self.emit = emit
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        return self

    def stop(self):
        self.stops += 1

    @property
    def running(self) -> bool:
        return self.starts > self.stops


@pytest.fixture
def watchers():
    """Every watcher the broker under test built, in construction order."""
    return []


@pytest.fixture
def make_broker(watchers):
    def factory(**kwargs):
        def build(emit):
            watcher = FakeWatcher(emit)
            watchers.append(watcher)
            return watcher

        return b.EventBroker(watcher_factory=build, **kwargs)

    return factory


@pytest.fixture
def broker(make_broker):
    return make_broker()


def drain(subscription) -> list[str]:
    """Every event name currently queued, without blocking."""
    names = []
    while True:
        event = subscription.get(timeout=0)
        if event is None:
            return names
        names.append(event.event)


# --------------------------------------------------------------------------
# One watcher per process
# --------------------------------------------------------------------------

def test_no_connections_means_no_watcher(broker, watchers):
    """Lazily, per spec Decision 5 -- an admin nobody has open must not
    pay for a stat() loop."""
    assert watchers == []
    assert broker.connection_count == 0


def test_the_first_connection_starts_exactly_one_watcher(broker, watchers):
    with broker.subscribe():
        assert len(watchers) == 1
        assert watchers[0].starts == 1


def test_further_connections_do_not_start_another_watcher(broker, watchers):
    """The point of the broker. One watcher per *process*, not per tab --
    otherwise the stat() load multiplies by the number of open tabs."""
    with broker.subscribe(), broker.subscribe(), broker.subscribe():
        assert broker.connection_count == 3
        assert len(watchers) == 1
        assert watchers[0].starts == 1


def test_the_watcher_stops_when_the_last_connection_closes(broker, watchers):
    first = broker.subscribe()
    second = broker.subscribe()

    first.close()
    assert watchers[0].running, "stopped while a connection was still open"

    second.close()
    assert not watchers[0].running
    assert broker.connection_count == 0


def test_a_later_connection_starts_a_fresh_watcher(broker, watchers):
    """Restart builds a new watcher rather than reviving the stopped one.

    A FileWatcher primes itself in __init__, so a fresh instance both
    re-reads the current state of disk -- which moved while nobody was
    connected -- and sidesteps the restart race in reusing a thread that is
    still winding down from stop().
    """
    broker.subscribe().close()
    with broker.subscribe():
        assert len(watchers) == 2
        assert watchers[1].running
    assert not watchers[1].running


def test_closing_twice_is_harmless(broker, watchers):
    """The stream closes in a finally block and Flask may also close the
    generator; a double close must not stop a watcher someone else owns."""
    subscription = broker.subscribe()
    subscription.close()
    subscription.close()

    with broker.subscribe():
        assert watchers[1].running


# --------------------------------------------------------------------------
# Fan-out
# --------------------------------------------------------------------------

def test_an_event_reaches_every_connection(broker, watchers):
    with broker.subscribe() as first, broker.subscribe() as second:
        watchers[0].emit("trades")

        assert drain(first) == ["trades"]
        assert drain(second) == ["trades"]


def test_a_closed_connection_stops_receiving(broker, watchers):
    first = broker.subscribe()
    second = broker.subscribe()
    first.close()

    watchers[0].emit("trades")

    assert drain(first) == []
    assert drain(second) == ["trades"]


def test_the_event_carries_its_name_and_a_timestamp(broker, watchers):
    with broker.subscribe() as subscription:
        watchers[0].emit("scan")
        event = subscription.get(timeout=0)

    assert event.event == "scan"
    # Decision 3: thin. A name, a seq and a time -- never the object.
    assert event.data() == {"seq": event.seq, "at": event.at}
    assert event.at.endswith("+00:00")


def test_publish_survives_one_full_queue(broker, watchers):
    """One wedged consumer must not stop delivery to the healthy ones."""
    with broker.subscribe() as wedged, broker.subscribe() as healthy:
        for _ in range(b.QUEUE_LIMIT + 5):
            watchers[0].emit("trades")

        assert drain(healthy)[-1] == "trades"
        assert len(drain(wedged)) <= b.QUEUE_LIMIT


def test_an_overflowing_queue_collapses_to_a_resync(broker, watchers):
    """Decision 4: recovery is a resync, not a replay.

    A consumer too slow to keep up is in exactly the position of one that
    reconnected -- its data is stale and it does not matter how many events
    it missed. So the queue is not grown and events are not dropped
    silently: the backlog collapses to the one event that fixes any amount
    of staleness.
    """
    emitted = b.QUEUE_LIMIT * 2
    with broker.subscribe() as subscription:
        for _ in range(emitted):
            watchers[0].emit("trades")

        events = drain(subscription)

    # The resync leads what survives, and the events that arrived after the
    # collapse queue behind it -- the client refetches everything, then
    # applies what happened since, which is the right order for both.
    assert events[0] == "resync"
    assert set(events[1:]) <= {"trades"}
    assert len(events) <= b.QUEUE_LIMIT, "the backlog outgrew the queue"
    assert len(events) < emitted


def test_a_subscriber_that_raises_does_not_break_the_others(broker, watchers):
    """The watcher calls _publish from its own thread; an exception there
    kills the fan-out for everyone, so it must not escape one connection."""
    with broker.subscribe() as broken, broker.subscribe() as healthy:
        def explode(_event):
            raise RuntimeError("consumer exploded")

        broken._offer = explode

        watchers[0].emit("trades")

        assert drain(healthy) == ["trades"]


# --------------------------------------------------------------------------
# The sequence counter
# --------------------------------------------------------------------------

def test_seq_is_monotonic(broker, watchers):
    with broker.subscribe() as subscription:
        for _ in range(5):
            watchers[0].emit("trades")

        seqs = []
        while (event := subscription.get(timeout=0)) is not None:
            seqs.append(event.seq)

    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_one_event_carries_one_seq_on_every_connection(broker, watchers):
    """A single counter for the process, incremented once per event -- not
    once per delivery. Two tabs looking at the same change see the same id,
    and neither sees a gap."""
    with broker.subscribe() as first, broker.subscribe() as second:
        watchers[0].emit("trades")
        watchers[0].emit("account")

        first_seqs = [first.get(timeout=0).seq for _ in range(2)]
        second_seqs = [second.get(timeout=0).seq for _ in range(2)]

    assert first_seqs == second_seqs
    assert first_seqs[1] == first_seqs[0] + 1


def test_seq_does_not_restart_with_a_new_connection(broker, watchers):
    """Process-wide, per Decision 4 -- it is the SSE `id:` the browser sends
    back as Last-Event-ID, so a restart would make two events collide."""
    with broker.subscribe() as first:
        watchers[0].emit("trades")
        seen = first.get(timeout=0).seq

    with broker.subscribe() as second:
        watchers[1].emit("trades")
        assert second.get(timeout=0).seq > seen


def test_the_counter_is_thread_safe(make_broker, watchers):
    """_publish runs on the watcher thread, but a broker is a process-wide
    singleton and nothing stops two of them arriving at once."""
    broker = make_broker()
    with broker.subscribe() as subscription:
        emit = broker.publish
        threads = [
            threading.Thread(target=lambda: [emit("trades") for _ in range(20)])
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        seqs = []
        while (event := subscription.get(timeout=0)) is not None:
            seqs.append(event.seq)

    assert len(set(seqs)) == len(seqs), "the same seq was issued twice"


# --------------------------------------------------------------------------
# The connection cap
# --------------------------------------------------------------------------

def test_the_cap_is_eight(broker):
    """Decision 5: each SSE connection holds a Werkzeug thread for its
    lifetime, so the ceiling is a real resource and not a policy."""
    assert b.MAX_CONNECTIONS == 8

    subscriptions = [broker.subscribe() for _ in range(8)]
    try:
        assert broker.connection_count == 8
        with pytest.raises(ApiError) as raised:
            broker.subscribe()
    finally:
        for subscription in subscriptions:
            subscription.close()

    assert raised.value.status == 503
    assert raised.value.code == "unavailable"


def test_a_closed_connection_frees_a_slot(make_broker):
    """The cap must bound concurrency, not total connections ever made --
    otherwise an admin left open for a day stops working."""
    broker = make_broker(max_connections=2)
    first = broker.subscribe()
    second = broker.subscribe()
    with pytest.raises(ApiError):
        broker.subscribe()

    first.close()
    third = broker.subscribe()
    try:
        assert broker.connection_count == 2
    finally:
        second.close()
        third.close()


def test_a_rejected_connection_does_not_start_a_watcher(make_broker, watchers):
    """The failure path must not leave a stat() loop behind it, or a
    client reconnect bug leaks watchers instead of being refused."""
    broker = make_broker(max_connections=1)
    with broker.subscribe():
        with pytest.raises(ApiError):
            broker.subscribe()
        assert len(watchers) == 1


def test_the_cap_holds_under_concurrent_subscribers(make_broker):
    """Two tabs opening together must not both pass a check-then-act."""
    broker = make_broker(max_connections=4)
    granted = []
    refused = []
    barrier = threading.Barrier(12)

    def connect():
        barrier.wait(timeout=5)
        try:
            granted.append(broker.subscribe())
        except ApiError:
            refused.append(1)

    threads = [threading.Thread(target=connect) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    try:
        assert len(granted) == 4
        assert len(refused) == 8
    finally:
        for subscription in granted:
            subscription.close()


# --------------------------------------------------------------------------
# The process-wide singleton
# --------------------------------------------------------------------------

def test_get_broker_returns_the_same_broker(monkeypatch):
    monkeypatch.setattr(b, "_BROKER", None)

    first = b.get_broker()
    assert b.get_broker() is first


def test_the_default_broker_watches_real_files(monkeypatch):
    """The factory default must be the real FileWatcher -- a broker wired to
    nothing would pass every test above and push no events in production."""
    monkeypatch.setattr(b, "_BROKER", None)

    broker = b.get_broker()
    with broker.subscribe():
        watcher = broker._watcher
        try:
            assert isinstance(watcher, b.FileWatcher)
        finally:
            pass
    assert broker.connection_count == 0
