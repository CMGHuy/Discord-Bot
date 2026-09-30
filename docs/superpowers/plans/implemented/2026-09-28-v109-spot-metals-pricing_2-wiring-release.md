# v109 — Spot gold/silver (XAUUSD/XAGUSD) Implementation Plan — Part 2: wiring, verification, release

> Part of the v109 plan. Header, goal, **Global Constraints**, **Parallelisation** and **Conventions for every task** live in
> `docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_0-index.md`; every task here implicitly includes them.

**Spec:** [`docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md`](../../specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md)

---

# Phase B — Hook points (continued)

### Task V109-5: `data.py` single-symbol hooks and the user-facing hints

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (imports line 12-16; `get_daily_data` line 29 and its not-found message line 62-66; new `_spot_daily_or_raise`; `get_current_price_detail` line 503; new `_spot_price_detail`)
- Modify: `swingbot/core/marketdata/ticker_utils.py` (module docstring only)
- Modify: `swingbot/commands/watchlist.py` (the heads-up text, lines 27-33)
- Create: `tests/marketdata/test_data_spot.py`

**Interfaces:**
- Consumes: V109-4's `router.daily_bars` / `router.latest_prices` spot branches and `router.spot_miss_reason`. V109-1's `spot_metals.is_spot_metal` and `spot_quote` (via `quote_with_reason`). The existing `data._yf_daily_batch`, `_yf_batch_prices`, `_price_cache` and `_last_good_batch_price`.
- Produces:
  - `get_daily_data("XAUUSD")` returns the scaled frame, or raises `ValueError` naming the reason. It never enters the `candidate_symbols()` loop.
  - `get_daily_data_batch` / `get_current_price_batch` get spot for free through the router. They are unchanged, and this task's tests pin them.
  - `get_current_price_detail("XAUUSD")` returns `PriceQuote(spot, False)`. On an outage it returns the stale last-good value only when `allow_stale=True`, else `None`. It never calls yfinance.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_data_spot.py`:

```python
"""v109: data.py never hands back unscaled futures for a spot metal."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data as data_mod
from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.marketdata.providers import router

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)
QUOTE = sm.SpotQuote(4151.70, datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc))


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    router.reset()
    data_mod._price_cache.clear()
    data_mod._last_good_batch_price.clear()

    def no_yahoo(*a, **k):
        raise AssertionError("a spot metal reached a direct Yahoo call")
    monkeypatch.setattr(data_mod.yf_safe, "download", no_yahoo)
    monkeypatch.setattr(data_mod.yf, "Ticker", no_yahoo)
    yield
    router.reset()
    data_mod._price_cache.clear()
    data_mod._last_good_batch_price.clear()


def _batch(calls):
    def fetch(tickers, period):
        calls.append(list(tickers))
        return {t: _frame() for t in tickers if t in ("GC=F", "AAPL")}
    return fetch


def test_single_daily_is_the_scaled_future(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    calls = []
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch(calls))
    df = data_mod.get_daily_data("xauusd")
    assert calls == [["GC=F"]]
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert df.attrs["source"] == "spot-scaled:GC=F"


def test_single_daily_outage_raises_never_aliases(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch([]))
    with pytest.raises(ValueError, match="spot quote missing"):
        data_mod.get_daily_data("XAUUSD")


def test_batch_daily_returns_spot_under_its_own_name(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    calls = []
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch(calls))
    out = data_mod.get_daily_data_batch(["AAPL", "XAUUSD"])
    assert calls == [["AAPL"], ["GC=F"]]
    assert set(out) == {"AAPL", "XAUUSD"}
    assert out["XAUUSD"].attrs["source"] == "spot-scaled:GC=F"


def test_batch_daily_outage_is_absent(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_daily_batch", _batch([]))
    assert data_mod.get_daily_data_batch(["XAUUSD"]) == {}


def test_price_detail_is_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) == \
        data_mod.PriceQuote(4151.70, False)
    assert data_mod.get_current_price("XAUUSD", allow_stale=False) == 4151.70


def test_price_detail_outage(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote missing"))
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) is None
    data_mod._price_cache["XAUUSD"] = (4150.0, 0.0, False)
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=False) is None
    assert data_mod.get_current_price_detail("XAUUSD", allow_stale=True) == \
        data_mod.PriceQuote(4150.0, True)


def test_batch_price_is_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    asked = []
    monkeypatch.setattr(data_mod, "_yf_batch_prices",
                        lambda ts: asked.append(list(ts)) or {"AAPL": 190.0})
    out = data_mod.get_current_price_batch(["XAUUSD", "AAPL"], allow_stale=False)
    assert asked == [["AAPL"]]
    assert out == {"XAUUSD": 4151.70, "AAPL": 190.0}
    assert router.last_source("XAUUSD") == "spot"


def test_batch_price_outage_is_absent_for_trading(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote missing"))
    monkeypatch.setattr(data_mod, "_yf_batch_prices", lambda ts: pytest.fail("no yfinance"))
    assert data_mod.get_current_price_batch(["XAUUSD"], allow_stale=False) == {}


def test_not_found_hint_names_the_spot_symbols(monkeypatch):
    monkeypatch.setattr(data_mod.yf_safe, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(ValueError) as err:
        data_mod.get_daily_data("NOPE1")
    assert "XAUUSD" in str(err.value) and "XAGUSD" in str(err.value)


def test_watchlist_help_names_the_spot_symbols():
    text = (Path(__file__).resolve().parents[2] / "swingbot" / "commands" / "watchlist.py").read_text(
        encoding="utf-8")
    assert "gold = `XAUUSD`" in text and "silver = `XAGUSD`" in text
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_data_spot.py`
Expected: FAIL. `test_single_daily_*` raises `AssertionError: a spot metal reached a direct Yahoo call` (the candidate loop). `test_price_detail_*` fails the same way. The hint tests fail. The batch tests already PASS through V109-4's router, which pins them.

- [ ] **Step 3: Implement the daily hook**

Imports in `data.py`: change `from swingbot.core.marketdata import yf_safe` to `from swingbot.core.marketdata import spot_metals, yf_safe`.

At the very top of `get_daily_data`'s body (before `if is_alpaca_eligible(ticker):`):

```python
    if spot_metals.is_spot_metal(ticker):
        return _spot_daily_or_raise(ticker, period)
```

Replace the `raise ValueError(...)` at the end of `get_daily_data` with:

```python
    raise ValueError(
        f"No data returned for '{ticker}'. Tried: {', '.join(tried)}. "
        f"Check the symbol matches Yahoo Finance's format (e.g. '^GSPC' for S&P 500, "
        f"'EURUSD=X' for forex). Spot gold = 'XAUUSD', spot silver = 'XAGUSD' "
        f"('GC=F' / 'SI=F' still work and stay futures-priced)."
    )
```

Add directly below `get_daily_data`:

```python
def _spot_daily_or_raise(ticker: str, period: str) -> pd.DataFrame:
    """v109: a spot metal's bars are its future's bars x the live spot ratio
    (router.daily_bars). Never the candidate_symbols() loop: ALIASES maps
    XAUUSD -> GC=F, which would hand back UNSCALED futures prices."""
    key = ticker.upper().strip()
    df = router.daily_bars([key], period, _yf_daily_batch).get(key)
    if df is None:
        raise ValueError(
            f"No spot data for '{key}': {router.spot_miss_reason(key) or 'unavailable'}. "
            f"Spot symbols never fall back to unscaled futures prices.")
    return df
```

- [ ] **Step 4: Implement the live-price hook**

In `get_current_price_detail`, directly after `now = time.monotonic()` and before `early = _cached_or_alpaca_quote(...)`:

```python
    if spot_metals.is_spot_metal(ticker_key):
        return _spot_price_detail(ticker_key, cached, now, allow_stale)
```

Add directly above `get_current_price_detail`:

```python
def _spot_price_detail(ticker_key: str, cached, now: float,
                       allow_stale: bool) -> PriceQuote | None:
    """v109: a spot metal's live price is gold-api.com's spot quote. Missing
    or stale is the same "no price" a failed quote already gives: None for a
    trading caller, the last known-good value (flagged stale) for display.
    Never the candidate loop, which would price XAUUSD off GC=F."""
    quote = spot_metals.spot_quote(ticker_key)
    if quote is not None:
        _price_cache[ticker_key] = (quote.price, now, False)
        return PriceQuote(quote.price, False)
    if cached and allow_stale:
        return PriceQuote(cached[0], True)
    return None
```

- [ ] **Step 5: Update the texts**

In `swingbot/commands/watchlist.py`, replace the heads-up message's middle two lines:

```python
            f"It's still in your watchlist, but scans will skip it until this resolves. "
            f"Common fixes: indices use Yahoo's `^` format (S&P 500 = `^GSPC`), spot metals are "
            f"gold = `XAUUSD`, silver = `XAGUSD` (futures `GC=F` / `SI=F` still work and stay "
            f"futures-priced), forex needs a `=X` suffix "
            f"(e.g. `EURUSD=X`). Use `!watchlist remove {ticker.upper()}` if you want to try a different symbol."
```

In `ticker_utils.py`'s module docstring, after the "Silver spot is \"SI=F\"..." bullet, add:

```
  - v109: XAUUSD / XAGUSD are NOT resolved through ALIASES any more. They are
    spot-priced instruments (core/marketdata/spot_metals.py) whose branch runs
    before any candidate loop; the aliases remain for GOLD/XAU/SILVER/XAG and
    for metadata lookups (company name, currency).
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_data_spot.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_data.py`, `python scripts/dev/testrun.py file tests/marketdata/test_data_alpaca_routing.py`, `python scripts/dev/testrun.py file tests/marketdata/test_current_price_staleness.py`
Expected: all PASS.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/data.py`
Expected: `get_current_price_batch` stays at C (12). `get_current_price_detail` is at most C (12) and `get_daily_data` at most B (10), so it is not listed. The two new helpers are not listed.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/marketdata/data.py swingbot/core/marketdata/ticker_utils.py swingbot/commands/watchlist.py tests/marketdata/test_data_spot.py
git commit -m "feat(v109): data.py prices spot metals off spot -- never the GC=F/SI=F alias

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/data.py swingbot/core/marketdata/ticker_utils.py swingbot/commands/watchlist.py tests/marketdata/test_data_spot.py
```

---

### Task V109-6: The cache rule — only raw futures are ever cached

**Files:**
- Modify: `swingbot/core/marketdata/data_store.py` (imports ~line 35-39; `save_to_disk` line 199; `update_cache` line 375; `get_intraday` line 433; new `refuse_spot_write`, `_spot_intraday`)
- Modify: `swingbot/core/marketdata/data_refresh.py` (`_merge_save` line 209; `refresh_all` line 349; imports)
- Modify: `swingbot/core/marketdata/backtest_cache.py` (`ensure_cached` line 103, `ensure_cached_background` line 131; imports)
- Modify: `docs/claude/known-traps.md` (one bullet after the "Two parallel OHLCV cache subsystems" bullet)
- Create: `tests/marketdata/test_spot_cache_rule.py`

**Interfaces:**
- Consumes: V109-1's `spot_metals.is_spot_metal`, `underlying`, `cache_symbol`, `cache_symbols`. V109-2's `spot_metals.scale_underlying`.
- Produces:
  - `data_store.refuse_spot_write(ticker: str) -> None` raises `ValueError` for a spot symbol.
  - `save_to_disk` / `_merge_save` refuse spot names.
  - `get_intraday("XAUUSD", ...)` caches and reads `GC_F` and returns the scaled frame or `None`.
  - `refresh_all`, `update_cache`, `ensure_cached` and `ensure_cached_background` operate on the underlying.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_spot_cache_rule.py`:

```python
"""v109 cache rule: a scaled spot frame is never written to either OHLCV
cache under XAUUSD/XAGUSD -- only the raw future is cached, under GC_F."""
import os

import pandas as pd
import pytest

from swingbot.core.marketdata import backtest_cache as bc
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.marketdata import spot_metals as sm

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


def _bars(n=30, start="2026-08-01", freq="D", close=4000.0):
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({"Open": close, "High": close + 5, "Low": close - 5,
                         "Close": close, "Volume": 100.0}, index=idx)


def _no_spot_files(root):
    hits = [os.path.join(d, f) for d, _, files in os.walk(root) for f in files
            if f.upper().startswith(("XAUUSD", "XAGUSD"))]
    assert hits == []


def test_save_to_disk_refuses_spot_names(tmp_path):
    with pytest.raises(ValueError, match="never cached"):
        data_store.save_to_disk(_bars(), "XAUUSD", "daily", base_dir=str(tmp_path))
    _no_spot_files(tmp_path)
    data_store.save_to_disk(_bars(), "GC=F", "daily", base_dir=str(tmp_path))
    assert os.path.exists(data_store.cache_path("GC=F", "daily", base_dir=str(tmp_path)))


def test_merge_save_refuses_spot_names(tmp_path):
    with pytest.raises(ValueError, match="never cached"):
        data_refresh._merge_save(None, _bars(), "XAGUSD", "daily", str(tmp_path))
    _no_spot_files(tmp_path)


def test_intraday_caches_the_future_and_returns_it_scaled(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    asked = []

    def fetch(sym, iv):
        asked.append((sym, iv))
        return _bars(freq="h")
    df = data_store.get_intraday("XAUUSD", base_dir=str(tmp_path), fetch_fn=fetch)
    assert asked == [("GC=F", "1h")]
    assert df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert os.path.exists(data_store.cache_path("GC=F", "1h", base_dir=str(tmp_path)))
    _no_spot_files(tmp_path)


def test_intraday_outage_is_none_but_the_future_is_still_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    out = data_store.get_intraday("XAUUSD", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, iv: _bars(freq="h"))
    assert out is None
    assert os.path.exists(data_store.cache_path("GC=F", "1h", base_dir=str(tmp_path)))
    _no_spot_files(tmp_path)


def test_refresh_all_refreshes_the_future_not_the_spot_name(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda sym, tf: asked.append(sym) or _bars())
    result = data_refresh.refresh_all(["XAUUSD", "AAPL", "GC=F"], ["daily"],
                                      base_dir=str(tmp_path), persist_state=False)
    assert asked == ["GC=F", "AAPL"]
    assert not any(k.upper().startswith("XAUUSD") for k in result["state"])
    _no_spot_files(tmp_path)


def test_update_cache_maps_spot_to_the_future(tmp_path):
    asked = []
    out = data_store.update_cache(["XAGUSD"], "1d", base_dir=str(tmp_path),
                                  fetch_fn=lambda sym, start: asked.append(sym) or _bars())
    assert asked == ["SI=F"] and set(out) == {"SI=F"}
    _no_spot_files(tmp_path)


def test_backtest_cache_stores_the_future(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    asked = []
    monkeypatch.setattr(bc, "fetch", lambda t: asked.append(t) or _bars(n=300))
    result = bc.ensure_cached("xauusd")
    assert asked == ["GC=F"] and result.ticker == "GC=F" and result.status == "ok"
    assert (tmp_path / "backtest_cache" / "GC_F.csv").exists()
    _no_spot_files(tmp_path)


def test_backtest_cache_background_stores_the_future(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    asked = []
    monkeypatch.setattr(bc, "fetch", lambda t: asked.append(t) or _bars(n=300))
    bc.ensure_cached_background("XAGUSD").join(timeout=10)
    assert asked == ["SI=F"]
    _no_spot_files(tmp_path)
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_cache_rule.py`
Expected: FAIL. `save_to_disk` writes `XAUUSD.csv` (no `ValueError`), `get_intraday` asks for `XAUUSD`, and so on.

- [ ] **Step 3: Implement in `data_store.py`**

Add `from swingbot.core.marketdata import spot_metals` to the imports. Add above `save_to_disk`:

```python
def refuse_spot_write(ticker: str) -> None:
    """v109 cache rule: a spot metal's frame is its future's bars x a live
    ratio. Cached under XAUUSD it would freeze one day's ratio into every
    later read -- so only the raw future is ever cached, under its own name."""
    if spot_metals.is_spot_metal(ticker):
        raise ValueError(
            f"'{ticker}' is spot-scaled and never cached -- cache "
            f"{spot_metals.underlying(ticker)} instead")
```

Change `save_to_disk` to:

```python
def save_to_disk(df: pd.DataFrame, ticker: str, interval: str, base_dir: str = DATA_DIR) -> str:
    refuse_spot_write(ticker)
    path = cache_path(ticker, interval, base_dir)
    df.to_csv(path)
    return path
```

In `update_cache`, make the first statement of the body (before `fetch = ...`):

```python
    symbols = spot_metals.cache_symbols(symbols)   # v109: cache the future, never the spot name
```

At the top of `get_intraday`'s body (before `path = cache_path(...)`):

```python
    if spot_metals.is_spot_metal(symbol):
        return _spot_intraday(symbol, interval, base_dir, fetch_fn)
```

Add directly below `get_intraday`:

```python
def _spot_intraday(symbol: str, interval: str, base_dir: str, fetch_fn):
    """v109: the future's cached/fetched intraday bars (cached under ITS
    name), rescaled on read. None when the spot ratio is unavailable -- the
    E29 annotation treats None as neutral, never as unscaled futures."""
    raw = get_intraday(spot_metals.underlying(symbol), interval,
                       base_dir=base_dir, fetch_fn=fetch_fn)
    df, _ = spot_metals.scale_underlying(symbol, raw)
    return df
```

- [ ] **Step 4: Implement in `data_refresh.py`**

Add `from swingbot.core.marketdata import spot_metals`. Also add `refuse_spot_write` to the existing `from swingbot.core.marketdata.data_store import ...` line (check the exact import with `git grep -n "from swingbot.core.marketdata.data_store import" swingbot/core/marketdata/data_refresh.py`). In `_merge_save`, make the first statement of the body (after the docstring):

```python
    refuse_spot_write(symbol)
```

In `refresh_all`, directly after the docstring (before `timeframes = [...]`):

```python
    symbols = spot_metals.cache_symbols(symbols)   # v109: refresh GC=F for XAUUSD, never XAUUSD
```

This adds no branch to `refresh_all` (legacy 17).

- [ ] **Step 5: Implement in `backtest_cache.py`**

Add `from swingbot.core.marketdata.spot_metals import cache_symbol`. In `ensure_cached`, change `ticker = ticker.upper()` to:

```python
    ticker = cache_symbol(ticker.upper())   # v109: XAUUSD caches GC=F, never itself
```

In `ensure_cached_background`, change `ticker = ticker.upper()` the same way.

- [ ] **Step 6: Document the trap**

In `docs/claude/known-traps.md`, directly after the "Two parallel OHLCV cache subsystems" bullet, add:

```markdown
- **Spot metals are never cached under their own name (v109).** `XAUUSD` /
  `XAGUSD` bars are `GC=F` / `SI=F` bars × a live spot ratio
  (`marketdata/spot_metals.py`). Only the raw future is cached (`GC_F.csv`);
  `save_to_disk` and `data_refresh._merge_save` raise on a spot name, and
  `refresh_all`, `update_cache` and `backtest_cache.ensure_cached` map it to
  the future. A cached scaled frame would freeze one day's ratio into later
  levels. The scan crawl skips the disk cache for spot symbols entirely.
```

- [ ] **Step 7: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_cache_rule.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_data_refresh.py`, `python scripts/dev/testrun.py file tests/marketdata/test_backtest_cache.py`, `python scripts/dev/testrun.py file tests/marketdata/test_universe.py` (holds the `get_intraday` round-trip tests)
Expected: all PASS.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/data_store.py swingbot/core/marketdata/data_refresh.py swingbot/core/marketdata/backtest_cache.py`
Expected: `refresh_all` stays at C (17), unchanged. No function this task wrote or changed is listed (`get_intraday` goes to B 10).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/marketdata/data_store.py swingbot/core/marketdata/data_refresh.py swingbot/core/marketdata/backtest_cache.py docs/claude/known-traps.md tests/marketdata/test_spot_cache_rule.py
git commit -m "feat(v109): cache rule -- only raw futures are cached for spot metals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/data_store.py swingbot/core/marketdata/data_refresh.py swingbot/core/marketdata/backtest_cache.py docs/claude/known-traps.md tests/marketdata/test_spot_cache_rule.py
```

---

### Task V109-7: Scan crawl — spot symbols fetched apart, ratio or skip logged once

Load the `no-lookahead` and `alert-surface` skills first.

**Files:**
- Modify: `swingbot/core/scanning/fetch.py` (imports line 18-19; `_crawl_latest_data` line 307; new `_spot_daily_worker`, `_log_spot_outcome`, `_crawl_spot` placed after `_fetch_cold_frames`)
- Create: `tests/scanning/test_crawl_spot.py`

**Interfaces:**
- Consumes: V109-4's `router.spot_miss_reason` and router `daily_bars` spot branch (via the existing `get_daily_data_batch`). V109-1's `spot_metals.split_spot`. V109-2's scaled-frame attrs (`spot_ratio`, `spot_price`, `spot_underlying`, `futures_price`). Existing `_run_bounded`, `runstate.is_stop_requested`, `_load_cached_daily`, `_fetch_cold_frames`.
- Produces:
  - `fetch._crawl_latest_data(tickers)` never passes a spot symbol to `_load_cached_daily` or `_fetch_cold_frames` (whose single-ticker fallback aliases XAUUSD to unscaled GC=F). It returns spot frames fetched by `_crawl_spot`.
  - `fetch._crawl_spot(tickers, progress=None) -> dict` logs exactly one of `"<SYM>: spot ratio %.5f (spot %.2f / <FUT> %.2f)"` or `"<SYM>: skipping new-signal scan -- spot quote unavailable (<reason>)"` per symbol per scan, in the scan's process.
  - `_scan_one` is **not** modified. A skipped spot symbol is simply absent from the crawl results, which is the existing "no frame" path.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_crawl_spot.py`:

```python
"""v109: the crawl fetches spot metals apart from the cache/alias paths and
logs the ratio (or the skip) once per symbol per scan, in the scan process."""
import logging

import pandas as pd
import pytest

from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.scanning import fetch

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


class _InlinePool:
    """Runs _run_bounded's worker inline (same stand-in as
    tests/scanning/test_scan_telemetry_sources.py)."""
    def __init__(self, max_workers=None, mp_context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        from concurrent.futures import Future
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:
            fut.set_exception(exc)
        return fut


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture
def crawl(monkeypatch, caplog):
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    caplog.set_level(logging.INFO, logger="swing-bot.scan_engine")
    seen = {"cache": [], "cold": [], "batch": []}

    def cached(t):
        seen["cache"].append(t)
        return _frame(190.0) if t == "AAPL" else None
    monkeypatch.setattr(fetch, "_load_cached_daily", cached)
    monkeypatch.setattr(fetch, "_fetch_cold_frames",
                        lambda ts, progress=None: seen["cold"].extend(ts) or [])
    return seen


def _batch_serves(monkeypatch, seen, frames):
    def batch(tickers, period):
        seen["batch"].append(list(tickers))
        return {t: frames[t] for t in tickers if t in frames}
    monkeypatch.setattr(fetch, "get_daily_data_batch", batch)


def test_spot_symbol_bypasses_cache_and_alias_paths(monkeypatch, crawl, caplog):
    _batch_serves(monkeypatch, crawl, {"XAUUSD": sm.scale_frame(_frame(), READING)})
    results = fetch._crawl_latest_data(["AAPL", "XAUUSD"])
    assert set(results) == {"AAPL", "XAUUSD"}
    assert crawl["cache"] == ["AAPL"]
    assert crawl["cold"] == []
    assert crawl["batch"] == [["XAUUSD"]]
    lines = [r.getMessage() for r in caplog.records]
    assert "XAUUSD: spot ratio 0.99435 (spot 4151.70 / GC=F 4175.30)" in lines
    assert sum("XAUUSD: spot ratio" in m for m in lines) == 1


def test_outage_skips_with_the_reason_and_never_falls_back(monkeypatch, crawl, caplog):
    from swingbot.core.marketdata.providers import router
    _batch_serves(monkeypatch, crawl, {})
    monkeypatch.setattr(router, "spot_miss_reason",
                        lambda t: "spot quote stale (1200s old)")
    results = fetch._crawl_latest_data(["XAUUSD"])
    assert "XAUUSD" not in results
    assert crawl["cold"] == [] and crawl["cache"] == []
    assert ("XAUUSD: skipping new-signal scan -- spot quote unavailable "
            "(spot quote stale (1200s old))") in [r.getMessage() for r in caplog.records]


def test_a_failed_worker_is_a_skip(monkeypatch, crawl, caplog):
    def boom(tickers, period):
        raise RuntimeError("worker died")
    monkeypatch.setattr(fetch, "get_daily_data_batch", boom)
    assert fetch._crawl_latest_data(["XAGUSD"]) == {}
    assert any(r.getMessage().startswith(
        "XAGUSD: skipping new-signal scan -- spot quote unavailable (")
        for r in caplog.records)


def test_progress_counts_spot_symbols(monkeypatch, crawl):
    from swingbot.core.scanning.scan_run import ScanProgress
    _batch_serves(monkeypatch, crawl, {"XAUUSD": sm.scale_frame(_frame(), READING)})
    progress = ScanProgress()
    fetch._crawl_latest_data(["AAPL", "XAUUSD"], progress)
    assert progress.total == 2 and progress.done == 2
```

`ScanProgress()` takes no arguments (`scan_run.py:99`, `__init__(self)` sets `total = done = 0`).

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_crawl_spot.py`
Expected: FAIL. `crawl["cache"] == ["AAPL", "XAUUSD"]` and `crawl["cold"] == ["XAUUSD"]` (spot goes through the cache and the alias-capable cold path), and there is no ratio log line.

- [ ] **Step 3: Implement**

Imports in `fetch.py`: change `from swingbot.core.marketdata import data_refresh, data_store, universe` to `from swingbot.core.marketdata import data_refresh, data_store, spot_metals, universe`.

Add after `_fetch_cold_frames`:

```python
def _spot_daily_worker(ticker: str, period: str) -> tuple:
    """v109 worker body for one spot symbol: its spot-scaled frame, or None
    plus the reason the router recorded -- that record lives in this worker
    process, so it travels back with the result (the same shape as
    _price_batch_with_sources)."""
    from swingbot.core.marketdata.providers import router
    df = get_daily_data_batch([ticker], period).get(ticker)
    if df is not None:
        return df, ""
    return None, router.spot_miss_reason(ticker) or "no spot frame"


def _log_spot_outcome(ticker: str, df, reason: str) -> None:
    """The scan's one line per spot symbol: the ratio its levels are drawn at
    (so an alert reconciles with the futures chart), or why it was skipped."""
    if df is None:
        log.info("%s: skipping new-signal scan -- spot quote unavailable (%s)", ticker, reason)
        return
    a = df.attrs
    log.info("%s: spot ratio %.5f (spot %.2f / %s %.2f)", ticker, a["spot_ratio"],
             a["spot_price"], a["spot_underlying"], a["futures_price"])


def _crawl_spot(tickers: list, progress: "ScanProgress" = None) -> dict:
    """v109: spot metals skip the disk cache (a scaled frame is never cached)
    and the cold path's single-ticker fallback (candidate_symbols() would
    alias XAUUSD to UNSCALED GC=F). One bounded worker per symbol; the
    outcome is logged here, in the scan's own process. A skipped symbol is
    simply absent -- _scan_one's existing "no frame" path, never futures."""
    period = config.DEFAULT_HISTORY_PERIOD
    timeout = int(getattr(config, "COLD_FETCH_TIMEOUT_SECONDS", 180))
    out: dict = {}
    for ticker in tickers:
        if runstate.is_stop_requested():
            break
        df, reason = _run_bounded(
            _spot_daily_worker, (ticker, period), timeout,
            label=f"Crawl: spot fetch for {ticker}") or (None, "spot fetch failed or timed out")
        _log_spot_outcome(ticker, df, reason)
        if df is not None:
            out[ticker] = df
        if progress is not None:
            progress.done += 1
            progress.current_ticker = ticker
    return out
