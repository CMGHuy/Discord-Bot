# v173 Execution fidelity, part 1: the close stamp, `manual_bulk` and the retag

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-3:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §1 (stamping a manual close) and §2 (re-tagging the 2026-09-30 bulk clear)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`) and the task ledger. Every task below implicitly includes those Global Constraints.

Tasks: V173-1..V173-5. V173-1 creates the worktree every branch task uses. V173-4 runs on `main` against production (read-only) and must finish before V173-5 starts. V173-5 was revised on 2026-10-19 (`FOR UPDATE`, `down_revision = "v172_001"`, `v173_002` chaining on it): index § Revision 2026-10-19.

**Tests never touch a database** (Global Constraints): every new test here uses plain dataclasses, dicts, fakes and monkeypatched seams. No `seed_store`, no `db_conn`, no `db_engine_empty`, never the production replica.

# Phase 1: Stamp and reason

### Task V173-1: Worktree; `record_transition(..., extra=)`

**Model:** haiku — one optional parameter, fully specified

**Files:**
- Modify: `swingbot/core/planning/plan_types.py:217-224` (`record_transition`)
- Create: `tests/planning/test_record_transition_extra.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None, at: str | None = None, extra: dict | None = None) -> None`. With `extra=None` the appended entry is exactly `{"status", "reason", "at"}` (today's shape); otherwise it is `{"status", "reason", "at", **extra}`. V173-3 calls it with `extra={"override": stamp}`. `plan_engine.py` re-exports the same function object, so no edit there.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill first. Then, from the main tree `$R = E:/Documents/Private/Projects/Discord-Bot`:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
```

If `.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides` is listed, reuse it and skip the `add`. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-18-v173-execution-fidelity-overrides -b 2026-10-18-v173-execution-fidelity-overrides main
```

From here on `$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path in this task is under `$WT`.

- [ ] **Step 2: Write the failing test**

Create `$WT/tests/planning/test_record_transition_extra.py`:

```python
"""v173 §1: record_transition(extra=) merges extra keys into the appended entry."""
import pytest

from swingbot.core.planning import plan_engine
from swingbot.core.planning.plan_types import PlanStatus, record_transition
from tests.planning.test_plan_engine_model import _plan


def _active():
    plan = _plan()
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="2026-10-01T14:00:00+00:00")
    return plan


def test_without_extra_the_entry_keeps_exactly_three_keys():
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="2026-10-02T15:00:00+00:00")
    assert plan.status_history[-1] == {"status": "CLOSED", "reason": "manual",
                                       "at": "2026-10-02T15:00:00+00:00"}


def test_extra_is_merged_into_the_entry():
    plan = _active()
    stamp = {"exit_price": 101.5, "price_source": "quote",
             "quote_ts": "2026-10-02T15:00:00+00:00", "bars_asof": "2026-10-01"}
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                      at="2026-10-02T15:00:00+00:00", extra={"override": stamp})
    assert plan.status_history[-1] == {"status": "CLOSED", "reason": "manual",
                                       "at": "2026-10-02T15:00:00+00:00", "override": stamp}
    assert plan.status == PlanStatus.CLOSED


def test_extra_none_value_is_kept_as_a_key():
    """A failed stamp is written as override: null, not left out."""
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t", extra={"override": None})
    assert "override" in plan.status_history[-1]
    assert plan.status_history[-1]["override"] is None


def test_an_illegal_transition_still_raises_and_appends_nothing():
    plan = _plan()   # PENDING
    with pytest.raises(ValueError):
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t",
                          extra={"override": None})
    assert plan.status_history == []
    assert plan.status == PlanStatus.PENDING


def test_extra_cannot_overwrite_the_three_core_keys():
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t",
                      extra={"status": "X", "reason": "Y", "at": "Z", "override": None})
    entry = plan.status_history[-1]
    assert (entry["status"], entry["reason"], entry["at"]) == ("CLOSED", "manual", "t")


def test_plan_engine_reexports_the_same_function():
    assert plan_engine.record_transition is record_transition
```

