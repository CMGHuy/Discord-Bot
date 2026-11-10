"""v211 (spec § Track 2, Printed alongside each verdict): the shock read-outs
printed beside a level idea's verdict -- gap split, day of the episode, the
shock-day null, the 3 x friction stress factor and the outcome-blind
preflight. Pure; never gating; reads no bar after the signal date."""
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import null, race, verdict

#: spec "stress": the shock verdict is re-printed at 3 x slippage.
SHOCK_STRESS_SLIPPAGE_FACTOR = 3
#: spec "gap split": next-open gap vs signal close, in percent.
GAP_BUCKETS = ("<= -1%", "-1% .. +1%", ">= +1%")
#: spec "day of the episode": the breadth peak so far, or any later shock date.
EPISODE_DAYS = ("peak", "later")


def gap_bucket(gap_pct: float) -> str | None:
    """Bucket a gap in percent; -1 % and +1 % fall on the outer buckets."""
    if not np.isfinite(gap_pct):
        return None
    if gap_pct <= -1.0:
        return GAP_BUCKETS[0]
    if gap_pct >= 1.0:
        return GAP_BUCKETS[2]
    return GAP_BUCKETS[1]


def _gaps(df, signal_pos) -> np.ndarray:
    """100 * (Open[t+1] - Close[t]) / Close[t]; NaN on the last bar."""
    pos = np.asarray(signal_pos, dtype=int)
    gaps = np.full(len(pos), np.nan)
    has_next = pos + 1 < len(df)
    close = df["Close"].to_numpy(dtype=float)[pos[has_next]]
    nxt = df["Open"].to_numpy(dtype=float)[pos[has_next] + 1]
    gaps[has_next] = 100.0 * (nxt - close) / close
    return gaps


def _episode_days(state, breadth, index, signal_pos) -> list:
    """peak / later / None per signal bar; the running max reads earlier rows only."""
    on = breadth.reindex(index)
    episode = state["episode"].reindex(index, fill_value=0).to_numpy(dtype=int)
    running = on.groupby(episode).cummax().to_numpy()
    values = on.to_numpy()
    out = []
    for t in np.asarray(signal_pos, dtype=int):
        if episode[t] == 0:
            out.append(None)
        elif values[t] >= running[t]:
            out.append("peak")
        else:
            out.append("later")
    return out


def event_tags(df, state: pd.DataFrame, breadth: pd.Series, signal_pos: np.ndarray) -> list[dict]:
    """One tag dict per signal position, in order."""
    signal_pos = np.asarray(signal_pos, dtype=int)
    if len(signal_pos) == 0:
        return []
    dates = df.index[signal_pos].strftime("%Y-%m-%d")
    gaps = _gaps(df, signal_pos)
    days = _episode_days(state, breadth, df.index, signal_pos)
    return [{"signal_date": d, "gap_pct": float(g), "gap_bucket": gap_bucket(g),
             "episode_day": e} for d, g, e in zip(dates, gaps, days)]


@dataclass(frozen=True, eq=False)
class ShockNull:
    event_pos: np.ndarray
    null_mean_r: np.ndarray
    dropped: int


def shock_null(df, event_pos, pool: np.ndarray, k: int, seed, *, cap: int, atr, shape: str,
               direction: str, slippage_bps=None, commission=None) -> ShockNull:
    """K pool bars per event drawn without replacement, raced like the idea."""
    event_pos = np.asarray(event_pos, dtype=int)
    bars = np.flatnonzero(np.asarray(pool, dtype=bool))
    if len(event_pos) == 0 or len(bars) < null.MIN_CANDIDATES:
        return ShockNull(np.array([], dtype=int), np.array([], dtype=float), len(event_pos))
    rng = np.random.default_rng(seed)
    size = min(k, len(bars))
    groups = [np.sort(rng.choice(bars, size=size, replace=False)) for _ in event_pos]
    extra = {} if direction == "long" else {"direction": direction}
    raced = race.race_for(shape)(df, np.concatenate(groups), cap, atr=atr,
                                 slippage_bps=slippage_bps, commission=commission, **extra)
    means = raced.r.reshape(len(groups), size).mean(axis=1)
    return ShockNull(event_pos, means, 0)


def preflight_years(state: pd.DataFrame, event_dates: Iterable, years=verdict.YEARS) -> dict[int, dict]:
    """Shock days, distinct ISO shock weeks and events per calendar year."""
    days = state.index[state["shock"].to_numpy(dtype=bool)]
    iso = days.isocalendar()
    events = pd.DatetimeIndex(pd.to_datetime(list(event_dates)))
    out = {}
    for year in years:
        in_year = np.asarray(days.year == year)
        weeks = set(zip(iso["year"][in_year], iso["week"][in_year]))
        out[year] = {"shock_days": int(in_year.sum()), "shock_weeks": len(weeks),
                     "events": int((events.year == year).sum())}
    return out
