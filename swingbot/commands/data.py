"""!charts, !download, !cached, !scrapeall and their slash twins (v153).

Each body lives in one handle_<name>(reply, ...) handler; the prefix command
and the /<name> slash command both call it through a Reply
(swingbot/commands/reply.py).
"""
import asyncio
import logging
import os
import shutil

import discord
from discord import app_commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core.marketdata import export_data
from swingbot.core.marketdata.data_store import (
    DATA_DIR as CACHE_DIR, INTERVAL_CONFIG, TIMEFRAMES, download_and_cache,
)
from swingbot.core.marketdata.export_data import export_ticker
from swingbot.core.marketdata.watchlist import load_watchlist

log = logging.getLogger(__name__)

MESSAGE_LIMIT = 1900
SCRAPE_POLL_S = 1.5
SCRAPE_USAGE = ("Usage: `!scrapeall` (skip tickers already scraped in the last ~20h) "
                "or `!scrapeall force` (re-download everything).")
SCRAPE_EMPTY = "Watchlist is empty -- add tickers with `!watchlist add TICKER` first."
SCRAPE_LONG_NOTE = "\n(Full per-ticker table attached below -- too long for one message.)"

# One choice per canonical timeframe; the value is its yfinance code, which is
# an INTERVAL_CONFIG key, so `1m` keeps !download's 1-minute warning.
INTERVAL_CHOICES = [
    app_commands.Choice(name=f"{name} ({cfg['interval']})", value=cfg["interval"])
    for name, cfg in TIMEFRAMES.items()
]
SCRAPE_MODE_CHOICES = [
    app_commands.Choice(name="cached (skip tickers scraped in the last ~20h)", value="cached"),
    app_commands.Choice(name="force (re-download everything)", value="force"),
]


# ──────────────────────────────────────────────
# charts
# ──────────────────────────────────────────────

async def _post_chart_export(reply, ticker: str) -> None:
    try:
        result = await asyncio.to_thread(export_ticker, ticker, config.EXPORT_DIR)
    except Exception as e:
        log.warning("!charts: could not export %s", ticker, exc_info=True)
        await reply.send(f"⚠️ Could not export {ticker}: {e}")
        return
    await reply.send(
        content=f"**{ticker}** — {result['bars']} trading days of history",
        files=[
            discord.File(result["csv"]),
            discord.File(result["recent_chart"]),
            discord.File(result["full_chart"]),
        ],
    )


async def handle_charts(reply) -> None:
    tickers = load_watchlist()
    await reply.defer()
    await reply.send(f"Downloading full historical daily data for {len(tickers)} ticker(s)… this can take a bit.")

    if os.path.exists(config.EXPORT_DIR):
        shutil.rmtree(config.EXPORT_DIR)
    os.makedirs(config.EXPORT_DIR, exist_ok=True)

    for ticker in tickers:
        await _post_chart_export(reply, ticker)

    await reply.send("Done — all watchlist history exported above.")


# ──────────────────────────────────────────────
# download
# ──────────────────────────────────────────────

def _download_intro(interval: str, cfg: dict, n_tickers: int) -> str:
    if interval == "1m":
        return (
            f"⚠️ Heads up: Yahoo Finance only provides **1-minute** candles for the trailing **~30 days** — "
            f"there's no source for years of 1-minute history for free. Pulling the maximum available "
            f"(~30 days) for {n_tickers} ticker(s) now and caching it to disk…"
        )
    if cfg["max_days"] is not None:
        return f"Downloading {interval} data (max ~{cfg['max_days']} days available from Yahoo) for {n_tickers} ticker(s)…"
    return f"Downloading full {interval} history for {n_tickers} ticker(s)…"


async def _download_all(reply, tickers: list, interval: str) -> list:
    results = []
    for t in tickers:
        try:
            results.append(await asyncio.to_thread(download_and_cache, t, interval))
        except Exception as e:
            log.warning("!download: %s failed", t, exc_info=True)
            await reply.send(f"⚠️ {t}: {e}")
    return results


def _download_table(results: list) -> str:
    lines = ["**Cached to disk:**", "```"]
    lines.append(f"{'Ticker':8s} {'Rows':>7s} {'From':19s} {'To':19s}")
    for r in results:
        lines.append(f"{r['ticker']:8s} {r['rows']:7d} {r['start'][:19]:19s} {r['end'][:19]:19s}")
    lines.append("```")
    return "\n".join(lines)


