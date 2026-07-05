"""
!plans — Show or generate trade plans for a given ticker and date range.

Workflow:
  1. Query the trade log for recorded plans matching the criteria.
  2. If plans exist → display them with links to !trade ID for full charts.
  3. If nothing recorded → run the backtest engine over that window and
     display the setups it would have fired (entry, stop, target, outcome).

Usage:
  !plans TICKER [from:YYYY-MM-DD] [to:YYYY-MM-DD] [horizon] [strategy]
  !plans TICKER from:2024-01-01 to:2024-12-31
  !plans TSLA from:2024-06-01 4w bnr
"""
import asyncio
from collections import defaultdict

import discord

from swingbot.bot_core import bot
from swingbot.core import scan_engine
from swingbot.core.data import get_daily_data, get_currency_symbol
from swingbot import config
from swingbot.core.strategy import HORIZONS
from swingbot.commands.backtest import (
    STRATEGY_MAP, ALL_STRATEGIES, _parse_backtest_args, _sync_backtest_one,
)

trade_log = scan_engine.trade_log

USAGE = (
    "**Usage:** `!plans TICKER [from:YYYY-MM-DD] [to:YYYY-MM-DD] [horizon] [strategy]`\n"
    "**Examples:**\n"
    "  `!plans TSLA` — last 90 days, all horizons/strategies\n"
    "  `!plans TSLA from:2024-01-01 to:2024-12-31`\n"
    "  `!plans AAPL 4w bnr from:2024-06-01`\n"
    "  `!plans MSFT from:2024-01-01 macd`\n"
    "\nIf no recorded trade plans are found in the window, the bot runs a "
    "historical backtest and shows every setup that would have triggered."
)


def _parse_plans_args(args: tuple):
    """
    Same flexible parser as backtest — horizon, strategy, from:, to:.
    Returns (horizon, strategy_norm, date_from, date_to).
    Defaults to last 90 days if no dates given.
    """
    import datetime as dt
    horizon = "all"
    strategy_norm = "all"
    date_from = date_to = None
    valid_horizons = {"all", *HORIZONS.keys()}

    for token in args:
        tl = token.lower().replace(" ", "").replace("_", "")
        if tl in valid_horizons:
            horizon = tl
        elif tl in STRATEGY_MAP:
            strategy_norm = STRATEGY_MAP[tl]
        elif tl == "all":
            strategy_norm = "all"
        elif tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]

    # Default: last 90 days
    if not date_from and not date_to:
        date_from = (dt.date.today() - dt.timedelta(days=90)).isoformat()

    return horizon, strategy_norm, date_from, date_to


def _query_trade_log(ticker: str, horizon: str, strategy_norm: str,
                     date_from: str, date_to: str) -> list:
    """Return recorded trade log entries matching criteria."""
    from_dt = date_from or "0000-01-01"
    to_dt   = date_to   or "9999-12-31"

    all_trades = trade_log.get_trades(ticker=ticker, limit=None)

    def _matches(t):
        opened = t.get("opened_at", "")[:10]
        if opened < from_dt or opened > to_dt:
            return False
        if horizon != "all" and t.get("horizon_key") != horizon:
            return False
        if strategy_norm != "all" and t.get("strategy") != strategy_norm:
            return False
        return True

    return [t for t in all_trades if _matches(t)]


def _format_logged_plan(t: dict) -> str:
    """One-line summary of a recorded trade plan."""
    direction_emoji = "📈" if t.get("direction") == "bullish" else "📉"
    status_emoji    = {"open": "🟡", "win": "✅", "loss": "❌", "closed": "⬜"}.get(
        t.get("status", ""), "⬜"
    )
    entry  = t.get("entry_price", t.get("entry", "?"))
    stop   = t.get("stop_loss", "?")
    target = t.get("take_profit", "?")
    lv     = t.get("confidence_level", "?")
    strat  = t.get("strategy", "?")
    horiz  = t.get("horizon_key", "?")
    opened = t.get("opened_at", "?")[:10]
    tid    = t.get("id", "?")
    return (
        f"{direction_emoji} {status_emoji} **{t.get('ticker','?')}** `{horiz}` — "
        f"Lv{lv} · {strat}\n"
        f"  Entry **{entry}** · Stop {stop} · Target {target}\n"
        f"  Opened: {opened}  `ID: {tid}`  — `!trade {tid}` for full chart"
    )


