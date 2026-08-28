"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/implemented/2026-07-11-v2-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass, field

import numpy as np

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market import opex
from swingbot.core.market.levels import MAX_TARGET2_LEG_MULTIPLE
from swingbot.core.backtesting.registry import Badge, decay_note, get_badge
from swingbot.core.market.strategy_types import (
    BREAKEVEN_TRIGGER_FRACTION,
    HORIZONS,
)
from .plan_types import (PlanStatus, TradePlanV2, effective_stop, plan_to_dict,
                         plan_from_dict, record_transition)
from . import params
from . import targets
from . import lifecycle
from . import exit_sim
from .exit_sim import (ExitResult, _not_triggered, _single_leg_exit_walk,
                       chandelier_stop, runner_floor, _scale_out_exit_walk,
                       simulate_exit)
from .lifecycle import (_lifecycle_levels, apply_level_lifecycle, trigger_hit,
                        fill_price, pending_expired, pending_invalidated)
from .targets import (select_structural_target, _safe_atr_value,
                      atr_target_candidates, fib_target_candidates,
                      sr_target_candidates, elliott_target_candidates,
                      select_tp2, _tp2_from_r)
from .params import (EXIT_V2_PARAMS, STRUCTURE_BUFFER_ATR, SR_VOLUME_STRENGTH_CEILING,
                     TRAIL_ATR_MULT, TP1_FRACTION, RUNNER_FLOOR_FRACTION,
                     DEFAULT_EXPIRY_BARS, exit_params_for,
                     _journal_entries, _resolve_stop_mult, _resolve_tp2_r,
                     _resolve_time_stop_days, _apply_quality, stamp_badge,
                     badge_stats_line)

log = logging.getLogger("swing-bot.plan_engine")

def _atr_plan(entry, atr_val, direction, horizon_key, strategy, stop_mult=None,
             candidate_levels=None):
    """Default volatility sizing: ATR-multiple stop; target is the nearest
    ATR-ladder candidate (atr_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31). Returns
    None when nothing clears the floor.
    `stop_mult` (edge E31) is an INJECTED MAE-informed adjustment factor,
    never looked up here. That is deliberate: this function is the shared
    sizing source for both live plans (build_strategy_plan) and the
    backtest (backtest._trade_plan_at), so a journal read hidden in here
    would silently price 2020 backtest trades off today's live journal.
    Callers that legitimately have a multiplier pass it in; the E33 fold
    harness will pass its own fold-train-derived value.

    Scaling `risk_distance` (rather than the stop price) keeps the stop's
    ATR-multiple exact -- the same distance feeds both the stop and, via
    select_structural_target's own risk argument, the target floor/cap.
    `strategy` is accepted but unused: the ladder is identical for all
    eight fallback strategies (kept for call-site signature parity, not
    because a per-strategy R:R table survives here -- that table is
    deleted in Task 14).
    """
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    risk_distance = h["atr_stop_multiple"] * atr_val
    if stop_mult is not None:
        risk_distance *= stop_mult
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if risk_distance > max_risk_amount:
        risk_distance = max_risk_amount
    stop_loss = entry - risk_distance if is_bull else entry + risk_distance

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit


# --- level lifecycle (P1) ---------------------------------------------------
#
# Deliberately lives HERE, next to the sizing builders, and not in either
# caller. backtest._trade_plan_at and build_strategy_plan are two separate
# plan paths, and edge-engine-v4's DATA_DRIVEN_STOPS_ENABLED scored exactly
# 0.0000 -- burning its one pre-registered validation shot -- because it
# reached only build_strategy_plan while the backtest sized through
# _trade_plan_at. Anything that touches stop/target must be shared by both or
# it is unmeasurable by construction.

