# v162 Alpaca history store, part 2: fetch, backfill CLI, update mode

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH7:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_2-backfill-switch.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§1 store, §2 backfill script, §3 training switch, Amendments, Acceptance 1–5)
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts (script-side imports, `RunSummary`, admin API) and the task ledger. Every task below implicitly includes them. Ledger part 2 outgrew the 1500-line cap: AH6–AH8 are here, AH9 and AH10 are in [`2026-10-15-v162-alpaca-history-store_2b-check-training-switch.md`](2026-10-15-v162-alpaca-history-store_2b-check-training-switch.md).

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows the main tree unchanged.
- Tests in `tests/history_store/` rely on AH2's `conftest.py`: `scripts/data` and `scripts/ops` are on `sys.path` (so `from alpaca_history import fetch` and `import fetch_backtest_data` work), and the `store_root` fixture points `HISTORY_STORE_DIR` at a `tmp_path` directory and returns it. CLI scripts are loaded with `importlib.util.spec_from_file_location`.
- Alpaca is always faked. The fakes below stand in for `AlpacaProvider.history_bars(ticker, timeframe, start, end)` (AH1): they return the **raw** Alpaca frame shape, lowercase `open, high, low, close, volume`, tz-aware UTC index, or `None` when the window holds no bars.
- `TokenBucket` in tests always gets a clock that jumps 60 s per call, so `acquire()` never waits: `guards.TokenBucket(clock=_jump_clock(), sleep=lambda s: None)`.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Complexity: `python -m radon cc -s -n C <files>` prints nothing for the files a task creates.

# Phase B: fetch, backfill CLI, update mode

### Task AH6: Yearly fetch and timeframe conversion

**Model:** sonnet — a pure loop over calendar years plus a converter table, behaviour fixed by the spec and the AH1/AH3 contracts

**Files:**
- Create: `scripts/data/alpaca_history/fetch.py`
- Test: `tests/history_store/test_fetch.py`

**Interfaces:**
- Consumes (AH1): `AlpacaProvider.history_bars(ticker: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame | None` with timeframe keys `"15min"`, `"30min"`, `"1d"` (raw frame, lowercase columns, tz-aware UTC index; raises `AlpacaMiss`/`AlpacaAuthError`); `providers.base.to_store_intraday(df)`, `providers.base.to_store_hourly(df30)`; existing `providers.base.to_yf_daily(df)` (`base.py:37`, naive `Date` index). (AH3): `guards.TokenBucket`, `guards.call_with_backoff(fn, *, limiter, sleep, retries)` (acquires a token per attempt, backs off on 429/5xx/no status, re-raises `AlpacaAuthError` at once).
- Produces (ledger AH6): `ALPACA_TIMEFRAME = {"15min": "15min", "hourly": "30min", "daily": "1d"}`; `year_windows(start: date, end: datetime) -> list[tuple[datetime, datetime]]`; `fetch_raw(provider, ticker, timeframe, start, end, *, limiter, sleep=time.sleep) -> pd.DataFrame | None`; `to_store_frame(timeframe, raw) -> pd.DataFrame`; `fetch_store_frame(provider, ticker, timeframe, start, end, *, limiter, sleep=time.sleep) -> pd.DataFrame | None`. AH7 and AH8 call `fetch_store_frame`.

**Rules this task freezes (spec §1 Source, 15min, hourly, daily):**
- One `history_bars` call per calendar year (UTC): the first window starts at `start` 00:00 UTC, every later one on 1 January, the last ends at `end`. A naive `end` is read as UTC. `end <= start` gives no windows.
- Windows with no bars are skipped. The joined raw frame is sorted and de-duplicated on the index (keep last), so a bar Alpaca returns at both edges of a boundary is stored once.
- Conversion happens **after** the years are joined (the hourly resample must see whole sessions): `15min` → `to_store_intraday` (all sessions kept), `hourly` → `to_store_hourly` (built from 30-minute bars, RTH only), `daily` → `to_yf_daily`. Alpaca's native `1Hour` timeframe is never requested.
- An unknown store timeframe raises `ValueError` before any request.

- [ ] **Step 1: Write the failing test**

Create `tests/history_store/test_fetch.py`:

