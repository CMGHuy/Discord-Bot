# Admin read performance, Layer 1 -- Part 3: read scope on, quote batching, the daily FX table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-c. Load each store once per request: opt-in, read routes only", "L1-b. Quote codes in one query, short negative memo", "L1-a. One FX rate per currency pair per day" (table, read memo), "Error handling", "Testing".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

Tasks in this part: V205-9 (`@read_scope` on the six GET views; the memo goes live in the admin), V205-10 (L1-b: one quote-code query per conversion call, a 5-minute negative memo), V205-11 (revision `v205_001`: the `fx_daily_rates` table and its repository), V205-12 (`fx_daily`: the "last positive close strictly before D" rule and the version-keyed table memo). V205-9 and V205-10 are pure refactors: the V205-4 goldens pass **unchanged**. V205-11 and V205-12 are additive: nothing reads the table until V205-15 (part 4), so no output moves in this part.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

# Phase 2 -- Load each store once per request (L1-c), continued

### Task V205-9: `@read_scope` on six GET views; mutating-route guard; write-then-reread tests; budgets lowered

**Model:** sonnet — a decorator, six one-line placements and tests over existing fixtures; the audit that makes it safe is V205-8's.

**Files:**
- Create: `swingbot/admin/api_v1/read_scope.py`, `tests/admin_perf/test_read_scope_routes.py`
- Modify: `swingbot/admin/api_v1/dashboard.py` (import + decorator on `dashboard`, line ~375), `swingbot/admin/api_v1/trades.py` (import + decorator on `list_trades`, line ~1081; E32, decorator line only), `swingbot/admin/api_v1/live.py` (import + decorator on `get_live`, line ~153), `swingbot/admin/api_v1/calendar.py` (import + decorators on `calendar_pnl` ~73, `calendar_pnl_day` ~128, `calendar_pnl_day_sparklines` ~173), `tests/admin_perf/test_budgets.py` (`BUDGETS` second numbers and one docstring sentence only)

**Interfaces:**
- Consumes (V205-6): `read_memo.scope()`, `read_memo.active()`, `read_memo.peek(key)`, keys `TRADES`, `PLANS`, `TRADE_ROWS`. (V205-7): the stores read through the memo. (V205-5): `from tests.admin_perf.test_budgets import BUDGETS, _cost` (`_cost(client, name, monkeypatch) -> tuple[int, list[str]]`). (V205-4): `golden_book.ENDPOINTS`, fixtures `golden_seed`, `frozen_clock`, `logged_in`, `sql_counted`, `admin_app`. (V205-8): `tests/admin_perf/test_memo_isolation.py`, which must pass unchanged with the decorators on. Existing: `api_v1.auth.require_auth` (`@wraps(view)`, auth.py:44); builders `_plan(plan_id, status=...)` and `_trade(trade_id, plan_id=..., status=...)` in `tests/admin/test_api_v1_trades.py`, used the same way by `tests/admin/test_api_v1_trade_commands.py:79-180`.
- Produces (ledger): `READ_SCOPE_ATTR = "__read_scope__"` and `read_scope(view)` in `swingbot/admin/api_v1/read_scope.py`. Exactly six endpoints carry it: `api_v1.dashboard`, `api_v1.list_trades`, `api_v1.get_live`, `api_v1.calendar_pnl`, `api_v1.calendar_pnl_day`, `api_v1.calendar_pnl_day_sparklines`.

**The view list comes from V205-8.** If V205-8 reported a scoped GET that writes or locks rows (its `no_writes` guard), the controller's decision on that report is final: use the view list as V205-8 left it. Drop any view the controller removed from `SCOPED` below and from the decorators, and name it in the commit message. With no such report, the list is the six above.

Why the decorator sits **under** `@require_auth`: `require_auth` wraps with `functools.wraps`, which copies the inner function's `__dict__` outward, so the marker reaches the function Flask registers (`app.view_functions["api_v1.<name>"]`). An unauthenticated request never opens a scope, and the scope covers exactly the view body. `Server-Timing` (V205-3, app-level `after_request`) stays outside it.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin_perf/test_read_scope_routes.py`:

```python
"""v205 V205-9: the read memo is on for exactly six GET views, never a write.

Spec L1-c: a scope is opened only by an explicit @read_scope on GET routes; a
request context alone never opens one. The route enumeration below fails any
POST/PUT/PATCH/DELETE view that carries the marker, and the behavioural tests
write and then re-read in the same request (trade_commands._plan_row /
_trade_row) to prove a write route sees its own write."""
import pytest

from swingbot.admin.api_v1 import read_scope as rs
from swingbot.core.infra import read_memo
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.admin_perf import golden_book as gb
from tests.admin_perf.test_budgets import _cost
from tests.store_seed import seed_store

NAMES = list(gb.ENDPOINTS)
SCOPED = {"api_v1.dashboard", "api_v1.list_trades", "api_v1.get_live", "api_v1.calendar_pnl",
          "api_v1.calendar_pnl_day", "api_v1.calendar_pnl_day_sparklines"}
_WRITES = {"POST", "PUT", "PATCH", "DELETE"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"


def _api_rules():
    from swingbot.admin import app as admin_module
    flask_app = admin_module.app
    return [(rule, flask_app.view_functions[rule.endpoint])
            for rule in flask_app.url_map.iter_rules() if rule.rule.startswith("/api/v1")]


# --- the decorator ---------------------------------------------------------

def test_the_view_runs_inside_a_scope_and_the_scope_ends_with_it():
    seen = []

    @rs.read_scope
    def view(x):
        seen.append(read_memo.active())
        return x * 2

    assert view(21) == 42
    assert seen == [True]
    assert read_memo.active() is False
    assert view.__name__ == "view"
    assert getattr(view, rs.READ_SCOPE_ATTR) is True


def test_an_exception_still_ends_the_scope():
    @rs.read_scope
    def view():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        view()
    assert read_memo.active() is False


def test_the_marker_survives_require_auth():
    from swingbot.admin.api_v1.auth import require_auth

    @require_auth
    @rs.read_scope
    def view():
        return "ok"

    assert getattr(view, rs.READ_SCOPE_ATTR, False) is True


# --- which routes carry it -------------------------------------------------

def test_exactly_the_six_read_views_carry_it(admin_app):
    marked = {rule.endpoint for rule, view in _api_rules() if getattr(view, rs.READ_SCOPE_ATTR, False)}
    assert marked == SCOPED
    for rule, _view in _api_rules():
        if rule.endpoint in SCOPED:
            assert not (rule.methods & _WRITES), (rule.rule, rule.methods)


def test_no_mutating_route_carries_it(admin_app):
    writes = [(rule, view) for rule, view in _api_rules() if rule.methods & _WRITES]
    assert len(writes) >= 20, "the enumeration found too few write routes to mean anything"
    offenders = [f"{sorted(rule.methods & _WRITES)} {rule.rule}" for rule, view in writes
                 if getattr(view, rs.READ_SCOPE_ATTR, False)]
    assert offenders == []


# --- what a scoped request does ---------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_each_store_loads_once_per_scoped_request(name, golden_seed, frozen_clock, sql_counted,
                                                  logged_in, monkeypatch):
    _, calls = _cost(logged_in, name, monkeypatch)
    assert calls.count("PlanRepository") <= 1, calls
    # TradeLog._all (read_memo.TRADES) and account._sum_realized_pnl (TRADE_ROWS) are two loads.
    assert calls.count("TradeRepository") <= 2, calls


def test_every_store_read_of_a_scoped_view_is_inside_the_scope(golden_seed, frozen_clock, logged_in,
                                                               monkeypatch):
    from swingbot.core.db.repositories.base import Repository
    seen = []
    real = Repository.list_all

    def spying(self, *args, **kwargs):
        seen.append((type(self).__name__, read_memo.active()))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", spying)
    assert logged_in.get(gb.ENDPOINTS["dashboard"]).status_code == 200
    store_reads = [active for cls, active in seen if cls in ("TradeRepository", "PlanRepository")]
    assert store_reads and all(store_reads), seen


def test_the_scope_ends_with_the_request(golden_seed, frozen_clock, logged_in):
    assert logged_in.get(gb.ENDPOINTS["trades"]).status_code == 200
    assert read_memo.active() is False
    assert read_memo.peek(read_memo.TRADES) is None


def test_a_second_request_sees_a_write_made_after_the_first(admin_app, logged_in):
    seed_store("plans", [])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=None, status="open")])
    first = logged_in.get("/api/v1/trades?status=open").get_json()
    seed_store("trades", [])
    second = logged_in.get("/api/v1/trades?status=open").get_json()
    assert _TRADE_ID in str(first)
    assert _TRADE_ID not in str(second)


# --- write routes, then re-read in the same request -------------------------

@pytest.fixture
def scopes_by_method(monkeypatch):
    """The HTTP method of every request that opened a read scope."""
    import flask
    opened: list[str] = []
    real = read_memo.scope

    def recording():
        opened.append(flask.request.method if flask.has_request_context() else "-")
        return real()

    monkeypatch.setattr(read_memo, "scope", recording)
    return opened


@pytest.fixture
def no_live_quote(monkeypatch):
    """As tests/admin/test_api_v1_trade_commands.py: closes never reach yfinance."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price_detail", lambda *a, **k: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)


def test_closing_a_plan_returns_the_fresh_row(admin_app, logged_in, no_live_quote, scopes_by_method):
    seed_store("plans", [_plan(_PLAN_ID, status="ACTIVE")])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    assert logged_in.get("/api/v1/trades").status_code == 200       # a scoped read first
    response = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CLOSED"                 # _plan_row re-read
    rows = logged_in.get("/api/v1/trades").get_json()
    assert "CLOSED" in str(rows) and _PLAN_ID in str(rows)
    assert "POST" not in scopes_by_method and "GET" in scopes_by_method


def test_cancelling_a_plan_returns_the_fresh_row(admin_app, logged_in, no_live_quote, scopes_by_method):
    seed_store("plans", [_plan(_PLAN_ID, status="PENDING")])
    seed_store("trades", [])
    response = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CANCELLED"
    assert "POST" not in scopes_by_method


def test_closing_a_legacy_trade_returns_the_fresh_row(admin_app, logged_in, no_live_quote,
                                                      scopes_by_method):
    seed_store("plans", [])
    seed_store("trades", [_trade(_TRADE_ID, plan_id=None, status="open")])
    response = logged_in.post(f"/api/v1/trades/{_TRADE_ID}/close")
    assert response.status_code == 200
    assert response.get_json()["status"] == "CLOSED"                 # _trade_row re-read
    assert "POST" not in scopes_by_method
```

- [ ] **Step 2: Run them to verify they fail**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_read_scope_routes.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'swingbot.admin.api_v1.read_scope'`.

- [ ] **Step 3: Write the decorator**

Create `swingbot/admin/api_v1/read_scope.py`:

```python
"""v205 L1-c: open the core read memo for one admin GET view.

`swingbot.core.infra.read_memo` loads each store once per scope; outside a
scope every store call is today's direct call. The admin opens a scope only
here, only on the GET views plan v205 lists (V205-9), and never on a write
route: tests/admin_perf/test_read_scope_routes.py enumerates the url map.

Place it under ``@require_auth``: that wrapper's ``functools.wraps`` copies
``READ_SCOPE_ATTR`` outward to the function Flask registers."""
from __future__ import annotations

import functools

from swingbot.core.infra import read_memo

READ_SCOPE_ATTR = "__read_scope__"


