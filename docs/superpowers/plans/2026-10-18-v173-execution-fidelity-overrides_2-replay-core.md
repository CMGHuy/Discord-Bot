# v173 Execution fidelity, part 2: exit-engine hooks and the replay core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-7:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (replay core: never resume, one cost basis, the override session)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`) and the task ledger. Every task below implicitly includes those Global Constraints.

Tasks: V173-6..V173-8. V173-6 may run in Wave A (right after V173-1). V173-7 → V173-8 run in order (both write `override_fidelity.py`), and V173-8 also needs V173-6. Part 3 (V173-9, V173-10) builds `replay_override`, `summarise` and the verdict on top of the names created here.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**Tests never touch a database** (Global Constraints): synthetic bars from `tests.helpers.make_ohlcv` or explicit `pd.DatetimeIndex` frames, `TradePlanV2` objects built in the test, no store.

# Phase 2: Replay core

### Task V173-6: `ExitResult.tp1_index` and public `fill_bar_exit`

**Model:** opus — the exit engine shared by every backtest; must stay behaviour-identical

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py:60-73` (`ExitResult`)
- Modify: `swingbot/core/planning/exit_sim_v2.py:79-90` (`_booked`), `:203-222` (`walk_v2`), `:236-248` (`_fill_bar_v2` becomes `fill_bar_exit`)
- Create: `tests/planning/test_exit_sim_v2_replay_hooks.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ExitResult.tp1_index` (`int | None`, default `None`): the TP1 bar's index on a v2 walk that reached TP1. `walk_v2` sets it on both TP1 paths (the single-leg TP1 exit, and the scale-out runner whatever the runner's exit, `acceptance_exit` at the TP1 close included). It is `None` on every other result: pre-TP1 stops, stall and acceptance exits, timeouts, the fill-bar stop, the entry-gap scratch, not-triggered rows and every v1 result. V173-8 and V173-9 read `result.tp1_index`.
  - `fill_bar_exit(df, j: int, fill: float, plan: TradePlanV2, instrument: InstrumentSpec) -> ExitResult | None`: the v2 fill-bar stop check, made public. `_fill_bar_v2` stays as an alias of the same function object, so `_filled` and every entry path are untouched. V173-8's `engine_path` calls it before `walk_v2`.

**Why `tp1_index` is a plain class attribute, not a dataclass field.** The index ledger reads "`ExitResult.tp1_index: int | None = None` (last field, after `cancel_reason`)". A real dataclass field would break an existing exit test: `tests/planning/test_exit_sim_scaleout_witness.py` hashes `dataclasses.asdict(res)` of v1 scale-out results against the frozen `fixtures/scale_out_witness.sha256`, and a new field adds `"tp1_index": None` to every row, changing the hash with no behaviour change. The Global Constraints require every existing exit test to stay green unchanged. So `tp1_index` is declared in the class body **without an annotation** (dataclasses ignore unannotated class attributes). Reads of `result.tp1_index` behave exactly as the ledger describes: `None` by default, set per instance by `_booked`. `asdict`, `==`, `repr` and `dataclasses.fields(ExitResult)` are unchanged. No consumer constructs `ExitResult(..., tp1_index=...)`; only `_booked` sets it.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/planning/test_exit_sim_v2_replay_hooks.py`:

```python
"""v173 §3: the replay hooks on the v2 exit walk.

`ExitResult.tp1_index` is the TP1 bar on both TP1 paths and None everywhere
else; `fill_bar_exit` is the public fill-bar stop check. Neither changes any
existing result: `asdict`, `==` and the dataclass fields are what they were.
Expected numbers were taken from walk_v2 before the change (FREE: v2 fills,
zero costs). Entry is bar 0's price; the walk starts at bar 1.
"""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim import ExitResult, simulate_exit
from swingbot.core.planning.exit_sim_v2 import fill_bar_exit, simulate_exit_v2, walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
TP2_BAR = (112.0, 121.0, 111.0, 120.0)

_FIELDS = ("outcome", "runner_outcome", "entry_index", "exit_index", "entry_price",
           "r_total", "legs", "cancel_reason")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _walk(bars, plan=None, *, scale_out=False, hold=10):
    df = make_ohlcv([ENTRY, *bars])
    return walk_v2(df, 0, 100.0, plan or _plan(), hold, FREE, scale_out=scale_out)


# --- ExitResult's shape is unchanged ---------------------------------------

def test_the_dataclass_fields_are_unchanged():
    assert tuple(f.name for f in dataclasses.fields(ExitResult)) == _FIELDS


def test_tp1_index_defaults_to_none_and_stays_out_of_asdict():
    res = ExitResult(outcome="no_trade", runner_outcome=None, entry_index=0, exit_index=None,
                     entry_price=100.0, r_total=0.0, legs=[])
    assert res.tp1_index is None
    assert "tp1_index" not in dataclasses.asdict(res)


def test_tp1_index_does_not_take_part_in_equality():
    a = _walk([FLAT, TP1_BAR])
    b = dataclasses.replace(a)          # a fresh instance: tp1_index back to the default
    assert b.tp1_index is None and a.tp1_index == 2
    assert a == b


# --- walk_v2 sets it on both TP1 paths --------------------------------------

def test_single_leg_tp1_exit_carries_the_tp1_bar():
    res = _walk([FLAT, TP1_BAR])
    assert (res.outcome, res.exit_index, res.r_total) == ("win", 2, 2.0)
    assert res.tp1_index == 2


def test_scale_out_runner_carries_the_tp1_bar_not_the_runner_exit():
    res = _walk([FLAT, TP1_BAR, TP2_BAR], _plan(tp1_fraction=0.5, tp2=120.0), scale_out=True)
    assert (res.outcome, res.runner_outcome, res.exit_index, res.r_total) == (
        "win", "runner_tp2", 3, 3.0)
    assert res.tp1_index == 2


def test_runner_timeout_still_carries_the_tp1_bar():
    res = _walk([FLAT, TP1_BAR, (110.0, 111.0, 109.0, 110.0)],
                _plan(tp1_fraction=0.5, tp2=130.0), scale_out=True, hold=3)
    assert (res.runner_outcome, res.exit_index) == ("runner_timeout", 3)
    assert res.tp1_index == 2


def test_a_stop_before_tp1_has_no_tp1_index():
    res = _walk([(93.0, 94.0, 92.0, 93.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("loss", 1, -1.4)
    assert res.tp1_index is None


def test_a_timeout_has_no_tp1_index():
    res = _walk([FLAT, FLAT], hold=2)
    assert (res.outcome, res.exit_index) == ("timeout", 2)
    assert res.tp1_index is None


def test_simulate_exit_v2_reaches_the_same_tp1_bar():
    """Market entry: signal bar 0, fill at bar 1's open, TP1 on bar 3."""
    df = make_ohlcv([ENTRY, FLAT, FLAT, TP1_BAR])
    res = simulate_exit_v2(df, 0, _plan(), FREE)
    assert (res.outcome, res.entry_index, res.exit_index) == ("win", 1, 3)
    assert res.tp1_index == 3


def test_v1_results_never_carry_a_tp1_index():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    res = simulate_exit(df, 0, _plan(tp1_fraction=0.5, tp2=120.0), scale_out=True)
    assert res.tp1_index is None


# --- fill_bar_exit ------------------------------------------------------------

def test_fill_bar_exit_is_the_private_check_under_a_public_name():
    assert exit_sim_v2._fill_bar_v2 is fill_bar_exit


def test_fill_bar_exit_stops_out_on_the_fill_bar_at_the_stop_itself():
    df = make_ohlcv([(100.0, 101.0, 94.0, 96.0), FLAT])
    res = fill_bar_exit(df, 0, 100.0, _plan(), FREE)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 0, 0, -1.0)
    assert res.legs[0]["exit_price"] == 95.0 and res.legs[0]["reason"] == "stop"
    assert res.tp1_index is None


def test_fill_bar_exit_returns_none_when_the_fill_bar_never_reaches_the_stop():
    assert fill_bar_exit(make_ohlcv([ENTRY, FLAT]), 0, 100.0, _plan(), FREE) is None


def test_fill_bar_exit_scratches_a_fill_at_or_beyond_the_stop():
    res = fill_bar_exit(make_ohlcv([ENTRY, FLAT]), 0, 94.0, _plan(), FREE)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == (
        "scratch", 0.0, "entry_gap_scratch")
    assert res.tp1_index is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_replay_hooks.py
```

