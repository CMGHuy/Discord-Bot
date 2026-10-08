"""Turn of the month (Ariel 1987; Lakonishok & Smidt 1988). Trigger frozen 2026-10-08 (v140)."""
from __future__ import annotations

import numpy as np
import pandas as pd

CAP = 4
PARAMS = {"day": "last trading day of the calendar month"}
SUMMARY = "t is the last trading day of its calendar month (ticker's own bar dates)"
SOURCE = "Ariel (1987); Lakonishok & Smidt (1988)"


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t when the next bar's DATE is in a new month.

    Reads the index only, never a price: the exchange calendar is public in
    advance. The frame's final bar has no next date and is False (reading F1).
    """
    index = pd.DatetimeIndex(df.index)
    months = np.asarray(index.year * 12 + index.month)
    last = np.zeros(len(months), dtype=bool)
    last[:-1] = months[1:] != months[:-1]
    return pd.Series(last, index=df.index, name="turn_of_month")
