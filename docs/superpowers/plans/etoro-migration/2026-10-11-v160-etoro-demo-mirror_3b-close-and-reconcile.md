# v160 eToro demo mirror, part 3b: close-time persistence and daily reconciliation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task EM9" -A 600 <this file>`; never read the plan whole.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Executor rules "At close", § Daily reconciliation, § Testing "close-time persistence")
**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md` carries the Global Constraints, the `## Parallelisation` table and the task ledger; every task below implicitly includes them. This file holds **EM9**, which the index assigns to part 3; it lives here because EM8 alone brings `_3-executor.md` to the 1500-line cap. The conventions block and part-local constraints at the top of `_3-executor.md` (worktree `WT`, never `cd`, fakes only, auth warnings once per scope) apply here too.

**Shell variables used in every task** (Git Bash; never `cd`):

```bash
REPO="E:/Documents/Private/Projects/Discord-Bot"
WT="$REPO/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror"
```

## Parallelisation (this file)

EM9 after EM8: same file (`swingbot/core/broker/executor.py`), and it fills EM8's `_after_final` hook. It may run beside EM11 (part 4), which only reads the row contract. EM10 (part 4) waits for EM9 because `run_tick` must be complete before the hook calls it.

# Phase 4 (continued): close persistence and reconciliation

### Task EM9: Close-time persistence and daily reconciliation

**Model:** opus — fills the executor's final-status hook and adds a once-a-day job keyed on the ET session calendar and a persisted date; a wrong trigger double-runs or silently skips, and the persisted economics feed every net-R figure in the parity report.

