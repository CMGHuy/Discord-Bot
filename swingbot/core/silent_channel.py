"""
The alerts channel never notifies.

Everything posted to DISCORD_CHANNEL_TRADES_ID -- trade alerts, the
"bot online" notice, session welcome/goodbye lines, config-change notices,
scan-progress messages, v2 fill events -- is sent with Discord's
SUPPRESS_NOTIFICATIONS flag (`silent=True`, the same thing the `@silent`
prefix does in the client). The message still posts, still renders in full,
and still marks the channel unread; it just raises no push/desktop
notification.

This is enforced at the point the channel is *resolved*, not at each
`send()` call site, because "this channel is quiet" is a property of the
channel, not of any one message. There are a dozen-odd places that resolve
the alerts channel and then hand the object off to a helper
(_check_session_transition, _post_daily_digest, _post_healthcheck,
_send_alerts, the admin-UI progress poller) which does its own sending --
threading a `silent=` flag through all of them would leave the policy one
forgotten keyword away from breaking, and any *future* send would default
back to notifying. Wrapping once at resolution means every send through
that object is covered, including ones not written yet.

Only DISCORD_CHANNEL_TRADES_ID is wrapped. The simple mirror
(DISCORD_CHANNEL_TRADES_SIMPLE_ID), the firehose, the closed-trades history
channel and a user's own `ctx` are deliberately left alone -- they are how a
signal still reaches you.
"""


class SilentChannel:
    """Thin proxy over a discord.py messageable that forces `silent=True`.

    Every other attribute (id, name, guild, purge, fetch_message, ...)
    delegates to the wrapped channel, and `send()` returns the real
    `discord.Message` -- so callers that keep the returned message around to
    edit or delete it later (the admin-UI progress message, the healthcheck
    hourly cleanup) work unchanged.

    A caller-supplied `silent=` is overwritten rather than honoured: this
    channel's whole contract is that nothing sent through it can ping.
    """

    __slots__ = ("_channel",)

    def __init__(self, channel):
        self._channel = channel

    async def send(self, *args, **kwargs):
        kwargs["silent"] = True
        return await self._channel.send(*args, **kwargs)

    def __getattr__(self, name):
        # Only reached for names not in __slots__, i.e. everything but
        # _channel -- so this never recurses.
        return getattr(self._channel, name)

    def __eq__(self, other):
        if isinstance(other, SilentChannel):
            return self._channel == other._channel
        return self._channel == other

    def __hash__(self):
        return hash(self._channel)

    def __repr__(self):
        return f"SilentChannel({self._channel!r})"


def silence(channel):
    """Wrap `channel` so nothing sent through it notifies.

    `None` passes straight through so the callers' existing
    "channel is None -> log a warning and bail" handling is untouched, and
    an already-wrapped channel is returned as-is so double-wrapping is a
    no-op rather than a second layer of proxy.
    """
    if channel is None or isinstance(channel, SilentChannel):
        return channel
    return SilentChannel(channel)
