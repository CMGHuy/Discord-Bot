# v189 — Book integrity and partial-trade truth: Implementation Plan, part 4 of 7 — book fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-12:" -A 400 <this file>`.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D2 (manual-close labels), D3.2/D3.3 (admin path in one transaction, network first), D4 A1, A2, A7; `## Corrections from the code brief` 7 and 11 win over earlier sections.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Spec clarifications` (2, 3, 6 apply here), `## Contracts`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.
**Tasks here:** V189-11, V189-12. Part 4 continues in [`_4b-delete-vocabulary.md`](2026-10-23-v189-book-integrity-partial-truth_4b-delete-vocabulary.md) (V189-13, V189-14), split to stay under 1500 lines; the two files share this header's consumed-contract list.
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` (created in V189-1). Every path below is relative to it; every command runs from it.

**What this part consumes from earlier parts** (all on the branch before V189-11 starts):

- V189-2: `metrics.net_outcome(trade) -> tuple[str, str | None]`, the golden fixture and its pytest helpers `load_golden()`, `closed_case(name)` in `tests/analytics/test_golden_partial_trade_metrics.py`.
- V189-5: `swingbot.core.db.engine.transaction(conn=None, *, lock_timeout_ms=None)`, `LockTimeout`, `BOT_LOCK_TIMEOUT_MS`, `ADMIN_LOCK_TIMEOUT_MS`; `Repository.get_for_update(key, *, conn)`.
- V189-6: `PlanStore.lock_for_update(plan_id, *, conn) -> TradePlanV2 | None`; `PlanStore.update(plan, *, conn=None) -> bool` (refuses only a stale write over a terminal plan; the same terminal write is allowed).
- V189-7 (`swingbot/core/tracking/performance.py`): `run_after_commit(callbacks)`, `_with_conn(conn)`, `_lock_for(conn)`, `_locked_open_trade(plan_id, conn)`, `TradeLog._settle_account_balance(t, *, conn=None)` (raises inside a transaction), `TradeLog._db_delete(trade_id, *, conn=None)`, `TradeLog.discard_plan_placeholder(plan_id, *, conn=None) -> bool`, `TradeLog.close_plan_trade(..., conn=None, close_reason=None, after_commit=None)`.
- v187 (merged on `main` before V189-1): `plan_manager.PENDING_CANCEL_EVENTS`, derived `NOTICE_EVENTS`, `instructions._CANCEL_WHY`, `session_expiry`'s per-transition message table, the `cancelled_limit` / `cancelled_gap_through_stop` rows in every vocabulary table. Re-read each with `git grep -n` before editing; line numbers below are `main` @ aedcad03 and may have moved.

Before the first edit in each task, confirm what it consumes exists on the branch: `git grep -n "def lock_for_update\|def run_after_commit\|def net_outcome\|class LockTimeout\|PENDING_CANCEL_EVENTS =" -- swingbot`. A missing name means an earlier task is not merged into the worktree: stop and report it.

# Phase D — Book fixes

### Task V189-11: Manual close in one transaction; the runner leg reaches the plan

**Model:** opus — moves the admin close across a transaction boundary that spans the plan row, the trade row and the account, with lock order, network-before-lock and the D2 label all in one change.

**Spec:** D2 (the manual close is the third caller of `net_outcome`), D3.2 "The admin path follows the same rule", D3.3 "Deadlock rules" (network before the lock), D4 A2; Corrections 4 and 8.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (`import math`; new helpers `_usable_price`, `_manual_close_label`, `_close_manually_onto`; new `TradeLog._open_trade_by_id`, `TradeLog._manual_close_price`; `close_trade_manual` `:1443-1494`)
- Modify: `swingbot/admin/api_v1/trade_commands.py` (imports `:20-41`; `_close_plan` `:143-177`; `close_trade` `:180-203`)
- Modify: `tests/admin/test_close_plan_override_stamp.py` (its fakes learn `lock_for_update`, `conn=`, `after_commit=` and a no-op `transaction`; no assertion changes)
- Create: `tests/tracking/test_manual_close_labels.py`
- Create: `tests/admin/test_close_plan_atomic.py`

**Interfaces:**
- Consumes: `metrics.net_outcome(trade)` (V189-2); `transaction`, `LockTimeout`, `ADMIN_LOCK_TIMEOUT_MS`, `Repository.get_for_update` (V189-5); `PlanStore.lock_for_update`, `PlanStore.update(..., conn=) -> bool` (V189-6); `run_after_commit`, `_lock_for`, `_settle_account_balance(t, *, conn=None)` (V189-7); golden helpers `load_golden`, `closed_case` (V189-2).
- Produces:
  ```python
  # swingbot/core/tracking/performance.py
  def _usable_price(price) -> bool                       # finite and > 0
  def _manual_close_label(t: dict) -> tuple[str, str | None]
  TradeLog._open_trade_by_id(self, trade_id: str, *, conn=None) -> dict | None   # V189-12 reuses it
  TradeLog.close_trade_manual(self, trade_id, reason="manual", *, exit_price=None,
                              conn=None, after_commit: list | None = None) -> bool
      # conn given: no quote fetch, no _LOCK, trade row locked, balance in the caller's tx
      # >= 2 legs after the close: (status, reason) from net_outcome; else ("closed", reason) as today
  # swingbot/admin/api_v1/trade_commands.py
  class PlanChanged(Exception)            # status moved between read and lock; nothing written
  def _close_plan(store, plan, reason="manual") -> None   # raises PlanChanged / LockTimeout
  ```
  `close_trade` maps `PlanChanged` and `LockTimeout` to `409 conflict`; `close_open` already counts any exception as `failed`.

**Decisions written down:**
- One quote serves the override stamp, the trade and the plan's runner leg. When the stamp has no live quote (`bar_close` / `none`), the close settles unpriced on both sides (no runner leg on either), where today `close_trade_manual` made a second live fetch. A second `allow_stale=False` fetch milliseconds after the first rarely differs, and a fetch inside the row lock is what D3.3 forbids. The standalone `close_trade_manual` (legacy-trade close, no `conn`) keeps its fetch exactly as today.
- A plan whose status changed between the admin's read and the row lock (closed by the bot, or TP1 filled) raises `PlanChanged` and writes nothing; the endpoint answers 409 so the admin reloads. Re-deriving the close from the new state inside the lock would need the runner-path stamp (a disk read) inside the lock.
- The runner path is stamped on a closed *copy* before the lock and copied onto the locked plan (`stamp_runner_path` reads the daily cache from disk).
- The A2 leg is appended only to a PARTIAL plan that already holds its TP1 leg. An ACTIVE plan's manual close still writes no leg to the plan, as today (`_step_active`'s stop close does not either).
- `close_trade_manual` with `conn` but no `after_commit` list runs its hooks at once, like `close_plan_trade`; `_close_plan` always passes a list.

- [ ] **Step 1: Write the failing label tests**

Create `tests/tracking/test_manual_close_labels.py`:

```python
"""v189 D2 on the manual-close path, and close_trade_manual's transaction mode.

A manual close that leaves two or more realized legs (TP1 banked, then the
runner closed by hand) is labelled by the sign of its unrounded blended net R:
win above +0.01R, loss below -0.01R, closed/scratch inside, closed/unscored
when the net cannot be computed. A close that leaves one leg or none keeps
today's `closed` exactly. With `conn=` the close joins the caller's
transaction: no quote is fetched, the balance point rolls back with it, and
the journal/snapshot hooks wait for `after_commit`.
"""
import logging
import math

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.db.engine import transaction
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog, run_after_commit
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_golden_partial_trade_metrics import closed_case, load_golden
from tests.store_seed import seed_store

G = load_golden()["trade"]
LABELS = load_golden()["label_table"]


def _golden_open(trade_id="t1", tp1_r=None):
    leg = dict(G["tp1_leg"])
    if tp1_r is not None:
        leg["r"] = tp1_r
    return {"id": trade_id, "ticker": G["ticker"], "status": "open",
            "direction": G["direction"], "entry": G["entry"], "stop_loss": G["stop_loss"],
            "shares": G["shares"], "legs": [leg]}


