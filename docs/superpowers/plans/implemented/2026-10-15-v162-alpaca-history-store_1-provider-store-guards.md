# v162 Alpaca history store, part 1: provider method, read seam, guards, identity (AH1–AH4; AH5 is in `2026-10-15-v162-alpaca-history-store_1b-store-io.md`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task AH3:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_1-provider-store-guards.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md). Its Global Constraints, Parallelisation, Shared contracts and Task ledger bind every task below.
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)

Paths: `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-15-v162-alpaca-history-store` (the branch). Never `cd`. Use absolute paths and `git -C $WT`.

**Import convention for the backfill package (AH3–AH5, and part 2):** `scripts/data/alpaca_history/` is imported as the top-level package `alpaca_history`, with `$WT/scripts/data` on `sys.path`. CLI scripts insert that path themselves. Tests get it from `tests/history_store/conftest.py` (AH2), which also inserts `$WT/scripts/ops` for `market_cache_repair`. Modules inside the package use absolute imports (`from alpaca_history import guards`), so a script and a test import them the same way. `swingbot` is importable because pytest's rootdir is the repo root.

# Phase A: provider method, converters, read seam

### Task AH1: Provider `history_bars` and store converters

**Model:** sonnet — one bounded provider method and two pure frame converters with faked-client tests; the timezone rule is spelled out below.

