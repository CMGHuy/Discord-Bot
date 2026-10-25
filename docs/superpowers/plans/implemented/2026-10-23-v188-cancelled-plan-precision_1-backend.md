# v188 — Cancelled-plan precision: Part 1, backend core (V188-1..V188-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-23-v188-cancelled-plan-precision-design.md](../specs/2026-10-23-v188-cancelled-plan-precision-design.md)
**Index:** [2026-10-23-v188-cancelled-plan-precision_0-index.md](2026-10-23-v188-cancelled-plan-precision_0-index.md) — Goal, Global Constraints, Spec clarifications 1–11, Contracts, Review Focus and Parallelisation live there and bind every task below. This part never changes a contract the index fixes.

**Scope:** the worktree, the `risk_cap` crossing-price persistence (the one bot-side edit), the pure replay, the cancelled/filled plan rows, and the figures and payload. The admin route is part 3 (`_3-route.md`, V188-5), split out to stay under the 1500-line cap; part 2 (`_2-screen.md`) consumes that route's payload unchanged.

**Working directory:** every path and command below is relative to the worktree root `.claude/worktrees/2026-10-23-v188-cancelled-plan-precision`, created in V188-1 Step 1. Never edit the main tree from a task.

**Fixture conventions shared by V188-2..V188-4** (V188-5's route lives in part 3 and defines its own) (each test file defines its own copy, no shared helper module):
- Frames come from `tests.helpers.make_ohlcv` with `(open, high, low, close)` tuples and `start="2026-07-30"`, so bar 0 is 2026-07-30, bar 1 2026-07-31, bar 2 **2026-08-03 (the cancel day)**, bar 3 2026-08-04 (the first walked bar), … bar 12 **2026-08-17 (`until` for a `2w` plan cancelled on 2026-08-03)**, bar 13 2026-08-18 (outside the window).
- The flat bar is `(100.0, 100.5, 99.5, 100.0)`: it touches neither a long trigger at 105 nor a stop at 95.
- The long plan is trigger 105, stop 95, TP1 120, horizon `2w`: risk 10, full target R **1.5**. The short plan is trigger 95, stop 105, TP1 80: the same R.
- The cancel `at` is `"2026-08-03T15:00:00+00:00"` (11:00 New York, 2026-08-03).

# Phase 1 — Worktree and the bot patch

### Task V188-1: Worktree; `risk_cap` cancels record their crossing price
**Model:** sonnet — a one-argument edit in a hot file, pinned by a byte-identity test; the care is in proving nothing else moved.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (the `risk_cap` `record_transition` call inside `_step_pending`, today around lines 940-941)
- Create: `tests/planning/test_risk_cap_entry_recorded.py` (suite `planning`)

**Interfaces:**
- Consumes: `record_transition(plan, new_status, reason=None, at=None, extra=None)` (`swingbot/core/planning/plan_types.py:230`; `extra` keys are merged under the three core keys, which always win).
- Produces: from this task on, the CANCELLED `status_history` entry a live `risk_cap` cancel writes is `{"entry_price": <fill float>, "status": "CANCELLED", "reason": "risk_cap", "at": <UTC iso>}`. V188-3 reads `entry_price` from that entry (`entry_source = "recorded"`). Window (`_expire_window`) cancels are not touched and keep no price; V188-3 estimates theirs.

- [ ] **Step 1: Create the worktree**

```bash
cd /e/Documents/Private/Projects/Discord-Bot
git worktree list
git worktree add .claude/worktrees/2026-10-23-v188-cancelled-plan-precision -b 2026-10-23-v188-cancelled-plan-precision main
cd .claude/worktrees/2026-10-23-v188-cancelled-plan-precision
git status --short
```

Expected: the new worktree on branch `2026-10-23-v188-cancelled-plan-precision`, `git status --short` empty. If `git worktree list` already shows this worktree, reuse it and resume at its first uncommitted task instead. Then run `/replicate-prod-db` once (CLAUDE.md: before a task's first test run against the database; `PlanStore` in `tests/planning/` is DB-backed).

- [ ] **Step 2: Write the failing test**

Create `tests/planning/test_risk_cap_entry_recorded.py`:

```python
"""v188: a live risk_cap cancel writes the crossing price onto its history entry.

The only bot-side change in v188. Everything else a cancel produces -- the
event, its detail, the plan status, every stored field -- stays byte-identical;
the history entry gains exactly one key, `entry_price`.
"""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

AT = "2026-08-03T15:00:00+00:00"


def _poll(tmp_path, monkeypatch, price, **plan_kw):
    """One poll at a pinned clock, out of structural-stop scope (2% ceiling)."""
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    monkeypatch.setattr(mgr, "_now", lambda: AT)
    store.add(_pending(**plan_kw))
    return store, mgr.poll()


def test_risk_cap_history_entry_carries_the_crossing_price(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    entry = store.get("p1").status_history[-1]
    assert entry == {"entry_price": 106.0, "status": "CANCELLED",
                     "reason": "risk_cap", "at": AT}


def test_the_recorded_price_is_the_fill_not_the_live_quote_below_trigger(tmp_path, monkeypatch):
    # bearish: fill = min(price, trigger); live 94.0 under trigger 95.0 fills at 94.0
    store, _ = _poll(tmp_path, monkeypatch, 94.0, direction="bearish",
                     trigger_price=95.0, stop_loss=105.0, tp1=80.0)
    assert store.get("p1").status_history[-1]["entry_price"] == 94.0


def test_event_detail_is_unchanged(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    assert events[0].detail == {
        "entry_price": 106.0,
        "stop_loss": 95.0,
        "planned_loss_pct": round(abs(106.0 - 95.0) / 106.0 * 100, 4),
        "max_planned_loss_pct": pytest.approx(2.0),
    }


def test_stored_plan_is_byte_identical_but_for_the_new_key(tmp_path, monkeypatch):
    store, _ = _poll(tmp_path, monkeypatch, 106.0, stop_loss=95.0)
    stored = plan_to_dict(store.get("p1"))
    assert stored["status_history"][-1].pop("entry_price") == 106.0

    control = _pending(stop_loss=95.0)
    record_transition(control, PlanStatus.CANCELLED, reason="risk_cap", at=AT)
    assert stored == plan_to_dict(control)
    assert store.get("p1").entry_price is None        # a cancel never sets entry_price


def test_invalidated_and_filled_entries_gain_no_key(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 94.0, stop_loss=95.0)
    assert [e.transition for e in events] == ["cancelled_invalidated"]
    assert set(store.get("p1").status_history[-1]) == {"status", "reason", "at"}

    store, events = _poll(tmp_path, monkeypatch, 106.0, stop_loss=104.0)
    assert [e.transition for e in events] == ["filled"]
    assert set(store.get("p1").status_history[-1]) == {"status", "reason", "at"}
```

`plan_to_dict` and `record_transition` are re-exported by `swingbot/core/planning/plan_engine.py:10-11`.

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_risk_cap_entry_recorded.py`
Expected: FAIL — `test_risk_cap_history_entry_carries_the_crossing_price` and `test_the_recorded_price_is_the_fill_not_the_live_quote_below_trigger` fail (the entry has no `entry_price`), `test_stored_plan_is_byte_identical_but_for_the_new_key` fails on `pop`. The other two pass already.

- [ ] **Step 4: Pass the fill as `extra`**

In `PlanManager._step_pending`, the `risk_cap` branch only:

```python
            if risk_pct > ceiling_pct:
                record_transition(plan, PlanStatus.CANCELLED, reason="risk_cap",
                                  at=self._now(), extra={"entry_price": fill})
```

Nothing else in the method changes: not the event, not its detail, not the `invalidated`, `expired` or `filled` branches. `_step_pending`'s cyclomatic complexity is unchanged (B(10)); the edit adds no branch.

- [ ] **Step 5: Run the test file and the neighbours that pin `_step_pending`**

Run: `python scripts/dev/testrun.py file tests/planning/test_risk_cap_entry_recorded.py`
Expected: 5 passed.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py` and `python scripts/dev/testrun.py file tests/planning/test_plan_manager_stop_ceiling.py`
Expected: both green, pass counts as before the edit.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_risk_cap_entry_recorded.py
git commit -m "feat(planning): risk_cap cancels record their crossing price on status_history (v188)

The history entry gains entry_price; event, detail, status and every stored
field stay byte-identical. No cancel rule changes.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

# Phase 2 — The pure core

### Task V188-2: Pure post-cancel replay
**Model:** opus — the no-lookahead bar walk: trading-date conversion across UTC/ET, window edges, stop-before-TP1 ties; a quiet off-by-one here biases every figure.

**Files:**
- Create: `swingbot/core/analytics/cancel_replay.py`
- Create: `tests/analytics/test_cancel_replay.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes: `swingbot.core.market.session.US_MARKET_TZ` (`ZoneInfo("America/New_York")`, `session.py:12`), `swingbot.core.market.strategy_types.HORIZONS` (`[h]["max_holding_days"]`, calendar days).
- Produces (index § Contracts, verbatim): `OUTCOMES = ("right", "wrong", "unresolved", "untriggered_after_cancel")`, `SPLIT_GUARD = 0.25`, frozen dataclass `Replay(outcome: str, r: float | None, tie: bool, touch_day: date | None, exit_day: date | None, until: date, elapsed: bool)`, `trading_date(at: str) -> date`, `window_end(start: date, horizon_key: str) -> date | None`, `split_guard_ok(frame, day: date, level: float) -> bool`, `last_bar_day(frame) -> date | None` (also accepts `None`), `replay(frame, *, bullish, entry, stop, tp1, after, until, require_touch=True) -> Replay`. `Replay.r` is the raw float; rounding happens only in V188-4's JSON.

**Rules this module owns** (index Spec clarifications 1–4; the one place each rule lives):
- Window: `until = start + timedelta(days=HORIZONS[h]["max_holding_days"])`; walked bars satisfy `after < day <= until` (the cancel-day bar is never walked); `elapsed` = the frame's last bar date `>= until`.
- Trading date: a date-only string parses as that date; an aware timestamp converts to New York; a naive one is read as UTC first.
- Touch: long `high >= entry`, short `low <= entry`. Without a touch: `untriggered_after_cancel` if elapsed, else `unresolved` with `r = None`. From the touch bar onward, **including the touch bar**, each bar checks the stop first (long `low <= stop`, short `high >= stop`), then TP1 (long `high >= tp1`, short `low <= tp1`). Stop first → `right`, `r = -1.0`, `tie = True` when the same bar also reached TP1. TP1 first → `wrong`, `r = |tp1 − entry| / |entry − stop|` (full target, no partial exit). Neither → `unresolved`, marked to the close of the last walked bar: `(close − entry) / risk` long, `(entry − close) / risk` short.
- `require_touch=False` (the filled-plan baseline) starts the walk at the first walked bar; `touch_day` is then that bar's date.
- Split guard: the last close on or before `day` must lie within `SPLIT_GUARD` (25%) of `level`, relative to `level`; no such bar, or `level <= 0`, fails the guard.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_cancel_replay.py`:

```python
"""v188: the post-cancel replay (pure).

Reference walk: scripts/reports/autopsy/bars.py (bisect_right strictly past the
exit day). Frames start 2026-07-30: bar 2 is the cancel day 2026-08-03, bar 3
the first walked bar, bar 12 is `until` (2026-08-17) for a 2w plan.
"""
from datetime import date

import pytest

from swingbot.core.analytics import cancel_replay as cr
from tests.helpers import make_ohlcv

FLAT = (100.0, 100.5, 99.5, 100.0)
CANCEL_DAY = date(2026, 8, 3)
UNTIL = date(2026, 8, 17)


def _frame(*walked, pre=(FLAT, FLAT, FLAT), total=14, pad=FLAT):
    """Bars 0-2 (through the cancel day), then `walked` from 2026-08-04, padded to `total`."""
    bars = list(pre) + list(walked)
    bars += [pad] * max(0, total - len(bars))
    return make_ohlcv(bars, start="2026-07-30")


def _long(frame, **kw):
    args = dict(bullish=True, entry=105.0, stop=95.0, tp1=120.0,
                after=CANCEL_DAY, until=UNTIL)
    args.update(kw)
    return cr.replay(frame, **args)


def _short(frame, **kw):
    args = dict(bullish=False, entry=95.0, stop=105.0, tp1=80.0,
                after=CANCEL_DAY, until=UNTIL)
    args.update(kw)
    return cr.replay(frame, **args)


# -- trading date --------------------------------------------------------------

@pytest.mark.parametrize("at, expected", [
    ("2026-08-03T15:00:00+00:00", date(2026, 8, 3)),   # in-session, UTC
    ("2026-08-03T16:00:00-04:00", date(2026, 8, 3)),   # window cancel, ET-aware
    ("2026-08-04T02:00:00", date(2026, 8, 3)),         # naive reads as UTC
    ("2026-08-03T15:00:00Z", date(2026, 8, 3)),
    ("2026-08-03", date(2026, 8, 3)),                  # date only stays that date
])
def test_trading_date(at, expected):
    assert cr.trading_date(at) == expected


def test_utc_after_midnight_maps_to_the_previous_ny_session():
    """Review Focus 1: 01:30 UTC on the 4th is 21:30 New York on the 3rd."""
    assert cr.trading_date("2026-08-04T01:30:00+00:00") == date(2026, 8, 3)


# -- window --------------------------------------------------------------------

def test_window_end_counts_calendar_days_of_the_horizon():
    assert cr.window_end(CANCEL_DAY, "2w") == UNTIL
    assert cr.window_end(CANCEL_DAY, "4w") == date(2026, 8, 31)


def test_unknown_horizon_has_no_window():
    assert cr.window_end(CANCEL_DAY, "9y") is None


def test_last_bar_day():
    assert cr.last_bar_day(_frame()) == date(2026, 8, 18)
    assert cr.last_bar_day(None) is None
    assert cr.last_bar_day(_frame().iloc[0:0]) is None


# -- verdicts, long ------------------------------------------------------------

def test_stop_first_is_a_right_cancel_at_minus_one_r():
    out = _long(_frame((104, 106, 104, 105), (100, 101, 94, 95)))
    assert (out.outcome, out.r, out.tie) == ("right", -1.0, False)
    assert out.touch_day == date(2026, 8, 4)
    assert out.exit_day == date(2026, 8, 5)
    assert out.until == UNTIL and out.elapsed is True


def test_tp1_first_is_a_wrong_cancel_at_full_target_r():
    out = _long(_frame((104, 106, 104, 105), (110, 121, 109, 120)))
    assert out.outcome == "wrong"
    assert out.r == pytest.approx(1.5)          # |120 - 105| / |105 - 95|
    assert out.exit_day == date(2026, 8, 5)


def test_same_bar_stop_and_tp1_counts_as_the_stop_and_is_a_tie():
    out = _long(_frame((104, 106, 104, 105), (105, 121, 94, 100)))
    assert (out.outcome, out.r, out.tie) == ("right", -1.0, True)


def test_the_touch_bar_itself_is_checked_stop_first():
    out = _long(_frame((100, 106, 94, 96)))     # touches 105 and 95 on one bar
    assert (out.outcome, out.tie) == ("right", False)
    assert out.touch_day == out.exit_day == date(2026, 8, 4)


def test_no_touch_in_an_elapsed_window_is_untriggered_after_cancel():
    out = _long(_frame())
    assert (out.outcome, out.r, out.touch_day) == ("untriggered_after_cancel", None, None)
    assert out.elapsed is True


def test_the_cancel_day_bar_is_never_walked():
    """No-lookahead: a cancel-day bar through trigger, stop and TP1 decides nothing."""
    out = _long(_frame(pre=(FLAT, FLAT, (100, 125, 90, 110))))
    assert out.outcome == "untriggered_after_cancel"


def test_a_bar_on_until_counts():
    walked = [FLAT] * 9 + [(104, 121, 104, 120)]   # bar 12 = 2026-08-17
    out = _long(_frame(*walked))
    assert (out.outcome, out.exit_day) == ("wrong", UNTIL)


def test_a_bar_after_until_never_counts():
    walked = [FLAT] * 10 + [(104, 121, 104, 120)]  # bar 13 = 2026-08-18
    out = _long(_frame(*walked))
    assert out.outcome == "untriggered_after_cancel"


def test_touched_without_exit_in_an_elapsed_window_is_marked_to_the_last_close():
    walked = [(104, 106, 104, 105)] + [(105, 108, 104, 106)] * 8 + [(106, 108, 105, 107)]
    out = _long(_frame(*walked))                   # last walked bar = 2026-08-17, close 107
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(0.2)             # (107 - 105) / 10
    assert out.elapsed is True and out.exit_day is None


def test_a_window_not_yet_over_is_unresolved_even_untouched():
    out = _long(_frame(total=8))                   # last bar 2026-08-10 < until
    assert (out.outcome, out.r, out.elapsed) == ("unresolved", None, False)


def test_a_window_not_yet_over_touched_is_marked_to_market():
    out = _long(_frame((104, 106, 104, 105), (105, 110, 104, 109), total=8))
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx((100.0 - 105.0) / 10.0)   # last walked close is the flat pad
    assert out.elapsed is False


def test_no_bar_after_the_cancel_day_is_unresolved():
    out = _long(_frame(total=3))
    assert (out.outcome, out.r, out.touch_day, out.elapsed) == ("unresolved", None, None, False)


# -- verdicts, short (mirrored) ------------------------------------------------

def test_short_stop_first_is_right():
    out = _short(_frame((96, 96, 94, 95), (100, 106, 99, 104)))
    assert (out.outcome, out.r) == ("right", -1.0)


def test_short_tp1_first_is_wrong_at_full_target_r():
    out = _short(_frame((96, 96, 94, 95), (90, 91, 79, 80)))
    assert out.outcome == "wrong"
    assert out.r == pytest.approx(1.5)


def test_short_same_bar_tie_counts_as_the_stop():
    out = _short(_frame((96, 96, 94, 95), (95, 106, 79, 90)))
    assert (out.outcome, out.tie) == ("right", True)


def test_short_flat_window_is_untriggered():
    assert _short(_frame()).outcome == "untriggered_after_cancel"


def test_short_unresolved_is_marked_mirrored():
    walked = [(96, 96, 94, 95)] + [(94, 96, 92, 93)] * 9   # last close 93
    out = _short(_frame(*walked))
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(0.2)                     # (95 - 93) / 10


# -- the baseline walk ---------------------------------------------------------

def test_without_a_touch_requirement_the_walk_starts_on_the_first_bar():
    out = _long(_frame((100, 101, 94, 95)), require_touch=False)
    assert (out.outcome, out.touch_day) == ("right", date(2026, 8, 4))


def test_without_a_touch_requirement_a_flat_window_is_unresolved():
    out = _long(_frame(), require_touch=False)
    assert out.outcome == "unresolved"
    assert out.r == pytest.approx(-0.5)                    # (100 - 105) / 10


# -- split guard ---------------------------------------------------------------

def test_split_guard_passes_a_close_near_the_level():
    assert cr.split_guard_ok(_frame(), CANCEL_DAY, 105.0) is True   # |100-105|/105 = 4.8%


def test_split_guard_fails_an_adjusted_close_far_from_the_level():
    """Review Focus 2: a 2:1 split adjusts history to 50 against a raw 105 level."""
    halved = (50.0, 50.25, 49.75, 50.0)
    assert cr.split_guard_ok(_frame(pre=(halved,) * 3), CANCEL_DAY, 105.0) is False


def test_split_guard_reads_the_last_close_on_or_before_the_day():
    frame = _frame(pre=(FLAT, FLAT, (100, 131, 99, 130)))   # cancel-day close 130
    assert cr.split_guard_ok(frame, CANCEL_DAY, 105.0) is True    # 23.8%
    assert cr.split_guard_ok(frame, date(2026, 7, 31), 140.0) is False  # 7/31 close 100: 28.6%


def test_split_guard_fails_with_no_bar_on_or_before_the_day():
    assert cr.split_guard_ok(_frame(), date(2026, 7, 1), 105.0) is False


def test_constants():
    assert cr.OUTCOMES == ("right", "wrong", "unresolved", "untriggered_after_cancel")
    assert cr.SPLIT_GUARD == 0.25
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_replay.py`
Expected: FAIL at collection — `ImportError: cannot import name 'cancel_replay'`.

- [ ] **Step 3: Implement `swingbot/core/analytics/cancel_replay.py`**

```python
"""v188: replay a withdrawn plan's price path after its cancel (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Reference walk: scripts/reports/autopsy/bars.py (`bisect_right` strictly past
the exit day, SPLIT_GUARD). Core may not import scripts/, so the walk is
re-implemented here, and this module is the one place its rules live.

NO-LOOKAHEAD: bars are walked strictly AFTER the cancel's NYSE trading date and
no later than `until`. Frames are `daily_delta.read_daily` output: a tz-naive
exchange-date DatetimeIndex with Open/High/Low/Close, the forming bar never
persisted. A same-bar stop + TP1 touch counts as the stop (the simulators'
conservative convention) and is flagged as a tie.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.market.strategy_types import HORIZONS

OUTCOMES = ("right", "wrong", "unresolved", "untriggered_after_cancel")
SPLIT_GUARD = 0.25   # mirrors scripts/reports/autopsy/bars.py


@dataclass(frozen=True)
class Replay:
    outcome: str
    r: float | None
    tie: bool
    touch_day: date | None
    exit_day: date | None
    until: date
    elapsed: bool


def trading_date(at: str) -> date:
    """The NYSE date of an ISO timestamp; a naive one is read as UTC."""
    text = str(at).strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(US_MARKET_TZ).date()


def window_end(start: date, horizon_key: str) -> date | None:
    spec = HORIZONS.get(horizon_key)
    if not spec:
        return None
    return start + timedelta(days=int(spec["max_holding_days"]))


def last_bar_day(frame: pd.DataFrame | None) -> date | None:
    if frame is None or frame.empty:
        return None
    return frame.index[-1].date()


def split_guard_ok(frame: pd.DataFrame, day: date, level: float) -> bool:
    upto = frame[frame.index.normalize() <= pd.Timestamp(day)]
    if upto.empty or level <= 0:
        return False
    close = float(upto["Close"].iloc[-1])
    return abs(close - level) / level <= SPLIT_GUARD
```

The walk, as private helpers so `replay` stays well under complexity 15:

```python
def _walked(frame, after, until):
    days = frame.index.normalize()
    return frame[(days > pd.Timestamp(after)) & (days <= pd.Timestamp(until))]

def _touch_at(bars, bullish, entry):
    for i, (high, low) in enumerate(zip(bars["High"], bars["Low"])):
        if (high >= entry) if bullish else (low <= entry):
            return i
    return None

def _first_exit(bars, bullish, stop, tp1):
    for ts, high, low in zip(bars.index, bars["High"], bars["Low"]):
        stop_hit = low <= stop if bullish else high >= stop
        tp1_hit = high >= tp1 if bullish else low <= tp1
        if stop_hit:
            return "right", bool(tp1_hit), ts.date()
        if tp1_hit:
            return "wrong", False, ts.date()
    return None

def _mark(bars, bullish, entry, stop):
    if bars.empty:
        return None
    close = float(bars["Close"].iloc[-1])
    move = close - entry if bullish else entry - close
    return move / abs(entry - stop)
```

```python
def replay(frame, *, bullish: bool, entry: float, stop: float, tp1: float,
           after: date, until: date, require_touch: bool = True) -> Replay:
    bars = _walked(frame, after, until)
    last = last_bar_day(frame)
    elapsed = last is not None and last >= until
    start = _touch_at(bars, bullish, entry) if require_touch else (0 if len(bars) else None)
    if start is None:
        outcome = "untriggered_after_cancel" if elapsed and require_touch else "unresolved"
        return Replay(outcome, None, False, None, None, until, elapsed)
    live = bars.iloc[start:]
    touch_day = live.index[0].date()
    hit = _first_exit(live, bullish, stop, tp1)
    if hit is None:
        return Replay("unresolved", _mark(live, bullish, entry, stop), False,
                      touch_day, None, until, elapsed)
    outcome, tie, day = hit
    r = -1.0 if outcome == "right" else abs(tp1 - entry) / abs(entry - stop)
    return Replay(outcome, r, tie, touch_day, day, until, elapsed)
```

`replay` assumes valid levels (risk > 0, TP1 beyond entry); V188-3 excludes `bad_levels` before calling it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_replay.py`
Expected: all pass, 0 failed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; no function in `cancel_replay.py` reaches 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/cancel_replay.py tests/analytics/test_cancel_replay.py
git commit -m "feat(analytics): pure post-cancel replay for v188 cancelled-plan precision

Strictly-after NYSE trading date, calendar-day horizon window, stop before TP1
with same-bar ties counted, long/short mirrored, split guard 0.25.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task V188-3: Cancelled and filled plans to replay rows
**Model:** opus — exclusion precedence, the recorded-versus-estimated `risk_cap` entry and the baseline population all decide what gets scored; a wrong default silently moves precision.

**Files:**
- Create: `swingbot/core/analytics/cancel_rows.py`
- Create: `tests/analytics/test_cancel_rows.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes: V188-2 `Replay`, `replay`, `trading_date`, `window_end`, `split_guard_ok`; V188-1's CANCELLED history key `entry_price`; `partials.is_filled(plan)` (`swingbot/core/analytics/partials.py:84`); `plan_types.PlanStatus`, `plan_types.plan_from_dict` (`plan_types.py:6, :222`); `stop_scope.plan_stop_ceiling(plan) -> float` (`stop_scope.py:51`); `risk_limits.planned_loss_pct(entry, stop) -> float` (`inf` when invalid); `tracking.origin.origin_of`, `NEXT_SESSION`.
- Produces (index § Contracts, verbatim): `REASONS`, `OTHER`, `MANUAL`, `FILLED`, `ENTRY_MODELS`, `EXCLUSIONS`, `Loader`, frozen dataclass `CancelRow` (the 19 fields in contract order, plus property `entry_date -> str` = `cancel_day.isoformat()`), `reason_bucket(raw) -> str`, `cancel_entry(plan, frame, cancel_day) -> tuple[float | None, str | None]`, `cancel_rows(plans, loader) -> list[CancelRow]`, `filled_rows(plans, loader) -> list[CancelRow]`, `manual_count(plans) -> int`. Every public function accepts `TradePlanV2` objects **or** plan dicts (the route passes `PlanStore().records()` dicts); dicts go through `plan_from_dict`.

**Decisions this task fixes** (index Spec clarifications 5–7, 11):
- The cancel is the **last** CANCELLED `status_history` entry; `raw_reason` is its `reason`; `cancel_day = trading_date(entry["at"])`, falling back to `plan.created_at` when `at` is missing. Only plans whose `status` is CANCELLED are cancel rows; `manual` ones are counted by `manual_count` and never become rows.
- Exclusion precedence (first failing check wins): `unknown_horizon` → `no_bars` (loader `None` or empty frame) → `no_cancel_entry` (a `cancel_fill` row with no entry; a `trigger` row with `trigger_price None` is `bad_levels`) → `bad_levels` (signed risk ≤ 0 or signed reward ≤ 0) → `split_guard` (checked against the row's own entry on the cancel day). An excluded row has `replay = None` and keeps every other field.
- `stop_ceiling_pct = plan_stop_ceiling(plan)` on every row (`None` if it raises `KeyError`/`TypeError`/`ValueError`); `cap_size_pct = round(100 × ceiling / planned_loss_pct(entry, stop), 2)` on **both** `risk_cap` rows, each with its own entry, `None` elsewhere or when the loss is not finite and positive.
- Filled rows: `is_filled(plan)`, `reason = FILLED`, `raw_reason = None`, `cancel_day` = trading date of the **first** ACTIVE entry, `entry = trigger_price`, `entry_model = "trigger"`, replayed with `require_touch=False`. They may still be open (an unfinished window is `unresolved`).

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_cancel_rows.py`:

```python
"""v188: cancelled and filled plans to replay rows (pure).

Frames start 2026-07-30; bar 2 is the cancel day 2026-08-03 (open 108 by
default here, so the estimated risk_cap entry differs from the trigger).
"""
from datetime import date

import pytest

from swingbot.core.analytics import cancel_rows as rows_mod
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

AT = "2026-08-03T15:00:00+00:00"
FLAT = (100.0, 100.5, 99.5, 100.0)
CANCEL_BAR = (108.0, 108.5, 99.5, 100.0)     # gap open 108 above the trigger 105
STOP_HIT = (100.0, 101.0, 94.0, 95.0)
LONG = dict(entry_type="stop_entry", trigger_price=105.0, stop_loss=95.0,
            tp1=120.0, horizon_key="2w", source="strategy", strategy="Fibonacci",
            stop_ceiling_pct=2.0)
SHORT = dict(LONG, direction="bearish", trigger_price=95.0, stop_loss=105.0, tp1=80.0)


def _frame(*walked, pre=(FLAT, FLAT, CANCEL_BAR), total=14):
    bars = list(pre) + list(walked)
    bars += [FLAT] * max(0, total - len(bars))
    return make_ohlcv(bars, start="2026-07-30")


def _cancelled(reason="invalidated", *, at=AT, extra=None, **kw):
    plan = _plan(**{**LONG, **kw})
    record_transition(plan, PlanStatus.CANCELLED, reason=reason, at=at, extra=extra)
    return plan


def _filled(*, at=AT, **kw):
    plan = _plan(**{**LONG, **kw})
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill", at=at)
    return plan


def _loader(frame):
    return lambda _ticker: frame


# -- reason buckets ------------------------------------------------------------

@pytest.mark.parametrize("raw, bucket", [
    ("risk_cap", "risk_cap"), ("invalidated", "invalidated"), ("expired", "expired"),
    ("manual", "manual"), ("never_triggered", "other"), ("no_session_data", "other"),
    (None, "other"),
])
def test_reason_bucket(raw, bucket):
    assert rows_mod.reason_bucket(raw) == bucket


def test_constants():
    assert rows_mod.REASONS == ("risk_cap", "invalidated", "expired")
    assert rows_mod.ENTRY_MODELS == ("trigger", "cancel_fill")
    assert rows_mod.EXCLUSIONS == ("no_bars", "split_guard", "bad_levels",
                                   "unknown_horizon", "no_cancel_entry")


# -- cancelled rows ------------------------------------------------------------

def test_an_invalidated_plan_is_one_trigger_row_with_its_replay():
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame((104, 106, 104, 105), STOP_HIT)))
    assert (row.reason, row.raw_reason, row.entry_model) == ("invalidated", "invalidated", "trigger")
    assert (row.entry, row.stop, row.tp1, row.entry_source) == (105.0, 95.0, 120.0, None)
    assert row.cancel_day == date(2026, 8, 3) and row.entry_date == "2026-08-03"
    assert (row.direction, row.origin, row.badge) == ("long", "regular", "WEAK")
    assert row.replay.outcome == "right" and row.excluded is None
    assert row.cap_size_pct is None and row.stop_ceiling_pct == 2.0


def test_a_risk_cap_plan_yields_a_trigger_row_and_an_estimated_fill_row():
    rows = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(_frame()))
    assert [r.entry_model for r in rows] == ["trigger", "cancel_fill"]
    fill = rows[1]
    assert (fill.entry, fill.entry_source) == (108.0, "estimated")   # max(open 108, trigger 105)
    assert fill.reason == "risk_cap" and fill.excluded is None