```python
"""v162 AH6: yearly Alpaca windows, retry through the guards, store-frame conversion."""
from __future__ import annotations

import itertools
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpaca_history import fetch, guards
from swingbot.core.marketdata.providers import alpaca_provider as ap

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _jump_clock():
    ticks = itertools.count(0.0, 60.0)
    return lambda: next(ticks)


def _limiter():
    return guards.TokenBucket(clock=_jump_clock(), sleep=lambda s: None)


def _raw(ny_stamps: list[str], close: float = 10.5) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(s, tz=NY) for s in ny_stamps]).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame({"open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
                         "close": [close] * n, "volume": [100.0] * n}, index=idx)


class FakeProvider:
    """Serves one raw frame per Alpaca timeframe, sliced to [start, end]
    (or whole, when `ignore_window` is set, to mimic a bar repeated at a boundary)."""

    def __init__(self, frames: dict[str, pd.DataFrame], errors: list[Exception] | None = None,
                 ignore_window: bool = False):
        self.frames = frames
        self.errors = list(errors or [])
        self.ignore_window = ignore_window
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe, start, end))
        if self.errors:
            raise self.errors.pop(0)
        frame = self.frames.get(timeframe)
        if frame is None:
            return None
        if self.ignore_window:
            return frame
        part = frame[(frame.index >= start) & (frame.index <= end)]
        return part if len(part) else None


class _Http(Exception):
    def __init__(self, code):
        super().__init__(str(code))
        self.status_code = code


def _wrapped(cls, code: int):
    try:
        raise cls(str(code)) from _Http(code)
    except cls as exc:
        return exc


def test_year_windows_cover_calendar_years_and_stop_at_end():
    end = datetime(2018, 3, 5, 12, 0, tzinfo=UTC)
    windows = fetch.year_windows(date(2016, 1, 1), end)
    assert windows == [
        (datetime(2016, 1, 1, tzinfo=UTC), datetime(2017, 1, 1, tzinfo=UTC)),
        (datetime(2017, 1, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)),
        (datetime(2018, 1, 1, tzinfo=UTC), end),
    ]


def test_year_windows_start_mid_year_and_naive_end_is_utc():
    windows = fetch.year_windows(date(2016, 6, 15), datetime(2016, 9, 1))
    assert windows == [(datetime(2016, 6, 15, tzinfo=UTC), datetime(2016, 9, 1, tzinfo=UTC))]


def test_year_windows_empty_when_end_not_after_start():
    assert fetch.year_windows(date(2020, 1, 1), datetime(2020, 1, 1, tzinfo=UTC)) == []


def test_fetch_raw_calls_once_per_year_with_the_alpaca_timeframe():
    raw30 = _raw(["2016-03-01 09:30", "2016-03-01 10:00", "2017-03-01 09:30"])
    prov = FakeProvider({"30min": raw30})
    out = fetch.fetch_raw(prov, "AAPL", "hourly", date(2016, 1, 1),
                          datetime(2017, 6, 1, tzinfo=UTC), limiter=_limiter())
    assert [c[1] for c in prov.calls] == ["30min", "30min"]
    assert len(out) == 3 and out.index.is_monotonic_increasing


def test_fetch_raw_drops_a_bar_returned_by_two_windows():
    prov = FakeProvider({"1d": _raw(["2016-12-30 00:00"])}, ignore_window=True)
    out = fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                          datetime(2017, 2, 1, tzinfo=UTC), limiter=_limiter())
    assert len(prov.calls) == 2
    assert len(out) == 1


def test_fetch_raw_returns_none_when_no_window_has_bars():
    prov = FakeProvider({})
    assert fetch.fetch_raw(prov, "AAPL", "15min", date(2016, 1, 1),
                           datetime(2018, 1, 2, tzinfo=UTC), limiter=_limiter()) is None
    assert len(prov.calls) == 3


def test_fetch_raw_retries_a_rate_limit_through_call_with_backoff():
    sleeps: list[float] = []
    prov = FakeProvider({"1d": _raw(["2016-03-01 00:00"])}, errors=[_wrapped(ap.AlpacaMiss, 429)])
    out = fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                          datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter(), sleep=sleeps.append)
    assert len(out) == 1
    assert len(sleeps) == 1 and len(prov.calls) == 2


def test_fetch_raw_stops_on_auth_error():
    prov = FakeProvider({}, errors=[_wrapped(ap.AlpacaAuthError, 401)])
    with pytest.raises(ap.AlpacaAuthError):
        fetch.fetch_raw(prov, "AAPL", "daily", date(2016, 1, 1),
                        datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter(), sleep=lambda s: None)
    assert len(prov.calls) == 1


def test_unknown_timeframe_raises_before_any_request():
    prov = FakeProvider({})
    with pytest.raises(ValueError):
        fetch.fetch_raw(prov, "AAPL", "1Hour", date(2016, 1, 1),
                        datetime(2017, 1, 1, tzinfo=UTC), limiter=_limiter())
    assert prov.calls == []
    with pytest.raises(ValueError):
        fetch.to_store_frame("weekly", _raw(["2016-03-01 09:30"]))


def test_to_store_frame_daily_is_a_naive_date_index():
    out = fetch.to_store_frame("daily", _raw(["2016-03-01 00:00", "2016-03-02 00:00"]))
    assert out.index.name == "Date" and out.index.tz is None
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert [d.isoformat() for d in out.index.date] == ["2016-03-01", "2016-03-02"]


def test_to_store_frame_15min_keeps_extended_hours_as_ny_wall_clock():
    out = fetch.to_store_frame("15min", _raw(["2016-03-01 04:00", "2016-03-01 09:30",
                                              "2016-03-01 19:45"]))
    assert out.index.name == "Datetime" and out.index.tz is None
    assert [t.strftime("%H:%M") for t in out.index] == ["04:00", "09:30", "19:45"]


def test_to_store_frame_hourly_is_built_from_30min_rth_bars():
    out = fetch.to_store_frame("hourly", _raw(["2016-03-01 08:00", "2016-03-01 09:30",
                                               "2016-03-01 10:00", "2016-03-01 15:30"]))
    assert out.index.name == "Datetime" and out.index.tz is None
    assert [t.strftime("%H:%M") for t in out.index] == ["09:30", "15:30"]
    assert out["Volume"].iloc[0] == 200.0


def test_fetch_store_frame_converts_or_returns_none():
    prov = FakeProvider({"15min": _raw(["2016-03-01 09:30", "2016-03-01 09:45"])})
    out = fetch.fetch_store_frame(prov, "AAPL", "15min", date(2016, 1, 1),
                                  datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter())
    assert out.index.name == "Datetime" and len(out) == 2
    assert fetch.fetch_store_frame(FakeProvider({}), "AAPL", "daily", date(2016, 1, 1),
                                   datetime(2016, 6, 1, tzinfo=UTC), limiter=_limiter()) is None
```

AH3's bucket spaces calls 0.5 s apart on its clock; `_jump_clock()` advances 60 s per read, so no test ever sleeps.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_fetch.py`
Expected: FAIL with `ImportError: cannot import name 'fetch' from 'alpaca_history'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/data/alpaca_history/fetch.py`:

```python
"""v162: fetch one ticker x timeframe from Alpaca one calendar year at a time
and convert it to the store's frame shape (spec §1).

Each year is one `AlpacaProvider.history_bars` call routed through the
guards' token bucket and backoff, so memory stays bounded and every request
is counted. Conversion runs once on the joined raw frame: the hourly
resample needs whole sessions.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pandas as pd

from swingbot.core.marketdata.providers.base import (
    to_store_hourly,
    to_store_intraday,
    to_yf_daily,
)

from alpaca_history.guards import TokenBucket, call_with_backoff

# Store timeframe -> the Alpaca timeframe key `history_bars` accepts. hourly is
# built from 30-minute bars (09:30-anchored); Alpaca's clock-aligned 1Hour
# bars are never requested.
ALPACA_TIMEFRAME = {"15min": "15min", "hourly": "30min", "daily": "1d"}

_CONVERTERS = {"15min": to_store_intraday, "hourly": to_store_hourly, "daily": to_yf_daily}


def _check(timeframe: str) -> None:
    if timeframe not in ALPACA_TIMEFRAME:
        raise ValueError(f"unknown store timeframe {timeframe!r}; "
                         f"expected one of {sorted(ALPACA_TIMEFRAME)}")


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def year_windows(start: date, end: datetime) -> list[tuple[datetime, datetime]]:
    """UTC (start, end) windows, one per calendar year, the last ending at `end`."""
    end = _utc(end)
    cur = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    windows = []
    while cur < end:
        nxt = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        windows.append((cur, min(nxt, end)))
        cur = nxt
    return windows


def fetch_raw(provider, ticker: str, timeframe: str, start: date, end: datetime, *,
              limiter: TokenBucket, sleep=time.sleep) -> pd.DataFrame | None:
    """The raw Alpaca frame for `ticker` over [start, end], or None when no year has bars."""
    _check(timeframe)
    alpaca_tf = ALPACA_TIMEFRAME[timeframe]
    parts = []
    for lo, hi in year_windows(start, end):
        frame = call_with_backoff(
            lambda lo=lo, hi=hi: provider.history_bars(ticker, alpaca_tf, lo, hi),
            limiter=limiter, sleep=sleep)
        if frame is not None and len(frame):
            parts.append(frame)
    if not parts:
        return None
    raw = pd.concat(parts).sort_index()
    return raw[~raw.index.duplicated(keep="last")]


def to_store_frame(timeframe: str, raw: pd.DataFrame) -> pd.DataFrame:
    """Raw Alpaca bars -> the store's naive-index `Open..Volume` frame."""
    _check(timeframe)
    return _CONVERTERS[timeframe](raw)


def fetch_store_frame(provider, ticker: str, timeframe: str, start: date, end: datetime, *,
                      limiter: TokenBucket, sleep=time.sleep) -> pd.DataFrame | None:
    """`fetch_raw` then `to_store_frame`; None when there is nothing to store."""
    raw = fetch_raw(provider, ticker, timeframe, start, end, limiter=limiter, sleep=sleep)
    if raw is None:
        return None
    frame = to_store_frame(timeframe, raw)
    return frame if len(frame) else None
```

