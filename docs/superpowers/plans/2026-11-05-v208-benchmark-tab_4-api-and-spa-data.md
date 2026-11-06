# v208 — Benchmark tab, part 4: endpoint, dead-overlay removal, SPA client + store, chart extension

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (its *Amendment after the code brief* overrides earlier spec text)
**Index:** [2026-11-05-v208-benchmark-tab_0-index.md](2026-11-05-v208-benchmark-tab_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the **response contract** live there; every task below implicitly includes them.

Tasks V208-11..V208-14. V208-11 (endpoint) needs V208-2, V208-5, V208-6
and V208-10 merged. V208-12 is independent backend-wise. V208-13 edits
`models.ts` after V208-12. V208-14 needs nothing from this part.

Conventions used in this part:

- **The response carries percentages** (`1.02` = +1.02%), built by V208-10
  from the fractions `benchmark.py` returns. The SPA never multiplies by 100;
  it formats the number it receives with a `%` sign.
- The response contract in the index is the only interface between V208-10
  and this part. This part never reads part 3's file.
- Backend tests reach Postgres: run `/replicate-prod-db` once per session
  before the first `tests/admin/` run.
- Frontend runs are narrow: `node frontend/scripts/ng-test.mjs frontend --include <spec>`.
  The TypeScript check for code outside specs is `cd frontend && npx tsc --noEmit -p tsconfig.app.json`.

# Phase E — API


### Task V208-11: `GET /api/v1/analytics/benchmark`

**Model:** sonnet — a thin Flask view over finished pure builders, with house-style param checks and paging copied from `equity.py`; no new algorithm.

**Files:**
- Create: `swingbot/admin/api_v1/benchmark.py`
- Modify: `swingbot/admin/api_v1/__init__.py:208-210` (add `benchmark` to the `from . import (...)` list in `register()`, alphabetical: after `analytics`)
- Create: `tests/admin/test_api_v1_benchmark.py`
- Modify (**only if v207 is merged**, i.e. `tests/admin/access_expectations.py` exists): `tests/admin/access_expectations.py`

**Interfaces:**
- Consumes:
  - V208-10 `swingbot.core.analytics.benchmark_view`: `BenchmarkInputs(rows, legs, bars, sessions, now, account_currency: str, mixed_tickers: list[str], refresher_on: bool)`; `build_benchmark(inputs, *, start: date | None, end: date | None, capture: str) -> dict` (the index's response contract, `daily` complete and newest first, no `daily_has_more`).
  - V208-5 `swingbot.core.marketdata.benchmarks.BENCHMARK_SYMBOLS`.
  - V208-2 `swingbot.core.db.repositories.benchmark_bars.benchmark_bars_repo()`: `list_range(symbols, start, end) -> list[dict]`; `upsert_bars(rows) -> int` (tests).
  - V208-6 `swingbot.refresher.benchmarks.live_since() -> date | None` (the one definition of the clamp date; the module only defines functions, so importing it is safe).
  - Existing: `equity_samples_repo().list_rows()`, `equity.realized_legs(trades)`, `equity.main_book(trades)`, `session.market_today(now)`, `session.nyse_calendar().sessions(start, end)` (both ends inclusive), `fx.account_currency_code()`, `fx.quote_currency_code(ticker, *, fetch)`, `admin_refresh.refresher_on()`, `TradeLog().get_trades(status=None, limit=None, sort_by="opened_at")`. From `.equity`: `_choice(name, allowed, default)`, `_limit()` (default 120, 1..500, 400 `limit must be one of 1..500`). From `.analytics`: `_iso_day(name) -> str | None` (400 `<name> must be a YYYY-MM-DD date`).
- Produces:
  - route `analytics_benchmark()` at `GET /api/v1/analytics/benchmark`, `require_auth`.
  - `ALLOWED_PARAMS = ("from", "to", "capture", "limit", "before")`.
  - `_now() -> datetime` (UTC; the one clock read, monkeypatched by tests).
  - `_load_inputs(now: datetime, start: date | None = None) -> BenchmarkInputs` (`start` only narrows the mixed-currency trade check; the ledger's one-argument call still works).
  - `_mixed_tickers(trades: list[dict], since: date) -> list[str]`.
  - `_page_daily(daily: list[dict], before: date | None, limit: int) -> tuple[list[dict], bool]`.
  - Response = contract + `daily` paged + `daily_has_more: bool`.

Request rules (Global Constraints, spec § API):

1. Any parameter outside `ALLOWED_PARAMS` → 400 `invalid`, message
   `unknown parameter '<x>'; allowed: ['from', 'to', 'capture', 'limit', 'before']`
   (first unknown in sorted order, the `analytics_soak` pattern). So ledger,
   strategy, horizon and direction are rejected: equity is account-wide.
2. `from`, `to`, `before`: `_iso_day` then `date.fromisoformat`. `from > to` →
   400 `invalid`, `from must be on or before to`.
3. `capture`: `_choice("capture", BENCHMARK_SYMBOLS, "SPY")`.
4. `limit`: `_limit()`.
5. `build_benchmark(_load_inputs(now, start), start=start, end=end, capture=capture)`,
   then `daily, has_more = _page_daily(body["daily"], before, limit)`.

`_load_inputs`: `today = market_today(now)`; `first = live_since() or today`;
`sessions = nyse_calendar().sessions(first, today)`; `trades = _trades()`;
`rows = equity_samples_repo().list_rows()` (both sources, all kinds: V208-8/9
filter them); `bars = benchmark_bars_repo().list_range(BENCHMARK_SYMBOLS, first, today)`;
`legs = equity.realized_legs(trades)`; `account_currency = fx.account_currency_code()`;
`mixed_tickers = _mixed_tickers(trades, start or first)`;
`refresher_on = admin_refresh.refresher_on()`.

`_mixed_tickers`: over `equity.main_book(trades)`, keep a trade when
`status == "open"` or `(closed_at or "")[:10] >= since.isoformat()`. Return the
sorted unique upper-cased tickers whose `fx.quote_currency_code(t, fetch=False)`
is neither `None` (unknown is not evidence) nor `"USD"`. Call it through the
module (`fx.quote_currency_code`) so the pin in `tests/admin/conftest.py` applies.

`_page_daily`: keep rows with `row["date"] < before.isoformat()` when `before` is
set (ISO strings compare as dates), then return `rows[:limit]` and
`len(rows) > limit`. `daily` is newest first, so the first `limit` rows are the
newest ones older than the cursor.

- [ ] **Step 1: Sync the local replica**

Run `/replicate-prod-db` (shared `swing-db`, port 56789) unless a sibling task in this session already did.

- [ ] **Step 2: Write the failing tests**

```python
# tests/admin/test_api_v1_benchmark.py
"""v208: GET /api/v1/analytics/benchmark -- params, clamp, capture, paging, empty state."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from swingbot.admin.api_v1 import benchmark as benchmark_api
from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape
from tests.store_seed import seed_store

URL = "/api/v1/analytics/benchmark"
BASE = 10000.0
# Fri 2026-10-16, 17:00 New York: the session is closed and final.
NOW = datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc)
SESSIONS = [date(2026, 10, 12) + timedelta(days=i) for i in range(5)]   # Mon..Fri
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")

BODY = {"range": dict, "as_of": str, "session_state": str, "account_currency": str,
        "mixed_tickers": list, "benchmarks_status": str, "benchmarks_last_session": NULLABLE_STR,
        "today": (dict, type(None)), "series": list, "markers": list, "exposure": list,
        "stats": dict, "vs": dict, "capture": dict, "daily": list, "daily_has_more": bool}


@pytest.fixture
def logged_in(client):
    from swingbot.admin import app

    response = client.post("/api/v1/session", json={
        "username": app.ADMIN_USERNAME, "password": app.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def frozen(admin_app, monkeypatch):
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})
    monkeypatch.setattr(benchmark_api, "_now", lambda: NOW)
    monkeypatch.setattr(benchmark_api, "_trades", lambda: [])


def _sample(day: date, hour: int, minute: int, value: float) -> dict:
    return {"at": datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc),
            "realized_balance": Decimal(str(BASE)),
            "unrealized_pnl": Decimal(str(value - BASE)), "equity": Decimal(str(value)),
            "open_n": 1, "skipped_n": 0, "source": "live", "kind": "point", "backfill_run": None}


def _seed_week():
    rows = []
    for i, day in enumerate(SESSIONS):
        rows += [_sample(day, 13, 35, BASE + 10 * i), _sample(day, 19, 55, BASE + 20 * i)]
    EquitySampleRepository().upsert_many(rows)
    benchmark_bars_repo().upsert_bars([
        {"symbol": s, "session": day, "close": 100.0 + i, "adj_close": 100.0 + i,
         "day_pct": 0.002 * (1 if i % 2 else -1), "source_symbol": s, "final": True,
         "as_of": NOW}
        for s in SYMBOLS for i, day in enumerate(SESSIONS)])


def test_the_route_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


@pytest.mark.parametrize("query, message", [
    ("ledger=main", "unknown parameter 'ledger'; allowed: ['from', 'to', 'capture', 'limit', 'before']"),
    ("strategy=RSI", "unknown parameter 'strategy'"),
    ("currency=usd", "unknown parameter 'currency'"),
    ("from=2026-13-01", "from must be a YYYY-MM-DD date"),
    ("before=yesterday", "before must be a YYYY-MM-DD date"),
    ("from=2026-10-15&to=2026-10-13", "from must be on or before to"),
    ("capture=DIA", "capture must be one of SPY, QQQ, ^IXIC, ^DJI"),
    ("limit=0", "limit must be one of 1..500"),
    ("limit=501", "limit must be one of 1..500"),
])
def test_bad_params_are_a_400(frozen, logged_in, query, message):
    response = logged_in.get(f"{URL}?{query}")
    assert_error(response, "invalid", 400)
    assert message in response.get_json()["error"]["message"]


def test_an_empty_book_is_a_200_that_says_no_data_never_zeros(frozen, logged_in):
    body = logged_in.get(URL).get_json()
    assert_shape(body, BODY)
    assert body["benchmarks_status"] == "empty"
    assert body["daily"] == [] and body["daily_has_more"] is False


def test_a_range_before_the_live_book_clamps_to_live_since(frozen, logged_in):
    _seed_week()
    body = logged_in.get(f"{URL}?from=2026-09-01").get_json()
    assert_shape(body, BODY)
    assert body["range"]["live_since"] == "2026-10-12"
    assert body["range"]["from"] == "2026-10-12"
    assert body["range"]["clamped"] is True
    assert body["session_state"] == "closed"
    assert {s["key"] for s in body["series"]} == {"bot_account", "bot_deployed", *SYMBOLS}


def test_the_capture_param_picks_the_index(frozen, logged_in):
    _seed_week()
    assert logged_in.get(URL).get_json()["capture"]["index"] == "SPY"
    assert logged_in.get(f"{URL}?capture=QQQ").get_json()["capture"]["index"] == "QQQ"


def test_daily_pages_newest_first_with_before(frozen, logged_in):
    _seed_week()
    full = logged_in.get(f"{URL}?limit=500").get_json()["daily"]
    assert len(full) >= 3
    dates = [row["date"] for row in full]
    assert dates == sorted(dates, reverse=True)
    first = logged_in.get(f"{URL}?limit=2").get_json()
    assert first["daily"] == full[:2] and first["daily_has_more"] is True
    second = logged_in.get(f"{URL}?limit=2&before={full[1]['date']}").get_json()
    assert second["daily"] == full[2:4]
    assert second["daily_has_more"] is (len(full) > 4)


def test_page_daily_keeps_rows_strictly_before_the_cursor():
    rows = [{"date": d} for d in ("2026-10-16", "2026-10-15", "2026-10-14")]
    assert benchmark_api._page_daily(rows, None, 2) == (rows[:2], True)
    assert benchmark_api._page_daily(rows, date(2026, 10, 15), 2) == (rows[2:], False)
    assert benchmark_api._page_daily([], None, 120) == ([], False)


def test_a_non_usd_account_and_a_non_usd_ticker_reach_the_response(frozen, logged_in, monkeypatch):
    _seed_week()
    trades = [{"id": "a" * 16, "ticker": "SAP.DE", "status": "open", "ledger": "main"},
              {"id": "b" * 16, "ticker": "AAPL", "status": "open", "ledger": "main"}]
    monkeypatch.setattr(benchmark_api, "_trades", lambda: trades)
    monkeypatch.setattr(benchmark_api.fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(benchmark_api.fx, "quote_currency_code",
                        lambda t, **_kw: "EUR" if t == "SAP.DE" else "USD")
    body = logged_in.get(URL).get_json()
    assert body["account_currency"] == "EUR"
    assert body["mixed_tickers"] == ["SAP.DE"]


def test_mixed_tickers_skip_unknown_codes_and_old_closed_trades(monkeypatch):
    monkeypatch.setattr(benchmark_api.fx, "quote_currency_code",
                        lambda t, **_kw: {"BMW.DE": "EUR", "VOD.L": "GBp"}.get(t))
    trades = [{"ticker": "BMW.DE", "status": "win", "closed_at": "2026-09-01T15:00:00+00:00"},
              {"ticker": "VOD.L", "status": "loss", "closed_at": "2026-10-14T15:00:00+00:00"},
              {"ticker": "XYZ", "status": "open"}]
    assert benchmark_api._mixed_tickers(trades, date(2026, 10, 12)) == ["VOD.L"]
```

If `equity.main_book` drops these test trades because they lack a field it
reads, add that field (e.g. `"ledger": "main"`) to the fixtures; do not
bypass `main_book` in the code.

If v207 is merged (`tests/admin/access_expectations.py` exists), also add the
row `("/api/v1/analytics/benchmark", "GET"): "viewer",` to `EXPECTATIONS` and
this test to the file above:

```python
def test_a_viewer_can_read_the_benchmark(frozen, viewer_client):
    client, _row = viewer_client
    assert client.get(URL).status_code == 200
```

Otherwise add neither: v207's viewer matrix gains the route (index § Parallelisation).

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_benchmark.py`
Expected: collection error, `cannot import name 'benchmark' from 'swingbot.admin.api_v1'`.

- [ ] **Step 4: Implement `swingbot/admin/api_v1/benchmark.py`**

Module docstring: v208, the Benchmark tab's one read. Equity is account-wide,
so there is no BookScope. Every figure comes from `core.analytics.benchmark_view`;
this module only loads and pages. Imports:

```python
from __future__ import annotations

from datetime import date, datetime, timezone

from flask import jsonify, request

from swingbot.core.analytics.benchmark_view import BenchmarkInputs, build_benchmark
from swingbot.core.db.repositories.benchmark_bars import benchmark_bars_repo
from swingbot.core.db.repositories.equity_samples import equity_samples_repo
from swingbot.core.market import session
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.benchmarks import BENCHMARK_SYMBOLS
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.core.tracking import equity
from swingbot.refresher.benchmarks import live_since

from . import ApiError, api_v1
from .analytics import _iso_day
from .auth import require_auth
from .equity import _choice, _limit
```

Functions, each well under complexity 15: `_now()`, `_trades()` (import
`TradeLog` inside the function, as `equity._realized` does), `_reject_unknown()`,
`_day(name) -> date | None`, `_mixed_tickers`, `_load_inputs`, `_page_daily`,
and the view:

```python
@api_v1.route("/analytics/benchmark", methods=["GET"])
@require_auth
def analytics_benchmark():
    _reject_unknown()
    start, end, before = _day("from"), _day("to"), _day("before")
    if start and end and start > end:
        raise ApiError("invalid", "from must be on or before to", 400)
    capture = _choice("capture", BENCHMARK_SYMBOLS, "SPY")
    limit = _limit()
    body = build_benchmark(_load_inputs(_now(), start), start=start, end=end, capture=capture)
    body["daily"], body["daily_has_more"] = _page_daily(body["daily"], before, limit)
    return jsonify(body)
```

Then add `benchmark` to the `register()` import list in `api_v1/__init__.py`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_benchmark.py`
Expected: all pass, `0 failed`. Then `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
(the route-list tests still pass) and `python scripts/dev/complexity_gate.py` (no new offender).

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/api_v1/benchmark.py swingbot/admin/api_v1/__init__.py tests/admin/test_api_v1_benchmark.py
# plus tests/admin/access_expectations.py, only when v207 is merged
git commit -m "feat(v208): GET /api/v1/analytics/benchmark -- params, clamp, capture, daily paging"
```

### Task V208-12: Remove the dead v94 SPY overlay; Overview links to Benchmark

**Model:** sonnet — a deletion across four files plus one link, with every pinning test named; nothing to design.

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (delete `_index_benchmark` at :89-110; in `analytics_equity_curve` (:321) delete the docstring paragraph at :363-365, the `spy_cum = ...` line at :381 and the `"benchmark": ...` key at :407)
- Modify: `tests/admin/test_api_v1_analytics.py:337-363`
- Modify: `frontend/src/app/api/models.ts:653` (drop `benchmark` from `AnalyticsEquityCurve`; leave the unrelated `benchmark: { spy_cum: ... }` at :712 alone)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` (:144-148 notes, :202-206 style, :264-269 computed) and `overview.spec.ts:56`
- Modify: `frontend/src/app/stores/analytics.snapshot.spec.ts:75`, `frontend/src/app/stores/analytics.store.spec.ts:219`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `AnalyticsEquityCurve` without a `benchmark` key (V208-13 adds the new types to the same `models.ts`, after this task). The Overview Equity panel ends with one link: text `Compare with indexes → Benchmark tab`, `routerLink="/insights/analytics"`, `[queryParams]="{ tab: 'benchmark' }"`. Until V208-13 adds `'benchmark'` to `ANALYTICS_TABS`, `?tab=benchmark` falls back to Overview, which is harmless in the meantime.

Why this goes: `get_extended_stats` stopped computing `spy_cum` in 4ae117dc, so
production has always sent `benchmark.spy_indexed: []`. The overlay never drew
a line. Removing it also drops a `get_extended_stats` call from every
equity-curve request.

- [ ] **Step 1: Change the backend tests**

In `tests/admin/test_api_v1_analytics.py`:
- In `test_equity_curve_carries_currency_and_percent_and_scope`, replace the last line `assert "spy_indexed" in body["benchmark"]` with `assert "benchmark" not in body`.
- Delete `test_index_benchmark_rebases_to_first_point_in_range` (it imports `_index_benchmark`, which no longer exists).
- Add:

```python
def test_the_dead_spy_overlay_is_gone():
    """v208: no producer has emitted `spy_cum` since 4ae117dc; the Benchmark tab replaces it."""
    from swingbot.admin.api_v1 import analytics

    assert not hasattr(analytics, "_index_benchmark")
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: 2 failures (`benchmark` still in the body; `_index_benchmark` still defined).

- [ ] **Step 3: Delete the backend overlay**

In `swingbot/admin/api_v1/analytics.py`: delete the whole `_index_benchmark`
function, the docstring paragraph that starts `` `benchmark.spy_indexed` re-bases ``,
the `spy_cum = (tl.get_extended_stats(...) ...)` line and the
`"benchmark": {"spy_indexed": ...},` entry in the `jsonify` call. `tl` and
`all_raw` stay (they feed `closed`). Then run `git grep -n "spy_indexed\|_index_benchmark" -- swingbot tests`; it must print nothing.

- [ ] **Step 4: Run the backend tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: `0 failed`. Then `python scripts/dev/complexity_gate.py`: `analytics_equity_curve` was C(11) and can only go down.

- [ ] **Step 5: Change the frontend specs**

Remove `benchmark: { spy_indexed: [] }, ` from the three fixtures:
`overview.spec.ts:56`, `analytics.snapshot.spec.ts:75`, `analytics.store.spec.ts:219`.
Add to `overview.spec.ts`, inside `describe('OverviewTab', ...)`:

```ts
  it('links to the Benchmark tab in place of the dead SPY notes (v208)', () => {
    for (const unit of ['r', 'pct', 'money']) {
      TestBed.resetTestingModule();
      const { el } = render({ unit: signal(unit) });
      const link = el.querySelector<HTMLAnchorElement>('a.benchmark-link');
      expect(link, unit).not.toBeNull();
      expect(link!.textContent!.trim()).toBe('Compare with indexes → Benchmark tab');
      expect(link!.getAttribute('href')).toBe('/insights/analytics?tab=benchmark');
      expect(el.textContent).not.toContain('SPY indexed');
      expect(el.textContent).not.toContain('SPY appears in % mode only');
    }
  });

  it('keeps the link when the scope has no closed trades', () => {
    const { el } = render({ equityCurve: signal({ points: [], points_n: 0, as_of: null, scope: {}, n: 0 }) });
    expect(el.querySelector('a.benchmark-link')).not.toBeNull();
  });
```

- [ ] **Step 6: Run the Overview spec to see it fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: the two new tests fail (no `a.benchmark-link`).

- [ ] **Step 7: Change the SPA**

- `models.ts`: delete the `benchmark: { spy_indexed: ... };` line from `AnalyticsEquityCurve`.
- `overview.ts`: delete the `@if (store.unit() === 'pct' && benchmarkSeries().length) { ... } @else if ... { ... }` block. Delete the `benchmarkSeries` computed and its doc comment. Directly after the panel's `@if (store.equityCurveError() ...) { ... }` chain closes, and still inside that `<sb-panel>`, add:

```html
        <p class="benchmark-link-row">
          <a class="sb-hit benchmark-link" routerLink="/insights/analytics" [queryParams]="{ tab: 'benchmark' }">Compare with indexes → Benchmark tab</a>
        </p>
```

  Replace the `.benchmark-note` rule and its comment with
  `.benchmark-link-row { font-size: var(--text-chip); margin: var(--space-6) 0 0; }`
  (`sb-hit` already gives the link its 44 px touch target; `RouterLink` is already in `imports`).
- Run `git grep -n "spy_indexed\|benchmarkSeries\|benchmark-note" -- frontend/src`; it must print nothing.

- [ ] **Step 8: Run the frontend specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/overview.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/analytics.snapshot.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/analytics.store.spec.ts`
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json` (no reference to the removed key remains)

- [ ] **Step 9: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py \
  frontend/src/app/api/models.ts frontend/src/app/workspaces/analytics/tabs/overview.ts \
  frontend/src/app/workspaces/analytics/tabs/overview.spec.ts \
  frontend/src/app/stores/analytics.snapshot.spec.ts frontend/src/app/stores/analytics.store.spec.ts
git commit -m "refactor(v208): drop the dead v94 SPY overlay; Overview links to the Benchmark tab"
```

# Phase F — SPA data and chart

### Task V208-13: SPA client, models, store slice for the Benchmark tab

**Model:** sonnet — types copied from the fixed response contract, one client method, and a store slice that follows the `partials` pattern; the paging race guard is spelled out below.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append the v208 types after `AnalyticsEquityCurve`; V208-12 has already removed its `benchmark` key)
- Modify: `frontend/src/app/api/api-client.ts` (+ `api-client.spec.ts`)
- Modify: `frontend/src/app/stores/analytics.store.ts` (+ `analytics.store.spec.ts`)
- Modify: `frontend/src/app/stores/analytics.partials.spec.ts:42-45` (it pins `ANALYTICS_TABS.at(-1) === 'partials'`, which stops being true once `benchmark` is appended)

**Interfaces:**
- Consumes: the index's **response contract** (V208-10 builds it, V208-11 serves it with `daily_has_more`). Existing in the store: `fetchPanel`, `resolveOne`, `panelFail`, `RESOLVERS`, `LOADERS`, `reload`'s `one` map, `isoDate`.
- Produces (V208-15..17 read these):
  - `models.ts`: `BenchmarkRange = '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'All'`; `BenchmarkKey`; `BenchmarkStat`; `BenchmarkEstimate`; `BenchmarkPoint`; `BenchmarkSeries`; `BenchmarkTodayLine`; `BenchmarkToday`; `BenchmarkSeriesStats`; `BenchmarkVs`; `BenchmarkCapture`; `BenchmarkDailyRow`; `BenchmarkExposure`; `AnalyticsBenchmark` (shapes below).
  - `api-client.ts`: `export interface BenchmarkParams { from?: string; to?: string; capture?: string; limit?: number; before?: string }`; `ApiClient.analyticsBenchmark(params: BenchmarkParams = {}): Observable<AnalyticsBenchmark>`.
  - `analytics.store.ts`: `export const BENCHMARK_RANGES: readonly BenchmarkRange[]` (`['1W', '1M', '3M', 'YTD', '1Y', 'All']`); `export function benchmarkRangeDates(range: BenchmarkRange, today: string): { from?: string; to?: string }`; `export function nyToday(now?: Date): string`; `AnalyticsTab` and `ANALYTICS_TABS` + `'benchmark'` (last); `PanelKey` + `'benchmark'`; state `benchmark: AnalyticsBenchmark | null`, `benchmarkError: string | null`, `benchmarkRange: BenchmarkRange` (`'3M'`), `benchmarkCapture: string` (`'SPY'`), `benchmarkLoadingMore: boolean` (`false`); methods `setBenchmarkRange(range)`, `setBenchmarkCapture(symbol)`, `refreshBenchmark()`, `loadMoreBenchmarkDaily()`.

**Which dates are sent.** If the scope bar has a custom date (`scope.from` or
`scope.to` set), those dates are sent and the preset is ignored. V208-15 then
shows no preset as selected. Otherwise the preset decides:
`benchmarkRangeDates(benchmarkRange, nyToday())`. `to` is never sent for a
preset (the server ends at today). `capture` is always sent. Ledger, strategy,
horizon and direction are **never** sent: the endpoint answers them with a 400.

- [ ] **Step 1: Add the types to `models.ts`**

```ts
/* -- v208: the Benchmark tab. Percentages (1.02 = +1.02 %), never fractions. -- */
export type BenchmarkRange = '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'All';
export type BenchmarkIndexKey = 'SPY' | 'QQQ' | '^IXIC' | '^DJI';
export type BenchmarkKey = 'bot_account' | 'bot_deployed' | BenchmarkIndexKey;
/** `reason` is shown verbatim when `value` is null ("needs ≥ 20 sessions", "no variance", ...). */
export interface BenchmarkStat { value: number | null; n: number; reason: string | null; }
export interface BenchmarkEstimate extends BenchmarkStat { se?: number | null; t?: number | null; headline?: boolean; }
export interface BenchmarkPoint {
  date: string; cum_pct: number | null; day_pct: number | null; span: number;
  missing: boolean; proxy: boolean; approx: boolean; clipped: boolean;
}
export interface BenchmarkSeries {
  key: BenchmarkKey; label: string; kind: 'bot' | 'index'; total_return: boolean; points: BenchmarkPoint[];
}
export interface BenchmarkTodayLine { pct: number | null; final: boolean; }
export interface BenchmarkToday { session: string; final: boolean; lines: Partial<Record<BenchmarkKey, BenchmarkTodayLine>>; }
export interface BenchmarkSeriesStats {
  total_pct: BenchmarkStat; max_dd_pct: BenchmarkStat; sharpe: BenchmarkStat;
  money_dd?: BenchmarkStat; losing_streak?: number; approx_share?: number | null;
}
export interface BenchmarkVs { lead_pp: BenchmarkStat; beta: BenchmarkEstimate; alpha: BenchmarkEstimate; }
export interface BenchmarkCapture {
  index: BenchmarkIndexKey; up_pct: BenchmarkStat; down_pct: BenchmarkStat; ratio: BenchmarkStat;
  up_n: number; down_n: number;
  beat: { up_days: number; up_beat: number; down_days: number; down_beat: number };
}
export interface BenchmarkDailyRow {
  date: string; lines: Partial<Record<BenchmarkKey, number | null>>; exposure_pct: number | null;
  open_n: number | null; beat: boolean | null; span: number; missing: boolean;
}
export interface BenchmarkExposure { date: string; pct: number | null; open_n: number; approx: boolean; }
export interface AnalyticsBenchmark {
  range: { from: string | null; to: string | null; live_since: string | null; sessions_n: number; clamped: boolean; is_all: boolean };
  as_of: string; session_state: 'pre' | 'open' | 'closed';
  account_currency: string; mixed_tickers: string[];
  benchmarks_status: 'ok' | 'stale' | 'empty'; benchmarks_last_session: string | null;
  today: BenchmarkToday | null;
  series: BenchmarkSeries[]; markers: { date: string; kind: 'base_balance' }[]; exposure: BenchmarkExposure[];
  stats: Partial<Record<BenchmarkKey, BenchmarkSeriesStats>>; vs: Partial<Record<BenchmarkIndexKey, BenchmarkVs>>;
  capture: BenchmarkCapture; daily: BenchmarkDailyRow[]; daily_has_more: boolean;
}
```

- [ ] **Step 2: Write the failing client test** (new `describe` in `api-client.spec.ts`, same providers and `afterEach(() => http.verify())` as `'ApiClient — equity candles'`)

```ts
describe('ApiClient — benchmark (v208)', () => {
  // providers / beforeEach / afterEach exactly as in 'ApiClient — equity candles'
  it('sends only the params it is given and never a BookScope field', () => {
    api.analyticsBenchmark().subscribe();
    const bare = http.expectOne((r) => r.url.endsWith('/api/v1/analytics/benchmark'));
    expect(bare.request.params.keys()).toEqual([]);
    bare.flush({});

    api.analyticsBenchmark({ from: '2026-08-05', capture: 'QQQ', limit: 2, before: '2026-11-03' }).subscribe();
    const full = http.expectOne((r) => r.url.endsWith('/api/v1/analytics/benchmark'));
    expect(full.request.params.get('from')).toBe('2026-08-05');
    expect(full.request.params.get('capture')).toBe('QQQ');
    expect(full.request.params.get('limit')).toBe('2');
    expect(full.request.params.get('before')).toBe('2026-11-03');
    for (const key of ['to', 'ledger', 'strategy', 'horizon', 'direction']) expect(full.request.params.has(key)).toBe(false);
    full.flush({});
  });
});
```

- [ ] **Step 3: Write the failing store tests**

In `analytics.partials.spec.ts`, rename the test to `'is a tab and routes from ?tab=partials'` and replace `expect(ANALYTICS_TABS.at(-1)).toBe('partials');` with `expect(ANALYTICS_TABS).toContain('partials');`.

In `analytics.store.spec.ts`, import `vi` from vitest; import `BENCHMARK_RANGES`, `benchmarkRangeDates`, `nyToday`, `ANALYTICS_TABS` from `./analytics.store`; import `scopeFromParams` from `'../workspaces/analytics/scope-url'` (as `analytics.partials.spec.ts` does). Add a top-level pure block and a nested block inside `describe('AnalyticsStore', ...)`:

```ts
describe('benchmark range dates (v208)', () => {
  it('resolves every preset against a New York calendar day', () => {
    expect(BENCHMARK_RANGES).toEqual(['1W', '1M', '3M', 'YTD', '1Y', 'All']);
    expect(benchmarkRangeDates('1W', '2026-11-05')).toEqual({ from: '2026-10-29' });
    expect(benchmarkRangeDates('1M', '2026-11-05')).toEqual({ from: '2026-10-05' });
    expect(benchmarkRangeDates('3M', '2026-11-05')).toEqual({ from: '2026-08-05' });
    expect(benchmarkRangeDates('YTD', '2026-11-05')).toEqual({ from: '2026-01-01' });
    expect(benchmarkRangeDates('1Y', '2026-11-05')).toEqual({ from: '2025-11-05' });
    expect(benchmarkRangeDates('All', '2026-11-05')).toEqual({});
  });
  it('clamps to the last day of a shorter month and crosses the year', () => {
    expect(benchmarkRangeDates('3M', '2026-05-31')).toEqual({ from: '2026-02-28' });
    expect(benchmarkRangeDates('1M', '2026-03-31')).toEqual({ from: '2026-02-28' });
    expect(benchmarkRangeDates('1Y', '2028-02-29')).toEqual({ from: '2027-02-28' });
    expect(benchmarkRangeDates('3M', '2026-01-15')).toEqual({ from: '2025-10-15' });
    expect(benchmarkRangeDates('1W', '2026-01-03')).toEqual({ from: '2025-12-27' });
  });
  it('takes today in New York, not UTC', () => {
    expect(nyToday(new Date('2026-11-06T03:00:00Z'))).toBe('2026-11-05');
    expect(nyToday(new Date('2026-11-06T06:00:00Z'))).toBe('2026-11-06');
  });
});
```

```ts
  describe('the Benchmark tab (v208)', () => {
    const STAT = { value: null, n: 0, reason: 'needs ≥ 10 index-up and ≥ 10 index-down sessions' };
    const row = (date: string) => ({ date, lines: { bot_account: 0.1, SPY: 0.2 }, exposure_pct: 40,
      open_n: 2, beat: false, span: 1, missing: false });
    const BENCHMARK = {
      range: { from: '2026-08-05', to: '2026-11-04', live_since: '2026-08-07', sessions_n: 2, clamped: true, is_all: false },
      as_of: '2026-11-05T15:00:00+00:00', session_state: 'open', account_currency: 'USD', mixed_tickers: [],
      benchmarks_status: 'ok', benchmarks_last_session: '2026-11-04', today: null,
      series: [], markers: [], exposure: [], stats: {}, vs: {},
      capture: { index: 'SPY', up_pct: STAT, down_pct: STAT, ratio: STAT, up_n: 0, down_n: 0,
                 beat: { up_days: 0, up_beat: 0, down_days: 0, down_beat: 0 } },
      daily: [row('2026-11-04'), row('2026-11-03')], daily_has_more: true,
    };
    const isBench = (req: { url: string }) => req.url === '/api/v1/analytics/benchmark';

    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['Date'] });
      vi.setSystemTime(new Date('2026-11-05T15:00:00Z'));
      tick();
      respondOverview();
    });
    afterEach(() => vi.useRealTimers());

    const open = () => {
      store.setTab('benchmark');
      tick();
      const req = backend.expectOne(isBench);
      req.flush(BENCHMARK);
      return req;
    };

    it('is the last tab, routes from ?tab=benchmark, and is fetched only while open', () => {
      expect(ANALYTICS_TABS.at(-1)).toBe('benchmark');
      expect(scopeFromParams(convertToParamMap({ tab: 'benchmark' })).tab).toBe('benchmark');
      backend.expectNone(isBench);
      const req = open();
      expect(req.request.params.get('from')).toBe('2026-08-05');
      expect(req.request.params.get('capture')).toBe('SPY');
      for (const key of ['to', 'ledger', 'strategy', 'horizon', 'direction']) expect(req.request.params.has(key)).toBe(false);
      expect(store.benchmark()?.daily.length).toBe(2);
      expect(store.benchmarkRange()).toBe('3M');
      backend.verify();
    });

    it('refetches on a range or capture change, and All sends no dates', () => {
      open();
      store.setBenchmarkRange('All');
      const all = backend.expectOne(isBench);
      expect(all.request.params.has('from')).toBe(false);
      all.flush(BENCHMARK);
      store.setBenchmarkCapture('QQQ');
      expect(backend.expectOne(isBench).request.params.get('capture')).toBe('QQQ');
    });

    it('lets a custom scope-bar date win over the preset', () => {
      open();
      store.setScope({ from: '2026-09-01' });
      const req = backend.expectOne(isBench);
      expect(req.request.params.get('from')).toBe('2026-09-01');
      expect(req.request.params.has('ledger')).toBe(false);
    });

    it('appends older daily rows and stops when the server has no more', () => {
      open();
      store.loadMoreBenchmarkDaily();
      expect(store.benchmarkLoadingMore()).toBe(true);
      const more = backend.expectOne(isBench);
      expect(more.request.params.get('before')).toBe('2026-11-03');
      more.flush({ ...BENCHMARK, daily: [row('2026-10-31')], daily_has_more: false });
      expect(store.benchmark()?.daily.map((r) => r.date)).toEqual(['2026-11-04', '2026-11-03', '2026-10-31']);
      expect(store.benchmark()?.daily_has_more).toBe(false);
      expect(store.benchmarkLoadingMore()).toBe(false);
      store.loadMoreBenchmarkDaily();
      backend.expectNone(isBench);
    });

    it('drops an older page that lands after the range changed', () => {
      open();
      store.loadMoreBenchmarkDaily();
      store.setBenchmarkRange('1M');
      const [more, fresh] = [
        backend.expectOne((r) => isBench(r) && r.params.has('before')),
        backend.expectOne((r) => isBench(r) && !r.params.has('before')),
      ];
      fresh.flush({ ...BENCHMARK, daily: [row('2026-11-04')], daily_has_more: false });
      more.flush({ ...BENCHMARK, daily: [row('2026-08-01')], daily_has_more: true });
      expect(store.benchmark()?.daily.map((r) => r.date)).toEqual(['2026-11-04']);
      expect(store.benchmarkLoadingMore()).toBe(false);
    });

    it('a poll refresh keeps the loaded rows and a failed one keeps the data', () => {
      open();
      store.refreshBenchmark();
      const poll = backend.expectOne(isBench);
      expect(poll.request.params.get('limit')).toBe('120');
      poll.flush('boom', { status: 500, statusText: 'Server Error' });
      expect(store.benchmark()?.daily.length).toBe(2);
      expect(store.benchmarkError()).not.toBeNull();
      store.reload('benchmark');
      backend.expectOne(isBench).flush(BENCHMARK);
      expect(store.benchmarkError()).toBeNull();
    });
  });
```

(Import `afterEach` with the other vitest names. If the store's `afterEach` hooks or interceptors make `expectNone` noisy, keep the assertion and fix the setup, never drop the check.)

- [ ] **Step 4: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/analytics.store.spec.ts` and `... --include src/app/api/api-client.spec.ts`
Expected: compile errors (`benchmarkRangeDates`, `analyticsBenchmark` not exported/defined).

- [ ] **Step 5: Implement the client method**

In `api-client.ts`: import `AnalyticsBenchmark` in the models import list, export `BenchmarkParams`, and add next to `analyticsPartials`:

```ts
  /** v208 — the Benchmark tab. Account-wide: never sends a BookScope field (the route 400s on one). */
  analyticsBenchmark(params: BenchmarkParams = {}): Observable<AnalyticsBenchmark> {
    let query = new HttpParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') query = query.set(key, String(value));
    }
    return this.http.get<AnalyticsBenchmark>(`${this.base}/analytics/benchmark`, { params: query });
  }
```

- [ ] **Step 6: Implement the store slice**

1. `AnalyticsTab`/`ANALYTICS_TABS`: append `'benchmark'`. `PanelKey`: add `'benchmark'`. Update the tab doc comment's count.
2. Exports next to `presetRange`: `BENCHMARK_RANGES`, `nyToday(now = new Date())` (`new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)`), and:

```ts
export function benchmarkRangeDates(range: BenchmarkRange, today: string): { from?: string; to?: string } {
  if (range === 'All') return {};
  const [y, m, d] = today.split('-').map(Number);
  if (range === 'YTD') return { from: `${y}-01-01` };
  if (range === '1W') return { from: isoDate(new Date(Date.UTC(y, m - 1, d - 7))) };
  const back = range === '1M' ? 1 : range === '3M' ? 3 : 12;
  const month = new Date(Date.UTC(y, m - 1 - back, 1));
  const lastDay = new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + 1, 0)).getUTCDate();
  return { from: isoDate(new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth(), Math.min(d, lastDay)))) };
}
```

3. `AnalyticsSlice` + `withState` init: the five fields with the defaults in Interfaces.
4. In `withMethods`: `benchmarkParams()` (the dates rule above plus `capture`); `loadBenchmark = () => fetchPanel(api.analyticsBenchmark(benchmarkParams()), 'benchmark', 'benchmarkError')`; `resolveBenchmark = () => resolveOne(api.analyticsBenchmark(benchmarkParams()), 'benchmark', 'benchmarkError')`. Add `benchmark:` to `RESOLVERS`, `LOADERS` and `reload`'s `one` map.
5. Methods: `setBenchmarkRange(range)` and `setBenchmarkCapture(symbol)` patch, then `loadBenchmark()`. `refreshBenchmark()` = `fetchPanel` with `limit: Math.min(500, Math.max(120, store.benchmark()?.daily.length ?? 0))` (no `loading` flag, so a poll never blanks the tab). `loadMoreBenchmarkDaily()`: return when there is no payload, `!daily_has_more`, `daily` is empty, or a load is already running. Otherwise remember `key = JSON.stringify(benchmarkParams())`, set `benchmarkLoadingMore: true`, request `{ ...benchmarkParams(), before: daily.at(-1).date }`. On `next`: always clear `benchmarkLoadingMore`; append `page.daily` and take `page.daily_has_more` **only if** `JSON.stringify(benchmarkParams()) === key`. On `error`: clear the flag, then `panelFail('benchmarkError')`.

- [ ] **Step 7: Run the specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/analytics.store.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/analytics.partials.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/api/api-client.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/scope-url.spec.ts`
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts \
  frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts \
  frontend/src/app/stores/analytics.partials.spec.ts
