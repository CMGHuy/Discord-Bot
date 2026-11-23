"""v239: the live (s, D) session pair and the completed-bar cut.

D is the NYSE session the bear-regime label is FOR; s is the last completed
session before it. s is the date of session.last_regular_close(now), which is
holiday-aware and closes a half-day at 13:00 ET; D is the next NYSE session
after s. A weekend, a holiday, a half-day after its early close, and a scan
after the close but before the refresher ran each map to one pair.

cut_completed keeps only bars dated on or before s. It does not call
strategy_pass.completed_frame: that helper is weekday 09:30-16:00 only, so
between 13:00 and 16:00 on a half-day it would drop the session's completed
bar. On a regular day the two cuts agree (tests/regime/test_regime_calendar.py).
The calendar covers 2018-2030 (session.NYSE_LAST_YEAR_COVERED); the 1993
base-rate study derives its sessions from the SPY bar index instead.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from swingbot.core.market import session


def session_pair(now: dt.datetime) -> tuple[dt.date, dt.date]:
    """``(s, D)``: the last completed NYSE session and the one the label is for."""
    last = session.last_regular_close(now).astimezone(session.US_MARKET_TZ).date()
    target = session.nyse_calendar().next_session(last)
    if target is None:
        raise ValueError(f"no NYSE session after {last} in the frozen calendar")
    return last, target


def cut_completed(df: pd.DataFrame | None, now: dt.datetime) -> pd.DataFrame | None:
    """Every bar dated on or before s; later bars (partial or stray) are dropped."""
    if df is None or len(df) == 0:
        return df
    last, _ = session_pair(now)
    return df.loc[pd.DatetimeIndex(df.index).date <= last]


def sessions_between(older: dt.date, newer: dt.date) -> int:
    """NYSE sessions after ``older`` up to and including ``newer``."""
    if newer <= older:
        return 0
    return len(session.nyse_calendar().sessions(older + dt.timedelta(days=1), newer))
