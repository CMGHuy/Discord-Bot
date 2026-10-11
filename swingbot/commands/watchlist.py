"""!watchlist and its subcommands, and the /watchlist twin (v153).

One handler, handle_watchlist(reply, action, ticker), answers both surfaces.
Its actions are the WATCHLIST_ACTIONS table, whose keys are also the
/watchlist `action` choice values.
"""
import asyncio
import logging
from typing import Awaitable, Callable

import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core.marketdata.backtest_cache import ensure_cached_background
from swingbot.core.marketdata.data import get_daily_data
from swingbot.core.marketdata.watchlist import add_ticker, clear_watchlist, load_watchlist, remove_ticker

log = logging.getLogger(__name__)

MISSING_TICKER = "Please provide a ticker for add/remove actions."
_NEEDS_TICKER = ("add", "remove")


async def _watchlist_show(reply, ticker: str | None = None) -> None:
    tickers = load_watchlist()
    await reply.send(f"Current watchlist: {', '.join(tickers) if tickers else '(empty)'}")


async def _watchlist_add(reply, ticker: str | None) -> None:
    tickers = add_ticker(ticker)
    # Kick off the full-history backtest-cache download in the background
    # (non-blocking; logs when done). Skips instantly if already cached.
    ensure_cached_background(ticker)
    await reply.send(f"Added **{ticker}**. Watchlist: {', '.join(tickers)}")

    try:
        await asyncio.to_thread(get_daily_data, ticker, "5d")
    except Exception as e:
        log.warning("!watchlist add %s: could not fetch data", ticker, exc_info=True)
        await reply.send(
            f"⚠️ Heads up: couldn't fetch data for **{ticker}** ({e}). "
            f"It's still in your watchlist, but scans will skip it until this resolves. "
            f"Common fixes: indices use Yahoo's `^` format (S&P 500 = `^GSPC`), spot metals are "
            f"gold = `XAUUSD`, silver = `XAGUSD` (futures `GC=F` / `SI=F` still work and stay "
            f"futures-priced), forex needs a `=X` suffix "
            f"(e.g. `EURUSD=X`). Use `!watchlist remove {ticker}` if you want to try a different symbol."
        )


async def _watchlist_remove(reply, ticker: str | None) -> None:
    tickers = remove_ticker(ticker)
    await reply.send(f"Removed **{ticker}**. Watchlist: {', '.join(tickers)}")


async def _watchlist_clear(reply, ticker: str | None = None) -> None:
    clear_watchlist()
    await reply.send("Watchlist cleared.")


WATCHLIST_ACTIONS: dict[str, Callable[..., Awaitable[None]]] = {
    "show": _watchlist_show,
    "add": _watchlist_add,
    "remove": _watchlist_remove,
    "clear": _watchlist_clear,
}


async def handle_watchlist(reply, action: str = "show", ticker: str | None = None) -> None:
    """Show, add, remove or clear. add/remove need a ticker; it is upper-cased."""
    run = WATCHLIST_ACTIONS.get(action)
    if run is None:
        await reply.send_error(
            f"Unknown watchlist action `{action}`. Use one of: {', '.join(WATCHLIST_ACTIONS)}."
        )
        return
    if action in _NEEDS_TICKER and not ticker:
        await reply.send_error(MISSING_TICKER)
        return
    await reply.defer()
    await run(reply, ticker.upper() if ticker else None)


# Each prefix command calls the handler itself (the index's prefix pattern),
# so SP18's one-body check sees the call inside the command.

@bot.group(name="watchlist", invoke_without_command=True)
async def watchlist_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "show")
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="add")
async def watchlist_add(ctx, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "add", ticker)
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="remove")
async def watchlist_remove(ctx, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "remove", ticker)
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="clear")
async def watchlist_clear(ctx):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "clear")
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /watchlist (moved from slash.py in v153; payload unchanged)
# ──────────────────────────────────────────────

@bot.tree.command(name="watchlist", description="Show, add, or remove tickers from the watchlist")
@app_commands.describe(
    action="Action to perform (leave blank to just show the list)",
    ticker="Ticker to add or remove",
)
@app_commands.choices(action=[
    app_commands.Choice(name="Show",   value="show"),
    app_commands.Choice(name="Add",    value="add"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Clear",  value="clear"),
])
async def slash_watchlist(
    interaction: discord.Interaction,
    action: app_commands.Choice[str] = None,
    ticker: str = None,
):
    await handle_watchlist(InteractionReply(interaction), action.value if action else "show", ticker)
