"""!trades, !trade, !tradecharts, !performance, !pnl."""
import asyncio
import os

import discord

from swingbot import config
from swingbot.core import scan_engine
from swingbot.bot_core import bot
from swingbot.core.risk_metrics import compute_risk_metrics

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


def format_trades_table(trades, header: str) -> str:
    lines = [header, "```"]
    lines.append(f"{'ID':8s} {'Ticker':6s} {'Method':10s} {'H':3s} {'Dir':5s} {'Conf':5s} {'Entry':>9s} {'SL':>9s} {'TP':>9s} {'Status':6s}")
    for t in trades:
        # Use the actual confirming method (target_sources/stop_sources priority
        # ranking) instead of the static "S/R Confluence" t["strategy"] default.
        method = _primary_source_label(t)
        method_short = method[:10]
        dir_short = "LONG" if t['direction'] == "bullish" else "SHORT"
        lines.append(
            f"{t['id']:8s} {t['ticker']:6s} {method_short:10s} {t['horizon_key']:3s} {dir_short:5s} "
            f"{'L'+str(t['confidence_level']):5s} {t['entry']:>9.2f} {t['stop_loss']:>9.2f} {t['take_profit']:>9.2f} {t['status']:6s}"
        )
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


@bot.group(name="trade", invoke_without_command=True)
async def trade_cmd(ctx, trade_id: str):
    match = trade_log.get_trade_by_id(trade_id)
    if not match:
        await ctx.send(f"No trade found with id `{trade_id}`. Use `!trades` to list recent ones.")
        return
    direction_word = "LONG (buy)" if match["direction"] == "bullish" else "SHORT (sell)"
    reward_pct = abs(match["take_profit"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
    lines = [
        f"**Trade {match['id']}** — {match['ticker']}",
        f"Strategy: {match['strategy']} ({match['horizon_key']})",
        f"Direction: {direction_word}, Confidence: {match['confidence_label']} (Lv{match['confidence_level']})",
        f"Entry: {match['entry']} | Stop-loss: {match['stop_loss']} | Target 1: {match['take_profit']} (+{reward_pct:.1f}% target)",
    ]
    if match.get("target2"):
        t2_pct = abs(match["target2"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
        lines.append(f"Target 2 (stretch): {match['target2']} (+{t2_pct:.1f}%)")
    lines.append(f"Opened: {match['opened_at']}")
    lines.append(f"Status: {match['status']}")
    if match["status"] != "open":
        lines.append(f"Closed: {match['closed_at']} @ {match['exit_price']}")

    chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, match)
    if chart_path:
        await ctx.send("\n".join(lines), file=discord.File(chart_path, filename=os.path.basename(chart_path)))
    else:
        await ctx.send("\n".join(lines) + "\n(Could not generate a chart for this trade right now.)")


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
