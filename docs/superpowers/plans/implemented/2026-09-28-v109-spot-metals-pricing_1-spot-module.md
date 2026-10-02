# v109 — Spot gold/silver (XAUUSD/XAGUSD) Implementation Plan — Part 1: spot module and router

> Part of the v109 plan. Header, goal, **Global Constraints**, **Parallelisation** and **Conventions for every task** live in
> `docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_0-index.md`; every task here implicitly includes them.

**Spec:** [`docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md`](../../specs/implemented/2026-09-28-v109-spot-metals-pricing-design.md)

---

# Phase A — The spot module

### Task V109-1: Config field, source tags and the spot quote client

**Files:**
- Modify: `swingbot/config.py` (Data Sources section, after the `ALPACA_BREAKER_COOLDOWN_SECONDS` Field at ~line 675)
- Modify: `.env.example` (after `ALPACA_BREAKER_COOLDOWN_SECONDS=300`, ~line 406)
- Modify: `swingbot/core/marketdata/providers/base.py` (next to `SOURCE_FALLBACK`, line 15)
- Create: `swingbot/core/marketdata/spot_metals.py`
- Create: `tests/marketdata/test_spot_metals.py`

**Interfaces:**
- Consumes: `swingbot.config` (`Field`, `FIELDS`), `providers/base.py`'s `SOURCE_*` constants block.
- Produces:
  - `config.SPOT_QUOTE_MAX_AGE_SECONDS: int` (default 900).
  - `base.SOURCE_SPOT = "spot"` and `base.SOURCE_SPOT_SCALED = "spot-scaled"`.
  - `spot_metals.SPOT_PAIRS`, `is_spot_metal(symbol) -> bool`, `underlying(symbol) -> str` (KeyError for a non-spot symbol), `cache_symbol(symbol: str) -> str`, `cache_symbols(symbols) -> list[str]`, `split_spot(tickers) -> tuple[list, list]` (spot, rest; order preserved).
  - `SpotQuote(price: float, updated_at: datetime)` (frozen dataclass; aware UTC).
  - `_raw_get(url: str) -> str`, `_now_mono() -> float`.
  - `quote_with_reason(symbol, *, now: datetime | None = None) -> tuple[SpotQuote | None, str]` (reason `""` on success).
  - `spot_quote(symbol, *, now=None) -> SpotQuote | None`, `reset() -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_spot_metals.py`:

```python
"""v109: spot gold/silver -- pair table, quote client, staleness."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import spot_metals as sm

NOW = datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc)


def _body(price=4151.70, updated=NOW):
    return json.dumps({"name": "Gold", "price": price, "symbol": "XAU",
                       "updatedAt": updated.isoformat().replace("+00:00", "Z")})


def _serve(monkeypatch, *bodies):
    """Stub the HTTP GET: the Nth call gets bodies[N] (the last repeats);
    an Exception instance is raised instead of returned."""
    calls = []

    def fake(url):
        calls.append(url)
        body = bodies[min(len(calls) - 1, len(bodies) - 1)]
        if isinstance(body, Exception):
            raise body
        return body
    monkeypatch.setattr(sm, "_raw_get", fake)
    return calls


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    sm.reset()
    monkeypatch.setattr(config, "SPOT_QUOTE_MAX_AGE_SECONDS", 900)
    clock = [1000.0]
    monkeypatch.setattr(sm, "_now_mono", lambda: clock[0])
    yield clock
    sm.reset()


def test_config_field_declared_in_data_sources():
    keys = {f.key: f for f in config.FIELDS}
    field = keys["SPOT_QUOTE_MAX_AGE_SECONDS"]
    assert field.section == "Data Sources"
    assert field.type == "number" and field.default == "900"


def test_source_tags():
    from swingbot.core.marketdata.providers import base
    assert base.SOURCE_SPOT == "spot"
    assert base.SOURCE_SPOT_SCALED == "spot-scaled"


def test_pair_table_and_membership():
    assert sm.SPOT_PAIRS == {"XAUUSD": ("XAU", "GC=F"), "XAGUSD": ("XAG", "SI=F")}
    assert sm.is_spot_metal("XAUUSD") and sm.is_spot_metal(" xagusd ")
    for other in ("GC=F", "SI=F", "GOLD", "XAU", "AAPL", "", None):
        assert not sm.is_spot_metal(other)
    assert sm.underlying("xauusd") == "GC=F" and sm.underlying("XAGUSD") == "SI=F"
    with pytest.raises(KeyError):
        sm.underlying("AAPL")


def test_cache_symbols_map_spot_to_its_future():
    assert sm.cache_symbol("XAUUSD") == "GC=F"
    assert sm.cache_symbol("AAPL") == "AAPL"
    assert sm.cache_symbols(["XAUUSD", "GC=F", "AAPL", "XAGUSD"]) == ["GC=F", "AAPL", "SI=F"]


def test_split_spot_preserves_order():
    assert sm.split_spot(["AAPL", "XAUUSD", "SI=F", "XAGUSD"]) == (
        ["XAUUSD", "XAGUSD"], ["AAPL", "SI=F"])


def test_quote_parsed_from_the_gold_api_payload(monkeypatch):
    calls = _serve(monkeypatch, _body())
    quote = sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=30))
    assert quote == sm.SpotQuote(4151.70, NOW)
    assert calls == ["https://api.gold-api.com/price/XAU"]


def test_silver_asks_for_xag(monkeypatch):
    calls = _serve(monkeypatch, _body(price=48.12))
    assert sm.spot_quote("XAGUSD", now=NOW).price == 48.12
    assert calls == ["https://api.gold-api.com/price/XAG"]


def test_non_spot_symbol_never_fetches(monkeypatch):
    calls = _serve(monkeypatch, _body())
    assert sm.quote_with_reason("AAPL", now=NOW) == (None, "AAPL is not a spot metal")
    assert calls == []


def test_quote_cached_for_fifteen_seconds(monkeypatch, _clean):
    clock = _clean
    calls = _serve(monkeypatch, _body(), _body(price=4160.0))
    first = sm.spot_quote("XAUUSD", now=NOW)
    clock[0] += 14
    assert sm.spot_quote("XAUUSD", now=NOW) == first and len(calls) == 1
    clock[0] += 2
    assert sm.spot_quote("XAUUSD", now=NOW).price == 4160.0 and len(calls) == 2


def test_stale_quote_is_treated_as_missing(monkeypatch):
    _serve(monkeypatch, _body())
    assert sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=900)) is not None
    quote, reason = sm.quote_with_reason("XAUUSD", now=NOW + timedelta(seconds=901))
    assert quote is None and reason.startswith("spot quote stale")


def test_staleness_reads_the_config_at_call_time(monkeypatch):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(config, "SPOT_QUOTE_MAX_AGE_SECONDS", 60)
    assert sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=61)) is None


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"price": 0, "updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"price": -3.0, "updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"price": 4151.7}),
])
def test_bad_payloads_are_none_never_raised(monkeypatch, body):
    _serve(monkeypatch, body)
    quote, reason = sm.quote_with_reason("XAUUSD", now=NOW)
    assert quote is None and reason == "spot quote missing"


def test_http_error_logged_once_per_failure_streak(monkeypatch, caplog, _clean):
    clock = _clean
    _serve(monkeypatch, OSError("boom"), OSError("boom"), _body())
    caplog.set_level(logging.INFO, logger="swing-bot.spot_metals")
    assert sm.spot_quote("XAUUSD", now=NOW) is None
    clock[0] += 20
    assert sm.spot_quote("XAUUSD", now=NOW) is None
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    clock[0] += 20
    assert sm.spot_quote("XAUUSD", now=NOW).price == 4151.70
    assert any("recovered" in r.getMessage() for r in caplog.records)


def test_a_failure_is_cached_too(monkeypatch, _clean):
    """An outage must not turn every caller into a 10 s blocking GET."""
    calls = _serve(monkeypatch, OSError("boom"))
    sm.spot_quote("XAUUSD", now=NOW)
    sm.spot_quote("XAUUSD", now=NOW)
    assert len(calls) == 1
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_metals.py`
Expected: FAIL. `ModuleNotFoundError: No module named 'swingbot.core.marketdata.spot_metals'` (collection error).

