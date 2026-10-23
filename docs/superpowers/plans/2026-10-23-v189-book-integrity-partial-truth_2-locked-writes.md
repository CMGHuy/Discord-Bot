# v189 — Book integrity and partial-trade truth: Implementation Plan, part 2 — locked writes (V189-5..V189-7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D3 (§ "The record is written whole or not at all") and `## Corrections from the code brief` items 4, 5.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — Goal, Global Constraints, Contracts, Parallelisation and the task ledger live there and bind every task below.

**Scope of this part.** Three foundations the plan-manager and book-fix parts (3, 4) build on:

- **V189-5** — `transaction()` learns a per-path `lock_timeout` and turns Postgres' "lock not available" into `LockTimeout`; repositories gain a `FOR UPDATE` read.
- **V189-6** — `PlanStore.update` takes the plan row lock, refuses a stale write over a terminal plan, and keeps the tighter stop; proven with two real connections.
- **V189-7** — `TradeLog` and the account balance accept the caller's connection, so a leg, a fill, a placeholder discard and a terminal close (with its balance point) can join the plan's transaction; journal and snapshot hooks can be deferred until after commit.

All three run in the worktree `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` created by V189-1. No task here changes behaviour for a caller that passes no new argument.

**Test-database note (applies to every task here).** The autouse fixture `tests/conftest.py::_store_database` monkeypatches `swingbot.core.db.engine.get_engine` (and `repositories.base.get_engine`) to this worker's test database and truncates the touched tables afterwards. Tests must therefore reach the engine as `engine_module.get_engine()` at call time (`from swingbot.core.db import engine as engine_module`), never through a name imported at module load.

---

# Phase B — Locks and guarded writes

### Task V189-5: Per-path lock timeouts and a FOR UPDATE read

**Model:** sonnet — two small, well-specified additions to the DB layer with a real-Postgres test; no cross-module reasoning.

**Files:**
- Modify: `swingbot/core/db/engine.py` (imports at `:4-9`, `transaction` at `:67-78`)
- Modify: `swingbot/core/db/repositories/base.py` (add `get_for_update` after `get` at `:41-45`)
- Create: `tests/db/test_lock_timeout.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (needs only V189-1's worktree).
- Produces (index § Contracts "Locks and the guarded store"):
  - `swingbot.core.db.engine.BOT_LOCK_TIMEOUT_MS = 1000`
  - `swingbot.core.db.engine.ADMIN_LOCK_TIMEOUT_MS = 5000`
  - `class swingbot.core.db.engine.LockTimeout(Exception)` — raised out of an **owned** `transaction()` when Postgres reports SQLSTATE `55P03` (`lock_not_available`); `__cause__` is the original `sqlalchemy.exc.DBAPIError`.
  - `transaction(conn=None, *, lock_timeout_ms: int | None = None)` — owned transaction: runs `SET LOCAL lock_timeout = '<ms>ms'` first when given (a non-positive value raises `ValueError` before any connection is taken); passthrough `conn`: yields it unchanged and sets nothing (its owner set the timeout and translates the error).
  - `Repository.get_for_update(self, key_value, *, conn) -> dict | None` — `SELECT ... FOR UPDATE` on the key; `conn` is keyword-only with **no default** (`TypeError` when omitted) and `ValueError` when `None`.

**Why.** Spec D3.3 "Deadlock rules": the bot's poll waits at most 1s on a plan row and skips that plan for one cycle; the admin waits 5s. `SET LOCAL` scopes the setting to the one transaction, so a pooled connection never carries it into the next checkout. `get_for_update` is the only row-lock primitive the later tasks use (V189-6 `PlanStore.update`, V189-7's account row, V189-12/14 plan links).

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_lock_timeout.py`:

```python
"""V189-5: per-path lock timeouts on owned transactions, and a FOR UPDATE read.

Two real connections to this worker's test database: one holds a row lock,
the other asks for it under a short lock_timeout and must get LockTimeout
quickly instead of waiting forever."""
from __future__ import annotations

import time

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from swingbot.core.db import engine as engine_module
from swingbot.core.db.engine import (ADMIN_LOCK_TIMEOUT_MS, BOT_LOCK_TIMEOUT_MS,
                                     LockTimeout, transaction)
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades

RECORD = {
    "trade_id": "LOCK-1",
    "ticker": "AAPL",
    "strategy": "RSI",
    "horizon": "2w",
    "direction": "bullish",
    "status": "open",
    "opened_at": "2026-01-02T15:00:00+00:00",
    "confidence": 4,
}


def _repo() -> Repository:
    return Repository(trades, key="trade_id")


@pytest.fixture
def seeded():
    _repo().insert(dict(RECORD))          # own transaction, committed
    return "LOCK-1"


def _shown_lock_timeout(conn) -> str:
    return conn.execute(sa.text("SHOW lock_timeout")).scalar_one()


def test_path_timeouts_are_one_and_five_seconds():
    assert (BOT_LOCK_TIMEOUT_MS, ADMIN_LOCK_TIMEOUT_MS) == (1000, 5000)


def test_owned_transaction_sets_the_lock_timeout_locally():
    with transaction(lock_timeout_ms=1234) as conn:
        assert _shown_lock_timeout(conn) == "1234ms"


def test_without_a_timeout_the_server_default_stands():
    with transaction() as conn:
        assert _shown_lock_timeout(conn) == "0"


def test_the_setting_does_not_leak_into_the_next_transaction():
    with transaction(lock_timeout_ms=1234):
        pass
    with transaction() as conn:
        assert _shown_lock_timeout(conn) == "0"


def test_a_passthrough_connection_is_yielded_unchanged():
    outer = engine_module.get_engine().connect()
    try:
        with outer.begin():
            with transaction(outer, lock_timeout_ms=50) as inner:
                assert inner is outer
                assert _shown_lock_timeout(inner) == "0"
    finally:
        outer.close()


@pytest.mark.parametrize("bad", [0, -5])
def test_a_non_positive_timeout_is_refused(bad):
    with pytest.raises(ValueError):
        with transaction(lock_timeout_ms=bad):
            pass


def test_get_for_update_returns_the_row(seeded):
    with transaction() as conn:
        row = _repo().get_for_update(seeded, conn=conn)
    assert row["trade_id"] == "LOCK-1" and row["status"] == "open"


def test_get_for_update_of_a_missing_key_is_none():
    with transaction() as conn:
        assert _repo().get_for_update("NOPE", conn=conn) is None


def test_get_for_update_requires_the_callers_connection():
    with pytest.raises(TypeError):
        _repo().get_for_update("LOCK-1")            # no conn keyword at all
    with pytest.raises(ValueError):
        _repo().get_for_update("LOCK-1", conn=None)


def test_a_held_row_lock_times_out_as_lock_timeout(seeded):
    holder = engine_module.get_engine().connect()
    try:
        holder.begin()
        assert _repo().get_for_update(seeded, conn=holder) is not None
        started = time.monotonic()
        with pytest.raises(LockTimeout) as caught:
            with transaction(lock_timeout_ms=200) as conn:
                _repo().get_for_update(seeded, conn=conn)
        assert time.monotonic() - started < 3.0
        assert isinstance(caught.value.__cause__, sa_exc.DBAPIError)
    finally:
        holder.rollback()
        holder.close()
    # Released at rollback: the same request now succeeds at once.
    with transaction(lock_timeout_ms=200) as conn:
        assert _repo().get_for_update(seeded, conn=conn) is not None


def test_other_database_errors_are_not_translated():
    with pytest.raises(sa_exc.DBAPIError) as caught:
        with transaction(lock_timeout_ms=200) as conn:
            conn.execute(sa.text("SELECT 1 / 0"))
    assert not isinstance(caught.value, LockTimeout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_lock_timeout.py`
