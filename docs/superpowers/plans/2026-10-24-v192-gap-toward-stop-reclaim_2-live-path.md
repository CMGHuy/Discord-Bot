# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 2: the live path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V192-9:" -A 300 <this file>`.

**Scope of this part (V192-8..V192-13):** live session timing and the open decision (fill at the open, the open-through-stop and risk-cap cancels, the open-beyond-TP1 scratch, the reclaim order), the premarket stop-cross debounce and the missed-open expiry; the reclaim wait, its fill at `E` and the end-of-session cancel, safe across a restart; the feed instruction copy and `Kind.RECLAIM_ORDER`; the manager's notice, log and placeholder wiring and the follower mapping; the alert's market-on-open line; scan-to-fill integration and the live/replay parity of `E`, `a_t`, `X` and the open decision.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (created in V192-1, Step 1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`. Never edit the main tree's files from a task.

**Database:** the `PlanManager` tests here use `PlanStore()` against the shared `swing-db` container, like `tests/planning/test_plan_manager_pending.py`. Run `/replicate-prod-db` once before the first of them (CLAUDE.md); never start a per-task container.

**Clock in tests:** 2026-10-13 is a Tuesday, 2026-10-14 a Wednesday, 2026-10-16 a Friday; no NYSE holiday falls in that week. Berlin runs ET + 6 h that week (CEST until 2026-10-25), so every clock below lands outside the default 23:00–08:00 Berlin quiet window unless a test says otherwise. Every manager test pins `INTRADAY_RTH_ONLY=True`, `QUIET_HOURS_START_BERLIN=23`, `QUIET_HOURS_END_BERLIN=8` (the `test_plan_manager_poll_window.py` idiom).

**Complexity:** after every code task run `python scripts/dev/complexity_gate.py`; it must pass. `PlanManager.poll` (20), `_step_active` (21) and `_on_event` (15) gain no branch (index § Global Constraints).

**What part 1 built that this part consumes** (verify with `git grep -n` in the worktree before starting a task): `swingbot/core/planning/gap_reclaim.py` — `OPEN_THROUGH_STOP`, `GAP_NO_RECLAIM`, `RISK_CAP`, `FILL_OPEN`, `RECLAIM_WAIT`, `tick_for`, `atr_at`, `reclaim_level_for`, `waits_for_open`, `stamp_next_open`, `decide_at_open`, `reclaim_touched`, `reclaim_fill_price` (V192-4); `TradePlanV2.reclaim_atr`, `reclaim_level`, `reclaim_session`, `waits_next_open` (V192-3); `config.MARKET_ENTRY_NEXT_OPEN`, `config.GAP_RECLAIM_ATR` (V192-2); builders building waiting market plans (V192-5); `swingbot/core/planning/market_next_open.py` — `next_open_market_exit`, `next_open_fill_bar`, `observing`, `NextOpenDecision` (V192-6, V192-7).

---

# Phase 5 — The live open decision

### Task V192-8: Live open decision and premarket stop-cross cancel
**Model:** opus — a new state-machine step ahead of the stop-entry rule on live paper plans, with session timing, a debounce and four outcomes; a wrong branch fills at a stale or through-the-stop price.

**Files:**
- Create: `swingbot/core/planning/market_open.py`
- Modify: `swingbot/core/planning/plan_manager.py` — imports (`:17-40`); module tables after `_STOPPED_REASONS` (`:158`); `PlanManager.__init__` (`:473-503`, one attribute); `_step` (`:863`, one routing line); `_step_pending` (`:955-1000`, its risk-cap block extracted into `_cancel_risk_cap`, behaviour unchanged); new methods after `_step_pending`
- Create: `tests/planning/test_market_open.py`, `tests/planning/test_plan_manager_market_open.py`

**Interfaces:**
- Consumes: `gap_reclaim.waits_for_open(plan)`, `gap_reclaim.decide_at_open(plan, open_price) -> str`, `gap_reclaim.FILL_OPEN`, `RECLAIM_WAIT`, `RISK_CAP`, `OPEN_THROUGH_STOP` (V192-4); `TradePlanV2.waits_next_open`, `reclaim_level`, `reclaim_session` (V192-3); `lifecycle.at_or_beyond_stop(plan, price)` (`lifecycle.py:198`); `session.is_nyse_regular_session`, `is_tape_open`, `now_et`, `nyse_calendar`, `session_close`, `RTH_OPEN`, `US_MARKET_TZ` (`swingbot/core/market/session.py`).
- Produces (index § Contracts): `market_open.PREMARKET_STOP_CONFIRM_POLLS = 2`; `market_open.deciding_session(plan) -> dt.date | None`; `market_open.market_phase(plan, now=None) -> str`, one of the module constants `BEFORE = "before"`, `EXTENDED = "extended"`, `OPEN = "open"`, `MISSED = "missed"`, `WAITING = "waiting"`, `AFTER_CLOSE = "after_close"`; `PlanManager._step_market_open(self, plan, price, now=None) -> list[PlanEvent]` (routed from `_step` by `waits_for_open`); `PlanManager._premarket_hits: dict[str, int]`; the module table `plan_manager._MARKET_PHASE_STEPS` (phase -> method name; V192-9 points `WAITING` and `AFTER_CLOSE` at its own methods); `PlanManager._cancel_risk_cap(self, plan, fill) -> list[PlanEvent]`; `plan_manager.GAP_TARGET_REASON = "gap_target"`.
- Events (exact detail keys, index § Contracts): `filled {"entry_price", "live_price", "fill": "open"}`; `gap_reclaim_order {"entry_price": E, "open_price", "reclaim_level": X, "order": "buy_stop"|"sell_stop", "tif": "DAY"}`; `cancelled_open_through_stop {"live_price", "phase": "open"|"premarket"}`; `cancelled_risk_cap` with the `_step_pending` keys; `cancelled_expired {"reason": "missed_open", "bars_waited": 0, "session": ISO date | None, "cancel_resting_order": True}`; an open at or beyond TP1 emits `filled` then `closed {"reason": "gap_target", "exit_price": open, "leg": {fraction 1.0, r 0.0, reason "gap_target"}, "_terminal_persisted": False}`. `record_transition` reasons: `next_open_fill`, `open_through_stop` (extra `{"phase"}`), `risk_cap`, `missed_open`, `gap_target`.

The deciding session follows the index: the first NYSE session whose 09:30 ET open is at or after `issued_at` (fallback: the session after `created_at`). The phase uses `is_nyse_regular_session`, the holiday- and half-day-aware form of the index's `is_regular_session`: on the deciding session the two agree except after a 13:00 half-day close, where only the NYSE form is right. The first regular-session poll on the deciding session decides at its price, as the index fixes it. The gap-target close is booked from `_on_event` (`_terminal_persisted: False`), never `_persist_terminal`: the `filled` event must first move the scan's placeholder trade onto the open, or `close_plan_trade` would close the placeholder and `record_plan_fill` would then find nothing and log a second trade.

- [ ] **Step 1: Write the failing timing tests** — `tests/planning/test_market_open.py`

```python
"""V192-8: which NYSE session's open decides a waiting market plan, and where a
poll sits against it. Pure: no store, no price."""
import datetime as dt

import pytest

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import market_open as mo
from swingbot.core.planning.plan_types import PlanStatus
from tests.planning.test_plan_engine_model import _plan


def _et(month, day, hh, mm=0):
    return dt.datetime(2026, month, day, hh, mm, tzinfo=US_MARKET_TZ)


def _waiting(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", created_at="2026-10-13",
                issued_at=_et(10, 13, 15).isoformat(), status=PlanStatus.PENDING,
                waits_next_open=True, stop_loss=98.5, tp1=103.0)
    base.update(kw)
    return _plan(**base)


def test_the_premarket_confirm_count_is_two():
    assert mo.PREMARKET_STOP_CONFIRM_POLLS == 2


def test_the_phase_names_are_the_frozen_strings():
    assert (mo.BEFORE, mo.EXTENDED, mo.OPEN, mo.MISSED, mo.WAITING, mo.AFTER_CLOSE) == (
        "before", "extended", "open", "missed", "waiting", "after_close")


@pytest.mark.parametrize("issued, expected", [
    (_et(10, 13, 15), dt.date(2026, 10, 14)),         # after Tuesday's open -> Wednesday
    (_et(10, 13, 8), dt.date(2026, 10, 13)),          # Tuesday premarket -> Tuesday's open
    (_et(10, 13, 9, 30), dt.date(2026, 10, 13)),      # exactly at the open: that open
    (_et(10, 13, 9, 31), dt.date(2026, 10, 14)),
    (_et(10, 16, 17), dt.date(2026, 10, 19)),         # Friday evening -> Monday
    (_et(10, 17, 10), dt.date(2026, 10, 19)),         # Saturday -> Monday
    (_et(11, 26, 12), dt.date(2026, 11, 27)),         # Thanksgiving -> the half-day after
])
def test_deciding_session_from_issued_at(issued, expected):
    assert mo.deciding_session(_waiting(issued_at=issued.isoformat())) == expected


def test_issued_at_is_read_in_et_and_naive_means_utc():
    # 13:00 UTC = 09:00 ET: before Tuesday's open
    assert mo.deciding_session(_waiting(issued_at="2026-10-13T13:00:00+00:00")) == dt.date(2026, 10, 13)
    # naive 14:00 is UTC = 10:00 ET: after the open
    assert mo.deciding_session(_waiting(issued_at="2026-10-13T14:00:00")) == dt.date(2026, 10, 14)


@pytest.mark.parametrize("created, expected", [
    ("2026-10-13", dt.date(2026, 10, 14)),
    ("2026-10-16", dt.date(2026, 10, 19)),
    ("2026-10-13T00:00:00+00:00", dt.date(2026, 10, 14)),   # UTC midnight = that date
    ("2026-10-13T20:30:00-04:00", dt.date(2026, 10, 14)),   # its ET date
])
def test_without_issued_at_the_session_after_created_at_decides(created, expected):
    assert mo.deciding_session(_waiting(issued_at=None, created_at=created)) == expected


def test_an_unreadable_issued_at_falls_back_and_unreadable_both_give_none():
    assert mo.deciding_session(_waiting(issued_at="garbage")) == dt.date(2026, 10, 14)
    assert mo.deciding_session(_waiting(issued_at="garbage", created_at="nope")) is None


@pytest.mark.parametrize("now, phase", [
    (_et(10, 13, 15, 30), mo.BEFORE),      # the alert day's RTH, after the issue
    (_et(10, 13, 16, 30), mo.EXTENDED),    # the alert day's after-hours tape
    (_et(10, 14, 2, 30), mo.BEFORE),       # polled, but before any tape exists
    (_et(10, 14, 8, 0), mo.EXTENDED),      # the deciding day's premarket
    (_et(10, 14, 9, 30), mo.OPEN),
    (_et(10, 14, 15, 59), mo.OPEN),        # the first RTH poll decides, whenever it lands
    (_et(10, 14, 16, 30), mo.MISSED),      # the deciding close passed with no RTH poll
    (_et(10, 15, 8, 0), mo.MISSED),
    (_et(10, 15, 10, 0), mo.MISSED),
])
def test_market_phase(now, phase):
    assert mo.market_phase(_waiting(), now) == phase


def test_a_half_day_deciding_session_is_missed_after_its_13_00_close():
    plan = _waiting(issued_at=_et(11, 26, 12).isoformat(), created_at="2026-11-26")
    assert mo.market_phase(plan, _et(11, 27, 12, 59)) == mo.OPEN
    assert mo.market_phase(plan, _et(11, 27, 13, 30)) == mo.MISSED


def test_no_deciding_session_is_missed():
    assert mo.market_phase(_waiting(issued_at="x", created_at="y"), _et(10, 14, 10)) == mo.MISSED


@pytest.mark.parametrize("now, phase", [
    (_et(10, 14, 11), mo.WAITING),
    (_et(10, 14, 15, 59), mo.WAITING),
    (_et(10, 14, 16, 0), mo.AFTER_CLOSE),     # the close is exclusive
    (_et(10, 15, 9, 45), mo.AFTER_CLOSE),     # the bot was down across the close
])
def test_a_plan_resting_for_its_reclaim(now, phase):
    assert mo.market_phase(_waiting(reclaim_session="2026-10-14"), now) == phase
```

- [ ] **Step 2: Write the failing manager tests** — `tests/planning/test_plan_manager_market_open.py`

```python
"""V192-8: PlanManager drives a market plan waiting for its next open -- the open
decision (fill, through-stop and risk-cap cancels, the gap-target scratch, the
reclaim order), the premarket stop-cross debounce and the missed open. The
reclaim wait itself is V192-9. DB-backed (PlanStore on the shared swing-db)."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import market_open as mo
from swingbot.core.planning import next_open_entry
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.risk_limits import planned_loss_pct
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan


def _et(day, hh, mm=0):
    return dt.datetime(2026, 10, day, hh, mm, tzinfo=US_MARKET_TZ)


ISSUED = _et(13, 15)            # Tuesday after the open: Wednesday's open decides
OPEN = _et(14, 9, 31)
PREMARKET = _et(14, 8)
AFTER_HOURS = _et(13, 16, 30)
PRE_TAPE = _et(14, 2, 30)


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "QUIET_HOURS_START_BERLIN", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_BERLIN", 8)


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", created_at="2026-10-13",
                issued_at=ISSUED.isoformat(), entry_type="market", direction="bullish",
                trigger_price=100.0, stop_loss=98.5, tp1=103.0, tp2=105.0,
                status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=95.0)
    base.update(kw)
    return _bull(**base)


class _Log:
    """Records the trade-log hooks PlanManager._on_event calls."""

    def __init__(self):
        self.calls = []

    def record_plan_fill(self, plan_id, price):
        self.calls.append(("fill", plan_id, price))
        return "t1"

    def discard_plan_placeholder(self, plan_id):
        self.calls.append(("discard", plan_id))
        return True

    def close_plan_trade(self, plan_id, leg, status, conn=None):
        self.calls.append(("close", plan_id, leg["r"], status))

    def log_trade(self, **kw):
        self.calls.append(("log", kw["plan_id"]))
        return "t2"


def _env(plan, prices, trade_log=None):
    feed = FakePriceFeed()
    feed.set_series(plan.ticker, list(prices))
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _tr(events):
    return [e.transition for e in events]


# --- routing ------------------------------------------------------------------

def test_a_waiting_plan_never_takes_the_stop_entry_fill():
    store, mgr = _env(_bull(), [100.5])          # >= trigger: _step_pending would fill
    assert mgr.poll(_et(13, 15, 30)) == []
    assert store.get("p1").status == PlanStatus.PENDING


def test_a_pending_market_plan_without_the_marker_keeps_todays_rule():
    store, mgr = _env(_bull(waits_next_open=None), [100.5])
    assert _tr(mgr.poll(_et(13, 15, 30))) == ["filled"]
    assert store.get("p1").entry_price == 100.5


# --- the open decision ----------------------------------------------------------

@pytest.mark.parametrize("make, price", [(_bull, 99.8), (_bear, 100.2)])
def test_the_open_fills_the_plan_at_the_open(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["filled"]
    assert events[0].detail == {"entry_price": price, "live_price": price, "fill": "open"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == price
    assert plan.status_history[-1]["reason"] == "next_open_fill"


@pytest.mark.parametrize("make, price", [(_bull, 98.5), (_bull, 97.0),
                                         (_bear, 101.5), (_bear, 103.0)])
def test_an_open_at_or_through_the_stop_cancels(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["cancelled_open_through_stop"]
    assert events[0].detail == {"live_price": price, "phase": "open"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "open_through_stop"
    assert plan.status_history[-1]["phase"] == "open"


@pytest.mark.parametrize("make, price", [(_bull, 100.6), (_bear, 99.4)])
def test_an_open_past_the_stop_ceiling_cancels_risk_cap(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["cancelled_risk_cap"]
    plan = store.get("p1")
    assert events[0].detail == {
        "entry_price": price, "stop_loss": plan.stop_loss,
        "planned_loss_pct": round(planned_loss_pct(price, plan.stop_loss), 4),
        "max_planned_loss_pct": 2.0}
    assert plan.status == PlanStatus.CANCELLED
    assert plan.status_history[-1]["reason"] == "risk_cap"


@pytest.mark.parametrize("make, level, price, order", [
    (_bull, 99.5, 99.5, "buy_stop"), (_bull, 99.5, 99.0, "buy_stop"),
    (_bear, 100.5, 100.5, "sell_stop"), (_bear, 100.5, 101.0, "sell_stop"),
])
def test_an_open_at_or_beyond_x_rests_for_a_reclaim(make, level, price, order):
    store, mgr = _env(make(reclaim_level=level, reclaim_atr=2.0), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["gap_reclaim_order"]
    assert events[0].detail == {"entry_price": 100.0, "open_price": price,
                                "reclaim_level": level, "order": order, "tif": "DAY"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.PENDING and plan.entry_price is None
    assert plan.reclaim_session == "2026-10-14"
    assert (plan.reclaim_level, plan.reclaim_atr) == (level, 2.0)


@pytest.mark.parametrize("make, level, price", [(_bull, 99.5, 99.51), (_bear, 100.5, 100.49)])
def test_an_open_short_of_x_fills_at_the_open(make, level, price):
    store, mgr = _env(make(reclaim_level=level, reclaim_atr=2.0), [price])
    assert _tr(mgr.poll(OPEN)) == ["filled"]
    plan = store.get("p1")
    assert plan.entry_price == price and plan.reclaim_session is None


@pytest.mark.parametrize("make, price", [(_bull, 103.2), (_bear, 96.8)])
def test_an_open_beyond_tp1_is_a_0r_gap_target_scratch(make, price):
    log = _Log()
    store, mgr = _env(make(stop_ceiling_pct=10.0), [price], trade_log=log)
    events = mgr.poll(OPEN)
    assert _tr(events) == ["filled", "closed"]
    assert events[1].detail["reason"] == pm.GAP_TARGET_REASON == next_open_entry.GAP_TARGET_REASON
    assert events[1].detail["exit_price"] == price
    assert events[1].detail["leg"] == {"fraction": 1.0, "exit_price": price, "r": 0.0,
                                       "reason": "gap_target"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED and plan.entry_price == price
    assert [h["reason"] for h in plan.status_history] == ["next_open_fill", "gap_target"]
    # the fill moves the placeholder first; only then is the trade closed, at 0R
    assert log.calls == [("fill", "p1", price), ("close", "p1", 0.0, "closed")]


def test_the_open_fill_moves_the_placeholder_trade():
    log = _Log()
    _store, mgr = _env(_bull(), [99.8], trade_log=log)
    mgr.poll(OPEN)
    assert log.calls == [("fill", "p1", 99.8)]


# --- the premarket stop cross -----------------------------------------------------

@pytest.mark.parametrize("make, price", [(_bull, 98.4), (_bear, 101.6)])
def test_two_consecutive_extended_polls_through_the_stop_cancel(make, price):
    store, mgr = _env(make(), [price, price])
    assert mgr.poll(PREMARKET) == []
    assert store.get("p1").status == PlanStatus.PENDING
    events = mgr.poll(PREMARKET + dt.timedelta(minutes=1))
    assert _tr(events) == ["cancelled_open_through_stop"]
    assert events[0].detail == {"live_price": price, "phase": "premarket"}
    assert store.get("p1").status_history[-1]["phase"] == "premarket"
    assert mgr._premarket_hits == {}


def test_a_poll_back_inside_the_stop_resets_the_count():
    store, mgr = _env(_bull(), [98.4, 98.9, 98.4, 98.4])
    for minute in range(3):
        assert mgr.poll(PREMARKET + dt.timedelta(minutes=minute)) == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert _tr(mgr.poll(PREMARKET + dt.timedelta(minutes=3))) == ["cancelled_open_through_stop"]


def test_the_alert_days_after_hours_count_too():
    _store, mgr = _env(_bull(), [98.0, 98.0])
    assert mgr.poll(AFTER_HOURS) == []
    assert _tr(mgr.poll(AFTER_HOURS + dt.timedelta(minutes=1))) == ["cancelled_open_through_stop"]


def test_a_pre_tape_print_never_counts():
    store, mgr = _env(_bull(), [98.0, 98.0])
    assert mgr.poll(PRE_TAPE) == []
    assert mgr.poll(PRE_TAPE + dt.timedelta(minutes=1)) == []
    assert store.get("p1").status == PlanStatus.PENDING and mgr._premarket_hits == {}


def test_one_premarket_hit_then_an_open_inside_the_stop_fills():
    _store, mgr = _env(_bull(), [98.4, 99.8])
    assert mgr.poll(PREMARKET) == []
    assert _tr(mgr.poll(OPEN)) == ["filled"]
    assert mgr._premarket_hits == {}


# --- the missed open ----------------------------------------------------------------

@pytest.mark.parametrize("now", [_et(14, 16, 30), _et(15, 10)])
def test_a_missed_deciding_open_expires_and_drops_the_placeholder(now):
    log = _Log()
    store, mgr = _env(_bull(), [99.8], trade_log=log)
    events = mgr.poll(now)
    assert _tr(events) == ["cancelled_expired"]
    assert events[0].detail == {"reason": "missed_open", "bars_waited": 0,
                                "session": "2026-10-14", "cancel_resting_order": True}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "missed_open"
    assert log.calls == [("discard", "p1")]


def test_the_phase_table_covers_every_phase():
    assert set(pm._MARKET_PHASE_STEPS) == {mo.BEFORE, mo.EXTENDED, mo.OPEN, mo.MISSED,
                                          mo.WAITING, mo.AFTER_CLOSE}
    assert all(hasattr(PlanManager, name) for name in pm._MARKET_PHASE_STEPS.values())
```

- [ ] **Step 3: Run both files to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_open.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_market_open.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.planning.market_open'` in both files.

- [ ] **Step 4: Create the timing module** — `swingbot/core/planning/market_open.py`

```python
"""v192: session timing for a market plan waiting for its next open (live only).

Which NYSE session's open decides the plan, and where one poll at ``now`` sits
against it. Pure: no store, no price, no I/O. What happens at that open -- fill,
cancel, rest for a reclaim -- is gap_reclaim.decide_at_open, the function the
replay calls too.

* deciding session: the first NYSE session whose 09:30 ET open is at or after
  the plan's ``issued_at`` (the alert); a plan without one (or with an
  unreadable one) uses the session after ``created_at``;