Expected: FAIL at collection with `ImportError: cannot import name 'fill_bar_exit' from 'swingbot.core.planning.exit_sim_v2'`.

- [ ] **Step 3: Add the attribute to `ExitResult`**

In `$WT/swingbot/core/planning/exit_sim.py`, the `ExitResult` dataclass ends with `cancel_reason: str | None = None`. Add directly below that line, inside the class body:

```python
    # v173: the TP1 bar's index on a v2 walk that reached TP1 (the single-leg
    # TP1 exit and the scale-out runner), set per instance by
    # exit_sim_v2._booked; None everywhere else, v1 included. Deliberately a
    # plain class attribute WITHOUT an annotation, so it is not a dataclass
    # field: dataclasses.asdict, ==, repr and fields() are unchanged, and the
    # frozen scale-out witness (a hash of asdict over v1 results) stays
    # byte-identical.
    tp1_index = None
```

Do not add a type annotation: an annotated name becomes a field and breaks `test_exit_sim_scaleout_witness.py`.

- [ ] **Step 4: Set it in `_booked` and `walk_v2`; make the fill-bar check public**

In `$WT/swingbot/core/planning/exit_sim_v2.py`, replace `_booked` (lines 79-90) with:

```python
def _booked(ctx, outcome: str, exit_index: int, legs: list[dict],
            runner_outcome: str | None = None,
            tp1_index: int | None = None) -> ExitResult:
    """The trade's ExitResult, its raw legs booked once through costs.book.
    `tp1_index` (v173) is the TP1 bar on the walks that reached TP1."""
    r_total, booked = costs.book(ctx.costs, direction=ctx.plan.direction,
                                 entry_price=ctx.entry_price, stop_loss=ctx.plan.stop_loss,
                                 legs=legs)
    for raw, leg in zip(legs, booked):
        if "price_basis" in raw:
            leg["price_basis"] = raw["price_basis"]
    result = ExitResult(outcome=outcome, runner_outcome=runner_outcome,
                        entry_index=ctx.entry_index, exit_index=exit_index,
                        entry_price=ctx.entry_price, r_total=r_total, legs=booked)
    result.tp1_index = tp1_index
    return result
```

In `walk_v2` (lines 203-222), change only the two TP1 `_booked` calls so both pass `tp1_index=pre`. The function becomes:

```python
def walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2,
            max_holding_days: int, instrument: InstrumentSpec, *,
            scale_out: bool) -> ExitResult:
    """The v2 exit walk from a filled entry: bars entry_index + 1 .. entry_index
    + max_holding_days (capped at the data). Single-leg unless `scale_out` and
    the plan keeps a runner (tp1_fraction < 1.0), as exit_sim._walk_for.
    v173: a result that reached TP1 carries that bar as `tp1_index`."""
    if abs(entry_price - plan.stop_loss) <= 0:
        return _no_trade(entry_index, entry_price)
    ctx = _context(df, entry_index, entry_price, plan, max_holding_days, instrument, scale_out)
    pre = _pre_tp1_v2(ctx)
    if isinstance(pre, ExitResult):
        return pre
    tp1_fill = fills.exit_fill(ctx.fills, "target", plan.tp1, float(ctx.open_[pre]),
                               plan.direction)
    if not ctx.stall:
        return _booked(ctx, "win", pre, [_leg(1.0, tp1_fill, "tp1", "target")],
                       tp1_index=pre)
    price, exit_index, reason, kind = _runner_v2(df, ctx, pre)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason, tp1_index=pre)
```

Replace `_fill_bar_v2` (lines 236-248) with the public function plus the alias:

```python
def fill_bar_exit(df, j: int, fill: float, plan: TradePlanV2,
                  instrument: InstrumentSpec) -> ExitResult | None:
    """Every v2 fill bar is checked for the stop, never the target: the path
    after the fill is unknown, so stop first. The open came before the fill,
    so a stop reached later on the bar fills at the stop itself.

    Public since v173: walk_v2 starts at bar j + 1, so a replay from a live
    fill (analytics/override_fidelity.py) calls this first, exactly as
    _filled does."""
    direction = plan.direction
    if fills.at_or_beyond_stop(fill, plan.stop_loss, direction):
        return _entry_gap_scratch(j, fill)
    if not fills.stop_touched(float(df["High"].values[j]), float(df["Low"].values[j]),
                              plan.stop_loss, direction):
        return None
    ctx = _context(df, j, fill, plan, 0, instrument, False)
    return _booked(ctx, "loss", j, [_leg(1.0, plan.stop_loss, "stop", "stop")])


#: The pre-v173 private name; `_filled` keeps calling it.
_fill_bar_v2 = fill_bar_exit
```

`_filled` (line 251 onward) is not edited: it still calls `_fill_bar_v2(df, j, fill, plan, instrument)`. The alias must sit above `_filled` in the file (module-level names resolve at call time, so either order works, but keep it next to the function it names).

- [ ] **Step 5: Run the new test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_replay_hooks.py
```

Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 6: Run every existing exit test, unchanged**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout_witness.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_single.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_runner_structure.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_acceptance.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py
```

