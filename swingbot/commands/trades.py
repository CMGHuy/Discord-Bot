"""!trades, !trade, !tradecharts, !performance, !pnl, !summary, and their slash twins (v153)."""
import asyncio
import os
from datetime import datetime, timezone

import discord
from discord import app_commands

from swingbot import config
from swingbot.core.planning import account as account_module
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.marketdata.data import get_currency_symbol
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import TRADE_FILTER_CHOICES
from swingbot.core.tracking.risk_metrics import compute_risk_metrics
from swingbot.core.tracking.performance import closed_pnl_pct
from swingbot.core.market.session import BERLIN_TZ as _BERLIN_TZ

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
TRADE_STATUSES = ("open", "win", "loss", "all")
STATUS_ERROR = "Status must be one of: open, win, loss, all"


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


async def handle_trades(reply, status: str = "all", per_page: int = DEFAULT_PER_PAGE) -> None:
    """
    Shows every logged trade -- any confidence level, any status by
    default -- sorted highest confidence first, paginated with Prev/Next
    buttons. `per_page` sets how many rows show per page (1-25).
    """
    if status not in TRADE_STATUSES:
        await reply.send_error(STATUS_ERROR)
        return
    per_page = max(MIN_PER_PAGE, min(per_page, MAX_PER_PAGE))
    await reply.defer()

    trades = trade_log.get_trades(status=status, limit=None, sort_by="confidence")
    if not trades:
        await reply.send(f"No trades found for status='{status}'.")
        return

    view = TradesPaginator(trades, f"**Trades ({status}, sorted by confidence high→low)**", per_page,
                           reply.author.id)
    view.message = await reply.send(view.render(), view=view)


async def handle_trades_clear(reply) -> None:
    """Clear all currently OPEN/active trades. Closed trade history is kept."""
    count = trade_log.clear_open()
    await reply.send(f"Cleared {count} open trade(s). Closed win/loss history was not touched.")


async def handle_trades_clear_history(reply) -> None:
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    count = trade_log.clear_history()
    await reply.send(f"Cleared {count} closed trade record(s). Open trades were not touched.")


@bot.group(name="trades", invoke_without_command=True)
async def trades_cmd(ctx, status: str = "all", per_page: int = DEFAULT_PER_PAGE):
    """
    Shows every logged trade -- any confidence level, any status by
    default -- sorted highest confidence first, paginated with Prev/Next
    buttons. `per_page` sets how many rows show per page (1-25).
    """
    reply = CtxReply(ctx)
    await handle_trades(reply, status, per_page)
    await send_prefix_tip(ctx, reply)


@trades_cmd.group(name="clear", invoke_without_command=True)
async def trades_clear(ctx):
    """Clear all currently OPEN/active trades. Closed trade history is kept.
    Use `!trades clear history` to remove closed trade records instead."""
    reply = CtxReply(ctx)
    await handle_trades_clear(reply)
    await send_prefix_tip(ctx, reply)


@trades_clear.command(name="history")
async def trades_clear_history(ctx):
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    reply = CtxReply(ctx)
    await handle_trades_clear_history(reply)
    await send_prefix_tip(ctx, reply)


_OPEN_STYLE = ("🔵", "scratch", "OPEN")
_CLOSED_STYLES = {
    "win": (kinds.outcome_mark("win"), "win", f"WIN {kinds.outcome_mark('win')}"),
    "loss": (kinds.outcome_mark("loss"), "loss", f"LOSS {kinds.outcome_mark('loss')}"),
}
_MANUAL_STYLE = (kinds.outcome_mark("manual"), "scratch", "MANUALLY CLOSED")
#: trade status -> the registry outcome whose mark the !today list shows.
_STATUS_OUTCOME = {"win": "win", "loss": "loss"}


