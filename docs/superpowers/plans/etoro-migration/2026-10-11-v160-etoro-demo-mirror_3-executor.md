# v160 eToro demo mirror: plan events become demo-account trades. Part 3: the executor (EM8–EM9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task EM8" -A 700 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Executor rules, § Sizing and order checks, § Daily reconciliation, § Testing `test_executor.py`)
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.

**Conventions for every task in this part**

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror` (created in EM1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`, and run tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>`.
- `swingbot/core/broker/__init__.py`, `guard.py` and `tests/broker/__init__.py` exist already (v159 ER7). No task here creates or edits them.
- `executor.py` imports `etoro_client` (lazily, in `get_executor`), so v159's AST scan counts it as eToro code: it must call `guard.assert_demo("demo")`, and it does, in `Executor.run_tick`. It never contains the substring `etoro.com`.
- The executor tests never touch Postgres or the network: they use `tests/broker/fakes.py` (`FakeClient`, `FakeRepo`, `FakePlans`, `ManualClock`), a fixed `now_fn`, and stub `checks.parse_eligibility` / `checks.check_open` so they test the executor's machine, not EM4's parsing or EM5's caps (those have their own tests).
- Every new function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for `executor.py`.

## Part-local constraints

- **Stale fills never open (controller decision, 2026-10-11).** A `filled` notice is resent every tick for up to `NOTICE_RESEND_DAYS = 5` days until Discord acknowledges it, with no resend marker, so the first `filled` the mirror ever sees for a plan can be days old (bot restarted, flag switched on, Discord down). An `open` row is therefore sent **only for a fresh fill**: at send time, before any eToro request, the executor skips the row with reason `stale_fill` when the plan is missing, its `status` is neither `ACTIVE` nor `PARTIAL`, or its fill time is more than `executor.STALE_FILL_MINUTES = 30` minutes before `now`. The fill time is the `at` of the latest `{"status": "ACTIVE", ...}` entry in `plan.status_history` (written by `record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill", at=self._now())`, `plan_manager.py:813`, an ISO-8601 UTC string). The `filled` event detail carries no timestamp (`{"entry_price", "live_price"}`, `plan_manager.py:816`), so the event is not a source. No `ACTIVE` entry, or an unparseable `at`, counts as stale (fail closed). Exactly 30 minutes is still fresh. `stale_fill` is an executor skip reason, like `no_position`.
- **Transient reads stay queued.** A failed eligibility or rates read (non-2xx, transport error) leaves the `open` row `queued` for the next tick; the stale-fill rule bounds the retries to 30 minutes. A failed lookup leaves the row where it was.
- **Ambiguous sends are recovered, never resent blind.** A transport error or a 5xx on an order call leaves the row `sending`; the next tick looks it up by `referenceId` (the request id). Found → its outcome; `404` (or a 2xx body without a `status`) → back to `queued` and resent with the **same** request id. A `move_stop` has nothing to look up, so a stuck one goes straight back to `queued`.
- **One tick at a time.** `run_tick` takes a non-blocking `threading.Lock`; a tick that finds it held (a timed-out tick's thread still running in `asyncio.to_thread`) returns at once.
- **Auth warnings once per process per scope:** `demo:write` (order and stop calls), `demo:read` (eligibility, lookup, portfolio, history), `market-data:read` (rates).

# Phase 4 — the executor (EM8–EM9)

### Task EM8: `executor.py`: rows, ordering, budget, sending, outcomes, recovery

**Model:** opus — the send state machine decides whether a demo order is sent twice, sent without a row, or sent for a stale fill; every branch is money-shaped and crosses five contracts (repository, sizing, checks, translator, client).

Spec § Executor rules, § Sizing and order checks (sizing steps 1–3, `check_open` at send time after a fresh quote), § Event mapping (deduplication), § Testing (`test_executor.py`). Index § Global Constraints (idempotency, lookup status ids, `move_stop` has no lookup, `no_position`, never `StoreWriteHalt`, logging contract). Part-local constraints above (stale fill, transient reads, recovery, one tick at a time).

What the executor does per tick (`run_tick(events)`):

1. `guard.assert_demo("demo")`; take the tick lock or return.
2. **Enqueue.** For each event: load the plan (`plans.get`), build `SentState` from `repo.for_plan(plan_id)` (`mirror.sent_state_from_rows`), translate (`mirror.actions_for`), and `repo.insert_new` one `queued` row per action, in action order. A duplicate key returns `None` and is ignored. A failed insert is logged (classified by `write_failure.is_store_write_failure`) and the event's remaining actions are not inserted, so `seq` order is never inverted.
3. **Advance** until the 20 s send budget (`SEND_BUDGET_S`) is spent: read every `queued`/`sending`/`in_flight` row (`repo.with_status`, ordered `plan_id, seq`); per plan, only the lowest-`seq` non-final row may move; when it reaches a final status the next row of the same plan may move in the same tick. A row whose `not_before` is in the future is left alone. The clock is checked before every row.
   - `queued` → send: `open` (stale-fill check, eligibility, quote, sizing, `check_open`, body), `close_units`/`close_all` (`POST` close by units, `None` = all), `move_stop` (`PATCH` stop). Followers need the plan's `open` row `filled` with a `position_id`; otherwise `skipped`/`no_position`. **The row is written `sending` before the request; if that write fails, nothing is sent.**
   - `sending` → recover by lookup (see part-local constraints).
   - `in_flight` → lookup; status id 3/5/9 → `filled` (open: `position_id`, `avg_price`, `units_filled`, `fees`, `filled_at`), 4/7/8/10 → `rejected` (`error_code`, `error_message`; `631`/`632` on a close or stop row → `closed_by_broker`), else stays `in_flight`.
4. Every final status calls the hook `_after_final(row)`; it is a no-op here and EM9 implements it.

Send-result mapping (`_apply_send_result`): bucket deferral → `queued`, `not_before = now`; `429` → `queued`, `not_before = now + Retry-After` (else `DEFAULT_RETRY_S = 60`); status `0` with an error, or `>= 500` → stays `sending`; 2xx → `in_flight` with `order_id` (a `move_stop` 2xx → `filled` at once); `409` or body error code `631`/`632` on a close or stop row → `closed_by_broker`; `401`/`403` → `rejected` plus one WARNING per process per scope; any other 4xx → `rejected`.

**Files:**
- Create: `swingbot/core/broker/executor.py`
- Create: `tests/broker/fakes.py`
- Create: `tests/broker/test_executor.py`

**Interfaces:**
- Consumes:
  - `swingbot.core.db.repositories.broker_orders` (EM2): `STATUSES`, `FINAL_STATUSES`, `broker_orders_repo()`; repository methods `insert_new(record) -> dict | None`, `for_plan(plan_id) -> list[dict]`, `with_status(statuses) -> list[dict]`, `set_status(request_id, status, changes=None) -> None` (`LookupError` on a missing row), `all_rows()`, `open_positions()`. Records are flat dicts; `position_id` is absent while NULL.
  - `swingbot.core.broker.sizing` (EM3): `WHOLE_UNIT_DECIMALS = 0`, `round_down(value: float, decimals: int) -> float`, `mirror_units(plan_units, entry, max_trade_usd, precision) -> SizeResult(units, plan_units, plan_notional, capped_notional, scale_factor)`.
  - `swingbot.core.broker.checks` (EM4, EM5): `OpenOrder(ticker, direction, entry, stop, units)`, `Quote(bid, ask, at)`, `Eligibility(instrument_id, symbol, allow_open, settlement_type, min_exposure_usd, max_units, min_stop_pct, max_stop_pct, unit_decimals)`, `MirrorBook(open_trades: tuple, balance: float, dfs: dict, sectors: dict | None)`, `CheckConfig.from_config()` (field `max_trade_usd`), `parse_eligibility(body, symbol, direction) -> Eligibility | None`, `order_price(direction, quote) -> float`, `check_open(order, quote, eligibility, book, cfg) -> str | None`, `heat_trades(open_rows) -> list[dict]`.
  - `swingbot.core.broker.mirror` (EM6): `ACTION_OPEN`, `ACTION_CLOSE_UNITS`, `ACTION_CLOSE_ALL`, `ACTION_MOVE_STOP`, `BrokerAction`, `sent_state_from_rows(rows) -> SentState`, `actions_for(event, plan, sent) -> list[BrokerAction]`.
  - `swingbot.core.broker.etoro_client` (EM7): `ClientResult(status_code, body=None, retry_after=None, deferred=False, error="")` with `.ok`; `EtoroClient()` methods `open_order(body, request_id)`, `close_position(position_id, instrument_id, units, request_id)`, `update_stop(position_id, stop_rate, request_id)`, `lookup(reference_id)`, `eligibility(symbol)`, `rates(instrument_id)`, `portfolio()`, `history(min_date, page=1, page_size=200)`.
  - `swingbot.core.broker.guard.assert_demo(account: str) -> None` (v159 ER7).
  - `swingbot.core.db.write_failure.is_store_write_failure(exc) -> bool` (`write_failure.py:24`).
  - `swingbot.core.planning.account.compute_position_size(entry, stop_loss, ...) -> dict | None` (`account.py:405`; keys `shares`, `balance`); `swingbot.core.planning.plan_store.PlanStore` (`.get(plan_id) -> TradePlanV2 | None`); `PlanStatus` (`plan_types.py:6`); `swingbot.core.marketdata.data.get_daily_data(ticker)` (`data.py:29`); `swingbot.core.marketdata.universe.sector_map(name) -> dict` (`universe.py:219`); `config.SCAN_UNIVERSE`.
  - Test helper `tests.planning.test_plan_engine_model._plan(**kw) -> TradePlanV2`.
- Produces (EM9, EM10, EM13 rely on these exact names):
  - `NAMESPACE = uuid.UUID("5b0c1f0e-7a4d-5c2b-9e61-3d8f2a6c1e47")`, `SEND_BUDGET_S = 20.0`, `STALE_FILL_MINUTES = 30`, `DEFAULT_RETRY_S = 60.0`, `STALE_FILL = "stale_fill"`, `NO_POSITION = "no_position"`, `ZERO_UNITS = "zero_units"`, `PENDING_STATUSES = ("queued", "sending", "in_flight")`.
  - `request_id_for(plan_id: str, action: str, event_key: str) -> str`; `outcome_for(status_id: object) -> str` (`"filled"`/`"rejected"`/`"in_flight"`); `fill_time(plan) -> datetime | None`; `is_fresh_fill(plan, now: datetime) -> bool`; `open_body(row: dict, eligibility: Eligibility, units: float) -> dict`.
  - `class Executor(client, repo, plans, *, clock=time.monotonic, now_fn=None, sizer=None, market=None)`: `run_tick(events: list) -> None`, `enqueue(events: list) -> int`, `advance(deadline: float) -> None`, `_after_final(row: dict) -> None` (no-op), and the private helpers EM9 reuses: `_open_row(plan_id) -> dict | None` (the plan's `open` row when `filled` with a `position_id`), `_set(row, status, changes) -> str`, `_store_problem(what, plan_id, exc) -> None`, `self._now() -> datetime`.
  - `get_executor() -> Executor` (process singleton over `EtoroClient()`, `broker_orders_repo()`, `PlanStore()`).
  - Row doc fields (flat record keys, index ledger): `ticker`, `direction`, `event_at`, `stop_sent`, `tp_sent`, `fraction`, `instrument_id`, `unit_decimals`, `settlement_type`, `requested`, `plan_units`, `units_requested`, `scale_factor`, `plan_notional`, `capped_notional`, `sizing_balance`, `quote_at_send`, `quote_at`, `sent_at`, `order_id`, `position_id`, `avg_price`, `units_filled`, `fees`, `filled_at`, `fraction_closed`, `skip_reason`, `error_code`, `error_message`, `not_before`.
  - `tests/broker/fakes.py`: `db_down() -> Exception`, `ManualClock(now=0.0)` (callable, `.advance(s)`), `FakeClient(clock=None, step_s=0.0)` (`.script(method, *results)`, `.calls: list[tuple[str, tuple]]`, `.names() -> list[str]`), `lookup_result(status_id, **kw) -> ClientResult`, `rates_result(instrument_id=1001, bid=100.0, ask=100.1) -> ClientResult`, `FakeRepo` (the six repository methods plus `.rows`, `.fail_insert: bool`, `.fail_status: set[str]`, `.row(request_id) -> dict`, `.seed(plan_id, action, event_key, status, **doc) -> dict`), `FakePlans(dict)`.

- [ ] **Step 1: Confirm every consumed contract is on the branch**

```bash
git -C "$WT" grep -n "def insert_new\|def open_positions" -- swingbot/core/db/repositories/broker_orders.py
git -C "$WT" grep -n "def mirror_units\|def round_down" -- swingbot/core/broker/sizing.py
git -C "$WT" grep -n "def check_open\|def heat_trades\|def parse_eligibility\|def order_price\|def from_config" -- swingbot/core/broker/checks.py
git -C "$WT" grep -n "def actions_for\|def sent_state_from_rows" -- swingbot/core/broker/mirror.py
git -C "$WT" grep -n "class EtoroClient\|class ClientResult" -- swingbot/core/broker/etoro_client.py
git -C "$WT" grep -n '"executor.py"' -- tests/broker/test_guard.py
```

Expected: every command prints at least one hit (2, 2, 5, 2, 2 and 1). A missing hit names the task that is not merged yet (EM2, EM3, EM4/EM5, EM6, EM7, EM1): stop with `BLOCKED: EM8 needs <task>`.

- [ ] **Step 2: Write the fakes**

Create `tests/broker/fakes.py`:

```python
"""In-memory stand-ins for the executor tests (v160). No Postgres, no network.

FakeRepo mirrors BrokerOrderRepository (EM2): insert_new dedupes on
(plan_id, action, event_key) and on request_id and assigns the next free
per-plan seq; set_status raises LookupError for an unknown request id.
FakeClient replies from a per-method script, else a sensible default, and
can advance a ManualClock on every call to exercise the send budget.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy.exc as sa_exc

from swingbot.core.broker.etoro_client import ClientResult
from swingbot.core.db.repositories.broker_orders import STATUSES

_CLOSING = frozenset({"filled", "closed_by_broker"})


def db_down() -> Exception:
    """What a failed Postgres write raises: a SQLAlchemyError."""
    return sa_exc.OperationalError("UPDATE broker_orders", {}, Exception("db down"))


class ManualClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def lookup_result(status_id, *, position_id=5001, avg_price=100.1, units=2.0, fees=0.0,
                  error_code=None, error_message="", http=200) -> ClientResult:
    body = {"status": {"id": status_id, "errorCode": error_code, "errorMessage": error_message},
            "positionExecutions": [{"positionId": position_id, "openingData": {
                "avgPrice": avg_price, "units": units, "fees": fees}}]}
    return ClientResult(http, body)


def rates_result(instrument_id=1001, bid=100.0, ask=100.1) -> ClientResult:
    return ClientResult(200, {"results": [{"instrumentId": instrument_id, "bid": bid,
                                           "ask": ask, "date": "2026-10-12T14:59:58Z"}]})


def _defaults() -> dict:
    return {
        "open_order": lambda: ClientResult(202, {"orderId": 7001, "referenceId": "ref"}),
        "close_position": lambda: ClientResult(200, {"orderForClose": {"orderID": 7002}}),
        "update_stop": lambda: ClientResult(202, {"operationId": "op-1"}),
        "lookup": lambda: lookup_result(3),
        "eligibility": lambda: ClientResult(200, {"eligibilities": []}),
        "rates": rates_result,
        "portfolio": lambda: ClientResult(200, {"clientPortfolio": {"positions": []}}),
        "history": lambda: ClientResult(200, []),
    }


class FakeClient:
    def __init__(self, clock: ManualClock | None = None, step_s: float = 0.0):
        self.calls: list[tuple[str, tuple]] = []
        self.scripts: dict[str, list] = {}
        self._clock = clock
        self._step = step_s
        self._defaults = _defaults()

    def script(self, method: str, *results: ClientResult) -> None:
        self.scripts.setdefault(method, []).extend(results)

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def _reply(self, name: str, *args) -> ClientResult:
        self.calls.append((name, args))
        if self._clock is not None:
            self._clock.advance(self._step)
        queue = self.scripts.get(name)
        return queue.pop(0) if queue else self._defaults[name]()

    def open_order(self, body, request_id):
        return self._reply("open_order", body, request_id)

    def close_position(self, position_id, instrument_id, units, request_id):
        return self._reply("close_position", position_id, instrument_id, units, request_id)

    def update_stop(self, position_id, stop_rate, request_id):
        return self._reply("update_stop", position_id, stop_rate, request_id)

    def lookup(self, reference_id):
        return self._reply("lookup", reference_id)

    def eligibility(self, symbol):
        return self._reply("eligibility", symbol)

    def rates(self, instrument_id):
        return self._reply("rates", instrument_id)

    def portfolio(self):
        return self._reply("portfolio")

    def history(self, min_date, page=1, page_size=200):
        return self._reply("history", min_date, page, page_size)


def _check(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")


class FakeRepo:
    def __init__(self):
        self.rows: list[dict] = []
        self.fail_insert = False
        self.fail_status: set[str] = set()

    def _sorted(self, rows) -> list[dict]:
        return [dict(row) for row in sorted(rows, key=lambda row: (row["plan_id"], row["seq"]))]

    def _clash(self, record: dict) -> bool:
        key = (record["plan_id"], record["action"], record["event_key"])
        return any(row["request_id"] == record["request_id"]
                   or (row["plan_id"], row["action"], row["event_key"]) == key
                   for row in self.rows)

    def insert_new(self, record: dict, *, conn=None) -> dict | None:
        if self.fail_insert:
            raise db_down()
        status = record.get("status", "queued")
        _check(status)
        if self._clash(record):
            return None
        seq = 1 + max((row["seq"] for row in self.rows if row["plan_id"] == record["plan_id"]),
                      default=0)
        row = {**record, "status": status, "seq": seq,
               "created_at": dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)}
        self.rows.append(row)
        return dict(row)

    def for_plan(self, plan_id: str, *, conn=None) -> list[dict]:
        return self._sorted(row for row in self.rows if row["plan_id"] == plan_id)

    def with_status(self, statuses, *, conn=None) -> list[dict]:
        wanted = set(statuses)
        return self._sorted(row for row in self.rows if row["status"] in wanted)

    def row(self, request_id: str) -> dict:
        """The live stored dict (tests read and edit it directly)."""
        for row in self.rows:
            if row["request_id"] == request_id:
                return row
        raise LookupError(request_id)

    def set_status(self, request_id: str, status: str, changes: dict | None = None, *,
                   conn=None) -> None:
        _check(status)
        if status in self.fail_status:
            raise db_down()
        row = self.row(request_id)
        row.update(changes or {})
        row["status"] = status

    def all_rows(self, *, conn=None) -> list[dict]:
        return [{**row, "updated_at": "2026-10-12T20:00:00+00:00"}
                for row in self._sorted(self.rows)]

    def open_positions(self, *, conn=None) -> list[dict]:
        out = []
        for opened in self._sorted(self.rows):
            if opened["action"] != "open" or opened["status"] != "filled":
                continue
            plan_rows = [row for row in self.rows if row["plan_id"] == opened["plan_id"]]
            gone = any(row["status"] == "closed_by_broker" for row in plan_rows) or any(
                row["action"] == "close_all" and row["status"] in _CLOSING for row in plan_rows)
            if not gone:
                out.append(opened)
        return out

    def seed(self, plan_id: str, action: str, event_key: str, status: str, **doc) -> dict:
        """Insert a row in any status, as an earlier tick would have left it."""
        from swingbot.core.broker.executor import request_id_for
        row = self.insert_new({"plan_id": plan_id, "action": action, "event_key": event_key,
                               "request_id": request_id_for(plan_id, action, event_key),
                               "ticker": doc.pop("ticker", "AAPL"),
                               "direction": doc.pop("direction", "bullish"), **doc})
        stored = self.row(row["request_id"])
        stored["status"] = status
        return stored


class FakePlans(dict):
    """plan_id -> TradePlanV2; `.get` is dict.get, like PlanStore.get."""
```

- [ ] **Step 3: Write the failing executor tests**

Create `tests/broker/test_executor.py`:

```python
"""v160 EM8: the executor's send machine (fake client, in-memory repository).

No Postgres, no network. checks.parse_eligibility and checks.check_open are
stubbed: their own rules are pinned in test_checks*.py; here only the
machine around them is under test.
"""
import datetime as dt
import logging
import uuid
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.broker import checks, executor, guard, sizing
from swingbot.core.broker.etoro_client import ClientResult, EtoroClient
from swingbot.core.broker.executor import (
    NAMESPACE, SEND_BUDGET_S, STALE_FILL_MINUTES, Executor, fill_time, get_executor,
    is_fresh_fill, outcome_for, request_id_for)
from swingbot.core.db.repositories.broker_orders import broker_orders_repo
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.planning.plan_types import PlanStatus
from tests.broker.fakes import (
    FakeClient, FakePlans, FakeRepo, ManualClock, lookup_result)
from tests.planning.test_plan_engine_model import _plan

NOW = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)   # Monday, 11:00 ET
LOGGER = "swingbot.core.broker.executor"
ELIG = checks.Eligibility(instrument_id=1001, symbol="AAPL", allow_open=True,
                          settlement_type="real", min_exposure_usd=10.0, max_units=None,
                          min_stop_pct=None, max_stop_pct=None, unit_decimals=0)
FILLED = PlanEvent("p1", "filled", {"entry_price": 100.0, "live_price": 100.2})
OPEN_RID = request_id_for("p1", "open", "filled")
CLOSE_RID = request_id_for("p1", "close_all", "closed")


def _filled_plan(age=dt.timedelta(minutes=1), **kw):
    base = dict(entry_price=100.0, status=PlanStatus.ACTIVE, status_history=[
        {"status": "ACTIVE", "reason": "stop_entry_fill", "at": (NOW - age).isoformat()}])
    base.update(kw)
    return _plan(**base)


@pytest.fixture(autouse=True)
def demo_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(guard, "assert_demo", calls.append)
    monkeypatch.setattr(executor, "_AUTH_WARNED", set())
    monkeypatch.setattr(config, "ETORO_MAX_TRADE_USD", 250.0, raising=False)
    return calls


@pytest.fixture
def seen(monkeypatch):
    state = SimpleNamespace(opens=[], verdict=None)
    monkeypatch.setattr(checks, "parse_eligibility", lambda body, symbol, direction: ELIG)

    def _check_open(order, quote, eligibility, book, cfg):
        state.opens.append(SimpleNamespace(order=order, quote=quote, eligibility=eligibility,
                                           book=book, cfg=cfg))
        return state.verdict

    monkeypatch.setattr(checks, "check_open", _check_open)
    return state


@pytest.fixture
def rig(seen):
    clock = ManualClock()
    client, repo, plans, markets = FakeClient(clock), FakeRepo(), FakePlans(p1=_filled_plan()), []

    def market(tickers):
        markets.append(list(tickers))
        return {ticker: None for ticker in tickers}, {"AAPL": "Technology"}

    ex = Executor(client, repo, plans, clock=clock, now_fn=lambda: NOW,
                  sizer=lambda entry, stop: {"shares": 10.0, "balance": 10000.0}, market=market)
    return SimpleNamespace(ex=ex, client=client, repo=repo, plans=plans, clock=clock,
                           seen=seen, markets=markets)


def _advance(rig):
    rig.ex.advance(rig.clock() + SEND_BUDGET_S)


def _filled_open(rig, plan_id="p1", **doc):
    base = dict(position_id=5001, instrument_id=1001, unit_decimals=0, units_filled=3.0,
                avg_price=100.1, stop_sent=95.0)
    base.update(doc)
    return rig.repo.seed(plan_id, "open", "filled", "filled", **base)


# --- ids and status ids -------------------------------------------------------

def test_request_ids_are_uuid5_of_plan_action_and_key():
    assert NAMESPACE == uuid.UUID("5b0c1f0e-7a4d-5c2b-9e61-3d8f2a6c1e47")
    assert OPEN_RID == str(uuid.uuid5(NAMESPACE, "p1:open:filled"))
    assert request_id_for("p1", "move_stop", "100.0000") != request_id_for("p1", "move_stop", "101.0000")


@pytest.mark.parametrize("status_id,outcome", [
    (3, "filled"), (5, "filled"), (9, "filled"), (4, "rejected"), (7, "rejected"),
    (8, "rejected"), (10, "rejected"), (1, "in_flight"), (2, "in_flight"), (6, "in_flight"),
    (11, "in_flight"), (12, "in_flight"), (None, "in_flight"), ("x", "in_flight")])
def test_outcome_for_maps_every_lookup_status(status_id, outcome):
    assert outcome_for(status_id) == outcome


# --- enqueue -------------------------------------------------------------------

def test_a_fill_queues_one_open_row_with_its_stop_and_target(rig):
    assert rig.ex.enqueue([FILLED]) == 1
    [row] = rig.repo.rows
    assert (row["action"], row["event_key"], row["status"], row["seq"]) == ("open", "filled", "queued", 1)
    assert row["request_id"] == OPEN_RID
    assert (row["ticker"], row["direction"], row["stop_sent"], row["tp_sent"]) == (
        "AAPL", "bullish", 95.0, 105.0)
    assert row["event_at"] == NOW.isoformat()


def test_a_resent_fill_queues_nothing_more(rig):
    rig.ex.enqueue([FILLED])
    assert rig.ex.enqueue([FILLED, FILLED]) == 0
    assert len(rig.repo.rows) == 1


def test_unknown_and_weak_plans_queue_nothing(rig):
    rig.plans["p2"] = _filled_plan(plan_id="p2", ledger="weak")
    assert rig.ex.enqueue([PlanEvent("zz", "filled", {}), PlanEvent("p2", "filled", {})]) == 0
    assert rig.repo.rows == []


def test_tp1_partial_queues_the_close_before_the_stop(rig):
    _filled_open(rig)
    rig.plans["p1"] = _filled_plan(status=PlanStatus.PARTIAL, working_stop=100.0)
    event = PlanEvent("p1", "tp1_partial", {"fraction": 0.5, "working_stop": 100.0})
    assert rig.ex.enqueue([event]) == 2
    assert [(r["action"], r["seq"], r["fraction"], r["stop_sent"])
            for r in rig.repo.for_plan("p1")[1:]] == [
        ("close_units", 2, 0.5, None), ("move_stop", 3, None, 100.0)]


def test_a_failed_insert_queues_nothing_and_warns(rig, caplog):
    rig.repo.fail_insert = True
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert rig.ex.enqueue([FILLED]) == 0
    assert rig.repo.rows == []
    assert "store write failure" in caplog.text


# --- no row, no send --------------------------------------------------------------

def test_nothing_is_sent_when_the_sending_write_fails(rig, caplog):
    rig.ex.enqueue([FILLED])
    rig.repo.fail_status = {"sending"}
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        _advance(rig)
    assert "open_order" not in rig.client.names()
    assert rig.repo.row(OPEN_RID)["status"] == "queued"
    assert "store write failure" in caplog.text


def test_a_failed_write_after_the_send_is_recovered_by_lookup_not_resent(rig):
    rig.ex.enqueue([FILLED])
    rig.repo.fail_status = {"in_flight"}
    _advance(rig)
    assert rig.client.names().count("open_order") == 1
    assert rig.repo.row(OPEN_RID)["status"] == "sending"
    rig.repo.fail_status = set()
    _advance(rig)
    assert rig.client.names().count("open_order") == 1
    assert rig.client.calls[-1] == ("lookup", (OPEN_RID,))
    assert rig.repo.row(OPEN_RID)["status"] == "filled"


# --- the open ------------------------------------------------------------------

def test_a_fresh_fill_sends_one_sized_open_with_its_stop(rig, caplog):
    expected = sizing.mirror_units(10.0, 100.0, 250.0, 0)
    assert expected.units == 2.0
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rig.ex.run_tick([FILLED])
    assert rig.client.names() == ["eligibility", "rates", "open_order"]
    body, request_id = rig.client.calls[-1][1]
    assert body == {"action": "open", "transaction": "buy", "instrumentId": 1001, "units": 2.0,
                    "orderType": "mkt", "leverage": 1, "stopLossRate": 95.0,
                    "takeProfitRate": 105.0, "stopLossType": "fixed", "settlementType": "real"}
    assert request_id == OPEN_RID
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["order_id"], row["requested"], row["sent_at"]) == (
        "in_flight", 7001, body, NOW.isoformat())
    assert (row["plan_units"], row["units_requested"], row["sizing_balance"]) == (10.0, 2.0, 10000.0)
    assert (row["scale_factor"], row["plan_notional"], row["capped_notional"]) == (
        expected.scale_factor, expected.plan_notional, expected.capped_notional)
    assert (row["quote_at_send"], row["instrument_id"], row["settlement_type"]) == (100.1, 1001, "real")
    [call] = rig.seen.opens
    assert call.order == checks.OpenOrder(ticker="AAPL", direction="bullish", entry=100.0,
                                          stop=95.0, units=2.0)
    assert call.quote == checks.Quote(bid=100.0, ask=100.1, at="2026-10-12T14:59:58Z")
    assert (call.eligibility, call.book.balance, call.cfg.max_trade_usd) == (ELIG, 10000.0, 250.0)
    assert "etoro mirror open in_flight: AAPL p1" in caplog.text


def test_the_next_tick_records_the_fill(rig):
    rig.ex.run_tick([FILLED])
    rig.client.script("lookup", lookup_result(3, position_id=5001, avg_price=100.12, units=2.0, fees=0.5))
    rig.ex.run_tick([])
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["position_id"], row["avg_price"], row["units_filled"], row["fees"]) == (
        "filled", 5001, 100.12, 2.0, 0.5)
    assert row["filled_at"] == NOW.isoformat()


def test_a_bearish_fill_sells_short_and_records_the_bid(rig):
    rig.plans["p1"] = _filled_plan(direction="bearish", stop_loss=105.0, tp1=98.0, tp2=95.0)
    rig.ex.run_tick([FILLED])
    body, _ = rig.client.calls[-1][1]
    assert (body["transaction"], body["stopLossRate"], body["takeProfitRate"]) == ("sellShort", 105.0, 95.0)
    assert rig.repo.row(OPEN_RID)["quote_at_send"] == 100.0


def test_a_runner_open_carries_no_take_profit(rig):
    rig.plans["p1"] = _filled_plan(tp2=None, tp1_fraction=0.5)
    rig.ex.run_tick([FILLED])
    assert "takeProfitRate" not in rig.client.calls[-1][1][0]


# --- stale fills (controller decision 2026-10-11) -----------------------------------

@pytest.mark.parametrize("age,sent", [
    (dt.timedelta(minutes=29, seconds=59), True), (dt.timedelta(minutes=30), True),
    (dt.timedelta(minutes=30, seconds=1), False), (dt.timedelta(days=2), False)])
def test_only_a_fill_at_most_30_minutes_old_opens(rig, age, sent):
    assert STALE_FILL_MINUTES == 30
    rig.plans["p1"] = _filled_plan(age=age)
    rig.ex.run_tick([FILLED])
    assert ("open_order" in rig.client.names()) is sent
    if not sent:
        row = rig.repo.row(OPEN_RID)
        assert (row["status"], row["skip_reason"]) == ("skipped", "stale_fill")
        assert rig.client.calls == []


@pytest.mark.parametrize("plan_kw", [
    dict(status=PlanStatus.CLOSED), dict(status=PlanStatus.CANCELLED), dict(status_history=[]),
    dict(status_history=[{"status": "ACTIVE", "reason": "x", "at": "not a time"}])])
def test_a_closed_plan_or_an_unknown_fill_time_is_stale(rig, plan_kw, caplog):
    rig.plans["p1"] = _filled_plan(**plan_kw)
    rig.ex.enqueue([FILLED])
    with caplog.at_level(logging.INFO, logger=LOGGER):
        _advance(rig)
    assert rig.repo.row(OPEN_RID)["skip_reason"] == "stale_fill"
    assert rig.client.calls == []
    assert "etoro mirror skipped (stale_fill): AAPL p1" in caplog.text


def test_a_plan_gone_from_the_store_is_stale(rig):
    rig.ex.enqueue([FILLED])
    del rig.plans["p1"]
    _advance(rig)
    assert rig.repo.row(OPEN_RID)["skip_reason"] == "stale_fill"


def test_fill_time_reads_the_latest_active_entry():
    plan = _plan(status_history=[
        {"status": "ACTIVE", "reason": "stop_entry_fill", "at": "2026-10-12T14:00:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1", "at": "2026-10-12T14:30:00+00:00"}])
    assert fill_time(plan) == dt.datetime(2026, 10, 12, 14, 0, tzinfo=dt.timezone.utc)
    naive = _plan(status_history=[{"status": "ACTIVE", "reason": "x", "at": "2026-10-12T14:00:00"}])
    assert fill_time(naive).tzinfo is not None
    assert is_fresh_fill(_filled_plan(status=PlanStatus.PARTIAL), NOW) is True
    assert is_fresh_fill(None, NOW) is False


# --- checks, sizing, quotes ------------------------------------------------------

def test_a_failed_check_skips_with_its_reason_and_never_sends(rig, caplog):
    rig.seen.verdict = "portfolio_heat"
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rig.ex.run_tick([FILLED])
    assert "open_order" not in rig.client.names()
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["skip_reason"], row["plan_units"]) == ("skipped", "portfolio_heat", 10.0)
    assert "etoro mirror skipped (portfolio_heat): AAPL p1" in caplog.text


def test_no_size_from_the_sizer_is_zero_units(rig):
    rig.ex._sizer = lambda entry, stop: None
    rig.ex.run_tick([FILLED])
    assert rig.repo.row(OPEN_RID)["skip_reason"] == "zero_units"
    assert rig.seen.opens == [] and "open_order" not in rig.client.names()


def test_an_ineligible_symbol_reaches_check_open_without_a_quote_read(rig, monkeypatch):
    monkeypatch.setattr(checks, "parse_eligibility", lambda body, symbol, direction: None)
    rig.seen.verdict = "ineligible"
    rig.ex.run_tick([FILLED])
    assert rig.client.names() == ["eligibility"]
    assert rig.seen.opens[0].eligibility is None
    assert rig.repo.row(OPEN_RID)["skip_reason"] == "ineligible"


@pytest.mark.parametrize("method,result", [
    ("eligibility", ClientResult(503, "down")), ("eligibility", ClientResult(0, error="Timeout: x")),
    ("rates", ClientResult(500, None)), ("rates", ClientResult(200, {"results": []}))])
def test_a_failed_read_leaves_the_open_queued_for_the_next_tick(rig, method, result):
    rig.client.script(method, result)
    rig.ex.run_tick([FILLED])
    assert "open_order" not in rig.client.names()
    assert rig.repo.row(OPEN_RID)["status"] == "queued"
    rig.ex.run_tick([])
    assert rig.client.names().count("open_order") == 1


def test_the_heat_book_holds_the_mirror_open_positions(rig):
    _filled_open(rig, "p2", ticker="MSFT", position_id=5002, avg_price=50.0, stop_sent=48.0)
    rig.ex.run_tick([FILLED])
    [call] = rig.seen.opens
    assert [trade["ticker"] for trade in call.book.open_trades] == ["MSFT"]
    assert rig.markets == [["AAPL", "MSFT"]]
    assert call.book.sectors == {"AAPL": "Technology"}


def test_an_empty_book_fetches_no_market_data(rig):
    rig.ex.run_tick([FILLED])
    assert rig.markets == []
    assert rig.seen.opens[0].book.open_trades == ()


# --- ordering, deferral, budget ------------------------------------------------

def test_a_follower_waits_for_its_open_across_ticks(rig):
    rig.ex.run_tick([FILLED])
    rig.repo.seed("p1", "move_stop", "100.0000", "queued", stop_sent=100.0)
    rig.client.script("lookup", lookup_result(11), lookup_result(11))
    rig.ex.run_tick([])
    rig.ex.run_tick([])
    assert "update_stop" not in rig.client.names()
    rig.ex.run_tick([])
    assert rig.client.names()[-2:] == ["lookup", "update_stop"]
    assert rig.repo.row(request_id_for("p1", "move_stop", "100.0000"))["status"] == "filled"


def test_a_bucket_deferral_requeues_for_the_next_tick(rig):
    rig.client.script("open_order", ClientResult(0, deferred=True))
    rig.ex.run_tick([FILLED])
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["not_before"]) == ("queued", NOW.isoformat())
    rig.ex.run_tick([])
    assert rig.client.names().count("open_order") == 2
    assert rig.repo.row(OPEN_RID)["status"] == "in_flight"


@pytest.mark.parametrize("retry_after,wait_s", [(30.0, 30), (None, 60)])
def test_a_429_waits_for_retry_after(rig, retry_after, wait_s):
    now = [NOW]
    rig.ex._now = lambda: now[0]
    rig.client.script("open_order", ClientResult(429, {}, retry_after=retry_after))
    rig.ex.run_tick([FILLED])
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["not_before"]) == (
        "queued", (NOW + dt.timedelta(seconds=wait_s)).isoformat())
    now[0] = NOW + dt.timedelta(seconds=wait_s - 1)
    rig.ex.run_tick([])
    assert rig.client.names().count("open_order") == 1
    now[0] = NOW + dt.timedelta(seconds=wait_s)
    rig.ex.run_tick([])
    assert rig.client.names().count("open_order") == 2


def test_the_send_budget_leaves_the_rest_queued(rig):
    rig.ex.client = rig.client = FakeClient(rig.clock, step_s=8.0)
    for n in range(1, 5):
        _filled_open(rig, f"p{n}", position_id=5000 + n)
        rig.repo.seed(f"p{n}", "move_stop", "100.0000", "queued", stop_sent=100.0)
    rig.ex.run_tick([])
    assert rig.client.names() == ["update_stop"] * 3
    assert [row["status"] for row in rig.repo.rows if row["action"] == "move_stop"] == [
        "filled", "filled", "filled", "queued"]


def test_an_error_in_one_plan_does_not_stop_the_others(rig, monkeypatch, caplog):
    _filled_open(rig, "p0", position_id=5000)
    rig.repo.seed("p0", "close_all", "closed", "queued")

    def _boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(rig.client, "close_position", _boom)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        rig.ex.run_tick([FILLED])
    assert "open_order" in rig.client.names()
    assert "boom" in caplog.text


# --- outcomes -------------------------------------------------------------------

@pytest.mark.parametrize("result,code", [
    (ClientResult(400, {"errorCode": 720, "errorMessage": "bad units"}), 720),
    (ClientResult(422, {"message": "nope"}), 422)])
def test_a_refused_open_is_rejected_and_never_retried(rig, result, code):
    rig.client.script("open_order", result)
    rig.ex.run_tick([FILLED])
    rig.ex.run_tick([])
    assert rig.client.names().count("open_order") == 1
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["error_code"]) == ("rejected", code)


def test_401_rejects_and_warns_once_naming_the_scope(rig, caplog):
    rig.plans["p2"] = _filled_plan(plan_id="p2")
    rig.client.script("open_order", ClientResult(401, {}), ClientResult(401, {}))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        rig.ex.run_tick([FILLED, PlanEvent("p2", "filled", {})])
    assert [row["status"] for row in rig.repo.rows] == ["rejected", "rejected"]
    assert caplog.text.count("demo:write") == 1


def test_a_rejected_lookup_records_the_error(rig):
    rig.ex.run_tick([FILLED])
    rig.client.script("lookup", lookup_result(4, error_code=747, error_message="market closed"))
    rig.ex.run_tick([])
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["error_code"], row["error_message"]) == ("rejected", 747, "market closed")


@pytest.mark.parametrize("result", [
    ClientResult(409, {}), ClientResult(400, {"errorCode": 631}),
    ClientResult(400, {"status": {"errorCode": 632}})])
def test_a_close_on_a_closed_position_is_closed_by_broker(rig, result):
    _filled_open(rig)
    rig.repo.seed("p1", "close_all", "closed", "queued")
    rig.client.script("close_position", result)
    rig.ex.run_tick([])
    assert rig.repo.row(CLOSE_RID)["status"] == "closed_by_broker"


def test_a_close_rejected_at_lookup_with_631_is_closed_by_broker(rig):
    _filled_open(rig)
    rig.repo.seed("p1", "close_all", "closed", "queued")
    rig.ex.run_tick([])
    assert rig.repo.row(CLOSE_RID)["status"] == "in_flight"
    rig.client.script("lookup", lookup_result(4, error_code=631))
    rig.ex.run_tick([])
    assert rig.repo.row(CLOSE_RID)["status"] == "closed_by_broker"


def test_a_stop_move_fills_on_202_and_is_closed_by_broker_on_409(rig):
    _filled_open(rig)
    first = rig.repo.seed("p1", "move_stop", "100.0000", "queued", stop_sent=100.0)
    rig.ex.run_tick([])
    assert rig.client.calls == [("update_stop", (5001, 100.0, first["request_id"]))]
    assert rig.repo.row(first["request_id"])["status"] == "filled"
    second = rig.repo.seed("p1", "move_stop", "101.0000", "queued", stop_sent=101.0)
    rig.client.script("update_stop", ClientResult(409, {}))
    rig.ex.run_tick([])
    assert rig.repo.row(second["request_id"])["status"] == "closed_by_broker"
    assert "lookup" not in rig.client.names()


@pytest.mark.parametrize("result", [ClientResult(0, error="Timeout: read timed out"),
                                    ClientResult(502, "bad gateway")])
def test_an_unanswered_send_stays_sending(rig, result):
    rig.client.script("open_order", result)
    rig.ex.run_tick([FILLED])
    assert rig.repo.row(OPEN_RID)["status"] == "sending"


# --- recovery ----------------------------------------------------------------

def test_a_stuck_sending_row_is_looked_up_before_any_resend(rig):
    rig.repo.seed("p1", "open", "filled", "sending", stop_sent=95.0)
    rig.ex.run_tick([])
    assert rig.client.calls == [("lookup", (OPEN_RID,))]
    row = rig.repo.row(OPEN_RID)
    assert (row["status"], row["position_id"]) == ("filled", 5001)


def test_a_sending_row_eToro_never_saw_is_resent_with_the_same_id(rig):
    rig.repo.seed("p1", "open", "filled", "sending", stop_sent=95.0)
    rig.client.script("lookup", ClientResult(404, {}))
    rig.ex.run_tick([])
    assert rig.repo.row(OPEN_RID)["status"] == "queued"
    assert "open_order" not in rig.client.names()
    rig.ex.run_tick([])
    assert rig.client.calls[-1][0] == "open_order"
    assert rig.client.calls[-1][1][1] == OPEN_RID


def test_a_stuck_stop_move_is_resent_without_a_lookup(rig):
    _filled_open(rig)
    rig.repo.seed("p1", "move_stop", "100.0000", "sending", stop_sent=100.0)
    rig.ex.run_tick([])
    rig.ex.run_tick([])
    assert rig.client.names() == ["update_stop"]


# --- followers ---------------------------------------------------------------

def test_close_units_closes_the_rounded_fraction(rig):
    _filled_open(rig, units_filled=3.0)
    row = rig.repo.seed("p1", "close_units", "tp1_partial", "queued", fraction=0.5)
    rig.ex.run_tick([])
    assert rig.client.calls == [("close_position", (5001, 1001, 1.0, row["request_id"]))]
    stored = rig.repo.row(row["request_id"])
    assert (stored["status"], stored["units_requested"]) == ("in_flight", 1.0)
    assert stored["fraction_closed"] == pytest.approx(1 / 3)


def test_close_units_that_round_to_nothing_are_skipped(rig):
    _filled_open(rig, units_filled=1.0)
    row = rig.repo.seed("p1", "close_units", "tp1_partial", "queued", fraction=0.5)
    rig.ex.run_tick([])
    assert rig.client.calls == []
    assert rig.repo.row(row["request_id"])["skip_reason"] == "zero_units"


def test_close_all_closes_the_whole_position(rig):
    _filled_open(rig)
    rig.repo.seed("p1", "close_all", "closed", "queued")
    rig.ex.run_tick([])
    assert rig.client.calls == [("close_position", (5001, 1001, None, CLOSE_RID))]


@pytest.mark.parametrize("open_status", ["rejected", "skipped"])
def test_a_follower_of_a_dead_open_is_no_position(rig, open_status, caplog):
    rig.repo.seed("p1", "open", "filled", open_status)
    rig.repo.seed("p1", "close_all", "closed", "queued")
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rig.ex.run_tick([])
    assert rig.client.calls == []
    row = rig.repo.row(CLOSE_RID)
    assert (row["status"], row["skip_reason"]) == ("skipped", "no_position")
    assert "etoro mirror skipped (no_position): AAPL p1" in caplog.text


# --- tick plumbing ---------------------------------------------------------

def test_every_final_status_reaches_the_after_final_hook(rig, monkeypatch):
    finals = []
    monkeypatch.setattr(rig.ex, "_after_final", finals.append)
    rig.ex.run_tick([FILLED])
    rig.ex.run_tick([])
    assert [(row["action"], row["status"], row["position_id"]) for row in finals] == [
        ("open", "filled", 5001)]


def test_run_tick_asserts_demo_and_accepts_none(rig, demo_calls):
    rig.ex.run_tick(None)
    assert demo_calls == ["demo"]


def test_a_tick_that_finds_the_previous_one_running_does_nothing(rig):
    rig.ex._lock.acquire()
    try:
        rig.ex.run_tick([FILLED])
    finally:
        rig.ex._lock.release()
    assert rig.repo.rows == [] and rig.client.calls == []


def test_get_executor_is_a_process_singleton(monkeypatch):
    monkeypatch.setattr(executor, "_EXECUTOR", None)
    first = get_executor()
    assert first is get_executor()
    assert isinstance(first.client, EtoroClient)
    assert first.repo is broker_orders_repo()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_executor.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'swingbot.core.broker.executor'`.

