# v160 eToro demo mirror: plan events become demo-account trades. Part 5: ops scripts (EM13–EM14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task EM13" -A 500 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Disable, drain and rollback, § Testing (the manual smoke script), § Rollout, § Panel review, § Risks (API drift))
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.
**Continued in** `..._5b-panel-and-full-suite.md` (EM15 complexity sweep and pre-close-out `/panel`, EM16 full suite), split off only to keep each file under 1500 lines.

**Conventions for every task in this part**

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror` (created in EM1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`, and run tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>`.
- `scripts/` is not a package. A script under `scripts/ops/` puts the repo root on `sys.path` itself (as `scripts/ops/data_sources_check.py` does), and its test imports it off `sys.path` (`sys.path.insert(0, str(ROOT / "scripts" / "ops"))`, as `tests/scripts/test_data_sources_check.py` does).
- **Both scripts touch eToro**, so v159's AST scan (`tests/broker/test_guard.py::unguarded_etoro_modules`, which walks `scripts/` too) requires each to call `assert_demo`: `main()` calls `guard.assert_demo("demo")` before anything else. Both tasks run `tests/broker/test_guard.py` to prove it.
- **No test calls eToro.** Both scripts take the client as an argument; tests pass `tests/broker/fakes.py::FakeClient` (EM8) and never build an `EtoroClient` with a real session.
- Every new function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for the new files.

## Part-local constraints

- **The drain writes rows the executor understands.** Its one action is `close_all` with `event_key = "drain"` and `request_id = executor.request_id_for(plan_id, "close_all", "drain")` (index § Global Constraints, Idempotency). It follows the executor's "no row, no send" order: the row is inserted and set `sending` before the request. Status mapping is the executor's (EM8): 2xx → `in_flight` with `order_id`, then looked up; lookup 3/5/9 → `filled`, 4/7/8/10 → `rejected` (error code 631/632 → `closed_by_broker`); `409` or body error code 631/632 → `closed_by_broker`; bucket deferral or `429` → `queued`; status 0 or `>= 500` → stays `sending` (a re-run looks it up first, never resends blind). A drained close carries no close economics (EM9's `_after_final` runs only inside the executor), so the parity report shows that trade's gross R as `None`; that is the accepted cost of a rollback path.
- **`--execute` refuses while the mirror is on.** With `ETORO_MIRROR_ENABLED` true, the live executor may be sending the same plan's own `close_all` in the same minute; the script exits 2 and says to switch the flag off (and SIGHUP) first. Dry run works either way and needs no keys.
- **The smoke script writes no `broker_orders` row.** It is a manual probe of the routes, not a mirror trade, so the parity report never counts it. Its request ids are fresh `uuid4`s, so they can never collide with a mirror id. It reuses `executor.open_body` and `checks.parse_eligibility`, so it probes exactly the body the mirror sends.
- **The smoke script runs only in US regular hours.** A market order outside them sits `WaitingForMarket` and would open after the script gave up, leaving a position nobody closes; `main()` exits 2 outside `session.is_regular_session()`.

# Phase 6 — ops scripts (EM13–EM14)

### Task EM13: Drain script

**Model:** sonnet — a bounded ops script over contracts that already exist (repository, client, `request_id_for`), with its full test and code given below; the judgement calls (no blind resend, refusing while the mirror is on) are made here.

Spec § Disable, drain and rollback ("lists every open position with a mirror row and, with `--execute`, closes each one through the same client (demo-only) and marks the rows. `--dry-run` is the default. Run it before any rollback that removes `broker/`"). Index § Global Constraints (demo only; `event_key "drain"`; never `StoreWriteHalt`), ledger row EM13.

The script lists `repo.open_positions()` (EM2: every `open` row `filled` whose plan has no `close_all` row `filled`/`closed_by_broker` and no row `closed_by_broker`). In a dry run it prints them and stops. With `--execute`, each position goes through `_drain_one`:

1. no `position_id` or `instrument_id` on the open row → `missing_ids`, nothing written or sent;
2. the plan already has its own `close_all` (any event key but `drain`) `queued`/`sending`/`in_flight` → `close_pending`: the executor is closing it, and a second close would race it;
3. insert the drain row (`insert_new`), or take the one an earlier run left; a final row reports its status and is never sent again;
4. a row left `sending` or `in_flight` is **looked up first**: found → its outcome; a `sending` row eToro never saw (`404`, or a 2xx body without `status`) → back to `queued` and sent with the **same** request id;
5. send: `set_status(..., "sending")` first (a failed write raises and nothing is sent), then `close_position(position_id, instrument_id, None, request_id)`; a 2xx is looked up every `POLL_S = 2.0` s for up to `WAIT_S = 30.0` s.

A drain row stays a normal `broker_orders` row: if the mirror is switched back on, the executor's own recovery picks up anything still `queued`, `sending` or `in_flight`.

**Files:**
- Create: `scripts/ops/etoro_mirror_drain.py`
- Create: `tests/scripts/test_etoro_mirror_drain.py`

**Interfaces:**
- Consumes:
  - `swingbot.core.db.repositories.broker_orders` (EM2): `FINAL_STATUSES`, `broker_orders_repo() -> BrokerOrderRepository` with `insert_new(record) -> dict | None`, `for_plan(plan_id) -> list[dict]`, `set_status(request_id, status, changes=None) -> None`, `open_positions() -> list[dict]`.
  - `swingbot.core.broker.etoro_client` (EM7): `EtoroClient()`, `close_position(position_id, instrument_id, units, request_id) -> ClientResult`, `lookup(reference_id) -> ClientResult`; `ClientResult(status_code, body=None, retry_after=None, deferred=False, error="")` with `.ok`.
  - `swingbot.core.broker.executor` (EM8): `request_id_for(plan_id, action, event_key) -> str`, `outcome_for(status_id) -> str`.
  - `swingbot.core.broker.mirror.ACTION_CLOSE_ALL` (EM6); `swingbot.core.broker.guard.assert_demo`, `RealAccountBlocked` (v159 ER7).
  - `config.ETORO_MIRROR_ENABLED` (EM1), `config.ETORO_USER_KEY`, `config.ETORO_API_KEY` (`config.py:128/134`).
  - Test helpers `tests/broker/fakes.py` (EM8): `FakeClient`, `FakeRepo` (`.seed`, `.row`, `.rows`, `.fail_insert`, `.fail_status`), `lookup_result(status_id, **kw)`.
- Produces (no later task consumes these; the ledger row is their contract):
  - `drain(repo, client, *, execute: bool, sleep=time.sleep, wait_s: float = WAIT_S) -> list[dict]`: one entry per open position, keys `plan_id, ticker, position_id, request_id, status`; `status` is `"dry_run"` when `execute` is false, else the row's local status after the run (`filled`, `closed_by_broker`, `rejected`, `in_flight`, `sending`, `queued`) or `missing_ids` / `close_pending`. `sleep` and `wait_s` are optional keywords, so the ledger's `drain(repo, client, *, execute)` call works unchanged.
  - `main(argv: list[str] | None = None) -> int`: `--dry-run` (default) or `--execute` (mutually exclusive); calls `guard.assert_demo("demo")` first; `--execute` exits 2 while `ETORO_MIRROR_ENABLED` is on or either key is blank; returns 0 on a dry run, 0 when every position closed (`filled`/`closed_by_broker`), else 1.

- [ ] **Step 1: Confirm the consumed contracts are on the branch**

```bash
git -C "$WT" grep -n "def open_positions\|def insert_new\|def set_status\|def for_plan\|^FINAL_STATUSES\|def broker_orders_repo" -- swingbot/core/db/repositories/broker_orders.py
git -C "$WT" grep -n "def request_id_for\|def outcome_for" -- swingbot/core/broker/executor.py
git -C "$WT" grep -n "def close_position\|def lookup\|class EtoroClient" -- swingbot/core/broker/etoro_client.py
git -C "$WT" grep -n "^ACTION_CLOSE_ALL" -- swingbot/core/broker/mirror.py
git -C "$WT" grep -n "class FakeRepo\|def seed\|def lookup_result" -- tests/broker/fakes.py
test -e "$WT/scripts/ops/etoro_mirror_drain.py" && echo EXISTS || echo absent
```

Expected: 6, 2, 3, 1 and 3 hits, then `absent`. A missing hit names the task that has not landed (EM2, EM8, EM7, EM6, EM8): stop with `BLOCKED: EM13 needs <task>`. `EXISTS` means an earlier run got this far: read the file and resume at the first step whose result is not on disk.

- [ ] **Step 2: Write the failing tests**

Create `tests/scripts/test_etoro_mirror_drain.py`:

```python
"""v160 EM13: scripts/ops/etoro_mirror_drain.py. Fake client, no network.

Most tests use tests/broker/fakes.FakeRepo; the last one runs the drain against
the real BrokerOrderRepository (db-test Postgres) to pin the row contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import sqlalchemy.exc as sa_exc

from swingbot import config
from swingbot.core.broker import guard
from swingbot.core.broker.etoro_client import ClientResult
from swingbot.core.broker.executor import request_id_for
from tests.broker.fakes import FakeClient, FakeRepo, lookup_result

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import etoro_mirror_drain as drain_mod  # noqa: E402

DRAIN_RID = request_id_for("p1", "close_all", "drain")


def _open(repo, plan_id="p1", ticker="AAPL", position_id=5001, instrument_id=1001):
    return repo.seed(plan_id, "open", "filled", "filled", ticker=ticker,
                     position_id=position_id, instrument_id=instrument_id,
                     units_filled=2.0, avg_price=100.1)


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


class SpyClient(FakeClient):
    """Records the drain row's status at the moment the close is sent."""

    def __init__(self, repo):
        super().__init__()
        self.repo = repo
        self.seen: list[str] = []

    def close_position(self, position_id, instrument_id, units, request_id):
        self.seen.append(self.repo.row(request_id)["status"])
        return super().close_position(position_id, instrument_id, units, request_id)


