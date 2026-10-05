"""Discord presentation for trade and plan lifecycle events."""
import logging
import os
import time
from datetime import datetime

import discord

from swingbot import config
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core import presentation as ui
from swingbot.core.infra.posted_log import log_posted
from swingbot.core.presentation import kinds
from swingbot.core.presentation.instructions import total_r
from swingbot.core.presentation.kinds import Kind
from swingbot.core.tracking.performance import closed_pnl_pct, closed_r_multiple
from .snapshots import _format_duration_hms
from .alert_embeds import strategy_plan_line
from .execution_embeds import plan_levels_block, plan_result_block
from .plan_table import banked_leg_pct_and_amount, partial_position_line, signed_money

log = logging.getLogger(__name__)
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
        log.warning("Could not regenerate chart for trade %s: %s", trade.get("id"), e, exc_info=True)
        return None


_STATUS_OUTCOME = {"win": "win", "loss": "loss", "closed": "manual"}
_RESULT_FIELD_WORD = {
    "win": f"WIN {kinds.outcome_mark('win')}",
    "loss": f"LOSS {kinds.outcome_mark('loss')}",
    "manual": "MANUALLY CLOSED",
}


def build_closed_trade_embed(trade: dict) -> discord.Embed:
    """Build a rich embed for a trade that just closed (win, loss, or manual close)."""
    # "win" | "loss" | "closed" (manual) -> the registry's outcome (v110).
    outcome = _STATUS_OUTCOME.get(trade["status"], "manual")
    outcome_word = _RESULT_FIELD_WORD[outcome]

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
    pnl_str = ui.fmt_pct(pct)

    # R-multiple — same last-leg-only bug as pnl_str above applied here too
    # (a plain (exit_price - entry) / risk calc only ever prices the
    # runner's own leg); see closed_r_multiple's docstring.
    r = closed_r_multiple(trade)
    r_str = ui.fmt_r(r)

    detail = kinds.outcome_detail(outcome, None if outcome == "manual" else r)
    embed = ui.push_embed(
        Kind.CLOSED_TRADE, trade["ticker"], trade.get("direction"), detail,
        description=ui.result_headline(direction=trade.get("direction", ""), entry=entry,
                                       exit_price=exit_price, stop=trade.get("stop_loss"),
                                       pct=pct, r=r))
    ui.apply_chrome(embed, kind=Kind.CLOSED_TRADE, r=kinds.result_r(outcome, r),
                    plan_id=trade.get("plan_id"))

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
            log.warning("Could not resolve closed-trades channel %s: %s", config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce, exc_info=True)
            return
    for trade in newly_closed:
        status = trade.get("status", "")
        if status not in ("win", "loss", "closed"):
            continue   # skip anything unexpected (still-open, etc.)
        try:
            # v110: the registry push line replaces the old ✅ WIN — **TICK** header.
            embed = build_closed_trade_embed(trade)
            await channel.send(**ui.push_kwargs(embed))
            log_posted(embed, trade.get("ticker"), channel)
        except Exception as e:
            log.warning("Could not post closed-trade notification for %s: %s", trade.get("id"), e, exc_info=True)


def build_near_close_embed(warning: dict) -> discord.Embed:
    t = warning["trade"]
    is_sl = warning["near_which"] == "stop-loss"
    approaching_word = "STOP-LOSS" if is_sl else "TAKE-PROFIT"
    cur = get_currency_symbol(t["ticker"], config.CURRENCY_SYMBOL)
    kind = Kind.NEAR_STOP if is_sl else Kind.NEAR_TP
    distance = warning["sl_dist_pct" if is_sl else "tp_dist_pct"]
    embed = ui.push_embed(kind, t["ticker"], t.get("direction"), f"{distance:.1f}% away")
    ui.apply_chrome(embed, kind=kind, plan_id=t.get("plan_id"))
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
    return embed


async def notify_near_close(bot, warnings: list):
    if not warnings or not config.DISCORD_CHANNEL_TRADES_HISTORY_ID:
        return
    channel = bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(config.DISCORD_CHANNEL_TRADES_HISTORY_ID))
        except Exception as _ce:
            log.warning("Could not resolve closed-trades channel %s: %s", config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce, exc_info=True)
            return
    for warning in warnings:
        try:
            embed = build_near_close_embed(warning)
            await channel.send(**ui.push_kwargs(embed))
            log_posted(embed, warning["trade"].get("ticker"), channel)
        except Exception as e:
            log.warning("Could not post near-close warning for %s: %s", warning["trade"].get("id"), e, exc_info=True)


