"""v162 Alpaca history store -- the read seam.

data/market_data/{15min,hourly,daily}/{SAFE}.csv is the THIRD OHLCV store,
next to data/backtest_cache/ and the root market_data/ cache
(docs/claude/known-traps.md). Only scripts/data/fetch_alpaca_history.py writes
it; training reads it through this module and nothing else. No network, no
write path, and no directory is ever created here.

Index convention (spec §1): intraday files hold naive America/New_York
wall-clock times labelled at the bar start (column `Datetime`); daily files
hold naive dates (column `Date`). 15min stores every session (04:00-20:00 ET);
`load(..., session="rth")` keeps the regular-hours bars.
"""
import json
import os
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.marketdata.data_store import safe_symbol

TIMEFRAMES = ("15min", "hourly", "daily")
INDEX_NAMES = {"15min": "Datetime", "hourly": "Datetime", "daily": "Date"}
SESSIONS = ("rth", "all")
MANIFEST_NAME = "_manifest.json"
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
ENV_VAR = "HISTORY_STORE_DIR"
RTH_FIRST_MINUTE = 9 * 60 + 30        # 09:30, first regular-hours 15min bar
RTH_LAST_15MIN_MINUTE = 15 * 60 + 45  # 15:45, last regular-hours 15min bar


class MissingStoreError(RuntimeError):
    """The history store, or one of its manifests, is absent. An alpaca
    training run stops on it rather than run with zero tickers."""


def store_root() -> Path:
    """HISTORY_STORE_DIR when set (read on every call; relative values resolve
    against the project root), else <config.DATA_DIR>/market_data."""
    override = os.environ.get(ENV_VAR, "").strip()
    if not override:
        return Path(config.DATA_DIR) / "market_data"
    path = Path(override)
    return path if path.is_absolute() else Path(config.DATA_DIR).parent / path


def timeframe_dir(timeframe: str) -> Path:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown history store timeframe {timeframe!r}; expected one of {TIMEFRAMES}")
    return store_root() / timeframe


def file_path(ticker: str, timeframe: str) -> Path:
    return timeframe_dir(timeframe) / f"{safe_symbol(ticker)}.csv"


def manifest_path(timeframe: str) -> Path:
    return timeframe_dir(timeframe) / MANIFEST_NAME


def manifest(timeframe: str) -> dict | None:
    """The timeframe's manifest, or None when the file is absent. A corrupt
    manifest raises: it is never mistaken for an empty store."""
    path = manifest_path(timeframe)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def require_manifest(timeframe: str) -> dict:
    found = manifest(timeframe)
    if found is None:
        raise MissingStoreError(
            f"history store manifest missing: {manifest_path(timeframe)} -- backfill it with "
            f"scripts/data/fetch_alpaca_history.py, pull it with scripts/ops/pull_history_store.sh, "
            f"or set TRAINING_DATA_SOURCE=yfinance")
    return found


def ticker_status(timeframe: str, ticker: str) -> str:
    """The ticker's manifest status (`ok`, `skipped: ...`, `flagged: ...`), or
    "missing" when there is no manifest, no entry or no status."""
    entry = ((manifest(timeframe) or {}).get("tickers") or {}).get(ticker.upper().strip())
    return (entry or {}).get("status") or "missing"


def load(ticker: str, timeframe: str, session: str = "rth") -> pd.DataFrame | None:
    """One ticker's bars from the store, or None when the file is missing or
    the result is empty. `session` filters 15min only: "rth" keeps the bars
    starting 09:30-15:45, "all" keeps every stored bar."""
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}; expected one of {SESSIONS}")
    path = file_path(ticker, timeframe)
    if not path.is_file():
        return None
    frame = _read(path, timeframe)
    if timeframe == "15min" and session == "rth":
        frame = _regular_hours(frame)
    return frame if len(frame) else None


def _read(path: Path, timeframe: str) -> pd.DataFrame:
    raw = pd.read_csv(path, index_col=0)
    index = pd.DatetimeIndex(pd.to_datetime(raw.index))
    if index.tz is not None:
        raise ValueError(f"{path}: tz-aware index; the history store holds naive "
                         f"New York wall-clock times")
    out = raw[OHLCV_COLUMNS].astype("float64")
    out.index = index
    out.index.name = INDEX_NAMES[timeframe]
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def _regular_hours(frame: pd.DataFrame) -> pd.DataFrame:
    minute = frame.index.hour * 60 + frame.index.minute
    return frame[(minute >= RTH_FIRST_MINUTE) & (minute <= RTH_LAST_15MIN_MINUTE)]
