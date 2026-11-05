# Durable lifecycle notifications — part 2: atomic actions

**Bump:** bot patch, ui patch
**Edge:** harvest
**Spec:** [Approved v197 spec](../specs/2026-10-28-v197-durable-lifecycle-notifications.md)

Read the [index](2026-10-28-v197-durable-lifecycle-notifications_0-index.md) for frozen event/transaction contracts and execution constraints. Read part 1's exact event/repository interfaces before implementing these tasks.

## Parallelisation

V197-3 follows the storage contract and precedes V197-4, which precedes V197-4b: the admin orchestrator requires fresh row locks, strict connection-aware settlement and explicit post-commit hooks. V197-4b consumes the tested service in existing routes; all three tasks share the manual close boundary and run sequentially. Implementation requires merged v194; this document authorizes no implementation or production operation.

# Phase 2 — Atomic admin transitions

### Task V197-3: Make manual settlement and fresh row reads transaction-composable
**Model:** opus — the change crosses planning, tracking and database boundaries to preserve atomic settlement.

**Files:**
- Modify: `swingbot/core/planning/account.py`
- Modify: `swingbot/core/tracking/performance.py`
- Modify: `swingbot/core/planning/plan_store.py`
- Create: `tests/tracking/test_manual_close_transaction.py`
- Modify: `tests/tracking/test_close_trade_manual_exit_price.py`

**Interfaces:** Extends account `_sum_realized_pnl`, `load_account_config`, `save_account_config` and `apply_realized_pnl` with keyword-only `conn=None`. Creates `TradeLog.close_trade_manual_in_transaction(trade_id, reason, *, exit_price, closed_at, transition_id, conn) -> dict | None` and `after_manual_close_commit(trade) -> None`. Extends PlanStore `get_record/get` with conn/for_update and makes update's existence check share its connection. V197-4 owns the outer transaction and advisory-lock order. Ordinary manual/automatic callers retain their existing public method behavior and safe best-effort hooks.

- [ ] **Step 1: Write failing transactional settlement tests.** Read schema-change and code-complexity guidance; invoke replicate-prod-db before the first DB test using shared infrastructure. Existing root test fixtures already expose db_conn/db_engine. Create `tests/tracking/test_manual_close_transaction.py`:

```python
from contextlib import contextmanager
import pytest
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan
from swingbot.core.db.repositories.plans import PlanRepository

AT = "2026-10-28T12:00:00+00:00"


def seed(conn, *, legs=None):
    AccountRepository().save(dict(base_balance=1000, balance=1000), conn=conn)
    TradeRepository().insert(dict(trade_id="manual-t", ticker="AAPL", strategy="RSI",
        horizon="2w", direction="bullish", status="open", opened_at=AT,
        entry=100, stop_loss=95, shares=10, legs=legs or []), conn=conn)


def close(conn, price=101):
    return TradeLog().close_trade_manual_in_transaction("manual-t", "manual",
        exit_price=price, closed_at=AT, transition_id="transition-t", conn=conn)


def test_all_account_and_trade_io_uses_supplied_connection(db_conn, monkeypatch):
    seed(db_conn)
    def no_implicit_connection():
        raise AssertionError("escaped caller transaction")
    monkeypatch.setattr("swingbot.core.db.repositories.base.get_engine", no_implicit_connection)
    monkeypatch.setattr(perf, "_manual_close_quote", lambda ticker: pytest.fail("network inside transaction"))
    monkeypatch.setattr(perf, "_after_close", lambda trade: pytest.fail("premature journal hook"))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: pytest.fail("premature snapshot"))
    result = close(db_conn)
    assert result["realized_pnl_amount"] == 10
    assert result["account_balance_after"] == 1010
    assert result["manual_transition_id"] == "transition-t"
    assert result["closed_at"] == AT
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "closed"
    assert account.load_account_config(conn=db_conn)["balance"] == 1010
    history = AccountRepository().history(conn=db_conn)
    assert len(history) == 1
    assert history[0]["pnl_amount"] == 10


def test_outer_rollback_reverts_trade_balance_and_history(db_conn):
    seed(db_conn)
    before = AccountRepository().load(conn=db_conn)
    with pytest.raises(RuntimeError), db_conn.begin_nested():
        close(db_conn)
        raise RuntimeError("later queue insertion failed")
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "open"
    assert AccountRepository().load(conn=db_conn) == before
    assert AccountRepository().history(conn=db_conn) == []


def test_settlement_failure_propagates_without_writing_trade(db_conn, monkeypatch):
    seed(db_conn)
    def failed(*args, **kwargs):
        raise RuntimeError("account save failed")
    monkeypatch.setattr(account, "apply_realized_pnl", failed)
    with pytest.raises(RuntimeError, match="account save failed"), db_conn.begin_nested():
        close(db_conn)
    assert TradeRepository().get("manual-t", conn=db_conn)["status"] == "open"


def test_missing_price_never_fetches_and_never_invents_realized_pnl(db_conn, monkeypatch):
    seed(db_conn)
    monkeypatch.setattr(perf, "_manual_close_quote", lambda ticker: pytest.fail("unexpected quote"))
    result = close(db_conn, price=None)
    assert result["status"] == "closed"
    assert result.get("exit_price") is None
    assert result.get("realized_pnl_amount") is None
    assert AccountRepository().history(conn=db_conn) == []


def test_partial_close_preserves_recorded_leg_and_settles_once(db_conn):
    seed(db_conn, legs=[dict(fraction=0.5, exit_price=110, r=2, reason="tp1")])
    result = close(db_conn, price=105)
    assert [leg["exit_price"] for leg in result["legs"]] == [110, 105]
    assert result["realized_pnl_amount"] == 75
    assert account.load_account_config(conn=db_conn)["balance"] == 1075
    assert close(db_conn, price=105) is None
    assert len(AccountRepository().history(conn=db_conn)) == 1


def test_post_commit_hook_is_explicit_and_uses_recorded_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(perf, "_after_close", lambda trade: calls.append(("journal", trade["id"])))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: calls.append(("snapshot", None)))
    TradeLog().after_manual_close_commit({"id": "manual-t"})
    assert calls == [("journal", "manual-t"), ("snapshot", None)]


def test_plan_get_and_update_share_outer_transaction_without_python_lock(db_conn, monkeypatch):
    PlanRepository().insert(_plan("11111111-1111-4111-8111-111111111111", status="ACTIVE"), conn=db_conn)
    store = PlanStore()
    @contextmanager
    def forbidden_lock():
        pytest.fail("caller-owned DB transaction must not wait on process-local plan lock")
        yield
    monkeypatch.setattr("swingbot.core.planning.plan_store._LOCK", forbidden_lock())
    plan = store.get("11111111-1111-4111-8111-111111111111", conn=db_conn, for_update=True)
    with db_conn.begin_nested() as savepoint:
        plan.status = "CLOSED"
        store.update(plan, conn=db_conn)
        assert store.get_record(plan.plan_id, conn=db_conn)["status"] == "CLOSED"
        savepoint.rollback()
    assert store.get_record(plan.plan_id, conn=db_conn)["status"] == "ACTIVE"
```