git commit -m "feat(v208): Benchmark client, models and store slice (range presets, paging, poll refresh)"
```

### Task V208-14: `<sb-line-chart>` colour/dash/gaps/multi hover + `<sb-exposure-strip>`

**Model:** sonnet — additive inputs on one shared chart primitive with Overview-unchanged pins, plus a small sibling SVG; the gap-path rule is given below.

**Files:**
- Modify: `frontend/src/app/ui/line-chart.ts` (+ `line-chart.spec.ts`)
- Modify: `frontend/src/app/ui/small-multiples.ts` (one expression: its `sharedDomain` spreads `pt.value` into `Math.min`, which no longer type-checks once `value` may be `null`)
- Create: `frontend/src/app/ui/exposure-strip.ts` (+ `exposure-strip.spec.ts`)

**Interfaces:**
- Consumes: `token(name)` from `./chart/chart-frame`; the existing `lineChartXScale`.
- Produces (V208-16 uses these):
  - `LineChartPoint { date: string; value: number | null; day?: number | null; flag?: string }`. `null` is a gap: no `0`, no interpolation.
  - `LineChartSeries { name: string; points: LineChartPoint[]; color?: string; dashed?: boolean }`. `color` is a CSS custom-property **name** (`'--chart-3'`, `'--accent'`), resolved through `token()`, never a raw colour. Absent → the palette colour by index, as today.
  - `seriesPath(series, xScale, yScale)` lifts the pen at every `null` (the next real point starts a new `M`).
  - `LineChart` input `hoverDetail: boolean` (default `false`). When false, the tooltip is byte-for-byte today's (`<name>: <valueFormat(value)>`, null-valued points left out). When true, each series gets a row: `<name>: <fmt(value)>`, then ` (day <fmt(day)>)` when `day` is a number, then ` · <flag>` when `flag` is set. A `null` value prints `<name>: —`.
  - The tooltip also opens on `pointerdown` (tap-to-inspect on phones).
  - `exposureBars(dates: readonly string[], bars: readonly ExposureBar[]): ExposureRect[]` and `ExposureStrip` (selector `sb-exposure-strip`, inputs `dates: string[]` (required; **the chart's own x dates**, so both share `lineChartXScale(dates)`) and `bars: ExposureBar[]` (required)). `ExposureBar = { date: string; pct: number | null; approx: boolean }`; `ExposureRect = { date: string; pct: number; approx: boolean; x: number; width: number; height: number }`, in a 600 × 40 viewBox.

Overview, Edge, Partials, Small multiples and the gallery pass none of the new
fields, so they must render exactly as before. The existing `line-chart.spec.ts`
tests stay green unchanged; they are the pin.

- [ ] **Step 1: Write the failing line-chart tests** (append to `line-chart.spec.ts`; import `token` from `./chart/chart-frame`)

```ts
describe('seriesPath gaps (v208)', () => {
  const x = (d: string) => ({ a: 0, b: 0.25, c: 0.5, d: 1 } as Record<string, number>)[d];
  const y = (v: number) => v / 10;
  it('lifts the pen at a null and never draws it as zero', () => {
    const path = seriesPath({ name: 's', points: [
      { date: 'a', value: 1 }, { date: 'b', value: null }, { date: 'c', value: 2 }, { date: 'd', value: 3 }] }, x, y);
    expect(path).toBe('M 0.0000 0.9000 M 0.5000 0.8000 L 1.0000 0.7000');
  });
  it('starts at the first real point and returns nothing for an all-null series', () => {
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: null }, { date: 'b', value: 5 }] }, x, y))
      .toBe('M 0.2500 0.5000');
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: null }] }, x, y)).toBe('');
  });
  it('draws a gap-free series exactly as before', () => {
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: 0 }, { date: 'd', value: 10 }] }, x, y))
      .toBe('M 0.0000 1.0000 L 1.0000 0.0000');
  });
});

