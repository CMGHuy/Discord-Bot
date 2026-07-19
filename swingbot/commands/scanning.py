"""!check, !session, !status, and the automatic background session-scan loop."""
import asyncio
import datetime as dt
import json
import os
import random
import time

import discord
from discord.ext import tasks

from swingbot import config
from swingbot.config import auto_reload_if_changed
from swingbot.core import scan_engine
from swingbot.core.analytics.rank import rank_plans
from swingbot.bot_core import bot, in_session, log, SESSION_TZ, install_reload_signal_handler, on_config_reload
from swingbot.core.account import load_account_config
from swingbot.core.data import get_current_price
from swingbot.core.performance import TradeLog
from swingbot.core.strategy import HORIZONS
from swingbot.core.watchlist import load_watchlist

_TRIGGER_FILE         = os.path.join(config.DATA_DIR, "trigger_check.flag")
# Queue file written by the admin UI when a trade is manually closed.
# Each line is a JSON-encoded trade record; the bot drains it and posts
# to DISCORD_CHANNEL_TRADES_HISTORY_ID, then deletes the file.
_MANUAL_CLOSE_QUEUE   = os.path.join(config.DATA_DIR, "manual_close_notify.json")
_PAUSE_FILE = os.path.join(config.DATA_DIR, "scan_paused.flag")
_HEARTBEAT_FILE = os.path.join(config.DATA_DIR, "bot_heartbeat.json")

# Tracks whether the trading session (in_session()) was active as of the
# last tick, so _check_session_transition() can tell "just opened"/"just
# closed" apart from "still open"/"still closed" -- None means "not
# established yet" (right after a bot (re)start), which deliberately
# suppresses the very first check: a restart that happens to land
# mid-session shouldn't fire a false "welcome" the moment it reconnects.
_session_was_active: bool | None = None

# Healthcheck messages sent so far in the CURRENT hour bucket, and which
# bucket that is -- see _post_healthcheck()'s hourly-cleanup logic.
# In-memory only (not persisted across restarts): a bot restart simply
# starts a fresh bucket, so at most the prior hour's healthchecks linger
# an extra cycle rather than being cleaned up immediately -- an acceptable
# trade-off for what's purely a channel-tidiness feature.
_healthcheck_msgs: list = []
_healthcheck_hour_bucket: tuple | None = None

# Session welcome/goodbye message pools -- see _check_session_transition().
# One is picked at random each time rather than always sending the exact
# same line, so a person watching the channel every day doesn't get the
# same two sentences on repeat for months. Deliberately mixed in tone
# (motivational / funny / supportive / reflective) rather than picking
# one register and sticking to it -- variety in TONE, not just wording,
# is what actually keeps it feeling alive instead of like a slightly
# reworded template. Every entry uses the same {start}/{end}/{interval}/
# {open_count}/{plural} placeholders so any one of them can be picked and
# .format()-ed the same way regardless of which it is.
_WELCOME_MESSAGES = (
    "☀️ **Rise and grind!** The trading session is open ({start:02d}:00–{end:02d}:00 Europe/Berlin), "
    "scanning every {interval} min. 📂 {open_count} open trade{plural} carried over from before. "
    "Let's make today count! 🚀",

    "🐷 **Oink oink, it's go time!** Session's open ({start:02d}:00–{end:02d}:00 Europe/Berlin), scanning "
    "every {interval} min. 📂 {open_count} open trade{plural} riding shotgun from yesterday. "
    "May the charts be ever in your favor! 📈",

    "🤝 **You've got this.** The session just opened ({start:02d}:00–{end:02d}:00 Europe/Berlin) — I'll be "
    "scanning every {interval} min so you don't have to stare at candles all day. 📂 {open_count} open "
    "trade{plural} still in play. One good decision at a time. 💪",

    "🌱 **A new session, a fresh set of possibilities.** Open {start:02d}:00–{end:02d}:00 Europe/Berlin, "
    "scanning every {interval} min. 📂 {open_count} open trade{plural} from before. Discipline compounds "
    "just like returns do. 🌿",

    "☕ **Coffee's brewed, charts are loaded.** Session's live ({start:02d}:00–{end:02d}:00 Europe/Berlin), "
    "scanning every {interval} min. 📂 {open_count} open trade{plural} already on the board. "
    "Let's not do anything *I'd* regret. 😅",

    "🔥 **Let's go!** Trading session open ({start:02d}:00–{end:02d}:00 Europe/Berlin), scanning every "
    "{interval} min. 📂 {open_count} open trade{plural} carried in. Small consistent wins beat big risky "
    "swings. 🏆",

    "🫶 **Good morning.** Whatever yesterday looked like, today's a clean slate. Session's open "
    "({start:02d}:00–{end:02d}:00 Europe/Berlin), scanning every {interval} min, 📂 {open_count} open "
    "trade{plural} still open. I'm watching the markets with you. 👀",

    "🚨 **Attention: humans and bots alike.** The market has clocked in ({start:02d}:00–{end:02d}:00 "
    "Europe/Berlin) and so have I, scanning every {interval} min. 📂 {open_count} open trade{plural} "
    "pending. Try not to fat-finger anything today. 😄",

    "📖 **Every session is a new page.** Open {start:02d}:00–{end:02d}:00 Europe/Berlin, scanning every "
    "{interval} min. 📂 {open_count} open trade{plural} from before. Write a good one. ✍️",

    "⚡ **Session's live!** {start:02d}:00–{end:02d}:00 Europe/Berlin, scanning every {interval} min, "
    "📂 {open_count} open trade{plural} in play. Stay patient, stay sharp, trust the process. 🎯",

    "🐸 **Ribbit.** (That's frog for \"the market's open\".) {start:02d}:00–{end:02d}:00 Europe/Berlin, "
    "scanning every {interval} min. 📂 {open_count} open trade{plural} hopping along from yesterday. "
    "Let's catch some good setups. 🪰",

    "🌤️ **However you're feeling today, I've got the scanning covered.** Session open {start:02d}:00–"
    "{end:02d}:00 Europe/Berlin, every {interval} min. 📂 {open_count} open trade{plural} still on watch. "
    "Take care of yourself first, the charts will wait. 💛",

    "🧭 **The market doesn't care about yesterday — only today's decisions matter.** Session open "
    "{start:02d}:00–{end:02d}:00 Europe/Berlin, scanning every {interval} min. 📂 {open_count} open "
    "trade{plural} carried over. Trade with intention. 🎈",

    "🥐 **Bonjour, traders.** The session has opened its little croissant shop for the day "
    "({start:02d}:00–{end:02d}:00 Europe/Berlin), scanning every {interval} min. 📂 {open_count} open "
    "trade{plural} still baking from before. Bon appétit, or whatever the trading equivalent is. 🥖",
)

