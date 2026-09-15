# v81 — Execution Feed, part 2: the plan manager

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-09-10-v81-execution-feed_0-index.md` — its Global Constraints
apply to every task here.

---

### Task F3: Manager feed bookkeeping — stamps, `stop_moved`, pending notices

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — imports (lines 11-22); a
  module-level block after `class PlanEvent` (ends line 47); `poll()` (lines
  148-203); `_step_active` break-even lines (357-358); two methods after `_now`
  (line 146)
- Create: `tests/planning/test_plan_manager_feed.py`

**Interfaces:**
- Consumes: `TradePlanV2.notified_stop`, `TradePlanV2.pending_notice`,
  `plan_types.breakeven_trigger`, `config.TRAIL_NOTIFY_MIN_R` (all F1); existing
  `plan_types.effective_stop`, `plan_engine.runner_floor`, `session.session_date`.
- Produces (module `swingbot.core.planning.plan_manager`):
  - `STOP_EVENTS: frozenset[str]` = `{"be_moved", "tp1_partial", "stop_moved"}`
  - `NOTICE_EVENTS: frozenset[str]` = `{"filled", "cancelled_expired", "cancelled_invalidated", "closed"}`
  - `NOTICE_RESEND_DAYS = 5`
  - `trail_notify_min_r() -> float`
  - `last_told_stop(plan) -> float`
  - `resting_stop(plan) -> float`
  - `stop_move_event(plan, today_session: str, min_r: float) -> PlanEvent | None`
  - `PlanManager.resend_notices(self, *, reload: bool = True) -> list[PlanEvent]`
  - Stamps: `tp1_partial.detail["working_stop"]`; `closed.detail["session"]`
    (`"regular"`/`"extended"`), `["notified_stop"]`, `["bot_stop"]`.
  - `poll()` returns re-sent notices first, then each open plan's events plus
    any `stop_moved`.

- [ ] **Step 0: Check v79 is on `main`**

Run: `git log --oneline main --grep="feat(v79)"`
Expected: at least one line. If empty, **stop** and tell the human partner —
v79 edits this same file.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_feed.py`:

```python
"""v81: plan_manager's execution-feed bookkeeping -- stamps, stop_moved,
pending notices and their re-send. Injected clock and feed, no network."""
import datetime as dt
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_engine import PlanStatus, runner_floor
from swingbot.core.planning.plan_manager import (PlanManager, resting_stop,
                                                 stop_move_event, trail_notify_min_r)
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending

DAY = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)          # Thursday, regular hours
AFTER_HOURS = dt.datetime(2026, 8, 27, 19, 30, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _pinned_flags(monkeypatch):
    """A dev machine's .env must never decide these outcomes."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_DEBOUNCE_TICKS", 2)
    monkeypatch.setattr(config, "QUIET_HOURS_START_ET", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_ET", 8)
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.25)
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _env(tmp_path, prices, plan=None, atr_fn=None):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price, atr_fn=atr_fn)


def _transitions(events):
    return [e.transition for e in events]


def _runner(working_stop, notified_stop=None):
    return _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 tp2=None, working_stop=working_stop, notified_stop=notified_stop)


# --- pure rules ----------------------------------------------------------------

def test_the_threshold_is_clamped_into_its_safe_range(monkeypatch):
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 3.0)
    assert trail_notify_min_r() == 1.0
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.0)
    assert trail_notify_min_r() == 0.01


def test_a_move_just_under_the_threshold_is_silent():
    assert stop_move_event(_runner(107.95, notified_stop=106.75), "2026-08-27", 0.25) is None


def test_a_move_at_the_threshold_emits_stop_moved():
    event = stop_move_event(_runner(108.0, notified_stop=106.75), "2026-08-27", 0.25)
    assert event.transition == "stop_moved"
    assert event.detail == {"old": 106.75, "new": 108.0,
                            "r_moved": pytest.approx(0.25), "effective": "now"}


def test_nothing_delivered_yet_reads_as_the_original_stop():
    event = stop_move_event(_runner(115.0), "2026-08-27", 0.25)
    assert event.detail["old"] == 95.0
    assert event.detail["r_moved"] == pytest.approx(4.0)


def test_a_break_even_armed_today_takes_effect_next_session():
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0, be_armed_session="2026-08-27")
    assert stop_move_event(plan, "2026-08-27", 0.25).detail["effective"] == "next_session"
    assert stop_move_event(plan, "2026-08-28", 0.25).detail["effective"] == "now"


def test_a_pending_plan_never_emits():
    assert stop_move_event(_pending(), "2026-08-27", 0.25) is None


def test_resting_stop_uses_the_runner_floor_for_a_pre_v39_partial_row():
    assert resting_stop(_runner(None)) == pytest.approx(runner_floor(100.0, 110.0))
    assert resting_stop(_runner(112.0)) == 112.0


# --- poll ----------------------------------------------------------------------

def test_break_even_emits_only_be_moved_in_its_own_tick(tmp_path):
    store, mgr = _env(tmp_path, [105.0])
    assert _transitions(mgr.poll(now=DAY)) == ["be_moved"]


def test_an_unacknowledged_break_even_is_resent_as_stop_moved(tmp_path):
    store, mgr = _env(tmp_path, [105.0, 105.0, 105.0])
    mgr.poll(now=DAY)
    events = mgr.poll(now=DAY)
    assert _transitions(events) == ["stop_moved"]
    assert (events[0].detail["new"], events[0].detail["effective"]) == (100.0, "next_session")

    plan = store.get("p1")
    plan.notified_stop = 100.0            # what ack_notified records on delivery
    store.update(plan)
    assert mgr.poll(now=DAY) == []


def test_tp1_partial_carries_the_runner_stop(tmp_path):
    store, mgr = _env(tmp_path, [110.5], plan=_active(tp2=None))
    events = mgr.poll(now=DAY)
    assert _transitions(events) == ["tp1_partial"]
    assert events[0].detail["working_stop"] == pytest.approx(runner_floor(100.0, 110.0))


def test_a_trail_ratchet_emits_stop_moved_in_the_same_tick(tmp_path):
    # ATR 2.0 x trail_atr_mult 2.5: at 120 the trail is 115.
    store, mgr = _env(tmp_path, [110.5, 120.0], plan=_active(tp2=None),
                      atr_fn=lambda ticker: 2.0)
    mgr.poll(now=DAY)
    plan = store.get("p1")
    plan.notified_stop = plan.working_stop     # the TP1 message was delivered
    store.update(plan)

    events = mgr.poll(now=DAY)
    assert _transitions(events) == ["stop_moved"]
    assert events[0].detail["old"] == pytest.approx(runner_floor(100.0, 110.0))
    assert events[0].detail["new"] == 115.0


def test_a_regular_session_close_is_stamped_and_queued(tmp_path):
    store, mgr = _env(tmp_path, [94.5])
    events = mgr.poll(now=DAY)
    assert _transitions(events) == ["closed"]
    detail = events[0].detail
    assert (detail["session"], detail["notified_stop"], detail["bot_stop"]) == ("regular", 95.0, 95.0)

    notice = store.get("p1").pending_notice
    assert notice["transition"] == "closed"
    assert notice["detail"]["exit_price"] == 94.5
    assert datetime.fromisoformat(notice["at"]).tzinfo is not None


def test_an_extended_hours_close_is_stamped_extended(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 94.0])
    assert mgr.poll(now=AFTER_HOURS) == []           # first confirming tick
    events = mgr.poll(now=AFTER_HOURS)
    assert _transitions(events) == ["closed"]
    assert events[0].detail["session"] == "extended"


def test_a_fill_is_queued_as_a_notice(tmp_path):
    store, mgr = _env(tmp_path, [106.0], plan=_pending())
    assert _transitions(mgr.poll(now=DAY)) == ["filled"]
    assert store.get("p1").pending_notice["transition"] == "filled"


def test_an_unacknowledged_notice_is_resent_every_tick(tmp_path):
    store, mgr = _env(tmp_path, [94.5])
    mgr.poll(now=DAY)                                 # closes and queues the notice
    for _ in range(2):
        resent = mgr.poll(now=DAY)
        assert _transitions(resent) == ["closed"]
        assert resent[0].detail["exit_price"] == 94.5
    assert store.get("p1").status == PlanStatus.CLOSED


def test_a_resent_notice_never_reaches_the_trade_log(tmp_path):
    class RecordingLog:
        def __init__(self):
            self.closes = []

        def reload(self):
            pass

        def close_plan_trade(self, *args):
            self.closes.append(args)

    trade_log = RecordingLog()
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    mgr = PlanManager(store, lambda ticker: 94.5, trade_log=trade_log)
    for _ in range(3):
        mgr.poll(now=DAY)
    assert len(trade_log.closes) == 1


def test_a_notice_older_than_five_days_is_dropped_not_resent(tmp_path, caplog):
    stale = _plan(status="CLOSED", pending_notice={
        "transition": "closed", "detail": {"reason": "loss", "exit_price": 94.5},
        "at": "2000-01-01T00:00:00+00:00"})
    store, mgr = _env(tmp_path, [], plan=stale)
    assert mgr.poll(now=DAY) == []
    assert store.get("p1").pending_notice is None
    assert "dropping undelivered closed" in caplog.text


# --- parity: the ledger is never read by an exit decision -----------------------

def _walk(path, **ledger):
    """Break-even, TP1, a trail ratchet, a pullback and a trail exit."""
    store = PlanStore(path=str(path))
    store.add(_active(tp2=None, **ledger))
    feed = FakePriceFeed()
    feed.set_series("AAPL", [105.0, 110.5, 120.0, 118.0, 114.9])
    mgr = PlanManager(store, feed.get_price, atr_fn=lambda ticker: 2.0)
    for _ in range(5):
        mgr.poll(now=DAY)
    plan = store.get("p1")
    return (plan.status, plan.working_stop, plan.entry_price, plan.legs_realized,
            [(h["status"], h["reason"]) for h in plan.status_history])


def test_the_feed_ledger_never_changes_an_exit(tmp_path):
    plain = _walk(tmp_path / "plain.json")
    primed = _walk(tmp_path / "primed.json", notified_stop=123.0, pending_notice={
        "transition": "filled", "detail": {"entry_price": 100.0},
        "at": datetime.now(timezone.utc).isoformat()})
    assert plain == primed
    assert plain[0] == PlanStatus.CLOSED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py`