Expected: every file PASS with `0 failed`, `0 xfailed`, and **no existing test file edited**: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides status --short tests/` shows only `?? tests/planning/test_exit_sim_v2_replay_hooks.py`. If the scale-out witness fails, `tp1_index` was declared with an annotation: remove it (Step 3).

Then let the diff-selector catch any other caller of `ExitResult` or `_fill_bar_v2` (backtest witnesses, arms):

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed`. If it widens to the full suite, hand the run to the `test-runner` subagent rather than reading its output here.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim_v2.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim.py
```

Expected: `_booked`, `walk_v2` and `fill_bar_exit` are not listed (each stays below rank C). A function the command lists that this task did not touch was already there; leave it.

- [ ] **Step 8: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/planning/exit_sim.py swingbot/core/planning/exit_sim_v2.py tests/planning/test_exit_sim_v2_replay_hooks.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): ExitResult.tp1_index and a public fill_bar_exit for the override replay"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-7: `override_fidelity`: constants, session assignment, plan readers, `OverrideRow`

**Model:** opus — no-lookahead territory (timestamp to session mapping)

**Files:**
- Create: `swingbot/core/analytics/override_fidelity.py`
- Create: `tests/analytics/test_override_fidelity_sessions.py`

**Interfaces:**
- Consumes: `swingbot.core.market.session` (`RTH_OPEN`, `US_MARKET_TZ`, `nyse_calendar`, `session_close`, all existing); `swingbot.core.planning.plan_types.PlanStatus` (existing).
- Produces (all in `swingbot/core/analytics/override_fidelity.py`; V173-8..V173-12 import them by these names):
  - Constants: `MANUAL_REASONS = ("manual", "manual_bulk")`; `STATUSES = ("resolved", "open", "stale", "ambiguous", "parity_mismatch", "split_affected", "unreplayable")`; `EXCLUDED_STATUSES = ("stale", "ambiguous", "parity_mismatch", "split_affected", "unreplayable")`; `TIMEOUT_REASONS = ("timeout", "runner_timeout")` (the two reasons `walk_v2` gives when it stops at `ctx.end`, which is also where it clips at the data end); `DEAD_BAND = 0.05`; `VERDICT_FLOOR = 30`; `WEEK_FLOOR = 10`; `EXCLUDED_CAP = 0.20`; `SPLIT_TOLERANCE = 0.02`; `LEDGER_ID = "v173-override-fidelity"`; `ROW_FIELDS` (the 19 row keys, in order).
  - `@dataclass(frozen=True) SessionHit(session: date, price_kind: str)`, `price_kind` `"open"` or `"close"`.
  - `assign_session(at_iso: str | None) -> SessionHit | None` per the Global Constraints table; a naive timestamp is read as UTC (every `status_history` `at` is written by `datetime.now(timezone.utc).isoformat()`); `None` for empty, unparseable or outside the NYSE calendar (2018-01-02..2030-12-31).
  - `latest_completed_session(now: datetime) -> date`: the last session whose `session_close` (ET) is at or before `now`; naive `now` read as UTC; `ValueError` outside the calendar.
  - `session_index(df, day: date | None) -> int | None`: positional index of the bar dated `day`.
  - `transition_at(plan, status: str) -> str | None`: `at` of the **first** `status_history` entry with `status`.
  - `override_entry(plan) -> dict | None`: the last `status_history` entry, when the plan is CLOSED and that entry is `CLOSED` with a reason in `MANUAL_REASONS`.
  - `is_override(plan) -> bool`.
  - `state_at_close(plan) -> str`: `"PARTIAL"` when any `status_history` entry is `PARTIAL`, else `"ACTIVE"`.
  - `@dataclass(frozen=True) OverrideRow` with exactly the 19 row fields of the Global Constraints, in that order (`plan_id, ticker, horizon, direction, state_at_close, close_date, bulk, approx, price_source, status` required; `actual_r, engine_r, delta_r, actual_usd, engine_usd, delta_usd, engine_exit_reason, outcome` default `None`; `source` default `"manual"`); `ValueError` on a `status` not in `STATUSES`; property `entry_date -> date | None` (= `close_date`, the attribute `stats.group_by_week` reads); `to_dict() -> dict` with `close_date` as an ISO string or `None`.
  - `outcome_of(delta_r: float | None) -> str | None`: `"helped"` above `+DEAD_BAND`, `"hurt"` below `-DEAD_BAND`, `"neutral"` otherwise (the band edges are neutral), `None` for `None`.
  - Test helper `tests.analytics.test_override_fidelity_sessions.override_plan(...)` and the stamps `FILL_AT`, `TP1_AT`, `CLOSE_AT`: V173-8 (and Part 3's tests, if they choose) import them.

**Why the session rules look like this.** §3's table: the override session is the session the human acted in, and the engine is never shown that session's range as a later path. A stamp before 09:30 ET on a session day belongs to that day's open (the unstamped exit price is that open); from 09:30 on, regular hours and after-hours alike, to that day's close. A stamp on a weekend or holiday belongs to the last session before it, at its close. ET, not UTC, decides the date: `2026-10-02T02:30Z` is 22:30 ET on 2026-10-01.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_sessions.py`:

```python
"""v173 §3: override sessions, plan readers and the OverrideRow shape.

Dates: 2026-10-01 is a Thursday in EDT (UTC-4); 2026-11-26 is Thanksgiving,
2026-11-27 a 13:00 ET early close and 2026-12-01 a Tuesday in EST (UTC-5).
"""
import dataclasses
import datetime as dt

import pandas as pd
import pytest

from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument import stats
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2

U = dt.timezone.utc
FILL_AT = "2026-10-01T14:00:00+00:00"    # Thu 10:00 ET
TP1_AT = "2026-10-05T15:00:00+00:00"     # Mon 11:00 ET
CLOSE_AT = "2026-10-07T18:00:00+00:00"   # Wed 14:00 ET

ROW_KEYS = ("plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason", "outcome", "source")


def override_plan(*, reason="manual", partial=False, status=PlanStatus.CLOSED,
                  history=None, close_at=CLOSE_AT, override=None, **kw):
    """A live plan record closed by a manual override (shared by the v173 tests).

    `override` is the stamp dict put on the CLOSED entry; leave it None for an
    unstamped close (the key is then absent, as on every pre-v173 close)."""
    if history is None:
        history = [{"status": "ACTIVE", "reason": "filled", "at": FILL_AT}]
        if partial:
            history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": TP1_AT})
        closed = {"status": "CLOSED", "reason": reason, "at": close_at}
        if override is not None:
            closed["override"] = override
        history.append(closed)
    legs = ([{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
              "closed_at": TP1_AT}] if partial else [])
    base = dict(
        plan_id="p1", ticker="T", created_at="2026-09-30", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish", entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=110.0,
        tp1_fraction=0.5 if partial else 1.0, tp2=120.0 if partial else None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0, quality_score=0,
        quality_breakdown=[], badge="WEAK", badge_stats={}, status=status,
        status_history=history, legs_realized=legs,
    )
    base.update(kw)
    return TradePlanV2(**base)


# --- frozen constants --------------------------------------------------------

def test_the_frozen_constants():
    assert of.MANUAL_REASONS == ("manual", "manual_bulk")
    assert of.STATUSES == ("resolved", "open", "stale", "ambiguous", "parity_mismatch",
                           "split_affected", "unreplayable")
    assert of.EXCLUDED_STATUSES == tuple(s for s in of.STATUSES if s not in ("resolved", "open"))
    assert of.TIMEOUT_REASONS == ("timeout", "runner_timeout")
    assert (of.DEAD_BAND, of.VERDICT_FLOOR, of.WEEK_FLOOR, of.EXCLUDED_CAP,
            of.SPLIT_TOLERANCE) == (0.05, 30, 10, 0.20, 0.02)
    assert of.LEDGER_ID == "v173-override-fidelity"
    assert of.ROW_FIELDS == ROW_KEYS


# --- assign_session: one test per row of the §3 table ------------------------

@pytest.mark.parametrize("at, session, kind", [
    ("2026-10-01T13:00:00+00:00", dt.date(2026, 10, 1), "open"),    # 09:00 ET, before the open
    ("2026-10-01T13:29:59+00:00", dt.date(2026, 10, 1), "open"),    # 09:29:59 ET
    ("2026-10-01T13:30:00+00:00", dt.date(2026, 10, 1), "close"),   # 09:30 ET, the open itself
    ("2026-10-01T18:00:00+00:00", dt.date(2026, 10, 1), "close"),   # regular hours
    ("2026-10-01T22:00:00+00:00", dt.date(2026, 10, 1), "close"),   # 18:00 ET, after the close
    ("2026-12-01T14:00:00+00:00", dt.date(2026, 12, 1), "open"),    # 09:00 EST
    ("2026-12-01T14:30:00Z", dt.date(2026, 12, 1), "close"),        # 09:30 EST, Z suffix
    ("2026-11-27T14:00:00+00:00", dt.date(2026, 11, 27), "open"),   # early-close day, pre-open
    ("2026-11-27T19:00:00+00:00", dt.date(2026, 11, 27), "close"),  # 14:00 EST, after the 13:00 close
])
def test_a_session_day(at, session, kind):
    assert of.assign_session(at) == of.SessionHit(session, kind)


def test_the_utc_date_is_not_the_et_date():
    """02:30 UTC on Oct 2 is 22:30 ET on Oct 1: Oct 1's close, not Oct 2's open."""
    assert of.assign_session("2026-10-02T02:30:00+00:00") == of.SessionHit(
        dt.date(2026, 10, 1), "close")


@pytest.mark.parametrize("at, session", [
    ("2026-10-03T15:00:00+00:00", dt.date(2026, 10, 2)),   # Saturday -> Friday
    ("2026-10-05T03:00:00+00:00", dt.date(2026, 10, 2)),   # Sunday 23:00 ET (Monday in UTC)
    ("2026-11-26T15:00:00+00:00", dt.date(2026, 11, 25)),  # Thanksgiving -> Wednesday
])
def test_a_non_trading_day_takes_the_last_session_close(at, session):
    assert of.assign_session(at) == of.SessionHit(session, "close")


def test_a_naive_timestamp_is_read_as_utc():
    assert of.assign_session("2026-10-01T13:00:00") == of.SessionHit(dt.date(2026, 10, 1), "open")


@pytest.mark.parametrize("at", [None, "", "garbage", "2017-06-01T15:00:00+00:00",
                                "2031-01-02T15:00:00+00:00"])
def test_no_session_for_missing_unparseable_or_out_of_calendar(at):
    assert of.assign_session(at) is None


# --- latest_completed_session ------------------------------------------------

@pytest.mark.parametrize("now, expected", [
    (dt.datetime(2026, 10, 1, 19, 59, tzinfo=U), dt.date(2026, 9, 30)),   # 15:59 ET: still open
    (dt.datetime(2026, 10, 1, 20, 0, tzinfo=U), dt.date(2026, 10, 1)),    # 16:00 ET: closed
    (dt.datetime(2026, 10, 3, 12, 0, tzinfo=U), dt.date(2026, 10, 2)),    # Saturday
    (dt.datetime(2026, 10, 5, 13, 0, tzinfo=U), dt.date(2026, 10, 2)),    # Monday pre-open
    (dt.datetime(2026, 11, 27, 18, 0, tzinfo=U), dt.date(2026, 11, 27)),  # 13:00 EST early close
    (dt.datetime(2026, 11, 27, 17, 59, tzinfo=U), dt.date(2026, 11, 25)), # before it; 26th a holiday
    (dt.datetime(2026, 10, 1, 20, 0), dt.date(2026, 10, 1)),              # naive = UTC
])
def test_latest_completed_session(now, expected):
    assert of.latest_completed_session(now) == expected


def test_latest_completed_session_refuses_outside_the_calendar():
    with pytest.raises(ValueError):
        of.latest_completed_session(dt.datetime(2017, 6, 1, tzinfo=U))


# --- session_index -----------------------------------------------------------

def _frame(days):
    idx = pd.DatetimeIndex(days)
    ones = [1.0] * len(idx)
    return pd.DataFrame({"Open": ones, "High": ones, "Low": ones, "Close": ones,
                         "Volume": ones}, index=idx)


def test_session_index_finds_the_bar_by_date():
    df = _frame(["2026-10-01", "2026-10-02", "2026-10-05"])
    assert of.session_index(df, dt.date(2026, 10, 5)) == 2
    assert of.session_index(df, dt.date(2026, 10, 1)) == 0


def test_session_index_is_none_for_a_missing_day_or_no_bars():
    df = _frame(["2026-10-01", "2026-10-02", "2026-10-05"])
    assert of.session_index(df, dt.date(2026, 10, 3)) is None
    assert of.session_index(df, None) is None
    assert of.session_index(None, dt.date(2026, 10, 5)) is None
    assert of.session_index(df.iloc[0:0], dt.date(2026, 10, 5)) is None


# --- plan readers --------------------------------------------------------------

def test_transition_at_reads_the_first_entry_with_the_status():
    plan = override_plan(partial=True)
    assert of.transition_at(plan, "ACTIVE") == FILL_AT
    assert of.transition_at(plan, "PARTIAL") == TP1_AT
    assert of.transition_at(plan, "CLOSED") == CLOSE_AT
    assert of.transition_at(override_plan(), "PARTIAL") is None


@pytest.mark.parametrize("reason", ["manual", "manual_bulk"])
def test_a_manual_close_is_an_override(reason):
    plan = override_plan(reason=reason)
    assert of.override_entry(plan) == plan.status_history[-1]
    assert of.is_override(plan)


def test_an_engine_close_is_not_an_override():
    plan = override_plan(reason="tp1_runner_trail", partial=True)
    assert of.override_entry(plan) is None and not of.is_override(plan)


def test_only_the_last_entry_counts():
    """A manual reason earlier in the history (never the terminal one) is not an override."""
    history = [{"status": "ACTIVE", "reason": "manual", "at": FILL_AT},
               {"status": "CLOSED", "reason": "stop", "at": CLOSE_AT}]
    plan = override_plan(history=history)
    assert not of.is_override(plan)


def test_an_open_or_empty_plan_is_not_an_override():
    active = override_plan(status=PlanStatus.ACTIVE,
                           history=[{"status": "ACTIVE", "reason": "filled", "at": FILL_AT}])
    assert not of.is_override(active)
    assert not of.is_override(override_plan(history=[]))


def test_state_at_close():
    assert of.state_at_close(override_plan(partial=True)) == "PARTIAL"
    assert of.state_at_close(override_plan()) == "ACTIVE"


# --- OverrideRow -------------------------------------------------------------

def _row(**kw):
    base = dict(plan_id="p1", ticker="T", horizon="4w", direction="bullish",
                state_at_close="ACTIVE", close_date=dt.date(2026, 10, 7), bulk=False,
                approx=False, price_source="quote", status="resolved")
    base.update(kw)
    return of.OverrideRow(**base)


def test_row_fields_are_exactly_the_payload_keys_in_order():
    assert tuple(f.name for f in dataclasses.fields(of.OverrideRow)) == ROW_KEYS


def test_row_defaults():
    row = _row()
    assert row.source == "manual"
    assert all(getattr(row, key) is None for key in ROW_KEYS[10:18])


def test_to_dict_writes_the_close_date_as_iso():
    row = _row(actual_r=0.5, engine_r=0.2, delta_r=0.3, outcome="helped")
    body = row.to_dict()
    assert tuple(body) == ROW_KEYS
    assert body["close_date"] == "2026-10-07"
    assert body["delta_r"] == 0.3 and body["outcome"] == "helped"
    assert _row(close_date=None).to_dict()["close_date"] is None


def test_entry_date_is_the_close_date_for_week_clustering():
    row = _row()
    assert row.entry_date == dt.date(2026, 10, 7)
    assert stats.iso_week_key(row.entry_date) == "2026-W41"
    assert list(stats.group_by_week([row])) == ["2026-W41"]


def test_row_is_frozen_and_refuses_an_unknown_status():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _row().status = "open"
    with pytest.raises(ValueError):
        _row(status="timeout")


# --- outcome_of: the frozen ±0.05R dead band ----------------------------------

@pytest.mark.parametrize("delta, outcome", [
    (0.051, "helped"), (0.05, "neutral"), (0.0, "neutral"), (-0.05, "neutral"),
    (-0.051, "hurt"), (2.0, "helped"), (-1.3, "hurt"), (None, None),
])
def test_outcome_of(delta, outcome):
    assert of.outcome_of(delta) == outcome
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
```

