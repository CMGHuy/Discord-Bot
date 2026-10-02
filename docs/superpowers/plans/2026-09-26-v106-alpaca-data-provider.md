# v106 — Alpaca Data Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot minor, ui minor
**Edge:** none (integrity)
**Spec:** `docs/superpowers/specs/2026-09-26-v106-alpaca-data-provider-design.md`

**Goal:** Route live-path US bars and quotes through Alpaca (`alpaca-py`), with
per-symbol yfinance fallback, a `.env` kill switch, source tagging, and a parity
report.

**Architecture:** A new `swingbot/core/marketdata/providers/` package holds
three things: the frame contract plus eligibility (`base.py`), an
`AlpacaProvider` (`alpaca_provider.py`), and a `router` (`router.py`). The
existing yfinance code in `data.py`/`data_store.py` is extracted into small
private callables and handed to the router as `yf_fetch`. The router tries
Alpaca for eligible symbols and falls back per symbol. Every public signature
stays the same.

**Tech Stack:** Python 3.11, `alpaca-py` (`StockHistoricalDataClient`),
pandas, pytest, Flask API, Angular.

## Global Constraints

- **Live path only.** Never touch `backtest_cache.py`,
  `scripts/data/fetch_backtest_data.py`, `data_store.fetch_interval_data`, the
  `market_data_refresh` loop, `market/events.py`, company/currency lookups, or
  option snapshots.
- **`ALPACA_ENABLED` defaults to `false`.** When off, every wrapped function
  must return exactly what it returned before this plan.
- **Feeds:** bars are always `DataFeed.SIP`, with `end = now − 16 min`. Live
  last-trade uses `ALPACA_DATA_FEED_LIVE` (default `iex`). **IEX volume is
  never read.**
- **Adjustment:** `Adjustment.ALL` (matches yfinance `auto_adjust=True`).
- **Stale-trade guard:** during the regular session (Mon–Fri 09:30–16:00 ET),
  a latest trade older than `ALPACA_MAX_TRADE_AGE_SECONDS` (default 300) is a
  miss.
- **Timeout** `ALPACA_TIMEOUT_SECONDS` (default 5). **Breaker:**
  `ALPACA_BREAKER_FAILURES` (default 3) consecutive failed calls → open for
  `ALPACA_BREAKER_COOLDOWN_SECONDS` (default 300). A 401/403 latches it open
  until the keys change. **Token bucket:** 150 requests/min.
- **Eligibility:** `asset_class.classify(sym) in {"equity","etf"}`, no `.`,
  matching `^[A-Z]{1,5}(-[A-Z])?$`. The Alpaca symbol is the ticker with
  `-` → `.`. Results are keyed by the original yfinance ticker.
- **Source tags:** `frame.attrs["source"]` ∈ `{"alpaca", "yfinance",
  "yfinance-fallback"}`.
- **No network in tests.** Fake `StockHistoricalDataClient` and yfinance.
- Every function written or changed ends below cyclomatic complexity 15
  (`python -m radon cc -s -n C <files>`). `get_current_price_batch` (today
  D/23) must end **lower**, never higher.
- Per-task checks use `python scripts/dev/testrun.py file <test file>`. The
  full suite runs once, in T12.

## Review Focus

1. **Alpaca returns data for only some of an eligible batch** (a delisted or
   unknown ticker is silently absent). The missing ones must come back via
   yfinance in the same call, not vanish → T4
   `test_partial_alpaca_result_falls_back_per_symbol`.
2. **Class shares** (`BRK-B`): sent to Alpaca as `BRK.B`, returned keyed
   `BRK-B` → T2 `test_class_share_symbol_mapping`, T3
   `test_daily_bars_rekeys_class_shares`.
3. **Lagging IEX print reaching a trading caller** (`allow_stale=False`
   SL/TP monitor) during the session → T3
   `test_stale_iex_trade_is_a_miss_in_session`.
4. **Alpaca hangs** (no response). The call must return within
   `ALPACA_TIMEOUT_SECONDS` plus the yfinance time, never block the scan →
   T4 `test_timeout_falls_back`.
5. **Keys rotated or revoked via SIGHUP in the admin container** (which has no
   `on_config_reload`). A 401 must latch the breaker, and new keys must
   un-latch it on the next call → T4 `test_auth_error_latches_until_keys_change`.

---

# Phase A — Provider package

### Task T1: Dependency and config fields

**Files:**
- Modify: `requirements.txt` (next to the `yfinance==0.2.66` pin, line ~23)
- Modify: `swingbot/config.py` (the "Data Sources" section, beside
  `FMP_API_KEY` ~631)
- Modify: `.env.example` (beside `FMP_API_KEY=` ~391)
- Test: `tests/test_config_alpaca.py`

**Interfaces:**
- Produces: `config.ALPACA_ENABLED: bool`, `config.ALPACA_API_KEY_ID: str`,
  `config.ALPACA_API_SECRET_KEY: str`, `config.ALPACA_DATA_FEED_LIVE: str`,
  `config.ALPACA_TIMEOUT_SECONDS: float`,
  `config.ALPACA_MAX_TRADE_AGE_SECONDS: int`,
  `config.ALPACA_BREAKER_FAILURES: int`,
  `config.ALPACA_BREAKER_COOLDOWN_SECONDS: int`.

- [ ] **Step 1: Pin the dependency.** Run `pip index versions alpaca-py`. Add
  `alpaca-py==<latest>` to `requirements.txt` with a one-line rationale comment
  in the file's existing style ("v106: live-path US bars/quotes; see spec").
  `pip install -r requirements.txt`. Then check that
  `python -c "from alpaca.data.historical import StockHistoricalDataClient; from alpaca.data.enums import DataFeed, Adjustment"`
  succeeds. **If alpaca-py's pinned dependencies conflict with `pandas==2.3.3`
  or `yfinance==0.2.66`, stop and report.** Do not bump those pins.
- [ ] **Step 2: Write the failing test.**

```python
# tests/test_config_alpaca.py
from swingbot import config

def test_alpaca_fields_declared_with_safe_defaults():
    keys = {f.key: f for f in config.FIELDS}
    for k in ("ALPACA_ENABLED", "ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
              "ALPACA_DATA_FEED_LIVE", "ALPACA_TIMEOUT_SECONDS",
              "ALPACA_MAX_TRADE_AGE_SECONDS", "ALPACA_BREAKER_FAILURES",
              "ALPACA_BREAKER_COOLDOWN_SECONDS"):
        assert k in keys, k
        assert keys[k].section == "Data Sources"
    assert keys["ALPACA_ENABLED"].default == "false"
    assert keys["ALPACA_API_SECRET_KEY"].sensitive is True
    assert keys["ALPACA_API_KEY_ID"].sensitive is True
    assert keys["ALPACA_DATA_FEED_LIVE"].default == "iex"

def test_alpaca_disabled_by_default():
    assert config.ALPACA_ENABLED is False
```

- [ ] **Step 3: Run it.** `python scripts/dev/testrun.py file tests/test_config_alpaca.py`
  → FAIL (missing keys).
- [ ] **Step 4: Add the fields.** Model them on `FMP_API_KEY` (password)
  and `MARKET_DATA_AUTO_REFRESH` (`type="checkbox"`). Check how
  `config.py` coerces checkbox/number types into module globals and follow
  it exactly.

```python
Field("ALPACA_ENABLED", "ALPACA_ENABLED", "Data Sources",
      "Use Alpaca for live US bars/quotes",
      type="checkbox", default="false",
      help="v106. When on, live-path daily bars, 1h bars and last-trade prices for "
           "US equities/ETFs come from Alpaca (SIP bars >=15 min old, IEX last "
           "trade), falling back per symbol to yfinance. Off = exact pre-v106 "
           "yfinance behaviour. Backtests never use Alpaca."),
Field("ALPACA_API_KEY_ID", "ALPACA_API_KEY_ID", "Data Sources", "Alpaca API key ID",
      type="password", sensitive=True, default="",
      help="From the Alpaca dashboard (paper or live account; market data is the same)."),
Field("ALPACA_API_SECRET_KEY", "ALPACA_API_SECRET_KEY", "Data Sources",
      "Alpaca API secret key", type="password", sensitive=True, default="",
      help="Paired with ALPACA_API_KEY_ID."),
Field("ALPACA_DATA_FEED_LIVE", "ALPACA_DATA_FEED_LIVE", "Data Sources",
      "Alpaca live-price feed", default="iex",
      help="'iex' on the free plan, 'sip' on a paid plan. Bars always use SIP."),
Field("ALPACA_TIMEOUT_SECONDS", "ALPACA_TIMEOUT_SECONDS", "Data Sources",
      "Alpaca call timeout (s)", type="number", default="5", min=1, max=30, step=1,
      help="Past this an Alpaca call is abandoned and the symbols fall back to yfinance."),
Field("ALPACA_MAX_TRADE_AGE_SECONDS", "ALPACA_MAX_TRADE_AGE_SECONDS", "Data Sources",
      "Max IEX last-trade age in session (s)", type="number", default="300",
      min=30, max=3600, step=30,
      help="During the regular session an older IEX print is treated as a miss so a "
           "lagging print never reaches a trading caller."),
Field("ALPACA_BREAKER_FAILURES", "ALPACA_BREAKER_FAILURES", "Data Sources",
      "Alpaca breaker: consecutive failures", type="number", default="3",
      min=1, max=20, step=1, help="Failed calls in a row before Alpaca is skipped."),
Field("ALPACA_BREAKER_COOLDOWN_SECONDS", "ALPACA_BREAKER_COOLDOWN_SECONDS",
      "Data Sources", "Alpaca breaker cool-down (s)", type="number", default="300",
      min=30, max=3600, step=30, help="How long Alpaca is skipped once the breaker opens."),
```

  Add a commented block to `.env.example`:

```
# --- Alpaca market data (v106) -- live path only, yfinance fallback ---
# ALPACA_ENABLED=false
# ALPACA_API_KEY_ID=
# ALPACA_API_SECRET_KEY=
# ALPACA_DATA_FEED_LIVE=iex
```

- [ ] **Step 5: Run it.** Same command → PASS.
- [ ] **Step 6: Commit.**

```bash
git add requirements.txt swingbot/config.py .env.example tests/test_config_alpaca.py
git commit -m "feat(v106): alpaca-py dependency and ALPACA_* config fields (default off)"
```

### Task T2: `providers/base.py` — eligibility and frame contract

**Files:**
- Create: `swingbot/core/marketdata/providers/__init__.py` (empty)
- Create: `swingbot/core/marketdata/providers/base.py`
- Test: `tests/marketdata/test_providers_base.py`

**Interfaces:**
- Produces:
  - `is_alpaca_eligible(ticker: str) -> bool`
  - `to_alpaca_symbol(ticker: str) -> str`
  - `to_yf_daily(df: pd.DataFrame) -> pd.DataFrame`
  - `to_yf_hourly(df30: pd.DataFrame) -> pd.DataFrame`
  - `NY` (`ZoneInfo("America/New_York")`)
  - `SOURCE_ALPACA = "alpaca"`, `SOURCE_YF = "yfinance"`,
    `SOURCE_FALLBACK = "yfinance-fallback"`
- Input to `to_yf_daily` / `to_yf_hourly`: one symbol's slice of alpaca-py
  `BarSet.df`, i.e. `df.xs(sym, level="symbol")`, which has a tz-aware UTC
  `timestamp` index and columns `open, high, low, close, volume, trade_count,
  vwap`.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/marketdata/test_providers_base.py
import pandas as pd
import pytest
from swingbot.core.marketdata.providers import base

@pytest.mark.parametrize("t,ok", [
    ("AAPL", True), ("SPY", True), ("BRK-B", True),
    ("SAP.DE", False), ("^GSPC", False), ("EURUSD=X", False),
    ("GC=F", False), ("BTC-USD", False), ("", False),
])
def test_eligibility(t, ok):
    assert base.is_alpaca_eligible(t) is ok

def test_class_share_symbol_mapping():
    assert base.to_alpaca_symbol("BRK-B") == "BRK.B"
    assert base.to_alpaca_symbol("AAPL") == "AAPL"

def _alpaca_daily():
    idx = pd.DatetimeIndex(["2026-09-24 04:00", "2026-09-25 04:00"], tz="UTC", name="timestamp")
    return pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0.5, 1.5],
                         "close": [1.5, 2.5], "volume": [100, 200],
                         "trade_count": [5, 6], "vwap": [1.4, 2.4]}, index=idx)

def test_to_yf_daily_matches_yfinance_shape():
    out = base.to_yf_daily(_alpaca_daily())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2026-09-24"), pd.Timestamp("2026-09-25")]
    assert all(out.dtypes == "float64")

def test_to_yf_hourly_rebuilds_on_0930_grid():
    idx = pd.date_range("2026-09-25 09:00", "2026-09-25 16:00", freq="30min",
                        tz=base.NY).tz_convert("UTC")
    df = pd.DataFrame({"open": range(len(idx)), "high": range(1, len(idx) + 1),
                       "low": range(len(idx)), "close": range(len(idx)),
                       "volume": [10] * len(idx)}, index=idx).astype(float)
    out = base.to_yf_hourly(df)
    assert str(out.index.tz) == "America/New_York"
    assert [t.strftime("%H:%M") for t in out.index] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    first = out.iloc[0]          # 09:30 + 10:00 half-hours, pre-market 09:00 excluded
    assert first["Open"] == 1 and first["Close"] == 2 and first["Volume"] == 20
    assert out.iloc[-1]["Volume"] == 10   # 15:30 bar is one half-hour; 16:00 excluded
```

- [ ] **Step 2: Run it.** `python scripts/dev/testrun.py file tests/marketdata/test_providers_base.py`
  → FAIL (module missing).
- [ ] **Step 3: Implement.**

```python
# swingbot/core/marketdata/providers/base.py
"""v106 provider contract: which symbols Alpaca may serve, and the frame
shapes every provider must hand back -- identical to what the yfinance path
returns today, so no consumer can tell the sources apart."""
import re
from zoneinfo import ZoneInfo

import pandas as pd

from swingbot.core.marketdata.asset_class import classify

NY = ZoneInfo("America/New_York")
SOURCE_ALPACA = "alpaca"
SOURCE_YF = "yfinance"
SOURCE_FALLBACK = "yfinance-fallback"

_US_SHAPE = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
_COLS = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}


def is_alpaca_eligible(ticker: str) -> bool:
    t = (ticker or "").upper().strip()
    if not _US_SHAPE.match(t):
        return False
    return classify(t) in {"equity", "etf"}


def to_alpaca_symbol(ticker: str) -> str:
    return ticker.upper().strip().replace("-", ".")


def _yf_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df[list(_COLS)].rename(columns=_COLS).astype("float64")


def to_yf_daily(df: pd.DataFrame) -> pd.DataFrame:
    out = _yf_columns(df)
    out.index = pd.DatetimeIndex(df.index).tz_convert(NY).normalize().tz_localize(None)
    out.index.name = "Date"
    return out


