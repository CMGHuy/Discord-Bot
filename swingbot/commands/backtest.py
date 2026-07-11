"""!backtest, !backtestwatchlist, !backtestconfluence."""
import asyncio

from swingbot.core.backtest import (
    run_backtest, run_backtest_daterange, run_full_backtest,
    run_confluence_backtest_daterange, summarize_confluence_trades,
    CONFLUENCE_HORIZONS, CONFLUENCE_MIN_AGREE, CONFLUENCE_RR,
)
from swingbot.bot_core import bot
from swingbot.core.data import get_daily_data
from swingbot.core.strategy import HORIZONS
from swingbot.core.watchlist import load_watchlist

STRATEGY_MAP = {
    # legacy
    "ema": "EMA Crossover", "emacrossover": "EMA Crossover",
    "vwap": "VWAP",
    "fib": "Fibonacci", "fibonacci": "Fibonacci",
    "sr": "Support/Resistance", "resistance": "Support/Resistance", "support": "Support/Resistance",
    "rsi": "RSI",
    "macd": "MACD",
    "elliott": "Elliott Wave", "ew": "Elliott Wave", "elliottwave": "Elliott Wave",
    # new
    "maribbon": "MA Ribbon", "ribbon": "MA Ribbon", "mar": "MA Ribbon",
    "bnr": "Break & Retest", "retest": "Break & Retest", "breakretest": "Break & Retest",
    "rsidiv": "RSI Divergence", "divergence": "RSI Divergence", "rsidivergence": "RSI Divergence",
    "volprofile": "Volume Profile", "hvn": "Volume Profile", "vp": "Volume Profile",
}

ALL_STRATEGIES = (
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence", "Volume Profile",
)

STRATEGY_ALIASES_HELP = (
    "ema, vwap, fib, sr, rsi, macd, elliott, "
    "ribbon/maribbon, bnr/retest, rsidiv/divergence, volprofile/hvn, all"
)


def _parse_date_args(args: list) -> tuple:
    """
    Scan args for from:YYYY-MM-DD and to:YYYY-MM-DD tokens.
    Returns (date_from, date_to, remaining_args).
    """
    date_from = date_to = None
    remaining = []
    for a in args:
        al = a.lower()
        if al.startswith("from:"):
            date_from = a[5:]
        elif al.startswith("to:"):
            date_to = a[3:]
        else:
            remaining.append(a)
    return date_from, date_to, remaining


def _run_backtest_combo(ticker, df, horizon, strategy_norm, date_from=None, date_to=None):
    use_range = date_from or date_to
    if horizon != "all" and strategy_norm != "all":
        if use_range:
            return [run_backtest_daterange(ticker, df, strategy_norm, horizon, date_from, date_to)]
        return [run_backtest(ticker, df, strategy_norm, horizon)]
    elif strategy_norm != "all":
        horizons = list(HORIZONS.keys())
        if use_range:
            return [run_backtest_daterange(ticker, df, strategy_norm, h, date_from, date_to) for h in horizons]
        return [run_backtest(ticker, df, strategy_norm, h) for h in horizons]
    elif horizon != "all":
        if use_range:
            return [run_backtest_daterange(ticker, df, s, horizon, date_from, date_to) for s in ALL_STRATEGIES]
        return [run_backtest(ticker, df, s, horizon) for s in ALL_STRATEGIES]
    else:
        summaries = run_full_backtest(ticker, df)
        if use_range:
            summaries = [run_backtest_daterange(ticker, df, s.strategy, s.horizon_key, date_from, date_to)
                         for s in summaries]
        return summaries


def _sync_backtest_one(ticker, horizon, strategy_norm, date_from, date_to):
    df = get_daily_data(ticker, period="max")
    summaries = _run_backtest_combo(ticker, df, horizon, strategy_norm, date_from, date_to)
    return len(df), summaries


def _sync_backtest_watchlist(tickers, horizon, strategy_norm, date_from, date_to):
    all_summaries = []
    errors = []
    for t in tickers:
        try:
            df = get_daily_data(t, period="max")
        except Exception as e:
            errors.append((t, str(e)))
            continue
        all_summaries.extend(_run_backtest_combo(t, df, horizon, strategy_norm, date_from, date_to))
    return all_summaries, errors


