"""
Shared Discord bot instance and cross-cutting behavior (session window,
command-not-found suggestions, argument-error hints, config hot-reload).
Command modules (swingbot/commands/*.py) import `bot` from here and
register their commands on it.
"""
import asyncio
import datetime as dt
import difflib
import logging
import signal
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from swingbot import config

# Two handlers on the root logger: console (same as before -- `docker
# compose logs -f bot` keeps working exactly as it did) and a rotating
# file under logs/bot.log, which lives on the same bind-mounted project
# directory the admin container shares -- that's what powers the admin
# UI's live Logs page. 5MB x 3 backups is plenty for a bot that logs a
# few lines per scan; older history simply rolls off rather than
# growing forever.
_log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

_file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
_file_handler.setFormatter(_log_formatter)

_root_logger = logging.getLogger()
_root_logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
_root_logger.addHandler(_console_handler)
_root_logger.addHandler(_file_handler)

log = logging.getLogger("swing-bot")

SESSION_TZ = ZoneInfo("Europe/Berlin")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

CONFIDENCE_EXPLAINER = (
    "**Confidence level = how many DISTINCT strategies confirm the target (capped at 5), nudged by up to "
    "±1 for setup quality AND, independently, up to ±1 for whether the payoff actually makes sense "
    "(expectancy):**\n"
    "1. **Very Low** — only 1 strategy confirms the target\n"
    "2. **Low** — 2 strategies confirm (or 1 with excellent quality/expectancy)\n"
    "3. **Medium** — 3 strategies confirm (or 2 with excellent quality/expectancy, or 4 with poor)\n"
    "4. **High** — 4 strategies confirm (or 3 with excellent quality/expectancy, or 5+ with poor)\n"
    "5. **Very High** — 5+ strategies confirm (or 4 with excellent quality/expectancy)\n\n"
    "'Strategies' means DISTINCT ones (EMA, VWAP, Fibonacci, rolling structure, zigzag pivots, Bollinger "
    "Bands, Donchian Channel, floor pivots, trendlines, Fair Value Gaps -- 10 total) landing within "
    f"{config.CONFLUENCE_DEVIATION_PCT:.1f}% of the target price -- the exact same count and tolerance the "
    "'min strategies confirmed' setting uses, so the level and that setting always agree. 5 Fibonacci ratios "
    "clustering together only ever count as ONE strategy (Fibonacci), never five.\n\n"
    "**Two independent ±1 adjustments, each capped at one level:**\n"
    "• **Setup quality** (0-100) — target distance beyond the minimum move, stop-side confluence, market "
    "regime alignment, a Bollinger squeeze/volume breakout, and a confirming candlestick pattern. ≥70 → +1, "
    "≤30 → -1.\n"
    "• **Expectancy** — the real \"should I trade this\" metric: `win_rate × reward:risk − (1 − win_rate)`, "
    "in R-multiples, using THIS trade's own reward:risk and the *empirical* win rate of previously-closed "
    "trades that reached this same base level (`!performance` per level). A positive expectancy means that "
    "payoff/win-rate combination genuinely makes money over many trades; zero or negative means it doesn't, "
    "no matter how clean the setup looks technically. ≥+0.5R → +1, ≤0.0R → -1. Before there are "
    "5+ closed trades at a level, a neutral 50% win rate is assumed instead of real data, clearly labeled as "
    "such in the trade plan's breakdown.\n\n"
    "Quality and expectancy can each move the level by at most one step, and they act independently -- "
    "together they can shift a base level by up to ±2, but strategy count still anchors where you start, so "
    "the level always stays a reliable answer to \"how many methods agree, and does the math actually work\" "
    "rather than something either factor alone could inflate or deflate past recognition.\n\n"
    f"**`!check` only posts scenarios that meet every requirement**, same as the automatic background scan -- "
    f"below Level {config.MIN_ALERT_CONFIDENCE_LEVEL} confidence, or short on min reward %, stop distance, "
    "risk:reward, or min strategies confirmed, and it isn't posted at all. The only difference from the "
    "automatic scan is that `!check` skips the multi-scan confirmation debounce, since it's a one-off "
    "on-demand look rather than a repeating alert. Its scan summary still reports how many scenarios were "
    "found vs. fully qualifying, so \"why didn't X show up\" stays answerable without spamming the channel "
    "with a full alert for every non-qualifying scenario too.\n\n"
    "Score is a rule-based confluence check, **not a statistical win probability**. "
    "Use `!performance` to see the *actual* historical win rate AND risk-adjusted stats (Sharpe, Sortino, "
    "max drawdown, Calmar) measured per level from closed trades. Getting to a genuine high win rate requires "
    "that empirical validation -- the confidence score alone can't promise it."
)