- [ ] **Step 3: Add the config field and `.env.example` line**

In `swingbot/config.py`, directly after the `ALPACA_BREAKER_COOLDOWN_SECONDS` `Field(...)` entry (still inside the "Data Sources" block), add:

```python
    Field("SPOT_QUOTE_MAX_AGE_SECONDS", "SPOT_QUOTE_MAX_AGE_SECONDS", "Data Sources",
          "Max spot metals quote age (s)", type="number", default="900",
          min=60, max=86400, step=60,
          help="v109. XAUUSD/XAGUSD are priced off gold-api.com's spot quote. A quote whose "
               "updatedAt is older than this is treated exactly like a missing one: the scan "
               "skips new signals for that metal and open plans are not stepped until a fresh "
               "quote arrives. Never falls back to unscaled futures prices."),
```

In `.env.example`, directly after `ALPACA_BREAKER_COOLDOWN_SECONDS=300`, add:

```
# v109: spot gold/silver (XAUUSD/XAGUSD) quote freshness, seconds.
SPOT_QUOTE_MAX_AGE_SECONDS=900
```

- [ ] **Step 4: Add the source tags to `providers/base.py`**

After `SOURCE_FALLBACK = "yfinance-fallback"` (line 15):

```python
SOURCE_SPOT = "spot"                 # v109: gold-api.com live spot quote
SOURCE_SPOT_SCALED = "spot-scaled"   # v109: futures bars x live spot ratio
```

- [ ] **Step 5: Create `swingbot/core/marketdata/spot_metals.py`**