async def handle_download(reply, interval: str, ticker: str | None = None) -> None:
    interval = interval.lower()
    if interval not in INTERVAL_CONFIG:
        await reply.send_error(f"Unknown interval '{interval}'. Use one of: {', '.join(INTERVAL_CONFIG)}")
        return

    tickers = [ticker.upper()] if ticker else load_watchlist()
    await reply.defer()
    await reply.send(_download_intro(interval, INTERVAL_CONFIG[interval], len(tickers)))

    results = await _download_all(reply, tickers, interval)
    if not results:
        await reply.send("Nothing downloaded.")
        return
    await reply.send(_download_table(results))


# ──────────────────────────────────────────────
# cached
# ──────────────────────────────────────────────

def _cached_row(tf: str, full_dir: str) -> str | None:
    """One summary row for a timeframe folder, or None if it holds no CSV."""
    symbols = rows = size_kb = 0
    for fname in sorted(os.listdir(full_dir)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(full_dir, fname)
        symbols += 1
        size_kb += os.path.getsize(path) / 1024
        try:
            with open(path) as f:
                rows += sum(1 for _ in f) - 1
        except OSError:
            continue
    if not symbols:
        return None
    return f"{tf:10s} {symbols:8d} {rows:10d} {size_kb:7.0f}K"


async def handle_cached(reply) -> None:
    base_dir = CACHE_DIR
    if not os.path.exists(base_dir):
        await reply.send("Nothing cached yet. Use `!download INTERVAL [TICKER]` first.")
        return

    # Layout is market_data/{timeframe}/{TICKER}.csv -- summarise per
    # timeframe folder rather than listing every symbol, since a populated
    # cache is 500+ files per timeframe and would blow the 2000-char limit.
    rows = []
    for tf in sorted(os.listdir(base_dir)):
        full_dir = os.path.join(base_dir, tf)
        if os.path.isdir(full_dir) and (row := _cached_row(tf, full_dir)):
            rows.append(row)
    if not rows:
        await reply.send("Nothing cached yet. Use `!download TIMEFRAME [TICKER]` first.")
        return
    header = f"{'Timeframe':10s} {'Symbols':>8s} {'Rows':>10s} {'Size':>8s}"
    await reply.send("\n".join(["**Locally cached data:**", "```", header, *rows, "```"]))


# ──────────────────────────────────────────────
# scrapeall
# ──────────────────────────────────────────────

def _scrape_intro(n_tickers: int, force: bool) -> str:
    return (
        f"Scraping full (all-time) history for {n_tickers} ticker(s), "
        f"{'forcing a fresh download for all of them' if force else 'skipping any already scraped in the last ~20h'}… "
        f"0/{n_tickers}"
    )


async def _poll_scrape_progress(reply, progress_msg, done_counter: dict, total: int) -> None:
    """Edit the progress message every SCRAPE_POLL_S until cancelled. Stops
    once the interaction token is stale: its webhook message can no longer
    be edited (a prefix reply is never stale)."""
    last_shown = None
    while not reply.stale:
        await asyncio.sleep(SCRAPE_POLL_S)
        label = f"Scraping full history… {done_counter['n']}/{total}"
        if label == last_shown or reply.stale:
            continue
        try:
            await progress_msg.edit(content=label)
        except discord.NotFound:
            return
        last_shown = label


async def _scrape_with_progress(reply, progress_msg, tickers: list, out_dir: str, force: bool) -> list:
    done_counter = {"n": 0}

    def _on_done(ticker, ok):
        done_counter["n"] += 1

    poller = asyncio.create_task(_poll_scrape_progress(reply, progress_msg, done_counter, len(tickers)))
    try:
        return await asyncio.to_thread(
            export_data.scrape_watchlist_history, tickers, out_dir, force=force, on_ticker_done=_on_done,
        )
    finally:
        poller.cancel()


def _scrape_summary(results: list, n_tickers: int, out_dir: str) -> tuple[str, str]:
    """(summary header, fenced per-ticker table) for a finished scrape."""
    ok_results = [r for r in results if r and not r.get("error")]
    failed = [r for r in results if r and r.get("error")]
    cached_count = sum(1 for r in ok_results if r.get("from_cache"))
    fresh_count = len(ok_results) - cached_count

    header = (
        f"**Scrape complete** — {len(ok_results)}/{n_tickers} succeeded "
        f"({fresh_count} freshly downloaded, {cached_count} already cached, {len(failed)} failed).\n"
        f"Saved to `{out_dir}` on disk."
    )
    table_lines = ["```", f"{'Ticker':8s} {'Bars':>7s} {'From':12s} {'To':12s} {'Source':6s}"]
    for r in ok_results:
        table_lines.append(f"{r['ticker']:8s} {r['bars']:7d} {str(r['start']):12s} {str(r['end']):12s} {'cache' if r['from_cache'] else 'fresh':6s}")
    if failed:
        table_lines += ["", "Failed:"] + [f"{r['ticker']:8s} {r['error']}" for r in failed]
    table_lines.append("```")
    return header, "\n".join(table_lines)


def _summary_file(out_dir: str, table_text: str) -> discord.File:
    summary_path = os.path.join(out_dir, "_scrape_summary.txt")
    with open(summary_path, "w") as f:
        f.write(table_text.strip("`"))
    return discord.File(summary_path, filename="scrape_summary.txt")


async def _deliver_scrape_summary(reply, progress_msg, header: str, table_text: str, out_dir: str) -> None:
    """Turn the progress message into the summary. A stale interaction token
    cannot edit, so its summary goes out as a fresh send instead -- the result
    is never lost. A too-long table goes out as an attached text file."""
    full_message = header + "\n" + table_text
    fits = len(full_message) <= MESSAGE_LIMIT
    text = full_message if fits else header + SCRAPE_LONG_NOTE
    try:
        if reply.stale:
            await reply.send(text)
        else:
            await progress_msg.edit(content=text)
        if not fits:
            await reply.send(file=_summary_file(out_dir, table_text))
    except discord.NotFound:
        await reply.send(full_message[:MESSAGE_LIMIT])


async def handle_scrapeall(reply, mode: str = "cached") -> None:
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
        await reply.send_error(SCRAPE_USAGE)
        return
    tickers = load_watchlist()
    if not tickers:
        await reply.send_error(SCRAPE_EMPTY)
        return

    force = mode == "force"
    out_dir = os.path.join(config.EXPORT_DIR, "full_history")
    await reply.defer()
    progress_msg = await reply.send(_scrape_intro(len(tickers), force))
    results = await _scrape_with_progress(reply, progress_msg, tickers, out_dir, force)
    header, table_text = _scrape_summary(results, len(tickers), out_dir)
    await _deliver_scrape_summary(reply, progress_msg, header, table_text, out_dir)


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.command(name="charts")
async def charts_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_charts(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="download")
async def download_cmd(ctx, interval: str, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_download(reply, interval, ticker)
    await send_prefix_tip(ctx, reply)


@bot.command(name="cached")
async def cached_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_cached(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="scrapeall")
async def scrapeall_cmd(ctx, mode: str = "cached"):
    """!scrapeall [force] -- full all-time daily history for the whole watchlist."""
    reply = CtxReply(ctx)
    await handle_scrapeall(reply, mode)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (new in v153)
# ──────────────────────────────────────────────

@bot.tree.command(name="charts", description="Export full daily history (CSV and charts) for every watchlist ticker")
async def slash_charts(interaction: discord.Interaction):
    await handle_charts(InteractionReply(interaction))


@bot.tree.command(name="download", description="Download and cache price history for one ticker or the watchlist")
@app_commands.describe(interval="Timeframe to download", ticker="One ticker (default: the whole watchlist)")
@app_commands.choices(interval=INTERVAL_CHOICES)
async def slash_download(interaction: discord.Interaction, interval: app_commands.Choice[str],
                         ticker: str = None):
    await handle_download(InteractionReply(interaction), interval.value, ticker)


@bot.tree.command(name="cached", description="Summarise the locally cached market data per timeframe")
async def slash_cached(interaction: discord.Interaction):
    await handle_cached(InteractionReply(interaction))


@bot.tree.command(name="scrapeall", description="Scrape full all-time daily history for the whole watchlist")
@app_commands.describe(mode="cached skips tickers scraped in the last ~20h; force re-downloads all")
@app_commands.choices(mode=SCRAPE_MODE_CHOICES)
async def slash_scrapeall(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
    await handle_scrapeall(InteractionReply(interaction), mode.value if mode else "cached")
