# v189 — Book integrity and partial-trade truth: Implementation Plan, part 3 — plan-manager transactions (V189-8..V189-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D2 (live callers), D3.1, D3.3 ("How the caller learns of an abort", "Deadlock rules", "Exits are not left to a price re-test"), D4 (NaN quotes) and `## Corrections from the code brief` items 1, 4, 5, 8.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — Goal, Global Constraints, Contracts (§ "Plan manager"), Parallelisation and the task ledger live there and bind every task below.

**Scope of this part.** All three tasks edit `swingbot/core/planning/plan_manager.py` and run strictly in order (V189-8 → V189-9 → V189-10):

- **V189-8** — the TP1 leg and the fill commit in the plan's own transaction; a refused stale write (`PlanStore.update` → `False`) aborts the step and nothing is emitted; close hooks run after commit; `_on_event` stops writing legs and fills.
- **V189-9** — a failed exit is retried once with the same observed price, then reported in the ops channel; a plan whose row is locked is skipped for one poll; stop-bearing plans step before PENDING ones; NaN/inf/non-positive quotes are ignored.
- **V189-10** — a runner or time-exit close after TP1 is labelled by its unrounded net R (`metrics.net_outcome`), not by "TP1 was touched". **It lives in [`_3b-net-labels.md`](2026-10-23-v189-book-integrity-partial-truth_3b-net-labels.md)**: this file reached the 1500-line cap with two tasks, so the third is split, not compressed.

**What part 2 established (consumed here; re-read with `git grep -n` before editing, never re-create):**

- `swingbot.core.db.engine`: `transaction(conn=None, *, lock_timeout_ms=None)`, `BOT_LOCK_TIMEOUT_MS = 1000`, `ADMIN_LOCK_TIMEOUT_MS = 5000`, `LockTimeout` (raised out of an **owned** transaction when Postgres reports 55P03; a passthrough `conn` lets the driver error reach the owner, which translates it).
- `PlanStore(*, lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS)`, attribute `lock_timeout_ms`; `PlanStore.lock_for_update(plan_id, *, conn)`; `PlanStore.update(plan, *, conn=None) -> bool` — row lock first, `False` (+ INFO `plan store: refused stale write to …`) when the stored plan is terminal and the incoming status differs, the same terminal write allowed, tighter `stop_loss`/`working_stop` kept (and written back onto the in-memory plan) when both sides are ACTIVE/PARTIAL.
- `TradeLog.append_leg_by_plan(plan_id, leg, *, conn=None)`, `record_plan_fill(plan_id, fill_price, *, conn=None) -> str | None`, `close_plan_trade(plan_id, leg, status, *, conn=None, close_reason=None, after_commit=None) -> dict | None`, `performance.run_after_commit(callbacks)`. With `conn` each reads and row-locks the plan's open trade on that connection (lock order plan → trade → account) and holds no `_LOCK`; inside `close_plan_trade` a failed balance write **raises** (rolls the close back).
- V189-7 already rewrote `tests/scanning/test_feed_close_routes.py::test_a_failed_balance_update_closes_with_r_only` into `test_a_failed_balance_update_rolls_the_close_back`. **Do not edit that test again**; every task here keeps it green (no `closed` event, plan still ACTIVE, trade still open with nothing realized).

**v187 is merged first** (V189-1 checks it). `plan_manager.py` then has `PENDING_CANCEL_EVENTS`, `NOTICE_EVENTS = {"filled", "closed"} | PENDING_CANCEL_EVENTS`, `_fill_pending(plan, fill, price, reason)` (the stop-entry and limit fill tail, risk-cap cancel included) and `_step_limit(plan, price)`. Line numbers below are pre-v187 `main` (`76b2c637`); locate each method by name.

**Worktree.** Every command runs from the worktree root `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` (created by V189-1). The autouse `tests/conftest.py::_store_database` fixture gives every test a real Postgres database and truncates it afterwards, so the transactions below are real.

---

# Phase C — Plan-manager transactions

### Task V189-8: Plan manager: TP1 leg and fill commit with the plan; aborts emit nothing

**Model:** opus — moves two trade writes into the plan's transaction across 15+ write sites of a 1700-line state machine, with abort, rollback and after-commit semantics that must hold on every step path.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports `:9-38`; new exceptions above `class PlanManager` `:457`; `__init__` `:458-484`; `_on_event` `:729-805`; `_persist_terminal` `:807-816`; the write sites in `_expire_window`, `_annotate_outlook`, `_step_pending`, `_fill_pending` / `_step_limit` (v187), `_step_active`, `_apply_structure_bar`, `_maybe_suggest_pyramid`, `_track_extreme`, `_apply_giveback`, `_ratchet_chandelier`, `_unresolved_events`, `_due_notice_events`, `check_bar`, `_check_bar_active`)
- Modify: `tests/planning/test_plan_manager_poll_window.py` (the `_RecordingLog` double `:202-210` only: it must accept the two new keyword arguments and the leg write)
- Create: `tests/planning/test_plan_manager_atomic_writes.py`

**Interfaces:**
- Consumes (part 2): `transaction`, `BOT_LOCK_TIMEOUT_MS`, `LockTimeout` (`swingbot.core.db.engine`); `PlanStore.update(plan, *, conn=None) -> bool`, `PlanStore.lock_timeout_ms`; `TradeLog.record_plan_fill(..., conn=)`, `append_leg_by_plan(..., conn=)`, `close_plan_trade(..., conn=, close_reason=, after_commit=)`; `performance.run_after_commit(callbacks)`.
- Produces (index § Contracts "Plan manager"):
  - `class PlanWriteAborted(Exception)` — attribute `plan_id`; raised by `_save` when `PlanStore.update` returns `False`. The store already logged the refusal at INFO.
  - `class PlanPersistFailed(Exception)` — attribute `plan_id`; raised after the transaction rolled back and an ERROR line was logged.
  - `PlanManager.__init__` sets `store.lock_timeout_ms = BOT_LOCK_TIMEOUT_MS` when the store has that attribute.
  - `PlanManager._save(self, plan, *, conn=None) -> None`.
  - `PlanManager._persist_fill(self, plan, fill: float) -> str | None` — one transaction: plan ACTIVE + `record_plan_fill(conn=)`; returns the trade id (`None` without a trade log or without a placeholder).
  - `PlanManager._persist_partial(self, plan, leg: dict) -> None` — one transaction: plan PARTIAL + `append_leg_by_plan(conn=)`.
  - `PlanManager._close_in_transaction(self, plan, leg, status, close_reason) -> None` — one attempt of the terminal write; hooks run after commit (V189-9 retries it).
  - `PlanManager._persist_terminal(self, plan, leg, status, close_reason: str | None = None) -> bool`.
  - Module constants `_PASS_THROUGH = (PlanWriteAborted, LockTimeout)` and `_SKIP_PLAN = (PlanWriteAborted, PlanPersistFailed, LockTimeout)`.
  - `event.detail["trade_id"]` on a `filled` event is set by the fill step when `_persist_fill` returned an id; `_on_event` falls back to `log_trade` only when it is absent.
