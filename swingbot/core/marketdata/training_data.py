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

v190: the point-in-time Alpaca store (data/market_data_pit/) is selected only
by select(..., store="pit"), which instrument v3 calls through
fetch_backtest_data.apply_data_source; it is never the default. It admits
`flagged: no-reference` (a delisted member with no reference to check against),
refuses to select without -- or with a stale -- _integrity.json, and every frame
it returns (daily, intraday, context) is trimmed and cut at `until`.

Training only: the live scan, data_refresh and backtest_cache.ensure_cached
never import this module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.marketdata import backtest_cache, history_store, pit_integrity

log = logging.getLogger(__name__)

DATA_SOURCES = ("alpaca", "yfinance")
PROVENANCE_SUFFIX = ".provenance.json"
NO_FILE = "no file"
EMPTY_FILE = "empty file"
NOT_IN_STORE = "not in store"
TRIMMED_EMPTY = "empty after integrity trim"
NO_BARS_BY_UNTIL = "no bars on or before the cut"
#: Manifest statuses the PIT store trains on (identity.OK, identity.NO_REFERENCE).
PIT_ADMITTED = ("ok", "flagged: no-reference")


class StaleIntegrityError(history_store.MissingStoreError):
    """The PIT daily manifest changed after its integrity report was frozen."""


@dataclass
class _Selection:
    source: str
    manifest: dict | None = None
    excluded: dict[str, str] = field(default_factory=dict)
    store: str = history_store.WATCHLIST
    until: str | None = None
    integrity: pit_integrity.Integrity | None = None


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


def _pit_exclusions(manifest: dict, integrity: pit_integrity.Integrity, *,
                    store: str) -> dict[str, str]:
    """Every PIT manifest ticker that cannot be trained on, with its reason:
    a status outside PIT_ADMITTED, an integrity refusal, or a missing file."""
    out: dict[str, str] = {}
    for ticker, entry in (manifest.get("tickers") or {}).items():
        status = (entry or {}).get("status") or "missing"
        if status not in PIT_ADMITTED:
            out[ticker] = status
            continue
        refusal = integrity.exclusion(ticker)
        if refusal is not None:
            out[ticker] = f"integrity: {refusal}"
        elif not history_store.file_path(ticker, "daily", store=store).is_file():
            out[ticker] = NO_FILE
    return out


def _check_store_args(source: str, key: str, until: str | None) -> None:
    if key == history_store.PIT and source != "alpaca":
        raise ValueError(f"the PIT store holds Alpaca bars; source {source!r} cannot read it")
    if until is not None and key != history_store.PIT:
        raise ValueError("until cuts the PIT store only")


def _require_fresh(integrity: pit_integrity.Integrity) -> None:
    path = history_store.manifest_path("daily", store=history_store.PIT)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = integrity.manifest_sha256("daily")
    if frozen != actual:
        raise StaleIntegrityError(
            f"report {str(frozen)[:12]} vs manifest {actual[:12]}: the PIT store's daily "
            f"manifest changed after its integrity report was frozen -- re-run "
            f"scripts/data/check_history_store.py --pit (never --mode update between the "
            f"freeze and a run)")


def _select_watchlist() -> _Selection:
    manifest = history_store.require_manifest("daily")
    return _Selection("alpaca", manifest, _manifest_exclusions(manifest))


def _select_pit(until: str | None) -> _Selection:
    manifest = history_store.require_manifest("daily", store=history_store.PIT)
    root = history_store.store_root(history_store.PIT)
    integrity = pit_integrity.load_integrity(root)
    if integrity is None:
        raise history_store.MissingStoreError(
            f"PIT store has no integrity report: {pit_integrity.integrity_path(root)} -- "
            f"build it with scripts/data/check_history_store.py --pit")
    _require_fresh(integrity)
    return _Selection("alpaca", manifest,
                      _pit_exclusions(manifest, integrity, store=history_store.PIT),
                      history_store.PIT, until, integrity)


def select(name: str | None = None, store: str | None = None,
           until: str | None = None) -> str:
    """Select the training source (and, for alpaca, the history store and the
    PIT cut) for this process and return the source. Positional, so a pool
    initializer can pass selection_args() whole."""
    global _SELECTION
    _SELECTION = None
    source = (name or _default_source()).strip().lower()
    if source not in DATA_SOURCES:
        raise ValueError(f"unknown training data source {source!r}; expected one of {DATA_SOURCES}")
    key = history_store.store_key(store)
    _check_store_args(source, key, until)
    if source == "yfinance":
        _SELECTION = _Selection("yfinance")
        return source
    _SELECTION = _select_pit(until) if key == history_store.PIT else _select_watchlist()
    log.info("training data: alpaca store %s, %d ticker(s) excluded",
             history_store.store_root(key), len(_SELECTION.excluded))
    return source


