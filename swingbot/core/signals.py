"""
Independent swing-trade signal-detection functions -- one per strategy
(EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, MACD, Elliott
Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile), each
evaluated across every swing horizon by strategy.evaluate_all(). Split out
of strategy.py because these are ~30 independent, self-contained
functions sharing only the SignalResult dataclass and a handful of
constants (HORIZONS, MIN_BARS, RSI thresholds, ...) that strategy.py
still owns -- strategy.py imports every one of these back and re-exposes
them (via STRATEGY_FUNCS and direct re-export) exactly as before, so
nothing about how a caller uses swingbot.core.strategy changes.

compute_volume_profile/compute_hvn_level also live here since they're the
data-computation half of the Volume Profile signal above -- but they're
reused well beyond just that one signal (trade_chart.py's volume-profile
panel, levels.py's confluence engine), so they're kept as their own
top-level functions rather than folded into volume_profile_signal.
"""
from dataclasses import dataclass, field

import pandas as pd

from .indicators import ema, macd, rsi, rolling_vwap, fibonacci_levels, elliott_wave3_entries, zigzag_pivots
from .strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, RSI_OVERBOUGHT, RSI_OVERSOLD,
    SR_VOLUME_MULTIPLE, SignalResult,
)


# ---------------------------------------------------------------------------
# Strategy 1: EMA Crossover (+ RSI filter)
# ---------------------------------------------------------------------------
def ema_cross_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close = df["Close"]
    fast = ema(close, h["ema_fast"])
    slow = ema(close, h["ema_slow"])
    rsi14 = rsi(close, 14)

    prev_diff = fast.iloc[-2] - slow.iloc[-2]
    curr_diff = fast.iloc[-1] - slow.iloc[-1]
    crossed_up = prev_diff <= 0 and curr_diff > 0
    crossed_down = prev_diff >= 0 and curr_diff < 0
    curr_rsi = float(rsi14.iloc[-1])

    if crossed_up and curr_rsi < RSI_OVERBOUGHT:
        trend, triggered = "bullish", True
    elif crossed_down:
        trend, triggered = "bearish", True
    else:
        trend, triggered = ("bullish" if curr_diff > 0 else "bearish"), False

    return SignalResult(
        ticker=ticker,
        strategy="EMA Crossover",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=float(close.iloc[-1]),
        details={
            f"EMA{h['ema_fast']}": round(float(fast.iloc[-1]), 2),
            f"EMA{h['ema_slow']}": round(float(slow.iloc[-1]), 2),
            "RSI(14)": round(curr_rsi, 1),
        },
    )


# ---------------------------------------------------------------------------
# Strategy 2: Rolling VWAP crossover
# ---------------------------------------------------------------------------
def vwap_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close = df["Close"]
    vwap = rolling_vwap(df, h["vwap_window"])

    prev_diff = close.iloc[-2] - vwap.iloc[-2]
    curr_diff = close.iloc[-1] - vwap.iloc[-1]
    crossed_up = prev_diff <= 0 and curr_diff > 0
    crossed_down = prev_diff >= 0 and curr_diff < 0

    if crossed_up:
        trend, triggered = "bullish", True
    elif crossed_down:
        trend, triggered = "bearish", True
    else:
        trend, triggered = ("bullish" if curr_diff > 0 else "bearish"), False

    return SignalResult(
        ticker=ticker,
        strategy="VWAP",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=float(close.iloc[-1]),
        details={
            f"VWAP({h['vwap_window']}d)": round(float(vwap.iloc[-1]), 2),
            "Close vs VWAP": f"{'+' if curr_diff >= 0 else ''}{curr_diff:.2f}",
        },
    )


