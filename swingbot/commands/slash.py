"""
Slash-command (/command) equivalents for key bot commands.

Discord shows these natively when the user types '/' — each parameter
has a description and, where applicable, a dropdown of valid choices.

These wrap the same business logic as the prefix (!) commands; they
don't replace them. Both work in parallel.

Registered via bot.tree; synced to Discord in on_ready (scanning.py).
"""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from swingbot.bot_core import bot, COMMANDS_BY_CATEGORY, CONFIDENCE_EXPLAINER
from swingbot import config
from swingbot.core.strategy import HORIZONS
from swingbot.core.watchlist import load_watchlist
from swingbot.core import scan_engine

# ──────────────────────────────────────────────
# Choice lists
# ──────────────────────────────────────────────

HORIZON_CHOICES = [app_commands.Choice(name=k, value=k) for k in HORIZONS] + [
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
TIER_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("All", "A", "B", "C")]
PERIOD_CHOICES = [app_commands.Choice(name=v, value=v) for v in ("7d", "30d", "90d", "ytd", "all")]


# ──────────────────────────────────────────────
# Helper — send long text in chunks
# ──────────────────────────────────────────────

async def _send_chunks(interaction: discord.Interaction, text: str, ephemeral: bool = False) -> None:
    """Send a response (possibly long) respecting the 2000-char limit."""
    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
    await interaction.response.send_message(chunks[0], ephemeral=ephemeral)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=ephemeral)


# ──────────────────────────────────────────────
# /ping
# ──────────────────────────────────────────────

@bot.tree.command(name="ping", description="Check bot latency")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🏓 Pong! {round(bot.latency * 1000)}ms", ephemeral=True
    )