_GOODBYE_MESSAGES = (
    "🌙 **That's a wrap.** Session's closed for today, back at {start:02d}:00 Europe/Berlin tomorrow. "
    "📂 {open_count} open trade{plural} still being watched overnight. However today went, you showed up "
    "— that counts. 👋",

    "😴 **The market has officially gone to bed.** See you at {start:02d}:00 Europe/Berlin. 📂 {open_count} "
    "open trade{plural} sleeping with one eye open overnight. Try to do the same. 🛌",

    "🏁 **Session closed.** Back at {start:02d}:00 Europe/Berlin tomorrow. 📂 {open_count} open "
    "trade{plural} still on watch. Whatever today's result, tomorrow's a new setup. Keep going. 💪",

    "🌇 **Another session in the books.** Reopens {start:02d}:00 Europe/Berlin. 📂 {open_count} open "
    "trade{plural} carrying overnight. Not every day needs to be a win — consistency is the real trade. 🌱",

    "🦉 **The night owls take over now.** (Just kidding, nobody's trading, go to sleep.) Back at "
    "{start:02d}:00 Europe/Berlin. 📂 {open_count} open trade{plural} on overnight watch. 🌌",

    "🤗 **Session's done for today.** Whatever the charts did, you did your part. Reopens {start:02d}:00 "
    "Europe/Berlin. 📂 {open_count} open trade{plural} still being tracked overnight. Rest up, you "
    "earned it. 💤",

    "🌟 **Markets closed, but the grind doesn't stop.** Back at {start:02d}:00 Europe/Berlin. "
    "📂 {open_count} open trade{plural} riding through the night. Review, reflect, come back sharper. 📚",

    "🍕 **Trading's done, dinner's calling.** See you at {start:02d}:00 Europe/Berlin. 📂 {open_count} "
    "open trade{plural} still open, unlike my patience for hunger right now. 😋",

    "🕯️ **The session closes, but the lessons stay with you.** Reopens {start:02d}:00 Europe/Berlin. "
    "📂 {open_count} open trade{plural} watched overnight. Every day in the market teaches something, "
    "if you're paying attention. 🎓",

    "🌆 **That's it for today — well done just for showing up.** Back at {start:02d}:00 Europe/Berlin. "
    "📂 {open_count} open trade{plural} being watched overnight. See you tomorrow. 💙",

    "🎬 **And... cut!** That's a wrap on today's episode of \"Watching Candles Move.\" Next one airs "
    "{start:02d}:00 Europe/Berlin. 📂 {open_count} open trade{plural} still in the plot. 🍿",

    "🚀 **Session closed — but growth doesn't clock out.** Back at {start:02d}:00 Europe/Berlin. "
    "📂 {open_count} open trade{plural} still flying overnight. See you tomorrow, ready to go again. 🌠",

    "🌌 **The market rests, and so should you.** Reopens {start:02d}:00 Europe/Berlin. 📂 {open_count} "
    "open trade{plural} quietly held overnight. Patience is a position too. 🙏",

    "🧦 **Market's closed, socks are off.** Back at {start:02d}:00 Europe/Berlin. 📂 {open_count} open "
    "trade{plural} still open somewhere out there in the dark. Sleep well. 😴",
)


def _write_heartbeat() -> None:
    """
    Stamps a small JSON file that the admin UI reads to show a blinking
    green/red bot-liveness dot on the Dashboard. Written on every
    session_scan tick (including off-hours / paused ticks) so the dot
    goes red only when the bot process itself stops responding, not just
    because it's outside the trading session window.
    """
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_HEARTBEAT_FILE, "w") as fh:
            json.dump({
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "session_active": in_session(),
                "scan_paused": is_scan_paused(),
            }, fh)
    except Exception:
        pass


def is_scan_paused() -> bool:
    """Whether the automatic background scan loop is currently paused
    (via the admin UI toggle or the !pause command). Manual scans
    (!check, and the admin UI's "Run !check now" trigger) are NOT
    affected by this -- pausing only stops the unattended, scheduled
    scanning so the user can still check on demand."""
    return os.path.exists(_PAUSE_FILE)


def set_scan_paused(paused: bool) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    if paused:
        with open(_PAUSE_FILE, "w") as f:
            f.write(dt.datetime.now(dt.timezone.utc).isoformat())
    else:
        try:
            os.remove(_PAUSE_FILE)
        except OSError:
            pass  # already resumed by a parallel caller

trade_log = scan_engine.trade_log


def _ordered_alerts(alerts: list, today=None) -> list:
    """Splits `alerts` (each a (embed, chart_path, plan_or_none) tuple)
    into plan-carrying and legacy groups, ranks the plan-carrying group
    by analytics.rank.rank_plans (THE shared ordering -- see Plan A
    Task A18), and returns plan-carrying alerts first (highest
    follow_score first), then every legacy (no-plan) alert in its
    original scan order, unchanged. rank_plans is given the plan
    objects directly and returns them in ranked order; this function
    re-derives the alert tuple order from that ranked plan-object list
    rather than re-scoring anything itself, so there is exactly one
    place (analytics.rank) that ever computes follow_score."""
    plan_alerts = [a for a in alerts if a[2] is not None]
    legacy_alerts = [a for a in alerts if a[2] is None]

    ranked_plans = rank_plans([a[2] for a in plan_alerts], today=today)
    by_plan_id = {id(a[2]): a for a in plan_alerts}
    ranked_alert_tuples = [by_plan_id[id(p)] for p in ranked_plans]

    return ranked_alert_tuples + legacy_alerts