def _build_summary_stats_from_logged(logged: list) -> str:
    """
    Per-strategy win rate for RECORDED (real, already-alerted) trade plans --
    the same shape as _build_summary_stats() below, which does it for
    backtest-generated setups. Split out so `!plans` shows a win-rate table
    either way, instead of only when nothing was recorded yet.
    """
    stats: dict = defaultdict(lambda: {"wins": 0, "losses": 0, "open": 0})
    for t in logged:
        strat = t.get("strategy", "?")
        status = t.get("status", "")
        if status == "win":
            stats[strat]["wins"] += 1
        elif status == "loss":
            stats[strat]["losses"] += 1
        else:
            stats[strat]["open"] += 1

    lines = ["```", f"{'Strategy':18s} {'W':>3s} {'L':>3s} {'Open':>4s} {'Win%':>6s}"]
    total_w = total_l = total_o = 0
    for strat in sorted(stats):
        s = stats[strat]
        w, l, o = s["wins"], s["losses"], s["open"]
        ev = w + l
        wr = f"{w/ev*100:.0f}%" if ev else "n/a"
        lines.append(f"{strat[:18]:18s} {w:>3d} {l:>3d} {o:>4d} {wr:>6s}")
        total_w += w; total_l += l; total_o += o
    total_ev = total_w + total_l
    wr_all = f"{total_w/total_ev*100:.0f}%" if total_ev else "n/a"
    lines.append(f"{'TOTAL':18s} {total_w:>3d} {total_l:>3d} {total_o:>4d} {wr_all:>6s}")
    lines.append("```")
    lines.append("*W=wins, L=losses, Open=not yet closed. Based on real recorded alerts, not a backtest.*")
    return "\n".join(lines)


def _deduplicate_setups(setups: list) -> list:
    """
    One trade at a time per (strategy, horizon) pair.

    For each strategy/horizon, discard any signal that begins while the
    previous trade in that pair is still running (exit_date hasn't passed
    yet, or the trade timed out with no recorded exit). This matches how
    you'd actually trade these signals — you don't pile on while already
    in a position.
    """
    last_exit: dict = {}   # (strategy, horizon) → last exit_date str or entry_date str
    filtered = []
    for strat, horiz, trade, cur in setups:
        key = (strat, horiz)
        prev_exit = last_exit.get(key)
        if prev_exit and trade.entry_date <= prev_exit:
            continue   # skip — overlaps with previous trade
        filtered.append((strat, horiz, trade, cur))
        # Use exit_date if available, else fall back to entry_date
        # (a timeout stays "open" until its entry_date for dedup purposes,
        # so the very next bar can still be taken — reasonable conservative choice)
        last_exit[key] = trade.exit_date or trade.entry_date
    return filtered


def _build_summary_stats(setups: list) -> str:
    """Build a compact stats table across all setups."""
    # Per-strategy aggregates (across all horizons)
    from collections import defaultdict
    stats: dict = defaultdict(lambda: {"wins": 0, "losses": 0, "total_r": 0.0, "timeouts": 0})

    for strat, horiz, trade, cur in setups:
        s = stats[strat]
        if trade.outcome == "win":
            s["wins"] += 1
            s["total_r"] += (trade.r_multiple or 0)
        elif trade.outcome == "loss":
            s["losses"] += 1
            s["total_r"] += (trade.r_multiple or 0)
        else:
            s["timeouts"] += 1

    lines = ["```", f"{'Strategy':18s} {'W':>3s} {'L':>3s} {'TO':>3s} {'Win%':>6s} {'TotalR':>7s}"]
    total_w = total_l = total_to = 0
    total_r = 0.0
    for strat in sorted(stats):
        s = stats[strat]
        w, l, to = s["wins"], s["losses"], s["timeouts"]
        ev = w + l
        wr = f"{w/ev*100:.0f}%" if ev else "n/a"
        tr = f"{s['total_r']:+.1f}R" if ev else "n/a"
        lines.append(f"{strat[:18]:18s} {w:>3d} {l:>3d} {to:>3d} {wr:>6s} {tr:>7s}")
        total_w += w; total_l += l; total_to += to; total_r += s["total_r"]
    total_ev = total_w + total_l
    wr_all = f"{total_w/total_ev*100:.0f}%" if total_ev else "n/a"
    tr_all = f"{total_r:+.1f}R" if total_ev else "n/a"
    lines.append(f"{'TOTAL':18s} {total_w:>3d} {total_l:>3d} {total_to:>3d} {wr_all:>6s} {tr_all:>7s}")
    lines.append("```")
    lines.append("*W=wins, L=losses, TO=timed out (no hit within max hold period)*")
    return "\n".join(lines)


def _sync_generate_plans(ticker: str, horizon: str, strategy_norm: str,
                          date_from: str, date_to: str):
    """Run backtest engine and return deduplicated setups in the date window."""
    df = get_daily_data(ticker, period="max")
    cur = get_currency_symbol(ticker, config.CURRENCY_SYMBOL)

    from swingbot.core.backtest import run_backtest_daterange, ALL_STRATEGIES as _ALL

    strategies = [strategy_norm] if strategy_norm != "all" else list(_ALL)
    horizons   = [horizon] if horizon != "all" else list(HORIZONS.keys())

    raw = []
    for h in horizons:
        for s in strategies:
            summary = run_backtest_daterange(ticker, df, s, h, date_from, date_to)
            for trade in summary.trades:
                raw.append((s, h, trade, cur))

    # Sort chronologically before deduplication
    raw.sort(key=lambda x: x[2].entry_date)

    # Remove overlapping trades per strategy/horizon
    setups = _deduplicate_setups(raw)

    return setups, len(df)


