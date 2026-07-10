"""
Turns a strategy signal into a concrete trade plan: entry, stop-loss,
take-profit. Three sizing methods, depending on what the strategy gives
us to work with:

  - Fibonacci signals have real market structure (the swing high/low),
    so the stop and target are placed relative to that structure.
  - Support/Resistance signals use a classic disciplined-trader sizing:
    a tight, fixed-percent stop (e.g. 7-8%, the William O'Neil "cut
    losses fast" rule) and a target that scales with breakout conviction.
  - EMA Crossover and VWAP signals don't have an obvious structural
    level, so risk is sized off ATR (volatility) with a reward:risk
    multiple, still capped at the horizon's max risk %.

Sizing parameters are read per-horizon from strategy.HORIZONS so live
alerts and backtest.py can't drift out of sync with each other.

ENTRY IS NOT ALWAYS THE CURRENT PRICE, AND ISN'T CONSTRAINED TO BE BELOW
IT EITHER. If the market has already moved away from the reference level
a strategy is based on (the fast EMA, VWAP, the exact Fibonacci level,
the broken support/resistance level), the plan suggests entering there
instead of chasing an already-extended price -- the classic "buy the
pullback" / "buy the retest" discipline. That reference level can sit on
either side of today's close (e.g. the fast EMA can be above price after
a sharp reversal), so a suggested entry of 107 when the market is at 100
is just as valid an output as one below current price -- whichever price
actually matches the strategy's structure wins, full stop. This is a
planned limit-entry reference, not a guarantee the market gets there;
`market_price` is always reported alongside so you can see the gap.

This is a mechanical, rule-based sizing -- not a guarantee the trade
will play out this way. It exists to make each alert concrete and
back-testable, not to promise an outcome.
"""
from dataclasses import dataclass

import pandas as pd

from .indicators import atr, ema, fibonacci_levels, rolling_vwap
from .strategy import HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE, compute_hvn_level
from .strategy_types import BREAKEVEN_TRIGGER_FRACTION, STRATEGY_RR_OVERRIDE

ATR_PERIOD = 14
STRUCTURE_BUFFER_ATR = 0.25  # extra cushion beyond swing high/low, in units of ATR

# How much stronger-than-minimum volume it takes to earn the FULL target range
SR_VOLUME_STRENGTH_CEILING = 3.0

# How far price must be extended from a strategy's reference level before we
# suggest waiting for a pullback/retest instead of chasing it
ENTRY_EXTENSION_THRESHOLD_PCT = 1.5

MANAGEMENT_NOTE = (
    f"After price covers {BREAKEVEN_TRIGGER_FRACTION:.0%} of the distance to target, "
    "move the stop to entry. A break-even exit is a scratch, not a loss -- this is "
    "the rule the backtest numbers assume."
)


@dataclass
class TradePlan:
    entry: float
    market_price: float
    entry_note: str
    entry_confluence: str | None
    stop_loss: float
    take_profit: float
    risk_per_share: float
    reward_per_share: float
    risk_reward_ratio: float
    method: str
    management_note: str = MANAGEMENT_NOTE


def compute_trade_plan(result, df: pd.DataFrame) -> TradePlan:
    h = HORIZONS[result.horizon_key]
    is_bull = result.trend == "bullish"
    market_price = result.close
    entry, entry_note = _suggested_entry(result, df, market_price, h)
    entry_confluence = _entry_confluence_note(entry, df, h, result.strategy)

    atr_val = float(atr(df, ATR_PERIOD).iloc[-1])
    if atr_val <= 0 or pd.isna(atr_val):
        atr_val = entry * 0.02  # fallback: 2% of price if ATR is degenerate

    if result.strategy == "Fibonacci" and "Swing high" in result.details and "Swing low" in result.details:
        stop_loss, take_profit, method = _fibonacci_plan(result, h, entry, atr_val, is_bull)

    elif result.strategy == "Support/Resistance":
        stop_loss, take_profit, method = _support_resistance_plan(result, h, entry, is_bull)

    elif result.strategy == "Elliott Wave" and ("Wave 2 low" in result.details or "Wave 2 high" in result.details):
        stop_loss, take_profit, method = _elliott_wave_plan(result, h, entry, atr_val, is_bull)

    else:
        stop_loss, take_profit, method = _volatility_plan(h, entry, atr_val, is_bull, result.strategy)

    risk_per_share = abs(entry - stop_loss)
    reward_per_share = abs(take_profit - entry)
    rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0

    return TradePlan(
        entry=round(entry, 4),
        market_price=round(market_price, 4),
        entry_note=entry_note,
        entry_confluence=entry_confluence,
        stop_loss=round(stop_loss, 4),
        take_profit=round(take_profit, 4),
        risk_per_share=round(risk_per_share, 4),
        reward_per_share=round(reward_per_share, 4),
        risk_reward_ratio=round(rr_ratio, 2),
        method=method,
    )