```

In `_crawl_latest_data`, make three edits and nothing else:
1. Directly before `cold = []`, insert `spot, plain = spot_metals.split_spot(tickers)`.
2. Change the cache loop header `for ticker in tickers:` (the one that calls `_load_cached_daily`) to `for ticker in plain:`.
3. Directly after the `for ticker, df in _fetch_cold_frames(cold, progress):` loop, insert `results.update(_crawl_spot(spot, progress))`.

Leave `progress.total = len(tickers)` and `LRUFrames(max_frames=len(tickers))` as they are: both already count the spot symbols.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_crawl_spot.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py` and `python scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py`
Expected: PASS.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/fetch.py swingbot/core/scanning/analyze.py`
Expected: `_crawl_latest_data` stays at B (9), so it is not listed. The new helpers are not listed. `_scan_one` is unchanged: `git diff main -- swingbot/core/scanning/analyze.py` is empty.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/fetch.py tests/scanning/test_crawl_spot.py
git commit -m "feat(v109): crawl fetches spot metals apart; ratio or skip logged once per scan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/fetch.py tests/scanning/test_crawl_spot.py
```

---

# Phase C — Verification, release, rollout

### Task V109-8: Full-suite verification

**Files:** none (a fix-forward touches whatever the failures name).

**Interfaces:**
- Consumes: V109-1..V109-7 committed on the worktree branch.
- Produces: a green branch, ready to merge.