- [ ] **Step 3: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_record_transition_extra.py
```

Expected: FAIL — `TypeError: record_transition() got an unexpected keyword argument 'extra'` in the extra tests (the no-extra, illegal and re-export tests pass).

If `PlanStatus` is not importable from `plan_types` (it is defined there today; check with `git -C $WT grep -n "^class PlanStatus" swingbot/core/planning/plan_types.py`), import it from `swingbot.core.planning.plan_engine` instead.

- [ ] **Step 4: Implement**

Replace `record_transition` in `$WT/swingbot/core/planning/plan_types.py` (lines 217-224) with:

```python
def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None, extra: dict | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine.

    `extra` (v173) adds keys to the appended entry -- today only the manual
    close's `override` stamp. The three core keys always win, so an `extra`
    can never rewrite what the transition itself says.
    """
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    entry = {**(extra or {}), "status": new_status, "reason": reason, "at": at}
    plan.status_history.append(entry)
```

Key order note: `{**extra, "status", "reason", "at"}` puts `override` first in the dict. JSON consumers do not depend on key order, but the tests above compare dicts (order-insensitive), so this is fine.

- [ ] **Step 5: Run the test and the existing transition tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_record_transition_extra.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_plan_engine_model.py
```

Expected: both PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/plan_types.py
```

Expected: no output for `record_transition` (it stays at CC 3).

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/planning/plan_types.py tests/planning/test_record_transition_extra.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): record_transition takes extra keys for the transition entry"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-2: Teach `manual_bulk` to its readers

**Model:** haiku — a dict entry and a label, fixed by the spec

**Files:**
- Modify: `swingbot/core/analytics/partials.py:30-33` (`_REASON_BUCKET`)
- Modify: `tests/analytics/test_partials.py` (append two tests)
- Modify: `frontend/src/app/workspaces/trades/exit-reasons.ts:5-20` (`EXIT_REASON_LABELS`)
- Modify: `frontend/src/app/workspaces/trades/exit-reasons.spec.ts` (append one `describe`)

**Interfaces:**
- Consumes: nothing (runs in Wave A after V173-1 created `$WT`).
- Produces: `partials._REASON_BUCKET["manual_bulk"] == "manual"` (so `outcome_bucket` puts a bulk-closed runner in the `manual` bucket and `STOP_EXIT_REASONS` membership in `runner_path.py:111` is unaffected); `EXIT_REASON_LABELS['manual_bulk'] === 'Bulk close'`, read by V173-15's three-width check on a re-tagged plan.

Readers left unchanged on purpose (spec §1, Global Constraints): `scripts/ops/export_book_rows.sh` (CANCELLED reasons only), `trades.py`, `lifecycle_embeds.py` (legacy trade `status`), `session_expiry.cancel_reason` (CANCELLED only). `manual` itself gets no label here: the spec names only `manual_bulk`, and `manual` keeps printing as written.

- [ ] **Step 1: Write the failing Python tests**

Append to `$WT/tests/analytics/test_partials.py` (it already imports `pa`, `PlanStatus`, and defines `_trade`, `_book`, `MANUAL`):

```python
# -- v173: a bulk clear is a manual close for the outcome buckets ------------

def test_a_bulk_cleared_runner_lands_in_the_manual_bucket():
    plan = _trade("Z", reason="manual_bulk")
    assert pa.outcome_bucket(plan) == "manual"


def test_bulk_and_single_manual_closes_share_one_bucket_row():
    book = [*_book(), _trade("Z", reason="manual_bulk")]
    rows = {row["bucket"]: row for row in pa.build_report(book, manual_exits={**MANUAL, "Z": 107.5})["outcomes"]}
    assert rows["manual"]["n"] == 2
    assert "other" not in rows
    assert rows["manual"]["avg_runner_r"] == pytest.approx((2.5 + 1.5) / 2)
```

(`_trade` gives entry 100, stop 95, so a manual runner exit at 107.5 is +1.5R; `D` stays at 112.5 = +2.5R.)

- [ ] **Step 2: Run them to verify they fail**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_partials.py
```

Expected: the two new tests FAIL (`'other' == 'manual'`, and an `other` row present); every existing test passes.

- [ ] **Step 3: Implement the Python side**

In `$WT/swingbot/core/analytics/partials.py`, lines 30-33 become:

```python
_REASON_BUCKET = {
    "tp1_runner_tp2": "tp2", "tp1_runner_trail": "trail", "tp1_runner_be": "floor",
    "tp1_runner_progress_stall": "stall", "time_exit": "time", "manual": "manual",
    # v173: a bulk clear is still a human close; it is told apart only by the
    # override-fidelity report, never by the partials buckets.
    "manual_bulk": "manual",
}
```

- [ ] **Step 4: Run the Python tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_partials.py
```

Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Write the failing frontend test**

Append to `$WT/frontend/src/app/workspaces/trades/exit-reasons.spec.ts`, after the last `describe`:

```typescript
describe('manual_bulk (v173)', () => {
  it('labels a bulk clear "Bulk close"', () => {
    expect(EXIT_REASON_LABELS['manual_bulk']).toBe('Bulk close');
    expect(reasonLabel('manual_bulk')).toBe('Bulk close');
  });

  it('uses it as the history fallback for a bulk-closed plan with no leg reason', () => {
    const history = [event('ACTIVE', 'filled'), event('CLOSED', 'manual_bulk')];
    expect(exitReasonLabel([], history, null)).toBe('Bulk close');
  });

  it('leaves a single manual close printed as written', () => {
    expect(reasonLabel('manual')).toBe('manual');
  });
});
```

- [ ] **Step 6: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/exit-reasons.spec.ts
```

Expected: the first two new tests FAIL (`expected 'manual_bulk' to be 'Bulk close'`); the third passes.

If `node_modules` is missing in the worktree, run `npm --prefix $WT/frontend ci` once first.

- [ ] **Step 7: Implement the label**

In `$WT/frontend/src/app/workspaces/trades/exit-reasons.ts`, add one entry at the end of `EXIT_REASON_LABELS` (after `'reversed': 'Reversed',`):

```typescript
  'reversed': 'Reversed',
  'manual_bulk': 'Bulk close',
};
```

- [ ] **Step 8: Run the frontend test**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/exit-reasons.spec.ts
```

Expected: PASS, including the existing `stores only lower-case, trimmed keys` test.

- [ ] **Step 9: Commit on the branch (two scoped commits)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/partials.py tests/analytics/test_partials.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): partials bucket a manual_bulk close as manual"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/workspaces/trades/exit-reasons.ts frontend/src/app/workspaces/trades/exit-reasons.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): trade page labels a manual_bulk close 'Bulk close'"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```


### Task V173-3: Stamp every manual close; bulk clears say `manual_bulk`; one price for stamp and trade

**Model:** sonnet — admin command plus one tracking kwarg, behaviour given by the spec

**Files:**
- Modify: `swingbot/admin/api_v1/trade_commands.py:89-108` (`_close_plan`, plus four new helpers above it) and `:258` (`close_open`'s call)
- Modify: `swingbot/core/tracking/performance.py:1417-1462` (`TradeLog.close_trade_manual`, plus one module helper)
- Create: `tests/admin/test_close_plan_override_stamp.py`
- Create: `tests/tracking/test_close_trade_manual_exit_price.py`
- Modify: `tests/admin/test_api_v1_trade_commands.py` (the `flaky` stub at `:345` gains `reason`; one autouse offline-quote fixture)
- Modify: `tests/admin/test_trade_commands_runner_path.py` (the same autouse `_no_live_quote` fixture: no test may reach the network)

**Interfaces:**
- Consumes: `record_transition(plan, new_status, reason=None, at=None, extra: dict | None = None)` from V173-1.
- Produces:
  - `_close_plan(store, plan, reason: str = "manual") -> None`. `close_trade` calls `_close_plan(store, plan)`; `close_open` calls `_close_plan(store, plan, "manual_bulk")` positionally.
  - `_override_stamp(ticker: str) -> dict | None`: keys exactly `exit_price, price_source, quote_ts, bars_asof`; `None` only when building it raised. Never raises.
  - The CLOSED transition entry carries key `override` (the stamp dict, or `None`). V173-7..V173-9 read it: `override_entry(plan)["override"]`.
  - `TradeLog.close_trade_manual(trade_id, reason="manual", *, exit_price: float | None = None) -> bool`.

What the spec fixes (§1, Global Constraints "The `override` stamp" and "One price for stamp and trade"):

- The quote is fetched **once**, in `_close_plan`, through `swingbot.core.marketdata.data.get_current_price_detail(ticker, allow_stale=False)` looked up on the module at call time (so tests monkeypatch it there). `quote_ts` is `datetime.now(timezone.utc).isoformat()` taken right after the fetch.
- No quote → last `Close` of `rp.cached_daily_bars(ticker)`, `price_source="bar_close"`, `quote_ts=None`. Neither → `exit_price=None`, `price_source="none"`. `bars_asof` = ISO date of that cache's last bar, or `None`.
- A quote fetch that raises counts as "no quote" (one warning) and falls back to the bar close. Any other exception while building the stamp (the cache read, a malformed frame) logs one warning and writes `"override": None`; the close goes ahead either way.
- The linked paper trade is settled at the stamp's price when it came from a quote (`exit_price=` passed in, no second fetch). A `bar_close` or `none` stamp passes `exit_price=None`, so `close_trade_manual` keeps today's own fetch: a daily close is never written as a live fill.
- Nothing else changes: the linked trade's `close_reason` stays `"manual (plan close, admin UI)"` on both paths, `stamp_runner_path` still runs for a PARTIAL plan, `store.update` and `_queue_notify` are unchanged.

- [ ] **Step 1: Write the failing `_close_plan` tests**

Create `$WT/tests/admin/test_close_plan_override_stamp.py`. It calls `_close_plan` and the two view functions directly (through `__wrapped__`, past `require_auth`) with fakes for the store, the trade log, the quote and the cache. No database, no network, no Flask test client.

```python
"""v173 §1: a manual close stamps its exit price, the price's source, the
quote time and the bar-cache date; a bulk clear says `manual_bulk`.

Everything is faked -- the plan store, the trade log, the live quote and the
daily cache -- so no test here opens a database or the network."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from flask import Flask

from swingbot.admin.api_v1 import trade_commands as tc
from swingbot.core.analytics import runner_path as rp
from swingbot.core.marketdata import data as md
from swingbot.core.marketdata.data import PriceQuote
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from tests.planning.test_plan_engine_model import _plan

PLAN_ID = "55555555-5555-4555-8555-555555555555"
TRADE_ID = "bbbbbbbbbbbbbbbb"
FILL_AT = "2026-10-14T14:00:00+00:00"


def _bars(last_close=101.5):
    index = pd.DatetimeIndex(["2026-10-15", "2026-10-16"])
    return pd.DataFrame({"Open": [100.0, 100.5], "High": [101.0, 102.0], "Low": [99.0, 100.0],
                         "Close": [100.2, last_close], "Volume": [1e6, 1e6]}, index=index)


