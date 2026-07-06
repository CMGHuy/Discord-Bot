"""!watchlist and its subcommands."""
import asyncio

from swingbot.bot_core import bot
from swingbot.core.data import get_daily_data
from swingbot.core.watchlist import add_ticker, clear_watchlist, load_watchlist, remove_ticker


@bot.group(name="watchlist", invoke_without_command=True)
async def watchlist_cmd(ctx):
    tickers = load_watchlist()
    await ctx.send(f"Current watchlist: {', '.join(tickers) if tickers else '(empty)'}")


@watchlist_cmd.command(name="add")
async def watchlist_add(ctx, ticker: str):
    tickers = add_ticker(ticker)
    await ctx.send(f"Added **{ticker.upper()}**. Watchlist: {', '.join(tickers)}")

    try:
        await asyncio.to_thread(get_daily_data, ticker, "5d")
    except Exception as e:
        await ctx.send(
            f"⚠️ Heads up: couldn't fetch data for **{ticker.upper()}** ({e}). "
            f"It's still in your watchlist, but scans will skip it until this resolves. "
            f"Common fixes: indices use Yahoo's `^` format (S&P 500 = `^GSPC`), metals use "
            f"futures tickers (gold = `GC=F`, silver = `SI=F`), forex needs a `=X` suffix "
            f"(e.g. `EURUSD=X`). Use `!watchlist remove {ticker.upper()}` if you want to try a different symbol."
        )


@watchlist_cmd.command(name="remove")
async def watchlist_remove(ctx, ticker: str):
    tickers = remove_ticker(ticker)
    await ctx.send(f"Removed **{ticker.upper()}**. Watchlist: {', '.join(tickers)}")


@watchlist_cmd.command(name="clear")
async def watchlist_clear(ctx):
    clear_watchlist()
    await ctx.send("Watchlist cleared.")