- [ ] **Step 1: The one full-suite run**

Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full` in the worktree. Require `0 failed` and `0 xfailed`. A changed pass count is not a failure. A red result is this plan's regressions, so fix forward from the failures it names. If a failure passes in isolation and sits in code this plan never touched, report it with both outputs and do not call the suite green.

- [ ] **Step 2: Complexity sweep over everything the plan touched**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/spot_metals.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/providers/base.py swingbot/core/marketdata/data.py swingbot/core/marketdata/data_store.py swingbot/core/marketdata/data_refresh.py swingbot/core/marketdata/backtest_cache.py swingbot/core/marketdata/asset_class.py swingbot/core/marketdata/universe.py swingbot/core/market/events.py swingbot/core/scanning/fetch.py`

Expected: only functions this plan did not change, plus the known pre-existing values: `refresh_all` 17, `get_earnings_datetimes` 14, `get_current_price_batch` 12, `get_current_price_detail` ≤ 12. Any other function at 15 or more is a regression to split before V109-9.

- [ ] **Step 3: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py swingbot/core/marketdata/spot_metals.py swingbot/core/marketdata/providers/router.py swingbot/core/scanning/fetch.py`
Expected: no output.

---

### Task V109-9: Merge and release `bot patch`

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`

**Interfaces:**
- Consumes: V109-8's green branch.
- Produces: the branch merged on `main`, the release commit and the regenerated history, pushed to `origin/main` (which triggers the image build and deploy).