#: v2 plan transition -> registry kind (v110 §2). "closed" is keyed by reason below.
PLAN_EVENT_KINDS = {
    "filled": Kind.ENTRY_TRIGGERED,
    "cancelled_expired": Kind.EXPIRED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
}

#: close reason -> (kind, outcome, phrase). STOPPED and SCRATCHED already say
#: it in their label; the phrases keep the four WIN closes distinct.
CLOSE_REASON_STYLES = {
    "loss": (Kind.STOPPED, "loss", ""),
    "scratch": (Kind.SCRATCHED, "scratch", ""),
    "win": (Kind.WIN, "win", "target hit"),
    "tp1_runner_be": (Kind.WIN, "win", "runner closed at its floor"),
    "tp1_runner_tp2": (Kind.WIN, "win", "runner hit TP2"),
    "tp1_runner_trail": (Kind.WIN, "win", "trail locked profit"),
    "tp1_runner_progress_stall": (Kind.WIN, "win", "runner exited: higher high failed on cooling volume"),
}

_ENDED_OUTCOME = {Kind.EXPIRED: "expired", Kind.INVALIDATED: "invalidated"}


def _event_style(plan, event) -> tuple:
    """(kind, title detail, stripe R) for one plan event."""
    if event.transition == "closed":
        kind, outcome, phrase = CLOSE_REASON_STYLES.get(
            event.detail.get("reason"), (Kind.EXITED, None, "closed"))
        r = total_r(plan, event.detail.get("exit_price"))
        outcome = outcome or kinds.outcome_for_r(r)
        detail = kinds.outcome_detail(outcome, r)
        return kind, (f"{detail} · {phrase}" if phrase else detail), kinds.result_r(outcome, r)
    kind = PLAN_EVENT_KINDS.get(event.transition, Kind.PLAN_UPDATE)
    ended = _ENDED_OUTCOME.get(kind)
    return kind, (kinds.outcome_detail(ended) if ended else ""), None


def _filled_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, d["entry_price"])
    embed.add_field(name="Entry", value=f"{d['entry_price']:.2f}")
    embed.add_field(name="Stop", value=f"{plan.stop_loss:.2f}")
    embed.add_field(name="TP1", value=f"{plan.tp1:.2f}")


def _be_moved_fields(embed, plan, d) -> None:
    embed.add_field(name="New stop", value=f"{d['working_stop']:.2f} (entry)")


def _tp1_partial_fields(embed, plan, d) -> None:
    pct, amount = banked_leg_pct_and_amount(plan, d["exit_price"], d["fraction"])
    banked = f"{d['fraction']:.0%} @ {d['exit_price']:.2f} ({d['r']:+.2f}R"
    if pct is not None:
        banked += f" · {pct:+.1f}%"
    if amount is not None:
        banked += f" · {signed_money(amount, config.CURRENCY_SYMBOL)}"
    embed.add_field(name="Banked", value=banked + ")")
    embed.add_field(name="Partial position", value=partial_position_line(plan), inline=False)


def _closed_fields(embed, plan, d) -> None:
    exit_price = d.get("exit_price")
    embed.description = plan_result_block(plan, exit_price, total_r(plan, exit_price))
    embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")


def _expired_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Never triggered — {d['bars_waited']} bar(s) waited, past the "
        f"{plan.expiry_bars}-bar window (trigger {plan.trigger_price:.2f})"), inline=False)


def _invalidated_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Price closed through the stop before entry triggered: "
        f"{d['live_price']:.2f} vs stop {plan.stop_loss:.2f}"), inline=False)


def _risk_cap_fields(embed, plan, d) -> None:
    embed.add_field(name="Why", value=(
        f"Trigger filled at {d['entry_price']:.2f} against stop {d['stop_loss']:.2f} — "
        f"{d['planned_loss_pct']:.2f}% planned risk, above the "
        f"{d['max_planned_loss_pct']:.1f}% hard cap. Never opened; no position, no P&L."),
        inline=False)


_EVENT_FIELDS = {
    "filled": _filled_fields,
    "be_moved": _be_moved_fields,
    "tp1_partial": _tp1_partial_fields,
    "closed": _closed_fields,
    "cancelled_expired": _expired_fields,
    "cancelled_invalidated": _invalidated_fields,
    "cancelled_risk_cap": _risk_cap_fields,
}