Expected: FAIL at collection with `ImportError: cannot import name 'override_fidelity' from 'swingbot.core.analytics'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Implement the module**

Create `$WT/swingbot/core/analytics/override_fidelity.py`:

```python
"""v173 §3: what a manual override did against the engine -- the pure core.

A manual close (`_close_plan`, reason "manual" or "manual_bulk") ends a plan
the engine would otherwise have kept managing. This module replays that plan
through the v2 exit engine from its real fill and compares the two arms on one
cost basis. It is pure: no store, no network, no file reads. Plans, bars
(`runner_path.cached_daily_bars`, read by the caller) and linked trades come
in as arguments.

This first block holds the frozen constants, the timestamp-to-session rule,
the plan readers and the row shape. The engine path and the two arms follow
(v173 V173-8); `replay_override` and `summarise` close the module (V173-9,
V173-10). The constants are pre-registered (spec §4): changing any of them is
a new spec, never an edit.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.planning.plan_types import PlanStatus

#: The terminal reasons of a manual close; "manual_bulk" rows are shown, never summed.
MANUAL_REASONS = ("manual", "manual_bulk")
#: Every row carries exactly one of these (spec §3 status table).
STATUSES = ("resolved", "open", "stale", "ambiguous", "parity_mismatch", "split_affected",
            "unreplayable")
#: Statuses left out of the sums and capped at EXCLUDED_CAP for the verdict.
EXCLUDED_STATUSES = ("stale", "ambiguous", "parity_mismatch", "split_affected",
                     "unreplayable")
#: walk_v2's reasons for stopping at ctx.end -- the hold cap, or the data end.
TIMEOUT_REASONS = ("timeout", "runner_timeout")
#: Frozen (spec §3, §4).
DEAD_BAND = 0.05
VERDICT_FLOOR = 30
WEEK_FLOOR = 10
EXCLUDED_CAP = 0.20
SPLIT_TOLERANCE = 0.02
LEDGER_ID = "v173-override-fidelity"

#: Longest run of calendar days with no NYSE session in the covered years is
#: four; two weeks of look-back always reaches the previous session.
_LOOKBACK = dt.timedelta(days=14)


@dataclass(frozen=True)
class SessionHit:
    """The NYSE session a timestamp belongs to, and which of its prices an
    unstamped exit would have got: "open" (before 09:30 ET) or "close"."""
    session: dt.date
    price_kind: str


def _to_et(moment: dt.datetime) -> dt.datetime:
    if moment.tzinfo is None:          # status_history stamps are written in UTC
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(US_MARKET_TZ)


def _parse_et(at_iso) -> dt.datetime | None:
    if not at_iso:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(at_iso))
    except ValueError:
        return None
    return _to_et(moment)


def _session_on_or_before(day: dt.date) -> dt.date | None:
    """The last NYSE session on or before `day`; None outside the calendar."""
    cal = nyse_calendar()
    if day < cal.first or day > cal.last:
        return None
    prior = cal.sessions(day - _LOOKBACK, day)
    return prior[-1] if prior else None


def assign_session(at_iso: str | None) -> SessionHit | None:
    """The override session of an ISO timestamp, in America/New_York.

    Session day before 09:30 -> that day, "open"; from 09:30 on (regular
    hours or after the close, early closes included) -> that day, "close";
    a non-session day -> the last session before it, "close". None when the
    stamp is missing, unparseable or outside the calendar."""
    local = _parse_et(at_iso)
    if local is None:
        return None
    day = local.date()
    prior = _session_on_or_before(day)
    if prior is None:
        return None
    if prior == day:
        return SessionHit(day, "open" if local.time() < RTH_OPEN else "close")
    return SessionHit(prior, "close")


def latest_completed_session(now: dt.datetime) -> dt.date:
    """The last NYSE session whose regular close (ET) is at or before `now`:
    the newest bar a fresh daily cache can hold."""
    local = _to_et(now)
    day = local.date()
    if nyse_calendar().is_session(day) and local.time() >= session_close(day):
        return day
    prior = _session_on_or_before(day - dt.timedelta(days=1))
    if prior is None:
        raise ValueError(f"{now.isoformat()} lies outside the NYSE calendar")
    return prior


def session_index(df, day: dt.date | None) -> int | None:
    """Positional index of the bar dated `day`; None when absent."""
    if df is None or len(df) == 0 or day is None:
        return None
    hits = np.flatnonzero(pd.DatetimeIndex(df.index).date == day)
    return int(hits[0]) if hits.size else None


def transition_at(plan, status: str) -> str | None:
    """`at` of the first status_history entry with `status`."""
    return next((entry.get("at") for entry in plan.status_history or []
                 if entry.get("status") == status), None)


def override_entry(plan) -> dict | None:
    """The terminal CLOSED entry of a manual close; None for any other plan."""
    history = plan.status_history or []
    if plan.status != PlanStatus.CLOSED or not history:
        return None
    last = history[-1]
    if last.get("status") == PlanStatus.CLOSED and last.get("reason") in MANUAL_REASONS:
        return last
    return None


def is_override(plan) -> bool:
    return override_entry(plan) is not None


def state_at_close(plan) -> str:
    """"PARTIAL" when TP1 had filled before the override, else "ACTIVE"."""
    partial = any(entry.get("status") == PlanStatus.PARTIAL
                  for entry in plan.status_history or [])
    return PlanStatus.PARTIAL if partial else PlanStatus.ACTIVE


@dataclass(frozen=True)
class OverrideRow:
    """One override against the engine. R is on the plan's initial risk, net
    of modelled costs and pre-tax; the *_usd fields are None without a dollar
    risk. Only `resolved` rows that are neither bulk nor approx are summed."""
    plan_id: str
    ticker: str
    horizon: str
    direction: str
    state_at_close: str
    close_date: dt.date | None
    bulk: bool
    approx: bool
    price_source: str
    status: str
    actual_r: float | None = None
    engine_r: float | None = None
    delta_r: float | None = None
    actual_usd: float | None = None
    engine_usd: float | None = None
    delta_usd: float | None = None
    engine_exit_reason: str | None = None
    outcome: str | None = None
    source: str = "manual"

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"unknown override status {self.status!r}")

    @property
    def entry_date(self) -> dt.date | None:
        """The close date, under the name stats.group_by_week reads."""
        return self.close_date

    def to_dict(self) -> dict:
        body = asdict(self)
        body["close_date"] = self.close_date.isoformat() if self.close_date else None
        return body


#: The row keys of the report payload, in order.
ROW_FIELDS = tuple(OverrideRow.__dataclass_fields__)


def outcome_of(delta_r: float | None) -> str | None:
    """helped / hurt / neutral under the frozen ±DEAD_BAND (edges are neutral)."""
    if delta_r is None:
        return None
    if delta_r > DEAD_BAND:
        return "helped"
    if delta_r < -DEAD_BAND:
        return "hurt"
    return "neutral"
```

`PlanStatus` (`plan_types.py:6`) is a class of plain string constants, so `state_at_close` returns the `str` `"PARTIAL"` or `"ACTIVE"`. `ROW_FIELDS` is derived from the dataclass so the payload key list can never drift from the row; the test pins it to the Global Constraints list.

- [ ] **Step 4: Run the test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
```

Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: no output (every function below rank C, i.e. CC < 11).

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_sessions.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override_fidelity sessions, plan readers and OverrideRow"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-8: Engine path from the fill, `leg_kind`, both arms through `costs.book`, dollar risk

**Model:** opus — exit-engine replay and cost basis feeding a frozen verdict

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (created by V173-7: extend the import block, append the engine and arm functions at the end)
- Create: `tests/analytics/test_override_fidelity_arms.py`

**Interfaces:**
- Consumes:
  - V173-6: `exit_sim_v2.fill_bar_exit(df, j, fill, plan, instrument) -> ExitResult | None`; `ExitResult.tp1_index`.
  - V173-7: `override_fidelity` module and its constants; test helper `tests.analytics.test_override_fidelity_sessions.override_plan`.
  - Existing: `exit_sim_v2.walk_v2` (`exit_sim_v2.py:203`), `exit_sim._hold_cap_bars` (`exit_sim.py:613`), `strategy_types.HORIZONS`, `contract.resolve` (`contract.py:130`), `costs.book` (`costs.py:41`), `time_exit.TIME_EXIT_REASON` (`"time_exit"`).
- Produces (in `override_fidelity.py`; V173-9 builds `replay_override` from these):
  - `INSTRUMENT = contract.resolve("v2")`.
  - `hold_cap_bars(plan) -> int` = `exit_sim._hold_cap_bars(plan, HORIZONS[plan.horizon_key]["max_holding_days"])`, the cap `simulate_exit_v2` uses.
  - `engine_frame(df, ov_idx: int) -> pd.DataFrame`: a copy of `df` whose bar `ov_idx` has `High = max(Open, Close)` and `Low = min(Open, Close)`; every other bar and the input frame are unchanged.
  - `engine_path(plan, df, fill_idx: int) -> ExitResult`: `fill_bar_exit(df, fill_idx, plan.entry_price, plan, INSTRUMENT)`, and when that is `None`, `walk_v2(df, fill_idx, plan.entry_price, plan, hold_cap_bars(plan), INSTRUMENT, scale_out=plan.tp1_fraction < 1.0)`. The plan's original `stop_loss` is the stop, as at the fill. V173-9 calls it twice: on the real frame (parity, ambiguity) and on `engine_frame(df, ov_idx)` (the engine arm).
  - `leg_kind(reason: str) -> str`: `"target"` for `tp1`, `runner_tp2`; `"close"` for `timeout`, `runner_timeout`, `acceptance_exit`, `stall_exit`, `runner_progress_stall`, `time_exit`; `"stop"` for every other reason (`stop`, `breakeven_stop`, `runner_be`, `runner_trail`, ...). It matches the kind `walk_v2` books each reason with.
  - `live_tp1_leg(plan) -> dict | None`: `{"fraction": plan.tp1_fraction, "exit_price": <legs_realized "tp1" leg's exit_price>, "reason": "tp1", "kind": "target"}`, or `None` when the plan has no realised TP1 leg with a price.
  - `actual_r(plan, exit_price: float, state: str) -> float` and `engine_r(plan, result: ExitResult, state: str) -> float`: each **one** `costs.book(INSTRUMENT.cost_model, direction=plan.direction, entry_price=plan.entry_price, stop_loss=plan.stop_loss, legs=[...])` call, per the Global Constraints "One cost basis". Both raise `ValueError` when the entry is at or beyond the stop, when a PARTIAL plan has no `live_tp1_leg`, or (`engine_r`) when the result has no leg left to book. V173-9 maps any `ValueError` here to `unreplayable`.
  - `dollar_risk(plan, trade: dict | None) -> float | None` = `float(trade["shares"]) * abs(plan.entry_price - plan.stop_loss)`; `None` with no trade, no or unparseable `shares`, a missing price, or a non-positive result.
  - `to_usd(r: float | None, risk: float | None) -> float | None` = `round(r * risk, 2)`, `None` if either is `None`.

**What the arms mean.**

- **Actual arm.** The human's exit. On a PARTIAL plan it is the live TP1 leg plus a remainder of `1 - tp1_fraction` at the override price. On an ACTIVE plan it is the whole position at the override price. The manual leg is booked as kind `"stop"`: 10 bps, a market order taken at a moment the engine did not choose.
- **Engine arm.** The replay's legs, each booked with the kind the engine itself gives that reason. On a PARTIAL plan the replay's own `tp1` leg is dropped and the **live** TP1 leg is used, so both arms share one TP1 leg and the delta is decided by the remainder alone. The remaining legs are re-scaled so their fractions sum to the remainder. In the normal case (one runner leg of `1 - tp1_fraction`) the scale is exactly 1.
- **Cost parity.** Both arms share entry, stop, entry slippage and the TP1 leg. So when the actual exit price equals the engine's exit price on a **stop-kind** engine exit (stop, breakeven, runner trail), `delta_r` is exactly 0. When the engine exit is a target or a close, the same price still differs by the slippage gap (5 bps against the manual leg's 10). That gap is a real cost of exiting by hand, not a bias, and a test pins it so nobody "fixes" it.
- **Bars before the fill.** On the single-leg paths (stop, TP1, timeout) no bar before the fill is read. On a runner, the chandelier trail reads ATR(14) and the structure frame, which can reach up to 13 sessions back from the trailing bar. That is past data, exactly as in every backtest, never lookahead. The invariance test below is therefore pinned on a single-leg plan; Part 3's no-lookahead test should use the same kind of plan, or change only bars at least 30 sessions before the fill.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_arms.py`:

```python
"""v173 §3: the engine path from the live fill and the two cost-basis arms.