def build_strategy_plan(df, index, *, ticker, strategy, horizon_key,
                        direction, level_map=None, quality_inputs=None,
                        stop_mult=None, tp2_r=None,
                        time_stop_days=None) -> TradePlanV2 | None:
    """THE constructor for strategy-source plans. Returns None when the
    strategy has no valid structure at this bar (same conditions as the
    backtest reference).

    `stop_mult` (edge E31), `tp2_r` and `time_stop_days` (edge E32): the
    MAE/MFE-derived overrides. Left None, each is resolved from the live
    journal iff config.DATA_DRIVEN_STOPS_ENABLED -- so the flag-off path
    is bit-identical to before and never opens the journal at all."""
    from swingbot.core.market.indicators import atr as atr_indicator
    from swingbot.core.market.indicators import elliott_wave3_entries

    close = float(df["Close"].iloc[index])
    atr_series = atr_indicator(df, 14)
    atr_val = _safe_atr_value(close, float(atr_series.iloc[index]))
    h = HORIZONS[horizon_key]
    applied_stop_mult = None

    if strategy == "Fibonacci":
        lookback = h["fib_lookback"]
        swing_high = float(df["High"].rolling(lookback).max().iloc[index])
        swing_low = float(df["Low"].rolling(lookback).min().iloc[index])
        if not (np.isfinite(swing_high) and np.isfinite(swing_low)):
            return None
        candidates = fib_target_candidates(df, index, h, close)
        result = _fibonacci_plan(close, atr_val, swing_high, swing_low, direction, horizon_key,
                                 candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    elif strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        ratio = float((df["Volume"] / vol_avg20).iloc[index])
        candidates = sr_target_candidates(df, index, h, close, ratio)
        result = _sr_plan(close, ratio, direction, horizon_key, candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    elif strategy == "Elliott Wave":
        _, _, entry_levels = elliott_wave3_entries(df, h["max_risk_pct"])
        if not entry_levels or index not in entry_levels:
            return None
        candidates = elliott_target_candidates(entry_levels[index], direction)
        result = _elliott_plan(close, atr_val, entry_levels[index]["wave2"], direction, horizon_key,
                               candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    else:
        # Only the genuine ATR-multiple path takes the MAE adjustment
        # (edge E31). The three branches above put their stop behind real
        # structure -- a fib swing, an Elliott wave-2 low, an S/R shelf --
        # and scaling those would slide the stop off the very structure it
        # exists to hide behind. That's a different, unvalidated idea from
        # "give the ATR stop the room this strategy's winners actually
        # used", so they stay structure-derived on purpose.
        # Opex composes ON TOP of whatever multiplier was already resolved --
        # an explicit caller override or E31's per-strategy MAE figure -- so
        # neither silently replaces the other. Off an opex day stop_mult() is
        # exactly 1.0 and this line is a no-op.
        applied_stop_mult = stop_mult if stop_mult is not None else params._resolve_stop_mult(strategy)
        _opex_stop_mult = opex.stop_mult()
        if _opex_stop_mult != 1.0:
            # Guarded rather than composed unconditionally: `None` here is
            # the contract for "no multiplier applied" and is asserted on by
            # tests/edge/test_edge_stops.py, so an unconditional `or 1.0`
            # would rewrite every ordinary plan's stop_mult_applied to 1.0.
            applied_stop_mult = (applied_stop_mult or 1.0) * _opex_stop_mult
        candidates = atr_target_candidates(close, atr_val, direction)
        result = _atr_plan(close, atr_val, direction, horizon_key, strategy,
                           stop_mult=applied_stop_mult, candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result

    # P1: the same adjuster backtest._trade_plan_at calls, with the level_map
    # this path already has (so it costs no extra level build here).
    # meta is intentionally unused for now: surfacing which level drove the
    # plan means a TradePlanV2 field, which is a persisted-schema change and a
    # separate piece of work from wiring the adjuster in.
    stop, tp1, _lifecycle_meta = apply_level_lifecycle(
        df, index, entry=close, stop=stop, tp1=tp1, atr_val=atr_val,
        direction=direction, strategy=strategy, horizon_key=horizon_key,
        level_map=level_map, candidate_levels=candidates)

    if abs(close - stop) <= 0:
        return None

    entry_type = entry_type_for(strategy, "strategy")
    created_at = df.index[index].date().isoformat()
    exit_params = params.exit_params_for(strategy)
    tp2 = None
    applied_tp2_r = None
    if exit_params["tp2"]:
        if level_map is not None:
            supports, resistances = level_map
            levels_above = [lv.price for lv in resistances]
            levels_below = [lv.price for lv in supports]
            tp2 = select_tp2(levels_above, levels_below, direction, close, tp1)
        # MFE-informed TP2 (edge E32): re-price the runner target at the
        # R-multiple this strategy's winners actually reached, when that
        # produces a valid TP2. Deliberately does NOT switch TP2 on for a
        # strategy whose exit params have none -- that on/off table is a
        # frozen TRAIN-grid result, and forcing it would be a different
        # exit model than E33 is set up to judge.
        resolved_tp2_r = tp2_r if tp2_r is not None else params._resolve_tp2_r(strategy)
        if resolved_tp2_r is not None:
            candidate = _tp2_from_r(close, stop, tp1, direction, resolved_tp2_r)
            if candidate is not None:
                tp2, applied_tp2_r = candidate, resolved_tp2_r
    plan = TradePlanV2(
        plan_id=str(uuid.uuid4()), ticker=ticker, created_at=created_at,
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=direction, entry_type=entry_type, trigger_price=close,
        entry_price=close if entry_type == "market" else None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=stop, tp1=tp1,
        tp1_fraction=TP1_FRACTION, tp2=tp2,
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=exit_params["trail_atr_mult"],
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    params.stamp_badge(plan)
    params._apply_quality(plan, quality_inputs)
    plan.stop_mult_applied = applied_stop_mult
    plan.tp2_r_applied = applied_tp2_r
    plan.time_stop_days = (time_stop_days if time_stop_days is not None
                           else params._resolve_time_stop_days(strategy))
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


def primary_strategy_for(scenario) -> str:
    """Real strategy attribution for a confluence scenario: the highest-
    priority confirming method behind its target (falling back to the stop's
    methods, then the legacy literal). Delegates the ranking to
    chart_geometry._pick_primary_source -- ONE priority list for charts,
    trade rows, and plan attribution. Imported lazily (matplotlib chain)."""
    from swingbot.core.charts.chart_geometry import _pick_primary_source
    sources = list(getattr(scenario, "target_sources", []) or []) \
        + list(getattr(scenario, "stop_sources", []) or [])
    return _pick_primary_source(sources) or "S/R Confluence"


def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy, level_map=None,
                          quality_inputs=None) -> TradePlanV2 | None:
    """THE constructor for confluence-source plans (a levels.build_scenarios
    Scenario). TP1 is a real structural level -- select_structural_target
    picks the nearest candidate that pays at least MIN_RISK_REWARD_RATIO,
    capped at MAX_RISK_REWARD_RATIO (v31). Returns None when nothing
    qualifies: there is deliberately no fallback to a fixed fraction of
    risk, since that arithmetic is exactly the bug this plan fixes.
    `primary_strategy` is the real per-scenario attribution (see
    primary_strategy_for). `level_map` is an optional (supports, resistances)
    pair from levels.build_level_map -- when absent, the only honest
    candidate is the scenario's own real target."""
    entry = scenario.entry
    is_bull = scenario.direction == "bullish"

    if level_map is not None:
        candidates = levels.target_candidates(*level_map, scenario.direction)
    else:
        candidates = [scenario.take_profit] if scenario.take_profit is not None else []

    tp1 = select_structural_target(entry, scenario.stop_loss, is_bull, candidates,
                                   config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if tp1 is None:
        return None

    if level_map is not None:
        supports, resistances = level_map
        resistances_prices = [float(lv.price) for lv in resistances]
        supports_prices = [float(lv.price) for lv in supports]
        tp2 = select_tp2(resistances_prices, supports_prices, scenario.direction, entry, tp1)
    else:
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
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    params.stamp_badge(plan)
    params._apply_quality(plan, quality_inputs)
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


# ---------------------------------------------------------------------------
# Stop-entry trigger + expiry semantics -- single source of truth for a
# pending stop_entry plan's bar-by-bar fate. Phase 2's exit simulator and
# Phase 5's live plan manager both call these instead of re-deriving the
# comparisons, so keep the boundary-equality behavior exactly as documented
# below (each one was a deliberate spec choice, not an oversight).
# ---------------------------------------------------------------------------

def _fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key,
                    candidate_levels=None):
    """Structural sizing off the fib swing, risk-capped. Target is the
    nearest real Fibonacci level (fib_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31) -- see
    select_structural_target. Returns None when no candidate clears the
    floor: no fallback to a fixed fraction of risk."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    if is_bull:
        stop_loss = swing_low - buffer
    else:
        stop_loss = swing_high + buffer

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit

def _sr_plan(entry, volume_ratio, direction, horizon_key, candidate_levels=None):
    """Fixed-percent stop. Target is the nearest real S/R candidate
    (sr_target_candidates) that pays at least MIN_RISK_REWARD_RATIO, capped
    at MAX_RISK_REWARD_RATIO (v31). Returns None when no candidate clears
    the floor."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    stop_pct = h["sr_stop_pct"]
    stop_loss = entry * (1 - stop_pct / 100) if is_bull else entry * (1 + stop_pct / 100)

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit



def _elliott_plan(entry, atr_val, wave2, direction, horizon_key, candidate_levels=None):
    """Stop beyond wave-2 (buffered, risk-capped). Target is the nearest
    real wave-3 projection (elliott_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31). Returns
    None when no candidate clears the floor."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    stop_loss = wave2 - buffer if is_bull else wave2 + buffer

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit
