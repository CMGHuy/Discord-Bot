"""Per-user /notify settings for factual paper plan updates (v152)."""
import asyncio
import logging

import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands.reply import InteractionReply
from swingbot.commands.scanning.follow_notify import (
    EVENT_LABELS, FOLLOWING_ONLY, NOTIFY_EVENTS, mentions_user,
)

log = logging.getLogger(__name__)
SLASH_ONLY = {"notify"}

WATCH_MODES = ("mention", "silent")
NOTIFY_EVENT_CHOICES = [app_commands.Choice(name=n, value=n) for n in (*NOTIFY_EVENTS, "all")]
WATCH_MODE_CHOICES = [app_commands.Choice(name=m, value=m) for m in WATCH_MODES]


_ON_OFF = {True: "on", False: "off"}
NOTIFY_PAIRING = ("Pass `event:` and `enabled:` together to change one update. "
                  "Nothing was changed.")
NOTIFY_STORE_DOWN = "Could not read or save your notify settings right now. Try again shortly."


def _notify_line(event: str, prefs: dict) -> str:
    following = _ON_OFF[mentions_user(frozenset({"taken"}), event, prefs)]
    watch = ("never" if event in FOLLOWING_ONLY
             else _ON_OFF[mentions_user(frozenset({"watch"}), event, prefs)])
    return f"• `{event}` — {EVENT_LABELS[event]}. Following: {following} · Watch: {watch}"


def _notify_summary(prefs: dict) -> str:
    """Which events the notify channel announces, and when it mentions the caller."""
    mode = prefs.get("watch_mode") if prefs.get("watch_mode") in WATCH_MODES else "mention"
    return "\n".join([
        "**The notify channel posts these paper plan updates** (facts, not advice):",
        *(_notify_line(event, prefs) for event in NOTIFY_EVENTS),
        f"Watch-only plans: {mode}.",
        "`closed_other` posts only when a plan has a Following follower, and mentions only them. "
        "Your settings decide whether you are mentioned, never whether a message posts.",
        "Change: `/notify event:<name|all> enabled:<true|false>` · `/notify watch_mode:<mention|silent>`",
    ])


def _apply_notify_change(user_id: int, event: str | None, enabled: bool | None,
                         watch_mode: str | None) -> dict:
    """Store the caller's change (sync; run in a thread) and return their prefs."""
    from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
    repo = notify_prefs_repo()
    if event is not None and enabled is not None:
        for name in (NOTIFY_EVENTS if event == "all" else (event,)):
            repo.set_pref(user_id, name, bool(enabled))
    if watch_mode is not None:
        repo.set_pref(user_id, "watch_mode", watch_mode)
    return repo.prefs(user_id)


async def handle_notify(reply, event: str | None = None,
                        enabled: bool | None = None, watch_mode: str | None = None) -> None:
    """Read or update the caller's mention preferences, then answer ephemerally."""
    if (event is None) != (enabled is None):
        await reply.send(NOTIFY_PAIRING, ephemeral=True)
        return
    try:
        prefs = await asyncio.to_thread(_apply_notify_change, reply.author.id,
                                        event, enabled, watch_mode)
    except Exception:
        log.warning("/notify: could not read or save prefs for user %s",
                    reply.author.id, exc_info=True)
        await reply.send(NOTIFY_STORE_DOWN, ephemeral=True)
        return
    await reply.send(_notify_summary(prefs), ephemeral=True)


@bot.tree.command(name="notify", description="Choose which paper plan updates mention you in the notify channel")
@app_commands.describe(event="The update to change, or all",
                       enabled="Mention me for it (true) or not (false)",
                       watch_mode="On plans I only Watch: mention me, or stay silent")
@app_commands.choices(event=NOTIFY_EVENT_CHOICES, watch_mode=WATCH_MODE_CHOICES)
async def slash_notify(interaction: discord.Interaction, event: app_commands.Choice[str] = None,
                       enabled: bool = None, watch_mode: app_commands.Choice[str] = None):
    await handle_notify(InteractionReply(interaction), event.value if event else None,
                        enabled, watch_mode.value if watch_mode else None)
