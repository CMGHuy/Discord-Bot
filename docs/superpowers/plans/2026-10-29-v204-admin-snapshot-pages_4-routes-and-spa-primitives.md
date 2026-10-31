# v204 Admin snapshot pages, part 4: routes and SPA primitives

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin snapshot pages](../specs/2026-10-29-v204-admin-snapshot-pages.md) (precedence: "Brief corrections", then "Panel amendments", then the earlier text)
**Index:** [`_0-index.md`](2026-10-29-v204-admin-snapshot-pages_0-index.md). The Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and every cross-task contract ("Request-path door additions", "Endpoints", "SPA contract") live there and bind every task below.

Part scope: V204-13 … V204-15. The dashboard sparkline, `/analytics/snapshot`
and the strategies registry read the `analytics.snapshot` row; the default
Analytics and Calendar views read their rows when V204-2 marked the route
`snapshot`; every one of those bodies gains `market_meta`; the page-load guard
covers Risk, Analytics and Calendar; and the SPA gains the primitives part 5
renders with.

`<wt>` is the implementation worktree's absolute path. Every DB-backed test
run is preceded once per session by `/replicate-prod-db` into the shared
`swing-db` container.

**Consumed from earlier work.**
- v201 (merged first): `admin_refresh.refresher_on()`, `market_values.total_meta`,
  `market_values.request_refresh`, MarketMeta (every key always present);
  `tests/admin_market/conftest.py` fixtures `market`, `session_is`,
  `refresher_on`, `on_client`; `tests/admin_market/test_page_loads_never_fetch.py`
  (`PAGE_LOAD_ENDPOINTS`, `FORBIDDEN`, fixtures `network_forbidden`, `book`);
  SPA `LiveValuesStore`, `overlayQuote`, `marketAgeLabel`, `sb-market-value`,
  `sb-market-refresh`, `MarketMeta`, `MarketStatus`, `MarketUpdates`.
- Part 1: `admin_refresh.SNAPSHOT_ANALYTICS`, `performance_key`,
  `equity_curve_key`, `calendar_key`, `calendar_months`, `is_snapshot_key`;
  `tests/admin_snapshots/golden_book.py` (`golden_book`, `golden_payload`,
  `assert_matches_golden`, `GOLDEN_MONTH`, plus `admin_app`, `client`,
  `_clear_login_limiter` re-exported).
- Part 2: `admin_snapshots.SNAPSHOT_ROUTES`, `admin_snapshots._fx_inputs(tickers, *, on)`,
  `admin_snapshots.build_inputs`, `admin_snapshots._now`; `page_bodies.performance_body`,
  `equity_curve_body`, `calendar_body` **only** for routes V204-2 marked
  `snapshot` (V204-14 Step 1 handles either outcome).
- Part 3 (V204-11; the `/market/updates` `snapshots` list and the refresh snapshots body are V204-11b): `market_values.read_snapshot(key, *, now=None) -> dict` and
  `market_values.snapshot_meta(snap, *, extra_missing=0) -> dict` (index
  "Request-path door additions"); `request_refresh(..., snapshots=...)`.

**Call-time lookup rule.** Every route below reaches the door as
`market_values.read_snapshot(...)`, `market_values.snapshot_meta(...)` and
`market_values.request_refresh(...)` through `from swingbot.admin import market_values`
(never `from ... import read_snapshot`), and `SNAPSHOT_ROUTES` as
`admin_snapshots.SNAPSHOT_ROUTES`. The tests monkeypatch those module
attributes, so both V204-2 outcomes are exercised whatever the verdict was.

**Payload shapes from part 2 the SPA must survive.** With no overlapping pair,
Risk's `correlation` is `{"labels": [...], "values": null, "reason": "insufficient_overlap"}`;
`availability["beta_spy"]` may be the string `"zero_variance"` instead of a
status object. V204-15 types both and gives part 5 one helper to render them as
"unavailable" with the reason, never as 0.

---

# Phase 4a: request routes read their snapshots (V204-13, V204-14)

### Task V204-13: Sparkline, `/analytics/snapshot` and the strategies registry read `analytics.snapshot`; request-time `refresh_snapshot` guard

**Model:** sonnet — three small call-site swaps behind one shared reader, against fixed door contracts and fake-backed tests; the kill-switch branch keeps today's code verbatim.

**Files:**
- Modify: `swingbot/admin/queries.py` (new `analytics_snapshot_read` and its two helpers; `_registry_rows` line ~209)
- Modify: `swingbot/admin/api_v1/analytics.py` (`_snapshot` 31-43, `analytics_snapshot` 45-50)
- Modify: `swingbot/admin/api_v1/dashboard.py` (`_equity_30d` 49-71)
- Modify: `tests/admin/test_api_v1_dashboard.py` (`test_equity_sparkline_is_numbers_not_svg`, shape only)
- Create: `tests/admin_snapshots/test_sparkline_and_snapshot_route.py`, `tests/admin_snapshots/test_no_request_refresh_snapshot.py`

**Interfaces:**
- Consumes: V204-11 `market_values.read_snapshot(key, *, now=None) -> dict`, `market_values.snapshot_meta(snap, *, extra_missing=0) -> dict`, `market_values.request_refresh(symbols, *, snapshots=(), priority=PRIORITY_USER) -> int`; V204-3 `admin_refresh.SNAPSHOT_ANALYTICS`; v201 `admin_refresh.refresher_on()`, `market_values.total_meta(quotes, *, extra_missing=0, now=None)`; part 1 `golden_payload`, `assert_matches_golden`, `admin_app`, `client`, `_clear_login_limiter`.
- Produces: `queries.analytics_snapshot_read(*, fresh: bool = False) -> tuple[dict, dict]` (the doc, never `None`, and its MarketMeta). `equity_30d` becomes `{"points": list[float], "change_pct": float | None, "market_meta": MarketMeta | None}`. The `/analytics/snapshot` body is the snapshot doc plus `"market_meta": MarketMeta`. V204-17 (part 5) reads both. For V204-14 (tests only): the `snapshot_rows` fixture and `stored(key, doc, ...)` helper in `tests/admin_snapshots/test_sparkline_and_snapshot_route.py`.