async def _send_alerts(destination, alerts):
    """alerts: list of (embed, chart_path, plan_or_none) 3-tuples.

    Every plan-carrying alert gets a PlanActionView(plan.plan_id,
    author_id=None) attached (any user may click); legacy (no-plan) alerts
    get no view. PlanActionView is imported lazily here rather than at
    module top to avoid a circular import: views.py imports from
    swingbot.core.plan_store, and scanning.py is imported very early during
    bot startup (bot_core.py registers commands from every
    swingbot/commands/* module) -- a top-level import is safe today (no
    cycle exists), but the lazy import documents the intent and costs
    nothing at this call frequency (once per alert message, not per scan
    tick).
    """
    from swingbot.commands.views import PlanActionView

    for embed, chart_path, plan in _ordered_alerts(alerts):
        view = PlanActionView(plan.plan_id, author_id=None) if plan is not None else None
        kwargs = {"embed": embed}
        if chart_path:
            kwargs["file"] = discord.File(chart_path, filename=os.path.basename(chart_path))
        if view is not None:
            kwargs["view"] = view
        msg = await destination.send(**kwargs)
        if view is not None:
            view.message = msg


def _presence_text() -> str:
    """
    Builds the short status string shown as the bot's Discord presence
    (the "Watching ..." line under its name in the member list) -- see
    _refresh_presence(). Replaces the old approach of posting a fresh
    "nothing new to post" message to the alerts channel on every single
    scan tick just to prove the process was still alive: that was pure
    channel noise on a busy watchlist (a new message every
    SCAN_INTERVAL_MINUTES, forever, regardless of whether anything
    actually happened), and it's not even a reliable liveness signal --
    a hung process still shows its last-sent message sitting there
    looking perfectly fine. A live, always-current presence string next
    to the bot's own name updates in place and needs no channel message
    at all to prove the bot is up right now.
    """
    open_count = trade_log.get_stats()["open"]
    plural = "" if open_count == 1 else "s"
    if is_scan_paused():
        return f"⏸ Paused · {open_count} open trade{plural}"
    if not in_session():
        return f"😴 Off-hours · {open_count} open trade{plural}"
    now_str = dt.datetime.now(SESSION_TZ).strftime("%H:%M")
    return f"🟢 Active · {open_count} open trade{plural} · {now_str}"


async def _refresh_presence():
    """
    Pushes the current _presence_text() onto the bot's Discord presence
    (an Activity of type "Watching", e.g. "Watching 🟢 Active · 3 open
    trades · 14:35") AND sets the bot's status dot so it works like the
    blinking green/red circle in the admin Dashboard:

      discord.Status.online  → solid green dot  (in session, scanning)
      discord.Status.idle    → yellow crescent   (bot running but off-hours)
      discord.Status.dnd     → red dot with dash (scan paused)

    The dot is visible next to the bot's name in the Discord member list,
    in DMs, and wherever the bot's avatar appears -- no channel message
    needed, updates in place, and goes red automatically the moment the
    bot process stops responding (Discord marks it offline).

    Called every session_scan tick (at least every SCAN_INTERVAL_MINUTES)
    plus once at startup and immediately after !pause/!resume so a manual
    state change is reflected right away. Best-effort: a failure here is
    logged and swallowed rather than taking down a scan.
    """
    try:
        if is_scan_paused():
            status = discord.Status.dnd       # 🔴 red dot with dash
        elif not in_session():
            status = discord.Status.idle      # 🌙 yellow crescent (off-hours)
        else:
            status = discord.Status.online    # 🟢 solid green dot
        await bot.change_presence(
            status=status,
            activity=discord.Activity(type=discord.ActivityType.watching, name=_presence_text()),
        )
    except Exception as e:
        log.debug("Could not update Discord presence: %s", e)


async def _check_session_transition(channel) -> None:
    """
    Fires a warm welcome message the moment the trading session (see
    in_session()/config.SESSION_START_HOUR/SESSION_END_HOUR) opens for
    the day, and a warm goodbye the moment it closes -- distinct from
    the one-time "Bot online" message (posted once when the PROCESS
    starts, regardless of session state -- see session_scan's on_ready
    handler) and from daily_recap (an analytical end-of-day retrospective,
    not a goodbye). Checked every tick, even while scanning is paused --
    the session boundary is about market hours, not whether the bot is
    actively scanning right now.

    _session_was_active starts as None specifically so a bot restart
    that happens to land mid-session doesn't fire a false "welcome" the
    instant it reconnects -- the first tick after (re)start just records
    the current state as a baseline, no message, and only ticks AFTER
    that can be a genuine transition.

    Which exact message gets sent is randomized every time (see
    _WELCOME_MESSAGES/_GOODBYE_MESSAGES) -- picking one of a wide, mixed-
    tone pool instead of always sending the same fixed line is what makes
    it feel like a fresh, living message instead of a canned template,
    even though the underlying event (session open/close) is the same
    every day.
    """
    global _session_was_active
    active = in_session()
    if _session_was_active is None:
        _session_was_active = active
        return
    if active == _session_was_active:
        return

    open_count = trade_log.get_stats()["open"]
    plural = "" if open_count == 1 else "s"
    pool = _WELCOME_MESSAGES if active else _GOODBYE_MESSAGES
    message = random.choice(pool).format(
        start=config.SESSION_START_HOUR, end=config.SESSION_END_HOUR,
        interval=config.SCAN_INTERVAL_MINUTES, open_count=open_count, plural=plural,
    )
    try:
        await channel.send(message)
    except Exception as e:
        log.warning("Could not post session welcome/goodbye message: %s", e)
    _session_was_active = active


