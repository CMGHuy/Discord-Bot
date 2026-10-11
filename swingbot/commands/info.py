"""!strategies, !confidence, !regime, !ticker, !strategycharts, !commands/!help,
!ping, and their slash twins (v153).

Each body lives in one handle_<name>(reply, ...) handler. The prefix command
and the slash twin both call it through a Reply (swingbot/commands/reply.py),
so the two surfaces cannot drift.
"""
import asyncio
import logging
import os

import discord
from discord import app_commands

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.scanning import engine as scan_engine
from swingbot.bot_core import bot, CONFIDENCE_EXPLAINER, COMMANDS_BY_CATEGORY
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core.market.strategy import HORIZONS, MIN_BARS, evaluate_all, live_horizons
from swingbot.core.charts.trade_chart import generate_all_strategy_charts
from swingbot.commands.reply import SLASH_TWIN, CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES

log = logging.getLogger(__name__)

#: The help embed's description; SP17's help_embeds() reuses it.
HELP_DESCRIPTION = "Alerts only, never places trades. Prefix: `!`  •  Slash: `/`"

HELP_TITLE = "📖 Swing Trade Bot — Commands"
CONT = " (cont.)"

# Discord embed limits: a field value, the fields per embed, and the
# characters per embed (title + description + field names/values + footer).
FIELD_VALUE_LIMIT = 1024
EMBED_FIELD_LIMIT = 25
EMBED_TOTAL_LIMIT = 6000

STRATEGY_NAMES = (
    "EMA Crossover, VWAP, Fibonacci retracement, Support/Resistance breakout, "
    "RSI mean-reversion, MACD, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile"
)

#: !ticker splits its snapshot on a newline at or before this many chars.
TICKER_MESSAGE_LIMIT = 1990

# /strategycharts draws one horizon; "all" is a scan choice, not a chart horizon.
CHART_HORIZON_CHOICES = [choice for choice in HORIZON_CHOICES if choice.value != "all"]
DIRECTION_CHOICES = [
    app_commands.Choice(name="bullish", value="bullish"),
    app_commands.Choice(name="bearish", value="bearish"),
]


def format_signal_plan_line(plan) -> str:
    """Compact !ticker plan line: 'MACD 4w ✅ 81.3% | entry 101.20 stop
    99.10 tp1 101.94 tp2 104.00' (tp2 clause omitted when there's no TP2)."""
    badge_mark = "✅" if plan.badge == "VALIDATED" else "⚠️"
    wr = (plan.badge_stats or {}).get("win_rate", 0.0)
    line = (f"{plan.strategy} {plan.horizon_key} {badge_mark} {wr:.1f}% | "
           f"entry {plan.trigger_price:.2f} stop {plan.stop_loss:.2f} "
           f"tp1 {plan.tp1:.2f}")
    if plan.tp2 is not None:
        line += f" tp2 {plan.tp2:.2f}"
    return line


def _sync_ticker_snapshot(ticker: str):
    """All the blocking work for !ticker (network fetch, indicator computation) in one place, run via to_thread."""
    df = get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
    results = evaluate_all(ticker, df)
    regime = scan_engine.get_regime()
    return df, results, regime


def _ticker_table_lines(ticker: str, df, results, regime) -> list[str]:
    last_close = float(df["Close"].iloc[-1])
    last_vol = int(df["Volume"].iloc[-1])

    lines = [f"**{ticker}** snapshot — close {last_close:.2f}, volume {last_vol:,}"]
    if regime:
        lines.append(f"Market regime: {regime.label}")
    lines.append("```")
    lines.append(f"{'Strategy':18s} {'Horiz':5s} {'Bias':8s} {'Fresh today':>11s}")
    for r in results:
        fresh = "YES" if r.triggered else ""
        lines.append(f"{r.strategy:18s} {r.horizon_key:5s} {r.trend:8s} {fresh:>11s}")
    lines.append("```")
    lines.append(
        "'Fresh today' = the signal crossed on today's candle. Only Level "
        f"{config.MIN_ALERT_CONFIDENCE_LEVEL}+ confidence signals become alerts via `!check`; "
        "everything is shown here regardless of confidence."
    )
    return lines


