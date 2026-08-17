"""Factor registry for the unified confidence score (v32).

One pure function per factor: (FactorContext) -> FactorResult | None.
Returning None means "this factor had no input to read" and the factor is
omitted from the breakdown entirely -- an absent reading must never render
as a real one that scored zero (the rule quality.py:107-111 already states).

Weights live in the FactorResult each function returns, so re-weighting on
TRAIN evidence never edits control flow.

The kept factor set and the reasoning behind every drop is
docs/superpowers/plans/v32-factor-reconciliation.md (Task 1).
"""
from __future__ import annotations

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
