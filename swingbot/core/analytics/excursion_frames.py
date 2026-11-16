"""v228: one ticker's archived bars for compute_excursion, finest first.

Reads market_data/{5min,15min,hourly}/<SYMBOL>.csv through
data_store.load_normalized (naive-UTC bar starts, pinned by
tests/marketdata/test_archive_time_basis.py) and tells a file that does not
exist (`missing`) from one that cannot be used (`unreadable`, e.g. mixed UTC
offsets), so the upgrade report never counts either as "no coverage".
Never creates a folder (data_store.cache_path would)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from swingbot.core.analytics.mfe_mae import INTRADAY_SOURCES
from swingbot.core.marketdata.data_store import DATA_DIR, load_normalized, safe_symbol


@dataclass(frozen=True)
class FrameSet:
    frames: dict[str, pd.DataFrame]
    missing: tuple[str, ...]
    unreadable: tuple[str, ...]


def _read(ticker: str, name: str, base_dir: str) -> tuple[str, pd.DataFrame | None]:
    if not ticker or not os.path.isfile(os.path.join(base_dir, name, f"{safe_symbol(ticker)}.csv")):
        return "missing", None
    df = load_normalized(ticker, name, base_dir=base_dir)
    return ("unreadable", None) if df is None else ("ok", df)


def load_frames(ticker: str, *, daily: pd.DataFrame | None = None,
                daily_from_archive: bool = False, base_dir: str = DATA_DIR) -> FrameSet:
    """Intraday archives in INTRADAY_SOURCES order, then the daily frame:
    the one passed in when it holds bars, else (daily_from_archive) the
    market_data/daily archive."""
    has_daily = daily is not None and not daily.empty
    names = INTRADAY_SOURCES + (("daily",) if daily_from_archive and not has_daily else ())
    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    unreadable: list[str] = []
    for name in names:
        state, df = _read(ticker, name, base_dir)
        if state == "ok":
            frames[name] = df
        else:
            (missing if state == "missing" else unreadable).append(name)
    if has_daily:
        frames["daily"] = daily
    return FrameSet(frames, tuple(missing), tuple(unreadable))