def test_a_recorded_crossing_price_wins_over_the_estimate():
    plan = _cancelled("risk_cap", extra={"entry_price": 106.5})
    fill = rows_mod.cancel_rows([plan], _loader(_frame()))[1]
    assert (fill.entry, fill.entry_source) == (106.5, "recorded")


def test_the_short_estimate_is_the_lower_of_open_and_trigger():
    gap_down = (90.0, 100.5, 89.5, 100.0)
    plan = _cancelled("risk_cap", **SHORT)
    fill = rows_mod.cancel_rows([plan], _loader(_frame(pre=(FLAT, FLAT, gap_down))))[1]
    assert (fill.entry, fill.entry_source, fill.direction) == (90.0, "estimated", "short")


def test_the_estimate_never_lies_inside_the_trigger():
    open_below = (101.0, 101.5, 99.5, 100.0)         # open under a long trigger of 105
    entry, source = rows_mod.cancel_entry(_cancelled("risk_cap"), _frame(pre=(FLAT, FLAT, open_below)),
                                          date(2026, 8, 3))
    assert (entry, source) == (105.0, "estimated")


def test_no_cancel_day_bar_excludes_only_the_fill_row():
    """Review Focus 3: never replay a missing crossing price from the trigger."""
    frame = _frame()
    frame = frame[frame.index.date != date(2026, 8, 3)]
    trigger, fill = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(frame))
    assert (fill.excluded, fill.replay, fill.entry, fill.entry_source) == \
        ("no_cancel_entry", None, None, None)
    assert trigger.excluded is None and trigger.replay is not None