def _format_backtest_table(header, summaries):
    lines = [header, "```"]
    lines.append(f"{'Strategy':18s} {'Horiz':5s} {'Sig':>4s} {'Eval':>4s} {'Scr':>4s} {'TO':>4s} {'Win%':>6s} {'ExpR':>6s} {'MaxDD%':>7s} {'AvgDays':>7s}")
    for s in summaries:
        wr = f"{s.win_rate:.0f}" if s.win_rate is not None else "n/a"
        er = f"{s.expectancy_r:.2f}" if s.expectancy_r is not None else "n/a"
        dd = f"{s.max_drawdown_pct:.1f}" if s.max_drawdown_pct is not None else "n/a"
        ad = f"{s.avg_holding_days:.0f}" if s.avg_holding_days is not None else "n/a"
        lines.append(f"{s.strategy:18s} {s.horizon_key:5s} {s.total_signals:4d} {s.evaluated:4d} {s.scratches:4d} {s.timeouts:4d} {wr:>6s} {er:>6s} {dd:>7s} {ad:>7s}")
    lines.append("```")
    lines.append(
        "Sig=signals, Eval=win+loss trades, Scr=break-even scratches, TO=timeouts (marked to market), "
        "Win%=wins/(wins+losses), ExpR=expectancy in R over ALL closed trades (>0 = profitable).\n"
        "⚠️ No fees/slippage, survivorship bias."
    )
    return "\n".join(lines)


