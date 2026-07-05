"""!charts, !download, !cached, !scrapeall."""
import asyncio
import os
import shutil

import discord

from swingbot import config
from swingbot.bot_core import bot
from swingbot.core import export_data
from swingbot.core.data_store import DATA_DIR as CACHE_DIR, INTERVAL_CONFIG, download_and_cache
from swingbot.core.export_data import export_ticker
from swingbot.core.watchlist import load_watchlist


@bot.command(name="charts")
async def charts_cmd(ctx):
    tickers = load_watchlist()
    await ctx.send(f"Downloading full historical daily data for {len(tickers)} ticker(s)… this can take a bit.")

    if os.path.exists(config.EXPORT_DIR):
        shutil.rmtree(config.EXPORT_DIR)
    os.makedirs(config.EXPORT_DIR, exist_ok=True)

    for ticker in tickers:
        try:
            result = await asyncio.to_thread(export_ticker, ticker, config.EXPORT_DIR)
        except Exception as e:
            await ctx.send(f"⚠️ Could not export {ticker}: {e}")
            continue

        await ctx.send(
            content=f"**{ticker}** — {result['bars']} trading days of history",
            files=[
                discord.File(result["csv"]),
                discord.File(result["recent_chart"]),
                discord.File(result["full_chart"]),
            ],
        )

    await ctx.send("Done — all watchlist history exported above.")


@bot.command(name="download")
async def download_cmd(ctx, interval: str, ticker: str = None):
    interval = interval.lower()
    if interval not in INTERVAL_CONFIG:
        await ctx.send(f"Unknown interval '{interval}'. Use one of: {', '.join(INTERVAL_CONFIG)}")
        return

    tickers = [ticker.upper()] if ticker else load_watchlist()
    cfg = INTERVAL_CONFIG[interval]

    if interval == "1m":
        await ctx.send(
            f"⚠️ Heads up: Yahoo Finance only provides **1-minute** candles for the trailing **~30 days** — "
            f"there's no source for years of 1-minute history for free. Pulling the maximum available "
            f"(~30 days) for {len(tickers)} ticker(s) now and caching it to disk…"
        )
    elif cfg["max_days"] is not None:
        await ctx.send(f"Downloading {interval} data (max ~{cfg['max_days']} days available from Yahoo) for {len(tickers)} ticker(s)…")
    else:
        await ctx.send(f"Downloading full {interval} history for {len(tickers)} ticker(s)…")

    results = []
    for t in tickers:
        try:
            info = await asyncio.to_thread(download_and_cache, t, interval)
            results.append(info)
        except Exception as e:
            await ctx.send(f"⚠️ {t}: {e}")

    if not results:
        await ctx.send("Nothing downloaded.")
        return

    lines = ["**Cached to disk:**", "```"]
    lines.append(f"{'Ticker':8s} {'Rows':>7s} {'From':19s} {'To':19s}")
    for r in results:
        lines.append(f"{r['ticker']:8s} {r['rows']:7d} {r['start'][:19]:19s} {r['end'][:19]:19s}")
    lines.append("```")
    await ctx.send("\n".join(lines))


@bot.command(name="cached")
async def cached_cmd(ctx):
    base_dir = CACHE_DIR
    if not os.path.exists(base_dir):
        await ctx.send("Nothing cached yet. Use `!download INTERVAL [TICKER]` first.")
        return

    lines = ["**Locally cached data:**", "```"]
    lines.append(f"{'Ticker':8s} {'Interval':9s} {'Rows':>7s} {'Size':>8s}")
    found = False
    for ticker_dir in sorted(os.listdir(base_dir)):
        full_dir = os.path.join(base_dir, ticker_dir)
        if not os.path.isdir(full_dir):
            continue
        for fname in sorted(os.listdir(full_dir)):
            path = os.path.join(full_dir, fname)
            interval = fname.replace(".csv", "")
            size_kb = os.path.getsize(path) / 1024
            with open(path) as f:
                rows = sum(1 for _ in f) - 1
            lines.append(f"{ticker_dir:8s} {interval:9s} {rows:7d} {size_kb:7.0f}K")
            found = True
    lines.append("```")
    if not found:
        await ctx.send("Nothing cached yet. Use `!download INTERVAL [TICKER]` first.")
        return
    await ctx.send("\n".join(lines))


