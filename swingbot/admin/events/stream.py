"""`GET /api/v1/events` — the SSE endpoint itself.

Spec: `docs/superpowers/specs/2026-08-08-v12-realtime-push-design.md`,
Decisions 3, 4 and 5.

The wire format is deliberately dull. An event says *what* changed and
nothing about how:

    event: trades
    id: 4812
    data: {"seq":4812,"at":"2026-08-08T14:03:11+00:00"}

The client refetches through the normal v1 endpoints, so there is no second
serialisation of a trade to keep in sync with the API -- see Decision 3 for
why the fat-event alternative was rejected.

Two shapes here are load-bearing:

**Everything that can fail, fails before the stream opens.** Auth and the
connection cap are both resolved in the view body, while a normal JSON
response is still possible. Once the generator is returned the status line
is already on the wire and a failure can only be expressed by hanging up,
which a client sees as a network blip and retries -- forever, in the case
of a 401.

**The generator never touches the request context.** `stream_with_context`
would keep the whole request alive for the connection's lifetime, which for
SSE is hours. Anything the body needs (the `Last-Event-ID` header) is read
in the view and passed in.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Iterator

from flask import Response, request

from swingbot.admin.api_v1 import api_v1, iso
from swingbot.admin.api_v1.auth import require_auth

from .broker import EventBroker, Subscription, get_broker

log = logging.getLogger("swing-bot.admin.events")

#: Seconds of silence before a comment-free keep-alive goes out. Proxies and
#: browsers both drop an idle connection, and the client cannot tell that
#: from a server with nothing to say.
PING_INTERVAL = 20.0


def _frame(name: str, data: dict, *, event_id: int | None = None) -> str:
    """One SSE frame: `event:`, optionally `id:`, `data:`, blank line.

    Compact JSON separators because this is a keep-alive-heavy stream and
    the frames are almost all overhead already.
    """
    lines = [f"event: {name}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append("data: " + json.dumps(data, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


def _now() -> str:
    return iso(datetime.now(timezone.utc))


def event_stream(
    subscription: Subscription,
    broker: EventBroker,
    *,
    ping_interval: float = PING_INTERVAL,
) -> Iterator[str]:
    """Frames for one connection, until the consumer closes the generator.

    Opens with a `resync`. Decision 4: recovery is a resync and not a
    replay, and that applies to the first connection exactly as it does to
    the thousandth reconnect -- the client has just arrived, whatever it is
    displaying is of unknown age, and one refetch fixes that regardless of
    how long it was away or how much it missed.
    """
    try:
        # The current high-water mark, not a fresh number: see EventBroker.seq.
        yield _frame("resync", {"seq": broker.seq, "at": _now()}, event_id=broker.seq)
        while True:
            event = subscription.get(timeout=ping_interval)
            if event is None:
                # No `id:` -- a ping is not a change, and giving it one would
                # have the browser hand it back as Last-Event-ID, naming a
                # position at which nothing happened.
                yield _frame("ping", {"at": _now()})
            else:
                yield _frame(event.event, event.data(), event_id=event.seq)
    finally:
        # Reached on GeneratorExit when the client hangs up, which is how
        # every one of these connections ends. Without it the slot is held
        # until the process restarts and the cap of 8 becomes a countdown.
        subscription.close()


@api_v1.route("/events", methods=["GET"])
@require_auth
def events():
    """Subscribe, then stream. Failures happen in that order for a reason.

    `require_auth` runs first and returns the v1 401 body before anything is
    streamed -- `EventSource` cannot set headers, so this authenticates by
    session cookie like every other v1 route. `subscribe()` raises
    `ApiError(503, "unavailable")` past the cap, which the app's error
    handler renders; both are ordinary JSON responses because neither has
    opened a stream yet.
    """
    broker = get_broker()
    subscription = broker.subscribe()

    last_event_id = request.headers.get("Last-Event-ID")
    if last_event_id:
        # Accepted and logged, never acted on (Decision 4). It stays in the
        # protocol because it costs nothing and is where replay would be
        # built from, if replay is ever wanted -- but a replay buffer means
        # a retention policy and a class of bug (overflow -> silently wrong
        # UI) to optimise a case the opening resync already handles.
        log.info("event connection resumed from Last-Event-ID %s", last_event_id)

    response = Response(
        event_stream(subscription, broker),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    # Nginx buffers proxied responses by default, which for a stream means
    # the browser sees nothing until the buffer fills -- i.e. an event push
    # that silently becomes a batch push. Harmless when absent.
    response.headers["X-Accel-Buffering"] = "no"
    return response
