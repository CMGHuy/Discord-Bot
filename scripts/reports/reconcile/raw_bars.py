"""v232: unadjusted daily bars for layer 1, in two scratch history stores.

Live fills are real quotes; the v162 store's bars are split- and dividend-
adjusted (Adjustment.ALL). Layer 1 walks RAW bars. The SPLIT-adjusted copy
exists only to find a split inside the window: split.Close / raw.Close is
constant unless a split falls inside the bars compared (a split after the
window, before the fetch, shifts every bar alike and is usable).

Layout: <root>/<kind>/daily/<SAFE>.csv and <root>/<kind>/daily/_manifest.json
for kind in KINDS, read back with history_store.load(ticker, "daily") while
HISTORY_STORE_DIR points at <root>/<kind> (use_store). The adjusted watchlist
store is never written or read here.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment

from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.data_store import safe_symbol

KINDS = ("raw", "split")
ADJUSTMENTS = {"raw": Adjustment.RAW, "split": Adjustment.SPLIT}
OK, EMPTY = "ok", "empty"


def store_dir(root: Path, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown bar kind {kind!r}; expected one of {KINDS}")
    return Path(root) / kind


@contextlib.contextmanager
def use_store(path: Path):
    """Point history_store at one scratch store; restore the previous override."""
    previous = os.environ.get(history_store.ENV_VAR)
    os.environ[history_store.ENV_VAR] = str(Path(path).resolve())
    try:
        yield Path(path)
    finally:
        if previous is None:
            os.environ.pop(history_store.ENV_VAR, None)
        else:
            os.environ[history_store.ENV_VAR] = previous


def _daily_dir(store: Path) -> Path:
    return Path(store) / "daily"


def write_frame(store: Path, ticker: str, frame: pd.DataFrame) -> str:
    """One ticker's daily bars as the store's CSV (naive Date index); its SHA-256."""
    out = frame[history_store.OHLCV_COLUMNS].astype("float64")
    index = pd.DatetimeIndex(out.index)
    if index.tz is not None:
        raise ValueError(f"{ticker}: tz-aware index; the store holds naive New York dates")
    out.index = index.normalize()
    out.index.name = "Date"
    data = out.to_csv(lineterminator="\n", date_format="%Y-%m-%d").encode("utf-8")
    path = _daily_dir(store) / f"{safe_symbol(ticker)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _manifest_path(store: Path) -> Path:
    return _daily_dir(store) / history_store.MANIFEST_NAME


def _read_manifest(store: Path, kind: str, start: dt.date, end: dt.date) -> dict:
    path = _manifest_path(store)
    window = (start.isoformat(), end.isoformat())
    if not path.is_file():
        return {"kind": kind, "start": window[0], "end": window[1], "tickers": {}}
    found = json.loads(path.read_text(encoding="utf-8"))
    if (found.get("start"), found.get("end")) != window:
        raise ValueError(f"{path} holds bars for {found.get('start')}..{found.get('end')}, "
                         f"not {window[0]}..{window[1]}; use a new --bars-root")
    return found


def _write_manifest(store: Path, manifest: dict) -> None:
    path = _manifest_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _fetch_one(provider, ticker: str, start, end, kind: str, store: Path) -> dict:
    got = provider.daily_bars_between([ticker], start, end,
                                      adjustment=ADJUSTMENTS[kind]).get(ticker)
    if got is None or got.empty:
        return {"status": EMPTY}
    return {"status": OK, "sha256": write_frame(store, ticker, got), "rows": int(len(got)),
            "first": got.index.min().date().isoformat(),
            "last": got.index.max().date().isoformat()}


def fetch_bars(tickers, start: dt.date, end: dt.date, root: Path, *, provider,
               out=print) -> dict:
    """Fetch each ticker's RAW and SPLIT bars once. The manifest is rewritten
    after every ticker, so an interrupted fetch resumes where it stopped."""
    wanted = sorted({t.upper().strip() for t in tickers})
    manifests = {}
    for kind in KINDS:
        store = store_dir(root, kind)
        manifest = _read_manifest(store, kind, start, end)
        todo = [t for t in wanted if t not in manifest["tickers"]]
        for done, ticker in enumerate(todo, 1):
            manifest["tickers"][ticker] = _fetch_one(provider, ticker, start, end, kind, store)
            _write_manifest(store, manifest)
            out(f"{kind} bars: {done}/{len(todo)} ({100 * done // len(todo)}%) {ticker}")
        _write_manifest(store, manifest)
        manifests[kind] = manifest
    return manifests


def load_bars(ticker: str, root: Path, kind: str = "raw") -> pd.DataFrame | None:
    with use_store(store_dir(root, kind)):
        return history_store.load(ticker, "daily")


# --- refusals and the bars manifest (V232-4b) -------------------------------------

SPLIT_DRIFT = 0.01
REFUSALS = ("no_bars", "split_in_window", "bars_end_early")


def _missing(frame) -> bool:
    return frame is None or frame.empty


def _window_ratio(raw: pd.DataFrame, split: pd.DataFrame, start: dt.date) -> pd.Series:
    """split.Close / raw.Close on the bars both series hold dated on or after start."""
    both = pd.concat([raw["Close"], split["Close"]], axis=1, keys=["raw", "split"],
                     join="inner")
    both = both[both.index >= pd.Timestamp(start)]
    ratio = both["split"] / both["raw"]
    return ratio[ratio.notna() & (ratio > 0) & (ratio != float("inf"))]


def refusal(raw, split, *, start: dt.date, last_exit: dt.date | None) -> str | None:
    """Why a ticker's bars cannot score its trades (REFUSALS order), or None."""
    if _missing(raw) or _missing(split):
        return "no_bars"
    ratio = _window_ratio(raw, split, start)
    if ratio.empty:
        return "no_bars"
    if float(ratio.max()) / float(ratio.min()) - 1.0 > SPLIT_DRIFT + 1e-12:
        return "split_in_window"
    if last_exit is not None and raw.index.max().date() < last_exit:
        return "bars_end_early"
    return None


def _summary(path: Path) -> dict:
    data = path.read_bytes()
    manifest = json.loads(data)
    statuses = [e.get("status") for e in manifest.get("tickers", {}).values()]
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "start": manifest.get("start"), "end": manifest.get("end"),
            "n_ok": statuses.count(OK), "n_empty": statuses.count(EMPTY)}


def bars_manifest(root: Path) -> dict:
    """Per kind: the manifest's SHA-256, window and counts -- no ticker names."""
    out = {}
    for kind in KINDS:
        path = _manifest_path(store_dir(root, kind))
        out[kind] = _summary(path) if path.is_file() else None
    return out
