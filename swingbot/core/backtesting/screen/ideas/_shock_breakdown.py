"""v211 shock breakdown family (spec v209 § Track 2, frozen 2026-11-05): the
daily shock state SHOCK_D both shock ideas read. Enter SHOCK on BREADTH_ATR1
>= 0.40; while SHOCK, release on the first date with BREADTH_ATR1 <= 0.10 and
the ^VIX close below the previous ^VIX close, the release date itself still
SHOCK; the next date is NORMAL unless BREADTH_ATR1 >= 0.40 again (a new
episode). No RECOVERY tier: daily bars cannot see the intraday repair. The
state on t reads context bars dated <= t only; a stock date the context lacks
is NORMAL, never forward-filled. Not the live market-shock detector (no
sector clause, no fast path, no VIX relief); a pass does not license its
labels. Not an idea module (no CAP, no events): the leading underscore keeps
it out of IDEA_MODULES."""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators

BREADTH = "BREADTH_ATR1"
VIX = "^VIX"
CONTEXT = (BREADTH, VIX)
ENTER_BREADTH = 0.40
RELEASE_BREADTH = 0.10
LOW_WINDOW = 20
SHOCK_PARAMS = {"breadth": BREADTH, "vix": VIX,
                "enter": ENTER_BREADTH, "release": RELEASE_BREADTH}
FAMILY = ("shock_support_break_short", "shock_failed_bounce_short")
SOURCE = ("v209 spec § Track 2 (frozen 2026-11-05): breadth-shock-conditioned "
          "breakdown shorts, after the 2026-11-05 session the long book lost 13.9R")


def _vix_down(vix: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    """True where the ^VIX close is below its own previous row's close."""
    down = (vix < vix.shift(1)).reindex(index, fill_value=False)
    return down.to_numpy(dtype=bool)


def _step(shock: bool, episode: int, breadth: float,
          down: bool) -> tuple[bool, int, bool]:
    """(shock_today, episode_today, shock_tomorrow); NaN breadth compares False."""
    shock_today = shock
    if not shock and breadth >= ENTER_BREADTH:
        shock_today, episode = True, episode + 1
    released = breadth <= RELEASE_BREADTH and down
    return shock_today, episode, shock_today and not released


def shock_state(breadth: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """Daily ``shock`` (bool) and ``episode`` (int64, 0 when NORMAL) on breadth's index."""
    values = breadth.to_numpy(dtype=float)
    downs = _vix_down(vix, breadth.index)
    shocks, episodes = np.zeros(len(values), dtype=bool), np.zeros(len(values), dtype=np.int64)
    shock, last = False, 0
    for i, value in enumerate(values):
        today, last, shock = _step(shock, last, value, bool(downs[i]))
        shocks[i] = today
        episodes[i] = last if today else 0
    return pd.DataFrame({"shock": shocks, "episode": episodes}, index=breadth.index)


def ticker_state(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """The shock state on ``df.index``; a date the context lacks is False/0."""
    state = shock_state(context[BREADTH]["Close"], context[VIX]["Close"])
    return pd.DataFrame(
        {"shock": state["shock"].reindex(df.index, fill_value=False).astype(bool),
         "episode": state["episode"].reindex(df.index, fill_value=0).astype(np.int64)},
        index=df.index)


def prior_low(df: pd.DataFrame, n: int = LOW_WINDOW) -> pd.Series:
    """min(Low[t-n .. t-1]); NaN until n prior bars."""
    return indicators.rolling_min(df["Low"].shift(1), n)


def prior_atr(df: pd.DataFrame) -> pd.Series:
    """ATR(14) as of bar t-1, dated t."""
    return indicators.atr(df).shift(1)
