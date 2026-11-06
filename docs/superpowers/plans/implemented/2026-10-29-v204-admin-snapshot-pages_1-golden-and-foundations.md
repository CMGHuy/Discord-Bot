# v204 Admin snapshot pages, part 1: golden payloads and foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Index:** [`_0-index.md`](2026-10-29-v204-admin-snapshot-pages_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract (Config fields, Contract module additions, Table, Repository) live there and bind every task below.

Part scope: V204-1 … V204-4. Frozen golden payloads from today's request code, the measure-first timing of Analytics and Calendar, the snapshot config fields and key helpers, and the `admin_snapshots` table with its compare-and-set repository. No page handler changes in this part.

`<wt>` is the implementation worktree's absolute path. v201 must be merged (index, Global Constraints) before V204-1. Every DB-backed test needs the shared `swing-db` replica (`/replicate-prod-db`) before its first run.

# Phase 1: Freeze and measure

### Task V204-1: Golden parity payloads from today's request code; `admin-snapshots` suite

**Model:** opus — the frozen reference every parity test in parts 2–4 compares against; a non-deterministic or network-touched golden file makes every later parity verdict meaningless.

**Files:**
- Create: `tests/admin_snapshots/__init__.py` (empty)
- Create: `tests/admin_snapshots/golden_book.py`
- Create: `tests/admin_snapshots/record_golden.py`
- Create: `tests/admin_snapshots/golden/{risk,performance_main,equity_curve_main,calendar_pnl,analytics_snapshot,sparkline}.json` (written by Step 5, never by hand)
- Create: `tests/admin_snapshots/test_golden_today.py`
- Modify: `tests/suites.toml` (append `[suites.admin-snapshots]`)

**Interfaces:**
- Consumes: v201 merged (`tests/admin/conftest.py` fixtures `admin_app`, `client`, `_clear_login_limiter`; `fx.quote_currency_code(t, *, fetch=...)`; `fx.fx_rate(..., refresh=...)`).
- Produces (ledger row V204-1, exactly): pytest fixture `golden_book` in `tests/admin_snapshots/golden_book.py`, returning a `GoldenBook(client, tmp_path, network_calls: list[str])`; `golden_payload(name: str) -> dict`; `GOLDEN_NAMES: tuple[str, ...]`; `normalise(body: dict) -> dict`; `GOLDEN_NOW = datetime(2026, 10, 28, 21, 0, tzinfo=UTC)`. Also, for later parity tests: `GOLDEN_MONTH = "2026-06"`, `BAR_SYMBOLS`, and `assert_matches_golden(name: str, body: dict) -> None`. That helper normalises `body` and compares only the golden file's top-level keys, so keys added later (such as V204-12's `market_meta`) never break parity. `record_golden.capture(client) -> dict[str, dict]`. Suite `admin-snapshots`.
- A later test module that uses `golden_book` imports it together with `admin_app`, `client` and `_clear_login_limiter` from `tests.admin_snapshots.golden_book`. Fixtures resolve through the test module's globals, and there is no `tests/admin_snapshots/conftest.py`.

**Behaviour fixed here:**
- Recorded with `ADMIN_REFRESHER="off"` and `MARKETDATA_LAYER="off"`, so every route runs today's request-time code: `_cached(...)`, `collect_portfolio_state`, `get_daily_data_batch` and `refresh_snapshot`.
- No time-freezing library is installed (`freezegun` and `time_machine` are absent). "Frozen at `GOLDEN_NOW`" means the book is anchored there: bars end on 2026-10-28, open trades opened on 2026-08-03, and closed trades closed between January and June 2026. `normalise` removes wall-clock values: `checked_at` and `built_at` at any depth, the top-level `killswitch`, `scan_health` and `as_of`, and `availability.killswitch`. If a figure still depends on the run date, its dotted path goes into `WALL_CLOCK_PATHS` with a comment naming the source. The golden file is never edited by hand.
- Daily bars are real yfinance-basis files (`daily_delta.cache_file(T, BASIS_YF)`) under a tmp working directory. Today's two daily entry points are stubbed to read those same files, so the off path (today) and V204-5's read-only reader see identical frames.
- Every provider entry point is poisoned and records its name. A capture with a non-empty record is a defect. Stub that function with a fixed answer in `golden_book.py`; never record a payload that reached the network.

- [ ] **Step 1: Check the preconditions**

Run: `git -C <wt> grep -n "def refresher_on" swingbot/core/marketdata/shared/admin_refresh.py` and `git -C <wt> grep -n "def request_refresh" swingbot/admin/market_values.py`
Expected: one hit each. Otherwise stop and report `BLOCKED: v201 not merged`.
Run: `git -C <wt> grep -n "def get_quote_batch\|def get_current_price\b\|def get_current_price_batch\|def prefetch_prices\|def _provider_currency_code" swingbot/core/marketdata/data.py`, `git -C <wt> grep -n "def refresh_symbol" swingbot/core/marketdata/data_refresh.py`, `git -C <wt> grep -n "def _refreshed_frame" swingbot/core/marketdata/fx.py`, `git -C <wt> grep -n "def download" swingbot/core/marketdata/yf_safe.py`, `git -C <wt> grep -n "def sector_map" swingbot/core/marketdata/universe.py`
Expected: every name hits (`monkeypatch.setattr` raises on a missing one). Match the `sector_map` stub below to the real parameters.

- [ ] **Step 2: Write `tests/admin_snapshots/golden_book.py`**

