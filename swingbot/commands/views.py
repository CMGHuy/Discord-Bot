"""
Interactive discord.ui.View subclasses for the plan-centric UX: a
per-alert action panel (chart / breakdown / watch / dismiss buttons --
PlanActionView, Tasks B9-B11) and the filterable/paginated !plans board
(PlanBoardView, Tasks B13-B14). Both follow the exact author-lock/
timeout/on_timeout-disables-children pattern TradesPaginator already
established (swingbot/commands/trades.py:83) -- the ONLY other View in
this codebase before this file existed -- so a user who has learned
"only the person who ran the command can page through it" from !trades
gets the identical mental model here.
"""
import asyncio
import os

import discord

from swingbot import config
from swingbot.core.data import get_currency_symbol, get_daily_data
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.jsonio import atomic_write_json, read_json
from swingbot.core.plan_store import PlanStore
from swingbot.core.strategy import HORIZONS

_plan_store = PlanStore()

_STARRED_PATH = os.path.join(config.DATA_DIR, "starred_plans.json")


def starred_ids() -> set:
    return set(read_json(_STARRED_PATH, []))


def star_plan(plan_id: str) -> None:
    ids = starred_ids()
    ids.add(plan_id)
    atomic_write_json(_STARRED_PATH, sorted(ids))


def unstar_plan(plan_id: str) -> None:
    ids = starred_ids()
    ids.discard(plan_id)
    atomic_write_json(_STARRED_PATH, sorted(ids))


class PlanActionView(discord.ui.View):
    """
    One action panel per posted plan: Chart (this task), Breakdown
    (Task B10), Watch/Dismiss (Task B11). `author_id=None` relaxes the
    lock to "any user may click" -- used when this view is attached to
    a scan alert (Task B12), where there is no single "author" (nobody
    ran a command; the bot posted it on its own schedule) and locking
    it to one person would make the buttons useless to everyone else
    watching the channel.
    """

    def __init__(self, plan_id: str, author_id: int | None, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.plan_id = plan_id
        self.author_id = author_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is None or interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your panel.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="📊 Chart", style=discord.ButtonStyle.primary, custom_id="plan:chart")
    async def chart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = _plan_store.get(self.plan_id)
        if plan is None:
            await interaction.followup.send("This plan no longer exists (closed/cancelled and pruned).", ephemeral=True)
            return
        try:
            df = await asyncio.to_thread(get_daily_data, plan.ticker)
        except Exception as exc:
            await interaction.followup.send(f"Could not fetch price data for {plan.ticker}: {exc}", ephemeral=True)
            return
        h = HORIZONS.get(plan.horizon_key, {})
        filename = f"{plan.ticker}_{plan.plan_id}_panel.png"
        try:
            chart_path = await asyncio.to_thread(
                generate_trade_chart,
                plan.ticker, df, plan.trigger_price, plan.stop_loss, plan.tp1,
                plan.direction, plan.strategy, h.get("label", plan.horizon_key), config.TRADE_CHART_DIR,
                filename=filename, currency_symbol=get_currency_symbol(plan.ticker, config.CURRENCY_SYMBOL),
                target2=plan.tp2, trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                horizon=h, plan_v2=plan,
            )
        except Exception as exc:
            await interaction.followup.send(f"Chart render failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(chart_path, filename=os.path.basename(chart_path)), ephemeral=True,
        )

    @discord.ui.button(label="🔍 Breakdown", style=discord.ButtonStyle.secondary, custom_id="plan:breakdown")
    async def breakdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        plan = _plan_store.get(self.plan_id)
        if plan is None:
            await interaction.response.send_message("This plan no longer exists.", ephemeral=True)
            return
        await interaction.response.send_message(embed=breakdown_embed(plan), ephemeral=True)

    @discord.ui.button(label="⭐ Watch", style=discord.ButtonStyle.secondary, custom_id="plan:watch")
    async def watch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.plan_id in starred_ids():
            unstar_plan(self.plan_id)
            await interaction.response.send_message("Unstarred.", ephemeral=True)
        else:
            star_plan(self.plan_id)
            await interaction.response.send_message("⭐ Starred — it'll sort first on `!plans` at equal follow score.", ephemeral=True)

    @discord.ui.button(label="🔕 Dismiss", style=discord.ButtonStyle.secondary, custom_id="plan:dismiss")
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)