# ---------------------------------------------------------------------------
# Strategy 3: Fibonacci retracement test
# ---------------------------------------------------------------------------
def fibonacci_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close_series = df["Close"]
    close = float(close_series.iloc[-1])
    prev_ref = float(close_series.iloc[-4]) if len(close_series) >= 4 else float(close_series.iloc[-2])

    fib = fibonacci_levels(df, h["fib_lookback"])
    levels = fib["levels"]
    swing_range = fib["swing_high"] - fib["swing_low"]

    if swing_range <= 0:
        # Flat/degenerate range -- nothing meaningful to test
        return SignalResult(
            ticker=ticker, strategy="Fibonacci", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=close,
            details={"note": "insufficient range to compute levels"},
        )

    nearest_ratio, nearest_price = min(levels.items(), key=lambda kv: abs(kv[1] - close))
    distance_pct = abs(nearest_price - close) / swing_range * 100
    is_testing_level = distance_pct <= FIB_TOLERANCE_PCT

    moving_up = close > prev_ref
    if is_testing_level and moving_up:
        trend, triggered = "bullish", True
    elif is_testing_level and not moving_up:
        trend, triggered = "bearish", True
    else:
        # No fresh test right now -- report bias only, don't alert
        midpoint = levels[0.5]
        trend, triggered = ("bullish" if close > midpoint else "bearish"), False

    return SignalResult(
        ticker=ticker,
        strategy="Fibonacci",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=close,
        details={
            "Swing high": round(fib["swing_high"], 2),
            "Swing low": round(fib["swing_low"], 2),
            "Nearest level": f"{nearest_ratio * 100:.1f}% ({nearest_price:.2f})",
            "Nearest level price": round(nearest_price, 4),
            "Distance": f"{distance_pct:.1f}% of range",
        },
    )


# ---------------------------------------------------------------------------
# Strategy 4: Support/Resistance breakout (classic "breakout from a base",
# confirmed by volume -- the O'Neil/Minervini style setup)
# ---------------------------------------------------------------------------
def support_resistance_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    lookback = h["sr_lookback"]
    close_series = df["Close"]
    close = float(close_series.iloc[-1])

    # Resistance/support established over the PRIOR window, excluding today,
    # so a breakout is measured against a level that existed before today's bar.
    resistance_series = df["High"].rolling(lookback).max().shift(1)
    support_series = df["Low"].rolling(lookback).min().shift(1)
    resistance = float(resistance_series.iloc[-1])
    support = float(support_series.iloc[-1])

    prev_close = float(close_series.iloc[-2]) if len(close_series) >= 2 else close
    prev_resistance = float(resistance_series.iloc[-2]) if len(resistance_series) >= 2 else resistance
    prev_support = float(support_series.iloc[-2]) if len(support_series) >= 2 else support

    vol_avg20 = float(df["Volume"].tail(20).mean())
    today_vol = float(df["Volume"].iloc[-1])
    volume_ratio = today_vol / vol_avg20 if vol_avg20 > 0 else 1.0
    volume_confirmed = volume_ratio >= SR_VOLUME_MULTIPLE

    breakout_up = (close > resistance) and (prev_close <= prev_resistance) and volume_confirmed
    breakdown_down = (close < support) and (prev_close >= prev_support) and volume_confirmed

    if breakout_up:
        trend, triggered = "bullish", True
    elif breakdown_down:
        trend, triggered = "bearish", True
    else:
        # No fresh breakout -- report bias only (which side of the range is price on)
        midpoint = (resistance + support) / 2 if pd.notna(resistance) and pd.notna(support) else close
        trend, triggered = ("bullish" if close >= midpoint else "bearish"), False

    return SignalResult(
        ticker=ticker,
        strategy="Support/Resistance",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=close,
        details={
            "Resistance": round(resistance, 2) if pd.notna(resistance) else None,
            "Support": round(support, 2) if pd.notna(support) else None,
            "Volume ratio": round(volume_ratio, 2),
            "Volume confirmed": "yes" if volume_confirmed else "no",
        },
    )


# ---------------------------------------------------------------------------
# Strategy 5: RSI mean-reversion (oversold bounce / overbought rejection)
# ---------------------------------------------------------------------------
def rsi_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close_series = df["Close"]
    close = float(close_series.iloc[-1])

    rsi14 = rsi(close_series, 14)
    prev_rsi = float(rsi14.iloc[-2]) if len(rsi14) >= 2 else float(rsi14.iloc[-1])
    curr_rsi = float(rsi14.iloc[-1])

    crossed_up = prev_rsi < RSI_OVERSOLD <= curr_rsi
    crossed_down = prev_rsi > RSI_OVERBOUGHT >= curr_rsi

    if crossed_up:
        trend, triggered = "bullish", True
    elif crossed_down:
        trend, triggered = "bearish", True
    else:
        # No fresh reversal -- lean toward the side RSI is closer to reclaiming
        trend, triggered = ("bullish" if curr_rsi < 50 else "bearish"), False

    return SignalResult(
        ticker=ticker,
        strategy="RSI",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=close,
        details={"RSI(14)": round(curr_rsi, 1)},
    )