def _signal_plan(df, ticker: str, r):
    from swingbot.core.planning.plan_engine import build_strategy_plan
    try:
        return build_strategy_plan(df, len(df) - 1, ticker=ticker,
                                   strategy=r.strategy, horizon_key=r.horizon_key,
                                   direction=r.trend)
    except Exception:
        return None


def _ticker_plan_lines(ticker: str, df, results) -> list[str]:
    plan_lines = []
    for r in results:
        if not r.triggered:
            continue
        plan = _signal_plan(df, ticker, r)
        if plan is not None:
            plan_lines.append(format_signal_plan_line(plan))
    if plan_lines:
        return ["**Trade plans (v2)**", *plan_lines]
    if any(r.triggered for r in results):
        return [
            f"**Trade plans (v2)** — no qualifying setup: no level beyond entry "
            f"pays {config.MIN_RISK_REWARD_RATIO:.1f}:1 against its own stop."]
    return []


def _message_parts(msg: str, limit: int = TICKER_MESSAGE_LIMIT) -> list[str]:
    """Split on the last newline at or before `limit`; a whitespace-only tail is dropped."""
    parts = []
    while len(msg) > limit:
        split_at = msg.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(msg[:split_at])
        msg = msg[split_at:]
    if msg.strip():
        parts.append(msg)
    return parts


def _sync_strategy_charts(ticker: str, df, direction: str, h: dict, currency_symbol: str):
    """All the blocking work for !strategycharts (chart rendering for every strategy) in one place, run via to_thread."""
    return generate_all_strategy_charts(
        ticker, df, direction, h["label"], config.TRADE_CHART_DIR, h,
        currency_symbol=currency_symbol, filename_prefix=f"{ticker}_strategy",
    )


def _strategycharts_problem(horizon: str, direction: str) -> str | None:
    if horizon not in live_horizons():
        return f"Unknown horizon '{horizon}'. Use one of: {', '.join(live_horizons())}"
    if direction not in ("bullish", "bearish"):
        return "Direction must be 'bullish' or 'bearish'."
    return None


def help_line(usage: str, desc: str) -> str:
    """One help row: the `!` form first, then its slash twin (v153).

    The twin comes only from SLASH_TWIN, for the longest key equal to the
    usage's leading words: `!trades clear` -> `trades clear` -> `/trades-clear`,
    `!trade ID` -> `trade` -> `/trade show`."""
    words = usage.lstrip("!").split()
    for n in range(len(words), 0, -1):
        twin = SLASH_TWIN.get(" ".join(words[:n]))
        if twin is not None:
            return f"`{usage}` · `/{twin}` — {desc}"
    return f"`{usage}` — {desc}"


def _clip(line: str, limit: int) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _field_chunks(lines: list[str], limit: int = FIELD_VALUE_LIMIT) -> list[str]:
    """Join rows into field values of at most `limit` chars, breaking only between rows."""
    chunks: list[str] = []
    current = ""
    for line in (_clip(raw, limit) for raw in lines):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            candidate = line
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def help_fields() -> list[tuple[str, str]]:
    """(name, value) per field; an oversized category continues as '<category> (cont.)'."""
    fields: list[tuple[str, str]] = []
    for category, rows in COMMANDS_BY_CATEGORY.items():
        chunks = _field_chunks([help_line(usage, desc) for usage, desc in rows])
        fields.extend((category if i == 0 else category + CONT, value) for i, value in enumerate(chunks))
    return fields


def _new_help_embed(first: bool) -> discord.Embed:
    if first:
        embed = discord.Embed(title=HELP_TITLE, description=HELP_DESCRIPTION)
    else:
        embed = discord.Embed(title=HELP_TITLE + CONT)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"))
    return embed