Every figure is booked through the real v2 instrument (resolve("v2"): 5 bps
entry and target/close slippage, 10 bps stop slippage, no commission). With
entry 100 and stop 95 the slipped entry is 100.05 and the risk 5.05, so e.g.
a manual exit at 104 is (104 * 0.999 - 100.05) / 5.05 = 0.762R. Expected
numbers were computed with costs.book before this module existed.
"""
import dataclasses

import pytest

from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.planning.exit_sim import ExitResult
from tests.analytics.test_override_fidelity_sessions import override_plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
TP2_BAR = (112.0, 121.0, 111.0, 120.0)
STOP_BAR = (96.0, 96.5, 94.0, 95.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)      # STALL_EXIT_ENABLED, RUNNER_STRUCTURE_EXIT at code defaults


def _active(**kw):
    return override_plan(**kw)


def _partial(tp1_price=110.0, **kw):
    plan = override_plan(partial=True, **kw)
    return dataclasses.replace(plan, legs_realized=[
        {"fraction": 0.5, "exit_price": tp1_price, "r": 2.0, "reason": "tp1"}])


def _trail_bars():
    """TP1 on bar 2, twenty rising bars that ratchet the trail, then a gap down."""
    rising = [(110.0 + i, 111.0 + i, 109.0 + i, 110.5 + i) for i in range(20)]
    return make_ohlcv([ENTRY, FLAT, TP1_BAR, *rising, (125.0, 125.5, 100.0, 101.0)])


# --- instrument and hold cap ---------------------------------------------------

def test_the_replay_books_on_the_v2_instrument():
    assert of.INSTRUMENT is resolve("v2")
    model = of.INSTRUMENT.cost_model
    assert (model.slippage_bps, model.stop_slippage_bps, model.commission_per_share) == (
        5.0, 10.0, 0.0)


def test_hold_cap_bars_is_the_simulators_cap():
    assert of.hold_cap_bars(_active()) == 28                    # HORIZONS["4w"]
    assert of.hold_cap_bars(_active(horizon_key="1w")) == 7
    assert of.hold_cap_bars(_active(hold_cap_bars=10)) == 10    # the plan's own cap wins


# --- engine_frame ----------------------------------------------------------------

def test_engine_frame_clamps_only_the_override_bar_and_leaves_the_input_alone():
    df = make_ohlcv([ENTRY, (101.0, 108.0, 96.0, 103.0), FLAT])
    frame = of.engine_frame(df, 1)
    assert frame.iloc[1][["Open", "High", "Low", "Close"]].tolist() == [101.0, 103.0, 101.0, 103.0]
    assert frame.iloc[0].tolist() == df.iloc[0].tolist()
    assert frame.iloc[2].tolist() == df.iloc[2].tolist()
    assert df.iloc[1][["High", "Low"]].tolist() == [108.0, 96.0]


# --- engine_path ----------------------------------------------------------------

def test_engine_path_checks_the_fill_bar_first():
    res = of.engine_path(_active(), make_ohlcv([(100.0, 101.0, 94.0, 96.0), FLAT]), 0)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 0, 0, -1.019)


def test_engine_path_walks_from_the_fill_index():
    res = of.engine_path(_active(), make_ohlcv([FLAT, ENTRY, FLAT, FLAT]), 1)
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 3)
    assert res.legs[0]["reason"] == "timeout"


def test_engine_path_stops_at_the_hold_cap():
    res = of.engine_path(_active(hold_cap_bars=2), make_ohlcv([ENTRY, *[FLAT] * 6]), 0)
    assert (res.outcome, res.exit_index) == ("timeout", 2)


def test_engine_path_scales_out_only_when_the_plan_keeps_a_runner():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    single = of.engine_path(_active(), df, 0)
    runner = of.engine_path(_active(tp1_fraction=0.5, tp2=120.0), df, 0)
    assert [leg["reason"] for leg in single.legs] == ["tp1"]
    assert [leg["reason"] for leg in runner.legs] == ["tp1", "runner_tp2"]
    assert single.tp1_index == runner.tp1_index == 2


def test_bars_before_the_fill_never_change_a_single_leg_engine_r():
    quiet = make_ohlcv([*[(50.0, 51.0, 49.0, 50.0)] * 5, ENTRY, FLAT, TP1_BAR])
    wild = make_ohlcv([*[(80.0, 90.0, 70.0, 85.0)] * 5, ENTRY, FLAT, TP1_BAR])
    a = of.engine_r(_active(), of.engine_path(_active(), quiet, 5), "ACTIVE")
    b = of.engine_r(_active(), of.engine_path(_active(), wild, 5), "ACTIVE")
    assert a == b == 1.959


# --- leg_kind ---------------------------------------------------------------------

@pytest.mark.parametrize("reason, kind", [
    ("tp1", "target"), ("runner_tp2", "target"),
    ("timeout", "close"), ("runner_timeout", "close"), ("acceptance_exit", "close"),
    ("stall_exit", "close"), ("runner_progress_stall", "close"), ("time_exit", "close"),
    ("stop", "stop"), ("breakeven_stop", "stop"), ("runner_be", "stop"),
    ("runner_trail", "stop"), ("entry_gap_scratch", "stop"),
])
def test_leg_kind_matches_the_engines_booking(reason, kind):
    assert of.leg_kind(reason) == kind


# --- live_tp1_leg -------------------------------------------------------------------

def test_live_tp1_leg_reads_the_realised_tp1_price():
    assert of.live_tp1_leg(_partial(tp1_price=110.4)) == {
        "fraction": 0.5, "exit_price": 110.4, "reason": "tp1", "kind": "target"}


def test_live_tp1_leg_is_none_without_a_priced_tp1_leg():
    assert of.live_tp1_leg(_active()) is None
    plan = dataclasses.replace(_partial(), legs_realized=[{"fraction": 0.5, "reason": "tp1"}])
    assert of.live_tp1_leg(plan) is None


# --- actual_r -----------------------------------------------------------------------

def test_actual_r_active_books_the_whole_position_as_a_stop_kind_exit():
    assert of.actual_r(_active(), 104.0, "ACTIVE") == 0.762


def test_actual_r_partial_books_the_live_tp1_leg_and_the_remainder_together():
    # 0.5 * (110 * 0.9995 - 100.05) / 5.05 + 0.5 * 0.76158 = 1.360
    assert of.actual_r(_partial(), 104.0, "PARTIAL") == 1.36


def test_actual_r_refuses_an_entry_at_the_stop():
    with pytest.raises(ValueError):
        of.actual_r(_active(entry_price=95.0), 96.0, "ACTIVE")


def test_actual_r_refuses_a_partial_plan_without_a_tp1_leg():
    with pytest.raises(ValueError):
        of.actual_r(_active(tp1_fraction=0.5), 104.0, "PARTIAL")


# --- engine_r -------------------------------------------------------------------------

def test_engine_r_rebooks_an_active_result_to_its_own_r_total():
    for bars in ([ENTRY, FLAT, TP1_BAR], [ENTRY, STOP_BAR], [ENTRY, FLAT, FLAT]):
        res = of.engine_path(_active(), make_ohlcv(bars), 0)
        assert of.engine_r(_active(), res, "ACTIVE") == res.r_total


def test_engine_r_keeps_both_legs_of_an_active_plan_that_reaches_tp1_later():
    plan = _active(tp1_fraction=0.5, tp2=120.0)
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert of.engine_r(plan, res, "ACTIVE") == res.r_total == 2.949


def test_engine_r_partial_uses_the_live_tp1_leg_and_the_replays_runner():
    plan = _partial()
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert res.runner_outcome == "runner_tp2"
    assert of.engine_r(plan, res, "PARTIAL") == res.r_total == 2.949


def test_the_tp1_leg_is_shared_so_its_price_never_moves_the_delta():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    deltas = []
    for tp1_price in (110.0, 111.0):
        plan = _partial(tp1_price=tp1_price)
        res = of.engine_path(plan, df, 0)
        deltas.append(round(of.actual_r(plan, 104.0, "PARTIAL")
                            - of.engine_r(plan, res, "PARTIAL"), 3))
    assert deltas == [-1.589, -1.589]


def test_engine_r_refuses_a_partial_result_with_no_runner_leg():
    lone_tp1 = ExitResult(outcome="win", runner_outcome=None, entry_index=0, exit_index=2,
                          entry_price=100.0, r_total=1.959,
                          legs=[{"fraction": 1.0, "exit_price": 110.0, "r": 1.959,
                                 "reason": "tp1"}])
    with pytest.raises(ValueError):
        of.engine_r(_partial(), lone_tp1, "PARTIAL")


# --- cost parity ------------------------------------------------------------------------

def test_cost_parity_on_a_stop_exit_gives_zero_delta():
    plan = _active()
    res = of.engine_path(plan, make_ohlcv([ENTRY, STOP_BAR]), 0)
    exit_price = res.legs[0]["exit_price"]
    assert exit_price == 95.0
    assert of.actual_r(plan, exit_price, "ACTIVE") - of.engine_r(plan, res, "ACTIVE") == 0


def test_cost_parity_on_a_runner_trail_gives_zero_delta():
    plan = _partial(tp2=200.0)
    res = of.engine_path(plan, _trail_bars(), 0)
    assert res.runner_outcome == "runner_trail"
    exit_price = res.legs[1]["exit_price"]
    assert of.actual_r(plan, exit_price, "PARTIAL") == of.engine_r(plan, res, "PARTIAL")


def test_a_manual_exit_at_the_engines_tp2_price_still_pays_the_stop_slippage():
    """Target kind slips 5 bps, the manual leg 10: a real cost of exiting by hand."""
    plan = _partial()
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert of.actual_r(plan, 120.0, "PARTIAL") == 2.943
    assert of.engine_r(plan, res, "PARTIAL") == 2.949


# --- dollars ------------------------------------------------------------------------------

def test_dollar_risk_is_record_shares_times_the_initial_risk():
    assert of.dollar_risk(_active(), {"shares": 10}) == 50.0
    assert of.dollar_risk(_active(), {"shares": "7.5"}) == 37.5
    bear = _active(direction="bearish", stop_loss=105.0, tp1=90.0)
    assert of.dollar_risk(bear, {"shares": 10}) == 50.0


@pytest.mark.parametrize("trade", [None, {}, {"shares": None}, {"shares": "n/a"},
                                   {"shares": 0}])
def test_dollar_risk_is_none_without_usable_shares(trade):
    assert of.dollar_risk(_active(), trade) is None


def test_to_usd():
    assert of.to_usd(0.762, 50.0) == 38.1
    assert of.to_usd(-1.019, 37.5) == -38.21
    assert of.to_usd(None, 50.0) is None
    assert of.to_usd(0.5, None) is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
```

Expected: FAIL, every test with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute ...` (`INSTRUMENT`, `engine_path`, ...).

- [ ] **Step 3: Extend the import block**

In `$WT/swingbot/core/analytics/override_fidelity.py`, replace the two `swingbot` import lines written by V173-7:

```python
from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.planning.plan_types import PlanStatus
```

with:

```python
from swingbot.core.backtesting.instrument import contract, costs
from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.exit_sim_v2 import fill_bar_exit, walk_v2
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.time_exit import TIME_EXIT_REASON
```

- [ ] **Step 4: Append the engine path and the arms**

Append to the end of `$WT/swingbot/core/analytics/override_fidelity.py`:

```python
# --- the engine path and the two arms (V173-8) ---------------------------------

#: The instrument every arm is booked on: v2 fills and costs, as the sim.
INSTRUMENT = contract.resolve("v2")

_TARGET_REASONS = frozenset({"tp1", "runner_tp2"})
_CLOSE_REASONS = frozenset({"timeout", "runner_timeout", "acceptance_exit", "stall_exit",
                            "runner_progress_stall", TIME_EXIT_REASON})


def hold_cap_bars(plan) -> int:
    """The walk length simulate_exit_v2 gives this plan."""
    return exit_sim._hold_cap_bars(plan, HORIZONS[plan.horizon_key]["max_holding_days"])


def engine_frame(df: pd.DataFrame, ov_idx: int) -> pd.DataFrame:
    """`df` with the override session's range shrunk to its open-close body.

    The human acted somewhere inside that session; the engine is never shown
    the session's high or low as a later path (spec §3, no lookahead). A
    touch of the real range is caught as `ambiguous` instead."""
    frame = df.copy()
    open_, close = float(frame["Open"].iat[ov_idx]), float(frame["Close"].iat[ov_idx])
    frame.iloc[ov_idx, frame.columns.get_loc("High")] = max(open_, close)
    frame.iloc[ov_idx, frame.columns.get_loc("Low")] = min(open_, close)
    return frame


def engine_path(plan, df: pd.DataFrame, fill_idx: int) -> ExitResult:
    """The plan left alone: the fill-bar stop check, then the v2 walk, from
    the live fill bar at the live fill price with the original stop. Never a
    mid-trade resume: the engine is deterministic, so replaying the whole
    trade is the counterfactual."""
    entry = float(plan.entry_price)
    early = fill_bar_exit(df, fill_idx, entry, plan, INSTRUMENT)
    if early is not None:
        return early
    return walk_v2(df, fill_idx, entry, plan, hold_cap_bars(plan), INSTRUMENT,
                   scale_out=plan.tp1_fraction < 1.0)


def leg_kind(reason: str) -> str:
    """The costs.EXIT_KINDS kind walk_v2 books a leg of this reason with."""
    if reason in _TARGET_REASONS:
        return "target"
    return "close" if reason in _CLOSE_REASONS else "stop"


def live_tp1_leg(plan) -> dict | None:
    """The realised TP1 leg as a raw costs.book leg; both arms share it."""
    leg = next((leg for leg in plan.legs_realized or [] if leg.get("reason") == "tp1"), None)
    if leg is None or leg.get("exit_price") is None:
        return None
    return {"fraction": float(plan.tp1_fraction), "exit_price": float(leg["exit_price"]),
            "reason": "tp1", "kind": "target"}


def _remainder(plan, state: str) -> float:
    """The position the override closed (plan_manager.py:1115)."""
    return 1.0 - float(plan.tp1_fraction) if state == PlanStatus.PARTIAL else 1.0


def _tp1_legs(plan, state: str) -> list[dict]:
    if state != PlanStatus.PARTIAL:
        return []
    leg = live_tp1_leg(plan)
    if leg is None:
        raise ValueError(f"{plan.plan_id}: PARTIAL at close but no realised tp1 leg")
    return [leg]


def _book(plan, legs: list[dict]) -> float:
    """One costs.book call: the plan's entry and original stop, every leg."""
    entry, stop = float(plan.entry_price), float(plan.stop_loss)
    sign = 1 if plan.direction == "bullish" else -1
    if (entry - stop) * sign <= 0:
        raise ValueError(f"{plan.plan_id}: entry {entry} is at or beyond the stop {stop}")
    r_total, _ = costs.book(INSTRUMENT.cost_model, direction=plan.direction,
                            entry_price=entry, stop_loss=stop, legs=legs)
    return r_total


