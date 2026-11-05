# Admin read performance, Layer 1 -- Part 2: budgets and the read memo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-c. Load each store once per request: opt-in, read routes only", "L1-d. Measurement stays in the product", "Testing".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

Tasks in this part: V205-5 (per-endpoint statement and `list_all` budgets on the golden book), V205-6 (the core `contextvars` read memo), V205-7 (`TradeLog._all`, `PlanStore._all` and `account._sum_realized_pnl` read through it), V205-8 (the nested-write audit, proven by a deep-frozen memo over all eight endpoints). Nothing in this part switches the memo on in production: no route carries `@read_scope` until V205-9 (part 3), so V205-7 and V205-8 must pass the V205-4 goldens and the V205-5 budgets **unchanged**.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

# Phase 1 -- Measurement (L1-d), continued

### Task V205-5: Per-endpoint budgets: statement count and `list_all` calls

**Model:** sonnet — one new test file over existing fixtures; the only judgement is reading the probe and copying its numbers.

**Files:**
- Create: `tests/admin_perf/test_budgets.py`

**Interfaces:**
- Consumes (V205-1): `admin_endpoint_timing.parse_server_timing(header) -> dict` (reached as `golden_book.admin_endpoint_timing`, which `golden_book.py` already imports). (V205-2): fixture `sql_counted`. (V205-3): every `/api/v1` response carries `Server-Timing: total;dur=..., db;dur=...;desc="<n> statements"`. (V205-4): `golden_book.ENDPOINTS`, fixtures `golden_seed`, `frozen_clock`, `logged_in`.
- Produces (ledger): `BUDGETS: dict[str, tuple[int, int]]` in `tests/admin_perf/test_budgets.py` -- endpoint name -> (max SQL statements, max `Repository.list_all` calls) for **one cold request** on the golden book, today's measured values. Tests assert `<=`. V205-9 lowers the second number per endpoint once `@read_scope` is on; nothing else edits `BUDGETS`.
- Produces: helper `_cost(client, name, monkeypatch) -> tuple[int, list[str]]` (statement count, the repository class name of each `list_all` call, in call order). V205-9 reuses it by import (`from tests.admin_perf.test_budgets import BUDGETS, _cost`).

Facts (verified): every store read goes through `Repository.list_all` (`swingbot/core/db/repositories/base.py:59`); no repository overrides it (`git grep -n "def list_all" -- swingbot/` has one hit), so patching the base method counts every subclass: `TradeLog._all` and `account._sum_realized_pnl` both reach it through `trades_repo()` (class `TradeRepository`), `PlanStore._all` through `plans_repo()` (class `PlanRepository`). Statement counts come from the response's `Server-Timing` header, which `request_timing`'s listener fills on the test engine once `sql_counted` has attached it (V205-2).

A "cold request" is the first GET after `golden_seed`: each test gets a fresh `golden_seed`, which empties `fx._frames`, `fx._quote_codes` and the risk cache, so the numbers do not depend on test order or on xdist placement.

- [ ] **Step 1: Write the failing test file**

Create `tests/admin_perf/test_budgets.py`:

```python
"""v205 V205-5: what one cold request of each profiled endpoint costs on the golden book.

BUDGETS[name] = (max SQL statements, max Repository.list_all calls), measured on
pre-memo code (V205-5) by test_probe_records_todays_cost and copied in by hand. The
tests assert <=, so a change that makes an endpoint cheaper still passes and one that
makes it dearer fails here rather than on a page. V205-9 lowers the list_all numbers
once @read_scope is on; nothing else edits BUDGETS.

The comment after each entry is the probe's list_all call list: which stores the
endpoint loaded, and how many times, before v205."""
import json
import os

import pytest

from swingbot.core.db.repositories.base import Repository
from tests.admin_perf import golden_book as gb

NAMES = list(gb.ENDPOINTS)

BUDGETS: dict[str, tuple[int, int]] = {}


def _cost(client, name, monkeypatch) -> tuple[int, list[str]]:
    """(SQL statements, list_all caller classes) of one GET of ``name``."""
    calls: list[str] = []
    real = Repository.list_all

    def counting(self, *args, **kwargs):
        calls.append(type(self).__name__)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Repository, "list_all", counting)
    try:
        response = client.get(gb.ENDPOINTS[name])
    finally:
        monkeypatch.setattr(Repository, "list_all", real)
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    timing = gb.admin_endpoint_timing.parse_server_timing(response.headers.get("Server-Timing"))
    assert "db" in timing, f"{name}: no Server-Timing db entry: {response.headers.get('Server-Timing')!r}"
    return int(timing["db"]["statements"]), calls


@pytest.mark.skipif(not os.environ.get("ADMIN_PERF_PROBE"),
                    reason="probe only: ADMIN_PERF_PROBE=<file> appends today's cost per endpoint")
@pytest.mark.parametrize("name", NAMES)
def test_probe_records_todays_cost(name, golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, name, monkeypatch)
    with open(os.environ["ADMIN_PERF_PROBE"], "a", encoding="utf-8") as out:
        out.write(json.dumps({"name": name, "statements": statements,
                              "list_all": len(calls), "calls": calls}) + "\n")


def test_every_endpoint_has_a_budget():
    assert list(BUDGETS) == NAMES
    for name, budget in BUDGETS.items():
        assert len(budget) == 2, name
        statements, list_all = budget
        assert isinstance(statements, int) and statements > 0, name
        assert isinstance(list_all, int) and list_all >= 0, name


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_stays_within_its_budget(name, golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, name, monkeypatch)
    max_statements, max_list_all = BUDGETS[name]
    assert statements <= max_statements, f"{name}: {statements} SQL statements > budget {max_statements}"
    assert len(calls) <= max_list_all, f"{name}: list_all x{len(calls)} > budget {max_list_all}: {calls}"


def test_the_counters_see_a_request(golden_seed, frozen_clock, sql_counted, logged_in, monkeypatch):
    statements, calls = _cost(logged_in, "dashboard", monkeypatch)
    assert statements > 0
    assert "TradeRepository" in calls and "PlanRepository" in calls, calls
```

- [ ] **Step 2: Run it to verify it fails**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`
Expected: `test_every_endpoint_has_a_budget` FAILS (`[] == ['dashboard', ...]`) and every `test_endpoint_stays_within_its_budget[*]` FAILS with `KeyError`; `test_the_counters_see_a_request` PASSES (it proves the counters are wired before you trust the probe). If it fails with "no Server-Timing db entry", V205-3's `install(app)` is not reached through `admin_app`'s reload: stop and report; never patch the header in this file.

- [ ] **Step 3: Run the probe**

Pick a scratch file outside the worktree, e.g. `<scratch>/v205_budgets.jsonl` (delete it first if it exists), then:

Run: `ADMIN_PERF_PROBE=<scratch>/v205_budgets.jsonl python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`
Expected: the 8 `test_probe_records_todays_cost[*]` pass (the Step 2 failures remain), and the file holds 8 JSON lines, one per endpoint.

Run the probe a **second** time into a second file and compare them (sorted by `name`): they must agree line for line. A difference means an outside read is not pinned by `golden_seed` (a cache warmed by an earlier test, a clock read). Find it and pin it in `golden_seed` (V205-4's conftest) in this task's commit, never by widening a budget; then re-run both probes.

- [ ] **Step 4: Copy the measured numbers into `BUDGETS`, by hand**

Replace `BUDGETS: dict[str, tuple[int, int]] = {}` with one entry per endpoint, **in `NAMES` order** (`dashboard`, `dashboard_today`, `trades`, `trades_open`, `live`, `calendar_month`, `calendar_day`, `calendar_sparklines`), each the probe's exact `(statements, list_all)` -- no headroom, no rounding -- with the probe's `calls` list as the comment. The shape, shown for the first entry with the probe's two numbers standing in as `S` and `L`:

```python
BUDGETS: dict[str, tuple[int, int]] = {
    "dashboard": (S, L),  # list_all: TradeRepository x.., PlanRepository x.. (probe, pre-v205)
    # ... the other seven, same shape, NAMES order
}
```

Every `S`/`L` is the integer literal the probe wrote. Expect `dashboard` to show several `PlanRepository` and `TradeRepository` calls (production showed 8 `list_all` calls on `/dashboard`); a `dashboard` entry with one call of each means the wrong book or the wrong route, so re-check Step 3.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_budgets.py`
Expected: `10 passed, 8 skipped` (the probe skips without `ADMIN_PERF_PROBE`), `0 failed`.

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf` -- expected `0 failed`, `0 xfailed`.

`git -C <wt> diff --stat -- swingbot/` must be empty for this task.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add tests/admin_perf/test_budgets.py
git -C <wt> commit -m "test(admin): per-endpoint SQL and list_all budgets on the golden book (v205 V205-5)"
```

(If Step 3 pinned a missed outside read, add `tests/admin_perf/conftest.py` to the same commit and name the read in the message body.)

# Phase 2 -- Load each store once per request (L1-c)

### Task V205-6: Core read memo (`contextvars`)

**Model:** sonnet — a small stdlib-only module against a fully specified contract; the thread and nesting cases are spelled out below.

**Files:**
- Create: `swingbot/core/infra/read_memo.py`
- Create: `tests/infra/test_read_memo.py` (suite `discord`, which owns `tests/infra/`)
- Modify: `docs/claude/architecture.md` (the `core/infra/` module list, lines ~31-33)

**Interfaces:**
- Consumes: nothing from `swingbot` (leaf module: stdlib only, like `swingbot/core/infra/swallowed.py`).
- Produces (index "Read memo"), consumed by V205-7 (stores), V205-8 (audit test) and V205-9 (`read_scope`):
  - `TRADE_ROWS = "trade_rows"`, `TRADES = "trades"`, `PLANS = "plans"`.
  - `scope() -> ContextManager[None]`: sets a fresh `dict` in contextvar `_MEMO`, resets its token in `finally`; a nested `scope()` reuses the outer memo and leaves it in place on exit.
  - `active() -> bool`.
  - `records(key: str, loader: Callable[[], list[dict]]) -> list[dict]`: outside a scope `loader()` unchanged (the very objects it returns); inside, the first call per key stores `loader()` and every call returns `[dict(r) for r in stored]`.
  - `mapping(key: str, loader: Callable[[], dict[str, dict]]) -> dict[str, dict]`: the same, returning `{k: dict(v) for k, v in stored.items()}`.
  - `peek(key: str) -> object | None`: test seam, the stored value or `None` (also `None` outside a scope).
- Callers **must** call through the module (`from swingbot.core.infra import read_memo`; `read_memo.records(...)`), never `from ...read_memo import records`: V205-8's audit test replaces `read_memo.records`/`read_memo.mapping` to deep-freeze what is stored.

Design notes the tests pin:
- The copies are **shallow** by contract (index Global Constraints): each caller owns the top level of every record it gets, exactly as it owns the fresh dicts `_all()` builds today; nested values (`legs`, `status_history`, ...) are shared within one scope. V205-8 proves no read path writes into them.
- A loader that raises stores nothing; the next call retries it.
- One gunicorn worker serves 16 threads (`deploy/gunicorn.conf.py`). Each thread has its own context, so two concurrent requests never share a memo; the `finally` reset means a request that raises never leaves its memo on a pooled thread.

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_read_memo.py`:

```python
"""v205 V205-6: the opt-in per-request read memo (index "Read memo")."""
import ast
import sys
import threading
from pathlib import Path

import pytest

from swingbot.core.infra import read_memo

SOURCE = Path(read_memo.__file__)


class _Loader:
    """Counts its calls; returns fresh nested records each time, like a repository."""

    def __init__(self):
        self.calls = 0

    def rows(self):
        self.calls += 1
        return [{"id": "a", "legs": [{"r": 1.0}]}, {"id": "b", "legs": []}]

    def by_id(self):
        return {row["id"]: row for row in self.rows()}


def test_outside_a_scope_every_call_is_the_loader_itself():
    loader = _Loader()
    first = read_memo.records(read_memo.TRADES, loader.rows)
    second = read_memo.records(read_memo.TRADES, loader.rows)
    assert loader.calls == 2 and first == second
    assert read_memo.active() is False and read_memo.peek(read_memo.TRADES) is None


