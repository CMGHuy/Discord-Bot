# v157 Instrument v2, phase 2: fills and costs. Part 1b: v2 entries and the `simulate_exit` seam (FC5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (section 2 "Fills and costs", rule 1, "Testing")
**Bump:** bot minor
**Edge:** none (integrity)

> The second half of part 1 (Phase B), split off `2026-10-10-v157-instrument-v2-fills-costs_1-contract-fills-walk.md` only to keep each file under 1500 lines. Index, Global Constraints, Where to work, Parallelisation and the task ledger: `2026-10-10-v157-instrument-v2-fills-costs_0-index.md`. Every task here implicitly includes the index's Global Constraints. Pull the task with `grep -n "^### Task FC5" -A 500 docs/superpowers/plans/2026-10-10-v157-instrument-v2-fills-costs_1b-entries-seam.md`.

`$R` is the main tree's root, `$WT` = `$R/.claude/worktrees/2026-10-10-v157-instrument-v2-fills-costs`. Never `cd`; every command uses absolute paths or `git -C $WT`.

Worked numbers in the tests below were computed by running the code shown here against today's `main`; a mismatch is a bug in the implementation, not a reason to edit an expected value.

# Phase B (continued): v2 entries behind the seam

### Task FC5: v2 entries (next-open market, gap cancel) and the `simulate_exit` seam

**Model:** opus — the dispatch seam on the simulator every backtest shares; a wrong guard silently moves v1 numbers (rule 1), and the entry rules carry three controller decisions.

**Files:**
- Modify: `swingbot/core/planning/exit_sim_v2.py` (created by FC4: imports, two constants, entry functions and `simulate_exit_v2` appended)
- Modify: `swingbot/core/planning/exit_sim.py` (`simulate_exit` only: one keyword, three docstring lines, one dispatch `if`)
- Create: `tests/planning/test_exit_sim_v2_entry.py`

**Interfaces:**
- Consumes:
  - FC4: `walk_v2`, `_context`, `_leg`, `_booked`. FC2: `fills.require_supported`, `entry_touched`, `entry_fill`, `at_or_beyond_stop`, `stop_touched`. FC1: `resolve`, `V1_FILLS`, `ZERO_COSTS`, `InstrumentSpec`.
  - Reused unchanged (verified with `git grep -n`): `exit_sim._not_triggered` :76, `_limit_unfilled` :577, `_hold_cap_bars` :613, `_is_compression` :557; `lifecycle.pending_expired` :137, `pending_invalidated` :144, `limit_cancelled` :170 (order-management rules on a pending order, not fills); `risk_limits.planned_loss_pct` :17; `stop_scope.plan_stop_ceiling` :47; `strategy_types.HORIZONS`.
- Produces (ledger):
  - `GAP_CANCEL = "gap_through_stop"`, `ENTRY_GAP_SCRATCH = "entry_gap_scratch"` (module constants in `exit_sim_v2`).
  - `simulate_exit_v2(df, signal_index: int, plan: TradePlanV2, instrument: InstrumentSpec, *, scale_out: bool = False, max_holding_days: int | None = None) -> ExitResult`.
  - `exit_sim.simulate_exit(df, signal_index, plan, *, scale_out=False, max_holding_days=None, instrument=None)`: FC6 and FC7 pass `instrument=` here.
- Entry rules (index, "Fill rules under v2", and the controller amendment):
  - *Market*: fills at bar `signal_index + 1`'s open. An open at or beyond the stop is `_not_triggered(GAP_CANCEL)` (outcome `not_triggered`, never counted). No next bar: `_not_triggered()`, reason-less.
  - *Limit*: `exit_sim._limit_entry_exit`'s scan on `fills.entry_touched("limit", ..., strict=plan.limit_strict_fill)` and `fills.entry_fill("limit", ...)`; the v131 cancel and the unfilled reasons are v1's (`_limit_unfilled`).
  - *Stop entry* (and any other `entry_type`, as in v1): `simulate_exit`'s stop-entry scan on `fills.entry_touched("stop_entry", ...)` / `entry_fill("stop_entry", ...)`; the compression short keeps its `"risk_cap"` cancel on the actual fill and its strict `"expired"`/`"invalidated"` reasons.
  - *Every* v2 fill bar, whatever the entry type, goes through `_fill_bar_v2`: a fill at or beyond the stop is a 0R scratch at the fill with leg reason `ENTRY_GAP_SCRATCH` (controller decision 3 keeps today's 0R; no cost is booked, because a fill on the wrong side of its stop has no risk to convert costs into; `costs.book` refuses one); otherwise a stop reached on the fill bar is a loss **at the stop level** (the open preceded the fill, so it cannot be the exit), booked through costs; the target is never checked on the fill bar. Under v1 only limits and the compression short check the fill bar; under v2 every stop entry does too (controller amendment: the bar's path after the trigger is unknown, so stop first).
  - Hold cap: `_hold_cap_bars` exactly as v1, counted from the fill bar (`walk_v2` scans `entry_index + 1 ..`).
