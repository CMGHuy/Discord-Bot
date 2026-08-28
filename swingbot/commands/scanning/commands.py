import asyncio
import datetime as dt
import time

import discord

from swingbot import config
from swingbot.bot_core import SESSION_TZ, bot, in_session, log
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.marketdata.watchlist import load_watchlist
from . import presence, recap, runstate
from .alerts import _send_alerts

trade_log = scan_engine.trade_log
_HISTORICAL_CHECK_MAX_RESULTS = 90
_DISCORD_MESSAGE_LIMIT = 1900

@bot.command(name="recap")
async def recap_cmd(ctx, date_arg: str = ""):
    """
    Post today's (or a specific day's) retrospective on demand.

    Usage:
      !recap              → today in Berlin time
      !recap 2026-07-04   → specific date (YYYY-MM-DD)
    """
    import datetime as _dt
    today = None
    if date_arg:
        try:
            today = _dt.date.fromisoformat(date_arg)
        except ValueError:
            await ctx.send(f"⚠️ Unrecognised date `{date_arg}`. Use YYYY-MM-DD.")
            return

    await ctx.send("⏳ Building retrospective…")
    try:
        await recap._post_retrospective(channel_id_override=ctx.channel.id, today=today)
    except Exception as exc:
        log.exception("!recap failed: %s", exc)
        await ctx.send(f"❌ Failed to build retrospective: {exc}")


@bot.command(name="check")
async def check_cmd(ctx, *args: str):
    """
    Live scan with optional date filtering.

    Usage:
      !check [horizon] [min_strategies] [from:YYYY-MM-DD] [to:YYYY-MM-DD]

    When from:/to: are given, queries the trade log for plans recorded in
    that window instead of running a live scan.
    Examples:
      !check
      !check 4w
      !check 4w 2
      !check from:2024-01-01 to:2024-12-31
      !check 4w from:2024-06-01
    """
    # --- parse args ---
    horizon = "all"
    min_confluence = None
    date_from = date_to = None

    for token in args:
        tl = token.lower()
        if tl in ("all", *HORIZONS.keys()):
            horizon = tl
        elif tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]
        elif tl.isdigit():
            min_confluence = int(tl)

    # --- historical mode: query trade log by date ---
    if date_from or date_to:
        await _check_historical(ctx, horizon, date_from, date_to)
        return

    # --- live scan mode (existing behaviour) ---
    min_lv = config.MIN_ALERT_CONFIDENCE_LEVEL
    progress = scan_engine.ScanProgress()
    scan_started = time.monotonic()
    progress_msg = await ctx.send(
        f"🔬 Scanning `{horizon}` · min confidence Lv{min_lv}"
        + (f" · min strategies {min_confluence}" if min_confluence else "")
        + " · starting…"
    )

    def _elapsed_str() -> str:
        secs = round(time.monotonic() - scan_started)
        return f"{secs}s" if secs < 60 else f"{secs // 60}m{secs % 60:02d}s"

    async def _poll_progress():
        last_shown = None
        while True:
            # Progress labels change only as scan stages advance; a two-second
            # cadence remains responsive without needlessly consuming Discord
            # edit rate-limit capacity during a long scan.
            await asyncio.sleep(2.0)
            elapsed = _elapsed_str()
            if progress.stage == "starting":
                # ScanProgress's own default stage, before _sync_run_scan's
                # background thread has done anything -- most commonly
                # because another scan (the automatic session scan, or a
                # concurrent !check) is still holding _scan_lock. Without
                # this branch, the generic "Analyzing" label below fires
                # instead (its if/elif chain has no case for "starting"),
                # showing a literal "0/0 (0%)" that reads identically to a
                # genuinely stuck scan -- this is what a real production
                # report described (v56).
                label = f"⏳ **Waiting to start** (queued behind another scan) · ⏱️ {elapsed}"
            elif progress.stage == "crawling data":
                ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                pct = round(progress.done / progress.total * 100) if progress.total else 0
                label = (
                    f"📡 **Crawling** — {progress.done}/{progress.total} ticker(s) fetched "
                    f"({pct}%){ticker_bit} · ⏱️ {elapsed}"
                )
            elif progress.stage == "building alerts":
                if progress.alerts_total:
                    label = (
                        f"📊 **Building alerts** — {progress.alerts_done}/{progress.alerts_total} done "
                        f"(generating charts…) · ⏱️ {elapsed}"
                    )
                else:
                    label = (
                        f"📊 **Deduplicating** — {progress.qualifying_found} qualifying "
                        f"scenario(s) found, merging similar setups… · ⏱️ {elapsed}"
                    )
            elif progress.stage == "analyzing" and progress.done == 0 and progress.current_ticker is None:
                # Market regime (SPY vs its 200-day EMA) is fetched once,
                # right before the per-ticker loop starts -- without this
                # branch the message would just sit on "0/N tickers (0%)"
                # with no ticker name yet, which reads identically to
                # "stuck" even though it's actively doing something.
                label = f"🌐 **Checking market regime** (SPY vs 200-day EMA)… · ⏱️ {elapsed}"
            else:
                ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                found_bit = f" · **{progress.qualifying_found} qualifying** so far" if progress.qualifying_found else ""
                label = (
                    f"🔬 **Analyzing** ({horizon}) — {progress.done}/{progress.total} ticker·horizon combo(s) "
                    f"({progress.pct}%){ticker_bit}{found_bit} · ⏱️ {elapsed}"
                )
            if label != last_shown:
                try:
                    await progress_msg.edit(content=label)
                except discord.NotFound:
                    return
                last_shown = label

    poller = asyncio.create_task(_poll_progress())
    try:
        alerts = await scan_engine.run_scan(
            horizon_filter=horizon, require_confirmation=False, bot=bot, progress=progress,
            min_confluence=min_confluence,
        )
    finally:
        poller.cancel()

    if progress.stopped:
        await progress_msg.edit(
            content=f"🛑 **Scan stopped early** (use `!stop` to cancel a scan in progress) — "
                    f"{len(alerts)} alert(s) built from what completed before the stop."
        )
        if alerts:
            await _send_alerts(ctx, alerts)
        return

    await progress_msg.edit(content="🔬 Scan complete — building results…")

    if not alerts:
        f = progress.funnel
        if f and f.get("scenarios_found", 0) > 0:
            not_ready_parts = []
            if f.get("failed_min_confluence", 0):
                not_ready_parts.append(f"{f['failed_min_confluence']} below min strategies")
            if f.get("failed_min_confidence", 0):
                not_ready_parts.append(f"{f['failed_min_confidence']} below min confidence (Lv{min_lv}+)")
            not_ready_str = (", ".join(not_ready_parts) + " — ") if not_ready_parts else ""
            await progress_msg.edit(
                content=(
                    f"📭 **No qualifying trades** right now (min confidence: Lv{min_lv}"
                    + (f", min strategies: {min_confluence}" if min_confluence else "")
                    + f").\n{not_ready_str}{f['scenarios_found']} scenario(s) analyzed."
                )
            )
        else:
            await progress_msg.edit(
                content=(
                    f"📭 **No qualifying trades** right now (min confidence: Lv{min_lv}"
                    + (f", min strategies: {min_confluence}" if min_confluence else "")
                    + ")."
                )
            )
        return

    f = progress.funnel
    lv_counts = f.get("conf_level_counts", {}) if f else {}
    lv_breakdown = (
        "  ".join(f"Lv{lv}:{cnt}" for lv, cnt in sorted(lv_counts.items()))
        if lv_counts else "none"
    )
    summary = (
        f"✅ **{len(alerts)} qualifying trade(s)** (min Lv{min_lv}"
        + (f", min strategies: {min_confluence}" if min_confluence else "")
        + f")  •  confidence breakdown: {lv_breakdown}"
    )
    await progress_msg.edit(content=summary)
    await _send_alerts(ctx, alerts)