def test_cap_size_on_both_risk_cap_rows():
    trigger, fill = rows_mod.cancel_rows([_cancelled("risk_cap")], _loader(_frame()))
    assert trigger.cap_size_pct == pytest.approx(21.0)    # 100 * 2 / (10/105*100)
    assert fill.cap_size_pct == pytest.approx(16.62)      # 100 * 2 / (13/108*100)


def test_a_pre_v139_plan_still_gets_a_cap_size():
    """Review Focus 5: no stored stop_ceiling_pct falls back, never raises."""
    confluence = _cancelled("risk_cap", stop_ceiling_pct=None, source="confluence")
    strategy = _cancelled("risk_cap", stop_ceiling_pct=None, plan_id="p2")
    rows = rows_mod.cancel_rows([confluence, strategy], _loader(_frame()))
    assert rows[0].stop_ceiling_pct == pytest.approx(2.0)
    assert rows[0].cap_size_pct == pytest.approx(21.0)
    assert rows[2].stop_ceiling_pct is not None and rows[2].cap_size_pct > 0


def test_manual_cancels_are_never_rows_and_are_counted():
    plans = [_cancelled("manual"), _cancelled(plan_id="p2")]
    assert [r.plan_id for r in rows_mod.cancel_rows(plans, _loader(_frame()))] == ["p2"]
    assert rows_mod.manual_count(plans) == 1