def test_outside_a_scope_the_loaders_own_objects_come_back():
    stored = [{"id": "a"}]
    assert read_memo.records(read_memo.TRADES, lambda: stored) is stored
    mapping = {"a": {"id": "a"}}
    assert read_memo.mapping(read_memo.PLANS, lambda: mapping) is mapping


def test_inside_a_scope_the_loader_runs_once_per_key():
    loader = _Loader()
    with read_memo.scope():
        assert read_memo.active() is True
        first = read_memo.records(read_memo.TRADES, loader.rows)
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert loader.calls == 1 and first == second
        read_memo.records(read_memo.TRADE_ROWS, loader.rows)
        assert loader.calls == 2                     # a second key loads on its own
    assert read_memo.active() is False


def test_each_call_gets_its_own_top_level_copies():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.records(read_memo.TRADES, loader.rows)
        first[0]["id"] = "changed"
        first.append({"id": "extra"})
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert [row["id"] for row in second] == ["a", "b"]
        assert first[1] is not second[1]
        stored = read_memo.peek(read_memo.TRADES)
        assert all(row is not stored_row for row, stored_row in zip(second, stored))


def test_copies_are_shallow_by_contract():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.records(read_memo.TRADES, loader.rows)
        second = read_memo.records(read_memo.TRADES, loader.rows)
        assert first[0]["legs"] is second[0]["legs"]  # V205-8 proves no reader writes here


def test_mapping_copies_each_value():
    loader = _Loader()
    with read_memo.scope():
        first = read_memo.mapping(read_memo.PLANS, loader.by_id)
        first["a"]["id"] = "changed"
        del first["b"]
        second = read_memo.mapping(read_memo.PLANS, loader.by_id)
        assert loader.calls == 1
        assert list(second) == ["a", "b"] and second["a"]["id"] == "a"


def test_a_nested_scope_reuses_and_keeps_the_outer_memo():
    loader = _Loader()
    with read_memo.scope():
        read_memo.records(read_memo.TRADES, loader.rows)
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, loader.rows)
            assert loader.calls == 1
        assert read_memo.active() is True
        assert read_memo.peek(read_memo.TRADES) is not None
        read_memo.records(read_memo.TRADES, loader.rows)
        assert loader.calls == 1
    assert read_memo.active() is False


def test_a_raising_body_still_resets_the_scope():
    with pytest.raises(RuntimeError):
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, _Loader().rows)
            raise RuntimeError("view failed")
    assert read_memo.active() is False and read_memo.peek(read_memo.TRADES) is None


def test_a_raising_loader_stores_nothing():
    loader = _Loader()

    def broken():
        raise ConnectionError("db down")

    with read_memo.scope():
        with pytest.raises(ConnectionError):
            read_memo.records(read_memo.TRADES, broken)
        assert read_memo.peek(read_memo.TRADES) is None
        assert len(read_memo.records(read_memo.TRADES, loader.rows)) == 2
        assert loader.calls == 1