async def _post_healthcheck(channel, text: str) -> None:
    """
    Posts the per-tick healthcheck message and keeps the channel from
    accumulating them indefinitely: at most one CLOCK HOUR's worth of
    healthchecks stay visible at a time. The moment the wall-clock hour
    rolls over (Europe/Berlin, matching the rest of the session-window
    logic), every healthcheck message sent during the PREVIOUS hour is
    deleted before this tick's new one goes up -- so on a busy watchlist
    scanning every few minutes, the channel doesn't slowly fill up with
    dozens of near-identical "nothing new" lines over the course of a
    day; at most the current hour's ticks are ever visible.

    In-memory bucket tracking only (_healthcheck_msgs/_healthcheck_hour_
    bucket) -- a bot restart just starts a fresh bucket, so the very last
    hour's messages before a restart may briefly outlive their hour, a
    harmless one-time exception.
    """
    global _healthcheck_msgs, _healthcheck_hour_bucket
    now = dt.datetime.now(SESSION_TZ)
    hour_bucket = (now.date(), now.hour)

    if _healthcheck_hour_bucket is not None and hour_bucket != _healthcheck_hour_bucket:
        for old_msg in _healthcheck_msgs:
            try:
                await old_msg.delete()
            except Exception:
                pass  # already gone, or too old/no permission -- not worth failing the tick over
        _healthcheck_msgs = []
    _healthcheck_hour_bucket = hour_bucket

    try:
        # silent=True -- a routine per-tick heartbeat, not something worth
        # a push notification/sound every SCAN_INTERVAL_MINUTES. Sets
        # Discord's own "suppress notifications" message flag, so it still
        # posts and appears in the channel normally, it just doesn't
        # ping/buzz the user's devices the way a real alert still should.
        msg = await channel.send(text, silent=True)
        _healthcheck_msgs.append(msg)
    except Exception as e:
        log.warning("Could not post healthcheck message: %s", e)


@tasks.loop(minutes=config.SCAN_INTERVAL_MINUTES)
async def session_scan():
    # The entire tick's real work is wrapped in a try/except (see below) so
    # ONE bad tick -- a transient network error, a malformed price bar, any
    # unhandled exception anywhere inside run_scan()'s pandas/network-heavy
    # pipeline -- can never take the whole loop down. Without this,
    # discord.py's tasks.Loop logs the traceback once and then just STOPS
    # calling this function forever (reconnect=True only auto-retries
    # discord-connection-related errors, not a generic exception raised by
    # our own scan code) -- silently, with no further log lines at all,
    # which is exactly the "bot went quiet and never scanned again" failure
    # mode seen before. Catching everything here guarantees a scan attempt
    # every SCAN_INTERVAL_MINUTES no matter what happened on the last one.
    try:
        await _session_scan_tick()
    except Exception:
        log.exception("session_scan tick failed -- will retry on the next scheduled tick "
                       "(every %d min) instead of stopping the loop entirely", config.SCAN_INTERVAL_MINUTES)


def _refresh_snapshot_safely() -> None:
    try:
        from swingbot.core.analytics.snapshots import refresh_snapshot
        refresh_snapshot()
    except Exception:
        log.warning("post-scan snapshot refresh failed", exc_info=True)


