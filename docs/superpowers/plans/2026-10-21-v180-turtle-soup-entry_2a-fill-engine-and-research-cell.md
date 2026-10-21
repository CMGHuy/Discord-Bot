# v180 — Turtle Soup entry, part 2a: fill engine and research cell

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-21-v180-turtle-soup-entry-design.md](../specs/2026-10-21-v180-turtle-soup-entry-design.md)
**Index:** [2026-10-21-v180-turtle-soup-entry_0-index.md](2026-10-21-v180-turtle-soup-entry_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Contracts`, `## Parallelisation` and the task ledger live there and bind every task below.
**Brief:** `.superpowers/briefs/2026-10-21-v180-turtle-soup-entry.md`

Tasks V180-5..V180-7 (V180-8 is part 2b). Every task runs in the worktree `.claude/worktrees/2026-10-21-v180-turtle-soup-entry` (created in V180-1) and commits on its branch. All paths below are relative to that worktree. Run every command from the worktree root.

Part 1 creates the names these tasks consume: `TURTLE_SOUP`, `turtle_soup_signal`, `sweep_frame` (V180-1), `STRUCTURAL_DROP_STRATEGIES`, `PLAN_SHAPES[TURTLE_SOUP]`, `turtle_soup_rejection_reason`, `RISK_CAP`, `NO_LEVEL_IN_BAND`, `PLAN_OTHER` (V180-4), and `population_split` already exists in `acceptance.py`. Check each with `git grep -n` before starting a task; a missing one means its part-1 task has not merged into the branch yet, so stop.

## Review Focus

1. **A signal on the last bar of the frame.** There is no next open, so the plan must come back `not_triggered` with no cancel reason, never an index error. Test: `test_a_signal_on_the_last_bar_never_fills` (V180-5).
2. **A walk cut short by the end of the data.** It must keep the plain `timeout` label and no `price_basis`, so a right-censored trade is never reported as a time-cap exit. Test: `test_a_walk_cut_short_by_the_data_is_a_plain_timeout` (V180-5).
3. **A gap through the target on the fill bar itself.** The open is both the fill and the exit: 0R gross, a `scratch`, never a win. Test: `test_an_open_through_the_target_on_the_fill_bar_is_a_scratch` (V180-5).

---

# Phase C — the fill engine

### Task V180-5: Next-open fill, open-through-stop cancel, fill risk cap and gap-aware single leg

**Model:** opus — replay fill semantics on the shared v1 simulator: a wrong session count or gap rule silently biases every Turtle Soup row, and three existing paths must stay byte-identical.

**Files:**
- Create: `swingbot/core/planning/next_open_entry.py`
- Create: `tests/planning/test_next_open_entry.py`
- Modify: `swingbot/core/planning/exit_sim.py` (`_hold_cap_bars` ~l.816, `simulate_exit` market branch ~l.876-879, new `SESSION_ONE_HOLD_CAP`, `_counts_fill_session`, `_market_exit`)

**Interfaces:**
- Consumes:
  - `TURTLE_SOUP` (V180-1, `swingbot/core/market/strategy_types.py`).
  - From V180-4: `PLAN_SHAPES[TURTLE_SOUP]` = `{"entry_type": "market", "expiry_bars": 1, "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0, "hold_cap_bars": 10}`, and `STRUCTURAL_DROP_STRATEGIES`. Together they make `stop_scope.plan_stop_ceiling(plan)` return the 2w DROP ceiling 3.0 for a Turtle Soup strategy plan.
  - Existing: `exit_sim.ExitResult`, `exit_sim._not_triggered(cancel_reason=None)`, `exit_sim._acceptance_result(plan, j, close_j, entry_index, entry_price, sign, risk)`, `exit_sim._tenth_session_reached(plan, entry_index, exit_index)`, `plan_manager.gap_stop_fill(bar_open, level, direction)`, `plan_manager.gap_target_fill(bar_open, level, direction)`, `risk_limits.planned_loss_pct(entry, stop)`, `time_exit.TIME_EXIT_REASON`, `time_exit.PROXY_BASIS`.
- Produces (V180-7 consumes the cancel reasons through `ExitResult.cancel_reason`; V180-8 reads the leg reasons):
  - `next_open_entry.NEXT_OPEN_STRATEGIES = frozenset({TURTLE_SOUP})`
  - `next_open_entry.OPEN_THROUGH_STOP = "open_through_stop"`, `RISK_CAP = "risk_cap"`, `GAP_STOP_REASON = "gap_stop"`, `GAP_TARGET_REASON = "gap_target"`
  - `uses_next_open_fill(plan) -> bool`
  - `next_open_exit(df, signal_index: int, plan, max_holding_days: int) -> ExitResult`
  - `gap_aware_single_leg_walk(df, entry_index: int, entry_price: float, plan, max_holding_days: int) -> ExitResult`
  - `exit_sim.SESSION_ONE_HOLD_CAP = frozenset({COMPRESSION_SHORT, TURTLE_SOUP})`, `exit_sim._counts_fill_session(plan) -> bool`, `exit_sim._market_exit(df, signal_index, plan, scale_out, max_holding_days) -> ExitResult`

**Session count (the spec's quant-engineer check, settled here).**

- The screen's `race()` walks bars `t+1 .. t+CAP` and exits at the close of `t+10`.
- Here the fill bar `t+1` is session 1, and the walk includes it.
- `simulate_exit` already passes `_hold_cap_bars(plan, max_holding_days)`, which becomes `10 - 1 = 9` for Turtle Soup. The walk therefore covers `entry_index .. entry_index + 9`, which is `t+1 .. t+10`.

The two counts are identical. V180-14's results doc states this.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_next_open_entry.py`:

```python
"""V180-5: Turtle Soup fills at the next open. An open at or below the stop cancels, a stop
farther than the 3% ceiling from the fill drops the plan, and one whole-position leg walks
from the fill bar with gap fills and a ten-session cap (fill = session 1)."""
import pytest

from swingbot.core.market.strategy_types import COMPRESSION_SHORT, HORIZONS, TURTLE_SOUP
from swingbot.core.planning import exit_sim
from swingbot.core.planning import next_open_entry as noe
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.time_exit import PROXY_BASIS, TIME_EXIT_REASON
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
FLAT = (100.0, 100.5, 99.5, 100.0)      # open, high, low, close: never reaches 98 or 104


def _bars(overrides=None, n=60):
    rows = [FLAT] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _ts(**kw):
    shape = PLAN_SHAPES[TURTLE_SOUP]
    base = dict(strategy=TURTLE_SOUP, horizon_key="2w", direction="bullish",
                entry_type=shape["entry_type"], expiry_bars=shape["expiry_bars"],
                tp1_fraction=shape["tp1_fraction"],
                breakeven_trigger_fraction=shape["breakeven_trigger_fraction"],
                hold_cap_bars=shape["hold_cap_bars"], trigger_price=100.0,
                stop_loss=98.0, tp1=104.0, tp2=None)
    base.update(kw)
    return _plan(**base)


def _run(df, plan=None):
    return simulate_exit(df, SIGNAL, plan or _ts(), scale_out=True)


def test_turtle_soup_is_the_only_next_open_strategy():
    assert noe.NEXT_OPEN_STRATEGIES == frozenset({TURTLE_SOUP})
    assert noe.uses_next_open_fill(_ts())
    assert not noe.uses_next_open_fill(_plan())          # a Fibonacci market plan


def test_fills_at_the_next_open_not_the_signal_close():
    result = _run(_bars({SIGNAL + 1: (100.2, 100.6, 99.8, 100.3)}))
    assert result.entry_index == SIGNAL + 1 and result.entry_price == 100.2


def test_other_market_plans_still_fill_at_the_signal_close():
    result = simulate_exit(_bars(), SIGNAL, _plan(), scale_out=True)
    assert result.entry_index == SIGNAL and result.entry_price == 100.0


@pytest.mark.parametrize("bar_open", [98.0, 97.0])
def test_an_open_at_or_below_the_stop_cancels(bar_open):
    result = _run(_bars({SIGNAL + 1: (bar_open, 99.0, bar_open - 0.5, 98.5)}))
    assert result.outcome == "not_triggered"
    assert result.cancel_reason == noe.OPEN_THROUGH_STOP == "open_through_stop"
    assert result.legs == [] and result.entry_index is None


def test_a_stop_beyond_three_percent_of_the_fill_is_dropped():
    # (101.5 - 98) / 101.5 = 3.45% > the 2w ceiling of 3.0%
    result = _run(_bars({SIGNAL + 1: (101.5, 101.8, 101.0, 101.4)}))
    assert result.outcome == "not_triggered"
    assert result.cancel_reason == noe.RISK_CAP == "risk_cap"


def test_a_stop_inside_the_ceiling_fills_and_is_never_moved():
    # (100.9 - 98) / 100.9 = 2.87%: fills; the stop the walk honours is still 98
    df = _bars({SIGNAL + 1: (100.9, 101.0, 100.5, 100.8),
                SIGNAL + 3: (99.0, 99.2, 97.9, 98.5)})
    result = _run(df)
    assert result.entry_price == 100.9
    assert result.outcome == "loss" and result.r_total == -1.0
    assert result.legs[0]["exit_price"] == 98.0 and result.legs[0]["reason"] == "stop"


def test_a_gap_through_the_stop_fills_at_the_open():
    result = _run(_bars({SIGNAL + 3: (97.0, 97.5, 96.5, 97.2)}))
    assert result.outcome == "loss" and result.exit_index == SIGNAL + 3
    assert result.legs[0] == {"fraction": 1.0, "exit_price": 97.0, "r": -1.5,
                              "reason": noe.GAP_STOP_REASON}
    assert result.r_total == -1.5


def test_a_gap_through_the_target_fills_at_the_better_open():
    result = _run(_bars({SIGNAL + 3: (105.0, 105.5, 104.6, 105.2)}))
    assert result.outcome == "win" and result.r_total == 2.5
    assert result.legs[0]["exit_price"] == 105.0
    assert result.legs[0]["reason"] == noe.GAP_TARGET_REASON == "gap_target"


def test_an_open_through_the_target_on_the_fill_bar_is_a_scratch():
    # stop 99, target 101; the fill opens at 101.2 (2.17% risk): out at the fill, 0R gross
    plan = _ts(stop_loss=99.0, tp1=101.0)
    result = _run(_bars({SIGNAL + 1: (101.2, 101.5, 100.9, 101.3)}), plan)
    assert result.outcome == "scratch" and result.r_total == 0.0
    assert result.entry_index == result.exit_index == SIGNAL + 1
    assert result.legs[0]["reason"] == "gap_target"


def test_the_fill_bar_is_walked_stop_before_target():
    result = _run(_bars({SIGNAL + 1: (100.0, 104.5, 97.5, 103.0)}))
    assert result.outcome == "loss" and result.r_total == -1.0
    assert result.exit_index == SIGNAL + 1 and result.legs[0]["reason"] == "stop"


def test_an_intraday_target_touch_is_a_win_at_the_target():
    result = _run(_bars({SIGNAL + 4: (100.0, 104.2, 99.8, 104.0)}))
    assert result.outcome == "win" and result.exit_index == SIGNAL + 4
    assert result.legs[0]["exit_price"] == 104.0 and result.legs[0]["reason"] == "tp1"
    assert result.r_total == 2.0


def test_the_hold_cap_closes_the_tenth_session_counting_the_fill():
    result = _run(_bars())
    assert result.outcome == "timeout"
    assert result.exit_index == result.entry_index + 9 == SIGNAL + 10     # the screen's t+10 close
    leg = result.legs[0]
    assert leg["reason"] == TIME_EXIT_REASON and leg["price_basis"] == PROXY_BASIS
    assert result.r_total == 0.0


def test_a_walk_cut_short_by_the_data_is_a_plain_timeout():
    df = _bars(n=SIGNAL + 5)
    result = _run(df)
    assert result.outcome == "timeout" and result.exit_index == len(df) - 1
    assert result.legs[0]["reason"] == "timeout" and "price_basis" not in result.legs[0]


def test_a_signal_on_the_last_bar_never_fills():
    result = _run(_bars(n=SIGNAL + 1))
    assert result.outcome == "not_triggered" and result.cancel_reason is None


def test_the_v129_acceptance_exit_closes_at_the_bar_close():
    plan = _ts(acceptance_close_below=99.0)
    result = _run(_bars({SIGNAL + 3: (99.5, 99.8, 98.6, 98.8)}), plan)
    assert result.outcome == "loss" and result.exit_index == SIGNAL + 3
    assert result.legs[0]["reason"] == "acceptance_exit" and result.r_total == -0.6


def test_a_bearish_plan_is_refused():
    with pytest.raises(ValueError):
        noe.next_open_exit(_bars(), SIGNAL, _ts(direction="bearish", stop_loss=102.0, tp1=96.0), 9)


def test_hold_cap_counts_the_fill_session_for_both_session_one_strategies():
    assert exit_sim.SESSION_ONE_HOLD_CAP == frozenset({COMPRESSION_SHORT, TURTLE_SOUP})
    assert exit_sim._hold_cap_bars(_ts(), 14) == 9
    compression = _plan(strategy=COMPRESSION_SHORT, horizon_key="2w", hold_cap_bars=10)
    assert exit_sim._hold_cap_bars(compression, 14) == 9
    assert exit_sim._hold_cap_bars(_plan(hold_cap_bars=10), 14) == 10
    assert exit_sim._hold_cap_bars(_ts(), 5) == 5


def test_the_two_week_horizon_admits_the_ten_session_hold():
    assert HORIZONS["2w"]["max_holding_days"] >= PLAN_SHAPES[TURTLE_SOUP]["hold_cap_bars"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_next_open_entry.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'swingbot.core.planning.next_open_entry'`.

- [ ] **Step 3: Create `swingbot/core/planning/next_open_entry.py`**

Module docstring, in substance:

- The v1 market entry fills at the signal close. A Turtle Soup alert is entered as orders before the open, so its replay fills at `Open[t+1]`, the way live would.
- An open at or below the stop cancels.
- A stop farther than the plan's ceiling from the fill drops the plan; it is never squeezed.
- A bar that opens beyond the stop or the target fills at that open (`plan_manager`'s live convention).
- This is the v1 path only; `exit_sim_v2` is untouched.

Imports, all at top level. `exit_sim` imports this module lazily inside `_market_exit`, so there is no cycle:

```python
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.risk_limits import planned_loss_pct
from .exit_sim import ExitResult, _acceptance_result, _not_triggered, _tenth_session_reached
from .plan_manager import gap_stop_fill, gap_target_fill
from .stop_scope import plan_stop_ceiling
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON
```

Constants exactly as in Interfaces. Functions:

- `uses_next_open_fill(plan) -> bool`: `plan.strategy in NEXT_OPEN_STRATEGIES`.
- `next_open_exit(df, signal_index, plan, max_holding_days) -> ExitResult`. `max_holding_days` is the walk length after the fill bar, as `simulate_exit` passes it (`_hold_cap_bars` already applied). Steps:
  1. `plan.direction != "bullish"` → `raise ValueError("next-open fill is long-only (v180 Turtle Soup)")`.
  2. `j = signal_index + 1`; `j >= len(df)` → `_not_triggered()` (no cancel reason).
  3. `fill = float(df["Open"].values[j])`; `fill <= plan.stop_loss` → `_not_triggered(OPEN_THROUGH_STOP)`.
  4. `planned_loss_pct(fill, plan.stop_loss) > plan_stop_ceiling(plan)` → `_not_triggered(RISK_CAP)`.
  5. Otherwise return `gap_aware_single_leg_walk(df, j, fill, plan, max_holding_days)`.
- `gap_aware_single_leg_walk(df, entry_index, entry_price, plan, max_holding_days) -> ExitResult`. It is long only. Every `r` is `round((exit_price - entry_price) / risk, 3)`, with `risk = entry_price - plan.stop_loss`. So a stop exit is exactly `-1.0`, and a target exit is the plan's R:R from the fill. Two helpers keep it under complexity 15:

```python
def _bar_exit(plan, bar_open, bar_high, bar_low, entry_price):
    """(outcome, exit_price, reason) for the first exit this bar makes, or None.
    Order: open through the stop, open through the target, low touches the stop
    (stop first, as everywhere in this engine), high touches the target."""
    if bar_open <= plan.stop_loss:
        return "loss", gap_stop_fill(bar_open, plan.stop_loss, "bullish"), GAP_STOP_REASON
    if bar_open >= plan.tp1:
        price = gap_target_fill(bar_open, plan.tp1, "bullish")
        return ("win" if price > entry_price else "scratch"), price, GAP_TARGET_REASON
    if bar_low <= plan.stop_loss:
        return "loss", plan.stop_loss, "stop"
    if bar_high >= plan.tp1:
        return "win", plan.tp1, "tp1"
    return None


def gap_aware_single_leg_walk(df, entry_index, entry_price, plan, max_holding_days):
    risk = entry_price - plan.stop_loss
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None, entry_index=entry_index,
                          exit_index=None, entry_price=entry_price, r_total=0.0, legs=[])
    opens, highs, lows, closes = (df[col].values for col in ("Open", "High", "Low", "Close"))
    end = min(entry_index + max_holding_days, len(df) - 1)
    for j in range(entry_index, end + 1):          # the fill bar is session 1 and is walked
        hit = _bar_exit(plan, float(opens[j]), float(highs[j]), float(lows[j]), entry_price)
        if hit is not None:
            return _booked(hit, entry_index, j, entry_price, risk)
        accepted = _acceptance_result(plan, j, float(closes[j]), entry_index, entry_price, 1, risk)
        if accepted is not None:                    # v129, after stop and target
            return accepted
    return _time_exit(plan, entry_index, end, entry_price, float(closes[end]), risk)
```

The two helpers:

- `_booked((outcome, price, reason), entry_index, j, entry_price, risk)` returns `ExitResult(outcome, None, entry_index, j, entry_price, r, [{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])`.
- `_time_exit` books outcome `"timeout"` at the last close, with leg reason `"timeout"`.
  - When `_tenth_session_reached(plan, entry_index, end)` is True, it sets the leg's `reason` to `TIME_EXIT_REASON` and adds `"price_basis": PROXY_BASIS`, as the compression short's `_single_leg_booking` does.
  - A right-censored walk keeps the plain label.

- [ ] **Step 4: Wire `exit_sim.py`**

1. Import `TURTLE_SOUP` beside `COMPRESSION_SHORT` from `swingbot.core.market.strategy_types`.
2. Add, next to `_is_compression`:

```python
#: v180: strategies whose fill session is session 1 of their hold cap (live: the tenth session closes).
SESSION_ONE_HOLD_CAP = frozenset({COMPRESSION_SHORT, TURTLE_SOUP})


def _counts_fill_session(plan) -> bool:
    return getattr(plan, "strategy", None) in SESSION_ONE_HOLD_CAP
```

3. In `_hold_cap_bars`:
   - Replace `_is_compression(plan)` with `_counts_fill_session(plan)`.
   - Update its docstring: the compression short's and Turtle Soup's fill session is session 1.
   - Leave `_is_compression` and its other callers unchanged: `_single_leg_booking`, the strict stop-entry path, `exit_sim_v2` and `override_fidelity`.
4. Add `_market_exit` and route `simulate_exit`'s market branch through it. Nothing else in `simulate_exit` changes, so its complexity stays at 13:

```python
def _market_exit(df, signal_index: int, plan: TradePlanV2, scale_out: bool,
                 max_holding_days: int) -> ExitResult:
    """A market entry: v180 next-open plans fill at Open[t+1] (next_open_entry); every other
    market plan fills at the signal bar's close, exactly as before."""
    from . import next_open_entry     # next_open_entry imports this module
    if next_open_entry.uses_next_open_fill(plan):
        return next_open_entry.next_open_exit(df, signal_index, plan, max_holding_days)
    entry_price = float(df["Close"].values[signal_index])
    return _walk_for(plan, scale_out)(df, signal_index, entry_price, plan, max_holding_days)
```

```python
    if plan.entry_type == "market":
        return _market_exit(df, signal_index, plan, scale_out, max_holding_days)
```

5. In `simulate_exit`'s docstring, extend the sentence "``market`` entries fill immediately at the signal bar's close" with: "except a v180 next-open strategy (``next_open_entry.NEXT_OPEN_STRATEGIES``), which fills at the next bar's open".

- [ ] **Step 5: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_next_open_entry.py`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 6: Prove the existing paths are byte-identical**

Run each. All must pass unmodified:

```bash
python scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py
python scripts/dev/testrun.py file tests/planning/test_compression_short_fill.py
python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_single.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_acceptance.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout_witness.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py
python scripts/dev/complexity_gate.py
```

Expected:

- Every test file is green.
- `complexity_gate.py` reports no regression: `simulate_exit` is still 13, and every new function is below 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/next_open_entry.py swingbot/core/planning/exit_sim.py tests/planning/test_next_open_entry.py
git commit -m "feat(v180): next-open fill, open-through-stop cancel, fill risk cap and gap-aware single leg for Turtle Soup" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V180-6: Research knob TURTLE_SOUP_RESEARCH_MODE

**Model:** haiku — mechanical registration of one select knob in four known places, copying the `COMPRESSION_SHORT_RESEARCH_MODE` precedent line for line.

**Files:**
- Modify: `swingbot/config.py` (the `Field(...)` list beside `COMPRESSION_SHORT_RESEARCH_MODE` ~l.1035; `_SEARCH_CLASSES["searchable"]` ~l.1451; `_MODE_VALUES` ~l.1502)
- Modify: `.env.example` (after `COMPRESSION_SHORT_RESEARCH_MODE=off`, ~l.608)
- Modify: `swingbot/scan_params.py` (dataclass field ~l.89; `from_config` ~l.158)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (`REGISTRY`, after the compression entry ~l.92)
- Create: `tests/backtesting/test_turtle_soup_knob.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing: `config.FIELDS`, `knobs.parse_knob`, `knobs.apply_knobs`, `reachability.Reach`, `reachability.REACHABLE`, `reachability.S`.
- Produces (V180-7 reads it through `turtle_soup_research.research_mode()`; V180-8's `measure_arms` keys its sidecar on it):
  - `config.TURTLE_SOUP_RESEARCH_MODE` ∈ `("off", "structural")`, default `"off"`
  - `ScanParams.turtle_soup_research_mode: str = "off"`
  - `reachability.REGISTRY["TURTLE_SOUP_RESEARCH_MODE"]` = `Reach(REACHABLE, <reason>, S)`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_turtle_soup_knob.py`:

```python
"""V180-6: TURTLE_SOUP_RESEARCH_MODE is a research-only select (off | structural), default off,
searchable, reachable through the strategy engine only, and threaded through ScanParams."""
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability
from swingbot.core.backtesting.arms.knobs import apply_knobs, parse_knob
from swingbot.scan_params import ScanParams

KNOB = "TURTLE_SOUP_RESEARCH_MODE"
ROOT = Path(__file__).resolve().parent.parent.parent


def test_knob_is_a_research_select_defaulting_off():
    field = next(f for f in config.FIELDS if f.attr == KNOB)
    assert field.default == "off"
    assert [value for value, _ in field.options] == ["off", "structural"]
    assert config.TURTLE_SOUP_RESEARCH_MODE == "off"


def test_parse_knob_accepts_only_the_two_modes():
    assert parse_knob(f"{KNOB}=structural") == (KNOB, "structural")
    with pytest.raises(ValueError):
        parse_knob(f"{KNOB}=screened")          # arm A is closed without a run


def test_knob_is_reachable_through_the_strategy_engine_only():
    reach = reachability.REGISTRY[KNOB]
    assert reach.cls == reachability.REACHABLE
    assert reach.observed_by == frozenset({"strategy"})
    assert reach.fixture_observable is False
    assert "v180" in reach.reason


def test_scan_params_carries_the_knob():
    assert ScanParams.from_config().turtle_soup_research_mode == "off"
    with apply_knobs({KNOB: "structural"}):
        assert ScanParams.from_config().turtle_soup_research_mode == "structural"
    assert config.TURTLE_SOUP_RESEARCH_MODE == "off"           # restored


def test_env_example_documents_it_off():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"\n{KNOB}=off\n" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_knob.py`
Expected: FAIL, with `StopIteration` in the first test and `KeyError: 'TURTLE_SOUP_RESEARCH_MODE'` in the reachability test.

- [ ] **Step 3: Register the knob**

1. `swingbot/config.py`, directly after the `COMPRESSION_SHORT_RESEARCH_MODE` `Field(...)`:

```python
    Field("TURTLE_SOUP_RESEARCH_MODE", "TURTLE_SOUP_RESEARCH_MODE", "Universe & Scanning",
          "Turtle Soup: research replay mode (v180)", type="select", default="off",
          options=["off", "structural"],
          help="v180 research-only measurement knob: the historical replay "
               "(scripts/backtest/measure_arms.py, StrategyEngine) adds the masked Turtle Soup long "
               "in its bullish 2w research cell, with the structural stop and level-map target. "
               "Nothing in the live bot reads it -- the live strategy mask stays closed. "
               "Off (default): the replay runs without Turtle Soup."),
```

2. Add `"TURTLE_SOUP_RESEARCH_MODE",` to `_SEARCH_CLASSES["searchable"]`, on the line after `"COMPRESSION_SHORT_RESEARCH_MODE",`.
3. Add `"TURTLE_SOUP_RESEARCH_MODE": ("off", "structural"),` to `_MODE_VALUES`, after the compression entry.
4. `.env.example`: after the `COMPRESSION_SHORT_RESEARCH_MODE=off` line, add a blank line and:

```
# v180 research-only: the historical replay (measure_arms.py, StrategyEngine)
# adds the masked Turtle Soup long in its bullish 2w research cell
# (off | structural). The live bot never reads it.
TURTLE_SOUP_RESEARCH_MODE=off
```

5. `swingbot/scan_params.py`:
   - Add `turtle_soup_research_mode: str = "off"   # v180 research replay only` after `compression_short_research_mode`.
   - In `from_config`, add `turtle_soup_research_mode=config.TURTLE_SOUP_RESEARCH_MODE,` after the compression line.
6. `swingbot/core/backtesting/arms/reachability.py`, after the `COMPRESSION_SHORT_RESEARCH_MODE` entry:

```python
    "TURTLE_SOUP_RESEARCH_MODE": Reach(REACHABLE, (
        "v180: StrategyEngine adds the masked Turtle Soup long inside its scoped "
        "('bullish', '2w') research cell, through the live constructor (structural stop, "
        "level-map target in the R:R band) and the next-open fill. Proven to change outcomes on "
        "the stamped pilot fixture in tests/backtest_scripts/test_measure_arms_turtle_sidecar.py "
        "(not the v74 fixture: a select has no perturbation there)."), S),
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_knob.py
python scripts/dev/testrun.py file tests/backtesting/test_knob_observability.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py
python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py
python scripts/dev/testrun.py changed
```

Expected: all green, 0 failed, 0 xfailed. `changed` selects the config and scan-params tests that reach the diff.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py .env.example swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py tests/backtesting/test_turtle_soup_knob.py
git commit -m "feat(v180): TURTLE_SOUP_RESEARCH_MODE research knob (off | structural), registered and reachable" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase D — the research cell and its diagnostics

### Task V180-7: StrategyEngine research cell, net-of-cost rows, events, subset fixture

**Model:** opus — it edits the shared replay engine that produces every arm row. It must keep every non-Turtle row byte-identical, and it threads costs and per-signal events without touching `iter_trades` (complexity 14).

**Files:**
- Create: `swingbot/core/backtesting/arms/turtle_soup_research.py`
- Create: `tests/backtesting/test_turtle_soup_engine.py`
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (module docstring; imports; `__init__`; `_run_strategies` l.147; `iter_trades_for_strategy`; `_entries` l.186; `_candidate_plan` l.272; `_skipped`; `_count_plan_none`)
- Modify: `swingbot/core/backtesting/backtest.py` (`_refuse_compression` l.85)

**Interfaces:**
- Consumes:
  - From V180-1: `TURTLE_SOUP`, and `ENTRY_FUNCS[TURTLE_SOUP]` masked by `STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}`.
  - From V180-4: `build_strategy_plan` builds a Turtle Soup plan. The stop is `Low[t] − 0.25 × ATR14[t]` via `_bounded_stop`. The target is a level-map resistance inside the 1.5–2.5 R:R band from the signal close, or no plan. The builder builds its own level map from bars ≤ t when `level_map` is None, and the engine passes None because `EXIT_V2_PARAMS[TURTLE_SOUP]["tp2"]` is False. The plan carries `PLAN_SHAPES[TURTLE_SOUP]`.
  - From V180-5: `simulate_exit` fills a Turtle Soup plan at the next open. It cancels with `ExitResult.cancel_reason` `"open_through_stop"` / `"risk_cap"`.
  - From V180-6: `config.TURTLE_SOUP_RESEARCH_MODE`.
  - Existing: `expectancy_attribution.net_r(entry, stop_loss, direction, legs)`, `entry_filters.gate_override`, `acceptance.population_split`, `acceptance.arm_trade_from_plan`.
- Produces (V180-3's `strategy_shift_replay` and V180-8 rely on these):
  - `turtle_soup_research.RESEARCH_KNOB = "TURTLE_SOUP_RESEARCH_MODE"`, `RESEARCH_MODES = ("off", "structural")`, `HORIZON = "2w"`, `RESEARCH_CELL = {"directions": (), "cells": {("bullish", "2w")}}`
  - `CANCEL_STATUS = {"open_through_stop": "cancelled_open_through_stop", "risk_cap": "cancelled_risk_cap_fill"}`
  - `research_mode() -> str`, `net_r(plan, result) -> float`
  - `trade_event(ticker, df, signal_date, plan, result, r_net) -> dict`, `cancel_event(ticker, signal_date, cancel_reason) -> dict`, `plan_none_event(ticker, signal_date) -> dict`.
    - Each event is `{"ticker", "signal_date", "status"}`.
    - `status` is `"trade"`, `"plan_none"`, a `CANCEL_STATUS` value, or `"not_triggered"`.
    - A trade event also carries `"entry_date", "exit_date", "entry_index", "exit_index", "hold_sessions", "outcome", "exit_reason", "r_gross", "r_net", "entry_price", "stop_loss", "tp1"`.
  - `StrategyEngine.turtle_soup_events: list[dict]`: one event per **counted** Turtle Soup candidate that reached the constructor, in signal order. Warm-up candidates and signals swallowed by an open position get no event.
  - Under the knob `structural`:
    - `StrategyEngine().run_ticker(...)` yields every baseline row unchanged, plus Turtle Soup rows booked at net R.
    - `StrategyEngine(strategies=(TURTLE_SOUP,))` yields exactly those Turtle Soup rows.
  - The test module `tests/backtesting/test_turtle_soup_engine.py` doubles as the shared world for V180-8: `path(fill_open=100.0)`, `FULL_PATH`, `SIGNAL_POS = 40`, `SIGNAL_DAY`, `FILL_DAY`, `TARGET = 105.0`, `PILOT = ("2018-06-01", "2020-12-31")`, `pin_world(monkeypatch, resistances=(TARGET,))`.

**Costs (index Open risks).**

- Only Turtle Soup rows are booked net. A Turtle Soup row is booked at 5 bps a side plus `commission_r()`, through `expectancy_attribution.net_r`, which is the screen's cost model.
- Every other row stays gross and byte-identical.
- The outcome label never changes: costs never flip win/loss.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_turtle_soup_engine.py`:

```python
"""V180-7: StrategyEngine runs the masked Turtle Soup long only under TURTLE_SOUP_RESEARCH_MODE,
inside its ("bullish", "2w") research cell. Its rows are booked net of costs, every other row is
untouched, and each counted candidate leaves one event for the diagnostics.

The world (shared with V180-8): 40 flat bars with a 98.0 low ten bars before the signal; the signal
bar sweeps it (low 97.6) and closes back above (99.9); the next bar opens at the fill; three bars later
the high reaches the one resistance the level map holds (105.0)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import population_split
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, STRATEGY_GATES, TURTLE_SOUP
from swingbot.core.planning import turtle_soup_plan
from swingbot.scan_params import ScanParams
from tests.backtesting.screen.helpers import random_walk
from tests.helpers import make_ohlcv

SIGNAL_POS = 40
TARGET = 105.0
PILOT = ("2018-06-01", "2020-12-31")
FLAT = (100.0, 100.5, 99.5, 100.0)
WIDE = ("2009-01-01", "2030-12-31")


def path(fill_open=100.0):
    rows = [FLAT] * SIGNAL_POS
    rows[30] = (100.0, 100.5, 98.0, 100.0)                  # L = 98.0, ten bars before the signal
    rows.append((99.8, 100.2, 97.6, 99.9))                  # the sweep: low < L, close > L
    rows.append((fill_open, max(fill_open, 100.5), min(fill_open, 99.6), 100.2))   # the fill bar
    rows += [(100.2, 101.2, 100.0, 101.0), (101.0, 102.7, 100.8, 102.5),
             (102.5, 105.2, 102.3, 104.8)]                  # the target prints on the fourth session
    rows += [(104.8, 105.0, 104.3, 104.6)] * 25
    return make_ohlcv(rows, start="2019-01-02")


FULL_PATH = path()
SIGNAL_DAY = FULL_PATH.index[SIGNAL_POS].date().isoformat()
FILL_DAY = FULL_PATH.index[SIGNAL_POS + 1].date().isoformat()


def pin_world(monkeypatch, resistances=(TARGET,)):
    """Pin the live-state flags off and the level map to the given resistances."""
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)

    def fake(*args, **kwargs):
        return [], [Level(price=p, sources=["Swing high", "Pivot high"]) for p in resistances]

    monkeypatch.setattr(levels_mod, "build_level_map", fake)
    monkeypatch.setattr(turtle_soup_plan, "build_level_map", fake, raising=False)


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    pin_world(monkeypatch)


@pytest.fixture
def structural(monkeypatch):
    monkeypatch.setattr(config, tsr.RESEARCH_KNOB, "structural")


def _run(engine, frame=FULL_PATH, horizons=("2w",), window=PILOT, ticker="TS1"):
    return list(engine.run_ticker(ticker, frame, horizons, window, ScanParams.from_config()))


def _turtle(rows):
    return [row for row in rows if row.strategy == TURTLE_SOUP]


def test_the_world_fires_exactly_one_signal():
    from swingbot.core.market.turtle_soup import turtle_soup_signal
    assert turtle_soup_signal(FULL_PATH).to_numpy().nonzero()[0].tolist() == [SIGNAL_POS]


def test_research_constants():
    assert tsr.RESEARCH_KNOB == "TURTLE_SOUP_RESEARCH_MODE"
    assert tsr.RESEARCH_MODES == ("off", "structural") and tsr.HORIZON == "2w"
    assert tsr.RESEARCH_CELL == {"directions": (), "cells": {("bullish", "2w")}}
    assert tsr.CANCEL_STATUS == {"open_through_stop": "cancelled_open_through_stop",
                                 "risk_cap": "cancelled_risk_cap_fill"}
    assert tsr.research_mode() == "off"


def test_knob_off_runs_no_turtle_soup():
    engine = StrategyEngine(strategies=("RSI",))
    assert TURTLE_SOUP not in engine._run_strategies()
    assert _turtle(_run(engine)) == [] and engine.turtle_soup_events == []


def test_structural_adds_one_net_of_cost_row(structural):
    engine = StrategyEngine(strategies=("RSI",))
    assert engine._run_strategies() == ("RSI", TURTLE_SOUP)
    (trade,) = _turtle(_run(engine))
    assert (trade.entry_date, trade.horizon_key, trade.direction, trade.outcome) == \
        (SIGNAL_DAY, "2w", "bullish", "win")
    (event,) = engine.turtle_soup_events
    assert event["status"] == "trade" and event["ticker"] == "TS1"
    assert event["signal_date"] == SIGNAL_DAY and event["entry_date"] == FILL_DAY
    assert event["entry_price"] == 100.0 and event["tp1"] == TARGET
    assert event["exit_reason"] == "tp1" and event["hold_sessions"] == 4
    expected_stop = 97.6 - 0.25 * float(atr(FULL_PATH.iloc[:SIGNAL_POS + 1], 14).iloc[-1])
    assert event["stop_loss"] == pytest.approx(expected_stop)
    legs = [{"fraction": 1.0, "exit_price": TARGET}]
    assert event["r_net"] == pytest.approx(ea.net_r(100.0, event["stop_loss"], "bullish", legs))
    assert event["r_net"] < event["r_gross"]
    assert trade.r_multiple == event["r_net"]


def test_the_cell_opens_only_bullish_2w_and_is_restored(structural):
    engine = StrategyEngine(strategies=("RSI",))
    assert _turtle(_run(engine, horizons=("4w",))) == []
    _run(engine)
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}


def test_an_open_through_the_stop_is_a_cancel_event_not_a_row(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, frame=path(fill_open=97.0)) == []
    assert engine.turtle_soup_events == [
        {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "cancelled_open_through_stop"}]


def test_a_stop_beyond_the_cap_at_the_fill_is_a_cancel_event(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, frame=path(fill_open=100.8)) == []      # stop ~97.31: 3.46% from 100.8
    assert [e["status"] for e in engine.turtle_soup_events] == ["cancelled_risk_cap_fill"]


@pytest.mark.parametrize("resistances", [(), (110.0,)])
def test_no_level_in_the_band_is_a_plan_none_event(structural, monkeypatch, resistances):
    pin_world(monkeypatch, resistances)
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine) == []
    assert engine.turtle_soup_events == [
        {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "plan_none"}]


def test_warm_up_signals_leave_no_event(structural):
    engine = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert _run(engine, window=("2019-03-15", "2020-12-31")) == []
    assert engine.turtle_soup_events == []


def test_a_turtle_soup_only_engine_yields_the_same_rows(structural):
    full = _turtle(_run(StrategyEngine(strategies=("RSI", "MACD"))))
    alone = StrategyEngine(strategies=(TURTLE_SOUP,))
    assert alone._run_strategies() == (TURTLE_SOUP,)
    assert _run(alone) == full and len(full) == 1


def test_baseline_rows_are_a_subset_of_the_component(monkeypatch):
    frames = {"TS1": FULL_PATH, "RW1": random_walk(400, seed=3), "RW2": random_walk(400, seed=11)}
    strategies = ("RSI", "MACD", "Support/Resistance")
    horizons = ("2w", "4w")

    def arm(mode):
        monkeypatch.setattr(config, tsr.RESEARCH_KNOB, mode)
        engine = StrategyEngine(strategies=strategies)
        return [row for ticker, frame in frames.items()
                for row in _run(engine, frame=frame, horizons=horizons, window=WIDE, ticker=ticker)]

    baseline, component = arm("off"), arm("structural")
    split = population_split(baseline, component)
    assert split["removed"] == [] and split["changed"] == []
    assert split["added"] and all(row.strategy == TURTLE_SOUP for row in split["added"])
    assert [row for row in component if row.strategy != TURTLE_SOUP] == baseline


def test_net_r_is_the_screen_cost_model(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    plan = SimpleNamespace(stop_loss=98.0, direction="bullish")
    result = SimpleNamespace(entry_price=100.0, legs=[{"fraction": 1.0, "exit_price": 104.0}])
    # entry 100.05, exit 103.948, risk 2.05: 3.898 / 2.05 - 2 * 1 / 100
    assert tsr.net_r(plan, result) == pytest.approx(1.8814634, abs=1e-6)


def test_cancel_and_plan_none_events():
    assert tsr.cancel_event("T", "2019-01-02", "risk_cap") == \
        {"ticker": "T", "signal_date": "2019-01-02", "status": "cancelled_risk_cap_fill"}
    assert tsr.cancel_event("T", "2019-01-02", None)["status"] == "not_triggered"
    assert tsr.plan_none_event("T", "2019-01-02") == \
        {"ticker": "T", "signal_date": "2019-01-02", "status": "plan_none"}


def test_the_signal_close_backtest_refuses_turtle_soup():
    with pytest.raises(ValueError, match="Turtle Soup"):
        bt._refuse_compression(TURTLE_SOUP)
    with pytest.raises(ValueError, match="CompressionResearchContext"):
        bt._refuse_compression(COMPRESSION_SHORT)
    assert bt._refuse_compression("RSI") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_engine.py`
Expected: FAIL at collection with `ImportError: cannot import name 'turtle_soup_research'`.

- [ ] **Step 3: Create `swingbot/core/backtesting/arms/turtle_soup_research.py`**

Module docstring: v180's Turtle Soup research cell for `StrategyEngine`. It covers four things:

- the knob;
- the one open cell, which is fixed and never the horizon being replayed;
- the cost model for the cell's rows, which is the screen's: 5 bps a side plus `commission_r()`;
- the per-signal events the diagnostics read.

Nothing here is read by the live bot.

```python
from swingbot import config
from swingbot.core.planning.next_open_entry import OPEN_THROUGH_STOP, RISK_CAP

RESEARCH_KNOB = "TURTLE_SOUP_RESEARCH_MODE"
RESEARCH_MODES = ("off", "structural")
HORIZON = "2w"
#: The live mask ({"directions": ()}) plus ("bullish", "2w") only.
RESEARCH_CELL = {"directions": (), "cells": {("bullish", HORIZON)}}
CANCEL_STATUS = {OPEN_THROUGH_STOP: "cancelled_open_through_stop", RISK_CAP: "cancelled_risk_cap_fill"}
```

Functions (signatures from Interfaces):

- `research_mode()`: `getattr(config, RESEARCH_KNOB, "off")`.
- `net_r(plan, result)`: `expectancy_attribution.net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs)`. Import `expectancy_attribution` inside the function, which keeps analytics out of this module's import time. Do not round.
- `trade_event(ticker, df, signal_date, plan, result, r_net)` returns:
  - the three base keys, with `status` `"trade"`;
  - `entry_date` / `exit_date`: `str(df.index[i].date())`;
  - `entry_index`, `exit_index`;
  - `hold_sessions`: `exit_index - entry_index + 1`;
  - `outcome`: `result.outcome`;
  - `exit_reason`: the last leg's `reason`, else `result.outcome`;
  - `r_gross`: `result.r_total`;
  - `r_net`;
  - `entry_price`: `result.entry_price`;
  - `stop_loss` and `tp1`: from the plan.
- `cancel_event`: `status = CANCEL_STATUS.get(cancel_reason, "not_triggered")`.
- `plan_none_event`: `status = "plan_none"`.

- [ ] **Step 4: Wire `strategy_engine.py`**

1. Imports:
   - `from swingbot.core.backtesting.arms import turtle_soup_research as tsr`.
   - Add `TURTLE_SOUP` to the `strategy_types` import.
   - After `RESEARCH_KNOB`, add the dispatch table:

   ```python
   #: Masked strategies the engine reads under their own fixed research cell (scoped gate_override).
   _RESEARCH_CELLS = {COMPRESSION_SHORT: RESEARCH_CELL, TURTLE_SOUP: tsr.RESEARCH_CELL}
   ```

2. Add one paragraph to the module docstring. It says that v180's Turtle Soup long joins under `TURTLE_SOUP_RESEARCH_MODE=structural`, inside its own ("bullish", "2w") cell, and that its rows are booked net of the screen's costs (`turtle_soup_research.net_r`) while every other row stays gross. It also says that `turtle_soup_events` lists one event per counted candidate.
3. `__init__`: add `self.turtle_soup_events: list[dict] = []` beside the compression diagnostics.
4. `_run_strategies`. Rename the current body, unchanged, to `_compression_strategies(self) -> tuple`, then:

```python
    def _run_strategies(self) -> tuple:
        """This run's strategies: the compression short and the v180 Turtle Soup long each join
        (once) when their research knob is on."""
        strategies = self._compression_strategies()
        if tsr.research_mode() == "off" or TURTLE_SOUP in strategies:
            return strategies
        return strategies + (TURTLE_SOUP,)
```

5. `_entries`, table-driven. The compression behaviour stays identical, including the context error:

```python
    def _entries(self, df, strategy, horizon_key):
        """Entry series; a masked research strategy is read under its own scoped research cell."""
        cell = _RESEARCH_CELLS.get(strategy)
        if cell is None:
            return bt._vectorized_entries(df, strategy, horizon_key)
        if strategy == COMPRESSION_SHORT and self.compression_context is None:
            raise CompressionContextError(...)      # the existing message, verbatim
        with entry_filters.gate_override(strategy, cell):
            return bt._vectorized_entries(df, strategy, horizon_key)
```

6. `iter_trades_for_strategy`: pass `r_multiple=self._booked_r(ticker, df, date, plan, result)` instead of `result.r_total`, with:

```python
    def _booked_r(self, ticker, df, date, plan, result) -> float:
        """Gross R for every strategy but Turtle Soup, whose row is booked net and logged (v180)."""
        if plan.strategy != TURTLE_SOUP:
            return result.r_total
        r_net = tsr.net_r(plan, result)
        self.turtle_soup_events.append(tsr.trade_event(ticker, df, date, plan, result, r_net))
        return r_net
```

7. `_candidate_plan`: move `self._candidate = (ticker, str(window.index[-1].date()))` above `if strategy == COMPRESSION_SHORT:`, so it is set for every candidate. `_count` reads it only for the compression short, which sets it at the same point as before.
8. `_skipped`: keep its first return; route the counted note through a helper:

```python
    def _skipped(self, result, strategy, stamp, counted=True) -> bool:
        """Whether the walk produced no scored trade; a research row says why (expiry, gap-risk...)."""
        if result.outcome not in SKIPPED:
            return False
        if counted:
            self._note_skip(strategy, stamp, result)
        return True

    def _note_skip(self, strategy, stamp, result) -> None:
        if strategy == COMPRESSION_SHORT:
            self._count(stamp, _CANCEL_REASONS.get(result.cancel_reason, "not_triggered"))
        elif strategy == TURTLE_SOUP:
            self.turtle_soup_events.append(tsr.cancel_event(*self._candidate, result.cancel_reason))
```

9. `_count_plan_none`: first line `if strategy == TURTLE_SOUP: self.turtle_soup_events.append(tsr.plan_none_event(*self._candidate)); return` (written as a two-line `if` block). The compression path is unchanged.

`iter_trades` is not edited.

- [ ] **Step 5: Wire `backtest._refuse_compression`**

Keep the name and the compression message byte-identical; table-drive it:

```python
def _signal_close_refusals() -> dict:
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT, TURTLE_SOUP
    return {
        COMPRESSION_SHORT: (f"{COMPRESSION_SHORT} is not backtestable here (signal-close entry, no hold "
                            "cap); use StrategyEngine with a CompressionResearchContext"),
        TURTLE_SOUP: (f"{TURTLE_SOUP} is not backtestable here (signal-close entry; it fills at the "
                      "next open with a ten-session hold cap); use StrategyEngine with "
                      "TURTLE_SOUP_RESEARCH_MODE=structural"),
    }


def _refuse_compression(strategy: str) -> None:
    """v119/v180: masked research strategies whose fill or hold cap this signal-close path does not
    model. Their research arm is arms/strategy_engine.py."""
    message = _signal_close_refusals().get(strategy)
    if message is not None:
        raise ValueError(message)
```

- [ ] **Step 6: Run the tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_engine.py
python scripts/dev/testrun.py file tests/backtesting/test_compression_reachability.py
python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_strategy_engine_gate_rows.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_record_blocked.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_constructor_parity.py
python scripts/dev/complexity_gate.py
```

Expected:

- All green, 0 failed, 0 xfailed.
- The compression files pass unmodified.
- The complexity gate shows `iter_trades` still at 14 and no new function at or above 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/arms/turtle_soup_research.py swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest.py tests/backtesting/test_turtle_soup_engine.py
git commit -m "feat(v180): Turtle Soup research cell in StrategyEngine -- net-of-cost rows, per-signal events, baseline subset proven" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