def test_an_unknown_reason_lands_in_other_with_its_raw_code():
    [row] = rows_mod.cancel_rows([_cancelled("never_triggered")], _loader(_frame()))
    assert (row.reason, row.raw_reason) == ("other", "never_triggered")
    assert row.replay is not None


def test_open_and_closed_plans_are_not_cancel_rows():
    assert rows_mod.cancel_rows([_plan(**LONG), _filled()], _loader(_frame())) == []


def test_next_session_origin_is_kept():
    [row] = rows_mod.cancel_rows([_cancelled(origin="next_session")], _loader(_frame()))
    assert row.origin == "next_session"


def test_dicts_and_plans_give_the_same_rows():
    plan = _cancelled("risk_cap")
    loader = _loader(_frame())
    assert rows_mod.cancel_rows([plan_to_dict(plan)], loader) == rows_mod.cancel_rows([plan], loader)


def test_the_window_cancel_et_timestamp_keeps_its_session():
    [row] = rows_mod.cancel_rows([_cancelled("expired", at="2026-08-03T16:00:00-04:00")],
                                 _loader(_frame()))
    assert row.cancel_day == date(2026, 8, 3)


# -- exclusions ----------------------------------------------------------------

def test_no_bars_is_excluded():
    [row] = rows_mod.cancel_rows([_cancelled()], lambda _t: None)
    assert (row.excluded, row.replay) == ("no_bars", None)


