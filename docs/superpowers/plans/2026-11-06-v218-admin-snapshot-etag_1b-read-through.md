# v218 — Admin snapshot, ETag/304 and Server-Timing — Part 1b: the read-through and the existing callers (V218-5..V218-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 3; L2 authority [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Layer 2 (L2-c, L2-b callers).
**Index:** [`2026-11-06-v218-admin-snapshot-etag_0-index.md`](2026-11-06-v218-admin-snapshot-etag_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and the Handoff decisions. Every task below implicitly includes the index's Global Constraints.

**Worktree:** every task runs in `.claude/worktrees/2026-11-06-v218-admin-snapshot-etag` (branch of the same name). Paths below are relative to that worktree root.

**Why a separate file:** Part 1 (`_1-snapshot.md`) reached 1428 lines with V218-1..V218-4. These two tasks would push it past the 1500-line cap, and a task is never split across files. Same ids, files and contracts as the ledger.

**Carried from Part 1:** `store_snapshot.end_request() -> None` (V218-4, an addition beyond the ledger, consumed only here) is called from `request_timing._teardown`.

# Phase 3 — the read-through and the existing callers

### Task V218-5: `read_memo` reads through the snapshot; L2-c frozen double-run and midnight-Berlin tests

**Model:** opus — wires a cross-request cache into every admin read path; the L2-c audit has to prove no reader writes into a record that now outlives its request.

**Files:**
- Modify: `swingbot/core/infra/read_memo.py` (docstring :1-22; new `_BACKING`, `set_backing`; `_stored` :56-63)
- Modify: `swingbot/admin/request_timing.py` (`_begin` :101-103, `_teardown` :125-135, imports :19-24)
- Modify: `swingbot/admin/app.py` (import beside `from swingbot import config` :45; after `snapshot_listener.install(app)`, added by V218-3)
- Modify: `tests/admin_perf/conftest.py` (fixtures `snapshot_on`, `frozen_snapshot`)
- Modify: `tests/admin_perf/test_memo_isolation.py` (backing unit test, install test, double-run test, midnight test, no-clock test)
- Create: `tests/admin_perf/test_snapshot_goldens.py`

**Interfaces:**
- Consumes (V218-4): `store_snapshot.read`, `install`, `begin_request`, `end_request`, `request_state`, `stored`, `reset`, `SNAPSHOT_KEYS`. (V218-2): `store_generation.set_connected`, `reset`; `config.ADMIN_STORE_SNAPSHOT`. (V218-3): `snapshot_listener.install(app)` already in `app.py`. Existing: `_freeze_record` (`tests/admin_perf/test_memo_isolation.py`), `BUDGETS` and `_cost` (`tests/admin_perf/test_budgets.py`), `gb.FROZEN_NOW`, `gb.ENDPOINTS`, `gb.CLOCK_MODULES`, fixtures `golden_seed`, `frozen_clock`, `logged_in`, `sql_counted`, `no_writes`.
- Produces (final names; V218-9 and V218-13 use the fixture):
  - `read_memo.set_backing(fn: Callable[[str, Callable[[], object]], object] | None) -> None`
  - fixture `snapshot_on` in `tests/admin_perf/conftest.py`: switch `on`, `connected` True, `store_snapshot.install()`, both reset on teardown; yields the `store_snapshot` module
  - fixture `frozen_snapshot`: `snapshot_on`, with every value the snapshot stores deep-frozen below its top level

**Background.** `read_memo._stored` is the one seam: inside a scope it loads each key once per request. With a backing installed it asks `store_snapshot.read(key, loader)` instead of calling `loader()`, and still hands every caller shallow copies (`records`/`mapping`), so the copy rule from v205 L1-c is unchanged. `read_memo` stays a leaf; the admin app installs the backing. The bot and the refresher never import `store_snapshot`, so for them `_BACKING` stays None. In tests the backing is installed whenever `swingbot.admin.app` has been imported, but `store_generation.connected()` starts False, so every existing test still loads directly. Only `snapshot_on` turns the snapshot on.

L2-c: records now outlive the request. The frozen fixture therefore freezes what the *snapshot* stores (the frozen loader output is exactly the value `store_snapshot.read` files), and the double-run test reads each endpoint in **two separate requests** on one snapshot. `frozen_memo` stays as it is: with the snapshot off it covers the per-request memo, as before.

Midnight: the index note proposes 2026-11-04 22:30 → 23:30 UTC, but the golden book has no close on Berlin 4 or 5 November, so no realized figure could move there. The test crosses Berlin midnight on **3 → 4 November** instead: 2026-11-03 22:30 UTC (23:30 Berlin, 3 Nov) → 23:30 UTC (00:30 Berlin, 4 Nov). On 3 Nov Berlin the book closed `golden-t1` (14:00 UTC), `golden-t2` (20:30 UTC) and `golden-t3` (2 Nov 23:30 UTC = 3 Nov 00:30 Berlin). On 4 Nov it closed nothing (`test_today_block.py:61`).

Budgets: on a warm request the snapshot keys cost no `list_all`, but the version check adds three `SELECT count(*), max(updated_at)` statements. The goldens test therefore pins the warm `list_all` count below the v205 budget and does not assert the statement budget for the warm path. `test_budgets.py` runs with the snapshot off and stays unchanged.

- [ ] **Step 0: Sync the local replica**

These tests reach Postgres (`golden_seed`). Run `/replicate-prod-db` once this session if no sibling task has (shared `swing-db`, port 56789, `.env` credentials never printed).

- [ ] **Step 1: Add the fixtures**

Append to `tests/admin_perf/conftest.py`:

```python
def _frozen_value(value, freeze):
    """Deep-freeze a stored loader value below each record's top level."""
    if isinstance(value, list):
        return [freeze(record) if isinstance(record, dict) else record for record in value]
    if isinstance(value, dict):
        return {key: freeze(record) if isinstance(record, dict) else record for key, record in value.items()}
    return value


@pytest.fixture
def snapshot_on(admin_app, monkeypatch):
    """v218: the admin snapshot on and vouched for (switch on, listener 'connected')."""
    from swingbot import config
    from swingbot.core.infra import store_generation, store_snapshot
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "on", raising=False)
    store_snapshot.reset()
    store_generation.reset()
    store_generation.set_connected(True)
    store_snapshot.install()
    yield store_snapshot
    store_snapshot.reset()
    store_generation.reset()


@pytest.fixture
def frozen_snapshot(snapshot_on, monkeypatch):
    """snapshot_on, and every value the snapshot stores is deep-frozen below its top level:
    a read path writing into a record shared across requests raises TypeError (v205 L2-c)."""
    from swingbot.core.infra import read_memo
    from tests.admin_perf.test_memo_isolation import _freeze_record
    real = snapshot_on.read
    monkeypatch.setattr(read_memo, "_BACKING", lambda key, loader: real(
        key, lambda: _frozen_value(loader(), _freeze_record)))
    return snapshot_on
```

- [ ] **Step 2: Write the failing memo-isolation tests**

In `tests/admin_perf/test_memo_isolation.py`, add to the imports:

```python
import pathlib
from datetime import datetime, timezone

from swingbot.core.infra import store_snapshot
```

Add one paragraph at the end of the module docstring: `v218 V218-5: the same audit on the cross-request snapshot. frozen_snapshot freezes what the snapshot stores, and each endpoint is read in two separate requests, the second served from the snapshot.`

Append:

```python
@pytest.fixture
def snap_states(monkeypatch):
    """store_snapshot.request_state() of each /api/v1 request, taken as request_timing tears it down."""
    states: list[str] = []
    real = store_snapshot.end_request

    def recording():
        states.append(store_snapshot.request_state())
        real()

    monkeypatch.setattr(store_snapshot, "end_request", recording)
    return states


def test_a_backing_serves_each_scopes_first_load_only(monkeypatch):
    seen = []
    monkeypatch.setattr(read_memo, "_BACKING", None)        # restored on teardown
    read_memo.set_backing(lambda key, loader: seen.append(key) or loader())
    with read_memo.scope():
        read_memo.records(read_memo.TRADES, lambda: [{"a": 1}])
        assert read_memo.records(read_memo.TRADES, lambda: []) == [{"a": 1}]
    assert seen == [read_memo.TRADES]
    read_memo.records(read_memo.TRADES, lambda: [])         # outside a scope: never the backing
    read_memo.set_backing(None)
    with read_memo.scope():
        assert read_memo.mapping(read_memo.PLANS, lambda: {"p": {"x": 1}}) == {"p": {"x": 1}}
    assert seen == [read_memo.TRADES]


def test_the_admin_app_installs_the_snapshot_backing(admin_app):
    assert read_memo._BACKING is store_snapshot.read


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_writes_into_no_snapshot_record_across_two_requests(
        name, golden_seed, frozen_clock, logged_in, frozen_snapshot, no_writes, snap_states):
    first = _get(logged_in, name)
    second = _get(logged_in, name)                          # a new request, on the same snapshot
    assert gb.mask(second) == gb.mask(first)
    assert _matches_golden(name, first)
    assert no_writes == [], f"{name} wrote inside a read scope: {no_writes}"
    assert snap_states[-2:] == ["miss", "hit"], snap_states


BEFORE_MIDNIGHT = datetime(2026, 11, 3, 22, 30, tzinfo=timezone.utc)   # 23:30 Berlin, 3 Nov
AFTER_MIDNIGHT = datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc)    # 00:30 Berlin, 4 Nov


def _today_counts(client) -> tuple[int, int]:
    """(/trades rows flagged today, /dashboard?mode=today realized n)."""
    items = _get_path(client, "/api/v1/trades")["items"]
    realized = _get_path(client, "/api/v1/dashboard?mode=today")["realized"]
    return sum(bool(row["today"]) for row in items), realized["n"]


def _get_path(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code, response.get_data()[:300])
    return response.get_json()


def test_berlin_midnight_moves_the_time_fields_while_the_snapshot_stays_a_hit(
        golden_seed, frozen_clock, logged_in, snapshot_on, snap_states, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", BEFORE_MIDNIGHT)
    rows_before, realized_before = _today_counts(logged_in)
    monkeypatch.setattr(gb, "FROZEN_NOW", AFTER_MIDNIGHT)
    rows_after, realized_after = _today_counts(logged_in)
    assert realized_before > 0 and realized_after == 0      # computed per request, not stored
    assert rows_after < rows_before
    assert snap_states[-2:] == ["hit", "hit"], snap_states  # the stored records did not change


def test_the_snapshot_reads_no_clock():
    for name in ("swingbot.core.infra.store_snapshot", "swingbot.core.infra.store_generation"):
        assert name not in gb.CLOCK_MODULES
    for module in (store_snapshot, store_snapshot.store_generation):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "datetime" not in source and "import time" not in source, module.__name__
```

- [ ] **Step 3: Write the failing goldens test**

Create `tests/admin_perf/test_snapshot_goldens.py`:

```python
"""v218 V218-5: the eight goldens are byte-identical with the snapshot on, cold and
warm, and with the switch off; a warm request loads fewer stores than v205's budget.
Goldens are never regenerated (golden_book.py)."""
import json

import pytest

from swingbot import config
from tests.admin_perf import golden_book as gb
from tests.admin_perf import money_reference as mr
from tests.admin_perf.test_budgets import BUDGETS, _cost

NAMES = list(gb.ENDPOINTS)


def _matches_golden(name, live) -> bool:
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    return gb.mask(gb.without_added(name, live), pointers) == gb.mask(golden, pointers)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:300])
    return response.get_json()


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden_on_the_snapshot(name, golden_seed, frozen_clock,
                                                            logged_in, snapshot_on):
    assert _matches_golden(name, _get(logged_in, name)), f"{name}: cold"
    assert _matches_golden(name, _get(logged_in, name)), f"{name}: warm"
    assert any(snapshot_on.stored(key) is not None for key in snapshot_on.SNAPSHOT_KEYS)


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_matches_its_frozen_golden_with_the_switch_off(name, golden_seed, frozen_clock,
                                                                logged_in, snapshot_on, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off")
    assert _matches_golden(name, _get(logged_in, name))
    assert all(snapshot_on.stored(key) is None for key in snapshot_on.SNAPSHOT_KEYS)


@pytest.mark.parametrize("name", NAMES)
def test_a_warm_request_loads_fewer_stores_than_the_budget(name, golden_seed, frozen_clock, sql_counted,
                                                           logged_in, snapshot_on, monkeypatch):
    _cost(logged_in, name, monkeypatch)                     # cold: fills the snapshot
    _statements, calls = _cost(logged_in, name, monkeypatch)
    assert len(calls) < BUDGETS[name][1], f"{name}: warm list_all {calls}"


def test_a_warm_trades_page_loads_no_trades_or_plans(golden_seed, frozen_clock, sql_counted,
                                                     logged_in, snapshot_on, monkeypatch):
    _cost(logged_in, "trades", monkeypatch)
    _statements, calls = _cost(logged_in, "trades", monkeypatch)
    assert "TradeRepository" not in calls and "PlanRepository" not in calls, calls
```

- [ ] **Step 4: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_memo_isolation.py`
Expected: FAIL. `test_a_backing_serves_each_scopes_first_load_only` fails with `AttributeError: ... has no attribute 'set_backing'`, and the snapshot tests fail on `snap_states` (no `miss`/`hit`, since `begin_request` is never called).

- [ ] **Step 5: Give `read_memo` a backing**

In `swingbot/core/infra/read_memo.py`, add this paragraph to the module docstring, before `The memo lives in a ...`:

```
A **backing** (v218) may serve each scope's first load of a key:
``set_backing(fn)`` makes ``_stored`` call ``fn(key, loader)`` instead of
``loader()``. The admin app installs ``store_snapshot.read`` there (a
cross-request snapshot of raw records); this module still copies per caller
and still imports nothing from ``swingbot``. With no backing (the bot, the
refresher, scripts) behaviour is exactly the above.
```

After the `_MEMO` ContextVar (:34-35), add:

```python
_BACKING: Callable[[str, Callable[[], object]], object] | None = None


def set_backing(fn: Callable[[str, Callable[[], object]], object] | None) -> None:
    """Route each scope's first load of a key through ``fn(key, loader)``; None = load directly."""
    global _BACKING
    _BACKING = fn
```

Replace `_stored` (:56-63) with:

```python
def _stored(key: str, loader: Callable[[], object]) -> object | None:
    """The memoised value for ``key`` (loading it once), or None outside a scope."""
    memo = _MEMO.get()
    if memo is None:
        return None
    if key not in memo:
        backing = _BACKING
        # A raising loader (or backing) stores nothing.
        memo[key] = loader() if backing is None else backing(key, loader)
    return memo[key]
```

- [ ] **Step 6: Arm and disarm the per-request snapshot state**

In `swingbot/admin/request_timing.py`, add to the imports after `from swingbot.core.infra.swallowed import swallowed` (:24):

```python
from swingbot.core.infra import store_snapshot
```

Replace `_begin` (:101-103) with:

```python
def _begin() -> None:
    if request.path.startswith(API_PREFIX):
        setattr(g, _G_KEY, (time.perf_counter(), start_request()))
        store_snapshot.begin_request()       # v218: one version read per request
```

In `_teardown` (:125), add `store_snapshot.end_request()` directly after the `if state is None: return` guard, before the `try:`. The rest stays as it is.

- [ ] **Step 7: Install the backing in the admin app**

In `swingbot/admin/app.py`, after `from swingbot import config` (:45), add:

```python
from swingbot.core.infra import store_snapshot
```

After the `snapshot_listener.install(app)` line that V218-3 added, add:

```python
# v218: read_memo's per-request loads of trades, plans and journal notes read
# through the cross-request snapshot, served only while it can vouch for it.
store_snapshot.install()
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_memo_isolation.py`, `python scripts/dev/testrun.py file tests/admin_perf/test_snapshot_goldens.py`, `python scripts/dev/testrun.py file tests/infra/test_read_memo.py`, `python scripts/dev/testrun.py file tests/infra/test_read_memo_stores.py` and `python scripts/dev/testrun.py file tests/admin_perf/test_store_snapshot.py`
Expected: PASS for all five.

Then `python scripts/dev/testrun.py suite admin-perf`. Expected: PASS, with the existing goldens, budgets and `test_clock_modules_cover_every_clock_read` unchanged. If a double-run endpoint fails with `TypeError: v205: a read path wrote into a memoised record's nested value`, the traceback names the writer. Copy at the writer, as V205-8 did, and add a verdict line to the module docstring. Never thaw the fixture.

Then `python scripts/dev/complexity_gate.py`. Expected: no new violation (`_stored` is 3).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/infra/read_memo.py tests/admin_perf/conftest.py tests/admin_perf/test_memo_isolation.py
git commit -m "feat(infra): read_memo reads through an installable backing; L2-c frozen double-run and midnight tests"
git add swingbot/admin/request_timing.py swingbot/admin/app.py tests/admin_perf/test_snapshot_goldens.py
git commit -m "feat(admin): install the store snapshot; arm its per-request state in request_timing"
```

### Task V218-6: Existing `plans_repo().version()` callers keyed on the trades generation

**Model:** sonnet — one tuple element appended to two cache keys, with tests on existing fakes.

**Files:**
- Modify: `swingbot/admin/api_v1/cancel_precision.py` (`_memo_key` :38-41)
- Modify: `swingbot/admin/watchlist_rows.py` (`_plans_signature` :67-73)
- Modify: `tests/admin/test_api_v1_cancel_precision.py` (`test_the_memo_key_carries_the_utc_hour` :93-96, one new test)
- Modify: `tests/admin/test_watchlist_rows.py` (one new test)

**Interfaces:**
- Consumes: `store_generation.generation("trades") -> int`, `bump(concern)`, `reset()` (V218-2). V218-1's recorded gap (v206 `### Plan 3 version() gap (V218-1)`), which names these two keys and points at this fix.
- Produces: nothing new. `cancel_precision._memo_key()` becomes `(plans_repo().version(), hour, store_generation.generation("trades"))`. `watchlist_rows._plans_signature()` becomes `("db", *plans_repo().version(), store_generation.generation("trades"))` or None.

**Background.** V218-1 showed that `(count, max(updated_at))` can stay put across a committed plan write: an upsert can commit under an older `clock_timestamp()` than a concurrent one. The `trades` NOTIFY channel fires on every `plans` and `starred_plans` write (`p2_001_plans_and_starred.py:25-26`), and the snapshot listener (V218-3) bumps generation `trades` on each one. Appending that generation to both keys closes the gap whenever the listener is up. When it is down, the generation stops moving, and the key degrades to exactly today's version-only behaviour, never to something worse. `journal` is not a plans concern and stays out of both keys.

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_api_v1_cancel_precision.py`, replace `test_the_memo_key_carries_the_utc_hour` (:93-96) with:

```python
def test_the_memo_key_carries_the_utc_hour_and_the_trades_generation(module, repo):
    from swingbot.core.infra import store_generation
    version, hour, generation = module._memo_key()
    assert version == repo.version()
    assert len(hour) == 13 and hour[10] == "T"      # "YYYY-MM-DDTHH"
    assert generation == store_generation.generation("trades")
```

and add after it:

```python
def test_a_trades_generation_bump_recomputes_with_an_unchanged_version(logged_in, module, repo, monkeypatch):
    """v218 V218-6: a plan write committed under an older stamp leaves version()
    unchanged (V218-1); the NOTIFY-driven generation still invalidates the memo."""
    from swingbot.core.infra import store_generation
    store_generation.reset()
    calls = []
    monkeypatch.setattr(module, "_load_plans", lambda: calls.append(1) or [])
    monkeypatch.setattr(module, "_bar_loader", lambda _t: None)
    try:
        logged_in.get(URL)
        logged_in.get(URL)
        assert len(calls) == 1                      # unchanged version and generation: memo kept
        store_generation.bump("trades")
        logged_in.get(URL)
        assert len(calls) == 2
        store_generation.bump("journal")            # not a plans concern
        logged_in.get(URL)
        assert len(calls) == 2
    finally:
        store_generation.reset()
```

In `tests/admin/test_watchlist_rows.py`, after `test_signal_projection_cache_reuses_a_plans_table_version_and_returns_copies`, add:

```python
def test_the_plans_signature_moves_with_the_trades_generation(monkeypatch):
    """v218 V218-6: same plans version, new trades generation -> a new signature."""
    from swingbot.admin import watchlist_rows
    from swingbot.core.infra import store_generation
    from tests.planning.test_plan_store_records import FakePlansRepo

    fake = FakePlansRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: fake)
    store_generation.reset()
    try:
        first = watchlist_rows._plans_signature()
        assert first == ("db", *fake.version(), 0)
        assert watchlist_rows._plans_signature() == first
        store_generation.bump("trades")
        second = watchlist_rows._plans_signature()
        assert second != first and second[:-1] == first[:-1]
        store_generation.bump("journal")
        assert watchlist_rows._plans_signature() == second
    finally:
        store_generation.reset()