Expected: FAIL — `ImportError: cannot import name 'resting_stop'`.

- [ ] **Step 3: Add the imports**

In `swingbot/core/planning/plan_manager.py`, change
`from datetime import datetime, timezone` to:

```python
from datetime import datetime, timedelta, timezone
```

and after `from swingbot.core.planning.plan_store import PlanStore` add:

```python
from swingbot.core.planning.plan_types import breakeven_trigger, effective_stop
```

- [ ] **Step 4: Add the module-level feed rules**

Directly after `class PlanEvent` (after its `detail: dict = field(default_factory=dict)` line), add:

```python
# v81 execution feed. Stop events tell the reader where to rest the stop and
# are acknowledged through plan.notified_stop; notice events are queued on
# plan.pending_notice and re-sent until acknowledged. Neither field is read
# by any exit path (tests/planning/test_plan_manager_feed.py pins that).
STOP_EVENTS = frozenset({"be_moved", "tp1_partial", "stop_moved"})
NOTICE_EVENTS = frozenset({"filled", "cancelled_expired", "cancelled_invalidated", "closed"})
NOTICE_RESEND_DAYS = 5


def trail_notify_min_r() -> float:
    """config.TRAIL_NOTIFY_MIN_R clamped to [0.01, 1.0]. The Field's min/max
    bind only the admin API, not .env loading; above 1R a failed break-even
    ping (a 1R move) could never be re-sent as stop_moved."""
    return min(1.0, max(0.01, float(config.TRAIL_NOTIFY_MIN_R)))


def last_told_stop(plan) -> float:
    """The stop last delivered to the reader; the order ticket delivered stop_loss."""
    return plan.notified_stop if plan.notified_stop is not None else plan.stop_loss


def resting_stop(plan) -> float:
    """The stop the reader should leave resting: the one this manager's exit
    check uses from the next session on. A PARTIAL row persisted before v39
    has no working_stop -- _step_partial falls back to the runner floor, and
    so does this; effective_stop would return the original risk stop there,
    the display bug v73 removed."""
    if plan.status == PlanStatus.PARTIAL and plan.working_stop is None:
        return runner_floor(plan.entry_price, plan.tp1)
    return effective_stop(plan)


def _stop_at_close(plan) -> float:
    """The stop the bot was holding when the plan closed."""
    if plan.working_stop is not None:
        return plan.working_stop
    if plan.legs_realized:
        return runner_floor(plan.entry_price, plan.tp1)
    return plan.stop_loss


def stop_move_event(plan, today_session: str, min_r: float) -> PlanEvent | None:
    """A stop_moved event when the resting stop is at least `min_r` of the
    plan's initial risk away from the stop last delivered, else None."""
    if plan.entry_price is None or plan.status not in (PlanStatus.ACTIVE, PlanStatus.PARTIAL):
        return None
    risk = abs(plan.entry_price - plan.stop_loss)
    if risk <= 0:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    old, new = last_told_stop(plan), resting_stop(plan)
    r_moved = (new - old) * sign / risk
    if abs(r_moved) < min_r - 1e-9:
        return None
    effective = ("next_session" if plan.status == PlanStatus.ACTIVE
                 and plan.be_armed_session == today_session else "now")
    return PlanEvent(plan.plan_id, "stop_moved",
                     {"old": old, "new": new, "r_moved": r_moved, "effective": effective})
```