def test_an_empty_frame_is_no_bars():
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame().iloc[0:0]))
    assert row.excluded == "no_bars"


def test_a_split_inside_the_data_is_excluded_and_kept_visible():
    """Review Focus 2: adjusted 50s against a raw 105 trigger."""
    halved = (50.0, 50.25, 49.75, 50.0)
    [row] = rows_mod.cancel_rows([_cancelled()], _loader(_frame(pre=(halved,) * 3)))
    assert (row.excluded, row.replay, row.ticker) == ("split_guard", None, "AAPL")


@pytest.mark.parametrize("levels", [
    dict(tp1=104.0),               # TP1 not beyond a long entry
    dict(stop_loss=106.0),         # stop above a long entry
    dict(trigger_price=None),
])
def test_bad_levels_are_excluded(levels):
    [row] = rows_mod.cancel_rows([_cancelled(**levels)], _loader(_frame()))
    assert row.excluded == "bad_levels"


def test_an_unknown_horizon_is_excluded():
    [row] = rows_mod.cancel_rows([_cancelled(horizon_key="9y")], _loader(_frame()))
    assert (row.excluded, row.stop_ceiling_pct) == ("unknown_horizon", 2.0)


# -- filled rows (the baseline population) -------------------------------------

def test_a_filled_plan_replays_from_its_trigger_without_a_touch():
    [row] = rows_mod.filled_rows([_filled()], _loader(_frame(STOP_HIT)))
    assert (row.reason, row.raw_reason, row.entry_model) == ("filled", None, "trigger")
    assert row.cancel_day == date(2026, 8, 3)
    assert row.replay.outcome == "right"


def test_filled_rows_skip_pending_and_cancelled_plans():
    plans = [_plan(**LONG), _cancelled(plan_id="p2"), _filled(plan_id="p3")]
    assert [r.plan_id for r in rows_mod.filled_rows(plans, _loader(_frame()))] == ["p3"]


def test_the_fill_day_is_the_first_active_transition():
    plan = _filled(at="2026-08-04T01:30:00+00:00")            # 21:30 ET on the 3rd
    record_transition(plan, PlanStatus.PARTIAL, at="2026-08-10T15:00:00+00:00")
    [row] = rows_mod.filled_rows([plan], _loader(_frame()))
    assert row.cancel_day == date(2026, 8, 3)


def test_empty_inputs():
    assert rows_mod.cancel_rows([], _loader(_frame())) == []
    assert rows_mod.filled_rows([], _loader(_frame())) == []
    assert rows_mod.manual_count([]) == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_rows.py`
Expected: FAIL at collection — `ImportError: cannot import name 'cancel_rows'`.

- [ ] **Step 3: Implement `swingbot/core/analytics/cancel_rows.py`**

Module head, imports and constants:

```python
"""v188: cancelled and filled plans to replay rows (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Bars arrive through an injected `loader(ticker) -> frame | None`, as in
`day_sparklines.py`. A plan whose row cannot be scored stays a row with an
`excluded` code: it is shown, never dropped and never scored.

The cancel is the LAST `status_history` entry with status CANCELLED; its
`reason` is bucketed into the closed allowlist REASONS, "manual" (the
partner's decision, out of scope) or OTHER. A `risk_cap` cancel yields two
rows: the plan's trigger, and the price that crossed it (`recorded` on the
history entry from v188 on, else `estimated` from the cancel-day open).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from swingbot.core.analytics.cancel_replay import (Replay, replay, split_guard_ok,
                                                   trading_date, window_end)
from swingbot.core.analytics.partials import is_filled
from swingbot.core.planning.plan_types import PlanStatus, plan_from_dict
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from swingbot.core.risk_limits import planned_loss_pct
from swingbot.core.tracking.origin import NEXT_SESSION, origin_of

REASONS = ("risk_cap", "invalidated", "expired")
OTHER = "other"
MANUAL = "manual"
FILLED = "filled"
ENTRY_MODELS = ("trigger", "cancel_fill")
EXCLUSIONS = ("no_bars", "split_guard", "bad_levels", "unknown_horizon", "no_cancel_entry")
Loader = Callable[[str], "pd.DataFrame | None"]
```

`CancelRow` is the frozen dataclass of index § Contracts, field for field, with the `entry_date` property. `reason_bucket` returns `raw` when it is in `REASONS`, `MANUAL` for `"manual"`, else `OTHER`. Private access helpers: `_as_plan(p)` (`plan_from_dict` for a dict), `_entries(plan, status) -> list[dict]` (history entries with that status, in order), `_day_of(entry, plan) -> date` (`trading_date(entry["at"] or plan.created_at)`), `_ceiling(plan)` (the guarded `plan_stop_ceiling`). `manual_count` counts CANCELLED plans whose last CANCELLED entry buckets to `MANUAL`.

Row building:

```python
def _cap_size(ceiling: float | None, entry: float | None, stop: float | None) -> float | None:
    """Share (%) of a normal position that keeps the planned loss at the ceiling."""
    if ceiling is None or entry is None:
        return None
    loss = planned_loss_pct(entry, stop)
    if not math.isfinite(loss) or loss <= 0:
        return None
    return round(100.0 * ceiling / loss, 2)


def _levels_ok(bullish: bool, entry, stop, tp1) -> bool:
    if entry is None or stop is None or tp1 is None:
        return False
    risk = entry - stop if bullish else stop - entry
    reward = tp1 - entry if bullish else entry - tp1
    return risk > 0 and reward > 0


def _exclusion(plan, frame, entry, day: date, model: str) -> str | None:
    """First failing check, in EXCLUSIONS' order of precedence below."""
    if window_end(day, plan.horizon_key) is None:
        return "unknown_horizon"
    if frame is None or frame.empty:
        return "no_bars"
    if entry is None:
        return "no_cancel_entry" if model == "cancel_fill" else "bad_levels"
    if not _levels_ok(plan.direction == "bullish", entry, plan.stop_loss, plan.tp1):
        return "bad_levels"
    if not split_guard_ok(frame, day, entry):
        return "split_guard"
    return None


def _replay(plan, frame, entry, day: date, require_touch: bool) -> Replay:
    return replay(frame, bullish=plan.direction == "bullish", entry=entry,
                  stop=plan.stop_loss, tp1=plan.tp1, after=day,
                  until=window_end(day, plan.horizon_key), require_touch=require_touch)


