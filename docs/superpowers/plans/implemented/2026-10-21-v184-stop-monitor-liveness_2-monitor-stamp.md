# v184 — Part 2: the monitor's check helpers, the liveness stamp and its wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-21-v184-stop-monitor-liveness-design.md](../specs/2026-10-21-v184-stop-monitor-liveness-design.md)
**Index:** [2026-10-21-v184-stop-monitor-liveness_0-index.md](2026-10-21-v184-stop-monitor-liveness_0-index.md). Goal, architecture, `## Global Constraints`, `## Spec clarifications`, `## Contracts`, `## Review Focus` and `## Parallelisation` live there and bind every task below.
**Tasks:** V184-5..V184-7. Every command runs from the worktree root `.claude/worktrees/2026-10-21-v184-stop-monitor-liveness` (created in V184-1).

Part 1 has shipped (or the named task has) when a task here starts. These tasks use, exactly as the index's Contracts state them:

- V184-2: `swingbot.core.market.session.is_nyse_regular_session(now: dt.datetime | None = None) -> bool`.
- V184-3: `plan_manager.reset_monitor_batch_status()`, `plan_manager.mark_monitor_batch_failed()`, `plan_manager.monitor_batch_failed() -> bool`. After V184-3, loops' `_legacy_live_price_batch` marks the flag when its `_run_bounded` returns `None` or raises, and `_live_price_batch` marks it when `monitor_quotes` raises.
- V184-4: `plan_manager.PollDemand(demanded: tuple[str, ...], priced: frozenset[str])` with `.unpriced -> tuple[str, ...]`, and module-level `plan_manager.last_poll_demand() -> PollDemand | None`.

**Database:** the trade-monitor tests reach the per-checkout test database (the equity sample already does today, and from V184-7 so does the stamp). If this session has not yet run `/replicate-prod-db`, run it before the first test run (CLAUDE.md).

**Swallowed-error ratchet** (`tests/infra/test_swallowed_ratchet.py`): the repo-wide count of untagged `except Exception` handlers is pinned at `BASELINE`. V184-5 and V184-7 move existing untagged handlers into helpers without adding or removing one, so the count is unchanged. The only new handler in this part (`stamp_tick`, V184-6) is tagged `ops.monitor_stamp`, which matches the ratchet's `TAG_RE`.

**Complexity:** `loops.trade_monitor` is radon C (13) today and unbaselined, so it must end below 15. After V184-5 it falls (the per-ticker loop leaves it); after V184-7 it is a four-line `try/finally`. Check with `python scripts/dev/complexity_gate.py` in each task.

---

# Phase — The monitor stamps its own liveness (V184-5..V184-7)

### Task V184-5: Extract trade_monitor's per-ticker checks and manager tick (behaviour-preserving)

**Model:** sonnet — a behaviour-preserving extraction across one async function, with existing test files to keep green; the helper return shapes are a contract V184-7 consumes.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (`trade_monitor` body, today l.662-720; three new helpers inserted directly above `@tasks.loop(seconds=60)` / `async def trade_monitor():`, below `_record_equity_sample`)
- Create: `tests/commands/test_trade_monitor_checks.py`

**Interfaces:**
- Consumes: nothing new. `loops.trade_log` (`close_if_live_price_hit(ticker, live)`, `check_near_tp_timeout(ticker, live)`), `plan_manager.run_manager_tick() -> list[PlanEvent]`, all existing.
- Produces (index § Contracts, Monitor checks):
  - `async def _check_open_ticker(ticker: str, live: float) -> tuple[list, bool]` — `(closed trades, errored)`.
  - `async def _check_open_tickers(tickers: list, live_prices: dict) -> tuple[list, list[str]]` — `(all newly closed, check_errors)`; `check_errors` holds the tickers whose `_check_open_ticker` reported `errored`, in `tickers` order.
  - `async def _run_plan_manager_tick() -> tuple[list, bool]` — `(plan events, raised)`; `([], True)` on raise.

This is a refactor (`docs/claude/code-complexity.md`): no log line, call order, argument or skip rule changes. Two behaviours of today's loop are kept exactly and pinned by the tests below:

