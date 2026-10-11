import asyncio
import datetime as dt
import logging
import time

import discord
from discord import app_commands

from swingbot import config
from swingbot.bot_core import SESSION_TZ, bot, in_session
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.market.strategy import LEGACY_HORIZONS
from swingbot.core.marketdata.watchlist import load_watchlist
from . import presence, recap, runstate
from .alerts import _send_alerts, post_short_universe, send_then_short

log = logging.getLogger(__name__)

trade_log = scan_engine.trade_log
_HISTORICAL_CHECK_MAX_RESULTS = 90
_DISCORD_MESSAGE_LIMIT = 1900

async def handle_recap(reply, date_arg: str = "") -> None:
    import datetime as _dt
    today = None
    if date_arg:
        try:
            today = _dt.date.fromisoformat(date_arg)
        except ValueError:
            await reply.send_error(f"⚠️ Unrecognised date `{date_arg}`. Use YYYY-MM-DD.")
            return

    await reply.send("⏳ Building retrospective…")
    try:
        await recap._post_retrospective(channel_id_override=reply.channel.id, today=today)
    except Exception as exc:
        log.exception("!recap failed")
        await reply.send_error(f"❌ Failed to build retrospective: {exc}")


@bot.command(name="recap")
async def recap_cmd(ctx, date_arg: str = ""):
    """
    Post today's (or a specific day's) retrospective on demand.

    Usage:
      !recap              → today in Berlin time
      !recap 2026-07-04   → specific date (YYYY-MM-DD)
    """
    reply = CtxReply(ctx)
    await handle_recap(reply, date_arg)
    await send_prefix_tip(ctx, reply)


def _parse_check_args(args) -> tuple[str, int | None, str | None, str | None]:
    """!check's free-form tokens -> (horizon, min_confluence, date_from, date_to)."""
    horizon = "all"
    min_confluence = None
    date_from = date_to = None
    for token in args:
        tl = token.lower()
        if tl in ("all", *LEGACY_HORIZONS):
            horizon = tl
        elif tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]
        elif tl.isdigit():
            min_confluence = int(tl)
    return horizon, min_confluence, date_from, date_to


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
    reply = CtxReply(ctx)
    await handle_check(reply, *_parse_check_args(args))
    await send_prefix_tip(ctx, reply)


async def handle_check(reply, horizon: str = "all", min_confluence: int | None = None,
                       date_from: str | None = None, date_to: str | None = None) -> None:
    """Live scan, or (with a date bound) the recorded plans in that window."""
    await reply.defer()
    if date_from or date_to:
        await _check_historical(reply, horizon, date_from, date_to)
        return
    await _check_live(reply, horizon, min_confluence)


def _min_strats_bit(min_confluence: int | None) -> str:
    return f", min strategies: {min_confluence}" if min_confluence else ""


def _check_intro(horizon: str, min_lv: int, min_confluence: int | None) -> str:
    return (
        f"🔬 Scanning `{horizon}` · min confidence Lv{min_lv}"
        + (f" · min strategies {min_confluence}" if min_confluence else "")
        + " · starting…"
    )


def _elapsed_str(scan_started: float) -> str:
    secs = round(time.monotonic() - scan_started)
    return f"{secs}s" if secs < 60 else f"{secs // 60}m{secs % 60:02d}s"


def _crawl_label(progress, elapsed: str) -> str:
    ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
    pct = round(progress.done / progress.total * 100) if progress.total else 0
    return (
        f"📡 **Crawling** — {progress.done}/{progress.total} ticker(s) fetched "
        f"({pct}%){ticker_bit} · ⏱️ {elapsed}"
    )


def _analyze_label(progress, horizon: str, elapsed: str) -> str:
    ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
    found_bit = f" · **{progress.qualifying_found} qualifying** so far" if progress.qualifying_found else ""
    return (
        f"🔬 **Analyzing** ({horizon}) — {progress.done}/{progress.total} ticker·horizon combo(s) "
        f"({progress.pct}%){ticker_bit}{found_bit} · ⏱️ {elapsed}"
    )


