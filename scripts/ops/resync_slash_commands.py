#!/usr/bin/env python3
"""Re-sync Discord's global slash-command set to THIS image's commands.

v153 rollback remedy. on_ready syncs once per process start
(swingbot/commands/scanning/loops.py:1047). A failed sync is only a WARNING
(:1048-1049) and is never retried in-process, so a rollback whose sync
failed leaves the newer image's commands registered against an image that
no longer handles them.

This script imports the command modules bot.py imports
(swingbot.commands.modules), logs in with the bot token over HTTP only (no
gateway: it never fires on_ready, never answers a command, and leaves the
running bot's session alone) and calls bot.tree.sync(), which bulk-overwrites
the global set with the running image's commands. Idempotent.

Run on production:
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/resync_slash_commands.py"
This script exists only in v153-or-later images, so it fixes a failed sync
on a v153 image (a roll-forward, or a restart that logged the WARNING). After a
rollback to a PRE-v153 image the container has neither it nor
swingbot/commands/modules.py: there the remedy is `docker compose restart bot`
(on_ready re-syncs on every start; docs/deploy/DEPLOY_HETZNER.md § Rolling back).

discord.py 2.7.1: Client.login() sets the application id tree.sync() needs;
tests/scripts/test_resync_slash_commands.py pins that.

Exit codes: 0 synced, 1 login or sync rejected, 2 DISCORD_TOKEN not set.
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


async def resync(bot, token: str) -> int:
    """Log in without the gateway, bulk-overwrite the global set, close. Returns the synced count."""
    async with bot:
        await bot.login(token)
        synced = await bot.tree.sync()
    return len(synced)


def main() -> int:
    import discord

    from swingbot import config
    from swingbot.bot_core import bot
    from swingbot.commands.modules import import_bot_command_modules

    if not config.TOKEN:
        print("DISCORD_TOKEN is not set; nothing synced.", file=sys.stderr)
        return 2
    loaded = import_bot_command_modules()
    try:
        count = asyncio.run(resync(bot, config.TOKEN))
    except (discord.LoginFailure, discord.HTTPException) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"Synced {count} slash command(s) to Discord from {len(loaded)} command modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
