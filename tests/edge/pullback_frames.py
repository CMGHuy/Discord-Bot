"""Hand-built frames with one known impulse leg and one known pullback leg (v122).

Bars 0..79 are flat (no strict fractal pivot). Bar 80 is the swing low SL0,
bars 81..90 climb to the swing high SH at bar 90, and bars 91..96 pull back.
With k=3 pivots SH is confirmed from bar 93, and at t=96 Close (104) is below
High[SH] (112). So the impulse leg is bars 80..90 at IMPULSE_VOLUME and the
pullback leg is bars 91..96 at `pullback_volume`, which makes the ratio
pullback_volume / IMPULSE_VOLUME.
"""
import pandas as pd

IMPULSE_VOLUME = 2_000_000.0
FLAT_BARS = 80


def pullback_frame(pullback_volume: float) -> pd.DataFrame:
    closes, highs, lows = [100.0] * FLAT_BARS, [101.0] * FLAT_BARS, [99.0] * FLAT_BARS
    volumes = [1_000_000.0] * FLAT_BARS
    closes.append(97.0); highs.append(101.0); lows.append(95.0); volumes.append(IMPULSE_VOLUME)
    for step in range(1, 11):
        close = 100.0 + step
        closes.append(close); highs.append(close + (2.0 if step == 10 else 1.0))
        lows.append(close - 1.0); volumes.append(IMPULSE_VOLUME)
    for step in range(1, 7):
        close = 110.0 - step
        closes.append(close); highs.append(close + 1.0); lows.append(close - 1.0)
        volumes.append(pullback_volume)
    opens = [closes[0]] + closes[:-1]
    index = pd.bdate_range("2019-01-01", periods=len(closes))
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes,
                         "Volume": volumes}, index=index)


def mirror(df: pd.DataFrame, pivot: float = 200.0) -> pd.DataFrame:
    """The bearish twin: prices reflected around `pivot`, volume unchanged."""
    out = df.copy()
    out["Open"], out["Close"] = pivot - df["Open"], pivot - df["Close"]
    out["High"], out["Low"] = pivot - df["Low"], pivot - df["High"]
    return out