- For V189-9: `_persist_terminal` is a single attempt here (failure → ERROR + `PlanPersistFailed`; `PlanWriteAborted` and `LockTimeout` pass through). `poll`'s existing `try/except Exception` around `_step` still catches all three in this task (logged at WARNING as "poll: step failed"); V189-9 replaces it with `_step_safely`.

**Why.** Spec D3.1 and D3.3. Today the plan goes PARTIAL (or ACTIVE) in one commit and the trade's leg (or fill) is written later by `_on_event`, which swallows every exception, so a failure leaves a PARTIAL plan with no trade leg and understates P&L forever. Every plan write is now guarded by `PlanStore.update`, but the manager ignores its `False`; this task turns it into an abort that emits nothing, so an admin close racing the bot sends no stale notice and books no P&L.

**Write sites.** After this task, `git grep -n "self.store.update(" swingbot/core/planning/plan_manager.py` lists only `_save` itself and the notice writers that run outside `_step`: `_resend_time_notices`, `_resend_pending`, `_feed_bookkeeping`, `_record_time_notices`, and `poll`'s `first_seen_price` write. A `False` there means the plan was ended elsewhere; the store logs it and nothing else needs to happen. (The module-level `ack_notified` uses a local `store.update(plan)` and is also left alone.)

**Accepted side effect.** The trade's TP1 leg used to be written from `event.detail` after `_stamp_exit_quote` had added a `quote` key; it is now written from the leg itself, so the trade's TP1 leg equals the plan's leg and carries no `quote`. Nothing reads a leg's `quote` (`git grep -n 'leg.get("quote")'` is empty); the stamp stays on the event, which is what the feed renders.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_atomic_writes.py`:

```python
"""V189-8: the TP1 leg and the fill commit in the plan's own transaction, a
refused stale write aborts the step with nothing emitted, and the close hooks
run only after the close has committed."""
from __future__ import annotations

import datetime as dt
import logging
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import (PlanEvent, PlanManager, PlanPersistFailed,
                                                 PlanWriteAborted)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"
STORE_LOG = "swingbot.core.planning.plan_store"


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _open_trade(trade_log, *, entry=100.0, stop_loss=95.0) -> str:
    return trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=entry, stop_loss=stop_loss,
        take_profit=110.0, target2=120.0, plan_id="p1")


def _manager(trade_log, prices, plan):
    store = PlanStore()
    store.add(plan)
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _transitions(events, name):
    return [e for e in events if e.transition == name]


def _end_elsewhere(status: str) -> None:
    """Another process ends the plan between the bot's read and its write."""
    other = PlanStore()
    plan = other.get("p1")
    if status == PlanStatus.CLOSED:
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t1")
    else:
        plan.status = status          # a direct row write, as another process leaves it
    assert other.update(plan) is True


def _refuse(*_args, **_kwargs):
    raise RuntimeError("trades table unavailable")


# --- the lock timeout of the bot path ------------------------------------------------

def test_the_manager_puts_its_store_on_the_bot_lock_timeout():
    store = PlanStore()
    PlanManager(store, lambda ticker: 100.0)
    assert store.lock_timeout_ms == BOT_LOCK_TIMEOUT_MS


def test_a_store_double_without_a_timeout_is_left_alone():
    store = object()
    PlanManager(store, lambda ticker: 100.0)
    assert not hasattr(store, "lock_timeout_ms")


def test_save_tolerates_a_store_double_that_returns_nothing():
    class _NoneStore:
        def update(self, plan, **_kw):
            return None

    PlanManager(_NoneStore(), lambda ticker: 100.0)._save(_active())   # no raise


def test_save_raises_when_the_store_refuses():
    class _RefusingStore:
        def update(self, plan, **_kw):
            return False

    with pytest.raises(PlanWriteAborted) as info:
        PlanManager(_RefusingStore(), lambda ticker: 100.0)._save(_active())
    assert info.value.plan_id == "p1"


# --- TP1 leg -----------------------------------------------------------------------

def test_the_tp1_leg_commits_with_the_partial_transition(trade_log):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [110.0], _active(tp2=120.0))

    events = mgr.poll(now=SATURDAY)

    assert [e.transition for e in events] == ["tp1_partial"]
    plan = store.get("p1")
    assert plan.status == PlanStatus.PARTIAL and len(plan.legs_realized) == 1
    trade = trade_log.trade_for_plan("p1")
    assert trade["legs"] == [plan.legs_realized[0]]
    assert trade["legs"][0]["reason"] == "tp1" and trade["legs"][0]["r"] == pytest.approx(2.0)


def test_a_failed_tp1_leg_rolls_the_partial_back(trade_log, monkeypatch, caplog):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [110.0], _active(tp2=120.0))
    monkeypatch.setattr(trade_log, "append_leg_by_plan", _refuse)
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert mgr.poll(now=SATURDAY) == []

    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE
    assert plan.legs_realized == [] and plan.working_stop is None
    assert not trade_log.trade_for_plan("p1").get("legs")
    assert "p1" in caplog.text and "transaction rolled back" in caplog.text


# --- fill ---------------------------------------------------------------------------

def test_the_fill_commits_with_the_active_transition(trade_log):
    trade_id = _open_trade(trade_log, entry=105.0, stop_loss=104.0)
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))

    filled = _transitions(mgr.poll(now=SATURDAY), "filled")

    assert len(filled) == 1 and filled[0].detail["trade_id"] == trade_id
    assert store.get("p1").status == PlanStatus.ACTIVE
    assert trade_log.trade_for_plan("p1")["entry"] == 106.0


def test_a_failed_fill_leaves_the_plan_pending_and_the_placeholder_untouched(
        trade_log, monkeypatch, caplog):
    _open_trade(trade_log, entry=105.0, stop_loss=104.0)
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))
    monkeypatch.setattr(trade_log, "record_plan_fill", _refuse)
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert _transitions(mgr.poll(now=SATURDAY), "filled") == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert trade_log.trade_for_plan("p1")["entry"] == 105.0
    assert "transaction rolled back" in caplog.text


def test_a_fill_without_a_placeholder_still_logs_a_trade_through_on_event(trade_log):
    store, mgr = _manager(trade_log, [106.0], _pending(stop_loss=104.0))
    filled = _transitions(mgr.poll(now=SATURDAY), "filled")
    assert filled[0].detail.get("trade_id") is not None
    assert trade_log.trade_for_plan("p1")["entry"] == 106.0