Add a compatibility assertion to the existing `tests/tracking/test_close_trade_manual_exit_price.py`; retain the current book fixture and all current price/partial-fill assertions:

```python

def test_legacy_manual_close_still_invokes_safe_post_close_hooks(book, monkeypatch):
    calls = []
    monkeypatch.setattr(perf, "_after_close", lambda trade: calls.append(trade["id"]))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: calls.append("snapshot"))
    assert TradeLog().close_trade_manual("t1", exit_price=101)
    assert calls == ["t1", "snapshot"]
```

- [ ] **Step 2: Run the narrow red test.** Run `python scripts/dev/testrun.py file tests/tracking/test_manual_close_transaction.py`. Expected failures are missing transaction methods/signatures. Do not call an unavailable DB skip a pass.

- [ ] **Step 3: Thread conn through the existing account functions without changing their math.** These are narrow signature/call-site edits inside four functions, not replacements of their existing defaults, seeding or P&L calculation. Apply all edits in this table; no other caller changes are required:

| Function | Exact edit |
|---|---|
| `_sum_realized_pnl` | Signature `def _sum_realized_pnl(*, conn=None) -> float:`; use `trades_repo().list_all(**({} if conn is None else {"conn": conn}))` instead of `list_all()`; retain every existing sum/leg-fallback branch. |
| `load_account_config` | Signature `def load_account_config(*, conn=None) -> dict:`; immediately before `stored = ...`, add `tx = {} if conn is None else {"conn": conn}`; use `account_repo().load(**tx)`, all three `_sum_realized_pnl(**tx)` calls, and `save_account_config(merged, **tx)` / `save_account_config(defaults, **tx)`. |
| `save_account_config` | Signature `def save_account_config(config: dict, *, conn=None) -> None:`; forward `conn=conn` to the existing account repository save. |
| `apply_realized_pnl` | Signature `def apply_realized_pnl(pnl_amount: float, meta: dict = None, *, conn=None) -> dict:`; add `tx = {} if conn is None else {"conn": conn}` before loading; call `load_account_config(**tx)` and `save_account_config(config, **tx)`; retain the existing P&L addition and history-entry construction. |

The empty kwargs on default calls preserve existing monkeypatch/test call conventions while actual supplied connections reach every nested read/write. `AccountRepository.save/append_history/load` already accept conn (verified); no repository change or alternate account store is needed. Keep the documented ordering: account settlement calculates prior stored realized P&L and adds this trade before its final closed-row upsert. Reading the just-closed row and adding it again would double count.

In `performance.py`, change only the signature and exception boundary of the existing `_settle_account_balance` method. Its existing price, share and leg calculations stay verbatim:

Use the exact signature `def _settle_account_balance(self, t: dict, *, conn=None) -> None:`.

Replace its existing `try`/`except` block after `pnl_amount` is calculated with this complete block:

```python
        try:
            tx = {} if conn is None else {"conn": conn}
            updated_cfg = account_module.apply_realized_pnl(
                pnl_amount,
                {"trade_id": t.get("id"), "ticker": t.get("ticker"), "status": t.get("status")},
                **tx,
            )
            t["realized_pnl_amount"] = pnl_amount
            t["account_balance_after"] = updated_cfg.get("balance")
        except Exception:
            if conn is not None:
                raise  # authoritative admin transaction must roll back
            log.warning("account settlement failed for trade %s", t.get("id"), exc_info=True)
```

Add these methods to `TradeLog` immediately before the existing `close_trade_manual`, without changing that existing method:

```python
    def close_trade_manual_in_transaction(self, trade_id, reason, *, exit_price,
                                          closed_at, transition_id, conn) -> dict | None:
        """Close a freshly locked trade; caller owns advisory lock and commit."""
        import sqlalchemy as sa
        from swingbot.core.db.repositories.trades import trades_repo
        from swingbot.core.db.schema import trades
        if conn is None:
            raise ValueError("caller_connection_required")
        row = conn.execute(sa.select(trades).where(
            trades.c.trade_id == trade_id).with_for_update()).one_or_none()
        if row is None:
            return None
        trade = _json_record(trades_repo()._record(row))
        if trade.get("status") != "open":
            return None
        if exit_price:
            _apply_exit_price(trade, exit_price, reason="manual")
        trade.update(status="closed", closed_at=closed_at, close_reason=reason,
                     manual_transition_id=transition_id)
        self._settle_account_balance(trade, conn=conn)
        self._db_upsert(trade, conn=conn)
        return trade

    def after_manual_close_commit(self, trade: dict) -> None:
        """Run derived effects only after the orchestrator's successful commit."""
        _after_close(trade)
        _refresh_snapshot_safely()
```

This path acquires no process-local `_LOCK`, makes no pricing request, and invokes no close hook while the database transaction is open. `_json_record` makes a fresh normalized snapshot; `_db_upsert` already takes conn. The new method must not call the old `close_trade_manual`, whose separate transaction/hooks would defeat atomicity.

- [ ] **Step 4: Make PlanStore fresh reads/updates compose on the same connection.** Add `import sqlalchemy as sa` to `plan_store.py`. Replace `get_record`, `get` and `update`, and add the private update helper as follows; leave the other store methods intact:

```python
    def get_record(self, plan_id: str, *, conn=None, for_update=False) -> dict | None:
        from swingbot.core.db.repositories.plans import plans_repo
        from swingbot.core.db.schema import plans
        repo = plans_repo()
        if not for_update:
            record = repo.get(plan_id, conn=conn)
        else:
            if conn is None:
                raise ValueError("locking_read_requires_connection")
            row = conn.execute(sa.select(plans).where(
                plans.c.plan_id == plan_id).with_for_update()).one_or_none()
            record = None if row is None else repo._record(row)
        return None if record is None else _normalised(record)

    def get(self, plan_id: str, *, conn=None, for_update=False) -> TradePlanV2 | None:
        record = self.get_record(plan_id, conn=conn, for_update=for_update)
        return plan_from_dict(record) if record is not None else None

    def _update_record(self, plan: TradePlanV2, *, conn=None) -> None:
        if self.get_record(plan.plan_id, conn=conn) is None:
            raise KeyError(plan.plan_id)
        self._persist(plan_to_dict(plan), conn=conn)

    def update(self, plan: TradePlanV2, *, conn=None) -> None:
        if conn is not None:
            self._update_record(plan, conn=conn)
            return
        with _LOCK:
            self._update_record(plan)
```

Skipping the process-local lock only for caller-owned transactions avoids taking locks in opposite order: a process-local writer may already hold `_LOCK` while waiting for this row. SQL locks supply the transactional path's exclusion. The normal update path retains its existing in-process lock.

- [ ] **Step 5: Verify atomicity and unchanged legacy behavior.** Run `python scripts/dev/testrun.py file tests/tracking/test_manual_close_transaction.py` and `python scripts/dev/testrun.py file tests/tracking/test_close_trade_manual_exit_price.py`. Require zero failures/xfailed and actual DB coverage. Run `python scripts/dev/complexity_gate.py`; the changed settlement function must remain below 15, as must every added method. Do not run a full suite. V197-4 adds end-to-end failure injection around the queue commit and true post-commit observation.

- [ ] **Step 6: Commit the verified transaction primitives.** After review and freshness checks, stage the five named paths and commit `refactor(v197): compose manual settlement on caller transactions`. No release bump or deployment occurs here; this is a prerequisite for the next task. The plan author executes no source edit, test or commit.