def read_scope(view):
    """Run ``view`` inside one read-memo scope; the scope resets in its own ``finally``."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        with read_memo.scope():
            return view(*args, **kwargs)

    setattr(wrapper, READ_SCOPE_ATTR, True)
    return wrapper
```

`read_memo.scope` is looked up on the module at call time, so a test can replace it (the `scopes_by_method` fixture).

- [ ] **Step 4: Put it on the six views**

In each of the four files add, directly after the line that imports `require_auth` (`from .auth import require_auth`):

```python
from .read_scope import read_scope
```

and one decorator line under `@require_auth`. `swingbot/admin/api_v1/dashboard.py` (~373):

```python
@api_v1.route("/dashboard", methods=["GET"])
@require_auth
@read_scope
def dashboard():
```

`swingbot/admin/api_v1/trades.py` (~1079; nothing else in `list_trades` changes):

```python
@api_v1.route("/trades", methods=["GET"])
@require_auth
@read_scope
def list_trades():
```

`swingbot/admin/api_v1/live.py` (~151):

```python
@api_v1.route("/live", methods=["GET"])
@require_auth
@read_scope
def get_live():
```

`swingbot/admin/api_v1/calendar.py` (~71, ~126, ~171):

```python
@api_v1.route("/calendar/pnl", methods=["GET"])
@require_auth
@read_scope
def calendar_pnl():
```

```python
@api_v1.route("/calendar/pnl/day", methods=["GET"])
@require_auth
@read_scope
def calendar_pnl_day():
```

```python
@api_v1.route("/calendar/pnl/day/sparklines", methods=["GET"])
@require_auth
@read_scope
def calendar_pnl_day_sparklines():
```

- [ ] **Step 5: Run the new tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_read_scope_routes.py`
Expected: `21 passed`, `0 failed` (3 decorator, 2 enumeration, 8 per-endpoint, 4 scoped-request incl. the second-request test, 3 write-route; if pytest's count differs, trust `0 failed`).

If `test_each_store_loads_once_per_scoped_request[<name>]` fails, read the `calls` list: a third `TradeRepository` or a second `PlanRepository` load means a store path still bypasses the memo. Report the path to the controller; never widen the assertion. If a write-route test shows `POST` in `scopes_by_method`, a write route opened a scope: find the stray decorator and remove it.

- [ ] **Step 6: Lower the `list_all` budgets**

Re-run V205-5's probe now that the memo is on (a scratch file outside the worktree, deleted first):

Run: `ADMIN_PERF_PROBE=<scratch>/v205_budgets_scoped.jsonl python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`
Expected: the 8 probe tests pass and the file holds 8 JSON lines.

In `<wt>/tests/admin_perf/test_budgets.py`, change **only the second number** of each `BUDGETS` entry to the probe's `list_all` value, and replace that entry's comment with the probe's new `calls` list plus `(probe, v205 V205-9 scoped)`. The first number (statements) stays as V205-5 measured it (index contract: V205-9 lowers only the `list_all` numbers). The shape, with `S` the unchanged V205-5 literal and `L2` the new probe literal:

```python
    "dashboard": (S, L2),  # list_all: TradeRepository x2, PlanRepository x1, ... (probe, v205 V205-9 scoped)
```

Every `L2` must be `<=` its old value; a larger number means the decorators made something dearer, which is a defect to report, never a budget to raise. Expect `dashboard` to fall from its pre-memo count to about three store loads plus whatever non-store repositories it reads.

Also change the module docstring's sentence "V205-9 lowers the list_all numbers once @read_scope is on; nothing else edits BUDGETS." to "V205-9 lowered the list_all numbers once @read_scope was on (statements unchanged); nothing else edits BUDGETS."

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`
Expected: `10 passed, 8 skipped`, `0 failed`.

- [ ] **Step 7: Run the neighbours**

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf`
Expected: `0 failed`, `0 xfailed`. The goldens and `test_memo_isolation.py` pass **unchanged**: `git -C <wt> diff --stat -- tests/admin_perf/golden/ tests/admin_perf/money_reference.py tests/admin_perf/test_memo_isolation.py` is empty.

Run: `python <wt>/scripts/dev/testrun.py suite admin`
Expected: `0 failed`, `0 xfailed`. The admin suite now runs these six views with the memo on. A failure is a store read inside one request that the memo changed; debug it with `superpowers:systematic-debugging`. The likely shape is a test that patches a store method or reseeds a store *between two reads of one request*. Fix the production path only if its output differs from the unscoped run; report anything else to the controller.

Run: `python <wt>/scripts/dev/testrun.py suite live-api` -- expected `0 failed`.

Run: `python <wt>/scripts/dev/complexity_gate.py` -- expected clean (`trades.list_trades` gains a decorator line only).

- [ ] **Step 8: Commit**

```bash
git -C <wt> add swingbot/admin/api_v1/read_scope.py tests/admin_perf/test_read_scope_routes.py
git -C <wt> commit -m "feat(admin): read_scope decorator opening the read memo for one GET view (v205 V205-9)"
git -C <wt> add swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/trades.py swingbot/admin/api_v1/live.py swingbot/admin/api_v1/calendar.py
git -C <wt> commit -m "perf(admin): dashboard, trades, live and calendar views load each store once (v205 V205-9)"
git -C <wt> add tests/admin_perf/test_budgets.py
git -C <wt> commit -m "test(admin): list_all budgets lowered to the scoped cost (v205 V205-9)"
```

# Phase 3 -- Quote codes in one query (L1-b)

### Task V205-10: L1-b: quote codes in one query; 5-minute negative memo

**Model:** sonnet — two small functions in a module with clear seams and one constructor argument; the trap (one-argument test seams on `fetch=True`) is named below.

**Files:**
- Modify: `swingbot/core/marketdata/fx.py` (new `UNKNOWN_MEMO_S`, `_unknown_until`, `stored_codes`, `_ask_store`; `_stored_code` becomes one line), `swingbot/core/marketdata/fx_convert.py` (`_Rates.__init__` gains `tickers`; `to_account_currency` passes them), `tests/marketdata/test_fx.py` and `tests/marketdata/test_fx_persisted.py` (one line each: their autouse `_isolated` fixture also resets `fx._unknown_until`)
- Create: `tests/marketdata/test_fx_quote_batch.py`

**Interfaces:**
- Consumes (existing): `fx._quote_codes`, `fx._clock()`, `quote_currency_repo().get_many(symbols, *, conn=None) -> dict[str, dict]` (`{symbol: {symbol, code, outcome, checked_at, retry_after}}`), `swallowed(log, tag, exc, ..., level=...)`; `fx_convert.quote_code(ticker, *, fetch)`, `fx_convert.rate(...)`.
- Produces (ledger): `fx.UNKNOWN_MEMO_S = 300`; `fx._unknown_until: dict[str, float]` (monotonic deadline per upper-cased key; tests reset it like `_frames`); `fx.stored_codes(keys: Iterable[str]) -> dict[str, str | None]`; `fx_convert._Rates(account, fetch=True, tickers=())`. V205-15 and V205-16 edit `fx.py`/`fx_convert.py` after this task and keep these names.

What changes: today `_Rates.quote` with `fetch=False` calls `fx.quote_currency_code(key, fetch=False)` once per ticker, and every unknown answer is a fresh `get_many([key])` round trip (59 calls in `/calendar/pnl` on production). After this task one conversion call resolves all its tickers with **one** `get_many`, and an unknown (or absent) answer is remembered for at most 5 minutes, so a code the refresher resolves meanwhile shows within 5 minutes (spec L1-b). `fetch=True` (refresher off) is untouched: it still calls the one-argument `fx.quote_currency_code(ticker)`, which `tests/admin/conftest.py:125-129` and `golden_seed` pin as `lambda ticker, **_kw:`. So the V205-4 goldens (refresher off) cannot move.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_fx_quote_batch.py`:

```python
"""v205 L1-b: quote codes for one conversion in one query; unknowns memoised for 5 minutes."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx, fx_convert

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)


class CountingCodes:
    def __init__(self):
        self.rows = {}
        self.calls: list[list[str]] = []
        self.fail = False

    def get_many(self, symbols, *, conn=None):
        wanted = [s.upper() for s in symbols]
        self.calls.append(wanted)
        if self.fail:
            raise RuntimeError("db down")
        return {s: self.rows[s] for s in wanted if s in self.rows}

    def known(self, symbol, code):
        self.rows[symbol] = {"symbol": symbol, "code": code, "outcome": "known",
                             "checked_at": T0, "retry_after": None}

    def unknown(self, symbol):
        self.rows[symbol] = {"symbol": symbol, "code": None, "outcome": "unknown",
                             "checked_at": T0, "retry_after": T0}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})
    monkeypatch.setattr(fx, "_unknown_until", {})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")


@pytest.fixture
def codes(monkeypatch):
    repo = CountingCodes()
    monkeypatch.setattr(fx, "quote_currency_repo", lambda: repo)
    return repo


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(fx, "_clock", c)
    return c


@pytest.fixture
def flat_rate(monkeypatch):
    """Every pair at 0.5, so a converted amount shows whether its quote resolved."""
    monkeypatch.setattr(fx, "fx_rate", lambda from_code, to_code, on, *, refresh=True: 0.5)


def _row(ticker, amount=10.0):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": "2026-10-28"}


def test_one_conversion_call_asks_the_store_once(codes, clock, flat_rate):
    codes.known("AAPL", "USD")
    codes.known("SAP.DE", "EUR")
    rows = fx_convert.to_account_currency(
        [_row("aapl"), _row("SAP.DE"), _row("AAPL"), _row("NEW"), _row(None)], fetch=False)
    assert codes.calls == [["AAPL", "SAP.DE", "NEW"]]
    assert [(r["realized_pnl_amount"], r["fx_missing"]) for r in rows] == [
        (5.0, False), (10.0, False), (5.0, False), (None, True), (None, True)]


def test_known_codes_are_remembered_for_the_process(codes, clock):
    codes.known("AAPL", "USD")
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}
    codes.rows.clear()
    clock.now += 10 * fx.UNKNOWN_MEMO_S
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}
    assert codes.calls == [["AAPL"]]
    assert fx._quote_codes["AAPL"] == "USD"


