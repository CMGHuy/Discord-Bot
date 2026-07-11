"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/2026-07-11-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from swingbot.core.levels import MAX_TARGET2_LEG_MULTIPLE
from swingbot.core.registry import Badge, get_badge
from swingbot.core.strategy_types import (
    BREAKEVEN_TRIGGER_FRACTION,
    HORIZONS,
    STRATEGY_RR_OVERRIDE,
)

# Same numbers backtest.py used before the extraction (parity-critical).
STRUCTURE_BUFFER_ATR = 0.25   # cushion beyond swing high/low, in ATR units
SR_VOLUME_STRENGTH_CEILING = 3.0
RR_FLOOR = 0.30               # break-even WR at 0.30 is 76.9% (strategy_types.py:211)
TRAIL_ATR_MULT = 2.5          # chandelier default; finalized by the Task 30 TRAIN grid
TP1_FRACTION = 0.5            # fixed by spec §5
DEFAULT_EXPIRY_BARS = 5


class PlanStatus:
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


_LEGAL_TRANSITIONS = {
    PlanStatus.PENDING: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.ACTIVE: {PlanStatus.PARTIAL, PlanStatus.CLOSED},
    PlanStatus.PARTIAL: {PlanStatus.CLOSED},
}


@dataclass
class TradePlanV2:
    plan_id: str
    ticker: str
    created_at: str            # ISO date of the bar/scan that created the plan
    source: str                # "strategy" | "confluence"
    strategy: str              # exact ALL_STRATEGIES string of the generating strategy
    horizon_key: str
    direction: str             # "bullish" | "bearish"
    entry_type: str            # "stop_entry" | "market"
    trigger_price: float
    entry_price: float | None
    expiry_bars: int
    stop_loss: float
    tp1: float
    tp1_fraction: float
    tp2: float | None
    breakeven_trigger_fraction: float
    trail_atr_mult: float
    quality_score: int
    quality_breakdown: list
    tier: str                  # "A" | "B" | "C"
    badge: str                 # "VALIDATED" | "WEAK"
    badge_stats: dict
    status: str
    status_history: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sizing builders — extracted verbatim from backtest._trade_plan_at so the
# backtest, live signals, and the plan manager all price identically.
# ---------------------------------------------------------------------------

def _safe_atr_value(entry: float, atr_val: float) -> float:
    if not np.isfinite(atr_val) or atr_val <= 0:
        return entry * 0.02
    return float(atr_val)


def _rr_for(strategy: str, horizon_key: str) -> float:
    rr_override = STRATEGY_RR_OVERRIDE.get(strategy)
    rr = rr_override if rr_override is not None else HORIZONS[horizon_key]["reward_risk_ratio"]
    return max(rr, RR_FLOOR)


def _atr_plan(entry, atr_val, direction, horizon_key, strategy):
    """Default volatility sizing: ATR-multiple stop, R:R-override target."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    risk_distance = h["atr_stop_multiple"] * atr_val
    rr = _rr_for(strategy, horizon_key)
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if risk_distance > max_risk_amount:
        risk_distance = max_risk_amount
    if is_bull:
        return entry - risk_distance, entry + risk_distance * rr
    return entry + risk_distance, entry - risk_distance * rr


def _fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key):
    """Structural sizing off the fib swing, risk-capped, R:R-override target."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    if is_bull:
        stop_loss, take_profit = swing_low - buffer, swing_high
    else:
        stop_loss, take_profit = swing_high + buffer, swing_low

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    risk_now = abs(entry - stop_loss)
    override = STRATEGY_RR_OVERRIDE.get("Fibonacci")
    if override is not None:
        take_profit = entry + risk_now * override if is_bull else entry - risk_now * override
    else:
        min_rr, max_rr = h["min_structure_rr"], h["max_structure_rr"]
        reward_now = abs(take_profit - entry)
        target_rr = reward_now / risk_now if risk_now > 0 else min_rr
        target_rr = max(min_rr, min(max_rr, target_rr))
        bounded_reward = risk_now * target_rr
        take_profit = entry + bounded_reward if is_bull else entry - bounded_reward
    return stop_loss, take_profit


def _sr_plan(entry, volume_ratio, direction, horizon_key):
    """Fixed-percent stop; target from volume strength unless R:R override set."""
    from swingbot.core.strategy import SR_VOLUME_MULTIPLE

    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    if not np.isfinite(volume_ratio):
        volume_ratio = SR_VOLUME_MULTIPLE

    stop_pct = h["sr_stop_pct"]
    strength = (volume_ratio - SR_VOLUME_MULTIPLE) / (SR_VOLUME_STRENGTH_CEILING - SR_VOLUME_MULTIPLE)
    strength = max(0.0, min(1.0, strength))
    target_pct = h["sr_target_min_pct"] + (h["sr_target_max_pct"] - h["sr_target_min_pct"]) * strength

    stop_loss = entry * (1 - stop_pct / 100) if is_bull else entry * (1 + stop_pct / 100)
    override = STRATEGY_RR_OVERRIDE.get("Support/Resistance")
    if override is not None:
        risk = abs(entry - stop_loss)
        take_profit = entry + risk * override if is_bull else entry - risk * override
    else:
        take_profit = entry * (1 + target_pct / 100) if is_bull else entry * (1 - target_pct / 100)
    return stop_loss, take_profit


