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

v190: data/market_data_pit/ is the FOURTH OHLCV directory, same layout, read with
`store="pit"`. Both default roots fall back to the main checkout's from a worktree.
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
WATCHLIST = "watchlist"
PIT = "pit"
WATCHLIST_DIRNAME = "market_data"
PIT_DIRNAME = "market_data_pit"
STORES = (WATCHLIST, PIT)
RTH_FIRST_MINUTE = 9 * 60 + 30        # 09:30, first regular-hours 15min bar
RTH_LAST_15MIN_MINUTE = 15 * 60 + 45  # 15:45, last regular-hours 15min bar


class MissingStoreError(RuntimeError):
    """The history store, or one of its manifests, is absent. An alpaca
    training run stops on it rather than run with zero tickers."""


def store_key(store: str | None) -> str:
    """Normalise a store name: None -> "watchlist"; anything unknown raises."""
    key = WATCHLIST if store is None else store
    if key not in STORES:
        raise ValueError(f"unknown history store {store!r}; expected one of {STORES}")
    return key


def _main_checkout(data_dir: Path) -> Path | None:
    """The main checkout when data_dir lies inside <main>/.claude/worktrees/<x>/
    (plain parts scan; no resolve(), no filesystem access), else None."""
    parts = data_dir.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return Path(*parts[:i]) if i else None
    return None


def resolve_data_root(name: str) -> Path:
    """<DATA_DIR>/<name> when it exists; from a worktree that lacks it, the main
    checkout's data/<name> when that exists; else the local path (so a missing
    store's error names where this checkout looked)."""
    data_dir = Path(config.DATA_DIR)
    local = data_dir / name
    if local.is_dir():
        return local
    main = _main_checkout(data_dir)
    if main is not None and (main / "data" / name).is_dir():
        return main / "data" / name
    return local


def store_root(store: str | None = None) -> Path:
    """The watchlist store: HISTORY_STORE_DIR when set (read on every call;
    relative values resolve against the project root; no worktree fallback for an
    explicit override), else data/market_data. The PIT store (store="pit") is
    data/market_data_pit, chosen by instrument v3 -- no environment variable, and
    HISTORY_STORE_DIR never redirects it. Both defaults fall back to the main
    checkout's directory from a worktree."""
    if store_key(store) == PIT:
        return resolve_data_root(PIT_DIRNAME)
    override = os.environ.get(ENV_VAR, "").strip()
    if not override:
        return resolve_data_root(WATCHLIST_DIRNAME)
    path = Path(override)
    return path if path.is_absolute() else Path(config.DATA_DIR).parent / path


def timeframe_dir(timeframe: str, *, store: str | None = None) -> Path:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown history store timeframe {timeframe!r}; expected one of {TIMEFRAMES}")
    return store_root(store) / timeframe


def file_path(ticker: str, timeframe: str, *, store: str | None = None) -> Path:
    return timeframe_dir(timeframe, store=store) / f"{safe_symbol(ticker)}.csv"


def manifest_path(timeframe: str, *, store: str | None = None) -> Path:
    return timeframe_dir(timeframe, store=store) / MANIFEST_NAME


def manifest(timeframe: str, *, store: str | None = None) -> dict | None:
    """The timeframe's manifest, or None when the file is absent. A corrupt
    manifest raises: it is never mistaken for an empty store."""
    path = manifest_path(timeframe, store=store)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _missing_store_hint(store: str | None) -> str:
    if store_key(store) == PIT:
        return ("backfill it with scripts/data/fetch_alpaca_history.py --universe sp500_pit "
                "--root data/market_data_pit (one fetcher per root)")
    return ("backfill it with scripts/data/fetch_alpaca_history.py, pull it with "
            "scripts/ops/pull_history_store.sh, or set TRAINING_DATA_SOURCE=yfinance")


def require_manifest(timeframe: str, *, store: str | None = None) -> dict:
    found = manifest(timeframe, store=store)
    if found is None:
        raise MissingStoreError(
            f"history store manifest missing: {manifest_path(timeframe, store=store)} -- "
            f"{_missing_store_hint(store)}")
    return found


def ticker_status(timeframe: str, ticker: str) -> str:
    """The ticker's manifest status (`ok`, `skipped: ...`, `flagged: ...`), or
    "missing" when there is no manifest, no entry or no status."""
    entry = ((manifest(timeframe) or {}).get("tickers") or {}).get(ticker.upper().strip())
    return (entry or {}).get("status") or "missing"


def load(ticker: str, timeframe: str, session: str = "rth", *,
         store: str | None = None) -> pd.DataFrame | None:
    """One ticker's bars from the store, or None when the file is missing or
    the result is empty. `session` filters 15min only: "rth" keeps the bars
    starting 09:30-15:45, "all" keeps every stored bar. A PIT frame is returned
    already trimmed to its integrity report's window; an empty trim result is
    None like an empty file."""
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}; expected one of {SESSIONS}")
    path = file_path(ticker, timeframe, store=store)
    if not path.is_file():
        return None
    frame = _read(path, timeframe)
    if timeframe == "15min" and session == "rth":
        frame = _regular_hours(frame)
    if store_key(store) == PIT:
        frame = _pit_trim(frame, ticker)
    return frame if frame is not None and len(frame) else None


def _pit_trim(frame: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """The integrity report's trim window for one PIT ticker (spec section 2.3)."""
    from swingbot.core.marketdata import pit_integrity
    root = store_root(PIT)
    integrity = pit_integrity.cached_integrity(root)
    if integrity is None:
        raise MissingStoreError(
            f"PIT store has no integrity report: {pit_integrity.integrity_path(root)} -- "
            f"build it with scripts/data/check_history_store.py --pit before any run reads it")
    return pit_integrity.apply_trim(frame, integrity.trim_window(ticker))


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