def _active(plan_id=PLAN_ID, ticker="AAPL"):
    plan = _plan(plan_id=plan_id, ticker=ticker, entry_price=101.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="filled", at=FILL_AT)
    return plan


def _partial():
    plan = _active()
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="2026-10-15T15:00:00+00:00")
    return plan


class FakeStore:
    def __init__(self, plans=()):
        self.plans = {plan.plan_id: plan for plan in plans}
        self.updated = []

    def all(self):
        return list(self.plans.values())

    def get(self, plan_id):
        return self.plans.get(plan_id)

    def update(self, plan):
        self.updated.append(plan.plan_id)


class FakeTradeLog:
    trades: list[dict] = []
    closes: list[dict] = []

    def get_trades(self, status=None, limit=None):
        return list(FakeTradeLog.trades)

    def close_trade_manual(self, trade_id, reason="manual", *, exit_price=None):
        FakeTradeLog.closes.append({"id": trade_id, "reason": reason, "exit_price": exit_price})
        return True


@pytest.fixture
def env(monkeypatch):
    """Offline seams. `env["quote"]` / `env["bars"]` are read at call time, so a
    test sets them before closing. An Exception value is raised instead."""
    state = {"quote": PriceQuote(123.45, False), "bars": _bars(), "quote_calls": [],
             "notified": [], "runner_stamps": []}

    def quote(ticker, *args, **kwargs):
        state["quote_calls"].append((ticker, kwargs.get("allow_stale")))
        value = state["quote"]
        if isinstance(value, Exception):
            raise value
        return value

    def bars(ticker):
        value = state["bars"]
        if isinstance(value, Exception):
            raise value
        return value

    FakeTradeLog.trades = [{"id": TRADE_ID, "plan_id": PLAN_ID, "status": "open"}]
    FakeTradeLog.closes = []
    monkeypatch.setattr(md, "get_current_price_detail", quote)
    monkeypatch.setattr(rp, "cached_daily_bars", bars)
    monkeypatch.setattr(rp, "stamp_runner_path",
                        lambda plan, fn, *, source="live": state["runner_stamps"].append(plan.plan_id))
    monkeypatch.setattr(tc, "TradeLog", FakeTradeLog)
    monkeypatch.setattr(tc, "_queue_notify", state["notified"].append)
    return state


def _closed_entry(plan):
    entry = plan.status_history[-1]
    assert entry["status"] == "CLOSED"
    return entry


# --- the stamp ----------------------------------------------------------------

def test_a_single_close_stamps_manual_with_the_four_override_fields(env):
    plan = _active()
    store = FakeStore([plan])
    tc._close_plan(store, plan)

    entry = _closed_entry(plan)
    assert entry["reason"] == "manual"
    stamp = entry["override"]
    assert set(stamp) == {"exit_price", "price_source", "quote_ts", "bars_asof"}
    assert stamp["exit_price"] == pytest.approx(123.45)
    assert stamp["price_source"] == "quote"
    assert stamp["bars_asof"] == "2026-10-16"
    assert datetime.fromisoformat(stamp["quote_ts"]).utcoffset() is not None
    assert plan.status == PlanStatus.CLOSED
    assert store.updated == [PLAN_ID]


def test_the_quote_is_fetched_once_and_never_stale(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert env["quote_calls"] == [("AAPL", False)]


def test_the_linked_trade_settles_at_the_stamped_quote(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert FakeTradeLog.closes == [{"id": TRADE_ID, "reason": "manual (plan close, admin UI)",
                                    "exit_price": pytest.approx(123.45)}]
    assert _closed_entry(plan)["override"]["exit_price"] == FakeTradeLog.closes[0]["exit_price"]


def test_a_bulk_close_stamps_manual_bulk(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan, "manual_bulk")
    entry = _closed_entry(plan)
    assert entry["reason"] == "manual_bulk"
    assert entry["override"]["price_source"] == "quote"
    assert FakeTradeLog.closes[0]["reason"] == "manual (plan close, admin UI)"


def test_no_quote_falls_back_to_the_cached_daily_close(env):
    env["quote"] = None
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] == {
        "exit_price": pytest.approx(101.5), "price_source": "bar_close",
        "quote_ts": None, "bars_asof": "2026-10-16"}
    # A daily close is never written to the trade as a live fill.
    assert FakeTradeLog.closes[0]["exit_price"] is None


def test_a_quote_that_raises_is_treated_as_no_quote(env):
    env["quote"] = TimeoutError("yfinance down")
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"]["price_source"] == "bar_close"


def test_no_quote_and_no_cache_records_source_none(env):
    env["quote"], env["bars"] = None, None
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] == {
        "exit_price": None, "price_source": "none", "quote_ts": None, "bars_asof": None}


def test_a_nan_last_close_is_no_price(env):
    env["quote"], env["bars"] = None, _bars(last_close=float("nan"))
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    stamp = _closed_entry(plan)["override"]
    assert (stamp["price_source"], stamp["exit_price"], stamp["bars_asof"]) == ("none", None, "2026-10-16")


def test_an_unreadable_cache_writes_a_null_stamp_and_still_closes(env):
    env["bars"] = OSError("bad csv")
    plan = _active()
    store = FakeStore([plan])
    tc._close_plan(store, plan)
    entry = _closed_entry(plan)
    assert "override" in entry and entry["override"] is None
    assert plan.status == PlanStatus.CLOSED
    assert store.updated == [PLAN_ID]
    assert env["notified"] and env["notified"][0]["status"] == PlanStatus.CLOSED


def test_a_stamp_builder_failure_still_closes(env, monkeypatch):
    def boom(ticker):
        raise RuntimeError("bug in the builder")

    monkeypatch.setattr(tc, "_build_override_stamp", boom)
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] is None
    assert FakeTradeLog.closes[0]["exit_price"] is None


def test_override_stamp_never_raises(env):
    env["bars"] = ValueError("malformed frame")
    assert tc._override_stamp("AAPL") is None


def test_a_partial_close_still_stamps_its_runner_path(env):
    plan = _partial()
    tc._close_plan(FakeStore([plan]), plan)
    assert env["runner_stamps"] == [PLAN_ID]
    assert _closed_entry(plan)["override"]["price_source"] == "quote"


def test_a_plan_with_no_linked_trade_is_still_stamped(env):
    FakeTradeLog.trades = []
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert FakeTradeLog.closes == []
    assert _closed_entry(plan)["override"]["exit_price"] == pytest.approx(123.45)


# --- the two callers ------------------------------------------------------------

@pytest.fixture
def request_ctx():
    return Flask("v173-close-tests").test_request_context


def test_close_open_passes_manual_bulk(env, monkeypatch, request_ctx):
    plans = [_active("11111111-1111-4111-8111-111111111111", "AAA"),
             _active("22222222-2222-4222-8222-222222222222", "BBB")]
    store = FakeStore(plans)
    seen = []
    monkeypatch.setattr(tc, "PlanStore", lambda: store)
    monkeypatch.setattr(tc, "_close_plan",
                        lambda store_, plan, reason="manual": seen.append((plan.ticker, reason)))
    with request_ctx("/api/v1/trades/close-open", method="POST"):
        body = tc.close_open.__wrapped__().get_json()
    assert body == {"closed": 2, "failed": 0, "tickers": ["AAA", "BBB"]}
    assert seen == [("AAA", "manual_bulk"), ("BBB", "manual_bulk")]


