"""Primary scan alert embed renderers."""
import json
import logging
from datetime import datetime, timezone

import discord

from swingbot import config
from swingbot.core.analytics.rank import follow_breakdown, follow_score
from swingbot.core.market import opex
from swingbot.core.market.strategy import HORIZONS
from swingbot.core import presentation as ui
from swingbot.core.scanning import embed_theme as theme

from .snapshots import _snapshot_and_diff
from .requirements import _sources_str, confidence_color
from .plan_table import (_v2_plan, plan_numbers_for_display, leg_rows)


log = logging.getLogger("swing-bot.scan_engine")
def build_embed(item, explanation, perf_stats, open_positions_warning, chart_filename,
                htf_info: dict = None, layout: str = "detailed") -> discord.Embed:
    """
    htf_info, when provided, is a dict from scan_engine.py's HTF check:
        {"htf_bias": "bullish"|"bearish", "counter_trend": bool, "ema_period": int, "horizon_key": str}
    Counter-trend setups get a ⚠️ warning field added to the embed.

    Fields are accumulated into `sections` (keyed by
    embed_theme.SECTION_ORDER) as (name, value, inline) tuples as they're
    computed, then flushed in that fixed order at the end -- so the field
    ORDER on the embed is always the same regardless of which optional
    fields happen to apply to this particular item.

    layout: "detailed" (default) shows every section this bot has always
    shown. "compact" drops the "Confirmed by" line, counter-trend warning,
    "what changed" section, "if it gets there" branches, track record, and
    position-limit warning -- keeping only a shortened headline, the trade
    plan table, and (in place of B2's two separate pedigree fields) a single
    one-line quality summary -- to fit more alerts on screen at once. Purely
    a rendering choice; no scoring or filtering changes.
    """
    result, plan, conf = item.result, item.plan, item.conf
    is_bull = result.trend == "bullish"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    all_ok = item.all_requirements_met
    compact = layout == "compact"
    priority_marker = "⭐ " if (conf.level >= 4 and all_ok) else ""
    needs_review_marker = "⚠️ " if not all_ok else ""
    plan_v2 = _v2_plan(item)
    title = f"{needs_review_marker}{priority_marker}{'🟢' if is_bull else '🔴'} {direction} — {result.ticker}"
    embed = discord.Embed(title=title, color=ui.accent_for_level(conf.level))

    sections: dict[str, list[tuple]] = {k: [] for k in ui.SECTION_ORDER}

    unmet = [(requirement.label, requirement.detail)
             for requirement in item.requirements if not requirement.passed]
    blocked = ui.blocked_by_field(unmet)
    if blocked is not None:
        sections["blocked"].append(blocked)
        embed.color = ui.accent_blocked()

    heat_blocked = getattr(item, "heat_blocked", None)
    if heat_blocked is not None:
        # Blocking is FLAGGED, never hidden (Edge plan E7) -- the alert
        # still posts with this headline field, suggested size 0, so the
        # operator always sees what the cap cost them.
        sections["headline"].append((
            "⛔ ENTRY BLOCKED — portfolio heat cap",
            (f"Open heat {heat_blocked['open_heat']}% / cap {heat_blocked['cap']}% — "
             f"suggested size **0 shares**. Close or trim a position to free heat."),
            False,
        ))

    # Flagged on every alert that day, exactly like heat_blocked above: the
    # tightened gates already decided what posts, and this tells the reader
    # what kind of day the survivors were found on so they can apply their
    # own judgement to entry timing.
    opex_note = opex.badge()
    if opex_note is not None:
        sections["headline"].append((opex_note[0], opex_note[1], False))

    cluster_blocked = getattr(item, "cluster_blocked", None)
    if cluster_blocked is not None:
        # Same flagged-not-hidden pattern as the portfolio heat cap above
        # (Edge plan E8).
        tickers_str = ", ".join(cluster_blocked.get("cluster", [])) or "—"
        sections["headline"].append((
            "⛔ ENTRY BLOCKED — correlated cluster",
            (f"Correlated with {tickers_str} (cluster heat {cluster_blocked['correlated_heat']}% / "
             f"cap {cluster_blocked['cap']}%) — suggested size **0 shares**."),
            False,
        ))

    kill_blocked = getattr(item, "kill_switch_blocked", None)
    if kill_blocked is not None:
        # Kill switch (Edge plan E47): same flagged-not-hidden pattern as
        # the E7/E8 blocks above -- informed, not blind. Unlike those two,
        # release is manual-only (`!killswitch off`), never automatic.
        sections["headline"].append((
            f"⛔ ENTRIES PAUSED (kill switch: {kill_blocked.get('reason')})",
            "Suggested size **0 shares** — a human needs to review before this re-engages (`!killswitch off`).",
            False,
        ))

    intraday = getattr(item, "intraday", None)
    if intraday is not None:
        # Edge plan E29: a LIVE-ONLY annotation. The stop-entry trigger is
        # still the daily one -- this only tells the operator whether the
        # 1h tape is currently on the plan's side. It is deliberately NOT a
        # backtest filter (no honest intraday history to fold-test it), so
        # it must never be presented as validated, and `None` (no data)
        # renders nothing at all rather than a misleading "against".
        sections["headline"].append((
            "⏱ Intraday timing",
            ("✅ confirms — last 1h close is on the plan's side of today's VWAP"
             if intraday else
             "⚠️ against — last 1h close is on the wrong side of today's VWAP; "
             "the daily trigger is unchanged, but entering now fights the tape"),
            False,
        ))

    sections["quality"].append(ui.confidence_field(conf.level, conf.score))

    # "Why follow this" (Task B6) -- always added (both compact and detailed
    # layouts) when a v2 plan exists, regardless of which branch above fired,
    # so the follow_score composite and its component breakdown are visible
    # even in compact mode where the two-field pedigree pair is dropped.
    if plan_v2 is not None:
        today = datetime.now(timezone.utc).date()
        score = follow_score(plan_v2, today=today)
        breakdown = follow_breakdown(plan_v2, today)
        breakdown_line = " · ".join(
            f"{label} +{pts:.0f}" if "quality" not in label else label
            for label, pts in breakdown
        )
        sections["quality"].append(ui.follow_field(score, breakdown_line))

    # combined_from always has at least the representative's own entry (set
    # during dedup), so the confirming strategy/horizon combo(s) are always
    # shown -- not just when more than one merged in.
    if not compact:
        confirmations = ", ".join(f"{c['strategy']} ({c['horizon_key']})" for c in item.combined_from)
        extra = f"  +{len(item.combined_from)-1} more horizon(s)" if len(item.combined_from) > 1 else ""
        sections["headline"].append(("Setup", f"{result.strategy}{extra}", True))
        sections["headline"].append(("Confirmed by", confirmations, False))
    else:
        sections["headline"].append(("Setup", result.strategy, True))
    sections["headline"].append(("Swing type", result.horizon_label, True))

    if htf_info and htf_info.get("counter_trend") and not compact:
        ema_p = htf_info["ema_period"]
        htf_bias_word = htf_info["htf_bias"].capitalize()
        signal_word = "Bullish" if is_bull else "Bearish"
        sections["warnings"].append((
            "📉 Counter-trend signal",
            (
                f"{signal_word} setup, but this ticker's own {ema_p}-day EMA trend is **{htf_bias_word}** "
                f"(higher-timeframe bias for {htf_info['horizon_key']} horizon). "
                "Counter-trend setups have a lower base probability of following through."
            ),
            False,
        ))

    # Always run -- this is the snapshot WRITE (updates the on-disk "last
    # seen" numbers for this ticker/horizon/direction combo), not just a
    # read, so the NEXT scan/!check of this same combo still diffs
    # correctly even when this particular embed is rendered compact.
    what_changed = _snapshot_and_diff(item)
    if not compact and what_changed:
        sections["changes"].append(("🔄 What changed since last scan", what_changed, False))

    if not compact:
        level_word = "Resistance" if is_bull else "Support"
        opposite_word = "Support" if is_bull else "Resistance"
        branch_lines = []
        if plan.target2_price is not None:
            branch_lines.append(f"Continues past {level_word.lower()} 1 → next stop {plan.target2_price:.2f} (+{plan.target2_distance_pct:.1f}%)")
        else:
            branch_lines.append(f"Continues past {level_word.lower()} 1 → no further level found for a stretch target")
        branch_lines.append(f"Reverses at {level_word.lower()} 1 → pulls back toward {opposite_word.lower()} at {plan.stop_loss:.2f} ({plan.stop_distance_pct:.1f}%)")
        sections["branches"].append(("🔀 If it gets there", "\n".join(branch_lines), False))

        if perf_stats["closed"] > 0:
            wr = perf_stats["win_rate"]
            sections["track_record"].append((
                f"Track record @ Lv{conf.level}",
                f"{wr:.0f}% win rate ({perf_stats['wins']}W/{perf_stats['losses']}L, {perf_stats['closed']} closed)",
                True,
            ))
        else:
            sections["track_record"].append((f"Track record @ Lv{conf.level}", "No closed trades yet at this level", True))

        if open_positions_warning:
            sections["warnings"].append(("⚠️ Position limit", open_positions_warning, False))

    for key in ui.SECTION_ORDER:
        for name, value, inline in sections[key]:
            embed.add_field(name=name, value=value, inline=inline)

    # v62 D4: the plan is the first thing on the first screenful.  Keep all
    # price selection behind the established legacy/v2 cutover funnel.
    nums = plan_numbers_for_display(plan_v2, {
        "entry": plan.entry,
        "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit,
        "target2": plan.target2_price,
    })
    headline = ui.plan_headline(
        direction=result.trend,
        entry=nums["entry"],
        target=nums["take_profit"],
        stop=nums["stop_loss"],
        target_pct=plan.target_distance_pct,
        stop_pct=-abs(plan.stop_distance_pct),
        r=plan.risk_reward_ratio,
    )
    embed.description = f"{headline}\n{explanation[:3500]}"
    if chart_filename:
        embed.set_image(url=f"attachment://{chart_filename}")
    theme.apply_footer(embed, plan_id=plan_v2.plan_id if plan_v2 else None)
    return embed