def _row(plan, frame, *, reason: str, raw: str | None, day: date, model: str,
         entry, source: str | None, require_touch: bool = True) -> CancelRow:
    excluded = _exclusion(plan, frame, entry, day, model)
    ceiling = _ceiling(plan)
    return CancelRow(
        plan_id=plan.plan_id, ticker=plan.ticker, strategy=plan.strategy,
        horizon_key=plan.horizon_key,
        direction="long" if plan.direction == "bullish" else "short",
        origin=NEXT_SESSION if origin_of(plan) == NEXT_SESSION else "regular",
        reason=reason, raw_reason=raw, cancel_day=day, entry_model=model,
        entry_source=source, entry=entry, stop=plan.stop_loss, tp1=plan.tp1,
        badge=plan.badge, stop_ceiling_pct=ceiling,
        cap_size_pct=_cap_size(ceiling, entry, plan.stop_loss) if reason == "risk_cap" else None,
        replay=None if excluded else _replay(plan, frame, entry, day, require_touch),
        excluded=excluded)
```

Public functions:

```python
def cancel_entry(plan, frame, cancel_day: date) -> tuple[float | None, str | None]:
    """The `risk_cap` crossing price: recorded on the history entry, else
    max(cancel-day open, trigger) long / min(...) short, else (None, None)."""
    cancels = _entries(plan, PlanStatus.CANCELLED)
    recorded = cancels[-1].get("entry_price") if cancels else None
    if recorded is not None:
        return float(recorded), "recorded"
    if frame is None or frame.empty or plan.trigger_price is None:
        return None, None
    on_day = frame[frame.index.normalize() == pd.Timestamp(cancel_day)]
    if on_day.empty:
        return None, None
    open_ = float(on_day["Open"].iloc[0])
    pick = max if plan.direction == "bullish" else min
    return pick(open_, float(plan.trigger_price)), "estimated"


def _cancelled(plans: list):
    """(plan, raw reason, cancel day) for every CANCELLED, non-manual plan."""
    for plan in map(_as_plan, plans):
        if plan.status != PlanStatus.CANCELLED:
            continue
        cancels = _entries(plan, PlanStatus.CANCELLED)
        last = cancels[-1] if cancels else None
        raw = (last or {}).get("reason")
        if reason_bucket(raw) != MANUAL:
            yield plan, raw, _day_of(last, plan)


def cancel_rows(plans: list, loader: Loader) -> list[CancelRow]:
    rows = []
    for plan, raw, day in _cancelled(plans):
        frame = loader(plan.ticker)
        reason = reason_bucket(raw)
        rows.append(_row(plan, frame, reason=reason, raw=raw, day=day, model="trigger",
                         entry=plan.trigger_price, source=None))
        if reason == "risk_cap":
            entry, source = cancel_entry(plan, frame, day)
            rows.append(_row(plan, frame, reason=reason, raw=raw, day=day,
                             model="cancel_fill", entry=entry, source=source))
    return rows


def filled_rows(plans: list, loader: Loader) -> list[CancelRow]:
    """Every filled plan, replayed from its trigger strictly after the first
    ACTIVE transition's trading date, without a touch requirement."""
    rows = []
    for plan in map(_as_plan, plans):
        if not is_filled(plan):
            continue
        day = _day_of(_entries(plan, PlanStatus.ACTIVE)[0], plan)
        rows.append(_row(plan, loader(plan.ticker), reason=FILLED, raw=None, day=day,
                         model="trigger", entry=plan.trigger_price, source=None,
                         require_touch=False))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_rows.py`
Expected: all pass, 0 failed.

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_replay.py`
Expected: still green.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_exclusion` and `cancel_entry` are the largest, B(8)).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/cancel_rows.py tests/analytics/test_cancel_rows.py
git commit -m "feat(analytics): cancelled and filled plans to v188 replay rows

Closed reason allowlist with a visible other bucket, manual counted not scored,
risk_cap trigger and crossing-price rows (recorded or estimated), cap-implied
size, visible exclusions, filled-plan baseline rows.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task V188-4: Figures, intervals, baseline and payload
**Model:** opus — the statistics contract: precision versus net R, the week-clustered interval, the baseline population and the frozen payload shape that part 2 renders.

**Files:**
- Create: `swingbot/core/analytics/cancel_precision.py`
- Create: `tests/analytics/test_cancel_precision.py` (suite `edge-analytics`)

**Interfaces:**
- Consumes: V188-2 `OUTCOMES`, `last_bar_day`, `Replay`; V188-3 `REASONS`, `OTHER`, `ENTRY_MODELS`, `CancelRow`, `Loader`, `cancel_rows`, `filled_rows`, `manual_count`; `instrument.stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples=10_000, seed=42) -> np.ndarray` and `iso_week_key(entry_date) -> str` (`stats.py:57, :28`; both arms share one week draw, a `None` statistic is dropped); `strategy_types.HORIZONS` (key order for the horizon split).
- Produces (index § Contracts, verbatim): `SMALL_N = 10`, `CI_PCT = (2.5, 97.5)`, `CAPTION`, `RISK_CAP_LABEL`, `TP1_NOTE`, `RULE_CHANGES`, `figure(rows, *, with_interval=True) -> dict`, `baseline_population(filled, scored) -> list[CancelRow]`, `precision_payload(plans, loader, *, generated_at) -> dict` — the Figure, Row and Payload JSON of index § Contracts, key for key. V188-5 serves `precision_payload` unchanged; part 2 types it as `CancelPrecision`.

**Decisions this task fixes** (index Spec clarifications 7–10, Global Constraints):
- Interval: the component arm is a list of per-ISO-week sums (`_Week(entry_date, right, wrong, net)`), the baseline arm is empty; `precision_ci` is the (2.5, 97.5) percentile of `sum(right) / sum(right + wrong)` per draw, `net_r_ci` that of `sum(net)`. No interval when `n = 0` or `with_interval=False`. A single week gives a degenerate `[p, p]` band, which is honest.
- Rounding: R values 2 dp, `precision` and `precision_ci` 4 dp; row levels are passed through unrounded.
- The headline pools the **trigger** rows of the three REASONS; `without_risk_cap` drops `risk_cap`; `cancel_fill` rows appear only in `cards.risk_cap_fill`; `other` only in `cards.other`. Splits run over the headline-`all` population, a key only when it has rows, origin order `regular, next_session`, direction `long, short`, horizon in `HORIZONS` order then unknown keys sorted.
- The scored window is the min/max `cancel_day` of the non-excluded headline rows; the baseline keeps filled rows inside it whose `(strategy, horizon_key)` pair occurs among them.
- `RULE_CHANGES` holds two rows. **Build-time check:** run `git log main --merges --grep v183 --format="%ad %s" --date=short`. At plan time (2026-10-23) it prints nothing (v183 is spec and plan only). If it prints a merge, add `("<its date>", "v183 gap-aware short sizing")` as a third row in date order and extend `test_a_rule_change_inside_the_window_is_listed` with a cancel on that date.
- The loader is wrapped so each ticker is read once per payload; `data_as_of` is the latest `last_bar_day` among the frames it returned.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_cancel_precision.py`:

```python
"""v188: figures, intervals, baseline and payload (pure)."""
from datetime import date, timedelta

import pytest

from swingbot.core.analytics import cancel_precision as cp
from swingbot.core.analytics.cancel_replay import Replay
from swingbot.core.analytics.cancel_rows import CancelRow
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

DAY = date(2026, 8, 3)
FIGURE_KEYS = {"n", "total", "excluded", "precision", "precision_ci", "r_avoided",
               "r_missed", "net_r", "net_r_ci", "counts", "unresolved_r", "ties", "small_n"}
ROW_KEYS = {"plan_id", "ticker", "strategy", "horizon_key", "direction", "origin", "reason",
            "raw_reason", "cancel_date", "entry_model", "entry_source", "entry", "stop", "tp1",
            "badge", "stop_ceiling_pct", "cap_size_pct", "outcome", "r", "tie", "exit_date",
            "excluded"}


def _row(outcome="right", r=-1.0, *, day=DAY, tie=False, excluded=None, **kw):
    base = dict(plan_id="p1", ticker="AAPL", strategy="Fibonacci", horizon_key="2w",
                direction="long", origin="regular", reason="invalidated",
                raw_reason="invalidated", cancel_day=day, entry_model="trigger",
                entry_source=None, entry=105.0, stop=95.0, tp1=120.0, badge="WEAK",
                stop_ceiling_pct=2.0, cap_size_pct=None, excluded=excluded,
                replay=None if excluded else Replay(outcome, r, tie, day, None,
                                                     day + timedelta(days=14), True))
    base.update(kw)
    return CancelRow(**base)


# -- figure --------------------------------------------------------------------

def test_an_empty_figure_is_n_zero_never_an_error():
    """Review Focus 4."""
    fig = cp.figure([])
    assert set(fig) == FIGURE_KEYS
    assert (fig["n"], fig["total"], fig["precision"], fig["precision_ci"], fig["net_r_ci"]) == \
        (0, 0, None, None, None)
    assert fig["small_n"] is True and fig["net_r"] == 0.0
    assert fig["counts"] == {"right": 0, "wrong": 0, "unresolved": 0,
                             "untriggered_after_cancel": 0}


def test_counts_precision_and_r():
    rows = [_row(), _row(), _row(tie=True), _row("wrong", 1.5), _row("unresolved", 0.2),
            _row("unresolved", None), _row("untriggered_after_cancel", None),
            _row(excluded="split_guard")]
    fig = cp.figure(rows, with_interval=False)
    assert (fig["n"], fig["total"], fig["excluded"]) == (4, 8, 1)
    assert fig["precision"] == 0.75
    assert (fig["r_avoided"], fig["r_missed"], fig["net_r"]) == (3.0, 1.5, 1.5)
    assert fig["counts"] == {"right": 3, "wrong": 1, "unresolved": 2,
                             "untriggered_after_cancel": 1}
    assert (fig["unresolved_r"], fig["ties"], fig["small_n"]) == (0.2, 1, True)
    assert fig["precision_ci"] is None and fig["net_r_ci"] is None


def test_net_r_can_be_negative_while_precision_is_above_half():
    fig = cp.figure([_row(), _row(), _row("wrong", 3.0)], with_interval=False)
    assert fig["precision"] == pytest.approx(0.6667)
    assert fig["net_r"] == -1.0


def test_all_unresolved_is_n_zero():
    fig = cp.figure([_row("unresolved", 0.4), _row("unresolved", None)])
    assert (fig["n"], fig["precision"], fig["precision_ci"], fig["small_n"]) == (0, None, None, True)
    assert fig["unresolved_r"] == 0.4


def test_the_small_n_marker_clears_at_ten():
    assert cp.figure([_row()] * 9, with_interval=False)["small_n"] is True
    assert cp.figure([_row()] * 10, with_interval=False)["small_n"] is False


def test_the_interval_brackets_the_point_and_is_reproducible():
    rows = [_row(day=DAY + timedelta(weeks=w)) for w in range(6)]
    rows += [_row("wrong", 1.5, day=DAY + timedelta(weeks=w)) for w in range(0, 6, 2)]
    first, second = cp.figure(rows), cp.figure(rows)
    lo, hi = first["precision_ci"]
    assert 0.0 <= lo <= first["precision"] <= hi <= 1.0
    assert first["net_r_ci"][0] <= first["net_r"] <= first["net_r_ci"][1]
    assert first == second                                    # seed 42


def test_one_week_gives_a_degenerate_interval():
    fig = cp.figure([_row(), _row("wrong", 1.5)])
    assert fig["precision_ci"] == [0.5, 0.5]


# -- baseline population -------------------------------------------------------

def test_the_baseline_keeps_the_window_and_the_strategy_horizon_pairs():
    scored = [_row(day=DAY), _row(day=DAY + timedelta(days=10))]
    inside = _row(reason="filled", day=DAY + timedelta(days=5), plan_id="f1")
    early = _row(reason="filled", day=DAY - timedelta(days=1), plan_id="f2")
    other_pair = _row(reason="filled", day=DAY, horizon_key="4w", plan_id="f3")
    kept = cp.baseline_population([inside, early, other_pair], scored)
    assert [r.plan_id for r in kept] == ["f1"]


def test_no_scored_cancels_means_no_baseline():
    assert cp.baseline_population([_row(reason="filled")], []) == []


# -- payload -------------------------------------------------------------------

FLAT = (100.0, 100.5, 99.5, 100.0)
STOP_HIT = (100.0, 101.0, 94.0, 95.0)
TP1_HIT = (104.0, 121.0, 104.0, 120.0)
LONG = dict(entry_type="stop_entry", trigger_price=105.0, stop_loss=95.0, tp1=120.0,
            horizon_key="2w", source="strategy", strategy="Fibonacci", stop_ceiling_pct=2.0)


def _frame(*walked):
    bars = [FLAT, FLAT, (108.0, 108.5, 99.5, 100.0)] + list(walked)
    return make_ohlcv(bars + [FLAT] * (14 - len(bars)), start="2026-07-30")


def _with(status, reason, plan_id, at="2026-08-03T15:00:00+00:00", **kw):
    plan = _plan(plan_id=plan_id, ticker=plan_id.upper(), **{**LONG, **kw})
    record_transition(plan, status, reason=reason, at=at)
    return plan


def _book():
    frames = {"INV": _frame((104, 106, 104, 105), STOP_HIT),      # invalidated, right
              "EXP": _frame((104, 106, 104, 105), TP1_HIT),       # expired, wrong 1.5R
              "CAP": _frame(),                                     # risk_cap, untriggered
              "OTH": _frame(), "MAN": _frame(),
              "FIL": _frame(STOP_HIT)}                             # baseline, right
    plans = [_with(PlanStatus.CANCELLED, "invalidated", "inv"),
             _with(PlanStatus.CANCELLED, "expired", "exp", at="2026-08-04T15:00:00+00:00"),
             _with(PlanStatus.CANCELLED, "risk_cap", "cap"),
             _with(PlanStatus.CANCELLED, "never_triggered", "oth"),
             _with(PlanStatus.CANCELLED, "manual", "man"),
             _with(PlanStatus.ACTIVE, "stop_entry_fill", "fil")]
    return plans, frames.get


def test_the_payload_shape_and_copy():
    plans, loader = _book()
    body = cp.precision_payload(plans, loader, generated_at="2026-10-23T12:00:00+00:00")
    assert body["caption"] == "Hypothetical replay, before commissions, slippage and tax"
    assert body["risk_cap_label"] == "Outcome of the skipped setup, unaffordable at the cap"
    assert body["tp1_note"] == ("A TP1 hit counts the full target R with no partial exit; "
                                "the bot does not bank winners in full.")
    assert body["small_n_threshold"] == 10
    assert set(body["cards"]) == {"risk_cap", "risk_cap_fill", "invalidated", "expired", "other"}
    assert set(body["headline"]) == {"all", "without_risk_cap"}
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    assert set(body["baseline"]) == FIGURE_KEYS


def test_the_payload_figures():
    plans, loader = _book()
    body = cp.precision_payload(plans, loader, generated_at="x")
    head = body["headline"]["all"]
    assert (head["n"], head["total"], head["precision"]) == (2, 3, 0.5)
    assert head["counts"]["untriggered_after_cancel"] == 1
    assert body["headline"]["without_risk_cap"]["total"] == 2
    assert body["cards"]["risk_cap_fill"]["total"] == 1
    assert body["cards"]["other"]["total"] == 1
    assert body["out_of_scope"] == {"manual": 1}
    assert (body["baseline"]["n"], body["baseline"]["precision"]) == (1, 1.0)
    assert body["window"] == {"first": "2026-08-03", "last": "2026-08-04"}
    assert body["rule_changes"] == []
    assert body["data_as_of"] == "2026-08-18"


def test_rows_are_newest_first_with_both_risk_cap_models_and_no_baseline_or_manual():
    plans, loader = _book()
    rows = cp.precision_payload(plans, loader, generated_at="x")["rows"]
    assert [(r["plan_id"], r["entry_model"]) for r in rows] == [
        ("exp", "trigger"), ("cap", "trigger"), ("cap", "cancel_fill"),
        ("inv", "trigger"), ("oth", "trigger")]
    fill = rows[2]
    assert (fill["entry"], fill["entry_source"]) == (108.0, "estimated")
    assert rows[0]["r"] == 1.5 and rows[0]["exit_date"] == "2026-08-05"


def test_splits_list_only_present_keys():
    plans, loader = _book()
    splits = cp.precision_payload(plans, loader, generated_at="x")["splits"]
    assert list(splits["origin"]) == ["regular"]
    assert list(splits["direction"]) == ["long"]
    assert list(splits["horizon"]) == ["2w"]


def test_an_excluded_row_has_null_outcome_r_and_exit():
    plans, _ = _book()
    rows = cp.precision_payload(plans[:1], lambda _t: None, generated_at="x")["rows"]
    assert (rows[0]["excluded"], rows[0]["outcome"], rows[0]["r"], rows[0]["exit_date"]) == \
        ("no_bars", None, None, None)


def test_a_rule_change_inside_the_window_is_listed():
    plan = _with(PlanStatus.CANCELLED, "invalidated", "inv", at="2026-09-28T15:00:00+00:00")
    body = cp.precision_payload([plan], lambda _t: make_ohlcv([FLAT] * 5, start="2026-09-24"),
                                generated_at="x")
    assert body["rule_changes"] == [{"date": "2026-09-28",
                                     "label": "v104 structural stops and stop-ceiling scope"}]


def test_the_loader_is_called_once_per_ticker():
    calls = []
    plans, loader = _book()
    cp.precision_payload(plans, lambda t: calls.append(t) or loader(t), generated_at="x")
    assert sorted(calls) == sorted(set(calls))


def test_an_empty_book():
    """Review Focus 4: an empty book is a payload with n = 0, never an error."""
    body = cp.precision_payload([], lambda _t: None, generated_at="x")
    assert body["headline"]["all"]["n"] == 0 and body["headline"]["all"]["precision"] is None
    assert body["headline"]["all"]["small_n"] is True
    assert (body["rows"], body["rule_changes"], body["data_as_of"]) == ([], [], None)
    assert body["window"] == {"first": None, "last": None}
    assert body["splits"] == {"origin": {}, "direction": {}, "horizon": {}}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_precision.py`