The package imports its siblings absolutely (`from alpaca_history.guards import ...`), part 1's import convention: `scripts/data` is on `sys.path` for both the CLI and the tests.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_fetch.py`
Expected: PASS (13 tests). Then `python -m radon cc -s -n C $WT/scripts/data/alpaca_history/fetch.py` prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/data/alpaca_history/fetch.py tests/history_store/test_fetch.py
git -C $WT commit -m "feat(v162): AH6 yearly Alpaca fetch and store-frame conversion"
```

### Task AH7: CLI `fetch_alpaca_history.py`, full mode

**Model:** sonnet — wiring of finished modules behind one CLI, every rule given below; the update logic (opus) is AH8

**Files:**
- Create: `scripts/data/fetch_alpaca_history.py`
- Test: `tests/history_store/test_fetch_alpaca_history.py`

**Interfaces:**
- Consumes (AH2): `history_store.TIMEFRAMES`, `history_store.store_root()`. (AH3): `guards.TokenBucket()` (attribute `calls`), `guards.assert_outside_hours(now, *, force)`, `guards.HoursGuardError`, `guards.estimate_bytes(n_tickers, timeframes, years)`, `guards.check_disk(path, needed_bytes)`, `guards.DiskGuardError`, `guards.Progress(total)` with `step(label)`. (AH4): `identity.skip_reason(ticker) -> str | None` (the full status text, e.g. `"skipped: futures"`), `identity.reference_frame(ticker, *, backtest_dir, market_dir)`, `identity.identity_check(fresh, reference) -> (IdentityResult, trimmed)`; `IdentityResult.status` is the manifest status text (`"ok"` or `"flagged: <reason>"`), `IdentityResult.to_json()` the manifest `identity` dict with key `dropped_before`. (AH5): `store_io.load_manifest(root, tf)`, `store_io.save_manifest(root, tf, manifest, *, now)`, `store_io.write_frame(frame, path, tf) -> sha256`, `store_io.ok_entry(frame, tf, *, start, sha256, identity, status, fetched_at)`, `store_io.skipped_entry(reason, *, start, fetched_at)` (`reason` is the full status text and becomes `status`), `store_io.is_complete(entry, start)`. (AH6): `fetch.fetch_store_frame(provider, ticker, tf, start, end, *, limiter)`. Existing: `fetch_backtest_data.training_tickers(watchlist, benchmark, training_universe)` and `load_watchlist()` (`scripts/data/fetch_backtest_data.py:62,83`), `data_store.safe_symbol` (`data_store.py:104`), `backtest_cache.CACHE_DIR` (`backtest_cache.py:45`), `config.MARKET_REGIME_TICKER`, `config.ALPACA_API_KEY_ID`, `config.ALPACA_API_SECRET_KEY`, `config.ALPACA_DATA_FEED_LIVE`.
- Produces (ledger AH7): `RunSummary` (index Shared contracts); `parse_args(argv)`; `make_provider() -> AlpacaProvider`; `run_full(args, provider, limiter, now) -> RunSummary`; `main(argv=None, *, provider=None, now=None) -> int`. For AH8 also: `NO_BARS = "skipped: no Alpaca bars"`; `_Run` (dataclass: `root, start, timeframes, force, provider, limiter, now, backtest_dir, market_dir`, property `stamp`); `_make_run(args, provider, limiter, now) -> _Run`; `full_ticker(ticker: str, run: _Run, summary: RunSummary) -> None` (loads the three manifests from disk, saves what it changed); `_tickers(args) -> list[str]`; `_store_path(root, timeframe, ticker) -> Path`; `make_limiter() -> guards.TokenBucket`; `_RUNNERS: dict[str, Callable]` (AH7 registers `"full"`, AH8 adds `"update"`). The test helpers `FakeHistory`, `NOW`, `DAYS`, `daily_closes`, `write_reference`, `load_cli` in the test module are imported by AH8's test.

**Rules this task freezes (spec §2, Global Constraints "Manifest shape", "Identity check", "Rate and hours"):**
- **Order of checks:** hours guard (refuses during the US regular session unless `--force-hours`, exit 1), then the disk guard over the tickers that still have work (exit 1), then the provider (missing keys or a 401/403 → exit 2), then the run.
- **Tickers:** `--tickers` (upper-cased, de-duplicated, sorted) wins; otherwise the watchlist plus `config.MARKET_REGIME_TICKER` through `fetch_backtest_data.training_tickers`, the same population `data/backtest_cache/` holds, so the regime benchmark every backtest reads (`run_backtest_range._market_frame`) is in the store.
- **Timeframes run daily first** (`daily`, `hourly`, `15min` order), because intraday entries copy the daily `status` and `identity`.
- **Per ticker:** `skip_reason` → every requested timeframe gets a `skipped_entry` and no request is made; a ticker already carrying that same skip status writes nothing. Otherwise the timeframes still to do are those whose entry is not `is_complete(entry, --start)` (all of them with `--force`). None → listed as unchanged, no request.
- **Identity:** the daily frame is fetched when daily is to do, or when no stored daily entry with an `identity` exists; it is checked against `reference_frame` and trimmed (`dropped_before`). Otherwise the stored daily status and identity are reused. No daily bars at all → every to-do timeframe is `skipped: no Alpaca bars`. A flagged ticker is written and listed under `flagged`.
- **Intraday frames** are trimmed to `index >= dropped_before` and written with the daily status and identity. A timeframe with no bars after trimming becomes `skipped: no Alpaca bars` for that timeframe only.
- **Resume:** after each ticker, the manifests it changed are saved (`save_manifest` is atomic), so a killed run resumes at the next incomplete ticker. A ticker with nothing to do saves nothing.
- `RunSummary` entries are `"<TICKER>/<timeframe>"`; `skipped` and `flagged` are keyed by ticker (a per-timeframe no-bars skip by `"<TICKER>/<timeframe>"`); `requests` = `limiter.calls`. The summary is printed at the end.

- [ ] **Step 1: Write the failing test**

Create `tests/history_store/test_fetch_alpaca_history.py`:

```python
"""v162 AH7: the backfill CLI in full mode -- guards, skips, identity flags, resume."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from alpaca_history import guards
from swingbot.core.marketdata.providers import alpaca_provider as ap

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
UTC = timezone.utc
NOW = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)            # a Saturday: outside the session
IN_SESSION = datetime(2024, 5, 28, 15, 0, tzinfo=UTC)    # Tuesday 11:00 ET
DAYS = pd.bdate_range("2023-01-02", "2024-05-31")
TF = ("daily", "hourly", "15min")


def load_cli():
    spec = importlib.util.spec_from_file_location(
        "fetch_alpaca_history", ROOT / "scripts" / "data" / "fetch_alpaca_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.make_limiter = _fast_limiter
    return mod


def _fast_limiter():
    """AH3's bucket on a clock that jumps 60 s per read, so it never sleeps."""
    ticks = itertools.count(0.0, 60.0)
    return guards.TokenBucket(clock=lambda: next(ticks), sleep=lambda s: None)


def daily_closes(days, base: float = 100.0) -> np.ndarray:
    return base + 0.1 * np.arange(len(days))


def _utc_index(naive_ny) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(naive_ny).tz_localize(NY).tz_convert("UTC")


def _frame(index_utc, closes) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": closes, "high": closes + 1, "low": closes - 1, "close": closes,
                         "volume": np.full(len(closes), 1000.0)}, index=index_utc)