def _status_style(status: str) -> tuple[str, str, str]:
    """(title icon, accent outcome, status word) for !trade. Closed-trade marks
    come from the v110 registry so they match the pushed RESULT messages."""
    if status == "open":
        return _OPEN_STYLE
    return _CLOSED_STYLES.get(status, _MANUAL_STYLE)


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

    icon, accent_outcome, status_word = _status_style(match["status"])
    accent = ui.accent_for_outcome(accent_outcome)

    embed = discord.Embed(title=f"{icon} Trade {match['id']} — {match['ticker']}")

    embed.add_field(name="Status", value=status_word, inline=True)
    embed.add_field(name="Direction", value=direction_word, inline=True)
    embed.add_field(
        name="Confidence",
        value=ui.confidence_label(match.get("confidence_level"), None),
        inline=True,
    )

    embed.add_field(name="Strategy", value=method, inline=True)
    embed.add_field(name="Horizon", value=match["horizon_key"], inline=True)
    if match.get("risk_reward_ratio"):
        embed.add_field(name="Reward:Risk", value=f"{match['risk_reward_ratio']}:1", inline=True)
    else:
        embed.add_field(name="\u200b", value="\u200b", inline=True)   # keeps the 3-column grid even

    reward_pct = abs(match["take_profit"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
    embed.add_field(name="Entry", value=ui.fmt_price(match["entry"], cur), inline=True)
    embed.add_field(name="Stop-loss", value=ui.fmt_price(match["stop_loss"], cur), inline=True)
    embed.add_field(
        name="Target 1",
        value=f"{ui.fmt_price(match['take_profit'], cur)} ({ui.fmt_pct(reward_pct)})",
        inline=True,
    )

    if match.get("target2"):
        t2_pct = abs(match["target2"] - match["entry"]) / match["entry"] * 100 if match["entry"] else 0.0
        embed.add_field(
            name="Target 2 (stretch)",
            value=f"{ui.fmt_price(match['target2'], cur)} ({ui.fmt_pct(t2_pct)})",
            inline=True,
        )

    embed.add_field(name="Opened", value=match["opened_at"][:16].replace("T", " ") + " UTC", inline=True)

    if not is_open:
        exit_price = match.get("exit_price")
        embed.add_field(
            name="Closed",
            value=(match.get("closed_at") or "n/a")[:16].replace("T", " ") + " UTC",
            inline=True,
        )
        embed.add_field(
            name="Exit price",
            value=ui.fmt_price(exit_price, cur) if exit_price else "n/a",
            inline=True,
        )

        # Realized P&L% + $/€ gain-loss -- the actual currency amount from
        # the position size snapshotted when this trade was opened (see
        # account.py / performance.py's _settle_account_balance). "n/a" for
        # a manual close (no exit price) or a trade logged before sizing
        # snapshots existed.
        pnl_pct = closed_pnl_pct(match)
        if pnl_pct is not None:
            embed.add_field(name="Realized P&L", value=ui.fmt_pct(pnl_pct), inline=True)
        else:
            embed.add_field(name="Realized P&L", value="n/a", inline=True)

        amount = match.get("realized_pnl_amount")
        embed.add_field(name="Gain/Loss", value=f"{amount:+.2f}{cur}" if amount is not None else "n/a", inline=True)

    if match.get("close_reason"):
        embed.add_field(name="Close reason", value=match["close_reason"], inline=False)

    trade_id = match["id"]
    if match.get("plan_id") or match.get("legs"):
        trade_id += " · Plan Engine v2"
    embed.add_field(name="Trade ID", value=trade_id, inline=False)
    ui.apply_chrome(embed, accent=accent, plan_id=match.get("plan_id"))
    return embed


async def handle_trade_show(reply, trade_id: str) -> None:
    match = trade_log.get_trade_by_id(trade_id)
    if not match:
        await reply.send_error(f"No trade found with id `{trade_id}`. Use `!trades` to list recent ones.")
        return
    await reply.defer()

    embed = _build_trade_detail_embed(match)
    chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, match)
    if chart_path:
        filename = os.path.basename(chart_path)
        embed.set_image(url=f"attachment://{filename}")
        await reply.send(embed=embed, file=discord.File(chart_path, filename=filename))
    else:
        embed.add_field(name="⚠️ Chart", value="Could not generate a chart for this trade right now.", inline=False)
        await reply.send(embed=embed)


async def handle_trade_delete(reply, trade_id: str) -> None:
    deleted = trade_log.delete_trade(trade_id)
    if not deleted:
        await reply.send_error(f"No trade found with id `{trade_id}`.")
        return
    await reply.send(f"Deleted trade `{trade_id}`.")


async def handle_tradecharts(reply, status: str = "open", limit: int = 5) -> None:
    if status not in TRADE_STATUSES:
        await reply.send_error(STATUS_ERROR)
        return
    limit = min(limit, 10)
    trades = trade_log.get_trades(status=status, limit=limit)
    if not trades:
        await reply.send(f"No trades found for status='{status}'.")
        return

    await reply.send(f"Generating charts for {len(trades)} trade(s)…")
    for t in trades:
        chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, t)
        caption = f"**{t['id']}** {t['ticker']} — {t['strategy']} ({t['horizon_key']}), {t['direction']}, status: {t['status']}"
        if chart_path:
            await reply.send(caption, file=discord.File(chart_path, filename=os.path.basename(chart_path)))
        else:
            await reply.send(caption + " (chart unavailable)")