def _entry_confluence_note(entry: float, df, h, source_strategy: str) -> str | None:
    """
    Checks whether OTHER strategies' reference levels (excluding the one
    that actually generated this entry) line up near the suggested entry --
    independent methods agreeing on the same price zone is a stronger
    signal than the source level trivially matching itself.

    Volume Profile's High Volume Node (the price real trading volume
    actually piled up at -- see strategy.compute_hvn_level) is included
    as one of the checked levels, same as fast EMA/VWAP/Fib/S&R. This is
    what lets e.g. a Fibonacci retracement entry get flagged as
    volume-confirmed when the fib level and the HVN happen to coincide --
    a technical level is much more convincing when real trading interest
    also piled up there, not just where a formula says it should be.
    Because volume backing an entry is meaningful on its own, an HVN
    match gets its own explicit "Volume-confirmed" callout even if
    nothing else agrees; anything else still needs 2+ agreeing levels
    to be called out as a general confluence note.
    """
    levels = {}
    try:
        levels["fast EMA"] = float(ema(df["Close"], h["ema_fast"]).iloc[-1])
    except Exception:
        pass
    try:
        levels["VWAP"] = float(rolling_vwap(df, h["vwap_window"]).iloc[-1])
    except Exception:
        pass
    try:
        fib = fibonacci_levels(df, h["fib_lookback"])
        nearest_ratio, nearest_price = min(fib["levels"].items(), key=lambda kv: abs(kv[1] - entry))
        levels["Fib level"] = nearest_price
    except Exception:
        pass
    try:
        sr_lookback = h["sr_lookback"]
        levels["resistance/support"] = float(df["High"].rolling(sr_lookback).max().shift(1).iloc[-1])
    except Exception:
        pass
    hvn = None
    try:
        hvn = compute_hvn_level(df, h["sr_lookback"])
        if hvn:
            levels["Volume Profile (HVN)"] = hvn[0]
    except Exception:
        pass

    # Exclude the level that trivially matches itself (it generated the
    # entry) -- covers every strategy whose own suggested entry (see
    # _suggested_entry above) is derived from one of the 5 levels tracked
    # here, not just the 5 whose name matches 1:1. MACD and MA Ribbon both
    # fall back to "the fast EMA it's derived from" for their pullback
    # entry (same reference as EMA Crossover); Break & Retest uses the
    # broken resistance/support level (same reference as Support/
    # Resistance). RSI, RSI Divergence, Elliott Wave, and plain RSI don't
    # map to any of these 5 -- they're intentionally left unmapped (None),
    # since none of the tracked levels here would trivially coincide with
    # their own entry price anyway.
    source_key = {
        "EMA Crossover": "fast EMA", "MACD": "fast EMA", "MA Ribbon": "fast EMA",
        "VWAP": "VWAP",
        "Fibonacci": "Fib level",
        "Support/Resistance": "resistance/support", "Break & Retest": "resistance/support",
        "Volume Profile": "Volume Profile (HVN)",
    }.get(source_strategy)
    levels.pop(source_key, None)

    agreeing = [name for name, price in levels.items() if entry != 0 and abs(price - entry) / entry * 100 <= ENTRY_EXTENSION_THRESHOLD_PCT]
    volume_confirmed = "Volume Profile (HVN)" in agreeing

    if len(agreeing) >= 2:
        source_label = source_key or "source"
        return f"Confluence: {', '.join(agreeing)} independently line up near this price too -- not just the {source_label} alone."
    if volume_confirmed and hvn:
        return (
            f"Volume-confirmed: real trading volume piled up at this exact price "
            f"(High Volume Node, {hvn[1]:.0f}% of period volume) -- not just a technical level, "
            f"actual trading interest backs this entry."
        )
    return None