describe('LineChart v208 options', () => {
  type S = { name: string; points: { date: string; value: number | null; day?: number | null; flag?: string }[];
             color?: string; dashed?: boolean };
  function render(series: S[], detail = false) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(LineChart);
    fixture.componentRef.setInput('series', series);
    fixture.componentRef.setInput('valueFormat', (v: number) => `${v.toFixed(2)}%`);
    if (detail) fixture.componentRef.setInput('hoverDetail', true);
    fixture.detectChanges();
    return fixture;
  }
  const hover = (fixture: ReturnType<typeof render>, type = 'pointermove') => {
    fixture.nativeElement.querySelector('svg').dispatchEvent(new MouseEvent(type, { clientX: 0, bubbles: true }));
    fixture.detectChanges();
    return (fixture.nativeElement.querySelector('.tooltip')?.textContent ?? '').replace(/\s+/g, ' ').trim();
  };
  beforeEach(() => TestBed.resetTestingModule());

  it('takes a colour token per series and dashes on request, legend included', () => {
    const fixture = render([
      { name: 'acct', color: '--chart-3', points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 1 }] },
      { name: 'dep', color: '--chart-3', dashed: true, points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 2 }] },
    ]);
    const paths = fixture.nativeElement.querySelectorAll('path.series');
    expect(paths[0].getAttribute('stroke')).toBe(token('--chart-3'));
    expect(paths[0].getAttribute('stroke-dasharray')).toBeNull();
    expect(paths[1].getAttribute('stroke-dasharray')).toBe('6 4');
    expect(fixture.nativeElement.querySelectorAll('.legend .entry i.dashed')).toHaveLength(1);
  });

  it('keeps the palette colour by index when no colour is given', () => {
    const fixture = render([{ name: 'a', points: [{ date: '2026-01-01', value: 1 }] },
                            { name: 'b', points: [{ date: '2026-01-01', value: 2 }] }]);
    expect(fixture.nativeElement.querySelectorAll('path.series')[1].getAttribute('stroke')).toBe(token('--chart-2'));
  });

  it('ignores nulls when scaling and never writes NaN', () => {
    const fixture = render([{ name: 'a', points: [
      { date: '2026-01-01', value: 1 }, { date: '2026-01-02', value: null }, { date: '2026-01-03', value: 3 }] }]);
    expect(fixture.nativeElement.querySelector('path.series').getAttribute('d')).not.toContain('NaN');
  });

  it('shows "No data to chart." when every value is null', () => {
    const fixture = render([{ name: 'a', points: [{ date: '2026-01-01', value: null }] }]);
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('No data to chart.');
  });

  it('keeps the plain tooltip when hoverDetail is off, leaving a null point out', () => {
    const text = hover(render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 10, day: 1 }] },
      { name: 'gap', points: [{ date: '2026-01-01', value: null }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 1 }] },
    ]));
    expect(text).toBe('2026-01-01 ui: 10.00% bot: 1.00%');
  });

  it('gives cumulative, day % and flag per series when hoverDetail is on, and — for a gap', () => {
    const text = hover(render([
      { name: 'Bot · account', points: [{ date: '2026-01-01', value: 1.5, day: 0.25 }] },
      { name: 'SPY', points: [{ date: '2026-01-01', value: 2, day: -0.5, flag: 'proxy' }] },
      { name: 'Bot · deployed', points: [{ date: '2026-01-01', value: null, flag: 'gap' }] },
    ], true));
    expect(text).toBe('2026-01-01 Bot · account: 1.50% (day 0.25%) SPY: 2.00% (day -0.50%) · proxy Bot · deployed: — · gap');
  });

  it('opens the tooltip on a tap', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 10 }] }]);
    expect(hover(fixture, 'pointerdown')).toContain('ui: 10.00%');
  });
});
```

- [ ] **Step 2: Write the failing exposure-strip tests** (`frontend/src/app/ui/exposure-strip.spec.ts`)

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { ExposureStrip, exposureBars } from './exposure-strip';

const DATES = ['2026-01-01', '2026-01-11', '2026-01-21'];

describe('exposureBars', () => {
  it('centres each bar on the chart x scale and skips a missing day', () => {
    const rects = exposureBars(DATES, [
      { date: '2026-01-01', pct: 50, approx: false },
      { date: '2026-01-11', pct: null, approx: false },
      { date: '2026-01-21', pct: 100, approx: true },
    ]);
    expect(rects.map((r) => r.date)).toEqual(['2026-01-01', '2026-01-21']);
    expect(rects[0].width).toBeCloseTo(160, 5);            // 600 / 3 × 0.8
    expect(rects[0].x).toBe(0);                            // clamped at the left edge
    expect(rects[1].x).toBeCloseTo(440, 5);                // clamped at the right edge
    expect(rects[0].height).toBeCloseTo(20, 5);            // 50 % of 40
    expect(rects[1].height).toBeCloseTo(40, 5);
    expect(rects[1].approx).toBe(true);
  });
  it('places a middle bar on its date and caps the height at 100 %', () => {
    const [mid] = exposureBars(DATES, [{ date: '2026-01-11', pct: 140, approx: false }]);
    expect(mid.x + mid.width / 2).toBeCloseTo(300, 5);
    expect(mid.height).toBeCloseTo(40, 5);
    expect(mid.pct).toBe(140);
  });
  it('returns nothing without dates, and ignores a bar on a date the chart lacks', () => {
    expect(exposureBars([], [{ date: '2026-01-01', pct: 10, approx: false }])).toEqual([]);
    expect(exposureBars(DATES, [{ date: '2026-02-01', pct: 10, approx: false }])).toEqual([]);
  });
});

describe('ExposureStrip', () => {
  function render(dates: string[], bars: { date: string; pct: number | null; approx: boolean }[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(ExposureStrip);
    fixture.componentRef.setInput('dates', dates);
    fixture.componentRef.setInput('bars', bars);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  it('draws one labelled bar per real day, approximated ones marked', () => {
    const el = render(DATES, [{ date: '2026-01-01', pct: 41.24, approx: true }, { date: '2026-01-11', pct: null, approx: false }]);
    expect(el.querySelector('svg')?.getAttribute('aria-label')).toBe('Exposure: share of equity in open trades per session');
    const rects = el.querySelectorAll('rect.bar');
    expect(rects).toHaveLength(1);
    expect(rects[0].classList.contains('approx')).toBe(true);
    expect(rects[0].querySelector('title')?.textContent).toBe('2026-01-01: 41.2% (approx.)');
  });
  it('renders nothing when there are no dates', () => {
    expect(render([], []).querySelector('svg')).toBeNull();
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/line-chart.spec.ts` and `... --include src/app/ui/exposure-strip.spec.ts`
Expected: type errors on `value: null`/`hoverDetail`, and `./exposure-strip` not found.