```python
"""v204 V204-1: the frozen golden book and its payloads.

The files under golden/ were recorded once, from the request-time code as it
stood before v204 (ADMIN_REFRESHER=off). No later task rewrites them: a parity
failure means the code is wrong, never the file (index, Global Constraints)."""
from __future__ import annotations

import importlib
import json
import math
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from tests.admin.conftest import _clear_login_limiter, admin_app, client  # noqa: F401
from tests.store_seed import seed_store

GOLDEN_DIR = pathlib.Path(__file__).with_name("golden")
GOLDEN_NAMES: tuple[str, ...] = ("risk", "performance_main", "equity_curve_main",
                                 "calendar_pnl", "analytics_snapshot", "sparkline")
GOLDEN_NOW = datetime(2026, 10, 28, 21, 0, tzinfo=timezone.utc)
GOLDEN_MONTH = "2026-06"
BAR_SYMBOLS: tuple[str, ...] = ("AAPL", "MSFT", "SAP.DE", "SPY")
QUOTE_CODES = {"SAP.DE": "EUR"}                  # everything else quotes in USD
FX_RATES = {("EUR", "USD"): 1.1}
SECTORS = {"AAPL": "Technology", "MSFT": "Technology"}   # SAP.DE unmapped on purpose
NETWORK: tuple[tuple[str, str], ...] = (
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
)
VOLATILE_KEYS = frozenset({"checked_at", "built_at"})
TOP_LEVEL_DROPPED = ("killswitch", "scan_health", "as_of")
#: Dotted paths that still move with the run date. Empty unless Step 6 finds one.
WALL_CLOCK_PATHS: tuple[str, ...] = ()


@dataclass
class GoldenBook:
    client: object
    tmp_path: pathlib.Path
    network_calls: list[str] = field(default_factory=list)


def _bars(symbol: str) -> pd.DataFrame:
    phase = BAR_SYMBOLS.index(symbol)
    index = pd.bdate_range(end="2026-10-28", periods=300, name="Date")
    close = [round(100 + 5 * math.sin(i / 7 + phase) + 0.02 * i * (phase + 1), 4)
             for i in range(len(index))]
    return pd.DataFrame({"Open": [c - 0.5 for c in close], "High": [c + 1 for c in close],
                         "Low": [c - 1 for c in close], "Close": close,
                         "Volume": [1_000_000 + i for i in range(len(index))]}, index=index)


def _open_trades() -> list[dict]:
    rows = [("AAPL", 100.0, 95.0, 10), ("MSFT", 200.0, 190.0, 5), ("SAP.DE", 150.0, 140.0, 4)]
    return [{"id": f"o{i:015d}", "ticker": t, "status": "open", "direction": "bullish",
             "strategy": "VWAP", "horizon_key": "1m", "ledger": "main",
             "entry": e, "stop_loss": s, "take_profit": e * 1.2, "shares": n,
             "opened_at": "2026-08-03T14:00:00+00:00"} for i, (t, e, s, n) in enumerate(rows, 1)]


def _closed(trade_id: str, ticker: str, opened: datetime, win: bool, ledger: str) -> dict:
    exit_price = 110.0 if win else 92.0
    return {"id": trade_id, "ticker": ticker, "status": "win" if win else "loss",
            "direction": "bullish", "strategy": "VWAP", "horizon_key": "1m", "ledger": ledger,
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0, "exit_price": exit_price,
            "shares": 10, "realized_pnl_amount": round((exit_price - 100.0) * 10, 2),
            "opened_at": opened.isoformat(), "closed_at": (opened + timedelta(days=3)).isoformat()}


def _closed_trades() -> list[dict]:
    start = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
    tickers = ("AAPL", "MSFT", "SAP.DE")
    main = [_closed(f"c{i:015d}", tickers[i % 3], start + timedelta(days=15 * i), i % 2 == 0, "main")
            for i in range(12)]                       # i = 10, 11 close in June (GOLDEN_MONTH)
    weak = [_closed(f"w{i:015d}", "AAPL", datetime(2026, 3, 2 + 7 * i, 14, tzinfo=timezone.utc),
                    i == 0, "weak") for i in range(2)]
    return main + weak


def _read_bars(symbol):
    from swingbot.core.marketdata import daily_delta
    return daily_delta.read_daily(str(symbol).upper(), basis=daily_delta.BASIS_YF)
```

Then, in the same file:
- `_write_bars()` writes `_bars(s)` to `daily_delta.cache_file(s, daily_delta.BASIS_YF)` for each `BAR_SYMBOLS` entry (`frame.to_csv(path)`; `cache_path` creates the directory), then calls `data_store.clear_normalized_frame_cache()`.
- `_poison(monkeypatch, calls)` sets every `NETWORK` pair to a function that appends `f"{module}.{name}"` to `calls` and raises `AssertionError`.
- `_drop_volatile(value)` recursively drops `VOLATILE_KEYS` from dicts, walking lists. `_drop_path(body, dotted)` deletes one dotted path when it is present.
- `normalise(body)` returns a deep copy (`json.loads(json.dumps(..., sort_keys=True))`) with: the top-level `TOP_LEVEL_DROPPED` removed, `availability.killswitch` removed when `availability` is a dict, `_drop_volatile` applied, and each `WALL_CLOCK_PATHS` path dropped.
- `golden_payload(name)` raises `KeyError` for a name outside `GOLDEN_NAMES`. Otherwise it returns `json.loads((GOLDEN_DIR / f"{name}.json").read_text("utf-8"))`.
- `assert_matches_golden(name, body)`: `got = normalise(body)`, `want = golden_payload(name)`. It asserts `set(want) <= set(got)` (the message names the missing keys), then `{k: got[k] for k in want} == want`.

The fixture:

```python
@pytest.fixture
def golden_book(client, tmp_path, monkeypatch):
    from swingbot.core.analytics import snapshots
    from swingbot.core.backtesting import registry
    from swingbot.core.marketdata import data, fx, universe

    monkeypatch.chdir(tmp_path)                 # market_data/daily/<T>.csv lands under tmp
    for attr, value in (("ADMIN_REFRESHER", "off"), ("MARKETDATA_LAYER", "off"),
                        ("MARKET_REGIME_TICKER", "SPY"), ("CURRENCY_SYMBOL", "$")):
        monkeypatch.setattr(config, attr, value)
    monkeypatch.setattr(snapshots, "DEFAULT_PATH", str(tmp_path / "analytics_snapshot.json"))
    monkeypatch.setattr(registry, "load_registry", lambda path=None: [])
    monkeypatch.setattr(universe, "sector_map", lambda name=None: dict(SECTORS))
    monkeypatch.setattr(fx, "quote_currency_code",
                        lambda ticker, **_kw: QUOTE_CODES.get(str(ticker).upper(), "USD"))
    monkeypatch.setattr(fx, "fx_rate", lambda src, dst, on=None, **_kw:
                        1.0 if src == dst else FX_RATES.get((src, dst)))
    monkeypatch.setattr(data, "get_daily_data", lambda ticker, period="2y", **_kw: _read_bars(ticker))
    monkeypatch.setattr(data, "get_daily_data_batch", lambda tickers, period="2y", **_kw: {
        str(t).upper(): f for t in tickers if (f := _read_bars(t)) is not None})
    book = GoldenBook(client=client, tmp_path=tmp_path)
    _poison(monkeypatch, book.network_calls)
    _write_bars()
    seed_store("account", {"balance": 10000.0, "base_balance": 10000.0, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})
    seed_store("trades", _open_trades() + _closed_trades())
    risk = importlib.import_module("swingbot.admin.api_v1.risk")
    risk._invalidate_cache()
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    yield book
    risk._invalidate_cache()
```

`snapshots.DEFAULT_PATH` is bound at import time from `config.DATA_DIR`, so without the patch the fresh rebuild would write the real `data/analytics_snapshot.json`.

- [ ] **Step 3: Write `tests/admin_snapshots/record_golden.py`**

```python
"""Capture the six golden payloads from a golden_book client; write them once."""
from __future__ import annotations

import json
import pathlib

from tests.admin_snapshots.golden_book import GOLDEN_DIR, GOLDEN_MONTH, GOLDEN_NAMES, normalise

#: Order matters: the analytics snapshot file must exist before the sparkline reads it.
CAPTURE_PATHS = {
    "risk": "/api/v1/risk",
    "performance_main": "/api/v1/analytics/performance?ledger=main",
    "equity_curve_main": "/api/v1/analytics/equity-curve?ledger=main",
    "calendar_pnl": f"/api/v1/calendar/pnl?month={GOLDEN_MONTH}",
    "analytics_snapshot": "/api/v1/analytics/snapshot?fresh=1",
}


def capture(client) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, path in CAPTURE_PATHS.items():
        resp = client.get(path)
        assert resp.status_code == 200, (name, resp.get_data(as_text=True))
        out[name] = resp.get_json()
    from swingbot.admin.api_v1 import dashboard
    out["sparkline"] = dashboard._equity_30d()
    return out


def write(payloads: dict[str, dict], directory: pathlib.Path = GOLDEN_DIR) -> list[pathlib.Path]:
    directory.mkdir(exist_ok=True)
    written = []
    for name in GOLDEN_NAMES:
        path = directory / f"{name}.json"
        if path.exists():
            raise FileExistsError(f"{path} is frozen (v204 V204-1); fix the code, not the golden file")
        path.write_text(json.dumps(normalise(payloads[name]), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        written.append(path)
    return written
```