- The seam: the first statement of `simulate_exit` dispatches `instrument is not None and instrument.version != "v1"` to `simulate_exit_v2` through a function-local import (`exit_sim_v2` imports `exit_sim`). `None` and `resolve("v1")` run today's code line for line. `simulate_exit` goes from cc 11 to 13 (radon counts the `and`), still below 15. No other function body in `exit_sim.py` changes.

- [ ] **Step 1: Write the failing test**, `$WT/tests/planning/test_exit_sim_v2_entry.py`:

```python
"""v157 FC5: v2 entries behind the simulate_exit seam -- next-open market
fills and their gap cancel, limit and stop-entry fills on fills.py, the
fill-bar stop check for every v2 entry, and v1 untouched by the seam."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import (V1_FILLS, ZERO_COSTS,
                                                           InstrumentSpec, resolve)
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.exit_sim_v2 import ENTRY_GAP_SCRATCH, GAP_CANCEL
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
SIGNAL = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)


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


def _run(bars, plan, instrument=FREE, **kw):
    return simulate_exit(make_ohlcv([SIGNAL, *bars]), 0, plan, instrument=instrument, **kw)


# --- market: next open, gap cancel, entry-bar stop ---------------------------

def test_market_entry_fills_at_the_next_open():
    res = _run([(100.5, 101.0, 100.0, 100.8), FLAT], _plan(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 100.5)
    assert (res.outcome, res.exit_index) == ("timeout", 2)


@pytest.mark.parametrize("gap_open", [95.0, 94.0])
def test_market_open_at_or_beyond_the_stop_cancels_uncounted(gap_open):
    res = _run([(gap_open, 96.0, 93.0, 95.5), FLAT], _plan())
    assert (res.outcome, res.cancel_reason, res.legs) == ("not_triggered", GAP_CANCEL, [])


def test_bearish_market_gap_up_through_the_stop_cancels():
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0)
    res = _run([(106.0, 107.0, 105.5, 106.0)], plan)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", GAP_CANCEL)


def test_market_signal_on_the_last_bar_is_not_triggered_without_a_reason():
    res = simulate_exit(make_ohlcv([SIGNAL]), 0, _plan(), instrument=FREE)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def test_market_entry_bar_checks_the_stop_first():
    res = _run([(100.0, 111.0, 94.0, 100.0)], _plan())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 95.0 and res.r_total == -1.0


def test_market_entry_bar_ignores_the_target():
    # bar 1 trades through the 110 target after the 100 open; the walk starts at bar 2.
    res = _run([(100.0, 111.0, 99.0, 110.0), (112.0, 112.5, 111.0, 112.0)], _plan())
    assert (res.outcome, res.exit_index) == ("win", 2)
    assert res.legs[0]["exit_price"] == 112.0           # gapped through: the open


def test_v2_costs_net_the_market_trade():
    res = _run([(100.0, 100.5, 99.5, 100.0), (98.0, 99.0, 94.0, 96.0)], _plan(), V2)
    assert res.entry_price == 100.0
    assert res.r_total == round((95.0 * 0.999 - 100.05) / 5.05, 3)


# --- limit -------------------------------------------------------------------

def _limit(**kw):
    return _plan(entry_type="limit", trigger_price=100.0, stop_loss=98.0, tp1=104.0, **kw)


def test_limit_opening_through_the_limit_fills_at_the_better_open():
    res = _run([(99.5, 100.2, 99.0, 99.8), FLAT], _limit(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 99.5)


def test_limit_filled_at_or_beyond_the_stop_is_a_0r_entry_gap_scratch():
    res = _run([(97.5, 98.0, 97.0, 97.8)], _limit(), V2)
    assert (res.outcome, res.entry_price, res.r_total) == ("scratch", 97.5, 0.0)
    assert res.legs == [{"fraction": 1.0, "exit_price": 97.5, "r": 0.0,
                         "reason": ENTRY_GAP_SCRATCH}]


def test_limit_fill_bar_reaching_the_stop_is_a_loss_at_the_stop():
    res = _run([(99.8, 100.0, 97.9, 98.5)], _limit())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 98.0
    assert res.r_total == round((98.0 - 99.8) / 1.8, 3)


def test_cancellable_limit_keeps_its_unfilled_reasons():
    res = _run([(101.0, 106.0, 100.5, 105.0)], _limit(limit_cancel_level=105.0))
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "cancelled")
    above = (101.0, 101.5, 100.5, 101.0)                 # never reaches the 100 limit
    res = _run([above] * 4, _limit(limit_cancel_level=105.0))
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


# --- stop entry --------------------------------------------------------------

def _breakout(**kw):
    return _plan(entry_type="stop_entry", trigger_price=105.0, stop_loss=100.0, tp1=110.0,
                 **kw)


def test_stop_entry_opening_beyond_the_trigger_fills_at_the_open():
    res = _run([(106.0, 107.0, 105.5, 106.5), FLAT], _breakout(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 106.0)


def test_every_v2_stop_entry_checks_the_stop_on_its_fill_bar():
    # Controller amendment: fills at 105, trades down to 99 on the same bar.
    bars = [(104.0, 106.0, 99.0, 101.0), (101.0, 101.5, 100.5, 101.0)]
    res = _run(bars, _breakout())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 100.0 and res.r_total == -1.0
    v1 = simulate_exit(make_ohlcv([SIGNAL, *bars]), 0, _breakout())
    assert v1.exit_index != 1                              # v1 never checks the fill bar


def test_stop_entry_fill_bar_ignores_the_target():
    res = _run([(104.0, 116.0, 104.0, 115.0), (115.0, 115.5, 114.0, 115.0)], _breakout())
    assert (res.outcome, res.exit_index) == ("win", 2)
    assert res.legs[0]["exit_price"] == 115.0


def test_stop_entry_expiry_and_invalidation_stay_reason_less():
    assert _run([FLAT] * 5, _breakout()).cancel_reason is None
    res = _run([(100.0, 100.5, 99.0, 99.5)], _breakout())
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def _compression(**kw):
    base = dict(strategy=COMPRESSION_SHORT, direction="bearish", entry_type="stop_entry",
                trigger_price=100.0, stop_loss=101.0, tp1=95.0, tp1_fraction=1.0,
                expiry_bars=1, horizon_key="2w")
    base.update(kw)
    return _plan(**base)


def test_compression_gap_fill_beyond_the_risk_cap_is_cancelled():
    plan = _compression()
    gap_open = plan.stop_loss / (1 + plan_stop_ceiling(plan) / 100.0) - 1.0
    res = _run([(gap_open, gap_open + 0.2, gap_open - 0.5, gap_open)], plan)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "risk_cap")


def test_compression_untouched_session_keeps_its_strict_expiry():
    res = _run([(100.5, 100.9, 100.2, 100.6), FLAT], _compression())
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


# --- the seam ----------------------------------------------------------------

@pytest.mark.parametrize("plan", [_plan(), _limit(), _breakout()])
def test_v1_spec_and_no_spec_run_the_same_v1_code(plan):
    df = make_ohlcv([SIGNAL, (100.5, 106.0, 99.0, 104.0), (104.0, 111.0, 103.0, 110.0), FLAT])
    assert simulate_exit(df, 0, plan, scale_out=True, instrument=resolve("v1")) == \
        simulate_exit(df, 0, plan, scale_out=True)


def test_a_v2_spec_without_next_open_fills_is_refused():
    odd = InstrumentSpec("v2", V1_FILLS, ZERO_COSTS)
    with pytest.raises(ValueError, match="next_open"):
        simulate_exit(make_ohlcv([SIGNAL, FLAT]), 0, _plan(), instrument=odd)


def test_hold_cap_is_resolved_as_in_v1():
    res = _run([FLAT] * 6, _plan(hold_cap_bars=2))
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 3)
```