**Files:**
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py` (add `HISTORY_TIMEFRAMES` under `ROWS_PER_PAGE` at :23, add `AlpacaProvider.history_bars` after `intraday_bars` at :106-112)
- Modify: `swingbot/core/marketdata/providers/base.py` (append `to_store_intraday`, `to_store_hourly` after `to_yf_hourly` at :44-53)
- Test: `tests/marketdata/test_alpaca_provider.py` (append)
- Test: `tests/marketdata/test_providers_base.py` (append)

**Interfaces:**
- Consumes: existing `_frames_from_raw(raw) -> {alpaca_symbol: DataFrame}` (alpaca_provider.py:30, lowercase `open..volume`, tz-aware UTC index named `timestamp`), `AlpacaProvider._call(method, req, client)` (:85; 401/403 → `AlpacaAuthError`, anything else → `AlpacaMiss` with the original exception on `__cause__`), `SIP_DELAY` (:18), `to_alpaca_symbol`, `to_yf_hourly`, `_yf_columns`, `NY` (base.py).
- Produces:
  - `alpaca_provider.HISTORY_TIMEFRAMES: dict[str, TimeFrame]`, keys `"15min"`, `"30min"`, `"1d"`.
  - `AlpacaProvider.history_bars(self, ticker: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame | None`. It returns the raw Alpaca frame (lowercase `open..volume`, tz-aware UTC index) or `None` when there are no bars. `end` is clamped to `now − SIP_DELAY`, and `start >= end` after the clamp returns `None` without a request. It raises `AlpacaMiss`/`AlpacaAuthError`, and `ValueError` on an unknown timeframe (before any request). `start`/`end` must be tz-aware.
  - `base.to_store_intraday(df: pd.DataFrame) -> pd.DataFrame`: raw UTC frame → `Open..Volume` float64, naive America/New_York wall-clock index named `Datetime`, every session kept, duplicates dropped (last wins), sorted.
  - `base.to_store_hourly(df30: pd.DataFrame) -> pd.DataFrame`: `to_yf_hourly(df30)` with the index made naive (wall-clock kept), named `Datetime`.

**Why naive wall-clock is safe:** the store keeps bars from 04:00 to 20:00 ET. The only ambiguous or missing wall-clock hours (the 01:00–02:00 fall-back hour and the 02:00–03:00 spring-forward gap) are outside that window, so dropping the zone loses nothing and every stored time is unique. A tz-aware CSV with mixed DST offsets would parse back as object/UTC and break `data_store.load_normalized` (brief § Traps), which is why the converters strip the zone *before* any write.

- [ ] **Step 0: Create the worktree (once, for the whole plan)**

Load the `worktree-lifecycle` skill and follow it. The commands it ends with for this plan:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store -b 2026-10-15-v162-alpaca-history-store main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store log --oneline -1
```

Expected: the last command prints the `main` HEAD that carries this plan (the v162 index commit or later). Every later path in this plan is under `$WT`.

- [ ] **Step 1: Write the failing provider tests**

Append to `$WT/tests/marketdata/test_alpaca_provider.py`:

```python
# --- v162: history_bars, the history store's one fetch path -------------------

H_START = datetime(2016, 1, 1, tzinfo=timezone.utc)
H_END = datetime(2017, 1, 1, tzinfo=timezone.utc)


def test_history_bars_requests_one_symbol_sip_all_over_the_given_window():
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).history_bars("AAPL", "15min", H_START, H_END)
    req = c.requests[0]
    assert req.symbol_or_symbols == ["AAPL"]
    assert req.timeframe.value == "15Min"
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    # alpaca-py's request model converts datetimes to UTC and drops tzinfo
    assert req.start == datetime(2016, 1, 1) and req.end == datetime(2017, 1, 1)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert str(out.index.tz) == "UTC"


@pytest.mark.parametrize("timeframe,wire", [("15min", "15Min"), ("30min", "30Min"), ("1d", "1Day")])
def test_history_bars_timeframes(timeframe, wire):
    c = FakeClient(bars=_barset(["AAPL"]))
    _prov(c).history_bars("AAPL", timeframe, H_START, H_END)
    assert c.requests[0].timeframe.value == wire


def test_history_bars_unknown_timeframe_raises_before_any_request():
    c = FakeClient(bars=_barset(["AAPL"]))
    with pytest.raises(ValueError, match="1Hour"):
        _prov(c).history_bars("AAPL", "1Hour", H_START, H_END)
    assert c.requests == []


def test_history_bars_clamps_end_to_the_sip_delay():
    c = FakeClient(bars=_barset(["AAPL"]))
    _prov(c).history_bars("AAPL", "1d", H_START, NOW + pd.Timedelta(days=30))
    assert c.requests[0].end == (NOW - ap.SIP_DELAY).replace(tzinfo=None)


def test_history_bars_window_entirely_inside_the_delay_is_none_without_a_request():
    c = FakeClient(bars=_barset(["AAPL"]))
    start = NOW - pd.Timedelta(minutes=5)
    assert _prov(c).history_bars("AAPL", "15min", start, NOW) is None
    assert c.requests == []


@pytest.mark.parametrize("bars", [{}, {"AAPL": []}, None])
def test_history_bars_no_bars_is_none(bars):
    assert _prov(FakeClient(bars=bars)).history_bars("AAPL", "1d", H_START, H_END) is None


def test_history_bars_class_share_uses_the_dotted_symbol():
    c = FakeClient(bars=_barset(["BRK.B"]))
    out = _prov(c).history_bars("BRK-B", "1d", H_START, H_END)
    assert c.requests[0].symbol_or_symbols == ["BRK.B"]
    assert out is not None and len(out) == 2


def test_history_bars_auth_error_propagates():
    err = Exception("forbidden"); err.status_code = 401
    with pytest.raises(ap.AlpacaAuthError):
        _prov(FakeClient(exc=err)).history_bars("AAPL", "1d", H_START, H_END)


def test_history_bars_rate_limit_is_a_miss_with_the_status_on_the_cause():
    err = Exception("too many requests"); err.status_code = 429
    with pytest.raises(ap.AlpacaMiss) as info:
        _prov(FakeClient(exc=err)).history_bars("AAPL", "1d", H_START, H_END)
    assert not isinstance(info.value, ap.AlpacaAuthError)
    assert info.value.__cause__.status_code == 429
```

- [ ] **Step 2: Write the failing converter tests**

Append to `$WT/tests/marketdata/test_providers_base.py`:

```python
# --- v162: history store converters (naive America/New_York wall-clock) -------

def _raw(utc_stamps):
    idx = pd.DatetimeIndex(utc_stamps, tz="UTC", name="timestamp")
    n = len(idx)
    return pd.DataFrame({"open": [1.0] * n, "high": [2.0] * n, "low": [0.5] * n,
                         "close": [1.5] * n, "volume": [100.0] * n,
                         "trade_count": [5] * n, "vwap": [1.4] * n}, index=idx)


def _hhmm(index):
    return [t.strftime("%Y-%m-%d %H:%M") for t in index]


def test_to_store_intraday_is_naive_new_york_wall_clock_across_both_dst_changes():
    # 09:30 ET is 14:30 UTC under EST and 13:30 UTC under EDT.
    # 2026: DST starts Sun 2026-03-08 and ends Sun 2026-11-01.
    out = base.to_store_intraday(_raw([
        "2026-03-06 14:30",   # Fri, EST
        "2026-03-09 13:30",   # Mon, EDT
        "2026-10-30 13:30",   # Fri, EDT
        "2026-11-02 14:30",   # Mon, EST
    ]))
    assert out.index.tz is None
    assert out.index.name == "Datetime"
    assert _hhmm(out.index) == ["2026-03-06 09:30", "2026-03-09 09:30",
                                "2026-10-30 09:30", "2026-11-02 09:30"]


def test_to_store_intraday_keeps_extended_hours():
    # 04:00 EDT = 08:00 UTC; the 19:45 EDT bar starts at 23:45 UTC
    out = base.to_store_intraday(_raw(["2026-03-09 08:00", "2026-03-09 23:45"]))
    assert _hhmm(out.index) == ["2026-03-09 04:00", "2026-03-09 19:45"]


def test_to_store_intraday_shape_sorted_and_deduplicated():
    raw = _raw(["2026-03-09 14:00", "2026-03-09 13:45", "2026-03-09 14:00"])
    raw.iloc[2, raw.columns.get_loc("close")] = 9.0       # the later duplicate wins
    out = base.to_store_intraday(raw)
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert all(out.dtypes == "float64")
    assert _hhmm(out.index) == ["2026-03-09 09:45", "2026-03-09 10:00"]
    assert out["Close"].iloc[-1] == 9.0


def test_to_store_intraday_treats_a_naive_index_as_utc():
    raw = _raw(["2026-03-09 13:30"])
    raw.index = raw.index.tz_localize(None)
    assert _hhmm(base.to_store_intraday(raw).index) == ["2026-03-09 09:30"]


def _thirty_minute_session(day):
    idx = pd.date_range(f"{day} 09:00", f"{day} 16:00", freq="30min",
                        tz=base.NY).tz_convert("UTC")
    return pd.DataFrame({"open": range(len(idx)), "high": range(1, len(idx) + 1),
                         "low": range(len(idx)), "close": range(len(idx)),
                         "volume": [10] * len(idx)}, index=idx).astype(float)


@pytest.mark.parametrize("day", ["2026-03-06", "2026-03-09"])   # EST, then EDT
def test_to_store_hourly_is_naive_on_the_0930_grid(day):
    out = base.to_store_hourly(_thirty_minute_session(day))
    assert out.index.tz is None and out.index.name == "Datetime"
    assert [t.strftime("%H:%M") for t in out.index] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    assert {t.strftime("%Y-%m-%d") for t in out.index} == {day}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: FAIL. The new tests fail with `AttributeError: 'AlpacaProvider' object has no attribute 'history_bars'`, and the existing tests still pass.

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_providers_base.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.marketdata.providers.base' has no attribute 'to_store_intraday'`.

- [ ] **Step 4: Implement the provider method**

In `$WT/swingbot/core/marketdata/providers/alpaca_provider.py`, directly under `ROWS_PER_PAGE = 10_000 ...` (line 23), add:

```python
#: v162 history store timeframes -> Alpaca bar size. Native 1Hour bars are
#: clock-aligned and never used: hourly is rebuilt from 30-minute bars.
HISTORY_TIMEFRAMES = {
    "15min": TimeFrame(15, TimeFrameUnit.Minute),
    "30min": TimeFrame(30, TimeFrameUnit.Minute),
    "1d": TimeFrame.Day,
}
```

and, as a method of `AlpacaProvider` directly after `intraday_bars` (after line 112), add:

```python
    def history_bars(self, ticker, timeframe, start, end):
        """v162: one symbol's raw bars over [start, end] for the history store.

        SIP feed, Adjustment.ALL, `end` clamped to now - SIP_DELAY (the free
        plan's delay). alpaca-py pages inside the one call, so callers bound
        memory by asking for one calendar year at a time. Returns the raw
        frame (lowercase open..volume, tz-aware UTC index) or None when there
        are no bars. Live callers keep using _bars; this method is research-only.
        """
        bar_size = HISTORY_TIMEFRAMES.get(timeframe)
        if bar_size is None:
            raise ValueError(f"unknown history timeframe {timeframe!r}; "
                             f"expected one of {sorted(HISTORY_TIMEFRAMES)}")
        end = min(end, self._now() - SIP_DELAY)
        if start >= end:
            return None
        symbol = to_alpaca_symbol(ticker)
        req = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=bar_size,
                               start=start, end=end,
                               feed=DataFeed.SIP, adjustment=Adjustment.ALL)
        raw = self._call("get_stock_bars", req, self._bars_client) or {}
        df = _frames_from_raw(raw).get(symbol)
        return None if df is None or df.empty else df
```

- [ ] **Step 5: Implement the converters**

Append to `$WT/swingbot/core/marketdata/providers/base.py`:

```python
def to_store_intraday(df: pd.DataFrame) -> pd.DataFrame:
    """v162 history store: raw Alpaca intraday bars (UTC) as naive
    America/New_York wall-clock bars labelled at the bar start, index
    `Datetime`. Every session is kept (04:00-20:00 ET); readers filter.
    A naive input index is taken as UTC. Duplicates (a year window's
    inclusive end) keep the last bar."""
    out = _yf_columns(df)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out.index = idx.tz_convert(NY).tz_localize(None)
    out.index.name = "Datetime"
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def to_store_hourly(df30: pd.DataFrame) -> pd.DataFrame:
    """v162 history store: `to_yf_hourly` (09:30-anchored, regular hours,
    the last bar 15:30-16:00 is a half-hour) with the New York index made
    naive. Wall-clock times are kept as they are."""
    out = to_yf_hourly(df30)
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    out.index.name = "Datetime"
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_providers_base.py`
Expected: PASS, 0 failed.

- [ ] **Step 7: Check complexity and that live callers are untouched**

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/providers/alpaca_provider.py $WT/swingbot/core/marketdata/providers/base.py`
Expected: no output.

Run: `git -C $WT diff -U0 main -- swingbot/core/marketdata/providers/alpaca_provider.py | grep -n "^-"`
Expected: only the `--- a/...` header line. `_bars`, `daily_bars` and `intraday_bars` have no removed lines.

Run: `python $WT/scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: PASS (the router still sees the same provider surface).

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/marketdata/providers/alpaca_provider.py swingbot/core/marketdata/providers/base.py tests/marketdata/test_alpaca_provider.py tests/marketdata/test_providers_base.py
git -C $WT commit -m "feat(v162): AlpacaProvider.history_bars and naive-NY store converters

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on `2026-10-15-v162-alpaca-history-store`. The main-tree status shows no file this task touched.

### Task AH2: `history_store` read seam, `tests/history_store/`, suite `history-store`, DST round trip

**Model:** sonnet — a small read-only module with path, manifest and session rules fully specified here, plus a new test directory and suite entry.

**Files:**
- Create: `swingbot/core/marketdata/history_store.py`
- Create: `tests/history_store/__init__.py`
- Create: `tests/history_store/conftest.py`
- Create: `tests/history_store/test_history_store.py`
- Modify: `tests/suites.toml` (append `[suites.history-store]` after `[suites.config]`, the last table, at :73-75)

**Interfaces:**
- Consumes: `base.to_store_intraday`, `base.to_store_hourly` (AH1), existing `base.to_yf_daily` (base.py:37), `data_store.safe_symbol(ticker) -> str` (data_store.py:104, upper-case + strip, `=`/`^`/`/` → `_`), `config.DATA_DIR` (absolute, `swingbot/config.py:64`).
- Produces (binding for AH4–AH25):
  - `TIMEFRAMES = ("15min", "hourly", "daily")`; `INDEX_NAMES = {"15min": "Datetime", "hourly": "Datetime", "daily": "Date"}`; `SESSIONS = ("rth", "all")`; `MANIFEST_NAME = "_manifest.json"`; `OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]`; `ENV_VAR = "HISTORY_STORE_DIR"`.
  - `class MissingStoreError(RuntimeError)`.
  - `store_root() -> Path`. It returns env `HISTORY_STORE_DIR` when set and non-blank, read on **every call** and never at import. A relative value resolves against `Path(config.DATA_DIR).parent`, as `backtest_cache._cache_dir` does. Otherwise it returns `Path(config.DATA_DIR) / "market_data"`.
  - `timeframe_dir(timeframe: str) -> Path` (`ValueError` on a timeframe outside `TIMEFRAMES`); `file_path(ticker: str, timeframe: str) -> Path` (`<dir>/<safe_symbol>.csv`); `manifest_path(timeframe: str) -> Path` (`<dir>/_manifest.json`). None of them creates a directory.
  - `manifest(timeframe: str) -> dict | None` (`None` when the file is absent; a corrupt file raises `json.JSONDecodeError`, never a silent `None`).
  - `require_manifest(timeframe: str) -> dict` (raises `MissingStoreError` whose message contains the missing path and names the rollback `TRAINING_DATA_SOURCE=yfinance`).
  - `ticker_status(timeframe: str, ticker: str) -> str`. It returns the manifest entry's `status`, or `"missing"` when the manifest, the entry or its `status` is absent. Manifest keys are the upper-case watchlist ticker (`BRK-B`), not the safe file name.
  - `load(ticker: str, timeframe: str, session: str = "rth") -> pd.DataFrame | None`. The result has `OHLCV_COLUMNS` as float64 and a naive `DatetimeIndex` named per `INDEX_NAMES`, sorted, with duplicates dropped (last wins). For `15min`, `"rth"` keeps bars starting 09:30–15:45 and `"all"` keeps every bar. `session` is validated but has no effect for `hourly`/`daily`. The function returns `None` for a missing file or an empty result. It raises `ValueError` on a bad timeframe or session, or on a tz-aware stored index.
  - Fixture `store_root(tmp_path, monkeypatch) -> Path`: creates `tmp_path/"market_data"`, sets `HISTORY_STORE_DIR` to it, returns it.
  - `tests/history_store/conftest.py` appends `ROOT/"scripts"/"data"` and `ROOT/"scripts"/"ops"` to `sys.path`.
  - Suite `[suites.history-store]`, `paths = ["tests/history_store/"]`.

- [ ] **Step 1: Create the test directory, its conftest and the suite entry**

Create `$WT/tests/history_store/__init__.py` as an empty file.

Create `$WT/tests/history_store/conftest.py`:

```python
"""tests/history_store/: the v162 Alpaca history store.

Puts scripts/data (the alpaca_history package and the data CLIs) and
scripts/ops (market_cache_repair) on sys.path -- appended, so nothing already
importable is shadowed -- and gives every test its own empty store root.
No test here reads the real data/market_data/ or touches the network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "scripts" / "data", ROOT / "scripts" / "ops"):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    """An empty history store under tmp_path, selected through HISTORY_STORE_DIR."""
    root = tmp_path / "market_data"
    root.mkdir()
    monkeypatch.setenv("HISTORY_STORE_DIR", str(root))
    return root
```

Append to `$WT/tests/suites.toml` (after the `[suites.config]` table, with one blank line before it):

```toml

[suites.history-store]
description = "v162 Alpaca history store: read seam, backfill, update, training switch"
paths = ["tests/history_store/"]
```

`tooling` is close to `max_tests = 1200`, so the history-store tests get their own suite (`docs/claude/testing-cost.md` § Test suites). CI builds one job per suite from this file, so no workflow edit is needed.

- [ ] **Step 2: Write the failing tests**

Create `$WT/tests/history_store/test_history_store.py`:

```python
"""history_store is the only reader of data/market_data/: paths, manifests,
the session filter, and the one index convention (naive New York wall-clock,
bar start) pinned by a fetch-frame -> CSV -> load round trip across both 2026
DST changes."""
import json
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store as hs
from swingbot.core.marketdata.providers import base


def _write(frame, ticker, timeframe):
    path = hs.file_path(ticker, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label=hs.INDEX_NAMES[timeframe])
    return path


def _manifest(root, timeframe, tickers):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    (folder / hs.MANIFEST_NAME).write_text(json.dumps(
        {"timeframe": timeframe, "feed": "sip", "adjustment": "all", "tickers": tickers}))


def _daily(dates, close=10.0):
    idx = pd.DatetimeIndex(pd.to_datetime(dates), name="Date")
    n = len(idx)
    return pd.DataFrame({"Open": [close] * n, "High": [close + 1] * n, "Low": [close - 1] * n,
                         "Close": [close] * n, "Volume": [1000.0] * n}, index=idx)


# --- paths --------------------------------------------------------------------

def test_default_root_is_data_market_data(monkeypatch):
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)
    assert hs.store_root() == Path(config.DATA_DIR) / "market_data"


def test_env_override_is_read_on_every_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "a"))
    assert hs.store_root() == tmp_path / "a"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "b"))
    assert hs.store_root() == tmp_path / "b"


def test_relative_override_resolves_against_the_project_root(monkeypatch):
    monkeypatch.setenv("HISTORY_STORE_DIR", "data/elsewhere")
    assert hs.store_root() == Path(config.DATA_DIR).parent / "data" / "elsewhere"


def test_unknown_timeframe_is_rejected(store_root):
    with pytest.raises(ValueError, match="1h"):
        hs.timeframe_dir("1h")


def test_file_names_use_safe_symbol(store_root):
    assert hs.file_path("brk-b", "daily") == store_root / "daily" / "BRK-B.csv"
    assert hs.file_path("GC=F", "15min") == store_root / "15min" / "GC_F.csv"


def test_paths_create_no_directories(store_root):
    hs.file_path("AAPL", "hourly")
    hs.manifest_path("hourly")
    assert not (store_root / "hourly").exists()


# --- manifests ----------------------------------------------------------------

def test_missing_manifest_is_none_and_require_raises_naming_the_path(store_root):
    assert hs.manifest("daily") is None
    with pytest.raises(hs.MissingStoreError) as info:
        hs.require_manifest("daily")
    assert str(store_root / "daily" / "_manifest.json") in str(info.value)
    assert "TRAINING_DATA_SOURCE=yfinance" in str(info.value)


def test_manifest_is_read_as_is(store_root):
    _manifest(store_root, "daily", {"AAPL": {"status": "ok"}})
    assert hs.require_manifest("daily")["tickers"] == {"AAPL": {"status": "ok"}}


def test_corrupt_manifest_raises(store_root):
    (store_root / "daily").mkdir()
    (store_root / "daily" / "_manifest.json").write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        hs.manifest("daily")


def test_ticker_status(store_root):
    assert hs.ticker_status("daily", "AAPL") == "missing"          # no manifest
    _manifest(store_root, "daily", {"AAPL": {"status": "ok"},
                                    "SNDK": {"status": "flagged: short-overlap"},
                                    "ODD": {}})
    assert hs.ticker_status("daily", "aapl") == "ok"
    assert hs.ticker_status("daily", "SNDK") == "flagged: short-overlap"
    assert hs.ticker_status("daily", "ODD") == "missing"
    assert hs.ticker_status("daily", "MSFT") == "missing"


# --- load ---------------------------------------------------------------------

def test_load_missing_file_is_none(store_root):
    assert hs.load("AAPL", "daily") is None


def test_load_daily_shape(store_root):
    _write(_daily(["2016-01-05", "2016-01-04", "2016-01-05"]), "AAPL", "daily")
    out = hs.load("AAPL", "daily")
    assert list(out.columns) == hs.OHLCV_COLUMNS
    assert all(out.dtypes == "float64")
    assert out.index.name == "Date" and out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]


def test_load_rejects_bad_session(store_root):
    with pytest.raises(ValueError, match="session"):
        hs.load("AAPL", "15min", session="pre")


def test_load_rejects_a_tz_aware_file(store_root):
    path = hs.file_path("AAPL", "daily")
    path.parent.mkdir(parents=True)
    path.write_text("Date,Open,High,Low,Close,Volume\n"
                    "2016-01-04 00:00:00-05:00,1,2,0.5,1.5,100\n")
    with pytest.raises(ValueError, match="naive"):
        hs.load("AAPL", "daily")


def test_load_empty_file_is_none(store_root):
    path = hs.file_path("AAPL", "daily")
    path.parent.mkdir(parents=True)
    path.write_text("Date,Open,High,Low,Close,Volume\n")
    assert hs.load("AAPL", "daily") is None


# --- the DST round trip (spec §1, acceptance 3) -----------------------------------

DST_DAYS = ["2026-03-06", "2026-03-09", "2026-10-30", "2026-11-02"]   # EST, EDT, EDT, EST


def _raw_session(day, start, end, freq):
    """Alpaca-shaped raw bars (lowercase, UTC) for one New York day."""
    idx = pd.date_range(f"{day} {start}", f"{day} {end}", freq=freq, tz=base.NY).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame({"open": [1.0] * n, "high": [2.0] * n, "low": [0.5] * n,
                         "close": [float(i) for i in range(n)], "volume": [100.0] * n},
                        index=pd.DatetimeIndex(idx, name="timestamp"))


def _raw_days(start, end, freq):
    return pd.concat([_raw_session(d, start, end, freq) for d in DST_DAYS])


def test_15min_round_trip_across_both_dst_changes(store_root):
    fetched = base.to_store_intraday(_raw_days("04:00", "19:45", "15min"))
    _write(fetched, "AAPL", "15min")

    every = hs.load("AAPL", "15min", session="all")
    pd.testing.assert_frame_equal(every, fetched, check_freq=False)

    rth = hs.load("AAPL", "15min")
    per_day = rth.groupby(rth.index.date)
    assert per_day.size().tolist() == [26, 26, 26, 26]
    assert {t.strftime("%H:%M") for t in per_day.head(1).index} == {"09:30"}
    assert {t.strftime("%H:%M") for t in per_day.tail(1).index} == {"15:45"}


def test_hourly_round_trip_across_both_dst_changes(store_root):
    fetched = base.to_store_hourly(_raw_days("09:00", "16:00", "30min"))
    _write(fetched, "AAPL", "hourly")
    loaded = hs.load("AAPL", "hourly", session="all")
    pd.testing.assert_frame_equal(loaded, fetched, check_freq=False)
    assert hs.load("AAPL", "hourly").equals(loaded)       # session is ignored for hourly
    per_day = loaded.groupby(loaded.index.date).size().tolist()
    assert per_day == [7, 7, 7, 7]
    assert loaded.index[0].strftime("%H:%M") == "09:30"


def test_daily_round_trip_across_both_dst_changes(store_root):
    raw = pd.concat([_raw_session(d, "00:00", "00:00", "1D") for d in DST_DAYS])
    fetched = base.to_yf_daily(raw)
    _write(fetched, "AAPL", "daily")
    loaded = hs.load("AAPL", "daily")
    assert [d.strftime("%Y-%m-%d") for d in loaded.index] == DST_DAYS
    pd.testing.assert_frame_equal(loaded, fetched, check_freq=False)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_history_store.py`
Expected: FAIL at collection with `ImportError: cannot import name 'history_store' from 'swingbot.core.marketdata'`.

- [ ] **Step 4: Implement the read seam**

Create `$WT/swingbot/core/marketdata/history_store.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_history_store.py`
Expected: PASS, 0 failed.

If `test_load_rejects_a_tz_aware_file` fails because `pd.to_datetime` already raises on the offset string, do not loosen the test. Wrap the parse in `_read`, catching `(ValueError, TypeError)` and re-raising `ValueError(f"{path}: tz-aware index; ...")`, so the message stays the same.

- [ ] **Step 6: Check the suite manifest, complexity and the main tree**

Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: PASS (the new directory is in exactly one suite).

Run: `python $WT/scripts/dev/testrun.py suites`
Expected: the list includes `history-store`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/history_store.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/core/marketdata/history_store.py tests/history_store/__init__.py tests/history_store/conftest.py tests/history_store/test_history_store.py tests/suites.toml
git -C $WT commit -m "feat(v162): history_store read seam, tests/history_store suite, DST round trip

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

# Phase B (start): backfill guards, identity check, store I/O

### Task AH3: Backfill guards: token bucket, backoff, hours, disk, progress

**Model:** sonnet — five small, independent guard helpers with injected clocks and fakes; the numbers are fixed by the spec.

**Files:**
- Create: `scripts/data/alpaca_history/__init__.py`
- Create: `scripts/data/alpaca_history/guards.py`
- Test: `tests/history_store/test_guards.py`

**Interfaces:**
- Consumes: `AlpacaMiss`, `AlpacaAuthError` (alpaca_provider.py:48/52; a 429/5xx is a plain `AlpacaMiss` carrying the original exception, with its `status_code`, on `__cause__`), `swingbot.core.market.session.is_regular_session(now) -> bool` (session.py:48; Mon–Fri 09:30 ≤ t < 16:00 ET, an aware `now` is converted to ET), the AH2 conftest `sys.path` entry for `scripts/data`.
- Produces (binding for AH6–AH8):
  - `RATE_PER_MINUTE = 120`, `MAX_RETRIES = 5`, `BACKOFF_BASE_SECONDS = 2.0`, `MIN_FREE_BYTES = 3 * 1024**3`, `ROWS_PER_YEAR = {"15min": 16_128, "hourly": 1_764, "daily": 252}` (252 sessions × 64 / 7 / 1 bars), `BYTES_PER_ROW = {"15min": 72, "hourly": 72, "daily": 64}`.
  - `class TokenBucket(rate_per_minute: int = RATE_PER_MINUTE, *, clock=time.monotonic, sleep=time.sleep)` with `acquire() -> None`, attribute `calls: int` (every acquisition, i.e. every request attempt) and `interval: float` (`60 / rate`). Capacity is one token, so no burst ever exceeds the rate in any 60-second window.
  - `status_of(exc: BaseException) -> int | None` (`exc.__cause__.status_code`, else `exc.status_code`, else `None`).
  - `call_with_backoff(fn: Callable[[], T], *, limiter: TokenBucket, sleep=time.sleep, retries: int = MAX_RETRIES) -> T`. It acquires one token per attempt. A 429, a 5xx or an unknown status sleeps `BACKOFF_BASE_SECONDS * 2**attempt` and retries, at most `retries` times. Any other `AlpacaMiss` (400/404/422) re-raises at once, and `AlpacaAuthError` re-raises at once.
  - `class HoursGuardError(RuntimeError)`; `assert_outside_hours(now: datetime | None = None, *, force: bool = False) -> None`.
  - `class DiskGuardError(RuntimeError)`; `estimate_bytes(n_tickers: int, timeframes: Sequence[str], years: float) -> int`; `check_disk(path: Path, needed_bytes: int, *, usage=shutil.disk_usage) -> None` (it walks up to the nearest existing parent before asking `usage`).
  - `class Progress(total: int, *, clock=time.monotonic, after_seconds: float = 900.0, out=print)` with `step(label: str) -> None`. It is silent for the first 15 minutes, then prints `[ NN%] done/total label` once per new integer percent.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_guards.py`:

```python
"""Backfill guards (spec §2): 120 requests a minute beside the live scan,
backoff on 429/5xx, auth errors stop the run, no run in the regular session
without --force-hours, a 3 GiB free-space floor, a percent after 15 minutes."""
from collections import namedtuple
from datetime import datetime, timezone

import pytest

from alpaca_history import guards
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss


class FakeClock:
    """A monotonic clock whose sleep advances it and records each wait."""
    def __init__(self, t=1000.0):
        self.t, self.sleeps = t, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 6))
        self.t += seconds


