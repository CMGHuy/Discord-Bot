# v162 Alpaca history store, part 1b: store I/O and manifests (AH5; AH1–AH4 are in `2026-10-15-v162-alpaca-history-store_1-provider-store-guards.md`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task AH5:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_1b-store-io.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md). Its Global Constraints, Parallelisation, Shared contracts and Task ledger bind every task below.
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)

Part 1 was split here only to keep each file under 1500 lines. AH5 is ledger part 1 and keeps its ledger id, files and contracts.

Paths: `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-15-v162-alpaca-history-store` (the branch). Never `cd`. Use absolute paths and `git -C $WT`. The package `scripts/data/alpaca_history/` is imported as `alpaca_history`, with `scripts/data` on `sys.path` (see part 1's import convention).

# Phase B (continued): store I/O

### Task AH5: Store I/O: atomic write, hashes, manifest

**Model:** sonnet — file writing, hashing and a fixed JSON shape; the atomicity and byte-for-byte determinism rules are spelled out and tested.

**Files:**
- Create: `scripts/data/alpaca_history/store_io.py`
- Test: `tests/history_store/test_store_io.py`

**Interfaces:**
- Consumes: `history_store.TIMEFRAMES`, `INDEX_NAMES`, `OHLCV_COLUMNS`, `MANIFEST_NAME`, `file_path`, `load`, `manifest`, `ticker_status` and the `store_root` fixture (AH2), the package from AH3. The manifest shape is from the index's Global Constraints.
- Produces (binding for AH7–AH9, AH20–AH22):
  - `FEED = "sip"`, `ADJUSTMENT = "all"`, `TMP_SUFFIX = ".tmp"`. A crashed run can leave a `<file>.tmp`, and every reader ignores it.
  - `sha256_file(path: Path) -> str` (hex).
  - `write_frame(frame: pd.DataFrame, path: Path, timeframe: str) -> str`. It writes `OHLCV_COLUMNS` with the index label `INDEX_NAMES[timeframe]`, dates as `%Y-%m-%d` (daily) or `%Y-%m-%d %H:%M:%S` (intraday), and `\n` line endings on every OS, so the VM's hashes verify on Windows after a pull. It writes to `<path>.tmp` and then calls `os.replace`, creating parent directories as needed, and returns the file's sha256. It raises `ValueError` before touching disk on a tz-aware, duplicated or unsorted index or a bad timeframe. On any failure the previous file is untouched and no `.tmp` is left.
  - `manifest_hash(tickers: dict) -> str`: sha256 of `"\n".join(sorted(f"{ticker}:{entry.get('sha256') or '-'}"))`.
  - `empty_manifest(timeframe: str) -> dict` (`timeframe`, `feed`, `adjustment`, `updated_at: None`, `hash`, `tickers: {}`).
  - `load_manifest(root: Path, timeframe: str) -> dict` (`root/<tf>/_manifest.json`, or `empty_manifest` when absent).
  - `save_manifest(root: Path, timeframe: str, manifest: dict, *, now: datetime) -> None`. It is atomic: it sorts `tickers`, recomputes `hash`, sets `updated_at` to `utc_stamp(now)` and updates `manifest` in place. The CLI calls it only when something changed (AH8: an unchanged day writes nothing).
  - `utc_stamp(now: datetime) -> str` (`YYYY-MM-DDTHH:MM:SSZ`; a naive `now` is taken as UTC). It is an extra helper beyond the ledger, used for `fetched_at` too.
  - `ok_entry(frame: pd.DataFrame, timeframe: str, *, start: str, sha256: str, identity: dict, status: str, fetched_at: str) -> dict`. `first`/`last` are `YYYY-MM-DD` (daily) or `YYYY-MM-DD HH:MM` (intraday), and `None` for an empty frame. `rows` is an `int`. The name reflects the full-entry shape: `status` may be a `flagged:` text.
  - `skipped_entry(reason: str, *, start: str, fetched_at: str) -> dict`. `reason` may be the full `skipped: ...` text from `identity.skip_reason` or a bare reason, which gets the prefix. `rows: 0`; `first`, `last`, `sha256` and `identity` are `None`.
  - `is_complete(entry: dict | None, start: str) -> bool` (status `ok` and `entry["start"] <= start`, ISO strings).

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_store_io.py`:

```python
"""Store I/O (spec §1-2): files are written to a temp name and renamed, hashed
byte-for-byte the same on Linux and Windows, and described by one manifest
per timeframe whose top-level hash covers every per-ticker hash."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from alpaca_history import store_io
from swingbot.core.marketdata import history_store as hs

NOW = datetime(2026, 10, 18, 6, 31, 2, tzinfo=timezone.utc)


def _frame(index, name):
    idx = pd.DatetimeIndex(pd.to_datetime(index), name=name)
    n = len(idx)
    values = np.arange(1, n + 1, dtype=float)
    return pd.DataFrame({"Open": values, "High": values + 1, "Low": values - 0.5,
                         "Close": values + 0.25, "Volume": values * 1000}, index=idx)


DAILY = ["2016-01-04", "2016-01-05", "2016-01-06"]
INTRADAY = ["2016-01-04 04:00", "2016-01-04 09:30", "2016-01-04 19:45"]


# --- write_frame -----------------------------------------------------------------------

def test_daily_file_layout_and_hash(store_root):
    path = hs.file_path("AAPL", "daily")
    digest = store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    data = path.read_bytes()
    assert data.startswith(b"Date,Open,High,Low,Close,Volume\n2016-01-04,")
    assert b"\r\n" not in data
    assert digest == hashlib.sha256(data).hexdigest() == store_io.sha256_file(path)
    assert not path.with_name(path.name + store_io.TMP_SUFFIX).exists()


def test_intraday_round_trips_through_history_store(store_root):
    frame = _frame(INTRADAY, "Datetime")
    store_io.write_frame(frame, hs.file_path("AAPL", "15min"), "15min")
    assert hs.file_path("AAPL", "15min").read_text().splitlines()[1].startswith("2016-01-04 04:00:00,")
    pd.testing.assert_frame_equal(hs.load("AAPL", "15min", session="all"), frame, check_freq=False)


def test_same_frame_same_hash(tmp_path):
    frame = _frame(DAILY, "Date")
    assert (store_io.write_frame(frame, tmp_path / "a.csv", "daily")
            == store_io.write_frame(frame.copy(), tmp_path / "b.csv", "daily"))


def test_extra_columns_are_not_written(tmp_path):
    frame = _frame(DAILY, "Date").assign(vwap=1.0)
    store_io.write_frame(frame, tmp_path / "a.csv", "daily")
    assert (tmp_path / "a.csv").read_text().splitlines()[0] == "Date,Open,High,Low,Close,Volume"


@pytest.mark.parametrize("bad", [
    _frame(DAILY, "Date").tz_localize("America/New_York"),
    _frame(["2016-01-04", "2016-01-04"], "Date"),
    _frame(["2016-01-05", "2016-01-04"], "Date"),
])
def test_bad_index_is_refused_and_the_old_file_kept(tmp_path, bad):
    path = tmp_path / "AAPL.csv"
    store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store_io.write_frame(bad, path, "daily")
    assert path.read_bytes() == before


def test_bad_timeframe_is_refused(tmp_path):
    with pytest.raises(ValueError):
        store_io.write_frame(_frame(DAILY, "Date"), tmp_path / "a.csv", "1h")


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "AAPL.csv"
    store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    before = path.read_bytes()

    def half_write(self, target, **kwargs):
        open(target, "w").write("Date,Open\n2016-")
        raise OSError("disk full")
    monkeypatch.setattr(pd.DataFrame, "to_csv", half_write)
    with pytest.raises(OSError):
        store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


# --- manifest -------------------------------------------------------------------------

def test_manifest_hash_is_order_independent_and_covers_every_entry():
    a = {"AAPL": {"sha256": "aa"}, "MSFT": {"sha256": "bb"}, "XAUUSD": {"sha256": None}}
    b = dict(reversed(list(a.items())))
    assert store_io.manifest_hash(a) == store_io.manifest_hash(b)
    expected = hashlib.sha256("AAPL:aa\nMSFT:bb\nXAUUSD:-".encode()).hexdigest()
    assert store_io.manifest_hash(a) == expected
    assert store_io.manifest_hash({**a, "MSFT": {"sha256": "bc"}}) != expected


def test_empty_manifest_shape():
    m = store_io.empty_manifest("hourly")
    assert m == {"timeframe": "hourly", "feed": "sip", "adjustment": "all", "updated_at": None,
                 "hash": store_io.manifest_hash({}), "tickers": {}}
    with pytest.raises(ValueError):
        store_io.empty_manifest("1h")


def test_absent_manifest_loads_empty(tmp_path):
    assert store_io.load_manifest(tmp_path, "daily") == store_io.empty_manifest("daily")


def test_save_then_load_and_read_through_history_store(store_root):
    m = store_io.load_manifest(store_root, "daily")
    m["tickers"]["MSFT"] = {"status": "flagged: short-overlap", "sha256": "bb"}
    m["tickers"]["AAPL"] = {"status": "ok", "sha256": "aa"}
    store_io.save_manifest(store_root, "daily", m, now=NOW)

    assert m["updated_at"] == "2026-10-18T06:31:02Z"
    assert m["hash"] == store_io.manifest_hash(m["tickers"])
    on_disk = json.loads((store_root / "daily" / "_manifest.json").read_text())
    assert on_disk == m and list(on_disk["tickers"]) == ["AAPL", "MSFT"]
    assert store_io.load_manifest(store_root, "daily") == m
    assert hs.manifest("daily") == m
    assert hs.ticker_status("daily", "MSFT") == "flagged: short-overlap"
    assert [p.name for p in (store_root / "daily").iterdir()] == ["_manifest.json"]


def test_utc_stamp():
    assert store_io.utc_stamp(NOW) == "2026-10-18T06:31:02Z"
    assert store_io.utc_stamp(datetime(2026, 10, 18, 6, 31, 2)) == "2026-10-18T06:31:02Z"


# --- entries --------------------------------------------------------------------------

IDENTITY = {"status": "ok", "median_ratio": 1.0001, "overlap": 2710, "dropped_before": None}


def test_ok_entry_daily():
    e = store_io.ok_entry(_frame(DAILY, "Date"), "daily", start="2016-01-01", sha256="aa",
                          identity=IDENTITY, status="ok", fetched_at="2026-10-18T06:12:40Z")
    assert e == {"status": "ok", "start": "2016-01-01", "first": "2016-01-04", "last": "2016-01-06",
                 "rows": 3, "sha256": "aa", "fetched_at": "2026-10-18T06:12:40Z",
                 "identity": IDENTITY}
    assert type(e["rows"]) is int


def test_ok_entry_intraday_and_flagged_status():
    e = store_io.ok_entry(_frame(INTRADAY, "Datetime"), "15min", start="2016-01-01", sha256="cc",
                          identity=IDENTITY, status="flagged: price-mismatch", fetched_at="t")
    assert (e["first"], e["last"], e["status"]) == ("2016-01-04 04:00", "2016-01-04 19:45",
                                                     "flagged: price-mismatch")


def test_ok_entry_empty_frame():
    e = store_io.ok_entry(_frame([], "Date"), "daily", start="2016-01-01", sha256="dd",
                          identity=IDENTITY, status="ok", fetched_at="t")
    assert (e["first"], e["last"], e["rows"]) == (None, None, 0)


@pytest.mark.parametrize("reason", ["skipped: futures", "futures"])
def test_skipped_entry(reason):
    assert store_io.skipped_entry(reason, start="2016-01-01", fetched_at="t") == {
        "status": "skipped: futures", "start": "2016-01-01", "first": None, "last": None,
        "rows": 0, "sha256": None, "fetched_at": "t", "identity": None}


@pytest.mark.parametrize("entry,start,complete", [
    ({"status": "ok", "start": "2016-01-01"}, "2016-01-01", True),
    ({"status": "ok", "start": "2016-01-01"}, "2018-01-01", True),     # covers a later start
    ({"status": "ok", "start": "2018-01-01"}, "2016-01-01", False),    # does not reach back
    ({"status": "flagged: short-overlap", "start": "2016-01-01"}, "2016-01-01", False),
    ({"status": "skipped: futures", "start": "2016-01-01"}, "2016-01-01", False),
    ({"status": "ok"}, "2016-01-01", False),
    (None, "2016-01-01", False),
])
def test_is_complete(entry, start, complete):
    assert store_io.is_complete(entry, start) is complete
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_store_io.py`
Expected: FAIL at collection with `ImportError: cannot import name 'store_io' from 'alpaca_history'`.

- [ ] **Step 3: Implement store I/O**

Create `$WT/scripts/data/alpaca_history/store_io.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_store_io.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Run the whole new suite and check complexity**

Run: `python $WT/scripts/dev/testrun.py suite history-store`
Expected: PASS, 0 failed (AH2–AH5's four files).

Run: `python -m radon cc -s -n C $WT/scripts/data/alpaca_history/`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/data/alpaca_history/store_io.py tests/history_store/test_store_io.py
git -C $WT commit -m "feat(v162): history store I/O -- atomic LF CSV writes, sha256, per-timeframe manifests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