def _fits(embed: discord.Embed, name: str, value: str) -> bool:
    return (len(embed.fields) < EMBED_FIELD_LIMIT
            and len(embed) + len(name) + len(value) <= EMBED_TOTAL_LIMIT)


def help_embeds() -> list[discord.Embed]:
    """The help catalog as embeds within Discord's limits (chrome applied first,
    so len(embed) already counts the footer)."""
    embeds = [_new_help_embed(first=True)]
    for name, value in help_fields():
        if not _fits(embeds[-1], name, value):
            embeds.append(_new_help_embed(first=False))
        embeds[-1].add_field(name=name, value=value, inline=False)
    return embeds


# ──────────────────────────────────────────────
# Handlers (one body per command, shared by ! and /)
# ──────────────────────────────────────────────

async def handle_strategies(reply) -> None:
    lines = [f"**Strategies:** {STRATEGY_NAMES}", "", "**Swing horizons:**"]
    for key in live_horizons():
        h = HORIZONS[key]
        lines.append(f"`{key}` — {h['label']} (needs {MIN_BARS[key]}+ trading days of history)")
    await reply.send("\n".join(lines), ephemeral=True)


async def handle_confidence(reply) -> None:
    await reply.send(CONFIDENCE_EXPLAINER, ephemeral=True)