Expected: FAIL at collection — `ImportError: cannot import name 'cancel_precision'`.

- [ ] **Step 3: Implement `swingbot/core/analytics/cancel_precision.py`**

Module head and the frozen copy:

```python
"""v188: cancelled-plan precision -- figures, intervals, baseline and payload (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Precision = right / (right + wrong); R avoided = right x 1.0R; R missed = the
wrong rows' full target R; net R = avoided - missed. Unresolved rows are marked
to market into `unresolved_r` and never enter precision or net R. Intervals are
the 95% percentile band of `week_cluster_bootstrap` over ISO-week sums, so a
draw costs about one item per week.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from swingbot.core.analytics.cancel_replay import OUTCOMES, last_bar_day
from swingbot.core.analytics.cancel_rows import (ENTRY_MODELS, OTHER, REASONS, CancelRow,
                                                 Loader, cancel_rows, filled_rows,
                                                 manual_count)
from swingbot.core.backtesting.instrument.stats import iso_week_key, week_cluster_bootstrap
from swingbot.core.market.strategy_types import HORIZONS

SMALL_N = 10
CI_PCT = (2.5, 97.5)
CAPTION = "Hypothetical replay, before commissions, slippage and tax"
RISK_CAP_LABEL = "Outcome of the skipped setup, unaffordable at the cap"
TP1_NOTE = ("A TP1 hit counts the full target R with no partial exit; "
            "the bot does not bank winners in full.")
RULE_CHANGES: tuple[tuple[str, str], ...] = (
    ("2026-09-28", "v104 structural stops and stop-ceiling scope"),
    ("2026-10-14", "v139 stored stop ceiling"),
)
```

Figures, intervals and the baseline:

```python
@dataclass(frozen=True)
class _Week:
    entry_date: str
    right: int
    wrong: int
    net: float


def _r(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _scored(rows: list[CancelRow]) -> list[CancelRow]:
    return [r for r in rows if r.excluded is None and r.replay is not None]


def _weeks(scored: list[CancelRow]) -> list[_Week]:
    by = defaultdict(list)
    for row in scored:
        if row.replay.outcome in ("right", "wrong"):
            by[iso_week_key(row.entry_date)].append(row)
    out = []
    for members in by.values():
        right = sum(1 for m in members if m.replay.outcome == "right")
        missed = sum(m.replay.r for m in members if m.replay.outcome == "wrong")
        out.append(_Week(members[0].entry_date, right, len(members) - right, right - missed))
    return out


def _precision_stat(_baseline, draw):
    decided = sum(w.right + w.wrong for w in draw)
    return sum(w.right for w in draw) / decided if decided else None


def _net_stat(_baseline, draw):
    return sum(w.net for w in draw)


def _interval(weeks: list[_Week], statistic, digits: int) -> list[float] | None:
    if not weeks:
        return None
    draws = week_cluster_bootstrap([], weeks, statistic)
    if draws.size == 0:
        return None
    lo, hi = np.percentile(draws, CI_PCT)
    return [round(float(lo), digits), round(float(hi), digits)]


def _tally(scored: list[CancelRow]) -> tuple[dict, float, float, int]:
    """(outcome counts, R missed, unresolved mark-to-market R, ties)."""
    counts = {o: sum(1 for r in scored if r.replay.outcome == o) for o in OUTCOMES}
    missed = sum(r.replay.r for r in scored if r.replay.outcome == "wrong")
    drift = sum(r.replay.r for r in scored
                if r.replay.outcome == "unresolved" and r.replay.r is not None)
    return counts, missed, drift, sum(1 for r in scored if r.replay.tie)


def figure(rows: list[CancelRow], *, with_interval: bool = True) -> dict:
    scored = _scored(rows)
    counts, missed, drift, ties = _tally(scored)
    n = counts["right"] + counts["wrong"]
    weeks = _weeks(scored) if with_interval and n else []
    return {
        "n": n, "total": len(rows), "excluded": len(rows) - len(scored),
        "precision": round(counts["right"] / n, 4) if n else None,
        "precision_ci": _interval(weeks, _precision_stat, 4),
        "r_avoided": _r(counts["right"]), "r_missed": _r(missed),
        "net_r": _r(counts["right"] - missed),
        "net_r_ci": _interval(weeks, _net_stat, 2),
        "counts": counts, "unresolved_r": _r(drift), "ties": ties,
        "small_n": n < SMALL_N,
    }


def baseline_population(filled: list[CancelRow], scored: list[CancelRow]) -> list[CancelRow]:
    """Filled rows whose fill day lies in the scored cancels' window and whose
    (strategy, horizon) pair occurs among them."""
    if not scored:
        return []
    first = min(r.cancel_day for r in scored)
    last = max(r.cancel_day for r in scored)
    pairs = {(r.strategy, r.horizon_key) for r in scored}
    return [r for r in filled
            if first <= r.cancel_day <= last and (r.strategy, r.horizon_key) in pairs]
```

The payload. Its private helpers, one line each (bodies follow from the tests and the contract):
- `_cached(loader) -> (load, frames)` — memoising wrapper; `frames` maps ticker → frame or `None`.
- `_data_as_of(frames) -> str | None` — max `last_bar_day` over the frames, ISO.
- `_window(scored) -> {"first", "last"}` — ISO min/max `cancel_day`, both `None` when empty.
- `_rule_changes(window) -> list[dict]` — `RULE_CHANGES` rows with `first <= date <= last`, `[]` when the window is empty.
- `_cards(trigger, rows)` — the five cards in key order `risk_cap, risk_cap_fill, invalidated, expired, other`.
- `_split(rows, attr, order)` and `_splits(pooled)` — as the decisions above.
- `_replay_json(row)` — `{"outcome", "r", "tie", "exit_date"}`, all null and `tie: False` for an excluded row; `_row_json(row)` — the Row JSON, `cancel_day` serialised as `cancel_date`.
- `_newest_first(rows)` — sort key `(-cancel_day.toordinal(), plan_id, ENTRY_MODELS.index(entry_model))`.

```python
def precision_payload(plans: list, loader: Loader, *, generated_at: str) -> dict:
    load, frames = _cached(loader)
    rows = cancel_rows(plans, load)
    trigger = [r for r in rows if r.entry_model == "trigger"]
    pooled = [r for r in trigger if r.reason in REASONS]
    scored = _scored(pooled)
    baseline = baseline_population(filled_rows(plans, load), scored)
    window = _window(scored)
    return {
        "generated_at": generated_at, "data_as_of": _data_as_of(frames),
        "caption": CAPTION, "risk_cap_label": RISK_CAP_LABEL, "tp1_note": TP1_NOTE,
        "small_n_threshold": SMALL_N, "window": window,
        "rule_changes": _rule_changes(window),
        "out_of_scope": {"manual": manual_count(plans)},
        "headline": {"all": figure(pooled),
                     "without_risk_cap": figure([r for r in pooled if r.reason != "risk_cap"])},
        "baseline": figure(baseline),
        "cards": _cards(trigger, rows),
        "splits": _splits(pooled),
        "rows": [_row_json(r) for r in _newest_first(rows)],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_cancel_precision.py`
Expected: all pass, 0 failed (the payload tests take about 0.3 s each: 10 000 resamples per interval).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_tally` is the largest, C(11)).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/cancel_precision.py tests/analytics/test_cancel_precision.py
git commit -m "feat(analytics): v188 cancelled-plan precision figures and payload

Precision beside net R with week-clustered intervals, small-N marker at 10,
filled-plan baseline, per-reason cards, splits, frozen copy, rule-change dates.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