def _selection() -> _Selection:
    if _SELECTION is None:
        select(None)
    return _SELECTION


def active() -> str:
    return _selection().source


def active_store() -> str:
    """"watchlist" or "pit" ("watchlist" for a yfinance selection too)."""
    return _selection().store


def selection_args() -> tuple:
    """What a pool worker passes to select() to land on this selection."""
    sel = _selection()
    if sel.store == history_store.PIT:
        return ("alpaca", history_store.PIT, sel.until)
    return (sel.source,)


def signal_cuts() -> dict[str, list[tuple[str, str]]] | None:
    """None unless the PIT store; else every admitted ticker's signal cuts."""
    sel = _selection()
    if sel.store != history_store.PIT:
        return None
    return {ticker: sel.integrity.signal_cuts(ticker)
            for ticker in sorted(sel.manifest.get("tickers") or {})
            if ticker not in sel.excluded}


def _cut(frame: pd.DataFrame | None, until: str | None) -> pd.DataFrame | None:
    """Bars dated on or before `until` (any timeframe); None when none remain."""
    if frame is None or until is None:
        return frame
    out = frame[frame.index < pd.Timestamp(until) + pd.Timedelta(days=1)]
    return out if len(out) else None


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
    frame = history_store.load(ticker, "daily", store=sel.store)
    if frame is None:
        return _exclude(sel, ticker, _missing_reason(sel, ticker))
    cut = _cut(frame, sel.until)
    if cut is None:
        return _exclude(sel, ticker, NO_BARS_BY_UNTIL)
    return cut


def _missing_reason(sel: _Selection, ticker: str) -> str:
    if not history_store.file_path(ticker, "daily", store=sel.store).is_file():
        return NO_FILE
    if sel.integrity is not None and sel.integrity.trim_window(ticker) != (None, None):
        return TRIMMED_EMPTY
    return EMPTY_FILE


def load_daily(ticker: str) -> pd.DataFrame | None:
    """Daily bars (Date index, Open..Volume) from the selected source, or None."""
    sel = _selection()
    if sel.source == "yfinance":
        return _load_yfinance(ticker)
    return _load_alpaca(sel, ticker.upper().strip())


def load_intraday(ticker: str, timeframe: str, session: str = "rth") -> pd.DataFrame | None:
    """Intraday bars from the selected alpaca store. The watchlist store is
    today's direct history_store.load; the PIT store serves only tickers its
    daily manifest admits, trimmed and cut at `until`."""
    sel = _selection()
    if sel.store != history_store.PIT:
        return history_store.load(ticker, timeframe, session)
    key = ticker.upper().strip()
    if key in sel.excluded or key not in (sel.manifest.get("tickers") or {}):
        return None
    return _cut(history_store.load(key, timeframe, session, store=sel.store), sel.until)


#: v211: context-only files the idea screen keeps beside the ticker CSVs of a
#: yfinance cache dir. Mirrors screen.context.CONTEXT_ONLY_STEMS (a test pins
#: them equal); marketdata may not import the screen (test_import_guard.py).
_CONTEXT_ONLY_STEMS = frozenset({"BREADTH_ATR1", "^VIX"})


def available_tickers() -> list[str]:
    """Tickers the selected source can serve: the manifest's trainable tickers,
    or the file stems of the yfinance cache (safe names, as a glob gives them)."""
    sel = _selection()
    if sel.source == "yfinance":
        folder = backtest_cache.CACHE_DIR
        return sorted(p.stem for p in folder.glob("*.csv") if p.stem not in _CONTEXT_ONLY_STEMS) if folder.is_dir() else []
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
    return _alpaca_provenance(sel)


def _alpaca_provenance(sel: _Selection) -> dict:
    out = {"data_source": "alpaca", "feed": sel.manifest.get("feed"),
           "adjustment": sel.manifest.get("adjustment"), "manifest_hash": sel.manifest.get("hash"),
           "store": sel.store, "store_dir": str(history_store.store_root(sel.store)),
           "excluded": excluded()}
    if sel.store == history_store.PIT:
        out["integrity_sha256"] = sel.integrity.sha256
    return out


def provenance_path(out_path: str | Path) -> Path:
    """The sidecar of a --json output: '<out>.provenance.json'."""
    return Path(str(out_path) + PROVENANCE_SUFFIX)


def write_provenance(out_path: str | Path) -> Path:
    path = provenance_path(out_path)
    path.write_text(json.dumps(provenance(), indent=1, sort_keys=True), encoding="utf-8")
    return path