async def _session_scan_tick():
    # Always refresh the live-status presence first, even on the early-return
    # paths below (paused / outside session / missing channel config) -- the
    # whole point is that this reflects the bot's real current state at least
    # once every SCAN_INTERVAL_MINUTES no matter what else happens this tick.
    await _refresh_presence()
    # Write heartbeat file so the admin dashboard can show a live green/red
    # status dot even when the bot is paused or outside the session window.
    _write_heartbeat()

    # Resolved once, up front, so the session welcome/goodbye check below
    # can run regardless of pause state (the session boundary is about
    # market hours, not whether scanning itself is paused) -- the rest of
    # the tick still early-returns on paused/off-session/missing-config
    # exactly as before.
    channel = None
    if config.DISCORD_CHANNEL_TRADES_ID:
        channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID))
    if channel is not None:
        await _check_session_transition(channel)

    if is_scan_paused():
        log.debug("session_scan tick skipped -- scanning is paused")
        return
    if not in_session():
        log.debug("session_scan tick skipped -- outside the session window")
        return
    if channel is None:
        log.warning("DISCORD_CHANNEL_TRADES_ID not set or channel not found; skipping scheduled post.")
        return

    now_str = dt.datetime.now(SESSION_TZ).strftime("%H:%M")
    log.info("Running session scan at %s…", now_str)
    progress = scan_engine.ScanProgress()
    alerts = await scan_engine.run_scan(require_confirmation=True, bot=bot, progress=progress)
    await _send_alerts(channel, alerts)

    from swingbot.core.charts.cache import purge
    await asyncio.to_thread(purge)

    _refresh_snapshot_safely()

    f = progress.funnel
    if alerts:
        log.info("Posted %d new confirmed signal(s).", len(alerts))
        if f:
            # "qualifying" and "alerts posted" can legitimately differ:
            # qualifying scenarios found for the same ticker+trend with a
            # near-identical entry/stop/target get merged into one alert by
            # dedup_scan_items() (same real setup, confirmed by more than one
            # strategy/horizon), and a qualifying scenario for a ticker that
            # already has an open trade is skipped rather than re-alerted.
            # Spelling that out here so "why did qualifying=2 but alerts=1"
            # is answerable at a glance instead of looking like a bug.
            gap_parts = []
            merged = max(0, f.get("fully_qualifying", 0) - f.get("deduped", f.get("fully_qualifying", 0)))
            if merged:
                gap_parts.append(f"{merged} merged as duplicate setup(s)")
            if f.get("skipped_already_open", 0):
                gap_parts.append(f"{f['skipped_already_open']} already open")
            gap_str = f" ({', '.join(gap_parts)})" if gap_parts else ""
            # A little more visual variety than a single 🔍 -- a quick
            # traffic-light-style read (🟢 several new alerts, 🟡 just one,
            # plus a ✨ sparkle when at least one is a priority ⭐ setup) so
            # the channel doesn't read as one flat wall of identical emoji.
            n = len(alerts)
            headline_icon = "🟢" if n >= 3 else "🟡" if n >= 1 else "⚪"
            sparkle = " ✨" if any("⭐" in (a[0].title or "") for a in alerts) else ""
            summary = (
                f"{headline_icon} 🔍 **Scan** ({now_str}) — 📡 {f['tickers']} tickers, {f['checked']} combos checked → "
                f"🧮 {f['scenarios_found']} scenario(s) found (✅ {f['fully_qualifying']} qualifying) → "
                f"**🚨 {n} new alert(s) posted above**{sparkle}{gap_str}"
            )
            await channel.send(summary)
    else:
        log.info("Session scan complete at %s — nothing new to post.", now_str)
        not_ready_parts = []
        if f and (f["scenarios_found"] > 0 or f["tickers"] > 0):
            if f.get("failed_min_confluence", 0):
                not_ready_parts.append(f"{f['failed_min_confluence']} below min strategies")
            if f.get("failed_min_confidence", 0):
                not_ready_parts.append(f"{f['failed_min_confidence']} below min confidence")
            if f.get("awaiting_confirmation", 0):
                not_ready_parts.append(f"{f['awaiting_confirmation']} awaiting confirmation")
            not_ready_log_str = (", ".join(not_ready_parts) + " — ") if not_ready_parts else ""
            log.info(
                "Scan detail (%s): %d tickers -> %d scenario(s) found (%d qualifying), %snothing new to post",
                now_str, f["tickers"], f["scenarios_found"], f["fully_qualifying"], not_ready_log_str,
            )

        # Healthcheck post -- one short message every scan tick (every
        # SCAN_INTERVAL_MINUTES), even when nothing qualified. Earlier this
        # branch deliberately posted NOTHING to avoid channel noise (see
        # _presence_text()'s docstring -- the bot's Discord presence dot was
        # meant to be the liveness signal instead). Brought back on request:
        # a live presence dot is easy to miss, and watching a message land
        # in the channel every 5 minutes is a much more obvious "yes, it's
        # still alive and actually scanning" signal than checking a status
        # dot next to the bot's name. Kept to one compact line (no embed, no
        # chart) specifically so it doesn't turn into the same noise problem
        # that got this removed the first time.
        open_count = trade_log.get_stats()["open"]
        if f:
            # Rewritten for clarity -- the old one-line version packed
            # "qualifying" and "awaiting confirmation" next to each other
            # with no explanation, which reads as a contradiction ("if it
            # qualified, why wasn't it shown?"). They're not mutually
            # exclusive: "qualifying" = passed every hard requirement
            # (min strategies confirmed, min confidence, min reward:risk,
            # etc.); "awaiting confirmation" is a SUBSET of qualifying --
            # a scenario that passed everything but hasn't yet reappeared
            # for SIGNAL_CONFIRMATION_SCANS consecutive scans in a row
            # (the automatic scan's debounce filter, meant to skip
            # intraday flicker -- see engine.py's module docstring).
            # "below min strategies"/"below min confidence" are separate
            # FAILURE tallies, not a partition of scenarios_found -- one
            # scenario can fail more than one requirement at once, so
            # those numbers can (and often do) add up to more than the
            # total scenario count. Spelling all of this out in the
            # message itself so the numbers don't need a code-read to make
            # sense of.
            awaiting = f.get("awaiting_confirmation", 0)
            confirm_note = (
                f" (needs to reappear {config.SIGNAL_CONFIRMATION_SCANS} scan(s) in a row before it posts)"
                if awaiting else ""
            )
            fail_bits = []
            if f.get("failed_min_confluence", 0):
                fail_bits.append(f"{f['failed_min_confluence']} below min strategies")
            if f.get("failed_min_confidence", 0):
                fail_bits.append(f"{f['failed_min_confidence']} below min confidence")
            bullets = [
                f"📡 {f['tickers']} tickers scanned",
                f"🧮 {f['scenarios_found']} scenario(s) found",
                f"✅ {f['fully_qualifying']} fully qualifying (⏳ {awaiting} still awaiting confirmation{confirm_note})",
            ]
            if fail_bits:
                bullets.append(f"❌ failed a requirement: {', '.join(fail_bits)}")
            bullets.append(f"📂 {open_count} open trade(s)")
            healthcheck = (
                f"💓 **Healthcheck** ({now_str}) — nothing new this tick\n"
                + "\n".join(f"• {b}" for b in bullets)
            )
        else:
            healthcheck = (
                f"💓 **Healthcheck** ({now_str}) — scan complete, nothing new\n"
                f"• 📂 {open_count} open trade(s)"
            )
        await _post_healthcheck(channel, healthcheck)

    # Refresh again now that this tick's own scan may have changed the open-
    # trade count (a trade closing mid-scan shouldn't have to wait for next
    # tick's presence update to be reflected).
    await _refresh_presence()


@session_scan.error
async def _session_scan_error(exc: Exception):
    """
    Last-resort safety net -- _session_scan_tick()'s own try/except above
    should catch everything and let the loop keep ticking on schedule, but
    if something still manages to escape (e.g. an exception raised by
    discord.py's own task-loop machinery, outside our function body), this
    logs it AND explicitly restarts the loop rather than letting
    discord.ext.tasks quietly stop calling session_scan forever.
    """
    log.exception("session_scan loop raised past its own try/except -- restarting the loop: %s", exc)
    if not session_scan.is_running():
        session_scan.restart()


@tasks.loop(minutes=15)
async def heartbeat():
    """
    Periodic "still alive and here's the state" LOG line only (never posted
    to Discord) -- makes it easy to confirm from the logs alone (Discord UI
    or the admin UI's Logs page) that the process is actually running and
    see its basic status at a glance, without needing to correlate scan-tick
    timestamps. The user-visible "is the bot alive" signal lives on the
    bot's own Discord presence instead (see _refresh_presence(), refreshed
    every session_scan tick -- i.e. at least every SCAN_INTERVAL_MINUTES),
    not in a channel message; this log-only heartbeat is a slower (15 min),
    log-file-only companion to that, unrelated to anything posted in Discord.
    """
    open_count = trade_log.get_stats()["open"]
    watchlist_size = len(load_watchlist())
    latency_ms = round(bot.latency * 1000) if bot.latency else None
    log.info(
        "Heartbeat -- session=%s scan=%s watchlist=%d open_trades=%d gateway_latency=%sms",
        "active" if in_session() else "inactive", "paused" if is_scan_paused() else "running",
        watchlist_size, open_count,
        latency_ms if latency_ms is not None else "n/a",
    )