@bot.command(name="scrapeall")
async def scrapeall_cmd(ctx, mode: str = "cached"):
    """
    Downloads FULL ("all time", period="max") daily history for EVERY
    ticker in the watchlist at once, concurrently -- see
    export_data.py's module docstring for the stock-market-scraper
    ideas this borrows. Skips a ticker entirely if it was already
    scraped within the last ~20h, unless `!scrapeall force` is used.

    Unlike !charts, this does NOT post every CSV/chart to the channel
    (dozens of file uploads for a full watchlist isn't practical) --
    it saves everything to exports/full_history/ on disk (persisted via
    the Docker volume) and posts a summary table, or a CSV attachment
    if the watchlist is too big for one Discord message.
    """
    mode = mode.lower()
    if mode not in ("cached", "force"):
        await ctx.send("Usage: `!scrapeall` (skip tickers already scraped in the last ~20h) or `!scrapeall force` (re-download everything).")
        return
    force = mode == "force"

    tickers = load_watchlist()
    if not tickers:
        await ctx.send("Watchlist is empty -- add tickers with `!watchlist add TICKER` first.")
        return

    out_dir = os.path.join(config.EXPORT_DIR, "full_history")
    progress_msg = await ctx.send(
        f"Scraping full (all-time) history for {len(tickers)} ticker(s), "
        f"{'forcing a fresh download for all of them' if force else 'skipping any already scraped in the last ~20h'}… "
        f"0/{len(tickers)}"
    )

    done_counter = {"n": 0}

    def _on_done(ticker, ok):
        done_counter["n"] += 1

    async def _poll_progress():
        last_shown = None
        while True:
            await asyncio.sleep(1.5)
            label = f"Scraping full history… {done_counter['n']}/{len(tickers)}"
            if label != last_shown:
                try:
                    await progress_msg.edit(content=label)
                except discord.NotFound:
                    return
                last_shown = label

    poller = asyncio.create_task(_poll_progress())
    try:
        results = await asyncio.to_thread(
            export_data.scrape_watchlist_history, tickers, out_dir, force=force, on_ticker_done=_on_done,
        )
    finally:
        poller.cancel()

    ok_results = [r for r in results if r and not r.get("error")]
    failed = [r for r in results if r and r.get("error")]
    cached_count = sum(1 for r in ok_results if r.get("from_cache"))
    fresh_count = len(ok_results) - cached_count

    summary_header = (
        f"**Scrape complete** — {len(ok_results)}/{len(tickers)} succeeded "
        f"({fresh_count} freshly downloaded, {cached_count} already cached, {len(failed)} failed).\n"
        f"Saved to `{out_dir}` on disk."
    )

    table_lines = ["```", f"{'Ticker':8s} {'Bars':>7s} {'From':12s} {'To':12s} {'Source':6s}"]
    for r in ok_results:
        table_lines.append(f"{r['ticker']:8s} {r['bars']:7d} {str(r['start']):12s} {str(r['end']):12s} {'cache' if r['from_cache'] else 'fresh':6s}")
    if failed:
        table_lines.append("")
        table_lines.append("Failed:")
        for r in failed:
            table_lines.append(f"{r['ticker']:8s} {r['error']}")
    table_lines.append("```")
    table_text = "\n".join(table_lines)

    full_message = summary_header + "\n" + table_text
    try:
        if len(full_message) <= 1900:
            await progress_msg.edit(content=full_message)
        else:
            # Watchlist too big for one Discord message -- keep the
            # header inline and attach the full table as a text file
            # instead of splitting across several messages.
            await progress_msg.edit(content=summary_header + "\n(Full per-ticker table attached below -- too long for one message.)")
            summary_path = os.path.join(out_dir, "_scrape_summary.txt")
            with open(summary_path, "w") as f:
                f.write(table_text.strip("`"))
            await ctx.send(file=discord.File(summary_path, filename="scrape_summary.txt"))
    except discord.NotFound:
        await ctx.send(full_message[:1900])
