# v189 — Book integrity and partial-trade truth: Implementation Plan, part 5 of 7 — clear history becomes an archived full reset

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-16:" -A 420 <this file>`.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D4 A6 ("clear history is a full reset, archived first"), D3 test bullet A6, `## Corrections from the code brief` 6 (cascaded rows are archived; `journal_entries` are kept) and 9 (archives git-ignored, ops-script convention, where the deploy paragraph goes).
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — `## Global Constraints`, `## Spec clarifications` 8 (`TradeLog.clear_history` stays a thin wrapper; the surfaces call `reset_closed_history` directly), `## Contracts` § Account reset, `## Parallelisation`, the task ledger.
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. Every path below is relative to it; every command runs from it.

**Consumed from earlier parts (names from the index ledger; re-read them as merged with `git grep -n` before use):**

- V189-5 (part 2): `swingbot.core.db.engine.transaction(conn=None, *, lock_timeout_ms=None)`, `ADMIN_LOCK_TIMEOUT_MS = 5000`, `LockTimeout`.
- V189-7 (part 2): `account.load_account_config(*, conn=None)`, `account.save_account_config(config, *, conn=None)`, `account._sum_realized_pnl(*, conn=None)`; `performance.run_after_commit(callbacks)`; `performance._refresh_snapshot_safely()` (exists today).
- V189-14 (part 4b): `TradeLog.clear_open() -> DeleteResult`, `TradeLog.delete_trade(id) -> DeleteResult`, and its edits to `swingbot/admin/api_v1/trade_commands.py`, `swingbot/commands/trades.py` and `tests/commands/parity_cases/trades.py` (`_FakeLog`). This part never touches those deleters; it edits only the clear-history lines next to them.
- v187: the admin-only decorators on `trades_clear_history` / `slash_trades_clear_history` (`commands.has_permissions(administrator=True)`, `app_commands.checks.has_permissions(administrator=True)`). Keep them exactly as merged.

**Decisions this part writes down (within the spec, not new scope):**

