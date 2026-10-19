# v173 Execution fidelity, part 2: exit-engine hooks and the replay core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-7:" -A 600 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (replay core: never resume, one cost basis, the override session) and `## Plan panel review` (indicators from the real frame, `unstamped`, before-costs figure)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints.

Tasks: V173-6, V173-21, V173-7 (revised 2026-10-19; V173-8 moved to part 2b, `_2b-engine-arms.md`). V173-6 may run in Wave A (right after V173-1). V173-21 runs after V173-6 (both edit `exit_sim_v2.py`). V173-7 creates `override_fidelity.py` and has no dependency inside this part; V173-8 (part 2b) follows it and needs V173-6 and V173-21. Parts 3 and 3b (V173-9, V173-22, V173-23, V173-10) build `replay_override`, `summarise` and the verdict on top of the names created here.

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

### Task V173-21: `walk_v2(..., indicator_df=None)`: indicators from a separate frame

**Model:** opus — the exit engine shared by every backtest; byte-identical default

**Files:**
- Modify: `swingbot/core/planning/exit_sim_v2.py` (import block; `_runner_v2` :174; `walk_v2` :203, as left by V173-6)
- Create: `tests/planning/test_exit_sim_v2_indicator_frame.py`

**Interfaces:**
- Consumes: V173-6's `walk_v2` (both TP1 `_booked` calls pass `tp1_index=pre`) and `ExitResult.tp1_index`. Existing: `swingbot.core.market.indicators.atr` (`indicators.py:62`, imported inside `_runner_v2` at call time as `atr_indicator`), `exit_sim.runner_structure_frame` (`exit_sim.py:46`, imported into `exit_sim_v2` at module level), `config.RUNNER_STRUCTURE_EXIT` (`"off"`, `"hl_trail"`, `"progress_stall"`; `config.py:1392`).
- Produces (V173-8's `engine_path` passes it):
  - `walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int, instrument: InstrumentSpec, *, scale_out: bool, indicator_df: pd.DataFrame | None = None) -> ExitResult`.
  - `_runner_v2(df, ctx, tp1_index: int, indicator_df=None)`: `atr_indicator(...)` and `runner_structure_frame(...)` read `indicator_df` when given, else `df`; `ctx` (built from `df`) still drives every exit check.
  - `ValueError` from `walk_v2` (before anything else, on every path) when `indicator_df` is given and its length or index differs from `df`'s.
  - Omitted (`None`), every result is byte-identical to before: no existing caller (`_filled` :251, `simulate_exit_v2` :315) passes it.

**Why.** The override replay walks an *engine frame*: the real bars with the override session's high and low shrunk to its open-close body, so the engine is never shown that session's range as a later path (spec §3). Today `_runner_v2` computes ATR(14) and the structure frame from the same `df` it walks, so shrinking one bar also shrinks ATR for the next 14 bars and moves every later trailing stop: a wide override bar would change the engine arm through its indicators, not through any exit it could have seen. The plan panel's fix (spec `## Plan panel review`; brief addendum D): one optional keyword that feeds only the two indicator calls. `ATR` and `runner_structure_frame` are read by position (`atr_series.iloc[j]`, `frame` row `j`), so the indicator frame must line up bar for bar, hence the `ValueError`.

**Concurrent plan note.** `docs/superpowers/plans/2026-10-19-v176-runner-giveback-exit_*.md` (V176-5) also edits `_runner_v2` (it returns a fifth element `stop_source`) and `_booked`. If V176-5 has merged into `main` before this task runs, apply the same two edits to its version: keep its return shape, add `indicator_df=None` as the last parameter, and use `source` for the two indicator calls. The test below does not depend on the return shape.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/planning/test_exit_sim_v2_indicator_frame.py`:

```python
"""v173 (plan panel): walk_v2 can read its runner indicators from a separate frame.

`indicator_df` feeds only ATR(14) and the structure frame; `df` still drives
every stop, target and close check. Omitted, nothing changes. Expected R
figures were taken from walk_v2 on these exact bars under pin_code_defaults
(RUNNER_STRUCTURE_EXIT "off"): 3.691 un-spiked, 3.565 with the wide bar 18,
3.697 for the clamped frame walked on its own (clamped) indicators.
"""
import dataclasses

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.market import indicators
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
STOP_BAR = (96.0, 96.5, 94.0, 95.0)
#: rising[15] sits at bar 18 (entry 0, flat 1, TP1 2, rising from 3).
OV_IDX = 18


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=200.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _bars(*, override_bar=None):
    """TP1 on bar 2, twenty rising bars, then bar 23 opens at 129 and trades
    through the trail, so the runner exits AT the trailing stop (an
    ATR-priced exit). `override_bar` replaces bar 18."""
    rising = [(110.0 + i, 111.0 + i, 109.0 + i, 110.5 + i) for i in range(20)]
    if override_bar is not None:
        rising[15] = override_bar
    return make_ohlcv([ENTRY, FLAT, TP1_BAR, *rising, (129.0, 129.5, 100.0, 101.0)])


SPIKE = (125.0, 150.0, 124.0, 125.5)      # wide high, touches neither trail nor TP2
WICK = (125.0, 126.0, 100.0, 125.5)       # deep low: touches the trail on the real bar


def _clamp(df, i):
    frame = df.copy()
    body = sorted((float(frame["Open"].iat[i]), float(frame["Close"].iat[i])))
    frame.iloc[i, frame.columns.get_loc("Low")] = body[0]
    frame.iloc[i, frame.columns.get_loc("High")] = body[1]
    return frame


def _walk(df, plan=None, *, scale_out=True, instrument=V2, **kw):
    return walk_v2(df, 0, 100.0, plan or _plan(), 28, instrument, scale_out=scale_out, **kw)


def _spy_atr(monkeypatch):
    """Record every frame ATR is computed from (_runner_v2 imports
    indicators.atr at call time, so patching the module attribute reaches it)."""
    seen = []
    real_atr = indicators.atr

    def spy(frame, period=14):
        seen.append(frame)
        return real_atr(frame, period)

    monkeypatch.setattr(indicators, "atr", spy)
    return seen


# --- omitted == the frame itself: byte-identical --------------------------------

@pytest.mark.parametrize("override_bar, r_total", [(None, 3.691), (SPIKE, 3.565)])
def test_omitted_and_the_frame_itself_give_equal_results(override_bar, r_total):
    df = _bars(override_bar=override_bar)
    default, explicit = _walk(df), _walk(df, indicator_df=df)
    assert default == explicit
    assert (default.runner_outcome, default.exit_index, default.r_total) == (
        "runner_trail", 23, r_total)
    assert default.tp1_index == explicit.tp1_index == 2


@pytest.mark.parametrize("bars", [[ENTRY, FLAT, TP1_BAR], [ENTRY, STOP_BAR], [ENTRY, FLAT, FLAT]])
def test_single_leg_walks_ignore_the_indicator_frame(bars):
    df = make_ohlcv(bars)
    plan = _plan(tp1_fraction=1.0, tp2=None)
    assert _walk(df, plan, scale_out=False, instrument=FREE) == _walk(
        df, plan, scale_out=False, instrument=FREE, indicator_df=_clamp(df, 1))


# --- a clamped frame with the real indicators -------------------------------------

def test_the_clamped_frame_reads_atr_from_the_real_bars(monkeypatch):
    seen = _spy_atr(monkeypatch)
    real = _bars(override_bar=SPIKE)
    clamped = _clamp(real, OV_IDX)
    res = _walk(clamped, indicator_df=real)
    assert seen and seen[-1] is real
    assert res.r_total == _walk(real).r_total == 3.565


def test_without_the_keyword_the_clamped_frame_reads_its_own_atr(monkeypatch):
    seen = _spy_atr(monkeypatch)
    clamped = _clamp(_bars(override_bar=SPIKE), OV_IDX)
    res = _walk(clamped)
    assert seen[-1] is clamped
    assert res.r_total == 3.697


def test_the_structure_frame_reads_the_real_bars_too(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    seen = []
    real_frame = exit_sim_v2.runner_structure_frame

    def spy(frame):
        seen.append(frame)
        return real_frame(frame)

    monkeypatch.setattr(exit_sim_v2, "runner_structure_frame", spy)
    real = _bars(override_bar=SPIKE)
    _walk(_clamp(real, OV_IDX), indicator_df=real)
    assert seen and seen[-1] is real


def test_exit_checks_still_read_the_walked_frame():
    """The real bar 18 wicks through the trail; its clamped body does not. With
    real indicators the clamped walk still does not stop on bar 18."""
    real = _bars(override_bar=WICK)
    on_real = _walk(real)
    on_clamped = _walk(_clamp(real, OV_IDX), indicator_df=real)
    assert (on_real.runner_outcome, on_real.exit_index) == ("runner_trail", OV_IDX)
    assert (on_clamped.runner_outcome, on_clamped.exit_index) == ("runner_trail", 23)


# --- the frames must line up --------------------------------------------------------

def test_an_indicator_frame_of_another_length_is_refused():
    df = _bars()
    with pytest.raises(ValueError, match="same index"):
        _walk(df, indicator_df=df.iloc[:-1])


def test_an_indicator_frame_on_other_dates_is_refused():
    df = _bars()
    shifted = df.copy()
    shifted.index = df.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="same index"):
        _walk(df, indicator_df=shifted)


def test_the_check_runs_on_every_path_not_only_the_runner():
    df = make_ohlcv([ENTRY, STOP_BAR])
    with pytest.raises(ValueError, match="same index"):
        _walk(df, _plan(tp1_fraction=1.0, tp2=None), scale_out=False, indicator_df=df.iloc[:1])
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_indicator_frame.py
```

Expected: FAIL. Every test that passes `indicator_df=` fails with `TypeError: walk_v2() got an unexpected keyword argument 'indicator_df'`; `test_without_the_keyword_the_clamped_frame_reads_its_own_atr` already passes (it pins today's behaviour).

- [ ] **Step 3: Implement the keyword**

In `$WT/swingbot/core/planning/exit_sim_v2.py`, add `import pandas as pd` to the import block, directly after `from dataclasses import dataclass` (with a blank line before the `swingbot` imports, as the file's import groups already are):

```python
from dataclasses import dataclass

import pandas as pd

from swingbot import config
```

Add this helper directly above `_runner_bar_v2`:

```python
def _check_indicator_frame(df, indicator_df) -> None:
    """v173: an indicator frame must line up with the exit frame bar for bar,
    because ATR and the structure frame are read by position."""
    if indicator_df is None:
        return
    if len(indicator_df) != len(df) or not indicator_df.index.equals(df.index):
        raise ValueError("indicator_df must have the same index and length as df")
```

Replace `_runner_v2` (line 174 onward) with:

```python
def _runner_v2(df, ctx, tp1_index: int, indicator_df=None):
    """exit_sim._runner_phase on fills.py's compares: (price, index, reason,
    kind) of the post-TP1 leg. The trailing stop set from bar j's close is
    first checked on bar j + 1.

    v173: ATR and the structure frame are computed from `indicator_df` when
    given (same index as `df`), else from `df`; ctx, built from `df`, still
    drives every exit check."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", "close"
    from swingbot.core.market.indicators import atr as atr_indicator
    source = df if indicator_df is None else indicator_df
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(source, 14)
    frame = runner_structure_frame(source) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close"
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close"
```

The only changes against the current body are the docstring paragraph, the `indicator_df=None` parameter, the `source = ...` line and `source` in the two indicator calls.

Replace `walk_v2` (as left by V173-6) with:

```python
def walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2,
            max_holding_days: int, instrument: InstrumentSpec, *,
            scale_out: bool, indicator_df: pd.DataFrame | None = None) -> ExitResult:
    """The v2 exit walk from a filled entry: bars entry_index + 1 .. entry_index
    + max_holding_days (capped at the data). Single-leg unless `scale_out` and
    the plan keeps a runner (tp1_fraction < 1.0), as exit_sim._walk_for.
    v173: a result that reached TP1 carries that bar as `tp1_index`, and
    `indicator_df` (same index and length as `df`, else ValueError) feeds
    only the runner's ATR and structure frame; omitted, the walk is unchanged."""
    _check_indicator_frame(df, indicator_df)
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
    price, exit_index, reason, kind = _runner_v2(df, ctx, pre, indicator_df)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason, tp1_index=pre)