def test_close_trade_passes_the_default_manual(env, monkeypatch, request_ctx):
    store = FakeStore([_active()])
    seen = []
    monkeypatch.setattr(tc, "PlanStore", lambda: store)
    monkeypatch.setattr(tc, "_close_plan",
                        lambda store_, plan, reason="manual": seen.append(reason))
    monkeypatch.setattr(tc, "_plan_row", lambda plan_id: {"plan_id": plan_id})
    with request_ctx(f"/api/v1/trades/{PLAN_ID}/close", method="POST"):
        assert tc.close_trade.__wrapped__(PLAN_ID) == {"plan_id": PLAN_ID}
    assert seen == ["manual"]


def test_a_bulk_close_end_to_end_stamps_every_plan(env, monkeypatch, request_ctx):
    plans = [_active("11111111-1111-4111-8111-111111111111", "AAA"),
             _active("22222222-2222-4222-8222-222222222222", "BBB")]
    FakeTradeLog.trades = []
    monkeypatch.setattr(tc, "PlanStore", lambda: FakeStore(plans))
    with request_ctx("/api/v1/trades/close-open", method="POST"):
        tc.close_open.__wrapped__()
    for plan in plans:
        entry = _closed_entry(plan)
        assert entry["reason"] == "manual_bulk"
        assert entry["override"]["price_source"] == "quote"
```

If `_looks_like_a_plan_id` rejects `PLAN_ID` (check with `git -C $WT grep -n "def _looks_like_a_plan_id" -A6 swingbot/admin/api_v1/trades.py`), use any id it accepts; `_PLAN_ID` in `tests/admin/test_api_v1_trade_commands.py` is the same UUID and goes down the plan branch today.

- [ ] **Step 2: Write the failing `close_trade_manual` tests**

Create `$WT/tests/tracking/test_close_trade_manual_exit_price.py`. `TradeLog`'s table read and write are replaced by an in-memory list, so no database opens.

```python
"""v173 §1: close_trade_manual(exit_price=) settles at the price the plan's
override stamp recorded, so the stamp and the trade never disagree. Without
it, today's own live fetch is unchanged."""
from __future__ import annotations

import pytest

from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog


def _open(trade_id="t1", legs=None):
    return {"id": trade_id, "ticker": "AAPL", "status": "open", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "legs": legs or []}


@pytest.fixture
def book(monkeypatch):
    """`rows` is the whole table; `upserts` every write; `fetches` every live fetch."""
    state = {"rows": [_open()], "upserts": [], "fetches": [], "quote": 111.0}

    def fetch(ticker, *args, **kwargs):
        state["fetches"].append((ticker, kwargs.get("allow_stale")))
        return state["quote"]

    monkeypatch.setattr(TradeLog, "_all", lambda self: state["rows"])
    monkeypatch.setattr(TradeLog, "_db_upsert",
                        staticmethod(lambda trade, conn=None: state["upserts"].append(dict(trade))))
    monkeypatch.setattr(TradeLog, "_settle_account_balance", lambda self, trade: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", fetch)
    return state


def test_a_given_exit_price_is_used_and_nothing_is_fetched(book):
    assert TradeLog().close_trade_manual("t1", reason="manual (plan close, admin UI)",
                                         exit_price=123.45) is True
    trade = book["rows"][0]
    assert trade["exit_price"] == pytest.approx(123.45)
    assert trade["status"] == "closed"
    assert trade["close_reason"] == "manual (plan close, admin UI)"
    assert book["fetches"] == []
    assert len(book["upserts"]) == 1


def test_without_an_exit_price_the_live_fetch_is_unchanged(book):
    assert TradeLog().close_trade_manual("t1") is True
    assert book["fetches"] == [("AAPL", False)]
    assert book["rows"][0]["exit_price"] == pytest.approx(111.0)


def test_a_failed_fetch_still_closes_without_a_price(book, monkeypatch):
    def boom(*args, **kwargs):
        raise TimeoutError("down")

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", boom)
    assert TradeLog().close_trade_manual("t1") is True
    assert book["rows"][0]["status"] == "closed"
    assert book["rows"][0].get("exit_price") is None


def test_a_partial_trade_banks_its_remainder_at_the_given_price(book):
    book["rows"] = [_open(legs=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}])]
    TradeLog().close_trade_manual("t1", exit_price=105.0)
    legs = book["rows"][0]["legs"]
    assert [leg["fraction"] for leg in legs] == [0.5, 0.5]
    assert legs[-1]["exit_price"] == pytest.approx(105.0)
    assert legs[-1]["r"] == pytest.approx(1.0)
    assert book["fetches"] == []


def test_an_already_closed_trade_is_not_touched(book):
    book["rows"][0]["status"] = "closed"
    assert TradeLog().close_trade_manual("t1", exit_price=123.45) is False
    assert book["upserts"] == []
```

- [ ] **Step 3: Run both to verify they fail**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_close_plan_override_stamp.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/tracking/test_close_trade_manual_exit_price.py
```

Expected: the admin file FAILs (`TypeError: _close_plan() takes 2 positional arguments but 3 were given`, `KeyError: 'override'`, `AttributeError: ... has no attribute '_build_override_stamp'`, and `seen == [("AAA", "manual"), ...]` for the bulk caller). The tracking file FAILs with `TypeError: close_trade_manual() got an unexpected keyword argument 'exit_price'` in the three `exit_price=` tests; the two tests without the kwarg already pass.

- [ ] **Step 4: Implement `close_trade_manual(exit_price=)`**

In `$WT/swingbot/core/tracking/performance.py`, add this module function directly above `class TradeLog:` (line ~580):

```python
def _manual_close_quote(ticker: str) -> float | None:
    """The live price a manual close settles at when its caller has none.
    Never raises: a network hiccup must never block the close itself."""
    try:
        from swingbot.core.marketdata.data import get_current_price
        return get_current_price(ticker, allow_stale=False)
    except Exception:
        return None
```

Then replace the signature, the docstring and the fetch block of `close_trade_manual` (lines 1417-1447, up to and including the `except Exception: price = None` block) so the method's top reads:

```python
    def close_trade_manual(self, trade_id: str, reason: str = "manual", *,
                           exit_price: float | None = None) -> bool:
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

        Locked the same way as every other mutator here so a concurrent
        write from the bot's own scan loop (a different process, same
        trades table) can't race with it and corrupt or lose data. The
        price fetch itself happens OUTSIDE the lock (it's a network call)
        and is re-validated against the trade's live status once inside.
        Returns True if a matching OPEN trade was found and closed.
        """
        with _LOCK:
            ticker = next((t["ticker"] for t in self._all()
                           if t["id"] == trade_id and t["status"] == "open"), None)
        price = exit_price
        if ticker and price is None:
            price = _manual_close_quote(ticker)
```

Everything from `closed_trade = None` to the end of the method stays exactly as it is.

- [ ] **Step 5: Implement the stamp and the `reason` parameter**

In `$WT/swingbot/admin/api_v1/trade_commands.py`, insert these four helpers directly above `def _close_plan` (below the `# --- close ---` banner):