def build_plan_event_embed(plan, event) -> discord.Embed:
    """Per-transition Discord embed for the v2 plan lifecycle (Task 72), styled
    by the v110 registry. Field text is unchanged from the pre-v110 builder."""
    kind, detail, stripe_r = _event_style(plan, event)
    embed = ui.push_embed(kind, plan.ticker, plan.direction, detail)
    ui.apply_chrome(embed, kind=kind, r=stripe_r, plan_id=plan.plan_id)
    embed.add_field(name="Plan (v2)", value=strategy_plan_line(plan), inline=False)
    fields = _EVENT_FIELDS.get(event.transition)
    if fields is not None:
        fields(embed, plan, event.detail)
    return embed


_WARN_EVERY_SECONDS = 15 * 60
_last_warned: dict[str, float] = {}


def _warn_throttled(plan_id: str, message: str, *args) -> None:
    """Avoid a log flood while an undelivered event is retried each minute."""
    now = time.monotonic()
    if now - _last_warned.get(plan_id, float("-inf")) < _WARN_EVERY_SECONDS:
        return
    _last_warned[plan_id] = now
    log.warning(message, *args)


def _resolve_channel(bot, channel_id):
    if not channel_id:
        return None
    try:
        return bot.get_channel(int(channel_id))
    except (TypeError, ValueError):
        return None


def _delivery(plan, event):
    from swingbot.core.planning.plan_manager import Delivery
    if event.transition == "stop_moved":
        return Delivery(plan.plan_id, "stop", event.detail["new"])
    if event.transition in ("be_moved", "tp1_partial"):
        return Delivery(plan.plan_id, "stop", event.detail["working_stop"])
    # A v119 time notice is acknowledged by its stable id, so one acked notice
    # never clears the other; every other notice by its transition.
    return Delivery(plan.plan_id, "notice", event.detail.get("notice_id", event.transition))


async def notify_plan_events(bot, events) -> list:
    """Post lifecycle instructions to the execution feed and report delivery.

    The feed notifies, history receives a silent copy. If the feed is absent
    or fails, the history copy deliberately notifies instead. Non-feed events
    keep their existing history-only status embed and are never acknowledged.
    """
    from swingbot.core.infra.silent_channel import silence
    from swingbot.core.planning.plan_manager import NOTICE_EVENTS, STOP_EVENTS
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.planning.time_exit import TIME_EVENTS
    from .execution_embeds import build_instruction_embed

    store = PlanStore()
    feed = _resolve_channel(bot, config.DISCORD_CHANNEL_TRADES_SIMPLE_ID)
    history = _resolve_channel(bot, config.DISCORD_CHANNEL_TRADES_HISTORY_ID)
    deliveries = []
    for event in events:
        try:
            plan = store.get(event.plan_id)
            if plan is None:
                continue
            if event.transition not in STOP_EVENTS | NOTICE_EVENTS | TIME_EVENTS:
                if history is not None:
                    status_embed = build_plan_event_embed(plan, event)
                    await history.send(**ui.push_kwargs(status_embed))
                    log_posted(status_embed, plan.ticker, history)
                continue
            embed = build_instruction_embed(plan, event)
            pinged = False
            if feed is not None:
                try:
                    await feed.send(**ui.push_kwargs(embed))
                    log_posted(embed, plan.ticker, feed)
                    pinged = True
                except Exception as exc:
                    _warn_throttled(plan.plan_id, "execution feed: %s for plan %s failed "
                                    "on feed (%s); history will notify instead",
                                    event.transition, plan.plan_id, exc)
            if history is not None:
                try:
                    await (silence(history) if pinged else history).send(**ui.push_kwargs(embed))
                    log_posted(embed, plan.ticker, history)
                    pinged = True
                except Exception as exc:
                    _warn_throttled(plan.plan_id, "execution feed: history copy of %s for "
                                    "plan %s failed: %s", event.transition, plan.plan_id, exc)
            if pinged:
                log.info("execution feed: delivered %s for plan %s",
                          event.transition, plan.plan_id)
                deliveries.append(_delivery(plan, event))
            else:
                _warn_throttled(plan.plan_id, "execution feed: %s for plan %s reached no "
                                "channel; it will be re-sent", event.transition, plan.plan_id)
        except Exception as exc:
            _warn_throttled(event.plan_id, "execution feed: could not post %s for plan %s: %s",
                            event.transition, event.plan_id, exc)
    return deliveries