```python
"""v109: spot gold/silver (XAUUSD / XAGUSD) as spot-priced instruments.

Yahoo has no spot metals series, so a spot symbol's bars are its COMEX
future's bars (GC=F / SI=F) rescaled by one live spot/futures ratio, and its
live price is gold-api.com's keyless spot quote. One constant multiplier
across a frame preserves every percentage distance, indicator crossing and
level ordering, so detection on XAUUSD equals detection on GC=F -- only the
price scale differs (tests/marketdata/test_spot_scaling_parity.py).

Cache rule (docs/claude/known-traps.md, two OHLCV caches): only the raw
futures frame is ever cached, under its own name (GC_F). A scaled frame is
computed on read and never written under XAUUSD -- it would freeze one day's
ratio into every later day's levels.
"""
import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot import config

log = logging.getLogger("swing-bot.spot_metals")

#: spot symbol -> (gold-api.com metal code, Yahoo futures symbol). The single
#: source of truth: another spot metal is one line here.
SPOT_PAIRS: dict[str, tuple[str, str]] = {
    "XAUUSD": ("XAU", "GC=F"),
    "XAGUSD": ("XAG", "SI=F"),
}
QUOTE_URL = "https://api.gold-api.com/price/{code}"
QUOTE_TIMEOUT_SECONDS = 10
#: Same TTL as data.py's _price_cache. Failures are cached too, so an outage
#: costs one blocking GET per 15 s rather than one per caller.
QUOTE_CACHE_TTL_SECONDS = 15

_quote_cache: dict = {}   # key -> (SpotQuote | None, fetched_at monotonic)
_failing: set = set()     # keys inside a failure streak (logged once)


@dataclass(frozen=True)
class SpotQuote:
    price: float
    updated_at: datetime   # aware, UTC


def _key(symbol) -> str:
    return str(symbol or "").upper().strip()


def is_spot_metal(symbol) -> bool:
    return _key(symbol) in SPOT_PAIRS


def underlying(symbol) -> str:
    """The Yahoo futures symbol a spot symbol's bars are scaled from.
    KeyError for a non-spot symbol."""
    return SPOT_PAIRS[_key(symbol)][1]


def cache_symbol(symbol: str) -> str:
    """What a cache writer stores for `symbol`: the underlying future for a
    spot symbol (the cache rule), else `symbol` unchanged."""
    key = _key(symbol)
    return SPOT_PAIRS[key][1] if key in SPOT_PAIRS else symbol


def cache_symbols(symbols) -> list:
    return list(dict.fromkeys(cache_symbol(s) for s in symbols))


def split_spot(tickers) -> tuple:
    """(spot symbols, everything else), each in input order."""
    tickers = list(tickers)
    return ([t for t in tickers if is_spot_metal(t)],
            [t for t in tickers if not is_spot_metal(t)])


def reset() -> None:
    """Tests only: forget cached quotes and failure streaks."""
    _quote_cache.clear()
    _failing.clear()


def _now_mono() -> float:
    return time.monotonic()


def _raw_get(url: str) -> str:
    """The HTTP GET, split out so tests never touch the network
    (marketdata/fmp_client.py's pattern)."""
    req = urllib.request.Request(url, headers={"User-Agent": "swingbot-spot/1.0"})
    with urllib.request.urlopen(req, timeout=QUOTE_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", "replace")


def _parse_quote(body: str):
    data = json.loads(body)
    price = float(data["price"])
    if price <= 0:
        return None
    updated = datetime.fromisoformat(str(data["updatedAt"]).replace("Z", "+00:00"))
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return SpotQuote(price, updated)


def _note_failure(key: str, why: str) -> None:
    if key not in _failing:
        _failing.add(key)
        log.warning("%s: spot quote unavailable (%s) -- not logged again until it recovers",
                    key, why)


def _note_success(key: str) -> None:
    if key in _failing:
        _failing.discard(key)
        log.info("%s: spot quote recovered", key)


def _fetch_quote(key: str):
    try:
        quote = _parse_quote(_raw_get(QUOTE_URL.format(code=SPOT_PAIRS[key][0])))
    except Exception as exc:
        _note_failure(key, f"{type(exc).__name__}: {exc}")
        return None
    if quote is None:
        _note_failure(key, "non-positive price")
        return None
    _note_success(key)
    return quote


def _cached_quote(key: str):
    now = _now_mono()
    hit = _quote_cache.get(key)
    if hit is not None and now - hit[1] < QUOTE_CACHE_TTL_SECONDS:
        return hit[0]
    quote = _fetch_quote(key)
    _quote_cache[key] = (quote, now)
    return quote


def quote_with_reason(symbol, *, now: datetime | None = None) -> tuple:
    """(SpotQuote, "") for a fresh quote, else (None, why). Stale is missing."""
    key = _key(symbol)
    if key not in SPOT_PAIRS:
        return None, f"{key} is not a spot metal"
    quote = _cached_quote(key)
    if quote is None:
        return None, "spot quote missing"
    age = ((now or datetime.now(timezone.utc)) - quote.updated_at).total_seconds()
    if age > float(config.SPOT_QUOTE_MAX_AGE_SECONDS):
        return None, f"spot quote stale ({age:.0f}s old)"
    return quote, ""


def spot_quote(symbol, *, now: datetime | None = None):
    """The fresh spot quote for a spot symbol, or None (missing, stale, not spot)."""
    return quote_with_reason(symbol, now=now)[0]
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_metals.py`
Expected: PASS. Then run `python scripts/dev/testrun.py file tests/test_env_example_sync.py` and `python scripts/dev/testrun.py file tests/test_config_alpaca.py`. Both should PASS, since the new key is in `.env.example`.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/spot_metals.py swingbot/core/marketdata/providers/base.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py .env.example swingbot/core/marketdata/providers/base.py swingbot/core/marketdata/spot_metals.py tests/marketdata/test_spot_metals.py
git commit -m "feat(v109): spot metals quote client and SPOT_QUOTE_MAX_AGE_SECONDS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/config.py .env.example swingbot/core/marketdata/providers/base.py swingbot/core/marketdata/spot_metals.py tests/marketdata/test_spot_metals.py
```

---

### Task V109-2: Spot ratio, frame scaling and the detection-parity proof

Load the `no-lookahead` skill first.

**Files:**
- Modify: `swingbot/core/marketdata/spot_metals.py` (append)
- Modify: `tests/marketdata/test_spot_metals.py` (append)
- Create: `tests/marketdata/test_spot_scaling_parity.py`

**Interfaces:**
- Consumes: V109-1's `quote_with_reason`, `underlying`, `_key`, `SPOT_PAIRS`; `base.SOURCE_SPOT_SCALED`; `data.get_current_price_batch(tickers, *, allow_stale=True) -> dict` (existing, `data.py:140`); `levels.build_level_map`, `levels.atr_floor_pct`, `levels.build_scenarios` (existing, `levels.py:564/635/648`); `entry_filters.ENTRY_FUNCS` (existing); `strategy_types.HORIZONS`; fixtures `tests/fixtures/v74/AAPL.csv`, `XOM.csv` (500 daily bars each, committed).
- Produces:
  - `RATIO_BAND = (0.95, 1.05)`.
  - `SpotRatio(symbol: str, spot: float, underlying: str, futures: float, ratio: float)` (frozen dataclass).
  - `_futures_price(symbol: str) -> float | None`.
  - `spot_ratio_detail(symbol, *, now=None) -> tuple[SpotRatio | None, str]`.
  - `spot_ratio(symbol, *, now=None) -> float | None`.
  - `scale_frame(df, reading: SpotRatio) -> DataFrame`. Its attrs are `source="spot-scaled:<underlying>"`, `spot_ratio`, `spot_price`, `futures_price` and `spot_underlying`. It also keeps any attrs the input had, and never mutates the input.
  - `scale_underlying(symbol, raw: DataFrame | None) -> tuple[DataFrame | None, str]`. It checks `raw` before any network call.

- [ ] **Step 1: Append the failing unit tests to `tests/marketdata/test_spot_metals.py`**

```python
# --- V109-2: ratio and scaling ---------------------------------------------
import pickle

import pandas as pd

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


