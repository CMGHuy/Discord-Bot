# Extended-hours exit check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-03-v70-extended-hours-exit-check-design.md`

**Version:** ui 1.11.0 · bot 1.5.2
**Bump:** bot minor (1.5.x → 1.6.0) · ui none
**Edge:** none (integrity)

**Goal:** Give an open plan whose stop-loss or last remaining target is
breached outside 09:30–16:00 ET a way to close on the tick that confirms it,
instead of waiting for the next regular session — without letting anything
else in the plan lifecycle act on an extended-hours print.

**Architecture:** `core/market/session.py` grows a second predicate,
`is_quiet_hours`, answering "is the tape somewhere nobody should be acting on
it" (23:00–08:00 ET by config, plus all weekend). `PlanManager.poll()`'s
two-way gate becomes three-way: quiet → nothing; regular → today's full
`_step()` state machine, byte for byte; anything else → a new, deliberately
tiny `_step_extended()` that can produce exactly one outcome, a terminal
close, and only after `EXTENDED_HOURS_DEBOUNCE_TICKS` consecutive polls agree.
Four new config fields make the whole path revertible to pre-v70 behaviour
without a code change.

**Tech Stack:** Python 3.11+, stdlib `zoneinfo`/`datetime`, pytest,
discord.py (one embed style row).

## Global Constraints

- **No threshold, fraction or frozen constant changes.**
  `BREAKEVEN_TRIGGER_FRACTION`, `RUNNER_FLOOR_FRACTION = 2/3`,
  `tp1_fraction = 0.50`, the RR bounds — all untouched. This plan changes
  *when an existing rule may act*, never *what it is*.
- **No backtest, grid or validation run.** `Edge: none (integrity)`: this
  plan makes no expectancy claim, so there is nothing for a pre-registration
  to test. Do not run `run_backtest_range.py` or `tune_strategy.py` as part
  of it. `_step_extended` has no simulator counterpart to match — the
  backtest's daily bars never modelled premarket/after-hours prices.
- **`_step`, `_step_pending`, `_step_active`, `_step_partial`,
  `_check_bar_active`, `_check_bar_partial` get no behaviour change.** The
  only edits to existing code paths in this whole plan are three: `poll()`'s
  gate (X4), the one line in `poll()` that writes `_last_seen` (X4), and one
  clause of `_on_event`'s reason→status mapping (X5). Everything else is new
  code beside them.
- **`INTRADAY_RTH_ONLY=false` behaves byte for byte as it does today** — full
  `_step()` every tick, round the clock, no debounce, no quiet-hours gate.
  The quiet window only ever applies *on top of* the RTH gate.
- **`swingbot/core/` stays Discord-free.** `session.py` may import
  `swingbot.config` (X2): `config.py` imports stdlib and `python-dotenv`
  only and nothing from `core/market/`, so there is no cycle.
- **Every new function takes an injectable `now`.** No test in this plan may
  patch `datetime` globally.
- **No frontend change, and therefore no `ui` bump.** The admin settings
  screen is schema-driven — `tests/admin/test_api_v1_system_settings.py::test_a_new_field_appears_with_no_endpoint_change`
  is the standing proof — so four new `Field()` entries reach the UI with
  zero code change under `frontend/`.
- Per-task verification is the narrow run:
  `python scripts/dev/testrun.py file tests/<the one file this task touched>.py`.
  Never `... full` inside a task — **Task X7 is the single full run.**

## Four things this plan settles that the spec did not

Read these before starting; each one changes a task's content.

1. **`reason == "win"` needs two mappings the spec's §4.6 calls
   "unchanged".** Verified in the code, not assumed: `_on_event`
   (`swingbot/core/planning/plan_manager.py:202-203`) maps a close reason to
   a trade status with `"win" if reason.startswith("tp1_") else "loss" if
   reason == "loss" else "closed"`, so `"win"` would land a target hit in
   `trades.json` as status `"closed"`; and `PLAN_EVENT_STYLES`
   (`swingbot/core/scanning/lifecycle_embeds.py:289-300`) has no `"win"` key,
   so Discord would post the fallback "Plan closed" embed in neutral grey for
   a winning trade. **Task X5** adds both, with tests.
2. **`poll()` must NOT write `_last_seen` on an extended-hours tick.** The
   spec's §4.1 snippet writes it unconditionally, which contradicts its own
   §3 ("the RTH state machine is unchanged"). `_continuous()` asks whether
   the *same session* has already seen a price on the safe side of the stop,
   and v64's `poll_stop_fill` then fills a breach **at the stop level**
   instead of at the observed price. An 08:30 premarket print above the stop
   would therefore make the 09:30 gap-down fill at the stop — a better price
   than anything that ever printed. **Task X4** gates the write to the
   regular branch and tests exactly that.
3. **The spec's Parallelisation "Group 1 (parallel)" is not parallel.**
   `is_quiet_hours` reads `config.QUIET_HOURS_START_ET` /
   `QUIET_HOURS_END_ET` — it consumes symbols the config task introduces, so
   the config fields land **first**. Phase 1 is sequential: X1 then X2.
4. **The debounce counter is keyed by breach kind, not just plan id.** The
   spec's §4.4 rule ("a reverting tick pops the entry entirely, so a later
   unrelated breach cannot complete a partial streak") generalises: a stop
   tick followed by a target tick are *two different breaches*, and with the
   spec's plain `dict[str, int]` the second would complete the first's count
   and close at the wrong level. Storing `(kind, streak)` costs two lines and
   removes the case. Same intent, tighter.

---

# Phase 1 — Config and the quiet-hours predicate

## Parallelisation

**Sequential: X1 before X2.** They edit different files, but `is_quiet_hours`
reads the two config fields X1 introduces, so X2's tests cannot pass first
(finding 3 above). Do not dispatch them together.

---

### Task X1: The four v70 config fields