def _progress_label(progress, horizon: str, elapsed: str) -> str:
    if progress.stage == "starting":
        # ScanProgress's own default stage, before _sync_run_scan's
        # background thread has done anything -- most commonly because
        # another scan (the automatic session scan, or a concurrent !check)
        # is still holding _scan_lock. Without this branch the generic
        # "Analyzing" label fires instead, showing a literal "0/0 (0%)"
        # that reads identically to a genuinely stuck scan (v56).
        return f"⏳ **Waiting to start** (queued behind another scan) · ⏱️ {elapsed}"
    if progress.stage == "crawling data":
        return _crawl_label(progress, elapsed)
    if progress.stage == "building alerts":
        if progress.alerts_total:
            return (
                f"📊 **Building alerts** — {progress.alerts_done}/{progress.alerts_total} done "
                f"(generating charts…) · ⏱️ {elapsed}"
            )
        return (
            f"📊 **Deduplicating** — {progress.qualifying_found} qualifying "
            f"scenario(s) found, merging similar setups… · ⏱️ {elapsed}"
        )
    if progress.stage == "analyzing" and progress.done == 0 and progress.current_ticker is None:
        # Market regime (SPY vs its 200-day EMA) is fetched once, right
        # before the per-ticker loop starts -- without this branch the
        # message would sit on "0/N tickers (0%)", which reads as "stuck".
        return f"🌐 **Checking market regime** (SPY vs 200-day EMA)… · ⏱️ {elapsed}"
    return _analyze_label(progress, horizon, elapsed)


async def _poll_check_progress(reply, progress_msg, progress, horizon: str, scan_started: float) -> None:
    """Edit the progress message as scan stages advance, until cancelled.
    Stops once the interaction token is stale: its webhook message can no
    longer be edited (a prefix reply is never stale)."""
    last_shown = None
    while not reply.stale:
        # Progress labels change only as scan stages advance; a two-second
        # cadence remains responsive without needlessly consuming Discord
        # edit rate-limit capacity during a long scan.
        await asyncio.sleep(2.0)
        label = _progress_label(progress, horizon, _elapsed_str(scan_started))
        if label == last_shown or reply.stale:
            continue
        try:
            await progress_msg.edit(content=label)
        except discord.NotFound:
            return
        last_shown = label


async def _check_live(reply, horizon: str, min_confluence: int | None) -> None:
    min_lv = config.MIN_ALERT_CONFIDENCE_LEVEL
    progress = scan_engine.ScanProgress()
    scan_started = time.monotonic()
    progress_msg = await reply.send(_check_intro(horizon, min_lv, min_confluence))

    poller = asyncio.create_task(_poll_check_progress(reply, progress_msg, progress, horizon, scan_started))
    try:
        alerts = await scan_engine.run_scan(
            horizon_filter=horizon, require_confirmation=False, bot=bot, progress=progress,
            min_confluence=min_confluence,
        )
    finally:
        poller.cancel()
    await _finish_check(reply, progress_msg, progress, alerts, min_lv, min_confluence)


async def _show_result(reply, progress_msg, content: str) -> None:
    """Turn the progress message into a result line. A stale interaction
    token cannot edit, so the result goes out as a fresh send instead."""
    if reply.stale:
        await reply.send(content)
    else:
        await progress_msg.edit(content=content)


def _no_alerts_text(f: dict | None, min_lv: int, min_confluence: int | None) -> str:
    base = f"📭 **No qualifying trades** right now (min confidence: Lv{min_lv}" + _min_strats_bit(min_confluence)
    if not (f and f.get("scenarios_found", 0) > 0):
        return base + ")."
    not_ready_parts = []
    if f.get("failed_min_confluence", 0):
        not_ready_parts.append(f"{f['failed_min_confluence']} below min strategies")
    if f.get("failed_min_confidence", 0):
        not_ready_parts.append(f"{f['failed_min_confidence']} below min confidence (Lv{min_lv}+)")
    not_ready_str = (", ".join(not_ready_parts) + " — ") if not_ready_parts else ""
    return base + f").\n{not_ready_str}{f['scenarios_found']} scenario(s) analyzed."