### Task V197-4: Commit linked lifecycle state and its notification atomically
**Model:** opus — the admin orchestrator coordinates planning, tracking, account and queue transactions.

**Files:**
- Create: `swingbot/admin/api_v1/lifecycle_commands.py`
- Create: `tests/admin/test_lifecycle_commands_db.py`

**Interfaces:** Consumes V197-3's caller-connection methods, V197-1's event builder and V197-2's enqueue. Creates `close_plan_atomic(plan_id: str, reason: str = 'manual') -> None`, `close_legacy_atomic(trade_id: str) -> None`, `cancel_plan_atomic(plan_id: str) -> None`, `LifecycleConflict` and `LifecycleNotFound`. V197-4b connects these to the existing HTTP routes. The command owns the commit; only a committed result reaches post-close hooks.

- [ ] **Step 1: Write failing database regressions.** Invoke replicate-prod-db before the task's first DB test and use shared infrastructure. The existing root conftest routes all repository connections to the test engine and exposes `store_db`; no new fixture infrastructure is required. Create `tests/admin/test_lifecycle_commands_db.py`:

```python
from concurrent.futures import ThreadPoolExecutor
import pytest
from swingbot import config
from swingbot.admin.api_v1 import lifecycle_commands as command
from swingbot.admin.api_v1 import trade_commands
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning import account
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade

PLAN = "11111111-1111-4111-8111-111111111111"
TRADE = "lifecycle-trade"


@pytest.fixture
def book(store_db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(trade_commands, "_override_stamp",
                        lambda ticker: {"exit_price": 102, "price_source": "quote"})
    monkeypatch.setattr(command, "_manual_close_quote", lambda ticker: 102)
    monkeypatch.setattr(command.rp, "cached_daily_bars", lambda ticker: None)
    hooks = []
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", lambda self, trade: hooks.append(trade))
    AccountRepository().save(dict(base_balance=1000, balance=1000))
    PlanRepository().insert(_plan(PLAN, status="ACTIVE"))
    TradeRepository().insert(perf._db_record(_trade(TRADE, plan_id=PLAN)))
    return hooks


def snapshot():
    return dict(plan=PlanRepository().get(PLAN), trade=TradeRepository().get(TRADE),
                account=AccountRepository().load(), history=AccountRepository().history(),
                events=NotifyQueueRepository().list_all())


def fail_after(fn):
    def wrapped(*args, **kwargs):
        fn(*args, **kwargs)
        raise RuntimeError("injected write failure")
    return wrapped


@pytest.mark.parametrize("point", ["account", "trade", "plan", "queue"])
def test_any_authoritative_write_failure_rolls_everything_back(book, monkeypatch, point):
    before = snapshot()
    if point == "account":
        monkeypatch.setattr(account, "apply_realized_pnl", fail_after(account.apply_realized_pnl))
    elif point == "trade":
        monkeypatch.setattr(TradeLog, "_db_upsert", staticmethod(fail_after(TradeLog._db_upsert)))
    elif point == "plan":
        monkeypatch.setattr(PlanStore, "update", fail_after(PlanStore.update))
    else:
        monkeypatch.setattr(NotifyQueueRepository, "enqueue", fail_after(NotifyQueueRepository.enqueue))
    with pytest.raises(RuntimeError, match="injected write failure"):
        command.close_plan_atomic(PLAN)
    assert snapshot() == before
    assert book == []


def test_success_commits_one_event_and_one_settlement_before_hooks(book, monkeypatch):
    observations = []
    def observe(self, closed):
        committed = snapshot()  # independent real connections after outer commit
        assert committed["plan"]["status"] == "CLOSED"
        assert committed["trade"]["status"] == "closed"
        assert len(committed["history"]) == 1
        assert len(committed["events"]) == 1
        observations.append(closed["id"])
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", observe)
    command.close_plan_atomic(PLAN)
    state = snapshot()
    assert observations == [TRADE]
    assert state["account"]["balance"] == 1010
    event = state["events"][0]
    assert event["kind"] == "plan_transition"
    assert event["payload"]["prior_status"] == "ACTIVE"
    assert event["payload"]["new_status"] == "CLOSED"
    assert event["payload"]["trade"]["exit_price"] == 102
    history = state["plan"]["status_history"][-1]
    assert event["transition_id"] == history["transition_id"]
    assert state["trade"]["manual_transition_id"] == history["transition_id"]
    assert event["payload"]["occurred_at"] == history["at"]


def test_concurrent_double_close_settles_and_enqueues_only_once(book):
    def attempt():
        try:
            command.close_plan_atomic(PLAN)
            return "closed"
        except command.LifecycleConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["closed", "conflict"]
    state = snapshot()
    assert len(state["events"]) == len(state["history"]) == 1
    assert len(book) == 1


def test_cancel_is_unfilled_and_rollback_preserves_pending(book, monkeypatch):
    row = PlanRepository().get(PLAN)
    row["status"] = "PENDING"
    PlanRepository().upsert(row)
    before = snapshot()
    with monkeypatch.context() as patch:
        patch.setattr(NotifyQueueRepository, "enqueue", fail_after(NotifyQueueRepository.enqueue))
        with pytest.raises(RuntimeError):
            command.cancel_plan_atomic(PLAN)
    assert snapshot() == before
    command.cancel_plan_atomic(PLAN)
    event = NotifyQueueRepository().list_all()[0]
    assert event["payload"]["new_status"] == "CANCELLED"
    assert event["payload"]["prior_status"] == "PENDING"
    assert "trade" not in event["payload"]
    assert AccountRepository().history() == []
    assert TradeRepository().get(TRADE)["status"] == "open"
    assert book == []


def test_legacy_close_preserves_recorded_fill_and_freezes_destination(book, monkeypatch):
    row = TradeRepository().get(TRADE)
    row["plan_id"] = None
    TradeRepository().upsert(row)
    command.close_legacy_atomic(TRADE)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "99")
    event = NotifyQueueRepository().list_all()[0]
    assert event["kind"] == "trade_closed"
    assert event["target_channel_id"] == "5"
    assert event["payload"]["trade_id"] == TRADE
    assert event["payload"]["trade"]["exit_price"] == 102
    assert event["payload"]["trade"]["realized_pnl_amount"] == 10
    assert len(book) == 1


def test_linked_trade_id_uses_same_atomic_plan_command(book):
    command.close_legacy_atomic(TRADE)
    state = snapshot()
    assert state["plan"]["status"] == "CLOSED"
    assert state["events"][0]["kind"] == "plan_transition"
    assert len(state["events"]) == 1


def test_post_commit_hook_failure_does_not_relabel_committed_action(book, monkeypatch):
    def fail(self, trade):
        raise RuntimeError("derived journal unavailable")
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", fail)
    command.close_plan_atomic(PLAN)
    assert snapshot()["plan"]["status"] == "CLOSED"
    assert NotifyQueueRepository().pending() == 1
```

