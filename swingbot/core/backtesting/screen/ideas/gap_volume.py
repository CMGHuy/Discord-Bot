"""Gap + volume continuation (earnings/news gap drift). Trigger: V140-8."""
from __future__ import annotations

import pandas as pd

CAP = 20
PARAMS = {"gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
SUMMARY = ("open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar "
           "mean volume ending the prior bar, close >= open")
SOURCE = "earnings/news gap drift; volume as the news proxy"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-8 implements the gap_volume trigger")