@pytest.fixture
def repo():
    return FakeRepo()


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "ETORO_USER_KEY", "user-key", raising=False)
    monkeypatch.setattr(config, "ETORO_API_KEY", "api-key", raising=False)


# --- dry run -------------------------------------------------------------------------

def test_dry_run_lists_only_open_positions_and_sends_nothing(repo):
    _open(repo)
    _open(repo, plan_id="p2", ticker="MSFT", position_id=5002)
    repo.seed("p2", "close_all", "closed", "filled")
    repo.seed("p3", "open", "filled", "rejected", ticker="NVDA")
    client = FakeClient()
    before = len(repo.rows)

    entries = drain_mod.drain(repo, client, execute=False)

    assert entries == [{"plan_id": "p1", "ticker": "AAPL", "position_id": 5001,
                        "request_id": DRAIN_RID, "status": "dry_run"}]
    assert client.calls == []
    assert len(repo.rows) == before


def test_dry_run_needs_no_client(repo):
    _open(repo)
    assert drain_mod.drain(repo, None, execute=False)[0]["status"] == "dry_run"


# --- execute: the happy path ---------------------------------------------------------

def test_execute_writes_the_row_before_sending_and_records_the_fill(repo):
    _open(repo)
    client = SpyClient(repo)

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.seen == ["sending"]
    assert client.names() == ["close_position", "lookup"]
    assert client.calls[0][1] == (5001, 1001, None, DRAIN_RID)
    assert client.calls[1][1] == (DRAIN_RID,)
    row = repo.row(DRAIN_RID)
    assert (row["action"], row["event_key"], row["status"]) == ("close_all", "drain", "filled")
    assert (row["position_id"], row["instrument_id"], row["order_id"]) == (5001, 1001, 7002)
    assert row["units_requested"] is None and row["sent_at"] and row["filled_at"]
    assert entries[0]["status"] == "filled"
    assert repo.open_positions() == []


def test_every_open_position_is_drained_in_one_run(repo):
    _open(repo)
    _open(repo, plan_id="p2", ticker="MSFT", position_id=5002, instrument_id=1002)

    entries = drain_mod.drain(repo, FakeClient(), execute=True, sleep=Sleeps())

    assert [(e["plan_id"], e["status"]) for e in entries] == [("p1", "filled"), ("p2", "filled")]
    assert repo.open_positions() == []


# --- no row, no send -----------------------------------------------------------------

@pytest.mark.parametrize("broken", ["insert", "sending"])
def test_a_failed_row_write_sends_nothing(repo, broken):
    _open(repo)
    if broken == "insert":
        repo.fail_insert = True
    else:
        repo.fail_status = {"sending"}
    client = FakeClient()

    with pytest.raises(sa_exc.OperationalError):
        drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.calls == []


# --- send outcomes -------------------------------------------------------------------

@pytest.mark.parametrize("result, status", [
    (ClientResult(409, {}), "closed_by_broker"),
    (ClientResult(400, {"errorCode": 631}), "closed_by_broker"),
    (ClientResult(400, {"errorCode": 99, "errorMessage": "nope"}), "rejected"),
    (ClientResult(429, {}, retry_after=5.0), "queued"),
    (ClientResult(0, deferred=True), "queued"),
    (ClientResult(0, error="timeout"), "sending"),
    (ClientResult(503, {}), "sending"),
])
def test_each_send_result_maps_like_the_executor(repo, result, status):
    _open(repo)
    client = FakeClient()
    client.script("close_position", result)

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert entries[0]["status"] == status
    assert repo.row(DRAIN_RID)["status"] == status
    assert client.names() == ["close_position"]


def test_a_rejected_close_records_the_error(repo):
    _open(repo)
    client = FakeClient()
    client.script("close_position", ClientResult(400, {"errorCode": 99, "errorMessage": "nope"}))

    drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    row = repo.row(DRAIN_RID)
    assert (row["error_code"], row["error_message"]) == (99, "nope")


# --- lookups -------------------------------------------------------------------------