def to_yf_hourly(df30: pd.DataFrame) -> pd.DataFrame:
    frame = _yf_columns(df30)
    frame.index = pd.DatetimeIndex(df30.index).tz_convert(NY)
    frame = frame.between_time("09:30", "15:59")
    out = frame.resample("60min", origin="start_day", offset="30min",
                         label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
    out = out.dropna(subset=["Open"])
    out.index.name = "Datetime"
    return out
```

- [ ] **Step 4: Run it.** Same command → PASS. If `classify` has side
  effects (for example, a network lookup through `universe.is_etf`), stop and
  report rather than stubbing it silently.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/marketdata/providers tests/marketdata/test_providers_base.py
git commit -m "feat(v106): provider base -- Alpaca eligibility and yfinance frame contract"
```

### Task T3: `providers/alpaca_provider.py`

**Files:**
- Create: `swingbot/core/marketdata/providers/alpaca_provider.py`
- Test: `tests/marketdata/test_alpaca_provider.py`

**Interfaces:**
- Consumes: T2's `to_alpaca_symbol`, `to_yf_daily`, `to_yf_hourly`, `NY`.
- Produces:
  - `class AlpacaMiss(Exception)`
  - `class AlpacaAuthError(AlpacaMiss)`
  - `AlpacaProvider(key_id: str, secret: str, live_feed: str = "iex", *,
    client=None, now=None)` where `now: Callable[[], datetime]` returns an
    aware UTC datetime.
  - `.daily_bars(tickers: list[str], period: str) -> dict[str, pd.DataFrame]`
    (keyed by the yfinance ticker; missing symbols are absent)
  - `.intraday_bars(ticker: str, interval: str) -> pd.DataFrame | None`
  - `.latest_prices(tickers: list[str], max_trade_age_s: int) -> dict[str, float]`
  - Raises `AlpacaAuthError` on HTTP 401/403 and `AlpacaMiss` on any other
    client exception.

- [ ] **Step 1: Write the failing tests** against a fake client (no network).

```python
# tests/marketdata/test_alpaca_provider.py
from datetime import datetime, timezone
from types import SimpleNamespace
import pandas as pd
import pytest
from swingbot.core.marketdata.providers import alpaca_provider as ap

def _barset(symbols):
    rows = []
    for s in symbols:
        for d in ("2026-09-24 04:00", "2026-09-25 04:00"):
            rows.append((s, pd.Timestamp(d, tz="UTC"), 1.0, 2.0, 0.5, 1.5, 100.0, 5, 1.4))
    df = pd.DataFrame(rows, columns=["symbol", "timestamp", "open", "high", "low",
                                     "close", "volume", "trade_count", "vwap"])
    return SimpleNamespace(df=df.set_index(["symbol", "timestamp"]))

class FakeClient:
    def __init__(self, bars=None, snaps=None, exc=None):
        self.bars, self.snaps, self.exc, self.requests = bars, snaps, exc, []
    def get_stock_bars(self, req):
        self.requests.append(req)
        if self.exc: raise self.exc
        return self.bars
    def get_stock_snapshot(self, req):
        self.requests.append(req)
        if self.exc: raise self.exc
        return self.snaps

NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)   # 11:00 ET, in session

def _prov(client):
    return ap.AlpacaProvider("k", "s", "iex", client=client, now=lambda: NOW)

def test_daily_bars_uses_sip_all_adjustment_and_delayed_end():
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).daily_bars(["AAPL"], "2y")
    req = c.requests[0]
    assert str(req.feed.value) == "sip" and str(req.adjustment.value) == "all"
    assert req.end <= NOW - pd.Timedelta(minutes=15)
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]

def test_daily_bars_rekeys_class_shares():
    out = _prov(FakeClient(bars=_barset(["BRK.B"]))).daily_bars(["BRK-B"], "1y")
    assert set(out) == {"BRK-B"}

def test_symbol_absent_from_response_is_absent_from_result():
    out = _prov(FakeClient(bars=_barset(["AAPL"]))).daily_bars(["AAPL", "ZZZZ"], "1y")
    assert set(out) == {"AAPL"}

def _snap(price, ts):
    return SimpleNamespace(latest_trade=SimpleNamespace(price=price, timestamp=ts))

def test_latest_prices_fresh_trade():
    c = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(seconds=30))})
    assert _prov(c).latest_prices(["AAPL"], 300) == {"AAPL": 190.0}
    assert str(c.requests[0].feed.value) == "iex"

def test_stale_iex_trade_is_a_miss_in_session():
    c = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(minutes=20))})
    assert _prov(c).latest_prices(["AAPL"], 300) == {}

def test_old_trade_ok_outside_session():
    sat = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)
    c = FakeClient(snaps={"AAPL": _snap(190.0, sat - pd.Timedelta(hours=40))})
    p = ap.AlpacaProvider("k", "s", "iex", client=c, now=lambda: sat)
    assert p.latest_prices(["AAPL"], 300) == {"AAPL": 190.0}

def test_auth_error_maps_to_alpaca_auth_error():
    err = Exception("forbidden"); err.status_code = 403
    with pytest.raises(ap.AlpacaAuthError):
        _prov(FakeClient(exc=err)).daily_bars(["AAPL"], "1y")

def test_other_error_maps_to_miss():
    with pytest.raises(ap.AlpacaMiss):
        _prov(FakeClient(exc=RuntimeError("500"))).daily_bars(["AAPL"], "1y")

def test_intraday_only_1h_supported():
    assert _prov(FakeClient()).intraday_bars("AAPL", "1d") is None
```

- [ ] **Step 2: Run it.** `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
  → FAIL.
- [ ] **Step 3: Implement.** Check the exact enum and attribute names against
  the installed alpaca-py (`python -c "import alpaca.data.requests as r; help(r.StockBarsRequest)"`).
  If one differs, fix the code *and* the fake, and say so in the commit
  message.

```python
# swingbot/core/marketdata/providers/alpaca_provider.py
"""v106 Alpaca market-data provider (alpaca-py). Bars: SIP, >=16 min old,
fully adjusted. Live: last trade on the configured feed, never its volume.
Every failure is an AlpacaMiss so the router can fall back per symbol."""
from datetime import datetime, time as dtime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from swingbot.core.marketdata.providers.base import (
    NY, to_alpaca_symbol, to_yf_daily, to_yf_hourly)

SIP_DELAY = timedelta(minutes=16)
HISTORY_FLOOR = datetime(2016, 1, 1, tzinfo=timezone.utc)
_PERIOD_DAYS = {"1d": 5, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366,
                "2y": 731, "5y": 1827, "10y": 3653}
INTRADAY_DAYS = 700


class AlpacaMiss(Exception):
    """Alpaca could not answer; the router falls back to yfinance."""


class AlpacaAuthError(AlpacaMiss):
    """401/403 -- the router latches its breaker until the keys change."""


def _start_for(period: str, now: datetime) -> datetime:
    days = _PERIOD_DAYS.get(period)
    return HISTORY_FLOOR if days is None else max(HISTORY_FLOOR, now - timedelta(days=days))


def _in_regular_session(now: datetime) -> bool:
    ny = now.astimezone(NY)
    return ny.weekday() < 5 and dtime(9, 30) <= ny.time() < dtime(16, 0)


class AlpacaProvider:
    def __init__(self, key_id: str, secret: str, live_feed: str = "iex", *,
                 client=None, now=None):
        self._client = client or StockHistoricalDataClient(key_id, secret)
        self._live_feed = DataFeed(live_feed.lower())
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _call(self, method, req):
        try:
            return getattr(self._client, method)(req)
        except Exception as exc:
            if getattr(exc, "status_code", None) in (401, 403):
                raise AlpacaAuthError(str(exc)) from exc
            raise AlpacaMiss(str(exc)) from exc

    def _bars(self, tickers, timeframe, start):
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockBarsRequest(symbol_or_symbols=list(by_symbol), timeframe=timeframe,
                               start=start, end=self._now() - SIP_DELAY,
                               feed=DataFeed.SIP, adjustment=Adjustment.ALL)
        df = self._call("get_stock_bars", req).df
        if df is None or df.empty:
            return {}
        present = set(df.index.get_level_values("symbol"))
        return {by_symbol[s]: df.xs(s, level="symbol") for s in by_symbol if s in present}

    def daily_bars(self, tickers, period):
        now = self._now()
        raw = self._bars(tickers, TimeFrame.Day, _start_for(period, now))
        return {t: to_yf_daily(df) for t, df in raw.items() if not df.empty}

    def intraday_bars(self, ticker, interval):
        if interval != "1h":
            return None
        start = self._now() - timedelta(days=INTRADAY_DAYS)
        raw = self._bars([ticker], TimeFrame(30, TimeFrameUnit.Minute), start)
        df = raw.get(ticker)
        return None if df is None or df.empty else to_yf_hourly(df)

    def _fresh_price(self, snap, now, max_age_s):
        trade = getattr(snap, "latest_trade", None)
        if trade is None or not trade.price or trade.price <= 0:
            return None
        if _in_regular_session(now) and (now - trade.timestamp).total_seconds() > max_age_s:
            return None
        return float(trade.price)

    def latest_prices(self, tickers, max_trade_age_s):
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockSnapshotRequest(symbol_or_symbols=list(by_symbol), feed=self._live_feed)
        snaps = self._call("get_stock_snapshot", req) or {}
        now = self._now()
        out = {}
        for sym, snap in snaps.items():
            price = self._fresh_price(snap, now, max_trade_age_s) if sym in by_symbol else None
            if price is not None:
                out[by_symbol[sym]] = price
        return out
```

- [ ] **Step 4: Run it** → PASS. Then run `python -m radon cc -s -n C swingbot/core/marketdata/providers/`,
  which should print nothing.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/marketdata/providers/alpaca_provider.py tests/marketdata/test_alpaca_provider.py
git commit -m "feat(v106): AlpacaProvider -- SIP delayed bars, IEX last trade with in-session age guard"
```

### Task T4: `providers/router.py`

**Files:**
- Create: `swingbot/core/marketdata/providers/router.py`
- Test: `tests/marketdata/test_provider_router.py`

**Interfaces:**
- Consumes: T2 (`is_alpaca_eligible`, `SOURCE_*`), T3 (`AlpacaProvider`,
  `AlpacaMiss`, `AlpacaAuthError`), T1 config globals (read at call time).
- Produces:
  - `daily_bars(tickers: list[str], period: str, yf_fetch: Callable[[list[str], str], dict]) -> dict[str, pd.DataFrame]`
  - `latest_prices(tickers: list[str], yf_fetch: Callable[[list[str]], dict]) -> dict[str, float]`
  - `intraday_bars(ticker: str, interval: str, yf_fetch: Callable[[str, str], pd.DataFrame | None]) -> pd.DataFrame | None`
  - `last_source(ticker: str) -> str | None`
  - `stats() -> dict` (keys `alpaca`, `yfinance`, `fallback`, `failures`,
    `breaker_open`)
  - `reset() -> None`
  - Test seam: `_provider_factory` (module global, a callable returning an
    `AlpacaProvider`-like object).

- [ ] **Step 1: Write the failing tests.**

```python
# tests/marketdata/test_provider_router.py
import time
import pandas as pd
import pytest
from swingbot import config
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss

def _df():
    return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-09-25"]))

class FakeProvider:
    def __init__(self, daily=None, prices=None, exc=None, sleep=0):
        self.daily, self.prices, self.exc, self.sleep, self.calls = daily or {}, prices or {}, exc, sleep, 0
    def _maybe(self):
        self.calls += 1
        if self.sleep: time.sleep(self.sleep)
        if self.exc: raise self.exc
    def daily_bars(self, tickers, period):
        self._maybe(); return {t: _df() for t in tickers if t in self.daily}
    def latest_prices(self, tickers, max_age):
        self._maybe(); return {t: p for t, p in self.prices.items() if t in tickers}
    def intraday_bars(self, t, iv):
        self._maybe(); return None

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(config, "ALPACA_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 2)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 60)
    router.reset()
    yield
    router.reset()

def _use(monkeypatch, prov):
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)

def yf_daily(calls):
    def f(tickers, period):
        calls.append(list(tickers)); return {t: _df() for t in tickers}
    return f

def test_disabled_is_pure_yfinance(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False); router.reset()
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov); calls = []
    out = router.daily_bars(["AAPL"], "2y", yf_daily(calls))
    assert prov.calls == 0 and calls == [["AAPL"]]
    assert out["AAPL"].attrs["source"] == "yfinance"

def test_split_by_eligibility(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"})); calls = []
    out = router.daily_bars(["AAPL", "SAP.DE"], "2y", yf_daily(calls))
    assert calls == [["SAP.DE"]]
    assert out["AAPL"].attrs["source"] == "alpaca"
    assert out["SAP.DE"].attrs["source"] == "yfinance"

def test_partial_alpaca_result_falls_back_per_symbol(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"})); calls = []
    out = router.daily_bars(["AAPL", "MSFT"], "2y", yf_daily(calls))
    assert calls == [["MSFT"]]
    assert out["MSFT"].attrs["source"] == "yfinance-fallback"

def test_timeout_falls_back(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}, sleep=2)); calls = []
    t0 = time.monotonic()
    out = router.daily_bars(["AAPL"], "2y", yf_daily(calls))
    assert time.monotonic() - t0 < 1.5
    assert out["AAPL"].attrs["source"] == "yfinance-fallback"

def test_breaker_opens_then_cools_down(enabled, monkeypatch):
    prov = FakeProvider(exc=AlpacaMiss("500")); _use(monkeypatch, prov)
    for _ in range(3):
        router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 2 and router.stats()["breaker_open"] is True
    monkeypatch.setattr(router._breaker, "open_until", 0.0)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 3

def test_auth_error_latches_until_keys_change(enabled, monkeypatch):
    prov = FakeProvider(exc=AlpacaAuthError("401")); _use(monkeypatch, prov)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    monkeypatch.setattr(router._breaker, "open_until", 0.0)
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 1                      # latched, not cooled down
    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k2")
    prov.exc = None
    router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 2                      # new keys -> new client, latch cleared

def test_latest_prices_records_last_source(enabled, monkeypatch):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    out = router.latest_prices(["AAPL", "SAP.DE"], lambda ts: {t: 50.0 for t in ts})
    assert out == {"AAPL": 190.0, "SAP.DE": 50.0}
    assert router.last_source("AAPL") == "alpaca"
    assert router.last_source("SAP.DE") == "yfinance"

def test_bucket_exhausted_is_a_miss(enabled, monkeypatch):
    prov = FakeProvider(daily={"AAPL"}); _use(monkeypatch, prov)
    monkeypatch.setattr(router._bucket, "tokens", 0.0)
    monkeypatch.setattr(router._bucket, "refill_per_s", 0.0)
    out = router.daily_bars(["AAPL"], "2y", yf_daily([]))
    assert prov.calls == 0 and out["AAPL"].attrs["source"] == "yfinance-fallback"
```

- [ ] **Step 2: Run it.** `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
  → FAIL.
- [ ] **Step 3: Implement.**

```python
# swingbot/core/marketdata/providers/router.py
"""v106 router: Alpaca first for eligible US symbols, yfinance for the rest
and for every Alpaca miss -- per symbol, never per batch. The yfinance path is
injected as `yf_fetch` (today's code, unchanged), so with ALPACA_ENABLED off
this module is a pass-through that only adds source tags.

Config is read at call time; the provider is cached per (key_id, secret) so
rotated keys take effect on the next call in any process -- the admin
container has no on_config_reload hook."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from swingbot import config
from swingbot.core.marketdata.providers.alpaca_provider import (
    AlpacaAuthError, AlpacaMiss, AlpacaProvider)
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_YF, is_alpaca_eligible)

log = logging.getLogger(__name__)
_provider_factory = AlpacaProvider
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alpaca")
_lock = threading.Lock()


class _Bucket:
    def __init__(self, per_minute=150):
        self.capacity = float(per_minute)
        self.tokens = float(per_minute)
        self.refill_per_s = per_minute / 60.0
        self.stamp = time.monotonic()

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.stamp) * self.refill_per_s)
        self.stamp = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class _Breaker:
    def __init__(self):
        self.fails, self.open_until, self.auth_latched = 0, 0.0, False

    def allows(self) -> bool:
        return not self.auth_latched and time.monotonic() >= self.open_until

    def record(self, ok: bool, auth: bool = False) -> None:
        was_open = not self.allows()
        if ok:
            self.fails = 0
        else:
            self.fails += 1
            self.auth_latched = self.auth_latched or auth
            if self.fails >= int(config.ALPACA_BREAKER_FAILURES):
                self.open_until = time.monotonic() + float(config.ALPACA_BREAKER_COOLDOWN_SECONDS)
        if was_open != (not self.allows()):
            log.warning("Alpaca breaker %s", "OPEN" if not self.allows() else "closed")


_bucket = _Bucket()
_breaker = _Breaker()
_provider = None
_provider_key = None
_last_source: dict = {}
_stats = {"alpaca": 0, "yfinance": 0, "fallback": 0, "failures": 0}


def reset() -> None:
    global _provider, _provider_key, _bucket, _breaker
    _provider, _provider_key = None, None
    _bucket, _breaker = _Bucket(), _Breaker()
    _last_source.clear()
    for k in _stats:
        _stats[k] = 0


def _active_provider():
    global _provider, _provider_key, _breaker
    if not config.ALPACA_ENABLED or not config.ALPACA_API_KEY_ID:
        return None
    key = (config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY)
    with _lock:
        if key != _provider_key:
            _provider = _provider_factory(key[0], key[1], config.ALPACA_DATA_FEED_LIVE)
            _provider_key, _breaker = key, _Breaker()
    return _provider if _breaker.allows() else None


def _attempt(method: str, *args):
    """One bounded Alpaca call. Returns its result, or None on any miss."""
    prov = _active_provider()
    if prov is None or not _bucket.take():
        return None
    try:
        result = _pool.submit(getattr(prov, method), *args).result(
            timeout=float(config.ALPACA_TIMEOUT_SECONDS))
    except (AlpacaMiss, FutureTimeout, Exception) as exc:
        _stats["failures"] += 1
        _breaker.record(False, auth=isinstance(exc, AlpacaAuthError))
        log.info("Alpaca %s miss: %s", method, exc)
        return None
    _breaker.record(True)
    return result


def _split(tickers):
    """(Alpaca-bound, yfinance-bound). Disabled or breaker-open means every
    ticker is plain yfinance -- tagged SOURCE_YF, never SOURCE_FALLBACK."""
    if _active_provider() is None:
        return [], list(tickers)
    wanted = [t for t in tickers if is_alpaca_eligible(t)]
    chosen = set(wanted)
    return wanted, [t for t in tickers if t not in chosen]


def _tag(frames: dict, source: str) -> dict:
    for df in frames.values():
        df.attrs["source"] = source
    return frames


def _merge(alpaca: dict, rest: list, misses: list, fetch) -> dict:
    out = _tag(dict(alpaca), SOURCE_ALPACA)
    out.update(_tag(fetch(rest), SOURCE_YF) if rest else {})
    out.update(_tag(fetch(misses), SOURCE_FALLBACK) if misses else {})
    _stats["alpaca"] += len(alpaca)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    return out


def daily_bars(tickers, period, yf_fetch):
    wanted, rest = _split(tickers)
    got = (_attempt("daily_bars", wanted, period) or {}) if wanted else {}
    misses = [t for t in wanted if t not in got]
    return _merge(got, rest, misses, lambda ts: yf_fetch(ts, period))


def latest_prices(tickers, yf_fetch):
    wanted, rest = _split(tickers)
    got = (_attempt("latest_prices", wanted,
                    int(config.ALPACA_MAX_TRADE_AGE_SECONDS)) or {}) if wanted else {}
    misses = [t for t in wanted if t not in got]
    out = dict(got)
    for group, source in ((rest, SOURCE_YF), (misses, SOURCE_FALLBACK)):
        fetched = yf_fetch(group) if group else {}
        out.update(fetched)
        _last_source.update({t: source for t in fetched})
    _last_source.update({t: SOURCE_ALPACA for t in got})
    _stats["alpaca"] += len(got)
    _stats["yfinance"] += len(rest)
    _stats["fallback"] += len(misses)
    return out


def intraday_bars(ticker, interval, yf_fetch):
    if not is_alpaca_eligible(ticker) or _active_provider() is None:
        df = yf_fetch(ticker, interval)
        source = SOURCE_YF
    else:
        df = _attempt("intraday_bars", ticker, interval)
        source = SOURCE_ALPACA
        if df is None or df.empty:
            df, source = yf_fetch(ticker, interval), SOURCE_FALLBACK
    if df is not None:
        df.attrs["source"] = source
    return df


def last_source(ticker: str):
    return _last_source.get(str(ticker).upper().strip())


def stats() -> dict:
    return {**_stats, "enabled": bool(config.ALPACA_ENABLED),
            "breaker_open": not _breaker.allows()}
```

- [ ] **Step 4: Run it** → PASS. Run radon on `router.py`; nothing ≥ C.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/marketdata/providers/router.py tests/marketdata/test_provider_router.py
git commit -m "feat(v106): provider router -- per-symbol fallback, timeout, breaker, bucket, source tags"
```

# Phase B — Wiring

### Task T5: Characterization tests pinning today's behaviour

**Files:**
- Test: `tests/marketdata/test_alpaca_killswitch.py`

**Interfaces:**
- Consumes: the public `data.py` / `data_store.py` functions as they are
  **before** T6/T7 edit them.
- Produces: tests T6 and T7 must keep green with `ALPACA_ENABLED=False`.

- [ ] **Step 1: Write the tests against the unmodified code.** Use the
  existing fake idioms: `monkeypatch.setattr(data_mod.yf, "download", fake)`
  (see `tests/marketdata/test_data.py:38ff`) and the `yf.Ticker` fake from
  `tests/marketdata/test_current_price_staleness.py:32-34`. For each of
  `get_daily_data("AAPL")`, `get_daily_data_batch(["AAPL","SAP.DE"])`,
  `get_current_price_batch(["AAPL"], allow_stale=False)`,
  `get_current_price_detail("AAPL", allow_stale=False)` and
  `data_store.get_intraday("AAPL", base_dir=tmp_path)`, feed a fixed fake
  yfinance frame and assert **exact** equality
  (`pd.testing.assert_frame_equal` / `==`) with the expected output, written
  out literally in the test. Also assert the fake `download` received the same
  args as today: capture `args`/`kwargs` and assert `group_by="ticker"`,
  `auto_adjust=True`, `period="2y"` for the batch call.

```python
# tests/marketdata/test_alpaca_killswitch.py  (skeleton -- one test per function)
import pandas as pd
import pytest
from swingbot import config
from swingbot.core.marketdata import data as data_mod

@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)

def _yf_batch_frame(tickers):
    idx = pd.DatetimeIndex(["2026-09-24", "2026-09-25"])
    cols = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
    return pd.DataFrame(1.0, index=idx, columns=cols)

def test_daily_batch_unchanged_when_disabled(monkeypatch):
    seen = {}
    def fake(*a, **k):
        seen.update(k); seen["arg"] = a[0]; return _yf_batch_frame(["AAPL", "SAP.DE"])
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_mod.get_daily_data_batch(["aapl", "SAP.DE"])
    assert seen["arg"] == "AAPL SAP.DE" and seen["group_by"] == "ticker"
    assert seen["auto_adjust"] is True and seen["period"] == "2y"
    assert set(out) == {"AAPL", "SAP.DE"}
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]
```

  Write the other four tests the same way, each with its own literal expected
  output.

- [ ] **Step 2: Run it.** `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_killswitch.py`
  → **PASS on unmodified code.** A failure here means the test is wrong, not
  the code. Fix the test.
- [ ] **Step 3: Commit.**

```bash
git add tests/marketdata/test_alpaca_killswitch.py
git commit -m "test(v106): pin pre-Alpaca yfinance behaviour of every live-path fetch"
```

### Task T6: Route `data.py` through the router

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (`get_daily_data` 27,
  `get_daily_data_batch` 59, `get_current_price_batch` 123,
  `get_current_price_detail` 446)
- Test: `tests/marketdata/test_data_alpaca_routing.py`

**Interfaces:**
- Consumes: T4 `router.daily_bars`, `router.latest_prices`.
- Produces:
  - `data._yf_daily_batch(tickers: list[str], period: str) -> dict[str, pd.DataFrame]`
    (today's download + slicing, verbatim)
  - `data._yf_batch_prices(tickers: list[str]) -> dict[str, float]` (today's
    1-minute download + last-close extraction, verbatim)

- [ ] **Step 1: Write the failing routing tests.** Fake the router's provider
  as in T4 (`router._provider_factory`), with `ALPACA_ENABLED=True`:
  - `get_daily_data_batch(["AAPL","SAP.DE"])`: `AAPL` comes from the fake
    Alpaca and has `attrs["source"]=="alpaca"`; `SAP.DE` comes via the fake
    `yf.download`.
  - `get_daily_data("AAPL")`: Alpaca hit; `yf.download` is never called.
  - `get_daily_data("^GSPC")`: goes straight to the existing
    `candidate_symbols` loop.
  - `get_current_price_batch(["AAPL"], allow_stale=False)`: the Alpaca price
    is returned **and** written to `_last_good_batch_price`.
  - `get_current_price_detail("AAPL", allow_stale=False)`: an Alpaca hit gives
    `PriceQuote(190.0, False)` and populates `_price_cache["AAPL"]`; an Alpaca
    miss runs the existing `yf.Ticker(...).history` path.
- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement, as minimal extractions.**
  - `get_daily_data_batch`: move everything after the dedupe/empty check into
    `_yf_daily_batch(tickers, period)` **unchanged**, including the
    `with_retry` call, the log line and the per-ticker slice loop. The body
    becomes `return router.daily_bars(tickers, period, _yf_daily_batch)`.
  - `get_daily_data`: before the `candidate_symbols` loop, add

```python
    if is_alpaca_eligible(ticker):
        hit = router.daily_bars([ticker.upper().strip()], period,
                                lambda ts, p: {}).get(ticker.upper().strip())
        if hit is not None and not hit.empty:
            return hit
```

    The `lambda ts, p: {}` means an Alpaca miss comes back empty, so the
    existing aliasing loop runs exactly as before.
  - `get_current_price_batch`: extract the network step (the 1-minute
    `yf_safe.download(... period="1d", interval="1m", group_by="ticker",
    prepost=True)` plus the last-non-NaN `Close > 0` extraction) into
    `_yf_batch_prices(tickers) -> {t: float}`, and call
    `router.latest_prices(to_fetch, _yf_batch_prices)` in its place. Keep
    every cache read/write, both TTLs and `_stale_batch_fallback` exactly
    where they are. The existing error handling around the download moves
    into `_yf_batch_prices` (return `{}` where it returned `{}` before).
  - `get_current_price_detail`: before the `candidate_symbols` loop, add

```python
    if is_alpaca_eligible(ticker_key):
        price = router.latest_prices([ticker_key], lambda ts: {}).get(ticker_key)
        if price:
            _price_cache[ticker_key] = (price, now, False)
            return PriceQuote(price, False)
```

  - Imports: `from swingbot.core.marketdata.providers import router` and
    `from swingbot.core.marketdata.providers.base import is_alpaca_eligible`.
- [ ] **Step 4: Run the routing tests, the characterization tests, and the
  existing data tests.** Each runs separately:
  `python scripts/dev/testrun.py file tests/marketdata/test_data_alpaca_routing.py`,
  `... file tests/marketdata/test_alpaca_killswitch.py`,
  `... file tests/marketdata/test_data.py`,
  `... file tests/marketdata/test_current_price_staleness.py`. All must PASS.
- [ ] **Step 5: Check complexity.** `python -m radon cc -s -n C swingbot/core/marketdata/data.py`:
  `get_current_price_batch` must rate lower than D(23), and no touched
  function may be higher than before (`get_current_price_detail` C(12),
  `get_daily_data_batch` C(11)). If `get_current_price_detail` reaches 15,
  move the Alpaca block into `_alpaca_price_quote(ticker_key, now)`.
- [ ] **Step 6: Commit.**

```bash
git add swingbot/core/marketdata/data.py tests/marketdata/test_data_alpaca_routing.py
git commit -m "feat(v106): route live daily bars and prices through the provider router"
```

### Task T7: Route `data_store.get_intraday` through the router

**Files:**
- Modify: `swingbot/core/marketdata/data_store.py:432` (`get_intraday`,
  `_default_fetch`)
- Test: `tests/marketdata/test_universe.py` (beside the existing
  `get_intraday` tests at ~221/240)

**Interfaces:**
- Consumes: T4 `router.intraday_bars`.
- Produces: none new.

- [ ] **Step 1: Write the failing test.** With `ALPACA_ENABLED=True` and a
  fake provider whose `intraday_bars` returns a Yahoo-shaped 1h frame (09:30
  grid, tz NY), `get_intraday("AAPL", base_dir=tmp_path)` returns it, and the
  CSV it writes merges cleanly with a pre-existing yfinance-built CSV (no
  duplicate timestamps: `assert not merged.index.duplicated().any()`). A
  second test: when `fetch_fn=` is injected, the router is bypassed
  (unchanged behaviour).
- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement.** Only the default fetch changes:

```python
    def _default_fetch(sym, iv):
        def _yf(s, i):
            df = yf_safe.download(s, period="700d", interval=i,
                                  auto_adjust=True, progress=False)
            return _normalize_columns(df) if df is not None and not df.empty else None
        return router.intraday_bars(sym, iv, _yf)
```

- [ ] **Step 4: Run it.** `python scripts/dev/testrun.py file tests/marketdata/test_universe.py`
  and `... file tests/marketdata/test_alpaca_killswitch.py` → PASS.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/marketdata/data_store.py tests/marketdata/test_universe.py
git commit -m "feat(v106): intraday 1h bars via Alpaca (09:30-grid), yfinance fallback"
```

# Phase C — Observability

### Task T8: Source counts in scan telemetry

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (the `scan_stats` dict,
  ~963)
- Test: `tests/scanning/test_scan_telemetry_sources.py` (create it; if
  `tests/scanning/` doesn't exist, put the file beside the existing scan
  telemetry tests: `git grep -ln log_scan_telemetry tests`)

**Interfaces:**
- Consumes: `frame.attrs["source"]` on `fresh_data` values
  (`fresh_data = fetch._crawl_latest_data(tickers, progress)`, scan_run.py:216).
- Produces: the telemetry row key `data_sources: {"alpaca": int, "yfinance":
  int, "yfinance-fallback": int, "cache": int}`, where `cache` counts frames
  with no source tag (served from the on-disk cache).

- [ ] **Step 1: Pickle round-trip test first.** Push a tagged frame through
  `_run_bounded` (`scanning/fetch.py:94`) using a module-level helper that
  returns it, then assert `attrs["source"]` survived:

```python
def _tagged():
    import pandas as pd
    df = pd.DataFrame({"Close": [1.0]}); df.attrs["source"] = "alpaca"; return df

def test_attrs_survive_spawn_round_trip():
    from swingbot.core.scanning.fetch import _run_bounded
    out = _run_bounded(_tagged, (), 30, "attrs-probe")
    assert out.attrs.get("source") == "alpaca"
```

  **If this fails,** change `_fetch_cold_frames`'s child function to return
  `(frames, {t: df.attrs.get("source")})`, re-apply the tags in the parent,
  and add a test for that. Record which branch you took in the commit message.
- [ ] **Step 2: Write the failing test** for a helper
  `_count_sources(frames: dict) -> dict`, placed at module level in
  `scan_run.py`: `{"AAPL": df(source=alpaca), "SAP.DE": df(source=yfinance),
  "X": df(no tag)}` gives `{"alpaca": 1, "yfinance": 1,
  "yfinance-fallback": 0, "cache": 1}`.
- [ ] **Step 3: Implement** `_count_sources` and add
  `"data_sources": _count_sources(fresh_data)` to `scan_stats`.
- [ ] **Step 4: Run it** → PASS.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/core/scanning/scan_run.py tests/scanning/test_scan_telemetry_sources.py
git commit -m "feat(v106): per-scan data_sources counts in scan telemetry"
```

### Task T9: Admin API — `data_sources` in scan health, `price_source` on watchlist rows

**Files:**
- Modify: `swingbot/admin/api_v1/risk.py:79` (`_scan_health`)
- Modify: `swingbot/admin/watchlist_rows.py` (`build_market_rows`)
- Test: the existing risk API test file (`git grep -ln "_scan_health\|/api/v1/risk" tests`)
  and `tests/admin/test_watchlist_rows.py`

**Interfaces:**
- Consumes: T4 `router.stats()`, `router.last_source(t)`; T8 telemetry key
  `data_sources`.
- Produces:
  - `GET /api/v1/risk` → `scan_health.data_sources = {"enabled": bool,
    "feed": str, "breaker_open": bool, "fallback_rate": float | None,
    "scans": int}`. `fallback_rate` = Σ yfinance-fallback / Σ (alpaca +
    yfinance-fallback) over the last 20 telemetry rows that carry
    `data_sources`; `None` when that denominator is 0.
  - Watchlist row field `price_source: "alpaca" | "yfinance" |
    "yfinance-fallback" | null`.

- [ ] **Step 1: Write the failing tests.**
  - Risk: seed `recent_telemetry` with two rows, `data_sources`
    `{alpaca: 9, yfinance-fallback: 1}` and `{alpaca: 10,
    yfinance-fallback: 0}`, and assert `fallback_rate == 0.05` and
    `scans == 2`.
  - Watchlist: monkeypatch `router.last_source` → `"alpaca"` and assert the
    row carries `price_source == "alpaca"`. With no price, assert `None`.
- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement** a helper `_data_sources_summary(rows)` in
  `risk.py`, called from `_scan_health` inside the existing
  `try/except Exception` so a failure degrades to the current response plus
  `data_sources: None`. In `build_market_rows`, set
  `row["price_source"] = router.last_source(ticker)` beside where the price is
  set.
- [ ] **Step 4: Run both test files** → PASS.
- [ ] **Step 5: Commit.**

```bash
git add swingbot/admin/api_v1/risk.py swingbot/admin/watchlist_rows.py tests/
git commit -m "feat(v106): expose data-source health and per-row price source in the admin API"
```

### Task T10: Frontend — data-source card and watchlist source badge

**Files:**
- Modify: `frontend/src/app/api/models.ts` (add fields)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (+ its template/spec)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (+ spec)

**Interfaces:**
- Consumes: T9's `scan_health.data_sources` and row `price_source`.
- Produces: none.

- [ ] **Step 1: Write failing specs.**
  - `risk.spec.ts`: with `data_sources = {enabled: true, feed: 'iex',
    breaker_open: false, fallback_rate: 0.05, scans: 20}`, the card shows
    "Alpaca · IEX", "5.0% fallback (20 scans)". With `breaker_open: true` it
    shows a warning state. With `enabled: false` it shows "yfinance only".
  - `watchlist.spec.ts`: a row with `price_source: 'yfinance-fallback'` shows
    a "fallback" badge; `'alpaca'` shows none (the default is quiet). Only the
    exception is flagged, which matches how `current_price_stale` is shown.
- [ ] **Step 2: Run them.** `cd frontend && npm test -- --include src/app/workspaces/risk/risk.spec.ts`
  (then the watchlist spec) → FAIL.
- [ ] **Step 3: Implement.** Reuse the existing design-system tokens and the
  scan-health card's structure, and put the badge in the same cell as the
  stale indicator. Types:

```ts
export interface DataSourcesHealth {
  enabled: boolean; feed: string; breaker_open: boolean;
  fallback_rate: number | null; scans: number;
}
// ScanHealth: data_sources?: DataSourcesHealth | null
// WatchlistRow: price_source?: 'alpaca' | 'yfinance' | 'yfinance-fallback' | null
```

- [ ] **Step 4: Run both specs** → PASS.
- [ ] **Step 5: Commit.**

```bash
git add frontend/src/app
git commit -m "feat(v106): Risk data-source card and watchlist fallback badge"
```

### Task T11: Parity report script

**Files:**
- Create: `scripts/reports/provider_parity_report.py`
- Test: `tests/reports/test_provider_parity_report.py` (or beside the existing
  report tests: `git grep -ln shadow_parity_report tests`)

**Interfaces:**
- Consumes: T3 `AlpacaProvider.daily_bars` / `.latest_prices`; the yfinance
  path via `data._yf_daily_batch` / `data._yf_batch_prices`; T2
  `is_alpaca_eligible`; the watchlist loader in
  `swingbot/core/marketdata/watchlist.py`.
- Produces: the CLI `python scripts/reports/provider_parity_report.py
  [--symbols A,B] [--sessions 60] [--json out.json]`, and a pure function
  `compare_daily(alpaca: dict, yf: dict) -> dict` with keys `symbols`,
  `close_bps_median`, `close_bps_p95`, `close_bps_max`, `missing_alpaca`,
  `missing_yf`, `action_mismatches: list[{symbol, date, bps}]`,
  `volume_ratio_median`.

- [ ] **Step 1: Write the failing test** for `compare_daily` on hand-built
  frames:
  - identical → 0 bps;
  - one day off by 1% → `close_bps_max == 100`;
  - that day listed in `action_mismatches` (> 50 bps on a single date);
  - a date present in only one source is counted in the matching `missing_*`.
- [ ] **Step 2: Run it** → FAIL.
- [ ] **Step 3: Implement.**
  - `compare_daily` is pure pandas.
  - `main()` builds an `AlpacaProvider` from `config`, calls both sources
    through their functions directly (**not** the router, so a fallback can't
    hide a difference), and prints a fixed-width table plus the live-price
    difference (IEX vs yfinance 1-minute last) per symbol.
  - Per-symbol progress goes to stdout with `flush=True`.
  - Exit 2 with a clear message if the keys are unset.
- [ ] **Step 4: Run it** → PASS. Keep every function under complexity 15.
- [ ] **Step 5: Commit.**

```bash
git add scripts/reports/provider_parity_report.py tests/
git commit -m "feat(v106): Alpaca-vs-yfinance provider parity report"
```

# Phase D — Verification, rollout, close-out

### Task T12: Full-suite verification

Run `python scripts/dev/testrun.py full` (or dispatch the `test-runner`
subagent) once, over everything this plan implemented. Expect `0 failed`,
`0 xfailed`. Also run `cd frontend && npm test` once. **If either is not
green, fix forward from those failures.** They are this plan's regressions,
and this task isn't done until both runs are green. Also run
`python -m py_compile` over the touched modules and
`python -m radon cc -s -n C swingbot/core/marketdata/` (nothing new ≥ 15;
`get_current_price_batch` lower than before).

### Task T13: Production rollout and pre-registered soak

Use the `mirror-prod` and `worktree-lifecycle` skills. Production is the
Hetzner VM.

- [x] **Step 1:** Merge to `main`. Deploy (`docs/deploy/DEPLOY_HETZNER.md`)
  with `ALPACA_ENABLED` absent (false). Confirm the containers are healthy and
  a scan completes. Nothing should change observably.
  *Done 2026-09-27: merge 00e9d2bb, CI run 36308021440 green, both
  containers healthy, `ALPACA_ENABLED=False` in the bot. Deployed on a
  Sunday -- the first post-deploy scan is Monday's.*
- [x] **Step 2:** The **user** creates the Alpaca account and keys. Add
  `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` to the production `.env`
  (never commit values). Mirror the placeholder names into `.env.example` if
  they differ from T1's, and commit.
  *Done 2026-09-27. Names match T1. A first `CK…` pair (Broker API) got 401;
  the replacement `PK…` paper-trading pair authenticates: daily, 1h and
  latest-trade calls all answer (valid keys are 26/44 chars, not 20/40).*
- [x] **Step 3:** On production, run
  `python scripts/reports/provider_parity_report.py --json /tmp/parity.json`
  and bring the summary back. **Pre-registered clause (d):** median close
  difference ≤ 5 bps, and every `action_mismatches` row explained (a known
  split/dividend date, and which side is right).
  *Result 2026-09-27, 75 eligible watchlist symbols x 60 sessions: close
  bps median 0.0, p95 0.28, max 9.38 (ILMN); missing_alpaca 0, missing_yf 0;
  volume ratio median 1.00; action_mismatches 0. **Clause (d) PASS.** Live
  diffs up to ~71 bps are a weekend artefact (IEX last print vs yfinance
  prepost 1m last) and are not part of the gate.*
- [x] **Step 4:** Record the baseline: the last 5 trading days of
  `data/scan_telemetry.jsonl` (cold-fetch phase times, `errors`,
  `data_skips`, `tickers`).
  *Baseline 2026-09-21..25 (yfinance only), ~180 scans/day, 77 tickers:*

  | day | scans | errors | data_skips | crawl p50 s | crawl p95 s | crawl max s |
  |---|---|---|---|---|---|---|
  | 09-21 | 180 | 0 | 180 | 12.68 | 14.68 | 25.11 |
  | 09-22 | 181 | 0 | 181 | 12.58 | 18.36 | 21.81 |
  | 09-23 | 180 | 0 | 180 | 12.47 | 19.11 | 22.51 |
  | 09-24 | 180 | 0 | 180 | 9.31 | 16.90 | 22.05 |
  | 09-25 | 180 | 0 | 180 | 0.40 | 14.53 | 27.12 |

  *(errors + data_skips) / tickers = **0.01299** over 69,377 ticker-scans
  (one ticker is data-skipped every scan).*

  **Finding (recorded before Step 5, so before any soak data exists):**
  clause (a) names "the cold-fetch phase in `phases_s`", but `phases_s`
  has no such phase -- only `crawl`, which also holds warm-cache loads,
  per-chunk process spawn and the sequential remainder loop (baseline p95
  14.5-19.1 s). (a) cannot be read as written. Clause (b)'s
  `data_sources` counts only the scan's daily frames, most of which are
  disk-cache hits kept warm by the yfinance-only refresh loop; the per-scan
  live-price batch -- Alpaca's largest share of traffic -- is not counted
  at all. Both measurements must be fixed before the flag goes on, never
  after.
- [x] **Step 5:** Set `ALPACA_ENABLED=true` and send SIGHUP to both
  containers. Soak for **5 trading days**.
  *Flag on 2026-09-27 ~10:28 UTC (Sunday, user's call), after the soak
  telemetry deploy (bd99ebd4). Soak window = trading days 2026-09-28 ..
  2026-10-02. **Trap:** `sed -i` on the host `.env` replaces the file, and
  the single-file bind mount `./.env:/app/.env` keeps the old inode -- the
  SIGHUP reported "no changes" and the containers still read `false`. A
  `docker compose restart bot admin` re-binds it; edit in place (or via the
  admin UI) to avoid that. First Alpaca-on scan (user `/check`, 10:29-10:31
  UTC): price_sources alpaca 75 / fallback 0 / none 2 (GC=F, SI=F --
  ineligible, no yfinance weekend price), live_prices phase 6.2 s vs ~11.6 s
  baseline, cold_fetch_s [1.03], errors 0, data_skips 1, 0 alerts.*
- [ ] **Step 6: Acceptance.** All of these must hold:
  - (a) p95 cold `get_daily_data_batch` wall time < 3 s (taken from the
    cold-fetch phase in `phases_s`);
  - (b) fallback rate < 5% of eligible symbol-fetches (from `data_sources`);
  - (c) (`errors` + `data_skips`) / `tickers` no worse than the baseline;
  - (d) from Step 3.

  **Any failed clause:** set `ALPACA_ENABLED=false`, send SIGHUP, and write up
  the failure. Do not tune thresholds after the fact.

  **Measurement definitions -- fixed 2026-09-27, before the flag went on
  and before any soak row existed** (resolves the Step 4 finding; the user
  chose to add telemetry rather than read `crawl`). Thresholds unchanged:
  - (a) reads telemetry key `cold_fetch_s`: the in-worker wall time of each
    `get_daily_data_batch` chunk (the call itself, not process spawn),
    pooled over every scan in the 5 soak days; p95 < 3 s. A soak with fewer
    than 20 chunk timings in total cannot pass (a) -- it is reported as
    unmeasured, not as a pass.
  - (b) pools telemetry keys `data_sources` (daily frames) and
    `price_sources` (live-price batch answers): Σ yfinance-fallback /
    Σ (alpaca + yfinance-fallback) over the soak rows < 5%. This is the
    figure the Risk page's data-source card shows.
  - (c) as written, against the Step 4 baseline 0.01299.

  **Soak attempt 1 -- FAILED on day 1 (2026-09-28), recorded before any fix.**
  148 scans 06:04-18:18 UTC: (a) p95 `cold_fetch_s` **13.99 s** (224 timings,
  max 18.75) -- FAIL; (b) fallback **48.99%** (2809 / 5734) -- FAIL; (c)
  0.01299 -- PASS (equal); (d) PASS. Every `Alpaca daily_bars miss:` line had
  empty text -- `str(FutureTimeout())` is `""`, so all 45 were the 5 s router
  timeout; the first all-fallback scan was 13:39 UTC (US open), all-fallback
  from 18:00. **Root cause, measured on production 19:01 UTC:** the scan's
  one request (75 symbols, 2y, SIP) is 36,843 rows = **4 sequential 10k-row
  pages, 3.9-4.8 s** whether or not today's forming bar is included, and
  whether adjusted or raw; SPY alone is 0.14-0.26 s. So the call sits at the
  timeout and tips over under session load, and even a successful call can
  never meet (a)'s 3 s. The user chose to fix it inside v106 with Alpaca left
  on (**T13a**), then restart the soak from Step 5 with **every threshold and
  measurement definition above unchanged**.

### Task T13a: Page-sized parallel daily-bar requests

**Files:** modify `swingbot/core/marketdata/providers/alpaca_provider.py`,
`swingbot/core/marketdata/providers/router.py`; tests in
`tests/marketdata/test_alpaca_provider.py`, `tests/marketdata/test_provider_router.py`.

**Design.** Alpaca already batches many symbols per request; the cost is
pagination (10,000 rows per page, fetched one after another inside
alpaca-py). So split the eligible symbols into batches that each fit **one**
page, and send the batches **in parallel**. Same HTTP request count as today
(4 for the live watchlist) -- no extra rate-limit pressure -- but each bucket
token now pays for exactly one HTTP call, where today one token covers 4.

- `alpaca_provider.symbols_per_request(period, now=None) -> int`:
  `rows = (now - _start_for(period, now)).days * 252 // 365 + 10`
  (trading-day estimate plus margin; holidays make it an over-estimate);
  return `max(1, ROWS_PER_PAGE // rows)` with `ROWS_PER_PAGE = 10_000`.
  `"2y"` gives 19 (measured 491 rows/symbol, 19 × 491 = 9,329 < 10,000).
- `router.daily_bars` slices `wanted` into consecutive batches of that size
  and calls a new `_attempt_many("daily_bars", batches, period)`:
  - one `_bucket.take()` per batch, **in the calling thread**; a batch with no
    token is not submitted (its symbols become misses → yfinance-fallback);
  - every submitted batch runs on `_pool` (4 workers) under **one shared
    deadline** `now + ALPACA_TIMEOUT_SECONDS`, so the whole call still returns
    within the timeout plus the yfinance time (Review Focus 4 holds);
  - each batch result is collected in the calling thread and recorded on the
    breaker on its own (bucket, breaker and `_stats` stay single-threaded);
  - a failed or timed-out batch sends **only its own symbols** to yfinance.
- Factor the per-future collection out of `_attempt` into
  `_collect(future, method, deadline)`, used by both. `_attempt`'s
  behaviour for `latest_prices` and `intraday_bars` is unchanged.
- The miss log names the exception type when its text is empty:
  `log.info("Alpaca %s miss: %s", method, str(exc) or type(exc).__name__)`
  (today's 45 blank lines are why).
- `latest_prices` and `intraday_bars` are out of scope (one snapshot call;
  one symbol).

- [ ] **Step 1: Failing tests.** Provider:
  `test_symbols_per_request_fits_one_page` (`"2y"` → 19; `"10y"` and an
  unknown period each ≥ 1 with `n × rows ≤ 10_000`). Router -- extend
  `FakeProvider` to record each `daily_bars` batch and to raise for a batch
  containing a given symbol; monkeypatch `alpaca_provider.symbols_per_request`
  (as imported by the router) to a small size:
  - `test_daily_bars_sends_page_sized_batches` (45 tickers, size 20 →
    batches of 20, 20, 5; all tagged `alpaca`);
  - `test_failed_batch_falls_back_only_its_symbols`;
  - `test_batches_run_in_parallel_under_one_deadline` (3 batches sleeping
    0.3 s, timeout 0.5 s → all `alpaca`, wall < 0.5 s);
  - `test_each_batch_takes_a_bucket_token` (2 tokens, no refill, 3 batches →
    the third batch's symbols are `yfinance-fallback`);
  - `test_miss_log_names_timeout` (caplog contains `TimeoutError`).
  Run `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
  and the provider test file: the new tests fail, the old ones pass.
- [ ] **Step 2: Implement** as designed. Both test files green, plus
  `tests/marketdata/test_data_alpaca_routing.py` and
  `tests/scanning/test_scan_telemetry_sources.py`.
- [ ] **Step 3: Complexity.** `python -m radon cc -s -n C` on both modules
  prints nothing.
- [ ] **Step 4: Full suite** via the `test-runner` agent (this task follows
  T12's run): `0 failed`, `0 xfailed`.
- [ ] **Step 5: Merge and deploy** (`docs/deploy/DEPLOY_HETZNER.md`), Alpaca
  still on. Confirm on the first market-hours scan after deploy: no
  `daily_bars miss` lines, `data_sources` fallback 0, `cold_fetch_s` for the
  Alpaca chunk under 3 s.
- [ ] **Step 6: Restart the soak.** Soak attempt 2 = the 5 trading days
  starting the first full trading day after the deploy; record the window
  here, then run T13 Step 6 unchanged.

  *Recorded 2026-10-02 (the boxes above were never ticked at the time).
  Steps 1-3 verified on main: the six named tests exist and
  `test_provider_router.py` passes; radon prints only `router._account`
  C (11), under the repo's < 15 limit. Merged d541f482 2026-09-30 19:03
  UTC; **production first checked out T13a at 2026-09-30 20:43 UTC**
  (`ce7bb09d`, host reflog), after the close. The Step 5 first-scan check
  was not recorded at the time; read afterwards: 0 `Alpaca daily_bars
  miss` lines and 0 Alpaca exceptions since the deploy. **Soak attempt 2
  window = 2026-10-01, 10-02, 10-05, 10-06, 10-07.** Evaluated by
  `scripts/ops/v106_soak_check.py` (T13 Step 6 definitions, unchanged),
  run each weekday 21:15 UTC by the one-shot cron
  `scripts/ops/install_v106_soak_cron.sh` → `logs/v106_soak_cron.log` on the VM.
  **Interim, 2026-10-02 13:31 UTC (day 2 before its session):** 275 scans;
  (a) p95 `cold_fetch_s` **4.70 s** (429 timings, max 18.84) -- FAIL so
  far; (b) fallback **1.53 %** (489 / 31871) -- PASS; (c) 0.01299 -- PASS.
  The fallback fix worked; (a) does not yet. Timings of 18 s sit far past
  the 5 s router deadline, so something other than the Alpaca call is now
  dominating the chunk -- not diagnosed. The user chose to run the full 5
  days as pre-registered rather than call it early; the verdict is the
  FINAL line after the 2026-10-07 run.*

### Task T14: Close-out

The user runs `/close-out`; the Skill tool blocks it for Claude. It follows
`document-lifecycle.md`:
- resolve `Bump:` from the then-current `VERSION.json`, with bot and ui
  bumped separately;
- regenerate the version history;
- move the spec and plan to `implemented/`, or to `no-lift/` if T13 failed;
- sync `AGENTS.md` if the data-provider seam belongs in its architecture
  summary;
- append a line to `docs/claude/architecture.md`'s module map for
  `marketdata/providers/`.

## Parallelisation

- **Sequential:**
  - T1 before everything (config globals).
  - T2 before T3/T4 (contract).
  - T5 before T6/T7 (the characterization tests must be written against
    untouched code).
  - T6 after T3–T5.
  - T10 after T9 (consumes its fields).
  - T12 after all code tasks; T13 → T14. T13a runs inside T13 (after soak
    attempt 1 failed, before its Step 6 restarts the soak).
- **Group A (parallel after T2):** T3 (`alpaca_provider.py`), T4
  (`router.py`). Disjoint files; T4 fakes the provider and consumes only T2
  plus T3's exception names. **Land T3 first if you're not dispatching
  both at once**, since T4 imports `AlpacaMiss`/`AlpacaAuthError`.
- **Group B (parallel after T6):** T7 (`data_store.py`, `test_universe.py`),
  T8 (`scan_run.py`), T9 (`risk.py`, `watchlist_rows.py`), T11 (new script).
  Disjoint files, and none consumes another's new symbol.