def _bucket(rate=guards.RATE_PER_MINUTE):
    clock = FakeClock()
    return guards.TokenBucket(rate, clock=clock, sleep=clock.sleep), clock


def _miss(status):
    """An AlpacaMiss shaped like AlpacaProvider._call raises it."""
    cause = Exception(f"http {status}")
    if status is not None:
        cause.status_code = status
    exc = AlpacaMiss(str(cause))
    exc.__cause__ = cause
    return exc


# --- token bucket ---------------------------------------------------------------

def test_first_call_is_free_then_calls_are_spaced_half_a_second():
    bucket, clock = _bucket()
    for _ in range(4):
        bucket.acquire()
    assert clock.sleeps == [0.5, 0.5, 0.5]
    assert bucket.calls == 4 and bucket.interval == 0.5


def test_never_more_than_the_rate_in_one_minute():
    bucket, clock = _bucket()
    start = clock.t
    for _ in range(guards.RATE_PER_MINUTE + 1):
        bucket.acquire()
    assert clock.t - start >= 60.0          # call 121 waits for the window to roll


def test_idle_time_is_not_banked_as_a_burst():
    bucket, clock = _bucket()
    bucket.acquire()
    clock.t += 30.0                          # idle
    bucket.acquire()
    bucket.acquire()
    assert clock.sleeps == [0.5]


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        guards.TokenBucket(0)