Why `test_every_v2_stop_entry_checks_the_stop_on_its_fill_bar` also runs v1: it pins that the amendment is v2-only. On the same tape v1's walk starts at bar 2 and never sees bar 1's 99 low.

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py`
Expected: collection error, `ImportError: cannot import name 'ENTRY_GAP_SCRATCH' from 'swingbot.core.planning.exit_sim_v2'`.

- [ ] **Step 3: Implement the entries.** Three edits in `$WT/swingbot/core/planning/exit_sim_v2.py`.

(a) Replace the FC4 import lines

```python
from .exit_sim import (ExitResult, _chandelier_ratchet, _is_compression, _no_trade,
                       _runner_timeout, _structure_update, _tenth_session_reached,
                       acceptance_exit, runner_floor, runner_structure_frame)
from .plan_types import TradePlanV2
```

with

```python
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import planned_loss_pct
from .exit_sim import (ExitResult, _chandelier_ratchet, _hold_cap_bars, _is_compression,
                       _limit_unfilled, _no_trade, _not_triggered, _runner_timeout,
                       _structure_update, _tenth_session_reached, acceptance_exit,
                       runner_floor, runner_structure_frame)
from .lifecycle import limit_cancelled, pending_expired, pending_invalidated
from .plan_types import TradePlanV2
from .stop_scope import plan_stop_ceiling
```

(b) Directly under `from .time_exit import PROXY_BASIS, TIME_EXIT_REASON`, add:

```python