```

`_pre_tp1_v2`, `_context`, `_filled` and `simulate_exit_v2` are not edited. Confirm nothing else calls `_runner_v2`:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "_runner_v2(" -- swingbot tests scripts
```

Expected: the definition and the one call in `walk_v2` only.

- [ ] **Step 4: Run the new test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_indicator_frame.py
```

Expected: PASS, `0 failed`, `0 xfailed`. If a figure is off, do not loosen it: recompute it with `walk_v2` on the same bars under `pin_code_defaults` in a scratch script in the session scratchpad; a difference in the omitted case means the default path changed, which is the bug.

- [ ] **Step 5: Run every existing exit test, unchanged**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_replay_hooks.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout_witness.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_runner_structure.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_acceptance.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py
```

Expected: every file PASS with `0 failed`, `0 xfailed`, and **no existing test file edited**: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides status --short tests/` shows only `?? tests/planning/test_exit_sim_v2_indicator_frame.py`. The scale-out witness lives at `tests/planning/test_exit_sim_scaleout_witness.py` (the index's `tests/test_exit_sim_scaleout_witness.py` is the same file under its old path).

Then let the diff-selector catch every backtest witness and arm that walks v2:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed`. If it widens to the full suite, hand the run to the `test-runner` subagent rather than reading its output here.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/planning/exit_sim_v2.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/complexity_gate.py
```

Expected: `walk_v2`, `_runner_v2` and `_check_indicator_frame` are not listed by `radon` (`_runner_v2` was B(8) and gains one branch); the gate passes.

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/planning/exit_sim_v2.py tests/planning/test_exit_sim_v2_indicator_frame.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): walk_v2 indicator_df keyword so a clamped replay frame keeps the real ATR and structure"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-7: `override_fidelity`: constants, session assignment, plan readers, stamp kinds, `OverrideRow`

**Model:** opus — no-lookahead territory (timestamp to session mapping)

**Files:**
- Create: `swingbot/core/analytics/override_fidelity.py`
- Create: `tests/analytics/test_override_fidelity_sessions.py`

**Interfaces:**
- Consumes: `swingbot.core.market.session` (`RTH_OPEN`, `US_MARKET_TZ`, `nyse_calendar`, `session_close`, all existing); `swingbot.core.planning.plan_types.PlanStatus` (existing). The `override` stamp shape written by V173-3 (`{"exit_price", "price_source", "quote_ts", "bars_asof"}`, or `None` when building it failed); this task only reads its presence and `price_source`.
- Produces (all in `swingbot/core/analytics/override_fidelity.py`; V173-8, V173-9, V173-22, V173-23, V173-10 and V173-26 import them by these names):
  - Constants: `MANUAL_REASONS = ("manual", "manual_bulk")`; `STATUSES = ("resolved", "open", "unstamped", "stale", "ambiguous", "parity_mismatch", "split_affected", "unreplayable")` (eight); `EXCLUDED_STATUSES = ("unstamped", "stale", "ambiguous", "parity_mismatch", "split_affected", "unreplayable")` (six: every status but `resolved` and `open`, in `STATUSES` order); `TIMEOUT_REASONS = ("timeout", "runner_timeout")` (the two reasons `walk_v2` gives when it stops at `ctx.end`, which is also where it clips at the data end); `STAMP_KINDS = ("missing", "failed", "stamped")`; `DEAD_BAND = 0.05`; `VERDICT_FLOOR = 30`; `WEEK_FLOOR = 10`; `EXCLUDED_CAP = 0.20`; `SPLIT_TOLERANCE = 0.02`; `LEDGER_ID = "v173-override-fidelity"`; `ROW_FIELDS` (the 20 row keys, in order).
  - `@dataclass(frozen=True) SessionHit(session: date, price_kind: str)`, `price_kind` `"open"` or `"close"`.
  - `assign_session(at_iso: str | None) -> SessionHit | None` per the Global Constraints rule; a naive timestamp is read as UTC (every `status_history` `at` is written by `datetime.now(timezone.utc).isoformat()`); `None` for empty, unparseable or outside the NYSE calendar (2018-01-02..2030-12-31).
  - `latest_completed_session(now: datetime) -> date`: the last session whose `session_close` (ET) is at or before `now`; naive `now` read as UTC; `ValueError` outside the calendar.
  - `session_index(df, day: date | None) -> int | None`: positional index of the bar dated `day`.
  - `transition_at(plan, status: str) -> str | None`: `at` of the **first** `status_history` entry with `status`.
  - `override_entry(plan) -> dict | None`: the last `status_history` entry, when the plan is CLOSED and that entry is `CLOSED` with a reason in `MANUAL_REASONS`.
  - `is_override(plan) -> bool`.
  - `state_at_close(plan) -> str`: `"PARTIAL"` when any `status_history` entry is `PARTIAL`, else `"ACTIVE"`.
  - `stamp_kind(entry: dict | None) -> str`, on the CLOSED entry: `"missing"` (no entry, or no `override` key: a pre-v173 close), `"failed"` (`override` present but `None` or not a dict, or its `price_source == "none"`: a post-v173 stamp that failed), `"stamped"` (otherwise). It reads only the `override` key, never the reason or the timestamp: a missing key is never inferred to be anything else (`schema-evolution.md`: no read-time upcasting). V173-9 maps `"failed"` on an individual close to `unstamped`, and `"missing"` to the session-bar path.
  - `@dataclass(frozen=True) OverrideRow` with exactly the 20 row fields of the Global Constraints, in that order (`plan_id, ticker, horizon, direction, state_at_close, close_date, bulk, approx, price_source, status` required; `actual_r, engine_r, delta_r, delta_r_gross, actual_usd, engine_usd, delta_usd, engine_exit_reason, outcome` default `None`; `source` default `"manual"`); `ValueError` on a `status` not in `STATUSES`; property `entry_date -> date | None` (= `close_date`, the attribute `stats.group_by_week` reads); `to_dict() -> dict` with `close_date` as an ISO string or `None`. `delta_r_gross` is the before-costs delta (descriptive only; never in the verdict decision).
  - `outcome_of(delta_r: float | None) -> str | None`: `"helped"` above `+DEAD_BAND`, `"hurt"` below `-DEAD_BAND`, `"neutral"` otherwise (the band edges are neutral), `None` for `None`.
  - Test helper `tests.analytics.test_override_fidelity_sessions.override_plan(...)`, the stamps `FILL_AT`, `TP1_AT`, `CLOSE_AT` and the sample stamp `QUOTE_STAMP`: V173-8 (and Part 3's tests, if they choose) import them.

**Why the session rules look like this.** §3's table: the override session is the session the human acted in, and the engine is never shown that session's range as a later path. A stamp before 09:30 ET on a session day belongs to that day's open (a pre-v173 close is priced from that open); from 09:30 on, regular hours and after-hours alike, to that day's close. A stamp on a weekend or holiday belongs to the last session before it, at its close. ET, not UTC, decides the date: `2026-10-02T02:30Z` is 22:30 ET on 2026-10-01.

**Why three stamp kinds (plan panel, 2026-10-19).** Two different things leave a close without a quote. A close made before v173 shipped has no `override` key at all: it is priced from its session bar and marked `approx`. A close made after v173 whose stamp builder failed carries `"override": None` (or a stamp whose `price_source` is `"none"`): the close was a decision, but nothing priced it, so it must not quietly fall back to a bar estimate and must count against the verdict's exclusion cap. That is the new `unstamped` status (V173-9), an excluded status. Telling the two apart from the key's presence alone is the only honest reading.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_sessions.py`:

```python
"""v173 §3: override sessions, plan readers, stamp kinds and the OverrideRow shape.

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
#: A post-v173 stamp from a live quote (the V173-3 shape).
QUOTE_STAMP = {"exit_price": 104.0, "price_source": "quote", "quote_ts": CLOSE_AT,
               "bars_asof": "2026-10-06"}

ROW_KEYS = ("plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source")


def override_plan(*, reason="manual", partial=False, status=PlanStatus.CLOSED,
                  history=None, close_at=CLOSE_AT, override=None, **kw):
    """A live plan record closed by a manual override (shared by the v173 tests).

    `override` is the stamp dict put on the CLOSED entry; leave it None for a
    pre-v173 close (the key is then absent). A failed post-v173 stamp
    (`"override": None`) needs an explicit `history`."""
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
    assert of.STATUSES == ("resolved", "open", "unstamped", "stale", "ambiguous",
                           "parity_mismatch", "split_affected", "unreplayable")
    assert of.EXCLUDED_STATUSES == ("unstamped", "stale", "ambiguous", "parity_mismatch",
                                    "split_affected", "unreplayable")
    assert of.EXCLUDED_STATUSES == tuple(s for s in of.STATUSES if s not in ("resolved", "open"))
    assert of.TIMEOUT_REASONS == ("timeout", "runner_timeout")
    assert of.STAMP_KINDS == ("missing", "failed", "stamped")
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


# --- stamp_kind: missing, failed, stamped --------------------------------------

def _closed(**extra):
    return {"status": "CLOSED", "reason": "manual", "at": CLOSE_AT, **extra}


def test_no_override_key_is_a_pre_v173_close():
    assert of.stamp_kind(_closed()) == "missing"
    assert of.stamp_kind(of.override_entry(override_plan())) == "missing"


def test_no_entry_at_all_is_missing():
    assert of.stamp_kind(None) == "missing"
    assert of.stamp_kind({}) == "missing"


def test_a_stamp_that_failed_to_build_is_failed():
    assert of.stamp_kind(_closed(override=None)) == "failed"


def test_a_stamp_with_no_price_is_failed():
    stamp = {"exit_price": None, "price_source": "none", "quote_ts": None, "bars_asof": None}
    assert of.stamp_kind(_closed(override=stamp)) == "failed"


def test_a_garbled_stamp_is_failed_not_stamped():
    assert of.stamp_kind(_closed(override="104.0")) == "failed"


@pytest.mark.parametrize("source", ["quote", "bar_close"])
def test_a_priced_stamp_is_stamped(source):
    stamp = {**QUOTE_STAMP, "price_source": source}
    if source == "bar_close":
        stamp["quote_ts"] = None
    assert of.stamp_kind(_closed(override=stamp)) == "stamped"
    plan = override_plan(override=stamp)
    assert of.stamp_kind(of.override_entry(plan)) == "stamped"


def test_the_kind_is_read_from_the_key_alone_never_the_reason_or_the_date():
    """A bulk close, or a close dated after v173 shipped, with no key is still
    'missing': nothing is inferred (no read-time upcasting)."""
    late = _closed(reason="manual_bulk", at="2026-12-01T18:00:00+00:00")
    assert of.stamp_kind(late) == "missing"


# --- OverrideRow -------------------------------------------------------------

def _row(**kw):
    base = dict(plan_id="p1", ticker="T", horizon="4w", direction="bullish",
                state_at_close="ACTIVE", close_date=dt.date(2026, 10, 7), bulk=False,
                approx=False, price_source="quote", status="resolved")
    base.update(kw)
    return of.OverrideRow(**base)


def test_row_fields_are_exactly_the_payload_keys_in_order():
    assert tuple(f.name for f in dataclasses.fields(of.OverrideRow)) == ROW_KEYS
    assert len(ROW_KEYS) == 20


def test_row_defaults():
    row = _row()
    assert row.source == "manual"
    assert all(getattr(row, key) is None for key in ROW_KEYS[10:19])


def test_to_dict_writes_the_close_date_as_iso():
    row = _row(actual_r=0.5, engine_r=0.2, delta_r=0.3, delta_r_gross=0.35, outcome="helped")
    body = row.to_dict()
    assert tuple(body) == ROW_KEYS
    assert body["close_date"] == "2026-10-07"
    assert body["delta_r"] == 0.3 and body["delta_r_gross"] == 0.35
    assert body["outcome"] == "helped"
    assert _row(close_date=None).to_dict()["close_date"] is None


def test_an_unstamped_row_carries_no_figures():
    row = _row(status="unstamped", price_source="none")
    body = row.to_dict()
    assert body["status"] == "unstamped"
    assert all(body[key] is None for key in ("actual_r", "engine_r", "delta_r", "delta_r_gross",
                                             "actual_usd", "engine_usd", "delta_usd"))


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


@pytest.mark.parametrize("status", ["resolved", "open", "unstamped", "stale", "ambiguous",
                                    "parity_mismatch", "split_affected", "unreplayable"])
def test_every_status_is_accepted(status):
    assert _row(status=status).status == status


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
(`runner_path.cached_daily_bars`, read by override_io) and linked trades come
in as arguments.

This first block holds the frozen constants, the timestamp-to-session rule,
the plan readers, the stamp kinds and the row shape. The engine path and the
two arms follow (V173-8); `replay_override` and its data admission (V173-9,
V173-22, V173-23) and `summarise` (V173-10) close the module. The constants
are pre-registered (spec §4): changing any of them is a new spec, never an
edit.
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
#: Every row carries exactly one of these (spec §3 status table, eight since
#: the plan panel added "unstamped").
STATUSES = ("resolved", "open", "unstamped", "stale", "ambiguous", "parity_mismatch",
            "split_affected", "unreplayable")
#: Statuses left out of the sums and capped at EXCLUDED_CAP for the verdict.
EXCLUDED_STATUSES = ("unstamped", "stale", "ambiguous", "parity_mismatch", "split_affected",
                     "unreplayable")
#: walk_v2's reasons for stopping at ctx.end -- the hold cap, or the data end.
TIMEOUT_REASONS = ("timeout", "runner_timeout")
#: What the CLOSED entry's `override` key says (stamp_kind).
STAMP_KINDS = ("missing", "failed", "stamped")
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
    """The NYSE session a timestamp belongs to, and which of its prices a
    pre-v173 close is priced from: "open" (before 09:30 ET) or "close"."""
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
    the newest bar a fresh daily cache can hold settled."""
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


def stamp_kind(entry: dict | None) -> str:
    """What the CLOSED entry's `override` key says, read from the key alone.

    "missing": no key (a close made before v173 shipped; priced from its
    session bar, approx). "failed": the key is there but holds None, a
    non-dict, or a stamp with price_source "none" (a v173 close nothing could
    price; V173-9 makes an individual one `unstamped`). "stamped": a priced
    stamp. A missing key is never inferred to be anything else."""
    if not entry or "override" not in entry:
        return "missing"
    stamp = entry["override"]
    if not isinstance(stamp, dict) or stamp.get("price_source") == "none":
        return "failed"
    return "stamped"


@dataclass(frozen=True)
class OverrideRow:
    """One override against the engine. R is on the plan's initial risk, net
    of modelled costs and pre-tax (`delta_r_gross`: the same delta before
    costs, descriptive only); the *_usd fields are None without a dollar
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
    delta_r_gross: float | None = None
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

`PlanStatus` (`plan_types.py:6`) is a class of plain string constants, so `state_at_close` returns the `str` `"PARTIAL"` or `"ACTIVE"`. `ROW_FIELDS` is derived from the dataclass so the payload key list can never drift from the row; the test pins it to the Global Constraints list (20 keys, `delta_r_gross` after `delta_r`).

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
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override_fidelity sessions, plan readers, stamp kinds and OverrideRow"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

