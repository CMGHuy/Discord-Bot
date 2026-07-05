"""!watchlist and its subcommands."""
import asyncio

from swingbot.bot_core import bot
from swingbot.core.data import get_daily_data, get_ticker_logo
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


@watchlist_cmd.command(name="fetchlogos")
async def watchlist_fetchlogos(ctx):
    """
    Pre-downloads and caches a logo for every ticker currently in the
    watchlist (data/logos/<TICKER>.png). Already-cached tickers resolve
    instantly, so this is safe to re-run any time after adding new tickers.

    Logos are used to stamp generated trade charts (core/trade_chart.py)
    and are shown next to each ticker in the admin UI's Watchlist,
    Dashboard, and trade-detail pages.
    """
    tickers = load_watchlist()
    await ctx.send(f"Fetching logos for **{len(tickers)}** ticker(s)… this can take a bit.")

    found, missing = [], []
    for t in tickers:
        logo = await asyncio.to_thread(get_ticker_logo, t)
        (found if logo is not None else missing).append(t)

    msg = f"✅ Logos ready for **{len(found)}/{len(tickers)}** ticker(s)."
    if missing:
        msg += f"\n⚠️ No logo found for: {', '.join(missing)} (unusual symbols, indices, futures, etc. often don't have one)."
    await ctx.send(msg)