```python
def _live_quote(ticker: str) -> tuple[float | None, str | None]:
    """(price, quote_ts) for the override stamp, fetched once. A fetch that
    raises is "no quote" (one warning), so the stamp falls back to the bar
    close rather than being lost. Looked up on the module at call time."""
    try:
        from swingbot.core.marketdata import data as md
        quote = md.get_current_price_detail(ticker, allow_stale=False)
    except Exception as exc:
        log.warning("override stamp: quote fetch failed for %s: %s", ticker, exc)
        return None, None
    quote_ts = datetime.now(timezone.utc).isoformat()
    if quote is None or not quote.price:
        return None, None
    return float(quote.price), quote_ts


def _last_bar(bars) -> tuple[str | None, float | None]:
    """(ISO date, close) of the daily cache's last bar; Nones when empty.
    A NaN close is no price."""
    if bars is None or len(bars) == 0:
        return None, None
    close = float(bars["Close"].iloc[-1])
    return bars.index[-1].date().isoformat(), (close if close == close else None)


def _build_override_stamp(ticker: str) -> dict:
    """The four-field `override` stamp (spec v173 §1). May raise; callers
    go through `_override_stamp`."""
    price, quote_ts = _live_quote(ticker)
    bars_asof, last_close = _last_bar(rp.cached_daily_bars(ticker))
    if price is not None:
        source = "quote"
    elif last_close is not None:
        price, source = last_close, "bar_close"
    else:
        source = "none"
    return {"exit_price": price, "price_source": source,
            "quote_ts": quote_ts if source == "quote" else None, "bars_asof": bars_asof}


def _override_stamp(ticker: str) -> dict | None:
    """What a manual close records about its exit, read only by the v173
    override-fidelity report. Never raises: a failure logs and returns None
    (written as `override: null`), and the close goes ahead."""
    try:
        return _build_override_stamp(ticker)
    except Exception as exc:
        log.warning("override stamp failed for %s: %s", ticker, exc, exc_info=True)
        return None
```

Replace `_close_plan` with:

```python
def _close_plan(store: PlanStore, plan, reason: str = "manual") -> None:
    """Close one ACTIVE/PARTIAL plan: settle its linked legacy trade, record
    the transition, and queue the bot's notification.

    Extracted from close_trade so the bulk endpoint runs exactly this and
    cannot drift from the single-position path. The caller checks status.
    `reason` is "manual" for a single close and "manual_bulk" for the bulk
    endpoint (v173): a bulk clear is not a decision, and the override report
    must be able to tell the two apart.
    """
    stamp = _override_stamp(plan.ticker)
    quoted = stamp["exit_price"] if stamp and stamp["price_source"] == "quote" else None
    tl = TradeLog()
    linked = _linked_trade(tl, plan.plan_id)
    if linked and linked.get("status") == _OPEN_LEGACY:
        # Through TradeLog's own locked mutator: the admin and the bot are
        # separate processes over one trades.json, so an unlocked
        # read-modify-write here could race the scan loop. The stamp's quote
        # is passed in so the stamp and the trade carry one price; a daily
        # close (bar_close) is never written to the trade as a live fill.
        tl.close_trade_manual(linked["id"], reason="manual (plan close, admin UI)",
                              exit_price=quoted)
    was_partial = plan.status == PlanStatus.PARTIAL
    # `at` is passed explicitly -- record_transition defaults it to None, and
    # the lifecycle strip's "today" counts read status_history[-1]["at"].
    record_transition(plan, PlanStatus.CLOSED, reason=reason,
                      at=datetime.now(timezone.utc).isoformat(),
                      extra={"override": stamp})
    if was_partial:   # v142: a manual runner close stamps its path too; never raises
        rp.stamp_runner_path(plan, rp.cached_daily_bars, source="live")
    store.update(plan)
    _queue_notify({"kind": "plan_transition", "plan_id": plan.plan_id,
                   "ticker": plan.ticker, "status": plan.status})
```

In `close_open`, change the one call inside the loop (line ~258) from `_close_plan(store, plan)` to:

```python
            _close_plan(store, plan, "manual_bulk")
```

and extend its docstring paragraph that starts "Per position it runs `_close_plan`" to:

```python
    Per position it runs `_close_plan` -- the same path the single-position
    close uses, including the manual-close notify record the bot reads --
    with reason "manual_bulk" (v173), so a bulk clear is never counted as
    an individual override.
```

`close_trade` keeps `_close_plan(store, plan)` unchanged (the default is `"manual"`).

- [ ] **Step 6: Keep the existing bulk test's stub call-compatible and offline**

In `$WT/tests/admin/test_api_v1_trade_commands.py`, `test_close_open_reports_failures_without_aborting_the_rest` (line ~345) monkeypatches `_close_plan` with a two-argument stub, which the new positional `"manual_bulk"` would break. Change the stub to:

```python
    def flaky(store, plan, reason="manual"):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(store, plan, reason)
```

Every plan close in this file now fetches a quote for its stamp. Keep the file offline by adding, right after the `notify_queue` fixture:

```python
@pytest.fixture(autouse=True)
def _no_live_quote(monkeypatch):
    """v173: _close_plan fetches a quote for the override stamp. Default it to
    "no quote" so these route tests never reach yfinance."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price_detail",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price",
                        lambda *args, **kwargs: None)
```

This file is DB-backed already (it seeds stores) and is left that way; only the stub and the fixture change.

