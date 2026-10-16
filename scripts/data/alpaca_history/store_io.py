"""Writes for the v162 history store: atomic CSV files, SHA-256 hashes and
one manifest per timeframe (data/market_data/<tf>/_manifest.json).

Every file is written to <name>.tmp and renamed, so a crash never leaves a
half-written CSV under a real name. Line endings are "\\n" on every OS, so a
hash computed on the VM verifies after the store is pulled to Windows.
history_store is the read side; this module is the only write side.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from swingbot.core.marketdata import history_store

FEED = "sip"
ADJUSTMENT = "all"
TMP_SUFFIX = ".tmp"
_CSV_DATE_FORMATS = {"15min": "%Y-%m-%d %H:%M:%S", "hourly": "%Y-%m-%d %H:%M:%S", "daily": "%Y-%m-%d"}
_ENTRY_FORMATS = {"15min": "%Y-%m-%d %H:%M", "hourly": "%Y-%m-%d %H:%M", "daily": "%Y-%m-%d"}


def _require_timeframe(timeframe: str) -> None:
    if timeframe not in history_store.TIMEFRAMES:
        raise ValueError(f"unknown history store timeframe {timeframe!r}; "
                         f"expected one of {history_store.TIMEFRAMES}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replace_atomically(path: Path, write: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _check_index(frame: pd.DataFrame) -> None:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        raise ValueError("history store frames hold naive New York wall-clock times; got a tz-aware index")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("history store frames need a sorted index without duplicates")


def write_frame(frame: pd.DataFrame, path: Path, timeframe: str) -> str:
    """Atomically write one ticker x timeframe file; return its sha256."""
    _require_timeframe(timeframe)
    _check_index(frame)
    path = Path(path)
    out = frame[history_store.OHLCV_COLUMNS]
    _replace_atomically(path, lambda tmp: out.to_csv(
        tmp, index_label=history_store.INDEX_NAMES[timeframe],
        date_format=_CSV_DATE_FORMATS[timeframe], lineterminator="\n"))
    return sha256_file(path)


def manifest_hash(tickers: dict) -> str:
    lines = sorted(f"{ticker}:{(entry or {}).get('sha256') or '-'}" for ticker, entry in tickers.items())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def empty_manifest(timeframe: str) -> dict:
    _require_timeframe(timeframe)
    return {"timeframe": timeframe, "feed": FEED, "adjustment": ADJUSTMENT,
            "updated_at": None, "hash": manifest_hash({}), "tickers": {}}


def _manifest_file(root: Path, timeframe: str) -> Path:
    _require_timeframe(timeframe)
    return Path(root) / timeframe / history_store.MANIFEST_NAME


def load_manifest(root: Path, timeframe: str) -> dict:
    path = _manifest_file(root, timeframe)
    if not path.is_file():
        return empty_manifest(timeframe)
    return json.loads(path.read_text(encoding="utf-8"))


def utc_stamp(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_manifest(root: Path, timeframe: str, manifest: dict, *, now: datetime) -> None:
    """Atomically write the manifest; sorts tickers, recomputes the top-level
    hash and stamps updated_at, updating `manifest` in place."""
    path = _manifest_file(root, timeframe)
    manifest["timeframe"] = timeframe
    manifest.setdefault("feed", FEED)
    manifest.setdefault("adjustment", ADJUSTMENT)
    manifest["tickers"] = dict(sorted(manifest.get("tickers", {}).items()))
    manifest["hash"] = manifest_hash(manifest["tickers"])
    manifest["updated_at"] = utc_stamp(now)
    text = json.dumps(manifest, indent=1) + "\n"
    _replace_atomically(path, lambda tmp: tmp.write_bytes(text.encode("utf-8")))


def _stamp(frame: pd.DataFrame, timeframe: str, pick: str) -> str | None:
    if frame.empty:
        return None
    return getattr(frame.index, pick)().strftime(_ENTRY_FORMATS[timeframe])


def ok_entry(frame: pd.DataFrame, timeframe: str, *, start: str, sha256: str,
             identity: dict, status: str, fetched_at: str) -> dict:
    """A written file's manifest entry; `status` is "ok" or a "flagged: ..." text."""
    _require_timeframe(timeframe)
    return {"status": status, "start": start,
            "first": _stamp(frame, timeframe, "min"), "last": _stamp(frame, timeframe, "max"),
            "rows": int(len(frame)), "sha256": sha256, "fetched_at": fetched_at,
            "identity": identity}


def skipped_entry(reason: str, *, start: str, fetched_at: str) -> dict:
    status = reason if reason.startswith("skipped:") else f"skipped: {reason}"
    return {"status": status, "start": start, "first": None, "last": None, "rows": 0,
            "sha256": None, "fetched_at": fetched_at, "identity": None}


def is_complete(entry: dict | None, start: str) -> bool:
    """A full-mode rerun skips this file: it is ok and reaches back to `start`."""
    if not entry or entry.get("status") != "ok" or not entry.get("start"):
        return False
    return str(entry["start"]) <= start
