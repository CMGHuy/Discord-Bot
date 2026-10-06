"""Hand-built price paths for fib_leg (v124). Bar i: High = p + 0.5,
Low = p - 0.5, Open = Close = p. mirror=True uses MIRROR - p, so every
bearish price expectation is MIRROR - (bullish price) and ratios are equal.

CLEAN (bars 0..17), k = 3:
  bar 3  p=13  swing high (H 13.5), confirmed at bar 6   -- the swing before the origin
  bar 7  p=9   swing low  (L 8.5),  confirmed at bar 10  -- the origin
  bar 13 p=15  highest High in (7, t] (H 15.5)           -- the end; >= 3 bars old from t=16
"""
import numpy as np
import pandas as pd

from tests.conftest import make_ohlcv

MIRROR = 30.0
CLEAN = [10, 11, 12, 13, 12, 11, 10, 9, 10, 11, 12, 13, 14, 15, 14, 13.5, 13, 12]
TIE = CLEAN[:14] + [15, 13.5, 13]            # bars 13 and 14 share High 15.5
BROKEN = CLEAN + [8]                          # bar 18 Low 7.5 undercuts the origin (8.5)
RESTART = CLEAN + [11.5, 12.5, 13.5, 14.5, 16, 15.5, 15, 14.8]   # bar 18 higher low (L 11.0), confirmed at 21
HIGH_PRIOR = CLEAN[:3] + [17] + CLEAN[4:]     # swing before the origin at H 17.5 > end 15.5
NO_PRIOR = [13, 12, 11, 10, 9, 10, 11, 12, 13, 14, 13, 12.5, 12]  # origin bar 4, end bar 9, no earlier swing high


def path_frame(path, *, mirror=False):
    p = np.asarray(path, dtype=float)
    if mirror:
        p = MIRROR - p
    idx = pd.bdate_range("2015-01-01", periods=len(p))
    return pd.DataFrame({"Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p,
                         "Volume": np.full(len(p), 1_000_000.0)}, index=idx)


def walk_frame(n=120, seed=124):
    closes = 100 + np.cumsum(np.random.default_rng(seed).normal(0.0, 1.0, n))
    return make_ohlcv(closes, spread_pct=2.0)