class FakeHistory:
    """Stands in for AlpacaProvider.history_bars: daily bars on `days`, intraday
    bars 04:00-20:00 ET on the last two of them, every price times `scale`."""

    def __init__(self, tickers, days=DAYS, scale: float = 1.0, error: Exception | None = None):
        self.tickers = set(tickers)
        self.days = days
        self.scale = scale
        self.error = error
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def _bars(self, timeframe: str) -> pd.DataFrame:
        if timeframe == "1d":
            return _frame(_utc_index(self.days), daily_closes(self.days) * self.scale)
        stamps = [ts for d in self.days[-2:]
                  for ts in pd.date_range(d + pd.Timedelta(hours=4), d + pd.Timedelta(hours=20),
                                          freq=timeframe, inclusive="left")]
        return _frame(_utc_index(stamps), np.full(len(stamps), 150.0) * self.scale)

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe, start, end))
        if self.error is not None:
            raise self.error
        if ticker not in self.tickers:
            return None
        frame = self._bars(timeframe)
        part = frame[(frame.index >= start) & (frame.index <= end)]
        return part if len(part) else None


def write_reference(directory: Path, ticker: str, days, closes) -> None:
    closes = np.asarray(closes, dtype=float)
    frame = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                          "Volume": 1.0}, index=pd.DatetimeIndex(days, name="Date"))
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / f"{ticker}.csv")


@pytest.fixture
def dirs(tmp_path, store_root):
    bt, md = tmp_path / "backtest_cache", tmp_path / "market_daily"
    md.mkdir()
    earlier = pd.bdate_range("2022-01-03", "2022-12-30")
    write_reference(bt, "AAPL", earlier.append(DAYS),
                    np.concatenate([np.full(len(earlier), 90.0), daily_closes(DAYS)]))
    late = DAYS[DAYS >= "2024-01-02"]
    write_reference(bt, "SNDK", late, daily_closes(DAYS)[DAYS >= "2024-01-02"])
    write_reference(bt, "MSFT", DAYS, daily_closes(DAYS) * 2)
    return {"root": store_root, "bt": bt, "md": md}


def _argv(dirs, tickers: str, *extra: str) -> list[str]:
    return ["--tickers", tickers, "--start", "2023-01-01", "--root", str(dirs["root"]),
            "--backtest-dir", str(dirs["bt"]), "--market-dir", str(dirs["md"]), *extra]


def _manifest(root: Path, tf: str) -> dict:
    return json.loads((root / tf / "_manifest.json").read_text())


def test_full_run_writes_three_timeframes_with_hashed_manifests(dirs):
    cli = load_cli()
    assert cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW) == 0
    for tf in TF:
        path = dirs["root"] / tf / "AAPL.csv"
        entry = _manifest(dirs["root"], tf)["tickers"]["AAPL"]
        assert entry["status"] == "ok" and entry["start"] == "2023-01-01"
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["rows"] == len(pd.read_csv(path))
        assert entry["identity"]["status"] == "ok"
    assert _manifest(dirs["root"], "daily")["feed"] == "sip"
    m15 = pd.read_csv(dirs["root"] / "15min" / "AAPL.csv", index_col="Datetime", parse_dates=True)
    assert m15.index[0].strftime("%H:%M") == "04:00" and len(m15) == 128
    hourly = pd.read_csv(dirs["root"] / "hourly" / "AAPL.csv", index_col="Datetime", parse_dates=True)
    assert len(hourly) == 14 and hourly.index[-1].strftime("%H:%M") == "15:30"


def test_identity_flags_are_written_inherited_and_listed(dirs, capsys):
    cli = load_cli()
    tickers = "AAPL,SNDK,MSFT,NVDA"
    assert cli.main(_argv(dirs, tickers), provider=FakeHistory(tickers.split(",")), now=NOW) == 0
    daily = _manifest(dirs["root"], "daily")["tickers"]
    assert daily["SNDK"]["status"] == "flagged: short-overlap"
    assert daily["MSFT"]["status"] == "flagged: price-mismatch"
    assert daily["NVDA"]["status"] == "flagged: no-reference"
    assert daily["SNDK"]["identity"]["dropped_before"] == "2024-01-02"
    first = pd.read_csv(dirs["root"] / "daily" / "SNDK.csv", index_col="Date", parse_dates=True).index[0]
    assert first == pd.Timestamp("2024-01-02")
    for tf in ("hourly", "15min"):
        entry = _manifest(dirs["root"], tf)["tickers"]["SNDK"]
        assert entry["status"] == "flagged: short-overlap"
        assert entry["identity"] == daily["SNDK"]["identity"]
    out = capsys.readouterr().out
    assert "flagged SNDK: flagged: short-overlap" in out and "flagged NVDA" in out


def test_skips_are_recorded_with_reasons_and_make_no_request(dirs, capsys):
    cli = load_cli()
    prov = FakeHistory([])
    assert cli.main(_argv(dirs, "XAUUSD,GC=F,^VIX"), provider=prov, now=NOW) == 0
    assert prov.calls == []
    for tf in TF:
        tickers = _manifest(dirs["root"], tf)["tickers"]
        for t in ("XAUUSD", "GC=F", "^VIX"):
            assert tickers[t]["status"].startswith("skipped: ") and tickers[t]["rows"] == 0
            assert tickers[t]["sha256"] is None
    out = capsys.readouterr().out
    assert "skipped XAUUSD: skipped: spot metal" in out and "skipped GC=F: skipped: futures" in out


def test_a_ticker_alpaca_does_not_serve_is_skipped_no_bars(dirs):
    cli = load_cli()
    assert cli.main(_argv(dirs, "AMZN"), provider=FakeHistory([]), now=NOW) == 0
    assert _manifest(dirs["root"], "daily")["tickers"]["AMZN"]["status"] == cli.NO_BARS
    assert not (dirs["root"] / "daily" / "AMZN.csv").exists()


def test_rerun_skips_complete_files_unless_forced(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW)
    manifest_before = (dirs["root"] / "daily" / "_manifest.json").read_text()
    again = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=again, now=NOW) == 0
    assert again.calls == []
    assert (dirs["root"] / "daily" / "_manifest.json").read_text() == manifest_before
    forced = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL", "--force"), provider=forced, now=NOW) == 0
    assert {c[1] for c in forced.calls} == {"1d", "30min", "15min"}


def test_an_earlier_start_is_not_covered_and_refetches(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW)
    earlier = FakeHistory(["AAPL"])
    argv = _argv(dirs, "AAPL")
    argv[argv.index("2023-01-01")] = "2022-06-01"
    assert cli.main(argv, provider=earlier, now=NOW) == 0
    assert earlier.calls
    assert _manifest(dirs["root"], "daily")["tickers"]["AAPL"]["start"] == "2022-06-01"


def test_intraday_only_rerun_reuses_the_stored_daily_identity(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL", "--timeframes", "daily"), provider=FakeHistory(["AAPL"]), now=NOW)
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL", "--timeframes", "15min"), provider=prov, now=NOW) == 0
    assert {c[1] for c in prov.calls} == {"15min"}
    assert _manifest(dirs["root"], "15min")["tickers"]["AAPL"]["status"] == "ok"


def test_hours_guard_refuses_in_session_unless_forced(dirs):
    cli = load_cli()
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=IN_SESSION) == 1
    assert prov.calls == []
    assert cli.main(_argv(dirs, "AAPL", "--force-hours"), provider=prov, now=IN_SESSION) == 0