- [ ] **Step 4: Extend `line-chart.ts`**

- Widen the two interfaces as in Interfaces (doc comment: `null` = no observation, drawn as a gap).
- `seriesPath`: one loop. A `null` value sets `pen = false`; a real value emits `M` when the pen is up, otherwise `L`, then sets `pen = true`. This is the same output as today for gap-free input, including one point → `M x y`, so delete the special cases.
- `allValues` and `hasData` count only non-null values.
- `colorFor(index)` → `colorOf(series, index)`: `series.color ? token(series.color) : seriesColour(index)`, used by the path and the legend.
- Path: `[attr.stroke-dasharray]="series.dashed ? '6 4' : null"`. Legend swatch: `<i [class.dashed]="!!series.dashed" [style.background]="series.dashed ? null : colorOf(series, i)" [style.border-top-color]="colorOf(series, i)">`, plus `.entry i.dashed { width: 14px; height: 0; border-radius: 0; border-top: 2px dashed; }`.
- `hoverDetail = input(false)`. `tooltipRows` returns `{ name: string; text: string }[]` built by the rules in Interfaces; the template prints `{{ row.text }}`. In plain mode, `text` is `${name}: ${valueFormat(value)}`, which is what the template printed before.
- Add `(pointerdown)="onPointerMove($event)"` beside `(pointermove)`.

