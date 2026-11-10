"""v204 snapshot bars: the yfinance-basis daily file, read-only by construction.

Admin snapshots read daily bars from `market_data/daily/<safe_symbol>.csv`
(the file and loader `daily_delta.read_daily(T, basis=BASIS_YF)` uses) and
nothing else. This module never calls the providers, `data.get_daily_data*`,
`data_refresh`, `freshness._daily_for` or the `backtest_cache`, and never
creates a directory or writes a file.

Loud failure, never a silent gap: an absent cache directory (an unmounted
volume) raises `DailyCacheUnavailable`; a symbol that is not on disk, empty,
unreadable or shorter than the caller's `min_rows` is listed in `missing`
with its reason, never returned as if it were whole. See `known-traps.md`
§ The market_data cache never self-heals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

PERIOD_DAYS = {"6mo": 183, "1y": 366, "2y": 731, "5y": 1827}   # moved from freshness._PERIOD_DAYS


class DailyCacheUnavailable(RuntimeError):
    """The daily bar cache directory is absent (an unmounted volume)."""


@dataclass(frozen=True)
class ReadOnlyBars:
    frames: dict
    missing: dict
    fingerprints: dict


def trim(df, period: str):
    days = PERIOD_DAYS.get(period)
    if days is None or df is None or not len(df):
        return df
    return df[df.index >= df.index[-1] - timedelta(days=days)]


def _daily_dir() -> str:
    """The daily cache directory, read at call time; raises when it is absent."""
    from swingbot.core.marketdata import data_store
    d = os.path.join(data_store.DATA_DIR, data_store.timeframe_name("daily"))
    if not os.path.isdir(d):
        raise DailyCacheUnavailable(f"daily bar cache {os.path.abspath(d)} is not mounted")
    return d


def _fingerprint(path: str, df) -> dict:
    return {"path": os.path.abspath(path), "mtime": os.path.getmtime(path),
            "last_bar": df.index[-1].strftime("%Y-%m-%d"), "rows": len(df)}


def _read_one(symbol: str, daily_dir: str, period: str, min_rows: int) -> tuple:
    """(frame, reason, fingerprint) for one symbol; exactly one of frame/reason is set."""
    from swingbot.core.marketdata import data_store, spot_metals
    if spot_metals.is_spot_metal(symbol):
        return None, "spot_metal", None
    path = os.path.join(daily_dir, f"{data_store.safe_symbol(symbol)}.csv")
    if not os.path.isfile(path):
        return None, "no_file", None
    if os.path.getsize(path) == 0:
        return None, "empty", None
    df = data_store.load_normalized_file(path, label=f"{symbol}/yfinance-auto_adjust")
    if df is None:
        return None, "unreadable", None
    fingerprint = _fingerprint(path, df)
    kept = trim(df, period)
    if len(kept) < min_rows:
        return None, f"short:{len(kept)}/{min_rows}", fingerprint
    return kept, None, fingerprint


def _unique(tickers) -> list:
    out: list = []
    for t in tickers:
        name = str(t).upper().strip()
        if name not in out:
            out.append(name)
    return out


def read_cached_daily(tickers, *, period: str = "2y", min_rows: int = 1) -> ReadOnlyBars:
    """Each ticker's cached yfinance-basis daily frame, trimmed to `period`."""
    daily_dir = _daily_dir()
    frames: dict = {}
    missing: dict = {}
    fingerprints: dict = {}
    for symbol in _unique(tickers):
        df, reason, fingerprint = _read_one(symbol, daily_dir, period, min_rows)
        if fingerprint is not None:
            fingerprints[symbol] = fingerprint
        if reason is not None:
            missing[symbol] = reason
        else:
            frames[symbol] = df
    return ReadOnlyBars(frames=frames, missing=missing, fingerprints=fingerprints)


class RecordingReader:
    """A `bars_reader` that remembers every frame, gap and fingerprint it served."""

    def __init__(self, *, period: str = "2y", min_rows: int = 1):
        self.period = period
        self.min_rows = min_rows
        self._frames, self._missing, self._fingerprints = {}, {}, {}

    def __call__(self, symbols) -> dict[str, "pd.DataFrame"]:
        got = read_cached_daily(symbols, period=self.period, min_rows=self.min_rows)
        self._frames.update(got.frames)
        self._missing.update(got.missing)
        self._fingerprints.update(got.fingerprints)
        return got.frames

    @property
    def seen(self) -> ReadOnlyBars:
        return ReadOnlyBars(frames=dict(self._frames), missing=dict(self._missing),
                            fingerprints=dict(self._fingerprints))