1. **One transaction, the book locked.** The reset runs in one transaction with `ADMIN_LOCK_TIMEOUT_MS` that first takes `LOCK TABLE plans, trades, account_balance_history IN EXCLUSIVE MODE` (plan → trade → account, the index's lock order). EXCLUSIVE blocks every concurrent write and `FOR UPDATE` on those tables but not plain reads, so the rows collected for the archive are exactly the rows deleted. A bot step that meets the lock waits at most its 1s `lock_timeout` and skips that plan for one poll (V189-9). The archive file is written **inside** that transaction, after collecting and before the first delete; if anything fails after the file is written, the file is removed and the transaction rolls back, so archives map one-to-one to resets that happened.
2. **Archive file name.** `account-reset-<YYYYmmddTHHMMSSZ>.json` (UTC, from `now`), created with exclusive-create mode: a second reset in the same second fails with `ArchiveFailed` instead of overwriting the first archive.
3. **Archived rows are repository records** (the shape `Repository.list_all` returns: promoted columns plus the document, no `id` / `updated_at`), passed through `codec.normalise`. The restore inserts them back through the same repositories, so the round trip needs no translation.
4. **Restore of later balance points.** Every balance point written after the reset was computed as `base + Σ realized` *without* the archived trades. The restore adds the restored realized P&L (`_sum_realized_pnl` after the inserts minus before, inside the same transaction) to each of those later points, which is exactly the balance they would have shown had the reset never run. It also deletes that reset's own reseed point. "A later reset has run" is detected as: the history no longer holds exactly one `account_reset` point naming this archive.
5. **Responses.** The endpoint returns the archive's file name, never the server path; the full path goes to the INFO log line. `LockTimeout` is not mapped to a status code (the reset is a rare manual action; the client sees the generic 500 and retries).

---

# Phase E — Account reset

### Task V189-15: Clear history becomes an archived full reset

**Model:** opus — a destructive bulk operation across four tables and a file, where the order (refuse → lock → archive → delete → reseed → after-commit refresh) and the failure paths are the whole point.

**Spec:** D4 A6 steps 1-3 and its kill-switch paragraph; D3 test bullet "A6: the archive file holds every deleted row. History is reseeded with one point at `base_balance`. A failed archive write leaves everything untouched."; D4 test bullet "Clear history resets the balance, the history and the drawdown peak"; Corrections 6 and 9; index § Contracts / Account reset; index clarification 8.

**Files:**
- Create: `swingbot/core/tracking/account_reset.py`
- Create: `tests/tracking/test_account_reset.py`
- Modify: `swingbot/core/db/repositories/plans.py` (`PlanRepository`: add `TERMINAL_STATUSES`, `delete_terminal`)
- Modify: `swingbot/core/db/repositories/account.py` (`AccountRepository`: add `clear_history`)
- Modify: `swingbot/core/tracking/performance.py` (`TradeLog.clear_history`, today `:1563-1566`; re-read with `git grep -n "def clear_history" swingbot/core/tracking/performance.py`)
- Modify: `.gitignore` (add `data/archives/` after the `data/backups/` line)
- Modify: `tests/tracking/test_tradelog_db_bulk.py` (`test_clear_history_deletes_closed_db_rows_only` replaced; the `clear_history` line of `test_clear_on_empty_db_returns_zero` removed)

**Interfaces:**
- Consumes: `transaction(lock_timeout_ms=)`, `ADMIN_LOCK_TIMEOUT_MS` (V189-5); `load_account_config(conn=)`, `save_account_config(cfg, conn=)`, `run_after_commit` (V189-7); `performance._refresh_snapshot_safely` (exists); `trades_repo().closed_trades(conn=)`, `trades_repo().clear(status="closed", conn=)`, `account_repo().history(conn=)`, `account_repo().append_history(entry, conn=)`, `plans_repo().list_all(conn=, where=, order_by=)`, `Repository(table, key)` (all exist); `throttle.kill_state()`, `throttle.current_throttle(points)` (exist); `codec.normalise` (exists).
- Produces (index § Contracts / Account reset):
  - `account_reset.RESET_REASON = "account_reset"`, `ARCHIVE_VERSION = 1`, `CHILD_TABLES` (`"starred_plans"`, `"plan_followers"`, `"plan_notifications"` → table), `BOOK_LOCK` (the `LOCK TABLE` statement), `REFUSED_TEXT`.
  - `class ResetRefused(Exception)`, `class ArchiveFailed(Exception)` (its message is the user-facing text).
  - `@dataclass(frozen=True) class ResetResult: removed_trades: int; removed_plans: int; archive_path: str; throttle_multiplier: float; throttle_paused: bool; kill_on: bool; base_balance: float; reset_at: str`.
  - `archive_dir() -> Path` (`Path(config.DATA_DIR) / "archives"`, read at call time).
  - `collect_archive(*, conn, reset_at: str | None = None) -> dict` — keys `version`, `reset_at`, `base_balance`, `trades`, `plans`, `account_balance_history`, `starred_plans`, `plan_followers`, `plan_notifications`. (`reset_at` is an optional keyword added to the index's `collect_archive(*, conn)`; a caller passing only `conn` gets "now".)
  - `reset_closed_history(*, force: bool = False, now: datetime | None = None) -> ResetResult`.
  - `describe_reset(result: ResetResult) -> str`.
  - `PlanRepository.TERMINAL_STATUSES = ("CLOSED", "CANCELLED")`, `PlanRepository.delete_terminal(self, *, conn) -> int`, `AccountRepository.clear_history(self, *, conn) -> int`.
  - `TradeLog.clear_history(self, *, force: bool = False) -> int` — `reset_closed_history(force=force).removed_trades`; lets `ResetRefused` / `ArchiveFailed` propagate.

- [ ] **Step 1: Write the failing test**

Create `tests/tracking/test_account_reset.py`:

```python
"""v189 A6: clear history is an archived full reset.

Every test runs against this worker's test database (the autouse store
fixture) with config.DATA_DIR pointed at tmp_path, so archives land in
tmp_path/archives. The seeded book: base 10,000; C1 closed +2,000 (plan P-C,
CLOSED, two realized legs), C2 closed -3,000 (no plan); O1 open on ACTIVE
P-O, O2 open on PENDING P-P; P-X CANCELLED; balance history 10,000 ->
12,000 -> 9,000 (a 25% drawdown, so the throttle is paused).
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.db.repositories.notifications import notifications_repo
from swingbot.core.db.repositories.plans import PlanRepository, plans_repo
from swingbot.core.db.repositories.starred import starred_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.edge import throttle
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import account_reset as ar
from tests.store_seed import seed_store

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
ARCHIVE = "account-reset-20261023T150000Z.json"
BASE = 10_000.0
HISTORY = [
    {"ts": "2026-10-01T10:00:00+00:00", "balance": 10_000.0, "pnl_amount": None,
     "reason": "account created"},
    {"ts": "2026-10-10T20:00:00+00:00", "balance": 12_000.0, "pnl_amount": 2_000.0,
     "trade_id": "C1"},
    {"ts": "2026-10-20T20:00:00+00:00", "balance": 9_000.0, "pnl_amount": -3_000.0,
     "trade_id": "C2"},
]
TWO_LEGS = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 130.0, "r": 6.0, "reason": "tp2"}]


def _plan_record(plan_id, status, legs=()):
    return {
        "plan_id": plan_id, "ticker": "GOLD", "created_at": "2026-10-01T09:00:00+00:00",
        "source": "strategy", "strategy": "RSI Divergence", "horizon_key": "1m",
        "direction": "bullish", "entry_type": "stop_entry", "trigger_price": 100.0,
        "entry_price": 100.0, "expiry_bars": 5, "stop_loss": 95.0, "tp1": 110.0,
        "tp1_fraction": 0.5, "tp2": 120.0, "breakeven_trigger_fraction": 0.5,
        "trail_atr_mult": 1.5, "quality_score": 70, "quality_breakdown": [],
        "badge": "VALIDATED", "badge_stats": {}, "status": status,
        "status_history": [], "legs_realized": list(legs),
    }


def _trade_record(trade_id, status, *, plan_id=None, exit_price=None, pnl=None):
    closed = status != "open"
    return {
        "id": trade_id, "plan_id": plan_id, "ticker": "GOLD", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
        "take_profit": 110.0, "shares": 100, "legs": [], "status": status,
        "opened_at": "2026-10-01T10:00:00+00:00",
        "closed_at": "2026-10-10T20:00:00+00:00" if closed else None,
        "exit_price": exit_price, "realized_pnl_amount": pnl,
    }


@pytest.fixture
def book(tmp_path, monkeypatch):
    """Seed the book above; return the directory archives are written to."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)   # never read from .env
    seed_store("account", {"base_balance": BASE, "balance_history": HISTORY})
    seed_store("plans", [_plan_record("P-C", "CLOSED", TWO_LEGS), _plan_record("P-X", "CANCELLED"),
                         _plan_record("P-O", "ACTIVE"), _plan_record("P-P", "PENDING")])
    seed_store("trades", [
        _trade_record("C1", "win", plan_id="P-C", exit_price=120.0, pnl=2_000.0),
        _trade_record("C2", "loss", exit_price=70.0, pnl=-3_000.0),
        _trade_record("O1", "open", plan_id="P-O"),
        _trade_record("O2", "open", plan_id="P-P"),
    ])
    starred_repo().star("P-C")
    starred_repo().star("P-O")
    followers_repo().add("P-C", 42, "taken", status_at_press="ACTIVE")
    followers_repo().add("P-O", 42, "watch", status_at_press="ACTIVE")
    notifications_repo().claim("P-X", "cancelled_expired", {"note": "sent"})
    return tmp_path / "archives"


def _trade_ids():
    return sorted(t["trade_id"] for t in trades_repo().list_all())


def _plan_ids():
    return sorted(p["plan_id"] for p in plans_repo().list_all())


def _state():
    """Everything a reset may touch, for the "left untouched" assertions."""
    return (_trade_ids(), _plan_ids(),
            [h["balance"] for h in account_module.get_balance_history()],
            sorted(starred_repo().ids()))


# --- the archive ----------------------------------------------------------------

def test_the_archive_holds_every_row_the_reset_deletes(book):
    result = ar.reset_closed_history(now=NOW)
    path = book / ARCHIVE
    assert result.archive_path == str(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["reset_at"] == "2026-10-23T15:00:00+00:00"
    assert payload["base_balance"] == BASE
    assert sorted(t["trade_id"] for t in payload["trades"]) == ["C1", "C2"]
    assert sorted(p["plan_id"] for p in payload["plans"]) == ["P-C", "P-X"]
    closed_plan = next(p for p in payload["plans"] if p["plan_id"] == "P-C")
    assert [leg["reason"] for leg in closed_plan["legs_realized"]] == ["tp1", "tp2"]
    assert [h["balance"] for h in payload["account_balance_history"]] == [10_000.0, 12_000.0, 9_000.0]
    assert [r["plan_id"] for r in payload["starred_plans"]] == ["P-C"]
    assert [(r["plan_id"], r["user_id"], r["kind"]) for r in payload["plan_followers"]] == [
        ("P-C", 42, "taken")]
    assert [(r["plan_id"], r["event"]) for r in payload["plan_notifications"]] == [
        ("P-X", "cancelled_expired")]


def test_archives_are_git_ignored():
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", f"data/archives/{ARCHIVE}"],
                       cwd=REPO)
    assert r.returncode == 0, "data/archives/ holds account data and must never be staged"


# --- what is deleted and what stays ----------------------------------------------

def test_closed_trades_and_finished_plans_go_open_and_live_stay(book):
    result = ar.reset_closed_history(now=NOW)
    assert (result.removed_trades, result.removed_plans) == (2, 2)
    assert _trade_ids() == ["O1", "O2"]
    assert _plan_ids() == ["P-O", "P-P"]
    assert sorted(starred_repo().ids()) == ["P-O"]               # P-C's star cascaded
    assert followers_repo().followers("P-O") == {42: frozenset({"watch"})}
    assert followers_repo().followers("P-C") == {}


def test_history_restarts_with_one_point_at_the_base_balance(book):
    ar.reset_closed_history(now=NOW)
    [point] = account_module.get_balance_history()
    assert (point["balance"], point["pnl_amount"]) == (BASE, 0.0)
    assert (point["reason"], point["archive"]) == (ar.RESET_REASON, ARCHIVE)
    assert datetime.fromisoformat(point["ts"]) == NOW              # session time zone agnostic
    assert account_module.load_account_config()["balance"] == BASE
    assert account_module.get_balance_history_points() == [("2026-10-23", BASE)]


def test_a_reset_of_an_empty_history_still_reseeds(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "KILLSWITCH_DEFAULT_ON", False)
    seed_store("account", {"base_balance": 5_000.0})
    result = ar.reset_closed_history(now=NOW)
    assert (result.removed_trades, result.removed_plans, result.base_balance) == (0, 0, 5_000.0)
    assert [h["balance"] for h in account_module.get_balance_history()] == [5_000.0]


# --- throttle and kill switch ------------------------------------------------------

def test_the_drawdown_peak_restarts_so_the_throttle_lifts(book):
    before = [b for _, b in account_module.get_balance_history_points()]
    assert throttle.drawdown_pct(before) == pytest.approx(25.0)
    assert throttle.current_throttle(before) == (0.0, True)
    result = ar.reset_closed_history(now=NOW)
    assert (result.throttle_multiplier, result.throttle_paused, result.kill_on) == (1.0, False, False)
    after = [b for _, b in account_module.get_balance_history_points()]
    assert throttle.drawdown_pct(after) == 0.0


def test_refused_while_the_kill_switch_is_tripped(book):
    killswitch_repo().engage("drawdown >20%")
    before = _state()
    with pytest.raises(ar.ResetRefused):
        ar.reset_closed_history(now=NOW)
    assert _state() == before
    assert not book.exists()
    assert throttle.kill_state()["on"] is True


def test_force_resets_but_never_releases_the_kill_switch(book):
    killswitch_repo().engage("drawdown >20%")
    result = ar.reset_closed_history(force=True, now=NOW)
    assert result.kill_on is True
    state = throttle.kill_state()
    assert (state["on"], state["reason"]) == (True, "drawdown >20%")
    assert _trade_ids() == ["O1", "O2"]


# --- failure paths ---------------------------------------------------------------------

def test_a_failed_archive_write_leaves_everything_untouched(book, tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(blocker))     # archives/ cannot be created
    before = _state()
    with pytest.raises(ar.ArchiveFailed, match="Nothing was deleted"):
        ar.reset_closed_history(now=NOW)
    assert _state() == before


def test_a_failure_after_the_archive_rolls_back_and_removes_the_file(book, monkeypatch):
    def boom(self, *, conn):
        raise RuntimeError("delete failed")
    monkeypatch.setattr(PlanRepository, "delete_terminal", boom)
    before = _state()
    with pytest.raises(RuntimeError, match="delete failed"):
        ar.reset_closed_history(now=NOW)
    assert _state() == before
    assert list(book.glob("*.json")) == []


def test_a_second_reset_in_the_same_second_never_overwrites_the_first_archive(book):
    ar.reset_closed_history(now=NOW)
    first = (book / ARCHIVE).read_bytes()
    with pytest.raises(ar.ArchiveFailed):
        ar.reset_closed_history(now=NOW)
    assert (book / ARCHIVE).read_bytes() == first
    assert len(account_module.get_balance_history()) == 1


def test_the_snapshot_refresh_runs_after_commit(book, monkeypatch):
    seen = []
    # Reads on its own connection, so it sees only committed rows.
    monkeypatch.setattr(ar, "_refresh_snapshot_safely", lambda: seen.append(_trade_ids()))
    ar.reset_closed_history(now=NOW)
    assert seen == [["O1", "O2"]]


# --- the words ---------------------------------------------------------------------------

def test_describe_reset_names_the_archive_throttle_kill_switch_and_sizing():
    result = ar.ResetResult(
        removed_trades=2, removed_plans=3, archive_path=f"/app/data/archives/{ARCHIVE}",
        throttle_multiplier=1.0, throttle_paused=False, kill_on=True,
        base_balance=10_000.0, reset_at="2026-10-23T15:00:00+00:00")
    assert ar.describe_reset(result) == (
        "Account reset: removed 2 closed trade(s) and 3 finished plan(s). Realized P&L and "
        "the drawdown history restart from the base balance 10,000.00.\n"
        f"Archive: {ARCHIVE}\n"
        "Throttle: 1.00x, not paused. The drawdown peak restarts at the base balance, "
        "so any throttle is lifted.\n"
        "Kill switch: on -- the reset never releases it; release it by hand.\n"
        "New trades are sized off the base balance. Open trades and live plans were not touched.")


def test_describe_reset_with_the_kill_switch_off():
    result = ar.ResetResult(
        removed_trades=0, removed_plans=0, archive_path=ARCHIVE, throttle_multiplier=1.0,
        throttle_paused=False, kill_on=False, base_balance=5_000.0, reset_at="x")
    assert "\nKill switch: off.\n" in ar.describe_reset(result)


def test_the_refusal_names_both_overrides():
    assert ar.REFUSED_TEXT == (
        "Reset refused: the kill switch is tripped. Release it first, or force the reset "
        "(`force=true` on the endpoint, `!trades clear history force` or "
        "`/trades-clear-history force:True`); the kill switch stays on either way.")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/tracking/test_account_reset.py`
Expected: FAIL at collection — `ImportError: cannot import name 'account_reset' from 'swingbot.core.tracking'`.

- [ ] **Step 3: Add the two bulk deletes to the repositories**

In `swingbot/core/db/repositories/plans.py`, inside `PlanRepository` (after `OPEN_STATUSES`):

```python
    #: The statuses that end a plan; the v189 account reset deletes these.
    TERMINAL_STATUSES = ("CLOSED", "CANCELLED")

    def delete_terminal(self, *, conn) -> int:
        """Delete every CLOSED/CANCELLED plan (v189 A6) inside the caller's
        transaction. Its starred_plans, plan_followers and plan_notifications
        rows go with it (ON DELETE CASCADE); the caller archives them first."""
        statement = sa.delete(plans).where(plans.c.status.in_(self.TERMINAL_STATUSES))
        return conn.execute(statement).rowcount
```

In `swingbot/core/db/repositories/account.py` add `import sqlalchemy as sa` and, inside `AccountRepository` (after `history`):

```python
    def clear_history(self, *, conn) -> int:
        """Delete every balance-history point inside the caller's transaction
        (v189 A6). The caller reseeds one point: an empty history reads as
        "no data", not as a flat account (known-traps "Measured-empty tables")."""
        return conn.execute(sa.delete(account_balance_history)).rowcount
```

`conn` is required on both: neither may ever run in a transaction of its own.

- [ ] **Step 4: Create `swingbot/core/tracking/account_reset.py`**

```python
"""v189 A6: clearing history is an archived full reset.

Order (spec D4 A6):
  1. refuse while the kill switch is tripped, unless forced (it is never cleared here);
  2. one transaction (ADMIN lock timeout) that locks plans, trades and
     account_balance_history IN EXCLUSIVE MODE (plan -> trade -> account),
     collects every closed trade, terminal plan, balance point and the terminal
     plans' star/follower/notification rows, writes them to
     data/archives/account-reset-<UTC>.json (the reset stops if that write
     fails), deletes them, and reseeds one history point at the base balance,
     so the drawdown peak, the throttle and the kill-switch drawdown trigger
     all restart from the base balance;
  3. after commit, the snapshot refresh.
Open trades, live plans and journal entries are never touched. The archive is
the rollback: scripts/ops/restore_account_reset.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from swingbot import config
from swingbot.core.db.codec import normalise
from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.plans import plans_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.db.schema import plan_followers, plan_notifications, plans, starred_plans
from swingbot.core.edge import throttle
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import _refresh_snapshot_safely, run_after_commit

log = logging.getLogger(__name__)

RESET_REASON = "account_reset"
ARCHIVE_VERSION = 1
CHILD_TABLES = {"starred_plans": starred_plans, "plan_followers": plan_followers,
                "plan_notifications": plan_notifications}
BOOK_LOCK = sa.text(
    "LOCK TABLE plans, trades, account_balance_history IN EXCLUSIVE MODE")
REFUSED_TEXT = (
    "Reset refused: the kill switch is tripped. Release it first, or force the reset "
    "(`force=true` on the endpoint, `!trades clear history force` or "
    "`/trades-clear-history force:True`); the kill switch stays on either way.")


class ResetRefused(Exception):
    """The kill switch is tripped and the caller did not force the reset."""


class ArchiveFailed(Exception):
    """The archive could not be written; nothing was deleted. The message is
    the user-facing text."""


@dataclass(frozen=True)
class ResetResult:
    removed_trades: int
    removed_plans: int
    archive_path: str
    throttle_multiplier: float
    throttle_paused: bool
    kill_on: bool
    base_balance: float
    reset_at: str


def archive_dir() -> Path:
    """Where reset archives live: the persistent data volume (read at call time)."""
    return Path(config.DATA_DIR) / "archives"


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _child_rows(table: sa.Table, plan_ids: list[str], *, conn) -> list[dict]:
    if not plan_ids:
        return []
    return Repository(table, key="plan_id").list_all(
        conn=conn, where=table.c.plan_id.in_(plan_ids), order_by=table.c.plan_id)


def collect_archive(*, conn, reset_at: str | None = None) -> dict:
    """Every row the reset deletes, as repository records, JSON-safe."""
    cfg = account_module.load_account_config(conn=conn)
    repo = plans_repo()
    terminal = repo.list_all(conn=conn, where=plans.c.status.in_(repo.TERMINAL_STATUSES),
                             order_by=plans.c.plan_id)
    plan_ids = [plan["plan_id"] for plan in terminal]
    payload = {
        "version": ARCHIVE_VERSION,
        "reset_at": reset_at or _utc(None).isoformat(),
        "base_balance": float(cfg["base_balance"]),
        "trades": trades_repo().closed_trades(conn=conn),
        "plans": terminal,
        "account_balance_history": account_repo().history(conn=conn),
    }
    for name, table in CHILD_TABLES.items():
        payload[name] = _child_rows(table, plan_ids, conn=conn)
    return normalise(payload)


def _failed_text(path: Path, exc: Exception) -> str:
    return (f"Reset aborted: the archive {path.name} could not be written ({exc}). "
            "Nothing was deleted.")


def _write_archive(path: Path, payload: dict) -> None:
    """Exclusive-create the archive (an existing one is never overwritten)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("x", encoding="utf-8")
    except OSError as exc:
        raise ArchiveFailed(_failed_text(path, exc)) from exc
    try:
        with handle:
            json.dump(payload, handle, indent=1, sort_keys=True, allow_nan=False)
    except (OSError, TypeError, ValueError) as exc:
        path.unlink(missing_ok=True)
        raise ArchiveFailed(_failed_text(path, exc)) from exc


def _reseed(base: float, reset_at: str, archive_name: str, *, conn) -> None:
    account_repo().append_history({"ts": reset_at, "balance": base, "pnl_amount": 0.0,
                                   "reason": RESET_REASON, "archive": archive_name}, conn=conn)
    cfg = account_module.load_account_config(conn=conn)
    account_module.save_account_config({**cfg, "balance": base, "balance_history": []},
                                       conn=conn)


def _reset_in_tx(path: Path, reset_at: str) -> tuple[int, int, float]:
    """Lock, archive, delete, reseed in one transaction; a failure after the
    archive was written removes the file, so every archive is a reset that
    happened. Returns (removed trades, removed plans, base balance)."""
    written = False
    try:
        with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
            conn.execute(BOOK_LOCK)
            payload = collect_archive(conn=conn, reset_at=reset_at)
            _write_archive(path, payload)
            written = True
            removed_plans = plans_repo().delete_terminal(conn=conn)
            removed_trades = trades_repo().clear(status="closed", conn=conn)
            account_repo().clear_history(conn=conn)
            _reseed(payload["base_balance"], reset_at, path.name, conn=conn)
    except Exception:
        if written:
            path.unlink(missing_ok=True)
        raise
    return removed_trades, removed_plans, payload["base_balance"]


def reset_closed_history(*, force: bool = False, now: datetime | None = None) -> ResetResult:
    """The archived full reset (spec D4 A6). Raises ResetRefused while the kill
    switch is tripped unless `force`, ArchiveFailed when the archive cannot be
    written (nothing deleted), LockTimeout when the book stays locked > 5s."""
    if throttle.kill_state().get("on") and not force:
        log.info("account reset refused: kill switch tripped (force overrides)")
        raise ResetRefused(REFUSED_TEXT)
    moment = _utc(now)
    path = archive_dir() / f"account-reset-{moment:%Y%m%dT%H%M%SZ}.json"
    removed_trades, removed_plans, base = _reset_in_tx(path, moment.isoformat())
    run_after_commit([_refresh_snapshot_safely])
    points = [balance for _, balance in account_module.get_balance_history_points()]
    multiplier, paused = throttle.current_throttle(points)
    kill_on = bool(throttle.kill_state().get("on"))
    log.info("account reset: removed %d closed trade(s) and %d terminal plan(s); archive %s%s",
             removed_trades, removed_plans, path, " (forced; kill switch left on)" if kill_on else "")
    return ResetResult(removed_trades=removed_trades, removed_plans=removed_plans,
                       archive_path=str(path), throttle_multiplier=multiplier,
                       throttle_paused=paused, kill_on=kill_on, base_balance=base,
                       reset_at=moment.isoformat())


def describe_reset(result: ResetResult) -> str:
    """The confirmation every surface shows (spec D4 A6)."""
    throttle_state = "paused" if result.throttle_paused else "not paused"
    kill = ("on -- the reset never releases it; release it by hand" if result.kill_on
            else "off")
    return "\n".join((
        f"Account reset: removed {result.removed_trades} closed trade(s) and "
        f"{result.removed_plans} finished plan(s). Realized P&L and the drawdown history "
        f"restart from the base balance {result.base_balance:,.2f}.",
        f"Archive: {Path(result.archive_path).name}",
        f"Throttle: {result.throttle_multiplier:.2f}x, {throttle_state}. The drawdown peak "
        "restarts at the base balance, so any throttle is lifted.",
        f"Kill switch: {kill}.",
        "New trades are sized off the base balance. Open trades and live plans were not touched.",
    ))
```

No `threading.Lock` is taken anywhere on this path (index lock rule): the Postgres table lock is the only serialisation. `run_after_commit` runs `_refresh_snapshot_safely` through the module-level name, so the test's monkeypatch of `ar._refresh_snapshot_safely` takes effect; keep the list literal built at call time.

- [ ] **Step 5: `TradeLog.clear_history` becomes the wrapper; ignore the archives; update the bulk test**

Replace `TradeLog.clear_history` in `swingbot/core/tracking/performance.py`:

```python
    def clear_history(self, *, force: bool = False) -> int:
        """v189 A6: the archived full reset (`account_reset.reset_closed_history`);
        returns how many closed trades it removed. Raises ResetRefused while the
        kill switch is tripped unless forced, ArchiveFailed when the archive
        cannot be written (then nothing is deleted). No `_LOCK`: the reset
        serialises on a Postgres table lock."""
        from swingbot.core.tracking import account_reset   # lazy: it imports this module
        return account_reset.reset_closed_history(force=force).removed_trades
```

In `.gitignore`, directly after the `data/backups/` line:

```
# v189 account-reset archives (closed trades, plans, balance history): account data.
data/archives/
```

In `tests/tracking/test_tradelog_db_bulk.py`, replace `test_clear_history_deletes_closed_db_rows_only` with:

```python
def test_clear_history_is_the_archived_reset(monkeypatch):
    from swingbot.core.tracking import account_reset
    calls = []

    def fake_reset(*, force=False, now=None):
        calls.append(force)
        return account_reset.ResetResult(
            removed_trades=2, removed_plans=1, archive_path="a.json", throttle_multiplier=1.0,
            throttle_paused=False, kill_on=False, base_balance=10_000.0, reset_at="x")

    monkeypatch.setattr(account_reset, "reset_closed_history", fake_reset)
    assert TradeLog().clear_history() == 2
    assert TradeLog().clear_history(force=True) == 2
    assert calls == [False, True]
```

and delete the line `assert log.clear_history() == 0` from `test_clear_on_empty_db_returns_zero` (leave its other lines exactly as V189-14 left them).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_account_reset.py`
Expected: PASS (15 tests).

Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_db_bulk.py`
Expected: PASS.

- [ ] **Step 7: Run the neighbours and the gate**

`/trades/clear-history` still calls `TradeLog().clear_history()` until V189-16 and still returns `{"removed": n}`; the `admin_app` fixture points `DATA_DIR` at `tmp_path`, so its archive lands there.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py`
Expected: PASS (`test_clear_history_leaves_open_trades` included).

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function is at most 4).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/tracking/account_reset.py swingbot/core/db/repositories/plans.py swingbot/core/db/repositories/account.py swingbot/core/tracking/performance.py .gitignore tests/tracking/test_account_reset.py tests/tracking/test_tradelog_db_bulk.py
git commit -m "feat(account): clear history is an archived full reset -- archive first, reseed at base, refused while the kill switch is tripped (v189 V189-15)"
```

### Task V189-16: Reset surfaces: endpoint force, Discord force, confirmation text

**Model:** sonnet — two thin surfaces over V189-15's function with a fixed status mapping and fixed copy, plus the parity cases that pin prefix and slash together.

**Spec:** D4 A6 ("The command's confirmation text says it resets the account's realized P&L and drawdown history, and names the archive …"; "refused while the kill switch is tripped, unless the caller passes an explicit override: `force=true` on the endpoint, or `!trades clear history force`"); index § Contracts / Account reset (endpoint body and status codes; Discord `!trades clear history [force]`, `/trades-clear-history force:<bool>`); index clarification 8 (surfaces call `reset_closed_history` directly).

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py` (`clear_history` route, today `:273-276`; add `_force_requested`, `_reset_payload`)
- Modify: `swingbot/commands/trades.py` (`handle_trades_clear_history` `:200-203`; prefix `trades_clear_history` `:227-232`; slash `slash_trades_clear_history` `:713-715`; the help line `:107`)
- Modify: `tests/commands/parity_cases/trades.py` (the `trades_clear_history` case's stub; three new cases; drop `_FakeLog.clear_history`)
- Modify: `tests/admin/test_api_v1_trade_commands.py` (`test_clear_history_leaves_open_trades`: the body now has more keys than `removed`)
- Test (run, no edit expected): `tests/commands/test_reply_parity.py` — it runs every `CASES` entry, so the new parity cases join it without an edit; the `SLASH_TWIN` row `"trades clear history": "trades-clear-history"` is unchanged.
- Create: `tests/admin/test_clear_history_reset_api.py`
- Create: `tests/commands/test_trades_clear_history_force.py`

Line numbers are pre-v187; v187 adds admin decorators to both Discord functions and V189-14 edits the neighbouring clear-open/delete handlers. Re-read with `git grep -n "clear_history" swingbot/admin/api_v1/trade_commands.py swingbot/commands/trades.py` and keep every decorator exactly as merged.

**Interfaces:**
- Consumes (V189-15): `account_reset.reset_closed_history(*, force=False, now=None) -> ResetResult`, `ResetResult` fields, `ResetRefused`, `ArchiveFailed` (message = user-facing text), `REFUSED_TEXT`, `describe_reset(result) -> str`.
- Produces:
  - `POST /api/v1/trades/clear-history` — force when `?force=` is `1`/`true`/`yes` (any case) or the JSON body is an object with `"force": true` (the boolean; anything else is no force). 200 `{"removed": int, "removed_plans": int, "archive": "<file name>", "throttle": {"multiplier": float, "paused": bool}, "kill_switch": bool, "notice": str}`; 409 `kill_switch_tripped` with `REFUSED_TEXT`; 500 `archive_failed` with the `ArchiveFailed` text. `removed` keeps its name, so the SPA's `ClearResult` reader keeps working.
  - `handle_trades_clear_history(reply, force: bool = False) -> None` — sends `describe_reset(result)`; on `ResetRefused` / `ArchiveFailed` sends `reply.send_error(str(exc))`.
  - `!trades clear history [force]` — prefix callback `trades_clear_history(ctx, mode: str = "")`, force iff `mode.lower() == "force"`.
  - `/trades-clear-history force:<bool>` — `slash_trades_clear_history(interaction, force: bool = False)`, option described `Reset even while the kill switch is tripped (it stays tripped)`; command description `Archive closed history, then reset realized P&L and drawdown (open trades kept)`.

**Decisions written down:**
- The admin SPA is not changed here (no force control, no notice display; a 409 reaches it as an error toast through its generic error path). That is the spec's scope: the override is named for the endpoint and the Discord command only.
- The slash command's payload changes (a new option and description), so the deploy that follows the merge runs the slash resync (`docs/deploy/DEPLOY_HETZNER.md`, the `resync_slash_commands.py` line). That is a deploy step, not part of this plan.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_clear_history_reset_api.py`:

```python
"""v189 A6: POST /api/v1/trades/clear-history is the archived full reset.

200 names the archive, the throttle and the kill switch; 409 while the kill
switch is tripped unless forced; 500 when the archive cannot be written.
"""
import pytest

from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.tracking import account_reset
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trade_commands import _no_live_quote, logged_in, seed  # noqa: F401  fixtures
from tests.admin.test_api_v1_trades import _trade
from tests.store_seed import seed_store

URL = "/api/v1/trades/clear-history"
KEYS = {"removed", "removed_plans", "archive", "throttle", "kill_switch", "notice"}


@pytest.fixture(autouse=True)
def _switch_off_by_default(admin_app, monkeypatch):
    """After admin_app's module reloads: a .env KILLSWITCH_DEFAULT_ON must not leak in."""
    monkeypatch.setattr("swingbot.config.KILLSWITCH_DEFAULT_ON", False)


def _book(seed):
    seed_store("account", {"base_balance": 10_000.0})
    seed(trades=[_trade("aaaaaaaaaaaaaaaa", status="open"),
                 _trade("cccccccccccccccc", status="win")])


def _statuses(client):
    return sorted(t["status"] for t in client.get("/api/v1/trades").get_json()["items"])


def test_the_reset_answers_with_its_archive_throttle_and_notice(seed, logged_in):
    _book(seed)
    r = logged_in.post(URL)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == KEYS
    assert (body["removed"], body["removed_plans"]) == (1, 0)
    assert body["archive"].startswith("account-reset-") and body["archive"].endswith("Z.json")
    assert "/" not in body["archive"] and "\\" not in body["archive"]      # a name, never a path
    assert (account_reset.archive_dir() / body["archive"]).exists()
    assert body["throttle"] == {"multiplier": 1.0, "paused": False}
    assert body["kill_switch"] is False
    assert body["notice"].startswith("Account reset: removed 1 closed trade(s) and 0 finished plan(s).")
    assert f"\nArchive: {body['archive']}\n" in body["notice"]
    assert _statuses(logged_in) == ["ACTIVE"]


def test_refused_while_the_kill_switch_is_tripped(seed, logged_in):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    r = logged_in.post(URL)
    assert_error(r, "kill_switch_tripped", 409)
    assert r.get_json()["error"]["message"] == account_reset.REFUSED_TEXT
    assert _statuses(logged_in) == ["ACTIVE", "CLOSED"]


@pytest.mark.parametrize("send", [
    lambda c: c.post(f"{URL}?force=true"),
    lambda c: c.post(f"{URL}?force=1"),
    lambda c: c.post(URL, json={"force": True}),
], ids=["query-true", "query-1", "json-true"])
def test_force_resets_past_the_kill_switch_and_leaves_it_on(seed, logged_in, send):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    r = send(logged_in)
    assert r.status_code == 200
    assert r.get_json()["kill_switch"] is True
    assert killswitch_repo().state()["on"] is True
    assert _statuses(logged_in) == ["ACTIVE"]


@pytest.mark.parametrize("send", [
    lambda c: c.post(f"{URL}?force=false"),
    lambda c: c.post(URL, json={"force": "yes"}),
    lambda c: c.post(URL, json=["force"]),
    lambda c: c.post(URL, data="force", content_type="text/plain"),
], ids=["query-false", "json-string", "json-list", "plain-text"])
def test_anything_but_an_explicit_true_is_not_force(seed, logged_in, send):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    assert_error(send(logged_in), "kill_switch_tripped", 409)


def test_a_failed_archive_is_a_500_that_says_nothing_was_deleted(seed, logged_in, monkeypatch):
    _book(seed)
    text = ("Reset aborted: the archive account-reset-x.json could not be written "
            "(disk full). Nothing was deleted.")

    def failing(*, force=False, now=None):
        raise account_reset.ArchiveFailed(text)

    monkeypatch.setattr(account_reset, "reset_closed_history", failing)
    r = logged_in.post(URL)
    assert_error(r, "archive_failed", 500)
    assert r.get_json()["error"]["message"] == text
    assert _statuses(logged_in) == ["ACTIVE", "CLOSED"]
```

Create `tests/commands/test_trades_clear_history_force.py`:

```python
"""v189 A6: `!trades clear history [force]` and `/trades-clear-history force:`
run the archived reset and reply with its description; a refusal or a failed
archive is an error reply."""
import asyncio

import pytest

from swingbot.commands import trades as trades_mod
from swingbot.core.tracking import account_reset

RESULT = account_reset.ResetResult(
    removed_trades=2, removed_plans=1,
    archive_path="/app/data/archives/account-reset-20261023T150000Z.json",
    throttle_multiplier=1.0, throttle_paused=False, kill_on=False,
    base_balance=10_000.0, reset_at="2026-10-23T15:00:00+00:00")
ARCHIVE_FAILED = ("Reset aborted: the archive account-reset-x.json could not be written "
                  "(disk full). Nothing was deleted.")


class _Reply:
    def __init__(self):
        self.sent, self.errors = [], []

    async def send(self, content=None, **kw):
        self.sent.append(content)

    async def send_error(self, text, *, ephemeral=True):
        self.errors.append(text)


def _patch_reset(monkeypatch, outcome):
    calls = []

    def fake(*, force=False, now=None):
        calls.append(force)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(account_reset, "reset_closed_history", fake)
    return calls


def _capture_handler(monkeypatch):
    seen = []

    async def handler(reply, force=False):
        seen.append(force)

    monkeypatch.setattr(trades_mod, "handle_trades_clear_history", handler)
    return seen


@pytest.mark.parametrize("force", [False, True])
def test_the_handler_runs_the_reset_and_replies_with_its_description(monkeypatch, force):
    calls = _patch_reset(monkeypatch, RESULT)
    reply = _Reply()
    asyncio.run(trades_mod.handle_trades_clear_history(reply, force=force))
    assert calls == [force]
    assert reply.sent == [account_reset.describe_reset(RESULT)]
    assert reply.errors == []


@pytest.mark.parametrize("error, text", [
    (account_reset.ResetRefused(account_reset.REFUSED_TEXT), account_reset.REFUSED_TEXT),
    (account_reset.ArchiveFailed(ARCHIVE_FAILED), ARCHIVE_FAILED),
], ids=["refused", "archive-failed"])
def test_a_refusal_or_a_failed_archive_is_an_error_reply(monkeypatch, error, text):
    _patch_reset(monkeypatch, error)
    reply = _Reply()
    asyncio.run(trades_mod.handle_trades_clear_history(reply))
    assert reply.errors == [text]
    assert reply.sent == []


@pytest.mark.parametrize("mode, force", [("", False), ("force", True), ("FORCE", True),
                                         ("forse", False)])
def test_the_prefix_word_force_maps_to_force(monkeypatch, mode, force):
    seen = _capture_handler(monkeypatch)

    async def no_tip(ctx, reply):
        return None

    monkeypatch.setattr(trades_mod, "CtxReply", lambda ctx: object())
    monkeypatch.setattr(trades_mod, "send_prefix_tip", no_tip)
    asyncio.run(trades_mod.trades_clear_history.callback(None, mode))
    assert seen == [force]


def test_the_slash_option_reaches_the_handler(monkeypatch):
    seen = _capture_handler(monkeypatch)
    monkeypatch.setattr(trades_mod, "InteractionReply", lambda interaction: object())
    asyncio.run(trades_mod.slash_trades_clear_history.callback(None, True))
    assert seen == [True]


def test_the_slash_command_describes_its_force_option():
    command = trades_mod.slash_trades_clear_history
    assert command.description == (
        "Archive closed history, then reset realized P&L and drawdown (open trades kept)")
    [param] = command.parameters
    assert (param.name, param.required) == ("force", False)
    assert param.description == "Reset even while the kill switch is tripped (it stays tripped)"
```

In `tests/commands/parity_cases/trades.py`:
- add `from swingbot.core.tracking import account_reset` to the imports;
- delete `_FakeLog.clear_history` (the handler no longer calls the trade log);
- add, after `_stub`:

```python
_RESET = account_reset.ResetResult(
    removed_trades=2, removed_plans=1,
    archive_path="/app/data/archives/account-reset-20261009T143000Z.json",
    throttle_multiplier=1.0, throttle_paused=False, kill_on=False,
    base_balance=10_000.0, reset_at="2026-10-09T14:30:00+00:00")


def _reset_stub(outcome=_RESET):
    """The trades stub plus a canned account reset (a ResetResult, or an
    exception to raise)."""
    base = _stub()

    def stub(monkeypatch):
        base(monkeypatch)

        def fake(*, force=False, now=None):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(trades_mod.account_reset, "reset_closed_history", fake)
    return stub
```

- replace the `trades_clear_history` row of `CASES` with:

```python
    ParityCase("trades_clear_history", trades_mod.handle_trades_clear_history, stub=_reset_stub()),
    ParityCase("trades_clear_history_force", trades_mod.handle_trades_clear_history,
               kwargs={"force": True}, stub=_reset_stub()),
    ParityCase("trades_clear_history_refused", trades_mod.handle_trades_clear_history,
               stub=_reset_stub(account_reset.ResetRefused(account_reset.REFUSED_TEXT)),
               expect="error"),
    ParityCase("trades_clear_history_archive_failed", trades_mod.handle_trades_clear_history,
               stub=_reset_stub(account_reset.ArchiveFailed(
                   "Reset aborted: the archive account-reset-x.json could not be written "
                   "(disk full). Nothing was deleted.")),
               expect="error"),
```

In `tests/admin/test_api_v1_trade_commands.py`, `test_clear_history_leaves_open_trades`: replace `assert r.get_json() == {"removed": 1}` with `assert r.get_json()["removed"] == 1` (the rest of the body is pinned in `tests/admin/test_clear_history_reset_api.py`).

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_clear_history_reset_api.py`
Expected: FAIL — the body is `{"removed": 1}` only (`set(body) == KEYS` fails), and with the switch tripped the route still calls V189-15's wrapper without `force`, whose uncaught `ResetRefused` answers 500, not 409 (and never 200 for the forced calls).

Run: `python scripts/dev/testrun.py file tests/commands/test_trades_clear_history_force.py`
Expected: FAIL — `handle_trades_clear_history()` takes no `force`, the prefix callback takes no `mode`, the slash command has no parameters.

- [ ] **Step 3: Implement the endpoint**

In `swingbot/admin/api_v1/trade_commands.py` add `from pathlib import Path` and `from swingbot.core.tracking import account_reset` to the imports, and replace the `clear_history` route with:

```python
_TRUE_WORDS = frozenset({"1", "true", "yes"})


def _force_requested() -> bool:
    """`?force=true` (or 1/yes), or a JSON object body `{"force": true}`.
    Anything else, including a JSON "yes", is no force."""
    if request.args.get("force", "").strip().lower() in _TRUE_WORDS:
        return True
    body = request.get_json(silent=True)
    return isinstance(body, dict) and body.get("force") is True


def _reset_payload(result: account_reset.ResetResult) -> dict:
    return {
        "removed": result.removed_trades,
        "removed_plans": result.removed_plans,
        "archive": Path(result.archive_path).name,
        "throttle": {"multiplier": result.throttle_multiplier, "paused": result.throttle_paused},
        "kill_switch": result.kill_on,
        "notice": account_reset.describe_reset(result),
    }


@api_v1.route("/trades/clear-history", methods=["POST"])
@require_auth
def clear_history():
    """v189 A6: the archived full reset. 409 while the kill switch is tripped
    unless forced; 500 when the archive cannot be written (nothing deleted)."""
    try:
        result = account_reset.reset_closed_history(force=_force_requested())
    except account_reset.ResetRefused as exc:
        return error("kill_switch_tripped", str(exc), 409)
    except account_reset.ArchiveFailed as exc:
        return error("archive_failed", str(exc), 500)
    return jsonify(_reset_payload(result))
```

The route calls `account_reset.reset_closed_history` through the module attribute, so the test's monkeypatch reaches it.

- [ ] **Step 4: Implement the Discord handler and both commands**

In `swingbot/commands/trades.py` add `from swingbot.core.tracking import account_reset` to the imports, then:

```python
async def handle_trades_clear_history(reply, force: bool = False) -> None:
    """v189 A6: archive the closed history, then reset realized P&L and the
    drawdown history to the base balance. Open trades are kept. Refused while
    the kill switch is tripped unless `force` (which never releases it)."""
    try:
        result = account_reset.reset_closed_history(force=force)
    except (account_reset.ResetRefused, account_reset.ArchiveFailed) as exc:
        await reply.send_error(str(exc))
        return
    await reply.send(account_reset.describe_reset(result))
```

The prefix command (keep v187's decorators above it):

```python
@trades_clear.command(name="history")
async def trades_clear_history(ctx, mode: str = ""):
    """Archive closed history, then reset realized P&L and drawdown. Open trades are kept.
    `!trades clear history force` resets even while the kill switch is tripped (it stays tripped)."""
    reply = CtxReply(ctx)
    await handle_trades_clear_history(reply, force=mode.lower() == "force")
    await send_prefix_tip(ctx, reply)
```

The slash command (keep v187's decorators):

```python
@bot.tree.command(name="trades-clear-history",
                  description="Archive closed history, then reset realized P&L and drawdown (open trades kept)")
@app_commands.describe(force="Reset even while the kill switch is tripped (it stays tripped)")
async def slash_trades_clear_history(interaction: discord.Interaction, force: bool = False):
    await handle_trades_clear_history(InteractionReply(interaction), force=force)
```

In the `!trades` help line (today `:107`), replace ``, `!trades clear history` to clear closed trade history.`` with ``, `!trades clear history` to archive and reset closed history (`force` while the kill switch is tripped).``

Each prefix and slash body still calls exactly one `handle_*` and the prefix body still calls `send_prefix_tip` (`tests/commands/test_slash_parity.py`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_clear_history_reset_api.py`
Expected: PASS (10 tests).

Run: `python scripts/dev/testrun.py file tests/commands/test_trades_clear_history_force.py`
Expected: PASS (10 tests).

- [ ] **Step 6: Run the neighbours and the gate**

Run each:
`python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py`
`python scripts/dev/testrun.py file tests/commands/test_reply_parity.py`
`python scripts/dev/testrun.py file tests/commands/test_slash_parity.py`
`python scripts/dev/testrun.py file tests/commands/test_state_command_gates.py`
`python scripts/dev/testrun.py file tests/commands/test_help_catalog.py`
Expected: PASS each (the slash-payload check accepts the new option: name, 1-100 char description, not required).

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_force_requested` 3, `clear_history` 3, `handle_trades_clear_history` 2).

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/trade_commands.py swingbot/commands/trades.py tests/commands/parity_cases/trades.py tests/admin/test_api_v1_trade_commands.py tests/admin/test_clear_history_reset_api.py tests/commands/test_trades_clear_history_force.py
git commit -m "feat(trades): clear history answers with the reset's archive, throttle and kill switch; force on the endpoint and both Discord commands (v189 V189-16)"
```

### Task V189-17: Restore script and the deploy-doc procedure

**Model:** sonnet — the inverse of V189-15 over the same repositories, with one refusal rule and one balance correction both pinned by round-trip tests, plus a thin dry-run-by-default CLI and one doc paragraph.

**Spec:** D4 A6 "**Rollback** is a documented restore: `scripts/ops/restore_account_reset.py <archive>` … re-inserts the archived rows in one transaction. It refuses if a later reset has run since. `docs/deploy/DEPLOY_HETZNER.md` gets the one-paragraph procedure."; D3 test bullet "The restore script round-trips the archive, and refuses after a later reset"; Correction 9 (dry run by default, `--apply` to write, tested under `tests/scripts/`; the paragraph goes at the end of `## PostgreSQL (the only store)`); this part's header decision 4.

**Files:**
- Modify: `swingbot/core/tracking/account_reset.py` (add `restore_archive` and its helpers; import `account_balance_history`)
- Create: `scripts/ops/restore_account_reset.py`
- Create: `tests/scripts/test_restore_account_reset.py`
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (one paragraph after `**Off-VM copy and stable snapshots (v120).**`, before `## Useful one-liners on the server`; re-find with `grep -n "Off-VM copy and stable snapshots\|## Useful one-liners" docs/deploy/DEPLOY_HETZNER.md`)

**Interfaces:**
- Consumes (V189-15): `ARCHIVE_VERSION`, `RESET_REASON`, `CHILD_TABLES`, `BOOK_LOCK`, `reset_closed_history`, the archive layout; (V189-7) `account._sum_realized_pnl(conn=)`, `load_account_config(conn=)`, `save_account_config(cfg, conn=)`, `run_after_commit`; (V189-5) `transaction(lock_timeout_ms=)`; `Repository.insert/patch/delete(conn=)`, `plans_repo().insert`, `trades_repo().insert`, `account_repo().history(conn=)` (exist). The test reuses V189-15's `book` fixture and constants from `tests/tracking/test_account_reset.py`.
- Produces:
  - `account_reset.restore_archive(path: str | Path, *, apply: bool = False) -> dict` — the summary `{"archive": <file name>, "reset_at": str, "trades": int, "plans": int, "account_balance_history": int, "starred_plans": int, "plan_followers": int, "plan_notifications": int, "later_points": int, "balance_shift": float | None, "applied": bool}` (`balance_shift` is None on a dry run). Raises `ValueError` for a file that is not a version-1 archive, and when the history does not hold exactly one `account_reset` point naming this archive (a later reset ran, or this archive was already restored).
  - `scripts/ops/restore_account_reset.py` — `main(argv: list[str] | None = None) -> int`: prints the summary as JSON to stdout and returns 0; prints `refused: <reason>` to stderr and returns 1 on `ValueError` / `OSError`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_restore_account_reset.py`:

```python
"""v189 A6 rollback: an account-reset archive restores the book it came from.

Uses V189-15's seeded book (base 10,000; C1 +2,000 and C2 -3,000 closed;
balance 9,000 before the reset).
"""
import json
from datetime import timedelta

import pytest

from scripts.ops import restore_account_reset as rar
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.plans import plans_repo
from swingbot.core.db.repositories.starred import starred_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.db.schema import plan_notifications
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import account_reset as ar
from tests.store_seed import seed_store
from tests.tracking.test_account_reset import (  # noqa: F401  (book is a fixture)
    ARCHIVE, NOW, _state, _trade_record, book)

LATER = NOW + timedelta(hours=1)
LATER_ARCHIVE = "account-reset-20261023T160000Z.json"


def _full_state():
    """Every restored table plus the computed balance, order-independent."""
    return (
        sorted((t["trade_id"], t["status"], t.get("realized_pnl_amount"))
               for t in trades_repo().list_all()),
        sorted((p["plan_id"], p["status"], len(p.get("legs_realized") or []))
               for p in plans_repo().list_all()),
        [(h["ts"], h["balance"]) for h in account_module.get_balance_history()],
        sorted(starred_repo().ids()),
        followers_repo().followers("P-C"),
        sorted((n["plan_id"], n["event"])
               for n in Repository(plan_notifications, key="plan_id").list_all()),
        account_module.load_account_config()["balance"],
    )


def test_a_dry_run_reports_and_writes_nothing(book):
    ar.reset_closed_history(now=NOW)
    after_reset = _state()
    summary = ar.restore_archive(book / ARCHIVE)
    assert summary == {
        "archive": ARCHIVE, "reset_at": "2026-10-23T15:00:00+00:00", "trades": 2, "plans": 2,
        "account_balance_history": 3, "starred_plans": 1, "plan_followers": 1,
        "plan_notifications": 1, "later_points": 0, "balance_shift": None, "applied": False}
    assert _state() == after_reset


def test_apply_round_trips_the_archive(book):
    before = _full_state()
    ar.reset_closed_history(now=NOW)
    summary = ar.restore_archive(book / ARCHIVE, apply=True)
    assert (summary["applied"], summary["balance_shift"]) == (True, -1_000.0)
    assert _full_state() == before
    assert account_module.load_account_config()["balance"] == 9_000.0


def test_points_written_after_the_reset_carry_the_restored_pnl(book):
    ar.reset_closed_history(now=NOW)
    # A trade closes after the reset: +500 on top of the reseeded 10,000.
    seed_store("trades", [_trade_record("C3", "win", exit_price=105.0, pnl=500.0)])
    account_repo().append_history({"ts": "2026-10-24T20:00:00+00:00", "balance": 10_500.0,
                                   "pnl_amount": 500.0, "trade_id": "C3"})
    summary = ar.restore_archive(book / ARCHIVE, apply=True)
    assert (summary["later_points"], summary["balance_shift"]) == (1, -1_000.0)
    assert [h["balance"] for h in account_module.get_balance_history()] == [
        10_000.0, 12_000.0, 9_000.0, 9_500.0]
    assert account_module.load_account_config()["balance"] == 9_500.0     # 10,000 + 2,000 - 3,000 + 500


def test_refused_after_a_later_reset_until_the_newest_is_restored_first(book):
    before = _full_state()
    ar.reset_closed_history(now=NOW)
    ar.reset_closed_history(now=LATER)
    after_two_resets = _state()
    with pytest.raises(ValueError, match="later reset"):
        ar.restore_archive(book / ARCHIVE, apply=True)
    assert _state() == after_two_resets
    ar.restore_archive(book / LATER_ARCHIVE, apply=True)
    ar.restore_archive(book / ARCHIVE, apply=True)
    assert _full_state() == before


def test_a_second_apply_of_the_same_archive_is_refused(book):
    ar.reset_closed_history(now=NOW)
    ar.restore_archive(book / ARCHIVE, apply=True)
    restored = _state()
    with pytest.raises(ValueError, match="later reset"):
        ar.restore_archive(book / ARCHIVE, apply=True)
    assert _state() == restored


def test_a_file_that_is_not_an_archive_is_refused(tmp_path):
    path = tmp_path / "account-reset-x.json"
    path.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a version-1 account-reset archive"):
        ar.restore_archive(path)


def test_the_script_dry_runs_by_default_and_applies_with_the_flag(book, capsys):
    ar.reset_closed_history(now=NOW)
    assert rar.main([str(book / ARCHIVE)]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False
    assert sorted(t["trade_id"] for t in trades_repo().list_all()) == ["O1", "O2"]
    assert rar.main([str(book / ARCHIVE), "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is True
    assert sorted(t["trade_id"] for t in trades_repo().list_all()) == ["C1", "C2", "O1", "O2"]


@pytest.mark.parametrize("make_path", [
    lambda book: book / ARCHIVE,                    # refused: a later reset ran
    lambda book: book / "no-such-archive.json",     # missing file
], ids=["later-reset", "missing-file"])
def test_the_script_exits_1_with_the_reason(book, capsys, make_path):
    ar.reset_closed_history(now=NOW)
    ar.reset_closed_history(now=LATER)
    assert rar.main([str(make_path(book)), "--apply"]) == 1
    assert capsys.readouterr().err.startswith("refused: ")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_restore_account_reset.py`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'scripts.ops.restore_account_reset'`.

- [ ] **Step 3: Add `restore_archive` to `swingbot/core/tracking/account_reset.py`**

Extend the schema import to `from swingbot.core.db.schema import account_balance_history, plan_followers, plan_notifications, plans, starred_plans`, then append:

```python
# --- rollback (scripts/ops/restore_account_reset.py) ------------------------------

_COUNTED = ("trades", "plans", "account_balance_history", *CHILD_TABLES)


def _load_archive(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != ARCHIVE_VERSION:
        raise ValueError(f"{path.name}: not a version-{ARCHIVE_VERSION} account-reset archive")
    return payload


def _reseed_point(history: list[dict], archive_name: str) -> dict:
    """This archive's reseed point. Any other picture means a later reset ran
    (it deleted this point) or this archive was already restored."""
    points = [entry for entry in history if entry.get("reason") == RESET_REASON]
    if len(points) != 1 or points[0].get("archive") != archive_name:
        raise ValueError(f"refusing to restore {archive_name}: a later reset has run since, or "
                         "this archive was already restored; restore the newest archive first")
    return points[0]


def _insert_rows(payload: dict, *, conn) -> None:
    """Plans before the rows that reference them; then trades and history."""
    for record in payload["plans"]:
        plans_repo().insert(record, conn=conn)
    for name, table in CHILD_TABLES.items():
        repo = Repository(table, key="plan_id")
        for record in payload[name]:
            repo.insert(record, conn=conn)
    for record in payload["trades"]:
        trades_repo().insert(record, conn=conn)
    history = Repository(account_balance_history, key="ts")
    for record in payload["account_balance_history"]:
        history.insert(record, conn=conn)


def _apply_restore(payload: dict, reseed: dict, later: list[dict], *, conn) -> float:
    """Drop the reseed point, re-insert the archive, and add the restored
    realized P&L to every point written since the reset (each was computed as
    base + realized without it). Returns that shift."""
    history = Repository(account_balance_history, key="ts")
    before = account_module._sum_realized_pnl(conn=conn)
    history.delete(reseed["ts"], conn=conn)
    _insert_rows(payload, conn=conn)
    shift = round(account_module._sum_realized_pnl(conn=conn) - before, 2)
    for point in later:
        history.patch(point["ts"], {"balance": round(float(point["balance"]) + shift, 2)},
                      conn=conn)
    cfg = account_module.load_account_config(conn=conn)
    account_module.save_account_config({**cfg, "balance_history": []}, conn=conn)
    return shift


def restore_archive(path: str | Path, *, apply: bool = False) -> dict:
    """Undo one reset from its archive (spec D4 A6 rollback): one transaction,
    the book locked (EXCLUSIVE, ADMIN timeout) when applying. A dry run (the
    default) only checks and counts. Raises ValueError on a foreign file or
    when a later reset has run since."""
    archive = Path(path)
    payload = _load_archive(archive)
    with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
        if apply:
            conn.execute(BOOK_LOCK)
        history = account_repo().history(conn=conn)
        reseed = _reseed_point(history, archive.name)
        later = [entry for entry in history if entry["ts"] > reseed["ts"]]
        summary = {"archive": archive.name, "reset_at": payload["reset_at"],
                   **{key: len(payload[key]) for key in _COUNTED},
                   "later_points": len(later), "balance_shift": None, "applied": apply}
        if apply:
            summary["balance_shift"] = _apply_restore(payload, reseed, later, conn=conn)
    if apply:
        run_after_commit([_refresh_snapshot_safely])
        log.info("account reset restored from %s: %d trade(s), %d plan(s), balance shift %.2f "
                 "on %d later point(s)", archive, summary["trades"], summary["plans"],
                 summary["balance_shift"], summary["later_points"])
    return summary
```

`account_repo().history(conn=)` returns repository records whose `ts` is the raw column value (a `datetime`), so `entry["ts"] > reseed["ts"]` compares instants and `delete(reseed["ts"])` / `patch(point["ts"], …)` hit the exact rows. A failed insert (a row that already exists) raises inside the transaction and rolls the whole restore back.

- [ ] **Step 4: Create `scripts/ops/restore_account_reset.py`**

```python
#!/usr/bin/env python3
"""Undo one account reset (v189 A6) from its archive.

`!trades clear history`, `/trades-clear-history` and the admin "Clear history"
action archive every row they delete to data/archives/account-reset-<UTC>.json.
This re-inserts one archive's rows in one transaction, removes that reset's
reseed point and adds the restored realized P&L to every balance point written
since. It refuses when a later reset has run since: restore the newest archive
first. Nothing is written unless --apply is passed; the default is a dry run.

    python scripts/ops/restore_account_reset.py data/archives/account-reset-20261023T150000Z.json
    python scripts/ops/restore_account_reset.py data/archives/account-reset-20261023T150000Z.json --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.tracking.account_reset import restore_archive  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", help="path to an account-reset-<UTC>.json archive")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args(argv)
    try:
        summary = restore_archive(args.archive, apply=args.apply)
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not args.apply:
        print("dry run: nothing written; rerun with --apply to restore", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Mark it executable like its siblings: `git update-index --chmod=+x scripts/ops/restore_account_reset.py` after `git add`.

- [ ] **Step 5: Add the deploy-doc paragraph**

In `docs/deploy/DEPLOY_HETZNER.md`, insert after the `**Off-VM copy and stable snapshots (v120).**` paragraph and before `## Useful one-liners on the server` (one blank line either side):

```markdown
**Undoing an account reset (v189).** Clearing history (`!trades clear history`, `/trades-clear-history`, the admin "Clear history" action) is a full reset: it writes every closed trade, finished plan (with its stars, followers and notification claims) and balance-history point to `data/archives/account-reset-<UTC>.json` on the data volume, deletes them in one transaction, and reseeds the balance history with one point at the base balance, so the drawdown peak and the throttle restart there. It is refused while the kill switch is tripped unless forced (`force=true`, `!trades clear history force`), and it never releases the switch. To undo one, dry-run first: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/restore_account_reset.py data/archives/<file>.json"`, check the counts, then rerun with `--apply`. The restore re-inserts the archived rows in one transaction, removes that reset's reseed point and adds the restored realized P&L to every balance point written since; it refuses when a later reset has run since (restore the newest archive first). Archives are git-ignored and are not in the nightly `pg_dump`: copy one off the VM by hand if it must outlive the VM.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_restore_account_reset.py`
Expected: PASS (9 tests).

Run: `python scripts/dev/testrun.py file tests/tracking/test_account_reset.py`
Expected: PASS (15 tests; the reset side is unchanged).

- [ ] **Step 7: Run the neighbours and the gate**

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`restore_archive` 5, `_insert_rows` 6, `_apply_restore` 2, `main` 3).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/tracking/account_reset.py scripts/ops/restore_account_reset.py tests/scripts/test_restore_account_reset.py docs/deploy/DEPLOY_HETZNER.md
git update-index --chmod=+x scripts/ops/restore_account_reset.py
git commit -m "feat(ops): restore_account_reset.py undoes one reset from its archive; deploy-doc procedure (v189 V189-17)"
```