Expected: FAIL at collection — `ImportError: cannot import name 'ADMIN_LOCK_TIMEOUT_MS' from 'swingbot.core.db.engine'`.

- [ ] **Step 3: Implement the timeouts in `engine.py`**

In `swingbot/core/db/engine.py`, replace the import block (`:4-9`) with:

```python
import logging
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine
from sqlalchemy import exc as sa_exc

from swingbot import config
```

Below `_CONNECT_TIMEOUT_SECONDS = 5` (`:16`) add:

```python
# v189 D3.3: how long a writer waits for a row lock before giving up. The bot's
# poll and scanner skip that plan for one cycle; admin and Discord commands wait
# longer because a person is waiting on the answer.
BOT_LOCK_TIMEOUT_MS = 1000
ADMIN_LOCK_TIMEOUT_MS = 5000
_LOCK_NOT_AVAILABLE = "55P03"     # Postgres SQLSTATE raised when lock_timeout expires
```

Below `class DatabaseUnavailable` (`:19-20`) add:

```python
class LockTimeout(Exception):
    """A row lock was not granted within the transaction's lock_timeout.

    Raised out of an owned ``transaction()`` (the whole transaction has already
    rolled back); ``__cause__`` is the driver error."""


def _is_lock_timeout(exc: BaseException) -> bool:
    """True when the driver error is Postgres' lock_not_available (55P03)."""
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == _LOCK_NOT_AVAILABLE


def _checked_timeout(lock_timeout_ms: int | None) -> int | None:
    """The timeout as a positive int, or None; refuses 0 (which means 'wait forever')."""
    if lock_timeout_ms is None:
        return None
    ms = int(lock_timeout_ms)
    if ms <= 0:
        raise ValueError(f"lock_timeout_ms must be positive, got {lock_timeout_ms!r}")
    return ms
```

Replace `transaction` (`:67-78`) with:

```python
@contextmanager
def transaction(conn=None, *, lock_timeout_ms: int | None = None):
    """Yield one transaction for several repository calls.

    An existing connection is passed through, allowing an already-atomic
    caller to compose without opening a second transaction; its owner chose
    the lock timeout and translates a timeout, so nothing is set here.

    An owned transaction with ``lock_timeout_ms`` runs ``SET LOCAL
    lock_timeout`` first (scoped to this transaction only, so a pooled
    connection never carries it on) and raises ``LockTimeout`` when a row lock
    is not granted in time.
    """
    if conn is not None:
        yield conn
        return
    ms = _checked_timeout(lock_timeout_ms)
    try:
        with get_engine().begin() as owned:
            if ms is not None:
                owned.execute(sa.text(f"SET LOCAL lock_timeout = '{ms}ms'"))
            yield owned
    except sa_exc.DBAPIError as exc:
        if _is_lock_timeout(exc):
            raise LockTimeout(f"row lock not granted within {ms}ms") from exc
        raise
```

(`ms` is an `int` produced by `_checked_timeout`, so the f-string cannot inject SQL; `SET` does not accept bind parameters.)

- [ ] **Step 4: Implement `get_for_update` in `base.py`**

In `swingbot/core/db/repositories/base.py`, directly after `get` (`:41-45`) add:

```python
    def get_for_update(self, key_value: Any, *, conn: sa.Connection) -> dict | None:
        """Read one row and hold its row lock until ``conn``'s transaction ends.

        ``conn`` is required: a lock taken in a throwaway transaction would be
        released the moment this method returned. Waits at most the
        transaction's ``lock_timeout`` (see ``engine.transaction``)."""
        if conn is None:
            raise ValueError(f"{self.table.name}.get_for_update needs the caller's connection")
        statement = sa.select(self.table).where(self.key_col == key_value).with_for_update()
        row = conn.execute(statement).one_or_none()
        return None if row is None else self._record(row)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/db/test_lock_timeout.py`
Expected: PASS (12 tests, 0 failed, 0 xfailed). If every test is *skipped* with "test database unreachable", start it (`docker compose --profile test up -d db-test`) and re-run; a skip is not a pass.

- [ ] **Step 6: Check nothing that already calls `transaction()` changed**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_trade_atomicity.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`transaction` is about 4, `get_for_update` 2).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/engine.py swingbot/core/db/repositories/base.py tests/db/test_lock_timeout.py
git commit -m "feat(db): per-path lock_timeout on owned transactions, LockTimeout, Repository.get_for_update (v189 V189-5)"
```

### Task V189-6: Guarded PlanStore.update: row lock, stale-terminal refusal, tighter stops

**Model:** opus — concurrency semantics across two processes; the guard is the single choke point for all 28 plan-manager write sites plus the admin writers, and the race tests must prove it with real connections.

**Files:**
- Modify: `swingbot/core/planning/plan_store.py` (module docstring `:1-3`, imports `:6-11`, `update` `:55-59`; add `__init__`, `lock_for_update` and three module helpers)
- Create: `tests/planning/test_plan_store_guard.py`
- Create: `tests/db/test_plan_store_race.py`

**Interfaces:**
- Consumes (V189-5): `swingbot.core.db.engine.transaction(conn=None, *, lock_timeout_ms=None)`, `ADMIN_LOCK_TIMEOUT_MS`, `BOT_LOCK_TIMEOUT_MS`, `LockTimeout`; `Repository.get_for_update(key, *, conn)` (inherited by `PlanRepository`, key `plan_id`). Existing: `swingbot.core.planning.exit_sim.tighter_stop(stop, other, is_bull) -> float` (`exit_sim.py:357`).
- Produces (index § Contracts):
  - `PlanStore.__init__(self, *, lock_timeout_ms: int = ADMIN_LOCK_TIMEOUT_MS)`; attribute `lock_timeout_ms: int` (V189-8's `PlanManager.__init__` sets it to `BOT_LOCK_TIMEOUT_MS` on its store).
  - `PlanStore.lock_for_update(self, plan_id: str, *, conn) -> TradePlanV2 | None` — locks and reads the row inside the caller's transaction (V189-11, V189-12, V189-14 use it).
  - `PlanStore.update(self, plan: TradePlanV2, *, conn=None) -> bool`:
    - opens `transaction(conn, lock_timeout_ms=self.lock_timeout_ms)` (a passthrough `conn` keeps its owner's timeout) and takes the row lock with `get_for_update`;
    - row absent → `KeyError(plan.plan_id)` (unchanged contract);
    - stored status `CLOSED`/`CANCELLED` and incoming status different → writes nothing, logs INFO `plan store: refused stale write to %s (stored %s, incoming %s)`, returns `False`;
    - stored **and** incoming status both in {`ACTIVE`, `PARTIAL`} → `stop_loss` and `working_stop` become the tighter of stored and incoming (per `direction`; `None` on one side keeps the other) and are written back onto the in-memory `plan` too;
    - otherwise writes the whole document as given and returns `True`;
    - `LockTimeout` propagates (owned transaction only);
    - never takes the process-local `plan_store._LOCK`.

**Why.** Spec D3.3 and index clarifications 3 and 4. Every plan write is a whole-document upsert, so a stale copy written after the admin closed the plan brings it back (audit A8), and a stale copy written after a ratchet loosens the stop. Putting the lock, the refusal and the merge inside `update` covers every caller without editing each. Same-terminal writes stay allowed so the notice, ack and `first_seen_price` writers that touch a plan this process has just closed keep working (`poll` writes `first_seen_price` on the plan `_step` may have just moved to `CLOSED`, brief §4).

- [ ] **Step 1: Write the failing unit tests**

Create `tests/planning/test_plan_store_guard.py`:

```python
"""V189-6: PlanStore.update locks the row, refuses a stale write over a
terminal plan, and never loosens a stop of an ACTIVE/PARTIAL plan."""
from __future__ import annotations