- [ ] **Step 7: Run the new tests and the affected existing ones**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_close_plan_override_stamp.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/tracking/test_close_trade_manual_exit_price.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_trade_commands_runner_path.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/tracking/test_one_trade_per_ticker.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. The first two never open a database. The last three are existing DB-backed files: if the disposable test database is down they skip with its start command, which is not a pass — start it as the skip message says and re-run. `test_trade_commands_runner_path.py` gets the same autouse `_no_live_quote` fixture shown above (paste it after the file's imports), so its new stamp quote never reaches yfinance; its stamps then fall back to `bar_close` or `none`, and its existing assertions do not read the stamp.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/admin/api_v1/trade_commands.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/tracking/performance.py
```

Expected: of the functions this task touches, only `TradeLog.close_trade_manual` may be listed (it was C 11 before; the extracted `_manual_close_quote` keeps it at 11, and it must stay `< 15`). `_close_plan`, `close_open` and the four new helpers stay below C.

- [ ] **Step 9: Commit on the branch (two scoped commits)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/tracking/performance.py tests/tracking/test_close_trade_manual_exit_price.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): close_trade_manual settles at a caller-given exit price"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/admin/api_v1/trade_commands.py tests/admin/test_close_plan_override_stamp.py tests/admin/test_api_v1_trade_commands.py tests/admin/test_trade_commands_runner_path.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): a manual close stamps its exit price; bulk clears close as manual_bulk"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

# Phase 2: The 2026-09-30 retag

### Task V173-4: Pin the 15 bulk-clear plan ids from production (read-only)

**Model:** sonnet — read-only prod query through `prod-inspector`, judge the count

**Files:**
- Modify: `docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md` (§ Pinned bulk-clear ids only, on `main`)

**Interfaces:**
- Consumes: nothing (independent of every branch task; may run any time before V173-5).
- Produces: § Pinned bulk-clear ids in the index: a table of the 15 `plan_id`s with ticker, `at` and the state before the close, plus a ready-to-paste Python tuple. V173-5 copies the tuple verbatim into `PINNED_PLAN_IDS`; V173-18 re-runs Query A after the deploy and expects the same 15 ids under `manual_bulk`.

This task never writes to production. Every statement runs inside `BEGIN TRANSACTION READ ONLY; ... ROLLBACK;`, through `scripts/ops/ssh-hetzner.sh` only (CLAUDE.md), piped on stdin so no SQL is quoted through the shell. The spec (§2) fixes the selection: last transition `manual`, `at` in 2026-09-30 20:54–20:56 UTC. The window is never widened to make a count fit.

- [ ] **Step 1: Write the two read-only queries to the session scratchpad**

Write `<scratchpad>/v173_pin_bulk_clear.sql` (the session scratchpad directory, never the repo):

```sql
-- v173 V173-4: read-only. Pins the 2026-09-30 bulk clear.
BEGIN TRANSACTION READ ONLY;

\echo '== A: the pinned window (expect exactly 15 rows) =='
SELECT plan_id,
       ticker,
       status                                         AS status_col,
       doc -> 'status_history' -> -1 ->> 'at'          AS closed_at,
       doc -> 'status_history' -> -2 ->> 'status'      AS state_before
FROM plans
WHERE doc -> 'status_history' -> -1 ->> 'status' = 'CLOSED'
  AND doc -> 'status_history' -> -1 ->> 'reason' = 'manual'
  AND (doc -> 'status_history' -> -1 ->> 'at')::timestamptz >= '2026-09-30 20:54:00+00'
  AND (doc -> 'status_history' -> -1 ->> 'at')::timestamptz <  '2026-09-30 20:56:00+00'
ORDER BY closed_at, plan_id;

\echo '== B: every manual close 2026-09-29..2026-10-01 by minute (the cluster must stand alone) =='
SELECT date_trunc('minute', (doc -> 'status_history' -> -1 ->> 'at')::timestamptz) AS minute_utc,
       count(*)                                                                  AS n
FROM plans
WHERE doc -> 'status_history' -> -1 ->> 'status' = 'CLOSED'
  AND doc -> 'status_history' -> -1 ->> 'reason' = 'manual'
  AND (doc -> 'status_history' -> -1 ->> 'at')::timestamptz >= '2026-09-29 00:00:00+00'
  AND (doc -> 'status_history' -> -1 ->> 'at')::timestamptz <  '2026-10-02 00:00:00+00'
GROUP BY 1
ORDER BY 1;

ROLLBACK;
```

- [ ] **Step 2: Run it on production through the wrapper (or dispatch `prod-inspector` with exactly this command)**

From the main tree `$R`:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -v ON_ERROR_STOP=1 -P pager=off -f -" < "<scratchpad>/v173_pin_bulk_clear.sql"
```

Expected: Query A prints 15 rows, every `status_col` is `CLOSED`, every `closed_at` falls in 20:54–20:55 UTC, `state_before` is `ACTIVE` or `PARTIAL`. Query B shows those 15 in the 20:54/20:55 minutes and no other manual close in the surrounding minutes (individual overrides on other days are expected and irrelevant).

- [ ] **Step 3: Judge the count — stop on anything but 15**

- **Exactly 15**, all `CLOSED`, cluster isolated in Query B → continue.
- **Any other count**, a `status_col` that is not `CLOSED`, or Query B showing manual closes in 20:53 or 20:56–20:57 that look like part of the same clear → **stop**. Do not widen or narrow the window. Ask the partner with `AskUserQuestion` (one question, recommended option first), quoting Query A's row count and Query B's minute counts, whether to pin the rows as found or to re-scope §2. Record the answer in this index's § Pinned bulk-clear ids before V173-5 starts.

- [ ] **Step 4: Record the ids in the index (on `main`)**

In `$R/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md`, replace the line `Not yet pinned.` in § Pinned bulk-clear ids with the run's output in this shape (one table row per Query A row, in Query A's order; the tuple holds the same ids in the same order, each with a trailing comment):

````markdown
Pinned on <YYYY-MM-DD> from a read-only production SELECT (V173-4, Query A: last transition `manual`, `at` in 2026-09-30 20:54–20:56 UTC); 15 rows, Query B showed no neighbouring manual closes.

| # | plan_id | ticker | closed_at (UTC) | state before |
|---|---|---|---|---|
| 1 | `<plan_id>` | `<TICKER>` | `<at>` | ACTIVE |
| … | … | … | … | … |

```python
PINNED_PLAN_IDS: tuple[str, ...] = (
    "<plan_id>",  # <TICKER> <at>
    # ... 15 lines in total
)
```
````

Leave the paragraph above it as written (it documents the gate); only the `Not yet pinned.` line is replaced.

Check the count you recorded:

```bash
grep -c '^| [0-9]* | `' E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md
```

Expected: `15`.

- [ ] **Step 5: Lint and commit on `main` (this file only)**

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/plan_lint.py E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/plans/2026-10-18-v173-execution-fidelity-overrides_0-index.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v173): pin the 15 bulk-clear plan ids from a read-only production SELECT"
```

Stage only the index: other sessions share the main tree (`worktree-lifecycle`), so never `git add -A` here. The scratchpad SQL file is not committed.

### Task V173-5: Alembic data revision `v173_001`: re-tag the pinned bulk clear

**Model:** opus — a schema/data migration on production rows

**Files:**
- Create: `swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py`
- Create: `tests/db/test_v173_manual_bulk_retag.py`