def test_a_close_still_in_flight_after_the_wait_stays_in_flight(repo):
    _open(repo)
    client = FakeClient()
    client.script("lookup", lookup_result(11), lookup_result(11), lookup_result(11))
    sleeps = Sleeps()

    entries = drain_mod.drain(repo, client, execute=True, sleep=sleeps, wait_s=4.0)

    assert entries[0]["status"] == "in_flight"
    assert sleeps == [drain_mod.POLL_S, drain_mod.POLL_S]
    assert client.names() == ["close_position", "lookup", "lookup", "lookup"]


def test_a_lookup_rejection_with_631_is_closed_by_broker(repo):
    _open(repo)
    client = FakeClient()
    client.script("lookup", lookup_result(4, error_code=631, error_message="closed"))

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert entries[0]["status"] == "closed_by_broker"
    assert repo.row(DRAIN_RID)["error_code"] == 631


def test_a_lookup_rejection_with_another_code_is_rejected(repo):
    _open(repo)
    client = FakeClient()
    client.script("lookup", lookup_result(4, error_code=700, error_message="market closed"))

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert entries[0]["status"] == "rejected"
    assert repo.row(DRAIN_RID)["error_message"] == "market closed"


# --- re-runs -------------------------------------------------------------------------

def test_a_rerun_looks_up_a_row_left_sending_and_never_resends_blind(repo):
    _open(repo)
    repo.seed("p1", "close_all", "drain", "sending", position_id=5001, instrument_id=1001)
    client = FakeClient()

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.names() == ["lookup"]
    assert entries[0]["status"] == "filled"


def test_a_rerun_resends_a_row_etoro_never_saw_with_the_same_request_id(repo):
    _open(repo)
    repo.seed("p1", "close_all", "drain", "sending", position_id=5001, instrument_id=1001)
    client = FakeClient()
    client.script("lookup", ClientResult(404, {}))

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.names() == ["lookup", "close_position", "lookup"]
    assert client.calls[1][1][3] == DRAIN_RID
    assert entries[0]["status"] == "filled"
    assert len([row for row in repo.rows if row["action"] == "close_all"]) == 1


def test_a_rerun_after_a_transport_error_keeps_the_row_sending(repo):
    _open(repo)
    repo.seed("p1", "close_all", "drain", "sending", position_id=5001, instrument_id=1001)
    client = FakeClient()
    client.script("lookup", ClientResult(0, error="timeout"))

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.names() == ["lookup"]
    assert entries[0]["status"] == "sending"


def test_a_rerun_after_a_rejected_drain_does_not_send_again(repo):
    _open(repo)
    repo.seed("p1", "close_all", "drain", "rejected", position_id=5001, instrument_id=1001)
    client = FakeClient()

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert client.calls == []
    assert entries[0]["status"] == "rejected"


# --- positions the drain leaves alone ------------------------------------------------

def test_a_plan_whose_own_close_is_in_flight_is_left_to_the_mirror(repo):
    _open(repo)
    repo.seed("p1", "close_all", "closed", "in_flight")
    client = FakeClient()

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert entries[0]["status"] == "close_pending"
    assert client.calls == []
    with pytest.raises(LookupError):
        repo.row(DRAIN_RID)


def test_a_position_without_ids_is_reported_and_not_sent(repo):
    _open(repo, instrument_id=None)
    client = FakeClient()

    entries = drain_mod.drain(repo, client, execute=True, sleep=Sleeps())

    assert entries[0]["status"] == "missing_ids"
    assert client.calls == []


# --- main ----------------------------------------------------------------------------

def _wire(monkeypatch, repo, client=None):
    calls = []
    monkeypatch.setattr(guard, "assert_demo", lambda account: calls.append(account))
    monkeypatch.setattr(drain_mod, "broker_orders_repo", lambda: repo)
    if client is None:
        monkeypatch.setattr(drain_mod, "EtoroClient",
                            lambda: pytest.fail("this path builds no client"))
    else:
        monkeypatch.setattr(drain_mod, "EtoroClient", lambda: client)
    return calls


def test_main_dry_run_calls_the_guard_and_needs_no_keys(repo, monkeypatch, capsys):
    _open(repo)
    monkeypatch.setattr(config, "ETORO_USER_KEY", "", raising=False)
    calls = _wire(monkeypatch, repo)

    assert drain_mod.main([]) == 0
    assert drain_mod.main(["--dry-run"]) == 0
    assert calls == ["demo", "demo"]
    assert "DRY RUN: 1 open mirrored position" in capsys.readouterr().out


def test_main_runs_the_guard_before_reading_the_store(monkeypatch):
    def refuse(account):
        raise guard.RealAccountBlocked("blocked")
    monkeypatch.setattr(guard, "assert_demo", refuse)
    monkeypatch.setattr(drain_mod, "broker_orders_repo", lambda: pytest.fail("store read"))

    with pytest.raises(guard.RealAccountBlocked):
        drain_mod.main(["--execute"])


def test_main_execute_refuses_while_the_mirror_is_on(repo, monkeypatch, keys, capsys):
    _open(repo)
    monkeypatch.setattr(config, "ETORO_MIRROR_ENABLED", True, raising=False)
    _wire(monkeypatch, repo)

    assert drain_mod.main(["--execute"]) == 2
    assert "ETORO_MIRROR_ENABLED" in capsys.readouterr().err
    assert all(row["action"] == "open" for row in repo.rows)


@pytest.mark.parametrize("blank", ["ETORO_USER_KEY", "ETORO_API_KEY"])
def test_main_execute_refuses_without_both_keys(repo, monkeypatch, keys, capsys, blank):
    _open(repo)
    monkeypatch.setattr(config, blank, "", raising=False)
    _wire(monkeypatch, repo)

    assert drain_mod.main(["--execute"]) == 2
    assert "ETORO_USER_KEY and ETORO_API_KEY" in capsys.readouterr().err


def test_main_execute_closes_everything_and_returns_zero(repo, monkeypatch, keys, capsys):
    _open(repo)
    _wire(monkeypatch, repo, FakeClient())

    assert drain_mod.main(["--execute"]) == 0
    assert repo.row(DRAIN_RID)["status"] == "filled"
    assert "closed 1 of 1" in capsys.readouterr().out


def test_main_execute_returns_one_when_a_position_is_left_open(repo, monkeypatch, keys, capsys):
    _open(repo)
    client = FakeClient()
    client.script("close_position", ClientResult(503, {}))
    _wire(monkeypatch, repo, client)

    assert drain_mod.main(["--execute"]) == 1
    out = capsys.readouterr().out
    assert "closed 0 of 1" in out and "sending" in out


def test_dry_run_and_execute_are_mutually_exclusive(repo, monkeypatch):
    _wire(monkeypatch, repo)
    with pytest.raises(SystemExit):
        drain_mod.main(["--dry-run", "--execute"])


# --- the real repository (db-test Postgres; skips when it is down) -------------------

