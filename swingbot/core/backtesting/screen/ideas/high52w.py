"""52-week-high momentum (George & Hwang 2004). Trigger: V140-6."""
from __future__ import annotations

import pandas as pd

CAP = 60
PARAMS = {"near_high": 0.95, "lookback": 252, "fast_sma": 50, "slow_sma": 200,
          "quiet_bars": 20}
SUMMARY = ("close >= 0.95 x the 252-bar high with SMA50 > SMA200; first true "
           "bar after >= 20 consecutive computable false bars")
SOURCE = "George & Hwang (2004)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-6 implements the high52w trigger")