- [ ] **Step 5: Add the two methods**

In `class PlanManager`, directly after `_now`, add:

```python
    def resend_notices(self, *, reload: bool = True) -> list[PlanEvent]:
        """v81: re-emit every notice the execution feed has not acknowledged.
        One queued more than NOTICE_RESEND_DAYS ago is dropped with a warning:
        a days-old EXIT or CANCEL is history, not an instruction. These events
        never pass through _on_event -- the trade log recorded them already."""
        if reload:
            self.store.reload()
        cutoff = datetime.now(timezone.utc) - timedelta(days=NOTICE_RESEND_DAYS)
        events: list[PlanEvent] = []
        for plan in self.store.all():
            notice = plan.pending_notice
            if not notice:
                continue
            try:
                queued = datetime.fromisoformat(notice["at"])
                if queued.tzinfo is None:
                    queued = queued.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                queued = None
            if queued is None or queued < cutoff:
                log.warning("execution feed: dropping undelivered %s for plan %s (queued %s)",
                            notice.get("transition"), plan.plan_id, notice.get("at"))
                plan.pending_notice = None
                self.store.update(plan)
                continue
            events.append(PlanEvent(plan.plan_id, notice["transition"],
                                    dict(notice["detail"])))
        return events

    def _feed_bookkeeping(self, plan: TradePlanV2, new_events: list[PlanEvent],
                          regular: bool, now=None) -> list[PlanEvent]:
        """v81: stamp this tick's events for the execution feed, queue its
        latest notice, and add a stop_moved when the resting stop has drifted
        from what the reader was told. Runs after _on_event."""
        for event in new_events:
            if event.transition == "tp1_partial":
                event.detail["working_stop"] = plan.working_stop
            elif event.transition == "closed":
                event.detail["session"] = "regular" if regular else "extended"
                event.detail["notified_stop"] = last_told_stop(plan)
                event.detail["bot_stop"] = _stop_at_close(plan)
        notices = [e for e in new_events if e.transition in NOTICE_EVENTS]
        if notices:
            latest = notices[-1]
            plan.pending_notice = {"transition": latest.transition,
                                   "detail": dict(latest.detail), "at": self._now()}
            self.store.update(plan)
        if not regular or any(e.transition in STOP_EVENTS | NOTICE_EVENTS
                              for e in new_events):
            return new_events
        moved = stop_move_event(plan, session_date(now), trail_notify_min_r())
        return new_events + [moved] if moved is not None else new_events
```