**Files:**
- Modify: `swingbot/config.py:534` (immediately after the `INTRADAY_RTH_ONLY` field)
- Modify: `.env.example:317` (immediately after `INTRADAY_RTH_ONLY=true`)
- Test: `tests/test_config_flags.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.EXTENDED_HOURS_EXIT_CHECK: bool` (default `True`),
  `config.QUIET_HOURS_START_ET: int` (23), `config.QUIET_HOURS_END_ET: int`
  (8), `config.EXTENDED_HOURS_DEBOUNCE_TICKS: int` (2). X2 reads the two
  quiet-hours ints; X3 reads the debounce count; X4 reads the check flag.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_flags.py` (it already ends with
`test_intraday_rth_only_defaults_on`):

```python
def test_v70_extended_hours_fields_exist_with_documented_defaults():
    """v70: the extended-hours exit check ships on, the quiet window is
    23:00-08:00 ET, and a breach needs two consecutive polls to confirm."""
    by_key = {f.key: f for f in config.FIELDS}

    assert by_key["EXTENDED_HOURS_EXIT_CHECK"].default == "true"
    assert by_key["QUIET_HOURS_START_ET"].default == "23"
    assert by_key["QUIET_HOURS_END_ET"].default == "8"
    assert by_key["EXTENDED_HOURS_DEBOUNCE_TICKS"].default == "2"

    assert isinstance(config.EXTENDED_HOURS_EXIT_CHECK, bool)
    assert isinstance(config.QUIET_HOURS_START_ET, int)
    assert isinstance(config.QUIET_HOURS_END_ET, int)
    assert isinstance(config.EXTENDED_HOURS_DEBOUNCE_TICKS, int)

    assert by_key["EXTENDED_HOURS_EXIT_CHECK"].section == "Plan Engine v2"
```

The assertions are on the **schema default and the cast type**, not on the
live module value, deliberately: this file's `test_v55_batch_fetch_fields_...`
sets the same precedent, and a dev machine whose `.env` overrides a field
must not turn the suite red.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_flags.py -k v70 -v`
Expected: FAIL with `KeyError: 'EXTENDED_HOURS_EXIT_CHECK'`.

- [ ] **Step 3: Add the four fields**

In `swingbot/config.py`, directly after the `INTRADAY_RTH_ONLY` `Field(...)`
entry (its help string ends `"Set false only to reproduce pre-v64 behaviour."`)
and before the `# --- Data sources` comment, insert:

```python
    Field("EXTENDED_HOURS_EXIT_CHECK", "EXTENDED_HOURS_EXIT_CHECK", "Plan Engine v2",
          "Close on stop/target hits during premarket and after-hours", type="checkbox",
          default="true",
          help="Outside regular hours but outside the quiet window below, check open plans "
               "for a confirmed stop-loss or final-target hit and close immediately -- no "
               "break-even arming, TP1 partial-banking or trailing-stop updates outside "
               "regular hours, only a terminal close. Set false to reproduce pre-v70 "
               "behaviour (fully dark outside 09:30-16:00 ET)."),
    Field("QUIET_HOURS_START_ET", "QUIET_HOURS_START_ET", "Plan Engine v2",
          "Quiet hours start (ET, 24h)", type="number", default="23", min=0, max=23, step=1,
          help="No plan monitoring at all from this hour (America/New_York) through "
               "QUIET_HOURS_END_ET, and none at all on Saturday/Sunday."),
    Field("QUIET_HOURS_END_ET", "QUIET_HOURS_END_ET", "Plan Engine v2",
          "Quiet hours end (ET, 24h)", type="number", default="8", min=0, max=23, step=1,
          help="Extended-hours exit checks resume at this hour (America/New_York)."),
    Field("EXTENDED_HOURS_DEBOUNCE_TICKS", "EXTENDED_HOURS_DEBOUNCE_TICKS", "Plan Engine v2",
          "Extended-hours confirmation ticks", type="number", default="2", min=1, max=5, step=1,
          help="Consecutive 60s extended-hours polls that must confirm a stop/target breach "
               "before closing -- guards against a single thin premarket/after-hours print "
               "(see v64's Divergence B) triggering a close a liquid market never would have."),
```

Nothing else is needed to publish them: `_apply_env()` walks `FIELDS` and
sets one module global per entry, `_CASTERS["checkbox"]` turns `"true"` into
`True` and `_CASTERS["number"]` turns `"23"` into `23`.

- [ ] **Step 4: Add them to `.env.example`**

`tests/test_env_example_sync.py::test_every_setting_appears_in_env_example`
fails on any schema key absent from the example file. Insert directly after
the existing `INTRADAY_RTH_ONLY=true` line:

```
# Outside 09:30-16:00 ET but outside the quiet window below, close a plan on a
# confirmed stop-loss or final-target hit. Terminal closes only -- no
# break-even arming, TP1 partials or trailing updates outside regular hours.
EXTENDED_HOURS_EXIT_CHECK=true
# No plan monitoring at all between these two ET hours, nor at any hour on
# Saturday/Sunday. The window runs START -> midnight -> END.
QUIET_HOURS_START_ET=23
QUIET_HOURS_END_ET=8
# Consecutive 60s extended-hours polls that must agree before a breach closes.
EXTENDED_HOURS_DEBOUNCE_TICKS=2
```

- [ ] **Step 5: Run both tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py`
Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: green, both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_flags.py
git commit -m "feat(v70): add the extended-hours exit-check config fields"
```

---

### Task X2: `is_quiet_hours`

**Files:**
- Modify: `swingbot/core/market/session.py` (new top-level import + one function)
- Test: `tests/market/test_session.py`

**Interfaces:**
- Consumes: `config.QUIET_HOURS_START_ET`, `config.QUIET_HOURS_END_ET` (X1).
- Produces: `session.is_quiet_hours(now: datetime | None = None) -> bool`.
  X4 calls it as the first arm of `poll()`'s gate.

- [ ] **Step 1: Write the failing test**

Add `is_quiet_hours` to the existing import block at the top of
`tests/market/test_session.py`, then append:

```python
@pytest.mark.parametrize(("moment", "expected"), [
    (_et(2026, 8, 27, 22, 59), False),
    (_et(2026, 8, 27, 23, 0), True),
    (_et(2026, 8, 27, 2, 0), True),
    (_et(2026, 8, 27, 7, 59), True),
    (_et(2026, 8, 27, 8, 0), False),
    (_et(2026, 8, 27, 12, 0), False),
    (_et(2026, 8, 27, 19, 30), False),
])
def test_quiet_hours_boundaries(moment, expected):
    assert is_quiet_hours(moment) is expected


@pytest.mark.parametrize("hour", list(range(24)))
def test_every_hour_of_the_weekend_is_quiet(hour):
    assert is_quiet_hours(_et(2026, 8, 29, hour, 0)) is True   # Saturday
    assert is_quiet_hours(_et(2026, 8, 30, hour, 0)) is True   # Sunday


def test_quiet_hours_never_overlaps_the_regular_session():
    for hour, minute in ((9, 30), (12, 0), (15, 59)):
        moment = _et(2026, 8, 27, hour, minute)
        assert is_regular_session(moment) is True
        assert is_quiet_hours(moment) is False


def test_the_window_is_read_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "QUIET_HOURS_START_ET", 20)
    monkeypatch.setattr(config, "QUIET_HOURS_END_ET", 6)
    assert is_quiet_hours(_et(2026, 8, 27, 19, 59)) is False
    assert is_quiet_hours(_et(2026, 8, 27, 20, 0)) is True
    assert is_quiet_hours(_et(2026, 8, 27, 5, 59)) is True
    assert is_quiet_hours(_et(2026, 8, 27, 6, 0)) is False


def test_a_utc_input_is_converted_before_the_window_is_applied():
    # 2026-08-28 02:00 UTC is 2026-08-27 22:00 ET -- a Thursday evening, one
    # hour before the window opens, not the small hours of Friday morning.
    utc = dt.datetime(2026, 8, 28, 2, 0, tzinfo=dt.timezone.utc)
    assert is_quiet_hours(utc) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/market/test_session.py -k quiet -v`
Expected: FAIL at import — `ImportError: cannot import name 'is_quiet_hours'`.

- [ ] **Step 3: Implement it**

In `swingbot/core/market/session.py`, add the config import to the header
(the module imports stdlib only today):

```python
import datetime as dt
from zoneinfo import ZoneInfo

from swingbot import config
```

and append after `is_regular_session`:

```python
def is_quiet_hours(now: dt.datetime | None = None) -> bool:
    """Return whether ``now`` falls in the overnight window the v70
    extended-hours exit check never runs in: ``config.QUIET_HOURS_START_ET``
    through ``config.QUIET_HOURS_END_ET`` ET, plus every hour of Saturday
    and Sunday -- a market that is fully shut all weekend.

    The bounds are read from ``config`` rather than passed in, the same way
    ``plan_manager`` already reads ``config.INTRADAY_RTH_ONLY`` directly.
    The window always runs START -> midnight -> END, so a START earlier than
    END (e.g. 8 and 23) means "quiet all day" and switches plan monitoring
    off entirely. That is the honest reading of an inverted window, not a
    bug to special-case.
    """
    et = now_et(now)
    if et.weekday() >= 5:
        return True
    start = dt.time(config.QUIET_HOURS_START_ET, 0)
    end = dt.time(config.QUIET_HOURS_END_ET, 0)
    t = et.time()
    return t >= start or t < end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_session.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/session.py tests/market/test_session.py
git commit -m "feat(v70): add is_quiet_hours to the session calendar"
```

---

# Phase 2 — The extended-hours exit path

## Parallelisation

**Sequential throughout: X3 → X4 → X5.** X3 and X4 both edit
`swingbot/core/planning/plan_manager.py` and X4 calls the method X3
introduces; X5 edits that same file again. Concurrent sessions share this
working tree, so two agents on `plan_manager.py` silently overwrite each
other. X6 (Phase 3, documentation only) is the one task that may run
alongside X5 — disjoint files, and docs describe behaviour rather than
consume a symbol.

All three tasks share one new test file,
`tests/planning/test_plan_manager_extended_hours.py`. X3 creates it with the
module header below; X4 and X5 append to it.

---

### Task X3: `_step_extended` and the two breach candidates

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:135` (one new dict in `__init__`)
- Modify: `swingbot/core/planning/plan_manager.py:391` (three new methods, after `_close_runner`)
- Test: `tests/planning/test_plan_manager_extended_hours.py` (create)

**Interfaces:**
- Consumes: `config.EXTENDED_HOURS_DEBOUNCE_TICKS` (X1); the existing
  `self._active_stop(plan, now) -> (float, bool)`, `self._close_runner(plan,
  fill, reason, risk, sign) -> list[PlanEvent]`, `runner_floor(entry, tp1)`,
  `session_date(now)`, `record_transition(plan, PlanStatus.CLOSED, reason=,
  at=)`.
- Produces: `PlanManager._eh_breach_streak: dict[str, tuple[str, int]]`
  (plan_id → (breach kind, consecutive confirming ticks)),
  `PlanManager._step_extended(plan, price, now=None) -> list[PlanEvent]`,
  and the two private helpers
  `_extended_candidate_active(plan, price, now=None)` /
  `_extended_candidate_partial(plan, price, now=None)`, each returning
  `tuple[str, Callable[[], list[PlanEvent]]] | None`, plus
  `_close_extended(plan, price, reason) -> list[PlanEvent]` (the whole-position
  close the ACTIVE candidates hand back; the PARTIAL ones reuse the existing
  `_close_runner`). X4 calls
  `_step_extended` from `poll()`. The close reasons produced here are
  `"loss"`, `"scratch"`, `"win"`, `"tp1_runner_be"`, `"tp1_runner_trail"`
  and `"tp1_runner_tp2"`; X5 makes `"win"` land correctly downstream.

This task's tests call `_step_extended` directly. That is deliberate, not
laziness: the gate that reaches it does not exist until X4, so a test
through `poll()` here would be testing X4's work. X4 adds the through-`poll`
tests.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_plan_manager_extended_hours.py`:

```python
"""v70: extended-hours terminal exits. Injected clock, no network, no
sleeps -- the same style as the rest of tests/planning/test_plan_manager_*."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active

# 2026-08-27 is a Thursday; 08-29/08-30 are Saturday/Sunday.
PREMARKET = dt.datetime(2026, 8, 27, 8, 30, tzinfo=US_MARKET_TZ)
RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
AFTER_HOURS = dt.datetime(2026, 8, 27, 19, 30, tzinfo=US_MARKET_TZ)
QUIET = dt.datetime(2026, 8, 27, 2, 0, tzinfo=US_MARKET_TZ)
SATURDAY = dt.datetime(2026, 8, 29, 12, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _v70_defaults(monkeypatch):
    """Pin every flag this file depends on, so a dev machine's .env can
    never decide the outcome of a test."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_DEBOUNCE_TICKS", 2)
    monkeypatch.setattr(config, "QUIET_HOURS_START_ET", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_ET", 8)


def _env(tmp_path, prices=(), plan=None):
    """_active() is entry 100, stop 95, tp1 110, tp1_fraction 0.5, so risk
    is 5.00 and runner_floor(100, 110) is 106.67."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price)


def _partial_env(tmp_path, tp2=None, floor_session="2026-08-26"):
    """An ACTIVE plan walked through TP1, with the runner floor stamped to
    an EARLIER session so v64's same-session guard is satisfied."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=tp2))
    mgr = PlanManager(store, feed.get_price)
    assert [e.transition for e in mgr.poll(now=RTH)] == ["tp1_partial"]
    plan = store.get("p1")
    plan.runner_floor_session = floor_session
    store.update(plan)
    return store, mgr


def test_one_breach_tick_never_closes(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_reverting_tick_clears_the_streak_entirely(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    assert mgr._eh_breach_streak["p1"] == ("stop", 1)
    assert mgr._step_extended(plan, 99.0, AFTER_HOURS) == []   # back above the stop
    assert "p1" not in mgr._eh_breach_streak                   # popped, not decremented
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []   # counting starts over
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_two_confirming_ticks_close_at_the_second_tick_price(tmp_path):
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 93.5, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "loss"
    assert events[0].detail["exit_price"] == 93.5    # the confirming print, never 95.0
    assert store.get("p1").status == PlanStatus.CLOSED
    assert "p1" not in mgr._eh_breach_streak


def test_a_break_even_stop_closes_as_a_scratch_from_the_next_session(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(working_stop=100.0,
                                             be_armed_session="2026-08-26"))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 99.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 99.4, AFTER_HOURS)
    assert events[0].detail["reason"] == "scratch"
    assert events[0].detail["exit_price"] == 99.4


def test_a_stop_armed_this_session_does_not_govern_extended_hours(tmp_path):
    """v64's rule, unchanged: a break-even stop governs from the session
    AFTER it armed, so the original 95.00 stop is still the live one."""
    store, mgr = _env(tmp_path, plan=_active(working_stop=100.0,
                                             be_armed_session="2026-08-27"))
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 99.4, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_tp1_with_a_tp2_still_to_run_is_inert(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(tp2=120.0))
    plan = store.get("p1")
    for _ in range(5):
        assert mgr._step_extended(plan, 111.0, AFTER_HOURS) == []
    p = store.get("p1")
    assert p.status == PlanStatus.ACTIVE
    assert p.legs_realized == []
    assert p.working_stop is None


def test_tp1_with_no_tp2_is_terminal_and_closes_as_a_win(tmp_path):
    store, mgr = _env(tmp_path, plan=_active(tp2=None))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 110.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 111.0, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "win"
    assert events[0].detail["exit_price"] == 111.0
    assert store.get("p1").status == PlanStatus.CLOSED


def test_the_break_even_trigger_never_arms_outside_regular_hours(tmp_path):
    """105.00 is the BE trigger for this plan (halfway to TP1). In RTH it
    arms a working stop; extended hours must leave the plan untouched."""
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 105.0, AFTER_HOURS) == []
    assert store.get("p1").working_stop is None


def test_a_pending_plan_never_moves_on_an_extended_hours_tick(tmp_path):
    store, mgr = _env(tmp_path, plan=_plan())      # PENDING, trigger 100
    plan = store.get("p1")
    for price in (101.0, 101.0, 101.0, 90.0, 90.0):
        assert mgr._step_extended(plan, price, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.PENDING


def test_a_runner_stop_closes_at_the_floor_reason(tmp_path):
    store, mgr = _partial_env(tmp_path)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 106.0, AFTER_HOURS) == []    # floor is 106.67
    events = mgr._step_extended(plan, 105.5, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == 105.5
    p = store.get("p1")
    assert p.status == PlanStatus.CLOSED
    assert len(p.legs_realized) == 2


def test_a_runner_closes_at_tp2(tmp_path):
    store, mgr = _partial_env(tmp_path, tp2=118.0)
    plan = store.get("p1")
    assert mgr._step_extended(plan, 118.5, AFTER_HOURS) == []
    events = mgr._step_extended(plan, 119.0, AFTER_HOURS)
    assert events[0].detail["reason"] == "tp1_runner_tp2"
    assert events[0].detail["exit_price"] == 119.0


def test_the_runner_floor_is_inert_in_its_own_session(tmp_path):
    store, mgr = _partial_env(tmp_path, floor_session="2026-08-27")
    plan = store.get("p1")
    for _ in range(4):
        assert mgr._step_extended(plan, 100.0, AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.PARTIAL


def test_the_trailing_ratchet_never_runs_outside_regular_hours(tmp_path):
    """_step_extended takes no atr_fn path at all: a new extreme must not
    move working_stop, whatever the ATR would have said."""
    store, mgr = _partial_env(tmp_path)
    mgr.atr_fn = lambda ticker: 2.0
    plan = store.get("p1")
    before = store.get("p1").working_stop
    assert mgr._step_extended(plan, 115.0, AFTER_HOURS) == []
    assert store.get("p1").working_stop == before
    assert store.get("p1").runner_high_close is None


def test_a_different_breach_cannot_finish_another_ones_streak(tmp_path):
    """The generalisation of the spec's pop-don't-decrement rule: a stop
    tick and a target tick are different breaches, so the second starts its
    own count rather than completing the first's."""
    store, mgr = _env(tmp_path, plan=_active(tp2=None))
    plan = store.get("p1")
    assert mgr._step_extended(plan, 94.0, AFTER_HOURS) == []     # stop, streak 1
    assert mgr._step_extended(plan, 111.0, AFTER_HOURS) == []    # tp1, streak 1 again
    assert mgr._eh_breach_streak["p1"] == ("tp1", 1)
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_the_debounce_count_is_read_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXTENDED_HOURS_DEBOUNCE_TICKS", 1)
    store, mgr = _env(tmp_path)
    plan = store.get("p1")
    events = mgr._step_extended(plan, 94.0, AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/planning/test_plan_manager_extended_hours.py -x -q`
