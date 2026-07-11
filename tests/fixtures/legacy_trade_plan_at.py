"""Frozen snapshot of backtest._trade_plan_at as it stood pre-extraction
(commit ac91654, confirmed byte-identical to 4e61a02 for this function --
Tasks 8-12 added plan_engine.py without touching backtest.py; commit ed9f559
is the one that later rewired _trade_plan_at to delegate to plan_engine),
preserved only so Task 13's parity harness has an independent "old"
implementation to diff against plan_engine.

Do not edit -- if you need to change sizing behavior, change plan_engine.py,
not this file. This module exists purely as a frozen reference point;
editing it in step with plan_engine.py would make the parity check compare
plan_engine against itself again, defeating the whole point of Task 13.

Imports only numpy and the per-horizon/per-strategy lookup tables it needs
from strategy_types.py (HORIZONS, STRATEGY_RR_OVERRIDE, SR_VOLUME_MULTIPLE --
those tables are untouched by the plan_engine extraction and are the single
source both before and after it). STRUCTURE_BUFFER_ATR and
SR_VOLUME_STRENGTH_CEILING are NOT centrally defined anywhere -- at commit
ac91654 they were local module-level constants in backtest.py (values 0.25
and 3.0; backtest.py, plan_engine.py, and trade_plan.py each still carry
their own identical copy today). They are reproduced here as literals
instead of imported from plan_engine.py, which would silently couple this
"old" reference to the "new" implementation it is supposed to be
independent of.
"""
import numpy as np

from swingbot.core.strategy_types import HORIZONS, SR_VOLUME_MULTIPLE, STRATEGY_RR_OVERRIDE

STRUCTURE_BUFFER_ATR = 0.25  # extra cushion beyond swing high/low, in units of ATR
SR_VOLUME_STRENGTH_CEILING = 3.0


def legacy_trade_plan_at(df, i, direction, strategy, horizon_key, atr_series,
                          swing_high_series=None, swing_low_series=None,
                          volume_ratio_series=None, entry_levels=None):
    """Verbatim copy of backtest._trade_plan_at's body as of commit ac91654."""
    close = df["Close"]
    entry = float(close.iloc[i])
    atr_val = float(atr_series.iloc[i])
    if not np.isfinite(atr_val) or atr_val <= 0:
        atr_val = entry * 0.02
    is_bull = direction == "bullish"
    h = HORIZONS[horizon_key]

    if strategy == "Fibonacci" and swing_high_series is not None:
        swing_high = float(swing_high_series.iloc[i])
        swing_low = float(swing_low_series.iloc[i])
        buffer = STRUCTURE_BUFFER_ATR * atr_val
        if is_bull:
            stop_loss = swing_low - buffer
            take_profit = swing_high
        else:
            stop_loss = swing_high + buffer
            take_profit = swing_low

        max_risk_amount = entry * (h["max_risk_pct"] / 100)
        risk_now = abs(entry - stop_loss)
        if risk_now > max_risk_amount:
            stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

        risk_now = abs(entry - stop_loss)
        # Per-strategy override takes priority over structure-based R:R bounds
        override_rr_fib = STRATEGY_RR_OVERRIDE.get(strategy)
        if override_rr_fib is not None:
            take_profit = entry + risk_now * override_rr_fib if is_bull else entry - risk_now * override_rr_fib
        else:
            min_rr, max_rr = h["min_structure_rr"], h["max_structure_rr"]
            reward_now = abs(take_profit - entry)
            target_rr = reward_now / risk_now if risk_now > 0 else min_rr
            target_rr = max(min_rr, min(max_rr, target_rr))
            bounded_reward = risk_now * target_rr
            take_profit = entry + bounded_reward if is_bull else entry - bounded_reward

    elif strategy == "Support/Resistance" and volume_ratio_series is not None:
        volume_ratio = float(volume_ratio_series.iloc[i])
        if not np.isfinite(volume_ratio):
            volume_ratio = SR_VOLUME_MULTIPLE

        stop_pct = h["sr_stop_pct"]
        target_min_pct, target_max_pct = h["sr_target_min_pct"], h["sr_target_max_pct"]
        strength = (volume_ratio - SR_VOLUME_MULTIPLE) / (SR_VOLUME_STRENGTH_CEILING - SR_VOLUME_MULTIPLE)
        strength = max(0.0, min(1.0, strength))
        target_pct = target_min_pct + (target_max_pct - target_min_pct) * strength

        if is_bull:
            stop_loss = entry * (1 - stop_pct / 100)
        else:
            stop_loss = entry * (1 + stop_pct / 100)
        # Apply per-strategy R:R override if set (overrides sr_target_pct calculation)
        override_rr_sr = STRATEGY_RR_OVERRIDE.get(strategy)
        if override_rr_sr is not None:
            risk = abs(entry - stop_loss)
            take_profit = entry + risk * override_rr_sr if is_bull else entry - risk * override_rr_sr
        else:
            take_profit = entry * (1 + target_pct / 100) if is_bull else entry * (1 - target_pct / 100)

    elif strategy == "Elliott Wave" and entry_levels and i in entry_levels:
        lv = entry_levels[i]
        buffer = STRUCTURE_BUFFER_ATR * atr_val
        if is_bull:
            stop_loss = lv["wave2"] - buffer
        else:
            stop_loss = lv["wave2"] + buffer

        max_risk_amount = entry * (h["max_risk_pct"] / 100)
        risk_now = abs(entry - stop_loss)
        if risk_now > max_risk_amount:
            stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

        risk_now = abs(entry - stop_loss)
        # Per-strategy override takes priority; fall back to HORIZONS reward_risk_ratio
        rr_override = STRATEGY_RR_OVERRIDE.get(strategy)
        rr = rr_override if rr_override is not None else h["reward_risk_ratio"]
        take_profit = entry + risk_now * rr if is_bull else entry - risk_now * rr

    else:
        risk_distance = h["atr_stop_multiple"] * atr_val
        # Use per-strategy R:R override if defined; otherwise fall back to HORIZONS value
        rr_override = STRATEGY_RR_OVERRIDE.get(strategy)
        rr = rr_override if rr_override is not None else h["reward_risk_ratio"]

        max_risk_amount = entry * (h["max_risk_pct"] / 100)
        if risk_distance > max_risk_amount:
            risk_distance = max_risk_amount

        if is_bull:
            stop_loss = entry - risk_distance
            take_profit = entry + risk_distance * rr
        else:
            stop_loss = entry + risk_distance
            take_profit = entry - risk_distance * rr

    return entry, stop_loss, take_profit
