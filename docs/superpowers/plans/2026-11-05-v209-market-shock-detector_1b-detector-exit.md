# v209 — Market-shock detector, part 1b: exit, second leg and overnight carry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md)
**Index:** [`2026-11-05-v209-market-shock-detector_0-index.md`](2026-11-05-v209-market-shock-detector_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly carries the index's Global Constraints.

Part 1 (`_1-detector-core.md`, V209-1..V209-3) reached the 1500-line file cap,
so V209-4 lives here; it is still ledger part 1 and runs straight after
V209-3 on the same branch. Do not commit on `main`: the commit step runs on
the plan's worktree branch.

# Phase 2 — the pure detector (continued)

### Task V209-4: `shock.py`: SHOCK → RECOVERY → NORMAL, second leg, overnight carry

**Model:** sonnet — two more table-driven rules with dwell and hold clocks and a cheap re-entry; pure code whose cases the tests enumerate.

**Files:**
- Modify: `swingbot/core/market/shock.py` (append `recovery_condition`, `reentry_condition`, `_from_shock`, `_from_recovery`; replace the `RULES` line)
- Create: `tests/market/test_shock_step_exit.py`

**Interfaces:**
- Consumes (V209-2/2b/3): `ShockState`, `ShockReading`, `ShockThresholds`, `measure`, `step`, `RULES`, `_EPS`, `_meets`, `_settled`, `_enter_shock`, `_carry`, `NameRow`, `ShockSnapshot`, `VixTape`.
- Produces: `recovery_condition(state, reading, th=ShockThresholds()) -> bool`; `reentry_condition(state, reading, th=ShockThresholds()) -> bool`; `RULES["SHOCK"] = _from_shock`, `RULES["RECOVERY"] = _from_recovery` (complete). `ShockState.session_date` / `vix_session_high` / `spy_prev_close` / `prev_breadth` carried as V209-3's `_carry` already does. V209-6 calls only `measure` and `step`; V210-2 (plan v210) compares `prior.label` with `new.label`.

Rules (spec § State machine; index Global Constraints):

- **Repaired** (one reading): `breadth_frac ≤ breadth_exit`; VIX clause —
  `vix_off_high_pct ≥ recovery_vix_off_high_pct` **or** `vix_chg_pct < 0`
  (below the prior close, since prior = `price / (1 + chg/100)`); missing
  VIX leaves the clause unmet; `spy_retrace ≥ recovery_spy_retrace`
  (`None`, i.e. no SPY, leaves it unmet so RECOVERY waits).
- `recovery_condition`: repaired, and for a **SHOCK** state also
  `min_dwell_min` elapsed since `state.since` (wall-clock, so overnight
  counts: a gap-up repair reaches RECOVERY on the new session's first reading).
- **SHOCK**: `recovery_condition` ⇒ RECOVERY with `since = hold_since =
  reading.as_of`; otherwise unchanged.
- `reentry_condition` (RECOVERY → SHOCK, one reading): the reading is
  settled (open-settle rule) **and** either breadth `≥ breadth_reenter` and
  strictly above `state.prev_breadth` (which `_carry` cleared on a new
  session), or `spy_new_low` (which `measure` sets only after an earlier
  same-session reading).
- **RECOVERY**: re-entry first ⇒ SHOCK (`since = as_of`); else a reading
  that is not repaired sets `hold_since = None` and stays RECOVERY; else the
  hold starts (or continues) and, once `recovery_min_dwell_min` has held,
  ⇒ NORMAL (`since = as_of`, `hold_since = None`). `_carry` restarts the
  hold on a new session, so the overnight gap never counts as holding.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_shock_step_exit.py`:

```python
"""v209 shock.step: SHOCK -> RECOVERY -> NORMAL, second leg, overnight carry."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (NameRow, ShockReading, ShockSnapshot, ShockState,
                                        ShockThresholds, VixTape, measure, recovery_condition,
                                        reentry_condition, step)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET, 60 min after the open
D0 = date(2026, 11, 5)
D1 = date(2026, 11, 6)
OPEN_D1 = datetime(2026, 11, 6, 14, 30, tzinfo=UTC)      # 09:30 ET
TH = ShockThresholds()
REPAIRED = dict(breadth_frac=0.20, vix_off_high_pct=5.0, spy_retrace=0.5)


def _reading(at=0, **over):
    base = dict(
        as_of=T0 + timedelta(minutes=at), session_date=D0, minutes_since_open=60.0 + at,
        breadth_frac=0.05, sectors_down=0, sectors_total=5, breadth_speed=None,
        spy_atr_move=0.0, qqq_atr_move=None, spy_last=500.0, spy_prev_close=500.0,
        spy_session_low=500.0, spy_new_low=False, spy_retrace=1.0, vix_level=16.0,
        vix_chg_pct=0.0, vix_session_high=16.0, vix_off_high_pct=0.0, n_names=30,
        insufficient=False)
    base.update(over)
    return ShockReading(**base)


def _day1(minutes, **over):
    """A reading `minutes` after the 2026-11-06 open."""
    return _reading(as_of=OPEN_D1 + timedelta(minutes=minutes), session_date=D1,
                    minutes_since_open=float(minutes), **over)


def _shock(since=T0, **over):
    return ShockState(**{"label": "SHOCK", "since": since, "session_date": D0,
                         "vix_session_high": 25.0, "spy_prev_close": 500.0, **over})


def _recovery(since=T0, **over):
    return ShockState(**{"label": "RECOVERY", "since": since, "session_date": D0,
                         "vix_session_high": 25.0, "spy_prev_close": 500.0,
                         "hold_since": since, "prev_breadth": 0.20, **over})


def test_rules_are_complete():
    assert shock.RULES["SHOCK"] is shock._from_shock
    assert shock.RULES["RECOVERY"] is shock._from_recovery


def test_shock_to_recovery_once_dwelled_and_repaired():
    after = step(_shock(), _reading(45, **REPAIRED), TH)
    assert after.label == "RECOVERY"
    assert after.since == after.hold_since == T0 + timedelta(minutes=45)


def test_shock_holds_before_the_minimum_dwell():
    assert step(_shock(), _reading(44, **REPAIRED), TH).label == "SHOCK"


@pytest.mark.parametrize("over", [
    dict(breadth_frac=0.21),
    dict(vix_off_high_pct=4.9),
    dict(spy_retrace=0.49),
    dict(spy_retrace=None, spy_last=None, spy_prev_close=None, spy_session_low=None),  # no SPY frame
    dict(vix_level=None, vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None),
], ids=["breadth", "vix-off-high", "spy-retrace", "no-spy", "no-vix"])
def test_each_unmet_clause_keeps_shock(over):
    reading = _reading(60, **dict(REPAIRED, **over))
    assert recovery_condition(_shock(), reading, TH) is False
    assert step(_shock(), reading, TH).label == "SHOCK"


def test_vix_below_its_prior_close_satisfies_the_vix_clause():
    reading = _reading(60, **dict(REPAIRED, vix_off_high_pct=0.0, vix_chg_pct=-0.5))
    assert step(_shock(), reading, TH).label == "RECOVERY"


def test_hysteresis_band_holds_shock():
    after = step(_shock(), _reading(90, **dict(REPAIRED, breadth_frac=0.30)), TH)
    assert after.label == "SHOCK" and after.since == T0


def test_recovery_to_normal_after_the_hold():
    state = step(_recovery(), _reading(15, **REPAIRED), TH)
    assert state.label == "RECOVERY" and state.hold_since == T0
    state = step(state, _reading(30, **REPAIRED), TH)
    assert state.label == "NORMAL" and state.since == T0 + timedelta(minutes=30)
    assert state.hold_since is None and state.entry_streak == 0


def test_a_failing_reading_restarts_the_hold_without_leaving_recovery():
    state = step(_recovery(), _reading(15, breadth_frac=0.25), TH)
    assert state.label == "RECOVERY" and state.hold_since is None
    state = step(state, _reading(30, **REPAIRED), TH)
    assert state.hold_since == T0 + timedelta(minutes=30)
    assert step(state, _reading(59, **REPAIRED), TH).label == "RECOVERY"
    assert step(state, _reading(60, **REPAIRED), TH).label == "NORMAL"


@pytest.mark.parametrize("prev, breadth, expected", [
    (0.25, 0.30, True),
    (0.31, 0.30, False),        # falling
    (0.30, 0.30, False),        # flat is not rising
    (None, 0.40, False),        # no earlier reading this session
    (0.20, 0.29, False),        # rising but under the re-entry bar
])
def test_reentry_on_rising_breadth(prev, breadth, expected):
    state = _recovery(prev_breadth=prev)
    reading = _reading(15, breadth_frac=breadth)
    assert reentry_condition(state, reading, TH) is expected
    after = step(state, reading, TH)
    assert after.label == ("SHOCK" if expected else "RECOVERY")
    if expected:
        assert after.since == reading.as_of and after.hold_since is None


def test_reentry_on_a_new_spy_session_low_needs_one_settled_reading():
    assert step(_recovery(), _reading(15, spy_new_low=True), TH).label == "SHOCK"
    early = _reading(15, spy_new_low=True, minutes_since_open=10.0)
    assert reentry_condition(_recovery(), early, TH) is False
    assert step(_recovery(), early, TH).label == "RECOVERY"


def test_overnight_gap_up_repair_reaches_recovery_on_the_first_reading():
    yesterday_close = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)
    first = _day1(1, **dict(REPAIRED, breadth_frac=0.05, vix_off_high_pct=0.0, vix_chg_pct=-3.0,
                            spy_retrace=1.0, spy_prev_close=498.0))
    after = step(_shock(since=yesterday_close), first, TH)
    assert after.label == "RECOVERY" and after.session_date == D1
    assert after.spy_prev_close == 498.0


def test_overnight_second_leg_down_stays_shock():
    first = _day1(20, breadth_frac=0.45, sectors_down=4, spy_retrace=0.2, spy_prev_close=490.0)
    after = step(_shock(since=datetime(2026, 11, 5, 19, 0, tzinfo=UTC)), first, TH)
    assert after.label == "SHOCK" and after.session_date == D1
    assert after.spy_prev_close == 490.0


def test_overnight_recovery_hold_restarts_with_the_session():
    late = datetime(2026, 11, 5, 20, 50, tzinfo=UTC)
    after = step(_recovery(since=late), _day1(20, **REPAIRED), TH)
    assert after.label == "RECOVERY" and after.hold_since == OPEN_D1 + timedelta(minutes=20)


def test_rising_breadth_is_judged_within_the_session_only():
    state = step(_recovery(prev_breadth=0.20), _day1(30, breadth_frac=0.35), TH)
    assert state.label == "RECOVERY" and state.prev_breadth == 0.35
    assert step(state, _day1(45, breadth_frac=0.36), TH).label == "SHOCK"


def test_an_insufficient_reading_holds_shock_and_recovery():
    thin = _reading(60, **dict(REPAIRED, insufficient=True, n_names=4))
    for state in (_shock(), _recovery()):
        assert step(state, thin, TH) is state


def _snap(at, session, minutes, spy_last, spy_prev, vix):
    names = tuple(NameRow(f"F{i}", "Flat", 100.0, 100.0, 2.0, True) for i in range(20))
    return ShockSnapshot(at, session, minutes, names,
                         NameRow("SPY", None, spy_last, spy_prev, 5.0, False), None, vix)


def test_first_reading_of_a_new_session_through_measure_and_step():
    y_at = datetime(2026, 11, 5, 19, 0, tzinfo=UTC)
    yesterday = measure(_snap(y_at, D0, 270.0, 480.0, 500.0, VixTape(30.0, 40.0, y_at)), None, TH)
    t_at = OPEN_D1 + timedelta(minutes=5)
    today = measure(_snap(t_at, D1, 5.0, 505.0, 498.0, VixTape(18.0, -8.0, t_at)), yesterday, TH)
    assert today.breadth_speed is None
    assert today.vix_session_high == 18.0 and today.spy_prev_close == 498.0
    assert today.spy_session_low == 505.0 and today.spy_new_low is False
    assert step(_shock(since=y_at), today, TH).label == "RECOVERY"


def test_a_full_cycle_normal_shock_recovery_normal():
    depth = dict(breadth_frac=0.45, sectors_down=4, sectors_total=5)
    state = ShockState()
    for at, over in [(0, depth), (15, depth), (60, REPAIRED), (75, REPAIRED), (90, REPAIRED)]:
        state = step(state, _reading(at, **over), TH)
    assert state.label == "NORMAL" and state.since == T0 + timedelta(minutes=90)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_step_exit.py`
Expected: FAIL — `ImportError: cannot import name 'recovery_condition'`.

- [ ] **Step 3: Implement**

In `swingbot/core/market/shock.py`, delete the V209-3 line
`RULES: dict[str, Rule] = {NORMAL: _from_normal, SHOCK: _hold, RECOVERY: _hold}`
and the now-unused `_hold` function. Insert the following directly after
`_from_normal` (so `RULES` is defined before `step`, which reads it at call
time):

```python
def _minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60.0


def _dwelled(state: ShockState, reading: ShockReading, minimum: float) -> bool:
    return state.since is None or _minutes(state.since, reading.as_of) + _EPS >= minimum


def _vix_repaired(reading: ShockReading, th: ShockThresholds) -> bool:
    below_prior_close = reading.vix_chg_pct is not None and reading.vix_chg_pct < 0
    return below_prior_close or _meets(reading.vix_off_high_pct, th.recovery_vix_off_high_pct)


def _repaired(reading: ShockReading, th: ShockThresholds) -> bool:
    return (reading.breadth_frac is not None
            and reading.breadth_frac <= th.breadth_exit + _EPS
            and _vix_repaired(reading, th)
            and _meets(reading.spy_retrace, th.recovery_spy_retrace))


def recovery_condition(state: ShockState, reading: ShockReading,
                       th: ShockThresholds = ShockThresholds()) -> bool:
    """SHOCK -> RECOVERY (with the SHOCK dwell), or RECOVERY still holding."""
    if state.label == SHOCK and not _dwelled(state, reading, th.min_dwell_min):
        return False
    return _repaired(reading, th)


def _rising(state: ShockState, reading: ShockReading) -> bool:
    return (state.prev_breadth is not None and reading.breadth_frac is not None
            and reading.breadth_frac > state.prev_breadth + _EPS)


def reentry_condition(state: ShockState, reading: ShockReading,
                      th: ShockThresholds = ShockThresholds()) -> bool:
    """RECOVERY -> SHOCK on one settled reading: rising breadth, or a new SPY low."""
    if not _settled(reading, th):
        return False
    rising = _rising(state, reading) and _meets(reading.breadth_frac, th.breadth_reenter)
    return rising or reading.spy_new_low


def _from_shock(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    if not recovery_condition(state, reading, th):
        return state
    return replace(state, label=RECOVERY, since=reading.as_of, hold_since=reading.as_of,
                   entry_streak=0)


def _from_recovery(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    if reentry_condition(state, reading, th):
        return _enter_shock(state, reading)
    if not recovery_condition(state, reading, th):
        return replace(state, hold_since=None)
    hold = state.hold_since or reading.as_of
    if _minutes(hold, reading.as_of) + _EPS >= th.recovery_min_dwell_min:
        return replace(state, label=NORMAL, since=reading.as_of, hold_since=None, entry_streak=0)
    return replace(state, hold_since=hold)


RULES: dict[str, Rule] = {NORMAL: _from_normal, SHOCK: _from_shock, RECOVERY: _from_recovery}
```

`_carry` and `step` stay where V209-3 put them (after `RULES`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_step_exit.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`
Expected: PASS (its SHOCK-holds case uses breadth 0.50, which is not repaired).

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`_from_recovery` is the largest, about 5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/shock.py tests/market/test_shock_step_exit.py
git commit -m "feat(v209): shock.step -- recovery, second-leg re-entry and overnight carry"
```