# ---------------------------------------------------------------------------
# Strategy 6: MACD Crossover -- MACD line crossing its signal line,
# with an optional histogram-acceleration filter to catch the freshest,
# highest-momentum entry (the bar the histogram reverses direction is
# the classical "MACD divergence" entry point, not just a zero-line cross).
# ---------------------------------------------------------------------------
def macd_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close_series = df["Close"]
    close = float(close_series.iloc[-1])

    # Scale MACD periods by horizon: shorter horizons use faster periods so
    # the indicator reacts to the same kind of move the horizon is trading.
    fast_p, slow_p, sig_p = MACD_PERIODS_BY_HORIZON.get(horizon_key, (12, 26, 9))

    if len(close_series) < slow_p + sig_p + 2:
        return SignalResult(
            ticker=ticker, strategy="MACD", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=close,
            details={"note": "insufficient history for MACD"},
        )

    m = macd(close_series, fast=fast_p, slow=slow_p, signal=sig_p)
    macd_curr = float(m["macd"].iloc[-1])
    macd_prev = float(m["macd"].iloc[-2])
    sig_curr = float(m["signal"].iloc[-1])
    sig_prev = float(m["signal"].iloc[-2])
    hist_curr = float(m["histogram"].iloc[-1])
    hist_prev = float(m["histogram"].iloc[-2])

    # Fresh crossover: MACD crossed its signal line this bar
    crossed_up = macd_prev <= sig_prev and macd_curr > sig_curr
    crossed_down = macd_prev >= sig_prev and macd_curr < sig_curr

    # Histogram reversal: histogram changed sign (even stronger signal)
    hist_turned_positive = hist_prev <= 0 and hist_curr > 0
    hist_turned_negative = hist_prev >= 0 and hist_curr < 0

    if crossed_up or hist_turned_positive:
        trend, triggered = "bullish", True
    elif crossed_down or hist_turned_negative:
        trend, triggered = "bearish", True
    else:
        # No fresh cross -- report current bias only
        trend, triggered = ("bullish" if macd_curr > sig_curr else "bearish"), False

    # Zero-line context: above zero = bull momentum regime, below = bear
    above_zero = macd_curr > 0

    return SignalResult(
        ticker=ticker,
        strategy="MACD",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=close,
        details={
            f"MACD({fast_p},{slow_p},{sig_p})": round(macd_curr, 4),
            "Signal": round(sig_curr, 4),
            "Histogram": round(hist_curr, 4),
            "Histogram direction": "rising" if hist_curr > hist_prev else "falling",
            "Zero-line": "above (bull regime)" if above_zero else "below (bear regime)",
        },
    )


# ---------------------------------------------------------------------------
# Strategy 7: Elliott Wave (simplified wave-3 breakout) -- see the honesty
# note in indicators.elliott_wave3_entries; this is a mechanical
# approximation of one piece of an inherently subjective theory.
# ---------------------------------------------------------------------------
def elliott_wave_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    threshold_pct = h["max_risk_pct"]  # reuse the horizon's risk scale for pivot granularity
    close = float(df["Close"].iloc[-1])

    bullish_series, bearish_series, entry_levels = elliott_wave3_entries(df, threshold_pct)
    last_idx = len(df) - 1
    is_bull_trigger = bool(bullish_series.iloc[-1])
    is_bear_trigger = bool(bearish_series.iloc[-1])

    pivots = zigzag_pivots(df, threshold_pct)
    details = {}
    if last_idx in entry_levels:
        lv = entry_levels[last_idx]
        if is_bull_trigger:
            details = {"Wave 1 high": round(lv["wave1"], 2), "Wave 2 low": round(lv["wave2"], 2)}
        else:
            details = {"Wave 1 low": round(lv["wave1"], 2), "Wave 2 high": round(lv["wave2"], 2)}

    if is_bull_trigger:
        trend, triggered = "bullish", True
    elif is_bear_trigger:
        trend, triggered = "bearish", True
    else:
        triggered = False
        if pivots:
            trend = "bullish" if close >= pivots[-1][1] else "bearish"
        else:
            trend = "bullish"
        details = {"note": "no valid wave-3 setup detected"}

    return SignalResult(
        ticker=ticker,
        strategy="Elliott Wave",
        horizon_key=horizon_key,
        horizon_label=h["label"],
        trend=trend,
        triggered=triggered,
        close=close,
        details=details,
    )