Spec § Executor rules ("At close: when a position's last close fills, or is found `closed_by_broker`, the executor pulls that trade from trading history and **persists** `net_profit`, `fees` and overnight cost into the row. The report never re-reads mutable live routes."), § Daily reconciliation (first trade-monitor tick after 16:15 ET each NYSE session, `session.market_today()`, last-run date through `scheduled_repo()`, compare demo positions with the repository's `filled` still-open rows, log missing-either-side / unit / stop mismatches at WARNING, **nothing corrected**), § Testing ("close-time persistence"). Index § Global Constraints (logging contract, never `StoreWriteHalt`, no network in the suite).

What this task adds:

1. **Close economics.** `_after_final(row)` (EM8's no-op hook) runs on every final status. When the row is a plan's closing row (a `close_all` that ended `filled`, or any row that ended `closed_by_broker`), it reads the trade history pages from the open's fill date (`HISTORY_PAGE_SIZE = 200` per page, at most `HISTORY_MAX_PAGES = 10`, stopping at the first short page), merges every history entry for the open row's `position_id` (`history_item`; a position closed in parts may be booked as more than one entry, so money fields are summed and the latest `closeTimestamp`'s `closeRate` is kept), and writes `close_economics(item)` plus `history_pending: False` into that row **without changing its status**. Exactly one closing row per plan holds the economics: a row is not persisted when another row of the plan already holds `net_profit` or `history_pending`.
2. **Not in history yet.** A close can reach history after its lookup says filled. If no entry matches, or the history read fails, the row gets `history_pending: True` and one WARNING; the daily reconciliation retries every pending row.
3. **Daily reconciliation.** `maybe_reconcile(now=None)` runs at the end of every `run_tick` whose send budget is not spent. It returns `False` at once unless `now_et(now).time() >= RECONCILE_AFTER_ET` (16:15) on an NYSE session day (`nyse_calendar().is_session`) not yet reconciled: a process-local date first, then `scheduled_repo().fired_on(RECONCILE_JOB)` (the persisted ET date, ISO). It reads the demo portfolio; on failure it returns `False` without marking, so the next tick retries. On success it logs one WARNING per `reconcile_findings` entry over the open rows (each enriched with `expected_units` = `units_filled` minus filled `close_units` `units_requested`, and `expected_stop` = the highest-`seq` filled `open`/`move_stop` row's `stop_sent`), retries pending closes, then marks the day (`scheduled_repo().mark(RECONCILE_JOB, day.isoformat())`) and returns `True`. Nothing is ever sent or corrected.

Row doc fields this task writes (flat record keys, closing rows only): `net_profit`, `fees`, `overnight_fees` (eToro's `overnightFees`, else `None`), `close_rate`, `closed_at` (eToro's `closeTimestamp`), `history_pending`.

**Files:**
- Modify: `swingbot/core/broker/executor.py`
- Create: `tests/broker/test_executor_close_and_reconcile.py`

**Interfaces:**
- Consumes:
  - EM8 `swingbot/core/broker/executor.py`: `Executor` with `run_tick`, `advance`, `_open_row(plan_id) -> dict | None`, `_store_problem(what, plan_id, exc)`, `_read_failed(result, scope, who)`, `_now()`, `self.client`, `self.repo`, `self._clock`; module helpers `_float`, `_int_or_none`, `_parse_time`, `_who`, `READ_SCOPE`, `SEND_BUDGET_S`, `request_id_for`.
  - EM8 `tests/broker/fakes.py`: `FakeClient(clock=None, step_s=0.0)` (`.script`, `.calls`, `.names()`; default `history` reply `ClientResult(200, [])`, default `portfolio` reply `{"clientPortfolio": {"positions": []}}`), `FakeRepo` (`.seed`, `.row`), `FakePlans`, `ManualClock`, `db_down`.
  - EM6 `mirror.ACTION_OPEN`, `ACTION_CLOSE_UNITS`, `ACTION_CLOSE_ALL`, `ACTION_MOVE_STOP`.
  - EM7 `EtoroClient.portfolio() -> ClientResult` (`clientPortfolio.positions[].positionID`, `.units`, `.stopLossRate`, `.instrumentID`) and `history(min_date: str, page: int = 1, page_size: int = 200) -> ClientResult` (a list of `positionId`, `closeRate`, `closeTimestamp`, `netProfit`, `fees`, `units`, optionally `overnightFees`).
  - `swingbot.core.market.session.now_et(now) -> datetime` (`session.py:30`, aware ET), `nyse_calendar() -> SessionCalendar` with `.is_session(d: date) -> bool` (`session.py:235`, `:172`).
  - `swingbot.core.db.repositories.scheduled.scheduled_repo()` with `fired_on(job) -> str | None` and `mark(job, date_iso)` (`scheduled.py:12`, `:16`), imported lazily inside the methods so tests patch the module attribute.
- Produces (EM10 calls `run_tick`; EM11/EM12 read the persisted fields):
  - `RECONCILE_JOB = "etoro_reconcile"`, `RECONCILE_AFTER_ET = datetime.time(16, 15)`, `HISTORY_PAGE_SIZE = 200`, `HISTORY_MAX_PAGES = 10`, `HISTORY_LOOKBACK_DAYS = 30`, `UNIT_TOLERANCE = 1e-4`, `RATE_TOLERANCE = 1e-4`.
  - `history_item(body: object, position_id: int) -> dict | None` (keys `positionId`, `closeRate`, `closeTimestamp`, `netProfit`, `fees`, `overnightFees`, `units`; accepts a list, or a dict wrapping one list).
  - `close_economics(item: dict) -> dict` (`{"net_profit", "fees", "overnight_fees", "close_rate", "closed_at"}`).
  - `reconcile_findings(portfolio_body: object, open_rows: list[dict]) -> list[str]` (row keys `plan_id`, `ticker`, `position_id`, `units_filled`, `stop_sent`, optional `expected_units`, `expected_stop`).
  - `Executor._after_final(row)` implemented; `Executor.maybe_reconcile(now: datetime | None = None) -> bool`; `run_tick` calls it last when the budget is not spent.

- [ ] **Step 1: Confirm EM8 is on the branch**

```bash
git -C "$WT" grep -n "def _after_final\|def _open_row\|def _read_failed\|def get_executor" -- swingbot/core/broker/executor.py
git -C "$WT" grep -n "class FakeRepo\|def seed" -- tests/broker/fakes.py
```

Expected: 4 hits, then 2 hits. Anything missing: stop with `BLOCKED: EM9 needs EM8`.

- [ ] **Step 2: Write the failing tests**

Create `tests/broker/test_executor_close_and_reconcile.py`:

```python
"""v160 EM9: close-time persistence and the daily reconciliation.

Fake client, in-memory repository and a fake scheduled-jobs store: no
Postgres, no network. Times are UTC; 2026-10-12 is a Monday (EDT, UTC-4).
"""
import datetime as dt
import logging
from types import SimpleNamespace

import pytest

from swingbot.core.broker import executor, guard
from swingbot.core.broker.etoro_client import ClientResult
from swingbot.core.broker.executor import (
    RECONCILE_AFTER_ET, RECONCILE_JOB, Executor, close_economics, history_item,
    reconcile_findings, request_id_for)
from swingbot.core.db.repositories import scheduled
from tests.broker.fakes import FakeClient, FakePlans, FakeRepo, ManualClock, db_down

LOGGER = "swingbot.core.broker.executor"
MON_1100_ET = dt.datetime(2026, 10, 12, 15, 0, tzinfo=dt.timezone.utc)
MON_1614_ET = dt.datetime(2026, 10, 12, 20, 14, tzinfo=dt.timezone.utc)
MON_1620_ET = dt.datetime(2026, 10, 12, 20, 20, tzinfo=dt.timezone.utc)
SAT_1700_ET = dt.datetime(2026, 10, 17, 21, 0, tzinfo=dt.timezone.utc)
CLOSE_RID = request_id_for("p1", "close_all", "closed")
STOP_RID = request_id_for("p1", "move_stop", "100.0000")
TRADE = {"positionId": 5001, "closeRate": 104.0, "closeTimestamp": "2026-10-12T19:00:00Z",
         "netProfit": 7.5, "fees": 0.4, "units": 2.0}
OTHER = {**TRADE, "positionId": 9999, "netProfit": -3.0}
ROW = {"plan_id": "p1", "ticker": "AAPL", "position_id": 5001, "units_filled": 2.0,
       "stop_sent": 95.0}
POS = {"positionID": 5001, "units": 2.0, "stopLossRate": 95.0, "isBuy": True,
       "instrumentID": 1001}


def _portfolio(*positions):
    return {"clientPortfolio": {"positions": list(positions)}}


class FakeScheduled:
    def __init__(self):
        self.fired: dict[str, str] = {}
        self.marks: list[tuple[str, str]] = []
        self.fail_read = False

    def fired_on(self, job, *, conn=None):
        if self.fail_read:
            raise db_down()
        return self.fired.get(job)

    def mark(self, job, date_iso, *, conn=None):
        self.marks.append((job, date_iso))
        self.fired[job] = date_iso


@pytest.fixture(autouse=True)
def demo_ok(monkeypatch):
    monkeypatch.setattr(guard, "assert_demo", lambda account: None)
    monkeypatch.setattr(executor, "_AUTH_WARNED", set())


@pytest.fixture
def jobs(monkeypatch):
    store = FakeScheduled()
    monkeypatch.setattr(scheduled, "scheduled_repo", lambda: store)
    return store


@pytest.fixture
def rig(jobs):
    clock, now = ManualClock(), [MON_1100_ET]
    client, repo = FakeClient(clock), FakeRepo()
    ex = Executor(client, repo, FakePlans(), clock=clock, now_fn=lambda: now[0],
                  sizer=lambda entry, stop: None, market=lambda tickers: ({}, None))
    return SimpleNamespace(ex=ex, client=client, repo=repo, clock=clock, now=now, jobs=jobs)


def _open(rig, plan_id="p1", position_id=5001, **doc):
    base = dict(position_id=position_id, instrument_id=1001, unit_decimals=0,
                units_filled=2.0, avg_price=100.1, stop_sent=95.0,
                filled_at="2026-10-12T14:30:00+00:00")
    base.update(doc)
    return rig.repo.seed(plan_id, "open", "filled", "filled", **base)


# --- history parsing (pure) -----------------------------------------------------

def test_history_item_finds_the_position_and_ignores_the_rest():
    item = history_item([OTHER, TRADE], 5001)
    assert (item["netProfit"], item["fees"], item["closeRate"], item["units"]) == (7.5, 0.4, 104.0, 2.0)
    assert item["overnightFees"] is None
    assert history_item([OTHER], 5001) is None


@pytest.mark.parametrize("body", [None, "x", 7, {"a": 1}, [None, "x"]])
def test_history_item_survives_an_unreadable_body(body):
    assert history_item(body, 5001) is None


def test_history_item_accepts_a_dict_wrapping_the_list():
    assert history_item({"page": 1, "results": [TRADE]}, 5001)["netProfit"] == 7.5


def test_a_position_closed_in_parts_is_merged():
    first = {**TRADE, "netProfit": 3.0, "fees": 0.2, "closeRate": 102.0, "units": 1.0,
             "closeTimestamp": "2026-10-12T15:00:00Z"}
    last = {**TRADE, "netProfit": 4.5, "fees": 0.2, "overnightFees": 0.1, "units": 1.0}
    item = history_item([last, first], 5001)
    assert item["netProfit"] == pytest.approx(7.5)
    assert item["fees"] == pytest.approx(0.4)
    assert (item["overnightFees"], item["units"], item["closeRate"]) == (0.1, 2.0, 104.0)
    assert item["closeTimestamp"] == "2026-10-12T19:00:00Z"


def test_close_economics_maps_the_fields():
    assert close_economics(TRADE) == {"net_profit": 7.5, "fees": 0.4, "overnight_fees": None,
                                      "close_rate": 104.0, "closed_at": "2026-10-12T19:00:00Z"}
    assert close_economics({**TRADE, "overnightFees": 0.3})["overnight_fees"] == 0.3
    assert close_economics({**TRADE, "netProfit": "n/a"})["net_profit"] is None


# --- reconcile_findings (pure) -----------------------------------------------------

def test_reconcile_findings_is_empty_when_everything_matches():
    assert reconcile_findings(_portfolio(POS), [ROW]) == []


def test_reconcile_findings_names_each_kind_of_drift():
    assert reconcile_findings(_portfolio(), [ROW]) == [
        "AAPL p1: position 5001 is open in broker_orders but not on eToro"]
    assert reconcile_findings(_portfolio(POS), []) == [
        "position 5001 (instrument 1001) is on eToro with no open mirror row"]
    assert reconcile_findings(_portfolio({**POS, "units": 3.0}), [ROW]) == [
        "AAPL p1: units 3.0 on eToro, 2.0 expected"]
    assert reconcile_findings(_portfolio({**POS, "stopLossRate": 90.0}), [ROW]) == [
        "AAPL p1: stop 90.0 on eToro, 95.0 expected"]


def test_reconcile_findings_prefers_the_expected_units_and_stop():
    row = {**ROW, "expected_units": 1.0, "expected_stop": 100.0}
    assert reconcile_findings(_portfolio({**POS, "units": 1.0, "stopLossRate": 100.0}), [row]) == []


@pytest.mark.parametrize("body", [None, "x", {}, {"clientPortfolio": {}},
                                  {"clientPortfolio": {"positions": "x"}}])
def test_an_unreadable_portfolio_is_one_finding(body):
    assert reconcile_findings(body, [ROW]) == [
        "portfolio response has no clientPortfolio.positions list"]


# --- close-time persistence ----------------------------------------------------------

def test_a_filled_close_all_persists_the_trade_economics(rig, caplog):
    _open(rig)
    rig.repo.seed("p1", "close_all", "closed", "in_flight")
    rig.client.script("history", ClientResult(200, [OTHER, TRADE]))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        rig.ex.run_tick([])
    assert rig.client.calls[-1] == ("history", ("2026-10-12", 1, 200))
    row = rig.repo.row(CLOSE_RID)
    assert row["status"] == "filled"
    assert (row["net_profit"], row["fees"], row["overnight_fees"]) == (7.5, 0.4, None)
    assert (row["close_rate"], row["closed_at"], row["history_pending"]) == (
        104.0, "2026-10-12T19:00:00Z", False)
    assert "etoro mirror close persisted: AAPL p1" in caplog.text


def test_a_stop_move_closed_by_broker_persists_on_that_row(rig):
    _open(rig)
    rig.repo.seed("p1", "move_stop", "100.0000", "queued", stop_sent=100.0)
    rig.client.script("update_stop", ClientResult(409, {}))
    rig.client.script("history", ClientResult(200, [TRADE]))
    rig.ex.run_tick([])
    assert rig.client.names() == ["update_stop", "history"]
    row = rig.repo.row(STOP_RID)
    assert (row["status"], row["net_profit"]) == ("closed_by_broker", 7.5)


def test_an_open_fill_or_a_partial_close_reads_no_history(rig):
    _open(rig)
    rig.repo.seed("p1", "close_units", "tp1_partial", "in_flight", units_requested=1.0)
    rig.repo.seed("p2", "open", "filled", "in_flight", stop_sent=95.0)
    rig.ex.run_tick([])
    assert rig.client.names() == ["lookup", "lookup"]


def test_a_second_closing_row_does_not_persist_again(rig):
    _open(rig)
    rig.repo.seed("p1", "move_stop", "100.0000", "closed_by_broker", net_profit=7.5)
    rig.repo.seed("p1", "close_all", "closed", "in_flight")
    rig.ex.run_tick([])
    assert rig.client.names() == ["lookup"]
    assert "net_profit" not in rig.repo.row(CLOSE_RID)


def test_the_history_window_falls_back_to_30_days_without_a_fill_date(rig):
    _open(rig, filled_at=None)
    rig.repo.seed("p1", "close_all", "closed", "in_flight")
    rig.ex.run_tick([])
    assert rig.client.calls[-1] == ("history", ("2026-09-12", 1, 200))


def test_history_is_paged_until_a_short_page(rig, monkeypatch):
    monkeypatch.setattr(executor, "HISTORY_PAGE_SIZE", 2)
    _open(rig)
    rig.repo.seed("p1", "close_all", "closed", "in_flight")
    rig.client.script("history", ClientResult(200, [OTHER, OTHER]), ClientResult(200, [TRADE]))
    rig.ex.run_tick([])
    assert [args for name, args in rig.client.calls if name == "history"] == [
        ("2026-10-12", 1, 2), ("2026-10-12", 2, 2)]
    assert rig.repo.row(CLOSE_RID)["net_profit"] == 7.5


@pytest.mark.parametrize("reply", [ClientResult(200, []), ClientResult(503, "down")])
def test_a_close_missing_from_history_is_pending_and_retried_at_reconciliation(rig, reply, caplog):
    _open(rig)
    rig.repo.seed("p1", "close_all", "closed", "in_flight")
    rig.client.script("history", reply)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        rig.ex.run_tick([])
    row = rig.repo.row(CLOSE_RID)
    assert (row["status"], row["history_pending"]) == ("filled", True)
    assert "net_profit" not in row
    if reply.ok:
        assert "close not in trade history yet: AAPL p1" in caplog.text
    rig.now[0] = MON_1620_ET
    rig.client.script("history", ClientResult(200, [TRADE]))
    rig.ex.run_tick([])
    assert rig.client.names()[-2:] == ["portfolio", "history"]
    row = rig.repo.row(CLOSE_RID)
    assert (row["net_profit"], row["history_pending"]) == (7.5, False)


# --- daily reconciliation ---------------------------------------------------------

@pytest.mark.parametrize("now", [MON_1100_ET, MON_1614_ET, SAT_1700_ET])
def test_reconciliation_waits_for_1615_et_on_a_session_day(rig, now):
    assert (RECONCILE_JOB, RECONCILE_AFTER_ET) == ("etoro_reconcile", dt.time(16, 15))
    assert rig.ex.maybe_reconcile(now) is False
    assert rig.client.calls == [] and rig.jobs.marks == []


def test_reconciliation_runs_once_per_session_across_restarts(rig, caplog):
    _open(rig)
    rig.client.script("portfolio", ClientResult(200, _portfolio(POS)))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert rig.ex.maybe_reconcile(MON_1620_ET) is True
    assert rig.jobs.marks == [("etoro_reconcile", "2026-10-12")]
    assert "reconciliation" not in caplog.text
    assert rig.ex.maybe_reconcile(MON_1620_ET) is False
    restarted = Executor(rig.client, rig.repo, FakePlans(), clock=rig.clock,
                         now_fn=lambda: MON_1620_ET)
    assert restarted.maybe_reconcile() is False
    assert rig.client.names() == ["portfolio"]


def test_reconciliation_logs_every_mismatch_and_corrects_nothing(rig, caplog):
    _open(rig, "p1", 5001, units_filled=2.0, stop_sent=95.0)
    rig.repo.seed("p1", "close_units", "tp1_partial", "filled", units_requested=1.0)
    rig.repo.seed("p1", "move_stop", "100.0000", "filled", stop_sent=100.0)
    _open(rig, "p2", 5002)
    statuses = [row["status"] for row in rig.repo.rows]
    rig.client.script("portfolio", ClientResult(200, _portfolio(
        {**POS, "units": 1.0, "stopLossRate": 99.0},
        {**POS, "positionID": 5003, "units": 4.0, "stopLossRate": 10.0})))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert rig.ex.maybe_reconcile(MON_1620_ET) is True
    assert "etoro mirror reconciliation: AAPL p1: stop 99.0 on eToro, 100.0 expected" in caplog.text
    assert "AAPL p2: position 5002 is open in broker_orders but not on eToro" in caplog.text
    assert "position 5003 (instrument 1001) is on eToro with no open mirror row" in caplog.text
    assert "units" not in caplog.text
    assert rig.client.names() == ["portfolio"]
    assert [row["status"] for row in rig.repo.rows] == statuses


def test_a_failed_portfolio_read_does_not_mark_the_day(rig):
    rig.client.script("portfolio", ClientResult(503, "down"))
    assert rig.ex.maybe_reconcile(MON_1620_ET) is False
    assert rig.jobs.marks == []
    assert rig.ex.maybe_reconcile(MON_1620_ET) is True
    assert rig.jobs.marks == [("etoro_reconcile", "2026-10-12")]


def test_an_unreadable_reconcile_date_skips_without_a_portfolio_read(rig, caplog):
    rig.jobs.fail_read = True
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert rig.ex.maybe_reconcile(MON_1620_ET) is False
    assert rig.client.calls == []
    assert "store write failure" in caplog.text


def test_run_tick_reconciles_after_advancing_the_queue(rig):
    rig.now[0] = MON_1620_ET
    rig.repo.seed("p1", "open", "filled", "in_flight", stop_sent=95.0)
    rig.ex.run_tick([])
    assert rig.client.names() == ["lookup", "portfolio"]


def test_run_tick_defers_reconciliation_when_the_budget_is_spent(rig):
    rig.now[0] = MON_1620_ET
    rig.ex.client = rig.client = FakeClient(rig.clock, step_s=25.0)
    rig.repo.seed("p1", "open", "filled", "in_flight", stop_sent=95.0)
    rig.ex.run_tick([])
    assert rig.client.names() == ["lookup"]
    rig.ex.run_tick([])
    assert rig.client.names() == ["lookup", "portfolio"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_executor_close_and_reconcile.py`
Expected: FAIL, collection error `ImportError: cannot import name 'RECONCILE_AFTER_ET' from 'swingbot.core.broker.executor'`.

- [ ] **Step 4: Implement close persistence and the reconciliation**

All edits are in `swingbot/core/broker/executor.py`.

(a) Add one import after `from swingbot.core.db.repositories.broker_orders import FINAL_STATUSES`:

```python
from swingbot.core.market.session import now_et, nyse_calendar
```

(b) Add these constants directly after the `WRITE_SCOPE, READ_SCOPE, RATES_SCOPE = ...` line:

```python
RECONCILE_JOB = "etoro_reconcile"            # scheduled_jobs.job; fired_on = ET session date
RECONCILE_AFTER_ET = dt.time(16, 15)
HISTORY_PAGE_SIZE = 200
HISTORY_MAX_PAGES = 10
HISTORY_LOOKBACK_DAYS = 30                   # history window when the open has no fill date
UNIT_TOLERANCE = 1e-4
RATE_TOLERANCE = 1e-4
_NO_POSITIONS = "portfolio response has no clientPortfolio.positions list"
_STOP_ACTIONS = frozenset({mirror.ACTION_OPEN, mirror.ACTION_MOVE_STOP})
```

(c) Insert this block directly above the `# --- the executor ---` comment line:

```python
# --- close economics and reconciliation (pure) ----------------------------------------

def _history_items(body) -> list:
    """The catalog documents a list; a dict wrapping one list is tolerated."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return next((value for value in body.values() if isinstance(value, list)), [])
    return []


def _sum_field(items: list[dict], key: str) -> float | None:
    values = [_float(item.get(key)) for item in items]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def history_item(body: object, position_id: int) -> dict | None:
    """position_id's closed trade from history. A position closed in parts may be
    booked as several entries: money fields and units are summed, and the
    latest closeTimestamp's closeRate is kept. None when nothing matches."""
    matches = [item for item in _history_items(body)
               if isinstance(item, dict) and _int_or_none(item.get("positionId")) == position_id]
    if not matches:
        return None
    latest = max(matches, key=lambda item: str(item.get("closeTimestamp") or ""))
    return {"positionId": position_id, "closeRate": latest.get("closeRate"),
            "closeTimestamp": latest.get("closeTimestamp"),
            "netProfit": _sum_field(matches, "netProfit"), "fees": _sum_field(matches, "fees"),
            "overnightFees": _sum_field(matches, "overnightFees"),
            "units": _sum_field(matches, "units")}


def close_economics(item: dict) -> dict:
    """The fields persisted into a closing row; anything unreadable is None."""
    closed_at = item.get("closeTimestamp")
    return {"net_profit": _float(item.get("netProfit")), "fees": _float(item.get("fees")),
            "overnight_fees": _float(item.get("overnightFees")),
            "close_rate": _float(item.get("closeRate")),
            "closed_at": str(closed_at) if closed_at else None}


def _portfolio_positions(body) -> list | None:
    portfolio = body.get("clientPortfolio") if isinstance(body, dict) else None
    positions = portfolio.get("positions") if isinstance(portfolio, dict) else None
    return positions if isinstance(positions, list) else None


def _drift(row: dict, position: dict) -> list[str]:
    findings = []
    expected_units = _float(row.get("expected_units", row.get("units_filled")))
    units = _float(position.get("units"))
    if expected_units is None or units is None or abs(units - expected_units) > UNIT_TOLERANCE:
        findings.append(f"{_who(row)}: units {units} on eToro, {expected_units} expected")
    expected_stop = _float(row.get("expected_stop", row.get("stop_sent")))
    stop = _float(position.get("stopLossRate"))
    if expected_stop is None or stop is None or abs(stop - expected_stop) > RATE_TOLERANCE:
        findings.append(f"{_who(row)}: stop {stop} on eToro, {expected_stop} expected")
    return findings


def reconcile_findings(portfolio_body: object, open_rows: list[dict]) -> list[str]:
    """Every mismatch between the demo portfolio and the open mirror rows."""
    positions = _portfolio_positions(portfolio_body)
    if positions is None:
        return [_NO_POSITIONS]
    on_etoro = {_int_or_none(p.get("positionID")): p for p in positions
                if isinstance(p, dict) and _int_or_none(p.get("positionID")) is not None}
    findings, mirrored = [], set()
    for row in open_rows:
        position_id = _int_or_none(row.get("position_id"))
        mirrored.add(position_id)
        position = on_etoro.get(position_id)
        if position is None:
            findings.append(f"{_who(row)}: position {position_id} is open in broker_orders "
                            "but not on eToro")
        else:
            findings.extend(_drift(row, position))
    findings.extend(f"position {pid} (instrument {p.get('instrumentID')}) is on eToro "
                    "with no open mirror row" for pid, p in on_etoro.items() if pid not in mirrored)
    return findings


def _expected(opened: dict, plan_rows: list[dict]) -> dict:
    """The open row plus what eToro should hold: units after filled partial closes,
    and the stop of the highest-seq filled open/move_stop row."""
    closed = sum(_float(row.get("units_requested")) or 0.0 for row in plan_rows
                 if row["action"] == mirror.ACTION_CLOSE_UNITS and row["status"] == "filled")
    stops = [row for row in plan_rows if row["action"] in _STOP_ACTIONS
             and row["status"] == "filled" and row.get("stop_sent") is not None]
    stop = max(stops, key=lambda row: row["seq"])["stop_sent"] if stops else opened.get("stop_sent")
    return {**opened, "expected_units": (_float(opened.get("units_filled")) or 0.0) - closed,
            "expected_stop": stop}


def _is_closing(row: dict) -> bool:
    """The row that ends a position: close_all filled, or anything closed_by_broker."""
    return row["status"] == "closed_by_broker" or (
        row["action"] == mirror.ACTION_CLOSE_ALL and row["status"] == "filled")


def _holds_close(row: dict) -> bool:
    return row.get("net_profit") is not None or bool(row.get("history_pending"))


def _history_since(opened: dict, now: dt.datetime) -> str:
    filled = _parse_time(opened.get("filled_at"))
    day = filled.date() if filled else (now - dt.timedelta(days=HISTORY_LOOKBACK_DAYS)).date()
    return day.isoformat()
```

(d) In `Executor.__init__`, add as its last line:

```python
        self._reconciled_on: dt.date | None = None   # process-local fast path
```

(e) Replace `Executor.run_tick` with:

```python
    def run_tick(self, events: list) -> None:
        guard.assert_demo("demo")
        if not self._lock.acquire(blocking=False):
            log.info("etoro mirror: previous tick still running; skipping this one")
            return
        try:
            self.enqueue(list(events or []))
            deadline = self._clock() + SEND_BUDGET_S
            self.advance(deadline)
            if self._clock() < deadline:             # a spent budget defers it one tick
                self.maybe_reconcile()
        finally:
            self._lock.release()
```

(f) Replace EM8's no-op `_after_final` with these methods (still inside `class Executor`, before `get_executor`):

```python
    # close-time persistence -----------------------------------------------------------
    def _after_final(self, row: dict) -> None:
        """On a plan's closing row, persist the trade's economics from history."""
        if not _is_closing(row):
            return
        try:
            self._persist_close(row)
        except Exception as exc:
            self._store_problem("persist close", row["plan_id"], exc)

    def _persist_close(self, row: dict) -> None:
        others = [r for r in self.repo.for_plan(row["plan_id"]) if r["request_id"] != row["request_id"]]
        if any(_holds_close(other) for other in others):
            return                                   # one closing row per plan holds it
        opened = self._open_row(row["plan_id"])
        if opened is None:
            return
        position_id = int(opened["position_id"])
        item = self._history_for(position_id, _history_since(opened, self._now()))
        if item is None:
            log.warning("etoro mirror close not in trade history yet: %s position %s; "
                        "retried at the daily reconciliation", _who(row), position_id)
            changes = {"history_pending": True}
        else:
            changes = {**close_economics(item), "history_pending": False}
            log.info("etoro mirror close persisted: %s net_profit %s fees %s",
                     _who(row), changes["net_profit"], changes["fees"])
        self.repo.set_status(row["request_id"], row["status"], changes)   # status unchanged
        row.update(changes)

    def _history_for(self, position_id: int, min_date: str) -> dict | None:
        items = []
        for page in range(1, HISTORY_MAX_PAGES + 1):
            result = self.client.history(min_date, page, HISTORY_PAGE_SIZE)
            if not result.ok:
                self._read_failed(result, READ_SCOPE, f"history position {position_id}")
                return None
            batch = _history_items(result.body)
            items.extend(batch)
            if len(batch) < HISTORY_PAGE_SIZE:
                break
        return history_item(items, position_id)

    def _retry_pending_closes(self) -> None:
        for row in self.repo.with_status(("filled", "closed_by_broker")):
            if not row.get("history_pending"):
                continue
            try:
                self._persist_close(row)
            except Exception as exc:
                self._store_problem("persist close", row["plan_id"], exc)

    # daily reconciliation ---------------------------------------------------------------
    def maybe_reconcile(self, now: dt.datetime | None = None) -> bool:
        """Once per NYSE session, first tick at or after 16:15 ET: log every
        portfolio/row mismatch at WARNING. Corrects nothing. The day is marked
        only after a successful portfolio read, so a failure retries next tick."""
        day = self._reconcile_day(now or self._now())
        if day is None:
            return False
        result = self.client.portfolio()
        if not result.ok:
            self._read_failed(result, READ_SCOPE, "reconciliation")
            return False
        try:
            self._reconcile(result.body)
        except Exception as exc:
            self._store_problem("reconciliation", RECONCILE_JOB, exc)
            return False
        self._mark_reconciled(day)
        return True

    def _reconcile_day(self, now: dt.datetime) -> dt.date | None:
        """The ET session date when a reconciliation is due, else None."""
        et = now_et(now)
        day = et.date()
        if (et.time() < RECONCILE_AFTER_ET or self._reconciled_on == day
                or not nyse_calendar().is_session(day)):
            return None
        from swingbot.core.db.repositories.scheduled import scheduled_repo
        try:
            fired = scheduled_repo().fired_on(RECONCILE_JOB)
        except Exception as exc:
            self._store_problem("read reconcile date", RECONCILE_JOB, exc)
            return None
        if fired == day.isoformat():
            self._reconciled_on = day
            return None
        return day

    def _reconcile(self, body) -> None:
        open_rows = [_expected(row, self.repo.for_plan(row["plan_id"]))
                     for row in self.repo.open_positions()]
        findings = reconcile_findings(body, open_rows)
        for finding in findings:
            log.warning("etoro mirror reconciliation: %s", finding)
        log.info("etoro mirror reconciliation done: %d open rows, %d findings",
                 len(open_rows), len(findings))
        self._retry_pending_closes()

    def _mark_reconciled(self, day: dt.date) -> None:
        self._reconciled_on = day
        from swingbot.core.db.repositories.scheduled import scheduled_repo
        try:
            scheduled_repo().mark(RECONCILE_JOB, day.isoformat())
        except Exception as exc:
            self._store_problem("mark reconcile date", RECONCILE_JOB, exc)
```

Two notes for the implementer. `test_reconciliation_runs_once_per_session_across_restarts` asserts that `"reconciliation"` is absent from WARNING output when nothing mismatches, so the "done" line stays at INFO. The time and calendar checks in `_reconcile_day` come before the `scheduled_repo()` read, so the EM8 tests (11:00 ET) never touch the store.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_executor_close_and_reconcile.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_executor.py`
Expected: PASS. EM8's tests run at 11:00 ET, so no reconciliation is due. The closing rows in EM8's tests now read the fake history (default `[]`), which marks them `history_pending` and asserts nothing about calls after the close.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/executor.py"`
Expected: no output. `reconcile_findings`, `_drift` and `_reconcile_day` are the busiest (B). If one reaches C, split it into a named helper without changing behaviour.

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add swingbot/core/broker/executor.py tests/broker/test_executor_close_and_reconcile.py
git -C "$WT" commit -m "feat(v160): EM9 -- broker executor: close economics and daily reconciliation

When a plan's position closes (close_all filled, or any row closed_by_broker)
the executor merges that position's trade-history entries and persists
net_profit, fees, overnight fees, close rate and time into the closing row,
so the parity report never re-reads live routes; a close not yet in history
is retried at the reconciliation. Once per NYSE session after 16:15 ET the
demo portfolio is compared with the open rows and every mismatch is logged
at WARNING; nothing is corrected. The date is persisted in scheduled_jobs.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