* phases of a waiting plan: BEFORE (no live tape, or a regular session before
  the deciding one), EXTENDED (a live extended-hours tape before the deciding
  open: the premarket stop-cross debounce runs), OPEN (the deciding session's
  regular hours: the first such poll decides), MISSED (that session closed, or
  a later one is trading, with no deciding poll);
* phases of a plan resting for its reclaim (``reclaim_session`` set): WAITING
  until that session's official close, AFTER_CLOSE from it on.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.market.session import (RTH_OPEN, US_MARKET_TZ, is_nyse_regular_session,
                                          is_tape_open, now_et, nyse_calendar, session_close)

PREMARKET_STOP_CONFIRM_POLLS = 2

BEFORE = "before"
EXTENDED = "extended"
OPEN = "open"
MISSED = "missed"
WAITING = "waiting"
AFTER_CLOSE = "after_close"


def _as_et(stamp) -> dt.datetime | None:
    """An ISO timestamp in ET (naive = UTC, as plan stamps are written), or None."""
    if stamp is None:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(US_MARKET_TZ)


def _created_day(created_at) -> dt.date | None:
    """The signal day: a date-only stamp (or UTC midnight) is that date, any
    other stamp its ET date -- plan_manager._eligible_session's reading."""
    try:
        created = dt.datetime.fromisoformat(str(created_at))
    except ValueError:
        return None
    if created.tzinfo is None:
        return created.date()
    utc = created.astimezone(dt.timezone.utc)
    if utc.time() == dt.time.min:
        return utc.date()
    return created.astimezone(US_MARKET_TZ).date()