@tasks.loop(seconds=30)
async def config_watcher():
    """
    Polls .env mtime every 30 seconds so settings saved via the admin UI
    apply quickly even when the Docker socket isn't mounted (which would
    have allowed an immediate SIGHUP). Without this, changes would only
    take effect at the next scan tick (up to SCAN_INTERVAL_MINUTES away).
    The mtime check is a single stat() syscall -- no file I/O -- so the
    overhead is negligible.

    Also watches for a trigger file written by the admin UI's "Run !check now"
    button. When found, runs a full scan immediately (same as !check all) and
    deletes the trigger file so it doesn't fire again next tick.
    """
    changed = await asyncio.to_thread(auto_reload_if_changed)
    if changed:
        # LOG_LEVEL change needs the Python logging level updated too
        if "LOG_LEVEL" in changed:
            import logging
            logging.getLogger().setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
        if "SCAN_INTERVAL_MINUTES" in changed and session_scan.is_running():
            session_scan.change_interval(minutes=config.SCAN_INTERVAL_MINUTES)
            log.info("Scan interval hot-reloaded to every %d min (takes effect next tick).",
                     config.SCAN_INTERVAL_MINUTES)
        log.info("Config auto-reloaded from .env -- %d setting(s) changed: %s",
                 len(changed), ", ".join(f"{k}={v[1]!r}" for k, v in changed.items()))

        # Notify Discord channel about key setting changes so the user can
        # confirm the new value is live without needing to check the logs.
        _notify_keys = {
            "MIN_ALERT_CONFIDENCE_LEVEL": (
                lambda old, new: (
                    f"⚙️ **Min confidence level** updated: Lv{old} → Lv{new}  "
                    f"(next `!check` and scheduled scans will use Lv{new}+)"
                )
            ),
            "MIN_TARGET_CONFLUENCE_COUNT": (
                lambda old, new: (
                    f"⚙️ **Min strategies confirmed** updated: {old} → {new}"
                )
            ),
            "SCAN_INTERVAL_MINUTES": (
                lambda old, new: (
                    f"⚙️ **Scan interval** updated: every {old} min → every {new} min"
                )
            ),
            "MIN_RISK_REWARD_RATIO": (
                lambda old, new: (
                    f"⚙️ **Min R:R ratio** updated: {old} → {new}"
                )
            ),
        }
        if config.DISCORD_CHANNEL_TRADES_ID:
            channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID))
            if channel:
                for attr_key, fmt_fn in _notify_keys.items():
                    if attr_key in changed:
                        old_val, new_val = changed[attr_key]
                        try:
                            await channel.send(fmt_fn(old_val, new_val))
                        except Exception as _e:
                            log.warning("Could not post config-change notice to Discord: %s", _e)

    # --- Admin UI manual-close notification queue ---
    if os.path.exists(_MANUAL_CLOSE_QUEUE):
        try:
            with open(_MANUAL_CLOSE_QUEUE, "r") as _qf:
                _queued = json.load(_qf)
        except Exception as _qe:
            log.warning("Could not read manual_close_notify queue: %s", _qe)
            _queued = []
        if _queued:
            try:
                os.remove(_MANUAL_CLOSE_QUEUE)
            except OSError:
                pass
            from swingbot.core.scanning.embeds import notify_closed_trades
            try:
                await notify_closed_trades(bot, _queued)
                log.info("Posted %d manually-closed trade notification(s) to Discord.", len(_queued))
            except Exception as _ne:
                log.warning("Failed to post manual-close notifications: %s", _ne)

    # --- Admin UI "Run !check now" trigger ---
    if os.path.exists(_TRIGGER_FILE):
        try:
            os.remove(_TRIGGER_FILE)
        except OSError:
            pass  # already removed by a parallel tick or a concurrent process
        else:
            log.info("Admin UI triggered a manual !check scan.")
            if not config.DISCORD_CHANNEL_TRADES_ID:
                log.warning("CHANNEL_ID not set; cannot post scan results.")
                return
            channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID))
            if channel is None:
                try:
                    channel = await bot.fetch_channel(int(config.DISCORD_CHANNEL_TRADES_ID))
                except Exception as _ce:
                    log.warning("Could not resolve channel %s for triggered scan: %s", config.DISCORD_CHANNEL_TRADES_ID, _ce)
                    return
            min_lv = config.MIN_ALERT_CONFIDENCE_LEVEL
            # Post a live-updating progress message — same UX as the Discord
            # !check command so the user sees per-ticker progress in real time.
            progress_msg = await channel.send(
                f"🔍 **Manual scan triggered from admin UI** · min confidence Lv{min_lv}"
                f" · crawling data… 0%"
            )
            progress = scan_engine.ScanProgress()

            async def _ui_poll_progress():
                last_shown = None
                while True:
                    await asyncio.sleep(2.0)
                    if progress.stage == "crawling data":
                        pct = round(progress.done / progress.total * 100) if progress.total else 0
                        ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                        label = (
                            f"📡 **Crawling** (UI trigger) — {progress.done}/{progress.total} "
                            f"ticker(s) fetched ({pct}%){ticker_bit}"
                        )
                    elif progress.stage == "building alerts":
                        if progress.alerts_total:
                            label = (
                                f"📊 **Building alerts** (UI trigger) — "
                                f"{progress.alerts_done}/{progress.alerts_total} done (generating charts…)"
                            )
                        else:
                            label = (
                                f"📊 **Deduplicating** (UI trigger) — "
                                f"{progress.qualifying_found} qualifying scenario(s) found, merging…"
                            )
                    else:
                        ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
                        found_bit = (
                            f" · **{progress.qualifying_found} qualifying** so far"
                            if progress.qualifying_found else ""
                        )
                        label = (
                            f"🔬 **Analyzing** (UI trigger) — {progress.done}/{progress.total} "
                            f"ticker·horizon combo(s) ({progress.pct}%){ticker_bit}{found_bit}"
                        )
                    if label != last_shown:
                        try:
                            await progress_msg.edit(content=label)
                        except discord.NotFound:
                            return
                        last_shown = label

            poller = asyncio.create_task(_ui_poll_progress())
            try:
                alerts = await scan_engine.run_scan(require_confirmation=False, bot=bot, progress=progress)
            finally:
                poller.cancel()

            await _send_alerts(channel, alerts)
            f = progress.funnel
            if progress.stopped:
                summary = (
                    f"🛑 **Triggered scan stopped early** (by the admin UI's Stop button or `!stop`) — "
                    f"**{len(alerts)} alert(s)** built from what completed before the stop."
                )
            elif f:
                lv_counts = f.get("conf_level_counts", {})
                lv_breakdown = (
                    "  ".join(f"Lv{lv}:{cnt}" for lv, cnt in sorted(lv_counts.items()))
                    if lv_counts else "none"
                )
                summary = (
                    f"✅ **Triggered scan complete** — {f['tickers']} ticker(s) · "
                    f"{f['fully_qualifying']} fully qualifying → **{len(alerts)} alert(s)**\n"
                    f"Confidence breakdown: {lv_breakdown}  (min Lv{min_lv})"
                )
            else:
                summary = f"✅ **Triggered scan complete** — {len(alerts)} alert(s) found (min confidence: Lv{min_lv})."
            try:
                await progress_msg.edit(content=summary)
            except discord.NotFound:
                await channel.send(summary)
            log.info("Triggered scan complete — %d alert(s) posted%s.", len(alerts),
                      " (stopped early)" if progress.stopped else "")


