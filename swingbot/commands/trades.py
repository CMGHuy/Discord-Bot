"""!trades, !trade, !tradecharts, !performance, !pnl, !summary."""
import asyncio
import os
from datetime import datetime, timezone

import discord

from swingbot import config
from swingbot.core import account as account_module
from swingbot.core import scan_engine
from swingbot.core.data import get_currency_symbol
from swingbot.bot_core import bot
from swingbot.core.risk_metrics import compute_risk_metrics

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BERLIN_TZ = _ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

trade_log = scan_engine.trade_log


def _primary_source_label(t: dict) -> str:
    """
    Picks the highest-priority confirming method from a trade's
    target_sources / stop_sources lists, using the same METHOD_PRIORITY
    ranking as the admin dashboard and trade charts.  Falls back to
    t["strategy"] (the old fixed "S/R Confluence" default) for trades
    logged before those source lists existed.
    """
    from swingbot.core.charts.chart_style import METHOD_PRIORITY
    sources = list(dict.fromkeys(
        (t.get("target_sources") or []) + (t.get("stop_sources") or [])
    ))
    if not sources:
        return t.get("strategy") or "--"

    def _rank(label: str):
        for i, key in enumerate(METHOD_PRIORITY):
            if label.startswith(key):
                return i
        return None

    ranked = [(r, s) for s in sources for r in [_rank(s)] if r is not None]
    if not ranked:
        return sources[0]
    ranked.sort(key=lambda x: x[0])
    return ranked[0][1]

MIN_PER_PAGE = 1
MAX_PER_PAGE = 25
DEFAULT_PER_PAGE = 10


def format_trade_row(t: dict, currency: str) -> str:
    """One fixed-width `!trades` table row. Legacy (no `legs`) behavior is
    byte-for-byte unchanged; a v2 two-leg trade (Task 68) gets a leg-aware
    Gain/Loss suffix instead of the plain amount -- banked leg + 'runner
    open' while still open, the already-summed realized total once closed
    (no recomputation -- Task 68's settle_legs already did that math)."""
    # Use the actual confirming method (target_sources/stop_sources priority
    # ranking) instead of the static "S/R Confluence" t["strategy"] default.
    method = _primary_source_label(t)
    method_short = method[:10]
    dir_short = "LONG" if t['direction'] == "bullish" else "SHORT"
    conf_level = t.get('confidence_level')
    conf_str = f"L{conf_level}" if conf_level is not None else "--"

    legs = t.get("legs") or []
    if legs and t.get("status") == "open":
        banked = sum((t.get("shares") or 0) * l["fraction"]
                     * (l["exit_price"] - t["entry"])
                     * (1 if t["direction"] == "bullish" else -1) for l in legs)
        frac = sum(l["fraction"] for l in legs)
        amount_str = f"+{currency}{banked:,.2f} (TP1 {frac:.0%}) / runner open"
    elif legs:
        amount = t.get("realized_pnl_amount") or 0.0
        amount_str = f"{'+' if amount >= 0 else ''}{currency}{abs(amount):,.2f}"
    else:
        # Realized $/€ gain/loss -- only meaningful for a closed win/loss
        # trade that has a sizing snapshot (see account.py/performance.py);
        # blank for a still-open trade or one logged before this existed.
        amount = t.get("realized_pnl_amount")
        amount_str = f"{amount:+.2f}" if amount is not None else "--"

    engine_str = "v2" if (t.get("plan_id") or legs) else "--"
    return (
        f"{t['id']:8s} {t['ticker']:6s} {method_short:10s} {t['horizon_key']:3s} {dir_short:5s} "
        f"{conf_str:5s} {t['entry']:>9.2f} {t['stop_loss']:>9.2f} {t['take_profit']:>9.2f} "
        f"{t['status']:6s} {engine_str:3s} {amount_str:>11s}"
    )


