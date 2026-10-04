# v131 Fibonacci Limit — Part 2: plan-shape field and registration

Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-04-v131-fib-zone-limit-entry_0-index.md`. Spec: `docs/superpowers/specs/2026-10-04-v131-fib-zone-limit-entry-design.md`.

Same worktree and branch as Part 1 (`<worktree>` = the absolute path of `.claude/worktrees/2026-10-04-v131-fib-zone-limit-entry`); `python scripts/dev/testrun.py ...` means `python <worktree>/scripts/dev/testrun.py ...`. Line numbers are `main`'s; after Part 1 they hold for `builders.py`, `backtest.py`, `params.py` and `strategy_types.py` (Part 1 did not touch them) — `entry_filters.py` is shifted by V131-02, so its anchors below are quoted text.

# Phase 2 — Shape field and registration (sequential)

### Task V131-04: `PLAN_SHAPES` `limit_price` — a pricer registry honoured by both plan constructors

**Files:**
- Modify: `swingbot/core/planning/builders.py` (imports `:4-6`; new block before `_geometry_ok` at `:258`; `build_strategy_plan` `:291` and `:349`; `plan_shape_for` docstring `:519-521`)
- Modify: `swingbot/core/planning/params.py:55-58` (comment above `PLAN_SHAPES`)
- Modify: `swingbot/core/backtesting/backtest.py` (`BacktestSummary` `:129`; new `_limit_plan_at` before `_trade_plan_at` `:188`; `_trade_plan_at` `:197`; `_bt_plan` `:267-290` plus new `_record_limit_order` after it; `run_backtest` `:350`, `:399`, `:548`)
- Create: `tests/planning/test_limit_price_shape.py`

**Interfaces:**
- Consumes: V131-03's `TradePlanV2.limit_cancel_level` / `limit_strict_fill` and `ExitResult.cancel_reason` values `"expired"`/`"cancelled"`; existing `builders._BranchInputs`, `_STRUCTURAL_BRANCHES`, `_atr_branch`, `strategy_entry_reference(df, index, strategy)`, `plan_shape_for(strategy)`; `backtest._floored(entry, stop, target, strategy, horizon_key)`; `plan_engine._safe_atr_value`, `apply_level_lifecycle`.
- Produces (V131-05 and V131-06 rely on these exact names):
  - `builders.LimitPricer(price: Callable, cancel_level: Callable, strict_fill: bool = True)` — frozen dataclass; both callables are `(df, index, horizon_key, direction) -> float | None`.
  - `builders.LIMIT_PRICERS: dict[str, LimitPricer]` (empty here; V131-05 registers `"fib_zone"`).
  - `builders.limit_pricer_for(strategy) -> LimitPricer | None` (raises `KeyError` for an unregistered name).
  - `builders.plan_entry_reference(df, index, strategy, horizon_key, direction) -> float | None`.
  - `builders.limit_order_fields(df, index, strategy, horizon_key, direction) -> dict` (`{}` or `{"limit_cancel_level", "limit_strict_fill"}`).
  - `builders.size_strategy_plan(df, index, strategy, horizon_key, direction, entry, atr_val) -> (stop, tp1, candidates) | None`.
  - `backtest._limit_plan_at(df, i, direction, strategy, horizon_key, atr_series) -> (entry, stop, target) | None`.
  - `backtest._record_limit_order(book, df, i, plan, res) -> None`; `BacktestSummary.limit_orders: list[dict]`, each `{"signal_date", "limit_price", "cancel_level", "status": "filled"|"expired"|"cancelled", "fill_date", "fill_price", "same_bar_new_high"}`.

- [ ] **Step 1: Write the failing tests.** Create `tests/planning/test_limit_price_shape.py`:

```python
"""v131: PLAN_SHAPES' optional "limit_price" key, honoured by both plan constructors."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.market import entry_filters as ef
from swingbot.core.planning import builders, params
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv

PROBE = "Probe Limit"
HZ = "4w"


def _probe_price(df, index, horizon_key, direction):
    """2% under the bar's close, or no order on an odd bar."""
    return None if index % 2 else float(df["Close"].iloc[index]) * 0.98


def _probe_cancel(df, index, horizon_key, direction):
    return float(df["High"].iloc[index]) * 1.05


SEEN = []


def _probe_branch(inputs):
    """Stop 1% and target 3% from whatever entry the constructor hands in."""
    SEEN.append(inputs.close)
    return inputs.close * 0.99, inputs.close * 1.03, [inputs.close * 1.03], None