def test_disk_guard_refusal_exits_1(dirs, monkeypatch):
    cli = load_cli()

    def refuse(path, needed, **kw):
        raise cli.guards.DiskGuardError("free space would drop below 3 GB")

    monkeypatch.setattr(cli.guards, "check_disk", refuse)
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=NOW) == 1
    assert prov.calls == []


def test_auth_error_stops_the_run_with_exit_2(dirs, capsys):
    cli = load_cli()
    try:
        raise ap.AlpacaAuthError("401 unauthorized")
    except ap.AlpacaAuthError as exc:
        prov = FakeHistory(["AAPL"], error=exc)
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=NOW) == 2
    assert len(prov.calls) == 1
    assert "401" in capsys.readouterr().err


def test_parse_args_defaults_resolve_at_call_time(store_root):
    cli = load_cli()
    args = cli.parse_args([])
    assert args.root == store_root
    assert args.timeframes == ("daily", "hourly", "15min")
    assert (args.start, args.mode, args.force, args.force_hours) == ("2016-01-01", "full", False, False)
    assert cli.parse_args(["--timeframes", "15min,daily"]).timeframes == ("daily", "15min")
    with pytest.raises(SystemExit):
        cli.parse_args(["--timeframes", "1Hour"])
    with pytest.raises(SystemExit):
        cli.parse_args(["--start", "2016-13-01"])


def test_run_summary_render_lists_counts_and_reasons():
    cli = load_cli()
    s = cli.RunSummary(written=["AAPL/daily"], skipped={"GC=F": "skipped: futures"},
                       flagged={"SNDK": "flagged: short-overlap"}, requests=3)
    text = s.render()
    assert text.splitlines()[0] == ("written 1, unchanged 0, refetched 0, skipped 1, "
                                    "flagged 1, requests 3")
    assert "skipped GC=F: skipped: futures" in text and "flagged SNDK: flagged: short-overlap" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_fetch_alpaca_history.py`
Expected: FAIL with `FileNotFoundError` for `scripts/data/fetch_alpaca_history.py`.

- [ ] **Step 3: Write the implementation**

Create `scripts/data/fetch_alpaca_history.py`:

```python
#!/usr/bin/env python3
"""v162: backfill and update the Alpaca history store data/market_data/ (spec §2).

    docker compose run --rm bot python scripts/data/fetch_alpaca_history.py
    docker compose run --rm bot python scripts/data/fetch_alpaca_history.py --mode update
    python scripts/data/fetch_alpaca_history.py --tickers AAPL,SPY --timeframes daily --root /tmp/s

15min (all sessions), hourly (from 30-minute bars, RTH) and daily bars from
the SIP tape, Adjustment.ALL, one calendar year per request. Refuses during
the US regular session (--force-hours overrides) and when free disk would drop
below 3 GB; at most 120 requests a minute beside the live scan. Each file is
written atomically and the manifests are saved per ticker, so a killed run
resumes; --force refetches files that are already complete.

Exit codes: 0 done, 1 a guard refused, 2 Alpaca rejected the key.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "scripts" / "data"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from alpaca_history import fetch, guards, identity, store_io  # noqa: E402
from swingbot.core.marketdata import history_store  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError  # noqa: E402

DEFAULT_START = "2016-01-01"
NO_BARS = "skipped: no Alpaca bars"
# Daily first: the intraday entries copy the daily status and identity.
RUN_ORDER = ("daily", "hourly", "15min")


@dataclass
class RunSummary:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    refetched: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    flagged: dict[str, str] = field(default_factory=dict)
    requests: int = 0

    def render(self) -> str:
        lines = [f"written {len(self.written)}, unchanged {len(self.unchanged)}, "
                 f"refetched {len(self.refetched)}, skipped {len(self.skipped)}, "
                 f"flagged {len(self.flagged)}, requests {self.requests}"]
        lines += [f"  skipped {key}: {why}" for key, why in sorted(self.skipped.items())]
        lines += [f"  flagged {key}: {why}" for key, why in sorted(self.flagged.items())]
        return "\n".join(lines)


@dataclass
class _Run:
    """What one ticker's fetch needs, built once per run."""
    root: Path
    start: str
    timeframes: tuple[str, ...]
    force: bool
    provider: object
    limiter: guards.TokenBucket
    now: datetime
    backtest_dir: Path
    market_dir: Path

    @property
    def stamp(self) -> str:
        return self.now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _csv_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _timeframes(text: str) -> tuple[str, ...]:
    asked = _csv_list(text)
    bad = [tf for tf in asked if tf not in history_store.TIMEFRAMES]
    if bad or not asked:
        raise argparse.ArgumentTypeError(
            f"unknown timeframe(s) {bad or text!r}; choose from {','.join(RUN_ORDER)}")
    return tuple(tf for tf in RUN_ORDER if tf in asked)


def _iso_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from swingbot.core.marketdata import backtest_cache
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframes", type=_timeframes, default="15min,hourly,daily")
    ap.add_argument("--start", type=_iso_date, default=DEFAULT_START)
    ap.add_argument("--tickers", default=None,
                    help="comma list (default: the watchlist plus the market-regime benchmark)")
    ap.add_argument("--mode", choices=("full", "update"), default="full")
    ap.add_argument("--force", action="store_true", help="refetch files that are already complete")
    ap.add_argument("--force-hours", action="store_true",
                    help="run during the US regular session anyway")
    ap.add_argument("--root", type=Path, default=None,
                    help="store root (default: HISTORY_STORE_DIR or data/market_data)")
    ap.add_argument("--backtest-dir", type=Path, default=None,
                    help="identity reference (default: data/backtest_cache)")
    ap.add_argument("--market-dir", type=Path, default=None,
                    help="identity fallback (default: market_data/daily)")
    args = ap.parse_args(argv)
    args.root = args.root or history_store.store_root()
    args.backtest_dir = args.backtest_dir or Path(backtest_cache.CACHE_DIR)
    args.market_dir = args.market_dir or ROOT / "market_data" / "daily"
    return args


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return sorted({t.upper() for t in _csv_list(args.tickers)})
    import fetch_backtest_data
    from swingbot import config
    return fetch_backtest_data.training_tickers(
        fetch_backtest_data.load_watchlist(), config.MARKET_REGIME_TICKER, None)


def _tickers(args: argparse.Namespace) -> list[str]:
    """The run's tickers, resolved once (the watchlist is read a single time)."""
    if getattr(args, "ticker_list", None) is None:
        args.ticker_list = _resolve_tickers(args)
    return args.ticker_list


def make_provider():
    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    if not (config.ALPACA_API_KEY_ID and config.ALPACA_API_SECRET_KEY):
        raise AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    return AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                          config.ALPACA_DATA_FEED_LIVE)


def _make_run(args, provider, limiter, now: datetime) -> _Run:
    return _Run(root=Path(args.root), start=args.start, timeframes=tuple(args.timeframes),
                force=args.force, provider=provider, limiter=limiter, now=now,
                backtest_dir=Path(args.backtest_dir), market_dir=Path(args.market_dir))


def _store_path(root: Path, timeframe: str, ticker: str) -> Path:
    return Path(root) / timeframe / f"{safe_symbol(ticker)}.csv"


def _manifests(root: Path) -> dict[str, dict]:
    return {tf: store_io.load_manifest(root, tf) for tf in history_store.TIMEFRAMES}


