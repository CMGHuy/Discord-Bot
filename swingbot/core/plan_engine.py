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


# ---------------------------------------------------------------------------
# Stop-entry trigger + expiry semantics -- single source of truth for a
# pending stop_entry plan's bar-by-bar fate. Phase 2's exit simulator and
# Phase 5's live plan manager both call these instead of re-deriving the
# comparisons, so keep the boundary-equality behavior exactly as documented
# below (each one was a deliberate spec choice, not an oversight).
# ---------------------------------------------------------------------------

def trigger_hit(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """True when this bar touched the stop_entry trigger. Bullish triggers
    are breakouts above trigger_price (bar_high >= trigger_price); bearish
    triggers are breakdowns below it (bar_low <= trigger_price). Touching
    the trigger exactly counts as a hit."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return bar_high >= plan.trigger_price
    return bar_low <= plan.trigger_price


def fill_price(plan: TradePlanV2, bar_open: float) -> float:
    """Worst-of fill for the bar that triggered: if the open already gapped
    through the trigger, you fill at the (worse) open; otherwise you fill
    at the trigger itself -- never better than trigger_price."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return max(bar_open, plan.trigger_price)
    return min(bar_open, plan.trigger_price)


def pending_expired(plan: TradePlanV2, bars_since_created: int) -> bool:
    """True once a still-pending stop_entry plan has waited longer than its
    expiry_bars window. Equality does not count as expired -- the plan gets
    the full expiry_bars-th bar to still trigger."""
    return bars_since_created > plan.expiry_bars


def pending_invalidated(plan: TradePlanV2, bar_close: float) -> bool:
    """True when price closes through the stop while the plan is still
    pending (trigger never fired) -- the setup's thesis broke before entry.
    Bullish: close <= stop_loss; bearish: close >= stop_loss. Closing
    exactly on the stop counts as invalidated."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return bar_close <= plan.stop_loss
    return bar_close >= plan.stop_loss


# ---------------------------------------------------------------------------
# Phase 2: exit model v2 (hybrid scale-out). simulate_exit is the shared
# bar-by-bar walk that backtest.py and (eventually) the live plan manager
# both call. Task 20 built the ENTRY phase -- how a signal becomes a filled
# trade (or a not_triggered stop_entry) -- reusing the Task 18 trigger/fill/
# expiry/invalidation helpers above rather than re-deriving them. Task 21
# adds the single-leg (scale_out=False) exit walk's win/loss cases, extracted
# verbatim from backtest.py's run_backtest loop so scale_out=False reproduces
# that reference exactly. Scratch/timeout polish and same-bar-ordering edge
# cases beyond what falls out of the verbatim extraction, plus scale-out legs,
# are Task 22+.
# ---------------------------------------------------------------------------

@dataclass
class ExitResult:
    outcome: str                 # "win"|"loss"|"scratch"|"timeout"|"not_triggered"|"no_trade"
    runner_outcome: str | None   # "runner_tp2"|"runner_trail"|"runner_be"|"runner_timeout"|None
    entry_index: int | None
    exit_index: int | None
    entry_price: float | None
    r_total: float               # sum over legs of fraction * signed_r
    legs: list                   # [{"fraction","exit_price","r","reason"}]


def _not_triggered() -> ExitResult:
    return ExitResult(
        outcome="not_triggered",
        runner_outcome=None,
        entry_index=None,
        exit_index=None,
        entry_price=None,
        r_total=0.0,
        legs=[],
    )


def _single_leg_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
) -> ExitResult:
    """Round-1 (scale_out=False) exit walk: extracted verbatim from
    backtest.py's run_backtest loop. Walks bars entry_index+1 .. min(entry_index
    + max_holding_days, n-1), tracking a break-even stop move once favorable
    excursion reaches breakeven_trigger_fraction * |tp1 - entry| (the moved
    stop only protects bars AFTER the trigger bar -- not the trigger bar
    itself). Same-bar ordering is conservative: stop is checked before target.
    win -> r = +rr where rr = |tp1 - entry| / risk; loss (stop hit pre-BE
    move) -> r = -1.0; scratch (stop hit post-BE move) -> r = 0.0; timeout ->
    r marked to the last scanned bar's close. Single leg always carries
    fraction=1.0 (round-1 has no partial exits)."""
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    stop_loss = plan.stop_loss
    tp1 = plan.tp1
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None,
                          entry_index=entry_index, exit_index=None,
                          entry_price=entry_price, r_total=0.0, legs=[])
    target_dist = abs(tp1 - entry_price)
    rr = target_dist / risk

    if is_bull:
        be_trigger = entry_price + plan.breakeven_trigger_fraction * target_dist
    else:
        be_trigger = entry_price - plan.breakeven_trigger_fraction * target_dist
    stop_moved = False

    end = min(entry_index + max_holding_days, n - 1)
    outcome, exit_price, exit_index = "timeout", None, None

    for j in range(entry_index + 1, end + 1):
        hi, lo = float(high[j]), float(low[j])
        cur_stop = entry_price if stop_moved else stop_loss
        if is_bull:
            hit_stop = lo <= cur_stop
            hit_target = hi >= tp1
            reached_trigger = hi >= be_trigger
        else:
            hit_stop = hi >= cur_stop
            hit_target = lo <= tp1
            reached_trigger = lo <= be_trigger

        # Conservative ordering: stop first (original stop still governs the
        # bar that first reaches the trigger), then target. The moved stop
        # only protects bars AFTER the trigger bar.
        if hit_stop:
            outcome = "scratch" if stop_moved else "loss"
            exit_price, exit_index = cur_stop, j
            break
        if hit_target:
            outcome, exit_price, exit_index = "win", tp1, j
            break
        if reached_trigger and not stop_moved:
            stop_moved = True

    if outcome == "timeout":
        exit_price, exit_index = float(close[end]), end

    if outcome == "win":
        r, reason = rr, "tp1"
    elif outcome == "loss":
        r, reason = -1.0, "stop"
    elif outcome == "scratch":
        r, reason = 0.0, "breakeven_stop"
    else:  # timeout
        r = (exit_price - entry_price) * sign / risk
        reason = "timeout"

    r = round(r, 3)

    return ExitResult(
        outcome=outcome,
        runner_outcome=None,
        entry_index=entry_index,
        exit_index=exit_index,
        entry_price=entry_price,
        r_total=r,
        legs=[{"fraction": 1.0, "exit_price": exit_price, "r": r, "reason": reason}],
    )


def simulate_exit(
    df,
    signal_index: int,
    plan: TradePlanV2,
    *,
    scale_out: bool = False,
    max_holding_days: int | None = None,
) -> ExitResult:
    """Shared entry + exit simulator (Tasks 18/20/21).

    ``market`` entries fill immediately at the signal bar's close.
    ``stop_entry`` entries scan forward from signal_index + 1 through the
    plan's expiry window looking for a trigger touch (Task 18's
    ``trigger_hit``/``fill_price``). If the plan invalidates (closes through
    the stop) or expires before triggering, this returns a terminal
    ``ExitResult("not_triggered", ...)``.

    Once entry is established, ``scale_out=False`` (the default) walks the
    single-leg round-1 exit (Task 21): win (TP1 touched), loss (stop hit
    before the break-even move), scratch (stop hit after the break-even
    move), or timeout -- extracted verbatim from backtest.py's run_backtest
    loop. ``scale_out=True`` (multi-leg partial exits) is Task 24+ and still
    raises NotImplementedError with entry_index/entry_price attached.
    """
    # Resolved eagerly per the interface contract -- both the single-leg
    # (Task 21) and scale-out (Task 24+) exit walks use it to bound the
    # timeout scan.
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]

    if plan.entry_type == "market":
        entry_index = signal_index
        entry_price = float(df["Close"].values[signal_index])
        if not scale_out:
            return _single_leg_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
        err = NotImplementedError(
            "simulate_exit: scale-out exit walk not implemented yet (Task 24+); "
            f"market entry established at entry_index={entry_index}, "
            f"entry_price={entry_price}"
        )
        err.entry_index = entry_index
        err.entry_price = entry_price
        raise err

    # stop_entry: scan signal_index+1 .. signal_index+plan.expiry_bars for a
    # trigger touch, watching for pre-fill invalidation along the way.
    high = df["High"].values
    low = df["Low"].values
    open_ = df["Open"].values
    close = df["Close"].values
    n = len(df)

    j = signal_index + 1
    while j < n:
        bars_since_created = j - signal_index
        if pending_expired(plan, bars_since_created):
            break
        if trigger_hit(plan, float(high[j]), float(low[j])):
            entry_index = j
            entry_price = fill_price(plan, float(open_[j]))
            if not scale_out:
                return _single_leg_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
            err = NotImplementedError(
                "simulate_exit: scale-out exit walk not implemented yet (Task 24+); "
                f"stop_entry filled at entry_index={entry_index}, "
                f"entry_price={entry_price}"
            )
            err.entry_index = entry_index
            err.entry_price = entry_price
            raise err
        if pending_invalidated(plan, float(close[j])):
            return _not_triggered()
        j += 1

    return _not_triggered()