**Interfaces:**
- Consumes: the 15 ids in the index § Pinned bulk-clear ids (V173-4). `manual_bulk` as a reason (V173-2 teaches its readers; this task does not depend on V173-2's code).
- Produces: `revision = "v173_001"`, `down_revision = "v172_001"` (the current head, written as a placeholder and re-checked by Step 1); `PINNED_PLAN_IDS: tuple[str, ...]` (exactly 15 unique ids); `retag(histories: dict[str, list], *, frm: str, to: str) -> dict[str, list]`; `apply(conn, *, frm: str, to: str) -> int` (rows written). V173-18 runs it on production through `deploy/deploy.sh` (`alembic upgrade head`) and verifies the 15 re-tags. **`v173_002` (V173-24, the `preregistration_verdicts` table) chains on this revision** (`v173_002.down_revision = "v173_001"`), so after V173-24 the single head is `v173_002` and `v173_001` sits directly below it; if `main` gains a revision before the merge, V173-17 re-chains only `v173_001.down_revision`.

**Gate:** do not start until the index § Pinned bulk-clear ids holds the 15-id tuple (V173-4 Step 4). If it still says `Not yet pinned.`, stop and report `BLOCKED: V173-4 has not run`.

What the revision does (spec §2, Global Constraints "Data revision"):

- **Upgrade:** for each of the 15 pinned plans, the last `status_history` entry must read `{"status": "CLOSED", "reason": "manual"}`; its `reason` becomes `"manual_bulk"`. Every other key of that entry, every earlier entry and every other plan is untouched.
- **Downgrade:** the exact reverse, refusing unless every pinned last entry reads `manual_bulk`.
- **Refusal before any write:** every history is checked first and the writes follow only if all 15 pass; one missing pinned id or one mismatch raises `RuntimeError` naming the ids, and nothing is written.
- **A database holding none of the pinned plans** (a fresh install, the disposable test database that `tests/db/test_migrations.py::test_migrations_produce_exactly_the_declared_schema` upgrades to head, a dev fixture book) is not the production book: the revision logs one line and writes nothing. Without this, `alembic upgrade head` would fail on every database except production. Some-but-not-all present still refuses. V173-18 verifies after the deploy that production really re-tagged 15 rows, so a silent no-op there cannot go unseen.
- **Reads and writes:** only `plan_id, doc -> 'status_history'` for the pinned ids, read with `SELECT plan_id, doc->'status_history' AS hist FROM plans WHERE plan_id = ANY(:ids) FOR UPDATE` (the row lock holds the 15 rows from the check to the write inside the revision's transaction, so a concurrent close or retag cannot slip between them; a test asserts the SQL text carries `FOR UPDATE`), and one `jsonb_set(doc, '{status_history}', CAST(:hist AS jsonb))` per pinned id. Pure helpers carry the logic so the test needs no database.

- [ ] **Step 1: Find the current head**

```bash
python -c "import re,pathlib; d=pathlib.Path(r'E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/migrations/versions'); revs={}; downs=set(); [(revs.__setitem__(re.search(r'^revision = \"(.+?)\"', t, re.M).group(1), f.name), downs.add((re.search(r'^down_revision = \"(.+?)\"', t, re.M) or [None, None])[1])) for f in d.glob('*.py') for t in [f.read_text(encoding='utf-8')]]; print(sorted(set(revs) - downs))"
```

Expected: `['v172_001']` (the head when this plan was revised, 2026-10-19; brief addendum A). That is the placeholder written as `down_revision` below. Another single id means a later plan merged a revision first: write that id instead, in both `down_revision` and the docstring's `Revises:` line. More than one id means the graph already has two heads: stop and report it. `v173_002` does not exist yet (V173-24 adds it on top of this revision).

- [ ] **Step 2: Write the failing test**

Create `$WT/tests/db/test_v173_manual_bulk_retag.py`. The revision module is loaded from its file (as `test_v146_confidence_points_migration.py` does), its SQL seam is a fake connection, and the chain checks read the script directory only. No database is opened.

```python
"""v173_001: re-tag exactly the 15 pinned 2026-09-30 bulk-clear closes as
manual_bulk, refusing before any write on a missing id or a mismatch.

The revision's logic is pure (`retag`, `apply` over a connection seam), so
every test here runs on a fake connection: no database, never the
production replica."""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import types

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v173_001_manual_bulk_retag.py")
BULK_AT = "2026-09-30T20:54:31+00:00"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v173_001_manual_bulk_retag", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
PINNED = MIG.PINNED_PLAN_IDS


def _history(reason="manual", *, partial=False):
    history = [{"status": "ACTIVE", "reason": "filled", "at": "2026-09-22T14:00:00+00:00"}]
    if partial:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-09-25T15:00:00+00:00"})
    history.append({"status": "CLOSED", "reason": reason, "at": BULK_AT})
    return history


def _book(reason="manual"):
    return {pid: _history(reason, partial=i % 2 == 1) for i, pid in enumerate(PINNED)}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """`plans` maps plan_id -> status_history (a list), like the doc column."""

    def __init__(self, plans):
        self.plans = plans
        self.selected_ids = None
        self.select_sql = None
        self.updates = []

    def execute(self, statement, params):
        sql = str(statement).strip()
        if sql.upper().startswith("SELECT"):
            self.select_sql = sql
            self.selected_ids = list(params["ids"])
            return _Result([(pid, copy.deepcopy(hist)) for pid, hist in self.plans.items()
                            if pid in params["ids"]])
        assert sql.upper().startswith("UPDATE PLANS"), sql
        history = json.loads(params["hist"])
        self.updates.append(params["plan_id"])
        self.plans[params["plan_id"]] = history
        return _Result([])


# --- the pinned ids -------------------------------------------------------------

def test_exactly_fifteen_unique_pinned_plan_ids():
    assert len(PINNED) == 15
    assert len(set(PINNED)) == 15
    assert all(isinstance(pid, str) and len(pid) == 36 and pid.count("-") == 4 for pid in PINNED)


# --- retag (pure) ---------------------------------------------------------------

def test_retag_changes_only_the_terminal_reason():
    book = _book()
    out = MIG.retag(book, frm="manual", to="manual_bulk")
    assert set(out) == set(PINNED)
    for pid in PINNED:
        assert out[pid][-1] == {"status": "CLOSED", "reason": "manual_bulk", "at": BULK_AT}
        assert out[pid][:-1] == book[pid][:-1]


def test_retag_never_mutates_its_input():
    book = _book()
    before = copy.deepcopy(book)
    MIG.retag(book, frm="manual", to="manual_bulk")
    assert book == before


def test_retag_keeps_any_other_key_on_the_terminal_entry():
    book = _book()
    book[PINNED[0]][-1]["note"] = "kept"
    out = MIG.retag(book, frm="manual", to="manual_bulk")
    assert out[PINNED[0]][-1]["note"] == "kept"


def test_retag_refuses_a_missing_pinned_id():
    book = _book()
    del book[PINNED[3]]
    with pytest.raises(RuntimeError, match=PINNED[3]):
        MIG.retag(book, frm="manual", to="manual_bulk")


@pytest.mark.parametrize("terminal", [
    {"status": "CLOSED", "reason": "manual_bulk", "at": BULK_AT},     # already changed
    {"status": "CLOSED", "reason": "tp1_runner_trail", "at": BULK_AT},
    {"status": "CANCELLED", "reason": "manual", "at": BULK_AT},
])
def test_retag_refuses_a_terminal_entry_that_is_not_closed_manual(terminal):
    book = _book()
    book[PINNED[5]][-1] = terminal
    with pytest.raises(RuntimeError, match=PINNED[5]):
        MIG.retag(book, frm="manual", to="manual_bulk")


def test_retag_refuses_an_empty_history():
    book = _book()
    book[PINNED[0]] = []
    with pytest.raises(RuntimeError, match=PINNED[0]):
        MIG.retag(book, frm="manual", to="manual_bulk")


# --- apply over a connection -----------------------------------------------------

def test_upgrade_then_downgrade_round_trips_exactly():
    original = _book()
    conn = FakeConn(copy.deepcopy(original))
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 15
    assert all(conn.plans[pid][-1]["reason"] == "manual_bulk" for pid in PINNED)
    assert MIG.apply(conn, frm="manual_bulk", to="manual") == 15
    assert conn.plans == original


def test_only_pinned_ids_are_read_and_written():
    plans = _book()
    plans["99999999-9999-4999-8999-999999999999"] = _history("manual")   # an individual override
    conn = FakeConn(plans)
    MIG.apply(conn, frm="manual", to="manual_bulk")
    assert set(conn.selected_ids) == set(PINNED)
    assert sorted(conn.updates) == sorted(PINNED)
    assert plans["99999999-9999-4999-8999-999999999999"][-1]["reason"] == "manual"


def test_the_pinned_read_locks_its_rows():
    """The check and the write must see the same 15 rows: FOR UPDATE."""
    assert "FOR UPDATE" in " ".join(str(MIG._SELECT).upper().split())
    conn = FakeConn(_book())
    MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.select_sql.upper().rstrip().endswith("FOR UPDATE")


def test_a_mismatch_refuses_before_any_write():
    plans = _book()
    plans[PINNED[-1]][-1]["reason"] = "manual_bulk"
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError):
        MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.updates == []


def test_some_but_not_all_pinned_plans_present_refuses_before_any_write():
    plans = _book()
    del plans[PINNED[7]]
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError, match=PINNED[7]):
        MIG.apply(conn, frm="manual", to="manual_bulk")
    assert conn.updates == []


def test_a_database_with_none_of_the_pinned_plans_is_left_alone():
    """A fresh install or the test database: `alembic upgrade head` must pass."""
    conn = FakeConn({"99999999-9999-4999-8999-999999999999": _history("manual")})
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 0
    assert conn.updates == []


def test_downgrade_refuses_unless_every_pinned_entry_reads_manual_bulk():
    plans = _book("manual_bulk")
    plans[PINNED[2]][-1]["reason"] = "manual"
    conn = FakeConn(plans)
    with pytest.raises(RuntimeError, match=PINNED[2]):
        MIG.apply(conn, frm="manual_bulk", to="manual")
    assert conn.updates == []


def test_upgrade_and_downgrade_run_on_the_alembic_bind(monkeypatch):
    conn = FakeConn(_book())
    monkeypatch.setattr(MIG, "op", types.SimpleNamespace(get_bind=lambda: conn))
    MIG.upgrade()
    assert all(conn.plans[pid][-1]["reason"] == "manual_bulk" for pid in PINNED)
    MIG.downgrade()
    assert all(conn.plans[pid][-1]["reason"] == "manual" for pid in PINNED)


def test_a_history_returned_as_json_text_is_decoded():
    book = _book()
    conn = FakeConn(book)
    real_execute = conn.execute

    def as_text(statement, params):
        result = real_execute(statement, params)
        return _Result([(pid, json.dumps(hist)) for pid, hist in result.fetchall()])

    conn.execute = as_text
    assert MIG.apply(conn, frm="manual", to="manual_bulk") == 15


# --- the revision graph (script directory only) ----------------------------------

@pytest.fixture(scope="module")
def scripts():
    return ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))


def test_v173_001_is_on_the_single_head_chain(scripts):
    """True now (v173_001 is the head) and after V173-24 (v173_002 on top)."""
    assert MIG.revision == "v173_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    chain = {rev.revision for rev in scripts.iterate_revisions(heads[0], "base")}
    assert "v173_001" in chain


def test_it_chains_onto_an_existing_revision(scripts):
    assert MIG.down_revision == "v172_001"   # re-chained only by V173-17 if main moved
    assert scripts.get_revision(MIG.down_revision) is not None
    assert scripts.get_revision("v173_001").down_revision == MIG.down_revision
```

- [ ] **Step 3: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_manual_bulk_retag.py
```

Expected: collection ERROR — `FileNotFoundError` for `v173_001_manual_bulk_retag.py`.

- [ ] **Step 4: Write the revision**

Create `$WT/swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py`. Set `down_revision` to the head from Step 1, and copy the tuple from the index § Pinned bulk-clear ids **verbatim**, including each line's `# <TICKER> <at>` comment, in place of the two comment lines inside `PINNED_PLAN_IDS`:

```python
"""plans.status_history: re-tag the 2026-09-30 bulk clear as manual_bulk

v173 §2. On 2026-09-30 20:54-20:55 UTC one bulk "close open" ran through the
same `_close_plan` as a single close and recorded reason "manual" on 15
plans. A bulk clear is not a decision, and the override-fidelity report must
not count it as one. This revision sets the terminal status_history entry's
reason to "manual_bulk" on exactly the 15 plan ids pinned below (from a
read-only production SELECT, recorded in the v173 plan index) and on
nothing else.

Refusals raise RuntimeError before anything is written:
- some, but not all, of the pinned plans exist;
- a pinned plan's last status_history entry is not
  {"status": "CLOSED", "reason": <from>}.
A database holding none of the pinned plans (a fresh install, the test
database, a dev fixture book) is not the production book: one log line,
nothing written, so `alembic upgrade head` still works there. Downgrade is
the exact reverse over the same 15 entries.

Revision ID: v173_001
Revises: v172_001
"""
from __future__ import annotations

import copy
import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "v173_001"
down_revision = "v172_001"   # = python -m alembic heads at implementation time (Step 1); v173_002 chains on v173_001
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Copied verbatim from the v173 plan index, § Pinned bulk-clear ids (V173-4).
PINNED_PLAN_IDS: tuple[str, ...] = (
    # "<plan_id>",  # <TICKER> <at>
    # ... exactly 15 lines
)

# FOR UPDATE: the 15 rows stay locked from the check to the write (one transaction).
_SELECT = sa.text(
    "SELECT plan_id, doc->'status_history' AS hist FROM plans WHERE plan_id = ANY(:ids) FOR UPDATE")
_UPDATE = sa.text(
    "UPDATE plans SET doc = jsonb_set(doc, '{status_history}', CAST(:hist AS jsonb)) "
    "WHERE plan_id = :plan_id")


def _terminal_is(history, reason: str) -> bool:
    """True when `history`'s last entry is a CLOSED transition with `reason`."""
    if not isinstance(history, list) or not history:
        return False
    last = history[-1]
    return (isinstance(last, dict) and last.get("status") == "CLOSED"
            and last.get("reason") == reason)


def retag(histories: dict[str, list], *, frm: str, to: str) -> dict[str, list]:
    """New status_history lists for every pinned plan, terminal reason `frm`
    -> `to`. Raises RuntimeError, naming the ids, when a pinned id is missing
    from `histories` or its terminal entry is not CLOSED/`frm`. Never mutates
    `histories`."""
    missing = [pid for pid in PINNED_PLAN_IDS if pid not in histories]
    if missing:
        raise RuntimeError(f"v173_001: pinned plans missing: {missing}")
    wrong = [pid for pid in PINNED_PLAN_IDS if not _terminal_is(histories[pid], frm)]
    if wrong:
        raise RuntimeError(
            f"v173_001: last status_history entry is not CLOSED/{frm!r} for {wrong}")
    out: dict[str, list] = {}
    for pid in PINNED_PLAN_IDS:
        history = copy.deepcopy(list(histories[pid]))
        history[-1]["reason"] = to
        out[pid] = history
    return out


def _as_list(value):
    """A jsonb value as Python: psycopg decodes it already; text is parsed."""
    return json.loads(value) if isinstance(value, str) else value


def apply(conn, *, frm: str, to: str) -> int:
    """Re-tag the pinned plans on `conn`; returns the rows written. Every
    check runs before the first write."""
    rows = conn.execute(_SELECT, {"ids": list(PINNED_PLAN_IDS)}).fetchall()
    histories = {row[0]: _as_list(row[1]) for row in rows}
    if not histories:
        log.info("v173_001: none of the %d pinned plans exist here (not the production "
                 "book); nothing to re-tag", len(PINNED_PLAN_IDS))
        return 0
    changed = retag(histories, frm=frm, to=to)
    for pid, history in changed.items():
        conn.execute(_UPDATE, {"hist": json.dumps(history), "plan_id": pid})
    log.info("v173_001: re-tagged %d plans %s -> %s", len(changed), frm, to)
    return len(changed)


def upgrade() -> None:
    apply(op.get_bind(), frm="manual", to="manual_bulk")


def downgrade() -> None:
    apply(op.get_bind(), frm="manual_bulk", to="manual")
```

If Step 1 found a head other than `v172_001`, write it in both `down_revision` and the docstring's `Revises:` line, and change the `== "v172_001"` assertion in `test_it_chains_onto_an_existing_revision` to match.

- [ ] **Step 5: Run the test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_v173_manual_bulk_retag.py
```

Expected: PASS, `0 failed`, `0 xfailed`. `test_exactly_fifteen_unique_pinned_plan_ids` failing means the tuple was not copied in full; `test_the_pinned_read_locks_its_rows` failing means `FOR UPDATE` was dropped from `_SELECT`.

- [ ] **Step 6: Run the revision-graph test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected (single head `v173_001` until V173-24 adds `v173_002` above it): `test_exactly_one_head`, `test_every_revision_id_is_part_prefixed` and `test_the_graph_roots_at_the_baseline` PASS. `test_migrations_produce_exactly_the_declared_schema` is an existing DB-backed test: it upgrades an empty test database to head, where this revision finds none of the pinned plans and writes nothing. It skips with the start command when the disposable test database is down; that skip is not a pass, so start it and re-run. It is never pointed at the production replica.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py
```

Expected: no output (every function below C).

- [ ] **Step 8: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/db/migrations/versions/v173_001_manual_bulk_retag.py tests/db/test_v173_manual_bulk_retag.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): data revision v173_001 re-tags the pinned 2026-09-30 bulk clear as manual_bulk"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The revision runs on production only in V173-18's deploy, after the § Before running a data revision on production check (`schema-evolution.md`: the last PITR drill passed, rollback is `scripts/ops/rollback_to.sh`); never run it by hand from this task.
