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
import logging
from dataclasses import dataclass

import discord

from swingbot import config
from .data import get_currency_symbol, get_daily_data
from .strategy import HORIZONS
from .charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart

log = logging.getLogger("swing-bot.scan_engine")


@dataclass
class RequirementCheck:
    """
    One named settings requirement (min reward %, min strategies
    confirmed, min confidence level, ...) checked against a single
    scenario, independent of whether it passed -- unlike the old
    sequential filter chain, EVERY requirement is always evaluated and
    kept, so a scenario can fail more than one at once and still be
    shown in full (see build_embed / _build_trade_plan_table) with
    every failing one marked, rather than silently vanishing at
    whichever filter it hit first.
    """
    key: str
    label: str
    passed: bool
    detail: str    # human-readable "actual value (needs threshold)", used verbatim when displaying a failure


CONFIDENCE_COLORS = {
    1: (231, 76, 60),    # red -- Very Low
    2: (230, 126, 34),   # orange -- Low
    3: (241, 196, 15),   # yellow -- Medium
    4: (154, 205, 50),   # yellow-green -- High
    5: (39, 174, 96),    # green -- Very High
}
CONFIDENCE_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟢"}

# Discord's ANSI code-block palette only has 8 foreground colors (30-37),
# so the 5-level confidence scale maps onto the closest available color --
# red -> yellow -> yellow -> green -> green. Always paired with "1;" for
# bold, so the Confidence field visually matches the embed's own
# confidence-color accent instead of rendering as plain white text.
CONFIDENCE_ANSI = {1: 31, 2: 33, 3: 33, 4: 32, 5: 32}


def confidence_color(level: int) -> discord.Color:
    r, g, b = CONFIDENCE_COLORS.get(level, (150, 150, 150))
    return discord.Color.from_rgb(r, g, b)


def _sources_str(sources) -> str:
    return ", ".join(dict.fromkeys(sources)) if sources else "n/a"