- [ ] **Step 1: Merge**

Follow the `worktree-lifecycle` skill. Run `git fetch` and compare with `origin/main`, because another session may have committed. Then merge branch `2026-09-28-v109-spot-metals-pricing` into `main`. If the merge resolved conflicts, run `python scripts/dev/testrun.py full` once on the result (the one exception in `document-conventions.md`). Otherwise do not re-run anything.

- [ ] **Step 2: Bump — read `VERSION.json` from disk**

Read `VERSION.json` now: never this plan, the spec's `Version:` line, or memory. Increment `bot` at the **patch** level, leave `ui` and `ui_updated` untouched, and set `bot_updated` to the current UTC time in `YYYY-MM-DD HH-MM-SS` format.

```bash
git add VERSION.json
git commit -m "release(bot): <new bot version> -- spot gold/silver alerts priced on spot (XAUUSD/XAGUSD)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- VERSION.json
```

- [ ] **Step 3: Regenerate the version history (after the bump commit)**

Run: `python scripts/dev/build_version_matrix.py`
Check: `git diff swingbot/admin/version_history.json` shows the new bot pair as `current`, with a real commit (not `"uncommitted"`).
Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS.

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new bot version> -- spot gold/silver alerts priced on spot (XAUUSD/XAGUSD)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/admin/version_history.json
```

- [ ] **Step 4: Push**

`git fetch`, confirm `main` is ahead of `origin/main` only by this plan's commits, then `git push origin main`. The GitHub Actions deploy runs on the push.

---

### Task V109-10: Production rollout, verification and close-out

Operator task, run by the controller. Production reads go through the `prod-inspector` agent (read-only). The watchlist swap is a data change done with bot commands, and there is nothing to mirror into the repo (spec §6). It follows the `mirror-prod` rule only if something else on the VM had to change. If it did, mirror it and commit it.

**Files:**
- Move: `docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md` → `docs/superpowers/specs/implemented/`
- Move: the three plan parts `docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_0-index.md`, `_1-spot-module.md`, `_2-wiring-release.md` → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: V109-9's deployed image.
- Produces: `XAUUSD` / `XAGUSD` live on the production watchlist, verified, and the documents closed.

- [ ] **Step 1: Confirm the deploy (prod-inspector, read-only)**

Confirm three things:
- The bot and admin containers run the image built from V109-9's push (the image tag `sha-<12>` matches the release commit's merge head).
- The bot logs the new version at start.
- From the VM, `curl -s https://api.gold-api.com/price/XAU` and `/XAG` return JSON with a positive `price` and an `updatedAt` within 15 minutes.