COMMANDS_BY_CATEGORY = {
    "📡 Scanning": [
        ("!check [horizon] [min_strategies] [from:YYYY-MM-DD] [to:YYYY-MM-DD]",
         "Live scan (no dates) or historical review (with dates). horizon=2w|4w|2m|3m|4m|5m|6m|7m|8m|9m|all. "
         "With from:/to: shows trade plans already recorded in that window instead of running a new scan."),
        ("!session", "Show the session window and whether it's active right now"),
        ("!status", "Show watchlist size, session state, open positions"),
        ("!pause", "Pause the automatic background scan loop (manual !check/`/check` still work)"),
        ("!resume", "Resume the automatic background scan loop after a !pause"),
        ("!stop", "Stop whatever scan is currently running (!check, /check, admin UI trigger, or the automatic scan)"),
    ],
    "📋 Watchlist": [
        ("!watchlist", "Show current watchlist"),
        ("!watchlist add TICKER", "Add a ticker"),
        ("!watchlist remove TICKER", "Remove a ticker"),
        ("!watchlist clear", "Clear the entire watchlist"),
    ],
    "🧠 Strategy & market info": [
        ("!strategies", "List available strategies and swing horizons"),
        ("!confidence", "Explain the 5 confidence levels"),
        ("!regime", "Show current broad market regime"),
        ("!ticker TICKER", "Full snapshot: current bias for all strategy/horizon combos on one ticker"),
        ("!strategycharts TICKER [horizon] [bullish|bearish]", "One standalone chart per supported strategy (EMA, VWAP, Fibonacci, FVG, Bollinger, Donchian, Rolling S/R, Floor Pivot, Zigzag Pivot, Trendline) -- what each says on its own, no filters applied"),
    ],
    "📊 Trades & performance": [
        ("!trades [open|win|loss|all] [per_page]", "All logged trades (any confidence), sorted highest-confidence first, with Prev/Next pagination buttons. Default: all statuses, 10/page"),
        ("!trade ID", "Full detail on one logged trade, with its chart"),
        ("!trade delete ID", "Delete a single trade record"),
        ("!trades clear", "Delete ALL trade records"),
        ("!tradecharts [open|closed|all] [n]", "Chart images for multiple trades at once (max 10)"),
        ("!pnl", "Current unrealized profit/loss for every open trade, at today's price"),
        ("!performance [level]", "Win rate + risk-adjusted stats (Sharpe, Sortino, max drawdown, Calmar, profit factor), overall or per confidence level"),
        ("!summary", "Today's status at a glance: trades opened/closed, wins/losses, net gain/loss, and account balance movement today"),
        ("!plans TICKER [from:YYYY-MM-DD] [to:YYYY-MM-DD] [horizon] [strategy]",
         "Historical trade-plan lookup/generation for one ticker over a date range."),
        ("!liveplans [status] [tier:A|B|C] [badge:validated|weak] [TICKER]",
         "Live ranked plan board (PENDING/ACTIVE/PARTIAL), filterable and paginated via buttons. Filters compose: status/tier/badge/ticker."),
    ],
    "📐 Analytics": [
        ("!top [n]", "The n highest follow-score PENDING/ACTIVE plans right now (default: DIGEST_MAX_PLANS)"),
        ("!stats [7d|30d|90d|ytd|all]", "Win rate, expectancy, profit factor, Sharpe/Sortino, max drawdown, by-tier and by-strategy breakdowns"),
        ("!lessons [n|week]", "Last n journal entries with their auto-generated lesson, or `week` for the weekly digest"),
        ("!calibration", "Tier calibration vs. design bands, quality-score deciles, and edge-decay alerts"),
        ("!journal TRADE_ID your note", "Attach a manual note to a trade's journal entry; `!journal TICKER` lists that ticker's entries"),
    ],
    "🧪 Backtesting": [
        ("!backtest TICKER [horizon] [strategy] [from:DATE] [to:DATE] [setups]",
         "Backtest one ticker. Strategies: ema|vwap|fib|sr|rsi|macd|elliott|ribbon|bnr|rsidiv|volprofile|all. "
         "Add from:YYYY-MM-DD / to:YYYY-MM-DD to filter by date. Add 'setups' to list every individual trade."),
        ("!backtestwatchlist [horizon] [strategy] [from:DATE] [to:DATE]",
         "Backtest every watchlist ticker ranked by expectancy. Same options as !backtest."),
    ],
    "💰 Account & sizing": [
        ("!account", "Show account balance / sizing settings"),
        ("!account balance AMOUNT", "Set account balance"),
        ("!account sizing risk|account", "Risk % (fixed-fractional) or Account % (fixed allocation, e.g. 0.1% of a €1M account = €1,000/trade)"),
        ("!account positionpct PCT", "Set position size % of account per trade (used in 'account' sizing mode)"),
        ("!account risk PCT", "Set risk % per trade (used in 'risk' sizing mode)"),
        ("!account maxpositions N", "Set max concurrent open positions"),
    ],
    "💾 Data export & local cache": [
        ("!charts", "Download full daily historical data (CSV) + candlestick charts (PNG) for the watchlist"),
        ("!scrapeall [force]", "Bulk-scrape full ('all time') history for every watchlist ticker at once, concurrently, skipping ones already scraped today unless 'force' is given"),
        ("!download INTERVAL [TICKER]", "Cache intraday OHLCV data to disk (1m/2m/5m/15m/30m/60m). Omit TICKER for the whole watchlist"),
        ("!cached", "List what's currently cached on disk per ticker/interval"),
    ],
    "❓ Help": [
        ("!ping", "Check bot latency"),
        ("!commands", "Show this list"),
    ],
}

