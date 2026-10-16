"""v165 D4 -- price sparklines for the calendar day page.

Spec: docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md (D4).

Pure: bars arrive through an injected `loader(ticker) -> frame | None`. The
admin route passes `data_store.load_normalized(ticker, "daily")` -- the
process-cached `market_data/` reader -- and nothing else. This module never
fetches, never reads `backtest_cache`, never calls `load_from_disk`
(known-traps: two OHLCV caches).

**No lookahead on a historical card:** the window ends 3 bars after the exit
bar, never at "today". Those 3 bars are context the page draws dimmed; the
response marks where the exit is (`exit_bar`).
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

import numpy as np
import pandas as pd

from swingbot.core.marketdata import spot_metals

SPARK_MAX_ROWS = 50
SPARK_MAX_BARS = 400
SPARK_PAD_BARS = 3

#: series field -> calendar row field. Order is the response's key order.
_TICKS = (("entry", "entry_price"), ("stop", "stop_price"), ("tp1", "tp1"),
          ("tp2", "tp2"), ("exit", "exit_price"))


def series_key(row: dict) -> str:
    """`"<trade_id>:<leg_index>"` -- one key per calendar row, legs apart."""
    return f"{row['trade_id']}:{row['leg_index']}"


def _utc_date(stamp: str | None) -> str | None:
    """`YYYY-MM-DD` of an ISO stamp in UTC; a naive stamp is read as UTC."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).date().isoformat()


def _bounds(index: pd.DatetimeIndex, opened: str, day: str) -> tuple[int, int] | None:
    """(entry_i, exit_i): first bar on/after `opened`, last bar on/before `day`.

    Bars are keyed by exchange date (the frame's tz-naive daily index,
    normalised so a stray time-of-day cannot push a bar past its date)."""
    days = index.normalize()
    entry_i = int(days.searchsorted(pd.Timestamp(opened), side="left"))
    exit_i = int(days.searchsorted(pd.Timestamp(day), side="right")) - 1
    if entry_i >= len(days) or exit_i < entry_i:
        return None
    return entry_i, exit_i


def _ticks(row: dict, window: pd.DataFrame) -> dict:
    """The recorded prices, or all None when entry no longer sits on the bars
    (a split or adjustment since entry) -- then only the close line draws."""
    entry = row.get("entry_price")
    low, high = float(window["Low"].min()), float(window["High"].max())
    if entry is None or not low <= float(entry) <= high:
        return {name: None for name, _ in _TICKS}
    return {name: row.get(field) for name, field in _TICKS}


def _finite_closes(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """The frame without bars whose Close is NaN/inf -- they would serialise
    as bare NaN, which JSON.parse rejects for the whole response. Dropped
    before any bar index is computed so entry, exit, the 400-bar cut and
    `last_bar` all agree; each bar is judged by its own Close only."""
    if frame is None:
        return None
    close = pd.to_numeric(frame["Close"], errors="coerce").to_numpy(dtype=float)
    return frame[np.isfinite(close)]


def series_for(row: dict, frame: pd.DataFrame | None) -> tuple[dict | None, bool]:
    """One row's series and whether the 400-bar cap cut it."""
    opened, day = _utc_date(row.get("opened_at")), row.get("day")
    frame = _finite_closes(frame)
    if frame is None or frame.empty or opened is None or not day:
        return None, False
    bounds = _bounds(frame.index, opened, day)
    if bounds is None:
        return None, False
    entry_i, exit_i = bounds
    start = max(0, entry_i - SPARK_PAD_BARS)
    stop = min(len(frame), exit_i + SPARK_PAD_BARS + 1)
    cut = stop - start > SPARK_MAX_BARS
    if cut:
        start = stop - SPARK_MAX_BARS
    window = frame.iloc[start:stop]
    dates = list(window.index.strftime("%Y-%m-%d"))
    last_bar = frame.index[-1].strftime("%Y-%m-%d")
    return {
        "closes": [{"date": d, "close": round(float(c), 4)}
                   for d, c in zip(dates, window["Close"])],
        "exit_bar": exit_i - start,
        "last_bar": last_bar,
        "stale": last_bar < day,
        **_ticks(row, window),
        "exit_date": dates[exit_i - start],
    }, cut


def _series_or_none(row: dict, loader: Callable[[str], pd.DataFrame | None]) -> tuple[dict | None, bool]:
    ticker = (row.get("ticker") or "").strip()
    # Spot metals are never cached under their own name (v109): decided by
    # the shared helper, before any load.
    if not ticker or spot_metals.is_spot_metal(ticker):
        return None, False
    return series_for(row, loader(ticker))


def sparklines_payload(
    day_rows: list[dict], loader: Callable[[str], pd.DataFrame | None],
) -> tuple[dict[str, dict | None], bool]:
    """`({series_key: series | None}, truncated)` for one day's rows.

    Deterministic caps: rows in `closed_at` order, the first 50 kept; a
    window over 400 bars keeps its last 400. Either cut sets `truncated`."""
    ordered = sorted(day_rows, key=lambda r: r.get("closed_at") or "")
    truncated = len(ordered) > SPARK_MAX_ROWS
    series: dict[str, dict | None] = {}
    for row in ordered[:SPARK_MAX_ROWS]:
        value, cut = _series_or_none(row, loader)
        series[series_key(row)] = value
        truncated = truncated or cut
    return series, truncated