def _save(run: _Run, manifests: dict[str, dict], timeframes) -> None:
    for tf in timeframes:
        store_io.save_manifest(run.root, tf, manifests[tf], now=run.now)


def _todo(run: _Run, manifests: dict[str, dict], ticker: str) -> list[str]:
    if run.force:
        return list(run.timeframes)
    return [tf for tf in run.timeframes
            if not store_io.is_complete(manifests[tf]["tickers"].get(ticker), run.start)]


def _record_skip(ticker: str, reason: str, run: _Run, manifests, summary: RunSummary) -> None:
    summary.skipped[ticker] = reason
    stale = [tf for tf in run.timeframes
             if (manifests[tf]["tickers"].get(ticker) or {}).get("status") != reason]
    for tf in stale:
        manifests[tf]["tickers"][ticker] = store_io.skipped_entry(
            reason, start=run.start, fetched_at=run.stamp)
    if stale:
        _save(run, manifests, stale)


def _fetch(run: _Run, ticker: str, timeframe: str) -> pd.DataFrame | None:
    return fetch.fetch_store_frame(run.provider, ticker, timeframe,
                                   date.fromisoformat(run.start), run.now, limiter=run.limiter)


def _daily_identity(ticker: str, run: _Run, manifests, todo: list[str]):
    """(status, identity dict, trimmed daily frame or None). Reuses the stored
    daily verdict when daily itself is not being refetched."""
    entry = manifests["daily"]["tickers"].get(ticker) or {}
    if "daily" not in todo and entry.get("identity") is not None:
        return entry["status"], entry["identity"], None
    daily = _fetch(run, ticker, "daily")
    if daily is None:
        return NO_BARS, None, None
    reference = identity.reference_frame(ticker, backtest_dir=run.backtest_dir,
                                         market_dir=run.market_dir)
    result, trimmed = identity.identity_check(daily, reference)
    if trimmed is None or not len(trimmed):
        return NO_BARS, None, None
    return result.status, result.to_json(), trimmed


def _trim(frame: pd.DataFrame | None, dropped_before: str | None) -> pd.DataFrame | None:
    if frame is not None and dropped_before:
        frame = frame[frame.index >= pd.Timestamp(dropped_before)]
    return frame if frame is not None and len(frame) else None


def _write(ticker, timeframe, frame, run: _Run, manifests, status, ident) -> None:
    sha = store_io.write_frame(frame, _store_path(run.root, timeframe, ticker), timeframe)
    manifests[timeframe]["tickers"][ticker] = store_io.ok_entry(
        frame, timeframe, start=run.start, sha256=sha, identity=ident, status=status,
        fetched_at=run.stamp)


def _write_timeframes(ticker, todo, run: _Run, manifests, verdict, summary) -> None:
    status, ident, daily = verdict
    dropped = (ident or {}).get("dropped_before")
    for tf in todo:
        frame = daily if tf == "daily" else _trim(_fetch(run, ticker, tf), dropped)
        if frame is None:
            manifests[tf]["tickers"][ticker] = store_io.skipped_entry(
                NO_BARS, start=run.start, fetched_at=run.stamp)
            summary.skipped[f"{ticker}/{tf}"] = NO_BARS
            continue
        _write(ticker, tf, frame, run, manifests, status, ident)
        summary.written.append(f"{ticker}/{tf}")


def full_ticker(ticker: str, run: _Run, summary: RunSummary) -> None:
    """Fetch every to-do timeframe of one ticker and save the manifests it changed."""
    manifests = _manifests(run.root)
    reason = identity.skip_reason(ticker)
    if reason:
        _record_skip(ticker, reason, run, manifests, summary)
        return
    todo = _todo(run, manifests, ticker)
    if not todo:
        summary.unchanged += [f"{ticker}/{tf}" for tf in run.timeframes]
        return
    verdict = _daily_identity(ticker, run, manifests, todo)
    if verdict[0] == NO_BARS:
        _record_skip(ticker, NO_BARS, run, manifests, summary)
        return
    if verdict[0] != "ok":
        summary.flagged[ticker] = verdict[0]
    _write_timeframes(ticker, todo, run, manifests, verdict, summary)
    _save(run, manifests, todo)


def run_full(args, provider, limiter: guards.TokenBucket, now: datetime) -> RunSummary:
    run = _make_run(args, provider, limiter, now)
    summary = RunSummary()
    tickers = _tickers(args)
    progress = guards.Progress(len(tickers))
    for ticker in tickers:
        progress.step(ticker)
        full_ticker(ticker, run, summary)
    summary.requests = limiter.calls
    return summary


# AH8 registers "update".
_RUNNERS = {"full": run_full}


def make_limiter() -> guards.TokenBucket:
    """The run's rate limiter (120 a minute). A seam so tests can swap in a
    bucket on a fake clock instead of sleeping 0.5 s per request."""
    return guards.TokenBucket()


def _utc_now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)


def _pending(args) -> int:
    """Tickers that still have a timeframe to fetch (all of them with --force)."""
    tickers = _tickers(args)
    if args.force or args.mode == "update":
        return len(tickers)
    manifests = {tf: store_io.load_manifest(Path(args.root), tf) for tf in args.timeframes}
    return sum(1 for t in tickers
               if any(not store_io.is_complete(manifests[tf]["tickers"].get(t), args.start)
                      for tf in args.timeframes))


def _preflight(args, now: datetime) -> None:
    """Hours guard, then the disk guard. Update mode needs room for one
    ticker's full lockstep refetch (temp file beside the old one) at a time."""
    guards.assert_outside_hours(now, force=args.force_hours)
    Path(args.root).mkdir(parents=True, exist_ok=True)
    years = max((now.date() - date.fromisoformat(args.start)).days / 365.25, 0.0)
    n = 1 if args.mode == "update" else _pending(args)
    guards.check_disk(Path(args.root), guards.estimate_bytes(n, args.timeframes, years))