# ---------------------------------------------------------------------------
# Strategy 8: Moving Average Ribbon Crossover
# 10 EMA crosses above 20 EMA while both are above the slow SMA — confirms
# a powerful, aligned medium-term trend.  Periods scale with horizon.
# ---------------------------------------------------------------------------
def ma_ribbon_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close = df["Close"]
    cur_price = float(close.iloc[-1])

    horizon_to_ribbon = {
        "2w": (10, 20, 50),
        "4w": (10, 20, 50),
        "2m": (20, 50, 100),
        "3m": (20, 50, 200),
        "6m": (50, 100, 200),
    }
    fast_p, mid_p, slow_p = horizon_to_ribbon.get(horizon_key, (10, 20, 50))

    if len(close) < slow_p + 2:
        return SignalResult(
            ticker=ticker, strategy="MA Ribbon", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=cur_price,
            details={"note": f"insufficient history (need {slow_p + 2} bars)"},
        )

    fast = ema(close, fast_p)
    mid  = ema(close, mid_p)
    slow_sma = close.rolling(slow_p).mean()

    fast_curr, fast_prev = float(fast.iloc[-1]), float(fast.iloc[-2])
    mid_curr,  mid_prev  = float(mid.iloc[-1]),  float(mid.iloc[-2])
    slow_curr = float(slow_sma.iloc[-1])

    crossed_up   = fast_prev <= mid_prev and fast_curr > mid_curr
    crossed_down = fast_prev >= mid_prev and fast_curr < mid_curr
    all_above_slow = fast_curr > slow_curr and mid_curr > slow_curr
    all_below_slow = fast_curr < slow_curr and mid_curr < slow_curr

    if crossed_up and all_above_slow:
        trend, triggered = "bullish", True
    elif crossed_down and all_below_slow:
        trend, triggered = "bearish", True
    elif crossed_up or crossed_down:
        trend = "bullish" if crossed_up else "bearish"
        triggered = False
    else:
        trend = "bullish" if fast_curr > mid_curr else "bearish"
        triggered = False

    return SignalResult(
        ticker=ticker, strategy="MA Ribbon", horizon_key=horizon_key,
        horizon_label=h["label"], trend=trend, triggered=triggered, close=cur_price,
        details={
            f"EMA{fast_p}": round(fast_curr, 2),
            f"EMA{mid_p}": round(mid_curr, 2),
            f"SMA{slow_p}": round(slow_curr, 2),
            "Aligned": "yes" if (all_above_slow or all_below_slow) else "no",
        },
    )