Expected: FAIL with `AttributeError: 'PlanManager' object has no attribute '_step_extended'`.

- [ ] **Step 3: Add the debounce map to `__init__`**

In `swingbot/core/planning/plan_manager.py`, directly after
`self._last_seen: dict[str, tuple[str, float]] = {}`:

```python
        # v70: plan_id -> (breach kind, consecutive confirming extended-hours
        # ticks). In-memory only, for the same reason _last_seen is: persisting
        # it would turn every 60s poll into a disk write where only a
        # transition writes today. A restart empties it, so the first tick
        # after a restart always needs a fresh confirmation -- the
        # conservative direction.
        self._eh_breach_streak: dict[str, tuple[str, int]] = {}
```

- [ ] **Step 4: Add the three methods**

Append to `PlanManager`, directly after `_close_runner` and before the
`# -- overnight/session-open bar check (Task 67)` comment block:

```python
    # -- extended-hours terminal exits (v70) --------------------------------
    #
    # Reached only from poll()'s extended-hours branch: RTH gate on, clock
    # outside 09:30-16:00 ET, outside quiet hours. The ONLY outcome this
    # path can produce is a terminal close of a plan that has unambiguously
    # finished -- no pending fills, no break-even arming, no TP1 partial
    # while a tp2 remains, no chandelier ratchet. Everything else stays
    # where v64 put it: regular hours only.

    def _step_extended(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
        if plan.status == PlanStatus.ACTIVE:
            candidate = self._extended_candidate_active(plan, price, now)
        elif plan.status == PlanStatus.PARTIAL:
            candidate = self._extended_candidate_partial(plan, price, now)
        else:
            candidate = None            # PENDING (and anything else): inert
        key = plan.plan_id
        if candidate is None:
            # Pop, never decrement: one reverting print resets the count
            # completely rather than leaving a partial streak a later,
            # unrelated breach could complete early.
            self._eh_breach_streak.pop(key, None)
            return []
        kind, close = candidate
        seen_kind, streak = self._eh_breach_streak.get(key, (None, 0))
        streak = streak + 1 if seen_kind == kind else 1
        if streak < config.EXTENDED_HOURS_DEBOUNCE_TICKS:
            self._eh_breach_streak[key] = (kind, streak)
            return []
        self._eh_breach_streak.pop(key, None)
        return close()

    def _extended_candidate_active(self, plan: TradePlanV2, price: float, now=None):
        """(kind, close) for an ACTIVE plan that has finished, else None.

        Mirrors _step_active's stop and TP1 comparisons exactly -- including
        _active_stop's session guard -- but returns a callable instead of
        acting, so the debounce lives in one place rather than per branch."""
        is_bull = plan.direction == "bullish"
        stop, is_be_stop = self._active_stop(plan, now)
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = "scratch" if is_be_stop else "loss"
            return ("stop", lambda: self._close_extended(plan, price, reason))
        if plan.tp2 is not None:
            # TP1 with a second leg still to run is a PARTIAL transition,
            # not a finish -- and banking a partial is regular-hours work.
            return None
        hit_tp1 = price >= plan.tp1 if is_bull else price <= plan.tp1
        if hit_tp1:
            return ("tp1", lambda: self._close_extended(plan, price, "win"))
        return None

    def _extended_candidate_partial(self, plan: TradePlanV2, price: float, now=None):
        """(kind, close) for a PARTIAL plan whose runner has finished, else
        None. Mirrors _step_partial's stop and TP2 comparisons, including
        v64's runner_floor_session guard; the pyramid suggestion and the
        chandelier ratchet are deliberately absent."""
        if plan.runner_floor_session == session_date(now):
            return None
        is_bull = plan.direction == "bullish"
        sign = 1 if is_bull else -1
        entry = plan.entry_price
        risk = abs(entry - plan.stop_loss)
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(entry, plan.tp1))
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return ("stop",
                    lambda: self._close_runner(plan, price, reason, risk, sign))
        if plan.tp2 is not None:
            hit_tp2 = price >= plan.tp2 if is_bull else price <= plan.tp2
            if hit_tp2:
                return ("tp2", lambda: self._close_runner(
                    plan, price, "tp1_runner_tp2", risk, sign))
        return None

    def _close_extended(self, plan: TradePlanV2, price: float,
                        reason: str) -> list[PlanEvent]:
        """Terminal close of a whole (pre-TP1) position at the confirming
        tick's price. Fills at `price`, never at the nominal level: the same
        "never record a better fill than what was actually seen" convention
        performance.py and trade_monitor already use. _on_event synthesizes
        the fraction=1.0 leg from the plan's own entry/stop."""
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=self._now())
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "closed",
                          {"reason": reason, "exit_price": price})]
```

`runner_floor` is already imported at the top of the module (the
`from swingbot.core.planning.plan_engine import (...)` block), as are
`session_date`, `record_transition` and `PlanStatus` — no import changes.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_extended_hours.py`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_extended_hours.py
git commit -m "feat(v70): add the debounced extended-hours terminal-exit step"
```

---

### Task X4: The three-way gate in `poll()`

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:140-142` (the gate) and `:173` (the `_last_seen` write)
- Test: `tests/planning/test_plan_manager_extended_hours.py` (append)

**Interfaces:**
- Consumes: `is_quiet_hours` (X2), `config.EXTENDED_HOURS_EXIT_CHECK` (X1),
  `self._step_extended` (X3).
- Produces: nothing new. `poll()` keeps its signature and its
  `list[PlanEvent]` return.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_plan_manager_extended_hours.py`:

```python
def test_two_after_hours_polls_close_the_plan(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5])
    assert mgr.poll(now=AFTER_HOURS) == []
    events = mgr.poll(now=AFTER_HOURS)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 93.5
    assert store.get("p1").status == PlanStatus.CLOSED


def test_premarket_polls_close_the_plan_too(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5])
    assert mgr.poll(now=PREMARKET) == []
    assert [e.transition for e in mgr.poll(now=PREMARKET)] == ["closed"]


def test_quiet_hours_are_fully_dark(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5, 93.0, 92.5])
    for _ in range(4):
        assert mgr.poll(now=QUIET) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_the_whole_weekend_is_fully_dark(tmp_path):
    store, mgr = _env(tmp_path, [94.0, 93.5])
    assert mgr.poll(now=SATURDAY) == []
    assert mgr.poll(now=SATURDAY) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_the_flag_off_reproduces_the_pre_v70_two_way_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", False)
    store, mgr = _env(tmp_path, [94.0, 93.5, 93.0])
    for _ in range(3):
        assert mgr.poll(now=AFTER_HOURS) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_rth_only_off_still_runs_the_full_machine_round_the_clock(tmp_path, monkeypatch):
    """The pre-v64 escape hatch is untouched: with INTRADAY_RTH_ONLY off an
    overnight tick takes the FULL _step branch -- one tick, no debounce --
    and the quiet window never applies."""
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _env(tmp_path, [94.0])
    assert [e.transition for e in mgr.poll(now=QUIET)] == ["closed"]


def test_regular_hours_still_arm_break_even(tmp_path):
    store, mgr = _env(tmp_path, [105.0])
    assert [e.transition for e in mgr.poll(now=RTH)] == ["be_moved"]
    assert store.get("p1").working_stop == 100.0


def test_an_extended_hours_tick_never_makes_the_next_rth_fill_continuous(tmp_path):
    """poll() records _last_seen on the REGULAR branch only. Otherwise an
    08:30 print above the stop would tell the 09:30 poll it had watched the
    tape cross, and v64's poll_stop_fill would fill the gap-down AT the stop
    -- a better price than anything that ever printed."""
    store, mgr = _env(tmp_path, [99.0, 94.0])
    assert mgr.poll(now=PREMARKET) == []          # above the stop: no candidate
    assert "p1" not in mgr._last_seen
    events = mgr.poll(now=RTH)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["exit_price"] == 94.0    # the gap price, not 95.00


def test_a_price_failure_on_one_plan_does_not_stop_the_others(tmp_path):
    """poll()'s existing per-plan isolation still holds on the new branch."""
    feed = FakePriceFeed()
    feed.set_series("MSFT", [94.0, 93.5])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())                                  # AAPL: no ticks queued
    store.add(_active(plan_id="p2", ticker="MSFT"))
    mgr = PlanManager(store, feed.get_price)
    assert mgr.poll(now=AFTER_HOURS) == []
    events = mgr.poll(now=AFTER_HOURS)
    assert [(e.plan_id, e.transition) for e in events] == [("p2", "closed")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/planning/test_plan_manager_extended_hours.py -k "after_hours or premarket or quiet or weekend" -x -q`
Expected: FAIL — `assert [] == ["closed"]`: today's two-way gate still
returns `[]` for every non-RTH tick.

- [ ] **Step 3: Replace the gate**

In `swingbot/core/planning/plan_manager.py`, replace

```python
        if config.INTRADAY_RTH_ONLY and not is_regular_session(now):
            return []
```

with

```python
        # Three-way gate (v70). INTRADAY_RTH_ONLY=false is the documented
        # pre-v64 escape hatch -- full _step() every tick, round the clock,
        # and no quiet-hours gate either: the quiet window only ever applies
        # ON TOP OF the RTH gate, never independently of it.
        if config.INTRADAY_RTH_ONLY:
            if is_quiet_hours(now):
                return []
            regular = is_regular_session(now)
            if not regular and not config.EXTENDED_HOURS_EXIT_CHECK:
                return []
        else:
            regular = True
```

and update the session import at the top of the module:

```python
from swingbot.core.market.session import (is_quiet_hours, is_regular_session,
                                          session_date)
```

- [ ] **Step 4: Route the tick and gate the `_last_seen` write**

Inside `poll()`'s per-plan loop, replace

```python
            try:
                new_events = self._step(plan, price, now)
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
            self._last_seen[plan.plan_id] = (session_date(now), price)
```

with

```python
            try:
                new_events = (self._step(plan, price, now) if regular
                              else self._step_extended(plan, price, now))
            except Exception:
                log.warning("poll: step failed for plan %s", plan.plan_id,
                            exc_info=True)
                continue
            if regular:
                # Regular-hours prints only. _last_seen feeds _continuous(),
                # which lets a stop breach fill AT the stop rather than at
                # the observed price -- claiming we watched the tape cross.
                # An extended-hours print is exactly what we did not watch:
                # letting one in here would fill the next session's gap-down
                # at a price that never traded. (v70; see the plan's finding 2.)
                self._last_seen[plan.plan_id] = (session_date(now), price)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_extended_hours.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_session.py`
