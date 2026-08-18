"""Factor registry for the unified confidence score (v32).

One pure function per factor: (FactorContext) -> FactorResult | None.
Returning None means "this factor had no input to read" and the factor is
omitted from the breakdown entirely -- an absent reading must never render
as a real one that scored zero (the rule quality.py:107-111 already states).

Weights live in the FactorResult each function returns, so re-weighting on
TRAIN evidence never edits control flow.

The kept factor set and the reasoning behind every drop is
docs/superpowers/plans/implemented/v32-factor-reconciliation.md (Task 1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from swingbot import config
from swingbot.core.market.candlestick_patterns import detect_confirming_pattern
from swingbot.core.market.volatility import (
    adx_trend_strength, macd_momentum_aligned, rsi_trend_aligned,
    squeeze_breakout_confirmation,
)


@dataclass(frozen=True)
class FactorResult:
    name: str
    points: int
    line: str


@dataclass
class FactorContext:
    """Everything any factor may read. All optional: a factor whose inputs
    are missing returns None rather than inventing a neutral value."""
    scenario: object = None
    df: object = None
    regime_trend: str | None = None
    htf_bias: str | None = None
    rs_percentile: float | None = None
    mtf: int | None = None
    breadth: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    trigger_distance_pct: float | None = None
    badge_status: str | None = None
    gap_fragile: bool = False
    macro_verdict: dict | None = None
    target_count: int = 0
    target_families: list = field(default_factory=list)
    stop_count: int = 0
    stop_families: list = field(default_factory=list)


Factor = Callable[[FactorContext], "FactorResult | None"]

FACTORS: list[Factor] = []


def run_factors(factors: list[Factor], ctx: FactorContext) -> tuple[int, dict]:
    """Returns (total_points, {name: line}). Factors returning None are
    omitted from both."""
    total = 0
    breakdown: dict[str, str] = {}
    for fn in factors:
        result = fn(ctx)
        if result is None:
            continue
        total += result.points
        breakdown[result.name] = result.line
    return total, breakdown


# --- confidence.py factors (Task 3) -----------------------------------
#
# Design note shared by every factor below: the original confidence.py
# scored a "neutral" fallback point value (e.g. 7/15, 5/10) whenever its
# input was missing or its underlying signal had insufficient history --
# baking "no data" and "genuinely middling data" into the same number. This
# registry's contract (Task 2) is stricter: a factor with nothing to read
# returns None and is omitted from the breakdown entirely, never rendered as
# a real reading that happened to score a neutral value. So every "neutral
# fallback" branch below became `return None` instead; every branch where
# the original scored a REAL 0 (a genuine, computed disagreement) is
# preserved as a real FactorResult(points=0, ...).


def factor_target_distance(ctx: FactorContext) -> FactorResult | None:
    if ctx.scenario is None:
        return None
    min_reward = config.MIN_REWARD_PCT if config.MIN_REWARD_PCT > 0 else 5.0
    ratio = ctx.scenario.target_distance_pct / min_reward
    points = min(20, round(10 * ratio))
    return FactorResult(
        "Target distance quality",
        points,
        f"{ctx.scenario.target_distance_pct:.1f}% away "
        f"({ratio:.1f}x the {min_reward:.0f}% minimum) (+{points})",
    )


def factor_stop_confluence(ctx: FactorContext) -> FactorResult | None:
    points = min(15, 5 * ctx.stop_count)
    families = ", ".join(ctx.stop_families) if ctx.stop_families else "none"
    plural = "y" if ctx.stop_count == 1 else "ies"
    return FactorResult(
        "Stop level confluence",
        points,
        f"{ctx.stop_count} strateg{plural} agree: {families} (+{points})",
    )


def factor_regime(ctx: FactorContext) -> FactorResult | None:
    if ctx.scenario is None or ctx.regime_trend is None:
        return None
    if ctx.regime_trend == ctx.scenario.direction:
        return FactorResult("Market regime alignment", 15,
                            f"aligned with {ctx.regime_trend} market regime (+15)")
    return FactorResult("Market regime alignment", 0,
                        f"⚠️ counter to {ctx.regime_trend} market regime (+0)")


def factor_adx(ctx: FactorContext) -> FactorResult | None:
    if ctx.df is None:
        return None
    info = adx_trend_strength(ctx.df)
    if info["adx"] is None:
        return None
    if info["strong"]:
        points = 15
    elif info["trending"]:
        points = 8
    else:
        points = 0
    return FactorResult("ADX trend strength", points,
                        f"ADX {info['adx']} ({info['label']}) (+{points})")


def factor_macd(ctx: FactorContext) -> FactorResult | None:
    if ctx.df is None or ctx.scenario is None:
        return None
    mom = macd_momentum_aligned(ctx.df, ctx.scenario.direction)
    if mom["macd_val"] is None:
        return None
    direction = ctx.scenario.direction
    if mom["strength"] == "strong":
        points = 15
        line = (f"histogram {'positive & rising' if direction == 'bullish' else 'negative & falling'} "
                f"(MACD {mom['macd_val']:+.4f}, hist {mom['histogram']:+.4f}) (+{points})")
    elif mom["strength"] == "moderate":
        points = 10
        line = (f"histogram on the {'positive' if direction == 'bullish' else 'negative'} side "
                f"(MACD {mom['macd_val']:+.4f}, hist {mom['histogram']:+.4f}) (+{points})")
    elif mom["strength"] == "weak":
        points = 5
        line = (f"MACD {'above' if direction == 'bullish' else 'below'} signal line only "
                f"(hist {mom['histogram']:+.4f}) (+{points})")
    else:
        points = 0
        line = f"⚠️ MACD momentum opposes {direction} direction (+0)"
    return FactorResult("MACD momentum", points, line)


def factor_rsi(ctx: FactorContext) -> FactorResult | None:
    if ctx.df is None or ctx.scenario is None:
        return None
    rsi_mom = rsi_trend_aligned(ctx.df, ctx.scenario.direction)
    if rsi_mom["rsi_val"] is None:
        return None
    direction = ctx.scenario.direction
    if rsi_mom["strength"] == "strong":
        points = 10
        line = (f"RSI {rsi_mom['rsi_val']} on the {'bullish' if direction == 'bullish' else 'bearish'} "
                f"side of 50 and still moving that way (+{points})")
    elif rsi_mom["strength"] == "moderate":
        points = 6
        line = f"RSI {rsi_mom['rsi_val']} on the expected side of 50 (+{points})"
    elif rsi_mom["strength"] == "weak":
        points = 3
        line = f"RSI {rsi_mom['rsi_val']} near the neutral midline -- neither confirms nor opposes (+{points})"
    else:
        points = 0
        line = f"⚠️ RSI {rsi_mom['rsi_val']} opposes {direction} direction (+0)"
    return FactorResult("RSI trend alignment", points, line)


def factor_squeeze(ctx: FactorContext) -> FactorResult | None:
    if ctx.df is None or ctx.scenario is None:
        return None
    squeeze = squeeze_breakout_confirmation(ctx.df, ctx.scenario.direction)
    if squeeze["confirmed"]:
        points = 10
        line = (f"TTM Squeeze fired -- BBands broke outside Keltner Channel "
                f"on {squeeze['width_pct']:.1f}% width, 1.5x+ volume in the "
                f"{ctx.scenario.direction} direction (+{points})")
        if "Bollinger Squeeze Breakout" not in ctx.scenario.target_sources:
            ctx.scenario.target_sources.append("Bollinger Squeeze Breakout")
    elif squeeze["is_squeeze"]:
        points = 5
        line = (f"squeeze ON (BBands inside Keltner Channel, width {squeeze['width_pct']:.1f}%) "
                f"-- awaiting breakout direction (+{points})")
    else:
        points = 0
        line = "no squeeze/breakout confirmation right now (+0)"
    return FactorResult("TTM Squeeze + volume breakout", points, line)


def factor_candlestick(ctx: FactorContext) -> FactorResult | None:
    if ctx.df is None or ctx.scenario is None:
        return None
    pattern = detect_confirming_pattern(ctx.df, ctx.scenario.direction)
    if pattern["confirmed"]:
        points = 10 if pattern["bars_ago"] == 0 else 6
        when = "today's candle" if pattern["bars_ago"] == 0 else "yesterday's candle"
        line = f"{pattern['pattern']} on {when} confirms {ctx.scenario.direction} (+{points})"
        source_label = f"Candlestick: {pattern['pattern']}"
        if source_label not in ctx.scenario.target_sources:
            ctx.scenario.target_sources.append(source_label)
    else:
        points = 0
        line = "no confirming pattern on the most recent candle(s) (+0)"
    return FactorResult("Candlestick pattern", points, line)


def factor_tight_stop(ctx: FactorContext) -> FactorResult | None:
    if ctx.scenario is None:
        return None
    if not (getattr(ctx.scenario, "tight_stop", False)
            and getattr(ctx.scenario, "atr_floor_pct", 0) > 0):
        return None
    shortfall_pct = ((ctx.scenario.atr_floor_pct - ctx.scenario.stop_distance_pct)
                     / ctx.scenario.atr_floor_pct)
    points = -min(15, round(shortfall_pct * 15))
    return FactorResult(
        "Tight stop penalty", points,
        f"⚠️ stop {ctx.scenario.stop_distance_pct:.1f}% away is below the ATR noise floor "
        f"({ctx.scenario.atr_floor_pct:.1f}%) — likely to get clipped by normal volatility "
        f"-> {points} quality pts",
    )


# --- quality.py components (Task 4). Point ranges carried over verbatim
# from quality.py:114-129 -- this task introduces no weight change;
# re-weighting happens in Task 9 on TRAIN evidence. RS/MTF/breadth were
# already None-safe in quality.py's own score_plan (which only calls their
# scoring function when the input isn't None); every other component here
# follows the same "None input -> return None" rule Task 3 established,
# distinguishing a genuinely-known reading that happens to score low from
# an input that was never available.


def factor_rs(ctx: FactorContext) -> FactorResult | None:
    if ctx.rs_percentile is None:
        return None
    points = int(round(max(0.0, min(ctx.rs_percentile - 50.0, 50.0)) / 5.0))
    return FactorResult(
        "Relative strength", points,
        f"RS percentile {ctx.rs_percentile:.0f} vs the scanned universe (+{points})",
    )


def factor_mtf(ctx: FactorContext) -> FactorResult | None:
    if ctx.mtf is None:
        return None
    points = {0: 0, 1: 3, 2: 6, 3: 10}.get(int(ctx.mtf), 0)
    return FactorResult(
        "Multi-timeframe alignment", points,
        f"{int(ctx.mtf)}/3 higher timeframes agree (+{points})",
    )


def factor_breadth(ctx: FactorContext) -> FactorResult | None:
    if ctx.breadth is None:
        return None
    points = int(round(max(0.0, min(ctx.breadth - 40.0, 20.0)) / 4.0))
    return FactorResult(
        "Market breadth", points,
        f"{ctx.breadth:.0f}% of the universe above its 50 EMA (+{points})",
    )


def factor_htf(ctx: FactorContext) -> FactorResult | None:
    if ctx.scenario is None or ctx.htf_bias not in ("bullish", "bearish"):
        return None
    if ctx.htf_bias == ctx.scenario.direction:
        return FactorResult("HTF bias", 15, f"HTF bias {ctx.htf_bias} agrees (+15)")
    return FactorResult("HTF bias", 0, f"⚠️ HTF bias {ctx.htf_bias} disagrees (+0)")


def factor_volume(ctx: FactorContext) -> FactorResult | None:
    if ctx.volume_ratio is None or not math.isfinite(ctx.volume_ratio):
        return None
    if ctx.volume_ratio >= 2.0:
        points = 10
    elif ctx.volume_ratio >= 1.2:
        points = 8
    elif ctx.volume_ratio >= 0.8:
        points = 4
    else:
        points = 0
    return FactorResult("Volume ratio", points, f"{ctx.volume_ratio:.2f}x average volume (+{points})")


def factor_atr_percentile(ctx: FactorContext) -> FactorResult | None:
    if ctx.atr_pct is None:
        return None
    if ctx.atr_pct >= 0.9:
        points = 0
    elif ctx.atr_pct >= 0.7:
        points = 5
    else:
        points = 10
    return FactorResult("ATR percentile", points,
                        f"ATR at the {ctx.atr_pct * 100:.0f}th percentile (+{points})")


def factor_trigger_distance(ctx: FactorContext) -> FactorResult | None:
    if ctx.trigger_distance_pct is None:
        return None
    if ctx.trigger_distance_pct <= 0.5:
        points = 10
    elif ctx.trigger_distance_pct <= 1.5:
        points = 6
    elif ctx.trigger_distance_pct <= 3.0:
        points = 3
    else:
        points = 0
    return FactorResult("Trigger distance", points,
                        f"{ctx.trigger_distance_pct:.1f}% from the entry trigger (+{points})")


def factor_badge(ctx: FactorContext) -> FactorResult | None:
    if ctx.badge_status is None:
        return None
    points = 20 if ctx.badge_status == "VALIDATED" else 0
    return FactorResult("Badge status", points, f"badge {ctx.badge_status} (+{points})")


def factor_gap(ctx: FactorContext) -> FactorResult | None:
    if not ctx.gap_fragile:
        return None
    return FactorResult("Gap penalty", -10, "⚠️ fragile gap risk (-10)")


def factor_target_confluence_quality(ctx: FactorContext) -> FactorResult | None:
    """Renamed from quality.component_confluence during Task 1's
    reconciliation to keep it visibly distinct, in the breakdown, from the
    honesty-cap base level -- both derive from the same target_count, a
    deliberate, flagged (not silently resolved) overlap. See
    docs/superpowers/plans/implemented/v32-factor-reconciliation.md."""
    count = max(0, int(ctx.target_count))
    points = 20 if count >= 4 else {0: 0, 1: 7, 2: 12, 3: 16}[count]
    return FactorResult(
        "Target confluence quality", points,
        f"{count} strateg{'y' if count == 1 else 'ies'} confirm the target (+{points})",
    )


# v32 Task 9: TRAIN factor-lift measurement (data/v32_train_lift.json, 4337
# trades) found NO factor with real, positively-signed, statistically
# distinguishable win-rate lift:
#   - 13 factors measured, Wilson-overlapping (indistinguishable from zero
#     lift): target_distance, stop_confluence, target_confluence_quality,
#     htf, adx, macd, squeeze, candlestick, mtf, volume, atr_percentile,
#     trigger_distance, badge, tight_stop.
#   - 1 factor measured with a REAL, non-overlapping lift, but the WRONG
#     sign: rsi (-0.056 -- higher "RSI confirms direction" points correlate
#     with a LOWER win rate, the opposite of its designed premise). Kept as
#     a positively-weighted factor with a flipped sign would be exactly the
#     post-hoc data-dredged rationalization this plan's TRAIN-derived-
#     weights discipline exists to prevent.
#   - 3 factors were never measurable at all with this repo's cache, not
#     measured-and-rejected: regime (needs a historical SPY feed this
#     harness doesn't reconstruct -- the offline quality-score decile audit
#     under scripts/reports/ documents the same limitation), rs and breadth
#     (both need a historical per-date cross-sectional universe
#     reconstruction the cache doesn't retain). Per Task 9's own rule
#     ("assign points from measured
#     lift"), no measurement means no basis to assign a weight either way --
#     these remain real candidates for a future spec once a way to measure
#     them exists, not falsified by this TRAIN run.
#
# Every function above stays defined and tested -- correct, validated
# implementations that simply didn't earn inclusion in the ACTIVE registry
# on this evidence, not broken code to delete. Only factor_gap ships,
# unchanged from Task 4: it never fires today (gap_fragile is never wired
# by any caller, live or offline) so it costs nothing to include, and
# dropping genuinely-untested infrastructure serves no purpose the way
# dropping an unsupported WEIGHT does.
#
# Full reasoning, and the user's explicit sign-off on this near-empty
# result (confirmed across three separate questions given how much it
# changes): docs/superpowers/plans/implemented/v32-train-preregistration.md.


# --- v33 Task 5: 6m macro-anchor alignment ------------------------------

_MACRO_ALIGNMENT_POINTS = 10   # provisional; re-derived in v33 Task 7


def factor_macro_alignment(ctx: FactorContext) -> FactorResult | None:
    """Agreement with the 6m macro anchor. Never blocks -- only the adjacent
    check gates. Exempt horizons return None so they are omitted from the
    breakdown rather than scored zero."""
    verdict = ctx.macro_verdict
    if not verdict or verdict["status"] == "exempt":
        return None
    if verdict["status"] == "aligned":
        return FactorResult(
            "Macro trend (6m)", _MACRO_ALIGNMENT_POINTS,
            f"agrees with the 6m {verdict['trend']} trend "
            f"(+{_MACRO_ALIGNMENT_POINTS})")
    return FactorResult(
        "Macro trend (6m)", 0,
        f"⚠️ counter to the 6m {verdict['trend']} trend (+0)")


FACTORS[:] = [
    factor_gap,
    # Provisional, unlike factor_gap and unlike every excluded factor above:
    # v33 Task 1's TRAIN measurement of the 6m macro anchor found only
    # +2.1pp lift, Wilson-overlapping (n_opp=56) -- currently
    # indistinguishable from the 13 factors already excluded above on the
    # same "no measured positive lift" grounds. Registered anyway per this
    # task's spec so v33 Task 7 can re-derive (or zero out) its weight from
    # a real TRAIN sweep before VALIDATION. UNIFIED_CONFIDENCE is
    # default-off, so this has zero live effect either way today.
    factor_macro_alignment,
]