# --- backoff --------------------------------------------------------------------

def test_status_of_reads_the_cause_then_the_exception():
    assert guards.status_of(_miss(429)) == 429
    own = AlpacaMiss("x"); own.status_code = 503
    assert guards.status_of(own) == 503
    assert guards.status_of(_miss(None)) is None


def _flaky(errors, result="bars"):
    calls = []

    def fn():
        calls.append(1)
        if errors:
            raise errors.pop(0)
        return result
    return fn, calls


@pytest.mark.parametrize("status", [429, 500, 503, None])
def test_retryable_errors_back_off_exponentially(status):
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(status), _miss(status)])
    assert guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep) == "bars"
    assert backoff.sleeps == [2.0, 4.0]
    assert len(calls) == 3 and bucket.calls == 3       # one token per attempt


@pytest.mark.parametrize("status", [400, 404, 422])
def test_client_errors_are_not_retried(status):
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(status)])
    with pytest.raises(AlpacaMiss):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == 1 and backoff.sleeps == []


def test_auth_error_stops_at_once():
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([AlpacaAuthError("forbidden")])
    with pytest.raises(AlpacaAuthError):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == 1 and backoff.sleeps == []


def test_retries_are_bounded():
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(429) for _ in range(10)])
    with pytest.raises(AlpacaMiss):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == guards.MAX_RETRIES + 1
    assert backoff.sleeps == [2.0, 4.0, 8.0, 16.0, 32.0]