- [ ] **Step 4: Write `tests/admin_snapshots/test_golden_today.py` and the suite entry**

```python
"""v204 V204-1: today's request code reproduces the frozen golden payloads."""
import os

import pytest

from swingbot.admin.api_v1 import risk
from tests.admin_snapshots import record_golden
from tests.admin_snapshots.golden_book import (  # noqa: F401  (fixtures)
    GOLDEN_MONTH, GOLDEN_NAMES, _clear_login_limiter, admin_app, assert_matches_golden, client,
    golden_book, golden_payload, normalise)


@pytest.mark.skipif(os.environ.get("V204_RECORD_GOLDEN") != "1", reason="recorded once, in V204-1")
def test_record_golden(golden_book):
    payloads = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    record_golden.write(payloads)


def test_capture_is_deterministic(golden_book):
    first = record_golden.capture(golden_book.client)
    risk._invalidate_cache()
    second = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    assert {n: normalise(b) for n, b in first.items()} == {n: normalise(b) for n, b in second.items()}


def test_today_matches_golden(golden_book):
    payloads = record_golden.capture(golden_book.client)
    assert golden_book.network_calls == []
    for name in GOLDEN_NAMES:
        assert_matches_golden(name, payloads[name])


def test_golden_book_carries_real_figures():
    body = golden_payload("risk")
    assert len(body["positions"]) == 3 and body["unmapped_count"] == 1
    assert body["heat"]["open_pct"] is not None
    assert body["metrics"]["benchmark_symbol"] == "SPY"
    assert body["correlation"]["values"], "correlation came back empty: bars did not reach the risk code"
    assert golden_payload("performance_main")["totals"]["closed"] == 12
    assert golden_payload("equity_curve_main")["points_n"] == 12
    assert golden_payload("calendar_pnl")["month"] == GOLDEN_MONTH
    assert golden_payload("analytics_snapshot")["equity_curve"]["points"]
    assert golden_payload("sparkline")["points"]
    assert all("checked_at" not in json.dumps(golden_payload(n)) for n in GOLDEN_NAMES)


def test_golden_files_are_never_overwritten(tmp_path):
    (tmp_path / "risk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="frozen"):
        record_golden.write({name: {} for name in GOLDEN_NAMES}, directory=tmp_path)
```

(Add `import json` beside `import os`.)

Append to `tests/suites.toml`:

```toml
[suites.admin-snapshots]
description = "v204 admin snapshot pages: golden parity, read-only bars, risk payload, builders, worker, routes"
paths = ["tests/admin_snapshots/"]
```

- [ ] **Step 5: Run before recording, then record once**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_golden_today.py`
Expected: FAIL. `test_today_matches_golden` and `test_golden_book_carries_real_figures` fail with `FileNotFoundError` (no golden files yet). `test_capture_is_deterministic` and `test_golden_files_are_never_overwritten` PASS. If `test_capture_is_deterministic` fails, or `network_calls` is non-empty, fix `golden_book.py` (see "Behaviour fixed here") before recording.
Run: `V204_RECORD_GOLDEN=1 python -m pytest <wt>/tests/admin_snapshots/test_golden_today.py::test_record_golden -q`
Expected: `1 passed`, and six files under `tests/admin_snapshots/golden/`.

- [ ] **Step 6: Check the recording and its date independence**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_golden_today.py`
Expected: PASS, `0 failed`, 1 skipped (`test_record_golden`).
Then read `risk.json` and `performance_main.json` for any value derived from today's date: a count that differs from the 12 + 2 seeded closed trades, or a date after 2026-10-28. Add each such dotted path to `WALL_CLOCK_PATHS`, with a one-line comment naming the function that reads the clock. Then delete the six files and record again (Step 5's second command). Deleting is allowed only inside this task, before its commit.
Run: `python <wt>/scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: PASS (the new directory belongs to exactly one suite).

- [ ] **Step 7: Commit**

```bash
git -C <wt> add tests/admin_snapshots/__init__.py tests/admin_snapshots/golden_book.py tests/admin_snapshots/record_golden.py tests/admin_snapshots/golden/risk.json tests/admin_snapshots/golden/performance_main.json tests/admin_snapshots/golden/equity_curve_main.json tests/admin_snapshots/golden/calendar_pnl.json tests/admin_snapshots/golden/analytics_snapshot.json tests/admin_snapshots/golden/sparkline.json tests/admin_snapshots/test_golden_today.py tests/suites.toml
git -C <wt> commit -m "test(v204): frozen golden payloads from today's request code; admin-snapshots suite"
```

### Task V204-2: Measure first: Analytics/Calendar under persisted FX alone

**Model:** sonnet — a timing harness plus one measured run against the replica; the verdict rule is fixed in the ledger, so nothing here is a design call.

**Files:**
- Create: `scripts/dev/time_admin_routes.py`
- Create: `tests/admin_snapshots/test_time_admin_routes.py`
- Create: `docs/superpowers/results/2026-10-29-v204-measure-first.md` (written by the script in Step 6)

**Interfaces:**
- Consumes: v201's `admin_refresh.refresher_on()` (true when `ADMIN_REFRESHER="on"` and `MARKETDATA_LAYER="on"`) and its never-fetch FX reads (`fx.quote_currency_code(t, fetch=False)`); the suite `admin-snapshots` (V204-1).
- Produces: the results doc, which carries exactly one verdict line per route, in this form (V204-8 reads them by eye to set `SNAPSHOT_ROUTES`):
  `` - `analytics.performance`: **request** (warm max 0.212 s, cold max 0.640 s) ``
  The route ids are `analytics.performance`, `analytics.equity_curve` and `calendar.pnl`; the verdict is `request` or `snapshot`.

**Behaviour fixed here (ledger rule):**
- `request` only when warm max ≤ 0.5 s **and** cold max ≤ 1.0 s, over 5 runs each, against the replicated DB with `ADMIN_REFRESHER=on` and the network poisoned. Anything else, including no samples, is `snapshot`.
- Warm: one discarded warm-up request, then 5 timed requests in the same process. Cold: 5 fresh subprocesses, each building the app, logging in and timing its **first** request to the route. App import and login are excluded from the timing.
- A poisoned network function called during any run is a defect, not a timing. The script prints the function names and exits 2 without writing the doc. Report that to the controller.
- Login reads `ADMIN_USERNAME`/`ADMIN_PASSWORD` from the environment `swingbot.config` loaded from `.env`. They are never printed, and a failed login exits 3 with the message `login failed` only.

- [ ] **Step 1: Write the failing tests** `tests/admin_snapshots/test_time_admin_routes.py`

```python
"""v204 V204-2: the measure-first harness (no database, no app)."""
import json
import re
import subprocess

import pytest

from scripts.dev import time_admin_routes as tar
from swingbot.core.marketdata import data