- an unpriced ticker (`not live or live <= 0`) is skipped before any call;
- when `close_if_live_price_hit` raises, `check_near_tp_timeout` is **not** called for that ticker (today's `continue`); when `check_near_tp_timeout` raises, the trades the first call already closed are still returned.

The three moved `except Exception` handlers keep their `log.warning(...)` bodies: they stay untagged, so the swallowed-ratchet count does not move.

- [ ] **Step 1: Write the failing tests** — create `tests/commands/test_trade_monitor_checks.py`

```python
"""v184 V184-5: trade_monitor's per-ticker checks and its plan-manager tick,
extracted into helpers whose return values carry what the liveness stamp
(V184-7) needs -- which tickers' checks raised, and whether the manager
raised -- without changing a single close, skip or log line.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import logging

import pytest

from swingbot.commands.scanning import loops
from swingbot.core.planning import plan_manager


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def calls(monkeypatch):
    """Record every close-path call; each fake returns what `results` says,
    or raises when the value is an exception instance."""
    log = []
    results = {}

    def fake(name):
        def _call(ticker, live):
            log.append((name, ticker, live))
            out = results.get((name, ticker), [])
            if isinstance(out, Exception):
                raise out
            return out
        return _call

    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", fake("close"))
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", fake("near_tp"))
    return log, results


def test_one_ticker_runs_close_then_near_tp_and_returns_both_closes(calls):
    log, results = calls
    results[("close", "AAPL")] = [{"id": "t1"}]
    results[("near_tp", "AAPL")] = [{"id": "t2"}]
    closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert closed == [{"id": "t1"}, {"id": "t2"}]
    assert errored is False
    assert log == [("close", "AAPL", 100.0), ("near_tp", "AAPL", 100.0)]


def test_a_raising_close_skips_near_tp_and_reports_an_error(calls, caplog):
    log, results = calls
    results[("close", "AAPL")] = RuntimeError("db gone")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert (closed, errored) == ([], True)
    assert log == [("close", "AAPL", 100.0)]
    assert any("close_if_live_price_hit failed for AAPL" in r.getMessage() for r in caplog.records)


def test_a_raising_near_tp_keeps_the_trades_the_close_already_closed(calls, caplog):
    log, results = calls
    results[("close", "AAPL")] = [{"id": "t1"}]
    results[("near_tp", "AAPL")] = RuntimeError("boom")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert (closed, errored) == ([{"id": "t1"}], True)
    assert any("check_near_tp_timeout failed for AAPL" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("price", [None, 0, 0.0, -1.0])
def test_an_unpriced_ticker_is_skipped_before_any_call(calls, price):
    log, _ = calls
    prices = {} if price is None else {"AAPL": price}
    closed, errors = _run(loops._check_open_tickers(["AAPL"], prices))
    assert (closed, errors) == ([], [])
    assert log == []


def test_check_errors_list_the_raising_tickers_in_order_and_the_rest_still_run(calls):
    log, results = calls
    results[("close", "MSFT")] = RuntimeError("x")
    results[("near_tp", "NVDA")] = RuntimeError("y")
    results[("close", "AAPL")] = [{"id": "a"}]
    closed, errors = _run(loops._check_open_tickers(
        ["MSFT", "AAPL", "NVDA"], {"MSFT": 1.0, "AAPL": 2.0, "NVDA": 3.0}))
    assert closed == [{"id": "a"}]
    assert errors == ["MSFT", "NVDA"]
    assert [c[:2] for c in log] == [("close", "MSFT"), ("close", "AAPL"), ("near_tp", "AAPL"),
                                    ("close", "NVDA"), ("near_tp", "NVDA")]


def test_manager_tick_returns_its_events_and_no_error(monkeypatch):
    monkeypatch.setattr(plan_manager, "run_manager_tick", lambda: ["e1"])
    assert _run(loops._run_plan_manager_tick()) == (["e1"], False)


def test_a_raising_manager_tick_is_logged_and_reported(monkeypatch, caplog):
    def boom():
        raise RuntimeError("store locked")
    monkeypatch.setattr(plan_manager, "run_manager_tick", boom)
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        assert _run(loops._run_plan_manager_tick()) == ([], True)
    assert any("plan manager tick failed" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_trade_monitor_checks.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.loops' has no attribute '_check_open_ticker'` (and the same for the other two helpers).

- [ ] **Step 3: Add the three helpers** — in `swingbot/commands/scanning/loops.py`, insert directly below `_record_equity_sample` and above `@tasks.loop(seconds=60)`:

```python
async def _check_open_ticker(ticker: str, live: float) -> tuple[list, bool]:
    """Exact SL/TP check, then the near-TP timeout, for one priced ticker.

    Returns (trades closed, errored). `errored` is True when either call
    raised: that ticker's stops were not (fully) checked this tick (v184).
    A raising close skips the near-TP check, as the loop always did."""
    closed_all: list = []
    try:
        closed = await asyncio.to_thread(trade_log.close_if_live_price_hit, ticker, live)
    except Exception as exc:
        log.warning("trade_monitor: close_if_live_price_hit failed for %s: %s", ticker, exc, exc_info=True)
        return closed_all, True
    if closed:
        log.info("trade_monitor: %d trade(s) closed for %s (live=%.4f)", len(closed), ticker, live)
        closed_all.extend(closed)

    # Near-TP timeout exit: for whatever's STILL open on this ticker
    # after the exact SL/TP check above (a trade that just tapped its
    # real target this same tick is already gone from "open" status by
    # the time this runs) -- locks in profit on a trade that got most
    # of the way to target and then stalled instead of actually
    # touching it. See config.NEAR_TP_TIMEOUT_* / performance.py's
    # check_near_tp_timeout docstring for the exact rule.
    try:
        near_tp_closed = await asyncio.to_thread(trade_log.check_near_tp_timeout, ticker, live)
    except Exception as exc:
        log.warning("trade_monitor: check_near_tp_timeout failed for %s: %s", ticker, exc, exc_info=True)
        return closed_all, True
    if near_tp_closed:
        log.info("trade_monitor: %d trade(s) closed for %s via near-TP timeout (live=%.4f)",
                 len(near_tp_closed), ticker, live)
        closed_all.extend(near_tp_closed)
    return closed_all, False


async def _check_open_tickers(tickers: list, live_prices: dict) -> tuple[list, list[str]]:
    """Run `_check_open_ticker` for every ticker with a usable price.

    The skip rule is the close call's own filter (`not live or live <= 0`):
    v184's `unquoted` field reuses it, so it must never drift. Returns
    (all newly closed trades, tickers whose check raised)."""
    all_newly_closed: list = []
    check_errors: list[str] = []
    for ticker in tickers:
        live = live_prices.get(ticker)
        if not live or live <= 0:
            continue
        closed, errored = await _check_open_ticker(ticker, live)
        all_newly_closed.extend(closed)
        if errored:
            check_errors.append(ticker)
    return all_newly_closed, check_errors


async def _run_plan_manager_tick() -> tuple[list, bool]:
    """v2 plan lifecycle tick (flag-gated; no-op while INTRADAY_MANAGER_V2=false).

    Returns (plan events, raised); a raise is logged and yields no events."""
    from swingbot.core.planning import plan_manager
    try:
        plan_events = await asyncio.to_thread(plan_manager.run_manager_tick)
    except Exception as exc:
        log.warning("trade_monitor: plan manager tick failed: %s", exc, exc_info=True)
        return [], True
    return plan_events, False
```

- [ ] **Step 4: Replace the loop body in `trade_monitor`** — keep the docstring unchanged. Replace everything from `open_trades = trade_log.get_trades(status="open", limit=200)` through `await _retry_notifications()` with the block below; the trailing `if all_newly_closed:` notify block stays exactly as it is. If V184-3 added a statement to this body (`git diff main -- swingbot/commands/scanning/loops.py` shows it), keep that statement in the same position.

```python
    open_trades = trade_log.get_trades(status="open", limit=200)
    tickers = list({t["ticker"] for t in open_trades})

    live_prices = await _live_price_batch(tickers)
    all_newly_closed, _check_errors = await _check_open_tickers(tickers, live_prices)

    plan_events, _manager_raised = await _run_plan_manager_tick()
    if plan_events:
        await _post_plan_events(plan_events)
    await _record_equity_sample(live_prices)
    await _retry_notifications()
```

`_check_errors` and `_manager_raised` stay unused until V184-7 wires them into the stamp; the leading underscore says so.

- [ ] **Step 5: Run the new tests, the existing trade-monitor tests, the ratchet and the gate**

Run:
```bash
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_checks.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py
python scripts/dev/testrun.py file tests/commands/test_equity_recorder.py
python scripts/dev/testrun.py file tests/commands/test_loops_follow_notify.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python scripts/dev/complexity_gate.py
```
Expected: every file `0 failed`, `0 xfailed`; the existing files pass **unmodified** (this is a refactor); the gate passes, and `python -m radon cc -s swingbot/commands/scanning/loops.py | grep -E "trade_monitor|_check_open|_run_plan_manager"` shows each of them below 15 (`trade_monitor` falls from C 13).

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_trade_monitor_checks.py
git commit -m "refactor(v184): extract trade_monitor's per-ticker checks and manager tick into helpers"
```

### Task V184-6: monitor_liveness module: tick record, doc builder, priced_at, write throttle

**Model:** sonnet — a new self-contained module with pure functions and one small state object; every rule is spelled out in the index's Contracts, and the tests drive it with fixed clocks.

**Files:**
- Create: `swingbot/commands/scanning/monitor_liveness.py`
- Create: `tests/commands/test_monitor_liveness.py`

**Interfaces:**
- Consumes:
  - V184-2: `swingbot.core.market.session.is_nyse_regular_session(now: dt.datetime | None = None) -> bool`.
  - V184-4: `swingbot.core.planning.plan_manager.PollDemand(demanded: tuple[str, ...], priced: frozenset[str])`, property `.unpriced -> tuple[str, ...]` (imported only under `TYPE_CHECKING` in the module; the tests import it for real).
  - Existing: `swingbot.commands.scanning.runstate._update_heartbeat(fields: dict) -> None` (merges `doc || fields`, swallows its own DB failure under `runstate.update_heartbeat`), `swingbot.core.infra.swallowed.swallowed(log, tag, exc, msg="", *args, level=logging.WARNING, exc_info=False)`.
- Produces (index § Contracts, Monitor stamp), consumed by V184-7:
  - constants `WRITE_INTERVAL_S = 120`, `UNQUOTED_CAP = 20`, `PLAN_MANAGER_ERROR = "<plan manager>"`;
  - `@dataclass class TickRecord` with `outcome="raised"`, `trade_tickers=None`, `live_prices=None`, `plan_demand=None`, `manager_raised=False`, `check_errors=[]`, `fetch_failed=False`;
  - `positions_of(rec) -> list[str] | None`, `unquoted_of(rec) -> list[str]`, `check_errors_of(rec) -> list[str]`;
  - `class MonitorLiveness(started_at: dt.datetime | None = None)` with attributes `started_at`, `priced_at` and methods `build(rec, now) -> dict`, `due(doc, now) -> bool`, `written(doc, now) -> None`;
  - module state `_STATE = MonitorLiveness()`, `_write(doc: dict) -> None`, `async def stamp_tick(rec, *, now=None) -> bool`.

**Rules this task pins** (spec § 1, index § Spec clarifications 1 and 4):

- `positions` is `None` (JSON `null`, "unknown") when the trade read did not complete (`trade_tickers is None`) or the plan manager raised; otherwise the sorted union of the trade tickers and the plan tickers `poll()` demanded. `plan_demand is None` means the manager demanded nothing this tick (flag off, quiet hours, serial seam), so only the trade tickers count.
- `unquoted` uses exactly the close call's filter: a trade ticker whose `live_prices.get(t)` is falsy or `<= 0` (missing `live_prices` counts as `{}`), plus `plan_demand.unpriced`. Sorted, then capped at 20 in the doc, with the uncapped length in `unquoted_count`.
- `priced_at` moves to `now` only when `outcome == "ok"`, `positions` is not `None`, `unquoted` is empty and `check_errors` is empty. A known-empty book (`positions == []`) counts. It never moves backwards and is never read back from the row: a new `MonitorLiveness` (a process restart) starts at `None`.
- `market_open` is `session.is_nyse_regular_session(now)`.
- Throttle: write on the first call, when `now - last write >= 120 s`, or when `(outcome, tuple(unquoted), fetch_failed, tuple(check_errors))` differs from the last written doc. A `priced_at` or `tick_at` change alone waits for the interval.
- `stamp_tick` never raises. Any exception is counted with `swallowed(log, "ops.monitor_stamp", ...)` and returns `False`; a failed write is not recorded as written, so the next tick retries.

- [ ] **Step 1: Write the failing tests** — create `tests/commands/test_monitor_liveness.py`

```python
"""v184 V184-6: the trade monitor's liveness stamp -- the `monitor` key in
the heartbeat row. Pure tests with fixed clocks; one DB test checks the
merge keeps the scan loop's own `timestamp`.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import datetime as dt
import logging

import pytest

from swingbot import config
from swingbot.commands.scanning import monitor_liveness as ml
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.planning.plan_manager import PollDemand

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 21, 13, 0, tzinfo=UTC)
NOW = dt.datetime(2026, 10, 21, 15, 0, tzinfo=UTC)          # Wed 11:00 ET, regular session

DOC_KEYS = {"started_at", "tick_at", "outcome", "positions", "unquoted", "unquoted_count",
            "fetch_failed", "check_errors", "priced_at", "market_open"}


def _rec(**kw) -> ml.TickRecord:
    base = dict(outcome="ok", trade_tickers=["AAPL"], live_prices={"AAPL": 100.0})
    base.update(kw)
    return ml.TickRecord(**base)


def _demand(demanded, priced=()):
    return PollDemand(demanded=tuple(demanded), priced=frozenset(priced))


# --- positions / unquoted / check_errors -------------------------------------

def test_a_fresh_record_is_unknown_and_raised():
    rec = ml.TickRecord()
    assert rec.outcome == "raised"
    assert ml.positions_of(rec) is None
    assert ml.unquoted_of(rec) == []
    assert ml.check_errors_of(rec) == []


def test_positions_are_the_sorted_union_of_trade_and_demanded_plan_tickers():
    rec = _rec(trade_tickers=["MSFT", "AAPL"], plan_demand=_demand(["NVDA", "AAPL"], ["NVDA", "AAPL"]))
    assert ml.positions_of(rec) == ["AAPL", "MSFT", "NVDA"]


def test_no_plan_demand_counts_only_the_trade_tickers():
    assert ml.positions_of(_rec(trade_tickers=["AAPL"], plan_demand=None)) == ["AAPL"]


def test_a_known_empty_book_is_an_empty_list_not_unknown():
    assert ml.positions_of(_rec(trade_tickers=[], live_prices={})) == []


def test_positions_are_unknown_when_the_trade_read_did_not_complete():
    assert ml.positions_of(_rec(trade_tickers=None)) is None


def test_positions_are_unknown_when_the_plan_manager_raised():
    assert ml.positions_of(_rec(manager_raised=True)) is None


@pytest.mark.parametrize("prices", [None, {}, {"AAPL": 0}, {"AAPL": 0.0}, {"AAPL": -2.0},
                                    {"AAPL": None}])
def test_unquoted_uses_the_close_calls_own_filter(prices):
    assert ml.unquoted_of(_rec(live_prices=prices)) == ["AAPL"]


def test_unquoted_adds_the_plan_tickers_poll_did_not_price_sorted():
    rec = _rec(trade_tickers=["TSLA", "AAPL"], live_prices={"AAPL": 1.0},
               plan_demand=_demand(["NVDA", "AMD", "MSFT"], ["MSFT"]))
    assert ml.unquoted_of(rec) == ["AMD", "NVDA", "TSLA"]


def test_check_errors_append_the_plan_manager_marker_when_it_raised():
    rec = _rec(check_errors=["MSFT"], manager_raised=True)
    assert ml.check_errors_of(rec) == ["MSFT", ml.PLAN_MANAGER_ERROR]
    assert ml.PLAN_MANAGER_ERROR == "<plan manager>"


# --- build -------------------------------------------------------------------

def test_build_writes_the_full_monitor_doc():
    state = ml.MonitorLiveness(started_at=START)
    doc = state.build(_rec(), NOW)
    assert set(doc) == DOC_KEYS
    assert doc["started_at"] == "2026-10-21T13:00:00+00:00"
    assert doc["tick_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["outcome"] == "ok"
    assert doc["positions"] == ["AAPL"]
    assert doc["unquoted"] == [] and doc["unquoted_count"] == 0
    assert doc["fetch_failed"] is False and doc["check_errors"] == []
    assert doc["priced_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["market_open"] is True


def test_unquoted_is_capped_at_twenty_names_with_the_full_count():
    tickers = [f"T{i:02d}" for i in range(25)]
    doc = ml.MonitorLiveness(started_at=START).build(
        _rec(trade_tickers=tickers, live_prices={}), NOW)
    assert doc["unquoted"] == tickers[:ml.UNQUOTED_CAP]
    assert doc["unquoted_count"] == 25


def test_fetch_failed_is_carried_as_a_bool():
    doc = ml.MonitorLiveness(started_at=START).build(_rec(fetch_failed=True, live_prices={}), NOW)
    assert doc["fetch_failed"] is True and doc["unquoted"] == ["AAPL"]


# --- priced_at ---------------------------------------------------------------

def test_a_restarted_process_starts_with_no_priced_at():
    state = ml.MonitorLiveness(started_at=START)
    assert state.priced_at is None
    assert state.build(_rec(outcome="raised"), NOW)["priced_at"] is None


def test_a_clean_tick_advances_priced_at_and_a_known_empty_book_counts():
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(trade_tickers=[], live_prices={}), NOW)
    assert state.priced_at == NOW


@pytest.mark.parametrize("dirty", [
    dict(outcome="raised"),
    dict(trade_tickers=None),
    dict(manager_raised=True),
    dict(live_prices={}),
    dict(check_errors=["AAPL"]),
    dict(plan_demand=PollDemand(demanded=("NVDA",), priced=frozenset())),
], ids=["raised", "trade-read-unknown", "manager-raised", "unquoted", "check-error", "plan-unpriced"])
def test_a_dirty_tick_never_advances_priced_at_and_keeps_the_last_clean_one(dirty):
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(), NOW)
    later = NOW + dt.timedelta(minutes=5)
    doc = state.build(_rec(**dirty), later)
    assert state.priced_at == NOW
    assert doc["priced_at"] == "2026-10-21T15:00:00+00:00"
    assert doc["tick_at"] == "2026-10-21T15:05:00+00:00"


def test_a_raised_tick_with_everything_priced_still_does_not_advance():
    state = ml.MonitorLiveness(started_at=START)
    state.build(_rec(outcome="raised"), NOW)
    assert state.priced_at is None


# --- market_open --------------------------------------------------------------

@pytest.mark.parametrize("moment, expected", [
    (dt.datetime(2026, 10, 21, 15, 0, tzinfo=UTC), True),     # Wed 11:00 ET
    (dt.datetime(2026, 10, 21, 13, 29, tzinfo=UTC), False),   # Wed 09:29 ET
    (dt.datetime(2026, 10, 24, 15, 0, tzinfo=UTC), False),    # Saturday
    (dt.datetime(2026, 11, 26, 16, 0, tzinfo=UTC), False),    # Thanksgiving, 11:00 ET
    (dt.datetime(2026, 11, 27, 17, 0, tzinfo=UTC), True),     # half-day, 12:00 ET
    (dt.datetime(2026, 11, 27, 18, 30, tzinfo=UTC), False),   # half-day, 13:30 ET
])
def test_market_open_is_the_holiday_and_half_day_aware_regular_session(moment, expected):
    doc = ml.MonitorLiveness(started_at=START).build(_rec(), moment)
    assert doc["market_open"] is expected


# --- due / written (the SSE throttle) ----------------------------------------

def test_the_first_doc_is_always_due():
    state = ml.MonitorLiveness(started_at=START)
    assert state.due(state.build(_rec(), NOW), NOW) is True


def test_an_unchanged_doc_waits_for_the_interval():
    state = ml.MonitorLiveness(started_at=START)
    first = state.build(_rec(), NOW)
    state.written(first, NOW)
    t60 = NOW + dt.timedelta(seconds=60)
    assert state.due(state.build(_rec(), t60), t60) is False
    t120 = NOW + dt.timedelta(seconds=ml.WRITE_INTERVAL_S)
    assert state.due(state.build(_rec(), t120), t120) is True


@pytest.mark.parametrize("change", [
    dict(outcome="raised"),
    dict(live_prices={}),
    dict(fetch_failed=True),
    dict(check_errors=["AAPL"]),
], ids=["outcome", "unquoted", "fetch_failed", "check_errors"])
def test_a_material_change_is_written_at_once(change):
    state = ml.MonitorLiveness(started_at=START)
    state.written(state.build(_rec(), NOW), NOW)
    t60 = NOW + dt.timedelta(seconds=60)
    assert state.due(state.build(_rec(**change), t60), t60) is True


# --- stamp_tick -----------------------------------------------------------------

@pytest.fixture
def fresh_state(monkeypatch):
    state = ml.MonitorLiveness(started_at=START)
    monkeypatch.setattr(ml, "_STATE", state)
    return state


def test_stamp_tick_writes_the_doc_once_then_throttles(fresh_state, monkeypatch):
    writes = []
    monkeypatch.setattr(ml, "_write", writes.append)
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is True
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW + dt.timedelta(seconds=60))) is False
    assert len(writes) == 1 and writes[0]["outcome"] == "ok"


def test_write_merges_only_the_monitor_key(monkeypatch):
    seen = []
    monkeypatch.setattr(runstate, "_update_heartbeat", seen.append)
    ml._write({"outcome": "ok"})
    assert seen == [{"monitor": {"outcome": "ok"}}]


def test_a_raising_write_is_swallowed_counted_and_retried(fresh_state, monkeypatch, caplog):
    def boom(doc):
        raise RuntimeError("db down")
    monkeypatch.setattr(ml, "_write", boom)
    before = swallowed_mod.snapshot().get("ops.monitor_stamp", {}).get("count", 0)
    with caplog.at_level(logging.WARNING, logger=ml.log.name):
        assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is False
    assert swallowed_mod.snapshot()["ops.monitor_stamp"]["count"] == before + 1
    writes = []
    monkeypatch.setattr(ml, "_write", writes.append)
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW + dt.timedelta(seconds=60))) is True
    assert len(writes) == 1


def test_a_raising_build_is_swallowed_too(fresh_state, monkeypatch):
    monkeypatch.setattr(ml.session, "is_nyse_regular_session",
                        lambda now=None: (_ for _ in ()).throw(ValueError("tz")))
    assert asyncio.run(ml.stamp_tick(_rec(), now=NOW)) is False


# --- the real merge -------------------------------------------------------------

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_the_monitor_merge_keeps_the_scan_loops_timestamp(data_dir, db_committed, db_url):
    runstate._write_heartbeat()
    before = HeartbeatRepository().last(conn=db_committed)
    doc = ml.MonitorLiveness(started_at=START).build(_rec(), NOW)
    ml._write(doc)
    after = HeartbeatRepository().last(conn=db_committed)
    assert after["timestamp"] == before["timestamp"]
    assert after["monitor"] == doc
    assert "session_active" in after and "scan_paused" in after
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_monitor_liveness.py`
Expected: FAIL at collection — `ImportError: cannot import name 'monitor_liveness' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Write the module** — create `swingbot/commands/scanning/monitor_liveness.py`

```python
"""v184: the trade monitor stamps its own liveness.

The scan loop's heartbeat (runstate._write_heartbeat) says nothing about the
60-second trade monitor: in August 2026 the monitor stalled for ~26 h while
that stamp stayed fresh, and four -1R stops filled at -3.3R to -6.0R. Each
monitor tick now ends by merging one key, ``monitor``, into the heartbeat row,
and scripts/ops/heartbeat_watch.sh alerts on it (monitor_stale,
stops_unchecked).

Only the monitor writes this key, and it always writes the whole object (the
merge is a shallow ``doc || fields``). ``started_at`` and ``priced_at`` live
in this process only and are never read back from the row: after a restart
``priced_at`` is null until the first fully priced tick, so a wedge followed
by a restart never reads as fresh.

The stamp adds no quote fetch and no quote-cache read: every field comes from
what the tick already did (live/replay parity).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session

from . import runstate

if TYPE_CHECKING:
    from swingbot.core.planning.plan_manager import PollDemand

log = logging.getLogger(__name__)

#: At most one write per this many seconds unless something material changes:
#: every bot_heartbeat write raises the admin's undebounced `bot` SSE event.
WRITE_INTERVAL_S = 120
#: `unquoted` names in the doc; `unquoted_count` carries the full number.
UNQUOTED_CAP = 20
#: The `check_errors` entry for a raised plan-manager tick.
PLAN_MANAGER_ERROR = "<plan manager>"


@dataclass
class TickRecord:
    """What one monitor tick did. Every field starts at "unknown": a tick that
    raises part-way leaves the rest unknown, never zero."""
    outcome: str = "raised"                     # "ok" only once the tick body returned
    trade_tickers: list[str] | None = None      # None = the trade read did not complete
    live_prices: dict[str, float] | None = None
    plan_demand: PollDemand | None = None       # None = the manager demanded nothing
    manager_raised: bool = False
    check_errors: list[str] = field(default_factory=list)
    fetch_failed: bool = False


def positions_of(rec: TickRecord) -> list[str] | None:
    """The stops the monitor is responsible for this tick, or None (unknown)."""
    if rec.trade_tickers is None or rec.manager_raised:
        return None
    plan = rec.plan_demand.demanded if rec.plan_demand is not None else ()
    return sorted(set(rec.trade_tickers) | set(plan))


def _unpriced_trade_tickers(rec: TickRecord) -> list[str]:
    """Trade tickers the close call skipped: its own `not live or live <= 0`."""
    prices = rec.live_prices or {}
    out = []
    for ticker in rec.trade_tickers or ():
        live = prices.get(ticker)
        if not live or live <= 0:
            out.append(ticker)
    return out


def unquoted_of(rec: TickRecord) -> list[str]:
    """Sorted, uncapped: trade tickers without a usable price plus the plan
    tickers poll() demanded and did not price."""
    plan = rec.plan_demand.unpriced if rec.plan_demand is not None else ()
    return sorted(set(_unpriced_trade_tickers(rec)) | set(plan))


def check_errors_of(rec: TickRecord) -> list[str]:
    """Tickers whose close checks raised, plus the plan-manager marker."""
    errors = list(rec.check_errors)
    if rec.manager_raised:
        errors.append(PLAN_MANAGER_ERROR)
    return errors


def _iso(moment: dt.datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _signature(doc: dict) -> tuple:
    """The fields whose change is written at once, throttle or not."""
    return (doc["outcome"], tuple(doc["unquoted"]), doc["fetch_failed"],
            tuple(doc["check_errors"]))


class MonitorLiveness:
    """Process-local source of truth for `started_at` and `priced_at`."""

    def __init__(self, started_at: dt.datetime | None = None) -> None:
        self.started_at = started_at or dt.datetime.now(dt.timezone.utc)
        self.priced_at: dt.datetime | None = None
        self._signature: tuple | None = None
        self._written_at: dt.datetime | None = None

    def build(self, rec: TickRecord, now: dt.datetime) -> dict:
        """The full `monitor` doc for this tick; advances `priced_at` to `now`
        on a clean tick (ok, positions known, nothing unquoted, no errors)."""
        positions = positions_of(rec)
        unquoted = unquoted_of(rec)
        errors = check_errors_of(rec)
        if rec.outcome == "ok" and positions is not None and not unquoted and not errors:
            self.priced_at = now
        return {
            "started_at": _iso(self.started_at),
            "tick_at": _iso(now),
            "outcome": rec.outcome,
            "positions": positions,
            "unquoted": unquoted[:UNQUOTED_CAP],
            "unquoted_count": len(unquoted),
            "fetch_failed": bool(rec.fetch_failed),
            "check_errors": errors,
            "priced_at": _iso(self.priced_at),
            "market_open": session.is_nyse_regular_session(now),
        }

    def due(self, doc: dict, now: dt.datetime) -> bool:
        if self._written_at is None or _signature(doc) != self._signature:
            return True
        return (now - self._written_at).total_seconds() >= WRITE_INTERVAL_S

    def written(self, doc: dict, now: dt.datetime) -> None:
        self._signature = _signature(doc)
        self._written_at = now


#: Created at import, which is process start (loops.py imports this module).
_STATE = MonitorLiveness()


def _write(doc: dict) -> None:
    runstate._update_heartbeat({"monitor": doc})


async def stamp_tick(rec: TickRecord, *, now: dt.datetime | None = None) -> bool:
    """Build this tick's doc and write it when due. Never raises; True when
    a write was handed to the database."""
    try:
        moment = now or dt.datetime.now(dt.timezone.utc)
        doc = _STATE.build(rec, moment)
        if not _STATE.due(doc, moment):
            return False
        await asyncio.to_thread(_write, doc)
        _STATE.written(doc, moment)
        return True
    except Exception as exc:  # noqa: BLE001 -- the stamp must never break the monitor
        swallowed(log, "ops.monitor_stamp", exc,
                  "trade_monitor: liveness stamp failed: %s", exc,
                  level=logging.WARNING, exc_info=True)
        return False
```

`_STATE` and `_write` are looked up by name at call time, so tests replace them with `monkeypatch.setattr(monitor_liveness, ...)`. `runstate._update_heartbeat` already swallows a DB failure under its own tag; the `ops.monitor_stamp` handler covers everything else (the build, the thread hand-off, a patched writer).

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
python scripts/dev/testrun.py file tests/commands/test_monitor_liveness.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`, `0 xfailed` in both files (the ratchet accepts `ops.monitor_stamp`: it matches `TAG_RE` and no other handler uses it — `git grep -n '"ops.monitor_stamp"'` shows exactly one hit); the gate passes (every function in the new module is A or B).

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning/monitor_liveness.py tests/commands/test_monitor_liveness.py
git commit -m "feat(v184): monitor_liveness -- tick record, monitor doc, priced_at and the write throttle"
```

### Task V184-7: Wire the stamp into trade_monitor: unknown defaults, finally stamp, parity

**Model:** opus — the tick's control flow gains a `try/finally` whose failure modes (a raised tick, a raised manager, a failed fetch) must each read as "unknown", never as "checked"; the closes and the provider-call count must stay exactly as they are.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (the `from . import ...` line near l.24; `trade_monitor` at `@tasks.loop(seconds=60)`; new `_monitor_tick` directly below it)
- Modify: `tests/commands/test_trade_monitor_shared_quote.py` (append two parity tests)
- Create: `tests/commands/test_trade_monitor_liveness.py`

**Interfaces:**
- Consumes:
  - V184-3: `plan_manager.reset_monitor_batch_status() -> None`, `plan_manager.monitor_batch_failed() -> bool`; loops' `_legacy_live_price_batch` marks the flag when its `_run_bounded` returns `None`.
  - V184-4: `plan_manager.last_poll_demand() -> PollDemand | None`, `plan_manager.PollDemand(demanded, priced)`.
  - V184-5: `_check_open_tickers(tickers, live_prices) -> tuple[list, list[str]]`, `_run_plan_manager_tick() -> tuple[list, bool]`.
  - V184-6: `monitor_liveness.TickRecord`, `monitor_liveness.stamp_tick(rec, *, now=None) -> bool`, `monitor_liveness.MonitorLiveness(started_at=None)`, `monitor_liveness._STATE`, `monitor_liveness._write(doc)`, `monitor_liveness.PLAN_MANAGER_ERROR`.
- Produces: `async def _monitor_tick(rec: monitor_liveness.TickRecord) -> None` in `loops.py`; the `monitor` key in the production heartbeat row, which V184-9's watch reads.

**What the wiring guarantees** (spec § 1 Stamp timing; index § Review Focus):

- `rec` is created before any work, with every field "unknown" and `outcome="raised"`. `outcome` becomes `"ok"` only after `_monitor_tick` returns.
- The stamp runs in `finally`, after the closes, `run_manager_tick`, the plan-event posts, the equity sample, the notification retries and the close notices. A tick that raises is still stamped, and the exception still reaches `@trade_monitor.error` exactly as before.
- `_monitor_tick` resets the per-tick fetch-failed flag first, then fills `rec` as the work happens: `trade_tickers` right after the trade read, `live_prices` after the batch, `check_errors` after the checks, `manager_raised` after the manager tick, then `plan_demand` and `fetch_failed` (read after the manager tick, so a failed plan-side batch counts too).
- Every call keeps its order and arguments. The stamp makes no quote call: `test_monitor_and_manager_share_one_provider_call_per_tick` still counts one provider call.
- If V184-3 put `plan_manager.reset_monitor_batch_status()` at the top of `trade_monitor`'s body, it moves into `_monitor_tick` as its first statement; it appears exactly once in `loops.py` afterwards (`git grep -c reset_monitor_batch_status swingbot/commands/scanning/loops.py` prints `1`).

- [ ] **Step 1: Write the failing wiring tests** — create `tests/commands/test_trade_monitor_liveness.py`

```python
"""v184 V184-7: every trade_monitor tick ends by stamping the `monitor` key.

The stamp sits in a `finally`: a raised tick is still stamped (as `raised`,
with unknown positions), a raised plan manager reads as unknown rather than
checked, and a failing stamp never touches the closes. Order and arguments
of everything the tick did before v184 stay the same.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import datetime as dt

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops, monitor_liveness
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_manager import PollDemand

REAL_LIVE_PRICE_BATCH = loops._live_price_batch
START = dt.datetime(2026, 10, 21, 13, 0, tzinfo=dt.timezone.utc)


def _run_tick():
    return asyncio.run(scanning_mod.trade_monitor.coro())


@pytest.fixture
def env(monkeypatch):
    """A stubbed tick: two open trades (AAPL, MSFT), both priced; closes
    return nothing; the manager returns no events and demanded nothing.
    `env["seq"]` records the order of every step, the stamp write last."""
    state = {"prices": {"AAPL": 100.0, "MSFT": 200.0}, "demand": None, "events": [],
             "closed": {}, "seq": [], "writes": []}
    seq = state["seq"]
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness(started_at=START))

    def write(doc):
        seq.append("stamp")
        state["writes"].append(doc)
    monkeypatch.setattr(monitor_liveness, "_write", write)
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda status=None, limit=None: [
        {"ticker": "AAPL", "id": "t1", "status": "open"},
        {"ticker": "MSFT", "id": "t2", "status": "open"}])

    async def prices(tickers):
        seq.append("prices")
        return {t: p for t, p in state["prices"].items() if t in tickers}
    monkeypatch.setattr(loops, "_live_price_batch", prices)

    def close(ticker, live):
        seq.append(f"close:{ticker}")
        return state["closed"].get(ticker, [])

    def near_tp(ticker, live):
        seq.append(f"near_tp:{ticker}")
        return []
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", close)
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", near_tp)

    def tick():
        seq.append("manager")
        return state["events"]
    monkeypatch.setattr(plan_manager, "run_manager_tick", tick)
    monkeypatch.setattr(plan_manager, "last_poll_demand", lambda: state["demand"])

    async def post_events(events):
        seq.append("plan_events")

    async def equity(live_prices):
        seq.append("equity")

    async def retry():
        seq.append("retry")
    monkeypatch.setattr(loops, "_post_plan_events", post_events)
    monkeypatch.setattr(loops, "_record_equity_sample", equity)
    monkeypatch.setattr(loops, "_retry_notifications", retry)

    async def notify(bot, closed):
        seq.append("notify")

    async def presence():
        seq.append("presence")
    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", notify)
    monkeypatch.setattr(loops.presence, "_refresh_presence", presence)
    return state


def _doc(env):
    assert len(env["writes"]) == 1, env["writes"]
    return env["writes"][0]


def test_a_clean_tick_stamps_ok_with_positions_and_advances_priced_at(env):
    _run_tick()
    doc = _doc(env)
    assert doc["outcome"] == "ok"
    assert doc["positions"] == ["AAPL", "MSFT"]
    assert doc["unquoted"] == [] and doc["unquoted_count"] == 0
    assert doc["check_errors"] == [] and doc["fetch_failed"] is False
    assert doc["priced_at"] is not None and doc["priced_at"] == doc["tick_at"]
    assert doc["started_at"] == "2026-10-21T13:00:00+00:00"


def test_the_stamp_is_the_last_step_and_nothing_else_moved(env):
    env["closed"]["AAPL"] = [{"id": "t1"}]
    env["events"] = ["ev"]
    _run_tick()
    assert env["seq"] == ["prices", "close:AAPL", "near_tp:AAPL", "close:MSFT", "near_tp:MSFT",
                          "manager", "plan_events", "equity", "retry", "notify", "presence",
                          "stamp"]


def test_an_unquoted_trade_ticker_is_still_skipped_and_now_reported(env):
    env["prices"] = {"AAPL": 100.0}
    _run_tick()
    doc = _doc(env)
    assert "close:MSFT" not in env["seq"]
    assert doc["unquoted"] == ["MSFT"] and doc["unquoted_count"] == 1
    assert doc["priced_at"] is None


def test_plan_tickers_poll_demanded_join_positions_and_unpriced_ones_are_unquoted(env):
    env["demand"] = PollDemand(demanded=("NVDA", "AAPL"), priced=frozenset({"AAPL"}))
    _run_tick()
    doc = _doc(env)
    assert doc["positions"] == ["AAPL", "MSFT", "NVDA"]
    assert doc["unquoted"] == ["NVDA"]
    assert doc["priced_at"] is None


def test_a_raising_close_call_is_a_check_error(env, monkeypatch):
    def close(ticker, live):
        env["seq"].append(f"close:{ticker}")
        if ticker == "AAPL":
            raise RuntimeError("store locked")
        return []
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", close)
    _run_tick()
    doc = _doc(env)
    assert doc["check_errors"] == ["AAPL"]
    assert "near_tp:AAPL" not in env["seq"] and "near_tp:MSFT" in env["seq"]
    assert doc["outcome"] == "ok" and doc["priced_at"] is None


def test_a_raising_manager_reads_as_unknown_not_checked(env, monkeypatch):
    def boom():
        env["seq"].append("manager")
        raise RuntimeError("plan store down")
    monkeypatch.setattr(plan_manager, "run_manager_tick", boom)
    _run_tick()
    doc = _doc(env)
    assert doc["positions"] is None
    assert doc["check_errors"] == [monitor_liveness.PLAN_MANAGER_ERROR]
    assert doc["priced_at"] is None
    assert "equity" in env["seq"] and "retry" in env["seq"]


def test_a_raised_tick_is_still_stamped_as_raised_and_the_error_escapes(env, monkeypatch):
    def broken(status=None, limit=None):
        raise RuntimeError("trades table gone")
    monkeypatch.setattr(loops.trade_log, "get_trades", broken)
    with pytest.raises(RuntimeError, match="trades table gone"):
        _run_tick()
    doc = _doc(env)
    assert doc["outcome"] == "raised"
    assert doc["positions"] is None and doc["priced_at"] is None
    assert env["seq"] == ["stamp"]


def test_a_restart_forgets_priced_at(env, monkeypatch):
    _run_tick()
    assert env["writes"][0]["priced_at"] is not None
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness(started_at=START))
    monkeypatch.setattr(plan_manager, "run_manager_tick",
                        lambda: (_ for _ in ()).throw(RuntimeError("x")))
    env["writes"].clear()
    _run_tick()
    assert _doc(env)["priced_at"] is None


def test_a_failed_bounded_fetch_sets_fetch_failed(env, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(loops, "_live_price_batch", REAL_LIVE_PRICE_BATCH)
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: None)
    _run_tick()
    doc = _doc(env)
    assert doc["fetch_failed"] is True
    assert doc["unquoted"] == ["AAPL", "MSFT"]
    assert not any(step.startswith("close:") for step in env["seq"])


def test_the_fetch_failed_flag_is_reset_at_the_start_of_each_tick(env):
    plan_manager.mark_monitor_batch_failed()
    _run_tick()
    assert _doc(env)["fetch_failed"] is False


def test_a_raising_stamp_write_leaves_the_tick_untouched(env, monkeypatch):
    def boom(doc):
        raise RuntimeError("db down")
    monkeypatch.setattr(monitor_liveness, "_write", boom)
    env["closed"]["AAPL"] = [{"id": "t1"}]
    assert _run_tick() is None
    assert env["seq"] == ["prices", "close:AAPL", "near_tp:AAPL", "close:MSFT", "near_tp:MSFT",
                          "manager", "equity", "retry", "notify", "presence"]
```

- [ ] **Step 2: Write the failing parity tests** — append to `tests/commands/test_trade_monitor_shared_quote.py`

```python
def test_the_stamp_adds_no_quote_call_and_lands_in_the_heartbeat_row(layer_on, shared_db, monkeypatch):
    """v184: the liveness stamp reuses the tick's own results -- one provider
    call per tick, the same two monitor_quotes calls as before, and the
    `monitor` key in the real heartbeat row."""
    from swingbot.commands.scanning import monitor_liveness
    from swingbot.core.db.repositories.heartbeat import HeartbeatRepository
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness())
    real = plan_manager.monitor_quotes
    seen = []
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda t: seen.append(list(t)) or real(t))
    _tick(monkeypatch, [])
    assert layer_on.calls == 1
    assert seen == [["AAPL"], ["AAPL"]]          # trade monitor, then the manager's batch
    row = HeartbeatRepository().last()
    assert row is not None and row["monitor"]["outcome"] == "ok"
    assert row["monitor"]["positions"] is not None and "AAPL" in row["monitor"]["positions"]


def test_the_stamp_itself_reads_no_quote_and_no_cache(monkeypatch):
    from swingbot.commands.scanning import monitor_liveness
    from swingbot.core.marketdata import data
    for name in ("get_current_price_batch", "get_quote_batch", "peek_cached_batch_price"):
        monkeypatch.setattr(data, name, lambda *a, **k: pytest.fail("quote read by the stamp"))
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda t: pytest.fail("monitor_quotes"))
    monkeypatch.setattr(plan_manager, "_price_batch_fn", lambda t: pytest.fail("batch fn"))
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness())
    writes = []
    monkeypatch.setattr(monitor_liveness, "_write", writes.append)
    rec = monitor_liveness.TickRecord(outcome="ok", trade_tickers=["AAPL"],
                                      live_prices={"AAPL": 190.0})
    assert asyncio.run(monitor_liveness.stamp_tick(rec)) is True
    assert len(writes) == 1
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run:
```bash
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_liveness.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py
```
Expected: `test_trade_monitor_liveness.py` FAILS — every test sees `env["writes"] == []` (no stamp yet), and `test_a_raised_tick_is_still_stamped...` sees `env["seq"] == []`. In the shared-quote file the new heartbeat test FAILS on `row["monitor"]` (`KeyError` or `row is None`); `test_the_stamp_itself_reads_no_quote_and_no_cache` already passes (V184-6's module makes no quote call), which is the pin it exists for.

- [ ] **Step 4: Import the module in `loops.py`** — extend the existing package import line (today l.24) in alphabetical order:

```python
from . import book_status, cooldown, equity_recorder, monitor_liveness, notices, ops_watch, outlook, presence, recap, runstate
```

Importing it here, at bot start, creates `monitor_liveness._STATE`, so `started_at` is the process start.

- [ ] **Step 5: Split `trade_monitor` into the stamped wrapper and `_monitor_tick`** — replace the whole `trade_monitor` function (decorator, docstring and body, after V184-5) with the two functions below. The old docstring is kept word for word, with one v184 paragraph appended; `@trade_monitor.error` below it is unchanged.

```python
@tasks.loop(seconds=60)
async def trade_monitor():
    """
    Lightweight SL/TP price monitor — runs every 60 seconds, entirely
    separate from the full scan cycle.  For every open trade it fetches
    the live price (incl. premarket/aftermarket via get_current_price),
    calls close_if_live_price_hit() for an exact SL/TP hit, and then
    check_near_tp_timeout() for whatever's still open -- closing early,
    as a win at the live price, any trade that's gotten most of the way
    to its target and then stalled there instead of actually tapping it
    (see config.NEAR_TP_TIMEOUT_*). If any trade closes either way, a
    notification is posted to DISCORD_CHANNEL_TRADES_HISTORY_ID immediately,
    without waiting for the next scheduled scan.

    Runs regardless of whether a full scan is in progress. It used to skip
    whenever scan_engine.is_scan_running() was true, on the theory that the
    full scan's own SL/TP check (TradeLog.update_open_trades) already
    covered this tick -- but that function deliberately EXCLUDES every
    trade with a plan_id (see its own docstring: a v2 plan's real stop/
    target moves after TP1 and update_open_trades only ever sees the
    stale original levels), which is every trade once PLAN_ENGINE_V2 is
    on. With scans now taking minutes, the skip left plan-linked trades'
    stops and targets unmonitored for most of the day -- production
    incident, 2026-08-24: two trades sat "open" for hours after clearly
    breaching their stop. close_if_live_price_hit() and run_manager_tick()
    both write through their own store's lock (TradeLog._LOCK,
    plan_store._LOCK) and no-op on a trade/plan a concurrent scan already
    closed, so running alongside a scan is safe, not just tolerated.

    With no open trade rows the batched quote lookup below has nothing to fetch,
    but the plan-manager tick still runs: a plan can be open with no open
    trade row (`!trades clear` / the admin's clear-open delete rows and leave
    plans ACTIVE), and returning early here left those positions' stops and
    targets unmonitored until some unrelated trade opened.

    After the closes, one equity sample is recorded (v172, equity_recorder): it
    reuses this tick's prices and never raises.

    v184: every tick ends by stamping the `monitor` key into the heartbeat row
    (monitor_liveness), in a `finally` so a tick that raises is stamped too.
    The record starts "unknown" and becomes "ok" only when the work returned;
    scripts/ops/heartbeat_watch.sh alerts when the stamp ages past 300 s or
    the stops go unchecked during the regular session. The stamp makes no
    quote call and never raises.
    """
    rec = monitor_liveness.TickRecord()
    try:
        await _monitor_tick(rec)
        rec.outcome = "ok"
    finally:
        await monitor_liveness.stamp_tick(rec)


async def _monitor_tick(rec: "monitor_liveness.TickRecord") -> None:
    """One monitor tick's work (the pre-v184 body of trade_monitor), filling
    `rec` as each step completes so a raise part-way leaves the rest unknown."""
    from swingbot.core.planning import plan_manager
    plan_manager.reset_monitor_batch_status()
    open_trades = trade_log.get_trades(status="open", limit=200)
    tickers = list({t["ticker"] for t in open_trades})
    rec.trade_tickers = tickers

    live_prices = await _live_price_batch(tickers)
    rec.live_prices = live_prices
    all_newly_closed, rec.check_errors = await _check_open_tickers(tickers, live_prices)

    plan_events, rec.manager_raised = await _run_plan_manager_tick()
    rec.plan_demand = plan_manager.last_poll_demand()
    rec.fetch_failed = plan_manager.monitor_batch_failed()
    if plan_events:
        await _post_plan_events(plan_events)
    await _record_equity_sample(live_prices)
    await _retry_notifications()

    if all_newly_closed:
        from swingbot.core.scanning.embeds import notify_closed_trades
        try:
            await notify_closed_trades(bot, all_newly_closed)
        except Exception as exc:
            log.warning("trade_monitor: failed to post close notifications: %s", exc, exc_info=True)
        await presence._refresh_presence()
```

The `notify_closed_trades` handler moves unchanged (still untagged, so the ratchet count is the same). If V184-3 left a `reset_monitor_batch_status()` call at the top of the old body, it is gone with the old body: the one in `_monitor_tick` replaces it.

- [ ] **Step 6: Run the new tests to verify they pass**

Run:
```bash
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_liveness.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_shared_quote.py
```
Expected: both `0 failed`, `0 xfailed`; `test_monitor_and_manager_share_one_provider_call_per_tick` still passes unmodified.

- [ ] **Step 7: Re-run every other file that drives `trade_monitor`, the ratchet and the gate**

Run:
```bash
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py
python scripts/dev/testrun.py file tests/commands/test_trade_monitor_checks.py
python scripts/dev/testrun.py file tests/commands/test_monitor_liveness.py
python scripts/dev/testrun.py file tests/commands/test_equity_recorder.py
python scripts/dev/testrun.py file tests/commands/test_loops_follow_notify.py
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
python scripts/dev/testrun.py file tests/planning/test_manager_singleton_staleness_repro.py
python scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py
python scripts/dev/testrun.py file tests/tracking/test_close_if_live_price_hit.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python scripts/dev/complexity_gate.py
git grep -c reset_monitor_batch_status swingbot/commands/scanning/loops.py
```
Expected: every file `0 failed`, `0 xfailed`, unmodified (they never asserted on the heartbeat; the stamp's write reaches the per-checkout test database, as the equity sample's already does, and `_update_heartbeat` swallows a write failure). The gate passes: `trade_monitor` is A (2) and `_monitor_tick` well below 15. The `git grep -c` prints `swingbot/commands/scanning/loops.py:1`.

If one of those files fails because a test asserts on `log.warning` call counts or on the exact set of heartbeat writes, fix the test's stub (patch `monitor_liveness._write` to a list, as `test_trade_monitor_liveness.py` does), never the stamp; note the file in the commit message.

- [ ] **Step 8: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_trade_monitor_liveness.py tests/commands/test_trade_monitor_shared_quote.py
git commit -m "feat(v184): trade_monitor stamps its own liveness in a finally, with unknown defaults"
```