#: A market entry whose next open is at or beyond the stop: cancelled, never counted.
GAP_CANCEL = "gap_through_stop"
#: A limit or stop entry filled at or beyond the stop: a 0R scratch at the fill
#: (v1's leg reason for it is "gap_through_stop"; v2 keeps that string for the cancel).
ENTRY_GAP_SCRATCH = "entry_gap_scratch"
```

(c) Append at the end of the module, after `walk_v2`:

```python


def _entry_gap_scratch(j: int, fill: float) -> ExitResult:
    """The fill sits at or through the stop, so the bracket stop fires at once:
    a flat 0R scratch at the fill (controller decision 3 keeps today's 0R). No
    cost is booked: the trade has no risk on the right side of its stop, so it
    has no R to convert costs into."""
    return ExitResult(outcome="scratch", runner_outcome=None, entry_index=j, exit_index=j,
                      entry_price=fill, r_total=0.0,
                      legs=[{"fraction": 1.0, "exit_price": fill, "r": 0.0,
                             "reason": ENTRY_GAP_SCRATCH}])


def _fill_bar_v2(df, j: int, fill: float, plan: TradePlanV2,
                 instrument: InstrumentSpec) -> ExitResult | None:
    """Every v2 fill bar is checked for the stop, never the target: the path
    after the fill is unknown, so stop first. The open came before the fill,
    so a stop reached later on the bar fills at the stop itself."""
    direction = plan.direction
    if fills.at_or_beyond_stop(fill, plan.stop_loss, direction):
        return _entry_gap_scratch(j, fill)
    if not fills.stop_touched(float(df["High"].values[j]), float(df["Low"].values[j]),
                              plan.stop_loss, direction):
        return None
    ctx = _context(df, j, fill, plan, 0, instrument, False)
    return _booked(ctx, "loss", j, [_leg(1.0, plan.stop_loss, "stop", "stop")])


def _filled(df, j: int, fill: float, plan: TradePlanV2, instrument: InstrumentSpec,
            scale_out: bool, max_holding_days: int) -> ExitResult:
    early = _fill_bar_v2(df, j, fill, plan, instrument)
    if early is not None:
        return early
    return walk_v2(df, j, fill, plan, max_holding_days, instrument, scale_out=scale_out)


def _market_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """The alert goes out after the signal close; the order fills at the next
    open. An open at or beyond the stop cancels it (GAP_CANCEL)."""
    j = signal_index + 1
    if j >= len(df):
        return _not_triggered()
    fill = fills.entry_fill(instrument.fill_model, "market", plan.direction,
                            bar_open=float(df["Open"].values[j]))
    if fills.at_or_beyond_stop(fill, plan.stop_loss, plan.direction):
        return _not_triggered(GAP_CANCEL)
    return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)


def _limit_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """exit_sim._limit_entry_exit on fills.py's touch and fill rules: the fill
    is checked first, then the v131 cancel level; unfilled rows keep v1's reasons."""
    high, low, open_ = df["High"].values, df["Low"].values, df["Open"].values
    last = min(signal_index + plan.expiry_bars, len(df) - 1)
    for j in range(signal_index + 1, last + 1):
        bar_high, bar_low = float(high[j]), float(low[j])
        if not fills.entry_touched("limit", plan.direction, bar_high, bar_low,
                                   plan.trigger_price, strict=bool(plan.limit_strict_fill)):
            if limit_cancelled(plan, bar_high, bar_low):
                return _limit_unfilled(plan, cancelled=True)
            continue
        fill = fills.entry_fill(instrument.fill_model, "limit", plan.direction,
                                bar_open=float(open_[j]), level=plan.trigger_price)
        return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)
    return _limit_unfilled(plan, cancelled=False)