def test_two_threads_never_share_a_memo():
    barrier = threading.Barrier(2)
    seen: dict[str, list[str]] = {}

    def request(tag):
        with read_memo.scope():
            read_memo.records(read_memo.TRADES, lambda: [{"id": tag}])
            barrier.wait(timeout=5)                  # both scopes are open at once
            seen[tag] = [row["id"] for row in read_memo.records(read_memo.TRADES, lambda: [])]

    threads = [threading.Thread(target=request, args=(tag,)) for tag in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert seen == {"one": ["one"], "two": ["two"]}


def test_peek_of_a_key_never_loaded_is_none():
    with read_memo.scope():
        assert read_memo.peek(read_memo.PLANS) is None


def test_it_is_a_leaf_module():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_read_memo.py`
Expected: collection error, `ImportError: cannot import name 'read_memo' from 'swingbot.core.infra'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/infra/read_memo.py`:

```python
"""Load each store once per admin read request (v205 L1-c).

A leaf module: it imports nothing from ``swingbot`` (or flask), so core stores
can read through it without a core -> admin import.

The memo is **opt-in**. Nothing is memoised unless a caller has entered
``scope()``; the admin's GET views do so through ``@read_scope``
(``swingbot/admin/api_v1/read_scope.py``). Outside a scope -- the bot, the
refresher, scripts, every write -- ``records()``/``mapping()`` return the
loader's own result, exactly today's direct call.

Inside a scope the first call per key stores the loader's result and every call
returns **shallow copies** of it (a new list or dict of new top-level dicts), so
each caller owns its records' top level as it owns the fresh dicts a store's
``_all()`` builds. Nested values are shared within the scope; no read path may
write into them (V205-8's frozen-memo test). A store call that passes ``conn``
(a transaction) never reads through here.

The memo lives in a ``contextvars.ContextVar``: each gunicorn thread has its own
context, and ``scope()`` resets its token in ``finally``, so no memo outlives
its request or crosses to another thread.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Callable, Iterator

TRADE_ROWS = "trade_rows"   # account._sum_realized_pnl: normalised trades rows
TRADES = "trades"           # TradeLog._all: trades in TradeLog's JSON shape
PLANS = "plans"             # PlanStore._all: plan_id -> plan record

_MEMO: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "swingbot_read_memo", default=None)


@contextlib.contextmanager
def scope() -> Iterator[None]:
    """Memoise store reads until the block exits; a nested scope reuses the outer memo."""
    if _MEMO.get() is not None:
        yield
        return
    token = _MEMO.set({})
    try:
        yield
    finally:
        _MEMO.reset(token)


def active() -> bool:
    """True inside ``scope()``."""
    return _MEMO.get() is not None


def _stored(key: str, loader: Callable[[], object]) -> object | None:
    """The memoised value for ``key`` (loading it once), or None outside a scope."""
    memo = _MEMO.get()
    if memo is None:
        return None
    if key not in memo:
        memo[key] = loader()          # a raising loader stores nothing
    return memo[key]


def records(key: str, loader: Callable[[], list[dict]]) -> list[dict]:
    """``loader()`` outside a scope; inside, per-call shallow copies of the memoised records."""
    if not active():
        return loader()
    return [dict(record) for record in _stored(key, loader)]


def mapping(key: str, loader: Callable[[], dict[str, dict]]) -> dict[str, dict]:
    """``loader()`` outside a scope; inside, a per-call copy with each value copied."""
    if not active():
        return loader()
    return {name: dict(record) for name, record in _stored(key, loader).items()}


def peek(key: str) -> object | None:
    """Test seam: the stored value for ``key``, or None (never loads)."""
    memo = _MEMO.get()
    return None if memo is None else memo.get(key)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_read_memo.py`
Expected: `12 passed`, `0 failed`.

Run: `python -m radon cc -s <wt>/swingbot/core/infra/read_memo.py` -- every function `A` (well under 15).

- [ ] **Step 5: Add the module-map entry**

In `<wt>/docs/claude/architecture.md`, the `core/infra/` entry currently reads:

```text
  shared by the equity recorder, the backfill and the admin), `core/infra/`
  (JSON, locks and delivery channels — `jsonio.py`, `state.py`,
  `notifier.py`, `silent_channel.py`), plus the four that predate the
```

Change it to:

```text
  shared by the equity recorder, the backfill and the admin), `core/infra/`
  (JSON, locks and delivery channels — `jsonio.py`, `state.py`,
  `notifier.py`, `silent_channel.py`; v205 `read_memo.py`, the opt-in
  `contextvars` memo that loads each store once per admin GET request,
  switched on only by `@read_scope`), plus the four that predate the
```

Codex mirror (`CLAUDE.md` § Claude is the operator): run `git -C <wt> grep -n "silent_channel" -- AGENTS.md`. No hit means `AGENTS.md` carries no module list and needs nothing; a hit means add `read_memo.py` there in the same condensed form in this commit. Then run `python <wt>/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` -- expected `0 failed`.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/infra/read_memo.py tests/infra/test_read_memo.py
git -C <wt> commit -m "feat(core): opt-in contextvars read memo for admin GET requests (v205 V205-6)"
git -C <wt> add docs/claude/architecture.md
git -C <wt> commit -m "docs(claude): read_memo in the core/infra module map (v205 V205-6)"
```

(Add `AGENTS.md` to the second commit only if Step 5 changed it.)

### Task V205-7: Stores read through the memo: `TradeLog._all`, `PlanStore._all`, `_sum_realized_pnl`

**Model:** opus — the three hottest store reads in core change shape; bot paths and write transactions must stay byte-identical, which needs care about every caller of `_all()`.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (`TradeLog._all`, line ~786; new module-level `_load_trade_records` beside `_json_record`, line ~705; one import)
- Modify: `swingbot/core/planning/plan_store.py` (`PlanStore._all`, line ~76; new module-level `_load_plan_records` beside `_normalised`; one import)
- Modify: `swingbot/core/planning/account.py` (`_sum_realized_pnl`, line ~86; new helper `_trade_rows(conn)`; one import)
- Create: `tests/infra/test_read_memo_stores.py` (suite `discord`)

**Interfaces:**
- Consumes (V205-6): `read_memo.records`, `read_memo.mapping`, `read_memo.scope`, `read_memo.peek`, keys `TRADES`, `PLANS`, `TRADE_ROWS`. Called **through the module** (`read_memo.records(...)`), so V205-8's test can replace them.
- Produces (ledger "Keys `read_memo.TRADE_ROWS`, `TRADES`, `PLANS`; `conn` given -> bypass"):
  - `TradeLog._all()` = `read_memo.records(read_memo.TRADES, _load_trade_records)`; `performance._load_trade_records() -> list[dict]` is today's body (`[_json_record(row) for row in trades_repo().list_all()]`).
  - `PlanStore._all()` = `read_memo.mapping(read_memo.PLANS, _load_plan_records)`; `plan_store._load_plan_records() -> dict[str, dict]` is today's body.
  - `account._trade_rows(conn) -> list[dict]`: with `conn`, `normalise(trades_repo().list_all(conn=conn))`, never memoised; without, `read_memo.records(read_memo.TRADE_ROWS, lambda: normalise(trades_repo().list_all()))`. `_sum_realized_pnl` calls it; its loop is unchanged.
  - V205-9 relies on: inside one scope, every `TradeLog`/`PlanStore` read and every standalone `_sum_realized_pnl` costs at most one `list_all` per key.

Facts (verified): `TradeLog._all` and `PlanStore._all` take no `conn`; every transactional read goes through its own locked path (`TradeLog._open_trade_for_plan(conn=...)` branches before `_all()`, `PlanStore.lock_for_update(conn=...)` reads the repository), so the memo never sees a transaction except through `_sum_realized_pnl(conn=...)`, which bypasses it. `_json_record` and `codec.normalise` build fully fresh nested values today; inside a scope the nested values become shared within that scope (the V205-6 contract), which V205-8 audits. Test doubles for `list_all` take `**_kw` (`tests/planning/test_plan_store_records.py:13`) or no arguments: the standalone calls stay `list_all()` with no arguments, exactly as today (`account._with_conn`'s docstring). `swingbot/admin/api_v1/live_events.py` and `cancel_precision.py` have their own `_load_plans`/`_load_trades`; the new names here are distinct on purpose.

Outside a scope nothing changes: the bot, the refresher, every script and every write call the loader directly. No route carries `@read_scope` before V205-9, so in production this task changes no behaviour at all; the goldens and budgets prove it.

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_read_memo_stores.py`:

```python
"""v205 V205-7: TradeLog, PlanStore and the account's realized-P&L sum read through the
read memo -- once per scope and key, today's direct read outside a scope, and never for
a call inside a transaction."""
import copy
from datetime import datetime, timezone

import pytest

from swingbot.core.infra import read_memo
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog


def _trade(trade_id, ticker, status, opened, *, pnl=None, legs=()):
    return {"trade_id": trade_id, "horizon": "2w", "ticker": ticker, "strategy": "RSI",
            "direction": "bullish", "status": status, "entry": 100.0, "stop_loss": 95.0,
            "shares": 2, "opened_at": opened, "closed_at": None,
            "realized_pnl_amount": pnl, "legs": list(legs)}


TRADES = [
    _trade("T1", "AAPL", "win", "2026-01-02T15:00:00+00:00", pnl=50.0),
    # settled from its legs: 2 shares x 1.0 x (95 - 100) = -10.0
    _trade("T2", "MSFT", "loss", "2026-01-03T15:00:00+00:00", legs=[{"fraction": 1.0, "exit_price": 95.0}]),
    _trade("T3", "NVDA", "open", "2026-01-04T15:00:00+00:00"),
]
PLANS = [
    {"plan_id": "P1", "ticker": "AAPL", "status": "ACTIVE", "status_history": [],
     "created_at": datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)},
    {"plan_id": "P2", "ticker": "MSFT", "status": "PENDING", "status_history": [],
     "created_at": datetime(2026, 1, 3, 8, 0, tzinfo=timezone.utc)},
]
REALIZED = 40.0          # 50.0 + (-10.0); T3 is open


class _Repo:
    """A repository double: fresh nested rows per call, each call's kwargs recorded."""

    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def list_all(self, **kwargs):
        self.calls.append(kwargs)
        return copy.deepcopy(self.rows)


@pytest.fixture
def trades(monkeypatch):
    repo = _Repo(TRADES)
    monkeypatch.setattr("swingbot.core.db.repositories.trades.trades_repo", lambda: repo)
    return repo


@pytest.fixture
def plans(monkeypatch):
    repo = _Repo(PLANS)
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: repo)
    return repo