VERDICT_LINE = re.compile(
    r"^- `(analytics\.performance|analytics\.equity_curve|calendar\.pnl)`: \*\*(request|snapshot)\*\* "
    r"\(warm max \d+\.\d{3} s, cold max \d+\.\d{3} s\)$", re.M)


@pytest.mark.parametrize("warm,cold,expected", [
    ([0.5] * 5, [1.0] * 5, "request"),
    ([0.1, 0.2, 0.51, 0.1, 0.1], [0.2] * 5, "snapshot"),
    ([0.1] * 5, [0.3, 1.01, 0.2, 0.2, 0.2], "snapshot"),
    ([], [0.1] * 5, "snapshot"),
    ([0.1] * 5, [], "snapshot"),
])
def test_verdict_rule(warm, cold, expected):
    assert tar.verdict(warm, cold) == expected


class FakeClient:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def get(self, path):
        self.calls.append(path)
        return type("Resp", (), {"status_code": self.status})()


def test_measure_warm_discards_one_warmup_and_times_each_run():
    client = FakeClient()
    times = tar.measure_warm(client, "/api/v1/calendar/pnl", runs=5)
    assert len(times) == 5 and all(t >= 0 for t in times)
    assert client.calls == ["/api/v1/calendar/pnl"] * 6


def test_timed_get_refuses_a_non_200():
    with pytest.raises(RuntimeError, match="503"):
        tar.timed_get(FakeClient(status=503), "/api/v1/calendar/pnl")


def test_poisoned_network_records_raises_and_restores():
    original = data.get_quote_batch
    with tar.poisoned_network() as calls:
        with pytest.raises(AssertionError):
            data.get_quote_batch(["AAPL"])
        assert calls == ["swingbot.core.marketdata.data.get_quote_batch"]
    assert data.get_quote_batch is original


def test_cold_run_with_a_network_call_is_a_defect(monkeypatch):
    out = json.dumps({"seconds": 0.1, "network": ["swingbot.core.marketdata.fx._refreshed_frame"]})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    with pytest.raises(tar.NetworkDefect, match="_refreshed_frame"):
        tar.measure_cold("calendar.pnl", runs=1)


def test_cold_run_collects_one_time_per_subprocess(monkeypatch):
    out = json.dumps({"seconds": 0.25, "network": []})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert tar.measure_cold("calendar.pnl", runs=3) == [0.25, 0.25, 0.25]


def test_render_has_exactly_one_verdict_line_per_route():
    results = {route: {"warm": [0.2] * 5, "cold": [0.7] * 5} for route in tar.ROUTES}
    results["calendar.pnl"]["cold"] = [1.4] * 5
    text = tar.render(results)
    found = dict(VERDICT_LINE.findall(text))
    assert found == {"analytics.performance": "request", "analytics.equity_curve": "request",
                     "calendar.pnl": "snapshot"}
    assert "| route |" in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_time_admin_routes.py`
Expected: FAIL with `ImportError: cannot import name 'time_admin_routes'`.

- [ ] **Step 3: Implement `scripts/dev/time_admin_routes.py`**

Module docstring: v204 measure-first (spec § Request path: "measures whether persisted FX alone brings them under 2 s"), the ledger's rule, and how it runs (`DATABASE_URL` at the `swing-db` replica, never production). Constants and signatures:

```python
ROUTES = {
    "analytics.performance": "/api/v1/analytics/performance",
    "analytics.equity_curve": "/api/v1/analytics/equity-curve",
    "calendar.pnl": "/api/v1/calendar/pnl",
}
RUNS = 5
WARM_MAX_S = 0.5
COLD_MAX_S = 1.0
NETWORK: tuple[tuple[str, str], ...] = (
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "get_daily_data"),
    ("swingbot.core.marketdata.data", "get_daily_data_batch"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
)


class NetworkDefect(RuntimeError): ...

def verdict(warm: Sequence[float], cold: Sequence[float]) -> str
def poisoned_network() -> ContextManager[list[str]]      # contextlib.contextmanager; setattr, then restore
def timed_get(client, path: str) -> float                # perf_counter around client.get; RuntimeError(f"{path} -> {status}") unless 200
def measure_warm(client, path: str, runs: int = RUNS) -> list[float]
def measure_cold(route: str, runs: int = RUNS) -> list[float]
def render(results: Mapping[str, Mapping[str, Sequence[float]]]) -> str
def main(argv: Sequence[str] | None = None) -> int
```

- `verdict`: `"request"` iff both lists are non-empty and `max(warm) <= WARM_MAX_S and max(cold) <= COLD_MAX_S`.
- `measure_cold` runs `subprocess.run([sys.executable, __file__, "--cold-one", route], capture_output=True, text=True, check=True)` `runs` times and parses the last stdout line as JSON. A non-empty `network` raises `NetworkDefect(", ".join(names))`.
- `_client()` (private) sets `config.ADMIN_REFRESHER = "on"` and `config.MARKETDATA_LAYER = "on"`, imports `swingbot.admin.app`, makes `app.test_client()` and posts `/api/v1/session` with the env credentials. A non-200 prints `login failed` and `raise SystemExit(3)`.
- `--cold-one ROUTE` mode: `_client()`, then `with poisoned_network() as calls:` one `timed_get`, printing `json.dumps({"seconds": t, "network": calls})`. A forbidden call raises inside the handler, so `timed_get` may raise, or the handler may swallow it. Either way `calls` carries the name, and the mode always prints its JSON line (catch the exception, report `seconds: null`).
- Default mode: `_client()` once, then per route `with poisoned_network() as calls:` `measure_warm`, then `measure_cold`. If any `calls`, print the names to stderr and return 2. Otherwise print `render(...)`, and with `--out PATH` write the results document (Step 6 shape) and return 0.
- `render` prints a Markdown table `| route | warm runs (s) | warm max | cold runs (s) | cold max | verdict |`, then one verdict line per route in `ROUTES` order, formatted exactly as in Interfaces (3 decimals).

The `__main__` guard is `raise SystemExit(main())`. Keep every function below complexity 15 (`main` delegates the two modes to `_cold_one(route)` and `_measure_all(out)`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_time_admin_routes.py`
Expected: PASS, `0 failed`.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: no new violation.

- [ ] **Step 5: Prepare the replica**

