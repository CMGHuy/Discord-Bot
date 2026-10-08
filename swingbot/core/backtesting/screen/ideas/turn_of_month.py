"""Turn of the month (Ariel 1987; Lakonishok & Smidt 1988). Trigger: V140-9."""
from __future__ import annotations

import pandas as pd

CAP = 4
PARAMS = {"day": "last trading day of the calendar month"}
SUMMARY = "t is the last trading day of its calendar month (ticker's own bar dates)"
SOURCE = "Ariel (1987); Lakonishok & Smidt (1988)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-9 implements the turn_of_month trigger")
