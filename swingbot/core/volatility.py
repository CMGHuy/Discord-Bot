"""
Volatility and momentum confirmation checks used by confidence.py.

Three independent signals, each callable on its own:

  1. squeeze_breakout_confirmation() -- TTM Squeeze (Bollinger Bands
     contracting INSIDE a Keltner Channel), upgraded from the old
     pure-Bollinger-width version. When BBands go inside KC the market is
     in extreme compression; when they re-expand outside KC on directional
     volume, the squeeze fires. This is the same logic John Carter's TTM
     Squeeze (and the LazyBear TradingView indicator) are based on -- far
     more precise than "BB width near a 6-month low" alone, because it
     anchors against a volatility-normalized channel rather than a raw
     percentage.

  2. macd_momentum_aligned() -- checks whether the MACD histogram is
     positive and rising (bullish) or negative and falling (bearish),
     giving a second, momentum-based read on direction that's independent
     of every price-level method in levels.py.

  3. adx_trend_strength() -- returns the ADX value and whether it is in
     "trending" territory (>= 20) or "strong trend" territory (>= 25).
     Used by confidence.py to score quality higher in genuinely trending
     markets and lower in choppy, directionless ones.

  4. rsi_trend_aligned() -- checks whether RSI's position relative to its
     50 midline (and its recent direction of travel) agrees with a
     scenario's direction, mirroring macd_momentum_aligned()'s three-tier
     ladder. Added after a real S/R Confluence SHORT was flagged (RSI 58
     and rising, i.e. clearly on the bullish side) with nothing in the
     confidence breakdown reflecting that RSI itself disagreed -- MACD
     alignment already covered momentum, but RSI, despite being computed
     and shown on every chart, fed into no scoring factor at all.

All four are implemented natively in pandas (via indicators.py) -- no
ta-lib/C compilation, no extra pip packages beyond what's already in use.
"""
import pandas as pd

from .indicators import adx, keltner_channel, macd, rsi


def bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Classic Bollinger Bands: middle = SMA(window), upper/lower = middle +/- num_std * rolling stdev."""
    middle = df["Close"].rolling(window).mean()
    std = df["Close"].rolling(window).std()
    return pd.DataFrame({"middle": middle, "upper": middle + num_std * std, "lower": middle - num_std * std})


def squeeze_breakout_confirmation(df: pd.DataFrame, direction: str, bb_window: int = 20, num_std: float = 2.0,
                                   kc_ema_period: int = 20, kc_atr_period: int = 10, kc_multiplier: float = 1.5,
                                   volume_multiple: float = 1.5) -> dict:
    """
    TTM Squeeze: Bollinger Bands contracting INSIDE Keltner Channel =
    extreme compression likely to resolve in a sharp directional move.
    When BBands re-expand outside KC, the squeeze fires. Direction
    confirmation requires today's close to break outside yesterday's BB
    in the scenario's direction, with volume >= volume_multiple × 20d avg.

    Upgrade from the old version: the old approach checked whether BB
    width (as a raw %) was near its 6-month low -- a reasonable proxy but
    sensitive to the specific history window. The KC-based version is
    better because:
      - A KC automatically scales to current volatility (ATR-based), so
        the threshold self-adjusts; no 126-bar lookback needed.
      - Squeeze ON (BBands inside KC) / OFF (BBands outside KC) is a
        binary, unambiguous state change -- the cleanest squeeze signal
        professional traders use.
      - The first bar after a squeeze turns OFF with directional volume
        is statistically the highest-probability entry point.

    Returns a dict with:
      confirmed      -- True only when squeeze fired AND volume + direction align
      is_squeeze     -- True when BBands are currently inside KC (squeeze is ON)
      squeeze_off    -- True on the first bar the squeeze turns OFF (the trigger)
      width_pct      -- current BB width as % of mid (cosmetic / display only)
      volume_confirmed, breakout_confirmed -- component flags
    """
    empty = {
        "confirmed": False, "is_squeeze": False, "squeeze_off": False,
        "width_pct": 0.0, "volume_confirmed": False, "breakout_confirmed": False,
    }
    if len(df) < max(bb_window, kc_ema_period, kc_atr_period) + 5:
        return empty

    bb = bollinger_bands(df, bb_window, num_std)
    kc = keltner_channel(df, kc_ema_period, kc_atr_period, kc_multiplier)

    # Squeeze ON when BOTH bb bands are inside BOTH kc bands
    squeeze_on = (bb["upper"] < kc["upper"]) & (bb["lower"] > kc["lower"])

    prev_squeeze = bool(squeeze_on.iloc[-2]) if len(squeeze_on) > 1 else False
    curr_squeeze = bool(squeeze_on.iloc[-1])
    squeeze_off = prev_squeeze and not curr_squeeze   # squeeze just fired this bar

    width_pct = float((bb["upper"].iloc[-1] - bb["lower"].iloc[-1]) / bb["middle"].iloc[-1] * 100) if pd.notna(bb["middle"].iloc[-1]) else 0.0

    avg_volume = df["Volume"].rolling(bb_window).mean().iloc[-2] if len(df) > bb_window + 1 else None
    today_volume = df["Volume"].iloc[-1]
    volume_confirmed = bool(avg_volume and pd.notna(avg_volume) and today_volume >= volume_multiple * avg_volume)

    prior_upper, prior_lower = bb["upper"].iloc[-2], bb["lower"].iloc[-2]
    close_today = df["Close"].iloc[-1]
    if direction == "bullish":
        breakout_confirmed = bool(pd.notna(prior_upper) and close_today > prior_upper)
    else:
        breakout_confirmed = bool(pd.notna(prior_lower) and close_today < prior_lower)

    confirmed = squeeze_off and volume_confirmed and breakout_confirmed

    return {
        "confirmed": confirmed,
        "is_squeeze": curr_squeeze,
        "squeeze_off": squeeze_off,
        "width_pct": round(width_pct, 2),
        "volume_confirmed": volume_confirmed,
        "breakout_confirmed": breakout_confirmed,
    }


def macd_momentum_aligned(df: pd.DataFrame, direction: str,
                           fast: int = 12, slow: int = 26, signal_period: int = 9) -> dict:
    """
    Checks whether MACD momentum currently aligns with `direction`.

    Three alignment levels (strongest → weakest, in order):
      1. histogram_positive_and_rising  -- histogram > 0 AND increasing
         (for bullish); strongest confirmation: momentum is BOTH with us
         AND accelerating.
      2. histogram_positive             -- histogram > 0 (bullish) or < 0
         (bearish); momentum is with us but may be decelerating.
      3. macd_above_signal              -- MACD line above its signal line
         (bullish) or below it (bearish); weakest, directional only.

    Returns {"aligned": bool, "strength": "strong"|"moderate"|"weak"|"none",
             "macd_val": float, "signal_val": float, "histogram": float}.
    """
    empty = {"aligned": False, "strength": "none", "macd_val": None,
             "signal_val": None, "histogram": None}
    if len(df) < slow + signal_period + 2:
        return empty

    try:
        m = macd(df["Close"], fast=fast, slow=slow, signal=signal_period)
        hist_curr = float(m["histogram"].iloc[-1])
        hist_prev = float(m["histogram"].iloc[-2])
        macd_val = float(m["macd"].iloc[-1])
        signal_val = float(m["signal"].iloc[-1])

        if pd.isna(hist_curr) or pd.isna(hist_prev):
            return empty

        if direction == "bullish":
            hist_positive = hist_curr > 0
            hist_rising = hist_curr > hist_prev
            macd_above = macd_val > signal_val
            aligned = macd_above
            if hist_positive and hist_rising:
                strength = "strong"
            elif hist_positive:
                strength = "moderate"
            elif macd_above:
                strength = "weak"
            else:
                strength = "none"
                aligned = False
        else:  # bearish
            hist_negative = hist_curr < 0
            hist_falling = hist_curr < hist_prev
            macd_below = macd_val < signal_val
            aligned = macd_below
            if hist_negative and hist_falling:
                strength = "strong"
            elif hist_negative:
                strength = "moderate"
            elif macd_below:
                strength = "weak"
            else:
                strength = "none"
                aligned = False

        return {
            "aligned": aligned,
            "strength": strength,
            "macd_val": round(macd_val, 4),
            "signal_val": round(signal_val, 4),
            "histogram": round(hist_curr, 4),
        }
    except Exception:
        return empty


def rsi_trend_aligned(df: pd.DataFrame, direction: str, period: int = 14) -> dict:
    """
    Checks whether RSI's position relative to its 50 midline -- and its
    recent direction of travel -- agrees with `direction`, mirroring
    macd_momentum_aligned()'s three-tier ladder so the two factors read
    the same way in confidence.py's breakdown.

    Three alignment levels (strongest -> weakest):
      1. favorable_and_moving  -- RSI on the expected side of 50 (> 50
         bullish, < 50 bearish) AND still moving further that way
         (rising for bullish, falling for bearish) -- momentum
         confirming AND building, not just present.
      2. favorable              -- RSI on the expected side of 50,
         regardless of which way it's currently moving.
      3. neutral                -- RSI within the neutral band around 50
         (NEUTRAL_LO-NEUTRAL_HI) -- not confirming, but not clearly
         opposed either; a genuinely flat/undecided reading shouldn't be
         scored the same as RSI actively trending the wrong way.

    Anything on the wrong side of 50 and outside the neutral band is
    "none" -- RSI actively opposes the scenario (e.g. RSI 58 and rising
    for a SHORT, the exact case that motivated adding this factor:
    S/R Confluence can build a bearish scenario purely from price-level
    geometry with no momentum check at all unless something like this
    explicitly looks at RSI's own direction).

    Returns {"aligned": bool, "strength": "strong"|"moderate"|"weak"|"none",
             "rsi_val": float | None}.
    """
    empty = {"aligned": False, "strength": "none", "rsi_val": None}
    if len(df) < period + 2:
        return empty

    NEUTRAL_LO, NEUTRAL_HI = 45.0, 55.0

    try:
        r = rsi(df["Close"], period)
        rsi_curr = float(r.iloc[-1])
        rsi_prev = float(r.iloc[-2])
        if pd.isna(rsi_curr) or pd.isna(rsi_prev):
            return empty

        if direction == "bullish":
            favorable = rsi_curr > 50
            moving_further = rsi_curr > rsi_prev
        else:  # bearish
            favorable = rsi_curr < 50
            moving_further = rsi_curr < rsi_prev
        neutral = NEUTRAL_LO <= rsi_curr <= NEUTRAL_HI

        if favorable and moving_further:
            strength, aligned = "strong", True
        elif favorable:
            strength, aligned = "moderate", True
        elif neutral:
            strength, aligned = "weak", False
        else:
            strength, aligned = "none", False

        return {"aligned": aligned, "strength": strength, "rsi_val": round(rsi_curr, 1)}
    except Exception:
        return empty


def adx_trend_strength(df: pd.DataFrame, period: int = 14) -> dict:
    """
    Returns the current ADX value and a categorical strength label.

    Labels (standard Wilder interpretation):
      < 20  : ranging / no trend   (choppy, setup is higher risk)
      20-24 : weak trend emerging
      25-39 : strong trend          (best swing-trade territory)
      >= 40 : very strong trend     (watch for exhaustion)

    Returns {"adx": float | None, "trending": bool, "strong": bool, "label": str}.
    'trending' = ADX >= 20; 'strong' = ADX >= 25.
    """
    empty = {"adx": None, "trending": False, "strong": False, "label": "unavailable"}
    if len(df) < period * 2 + 5:
        return empty
    try:
        adx_series = adx(df, period)
        val = float(adx_series.iloc[-1])
        if pd.isna(val):
            return empty
        if val >= 40:
            label = "very strong trend"
        elif val >= 25:
            label = "strong trend"
        elif val >= 20:
            label = "weak trend emerging"
        else:
            label = "ranging / no clear trend"
        return {
            "adx": round(val, 1),
            "trending": val >= 20,
            "strong": val >= 25,
            "label": label,
        }
    except Exception:
        return empty