def test_an_unknown_code_is_remembered_for_five_minutes_then_asked_again(codes, clock):
    codes.unknown("ZZZ")
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": None, "NEW": None}
    codes.known("ZZZ", "USD")                       # the refresher resolves it meanwhile
    clock.now += fx.UNKNOWN_MEMO_S - 1
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": None, "NEW": None}
    assert codes.calls == [["ZZZ", "NEW"]]          # inside the memo: no query
    clock.now += 2
    assert fx.stored_codes(["ZZZ", "NEW"]) == {"ZZZ": "USD", "NEW": None}
    assert codes.calls == [["ZZZ", "NEW"], ["ZZZ", "NEW"]]


def test_the_single_ticker_path_shares_the_negative_memo(codes, clock):
    assert fx.quote_currency_code("NEW", fetch=False) is None
    assert fx.quote_currency_code("new", fetch=False) is None
    assert codes.calls == [["NEW"]]


def test_a_store_error_is_all_none_swallowed_and_not_memoised(codes, clock):
    before = sw.snapshot().get("marketdata.fx.stored_code", {}).get("count", 0)
    codes.fail = True
    assert fx.stored_codes(["AAPL", "ZZZ"]) == {"AAPL": None, "ZZZ": None}
    assert sw.snapshot()["marketdata.fx.stored_code"]["count"] == before + 1
    assert fx._unknown_until == {} and fx._quote_codes == {}
    codes.fail = False
    codes.known("AAPL", "USD")
    assert fx.stored_codes(["AAPL"]) == {"AAPL": "USD"}          # asked again at once


def test_no_keys_means_no_query(codes, clock):
    assert fx.stored_codes([]) == {}
    assert fx.stored_codes(["", None, "  "]) == {}
    assert codes.calls == []


def test_fetch_true_keeps_the_one_argument_seam(monkeypatch, codes, flat_rate):
    seen = []
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: seen.append(ticker) or "USD")
    monkeypatch.setattr(fx, "stored_codes", lambda keys: pytest.fail("fetch=True must not batch"))
    rows = fx_convert.to_account_currency([_row("AAPL"), _row("MSFT")])
    assert seen == ["AAPL", "MSFT"]
    assert [r["realized_pnl_amount"] for r in rows] == [5.0, 5.0]
    assert codes.calls == []


def test_convert_amount_without_fetch_still_resolves_its_one_ticker(codes, clock, flat_rate):
    codes.known("AAPL", "USD")
    assert fx_convert.convert_amount(10.0, "AAPL", date(2026, 10, 28), fetch=False) == (5.0, False)
    assert codes.calls == [["AAPL"]]
```

Append one line to the autouse `_isolated` fixture of `tests/marketdata/test_fx.py` (after `monkeypatch.setattr(fx, "_quote_codes", {})`, line ~25) and of `tests/marketdata/test_fx_persisted.py` (line ~39), so the new process memo never leaks between their tests:

```python
    monkeypatch.setattr(fx, "_unknown_until", {})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_quote_batch.py`
Expected: FAIL. The fixture `_isolated` raises `AttributeError: <module 'swingbot.core.marketdata.fx'> has no attribute '_unknown_until'` for every test.

- [ ] **Step 3: Implement the batch in `fx.py`**

In `<wt>/swingbot/core/marketdata/fx.py`, after `FRAME_TTL_S = 15 * 60` add:

```python
#: v205 L1-b: how long an unknown (or absent) stored quote code is remembered,
#: so a request never re-asks the store per ticker, and a code the refresher
#: resolves meanwhile shows within this long.
UNKNOWN_MEMO_S = 300
```

After `_quote_codes: dict[str, str] = {}` add:

```python
_unknown_until: dict[str, float] = {}
```

Replace the whole `_stored_code` function (lines ~103-113) with:

```python
def _stored_code(key: str) -> str | None:
    """v201: the refresher's persisted answer; never the network. Unknown/missing -> None."""
    return stored_codes([key]).get(key)


def stored_codes(keys: Iterable[str]) -> dict[str, str | None]:
    """v205 L1-b: the refresher's persisted answers for many tickers in one query.

    A known code is memoised for the process (`_quote_codes`); an unknown or
    absent one for UNKNOWN_MEMO_S (`_unknown_until`, monotonic `_clock()`).
    Keys in neither memo cost one `get_many` together. A store error answers
    None for those keys and memoises nothing, so the next call asks again."""
    now = _clock()
    out: dict[str, str | None] = {}
    ask: list[str] = []
    for key in dict.fromkeys(str(k or "").upper().strip() for k in keys):
        if not key:
            continue
        if key in _quote_codes:
            out[key] = _quote_codes[key]
        elif _unknown_until.get(key, 0.0) > now:
            out[key] = None
        else:
            ask.append(key)
    if ask:
        out.update(_ask_store(ask, now))
    return out


def _ask_store(keys: list[str], now: float) -> dict[str, str | None]:
    """One `get_many` for `keys`; memoise every answer (see `stored_codes`)."""
    try:
        rows = quote_currency_repo().get_many(keys)
    except Exception as exc:
        swallowed(log, "marketdata.fx.stored_code", exc, level=logging.DEBUG)
        return dict.fromkeys(keys)
    out: dict[str, str | None] = {}
    for key in keys:
        row = rows.get(key)
        if row and row.get("outcome") == "known" and row.get("code"):
            _quote_codes[key] = str(row["code"])
            out[key] = _quote_codes[key]
        else:
            _unknown_until[key] = now + UNKNOWN_MEMO_S
            out[key] = None
    return out
```

The `swallowed` tag `marketdata.fx.stored_code` moves with the `except` (the old site is gone), so it stays unique repo-wide. `Iterable` is already imported (`from collections.abc import Iterable`).

- [ ] **Step 4: Resolve a call's tickers up front in `fx_convert.py`**

In `<wt>/swingbot/core/marketdata/fx_convert.py`, replace `_Rates.__init__` with:

```python
    def __init__(self, account: str, fetch: bool = True, tickers=()):
        self.account = account
        self.fetch = fetch
        # v205 L1-b: never-fetch reads resolve every ticker of the call in one query;
        # fetch=True keeps the one-argument per-ticker seam (`quote_code`).
        self._quotes: dict[str, str | None] = {} if fetch else _stored_quotes(tickers)
        self._rates: dict[tuple[str, date], float | None] = {}
```

Add above `class _Rates:`:

```python
def _stored_quotes(tickers) -> dict[str, str | None]:
    """Upper-cased ticker -> stored quote code, one `fx.stored_codes` query (none when empty)."""
    keys = [key for key in (str(t or "").upper().strip() for t in tickers) if key]
    return fx.stored_codes(keys) if keys else {}
```

In `to_account_currency`, change the `_Rates(...)` line to:

```python
    rates = _Rates(account or fx.account_currency_code(), fetch,
                   tickers=[row.get("ticker") for row in rows])
