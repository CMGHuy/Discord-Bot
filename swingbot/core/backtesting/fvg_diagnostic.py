"""v143 FVG (bullish) badge diagnostic: the pure logic.

Research tooling. Nothing under swingbot/ imports this module (pinned by
tests/backtesting/test_fvg_diagnostic_import_guard.py); the one caller is
scripts/backtest/measure_fvg_bullish_diagnostic.py.

NO LOOKAHEAD: every feature reads df.iloc[:i + 1] only, i the signal bar.
Only `outcome` walks forward, and it is the thing being measured.

Spec: docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md
"""
from __future__ import annotations

import dataclasses
import math

from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.quality import atr_percentile, score_plan
from swingbot.core.scanning.regime import get_htf_bias

STRATEGY = "FVG (bullish)"
TRAIN = ("2020-01-01", "2023-12-31")
SMA_BARS = 200
ROLE_TARGET, ROLE_STOP, ROLE_NONE = "target", "stop", "unidentified"
GAP_FEATURES = ("gap_age", "gap_height_atr", "displacement", "gap_open")


# --- features (window = df.iloc[:i + 1] only) --------------------------------

@dataclasses.dataclass(frozen=True)
class SignalContext:
    """What the replay knew about one plan at its signal bar, beyond the plan:
    the scenario's own clustered target and stop levels with the sources
    behind each (levels.Scenario.take_profit / target_sources / stop_loss /
    stop_sources, captured at plan build), the live confluence tolerance in
    percent, the bar the replay's cached level map was built on (never later
    than the signal bar; None = the signal bar), and the two per-trade
    readings the driver computes."""
    target: float | None
    target_sources: tuple
    stop: float | None
    stop_sources: tuple
    tolerance_pct: float
    map_bar: int | None = None
    earnings_distance: int | None = None
    confluence_count: int | None = None