def _gc():
    df = pd.DataFrame({"Open": [4000.0, 4010.0], "High": [4020.0, 4030.0],
                       "Low": [3990.0, 4000.0], "Close": [4010.0, 4020.0],
                       "Volume": [1000.0, 1200.0]},
                      index=pd.DatetimeIndex(["2026-09-24", "2026-09-25"]))
    df.attrs["source"] = "yfinance"
    return df


def test_ratio_is_spot_over_the_live_future(monkeypatch):
    _serve(monkeypatch, _body())
    asked = []
    monkeypatch.setattr(sm, "_futures_price", lambda s: asked.append(s) or 4175.30)
    reading, reason = sm.spot_ratio_detail("XAUUSD", now=NOW)
    assert (reading, reason) == (READING, "")
    assert asked == ["GC=F"]
    assert f"{reading.ratio:.5f}" == "0.99435"
    assert sm.spot_ratio("XAUUSD", now=NOW) == READING.ratio


def test_missing_quote_never_asks_for_the_future(monkeypatch):
    _serve(monkeypatch, OSError("down"))
    monkeypatch.setattr(sm, "_futures_price", lambda s: pytest.fail("no futures read"))
    assert sm.spot_ratio_detail("XAUUSD", now=NOW) == (None, "spot quote missing")


@pytest.mark.parametrize("futures", [None, 0.0, -1.0])
def test_missing_future_is_none(monkeypatch, futures):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(sm, "_futures_price", lambda s: futures)
    assert sm.spot_ratio_detail("XAUUSD", now=NOW) == (None, "GC=F live price unavailable")


@pytest.mark.parametrize("futures", [3000.0, 4500.0])
def test_ratio_outside_the_sanity_band_is_rejected_and_logged(monkeypatch, caplog, futures):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(sm, "_futures_price", lambda s: futures)
    caplog.set_level(logging.WARNING, logger="swing-bot.spot_metals")
    reading, reason = sm.spot_ratio_detail("XAUUSD", now=NOW)
    assert reading is None and "outside" in reason
    assert any("outside" in r.getMessage() for r in caplog.records)
    assert sm.spot_ratio("XAUUSD", now=NOW) is None


def test_futures_price_is_a_trading_grade_read(monkeypatch):
    from swingbot.core.marketdata import data as data_mod
    seen = {}

    def fake(tickers, *, allow_stale=True):
        seen.update(tickers=list(tickers), allow_stale=allow_stale)
        return {"GC=F": 4175.30}
    monkeypatch.setattr(data_mod, "get_current_price_batch", fake)
    assert sm._futures_price("GC=F") == 4175.30
    assert seen == {"tickers": ["GC=F"], "allow_stale": False}


def test_scale_frame_multiplies_prices_only():
    raw = _gc()
    out = sm.scale_frame(raw, READING)
    for col in ("Open", "High", "Low", "Close"):
        assert out[col].tolist() == pytest.approx((raw[col] * READING.ratio).tolist())
    assert out["Volume"].tolist() == [1000.0, 1200.0]
    assert raw["Close"].tolist() == [4010.0, 4020.0]          # input untouched
    assert raw.attrs == {"source": "yfinance"}
    assert out.attrs["source"] == "spot-scaled:GC=F"
    assert out.attrs["spot_ratio"] == READING.ratio
    assert out.attrs["spot_price"] == 4151.70
    assert out.attrs["futures_price"] == 4175.30
    assert out.attrs["spot_underlying"] == "GC=F"


def test_scaled_attrs_survive_the_spawn_pickle():
    out = sm.scale_frame(_gc(), READING)
    assert pickle.loads(pickle.dumps(out)).attrs == out.attrs


def test_scale_underlying_checks_bars_before_any_network(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: pytest.fail("no ratio read"))
    assert sm.scale_underlying("XAUUSD", None) == (None, "no GC=F bars")
    assert sm.scale_underlying("XAUUSD", _gc().iloc[0:0]) == (None, "no GC=F bars")


def test_scale_underlying_passes_the_ratio_reason_through(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: (None, "spot quote stale (1200s old)"))
    assert sm.scale_underlying("XAUUSD", _gc()) == (None, "spot quote stale (1200s old)")


def test_scale_underlying_scales(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: (READING, ""))
    df, reason = sm.scale_underlying("XAUUSD", _gc())
    assert reason == "" and df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4020.0 * READING.ratio)
```

- [ ] **Step 2: Create the parity test `tests/marketdata/test_spot_scaling_parity.py`**

```python
"""v109 NO-LOOKAHEAD / detection-parity proof for spot metals.

A spot frame is its futures frame times ONE constant ratio. That must leave
every entry signal, level and scenario identical up to the price scale --
otherwise XAUUSD alerts would differ from GC=F alerts for a reason other than
the basis, and the spec's "detection is unchanged by construction" would be
false. The committed v74 fixtures (500 real daily bars) are lifted to a
metals-like price scale so the signals are real, not vacuous.

If a strategy fails here, do NOT loosen the assertion: that strategy reads an
absolute price somewhere, and the controller must decide (BLOCKED).
"""
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import entry_filters, levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.marketdata import spot_metals as sm

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "v74"
RATIO = 4151.70 / 4175.30          # the 2026-09-28 measured gold basis
READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, RATIO)