# Each entry: (usage_syntax, concrete_example)
COMMAND_USAGE = {
    # Scanning
    "check":               ("!check [horizon] [min_strategies] [from:YYYY-MM-DD] [to:YYYY-MM-DD]",
                            "!check 4w  or  !check all 2  or  !check from:2024-01-01 to:2024-12-31"),
    "session":             ("!session", "!session"),
    "status":              ("!status",  "!status"),
    # Watchlist
    "watchlist":           ("!watchlist", "!watchlist"),
    "watchlist add":       ("!watchlist add TICKER",    "!watchlist add AAPL"),
    "watchlist remove":    ("!watchlist remove TICKER", "!watchlist remove TSLA"),
    "watchlist clear":     ("!watchlist clear",         "!watchlist clear"),
    # Strategy & market info
    "strategies":          ("!strategies", "!strategies"),
    "confidence":          ("!confidence", "!confidence"),
    "regime":              ("!regime",     "!regime"),
    "ticker":              ("!ticker TICKER",
                            "!ticker AAPL"),
    "strategycharts":      ("!strategycharts TICKER [horizon] [bullish|bearish]",
                            "!strategycharts AAPL 4w bullish"),
    # Trades & performance
    "trades":              ("!trades [open|win|loss|all] [per_page]",
                            "!trades open  or  !trades all 5"),
    "trades clear":        ("!trades clear", "!trades clear"),
    "trade":               ("!trade ID",        "!trade 42"),
    "trade delete":        ("!trade delete ID", "!trade delete 42"),
    "tradecharts":         ("!tradecharts [open|closed|all] [n]",
                            "!tradecharts open 5"),
    "pnl":                 ("!pnl", "!pnl"),
    "performance":         ("!performance [level]",
                            "!performance  or  !performance 4"),
    "summary":             ("!summary", "!summary"),
    # Backtesting
    "backtest":            ("!backtest TICKER [horizon] [strategy] [from:YYYY-MM-DD] [to:YYYY-MM-DD] [setups]",
                            "!backtest AAPL 4w bnr from:2024-01-01 to:2024-12-31 setups"),
    "backtestwatchlist":   ("!backtestwatchlist [horizon] [strategy] [from:YYYY-MM-DD] [to:YYYY-MM-DD]",
                            "!backtestwatchlist 4w ribbon from:2024-01-01"),
    # Account
    "account":             ("!account", "!account"),
    "account balance":     ("!account balance AMOUNT", "!account balance 10000"),
    "account sizing":      ("!account sizing risk|account", "!account sizing account"),
    "account positionpct": ("!account positionpct PCT", "!account positionpct 0.1"),
    "account risk":        ("!account risk PCT",        "!account risk 1.5"),
    "account maxpositions":("!account maxpositions N",  "!account maxpositions 5"),
    # Data & cache
    "charts":              ("!charts", "!charts"),
    "scrapeall":           ("!scrapeall [force]", "!scrapeall  or  !scrapeall force"),
    "download":            ("!download INTERVAL [TICKER]",
                            "!download 5m AAPL  or  !download 15m"),
    "cached":              ("!cached", "!cached"),
    "plans":               ("!plans TICKER [from:YYYY-MM-DD] [to:YYYY-MM-DD] [horizon] [strategy]",
                            "!plans TSLA from:2024-01-01 to:2024-12-31  or  !plans AAPL 4w bnr"),
    "liveplans":           ("!liveplans [status] [tier:A|B|C] [badge:validated|weak] [TICKER]",
                            "!liveplans  or  !liveplans active tier:a NVDA"),
    # Analytics
    "top":                 ("!top [n]", "!top  or  !top 5"),
    "stats":               ("!stats [7d|30d|90d|ytd|all]", "!stats  or  !stats 30d"),
    "lessons":             ("!lessons [n|week]", "!lessons 10  or  !lessons week"),
    "calibration":         ("!calibration", "!calibration"),
    "journal":             ("!journal TRADE_ID your note here", "!journal T-42 watch the gap next time  or  !journal NVDA"),
    "ping":                ("!ping", "!ping"),
    "commands":            ("!commands", "!commands"),
}