Stop and report if the endpoint is unreachable from the VM. The code would then skip spot symbols on every scan.

- [ ] **Step 2: Record the open futures plans (prod-inspector, read-only)**

List the open plans on `GC=F` and `SI=F`. Confirm that the plan manager steps open plans independently of watchlist membership: the plan-manager tick logs name them each tick, or the code path shows it. Spec §6.3 says these plans close out in futures. If removing a symbol from the watchlist would stop its plans being stepped, **stop and ask the partner** before Step 3.

- [ ] **Step 3: Swap the watchlist (partner or controller, in Discord)**

```
!watchlist remove GC=F
!watchlist add XAUUSD
!watchlist remove SI=F
!watchlist add XAGUSD
```

Each `add` should answer "Added **XAUUSD**..." with **no** "Heads up: couldn't fetch data" follow-up. A heads-up here means the spot fetch failed on production (the message carries the reason). Stop and investigate.

- [ ] **Step 4: Verify the first scan (prod-inspector, read-only, `/opt/swing-bot/logs`)**

Check the first scan after the swap for five things:
- One `XAUUSD: spot ratio 0.99xxx (spot ... / GC=F ...)` line and one `XAGUSD: spot ratio ...` line, each ratio inside `[0.95, 1.05]`.
- No `XAUUSD: skipping new-signal scan -- spot quote unavailable` line. If there is one, report its reason.
- No `XAUUSD.csv` / `XAGUSD.csv` under `market_data/*/` or `data/backtest_cache/`.
- `market_data/daily/GC_F.csv` and `SI_F.csv` present and refreshed by `market_data_refresh`.
- No XAUUSD/XAGUSD errors in the scan's per-ticker lines.

