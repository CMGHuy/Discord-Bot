"""v190 -- the PIT store's integrity report (data/market_data_pit/_integrity.json).

The file is written only by scripts/data/check_history_store.py --pit (V190-15)
and frozen before a re-baseline. This module reads it and never writes it;
swingbot/core/marketdata never imports scripts/.

The trim is causal: each ticker's window comes from its membership spans and a
break test frozen before any strategy result is read (spec section 2.3), so
removing a reused symbol's foreign bars uses no information from the bars a
strategy later trades on. history_store.load(store="pit") applies the trim
before any indicator or exit walk reads the frame.

Shape (plan index, section Contracts):

    {"schema": 1, "generated_at": iso, "store_start": date, "store_end": date,
     "thresholds": {...}, "detector_sha": {path: blob},
     "manifest_sha256": {"daily": hex, "hourly": hex, "15min": hex},
     "no_bars": [TICKER, ...],
     "tickers": {TICKER: {
         "admitted": bool, "reason": str | None,
         "identity": status, "identity_manifest": status,
         "reference": {"source": str | None, "sha256": hex | None},
         "dropped_before": int, "first_bar": date | None, "last_bar": date | None,
         "coverage": [{"span": [start, end_excl], "expected": int, "present": int,
                       "missing_runs": [[start, end_excl, sessions]]}],
         "signal_cuts": [[start, end_excl, reason]],
         "trim": {"keep_from": date | None, "keep_before": date | None, "reason": str | None},
         "breaks": [{"date": date, "kind": str, "resolution": str}]}}}
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

INTEGRITY_NAME = "_integrity.json"
SCHEMA_VERSION = 1
NOT_IN_REPORT = "not in integrity report"
NO_BARS_REASON = "no bars"
NOT_ADMITTED = "not admitted"


def _norm(ticker: str) -> str:
    return ticker.upper().strip()


@dataclass(frozen=True)
class Integrity:
    sha256: str
    doc: dict

    def _entry(self, ticker: str) -> dict:
        return (self.doc.get("tickers") or {}).get(_norm(ticker)) or {}

    def trim_window(self, ticker: str) -> tuple[str | None, str | None]:
        """(keep_from inclusive, keep_before exclusive); (None, None) untrimmed."""
        trim = self._entry(ticker).get("trim") or {}
        return trim.get("keep_from"), trim.get("keep_before")

    def signal_cuts(self, ticker: str) -> list[tuple[str, str]]:
        """[(start, end_excl), ...] sorted; the cut reason is dropped."""
        cuts = self._entry(ticker).get("signal_cuts") or []
        return sorted((cut[0], cut[1]) for cut in cuts)

    def exclusion(self, ticker: str) -> str | None:
        """Why the ticker is refused, or None when it is admitted."""
        key = _norm(ticker)
        if key in (self.doc.get("no_bars") or []):
            return NO_BARS_REASON
        entry = (self.doc.get("tickers") or {}).get(key)
        if entry is None:
            return NOT_IN_REPORT
        if not entry.get("admitted"):
            return entry.get("reason") or NOT_ADMITTED
        return None

    def manifest_sha256(self, timeframe: str) -> str | None:
        return (self.doc.get("manifest_sha256") or {}).get(timeframe)


def integrity_path(root: Path) -> Path:
    return Path(root) / INTEGRITY_NAME


def load_integrity(root: Path) -> Integrity | None:
    """The report under root, or None when absent. An unknown schema raises."""
    path = integrity_path(root)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"{path}: integrity schema {doc.get('schema')!r}; "
                         f"expected {SCHEMA_VERSION}")
    return Integrity(sha256=hashlib.sha256(raw).hexdigest(), doc=doc)


_CACHE: dict[Path, tuple[tuple[int, int], Integrity | None]] = {}


def cached_integrity(root: Path) -> Integrity | None:
    """load_integrity memoised on (path, st_mtime_ns, st_size): a rewritten file is
    re-read, and an absent one is not cached so a report written later is found."""
    path = integrity_path(root)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    stamp = (stat.st_mtime_ns, stat.st_size)
    hit = _CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    found = load_integrity(root)
    _CACHE[path] = (stamp, found)
    return found


def apply_trim(frame: pd.DataFrame | None,
               window: tuple[str | None, str | None]) -> pd.DataFrame | None:
    """Keep keep_from <= bar date < keep_before, compared on the bar's day for every
    timeframe (an intraday bar on keep_before's date is dropped, one on keep_from's
    date kept). (None, None) returns the frame unchanged; an empty result is None."""
    keep_from, keep_before = window
    if frame is None or (keep_from is None and keep_before is None):
        return frame
    days = frame.index.normalize()
    mask = np.ones(len(frame), dtype=bool)
    if keep_from is not None:
        mask &= days >= pd.Timestamp(keep_from)
    if keep_before is not None:
        mask &= days < pd.Timestamp(keep_before)
    out = frame[mask]
    return out if len(out) else None
