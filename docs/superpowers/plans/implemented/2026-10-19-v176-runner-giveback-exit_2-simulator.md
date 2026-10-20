# v176 Runner give-back exit. Part 2: simulator parity and pinned tests (V176-5..V176-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V176-5:" -A 400 docs/superpowers/plans/2026-10-19-v176-runner-giveback-exit_2-simulator.md`.

**Spec:** [`docs/superpowers/specs/2026-10-19-v176-runner-giveback-exit-design.md`](../specs/2026-10-19-v176-runner-giveback-exit-design.md) (this part: § Where it changes item 3 "Backtest", § Exit reason "no new string", § Risks "Pinned backtest numbers", § Testing "Simulator")
**Index:** [`2026-10-19-v176-runner-giveback-exit_0-index.md`](2026-10-19-v176-runner-giveback-exit_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Parallelisation`, the task ledger and the **pinned-test decision table** V176-6 follows. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v176-runner-giveback-exit` (created in V176-1). Never `cd`; use `git -C $WT` and `python $WT/scripts/dev/testrun.py file <test>`. All file paths below are relative to `$WT`. The plan-manager tests use the Postgres test database (`/replicate-prod-db` once per session before the first DB-backed run).

**Order.** V176-5 -> V176-6, strictly. V176-5 needs V176-1 committed (it edits `exit_sim.py` after V176-1 and imports its helpers). V176-5 may run alongside V176-2/V176-3/V176-4 (disjoint files). Between V176-5 and V176-6 two existing tests are **expected red** (`tests/planning/test_exit_sim_scaleout_witness.py::test_scale_out_walk_is_byte_identical_to_the_frozen_witness` and `tests/planning/test_exit_sim_runner_structure.py::test_off_is_byte_identical`): the new `ExitResult` field enters `dataclasses.asdict` and so the witness hash; V176-6 drops it before hashing. V176-6 is the task that turns them green.

**Consumed from part 1 (V176-1, ledger names only)**, all in `swingbot/core/planning/exit_sim.py`:
- `giveback_stop(extreme: float, pct: float, direction: str) -> float` (pct in percent);
- `runner_giveback_pct() -> float` (clamp of `config.RUNNER_GIVEBACK_PCT` to `GIVEBACK_PCT_BOUNDS = (0.5, 49.0)`);
- `giveback_level(extreme: float | None, direction: str) -> float | None` (None when `config.RUNNER_GIVEBACK_ENABLED` is false or `extreme is None`; else `giveback_stop(extreme, runner_giveback_pct(), direction)`, read at call time);
- `tighter_stop(stop: float, other: float | None, is_bull: bool) -> float` (`stop` when `other is None`, else `max` long / `min` short);
- `runner_stop_source(stop: float, floor: float, giveback: float | None) -> str` (`"floor"` if `stop == floor`, else `"giveback"` if `stop == giveback`, else `"trail"`);
- `config.RUNNER_GIVEBACK_ENABLED: bool` (default `True`), `config.RUNNER_GIVEBACK_PCT: float` (default `5.0`).

**Decisions this part fixes** (inside the ledger's contracts):
- The simulator's give-back extreme is a **separate** running value from the chandelier's `extreme_close`. With `GIVEBACK_EXTREME_BASIS = "close"` (the default, the spec's rule) the two are always equal; with `"high_low"` (measurement-only, V176-8's tick-proxy arm reporting the spec's tick/close gap) the give-back tracks the bar's high (long) / low (short) while the chandelier keeps the close. Both seed from the TP1 bar (`close` basis: its close; `high_low`: its high / low, which for a long is reached at or after the TP1 touch because `high >= tp1`) and both are first applied after bar `tp1_index + 1` is checked: effective the next bar, no intrabar lookahead.
- Order inside a runner bar after the stop/TP2 check: chandelier ratchet, then give-back ratchet, then the structure update (when enabled). That is the live order too (give-back before `_structure_runner_step`).
- `stop_source` is decided at the bar test from the stop that was checked and the give-back level from the **same** extreme that set it, so the float equality in `runner_stop_source` compares identical values. Non-stop runner exits (`runner_tp2`, `runner_timeout`, `runner_progress_stall`, `acceptance_exit`) and every single-leg walk carry `runner_stop_source = None`.
- Legs are untouched (no new leg key), so no exact-dict leg test moves; the source rides only on `ExitResult.runner_stop_source`. In v2, `_booked` takes it as a keyword.

---

# Phase 3: Simulator parity

### Task V176-5: Simulator parity in `exit_sim` and `exit_sim_v2`

**Model:** opus — exit-walk semantics shared by every backtest (no-lookahead ordering, a result-shape change across two simulators), where a subtle slip silently moves every badge.

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (`ExitResult` :61-75; after `_chandelier_ratchet` :424-430 add the basis constant and three helpers; `_runner_bar_exit` :411-421; `_runner_phase` :439-484; `_runner_result` :487-499)
- Modify: `swingbot/core/planning/exit_sim_v2.py` (imports :25-28; `_booked` :79-89; `_runner_bar_v2` :160-171; `_runner_v2` :174-199; `walk_v2` :219-222)
- Create: `tests/planning/test_exit_sim_giveback.py`

**Interfaces:**
- Consumes (V176-1, in `exit_sim.py`): `giveback_stop`, `giveback_level`, `tighter_stop`, `runner_stop_source`; `config.RUNNER_GIVEBACK_ENABLED`, `config.RUNNER_GIVEBACK_PCT`.
- Produces:
  - `exit_sim.GIVEBACK_EXTREME_BASIS: str = "close"` (`"close"` | `"high_low"`; measurement-only module constant, read at call time by `_giveback_extreme`, so V176-8 sets it with `exit_sim.GIVEBACK_EXTREME_BASIS = basis` in each worker; any other value raises `ValueError` at the first runner).
  - `exit_sim._giveback_extreme(ctx, j: int, extreme: float | None) -> float`; `exit_sim._giveback_ratchet(ctx, extreme: float, runner_stop: float) -> float`; `exit_sim._stop_source(ctx, runner_stop: float, floor: float, gb_extreme: float | None) -> str`.
  - `ExitResult.runner_stop_source: str | None = None` (last dataclass field; `"floor"` / `"trail"` / `"giveback"` only when the runner closed on its stop, else `None`).
  - `exit_sim._runner_bar_exit(ctx, j, runner_stop, floor, gb_extreme=None) -> (price, index, reason, stop_source) | None`; `exit_sim._runner_phase(df, ctx, tp1_index, trace=None) -> (price, index, reason, stop_source)`.
  - `exit_sim_v2._runner_bar_v2(ctx, j, runner_stop, floor, gb_extreme=None) -> (price, index, reason, kind, stop_source) | None`; `exit_sim_v2._runner_v2(df, ctx, tp1_index) -> (price, index, reason, kind, stop_source)`; `exit_sim_v2._booked(ctx, outcome, exit_index, legs, runner_outcome=None, runner_stop_source=None) -> ExitResult`.

Nothing outside the two modules calls `_runner_bar_exit`, `_runner_phase`, `_runner_result`, `_runner_bar_v2`, `_runner_v2` or `_booked` (verified: `git grep -n "_runner_phase\|_runner_bar_exit\|_runner_result\|_runner_v2\|_runner_bar_v2\|_booked(" -- '*.py'` hits only `exit_sim.py` / `exit_sim_v2.py`), so widening the tuples has no other caller to update.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_exit_sim_giveback.py`:

```python
"""v176 V176-5: the runner give-back in both exit simulators.

Bullish frame: the market entry fills at bar 0's close (100); stop 95,
TP1 110 (tp1_fraction 0.5), so the runner floor is 106.6667.
trail_atr_mult=50 parks the chandelier far below the floor, so only the
floor and the give-back can bind.
  bar 1 (100, 111, 99.5, 110.5)   TP1 touched; extreme close 110.5
  bar 2 (110.5, 121, 110, 120)    checked against the floor (low 110 passes);
                                  its close 120 sets give-back 114.0 for bar 3
  bar 3 (120, 120.5, 113, 113.5)  low 113 <= 114: runner out at 114 (give-back)
  bar 4 (113.5, 114, 106, 106.5)  reached only with the give-back off:
                                  low 106 <= floor -> runner_be
Bar 2's own low (110) is below the 114 its close sets: an intrabar read
would close the runner on bar 2, so exit_index == 3 is the no-lookahead check.
The bearish frame mirrors it around 100 (floor 93.3333, give-back 84.0).
"""
import dataclasses
import hashlib
import json

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_scaleout_witness import FIXTURE, witness_rows
from tests.planning.test_exit_sim_single import _plan

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BEAR_FLOOR = 100.0 - (2.0 / 3.0) * 10.0
BULL_BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
             (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
BEAR_BARS = [100.0, (100.0, 100.5, 89.0, 89.5), (89.5, 90.0, 79.0, 80.0),
             (80.0, 87.0, 79.5, 86.5), (86.5, 94.0, 86.0, 93.5)]
FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Give-back on at 5%, every other runner rule that could bind switched off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")


def _bull(**kw):
    base = dict(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _v1(bars, plan):
    return simulate_exit(make_ohlcv(bars), 0, plan, scale_out=True)


def _v2(bars, plan):
    return walk_v2(make_ohlcv(bars), 0, 100.0, plan, 10, FREE, scale_out=True)


# --- v1 walk ---------------------------------------------------------------

def test_flag_on_bullish_runner_exits_at_the_giveback_level_the_next_bar():
    res = _v1(BULL_BARS, _bull())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"            # no new reason string
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3                             # bar 2 sets it, bar 3 checks it
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(120.0, 5.0, "bullish")
    assert res.legs[1]["exit_price"] == pytest.approx(114.0)
    assert res.legs[1]["reason"] == "runner_trail"
    assert res.legs[1]["r"] == pytest.approx(2.8)
    assert res.r_total == pytest.approx(2.4)
    assert set(res.legs[1]) == {"fraction", "exit_price", "r", "reason"}   # legs untouched


def test_flag_on_bearish_runner_exits_at_the_giveback_level_the_next_bar():
    res = _v1(BEAR_BARS, _bear())
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(80.0, 5.0, "bearish")
    assert res.legs[1]["exit_price"] == pytest.approx(84.0)
    assert res.legs[1]["r"] == pytest.approx(3.2)
    assert res.r_total == pytest.approx(2.6)


@pytest.mark.parametrize("bars,plan,floor", [(BULL_BARS, _bull, FLOOR),
                                              (BEAR_BARS, _bear, BEAR_FLOOR)])
def test_flag_off_runner_rides_to_the_floor(monkeypatch, bars, plan, floor):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _v1(bars, plan())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4
    assert res.legs[1]["exit_price"] == pytest.approx(floor)


def test_a_giveback_looser_than_the_floor_never_moves_the_stop(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 20.0)    # 120 x 0.80 = 96 < floor
    res = _v1(BULL_BARS, _bull())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4


def test_a_chandelier_tighter_than_the_giveback_is_tagged_trail():
    # trail_atr_mult=0.01 puts the chandelier a hair under the 120 close,
    # far above the 114 give-back: the trail binds, the give-back never does.
    res = _v1(BULL_BARS, _bull(trail_atr_mult=0.01))
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "trail"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] > 114.0


@pytest.mark.parametrize("bars,plan,extreme,direction", [
    (BULL_BARS, _bull, 121.0, "bullish"),       # bar 2's high
    (BEAR_BARS, _bear, 79.0, "bearish"),        # bar 2's low
])
def test_high_low_basis_tracks_the_bar_extreme_for_the_next_bar(monkeypatch, bars, plan,
                                                                 extreme, direction):
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "high_low")
    res = _v1(bars, plan())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(extreme, 5.0, direction)


def test_an_unknown_basis_is_rejected(monkeypatch):
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "open")
    with pytest.raises(ValueError, match="GIVEBACK_EXTREME_BASIS"):
        _v1(BULL_BARS, _bull())


def test_non_stop_runner_exits_and_single_legs_carry_no_stop_source():
    tp2 = _v1(BULL_BARS, _bull(tp2=115.0))                 # bar 2's high 121 reaches TP2
    assert tp2.runner_outcome == "runner_tp2"
    assert tp2.runner_stop_source is None
    timeout = _v1(BULL_BARS[:3], _bull())                  # data ends on bar 2
    assert timeout.runner_outcome == "runner_timeout"
    assert timeout.runner_stop_source is None
    single = simulate_exit(make_ohlcv(BULL_BARS), 0, _bull(), scale_out=False)
    assert single.runner_outcome is None
    assert single.runner_stop_source is None


def test_flag_off_reproduces_the_frozen_scale_out_witness(monkeypatch):
    """Spec § Testing: flag off gives an identical trade list on an existing
    fixture. The new field is dropped before hashing (V176-6 moves that drop
    into witness_rows itself; pop(..., None) keeps this test valid after it)."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    rows = witness_rows()
    for row in rows:
        assert row[4].pop("runner_stop_source", None) != "giveback"
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    assert digest == FIXTURE.read_text(encoding="utf-8").strip()


# --- v2 walk ---------------------------------------------------------------

@pytest.mark.parametrize("bars,plan,exit_price", [
    (BULL_BARS, _bull, 114.0),
    (BEAR_BARS, _bear, 84.0),
])
def test_v2_flag_on_runner_exits_at_the_giveback_level(bars, plan, exit_price):
    res = _v2(bars, plan())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == pytest.approx(exit_price)
    assert res.legs[1]["reason"] == "runner_trail"


def test_v2_flag_off_runner_rides_to_the_floor(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _v2(BULL_BARS, _bull())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)


def test_v1_and_v2_agree_on_the_giveback_exit():
    v1, v2 = _v1(BULL_BARS, _bull()), _v2(BULL_BARS, _bull())
    assert (v1.exit_index, v1.runner_outcome, v1.runner_stop_source) == \
           (v2.exit_index, v2.runner_outcome, v2.runner_stop_source)
    assert v1.legs[1]["exit_price"] == pytest.approx(v2.legs[1]["exit_price"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_giveback.py`
Expected: FAIL. The flag-on tests fail with `AttributeError: 'ExitResult' object has no attribute 'runner_stop_source'` or on `runner_outcome == "runner_be"` / `exit_index == 4` (no give-back in the walk yet); every test errors in the autouse fixture first if `exit_sim` has no `GIVEBACK_EXTREME_BASIS` (monkeypatch `raising=True` gives `AttributeError`).

- [ ] **Step 3: Add the `ExitResult` field**

In `swingbot/core/planning/exit_sim.py`, `ExitResult` (:61-75), after `cancel_reason`, append (it must stay the **last** field so positional constructions keep working):

```python
    # Why a not_triggered row was excluded: the compression short's
    # "risk_cap"|"expired"|"invalidated", or a v131 cancellable limit's
    # "expired"|"cancelled". None everywhere else.
    cancel_reason: str | None = None
    # v176: which runner stop term closed the runner -- "floor" | "trail" |
    # "giveback" -- when the runner exited on its stop (runner_be /
    # runner_trail). None for every other exit and every single-leg walk.
    # Rides here, not on the leg: legs keep their four keys.
    runner_stop_source: str | None = None
```

- [ ] **Step 4: Add the basis constant and the three helpers**

In `swingbot/core/planning/exit_sim.py`, directly after `_chandelier_ratchet` (ends :430), insert:

```python
#: v176: which price sets the give-back's best price in the simulator.
#: "close" is the rule (extreme close, effective the next bar, like the
#: chandelier). "high_low" is the measurement's tick proxy (extreme high for a
#: long, low for a short, still effective the next bar) used only to report
#: the spec's tick/close gap. A module constant, never config: V176-8 assigns
#: ``exit_sim.GIVEBACK_EXTREME_BASIS`` in its worker processes.
GIVEBACK_EXTREME_BASIS: str = "close"
_GIVEBACK_BASES = ("close", "high_low")


def _giveback_extreme(ctx, j: int, extreme: float | None) -> float:
    """The give-back's best price after bar j (``extreme`` None seeds it).
    Reads GIVEBACK_EXTREME_BASIS at call time."""
    if GIVEBACK_EXTREME_BASIS not in _GIVEBACK_BASES:
        raise ValueError(f"GIVEBACK_EXTREME_BASIS must be one of {_GIVEBACK_BASES}, "
                         f"got {GIVEBACK_EXTREME_BASIS!r}")
    if GIVEBACK_EXTREME_BASIS == "high_low":
        price = float(ctx.high[j]) if ctx.is_bull else float(ctx.low[j])
    else:
        price = float(ctx.close[j])
    if extreme is None:
        return price
    return max(extreme, price) if ctx.is_bull else min(extreme, price)


def _giveback_ratchet(ctx, extreme: float, runner_stop: float) -> float:
    """v176: tighten the runner stop for the NEXT bar to the give-back level
    off ``extreme``. Never loosens (tighter_stop); a no-op with the flag off."""
    return tighter_stop(runner_stop, giveback_level(extreme, ctx.plan.direction), ctx.is_bull)


def _stop_source(ctx, runner_stop: float, floor: float, gb_extreme: float | None) -> str:
    """Which term set the stop that just fired. The give-back level is
    recomputed from the SAME extreme that set ``runner_stop`` (the extreme is
    only extended after the bar test), so the float equality is exact."""
    return runner_stop_source(runner_stop, floor,
                              giveback_level(gb_extreme, ctx.plan.direction))
```

(`tighter_stop`, `giveback_level` and `runner_stop_source` are module-level functions V176-1 placed next to `chandelier_stop` at :227, earlier in the same file; no import is needed.)

- [ ] **Step 5: Thread the source through the v1 runner walk**

Replace `_runner_bar_exit` (:411-421) with:

```python
def _runner_bar_exit(ctx, j, runner_stop, floor, gb_extreme=None):
    """Runner stop first, then TP2; the stop checked is the one set BEFORE bar j.
    (price, index, reason, stop_source); stop_source is None for TP2."""
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if (lo <= runner_stop) if ctx.is_bull else (hi >= runner_stop):
        # v39: "runner_be" means "closed at its initial post-TP1 floor"; the
        # string is deliberately unchanged (~30 files pattern-match it).
        # v176: a give-back close is still "runner_trail"; the term that
        # fired rides on ExitResult.runner_stop_source instead.
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return runner_stop, j, reason, _stop_source(ctx, runner_stop, floor, gb_extreme)
    tp2 = ctx.plan.tp2
    if tp2 is not None and ((hi >= tp2) if ctx.is_bull else (lo <= tp2)):
        return tp2, j, "runner_tp2", None
    return None
```

Replace `_runner_phase` (:439-484) with the following. The acceptance comment is unchanged; the new lines are `gb_extreme` and `_giveback_ratchet`, and every return gains a 4th element:

```python
def _runner_phase(df, ctx, tp1_index, trace=None):
    """Phase 2: (exit price, exit index, runner reason, stop source) for the
    post-TP1 leg. v123: a structure rule (RUNNER_STRUCTURE_EXIT) updates after
    the chandelier, from this bar's close, effective next bar; a stall exits at
    the next open. v176: the give-back ratchets after the chandelier and before
    the structure rule (the live order), from its own extreme
    (GIVEBACK_EXTREME_BASIS), effective next bar."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        # v129: the TP1 bar itself closed through the threshold -- TP1 banked
        # first (stop -> target -> acceptance), the remainder exits at that
        # close. Later runner bars are not checked: the arm-Z/B thresholds sit
        # on the stop side of entry (level -/+ b*ATR) and the runner stop on
        # the profit side, so a later close past the threshold would already
        # have hit the runner stop. Nothing enforces that for an arbitrary
        # threshold; a plan whose threshold sits on the profit side of entry
        # would need a per-bar check here.
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", None
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    gb_extreme = _giveback_extreme(ctx, tp1_index, None)
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", None
        checked_stop = runner_stop
        hit = _runner_bar_exit(ctx, j, runner_stop, floor, gb_extreme)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        gb_extreme = _giveback_extreme(ctx, j, gb_extreme)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        runner_stop = _giveback_ratchet(ctx, gb_extreme, runner_stop)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop, atr_series)
        if trace is not None:
            trace.append((j, runner_stop))
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", None
```

Replace `_runner_result` (:487-499) with:

```python
def _runner_result(ctx, runner) -> ExitResult:
    runner_exit, exit_index, reason, stop_source = runner
    plan = ctx.plan
    rr = abs(plan.tp1 - ctx.entry_price) / ctx.risk
    frac1 = plan.tp1_fraction
    frac2 = 1.0 - frac1
    leg1 = {"fraction": frac1, "exit_price": plan.tp1, "r": round(rr, 3), "reason": "tp1"}
    r2 = round((runner_exit - ctx.entry_price) * ctx.sign / ctx.risk, 3)
    leg2 = {"fraction": frac2, "exit_price": runner_exit, "r": r2, "reason": reason}
    return ExitResult(outcome="win", runner_outcome=reason, entry_index=ctx.entry_index,
                      exit_index=exit_index, entry_price=ctx.entry_price,
                      r_total=round(frac1 * rr + frac2 * r2, 3), legs=[leg1, leg2],
                      runner_stop_source=stop_source)
```

A subtlety the implementer must keep: `_runner_bar_exit` receives `gb_extreme` **before** it is extended with bar j, i.e. the extreme that set `runner_stop` after bar j-1. Moving the `_giveback_extreme` line above the bar test would both read bar j's own price (lookahead) and break the exact `stop == giveback` match.

- [ ] **Step 6: Thread the source through the v2 runner walk**

In `swingbot/core/planning/exit_sim_v2.py`, replace the `from .exit_sim import (...)` block (:25-28) with:

```python
from .exit_sim import (ExitResult, _chandelier_ratchet, _giveback_extreme, _giveback_ratchet,
                       _hold_cap_bars, _is_compression, _limit_unfilled, _no_trade,
                       _not_triggered, _runner_timeout, _stop_source, _structure_update,
                       _tenth_session_reached, acceptance_exit, runner_floor,
                       runner_structure_frame)
```

(`_giveback_extreme` is imported as a function, never `GIVEBACK_EXTREME_BASIS` itself: the function reads the `exit_sim` global at call time, so V176-8 setting `exit_sim.GIVEBACK_EXTREME_BASIS` reaches the v2 walk too.)

Replace `_booked` (:79-89) with:

```python
def _booked(ctx, outcome: str, exit_index: int, legs: list[dict],
            runner_outcome: str | None = None,
            runner_stop_source: str | None = None) -> ExitResult:
    """The trade's ExitResult, its raw legs booked once through costs.book.
    v176: ``runner_stop_source`` rides on the result, never on a leg."""
    r_total, booked = costs.book(ctx.costs, direction=ctx.plan.direction,
                                 entry_price=ctx.entry_price, stop_loss=ctx.plan.stop_loss,
                                 legs=legs)
    for raw, leg in zip(legs, booked):
        if "price_basis" in raw:
            leg["price_basis"] = raw["price_basis"]
    return ExitResult(outcome=outcome, runner_outcome=runner_outcome,
                      entry_index=ctx.entry_index, exit_index=exit_index,
                      entry_price=ctx.entry_price, r_total=r_total, legs=booked,
                      runner_stop_source=runner_stop_source)
```

Replace `_runner_bar_v2` (:160-171) with:

```python
def _runner_bar_v2(ctx, j: int, runner_stop: float, floor: float, gb_extreme=None):
    """Runner stop first, then TP2, each filled through fills.exit_fill:
    (price, index, reason, kind, stop_source) or None; stop_source is None for TP2."""
    hi, lo, op = float(ctx.high[j]), float(ctx.low[j]), float(ctx.open_[j])
    direction = ctx.plan.direction
    if fills.stop_touched(hi, lo, runner_stop, direction):
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return (fills.exit_fill(ctx.fills, "stop", runner_stop, op, direction), j, reason,
                "stop", _stop_source(ctx, runner_stop, floor, gb_extreme))
    tp2 = ctx.plan.tp2
    if tp2 is not None and fills.target_touched(hi, lo, tp2, direction):
        return (fills.exit_fill(ctx.fills, "target", tp2, op, direction), j, "runner_tp2",
                "target", None)
    return None
```

Replace `_runner_v2` (:174-199) with:

```python
def _runner_v2(df, ctx, tp1_index: int):
    """exit_sim._runner_phase on fills.py's compares: (price, index, reason,
    kind, stop_source) of the post-TP1 leg. The trailing stop set from bar j's
    close is first checked on bar j + 1; v176's give-back ratchets after the
    chandelier and before the structure rule, as in exit_sim."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", "close", None
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    gb_extreme = _giveback_extreme(ctx, tp1_index, None)
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close", None
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor, gb_extreme)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        gb_extreme = _giveback_extreme(ctx, j, gb_extreme)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        runner_stop = _giveback_ratchet(ctx, gb_extreme, runner_stop)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close", None
```

In `walk_v2` replace its last four lines (:219-222) with:

```python
    price, exit_index, reason, kind, stop_source = _runner_v2(df, ctx, pre)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason,
                   runner_stop_source=stop_source)
```

`_V2Ctx` already carries `high`, `low`, `close`, `is_bull` and `plan`, the fields `_giveback_extreme`, `_giveback_ratchet` and `_stop_source` read by name.

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_giveback.py`
Expected: PASS (`0 failed`).

- [ ] **Step 8: Run the neighbouring simulator tests**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py tests/planning/test_exit_sim_v2_walk.py tests/planning/test_exit_sim_single.py tests/planning/test_exit_sim_runner_structure.py tests/planning/test_exit_sim_scaleout_witness.py`
Expected: `test_exit_sim_scaleout_witness.py::test_scale_out_walk_is_byte_identical_to_the_frozen_witness` and `test_exit_sim_runner_structure.py::test_off_is_byte_identical` FAIL (the new `runner_stop_source` key enters `dataclasses.asdict`, so the hash moves; V176-6 drops it before hashing and pins the flag off). Every other test PASSES. Any **other** failure here is a V176-5 bug to fix now, with one exception: a numeric assertion that moved only because the give-back now binds on its fixture. Record that test's name and its old/new value in the commit message body for V176-6 (which owns the decision table) and do not edit it here.

- [ ] **Step 9: Complexity gate**

Run: `python $WT/scripts/dev/complexity_gate.py`
Expected: exit 0. `_runner_phase` (B 9 before) and `_runner_v2` (B 8 before) gain no branch; `_giveback_extreme` is about C=6.

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/planning/exit_sim.py swingbot/core/planning/exit_sim_v2.py tests/planning/test_exit_sim_giveback.py
git -C $WT commit -m "feat(v176): runner give-back in exit_sim and exit_sim_v2, ExitResult.runner_stop_source

Give-back ratchets after the chandelier from its own extreme (close basis by
default, high_low for the measurement), effective the next bar; the closing
term rides on ExitResult.runner_stop_source. Witness hashes stay red until V176-6.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4: Pinned tests

### Task V176-6: Pinned and golden tests: flag-off pins and re-pins

**Model:** sonnet — mechanical test edits under a fixed decision table, with a judgement call only on which conditional test moved and why.

**Files:**
- Modify: `tests/backtesting/test_pullback_dryup_witness.py` (`pin_code_defaults` :18-26, plus one new test)
- Modify: `tests/planning/test_exit_sim_scaleout_witness.py` (autouse flag-off fixture; `witness_rows` :40-49 drops `runner_stop_source` before hashing; `tests/planning/fixtures/scale_out_witness.sha256` is **not** touched)
- Modify: `tests/backtesting/test_v139_flag_off_golden.py` (:51-57)
- Modify: `tests/backtesting/test_v129_flag_off_golden.py` (:55-60)
- Modify: `tests/backtesting/test_v131_witness.py` (imports :12-20; autouse fixture)
- Modify: `tests/market/test_v113_horizon_witness.py` (`PINS` :30-41)
- Modify: `tests/backtesting/test_headroom_witness.py` (:42-53)
- Modify: `tests/backtesting/test_runner_structure_parity.py` (autouse fixture)
- Modify: `tests/planning/test_exit_sim_runner_structure.py` (autouse fixture)
- Modify: `tests/scripts/test_runner_headroom.py` (imports :1-12; autouse fixture)
- Conditionally (only a test that actually moves, per the index's decision table): `tests/backtesting/test_v74_no_behaviour_change.py`, `tests/planning/test_exit_sim_acceptance.py`, `tests/planning/test_acceptance_runner_aggregation.py`, `tests/backtesting/test_acceptance_replay.py` (flag-off if moved); `tests/backtesting/test_backtest_engine.py`, `tests/planning/test_exit_sim_scaleout.py` (re-pin if moved)

**Interfaces:**
- Consumes: V176-1's `config.RUNNER_GIVEBACK_ENABLED`; V176-5's `ExitResult.runner_stop_source` (the key the witness drops).
- Produces: `pin_code_defaults(monkeypatch, *, giveback: bool = False) -> None` (code defaults for every field, then `config.RUNNER_GIVEBACK_ENABLED = giveback`). Every existing caller (`tests/backtesting/instrument/golden.py`, `instrument/test_v1_golden.py`, `instrument/test_live_constructor_replay.py`, `instrument/test_constructor_parity.py`, `instrument/test_fills_costs_replay.py`, `arms/test_engine_instrument.py`, `test_pullback_dryup_witness.py`, `tests/planning/test_exit_sim_v2_walk.py`, `tests/planning/test_exit_sim_v2_entry.py`, `tests/backtest_scripts/test_measure_fib_diagnostic.py`) keeps calling `pin_code_defaults(monkeypatch)` unchanged and so gets the give-back **off**: their goldens were captured on pre-v176 code defaults. No caller file is edited.

**Rule (index § Pinned-test decisions):** a witness or golden exists to prove an unrelated change moved no numbers, so it is pinned flag-off and its fixture is never regenerated. A test of current engine behaviour is re-pinned to the newly measured value with a `# v176: give-back on` comment if it moves. A conditional row that does not move gets no edit. **Never regenerate a fixture file** (`*.sha256`, `tests/fixtures/v129/`, `v139/`, `v131/`, `v113/`, `v135/`, `instrument/v1_golden.jsonl`) to make a test pass.

- [ ] **Step 1: Write the failing test for `pin_code_defaults`**

In `tests/backtesting/test_pullback_dryup_witness.py`, after `test_pin_code_defaults_overrides_an_environment_value` (:38-42), add:

```python
def test_pin_code_defaults_pins_the_runner_giveback_off_unless_asked(monkeypatch):
    # v176: the give-back defaults ON in code, but every golden that calls
    # pin_code_defaults was captured before it existed.
    field = next(f for f in config.FIELDS if f.attr == "RUNNER_GIVEBACK_ENABLED")
    assert config._cast(field, field.default) is True
    pin_code_defaults(monkeypatch)
    assert config.RUNNER_GIVEBACK_ENABLED is False
    pin_code_defaults(monkeypatch, giveback=True)
    assert config.RUNNER_GIVEBACK_ENABLED is True
```

- [ ] **Step 2: Run the red set to see it fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_witness.py tests/planning/test_exit_sim_scaleout_witness.py tests/planning/test_exit_sim_runner_structure.py`
Expected: FAIL. `test_pin_code_defaults_pins_the_runner_giveback_off_unless_asked` fails on `assert config.RUNNER_GIVEBACK_ENABLED is False` (the helper casts the field's `"true"` default); `test_scale_out_walk_is_byte_identical_to_the_frozen_witness` and `test_off_is_byte_identical` fail on the hash (V176-5's new field, plus any runner the give-back now closes).

- [ ] **Step 3: Give `pin_code_defaults` the give-back pin**

Replace `pin_code_defaults` in `tests/backtesting/test_pullback_dryup_witness.py` (:18-26) with:

```python
def pin_code_defaults(monkeypatch, *, giveback: bool = False) -> None:
    """Set every config field to its code default for this test only.

    The witness was captured on code defaults. A developer's .env, or a
    variable inherited from the shell, can override a field such as
    MIN_STOP_DISTANCE_PCT and change which scenarios the replay admits.

    v176: RUNNER_GIVEBACK_ENABLED defaults on in code, but every golden that
    calls this was captured before the runner give-back existed, so it is
    pinned off unless the caller passes ``giveback=True``.
    """
    for field in config.FIELDS:
        monkeypatch.setattr(config, field.attr, config._cast(field, field.default))
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", giveback)
```

- [ ] **Step 4: Pin the scale-out witness off and drop the new field before hashing**

In `tests/planning/test_exit_sim_scaleout_witness.py`, replace the import block (:2-11) with:

```python
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import simulate_exit
from tests.planning.test_exit_sim_single import _plan
```

After the `FIXTURE = ...` line (:13), add:

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: this byte-identity witness predates the runner give-back
    (default on); it is pinned off and its fixture is never regenerated."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

Before `def witness_rows():` add:

```python
def _witness_dict(res) -> dict:
    """asdict(res) without v176's runner_stop_source: the frozen hash predates the field."""
    out = dataclasses.asdict(res)
    out.pop("runner_stop_source", None)
    return out


```

and in `witness_rows` replace the append line (:48) with:

```python
                    rows.append([f, i, direction, tp2 is not None, _rounded(_witness_dict(res))])
```

`witness_rows` / `witness_hash` are also imported by `tests/planning/test_exit_sim_runner_structure.py` and `tests/planning/test_exit_sim_giveback.py`. The autouse fixture applies only inside this module, so the next step pins the flag in `test_exit_sim_runner_structure.py` too; `test_exit_sim_giveback.py` already sets it off in its own witness test and its `pop("runner_stop_source", None)` is a no-op now.

- [ ] **Step 5: Pin the structure-rule tests off**

In `tests/planning/test_exit_sim_runner_structure.py`, after `E = WARMUP - 1` (:11), add:

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: these tests isolate the structure rule (and reuse the frozen
    scale-out witness), so the runner give-back is pinned off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

In `tests/backtesting/test_runner_structure_parity.py`, after the imports (:8), add:

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: live-vs-replay parity of the structure rule only; the give-back
    has its own tests, so it is pinned off on both sides."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

(`pytest` and `config` are already imported in both files.)

- [ ] **Step 6: Pin the goldens and witnesses off**

`tests/backtesting/test_v139_flag_off_golden.py`, in `test_knobs_off_replay_matches_the_pre_v139_golden` after the two existing `monkeypatch.setattr` lines (:53-54), add:

```python
    # v176: the golden predates the runner give-back (default on); never regenerate it.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

`tests/backtesting/test_v129_flag_off_golden.py`, in `test_flag_off_exits_match_the_pre_v129_golden` after the `ACCEPTANCE_EXIT_ENABLED` line (:57), add:

```python
    # v176: the golden predates the runner give-back (default on); never regenerate it.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

`tests/backtesting/test_v131_witness.py`: add `from swingbot import config` as the first `swingbot` import (above `from swingbot.core.backtesting.backtest import ...`, :14), and after `OPEN_GATES = ...` (:29) add:

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: the witness predates the runner give-back (default on); pinned off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

(Its `_trade_rows` dumps `dataclasses.asdict(trade)` of a backtest trade, not an `ExitResult`, so no field is dropped there. Confirm with `grep -n "asdict" tests/backtesting/test_v131_witness.py`: the only hit is `asdict(trade)` at :69.)

`tests/market/test_v113_horizon_witness.py`, add one entry to `PINS` (:30-41), after `"MAX_RISK_REWARD_RATIO": 2.5,`:

```python
    "RUNNER_GIVEBACK_ENABLED": False,     # v176: default on; the golden predates it
```

`tests/backtesting/test_headroom_witness.py`, replace the test header and its first line (:42-44) with:

```python
@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness(monkeypatch):
    # v176: v123's headroom instrument is the spec's cited baseline; pin the
    # runner give-back (default on) off so the witness keeps measuring it.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    assert config.HEADROOM_SCOPE == "off"
```

(the remaining body from `assert config.HEADROOM_MIN_R == 0.0` on is unchanged).

`tests/scripts/test_runner_headroom.py`: add `from swingbot import config` above `from swingbot.core.marketdata import backtest_cache` (:9), and after the last import (:12) add:

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: these tests pin v123's headroom instrument; the runner give-back
    (default on) is pinned off so their runner exits stay the instrument's."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

- [ ] **Step 7: Run the pinned set to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_witness.py tests/planning/test_exit_sim_scaleout_witness.py tests/planning/test_exit_sim_runner_structure.py tests/backtesting/test_runner_structure_parity.py tests/backtesting/test_v139_flag_off_golden.py tests/backtesting/test_v129_flag_off_golden.py tests/backtesting/test_v131_witness.py tests/market/test_v113_horizon_witness.py tests/backtesting/test_headroom_witness.py tests/scripts/test_runner_headroom.py tests/planning/test_exit_sim_giveback.py`
Expected: PASS (`0 failed`, `0 xfailed`). The slow-marked goldens run too (the `file` profile does not deselect `slow`). If the witness hash still differs with the flag off, V176-5 changed a flag-off walk: that is a V176-5 bug (most likely the `_giveback_extreme` line placed above the bar test, or `_giveback_ratchet` not returning `runner_stop` unchanged when `giveback_level` is None). Fix it in `exit_sim.py` / `exit_sim_v2.py`; never rewrite the `.sha256`.

- [ ] **Step 8: Run every `pin_code_defaults` caller**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/ tests/backtesting/arms/test_engine_instrument.py tests/planning/test_exit_sim_v2_walk.py tests/planning/test_exit_sim_v2_entry.py tests/backtest_scripts/test_measure_fib_diagnostic.py`
Expected: PASS. These now get the give-back off through the default `giveback=False`, which is exactly the pre-v176 code default their goldens were captured on.

- [ ] **Step 9: Run the conditional set and apply the decision table**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_v74_no_behaviour_change.py tests/planning/test_exit_sim_acceptance.py tests/planning/test_acceptance_runner_aggregation.py tests/backtesting/test_acceptance_replay.py tests/backtesting/test_backtest_engine.py tests/planning/test_exit_sim_scaleout.py`

Plus any test name V176-5's commit body recorded as moved (`git -C $WT log -1 --format=%B <V176-5 sha>`).

For each **failing** test, confirm the give-back is the cause first: rerun it alone with the flag forced off, e.g.

```bash
python -m pytest "<path>::<test_name>" -v
```

after temporarily adding `monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)` as the test's first line. If it still fails with the flag off, the cause is not the give-back: stop and report it (a V176-5 regression), do not pin. If it passes, revert the temporary line and apply the table:

- **flag-off rows** (`test_v74_no_behaviour_change.py`, `test_exit_sim_acceptance.py`, `test_acceptance_runner_aggregation.py`, `test_acceptance_replay.py`): add to the module, after its imports (adding `import pytest` / `from swingbot import config` if the file lacks them; `test_v74_no_behaviour_change.py` lacks `import pytest`, `test_acceptance_runner_aggregation.py` lacks both):

```python


@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: this test pins a pre-give-back result (witness / acceptance
    exit, not the runner); the runner give-back (default on) is pinned off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

- **re-pin rows** (`test_backtest_engine.py`, `test_exit_sim_scaleout.py`): these test current engine output, so the new number is the right one. Replace only the literal that moved with the value the failure printed (keep the existing `pytest.approx` / rounding form), and put the old value in a trailing comment, e.g.

```python
    assert result.legs[1]["exit_price"] == pytest.approx(114.0)  # v176: give-back on (was 108.0)
```

  Before re-pinning, re-derive the new value by hand from the fixture bars (give-back = best close since TP1 x 0.95 long / x 1.05 short, effective the next bar) and state the derivation in the commit body. A value you cannot derive is a bug, not a re-pin.

A conditional test that passes gets no edit. Rerun each edited file alone until it passes: `python $WT/scripts/dev/testrun.py file <path>`.

- [ ] **Step 10: Record the decisions**

Append to the commit body one line per test touched or checked in Step 9: `<path>: unmoved | flag-off (moved) | re-pinned <old> -> <new> (<derivation>)`. The spec (§ Risks) requires the per-test decision to be recorded; the commit body is the plan's record, and V176-14's close-out quotes it.

- [ ] **Step 11: Commit**

```bash
git -C $WT add tests/backtesting/test_pullback_dryup_witness.py tests/planning/test_exit_sim_scaleout_witness.py tests/planning/test_exit_sim_runner_structure.py tests/backtesting/test_runner_structure_parity.py tests/backtesting/test_v139_flag_off_golden.py tests/backtesting/test_v129_flag_off_golden.py tests/backtesting/test_v131_witness.py tests/market/test_v113_horizon_witness.py tests/backtesting/test_headroom_witness.py tests/scripts/test_runner_headroom.py
# plus each conditional file Step 9 edited, by path
git -C $WT status --short tests/
git -C $WT commit -m "test(v176): pin witnesses and goldens flag-off, re-pin moved engine tests

pin_code_defaults(giveback=False) keeps every instrument golden on pre-v176
defaults; the scale-out witness drops runner_stop_source before hashing and
its fixture is unchanged.

<Step 10 decision lines>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `git -C $WT status --short tests/` shows no modified fixture file (`*.sha256`, `*.json`, `*.jsonl` under `tests/fixtures/` or `tests/planning/fixtures/`).