@bot.group(name="trade", invoke_without_command=True)
async def trade_cmd(ctx, trade_id: str):
    reply = CtxReply(ctx)
    await handle_trade_show(reply, trade_id)
    await send_prefix_tip(ctx, reply)


@trade_cmd.command(name="delete")
async def trade_delete(ctx, trade_id: str):
    reply = CtxReply(ctx)
    await handle_trade_delete(reply, trade_id)
    await send_prefix_tip(ctx, reply)


@bot.command(name="tradecharts")
async def tradecharts_cmd(ctx, status: str = "open", limit: int = 5):
    reply = CtxReply(ctx)
    await handle_tradecharts(reply, status, limit)
    await send_prefix_tip(ctx, reply)


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


def _level_performance_lines(level: int, all_trades: list) -> list[str]:
    stats = trade_log.get_stats(level)
    wr = f"{stats['win_rate']:.0f}%" if stats["win_rate"] is not None else "n/a"
    lines = [
        f"**Confidence Level {level}** — {stats['total']} trades logged "
        f"({stats['open']} open, {stats['closed']} closed)",
        f"Win rate: {wr} ({stats['wins']}W / {stats['losses']}L)",
    ]
    closed_at_level = [t for t in all_trades if t["confidence_level"] == level and t["status"] in ("win", "loss")]
    _append_risk_metrics_lines(lines, closed_at_level)
    return lines


def _overall_performance_lines(all_trades: list) -> list[str]:
    lines = ["**Performance by confidence level:**"]
    by_level = trade_log.get_stats_by_confidence()
    for lvl in range(1, 6):
        s = by_level[lvl]
        wr = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "n/a"
        lines.append(f"Lv{lvl}: {wr} win rate — {s['wins']}W/{s['losses']}L closed, {s['open']} open ({s['total']} total)")
    overall = trade_log.get_stats(ledger="main")
    wr_overall = f"{overall['win_rate']:.0f}%" if overall["win_rate"] is not None else "n/a"
    lines.append(f"\n**Overall:** {wr_overall} win rate — {overall['wins']}W/{overall['losses']}L closed, {overall['open']} open")

    closed_overall = [t for t in all_trades if t["status"] in ("win", "loss")]
    _append_risk_metrics_lines(lines, closed_overall)
    weak = trade_log.weak_summary()
    lines.append(f"\n**WEAK ledger (separate):** {weak['wins']}W/{weak['losses']}L, "
                 f"N {weak['n']}, P&L {weak['total_pnl']:+.2f}")
    return lines


async def handle_performance(reply, level: int | None = None) -> None:
    if level is not None and level not in range(1, 6):
        await reply.send_error("Level must be 1-5.")
        return
    await reply.defer()
    all_trades = trade_log.get_trades(status="all", limit=None, ledger="main")
    if level is None:
        lines = _overall_performance_lines(all_trades)
    else:
        lines = _level_performance_lines(level, all_trades)
    await reply.send("\n".join(lines))


@bot.command(name="performance")
async def performance_cmd(ctx, level: int = None):
    reply = CtxReply(ctx)
    await handle_performance(reply, level)
    await send_prefix_tip(ctx, reply)


def _pnl_lines(rows: list) -> list[str]:
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
    return lines


async def handle_pnl(reply) -> None:
    await reply.send("Fetching current prices for all open trades…")
    rows = await asyncio.to_thread(scan_engine.get_all_unrealized_pnl)
    if not rows:
        await reply.send("No open trades right now.")
        return
    await reply.send_chunks("\n".join(_pnl_lines(rows)))


@bot.command(name="pnl")
async def pnl_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_pnl(reply)
    await send_prefix_tip(ctx, reply)


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
    return dt.astimezone(_BERLIN_TZ).date()


_SPACER = "​"


def _sign_mark(value, positive: str, negative: str, zero: str) -> str:
    """`positive` above 0, `negative` below, `zero` at 0 or None."""
    v = value or 0
    if v > 0:
        return positive
    if v < 0:
        return negative
    return zero


def _clip_field(text: str) -> str:
    return text[:997] + "…" if len(text) > 1000 else text


