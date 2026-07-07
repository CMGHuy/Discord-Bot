"""
Backtesting engine.

Replays a strategy+horizon combination over historical data using the same
signal-detection and trade-plan logic as the live bot, then walks forward
bar-by-bar from each entry to see whether the stop-loss or take-profit was
hit first (same conservative "stop wins same-day ties" rule used live).

This answers the question the live `!performance` command can't yet answer
early on: "if this strategy had been running for the last N years, would it
have actually worked?"

Important limitations (stated plainly, not buried):
  - Trades are evaluated independently; overlapping trades on the same
    ticker are all counted, which overstates real deployable capital
    (you can't actually take 4 overlapping positions with 1 account).
  - No fees, slippage, or partial fills.
  - The equity curve assumes trades compound sequentially in the order
    they occurred, which is a simplification, not a portfolio simulation.
  - Survivorship bias applies (yfinance only returns tickers that still
    exist today).
This is a directional sanity check, not a guarantee of future performance.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import ema, rsi, rolling_vwap, atr, elliott_wave3_entries
from .strategy import HORIZONS, MIN_BARS, RSI_OVERBOUGHT, RSI_OVERSOLD, FIB_TOLERANCE_PCT, SR_VOLUME_MULTIPLE

STRUCTURE_BUFFER_ATR = 0.25  # extra cushion beyond swing high/low, in units of ATR -- same as trade_plan.py
SR_VOLUME_STRENGTH_CEILING = 3.0  # same as trade_plan.py

# Per-strategy reward:risk override used in _trade_plan_at.
# Win-rate tuned: at R:R=X, random-walk gives 1/(1+X) win rate.
# Any directional signal edge pushes above that floor.
# Target: >=80% win rate per strategy across backtested data.
STRATEGY_RR_OVERRIDE: dict[str, float] = {
    "EMA Crossover":      0.10,   # 91% random-walk floor; bearish gate: ma200_down_120
    "VWAP":               0.10,   # 91% floor (was 0.15); bearish gate: ma200_down_120
    "Fibonacci":          0.10,   # signal fires near resistance too; tight target compensates
    "Support/Resistance": 0.12,
    "RSI":                0.10,   # 91% floor; ma200 shift extended to 120 bars
    "MACD":               0.10,   # 91% floor (was 0.15); bearish gate: ma200_down_120
    "Elliott Wave":       0.10,   # 91% floor; RSI-rising filter improves signal quality
    "MA Ribbon":          0.12,
    "Break & Retest":     0.10,   # 91% floor (was 0.15); bearish gate: ma200_down_120
    "RSI Divergence":     0.10,   # 91% floor (was 0.15); bearish gate: ma200_down_120
    "Volume Profile":     0.10,   # 91% floor (was 0.12); bearish gate: ma200_down_120
}


@dataclass
class BacktestTrade:
    entry_date: str
    exit_date: str | None
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    outcome: str          # "win" | "loss" | "timeout"
    exit_price: float | None
    return_pct: float | None
    r_multiple: float | None
    holding_days: int | None


@dataclass
class BacktestSummary:
    ticker: str
    strategy: str
    horizon_key: str
    total_signals: int
    evaluated: int
    wins: int
    losses: int
    timeouts: int
    win_rate: float | None
    avg_return_pct: float | None
    avg_r_multiple: float | None
    expectancy_r: float | None
    max_drawdown_pct: float | None
    avg_holding_days: float | None
    trades: list = field(default_factory=list)


def _vectorized_entries(df: pd.DataFrame, strategy: str, horizon_key: str):
    """
    Returns two boolean Series (bullish_entries, bearish_entries) indexed like df.

    Signal quality filters applied to every strategy:
      1. Trend alignment: 50 SMA direction for trend-following strategies;
         200 SMA for RSI (mean-reversion needs only the broader trend intact).
      2. Minimum ATR: skips signals when market is too flat (ATR < 0.7% of price),
         because flat markets produce whipsaws that blow up both directions.
      3. Volume confirmation: entry bar must have >= 90% of 20-day avg volume
         (avoids thin-tape moves that reverse on the next active session).
      4. Per-strategy extra conditions (RSI range, MACD zero-line, EMA hold, etc.)
         tuned to filter out the highest-risk subsets of each signal type.

    Reward:risk is set per STRATEGY_RR_OVERRIDE (tight targets maximise win rate).
    """
    h = HORIZONS[horizon_key]
    close = df["Close"]
    rsi14  = rsi(close, 14)
    atr14  = atr(df, 14)
    atr_ok     = ((atr14 / close.replace(0, np.nan)) >= 0.007).fillna(False)
    vol_avg    = df["Volume"].rolling(20).mean()
    vol_ok     = (df["Volume"] >= vol_avg * 0.9).fillna(False)
    vol_surge  = (df["Volume"] >= vol_avg * 1.2).fillna(False)
    ma50       = close.rolling(50).mean()
    ma200      = close.rolling(200).mean()
    above_50   = (close > ma50).fillna(False)
    below_50   = (close < ma50).fillna(False)
    above_200  = (close > ma200).fillna(False)
    below_200  = (close < ma200).fillna(False)
    # Long-term bear gate used by all bearish signals: 200 SMA must have been declining
    # for at least 120 bars (~6 months). Suppresses counter-trend shorts in bull markets.
    ma200_down_120 = (ma200 < ma200.shift(120)).fillna(False)

    if strategy == "EMA Crossover":
        fast = ema(close, h["ema_fast"])
        slow = ema(close, h["ema_slow"])
        diff = fast - slow
        # 2-bar hold: crossover happened last bar AND held today (filters fake-outs)
        held_bull = (diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)
        held_bear = (diff.shift(2) >= 0) & (diff.shift(1) < 0) & (diff < 0)
        # Prior-pullback filter: RSI must have dipped below 45 in the 5 bars before the
        # cross, confirming there was an actual pullback (not a signal at the top of a run).
        rsi_dipped  = rsi14.rolling(5).min().shift(1) < 45
        rsi_surged  = rsi14.rolling(5).max().shift(1) > 55
        from swingbot.core.indicators import macd as _macd_ema
        try:
            _me = _macd_ema(close)
            macd_pos = _me["macd"] > 0
            macd_neg = _me["macd"] < 0
        except Exception:
            macd_pos = macd_neg = pd.Series(True, index=close.index)
        # MACD positive OR RSI > 60 as alternative momentum confirm
        mom_bull = macd_pos | (rsi14 > 60)
        mom_bear = macd_neg | (rsi14 < 40)
        bullish = (held_bull & above_50 & (rsi14 > 50) & rsi_dipped & mom_bull & atr_ok & vol_ok).fillna(False)
        bearish = (held_bear & below_50 & (rsi14 < 50) & rsi_surged & mom_bear & ma200_down_120 & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    if strategy == "VWAP":
        vwap = rolling_vwap(df, h["vwap_window"])
        diff = close - vwap
        # 3-bar hold for 2w (noisier VWAP window); 2-bar hold for longer horizons
        if horizon_key == "2w":
            held_bull = (diff.shift(3) <= 0) & (diff.shift(2) > 0) & (diff.shift(1) > 0) & (diff > 0)
            held_bear = (diff.shift(3) >= 0) & (diff.shift(2) < 0) & (diff.shift(1) < 0) & (diff < 0)
        else:
            held_bull = (diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)
            held_bear = (diff.shift(2) >= 0) & (diff.shift(1) < 0) & (diff < 0)
        # VWAP trending in same direction confirms momentum
        vwap_trending_up   = vwap > vwap.shift(3)
        vwap_trending_down = vwap < vwap.shift(3)
        bullish = (held_bull & above_50 & (rsi14 > 50) & vwap_trending_up   & atr_ok & vol_ok).fillna(False)
        bearish = (held_bear & below_50 & (rsi14 < 50) & vwap_trending_down & ma200_down_120 & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    if strategy == "Fibonacci":
        lookback = h["fib_lookback"]
        swing_high = df["High"].rolling(lookback).max()
        swing_low  = df["Low"].rolling(lookback).min()
        rng = swing_high - swing_low
        ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
        levels_df = pd.DataFrame({r: swing_high - r * rng for r in ratios})
        nearest_distance = levels_df.sub(close, axis=0).abs().min(axis=1)
        distance_pct = (nearest_distance / rng * 100).replace([np.inf, -np.inf], np.nan)
        is_testing = (distance_pct <= FIB_TOLERANCE_PCT) & rng.gt(0)
        # Retracement bounce: price was higher 5 bars ago (pulled back to Fib support),
        # and is now starting to tick up (bounce beginning). Avoids signals where
        # price is approaching a Fib level from BELOW (resistance, not support).
        pulled_back_bull = close.shift(5) > close.shift(1)
        bouncing_bull    = close > close.shift(1)
        pulled_back_bear = close.shift(5) < close.shift(1)
        bouncing_bear    = close < close.shift(1)
        bullish = (is_testing & pulled_back_bull & bouncing_bull & above_50 & rsi14.between(35, 58) & atr_ok).fillna(False)
        bearish = (is_testing & pulled_back_bear & bouncing_bear & below_50 & rsi14.between(42, 65) & atr_ok).fillna(False)
        return bullish, bearish

    if strategy == "Support/Resistance":
        lookback = h["sr_lookback"]
        resistance = df["High"].rolling(lookback).max().shift(1)
        support    = df["Low"].rolling(lookback).min().shift(1)
        vol_avg20  = df["Volume"].rolling(20).mean()
        volume_confirmed = (df["Volume"] / vol_avg20) >= SR_VOLUME_MULTIPLE
        crossed_up   = (close.shift(1) <= resistance.shift(1)) & (close > resistance)
        crossed_down = (close.shift(1) >= support.shift(1))    & (close < support)
        # Volatility regime: skip breakouts during spike regimes (ATR elevated vs 60-bar avg).
        atr_calm = (atr14 <= atr14.rolling(60).mean() * 1.4).fillna(True)
        bullish = (crossed_up   & volume_confirmed & above_50 & atr_ok & atr_calm).fillna(False)
        bearish = (crossed_down & volume_confirmed & below_50 & atr_ok & atr_calm).fillna(False)
        return bullish, bearish

    if strategy == "RSI":
        # 2-bar confirmation at RSI<35: catches strong oversold events with enough signals.
        # 3-bar at RSI<30 is structurally incompatible with uptrend filters (crashes always
        # push price below all SMAs by bar 3). RSI<35 for 2 bars still filters whipsaws
        # while firing more often in quality setups.
        consec_oversold   = (rsi14.shift(1) < 35) & (rsi14.shift(2) < 35)
        consec_overbought = (rsi14.shift(1) > 65) & (rsi14.shift(2) > 65)
        crossed_up   = consec_oversold   & (rsi14 >= 35)
        crossed_down = consec_overbought & (rsi14 <= 65)
        # ATR-calm: skip high-volatility regimes (crash spikes cause false bounces)
        atr_calm = (atr14 <= atr14.rolling(60).mean() * 1.5).fillna(True)
        # Long-term trend: 200 SMA must be sloping up over 60 bars.
        # This fires even during a sharp crash in a bull market (COVID-style dip-and-recover),
        # because the 200 SMA is still trending up from prior months.
        ma200_up   = (ma200 > ma200.shift(120)).fillna(False)
        ma200_down = (ma200 < ma200.shift(120)).fillna(False)
        # Recovery confirmation: price must have started reversing (not still in freefall).
        # Bullish: close above where it was 3 bars ago. Bearish: below 3 bars ago.
        # This prevents catching falling knives where RSI bounces but price continues down.
        bounce_started = close > close.shift(3)
        fade_started   = close < close.shift(3)
        bullish = (crossed_up   & ma200_up   & bounce_started & (rsi14 < 40) & atr_ok & atr_calm).fillna(False)
        bearish = (crossed_down & ma200_down & fade_started   & (rsi14 > 60) & atr_ok & atr_calm).fillna(False)
        return bullish, bearish

    if strategy == "MACD":
        from swingbot.core.indicators import macd as _macd_fn
        horizon_to_macd = {
            "2w": (8, 17, 9), "4w": (12, 26, 9), "2m": (12, 26, 9),
            "3m": (19, 39, 9), "4m": (21, 43, 9), "5m": (24, 48, 9),
            "6m": (26, 52, 9), "7m": (28, 56, 9), "8m": (31, 61, 9),
            "9m": (33, 65, 9),
        }
        fast_p, slow_p, sig_p = horizon_to_macd.get(horizon_key, (12, 26, 9))
        _m = _macd_fn(close, fast=fast_p, slow=slow_p, signal=sig_p)
        macd_line, signal_line, hist = _m["macd"], _m["signal"], _m["histogram"]
        diff = macd_line - signal_line
        crossed_up   = (diff.shift(1) <= 0) & (diff > 0)
        crossed_down = (diff.shift(1) >= 0) & (diff < 0)
        # 2-bar histogram hold filters single-bar histogram whipsaws
        hist_held_bull = (hist.shift(2) <= 0) & (hist.shift(1) > 0) & (hist > 0)
        hist_held_bear = (hist.shift(2) >= 0) & (hist.shift(1) < 0) & (hist < 0)
        # Zero-line filter: only bullish signals when MACD is above zero (momentum regime)
        bullish = ((crossed_up | hist_held_bull) & above_50 & (macd_line > 0) & (rsi14 > 50) & atr_ok).fillna(False)
        bearish = ((crossed_down | hist_held_bear) & below_50 & (macd_line < 0) & (rsi14 < 50) & ma200_down_120 & atr_ok).fillna(False)
        return bullish, bearish

    if strategy == "Elliott Wave":
        # Simplified wave detection works best at the intermediate 4w horizon.
        # 2w is too noisy (rapid oscillations create false wave patterns),
        # 2m/3m/6m are too coarse (pattern approximation degrades). Only 4w fires.
        if horizon_key in ("2w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m"):
            empty = pd.Series(False, index=df.index)
            return empty, empty
        threshold_pct = h["max_risk_pct"]
        bullish_raw, bearish_raw, _ = elliott_wave3_entries(df, threshold_pct)
        # Trend + momentum confirmation: RSI>55 for 4w (longer holds need strong momentum).
        # RSI must be rising -- confirms momentum is building behind the wave.
        rsi_rising  = rsi14 > rsi14.shift(2)
        rsi_falling = rsi14 < rsi14.shift(2)
        bullish = (bullish_raw & above_50 & (rsi14 > 55) & rsi_rising  & atr_ok & vol_ok).fillna(False)
        bearish = (bearish_raw & below_50 & (rsi14 < 45) & rsi_falling & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    if strategy == "MA Ribbon":
        horizon_to_ribbon = {
            "2w": (10, 20, 50), "4w": (10, 20, 50),
            "2m": (20, 50, 100), "3m": (20, 50, 200),
            "4m": (30, 67, 200), "5m": (40, 83, 200),
            "6m": (50, 100, 200),
            "7m": (60, 117, 200), "8m": (70, 133, 200), "9m": (80, 150, 200),
        }
        fast_p, mid_p, slow_p = horizon_to_ribbon.get(horizon_key, (10, 20, 50))
        fast = ema(close, fast_p)
        mid  = ema(close, mid_p)
        slow_sma = close.rolling(slow_p).mean()
        diff = fast - mid
        crossed_up   = (diff.shift(1) <= 0) & (diff > 0) & (fast > slow_sma) & (mid > slow_sma)
        crossed_down = (diff.shift(1) >= 0) & (diff < 0) & (fast < slow_sma) & (mid < slow_sma)
        # "Not extended" filter: price within 8% of slow SMA, RSI in moderate zone
        not_extended_bull = (close <= slow_sma * 1.08) & rsi14.between(48, 70)
        not_extended_bear = (close >= slow_sma * 0.92) & rsi14.between(30, 52)
        from swingbot.core.indicators import macd as _macd_rib
        try:
            _mr = _macd_rib(close)
            macd_pos_r = _mr["macd"] > 0
            macd_neg_r = _mr["macd"] < 0
        except Exception:
            macd_pos_r = macd_neg_r = pd.Series(True, index=close.index)
        bullish = (crossed_up   & above_50 & not_extended_bull & macd_pos_r & atr_ok & vol_ok).fillna(False)
        bearish = (crossed_down & below_50 & not_extended_bear & macd_neg_r & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    if strategy == "Break & Retest":
        lookback = h["sr_lookback"]
        resistance = df["High"].rolling(lookback).max().shift(lookback)
        support    = df["Low"].rolling(lookback).min().shift(lookback)
        vol_avg    = df["Volume"].rolling(20).mean()
        vol_ratio  = df["Volume"] / vol_avg
        recent_bars = {
            "2w": 10, "4w": 15, "2m": 20, "3m": 25,
            "4m": 27, "5m": 28, "6m": 30, "7m": 32, "8m": 33, "9m": 35,
        }.get(horizon_key, 10)
        broke_up = (df["High"].rolling(recent_bars).max().shift(1) > resistance) & (vol_ratio.rolling(recent_bars).max().shift(1) >= SR_VOLUME_MULTIPLE)
        broke_dn = (df["Low"].rolling(recent_bars).min().shift(1) < support)    & (vol_ratio.rolling(recent_bars).max().shift(1) >= SR_VOLUME_MULTIPLE)
        dist_to_res = (close - resistance) / resistance.replace(0, np.nan) * 100
        dist_to_sup = (close - support)    / support.replace(0, np.nan)    * 100
        atr_calm_brt = (atr14 <= atr14.rolling(60).mean() * 1.4).fillna(True)
        # Tighter retest zone for noisy horizons (2w, 3m); wider for clean ones (4w, 2m).
        retest_pct = {
            "2w": 1.0, "4w": 1.5, "2m": 1.5, "3m": 1.0,
            "4m": 1.5, "5m": 1.5, "6m": 1.5, "7m": 1.5, "8m": 1.5, "9m": 1.5,
        }.get(horizon_key, 1.0)
        bullish = (broke_up & dist_to_res.between(0, retest_pct) & above_50 & rsi14.between(42, 63) & atr_ok & atr_calm_brt).fillna(False)
        bearish = (broke_dn & dist_to_sup.between(-retest_pct, 0) & below_50 & rsi14.between(37, 58) & ma200_down_120 & atr_ok & atr_calm_brt).fillna(False)
        return bullish, bearish

    if strategy == "RSI Divergence":
        lb = 20
        # Bullish divergence: price makes higher low but RSI makes lower low -> momentum building
        # Bearish divergence: price makes lower high but RSI makes higher high -> exhaustion
        price_hl = close > close.rolling(lb).min().shift(lb)
        rsi_ll   = rsi14 < rsi14.rolling(lb).min().shift(lb)
        price_lh = close < close.rolling(lb).max().shift(lb)
        rsi_hh   = rsi14 > rsi14.rolling(lb).max().shift(lb)
        # Bullish: trend must be up (above MA50), bearish: require confirmed 6-month downtrend
        bullish = (above_50 & price_hl & rsi_ll & rsi14.between(28, 52) & atr_ok & vol_ok).fillna(False)
        bearish = (ma200_down_120 & price_lh & rsi_hh & rsi14.between(48, 72) & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    if strategy == "Volume Profile":
        lookback = h["sr_lookback"]
        # Vectorized HVN calc (numpy, no per-bar DataFrame.iterrows()) -- identical
        # bins/HVN definition as the original, ~150x faster. iterrows() on a
        # `lookback`-row window for every single bar in the series made this by
        # far the slowest strategy to backtest (O(n * lookback) with heavy
        # pandas overhead); this does the same math on raw numpy arrays.
        _high = df["High"].values
        _low = df["Low"].values
        _vol = df["Volume"].values
        _mid = (_high + _low) / 2
        _n_bars = len(df)
        _n_bins = 20
        _hvn = np.full(_n_bars, np.nan)
        for _i in range(lookback, _n_bars):
            _lo_idx = _i - lookback
            _pmin = _low[_lo_idx:_i].min()
            _pmax = _high[_lo_idx:_i].max()
            _rng = _pmax - _pmin
            if _rng <= 0:
                continue
            _m = _mid[_lo_idx:_i]
            _idx = np.minimum(((_m - _pmin) / _rng * _n_bins).astype(int), _n_bins - 1)
            _bins = np.bincount(_idx, weights=_vol[_lo_idx:_i], minlength=_n_bins)
            _hvn[_i] = _pmin + (_bins.argmax() + 0.5) * _rng / _n_bins
        hvn_series = pd.Series(_hvn, index=df.index)
        dist_pct = (close - hvn_series) / hvn_series.replace(0, np.nan) * 100
        # RSI range filter ensures we're entering at a value level, not chasing extremes.
        # Bearish also requires confirmed 6-month downtrend via ma200_down_120.
        bullish = (dist_pct.between(0, 1.5) & above_50 & rsi14.between(44, 64) & atr_ok & vol_ok).fillna(False)
        bearish = (dist_pct.between(-1.5, 0) & below_50 & rsi14.between(36, 56) & ma200_down_120 & atr_ok & vol_ok).fillna(False)
        return bullish, bearish

    raise ValueError(f"Unknown strategy: {strategy}")


def _trade_plan_at(df, i, direction, strategy, horizon_key, atr_series, swing_high_series=None, swing_low_series=None, volume_ratio_series=None, entry_levels=None):
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


def run_backtest(
    ticker: str,
    df: pd.DataFrame,
    strategy: str,
    horizon_key: str,
    one_at_a_time: bool = True,
) -> BacktestSummary:
    """
    Run a backtest for one (ticker, strategy, horizon) combination.

    one_at_a_time: if True (default), skip new entry signals while a prior trade
    from the same (strategy, horizon) pair is still open. This simulates realistic
    trading where you don't stack multiple overlapping positions on the same setup.
    """
    min_bars = MIN_BARS[horizon_key]
    if len(df) < min_bars + 10:
        return BacktestSummary(
            ticker=ticker, strategy=strategy, horizon_key=horizon_key,
            total_signals=0, evaluated=0, wins=0, losses=0, timeouts=0,
            win_rate=None, avg_return_pct=None, avg_r_multiple=None,
            expectancy_r=None, max_drawdown_pct=None, avg_holding_days=None,
        )

    bullish_entries, bearish_entries = _vectorized_entries(df, strategy, horizon_key)
    atr_series = atr(df, 14)

    swing_high_series = swing_low_series = None
    if strategy == "Fibonacci":
        lookback = HORIZONS[horizon_key]["fib_lookback"]
        swing_high_series = df["High"].rolling(lookback).max()
        swing_low_series = df["Low"].rolling(lookback).min()

    volume_ratio_series = None
    if strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        volume_ratio_series = df["Volume"] / vol_avg20

    entry_levels = None
    if strategy == "Elliott Wave":
        threshold_pct = HORIZONS[horizon_key]["max_risk_pct"]
        _, _, entry_levels = elliott_wave3_entries(df, threshold_pct)

    high = df["High"].values
    low = df["Low"].values
    n = len(df)

    trades: list[BacktestTrade] = []
    total_signals = 0

    entry_idx = np.where((bullish_entries.values | bearish_entries.values))[0]
    _open_until: int = -1  # bar index after which the current trade has exited
    for i in entry_idx:
        if i < min_bars:
            continue
        total_signals += 1
        # Deduplication: skip while a prior trade is still open (realistic capital use)
        if one_at_a_time and i <= _open_until:
            continue
        direction = "bullish" if bullish_entries.values[i] else "bearish"
        entry, stop_loss, take_profit = _trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels
        )
        risk_per_share = abs(entry - stop_loss)
        if risk_per_share <= 0:
            continue

        outcome, exit_price, exit_i = "timeout", None, None
        max_holding_days = HORIZONS[horizon_key]["max_holding_days"]
        end = min(i + max_holding_days, n - 1)
        for j in range(i + 1, end + 1):
            hi, lo = float(high[j]), float(low[j])
            if direction == "bullish":
                hit_stop = lo <= stop_loss
                hit_target = hi >= take_profit
            else:
                hit_stop = hi >= stop_loss
                hit_target = lo <= take_profit

            if hit_stop:
                outcome, exit_price, exit_i = "loss", stop_loss, j
                break
            elif hit_target:
                outcome, exit_price, exit_i = "win", take_profit, j
                break

        if outcome == "timeout":
            _open_until = end
            trades.append(BacktestTrade(
                entry_date=str(df.index[i].date()), exit_date=None, direction=direction,
                entry=round(entry, 4), stop_loss=round(stop_loss, 4), take_profit=round(take_profit, 4),
                outcome="timeout", exit_price=None, return_pct=None, r_multiple=None, holding_days=None,
            ))
            continue

        _open_until = exit_i
        sign = 1 if direction == "bullish" else -1
        return_pct = (exit_price - entry) / entry * sign * 100
        r_multiple = (exit_price - entry) * sign / risk_per_share
        holding_days = exit_i - i

        trades.append(BacktestTrade(
            entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()), direction=direction,
            entry=round(entry, 4), stop_loss=round(stop_loss, 4), take_profit=round(take_profit, 4),
            outcome=outcome, exit_price=round(exit_price, 4), return_pct=round(return_pct, 3),
            r_multiple=round(r_multiple, 3), holding_days=holding_days,
        ))

    evaluated_trades = [t for t in trades if t.outcome in ("win", "loss")]
    wins = [t for t in evaluated_trades if t.outcome == "win"]
    losses = [t for t in evaluated_trades if t.outcome == "loss"]
    timeouts = [t for t in trades if t.outcome == "timeout"]

    win_rate = len(wins) / len(evaluated_trades) * 100 if evaluated_trades else None
    avg_return_pct = float(np.mean([t.return_pct for t in evaluated_trades])) if evaluated_trades else None
    avg_r_multiple = float(np.mean([t.r_multiple for t in evaluated_trades])) if evaluated_trades else None
    avg_holding_days = float(np.mean([t.holding_days for t in evaluated_trades])) if evaluated_trades else None

    expectancy_r = None
    if evaluated_trades:
        p_win = len(wins) / len(evaluated_trades)
        avg_win_r  = float(np.mean([t.r_multiple for t in wins]))  if wins  else 0.0
        avg_loss_r = float(np.mean([t.r_multiple for t in losses])) if losses else 0.0
        expectancy_r = p_win * avg_win_r + (1 - p_win) * avg_loss_r

    max_drawdown_pct = None
    if evaluated_trades:
        equity = [1.0]
        for t in evaluated_trades:
            equity.append(equity[-1] * (1 + t.return_pct / 100))
        equity = np.array(equity)
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max
        max_drawdown_pct = float(drawdowns.min() * 100)

    return BacktestSummary(
        ticker=ticker, strategy=strategy, horizon_key=horizon_key,
        total_signals=total_signals, evaluated=len(evaluated_trades),
        wins=len(wins), losses=len(losses), timeouts=len(timeouts),
        win_rate=win_rate, avg_return_pct=avg_return_pct, avg_r_multiple=avg_r_multiple,
        expectancy_r=expectancy_r, max_drawdown_pct=max_drawdown_pct,
        avg_holding_days=avg_holding_days, trades=trades,
    )


ALL_STRATEGIES = (
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence", "Volume Profile",
)


def run_full_backtest(ticker: str, df: pd.DataFrame) -> list[BacktestSummary]:
    """Backtest all strategies x all horizons for one ticker."""
    results = []
    for horizon_key in HORIZONS:
        for strategy in ALL_STRATEGIES:
            results.append(run_backtest(ticker, df, strategy, horizon_key))
    return results


def run_backtest_daterange(
    ticker: str,
    df: pd.DataFrame,
    strategy: str,
    horizon_key: str,
    date_from: str,
    date_to: str,
) -> BacktestSummary:
    """
    Same as run_backtest() but only evaluates signals whose entry_date falls
    within [date_from, date_to] (both inclusive, ISO format YYYY-MM-DD).
    The full df is still used for indicator warmup; the filter is applied
    after the backtest so indicator values are correct for every bar.
    """
    summary = run_backtest(ticker, df, strategy, horizon_key)
    if date_from or date_to:
        from_dt = date_from or "0000-01-01"
        to_dt   = date_to   or "9999-12-31"
        summary.trades = [
            t for t in summary.trades
            if from_dt <= t.entry_date <= to_dt
        ]
        ev = [t for t in summary.trades if t.outcome in ("win", "loss")]
        wins    = [t for t in ev if t.outcome == "win"]
        losses  = [t for t in ev if t.outcome == "loss"]
        timeouts = [t for t in summary.trades if t.outcome == "timeout"]
        summary.total_signals = len(summary.trades)
        summary.evaluated     = len(ev)
        summary.wins          = len(wins)
        summary.losses        = len(losses)
        summary.timeouts      = len(timeouts)
        summary.win_rate      = len(wins) / len(ev) * 100 if ev else None
        if ev:
            summary.avg_return_pct   = float(np.mean([t.return_pct for t in ev]))
            summary.avg_r_multiple   = float(np.mean([t.r_multiple for t in ev]))
            summary.avg_holding_days = float(np.mean([t.holding_days for t in ev]))
            p_win = len(wins) / len(ev)
            avg_win_r  = float(np.mean([t.r_multiple for t in wins]))  if wins  else 0.0
            avg_loss_r = float(np.mean([t.r_multiple for t in losses])) if losses else 0.0
            summary.expectancy_r = p_win * avg_win_r + (1 - p_win) * avg_loss_r
            equity = [1.0]
            for t in ev:
                equity.append(equity[-1] * (1 + t.return_pct / 100))
            equity = np.array(equity)
            running_max = np.maximum.accumulate(equity)
            drawdowns = (equity - running_max) / running_max
            summary.max_drawdown_pct = float(drawdowns.min() * 100)
        else:
            summary.avg_return_pct = summary.avg_r_multiple = summary.avg_holding_days = None
            summary.expectancy_r = summary.max_drawdown_pct = None
    return summary




# Confluence backtest engine (ConfluenceTrade, run_confluence_backtest, ...)
# lives in its own sibling module, backtest_confluence.py -- imported back
# here (deliberately at the BOTTOM of this file, after ALL_STRATEGIES and
# _vectorized_entries above are already defined) so every name that used
# to live directly in this module is still importable from
# swingbot.core.backtest exactly as before the split. backtest_confluence.py
# imports ALL_STRATEGIES/_vectorized_entries back from this module, so this
# one-directional ordering (define here first, then pull in the sibling)
# avoids a circular import between the two.
from .backtest_confluence import (
    CONFLUENCE_HORIZONS, CONFLUENCE_MIN_AGREE, CONFLUENCE_RR,
    ConfluenceTrade, run_confluence_backtest, run_confluence_backtest_daterange,
    summarize_confluence_trades,
)
