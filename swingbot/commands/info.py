"""!strategies, !confidence, !regime, !ticker, !strategycharts, !commands/!help, !ping."""
import asyncio
import os

import discord

from swingbot import config
from swingbot.core import scan_engine
from swingbot.bot_core import bot, CONFIDENCE_EXPLAINER, COMMANDS_BY_CATEGORY
from swingbot.core.data import get_currency_symbol, get_daily_data
from swingbot.core.strategy import HORIZONS, MIN_BARS, evaluate_all
from swingbot.core.charts.trade_chart import generate_all_strategy_charts


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


@bot.command(name="strategies")
async def strategies_cmd(ctx):
    lines = [
        "**Strategies:** EMA Crossover, VWAP, Fibonacci retracement, Support/Resistance breakout, "
        "RSI mean-reversion, Elliott Wave (simplified)",
        "", "**Swing horizons:**",
    ]
    for key, h in HORIZONS.items():
        lines.append(f"`{key}` — {h['label']} (needs {MIN_BARS[key]}+ trading days of history)")
    await ctx.send("\n".join(lines))


@bot.command(name="confidence")
async def confidence_cmd(ctx):
    await ctx.send(CONFIDENCE_EXPLAINER)


@bot.command(name="ticker")
async def ticker_cmd(ctx, ticker: str):
    """Full current-state snapshot for one ticker, independent of alert confirmation or confidence filter."""
    ticker = ticker.upper()
    await ctx.send(f"Pulling a full snapshot for {ticker}…")
    try:
        df, results, regime = await asyncio.to_thread(_sync_ticker_snapshot, ticker)
    except Exception as e:
        await ctx.send(f"⚠️ Could not fetch data for {ticker}: {e}")
        return

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

    plan_lines = []
    for r in results:
        if not r.triggered:
            continue
        from swingbot.core.plan_engine import build_strategy_plan
        try:
            plan = build_strategy_plan(df, len(df) - 1, ticker=ticker,
                                       strategy=r.strategy, horizon_key=r.horizon_key,
                                       direction=r.trend)
        except Exception:
            plan = None
        if plan is not None:
            plan_lines.append(format_signal_plan_line(plan))
    if plan_lines:
        lines.append("**Trade plans**")
        lines.extend(plan_lines)

    msg = "\n".join(lines)
    while len(msg) > 1990:
        split_at = msg.rfind("\n", 0, 1990)
        if split_at == -1:
            split_at = 1990
        await ctx.send(msg[:split_at])
        msg = msg[split_at:]
    if msg.strip():
        await ctx.send(msg)


def _sync_strategy_charts(ticker: str, df, direction: str, h: dict, currency_symbol: str):
    """All the blocking work for !strategycharts (chart rendering for every strategy) in one place, run via to_thread."""
    return generate_all_strategy_charts(
        ticker, df, direction, h["label"], config.TRADE_CHART_DIR, h,
        currency_symbol=currency_symbol, filename_prefix=f"{ticker}_strategy",
    )


@bot.command(name="strategycharts")
async def strategycharts_cmd(ctx, ticker: str, horizon: str = "4w", direction: str = "bullish"):
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
    ticker = ticker.upper()
    horizon = horizon.lower()
    direction = direction.lower()
    if horizon not in HORIZONS:
        await ctx.send(f"Unknown horizon '{horizon}'. Use one of: {', '.join(HORIZONS.keys())}")
        return
    if direction not in ("bullish", "bearish"):
        await ctx.send("Direction must be 'bullish' or 'bearish'.")
        return

    h = HORIZONS[horizon]
    await ctx.send(f"Simulating every supported strategy for {ticker} ({h['label']}, {direction})…")
    try:
        df = await asyncio.to_thread(get_daily_data, ticker, config.DEFAULT_HISTORY_PERIOD)
    except Exception as e:
        await ctx.send(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
    if len(df) < MIN_BARS.get(horizon, 0):
        await ctx.send(f"Not enough history for {ticker} at this horizon ({len(df)} bars, needs {MIN_BARS[horizon]}+).")
        return

    currency_symbol = get_currency_symbol(ticker, config.CURRENCY_SYMBOL)
    paths = await asyncio.to_thread(_sync_strategy_charts, ticker, df, direction, h, currency_symbol)
    if not paths:
        await ctx.send(f"No strategy currently has a usable {direction} level for {ticker} at this horizon.")
        return

    await ctx.send(
        f"**{len(paths)} strategy chart(s) for {ticker}** ({h['label']}, {direction}) -- each shows what THAT ONE "
        "strategy alone thinks the next level is; none of `!check`'s usual filters are applied here."
    )
    for family, path in paths.items():
        await ctx.send(f"**{family}**", file=discord.File(path, filename=os.path.basename(path)))


@bot.command(name="regime")
async def regime_cmd(ctx):
    regime = await asyncio.to_thread(scan_engine.get_regime)
    if regime is None:
        await ctx.send("Could not fetch market regime right now.")
        return
    await ctx.send(
        f"**Market regime:** {regime.label}\n"
        f"{regime.ticker} close: {regime.close} | 200EMA: {regime.ema200} "
        f"({regime.pct_above_ema:+.1f}%) | 200EMA slope (20d): {regime.ema_slope_pct:+.2f}%\n\n"
        f"This feeds into confidence scoring (+10 pts when a signal agrees with the regime)."
    )


@bot.command(name="ping")
async def ping_cmd(ctx):
    await ctx.send(f"🏓 Pong! {round(bot.latency * 1000)}ms")


@bot.command(name="commands", aliases=["help"])
async def commands_cmd(ctx):
    embed = discord.Embed(
        title="📖 Swing Trade Bot — Commands",
        description="Alerts only, never places trades. Prefix: `!`",
        color=discord.Color.blurple(),
    )
    for category, cmds in COMMANDS_BY_CATEGORY.items():
        value = "\n".join(f"`{cmd}` — {desc}" for cmd, desc in cmds)
        embed.add_field(name=category, value=value, inline=False)
    await ctx.send(embed=embed)