```

`_Rates.quote` is unchanged: a key already in `self._quotes` (including a `None` answer) is returned; any other key still goes through `quote_code(key, fetch=self.fetch)`. `convert_amount` is unchanged (one ticker: `quote_currency_code(key, fetch=False)` -> `_stored_code` -> `stored_codes([key])`, one query).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_quote_batch.py`
Expected: `8 passed`, `0 failed`.

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_persisted.py`, then `... file tests/marketdata/test_fx.py`
Expected: `0 failed` each, no assertion edited beyond the one `_isolated` line.

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` -- expected `0 failed` (the tag moved, it was not duplicated).

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf` -- expected `0 failed`; the goldens pass unchanged (`git -C <wt> diff --stat -- tests/admin_perf/` empty).

Run: `python <wt>/scripts/dev/testrun.py suite admin` and `python <wt>/scripts/dev/testrun.py suite refresher` -- expected `0 failed` each (`tests/admin_market/` exercises `fetch=False` with the refresher on).

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx.py <wt>/swingbot/core/marketdata/fx_convert.py` -- `stored_codes` and `_ask_store` are `A`/`B` (under 10); `python <wt>/scripts/dev/complexity_gate.py` clean.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/fx.py swingbot/core/marketdata/fx_convert.py tests/marketdata/test_fx_quote_batch.py tests/marketdata/test_fx.py tests/marketdata/test_fx_persisted.py
git -C <wt> commit -m "perf(marketdata): quote codes of one conversion in one query, unknowns memoised 5 min (v205 V205-10)"
```

# Phase 4 -- One FX rate per pair per day (L1-a): the table and its reader

### Task V205-11: Alembic `v205_001`: `fx_daily_rates`; repository; head test relaxed

**Model:** opus — a schema change that must match `compare_metadata` exactly, a composite-key repository outside the base class's single-key model, and a revision chain whose head may move under it.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v205_001_fx_daily_rates.py`, `tests/db/test_v205_fx_daily_rates.py`
- Modify: `swingbot/core/db/schema.py` (table after `quote_currencies`, ~line 317; `PROMOTION_REASONS["fx_daily_rates"]` after the `quote_currencies` entry, ~line 541), `swingbot/core/db/repositories/market_refresh.py` (`FxDailyRateRepository`, `QuoteCurrencyRepository.known_codes`, `fx_daily_rate_repo()`), `tests/db/test_v200_discord_issued_at.py` (the fixed-head assertion, lines ~166-169), `tests/db/test_unknown_field_round_trip.py` (one `NOT_REPOSITORY_BACKED` entry: `test_every_table_is_covered_or_excused` fails on any new table otherwise)

**Interfaces:**
- Consumes (existing): `schema.register(table, promoted)`, `standard_columns()`, `METADATA`, `PROMOTION_REASONS`, `promoted_for`, `contract_violations`; `Repository(table, key=...)`, `Repository._tx(conn)`; `_singleton(cls)`, `_STAMP`; fixtures `db_conn`, `db_engine_empty` (`tests/db/conftest.py:105,135`).
- Produces (ledger, index "Table" and "Repository"): table `fx_daily_rates` (`base`, `account`, `day` composite PK in that order; `rate Float(53) NOT NULL`, `bar_date Date NOT NULL`, `snapped_at TIMESTAMPTZ NOT NULL`, `source Text NOT NULL`; `doc`, `updated_at`; no secondary index); `FxDailyRateRepository` with `insert_if_absent(rows, *, conn=None) -> int`, `all_rates(*, conn=None) -> list[dict]` (`{base, account, day, rate, bar_date}` ordered by `(base, account, day)`), `version(*, conn=None) -> tuple[int, datetime | None]`, `days_present(base, account, *, conn=None) -> set[date]`; `QuoteCurrencyRepository.known_codes(*, conn=None) -> set[str]`; accessor `fx_daily_rate_repo()`. V205-12 reads `version`/`all_rates`; V205-13/14 write through `insert_if_absent` and read `days_present`/`known_codes`.

**The revision's parent is decided now, not by the plan.** Run `python -m alembic -c <wt>/alembic.ini heads`. It prints one head: `v200_001` is expected, but plan v204 (unimplemented when this plan was written) may have landed `v204_001` first. That printed id is `down_revision` below wherever the code says `v200_001`, and the docstring's `Revises:` line. If it prints two heads, stop and report: never merge heads in this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_v205_fx_daily_rates.py`:

```python
"""v205: revision v205_001 -- fx_daily_rates, one FX rate per major-code pair per
Berlin day, and the repository that writes it insert-if-absent."""
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import market_refresh as mr

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTED = ("base", "account", "day", "rate", "bar_date", "snapped_at", "source")
T0 = datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc)


def _row(day, rate, *, base="USD", account="EUR", bar=None, source="snap", at=T0):
    return {"base": base, "account": account, "day": day, "rate": rate,
            "bar_date": bar or day - timedelta(days=1), "snapped_at": at,
            "source": source}


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables["fx_daily_rates"]
    assert schema.promoted_for("fx_daily_rates") == PROMOTED
    assert set(schema.PROMOTION_REASONS["fx_daily_rates"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["base", "account", "day"]
    assert all(table.c[name].nullable is False for name in PROMOTED)
    assert list(table.indexes) == []
    assert "fx_daily_rates" not in events.TABLE_CHANNELS


def test_column_types():
    t = schema.fx_daily_rates
    assert isinstance(t.c.day.type, sa.Date) and isinstance(t.c.bar_date.type, sa.Date)
    assert isinstance(t.c.rate.type, sa.Float)
    assert t.c.snapped_at.type.timezone is True
    assert isinstance(t.c.base.type, sa.Text) and isinstance(t.c.source.type, sa.Text)


def test_v205_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v205_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1      # later revisions may stack on v205_001; never branch
    assert "v205_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_it_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "fx_daily_rates" in sa.inspect(connection).get_table_names()
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v205_001").down_revision)
        remaining = set(sa.inspect(connection).get_table_names())
        assert "fx_daily_rates" not in remaining and "quote_currencies" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "fx_daily_rates" in sa.inspect(connection).get_table_names()


# --- the repository ----------------------------------------------------------

def test_insert_if_absent_keeps_the_first_value_of_a_day(db_conn):
    repo = mr.FxDailyRateRepository()
    day = date(2026, 11, 4)
    assert repo.insert_if_absent([_row(day, 0.86)], conn=db_conn) == 1
    assert repo.insert_if_absent([_row(day, 0.99, source="backfill"),
                                  _row(date(2026, 11, 5), 0.87)], conn=db_conn) == 1
    rates = repo.all_rates(conn=db_conn)
    assert [(r["day"], r["rate"]) for r in rates] == [(day, 0.86), (date(2026, 11, 5), 0.87)]
    assert set(rates[0]) == {"base", "account", "day", "rate", "bar_date"}


def test_nothing_to_insert_writes_nothing(db_conn):
    assert mr.FxDailyRateRepository().insert_if_absent([], conn=db_conn) == 0


@pytest.mark.parametrize("bad", [{"source": "live"}, {"rate": 0.0}, {"rate": -1.0}])
def test_a_bad_row_is_refused(db_conn, bad):
    with pytest.raises(ValueError):
        mr.FxDailyRateRepository().insert_if_absent([{**_row(date(2026, 11, 4), 0.86), **bad}],
                                                    conn=db_conn)


def test_all_rates_orders_by_pair_then_day_and_upper_cases_codes(db_conn):
    repo = mr.FxDailyRateRepository()
    repo.insert_if_absent([_row(date(2026, 11, 5), 0.87),
                           _row(date(2026, 11, 4), 1.15, base="gbp"),
                           _row(date(2026, 11, 4), 0.86)], conn=db_conn)
    assert [(r["base"], r["account"], r["day"]) for r in repo.all_rates(conn=db_conn)] == [
        ("GBP", "EUR", date(2026, 11, 4)), ("USD", "EUR", date(2026, 11, 4)),
        ("USD", "EUR", date(2026, 11, 5))]


def test_version_is_count_and_latest_snap(db_conn):
    repo = mr.FxDailyRateRepository()
    assert repo.version(conn=db_conn) == (0, None)
    later = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)
    repo.insert_if_absent([_row(date(2026, 11, 4), 0.86),
                           _row(date(2026, 11, 5), 0.87, at=later)], conn=db_conn)
    assert repo.version(conn=db_conn) == (2, later)


def test_days_present_is_per_pair(db_conn):
    repo = mr.FxDailyRateRepository()
    repo.insert_if_absent([_row(date(2026, 11, 4), 0.86),
                           _row(date(2026, 11, 3), 1.15, base="GBP")], conn=db_conn)
    assert repo.days_present("USD", "EUR", conn=db_conn) == {date(2026, 11, 4)}
    assert repo.days_present("usd", "eur", conn=db_conn) == {date(2026, 11, 4)}
    assert repo.days_present("ZAR", "EUR", conn=db_conn) == set()


def test_known_codes_are_the_distinct_known_answers(db_conn):
    codes = mr.QuoteCurrencyRepository()
    codes.put("AAPL", "USD", "known", checked_at=T0, conn=db_conn)
    codes.put("MSFT", "USD", "known", checked_at=T0, conn=db_conn)
    codes.put("VOD.L", "GBp", "known", checked_at=T0, conn=db_conn)
    codes.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0, conn=db_conn)
    assert codes.known_codes(conn=db_conn) == {"USD", "GBp"}