- [ ] **Step 6: Wire them into `poll()`**

In `poll()`, replace:

```python
        events: list[PlanEvent] = []
        for plan in self.store.open_plans():
```

with:

```python
        events: list[PlanEvent] = self.resend_notices(reload=False)   # v81
        for plan in self.store.open_plans():
```

and replace the end of the loop:

```python
            for event in new_events:
                self._on_event(plan, event)
            events.extend(new_events)
        return events
```

with:

```python
            for event in new_events:
                self._on_event(plan, event)
            events.extend(self._feed_bookkeeping(plan, new_events, regular, now))
        return events
```

- [ ] **Step 7: Read the break-even price through the shared helper**

In `_step_active`, replace:

```python
        target_dist = abs(plan.tp1 - entry)
        be_trigger = entry + sign * plan.breakeven_trigger_fraction * target_dist
```

with:

```python
        be_trigger = breakeven_trigger(plan, entry)   # v81: one formula, shared with the ticket
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py`
Expected: PASS — the break-even refactor changes no outcome.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_extended_hours.py`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_feed.py
git commit -m "feat(v81): plan manager stamps feed events, emits stop_moved and re-sends notices"
```

---

### Task F4: `ack_notified` and `run_notice_sweep`

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — `typing` import; a
  `Delivery` class after `stop_move_event`; `run_manager_tick` (lines 650-663)
  and two new functions after it
- Create: `tests/planning/test_plan_manager_feed_ack.py`