Expected: green, both. The second is the v64 gate suite — it must still pass
untouched, including `test_flag_off_restores_round_the_clock_behaviour`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_extended_hours.py
git commit -m "feat(v70): gate poll() three ways -- quiet, regular, extended"
```

---

### Task X5: A terminal target hit is recorded and posted as a win

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:202-203` (`_on_event`'s reason→status map)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py:289-300` (`PLAN_EVENT_STYLES`)
- Test: `tests/planning/test_plan_manager_extended_hours.py` (append)
- Test: `tests/scanning/test_transition_embeds.py` (append)

**Interfaces:**
- Consumes: the `"win"` close reason X3 introduced.
- Produces: nothing new. It makes two existing lookups recognise `"win"`:
  `TradeLog.close_plan_trade(..., status="win")` instead of `"closed"`, and a
  green "Win" embed instead of the neutral fallback.

This is finding 1. Without it the feature still *closes* the plan, so no test
in X3 or X4 catches it — the damage is downstream, in the trade record's
status (which every win-rate and expectancy number is computed from) and in
the Discord post the user actually reads.

- [ ] **Step 1: Write the failing tests**

Append to `tests/planning/test_plan_manager_extended_hours.py`:

```python
class _RecordingLog:
    """Minimal TradeLog stand-in: PlanManager._on_event only ever calls
    reload() and close_plan_trade() on a terminal close."""

    def __init__(self):
        self.closed = []

    def reload(self):
        pass

    def close_plan_trade(self, plan_id, leg, status):
        self.closed.append((plan_id, leg, status))


def test_a_terminal_target_close_reaches_the_trade_log_as_a_win(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5, 111.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=None))
    trade_log = _RecordingLog()
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    assert mgr.poll(now=AFTER_HOURS) == []
    assert [e.transition for e in mgr.poll(now=AFTER_HOURS)] == ["closed"]

    plan_id, leg, status = trade_log.closed[0]
    assert (plan_id, status) == ("p1", "win")
    assert leg["fraction"] == 1.0
    assert leg["exit_price"] == 111.0
    assert leg["r"] == pytest.approx((111.0 - 100.0) / 5.0)


def test_a_terminal_stop_close_still_reaches_the_trade_log_as_a_loss(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [94.0, 93.5])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    trade_log = _RecordingLog()
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log)

    assert mgr.poll(now=AFTER_HOURS) == []
    assert [e.transition for e in mgr.poll(now=AFTER_HOURS)] == ["closed"]
    assert trade_log.closed[0][2] == "loss"
```

Append to `tests/scanning/test_transition_embeds.py`:

```python
def test_a_terminal_target_close_reads_as_a_win():
    """v70: an ACTIVE plan with no tp2 closes with reason 'win'. Without a
    style row it would post the neutral 'Plan closed' fallback."""
    e = _embed("closed", {"reason": "win", "exit_price": 111.0})
    assert "Win" in e.title and "🟢" in e.title
    assert any("111" in (f.value or "") for f in e.fields)
    assert PLAN_EVENT_STYLES["win"][1].value == tokens.ACCENT_RAMP[5]
```

and extend the existing `test_close_reasons_have_distinct_copy` in the same
file to cover the sixth reason — every close reason the manager can emit has
its own copy, and `"win"` is now one of them:

```python
def test_close_reasons_have_distinct_copy():
    titles = {r: _embed("closed", {"reason": r, "exit_price": 100.0}).title
              for r in ("loss", "scratch", "win", "tp1_runner_be",
                        "tp1_runner_tp2", "tp1_runner_trail")}
    assert len(set(titles.values())) == 6
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/planning/test_plan_manager_extended_hours.py -k trade_log -q`
Expected: FAIL — `assert ('p1', 'closed') == ('p1', 'win')`.

Run: `python -m pytest tests/scanning/test_transition_embeds.py -k terminal_target -q`
Expected: FAIL with `KeyError: 'win'`.

- [ ] **Step 3: Teach `_on_event` the reason**

In `swingbot/core/planning/plan_manager.py`, inside `_on_event`'s
`elif event.transition == "closed":` branch, replace

```python
                status = ("win" if reason.startswith("tp1_")
                          else "loss" if reason == "loss" else "closed")
```

with

```python
                # "win" is v70's terminal-target reason: an ACTIVE plan with
                # no tp2 whose tp1 was confirmed outside regular hours closes
                # the whole position at its last remaining target.
                status = ("win" if reason == "win" or reason.startswith("tp1_")
                          else "loss" if reason == "loss" else "closed")
```

- [ ] **Step 4: Add the embed style row**

In `swingbot/core/scanning/lifecycle_embeds.py`, add to `PLAN_EVENT_STYLES`,
directly after the `"scratch"` row:

```python
    "win":                   ("🟢 Win — target hit — {ticker}", _GOOD),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_extended_hours.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: green, both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/core/scanning/lifecycle_embeds.py tests/planning/test_plan_manager_extended_hours.py tests/scanning/test_transition_embeds.py
git commit -m "fix(v70): record and post a terminal target close as a win"
```

---

# Phase 3 — Documentation, verification, release

## Parallelisation

**X6 may run alongside X5** (documentation files only; no shared file with
any code task, and it consumes no symbol). **X7 is last and alone** — it is
the plan's single full-suite run and its release commit.

---

### Task X6: Record what is now live outside regular hours

**Files:**
- Modify: `docs/claude/architecture.md:56` (the Plan Engine v2 invariant sentence)
- Modify: `docs/claude/known-traps.md` (append a section)
- Modify: `.codex/AGENTS.md` (only if it repeats the RTH claim)

The trap being recorded is real and this repo's own shape: after v70 there
are **two** live exit paths with different powers, and the narrow one is easy
to forget. A rule added only to `_step_active` now silently does not apply
for ~17 hours a day.

- [ ] **Step 1: Extend the architecture invariant sentence**

In `docs/claude/architecture.md`, the Plan Engine v2 bullet currently ends
the invariant sentence with "...and v64 fixed extended-hours prints,
sampled-tick stop fills, and same-session moved stops. Any new live-path exit
rule must name the simulator line it matches." Append, in the same paragraph:

```markdown
  v70 then reopened exactly one capability outside those hours: `poll()` gates
  three ways (quiet window → nothing; regular → the full `_step()`; otherwise
  → `_step_extended()`), and the extended branch may only close a plan that
  has finished — a confirmed stop breach, or the last remaining target — after
  `EXTENDED_HOURS_DEBOUNCE_TICKS` consecutive polls agree. Break-even arming,
  TP1 partials, the chandelier ratchet and pending fills stay regular-hours
  only, so the simulator still has nothing to match outside 09:30–16:00 ET.
```

- [ ] **Step 2: Add the known-traps section**

Append to `docs/claude/known-traps.md`:

```markdown
## There are two live exit paths, and the extended-hours one is narrow

Since v70, `PlanManager.poll()` routes a tick three ways:

| Clock (with `INTRADAY_RTH_ONLY` on) | Path | What it may do |
|---|---|---|
| Quiet window (`QUIET_HOURS_START_ET`–`QUIET_HOURS_END_ET` ET, all weekend) | none | nothing at all |
| Mon–Fri 09:30–16:00 ET | `_step()` | the whole state machine |
| Everything else | `_step_extended()` | close a finished plan, nothing else |

`_step_extended` deliberately implements **only** terminal exits: a confirmed
stop/break-even-stop breach, an ACTIVE plan's `tp1` when there is no `tp2`
left, a PARTIAL runner's floor/trail stop or `tp2`. It arms no break-even
stop, banks no TP1 partial, moves no chandelier trail, fills no PENDING
trigger, and emits no pyramid suggestion — every one of those would act on a
thin premarket print, which is the bug (`v64`'s "Divergence B") the RTH gate
exists to prevent.

**The trap:** an exit rule added only to `_step_active`/`_step_partial` is
inert for the ~17.5 hours a day and the whole weekend that the extended
branch covers, and one added only to `_step_extended` never runs during the
session. Decide which it is, and say so in the code. If a new rule is
genuinely terminal, mirror it into `_extended_candidate_active` /
`_extended_candidate_partial`; if it manages a still-open position, it
belongs in `_step*` only.

Two more properties worth knowing before editing this path:

- **The debounce map (`_eh_breach_streak`) is in-memory and keyed by breach
  kind.** A restart empties it, so the first extended tick after a restart
  always needs a fresh confirming tick. A reverting print pops the entry
  outright rather than decrementing it.
- **`poll()` records `_last_seen` on the regular branch only.** That map
  feeds `_continuous()`, which lets a stop fill *at the stop* instead of at
  the observed price. An extended-hours print is precisely the case where
  nobody watched the tape cross, so admitting one there would fill the next
  session's gap-down at a price that never traded.
```

- [ ] **Step 3: Mirror into the Codex agent file if it repeats the claim**

Run: `grep -n "RTH\|regular hours\|INTRADAY_RTH_ONLY" .codex/AGENTS.md`

If it states that plans are managed during regular hours only, condense Step
1's correction into one sentence there. The sync is one-way — a Claude
session updates `.codex/AGENTS.md`, never the reverse. If it does not mention
it, change nothing and say so in the commit body.

- [ ] **Step 4: Commit**

```bash
git add docs/claude/architecture.md docs/claude/known-traps.md .codex/AGENTS.md
git commit -m "docs(v70): record the three-way poll gate and the narrow extended path"
```

---

### Task X7: Full-suite verification, version bump, close-out

- [ ] **Step 1: Run the full suite once**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner`
subagent so ~1150 progress lines stay out of the session context.

Expected: `0 failed`, `0 xfailed`. A *changed pass count* is not a failure —
this plan adds roughly 45 tests (the weekend parametrisation alone is 24).

**If it is not green, fix forward from those failures.** They are this plan's
regressions. The two likely shapes, both of which mean a real bug rather than
a stale test:

- A `plan_manager` test that polls with **no** `now=` argument and a wall
  clock that happens to sit in the quiet window or the weekend — those tests
  now return `[]` where they used to act. Fix by injecting the clock the test
  meant (`now=RTH`), never by widening the quiet window.
- A test asserting on `PLAN_EVENT_STYLES`'s size or on every close reason's
  copy. Extend it to include `"win"`; do not delete the assertion.

- [ ] **Step 2: Bump the bot version**

Edit `VERSION.json`: `bot` `1.5.2` → `1.6.0`, and set `bot_updated` to the
current UTC timestamp in the existing `YYYY-MM-DD HH-MM-SS` format. Leave
`ui` and `ui_updated` untouched — no file under `frontend/` changed.

Minor, not patch, on the observable-difference test: a stop or target
breached at 20:00 ET now closes the plan and posts a Discord alert that same
evening, where before the position sat open until the next morning's first
regular-hours poll. That is a different product for whoever holds the
position overnight, which is the test — not the size of the diff.

- [ ] **Step 3: Commit the bump, then regenerate version history**

The generator walks `git log` for `VERSION.json`, so the bump must already be
committed or it records a `"working tree"` placeholder:

```bash
git add VERSION.json
git commit -m "release(bot): 1.6.0 -- extended-hours stop/target exits"
python scripts/dev/build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): 1.6.0 -- extended-hours stop/target exits"
```

The local gate ran *before* the bump and structurally cannot catch a missed
regeneration, so confirm it yourself:

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: green (`test_the_committed_file_matches_the_current_generator`).

- [ ] **Step 4: Close the plan out**

Move both documents to `implemented/`:

```bash
git mv docs/superpowers/specs/2026-09-03-v70-extended-hours-exit-check-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-03-v70-extended-hours-exit-check.md docs/superpowers/plans/implemented/
git commit -m "docs(v70): close out the extended-hours exit check"
```

If the `Bump:` or `Edge:` prediction in either header came out wrong, amend
the line in this commit and add one clause saying why. A wrong prediction
recorded is worth more than a right one hidden.

---

## Success criteria

1. A plan whose stop is breached at 19:30 ET closes on the second confirming
   60s poll, at that poll's price, and posts the same Discord embed an
   RTH close posts. The §1.1 incident (DDOG, exit 4.2% past the stop after an
   overnight blackout) becomes a close near the breach instead.
2. Between 23:00 and 08:00 ET, and for every hour of Saturday and Sunday,
   `poll()` returns `[]` without fetching a price.
3. `EXTENDED_HOURS_EXIT_CHECK=false` reproduces pre-v70 behaviour exactly,
   and `INTRADAY_RTH_ONLY=false` reproduces pre-v64 behaviour exactly. Both
   are asserted, not assumed.
4. Nothing but a terminal close can happen outside regular hours: no
   break-even arming, no TP1 partial while a `tp2` remains, no trailing
   ratchet, no PENDING fill or invalidation.
5. A terminal target close is recorded as `status="win"` in `trades.json` and
   posted as a green "Win" embed.
6. `python scripts/dev/testrun.py full` is `0 failed`, `0 xfailed`.

## Post-plan: what ships, and what it does not claim

**Nothing to change on production's `.env`.** All four fields have defaults,
and `_apply_env()` falls back to the schema default for any key the file does
not set — so deploying the image is the whole rollout, and the check is on
from the first tick after restart. To ship it off instead, add
`EXTENDED_HOURS_EXIT_CHECK=false` to the VM's `.env` and SIGHUP; both flags
are hot-reloadable.

**No expectancy claim, and none is measurable from this.** Capping how far
past a stop a position can run should raise realised expectancy against
today's overnight blackout, but the backtest reads regular-hours daily bars
and cannot score an extended-hours fill at all — there is no simulator
counterpart to compare against and no pre-registration this could settle.
`Edge: none (integrity)` is the honest line, and the first place this will
show up as a number is the live paper-trade record, not a backtest.

**The accepted limitations, unchanged from v64 §4.1:** no holiday or half-day
calendar (a holiday's stale last price is idempotent against this check the
same way it is against the RTH one), and one price sample per plan per 60s
tick rather than a bar — a spike between polls is still missed, and now
missed in extended hours too.
