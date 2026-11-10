"""Shock failed bounce, short (v211, frozen 2026-11-05 in spec v209 § Track 2).

On a SHOCK_D date (_shock_breakdown.py): a bar b in t-5..t-1 bounced
(Close[b] > Close[b-1]) after a decline of at least 1 ATR14[b-2] from
max(High[b-10..b-2]), with a lower high (High[b] below that max); the latest
such b counts; today closes below Low[b] for the first time since b. The race
shorts the next open (fixed 1.5/3 ATR, 10-bar cap). The live follow-on's
placeable stop is a resting buy-stop just above High[b]; it is not part of the
frozen race. The control is the same trigger with the shock state ignored
(printed, never gating). One family with shock_support_break_short.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb

CAP = 10
RACE = "fixed"
DIRECTION = "short"
CONTEXT = sb.CONTEXT
CONTEXT_KIND = "level"
FAMILY = sb.FAMILY
SOURCE = sb.SOURCE
DECLINE_ATR = 1.0
HIGH_FROM = 10
HIGH_TO = 2
BOUNCE_FROM = 5
BOUNCE_TO = 1
PARAMS = {**sb.SHOCK_PARAMS, "decline_atr": DECLINE_ATR, "high_from": HIGH_FROM,
          "high_to": HIGH_TO, "bounce_from": BOUNCE_FROM, "bounce_to": BOUNCE_TO,
          "side": "short"}
SUMMARY = ("SHOCK_D on t; bounce bar b in t-5..t-1 (close[b-1] <= max(High[b-10..b-2]) "
           "- 1.0 ATR14[b-2], close[b] > close[b-1], High[b] < that max; latest b) "
           "and close[t] < Low[b], the first close below it since b (short, next open)")


def _recent_high(df: pd.DataFrame) -> pd.Series:
    """max(High[b-10 .. b-2]) seen from b."""
    return indicators.rolling_max(df["High"], HIGH_FROM - HIGH_TO + 1).shift(HIGH_TO)


def bounce_setup(df: pd.DataFrame) -> pd.Series:
    """Conditions 1-3 with b as the bounce bar (NaN warm-up -> False)."""
    hh = _recent_high(df)
    atr = indicators.atr(df).shift(2)                          # ATR14[b-2]
    prev = df["Close"].shift(1)
    setup = (prev <= hh - DECLINE_ATR * atr) & (df["Close"] > prev) & (df["High"] < hh)
    return setup.fillna(False).astype(bool)


def bounce_bar(df: pd.DataFrame) -> pd.Series:
    """Position of the latest b in t-5..t-1 with bounce_setup[b]; NaN when none."""
    n = len(df)
    pos = np.arange(n, dtype=float)
    setup = bounce_setup(df).to_numpy()
    latest = pd.Series(np.where(setup, pos, np.nan), index=df.index)
    latest = latest.shift(BOUNCE_TO).ffill()
    return latest.where(pos - latest <= BOUNCE_FROM)


def failure(df: pd.DataFrame, bounce: pd.Series) -> pd.Series:
    """Condition 4: Close[t] < Low[b] and no close in b+1 .. t-1 below it."""
    close, low = df["Close"].to_numpy(float), df["Low"].to_numpy(float)
    b, pos = bounce.to_numpy(float), np.arange(len(df))
    ok = np.isfinite(b)
    bi = np.where(ok, b, 0).astype(int)
    low_b = np.where(ok, low[bi], np.nan)
    with np.errstate(invalid="ignore"):
        hit = ok & (close < low_b)
        for lag in range(1, BOUNCE_FROM):             # bars t-1 .. t-4, only those after b
            prev = np.r_[np.full(lag, np.nan), close[:-lag]]
            hit &= ~((pos - lag > bi) & (prev < low_b))
    return pd.Series(hit, index=df.index)


def events(df: pd.DataFrame, context) -> pd.Series:
    out = failure(df, bounce_bar(df)) & sb.ticker_state(df, context)["shock"]
    return out.rename("shock_failed_bounce_short")


def control_events(df: pd.DataFrame) -> pd.Series:
    return failure(df, bounce_bar(df)).rename("shock_failed_bounce_short_control")