def test_outside_a_scope_every_read_is_a_fresh_query(trades, plans):
    TradeLog()._all()
    TradeLog().get_trades(status=None, limit=None)
    assert account._sum_realized_pnl() == REALIZED
    assert account._sum_realized_pnl() == REALIZED
    PlanStore().records()
    PlanStore().get_record("P1")
    assert trades.calls == [{}, {}, {}, {}]           # list_all() with no arguments, as today
    assert plans.calls == [{}, {}]


def test_inside_a_scope_each_key_loads_once(trades, plans):
    with read_memo.scope():
        TradeLog()._all()
        TradeLog().get_trades(status=None, limit=None)
        TradeLog().get_trades(status="win", limit=None)
        assert len(trades.calls) == 1
        assert account._sum_realized_pnl() == REALIZED
        assert account._sum_realized_pnl() == REALIZED
        assert len(trades.calls) == 2                  # TRADE_ROWS is its own key
        PlanStore().records()
        PlanStore().get_record("P1")
        assert PlanStore().get_record("missing") is None
        assert len(plans.calls) == 1


def test_scoped_reads_equal_direct_reads(trades, plans):
    direct = (TradeLog()._all(), PlanStore()._all(), account._sum_realized_pnl())
    with read_memo.scope():
        for _ in range(2):
            assert (TradeLog()._all(), PlanStore()._all(), account._sum_realized_pnl()) == direct


def test_each_caller_owns_the_top_level_of_its_records(trades, plans):
    with read_memo.scope():
        first = TradeLog()._all()
        first[0]["status"] = "changed"
        first.pop()
        again = TradeLog()._all()
        assert [t["status"] for t in again] == ["win", "loss", "open"]
        record = PlanStore().get_record("P1")
        record["status"] = "CLOSED"
        assert PlanStore().get_record("P1")["status"] == "ACTIVE"


def test_a_transaction_never_reads_through_the_memo(trades):
    conn = object()
    with read_memo.scope():
        assert account._sum_realized_pnl(conn=conn) == REALIZED
        assert account._sum_realized_pnl(conn=conn) == REALIZED
        assert read_memo.peek(read_memo.TRADE_ROWS) is None
        assert account._sum_realized_pnl() == REALIZED
        assert read_memo.peek(read_memo.TRADE_ROWS) is not None
    assert trades.calls == [{"conn": conn}, {"conn": conn}, {}]


def test_the_memo_holds_each_stores_parsed_shape(trades, plans):
    with read_memo.scope():
        TradeLog()._all()
        PlanStore().records()
        account._sum_realized_pnl()
        assert [t["id"] for t in read_memo.peek(read_memo.TRADES)] == ["T1", "T2", "T3"]
        assert "trade_id" not in read_memo.peek(read_memo.TRADES)[0]
        assert read_memo.peek(read_memo.PLANS)["P1"]["created_at"] == "2026-01-02T08:00:00+00:00"
        assert read_memo.peek(read_memo.TRADE_ROWS)[0]["trade_id"] == "T1"


def test_the_stores_call_the_memo_through_its_module(trades, plans, monkeypatch):
    seen = []
    real_records, real_mapping = read_memo.records, read_memo.mapping
    monkeypatch.setattr(read_memo, "records", lambda key, loader: seen.append(key) or real_records(key, loader))
    monkeypatch.setattr(read_memo, "mapping", lambda key, loader: seen.append(key) or real_mapping(key, loader))
    TradeLog()._all()
    account._sum_realized_pnl()
    PlanStore().records()
    assert seen == [read_memo.TRADES, read_memo.TRADE_ROWS, read_memo.PLANS]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_read_memo_stores.py`
Expected: `test_outside_a_scope_every_read_is_a_fresh_query`, `test_scoped_reads_equal_direct_reads` and `test_each_caller_owns_the_top_level_of_its_records` PASS (today every read is fresh, so they pin what must not change); the other four FAIL (`assert 3 == 1` in `test_inside_a_scope_each_key_loads_once`, `peek(...) is not None` in the transaction and shape tests, `seen == []` in the module test).

- [ ] **Step 3: Route `TradeLog._all` through the memo**

In `<wt>/swingbot/core/tracking/performance.py`, add to the `swingbot` imports at the top (after `from swingbot import config`):

```python
from swingbot.core.infra import read_memo
```

Directly below `_json_record` (line ~705-718), add:

```python
def _load_trade_records() -> list[dict]:
    """Every trades row in TradeLog's JSON shape, read fresh (TradeLog._all's loader)."""
    from swingbot.core.db.repositories.trades import trades_repo
    return [_json_record(row) for row in trades_repo().list_all()]
```

Replace `TradeLog._all` (line ~786-789):

```python
    def _all(self) -> list[dict]:
        """Every trade, in TradeLog's API shape. v205: inside an admin read scope
        (``read_memo.scope()``) the table is read and parsed once per request and
        each call gets shallow copies; outside one, today's direct read."""
        return read_memo.records(read_memo.TRADES, _load_trade_records)