def _futures_like(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / f"{name}.csv", index_col=0, parse_dates=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype("float64")
    df[["Open", "High", "Low", "Close"]] *= 20.0   # ~3000-4000, a gold-like scale
    return df


def _signals(df, strategy):
    out = []
    for horizon in HORIZONS:
        bull, bear = entry_filters.ENTRY_FUNCS[strategy](df, horizon)
        out.append((horizon,
                    bull.fillna(False).astype(bool).tolist(),
                    bear.fillna(False).astype(bool).tolist()))
    return out


@pytest.mark.parametrize("name", ["AAPL", "XOM"])
@pytest.mark.parametrize("strategy", sorted(entry_filters.ENTRY_FUNCS))
def test_entry_signals_identical_on_scaled_bars(name, strategy):
    raw = _futures_like(name)
    assert _signals(sm.scale_frame(raw, READING), strategy) == _signals(raw, strategy)


def test_the_parity_fixtures_are_not_vacuous():
    total = 0
    for name in ("AAPL", "XOM"):
        raw = _futures_like(name)
        for strategy in entry_filters.ENTRY_FUNCS:
            total += sum(sum(b) + sum(s) for _, b, s in _signals(raw, strategy))
    assert total >= 50, "fixtures must fire real signals for parity to mean anything"


def _plan(df, horizon):
    h = HORIZONS[horizon]
    price = float(df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(df, h, price)
    floor = levels.atr_floor_pct(df, price, h)
    scenarios = levels.build_scenarios(price, supports, resistances, min_reward_pct=1.0,
                                       atr_floor=floor, min_stop_distance_pct=0.5,
                                       max_stop_distance_pct=15.0)
    return price, supports, resistances, floor, scenarios


def _scaled(values):
    return [None if v is None else v * RATIO for v in values]


@pytest.mark.parametrize("name,horizon", [("XOM", "4w"), ("XOM", "3m"), ("AAPL", "4w")])
def test_levels_and_scenarios_are_the_futures_ones_times_the_ratio(name, horizon):
    raw = _futures_like(name)
    p0, s0, r0, f0, sc0 = _plan(raw, horizon)
    p1, s1, r1, f1, sc1 = _plan(sm.scale_frame(raw, READING), horizon)
    assert p1 == pytest.approx(p0 * RATIO, rel=1e-12)
    assert [lv.price for lv in s1] == pytest.approx(_scaled([lv.price for lv in s0]), rel=1e-9)
    assert [lv.price for lv in r1] == pytest.approx(_scaled([lv.price for lv in r0]), rel=1e-9)
    assert [len(lv.sources) for lv in s1] == [len(lv.sources) for lv in s0]
    assert [len(lv.sources) for lv in r1] == [len(lv.sources) for lv in r0]
    assert f1 == pytest.approx(f0, rel=1e-9)
    assert [s.direction for s in sc1] == [s.direction for s in sc0]
    for a, b in zip(sc0, sc1):
        assert [b.entry, b.stop_loss, b.take_profit] == pytest.approx(
            _scaled([a.entry, a.stop_loss, a.take_profit]), rel=1e-9)
        assert (b.target2_price is None) == (a.target2_price is None)
        if a.target2_price is not None:
            assert b.target2_price == pytest.approx(a.target2_price * RATIO, rel=1e-9)
        assert b.risk_reward_ratio == a.risk_reward_ratio
        assert b.stop_distance_pct == pytest.approx(a.stop_distance_pct, rel=1e-9)


def test_the_scenario_fixture_builds_both_directions():
    *_, scenarios = _plan(_futures_like("XOM"), "3m")
    assert sorted(s.direction for s in scenarios) == ["bearish", "bullish"]
```

- [ ] **Step 3: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_metals.py`
Expected: FAIL. `AttributeError: module ... has no attribute 'SpotRatio'`.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_scaling_parity.py`
Expected: FAIL. Same `AttributeError`.

- [ ] **Step 4: Append the implementation to `spot_metals.py`**

Add `from swingbot.core.marketdata.providers.base import SOURCE_SPOT_SCALED` to the imports (after `from swingbot import config`). Then append:

```python
#: A reading outside this band is a bad quote or a contract-roll glitch, and
#: must not rescale a whole history.
RATIO_BAND = (0.95, 1.05)
_PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


@dataclass(frozen=True)
class SpotRatio:
    symbol: str
    spot: float
    underlying: str
    futures: float
    ratio: float


def _futures_price(symbol: str):
    """The future's live price, trading-grade (no stale last-good fallback).
    Imported here: data.py imports the router, which imports this module."""
    from swingbot.core.marketdata.data import get_current_price_batch
    return get_current_price_batch([symbol], allow_stale=False).get(symbol)


def spot_ratio_detail(symbol, *, now: datetime | None = None) -> tuple:
    """(SpotRatio, "") or (None, why). Missing/stale spot, a missing future
    price, or a ratio outside RATIO_BAND are all None."""
    quote, reason = quote_with_reason(symbol, now=now)
    if quote is None:
        return None, reason
    key = _key(symbol)
    under = SPOT_PAIRS[key][1]
    futures = _futures_price(under)
    if not futures or futures <= 0:
        return None, f"{under} live price unavailable"
    ratio = quote.price / float(futures)
    if not RATIO_BAND[0] <= ratio <= RATIO_BAND[1]:
        log.warning("%s: spot ratio %.5f (spot %.2f / %s %.2f) outside [%.2f, %.2f] -- rejected",
                    key, ratio, quote.price, under, futures, *RATIO_BAND)
        return None, f"ratio {ratio:.5f} outside [{RATIO_BAND[0]}, {RATIO_BAND[1]}]"
    return SpotRatio(key, quote.price, under, float(futures), ratio), ""


def spot_ratio(symbol, *, now: datetime | None = None):
    reading, _ = spot_ratio_detail(symbol, now=now)
    return reading.ratio if reading is not None else None


def scale_frame(df, reading: SpotRatio):
    """A copy of `df` with Open/High/Low/Close x reading.ratio. Volume and
    every other column (market-context columns included) are untouched.
    One constant multiplier: every % distance, crossing and ordering is
    preserved, and no bar reads anything but itself."""
    out = df.copy()
    cols = [c for c in _PRICE_COLUMNS if c in out.columns]
    out[cols] = out[cols] * reading.ratio
    out.attrs = {**df.attrs,
                 "source": f"{SOURCE_SPOT_SCALED}:{reading.underlying}",
                 "spot_ratio": reading.ratio, "spot_price": reading.spot,
                 "futures_price": reading.futures, "spot_underlying": reading.underlying}
    return out


def scale_underlying(symbol, raw) -> tuple:
    """(scaled frame, "") from the underlying's raw bars, or (None, why).
    Checks the bars first so an empty fetch costs no quote/price call."""
    under = underlying(symbol)
    if raw is None or raw.empty:
        return None, f"no {under} bars"
    reading, reason = spot_ratio_detail(symbol)
    if reading is None:
        return None, reason
    return scale_frame(raw, reading), ""
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_metals.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_spot_scaling_parity.py`
Expected: PASS. A pre-write check on this machine found no mismatch, for both fixtures across all 10 horizons and all 15 `ENTRY_FUNCS` strategies (v104's masked short entries included), at this ratio. If a strategy mismatches now, stop and report `BLOCKED` with the strategy/horizon. Do not edit the assertion.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/spot_metals.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/marketdata/spot_metals.py tests/marketdata/test_spot_metals.py tests/marketdata/test_spot_scaling_parity.py
git commit -m "feat(v109): spot ratio, frame scaling and the detection-parity proof

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/spot_metals.py tests/marketdata/test_spot_metals.py tests/marketdata/test_spot_scaling_parity.py
```

---

# Phase B — Hook points

### Task V109-3: Classification, liquidity/RS exemption and earnings short-circuit

**Files:**
- Modify: `swingbot/core/marketdata/asset_class.py` (`classify`, line 68; module docstring)
- Modify: `swingbot/core/marketdata/universe.py` (`_VOLUME_NOT_SHARES`, line 35, and its comment)
- Modify: `swingbot/core/market/events.py` (the three `is_etf(ticker)` guards at ~lines 50, 157, 183)
- Modify: `tests/marketdata/test_asset_class.py` (the `("XAUUSD", "future")` row at line 60)
- Modify: `tests/marketdata/test_universe.py` (parametrize list at line 32; one new test)
- Create: `tests/market/test_events_spot.py`

**Interfaces:**
- Consumes: V109-1 `spot_metals.is_spot_metal`.
- Produces: `classify("XAUUSD") == classify("XAGUSD") == "spot_metal"`, `is_rs_eligible("XAUUSD") is False`, `"spot_metal" in universe._VOLUME_NOT_SHARES`, `events._never_reports(ticker) -> bool`.

- [ ] **Step 1: Write the failing tests**

In `tests/marketdata/test_asset_class.py`, change the parametrize row `("XAUUSD", "future"),` inside `test_classify_handles_unresolved_watchlist_aliases` to `("XAUUSD", "spot_metal"),`, and add the row `("XAGUSD", "spot_metal"),` below it. Leave `test_classification_uses_the_resolved_symbol_not_the_alias` alone: `candidate_symbols("XAUUSD")[1]` is still `GC=F`, a future. Then append:

```python
@pytest.mark.parametrize("symbol", ["XAUUSD", "XAGUSD", " xauusd "])
def test_spot_metals_classify_before_the_alias_walk(symbol):
    """v109: XAUUSD is spot-priced now, not an alias of GC=F."""
    assert classify(symbol) == "spot_metal"
    assert is_rs_eligible(symbol) is False


@pytest.mark.parametrize("symbol,expected", [
    ("GC=F", "future"), ("SI=F", "future"), ("XAU", "future"), ("GOLD", "equity"),
])
def test_futures_and_other_aliases_are_unchanged(symbol, expected):
    assert classify(symbol) == expected
```

In `tests/marketdata/test_universe.py`, change the parametrize list of `test_non_share_symbols_skip_the_dollar_volume_floor` to `["SI=F", "XAGUSD", "XAUUSD", "GC=F", "EURUSD=X", "^GSPC"]` and append:

```python
def test_spot_metal_class_is_volume_exempt():
    from swingbot.core.marketdata.universe import _VOLUME_NOT_SHARES
    assert "spot_metal" in _VOLUME_NOT_SHARES


def test_spot_metals_still_need_history_and_price():
    from swingbot.core.marketdata.universe import liquidity_reason
    assert liquidity_reason(make_ohlcv(np.full(10, 4150.0)), symbol="XAUUSD") is not None
```

Create `tests/market/test_events_spot.py`:

```python
"""v109: spot metals never report earnings -- and never ask Yahoo."""
import pytest

from swingbot.core.market import events


@pytest.fixture(autouse=True)
def _no_yahoo(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a spot metal reached Yahoo's earnings endpoints")
    monkeypatch.setattr(events.yf, "Ticker", boom)
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
    yield
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()


@pytest.mark.parametrize("symbol", ["XAUUSD", "XAGUSD", "xauusd"])
def test_spot_metals_have_no_earnings(symbol):
    assert events.get_next_earnings_date(symbol) is None
    assert events.get_next_earnings_datetime(symbol) is None
    assert events.get_earnings_datetimes(symbol, refresh=True) == []
    assert events.earnings_within_window(symbol, 30) is None


def test_never_reports_covers_funds_and_spot(monkeypatch):
    monkeypatch.setattr(events, "is_etf", lambda t: t == "SPY")
    assert events._never_reports("SPY") and events._never_reports("XAUUSD")
    assert not events._never_reports("AAPL") and not events._never_reports("GC=F")
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_asset_class.py`
Expected: FAIL (`'future' == 'spot_metal'`).
Run: `python scripts/dev/testrun.py file tests/market/test_events_spot.py`
Expected: FAIL (`AssertionError: a spot metal reached Yahoo's earnings endpoints`, `AttributeError: _never_reports`).

- [ ] **Step 3: Implement `classify`**

In `asset_class.classify`, directly after the `if sym in _OVERRIDES: return _OVERRIDES[sym]` block and before the `candidate_symbols` import, insert:

```python
    # v109: spot metals are their own instrument -- checked before the alias
    # walk, which would read XAUUSD as its GC=F alias ("future").
    from swingbot.core.marketdata.spot_metals import is_spot_metal
    if is_spot_metal(sym):
        return "spot_metal"
```

(Import inside the function: `spot_metals` imports `providers/base`, which imports this module.) In the module docstring, after the paragraph ending "...an already-resolved Yahoo symbol.", add:

```
v109: XAUUSD / XAGUSD are the exception -- they are spot-priced instruments
(core/marketdata/spot_metals.py), classified "spot_metal" before the alias
walk. RS-exempt like futures; volume-exempt (universe._VOLUME_NOT_SHARES).
```

- [ ] **Step 4: Implement the volume exemption**

In `universe.py`, replace the `_VOLUME_NOT_SHARES` line and extend its comment:

```python
#: Asset classes whose Yahoo "Volume" is not a share count: futures report
#: contracts (SI=F is 5,000 oz each), FX and indices report 0. Close x Volume
#: is meaningless for them, so only the history and price floors apply.
#: v109: spot metals carry their future's contract volume unchanged.
_VOLUME_NOT_SHARES = frozenset({"future", "fx", "index", "spot_metal"})
```

- [ ] **Step 5: Implement the earnings short-circuit**

In `events.py`, add `from swingbot.core.marketdata.spot_metals import is_spot_metal` beside the existing `from swingbot.core.marketdata.universe import is_etf`, and add after `_NOT_CACHED = object()`:

```python
def _never_reports(ticker: str) -> bool:
    """Funds and spot metals (v109) never report earnings: never gate, never fetch."""
    return is_etf(ticker) or is_spot_metal(ticker)
```

Then change the guard in each of `get_next_earnings_date`, `_fetch_next_earnings_datetime` and `get_earnings_datetimes` from `if is_etf(ticker):` to `if _never_reports(ticker):`. The return values stay unchanged (`None`, `None`, `[]`).

- [ ] **Step 6: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_asset_class.py`, `python scripts/dev/testrun.py file tests/marketdata/test_universe.py`, `python scripts/dev/testrun.py file tests/market/test_events_spot.py`
Expected: all PASS.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/asset_class.py swingbot/core/marketdata/universe.py swingbot/core/market/events.py`
Expected: `get_earnings_datetimes` still at C (14). The guard swap adds no branch. Nothing else from these files is listed except functions this task did not touch.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/marketdata/asset_class.py swingbot/core/marketdata/universe.py swingbot/core/market/events.py tests/marketdata/test_asset_class.py tests/marketdata/test_universe.py tests/market/test_events_spot.py
git commit -m "feat(v109): spot_metal asset class -- RS/volume exempt, no earnings lookups

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/asset_class.py swingbot/core/marketdata/universe.py swingbot/core/market/events.py tests/marketdata/test_asset_class.py tests/marketdata/test_universe.py tests/market/test_events_spot.py
```

---

### Task V109-4: Router spot branches

**Files:**
- Modify: `swingbot/core/marketdata/providers/router.py` (imports lines 14-18; `reset` line 72; `daily_bars` line 135; `latest_prices` line 142; `intraday_bars` line 159; new helpers)
- Create: `tests/marketdata/test_provider_router_spot.py`

**Interfaces:**
- Consumes: V109-1 `split_spot`, `underlying`, `quote_with_reason`, `is_spot_metal`, `base.SOURCE_SPOT`. V109-2 `scale_underlying`, `SpotRatio`.
- Produces:
  - `router.daily_bars(tickers, period, yf_fetch)` returns spot symbols as scaled frames, keyed by the spot symbol. The spot symbol is never passed to `yf_fetch` or Alpaca. Its underlying is fetched under its own name, reusing a frame the same call already fetched.
  - `router.latest_prices(tickers, yf_fetch)` returns the spot quote price for spot symbols, with `last_source(sym) == "spot"`.
  - `router.intraday_bars(ticker, interval, yf_fetch)` returns the scaled underlying for a spot symbol, or `None`.
  - `router.spot_miss_reason(ticker) -> str | None` gives the last reason a spot symbol got no frame/price in this process. `reset()` clears it.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_provider_router_spot.py`:

```python
"""v109: the router splits spot metals off before Alpaca/yfinance."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import spot_metals as sm
from swingbot.core.marketdata.providers import router

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)
SILVER = sm.SpotRatio("XAGUSD", 48.0, "SI=F", 48.4, 48.0 / 48.4)
QUOTE = sm.SpotQuote(4151.70, datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc))


def _frame(close=4000.0):
    return pd.DataFrame({"Open": [close], "High": [close], "Low": [close],
                         "Close": [close], "Volume": [10.0]},
                        index=pd.DatetimeIndex(["2026-09-25"]))


@pytest.fixture(autouse=True)
def _plain(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    router.reset()
    yield
    router.reset()


def _ratio_ok(monkeypatch):
    table = {"XAUUSD": READING, "XAGUSD": SILVER}
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (table[s], ""))


def _yf_daily(calls, have=("AAPL", "GC=F", "SI=F")):
    def fetch(tickers, period):
        calls.append(list(tickers))
        return {t: _frame() for t in tickers if t in have}
    return fetch


def test_daily_spot_is_scaled_future_and_never_asked_by_name(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["AAPL", "XAUUSD"], "2y", _yf_daily(calls))
    assert calls == [["AAPL"], ["GC=F"]]
    assert set(out) == {"AAPL", "XAUUSD"}
    assert out["XAUUSD"]["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert out["XAUUSD"].attrs["source"] == "spot-scaled:GC=F"
    assert out["AAPL"].attrs["source"] == "yfinance"


def test_daily_reuses_a_future_the_same_call_fetched(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["GC=F", "XAUUSD", "XAGUSD"], "2y", _yf_daily(calls))
    assert calls == [["GC=F"], ["SI=F"]]
    assert out["GC=F"]["Close"].iloc[-1] == 4000.0          # the raw future, unscaled
    assert out["GC=F"].attrs["source"] == "yfinance"
    assert set(out) == {"GC=F", "XAUUSD", "XAGUSD"}


def test_daily_spot_only_call(monkeypatch):
    _ratio_ok(monkeypatch)
    calls = []
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily(calls))
    assert calls == [["GC=F"]] and list(out) == ["XAUUSD"]


def test_daily_outage_drops_the_spot_symbol_and_records_why(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    assert out == {}
    assert router.spot_miss_reason("xauusd") == "spot quote missing"


def test_daily_missing_future_bars(monkeypatch):
    _ratio_ok(monkeypatch)
    out = router.daily_bars(["XAUUSD"], "2y", _yf_daily([], have=()))
    assert out == {} and router.spot_miss_reason("XAUUSD") == "no GC=F bars"


def test_a_later_hit_clears_the_miss(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    _ratio_ok(monkeypatch)
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    assert router.spot_miss_reason("XAUUSD") is None


def test_latest_prices_serve_the_spot_quote(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (QUOTE, ""))
    asked = []
    out = router.latest_prices(["AAPL", "XAUUSD"],
                               lambda ts: asked.append(list(ts)) or {"AAPL": 190.0})
    assert asked == [["AAPL"]]
    assert out == {"AAPL": 190.0, "XAUUSD": 4151.70}
    assert router.last_source("XAUUSD") == "spot"
    assert router.last_source("AAPL") == "yfinance"


def test_latest_prices_outage_is_absent_never_futures(monkeypatch):
    monkeypatch.setattr(sm, "quote_with_reason", lambda s, **k: (None, "spot quote stale (1200s old)"))
    out = router.latest_prices(["XAUUSD"], lambda ts: pytest.fail("no yfinance call"))
    assert out == {}
    assert router.spot_miss_reason("XAUUSD") == "spot quote stale (1200s old)"


def test_intraday_spot_scales_the_future(monkeypatch):
    _ratio_ok(monkeypatch)
    asked = []
    df = router.intraday_bars("XAUUSD", "1h", lambda t, iv: asked.append((t, iv)) or _frame())
    assert asked == [("GC=F", "1h")]
    assert df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)


def test_intraday_outage_is_none(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    assert router.intraday_bars("XAUUSD", "1h", lambda t, iv: _frame()) is None


def test_reset_clears_spot_misses(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    router.daily_bars(["XAUUSD"], "2y", _yf_daily([]))
    router.reset()
    assert router.spot_miss_reason("XAUUSD") is None
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router_spot.py`
Expected: FAIL. `AttributeError: module 'swingbot.core.marketdata.providers.router' has no attribute 'spot_miss_reason'`, and `calls == [["AAPL", "XAUUSD"]]` mismatches.

- [ ] **Step 3: Implement**

Imports in `router.py`:

```python
from swingbot import config
from swingbot.core.marketdata import spot_metals
from swingbot.core.marketdata.providers.alpaca_provider import (
    AlpacaAuthError, AlpacaMiss, AlpacaProvider)
from swingbot.core.marketdata.providers.base import (
    SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_SPOT, SOURCE_YF, is_alpaca_eligible)
```

After `_last_source: dict = {}` add `_spot_miss: dict = {}`, and in `reset()` add `_spot_miss.clear()` after `_last_source.clear()`.

Add these helpers after `_merge`:

```python
def _scaled_or_miss(ticker, raw):
    """v109: one spot symbol's scaled frame, or None with the reason recorded
    for spot_miss_reason() (the scan crawl reads it back in its worker)."""
    df, reason = spot_metals.scale_underlying(ticker, raw)
    key = str(ticker).upper().strip()
    if df is None:
        _spot_miss[key] = reason
        log.info("%s: no spot-scaled bars (%s)", key, reason)
    else:
        _spot_miss.pop(key, None)
    return df


def _spot_daily(spot, have: dict, fetch) -> dict:
    """v109: spot symbols are never sent to Alpaca or to yfinance under their
    own name -- their future is fetched under ITS name (reusing a frame this
    call already has) and rescaled by the live spot ratio."""
    if not spot:
        return {}
    unders = list(dict.fromkeys(spot_metals.underlying(t) for t in spot))
    need = [u for u in unders if u not in have]
    raw = {**have, **(fetch(need) if need else {})}
    scaled = {t: _scaled_or_miss(t, raw.get(spot_metals.underlying(t))) for t in spot}
    return {t: df for t, df in scaled.items() if df is not None}


def _spot_prices(spot) -> dict:
    """v109: a spot symbol's live price is its spot quote -- or nothing."""
    out = {}
    for ticker in spot:
        quote, reason = spot_metals.quote_with_reason(ticker)
        if quote is None:
            _spot_miss[str(ticker).upper().strip()] = reason
            continue
        out[ticker] = quote.price
        _last_source[ticker] = SOURCE_SPOT
    return out
```

Replace `daily_bars`, `latest_prices` and `intraday_bars` with the following. The only changes are the first line of each, the spot `update` line, and `intraday_bars`' spot guard:

```python
def daily_bars(tickers, period, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
    wanted, rest = _split(tickers)
    got = (_attempt("daily_bars", wanted, period) or {}) if wanted else {}
    misses = [t for t in wanted if t not in got]
    out = _merge(got, rest, misses, lambda ts: yf_fetch(ts, period))
    out.update(_spot_daily(spot, out, lambda ts: yf_fetch(ts, period)))
    return out


def latest_prices(tickers, yf_fetch):
    spot, tickers = spot_metals.split_spot(tickers)
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
    out.update(_spot_prices(spot))
    return out


def intraday_bars(ticker, interval, yf_fetch):
    if spot_metals.is_spot_metal(ticker):
        # v109: the future's bars under its own name, rescaled -- never the
        # spot symbol itself, never unscaled.
        return _scaled_or_miss(
            ticker, intraday_bars(spot_metals.underlying(ticker), interval, yf_fetch))
    # Only 1h is served by Alpaca; any other interval is plain yfinance,
    # not a fallback.
    if interval != "1h" or not is_alpaca_eligible(ticker) or _active_provider() is None:
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
```

Add after `last_source`:

```python
def spot_miss_reason(ticker: str):
    """v109: why this process last served a spot symbol no frame/price, or None."""
    return _spot_miss.get(str(ticker).upper().strip())
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router_spot.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: PASS (no regression in the Alpaca paths).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/marketdata/providers/router.py`
Expected: no output (`latest_prices` stays at 9, `intraday_bars` goes to 8).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/marketdata/providers/router.py tests/marketdata/test_provider_router_spot.py
git commit -m "feat(v109): router serves spot metals -- scaled futures bars, spot quote prices

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/marketdata/providers/router.py tests/marketdata/test_provider_router_spot.py
```