def _check_summary(alerts: list, f: dict | None, min_lv: int, min_confluence: int | None) -> str:
    lv_counts = f.get("conf_level_counts", {}) if f else {}
    lv_breakdown = (
        "  ".join(f"Lv{lv}:{cnt}" for lv, cnt in sorted(lv_counts.items()))
        if lv_counts else "none"
    )
    return (
        f"✅ **{len(alerts)} qualifying trade(s)** (min Lv{min_lv}"
        + _min_strats_bit(min_confluence)
        + f")  •  confidence breakdown: {lv_breakdown}"
    )


async def _finish_check(reply, progress_msg, progress, alerts: list, min_lv: int,
                        min_confluence: int | None) -> None:
    """Result line on the progress message, then the alerts to the caller (`reply`)."""
    if progress.stopped:
        await _show_result(
            reply, progress_msg,
            f"🛑 **Scan stopped early** (use `!stop` to cancel a scan in progress) — "
            f"{len(alerts)} alert(s) built from what completed before the stop.",
        )
        if alerts:
            await _send_alerts(reply, alerts)
        return

    if not reply.stale:
        await progress_msg.edit(content="🔬 Scan complete — building results…")

    if not alerts:
        await _show_result(reply, progress_msg, _no_alerts_text(progress.funnel, min_lv, min_confluence))
        await post_short_universe(reply, bot=bot, require_confirmation=False)
        return

    await _show_result(reply, progress_msg, _check_summary(alerts, progress.funnel, min_lv, min_confluence))
    await send_then_short(reply, alerts, bot=bot, require_confirmation=False)


def _historical_line(t: dict) -> str:
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
    return (
        f"{direction_emoji} {status_emoji} **{ticker}** `{horizon_k}` — "
        f"Lv{lv} · {strats}\n"
        f"Entry **{entry}** · Stop {stop} · Target {target}\n"
        f"Opened: {opened}  `ID: {tid}`  — use `!trade {tid}` for full details & chart"
    )


def _pack_messages(lines: list[str]) -> list[str]:
    """Pack lines into Discord-safe messages instead of one request per plan."""
    messages, chunk, chunk_len = [], [], 0
    for line in lines:
        line_len = len(line) + (2 if chunk else 0)
        if chunk and chunk_len + line_len > _DISCORD_MESSAGE_LIMIT:
            messages.append("\n\n".join(chunk))
            chunk, chunk_len = [], 0
            line_len = len(line)
        chunk.append(line)
        chunk_len += line_len
    if chunk:
        messages.append("\n\n".join(chunk))
    return messages