def in_session(now: dt.datetime = None) -> bool:
    now = now or dt.datetime.now(SESSION_TZ)
    return config.SESSION_START_HOUR <= now.hour < config.SESSION_END_HOUR


_reload_handler_installed = False
_reload_callbacks = []


def on_config_reload(fn):
    """
    Registers a callback to run after every successful hot reload,
    called as fn(changed: dict). Use this for anything that captured a
    config value at definition/decoration time and needs to be told
    explicitly when that value changes -- e.g. `@tasks.loop(minutes=...)`
    bakes its interval in at decoration time, so commands/scanning.py
    uses this to call session_scan.change_interval() when
    SCAN_INTERVAL_MINUTES changes. Plain `config.X` reads elsewhere
    don't need this -- they see the new value automatically on their
    next read.
    """
    _reload_callbacks.append(fn)
    return fn


def _handle_reload_signal():
    """
    Runs on SIGHUP: re-reads .env and updates every config.* global in
    place, live, with no restart. This is what makes the admin UI's
    "Update settings" button an actual hot reload rather than "saved,
    please restart" -- see swingbot/config.py's docstring for exactly
    which settings this can and can't apply live.
    """
    try:
        changed = config.reload()
    except Exception:
        # config.reload() runs synchronously inside an asyncio signal-handler
        # callback -- an unhandled exception here (e.g. a transient I/O
        # error reading .env) would otherwise propagate straight into
        # asyncio's default callback-exception handling instead of this
        # module's own logging, and skip the reload callbacks below
        # entirely with no clear trace of why. Same defensive pattern as
        # the per-callback try/except a few lines down.
        log.exception("SIGHUP reload failed -- config left unchanged; fix the .env and try again")
        return
    if "LOG_LEVEL" in changed:
        new_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
        logging.getLogger().setLevel(new_level)
    for callback in _reload_callbacks:
        try:
            callback(changed)
        except Exception:
            log.exception("Reload callback %r failed", callback)
    if changed:
        log.info("SIGHUP reload complete -- %d setting(s) changed: %s", len(changed),
                 ", ".join(f"{k}={v[1]!r}" for k, v in changed.items()))
    else:
        log.info("SIGHUP reload complete -- no changes detected.")