Once an XAUUSD or XAGUSD alert fires, possibly days later, confirm its trigger price sits within the quote's spread of gold-api's spot at alert time. Record that as a follow-up note, not a blocker.

- [ ] **Step 5: Close out the documents**

```bash
git mv docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_0-index.md docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_1-spot-module.md docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_2-wiring-release.md docs/superpowers/plans/implemented/
```

In each of the three moved plan parts, fix the `**Spec:**` link to `../../specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md`, and check it with `ls docs/superpowers/specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md`. If the shipped impact differed from `Bump: bot patch` / `Edge: volume`, amend the spec's line with one clause saying why.

```bash
git add docs/superpowers/specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md docs/superpowers/plans/implemented/2026-09-28-v109-spot-metals-pricing_*.md
git commit -m "docs(v109): close out -- spot gold/silver live on production

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md docs/superpowers/specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_0-index.md docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_1-spot-module.md docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_2-wiring-release.md docs/superpowers/plans/implemented/2026-09-28-v109-spot-metals-pricing_0-index.md docs/superpowers/plans/implemented/2026-09-28-v109-spot-metals-pricing_1-spot-module.md docs/superpowers/plans/implemented/2026-09-28-v109-spot-metals-pricing_2-wiring-release.md
git push origin main
```

- [ ] **Step 6: Remove the worktree**

Remove `.claude/worktrees/2026-09-28-v109-spot-metals-pricing` per `worktree-lifecycle`. Before deleting the branch, run `git rev-list --count main..2026-09-28-v109-spot-metals-pricing`: it must print `0`. Otherwise **stop** and ask. Never touch a branch with `backup` in its name or any `stable-*` branch (`docs/claude/git-safety.md`).