@tasks.loop(seconds=60)
async def trade_monitor():
    """
    Lightweight SL/TP price monitor — runs every 60 seconds, entirely
    separate from the full scan cycle.  For every open trade it fetches
    the live price (incl. premarket/aftermarket via get_current_price),
    calls close_if_live_price_hit() for an exact SL/TP hit, and then
    check_near_tp_timeout() for whatever's still open -- closing early,
    as a win at the live price, any trade that's gotten most of the way
    to its target and then stalled there instead of actually tapping it
    (see config.NEAR_TP_TIMEOUT_*). If any trade closes either way, a
    notification is posted to DISCORD_CHANNEL_TRADES_HISTORY_ID immediately,
    without waiting for the next scheduled scan.

    Skips silently if a full scan is already running (which does the same
    SL/TP check inside update_open_trades, but not the near-TP timeout --
    that's this task's alone) to avoid a race on trades.json.
    Also skips when there are no open trades, keeping the overhead
    proportional to actual activity.
    """
    if scan_engine.is_scan_running():
        return  # full scan already handles SL/TP this tick

    open_trades = trade_log.get_trades(status="open", limit=200)
    if not open_trades:
        return

    tickers = list({t["ticker"] for t in open_trades})
    all_newly_closed = []

    for ticker in tickers:
        try:
            live = await asyncio.to_thread(get_current_price, ticker)
        except Exception as exc:
            log.debug("trade_monitor: price fetch failed for %s: %s", ticker, exc)
            continue
        if not live or live <= 0:
            continue
        try:
            closed = await asyncio.to_thread(trade_log.close_if_live_price_hit, ticker, live)
        except Exception as exc:
            log.warning("trade_monitor: close_if_live_price_hit failed for %s: %s", ticker, exc)
            continue
        if closed:
            log.info("trade_monitor: %d trade(s) closed for %s (live=%.4f)", len(closed), ticker, live)
            all_newly_closed.extend(closed)

        # Near-TP timeout exit: for whatever's STILL open on this ticker
        # after the exact SL/TP check above (a trade that just tapped its
        # real target this same tick is already gone from "open" status by
        # the time this runs) -- locks in profit on a trade that got most
        # of the way to target and then stalled instead of actually
        # touching it. See config.NEAR_TP_TIMEOUT_* / performance.py's
        # check_near_tp_timeout docstring for the exact rule.
        try:
            near_tp_closed = await asyncio.to_thread(trade_log.check_near_tp_timeout, ticker, live)
        except Exception as exc:
            log.warning("trade_monitor: check_near_tp_timeout failed for %s: %s", ticker, exc)
            continue
        if near_tp_closed:
            log.info("trade_monitor: %d trade(s) closed for %s via near-TP timeout (live=%.4f)",
                      len(near_tp_closed), ticker, live)
            all_newly_closed.extend(near_tp_closed)

    # v2 plan lifecycle tick (flag-gated; no-op while INTRADAY_MANAGER_V2=false)
    from swingbot.core import plan_manager
    try:
        plan_events = await asyncio.to_thread(plan_manager.run_manager_tick)
    except Exception as exc:
        log.warning("trade_monitor: plan manager tick failed: %s", exc)
        plan_events = []
    if plan_events:
        from swingbot.core.scanning.embeds import notify_plan_events
        await notify_plan_events(bot, plan_events)   # Task 72

    if all_newly_closed:
        from swingbot.core.scanning.embeds import notify_closed_trades
        try:
            await notify_closed_trades(bot, all_newly_closed)
        except Exception as exc:
            log.warning("trade_monitor: failed to post close notifications: %s", exc)
        await _refresh_presence()


_recap_fired_date: dt.date | None = None   # tracks the last date a recap was posted


async def _post_retrospective(channel_id_override: int | None = None, today=None):
    """Build and post today's (or `today`'s, if given) retrospective. Called
    by daily_recap task and !recap command."""
    from swingbot.core.retrospective import build_daily_retrospective

    all_trades = trade_log.get_trades(limit=10_000)
    messages   = build_daily_retrospective(all_trades, today=today)

    # Resolve target channel: explicit override → DISCORD_CHANNEL_RETROSPECTIVE_ID → DISCORD_CHANNEL_TRADES_HISTORY_ID
    cid = channel_id_override
    if not cid:
        rc = getattr(config, "DISCORD_CHANNEL_RETROSPECTIVE_ID", None)
        if rc:
            try:
                cid = int(rc)
            except (ValueError, TypeError):
                pass
    if not cid:
        cc = getattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", None)
        if cc:
            try:
                cid = int(cc)
            except (ValueError, TypeError):
                pass
    if not cid:
        log.warning("daily_recap: no channel configured (set DISCORD_CHANNEL_RETROSPECTIVE_ID or DISCORD_CHANNEL_TRADES_HISTORY_ID).")
        return

    channel = bot.get_channel(cid)
    if channel is None:
        try:
            channel = await bot.fetch_channel(cid)
        except Exception as exc:
            log.warning("daily_recap: cannot resolve channel %s: %s", cid, exc)
            return

    for msg in messages:
        if not msg.strip():
            continue
        # Discord message limit is 2000 chars; chunk if needed
        while len(msg) > 1990:
            split_at = msg.rfind("\n", 0, 1990)
            if split_at == -1:
                split_at = 1990
            await channel.send(msg[:split_at])
            msg = msg[split_at:]
        if msg.strip():
            await channel.send(msg)