Run `/replicate-prod-db` (the shared `swing-db` container). If its reported `alembic` revision is behind `python -m alembic -c <wt>/alembic.ini heads` (v201's `v201_001` is not on production yet), migrate **the replica only**, as the skill describes. Then point `DATABASE_URL` at the replica, as the skill reports it. Expected: the replica is at head and `quote_currencies` exists. With an empty `quote_currencies`, every non-USD row is FX-missing, not fetched; that is the state the request path meets on the first day after deploy.

- [ ] **Step 6: Measure and write the results document**

Run: `python <wt>/scripts/dev/time_admin_routes.py --out <wt>/docs/superpowers/results/2026-10-29-v204-measure-first.md`
Expected: exit 0, and a table plus three verdict lines on stdout. Exit 2 is a defect: report the printed function names to the controller and stop. Do not commit a document then.

The document the script writes has this shape (the script fills in the bracketed parts):

```markdown
<level-1 heading: "v204 measure-first: Analytics and Calendar under persisted FX alone">

**Plan:** v204 task V204-2. **Rule:** `request` when warm max ≤ 0.5 s and cold max ≤ 1.0 s over 5 runs each; else `snapshot`.
**Run:** <UTC timestamp>, commit <git rev-parse --short HEAD>, replica restored <date from /replicate-prod-db>, alembic <head>, `ADMIN_REFRESHER=on`, network poisoned (no call recorded).
**Book:** <n trades> trades (<n closed> closed), <n quote_currencies rows> persisted quote currencies.

<render() output>
```

Add the git commit and book counts through `subprocess.run(["git", "rev-parse", "--short", "HEAD"])` and two `SELECT count(*)` reads (`trades`, `quote_currencies`) through `swingbot.core.db.engine`. Add the replica restore date by hand, from the skill's report, before committing.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add scripts/dev/time_admin_routes.py tests/admin_snapshots/test_time_admin_routes.py docs/superpowers/results/2026-10-29-v204-measure-first.md
git -C <wt> commit -m "test(v204): measure-first timing of Analytics/Calendar under persisted FX; verdicts recorded"
```

# Phase 2: Contract and storage

### Task V204-3: Snapshot config fields, `stale_after_s("snapshot")`, snapshot keys and marks

**Model:** sonnet — six config fields and small pure helpers on a contract the index fixes exactly; the tests pin every value.

**Files:**
- Modify: `swingbot/config.py` (6 `Field`s directly after v201's `ADMIN_STALE_PRICE_EXTENDED_S` field)
- Modify: `.env.example` (6 keys directly after v201's `ADMIN_STALE_PRICE_EXTENDED_S=` line). This file is not in the ledger row, but `tests/infra/test_env_example_sync.py` fails without it.
- Modify (created by v201 V201-1): `swingbot/core/marketdata/shared/admin_refresh.py`
- Modify (created by v201 V201-1): `tests/refresher/test_admin_refresh_contract.py` (one line; see Step 3). Also not in the ledger row: v201 pinned `stale_after_s("snapshot", ...)` as an error, and this task makes it valid.
- Test: `tests/test_config_v204_keys.py`, `tests/admin_snapshots/test_snapshot_contract.py`

**Interfaces:**
- Consumes: v201's `admin_refresh` (`_STALE_ATTR`, `stale_after_s`, `cadence_s`), `session.SESSION_*`, `session.now_et`.
- Produces: the index's "Config fields" and "Contract module additions" sections, exactly: `stale_after_s("snapshot", state)`, `snapshot_cadence_s(state) -> float`, `snapshot_mark_timeout_s() -> float`, `SNAPSHOT_RISK = "risk"`, `SNAPSHOT_ANALYTICS = "analytics.snapshot"`, `performance_key(ledger) -> str`, `equity_curve_key(ledger) -> str`, `calendar_key(month) -> str`, `is_snapshot_key(key) -> bool`, `snapshot_mark_key(key) -> str`, `snapshot_key_of(mark_key) -> str | None` and `calendar_months(now=None) -> tuple[str, str]`.
- `admin_refresh` keeps importing nothing from `swingbot.core.analytics`. The ledger tuple is restated as `_LEDGERS = ("main", "weak", "both")`, and a test pins it equal to `scope.LEDGERS`.

- [ ] **Step 1: Write the failing config test** `tests/test_config_v204_keys.py`

```python
"""v204: the snapshot worker's cadence, budget and staleness knobs (index "Config fields")."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (default, min, max). Dict order is the FIELDS order.
V204_FIELDS = {
    "ADMIN_SNAPSHOT_REGULAR_S": ("300", 60, 3600),
    "ADMIN_SNAPSHOT_EXTENDED_S": ("900", 60, 7200),
    "ADMIN_SNAPSHOT_CLOSED_S": ("3600", 300, 21600),
    "ADMIN_SNAPSHOT_BUDGET_S": ("90", 10, 600),
    "ADMIN_STALE_SNAPSHOT_REGULAR_S": ("600", 60, 3600),
    "ADMIN_STALE_SNAPSHOT_EXTENDED_S": ("1800", 300, 7200),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_field_is_a_hot_reloadable_data_sources_number(attr):
    field = _field(attr)
    default, low, high = V204_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", "number", default)
    assert (field.min, field.max, field.step) == (low, high, 1)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert field.help.startswith("v204. ")


def test_fields_sit_together_after_the_v201_price_knobs():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("ADMIN_STALE_PRICE_EXTENDED_S") + 1
    assert attrs[start:start + len(V204_FIELDS)] == list(V204_FIELDS)


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    assert config._cast(_field(attr), _field(attr).default) == int(V204_FIELDS[attr][0])


@pytest.mark.parametrize("attr", sorted(V204_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V204_FIELDS[attr][0]}\n" in text
```

- [ ] **Step 2: Write the failing contract test** `tests/admin_snapshots/test_snapshot_contract.py`

```python
"""v204: snapshot staleness, cadence, budget-derived mark timeout and key shapes."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.analytics import scope
from swingbot.core.marketdata.shared import admin_refresh as ar

UTC = timezone.utc


def test_snapshot_staleness_reads_config_at_call_time(monkeypatch):
    assert ar.stale_after_s("snapshot", "regular") == 600.0
    assert ar.stale_after_s("snapshot", "extended") == 1800.0
    assert ar.stale_after_s("snapshot", "closed") is None      # closed rule lives in the door and the SPA
    monkeypatch.setattr(config, "ADMIN_STALE_SNAPSHOT_REGULAR_S", 61)
    assert ar.stale_after_s("snapshot", "regular") == 61.0
    assert ar.stale_after_s("price", "regular") == float(config.ADMIN_STALE_PRICE_REGULAR_S)
    with pytest.raises(ValueError):
        ar.stale_after_s("bogus", "regular")


def test_snapshot_cadence_per_session(monkeypatch):
    assert [ar.snapshot_cadence_s(s) for s in ("regular", "extended", "closed")] == [300.0, 900.0, 3600.0]
    monkeypatch.setattr(config, "ADMIN_SNAPSHOT_EXTENDED_S", 120)
    assert ar.snapshot_cadence_s("extended") == 120.0
    with pytest.raises(ValueError):
        ar.snapshot_cadence_s("lunch")


def test_mark_timeout_is_budget_plus_thirty(monkeypatch):
    assert ar.snapshot_mark_timeout_s() == 120.0
    monkeypatch.setattr(config, "ADMIN_SNAPSHOT_BUDGET_S", 45)
    assert ar.snapshot_mark_timeout_s() == 75.0


def test_fixed_keys_and_ledgers_match_scope():
    assert (ar.SNAPSHOT_RISK, ar.SNAPSHOT_ANALYTICS) == ("risk", "analytics.snapshot")
    assert ar._LEDGERS == scope.LEDGERS


@pytest.mark.parametrize("ledger", ["main", "weak", "both"])
def test_ledger_keys(ledger):
    assert ar.performance_key(ledger) == f"analytics.performance:{ledger}"
    assert ar.equity_curve_key(ledger) == f"analytics.equity_curve:{ledger}"


@pytest.mark.parametrize("bad", ["", "Main", "all", "main "])
def test_ledger_keys_reject_unknown_ledgers(bad):
    with pytest.raises(ValueError):
        ar.performance_key(bad)
    with pytest.raises(ValueError):
        ar.equity_curve_key(bad)


def test_calendar_key_takes_a_real_month_only():
    assert ar.calendar_key("2026-10") == "calendar.pnl:2026-10"
    for bad in ("2026-13", "2026-1", "2026-00", "oct", ""):
        with pytest.raises(ValueError):
            ar.calendar_key(bad)


@pytest.mark.parametrize("key", ["risk", "analytics.snapshot", "analytics.performance:main",
                                 "analytics.equity_curve:both", "calendar.pnl:2026-09"])
def test_is_snapshot_key_accepts_the_five_shapes(key):
    assert ar.is_snapshot_key(key) is True


@pytest.mark.parametrize("key", ["", "RISK", "risk:main", "quote:AAPL", "snapshot:risk",
                                 "analytics.performance", "analytics.performance:all",
                                 "calendar.pnl:2026-13", "calendar.pnl:2026-9", None, 7])
def test_is_snapshot_key_rejects_everything_else(key):
    assert ar.is_snapshot_key(key) is False


def test_mark_keys_round_trip():
    assert ar.snapshot_mark_key("calendar.pnl:2026-10") == "snapshot:calendar.pnl:2026-10"
    assert ar.snapshot_key_of("snapshot:calendar.pnl:2026-10") == "calendar.pnl:2026-10"
    assert ar.snapshot_key_of("quote:AAPL") is None
    assert ar.snapshot_key_of("snapshot:bogus") is None
    with pytest.raises(ValueError):
        ar.snapshot_mark_key("quote:AAPL")


@pytest.mark.parametrize("now,months", [
    (datetime(2026, 10, 30, 15, 0, tzinfo=UTC), ("2026-10", "2026-09")),
    (datetime(2026, 1, 10, 15, 0, tzinfo=UTC), ("2026-01", "2025-12")),
    (datetime(2026, 11, 1, 3, 0, tzinfo=UTC), ("2026-10", "2026-09")),   # 23:00 ET on Oct 31
])
def test_calendar_months_use_the_new_york_date(now, months):
    assert ar.calendar_months(now) == months


def test_calendar_months_default_to_now():
    current, previous = ar.calendar_months()
    assert ar.is_snapshot_key(ar.calendar_key(current)) and ar.is_snapshot_key(ar.calendar_key(previous))
```

- [ ] **Step 3: Adjust v201's contract test, then run all three files to verify they fail**

In `tests/refresher/test_admin_refresh_contract.py`, `test_cadence_and_staleness_read_config_at_call_time` ends with `ar.stale_after_s("snapshot", "regular")` under `pytest.raises(ValueError)` and the comment `# snapshot staleness is v204's`. Change that call to `ar.stale_after_s("bogus", "regular")` and drop the comment.
Run: `python <wt>/scripts/dev/testrun.py file tests/test_config_v204_keys.py`, then the same for `tests/admin_snapshots/test_snapshot_contract.py`
Expected: FAIL (`StopIteration` for the fields; `AttributeError: ... 'snapshot_cadence_s'`, and `ValueError` from `stale_after_s("snapshot", ...)`).

- [ ] **Step 4: Implement the config fields**

After v201's `ADMIN_STALE_PRICE_EXTENDED_S` `Field(...)` in `swingbot/config.py`, add the six `Field`s in `V204_FIELDS` order. Each is `"Data Sources"`, `type="number"`, `step=1`, `key == attr`, with min/max from the table and `help` starting `"v204. "`. Labels, in order: "Snapshot cadence: regular hours (s)", "Snapshot cadence: pre/after hours (s)", "Snapshot cadence: market closed (s)", "Snapshot build budget (s)", "Snapshot stale after: regular hours (s)" and "Snapshot stale after: pre/after hours (s)". The help text says what each knob does and that the mark timeout is the budget + 30 s. The two stale fields' help says that while the market is closed, a snapshot is stale when it was built before the last regular close, or when its inputs are stale.

In `.env.example`, directly after `ADMIN_STALE_PRICE_EXTENDED_S=900`, add a comment line `# v204: admin snapshot worker (runs inside the refresher service).` and the six `KEY=default` lines in the same order.

- [ ] **Step 5: Implement the contract additions in `admin_refresh.py`**

Add to `_STALE_ATTR`:

```python
    ("snapshot", session.SESSION_REGULAR): "ADMIN_STALE_SNAPSHOT_REGULAR_S",
    ("snapshot", session.SESSION_EXTENDED): "ADMIN_STALE_SNAPSHOT_EXTENDED_S",
```

The new names, appended after `quote_mark_key`:

```python
SNAPSHOT_RISK = "risk"
SNAPSHOT_ANALYTICS = "analytics.snapshot"
#: scope.LEDGERS, restated so marketdata imports nothing from analytics (pinned by test).
_LEDGERS = ("main", "weak", "both")
_SNAPSHOT_CADENCE_ATTR = {
    session.SESSION_REGULAR: "ADMIN_SNAPSHOT_REGULAR_S",
    session.SESSION_EXTENDED: "ADMIN_SNAPSHOT_EXTENDED_S",
    session.SESSION_CLOSED: "ADMIN_SNAPSHOT_CLOSED_S",
}
_MONTH = r"\d{4}-(?:0[1-9]|1[0-2])"
_LEDGER = "|".join(_LEDGERS)
_SNAPSHOT_KEY = re.compile(
    rf"(?:risk|analytics\.snapshot|analytics\.(?:performance|equity_curve):(?:{_LEDGER})"
    rf"|calendar\.pnl:{_MONTH})")
_MARK_PREFIX = "snapshot:"


def snapshot_cadence_s(state: str) -> float: ...       # as cadence_s, over _SNAPSHOT_CADENCE_ATTR
def snapshot_mark_timeout_s() -> float: ...            # float(config.ADMIN_SNAPSHOT_BUDGET_S) + 30.0
def performance_key(ledger: str) -> str: ...           # ValueError unless ledger in _LEDGERS
def equity_curve_key(ledger: str) -> str: ...
def calendar_key(month: str) -> str: ...               # ValueError unless re.fullmatch(_MONTH, month)
def is_snapshot_key(key) -> bool: ...                  # isinstance str and _SNAPSHOT_KEY.fullmatch
def snapshot_mark_key(key: str) -> str: ...            # ValueError unless is_snapshot_key
def snapshot_key_of(mark_key: str) -> str | None: ...  # strip _MARK_PREFIX; None unless the rest is a snapshot key
def calendar_months(now: datetime | None = None) -> tuple[str, str]: ...
```

`calendar_months` takes `d = session.now_et(now).date()` and returns `(f"{d:%Y-%m}", f"{d.replace(day=1) - timedelta(days=1):%Y-%m}")`. Add `import re` and `timedelta`. The module docstring gains one sentence: v204 adds the snapshot staleness kind, cadence and key shapes.

- [ ] **Step 6: Run the changed files and the guards they touch**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for each of `tests/test_config_v204_keys.py`, `tests/admin_snapshots/test_snapshot_contract.py`, `tests/refresher/test_admin_refresh_contract.py`, `tests/test_config_v201_keys.py`, `tests/infra/test_env_example_sync.py`
Expected: all PASS (`0 failed`). Then run `python <wt>/scripts/dev/complexity_gate.py`. Expected: clean.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/config.py .env.example swingbot/core/marketdata/shared/admin_refresh.py tests/refresher/test_admin_refresh_contract.py tests/test_config_v204_keys.py tests/admin_snapshots/test_snapshot_contract.py
git -C <wt> commit -m "feat(v204): snapshot cadence/budget/staleness knobs; snapshot keys and marks in admin_refresh"
```

### Task V204-4: Alembic `v204_001`: `admin_snapshots` table; compare-and-set repository

**Model:** opus — a production schema migration plus the write-ordering rule (newer `computed_at` wins) that keeps an abandoned build from overwriting a newer snapshot.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v204_001_admin_snapshots.py`
- Modify: `swingbot/core/db/schema.py` (one `register(...)` table after v201's `refresher_heartbeat`; one `PROMOTION_REASONS` entry after v201's entries)
- Create: `swingbot/core/db/repositories/admin_snapshots.py`
- Test: `tests/db/test_v204_admin_snapshots.py`
- Modify (created by v201 V201-2): `tests/db/test_v201_tables.py` (one assertion; see Step 6). Not in the ledger row: its exact-head assertion stops holding once `v204_001` exists.

**Interfaces:**
- Consumes: nothing from earlier v204 tasks. v201's revision `v201_001` is the expected head.
- Produces: the index's "Table" and "Repository" sections, exactly. Table `admin_snapshots`, importable as `swingbot.core.db.schema.admin_snapshots`. `AdminSnapshotRepository` with `put(key, doc, inputs, *, computed_at, stale_inputs, conn=None) -> bool`, `read(key, *, conn=None) -> dict | None`, `read_many(keys, *, conn=None) -> dict[str, dict]`, `changed_since(since, *, conn=None) -> list[dict]` and `prune(prefix, keep, *, conn=None) -> int`. Accessor `admin_snapshot_repo() -> AdminSnapshotRepository`. Each row dict is `{key, doc, inputs, computed_at, stale_inputs, updated_at}`, with tz-aware UTC times. `changed_since` rows are `{key, computed_at, stale_inputs, updated_at}`, ordered by `updated_at`.
- `put` raises `ValueError` for a naive `computed_at`, or for a `doc`/`inputs` holding `NaN`/`Infinity` (`json.dumps(..., allow_nan=False)`), so "never NaN" fails loudly at the write. The repository validates no key shape: `core/db` imports nothing from `core/marketdata`, and the worker and door validate keys with `is_snapshot_key`.

- [ ] **Step 1: Write the failing test** `tests/db/test_v204_admin_snapshots.py`

```python
"""v204: revision v204_001 -- admin_snapshots, one row per key, newer computed_at wins."""
import math
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import admin_snapshots as snaps

REPO = pathlib.Path(__file__).resolve().parents[2]
UTC = timezone.utc
T0 = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
PROMOTED = ("key", "computed_at", "stale_inputs", "inputs")


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables["admin_snapshots"]
    assert schema.promoted_for("admin_snapshots") == PROMOTED
    assert set(schema.PROMOTION_REASONS["admin_snapshots"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert all(table.c[c].nullable is False for c in PROMOTED)
    assert "admin_snapshots" not in events.TABLE_CHANNELS


def test_column_types_and_index():
    t = schema.admin_snapshots
    assert t.c.key.primary_key and isinstance(t.c.key.type, sa.Text)
    assert t.c.computed_at.type.timezone is True
    assert isinstance(t.c.stale_inputs.type, sa.Boolean)
    assert "false" in str(t.c.stale_inputs.server_default.arg).lower()
    assert isinstance(t.c.inputs.type, postgresql.JSONB)
    assert {i.name: [c.name for c in i.columns] for i in t.indexes} == {
        "admin_snapshots_updated_idx": ["updated_at"]}


def test_v204_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v204_001")
    assert scripts.get_revision(revision.down_revision) is not None
    assert scripts.get_heads() == ["v204_001"]


def test_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "admin_snapshots" in sa.inspect(connection).get_table_names()
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v204_001").down_revision)
        remaining = set(sa.inspect(connection).get_table_names())
        assert "admin_snapshots" not in remaining and "market_refresh_marks" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "admin_snapshots" in sa.inspect(connection).get_table_names()


DOC = {"heat": {"open_pct": 1.25, "cap_pct": 6.0}, "positions": [], "correlation": {"values": None}}
INPUTS = {"computed_at": T0.isoformat(), "missing": {"bars": {"XAUUSD": "spot_metal"}}}


def test_put_inserts_and_read_returns_the_row(db_conn):
    repo = snaps.AdminSnapshotRepository()
    assert repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=True, conn=db_conn) is True
    row = repo.read("risk", conn=db_conn)
    assert (row["key"], row["doc"], row["inputs"], row["computed_at"], row["stale_inputs"]) == (
        "risk", DOC, INPUTS, T0, True)
    assert row["updated_at"].tzinfo is not None
    assert repo.read("calendar.pnl:2026-10", conn=db_conn) is None


def test_put_newer_computed_at_replaces(db_conn):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=True, conn=db_conn)
    newer = {**DOC, "positions": [{"ticker": "AAPL"}]}
    assert repo.put("risk", newer, {}, computed_at=T0 + timedelta(seconds=1),
                    stale_inputs=False, conn=db_conn) is True
    row = repo.read("risk", conn=db_conn)
    assert (row["doc"], row["inputs"], row["stale_inputs"]) == (newer, {}, False)


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-90)])
def test_put_older_computed_at_is_rejected(db_conn, delta):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=False, conn=db_conn)
    late = {"heat": {"open_pct": 99.0}}
    assert repo.put("risk", late, {}, computed_at=T0 + delta, stale_inputs=True, conn=db_conn) is False
    row = repo.read("risk", conn=db_conn)
    assert (row["doc"], row["computed_at"], row["stale_inputs"]) == (DOC, T0, False)


def test_put_refuses_naive_times_and_non_finite_numbers(db_conn):
    repo = snaps.AdminSnapshotRepository()
    with pytest.raises(ValueError):
        repo.put("risk", DOC, {}, computed_at=T0.replace(tzinfo=None), stale_inputs=False, conn=db_conn)
    with pytest.raises(ValueError):
        repo.put("risk", {"beta": math.nan}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    with pytest.raises(ValueError):
        repo.put("risk", DOC, {"rate": math.inf}, computed_at=T0, stale_inputs=False, conn=db_conn)
    assert repo.read("risk", conn=db_conn) is None


def test_read_many_returns_only_present_keys(db_conn):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    repo.put("analytics.snapshot", {"overall": {}}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    got = repo.read_many(["risk", "analytics.snapshot", "calendar.pnl:2026-10"], conn=db_conn)
    assert set(got) == {"risk", "analytics.snapshot"} and got["risk"]["doc"] == DOC
    assert repo.read_many([], conn=db_conn) == {}


def test_changed_since_sees_writes_after_the_cursor(db_conn):
    repo = snaps.AdminSnapshotRepository()
    cursor = db_conn.execute(sa.text("select clock_timestamp()")).scalar()
    repo.put("risk", DOC, {}, computed_at=T0, stale_inputs=True, conn=db_conn)
    [row] = repo.changed_since(cursor, conn=db_conn)
    assert (row["key"], row["computed_at"], row["stale_inputs"]) == ("risk", T0, True)
    assert set(row) == {"key", "computed_at", "stale_inputs", "updated_at"}
    assert repo.changed_since(row["updated_at"], conn=db_conn) == []
    repo.put("risk", DOC, {}, computed_at=T0 - timedelta(seconds=5), stale_inputs=False, conn=db_conn)
    assert repo.changed_since(row["updated_at"], conn=db_conn) == []      # a rejected put is no change


def test_prune_deletes_old_months_only(db_conn):
    repo = snaps.AdminSnapshotRepository()
    for key in ("risk", "calendar.pnl:2026-08", "calendar.pnl:2026-09", "calendar.pnl:2026-10"):
        repo.put(key, {}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    assert repo.prune("calendar_pnl:", [], conn=db_conn) == 0            # "_" is not a LIKE wildcard here
    assert repo.prune("calendar.pnl:", ["calendar.pnl:2026-10", "calendar.pnl:2026-09"], conn=db_conn) == 1
    assert set(repo.read_many(["risk", "calendar.pnl:2026-08", "calendar.pnl:2026-09",
                               "calendar.pnl:2026-10"], conn=db_conn)) == {
        "risk", "calendar.pnl:2026-09", "calendar.pnl:2026-10"}


def test_accessor_is_a_singleton():
    assert snaps.admin_snapshot_repo() is snaps.admin_snapshot_repo()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v204_admin_snapshots.py`
Expected: FAIL at collection with `ImportError` (`admin_snapshots` repository module missing).

- [ ] **Step 3: Declare the table in `swingbot/core/db/schema.py`**

After v201's `refresher_heartbeat`, add this comment block: "v204: the admin snapshot pages' stored payloads, one row per key (risk, analytics.snapshot, analytics.performance:<ledger>, analytics.equity_curve:<ledger>, calendar.pnl:<YYYY-MM>). Written only by the refresher's snapshot worker, compare-and-set on computed_at. Read by the admin request door. No SSE trigger: the worker raises `market` itself."

```python
admin_snapshots = register(sa.Table("admin_snapshots", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("inputs", JSONB, nullable=False),
    *standard_columns(),
    sa.Index("admin_snapshots_updated_idx", "updated_at")),
    ("key", "computed_at", "stale_inputs", "inputs"))
```

`PROMOTION_REASONS["admin_snapshots"]`, one reason per promoted column:
- `"key"`: "primary key; one row per snapshot key, so the table never grows with time"
- `"computed_at"`: "the compare-and-set WHERE in put (newer computed_at wins) and the closed-market stale rule"
- `"stale_inputs"`: "bars older than the last completed session; read by /market/updates without the doc"
- `"inputs"`: "recorded inputs (quotes, FX, bar-file fingerprints, thresholds, code version), kept apart from the payload in doc"

- [ ] **Step 4: Write the revision** `swingbot/core/db/migrations/versions/v204_001_admin_snapshots.py`

First find the head: `python -m alembic -c <wt>/alembic.ini heads` (expect `v201_001`). Use it as `down_revision`.

```python
"""v204: admin_snapshots -- stored Risk/Analytics/Calendar/sparkline payloads.

Additive. Rollback is this revision's downgrade. Leaving the table after a code
rollback is also safe: only the snapshot worker and the admin door read it.

Revision ID: v204_001
Revises: <head printed above>
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v204_001"
down_revision = "v201_001"   # replace with the head printed above
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table("admin_snapshots",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("computed_at", _TS, nullable=False),
        sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()))
    op.create_index("admin_snapshots_updated_idx", "admin_snapshots", ["updated_at"])


def downgrade() -> None:
    op.drop_index("admin_snapshots_updated_idx", table_name="admin_snapshots")
    op.drop_table("admin_snapshots")
```

- [ ] **Step 5: Implement `swingbot/core/db/repositories/admin_snapshots.py`**

Module docstring: the one writer (the refresher's snapshot worker), the readers (the admin door and `/market/updates`), the compare-and-set rule and why it exists (a build abandoned on budget overrun may finish late), and that the table raises no SSE event. Connection handling is as in `equity_samples.py` (`Repository._tx(conn)`). `_STAMP = sa.func.clock_timestamp()` stamps `updated_at` on every write, as v201's repositories do, so a cursor read inside one transaction still orders the writes. Readers build plain dicts from row columns (`doc` stays the payload; do not use `_record`).

The statement the tests do not fully determine:

```python
    def put(self, key: str, doc: dict, inputs: dict, *, computed_at: datetime,
            stale_inputs: bool, conn: sa.Connection | None = None) -> bool:
        """Write when the row is absent or older; True when a row was written."""
        if computed_at.tzinfo is None:
            raise ValueError("computed_at must be timezone-aware")
        json.dumps(doc, allow_nan=False)        # ValueError on NaN/Infinity: never store one
        json.dumps(inputs, allow_nan=False)
        t = self.table
        ins = pg_insert(t).values(key=key, doc=doc, inputs=inputs,
                                  computed_at=computed_at.astimezone(timezone.utc),
                                  stale_inputs=bool(stale_inputs), updated_at=_STAMP)
        stmt = ins.on_conflict_do_update(
            index_elements=[t.c.key],
            set_={"doc": ins.excluded.doc, "inputs": ins.excluded.inputs,
                  "computed_at": ins.excluded.computed_at,
                  "stale_inputs": ins.excluded.stale_inputs, "updated_at": _STAMP},
            where=t.c.computed_at < ins.excluded.computed_at,
        ).returning(t.c.key)
        with self._tx(conn) as c:
            return c.execute(stmt).first() is not None
```

The rest follows the tests:
- `read` and `read_many` select the six columns. `read_many` returns `{}` for no keys without querying.
- `changed_since` selects `key, computed_at, stale_inputs, updated_at` where `updated_at > since`, ordered by `updated_at`.
- `prune` deletes where `t.c.key.startswith(prefix, autoescape=True)` and `t.c.key.not_in(list(keep))`, and returns `rowcount`. With an empty `keep`, it drops the `not_in` clause.
- `admin_snapshot_repo()` is a module-level singleton, as in `equity_samples_repo()`.

- [ ] **Step 6: Run the new test and the schema guards**

Run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`).
Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v204_admin_snapshots.py`, then the same for `tests/db/test_migrations.py` (declared schema == migrated schema, one head), `tests/db/test_trigger_coverage.py`, `tests/db/test_schema_contract.py`, `tests/db/test_v201_tables.py`
Expected: all PASS. `test_v201_tables.py::test_v201_001_sits_on_the_single_prior_head` asserts `heads == ["v201_001"]`; it now fails by design. Change that one assertion to `assert len(scripts.get_heads()) == 1` (the v204 test pins the actual head), and re-run the file. A `compare_metadata` diff in `test_migrations.py` names the column or index that differs between Step 3 and Step 4; fix the revision to match `schema.py`.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v204_001_admin_snapshots.py swingbot/core/db/repositories/admin_snapshots.py tests/db/test_v204_admin_snapshots.py tests/db/test_v201_tables.py
git -C <wt> commit -m "feat(v204): v204_001 admin_snapshots table and compare-and-set repository"
```