- [ ] **Step 2: Run the narrow red test.** Run `python scripts/dev/testrun.py file tests/admin/test_lifecycle_commands_db.py`. The new service should be missing; resolve fixture/connectivity problems separately. These tests must reach real Postgres, including the concurrent callers and hook observation from independent connections.

- [ ] **Step 3: Implement the complete command service.** Write `swingbot/admin/api_v1/lifecycle_commands.py`:

```python
"""Atomic admin transitions and immutable notification recording."""
from datetime import datetime, timezone
import logging
from uuid import uuid4
import sqlalchemy as sa
from swingbot import config
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.db.schema import trades
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus, record_transition
from swingbot.core.tracking.performance import TradeLog, _json_record, _manual_close_quote

log = logging.getLogger(__name__)
CLOSEABLE = (PlanStatus.ACTIVE, PlanStatus.PARTIAL)


class LifecycleNotFound(LookupError):
    pass


class LifecycleConflict(ValueError):
    pass


def _serialize_settlement(conn):
    conn.execute(sa.text("SELECT pg_advisory_xact_lock(197, 1)"))


def _require_plan(plan, statuses):
    if plan is None:
        raise LifecycleNotFound("No plan with that ID.")
    if plan.status not in statuses:
        raise LifecycleConflict(f"Cannot apply this action to a {plan.status} plan.")


def _prepared_plan(plan_id):
    plan = PlanStore().get(plan_id)
    _require_plan(plan, CLOSEABLE)
    # Lazy import keeps HTTP registration separate from the service module.
    from .trade_commands import _override_stamp
    stamp = _override_stamp(plan.ticker)
    quote = stamp.get("exit_price") if stamp and stamp.get("price_source") == "quote" else None
    if quote is None:
        quote = _manual_close_quote(plan.ticker)
    try:
        bars = rp.cached_daily_bars(plan.ticker)
    except Exception:
        bars = None
    return plan.ticker, stamp, quote, bars


def _locked_linked_trade(plan_id, conn):
    row = conn.execute(sa.select(trades).where(trades.c.doc["plan_id"].astext == plan_id)
        .order_by(trades.c.trade_id).limit(1).with_for_update()).one_or_none()
    return None if row is None else _json_record(trades_repo()._record(row))


def _locked_trade(trade_id, conn):
    row = conn.execute(sa.select(trades).where(trades.c.trade_id == trade_id)
                       .with_for_update()).one_or_none()
    return None if row is None else _json_record(trades_repo()._record(row))


def _close_linked(linked, quote, at, transition_id, conn):
    if linked is None or linked.get("status") != "open":
        return None
    closed = TradeLog().close_trade_manual_in_transaction(linked["id"],
        "manual (plan close, admin UI)", exit_price=quote, closed_at=at,
        transition_id=transition_id, conn=conn)
    if closed is None:
        raise LifecycleConflict("The linked trade changed; retry the action.")
    return closed


def _enqueue_plan(plan, prior, closed, channel, conn):
    transition = plan.status_history[-1]
    payload = dict(ticker=plan.ticker, direction=plan.direction, plan_id=plan.plan_id,
        trade_id=closed["id"] if closed else None, prior_status=prior, new_status=plan.status,
        reason=transition["reason"], occurred_at=transition["at"])
    if closed is not None:
        payload["trade"] = closed
    event = make_event(transition_id=transition["transition_id"], kind="plan_transition",
        target_channel_id=channel, occurred_at=transition["at"], payload=payload)
    notify_queue_repo().enqueue(event, conn=conn)


def _after_commit(closed):
    if closed is None:
        return
    try:
        TradeLog().after_manual_close_commit(closed)
    except Exception:
        log.error("lifecycle post-commit derived hooks failed trade=%s", closed["id"])


def close_plan_atomic(plan_id: str, reason: str = "manual") -> None:
    ticker, stamp, quote, bars = _prepared_plan(plan_id)
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    store = PlanStore()
    with transaction() as conn:
        _serialize_settlement(conn)
        plan = store.get(plan_id, conn=conn, for_update=True)
        _require_plan(plan, CLOSEABLE)
        if plan.ticker != ticker:
            raise LifecycleConflict("The plan changed; retry the action.")
        prior = plan.status
        at, transition_id = datetime.now(timezone.utc).isoformat(), str(uuid4())
        linked = _locked_linked_trade(plan_id, conn)
        closed = _close_linked(linked, quote, at, transition_id, conn)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at,
            extra={"transition_id": transition_id, "prior_status": prior, "override": stamp})
        if prior == PlanStatus.PARTIAL:
            rp.stamp_runner_path(plan, lambda ticker: bars, source="live")
        store.update(plan, conn=conn)
        _enqueue_plan(plan, prior, closed, channel, conn)
    _after_commit(closed)


def cancel_plan_atomic(plan_id: str) -> None:
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    store = PlanStore()
    with transaction() as conn:
        _serialize_settlement(conn)
        plan = store.get(plan_id, conn=conn, for_update=True)
        _require_plan(plan, (PlanStatus.PENDING,))
        prior = plan.status
        at, transition_id = datetime.now(timezone.utc).isoformat(), str(uuid4())
        record_transition(plan, PlanStatus.CANCELLED, reason="manual", at=at,
            extra={"transition_id": transition_id, "prior_status": prior})
        store.update(plan, conn=conn)
        _enqueue_plan(plan, prior, None, channel, conn)


def _require_open_trade(trade):
    if trade is None:
        raise LifecycleNotFound("No trade with that ID.")
    if trade.get("status") != "open":
        raise LifecycleConflict("Trade is already closed.")


def _enqueue_trade(closed, channel, conn):
    payload = dict(ticker=closed["ticker"], direction=closed["direction"],
        plan_id=closed.get("plan_id"), trade_id=closed["id"], prior_status="open",
        new_status=closed["status"], reason=closed["close_reason"],
        occurred_at=closed["closed_at"], trade=closed)
    event = make_event(transition_id=closed["manual_transition_id"], kind="trade_closed",
        target_channel_id=channel, occurred_at=closed["closed_at"], payload=payload)
    notify_queue_repo().enqueue(event, conn=conn)


def close_legacy_atomic(trade_id: str) -> None:
    before = TradeLog().get_trade_by_id(trade_id)
    _require_open_trade(before)
    if before.get("plan_id"):
        close_plan_atomic(before["plan_id"])
        return
    quote = _manual_close_quote(before["ticker"])
    channel = config.DISCORD_CHANNEL_TRADES_HISTORY_ID
    with transaction() as conn:
        _serialize_settlement(conn)
        current = _locked_trade(trade_id, conn)
        _require_open_trade(current)
        if current.get("plan_id") or current["ticker"] != before["ticker"]:
            raise LifecycleConflict("The trade changed; retry the action.")
        closed = TradeLog().close_trade_manual_in_transaction(trade_id,
            "manual (admin UI)", exit_price=quote,
            closed_at=datetime.now(timezone.utc).isoformat(), transition_id=str(uuid4()), conn=conn)
        if closed is None:
            raise LifecycleConflict("The trade changed; retry the action.")
        _enqueue_trade(closed, channel, conn)
    _after_commit(closed)
```

