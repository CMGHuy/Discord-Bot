# Live exit parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/implemented/2026-08-28-v64-live-exit-parity-design.md`

**Version:** ui 1.9.2 · bot 1.4.5
**Bump:** bot minor (1.4.x → 1.5.0) · ui none
**Edge:** none (integrity)

**Goal:** Make `plan_manager.py`'s live exit path implement the same
break-even rule `plan_engine.py`'s backtest simulator measures, so
`architecture.md`'s "live behavior equals backtested behavior by
construction" is true again.

**Architecture:** A new stdlib-only `core/market/session.py` answers "is the
US market in regular hours" and "what ET session date is it". `PlanManager`
gates its whole poll tick on the first, and stamps two new `TradePlanV2`
session-date fields with the second so a break-even stop and a runner floor
govern only from the session *after* they arm. A per-plan in-memory
last-seen price lets a stop breach distinguish "the tape crossed the level
while we watched" (fill at the level) from "we are looking for the first
time since a gap" (fill at the observed price).

**Tech Stack:** Python 3.11+, stdlib `zoneinfo`/`datetime`, pytest.

## Global Constraints

- **No threshold, fraction or frozen constant changes.**
  `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `RUNNER_FLOOR_FRACTION = 2/3`,
  `tp1_fraction = 0.50`, `MIN_RISK_REWARD_RATIO = 1.5`,
  `MAX_RISK_REWARD_RATIO = 2.5` are all untouched. This plan changes *when
  the existing rule may act*, never *what it is*.
- **No backtest, grid or validation run.** This plan makes no expectancy
  claim, so there is nothing here for a pre-registration to test. Do not
  run `run_backtest_range.py` as part of it.
- **`swingbot/core/` stays Discord-free.** `session.py` imports stdlib only.
- **Every new function takes an injectable `now`/clock argument.** No test
  in this plan may patch `datetime` globally.
- **`_check_bar_active` / `_check_bar_partial` get no behaviour changes.**
  They are unreachable from production code (`git grep check_bar` returns
  only `plan_manager.py` and two test files). Task P9 documents that; no
  other task touches them.
- Per-task verification is the narrow run:
  `python scripts/dev/testrun.py file tests/<the one file this task touched>.py`.
  Never `... full` inside a task — Task P10 is the single full run.

---

# Phase 1 — Session primitives and plan fields

## Parallelisation

- **Group 1 (parallel):** P1, P2 — different files
  (`core/market/session.py` + `core/market/opex.py` vs
  `core/planning/plan_engine.py`), and neither consumes a symbol the other
  introduces.
- **Sequential after Group 1:** P3 through P8, in order. All of them edit
  `plan_manager.py`'s `_step_active`/`_step_partial`/`poll` and each
  consumes what the previous wrote. Concurrent sessions share this working
  tree — two agents on `plan_manager.py` silently overwrite each other.
- **Sequential last:** P9 (documents the finished behaviour), then P10.

---

### Task P1: US market session module

**Files:**
- Create: `swingbot/core/market/session.py`
- Modify: `swingbot/core/market/opex.py:33-35`
- Test: `tests/market/test_session.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `US_MARKET_TZ: ZoneInfo`, `RTH_OPEN: datetime.time`,
  `RTH_CLOSE: datetime.time`, `now_et(now: datetime | None = None) -> datetime`,
  `is_regular_session(now: datetime | None = None) -> bool`,
  `session_date(now: datetime | None = None) -> str`. Tasks P3–P8 import
  `is_regular_session` and `session_date`.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_session.py`:

```python
import datetime as dt

import pytest

from swingbot.core.market.session import (US_MARKET_TZ, is_regular_session,
                                          now_et, session_date)


def _et(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=US_MARKET_TZ)


@pytest.mark.parametrize("moment,expected", [
    (_et(2026, 8, 27, 9, 29), False),   # one minute before the open
    (_et(2026, 8, 27, 9, 30), True),    # the open itself is in session
    (_et(2026, 8, 27, 12, 0), True),
    (_et(2026, 8, 27, 15, 59), True),
    (_et(2026, 8, 27, 16, 0), False),   # the close itself is OUT
    (_et(2026, 8, 27, 4, 15), False),   # premarket print
    (_et(2026, 8, 27, 19, 30), False),  # after-hours print
    (_et(2026, 8, 29, 12, 0), False),   # Saturday
    (_et(2026, 8, 30, 12, 0), False),   # Sunday
])
def test_regular_session_boundaries(moment, expected):
    assert is_regular_session(moment) is expected


def test_naive_and_utc_inputs_are_converted_to_et():
    # 20:00 UTC on a summer weekday is 16:00 ET -- the close, so OUT.
    utc = dt.datetime(2026, 8, 27, 20, 0, tzinfo=dt.timezone.utc)
    assert is_regular_session(utc) is False
    # 18:00 UTC the same day is 14:00 ET -- mid-session.
    assert is_regular_session(dt.datetime(2026, 8, 27, 18, 0,
                                          tzinfo=dt.timezone.utc)) is True


def test_session_date_is_the_et_calendar_day_not_the_utc_one():
    # 22:00 ET on the 27th is 02:00 UTC on the 28th. The ET session date
    # is what stamps a plan, so this must still read 2026-08-27.
    assert session_date(_et(2026, 8, 27, 22, 0)) == "2026-08-27"
    utc_next_day = dt.datetime(2026, 8, 28, 2, 0, tzinfo=dt.timezone.utc)
    assert session_date(utc_next_day) == "2026-08-27"