**Behaviour fixed here:**
- **One reader, `queries.analytics_snapshot_read(*, fresh=False)`.** It returns `_snapshot_read_on(fresh)` when `admin_refresh.refresher_on()`, else `_snapshot_read_off(fresh)`. After this task `_snapshot_read_off` is the only function in `swingbot/admin` that names `refresh_snapshot`.
  - **`_snapshot_read_on(fresh) -> tuple[dict, dict]`:** when `fresh`, first `market_values.request_refresh([], snapshots=[admin_refresh.SNAPSHOT_ANALYTICS])`. Then `snap = market_values.read_snapshot(admin_refresh.SNAPSHOT_ANALYTICS)` and return `(snap["doc"] or {}, market_values.snapshot_meta(snap))`. It never calls `load_snapshot`, `refresh_snapshot`, `compute_snapshot` or any `admin_snapshots.build_*`. An absent row returns `({}, meta)` with `meta["refreshing"] is True` (the door enqueued the key).
  - **`_snapshot_read_off(fresh) -> tuple[dict, dict]`** (kill switch): today's `_snapshot` logic through this module's own top-level names `load_snapshot`/`refresh_snapshot`, which existing tests patch (`tests/admin/test_badge_decay_surface.py:88`). `fresh` → `refresh_snapshot()` then `doc = load_snapshot(max_age_seconds=3600) or {}`; else `doc = load_snapshot(max_age_seconds=3600) or refresh_snapshot() or {}`. The meta is `{**market_values.total_meta([]), "as_of": built, "computed_at": built}` with `built = doc.get("built_at")`; `source` stays `"request"`.
  - Import `admin_refresh` and `market_values` lazily inside the helpers, as modules (the part's call-time lookup rule).
- **`_snapshot(fresh=False)`** in `api_v1/analytics.py` returns `queries.analytics_snapshot_read(fresh=fresh)[0]`. `analytics_calibration` keeps calling it unchanged. The lazy `from swingbot.core.analytics.snapshots import ...` line goes.
- **`analytics_snapshot()`**: `doc, meta = analytics_snapshot_read(fresh=request.args.get("fresh") == "1")`, then `jsonify({**doc, "market_meta": meta})`.
- **`_equity_30d()`**: inside today's `try`, `snap, meta = analytics_snapshot_read()` replaces the `load_snapshot(...) or refresh_snapshot()` line and its import. The points expression and `change_pct` are unchanged. The `except Exception` branch sets `points, meta = [], None` (today it swallowed too). It returns `{"points": points, "change_pct": change, "market_meta": meta}`. With the refresher on, an absent row gives empty points **with** `market_meta.refreshing = True`: no rebuild, and no silent empty series.
- **`_registry_rows()`**: `snap, _meta = analytics_snapshot_read()` replaces its first line. The rest is unchanged.

- [ ] **Step 1: Check the preconditions**

Run: `git -C <wt> grep -n "def read_snapshot\|def snapshot_meta" swingbot/admin/market_values.py` and `git -C <wt> grep -n "SNAPSHOT_ANALYTICS =" swingbot/core/marketdata/shared/admin_refresh.py`
Expected: three hits. A miss means V204-11 or V204-3 is not in the worktree: stop and report `BLOCKED: V204-11 not merged`.

- [ ] **Step 2: Write the failing route tests** in `tests/admin_snapshots/test_sparkline_and_snapshot_route.py`

```python
"""v204 V204-13: the sparkline, /analytics/snapshot and the registry read the analytics.snapshot row."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.admin import market_values, queries
from swingbot.admin.api_v1 import dashboard as dashboard_api
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin.test_badge_decay_surface import _reg
from tests.admin_snapshots.golden_book import (  # noqa: F401
    _clear_login_limiter, admin_app, assert_matches_golden, client, golden_payload)

COMPUTED = "2026-10-29T14:30:00+00:00"
LOGIN = {"username": "admin", "password": "admin"}
REBUILDERS = (
    "swingbot.core.analytics.snapshots.refresh_snapshot",
    "swingbot.core.analytics.snapshots.compute_snapshot",
    "swingbot.core.analytics.snapshots.load_snapshot",
    "swingbot.admin.queries.refresh_snapshot",
    "swingbot.admin.queries.load_snapshot",
)


def stored(key, doc, *, computed_at=COMPUTED, refreshing=False, error=None, fx_as_of=None):
    """A row as V204-11's read_snapshot returns it. V204-14 imports this helper."""
    return {"key": key, "doc": doc, "computed_at": computed_at, "stale_inputs": False,
            "refreshing": refreshing, "error": error,
            "inputs": {"computed_at": computed_at, "oldest_quote_as_of": None, "oldest_fx_as_of": fx_as_of,
                       "missing": {"quotes": [], "fx": [], "bars": {}}}}


@pytest.fixture
def snapshot_rows(monkeypatch):
    """A fake door with the refresher on: rows by key, every read and refresh recorded.
    V204-14 imports this fixture together with `stored`."""
    rows, reads, refreshes = {}, [], []

    def read(key, *, now=None):
        reads.append(key)
        return rows.get(key) or {"key": key, "doc": None, "inputs": None, "computed_at": None,
                                 "stale_inputs": False, "refreshing": True, "error": None}

    def refresh(symbols, *, snapshots=(), priority=0):
        refreshes.append((list(symbols), list(snapshots)))
        return len(list(snapshots))

    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(market_values, "read_snapshot", read)
    monkeypatch.setattr(market_values, "request_refresh", refresh)
    return SimpleNamespace(rows=rows, reads=reads, refreshes=refreshes)


@pytest.fixture
def no_rebuild(monkeypatch):
    calls = []
    for target in REBUILDERS:
        monkeypatch.setattr(target, lambda *a, _t=target, **k: calls.append(_t))
    return calls


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=LOGIN)
    return client


def test_sparkline_reads_the_stored_row_and_matches_golden(snapshot_rows, no_rebuild):
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(
        ar.SNAPSHOT_ANALYTICS, golden_payload("analytics_snapshot"))
    body = dashboard_api._equity_30d()
    assert_matches_golden("sparkline", body)
    assert body["market_meta"]["source"] == "snapshot"
    assert body["market_meta"]["computed_at"] == COMPUTED
    assert no_rebuild == []


def test_sparkline_without_a_row_is_empty_and_refreshing_never_rebuilt(snapshot_rows, no_rebuild):
    body = dashboard_api._equity_30d()
    assert body["points"] == [] and body["change_pct"] is None
    assert body["market_meta"]["refreshing"] is True
    assert snapshot_rows.reads == [ar.SNAPSHOT_ANALYTICS]
    assert no_rebuild == []


def test_snapshot_route_forwards_the_row_with_its_meta(logged_in, snapshot_rows, no_rebuild):
    doc = {"overall": {"n": 3}, "equity_curve": {"points": []}}
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(ar.SNAPSHOT_ANALYTICS, doc)
    body = logged_in.get("/api/v1/analytics/snapshot").get_json()
    meta = body.pop("market_meta")
    assert body == doc
    assert meta["source"] == "snapshot" and meta["refreshing"] is False
    assert no_rebuild == []


def test_snapshot_route_with_no_row_is_empty_and_refreshing(logged_in, snapshot_rows, no_rebuild):
    body = logged_in.get("/api/v1/analytics/snapshot").get_json()
    assert set(body) == {"market_meta"} and body["market_meta"]["refreshing"] is True
    assert no_rebuild == []


def test_fresh_enqueues_the_snapshot_and_never_rebuilds(logged_in, snapshot_rows, no_rebuild):
    assert logged_in.get("/api/v1/analytics/snapshot?fresh=1").status_code == 200
    assert snapshot_rows.refreshes == [([], [ar.SNAPSHOT_ANALYTICS])]
    assert no_rebuild == []


def test_registry_rows_read_the_stored_row(snapshot_rows, no_rebuild, monkeypatch):
    monkeypatch.setattr(queries, "load_registry", lambda: _reg("2019-01-01"))
    snapshot_rows.rows[ar.SNAPSHOT_ANALYTICS] = stored(ar.SNAPSHOT_ANALYTICS, {
        "by": {"strategy": [{"key": "Fibonacci", "n": 7, "win_rate": 80.0}]},
        "calibration": {"drift": []}})
    rows = queries._registry_rows()
    assert rows[0]["live_n"] == 7 and rows[0]["live_wr"] == 80.0
    assert no_rebuild == []


def test_kill_switch_off_keeps_the_file_path_and_adds_a_request_meta(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    calls = []
    monkeypatch.setattr(queries, "load_snapshot", lambda max_age_seconds=3600: None)
    monkeypatch.setattr(queries, "refresh_snapshot", lambda: calls.append("refresh"))
    body = dashboard_api._equity_30d()
    assert calls == ["refresh"]                      # today's request-time rebuild, behind the flag
    assert body["points"] == [] and body["market_meta"]["source"] == "request"


def test_kill_switch_off_meta_carries_the_file_build_time(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    built = "2026-10-29T13:00:00+00:00"
    monkeypatch.setattr(queries, "load_snapshot",
                        lambda max_age_seconds=3600: {"built_at": built, "overall": {}})
    doc, meta = queries.analytics_snapshot_read()
    assert doc["built_at"] == built
    assert meta["computed_at"] == built and meta["as_of"] == built
    assert meta["source"] == "request" and meta["refreshing"] is False
```

`_reg` (`tests/admin/test_badge_decay_surface.py:21`) is a plain helper, so importing it collects no extra tests. If `active_rows` drops the `_reg` record because it lacks a field the v162 source filter needs, patch `queries.active_rows` to `lambda rows: rows` in that one test.

- [ ] **Step 3: Write the failing guard** in `tests/admin_snapshots/test_no_request_refresh_snapshot.py`

```python
"""v204 V204-13: no request-time caller rebuilds the analytics snapshot while the refresher is on.

Spec Panel amendments and Brief corrections: the guard names every request-time
caller -- api_v1/analytics.py `_snapshot`, api_v1/dashboard.py `_equity_30d`
and queries.py `_registry_rows` -- and an AST scan fails on any new one."""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

from swingbot import config
from swingbot.admin import market_values, queries

ROOT = Path(__file__).resolve().parents[2]
GUARDED = [
    ("swingbot.admin.api_v1.analytics", "_snapshot", {}),
    ("swingbot.admin.api_v1.analytics", "_snapshot", {"fresh": True}),
    ("swingbot.admin.api_v1.dashboard", "_equity_30d", {}),
    ("swingbot.admin.queries", "_registry_rows", {}),
]
REBUILDERS = [
    ("swingbot.core.analytics.snapshots", "refresh_snapshot"),
    ("swingbot.core.analytics.snapshots", "compute_snapshot"),
    ("swingbot.admin.queries", "refresh_snapshot"),
    ("swingbot.core.analytics.admin_snapshots", "build_analytics_snapshot"),
]


@pytest.fixture
def rebuilds(monkeypatch):
    calls: list[str] = []
    for module, name in REBUILDERS:
        def boom(*a, _n=f"{module}.{name}", **k):
            calls.append(_n)
            raise AssertionError(f"request-time snapshot rebuild: {_n}")
        monkeypatch.setattr(importlib.import_module(module), name, boom)
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(market_values, "read_snapshot", lambda key, *, now=None: {
        "key": key, "doc": None, "inputs": None, "computed_at": None,
        "stale_inputs": False, "refreshing": True, "error": None})
    monkeypatch.setattr(market_values, "request_refresh", lambda *a, **k: 0)
    monkeypatch.setattr(queries, "load_registry", lambda: [])
    return calls


@pytest.mark.parametrize("module, name, kwargs", GUARDED)
def test_request_time_caller_never_rebuilds_when_on(rebuilds, module, name, kwargs):
    getattr(importlib.import_module(module), name)(**kwargs)
    assert rebuilds == []


def _functions_naming(path: Path, symbol: str) -> set[str]:
    found = set()
    for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Name) and node.id == symbol) or \
               (isinstance(node, ast.Attribute) and node.attr == symbol) or \
               (isinstance(node, ast.alias) and node.name == symbol):
                found.add(fn.name)
    return found


def test_only_the_kill_switch_reader_names_refresh_snapshot_in_the_admin_package():
    hits = {}
    for path in sorted((ROOT / "swingbot" / "admin").rglob("*.py")):
        names = _functions_naming(path, "refresh_snapshot")
        if names:
            hits[path.relative_to(ROOT).as_posix()] = names
    assert hits == {"swingbot/admin/queries.py": {"_snapshot_read_off"}}


def test_the_shared_reader_branches_on_the_kill_switch():
    source = inspect.getsource(queries.analytics_snapshot_read)
    assert "refresher_on()" in source and "_snapshot_read_off" in source
```

- [ ] **Step 4: Update the dashboard shape** in `tests/admin/test_api_v1_dashboard.py`, `test_equity_sparkline_is_numbers_not_svg` only (`assert_shape` is exact, so the new key must be declared):

```python
    assert_shape(equity, {"points": list, "change_pct": NULLABLE_NUMBER,
                          "market_meta": (dict, type(None))}, where="equity_30d")
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_sparkline_and_snapshot_route.py`, then `... file tests/admin_snapshots/test_no_request_refresh_snapshot.py`, then `... file tests/admin/test_api_v1_dashboard.py`
Expected: FAIL: `KeyError: 'market_meta'`, `AttributeError: ... has no attribute 'analytics_snapshot_read'`, the rebuild recorder firing on `refresh_snapshot`, and the AST scan listing `_snapshot`, `_equity_30d` and `_registry_rows`.

- [ ] **Step 6: Implement** `queries.analytics_snapshot_read`, `_snapshot_read_on`, `_snapshot_read_off` and the three call-site swaps exactly as fixed above. Keep `queries.py`'s top-level `from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot`; the off path and existing tests use those names. The AST scan counts the module-level import as no function, so it stays allowed.

- [ ] **Step 7: Run the tests to verify they pass, plus today's callers**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_sparkline_and_snapshot_route.py`, `... file tests/admin_snapshots/test_no_request_refresh_snapshot.py`, `... file tests/admin/test_api_v1_dashboard.py`
Expected: PASS, `0 failed`.
Run: `... file tests/admin/test_badge_decay_surface.py`, `... file tests/backtesting/test_registry_data_source.py`, `... file tests/admin/test_api_v1_analytics.py`, `... file tests/admin_snapshots/test_golden_today.py`
Expected: PASS with assertions unchanged (the off path is today's code).
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add swingbot/admin/queries.py swingbot/admin/api_v1/analytics.py swingbot/admin/api_v1/dashboard.py tests/admin/test_api_v1_dashboard.py tests/admin_snapshots/test_sparkline_and_snapshot_route.py tests/admin_snapshots/test_no_request_refresh_snapshot.py
git -C <wt> commit -m "feat(v204): sparkline, analytics snapshot and registry read the stored snapshot"
```

### Task V204-14: Analytics default/filtered and Calendar routes: snapshot or never-fetch request, both with `market_meta`; page-load no-network test

**Model:** opus — routing per V204-2's verdict with both outcomes live in tests, a fallback that must never read as zero, and the page-load guard that proves spec Goal 1 for Risk, Analytics and Calendar together.

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance` ~165, `analytics_equity_curve` ~312; new `default_view_body`, `request_market_meta`, `_closed_tickers`, `_ledger_default_key`; `_performance_body`, `_equity_curve_body`)
- Modify: `swingbot/admin/api_v1/calendar.py` (`calendar_pnl` 71-107; new `_calendar_default_key`, `_calendar_body`)
- Modify (created by v201 V201-8, merged before V204-1): `tests/admin_market/test_page_loads_never_fetch.py` (append endpoints; extend `FORBIDDEN` and `network_forbidden`)
- Modify (shape only, `assert_shape` is exact): `tests/admin/test_api_v1_analytics.py` (~line 83), `tests/admin/test_api_analytics.py` (~line 186), `tests/admin/test_api_v1_calendar.py` (`test_response_shape`, ~line 72)
- Create: `tests/admin_snapshots/test_analytics_calendar_routes.py`

**Interfaces:**
- Consumes: V204-11 `market_values.read_snapshot`, `snapshot_meta`; V204-8 `admin_snapshots.SNAPSHOT_ROUTES`, `admin_snapshots._fx_inputs(tickers, *, on) -> tuple[dict, list[str]]`, `admin_snapshots.build_inputs`, `admin_snapshots._now`, and `page_bodies.performance_body`/`equity_curve_body`/`calendar_body` where they exist; V204-5 `daily_readonly.DailyCacheUnavailable`; V204-3 `admin_refresh.performance_key`, `equity_curve_key`, `calendar_key`, `calendar_months`; v201 `admin_refresh.refresher_on()`, `market_values.total_meta`; `scope.BookScope`, `closed_only`; `swingbot.core.infra.swallowed.swallowed`; V204-13 test helpers `snapshot_rows`, `stored`, `logged_in`; part 1 `golden_book`, `assert_matches_golden`, `GOLDEN_MONTH`.
- Produces: every `/analytics/performance`, `/analytics/equity-curve` and `/calendar/pnl` body gains `"market_meta": MarketMeta` (index ledger row V204-14). `analytics.default_view_body(route: str, key: str | None, compute: Callable[[], dict]) -> dict` and `analytics.request_market_meta(*, fx_missing: int, tickers: Iterable[str], refreshing: bool = False, error: str | None = None) -> dict` (used by `calendar.py`; nothing outside the two route modules).

**Behaviour fixed here:**
- **One body function per route, whatever V204-2 decided.** `analytics._performance_body(scope) -> dict`, `analytics._equity_curve_body(scope) -> dict` and `calendar._calendar_body(month: str, filters: tuple[str | None, str | None]) -> dict` always exist after this task.
  - Route marked `snapshot` (V204-8 moved its body): the name is a module-level alias, `_performance_body = page_bodies.performance_body` (likewise the others).
  - Route marked `request`: extract today's body **unchanged** into that function in the same module: from `tl = TradeLog()` (calendar: `everything = pc.load_rows(...)`) to the dict passed to `jsonify`, which it returns. `scope`, `month` and `filters` arrive as arguments (calendar: `strategy, horizon = filters`). This is a move with no behaviour change, so complexity moves with it.
- **Default-view keys.** `_ledger_default_key(route: str, scope: BookScope) -> str | None` returns `admin_refresh.performance_key(scope.ledger)` (route `"analytics.performance"`) or `admin_refresh.equity_curve_key(scope.ledger)` (route `"analytics.equity_curve"`) when `scope == BookScope(ledger=scope.ledger)`, so no date, strategy, horizon, direction or origin filter is set. Otherwise it returns `None`. Use a two-entry dict, not an `if` chain. `calendar._calendar_default_key(month, filters) -> str | None` is `admin_refresh.calendar_key(month)` when `filters == (None, None)` and `month in admin_refresh.calendar_months()`, else `None`.
- **`default_view_body(route, key, compute)`:**
  1. When `key is not None`, `admin_refresh.refresher_on()` and `route in admin_snapshots.SNAPSHOT_ROUTES`: `snap = market_values.read_snapshot(key)`. A stored doc returns `{**snap["doc"], "market_meta": market_values.snapshot_meta(snap)}` and `compute` is never called.
  2. Otherwise, or when the row has no doc yet: `body = compute()`, then `body["market_meta"] = request_market_meta(fx_missing=int(body.get("fx_missing_count") or 0), tickers=_closed_tickers(), refreshing=snap is not None, error=snap["error"] if snap else None)`. An absent row (first boot, new month) therefore serves the request-time body, which never fetches when on, with `refreshing: true`. It is never an empty body of zeros and never a snapshot build.
- **`request_market_meta`** starts from `market_values.total_meta([], extra_missing=fx_missing)`, so `missing_count` and `incomplete` carry the FX rows the body left unconverted. `as_of` is `admin_snapshots.build_inputs(computed_at=admin_snapshots._now(), fx=fx_map)["oldest_fx_as_of"]` with `fx_map, _ = admin_snapshots._fx_inputs(list(tickers), on=admin_snapshots._now().date())`. A `DailyCacheUnavailable` leaves `as_of` at `None` ("unknown", never "now") and is logged with `swallowed(log, "admin.analytics.fx_as_of", exc)`. `refreshing` is OR-ed in and `error` is set when given. `source` stays `"request"`.
- **`_closed_tickers() -> list[str]`**: the sorted unique tickers of `closed_only(_all_trades(TradeLog()))`.
- **Routes.** `analytics_performance`: `scope = _scope()`, then `return jsonify(default_view_body("analytics.performance", _ledger_default_key("analytics.performance", scope), lambda: _performance_body(scope)))`. `analytics_equity_curve` follows the same pattern. `calendar_pnl`: `_reject_unknown_params()`, `month = _month_param()`, `filters = _filter_args()`, then `default_view_body("calendar.pnl", _calendar_default_key(month, filters), lambda: _calendar_body(month, filters))`, with `default_view_body` imported lazily from `.analytics`.
- **The kill switch is the same code.** With the refresher off, step 1 never runs, so the body is today's plus `market_meta`. The off-path golden payloads still match.

- [ ] **Step 1: Read V204-2's outcome**

Run: `git -C <wt> grep -n "def performance_body\|def equity_curve_body\|def calendar_body" swingbot/core/analytics/page_bodies.py` and `git -C <wt> grep -n "SNAPSHOT_ROUTES" swingbot/core/analytics/admin_snapshots.py`
Expected: a hit for each route V204-2 marked `snapshot` (no file at all when it marked none). Write down which bodies get an alias and which get extracted. A body moved to `page_bodies` for a route **not** in `SNAPSHOT_ROUTES`, or the other way round, means V204-8 is inconsistent: stop and report `BLOCKED: page_bodies and SNAPSHOT_ROUTES disagree`.

- [ ] **Step 2: Write the failing route tests** in `tests/admin_snapshots/test_analytics_calendar_routes.py`

```python
"""v204 V204-14: default Analytics and Calendar views read their snapshot; every other view
computes on request and never fetches; both carry market_meta. SNAPSHOT_ROUTES is patched,
so both V204-2 outcomes are tested whatever the measured verdict was."""
import pytest

from swingbot.admin import market_values
from swingbot.admin.api_v1 import analytics as analytics_api
from swingbot.admin.api_v1 import calendar as calendar_api
from swingbot.core.analytics import admin_snapshots
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_MONTH, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)
from tests.admin_snapshots.test_sparkline_and_snapshot_route import (  # noqa: F401
    logged_in, snapshot_rows, stored)

ALL_ROUTES = frozenset({"analytics.performance", "analytics.equity_curve", "calendar.pnl"})
CURRENT, PREVIOUS = ar.calendar_months()


@pytest.fixture
def all_snapshotted(monkeypatch, snapshot_rows):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", ALL_ROUTES)
    return snapshot_rows


@pytest.fixture
def no_compute(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("request-time body computed for a stored default view")
    monkeypatch.setattr(analytics_api, "_performance_body", boom)
    monkeypatch.setattr(analytics_api, "_equity_curve_body", boom)
    monkeypatch.setattr(calendar_api, "_calendar_body", boom)


@pytest.fixture
def fx_known(monkeypatch):
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", lambda tickers, *, on: (
        {"EUR": {"rate": 1.1, "as_of": "2026-10-27"}}, []))


@pytest.mark.parametrize("path, key", [
    ("/api/v1/analytics/performance", "analytics.performance:main"),
    ("/api/v1/analytics/performance?ledger=weak", "analytics.performance:weak"),
    ("/api/v1/analytics/equity-curve?ledger=both", "analytics.equity_curve:both"),
    (f"/api/v1/calendar/pnl?month={CURRENT}", f"calendar.pnl:{CURRENT}"),
    (f"/api/v1/calendar/pnl?month={PREVIOUS}", f"calendar.pnl:{PREVIOUS}"),
])
def test_default_view_serves_its_stored_row(logged_in, all_snapshotted, no_compute, path, key):
    all_snapshotted.rows[key] = stored(key, {"sentinel": key}, fx_as_of="2026-10-28")
    body = logged_in.get(path).get_json()
    meta = body.pop("market_meta")
    assert body == {"sentinel": key}
    assert meta["source"] == "snapshot" and meta["as_of"] == "2026-10-28"
    assert all_snapshotted.reads == [key]


@pytest.mark.parametrize("path", [
    "/api/v1/analytics/performance?ledger=main&strategy=Fibonacci",
    "/api/v1/analytics/equity-curve?from=2026-01-01",
    "/api/v1/calendar/pnl?month=2025-01",
    f"/api/v1/calendar/pnl?month={CURRENT}&strategy=Fibonacci",
])
def test_filtered_or_older_view_computes_on_request(logged_in, all_snapshotted, fx_known, path):
    resp = logged_in.get(path)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    meta = resp.get_json()["market_meta"]
    assert all_snapshotted.reads == []
    assert meta["source"] == "request" and meta["as_of"] == "2026-10-27"
    assert meta["refreshing"] is False


def test_route_not_marked_snapshot_never_reads_a_row(logged_in, snapshot_rows, fx_known, monkeypatch):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", frozenset())
    body = logged_in.get("/api/v1/analytics/performance").get_json()
    assert snapshot_rows.reads == []
    assert "totals" in body and body["market_meta"]["source"] == "request"


def test_absent_row_serves_the_request_body_refreshing(logged_in, all_snapshotted, fx_known):
    body = logged_in.get("/api/v1/analytics/performance").get_json()
    assert all_snapshotted.reads == ["analytics.performance:main"]
    assert "totals" in body                                   # the real body, never zeros
    assert body["market_meta"]["source"] == "request"
    assert body["market_meta"]["refreshing"] is True


def test_request_meta_counts_unconverted_rows_never_zero(logged_in, snapshot_rows, fx_known,
                                                          monkeypatch):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", frozenset())
    monkeypatch.setattr(analytics_api, "_performance_body", lambda scope: {"fx_missing_count": 2})
    meta = logged_in.get("/api/v1/analytics/performance?strategy=Fibonacci").get_json()["market_meta"]
    assert meta["missing_count"] == 2 and meta["incomplete"] is True


def test_unmounted_bar_cache_leaves_the_fx_as_of_unknown(logged_in, snapshot_rows, monkeypatch):
    def unmounted(tickers, *, on):
        raise DailyCacheUnavailable("daily bar cache /data/market_data is not mounted")
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", unmounted)
    resp = logged_in.get("/api/v1/calendar/pnl?month=2025-01")
    assert resp.status_code == 200 and resp.get_json()["market_meta"]["as_of"] is None


@pytest.mark.parametrize("name, path", [
    ("performance_main", "/api/v1/analytics/performance?ledger=main"),
    ("equity_curve_main", "/api/v1/analytics/equity-curve?ledger=main"),
    ("calendar_pnl", f"/api/v1/calendar/pnl?month={GOLDEN_MONTH}"),
])
def test_kill_switch_off_serves_today_bodies_with_a_request_meta(golden_book, monkeypatch, name, path):
    monkeypatch.setattr(admin_snapshots, "SNAPSHOT_ROUTES", ALL_ROUTES)
    reads = []
    monkeypatch.setattr(market_values, "read_snapshot", lambda key, **k: reads.append(key))
    body = golden_book.client.get(path).get_json()
    assert_matches_golden(name, body)
    assert body["market_meta"]["source"] == "request"
    assert reads == []
```

- [ ] **Step 3: Extend the page-load guard** in `tests/admin_market/test_page_loads_never_fetch.py`

Append to `PAGE_LOAD_ENDPOINTS` (the endpoints the Risk, Analytics overview and Calendar pages call on load, plus one filtered view and one older month):

```python
    "/api/v1/risk",
    "/api/v1/analytics/snapshot",
    "/api/v1/analytics/performance",
    "/api/v1/analytics/equity-curve",
    "/api/v1/calendar/pnl",
    "/api/v1/analytics/performance?strategy=Fibonacci",
    "/api/v1/calendar/pnl?month=2025-01",
```

Append to `FORBIDDEN` (v204's additions to v201's list, index Global Constraints):

```python
    ("swingbot.core.marketdata.data", "get_daily_data"),
    ("swingbot.admin.freshness", "_daily_for"),
    ("swingbot.core.analytics.snapshots", "compute_snapshot"),
    ("swingbot.admin.queries", "refresh_snapshot"),
```

At the end of the `network_forbidden` fixture, before `return calls`, add the two patches a fixed `(module, name)` list cannot express:

```python
    from swingbot.core.analytics import admin_snapshots
    from swingbot.core.marketdata import fx

    for name in sorted(n for n in dir(admin_snapshots) if n.startswith("build_") and n != "build_inputs"):
        def build_boom(*args, _name=f"admin_snapshots.{name}", **kwargs):
            calls.append(_name)
            raise AssertionError(f"snapshot build on a page load: {_name}")
        monkeypatch.setattr(admin_snapshots, name, build_boom)

    real_code = fx.quote_currency_code
    fetch_default = inspect.signature(real_code).parameters["fetch"].default

    def code_without_fetch(ticker, *args, **kwargs):
        if kwargs.get("fetch", fetch_default):
            calls.append("fx.quote_currency_code(fetch=True)")
            raise AssertionError("quote currency fetched on a page load")
        return real_code(ticker, *args, **kwargs)
    monkeypatch.setattr(fx, "quote_currency_code", code_without_fetch)
```

Add `import inspect` at the top. `build_inputs` is pure, and `request_market_meta` uses it, so it stays callable.

- [ ] **Step 4: Declare the new key in the three exact-shape tests**

In `tests/admin/test_api_v1_analytics.py` (the `/api/v1/analytics/performance` shape, ~line 83), in `tests/admin/test_api_analytics.py` (the body shape, ~line 186) and in `tests/admin/test_api_v1_calendar.py` `test_response_shape` (~line 72), add one entry to the existing dict: `"market_meta": dict,`. Change nothing else in those files.

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_analytics_calendar_routes.py`
Expected: FAIL (`KeyError: 'market_meta'`; `AttributeError` on `_performance_body` for a route V204-2 marked `request`).
Run: `... file tests/admin_market/test_page_loads_never_fetch.py`
Expected: FAIL on the new Analytics and Calendar endpoints: the `market_meta` work is missing, and any remaining request-time fetch shows up in the recorded list. `/api/v1/risk` and `/api/v1/analytics/snapshot` should already pass, since V204-12 and V204-13 are merged. If they fail, report which forbidden name fired; do not weaken the list.

- [ ] **Step 6: Implement** the body functions (alias or unchanged extraction, per Step 1), `_ledger_default_key`, `_calendar_default_key`, `_closed_tickers`, `request_market_meta`, `default_view_body` and the three route edits, exactly as fixed above. Use the module-attribute lookups from this part's call-time lookup rule. `default_view_body` and `request_market_meta` each stay well under complexity 15. Split the "stored doc" branch into `_stored_view(route, key) -> dict | None` (`None` when step 1 does not apply) if needed.

- [ ] **Step 7: Run the tests to verify they pass, plus today's route tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_snapshots/test_analytics_calendar_routes.py`, `... file tests/admin_market/test_page_loads_never_fetch.py`
Expected: PASS, `0 failed`, and `network_forbidden == []` for every endpoint.
Run: `... file tests/admin/test_api_v1_analytics.py`, `... file tests/admin/test_api_analytics.py`, `... file tests/admin/test_api_v1_calendar.py`, `... file tests/admin/test_api_v1_money.py`, `... file tests/admin_snapshots/test_golden_today.py`, `... file tests/admin_snapshots/test_file_producer_parity.py`, `... file tests/admin_snapshots/test_build_analytics.py`
Expected: PASS. Only the three shape dicts changed.
Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean (an extracted body keeps the complexity it had as a route).

- [ ] **Step 8: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/analytics.py swingbot/admin/api_v1/calendar.py tests/admin_market/test_page_loads_never_fetch.py tests/admin/test_api_v1_analytics.py tests/admin/test_api_analytics.py tests/admin/test_api_v1_calendar.py tests/admin_snapshots/test_analytics_calendar_routes.py
git -C <wt> commit -m "feat(v204): analytics and calendar default views read snapshots; market_meta; page-load guard"
```

# Phase 4b: SPA primitives (V204-15)

### Task V204-15: SPA primitives: snapshot models, live snapshot updates, snapshot age tone, refresh with snapshots, `followSnapshot`, lower-bound and P&L-basis labels

**Model:** sonnet — leaf functions, one store extension and three small input additions against a fixed JSON contract, each pinned by a spec written first.

**Files:**
- Modify: `frontend/src/app/api/models.ts`, `frontend/src/app/api/api-client.ts`
- Modify (created by v201 V201-16, merged before V204-1): `frontend/src/app/stores/live-values.store.ts`, `live-values.store.spec.ts`
- Modify: `frontend/src/app/ui/age-hint.ts`, `age-hint.spec.ts`, `ui/market-value.ts`, `market-value.spec.ts`, `ui/market-refresh.ts`, `market-refresh.spec.ts`
- Create: `frontend/src/app/stores/snapshot-follow.ts`, `snapshot-follow.spec.ts`, `frontend/src/app/ui/lower-bound.ts`, `lower-bound.spec.ts`, `frontend/src/app/ui/pnl-basis.ts`, `pnl-basis.spec.ts`
- Modify (one guard, so `ng build` stays green once `Correlation.values` is nullable): `frontend/src/app/workspaces/risk/risk.ts`, the correlation `@if` at ~line 529

**Interfaces:**
- Consumes: the index's "SPA contract" and "Endpoints". The JSON comes from V204-11b (`/market/updates` `snapshots`, `status.stale_snapshot_s`; `/market/refresh` `snapshots`), V204-12 (Risk body additions), V204-13 and V204-14 (`market_meta` on the sparkline, Analytics and Calendar bodies). Part 2 shapes: `correlation.values: null` with `reason: "insufficient_overlap"`; `availability.beta_spy === "zero_variance"`. v201 V201-16: `LiveValuesStore` (`sync`, `local`, `LOCAL_REFRESH_TIMEOUT_MS`), `overlayQuote`, `marketAgeLabel`, `ageText`, `MarketValue`, `MarketRefresh`, `CLOCK`.
- Produces (index "SPA contract", exactly, plus three additive helpers marked *new*): `SnapshotUpdate`, `RiskBarsMeta`, `RiskFxMeta`, `RiskAccount` (*new* name for the `account` shape), the optional `Risk` and `market_meta` fields; `ApiClient.refreshMarket(body: {symbols: string[]; snapshots?: string[]})`; `LiveValuesStore.snapshot(key: string): Signal<SnapshotUpdate | null>`, `requestRefresh(symbols: string[], snapshots: string[] = [])`; `marketAgeLabel(asOf, nowMs, status, opts?: {kind?: 'price' | 'snapshot'; staleInputs?: boolean; computedAt?: string | null})`; `sb-market-value` inputs `kind`, `staleInputs`, `computedAt`; `sb-market-refresh` input `snapshots`; `followSnapshot(key, loadedAt, reload): EffectRef`, `snapshotMeta(meta, live): MarketMeta | null`; `lowerBoundLabel(value: string, missing: number): string | null`; `PNL_BASIS_LABEL`. *New:* `unavailableLabel(reason: string | null | undefined): string` and `availabilityReason(a: DomainAvailability | 'zero_variance' | null | undefined): string | null` in `ui/lower-bound.ts`; component `sb-pnl-basis` (`PnlBasis`) in `ui/pnl-basis.ts`. Part 5 renders with these.

**Behaviour fixed here:**
- **models.ts.**
  - `SnapshotUpdate {key: string; computed_at: string | null; stale_inputs: boolean; refreshing: boolean; error: string | null}`.
  - `MarketUpdates.snapshots?: SnapshotUpdate[]` and `MarketStatus.stale_snapshot_s?: number | null`. Both are optional, as v201 did for `RowQuoteFields`, so v201's spec literals and an older server still type-check. The store treats an absent value as `[]` or `null`.
  - `RiskBarsMeta {per_symbol: Record<string, string>; oldest: string | null; newest: string | null; stale_inputs: boolean; missing: {symbol: string; reason: string}[]}`, `RiskFxMeta {as_of: string | null; missing: string[]}`, `RiskAccount {balance: number | null; currency: string}`.
  - `Risk` gains the optional fields `market_meta?: MarketMeta`, `computed_at?: string | null`, `bars_meta?: RiskBarsMeta`, `fx_meta?: RiskFxMeta`, `lower_bound?: string[]` and `account?: RiskAccount`.
  - `Correlation` becomes `{labels: string[]; values: (number | null)[][] | null; reason?: string | null}`. `RiskAvailability` gains `beta_spy?: DomainAvailability | 'zero_variance'`.
  - `market_meta?: MarketMeta` goes on `EquitySeries`, `AnalyticsSnapshot`, `AnalyticsPerformance`, `AnalyticsEquityCurve` and `PnlCalendar`.
- **api-client.** `refreshMarket(body: {symbols: string[]; snapshots?: string[]})` posts the body as given.
- **LiveValuesStore.**
  - A `snapshots` signal map `Record<key, SnapshotUpdate>` is filled from `updates.snapshots ?? []` in the same merge as quotes (last one wins, keys kept as sent). `status` is unchanged.
  - Local marks use the key `'snapshot:<key>'` with the request time in ms.
  - `snapshot(key)` returns a memoised `computed`. While a local mark is set it is the stored update with `refreshing: true`, or the shell `{key, computed_at: null, stale_inputs: false, refreshing: true, error: null}` when nothing is stored. Otherwise it is the stored update or `null`.
  - A local snapshot mark clears when an update for that key arrives with an `error`, or with `refreshing === false` **and** `Date.parse(computed_at) >= the request time`. It also clears after `LOCAL_REFRESH_TIMEOUT_MS`, or when the POST errors. An older row arriving while the build is still queued does not stop the spinner. Quote marks keep v201's rule.
  - `requestRefresh(symbols, snapshots = [])` sets every local mark at once. It calls `refreshMarket({symbols})` when `snapshots` is empty, which is v201's exact body, and `refreshMarket({symbols, snapshots})` otherwise.
- **`marketAgeLabel`.** `kind` defaults to `'price'`, and the price path is v201's unchanged. For `kind: 'snapshot'`, **the clock is `opts.computedAt`; `asOf` is never read** (index note, commit 65b48fd4). Risk's FX `as_of` is a bare date, and an age taken from it would make Risk always stale. `as_of` is shown only as an input clock label by part 5. In order:
  1. `status?.heartbeat.stalled` → tone `'stalled'`, text `ageText(age)` (`null` when `computedAt` is null).
  2. `computedAt` null → `{text: null, tone: staleInputs ? 'stale' : 'fresh'}`.
  3. `status?.session === 'closed'`. When `staleInputs` or `Date.parse(computedAt) < Date.parse(status.last_close_at)`: `{text: 'as of <Ddd HH:MM> ET' (from computedAt), tone: 'stale'}`. Otherwise `{text: 'as of last close · <Ddd HH:MM> ET' (from last_close_at), tone: 'closed'}`. Reuse v201's ET formatter.
  4. Otherwise `age = (nowMs - Date.parse(computedAt)) / 1000`, tone `'stale'` when `staleInputs` or (`status?.stale_snapshot_s` is set and `age > it`), else `'fresh'`. Text `ageText(age)`.
- **`sb-market-value`** gains `kind = input<'price' | 'snapshot'>('price')`, `staleInputs = input(false)` and `computedAt = input<string | null>(null)`, passed through as `opts`. For a snapshot the value slot is hidden only when `computedAt` is null (not `asOf`). The markup and styles are unchanged.
- **`sb-market-refresh`** gains `snapshots = input<string[]>([])`. It is disabled when both lists are empty, and a click calls `requestRefresh(symbols(), snapshots())`. Update v201's spec expectation to `toHaveBeenCalledWith(['MSFT'], [])`.
- **`stores/snapshot-follow.ts`.**
  - `followSnapshot(key, loadedAt, reload)` must be called in an injection context. It injects `LiveValuesStore` and returns `effect(...)`. The effect reads `k = key()`, then `at = live.snapshot(k)()?.computed_at` and `loaded = loadedAt()`. When `k && at`, the pair `${k}@${at}` was not seen before, and (`loaded === null` or `Date.parse(at) > Date.parse(loaded)`), it records the pair and calls `untracked(reload)`. So each newer snapshot reloads once, and a page loaded from a request body (no `computed_at`) reloads once when its first snapshot lands.
  - `snapshotMeta(meta, live)` returns `null` for a null or undefined `meta` and `meta` itself when `live` is null. Otherwise it returns `{...meta, refreshing: meta.refreshing || live.refreshing, error: meta.error ?? live.error}`.
- **`ui/lower-bound.ts`.**
  - `lowerBoundLabel(value, missing)` returns `null` when `missing <= 0`, else `` `≥ ${value}, ${missing} position${missing === 1 ? '' : 's'} unpriced` ``.
  - `UNAVAILABLE_REASONS = {insufficient_overlap: 'fewer than 2 overlapping bars', zero_variance: 'benchmark did not move'}`. `unavailableLabel(reason)` returns `'unavailable'` for a null reason, `` `unavailable: ${UNAVAILABLE_REASONS[reason] ?? reason}` `` otherwise.
  - `availabilityReason(a)` returns `'zero_variance'` for that string, `a.reason ?? 'unavailable'` when `a?.state === 'unavailable'`, and `null` otherwise.
  - A null correlation or beta is therefore shown as "unavailable: …", never as 0.
- **`ui/pnl-basis.ts`.** `export const PNL_BASIS_LABEL = 'pre-tax, before modelled frictions'`. `sb-pnl-basis` renders `<span class="pnl-basis">{{ label }}</span>` with styles `font-size: var(--text-micro); color: var(--text-faint); white-space: normal; overflow-wrap: anywhere`, so on narrow widths it wraps under its figure and never widens a column.
- **risk.ts guard.** `@if (corr.labels.length) {` becomes `@if (corr.labels.length && corr.values) {`, which falls through to today's "Correlation data unavailable." branch. Part 5 (V204-16) adds the reason with `unavailableLabel`. This line is this task's only edit to that file.

- [ ] **Step 1: Write the failing specs**

`ui/age-hint.spec.ts`, a new `describe('marketAgeLabel snapshot')` reusing v201's `NOW` (`2026-10-31T15:00:00Z`, a Saturday) and a status helper with `stale_snapshot_s: 600`:

```ts
const sst = (session: 'regular' | 'extended' | 'closed', stalled = false): MarketStatus => ({
  session, last_close_at: '2026-10-30T20:00:00Z', stale_price_s: 120, stale_snapshot_s: 600,
  heartbeat: { beat_at: null, cadence_s: 30, stalled } });
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const snap = (computedAt: string | null, staleInputs = false) =>
  ({ kind: 'snapshot' as const, computedAt, staleInputs });

it('snapshot age comes from computed_at, never from a date-only as_of', () =>
  expect(marketAgeLabel('2026-10-28', NOW, sst('regular'), snap(ago(180))))
    .toEqual({ text: ageText(180), tone: 'fresh' }));
it('snapshot older than stale_snapshot_s is stale', () =>
  expect(marketAgeLabel(null, NOW, sst('regular'), snap(ago(700))).tone).toBe('stale'));
it('stale_inputs is stale whatever the age', () =>
  expect(marketAgeLabel(null, NOW, sst('extended'), snap(ago(5), true)).tone).toBe('stale'));
it('closed: built after the close reads as of last close', () =>
  expect(marketAgeLabel(null, NOW, sst('closed'), snap('2026-10-30T21:10:00Z')))
    .toEqual({ text: 'as of last close · Fri 16:00 ET', tone: 'closed' }));
it('closed: built before the close is stale with its own time', () =>
  expect(marketAgeLabel(null, NOW, sst('closed'), snap('2026-10-30T19:00:00Z')))
    .toEqual({ text: 'as of Fri 15:00 ET', tone: 'stale' }));
it('closed: stale_inputs is stale', () =>
  expect(marketAgeLabel(null, NOW, sst('closed'), snap('2026-10-30T21:10:00Z', true)).tone).toBe('stale'));
it('stalled wins over stale_inputs', () =>
  expect(marketAgeLabel(null, NOW, sst('regular', true), snap(ago(5), true)).tone).toBe('stalled'));
it('no computed_at gives no text', () =>
  expect(marketAgeLabel('2026-10-28', NOW, sst('regular'), snap(null))).toEqual({ text: null, tone: 'fresh' }));
```

`stores/live-values.store.spec.ts`: extend v201's harness, which has the fake `ApiClient`, the `FakeEventStream` and `vi.useFakeTimers()`. Add `vi.setSystemTime(Date.parse('2026-10-29T14:00:00Z'))` and a `reply(snapshots)` helper that answers `marketUpdates` with `{cursor: 'c1', quotes: [], snapshots, status}`. Cases, each written as real code:
- `merges snapshot updates by key`: reply `[{key: 'risk', computed_at: '2026-10-29T13:55:00Z', stale_inputs: false, refreshing: false, error: null}]` after `raise('market')`; `snapshot('risk')()` equals it.
- `a reply without snapshots (older server) changes nothing`: `snapshot('risk')()` is `null` and no error is thrown.
- `requestRefresh with snapshots marks them at once and posts both lists`: `requestRefresh([], ['risk'])` makes `snapshot('risk')()` equal `{key: 'risk', computed_at: null, stale_inputs: false, refreshing: true, error: null}`, and `refreshMarket` is called with `{symbols: [], snapshots: ['risk']}`.
- `requestRefresh with symbols only keeps v201's body`: `refreshMarket` is called with exactly `{symbols: ['NVDA']}`.
- `an older row does not stop a requested spinner`: request, then reply `refreshing: false, computed_at: '2026-10-29T13:55:00Z'`. `snapshot('risk')()?.refreshing` is still `true`.
- `a newer row stops it`: reply `computed_at: '2026-10-29T14:01:00Z', refreshing: false` → `refreshing` is `false`.
- `an error stops it`: reply `error: 'budget exceeded after 90s'` → `refreshing` is `false` and `error` is set.
- `the local snapshot mark clears after LOCAL_REFRESH_TIMEOUT_MS`.

`stores/snapshot-follow.spec.ts`: a fake `LiveValuesStore` with `snapshot = (k: string) => computed(() => map()[k] ?? null)` over a `signal<Record<string, SnapshotUpdate>>`, provided through `TestBed`; `followSnapshot` is created in `TestBed.runInInjectionContext`. Cases:

```ts
it('reloads once per newer computed_at', () => {
  const reload = vi.fn();
  const loaded = signal<string | null>('2026-10-29T14:00:00Z');
  TestBed.runInInjectionContext(() => followSnapshot(() => 'risk', loaded, reload));
  push('risk', '2026-10-29T14:00:00Z'); TestBed.tick();
  expect(reload).not.toHaveBeenCalled();                    // same as loaded
  push('risk', '2026-10-29T14:05:00Z'); TestBed.tick();
  expect(reload).toHaveBeenCalledTimes(1);
  loaded.set('2026-10-29T14:05:00Z'); TestBed.tick();
  expect(reload).toHaveBeenCalledTimes(1);                  // its own reload does not loop
});
it('a request-sourced page reloads once when its first snapshot lands', () => { /* loaded null, one push → 1 call; same push again → still 1 */ });
it('a null key follows nothing', () => { /* key () => null, push → 0 calls */ });
it('a new key (another month) is followed on its own', () => { /* switch key signal, push for the new key → reload */ });
```

Write each commented case out in full. Then test `snapshotMeta`. It returns `null` for `undefined`. With `live` null it returns the same object. It ORs `refreshing`. It keeps the meta's own error and takes the live error only when the meta has none.

`ui/lower-bound.spec.ts`: `lowerBoundLabel('$1,200', 0)` → `null`; `1` → `'≥ $1,200, 1 position unpriced'`; `3` → `'≥ $1,200, 3 positions unpriced'`. `unavailableLabel('insufficient_overlap')` → `'unavailable: fewer than 2 overlapping bars'`; `'zero_variance'` → `'unavailable: benchmark did not move'`; `'foo'` → `'unavailable: foo'`; `null` → `'unavailable'`. `availabilityReason('zero_variance')` → `'zero_variance'`; `{state: 'unavailable', checked_at: 'x', reason: 'market_data_unavailable'}` → that reason; `{state: 'ok', …}` → `null`; `undefined` → `null`.

`ui/pnl-basis.spec.ts`: `PNL_BASIS_LABEL` is exactly `'pre-tax, before modelled frictions'`, and a host rendering `<sb-pnl-basis />` shows that text in `.pnl-basis`.

`ui/market-value.spec.ts` (v201 host, with new bindings `[kind]`, `[staleInputs]`, `[computedAt]`): a snapshot cell with `asOf = '2026-10-28'` and `computedAt` 3 min before the clock in regular hours gets `data-tone="fresh"` and an `.mv-age` of `ageText(180)`. With `staleInputs` true it gets `data-tone="stale"`. With `computedAt` null and `refreshing` true, `.mv-value` is hidden and the spinner shows.

`ui/market-refresh.spec.ts`: `snapshots = ['risk']` with no symbols is enabled, and a click calls `requestRefresh([], ['risk'])`. Both lists empty → disabled. Change v201's case to `toHaveBeenCalledWith(['MSFT'], [])`.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/ui/age-hint.spec.ts --include src/app/stores/live-values.store.spec.ts --include src/app/stores/snapshot-follow.spec.ts --include src/app/ui/lower-bound.spec.ts --include src/app/ui/pnl-basis.spec.ts --include src/app/ui/market-value.spec.ts --include src/app/ui/market-refresh.spec.ts`
Expected: FAIL. The build fails on the missing modules (`snapshot-follow`, `lower-bound`, `pnl-basis`) and on `snapshot`/`stale_snapshot_s` types.

- [ ] **Step 3: Implement** the files above exactly as fixed. Keep `LiveValuesStore`'s merge readable: give the snapshot merge and the snapshot-mark clearing their own private helpers (`mergeSnapshots`, `clearSnapshotMarks`). Split `marketAgeLabel`'s snapshot path into a private `snapshotLabel(...)`, so the price path stays byte-identical. Apply the one-line `risk.ts` guard.

- [ ] **Step 4: Run the specs and the touched neighbours**

Run: the Step 2 command plus `--include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/api/api-client.spec.ts`
Expected: PASS.
Run: `npm --prefix <wt>/frontend exec -- ng build`
Expected: green. A strict-template error at the `risk.ts` guard means the narrowing did not apply. Bind `[values]="corr.values ?? []"` inside the guarded branch instead. Make no other change to that file.

- [ ] **Step 5: Check the labels at three widths**

Add one gallery example beside v201's `sb-market-value` example in `workspaces/gallery/gallery.ts`. It shows a snapshot cell (fresh, stale inputs, closed "as of last close"), a `lowerBoundLabel` line and `sb-pnl-basis` under a figure. Run `npm --prefix <wt>/frontend exec -- ng serve` and `node <wt>/frontend/scripts/browse.mjs shots --base http://localhost:4200 --path /app/ui --widths 1440,768,390`. At 390 px, confirm the labels wrap under their value with `page-scroll-x: 0`.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/live-values.store.ts frontend/src/app/stores/live-values.store.spec.ts frontend/src/app/stores/snapshot-follow.ts frontend/src/app/stores/snapshot-follow.spec.ts frontend/src/app/ui/age-hint.ts frontend/src/app/ui/age-hint.spec.ts frontend/src/app/ui/market-value.ts frontend/src/app/ui/market-value.spec.ts frontend/src/app/ui/market-refresh.ts frontend/src/app/ui/market-refresh.spec.ts frontend/src/app/ui/lower-bound.ts frontend/src/app/ui/lower-bound.spec.ts frontend/src/app/ui/pnl-basis.ts frontend/src/app/ui/pnl-basis.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/gallery/gallery.ts
git -C <wt> commit -m "feat(v204): SPA snapshot primitives -- live snapshots, snapshot age tone, follow, lower-bound and P&L-basis labels"
```