```

- [ ] **Step 4: Route `PlanStore._all` through the memo**

In `<wt>/swingbot/core/planning/plan_store.py`, add after `from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction`:

```python
from swingbot.core.infra import read_memo
```

Directly below `_normalised` (line ~55-59), add:

```python
def _load_plan_records() -> dict[str, dict]:
    """plan_id -> record, read fresh from the plans table (PlanStore._all's loader)."""
    from swingbot.core.db.repositories.plans import plans_repo
    return {record["plan_id"]: _normalised(record) for record in plans_repo().list_all()}
```

Replace `PlanStore._all` (line ~75-79):

```python
    @staticmethod
    def _all() -> dict[str, dict]:
        """Map plan ids to records from the plans table. v205: through the read
        memo (once per admin read request, per-call copies); outside a scope,
        today's direct read."""
        return read_memo.mapping(read_memo.PLANS, _load_plan_records)
```

- [ ] **Step 5: Route `_sum_realized_pnl`'s standalone read through the memo**

In `<wt>/swingbot/core/planning/account.py`, add after `from swingbot import config as app_config`:

```python
from swingbot.core.infra import read_memo
```

Directly above `_sum_realized_pnl`, add:

```python
def _trade_rows(conn) -> list[dict]:
    """Every trades row, normalised. Inside a caller's transaction (``conn``): read
    on it and never memoised. Standalone: through the v205 read memo, which outside
    an admin read scope is today's direct ``list_all()``."""
    from swingbot.core.db.codec import normalise
    from swingbot.core.db.repositories.trades import trades_repo
    if conn is not None:
        return normalise(trades_repo().list_all(conn=conn))
    return read_memo.records(read_memo.TRADE_ROWS, lambda: normalise(trades_repo().list_all()))
```

In `_sum_realized_pnl`, replace the three lines

```python
    from swingbot.core.db.repositories.trades import trades_repo
    from swingbot.core.db.codec import normalise
    trades = normalise(trades_repo().list_all(**_with_conn(conn)))
```

with

```python
    trades = _trade_rows(conn)
```

Leave the docstring and the summing loop unchanged. `_with_conn` stays (its other callers keep using it).

- [ ] **Step 6: Check every `_all()` caller is standalone**

Run: `git -C <wt> grep -n "_all()" -- swingbot/core/tracking/performance.py swingbot/core/planning/plan_store.py`
For each hit, confirm it is either in a method that takes no `conn` or on its `conn is None` branch (as `_open_trade_for_plan`). A hit reached with a live `conn` is a write transaction reading through the memo: stop and report it to the controller rather than routing it.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_read_memo_stores.py`
Expected: `7 passed`, `0 failed`.

The stores' own tests (these hit the database: run `/replicate-prod-db` first if this worktree has not yet):

Run: `python <wt>/scripts/dev/testrun.py file tests/tracking/test_tradelog_no_snapshot.py tests/tracking/test_tradelog_db_reads.py tests/tracking/test_tradelog_conn.py tests/tracking/test_tradelog_db_bulk.py tests/planning/test_plan_store_records.py tests/planning/test_plan_store_db_reads.py tests/planning/test_plan_store_guard.py tests/planning/test_account_db.py tests/planning/test_account_legs.py`
Expected: `0 failed` (unchanged: none of them opens a scope).