async def _check_historical(ctx, horizon: str, date_from: str | None, date_to: str | None):
    """Show trade plans recorded in the trade log within a date window."""
    from_dt = date_from or "0000-01-01"
    to_dt   = date_to   or "9999-12-31"

    all_trades = trade_log.get_trades(status=None, limit=None)

    # Filter by opened_at date and optional horizon
    def _in_range(t):
        opened = t.get("opened_at", "")[:10]  # YYYY-MM-DD
        if opened < from_dt or opened > to_dt:
            return False
        if horizon != "all" and t.get("horizon_key") != horizon:
            return False
        return True

    trades = [t for t in all_trades if _in_range(t)]

    range_str = f"{date_from or '…'} → {date_to or 'now'}"
    horiz_str = f" · horizon `{horizon}`" if horizon != "all" else ""

    if not trades:
        await ctx.send(
            f"📭 No recorded trade plans found for **{range_str}**{horiz_str}.\n"
            "Trade plans are only recorded when the bot posts an alert (or you run `!check`)."
        )
        return

    total = len(trades)
    displayed = trades[:_HISTORICAL_CHECK_MAX_RESULTS]
    truncation = (
        f" Showing the first {_HISTORICAL_CHECK_MAX_RESULTS}; narrow the date range or horizon for the rest."
        if total > len(displayed) else ""
    )
    header = (
        f"📋 **{total} recorded trade plan(s)** — {range_str}{horiz_str}.{truncation}\n"
        "*(from the trade log — these are plans the bot actually posted)*\n"
    )
    await ctx.send(header)

    # Pack summaries into Discord-safe messages instead of emitting one request
    # per plan. The display cap above bounds request pressure for broad ranges.
    summaries = []
    for t in displayed:
        direction_emoji = "📈" if t.get("direction") == "bullish" else "📉"
        status_emoji = {"open": "🟡", "win": "✅", "loss": "❌", "closed": "⬜"}.get(t.get("status", ""), "⬜")
        entry   = t.get("entry_price", t.get("entry", "?"))
        stop    = t.get("stop_loss", "?")
        target  = t.get("take_profit", "?")
        lv      = t.get("confidence_level", "?")
        strats  = t.get("strategy", "?")
        horizon_k = t.get("horizon_key", "?")
        opened  = t.get("opened_at", "?")[:10]
        ticker  = t.get("ticker", "?")
        tid     = t.get("id", "?")

        line = (
            f"{direction_emoji} {status_emoji} **{ticker}** `{horizon_k}` — "
            f"Lv{lv} · {strats}\n"
            f"Entry **{entry}** · Stop {stop} · Target {target}\n"
            f"Opened: {opened}  `ID: {tid}`  — use `!trade {tid}` for full details & chart"
        )
        summaries.append(line)

    chunk, chunk_len = [], 0
    for line in summaries:
        line_len = len(line) + (2 if chunk else 0)
        if chunk and chunk_len + line_len > _DISCORD_MESSAGE_LIMIT:
            await ctx.send("\n\n".join(chunk))
            chunk, chunk_len = [], 0
            line_len = len(line)
        chunk.append(line)
        chunk_len += line_len
    if chunk:
        await ctx.send("\n\n".join(chunk))


