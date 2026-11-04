"""v205 L1-a: one FX rate per currency pair per Berlin day.

`rate_before` is the one rule the 08:00 snap and the backfill both use
(core/marketdata/fx_snap.py): the last positive daily close dated strictly
before day D, so the value known at 08:00 Berlin on D is reproducible from the
frames (snap(D) == backfill(D)). `lookup` (V205-12b) serves those stored rows
(`fx_daily_rates`) from a process memo keyed on the table's version.

Display only, like `fx`: a missing rate is None (the caller flags `fx_missing`),
never 1.0, and an unreadable table is a miss, never an exception. Codes in and
out are MAJOR ISO codes; the caller applies a minor unit's scale. This module
imports nothing from `fx` (fx imports it) and nothing from the admin.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

#: How old the bar behind a rate may be. A long weekend plus a holiday is four
#: days; a week covers every market closure without letting a stale rate stand
#: in for a missing one. `fx.FALLBACK_DAYS` is this object (V205-15).
FALLBACK_DAYS = 7


def _clock() -> float:
    """Monotonic seconds; the seam tests replace (never a patched stdlib `time`)."""
    return time.monotonic()


def _bar_dates(index) -> np.ndarray:
    """Each stamp's own calendar date as datetime64[D]; a tz-aware index keeps its wall date."""
    stamps = pd.DatetimeIndex(pd.to_datetime(index))
    if stamps.tz is not None:
        stamps = stamps.tz_localize(None)
    return stamps.normalize().to_numpy().astype("datetime64[D]")


def rate_before(frame: pd.DataFrame | None, day: date) -> tuple[float, date] | None:
    """`(close, bar_date)` of the last positive close dated strictly before `day`,
    or None when there is none or its bar is more than FALLBACK_DAYS before `day`."""
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return None
    dates = _bar_dates(frame.index)
    closes = pd.to_numeric(frame["Close"], errors="coerce").to_numpy(dtype=float)
    keep = (dates < np.datetime64(day, "D")) & np.isfinite(closes) & (closes > 0)
    if not keep.any():
        return None
    kept_dates, kept_closes = dates[keep], closes[keep]
    newest = kept_dates.max()
    position = int(np.flatnonzero(kept_dates == newest)[-1])
    bar_date = newest.astype(object)
    if (day - bar_date).days > FALLBACK_DAYS:
        return None
    return float(kept_closes[position]), bar_date