def _price_for_net(net_r: float) -> float:
    """The runner exit that gives the golden trade a blended net R of `net_r`."""
    tp1 = G["tp1_leg"]["fraction"] * G["tp1_leg"]["r"]
    runner_r = (net_r - tp1) / (1.0 - G["tp1_fraction"])
    return G["entry"] + runner_r * G["risk_per_share"]


@pytest.fixture
def book(monkeypatch):
    """In-memory trades table; no account, journal, snapshot or network."""
    state = {"rows": [_golden_open()], "upserts": []}
    monkeypatch.setattr(TradeLog, "_all", lambda self: state["rows"])
    monkeypatch.setattr(TradeLog, "_db_upsert",
                        staticmethod(lambda trade, conn=None: state["upserts"].append(dict(trade))))
    monkeypatch.setattr(TradeLog, "_settle_account_balance", lambda self, trade: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    return state


@pytest.mark.parametrize("row", LABELS, ids=[str(r["net_r"]) for r in LABELS])
def test_a_scaled_out_manual_close_is_labelled_by_net_r(book, row):
    assert TradeLog().close_trade_manual(
        "t1", reason="manual (admin UI)", exit_price=_price_for_net(row["net_r"])) is True
    trade = book["rows"][0]
    assert len(trade["legs"]) == 2
    assert metrics._blended_r_raw(trade) == pytest.approx(row["net_r"], abs=1e-9)
    assert trade["status"] == row["status"]
    assert trade["close_reason"] == (row["close_reason"] or "manual (admin UI)")


def test_the_golden_manual_close_is_a_win_at_2_5r(book):
    case = closed_case("manual")
    TradeLog().close_trade_manual("t1", exit_price=case["runner_exit"])
    trade = book["rows"][0]
    assert trade["legs"][-1]["r"] == pytest.approx(case["runner_r"])
    assert metrics.r_multiple(trade) == pytest.approx(case["net_r"])
    assert (trade["status"], trade["close_reason"]) == ("win", "manual")


def test_a_single_leg_manual_close_keeps_todays_closed_label(book):
    """An unscaled ACTIVE trade closed by hand at a loss is still `closed`:
    D2 relabels only closes with two or more realized legs."""
    book["rows"] = [{**_golden_open(), "legs": []}]
    TradeLog().close_trade_manual("t1", reason="manual (admin UI)", exit_price=90.0)
    trade = book["rows"][0]
    assert (trade["status"], trade["close_reason"]) == ("closed", "manual (admin UI)")
    assert trade["exit_price"] == pytest.approx(90.0)


def test_a_partial_closed_without_a_price_stays_one_leg_and_closed(book):
    TradeLog().close_trade_manual("t1", reason="manual (admin UI)")
    trade = book["rows"][0]
    assert len(trade["legs"]) == 1
    assert (trade["status"], trade["close_reason"]) == ("closed", "manual (admin UI)")


def test_a_nan_price_is_no_price(book):
    """`if price:` let NaN through (NaN is truthy) and wrote a NaN leg."""
    TradeLog().close_trade_manual("t1", exit_price=float("nan"))
    trade = book["rows"][0]
    assert len(trade["legs"]) == 1
    assert trade.get("exit_price") is None
    assert trade["status"] == "closed"


def test_an_uncomputable_net_is_unscored_with_a_warning(book, caplog):
    book["rows"] = [_golden_open(tp1_r=float("nan"))]
    with caplog.at_level(logging.WARNING):
        TradeLog().close_trade_manual("t1", reason="manual (admin UI)", exit_price=115.0)
    trade = book["rows"][0]
    assert (trade["status"], trade["close_reason"]) == ("closed", "unscored")
    assert any("t1" in record.getMessage() for record in caplog.records)


# --- transaction mode (real database) --------------------------------------------

TRADE_ID = "bbbbbbbbbbbbbbbb"


@pytest.fixture
def db_book(monkeypatch):
    """The golden PARTIAL trade (TP1 banked) open in the database. Returns
    the list the journal and snapshot hooks append to."""
    def no_fetch(*args, **kwargs):
        raise AssertionError("no quote may be fetched inside a transaction")

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", no_fetch)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    seed_store("trades", [{**_trade(TRADE_ID, ticker=G["ticker"]), "entry": G["entry"],
                           "stop_loss": G["stop_loss"], "shares": G["shares"],
                           "legs": [dict(G["tp1_leg"])]}])
    journal = []
    monkeypatch.setattr(perf, "_after_close", lambda trade: journal.append(trade["id"]))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: journal.append("snapshot"))
    return journal


def test_inside_a_transaction_the_hooks_wait_for_commit(db_book):
    hooks = []
    with transaction() as tx:
        assert TradeLog().close_trade_manual(
            TRADE_ID, reason="manual (plan close, admin UI)",
            exit_price=closed_case("manual")["runner_exit"], conn=tx, after_commit=hooks) is True
        assert db_book == []
    assert db_book == []
    run_after_commit(hooks)
    assert db_book == [TRADE_ID, "snapshot"]
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "win"
    assert trade["realized_pnl_amount"] == pytest.approx(closed_case("manual")["realized_pnl_amount"])
    points = account_module.get_balance_history()
    assert [round(p["pnl_amount"], 2) for p in points] == [1250.0]


def test_a_rolled_back_manual_close_leaves_no_trace(db_book):
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            TradeLog().close_trade_manual(TRADE_ID, exit_price=115.0, conn=tx, after_commit=[])
            raise RuntimeError("the plan write after it failed")
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []
    assert db_book == []


def test_no_quote_is_fetched_inside_a_transaction(db_book):
    with transaction() as tx:
        TradeLog().close_trade_manual(TRADE_ID, exit_price=None, conn=tx, after_commit=[])
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert (trade["status"], len(trade["legs"])) == ("closed", 1)


def test_an_already_closed_trade_is_untouched_in_a_transaction(db_book):
    with transaction() as tx:
        TradeLog().close_trade_manual(TRADE_ID, exit_price=115.0, conn=tx, after_commit=[])
    with transaction() as tx:
        assert TradeLog().close_trade_manual(TRADE_ID, exit_price=120.0, conn=tx,
                                             after_commit=[]) is False
    assert TradeLog().get_trade_by_id(TRADE_ID)["exit_price"] == pytest.approx(115.0)
    assert math.isclose(account_module.get_balance_history()[-1]["pnl_amount"], 1250.0)
```

- [ ] **Step 2: Write the failing admin-close tests**

Create `tests/admin/test_close_plan_atomic.py`:

```python
"""v189 D3.2/D3.3 + A2: the admin close of a plan is one transaction.

The plan row is locked first, then the linked trade, then the account (the
plan -> trade -> account order every path uses); the quote and the runner-path
stamp are read before the lock. The plan, the trade, its runner leg on BOTH
stores and the balance point commit together or not at all, and the journal
hook runs only after commit. A plan whose status moved before the lock is a
409 and nothing is written.
"""
import pytest

import swingbot.admin.app  # noqa: F401  (loads the api_v1 package in order)
from swingbot.admin.api_v1 import trade_commands as tc
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import LockTimeout
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.marketdata.data import PriceQuote
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.analytics.test_golden_partial_trade_metrics import closed_case, load_golden
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
PLAN_ID = "55555555-5555-4555-8555-555555555555"
TRADE_ID = "bbbbbbbbbbbbbbbb"
G = load_golden()["trade"]
TP1_AT = "2026-08-05T15:00:00+00:00"
MANUAL = closed_case("manual")


def _tp1_leg():
    return {**G["tp1_leg"], "closed_at": TP1_AT}


def _golden_partial_plan():
    return {**_plan(PLAN_ID, ticker=G["ticker"], status="PARTIAL"),
            "entry_price": G["entry"], "stop_loss": G["stop_loss"], "tp1": G["tp1"],
            "tp2": G["tp2"], "tp1_fraction": G["tp1_fraction"], "legs_realized": [_tp1_leg()],
            "status_history": [
                {"status": "ACTIVE", "reason": "stop_entry_fill", "at": "2026-08-04T14:00:00+00:00"},
                {"status": "PARTIAL", "reason": "tp1_partial", "at": TP1_AT}]}