def test_the_drain_row_round_trips_through_the_real_repository():
    from swingbot.core.db.repositories.broker_orders import broker_orders_repo
    repo = broker_orders_repo()
    open_rid = request_id_for("p1", "open", "filled")
    repo.insert_new({"plan_id": "p1", "action": "open", "event_key": "filled",
                     "request_id": open_rid, "ticker": "AAPL", "direction": "bullish"})
    repo.set_status(open_rid, "filled", {"position_id": 5001, "instrument_id": 1001,
                                         "units_filled": 2.0})

    entries = drain_mod.drain(repo, FakeClient(), execute=True, sleep=Sleeps())

    assert [entry["status"] for entry in entries] == ["filled"]
    rows = repo.for_plan("p1")
    assert [(r["action"], r["event_key"], r["seq"], r["status"]) for r in rows] == [
        ("open", "filled", 1, "filled"), ("close_all", "drain", 2, "filled")]
    assert (rows[1]["position_id"], rows[1]["instrument_id"], rows[1]["order_id"]) == (
        5001, 1001, 7002)
    assert repo.open_positions() == []
    assert drain_mod.drain(repo, FakeClient(), execute=True, sleep=Sleeps()) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_mirror_drain.py
```

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'etoro_mirror_drain'`.

- [ ] **Step 4: Write the script**

Create `scripts/ops/etoro_mirror_drain.py`:

```python
#!/usr/bin/env python3
"""Drain the eToro demo mirror: close every demo position that has a mirror row.

Run inside the bot container, with ETORO_MIRROR_ENABLED switched off first:
    python scripts/ops/etoro_mirror_drain.py            # dry run: list only
    python scripts/ops/etoro_mirror_drain.py --execute  # close each position

Spec v160 § Disable, drain and rollback: run it before any rollback that
removes swingbot/core/broker/. Each close is a `close_all` row with event key
"drain", written and set `sending` before it is sent (no row, no send), so a
re-run looks up what an earlier run left in flight instead of closing twice.
Status mapping follows the executor (EM8). Demo account only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.broker import guard  # noqa: E402
from swingbot.core.broker.etoro_client import EtoroClient  # noqa: E402
from swingbot.core.broker.executor import outcome_for, request_id_for  # noqa: E402
from swingbot.core.broker.mirror import ACTION_CLOSE_ALL  # noqa: E402
from swingbot.core.db.repositories.broker_orders import (  # noqa: E402
    FINAL_STATUSES, broker_orders_repo,
)

DRAIN_KEY = "drain"
POLL_S = 2.0
WAIT_S = 30.0
DRY_RUN = "dry_run"
MISSING_IDS = "missing_ids"
CLOSE_PENDING = "close_pending"

_PENDING = frozenset({"queued", "sending", "in_flight"})
_BROKER_CLOSED_CODES = frozenset({631, 632})
_CLOSED = frozenset({"filled", "closed_by_broker"})


# --- small parsers (the executor's reading of eToro bodies) ---------------------------

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_block(body) -> dict:
    block = body.get("status") if isinstance(body, dict) else None
    return block if isinstance(block, dict) else {}


def _error_code(body) -> int | None:
    if not isinstance(body, dict):
        return None
    code = body.get("errorCode")
    return _int_or_none(code if code is not None else _status_block(body).get("errorCode"))


def _error_message(body) -> str:
    if not isinstance(body, dict):
        return str(body or "")[:300]
    return str(body.get("errorMessage") or body.get("message") or "")[:300]


def _order_id(body):
    close = body.get("orderForClose") if isinstance(body, dict) else None
    return close.get("orderID") if isinstance(close, dict) else None


# --- outcome mapping -----------------------------------------------------------------

def _send_outcome(result) -> tuple[str, dict]:
    """A close_position result -> (status, row changes)."""
    if result.deferred or result.status_code == 429:
        return "queued", {"not_before": _now_iso()}
    if result.status_code == 0 or result.status_code >= 500:
        return "sending", {}
    if result.ok:
        return "in_flight", {"order_id": _order_id(result.body)}
    code = _error_code(result.body)
    if result.status_code == 409 or code in _BROKER_CLOSED_CODES:
        return "closed_by_broker", {"error_code": code}
    return "rejected", {"error_code": code if code is not None else result.status_code,
                        "error_message": _error_message(result.body)}


def _lookup_outcome(result, current: str) -> tuple[str, dict]:
    """An orders:lookup result -> (status, row changes) for a row now `current`."""
    block = _status_block(result.body) if result.ok else {}
    if not block:
        unseen = current == "sending" and (result.status_code == 404 or result.ok)
        return ("queued" if unseen else current), {}
    outcome = outcome_for(block.get("id"))
    if outcome == "filled":
        return "filled", {"filled_at": _now_iso()}
    if outcome == "rejected":
        code = _int_or_none(block.get("errorCode"))
        status = "closed_by_broker" if code in _BROKER_CLOSED_CODES else "rejected"
        return status, {"error_code": code, "error_message": str(block.get("errorMessage") or "")}
    return "in_flight", {}


# --- one position --------------------------------------------------------------------

def _entry(opened: dict, status: str) -> dict:
    return {"plan_id": opened["plan_id"], "ticker": opened.get("ticker"),
            "position_id": opened.get("position_id"),
            "request_id": request_id_for(opened["plan_id"], ACTION_CLOSE_ALL, DRAIN_KEY),
            "status": status}


def _mirror_close_pending(rows: list[dict]) -> bool:
    """The executor already has this plan's own close_all on its way."""
    return any(row["action"] == ACTION_CLOSE_ALL and row["event_key"] != DRAIN_KEY
               and row["status"] in _PENDING for row in rows)


def _claim(repo, opened: dict) -> dict:
    """Insert the drain row, or return the one an earlier run left."""
    request_id = request_id_for(opened["plan_id"], ACTION_CLOSE_ALL, DRAIN_KEY)
    row = repo.insert_new({
        "plan_id": opened["plan_id"], "action": ACTION_CLOSE_ALL, "event_key": DRAIN_KEY,
        "request_id": request_id, "ticker": opened.get("ticker"),
        "direction": opened.get("direction"), "position_id": opened["position_id"],
        "instrument_id": opened["instrument_id"], "units_requested": None})
    if row is not None:
        return row
    return next(row for row in repo.for_plan(opened["plan_id"])
                if row["request_id"] == request_id)


def _send(repo, client, row: dict) -> str:
    """No row, no send: `sending` is stored before the request goes out."""
    request_id = row["request_id"]
    repo.set_status(request_id, "sending", {"sent_at": _now_iso()})
    result = client.close_position(int(row["position_id"]), int(row["instrument_id"]),
                                   None, request_id)
    status, changes = _send_outcome(result)
    if status != "sending":
        repo.set_status(request_id, status, changes)
    return status


def _settle(repo, client, row: dict, *, sleep, wait_s: float) -> str:
    """Look the close up until it is final, unseen, or wait_s has passed."""
    current, waited = row["status"], 0.0
    while True:
        status, changes = _lookup_outcome(client.lookup(row["request_id"]), current)
        if status != current or changes:
            repo.set_status(row["request_id"], status, changes)
        current = status
        if status != "in_flight" or waited >= wait_s:
            return status
        sleep(POLL_S)
        waited += POLL_S


def _drain_one(repo, client, opened: dict, *, sleep, wait_s: float) -> str:
    if opened.get("position_id") is None or opened.get("instrument_id") is None:
        return MISSING_IDS
    if _mirror_close_pending(repo.for_plan(opened["plan_id"])):
        return CLOSE_PENDING
    row = _claim(repo, opened)
    status = row["status"]
    if status in FINAL_STATUSES:
        return status
    if status in ("sending", "in_flight"):
        status = _settle(repo, client, row, sleep=sleep, wait_s=wait_s)
        if status != "queued":
            return status
    status = _send(repo, client, row)
    if status == "in_flight":
        status = _settle(repo, client, {**row, "status": status}, sleep=sleep, wait_s=wait_s)
    return status


def drain(repo, client, *, execute: bool, sleep=time.sleep,
          wait_s: float = WAIT_S) -> list[dict]:
    """One entry per open mirrored position; closes each one only when `execute`."""
    entries = []
    for opened in repo.open_positions():
        status = (_drain_one(repo, client, opened, sleep=sleep, wait_s=wait_s)
                  if execute else DRY_RUN)
        entries.append(_entry(opened, status))
    return entries


# --- CLI -----------------------------------------------------------------------------

def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Close every eToro demo position the v160 mirror opened.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="list only (the default)")
    mode.add_argument("--execute", action="store_true",
                      help="close each listed position on the demo account")
    return parser.parse_args(argv)


def _execute_blocker() -> str | None:
    if config.ETORO_MIRROR_ENABLED:
        return ("ETORO_MIRROR_ENABLED is on: switch it off and send SIGHUP first, so the "
                "live mirror cannot close the same positions at the same time.")
    if not config.ETORO_USER_KEY or not config.ETORO_API_KEY:
        return "ETORO_USER_KEY and ETORO_API_KEY must both be set in .env to close positions."
    return None


def _report(entries: list[dict], execute: bool) -> int:
    for entry in entries:
        print(f"{entry['plan_id']}  {entry['ticker']}  position {entry['position_id']}  "
              f"{entry['status']}")
    if not execute:
        print(f"DRY RUN: {len(entries)} open mirrored position(s); "
              "re-run with --execute to close them.")
        return 0
    left = [entry for entry in entries if entry["status"] not in _CLOSED]
    print(f"closed {len(entries) - len(left)} of {len(entries)}")
    if left:
        print("not closed: re-run in a minute for queued / sending / in_flight; close "
              "rejected and missing_ids positions by hand in the eToro app; close_pending "
              "ones are already being closed by the mirror.")
    return 1 if left else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    guard.assert_demo("demo")
    client = None
    if args.execute:
        problem = _execute_blocker()
        if problem:
            print(problem, file=sys.stderr)
            return 2
        client = EtoroClient()
    entries = drain(broker_orders_repo(), client, execute=args.execute)
    return _report(entries, args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests, the guard scan and the complexity check**

```bash
python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_mirror_drain.py
python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py
python -m radon cc -s -n C "$WT/scripts/ops/etoro_mirror_drain.py"
```

Expected: both runs `0 failed`, and the drain run reports **0 skipped**: the last test needs the db-test Postgres, and a skip there means the task is not done (start db-test with the command the skip message prints, then re-run this file). `test_guard.py` passes because `main()` calls `guard.assert_demo("demo")` (the scan walks `scripts/`). radon prints nothing.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add scripts/ops/etoro_mirror_drain.py tests/scripts/test_etoro_mirror_drain.py
git -C "$WT" commit -m "feat(v160): EM13 -- eToro mirror drain script

scripts/ops/etoro_mirror_drain.py lists every open demo position with a mirror
row (dry run by default) and, with --execute, closes each one as a close_all
row with event key drain: row first, then the send, then a bounded lookup.
A re-run looks up what an earlier run left in flight and never resends
blind. --execute refuses while ETORO_MIRROR_ENABLED is on or a key is blank.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task EM14: Manual demo smoke script

**Model:** sonnet — a short manual-run script over the existing client, translator body and eligibility parser, fully specified below; the only judgement is leaving no position behind on any failure path.

Spec § Testing ("`scripts/ops/etoro_demo_smoke.py` is manual: one 1-unit demo buy with a stop attached, a lookup and a close, using the `.env` keys. It is run once by hand after deploy"), § Rollout step 3 (run before `ETORO_MIRROR_ENABLED=true`), § Risks ("the smoke script catches drift"). Ledger row EM14.

The smoke walks six steps and stops at the first failure, naming it: `eligibility` (the symbol is open for a long, with a settlement type), `rates` (a usable ask), `open` (`open_order` with `executor.open_body`: market, leverage 1, **1 unit**, a fixed stop 10 % below the ask moved inside eToro's stop-distance bounds, no take-profit), `open_lookup` (poll `lookup` every `POLL_S = 5.0` s up to `wait_s`; filled → `positionId`, `avgPrice`), `close` (`close_position(position_id, instrument_id, None, ...)`), `close_lookup`. Reusing `open_body` and `parse_eligibility` means the smoke probes exactly what the mirror sends, so a renamed field or route shows up here first. Every failure after the open fills says the demo position is still open and names its id, so the partner closes it in the eToro app.

`main()` refuses (exit 2) when a key is blank or the US market is not in a regular session today (`session.is_regular_session()` and `nyse_calendar().is_session(market_today())`): outside it a market order waits for the open and outlives the script.

**Files:**
- Create: `scripts/ops/etoro_demo_smoke.py`
- Create: `tests/scripts/test_etoro_demo_smoke.py`

**Interfaces:**
- Consumes:
  - `swingbot.core.broker.etoro_client` (EM7): `EtoroClient()`, `eligibility(symbol)`, `rates(instrument_id)`, `open_order(body, request_id)`, `lookup(reference_id)`, `close_position(position_id, instrument_id, units, request_id)`, each `-> ClientResult` (`.ok`, `.status_code`, `.body`, `.error`).
  - `swingbot.core.broker.checks.parse_eligibility(body, symbol, direction) -> Eligibility | None` (EM4; fields `instrument_id`, `allow_open`, `settlement_type`, `min_stop_pct`, `max_stop_pct`).
  - `swingbot.core.broker.executor` (EM8): `open_body(row: dict, eligibility: Eligibility, units: float) -> dict` (reads `row["direction"]`, `row["stop_sent"]`, `row.get("tp_sent")`), `outcome_for(status_id) -> str`.
  - `swingbot.core.broker.mirror.round_rate(rate) -> float` (EM6); `swingbot.core.broker.guard.assert_demo`, `RealAccountBlocked` (v159 ER7).
  - `swingbot.core.market.session`: `is_regular_session(now=None) -> bool` (`session.py:48`), `market_today(now=None) -> dt.date` (`:115`), `nyse_calendar() -> SessionCalendar` with `.is_session(d)` (`:220`).
  - `config.ETORO_USER_KEY`, `config.ETORO_API_KEY` (`config.py:128/134`).
  - Test helpers `tests/broker/fakes.py` (EM8): `FakeClient` (defaults: `open_order` 202, `lookup` → `lookup_result(3)` with position 5001 at 100.1, `close_position` 200, `rates` → `rates_result()` ask 100.1 for instrument 1001), `lookup_result`, `rates_result`.
- Produces (no later task consumes these; the ledger row is their contract):
  - `SMOKE_UNITS = 1.0`, `SMOKE_STOP_PCT = 10.0`, `POLL_S = 5.0`, `WAIT_S = 60.0`.
  - `stop_pct(eligibility) -> float`: 10, raised to `min_stop_pct + 1` when that bound is 10 or more, lowered to the midpoint of the bounds when `max_stop_pct` is 10 or less.
  - `smoke(client, symbol: str, *, sleep=time.sleep, wait_s: float = 60.0) -> dict` with keys `ok, step, symbol, instrument_id, settlement_type, stop_rate, open_request_id, position_id, avg_price, close_request_id, detail`; `step` is the failing step, or `"done"`.
  - `main(argv: list[str] | None = None) -> int`: `--symbol` (default `AAPL`); calls `guard.assert_demo("demo")` first; exit 2 when either key is blank or the market is not in a regular session; prints the result as JSON; 0 when `ok`, else 1.

- [ ] **Step 1: Confirm the consumed contracts are on the branch**

```bash
git -C "$WT" grep -n "def eligibility\|def rates\|def open_order\|def lookup\|def close_position\|class EtoroClient" -- swingbot/core/broker/etoro_client.py
git -C "$WT" grep -n "def parse_eligibility" -- swingbot/core/broker/checks.py
git -C "$WT" grep -n "def open_body\|def outcome_for" -- swingbot/core/broker/executor.py
git -C "$WT" grep -n "def round_rate" -- swingbot/core/broker/mirror.py
git -C "$WT" grep -n "def is_regular_session\|def market_today\|def nyse_calendar" -- swingbot/core/market/session.py
git -C "$WT" grep -n "def rates_result\|def lookup_result\|class FakeClient" -- tests/broker/fakes.py
test -e "$WT/scripts/ops/etoro_demo_smoke.py" && echo EXISTS || echo absent
```

Expected: 6, 1, 2, 1, 3 and 3 hits, then `absent`. A missing hit names the task that has not landed (EM7, EM4, EM8, EM6, —, EM8): stop with `BLOCKED: EM14 needs <task>`. EM14 may run in parallel with EM8 (index § Parallelisation) only up to this step: it consumes `open_body` and `fakes.py`, so it waits for EM8 to land. `EXISTS` means an earlier run got this far: read the file and resume at the first step whose result is not on disk.

- [ ] **Step 2: Write the failing tests**

Create `tests/scripts/test_etoro_demo_smoke.py`:

```python
"""v160 EM14: scripts/ops/etoro_demo_smoke.py. Fake client, no network.

The real run is manual (spec § Testing): once by hand after a deploy, in US
regular hours, with the .env keys. These tests pin the step order, the exact
open body, and that every failure after a fill names the position left open.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.broker import guard
from swingbot.core.broker.checks import Eligibility
from swingbot.core.broker.etoro_client import ClientResult
from tests.broker.fakes import FakeClient, lookup_result

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import etoro_demo_smoke as smoke_mod  # noqa: E402

REAL_1 = {"settlementType": "Real", "direction": "long", "leverageValues": [1],
          "minStopLossPercentage": 0.5, "maxStopLossPercentage": 100}
AAPL = {"instrumentId": 1001, "symbol": "AAPL", "allowOpenPosition": True,
        "minPositionExposure": 10, "unitsQuantityType": "Fractional",
        "leverageConfigs": [REAL_1]}
FULL_RUN = ["eligibility", "rates", "open_order", "lookup", "close_position", "lookup"]


def _eligible(**overrides) -> ClientResult:
    return ClientResult(200, {"eligibilities": [dict(AAPL, **overrides)]})


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


@pytest.fixture
def client():
    fake = FakeClient()
    fake.script("eligibility", _eligible())
    return fake


def _elig(min_stop_pct=None, max_stop_pct=None) -> Eligibility:
    return Eligibility(instrument_id=1001, symbol="AAPL", allow_open=True,
                       settlement_type="real", min_exposure_usd=10.0, max_units=None,
                       min_stop_pct=min_stop_pct, max_stop_pct=max_stop_pct, unit_decimals=4)


# --- the happy path ------------------------------------------------------------------

def test_a_full_run_buys_one_unit_with_a_stop_looks_it_up_and_closes_it(client):
    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["ok"] is True and out["step"] == "done"
    assert client.names() == FULL_RUN
    body, open_rid = client.calls[2][1]
    assert body == {"action": "open", "transaction": "buy", "instrumentId": 1001,
                    "units": 1.0, "orderType": "mkt", "leverage": 1, "stopLossRate": 90.09,
                    "stopLossType": "fixed", "settlementType": "real"}
    assert client.calls[3][1] == (open_rid,)
    close_rid = out["close_request_id"]
    assert client.calls[4][1] == (5001, 1001, None, close_rid)
    assert client.calls[5][1] == (close_rid,)
    assert open_rid == out["open_request_id"] != close_rid
    uuid.UUID(open_rid)
    uuid.UUID(close_rid)
    assert (out["instrument_id"], out["settlement_type"], out["stop_rate"]) == (1001, "real", 90.09)
    assert (out["position_id"], out["avg_price"]) == (5001, 100.1)


def test_each_run_uses_fresh_request_ids(client):
    first = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())
    client.script("eligibility", _eligible())
    second = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())
    assert first["open_request_id"] != second["open_request_id"]


# --- failures before anything is opened ----------------------------------------------

@pytest.mark.parametrize("reply", [
    ClientResult(200, {"eligibilities": []}),
    _eligible(allowOpenPosition=False),
    _eligible(leverageConfigs=[]),
])
def test_an_ineligible_symbol_stops_at_eligibility(reply):
    client = FakeClient()
    client.script("eligibility", reply)

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert (out["ok"], out["step"]) == (False, "eligibility")
    assert client.names() == ["eligibility"]


def test_a_refused_key_names_the_scopes_it_needs():
    client = FakeClient()
    client.script("eligibility", ClientResult(401, {"message": "unauthorized"}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "eligibility"
    assert "demo:write" in out["detail"] and "market-data:read" in out["detail"]


def test_no_usable_ask_stops_at_rates_and_sends_nothing(client):
    client.script("rates", ClientResult(200, {"results": []}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "rates"
    assert "open_order" not in client.names()


def test_a_refused_open_stops_at_open(client):
    client.script("open_order", ClientResult(400, {"errorMessage": "bad body"}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "open" and "bad body" in out["detail"]
    assert client.names() == ["eligibility", "rates", "open_order"]


# --- failures around the open lookup -------------------------------------------------

def test_an_open_rejected_at_lookup_closes_nothing(client):
    client.script("lookup", lookup_result(4, error_code=700, error_message="market closed"))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "open_lookup" and "market closed" in out["detail"]
    assert "close_position" not in client.names()


def test_an_open_still_pending_after_the_wait_says_so(client):
    client.script("lookup", lookup_result(11), lookup_result(11), lookup_result(11))
    sleeps = Sleeps()

    out = smoke_mod.smoke(client, "AAPL", sleep=sleeps, wait_s=10.0)

    assert out["step"] == "open_lookup" and "still pending" in out["detail"]
    assert out["open_request_id"] in out["detail"]
    assert sleeps == [smoke_mod.POLL_S, smoke_mod.POLL_S]
    assert "close_position" not in client.names()


def test_a_lookup_404_before_the_order_is_indexed_keeps_polling(client):
    client.script("lookup", ClientResult(404, {}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["ok"] is True
    assert client.names() == ["eligibility", "rates", "open_order", "lookup", "lookup",
                              "close_position", "lookup"]


def test_a_fill_without_a_position_id_stops_and_says_check_the_account(client):
    client.script("lookup", ClientResult(200, {"status": {"id": 3}, "positionExecutions": []}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "open_lookup" and "positionId" in out["detail"]
    assert "close_position" not in client.names()


# --- failures after the position is open: always name it -----------------------------

def test_a_refused_close_names_the_position_left_open(client):
    client.script("close_position", ClientResult(500, {}))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "close"
    assert "still open" in out["detail"] and "5001" in out["detail"]


def test_a_close_rejected_at_lookup_names_the_position_left_open(client):
    client.script("lookup", lookup_result(3),
                  lookup_result(4, error_code=700, error_message="nope"))

    out = smoke_mod.smoke(client, "AAPL", sleep=Sleeps())

    assert out["step"] == "close_lookup"
    assert "still open" in out["detail"] and "5001" in out["detail"]


# --- the stop distance ---------------------------------------------------------------

@pytest.mark.parametrize("low, high, expected", [
    (None, None, 10.0),
    (0.5, 100.0, 10.0),
    (12.0, None, 13.0),
    (0.5, 8.0, 4.25),
    (None, 10.0, 5.0),
])
def test_stop_pct_stays_inside_etoros_bounds(low, high, expected):
    assert smoke_mod.stop_pct(_elig(low, high)) == expected


# --- main ----------------------------------------------------------------------------

def _wire(monkeypatch, client=None, *, market_open=True):
    calls = []
    monkeypatch.setattr(guard, "assert_demo", lambda account: calls.append(account))
    monkeypatch.setattr(smoke_mod, "_market_open", lambda: market_open)
    monkeypatch.setattr(config, "ETORO_USER_KEY", "user-key", raising=False)
    monkeypatch.setattr(config, "ETORO_API_KEY", "api-key", raising=False)
    if client is None:
        monkeypatch.setattr(smoke_mod, "EtoroClient",
                            lambda: pytest.fail("this path builds no client"))
    else:
        monkeypatch.setattr(smoke_mod, "EtoroClient", lambda: client)
    return calls


@pytest.mark.parametrize("blank", ["ETORO_USER_KEY", "ETORO_API_KEY"])
def test_main_exits_two_when_a_key_is_blank(monkeypatch, capsys, blank):
    calls = _wire(monkeypatch)
    monkeypatch.setattr(config, blank, "", raising=False)

    assert smoke_mod.main([]) == 2
    assert calls == ["demo"]
    assert "ETORO_USER_KEY and ETORO_API_KEY" in capsys.readouterr().err


def test_main_runs_the_guard_before_anything_else(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(config, "ETORO_USER_KEY", "", raising=False)

    def refuse(account):
        raise guard.RealAccountBlocked("blocked")
    monkeypatch.setattr(guard, "assert_demo", refuse)

    with pytest.raises(guard.RealAccountBlocked):
        smoke_mod.main([])


def test_main_exits_two_outside_a_regular_session(monkeypatch, capsys):
    _wire(monkeypatch, market_open=False)

    assert smoke_mod.main([]) == 2
    assert "regular hours" in capsys.readouterr().err


def test_main_prints_the_result_and_exits_zero_on_success(monkeypatch, capsys, client):
    _wire(monkeypatch, client)

    assert smoke_mod.main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True and printed["step"] == "done"
    assert client.calls[0] == ("eligibility", ("AAPL",))


def test_main_passes_the_symbol_and_exits_one_on_failure(monkeypatch, capsys):
    client = FakeClient()
    _wire(monkeypatch, client)

    assert smoke_mod.main(["--symbol", "MSFT"]) == 1
    assert client.calls[0] == ("eligibility", ("MSFT",))
    assert json.loads(capsys.readouterr().out)["step"] == "eligibility"


def test_the_smoke_writes_no_mirror_rows():
    text = Path(smoke_mod.__file__).read_text(encoding="utf-8")
    assert "broker_orders" not in text and "request_id_for" not in text
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_demo_smoke.py
```

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'etoro_demo_smoke'`.

- [ ] **Step 4: Write the script**

Create `scripts/ops/etoro_demo_smoke.py`:

```python
#!/usr/bin/env python3
"""Manual smoke test of the eToro demo routes the v160 mirror uses.

