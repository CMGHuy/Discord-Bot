"""NG22 — GET /api/v1/events, the SSE endpoint.

NG19 TRIAGE: KEEP unchanged. This tests `swingbot/admin/events/stream.py`,
a v1 route with no Jinja involvement; it survives the cutover untouched.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v12-realtime-push-design.md`,
Decisions 3 (thin events), 4 (resync, not replay) and 5 (auth, and the cap).

**Nothing here consumes the stream to exhaustion.** `event_stream` is an
infinite generator by design -- it ends when the client hangs up -- so a
test that asks the Flask test client for `response.data` hangs the suite
rather than failing it. The frames are pulled one at a time from the
response iterator and the generator is closed by hand, and the pings are
driven by a fake subscription rather than by waiting 20 real seconds.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_error

from swingbot.admin.events import broker as b

# stream.py is an endpoint module: it imports api_v1.auth, which imports
# swingbot.admin.app -- and app.py only calls api_v1.register() at the very
# bottom of its own body. Importing stream FIRST re-enters register() while
# app.py is still executing and trips the circular import api_v1 documents
# (auth ends up partially initialised and every endpoint module's
# `from .auth import require_auth` fails). Importing the app module first
# makes the required ordering explicit: by the time it returns, register()
# has already imported stream, so the line below is a sys.modules lookup.
import swingbot.admin.app  # noqa: E402,F401  (must precede the next import)

from swingbot.admin.events import stream as s  # noqa: E402


class FakeWatcher:
    def __init__(self, emit):
        self.emit = emit

    def start(self):
        return self

    def stop(self):
        return None


@pytest.fixture
def broker(monkeypatch):
    """A broker whose watcher is inert, installed as the process singleton.

    The real listener would open a Postgres connection against the test's
    tmp_path for the life of every connection these tests open.
    """
    made = b.EventBroker(watcher_factory=lambda emit: FakeWatcher(emit))
    monkeypatch.setattr(b, "_BROKER", made)
    monkeypatch.setattr(s, "get_broker", lambda: made)
    return made


def frames(text: str) -> list[dict]:
    """Parse SSE wire text into `{name, id, data}` dicts."""
    parsed = []
    for block in text.strip("\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(": ")
            fields[key] = value
        parsed.append({
            "name": fields.get("event"),
            "id": fields.get("id"),
            "data": json.loads(fields["data"]),
        })
    return parsed


def take(response, count: int) -> list[dict]:
    """Pull exactly `count` frames, then close the generator.

    The frames arrive as bytes: `event_stream` yields str and WSGI encodes
    on the way out, which is worth decoding explicitly here rather than
    hiding, since it is what actually goes over the wire.
    """
    iterator = iter(response.response)
    chunks = [next(iterator).decode("utf-8") for _ in range(count)]
    response.response.close()
    return frames("".join(chunks))


# --------------------------------------------------------------------------
# Auth — before the stream opens
# --------------------------------------------------------------------------

def test_unauthenticated_gets_the_v1_401_body(client, broker):
    """Decision 5. A 401 must arrive as a JSON response, not as a stream
    that opens and then hangs up -- the client cannot tell the latter from
    a network blip, and retries it forever."""
    response = client.get("/api/v1/events")

    assert response.status_code == 401
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.get_json()["error"]["code"] == "auth"


def test_a_refused_connection_is_not_registered(client, broker):
    assert broker.connection_count == 0
    client.get("/api/v1/events")
    assert broker.connection_count == 0


def test_authenticated_opens_an_event_stream(client, auth, broker):
    response = client.get("/api/v1/events", headers=auth)
    try:
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        # Nginx buffers proxied responses by default, which turns an event
        # push into a batch push with no error anywhere.
        assert response.headers["X-Accel-Buffering"] == "no"
    finally:
        response.response.close()


# --------------------------------------------------------------------------
# The wire format
# --------------------------------------------------------------------------

def test_the_stream_opens_with_a_resync(client, auth, broker):
    """Decision 4: a client that has just arrived is displaying data of
    unknown age, which is the same problem as a reconnect."""
    response = client.get("/api/v1/events", headers=auth)

    assert take(response, 1)[0]["name"] == "resync"


def test_an_event_reaches_the_wire_in_the_spec_shape(client, auth, broker):
    response = client.get("/api/v1/events", headers=auth)
    broker.publish("trades")

    opening, event = take(response, 2)

    assert opening["name"] == "resync"
    assert event["name"] == "trades"
    assert event["id"] == str(broker.seq)
    # Decision 3: thin. A seq and a time -- never the object, and not even
    # the event name, which travels in `event:` where addEventListener
    # dispatches on it.
    assert set(event["data"]) == {"seq", "at"}
    assert event["data"]["seq"] == broker.seq


def test_the_opening_resync_does_not_consume_a_seq(client, auth, broker):
    """It carries the high-water mark. Issuing a fresh number for an event
    only one connection sees would leave a permanent gap in every other
    open connection's ids."""
    broker.publish("trades")
    before = broker.seq

    response = client.get("/api/v1/events", headers=auth)
    opening = take(response, 1)[0]

    assert broker.seq == before
    assert opening["data"]["seq"] == before
    assert opening["id"] == str(before)