async def _check_historical(reply, horizon: str, date_from: str | None, date_to: str | None):
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
        await reply.send(
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
    await reply.send(header)

    # The display cap above bounds request pressure for broad ranges.
    for message in _pack_messages([_historical_line(t) for t in displayed]):
        await reply.send(message)


def _session_now() -> dt.datetime:
    """Seam for tests (monkeypatched)."""
    return dt.datetime.now(SESSION_TZ)


async def handle_session(reply) -> None:
    from swingbot.bot_core import in_session
    now = _session_now()
    active = in_session()
    start = config.SESSION_START_HOUR
    end = config.SESSION_END_HOUR
    status = "🟢 **Active**" if active else "🔴 **Inactive**"
    paused_bit = "\n⏸️ **Scanning is paused** — use `!resume` or the admin UI to resume." if runstate.is_scan_paused() else ""
    await reply.send(
        f"{status} — session window: {start:02d}:00–{end:02d}:00 Europe/Berlin (Mon-Fri)\n"
        f"Current time: {now.strftime('%Y-%m-%d %H:%M %Z')}{paused_bit}"
    )


async def handle_status(reply) -> None:
    wl = load_watchlist()
    stats = trade_log.get_stats()
    active = in_session()
    session_status = "🟢 active" if active else "🔴 inactive"
    latency_ms = round(bot.latency * 1000) if bot.latency else None
    paused = runstate.is_scan_paused()
    scan_line = "⏸️ **paused** (manual !check still works)" if paused else "▶️ running"
    await reply.send(
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


async def handle_pause(reply) -> None:
    """Pause the automatic background scan loop. Manual !check still works."""
    if runstate.is_scan_paused():
        await reply.send("⏸️ Scanning is already paused.")
        return
    runstate.set_scan_paused(True)
    log.info("Automatic scanning paused via !pause (by %s).", reply.author)
    await presence._refresh_presence()
    await reply.send(
        "⏸️ **Automatic scanning paused.** The bot will stop posting scheduled alerts. "
        "`!check` still works on demand. Use `!resume` or the admin UI to turn it back on."
    )


async def handle_resume(reply) -> None:
    """Resume the automatic background scan loop after a !pause."""
    if not runstate.is_scan_paused():
        await reply.send("▶️ Scanning is already running.")
        return
    runstate.set_scan_paused(False)
    log.info("Automatic scanning resumed via !resume (by %s).", reply.author)
    await presence._refresh_presence()
    await reply.send("▶️ **Automatic scanning resumed.**")


async def handle_stop(reply) -> None:
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
        await reply.send("ℹ️ No scan is currently running.", ephemeral=True)
        return
    scan_engine.request_stop()
    log.info("Stop requested via !stop (by %s).", reply.author)
    await reply.send("🛑 **Stop requested** — the running scan will end after finishing its current ticker.")


# Each prefix command calls its handler itself (the index's prefix pattern),
# so SP18's one-body check sees the call inside the command.

@bot.command(name="session")
async def session_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_session(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="status")
async def status_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_status(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="pause")
async def pause_cmd(ctx):
    """Pause the automatic background scan loop. Manual !check still works."""
    reply = CtxReply(ctx)
    await handle_pause(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="resume")
async def resume_cmd(ctx):
    """Resume the automatic background scan loop after a !pause."""
    reply = CtxReply(ctx)
    await handle_resume(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="stop")
async def stop_cmd(ctx):
    """Stop whatever scan is currently in progress (see handle_stop)."""
    reply = CtxReply(ctx)
    await handle_stop(reply)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (/check and /stop moved from slash.py in v153, payload
# unchanged; /recap /session /status /pause /resume new)
# ──────────────────────────────────────────────

def _min_from_option(n: int | None) -> int | None:
    """Today's token rule: `str(n).isdigit()` -- a negative minimum is ignored."""
    return n if n is not None and n >= 0 else None


@bot.tree.command(name="check", description="Live scan or historical review of recorded trade plans")
@app_commands.describe(
    horizon="Swing horizon (default: all)",
    min_strategies="Override min confirmed strategies for this run (live mode only)",
    from_date="Start date YYYY-MM-DD — enables historical mode, shows recorded plans",
    to_date="End date YYYY-MM-DD — use with from_date for a specific window",
)
@app_commands.choices(horizon=HORIZON_CHOICES)
async def slash_check(
    interaction: discord.Interaction,
    horizon: app_commands.Choice[str] = None,
    min_strategies: int = None,
    from_date: str = None,
    to_date: str = None,
):
    await handle_check(
        InteractionReply(interaction), horizon.value if horizon else "all",
        _min_from_option(min_strategies), from_date or None, to_date or None,
    )


@bot.tree.command(name="stop", description="Stop whatever scan is currently running")
async def slash_stop(interaction: discord.Interaction):
    await handle_stop(InteractionReply(interaction))


@bot.tree.command(name="recap", description="Post today's (or a given day's) retrospective in this channel")
@app_commands.describe(date="Day to recap, YYYY-MM-DD (default: today, Berlin time)")
async def slash_recap(interaction: discord.Interaction, date: str = None):
    await handle_recap(InteractionReply(interaction), date or "")


@bot.tree.command(name="session", description="Show the scan session window and whether it is active now")
async def slash_session(interaction: discord.Interaction):
    await handle_session(InteractionReply(interaction))


@bot.tree.command(name="status", description="Bot status: scanning, session, watchlist, open positions, latency")
async def slash_status(interaction: discord.Interaction):
    await handle_status(InteractionReply(interaction))


@bot.tree.command(name="pause", description="Pause the automatic background scan loop (manual /check still works)")
async def slash_pause(interaction: discord.Interaction):
    await handle_pause(InteractionReply(interaction))


@bot.tree.command(name="resume", description="Resume the automatic background scan loop")
async def slash_resume(interaction: discord.Interaction):
    await handle_resume(InteractionReply(interaction))