def _suggested_entry(result, df, market_price, h):
    """
    Picks the entry a disciplined trader would actually use: the current
    price if it's still close to the strategy's reference level, or a
    pullback/retest at that reference level if price has already run.
    """
    strategy = result.strategy

    if strategy == "EMA Crossover":
        fast_val = float(ema(df["Close"], h["ema_fast"]).iloc[-1])
        extension_pct = abs(market_price - fast_val) / market_price * 100
        if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
            return fast_val, (
                f"Pullback entry near the {h['ema_fast']}-day EMA ({fast_val:.2f}) rather than chasing "
                f"the current price, which is already {extension_pct:.1f}% extended from it."
            )
        return market_price, f"Current price is already close to the {h['ema_fast']}-day EMA -- minimal chase risk."

    if strategy == "VWAP":
        vwap_val = float(rolling_vwap(df, h["vwap_window"]).iloc[-1])
        extension_pct = abs(market_price - vwap_val) / market_price * 100
        if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
            return vwap_val, (
                f"Pullback entry near VWAP ({vwap_val:.2f}) rather than chasing the current price, "
                f"which is already {extension_pct:.1f}% extended from it."
            )
        return market_price, "Current price is already close to VWAP -- minimal chase risk."

    if strategy == "Fibonacci":
        level_price = result.details.get("Nearest level price")
        level_label = result.details.get("Nearest level", "")
        if level_price:
            return level_price, (
                f"Entry set at the precise {level_label} Fibonacci level being tested, for a clean "
                f"limit price rather than the raw close."
            )
        return market_price, "Current price (exact Fibonacci level unavailable)."

    if strategy == "Support/Resistance":
        level_key = "Resistance" if result.trend == "bullish" else "Support"
        level_price = result.details.get(level_key)
        if level_price:
            extension_pct = abs(market_price - level_price) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                other_role = "support" if result.trend == "bullish" else "resistance"
                return level_price, (
                    f"Retest entry at the broken {level_key.lower()} ({level_price:.2f}) rather than "
                    f"chasing a breakout already {extension_pct:.1f}% extended -- broken {level_key.lower()} "
                    f"often becomes {other_role} on a retest."
                )
        return market_price, "Fresh breakout -- current price is the entry, minimal extension yet."

    if strategy == "RSI":
        return market_price, (
            "Entry at current price -- RSI reversal signals are confirmed by the crossback itself, "
            "there's no separate pullback level to wait for."
        )

    if strategy == "MACD":
        # MACD itself is an oscillator (no price level), but it's derived
        # from the same fast EMA of price that EMA Crossover uses -- that's
        # the natural pullback reference here rather than chasing the bar
        # the cross/histogram-flip happened on.
        fast_p, _, _ = MACD_PERIODS_BY_HORIZON.get(result.horizon_key, (12, 26, 9))
        fast_val = float(ema(df["Close"], fast_p).iloc[-1])
        extension_pct = abs(market_price - fast_val) / market_price * 100
        if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
            return fast_val, (
                f"Pullback entry near the {fast_p}-day EMA ({fast_val:.2f}) that MACD is derived from, "
                f"rather than chasing the current price, already {extension_pct:.1f}% extended from it."
            )
        return market_price, "Current price is already close to the underlying fast EMA -- minimal chase risk."

    if strategy == "MA Ribbon":
        # details holds f"EMA{fast_p}" as its first key (see ma_ribbon_signal) --
        # pull it out by prefix instead of duplicating the horizon->period map.
        fast_val = next((v for k, v in result.details.items() if k.startswith("EMA")), None)
        if fast_val:
            extension_pct = abs(market_price - fast_val) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                return fast_val, (
                    f"Pullback entry near the fast EMA of the ribbon ({fast_val:.2f}) rather than chasing "
                    f"the current price, already {extension_pct:.1f}% extended from it."
                )
        return market_price, "Current price is already close to the ribbon's fast EMA -- minimal chase risk."

    if strategy == "Break & Retest":
        level_key = "Resistance level" if result.trend == "bullish" else "Support level"
        level_price = result.details.get(level_key) or result.details.get(level_key.split(" ")[0])
        if level_price:
            extension_pct = abs(market_price - level_price) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                other_role = "support" if result.trend == "bullish" else "resistance"
                return level_price, (
                    f"Retest entry at the broken level ({level_price:.2f}) rather than chasing a break "
                    f"already {extension_pct:.1f}% extended -- it often becomes {other_role} on a retest."
                )
        return market_price, "Fresh break -- current price is the entry, minimal extension yet."

    if strategy == "RSI Divergence":
        level_key = "Recent swing low" if result.trend == "bullish" else "Recent swing high"
        level_price = result.details.get(level_key)
        if level_price:
            extension_pct = abs(market_price - level_price) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                return level_price, (
                    f"Pullback entry back toward the swing {'low' if result.trend == 'bullish' else 'high'} "
                    f"the divergence formed at ({level_price:.2f}) rather than chasing price already "
                    f"{extension_pct:.1f}% past it."
                )
        return market_price, "Current price is still close to the swing point the divergence formed at."

    if strategy == "Volume Profile":
        level_price = result.details.get("HVN level")
        if level_price:
            extension_pct = abs(market_price - level_price) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                return level_price, (
                    f"Retest entry back at the High Volume Node ({level_price:.2f}) rather than chasing "
                    f"price already {extension_pct:.1f}% away from the level the signal is based on."
                )
        return market_price, "Current price is already close to the HVN -- minimal chase risk."

    if strategy == "Elliott Wave":
        level_key = "Wave 1 high" if result.trend == "bullish" else "Wave 1 low"
        level_price = result.details.get(level_key)
        if level_price:
            extension_pct = abs(market_price - level_price) / market_price * 100
            if extension_pct > ENTRY_EXTENSION_THRESHOLD_PCT:
                return level_price, (
                    f"Retest entry at the wave 1 {'high' if result.trend == 'bullish' else 'low'} "
                    f"({level_price:.2f}) rather than chasing wave 3 already {extension_pct:.1f}% underway."
                )
        return market_price, "Fresh wave 3 breakout past the wave 1 extreme -- current price is the entry."

    return market_price, "Current price."