def atr14_at(df, i) -> float | None:
    """ATR14 at the signal bar, or None when it is not a positive number."""
    value = float(atr(df.iloc[:i + 1], 14).iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def _nearest(gaps, level, tolerance_pct):
    """The gap whose mid is nearest `level`, when it lies within
    `tolerance_pct` percent of the level -- the comparison
    levels.count_confirming_strategies makes."""
    if not level or level <= 0:
        return None
    best = min(gaps, key=lambda gap: abs(gap["mid"] - level), default=None)
    if best is None or abs(best["mid"] - level) / level * 100 > tolerance_pct:
        return None
    return best


def match_gap(gaps, ctx) -> tuple:
    """(gap, role): the unfilled BULLISH gap that made FVG a source of this
    plan. The scan labels a plan from the sources clustered into its
    scenario's target level, then its stop level, so a level is tried only
    when "FVG (bullish)" is among its sources: target first, then stop. The
    gap is the one whose mid is nearest that level, within the confluence
    tolerance of it. Otherwise (None, "unidentified")."""
    bullish = [gap for gap in gaps if gap["direction"] == "bullish"]
    for level, sources, role in ((ctx.target, ctx.target_sources, ROLE_TARGET),
                                 (ctx.stop, ctx.stop_sources, ROLE_STOP)):
        if STRATEGY not in sources:
            continue
        gap = _nearest(bullish, level, ctx.tolerance_pct)
        if gap is not None:
            return gap, role
    return None, ROLE_NONE


def gap_is_open(gaps, gap) -> bool:
    """True when `gaps` still holds the same gap: same formation bar, same
    direction."""
    return any(g["bar_index"] == gap["bar_index"] and g["direction"] == gap["direction"]
               for g in gaps)


def gap_features(df, i, gap, atr_val) -> dict:
    """Features 1-3 and 9 for an identified gap. Age, height and displacement
    are read at the signal bar; `gap_open` is whether the finder still
    returns the gap on bars <= i."""
    window = df.iloc[:i + 1]
    return {
        "gap_age": int(i - gap["bar_index"]),
        "gap_height_atr": (gap["top"] - gap["bottom"]) / atr_val if atr_val else None,
        "displacement": bool(fvg.is_displacement_gap(
            window, gap, fvg.DEFAULT_DISPLACEMENT_ATR_K)),
        "gap_open": gap_is_open(fvg.find_fair_value_gaps_detailed(window), gap),
    }


def entry_reference(plan) -> float:
    """The price 1R is measured from (acceptance.arm_trade_from_plan's rule)."""
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def trend_aligned(df, i, direction) -> bool | None:
    """close > SMA200 for a bullish plan, close < SMA200 for a bearish one."""
    closes = df["Close"].values[:i + 1]
    if len(closes) < SMA_BARS:
        return None
    sma, close = float(closes[-SMA_BARS:].mean()), float(closes[-1])
    return close > sma if direction == "bullish" else close < sma


def target_confluence_count(df, i, horizon_key, target, tolerance_pct) -> int:
    """Strategy families whose own level lies within `tolerance_pct` of the
    scenario's target, on bars <= i: the number the live scan stores as
    item.target_confluence[0] (scanning/analyze.py). 0 without a target."""
    window = df.iloc[:i + 1]
    close = float(window["Close"].iloc[-1])
    return levels.count_confirming_strategies(
        window, HORIZONS[horizon_key], close, target, tolerance_pct=tolerance_pct)[0]


def volume_ratio(window) -> float | None:
    """Last bar's volume over its 20-bar mean, as _build_quality_inputs has it."""
    if len(window) < 20:
        return None
    average = window["Volume"].rolling(20).mean().iloc[-1]
    return float(window["Volume"].iloc[-1] / average) if average else None


def quality_inputs(df, i, plan, confluence_count) -> dict:
    """score_plan's inputs, built the way scanning.analyze._build_quality_inputs
    builds them, from bars <= i of this ticker only. Market regime,
    relative-strength percentile and breadth need the whole market at that
    date and stay None (the scorer's neutral defaults)."""
    window = df.iloc[:i + 1]
    close = float(window["Close"].iloc[-1])
    bias = get_htf_bias(window, plan.horizon_key)
    return {
        "regime": None,
        "htf_bias": bias["bias"] if bias else None,
        "confluence_count": confluence_count,
        "volume_ratio": volume_ratio(window),
        "atr_pct": atr_percentile(window),
        "trigger_distance_pct": abs(plan.trigger_price - close) / close * 100,
        "rs_percentile": None,
        "breadth": None,
    }


def replay_quality(df, i, plan, confluence_count) -> int | None:
    """The live scorer on the causal inputs: a REPLAY quality score, not the
    live one. None without a confluence count; one is never made up."""
    if confluence_count is None:
        return None
    inputs = quality_inputs(df, i, plan, confluence_count)
    return score_plan(direction=plan.direction, badge_status=plan.badge, **inputs).score


def plan_features(df, i, plan, atr_val, confluence_count=None) -> dict:
    """Features 4-7. An unusable ATR14 leaves 4 and 7 not computable."""
    close = float(df["Close"].values[i])
    has_atr = atr_val is not None
    return {
        "stop_atr": abs(entry_reference(plan) - plan.stop_loss) / atr_val if has_atr else None,
        "quality": replay_quality(df, i, plan, confluence_count),
        "trend_aligned": trend_aligned(df, i, plan.direction),
        "volatility": atr_val / close if has_atr and close > 0 else None,
    }


def earnings_distance(signal_pos, reaction_positions) -> int | None:
    """Sessions to the next earnings reaction, v82's exposure definition:
    None unless the signal sits inside the ticker's covered span."""
    if signal_pos is None or not reaction_positions:
        return None
    if not reaction_positions[0] <= signal_pos <= reaction_positions[-1]:
        return None
    return next_reaction_distance(signal_pos, reaction_positions)


def map_gaps(df, i, ctx) -> list:
    """The finder's gaps on the window the level map was built on. The replay
    reuses one map for up to LEVEL_REFRESH_BARS bars, so the gap behind a
    level's FVG source is looked up where the map saw it -- never past bar i."""
    map_bar = i if ctx.map_bar is None else min(ctx.map_bar, i)
    return fvg.find_fair_value_gaps_detailed(df.iloc[:map_bar + 1])


def features(df, i, plan, ctx) -> dict:
    """All nine features plus fvg_role, from bars <= i. None = not computable."""
    atr_val = atr14_at(df, i)
    gap, role = match_gap(map_gaps(df, i, ctx), ctx)
    out = {"fvg_role": role, **dict.fromkeys(GAP_FEATURES)}
    if gap is not None:
        out.update(gap_features(df, i, gap, atr_val))
    out.update(plan_features(df, i, plan, atr_val, ctx.confluence_count))
    out["earnings_distance"] = ctx.earnings_distance
    return out