# --- _on_event no longer writes legs or fills ------------------------------------------

def test_on_event_writes_no_leg_and_no_fill():
    log = MagicMock()
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=log)
    plan = _active()

    mgr._on_event(plan, PlanEvent("p1", "tp1_partial", {"fraction": 0.5, "exit_price": 110.0}))
    mgr._on_event(plan, PlanEvent("p1", "filled", {"entry_price": 100.0, "trade_id": "T9"}))

    log.append_leg_by_plan.assert_not_called()
    log.record_plan_fill.assert_not_called()
    log.log_trade.assert_not_called()


def test_on_event_falls_back_to_log_trade_only_without_a_trade_id():
    log = MagicMock()
    log.log_trade.return_value = "T-NEW"
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=log)
    event = PlanEvent("p1", "filled", {"entry_price": 100.0})

    mgr._on_event(_active(), event)

    log.log_trade.assert_called_once()
    assert event.detail["trade_id"] == "T-NEW"


# --- aborts emit nothing ----------------------------------------------------------------

def test_an_exit_over_a_plan_ended_elsewhere_aborts_and_emits_nothing(
        trade_log, monkeypatch, caplog):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [94.0], _active(tp2=120.0))
    hooks: list = []
    monkeypatch.setattr(performance, "_after_close", lambda trade: hooks.append("journal"))

    def cancelled_meanwhile(plan, stop, now):
        _end_elsewhere(PlanStatus.CANCELLED)
        return False

    monkeypatch.setattr(mgr, "_continuous", cancelled_meanwhile)
    history_before = len(account_repo().history())
    caplog.set_level(logging.INFO, logger=STORE_LOG)

    assert mgr.poll(now=SATURDAY) == []

    assert store.get("p1").status == PlanStatus.CANCELLED
    assert trade_log.trade_for_plan("p1")["status"] == "open"
    assert len(account_repo().history()) == history_before
    assert hooks == []
    assert "refused stale write to p1" in caplog.text


def test_a_stale_non_status_write_aborts_the_step(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [105.0], _active(tp2=120.0))
    real_trigger = plan_manager.breakeven_trigger

    def closed_meanwhile(plan, entry):
        _end_elsewhere(PlanStatus.CLOSED)
        return real_trigger(plan, entry)

    monkeypatch.setattr(plan_manager, "breakeven_trigger", closed_meanwhile)

    assert mgr.poll(now=SATURDAY) == []
    stored = store.get("p1")
    assert stored.status == PlanStatus.CLOSED and stored.working_stop is None


def test_check_bar_returns_nothing_when_the_write_is_refused(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))

    def refused(plan, *, conn=None):
        raise PlanWriteAborted(plan.plan_id)

    monkeypatch.setattr(mgr, "_save", refused)
    assert mgr.check_bar("p1", 111.0, 112.0, 109.0) == []


def test_check_bar_returns_nothing_when_the_write_rolled_back(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))

    def failed(plan, leg):
        raise PlanPersistFailed(plan.plan_id)

    monkeypatch.setattr(mgr, "_persist_partial", failed)
    assert mgr.check_bar("p1", 111.0, 112.0, 109.0) == []


# --- hooks after commit -------------------------------------------------------------

def test_close_hooks_see_the_committed_close(trade_log, monkeypatch):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [94.0], _active(tp2=120.0))
    seen: list = []

    def journal(trade):
        # A fresh connection: it sees only what has committed.
        seen.append((PlanStore().get("p1").status, TradeLog().trade_for_plan("p1")["status"]))

    monkeypatch.setattr(performance, "_after_close", journal)

    assert [e.transition for e in mgr.poll(now=SATURDAY)] == ["closed"]
    assert seen == [(PlanStatus.CLOSED, "loss")]


def test_a_terminal_close_reaches_the_trade_with_its_close_reason(trade_log):
    _open_trade(trade_log)
    store, mgr = _manager(trade_log, [], _active(tp2=120.0))
    plan = store.get("p1")
    record_transition(plan, PlanStatus.CLOSED, reason="scratch", at="t1")
    leg = {"fraction": 1.0, "exit_price": 100.0, "r": 0.0, "reason": "scratch"}

    assert mgr._persist_terminal(plan, leg, "closed", close_reason="scratch") is True

    trade = trade_log.trade_for_plan("p1")
    assert (trade["status"], trade["close_reason"]) == ("closed", "scratch")
    assert store.get("p1").status == PlanStatus.CLOSED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_atomic_writes.py`
Expected: FAIL at collection — `ImportError: cannot import name 'PlanPersistFailed' from 'swingbot.core.planning.plan_manager'`.

- [ ] **Step 3: Imports, the two exceptions and the bot lock timeout**

In `swingbot/core/planning/plan_manager.py`, add to the imports (after `from swingbot.core.analytics import runner_path as rp`):

```python
from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, LockTimeout, transaction
```

(`plan_store` already imports `swingbot.core.db.engine` at module level since V189-6, so this adds no new import-time dependency.)

Directly above `class PlanManager:` add:

```python
class PlanWriteAborted(Exception):
    """PlanStore.update refused a stale write: the stored plan is terminal and
    this copy is not the same terminal write (v189 D3.3). The store logged it
    at INFO; the step that produced the write emits nothing."""

    def __init__(self, plan_id: str):
        super().__init__(plan_id)
        self.plan_id = plan_id


class PlanPersistFailed(Exception):
    """A plan transition and its trade write rolled back together; logged at
    ERROR where it failed. The step emits nothing and the next poll
    re-evaluates the plan from its stored state (v189 D3.1)."""

    def __init__(self, plan_id: str):
        super().__init__(plan_id)
        self.plan_id = plan_id


# Errors a persist helper re-raises untouched: an abort is not a failure, and
# a lock timeout is the caller's to skip (v189 D3.3 "Deadlock rules").
_PASS_THROUGH = (PlanWriteAborted, LockTimeout)
# Every way a step can end with nothing written for this plan this cycle.
_SKIP_PLAN = (PlanWriteAborted, PlanPersistFailed, LockTimeout)
```

At the end of `PlanManager.__init__` add:

```python
        # v189 D3.3: the bot path waits at most BOT_LOCK_TIMEOUT_MS for a plan
        # row another process holds, then skips that plan for one poll. Store
        # doubles without the attribute are left alone.
        if hasattr(store, "lock_timeout_ms"):
            store.lock_timeout_ms = BOT_LOCK_TIMEOUT_MS
