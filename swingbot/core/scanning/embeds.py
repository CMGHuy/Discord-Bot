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

from swingbot import config
from swingbot.core import account
from swingbot.core.account import compute_position_size, load_account_config
from swingbot.core.data import get_currency_symbol, get_daily_data
from swingbot.core.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line
from swingbot.core.registry import Badge
from swingbot.core.strategy import HORIZONS
from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, generate_trade_chart

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


def _load_scan_snapshots() -> dict:
    if not os.path.exists(_SNAPSHOT_PATH):
        return {}
    try:
        with open(_SNAPSHOT_PATH, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_scan_snapshots(data: dict) -> None:
    try:
        with open(_SNAPSHOT_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _format_duration_hms(total_seconds: float) -> str:
    """Day/hour/minute holding-period label, e.g. "1 day 5 hours 32 minutes"
    -- mirrors admin/app.py's _format_duration_hms exactly (duplicated
    rather than imported since admin/ imports FROM core/, not the other way
    around, and this one small formatter isn't worth a shared-module
    detour for)."""
    total_seconds = max(0.0, total_seconds)
    total_minutes = int(total_seconds // 60)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours or days:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


def _snapshot_and_diff(item) -> str | None:
    """
    Compares this scenario's current entry/stop/target/confidence/R:R
    against the last time this exact ticker + horizon + direction combo was
    posted (by either `!check` or the automatic scan -- they share the same
    store), and returns a short "what changed" summary. Returns None the
    very first time a combo is seen (nothing to diff against yet) or when
    every tracked number is unchanged.

    Always writes the CURRENT numbers back to disk as the new "last seen"
    snapshot before returning, so the NEXT scan/`!check` of this same combo
    diffs against this one -- this call is the update, not just a read.
    """
    result, plan, conf = item.result, item.plan, item.conf
    key = f"{result.ticker}|{result.horizon_key}|{result.trend}"
    snapshots = _load_scan_snapshots()
    prev = snapshots.get(key)

    current = {
        "entry": plan.entry, "stop_loss": plan.stop_loss, "take_profit": plan.take_profit,
        "confidence_level": conf.level, "risk_reward_ratio": plan.risk_reward_ratio,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    snapshots[key] = current
    _save_scan_snapshots(snapshots)

    if prev is None:
        return None

    changes = []
    if abs(prev.get("entry", plan.entry) - plan.entry) > 1e-9:
        pct = ((plan.entry - prev["entry"]) / prev["entry"] * 100) if prev.get("entry") else 0
        changes.append(f"Entry {prev['entry']:.2f} → {plan.entry:.2f} ({pct:+.1f}%)")
    if abs(prev.get("stop_loss", plan.stop_loss) - plan.stop_loss) > 1e-9:
        changes.append(f"Stop {prev['stop_loss']:.2f} → {plan.stop_loss:.2f}")
    if abs(prev.get("take_profit", plan.take_profit) - plan.take_profit) > 1e-9:
        changes.append(f"Target {prev['take_profit']:.2f} → {plan.take_profit:.2f}")
    if prev.get("confidence_level") != conf.level:
        prev_level = prev.get("confidence_level", conf.level)
        arrow = "⬆️" if conf.level > prev_level else "⬇️"
        changes.append(f"Confidence Lv{prev_level} {arrow} Lv{conf.level}")
    if prev.get("risk_reward_ratio") != plan.risk_reward_ratio:
        changes.append(f"R:R {prev.get('risk_reward_ratio', '?')}:1 → {plan.risk_reward_ratio}:1")

    return " · ".join(changes) if changes else None


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
    truth the posting decision for BOTH scan modes is built from
    (`ScanItem.all_requirements_met` -- see engine.py's alert-building
    loop, which only posts a scenario once every one of these passes),
    so `!check` and the automatic scan can never disagree about what
    "meets the settings" means.
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


def plan_numbers_for_display(plan, legacy: dict) -> dict:
    """THE cutover switch: which numbers do embeds/charts/trade-logging
    show? flag != 'on' or no plan -> legacy scenario numbers (today's
    behavior); 'on' -> the v2 plan's numbers."""
    if config.PLAN_ENGINE_V2 != "on" or plan is None:
        return dict(legacy)
    return {"entry": plan.trigger_price, "stop_loss": plan.stop_loss,
            "take_profit": plan.tp1, "target2": plan.tp2}


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

    plan_v2 = getattr(item, "plan_v2", None)
    nums = plan_numbers_for_display(plan_v2, {
        "entry": plan.entry, "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit, "target2": plan.target2_price})
    entry, stop_loss = nums["entry"], nums["stop_loss"]
    take_profit, target2 = nums["take_profit"], nums["target2"]
    v2_priced = config.PLAN_ENGINE_V2 == "on" and plan_v2 is not None
    if entry == plan.entry and stop_loss == plan.stop_loss:
        # funnel returned the legacy numbers -- keep the scenario's own
        # (differently-rounded) distance/RR fields byte-identical
        stop_dist_pct = plan.stop_distance_pct
        target_dist_pct = plan.target_distance_pct
        target2_dist_pct = plan.target2_distance_pct
        rr = plan.risk_reward_ratio
    else:
        stop_dist_pct = abs(entry - stop_loss) / entry * 100
        target_dist_pct = abs(take_profit - entry) / entry * 100
        target2_dist_pct = (abs(target2 - entry) / entry * 100
                            if target2 is not None else None)
        risk = abs(entry - stop_loss)
        rr = round(abs(take_profit - entry) / risk, 2) if risk else plan.risk_reward_ratio

    req_by_key = {r.key: r for r in item.requirements}

    def _row_value(key: str, ok_value: str) -> str:
        """Plain value if the requirement passed (or doesn't apply); the requirement's own
        failure detail, bold red, if it didn't."""
        r = req_by_key.get(key)
        if r is None or r.passed:
            return ok_value
        return _ansi_bad(f"{ok_value}  ⚠ {r.detail}")

    stop_value = f"{stop_loss:.2f}  ({stop_sign}{stop_dist_pct:.1f}%)"
    min_stop_req, max_stop_req = req_by_key.get("min_stop_distance"), req_by_key.get("max_stop_distance")
    if min_stop_req and not min_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {min_stop_req.detail}")
    elif max_stop_req and not max_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {max_stop_req.detail}")

    rows = [
        ("Direction", direction),
        ("Entry (now)", f"{entry:.2f}"),
    ]
    if v2_priced:
        # Make it unmistakable that these prices came from the v2 plan
        # engine, not the legacy scenario sizing.
        rows.insert(0, ("Engine", "Plan Engine v2"))
    rows += [
        ("Stop loss", stop_value),
        (f"{level_word} 1 (Target)", _row_value("min_reward", f"{take_profit:.2f}  (+{target_dist_pct:.1f}%)")),
    ]
    if target2 is not None:
        rows.append((f"{level_word} 2 (Stretch)", f"{target2:.2f}  (+{target2_dist_pct:.1f}%)"))
    rows.append(("Reward:Risk", _row_value("min_risk_reward", f"{rr}:1")))
    rows.append(("Confidence", _row_value("min_confidence", f"{conf.label} (Lv{conf.level}/5)")))
    rows.append(("Target confirmed by", _row_value("min_confluence", _sources_str(plan.target_sources))))
    rows.append(("Stop confirmed by", _sources_str(plan.stop_sources)))

    # Position sizing -- uses the live account config so !account changes
    # are reflected immediately without a bot restart.
    account_cfg = load_account_config()
    pos = compute_position_size(entry, stop_loss, account_cfg)
    if pos and pos["balance"] > 0:
        cur = config.CURRENCY_SYMBOL
        cap_note = f"  [capped at {pos['max_position_pct']:.0f}% of account]" if pos["capped"] else ""
        rows.append((
            "Suggested size",
            f"~{pos['shares']:.1f} shares  "
            f"({cur}{pos['position_value']:,.0f} deployed, "
            f"{cur}{pos['risk_amount']:,.0f} at risk @ {pos['risk_pct']}% rule){cap_note}",
        ))
        # Possible P&L in real currency, not just % -- the "Suggested size"
        # row above already states the $ at risk, but never the $ upside,
        # so there was no way to see the actual dollar trade-off (risk $X to
        # make $Y) without doing the shares x distance math yourself.
        possible_profit = pos["shares"] * abs(take_profit - entry)
        pnl_line = f"+{cur}{possible_profit:,.0f} at target  /  -{cur}{pos['risk_amount']:,.0f} at stop"
        if target2 is not None:
            possible_profit2 = pos["shares"] * abs(target2 - entry)
            pnl_line += f"  (+{cur}{possible_profit2:,.0f} at stretch target)"
        rows.append(("Possible P&L", pnl_line))

    if plan_v2 is not None:
        rows.append(("Entry (v2)", entry_line(plan_v2)))
        cur = config.CURRENCY_SYMBOL
        tp1_row, runner_row = leg_rows(plan_v2, currency=cur)
        rows.append(("TP1 leg (50%)", tp1_row))
        rows.append(("Runner leg (50%)", runner_row))

    key_width = max(len(k) for k, _ in rows)
    lines = [f"{k.ljust(key_width)} : {v}" for k, v in rows]
    return "```ansi\n" + "\n".join(lines) + "\n```"


def badge_field_for(plan) -> tuple[str, str] | None:
    """(field_name, field_value) for a v2 plan's pedigree, or None."""
    if plan is None:
        return None
    stats = plan.badge_stats or {}
    badge = Badge(status=plan.badge, n=stats.get("n", 0),
                  win_rate=stats.get("win_rate", 0.0),
                  expectancy_r=stats.get("expectancy_r", 0.0),
                  window=stats.get("window", ""))
    if plan.badge == "VALIDATED":
        return ("✅ VALIDATED", badge_stats_line(badge))
    caution = WEAK_CAUTION_TEXT.format(win_rate=badge.win_rate, n=badge.n)
    return ("⚠️ WEAK", f"**{caution}**")


def quality_lines(plan) -> tuple[str, str] | None:
    """('Quality: 82/100 (Tier A)', 'regime +15 · htf +8 · ...') or None
    for unscored plans. Middle-dot separated, signed ints -- rendering is
    FIXED here; every consumer prints these two strings verbatim."""
    if plan is None or not plan.quality_breakdown:
        return None
    header = f"Quality: {plan.quality_score}/100 (Tier {plan.tier})"
    detail = " · ".join(f"{name} {pts:+d}" for name, pts in plan.quality_breakdown)
    return header, detail


def entry_line(plan) -> str:
    if plan.entry_type == "stop_entry":
        side = "BUY STOP above" if plan.direction == "bullish" else "SELL STOP below"
        return (f"Entry: {side} {plan.trigger_price:.2f} "
                f"(expires in {plan.expiry_bars} bars)")
    return f"Entry: market ~{plan.trigger_price:.2f}"


def leg_rows(plan, currency: str) -> tuple[str, str]:
    """('50% @ 102.00 → +$17.50', '50% → TP2 105.00 / trail') for the
    two-leg sizing block. P&L uses the SAME sizing snapshot source as the
    legacy table (account.compute_position_size at render time)."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    frac1 = plan.tp1_fraction
    try:
        sizing = account.compute_position_size(entry, plan.stop_loss)
    except Exception:
        sizing = None
    tp1_pct = f"{frac1:.0%} @ {plan.tp1:.2f}"
    if sizing and sizing.get("shares"):
        sign = 1 if plan.direction == "bullish" else -1
        pnl = sizing["shares"] * frac1 * (plan.tp1 - entry) * sign
        tp1_row = f"{tp1_pct} → {'+' if pnl >= 0 else ''}{currency}{abs(pnl):,.2f}"
    else:
        tp1_row = tp1_pct
    runner = f"{1 - frac1:.0%} → " + (f"TP2 {plan.tp2:.2f} / trail"
                                      if plan.tp2 else "trail")
    return tp1_row, runner


def build_embed(item, explanation, perf_stats, open_positions_warning, chart_filename,
                htf_info: dict = None) -> discord.Embed:
    """
    htf_info, when provided, is a dict from scan_engine.py's HTF check:
        {"htf_bias": "bullish"|"bearish", "counter_trend": bool, "ema_period": int, "horizon_key": str}
    Counter-trend setups get a ⚠️ warning field added to the embed.
    """
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

    plan_v2 = getattr(item, "plan_v2", None)
    badge_field = badge_field_for(plan_v2)
    if badge_field is not None:
        embed.add_field(name=badge_field[0], value=badge_field[1], inline=False)
        quality_field = quality_lines(plan_v2)
        if quality_field is not None:
            embed.add_field(name=quality_field[0], value=quality_field[1], inline=False)

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

    if htf_info and htf_info.get("counter_trend"):
        ema_p = htf_info["ema_period"]
        htf_bias_word = htf_info["htf_bias"].capitalize()
        signal_word = "Bullish" if is_bull else "Bearish"
        embed.add_field(
            name="📉 Counter-trend signal",
            value=(
                f"{signal_word} setup, but this ticker's own {ema_p}-day EMA trend is **{htf_bias_word}** "
                f"(higher-timeframe bias for {htf_info['horizon_key']} horizon). "
                f"Counter-trend setups have a lower base probability of following through -- "
                f"confidence was reduced by {config.HTF_COUNTER_TREND_PENALTY} points to reflect this."
            ),
            inline=False,
        )

    v2_priced = config.PLAN_ENGINE_V2 == "on" and plan_v2 is not None
    plan_field_name = "🎯 Trade plan (v2)" if v2_priced else "🎯 Trade plan"
    embed.add_field(name=plan_field_name, value=_build_trade_plan_table(item), inline=False)

    what_changed = _snapshot_and_diff(item)
    if what_changed:
        embed.add_field(name="🔄 What changed since last scan", value=what_changed, inline=False)

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
    footer = "Technical signal only, based on today's still-developing daily candle -- not financial advice."
    if v2_priced:
        footer = "Plan Engine v2 · " + footer
    embed.set_footer(text=footer)
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

    # Realized P&L — only meaningful when we have an exit price
    if exit_price is not None and entry:
        raw_pct = (exit_price - entry) / entry * 100
        pct     = raw_pct if is_bull else -raw_pct
        pnl_str = f"{pct:+.2f}%"
    else:
        pnl_str = "n/a"

    # R-multiple — risk_per_share is stored on the trade if sizing was active
    risk = trade.get("risk_per_share") or abs(entry - trade.get("stop_loss", entry)) or None
    if risk and exit_price is not None:
        realized = (exit_price - entry) if is_bull else (entry - exit_price)
        r_str    = f"{realized / risk:+.2f}R"
    else:
        r_str = "n/a"

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
        from datetime import datetime, timezone
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

    footer = f"Trade ID: {trade['id']}"
    if trade.get("plan_id") or trade.get("legs"):
        footer += " · Plan Engine v2"
    embed.set_footer(text=footer)
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
    embed.set_footer(text=f"Trade ID: {t['id']} -- use !trade {t['id']} for full detail")
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
    "tp1_runner_be":   ("🟢 Win — runner closed at break-even — {ticker}", discord.Color.green()),
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
        template, color = _EVENT_STYLE[event.transition]
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
        embed.add_field(name="Banked",
                        value=f"{d['fraction']:.0%} @ {d['exit_price']:.2f} "
                              f"({d['r']:+.2f}R)")
        embed.add_field(name="Runner",
                        value="runner active, stop at break-even", inline=False)
    elif event.transition == "closed":
        embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")
    embed.set_footer(text=f"v2 plan {plan.plan_id[:8]}")
    return embed


async def notify_plan_events(bot, events):
    """Route fills to the alerts channel, everything else to history --
    same split notify_closed_trades already uses."""
    from swingbot.core.plan_store import PlanStore
    store = PlanStore()
    for event in events:
        plan = store.get(event.plan_id)
        if plan is None:
            continue
        channel_id = (config.DISCORD_CHANNEL_TRADES_ID
                      if event.transition == "filled"
                      else config.DISCORD_CHANNEL_TRADES_HISTORY_ID)
        channel = bot.get_channel(int(channel_id)) if channel_id else None
        if channel is not None:
            await channel.send(embed=build_plan_event_embed(plan, event))