def _fibonacci_plan(result, h, entry, atr_val, is_bull):
    swing_high = result.details["Swing high"]
    swing_low = result.details["Swing low"]
    buffer = STRUCTURE_BUFFER_ATR * atr_val

    if is_bull:
        stop_loss = swing_low - buffer
        take_profit = swing_high
    else:
        stop_loss = swing_high + buffer
        take_profit = swing_low

    method = (
        f"Structure-based ({h['label']}): stop beyond the swing low/high "
        f"(from the last {h['fib_lookback']} bars), target the opposite end of the range"
    )

    max_risk_pct = h["max_risk_pct"]
    max_risk_amount = entry * (max_risk_pct / 100)
    risk_now = abs(entry - stop_loss)
    if risk_now > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount
        method += f"; stop capped at {max_risk_pct}% of entry (swing low/high was unrealistically far away)"

    min_rr, max_rr = h["min_structure_rr"], h["max_structure_rr"]
    risk_now = abs(entry - stop_loss)
    reward_now = abs(take_profit - entry)
    target_rr = reward_now / risk_now if risk_now > 0 else min_rr
    target_rr = max(min_rr, min(max_rr, target_rr))
    if abs(target_rr - (reward_now / risk_now if risk_now > 0 else 0)) > 1e-9:
        bounded_reward = risk_now * target_rr
        take_profit = entry + bounded_reward if is_bull else entry - bounded_reward
        method += f"; target set to {target_rr:.1f}:1 reward:risk (bounded {min_rr}-{max_rr}:1 for this horizon)"

    return stop_loss, take_profit, method


