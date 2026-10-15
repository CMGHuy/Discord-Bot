"""v162: `fetch_alpaca_history.py --mode update` (spec §2).

With Adjustment.ALL every new split or dividend rescales all older bars, and
the shift is uniform and can be tiny, so a short overlap check misses it.
Each update therefore refetches the ticker's full daily history and compares
every stored close at BASIS_RTOL. A change refetches every stored timeframe of
the ticker in full and replaces them together, daily last; otherwise each
timeframe appends the bars after its last one. No file holds two bases and no
ticker has timeframes on different bases.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from alpaca_history import fetch, store_io
from alpaca_history.guards import TokenBucket
from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.data_store import safe_symbol
from swingbot.core.marketdata.providers.alpaca_provider import SIP_DELAY

BASIS_RTOL = 1e-6
NO_BARS = "skipped: no Alpaca bars"
# Daily is written last: a run killed mid-refetch keeps the old daily file, so
# the next update sees the basis change again and refetches all three.
WRITE_ORDER = ("15min", "hourly", "daily")


def basis_changed(stored: pd.DataFrame | None, fresh: pd.DataFrame) -> bool:
    """True when any stored daily close moved by more than BASIS_RTOL relative,
    went NaN on one side, or its date vanished from the fresh history."""
    if stored is None or not len(stored):
        return False
    if len(stored.index.difference(fresh.index)):
        return True
    old = stored["Close"].astype(float)
    new = fresh["Close"].reindex(stored.index).astype(float)
    if bool((old.isna() ^ new.isna()).any()):
        return True
    rel = (new - old).abs() / old.abs().clip(lower=1e-12)
    return bool((rel.dropna() > BASIS_RTOL).any())


def new_bars(stored: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
    """The fresh rows strictly after the last stored bar (an empty frame when none)."""
    if stored is None or not len(stored):
        return fresh.copy()
    return fresh[fresh.index > stored.index.max()]


def read_stored(path: Path, timeframe: str) -> pd.DataFrame | None:
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index.name = history_store.INDEX_NAMES[timeframe]
    return frame if len(frame) else None


def _trim(frame: pd.DataFrame | None, dropped_before: str | None) -> pd.DataFrame | None:
    if frame is not None and dropped_before:
        frame = frame[frame.index >= pd.Timestamp(dropped_before)]
    return frame if frame is not None and len(frame) else None


@dataclass
class _Ticker:
    """One ticker's update: its manifests, provider and stored daily verdict."""
    ticker: str
    root: Path
    provider: object
    limiter: TokenBucket
    now: datetime
    start: date
    manifests: dict
    status: str
    identity: dict | None

    @property
    def stamp(self) -> str:
        return self.now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def path(self, timeframe: str) -> Path:
        return self.root / timeframe / f"{safe_symbol(self.ticker)}.csv"

    def entry(self, timeframe: str) -> dict | None:
        return self.manifests[timeframe]["tickers"].get(self.ticker)

    def fetch(self, timeframe: str, since: date) -> pd.DataFrame | None:
        # End at now - SIP_DELAY, like the full run: the SIP tape is delayed.
        frame = fetch.fetch_store_frame(self.provider, self.ticker, timeframe, since,
                                        self.now - SIP_DELAY, limiter=self.limiter)
        return _trim(frame, (self.identity or {}).get("dropped_before"))


def _put(t: _Ticker, timeframe: str, frame: pd.DataFrame) -> None:
    start = t.entry(timeframe)["start"]
    sha = store_io.write_frame(frame, t.path(timeframe), timeframe)
    t.manifests[timeframe]["tickers"][t.ticker] = store_io.ok_entry(
        frame, timeframe, start=start, sha256=sha, identity=t.identity, status=t.status,
        fetched_at=t.stamp)


def _drop(t: _Ticker, timeframe: str) -> None:
    start = t.entry(timeframe)["start"]
    t.path(timeframe).unlink(missing_ok=True)
    t.manifests[timeframe]["tickers"][t.ticker] = store_io.skipped_entry(
        NO_BARS, start=start, fetched_at=t.stamp)


def _save(t: _Ticker, timeframes) -> None:
    for tf in timeframes:
        store_io.save_manifest(t.root, tf, t.manifests[tf], now=t.now)


def _stored_timeframes(t: _Ticker) -> list[str]:
    return [tf for tf in WRITE_ORDER
            if (t.entry(tf) or {}).get("sha256") and t.path(tf).exists()]


def _refetch_all(t: _Ticker, fresh_daily: pd.DataFrame) -> None:
    """Lockstep: fetch every stored timeframe first, then write, daily last."""
    tfs = _stored_timeframes(t)
    frames = {tf: fresh_daily if tf == "daily"
              else t.fetch(tf, date.fromisoformat(t.entry(tf)["start"])) for tf in tfs}
    for tf in tfs:
        if frames[tf] is None:
            _drop(t, tf)
        else:
            _put(t, tf, frames[tf])
    _save(t, tfs)


def _append(t: _Ticker, timeframes: Sequence[str], fresh_daily: pd.DataFrame) -> list[str]:
    changed = []
    for tf in (tf for tf in WRITE_ORDER if tf in timeframes):
        stored = read_stored(t.path(tf), tf)
        if stored is None:
            continue
        fresh = fresh_daily if tf == "daily" else t.fetch(tf, stored.index.max().date())
        add = new_bars(stored, fresh) if fresh is not None else None
        if add is None or not len(add):
            continue
        _put(t, tf, pd.concat([stored, add]))
        changed.append(tf)
    return changed


def update_ticker(ticker: str, *, root: Path, provider, limiter: TokenBucket, now: datetime,
                  timeframes: Sequence[str], start: date) -> str:
    """"unchanged", "appended" or "refetched" for one stored ticker."""
    manifests = {tf: store_io.load_manifest(root, tf) for tf in history_store.TIMEFRAMES}
    daily = manifests["daily"]["tickers"][ticker]
    t = _Ticker(ticker=ticker, root=Path(root), provider=provider, limiter=limiter, now=now,
                start=start, manifests=manifests, status=daily["status"],
                identity=daily.get("identity"))
    fresh = t.fetch("daily", start)
    if fresh is None:
        return "unchanged"
    if basis_changed(read_stored(t.path("daily"), "daily"), fresh):
        _refetch_all(t, fresh)
        return "refetched"
    changed = _append(t, timeframes, fresh)
    _save(t, changed)
    return "appended" if changed else "unchanged"