The goldens and budgets, **unchanged** (no route has a scope yet, so the memo is inert there):

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf`
Expected: `0 failed`, `0 xfailed`; `git -C <wt> diff --stat -- tests/admin_perf/` empty.

Complexity: `python -m radon cc -s <wt>/swingbot/core/planning/account.py <wt>/swingbot/core/tracking/performance.py <wt>/swingbot/core/planning/plan_store.py | grep -E "_trade_rows|_sum_realized_pnl|_load_trade_records|_load_plan_records| _all"` -- `_sum_realized_pnl` at or below its baseline `B7`, the new helpers `A`. Then `python <wt>/scripts/dev/complexity_gate.py` -- expected clean.

- [ ] **Step 8: Commit**

```bash
git -C <wt> add swingbot/core/tracking/performance.py swingbot/core/planning/plan_store.py swingbot/core/planning/account.py tests/infra/test_read_memo_stores.py
git -C <wt> commit -m "perf(core): trades, plans and the realized-P&L sum read through the read memo (v205 V205-7)"
```

### Task V205-8: Nested-write audit of GET-path mutators; deep copies where needed

**Model:** opus — proving that eight whole endpoints never write into shared nested values, and fixing any that do without changing their output, is cross-module judgement.

**Files:**
- Create: `tests/admin_perf/test_memo_isolation.py`
- Modify (only if Step 3 convicts them; the static audit below expects none): `swingbot/admin/api_v1/trades.py` (`_attach_current_prices`, `_attach_unrealized_pnl`, `_strip_internal_fields`), `swingbot/admin/queries.py`, `swingbot/admin/api_v1/dashboard.py`, or any other function a failing traceback names

**Interfaces:**
- Consumes (V205-6): `read_memo.scope`, `active`, `records`, `mapping`, `peek`, keys `TRADES`, `PLANS`, `TRADE_ROWS`. (V205-7): stores call `read_memo.records`/`read_memo.mapping` through the module; loaders `performance._load_trade_records()`, `plan_store._load_plan_records()`. (V205-4/4b): `golden_book` (`ENDPOINTS`, `golden_path`, `mask`), `money_reference.EXPECTED_MONEY`, fixtures `golden_seed`, `frozen_clock`, `logged_in`; the session `db_engine` fixture (`tests/conftest.py`).
- Produces: the audit verdict per mutator, recorded in the test module's docstring (ledger). Helpers `_freeze(value)`, `_freeze_record(record) -> dict`, fixtures `frozen_memo`, `no_writes` (local to this file). V205-9 runs this file again once `@read_scope` is on; it must stay green unchanged.

Why this task exists: today every `_all()` call builds fully fresh nested values (`_json_record` ends in `codec.normalise`, which rebuilds every list and dict). Inside a scope (V205-6 contract) each caller gets its own top level, but nested values (`legs`, `status_history`, `legs_realized`, `cohort_stats`, `quality_breakdown`, ...) are shared by every reader in the request. A reader that appends to a trade's `legs` would corrupt every later reader's view in the same request. The spec (L1-c, "Callers receive the same objects as today") requires each such writer to copy first.

**Static audit (2026-11-04, plan writer).** On the six scoped views' path (`api_v1/dashboard.py`, `api_v1/trades.py`, `api_v1/live.py`, `api_v1/calendar.py`, `admin/dashboard.py`, `admin/queries.py`, `core/analytics/pnl_calendar.py`, `core/tracking/equity.py`, `api_v1/risk_read_model.py`, `api_v1/risk.py`, `core/analytics/rank.py`, `core/marketdata/fx_convert.py`), `git grep -nE '\]\s*(\.append|\.extend|\.sort|\.insert|\.pop|\.update|\.setdefault)\(|\]\[[^]]+\]\s*=[^=]'` finds one hit, `pnl_calendar.py:430` `by_weekday[WEEKDAYS[index]].append(row)`, which appends to a local bucket list, not a record. `.status_history`/`.legs_realized` appends exist only on write paths (`trade_commands.py:177`, `plan_manager.py`, `plan_types.py:273`), never reached by a GET view. The three named candidates in `trades.py` write **top-level** keys of rows that `_row_from_plan`/`_row_from_trade` build as new dicts (`trades.py:258`, `:628`): `_attach_current_prices` (`:1391`, and `_attach_layer_prices`/`_attach_door_prices` under it) sets `current_price`, `current_price_stale`, `price_age_s`, `price_as_of`; `_attach_unrealized_pnl` (`:1308`) sets `pnl_pct`, `r_multiple`, `realized_pnl_amount`, `fx_missing`, `_display_shares`; `_strip_internal_fields` (`:1348`) pops `_display_shares`. `queries._ranked_plan_rows` builds new dicts from `plan_to_dict`. `PlanStore._normalised` rewrites `created_at` inside the loader, before anything is stored. **Expected verdict: nothing convicted.** Grep cannot see a write through an alias (`legs = t["legs"]; legs.append(...)`), so the frozen-memo test below is the proof, not the grep.

- [ ] **Step 1: Write the tests**

Create `tests/admin_perf/test_memo_isolation.py`:

```python
"""v205 V205-8: no read path writes into a memoised record's nested values.

Inside read_memo.scope() each caller gets shallow copies: the top level of a record
is the caller's own, but nested values (legs, status_history, legs_realized,
cohort_stats, ...) are shared by every reader in the request. This module
deep-freezes everything the memo stores and runs the eight profiled endpoints inside
a scope: a nested write raises TypeError, the endpoint answers 500, and the traceback
names the writer. A guard on the test engine also fails any INSERT/UPDATE/DELETE or
row lock issued while a scope is open: a scoped GET must never write.

Audit verdict, per GET-path mutator (static audit 2026-11-04 plus this module):
- api_v1/trades.py _attach_current_prices (+ _attach_layer_prices, _attach_door_prices):
  top-level keys of rows built fresh by _row_from_plan/_row_from_trade -- acquitted.
- api_v1/trades.py _attach_unrealized_pnl: top-level row keys -- acquitted.
- api_v1/trades.py _strip_internal_fields: pops a top-level row key -- acquitted.
- admin/queries.py _plan_rows/_ranked_plan_rows: new dicts from plan_to_dict -- acquitted.
- api_v1/dashboard.py: writes only into its own `out` dicts -- acquitted.
- core/analytics/pnl_calendar.py:430: appends to a local bucket list -- acquitted.
- core/marketdata/fx_convert.to_account_currency: copies each row before writing -- acquitted.
- core/planning/plan_store._normalised: rewrites created_at in the loader, before
  the memo stores the record -- acquitted.
(A conviction found by this module is recorded here as "convicted: <fix>".)

Limit: a C-level helper that writes a list in place without calling its methods
(heapq) would not be caught; none is used on these paths."""
import copy
import json

import pytest
import sqlalchemy as sa

from swingbot.core.db.codec import normalise
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.infra import read_memo
from swingbot.core.planning import plan_store
from swingbot.core.tracking import performance
from tests.admin_perf import golden_book as gb
from tests.admin_perf import money_reference as mr

NAMES = list(gb.ENDPOINTS)
_WRITES = ("INSERT", "UPDATE", "DELETE")


def _refuse(self, *args, **kwargs):
    raise TypeError("v205: a read path wrote into a memoised record's nested value; copy it first")


class _FrozenList(list):
    append = extend = insert = remove = pop = clear = sort = reverse = _refuse
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _refuse

    def __copy__(self):
        return list(self)

    def __deepcopy__(self, memo):
        return [copy.deepcopy(item, memo) for item in self]


class _FrozenDict(dict):
    __setitem__ = __delitem__ = __ior__ = _refuse
    update = pop = popitem = setdefault = clear = _refuse

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        return {key: copy.deepcopy(value, memo) for key, value in self.items()}


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


def _freeze_record(record: dict) -> dict:
    """A plain top-level dict (the caller's own copy is made from it) over frozen nested values."""
    return {key: _freeze(item) for key, item in record.items()}


@pytest.fixture
def frozen_memo(monkeypatch):
    """Everything the memo stores is deep-frozen below its top level."""
    real_records, real_mapping = read_memo.records, read_memo.mapping
    monkeypatch.setattr(read_memo, "records", lambda key, loader: real_records(
        key, lambda: [_freeze_record(record) for record in loader()]))
    monkeypatch.setattr(read_memo, "mapping", lambda key, loader: real_mapping(
        key, lambda: {name: _freeze_record(record) for name, record in loader().items()}))


@pytest.fixture
def no_writes(db_engine):
    """Statements that write or lock rows while a read scope is open."""
    seen: list[str] = []

    def guard(conn, cursor, statement, parameters, context, executemany):
        text = statement.lstrip().upper()
        if read_memo.active() and (text.startswith(_WRITES) or " FOR UPDATE" in text):
            seen.append(statement.strip().splitlines()[0][:160])

    sa.event.listen(db_engine, "before_cursor_execute", guard)
    yield seen
    sa.event.remove(db_engine, "before_cursor_execute", guard)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:600])
    return response.get_json()


def _matches_golden(name, live) -> bool:
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    return gb.mask(live, pointers) == gb.mask(golden, pointers)


