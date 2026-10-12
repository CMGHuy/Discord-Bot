"""One answer surface for prefix (`!`) and slash (`/`) commands (v153).

Every command body is an `async def handle_<name>(reply, <typed args>)`
next to its prefix command. The prefix command wraps its `ctx` in
`CtxReply`; the slash twin, defined in the same module, wraps its
`interaction` in `InteractionReply`. A handler answers only through the
`Reply` members below and never touches `ctx` or `interaction`.

Both implementations forward only non-None keyword arguments: discord.py's
`Webhook.send` raises on `view=None` / `file=None`.

`SLASH_TWIN` maps every qualified prefix name, as `bot.walk_commands()`
yields it, to its slash path. The tip line and the parity test
(`tests/commands/test_slash_parity.py`) read it; nothing else maps names.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Callable, Protocol, runtime_checkable

CHUNK = 1900                  # Discord caps a message at 2000 chars
TOKEN_LIFETIME_S = 14 * 60    # interaction tokens die at 15 min; keep a minute's margin
# Deploy day (2026-10-12) + 90 days; on and after it `prefix_tip` returns
# None and the tip line retires itself (pinned by plan v153 SP21). A date
# check, not a config key. Owner: the partner. Deleting this constant and the
# tip helpers is folded into the next plan that touches this file.
PREFIX_TIP_UNTIL = dt.date(2027, 1, 10)

SLASH_TWIN: dict[str, str] = {
    # account.py -- `!account` alone runs, so it maps to a `show` subcommand
    "account": "account show",
    "account balance": "account balance",
    "account risk": "account risk",
    "account maxpositions": "account maxpositions",
    "account sizing": "account sizing",
    "account positionpct": "account positionpct",
    "account maxpositionpct": "account maxpositionpct",
    "account maxposition": "account maxposition",
    "account maxrisk": "account maxrisk",
    # backtest.py
    "backtest": "backtest",
    "backtestwatchlist": "backtestwatchlist",
    # data.py
    "charts": "charts",
    "download": "download",
    "cached": "cached",
    "scrapeall": "scrapeall",
    # growth.py
    "growth": "growth",
    "killswitch": "killswitch",
    "portfolio": "portfolio",
    # history.py
    "plans": "plans",
    # info.py
    "strategies": "strategies",
    "confidence": "confidence",
    "ticker": "ticker",
    "strategycharts": "strategycharts",
    "regime": "regime",
    "ping": "ping",
    "commands": "help",
    # plans.py
    "liveplans": "liveplans",
    # scanning/commands.py
    "recap": "recap",
    "check": "check",
    "session": "session",
    "status": "status",
    "pause": "pause",
    "resume": "resume",
    "stop": "stop",
    # stats.py
    "soak": "soak",
    "top": "top",
    "stats": "stats",
    "lessons": "lessons",
    "calibration": "calibration",
    "journal": "journal",
    # trades.py -- `/trades` already exists as a plain command, so the clear
    # subcommands become hyphenated top-level names
    "trades": "trades",
    "trades clear": "trades-clear",
    "trades clear history": "trades-clear-history",
    "trade": "trade show",
    "trade delete": "trade delete",
    "tradecharts": "tradecharts",
    "performance": "performance",
    "pnl": "pnl",
    "summary": "summary",
    # watchlist.py -- `/watchlist` dispatches on its `action` choice
    "watchlist": "watchlist show",
    "watchlist add": "watchlist add",
    "watchlist remove": "watchlist remove",
    "watchlist clear": "watchlist clear",
}


def _content_args(content: str | None) -> tuple:
    """`content` positional when present -- tests read `call.args[0]`."""
    return () if content is None else (content,)


def _media_kwargs(embed: Any, file: Any, files: Any, view: Any, silent: bool) -> dict:
    kw = {name: value for name, value in
          (("embed", embed), ("file", file), ("files", files), ("view", view))
          if value is not None}
    if silent:
        kw["silent"] = True
    return kw


def _chunks(text: str) -> list[str]:
    return [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]


@runtime_checkable
class Reply(Protocol):
    """What a handler may use. `send` returns an editable handle."""

    failed: bool

    @property
    def author(self) -> Any: ...

    @property
    def channel(self) -> Any: ...

    @property
    def stale(self) -> bool: ...

    async def defer(self, ephemeral: bool = False) -> None: ...

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any: ...

    async def send_chunks(self, text: str, *, ephemeral: bool = False) -> None: ...

    async def send_error(self, text: str, *, ephemeral: bool = True) -> Any: ...


class _ReplyBase:
    """`send_chunks` and `send_error`, shared; subclasses implement `send`."""

    def __init__(self) -> None:
        self.failed = False

    async def send(self, content: str | None = None, **kw: Any) -> Any:
        raise NotImplementedError

    async def send_chunks(self, text: str, *, ephemeral: bool = False) -> None:
        for chunk in _chunks(text):
            await self.send(chunk, ephemeral=ephemeral)

    async def send_error(self, text: str, *, ephemeral: bool = True) -> Any:
        handle = await self.send(text, ephemeral=ephemeral)
        self.failed = True
        return handle


class CtxReply(_ReplyBase):
    """A prefix command's answer. `defer` and `ephemeral` are documented
    no-ops: a prefix reply is always a plain channel message, as before."""

    def __init__(self, ctx: Any) -> None:
        super().__init__()
        self._ctx = ctx

    @property
    def author(self) -> Any:
        return self._ctx.author

    @property
    def channel(self) -> Any:
        return self._ctx.channel

    @property
    def stale(self) -> bool:
        return False

    async def defer(self, ephemeral: bool = False) -> None:
        return None

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any:
        kw = _media_kwargs(embed, file, files, view, silent)
        return await self._ctx.send(*_content_args(content), **kw)


class InteractionReply(_ReplyBase):
    """A slash command's answer.

    First send without a defer -> `response.send_message` and the
    `original_response()` handle; every later send -> `followup.send(wait=True)`
    and its `WebhookMessage`. Once `stale` (the 15-minute token may be
    dead), `send` posts with `interaction.channel.send` instead, without
    `ephemeral`, so a long `/scrapeall` loses late progress edits but never
    its result."""

    def __init__(self, interaction: Any, *, clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__()
        self._interaction = interaction
        self._clock = clock
        self._started = clock()

    @property
    def author(self) -> Any:
        return self._interaction.user

    @property
    def channel(self) -> Any:
        return self._interaction.channel

    @property
    def stale(self) -> bool:
        return self._clock() - self._started >= TOKEN_LIFETIME_S

    async def defer(self, ephemeral: bool = False) -> None:
        response = self._interaction.response
        if self.stale or response.is_done():
            return
        await response.defer(thinking=True, ephemeral=ephemeral)

    async def send(self, content: str | None = None, *, embed: Any = None, file: Any = None,
                   files: Any = None, view: Any = None, ephemeral: bool = False,
                   silent: bool = False) -> Any:
        kw = _media_kwargs(embed, file, files, view, silent)
        args = _content_args(content)
        if self.stale:
            return await self._interaction.channel.send(*args, **kw)
        if ephemeral:
            kw["ephemeral"] = True
        response = self._interaction.response
        if not response.is_done():
            await response.send_message(*args, **kw)
            return await self._interaction.original_response()
        return await self._interaction.followup.send(*args, wait=True, **kw)


def _today() -> dt.date:
    """Seam for tests (monkeypatched)."""
    return dt.date.today()


def prefix_tip(qualified_name: str, today: dt.date) -> str | None:
    """The one-line nudge to a prefix command's slash twin, until PREFIX_TIP_UNTIL."""
    twin = SLASH_TWIN.get(qualified_name)
    if twin is None or today >= PREFIX_TIP_UNTIL:
        return None
    return f"Tip: this is now /{twin}"


async def send_prefix_tip(ctx: Any, reply: Reply) -> None:
    """Send the tip after a successful prefix answer.

    Nothing is sent when the reply failed, when the command name is not a
    `str` key of SLASH_TWIN (a MagicMock ctx in older tests), or after the
    cutoff. A handler that raised never reaches this call."""
    name = getattr(getattr(ctx, "command", None), "qualified_name", None)
    if not isinstance(name, str) or reply.failed:
        return
    tip = prefix_tip(name, _today())
    if tip is not None:
        await reply.send(tip)