All authoritative writes finish before `_after_commit`. The pre-read only prepares data; the command revalidates the current locked row. Advisory lock `(197, 1)` is acquired before plan/trade locks and before settlement reads, including initial account seeding. The linked-trade-ID route delegates to the plan command before taking any trade lock, preserving lock order and preventing a closed trade behind an active plan. A cancellation changes the pending plan and queues its unfilled transition without inventing settlement.

The fallback quote preserves the old manual-close behavior when an override stamp has no fresh quote. Both quote attempts occur before locking, and the resulting price is passed explicitly; no delivery process will calculate it again. Runner bars are also read before locking, while the path stamp uses the final locked plan plus that prepared data. Existing safe `_override_stamp`, `_manual_close_quote` and `stamp_runner_path` symbols were verified in source; `cached_daily_bars(ticker)` is a disk-cache reader, not a provider fetch.

- [ ] **Step 4: Verify rollback, duplicate actions and committed hooks.** Run `python scripts/dev/testrun.py file tests/admin/test_lifecycle_commands_db.py`. Require every injected failure to leave trade, plan, account, balance history and queue byte-for-byte equivalent at the repository boundary, with no hook call. Require concurrent closes to produce one settlement and one event. Run `python scripts/dev/complexity_gate.py`; every helper must remain below 15. No full suite here.