def test_every_connection_gets_its_own_stream(client, admin_app, auth, broker):
    second = admin_app.test_client()
    first_response = client.get("/api/v1/events", headers=auth)
    second_response = second.get("/api/v1/events", headers=auth)

    broker.publish("scan")

    first = take(first_response, 2)[1]
    other = take(second_response, 2)[1]

    assert first["name"] == other["name"] == "scan"
    assert first["id"] == other["id"], "one change, one id, on every tab"


# --------------------------------------------------------------------------
# Pings
# --------------------------------------------------------------------------

class SilentSubscription:
    """A subscription that only ever times out. Records the waits."""

    def __init__(self):
        self.timeouts = []
        self.closed = False

    def get(self, timeout=None):
        self.timeouts.append(timeout)
        return None

    def close(self):
        self.closed = True


def test_silence_produces_a_ping(broker):
    subscription = SilentSubscription()
    generator = s.event_stream(subscription, broker, ping_interval=0.01)
    try:
        parsed = frames(next(generator) + next(generator))
    finally:
        generator.close()

    assert [f["name"] for f in parsed] == ["resync", "ping"]
    assert subscription.timeouts == [0.01]


def test_the_ping_interval_is_twenty_seconds(broker):
    """Long enough to be free, short enough to beat the proxy and browser
    idle timeouts that would otherwise drop a quiet connection."""
    assert s.PING_INTERVAL == 20.0

    subscription = SilentSubscription()
    generator = s.event_stream(subscription, broker)
    try:
        next(generator)
        next(generator)
    finally:
        generator.close()

    assert subscription.timeouts == [20.0]


def test_a_ping_carries_no_id(broker):
    """It is not a change. An id would have the browser hand it back as
    Last-Event-ID, naming a position at which nothing happened."""
    subscription = SilentSubscription()
    generator = s.event_stream(subscription, broker, ping_interval=0.01)
    try:
        next(generator)
        ping = frames(next(generator))[0]
    finally:
        generator.close()

    assert ping["name"] == "ping"
    assert ping["id"] is None
    assert set(ping["data"]) == {"at"}


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

def test_closing_the_stream_releases_the_slot(client, auth, broker):
    """The cap is 8 and every connection ends by hanging up, so a slot not
    released on close turns the cap into a countdown to an admin that can
    no longer stream at all."""
    response = client.get("/api/v1/events", headers=auth)
    next(iter(response.response))
    assert broker.connection_count == 1

    response.response.close()

    assert broker.connection_count == 0


def test_the_generator_closes_its_subscription(broker):
    subscription = SilentSubscription()
    generator = s.event_stream(subscription, broker, ping_interval=0.01)
    next(generator)
    generator.close()

    assert subscription.closed


def test_past_the_cap_the_answer_is_503_unavailable(client, auth, broker, monkeypatch):
    """Decision 5. Each open stream holds a Werkzeug thread for its
    lifetime, so this is a resource ceiling, not a policy."""
    monkeypatch.setattr(broker, "_max_connections", 1)
    first = client.get("/api/v1/events", headers=auth)
    try:
        response = client.get("/api/v1/events", headers=auth)

        assert response.status_code == 503
        assert response.headers["Content-Type"].startswith("application/json")
        assert response.get_json()["error"]["code"] == "unavailable"
    finally:
        first.response.close()


def test_a_slot_freed_by_a_hangup_is_reusable(client, auth, broker, monkeypatch):
    monkeypatch.setattr(broker, "_max_connections", 1)
    first = client.get("/api/v1/events", headers=auth)
    next(iter(first.response))
    first.response.close()

    second = client.get("/api/v1/events", headers=auth)
    try:
        assert second.status_code == 200
    finally:
        second.response.close()