In `small-multiples.ts`, change `s.points.map(pt=>pt.value)` to `s.points.flatMap(pt=>pt.value===null?[]:[pt.value])` and leave the rest of that one-line file alone.

- [ ] **Step 5: Create `exposure-strip.ts`**

`exposureBars`: `const scale = lineChartXScale(dates)`; `width = 600 / dates.length * 0.8`; keep a bar only when `pct !== null` and `dates.includes(date)`; `x = min(max(scale(date) * 600 - width / 2, 0), 600 - width)`; `height = min(max(pct, 0), 100) / 100 * 40`. Component: standalone, `OnPush`, renders nothing when `dates()` is empty. Otherwise `<svg viewBox="0 0 600 40" preserveAspectRatio="none" role="img" aria-label="Exposure: share of equity in open trades per session">` with one `<rect class="bar" [class.approx]="r.approx" [attr.x] [attr.y]="40 - r.height" [attr.width] [attr.height]><title>{{ r.date }}: {{ r.pct.toFixed(1) }}%{{ r.approx ? ' (approx.)' : '' }}</title></rect>` per rect. Styles: `:host { display: block; }`, `svg { width: 100%; height: 40px; display: block; }`, `rect.bar { fill: var(--text-faint); }`, `rect.bar.approx { fill-opacity: 0.45; }`. Same width as the chart above it, so the two line up at every width.

- [ ] **Step 6: Run the specs to see them pass**

Run each, expecting `0 failed`:
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/line-chart.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/exposure-strip.spec.ts`
- `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/analytics/tabs/overview.spec.ts` (Overview unchanged)
- `node frontend/scripts/ng-test.mjs frontend --include src/app/ui/all-sources.spec.ts` and `... --include src/app/ui/chart-palette.spec.ts` (no raw colours; token-only)
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json` (Edge, Partials, Small multiples and the gallery still compile)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts \
  frontend/src/app/ui/small-multiples.ts \
  frontend/src/app/ui/exposure-strip.ts frontend/src/app/ui/exposure-strip.spec.ts
git commit -m "feat(v208): line chart colour/dash/gaps/hover detail; exposure strip on the chart's x scale"
```