def install_reload_signal_handler():
    """
    Registers the SIGHUP hot-reload handler on the running event loop.
    Call once, after the loop is running (e.g. from on_ready) --
    asyncio's add_signal_handler needs a running loop, and signal
    handlers registered via the plain `signal` module aren't safe to mix
    with asyncio. No-ops (and logs) on platforms without SIGHUP, e.g.
    Windows -- hot reload is a nice-to-have, not required for the bot to
    run; the "Restart bot container" button in the admin UI still works
    everywhere.
    """
    global _reload_handler_installed
    if _reload_handler_installed:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGHUP, _handle_reload_signal)
        _reload_handler_installed = True
        log.info("Hot-reload signal handler installed (SIGHUP).")
    except (NotImplementedError, AttributeError):
        log.info("SIGHUP hot-reload isn't available on this platform -- use the 'Restart bot container' "
                  "button (or `docker compose restart bot`) after changing settings instead.")


@bot.event
async def on_command(ctx):
    """Logs every command invocation -- who ran what, where. Cheap, and
    genuinely useful for after-the-fact debugging ("why did the bot do
    X" is usually answerable by "someone ran !Y at that time")."""
    channel_name = getattr(ctx.channel, "name", str(ctx.channel))
    log.info("Command '%s' invoked by %s in #%s", ctx.message.content, ctx.author, channel_name)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        attempted = ctx.message.content.split()[0].lstrip("!").lower()
        all_names = sorted({c.qualified_name for c in bot.walk_commands()})
        matches = difflib.get_close_matches(attempted, all_names, n=3, cutoff=0.4)
        suggestion = (" Did you mean: " + ", ".join(f"`!{m}`" for m in matches) + "?") if matches else ""
        await ctx.send(
            f"❓ Unknown command `!{attempted}`.{suggestion}\n"
            "Run `!commands` or `!help` to see all available commands."
        )
        return

    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument, commands.TooManyArguments)):
        name = ctx.command.qualified_name if ctx.command else ""
        info = COMMAND_USAGE.get(name)
        if info:
            usage, example = info
            await ctx.send(
                f"⚠️ Wrong usage of `!{name}`.\n"
                f"**Usage:** `{usage}`\n"
                f"**Example:** `{example}`"
            )
        else:
            await ctx.send(f"⚠️ {error}\nRun `!commands` for the full list.")
        return

    if isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 You don't have permission to run that command.")
        return

    log.exception("Unhandled command error in '%s': %s", ctx.message.content, error)
    await ctx.send(f"💥 Something went wrong: `{error}`\nIf this keeps happening, check the bot logs.")