def test_now_et_defaults_to_the_current_moment_in_et():
    assert now_et().tzinfo is US_MARKET_TZ
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/market/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.session'`

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/market/session.py`:

```python
"""US regular-trading-hours calendar for the live plan manager.

Stdlib only -- no pandas, no network -- the same shape as opex.py, which
owns a US market timezone for a different policy and now imports this
module's constant rather than declaring a second one.

WHY THIS EXISTS. `get_current_price` fetches with `prepost=True`, so the
60s monitor sees premarket and after-hours prints. A regular stop order
does not execute outside regular hours, and the backtest reads
regular-hours daily bars and cannot see those prints at all. Without this
gate the live manager acts on a price universe neither reality nor the
backtest shares.

ACCEPTED LIMITATION, stated rather than solved: no holiday or half-day
calendar. On a market holiday `is_regular_session` returns True and
`get_current_price` returns the previous session's close -- a stale price
that either already armed a break-even move or already did not, so acting
on it again is idempotent and the failure is benign. A 13:00 half-day close
has the same shape. Building a holiday calendar to close a benign gap is
not worth the dependency; if it ever stops being benign that is a new
observation and its own change.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

US_MARKET_TZ = ZoneInfo("America/New_York")

# The regular session. The open is inclusive and the close exclusive:
# 16:00:00 is the closing print, after which no stop rests in the book.
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def now_et(now: dt.datetime | None = None) -> dt.datetime:
    """`now` (or the current moment) as an aware datetime in US market time.

    A naive datetime is assumed to already BE market time rather than
    silently localized to the host's timezone -- this bot runs on a
    UTC-clocked VM and a Windows dev box, and guessing from the host would
    make the same input mean two things.
    """
    if now is None:
        return dt.datetime.now(US_MARKET_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=US_MARKET_TZ)
    return now.astimezone(US_MARKET_TZ)


def is_regular_session(now: dt.datetime | None = None) -> bool:
    """True during Mon-Fri 09:30 <= t < 16:00 America/New_York."""
    et = now_et(now)
    if et.weekday() >= 5:
        return False
    return RTH_OPEN <= et.time() < RTH_CLOSE


def session_date(now: dt.datetime | None = None) -> str:
    """The ET calendar date, ISO. This is what stamps a plan -- a UTC date
    would roll over at 20:00 ET and split one session across two stamps."""
    return now_et(now).date().isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/market/test_session.py -v`
Expected: PASS, 13 tests.

- [ ] **Step 5: Point opex.py at the shared timezone constant**

In `swingbot/core/market/opex.py`, replace the local `ZoneInfo` declaration
at lines 33-35:

```python
from zoneinfo import ZoneInfo

US_MARKET_TZ = ZoneInfo("America/New_York")
```

with:

```python
from swingbot.core.market.session import US_MARKET_TZ
```

`US_CLOSE_TIME` stays exactly where it is — it anchors an opex policy, not
a session boundary, and moving it would ripple into flag-gated behaviour
this plan has no business touching. `opex.US_MARKET_TZ` keeps working for
every existing importer because the name is still bound in that module.

- [ ] **Step 6: Run the opex tests to verify nothing moved**

Run: `python scripts/dev/testrun.py file tests/market/test_opex.py`
Expected: green. If `tests/market/test_opex.py` does not exist, find the
opex tests with `git grep -l "opex" -- tests/` and run that file instead.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/session.py swingbot/core/market/opex.py tests/market/test_session.py
git commit -m "feat(v64): add US regular-session calendar for the live plan manager"
```

---

### Task P2: Session-stamp fields on TradePlanV2

**Files:**
- Modify: `swingbot/core/planning/plan_engine.py:82-140` (the `TradePlanV2` dataclass)
- Test: `tests/planning/test_plan_serialization.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `TradePlanV2.be_armed_session: str | None = None` and
  `TradePlanV2.runner_floor_session: str | None = None`. Tasks P5–P7 read
  and write both.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_plan_serialization.py`:

```python
def test_session_stamp_fields_default_to_none_and_round_trip():
    from swingbot.core.planning.plan_engine import plan_from_dict, plan_to_dict
    from tests.planning.test_plan_engine_model import _plan

    p = _plan()
    assert p.be_armed_session is None
    assert p.runner_floor_session is None

    p.be_armed_session = "2026-08-27"
    p.runner_floor_session = "2026-08-28"
    back = plan_from_dict(plan_to_dict(p))
    assert back.be_armed_session == "2026-08-27"
    assert back.runner_floor_session == "2026-08-28"


def test_a_plan_persisted_before_v64_loads_with_unstamped_sessions():
    """No migration: plan_from_dict filters to known field names and lets
    the dataclass defaults fill the rest. A plan already carrying a moved
    stop loads with be_armed_session None, which reads as 'armed on an
    unknown session' -- i.e. not this one -- so its stop governs
    immediately, exactly as it did before this change."""
    from swingbot.core.planning.plan_engine import plan_from_dict, plan_to_dict
    from tests.planning.test_plan_engine_model import _plan

    legacy = plan_to_dict(_plan())
    legacy["working_stop"] = 100.0
    del legacy["be_armed_session"]
    del legacy["runner_floor_session"]

    back = plan_from_dict(legacy)
    assert back.working_stop == 100.0
    assert back.be_armed_session is None
    assert back.runner_floor_session is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_plan_serialization.py -k session -v`
Expected: FAIL with `AttributeError: 'TradePlanV2' object has no attribute 'be_armed_session'`

- [ ] **Step 3: Add the fields**

In `swingbot/core/planning/plan_engine.py`, immediately after the
`confidence_level: int | None = None` field at the end of the
`TradePlanV2` dataclass, add:

```python
    # v64 live-exit parity. The ET session date (YYYY-MM-DD) on which the
    # break-even move armed, and on which TP1 fired and wrote the runner
    # floor. Both exist so the live manager can reproduce this module's own
    # rule -- "the moved stop only protects bars AFTER the trigger bar"
    # (see _single_leg_exit_walk's conservative-ordering comment) -- which
    # a 60s poller otherwise breaks by arming and firing the same session.
    #
    # None means "armed on an unknown session", which reads as "not this
    # session" and lets the stop govern immediately. That is deliberately
    # the right answer for a plan persisted before this field existed:
    # plan_from_dict falls back to dataclass defaults for absent keys, so
    # data/plans.json needs no migration.
    be_armed_session: str | None = None
    runner_floor_session: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_engine.py tests/planning/test_plan_serialization.py
git commit -m "feat(v64): stamp break-even and runner-floor arming sessions on TradePlanV2"
```

---

# Phase 2 — Live manager parity fixes

Sequential throughout: every task below edits `plan_manager.py`'s
`poll`/`_step_active`/`_step_partial` and consumes what the previous task
wrote.

---

### Task P3: INTRADAY_RTH_ONLY config flag

**Files:**
- Modify: `swingbot/config.py:527` (immediately after the `INTRADAY_MANAGER_V2` field)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.INTRADAY_RTH_ONLY: bool`, default `True`. Task P4 reads it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_intraday_rth_only_defaults_on():
    from swingbot import config
    assert config.INTRADAY_RTH_ONLY is True
```

If `tests/test_config.py` does not exist, locate the config tests with
`git grep -l "from swingbot import config" -- tests/ | head` and append to
whichever file already asserts on field defaults.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -k rth_only -v`
Expected: FAIL with `AttributeError: module 'swingbot.config' has no attribute 'INTRADAY_RTH_ONLY'`

- [ ] **Step 3: Add the field**

In `swingbot/config.py`, directly after the `INTRADAY_MANAGER_V2` `Field(...)`
entry, insert:

```python
    Field("INTRADAY_RTH_ONLY", "INTRADAY_RTH_ONLY", "Plan Engine v2",
          "Manage plans only during regular US trading hours",
          type="checkbox", default="true",
          help="The 60s plan manager ticks only Mon-Fri 09:30-16:00 America/New_York. "
               "get_current_price fetches with prepost=True, so with this off the manager "
               "acts on premarket and after-hours prints: a single thin print can arm the "
               "break-even move permanently, or close a position at a price no regular stop "
               "order could ever have filled. The backtest reads regular-hours daily bars and "
               "cannot see those prints, so with this off the live bot and every VALIDATED "
               "badge describe different rules. Overnight moves are not lost -- they are "
               "realised on the first regular-hours poll, which prices them as the gaps they "
               "are. Off restores the pre-v64 24/7 behaviour; the only reason to do that is "
               "to reproduce an old result."),
```

Nothing else is needed: `_apply_env()` walks `FIELDS` and sets a module
global per entry, and `_CASTERS["checkbox"]` turns `"true"` into `True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_config.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py tests/test_config.py
git commit -m "feat(v64): add INTRADAY_RTH_ONLY flag, default on"
```

---

### Task P4: Gate the poll tick to regular hours

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:134-168` (`PlanManager.poll`)
- Test: `tests/planning/test_plan_manager_session.py`

**Interfaces:**
- Consumes: `config.INTRADAY_RTH_ONLY` (P3), `session.is_regular_session` (P1).
- Produces: `PlanManager.poll(now: datetime | None = None)` — the optional
  `now` is the injected clock every later task's tests use.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_session.py`:

```python
import datetime as dt

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)      # Thursday noon
AFTER_HOURS = dt.datetime(2026, 8, 27, 19, 30, tzinfo=US_MARKET_TZ)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())          # entry 100, stop 95, tp1 110
    return store, PlanManager(store, feed.get_price)


def test_after_hours_poll_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    store, mgr = _env(tmp_path, [94.0])       # would be a stop-out in session
    assert mgr.poll(now=AFTER_HOURS) == []
    assert store.get("p1").status == "ACTIVE"


def test_regular_hours_poll_still_acts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=RTH)
    assert [e.transition for e in events] == ["closed"]


def test_flag_off_restores_round_the_clock_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_plan_manager_session.py -v`
Expected: FAIL — `test_after_hours_poll_is_a_no_op` gets a `closed` event
(the gate does not exist), and the other two fail on
`poll() got an unexpected keyword argument 'now'`.

- [ ] **Step 3: Add the import and the gate**

In `swingbot/core/planning/plan_manager.py`, add to the imports at the top:

```python
from swingbot.core.market.session import is_regular_session, session_date
```

Then change the `poll` signature and add the gate as its first statement,
before `self.store.reload()`:

```python
    def poll(self, now=None) -> list[PlanEvent]:
        # v64: act only on prices a regular stop order could actually have
        # traded against. get_current_price fetches with prepost=True, so
        # without this gate one thin premarket print arms the break-even
        # move permanently and one thin after-hours print closes the
        # position -- neither fillable in reality, and neither visible to
        # the backtest, which reads regular-hours daily bars. The gate is
        # on the WHOLE tick rather than on the break-even arm alone: gating
        # only the arm would leave a state machine that fills entries and
        # closes positions on prints it refuses to arm on, three rules for
        # one price feed. Overnight moves are realised on the first
        # regular-hours poll, which _step_active prices as the gap it is.
        #
        # `now` is injectable so tests need no global datetime patch.
        if config.INTRADAY_RTH_ONLY and not is_regular_session(now):
            return []
        self.store.reload()
```

The rest of `poll` is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_session.py`
Expected: green, 3 tests.

- [ ] **Step 5: Verify no existing manager test regressed**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py`

Expected: green. Existing tests call `mgr.poll()` with no clock, so
`is_regular_session(None)` reads the wall clock and they will fail whenever
the suite runs outside market hours. **If any fail for that reason, fix
them by setting the flag off for the module** rather than by weakening the
gate — add to `tests/planning/test_plan_manager_active.py`,
`test_plan_manager_pending.py` and `test_plan_manager_partial.py`:

```python
@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    """These modules test exit ARITHMETIC, not the session gate (which has
    its own file). Pinning the flag off keeps them deterministic whatever
    time of day the suite runs."""
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
```

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/
git commit -m "fix(v64): gate the live plan tick to regular trading hours"
```

---

### Task P5: Realistic poll fills on a stop breach

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — add `poll_stop_fill` beside `gap_stop_fill` (line 25), add `_last_seen` to `__init__` (line 124), record it in `poll`, add `_continuous`, use both in `_step_active`
- Test: `tests/planning/test_plan_manager_fills.py`

**Interfaces:**
- Consumes: `session_date` (P1), `PlanManager.poll(now=...)` (P4).
- Produces: `poll_stop_fill(price: float, stop: float, continuous: bool) -> float`
  and `PlanManager._continuous(plan: TradePlanV2, stop: float) -> bool`.
  Task P7 calls both for the runner leg.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_fills.py`:

```python
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager, poll_stop_fill
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

DAY1_OPEN = dt.datetime(2026, 8, 27, 9, 35, tzinfo=US_MARKET_TZ)
DAY1_NOON = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
DAY2_OPEN = dt.datetime(2026, 8, 28, 9, 35, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _rth_on(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())          # bullish, entry 100, stop 95, tp1 110
    return store, PlanManager(store, feed.get_price)


def test_poll_stop_fill_clamps_when_continuous():
    assert poll_stop_fill(94.2, 95.0, continuous=True) == 95.0
    assert poll_stop_fill(94.2, 95.0, continuous=False) == 94.2


def test_continuous_breach_fills_at_the_stop_not_the_sampled_price(tmp_path):
    # Poll 1 sees 99 -- safely above the 95 stop, same session. Poll 2 sees
    # 94.2: the tape crossed 95 while we were watching, so a resting stop
    # filled AT 95. 94.2 is a 60-second sampling artifact, not a fill.
    store, mgr = _env(tmp_path, [99.0, 94.2])
    assert mgr.poll(now=DAY1_OPEN) == []
    events = mgr.poll(now=DAY1_NOON)
    assert events[0].detail["exit_price"] == 95.0
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx(-1.0)


def test_first_poll_of_a_session_keeps_the_gap(tmp_path):
    # Nothing seen this session: this is the first look after an overnight
    # gap, so the observed price IS the fill -- same convention as
    # gap_stop_fill applied to a bar's open.
    store, mgr = _env(tmp_path, [91.0])
    events = mgr.poll(now=DAY1_OPEN)
    assert events[0].detail["exit_price"] == 91.0
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx((91 - 100) / 5)


def test_yesterdays_observation_does_not_make_today_continuous(tmp_path):
    # Seen at 99 yesterday, gaps to 91 overnight. The prior observation is
    # from a different session, so this is a gap fill, not a clamp.
    store, mgr = _env(tmp_path, [99.0, 91.0])
    assert mgr.poll(now=DAY1_NOON) == []
    events = mgr.poll(now=DAY2_OPEN)
    assert events[0].detail["exit_price"] == 91.0


def test_continuity_works_the_same_way_for_a_short(tmp_path):
    # Bearish: the safe side of a 105 stop is BELOW it. Poll 1 sees 101,
    # poll 2 sees 106 -- we watched the tape cross 105, so the buy-stop
    # filled at 105, not at the 106 this poll happened to sample.
    feed = FakePriceFeed()
    feed.set_series("AAPL", [101.0, 106.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(direction="bearish", stop_loss=105.0, tp1=90.0))
    mgr = PlanManager(store, feed.get_price)
    assert mgr.poll(now=DAY1_OPEN) == []
    events = mgr.poll(now=DAY1_NOON)
    assert events[0].detail["exit_price"] == 105.0
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx(-1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_plan_manager_fills.py -v`
Expected: FAIL with `ImportError: cannot import name 'poll_stop_fill'`

- [ ] **Step 3: Add the fill helper**

In `swingbot/core/planning/plan_manager.py`, directly after
`gap_target_fill` (around line 32), add:

```python
def poll_stop_fill(price: float, stop: float, continuous: bool) -> float:
    """Fill for a stop breach seen by the 60s poller -- gap_stop_fill's
    sibling for a path that samples a tape instead of reading a bar.

    `continuous`: a previous poll THIS regular session saw the price on the
    safe side of `stop`. The tape crossed the level while we were watching,
    so a resting stop order filled AT it; the worse price this poll happened
    to sample 60 seconds later is a sampling artifact, not something the
    market did to the order. Clamping to `stop` is the better price for a
    long and for a short alike, so no direction branch is needed.

    Otherwise this is the first look since a gap and the observed price IS
    the fill -- exactly the convention gap_stop_fill applies to a bar open.

    Without this, EVERY live stop-out booked a gap-magnitude penalty,
    including the great majority that were not gaps. On a break-even stop
    that turned an exit the backtest scores at exactly 0.000R into a small
    recorded loss on every single trade.
    """
    return stop if continuous else price
```

- [ ] **Step 4: Track the last observation and use it**

In `PlanManager.__init__` (around line 129), after
`self.trade_log = trade_log`, add:

```python
        # v64: plan_id -> (ET session date, last observed price). In memory,
        # not on the plan: persisting it would turn every 60s poll of every
        # open plan into an atomic plans.json write, where today
        # store.update() fires only on a transition. A restart empties the
        # map, so the first poll afterwards is treated as discontinuous and
        # falls back to the observed price -- the conservative direction,
        # and the same answer this code gave before v64.
        self._last_seen: dict[str, tuple[str, float]] = {}
```

Add the `_continuous` helper as a method, directly above `_step`:

```python
    def _continuous(self, plan: TradePlanV2, stop: float, now=None) -> bool:
        """True when a previous poll THIS session saw `plan`'s price on the
        safe side of `stop` -- i.e. we watched the tape cross the level."""
        seen = self._last_seen.get(plan.plan_id)
        if seen is None:
            return False
        seen_session, seen_price = seen
        if seen_session != session_date(now):
            return False
        return (seen_price > stop if plan.direction == "bullish"
                else seen_price < stop)
```

In `poll`, record every observation. Change the `_step` call site so the
recording happens after the step, regardless of outcome — a closed plan's
stale entry is harmless because plan ids are never reused:

```python
            try:
                new_events = self._step(plan, price, now)
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
            self._last_seen[plan.plan_id] = (session_date(now), price)
```

Thread `now` through `_step`:

```python
    def _step(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        if plan.status == PlanStatus.PENDING:
            return self._step_pending(plan, price)
        if plan.status == PlanStatus.ACTIVE:
            return self._step_active(plan, price, now)     # Tasks 61-63
        if plan.status == PlanStatus.PARTIAL:
            return self._step_partial(plan, price, now)    # Tasks 64-66
        return []
```

- [ ] **Step 5: Use the fill in `_step_active`**

Change `_step_active`'s signature to
`def _step_active(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:`
and replace its stop branch:

```python
        stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if plan.working_stop is not None else "loss"
            record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": price})]
```

with:

```python
        stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if plan.working_stop is not None else "loss"
            fill = poll_stop_fill(price, stop, self._continuous(plan, stop, now))
            record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "closed",
                              {"reason": reason, "exit_price": fill})]
```

`_step_partial` keeps its current signature body for now — Task P7 changes
it. Accept the unused `now` parameter there in this task:

```python
    def _step_partial(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_fills.py`
Expected: green, 5 tests.

Then run the neighbours that assert on exit prices:
`python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py`

`test_stop_hit_pre_be_is_loss` asserts `exit_price == 94.5` from a single
poll. That is still correct — one poll means no prior observation, so the
fill stays at the observed price. If it fails, the `_continuous` logic is
wrong; fix the logic, not the test.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_fills.py
git commit -m "fix(v64): fill a continuous poll stop breach at the stop, not the sampled tick"
```

---

### Task P6: The break-even stop protects later sessions only

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — add `_active_stop`, use it in `_step_active`, stamp `be_armed_session` on arming
- Test: `tests/planning/test_plan_manager_be_session.py`

**Interfaces:**
- Consumes: `session_date` (P1), `TradePlanV2.be_armed_session` (P2),
  `poll_stop_fill`/`_continuous` (P5).
- Produces: `PlanManager._active_stop(plan, now=None) -> tuple[float, bool]`
  returning `(level, is_be_stop)`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_be_session.py`:

```python
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

DAY1_A = dt.datetime(2026, 8, 27, 10, 0, tzinfo=US_MARKET_TZ)
DAY1_B = dt.datetime(2026, 8, 27, 14, 0, tzinfo=US_MARKET_TZ)
DAY2 = dt.datetime(2026, 8, 28, 10, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _rth_on(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())          # bullish, entry 100, stop 95, tp1 110
    return store, PlanManager(store, feed.get_price)


def test_arming_stamps_the_session(tmp_path):
    store, mgr = _env(tmp_path, [105.0])       # BE trigger = 100 + 0.5*10
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["be_moved"]
    p = store.get("p1")
    assert p.working_stop == 100.0
    assert p.be_armed_session == "2026-08-27"


def test_be_stop_does_not_fire_the_session_it_armed(tmp_path):
    # plan_engine's own rule: "the moved stop only protects bars AFTER the
    # trigger bar". Arm at 105, drop to 99.9 the same session -- the
    # backtest keeps this trade alive, so live must too.
    store, mgr = _env(tmp_path, [105.0, 99.9])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["be_moved"]
    assert mgr.poll(now=DAY1_B) == []
    assert store.get("p1").status == "ACTIVE"


def test_be_stop_fires_the_next_session(tmp_path):
    # Day 2 poll A at 101 is above the 100 break-even stop, so poll B's
    # breach is CONTINUOUS and fills at 100 -- the 0.000R the backtest
    # scores. This is the exact path the reported symptom broke.
    store, mgr = _env(tmp_path, [105.0, 101.0, 99.9])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["be_moved"]
    assert mgr.poll(now=DAY2) == []
    events = mgr.poll(now=dt.datetime(2026, 8, 28, 14, 0, tzinfo=US_MARKET_TZ))
    assert events[0].detail["reason"] == "scratch"
    assert events[0].detail["exit_price"] == 100.0
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx(0.0)
    assert store.get("p1").status == "CLOSED"


def test_the_first_look_of_a_new_session_still_prices_an_overnight_gap(tmp_path):
    # The counterpart: nothing seen yet on day 2, so a price already
    # through the break-even stop is a genuine overnight gap and books the
    # small real loss. v64 makes scratches rarer and prices the continuous
    # ones at 0R -- it does not pretend every scratch is free.
    store, mgr = _env(tmp_path, [105.0, 99.9])
    mgr.poll(now=DAY1_A)
    events = mgr.poll(now=DAY2)
    assert events[0].detail["reason"] == "scratch"
    assert events[0].detail["exit_price"] == 99.9
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx((99.9 - 100) / 5)


def test_original_stop_breached_the_arming_session_is_a_loss_not_a_scratch(tmp_path):
    # THE label bug this rule creates if reason keys off `working_stop is
    # not None` instead of which stop was actually breached: a full -1R
    # outcome filed under the label analytics treat as ~0R.
    store, mgr = _env(tmp_path, [105.0, 94.0])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["be_moved"]
    events = mgr.poll(now=DAY1_B)
    assert events[0].detail["reason"] == "loss"
    assert events[0].detail["exit_price"] == 95.0      # continuous: clamps to stop
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx(-1.0)


def test_a_pre_v64_plan_with_an_unstamped_session_governs_immediately(tmp_path):
    store, mgr = _env(tmp_path, [99.9])
    p = store.get("p1")
    p.working_stop = 100.0
    p.be_armed_session = None          # armed before this field existed
    store.update(p)
    events = mgr.poll(now=DAY1_A)
    assert events[0].detail["reason"] == "scratch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_plan_manager_be_session.py -v`
Expected: FAIL — `test_arming_stamps_the_session` sees
`be_armed_session is None`, and `test_be_stop_does_not_fire_the_session_it_armed`
gets a `closed` event.

- [ ] **Step 3: Add the governing-stop helper**

In `swingbot/core/planning/plan_manager.py`, directly above `_step_active`,
add:

```python
    def _active_stop(self, plan: TradePlanV2, now=None) -> tuple[float, bool]:
        """The stop actually governing an ACTIVE plan right now, and whether
        it is the break-even one.

        v64 parity: the moved stop protects only from the session AFTER it
        armed, matching plan_engine._single_leg_exit_walk's "the moved stop
        only protects bars AFTER the trigger bar". Until then the ORIGINAL
        stop still governs -- and a breach of THAT is a full -1R loss, not
        a scratch, which is why this returns the label rather than leaving
        the caller to infer it from `working_stop is not None`.

        be_armed_session None means "armed on an unknown session", i.e. not
        this one, so a plan persisted before that field existed keeps its
        moved stop governing immediately.
        """
        if plan.working_stop is None:
            return plan.stop_loss, False
        if plan.be_armed_session == session_date(now):
            return plan.stop_loss, False
        return plan.working_stop, True
```

- [ ] **Step 4: Use it, and stamp the session on arming**

In `_step_active`, replace the stop branch written in Task P5:

```python
        stop = plan.working_stop if plan.working_stop is not None else plan.stop_loss
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if plan.working_stop is not None else "loss"
```

with:

```python
        stop, is_be_stop = self._active_stop(plan, now)
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if is_be_stop else "loss"
```

The `fill`/`record_transition`/`return` lines below it are unchanged.

Then in the same method, stamp the session when the move arms:

```python
        if reached_be and plan.working_stop is None:
            plan.working_stop = entry
            plan.be_armed_session = session_date(now)   # v64: protects LATER sessions
            self.store.update(plan)
            return [PlanEvent(plan.plan_id, "be_moved",
                              {"working_stop": entry, "live_price": price})]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_be_session.py`
Expected: green, 6 tests.

- [ ] **Step 6: Fix the neighbour that encodes the old rule**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py`

`test_stop_hit_post_be_is_scratch` polls twice with no clock, so both polls
land in the same session and it now correctly gets no close. **This test
asserted the bug.** Rewrite it to pass an explicit two-session clock:

```python
def test_stop_hit_post_be_is_scratch(tmp_path):
    # v64: the break-even stop protects only from the session AFTER it
    # armed (plan_engine's "bars AFTER the trigger bar"), so the second
    # poll must be a later session for this to close.
    import datetime as dt
    from swingbot.core.market.session import US_MARKET_TZ
    day1 = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
    day2 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=US_MARKET_TZ)
    store, mgr = _env(tmp_path, [105.0, 99.9])
    assert [e.transition for e in mgr.poll(now=day1)] == ["be_moved"]
    events = mgr.poll(now=day2)
    assert events[0].detail["reason"] == "scratch"
    assert store.get("p1").status == PlanStatus.CLOSED
```

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/
git commit -m "fix(v64): break-even stop protects later sessions only, matching the backtest"
```

---

### Task P7: The runner floor protects later sessions only

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — stamp `runner_floor_session` at TP1 in `_step_active`, gate the exit checks in `_step_partial`
- Test: `tests/planning/test_plan_manager_runner_session.py`

**Interfaces:**
- Consumes: `session_date` (P1), `TradePlanV2.runner_floor_session` (P2),
  `poll_stop_fill`/`_continuous` (P5).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_runner_session.py`:

```python
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

DAY1_A = dt.datetime(2026, 8, 27, 10, 0, tzinfo=US_MARKET_TZ)
DAY1_B = dt.datetime(2026, 8, 27, 14, 0, tzinfo=US_MARKET_TZ)
DAY2 = dt.datetime(2026, 8, 28, 10, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _rth_on(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())          # bullish, entry 100, stop 95, tp1 110
    return store, PlanManager(store, feed.get_price)


def test_tp1_stamps_the_runner_floor_session(tmp_path):
    store, mgr = _env(tmp_path, [110.5])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["tp1_partial"]
    p = store.get("p1")
    assert p.working_stop == pytest.approx(100 + (2 / 3) * 10)   # runner_floor
    assert p.runner_floor_session == "2026-08-27"


def test_runner_floor_does_not_fire_the_session_tp1_did(tmp_path):
    # _scale_out_exit_walk's phase 2 runs range(tp1_index + 1, ...) -- the
    # floor never governs the TP1 bar. Live must match.
    store, mgr = _env(tmp_path, [110.5, 100.0])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["tp1_partial"]
    assert mgr.poll(now=DAY1_B) == []
    assert store.get("p1").status == "PARTIAL"


def test_runner_floor_fires_the_next_session(tmp_path):
    store, mgr = _env(tmp_path, [110.5, 100.0])
    mgr.poll(now=DAY1_A)
    events = mgr.poll(now=DAY2)
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert store.get("p1").status == "CLOSED"


def test_tp2_also_waits_for_the_next_session(tmp_path):
    # The whole phase-2 exit check is suppressed on the TP1 session, not
    # just the stop half -- otherwise live banks a TP2 the backtest cannot
    # see, which is the same parity break with the sign flipped.
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5, 130.0, 130.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=125.0))
    mgr = PlanManager(store, feed.get_price)
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["tp1_partial"]
    assert mgr.poll(now=DAY1_B) == []
    events = mgr.poll(now=DAY2)
    assert events[0].detail["reason"] == "tp1_runner_tp2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_plan_manager_runner_session.py -v`
Expected: FAIL — `runner_floor_session` is `None` and the floor fires the
same session.

- [ ] **Step 3: Stamp the session at TP1**

In `_step_active`'s TP1 branch, beside the existing `working_stop` write:

```python
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            plan.runner_floor_session = session_date(now)       # v64: governs LATER sessions
```

- [ ] **Step 4: Gate the phase-2 exit checks**

In `_step_partial`, wrap the stop and TP2 branches in the session guard.
The pyramid branch above them and the chandelier ratchet below them stay
outside it. Replace:

```python
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            # v39: "tp1_runner_be" now means "closed at the initial post-TP1
            # floor", not literally at entry. The string is unchanged on
            # purpose -- see the same note in plan_engine._scale_out_exit_walk.
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, price, reason, risk, sign)

        if plan.tp2 is not None:
            hit_tp2 = price >= plan.tp2 if is_bull else price <= plan.tp2
            if hit_tp2:
                return self._close_runner(plan, price, "tp1_runner_tp2", risk, sign)
```

with:

```python
        # v64: phase 2 governs only from the session AFTER TP1 fired --
        # _scale_out_exit_walk runs range(tp1_index + 1, ...), so neither the
        # floor nor TP2 is checked against the TP1 bar itself. Suppressing
        # only the stop half would let live bank a TP2 the backtest cannot
        # see: the same parity break with the sign flipped. The chandelier
        # ratchet below is deliberately NOT gated -- the backtest also seeds
        # extreme_close from the TP1 bar's close.
        if plan.runner_floor_session != session_date(now):
            hit_stop = price <= stop if is_bull else price >= stop
            if hit_stop:
                # v39: "tp1_runner_be" now means "closed at the initial
                # post-TP1 floor", not literally at entry. The string is
                # unchanged on purpose -- see the same note in
                # plan_engine._scale_out_exit_walk.
                reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                          else "tp1_runner_trail")
                fill = poll_stop_fill(price, stop, self._continuous(plan, stop, now))
                return self._close_runner(plan, fill, reason, risk, sign)

            if plan.tp2 is not None:
                hit_tp2 = price >= plan.tp2 if is_bull else price <= plan.tp2
                if hit_tp2:
                    return self._close_runner(plan, price, "tp1_runner_tp2",
                                              risk, sign)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_runner_session.py`
Expected: green, 4 tests.

- [ ] **Step 6: Fix the neighbours that encode the old rule**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`

Any test that banks TP1 and closes the runner within one `poll()` sequence
now correctly gets no close. Give each an explicit two-session clock the
same way Task P6 Step 6 did. **Do not** relax the guard to make them pass —
they encode the pre-v64 behaviour, which is the bug.

Tests using `mgr.check_bar(...)` need no change: that path is untouched.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/
git commit -m "fix(v64): runner floor and TP2 protect later sessions only"
```

---

### Task P8: Thread the clock through `run_manager_tick`

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:470-482` (`run_manager_tick`)
- Test: `tests/planning/test_trade_monitor_wiring.py`

**Interfaces:**
- Consumes: `PlanManager.poll(now=...)` (P4).
- Produces: nothing new — `run_manager_tick()` keeps its signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_trade_monitor_wiring.py`:

```python
def test_run_manager_tick_is_a_no_op_outside_regular_hours(monkeypatch, tmp_path):
    """The whole point of the v64 gate is that the 60s loop stops acting on
    extended-hours prints. Assert it at the wiring seam, not just on the
    PlanManager method the loop calls."""
    import datetime as dt

    from swingbot import config
    from swingbot.core.market import session as session_mod
    from swingbot.core.planning import plan_manager

    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plan_manager, "_MANAGER", None)
    monkeypatch.setattr(
        session_mod, "is_regular_session",
        lambda now=None: False)
    monkeypatch.setattr(
        plan_manager, "is_regular_session",
        lambda now=None: False)

    assert plan_manager.run_manager_tick() == []
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/planning/test_trade_monitor_wiring.py -k outside_regular -v`

Expected: this may already PASS, because `run_manager_tick` calls
`_MANAGER.poll()` with no argument and `poll` gates on
`is_regular_session(None)`. **That is the correct outcome and the test is
still worth keeping** — it pins the wiring so a later refactor of
`run_manager_tick` cannot quietly drop the gate. If it fails, the gate is
not reached from the singleton path; fix `run_manager_tick`.

- [ ] **Step 3: Add the explanatory comment**

In `run_manager_tick`, above the `return _MANAGER.poll()` line:

```python
    # No `now` argument: production reads the wall clock. The parameter
    # exists purely so tests can inject a session without patching
    # datetime globally.
    return _MANAGER.poll()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_trade_monitor_wiring.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_trade_monitor_wiring.py
git commit -m "test(v64): pin the RTH gate at the trade-monitor wiring seam"
```

---

# Phase 3 — Documentation and verification

---

### Task P9: Record the restored invariant and the dead bar-check path

**Files:**
- Modify: `docs/claude/architecture.md` (the Plan Engine v2 bullet)
- Modify: `docs/claude/known-traps.md` (append a row)
- Modify: `swingbot/core/planning/plan_manager.py:365-370` (`check_bar` docstring)
- Modify: `.codex/AGENTS.md` (only if it repeats the parity claim)

- [ ] **Step 1: Correct the architecture claim**

In `docs/claude/architecture.md`, the Plan Engine v2 bullet says live
behaviour equals backtested behaviour "by construction". Replace that
clause with the truth — that it is an invariant this repo actively
maintains, and what maintains it:

```markdown
  `swingbot/core/backtesting/backtest.py run_backtest(..., exit_model="v2",
  scale_out=True)` uses the same simulator, so live behavior equals
  backtested behavior. That is an **invariant this repo maintains, not one
  the code structure guarantees** — the live path polls a tape every 60s
  while the simulator walks daily bars, and v64 fixed three ways they had
  drifted apart: extended-hours prints acting on plans (now gated by
  `INTRADAY_RTH_ONLY`), a stop breach filling at the sampled tick rather
  than at the stop, and a moved stop firing the same session it armed
  instead of "bars AFTER the trigger bar". Any new live-path exit rule must
  name the simulator line it matches.
```

- [ ] **Step 2: Add the known-traps row**

Append to `docs/claude/known-traps.md`:

```markdown
## `PlanManager.check_bar()` is unwired — do not "fix" it

`check_bar` / `_check_bar_active` / `_check_bar_partial` model overnight
gap fills against a real OHLC bar, are fully tested
(`tests/planning/test_plan_manager_gaps.py`), and **are never called from
production code.** `git grep check_bar` returns `plan_manager.py` and two
test files, nothing else. The live bot exits exclusively through `poll()`.

They are deliberately left inert rather than deleted or wired. Wiring them
would create a second authority for the same transition — two writers, one
`plans.json` — and v64 gave `poll()` its own gap handling (`poll_stop_fill`:
the first observation of a session keeps the gap, a continuous one clamps
to the stop), so there is nothing left for a second path to add.

**Consequence for anyone editing exit behaviour:** a change made only in
`_check_bar_*` ships nothing. That is the trap. Fix `_step_active` /
`_step_partial`, and mirror into `_check_bar_*` only to keep the tested
pair honest.
```

- [ ] **Step 3: Mark the dead path in code**

Prepend to the `check_bar` docstring block in `plan_manager.py` (the
"overnight/session-open bar check (Task 67)" comment above it):

```python
    # -- overnight/session-open bar check (Task 67) --------------------------
    #
    # UNWIRED. Nothing in production calls check_bar() -- `git grep check_bar`
    # returns this file and two test files. The live bot exits exclusively
    # through poll(). Kept, tested and inert: wiring it would make a second
    # authority for the same transition, and v64 gave poll() its own gap
    # handling (see poll_stop_fill). A change made only here ships nothing.
    # See docs/claude/known-traps.md.
```

- [ ] **Step 4: Mirror into the Codex agent file if it repeats the claim**

Run: `grep -n "by construction\|equals backtested" .codex/AGENTS.md`

If it repeats the parity claim, condense Step 1's correction into one
sentence there. The sync is one-way — a Claude session updates
`.codex/AGENTS.md`, never the reverse. If it does not mention it, change
nothing.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/architecture.md docs/claude/known-traps.md swingbot/core/planning/plan_manager.py .codex/AGENTS.md
git commit -m "docs(v64): record the restored live/backtest invariant and the unwired bar-check path"
```

---

### Task P10: Full-suite verification and version bump

- [ ] **Step 1: Run the full suite once**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner`
subagent so ~1150 progress lines stay out of the session context.

Expected: `0 failed`, `0 xfailed`. A *changed pass count* is not a failure —
this plan adds roughly 20 tests.

**If it is not green, fix forward from those failures.** They are this
plan's regressions. The likely shape is a `plan_manager` test that polls
twice with no clock and relied on same-session firing; give it an explicit
two-session clock as Tasks P6 and P7 did. Do not weaken a session guard to
make a test pass.

- [ ] **Step 2: Bump the bot version**

Edit `VERSION.json`: `bot` `1.4.5` → `1.5.0`, and set `bot_updated` to the
current timestamp in the existing `YYYY-MM-DD HH-MM-SS` format. Leave the
`ui` line and `ui_updated` untouched — no frontend file changed.

Minor, not patch: with `INTRADAY_RTH_ONLY` on, no plan transition and
therefore no Discord lifecycle alert fires outside 09:30–16:00 ET. That is
an observable product difference, which is the test — not the size of the
diff.

- [ ] **Step 3: Regenerate version history**

The local gate runs *before* the bump, so it structurally cannot catch a
missed regeneration. Find the generator with
`git grep -n "version_history" -- scripts/` and run it, then commit the
regenerated `version_history.json` **in the same commit as the bump.**

- [ ] **Step 4: Commit**

```bash
git add VERSION.json data/version_history.json
git commit -m "chore(v64): bump bot to 1.5.0 for live exit parity"
```

- [ ] **Step 5: Close the plan out**

Move both documents to `implemented/`:

```bash
git mv docs/superpowers/specs/2026-08-28-v64-live-exit-parity-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-28-v64-live-exit-parity.md docs/superpowers/plans/implemented/
git commit -m "docs(v64): close out live exit parity"
```

If the `Bump:` or `Edge:` prediction in either header came out wrong, amend
the line in this commit and add one clause saying why. A wrong prediction
recorded is worth more than a right one hidden.

---

## Post-plan: what is now measurable, and what it still costs

The registry badges describe the corrected rule only after
`run_backtest_range.py --emit-registry` is re-run. **That is not part of
this plan** — it is its own task with its own runtime, and it changes no
threshold.

The Tier 2 break-even questions (arming on a close, trigger 0.5 → 0.75, a
partial floor instead of full break-even, direction-aware break-even) are
now measurable against a harness whose live twin matches it. **Each is a
new pre-registered hypothesis with its own TRAIN grid and its own one-shot
VALIDATION.** Nothing in this plan is evidence for any of them.


## Close-out

**Complete 2026-08-30.** All V64 tasks merged to main in 87a4e5a; the full Python suite completed with exit code 0. The planned bot minor bump was already represented by the prior bot 1.5.0 Discord-message release, so this close-out intentionally adds no duplicate release metadata.