def main(argv: list[str] | None = None, *, provider=None, now: datetime | None = None) -> int:
    args = parse_args(argv)
    now = _utc_now(now)
    try:
        _preflight(args, now)
        provider = provider or make_provider()
        summary = _RUNNERS[args.mode](args, provider, make_limiter(), now)
    except (guards.HoursGuardError, guards.DiskGuardError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    except AlpacaAuthError as exc:
        print(f"stopped: Alpaca rejected the key ({exc})", file=sys.stderr)
        return 2
    print(summary.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Notes for the implementer:
- AH3's `TokenBucket` holds one token and spaces calls 0.5 s apart on the real clock, so `main` builds it through `make_limiter()`; `load_cli()` in the tests swaps that seam for a bucket on a jumping clock. Never lower `RATE_PER_MINUTE` to speed a test.
- `_daily_identity` returns `NO_BARS` as its status when no daily bar exists; `full_ticker` turns that into a ticker-wide skip.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_fetch_alpaca_history.py`
Expected: PASS (12 tests). Then `python -m radon cc -s -n C $WT/scripts/data/fetch_alpaca_history.py` prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/data/fetch_alpaca_history.py tests/history_store/test_fetch_alpaca_history.py
git -C $WT commit -m "feat(v162): AH7 fetch_alpaca_history CLI, full mode with guards, identity and resume"
```

### Task AH8: `--mode update`: full daily compare, lockstep refetch, append

**Model:** opus — the adjustment-basis guard: a missed rescale silently mixes two price bases inside one file and across timeframes, which corrupts every backtest that reads the store (quant-engineer BLOCKING finding)

**Files:**
- Create: `scripts/data/alpaca_history/update.py`
- Modify: `scripts/data/fetch_alpaca_history.py` (AH7: the import line, the `_RUNNERS` block)
- Test: `tests/history_store/test_update.py`

**Interfaces:**
- Consumes (AH2): `history_store.TIMEFRAMES`, `history_store.INDEX_NAMES`. (AH3): `guards.TokenBucket`, `guards.Progress`. (AH4): `identity.skip_reason`. (AH5): `store_io.load_manifest`, `store_io.save_manifest(root, tf, manifest, *, now)`, `store_io.write_frame(frame, path, tf) -> sha256`, `store_io.ok_entry(...)`, `store_io.skipped_entry(reason, *, start, fetched_at)`. (AH6): `fetch.fetch_store_frame`. (AH7): `RunSummary`, `_Run`, `_make_run`, `full_ticker`, `_tickers`, `_store_path`, `_RUNNERS`, `NO_BARS`; test helpers `FakeHistory`, `NOW`, `DAYS`, `load_cli`, `dirs`, `_argv`, `_manifest` from `tests/history_store/test_fetch_alpaca_history.py`.
- Produces (ledger AH8): `BASIS_RTOL = 1e-6`; `basis_changed(stored, fresh) -> bool`; `new_bars(stored, fresh) -> pd.DataFrame`; `update_ticker(ticker, *, root, provider, limiter, now, timeframes, start) -> str` (`"unchanged"`, `"appended"`, `"refetched"`); `run_update(args, provider, limiter, now) -> RunSummary` (in the CLI module, beside `run_full`, because `RunSummary` lives there). Also `update.NO_BARS` (equal to the CLI's), `update.WRITE_ORDER = ("15min", "hourly", "daily")`, `update.read_stored(path, timeframe) -> pd.DataFrame | None`. AH20's cron runs `--mode update`.

**Rules this task freezes (spec §2 "`--mode update` never mixes adjustment bases", Acceptance 4):**
- **Which path a ticker takes.** A ticker with a `skip_reason`, or without a stored file and a non-null `sha256` entry for `daily` and every requested timeframe, goes through AH7's `full_ticker` (a new watchlist name is backfilled, a skip is re-recorded only when it changed). Every other ticker, flagged ones included, goes through `update_ticker`.
- **The compare.** `update_ticker` refetches the ticker's **full** daily history from the daily entry's `start`, trimmed by the stored `identity.dropped_before`. The basis has changed when a stored daily date is missing from the fresh frame, when a close is NaN on one side only, or when any `|fresh − stored| / |stored| > BASIS_RTOL` over every stored date. A split shows up as a step in that ratio and trips the same test.
- **Lockstep refetch.** On a basis change, every timeframe of the ticker that has a stored file (whatever `--timeframes` says) is refetched in full from its entry's `start` and replaced. **All frames are fetched before any write, and they are written in `WRITE_ORDER`, daily last.** A run killed mid-refetch therefore keeps the old daily file, and the next update sees the change again and refetches all three. No file ever holds two bases. A timeframe that comes back empty on refetch has its old file deleted and its entry set to `skipped: no Alpaca bars` (an old-basis file is never kept).
- **Append.** Without a basis change, each requested timeframe appends the bars strictly after its last stored index: daily from the fresh daily frame, intraday from a fetch starting at the date of the last stored bar. Entries keep their `start`, daily `status` and `identity`; `rows`, `last`, `sha256` and `fetched_at` are refreshed.
- **Nothing to do writes nothing.** No data file, no manifest, no `updated_at` change. An empty daily answer from Alpaca leaves the ticker untouched (`"unchanged"`): a transient empty response is never read as a vanished history.
- **Summary.** `unchanged` → every requested timeframe under `unchanged`; `appended` → under `written`; `refetched` → all three under `refetched`; a flagged ticker also lands in `flagged`.

- [ ] **Step 1: Write the failing test**

Create `tests/history_store/test_update.py`:

```python
"""v162 AH8: --mode update -- an unchanged day writes nothing, a tiny rescale
refetches all three timeframes together, new bars append."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from alpaca_history import store_io, update
from tests.history_store.test_fetch_alpaca_history import (  # noqa: F401  (dirs is a fixture)
    DAYS,
    NOW,
    FakeHistory,
    _argv,
    _manifest,
    dirs,
    load_cli,
)

UTC = timezone.utc
LATER = datetime(2024, 6, 8, 12, 0, tzinfo=UTC)          # the next Saturday
LONGER = pd.bdate_range("2023-01-02", "2024-06-07")


def _daily(closes, days) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": 1.0}, index=pd.DatetimeIndex(days, name="Date"))


def _snapshot(root):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def _backfill(cli, dirs, tickers="AAPL"):
    assert cli.main(_argv(dirs, tickers), provider=FakeHistory(tickers.split(",")), now=NOW) == 0


# --- pure helpers --------------------------------------------------------------

DAYS5 = pd.bdate_range("2024-01-01", periods=5)


def test_identical_history_is_the_same_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    assert update.basis_changed(stored, stored.copy()) is False


def test_a_uniform_rescale_far_below_a_hundredth_of_a_percent_is_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    fresh = stored.copy()
    fresh["Close"] *= 1 - 5e-6
    assert update.basis_changed(stored, fresh) is True


def test_float_noise_under_the_tolerance_is_not_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    fresh = stored.copy()
    fresh["Close"] *= 1 + 1e-8
    assert update.basis_changed(stored, fresh) is False


def test_a_vanished_stored_row_or_one_sided_nan_is_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    assert update.basis_changed(stored, stored.drop(DAYS5[2])) is True
    fresh = stored.copy()
    fresh.loc[DAYS5[1], "Close"] = np.nan
    assert update.basis_changed(stored, fresh) is True


def test_a_split_step_is_a_new_basis_and_new_rows_alone_are_not():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    split = stored.copy()
    split.loc[DAYS5[:3], "Close"] /= 2
    assert update.basis_changed(stored, split) is True
    longer = _daily([10.0, 10.5, 11.0, 11.5, 12.0, 12.5], pd.bdate_range("2024-01-01", periods=6))
    assert update.basis_changed(stored, longer) is False
    assert update.basis_changed(None, longer) is False


def test_new_bars_are_strictly_after_the_last_stored_bar():
    stored = _daily([1.0, 2.0, 3.0], DAYS5[:3])
    fresh = _daily([1.0, 2.0, 3.0, 4.0, 5.0], DAYS5)
    assert list(update.new_bars(stored, fresh).index) == list(DAYS5[3:])
    none = update.new_bars(stored, stored.copy())
    assert none.empty and list(none.columns) == list(stored.columns)
    assert len(update.new_bars(None, fresh)) == 5


def test_the_no_bars_status_matches_the_cli():
    assert update.NO_BARS == load_cli().NO_BARS
    assert update.WRITE_ORDER[-1] == "daily"


# --- through the CLI ------------------------------------------------------------

def test_an_unchanged_day_writes_nothing(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs, "AAPL,SNDK")
    before = _snapshot(dirs["root"])
    prov = FakeHistory(["AAPL", "SNDK"])
    assert cli.main(_argv(dirs, "AAPL,SNDK", "--mode", "update"), provider=prov, now=NOW) == 0
    assert prov.calls, "update must still compare against a fresh daily history"
    assert _snapshot(dirs["root"]) == before
    out = capsys.readouterr().out
    assert "unchanged 6" in out and "flagged SNDK" in out


def test_a_tiny_dividend_rescale_refetches_all_three_timeframes(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs)
    scale = 1 - 5e-6                       # 0.0005 %: far below 0.01 %
    prov = FakeHistory(["AAPL"], scale=scale)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=NOW) == 0
    root = dirs["root"]
    daily = pd.read_csv(root / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert daily["Close"].iloc[0] == pytest.approx(100.0 * scale, rel=1e-12)
    for tf in ("hourly", "15min"):
        frame = pd.read_csv(root / tf / "AAPL.csv", index_col="Datetime", parse_dates=True)
        assert frame["Close"].eq(frame["Close"].iloc[0]).all()           # one basis per file
        assert frame["Close"].iloc[0] == pytest.approx(150.0 * scale, rel=1e-12)
        entry = _manifest(root, tf)["tickers"]["AAPL"]
        assert entry["sha256"] == store_io.sha256_file(root / tf / "AAPL.csv")
    assert "refetched 3" in capsys.readouterr().out


def test_a_refetch_writes_daily_last(dirs, monkeypatch):
    cli = load_cli()
    _backfill(cli, dirs)
    order: list[str] = []
    real = store_io.write_frame

    def spy(frame, path, timeframe):
        order.append(timeframe)
        return real(frame, path, timeframe)

    monkeypatch.setattr(store_io, "write_frame", spy)
    cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=FakeHistory(["AAPL"], scale=0.5),
             now=NOW)
    assert order == ["15min", "hourly", "daily"]


def test_a_killed_refetch_is_redone_by_the_next_update(dirs, monkeypatch):
    cli = load_cli()
    _backfill(cli, dirs)
    real = store_io.write_frame

    def die_on_daily(frame, path, timeframe):
        if timeframe == "daily":
            raise KeyboardInterrupt
        return real(frame, path, timeframe)

    monkeypatch.setattr(store_io, "write_frame", die_on_daily)
    with pytest.raises(KeyboardInterrupt):
        cli.main(_argv(dirs, "AAPL", "--mode", "update"),
                 provider=FakeHistory(["AAPL"], scale=0.5), now=NOW)
    monkeypatch.setattr(store_io, "write_frame", real)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"),
                    provider=FakeHistory(["AAPL"], scale=0.5), now=NOW) == 0
    daily = pd.read_csv(dirs["root"] / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert daily["Close"].iloc[0] == pytest.approx(50.0)


def test_new_sessions_append_to_every_timeframe(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = FakeHistory(["AAPL"], days=LONGER)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=LATER) == 0
    root = dirs["root"]
    daily = pd.read_csv(root / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert len(daily) == len(DAYS) + 5 and daily.index.is_unique
    assert len(pd.read_csv(root / "15min" / "AAPL.csv")) == 256
    assert len(pd.read_csv(root / "hourly" / "AAPL.csv")) == 28
    entry = _manifest(root, "daily")["tickers"]["AAPL"]
    assert entry["last"] == "2024-06-07" and entry["start"] == "2023-01-01"
    assert entry["rows"] == len(daily)
    assert "written 3" in capsys.readouterr().out


def test_an_empty_daily_answer_leaves_the_store_untouched(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    before = _snapshot(dirs["root"])
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=FakeHistory([]), now=NOW) == 0
    assert _snapshot(dirs["root"]) == before


def test_a_new_watchlist_ticker_is_backfilled_by_update(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = FakeHistory(["AAPL", "NVDA"])
    assert cli.main(_argv(dirs, "AAPL,NVDA", "--mode", "update"), provider=prov, now=NOW) == 0
    for tf in ("daily", "hourly", "15min"):
        assert (dirs["root"] / tf / "NVDA.csv").exists()
        assert _manifest(dirs["root"], tf)["tickers"]["NVDA"]["status"] == "flagged: no-reference"
```

`test_a_new_watchlist_ticker_is_backfilled_by_update` relies on `dirs` writing no reference for NVDA (AH7's fixture), so its identity is `flagged: no-reference` and it is still written.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_update.py`
Expected: FAIL with `ImportError: cannot import name 'update' from 'alpaca_history'`.

- [ ] **Step 3: Write `update.py`**

Create `scripts/data/alpaca_history/update.py`:

```python
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
        frame = fetch.fetch_store_frame(self.provider, self.ticker, timeframe, since, self.now,
                                        limiter=self.limiter)
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
```

- [ ] **Step 4: Wire `--mode update` into the CLI**

In `scripts/data/fetch_alpaca_history.py`, change the package import line to:

```python
from alpaca_history import fetch, guards, identity, store_io, update  # noqa: E402
```

Replace the AH7 block

```python
# AH8 registers "update".
_RUNNERS = {"full": run_full}
```

with:

```python
def _updatable(run: _Run, ticker: str) -> bool:
    """True when daily and every requested timeframe already have a stored file."""
    manifests = {tf: store_io.load_manifest(run.root, tf) for tf in history_store.TIMEFRAMES}
    for tf in {"daily", *run.timeframes}:
        entry = manifests[tf]["tickers"].get(ticker) or {}
        if not entry.get("sha256") or not _store_path(run.root, tf, ticker).exists():
            return False
    return True


_OUTCOME_FIELD = {"unchanged": "unchanged", "appended": "written", "refetched": "refetched"}


def _update_one(ticker: str, run: _Run, summary: RunSummary) -> None:
    if identity.skip_reason(ticker) or not _updatable(run, ticker):
        full_ticker(ticker, run, summary)
        return
    daily = store_io.load_manifest(run.root, "daily")["tickers"][ticker]
    outcome = update.update_ticker(
        ticker, root=run.root, provider=run.provider, limiter=run.limiter, now=run.now,
        timeframes=run.timeframes, start=date.fromisoformat(daily["start"]))
    tfs = history_store.TIMEFRAMES if outcome == "refetched" else run.timeframes
    getattr(summary, _OUTCOME_FIELD[outcome]).extend(f"{ticker}/{tf}" for tf in tfs)
    if daily["status"] != "ok":
        summary.flagged[ticker] = daily["status"]


def run_update(args, provider, limiter: guards.TokenBucket, now: datetime) -> RunSummary:
    run = _make_run(args, provider, limiter, now)
    summary = RunSummary()
    tickers = _tickers(args)
    progress = guards.Progress(len(tickers))
    for ticker in tickers:
        progress.step(ticker)
        _update_one(ticker, run, summary)
    summary.requests = limiter.calls
    return summary


_RUNNERS = {"full": run_full, "update": run_update}
```

`make_limiter()` stays where AH7 put it (after the replaced block).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_update.py`
Expected: PASS (14 tests).
Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_fetch_alpaca_history.py`
Expected: PASS (12 tests, AH7 unchanged).
Then `python -m radon cc -s -n C $WT/scripts/data/alpaca_history/update.py $WT/scripts/data/fetch_alpaca_history.py` prints nothing.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/data/alpaca_history/update.py scripts/data/fetch_alpaca_history.py tests/history_store/test_update.py
git -C $WT commit -m "feat(v162): AH8 update mode -- full daily compare, lockstep refetch daily-last, append"
```