def deciding_session(plan) -> dt.date | None:
    """The NYSE session whose open decides ``plan`` (module docstring), or None."""
    calendar = nyse_calendar()
    issued = _as_et(getattr(plan, "issued_at", None))
    if issued is not None:
        day = issued.date()
        if calendar.is_session(day) and issued.time() <= RTH_OPEN:
            return day
        return calendar.next_session(day)
    created = _created_day(getattr(plan, "created_at", None))
    return calendar.next_session(created) if created is not None else None


def _iso_day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _closed(day: dt.date, et: dt.datetime) -> bool:
    """``et`` is at or after ``day``'s official close (13:00 ET on a half-day)."""
    return et.date() > day or (et.date() == day and et.time() >= session_close(day))


def market_phase(plan, now=None) -> str:
    """Where a poll at ``now`` sits for this waiting plan (module docstring)."""
    et = now_et(now)
    rest = _iso_day(getattr(plan, "reclaim_session", None))
    if rest is not None:
        return AFTER_CLOSE if _closed(rest, et) else WAITING
    day = deciding_session(plan)
    if day is None:
        return MISSED
    if is_nyse_regular_session(et):
        if et.date() == day:
            return OPEN
        return MISSED if et.date() > day else BEFORE
    if _closed(day, et):
        return MISSED
    return EXTENDED if is_tape_open(et) else BEFORE