def build_simple_alert(item) -> discord.Embed:
    """The DISCORD_CHANNEL_TRADES_SIMPLE_ID mirror of a full alert: the same
    signal stripped to the fields needed to act on it -- ticker, direction,
    confidence level + score, horizon, setup, entry, TP1, TP2, SL. No chart is
    generated or attached (that is the point: this channel stays readable on a
    phone and costs no render time), no track record, no sizing, no
    requirement annotations, no plan buttons.

    A coloured embed rather than a plain string. Its accent reports confidence;
    direction stays explicit in the title and shared ANSI headline. Entry/TP1/TP2/SL are packed onto ONE line, each carrying its
    own emoji label (🎯/💰/💰/🛑) so which number is which stays unambiguous
    even without the old one-per-line layout.

    Prices come from plan_numbers_for_display() -- the SAME funnel
    _build_trade_plan_table() feeds the full embed from -- so the two channels
    can never quote different numbers for one signal. Anything that moves
    pricing (the PLAN_ENGINE_V2 cutover included) moves both at once.
    """
    result, plan, conf = item.result, item.plan, item.conf
    plan_v2 = _v2_plan(item)
    is_bull = result.trend == "bullish"
    direction = "LONG" if is_bull else "SHORT"
    arrow = "▲" if is_bull else "▼"

    nums = plan_numbers_for_display(plan_v2, {
        "entry": plan.entry, "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit, "target2": plan.target2_price})

    # "Setup" is the full embed's Setup field (the generating strategy) plus
    # the confluence methods that confirmed the target -- Fib, VWAP, EMA,
    # structure, ... -- which is the part that says WHY the level is there.
    # The full embed splits these across two places ("Setup" in the headline,
    # "Target confirmed by" in the plan table); one line is enough here.
    setup = result.strategy
    sources = _sources_str(plan.target_sources)
    if sources != "n/a":
        setup = f"{setup} · {sources}"

    plan_line = f"🎯 Entry **{nums['entry']:.2f}**  ·  💰 TP1 **{nums['take_profit']:.2f}**"
    tp2 = nums["target2"]
    if tp2 is not None:
        plan_line += f"  ·  💰 TP2 **{tp2:.2f}**"
    elif plan_v2 is not None:
        # v2 scale-out plans manage the runner to a trailing stop instead of
        # a fixed second target -- say so rather than silently dropping the
        # field, same convention as the full embed's leg_rows().
        plan_line += "  ·  💰 TP2 **trail**"
    plan_line += f"  ·  🛑 SL **{nums['stop_loss']:.2f}**"

    headline = ui.plan_headline(
        direction=result.trend, entry=nums["entry"], target=nums["take_profit"],
        stop=nums["stop_loss"], target_pct=plan.target_distance_pct,
        stop_pct=-abs(plan.stop_distance_pct), r=plan.risk_reward_ratio,
    )
    embed = discord.Embed(
        title=f"{arrow} {direction} — {result.ticker}",
        description=(
            f"{headline}\n"
            f"Confidence: {ui.confidence_label(conf.level, conf.score)}\n"
            f"Horizon: {result.horizon_label}\n"
            f"Setup: {setup}\n\n"
            f"{plan_line}"
        ),
    )
    ui.apply_chrome(embed, accent=ui.accent_for_level(conf.level),
                    plan_id=plan_v2.plan_id if plan_v2 else None)
    return embed