Run once by hand after a deploy, inside the bot container, during US regular
hours, with ETORO_USER_KEY / ETORO_API_KEY set in .env:
    python scripts/ops/etoro_demo_smoke.py [--symbol AAPL]

One 1-unit demo buy with a stop attached (the mirror's own open body), a
lookup, a close and a lookup. It writes nothing to the mirror's table, so the
parity report never counts it. Exit 0 when every step answered as expected, 1 when a
step failed (the output names it, and any position left open), 2 when it
refused to start. Demo account only; never part of the test suite.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.broker import checks, guard  # noqa: E402
from swingbot.core.broker.etoro_client import EtoroClient  # noqa: E402
from swingbot.core.broker.executor import open_body, outcome_for  # noqa: E402
from swingbot.core.broker.mirror import round_rate  # noqa: E402
from swingbot.core.market.session import (  # noqa: E402
    is_regular_session, market_today, nyse_calendar,
)

SMOKE_UNITS = 1.0
SMOKE_STOP_PCT = 10.0
POLL_S = 5.0
WAIT_S = 60.0
_SCOPES = "demo:write, demo:read and market-data:read"


@dataclass
class _Run:
    client: object
    sleep: object
    wait_s: float
    out: dict
    eligibility: checks.Eligibility | None = None
    ask: float | None = None


# --- parsing -------------------------------------------------------------------------

def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_block(body) -> dict:
    block = body.get("status") if isinstance(body, dict) else None
    return block if isinstance(block, dict) else {}


def _message(body) -> str:
    if not isinstance(body, dict):
        return str(body or "")[:300]
    block = _status_block(body)
    return str(body.get("errorMessage") or block.get("errorMessage")
               or body.get("message") or "")[:300]


def _http_problem(result) -> str:
    text = f"HTTP {result.status_code}: {result.error or _message(result.body)}"
    if result.status_code in (401, 403):
        text += f" (the key needs the scopes {_SCOPES})"
    return text


def _ask(body, instrument_id: int) -> float | None:
    results = body.get("results") if isinstance(body, dict) else None
    for item in results if isinstance(results, list) else []:
        if isinstance(item, dict) and _int_or_none(item.get("instrumentId")) == instrument_id:
            ask = _float(item.get("ask"))
            return ask if ask and ask > 0 else None
    return None


def _first_execution(body) -> dict:
    executions = body.get("positionExecutions") if isinstance(body, dict) else None
    first = executions[0] if isinstance(executions, list) and executions else {}
    return first if isinstance(first, dict) else {}


def stop_pct(eligibility) -> float:
    """10 % below the ask, moved inside eToro's stop-distance bounds when it has them."""
    pct = SMOKE_STOP_PCT
    low, high = eligibility.min_stop_pct, eligibility.max_stop_pct
    if low is not None and pct <= low:
        pct = low + 1.0
    if high is not None and pct >= high:
        pct = (high + (low or 0.0)) / 2
    return pct


# --- the steps -----------------------------------------------------------------------

def _still_open(run: _Run) -> str:
    return (f"demo position {run.out['position_id']} is still open: close it in the "
            "eToro app")


def _await(run: _Run, request_id: str) -> tuple[str, object]:
    """Poll orders:lookup until the order is final or wait_s has passed."""
    waited = 0.0
    while True:
        result = run.client.lookup(request_id)
        block = _status_block(result.body) if result.ok else {}
        outcome = outcome_for(block.get("id")) if block else "in_flight"
        if outcome != "in_flight" or waited >= run.wait_s:
            return outcome, result.body
        run.sleep(POLL_S)
        waited += POLL_S


def _eligibility(run: _Run) -> str | None:
    symbol = run.out["symbol"]
    result = run.client.eligibility(symbol)
    if not result.ok:
        return _http_problem(result)
    found = checks.parse_eligibility(result.body, symbol, "bullish")
    if found is None or not found.allow_open or found.settlement_type is None:
        return f"{symbol} is not open for a long position on this demo account"
    run.eligibility = found
    run.out.update(instrument_id=found.instrument_id, settlement_type=found.settlement_type)
    return None


def _rates(run: _Run) -> str | None:
    result = run.client.rates(run.eligibility.instrument_id)
    run.ask = _ask(result.body, run.eligibility.instrument_id) if result.ok else None
    if run.ask is None:
        detail = _http_problem(result) if not result.ok else "no usable ask in the answer"
        return f"rates for instrument {run.eligibility.instrument_id}: {detail}"
    return None


def _open(run: _Run) -> str | None:
    stop = round_rate(run.ask * (1 - stop_pct(run.eligibility) / 100))
    body = open_body({"direction": "bullish", "stop_sent": stop, "tp_sent": None},
                     run.eligibility, SMOKE_UNITS)
    request_id = str(uuid.uuid4())
    run.out.update(stop_rate=stop, open_request_id=request_id)
    result = run.client.open_order(body, request_id)
    return None if result.ok else _http_problem(result)


def _open_lookup(run: _Run) -> str | None:
    request_id = run.out["open_request_id"]
    outcome, body = _await(run, request_id)
    if outcome == "rejected":
        return f"eToro rejected the open: {_message(body)}"
    if outcome != "filled":
        return (f"open still pending after {run.wait_s:.0f}s (market closed?): check the "
                f"demo account for order {request_id} and close it by hand")
    first = _first_execution(body)
    position_id = _int_or_none(first.get("positionId"))
    if position_id is None:
        return (f"order {request_id} filled but the lookup carried no positionId: check "
                "the demo account and close the position by hand")
    opening = first.get("openingData") if isinstance(first.get("openingData"), dict) else {}
    run.out.update(position_id=position_id, avg_price=_float(opening.get("avgPrice")))
    return None


def _close(run: _Run) -> str | None:
    request_id = str(uuid.uuid4())
    run.out["close_request_id"] = request_id
    result = run.client.close_position(run.out["position_id"],
                                       run.eligibility.instrument_id, None, request_id)
    return None if result.ok else f"{_http_problem(result)}; {_still_open(run)}"


def _close_lookup(run: _Run) -> str | None:
    outcome, body = _await(run, run.out["close_request_id"])
    if outcome == "filled":
        return None
    return f"close {outcome} ({_message(body) or 'no message'}); {_still_open(run)}"


_STEPS = (("eligibility", _eligibility), ("rates", _rates), ("open", _open),
          ("open_lookup", _open_lookup), ("close", _close), ("close_lookup", _close_lookup))


def _blank(symbol: str) -> dict:
    return {"ok": False, "step": "", "symbol": symbol, "instrument_id": None,
            "settlement_type": None, "stop_rate": None, "open_request_id": None,
            "position_id": None, "avg_price": None, "close_request_id": None, "detail": ""}


def smoke(client, symbol: str, *, sleep=time.sleep, wait_s: float = WAIT_S) -> dict:
    """Run the six steps, stopping at the first failure; the result names it."""
    run = _Run(client=client, sleep=sleep, wait_s=wait_s, out=_blank(symbol))
    for name, step in _STEPS:
        run.out["step"] = name
        problem = step(run)
        if problem:
            run.out["detail"] = problem
            return run.out
    run.out.update(ok=True, step="done",
                   detail="eligibility, rates, open, lookup and close all answered")
    return run.out


# --- CLI -----------------------------------------------------------------------------

def _market_open() -> bool:
    return is_regular_session() and nyse_calendar().is_session(market_today())


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One 1-unit eToro demo buy, lookup and close (manual smoke test).")
    parser.add_argument("--symbol", default="AAPL", help="symbol to trade (default AAPL)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    guard.assert_demo("demo")
    if not config.ETORO_USER_KEY or not config.ETORO_API_KEY:
        print(f"ETORO_USER_KEY and ETORO_API_KEY must both be set in .env (scopes {_SCOPES}).",
              file=sys.stderr)
        return 2
    if not _market_open():
        print("Run during US regular hours (09:30-16:00 ET on an NYSE session): a market "
              "order outside them waits for the open and would outlive this script.",
              file=sys.stderr)
        return 2
    result = smoke(EtoroClient(), args.symbol)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests, the guard scan and the complexity check**

```bash
python "$WT/scripts/dev/testrun.py" file tests/scripts/test_etoro_demo_smoke.py
python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py
python -m radon cc -s -n C "$WT/scripts/ops/etoro_demo_smoke.py"
```

Expected: both runs `0 failed`. `test_guard.py` passes because `main()` calls `guard.assert_demo("demo")` (the script names `ETORO_USER_KEY` and imports `etoro_client`, so the scan would flag it otherwise). radon prints nothing. The smoke is **not** run against eToro here: that is rollout step 3, by the partner, on the VM.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add scripts/ops/etoro_demo_smoke.py tests/scripts/test_etoro_demo_smoke.py
git -C "$WT" commit -m "feat(v160): EM14 -- manual eToro demo smoke script

scripts/ops/etoro_demo_smoke.py: eligibility, rates, one 1-unit demo buy with
a stop (the mirror's own open body), lookup, close, lookup. Stops at the first
failure, names the step and any position left open. Refuses without both
keys or outside a regular NYSE session. Writes no broker_orders row.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