import logging

import pytest

from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning import plan_store as plan_store_module
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _model_plan

LOGGER = "swingbot.core.planning.plan_store"


def _bull(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bullish", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _bear(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bearish", trigger_price=100.0,
                entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=85.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _stored(plan_id="P1") -> dict:
    return PlanRepository().get(plan_id)


def test_the_default_timeout_is_the_admin_path():
    assert PlanStore().lock_timeout_ms == ADMIN_LOCK_TIMEOUT_MS
    assert PlanStore(lock_timeout_ms=1000).lock_timeout_ms == 1000


def test_lock_for_update_reads_the_plan_inside_the_callers_transaction():
    PlanStore().add(_bull())
    with transaction() as conn:
        plan = PlanStore().lock_for_update("P1", conn=conn)
        assert plan.plan_id == "P1" and plan.status == PlanStatus.ACTIVE
        assert PlanStore().lock_for_update("MISSING", conn=conn) is None


def test_an_ordinary_write_returns_true_and_lands():
    store = PlanStore()
    store.add(_bull())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
    assert _stored()["first_seen_price"] == 101.0


def test_an_unknown_plan_still_raises_keyerror():
    with pytest.raises(KeyError):
        PlanStore().update(_bull(plan_id="MISSING"))


@pytest.mark.parametrize("terminal, stale_status", [
    (PlanStatus.CLOSED, PlanStatus.ACTIVE),
    (PlanStatus.CLOSED, PlanStatus.PARTIAL),
    (PlanStatus.CANCELLED, PlanStatus.PENDING),
])
def test_a_stale_write_over_a_terminal_plan_is_refused(caplog, terminal, stale_status):
    store = PlanStore()
    store.add(_bull(status=terminal))
    stale = _bull(status=stale_status, first_seen_price=101.0)
    caplog.set_level(logging.INFO, logger=LOGGER)

    assert store.update(stale) is False

    row = _stored()
    assert row["status"] == terminal
    assert row.get("first_seen_price") is None
    assert (f"plan store: refused stale write to P1 (stored {terminal}, incoming {stale_status})"
            in caplog.text)


def test_the_same_terminal_write_is_allowed():
    store = PlanStore()
    store.add(_bull(status=PlanStatus.CLOSED))
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
    assert _stored()["first_seen_price"] == 101.0


@pytest.mark.parametrize("stored_ws, incoming_ws, kept", [
    (100.0, 98.0, 100.0),     # stale, looser copy: the stored stop survives
    (100.0, 101.0, 101.0),    # a genuine ratchet: the incoming stop wins
    (100.0, None, 100.0),     # a copy without a working stop never clears one
    (None, 99.0, 99.0),       # nothing stored yet: the incoming stop stands
])
def test_a_bullish_working_stop_only_ever_tightens(stored_ws, incoming_ws, kept):
    store = PlanStore()
    store.add(_bull(working_stop=stored_ws))
    incoming = _bull(working_stop=incoming_ws)

    assert store.update(incoming) is True

    assert _stored()["working_stop"] == kept
    assert incoming.working_stop == kept          # written back onto the caller's plan


def test_a_bearish_working_stop_only_ever_tightens():
    store = PlanStore()
    store.add(_bear(working_stop=100.0))
    incoming = _bear(working_stop=102.0)          # looser for a short
    assert store.update(incoming) is True
    assert _stored()["working_stop"] == 100.0 and incoming.working_stop == 100.0


@pytest.mark.parametrize("incoming_stop, kept", [(90.0, 95.0), (97.0, 97.0)])
def test_the_original_stop_never_loosens_either(incoming_stop, kept):
    store = PlanStore()
    store.add(_bull(stop_loss=95.0))
    assert store.update(_bull(stop_loss=incoming_stop)) is True
    assert _stored()["stop_loss"] == kept


def test_the_tp1_transition_keeps_the_tighter_stop():
    store = PlanStore()
    store.add(_bull(working_stop=107.0))          # a fresher ratchet already stored
    incoming = _bull(status=PlanStatus.PARTIAL, working_stop=106.66666666666667)
    assert store.update(incoming) is True
    row = _stored()
    assert row["status"] == PlanStatus.PARTIAL and row["working_stop"] == 107.0


def test_a_pending_plan_is_written_as_given():
    store = PlanStore()
    store.add(_bull(status=PlanStatus.PENDING, entry_price=None, stop_loss=95.0))
    assert store.update(_bull(status=PlanStatus.PENDING, entry_price=None, stop_loss=90.0)) is True
    assert _stored()["stop_loss"] == 90.0


def test_update_joins_the_callers_transaction():
    store = PlanStore()
    store.add(_bull())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            assert store.update(plan, conn=conn) is True
            raise RuntimeError("the caller's next write failed")
    assert _stored().get("first_seen_price") is None


class _ExplodingLock:
    def __enter__(self):
        raise AssertionError("update must not take the process-local _LOCK")

    def __exit__(self, *exc):
        return False


def test_update_holds_no_process_local_lock(monkeypatch):
    store = PlanStore()
    store.add(_bull())
    monkeypatch.setattr(plan_store_module, "_LOCK", _ExplodingLock())
    plan = store.get("P1")
    plan.first_seen_price = 101.0
    assert store.update(plan) is True
```

- [ ] **Step 2: Write the failing race tests (two real connections)**

Create `tests/db/test_plan_store_race.py`:

```python
"""V189-6: the bot's stale plan write racing an admin close or a fresh ratchet,
on two real connections. The admin transaction holds the plan row lock while
the bot's update waits on it; after the admin commits, the bot's write is
refused (terminal) or merged (tighter stop)."""
from __future__ import annotations

import logging
import threading
import time

import pytest

from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, LockTimeout, transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _model_plan

pytestmark = pytest.mark.slow
LOGGER = "swingbot.core.planning.plan_store"


def _active(**kw):
    base = dict(plan_id="P1", entry_type="market", direction="bullish", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _model_plan(**base)


def _bot_update_in_thread(store: PlanStore, plan) -> tuple[threading.Thread, dict]:
    outcome: dict = {}

    def run():
        try:
            outcome["result"] = store.update(plan)
        except BaseException as exc:  # noqa: BLE001 - the test inspects it
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _to_partial(plan):
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t0")


def _first_seen(plan):
    plan.first_seen_price = 101.0


def _ratchet(plan):
    plan.working_stop = 100.0


@pytest.mark.parametrize("stale_change", [_to_partial, _first_seen, _ratchet],
                         ids=["status-changing", "first_seen_price", "stop-ratchet"])
def test_an_admin_close_survives_the_bots_stale_write(caplog, stale_change):
    PlanStore().add(_active())
    bot_store = PlanStore(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS)
    stale = bot_store.get("P1")          # the copy the bot read earlier in its poll
    stale_change(stale)
    caplog.set_level(logging.INFO, logger=LOGGER)

    admin = PlanStore()
    with transaction() as conn:
        plan = admin.lock_for_update("P1", conn=conn)
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t1")
        assert admin.update(plan, conn=conn) is True
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        time.sleep(0.3)
        assert thread.is_alive(), "the bot's write must wait on the admin's row lock"
    thread.join(timeout=5)

    assert not thread.is_alive() and "error" not in outcome, outcome
    assert outcome["result"] is False
    final = PlanStore().get("P1")
    assert final.status == PlanStatus.CLOSED
    assert final.first_seen_price is None and final.working_stop is None
    assert "plan store: refused stale write to P1 (stored CLOSED" in caplog.text


def test_a_fresh_ratchet_survives_a_stale_looser_stop():
    PlanStore().add(_active(working_stop=100.0))
    bot_store = PlanStore(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS)
    stale = bot_store.get("P1")           # working_stop 100 at read time
    stale.first_seen_price = 101.0

    other = PlanStore()
    with transaction() as conn:
        plan = other.lock_for_update("P1", conn=conn)
        plan.working_stop = 102.0         # the fresher ratchet
        assert other.update(plan, conn=conn) is True
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        time.sleep(0.3)
        assert thread.is_alive()
    thread.join(timeout=5)

    assert outcome.get("result") is True, outcome
    final = PlanStore().get("P1")
    assert final.working_stop == 102.0     # tighter stop kept
    assert final.first_seen_price == 101.0  # the bot's other field still lands


def test_a_lock_held_past_the_timeout_raises_and_writes_nothing():
    PlanStore().add(_active())
    bot_store = PlanStore(lock_timeout_ms=200)
    stale = bot_store.get("P1")
    stale.first_seen_price = 101.0

    holder = PlanStore()
    with transaction() as conn:
        assert holder.lock_for_update("P1", conn=conn) is not None
        thread, outcome = _bot_update_in_thread(bot_store, stale)
        thread.join(timeout=5)

    assert isinstance(outcome.get("error"), LockTimeout), outcome
    assert PlanStore().get("P1").first_seen_price is None
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_store_guard.py`
Expected: FAIL — `AttributeError: 'PlanStore' object has no attribute 'lock_timeout_ms'` and the refusal/merge assertions (today `update` returns `None` and overwrites).

Run: `python scripts/dev/testrun.py file tests/db/test_plan_store_race.py`
Expected: FAIL — `AttributeError: 'PlanStore' object has no attribute 'lock_for_update'`.

- [ ] **Step 4: Implement the guarded store**

In `swingbot/core/planning/plan_store.py`, replace the module docstring (`:1-3`) with:

```python
"""Persistence for live TradePlanV2 lifecycles (the `plans` table).
Every read goes to the repository and every write is a row-level upsert, so
a PlanStore instance holds no snapshot.

v189 D3.3: `update` is the one guarded write. It takes the plan row lock
(`SELECT ... FOR UPDATE`, waiting at most `lock_timeout_ms`), refuses to
overwrite a CLOSED/CANCELLED plan with a stale copy, and never loosens the
stop of an ACTIVE/PARTIAL plan. The row lock, not the process-local `_LOCK`,
is what serialises the bot and admin processes; `update` never holds `_LOCK`
while waiting on the row."""
```

Replace the imports (`:6-11`) with:

```python
import logging
import threading
from datetime import datetime

from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.planning.exit_sim import tighter_stop
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       plan_from_dict, plan_to_dict)
```

Below `_OPEN_STATUSES` (`:16`) add:

```python
_TERMINAL_STATUSES = {PlanStatus.CLOSED, PlanStatus.CANCELLED}
_STOP_BEARING = {PlanStatus.ACTIVE, PlanStatus.PARTIAL}


def _refuses(stored_status: str | None, incoming_status: str) -> bool:
    """A stale copy may never overwrite a terminal plan; the same terminal
    write (a notice or ack on a plan this process just closed) is allowed."""
    return stored_status in _TERMINAL_STATUSES and incoming_status != stored_status


def _merged_stop(stored: float | None, incoming: float | None, is_bull: bool) -> float | None:
    """The tighter of two stops; a missing one never loosens the other."""
    if incoming is None:
        return stored
    if stored is None:
        return incoming
    return tighter_stop(float(incoming), float(stored), is_bull)


def _keep_tighter_stops(stored: dict, plan: TradePlanV2) -> None:
    """For a stop-bearing plan, write back the tighter of the stored and the
    incoming stop_loss and working_stop onto ``plan`` (so the caller's copy
    and the row agree). Other statuses are written as given."""
    if stored.get("status") not in _STOP_BEARING or plan.status not in _STOP_BEARING:
        return
    is_bull = plan.direction == "bullish"
    plan.stop_loss = _merged_stop(stored.get("stop_loss"), plan.stop_loss, is_bull)
    plan.working_stop = _merged_stop(stored.get("working_stop"), plan.working_stop, is_bull)
```

Inside `class PlanStore:`, before `_persist`, add:

```python
    def __init__(self, *, lock_timeout_ms: int = ADMIN_LOCK_TIMEOUT_MS):
        # How long update() waits on the plan row lock in a transaction it owns.
        # The plan manager lowers this to BOT_LOCK_TIMEOUT_MS on its own store.
        self.lock_timeout_ms = lock_timeout_ms
```

Replace `update` (`:55-59`) with these two methods:

```python
    def lock_for_update(self, plan_id: str, *, conn) -> TradePlanV2 | None:
        """Lock the plan row inside the caller's transaction and return the plan
        as stored, or None when it does not exist."""
        from swingbot.core.db.repositories.plans import plans_repo
        record = plans_repo().get_for_update(plan_id, conn=conn)
        return plan_from_dict(_normalised(record)) if record else None

    def update(self, plan: TradePlanV2, *, conn=None) -> bool:
        """Write the whole plan under its row lock. False (and nothing written)
        when the stored plan is terminal and this copy is not the same terminal
        write; raises KeyError when the row is absent. LockTimeout propagates
        from a transaction this call owns."""
        from swingbot.core.db.repositories.plans import plans_repo
        with transaction(conn, lock_timeout_ms=self.lock_timeout_ms) as tx:
            stored = plans_repo().get_for_update(plan.plan_id, conn=tx)
            if stored is None:
                raise KeyError(plan.plan_id)
            if _refuses(stored.get("status"), plan.status):
                log.info("plan store: refused stale write to %s (stored %s, incoming %s)",
                         plan.plan_id, stored.get("status"), plan.status)
                return False
            _keep_tighter_stops(stored, plan)
            self._persist(plan_to_dict(plan), conn=tx)
        return True
```

`add` keeps `with _LOCK:` (insert-only, no row to wait on). `_all`, `get`, `open_plans`, `all`, `for_session` are unchanged.

- [ ] **Step 5: Run both files to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_store_guard.py`
Expected: PASS (19 tests, 0 failed, 0 xfailed).

Run: `python scripts/dev/testrun.py file tests/db/test_plan_store_race.py`
Expected: PASS (5 tests). If the `thread.is_alive()` assertion fails intermittently, the machine is too loaded for a 0.3s window: raise the `time.sleep` to 0.6 (still under the 1s bot timeout) rather than removing the assertion.

- [ ] **Step 6: Run the existing store and race tests, then everything the diff reaches**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_store_db.py`
Expected: PASS (`test_update_of_an_unknown_plan_still_raises_keyerror` included).

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_concurrent_close.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed. A failure here is most likely a test that set a terminal plan's `status` back to an open value and called `update` to "reopen" it as fixture setup: rewrite that setup to `PlanStore().add(...)` the plan in the state it needs (never weaken `_refuses`). A test that deliberately writes a *looser* stop on an ACTIVE/PARTIAL plan through `update` is now asserting what the spec forbids: stop and report it rather than editing the assertion.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`update` about 4, `_keep_tighter_stops` 3, `_merged_stop` 3).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_store.py tests/planning/test_plan_store_guard.py tests/db/test_plan_store_race.py
git commit -m "feat(planning): PlanStore.update locks the plan row, refuses stale terminal overwrites, keeps the tighter stop (v189 V189-6)"
```

### Task V189-7: One transaction for TradeLog and the balance; hooks after commit

**Model:** opus — transaction boundaries across two modules, with the balance arithmetic's "trade not yet saved" invariant and the existing monkeypatched doubles both to be preserved.

**Files:**
- Modify: `swingbot/core/planning/account.py` (`_sum_realized_pnl` `:72-102`, `load_account_config` `:105-153`, `save_account_config` `:156-158`, `apply_realized_pnl` `:366-401`)
- Modify: `swingbot/core/tracking/performance.py` (imports `:18-29`; module helpers near `_after_close` `:107-115`; `TradeLog._db_delete` `:614-617`; `append_leg_by_plan` `:792-802`; `record_plan_fill` `:804-836`; `discard_plan_placeholder` `:838-855`; `close_plan_trade` `:857-881`; `_settle_account_balance` `:883-942`)
- Modify: `tests/scanning/test_feed_close_routes.py` (`test_a_failed_balance_update_closes_with_r_only` `:170-180`, whose expectation D3.2 reverses)
- Create: `tests/tracking/test_tradelog_conn.py`

`tests/tracking/test_close_trade_manual_exit_price.py` needs **no** change: its doubles (`_all` as `lambda self`, `_settle_account_balance` as `lambda self, trade`) are only reached through `close_trade_manual`, which this task does not touch, and every new argument below is passed only when a connection is given.

**Interfaces:**
- Consumes (V189-5): `transaction(conn=None, *, lock_timeout_ms=None)`, `Repository.get_for_update(key, *, conn)`. (V189-6 is not consumed; the plan lock is the caller's.)
- Produces (index § Contracts "TradeLog and account"):
  - `account._sum_realized_pnl(*, conn=None) -> float`
  - `account.load_account_config(*, conn=None) -> dict`
  - `account.save_account_config(config: dict, *, conn=None) -> None`
  - `account.apply_realized_pnl(pnl_amount: float, meta: dict = None, *, conn=None) -> dict` — with `conn`, first locks the account config row (`FOR UPDATE`) so two concurrent closes compute their balance points one after the other; then reads and writes on `conn`.
  - `performance.run_after_commit(callbacks: list) -> None` — calls each zero-argument callable in order; an exception is logged at WARNING and swallowed, and the rest still run.
  - `TradeLog._settle_account_balance(self, t: dict, *, conn=None) -> None` — `conn` given: a failed `apply_realized_pnl` **raises** (the caller's transaction rolls the close back); `conn` absent: logged and swallowed as today.
  - `TradeLog.append_leg_by_plan(self, plan_id: str, leg: dict, *, conn=None) -> None`
  - `TradeLog.record_plan_fill(self, plan_id: str, fill_price: float, *, conn=None) -> str | None`
  - `TradeLog.discard_plan_placeholder(self, plan_id: str, *, conn=None) -> bool`
  - `TradeLog.close_plan_trade(self, plan_id, leg, status, *, conn=None, close_reason: str | None = None, after_commit: list | None = None) -> dict | None` — returns the closed trade (`None` when the plan has no open trade); sets `close_reason` on the trade when given; with `after_commit` a list, **appends** the journal hook and the snapshot refresh to it instead of running them; with `after_commit=None` runs them at once (today's order).
  - With `conn`, each of the four TradeLog writers reads the plan's open trade on `conn` and row-locks it (lock order plan → trade → account) and holds **no** process-local `_LOCK`; without `conn` each behaves exactly as today (own commit, `_LOCK`, `self._all()`).
- For part 3 (V189-8): `_persist_terminal` passes `close_reason=` and `after_commit=` and calls `run_after_commit` after its `with transaction()` block; `_persist_fill` / `_persist_partial` pass `conn=` to `record_plan_fill` / `append_leg_by_plan`. From this task on, a balance-write failure inside `_persist_terminal` rolls the close back (the rewritten feed-close test pins that); V189-8/9 add the retry and the ops notice on top.

**Why.** Spec D3.1–D3.2 and Corrections item 4. Today the TP1 leg, the fill and the balance point commit on their own connections, so a failure leaves a plan PARTIAL with no trade leg or a balance point with no close; and the journal and snapshot run before the close commits. The balance write must stay **inside** the transaction: `apply_realized_pnl`'s `base + Σ realized + pnl_amount` is right only while the closing trade row is unsaved, and a rollback must take the point with it so a retried close cannot duplicate it.

- [ ] **Step 1: Write the failing tests**

Create `tests/tracking/test_tradelog_conn.py`:

```python
"""V189-7: TradeLog's plan writers and the account balance join the caller's
transaction; journal and snapshot hooks can wait for the commit."""
from __future__ import annotations

import logging

import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, run_after_commit
from tests.store_seed import seed_store

WIN_LEG = {"fraction": 1.0, "exit_price": 110.0, "r": 2.0, "reason": "win"}
TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _open(tlog, plan_id="p1") -> str:
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="High", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id=plan_id)


def _trade(tlog, plan_id="p1") -> dict | None:
    return next((t for t in tlog.get_trades(status=None, limit=None)
                 if t.get("plan_id") == plan_id), None)


def _history_len() -> int:
    return len(account_repo().history())


class _Boom(RuntimeError):
    pass


def _rolled_back(write) -> None:
    """Run ``write(conn)`` in a transaction whose next statement fails."""
    with pytest.raises(_Boom):
        with transaction() as conn:
            write(conn)
            raise _Boom("the plan write after it failed")


# --- the leg, the fill and the placeholder -------------------------------------------

def test_a_leg_written_on_the_callers_connection_rolls_back_with_it(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn))
    assert not _trade(tlog).get("legs")


def test_a_leg_written_on_the_callers_connection_commits_with_it(tlog):
    _open(tlog)
    with transaction() as conn:
        tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn)
    assert _trade(tlog)["legs"] == [TP1_LEG]


def test_a_fill_rolls_back_with_the_callers_transaction(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.record_plan_fill("p1", 101.0, conn=conn))
    assert _trade(tlog)["entry"] == 100.0


def test_a_fill_commits_and_returns_the_trade_id(tlog):
    trade_id = _open(tlog)
    with transaction() as conn:
        assert tlog.record_plan_fill("p1", 101.0, conn=conn) == trade_id
    assert _trade(tlog)["entry"] == 101.0


def test_a_placeholder_discard_rolls_back_with_the_callers_transaction(tlog):
    _open(tlog)
    _rolled_back(lambda conn: tlog.discard_plan_placeholder("p1", conn=conn))
    assert _trade(tlog)["status"] == "open"


def test_a_placeholder_discard_commits(tlog):
    _open(tlog)
    with transaction() as conn:
        assert tlog.discard_plan_placeholder("p1", conn=conn) is True
    assert _trade(tlog) is None


def test_writers_on_a_connection_take_no_process_local_lock(tlog, monkeypatch):
    _open(tlog)

    class _Exploding:
        def __enter__(self):
            raise AssertionError("a conn= write must not hold TradeLog._LOCK")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(performance, "_LOCK", _Exploding())
    with transaction() as conn:
        tlog.append_leg_by_plan("p1", TP1_LEG, conn=conn)
        assert tlog.record_plan_fill("p1", 101.0, conn=conn) is not None


# --- the terminal close and its balance point ----------------------------------------

def test_a_rolled_back_close_leaves_no_trade_change_and_no_balance_point(tlog):
    _open(tlog)
    before = _history_len()
    _rolled_back(lambda conn: tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn,
                                                    after_commit=[]))
    trade = _trade(tlog)
    assert trade["status"] == "open" and trade.get("realized_pnl_amount") is None
    assert _history_len() == before


def test_a_committed_close_writes_one_balance_point_with_todays_arithmetic(tlog):
    _open(tlog)
    shares = _trade(tlog)["shares"]
    expected_pnl = round(shares * (110.0 - 100.0), 2)
    base = account_module.load_account_config()["balance"]
    before = _history_len()

    with transaction() as conn:
        closed = tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=[])

    assert closed["status"] == "win"
    assert closed["realized_pnl_amount"] == expected_pnl
    assert closed["account_balance_after"] == round(base + expected_pnl, 2)
    history = account_repo().history()
    assert len(history) == before + 1
    assert history[-1]["balance"] == round(base + expected_pnl, 2)
    # No double count: once the trade row is saved, the recomputed balance agrees.
    assert account_module.load_account_config()["balance"] == round(base + expected_pnl, 2)


def test_close_reason_is_written_when_given(tlog):
    _open(tlog)
    with transaction() as conn:
        closed = tlog.close_plan_trade("p1", WIN_LEG, "closed", conn=conn,
                                       close_reason="scratch", after_commit=[])
    assert closed["close_reason"] == "scratch"
    assert _trade(tlog)["close_reason"] == "scratch"


def test_close_without_an_open_trade_returns_none(tlog):
    with transaction() as conn:
        assert tlog.close_plan_trade("nope", WIN_LEG, "win", conn=conn, after_commit=[]) is None


def test_a_failed_balance_write_inside_the_transaction_rolls_the_close_back(tlog, monkeypatch):
    _open(tlog)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    with pytest.raises(RuntimeError, match="account store down"):
        with transaction() as conn:
            tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=[])
    assert _trade(tlog)["status"] == "open"


def test_without_a_connection_a_failed_balance_write_is_still_swallowed(tlog, monkeypatch, caplog):
    _open(tlog)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    caplog.set_level(logging.WARNING, logger=performance.log.name)
    closed = tlog.close_plan_trade("p1", WIN_LEG, "win")
    assert closed["status"] == "win" and closed.get("realized_pnl_amount") is None
    assert "account settlement failed" in caplog.text


# --- hooks after commit ----------------------------------------------------------------

def _record_hooks(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(performance, "_after_close", lambda trade: calls.append(("journal", trade["id"])))
    monkeypatch.setattr(performance, "_refresh_snapshot_safely", lambda: calls.append(("snapshot", None)))
    return calls


def test_hooks_wait_for_the_commit_when_the_caller_collects_them(tlog, monkeypatch):
    trade_id = _open(tlog)
    calls = _record_hooks(monkeypatch)
    callbacks: list = []
    with transaction() as conn:
        tlog.close_plan_trade("p1", WIN_LEG, "win", conn=conn, after_commit=callbacks)
        assert calls == []                      # nothing ran inside the transaction
    run_after_commit(callbacks)
    assert calls == [("journal", trade_id), ("snapshot", None)]


def test_without_a_collector_the_hooks_run_at_once_as_today(tlog, monkeypatch):
    trade_id = _open(tlog)
    calls = _record_hooks(monkeypatch)
    tlog.close_plan_trade("p1", WIN_LEG, "win")
    assert calls == [("journal", trade_id), ("snapshot", None)]


def test_run_after_commit_logs_a_failure_and_keeps_going(caplog):
    ran: list = []

    def broken():
        raise RuntimeError("journal down")

    caplog.set_level(logging.WARNING, logger=performance.log.name)
    run_after_commit([broken, lambda: ran.append("snapshot")])
    assert ran == ["snapshot"]
    assert "after-commit hook" in caplog.text


def test_run_after_commit_of_nothing_is_a_no_op():
    run_after_commit([])


# --- account functions on a connection ---------------------------------------------------

def test_apply_realized_pnl_on_a_connection_rolls_back_with_it(tlog):
    before = _history_len()
    _rolled_back(lambda conn: account_module.apply_realized_pnl(50.0, {"trade_id": "x"}, conn=conn))
    assert _history_len() == before


def test_load_account_config_reads_on_the_callers_connection(tlog):
    with transaction() as conn:
        cfg = account_module.load_account_config(conn=conn)
    assert cfg["balance"] == account_module.load_account_config()["balance"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_conn.py`
Expected: FAIL at collection — `ImportError: cannot import name 'run_after_commit' from 'swingbot.core.tracking.performance'`.

- [ ] **Step 3: `account.py` — every balance read and write accepts the caller's connection**

In `swingbot/core/planning/account.py`, above `_sum_realized_pnl` (`:72`) add:

```python
def _with_conn(conn) -> dict:
    """``{"conn": conn}`` inside a caller's transaction, else ``{}`` -- so a
    standalone call stays byte-identical to the pre-v189 call (tests replace
    these functions with zero-argument doubles)."""
    return {} if conn is None else {"conn": conn}
```

Change `_sum_realized_pnl`'s signature and its one read (body otherwise unchanged):

```python
def _sum_realized_pnl(*, conn=None) -> float:
    ...
    trades = normalise(trades_repo().list_all(conn=conn))
```

Change `load_account_config` (body otherwise unchanged):

```python
def load_account_config(*, conn=None) -> dict:
    ...
    stored = account_repo().load(conn=conn)
    ...
            realized_so_far = _sum_realized_pnl(conn=conn)
    ...
        merged["balance"] = round(merged["base_balance"] + _sum_realized_pnl(conn=conn), 2)
        if needs_save:
            save_account_config(merged, conn=conn)
        return merged
    ...
    defaults["balance"] = round(defaults["base_balance"] + _sum_realized_pnl(conn=conn), 2)
    ...
    save_account_config(defaults, conn=conn)
    return dict(defaults)
```

Replace `save_account_config` (`:156-158`):

```python
def save_account_config(config: dict, *, conn=None) -> None:
    from swingbot.core.db.repositories.account import account_repo
    account_repo().save(config, conn=conn)
```

Replace `apply_realized_pnl`'s signature and body (`:366`, `:388-401`); keep its docstring and append the paragraph shown:

```python
def apply_realized_pnl(pnl_amount: float, meta: dict = None, *, conn=None) -> dict:
    """
    ...existing docstring unchanged...

    v189 D3.2: with ``conn`` this runs inside the closing transaction. It first
    locks the account config row, so two closes committing at once compute
    their balance points one after the other (the second sees the first's
    saved trade), and a rollback removes the point together with the close.
    """
    if conn is not None:
        from swingbot.core.db.repositories.account import CONFIG_KEY, account_repo
        account_repo().get_for_update(CONFIG_KEY, conn=conn)
    config = load_account_config(**_with_conn(conn))
    new_balance = round(float(config.get("balance", 0)) + pnl_amount, 2)
    config["balance"] = new_balance
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "balance": new_balance,
        "pnl_amount": round(pnl_amount, 2),
    }
    if meta:
        entry.update(meta)
    _append_balance_history(config, entry)
    save_account_config(config, **_with_conn(conn))
    return config
```

Before editing, re-read these four functions with `git grep -n "def _sum_realized_pnl\|def load_account_config\|def save_account_config\|def apply_realized_pnl" swingbot/core/planning/account.py`: v187 edits this file (`_validated`, sizing helpers) and line numbers may have moved; change only the lines shown.

- [ ] **Step 4: `performance.py` — module helpers**

In `swingbot/core/tracking/performance.py`, add to the imports (`:18-22`):

```python
from contextlib import nullcontext
```

Directly after `_after_close` (`:107-115`) add:

```python
def run_after_commit(callbacks: list) -> None:
    """Run the hooks a transaction collected, once it has committed. Each is a
    zero-argument callable; one failing never stops the rest (v189 D3.2: the
    journal and the snapshot are rebuildable, the committed close is not)."""
    for callback in callbacks:
        try:
            callback()
        except Exception:
            log.warning("after-commit hook %r failed", callback, exc_info=True)


def _with_conn(conn) -> dict:
    """``{"conn": conn}`` inside a caller's transaction, else ``{}``, so a
    standalone call is byte-identical to the pre-v189 call."""
    return {} if conn is None else {"conn": conn}


def _lock_for(conn):
    """The process-local ``_LOCK`` for a standalone write. Inside a caller's
    transaction the plan row lock serialises writers across processes, and no
    threading lock may be held while waiting on a row lock (v189 D3.3)."""
    return _LOCK if conn is None else nullcontext()


def _locked_open_trade(plan_id: str, conn) -> dict | None:
    """The plan's open trade, read on ``conn`` and row-locked there (lock order
    plan -> trade -> account), in TradeLog's JSON shape; None when none is open."""
    from swingbot.core.db.repositories.trades import OPEN_STATUS, trades_repo
    from swingbot.core.db.schema import trades as trades_table
    import sqlalchemy as sa
    repo = trades_repo()
    rows = repo.list_all(conn=conn, limit=1, where=sa.and_(
        trades_table.c.doc["plan_id"].astext == plan_id,
        trades_table.c.status == OPEN_STATUS))
    if not rows:
        return None
    locked = repo.get_for_update(rows[0]["trade_id"], conn=conn)
    if locked is None or locked.get("status") != OPEN_STATUS:
        return None
    return _json_record(locked)


def _close_onto(t: dict, leg: dict | None, status: str, close_reason: str | None) -> None:
    """Apply a terminal close to an open trade dict in place (no I/O)."""
    if leg is not None:
        append_leg(t, leg)
    t["status"] = status
    t["exit_price"] = (t["legs"][-1]["exit_price"] if t.get("legs")
                       else t.get("exit_price"))
    t["closed_at"] = datetime.now(timezone.utc).isoformat()
    if close_reason is not None:
        t["close_reason"] = close_reason
```

Check the two names the helper imports exist before relying on them: `git grep -n "OPEN_STATUS" swingbot/core/db/repositories/trades.py` (used at `trades.py:37`) and `git grep -n "^trades = \|^trades=" swingbot/core/db/schema.py`. If `OPEN_STATUS` is not importable under that name, use the literal `"open"`.

- [ ] **Step 5: `performance.py` — split the realized-amount arithmetic out of `_settle_account_balance`**

Above `class TradeLog:` add (the body is the first half of today's `_settle_account_balance`, moved verbatim):

```python
def _realized_amount(t: dict) -> float | None:
    """The trade's realized currency P&L, or None when the close settles
    nothing (no share snapshot, no entry, an unsettled status, or a manual
    close without an exit price). Pure: no account I/O."""
    shares = t.get("shares")
    entry = t.get("entry")
    status = t.get("status")
    if not shares or entry is None or status not in ("win", "loss", "closed"):
        return None
    if t.get("legs"):
        # v2 two-leg trade: a runner scratch settles as status "closed",
        # not "win"/"loss" -- settle_legs handles the sign/fraction math.
        return settle_legs(t)
    exit_price = t.get("exit_price")
    # "closed" is included because a reversal exits early at the live price --
    # real money moved, so it must hit the account balance like any win/loss.
    # A manual admin close still no-ops: it records no exit_price.
    if exit_price is None:
        return None
    is_bull = t.get("direction") == "bullish"
    pnl_amount = shares * (exit_price - entry) if is_bull else shares * (entry - exit_price)
    return round(pnl_amount, 2)
```

(Folding the status test into the first guard is behaviour-identical: both branches of today's body returned early for a status outside `win`/`loss`/`closed`.)

Replace `_settle_account_balance` (`:883-942`), keeping its docstring and appending the paragraph shown:

```python
    def _settle_account_balance(self, t: dict, *, conn=None) -> None:
        """
        ...existing docstring unchanged...

        v189 D3.2: with ``conn`` the balance point is written in the caller's
        transaction and a failure RAISES, rolling the whole close back -- a
        close without its balance point is the half-write this replaces.
        Without ``conn`` a failure is logged and swallowed, as before.
        """
        pnl_amount = _realized_amount(t)
        if pnl_amount is None:
            return
        meta = {"trade_id": t.get("id"), "ticker": t.get("ticker"), "status": t.get("status")}
        try:
            updated_cfg = account_module.apply_realized_pnl(pnl_amount, meta, **_with_conn(conn))
        except Exception:
            if conn is not None:
                raise
            # Standalone close: account bookkeeping must never prevent the
            # trade itself from closing. Logged, though: a silent miss here
            # leaves the balance wrong with nothing to say why.
            log.warning(
                "account settlement failed for trade %s", t.get("id"), exc_info=True)
            return
        t["realized_pnl_amount"] = pnl_amount
        t["account_balance_after"] = updated_cfg.get("balance")
```

- [ ] **Step 6: `performance.py` — the four plan writers take `conn=`**

Add one private method to `TradeLog`, after `_all` (`:636-639`):

```python
    def _open_trade_for_plan(self, plan_id: str, *, conn=None) -> dict | None:
        """The plan's open trade. Standalone: from ``self._all()`` exactly as
        before. Inside a transaction: read and row-locked on ``conn``."""
        if conn is None:
            return next((t for t in self._all()
                         if t.get("plan_id") == plan_id and t["status"] == "open"), None)
        return _locked_open_trade(plan_id, conn)
```

Replace `_db_delete` (`:614-617`):

```python
    @staticmethod
    def _db_delete(trade_id: str, *, conn=None) -> None:
        from swingbot.core.db.repositories.trades import trades_repo
        trades_repo().delete(trade_id, conn=conn)
```

Replace `append_leg_by_plan` (`:792-802`):

```python
    def append_leg_by_plan(self, plan_id: str, leg: dict, *, conn=None) -> None:
        """Bank a leg (e.g. TP1 partial) onto the still-open v2 trade this
        plan created. No-op if the plan's trade can't be found (log_trade
        may have failed, or trade_log was wired in after the fill). With
        ``conn`` the leg commits or rolls back with the plan's transition."""
        with _lock_for(conn):
            t = self._open_trade_for_plan(plan_id, conn=conn)
            if t is None:
                return
            append_leg(t, leg)
            self._db_upsert(t, conn=conn)
```

In `record_plan_fill` (`:804-836`) change only the signature, the lock line, the lookup and the upsert; the docstring gains one sentence; the sizing block stays exactly as it is on `main` after v187 (including any `ticker=` argument v187 added):

```python
    def record_plan_fill(self, plan_id: str, fill_price: float, *, conn=None) -> str | None:
        """...existing docstring unchanged...

        With ``conn`` the fill commits or rolls back with the plan's ACTIVE
        transition (v189 D3.1)."""
        with _lock_for(conn):
            t = self._open_trade_for_plan(plan_id, conn=conn)
            if t is None:
                return None
            t["entry"] = fill_price
            # ...the existing compute_position_size try/except and the three
            # assignments under `if sizing is not None:` stay unchanged...
            self._db_upsert(t, conn=conn)
            return t["id"]
```

Replace `discard_plan_placeholder`'s body (`:851-855`; signature becomes `(self, plan_id: str, *, conn=None) -> bool`, docstring unchanged):

```python
        with _lock_for(conn):
            t = self._open_trade_for_plan(plan_id, conn=conn)
            if t is None:
                return False
            self._db_delete(t["id"], conn=conn)
        return True
```

Replace `close_plan_trade` (`:857-881`):

```python
    def close_plan_trade(self, plan_id: str, leg: dict | None, status: str, *, conn=None,
                         close_reason: str | None = None,
                         after_commit: list | None = None) -> dict | None:
        """Final leg + terminal status for a v2 plan's trade. `leg` is the
        real leg dict for a runner close; the caller (PlanManager, which has
        the TradePlanV2 and so can recompute the r-multiple) synthesizes a
        fraction=1.0 leg for a pre-TP1 loss/scratch that closes the ORIGINAL
        single position -- this method just appends whatever it's given so
        settle_legs always has a leg to work from.

        v189 D3.2: with ``conn`` the close and its balance point join the
        caller's transaction (a failed balance write raises). The journal hook
        and the snapshot refresh are appended to ``after_commit`` when the
        caller passes a list, to run once it has committed
        (``run_after_commit``); with no list they run at once, as before.
        Returns the closed trade, or None when the plan has no open trade."""
        with _lock_for(conn):
            t = self._open_trade_for_plan(plan_id, conn=conn)
            if t is None:
                return None
            _close_onto(t, leg, status, close_reason)
            if conn is None:
                self._settle_account_balance(t)
            else:
                self._settle_account_balance(t, conn=conn)
            _restamp_taken_by(t, plan_id)
            closed_trade = dict(t)
            self._db_upsert(t, conn=conn)
        hooks = [lambda: _after_close(closed_trade), lambda: _refresh_snapshot_safely()]
        if after_commit is None:
            run_after_commit(hooks)
        else:
            after_commit.extend(hooks)
        return closed_trade
```

(The `if conn is None` split keeps the `lambda self, trade: None` double some tests install for `_settle_account_balance` working on the standalone path. The hooks are lambdas so a monkeypatched `_after_close` / `_refresh_snapshot_safely` is looked up when the hook runs. Both hooks already swallow their own errors, so routing them through `run_after_commit` changes nothing for the standalone path.)

- [ ] **Step 7: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_conn.py`
Expected: PASS (19 tests, 0 failed, 0 xfailed).

- [ ] **Step 8: Rewrite the one test whose expectation D3.2 reverses**

`tests/scanning/test_feed_close_routes.py::test_a_failed_balance_update_closes_with_r_only` asserts that a failed balance write still closes the trade. `PlanManager._persist_terminal` already passes `conn=` to `close_plan_trade`, so from this task on the failure rolls the close back instead. Run it first to confirm it is the only casualty:

Run: `python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`
Expected: exactly `test_a_failed_balance_update_closes_with_r_only` FAILS (`_run`'s `assert closed` finds no closed event).

Replace that test (`:170-180`) with:

```python
def test_a_failed_balance_update_rolls_the_close_back(trade_log, monkeypatch):
    """v189 D3.2: the balance point is written inside the close transaction, so
    a failed balance write rolls the whole close back -- no closed event, the
    plan still ACTIVE, the trade still open with nothing realized."""
    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    _placeholder(trade_log)
    feed = FakePriceFeed([("AAPL", p) for p in (106, 103)])
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)
    events = [e for _ in range(2) for e in mgr.poll(now=SATURDAY)]

    assert [e for e in events if e.transition == "closed"] == []
    assert store.get("p1").status == "ACTIVE"
    record = trade_log.trade_for_plan("p1")
    assert record["status"] == "open" and record.get("realized_pnl_amount") is None
```

and in the module docstring (`:1-15`) change "and every unsettled case, which must print R only" to "every unsettled case, which must print R only, and the one failure that rolls the close back".

Run: `python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`
Expected: PASS.

- [ ] **Step 9: Run the existing TradeLog and account tests, then everything the diff reaches**

Run each (all must PASS unchanged):
`python scripts/dev/testrun.py file tests/tracking/test_record_plan_fill.py`
`python scripts/dev/testrun.py file tests/tracking/test_discard_plan_placeholder.py`
`python scripts/dev/testrun.py file tests/tracking/test_taken_by.py`
`python scripts/dev/testrun.py file tests/tracking/test_close_trade_manual_exit_price.py`
`python scripts/dev/testrun.py file tests/planning/test_account_db.py`
`python scripts/dev/testrun.py file tests/planning/test_account_legs.py`

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed. A new failure in a test that replaces `apply_realized_pnl` / `load_account_config` with a double and drives a **plan-manager** close is the same reversal as Step 8: report it to the controller with the test name rather than loosening `_settle_account_balance`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_settle_account_balance` drops from 10 to about 3; `_realized_amount` is about 7; `close_plan_trade` about 5; `load_account_config` unchanged at 4.

- [ ] **Step 10: Commit**

Two scoped commits (the account module is a separate concern from the TradeLog writers):

```bash
git add swingbot/core/planning/account.py
git commit -m "feat(account): balance reads and writes accept the caller's connection; apply_realized_pnl locks the account row (v189 V189-7)"
git add swingbot/core/tracking/performance.py tests/tracking/test_tradelog_conn.py tests/scanning/test_feed_close_routes.py
git commit -m "feat(tracking): TradeLog plan writes join the caller's transaction; close hooks can wait for commit (v189 V189-7)"
```

(Every Step 7 and Step 9 run happens before the first commit, with both files edited; the two commits only split the green state by concern.)