def _format_generated_plan(strat: str, horiz: str, t, cur: str) -> str:
    """Format a backtest-generated setup as a trade plan summary."""
    direction_emoji = "📈" if t.direction == "bullish" else "📉"
    outcome_emoji   = {"win": "✅", "loss": "❌", "timeout": "⏳"}.get(t.outcome, "❓")
    r_str = f"{t.r_multiple:+.2f}R" if t.r_multiple is not None else "—"

    if t.outcome == "timeout":
        exit_str = f"→ ⏳ timed out (no exit within max hold)"
    elif t.exit_date:
        exit_str = f"→ exit {t.exit_date} ({r_str})"
    else:
        exit_str = "→ open"

    hold_str = f" · held {t.holding_days}d" if t.holding_days else ""
    return (
        f"{direction_emoji} {outcome_emoji} `{horiz}` **{strat}** — {t.entry_date} {exit_str}{hold_str}\n"
        f"  Entry **{cur}{t.entry:.2f}** · Stop {cur}{t.stop_loss:.2f} · "
        f"Target {cur}{t.take_profit:.2f}"
    )


@bot.command(name="plans")
async def plans_cmd(ctx, ticker: str = None, *args):
    """
    Show or generate trade plans for a ticker over a date range.

    !plans TICKER [from:DATE] [to:DATE] [horizon] [strategy]
    """
    if ticker is None:
        await ctx.send(USAGE)
        return

    ticker = ticker.upper()
    if ticker.startswith("FROM:") or ticker.startswith("TO:"):
        await ctx.send(f"⚠️ Please provide a ticker first.\n{USAGE}")
        return

    horizon, strategy_norm, date_from, date_to = _parse_plans_args(args)

    range_str  = f"{date_from or '…'} → {date_to or 'now'}"
    horiz_str  = f" · horizon `{horizon}`" if horizon != "all" else ""
    strat_str  = f" · strategy `{strategy_norm}`" if strategy_norm != "all" else ""
    header_ctx = f"**{ticker}** · {range_str}{horiz_str}{strat_str}"

    status_msg = await ctx.send(f"🔍 Looking up trade plans for {header_ctx}…")

    # --- Step 1: check trade log ---
    logged = _query_trade_log(ticker, horizon, strategy_norm, date_from, date_to)

    if logged:
        await status_msg.edit(
            content=f"📋 Found **{len(logged)} recorded** trade plan(s) for {header_ctx}:"
        )
        await ctx.send("**Win rate by strategy** (recorded alerts):")
        await ctx.send(_build_summary_stats_from_logged(logged))
        for t in logged:
            await ctx.send(_format_logged_plan(t))
        await ctx.send(
            f"*These are plans the bot actually posted. "
            f"Use `!plans {ticker} ... generate` to also see backtest-generated setups.*"
        )
        return

    # --- Step 2: nothing recorded — generate from backtest ---
    await status_msg.edit(
        content=(
            f"📭 No recorded plans found for {header_ctx}.\n"
            f"🔄 Generating historical setups via backtest engine…"
        )
    )

    try:
        setups, bar_count = await asyncio.to_thread(
            _sync_generate_plans, ticker, horizon, strategy_norm, date_from, date_to
        )
    except Exception as e:
        await status_msg.edit(content=f"⚠️ Could not fetch data for **{ticker}**: {e}")
        return

    if not setups:
        await status_msg.edit(
            content=(
                f"📭 No trade setups found for {header_ctx} "
                f"({bar_count} bars of history checked).\n"
                "Try a wider date range, different horizon, or different strategy."
            )
        )
        return

    ev_count = sum(1 for _, _, t, _ in setups if t.outcome in ("win", "loss"))
    win_count = sum(1 for _, _, t, _ in setups if t.outcome == "win")
    win_pct = f"{win_count/ev_count*100:.0f}%" if ev_count else "n/a"
    total_r = sum(t.r_multiple or 0 for _, _, t, _ in setups if t.outcome in ("win", "loss"))
    total_r_str = f"{total_r:+.1f}R" if ev_count else "n/a"

    await status_msg.edit(
        content=(
            f"⚙️ **{len(setups)} setup(s)** for {header_ctx} ({bar_count} bars)\n"
            f"📊 Closed trades: **{ev_count}** evaluated · **{win_pct}** win rate · **{total_r_str}** total R\n"
            f"*(one trade at a time per strategy/horizon — overlapping signals skipped)*"
        )
    )

    # Summary stats table
    await ctx.send(_build_summary_stats(setups))

    # Individual setups in batches
    batch = []
    for strat, horiz, trade, cur in setups:
        line = _format_generated_plan(strat, horiz, trade, cur)
        batch.append(line)
        if len("\n\n".join(batch)) > 1800:
            await ctx.send("\n\n".join(batch[:-1]))
            batch = [line]
    if batch:
        await ctx.send("\n\n".join(batch))

    await ctx.send(
        "⚠️ *Generated setups are backtest simulations — no fees/slippage. "
        "Overlapping signals within the same strategy/horizon are skipped. "
        "Recorded alerts (`!check`) apply stricter confluence and confidence filters.*"
    )