def test_the_plans_signature_is_none_when_the_database_is_unreachable(monkeypatch):
    from swingbot.admin import watchlist_rows

    def boom():
        raise OSError("no database")

    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", boom)
    assert watchlist_rows._plans_signature() is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_cancel_precision.py` and `python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py`
Expected: FAIL. The first fails with `ValueError: not enough values to unpack (expected 3, got 2)` and on `assert len(calls) == 2` after the trades bump. The second fails on `first == ("db", 0, 0, 0)`, because the signature has no generation yet. The `None` test already passes, since it pins today's behaviour.

- [ ] **Step 3: Append the generation to both keys**

In `swingbot/admin/api_v1/cancel_precision.py`, replace `_memo_key` (:38-41) with:

```python
def _memo_key() -> tuple:
    """(plans version, UTC hour, trades generation). The generation moves on every
    plans NOTIFY, so a write committed under an older updated_at stamp, which leaves
    version() unchanged (v218 V218-1), still invalidates the memo."""
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.infra import store_generation
    hour = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")
    return (plans_repo().version(), hour, store_generation.generation("trades"))
```

In `swingbot/admin/watchlist_rows.py`, replace `_plans_signature` (:67-73) with:

```python
def _plans_signature() -> tuple | None:
    """Cross-process version token for the plans table (None when the
    database is unreachable, so the cache is skipped rather than stale).

    v218: the trades generation (bumped on every plans NOTIFY by the admin's
    snapshot listener) joins the table version, because a write can commit
    under an older updated_at stamp and leave version() unchanged."""
    try:
        from swingbot.core.db.repositories.plans import plans_repo
        from swingbot.core.infra import store_generation
        return ("db", *plans_repo().version(), store_generation.generation("trades"))
    except Exception:
        return None
```

Neither call site changes: `build_signals` compares signatures by equality (`watchlist_rows.py:338-370`), and the cancel-precision memo is a dict keyed on `_memo_key()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_cancel_precision.py` and `python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py`
Expected: PASS for both.

Then `python scripts/dev/complexity_gate.py`. Expected: no new violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/cancel_precision.py tests/admin/test_api_v1_cancel_precision.py
git commit -m "fix(admin): cancel-precision memo keys on the trades generation as well as the plans version"
git add swingbot/admin/watchlist_rows.py tests/admin/test_watchlist_rows.py
git commit -m "fix(admin): watchlist plan signature keys on the trades generation as well as the plans version"
```