def _golden_open_trade():
    return {**_trade(TRADE_ID, plan_id=PLAN_ID, ticker=G["ticker"]),
            "entry": G["entry"], "stop_loss": G["stop_loss"], "take_profit": G["tp1"],
            "target2": G["tp2"], "shares": G["shares"],
            "position_value": G["shares"] * G["entry"], "legs": [_tp1_leg()]}


@pytest.fixture
def golden(admin_app, monkeypatch):
    """The golden PARTIAL plan and its open trade; the live quote is the
    manual case's runner exit (115) unless a test sets golden["price"]."""
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    seed_store("plans", [_golden_partial_plan()])
    seed_store("trades", [_golden_open_trade()])
    state = {"price": MANUAL["runner_exit"], "journal": []}

    def detail(*args, **kwargs):
        return None if state["price"] is None else PriceQuote(state["price"], False)

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price_detail", detail)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: state["journal"].append(trade["id"]))
    return state


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _legs(record):
    return [(leg["fraction"], leg["exit_price"], round(leg["r"], 6), leg["reason"])
            for leg in record]


def test_a_manual_partial_close_writes_the_runner_leg_to_both_stores(golden, logged_in):
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(PLAN_ID)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert plan.status == "CLOSED"
    runner = plan.legs_realized[-1]
    assert (runner["fraction"], runner["exit_price"], runner["reason"]) == (0.5, 115.0, "manual")
    assert runner["r"] == pytest.approx(MANUAL["runner_r"])
    assert runner["closed_at"] == plan.status_history[-1]["at"]
    assert _legs(plan.legs_realized) == _legs(trade["legs"])


def test_the_trade_is_labelled_and_settled_with_its_balance_point(golden, logged_in):
    logged_in.post(f"/api/v1/trades/{PLAN_ID}/close")
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == MANUAL["status"]
    assert trade["close_reason"] == "manual (plan close, admin UI)"
    assert trade["realized_pnl_amount"] == pytest.approx(MANUAL["realized_pnl_amount"])
    assert [p["pnl_amount"] for p in account_module.get_balance_history()] == [1250.0]
    assert golden["journal"] == [TRADE_ID], "the journal hook ran once, after commit"


def test_a_failed_plan_write_rolls_the_trade_close_back(golden, monkeypatch):
    def refuse(self, plan, *, conn=None):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(PlanStore, "update", refuse)
    store = PlanStore()
    with pytest.raises(RuntimeError):
        tc._close_plan(store, store.get(PLAN_ID))
    assert PlanStore().get(PLAN_ID).status == "PARTIAL"
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []
    assert golden["journal"] == [], "no hook runs for a rolled-back close"