**Interfaces:**
- Consumes: `PlanManager.resend_notices` (F3); `TradePlanV2` ledger fields (F1).
- Produces (module `swingbot.core.planning.plan_manager`):
  - `class Delivery(NamedTuple)`: `plan_id: str`, `kind: str` (`"stop"` or
    `"notice"`), `value: object` (the delivered stop price, or the delivered
    notice's transition)
  - `ack_notified(deliveries: list[Delivery]) -> None`
  - `run_notice_sweep() -> list[PlanEvent]`

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_plan_manager_feed_ack.py`:

```python
"""v81: ack_notified records what the execution feed delivered, through the
manager's own store; run_notice_sweep re-sends notices with no manager tick."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import Delivery, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(pm, "_MANAGER", None)
    return PlanStore()


def _notice(transition="closed"):
    return {"transition": transition, "detail": {"reason": "loss", "exit_price": 94.5},
            "at": datetime.now(timezone.utc).isoformat()}


def test_a_delivered_stop_is_recorded(store):
    store.add(_plan(status="PARTIAL", entry_price=100.0, working_stop=107.3))
    pm.ack_notified([Delivery("p1", "stop", 107.3)])
    assert PlanStore().get("p1").notified_stop == 107.3


def test_a_delivered_notice_clears_the_queue(store):
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    pm.ack_notified([Delivery("p1", "notice", "closed")])
    assert PlanStore().get("p1").pending_notice is None


def test_an_older_delivery_never_clears_a_newer_notice(store):
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    pm.ack_notified([Delivery("p1", "notice", "filled")])
    assert PlanStore().get("p1").pending_notice["transition"] == "closed"


def test_ack_writes_through_the_live_managers_store(store, monkeypatch):
    store.add(_plan(status="PARTIAL", entry_price=100.0, working_stop=107.3))
    manager = PlanManager(PlanStore(), lambda ticker: 100.0)
    monkeypatch.setattr(pm, "_MANAGER", manager)
    pm.ack_notified([Delivery("p1", "stop", 107.3)])
    assert manager.store.get("p1").notified_stop == 107.3


def test_empty_input_and_unknown_plans_are_ignored(store):
    pm.ack_notified([])
    pm.ack_notified([Delivery("missing", "stop", 1.0)])


def test_run_notice_sweep_resends_without_fetching_a_price(store, monkeypatch):
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    monkeypatch.setattr(pm, "_price_fn",
                        lambda ticker: pytest.fail("the sweep must not fetch prices"))
    assert [e.transition for e in pm.run_notice_sweep()] == ["closed"]


def test_run_notice_sweep_is_a_noop_with_the_manager_off(store, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    store.add(_plan(status="CLOSED", pending_notice=_notice("closed")))
    assert pm.run_notice_sweep() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed_ack.py`
Expected: FAIL — `ImportError: cannot import name 'Delivery'`.

- [ ] **Step 3: Add `Delivery`**

In `swingbot/core/planning/plan_manager.py`, after
`from dataclasses import dataclass, field` add:

```python
from typing import NamedTuple
```

Directly after `def stop_move_event(...)` (added in F3), add:

```python
class Delivery(NamedTuple):
    """One execution-feed message that reached a notifying channel --
    lifecycle_embeds.notify_plan_events returns these for ack_notified."""

    plan_id: str
    kind: str       # "stop" | "notice"
    value: object   # the delivered stop price, or the delivered notice's transition
```

- [ ] **Step 4: Factor the singleton and add the two functions**

Replace `run_manager_tick` (from `def run_manager_tick() -> list[PlanEvent]:`
through `    return _MANAGER.poll()`) with:

```python
def _manager() -> PlanManager:
    """The process-wide PlanManager, built on first use."""
    global _MANAGER
    if _MANAGER is None:
        from swingbot.core.tracking.performance import TradeLog
        _MANAGER = PlanManager(PlanStore(), _price_fn, atr_fn=_live_atr,
                               bar_count_fn=_bars_since, trade_log=TradeLog())
    return _MANAGER


def run_manager_tick() -> list[PlanEvent]:
    """One synchronous manager tick -- the trade_monitor loop calls this via
    asyncio.to_thread. Flag off = pure no-op (no store instantiation, no
    file creation)."""
    from swingbot import config
    if not config.INTRADAY_MANAGER_V2:
        return []
    # Production reads the wall clock; poll's optional clock is test injection.
    return _manager().poll()


def run_notice_sweep() -> list[PlanEvent]:
    """v81: re-send unacknowledged notices when trade_monitor has no open
    trade to tick for -- exactly the state right after the last position
    closes, whose EXIT must still reach the reader. Fetches no prices."""
    from swingbot import config
    if not config.INTRADAY_MANAGER_V2:
        return []
    return _manager().resend_notices()


def ack_notified(deliveries) -> None:
    """v81: record what the execution feed delivered. Writes through the live
    manager's own store (reloaded first), so the manager stays the only
    writer of plans. A stop delivery sets notified_stop; a notice delivery
    clears pending_notice only when it is still that same notice."""
    if not deliveries:
        return
    store = _MANAGER.store if _MANAGER is not None else PlanStore()
    store.reload()
    for delivery in deliveries:
        plan = store.get(delivery.plan_id)
        if plan is None:
            continue
        if delivery.kind == "stop":
            plan.notified_stop = float(delivery.value)
        elif delivery.kind == "notice":
            notice = plan.pending_notice
            if not notice or notice.get("transition") != delivery.value:
                continue       # a newer notice replaced the one delivered; keep it
            plan.pending_notice = None
        else:
            continue
        store.update(plan)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed_ack.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/planning/test_trade_monitor_wiring.py`
Expected: PASS — the singleton refactor keeps `_price_fn`/`_bars_since` injectable.

Run: `python scripts/dev/testrun.py file tests/planning/test_manager_singleton_staleness_repro.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_feed_ack.py
git commit -m "feat(v81): ack_notified and run_notice_sweep"
```