```

- [ ] **Step 5: Wire the manager** — `swingbot/core/planning/plan_manager.py`

5a. Imports, after `from swingbot.core.planning import session_expiry` (`:39`):

```python
from swingbot.core.planning import gap_reclaim, market_open
from swingbot.core.planning.lifecycle import at_or_beyond_stop
```

(`gap_reclaim` imports `config`, `risk_limits`, `lifecycle`, `plan_types`, `stop_scope` and, lazily, `next_open_entry`; `market_open` imports only `session`. Neither imports `plan_manager`, so there is no cycle. `next_open_entry` imports this module, which is why the gap-target reason is restated below rather than imported.)

5b. Module tables, directly after `_STOPPED_REASONS` (`:158`):

```python
# v192: the close reason of a waiting market plan whose next open sat at or
# beyond TP1 -- next_open_entry.GAP_TARGET_REASON (that module imports this one,
# so the string is restated; tests pin the two equal).
GAP_TARGET_REASON = "gap_target"

#: v192: market_open phase -> the PlanManager method that steps a waiting market
#: plan in it. V192-9 points WAITING and AFTER_CLOSE at the reclaim handlers.
_MARKET_PHASE_STEPS = {
    market_open.BEFORE: "_market_hold",
    market_open.EXTENDED: "_market_extended",
    market_open.OPEN: "_market_at_open",
    market_open.MISSED: "_market_missed",
    market_open.WAITING: "_market_hold",
    market_open.AFTER_CLOSE: "_market_hold",
}

#: v192: gap_reclaim.decide_at_open verdict -> the PlanManager method acting on it.
_OPEN_DECISIONS = {
    gap_reclaim.FILL_OPEN: "_fill_at_open",
    gap_reclaim.RECLAIM_WAIT: "_rest_for_reclaim",
    gap_reclaim.RISK_CAP: "_cancel_open_risk_cap",
    gap_reclaim.OPEN_THROUGH_STOP: "_cancel_open_through_stop",
}


def _opens_beyond_tp1(plan, price: float) -> bool:
    """The open already sits at or beyond TP1 (v180 _bar_exit's gap-target case)."""
    return price >= plan.tp1 if plan.direction == "bullish" else price <= plan.tp1
```

5c. `PlanManager.__init__`, after `self.last_poll_check_errors: list[str] = []`:

```python
        # v192: plan_id -> consecutive extended-hours polls at or through the stop
        # of a market plan waiting for its next open. In memory on purpose: after
        # a restart two fresh confirming polls are needed before it cancels.
        self._premarket_hits: dict[str, int] = {}
```

5d. `_step`, first statement of the body:

```python
        if gap_reclaim.waits_for_open(plan):
            return self._step_market_open(plan, price, now)     # v192
```

5e. `_step_pending`: inside `if crossed:`, replace

```python
            risk_pct = planned_loss_pct(fill, plan.stop_loss)
            ceiling_pct = plan_stop_ceiling(plan)
            if risk_pct > ceiling_pct:
                record_transition(plan, PlanStatus.CANCELLED, reason="risk_cap",
                                  at=self._now(), extra={"entry_price": fill})
                self.store.update(plan)
                return [PlanEvent(plan.plan_id, "cancelled_risk_cap", {
                    "entry_price": fill,
                    "stop_loss": plan.stop_loss,
                    "planned_loss_pct": round(risk_pct, 4),
                    "max_planned_loss_pct": ceiling_pct,
                })]
```

with

```python
            if planned_loss_pct(fill, plan.stop_loss) > plan_stop_ceiling(plan):
                return self._cancel_risk_cap(plan, fill)