def _add_spacer(embed: discord.Embed) -> None:
    embed.add_field(name=_SPACER, value=_SPACER, inline=True)   # keeps the 3-column grid even


def _summary_day(all_trades: list, today) -> dict:
    opened = [t for t in all_trades if _berlin_date(t.get("opened_at")) == today]
    closed = [
        t for t in all_trades
        if t["status"] in ("win", "loss", "closed") and _berlin_date(t.get("closed_at")) == today
    ]
    return {
        "opened": opened,
        "closed": closed,
        "wins": [t for t in closed if t["status"] == "win"],
        "losses": [t for t in closed if t["status"] == "loss"],
        "manual": [t for t in closed if t["status"] == "closed"],
    }


def _summary_money(closed: list) -> tuple:
    """(net realized amount, average realized P&L %), each None when nothing counts."""
    amounts = [t["realized_pnl_amount"] for t in closed if t.get("realized_pnl_amount") is not None]
    net_amount = sum(amounts) if amounts else None
    pnl_pcts = [p for t in closed if (p := closed_pnl_pct(t)) is not None]
    avg_pnl_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else None
    return net_amount, avg_pnl_pct


def _add_count_fields(embed: discord.Embed, day: dict, open_count: int) -> None:
    embed.add_field(name="🆕 Opened today", value=str(len(day["opened"])), inline=True)
    embed.add_field(name="🏁 Closed today", value=str(len(day["closed"])), inline=True)
    embed.add_field(name="📂 Still open", value=str(open_count), inline=True)

    embed.add_field(name="Wins", value=f"✅ {len(day['wins'])}", inline=True)
    embed.add_field(name="Losses", value=f"❌ {len(day['losses'])}", inline=True)
    if day["manual"]:
        embed.add_field(name="Manually closed", value=f"🔒 {len(day['manual'])}", inline=True)
    else:
        _add_spacer(embed)


def _add_money_fields(embed: discord.Embed, avg_pnl_pct, net_amount) -> None:
    pnl_emoji = _sign_mark(avg_pnl_pct, "🟢", "🔴", "⚪")
    net_emoji = _sign_mark(net_amount, "🟢", "🔴", "⚪")
    embed.add_field(name="📊 Avg realized P&L", value=f"{pnl_emoji} {ui.fmt_pct(avg_pnl_pct)}" if avg_pnl_pct is not None else "n/a", inline=True)
    embed.add_field(name="💰 Net gain/loss", value=f"{net_emoji} {net_amount:+.2f}" if net_amount is not None else "n/a", inline=True)
    _add_spacer(embed)


def _add_balance_fields(embed: discord.Embed, acct: dict) -> None:
    embed.add_field(name="🏦 Account balance", value=ui.fmt_price(acct["balance"]) if acct["balance"] is not None else "n/a", inline=True)
    bal_change = acct.get("pct_change_today")
    bal_emoji = _sign_mark(bal_change, "📈", "📉", "➖")
    embed.add_field(
        name="Balance change today",
        value=f"{bal_emoji} {ui.fmt_pct(bal_change)}" if bal_change is not None else "no change yet today",
        inline=True,
    )
    _add_spacer(embed)


def _closed_trade_line(t: dict) -> str:
    icon = kinds.outcome_mark(_STATUS_OUTCOME.get(t["status"], "manual"))
    pct = closed_pnl_pct(t)
    amt = t.get("realized_pnl_amount")
    pct_str = ui.fmt_pct(pct) if pct is not None else "n/a"
    amt_str = f"{amt:+.2f}" if amt is not None else "n/a"
    return f"{icon} `{t['id']}` {t['ticker']:6s} {pct_str:>8s}  ({amt_str})"


def _opened_trade_line(t: dict) -> str:
    return (
        f"{'🟩' if t['direction'] == 'bullish' else '🟥'} `{t['id']}` {t['ticker']:6s} "
        f"{ui.direction_glyph(t['direction'])} {'LONG' if t['direction'] == 'bullish' else 'SHORT'} "
        f"{ui.confidence_label(t.get('confidence_level'), None)}"
    )