async def handle_ticker(reply, ticker: str) -> None:
    """Full current-state snapshot for one ticker, independent of alert confirmation or confidence filter."""
    ticker = ticker.upper()
    await reply.send(f"Pulling a full snapshot for {ticker}…")
    try:
        df, results, regime = await asyncio.to_thread(_sync_ticker_snapshot, ticker)
    except Exception as e:
        log.warning("!ticker %s: could not fetch data", ticker, exc_info=True)
        await reply.send_error(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
    lines = _ticker_table_lines(ticker, df, results, regime) + _ticker_plan_lines(ticker, df, results)
    for part in _message_parts("\n".join(lines)):
        await reply.send(part)


async def handle_strategycharts(reply, ticker: str, horizon: str = "4w", direction: str = "bullish") -> None:
    """
    Generates one standalone chart per supported strategy (EMA, VWAP,
    Fibonacci, FVG, Bollinger, Donchian, Rolling S/R, Floor Pivot,
    Zigzag Pivot, Trendline) for one ticker -- what EACH strategy says
    on its OWN, not the merged multi-strategy consensus level !check
    alerts show. A diagnostic/exploration tool: it does NOT apply the
    usual reward/stop/risk-reward/confidence/confluence filters, so a
    chart showing up here doesn't mean it would ever qualify as a real
    alert.
    """
    ticker, horizon, direction = ticker.upper(), horizon.lower(), direction.lower()
    problem = _strategycharts_problem(horizon, direction)
    if problem:
        await reply.send_error(problem)
        return

    h = HORIZONS[horizon]
    await reply.send(f"Simulating every supported strategy for {ticker} ({h['label']}, {direction})…")
    try:
        df = await asyncio.to_thread(get_daily_data, ticker, config.DEFAULT_HISTORY_PERIOD)
    except Exception as e:
        log.warning("!strategycharts %s: could not fetch data", ticker, exc_info=True)
        await reply.send_error(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
    if len(df) < MIN_BARS.get(horizon, 0):
        await reply.send_error(
            f"Not enough history for {ticker} at this horizon ({len(df)} bars, needs {MIN_BARS[horizon]}+).")
        return

    currency_symbol = get_currency_symbol(ticker, config.CURRENCY_SYMBOL)
    paths = await asyncio.to_thread(_sync_strategy_charts, ticker, df, direction, h, currency_symbol)
    if not paths:
        await reply.send(f"No strategy currently has a usable {direction} level for {ticker} at this horizon.")
        return

    await reply.send(
        f"**{len(paths)} strategy chart(s) for {ticker}** ({h['label']}, {direction}) -- each shows what THAT ONE "
        "strategy alone thinks the next level is; none of `!check`'s usual filters are applied here."
    )
    for family, path in paths.items():
        await reply.send(f"**{family}**", file=discord.File(path, filename=os.path.basename(path)))


async def handle_regime(reply) -> None:
    await reply.defer(ephemeral=True)
    regime = await asyncio.to_thread(scan_engine.get_regime)
    if regime is None:
        await reply.send_error("Could not fetch market regime right now.")
        return
    await reply.send(
        f"**Market regime:** {regime.label}\n"
        f"{regime.ticker} close: {regime.close} | 200EMA: {regime.ema200} "
        f"({regime.pct_above_ema:+.1f}%) | 200EMA slope (20d): {regime.ema_slope_pct:+.2f}%\n\n"
        f"This feeds into confidence scoring (+10 pts when a signal agrees with the regime).",
        ephemeral=True,
    )


async def handle_ping(reply) -> None:
    await reply.send(f"🏓 Pong! {round(bot.latency * 1000)}ms", ephemeral=True)


async def handle_help(reply) -> None:
    for embed in help_embeds():
        await reply.send(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.command(name="strategies")
async def strategies_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_strategies(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="confidence")
async def confidence_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_confidence(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="ticker")
async def ticker_cmd(ctx, ticker: str):
    """Full current-state snapshot for one ticker, independent of alert confirmation or confidence filter."""
    reply = CtxReply(ctx)
    await handle_ticker(reply, ticker)
    await send_prefix_tip(ctx, reply)


@bot.command(name="strategycharts")
async def strategycharts_cmd(ctx, ticker: str, horizon: str = "4w", direction: str = "bullish"):
    """One standalone chart per strategy for one ticker (diagnostic; no alert filters)."""
    reply = CtxReply(ctx)
    await handle_strategycharts(reply, ticker, horizon, direction)
    await send_prefix_tip(ctx, reply)


@bot.command(name="regime")
async def regime_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_regime(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="ping")
async def ping_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_ping(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="commands", aliases=["help"])
async def commands_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_help(reply)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (moved from slash.py in v153, decorators verbatim;
# /strategycharts is new)
# ──────────────────────────────────────────────

@bot.tree.command(name="ping", description="Check bot latency")
async def slash_ping(interaction: discord.Interaction):
    await handle_ping(InteractionReply(interaction))


@bot.tree.command(name="help", description="Show all available commands")
async def slash_help(interaction: discord.Interaction):
    await handle_help(InteractionReply(interaction))


@bot.tree.command(name="confidence", description="Explain the 5 confidence levels")
async def slash_confidence(interaction: discord.Interaction):
    await handle_confidence(InteractionReply(interaction))


@bot.tree.command(name="strategies", description="List available strategies and swing horizons")
async def slash_strategies(interaction: discord.Interaction):
    await handle_strategies(InteractionReply(interaction))


@bot.tree.command(name="regime", description="Show current broad market regime (SPY trend)")
async def slash_regime(interaction: discord.Interaction):
    await handle_regime(InteractionReply(interaction))


@bot.tree.command(name="ticker", description="Full bias snapshot for a single stock across all strategies")
@app_commands.describe(ticker="Stock ticker symbol, e.g. AAPL")
async def slash_ticker(interaction: discord.Interaction, ticker: str):
    await handle_ticker(InteractionReply(interaction), ticker)


@bot.tree.command(name="strategycharts",
                  description="One chart per strategy for a ticker (diagnostic, no alert filters)")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. AAPL",
    horizon="Swing horizon (default: 4w)",
    direction="Trade direction (default: bullish)",
)
@app_commands.choices(horizon=CHART_HORIZON_CHOICES, direction=DIRECTION_CHOICES)
async def slash_strategycharts(
    interaction: discord.Interaction,
    ticker: str,
    horizon: app_commands.Choice[str] = None,
    direction: app_commands.Choice[str] = None,
):
    await handle_strategycharts(
        InteractionReply(interaction), ticker,
        horizon.value if horizon else "4w",
        direction.value if direction else "bullish",
    )