def test_the_frozen_memo_refuses_nested_writes_only():
    record = _freeze_record({"id": "t", "legs": [{"r": 1.0}], "meta": {"a": 1}})
    record["id"] = "mine"                                # the top level is the caller's
    for write in (lambda: record["legs"].append({}), lambda: record["legs"][0].update(r=2.0),
                  lambda: record["meta"].__setitem__("a", 2), lambda: record["legs"].sort()):
        with pytest.raises(TypeError, match="v205"):
            write()
    thawed = copy.deepcopy(record)
    thawed["legs"].append({"r": 2.0})                    # a deep copy is plain and mutable
    assert type(thawed["legs"]) is list and type(thawed["meta"]) is dict
    assert isinstance(record["legs"], list) and json.loads(json.dumps(record))["legs"] == [{"r": 1.0}]


def test_a_view_reads_through_the_tests_scope(golden_seed, frozen_clock, logged_in):
    """The Flask test client runs the view in this thread and context, so the
    scopes below really cover the views (otherwise this module proves nothing)."""
    with read_memo.scope():
        _get(logged_in, "dashboard")
        assert read_memo.peek(read_memo.TRADES) is not None
        assert read_memo.peek(read_memo.PLANS) is not None


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_writes_into_no_memoised_record(name, golden_seed, frozen_clock, logged_in,
                                                 frozen_memo, no_writes):
    with read_memo.scope():
        first = _get(logged_in, name)
        second = _get(logged_in, name)                  # the same request's memo, read again
    assert gb.mask(second) == gb.mask(first)
    assert _matches_golden(name, first)
    assert no_writes == [], f"{name} wrote inside a read scope: {no_writes}"


def test_all_eight_endpoints_in_one_scope_match_their_goldens(golden_seed, frozen_clock, logged_in,
                                                              frozen_memo, no_writes):
    with read_memo.scope():
        for _ in range(2):
            mismatched = [name for name in NAMES if not _matches_golden(name, _get(logged_in, name))]
            assert mismatched == []
    assert no_writes == []


def test_memoised_records_still_equal_a_fresh_load(golden_seed, frozen_clock, logged_in, frozen_memo):
    with read_memo.scope():
        for name in NAMES:
            _get(logged_in, name)
        trades = read_memo.peek(read_memo.TRADES)
        assert sorted(trades, key=lambda t: t["id"]) == sorted(
            performance._load_trade_records(), key=lambda t: t["id"])
        assert read_memo.peek(read_memo.PLANS) == plan_store._load_plan_records()
        rows = read_memo.peek(read_memo.TRADE_ROWS)
        if rows is not None:
            assert sorted(rows, key=lambda t: t["trade_id"]) == sorted(
                normalise(trades_repo().list_all()), key=lambda t: t["trade_id"])
```

- [ ] **Step 2: Run them**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet (shared `swing-db`, port 56789).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_memo_isolation.py`
Expected (the static audit's prediction): `12 passed`, `0 failed`. `test_a_view_reads_through_the_tests_scope` must pass first: if it fails, the views do not see the test's scope and every other result here is vacuous, so stop and report.

- [ ] **Step 3: Convict and fix, only where a test fails**

Read each failure:

1. **A 500 with `TypeError: v205: a read path wrote into a memoised record's nested value`** in `test_endpoint_writes_into_no_memoised_record[<name>]`: the traceback's innermost `swingbot/` frame is the writer. Fix it at that site by copying the nested value before writing, as `fx_convert.to_account_currency` copies its rows. For a list of dicts the shape is:

   ```python
   legs = [dict(leg) for leg in (row.get("legs") or [])]   # the caller's own copy
   legs[0]["closed_at"] = closed_at                          # the write the traceback named
   row["legs"] = legs
   ```

   and for a nested dict `row["cohort_stats"] = {**(row.get("cohort_stats") or {}), "key": value}`. Copy at the narrowest site, never by deep-copying whole records in the memo (that would bring back the parse cost the memo removes). The output must not change: the same test then passes against the frozen golden. If the writer is `trades.list_trades` (E32), `TradeLog.get_trades` (C18) or `queries._plan_rows` (C18), put the copy in a new helper and call it in one line; never add a branch to those. Record the conviction in the module docstring's verdict list (`- <module> <function>: convicted: <what it wrote>, now copies <what>`).
2. **`no_writes` not empty**: a scoped GET issues a write or a row lock. Do not fix this here: stop and report the endpoint and statement to the controller, since V205-9 puts `@read_scope` on that view.
3. **`test_all_eight_endpoints_in_one_scope_match_their_goldens` fails while every per-endpoint test passes**: re-run the same sequence once without `read_memo.scope()` in a scratch copy of the test. If it fails there too, the cause is a process cache shared across requests (not the memo): report it. If it passes there, one endpoint's top-level writes reach another through the memo, which the copies forbid by contract: debug with `superpowers:systematic-debugging` and fix in `read_memo` only if V205-6's tests are wrong.
4. **`test_memoised_records_still_equal_a_fresh_load` fails while the others pass**: something reached the stored records themselves (not a copy). Find the path that gets a stored object (only `peek` should) and fix it.
5. **A golden mismatch with no `TypeError`** under `frozen_memo` only (the same endpoint passes `test_golden_endpoints.py`): some reader tests `type(x) is list`/`dict` and treats the frozen subclass differently. That is a test artefact, not a conviction: report the site; never change production code to suit the frozen doubles.

After every fix, re-run this file until `12 passed`.

- [ ] **Step 4: Run the neighbours**

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf`
Expected: `0 failed`, `0 xfailed`. The goldens and budgets pass unchanged: `git -C <wt> diff --stat -- tests/admin_perf/golden/ tests/admin_perf/test_budgets.py tests/admin_perf/money_reference.py` empty.

If Step 3 changed `swingbot/`: `python <wt>/scripts/dev/testrun.py changed` (expected `0 failed`) and `python <wt>/scripts/dev/complexity_gate.py` (expected clean).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add tests/admin_perf/test_memo_isolation.py
git -C <wt> commit -m "test(admin): deep-frozen read memo proves no GET path writes nested values (v205 V205-8)"
```

If Step 3 convicted a mutator, commit each fix separately before the test commit, staging only its file(s):

```bash
git -C <wt> add swingbot/admin/api_v1/trades.py
git -C <wt> commit -m "fix(admin): <function> copies <nested value> before writing it (v205 V205-8)"
```