@bot.command(name="session")
async def session_cmd(ctx):
    from swingbot.bot_core import in_session
    now = dt.datetime.now(SESSION_TZ)
    active = in_session()
    start = config.SESSION_START_HOUR
    end = config.SESSION_END_HOUR
    status = "🟢 **Active**" if active else "🔴 **Inactive**"
    paused_bit = "\n⏸️ **Scanning is paused** — use `!resume` or the admin UI to resume." if runstate.is_scan_paused() else ""
    await ctx.send(
        f"{status} — session window: {start:02d}:00–{end:02d}:00 Europe/Berlin (7 days)\n"
        f"Current time: {now.strftime('%Y-%m-%d %H:%M %Z')}{paused_bit}"
    )


@bot.command(name="status")
async def status_cmd(ctx):
    wl = load_watchlist()
    stats = trade_log.get_stats()
    active = in_session()
    session_status = "🟢 active" if active else "🔴 inactive"
    latency_ms = round(bot.latency * 1000) if bot.latency else None
    paused = runstate.is_scan_paused()
    scan_line = "⏸️ **paused** (manual !check still works)" if paused else "▶️ running"
    await ctx.send(
        f"**Bot status**\n"
        f"Automatic scanning: {scan_line}\n"
        f"Session: {session_status} ({config.SESSION_START_HOUR:02d}:00–{config.SESSION_END_HOUR:02d}:00 Berlin)\n"
        f"Watchlist: {len(wl)} ticker(s)\n"
        f"Open positions: {stats['open']} / {config.MAX_OPEN_POSITIONS} max\n"
        f"Closed trades: {stats.get('win', 0)} wins · {stats.get('loss', 0)} losses\n"
        f"Min confidence: Lv{config.MIN_ALERT_CONFIDENCE_LEVEL} · "
        f"Min strategies: {config.MIN_TARGET_CONFLUENCE_COUNT}\n"
        f"Gateway latency: {latency_ms}ms" + (" ⚠️ high" if latency_ms and latency_ms > 300 else "")
    )


@bot.command(name="pause")
async def pause_cmd(ctx):
    """Pause the automatic background scan loop. Manual !check still works."""
    if runstate.is_scan_paused():
        await ctx.send("⏸️ Scanning is already paused.")
        return
    runstate.set_scan_paused(True)
    log.info("Automatic scanning paused via !pause (by %s).", ctx.author)
    await presence._refresh_presence()
    await ctx.send(
        "⏸️ **Automatic scanning paused.** The bot will stop posting scheduled alerts. "
        "`!check` still works on demand. Use `!resume` or the admin UI to turn it back on."
    )


@bot.command(name="resume")
async def resume_cmd(ctx):
    """Resume the automatic background scan loop after a !pause."""
    if not runstate.is_scan_paused():
        await ctx.send("▶️ Scanning is already running.")
        return
    runstate.set_scan_paused(False)
    log.info("Automatic scanning resumed via !resume (by %s).", ctx.author)
    await presence._refresh_presence()
    await ctx.send("▶️ **Automatic scanning resumed.**")


@bot.command(name="stop")
async def stop_cmd(ctx):
    """
    Stop whatever scan is currently in progress (!check, /check, the
    admin UI's "Run !check now" trigger, or the automatic session scan).

    Different from !pause: !pause only stops FUTURE automatic scans from
    starting -- a scan already running keeps going. !stop cuts short a
    scan that's already running, right now. It's cooperative (checked
    once per ticker inside scan_engine's crawl/analyze/alert-building
    loops), so it takes effect at the next checkpoint, not instantly --
    there's no way to forcibly kill a scan mid-fetch.
    """
    if not scan_engine.is_scan_running():
        await ctx.send("ℹ️ No scan is currently running.")
        return
    scan_engine.request_stop()
    log.info("Stop requested via !stop (by %s).", ctx.author)
    await ctx.send("🛑 **Stop requested** — the running scan will end after finishing its current ticker.")