def _add_trade_lists(embed: discord.Embed, day: dict) -> None:
    if day["closed"]:
        ordered = sorted(day["closed"], key=lambda t: t.get("closed_at") or "")
        text = _clip_field("\n".join(_closed_trade_line(t) for t in ordered))
        embed.add_field(name="Closed trades today", value=f"```{text}```", inline=False)
    if day["opened"]:
        text = _clip_field("\n".join(_opened_trade_line(t) for t in day["opened"]))
        embed.add_field(name="Opened trades today", value=f"```{text}```", inline=False)
    if not day["opened"] and not day["closed"]:
        embed.add_field(name=_SPACER, value="No trades opened or closed yet today.", inline=False)


def _summary_embed(today, all_trades: list, open_count: int, acct: dict) -> discord.Embed:
    day = _summary_day(all_trades, today)
    net_amount, avg_pnl_pct = _summary_money(day["closed"])
    embed = discord.Embed(title=f"📋 Today's Summary — {today.isoformat()} (Berlin)")
    _add_count_fields(embed, day, open_count)
    _add_money_fields(embed, avg_pnl_pct, net_amount)
    _add_balance_fields(embed, acct)
    _add_trade_lists(embed, day)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome(_sign_mark(net_amount, "win", "loss", "scratch")))
    return embed


async def handle_summary(reply) -> None:
    """
    Everything that happened TODAY (Europe/Berlin calendar day) in one
    place: trades opened, trades closed (win/loss, %, and $/€), and the
    account balance's own movement today -- a quick end-of-day (or
    check-in-anytime) status read without digging through !trades or the
    admin Performance page.
    """
    today = datetime.now(_BERLIN_TZ).date()
    all_trades = trade_log.get_trades(status="all", limit=None, ledger="main")
    acct = account_module.get_daily_summary()
    open_count = trade_log.get_stats()["open"]
    await reply.send(embed=_summary_embed(today, all_trades, open_count, acct))


@bot.command(name="summary")
async def summary_cmd(ctx):
    """Everything that happened today (Europe/Berlin calendar day) in one place."""
    reply = CtxReply(ctx)
    await handle_summary(reply)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (v153). /trades moved from slash.py with its decorators
# verbatim. A command cannot also be a group, so `!trades clear` and
# `!trades clear history` become the top-level /trades-clear and
# /trades-clear-history; `!trade` alone maps to /trade show.
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
    await handle_trades(InteractionReply(interaction), filter.value if filter else "all", per_page)


@bot.tree.command(name="trades-clear", description="Clear all open trades (closed trade history is kept)")
async def slash_trades_clear(interaction: discord.Interaction):
    await handle_trades_clear(InteractionReply(interaction))


@bot.tree.command(name="trades-clear-history", description="Clear all closed trade records (open trades are kept)")
async def slash_trades_clear_history(interaction: discord.Interaction):
    await handle_trades_clear_history(InteractionReply(interaction))


trade_group = app_commands.Group(name="trade", description="Show or delete one logged trade")


@trade_group.command(name="show", description="Full detail and chart for one trade")
@app_commands.describe(trade_id="Trade ID, as listed by /trades")
async def slash_trade_show(interaction: discord.Interaction, trade_id: str):
    await handle_trade_show(InteractionReply(interaction), trade_id)


@trade_group.command(name="delete", description="Delete one logged trade")
@app_commands.describe(trade_id="Trade ID, as listed by /trades")
async def slash_trade_delete(interaction: discord.Interaction, trade_id: str):
    await handle_trade_delete(InteractionReply(interaction), trade_id)


bot.tree.add_command(trade_group)


@bot.tree.command(name="tradecharts", description="Chart the most recent trades of one status")
@app_commands.describe(
    status="Trade status (default: open)",
    limit="How many trades to chart (max 10, default 5)",
)
@app_commands.choices(status=TRADE_FILTER_CHOICES)
async def slash_tradecharts(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] = None,
    limit: int = 5,
):
    await handle_tradecharts(InteractionReply(interaction), status.value if status else "open", limit)


@bot.tree.command(name="performance", description="Win rate + risk-adjusted stats for closed trades")
@app_commands.describe(level="Filter to a specific confidence level (1-5), or omit for overall")
async def slash_performance(
    interaction: discord.Interaction,
    level: int = None,
):
    await handle_performance(InteractionReply(interaction), level)


@bot.tree.command(name="pnl", description="Current unrealized P&L for every open trade")
async def slash_pnl(interaction: discord.Interaction):
    await handle_pnl(InteractionReply(interaction))


@bot.tree.command(name="summary", description="Today's trades opened and closed, P&L and balance change (Berlin day)")
async def slash_summary(interaction: discord.Interaction):
    await handle_summary(InteractionReply(interaction))