def test_the_accessor_is_a_singleton():
    assert mr.fx_daily_rate_repo() is mr.fx_daily_rate_repo()
    assert isinstance(mr.fx_daily_rate_repo(), mr.FxDailyRateRepository)
```

- [ ] **Step 2: Run them to verify they fail**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v205_fx_daily_rates.py`
Expected: FAIL; `KeyError: 'fx_daily_rates'` in the schema tests and `AttributeError: module ... has no attribute 'FxDailyRateRepository'` in the repository tests.

- [ ] **Step 3: Declare the table in `schema.py`**

In `<wt>/swingbot/core/db/schema.py`, directly after the `quote_currencies = register(...)` block:

```python
# v205: one FX rate per (major base, major account, Berlin day): the last positive
# daily close strictly before that day. Written insert-if-absent by the refresher's
# 08:00 Berlin snap and the one-off backfill (core/marketdata/fx_snap.py); read whole
# by core/marketdata/fx_daily.py. No SSE trigger.
fx_daily_rates = register(sa.Table("fx_daily_rates", METADATA,
    sa.Column("base", sa.Text, primary_key=True),
    sa.Column("account", sa.Text, primary_key=True),
    sa.Column("day", sa.Date, primary_key=True),
    sa.Column("rate", sa.Float(53), nullable=False),
    sa.Column("bar_date", sa.Date, nullable=False),
    sa.Column("snapped_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    *standard_columns()),
    ("base", "account", "day", "rate", "bar_date", "snapped_at", "source"))
```

In `PROMOTION_REASONS`, directly after the `"quote_currencies": {...},` entry:

```python
    "fx_daily_rates": {
        "base": "primary key (base, account, day): one rate per major-code pair per Berlin day",
        "account": "primary key (base, account, day): the major account currency converted into",
        "day": "primary key: the Berlin calendar day the rate serves; fx_daily.lookup's sort key",
        "rate": "NOT NULL multiplier fx_daily.lookup returns; never 1.0 for a missing pair",
        "bar_date": "NOT NULL date of the frame bar the rate came from; the FALLBACK_DAYS test",
        "snapped_at": "NOT NULL write time; max(snapped_at) is half of the memo's version key",
        "source": "NOT NULL snap/backfill provenance, checked after the deploy backfill",
    },
```

- [ ] **Step 4: Write the revision**

Create `<wt>/swingbot/core/db/migrations/versions/v205_001_fx_daily_rates.py` (replace both `v200_001` with the head the `alembic heads` command above printed, if it differs):

```python
"""v205: fx_daily_rates -- one FX rate per (major base, major account, Berlin day).

Additive: rollback is this revision's downgrade; leaving the table after a code
rollback is also safe (the old code never reads it).

Revision ID: v205_001
Revises: v200_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v205_001"
down_revision = "v200_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("fx_daily_rates",
        sa.Column("base", sa.Text, primary_key=True),
        sa.Column("account", sa.Text, primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("rate", sa.Float(53), nullable=False),
        sa.Column("bar_date", sa.Date, nullable=False),
        sa.Column("snapped_at", _TS, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        *_standard())


def downgrade() -> None:
    op.drop_table("fx_daily_rates")
```

- [ ] **Step 5: Write the repository**

In `<wt>/swingbot/core/db/repositories/market_refresh.py`: add `from datetime import date, datetime, timedelta` (replacing the existing `from datetime import datetime, timedelta`), add `fx_daily_rates` to the `from swingbot.core.db.schema import (...)` list, and extend the module docstring's first line to "v201: the refresher's four stores ... and the heartbeat; v205: the daily FX rates." Add to `QuoteCurrencyRepository` (after `due`):

```python
    def known_codes(self, *, conn=None) -> set[str]:
        """v205: every distinct code a symbol is known to be quoted in (the snap's pairs in use)."""
        t = self.table
        stmt = sa.select(t.c.code).distinct().where(t.c.outcome == "known", t.c.code.is_not(None))
        with self._tx(conn) as c:
            return {r.code for r in c.execute(stmt)}
```

After the `QuoteCurrencyRepository` class add:

```python
_FX_SOURCES = ("snap", "backfill")


def _fx_values(row: dict) -> dict:
    """One fx_daily_rates row, codes upper-cased; a bad source or rate is refused."""
    rate = float(row["rate"])
    if row["source"] not in _FX_SOURCES or not rate > 0:
        raise ValueError(f"fx_daily_rates: refused row {row!r}")
    return {"base": str(row["base"]).upper(), "account": str(row["account"]).upper(),
            "day": row["day"], "rate": rate, "bar_date": row["bar_date"],
            "snapped_at": row["snapped_at"], "source": row["source"], "updated_at": _STAMP}


class FxDailyRateRepository(Repository):
    """v205: one rate per (base, account, Berlin day), written insert-if-absent only.

    The key is composite, so the base class's single-key get/upsert are never
    used; every method writes its own SQL. The first value written is the day's
    value: a later snap or a re-run backfill never changes it."""

    def __init__(self):
        super().__init__(fx_daily_rates, key="day")

    def insert_if_absent(self, rows, *, conn=None) -> int:
        values = [_fx_values(row) for row in rows]
        if not values:
            return 0
        stmt = pg_insert(self.table).values(values).on_conflict_do_nothing(
            index_elements=["base", "account", "day"])
        with self._tx(conn) as c:
            return int(c.execute(stmt).rowcount or 0)

    def all_rates(self, *, conn=None) -> list[dict]:
        t = self.table
        stmt = sa.select(t.c.base, t.c.account, t.c.day, t.c.rate, t.c.bar_date).order_by(
            t.c.base, t.c.account, t.c.day)
        with self._tx(conn) as c:
            return [dict(r._mapping) for r in c.execute(stmt)]

    def version(self, *, conn=None) -> tuple[int, datetime | None]:
        t = self.table
        stmt = sa.select(sa.func.count(), sa.func.max(t.c.snapped_at)).select_from(t)
        with self._tx(conn) as c:
            count, latest = c.execute(stmt).one()
        return int(count), latest

    def days_present(self, base: str, account: str, *, conn=None) -> set[date]:
        t = self.table
        stmt = sa.select(t.c.day).where(t.c.base == base.upper(), t.c.account == account.upper())
        with self._tx(conn) as c:
            return {r.day for r in c.execute(stmt)}
```