def breakdown_embed(plan) -> discord.Embed:
    """Pure renderer (plan in, Embed out) so this is unit-testable
    without any Interaction plumbing -- the button callback below is a
    thin wrapper that just calls this and sends it ephemeral."""
    from swingbot.core.analytics.rank import follow_score, follow_breakdown
    import datetime as dt

    embed = discord.Embed(title=f"🔍 Breakdown — {plan.ticker} ({plan.tier}/{plan.badge})",
                          color=discord.Color.blurple())

    quality_lines = "\n".join(f"{label}: {pts:+d}" for label, pts in (plan.quality_breakdown or [])) or "no components recorded"
    embed.add_field(name=f"📐 Quality score ({plan.quality_score}/100)", value=quality_lines, inline=False)

    stats = plan.badge_stats or {}
    badge_lines = (
        f"Status: {stats.get('status', plan.badge)}\n"
        f"OOS N={stats.get('n', 0)}, WR {stats.get('win_rate', 0):.1f}%, "
        f"ExpR {stats.get('expectancy_r', 0):+.3f}\nWindow: {stats.get('window', 'n/a')}"
    )
    embed.add_field(name="🏷️ Badge / track record", value=badge_lines, inline=False)

    today = dt.date.today()
    score = follow_score(plan, today=today)
    breakdown = follow_breakdown(plan, today)
    breakdown_lines = "\n".join(f"{label}: +{pts:.0f}" for label, pts in breakdown) or "no components"
    embed.add_field(name=f"🧭 Follow score ({score:.0f})", value=breakdown_lines, inline=False)

    history = (plan.status_history or [])[-5:]
    if history:
        timeline_lines = []
        for i, entry in enumerate(history):
            frm = history[i - 1]["status"] if i > 0 else "—"
            timeline_lines.append(f"{entry.get('at', '?')} {frm}→{entry['status']} ({entry.get('reason') or 'n/a'})")
        timeline = "\n".join(timeline_lines)
    else:
        timeline = "No transitions recorded yet."
    embed.add_field(name="🕒 Status timeline", value=timeline[:1024], inline=False)

    return embed


class PlanBoardView(discord.ui.View):
    """
    Filterable !plans board (Task B15 supplies render_fn). Three
    dropdowns hold the current status/tier/badge filter state; every
    selection change and the Refresh button all funnel through the
    same `_apply` method, which calls `render_fn` and edits the
    message in place -- one render path regardless of which control
    triggered it, so there's no risk of the three selects drifting out
    of sync with each other.
    """

    def __init__(self, render_fn, author_id: int, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.render_fn = render_fn
        self.author_id = author_id
        self.status = "All"
        self.tier = "All"
        self.badge = "All"
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("Not your panel.", ephemeral=True)
        return False

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _apply(self, *, status=None, tier=None, badge=None, interaction: discord.Interaction = None):
        if status is not None:
            self.status = status
        if tier is not None:
            self.tier = tier
        if badge is not None:
            self.badge = badge
        content, embed = self.render_fn(self.status, self.tier, self.badge)
        if interaction is not None:
            await interaction.response.edit_message(content=content, embed=embed, view=self)
        return content, embed

    @discord.ui.select(
        placeholder="Status: All", custom_id="board:status",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "PENDING", "ACTIVE", "PARTIAL")],
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(status=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Tier: All", custom_id="board:tier",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "A", "B", "C")],
    )
    async def tier_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(tier=select.values[0], interaction=interaction)

    @discord.ui.select(
        placeholder="Badge: All", custom_id="board:badge",
        options=[discord.SelectOption(label=v, value=v) for v in ("All", "VALIDATED", "WEAK")],
    )
    async def badge_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self._apply(badge=select.values[0], interaction=interaction)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="board:refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction=interaction)
