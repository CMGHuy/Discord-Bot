"""
Discord embed/table rendering for scan_engine.py's alert pipeline -- turns
a ScanItem (or a stored trade dict) into the actual discord.Embed objects
posted to a channel, plus the two "post this to Discord" notifiers for
closed trades and near-stop/target warnings. Split out of scan_engine.py
because this is pure presentation logic (dict/object in, Embed out) with
no dependency on the scan loop's own crawl/analyze/dedup machinery --
scan_engine.py imports everything here back and calls it exactly as
before, so nothing about `!check`, the automatic scan, or the trade-detail
chart regeneration used by the admin UI changes.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from swingbot.core.market import opex
from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size, load_account_config
from swingbot.core.analytics.rank import follow_breakdown, follow_score
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core.tracking.performance import closed_pnl_pct, closed_r_multiple
from swingbot.core.backtesting.registry import decay_for
from swingbot.core.planning.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line, runner_floor
from swingbot.core.backtesting.registry import Badge
from swingbot.core.scanning import embed_theme as theme
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from . import snapshots
from .snapshots import (_load_scan_snapshots, _save_scan_snapshots,
                        _format_duration_hms, _snapshot_and_diff)
from . import requirements
from .requirements import (RequirementCheck, CONFIDENCE_COLORS,
                           CONFIDENCE_EMOJI, CONFIDENCE_ANSI, confidence_color,
                           _sources_str, _build_requirement_checks, _confidence_block)
from . import plan_table
from .plan_table import (plan_numbers_for_display, _ansi_bad,
                         _build_trade_plan_table, badge_field_for, quality_lines,
                         entry_line, leg_rows, banked_leg_pct_and_amount,
                         partial_position_line, signed_money, _v2_plan)
from . import alert_embeds
from .alert_embeds import build_embed, build_simple_alert

log = logging.getLogger("swing-bot.scan_engine")

# ── "What changed since last scan" tracking ──────────────────────────────
# A small on-disk cache of the last-posted numbers for each distinct
# ticker/horizon/direction combo, so every embed can say what actually moved
# since the last time this exact setup was shown (entry drifted, stop/target
# adjusted, confidence upgraded/downgraded) instead of only ever showing a
# fresh snapshot with no history. Deliberately its own tiny store rather than
# reusing the automatic scan's confirmation-debounce state (core/state.py)
# -- that state machine only exists for require_confirmation=True and is
# cleared/consumed once confirmed, so it can't answer "what changed" for
# `!check` (require_confirmation=False), which never touches it at all.
_SNAPSHOT_PATH = os.path.join(config.DATA_DIR, "scan_snapshots.json")


def regenerate_chart_for_trade(trade: dict) -> str | None:
    # A closed trade's chart never changes once closed (same OHLCV window,
    # same levels) -- if the deterministic file from a prior regen already
    # exists on disk, reuse it directly instead of re-fetching data and
    # re-rendering.
    deterministic_path = os.path.join(config.TRADE_CHART_DIR, f"{trade['ticker']}_{trade['id']}_view.png")
    if trade.get("status") in ("win", "loss", "closed") and os.path.exists(deterministic_path):
        return deterministic_path
    try:
        df = get_daily_data(trade["ticker"])
        h = HORIZONS.get(trade["horizon_key"], {})
        horizon_label = h.get("label", trade["horizon_key"])
        filename = f"{trade['ticker']}_{trade['id']}_view.png"
        # Re-viewing an older trade later should show where price actually
        # is *now* (today's fresh close from df) alongside the original
        # planned entry -- they'll usually differ since time has passed.
        current_price = float(df["Close"].iloc[-1])

        markers = None
        try:
            from swingbot.core.analytics.journal import JournalStore
            entry = JournalStore().get(trade["id"])
            if entry and entry.get("mfe_r") is not None:
                closed_key = trade.get("closed_at", trade["opened_at"])[:10]
                window = df.loc[trade["opened_at"][:10]:closed_key]
                if not window.empty:
                    is_bull = trade["direction"] == "bullish"
                    mfe_date = window["High"].idxmax() if is_bull else window["Low"].idxmin()
                    mae_date = window["Low"].idxmin() if is_bull else window["High"].idxmax()
                    mfe_price = float(window.loc[mfe_date, "High" if is_bull else "Low"])
                    mae_price = float(window.loc[mae_date, "Low" if is_bull else "High"])
                    markers = {
                        "mfe": (mfe_date, mfe_price), "mfe_r": entry.get("mfe_r"),
                        "mae": (mae_date, mae_price), "mae_r": entry.get("mae_r"),
                    }
        except Exception as _je:
            log.debug("Could not compute MFE/MAE markers for trade %s: %s", trade.get("id"), _je)

        return generate_trade_chart(
            trade["ticker"], df, trade["entry"], trade["stop_loss"], trade["take_profit"],
            trade["direction"], trade["strategy"], horizon_label, config.TRADE_CHART_DIR, filename=filename,
            currency_symbol=get_currency_symbol(trade["ticker"], config.CURRENCY_SYMBOL),
            target2=trade.get("target2"),
            trendline_lookback=h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
            target_sources=trade.get("target_sources"),
            stop_sources=trade.get("stop_sources"),
            horizon=h,
            market_price=current_price,
            markers=markers,
            # The line the trade was planned on and the PNG originally drew
            # (charts/trendline_fit.py) -- without this, re-viewing an older
            # trade would refit a fresh trendline against today's data while
            # the SPA (market.py) keeps reading the one stored fit, so the
            # two would show different lines for the same trade. None for
            # every trade logged before the fit was stored, or one never
            # trendline-confirmed -- generate_trade_chart falls back to its
            # own live fit exactly as it always has.
            trendline_fit=trade.get("trendline_fit"),
        )
    except Exception as e:
        log.warning("Could not regenerate chart for trade %s: %s", trade.get("id"), e)
        return None


def build_closed_trade_embed(trade: dict) -> discord.Embed:
    """Build a rich embed for a trade that just closed (win, loss, or manual close)."""
    status   = trade["status"]   # "win" | "loss" | "closed"
    won      = status == "win"
    manual   = status == "closed"

    if manual:
        outcome_word = "MANUALLY CLOSED"
        icon  = "🔒"
        color = discord.Color.from_rgb(90, 98, 117)   # grey
    elif won:
        outcome_word = "WIN ✅"
        icon  = "✅"
        color = discord.Color.green()
    else:
        outcome_word = "LOSS ❌"
        icon  = "❌"
        color = discord.Color.red()

    cur        = get_currency_symbol(trade["ticker"], config.CURRENCY_SYMBOL)
    exit_price = trade.get("exit_price")
    entry      = trade.get("entry", 0.0)
    is_bull    = trade.get("direction") == "bullish"

    # Realized P&L — only meaningful when we have an exit price. Goes
    # through closed_pnl_pct() rather than a plain (exit_price - entry)
    # calc: for a scaled-out (v2 two-leg) trade, exit_price is only the
    # runner leg's own exit (see close_plan_trade), so pricing a % off it
    # alone silently dropped the TP1 leg's contribution -- a win that gave
    # back some of its TP1 gain on the runner could show a NEGATIVE % here
    # right next to a positive Gain/Loss amount.
    pct = closed_pnl_pct(trade)
    pnl_str = f"{pct:+.2f}%" if pct is not None else "n/a"

    # R-multiple — same last-leg-only bug as pnl_str above applied here too
    # (a plain (exit_price - entry) / risk calc only ever prices the
    # runner's own leg); see closed_r_multiple's docstring.
    r = closed_r_multiple(trade)
    r_str = f"{r:+.2f}R" if r is not None else "n/a"

    title = f"{icon} {trade['ticker']} — {outcome_word}"
    embed = discord.Embed(title=title, color=color)

    # Realized $/€ gain/loss -- computed from the share count snapshotted
    # onto the trade when it was OPENED (see account.py / performance.py's
    # _settle_account_balance), not recomputed from today's account
    # balance. None for trades logged before this feature existed, or a
    # manual close (no real exit price to settle against).
    amount = trade.get("realized_pnl_amount")
    amount_str = f"{amount:+.2f}{cur}" if amount is not None else "n/a"

    # Top summary line
    result_parts = [outcome_word, f"P&L: {pnl_str}", f"Gain/Loss: {amount_str}", f"R: {r_str}"]
    embed.add_field(name="Result", value=" · ".join(result_parts), inline=False)

    # Trade plan
    embed.add_field(name="Setup",      value=f"{trade.get('strategy','?')} ({trade.get('horizon_key','?')})", inline=True)
    embed.add_field(name="Direction",  value="LONG" if is_bull else "SHORT", inline=True)
    embed.add_field(name="Confidence", value=f"{trade.get('confidence_label','?')} (Lv{trade.get('confidence_level','?')})", inline=True)
    embed.add_field(name="Entry",  value=f"{cur}{entry:.2f}", inline=True)
    if exit_price is not None:
        embed.add_field(name="Exit", value=f"{cur}{exit_price:.2f}", inline=True)
    else:
        embed.add_field(name="Exit", value="—  (manually closed, no price recorded)", inline=True)
    embed.add_field(name="Stop loss",  value=f"{cur}{trade.get('stop_loss', 0):.2f}", inline=True)
    embed.add_field(name="Target",     value=f"{cur}{trade.get('take_profit', 0):.2f}", inline=True)
    if trade.get("risk_reward_ratio"):
        embed.add_field(name="R:R at open", value=f"{trade['risk_reward_ratio']}:1", inline=True)

    # Holding period
    try:
        opened  = datetime.fromisoformat(trade["opened_at"])
        closed_ = datetime.fromisoformat(trade["closed_at"])
        days    = max(0, (closed_ - opened).days)
        embed.add_field(name="Held", value=f"{days}d  ({trade['opened_at'][:10]} → {trade['closed_at'][:10]})", inline=False)
    except Exception:
        pass

    # Lesson learned / original explanation
    explanation = trade.get("explanation") or ""
    if explanation.strip():
        # Discord field values max 1024 chars
        lesson = explanation.strip()
        if len(lesson) > 1000:
            lesson = lesson[:997] + "…"
        embed.add_field(name="📖 Why this trade was opened", value=lesson, inline=False)

    # What happened -- a narrative summary of the trade's actual outcome
    # (how it closed, how long it took, and the real PnL), placed right
    # under "why this trade was opened" so the two read together as a
    # before/after: why we got in, then what actually happened. The
    # "Result" line up top is a compact stat strip for scanning several
    # trades at once; this is the same numbers spelled out in one sentence
    # for whoever's reading just this one trade.
    close_reason = trade.get("close_reason", "")
    reason_phrases = {
        "manual": "closed manually",
        "auto (price monitor)": "closed automatically after price hit its stop-loss or take-profit",
        "auto (near-TP stall)": "closed automatically after stalling near its take-profit without quite reaching it",
        "auto (near-TP timeout)": "closed automatically after running out of time while sitting near its take-profit",
    }
    reason_phrase = reason_phrases.get(close_reason, close_reason or "closed")
    dir_word = "long" if is_bull else "short"
    held_phrase = ""
    try:
        opened_dt = datetime.fromisoformat(trade["opened_at"])
        closed_dt = datetime.fromisoformat(trade["closed_at"])
        held_phrase = f" after being held {_format_duration_hms(max(0.0, (closed_dt - opened_dt).total_seconds()))}"
    except Exception:
        pass
    exit_phrase = f"{cur}{exit_price:.2f}" if exit_price is not None else "an unrecorded price"
    what_happened = (
        f"This {dir_word} trade opened at {cur}{entry:.2f} and was {reason_phrase}{held_phrase}, "
        f"exiting at {exit_phrase} -- {pnl_str} ({amount_str}, {r_str})."
    )
    embed.add_field(name="📋 What happened", value=what_happened, inline=False)

    if close_reason:
        embed.add_field(name="Close reason", value=close_reason, inline=False)

    id_suffix = " · Plan Engine v2" if (trade.get("plan_id") or trade.get("legs")) else ""
    embed.add_field(name="Trade ID", value=f"`{trade['id']}`{id_suffix}", inline=False)
    theme.apply_footer(embed, plan_id=trade.get("plan_id"))
    return embed


async def notify_closed_trades(bot, newly_closed: list):
    """Send a notification for every newly-closed trade (win, loss, or manual close)."""
    if not newly_closed:
        return
    if not config.DISCORD_CHANNEL_TRADES_HISTORY_ID:
        log.warning(
            "notify_closed_trades: DISCORD_CHANNEL_TRADES_HISTORY_ID is not set in .env — "
            "cannot post closed-trade notifications. Set it in Settings > Discord Connection."
        )
        return
    channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
        except Exception as _ce:
            log.warning("Could not resolve closed-trades channel %s: %s", config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce)
            return
    for trade in newly_closed:
        status = trade.get("status", "")
        if status not in ("win", "loss", "closed"):
            continue   # skip anything unexpected (still-open, etc.)
        try:
            embed = build_closed_trade_embed(trade)
            # Compact header line so the embed title stands out
            header_map = {"win": "✅ WIN", "loss": "❌ LOSS", "closed": "🔒 CLOSED"}
            header = f"{header_map.get(status, status.upper())} — **{trade['ticker']}**"
            await channel.send(content=header, embed=embed)
        except Exception as e:
            log.warning("Could not post closed-trade notification for %s: %s", trade.get("id"), e)


def build_near_close_embed(warning: dict) -> discord.Embed:
    t = warning["trade"]
    is_sl = warning["near_which"] == "stop-loss"
    color = discord.Color.red() if is_sl else discord.Color.green()
    approaching_word = "STOP-LOSS" if is_sl else "TAKE-PROFIT"
    cur = get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL)
    title = f"⚠️ APPROACHING {approaching_word} — {t['ticker']}"
    embed = discord.Embed(title=title, color=color)
    embed.add_field(
        name="Approaching",
        value=f"**{approaching_word}** ({warning['sl_dist_pct' if is_sl else 'tp_dist_pct']:.1f}% away)",
        inline=False,
    )
    embed.add_field(name="Setup", value=f"{t['strategy']} ({t['horizon_key']})", inline=True)
    embed.add_field(name="Direction", value="LONG" if t["direction"] == "bullish" else "SHORT", inline=True)
    embed.add_field(name="Confidence", value=f"{t['confidence_label']} (Lv{t['confidence_level']})", inline=True)
    embed.add_field(name="Entry", value=f"{cur}{t['entry']:.2f}", inline=True)
    embed.add_field(name="Current price", value=f"{cur}{warning['current_price']:.2f}", inline=True)
    embed.add_field(name="Stop-loss", value=f"{cur}{t['stop_loss']:.2f} ({warning['sl_dist_pct']:.1f}% away)", inline=True)
    embed.add_field(name="Recommended TP", value=f"{cur}{t['take_profit']:.2f} ({warning['tp_dist_pct']:.1f}% away)", inline=True)
    embed.add_field(name="Trade ID", value=f"`{t['id']}` -- use !trade {t['id']} for full detail", inline=False)
    theme.apply_footer(embed, plan_id=t.get("plan_id"))
    return embed


async def notify_near_close(bot, warnings: list):
    if not warnings or not config.DISCORD_CHANNEL_TRADES_HISTORY_ID:
        return
    channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
        except Exception as _ce:
            log.warning("Could not resolve closed-trades channel %s: %s", config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce)
            return
    for warning in warnings:
        try:
            await channel.send(embed=build_near_close_embed(warning))
        except Exception as e:
            log.warning("Could not post near-close warning for %s: %s", warning["trade"].get("id"), e)


_EVENT_STYLE = {
    "filled":                ("🎯 ENTRY TRIGGERED — {ticker}", discord.Color.blue()),
    "cancelled_expired":     ("⏱ Plan expired — {ticker}", discord.Color.dark_grey()),
    "cancelled_invalidated": ("❌ Plan invalidated — {ticker}", discord.Color.dark_red()),
    "be_moved":              ("🛡 Stop moved to break-even — {ticker}", discord.Color.teal()),
    "tp1_partial":           ("💰 TP1 banked — {ticker}", discord.Color.gold()),
}
_CLOSE_STYLE = {
    "loss":            ("🔴 Stopped out — {ticker}", discord.Color.red()),
    "scratch":         ("⚪ Scratched at break-even — {ticker}", discord.Color.light_grey()),
    "tp1_runner_be":   ("🟢 Win — runner closed at its floor — {ticker}", discord.Color.green()),
    "tp1_runner_tp2":  ("🟢🟢 Win — runner hit TP2 — {ticker}", discord.Color.green()),
    "tp1_runner_trail": ("🟢 Win — trail locked profit — {ticker}", discord.Color.green()),
}


def build_plan_event_embed(plan, event) -> discord.Embed:
    """Per-transition Discord embed for the v2 plan lifecycle (Task 72)."""
    if event.transition == "closed":
        template, color = _CLOSE_STYLE.get(
            event.detail.get("reason"),
            ("Plan closed — {ticker}", discord.Color.light_grey()))
    else:
        template, color = _EVENT_STYLE.get(
            event.transition, ("Plan update — {ticker}", discord.Color.light_grey()))
    embed = discord.Embed(title=template.format(ticker=plan.ticker), color=color)
    embed.add_field(name="Plan (v2)", value=(
        f"{plan.strategy} · {plan.horizon_key} · {plan.direction} · "
        f"{'✅' if plan.badge == 'VALIDATED' else '⚠️'} {plan.badge}"), inline=False)
    d = event.detail
    if event.transition == "filled":
        embed.add_field(name="Entry", value=f"{d['entry_price']:.2f}")
        embed.add_field(name="Stop", value=f"{plan.stop_loss:.2f}")
        embed.add_field(name="TP1", value=f"{plan.tp1:.2f}")
    elif event.transition == "be_moved":
        embed.add_field(name="New stop", value=f"{d['working_stop']:.2f} (entry)")
    elif event.transition == "tp1_partial":
        pct, amount = banked_leg_pct_and_amount(plan, d["exit_price"], d["fraction"])
        cur = config.CURRENCY_SYMBOL
        banked = (f"{d['fraction']:.0%} @ {d['exit_price']:.2f} "
                 f"({d['r']:+.2f}R")
        if pct is not None:
            banked += f" · {pct:+.1f}%"
        if amount is not None:
            banked += f" · {signed_money(amount, cur)}"
        banked += ")"
        embed.add_field(name="Banked", value=banked)
        embed.add_field(name="Partial position", value=partial_position_line(plan),
                        inline=False)
    elif event.transition == "closed":
        embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")
    embed.set_footer(text=f"v2 plan {plan.plan_id[:8]}")
    return embed


async def notify_plan_events(bot, events):
    """Route fills to the alerts channel, everything else to history --
    same split notify_closed_trades already uses."""
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.infra.silent_channel import silence
    store = PlanStore()
    for event in events:
        plan = store.get(event.plan_id)
        if plan is None:
            continue
        is_fill = event.transition == "filled"
        channel_id = (config.DISCORD_CHANNEL_TRADES_ID
                      if is_fill
                      else config.DISCORD_CHANNEL_TRADES_HISTORY_ID)
        channel = bot.get_channel(int(channel_id)) if channel_id else None
        if is_fill:
            # Alerts channel -> never notifies (silent_channel.py). The
            # history channel keeps its notification: a closed trade is a
            # result you want pushed, not something you'll scroll back for.
            channel = silence(channel)
        if channel is not None:
            await channel.send(embed=build_plan_event_embed(plan, event))