def format_trades_table(trades, header: str) -> str:
    lines = [header, "```"]
    lines.append(
        f"{'ID':8s} {'Ticker':6s} {'Method':10s} {'H':3s} {'Dir':5s} {'Conf':5s} "
        f"{'Entry':>9s} {'SL':>9s} {'TP':>9s} {'Status':6s} {'Eng':3s} {'Gain/Loss':>11s}"
    )
    for t in trades:
        lines.append(format_trade_row(t, config.CURRENCY_SYMBOL))
    lines.append("```")
    lines.append("Use `!trade ID` for full detail, `!trade delete ID` to remove one, `!trades clear` to clear active trades, `!trades clear history` to clear closed trade history.")
    return "\n".join(lines)


class TradesPaginator(discord.ui.View):
    """
    Prev/Next pagination over an already-sorted trade list. Only the
    person who ran the command can page through it (button clicks from
    anyone else are declined) -- keeps multiple people paging the same
    channel from stepping on each other's page state.
    """

    def __init__(self, trades: list, header: str, per_page: int, author_id: int):
        super().__init__(timeout=180)
        self.trades = trades
        self.header = header
        self.per_page = per_page
        self.author_id = author_id
        self.page = 0
        self.max_page = max(0, (len(trades) - 1) // per_page) if trades else 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.max_page

    def render(self) -> str:
        start = self.page * self.per_page
        page_trades = self.trades[start:start + self.per_page]
        header = (
            f"{self.header} — page {self.page + 1}/{self.max_page + 1} "
            f"({len(self.trades)} total, {self.per_page}/page)"
        )
        return format_trades_table(page_trades, header)

    async def _turn_page(self, interaction: discord.Interaction, delta: int):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran `!trades` can page through this -- run it yourself to get your own pager.",
                ephemeral=True,
            )
            return
        self.page = max(0, min(self.max_page, self.page + delta))
        self._sync_buttons()
        await interaction.response.edit_message(content=self.render(), view=self)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._turn_page(interaction, -1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._turn_page(interaction, 1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@bot.group(name="trades", invoke_without_command=True)
async def trades_cmd(ctx, status: str = "all", per_page: int = DEFAULT_PER_PAGE):
    """
    Shows every logged trade -- any confidence level, any status by
    default -- sorted highest confidence first, paginated with Prev/Next
    buttons. `per_page` sets how many rows show per page (1-25).
    """
    if status not in ("open", "win", "loss", "all"):
        await ctx.send("Status must be one of: open, win, loss, all")
        return
    per_page = max(MIN_PER_PAGE, min(per_page, MAX_PER_PAGE))

    trades = trade_log.get_trades(status=status, limit=None, sort_by="confidence")
    if not trades:
        await ctx.send(f"No trades found for status='{status}'.")
        return

    view = TradesPaginator(trades, f"**Trades ({status}, sorted by confidence high→low)**", per_page, ctx.author.id)
    view.message = await ctx.send(view.render(), view=view)


@trades_cmd.group(name="clear", invoke_without_command=True)
async def trades_clear(ctx):
    """Clear all currently OPEN/active trades. Closed trade history is kept.
    Use `!trades clear history` to remove closed trade records instead."""
    count = trade_log.clear_open()
    await ctx.send(f"Cleared {count} open trade(s). Closed win/loss history was not touched.")


@trades_clear.command(name="history")
async def trades_clear_history(ctx):
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    count = trade_log.clear_history()
    await ctx.send(f"Cleared {count} closed trade record(s). Open trades were not touched.")


def _build_trade_detail_embed(match: dict) -> discord.Embed:
    """
    One trade's full detail as a proper Discord embed -- a grid of
    label/value fields (Discord's own "table" layout) instead of a wall of
    prose sentences, so entry/stop/target/status etc. each read as their
    own row instead of being buried mid-sentence.
    """
    is_bull = match["direction"] == "bullish"
    is_open = match["status"] == "open"
    direction_word = "LONG (buy)" if is_bull else "SHORT (sell)"
    cur = get_currency_symbol(match["ticker"], config.CURRENCY_SYMBOL)
    method = _primary_source_label(match)

    if is_open:
        icon, color = "🔵", discord.Color.blue()
        status_word = "OPEN"
    elif match["status"] == "win":
        icon, color = "✅", discord.Color.green()
        status_word = "WIN ✅"
    elif match["status"] == "loss":
        icon, color = "❌", discord.Color.red()
        status_word = "LOSS ❌"
    else:
        icon, color = "🔒", discord.Color.from_rgb(90, 98, 117)
        status_word = "MANUALLY CLOSED"

    embed = discord.Embed(title=f"{icon} Trade {match['id']} — {match['ticker']}", color=color)

    embed.add_field(name="Status", value=status_word, inline=True)
    embed.add_field(name="Direction", value=direction_word, inline=True)
    embed.add_field(name="Confidence", value=f"{match['confidence_label']} (Lv{match['confidence_level']})", inline=True)

    embed.add_field(name="Strategy", value=method, inline=True)
    embed.add_field(name="Horizon", value=match["horizon_key"], inline=True)
    if match.get("risk_reward_ratio"):
        embed.add_field(name="Reward:Risk", value=f"{match['risk_reward_ratio']}:1", inline=True)
    else:
        embed.add_field(name="​", value="​", inline=True)   # keeps the 3-column grid even

    reward_pct = abs(match["take_profit"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
    embed.add_field(name="Entry", value=f"{cur}{match['entry']:.2f}", inline=True)
    embed.add_field(name="Stop-loss", value=f"{cur}{match['stop_loss']:.2f}", inline=True)
    embed.add_field(name="Target 1", value=f"{cur}{match['take_profit']:.2f} (+{reward_pct:.1f}%)", inline=True)

    if match.get("target2"):
        t2_pct = abs(match["target2"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
        embed.add_field(name="Target 2 (stretch)", value=f"{cur}{match['target2']:.2f} (+{t2_pct:.1f}%)", inline=True)

    embed.add_field(name="Opened", value=match["opened_at"][:16].replace("T", " ") + " UTC", inline=True)

    if not is_open:
        exit_price = match.get("exit_price")
        embed.add_field(
            name="Closed",
            value=(match.get("closed_at") or "n/a")[:16].replace("T", " ") + " UTC",
            inline=True,
        )
        embed.add_field(name="Exit price", value=f"{cur}{exit_price:.2f}" if exit_price else "n/a", inline=True)

        # Realized P&L% + $/€ gain-loss -- the actual currency amount from
        # the position size snapshotted when this trade was opened (see
        # account.py / performance.py's _settle_account_balance). "n/a" for
        # a manual close (no exit price) or a trade logged before sizing
        # snapshots existed.
        if exit_price and match["entry"]:
            raw_pct = (exit_price - match["entry"]) / match["entry"] * 100
            pnl_pct = raw_pct if is_bull else -raw_pct
            embed.add_field(name="Realized P&L", value=f"{pnl_pct:+.2f}%", inline=True)
        else:
            embed.add_field(name="Realized P&L", value="n/a", inline=True)

        amount = match.get("realized_pnl_amount")
        embed.add_field(name="Gain/Loss", value=f"{amount:+.2f}{cur}" if amount is not None else "n/a", inline=True)

    if match.get("close_reason"):
        embed.add_field(name="Close reason", value=match["close_reason"], inline=False)

    footer = f"Trade ID: {match['id']}"
    if match.get("plan_id") or match.get("legs"):
        footer += " · Plan Engine v2"
    embed.set_footer(text=footer)
    return embed


@bot.group(name="trade", invoke_without_command=True)
async def trade_cmd(ctx, trade_id: str):
    match = trade_log.get_trade_by_id(trade_id)
    if not match:
        await ctx.send(f"No trade found with id `{trade_id}`. Use `!trades` to list recent ones.")
        return

    embed = _build_trade_detail_embed(match)
    chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, match)
    if chart_path:
        filename = os.path.basename(chart_path)
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=discord.File(chart_path, filename=filename))
    else:
        embed.add_field(name="⚠️ Chart", value="Could not generate a chart for this trade right now.", inline=False)
        await ctx.send(embed=embed)


@trade_cmd.command(name="delete")
async def trade_delete(ctx, trade_id: str):
    deleted = trade_log.delete_trade(trade_id)
    if deleted:
        await ctx.send(f"Deleted trade `{trade_id}`.")
    else:
        await ctx.send(f"No trade found with id `{trade_id}`.")


@bot.command(name="tradecharts")
async def tradecharts_cmd(ctx, status: str = "open", limit: int = 5):
    if status not in ("open", "win", "loss", "all"):
        await ctx.send("Status must be one of: open, win, loss, all")
        return
    limit = min(limit, 10)
    trades = trade_log.get_trades(status=status, limit=limit)
    if not trades:
        await ctx.send(f"No trades found for status='{status}'.")
        return

    await ctx.send(f"Generating charts for {len(trades)} trade(s)…")
    for t in trades:
        chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, t)
        caption = f"**{t['id']}** {t['ticker']} — {t['strategy']} ({t['horizon_key']}), {t['direction']}, status: {t['status']}"
        if chart_path:
            await ctx.send(caption, file=discord.File(chart_path, filename=os.path.basename(chart_path)))
        else:
            await ctx.send(caption + " (chart unavailable)")


def _append_risk_metrics_lines(lines: list, closed_trades: list):
    """
    Appends risk-adjusted metrics (Sharpe/Sortino/drawdown/Calmar/profit
    factor) if there's enough closed-trade history to compute them
    meaningfully (see risk_metrics.MIN_CLOSED_TRADES); adds nothing
    otherwise (e.g. quantstats isn't installed, or too few trades yet) --
    !performance degrades gracefully to win-rate-only stats, exactly like
    before this feature existed.
    """
    metrics = compute_risk_metrics(closed_trades)
    if not metrics:
        return
    lines.append("")
    lines.append(f"**Risk-adjusted** (from {metrics['n_trades']} closed trades, *per-trade, not annualized*):")
    lines.append(
        f"Sharpe {metrics['sharpe']} · Sortino {metrics['sortino']} · "
        f"Max drawdown {metrics['max_drawdown_pct']}% · "
        f"Calmar {metrics['calmar'] if metrics['calmar'] is not None else 'n/a'}"
    )
    lines.append(
        f"Profit factor {metrics['profit_factor'] if metrics['profit_factor'] is not None else 'n/a'} · "
        f"Avg win {metrics['avg_win_pct']}% · Avg loss {metrics['avg_loss_pct']}% · "
        f"Best {metrics['best_trade_pct']}% · Worst {metrics['worst_trade_pct']}%"
    )


@bot.command(name="performance")
async def performance_cmd(ctx, level: int = None):
    all_trades = trade_log.get_trades(status="all", limit=None)

    if level is not None:
        if level not in range(1, 6):
            await ctx.send("Level must be 1-5.")
            return
        stats = trade_log.get_stats(level)
        wr = f"{stats['win_rate']:.0f}%" if stats["win_rate"] is not None else "n/a"
        lines = [
            f"**Confidence Level {level}** — {stats['total']} trades logged "
            f"({stats['open']} open, {stats['closed']} closed)",
            f"Win rate: {wr} ({stats['wins']}W / {stats['losses']}L)",
        ]
        closed_at_level = [t for t in all_trades if t["confidence_level"] == level and t["status"] in ("win", "loss")]
        _append_risk_metrics_lines(lines, closed_at_level)
        await ctx.send("\n".join(lines))
        return

    lines = ["**Performance by confidence level:**"]
    by_level = trade_log.get_stats_by_confidence()
    for lvl in range(1, 6):
        s = by_level[lvl]
        wr = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "n/a"
        lines.append(f"Lv{lvl}: {wr} win rate — {s['wins']}W/{s['losses']}L closed, {s['open']} open ({s['total']} total)")
    overall = trade_log.get_stats()
    wr_overall = f"{overall['win_rate']:.0f}%" if overall["win_rate"] is not None else "n/a"
    lines.append(f"\n**Overall:** {wr_overall} win rate — {overall['wins']}W/{overall['losses']}L closed, {overall['open']} open")

    closed_overall = [t for t in all_trades if t["status"] in ("win", "loss")]
    _append_risk_metrics_lines(lines, closed_overall)
    await ctx.send("\n".join(lines))


@bot.command(name="pnl")
async def pnl_cmd(ctx):
    await ctx.send("Fetching current prices for all open trades…")
    rows = await asyncio.to_thread(scan_engine.get_all_unrealized_pnl)
    if not rows:
        await ctx.send("No open trades right now.")
        return

    lines = [f"**Unrealized P/L — {len(rows)} open trade(s):**", "```"]
    lines.append(f"{'ID':8s} {'Ticker':6s} {'Dir':7s} {'Entry':>9s} {'Now':>9s} {'P/L%':>7s} {'ToSL%':>6s} {'ToTP%':>6s}")
    total_pct = 0.0
    counted = 0
    for row in rows:
        t, pnl = row["trade"], row["pnl"]
        if pnl is None:
            lines.append(f"{t['id']:8s} {t['ticker']:6s} {t['direction']:7s} {'price unavailable':>40s}")
            continue
        lines.append(
            f"{t['id']:8s} {t['ticker']:6s} {t['direction']:7s} {t['entry']:>9.2f} {pnl.current_price:>9.2f} "
            f"{pnl.pct_change:>+6.2f}% {pnl.distance_to_sl_pct:>5.1f}% {pnl.distance_to_tp_pct:>5.1f}%"
        )
        total_pct += pnl.pct_change
        counted += 1
    lines.append("```")
    if counted:
        lines.append(f"Average unrealized P/L across {counted} priced trade(s): {total_pct/counted:+.2f}%")
    lines.append("ToSL%/ToTP% = how far the current price is from the stop-loss / recommended TP.")
    await ctx.send("\n".join(lines))


def _berlin_date(iso_ts: str):
    """Parses an ISO timestamp and returns its calendar date in Europe/Berlin
    -- the same day boundary performance.py's by-day-of-week breakdown and
    account.py's daily balance summary already use, so "today" means the
    same thing everywhere in the bot."""
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(_BERLIN_TZ) if _BERLIN_TZ else dt).date()


def _closed_pnl_pct(t: dict) -> float | None:
    entry, exit_p = t.get("entry"), t.get("exit_price")
    if not entry or not exit_p:
        return None
    raw = (exit_p - entry) / entry * 100
    return raw if t["direction"] == "bullish" else -raw


@bot.command(name="summary")
async def summary_cmd(ctx):
    """
    Everything that happened TODAY (Europe/Berlin calendar day) in one
    place: trades opened, trades closed (win/loss, %, and $/€), and the
    account balance's own movement today -- a quick end-of-day (or
    check-in-anytime) status read without digging through !trades or the
    admin Performance page.
    """
    today = datetime.now(_BERLIN_TZ).date() if _BERLIN_TZ else datetime.now(timezone.utc).date()
    all_trades = trade_log.get_trades(status="all", limit=None)

    opened_today = [t for t in all_trades if _berlin_date(t.get("opened_at")) == today]
    closed_today = [
        t for t in all_trades
        if t["status"] in ("win", "loss", "closed") and _berlin_date(t.get("closed_at")) == today
    ]
    wins_today   = [t for t in closed_today if t["status"] == "win"]
    losses_today = [t for t in closed_today if t["status"] == "loss"]
    manual_today = [t for t in closed_today if t["status"] == "closed"]

    amounts = [t["realized_pnl_amount"] for t in closed_today if t.get("realized_pnl_amount") is not None]
    net_amount = sum(amounts) if amounts else None
    pnl_pcts = [p for t in closed_today if (p := _closed_pnl_pct(t)) is not None]
    avg_pnl_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else None

    acct = account_module.get_daily_summary()

    color = (
        discord.Color.green() if (net_amount or 0) > 0
        else discord.Color.red() if (net_amount or 0) < 0
        else discord.Color.from_rgb(90, 98, 117)
    )
    embed = discord.Embed(title=f"📋 Today's Summary — {today.isoformat()} (Berlin)", color=color)

    embed.add_field(name="🆕 Opened today", value=str(len(opened_today)), inline=True)
    embed.add_field(name="🏁 Closed today", value=str(len(closed_today)), inline=True)
    embed.add_field(name="📂 Still open", value=str(trade_log.get_stats()["open"]), inline=True)

    embed.add_field(name="Wins", value=f"✅ {len(wins_today)}", inline=True)
    embed.add_field(name="Losses", value=f"❌ {len(losses_today)}", inline=True)
    if manual_today:
        embed.add_field(name="Manually closed", value=f"🔒 {len(manual_today)}", inline=True)
    else:
        embed.add_field(name="​", value="​", inline=True)   # keeps the 3-column grid even

    pnl_emoji = "🟢" if (avg_pnl_pct or 0) > 0 else "🔴" if (avg_pnl_pct or 0) < 0 else "⚪"
    net_emoji = "🟢" if (net_amount or 0) > 0 else "🔴" if (net_amount or 0) < 0 else "⚪"
    embed.add_field(name="📊 Avg realized P&L", value=f"{pnl_emoji} {avg_pnl_pct:+.2f}%" if avg_pnl_pct is not None else "n/a", inline=True)
    embed.add_field(name="💰 Net gain/loss", value=f"{net_emoji} {net_amount:+.2f}" if net_amount is not None else "n/a", inline=True)
    embed.add_field(name="​", value="​", inline=True)

    embed.add_field(name="🏦 Account balance", value=f"{acct['balance']:.2f}" if acct["balance"] is not None else "n/a", inline=True)
    bal_change = acct.get("pct_change_today")
    bal_emoji = "📈" if (bal_change or 0) > 0 else "📉" if (bal_change or 0) < 0 else "➖"
    embed.add_field(
        name="Balance change today",
        value=f"{bal_emoji} {bal_change:+.2f}%" if bal_change is not None else "no change yet today",
        inline=True,
    )
    embed.add_field(name="​", value="​", inline=True)

    if closed_today:
        lines = []
        for t in sorted(closed_today, key=lambda t: t.get("closed_at") or ""):
            icon = "✅" if t["status"] == "win" else ("❌" if t["status"] == "loss" else "🔒")
            pct = _closed_pnl_pct(t)
            amt = t.get("realized_pnl_amount")
            pct_str = f"{pct:+.2f}%" if pct is not None else "n/a"
            amt_str = f"{amt:+.2f}" if amt is not None else "n/a"
            lines.append(f"{icon} `{t['id']}` {t['ticker']:6s} {pct_str:>8s}  ({amt_str})")
        text = "\n".join(lines)
        if len(text) > 1000:
            text = text[:997] + "…"
        embed.add_field(name="Closed trades today", value=f"```{text}```", inline=False)

    if opened_today:
        lines = [
            f"{'🟩' if t['direction'] == 'bullish' else '🟥'} `{t['id']}` {t['ticker']:6s} "
            f"{'▲ LONG ' if t['direction'] == 'bullish' else '▼ SHORT'} {'⭐'*t.get('confidence_level', 0)}Lv{t['confidence_level']}"
            for t in opened_today
        ]
        text = "\n".join(lines)
        if len(text) > 1000:
            text = text[:997] + "…"
        embed.add_field(name="Opened trades today", value=f"```{text}```", inline=False)

    if not opened_today and not closed_today:
        embed.add_field(name="​", value="No trades opened or closed yet today.", inline=False)

    await ctx.send(embed=embed)