def actual_r(plan, exit_price: float, state: str) -> float:
    """The override as booked: the live TP1 leg (PARTIAL) plus the closed
    remainder at `exit_price`, a stop-kind exit (a market order by hand)."""
    manual = {"fraction": _remainder(plan, state), "exit_price": float(exit_price),
              "reason": "manual", "kind": "stop"}
    return _book(plan, [*_tp1_legs(plan, state), manual])


def engine_r(plan, result: ExitResult, state: str) -> float:
    """The replay as booked: the live TP1 leg (PARTIAL; the replay's own tp1
    leg is dropped) plus the replay's remainder legs, re-scaled to the
    remainder, each with the kind the engine books its reason with."""
    partial = state == PlanStatus.PARTIAL
    own = [leg for leg in result.legs if not (partial and leg.get("reason") == "tp1")]
    total = sum(float(leg["fraction"]) for leg in own)
    if total <= 0:
        raise ValueError(f"{plan.plan_id}: the engine result has no leg to book")
    scale = _remainder(plan, state) / total
    legs = [{"fraction": float(leg["fraction"]) * scale, "exit_price": float(leg["exit_price"]),
             "reason": leg["reason"], "kind": leg_kind(leg["reason"])} for leg in own]
    return _book(plan, [*_tp1_legs(plan, state), *legs])


