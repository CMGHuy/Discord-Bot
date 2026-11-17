"""v229 time basis. The VM's 5-minute archive stamps each bar with its START
and an explicit UTC offset; the journal export writes UTC text. Both are read
here with UTC parsing -- never through data_store.load_normalized (drops the
zone) or cache_path (creates directories). 15:30 ET is derived per date
through zoneinfo, so it moves with daylight saving."""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market.session import (  # noqa: E402
    RTH_OPEN, is_early_close, nyse_calendar, session_close)
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFER_AT = dt.time(15, 30)
BAR_MINUTES = 5
COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_OFFSET = re.compile(r"(Z|[+-]\d{2}(:?\d{2})?)$")


class ArchiveError(ValueError):
    """An archive file exists but cannot be trusted as bar-start UTC bars."""


def to_utc(text) -> pd.Timestamp:
    """Parse a timestamp as UTC; ValueError on blank or unparseable text."""
    if text is None or not str(text).strip():
        raise ValueError("empty timestamp")
    ts = pd.to_datetime(str(text).strip(), utc=True)
    if pd.isna(ts):
        raise ValueError(f"unparseable timestamp {text!r}")
    return pd.Timestamp(ts)


def et_date(ts) -> dt.date:
    return pd.Timestamp(ts).tz_convert(ET).date()


def et_time(ts) -> dt.time:
    return pd.Timestamp(ts).tz_convert(ET).time()


def _utc_at(d: dt.date, wall: dt.time) -> pd.Timestamp:
    return pd.Timestamp(dt.datetime.combine(d, wall), tz=ET).tz_convert("UTC")


def session_open(d: dt.date) -> pd.Timestamp:
    return _utc_at(d, RTH_OPEN)


def session_close_utc(d: dt.date) -> pd.Timestamp:
    return _utc_at(d, session_close(d))


def deferral_start(d: dt.date) -> pd.Timestamp | None:
    """15:30 ET on ``d`` in UTC; None on a half day or a non-session day."""
    if not nyse_calendar().is_session(d) or is_early_close(d):
        return None
    return _utc_at(d, DEFER_AT)


def horizon_end(d: dt.date, sessions: int = 5) -> pd.Timestamp | None:
    """UTC close of the ``sessions``-th session after ``d``; None past the calendar."""
    last = nyse_calendar().session_after(d, sessions)
    return None if last is None else session_close_utc(last)


def _regular_mask(index: pd.DatetimeIndex) -> np.ndarray:
    local = index.tz_convert(ET)
    cal = nyse_calendar()
    closes = {d: session_close(d) for d in set(local.date) if cal.is_session(d)}
    return np.array([d in closes and RTH_OPEN <= t < closes[d]
                     for d, t in zip(local.date, local.time)], dtype=bool)


def _parse_index(raw: pd.Index, path: Path) -> pd.DatetimeIndex:
    text = raw.astype(str)
    naive = [s for s in text if not _OFFSET.search(s.strip())]
    if naive:
        raise ArchiveError(f"{path}: stamp without a UTC offset, e.g. {naive[0]!r}")
    try:
        return pd.DatetimeIndex(pd.to_datetime(text, utc=True), name="Datetime")
    except (ValueError, TypeError) as exc:
        raise ArchiveError(f"{path}: unparseable stamps ({exc})") from exc


def load_bars(bars_dir, ticker: str) -> pd.DataFrame | None:
    """Regular-session 5-minute bars of ``ticker``, UTC bar starts, sorted.
    None when the file is missing; ArchiveError when it cannot be trusted."""
    path = Path(bars_dir) / f"{safe_symbol(ticker)}.csv"
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0)
    except (OSError, ValueError) as exc:
        raise ArchiveError(f"{path}: unreadable ({exc})") from exc
    missing = [c for c in COLUMNS if c not in frame.columns]
    if missing:
        raise ArchiveError(f"{path}: missing columns {missing}")
    frame = frame[list(COLUMNS)].apply(pd.to_numeric, errors="coerce").astype(float)
    frame.index = _parse_index(frame.index, path)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[_regular_mask(frame.index)]


def _last_stamp(path: Path) -> pd.Timestamp | None:
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 4096))
        lines = [ln for ln in fh.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return to_utc(lines[-1].split(",", 1)[0])
    except ValueError:
        return None


def archive_last_bar(bars_dir) -> str | None:
    """ISO UTC of the latest last bar over every archive file, or None."""
    root = Path(bars_dir)
    if not root.is_dir():
        return None
    stamps = [s for s in (_last_stamp(p) for p in sorted(root.glob("*.csv"))) if s is not None]
    return max(stamps).isoformat() if stamps else None