```

- [ ] **Step 4: `_save` and the persist helpers**

Replace `_persist_terminal` (`:807-816`) with this block:

```python
    def _save(self, plan: TradePlanV2, *, conn=None) -> None:
        """Write the plan through the guarded store (v189 D3.3). A refused
        stale write raises PlanWriteAborted; ``is False`` (not falsiness) so a
        store double returning None keeps working."""
        if conn is None:
            written = self.store.update(plan)
        else:
            written = self.store.update(plan, conn=conn)
        if written is False:
            raise PlanWriteAborted(plan.plan_id)

    @staticmethod
    def _rolled_back(plan: TradePlanV2, what: str, exc: Exception) -> PlanPersistFailed:
        log.error("plan %s (%s): %s not recorded, transaction rolled back: %s",
                  plan.plan_id, plan.ticker, what, exc, exc_info=exc)
        return PlanPersistFailed(plan.plan_id)

    def _persist_fill(self, plan: TradePlanV2, fill: float) -> str | None:
        """The ACTIVE transition and the placeholder trade's fill, in one
        transaction (v189 D3.1). Returns the trade id, or None without a trade
        log or without a placeholder (``_on_event`` then logs the trade)."""
        if self.trade_log is None:
            self._save(plan)
            return None
        try:
            with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as conn:
                self._save(plan, conn=conn)
                return self.trade_log.record_plan_fill(plan.plan_id, fill, conn=conn)
        except _PASS_THROUGH:
            raise
        except Exception as exc:
            raise self._rolled_back(plan, "fill", exc) from exc

    def _persist_partial(self, plan: TradePlanV2, leg: dict) -> None:
        """The PARTIAL transition and the trade's TP1 leg, in one transaction
        (v189 D3.1): the plan is never PARTIAL without its trade leg."""
        if self.trade_log is None:
            self._save(plan)
            return
        try:
            with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as conn:
                self._save(plan, conn=conn)
                self.trade_log.append_leg_by_plan(plan.plan_id, dict(leg), conn=conn)
        except _PASS_THROUGH:
            raise
        except Exception as exc:
            raise self._rolled_back(plan, "TP1 leg", exc) from exc

    def _close_in_transaction(self, plan: TradePlanV2, leg: dict, status: str,
                              close_reason: str | None) -> None:
        """One attempt at the terminal write: the plan, the trade's close and
        its balance point commit together (v189 D3.2); the journal and the
        snapshot refresh run only after the commit."""
        from swingbot.core.tracking.performance import run_after_commit
        callbacks: list = []
        with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as conn:
            self._save(plan, conn=conn)
            self.trade_log.close_plan_trade(plan.plan_id, leg, status, conn=conn,
                                            close_reason=close_reason,
                                            after_commit=callbacks)
        run_after_commit(callbacks)

    def _persist_terminal(self, plan: TradePlanV2, leg: dict, status: str,
                          close_reason: str | None = None) -> bool:
        """Persist a terminal plan and its linked trade as one DB transaction.
        True when the trade was closed with it; False without a trade log."""
        if self.trade_log is None:
            self._save(plan)
            return False
        try:
            self._close_in_transaction(plan, leg, status, close_reason)
        except _PASS_THROUGH:
            raise
        except Exception as exc:
            raise self._rolled_back(plan, "close", exc) from exc
        return True
```

(`performance` is imported inside the method, as `TradeLog` is in `_manager()`, because `swingbot.core.tracking.performance` imports planning modules at load.)

- [ ] **Step 5: The fill and TP1 write sites use the helpers**

(a) The fill. After v187 the ACTIVE tail lives in `_fill_pending` (`git grep -n "def _fill_pending" swingbot/core/planning/plan_manager.py`). Replace its last four statements:

```python
        plan.entry_price = fill
        record_transition(plan, PlanStatus.ACTIVE, reason=reason, at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "filled",
                          {"entry_price": fill, "live_price": price})]
```

with:

```python
        plan.entry_price = fill
        record_transition(plan, PlanStatus.ACTIVE, reason=reason, at=self._now())
        detail = {"entry_price": fill, "live_price": price}
        trade_id = self._persist_fill(plan, fill)
        if trade_id is not None:
            detail["trade_id"] = trade_id
        return [PlanEvent(plan.plan_id, "filled", detail)]
```

and in the same method replace the risk-cap cancel's `self.store.update(plan)` with `self._save(plan)`.

(b) `_step_active`'s TP1 branch (`:1021-1025`): replace

```python
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]
```

with

```python
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
            self._persist_partial(plan, leg)
            return [PlanEvent(plan.plan_id, "tp1_partial", dict(leg))]
```

(c) `_check_bar_active`'s TP1 branch (`:1460-1464`): the same replacement (`self.store.update(plan)` → `self._persist_partial(plan, leg)`).

(d) Every other write reached from `_step` or `check_bar` becomes `self._save(plan)` — replace `self.store.update(plan)` with `self._save(plan)` in exactly these methods: `_expire_window`, `_annotate_outlook`, `_step_pending` (expired, invalidated and any cancel v187 left there), `_step_limit` (v187's `cancelled_limit` and `cancelled_gap_through_stop` writes), `_step_active` (the break-even write `:1059`), `_apply_structure_bar`, `_maybe_suggest_pyramid`, `_track_extreme`, `_apply_giveback`, `_ratchet_chandelier`, `_unresolved_events`, `_due_notice_events`.

Then check:

Run: `git grep -n "self.store.update(" swingbot/core/planning/plan_manager.py`
Expected: matches only inside `_save`, `_resend_time_notices`, `_resend_pending`, `_feed_bookkeeping`, `_record_time_notices` and `poll` (the `first_seen_price` write). A match in any other method is a missed site.

- [ ] **Step 6: `check_bar` returns nothing for a skipped plan**

Replace `check_bar` (`:1415-1429`) with:

```python
    def check_bar(self, plan_id: str, bar_open: float, bar_high: float,
                  bar_low: float) -> list[PlanEvent]:
        plan = self.store.get(plan_id)
        if plan is None:
            return []
        try:
            events = self._check_bar_step(plan, bar_open, bar_high, bar_low)
        except _SKIP_PLAN as exc:
            # v189 D3.3: aborted, rolled back or locked -- nothing was
            # written, so nothing is emitted (logged where it happened).
            log.info("check_bar: plan %s skipped (%s)", plan_id, type(exc).__name__)
            return []
        for event in events:
            log_plan_event(plan, event)
            self._on_event(plan, event)
        return events

    def _check_bar_step(self, plan: TradePlanV2, bar_open: float, bar_high: float,
                        bar_low: float) -> list[PlanEvent]:
        if plan.status == PlanStatus.ACTIVE:
            return self._check_bar_active(plan, bar_open, bar_high, bar_low)
        if plan.status == PlanStatus.PARTIAL:
            return self._check_bar_partial(plan, bar_open, bar_high, bar_low)
        return []
```

(`check_bar` stays unwired in production — `docs/claude/known-traps.md`; do not add a caller.)

- [ ] **Step 7: `_on_event` stops writing the fill and the leg**

In `_on_event` (`:729-805`):

(a) In the `filled` branch, replace the call

```python
                trade_id = self.trade_log.record_plan_fill(
                    plan.plan_id, plan.entry_price)