def dollar_risk(plan, trade: dict | None) -> float | None:
    """Dollars at risk at the fill: the linked paper trade's record shares
    times the initial risk per share (the v170 convention). None when the
    trade or its shares are missing: the row then shows R only."""
    if not trade or trade.get("shares") is None:
        return None
    if plan.entry_price is None or plan.stop_loss is None:
        return None
    try:
        shares = float(trade["shares"])
    except (TypeError, ValueError):
        return None
    risk = shares * abs(float(plan.entry_price) - float(plan.stop_loss))
    return risk if risk > 0 else None


def to_usd(r: float | None, risk: float | None) -> float | None:
    """R in dollars; None when either side is unknown."""
    if r is None or risk is None:
        return None
    return round(r * risk, 2)
```

Paper-trade `shares` are stored positive for both directions (`performance.py:477-480` applies the direction sign separately), so one formula serves bulls and bears.

- [ ] **Step 5: Run the new test and the V173-7 test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
```

Expected: both PASS, `0 failed`, `0 xfailed`.

If a numeric expectation is off by 0.001, do not loosen it to `approx`. Recompute it with `costs.book(resolve("v2").cost_model, ...)` in a scratch script. A mismatch means the legs or kinds differ from the ones described above, and that is the bug to fix.

- [ ] **Step 6: Purity and complexity**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "open(\|requests\|PlanStore\|TradeLog\|data_store\|cached_daily_bars\|get_current_price" -- swingbot/core/analytics/override_fidelity.py
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: the `grep` finds nothing (the module does no I/O; `cached_daily_bars` is read only by the callers in V173-11/V173-12). The `radon` call prints nothing.

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_arms.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): replay an override from its fill and book both arms on one cost basis"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