Beside the other accessors at the bottom:

```python
def fx_daily_rate_repo() -> FxDailyRateRepository:
    return _singleton(FxDailyRateRepository)
```

- [ ] **Step 6: Relax the two whole-schema tests**

In `<wt>/tests/db/test_v200_discord_issued_at.py`, replace the test at lines ~166-169:

```python
def test_v200_001_sits_on_v201_001_and_is_the_single_head(scripts):
    assert (MIG.revision, MIG.down_revision) == ("v200_001", "v201_001")
    assert scripts.get_revision("v200_001").down_revision == "v201_001"
    assert scripts.get_heads() == ["v200_001"]
```

with:

```python
def test_v200_001_sits_on_v201_001_below_the_single_head(scripts):
    assert (MIG.revision, MIG.down_revision) == ("v200_001", "v201_001")
    assert scripts.get_revision("v200_001").down_revision == "v201_001"
    heads = scripts.get_heads()
    assert len(heads) == 1      # later revisions (v205_001, ...) stack on it; never branch
    assert "v200_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}
```

(If v204 already relaxed this test the same way, leave it.)

In `<wt>/tests/db/test_unknown_field_round_trip.py`, add to `NOT_REPOSITORY_BACKED`:

```python
    "fx_daily_rates": "composite key (base, account, day), written insert_if_absent only and "
                      "read as promoted columns; its round trip is tests/db/test_v205_fx_daily_rates.py",
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v205_fx_daily_rates.py`
Expected: `14 passed`, `0 failed`.

Run each: `python <wt>/scripts/dev/testrun.py file tests/db/test_migrations.py`, `... file tests/db/test_v200_discord_issued_at.py`, `... file tests/db/test_v201_tables.py`, `... file tests/db/test_unknown_field_round_trip.py`, `... file tests/db/test_schema.py`, `... file tests/db/test_schema_contract.py`
Expected: `0 failed` each. `test_migrations_produce_exactly_the_declared_schema` is the one that proves `schema.py` and the revision agree (PK order, `Date`, `Float(53)`, nullability); a diff there is fixed in whichever side is wrong, never by loosening the test.

Run: `python <wt>/scripts/dev/testrun.py suite storage` -- expected `0 failed`, `0 xfailed`.

Run: `python <wt>/scripts/dev/complexity_gate.py` -- expected clean.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v205_001_fx_daily_rates.py tests/db/test_v200_discord_issued_at.py tests/db/test_unknown_field_round_trip.py
git -C <wt> commit -m "feat(db): fx_daily_rates table, revision v205_001 (v205 V205-11)"
git -C <wt> add swingbot/core/db/repositories/market_refresh.py tests/db/test_v205_fx_daily_rates.py
git -C <wt> commit -m "feat(db): FxDailyRateRepository, insert-if-absent, and known quote codes (v205 V205-11)"
```

The new test file goes in the second commit, with the repository it imports. If the head was not `v200_001`, name the actual parent in the first commit's message body.

### Task V205-12: Rate rule `rate_before` (new module `fx_daily`)

**Model:** opus — the one rate rule both snap and backfill rest on (dates, tz, duplicates, gaps), vectorised without changing what it answers.

**Files:**
- Create: `swingbot/core/marketdata/fx_daily.py`, `tests/marketdata/test_fx_daily.py`
- Modify: `docs/claude/architecture.md` (the `core/marketdata/` entry of the module map, lines ~17-21)

**Interfaces:**
- Consumes: nothing from earlier tasks (pandas, numpy only).
- Produces (ledger, index "fx_daily"): `FALLBACK_DAYS = 7`; `rate_before(frame: pd.DataFrame | None, day: date) -> tuple[float, date] | None`; `_clock() -> float` (monotonic seam). V205-12b appends the table memo (`VERSION_CHECK_S`, `lookup`, `reset_memo`) to this module. V205-13/14 call `rate_before`. V205-15 calls it and makes `fx.FALLBACK_DAYS` this object by import.
- `fx_daily` imports nothing from `swingbot.core.marketdata.fx` (fx imports fx_daily in V205-15), nothing from `swingbot.admin`, nothing from `flask`. A test pins this.

**The rule (spec L1-a, index Global Constraints).** The rate for day D is the last positive close dated **strictly before** D, with the frame index normalised to dates explicitly. A tz-aware index keeps its own wall-clock date, as `Timestamp.date()` does today; a naive index is its date. NaN and non-positive closes are skipped. Duplicate stamps are allowed: among bars on the newest date, the last row in frame order wins. Unsorted stamps are allowed: the newest date wins wherever it sits. The answer is `None` unless `D - bar_date <= FALLBACK_DAYS` days. This is today's `fx._close_on_or_before` with two changes. The bar must be before D, not on it. The scan is vectorised over numpy arrays, with no Python list over the whole index per call; that list was 4.1 s of `/calendar/pnl`.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_fx_daily.py`:

```python
"""v205 L1-a: the daily FX rate rule, fx_daily.rate_before.

Every expected rate is a literal read off the fixture frame by hand, never a
recomputation through fx or fx_convert. The table memo's tests are
tests/marketdata/test_fx_daily_lookup.py (V205-12b)."""
import ast
import math
import pathlib
from datetime import date

import pandas as pd
import pytest

from swingbot.core.marketdata import fx_daily

SOURCE = pathlib.Path(fx_daily.__file__)


def _frame(closes, tz=None):
    index = pd.DatetimeIndex(list(closes), tz=tz)
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "Close": values}, index=index)


def _frame_rows(rows, tz=None):
    """Duplicate or unsorted stamps: (stamp, close) pairs in frame order."""
    return pd.DataFrame({"Close": [c for _, c in rows]},
                        index=pd.DatetimeIndex([s for s, _ in rows], tz=tz))


WEEK = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92, "2026-10-21": 0.93,
               "2026-10-22": 0.94, "2026-10-23": 0.95})


@pytest.mark.parametrize("day,expected", [
    (date(2026, 10, 19), None),                              # first bar: nothing before it
    (date(2026, 10, 20), (0.91, date(2026, 10, 19))),
    (date(2026, 10, 21), (0.92, date(2026, 10, 20))),        # strictly before: not 0.93
    (date(2026, 10, 24), (0.95, date(2026, 10, 23))),        # after the last bar
    (date(2026, 10, 26), (0.95, date(2026, 10, 23))),        # Monday after the weekend gap
    (date(2026, 10, 30), (0.95, date(2026, 10, 23))),        # 7 days after the bar: still served
    (date(2026, 10, 31), None),                              # 8 days: fx_missing, never stale
])
def test_last_positive_close_strictly_before_the_day(day, expected):
    assert fx_daily.rate_before(WEEK, day) == expected


def test_nan_and_non_positive_closes_are_skipped():
    frame = _frame({"2026-10-19": 0.91, "2026-10-20": float("nan"), "2026-10-21": 0.0,
                    "2026-10-22": -1.0})
    assert fx_daily.rate_before(frame, date(2026, 10, 23)) == (0.91, date(2026, 10, 19))


def test_a_string_close_is_coerced_or_skipped():
    frame = pd.DataFrame({"Close": ["0.9", "bad"]},
                         index=pd.DatetimeIndex(["2026-10-19", "2026-10-20"]))
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.9, date(2026, 10, 19))


def test_duplicate_stamps_take_the_last_row_of_the_newest_date():
    frame = _frame_rows([("2026-10-19", 0.91), ("2026-10-20", 0.92), ("2026-10-20", 0.925)])
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.925, date(2026, 10, 20))


def test_unsorted_stamps_take_the_newest_date_wherever_it_sits():
    frame = _frame_rows([("2026-10-21", 0.93), ("2026-10-19", 0.91), ("2026-10-20", 0.92)])
    assert fx_daily.rate_before(frame, date(2026, 10, 22)) == (0.93, date(2026, 10, 21))
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))


def test_a_tz_aware_index_keeps_its_own_wall_date():
    london = _frame({"2026-10-20 00:00": 0.92}, tz="Europe/London")
    assert fx_daily.rate_before(london, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))
    assert fx_daily.rate_before(london, date(2026, 10, 20)) is None
    late_utc = _frame({"2026-10-20 23:00": 0.92}, tz="UTC")       # Berlin would say 10-21
    assert fx_daily.rate_before(late_utc, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))


@pytest.mark.parametrize("frame", [None, pd.DataFrame(),
                                   pd.DataFrame({"Open": [1.0]}, index=pd.DatetimeIndex(["2026-10-19"]))])
def test_no_frame_no_rows_or_no_close_column_is_none(frame):
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) is None


def test_the_answer_is_a_plain_float_and_date():
    rate, bar = fx_daily.rate_before(WEEK, date(2026, 10, 21))
    assert type(rate) is float and type(bar) is date and math.isfinite(rate)


def test_fallback_days_is_seven():
    assert fx_daily.FALLBACK_DAYS == 7


def test_the_module_imports_neither_fx_nor_admin_nor_flask():
    names = set()
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    assert "swingbot.core.marketdata.fx" not in names
    assert not any(n.startswith(("swingbot.admin", "flask")) for n in names), names
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_daily.py`
Expected: collection fails with `ImportError: cannot import name 'fx_daily' from 'swingbot.core.marketdata'`.

- [ ] **Step 3: Write `fx_daily.py`**

Create `<wt>/swingbot/core/marketdata/fx_daily.py`:

```python
"""v205 L1-a: one FX rate per currency pair per Berlin day.

`rate_before` is the one rule the 08:00 snap and the backfill both use
(core/marketdata/fx_snap.py): the last positive daily close dated strictly
before day D, so the value known at 08:00 Berlin on D is reproducible from the
frames (snap(D) == backfill(D)). `lookup` (V205-12b) serves those stored rows
(`fx_daily_rates`) from a process memo keyed on the table's version.

Display only, like `fx`: a missing rate is None (the caller flags `fx_missing`),
never 1.0, and an unreadable table is a miss, never an exception. Codes in and
out are MAJOR ISO codes; the caller applies a minor unit's scale. This module
imports nothing from `fx` (fx imports it) and nothing from the admin.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

#: How old the bar behind a rate may be. A long weekend plus a holiday is four
#: days; a week covers every market closure without letting a stale rate stand
#: in for a missing one. `fx.FALLBACK_DAYS` is this object (V205-15).
FALLBACK_DAYS = 7


def _clock() -> float:
    """Monotonic seconds; the seam tests replace (never a patched stdlib `time`)."""
    return time.monotonic()


def _bar_dates(index) -> np.ndarray:
    """Each stamp's own calendar date as datetime64[D]; a tz-aware index keeps its wall date."""
    stamps = pd.DatetimeIndex(pd.to_datetime(index))
    if stamps.tz is not None:
        stamps = stamps.tz_localize(None)
    return stamps.normalize().to_numpy().astype("datetime64[D]")


def rate_before(frame: pd.DataFrame | None, day: date) -> tuple[float, date] | None:
    """`(close, bar_date)` of the last positive close dated strictly before `day`,
    or None when there is none or its bar is more than FALLBACK_DAYS before `day`."""
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return None
    dates = _bar_dates(frame.index)
    closes = pd.to_numeric(frame["Close"], errors="coerce").to_numpy(dtype=float)
    keep = (dates < np.datetime64(day, "D")) & np.isfinite(closes) & (closes > 0)
    if not keep.any():
        return None
    kept_dates, kept_closes = dates[keep], closes[keep]
    newest = kept_dates.max()
    position = int(np.flatnonzero(kept_dates == newest)[-1])
    bar_date = newest.astype(object)
    if (day - bar_date).days > FALLBACK_DAYS:
        return None
    return float(kept_closes[position]), bar_date
```

`newest.astype(object)` turns a `datetime64[D]` scalar into a `datetime.date`, so the answer compares equal to `date(...)` literals and subtracts from `day`. `log` is declared here for V205-12b's `swallowed` call.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_daily.py`
Expected: `18 passed`, `0 failed`.

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx_daily.py` -- every function `A` or `B` (under 10); `python <wt>/scripts/dev/complexity_gate.py` clean.

- [ ] **Step 5: Add the module-map entry**

In `<wt>/docs/claude/architecture.md`, the `core/marketdata/` entry currently reads:

```text
  v190 the PIT store's integrity reader `pit_integrity.py`; instrument v3
  selects that store through `training_data.select(name, store, until)`), `core/market/`
```

Change it to:

```text
  v190 the PIT store's integrity reader `pit_integrity.py`; instrument v3
  selects that store through `training_data.select(name, store, until)`;
  v205 `fx_daily.py`, the admin's one FX rate per pair per Berlin day: the
  rule `rate_before` and the `fx_daily_rates` memo), `core/market/`
```

If V205-6's `read_memo` edit or another commit has moved these lines, insert the same text before the `), \`core/market/\`` that closes the `core/marketdata/` parenthesis.

Codex mirror: run `git -C <wt> grep -n "pit_integrity" -- AGENTS.md`. No hit means `AGENTS.md` carries no module list and needs nothing. A hit means you add `fx_daily.py` there in the same condensed form, in this commit. Then run `python <wt>/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` -- expected `0 failed`.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/fx_daily.py tests/marketdata/test_fx_daily.py
git -C <wt> commit -m "feat(marketdata): fx_daily.rate_before, the last positive close strictly before a day (v205 V205-12)"
git -C <wt> add docs/claude/architecture.md
git -C <wt> commit -m "docs(claude): fx_daily in the core/marketdata module map (v205 V205-12)"
```

(Add `AGENTS.md` to the second commit only if Step 5 changed it.)