def test_last_event_id_is_accepted_but_not_replayed(client, auth, broker, caplog):
    """Decision 4: the header stays in the protocol because it costs nothing
    and is where replay would be built from -- but the stream still opens
    with a resync and nothing before it is re-sent."""
    broker.publish("trades")
    broker.publish("account")

    response = client.get(
        "/api/v1/events", headers={**auth, "Last-Event-ID": "1"}
    )
    opening = take(response, 1)[0]

    assert opening["name"] == "resync"
    assert opening["data"]["seq"] == broker.seq, "replayed from the given id"


# --------------------------------------------------------------------------
# v207: the principal is re-checked on every loop pass
# --------------------------------------------------------------------------

class OneEventSubscription(SilentSubscription):
    """A subscription that always has an event waiting."""

    def get(self, timeout=None):
        self.timeouts.append(timeout)
        return b.Event(seq=7, event="trades", at="2026-11-05T00:00:00+00:00")


def test_the_stream_ends_when_still_valid_turns_false(broker):
    subscription = SilentSubscription()
    valid = {"ok": True}
    generator = s.event_stream(subscription, broker, ping_interval=0.01,
                               still_valid=lambda: valid["ok"])
    assert next(generator).startswith("event: resync")
    assert next(generator).startswith("event: ping")
    valid["ok"] = False
    with pytest.raises(StopIteration):
        next(generator)
    assert subscription.closed


def test_a_revoked_principal_is_not_sent_the_waiting_event(broker):
    subscription = OneEventSubscription()
    generator = s.event_stream(subscription, broker, ping_interval=0.01,
                               still_valid=lambda: False)
    assert next(generator).startswith("event: resync")
    with pytest.raises(StopIteration):
        next(generator)
    assert subscription.closed


def test_session_snapshot_copies_only_the_principal_fields(admin_app):
    from flask import session

    with admin_app.test_request_context("/api/v1/events"):
        session.update({"role": "viewer", "user_id": 4, "credential_version": 2,
                        "username": "viewer1", "unrelated": "x"})
        snapshot = s.session_snapshot()
    assert snapshot == {"role": "viewer", "user_id": 4, "credential_version": 2,
                        "username": "viewer1"}


def test_a_viewer_disabled_mid_stream_is_cut_off(viewer_client, broker, monkeypatch):
    from swingbot.core.db.repositories.admin_users import admin_users_repo

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    client, row = viewer_client
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    iterator = iter(response.response)
    assert next(iterator).decode("utf-8").startswith("event: resync")
    assert next(iterator).decode("utf-8").startswith("event: ping")
    admin_users_repo().set_disabled(row["id"], True)
    with pytest.raises(StopIteration):
        next(iterator)
    response.response.close()
    assert_error(client.get("/api/v1/events"), "auth", 401)


def test_an_admin_session_stream_ends_when_the_admin_password_changes(client, broker,
                                                                      monkeypatch):
    from swingbot.admin import app as admin_module

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    response = client.get("/api/v1/events")
    iterator = iter(response.response)
    assert next(iterator).decode("utf-8").startswith("event: resync")
    monkeypatch.setattr(admin_module, "ADMIN_PASSWORD", "changed-password")
    with pytest.raises(StopIteration):
        next(iterator)
    response.response.close()


def test_a_basic_admin_stream_is_not_rechecked(client, auth, broker, monkeypatch):
    """Basic carries no session principal: nothing to revoke mid-stream."""
    from swingbot.admin import app as admin_module

    monkeypatch.setattr(s, "PING_INTERVAL", 0.01)
    response = client.get("/api/v1/events", headers=auth)
    monkeypatch.setattr(admin_module, "principal_from_session",
                        lambda data: pytest.fail("Basic stream re-checked a session"))
    names = [frame["name"] for frame in take(response, 3)]
    assert names == ["resync", "ping", "ping"]


def test_a_viewer_stream_carries_only_seq_and_at(viewer_client, broker):
    client, _row = viewer_client
    response = client.get("/api/v1/events")
    broker.publish("settings")
    resync, event = take(response, 2)
    assert event["name"] == "settings"
    assert set(event["data"]) == {"seq", "at"}
    assert set(resync["data"]) == {"seq", "at"}
