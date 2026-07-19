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
from swingbot.core.plan_store import PlanStore
from swingbot.core.strategy import HORIZONS

_plan_store = PlanStore()


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