# ---------------------------------------------------------------------------
# Strategy 9: Break & Retest
# Price broke above resistance on heavy volume in the last 10 bars, then
# pulled back to within 2% of the level and is bouncing (bullish).
# Bearish mirror: broke below support, retesting from below.
# ---------------------------------------------------------------------------
def break_retest_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    lookback = h["sr_lookback"]
    close = float(df["Close"].iloc[-1])

    if len(df) < lookback + 10:
        return SignalResult(
            ticker=ticker, strategy="Break & Retest", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=close,
            details={"note": "insufficient history"},
        )

    volume    = df["Volume"]
    avg_vol   = float(volume.iloc[-(lookback + 10):-10].mean()) or 1.0
    resistance = float(df["High"].iloc[-(lookback + 10):-10].max())
    support    = float(df["Low"].iloc[-(lookback + 10):-10].min())

    # Horizon-aware look-back: how many bars count as a "recent" breakout
    recent_bars = {"2w": 10, "4w": 15, "2m": 20, "3m": 25, "6m": 30}.get(horizon_key, 10)
    recent = df.iloc[-recent_bars:]
    recent_close = float(df["Close"].iloc[-1])
    recent_highs = recent["High"]
    recent_vols  = recent["Volume"]
    vol_thresh   = avg_vol * SR_VOLUME_MULTIPLE

    bull_break = recent[(recent_highs > resistance) & (recent_vols > vol_thresh)]
    dist_to_res = (recent_close - resistance) / resistance * 100
    bear_break  = recent[(recent["Low"] < support) & (recent_vols > vol_thresh)]
    dist_to_sup = (recent_close - support) / support * 100

    if len(bull_break) and 0 <= dist_to_res < 2.5:
        trend, triggered = "bullish", True
        details = {
            "Resistance level": round(resistance, 2),
            "Distance above level": f"+{dist_to_res:.1f}%",
            "Breakout volume x avg": f"{float(bull_break['Volume'].max()) / avg_vol:.1f}x",
        }
    elif len(bear_break) and -2.5 < dist_to_sup <= 0:
        trend, triggered = "bearish", True
        details = {
            "Support level": round(support, 2),
            "Distance below level": f"{dist_to_sup:.1f}%",
            "Breakdown volume x avg": f"{float(bear_break['Volume'].max()) / avg_vol:.1f}x",
        }
    else:
        trend = "bullish" if recent_close > (resistance + support) / 2 else "bearish"
        triggered = False
        details = {"Resistance": round(resistance, 2), "Support": round(support, 2)}

    return SignalResult(
        ticker=ticker, strategy="Break & Retest", horizon_key=horizon_key,
        horizon_label=h["label"], trend=trend, triggered=triggered, close=close,
        details=details,
    )


# ---------------------------------------------------------------------------
# Strategy 10: RSI Hidden Bullish/Bearish Divergence
# Hidden bullish: price higher low + RSI lower low (uptrend continuation).
# Hidden bearish: price lower high + RSI higher high (downtrend continuation).
# ---------------------------------------------------------------------------
def rsi_divergence_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    close_series = df["Close"]
    close = float(close_series.iloc[-1])
    lookback = max(h["sr_lookback"], 20)

    if len(df) < lookback + 10:
        return SignalResult(
            ticker=ticker, strategy="RSI Divergence", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=close,
            details={"note": "insufficient history"},
        )

    rsi14 = rsi(close_series, 14)
    w_close = close_series.iloc[-lookback:].reset_index(drop=True)
    w_rsi   = rsi14.iloc[-lookback:].reset_index(drop=True)
    curr_rsi = float(rsi14.iloc[-1])

    def _swing_lows(s, n=3):
        return [(i, float(s.iloc[i])) for i in range(n, len(s) - n)
                if all(s.iloc[i] < s.iloc[i - j] for j in range(1, n + 1)) and
                   all(s.iloc[i] < s.iloc[i + j] for j in range(1, n + 1))]

    def _swing_highs(s, n=3):
        return [(i, float(s.iloc[i])) for i in range(n, len(s) - n)
                if all(s.iloc[i] > s.iloc[i - j] for j in range(1, n + 1)) and
                   all(s.iloc[i] > s.iloc[i + j] for j in range(1, n + 1))]

    price_lows  = _swing_lows(w_close)
    rsi_lows    = _swing_lows(w_rsi)
    price_highs = _swing_highs(w_close)
    rsi_highs   = _swing_highs(w_rsi)

    trend = "bullish" if curr_rsi > 50 else "bearish"
    triggered = False
    details = {"RSI(14)": round(curr_rsi, 1)}

    # Hidden bullish: price makes higher low, RSI makes lower low
    if len(price_lows) >= 2 and len(rsi_lows) >= 2:
        pl1_i, pl1_v = price_lows[-2]
        pl2_i, pl2_v = price_lows[-1]
        near1 = [rv for ri, rv in rsi_lows if abs(ri - pl1_i) <= 5]
        near2 = [rv for ri, rv in rsi_lows if abs(ri - pl2_i) <= 5]
        if near1 and near2 and pl2_v > pl1_v and near2[-1] < near1[-1]:
            trend, triggered = "bullish", True
            details.update({
                "Pattern": "Hidden bullish divergence",
                "Price lows": f"{round(pl1_v, 2)} → {round(pl2_v, 2)} (higher)",
                "RSI lows":   f"{round(near1[-1], 1)} → {round(near2[-1], 1)} (lower)",
                # Raw float (not the formatted string above) -- lets trade_plan.py
                # use the most recent swing low as a pullback/retest reference
                # level without having to parse the display string.
                "Recent swing low": round(pl2_v, 2),
            })

    # Hidden bearish: price makes lower high, RSI makes higher high
    if not triggered and len(price_highs) >= 2 and len(rsi_highs) >= 2:
        ph1_i, ph1_v = price_highs[-2]
        ph2_i, ph2_v = price_highs[-1]
        near1 = [rv for ri, rv in rsi_highs if abs(ri - ph1_i) <= 5]
        near2 = [rv for ri, rv in rsi_highs if abs(ri - ph2_i) <= 5]
        if near1 and near2 and ph2_v < ph1_v and near2[-1] > near1[-1]:
            trend, triggered = "bearish", True
            details.update({
                "Pattern": "Hidden bearish divergence",
                "Price highs": f"{round(ph1_v, 2)} → {round(ph2_v, 2)} (lower)",
                "RSI highs":   f"{round(near1[-1], 1)} → {round(near2[-1], 1)} (higher)",
                # Raw float counterpart of "Price highs" above, for trade_plan.py.
                "Recent swing high": round(ph2_v, 2),
            })

    return SignalResult(
        ticker=ticker, strategy="RSI Divergence", horizon_key=horizon_key,
        horizon_label=h["label"], trend=trend, triggered=triggered, close=close,
        details=details,
    )


