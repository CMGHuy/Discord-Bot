import datetime as dt
import random

import discord

from swingbot import config
from swingbot.bot_core import SESSION_TZ, bot, in_session, log
from swingbot.core.scanning import engine as scan_engine
from . import alerts, runstate

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

_session_was_active: bool | None = None
_healthcheck_msgs: list = []
_healthcheck_hour_bucket: tuple | None = None
trade_log = scan_engine.trade_log
_post_daily_digest = alerts._post_daily_digest

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
    if runstate.is_scan_paused():
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
        if runstate.is_scan_paused():
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

    if not active and config.DAILY_DIGEST_ENABLED:
        try:
            await _post_daily_digest(channel)
        except Exception as e:
            log.warning("Could not post daily top-plans digest: %s", e)

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