def test_a_failed_balance_write_leaves_the_plan_open(golden, monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(perf.account_module, "apply_realized_pnl", refuse)
    store = PlanStore()
    with pytest.raises(RuntimeError):
        tc._close_plan(store, store.get(PLAN_ID))
    plan = PlanStore().get(PLAN_ID)
    assert plan.status == "PARTIAL" and len(plan.legs_realized) == 1
    assert TradeLog().get_trade_by_id(TRADE_ID)["status"] == "open"


def test_a_plan_closed_before_the_lock_is_a_409_and_nothing_changes(golden, logged_in,
                                                                      monkeypatch):
    """The bot closes the plan while the admin's stamp quote is in flight."""
    def stamp_while_the_bot_closes(ticker):
        PlanRepository().patch(PLAN_ID, {"status": "CLOSED"})
        return None

    monkeypatch.setattr(tc, "_override_stamp", stamp_while_the_bot_closes)
    assert_error(logged_in.post(f"/api/v1/trades/{PLAN_ID}/close"), "conflict", 409)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []


def test_a_lock_timeout_is_a_409(golden, logged_in, monkeypatch):
    def busy(store, plan, reason="manual"):
        raise LockTimeout("plan row held by the bot")

    monkeypatch.setattr(tc, "_close_plan", busy)
    assert_error(logged_in.post(f"/api/v1/trades/{PLAN_ID}/close"), "conflict", 409)


def test_no_quote_closes_both_stores_unpriced(golden, logged_in):
    golden["price"] = None
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(PLAN_ID)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert plan.status == "CLOSED" and len(plan.legs_realized) == 1
    assert (trade["status"], len(trade["legs"])) == ("closed", 1)
```

If `LockTimeout` takes no message argument in V189-5's definition, construct it bare (`LockTimeout()`); check with `git grep -n "class LockTimeout" -A 4 -- swingbot/core/db/engine.py`.

- [ ] **Step 3: Run both new files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_manual_close_labels.py`
Expected: FAIL — the label-table rows all read `closed`; `test_a_nan_price_is_no_price` finds a second (NaN) leg; the transaction-mode tests fail with `TypeError: close_trade_manual() got an unexpected keyword argument 'conn'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_close_plan_atomic.py`
Expected: FAIL — the plan keeps one leg after the close; the rollback tests find the trade closed and a balance point written; the 409 tests get 200 or an uncaught `LockTimeout`.

- [ ] **Step 4: `performance.py` — helpers**

In `swingbot/core/tracking/performance.py` add `import math` to the standard-library imports (`:18-22`). Directly after `_apply_exit_price` (`:520-538`) add:

```python
def _usable_price(price) -> bool:
    """A price a close may settle at: finite and positive. A NaN quote is
    truthy, so `if price:` let it write a NaN leg (v189 D4)."""
    return price is not None and math.isfinite(price) and price > 0


def _manual_close_label(t: dict) -> tuple[str, str | None]:
    """(status, close_reason override) of a manual close (v189 D2).

    Two or more realized legs: the sign of the unrounded net R
    (`metrics.net_outcome`) -- win/loss keep the caller's reason, a scratch
    or an uncomputable net replaces it with `scratch` / `unscored`. One leg or
    none: today's `closed`, reason untouched, so single-leg labels never move.
    Imported lazily: the analytics package imports this module."""
    if len(t.get("legs") or []) < 2:
        return "closed", None
    from swingbot.core.analytics import metrics
    return metrics.net_outcome(t)


def _close_manually_onto(t: dict, price: float | None, reason: str) -> None:
    """Apply a manual close to an open trade dict in place (no I/O): the
    still-open remainder realized as one more leg at a usable `price`, then
    the label."""
    if _usable_price(price):
        _apply_exit_price(t, price, reason="manual")
    status, labelled = _manual_close_label(t)
    t["status"] = status
    t["closed_at"] = datetime.now(timezone.utc).isoformat()
    t["close_reason"] = labelled or reason
```

- [ ] **Step 5: `performance.py` — two lookups and `close_trade_manual`**

Add these two methods to `TradeLog`, right after V189-7's `_open_trade_for_plan`:

```python
    def _open_trade_by_id(self, trade_id: str, *, conn=None) -> dict | None:
        """The open trade `trade_id`. Standalone: from `self._all()` as before.
        Inside a transaction: read and row-locked on `conn` (lock order plan ->
        trade -> account), in TradeLog's JSON shape. None when not open."""
        if conn is None:
            return next((t for t in self._all()
                         if t["id"] == trade_id and t["status"] == "open"), None)
        from swingbot.core.db.repositories.trades import OPEN_STATUS, trades_repo
        row = trades_repo().get_for_update(trade_id, conn=conn)
        return _json_record(row) if row and row.get("status") == OPEN_STATUS else None

    def _manual_close_price(self, trade_id: str, exit_price: float | None) -> float | None:
        """The settlement price of a standalone manual close: the caller's, else
        one live fetch for the open trade's ticker, made OUTSIDE any lock."""
        if exit_price is not None:
            return exit_price
        trade = self._open_trade_by_id(trade_id)
        return _manual_close_quote(trade["ticker"]) if trade else None
```

Replace `close_trade_manual` (`:1443-1494`) with:

```python
    def close_trade_manual(self, trade_id: str, reason: str = "manual", *,
                           exit_price: float | None = None, conn=None,
                           after_commit: list | None = None) -> bool:
        """
        Marks an open trade as closed, fetching the live market price to
        stand in as its exit (used by the admin UI's "Close" button -- a
        human override of TIMING, not of price: the position really did
        exit at whatever the market was doing at that moment, so it
        settles like any other close -- account balance, pnl_pct,
        r_multiple -- rather than leaving all three permanently null. A
        PARTIAL trade's still-open remainder (whatever `legs` hasn't
        already banked) is realized as one more leg at that price, on top
        of TP1. Falls back to the old no-exit-price close if the price
        fetch fails or the ticker has no live quote -- a network hiccup
        must never block the close itself.

        `exit_price` (v173): the live quote the caller already fetched for
        the plan's override stamp. Given, it is the settlement price and no
        second fetch happens, so the stamp and the trade carry one price.
        None keeps the fetch above.

        v189 D2: a close that leaves two or more realized legs is labelled by
        the sign of its net R (`metrics.net_outcome`); one leg or none stays
        `closed`, as before.

        Concurrency (v189 D3.3). Standalone (no `conn`), the read-modify-write
        runs under the process-local `_LOCK`, the price fetch outside it --
        that guards this process only. Cross-process protection comes from
        the database: with `conn` the trade row is locked (`SELECT ... FOR
        UPDATE`) inside the caller's transaction, which has already locked
        the plan row, so a bot close of the same position waits or is
        refused. With `conn` nothing is fetched (no network inside a row
        lock), the balance point is written in the same transaction (a
        failure raises and rolls the close back), and the journal / snapshot
        hooks go to `after_commit` when given.
        Returns True if a matching OPEN trade was found and closed.
        """
        price = exit_price if conn is not None else self._manual_close_price(trade_id, exit_price)
        with _lock_for(conn):
            t = self._open_trade_by_id(trade_id, conn=conn)
            if t is None:
                return False
            _close_manually_onto(t, price, reason)
            if conn is None:
                self._settle_account_balance(t)
            else:
                self._settle_account_balance(t, conn=conn)
            closed_trade = dict(t)
            self._db_upsert(t, conn=conn)
        hooks = [lambda: _after_close(closed_trade), lambda: _refresh_snapshot_safely()]
        if after_commit is None:
            run_after_commit(hooks)
        else:
            after_commit.extend(hooks)
        return True
```

(The standalone path still mutates the dict `_all()` returned and upserts it, so `tests/tracking/test_close_trade_manual_exit_price.py`'s doubles keep working; the `if conn is None` split keeps its `lambda self, trade: None` double for `_settle_account_balance` valid. `_manual_close_price` reads the open trade without `_LOCK`; the old code took the lock only for that read, and the locked re-read below re-validates the status.)

- [ ] **Step 6: `trade_commands.py` — imports and the helpers**

In `swingbot/admin/api_v1/trade_commands.py` change the import block (`:20-41`) to:

```python
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, LockTimeout, transaction
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.tracking.performance import TradeLog, run_after_commit
from swingbot.core.planning.plan_engine import (PlanStatus, plan_from_dict, plan_to_dict,
                                                record_transition)
from swingbot.core.planning.plan_store import PlanStore

from . import api_v1, error
from .auth import require_auth
from .trades import (
    _attach_current_prices,
    _looks_like_a_plan_id,
    _noted_ids,
    _row_from_plan,
    _row_from_trade,
)
```

(Keep any import v187 added to this block; the changes are `import math`, the `db.engine` line, `run_after_commit` and the two plan-dict helpers.)

Directly above `_close_plan` (`:143`) add:

```python
class PlanChanged(Exception):
    """The plan's status moved between the admin's read and the row lock (the
    bot closed it, or TP1 filled). Nothing was written; the caller reloads."""


def _usable(price) -> bool:
    return price is not None and math.isfinite(price) and price > 0


def _runner_leg(plan, price, at: str) -> dict | None:
    """v189 A2: a PARTIAL plan's still-open remainder realized at `price`, in
    the shape `_close_runner` writes. None for an ACTIVE plan, a PARTIAL with
    no banked leg on record, a zero-risk plan or no usable price (the trade
    side then closes unpriced as well, so the two stores still agree)."""
    if plan.status != PlanStatus.PARTIAL or not plan.legs_realized or not _usable(price):
        return None
    remaining = round(1.0 - sum(leg.get("fraction", 0) for leg in plan.legs_realized), 6)
    risk = abs(plan.entry_price - plan.stop_loss) if plan.entry_price is not None else 0.0
    if remaining <= 0 or not risk:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    return {"fraction": remaining, "exit_price": price,
            "r": (price - plan.entry_price) * sign / risk, "reason": "manual", "closed_at": at}


def _close_plan_onto(plan, price, reason: str, stamp, at: str) -> None:
    """The close on an in-memory plan, no I/O: the A2 runner leg, then the
    CLOSED transition carrying the v173 override stamp. `at` is explicit --
    the lifecycle strip's "today" counts read status_history[-1]["at"]."""
    leg = _runner_leg(plan, price, at)
    if leg is not None:
        plan.legs_realized.append(leg)
    record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at, extra={"override": stamp})


def _runner_path_for(plan, price, reason: str, stamp, at: str) -> tuple[bool, dict | None]:
    """(stamped, path). v142: a manual runner close stamps its path; that
    reads the daily cache from disk, so it runs on a closed COPY before any
    row lock. An ACTIVE plan has no runner: (False, None). Never raises."""
    if plan.status != PlanStatus.PARTIAL:
        return False, None
    preview = plan_from_dict(plan_to_dict(plan))
    _close_plan_onto(preview, price, reason, stamp, at)
    return True, rp.stamp_runner_path(preview, rp.cached_daily_bars, source="live")


def _close_linked_trade(tl: TradeLog, linked: dict | None, price, conn, hooks: list) -> None:
    """Settle the plan's open trade inside the plan's transaction (trade row
    locked after the plan row), at the stamp's quote; hooks wait for commit."""
    if linked and linked.get("status") == _OPEN_LEGACY:
        tl.close_trade_manual(linked["id"], reason="manual (plan close, admin UI)",
                              exit_price=price, conn=conn, after_commit=hooks)
```

- [ ] **Step 7: `trade_commands.py` — `_close_plan` and `close_trade`**

Replace `_close_plan` (`:143-177`) with:

```python
def _close_plan(store: PlanStore, plan, reason: str = "manual") -> None:
    """Close one ACTIVE/PARTIAL plan: settle its linked legacy trade, record
    the transition, and queue the bot's notification.

    Extracted from close_trade so the bulk endpoint runs exactly this and
    cannot drift from the single-position path. The caller checks status.
    `reason` is "manual" for a single close and "manual_bulk" for the bulk
    endpoint (v173): a bulk clear is not a decision, and the override report
    must be able to tell the two apart.

    v189 D3: one transaction. The quote (override stamp) and the runner-path
    stamp are read first, with no lock held. Then the plan row is locked,
    re-checked (a status that moved raises PlanChanged), closed with its A2
    runner leg, the linked trade closed at the same quote with its balance
    point, and the plan written -- all of it commits or none of it does. The
    journal and snapshot hooks run after commit. One quote serves the stamp,
    the trade and the plan leg; without a live quote both close unpriced.
    """
    stamp = _override_stamp(plan.ticker)
    price = stamp["exit_price"] if stamp and stamp["price_source"] == "quote" else None
    at = datetime.now(timezone.utc).isoformat()
    stamped, runner_path = _runner_path_for(plan, price, reason, stamp, at)
    tl = TradeLog()
    linked = _linked_trade(tl, plan.plan_id)
    hooks: list = []
    with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as tx:
        current = store.lock_for_update(plan.plan_id, conn=tx)
        if current is None or current.status != plan.status:
            raise PlanChanged(plan.plan_id)
        _close_plan_onto(current, price, reason, stamp, at)
        if stamped:
            current.runner_path = runner_path
        _close_linked_trade(tl, linked, price, tx, hooks)
        if not store.update(current, conn=tx):
            raise PlanChanged(plan.plan_id)
    run_after_commit(hooks)
    _queue_notify({"kind": "plan_transition", "plan_id": current.plan_id,
                   "ticker": current.ticker, "status": current.status})
```

In `close_trade`, replace the two lines `_close_plan(store, plan)` / `return _plan_row(trade_id)` (`:192-193`) with:

```python
        try:
            _close_plan(store, plan)
        except (PlanChanged, LockTimeout):
            return error("conflict",
                         "This position changed or is being updated by the bot; "
                         "reload and try again.", 409)
        return _plan_row(trade_id)
```

`close_open` is unchanged: its per-plan `except Exception` already counts a `PlanChanged` or `LockTimeout` as `failed`.

- [ ] **Step 8: Teach the v173 stamp test's fakes the transactional seams**

`tests/admin/test_close_plan_override_stamp.py` fakes the store, the trade log and every network seam, and must stay database-free. Three edits, no assertion changes:

(a) Add `from contextlib import nullcontext` to its imports.

(b) Replace `FakeStore.update` and add `lock_for_update` (it hands back the same object, so the in-place assertions on `plan.status_history` still read the closed plan):

```python
    def lock_for_update(self, plan_id, *, conn):
        return self.plans.get(plan_id)

    def update(self, plan, *, conn=None):
        self.updated.append(plan.plan_id)
        return True
```

(c) Change `FakeTradeLog.close_trade_manual`'s signature to:

```python
    def close_trade_manual(self, trade_id, reason="manual", *, exit_price=None,
                           conn=None, after_commit=None):
```

and in the `env` fixture, next to `monkeypatch.setattr(tc, "TradeLog", FakeTradeLog)`, add:

```python
    monkeypatch.setattr(tc, "transaction", lambda *args, **kwargs: nullcontext(None))
```

- [ ] **Step 9: Run the new and the touched tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_manual_close_labels.py`
Expected: PASS (14 tests: 5 label rows, 5 in-memory cases, 4 transaction-mode cases).

Run: `python scripts/dev/testrun.py file tests/admin/test_close_plan_atomic.py`
Expected: PASS (7 tests).

Run each (all must PASS):
`python scripts/dev/testrun.py file tests/admin/test_close_plan_override_stamp.py`
`python scripts/dev/testrun.py file tests/admin/test_trade_commands_runner_path.py`
`python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py`
`python scripts/dev/testrun.py file tests/tracking/test_close_trade_manual_exit_price.py`
`python scripts/dev/testrun.py file tests/tracking/test_one_trade_per_ticker.py`

A failure asserting the linked trade settled at a *second* live fetch after the stamp found no quote is the one deliberate change (decision 1): report the test name to the controller rather than adding the fetch back.

- [ ] **Step 10: Everything the diff reaches, and the complexity gate**

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `close_trade_manual` drops from 11 to about 5; `_runner_leg` about 8; `_close_plan` about 5; every other new function at most 4.

- [ ] **Step 11: Commit**

Two scoped commits (the TradeLog close and the admin path are separate concerns; both files are edited and Steps 9-10 are green before the first):

```bash
git add swingbot/core/tracking/performance.py tests/tracking/test_manual_close_labels.py
git commit -m "feat(tracking): manual close labels scaled-out trades by net R and can join the caller's transaction (v189 V189-11)"
git add swingbot/admin/api_v1/trade_commands.py tests/admin/test_close_plan_atomic.py tests/admin/test_close_plan_override_stamp.py
git commit -m "fix(admin): a plan close is one transaction, network first, and writes the runner leg to the plan (v189 V189-11)"
```

### Task V189-12: Plan links; a reversal never books a never-filled placeholder

**Model:** opus — a new module every out-of-manager close goes through, a locked fill check that races the poll, and an extraction out of `_sync_run_scan` (complexity 96) that must not change any other branch.

**Spec:** D4 A1 and "A1 race"; D3.2 (the reversal's `_close_linked_plan_safely` joins the transaction); Corrections 7 and 8 (the reversal block moves into a named helper); index clarification 6.

**Files:**
- Create: `swingbot/core/tracking/plan_links.py`
- Modify: `swingbot/core/tracking/performance.py` (`_close_linked_plan_safely` `:118-140`; `close_trade_reversed` `:1308-1348`)
- Modify: `swingbot/core/scanning/scan_run.py` (imports `:2-55`; new `_usable_reversal_price` and `_settle_reversal` above `_sync_run_scan` `:448`; the reversal block `:931-941`)
- Create: `tests/tracking/test_plan_links.py`
- Create: `tests/scanning/test_reversal_placeholder.py`

**Interfaces:**
- Consumes: `transaction`, `LockTimeout`, `BOT_LOCK_TIMEOUT_MS`, `ADMIN_LOCK_TIMEOUT_MS` (V189-5); `PlanStore.lock_for_update`, `PlanStore.update(..., conn=)` (V189-6); `TradeLog.discard_plan_placeholder(plan_id, *, conn=None)`, `TradeLog._settle_account_balance(t, *, conn=None)`, `run_after_commit` (V189-7); `TradeLog._open_trade_by_id(trade_id, *, conn=None)` (V189-11).
- Produces:
  ```python
  # swingbot/core/tracking/plan_links.py
  LINKED_TERMINAL: dict                  # {PENDING: CANCELLED, ACTIVE: CLOSED, PARTIAL: CLOSED}
  TRADE_DELETED_EVENT = "cancelled_trade_deleted"
  @dataclass(frozen=True) class EndedPlan: plan_id: str; ticker: str; status_before: str; status_after: str
  @dataclass(frozen=True) class DeleteResult: removed: int; ended: tuple[EndedPlan, ...] = ()   # __bool__: removed > 0
  def end_linked_plan(plan_id: str, reason: str, *, conn, notice: bool = False) -> EndedPlan | None
  def cancel_unfilled_in(plan_id: str, reason: str, *, conn) -> bool       # the locked check + cancel, caller's tx
  def cancel_if_unfilled(plan_id: str, reason: str) -> bool               # own tx, BOT_LOCK_TIMEOUT_MS
  # swingbot/core/tracking/performance.py
  def _close_linked_plan_safely(plan_id: str, reason: str, *, conn=None) -> None   # conn: raises; else own tx, swallows
  TradeLog.close_trade_reversed(self, trade_id: str, exit_price: float) -> dict | None
      # one tx (BOT_LOCK_TIMEOUT_MS): plan PENDING -> cancel + discard, None; else close, balance, plan CLOSED
  # swingbot/core/scanning/scan_run.py
  def _settle_reversal(trade_log, existing_trade: dict, live_price: float | None) -> dict | None
  ```
  `end_linked_plan(..., notice=True)` writes `pending_notice`: `{"transition": "cancelled_trade_deleted", "detail": {"reason": reason, "live_price": None}, "at": <iso>}` when it cancels, `{"transition": "closed", "detail": {"reason": reason}, "at": <iso>}` when it closes. V189-14 is its only `notice=True` caller.

**Decisions written down:**
- "Has this plan filled?" is "is the plan still PENDING under its row lock". v187's `_fill_pending` and V189-8's `_persist_fill` move a plan to ACTIVE and write its fill in one transaction, so a PENDING plan has no fill and an ACTIVE one has.
- A placeholder reversal returns the placeholder record with `status: "discarded"` (truthy), so the scan counts the ticker as freed and lets the inverse through, exactly as after a real reversal. It needs no live price.
- `close_trade_reversed` also refuses to book a placeholder on its own (cancels and returns None), so no caller can book one; the scan reaches it only for a filled plan.
- The reversal path is a bot path: its transactions use `BOT_LOCK_TIMEOUT_MS`, and a `LockTimeout` defers the reversal to the next scan (logged at INFO) instead of failing the scan.
- `_close_linked_plan_safely` with `conn` raises instead of swallowing: a swallowed SQL error inside a Postgres transaction leaves it aborted, and a half-ended position is the defect being fixed. Without `conn` (no caller after this task) it keeps its never-raise contract in its own short transaction.
- A reversal of a filled plan keeps today's label (`closed` / `reversed`): D2's callers are the runner, time-exit and manual closes only.

- [ ] **Step 1: Write the failing plan-links tests**

Create `tests/tracking/test_plan_links.py`:

```python
"""v189 D4 A1/A7: tracking/plan_links ends a trade's v2 plan in the trade's
own transaction -- PENDING cancels, ACTIVE/PARTIAL close -- and checks
"never filled" under the plan row lock."""
import logging

import pytest

from swingbot.core.db.engine import transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.tracking.plan_links import DeleteResult, EndedPlan
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store


@pytest.fixture(autouse=True)
def _account(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})


def _partial():
    plan = _active()
    plan.legs_realized.append({"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"})
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    return plan


_PLANS = {"PENDING": lambda: _plan(entry_type="stop_entry"), "ACTIVE": _active,
          "PARTIAL": _partial}
_ENDS = {"PENDING": "CANCELLED", "ACTIVE": "CLOSED", "PARTIAL": "CLOSED"}


def _log(tl, plan):
    return tl.log_trade(ticker=plan.ticker, strategy="RSI", horizon_key="2w",
                        direction="bullish", confidence_level=3, confidence_label="Medium",
                        entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)


def _end(plan_id, reason="reversed", notice=False):
    with transaction() as tx:
        return plan_links.end_linked_plan(plan_id, reason, conn=tx, notice=notice)


@pytest.mark.parametrize("status", list(_PLANS))
def test_end_linked_plan_maps_each_open_status(status):
    PlanStore().add(_PLANS[status]())
    ended = _end("p1")
    assert ended == EndedPlan("p1", "AAPL", status, _ENDS[status])
    stored = PlanStore().get("p1")
    assert stored.status == _ENDS[status]
    assert stored.status_history[-1]["reason"] == "reversed"
    assert stored.status_history[-1]["at"]
    assert stored.pending_notice is None


def _terminal(status):
    if status == "CLOSED":
        plan = _active()
        record_transition(plan, PlanStatus.CLOSED, reason="loss", at="t2")
        return plan
    plan = _plan(entry_type="stop_entry")
    record_transition(plan, PlanStatus.CANCELLED, reason="expired", at="t2")
    return plan


@pytest.mark.parametrize("status", ["CLOSED", "CANCELLED"])
def test_a_terminal_plan_is_left_alone(status):
    PlanStore().add(_terminal(status))
    before = PlanStore().get("p1").status_history
    assert _end("p1") is None
    assert PlanStore().get("p1").status_history == before


def test_a_missing_plan_is_none():
    assert _end("nope") is None


def test_notice_on_a_cancel_queues_the_trade_deleted_event():
    PlanStore().add(_PLANS["PENDING"]())
    _end("p1", reason="trade_deleted", notice=True)
    notice = PlanStore().get("p1").pending_notice
    assert notice["transition"] == plan_links.TRADE_DELETED_EVENT == "cancelled_trade_deleted"
    assert notice["detail"] == {"reason": "trade_deleted", "live_price": None}
    assert notice["at"]


@pytest.mark.parametrize("status", ["ACTIVE", "PARTIAL"])
def test_notice_on_a_close_queues_a_closed_event_without_a_price(status):
    PlanStore().add(_PLANS[status]())
    _end("p1", reason="trade_deleted", notice=True)
    notice = PlanStore().get("p1").pending_notice
    assert (notice["transition"], notice["detail"]) == ("closed", {"reason": "trade_deleted"})


def test_ending_a_plan_rolls_back_with_its_transaction():
    PlanStore().add(_active())
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            plan_links.end_linked_plan("p1", "reversed", conn=tx)
            raise RuntimeError("the trade write after it failed")
    assert PlanStore().get("p1").status == "ACTIVE"


def test_cancel_if_unfilled_cancels_a_pending_plan_and_drops_its_placeholder():
    tl = TradeLog()
    PlanStore().add(_PLANS["PENDING"]())
    _log(tl, PlanStore().get("p1"))
    assert plan_links.cancel_if_unfilled("p1", "reversed") is True
    assert PlanStore().get("p1").status == "CANCELLED"
    assert tl.trade_for_plan("p1") is None


def test_cancel_if_unfilled_leaves_a_filled_plan_and_its_trade_alone():
    tl = TradeLog()
    PlanStore().add(_active())
    _log(tl, PlanStore().get("p1"))
    assert plan_links.cancel_if_unfilled("p1", "reversed") is False
    assert PlanStore().get("p1").status == "ACTIVE"
    assert tl.trade_for_plan("p1")["status"] == "open"


def test_cancel_if_unfilled_on_a_missing_plan_is_false():
    assert plan_links.cancel_if_unfilled("nope", "reversed") is False


def test_delete_result_is_truthy_only_when_something_was_removed():
    assert not DeleteResult(removed=0)
    assert DeleteResult(removed=2)
    assert DeleteResult(removed=1).ended == ()


def test_close_linked_plan_safely_raises_inside_a_transaction(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    PlanStore().add(_active())
    monkeypatch.setattr(plan_links, "end_linked_plan", boom)
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            perf._close_linked_plan_safely("p1", "reversed", conn=tx)


def test_close_linked_plan_safely_alone_never_raises(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(plan_links, "end_linked_plan", boom)
    with caplog.at_level(logging.WARNING):
        perf._close_linked_plan_safely("p1", "reversed")
    assert "could not close plan p1" in caplog.text
```

- [ ] **Step 2: Write the failing reversal tests**

Create `tests/scanning/test_reversal_placeholder.py`:

```python
"""v189 A1: a reversal never books P&L on a never-filled placeholder.

A stop-entry plan's trade row is logged while the plan is still PENDING. When
an opposite setup reverses the ticker before the order fills, there is no
position to close: the plan is cancelled and the placeholder discarded, with
no P&L and no balance point. The "never filled" check runs under the plan row
lock, so a fill the poll records meanwhile turns it into the real position it
is, closed and settled with its plan in one transaction.
"""
import inspect

import pytest

from swingbot.core.db.engine import LockTimeout
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import scan_run
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store


@pytest.fixture
def tlog(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _pending():
    return _plan(entry_type="stop_entry")          # PENDING, plan_id "p1"


def _filled():
    plan = _plan(entry_type="stop_entry", entry_price=100.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill",
                      at="2026-10-20T14:00:00+00:00")
    return plan


def _open_trade(tl, plan) -> dict:
    """The trade the scan reads with open_trade_for_ticker before reversing."""
    PlanStore().add(plan)
    tid = tl.log_trade(ticker=plan.ticker, strategy="RSI", horizon_key="2w",
                       direction="bullish", confidence_level=3, confidence_label="Medium",
                       entry=100.0, stop_loss=95.0, take_profit=110.0, plan_id=plan.plan_id)
    return tl.get_trade_by_id(tid)


@pytest.mark.parametrize("live_price", [97.5, None])
def test_a_reversal_against_a_placeholder_books_nothing_and_cancels_the_plan(tlog, live_price):
    existing = _open_trade(tlog, _pending())
    settled = scan_run._settle_reversal(tlog, existing, live_price)
    assert settled is not None and settled["status"] == "discarded"
    plan = PlanStore().get("p1")
    assert plan.status == "CANCELLED"
    assert plan.status_history[-1]["reason"] == "reversed"
    assert tlog.trade_for_plan("p1") is None
    assert tlog.get_trades(status=None, limit=None) == []
    assert account_module.get_balance_history() == []


def test_a_plan_that_filled_meanwhile_is_reversed_as_the_real_position(tlog):
    """`existing` was read while the plan was PENDING; the poll fills it before
    the reversal takes the lock. The locked check sees ACTIVE and books it."""
    existing = _open_trade(tlog, _pending())
    plan = PlanStore().get("p1")
    plan.entry_price = 100.0
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill",
                      at="2026-10-20T14:00:00+00:00")
    PlanStore().update(plan)
    tlog.record_plan_fill("p1", 100.0)

    settled = scan_run._settle_reversal(tlog, existing, 97.5)
    assert (settled["status"], settled["close_reason"]) == ("closed", "reversed")
    assert settled["realized_pnl_amount"] < 0
    assert PlanStore().get("p1").status == "CLOSED"
    assert len(account_module.get_balance_history()) == 1


@pytest.mark.parametrize("live_price", [None, 0.0, float("nan")])
def test_no_usable_price_settles_nothing_for_a_real_position(tlog, live_price):
    existing = _open_trade(tlog, _filled())
    assert scan_run._settle_reversal(tlog, existing, live_price) is None
    assert tlog.trade_for_plan("p1")["status"] == "open"
    assert PlanStore().get("p1").status == "ACTIVE"


def test_a_locked_plan_defers_the_reversal(tlog, monkeypatch):
    existing = _open_trade(tlog, _pending())

    def locked(plan_id, reason):
        raise LockTimeout("plan row held by the poll")

    monkeypatch.setattr(plan_links, "cancel_if_unfilled", locked)
    assert scan_run._settle_reversal(tlog, existing, 97.5) is None
    assert PlanStore().get("p1").status == "PENDING"
    assert tlog.trade_for_plan("p1")["status"] == "open"


def test_close_trade_reversed_never_books_a_placeholder(tlog):
    existing = _open_trade(tlog, _pending())
    assert tlog.close_trade_reversed(existing["id"], 97.5) is None
    assert PlanStore().get("p1").status == "CANCELLED"
    assert tlog.trade_for_plan("p1") is None
    assert account_module.get_balance_history() == []


def test_the_reversal_and_its_plan_close_commit_together(tlog, monkeypatch):
    existing = _open_trade(tlog, _filled())

    def refuse(*args, **kwargs):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(plan_links, "end_linked_plan", refuse)
    with pytest.raises(RuntimeError):
        tlog.close_trade_reversed(existing["id"], 97.5)
    assert tlog.trade_for_plan("p1")["status"] == "open"
    assert PlanStore().get("p1").status == "ACTIVE"
    assert account_module.get_balance_history() == []


def test_the_scan_loop_settles_reversals_through_the_helper():
    source = inspect.getsource(scan_run._sync_run_scan)
    assert "_settle_reversal(trade_log, existing_trade, live_price)" in source
    assert "close_trade_reversed(" not in source
```

- [ ] **Step 3: Run both new files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_plan_links.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.tracking.plan_links'`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_reversal_placeholder.py`
Expected: FAIL — the same import error (and, once plan_links exists, `AttributeError: module 'swingbot.core.scanning.scan_run' has no attribute '_settle_reversal'`).

- [ ] **Step 4: Create `plan_links.py`**

Create `swingbot/core/tracking/plan_links.py`:

```python
"""Ending a trade's v2 plan in the trade's own transaction (v189 D4 A1, A7).

A paper trade row and its v2 plan are two halves of one position. A path that
ends the trade OUTSIDE the plan manager -- a reversal, a delete -- ends the
plan in the same database transaction, through here:

* `end_linked_plan` maps PENDING -> CANCELLED and ACTIVE/PARTIAL -> CLOSED (the
  mapping `_close_linked_plan_safely` has always used), records the reason and
  the time, and on request queues the plan's durable `pending_notice`, which
  `PlanManager.resend_notices` re-emits to the execution feed and the follow
  channel until it is acknowledged.
* `cancel_unfilled_in` / `cancel_if_unfilled` are the reversal's "has this plan
  filled?" check and cancel, under the plan row lock, so a fill the poll
  records meanwhile is seen and the trade is treated as the position it is.

Lock order is the plan row first (`PlanStore.lock_for_update`), then the trade
row, then the account. No process-local lock is taken here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, transaction
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore

#: open plan status -> the terminal status its plan takes when the trade ends
#: outside the plan manager. A PENDING plan never filled, so it can only cancel.
LINKED_TERMINAL = {PlanStatus.PENDING: PlanStatus.CANCELLED,
                   PlanStatus.ACTIVE: PlanStatus.CLOSED,
                   PlanStatus.PARTIAL: PlanStatus.CLOSED}

#: the cancel event a PENDING plan announces when its placeholder is deleted.
TRADE_DELETED_EVENT = "cancelled_trade_deleted"


@dataclass(frozen=True)
class EndedPlan:
    """One plan a trade-side path ended."""
    plan_id: str
    ticker: str
    status_before: str
    status_after: str


@dataclass(frozen=True)
class DeleteResult:
    """What a delete removed: the trade rows, and every plan it ended."""
    removed: int
    ended: tuple[EndedPlan, ...] = ()

    def __bool__(self) -> bool:
        return self.removed > 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notice(terminal: str, reason: str, at: str) -> dict:
    """The pending_notice a delete leaves on its plan (index clarification 2).
    A cancelled plan announces `cancelled_trade_deleted`; a closed one a
    `closed` with no exit price -- the trade was deleted, nothing was exited."""
    if terminal == PlanStatus.CANCELLED:
        return {"transition": TRADE_DELETED_EVENT,
                "detail": {"reason": reason, "live_price": None}, "at": at}
    return {"transition": "closed", "detail": {"reason": reason}, "at": at}


def end_linked_plan(plan_id: str, reason: str, *, conn,
                    notice: bool = False) -> EndedPlan | None:
    """Lock `plan_id` in the caller's transaction and end it by
    LINKED_TERMINAL. None (nothing written) when the plan is missing or
    already terminal. `notice=True` (the delete path) queues the plan's
    feed / follow notice in the same write. Raises on a failed write, so the
    caller's transaction rolls back whole."""
    store = PlanStore()
    plan = store.lock_for_update(plan_id, conn=conn)
    terminal = LINKED_TERMINAL.get(getattr(plan, "status", None))
    if terminal is None:
        return None
    before, at = plan.status, _now_iso()
    record_transition(plan, terminal, reason=reason, at=at)
    if notice:
        plan.pending_notice = _notice(terminal, reason, at)
    store.update(plan, conn=conn)
    return EndedPlan(plan.plan_id, plan.ticker, before, terminal)


def cancel_unfilled_in(plan_id: str, reason: str, *, conn) -> bool:
    """In the caller's transaction: when `plan_id` is still PENDING under its
    row lock (its order never filled), cancel it with `reason` and discard its
    placeholder trade row; True. Otherwise touch nothing; False. No P&L is
    ever booked here."""
    plan = PlanStore().lock_for_update(plan_id, conn=conn)
    if plan is None or plan.status != PlanStatus.PENDING:
        return False
    from swingbot.core.tracking.performance import TradeLog   # performance imports this module
    end_linked_plan(plan_id, reason, conn=conn)
    TradeLog().discard_plan_placeholder(plan_id, conn=conn)
    return True


def cancel_if_unfilled(plan_id: str, reason: str) -> bool:
    """`cancel_unfilled_in` in its own transaction, on the bot's lock timeout
    (the reversal runs in the scanner). LockTimeout propagates."""
    with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as tx:
        return cancel_unfilled_in(plan_id, reason, conn=tx)
```

- [ ] **Step 5: `performance.py` — `_close_linked_plan_safely` takes `conn=`**

Replace `_close_linked_plan_safely` (`:118-140`) with:

```python
def _close_linked_plan_safely(plan_id: str, reason: str, *, conn=None) -> None:
    """Close the v2 plan behind a trade row that was closed OUTSIDE the plan
    manager (today: a reversal). The row is only half the position; left
    alone, the plan stays open and the manager keeps stepping it. A PENDING
    plan can only cancel; ACTIVE/PARTIAL close (plan_links.LINKED_TERMINAL).

    v189 D3.2: with `conn` the plan ends inside the caller's transaction and
    a failure RAISES -- a half-ended position is what this replaces, and a
    swallowed SQL error would leave the transaction unusable anyway. Without
    `conn` it runs in its own short transaction and, as before, never breaks
    the trade close it follows."""
    from swingbot.core.tracking import plan_links
    if conn is not None:
        plan_links.end_linked_plan(plan_id, reason, conn=conn)
        return
    try:
        from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
        with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as tx:
            plan_links.end_linked_plan(plan_id, reason, conn=tx)
    except Exception:
        log.warning(
            "could not close plan %s after its trade closed", plan_id, exc_info=True)
```

(`plan_links.end_linked_plan` is looked up on the module at call time, so the tests' monkeypatch reaches it.)

- [ ] **Step 6: `performance.py` — `close_trade_reversed` in one transaction**

Replace `close_trade_reversed` (`:1308-1348`) with:

```python
    def close_trade_reversed(self, trade_id: str, exit_price: float) -> dict | None:
        """Close an open trade early because the opposite setup has taken over.

        Modelled on check_near_tp_timeout()'s early close, NOT on
        close_trade_manual(): that one records no exit_price and never settles
        the account balance, which would leave P&L and R blank in Trade
        History and hide the whole point of cutting the loss sooner.

        Lands as status "closed" with close_reason "reversed", so it counts as
        a scratch rather than a win or a loss -- win rate is computed over
        wins+losses only, and a reversal is neither. The reason keeps them
        filterable.

        A plan-linked (v2) trade is realized the way close_trade_manual
        realizes one: any runner remainder left after TP1 becomes its own leg
        at `exit_price`, so settle_legs prices the whole position.

        v189 A1/D3: one transaction on the bot's lock timeout, lock order plan
        -> trade -> account. A trade whose plan is still PENDING under its row
        lock is a never-filled placeholder, not a position: the plan is
        cancelled, the placeholder discarded, no P&L booked, and None is
        returned. Otherwise the trade closes, its balance point and its plan's
        CLOSED transition commit together, and the journal and snapshot hooks
        run after commit.

        Returns the closed record, or None if the trade was not open (a
        parallel tick may have closed it first) or was a placeholder.
        """
        from swingbot.core.db.engine import BOT_LOCK_TIMEOUT_MS, transaction
        from swingbot.core.tracking import plan_links
        found = self._open_trade_by_id(trade_id)
        plan_id = found.get("plan_id") if found else None
        with transaction(lock_timeout_ms=BOT_LOCK_TIMEOUT_MS) as tx:
            if plan_id and plan_links.cancel_unfilled_in(plan_id, "reversed", conn=tx):
                return None
            closed = self._reverse_open_trade(trade_id, exit_price, conn=tx)
            if closed is not None and plan_id:
                _close_linked_plan_safely(plan_id, reason="reversed", conn=tx)
        if closed is not None:
            run_after_commit([lambda: _after_close(closed), lambda: _refresh_snapshot_safely()])
        return closed

    def _reverse_open_trade(self, trade_id: str, exit_price: float, *, conn) -> dict | None:
        """The reversal close of one open trade inside `conn`'s transaction:
        the runner remainder as a leg, `closed`/`reversed`, and its balance
        point (a failed balance write raises). None when it is not open."""
        t = self._open_trade_by_id(trade_id, conn=conn)
        if t is None:
            return None
        _apply_exit_price(t, exit_price, reason="reversed")
        t["status"] = "closed"
        t["closed_at"] = datetime.now(timezone.utc).isoformat()
        t["close_reason"] = "reversed"
        self._settle_account_balance(t, conn=conn)
        closed = dict(t)
        self._db_upsert(t, conn=conn)
        return closed
```

- [ ] **Step 7: `scan_run.py` — extract the reversal settlement**

In `swingbot/core/scanning/scan_run.py` add to the imports (beside `from swingbot.core.tracking.performance import TradeLog`, `:41`):

```python
from swingbot.core.db.engine import LockTimeout
from swingbot.core.tracking import plan_links
```

Directly above `def _sync_run_scan(` (`:448`) add:

```python
def _usable_reversal_price(price) -> bool:
    """A live quote a reversal may settle at: finite and positive."""
    return price is not None and math.isfinite(price) and price > 0


def _settle_reversal(trade_log, existing_trade: dict, live_price: float | None) -> dict | None:
    """Settle the open trade an opposite setup is reversing (v189 A1).

    A trade whose plan never filled is a placeholder for a resting order, not
    a position: plan_links.cancel_if_unfilled cancels the plan and discards
    the placeholder under the plan row lock -- no P&L, no price needed.
    Anything else closes at the live price through close_trade_reversed,
    which re-checks the plan under the same lock (a fill recorded meanwhile
    makes it the real position it is).

    Returns the closed trade, the discarded placeholder (status "discarded"),
    or None when nothing was settled: no usable price for a real position,
    already closed, or the plan row held by another writer (logged; the next
    scan tries again)."""
    plan_id = existing_trade.get("plan_id")
    try:
        if plan_id and plan_links.cancel_if_unfilled(plan_id, "reversed"):
            log.info("%s: reversal cancelled unfilled plan %s; its placeholder booked nothing",
                     existing_trade.get("ticker"), plan_id)
            return dict(existing_trade, status="discarded")
        if not _usable_reversal_price(live_price):
            return None
        return trade_log.close_trade_reversed(existing_trade["id"], live_price)
    except LockTimeout:
        log.info("%s: reversal deferred -- plan %s is locked by another writer",
                 existing_trade.get("ticker"), plan_id)
        return None
```

In `_sync_run_scan`, replace the block from `live_price = fetch.get_current_price(...)` through the `log.info("%s: reversed ...")` call (`:931-941`) with:

```python
                live_price = fetch.get_current_price(result.ticker, allow_stale=False)
                closed = _settle_reversal(trade_log, existing_trade, live_price)
                if closed is not None:
                    reversed_count += 1
                    already_open = False
                    log.info("%s: reversed %s -> %s at %s (%s)",
                             result.ticker, existing_trade["direction"],
                             result.trend, live_price, decision.reason)
```

The comment block above `live_price = ...` (the four `# No df in scope ...` lines) stays. The log line moves from `%.2f` to `%s` because a placeholder reversal may have no price.

- [ ] **Step 8: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_plan_links.py`
Expected: PASS (16 tests).

Run: `python scripts/dev/testrun.py file tests/scanning/test_reversal_placeholder.py`
Expected: PASS (10 tests).

- [ ] **Step 9: Existing reversal and scan tests, everything the diff reaches, the gate**

Run each (all must PASS unchanged):
`python scripts/dev/testrun.py file tests/tracking/test_one_trade_per_ticker.py`
`python scripts/dev/testrun.py file tests/scanning/test_short_funnel.py`
`python scripts/dev/testrun.py file tests/scanning/test_feed_close_routes.py`

`test_one_trade_per_ticker.py::test_reversing_a_pending_plans_placeholder_trade_cancels_the_plan` keeps passing: it asserts only the CANCELLED status, which still holds (the close now also books nothing). `test_short_funnel.py`'s fake trade log has no `plan_id` on its trades, so `_settle_reversal` goes straight to its `close_trade_reversed`.

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0, and `_sync_run_scan` strictly below its baseline of 96 (the `if live_price and live_price > 0` guard left it: 94). Confirm with `python -m radon cc -s swingbot/core/scanning/scan_run.py | grep _sync_run_scan`. `close_trade_reversed` about 6, `_settle_reversal` about 5, `end_linked_plan` about 3.

- [ ] **Step 10: Commit**

Two scoped commits (the links and TradeLog, then the scanner):

```bash
git add swingbot/core/tracking/plan_links.py swingbot/core/tracking/performance.py tests/tracking/test_plan_links.py
git commit -m "feat(tracking): plan_links ends a trade's plan in the trade's transaction; a reversal never books a placeholder (v189 V189-12)"
git add swingbot/core/scanning/scan_run.py tests/scanning/test_reversal_placeholder.py
git commit -m "fix(scanning): reversal settles through _settle_reversal -- an unfilled plan is cancelled, not booked (v189 V189-12)"
```

(Both files are edited and Steps 8-9 are green before the first commit.)