# ---------------------------------------------------------------------------
# Strategy 11: Volume Profile HVN Support/Resistance
# Finds the High Volume Node (HVN) — the price bucket with the most traded
# volume — and triggers when price consolidates just above it (bullish
# floor) or just below it (bearish ceiling).
# ---------------------------------------------------------------------------
def compute_volume_profile(
    df: pd.DataFrame, lookback: int, n_bins: int = 20,
    price_min: float = None, price_max: float = None,
) -> dict | None:
    """
    Bins the last `lookback` bars' trading range into `n_bins` price
    buckets and sums each bucket's traded volume -- the full Volume
    Profile histogram, not just its single busiest bucket. compute_hvn_level
    (below) calls this and keeps only the winning bucket; trade_chart.py's
    left-side volume profile panel uses the full histogram to draw every
    bucket, not just the busiest one.

    By default (`price_min`/`price_max` both None, the only way every
    existing caller uses this), the bucketed price range is exactly the
    last `lookback` bars' own High/Low extremes, same as always. Passing
    explicit `price_min`/`price_max` overrides that -- trade_chart.py's
    panel does this, passing the price PANEL's actual final y-axis range
    (which is padded, and further widened to fit the entry/stop/target
    lines -- an entry can be a deliberate pullback level well away from
    where price has recently traded, not necessarily "now"). Without
    this, buckets only covered the recent window's own narrow range,
    leaving the portion of the panel above/below that range with no
    buckets at all -- a visible unbinned gap wherever the chart's visible
    prices (including a distant entry/stop/target) fell outside it.

    Returns a dict with:
      - "bin_edges": list of n_bins+1 price boundaries, low to high
      - "bin_volumes": list of n_bins summed-volume totals, one per bucket,
        in the same low-to-high order as bin_edges
      - "poc_index": index of the busiest bucket (Point of Control)
      - "poc_price": price at the center of that bucket
      - "poc_pct": that bucket's % share of total period volume

    Returns None if there isn't enough history, or the resulting range
    (explicit or derived) is flat/inverted.
    """
    if len(df) < lookback + 2:
        return None
    window = df.iloc[-lookback:]
    if price_min is None:
        price_min = float(window["Low"].min())
    if price_max is None:
        price_max = float(window["High"].max())
    price_range = price_max - price_min
    if price_range <= 0:
        return None

    bin_size = price_range / n_bins
    bins = [0.0] * n_bins
    for _, row in window.iterrows():
        mid = (float(row["High"]) + float(row["Low"])) / 2
        # A bar's midpoint can fall outside an explicitly widened range
        # only if it's narrower than the window's own extremes (not the
        # normal case here, since the panel only ever widens); skip
        # rather than clamp so volume never gets misattributed to an
        # edge bucket it didn't actually trade in.
        if mid < price_min or mid > price_max:
            continue
        idx = min(max(int((mid - price_min) / bin_size), 0), n_bins - 1)
        bins[idx] += float(row["Volume"])

    total_vol = sum(bins)
    poc_idx = bins.index(max(bins)) if total_vol > 0 else n_bins // 2
    bin_edges = [price_min + i * bin_size for i in range(n_bins + 1)]
    poc_price = price_min + (poc_idx + 0.5) * bin_size
    poc_pct = (bins[poc_idx] / total_vol * 100) if total_vol else 0.0

    return {
        "bin_edges": bin_edges,
        "bin_volumes": bins,
        "poc_index": poc_idx,
        "poc_price": poc_price,
        "poc_pct": poc_pct,
    }


