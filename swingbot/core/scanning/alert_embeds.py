"""Primary scan alert embed renderers."""
import json
import logging
from datetime import datetime, timezone

import discord

from swingbot import config
from swingbot.core.analytics.rank import follow_breakdown, follow_score
from swingbot.core.market import opex
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.scanning import embed_theme as theme

from .snapshots import _snapshot_and_diff
from .requirements import _confidence_block, _sources_str, confidence_color
from .plan_table import (_build_trade_plan_table, _v2_plan, badge_field_for,
                         quality_lines, plan_numbers_for_display, leg_rows)


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
    # A v2-plan-carrying item gets a level/badge chip prefix on its title
    # ("5️⃣ ✅ VALIDATED · ...") so pedigree is visible before opening the
    # embed at all; items with no v2 plan keep today's plain title.
    # v32 Task 11: was a tier chip (🅰/🅱/🅲); tier is retired in favour of
    # plan_v2.confidence_level.
    chip_prefix = f"{theme.level_chip(plan_v2.confidence_level)} {theme.badge_chip(plan_v2.badge)} · " if plan_v2 is not None else ""
    title = f"{chip_prefix}{needs_review_marker}{priority_marker}{'🟢' if is_bull else '🔴'} {direction} — {result.ticker}"
    if plan_v2 is not None:
        # Badge/level dominates the color once a v2 plan exists -- "did this
        # clear the validation bar, and how confident is it" outranks the
        # legacy scan-time confidence-level color below.
        embed_color = theme.plan_color(plan_v2.badge, plan_v2.confidence_level)
    else:
        # Embed color highlights CONFIDENCE (red=lowest -> green=highest) when
        # every requirement is met; a scenario still missing one or more is
        # always shown in neutral gray regardless of its score, so "this one
        # needs a second look" reads at a glance from the color alone, before
        # even opening the trade plan table where the specific failing
        # parameter(s) are marked in bold red.
        embed_color = confidence_color(conf.level) if all_ok else discord.Color.from_rgb(149, 165, 166)
    embed = discord.Embed(title=title, color=embed_color)

    sections: dict[str, list[tuple]] = {k: [] for k in theme.SECTION_ORDER}

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

    if plan_v2 is not None and plan_v2.badge == "WEAK":
        # First field on the embed for any WEAK plan, both layouts -- a
        # single-line caution replacing the old multi-line badge_field_for
        # block (see the `else:` branch below, which suppresses that field
        # for WEAK so this doesn't duplicate it).
        stats = plan_v2.badge_stats or {}
        wr = stats.get("win_rate", 0.0)
        n = stats.get("n", 0)
        sections["headline"].append((
            "⚠️ WEAK", f"OOS WR {wr:.1f}% (N={n}), below the 80% bar. Extra care.", False,
        ))

    if compact:
        # One condensed line replaces B2's two separate pedigree fields
        # (badge_field_for + quality_lines) -- fewer fields is the whole
        # point of compact mode.
        if plan_v2 is not None:
            stats = plan_v2.badge_stats or {}
            oos_bit = f" (OOS N={stats.get('n', 0)} WR {stats.get('win_rate', 0):.1f}%)" if stats else ""
            quality_line = f"Level {plan_v2.confidence_level} · {plan_v2.quality_score}/100 · {theme.badge_chip(plan_v2.badge)}{oos_bit}"
            sections["quality"].append(("📐 Quality", quality_line, False))
    else:
        badge_field = badge_field_for(plan_v2)
        # WEAK's own badge_field is suppressed here -- the headline block
        # above already covers it (single-line, first-positioned); appending
        # it again here would duplicate the "⚠️ WEAK" field. VALIDATED is
        # unaffected. quality_lines(...) is independent of badge and must
        # keep rendering for WEAK plans, so it's no longer nested under the
        # badge_field check.
        if badge_field is not None and plan_v2.badge != "WEAK":
            sections["quality"].append((badge_field[0], badge_field[1], False))
        quality_field = quality_lines(plan_v2)
        if quality_field is not None:
            sections["quality"].append((quality_field[0], quality_field[1], False))

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
        sections["quality"].append(("🧭 Follow score", f"{theme.follow_chip(score)}\n{breakdown_line}", False))

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
    sections["headline"].append(("Confidence", _confidence_block(conf), True))

    if not all_ok:
        unmet = ", ".join(r.label for r in item.requirements if not r.passed)
        sections["warnings"].append((
            "⚠️ Not yet a clean setup",
            f"Doesn't meet: {unmet}. Shown for visibility -- see the trade plan below for exactly why "
            "(marked in bold red); not logged as a paper trade and won't auto-alert until it clears these.",
            False,
        ))

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

    v2_priced = config.PLAN_ENGINE_V2 == "on" and plan_v2 is not None
    plan_field_name = "🎯 Trade plan (v2)" if v2_priced else "🎯 Trade plan"
    sections["plan"].append((plan_field_name, _build_trade_plan_table(item), False))

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

    for key in theme.SECTION_ORDER:
        for name, value, inline in sections[key]:
            embed.add_field(name=name, value=value, inline=inline)

    embed.description = explanation[:4000]
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

    A colored Embed rather than a plain string -- the color bar is the
    fastest long/short signal on a phone, matching the SPA table's own
    direction convention (sb-direction-arrow: long=green/▲, short=red/▼,
    the one recorded exception to green/red meaning outcome rather than
    direction). Entry/TP1/TP2/SL are packed onto ONE line, each carrying its
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
    color = discord.Color.green() if is_bull else discord.Color.red()

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

    # Embed titles can't carry color -- an ```ansi code block is the only
    # place Discord renders one, so the colored direction triangle lives as
    # the description's first line (title keeps its own plain-text copy for
    # notification previews, which strip embeds down to the title).
    ansi_code = 32 if is_bull else 31
    direction_block = f"```ansi\n[1;{ansi_code}m{arrow} {direction} — {result.ticker}[0m\n```"

    return discord.Embed(
        title=f"{arrow} {direction} — {result.ticker}",
        description=(
            f"{direction_block}"
            f"Confidence: {conf.label} (Lv{conf.level}/5, {conf.score}/100)\n"
            f"Horizon: {result.horizon_label}\n"
            f"Setup: {setup}\n\n"
            f"{plan_line}"
        ),
        color=color,
    )