def _support_resistance_plan(result, h, entry, is_bull):
    stop_pct = h["sr_stop_pct"]
    target_min_pct = h["sr_target_min_pct"]
    target_max_pct = h["sr_target_max_pct"]

    volume_ratio = result.details.get("Volume ratio", SR_VOLUME_MULTIPLE)
    strength = (volume_ratio - SR_VOLUME_MULTIPLE) / (SR_VOLUME_STRENGTH_CEILING - SR_VOLUME_MULTIPLE)
    strength = max(0.0, min(1.0, strength))
    target_pct = target_min_pct + (target_max_pct - target_min_pct) * strength

    if is_bull:
        stop_loss = entry * (1 - stop_pct / 100)
        take_profit = entry * (1 + target_pct / 100)
    else:
        stop_loss = entry * (1 + stop_pct / 100)
        take_profit = entry * (1 - target_pct / 100)

    method = (
        f"Breakout sizing ({h['label']}): stop fixed at {stop_pct}% of entry, "
        f"target {target_pct:.0f}% (scaled between {target_min_pct:.0f}-{target_max_pct:.0f}% "
        f"by breakout volume strength -- {volume_ratio:.1f}x the 20-day average)"
    )
    return stop_loss, take_profit, method


def _elliott_wave_plan(result, h, entry, atr_val, is_bull):
    """
    Structural sizing for the simplified Elliott Wave strategy: stop
    beyond the wave 2 pivot (the level that, if broken, invalidates the
    wave count), target via the horizon's standard reward:risk multiple
    since wave 3 length isn't reliably predictable from wave 1 alone
    without a full discretionary count.
    """
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    if is_bull:
        wave2_low = result.details["Wave 2 low"]
        stop_loss = wave2_low - buffer
    else:
        wave2_high = result.details["Wave 2 high"]
        stop_loss = wave2_high + buffer

    method = f"Elliott Wave sizing ({h['label']}): stop beyond the wave 2 pivot (invalidation point)"

    max_risk_pct = h["max_risk_pct"]
    max_risk_amount = entry * (max_risk_pct / 100)
    risk_now = abs(entry - stop_loss)
    if risk_now > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount
        method += f"; stop capped at {max_risk_pct}% of entry (wave 2 pivot was unrealistically far away)"

    risk_now = abs(entry - stop_loss)
    rr = STRATEGY_RR_OVERRIDE.get(result.strategy, h["reward_risk_ratio"])
    take_profit = entry + risk_now * rr if is_bull else entry - risk_now * rr
    method += f"; target = {rr:.1f}:1 reward:risk (wave 3 length isn't reliably predictable, so this uses the horizon's standard ratio rather than a wave-count projection)"

    return stop_loss, take_profit, method


def _volatility_plan(h, entry, atr_val, is_bull, strategy_name=None):
    risk_distance = h["atr_stop_multiple"] * atr_val
    rr = STRATEGY_RR_OVERRIDE.get(strategy_name, h["reward_risk_ratio"])

    max_risk_pct = h["max_risk_pct"]
    max_risk_amount = entry * (max_risk_pct / 100)
    capped_note = ""
    if risk_distance > max_risk_amount:
        risk_distance = max_risk_amount
        capped_note = f"; stop capped at {max_risk_pct}% of entry"

    if is_bull:
        stop_loss = entry - risk_distance
        take_profit = entry + risk_distance * rr
    else:
        stop_loss = entry + risk_distance
        take_profit = entry - risk_distance * rr

    method = (
        f"Volatility-based ({h['label']}): stop = {h['atr_stop_multiple']}x ATR(14), "
        f"target = {rr:.1f}:1 reward:risk{capped_note}"
    )
    return stop_loss, take_profit, method