@tasks.loop(minutes=1)
async def daily_recap():
    """
    Posts the end-of-session retrospective once per weekday, at SESSION_END_HOUR
    (Europe/Berlin) + 15 minutes, so it runs right after the trading session closes.
    Guards against duplicate posts within the same calendar day.
    """
    global _recap_fired_date
    try:
        from zoneinfo import ZoneInfo as _ZI
        now = dt.datetime.now(_ZI("Europe/Berlin"))
    except Exception:
        now = dt.datetime.utcnow()

    # Only on Mon–Fri (weekday() 0–4)
    if now.weekday() > 4:
        return

    today = now.date()
    if _recap_fired_date == today:
        return  # already posted today

    # Fire at SESSION_END_HOUR:15 Berlin time (15-min grace after session closes)
    trigger_hour   = config.SESSION_END_HOUR
    trigger_minute = 15
    if now.hour != trigger_hour or now.minute < trigger_minute:
        return

    log.info("daily_recap: posting end-of-session retrospective for %s", today)
    _recap_fired_date = today
    try:
        await _post_retrospective()
    except Exception as exc:
        log.exception("daily_recap: failed to post retrospective: %s", exc)


@on_config_reload
def _apply_scan_interval_change(changed: dict):
    """SCAN_INTERVAL_MINUTES is baked into @tasks.loop() at decoration time
    (discord.ext.tasks doesn't re-read it live), so a hot reload needs to
    explicitly push the new interval onto the running loop."""
    if "SCAN_INTERVAL_MINUTES" in changed and session_scan.is_running():
        new_minutes = config.SCAN_INTERVAL_MINUTES
        session_scan.change_interval(minutes=new_minutes)
        log.info("Scan interval hot-reloaded to every %d minute(s) (takes effect next tick).", new_minutes)


@bot.event
async def on_ready():
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "n/a")
    log.info("Watching %d guild(s): %s", len(bot.guilds), ", ".join(g.name for g in bot.guilds) or "none")
    wl_size = len(load_watchlist())
    log.info(
        "Session window: %02d:00-%02d:00 Europe/Berlin (7 days), scanning every %d min, "
        "%d-scan confirmation, min confidence Lv%d, min %d strategies confirmed (within %.1f%% deviation), "
        "watchlist size %d",
        config.SESSION_START_HOUR, config.SESSION_END_HOUR, config.SCAN_INTERVAL_MINUTES,
        config.SIGNAL_CONFIRMATION_SCANS, config.MIN_ALERT_CONFIDENCE_LEVEL, config.MIN_TARGET_CONFLUENCE_COUNT,
        config.CONFLUENCE_DEVIATION_PCT, wl_size,
    )
    install_reload_signal_handler()
    if not session_scan.is_running():
        session_scan.start()
    if not heartbeat.is_running():
        heartbeat.start()
    if not config_watcher.is_running():
        config_watcher.start()
    if not trade_monitor.is_running():
        trade_monitor.start()
    if not daily_recap.is_running():
        daily_recap.start()
    await _refresh_presence()

    # Sync slash commands to Discord (runs once on startup; safe to call every time)
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s) to Discord.", len(synced))
    except Exception as e:
        log.warning("Failed to sync slash commands: %s", e)

    # Post a startup notice to the alerts channel so there's a visible
    # timestamp in Discord for when the bot came (back) online.
    if config.DISCORD_CHANNEL_TRADES_ID:
        channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID))
        if channel:
            open_count = trade_log.get_stats()["open"]
            await channel.send(
                f"🤖 **Bot online** — {dt.datetime.now(SESSION_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"Session: {config.SESSION_START_HOUR:02d}:00–{config.SESSION_END_HOUR:02d}:00 Berlin · "
                f"scan every {config.SCAN_INTERVAL_MINUTES} min · watchlist: {wl_size} ticker(s) · "
                f"open trades: {open_count} · min confidence: Lv{config.MIN_ALERT_CONFIDENCE_LEVEL}"
            )


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
        await _post_retrospective(channel_id_override=ctx.channel.id, today=today)
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
            # 0.8s (down from 1.5s) so the message visibly updates more
            # often -- on a big watchlist the crawl/analyze phases can each
            # run for tens of seconds, and a slower poll made it easy to
            # mistake "still working, just between updates" for "stuck".
            await asyncio.sleep(0.8)
            elapsed = _elapsed_str()
            if progress.stage == "crawling data":
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

    header = (
        f"📋 **{len(trades)} recorded trade plan(s)** — {range_str}{horiz_str}\n"
        "*(from the trade log — these are plans the bot actually posted)*\n"
    )
    await ctx.send(header)

    # Send each trade as a short summary (avoid chart re-generation)
    for t in trades:
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
        await ctx.send(line)


@bot.command(name="session")
async def session_cmd(ctx):
    from swingbot.bot_core import in_session
    now = dt.datetime.now(SESSION_TZ)
    active = in_session()
    start = config.SESSION_START_HOUR
    end = config.SESSION_END_HOUR
    status = "🟢 **Active**" if active else "🔴 **Inactive**"
    paused_bit = "\n⏸️ **Scanning is paused** — use `!resume` or the admin UI to resume." if is_scan_paused() else ""
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
    paused = is_scan_paused()
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
    if is_scan_paused():
        await ctx.send("⏸️ Scanning is already paused.")
        return
    set_scan_paused(True)
    log.info("Automatic scanning paused via !pause (by %s).", ctx.author)
    await _refresh_presence()
    await ctx.send(
        "⏸️ **Automatic scanning paused.** The bot will stop posting scheduled alerts. "
        "`!check` still works on demand. Use `!resume` or the admin UI to turn it back on."
    )


@bot.command(name="resume")
async def resume_cmd(ctx):
    """Resume the automatic background scan loop after a !pause."""
    if not is_scan_paused():
        await ctx.send("▶️ Scanning is already running.")
        return
    set_scan_paused(False)
    log.info("Automatic scanning resumed via !resume (by %s).", ctx.author)
    await _refresh_presence()
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