@pytest.fixture
def probe(monkeypatch):
    SEEN.clear()
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    monkeypatch.setitem(params.PLAN_SHAPES, PROBE, {
        "entry_type": "limit", "expiry_bars": 3, "tp1_fraction": 0.5,
        "breakeven_trigger_fraction": 0.5, "limit_price": "probe"})
    monkeypatch.setitem(builders.LIMIT_PRICERS, "probe",
                        builders.LimitPricer(price=_probe_price, cancel_level=_probe_cancel))
    monkeypatch.setitem(builders._STRUCTURAL_BRANCHES, PROBE, _probe_branch)
    return PROBE


def _frame(n=80):
    return make_ohlcv([100.0 + 0.1 * k for k in range(n)], start="2020-01-02")


def test_build_strategy_plan_enters_at_the_limit_and_prices_from_it(probe):
    df = _frame()
    plan = builders.build_strategy_plan(df, 60, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish")
    limit = float(df["Close"].iloc[60]) * 0.98
    assert SEEN == [pytest.approx(limit)]
    assert (plan.entry_type, plan.entry_price, plan.status) == ("limit", None, PlanStatus.PENDING)
    assert plan.trigger_price == pytest.approx(limit)
    assert plan.stop_loss == pytest.approx(limit * 0.99) and plan.tp1 == pytest.approx(limit * 1.03)
    assert plan.expiry_bars == 3
    assert plan.limit_cancel_level == pytest.approx(float(df["High"].iloc[60]) * 1.05)
    assert plan.limit_strict_fill is True


def test_no_limit_price_means_no_plan_in_either_constructor(probe):
    df = _frame()
    assert builders.build_strategy_plan(df, 61, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish") is None
    assert backtest._trade_plan_at(df, 61, "bullish", probe, HZ, backtest.atr(df, 14)) is None


def test_the_backtest_constructor_prices_the_same_plan(probe):
    df = _frame()
    live = builders.build_strategy_plan(df, 60, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish")
    entry, stop, target = backtest._trade_plan_at(df, 60, "bullish", probe, HZ, backtest.atr(df, 14))
    assert (entry, stop, target) == pytest.approx((live.trigger_price, live.stop_loss, live.tp1))
    plan = backtest._bt_plan(df, 60, ticker="T", strategy=probe, horizon_key=HZ,
                             direction="bullish", entry=entry, stop_loss=stop,
                             take_profit=target, tp2=None, trail_atr_mult=3.0)
    assert (plan.entry_type, plan.trigger_price, plan.expiry_bars) == ("limit", entry, 3)
    assert plan.limit_cancel_level == pytest.approx(live.limit_cancel_level)
    assert plan.limit_strict_fill is True


def test_run_backtest_records_every_placed_order_and_scores_from_the_fill(probe, monkeypatch):
    bars = [(100.0, 100.5, 99.5, 100.0)] * 60
    bars += [(100.0, 100.5, 99.5, 100.0)]          # bar 60: signal, limit 98.0, stop 97.02
    bars += [(99.0, 99.2, 97.9, 98.5)]             # bar 61: trades through 98.0 -> fill
    bars += [(98.5, 101.0, 98.4, 100.9)] * 3       # target 100.94 reached on bar 62
    bars += [(100.0, 100.5, 99.5, 100.0)] * 15
    df = make_ohlcv(bars, start="2020-01-02")
    fired = pd.Series(False, index=df.index)
    fired.iloc[60] = True
    monkeypatch.setitem(ef.ENTRY_FUNCS, probe, lambda d, hk, p=None: (fired.copy(), fired & False))
    summary = backtest.run_backtest("T", df, probe, HZ, exit_model="v2", scale_out=False)
    [trade] = summary.trades
    assert trade.entry == pytest.approx(98.0) and trade.outcome == "win"
    assert trade.r_multiple == pytest.approx((98.0 * 1.03 - 98.0) / (98.0 - 98.0 * 0.99), abs=1e-3)
    [order] = summary.limit_orders
    assert order["status"] == "filled" and order["fill_price"] == pytest.approx(98.0)
    assert order["signal_date"] == str(df.index[60].date())
    assert order["fill_date"] == str(df.index[61].date())
    assert order["same_bar_new_high"] is False


def test_an_unfilled_order_is_recorded_and_produces_no_trade(probe, monkeypatch):
    df = make_ohlcv([(100.0, 100.5, 99.5, 100.0)] * 80, start="2020-01-02")
    fired = pd.Series(False, index=df.index)
    fired.iloc[60] = True
    monkeypatch.setitem(ef.ENTRY_FUNCS, probe, lambda d, hk, p=None: (fired.copy(), fired & False))
    summary = backtest.run_backtest("T", df, probe, HZ, exit_model="v2", scale_out=True)
    assert summary.trades == []
    assert [order["status"] for order in summary.limit_orders] == ["expired"]


def test_an_unregistered_pricer_name_fails_loudly(monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, PROBE, {"entry_type": "limit", "limit_price": "nope"})
    with pytest.raises(KeyError):
        builders.limit_pricer_for(PROBE)


def test_a_strategy_without_the_key_keeps_its_entry_reference_and_defaults():
    df = _frame()
    assert builders.limit_pricer_for("RSI") is None
    assert builders.plan_entry_reference(df, 60, "RSI", HZ, "bullish") == float(df["Close"].iloc[60])
    assert builders.limit_order_fields(df, 60, "RSI", HZ, "bullish") == {}


def test_the_v113_fade_limit_keeps_its_touch_fill_and_records_no_orders():
    from swingbot.core.market.strategy_types import FADE_STRATEGY
    from tests.market.test_fib_sr_confluence import _trending_frame
    df = _trending_frame(400, -0.06, seed=11)
    plan = backtest._bt_plan(df, 300, ticker="T", strategy=FADE_STRATEGY, horizon_key="1w",
                             direction="bearish", entry=100.0, stop_loss=102.0,
                             take_profit=98.0, tp2=None, trail_atr_mult=2.5)
    assert (plan.entry_type, plan.limit_cancel_level, plan.limit_strict_fill) == ("limit", None, False)
    with ef.gate_override(FADE_STRATEGY, {"cells": frozenset({("bearish", "1w")})}):
        summary = backtest.run_backtest("T", df, FADE_STRATEGY, "1w", exit_model="v2", scale_out=True)
    assert summary.limit_orders == []
```

- [ ] **Step 2: Run to verify it fails.** `python scripts/dev/testrun.py file tests/planning/test_limit_price_shape.py`. Expected: FAIL — `AttributeError: module 'swingbot.core.planning.builders' has no attribute 'LIMIT_PRICERS'`.

- [ ] **Step 3: builders.py.**

(a) Imports — replace lines 4-6:

```python
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
```

(b) Directly above `def _geometry_ok(close, stop, tp1, strategy, horizon_key) -> bool:` (line 258), insert:

```python
# --- v131: resting-limit pricing (PLAN_SHAPES' optional "limit_price") ------
#
# A strategy whose PLAN_SHAPES entry names a registered pricer is traded as a
# resting limit order priced at its alert bar: entry is the pricer's price, and
# stop and targets are sized from it by the strategy's own branch. A strategy
# without the key resolves to None everywhere below and builds exactly the
# plan it always built (tests/backtesting/test_v131_witness.py).


@dataclass(frozen=True)
class LimitPricer:
    """`price` and `cancel_level` are (df, index, horizon_key, direction) ->
    float | None, frozen at bar `index` from bars <= index only. A None price
    means no order. `strict_fill`: the limit fills only on a strict
    trade-through, never on an exact touch."""
    price: Callable
    cancel_level: Callable
    strict_fill: bool = True


LIMIT_PRICERS: dict[str, LimitPricer] = {}


def limit_pricer_for(strategy: str) -> LimitPricer | None:
    """The strategy's registered pricer, or None when its shape names none. A
    name with no registered pricer is a configuration error and raises."""
    name = plan_shape_for(strategy).get("limit_price")
    return None if name is None else LIMIT_PRICERS[name]


def plan_entry_reference(df, index, strategy, horizon_key, direction) -> float | None:
    """The price a strategy plan is sized and triggered from: the registered
    limit price for a resting-limit strategy (None = no order at this bar),
    otherwise strategy_entry_reference, unchanged."""
    pricer = limit_pricer_for(strategy)
    if pricer is None:
        return strategy_entry_reference(df, index, strategy)
    price = pricer.price(df, index, horizon_key, direction)
    return None if price is None else float(price)


def limit_order_fields(df, index, strategy, horizon_key, direction) -> dict:
    """TradePlanV2 keyword overrides for a resting-limit strategy: the frozen
    cancel level and the strict-fill flag. Empty for every other strategy,
    so the plan keeps its dataclass defaults."""
    pricer = limit_pricer_for(strategy)
    if pricer is None:
        return {}
    level = pricer.cancel_level(df, index, horizon_key, direction)
    return {"limit_cancel_level": None if level is None else float(level),
            "limit_strict_fill": pricer.strict_fill}


def size_strategy_plan(df, index, strategy, horizon_key, direction, entry, atr_val):
    """(stop, tp1, candidates) from the strategy's own sizing branch, priced
    from `entry`, or None. backtest._limit_plan_at sizes resting-limit plans
    through this, the same branch build_strategy_plan dispatches to."""
    branch = _STRUCTURAL_BRANCHES.get(strategy, _atr_branch)
    picked = branch(_BranchInputs(df, index, strategy, horizon_key, direction, entry,
                                  atr_val, None, None))
    return None if picked is None else picked[:3]


```

(c) In `build_strategy_plan`, replace line 291 (`    close = strategy_entry_reference(df, index, strategy)`) with:

```python
    close = plan_entry_reference(df, index, strategy, horizon_key, direction)
    if close is None:
        return None                     # v131: a resting-limit strategy with no order here
```

(d) In the same function's `TradePlanV2(...)` call, after `        hold_cap_bars=shape.get("hold_cap_bars"),` (line 349) add:

```python
        **limit_order_fields(df, index, strategy, horizon_key, direction),
```

(e) Replace `plan_shape_for`'s docstring (lines 519-521) with:

```python
    """Entry type, entry-order life, TP1 fraction and break-even trigger for a
    strategy-source plan, plus the optional v131 "limit_price" pricer name.
    build_strategy_plan and backtest._bt_plan both read this, so the two
    cannot diverge. Unlisted strategies get today's shape."""
```

- [ ] **Step 4: params.py.** Replace the two comment lines directly above `PLAN_SHAPES: dict[str, dict] = {` (line 58) — `# today's shape (builders.plan_shape_for). Read by the live builder and the` / `# backtest alike.` — with:

```python
# today's shape (builders.plan_shape_for). Read by the live builder and the
# backtest alike.
# v131: an optional "limit_price" key names a builders.LIMIT_PRICERS entry. With
# it, entry is the pricer's frozen limit price and stop and targets are sized
# from that price (builders.plan_entry_reference, backtest._limit_plan_at);
# without it, nothing about the plan changes.
```

- [ ] **Step 5: backtest.py.**

(a) `BacktestSummary` — after `    avg_win_r: float | None = None` (line 129) add:

```python
    # v131: one record per placed cancellable limit order (_record_limit_order);
    # empty for every strategy without a PLAN_SHAPES "limit_price".
    limit_orders: list = field(default_factory=list)
```

(b) Directly above `def _trade_plan_at(` (line 188) insert:

```python
def _limit_plan_at(df, i, direction, strategy, horizon_key, atr_series):
    """v131: (entry, stop, target) for a resting-limit strategy, priced entirely
    from its frozen limit price at bar i through the same builders helpers
    build_strategy_plan uses; None when there is no order or no qualifying
    target."""
    from swingbot.core.planning.builders import plan_entry_reference, size_strategy_plan
    from swingbot.core.planning.plan_engine import _safe_atr_value, apply_level_lifecycle

    entry = plan_entry_reference(df, i, strategy, horizon_key, direction)
    if entry is None:
        return None
    atr_val = _safe_atr_value(entry, float(atr_series.iloc[i]))
    picked = size_strategy_plan(df, i, strategy, horizon_key, direction, entry, atr_val)
    if picked is None:
        return None
    stop_loss, take_profit, candidates = picked
    stop_loss, take_profit, _ = apply_level_lifecycle(
        df, i, entry=entry, stop=stop_loss, tp1=take_profit, atr_val=atr_val,
        direction=direction, strategy=strategy, horizon_key=horizon_key,
        candidate_levels=candidates)
    return _floored(entry, stop_loss, take_profit, strategy, horizon_key)


```

(c) In `_trade_plan_at`, replace line 197 (`    _refuse_compression(strategy)`) with:

```python
    _refuse_compression(strategy)
    from swingbot.core.planning.builders import limit_pricer_for
    if limit_pricer_for(strategy) is not None:
        return _limit_plan_at(df, i, direction, strategy, horizon_key, atr_series)
```

(d) In `_bt_plan`, replace `    from swingbot.core.planning.builders import plan_shape_for` with `    from swingbot.core.planning.builders import limit_order_fields, plan_shape_for`, and replace the end of its `TradePlanV2(...)` call

```python
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
    )
```

with

```python
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
        **limit_order_fields(df, i, strategy, horizon_key, direction),
    )


def _record_limit_order(book: list, df, i, plan, res) -> None:
    """v131: one record per placed cancellable limit order -- filled, expired
    or cancelled -- with the fill bar's date and price and whether that bar
    also traded beyond the cancel level. Plans without a cancel level record
    nothing, so every other strategy's summary keeps an empty list."""
    if plan.limit_cancel_level is None:
        return
    record = {"signal_date": str(df.index[i].date()), "limit_price": plan.trigger_price,
              "cancel_level": plan.limit_cancel_level, "status": res.cancel_reason or "filled",
              "fill_date": None, "fill_price": None, "same_bar_new_high": None}
    if res.entry_index is not None:
        j = res.entry_index
        record.update(fill_date=str(df.index[j].date()), fill_price=res.entry_price,
                      same_bar_new_high=bool(float(df["High"].values[j]) > plan.limit_cancel_level))
    book.append(record)
```

(e) In `run_backtest` — **no new branch** (it is CC 58 and may not grow):
- after `    trades: list[BacktestTrade] = []` (line 350) add `    limit_orders: list[dict] = []`;
- after `            res = simulate_exit(df, i, plan, scale_out=scale_out)` (line 399) add `            _record_limit_order(limit_orders, df, i, plan, res)`;
- in the final `BacktestSummary(...)`, after `        avg_win_r=float(np.mean([t.r_multiple for t in wins])) if wins else None,` (line 548) add `        limit_orders=limit_orders,`.

- [ ] **Step 6: Run to verify it passes.**

```bash
python scripts/dev/testrun.py file tests/planning/test_limit_price_shape.py
python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py
python scripts/dev/testrun.py file tests/planning/test_limit_entry.py
```

Expected: 8 passed; witness 2 passed (byte-identity holds); the engine and v113 limit files unchanged and green.

- [ ] **Step 7: Complexity.** `python -m radon cc -s swingbot/core/backtesting/backtest.py swingbot/core/planning/builders.py | grep -E "run_backtest |_trade_plan_at|build_strategy_plan|_limit_plan_at|_record_limit|limit_|plan_entry|size_strategy"`. Required: `run_backtest - F (58)` (unchanged), `_trade_plan_at - C (14)`, `build_strategy_plan - C (14)`, every new function ≤ 4.

- [ ] **Step 8: Commit**

```bash
git -C <worktree> add swingbot/core/planning/builders.py swingbot/core/planning/params.py swingbot/core/backtesting/backtest.py tests/planning/test_limit_price_shape.py
git -C <worktree> commit -m "feat(v131): PLAN_SHAPES limit_price -- registered limit pricers honoured by build_strategy_plan and the backtest, order records on the summary

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V131-05: Register the masked `Fibonacci Limit` strategy

**Files:**
- Modify: `swingbot/core/market/strategy_types.py:22` (constant after `FADE_STRATEGY`), `:269` (gate after the compression short's)
- Modify: `swingbot/core/market/entry_filters.py` (import at `:23-26`; entry function after V131-02's `fib_limit_cancel_at`)
- Modify: `swingbot/core/planning/params.py` (import `:7`; `EXIT_V2_PARAMS` `:49`; `PLAN_SHAPES` after the compression short's entry)
- Modify: `swingbot/core/planning/builders.py` (import `:12-13`; `_fib_limit_plan` and `_fib_limit_branch` before `_atr_branch`; `_STRUCTURAL_BRANCHES` `:255`; `LIMIT_PRICERS` from V131-04)
- Modify: `tests/planning/test_strategy_branch_table.py:8`
- Create: `tests/planning/test_fib_limit_registration.py`

**Interfaces:**
- Consumes: V131-02's `fibonacci_limit_setups`, `fib_limit_anchors`, `fib_limit_price_at`, `fib_limit_cancel_at`, `DEFAULT_PARAMS["Fibonacci Limit"]`; V131-04's `LimitPricer`, `LIMIT_PRICERS`, `limit_pricer_for`; existing `_bounded_stop`, `select_structural_target`, `fib_target_candidates`, `_branch_result`, `STRUCTURE_BUFFER_ATR`, `TP1_FRACTION`, `strategy_types.BREAKEVEN_TRIGGER_FRACTION`, `admits`, `_off`.
- Produces: `strategy_types.FIB_LIMIT = "Fibonacci Limit"`; `STRATEGY_GATES[FIB_LIMIT] = {"directions": ()}`; `entry_filters.fibonacci_limit_entries(df, horizon_key, params=None)` registered as `ENTRY_FUNCS[FIB_LIMIT]`; `params.EXIT_V2_PARAMS[FIB_LIMIT]`, `params.PLAN_SHAPES[FIB_LIMIT]` (with `"limit_price": "fib_zone"`); `builders._fib_limit_plan(entry, atr_val, swing_low, direction, horizon_key, candidate_levels, params=None)`, `builders._fib_limit_branch(inputs)`, `builders.LIMIT_PRICERS["fib_zone"]`.

- [ ] **Step 1: Load the `edge-module` skill** (a new strategy entry in `strategy_types.py`) and follow its registry checklist alongside the steps below; the strategy stays masked and gets no registry row in this task.

- [ ] **Step 2: Write the failing tests.** Create `tests/planning/test_fib_limit_registration.py`:

```python
"""v131: the masked `Fibonacci Limit` strategy -- entries, plan shape and sizing."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import FIB_LIMIT, STRATEGY_GATES
from swingbot.core.planning import builders, params
from swingbot.core.planning.stop_scope import stop_ceiling
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "2w"
UNMASKED = {"directions": ("bullish",)}


def _frame():
    return _trending_frame(400, 0.06, seed=2)


def _arm_bars(df, horizon=HZ):
    return [int(t) for t in np.nonzero(ef.fibonacci_limit_setups(df, horizon)["arm"].to_numpy())[0]]


def test_ships_masked_and_out_of_the_backtest_strategy_list():
    assert STRATEGY_GATES[FIB_LIMIT] == {"directions": ()}
    assert FIB_LIMIT not in backtest.ALL_STRATEGIES
    bullish, bearish = ef.entries_for(FIB_LIMIT, _frame(), HZ)
    assert not bullish.any() and not bearish.any()


def test_the_masked_entry_function_skips_the_order_book(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("masked strategy walked the order book")
    monkeypatch.setattr(ef, "fibonacci_limit_setups", boom)
    bullish, _ = ef.ENTRY_FUNCS[FIB_LIMIT](_frame(), HZ)
    assert not bullish.any()


def test_unmasked_entries_are_the_arming_bars_bullish_only():
    df = _frame()
    with ef.gate_override(FIB_LIMIT, UNMASKED):
        bullish, bearish = ef.entries_for(FIB_LIMIT, df, HZ)
    assert [int(t) for t in np.nonzero(bullish.to_numpy())[0]] == _arm_bars(df)
    assert bullish.any() and not bearish.any()


def test_plan_shape_and_exits_are_fibonacci_s_on_a_resting_limit():
    shape = builders.plan_shape_for(FIB_LIMIT)
    assert shape == {"entry_type": "limit", "expiry_bars": 5, "tp1_fraction": 0.5,
                     "breakeven_trigger_fraction": 0.5, "limit_price": "fib_zone"}
    assert shape["expiry_bars"] == ef.DEFAULT_PARAMS[FIB_LIMIT]["N"]
    assert params.exit_params_for(FIB_LIMIT) == params.exit_params_for("Fibonacci") == {
        "trail_atr_mult": 3.0, "tp2": False}
    assert builders.limit_pricer_for(FIB_LIMIT) is builders.LIMIT_PRICERS["fib_zone"]


def test_the_plan_is_priced_entirely_from_the_limit(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    df = _frame()
    setups = ef.fibonacci_limit_setups(df, HZ)
    built = 0
    for t in _arm_bars(df):
        plan = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        if plan is None:
            continue
        built += 1
        limit = float(setups["limit_price"].iloc[t])
        atr_val = builders._safe_atr_value(limit, float(atr(df, 14).iloc[t]))
        raw_stop = float(setups["swing_low"].iloc[t]) - params.STRUCTURE_BUFFER_ATR * atr_val
        ceiling = stop_ceiling(FIB_LIMIT, "bullish", HZ)[0]
        assert plan.trigger_price == pytest.approx(limit) and plan.entry_price is None
        assert plan.stop_loss == pytest.approx(max(raw_stop, limit * (1 - ceiling / 100)))
        risk = limit - plan.stop_loss
        assert 1.5 - 1e-9 <= (plan.tp1 - limit) / risk <= 2.5 + 1e-9
        assert plan.limit_cancel_level == float(setups["swing_high"].iloc[t])
        assert plan.limit_strict_fill is True and plan.expiry_bars == 5
    assert built >= 1, "fixture must build at least one plan"


def test_no_bearish_plan():
    df = _frame()
    t = _arm_bars(df)[0]
    assert builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                        horizon_key=HZ, direction="bearish") is None


def test_backtest_and_live_constructors_agree():
    df = _frame()
    atr_series = backtest.atr(df, 14)
    for t in _arm_bars(df):
        live = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        bt = backtest._trade_plan_at(df, t, "bullish", FIB_LIMIT, HZ, atr_series)
        if live is None:
            assert bt is None
            continue
        assert bt == pytest.approx((live.trigger_price, live.stop_loss, live.tp1))


def test_run_backtest_scores_fills_from_the_limit_and_records_every_order():
    df = _frame()
    with ef.gate_override(FIB_LIMIT, UNMASKED):
        summary = backtest.run_backtest("T", df, FIB_LIMIT, HZ, exit_model="v2", scale_out=True)
    assert summary.limit_orders, "fixture must place at least one order"
    assert {order["status"] for order in summary.limit_orders} <= {"filled", "expired", "cancelled"}
    filled = [order for order in summary.limit_orders if order["status"] == "filled"]
    assert len(filled) == len(summary.trades)
    for order, trade in zip(filled, summary.trades):
        assert trade.entry_date == order["signal_date"]
        assert trade.entry == pytest.approx(order["limit_price"], abs=1e-4)
        assert order["fill_price"] <= order["limit_price"] + 1e-9
        assert order["fill_date"] > order["signal_date"]


def test_truncation_invariance_of_the_built_plan():
    """No lookahead in the plan: the plan at t is the same from df.iloc[:t+1]."""
    df = _frame()
    for t in _arm_bars(df):
        full = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        cut = builders.build_strategy_plan(df.iloc[:t + 1], t, ticker="T", strategy=FIB_LIMIT,
                                           horizon_key=HZ, direction="bullish")
        assert (full is None) == (cut is None)
        if full is not None:
            assert (cut.trigger_price, cut.stop_loss, cut.tp1, cut.limit_cancel_level) == pytest.approx(
                (full.trigger_price, full.stop_loss, full.tp1, full.limit_cancel_level))


@pytest.mark.parametrize("scale", [20.0, 0.05])
def test_arming_is_price_scale_invariant(scale):
    """The masked entry is trivially scale-invariant in test_spot_scaling_parity;
    pin the unmasked arming rule here."""
    df = _frame()
    scaled = df.copy()
    scaled[["Open", "High", "Low", "Close"]] *= scale
    assert _arm_bars(scaled) == _arm_bars(df)
```

And in `tests/planning/test_strategy_branch_table.py`, after line 8 (`        "Fibonacci", "Support/Resistance", "Elliott Wave", "Fibonacci Continuation",`) add the line `        "Fibonacci Limit",`.

- [ ] **Step 3: Run to verify it fails.** `python scripts/dev/testrun.py file tests/planning/test_fib_limit_registration.py`. Expected: FAIL — `ImportError: cannot import name 'FIB_LIMIT' from 'swingbot.core.market.strategy_types'`.

- [ ] **Step 4: strategy_types.py.** After line 22 (`FADE_STRATEGY = "Downtrend Overbought Fade"`) add:

```python
# v131: a resting buy limit inside today's Fibonacci retracement zone (masked).
FIB_LIMIT = "Fibonacci Limit"
```

In `STRATEGY_GATES`, after `    "First Bearish Compression Release": {"directions": ()},` (line 269) add:

```python
    # v131 ships masked, out of backtest.ALL_STRATEGIES; its measurement unmasks
    # it through entry_filters.gate_override. Live wiring is a follow-on spec.
    FIB_LIMIT: {"directions": ()},
```

- [ ] **Step 5: entry_filters.py.** Replace the import block at lines 23-26 with:

```python
from swingbot.core.market.strategy_types import (
    FIB_LIMIT, FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE,
    STRATEGY_GATES, admits,
)
```

Directly after V131-02's `fib_limit_cancel_at` function (ends `    return None if row is None else float(row["swing_high"])`), add:

```python


def fibonacci_limit_entries(df, horizon_key, params=None):
    """Bullish arming bars of the v131 Fibonacci Limit; never bearish. While the
    strategy is masked (it ships masked) this returns all-False without
    walking the order book, so the live scan pays nothing for it."""
    off = _off(df)
    if not admits(FIB_LIMIT, "bullish", horizon_key):
        return off, off.copy()
    return fibonacci_limit_setups(df, horizon_key, params)["arm"].astype(bool), off


ENTRY_FUNCS[FIB_LIMIT] = fibonacci_limit_entries
```

- [ ] **Step 6: params.py.** Replace line 7's import line with:

```python
from swingbot.core.backtesting.registry import Badge, decay_note, get_badge
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION, FIB_LIMIT
```

In `EXIT_V2_PARAMS`, after `    "First Bearish Compression Release": {"trail_atr_mult": 2.5, "tp2": False},` (line 49) add:

```python
    # v131: today's Fibonacci exits, unchanged (spec "The order and the plan").
    FIB_LIMIT: {"trail_atr_mult": 3.0, "tp2": False},
```

In `PLAN_SHAPES`, after the compression short's entry (the line ending `"hold_cap_bars": 10},   # hard exit 10 sessions after the fill`) add:

```python
    # v131: buy limit inside the retracement zone, live expiry_bars (= the
    # setup's N, entry_filters.DEFAULT_PARAMS) bars after the arming bar;
    # Fibonacci's own TP1 fraction and break-even trigger.
    FIB_LIMIT: {"entry_type": "limit", "expiry_bars": 5, "tp1_fraction": TP1_FRACTION,
                "breakeven_trigger_fraction": BREAKEVEN_TRIGGER_FRACTION,
                "limit_price": "fib_zone"},
```

- [ ] **Step 7: builders.py.**

(a) Replace the `strategy_types` import (lines 12-13) with:

```python
from swingbot.core.market.strategy_types import (BREAKEVEN_TRIGGER_FRACTION, COMPRESSION_SHORT,
                                                  FIB_LIMIT, HORIZONS, SHORT_STRATEGIES)
```

(b) Directly above `def _atr_branch(inputs):` (line 218) insert:

```python
def _fib_limit_plan(entry, atr_val, swing_low, direction, horizon_key, candidate_levels,
                    params=None):
    """v131: (stop, tp1) priced from the limit `entry`. Stop = swing_low -
    STRUCTURE_BUFFER_ATR x ATR14 through _bounded_stop under FIB_LIMIT's own
    ceiling (capped at 2% below the limit out of STRUCTURAL_STOP_SCOPE, dropped
    inside it); TP1 = select_structural_target over the Fibonacci candidates,
    R measured from the limit. None when bearish, dropped, or no candidate
    reaches the floor -- no order is placed."""
    if direction != "bullish":
        return None
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
    stop_loss = _bounded_stop(entry, swing_low - STRUCTURE_BUFFER_ATR * atr_val, True,
                              FIB_LIMIT, direction, horizon_key)
    if stop_loss is None:
        return None
    take_profit = select_structural_target(
        entry, stop_loss, True, candidate_levels,
        params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    return None if take_profit is None else (stop_loss, take_profit)


def _fib_limit_branch(inputs):
    """Size a v131 Fibonacci Limit order from its frozen swing low; inputs.close
    is the limit price (plan_entry_reference)."""
    from swingbot.core.market.entry_filters import fib_limit_anchors

    horizon = HORIZONS[inputs.horizon_key]
    window = inputs.df.iloc[max(0, inputs.index + 1 - horizon["fib_lookback"]):inputs.index + 1]
    swing_low = float(fib_limit_anchors(window, inputs.horizon_key)["swing_low"].iloc[-1])
    if not np.isfinite(swing_low):
        return None
    candidates = fib_target_candidates(inputs.df, inputs.index, horizon, inputs.close)
    result = _fib_limit_plan(inputs.close, inputs.atr_val, swing_low, inputs.direction,
                             inputs.horizon_key, candidates, params=inputs.scan_params)
    return _branch_result(result, candidates)


```

(c) After `_STRUCTURAL_BRANCHES[COMPRESSION_SHORT] = _compression_branch` (line 255) add `_STRUCTURAL_BRANCHES[FIB_LIMIT] = _fib_limit_branch`.

(d) Replace V131-04's `LIMIT_PRICERS: dict[str, LimitPricer] = {}` with:

```python
def _fib_zone_price(df, index, horizon_key, direction):
    from swingbot.core.market.entry_filters import fib_limit_price_at
    return fib_limit_price_at(df, index, horizon_key, direction)


def _fib_zone_cancel(df, index, horizon_key, direction):
    from swingbot.core.market.entry_filters import fib_limit_cancel_at
    return fib_limit_cancel_at(df, index, horizon_key, direction)


LIMIT_PRICERS: dict[str, LimitPricer] = {
    # v131 Fibonacci Limit: swing_high - L x leg, cancelled above the swing high.
    "fib_zone": LimitPricer(price=_fib_zone_price, cancel_level=_fib_zone_cancel),
}
```

- [ ] **Step 8: Run to verify it passes, plus every test that enumerates `ENTRY_FUNCS` or the branch table.**

```bash
python scripts/dev/testrun.py file tests/planning/test_fib_limit_registration.py
python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py
python scripts/dev/testrun.py file tests/market/test_v113_horizon.py
python scripts/dev/testrun.py file tests/marketdata/test_spot_scaling_parity.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py
```

Expected: 11 passed in the new file; every other file green (the masked entry is all-False on `1w` and everywhere, so `test_every_registered_strategy_is_masked_on_1w_by_default` and the scaling parity hold). Also `python -c "import bot"` from the worktree imports cleanly (no import cycle through `params` → `strategy_types`).

- [ ] **Step 9: No-lookahead.** `test_truncation_invariance_of_the_built_plan` must pass: the plan built from `df.iloc[:t+1]` equals the plan from the full frame at every arming bar. `fib_target_candidates` already slices to `index`; `_fib_limit_branch` slices its own window.

- [ ] **Step 10: Complexity.** `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/market/entry_filters.py swingbot/core/planning/params.py` — no v131 function listed (measured: `_fib_limit_plan` 5, `_fib_limit_branch` 2, `fibonacci_limit_entries` 2).

- [ ] **Step 11: Commit**

```bash
git -C <worktree> add swingbot/core/market/strategy_types.py swingbot/core/market/entry_filters.py swingbot/core/planning/params.py swingbot/core/planning/builders.py tests/planning/test_fib_limit_registration.py tests/planning/test_strategy_branch_table.py
git -C <worktree> commit -m "feat(v131): register Fibonacci Limit masked -- arming entries, limit plan shape, fib_zone pricer, sizing from the limit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