def _format_per_strategy_winrate(summaries):
    """One row per STRATEGY (all horizons pooled) -- the number that answers
    'does this strategy hit 80% win rate AND make money'. The flag requires
    all three: win rate >= 80, expectancy > 0, and scratches+timeouts <= 50%
    of closed trades (else the win rate is resting on excluded trades)."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"evaluated": 0, "wins": 0, "losses": 0,
                               "scratches": 0, "timeouts": 0, "r_weighted": 0.0})
    for s in summaries:
        closed = s.evaluated + s.scratches + s.timeouts
        if not closed:
            continue
        a = agg[s.strategy]
        a["evaluated"] += s.evaluated
        a["wins"] += s.wins
        a["losses"] += s.losses
        a["scratches"] += s.scratches
        a["timeouts"] += s.timeouts
        if s.expectancy_r is not None:
            a["r_weighted"] += s.expectancy_r * closed

    lines = ["**Win rate by strategy** (all horizons combined):", "```",
             f"{'Strategy':20s} {'Eval':>5s} {'Scr':>4s} {'TO':>4s} {'Win%':>6s} {'ExpR':>7s}  Pass"]
    for strat in ALL_STRATEGIES:
        a = agg.get(strat)
        closed = (a["evaluated"] + a["scratches"] + a["timeouts"]) if a else 0
        if not closed or a["evaluated"] == 0:
            lines.append(f"{strat:20s} {'0':>5s} {'':>4s} {'':>4s}    n/a     n/a  —")
            continue
        wr = a["wins"] / a["evaluated"] * 100
        er = a["r_weighted"] / closed
        excluded_share = (a["scratches"] + a["timeouts"]) / closed
        flag = "✅" if (wr >= 80 and er > 0 and excluded_share <= 0.5) else "❌"
        lines.append(f"{strat:20s} {a['evaluated']:5d} {a['scratches']:4d} {a['timeouts']:4d} {wr:5.1f}% {er:+7.3f}  {flag}")
    lines.append("```")
    lines.append(
        "Pass = win rate ≥80% AND expectancy >0 AND ≤50% of closed trades excluded "
        "(scratches/timeouts). ExpR is averaged over ALL closed trades."
    )
    return "\n".join(lines)


def _format_setup_list(header, summaries):
    """List every individual trade setup across all summaries."""
    all_trades = []
    for s in summaries:
        for t in s.trades:
            all_trades.append((s.strategy, s.horizon_key, t))

    if not all_trades:
        return header + "\nNo trade setups found in that date range."

    chunks = [header, f"Found **{len(all_trades)}** setup(s):\n```"]
    chunks.append(
        f"{'Date':10s} {'Exit':10s} {'Strat':14s} {'H':4s} {'Dir':5s} "
        f"{'Entry':>8s} {'Stop':>8s} {'Target':>8s} {'Result':>8s} {'R':>5s}"
    )
    for strat, horiz, t in all_trades:
        result = t.outcome.upper()[:7]
        r_str = f"{t.r_multiple:.2f}" if t.r_multiple is not None else "open"
        exit_d = t.exit_date or "open"
        dir_s = "BULL" if t.direction == "bullish" else "BEAR"
        chunks.append(
            f"{t.entry_date:10s} {exit_d:10s} {strat[:14]:14s} {horiz:4s} {dir_s:5s} "
            f"{t.entry:>8.2f} {t.stop_loss:>8.2f} {t.take_profit:>8.2f} {result:>8s} {r_str:>5s}"
        )
    chunks.append("```")
    return "\n".join(chunks)


def _parse_backtest_args(args: tuple):
    """
    Parse positional args for !backtest / !backtestwatchlist flexibly.

    Tokens are classified in one pass:
      - Known horizon key or "all"      → horizon
      - Known strategy alias or "all"   → strategy
      - Starts with "from:" or "to:"    → date filter
      - "setups" or "list"              → flag

    Order doesn't matter — `!backtest TSLA setups` and
    `!backtest TSLA 4w bnr setups` both work correctly.
    """
    horizon = "all"
    strategy_norm = "all"
    date_from = date_to = None
    list_setups = False

    valid_horizons = {"all", *HORIZONS.keys()}

    for token in args:
        tl = token.lower().replace(" ", "").replace("_", "")
        if tl in valid_horizons:
            horizon = tl
        elif tl in STRATEGY_MAP:
            strategy_norm = STRATEGY_MAP[tl]
        elif tl == "all":          # strategy = all
            strategy_norm = "all"
        elif tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]
        elif tl in ("setups", "list"):
            list_setups = True
        # unknown tokens silently ignored (avoid hard errors for extra spaces etc.)

    return horizon, strategy_norm, date_from, date_to, list_setups


@bot.command(name="backtest")
async def backtest_cmd(ctx, ticker: str, *args):
    ticker = ticker.upper()
    horizon, strategy_norm, date_from, date_to, list_setups = _parse_backtest_args(args)

    range_str = ""
    if date_from or date_to:
        range_str = f" [{date_from or '…'} → {date_to or 'now'}]"

    await ctx.send(f"Backtesting **{ticker}**{range_str}… this can take a few seconds.")
    try:
        bar_count, summaries = await asyncio.to_thread(
            _sync_backtest_one, ticker, horizon, strategy_norm, date_from, date_to
        )
    except Exception as e:
        await ctx.send(f"⚠️ Could not fetch data for {ticker}: {e}")
        return

    header = f"Backtest — **{ticker}**{range_str} ({bar_count} bars of history):"
    if list_setups:
        msg = _format_setup_list(header, summaries)
    else:
        msg = _format_backtest_table(header, summaries)

    if len(msg) <= 1950:
        await ctx.send(msg)
    else:
        for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
            await ctx.send(chunk)

    # Per-strategy win rate, combined across every horizon shown above.
    await ctx.send(_format_per_strategy_winrate(summaries))


@bot.command(name="backtestwatchlist")
async def backtestwatchlist_cmd(ctx, *args):
    horizon, strategy_norm, date_from, date_to, _ = _parse_backtest_args(args)

    tickers = load_watchlist()
    range_str = f" [{date_from or '…'} → {date_to or 'now'}]" if (date_from or date_to) else ""
    await ctx.send(f"Backtesting **{len(tickers)}** watchlist ticker(s){range_str}… this can take a while.")

    all_summaries, errors = await asyncio.to_thread(
        _sync_backtest_watchlist, tickers, horizon, strategy_norm, date_from, date_to
    )
    for t, err in errors:
        await ctx.send(f"⚠️ Skipping {t}: {err}")

    evaluated = [s for s in all_summaries if s.evaluated >= 5]
    evaluated.sort(key=lambda s: (s.expectancy_r if s.expectancy_r is not None else -999), reverse=True)

    # Per-strategy win rate across the WHOLE watchlist (every ticker, every
    # horizon tested, combined) -- answers "is every strategy hitting 80%?"
    # directly, regardless of whether any single ticker/horizon combo had
    # enough trades on its own to make the leaderboard below.
    await ctx.send(_format_per_strategy_winrate(all_summaries))

    if not evaluated:
        await ctx.send(
            "No combo had ≥5 closed backtest trades across the watchlist — "
            "try `!backtest TICKER` on individual names instead."
        )
        return

    lines = [
        f"**Watchlist backtest leaderboard**{range_str} (combos with 5+ closed trades, ranked by ExpR):",
        "```",
        f"{'Ticker':7s} {'Strategy':18s} {'Horiz':5s} {'Eval':>4s} {'Win%':>6s} {'ExpR':>6s} {'MaxDD%':>7s}",
    ]
    for s in evaluated[:20]:
        wr = f"{s.win_rate:.0f}" if s.win_rate is not None else "n/a"
        er = f"{s.expectancy_r:.2f}" if s.expectancy_r is not None else "n/a"
        dd = f"{s.max_drawdown_pct:.1f}" if s.max_drawdown_pct is not None else "n/a"
        lines.append(f"{s.ticker:7s} {s.strategy:18s} {s.horizon_key:5s} {s.evaluated:4d} {wr:>6s} {er:>6s} {dd:>7s}")
    lines.append("```")
    lines.append("⚠️ Overlapping trades counted independently, no fees/slippage, survivorship bias.")
    await ctx.send("\n".join(lines))


def _sync_confluence_watchlist(tickers, min_agree, rr, date_from, date_to):
    all_trades = []
    errors = []
    for t in tickers:
        try:
            df = get_daily_data(t, period="max")
        except Exception as e:
            errors.append((t, str(e)))
            continue
        for horizon_key in CONFLUENCE_HORIZONS:
            all_trades.extend(
                run_confluence_backtest_daterange(t, df, horizon_key, date_from, date_to, min_agree, rr)
            )
    return all_trades, errors


@bot.command(name="backtestconfluence")
async def backtestconfluence_cmd(ctx, *args):
    """
    Alternative to !backtest / !backtestwatchlist: instead of trusting any
    single strategy (whose own targets are sized at 0.35-0.40x the stop
    distance -- see core/strategy_types.STRATEGY_RR_OVERRIDE, and the
    exit engine's break-even/scratch rule in core/backtest.py's module
    docstring), this only takes a trade when >=min_agree of the 11
    strategies fire the same direction on the same day, using a real
    reward:risk target (default 0.25 -- the exact ratio where 80% win
    rate is break-even).

    Usage: !backtestconfluence [min_agree] [rr] [from:YYYY-MM-DD] [to:YYYY-MM-DD]
    Defaults: min_agree=2, rr=0.25, full available history.
    Runs across the whole watchlist and CONFLUENCE_HORIZONS (2w excluded --
    validated negative edge on 2024 data).
    """
    min_agree = CONFLUENCE_MIN_AGREE
    rr = CONFLUENCE_RR
    date_from = date_to = None
    for token in args:
        tl = token.lower()
        if tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]
        elif token.isdigit():
            min_agree = int(token)
        else:
            try:
                rr = float(token)
            except ValueError:
                pass

    tickers = load_watchlist()
    range_str = f" [{date_from or '…'} → {date_to or 'now'}]" if (date_from or date_to) else ""
    await ctx.send(
        f"Backtesting **{len(tickers)}** watchlist ticker(s) with confluence >= {min_agree} strategies, "
        f"R:R={rr}{range_str} across {', '.join(CONFLUENCE_HORIZONS)}… this can take a while."
    )

    all_trades, errors = await asyncio.to_thread(
        _sync_confluence_watchlist, tickers, min_agree, rr, date_from, date_to
    )
    for t, err in errors:
        await ctx.send(f"⚠️ Skipping {t}: {err}")

    overall = summarize_confluence_trades(all_trades)
    if overall["evaluated"] == 0:
        await ctx.send("No closed confluence trades found in that window.")
        return

    lines = [
        f"**Confluence backtest**{range_str} — min_agree={min_agree}, R:R={rr}:",
        "```",
        f"Trades evaluated: {overall['evaluated']}  (wins {overall['wins']}, losses {overall['losses']})",
        f"Win rate:   {overall['win_rate']:.2f}%",
        f"Expectancy: {overall['expectancy_r']:+.4f}R per trade  (avg win {overall['avg_win_r']:.3f}R, avg loss {overall['avg_loss_r']:.3f}R)",
        "```",
        "Per-horizon breakdown:",
        "```",
        f"{'Horiz':6s} {'N':>5s} {'Win%':>7s} {'ExpR':>8s}",
    ]
    for hk in CONFLUENCE_HORIZONS:
        ts = [t for t in all_trades if t.horizon_key == hk]
        s = summarize_confluence_trades(ts)
        if s["evaluated"] == 0:
            continue
        lines.append(f"{hk:6s} {s['evaluated']:5d} {s['win_rate']:6.1f}% {s['expectancy_r']:+8.4f}")
    lines.append("```")
    lines.append(
        "⚠️ Same limitations as !backtestwatchlist (overlapping trades, no fees/slippage, "
        "survivorship bias). Expectancy > 0 means the system is net profitable on average per "
        "trade risked; win rate alone does not tell you that -- see core/backtest.py docstring."
    )
    await ctx.send("\n".join(lines))