- [ ] **Step 5: Commit the independently testable service.** After normal review and freshness checks, run `git add swingbot/admin/api_v1/lifecycle_commands.py tests/admin/test_lifecycle_commands_db.py` and `git commit -m "feat(v197): commit manual lifecycle state and notification atomically"`. The author does not execute these commands. V197-4b activates the service in the routes; no intermediate deployment is permitted.

### Task V197-4b: Route close/cancel actions through the atomic service and report failures truthfully
**Model:** sonnet — the task wires existing HTTP endpoints to the tested command boundary.

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py`
- Modify: `tests/admin/test_api_v1_trade_commands.py`

**Interfaces:** Consumes V197-4's three atomic service functions and its two domain exceptions. Preserves route URLs, authentication, successful response projections, `_close_plan(store, plan, reason='manual')` as the bulk-close patch surface, and the bulk `closed`/`failed`/`tickers` response. Removes `_queue_notify` as a competing best-effort producer.

- [ ] **Step 1: Update the existing queue observations and add failing endpoint tests.** Invoke replicate-prod-db before the first DB test. The existing `seed`, `logged_in` and quote-isolation fixtures remain in `tests/admin/test_api_v1_trade_commands.py`. Replace its destructive queue fixture with:

```python
@pytest.fixture
def notify_queue():
    """Inspect durable events without acknowledging or deleting them."""
    from swingbot.core.db.repositories.notify_queue import notify_queue_repo
    return notify_queue_repo().list_all
```

Update the three direct identity assertions to the canonical payload shape: `r.get('plan_id')` becomes `r['payload'].get('plan_id')` in `test_closing_a_plan_queues_a_notify_record_for_that_plan`; `r.get('trade_id')` becomes `r['payload'].get('trade_id')` in `test_close_an_open_legacy_trade`. Replace the assertion in `test_closing_a_legacy_trade_reaches_the_db_queue_under_its_trade_id` with:

```python
    queued = notify_queue_repo().list_all()
    assert [row["payload"]["trade_id"] for row in queued] == [_TRADE_ID]
    assert queued[0]["payload"]["trade"]["id"] == _TRADE_ID
```

The existing bulk count test still reads `event['kind']` at the top level; preserve it. Revise test comments referring to destructive drain or top-level trade_id so they describe immutable nested snapshots. Append the following tests:

```python

def test_close_queue_failure_returns_503_and_rolls_back(seed, logged_in, monkeypatch):
    from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.performance import TradeLog
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    def fail(self, event, *, conn=None):
        raise RuntimeError("private diagnostic must not reach HTTP")
    monkeypatch.setattr(NotifyQueueRepository, "enqueue", fail)
    response = logged_in.post(f"/api/v1/trades/{_PLAN_ID}/close")
    assert_error(response, "unavailable", 503)
    assert "private diagnostic" not in response.get_data(as_text=True)
    assert PlanStore().get(_PLAN_ID).status == "ACTIVE"
    assert TradeLog().get_trade_by_id(_TRADE_ID)["status"] == "open"


def test_cancel_queue_failure_keeps_plan_pending(seed, logged_in, monkeypatch):
    from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
    from swingbot.core.planning.plan_store import PlanStore
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])
    def fail(self, event, *, conn=None):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(NotifyQueueRepository, "enqueue", fail)
    assert_error(logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel"), "unavailable", 503)
    assert PlanStore().get(_PLAN_ID).status == "PENDING"


def test_cancel_queues_unfilled_transition_with_recorded_identity(seed, logged_in, notify_queue):
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])
    assert logged_in.post(f"/api/v1/trades/{_PLAN_ID}/cancel").status_code == 200
    events = notify_queue()
    assert len(events) == 1
    assert events[0]["kind"] == "plan_transition"
    assert events[0]["payload"]["new_status"] == "CANCELLED"
    assert events[0]["payload"]["prior_status"] == "PENDING"
    assert "trade" not in events[0]["payload"]
    assert events[0]["transition_id"] and events[0]["event_id"]


