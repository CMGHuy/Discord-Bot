"""v214 G3: fvg_overhead_aged. The live FVG detector per bar on df.iloc[:t+1];
bearish gaps aged >= 5 bars; within reach = Close[t] < bottom <= Close[t] +
3 x ATR14[t]; one event per gap bar_index, at its first qualifying bar;
control = no gap within reach but an aged gap beyond it.

Frozen 2026-11-06 (v214 G3). Avoid mode: must do worse than the matched null
and the out-of-reach control (screen/verdict.py). Event uses Close[t] as the
frozen proxy for the next-open entry. Never vectorised: the per-bar call is
the implementation (a vectorised form needs the spec's parity test).

NO-LOOKAHEAD: the state at bar t reads bars 0..t only -- the detector runs on
df.iloc[:t+1], ATR14 is trailing, and Close[t] is the bar's own close.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.errors import IdeaError
from swingbot.core.market import fvg

NAME = "fvg_overhead_aged"
CAP = 20
MODE = "avoid"
RACE = "fixed"
DIRECTION = "long"
ENTRY = "next_open"
MIN_AGE_BARS = 5
REACH_ATR = 3.0
STATE_COLUMNS = ("event", "control_condition", "condition", "bottom")
PARAMS = {"side": "bearish", "anchor": "bottom", "min_age_bars": MIN_AGE_BARS,
          "reach_atr": REACH_ATR, "atr_n": 14, "lookback": fvg.LOOKBACK_BARS,
          "max_per_side": fvg.MAX_GAPS_PER_SIDE, "fill": "any wick touch",
          "onset": "once per gap bar_index"}
SUMMARY = ("first bar t at which an unfilled bearish FVG (live detector on bars <= t) "
           "aged >= 5 bars has Close[t] < bottom <= Close[t] + 3 x ATR14[t]; once per "
           "gap; avoid mode against the null and an out-of-reach control")
SOURCE = ("docs/superpowers/results/2026-11-06-loss-review-sep-nov.md: live longs whose "
          "TP1 sits at an older unfilled bearish FVG, N = 68, ExpR -0.199R since "
          "2026-09-01 (motivation only)")


def _inputs(df: pd.DataFrame):
    try:
        return (indicators.atr(df, PARAMS["atr_n"]).to_numpy(dtype=float),
                df["Close"].to_numpy(dtype=float))
    except Exception as exc:
        raise IdeaError(f"{NAME}: cannot read the frame: {exc!r}") from exc


def _aged_bearish(df: pd.DataFrame, t: int) -> list:
    try:
        gaps = fvg.scan_fair_value_gaps(df.iloc[: t + 1], PARAMS["lookback"],
                                        PARAMS["max_per_side"])
    except Exception as exc:
        raise IdeaError(f"{NAME}: FVG detector failed at bar {t} "
                        f"({df.index[t]}): {exc!r}") from exc
    return [g for g in gaps
            if g["direction"] == "bearish" and t - g["bar_index"] >= MIN_AGE_BARS]


def _split_by_reach(aged: list, close: float, reach: float) -> tuple[list, list]:
    """Aged gaps with close < bottom <= reach, and those with bottom > reach."""
    within = [g for g in aged if close < g["bottom"] <= reach]
    beyond = [g for g in aged if g["bottom"] > reach]
    return within, beyond


def states(df: pd.DataFrame) -> pd.DataFrame:
    """Per bar: event (first bar a gap is in reach), condition (any aged gap
    in reach), control_condition (none in reach, one beyond) and the lowest
    in-reach bottom on event bars."""
    atr, close = _inputs(df)
    n = len(df)
    event, control, condition = (np.zeros(n, dtype=bool) for _ in range(3))
    bottom = np.full(n, np.nan, dtype=float)
    fired: set[int] = set()
    for t in np.flatnonzero(np.isfinite(atr)):
        within, beyond = _split_by_reach(_aged_bearish(df, int(t)),
                                         close[t], close[t] + REACH_ATR * atr[t])
        condition[t] = bool(within)
        control[t] = not within and bool(beyond)
        if any(g["bar_index"] not in fired for g in within):
            event[t] = True
            bottom[t] = min(g["bottom"] for g in within)
        fired.update(g["bar_index"] for g in within)
    return pd.DataFrame({"event": event, "control_condition": control,
                         "condition": condition, "bottom": bottom},
                        index=df.index, columns=list(STATE_COLUMNS))


def events(df: pd.DataFrame) -> pd.Series:
    return states(df)["event"].rename("fvg_overhead_aged")