```

with

```python
                # v189 D3.1: the fill step already moved the placeholder onto
                # the fill inside the plan's own transaction (_persist_fill)
                # and put the trade id on the event.
                trade_id = event.detail.get("trade_id")
```

and in the comment above it change `record_plan_fill() finds it by plan_id and moves its entry (and resized shares) onto plan.entry_price.` to `_persist_fill -> record_plan_fill() finds it by plan_id and moves its entry (and resized shares) onto plan.entry_price, in the plan's own transaction.` Keep the `if trade_id is None:` fallback and `event.detail["trade_id"] = trade_id` exactly as they are.

(b) Delete the two lines

```python
            elif event.transition == "tp1_partial":
                self.trade_log.append_leg_by_plan(plan.plan_id, event.detail)
```

(the leg is written by `_persist_partial`). The `PENDING_CANCEL_EVENTS` discard branch and the `closed` branch stay unchanged (index clarification 11).

- [ ] **Step 8: Update the one trade-log double that the persist helpers now reach**

In `tests/planning/test_plan_manager_poll_window.py`, replace `_RecordingLog` (`:202-210`) with:

```python
class _RecordingLog:
    """Minimal TradeLog stand-in: the plan manager writes the TP1 leg and the
    terminal close through it, inside the plan's transaction (v189 D3.1)."""

    def __init__(self):
        self.closed = []
        self.legs = []

    def append_leg_by_plan(self, plan_id, leg, *, conn=None):
        self.legs.append((plan_id, leg))

    def close_plan_trade(self, plan_id, leg, status, *, conn=None, close_reason=None,
                         after_commit=None):
        self.closed.append((plan_id, leg, status))
```

- [ ] **Step 9: Run the new tests, then every plan-manager and close-route test**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_atomic_writes.py`
Expected: PASS (17 tests, 0 failed, 0 xfailed).

Run each (all must PASS unchanged):
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_poll_window.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_concurrent_close.py`
`python scripts/dev/testrun.py file tests/planning/test_manager_singleton_staleness_repro.py`
`python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`
`python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`
`python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`

Run: `python scripts/dev/testrun.py suite planning`
Expected: 0 failed, 0 xfailed. A failure in a test that installs its own trade-log double is the Step 8 pattern (the double needs `append_leg_by_plan` and the two new keyword arguments): fix the double, never the helper. A failure where a test **expects** a PARTIAL plan without a trade leg, or a fill without its record, is the behaviour D3.1 removes: report it to the controller with the test name.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_on_event` drops from 15 to 14; `check_bar` about 3; every new helper at most 4.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_atomic_writes.py tests/planning/test_plan_manager_poll_window.py
git commit -m "feat(planning): TP1 leg and fill commit with the plan; a refused stale write aborts the step (v189 V189-8)"
```

### Task V189-9: Exit retry and ops notice; lock skip, stop-first order, finite quotes

**Model:** opus — retry semantics that must not double-book a close, a lock-skip path proven with two real connections, and a baselined `poll` (complexity 20) that may only shrink.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports; module helper `_usable_price` near `quote_stamp` `:90`; `__init__`; `poll` `:589-688`; `_persist_terminal` from V189-8; new `_retry_close`, `_record_exit_failure`, `take_exit_failures`, `_step_safely`, `_ordered`; `_monitor_quote_worker` `:1543-1549`; `_price_batch_fn` `:1578-1584`; module `drain_exit_failures` after `run_manager_tick` `:1629-1637`)
- Modify: `swingbot/commands/scanning/loops.py` (new `_post_exit_failures` after `_post_cooldown_note` `:120-133`; one call in `trade_monitor` after the plan-event post `:711-712`)
- Create: `tests/planning/test_plan_manager_exit_retry.py`
- Create: `tests/planning/test_plan_manager_quote_guard.py`

**Interfaces:**
- Consumes (V189-8): `PlanWriteAborted`, `PlanPersistFailed`, `_close_in_transaction(plan, leg, status, close_reason)`, `_persist_terminal`, `_SKIP_PLAN`; (V189-5/6) `LockTimeout`, `transaction`, `PlanStore.lock_for_update(plan_id, *, conn)`.
- Produces (index § Contracts "Plan manager"):
  - `_persist_terminal(plan, leg, status, close_reason=None) -> bool` — any exception other than `PlanWriteAborted` (a `LockTimeout` included) is retried **once, at once, with the same plan, leg and price**; a second failure logs ERROR, appends one entry to `self._exit_failures` and raises `PlanPersistFailed`.
  - `PlanManager.take_exit_failures(self) -> list[dict]` — drains `[{"plan_id", "ticker", "exit_price", "reason", "error"}]`.
  - `PlanManager._step_safely(self, plan, price: float, now) -> list[PlanEvent] | None` — `None` means "skip this plan this poll".
  - `PlanManager._ordered(self, plans: list) -> list` — non-PENDING plans first, otherwise in the given order (stable).
  - `def _usable_price(price) -> bool` — a number that is finite and `> 0`; `None`, NaN, ±inf, zero, negatives and non-numbers are `False`.
  - Module `def drain_exit_failures() -> list[dict]` — the process manager's drained failures, `[]` before the first tick.
  - `swingbot.commands.scanning.loops._post_exit_failures(failures: list[dict]) -> None` (async) — one ops-channel message per failure: `⚠️ Exit not recorded: {ticker} plan `{plan_id}` -- observed {reason} exit at {exit_price:.2f}. The book still shows the position open; check it by hand.`

**Why.** Spec D3.3 "Exits are not left to a price re-test" and "Deadlock rules", D4 "NaN quotes". A rolled-back stop would leave the book showing a position the tape has exited, and the next poll might never see that price again, so a missed stop flatters the book; the exit is retried once with the observed price and then reported, never silently dropped. A missed TP1 or fill needs no retry (the next poll re-evaluates it). One stuck admin transaction must delay one plan by one poll, not stall the loop, and stop-bearing plans are stepped first so the lock budget goes to exits. `if not price or price <= 0` lets NaN through (NaN is truthy and `NaN <= 0` is False).

- [ ] **Step 1: Write the failing retry and notice tests**

Create `tests/planning/test_plan_manager_exit_retry.py`:

```python
"""V189-9: a failed exit is retried once with the same observed price; a second
failure is logged, recorded and posted to the ops channel. Aborts and non-exit
writes are never retried."""
from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import time
import types
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    log = TradeLog()
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=100.0, stop_loss=95.0,
        take_profit=110.0, target2=120.0, plan_id="p1")
    return log


def _manager(trade_log, prices):
    store = PlanStore()
    store.add(_active(tp2=120.0))
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _spy_close(trade_log, monkeypatch, *, fail_times: int) -> list:
    """Wrap close_plan_trade: record every call's leg, fail the first ``fail_times``."""
    real = trade_log.close_plan_trade
    calls: list = []

    def close(plan_id, leg, status, **kwargs):
        calls.append(dict(leg))
        if len(calls) <= fail_times:
            raise RuntimeError("trades table unavailable")
        return real(plan_id, leg, status, **kwargs)

    monkeypatch.setattr(trade_log, "close_plan_trade", close)
    return calls


# --- retry once ------------------------------------------------------------------------

def test_a_failed_exit_is_retried_once_with_the_same_price(trade_log, monkeypatch, caplog):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=1)
    history_before = len(account_repo().history())
    caplog.set_level(logging.WARNING, logger=MANAGER_LOG)

    events = mgr.poll(now=SATURDAY)

    assert [e.transition for e in events] == ["closed"]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0]["exit_price"] == 94.0
    assert store.get("p1").status == PlanStatus.CLOSED
    trade = trade_log.trade_for_plan("p1")
    assert trade["status"] == "loss" and trade["exit_price"] == 94.0
    assert len(account_repo().history()) == history_before + 1   # one point, not two
    assert mgr.take_exit_failures() == []
    assert "retrying once" in caplog.text


def test_an_exit_that_fails_twice_is_recorded_and_emits_nothing(trade_log, monkeypatch, caplog):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=2)
    history_before = len(account_repo().history())
    caplog.set_level(logging.ERROR, logger=MANAGER_LOG)

    assert mgr.poll(now=SATURDAY) == []

    assert len(calls) == 2
    assert store.get("p1").status == PlanStatus.ACTIVE
    assert trade_log.trade_for_plan("p1")["status"] == "open"
    assert len(account_repo().history()) == history_before
    assert mgr.take_exit_failures() == [{
        "plan_id": "p1", "ticker": "AAPL", "exit_price": 94.0, "reason": "loss",
        "error": "RuntimeError: trades table unavailable"}]
    assert mgr.take_exit_failures() == []                 # drained
    assert "exit not recorded" in caplog.text and "p1" in caplog.text


def test_an_aborted_exit_is_not_retried(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [94.0])
    calls = _spy_close(trade_log, monkeypatch, fail_times=0)

    def cancelled_meanwhile(plan, stop, now):
        other = PlanStore()
        stored = other.get("p1")
        stored.status = PlanStatus.CANCELLED
        other.update(stored)
        return False

    monkeypatch.setattr(mgr, "_continuous", cancelled_meanwhile)

    assert mgr.poll(now=SATURDAY) == []
    assert calls == []
    assert mgr.take_exit_failures() == []


def test_a_failed_tp1_leg_is_not_retried(trade_log, monkeypatch):
    store, mgr = _manager(trade_log, [110.0])
    attempts: list = []

    def refuse(*_args, **_kwargs):
        attempts.append(1)
        raise RuntimeError("trades table unavailable")

    monkeypatch.setattr(trade_log, "append_leg_by_plan", refuse)

    assert mgr.poll(now=SATURDAY) == []
    assert attempts == [1]
    assert mgr.take_exit_failures() == []


@pytest.mark.slow
def test_an_exit_whose_plan_row_stays_locked_is_retried_then_reported(trade_log):
    store, mgr = _manager(trade_log, [94.0])
    with transaction() as conn:
        PlanStore().lock_for_update("p1", conn=conn)       # another process holds the row
        started = time.monotonic()
        events = mgr.poll(now=SATURDAY)
        elapsed = time.monotonic() - started

    assert events == []
    assert 1.5 < elapsed < 6.0                             # two 1s lock waits
    [failure] = mgr.take_exit_failures()
    assert failure["plan_id"] == "p1" and failure["error"].startswith("LockTimeout")
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_drain_exit_failures_before_the_first_tick_is_empty(monkeypatch):
    monkeypatch.setattr(plan_manager, "_MANAGER", None)
    assert plan_manager.drain_exit_failures() == []


def test_drain_exit_failures_empties_the_process_manager(monkeypatch):
    mgr = PlanManager(PlanStore(), lambda ticker: 100.0)
    mgr._exit_failures.append({"plan_id": "p1"})
    monkeypatch.setattr(plan_manager, "_MANAGER", mgr)
    assert plan_manager.drain_exit_failures() == [{"plan_id": "p1"}]
    assert plan_manager.drain_exit_failures() == []


# --- the ops-channel notice ---------------------------------------------------------------

class _Channel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


FAILURE = {"plan_id": "p1", "ticker": "AAPL", "exit_price": 94.0, "reason": "loss",
           "error": "RuntimeError: boom"}


def test_each_failed_exit_posts_one_ops_line(monkeypatch):
    chan = _Channel()
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    second = {**FAILURE, "plan_id": "p2", "ticker": "MSFT", "exit_price": 310.5,
              "reason": "tp1_runner_trail"}

    asyncio.run(loops_mod._post_exit_failures([FAILURE, second]))

    assert [m["content"] for m in chan.sent] == [
        "⚠️ Exit not recorded: AAPL plan `p1` -- observed loss exit at 94.00. "
        "The book still shows the position open; check it by hand.",
        "⚠️ Exit not recorded: MSFT plan `p2` -- observed tp1_runner_trail exit at 310.50. "
        "The book still shows the position open; check it by hand.",
    ]


def test_no_failures_look_up_no_channel(monkeypatch):
    looked_up: list = []
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: looked_up.append(1))
    asyncio.run(loops_mod._post_exit_failures([]))
    assert looked_up == []


def test_without_a_channel_the_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: None)
    with caplog.at_level(logging.ERROR):
        asyncio.run(loops_mod._post_exit_failures([FAILURE]))
    assert any("no ops channel" in r.getMessage() for r in caplog.records)


def test_a_failing_send_warns_and_keeps_posting(monkeypatch, caplog):
    chan = _Channel(fail=True)
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_exit_failures([FAILURE, {**FAILURE, "plan_id": "p2"}]))
    messages = [r.getMessage() for r in caplog.records]
    assert sum("exit-failure notice" in m for m in messages) == 2


def test_trade_monitor_posts_the_drained_failures_after_the_manager_tick():
    source = inspect.getsource(loops_mod.trade_monitor.coro)
    tick = source.index("plan_manager.run_manager_tick")
    post = source.index("await _post_exit_failures(plan_manager.drain_exit_failures())")
    assert tick < post
```

- [ ] **Step 2: Write the failing poll-guard tests**

Create `tests/planning/test_plan_manager_quote_guard.py`:

```python
"""V189-9: poll ignores NaN/inf/non-positive quotes, steps stop-bearing plans
before PENDING ones, and skips (never stalls on) a plan another process has
locked."""
from __future__ import annotations

import datetime as dt
import logging
import math
import time
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager, _usable_price
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"


@pytest.fixture(autouse=True)
def _full_step_every_tick(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _quote(symbol, price):
    return QuoteDetail(symbol=symbol, price=price, trade_at=None, bid=None, ask=None,
                       quote_at=None, source="legacy")


@pytest.mark.parametrize("price, usable", [
    (100.0, True), (0.01, True), (7, True),
    (0.0, False), (-1.0, False), (None, False), ("n/a", False),
    (math.nan, False), (math.inf, False), (-math.inf, False),
])
def test_usable_price(price, usable):
    assert _usable_price(price) is usable


@pytest.mark.parametrize("bad", [math.nan, math.inf, 0.0, -3.0])
def test_poll_never_steps_a_plan_on_an_unusable_quote(monkeypatch, bad):
    store = PlanStore()
    store.add(_active())
    mgr = PlanManager(store, lambda ticker: bad)
    stepped: list = []
    monkeypatch.setattr(mgr, "_step", lambda plan, price, now=None: stepped.append(price) or [])

    assert mgr.poll(now=SATURDAY) == []
    assert stepped == []
    assert store.get("p1").first_seen_price is None


def test_the_shared_price_batch_drops_unusable_quotes(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    details = {"GOOD": _quote("GOOD", 101.0), "NAN": _quote("NAN", math.nan),
               "ZERO": _quote("ZERO", 0.0), "NONE": _quote("NONE", None)}
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda tickers: details)

    prices = plan_manager._price_batch_fn(list(details))

    assert dict(prices) == {"GOOD": 101.0}


def test_the_quote_worker_drops_unusable_quotes(monkeypatch):
    from swingbot.core.marketdata import data
    quotes = {"GOOD": _quote("GOOD", 101.0), "NAN": _quote("NAN", math.nan),
              "INF": _quote("INF", math.inf)}
    monkeypatch.setattr(data, "get_quote_batch", lambda tickers, **kw: quotes)

    docs, _rows = plan_manager._monitor_quote_worker(list(quotes))

    assert set(docs) == {"GOOD"}


def test_ordered_puts_stop_bearing_plans_first_and_keeps_order():
    plans = [_plan(plan_id="a", status=PlanStatus.PENDING),
             _plan(plan_id="b", status=PlanStatus.ACTIVE),
             _plan(plan_id="c", status=PlanStatus.PENDING),
             _plan(plan_id="d", status=PlanStatus.PARTIAL)]
    ordered = PlanManager(PlanStore(), lambda ticker: 1.0)._ordered(plans)
    assert [p.plan_id for p in ordered] == ["b", "d", "a", "c"]


def test_poll_steps_the_active_plan_before_the_pending_one(monkeypatch):
    store = PlanStore()
    store.add(_pending(plan_id="pend", ticker="MSFT"))
    store.add(_active(plan_id="act"))
    mgr = PlanManager(store, lambda ticker: 100.0)
    order: list = []
    real_step = mgr._step

    def spy(plan, price, now=None):
        order.append(plan.plan_id)
        return real_step(plan, price, now)

    monkeypatch.setattr(mgr, "_step", spy)
    mgr.poll(now=SATURDAY)
    assert order == ["act", "pend"]


def test_a_step_that_raises_is_logged_and_skipped(monkeypatch, caplog):
    store = PlanStore()
    store.add(_active())
    mgr = PlanManager(store, lambda ticker: 100.0)

    def broken(plan, price, now=None):
        raise ValueError("bad plan geometry")

    monkeypatch.setattr(mgr, "_step", broken)
    caplog.set_level(logging.WARNING, logger=MANAGER_LOG)
    assert mgr.poll(now=SATURDAY) == []
    assert "poll: step failed for plan p1" in caplog.text


@pytest.mark.slow
def test_a_locked_plan_is_skipped_for_one_poll_and_the_rest_are_stepped(caplog):
    store = PlanStore()
    store.add(_active())                                   # p1 AAPL
    store.add(_active(plan_id="p2", ticker="MSFT"))
    mgr = PlanManager(store, lambda ticker: 105.0)         # arms break-even on both
    caplog.set_level(logging.INFO, logger=MANAGER_LOG)

    with transaction() as conn:
        PlanStore().lock_for_update("p1", conn=conn)       # an admin transaction holds p1
        started = time.monotonic()
        events = mgr.poll(now=SATURDAY)
        elapsed = time.monotonic() - started

    assert [(e.plan_id, e.transition) for e in events] == [("p2", "be_moved")]
    assert PlanStore().get("p1").working_stop is None
    assert PlanStore().get("p2").working_stop == 100.0
    assert "plan p1 is locked by another writer" in caplog.text
    assert elapsed < 4.0                                   # one 1s wait, not a stall
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_exit_retry.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.loops' has no attribute '_post_exit_failures'` (and `PlanManager` has no `take_exit_failures`).

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_quote_guard.py`
Expected: FAIL at collection — `ImportError: cannot import name '_usable_price'`.

- [ ] **Step 4: `_usable_price` and the quote batch guards**

In `swingbot/core/planning/plan_manager.py` add `import math` to the standard-library imports, and directly above `def quote_stamp(` add:

```python
def _usable_price(price) -> bool:
    """A quote the state machine may act on: a finite number above zero.
    ``not price`` let NaN through (NaN is truthy and ``NaN <= 0`` is False),
    and a NaN never crosses a level, so it silently looked like 'no move'
    (v189 D4)."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value > 0
```

In `_monitor_quote_worker` replace

```python
    return {t: q.to_doc() for t, q in quotes.items() if q.price}, counters.snapshot_and_clear()
```

with

```python
    return ({t: q.to_doc() for t, q in quotes.items() if _usable_price(q.price)},
            counters.snapshot_and_clear())
```

In `_price_batch_fn` replace

```python
    return QuotePrices({t: q.price for t, q in details.items() if q.price}, details)
```

with

```python
    return QuotePrices({t: q.price for t, q in details.items() if _usable_price(q.price)},
                       details)
```

- [ ] **Step 5: `_ordered`, `_step_safely` and the `poll` loop**

In `PlanManager.__init__` (before the V189-8 lock-timeout lines) add:

```python
        # v189 D3.3: exits that failed twice, drained by take_exit_failures()
        # and posted to the ops channel by commands/scanning/loops.py.
        self._exit_failures: list[dict] = []
```

Add these methods right after `poll`:

```python
    @staticmethod
    def _ordered(plans: list) -> list:
        """Stop-bearing (non-PENDING) plans first, each group in its given
        order: with a 1s lock budget per plan, exits are attempted before
        entries (v189 D3.3)."""
        return sorted(plans, key=lambda plan: plan.status == PlanStatus.PENDING)

    def _step_safely(self, plan: TradePlanV2, price: float, now) -> list[PlanEvent] | None:
        """``_step`` for one plan of a poll. None = skip the plan this poll:
        nothing was written, so nothing is emitted or bookkept."""
        try:
            return self._step(plan, price, now)
        except (PlanWriteAborted, PlanPersistFailed):
            return None          # logged where it happened: INFO refusal / ERROR rollback
        except LockTimeout:
            log.info("poll: plan %s is locked by another writer; skipped this poll",
                     plan.plan_id)
            return None
        except Exception:
            log.warning("poll: step failed for plan %s", plan.plan_id, exc_info=True)
            return None
```

In `poll`, make exactly three edits:

(a) `for plan in open_plans:` (the stepping loop, `:633`) becomes `for plan in self._ordered(open_plans):`. The ticker list for the batch fetch above it is unchanged.

(b) The quote guard

```python
            if not price or price <= 0:
                continue
```

becomes

```python
            if not _usable_price(price):
                continue
```

(c) The step call

```python
            self._warn_legacy_open_risk(plan)
            try:
                new_events = self._step(plan, price, now)
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
```

becomes

```python
            self._warn_legacy_open_risk(plan)
            new_events = self._step_safely(plan, price, now)
            if new_events is None:
                continue
```

- [ ] **Step 6: The terminal write retries once, then records the failure**

Replace V189-8's `_persist_terminal` with the three methods below, and add `take_exit_failures` after them:

```python
    def _persist_terminal(self, plan: TradePlanV2, leg: dict, status: str,
                          close_reason: str | None = None) -> bool:
        """Persist a terminal plan and its linked trade as one DB transaction.
        True when the trade was closed with it; False without a trade log.

        v189 D3.3: a failed or timed-out exit is retried once, at once, with
        the same plan, leg and observed price -- a missed stop would flatter
        the book, and the next poll may never see that price again. A refused
        stale write (PlanWriteAborted) is not a failure and is never retried."""
        if self.trade_log is None:
            self._save(plan)
            return False
        try:
            self._close_in_transaction(plan, leg, status, close_reason)
        except PlanWriteAborted:
            raise
        except Exception as first:
            log.warning("plan %s (%s): exit write failed (%s); retrying once at %s",
                        plan.plan_id, plan.ticker, first, leg.get("exit_price"))
            self._retry_close(plan, leg, status, close_reason)
        return True

    def _retry_close(self, plan: TradePlanV2, leg: dict, status: str,
                     close_reason: str | None) -> None:
        try:
            self._close_in_transaction(plan, leg, status, close_reason)
        except PlanWriteAborted:
            raise
        except Exception as exc:
            self._record_exit_failure(plan, leg, exc)
            raise PlanPersistFailed(plan.plan_id) from exc

    def _record_exit_failure(self, plan: TradePlanV2, leg: dict, exc: Exception) -> None:
        failure = {"plan_id": plan.plan_id, "ticker": plan.ticker,
                   "exit_price": float(leg["exit_price"]), "reason": leg.get("reason"),
                   "error": f"{type(exc).__name__}: {exc}"}
        self._exit_failures.append(failure)
        log.error("plan %s (%s): exit not recorded -- observed %s exit at %.4f failed "
                  "twice, the book still shows it open: %s",
                  plan.plan_id, plan.ticker, failure["reason"], failure["exit_price"],
                  failure["error"], exc_info=exc)

    def take_exit_failures(self) -> list[dict]:
        """The exits that failed twice since the last call, oldest first."""
        failures, self._exit_failures = self._exit_failures, []
        return failures
```

After `run_manager_tick` add:

```python
def drain_exit_failures() -> list[dict]:
    """The process manager's failed exits since the last call (v189 D3.3), for
    the trade_monitor loop to post; [] before the manager's first tick."""
    if _MANAGER is None:
        return []
    return _MANAGER.take_exit_failures()
```

- [ ] **Step 7: The ops-channel notice in `loops.py`**

In `swingbot/commands/scanning/loops.py`, after `_post_cooldown_note` add:

```python
def _exit_failure_text(failure: dict) -> str:
    return (f"⚠️ Exit not recorded: {failure['ticker']} plan `{failure['plan_id']}` -- "
            f"observed {failure['reason']} exit at {failure['exit_price']:.2f}. "
            "The book still shows the position open; check it by hand.")


async def _post_exit_failures(failures: list[dict]) -> None:
    """v189 D3.3: an exit the plan manager could not record after one retry is
    never silent -- one line per plan on the ops channel (else the trades
    channel). Not silent(): it must notify. A failed send is one WARNING and
    never raises into the monitor tick."""
    if not failures:
        return
    channel = _ops_channel()
    if channel is None:
        log.error("exit not recorded for %d plan(s) and no ops channel is configured: %s",
                  len(failures), ", ".join(f["plan_id"] for f in failures))
        return
    for failure in failures:
        try:
            await channel.send(content=_exit_failure_text(failure))
        except Exception:
            log.warning("could not post the exit-failure notice for plan %s",
                        failure.get("plan_id"), exc_info=True)
```

In `trade_monitor`, directly after

```python
    if plan_events:
        await _post_plan_events(plan_events)
```

add

```python
    await _post_exit_failures(plan_manager.drain_exit_failures())
```

- [ ] **Step 8: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_exit_retry.py`
Expected: PASS (12 tests, 0 failed, 0 xfailed).

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_quote_guard.py`
Expected: PASS (20 tests, 0 failed, 0 xfailed).

- [ ] **Step 9: Run what the diff reaches**

Run each (all must PASS unchanged):
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_atomic_writes.py`
`python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py` (its `test_a_failed_balance_update_rolls_the_close_back` now fails the close twice and still sees no `closed` event, an ACTIVE plan and an open trade)
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_logging.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_poll_window.py`
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_shared_quote.py`
`python scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py`
`python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed. A test that pins the plan stepping order for mixed PENDING and ACTIVE plans in one poll is the ordering D3.3 introduces: report it with the test name rather than dropping `_ordered`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `poll` drops from 20 to 19 (the `or` in the quote guard is gone; the `if new_events is None` replaces the `except`); `_step_safely` 5, `_persist_terminal` 4, `_retry_close` 3.

- [ ] **Step 10: Commit**

Two scoped commits (the manager, then the Discord surface):

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_quote_guard.py
git commit -m "feat(planning): exit retried once then recorded; locked plans skipped; stop-bearing plans first; finite quotes only (v189 V189-9)"
git add swingbot/commands/scanning/loops.py tests/planning/test_plan_manager_exit_retry.py
git commit -m "feat(loops): post exits the plan manager could not record to the ops channel (v189 V189-9)"
```

(Both files are edited and every Step 8–9 run is green before the first commit; the two commits only split that green state by concern.)