```

and add, directly after `_step_pending`:

```python
    def _cancel_risk_cap(self, plan: TradePlanV2, fill: float) -> list[PlanEvent]:
        """Cancel a plan whose fill would breach its stop ceiling: the stop-entry
        trigger and (v192) a waiting market plan's open. Same record, same event."""
        risk_pct = planned_loss_pct(fill, plan.stop_loss)
        ceiling_pct = plan_stop_ceiling(plan)
        record_transition(plan, PlanStatus.CANCELLED, reason="risk_cap",
                          at=self._now(), extra={"entry_price": fill})
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "cancelled_risk_cap", {
            "entry_price": fill,
            "stop_loss": plan.stop_loss,
            "planned_loss_pct": round(risk_pct, 4),
            "max_planned_loss_pct": ceiling_pct,
        })]

    # -- v192: a market plan waiting for its next open -------------------------

    def _step_market_open(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """One poll of a market plan waiting for its next open. market_open picks
        the phase; the open decision is gap_reclaim.decide_at_open, the function
        the replay calls. Outside EXTENDED the premarket count starts over."""
        phase = market_open.market_phase(plan, now)
        if phase != market_open.EXTENDED:
            self._premarket_hits.pop(plan.plan_id, None)
        return getattr(self, _MARKET_PHASE_STEPS[phase])(plan, price, now)

    def _market_hold(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        return []

    def _market_extended(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """A live extended-hours print before the deciding open: PREMARKET_STOP_CONFIRM_POLLS
        consecutive prints at or through the stop cancel; a print back inside resets."""
        if not at_or_beyond_stop(plan, price):
            self._premarket_hits.pop(plan.plan_id, None)
            return []
        hits = self._premarket_hits.get(plan.plan_id, 0) + 1
        if hits < market_open.PREMARKET_STOP_CONFIRM_POLLS:
            self._premarket_hits[plan.plan_id] = hits
            return []
        self._premarket_hits.pop(plan.plan_id, None)
        return self._cancel_through_stop(plan, price, "premarket")

    def _market_at_open(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        decision = gap_reclaim.decide_at_open(plan, price)
        return getattr(self, _OPEN_DECISIONS[decision])(plan, price, now)

    def _fill_at_open(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        plan.entry_price = price
        record_transition(plan, PlanStatus.ACTIVE, reason="next_open_fill", at=self._now())
        filled = PlanEvent(plan.plan_id, "filled",
                           {"entry_price": price, "live_price": price, "fill": "open"})
        if not _opens_beyond_tp1(plan, price):
            self.store.update(plan)
            return [filled]
        return [filled, self._gap_target_close(plan, price)]

    def _gap_target_close(self, plan: TradePlanV2, price: float) -> PlanEvent:
        """v180's _bar_exit convention, booked as the replay books it: an open at or
        beyond TP1 fills there and closes there, a 0R scratch. The trade-log close
        runs from _on_event AFTER the fill event moved the placeholder trade onto
        the open -- never _persist_terminal here, which would close the placeholder
        first and leave record_plan_fill nothing to move."""
        leg = {"fraction": 1.0, "exit_price": price, "r": 0.0, "reason": GAP_TARGET_REASON}
        record_transition(plan, PlanStatus.CLOSED, reason=GAP_TARGET_REASON, at=self._now())
        self.store.update(plan)
        return PlanEvent(plan.plan_id, "closed", {"reason": GAP_TARGET_REASON, "exit_price": price,
                                                  "leg": leg, "_terminal_persisted": False})

    def _rest_for_reclaim(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """The veto armed: the open sat at or beyond X. The plan rests for this one
        session as a DAY stop order at E; V192-9 fills or cancels it."""
        plan.reclaim_session = session_date(now)
        self.store.update(plan)
        order = "buy_stop" if plan.direction == "bullish" else "sell_stop"
        return [PlanEvent(plan.plan_id, "gap_reclaim_order", {
            "entry_price": plan.trigger_price, "open_price": price,
            "reclaim_level": plan.reclaim_level, "order": order, "tif": "DAY"})]

    def _cancel_open_risk_cap(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        return self._cancel_risk_cap(plan, price)

    def _cancel_open_through_stop(self, plan: TradePlanV2, price: float,
                                  now=None) -> list[PlanEvent]:
        return self._cancel_through_stop(plan, price, "open")

    def _cancel_through_stop(self, plan: TradePlanV2, price: float, phase: str) -> list[PlanEvent]:
        record_transition(plan, PlanStatus.CANCELLED, reason=gap_reclaim.OPEN_THROUGH_STOP,
                          at=self._now(), extra={"phase": phase})
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "cancelled_open_through_stop",
                          {"live_price": price, "phase": phase})]

    def _market_missed(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """No poll saw the deciding open (the bot was down or silent through it):
        cancel, never fill at a stale price."""
        session = market_open.deciding_session(plan)
        record_transition(plan, PlanStatus.CANCELLED, reason="missed_open", at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "cancelled_expired", {
            "reason": "missed_open", "bars_waited": 0,
            "session": session.isoformat() if session else None,
            "cancel_resting_order": True})]
```

`session_date(now)` is already imported (`:22`) and is the ET date the OPEN phase was decided on, which is the deciding session.

- [ ] **Step 6: Run the new tests, the neighbouring manager suites, and the gate**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_open.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_market_open.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_poll_window.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere (the pending file pins the extracted `_cancel_risk_cap` record and event unchanged); the gate passes (`_step` gains one branch and `_step_pending` loses two; every new method is under cc 5; `market_phase` is cc 8).

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add swingbot/core/planning/market_open.py swingbot/core/planning/plan_manager.py tests/planning/test_market_open.py tests/planning/test_plan_manager_market_open.py
git commit -m "feat(v192): live open decision for waiting market plans -- fill, through-stop and risk-cap cancels, gap-target scratch, reclaim order, premarket debounce, missed open"
```

### Task V192-9: Live reclaim wait: fill at E, end-of-session cancel, reload safety
**Model:** opus — the resting-order half of the live state machine; a wrong phase re-decides the open, fills at a stale price, or leaves a stale DAY order alive past the close across a restart.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — `_MARKET_PHASE_STEPS` (V192-8) and two new methods after `_market_missed`
- Create: `tests/planning/test_plan_manager_gap_reclaim.py`

**Interfaces:**
- Consumes: `PlanManager._step_market_open`, `_MARKET_PHASE_STEPS`, `_rest_for_reclaim` (sets `reclaim_session`), the V192-8 test helpers `_bull`, `_bear`, `_env`, `_et`, `_tr`, `_Log`, `_flags`, `OPEN` (`tests/planning/test_plan_manager_market_open.py`); `gap_reclaim.reclaim_touched(plan, high, low)`, `gap_reclaim.GAP_NO_RECLAIM` (V192-4); `market_open.WAITING`, `AFTER_CLOSE` (V192-8); `session.session_close`, `US_MARKET_TZ`, `is_regular_session` (already imported in `plan_manager.py`).
- Produces: `PlanManager._market_waiting(self, plan, price, now=None)` and `PlanManager._market_after_close(self, plan, price, now=None)`; events `filled {"entry_price": E, "live_price", "fill": "reclaim"}` (record reason `gap_reclaim_fill`) and `cancelled_gap_no_reclaim {"entry_price": E, "session": ISO date}` (record reason `gap_no_reclaim`, `at` = that session's official close in ET).

Live fills at `E` itself (the DAY stop order's price) on the first regular-session poll at or one tick through it (bull `price ≥ E + tick`, bear `price ≤ E − tick`): `reclaim_touched(plan, price, price)` — the live price stands in for both bar High and bar Low, the module-docstring convention of `plan_manager.py`. A print through the stop while resting cancels nothing: a buy-stop above the market stays resting, and the replay's ambiguous-bar rule (fill, then the stop) is what a later reclaim produces live as well. No risk-cap check at `E`: the scan refused the plan unless its loss at `E` was within the ceiling (`analyze.attach_plan_v2`, `:520-533`), and the fill price is that same `E`.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_plan_manager_gap_reclaim.py`

```python
"""V192-9: a market plan resting for its reclaim -- fill at E one tick through it,
cancel at the session's close, survive a restart and a knob flip. DB-backed."""
import pytest

from swingbot import config
from swingbot.core.planning import market_open as mo
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_market_open import (OPEN, _Log, _bear, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)


def _resting(make=_bull, **kw):
    """A plan whose deciding open sat at or beyond X: it now rests for the session."""
    level, open_price = (99.5, 99.0) if make is _bull else (100.5, 101.0)
    open_price = kw.pop("open_price", open_price)
    base = dict(reclaim_level=level, reclaim_atr=2.0)
    base.update(kw)
    store, mgr = _env(make(**base), [open_price])
    assert _tr(mgr.poll(OPEN)) == ["gap_reclaim_order"]
    return store, mgr


def _step(store, mgr, price, now):
    return mgr._step(store.get("p1"), price, now)


def test_the_phase_table_points_at_the_reclaim_handlers():
    assert pm._MARKET_PHASE_STEPS[mo.WAITING] == "_market_waiting"
    assert pm._MARKET_PHASE_STEPS[mo.AFTER_CLOSE] == "_market_after_close"


@pytest.mark.parametrize("make, touch, through", [(_bull, 100.0, 100.01), (_bear, 100.0, 99.99)])
def test_the_reclaim_fills_at_e_only_one_tick_through_it(make, touch, through):
    store, mgr = _resting(make)
    assert _step(store, mgr, touch, _et(14, 10)) == []        # a bare touch of E is not a fill
    assert store.get("p1").status == PlanStatus.PENDING
    events = _step(store, mgr, through, _et(14, 10, 1))
    assert _tr(events) == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": through, "fill": "reclaim"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == 100.0
    assert plan.status_history[-1]["reason"] == "gap_reclaim_fill"


def test_a_sub_dollar_reclaim_uses_the_small_tick():
    store, mgr = _resting(trigger_price=0.85, stop_loss=0.835, tp1=0.88, tp2=0.9,
                          reclaim_level=0.84, open_price=0.84)
    assert _step(store, mgr, 0.85005, _et(14, 10)) == []
    assert _tr(_step(store, mgr, 0.8501, _et(14, 10, 1))) == ["filled"]
    assert store.get("p1").entry_price == 0.85


def test_the_reclaim_fill_moves_the_placeholder_to_e():
    log = _Log()
    plan = _bull(reclaim_level=99.5, reclaim_atr=2.0)
    feed = FakePriceFeed()
    feed.set_series("AAPL", [99.0, 100.01])
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, feed.get_price, trade_log=log)
    mgr.poll(OPEN)
    mgr.poll(_et(14, 10))
    assert ("fill", "p1", 100.0) in log.calls
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_print_through_the_stop_while_resting_cancels_nothing():
    store, mgr = _resting()
    assert _step(store, mgr, 98.0, _et(14, 11)) == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert _tr(_step(store, mgr, 100.01, _et(14, 14))) == ["filled"]


def test_the_open_decision_is_never_taken_twice():
    store, mgr = _resting()
    assert _step(store, mgr, 99.0, _et(14, 11)) == []           # still at or beyond X
    assert store.get("p1").reclaim_session == "2026-10-14"


@pytest.mark.parametrize("now", [_et(14, 16), _et(14, 17, 30), _et(15, 9, 45)])
def test_no_reclaim_by_the_close_cancels(now):
    store, mgr = _resting()
    events = _step(store, mgr, 99.2, now)
    assert _tr(events) == ["cancelled_gap_no_reclaim"]
    assert events[0].detail == {"entry_price": 100.0, "session": "2026-10-14"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "gap_no_reclaim"
    assert plan.status_history[-1]["at"] == "2026-10-14T16:00:00-04:00"


def test_a_bearish_plan_cancels_the_same_way():
    store, mgr = _resting(_bear)
    assert _tr(_step(store, mgr, 100.8, _et(14, 16, 5))) == ["cancelled_gap_no_reclaim"]


def test_a_restart_keeps_the_rest_and_still_cancels_at_the_close():
    store, _mgr = _resting()
    before = store.get("p1")
    fresh = PlanManager(PlanStore(), lambda ticker: 99.0)        # a restarted bot
    plan = fresh.store.get("p1")
    assert (plan.reclaim_session, plan.reclaim_level, plan.reclaim_atr) == (
        before.reclaim_session, before.reclaim_level, before.reclaim_atr) == ("2026-10-14", 99.5, 2.0)
    assert fresh._step(plan, 99.0, _et(14, 12)) == []
    assert _tr(fresh._step(fresh.store.get("p1"), 99.0, _et(14, 16, 1))) == [
        "cancelled_gap_no_reclaim"]


def test_a_knob_flip_while_resting_changes_nothing(monkeypatch):
    store, mgr = _resting()
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    assert _tr(_step(store, mgr, 100.01, _et(14, 10))) == ["filled"]
    assert store.get("p1").entry_price == 100.0
```

- [ ] **Step 2: Run it to see it fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gap_reclaim.py
```

Expected: FAIL — `_MARKET_PHASE_STEPS[mo.WAITING] == "_market_hold"`, and every reclaim step returns `[]`.

- [ ] **Step 3: Implement** — `swingbot/core/planning/plan_manager.py`

In `_MARKET_PHASE_STEPS` replace the two `"_market_hold"` values of `WAITING` and `AFTER_CLOSE`:

```python
    market_open.WAITING: "_market_waiting",
    market_open.AFTER_CLOSE: "_market_after_close",
```

and drop the comment line "V192-9 points WAITING and AFTER_CLOSE at the reclaim handlers.". Add after `_market_missed`:

```python
    def _market_waiting(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """Resting as a DAY stop order at E: fill at E on the first regular-session
        print one tick through it (the live price stands in for High and Low). A
        print through the stop cancels nothing -- the stop order rests above."""
        if not is_regular_session(now) or not gap_reclaim.reclaim_touched(plan, price, price):
            return []
        entry = plan.trigger_price
        plan.entry_price = entry
        record_transition(plan, PlanStatus.ACTIVE, reason="gap_reclaim_fill", at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "filled",
                          {"entry_price": entry, "live_price": price, "fill": "reclaim"})]

    def _market_after_close(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        """The resting session closed without a reclaim: the DAY order is gone.
        Recorded at that session's official close, whenever the poll lands."""
        rest = date.fromisoformat(plan.reclaim_session)
        closed_at = datetime.combine(rest, session_close(rest), tzinfo=US_MARKET_TZ).isoformat()
        record_transition(plan, PlanStatus.CANCELLED, reason=gap_reclaim.GAP_NO_RECLAIM,
                          at=closed_at)
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "cancelled_gap_no_reclaim",
                          {"entry_price": plan.trigger_price, "session": plan.reclaim_session})]
```

`market_phase` returns `AFTER_CLOSE` only for a readable `reclaim_session`, so `date.fromisoformat` cannot fail here.

- [ ] **Step 4: Run the tests and the gate**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gap_reclaim.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_market_open.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`; the gate passes (both new methods cc 3).

- [ ] **Step 5: Commit (in the worktree)**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_gap_reclaim.py
git commit -m "feat(v192): live reclaim wait -- fill at E one tick through, cancel at the session close, restart-safe"
```

# Phase 6 — Feed, followers and the alert

### Task V192-10: Feed instruction copy and `Kind.RECLAIM_ORDER`
**Model:** opus — broker-order copy the partner places from; a wrong verb or a missing builder posts a stale or contradictory order, and `_cancel_why` KeyErrors on an unknown cancel.

**Files:**
- Modify: `swingbot/core/presentation/kinds.py` (the `Kind` enum, ENTRY block, `:118-120`)
- Modify: `swingbot/core/presentation/instructions.py` — `_EXIT_WORDS` (`:32`), `_CANCEL_LEADS` / `_cancel_why` / `_cancelled` (`:543-570`), `_BUILDERS` (`:572`); new helpers beside them
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` — `PLAN_EVENT_KINDS` (`:303`)
- Modify: `swingbot/core/scanning/execution_embeds.py` — `_EVENT_KINDS` (`:28`)
- Modify: `scripts/dev/render_feed_samples.py` — `SAMPLES` (`:41`)
- Create: `tests/presentation/test_gap_reclaim_instructions.py`

**Interfaces:**
- Consumes: the event names and detail keys of V192-8/V192-9 (index § Contracts); `TradePlanV2.waits_next_open`, `reclaim_level` (V192-3); `tests/presentation/test_feed_guards.py` helpers `_order_glyph_hits`, `_allowed`, `_FORBIDDEN`, `_VERBS`.
- Produces: `Kind.RECLAIM_ORDER = KindSpec(Family.ENTRY, "STOP ORDER AT ENTRY")`; `instructions._BUILDERS` entries `gap_reclaim_order` (`_reclaim_order`), `cancelled_open_through_stop` and `cancelled_gap_no_reclaim` (`_cancelled`); `_CANCEL_LEADS` rows `cancelled_open_through_stop: "invalid"`, `cancelled_gap_no_reclaim: "expiry"`; `_EXIT_WORDS["gap_target"] = "opened past TP1"`; `PLAN_EVENT_KINDS` and `execution_embeds._EVENT_KINDS` rows `cancelled_open_through_stop: Kind.INVALIDATED`, `cancelled_gap_no_reclaim: Kind.EXPIRED`, `gap_reclaim_order: Kind.RECLAIM_ORDER` (the `follow_notify` kinds of index § Contracts, so the two channels agree).

Copy rules (the v170 feed guards, applied to the new messages in this task's test): every order glyph leads its direction's broker verb; every cancel says `CANCEL` and names the order it withdraws — the DAY stop at `E` for `gap_no_reclaim`, `BUY AT MARKET ON OPEN` / `SELL SHORT AT MARKET ON OPEN` for any other cancel of a plan built to wait for the open (`waits_next_open is True`, which survives the cancel; status alone does not); no glyph literal in `instructions.py`; no verb of the other direction. A stop-entry plan's cancel headline is unchanged.

- [ ] **Step 1: Write the failing tests** — `tests/presentation/test_gap_reclaim_instructions.py`

```python
"""V192-10: execution-feed copy for a market plan waiting for its next open --
the DAY stop-order instruction, the new cancels, the missed open, the gap-target
close -- under the v170 feed guards, plus the registry kind and both kind maps."""
import importlib.util
from pathlib import Path

import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import execution_embeds as ee
from swingbot.core.scanning import lifecycle_embeds as le
from tests.planning.test_plan_engine_model import _plan
from tests.presentation.test_feed_guards import _FORBIDDEN, _VERBS, _allowed, _order_glyph_hits

S = tokens.FEED_SYMBOLS
LEVELS = {
    "bullish": dict(trigger_price=100.0, stop_loss=98.5, tp1=103.0, tp2=105.0, reclaim_level=99.5),
    "bearish": dict(trigger_price=100.0, stop_loss=101.5, tp1=97.0, tp2=95.0, reclaim_level=100.5),
}
NEW = ("gap_reclaim_order", "cancelled_open_through_stop", "cancelled_gap_no_reclaim")


def _waiting(direction="bullish", **kw):
    base = dict(source="confluence", strategy="S/R Confluence", entry_type="market",
                direction=direction, waits_next_open=True, reclaim_atr=2.0,
                status="PENDING", **LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _order_event(direction):
    lv = LEVELS[direction]
    return PlanEvent("p1", "gap_reclaim_order", {
        "entry_price": 100.0, "open_price": 99.0 if direction == "bullish" else 101.0,
        "reclaim_level": lv["reclaim_level"], "tif": "DAY",
        "order": "buy_stop" if direction == "bullish" else "sell_stop"})


def _messages(direction):
    lv = LEVELS[direction]
    cancelled = _waiting(direction, status="CANCELLED")
    events = [
        (_waiting(direction), _order_event(direction)),
        (cancelled, PlanEvent("p1", "cancelled_open_through_stop",
                              {"live_price": lv["stop_loss"], "phase": "open"})),
        (cancelled, PlanEvent("p1", "cancelled_open_through_stop",
                              {"live_price": lv["stop_loss"], "phase": "premarket"})),
        (cancelled, PlanEvent("p1", "cancelled_gap_no_reclaim",
                              {"entry_price": 100.0, "session": "2026-10-14"})),
        (cancelled, PlanEvent("p1", "cancelled_expired",
                              {"reason": "missed_open", "bars_waited": 0, "session": "2026-10-14",
                               "cancel_resting_order": True})),
    ]
    return [ins.instruction_for(plan, event, money=ins.money_from(54.35, "$"))
            for plan, event in events]


# --- the registry and the kind maps ------------------------------------------------

def test_the_reclaim_order_kind():
    assert Kind.RECLAIM_ORDER.family is Family.ENTRY
    assert Kind.RECLAIM_ORDER.label == "STOP ORDER AT ENTRY"


@pytest.mark.parametrize("table", [le.PLAN_EVENT_KINDS, ee._EVENT_KINDS])
def test_both_kind_maps_carry_the_new_transitions(table):
    assert table["cancelled_open_through_stop"] is Kind.INVALIDATED
    assert table["cancelled_gap_no_reclaim"] is Kind.EXPIRED
    assert table["gap_reclaim_order"] is Kind.RECLAIM_ORDER


def test_every_new_transition_has_a_builder():
    assert set(NEW) <= set(ins._BUILDERS)


# --- the v170 guards on the new messages --------------------------------------------

@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_every_order_glyph_leads_its_broker_verb(direction):
    allowed = _allowed(direction)
    for instruction in _messages(direction):
        for key, after in _order_glyph_hits(instruction):
            assert after.startswith(allowed[key]), (key, after, instruction)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_no_message_carries_the_other_directions_verbs(direction):
    for instruction in _messages(direction):
        text = "\n".join((instruction.headline, *instruction.lines))
        assert [v for v in _FORBIDDEN[direction] if v in text] == [], instruction


def test_instructions_py_still_writes_no_glyph_literal():
    source = Path(ins.__file__).read_text(encoding="utf-8")
    assert [key for key, glyph in S.items() if glyph in source] == []


# --- the stop-order instruction --------------------------------------------------------

@pytest.mark.parametrize("direction, stop_verb, refrain, side", [
    ("bullish", "BUY STOP", "buy", "below"), ("bearish", "SELL STOP", "short", "above")])
def test_the_reclaim_order_instruction(direction, stop_verb, refrain, side):
    instruction = _messages(direction)[0]
    assert instruction.verb == ins.PLACE
    assert instruction.headline == (f"{S['entry']} {stop_verb} 100.00 DAY · "
                                    f"don't {refrain} at the open")
    level = LEVELS[direction]["reclaim_level"]
    assert instruction.lines[0].startswith(
        f"Opened at {101.0 if direction == 'bearish' else 99.0:.2f}, at or {side} {level:.2f}")
    assert "fills only if price trades through 100.00 today" in instruction.lines[1]
    keys = {key for key, _after in _order_glyph_hits(instruction)}
    assert {"entry", "stop", "tp1"} <= keys


# --- cancels ---------------------------------------------------------------------------

@pytest.mark.parametrize("direction, market", [("bullish", "BUY AT MARKET"),
                                               ("bearish", "SELL SHORT AT MARKET")])
def test_cancels_name_the_order_they_withdraw(direction, market):
    _order, through, premarket, no_reclaim, missed = _messages(direction)
    entry_stop = _VERBS[direction]["entry"][0]
    assert through.headline == f"{S['invalid']} CANCEL {market} ON OPEN"
    assert premarket.headline == through.headline
    assert no_reclaim.headline == f"{S['expiry']} CANCEL {entry_stop} 100.00 (DAY)"
    assert missed.headline == f"{S['expiry']} CANCEL {market} ON OPEN"
    assert all(i.verb == ins.CANCEL for i in (through, premarket, no_reclaim, missed))


def test_the_cancel_reasons_read_the_event():
    _order, through, premarket, no_reclaim, missed = _messages("bullish")
    assert through.lines == ("opened at 98.50, at or through the stop 98.50; never filled",)
    assert premarket.lines == ("traded at 98.50 before the open, at or through the stop 98.50 "
                               "on two checks; never filled",)
    assert no_reclaim.lines == ("opened toward the stop and never traded back through 100.00 "
                                "on 2026-10-14; never filled",)
    assert missed.lines == ("the bot saw no price at the 2026-10-14 open; never filled",)


def test_a_stop_entry_cancel_is_unchanged():
    plan = _plan(entry_type="stop_entry", trigger_price=102.5, stop_loss=98.4, tp1=106.0,
                 created_at="2026-09-10", status="CANCELLED")
    instruction = ins.instruction_for(plan, PlanEvent("p1", "cancelled_invalidated", {}))
    assert instruction.headline == f"{S['invalid']} CANCEL BUY STOP 102.50"


def test_the_gap_target_close_names_its_reason():
    plan = _waiting(status="CLOSED", entry_price=103.2, stop_ceiling_pct=10.0)
    instruction = ins.instruction_for(plan, PlanEvent("p1", "closed", {
        "reason": "gap_target", "exit_price": 103.2, "session": "regular"}))
    assert instruction.verb == ins.EXITED
    assert instruction.headline.endswith("EXITED @ 103.20 · opened past TP1")


# --- the rendered embeds -------------------------------------------------------------

def test_the_reclaim_order_renders_as_its_kind(monkeypatch):
    monkeypatch.setattr(ee, "_linked_trade", lambda plan_id: None)
    monkeypatch.setattr(ee, "_sizing_snapshot", lambda entry, plan: {"shares": 54.35})
    embed = ee.build_instruction_embed(_waiting(), _order_event("bullish"))
    assert "STOP ORDER AT ENTRY" in embed.title


def test_render_feed_samples_renders_every_sample(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "render_feed_samples.py"
    spec = importlib.util.spec_from_file_location("render_feed_samples", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    # _render patches these module attributes; register them so monkeypatch restores them
    monkeypatch.setattr(ee, "_sizing_snapshot", ee._sizing_snapshot)
    monkeypatch.setattr(ee, "_linked_trade", ee._linked_trade)
    names = [name for name, *_rest in script.SAMPLES]
    for wanted in ("reclaim order long", "reclaim order short", "cancel open through stop",
                   "cancel premarket through stop", "cancel no reclaim", "cancel missed open",
                   "closed gap target"):
        assert wanted in names
    for name, plan_kw, event, logged, realized in script.SAMPLES:
        assert script._render(plan_kw, event, logged, realized), name
```

- [ ] **Step 2: Run it to see it fail**

```bash
python scripts/dev/testrun.py file tests/presentation/test_gap_reclaim_instructions.py
```

Expected: FAIL — `AttributeError: RECLAIM_ORDER`, and `instruction_for` raises `ValueError: no execution-feed instruction for 'gap_reclaim_order'`.

- [ ] **Step 3: Add the kind** — `swingbot/core/presentation/kinds.py`, in the `# ENTRY` block after `FILLED`:

```python
    RECLAIM_ORDER = KindSpec(Family.ENTRY, "STOP ORDER AT ENTRY")   # v192: DAY stop at E
```

- [ ] **Step 4: The instruction copy** — `swingbot/core/presentation/instructions.py`

4a. `_EXIT_WORDS`: add the row

```python
    "gap_target": "opened past TP1",
```

4b. Replace `_CANCEL_LEADS`, `_cancel_why` and `_cancelled` with:

```python
#: cancel transition -> its headline's FEED_SYMBOLS key ('' = no glyph, v170 Decision 4).
_CANCEL_LEADS = {"cancelled_expired": "expiry", "cancelled_invalidated": "invalid",
                 "cancelled_risk_cap": "",
                 "cancelled_open_through_stop": "invalid",     # v192
                 "cancelled_gap_no_reclaim": "expiry"}         # v192


def _through_stop_why(plan, detail: dict) -> str:
    price, stop = _price(detail["live_price"]), _price(plan.stop_loss)
    if detail.get("phase") == "premarket":
        return (f"traded at {price} before the open, at or through the stop {stop} "
                "on two checks; never filled")
    return f"opened at {price}, at or through the stop {stop}; never filled"


def _no_reclaim_why(plan, detail: dict) -> str:
    return (f"opened toward the stop and never traded back through "
            f"{_price(detail['entry_price'])} on {detail['session']}; never filled")


def _missed_open_why(plan, detail: dict) -> str:
    return f"the bot saw no price at the {detail.get('session') or 'deciding'} open; never filled"


#: v192: the cancels of a market plan waiting for its next open, by transition.
_WAITING_WHY = {"cancelled_open_through_stop": _through_stop_why,
                "cancelled_gap_no_reclaim": _no_reclaim_why}


def _cancel_why(plan, transition: str, detail: dict) -> str:
    if detail.get("reason_message"):
        return detail["reason_message"]             # v144: an outlook plan states its reason
    special = _WAITING_WHY.get(transition)
    if special is None and detail.get("reason") == "missed_open":
        special = _missed_open_why
    if special is not None:
        return special(plan, detail)
    if short_notice.is_compression(plan) and transition != "cancelled_invalidated":
        return short_notice.compression_cancel_why(plan, transition, detail)
    if transition == "cancelled_expired":
        return f"not triggered within {plan.expiry_bars} sessions"
    if transition == "cancelled_invalidated":
        return f"price reached the stop {_price(plan.stop_loss)} before triggering"
    return (f"triggered at {_price(detail['entry_price'])} but risked "
            f"{detail['planned_loss_pct']:.1f}% against stop "
            f"{_price(detail['stop_loss'])} -- above the "
            f"{detail['max_planned_loss_pct']:.1f}% cap; never filled")


def _cancel_order(plan, side: dict, transition: str) -> str:
    """The order a cancel withdraws: v192's DAY stop at E after a gap with no
    reclaim, the market-on-open order of any other plan built to wait for the
    open (the marker survives the cancel), else the stop entry as before."""
    if transition == "cancelled_gap_no_reclaim":
        return f"{side['entry_stop']} {_price(plan.trigger_price)} (DAY)"
    if getattr(plan, "waits_next_open", None) is True:
        return f"{side['entry_market']} ON OPEN"
    return f"{side['entry_stop']} {_price(plan.trigger_price)}"


def _cancelled(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    key = _CANCEL_LEADS[event.transition]
    lead = f"{_S[key]} " if key else ""
    return Instruction(
        verb=CANCEL,
        headline=f"{lead}CANCEL {_cancel_order(plan, side, event.transition)}",
        lines=(_cancel_why(plan, event.transition, event.detail),), tone="inert", **common)


#: v192: what a reader must not do at the open, and which side of X the open sat.
_REFRAIN = {"bullish": "buy", "bearish": "short"}
_BEYOND = {"bullish": "below", "bearish": "above"}


def _reclaim_order(plan, event, side: dict, common: dict, money: Money | None) -> Instruction:
    """v192: the open sat at or beyond X toward the stop -- no entry at the open;
    a DAY stop order at E for this one session instead."""
    detail = event.detail
    entry = _price(detail["entry_price"])
    return Instruction(
        verb=PLACE,
        headline=(f"{_S['entry']} {side['entry_stop']} {entry} DAY · "
                  f"don't {_REFRAIN[plan.direction]} at the open"),
        lines=(f"Opened at {_price(detail['open_price'])}, at or {_BEYOND[plan.direction]} "
               f"{_price(detail['reclaim_level'])} toward the stop {_price(plan.stop_loss)}",
               "Cancel any market-on-open order still working; this order fills only if "
               f"price trades through {entry} today and is cancelled at the close",
               f"After a fill: {_S['stop']} {side['stop']} {_price(plan.stop_loss)} · "
               f"{_S['tp1']} {side['limit']} {_price(plan.tp1)}"),
        tone="neutral", **common)
```

4c. `_BUILDERS`: add the three rows

```python
    "cancelled_open_through_stop": _cancelled,
    "cancelled_gap_no_reclaim": _cancelled,
    "gap_reclaim_order": _reclaim_order,
```

- [ ] **Step 5: The kind maps**

`swingbot/core/scanning/lifecycle_embeds.py` `PLAN_EVENT_KINDS` and `swingbot/core/scanning/execution_embeds.py` `_EVENT_KINDS` each gain:

```python
    "cancelled_open_through_stop": Kind.INVALIDATED,     # v192
    "cancelled_gap_no_reclaim": Kind.EXPIRED,            # v192
    "gap_reclaim_order": Kind.RECLAIM_ORDER,             # v192
```

`_result_detail` (execution) and `_ENDED_OUTCOME` (lifecycle) already give `EXPIRED` / `INVALIDATED` their grey mark; nothing else changes.

- [ ] **Step 6: The feed samples** — `scripts/dev/render_feed_samples.py`

After `DUE = ...` add:

```python
#: v192: a market plan built to wait for its next open, with the veto armed.
WAITING = dict(entry_type="market", waits_next_open=True, reclaim_level=181.10, reclaim_atr=2.6)
WAITING_SHORT = {**SHORT, **WAITING, "reclaim_level": 51.30}
```

and append to `SAMPLES`:

```python
    ("reclaim order long", WAITING,
     ("gap_reclaim_order", {"entry_price": 182.40, "open_price": 180.90, "reclaim_level": 181.10,
                            "order": "buy_stop", "tif": "DAY"}), None, None),
    ("reclaim order short", WAITING_SHORT,
     ("gap_reclaim_order", {"entry_price": 50.0, "open_price": 51.60, "reclaim_level": 51.30,
                            "order": "sell_stop", "tif": "DAY"}), None, None),
    ("cancel open through stop", {**WAITING, "status": "CANCELLED"},
     ("cancelled_open_through_stop", {"live_price": 177.20, "phase": "open"}), None, None),
    ("cancel premarket through stop", {**WAITING, "status": "CANCELLED"},
     ("cancelled_open_through_stop", {"live_price": 177.60, "phase": "premarket"}), None, None),
    ("cancel no reclaim", {**WAITING, "status": "CANCELLED"},
     ("cancelled_gap_no_reclaim", {"entry_price": 182.40, "session": "2026-10-15"}), None, None),
    ("cancel missed open", {**WAITING, "status": "CANCELLED"},
     ("cancelled_expired", {"reason": "missed_open", "bars_waited": 0, "session": "2026-10-15",
                            "cancel_resting_order": True}), None, None),
    ("closed gap target", {**WAITING, "status": "CLOSED", "entry_price": 189.50},
     _closed("gap_target", 189.50, 177.80), None, 0.0),
```

On a tree before v192 these render as `RENDER ERROR` (no `waits_next_open` field), which the script already records per sample.

- [ ] **Step 7: Run the tests, the feed guards and the gate**

```bash
python scripts/dev/testrun.py file tests/presentation/test_gap_reclaim_instructions.py
python scripts/dev/testrun.py file tests/presentation/test_feed_guards.py
python scripts/dev/testrun.py file tests/presentation/test_instructions.py
python scripts/dev/testrun.py file tests/presentation/test_kinds.py
python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`; the gate passes (`_cancel_why` rises to cc 9).

- [ ] **Step 8: Commit (in the worktree)**

```bash
git add swingbot/core/presentation/kinds.py swingbot/core/presentation/instructions.py swingbot/core/scanning/lifecycle_embeds.py swingbot/core/scanning/execution_embeds.py scripts/dev/render_feed_samples.py tests/presentation/test_gap_reclaim_instructions.py
git commit -m "feat(v192): feed copy for the DAY stop at entry, the open-time cancels and the gap-target close; Kind.RECLAIM_ORDER"
```

