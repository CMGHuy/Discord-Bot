"""v162 training-data switch: which daily bars backtests, grids and the admin
Tuning page train on.

`alpaca` reads the history store (data/market_data/daily/, through
history_store); `yfinance` reads the legacy data/backtest_cache/ exactly as
scripts/data/fetch_backtest_data.load_cached always did. The default is
config.TRAINING_DATA_SOURCE, except that a set BACKTEST_CACHE_DIR (an explicit
yfinance-shaped cache: the ext-cache screens, the §5 snapshot legs) means
yfinance. A script's --data-source names the source outright.

One selection per process, and a run never mixes sources: there is no
per-ticker fallback. `alpaca` with no daily manifest raises
history_store.MissingStoreError on first use -- never a zero-ticker run. A
ticker the manifest marks skipped/flagged, or whose file is missing or empty,
is left out and recorded with its reason (excluded(), provenance()).

Training only: the live scan, data_refresh and backtest_cache.ensure_cached
never import this module.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.marketdata import backtest_cache, history_store

log = logging.getLogger(__name__)

DATA_SOURCES = ("alpaca", "yfinance")
PROVENANCE_SUFFIX = ".provenance.json"
NO_FILE = "no file"
EMPTY_FILE = "empty file"
NOT_IN_STORE = "not in store"


@dataclass
class _Selection:
    source: str
    manifest: dict | None = None
    excluded: dict[str, str] = field(default_factory=dict)


_SELECTION: _Selection | None = None


def reset() -> None:
    """Forget the selection; the next use selects the default again."""
    global _SELECTION
    _SELECTION = None


def _default_source() -> str:
    if os.environ.get("BACKTEST_CACHE_DIR", "").strip():
        return "yfinance"
    return str(config.TRAINING_DATA_SOURCE)


def _manifest_exclusions(manifest: dict) -> dict[str, str]:
    """Every manifest ticker that cannot be trained on, with its reason."""
    out: dict[str, str] = {}
    for ticker, entry in (manifest.get("tickers") or {}).items():
        status = (entry or {}).get("status") or "missing"
        if status != "ok":
            out[ticker] = status
        elif not history_store.file_path(ticker, "daily").is_file():
            out[ticker] = NO_FILE
    return out


def select(name: str | None = None) -> str:
    """Select the training source for this process and return it."""
    global _SELECTION
    _SELECTION = None
    source = (name or _default_source()).strip().lower()
    if source not in DATA_SOURCES:
        raise ValueError(f"unknown training data source {source!r}; expected one of {DATA_SOURCES}")
    if source == "yfinance":
        _SELECTION = _Selection("yfinance")
        return source
    manifest = history_store.require_manifest("daily")
    _SELECTION = _Selection("alpaca", manifest, _manifest_exclusions(manifest))
    log.info("training data: alpaca store %s, %d ticker(s) excluded",
             history_store.store_root(), len(_SELECTION.excluded))
    return source


def _selection() -> _Selection:
    if _SELECTION is None:
        select(None)
    return _SELECTION


def active() -> str:
    return _selection().source


def _load_yfinance(ticker: str) -> pd.DataFrame | None:
    """The pre-v162 fetch_backtest_data.load_cached, unchanged."""
    p = backtest_cache.cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def _exclude(sel: _Selection, ticker: str, reason: str) -> None:
    if ticker not in sel.excluded:
        log.info("training data: excluded %s (%s)", ticker, reason)
    sel.excluded[ticker] = reason
    return None


def _load_alpaca(sel: _Selection, ticker: str) -> pd.DataFrame | None:
    if ticker in sel.excluded:
        return None
    if ticker not in (sel.manifest.get("tickers") or {}):
        return _exclude(sel, ticker, NOT_IN_STORE)
    frame = history_store.load(ticker, "daily")
    if frame is None:
        exists = history_store.file_path(ticker, "daily").is_file()
        return _exclude(sel, ticker, EMPTY_FILE if exists else NO_FILE)
    return frame


def load_daily(ticker: str) -> pd.DataFrame | None:
    """Daily bars (Date index, Open..Volume) from the selected source, or None."""
    sel = _selection()
    if sel.source == "yfinance":
        return _load_yfinance(ticker)
    return _load_alpaca(sel, ticker.upper().strip())


def available_tickers() -> list[str]:
    """Tickers the selected source can serve: the manifest's trainable tickers,
    or the file stems of the yfinance cache (safe names, as a glob gives them)."""
    sel = _selection()
    if sel.source == "yfinance":
        folder = backtest_cache.CACHE_DIR
        return sorted(p.stem for p in folder.glob("*.csv")) if folder.is_dir() else []
    return sorted(t for t in (sel.manifest.get("tickers") or {}) if t not in sel.excluded)


def excluded() -> dict[str, str]:
    return dict(sorted(_selection().excluded.items()))


def exclusion_lines() -> list[str]:
    return [f"excluded {ticker}: {reason}" for ticker, reason in excluded().items()]


def provenance() -> dict:
    """What a result was trained on: written next to every --json output."""
    sel = _selection()
    if sel.source == "yfinance":
        return {"data_source": "yfinance", "feed": "yfinance", "adjustment": "auto_adjust",
                "manifest_hash": None, "store_dir": str(backtest_cache.CACHE_DIR), "excluded": {}}
    return {"data_source": "alpaca", "feed": sel.manifest.get("feed"),
            "adjustment": sel.manifest.get("adjustment"), "manifest_hash": sel.manifest.get("hash"),
            "store_dir": str(history_store.store_root()), "excluded": excluded()}


def provenance_path(out_path: str | Path) -> Path:
    """The sidecar of a --json output: '<out>.provenance.json'."""
    return Path(str(out_path) + PROVENANCE_SUFFIX)


def write_provenance(out_path: str | Path) -> Path:
    path = provenance_path(out_path)
    path.write_text(json.dumps(provenance(), indent=1, sort_keys=True), encoding="utf-8")
    return path