def _elliott_plan(entry, atr_val, wave2, direction, horizon_key):
    """Stop beyond wave-2 (buffered, risk-capped); R:R-override target."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    stop_loss = wave2 - buffer if is_bull else wave2 + buffer

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    risk_now = abs(entry - stop_loss)
    rr = _rr_for("Elliott Wave", horizon_key)
    take_profit = entry + risk_now * rr if is_bull else entry - risk_now * rr
    return stop_loss, take_profit


# ---------------------------------------------------------------------------
# TP2 selection — the next structural level beyond TP1 (levels.py already
# does the clustering; this just picks a target and caps the leg).
# ---------------------------------------------------------------------------

def select_tp2(levels_above: list, levels_below: list, direction: str,
               entry: float, tp1: float) -> float | None:
    """
    First clustered level strictly beyond TP1 in the trade direction — the
    "if it keeps going" stretch target. `levels_above`/`levels_below` are
    plain price floats (already-clustered `Level.price` values, e.g. from
    `levels.build_level_map` — callers extract `.price` before calling this;
    reuse that clustering, don't reimplement it here).

    None if no level sits beyond TP1 on the trade-direction side, or if the
    TP1 -> candidate leg exceeds `MAX_TARGET2_LEG_MULTIPLE` times the
    entry -> TP1 leg — the same "don't show a wildly disproportionate
    runner" cap levels.py's own target-2 selection uses (see its docstring).
    """
    leg1 = abs(tp1 - entry)
    if leg1 <= 0:
        return None

    is_bull = direction == "bullish"
    candidates = levels_above if is_bull else levels_below
    beyond = [p for p in candidates if (p > tp1 if is_bull else p < tp1)]
    if not beyond:
        return None

    candidate = min(beyond) if is_bull else max(beyond)
    leg2 = abs(candidate - tp1)
    if leg2 > leg1 * MAX_TARGET2_LEG_MULTIPLE:
        return None
    return candidate


def build_strategy_plan(df, index, *, ticker, strategy, horizon_key,
                        direction, level_map=None) -> TradePlanV2 | None:
    """THE constructor for strategy-source plans. Returns None when the
    strategy has no valid structure at this bar (same conditions as the
    backtest reference)."""
    from swingbot.core.indicators import atr as atr_indicator
    from swingbot.core.indicators import elliott_wave3_entries

    close = float(df["Close"].iloc[index])
    atr_series = atr_indicator(df, 14)
    atr_val = _safe_atr_value(close, float(atr_series.iloc[index]))
    h = HORIZONS[horizon_key]

    if strategy == "Fibonacci":
        lookback = h["fib_lookback"]
        swing_high = float(df["High"].rolling(lookback).max().iloc[index])
        swing_low = float(df["Low"].rolling(lookback).min().iloc[index])
        if not (np.isfinite(swing_high) and np.isfinite(swing_low)):
            return None
        stop, tp1 = _fibonacci_plan(close, atr_val, swing_high, swing_low, direction, horizon_key)
    elif strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        ratio = float((df["Volume"] / vol_avg20).iloc[index])
        stop, tp1 = _sr_plan(close, ratio, direction, horizon_key)
    elif strategy == "Elliott Wave":
        _, _, entry_levels = elliott_wave3_entries(df, h["max_risk_pct"])
        if not entry_levels or index not in entry_levels:
            return None
        stop, tp1 = _elliott_plan(close, atr_val, entry_levels[index]["wave2"], direction, horizon_key)
    else:
        stop, tp1 = _atr_plan(close, atr_val, direction, horizon_key, strategy)

    if abs(close - stop) <= 0:
        return None

    entry_type = entry_type_for(strategy, "strategy")
    created_at = df.index[index].date().isoformat()
    tp2 = None
    if level_map is not None:
        supports, resistances = level_map
        levels_above = [lv.price for lv in resistances]
        levels_below = [lv.price for lv in supports]
        tp2 = select_tp2(levels_above, levels_below, direction, close, tp1)
    plan = TradePlanV2(
        plan_id=str(uuid.uuid4()), ticker=ticker, created_at=created_at,
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=direction, entry_type=entry_type, trigger_price=close,
        entry_price=close if entry_type == "market" else None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=stop, tp1=tp1,
        tp1_fraction=TP1_FRACTION, tp2=tp2,
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=TRAIL_ATR_MULT, quality_score=0, quality_breakdown=[],
        tier="C", badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    stamp_badge(plan)
    return plan


# ---------------------------------------------------------------------------
# Confluence-source plans — built from a levels.build_scenarios() Scenario
# rather than a per-bar strategy signal.
# ---------------------------------------------------------------------------

CONFLUENCE_BREAKOUT_LOOKBACK = 20  # same fixed window levels.py's own Donchian candidate uses


def scenario_is_breakout(scenario, df) -> bool:
    """
    True when hitting the scenario's own target requires price to make a
    new local extreme -- i.e. the target sits beyond the recent N-bar
    trading range (the same 20-bar Donchian-style window levels.py already
    sources a candidate level from; see collect_candidate_levels), rather
    than just completing a move inside a range that already contains it.
    Breakout-direction scenarios get a stop-entry trigger instead of an
    immediate market fill (see build_confluence_plan).

    The lookback excludes the in-progress last bar (`.shift(1)`), matching
    collect_candidate_levels's own Donchian computation.
    """
    is_bull = scenario.direction == "bullish"
    if is_bull:
        recent_extreme = df["High"].rolling(CONFLUENCE_BREAKOUT_LOOKBACK).max().shift(1).iloc[-1]
        if not np.isfinite(recent_extreme):
            return False
        return scenario.take_profit > float(recent_extreme)
    recent_extreme = df["Low"].rolling(CONFLUENCE_BREAKOUT_LOOKBACK).min().shift(1).iloc[-1]
    if not np.isfinite(recent_extreme):
        return False
    return scenario.take_profit < float(recent_extreme)


def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy) -> TradePlanV2:
    """THE constructor for confluence-source plans (a levels.build_scenarios
    Scenario). TP1 is RECOMPUTED under the unified exit policy rather than
    reusing the scenario's own target -- see spec §5; the scenario's own
    take_profit survives as tp2 only when it still lies beyond the new TP1.
    `strategy` is a placeholder attribution until Task 38 wires the real
    generating strategy through."""
    entry = scenario.entry
    is_bull = scenario.direction == "bullish"
    risk = abs(entry - scenario.stop_loss)
    rr = STRATEGY_RR_OVERRIDE.get(primary_strategy, 0.35)
    tp1 = entry + risk * rr if is_bull else entry - risk * rr

    tp2 = None
    if scenario.take_profit is not None:
        beyond_tp1 = scenario.take_profit > tp1 if is_bull else scenario.take_profit < tp1
        if beyond_tp1:
            tp2 = scenario.take_profit

    entry_type = "stop_entry" if scenario_is_breakout(scenario, df) else "market"
    created_at = df.index[-1].date().isoformat()

    plan = TradePlanV2(
        plan_id=str(uuid.uuid4()), ticker=ticker, created_at=created_at,
        source="confluence", strategy=primary_strategy, horizon_key=horizon_key,
        direction=scenario.direction, entry_type=entry_type, trigger_price=entry,
        entry_price=entry if entry_type == "market" else None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=scenario.stop_loss, tp1=tp1,
        tp1_fraction=TP1_FRACTION, tp2=tp2,
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=TRAIL_ATR_MULT, quality_score=0, quality_breakdown=[],
        tier="C", badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    stamp_badge(plan)
    return plan


# Strategy-source plans enter at the signal close ("market") — this is the
# entry the round-1 validation measured. Task 30's TRAIN grid may flip
# breakout-class strategies to stop_entry iff it clears the acceptance gates.
STRATEGY_ENTRY_TYPE: dict[str, str] = {}

# Rendered verbatim by embeds for plans whose source failed the 80% OOS bar.
WEAK_CAUTION_TEXT = (
    "⚠️ WEAK: this setup did not reach 80% win rate out-of-sample "
    "(WR {win_rate:.1f}%, N={n}). Treat with extra care — reduced size, "
    "manual confirmation recommended."
)


def entry_type_for(strategy: str, source: str) -> str:
    if source == "confluence":
        return "stop_entry"
    return STRATEGY_ENTRY_TYPE.get(strategy, "market")


def stamp_badge(plan: TradePlanV2) -> None:
    """Set badge + badge_stats from the committed validation registry."""
    b = get_badge(plan.source, plan.strategy, plan.horizon_key)
    plan.badge = b.status
    plan.badge_stats = {"status": b.status, "n": b.n, "win_rate": b.win_rate,
                        "expectancy_r": b.expectancy_r, "window": b.window}


def badge_stats_line(badge: Badge) -> str:
    window = badge.window.replace("-01-01..", "-").replace("-12-31", "") or "n/a"
    return (f"OOS {window}: N={badge.n}, WR {badge.win_rate:.1f}%, "
            f"ExpR {badge.expectancy_r:+.3f}")


def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine."""
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    plan.status_history.append({"status": new_status, "reason": reason, "at": at})