# --- market hours ----------------------------------------------------------------

def test_refuses_during_the_regular_session():
    wednesday_11_et = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(guards.HoursGuardError, match="--force-hours"):
        guards.assert_outside_hours(wednesday_11_et)


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc),   # Wed 17:00 ET, after the close
    datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc),   # Wed 09:00 ET, before the open
    datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc),   # Sunday
])
def test_allows_outside_the_regular_session(now):
    guards.assert_outside_hours(now)


def test_force_hours_overrides():
    guards.assert_outside_hours(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc), force=True)


# --- disk ------------------------------------------------------------------------

Usage = namedtuple("Usage", "total used free")
GIB = 1024 ** 3


def test_estimate_is_linear_in_tickers_and_years():
    one = guards.estimate_bytes(1, ["daily"], 1.0)
    assert one == 252 * 64
    assert guards.estimate_bytes(10, ["daily"], 2.0) == 20 * one


def test_full_watchlist_estimate_is_about_a_gigabyte():
    estimate = guards.estimate_bytes(77, ["15min", "hourly", "daily"], 10.8)
    assert 0.8 * GIB < estimate < 1.5 * GIB          # spec §1: about 1.2 GB


def test_disk_guard_passes_with_room(tmp_path):
    guards.check_disk(tmp_path, 1 * GIB, usage=lambda p: Usage(0, 0, 5 * GIB))