def _stop_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """exit_sim's stop-entry scan on fills.py's touch and fill rules. The
    compression short keeps its risk-cap cancel on the actual fill and its
    strict not_triggered reasons."""
    high, low = df["High"].values, df["Low"].values
    open_, close = df["Open"].values, df["Close"].values
    strict = _is_compression(plan)
    for j in range(signal_index + 1, len(df)):
        if pending_expired(plan, j - signal_index):
            break
        if fills.entry_touched("stop_entry", plan.direction, float(high[j]), float(low[j]),
                               plan.trigger_price):
            fill = fills.entry_fill(instrument.fill_model, "stop_entry", plan.direction,
                                    bar_open=float(open_[j]), level=plan.trigger_price)
            if strict and planned_loss_pct(fill, plan.stop_loss) > plan_stop_ceiling(plan):
                return _not_triggered("risk_cap")
            return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)
        if pending_invalidated(plan, float(close[j])):
            return _not_triggered("invalidated" if strict else None)
    return _not_triggered("expired" if strict else None)


_ENTRIES = {"market": _market_entry_v2, "limit": _limit_entry_v2}


def simulate_exit_v2(df, signal_index: int, plan: TradePlanV2, instrument: InstrumentSpec,
                     *, scale_out: bool = False,
                     max_holding_days: int | None = None) -> ExitResult:
    """exit_sim.simulate_exit under a v2 instrument: the entry (market at the
    next open, limit, stop entry -- any other entry_type is a stop entry, as
    in v1), the fill-bar stop check, then walk_v2. Same hold-cap resolution
    as v1."""
    fills.require_supported(instrument.fill_model)
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]
    max_holding_days = _hold_cap_bars(plan, max_holding_days)
    entry = _ENTRIES.get(plan.entry_type, _stop_entry_v2)
    return entry(df, signal_index, plan, instrument, scale_out, max_holding_days)
```

- [ ] **Step 4: Run the entry tests without the seam.**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py`
Expected: `23 failed`, each with `TypeError: simulate_exit() got an unexpected keyword argument 'instrument'` (the seam is still missing).

- [ ] **Step 5: Implement the seam** in `$WT/swingbot/core/planning/exit_sim.py`, inside `simulate_exit` only.

(a) The signature gains one keyword, after `max_holding_days`:

```python
    scale_out: bool = False,
    max_holding_days: int | None = None,
    instrument=None,
) -> ExitResult:
```

(b) In its docstring, directly after the first line `"""Shared entry + exit simulator (Tasks 18/20/21/24).`, add a blank line and:

```
    ``instrument`` (v157): None or the v1 ``InstrumentSpec`` runs the code
    below, unchanged. Any other version is handed to
    ``exit_sim_v2.simulate_exit_v2`` (next-open market entries, gap-through
    fills, costs booked in R; v136 spec section 2).
```

(c) The first statement of the body, above the comment `# Resolved eagerly per the interface contract`:

```python
    if instrument is not None and instrument.version != "v1":
        from .exit_sim_v2 import simulate_exit_v2   # exit_sim_v2 imports this module
        return simulate_exit_v2(df, signal_index, plan, instrument, scale_out=scale_out,
                                max_holding_days=max_holding_days)
```

Nothing else in `exit_sim.py` changes: `git -C $WT diff --stat swingbot/core/planning/exit_sim.py` shows one file, about 10 insertions, 0 deletions.

- [ ] **Step 6: Run the new tests, every older exit test, the v1 goldens and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py`
Expected: `23 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/planning/`
Expected: `0 failed` (covers `test_exit_sim_{entry,single,scaleout,scaleout_witness,hold_cap,acceptance,runner_structure}.py`, `test_limit_cancel.py`, `test_compression_short_fill.py`, `test_plan_manager_gaps.py`, FC4's walk tests).
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `1 passed` (slow-marked, so run it by file; never regenerate the golden).
Run: `python -m radon cc -s -n C $WT/swingbot/core/planning/exit_sim_v2.py $WT/swingbot/core/planning/exit_sim.py`
Expected: exactly three C entries, all in `exit_sim.py`: `_single_leg_exit_walk - C (14)` and `_pre_tp1_phase - C (12)` (both untouched) and `simulate_exit - C (13)`; nothing from `exit_sim_v2.py` (its largest, `_stop_entry_v2`, is B (9)).

- [ ] **Step 7: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/planning/exit_sim_v2.py swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_v2_entry.py
git -C $WT commit -m "feat(v157): v2 entries -- next-open market fill and gap cancel, fill-bar stop check; simulate_exit(instrument=) seam (FC5)"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows nothing new.
