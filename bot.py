"""
Swing Trade Alert Bot -- entry point.
======================================
Scans a watchlist of stocks/ETFs throughout the trading session across
five swing horizons (2 weeks, 4 weeks, 2 months, 3 months, 6 months --
capped at 6 months max). For each ticker/horizon, finds the next
support and resistance level using every method at once (EMA, VWAP,
Fibonacci, rolling structure, zigzag pivots -- see swingbot/core/levels.py)
and, if either is at least MIN_REWARD_PCT (default 5%) away from today's
price, builds a trade plan: LONG toward resistance, SHORT toward
support, with a second target beyond that and both the continuation and
reversal outcome described. Only Level 3+ confidence scenarios are
shown, with Level 4-5 (High/Very High) prioritized -- quality over
quantity. Near-identical scenarios on the same ticker are merged into
one alert. `!check` gives a full snapshot of every current qualifying
scenario, not just newly-flipped ones.

Alerts only -- no orders are ever placed. Not financial advice.

This file just wires everything together -- the actual implementation
lives under swingbot/:
  - swingbot/config.py            all settings
  - swingbot/bot_core.py           shared bot instance, session window, error handling
  - swingbot/core/scan_engine.py    the core scan/dedup/alert-building logic
  - swingbot/core/*.py              indicators, levels, strategies, trade plans, charts, etc.
  - swingbot/commands/*.py          Discord commands, grouped by area
  - swingbot/admin/app.py           the admin web UI (run via admin_ui.py)

Run `!commands` in Discord for the full command list.
"""
from swingbot import config
from swingbot.bot_core import bot, log

# Import each command module so its @bot.command()/@bot.group() decorators
# register on the shared bot instance. Order doesn't matter functionally,
# but commands.scanning defines on_ready/the scan loop so it's listed first.
from swingbot.commands import scanning   # noqa: F401
from swingbot.commands import watchlist  # noqa: F401
from swingbot.commands import info       # noqa: F401
from swingbot.commands import trades     # noqa: F401
from swingbot.commands import backtest   # noqa: F401
from swingbot.commands import account    # noqa: F401
from swingbot.commands import data       # noqa: F401
from swingbot.commands import slash      # noqa: F401  — slash (/) command equivalents
from swingbot.commands import history    # noqa: F401  — !plans command

if __name__ == "__main__":
    config.log_startup_config()
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Create a .env file (see README.md).")
    try:
        bot.run(config.TOKEN, log_handler=None)
    except Exception as exc:
        log.critical("bot.run() failed — bot did not start: %s", exc, exc_info=True)
        raise
