"""Publication-lag-aware historical macro frame — the no-lookahead
foundation G90's backtest snapshots stand on. Monthly prints become
visible on their RELEASE date (from the G29 calendar), not their
reference month.

Post-audit registry (see the G41 audit note): the standalone series.py was
cut with G13-G20, so the registry lives here and lists only what survives —
VIX plus the derived daily series. All of them are same-day prints, so the
lag machinery is currently a no-op in production. It is kept generic and
tested anyway: it is the thing that makes a monthly series safe to add, and
getting it wrong is a silent lookahead bug that inflates every backtest.
"""
from __future__ import annotations

import os

import pandas as pd

from swingbot import config
from swingbot.core.jsonio import read_json
from swingbot.core.macro import calendar_events

HISTORY_DIR = os.path.join(config.DATA_DIR, "macro", "history")

# The surviving series. Daily prints, zero publication lag.
SERIES_KEYS = ("vix", "vix_percentile", "breadth_50dma", "breadth_200dma")

# series key -> release kind gating its visibility. Unlisted keys are
# daily prints (VIX, breadth: same-day). The monthly mappings are retained
# so a future monthly series is lag-correct the moment it is registered.
_RELEASE_KIND = {
    "cpi_yoy": "cpi", "core_cpi_yoy": "cpi", "cpi_mom": "cpi",
    "ppi_yoy": "ppi", "ppi_mom": "ppi", "core_ppi_yoy": "ppi",
    "pce_yoy": "pce", "core_pce_yoy": "pce",
    "unemployment": "nfp", "payrolls_change_k": "nfp",
}


def _visible_from(obs_date: str, key: str, release_dates: dict) -> str:
    """A monthly print for reference month M becomes visible on the first
    release date AFTER M's month-end; daily series are same-day."""
    kind = _RELEASE_KIND.get(key)
    if kind is None:
        return obs_date
    month_end = (pd.Timestamp(obs_date) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    for release in release_dates.get(kind, ()):
        if release > month_end:
            return release
    return month_end        # no known release: month-end (still conservative)


def as_of_frame(start: str = "2018-01-01", end: str | None = None,
                series_keys=None) -> pd.DataFrame:
    """Date-indexed frame, one column per series key, forward-filled from
    the date each observation actually became public.

    series_keys is injectable so a caller (or a test) can build a frame for
    keys outside the shipped registry without the registry pretending to
    provide data it does not have.
    """
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    idx = pd.bdate_range(start, end)
    release_dates: dict[str, list[str]] = {}
    for e in calendar_events.load_events():
        release_dates.setdefault(e["kind"], []).append(e["date"])
    for dates in release_dates.values():
        dates.sort()
    frame = pd.DataFrame(index=idx)
    for key in (series_keys or SERIES_KEYS):
        col = pd.Series(index=idx, dtype=float)
        raw = read_json(os.path.join(HISTORY_DIR, f"{key}.json"), default=None)
        for obs_date, value in raw or []:
            ts = pd.Timestamp(_visible_from(obs_date, key, release_dates))
            pos = idx.searchsorted(ts)
            if pos < len(idx):
                col.iloc[pos] = value          # later prints overwrite on same day
        frame[key] = col.ffill()
    return frame
