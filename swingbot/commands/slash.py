"""
Slash-command (/command) equivalents for key bot commands.

Discord shows these natively when the user types '/' — each parameter
has a description and, where applicable, a dropdown of valid choices.

These wrap the same business logic as the prefix (!) commands; they
don't replace them. Both work in parallel.

Registered via bot.tree; synced to Discord in on_ready (scanning.py).
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from swingbot.bot_core import bot
from swingbot.core.market.strategy import live_horizons
from swingbot.core.scanning import engine as scan_engine

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Choice lists
# ──────────────────────────────────────────────

HORIZON_CHOICES = [app_commands.Choice(name=k, value=k) for k in live_horizons()] + [
    app_commands.Choice(name="all", value="all")
]

STRATEGY_CHOICES = [
    app_commands.Choice(name="All strategies",    value="all"),
    app_commands.Choice(name="EMA Crossover",     value="ema"),
    app_commands.Choice(name="VWAP",              value="vwap"),
    app_commands.Choice(name="Fibonacci",         value="fib"),
    app_commands.Choice(name="Support/Resistance",value="sr"),
    app_commands.Choice(name="RSI",               value="rsi"),
    app_commands.Choice(name="MACD",              value="macd"),
    app_commands.Choice(name="Elliott Wave",      value="elliott"),
    app_commands.Choice(name="MA Ribbon",         value="ribbon"),
    app_commands.Choice(name="Break & Retest",    value="bnr"),
    app_commands.Choice(name="RSI Divergence",    value="rsidiv"),
    app_commands.Choice(name="Volume Profile",    value="volprofile"),
]

TRADE_FILTER_CHOICES = [
    app_commands.Choice(name="All",  value="all"),
    app_commands.Choice(name="Open", value="open"),
    app_commands.Choice(name="Win",  value="win"),
    app_commands.Choice(name="Loss", value="loss"),
]

STATUS_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")]
# v32 Task 11: tier (A/B/C) retired in favour of confidence level (1-5).
LEVEL_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "1", "2", "3", "4", "5")]
PERIOD_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("7d", "30d", "90d", "ytd", "all")]


# ──────────────────────────────────────────────
# App-command errors (v153 SP3)
# ──────────────────────────────────────────────

# Check failures get a one-line ephemeral answer, matching the prefix side's
# on_command_error (bot_core.py); anything else is logged and re-raised.
APP_CHECK_REPLIES: dict[type, str] = {
    app_commands.MissingPermissions: "🚫 You don't have permission to run that command.",
    app_commands.NoPrivateMessage: "This command only works in a server.",
}


def _check_reply(error: Exception) -> str | None:
    for kind, text in APP_CHECK_REPLIES.items():
        if isinstance(error, kind):
            return text
    return None


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError) -> None:
    text = _check_reply(error)
    if text is None:
        name = getattr(interaction.command, "qualified_name", "?")
        log.error("Unhandled slash command error in /%s: %s", name, error, exc_info=error)
        raise error
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


# ──────────────────────────────────────────────
# /liveplans
# ──────────────────────────────────────────────

@bot.tree.command(name="liveplans", description="Live v2 plan lifecycle board (PENDING/ACTIVE/PARTIAL)")
@app_commands.describe(status="Filter by lifecycle status", level="Filter by confidence level")
@app_commands.choices(status=STATUS_CHOICES, level=LEVEL_CHOICES)
async def slash_liveplans(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] = None,
    level: app_commands.Choice[str] = None,
):
    args = []
    if status and status.value != "All":
        args.append(status.value.lower())
    if level and level.value != "All":
        args.append(f"level:{level.value.lower()}")

    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.plans import liveplans_cmd
    await liveplans_cmd.callback(ctx, *args)


# ──────────────────────────────────────────────
# /check
# ──────────────────────────────────────────────

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
    """
    Runs the exact same underlying coroutine as the `!check` prefix
    command -- directly, not by faking a "!check ..." message in the
    channel like this used to. That old trick was silently broken: a
    message sent via `interaction.channel.send()` is authored BY THE BOT
    ITSELF, and discord.py's `commands.Bot.process_commands()`
    unconditionally ignores any message whose author is a bot
    (`if message.author.bot: return`, see discord.py's ext/commands/bot.py).
    So `/check` was posting a "!check all" line that looked like a
    command but was never actually parsed or run -- explaining why it
    appeared to do nothing (and why, with no horizon chosen, it always
    looked like it had specifically run "!check all" rather than the
    equivalent bare "!check").

    Fixed by building a real `Context` from the interaction (discord.py
    2.0+'s supported bridge, `Context.from_interaction`) and calling
    `check_cmd`'s own callback directly -- same code path, same live
    progress messages, same result, whether invoked via `!check` or
    `/check`.
    """
    args = []
    if horizon is not None:
        args.append(horizon.value)
    if min_strategies is not None:
        args.append(str(min_strategies))
    if from_date:
        args.append(f"from:{from_date}")
    if to_date:
        args.append(f"to:{to_date}")

    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.scanning import check_cmd
    await check_cmd.callback(ctx, *args)


# ──────────────────────────────────────────────
# /stop
# ──────────────────────────────────────────────

@bot.tree.command(name="stop", description="Stop whatever scan is currently running")
async def slash_stop(interaction: discord.Interaction):
    if not scan_engine.is_scan_running():
        await interaction.response.send_message("ℹ️ No scan is currently running.", ephemeral=True)
        return
    scan_engine.request_stop()
    await interaction.response.send_message(
        "🛑 **Stop requested** — the running scan will end after finishing its current ticker."
    )


# ──────────────────────────────────────────────
# /backtest
# ──────────────────────────────────────────────

@bot.tree.command(name="backtest", description="Backtest a ticker against historical data")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. AAPL",
    horizon="Swing horizon (default: all)",
    strategy="Strategy to test (default: all)",
    from_date="Start date YYYY-MM-DD (optional)",
    to_date="End date YYYY-MM-DD (optional)",
    setups="List every individual trade setup instead of the summary table",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtest(
    interaction: discord.Interaction,
    ticker: str,
    horizon: app_commands.Choice[str] = None,
    strategy: app_commands.Choice[str] = None,
    from_date: str = None,
    to_date: str = None,
    setups: bool = False,
):
    ticker = ticker.upper()
    args = [ticker, horizon.value if horizon else "all", strategy.value if strategy else "all"]
    if from_date:
        args.append(f"from:{from_date}")
    if to_date:
        args.append(f"to:{to_date}")
    if setups:
        args.append("setups")
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.backtest import backtest_cmd
    await backtest_cmd.callback(ctx, *args)


# ──────────────────────────────────────────────
# /backtestwatchlist
# ──────────────────────────────────────────────

@bot.tree.command(name="backtestwatchlist", description="Backtest every watchlist ticker, ranked by expectancy")
@app_commands.describe(
    horizon="Swing horizon (default: all)",
    strategy="Strategy to test (default: all)",
    from_date="Start date YYYY-MM-DD (optional)",
    to_date="End date YYYY-MM-DD (optional)",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtestwatchlist(
    interaction: discord.Interaction,
    horizon: app_commands.Choice[str] = None,
    strategy: app_commands.Choice[str] = None,
    from_date: str = None,
    to_date: str = None,
):
    args = [horizon.value if horizon else "all", strategy.value if strategy else "all"]
    if from_date:
        args.append(f"from:{from_date}")
    if to_date:
        args.append(f"to:{to_date}")
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.backtest import backtestwatchlist_cmd
    await backtestwatchlist_cmd.callback(ctx, *args)


# ──────────────────────────────────────────────
# /watchlist
# ──────────────────────────────────────────────

@bot.tree.command(name="watchlist", description="Show, add, or remove tickers from the watchlist")
@app_commands.describe(
    action="Action to perform (leave blank to just show the list)",
    ticker="Ticker to add or remove",
)
@app_commands.choices(action=[
    app_commands.Choice(name="Show",   value="show"),
    app_commands.Choice(name="Add",    value="add"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Clear",  value="clear"),
])
async def slash_watchlist(
    interaction: discord.Interaction,
    action: app_commands.Choice[str] = None,
    ticker: str = None,
):
    act = action.value if action else "show"
    if act in ("add", "remove") and not ticker:
        await interaction.response.send_message("Please provide a ticker for add/remove actions.", ephemeral=True)
        return

    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.watchlist import watchlist_cmd, watchlist_add, watchlist_remove, watchlist_clear
    if act == "show":
        await watchlist_cmd.callback(ctx)
    elif act == "add":
        await watchlist_add.callback(ctx, ticker.upper())
    elif act == "remove":
        await watchlist_remove.callback(ctx, ticker.upper())
    elif act == "clear":
        await watchlist_clear.callback(ctx)


# ──────────────────────────────────────────────
# /top
# ──────────────────────────────────────────────

@bot.tree.command(name="top", description="Highest follow-score PENDING/ACTIVE plans")
@app_commands.describe(n="How many plans to show (default: config.DIGEST_MAX_PLANS)")
async def slash_top(interaction: discord.Interaction, n: int = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import top_cmd
    if n is not None:
        await top_cmd.callback(ctx, n)
    else:
        await top_cmd.callback(ctx)


# ──────────────────────────────────────────────
# /stats
# ──────────────────────────────────────────────

@bot.tree.command(name="stats", description="Win rate, expectancy, and risk-adjusted stats")
@app_commands.describe(period="Time window")
@app_commands.choices(period=PERIOD_CHOICES)
async def slash_stats(interaction: discord.Interaction, period: app_commands.Choice[str] = None):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import stats_cmd
    await stats_cmd.callback(ctx, period.value if period else "all")


# ──────────────────────────────────────────────
# /soak
# ──────────────────────────────────────────────

@bot.tree.command(name="soak", description="v93 trust-rule readout for a strategy's shadow plans")
@app_commands.describe(strategy="Exact strategy name, e.g. MACD")
async def slash_soak(interaction: discord.Interaction, strategy: str):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import soak_cmd
    await soak_cmd.callback(ctx, strategy=strategy)


# ──────────────────────────────────────────────
# /lessons
# ──────────────────────────────────────────────

@bot.tree.command(name="lessons", description="Recent journal entries and their auto-generated lessons")
@app_commands.describe(arg="A number of entries, or 'week' for the weekly digest")
async def slash_lessons(interaction: discord.Interaction, arg: str = "5"):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import lessons_cmd
    await lessons_cmd.callback(ctx, arg)