def _build_requirement_checks(scenario, target_confluence: tuple, conf, effective_min_confluence: int) -> list:
    """
    Evaluates EVERY configured requirement against one scenario --
    always all of them, never stopping at the first failure -- and
    returns a RequirementCheck per one. This is the single source of
    truth both `!check`'s always-show-everything display and the
    automatic scan's stricter posting decision (`ScanItem.all_requirements_met`)
    are built from, so the two can never disagree about what "meets
    the settings" means.
    """
    confluence_count, confluence_families = target_confluence
    c = scenario.constraints

    checks = [
        RequirementCheck(
            key="min_reward", label="Min reward %", passed=c.get("min_reward", True),
            detail=f"{scenario.target_distance_pct:.1f}% (needs {config.MIN_REWARD_PCT:.1f}%+)",
        ),
        RequirementCheck(
            key="min_stop_distance", label="Min stop distance %", passed=c.get("min_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (needs {config.MIN_STOP_DISTANCE_PCT:.1f}%+)",
        ),
        RequirementCheck(
            key="max_stop_distance", label="Max stop-loss %", passed=c.get("max_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (needs ≤{config.MAX_STOP_LOSS_PCT:.1f}%)",
        ),
        RequirementCheck(
            key="min_risk_reward", label="Min reward:risk", passed=c.get("min_risk_reward", True),
            detail=f"{scenario.risk_reward_ratio}:1 (needs {config.MIN_RISK_REWARD_RATIO:.1f}:1+)",
        ),
        RequirementCheck(
            key="min_confluence", label="Min strategies confirmed", passed=confluence_count >= effective_min_confluence,
            detail=(
                f"{confluence_count} strateg{'y' if confluence_count == 1 else 'ies'} "
                f"({', '.join(confluence_families) or 'none'}) within {config.CONFLUENCE_DEVIATION_PCT:.1f}% "
                f"(needs {effective_min_confluence}+)"
            ),
        ),
        RequirementCheck(
            key="min_confidence", label="Min confidence level", passed=conf.level >= config.MIN_ALERT_CONFIDENCE_LEVEL,
            detail=f"Lv{conf.level} {conf.label} (needs Lv{config.MIN_ALERT_CONFIDENCE_LEVEL}+)",
        ),
    ]
    return checks


def _confidence_block(conf) -> str:
    ansi_code = CONFIDENCE_ANSI.get(conf.level, 37)
    text = f"{CONFIDENCE_EMOJI.get(conf.level, '⚪')} {conf.label} (Lv{conf.level}/5, {conf.score}/100)"
    return f"```ansi\n[1;{ansi_code}m{text}[0m\n```"


def _ansi_bad(text: str) -> str:
    """Bold red, Discord ansi code-block palette -- used to mark a single failing requirement's row/value."""
    return f"[1;31m{text}[0m"


def _build_trade_plan_table(item) -> str:
    """
    Renders the full trade plan as a single aligned, monospace table
    (key : value rows in an ansi code block) -- every summarized
    parameter of the trade in one place, including which independent
    strategies (EMA/VWAP/Fibonacci/structure/pivots/FVG/...) agreed on
    the target and stop levels that produced this plan.

    Every row is always shown with its real computed value, regardless
    of whether it clears the configured requirement for that parameter
    (min reward %, stop distance, risk:reward, min strategies
    confirmed, min confidence) -- a scenario with a real entry point is
    never hidden just because one number falls short. Whichever
    row(s) correspond to an unmet requirement (see item.requirements)
    are rendered in bold red with the actual requirement appended, so
    it's always visible AT A GLANCE which specific parameter is holding
    a setup back, not just that "something" failed.
    """
    result, plan, conf = item.result, item.plan, item.conf
    is_bull = result.trend == "bullish"
    level_word = "Resistance" if is_bull else "Support"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    stop_sign = "-" if is_bull else "+"

    req_by_key = {r.key: r for r in item.requirements}

    def _row_value(key: str, ok_value: str) -> str:
        """Plain value if the requirement passed (or doesn't apply); the requirement's own
        failure detail, bold red, if it didn't."""
        r = req_by_key.get(key)
        if r is None or r.passed:
            return ok_value
        return _ansi_bad(f"{ok_value}  ⚠ {r.detail}")

    stop_value = f"{plan.stop_loss:.2f}  ({stop_sign}{plan.stop_distance_pct:.1f}%)"
    min_stop_req, max_stop_req = req_by_key.get("min_stop_distance"), req_by_key.get("max_stop_distance")
    if min_stop_req and not min_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {min_stop_req.detail}")
    elif max_stop_req and not max_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {max_stop_req.detail}")

    rows = [
        ("Direction", direction),
        ("Entry (now)", f"{plan.entry:.2f}"),
        ("Stop loss", stop_value),
        (f"{level_word} 1 (Target)", _row_value("min_reward", f"{plan.take_profit:.2f}  (+{plan.target_distance_pct:.1f}%)")),
    ]
    if plan.target2_price is not None:
        rows.append((f"{level_word} 2 (Stretch)", f"{plan.target2_price:.2f}  (+{plan.target2_distance_pct:.1f}%)"))
    rows.append(("Reward:Risk", _row_value("min_risk_reward", f"{plan.risk_reward_ratio}:1")))
    rows.append(("Confidence", _row_value("min_confidence", f"{conf.label} (Lv{conf.level}/5)")))
    rows.append(("Target confirmed by", _row_value("min_confluence", _sources_str(plan.target_sources))))
    rows.append(("Stop confirmed by", _sources_str(plan.stop_sources)))

    key_width = max(len(k) for k, _ in rows)
    lines = [f"{k.ljust(key_width)} : {v}" for k, v in rows]
    return "```ansi\n" + "\n".join(lines) + "\n```"


def build_embed(item, explanation, perf_stats, open_positions_warning, chart_filename) -> discord.Embed:
    result, plan, conf = item.result, item.plan, item.conf
    is_bull = result.trend == "bullish"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    all_ok = item.all_requirements_met
    priority_marker = "⭐ " if (conf.level >= 4 and all_ok) else ""
    needs_review_marker = "⚠️ " if not all_ok else ""
    title = f"{needs_review_marker}{priority_marker}{'🟢' if is_bull else '🔴'} {direction} — {result.ticker}"
    # Embed color highlights CONFIDENCE (red=lowest -> green=highest) when
    # every requirement is met; a scenario still missing one or more is
    # always shown in neutral gray regardless of its score, so "this one
    # needs a second look" reads at a glance from the color alone, before
    # even opening the trade plan table where the specific failing
    # parameter(s) are marked in bold red.
    embed_color = confidence_color(conf.level) if all_ok else discord.Color.from_rgb(149, 165, 166)
    embed = discord.Embed(title=title, color=embed_color)

    # combined_from always has at least the representative's own entry (set
    # during dedup), so the confirming strategy/horizon combo(s) are always
    # shown -- not just when more than one merged in.
    confirmations = ", ".join(f"{c['strategy']} ({c['horizon_key']})" for c in item.combined_from)
    extra = f"  +{len(item.combined_from)-1} more horizon(s)" if len(item.combined_from) > 1 else ""
    embed.add_field(name="Setup", value=f"{result.strategy}{extra}", inline=True)
    embed.add_field(name="Confirmed by", value=confirmations, inline=False)

    embed.add_field(name="Swing type", value=result.horizon_label, inline=True)
    embed.add_field(name="Confidence", value=_confidence_block(conf), inline=True)

    if not all_ok:
        unmet = ", ".join(r.label for r in item.requirements if not r.passed)
        embed.add_field(
            name="⚠️ Not yet a clean setup",
            value=f"Doesn't meet: {unmet}. Shown for visibility -- see the trade plan below for exactly why "
                  "(marked in bold red); not logged as a paper trade and won't auto-alert until it clears these.",
            inline=False,
        )

    embed.add_field(name="🎯 Trade plan", value=_build_trade_plan_table(item), inline=False)

    level_word = "Resistance" if is_bull else "Support"
    opposite_word = "Support" if is_bull else "Resistance"
    branch_lines = []
    if plan.target2_price is not None:
        branch_lines.append(f"Continues past {level_word.lower()} 1 → next stop {plan.target2_price:.2f} (+{plan.target2_distance_pct:.1f}%)")
    else:
        branch_lines.append(f"Continues past {level_word.lower()} 1 → no further level found for a stretch target")
    branch_lines.append(f"Reverses at {level_word.lower()} 1 → pulls back toward {opposite_word.lower()} at {plan.stop_loss:.2f} ({plan.stop_distance_pct:.1f}%)")
    embed.add_field(name="🔀 If it gets there", value="\n".join(branch_lines), inline=False)

    if perf_stats["closed"] > 0:
        wr = perf_stats["win_rate"]
        embed.add_field(
            name=f"Track record @ Lv{conf.level}",
            value=f"{wr:.0f}% win rate ({perf_stats['wins']}W/{perf_stats['losses']}L, {perf_stats['closed']} closed)",
            inline=True,
        )
    else:
        embed.add_field(name=f"Track record @ Lv{conf.level}", value="No closed trades yet at this level", inline=True)

    if open_positions_warning:
        embed.add_field(name="⚠️ Position limit", value=open_positions_warning, inline=False)

    embed.description = explanation[:4000]
    if chart_filename:
        embed.set_image(url=f"attachment://{chart_filename}")
    embed.set_footer(text="Technical signal only, based on today's still-developing daily candle -- not financial advice.")
    return embed


def regenerate_chart_for_trade(trade: dict) -> str | None:
    try:
        df = get_daily_data(trade["ticker"])
        h = HORIZONS.get(trade["horizon_key"], {})
        horizon_label = h.get("label", trade["horizon_key"])
        filename = f"{trade['ticker']}_{trade['id']}_view.png"
        # Re-viewing an older trade later should show where price actually
        # is *now* (today's fresh close from df) alongside the original
        # planned entry -- they'll usually differ since time has passed.
        current_price = float(df["Close"].iloc[-1])
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
        )
    except Exception as e:
        log.warning("Could not regenerate chart for trade %s: %s", trade.get("id"), e)
        return None


def build_closed_trade_embed(trade: dict) -> discord.Embed:
    won = trade["status"] == "win"
    outcome_word = "WIN" if won else "LOSS"
    color = discord.Color.green() if won else discord.Color.red()
    pct = (trade["exit_price"] - trade["entry"]) / trade["entry"] * 100
    if trade["direction"] == "bearish":
        pct = -pct
    cur = get_currency_symbol(trade["ticker"], config.CURRENCY_SYMBOL)
    title = f"{'✅' if won else '❌'} TRADE CLOSED: {outcome_word} — {trade['ticker']}"
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Result", value=f"**{outcome_word}** ({pct:+.2f}%)", inline=False)
    embed.add_field(name="Setup", value=f"{trade['strategy']} ({trade['horizon_key']})", inline=True)
    embed.add_field(name="Direction", value="LONG" if trade["direction"] == "bullish" else "SHORT", inline=True)
    embed.add_field(name="Confidence", value=f"{trade['confidence_label']} (Lv{trade['confidence_level']})", inline=True)
    embed.add_field(name="Entry", value=f"{cur}{trade['entry']:.2f}", inline=True)
    embed.add_field(name="Exit", value=f"{cur}{trade['exit_price']:.2f}", inline=True)
    embed.add_field(name="Change", value=f"{pct:+.2f}%", inline=True)
    embed.add_field(name="Opened", value=trade["opened_at"][:19], inline=True)
    embed.add_field(name="Closed", value=trade["closed_at"][:19], inline=True)
    embed.set_footer(text=f"Trade ID: {trade['id']}")
    return embed


async def notify_closed_trades(bot, newly_closed: list):
    if not newly_closed or not config.CLOSED_TRADES_CHANNEL_ID:
        return
    channel = bot.get_channel(int(config.CLOSED_TRADES_CHANNEL_ID))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(config.CLOSED_TRADES_CHANNEL_ID))
        except Exception as _ce:
            log.warning("Could not resolve closed-trades channel %s: %s", config.CLOSED_TRADES_CHANNEL_ID, _ce)
            return
    for trade in newly_closed:
        try:
            outcome_word = "WIN" if trade["status"] == "win" else "LOSS"
            await channel.send(content=f"**{outcome_word}** — {trade['ticker']} (`{trade['id']}`)", embed=build_closed_trade_embed(trade))
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
    embed.set_footer(text=f"Trade ID: {t['id']} -- use !trade {t['id']} for full detail")
    return embed


async def notify_near_close(bot, warnings: list):
    if not warnings or not config.CLOSED_TRADES_CHANNEL_ID:
        return
    channel = bot.get_channel(int(config.CLOSED_TRADES_CHANNEL_ID))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(config.CLOSED_TRADES_CHANNEL_ID))
        except Exception as _ce:
            log.warning("Could not resolve closed-trades channel %s: %s", config.CLOSED_TRADES_CHANNEL_ID, _ce)
            return
    for warning in warnings:
        try:
            await channel.send(embed=build_near_close_embed(warning))
        except Exception as e:
            log.warning("Could not post near-close warning for %s: %s", warning["trade"].get("id"), e)