def compute_hvn_level(df: pd.DataFrame, lookback: int, n_bins: int = 20) -> tuple[float, float] | None:
    """
    Volume Profile's core calculation: the price of the High Volume Node
    (the bucket where the most shares actually changed hands, out of
    `n_bins` buckets across the last `lookback` bars' trading range) and
    its share of total period volume, as (hvn_price, vol_share_pct).

    Pulled out as its own function so trade_plan.py can reuse the exact
    same calculation to check whether OTHER strategies' entries (e.g. a
    Fibonacci retracement level) happen to coincide with a real
    high-volume price, not just a formula-derived one -- without a
    second, drift-prone copy of this logic living in two files. Delegates
    to compute_volume_profile (which keeps the full per-bucket histogram,
    needed by trade_chart.py's volume profile panel) and keeps just the
    winning bucket, so this function's own return contract is unchanged
    for its existing callers.

    Returns None if there isn't enough history or the range is flat.
    """
    profile = compute_volume_profile(df, lookback, n_bins)
    if profile is None:
        return None
    return profile["poc_price"], profile["poc_pct"]


def volume_profile_signal(ticker: str, df: pd.DataFrame, horizon_key: str) -> SignalResult:
    h = HORIZONS[horizon_key]
    lookback = h["sr_lookback"]
    close = float(df["Close"].iloc[-1])

    hvn = compute_hvn_level(df, lookback)
    if hvn is None:
        note = "insufficient history" if len(df) < lookback + 2 else "flat price range"
        return SignalResult(
            ticker=ticker, strategy="Volume Profile", horizon_key=horizon_key,
            horizon_label=h["label"], trend="bullish", triggered=False, close=close,
            details={"note": note},
        )
    hvn_price, vol_share_pct = hvn
    dist_pct  = (close - hvn_price) / hvn_price * 100
    vol_share = f"{vol_share_pct:.0f}% of period volume" if vol_share_pct else "n/a"

    if 0 < dist_pct < 1.5:        # price within 1.5% above HVN → floor support (tighter = fewer false signals)
        trend, triggered = "bullish", True
        details = {
            "HVN level": round(hvn_price, 2),
            "Distance above HVN": f"+{dist_pct:.1f}%",
            "HVN volume share": vol_share,
        }
    elif -1.5 < dist_pct < 0:     # price within 1.5% below HVN → ceiling resistance (tighter = fewer false signals)
        trend, triggered = "bearish", True
        details = {
            "HVN level": round(hvn_price, 2),
            "Distance below HVN": f"{dist_pct:.1f}%",
            "HVN volume share": vol_share,
        }
    else:
        trend = "bullish" if close > hvn_price else "bearish"
        triggered = False
        details = {"HVN level": round(hvn_price, 2), "Distance from HVN": f"{dist_pct:+.1f}%"}

    return SignalResult(
        ticker=ticker, strategy="Volume Profile", horizon_key=horizon_key,
        horizon_label=h["label"], trend=trend, triggered=triggered, close=close,
        details=details,
    )

