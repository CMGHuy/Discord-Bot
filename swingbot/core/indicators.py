"""Technical indicator helpers used by the swing trading strategy."""
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_value = 100 - (100 / (1 + rs))
    # Where avg_loss is 0, RSI is 100 (pure uptrend)
    rsi_value = rsi_value.where(avg_loss != 0, 100)
    return rsi_value


def rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Rolling Volume-Weighted Average Price over `window` daily bars.

    True intraday VWAP needs tick/minute data; for a daily-bar swing bot we
    approximate it with a rolling window over typical price * volume, which
    is the standard way swing traders anchor VWAP on daily charts.
    """
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_vol = typical_price * df["Volume"]
    return tp_vol.rolling(window).sum() / df["Volume"].rolling(window).sum()


def fibonacci_levels(df: pd.DataFrame, lookback: int) -> dict:
    """
    Standard Fibonacci retracement levels between the highest high and
    lowest low over the last `lookback` bars.

    Returns a dict with swing_high, swing_low, and levels
    {ratio: price_level} for ratios 0.236, 0.382, 0.5, 0.618, 0.786,
    measured down from the swing high.
    """
    window = df.iloc[-lookback:]
    swing_high = float(window["High"].max())
    swing_low = float(window["Low"].min())
    diff = swing_high - swing_low

    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {r: swing_high - r * diff for r in ratios}
    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "levels": levels,
    }


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing) -- used to size stop-losses/targets."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def zigzag_pivots(df: pd.DataFrame, threshold_pct: float) -> list:
    """
    Simple zigzag pivot detector: walks closing prices and registers a
    pivot (a local high or low) each time price reverses by at least
    `threshold_pct` from the last confirmed extreme. This is the standard
    building block used to identify swing structure for pattern-based
    strategies (here: a simplified Elliott Wave count).

    Returns a list of (bar_index, price, kind) tuples in chronological
    order, where kind is "high" or "low" and bar_index is a positional
    index into df (0-based).
    """
    closes = df["Close"].values
    n = len(closes)
    pivots = []
    if n == 0:
        return pivots

    start_idx = 0
    start_price = closes[0]
    last_extreme_idx = 0
    last_extreme_price = closes[0]
    direction = None  # None until the first threshold-sized move establishes one

    for i in range(1, n):
        price = closes[i]
        if last_extreme_price == 0:
            continue
        change_pct = (price - last_extreme_price) / last_extreme_price * 100

        if direction is None:
            if change_pct >= threshold_pct:
                # First confirmed move is up -- the starting point was a low.
                pivots.append((start_idx, start_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i
            elif change_pct <= -threshold_pct:
                # First confirmed move is down -- the starting point was a high.
                pivots.append((start_idx, start_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "up":
            if price >= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (last_extreme_price - price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "high"))
                direction = "down"
                last_extreme_price, last_extreme_idx = price, i
        elif direction == "down":
            if price <= last_extreme_price:
                last_extreme_price, last_extreme_idx = price, i
            elif (price - last_extreme_price) / last_extreme_price * 100 >= threshold_pct:
                pivots.append((last_extreme_idx, last_extreme_price, "low"))
                direction = "up"
                last_extreme_price, last_extreme_idx = price, i

    return pivots


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    MACD (Moving Average Convergence Divergence).

    Returns a dict with three Series aligned to `series`:
      - 'macd'     : the MACD line (fast EMA - slow EMA)
      - 'signal'   : the signal line (EMA of MACD)
      - 'histogram': histogram (MACD - signal), positive = bullish momentum,
                     negative = bearish momentum.

    Standard parameters (12, 26, 9) work well for daily swing charts; the
    caller can pass horizon-adjusted values for shorter timeframes.
    """
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index -- measures TREND STRENGTH, not direction.
    Values: < 20 = weak/ranging, 20-25 = emerging trend, 25-40 = strong
    trend, > 40 = very strong trend. Direction comes from +DI vs -DI, not
    ADX itself. Used by confidence.py to boost setups in genuinely trending
    markets and penalise range-bound noise.

    Implemented with Wilder's smoothing (same as ATR/RSI) to match the
    standard charting-platform definition exactly.
    """
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)

    # True Range
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Directional moves
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Wilder smoothing (same as ATR)
    alpha = 1 / period
    atr_w = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_w

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan")))
    adx_series = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    return adx_series


def keltner_channel(df: pd.DataFrame, ema_period: int = 20, atr_period: int = 10,
                    multiplier: float = 1.5) -> dict:
    """
    Keltner Channel: EMA +/- multiplier * ATR.

    Used together with Bollinger Bands to detect the classic TTM Squeeze:
    when Bollinger Bands (2σ) contract INSIDE the Keltner Channel, the
    market is in extreme compression -- historically the highest-probability
    moment for a sharp directional breakout. When BBands re-expand outside
    the KC, the squeeze fires.

    Returns a dict of three Series: 'middle', 'upper', 'lower'.
    """
    middle = df["Close"].ewm(span=ema_period, adjust=False).mean()
    atr_val = atr(df, atr_period)
    return {
        "middle": middle,
        "upper": middle + multiplier * atr_val,
        "lower": middle - multiplier * atr_val,
    }


def elliott_wave3_entries(df: pd.DataFrame, threshold_pct: float):
    """
    Simplified Elliott Wave "wave 3 breakout" entry detector.

    IMPORTANT HONESTY NOTE: real Elliott Wave analysis is inherently
    subjective -- experienced analysts can and do disagree on wave counts
    for the same chart, and a full count involves Fibonacci-ratio checks
    across multiple wave degrees that resist full mechanization. This is
    a deliberately simplified, mechanical approximation of ONE piece of
    the theory: after a wave 1 impulse and a wave 2 pullback that respects
    the basic structural rule (wave 2 does not fully retrace past the
    start of wave 1), price breaking back past the wave 1 extreme is
    treated as the wave 3 entry signal -- wave 3 is conventionally the
    longest and most reliable wave to trade. This does NOT validate wave
    3/5 length ratios, alternation, or higher-degree wave context the way
    a full discretionary count would.

    Returns (bullish_entries, bearish_entries, entry_levels):
      - bullish_entries / bearish_entries: boolean pd.Series aligned to
        df.index, True on the bar where the wave 3 breakout is confirmed.
      - entry_levels: dict of {bar_index: {"wave1": price, "wave2": price}}
        for every triggered bar, so callers can size a structural stop
        beyond the wave 2 pivot without recomputing pivots themselves.
    """
    pivots = zigzag_pivots(df, threshold_pct)
    n = len(df)
    bullish = pd.Series(False, index=df.index)
    bearish = pd.Series(False, index=df.index)
    entry_levels = {}
    close = df["Close"].values

    for k in range(2, len(pivots)):
        idx0, p0, kind0 = pivots[k - 2]
        idx1, p1, kind1 = pivots[k - 1]
        idx2, p2, kind2 = pivots[k]

        if kind0 == "low" and kind1 == "high" and kind2 == "low" and p2 > p0:
            for j in range(idx2 + 1, n):
                if close[j] > p1 and close[j - 1] <= p1:
                    bullish.iloc[j] = True
                    entry_levels[j] = {"wave1": p1, "wave2": p2}
                    break
        elif kind0 == "high" and kind1 == "low" and kind2 == "high" and p2 < p0:
            for j in range(idx2 + 1, n):
                if close[j] < p1 and close[j - 1] >= p1:
                    bearish.iloc[j] = True
                    entry_levels[j] = {"wave1": p1, "wave2": p2}
                    break

    return bullish, bearish, entry_levels
