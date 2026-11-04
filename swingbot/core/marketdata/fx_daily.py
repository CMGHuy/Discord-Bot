"""v205 L1-a: one FX rate per currency pair per Berlin day.

`rate_before` is the one rule the 08:00 snap and the backfill both use
(core/marketdata/fx_snap.py): the last positive daily close dated strictly
before day D, so the value known at 08:00 Berlin on D is reproducible from the
frames (snap(D) == backfill(D)). `lookup` serves those stored rows
(`fx_daily_rates`) from a process memo keyed on the table's version.

Display only, like `fx`: a missing rate is None (the caller flags `fx_missing`),
never 1.0, and an unreadable table is a miss, never an exception. Codes in and
out are MAJOR ISO codes; the caller applies a minor unit's scale. This module
imports nothing from `fx` (fx imports it) and nothing from the admin.
"""
from __future__ import annotations

import bisect
import logging
import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

#: How old the bar behind a rate may be. A long weekend plus a holiday is four
#: days; a week covers every market closure without letting a stale rate stand
#: in for a missing one. `fx.FALLBACK_DAYS` is this object (V205-15).
FALLBACK_DAYS = 7

#: How often a process asks whether the table changed.
VERSION_CHECK_S = 60


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


@dataclass(frozen=True)
class _Memo:
    version: tuple | None
    checked_at: float
    pairs: dict = field(default_factory=dict)   # (base, account) -> ([day], [(day, rate, bar_date)])


_memo: _Memo | None = None


def reset_memo() -> None:
    """Forget the loaded table (tests; nothing in production calls it)."""
    global _memo
    _memo = None


def _index(rows: list[dict]) -> dict:
    """Rows ordered by (base, account, day) -> per pair, parallel sorted lists for bisect."""
    pairs: dict = {}
    for row in rows:
        days, entries = pairs.setdefault((row["base"], row["account"]), ([], []))
        days.append(row["day"])
        entries.append((row["day"], float(row["rate"]), row["bar_date"]))
    return pairs


def _current(now: float) -> _Memo:
    """The memo, its version re-checked once VERSION_CHECK_S has passed."""
    global _memo
    memo = _memo
    if memo is not None and now - memo.checked_at < VERSION_CHECK_S:
        return memo
    repo = fx_daily_rate_repo()
    version = tuple(repo.version())
    if memo is not None and memo.version == version:
        memo = _Memo(version, now, memo.pairs)
    else:
        memo = _Memo(version, now, _index(repo.all_rates()))
    _memo = memo
    return memo


def _pick(series, day: date) -> float | None:
    """The exact row's rate, else the nearest earlier row's if its bar is within FALLBACK_DAYS."""
    if not series:
        return None
    days, entries = series
    position = bisect.bisect_right(days, day)
    if position == 0:
        return None
    row_day, rate, bar_date = entries[position - 1]
    if row_day == day or (day - bar_date).days <= FALLBACK_DAYS:
        return rate
    return None


def lookup(base: str, account: str, day: date) -> float | None:
    """The stored rate for (major base, major account, Berlin day), or None.

    A read error is None for this call, keeps the memo, and waits
    VERSION_CHECK_S before asking again (the deploy window before
    `alembic upgrade head` creates the table)."""
    global _memo
    now = _clock()
    try:
        memo = _current(now)
    except Exception as exc:
        swallowed(log, "marketdata.fx_daily.lookup", exc, level=logging.DEBUG)
        kept = _memo
        _memo = _Memo(kept.version if kept else None, now, kept.pairs if kept else {})
        return None
    return _pick(memo.pairs.get((base, account)), day)