def test_bulk_failure_counts_only_committed_positions(seed, logged_in, monkeypatch, notify_queue):
    from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
    from swingbot.core.planning.plan_store import PlanStore
    first = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    seed(plans=[_plan(first, ticker="AAPL", status="ACTIVE"),
                _plan(second, ticker="MSFT", status="ACTIVE")])
    original = NotifyQueueRepository.enqueue
    def fail_one(self, event, *, conn=None):
        if event["payload"]["plan_id"] == first:
            raise RuntimeError("queue failed for first position")
        return original(self, event, conn=conn)
    monkeypatch.setattr(NotifyQueueRepository, "enqueue", fail_one)
    response = logged_in.post("/api/v1/trades/close-open")
    assert response.status_code == 200
    assert response.get_json() == {"closed": 1, "failed": 1, "tickers": ["MSFT"]}
    assert PlanStore().get(first).status == "ACTIVE"
    assert PlanStore().get(second).status == "CLOSED"
    assert [event["payload"]["plan_id"] for event in notify_queue()] == [second]
```

- [ ] **Step 2: Run the narrow red test.** Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py`. The newly asserted rollback/error behavior should fail on the old best-effort queue route. Existing authentication, invalid-status, not-found, bulk scope and fill/override tests must remain part of this same file's checks.

- [ ] **Step 3: Wire the service without changing response projections.** In `trade_commands.py`, add `from . import lifecycle_commands as lifecycle`. Delete the old `_queue_notify` function entirely; only the service owns queue insertion. Keep `_linked_trade`, `_plan_row`, `_trade_row`, override helpers and bulk scope logic. Replace `_close_plan` with the compatibility adapter:

```python
def _close_plan(store: PlanStore, plan, reason: str = "manual") -> None:
    """Keep the bulk-close seam while the service owns fresh reads and commit."""
    lifecycle.close_plan_atomic(plan.plan_id, reason)
```

Use normal module indentation for `def _close_plan`. Add these helpers before the route declarations:

```python
def _perform_lifecycle(action, identity, projection):
    try:
        action(identity)
    except lifecycle.LifecycleNotFound as exc:
        return error("not_found", str(exc), 404)
    except lifecycle.LifecycleConflict as exc:
        return error("invalid", str(exc), 422)
    except Exception as exc:
        log.error("admin lifecycle action could not commit type=%s", type(exc).__name__)
        return error("unavailable", "The action could not be saved. Try again.", 503)
    # Projection failure after commit must not be described as an action rollback.
    return projection(identity)


def _reject_legacy_cancel(trade_id):
    if TradeLog().get_trade_by_id(trade_id) is None:
        raise lifecycle.LifecycleNotFound("No trade with that ID.")
    raise lifecycle.LifecycleConflict("Only plans can be cancelled.")
```

Replace only the bodies of the existing decorated `close_trade` and `cancel_trade` routes with the following complete definitions, retaining each existing URL decorator and `@require_auth` exactly once:

```python
def close_trade(trade_id: str):
    if _looks_like_a_plan_id(trade_id):
        return _perform_lifecycle(lifecycle.close_plan_atomic, trade_id, _plan_row)
    return _perform_lifecycle(lifecycle.close_legacy_atomic, trade_id, _trade_row)


def cancel_trade(trade_id: str):
    action = lifecycle.cancel_plan_atomic if _looks_like_a_plan_id(trade_id) else _reject_legacy_cancel
    return _perform_lifecycle(action, trade_id, _plan_row)
```

The existing `close_open` loop already invokes `_close_plan` once per position and increments success only after it returns. Use this complete loop to retain scope/count behavior while sanitizing failure logging:

```python
    for plan in store.all():
        if plan.status not in closeable:
            continue
        try:
            _close_plan(store, plan, "manual_bulk")
            closed += 1
            tickers.append(plan.ticker)
        except Exception as exc:
            log.error("bulk close failed plan=%s type=%s", plan.plan_id, type(exc).__name__)
            failed += 1
```

Do not put the loop inside one outer transaction: each failed position rolls back independently, and later positions still run. Do not enqueue another record in the route after service return. Remove imports that became unused solely because the old mutation body disappeared; preserve all imports used by override preparation and row projections. The explicit 503 response is for failure before a successful commit; deferred journal/snapshot failures are handled by the service and do not generate that response.

- [ ] **Step 4: Verify endpoint contracts and rollback semantics.** Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py` and require zero failures/xfailed with actual DB execution. Run `python scripts/dev/complexity_gate.py`; no changed endpoint/helper may reach 15. This task does not run the full suite. V197-8 will verify the integrated API → queue → Discord path.

- [ ] **Step 5: Commit the route integration.** After normal review and freshness checks, run `git add swingbot/admin/api_v1/trade_commands.py tests/admin/test_api_v1_trade_commands.py` and `git commit -m "fix(v197): fail admin lifecycle actions when durable recording fails"`. The author does not execute these commands. Consumer replacement and final verification still precede any rollout.