def test_disk_guard_refuses_below_the_floor(tmp_path):
    with pytest.raises(guards.DiskGuardError, match="3 GiB"):
        guards.check_disk(tmp_path, int(2.5 * GIB), usage=lambda p: Usage(0, 0, 5 * GIB))


def test_disk_guard_asks_about_the_nearest_existing_directory(tmp_path):
    asked = []
    guards.check_disk(tmp_path / "market_data" / "15min", 0,
                      usage=lambda p: asked.append(p) or Usage(0, 0, 10 * GIB))
    assert asked == [tmp_path]


# --- progress --------------------------------------------------------------------

def test_progress_is_silent_for_fifteen_minutes_then_prints_each_new_percent():
    clock, lines = FakeClock(), []
    progress = guards.Progress(200, clock=clock, out=lines.append)
    progress.step("AAPL/daily")
    clock.t += 899
    progress.step("AAPL/hourly")
    assert lines == []
    clock.t += 2
    progress.step("AAPL/15min")          # 3/200 = 1%
    progress.step("MSFT/daily")          # 4/200 = 2%
    progress.step("MSFT/hourly")         # 5/200 = 2%, no new line
    assert lines == ["[  1%] 3/200 AAPL/15min", "[  2%] 4/200 MSFT/daily"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_guards.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'alpaca_history'`.

- [ ] **Step 3: Create the package**

Create `$WT/scripts/data/alpaca_history/__init__.py`:

```python
"""v162 Alpaca history store backfill: the modules behind
scripts/data/fetch_alpaca_history.py. Imported as the top-level package
`alpaca_history` with scripts/data on sys.path (the CLI inserts it, tests get
it from tests/history_store/conftest.py)."""
```

- [ ] **Step 4: Implement the guards**

Create `$WT/scripts/data/alpaca_history/guards.py`:

```python
"""Backfill guards (v162 spec §2).

The Alpaca key's budget (200 requests a minute) is shared with the live scan,
so the backfill spaces its calls at RATE_PER_MINUTE and backs off on 429/5xx.
An auth error stops the run. The regular session is off limits unless forced.
The disk also holds the PITR repository and the nightly dumps, so a run that
would leave less than MIN_FREE_BYTES free is refused before it writes.
"""
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from swingbot.core.market.session import is_regular_session
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss

T = TypeVar("T")

RATE_PER_MINUTE = 120
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
MIN_FREE_BYTES = 3 * 1024 ** 3
GIB = 1024 ** 3
#: bars a year per ticker: 252 sessions x 64 (15min, 04:00-20:00 ET) / 7 (hourly RTH) / 1
ROWS_PER_YEAR = {"15min": 252 * 64, "hourly": 252 * 7, "daily": 252}
#: CSV bytes per row: a "YYYY-MM-DD HH:MM:SS" stamp plus five floats; daily has a shorter stamp
BYTES_PER_ROW = {"15min": 72, "hourly": 72, "daily": 64}


class TokenBucket:
    """At most `rate_per_minute` acquisitions in any 60 seconds. The capacity
    is one token: idle time is never banked into a burst, so the live scan
    always keeps its share of the key's budget."""

    def __init__(self, rate_per_minute: int = RATE_PER_MINUTE, *,
                 clock=time.monotonic, sleep=time.sleep):
        if rate_per_minute <= 0:
            raise ValueError(f"rate_per_minute must be positive, got {rate_per_minute}")
        self.interval = 60.0 / rate_per_minute
        self.calls = 0
        self._clock, self._sleep = clock, sleep
        self._next = None

    def acquire(self) -> None:
        now = self._clock()
        if self._next is not None and now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self.interval
        self.calls += 1


def status_of(exc: BaseException) -> int | None:
    """The HTTP status behind an AlpacaMiss: AlpacaProvider._call keeps the
    original exception on __cause__."""
    for candidate in (exc.__cause__, exc):
        status = getattr(candidate, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _retryable(exc: BaseException) -> bool:
    status = status_of(exc)
    return status is None or status == 429 or status >= 500


def call_with_backoff(fn: Callable[[], T], *, limiter: TokenBucket,
                      sleep=time.sleep, retries: int = MAX_RETRIES) -> T:
    """fn() under the rate limit. 429/5xx/unknown back off 2 s x 2^attempt,
    at most `retries` times; other misses and auth errors raise at once."""
    for attempt in range(retries + 1):
        limiter.acquire()
        try:
            return fn()
        except AlpacaAuthError:
            raise
        except AlpacaMiss as exc:
            if attempt >= retries or not _retryable(exc):
                raise
            sleep(BACKOFF_BASE_SECONDS * 2 ** attempt)
    raise AssertionError("unreachable: the last attempt returns or raises")


class HoursGuardError(RuntimeError):
    """The US regular session is open and --force-hours was not given."""


def assert_outside_hours(now: datetime | None = None, *, force: bool = False) -> None:
    if force:
        return
    if is_regular_session(now or datetime.now(timezone.utc)):
        raise HoursGuardError(
            "the US regular session is open (Mon-Fri 09:30-16:00 ET); the backfill shares the "
            "Alpaca key with the live scan -- run it outside hours or pass --force-hours")


class DiskGuardError(RuntimeError):
    """The run would leave less than MIN_FREE_BYTES free on the store's disk."""


def estimate_bytes(n_tickers: int, timeframes: Sequence[str], years: float) -> int:
    per_ticker_year = sum(ROWS_PER_YEAR[tf] * BYTES_PER_ROW[tf] for tf in timeframes)
    return int(per_ticker_year * n_tickers * max(years, 0.0))


def _nearest_existing(path: Path) -> Path:
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def check_disk(path: Path, needed_bytes: int, *, usage=shutil.disk_usage) -> None:
    free = usage(_nearest_existing(path)).free
    if free - needed_bytes < MIN_FREE_BYTES:
        raise DiskGuardError(
            f"free space {free / GIB:.2f} GiB minus this run's estimate {needed_bytes / GIB:.2f} GiB "
            f"would leave less than {MIN_FREE_BYTES // GIB} GiB; the disk also holds the PITR "
            f"repository and the nightly dumps")


class Progress:
    """Silent for `after_seconds` (15 minutes), then one line per new integer
    percent: `[ NN%] done/total label`."""

    def __init__(self, total: int, *, clock=time.monotonic,
                 after_seconds: float = 900.0, out=print):
        self.total = max(int(total), 1)
        self.done = 0
        self._clock, self._after, self._out = clock, after_seconds, out
        self._start = clock()
        self._last_pct = None

    def step(self, label: str) -> None:
        self.done += 1
        if self._clock() - self._start < self._after:
            return
        pct = min(100, self.done * 100 // self.total)
        if pct == self._last_pct:
            return
        self._last_pct = pct
        self._out(f"[{pct:3d}%] {self.done}/{self.total} {label}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_guards.py`
Expected: PASS, 0 failed.

- [ ] **Step 6: Check complexity**

Run: `python -m radon cc -s -n C $WT/scripts/data/alpaca_history/guards.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add scripts/data/alpaca_history/__init__.py scripts/data/alpaca_history/guards.py tests/history_store/test_guards.py
git -C $WT commit -m "feat(v162): backfill guards -- 120/min token bucket, 429/5xx backoff, hours and disk refusals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

### Task AH4: Identity check and skip classification

**Model:** sonnet — a pure comparison with stated thresholds and statuses; the NaN and short-overlap edges are pinned by the tests below.

**Files:**
- Create: `scripts/data/alpaca_history/identity.py`
- Test: `tests/history_store/test_identity.py`

**Interfaces:**
- Consumes: `ALPACA_TOLERANCE = 0.005` and `close_ratios(cache, fresh) -> (c, f, [fresh Close / cache Close per overlapping index])` from `scripts/ops/market_cache_repair.py:36/40` (it skips a non-positive or NaN cache close but not a NaN fresh close, and needs unique indexes), `data_store.safe_symbol`, `providers.base.is_alpaca_eligible`/`NY`, `spot_metals.is_spot_metal` (spot_metals.py:53), the package from AH3.
- Produces (binding for AH7, AH8):
  - `MIN_IDENTITY_OVERLAP = 250`; status constants `OK = "ok"`, `NO_REFERENCE = "flagged: no-reference"`, `SHORT_OVERLAP = "flagged: short-overlap"`, `PRICE_MISMATCH = "flagged: price-mismatch"`.
  - `skip_reason(ticker: str) -> str | None`. It returns the full manifest status `"skipped: spot metal (built from futures)"`, `"skipped: futures"`, `"skipped: index"` or `"skipped: not Alpaca-eligible"`, checked in that order, or `None` for a ticker Alpaca can serve.
  - `reference_frame(ticker: str, *, backtest_dir: Path, market_dir: Path) -> pd.DataFrame | None`. It reads `backtest_dir/<SAFE>.csv` first, then `market_dir/<SAFE>.csv`; `market_dir` is the root `market_data/daily` folder. The result is a single `Close` column (numeric, NaN where unparseable) over naive midnight dates, deduplicated and sorted. A missing file, or one without rows or a `Close` column, falls through to the next file.
  - `@dataclass(frozen=True) IdentityResult(status: str, median_ratio: float | None, overlap: int, dropped_before: str | None)` with `to_json() -> dict` (the manifest's `identity` object; `median_ratio` rounded to 6 places).
  - `identity_check(fresh: pd.DataFrame, reference: pd.DataFrame | None) -> tuple[IdentityResult, pd.DataFrame]`. `fresh` is a store daily frame (`Date` index, `Close` column). It returns the result and `fresh` with every bar before the reference's first bar dropped (`dropped_before` = that first date, `YYYY-MM-DD`). Only finite ratios over positive closes count toward `overlap`. Fewer than 250 is `SHORT_OVERLAP`, never a pass. `|median − 1| ≤ 0.005` is `OK`, otherwise `PRICE_MISMATCH`. No reference returns `NO_REFERENCE` with `fresh` unchanged.

**Why it compares with `data/backtest_cache` first:** that cache goes back to 2000 or the listing date and is rebuilt by `fetch_backtest_data.py`. The root `market_data/daily` cache never self-heals (`known-traps.md` § The market_data cache never self-heals), so it is only the fallback. Ticker reuse is the live risk: `SNDK` was SanDisk until 2016 and has been a new listing since 2025. Alpaca's pre-2025 bars belong to another company, and dropping everything before the reference's first bar removes them.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_identity.py`:

```python
"""Identity check (spec §2): a fresh Alpaca daily frame is accepted only when
its closes agree with data/backtest_cache (fallback market_data/daily) to 0.5%
by median over at least 250 finite overlapping bars. Bars before the
reference's first bar are dropped (ticker reuse, e.g. SNDK)."""
import math

import numpy as np
import pandas as pd
import pytest

from alpaca_history import identity


def _daily(n, close=10.0, start="2016-01-04"):
    idx = pd.DatetimeIndex(pd.bdate_range(start, periods=n), name="Date")
    closes = np.full(n, float(close)) if np.isscalar(close) else np.asarray(close, float)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": np.full(n, 1e6)}, index=idx)


def _ref(frame, factor=1.0):
    return pd.DataFrame({"Close": frame["Close"] / factor}, index=frame.index)


# --- skips -------------------------------------------------------------------------

@pytest.mark.parametrize("ticker,reason", [
    ("XAUUSD", "skipped: spot metal (built from futures)"),
    ("xagusd", "skipped: spot metal (built from futures)"),
    ("GC=F", "skipped: futures"),
    ("^GSPC", "skipped: index"),
    ("SAP.DE", "skipped: not Alpaca-eligible"),
    ("EURUSD=X", "skipped: not Alpaca-eligible"),
    ("BTC-USD", "skipped: not Alpaca-eligible"),
    ("AAPL", None), ("SPY", None), ("BRK-B", None),
])
def test_skip_reason(ticker, reason):
    assert identity.skip_reason(ticker) == reason


# --- reference ---------------------------------------------------------------------

def _csv(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)


def test_reference_prefers_backtest_cache(tmp_path):
    _csv(tmp_path / "bc", "AAPL.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,10,5\n")
    _csv(tmp_path / "md", "AAPL.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,99,5\n")
    ref = identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref["Close"].tolist() == [10.0]


def test_reference_falls_back_to_market_data_and_normalises_tz(tmp_path):
    _csv(tmp_path / "md", "GC_F.csv",
         "Date,Open,High,Low,Close,Volume\n"
         "2016-01-05 00:00:00-05:00,1,1,1,11,5\n2016-01-04 00:00:00-05:00,1,1,1,10,5\n")
    ref = identity.reference_frame("GC=F", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref.index.tz is None
    assert list(ref.index) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]
    assert ref["Close"].tolist() == [10.0, 11.0]


def test_reference_skips_a_file_without_close(tmp_path):
    _csv(tmp_path / "bc", "AAPL.csv", "Date,Open\n2016-01-04,1\n")
    _csv(tmp_path / "md", "AAPL.csv", "Date,Close\n2016-01-04,12\n")
    ref = identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref["Close"].tolist() == [12.0]


def test_no_reference_is_none(tmp_path):
    assert identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc",
                                    market_dir=tmp_path / "md") is None


# --- identity_check ------------------------------------------------------------------

def test_agreeing_frame_is_ok():
    fresh = _daily(300)
    result, kept = identity.identity_check(fresh, _ref(fresh, 1.001))
    assert result.status == identity.OK
    assert result.median_ratio == pytest.approx(1.001)
    assert (result.overlap, result.dropped_before) == (300, None)
    pd.testing.assert_frame_equal(kept, fresh)


@pytest.mark.parametrize("factor,status", [
    (1.004, identity.OK), (0.996, identity.OK),
    (1.006, identity.PRICE_MISMATCH), (0.994, identity.PRICE_MISMATCH),
    (2.0, identity.PRICE_MISMATCH),
])
def test_tolerance_is_half_a_percent(factor, status):
    fresh = _daily(300)
    assert identity.identity_check(fresh, _ref(fresh, factor))[0].status == status


@pytest.mark.parametrize("n,status", [(249, identity.SHORT_OVERLAP), (250, identity.OK)])
def test_minimum_overlap_is_250_bars(n, status):
    fresh = _daily(n)
    result, _ = identity.identity_check(fresh, _ref(fresh))
    assert (result.status, result.overlap) == (status, n)


def test_nan_and_zero_closes_never_count_toward_the_overlap():
    fresh = _daily(300)
    ref = _ref(fresh)
    fresh.iloc[:60, fresh.columns.get_loc("Close")] = np.nan      # 60 NaN fresh closes
    ref.iloc[60:70, 0] = np.nan                                   # 10 NaN reference closes
    ref.iloc[70:75, 0] = 0.0                                      # 5 zero reference closes
    result, _ = identity.identity_check(fresh, ref)
    assert result.overlap == 225
    assert result.status == identity.SHORT_OVERLAP                # never a pass
    assert result.median_ratio is not None and not math.isnan(result.median_ratio)


def test_no_reference_is_flagged_and_the_frame_kept():
    fresh = _daily(300)
    result, kept = identity.identity_check(fresh, None)
    assert (result.status, result.overlap, result.median_ratio) == (identity.NO_REFERENCE, 0, None)
    assert kept is fresh


def test_bars_before_the_reference_start_are_dropped():
    """SNDK: Alpaca still serves the old SanDisk years; the reference is the
    new listing. Everything before its first bar goes."""
    fresh = _daily(600, close=np.r_[np.full(300, 55.0), np.full(300, 10.0)])
    new_listing = fresh.iloc[300:]
    result, kept = identity.identity_check(fresh, _ref(new_listing))
    assert result.dropped_before == new_listing.index[0].strftime("%Y-%m-%d")
    assert kept.index[0] == new_listing.index[0] and len(kept) == 300
    assert result.status == identity.OK and result.overlap == 300


def test_to_json_is_the_manifest_identity_object():
    result = identity.IdentityResult(identity.OK, 1.00012345678, 2710, None)
    assert result.to_json() == {"status": "ok", "median_ratio": 1.000123,
                                "overlap": 2710, "dropped_before": None}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_identity.py`
Expected: FAIL at collection with `ImportError: cannot import name 'identity' from 'alpaca_history'`.

- [ ] **Step 3: Implement the identity module**

Create `$WT/scripts/data/alpaca_history/identity.py`:

```python
"""Identity check and skip classification (v162 spec §2).

One bad fetch can hand a ticker another instrument's history
(known-traps.md, "The market_data cache never self-heals"), and Alpaca serves
reused tickers' old histories (SNDK). So a fresh daily frame is compared with
data/backtest_cache/<SAFE>.csv (fallback: the root market_data/daily cache):
the median fresh/reference close ratio over at least MIN_IDENTITY_OVERLAP
finite bars must lie within ALPACA_TOLERANCE of 1. A disagreeing ticker is
still written, but flagged; training leaves flagged tickers out.
"""
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from swingbot.core.marketdata.data_store import safe_symbol
from swingbot.core.marketdata.providers.base import NY, is_alpaca_eligible
from swingbot.core.marketdata.spot_metals import is_spot_metal

_OPS = Path(__file__).resolve().parents[2] / "ops"
if str(_OPS) not in sys.path:
    sys.path.append(str(_OPS))
from market_cache_repair import ALPACA_TOLERANCE, close_ratios  # noqa: E402

MIN_IDENTITY_OVERLAP = 250
OK = "ok"
NO_REFERENCE = "flagged: no-reference"
SHORT_OVERLAP = "flagged: short-overlap"
PRICE_MISMATCH = "flagged: price-mismatch"


def skip_reason(ticker: str) -> str | None:
    """The manifest status for a symbol Alpaca cannot serve, else None."""
    symbol = (ticker or "").upper().strip()
    if is_spot_metal(symbol):
        return "skipped: spot metal (built from futures)"
    if symbol.endswith("=F"):
        return "skipped: futures"
    if symbol.startswith("^"):
        return "skipped: index"
    if not is_alpaca_eligible(symbol):
        return "skipped: not Alpaca-eligible"
    return None


def _naive_dates(values) -> pd.DatetimeIndex:
    """Naive midnight dates from a CSV index that may carry a UTC offset."""
    try:
        index = pd.DatetimeIndex(pd.to_datetime(values))
    except (ValueError, TypeError):
        index = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    if index.tz is not None:
        index = index.tz_convert(NY).tz_localize(None)
    return index.normalize()


def _read_reference(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    raw = pd.read_csv(path, index_col=0)
    if raw.empty or "Close" not in raw.columns:
        return None
    frame = pd.DataFrame({"Close": pd.to_numeric(raw["Close"], errors="coerce").to_numpy()},
                         index=_naive_dates(raw.index))
    frame.index.name = "Date"
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index()


def reference_frame(ticker: str, *, backtest_dir: Path, market_dir: Path) -> pd.DataFrame | None:
    name = f"{safe_symbol(ticker)}.csv"
    for folder in (backtest_dir, market_dir):
        frame = _read_reference(Path(folder) / name)
        if frame is not None:
            return frame
    return None


@dataclass(frozen=True)
class IdentityResult:
    status: str
    median_ratio: float | None
    overlap: int
    dropped_before: str | None

    def to_json(self) -> dict:
        out = asdict(self)
        if out["median_ratio"] is not None:
            out["median_ratio"] = round(out["median_ratio"], 6)
        return out


def _unique(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[~frame.index.duplicated(keep="last")]


def _finite_ratios(fresh: pd.DataFrame, reference: pd.DataFrame) -> list[float]:
    """fresh/reference close per overlapping bar, NaN-safe: close_ratios
    already skips a NaN or non-positive reference close; a NaN or
    non-positive fresh close is dropped here."""
    _, _, ratios = close_ratios(_unique(reference), _unique(fresh))
    return [r for r in ratios if math.isfinite(r) and r > 0]


def _trim(fresh: pd.DataFrame, first_reference_bar) -> tuple[pd.DataFrame, str | None]:
    if fresh.empty or fresh.index.min() >= first_reference_bar:
        return fresh, None
    return fresh[fresh.index >= first_reference_bar], first_reference_bar.strftime("%Y-%m-%d")


def _verdict(ratios: list[float]) -> tuple[str, float | None]:
    median = statistics.median(ratios) if ratios else None
    if len(ratios) < MIN_IDENTITY_OVERLAP:
        return SHORT_OVERLAP, median
    return (OK if abs(median - 1) <= ALPACA_TOLERANCE else PRICE_MISMATCH), median


def identity_check(fresh: pd.DataFrame, reference: pd.DataFrame | None
                   ) -> tuple[IdentityResult, pd.DataFrame]:
    """(result, fresh without the bars before the reference's first bar)."""
    if reference is None or reference.empty:
        return IdentityResult(NO_REFERENCE, None, 0, None), fresh
    kept, dropped_before = _trim(fresh, reference.index.min())
    ratios = _finite_ratios(kept, reference)
    status, median = _verdict(ratios)
    return IdentityResult(status, median, len(ratios), dropped_before), kept
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_identity.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Check complexity and that the repair script is untouched**

Run: `python -m radon cc -s -n C $WT/scripts/data/alpaca_history/identity.py`
Expected: no output.

Run: `git -C $WT diff --stat main -- scripts/ops/market_cache_repair.py`
Expected: no output (the constant and helper are imported, never edited).

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/data/alpaca_history/identity.py tests/history_store/test_identity.py
git -C $WT commit -m "feat(v162): history identity check -- 250-bar NaN-safe median vs backtest_cache, pre-listing trim, skips

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