# ──────────────────────────────────────────────
# /help
# ──────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Swing Trade Bot — Commands",
        description="Alerts only, never places trades. Prefix: `!`  •  Slash: `/`",
        color=discord.Color.blurple(),
    )
    for category, cmds in COMMANDS_BY_CATEGORY.items():
        value = "\n".join(f"`{cmd}` — {desc}" for cmd, desc in cmds)
        embed.add_field(name=category, value=value, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
# /confidence
# ──────────────────────────────────────────────

@bot.tree.command(name="confidence", description="Explain the 5 confidence levels")
async def slash_confidence(interaction: discord.Interaction):
    await interaction.response.send_message(CONFIDENCE_EXPLAINER, ephemeral=True)


# ──────────────────────────────────────────────
# /strategies
# ──────────────────────────────────────────────

@bot.tree.command(name="strategies", description="List available strategies and swing horizons")
async def slash_strategies(interaction: discord.Interaction):
    lines = [
        "**Strategies:** EMA Crossover, VWAP, Fibonacci retracement, Support/Resistance breakout, "
        "RSI mean-reversion, MACD, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile",
        "", "**Swing horizons:**",
    ]
    for key, h in HORIZONS.items():
        lines.append(f"`{key}` — {h['label']}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ──────────────────────────────────────────────
# /regime
# ──────────────────────────────────────────────

@bot.tree.command(name="regime", description="Show current broad market regime (SPY trend)")
async def slash_regime(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    regime = await asyncio.to_thread(scan_engine.get_regime)
    if regime is None:
        await interaction.followup.send("Could not fetch market regime right now.", ephemeral=True)
        return
    await interaction.followup.send(
        f"**Market regime:** {regime.label}\n"
        f"{regime.ticker} close: {regime.close} | 200EMA: {regime.ema200} "
        f"({regime.pct_above_ema:+.1f}%) | 200EMA slope (20d): {regime.ema_slope_pct:+.2f}%\n\n"
        f"This feeds into confidence scoring (+10 pts when a signal agrees with the regime).",
        ephemeral=True,
    )


# ──────────────────────────────────────────────
# /pnl
# ──────────────────────────────────────────────

@bot.tree.command(name="pnl", description="Current unrealized P&L for every open trade")
async def slash_pnl(interaction: discord.Interaction):
    await interaction.response.defer()
    # Delegate to the prefix command by posting it in the channel
    # (slash and prefix share no ctx; easiest bridge is to re-use the engine directly)
    from swingbot.core.scan_engine import get_all_unrealized_pnl
    rows = await asyncio.to_thread(get_all_unrealized_pnl)
    if not rows:
        await interaction.followup.send("No open trades right now.")
        return
    lines = ["**Open trade P&L** (live prices):"]
    for r in rows:
        lines.append(r)
    await _send_chunks(interaction, "\n".join(lines))


# ──────────────────────────────────────────────
# /liveplans
# ──────────────────────────────────────────────

@bot.tree.command(name="liveplans", description="Live v2 plan lifecycle board (PENDING/ACTIVE/PARTIAL)")
@app_commands.describe(status="Filter by lifecycle status", tier="Filter by quality tier")
@app_commands.choices(status=STATUS_CHOICES, tier=TIER_CHOICES)
async def slash_liveplans(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] = None,
    tier: app_commands.Choice[str] = None,
):
    args = []
    if status and status.value != "All":
        args.append(status.value.lower())
    if tier and tier.value != "All":
        args.append(f"tier:{tier.value.lower()}")

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
# /ticker
# ──────────────────────────────────────────────

@bot.tree.command(name="ticker", description="Full bias snapshot for a single stock across all strategies")
@app_commands.describe(ticker="Stock ticker symbol, e.g. AAPL")
async def slash_ticker(interaction: discord.Interaction, ticker: str):
    ticker = ticker.upper()
    await interaction.response.send_message(f"Pulling snapshot for **{ticker}**…")
    await interaction.channel.send(f"!ticker {ticker}")


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
    h_val = horizon.value if horizon else "all"
    s_val = strategy.value if strategy else "all"
    parts = [f"!backtest {ticker} {h_val} {s_val}"]
    if from_date:
        parts.append(f"from:{from_date}")
    if to_date:
        parts.append(f"to:{to_date}")
    if setups:
        parts.append("setups")
    cmd_str = " ".join(parts)
    await interaction.response.send_message(f"Running `{cmd_str}`…")
    await interaction.channel.send(cmd_str)


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
    h_val = horizon.value if horizon else "all"
    s_val = strategy.value if strategy else "all"
    parts = [f"!backtestwatchlist {h_val} {s_val}"]
    if from_date:
        parts.append(f"from:{from_date}")
    if to_date:
        parts.append(f"to:{to_date}")
    cmd_str = " ".join(parts)
    await interaction.response.send_message(f"Running `{cmd_str}`…")
    await interaction.channel.send(cmd_str)


# ──────────────────────────────────────────────
# /trades
# ──────────────────────────────────────────────

@bot.tree.command(name="trades", description="List logged trades with pagination")
@app_commands.describe(
    filter="Filter by trade status (default: all)",
    per_page="Trades per page (default: 10)",
)
@app_commands.choices(filter=TRADE_FILTER_CHOICES)
async def slash_trades(
    interaction: discord.Interaction,
    filter: app_commands.Choice[str] = None,
    per_page: int = 10,
):
    f_val = filter.value if filter else "all"
    await interaction.response.send_message(f"Fetching trades…")
    await interaction.channel.send(f"!trades {f_val} {per_page}")


# ──────────────────────────────────────────────
# /performance
# ──────────────────────────────────────────────

@bot.tree.command(name="performance", description="Win rate + risk-adjusted stats for closed trades")
@app_commands.describe(level="Filter to a specific confidence level (1-5), or omit for overall")
async def slash_performance(
    interaction: discord.Interaction,
    level: int = None,
):
    await interaction.response.send_message("Fetching performance stats…")
    await interaction.channel.send(f"!performance{' ' + str(level) if level else ''}")


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
    if act == "show":
        await interaction.response.send_message("Fetching watchlist…")
        await interaction.channel.send("!watchlist")
    elif act in ("add", "remove") and ticker:
        t = ticker.upper()
        await interaction.response.send_message(f"Running `!watchlist {act} {t}`…")
        await interaction.channel.send(f"!watchlist {act} {t}")
    elif act == "clear":
        await interaction.response.send_message("Running `!watchlist clear`…")
        await interaction.channel.send("!watchlist clear")
    else:
        await interaction.response.send_message(
            "Please provide a ticker for add/remove actions.", ephemeral=True
        )


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
# /lessons
# ──────────────────────────────────────────────

@bot.tree.command(name="lessons", description="Recent journal entries and their auto-generated lessons")
@app_commands.describe(arg="A number of entries, or 'week' for the weekly digest")
async def slash_lessons(interaction: discord.Interaction, arg: str = "5"):
    await interaction.response.defer()
    ctx = await commands.Context.from_interaction(interaction)
    from swingbot.commands.stats import lessons_cmd
    await lessons_cmd.callback(ctx, arg)
