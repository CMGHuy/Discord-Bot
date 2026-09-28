# v113 Part 1b — Reward floor, limit entries, the Downtrend Overbought Fade, D fetch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §1, §3, §5, §8.1–8.3

Same worktree and branch as Part 1a. Every path is relative to the worktree root; no command uses `cd`.

---

### Task V113-5: The horizon-scoped reward floor for strategy plans

**Files:**
- Create: `swingbot/core/planning/reward_floor.py`
- Modify: `swingbot/core/planning/builders.py` (import; new `_geometry_ok`; the `if abs(close - stop) <= 0:` check in `build_strategy_plan`)
- Modify: `swingbot/core/backtesting/backtest.py` (new `_floored`; the last line of `_trade_plan_at`)
- Create: `tests/planning/test_reward_floor.py`

**Interfaces:**
- Consumes: `HORIZONS["1w"]["min_reward_pct"] = 2.0`, `LEGACY_HORIZONS` (V113-2).
- Produces (module `swingbot.core.planning.reward_floor`): `DROPS: collections.Counter`, `PASSES: collections.Counter` keyed `(strategy, horizon_key)`; `floor_pct(horizon_key) -> float | None`; `clears(entry, tp1, strategy, horizon_key) -> bool`; `reset() -> None`. `builders._geometry_ok(close, stop, tp1, strategy, horizon_key) -> bool`; `backtest._floored(entry, stop_loss, take_profit, strategy, horizon_key) -> tuple | None`. V113-10 reads the counters for the floor-drop rate.

Amendment 1 (index) explains why this is a new floor and not a change to `config.MIN_REWARD_PCT`.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_reward_floor.py`:

```python
"""v113 §1: the strategy-plan reward floor exists on 1w only (2.0%)."""
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.planning import reward_floor as rf


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)
    rf.reset()
    yield
    rf.reset()


def test_only_1w_has_a_floor():
    assert rf.floor_pct("1w") == 2.0
    assert all(rf.floor_pct(hk) is None for hk in LEGACY_HORIZONS)


def test_legacy_horizons_always_clear_and_count_nothing():
    for hk in LEGACY_HORIZONS:
        assert rf.clears(100.0, 100.5, "MACD", hk)
    assert not rf.DROPS and not rf.PASSES


def test_1w_floor_is_two_percent_in_both_directions_and_counted():
    assert rf.clears(100.0, 102.0, "MACD", "1w")
    assert rf.clears(100.0, 98.0, "MACD", "1w")
    assert not rf.clears(100.0, 101.9, "MACD", "1w")
    assert rf.PASSES[("MACD", "1w")] == 2 and rf.DROPS[("MACD", "1w")] == 1
    rf.reset()
    assert not rf.DROPS and not rf.PASSES


def test_the_fade_target_at_m_one_sits_exactly_on_the_floor():
    entry = 187.3899
    stop = entry * 1.02
    assert rf.clears(entry, entry - 1.0 * (stop - entry), "Downtrend Overbought Fade", "1w")


def test_build_strategy_plan_drops_what_the_floor_drops(market_df, monkeypatch):
    from swingbot.core.planning import builders
    kwargs = dict(ticker="X", strategy="RSI Divergence", horizon_key="4w", direction="bullish")
    i = next(i for i in range(400, len(market_df))
             if builders.build_strategy_plan(market_df, i, **kwargs) is not None)
    monkeypatch.setattr(rf, "clears", lambda *args: False)
    assert builders.build_strategy_plan(market_df, i, **kwargs) is None


def test_trade_plan_at_drops_what_the_floor_drops(market_df, monkeypatch):
    from swingbot.core.backtesting import backtest as bt
    series = bt._plan_series(market_df, "RSI Divergence", "4w")
    i = next(i for i in range(400, len(market_df))
             if bt._trade_plan_at(market_df, i, "bullish", "RSI Divergence", "4w", *series) is not None)
    monkeypatch.setattr(rf, "clears", lambda *args: False)
    assert bt._trade_plan_at(market_df, i, "bullish", "RSI Divergence", "4w", *series) is None


def test_every_1w_plan_that_builds_clears_two_percent(market_df):
    from swingbot.core.planning import builders
    built = [p for i in range(400, 700)
             if (p := builders.build_strategy_plan(market_df, i, ticker="X", strategy="RSI Divergence",
                                                   horizon_key="1w", direction="bullish")) is not None]
    assert all(abs(p.tp1 - p.trigger_price) / p.trigger_price * 100 >= 2.0 - 1e-9 for p in built)
    assert built, "fixture must build at least one 1w plan"
    assert rf.PASSES[("RSI Divergence", "1w")] == len(built)   # every built plan was counted once
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_reward_floor.py`
Expected: FAIL — `ImportError: cannot import name 'reward_floor'`.

- [ ] **Step 3: Create `swingbot/core/planning/reward_floor.py`**

```python
"""v113 §1: the horizon-scoped reward floor for strategy-source plans.

Only a horizon carrying "min_reward_pct" in strategy_types.HORIZONS has one
(today: 1w = 2.0%). Every legacy horizon has none -- exactly as before v113,
when no reward floor gated strategy plans at all (config.MIN_REWARD_PCT gates
only confluence scenarios, and still does). build_strategy_plan and
backtest._trade_plan_at both call clears(), so live and backtest cannot diverge.

DROPS / PASSES count every decision per (strategy, horizon) in this process so
measure_v113 can report a floor-drop rate; call reset() before a measured run.
"""
from __future__ import annotations

import collections

from swingbot.core.market.strategy_types import HORIZONS

DROPS: collections.Counter = collections.Counter()
PASSES: collections.Counter = collections.Counter()
_EPS = 1e-9   # a target exactly on the floor must clear it despite float noise


def floor_pct(horizon_key: str) -> float | None:
    """This horizon's minimum target distance in % of entry, or None (no floor)."""
    return HORIZONS[horizon_key].get("min_reward_pct")


def clears(entry: float, tp1: float, strategy: str, horizon_key: str) -> bool:
    """True when TP1 sits at least the horizon's floor away from entry (either
    direction). Horizons without a floor always clear and are not counted."""
    floor = floor_pct(horizon_key)
    if floor is None:
        return True
    ok = entry > 0 and abs(tp1 - entry) / entry * 100.0 >= floor - _EPS
    (PASSES if ok else DROPS)[(strategy, horizon_key)] += 1
    return ok


def reset() -> None:
    DROPS.clear()
    PASSES.clear()
```

- [ ] **Step 4: Wire it into the live builder.** In `swingbot/core/planning/builders.py`, directly under `from . import params as plan_params` add `from . import reward_floor`. Directly above `def build_strategy_plan(` add:

```python
def _geometry_ok(close, stop, tp1, strategy, horizon_key) -> bool:
    """A plan needs a real stop distance and (v113 §1) must clear its horizon's
    strategy-plan reward floor -- the same check backtest._trade_plan_at runs."""
    return abs(close - stop) > 0 and reward_floor.clears(close, tp1, strategy, horizon_key)
```

In `build_strategy_plan`, replace

```python
    if abs(close - stop) <= 0:
        return None
```

with

```python
    if not _geometry_ok(close, stop, tp1, strategy, horizon_key):
        return None
```

- [ ] **Step 5: Wire it into the backtest.** In `swingbot/core/backtesting/backtest.py`, directly above `def _trade_plan_at(` add:

```python
def _floored(entry, stop_loss, take_profit, strategy, horizon_key):
    """(entry, stop, target), or None when the plan misses its horizon's v113
    reward floor -- the same planning/reward_floor check build_strategy_plan runs."""
    from swingbot.core.planning.reward_floor import clears
    if not clears(entry, take_profit, strategy, horizon_key):
        return None
    return entry, stop_loss, take_profit
```

and change the last line of `_trade_plan_at` from `return entry, stop_loss, take_profit` to `return _floored(entry, stop_loss, take_profit, strategy, horizon_key)`.

- [ ] **Step 6: Run the tests, the witness and the builder/backtest neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_reward_floor.py tests/market/test_v113_horizon_witness.py tests/planning/test_build_strategy_plan.py tests/backtesting/test_sizing_parity.py tests/backtesting/test_backtest_engine.py`
Expected: all PASS. If `test_every_1w_plan_that_builds_clears_two_percent` builds zero plans, widen its range to `range(400, 1400)` rather than weakening the assertion.

Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py swingbot/core/planning/reward_floor.py`
Expected: `build_strategy_plan` still `C (13)`, `_trade_plan_at` still `C (13)`, `run_backtest` still `F (59)`; nothing new listed.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/reward_floor.py swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py tests/planning/test_reward_floor.py
git commit -m "feat(v113): horizon-scoped strategy-plan reward floor -- 2% on 1w, none on legacy horizons, counted for the floor-drop rate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-6: A `limit` entry type in the shared simulator, and per-strategy plan shapes

**Files:**
- Modify: `swingbot/core/planning/lifecycle.py` (append four helpers after `pending_invalidated`)
- Modify: `swingbot/core/planning/exit_sim.py` (import; new `_walk_for`, `_fill_bar_exit`, `_limit_entry_exit`; `simulate_exit`)
- Modify: `swingbot/core/planning/plan_types.py:30` (comment only)
- Modify: `swingbot/core/planning/params.py` (new `PLAN_SHAPES` after `EXIT_V2_PARAMS`)
- Modify: `swingbot/core/planning/builders.py` (new `plan_shape_for` after `entry_type_for`; `build_strategy_plan` reads it)
- Modify: `swingbot/core/backtesting/backtest.py` (new `_bt_plan`; `run_backtest`'s v2 branch builds its plan through it)
- Create: `tests/planning/test_limit_entry.py`, `tests/planning/test_plan_shape.py`

**Interfaces:**
- Consumes: `_geometry_ok` context in `build_strategy_plan` (V113-5 — same file, sequential).
- Produces:
  - `lifecycle.limit_hit(plan, bar_high, bar_low) -> bool`, `lifecycle.limit_fill_price(plan, bar_open) -> float`, `lifecycle.stop_touched(plan, bar_high, bar_low) -> bool`, `lifecycle.at_or_beyond_stop(plan, price) -> bool`.
  - `simulate_exit` handles `plan.entry_type == "limit"`; any plan with `tp1_fraction >= 1.0` takes the single-leg walk.
  - `params.PLAN_SHAPES: dict[str, dict]` (empty here; V113-8 adds the fade's row).
  - `builders.plan_shape_for(strategy) -> dict` with keys `entry_type`, `expiry_bars`, `tp1_fraction`, `breakeven_trigger_fraction`.
  - `backtest._bt_plan(df, i, *, ticker, strategy, horizon_key, direction, entry, stop_loss, take_profit, tp2, trail_atr_mult) -> TradePlanV2`.

Load `no-lookahead` before starting: the fill reads bar *t+1*, which only the simulator may do.

- [ ] **Step 1: Write the failing simulator tests** — `tests/planning/test_limit_entry.py`:

```python
"""v113 §3: limit entries in the shared exit simulator (spec fill model + amendment 3)."""
import pytest

from swingbot.core.planning import lifecycle
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

SIGNAL = (100.5, 101.0, 99.5, 100.0)      # bar 0: signal bar; its close 100 is the limit
FLAT = (99.5, 100.2, 99.3, 99.6)          # trades through 100, never reaches 102 or 98


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="1w", direction="bearish",
        entry_type="limit", trigger_price=100.0, entry_price=None, expiry_bars=1,
        stop_loss=102.0, tp1=98.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=1.0, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _df(*bars):
    return make_ohlcv([SIGNAL, *bars])


@pytest.mark.parametrize("scale_out", [False, True])
def test_sell_limit_fills_at_the_limit_and_wins_at_the_whole_position_target(scale_out):
    df = _df((99.5, 100.4, 99.2, 99.6), (99.4, 99.6, 98.6, 98.8), (98.7, 98.9, 97.9, 98.1), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=scale_out)
    assert (res.outcome, res.entry_index, res.entry_price, res.exit_index) == ("win", 1, 100.0, 3)
    assert res.r_total == pytest.approx(1.0) and res.runner_outcome is None
    assert [leg["fraction"] for leg in res.legs] == [1.0]


def test_no_fill_when_bar_t_plus_1_never_reaches_the_limit_even_if_t_plus_2_does():
    df = _df((99.0, 99.8, 98.5, 99.0), (99.5, 100.5, 99.0, 100.0), FLAT)
    assert simulate_exit(df, 0, _plan(), scale_out=True).outcome == "not_triggered"


def test_a_gap_above_the_limit_fills_at_the_open():
    df = _df((100.8, 101.0, 100.1, 100.3), (100.0, 100.2, 98.5, 98.7), (98.5, 98.6, 97.8, 98.0))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert res.entry_price == 100.8 and res.outcome == "win"
    assert res.r_total == pytest.approx(2.8 / 1.2, abs=1e-3)


def test_a_stop_touch_on_the_fill_bar_is_a_full_loss_on_that_bar():
    df = _df((99.8, 102.5, 99.5, 101.8), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)
    assert res.legs[0]["exit_price"] == 102.0


def test_a_gap_through_the_stop_exits_flat_on_the_fill_bar():
    df = _df((102.6, 103.0, 102.2, 102.8), FLAT)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_price, res.exit_index, res.r_total) == ("scratch", 102.6, 1, 0.0)


def test_the_time_stop_closes_at_the_seventh_bar_after_entry():
    df = _df(*([FLAT] * 10))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 8)
    assert res.r_total == pytest.approx(0.2)


def test_buy_limit_mirrors_the_sell_limit():
    plan = _plan(direction="bullish", stop_loss=98.0, tp1=102.0)
    df = _df((100.5, 100.8, 99.9, 100.4), (100.6, 102.2, 100.4, 102.0))
    res = simulate_exit(df, 0, plan, scale_out=True)
    assert (res.outcome, res.entry_price, res.exit_index) == ("win", 100.0, 2)


def test_lifecycle_helpers():
    sell, buy = _plan(), _plan(direction="bullish", stop_loss=98.0, tp1=102.0)
    assert lifecycle.limit_hit(sell, 100.0, 99.0) and not lifecycle.limit_hit(sell, 99.99, 99.0)
    assert lifecycle.limit_hit(buy, 101.0, 100.0) and not lifecycle.limit_hit(buy, 101.0, 100.01)
    assert lifecycle.limit_fill_price(sell, 99.0) == 100.0 and lifecycle.limit_fill_price(sell, 101.0) == 101.0
    assert lifecycle.limit_fill_price(buy, 101.0) == 100.0 and lifecycle.limit_fill_price(buy, 99.0) == 99.0
    assert lifecycle.stop_touched(sell, 102.0, 99.0) and not lifecycle.stop_touched(sell, 101.9, 99.0)
    assert lifecycle.at_or_beyond_stop(sell, 102.0) and not lifecycle.at_or_beyond_stop(buy, 98.1)
```

`tests/planning/test_plan_shape.py`:

```python
"""v113: one plan shape per strategy, read by the live builder and the backtest alike."""
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION
from swingbot.core.planning import builders, params
from swingbot.core.planning.plan_types import PlanStatus

LIMIT = {"entry_type": "limit", "expiry_bars": 1, "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0}


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)


def test_unlisted_strategies_keep_todays_shape():
    assert builders.plan_shape_for("MACD") == {
        "entry_type": "market", "expiry_bars": 5, "tp1_fraction": 0.5,
        "breakeven_trigger_fraction": BREAKEVEN_TRIGGER_FRACTION}


def test_a_listed_shape_overrides_only_its_keys(monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, "Probe", {"entry_type": "limit", "expiry_bars": 1})
    shape = builders.plan_shape_for("Probe")
    assert (shape["entry_type"], shape["expiry_bars"], shape["tp1_fraction"]) == ("limit", 1, 0.5)


def test_the_live_builder_uses_the_shape(market_df, monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, "RSI Divergence", dict(LIMIT))
    plan = next(p for i in range(400, 700)
                if (p := builders.build_strategy_plan(market_df, i, ticker="X", strategy="RSI Divergence",
                                                      horizon_key="4w", direction="bullish")) is not None)
    assert (plan.entry_type, plan.expiry_bars, plan.tp1_fraction, plan.breakeven_trigger_fraction,
            plan.entry_price, plan.status) == ("limit", 1, 1.0, 1.0, None, PlanStatus.PENDING)


def test_the_backtest_uses_the_shape(market_df, monkeypatch):
    from swingbot.core.backtesting import backtest as bt
    monkeypatch.setitem(params.PLAN_SHAPES, "Probe", dict(LIMIT))
    plan = bt._bt_plan(market_df, 500, ticker="X", strategy="Probe", horizon_key="4w",
                       direction="bullish", entry=100.0, stop_loss=98.0, take_profit=103.0,
                       tp2=None, trail_atr_mult=2.5)
    assert (plan.entry_type, plan.expiry_bars, plan.tp1_fraction,
            plan.breakeven_trigger_fraction, plan.entry_price) == ("limit", 1, 1.0, 1.0, None)
    default = bt._bt_plan(market_df, 500, ticker="X", strategy="MACD", horizon_key="4w",
                          direction="bullish", entry=100.0, stop_loss=98.0, take_profit=103.0,
                          tp2=None, trail_atr_mult=2.5)
    assert (default.entry_type, default.expiry_bars, default.tp1_fraction, default.entry_price) == (
        "market", 5, 0.5, 100.0)
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_limit_entry.py tests/planning/test_plan_shape.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'limit_hit'` / `'plan_shape_for'`; the limit simulations return `not_triggered` from the stop-entry scan.

- [ ] **Step 3: Lifecycle helpers.** Append to `swingbot/core/planning/lifecycle.py`, directly after `pending_invalidated`:

```python
def limit_hit(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """v113: a resting LIMIT order at trigger_price trades on this bar -- a sell
    limit (bearish) when the high reaches it, a buy limit (bullish) when the
    low does. Touching the limit exactly counts."""
    if plan.direction == "bullish":
        return bar_low <= plan.trigger_price
    return bar_high >= plan.trigger_price


def limit_fill_price(plan: TradePlanV2, bar_open: float) -> float:
    """At the limit, or at the open when the bar gapped through it: a limit
    never fills worse than its own price (a sell fills at max(open, limit))."""
    if plan.direction == "bullish":
        return min(bar_open, plan.trigger_price)
    return max(bar_open, plan.trigger_price)


def stop_touched(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """This bar reached the plan's initial stop."""
    if plan.direction == "bullish":
        return bar_low <= plan.stop_loss
    return bar_high >= plan.stop_loss


def at_or_beyond_stop(plan: TradePlanV2, price: float) -> bool:
    """`price` already sits at or through the stop (a fill that gapped past it)."""
    if plan.direction == "bullish":
        return price <= plan.stop_loss
    return price >= plan.stop_loss
```

- [ ] **Step 4: The simulator.** In `swingbot/core/planning/exit_sim.py` change the lifecycle import to:

```python
from .lifecycle import (at_or_beyond_stop, fill_price, limit_fill_price, limit_hit,
                        pending_expired, pending_invalidated, stop_touched, trigger_hit)
```

Directly above `def simulate_exit(` add:

```python
def _walk_for(plan: TradePlanV2, scale_out: bool):
    """The exit walk for this plan. A whole-position target (tp1_fraction 1.0,
    v113 Part A) has no runner leg, so it always takes the single-leg walk --
    the scale-out walk's pre-TP1 phase, then out at TP1."""
    if scale_out and plan.tp1_fraction < 1.0:
        return _scale_out_exit_walk
    return _single_leg_exit_walk


def _fill_bar_exit(df, j: int, entry_price: float, plan: TradePlanV2) -> ExitResult | None:
    """v113 amendment 3: the bar that fills a limit can also reach the stop.
    Stop first, as everywhere in this engine. A fill at or through the stop (the
    bar gapped past it) exits flat at the fill -- a scratch, 0R, because the
    bracket stop triggers at once; otherwise a stop touch on the fill bar is a
    full loss at the stop. None when the fill bar is clean."""
    if at_or_beyond_stop(plan, entry_price):
        return ExitResult(outcome="scratch", runner_outcome=None, entry_index=j, exit_index=j,
                          entry_price=entry_price, r_total=0.0,
                          legs=[{"fraction": 1.0, "exit_price": entry_price, "r": 0.0,
                                 "reason": "gap_through_stop"}])
    if stop_touched(plan, float(df["High"].values[j]), float(df["Low"].values[j])):
        return ExitResult(outcome="loss", runner_outcome=None, entry_index=j, exit_index=j,
                          entry_price=entry_price, r_total=-1.0,
                          legs=[{"fraction": 1.0, "exit_price": plan.stop_loss, "r": -1.0,
                                 "reason": "stop"}])
    return None


def _limit_entry_exit(df, signal_index: int, plan: TradePlanV2, scale_out: bool,
                      max_holding_days: int) -> ExitResult:
    """v113 §3: a resting limit at trigger_price, live for the plan's
    expiry_bars bars after the signal bar (Part A: 1, so bar t+1 only). Fills on
    the first bar that trades through it, at limit_fill_price; the fill bar is
    checked against the stop (_fill_bar_exit), then the normal exit walk runs
    from the fill bar, so the time stop counts bars after ENTRY."""
    high, low, open_ = df["High"].values, df["Low"].values, df["Open"].values
    last = min(signal_index + plan.expiry_bars, len(df) - 1)
    for j in range(signal_index + 1, last + 1):
        if not limit_hit(plan, float(high[j]), float(low[j])):
            continue
        entry_price = limit_fill_price(plan, float(open_[j]))
        early = _fill_bar_exit(df, j, entry_price, plan)
        if early is not None:
            return early
        return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)
    return _not_triggered()
```

In `simulate_exit`, directly after the `hold_cap` block and before `if plan.entry_type == "market":`, add:

```python
    if plan.entry_type == "limit":
        return _limit_entry_exit(df, signal_index, plan, scale_out, max_holding_days)
```

and replace **both** occurrences of the pair

```python
            if not scale_out:
                return _single_leg_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
            return _scale_out_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
```

(one in the `market` branch at 8 spaces of indent, one in the stop-entry loop at 12) with the single line, at the same indent:

```python
        return _walk_for(plan, scale_out)(df, entry_index, entry_price, plan, max_holding_days)
```

Add to the docstring, after the `stop_entry` paragraph: ``` ``limit`` entries (v113) are resting limits: see _limit_entry_exit. A plan whose tp1_fraction is 1.0 always takes the single-leg walk.```

In `swingbot/core/planning/plan_types.py` change the `entry_type` comment to `# "stop_entry" | "market" | "limit" (v113)`.

- [ ] **Step 5: Plan shapes.** In `swingbot/core/planning/params.py`, directly after the `EXIT_V2_PARAMS` dict, add:

```python

# v113: the shape of a plan whose strategy is traded as resting orders placed at
# alert time -- entry type, how long the entry order lives, how much of the
# position TP1 closes, and the break-even trigger (1.0 = never before TP1,
# because a resting bracket is never edited). A strategy not listed gets
# today's shape (builders.plan_shape_for). Read by the live builder and the
# backtest alike.
PLAN_SHAPES: dict[str, dict] = {}
```

In `swingbot/core/planning/builders.py`, directly after `entry_type_for`, add:

```python
def plan_shape_for(strategy: str) -> dict:
    """Entry type, entry-order life, TP1 fraction and break-even trigger for a
    strategy-source plan. build_strategy_plan and backtest._bt_plan both read
    this, so the two cannot diverge. Unlisted strategies get today's shape."""
    shape = {"entry_type": entry_type_for(strategy, "strategy"),
             "expiry_bars": DEFAULT_EXPIRY_BARS, "tp1_fraction": TP1_FRACTION,
             "breakeven_trigger_fraction": BREAKEVEN_TRIGGER_FRACTION}
    shape.update(plan_params.PLAN_SHAPES.get(strategy, {}))
    return shape
```

In `build_strategy_plan`, replace `entry_type = entry_type_for(strategy, "strategy")` with

```python
    shape = plan_shape_for(strategy)
    entry_type = shape["entry_type"]
```

and in its `TradePlanV2(...)` call replace `expiry_bars=DEFAULT_EXPIRY_BARS` with `expiry_bars=shape["expiry_bars"]`, `tp1_fraction=TP1_FRACTION` with `tp1_fraction=shape["tp1_fraction"]`, and `breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION` with `breakeven_trigger_fraction=shape["breakeven_trigger_fraction"]`.

- [ ] **Step 6: The backtest builds its plan through the shape.** In `swingbot/core/backtesting/backtest.py`, directly above `def run_backtest(` add:

```python
def _bt_plan(df, i, *, ticker, strategy, horizon_key, direction, entry, stop_loss,
             take_profit, tp2, trail_atr_mult):
    """The backtest's TradePlanV2 for one entry, in the same shape the live
    builder uses (builders.plan_shape_for) -- a limit-entry strategy is
    simulated as a limit here too. expiry 5 / TP1 fraction 0.5 for every
    unlisted strategy, exactly the literals this loop carried before v113."""
    from swingbot.core.planning.builders import plan_shape_for
    from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
    from swingbot.core.planning.short_builders import short_hold_cap

    shape = plan_shape_for(strategy)
    return TradePlanV2(
        plan_id="bt", ticker=ticker, created_at=str(df.index[i].date()),
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=direction, entry_type=shape["entry_type"], trigger_price=entry,
        entry_price=entry if shape["entry_type"] == "market" else None,
        expiry_bars=shape["expiry_bars"], stop_loss=stop_loss,
        tp1=take_profit, tp1_fraction=shape["tp1_fraction"], tp2=tp2,
        breakeven_trigger_fraction=shape["breakeven_trigger_fraction"],
        trail_atr_mult=trail_atr_mult,
        hold_cap_bars=short_hold_cap(df, i, strategy),
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
    )
```

In `run_backtest`'s v2 setup block, change

```python
        from swingbot.core.planning.plan_engine import (
            PlanStatus, TradePlanV2, entry_type_for, exit_params_for,
            select_tp2,
        )
        from swingbot.core.planning.short_builders import short_hold_cap
```

to `from swingbot.core.planning.plan_engine import exit_params_for, select_tp2`, and in the v2 branch replace everything from `entry_type = entry_type_for(strategy, "strategy")` through the closing `)` of the `TradePlanV2(` call with:

```python
            plan = _bt_plan(df, i, ticker=ticker, strategy=strategy, horizon_key=horizon_key,
                            direction=direction, entry=entry, stop_loss=stop_loss,
                            take_profit=take_profit, tp2=tp2,
                            trail_atr_mult=_exit_params["trail_atr_mult"])
```

- [ ] **Step 7: Run the tests, the witness and the simulator/backtest neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_limit_entry.py tests/planning/test_plan_shape.py tests/market/test_v113_horizon_witness.py`
Expected: all PASS.

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py tests/planning/test_exit_sim_single.py tests/planning/test_exit_sim_scaleout.py tests/planning/test_exit_sim_hold_cap.py tests/planning/test_build_strategy_plan.py tests/planning/test_short_builders.py tests/backtesting/test_backtest_engine.py tests/backtesting/test_exit_parity.py tests/backtesting/test_sizing_parity.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/planning/exit_sim.py swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py`
Expected: `_scale_out_exit_walk D (30)` and `_single_leg_exit_walk C (16)` unchanged; `simulate_exit` at or below its previous `B (10)` (it drops two `if`s and gains one); `run_backtest` below `F (59)`; `build_strategy_plan` still `C (13)`; no new function listed.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/planning/lifecycle.py swingbot/core/planning/exit_sim.py swingbot/core/planning/plan_types.py swingbot/core/planning/params.py swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py tests/planning/test_limit_entry.py tests/planning/test_plan_shape.py
git commit -m "feat(v113): limit entry type in the shared exit simulator (t+1 fill, fill-bar stop first) and per-strategy plan shapes for builder and backtest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-7: The Downtrend Overbought Fade signal, registered short-only and masked

**Files:**
- Modify: `swingbot/core/market/strategy_types.py:17-20` (short lists) and `STRATEGY_GATES` (one row)
- Modify: `swingbot/core/market/short_entries.py` (imports, constants, `fade_frame`, `FRAMES`, docstring)
- Modify: `scripts/backtest/measure_v104.py:33,52` (unpack `V104_SHORTS`)
- Create: `tests/market/test_fade_entries.py`

**Interfaces:**
- Consumes: `admits`, `gate_override` with `cells` (V113-2); `measure_v104.ALL_HZ` edit (V113-4, same file — sequential).
- Produces:
  - `strategy_types.V104_SHORTS = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")`, `strategy_types.FADE_STRATEGY = "Downtrend Overbought Fade"`, `SHORT_STRATEGIES = V104_SHORTS + (FADE_STRATEGY,)`; `STRATEGY_GATES["Downtrend Overbought Fade"] == {"directions": ()}`.
  - `short_entries.FADE`, `short_entries.fade_frame(df, horizon_key, params=None) -> DataFrame` with columns `signal, level, stop, target_a, target_b`; `DEFAULT_PARAMS[FADE] == {"m": 1.0}`; `ENTRY_FUNCS[FADE]` (short-only); `structure_at(FADE, ...)`.
  - `tests.market.test_fade_entries.fade_df(tail=12, tail_step=0.995) -> (df, t)` and `HZ = "1w"`, consumed by V113-8.

Load `no-lookahead` before starting.

- [ ] **Step 1: Write the failing tests** — `tests/market/test_fade_entries.py`:

```python
"""v113 §3 Part A: Downtrend Overbought Fade entries (bars <= t only)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.strategy_types import (FADE_STRATEGY, SHORT_STRATEGIES, STRATEGY_GATES,
                                                 V104_SHORTS)
from tests.helpers import make_ohlcv

HZ = "1w"
UNMASKED = {"directions": (), "cells": {("bearish", "1w")}}


def fade_df(tail=12, tail_step=0.995):
    """240 bars grinding 200 -> 100 (far under a falling SMA200), two +2% up days
    (RSI(2) ~82.7, then ~93.6 on bar t), then `tail` bars moving by `tail_step`."""
    closes = list(np.linspace(200.0, 100.0, 240))
    close = closes[-1]
    for step in (1.02, 1.02):
        close *= step
        closes.append(close)
    t = len(closes) - 1
    for _ in range(tail):
        close *= tail_step
        closes.append(close)
    df = make_ohlcv(closes, start="2015-01-02")
    df["evt_bars_to_next"] = np.nan
    return df, t


def test_fires_on_the_second_up_day_only():
    df, t = fade_df()
    frame = se.fade_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]


@pytest.mark.parametrize("m", [1.0, 1.25, 1.5])
def test_plan_columns_are_the_fixed_geometry(m):
    df, t = fade_df()
    row = se.fade_frame(df, HZ, params={"m": m}).iloc[t]
    close = float(df["Close"].iloc[t])
    assert row["level"] == pytest.approx(close)
    assert row["stop"] == pytest.approx(close * 1.02)
    assert row["target_a"] == pytest.approx(close - m * (close * 1.02 - close))
    assert np.isnan(row["target_b"])


@pytest.mark.parametrize("bars,fires", [(0, False), (3, False), (7, False), (8, True), (np.nan, True)])
def test_an_earnings_reaction_within_seven_bars_blocks(bars, fires):
    df, t = fade_df()
    df.loc[df.index[t], "evt_bars_to_next"] = bars
    assert bool(se.fade_frame(df, HZ)["signal"].iloc[t]) is fires


def test_no_earnings_column_means_no_signal():
    df, _ = fade_df()
    assert not se.fade_frame(df.drop(columns=["evt_bars_to_next"]), HZ)["signal"].any()


def test_needs_close_under_a_falling_sma200():
    closes = list(np.linspace(100.0, 200.0, 240))
    close = closes[-1]
    for step in (1.02, 1.02, 0.995):
        close *= step
        closes.append(close)
    df = make_ohlcv(closes, start="2015-01-02")
    df["evt_bars_to_next"] = np.nan
    assert not se.fade_frame(df, HZ)["signal"].any()


@pytest.mark.parametrize("offset", [-1, 0, 3])
def test_truncation_invariance(offset):
    df, t = fade_df()
    cut = t + offset
    assert cut < len(df) - 1
    full = se.fade_frame(df, HZ)
    part = se.fade_frame(df.iloc[:cut + 1], HZ)
    pd.testing.assert_series_equal(part.iloc[-1], full.iloc[cut], check_names=False)


def test_registered_short_only_and_masked_until_a_cell_admits_1w():
    df, t = fade_df()
    bull, bear = ef.ENTRY_FUNCS[se.FADE](df, HZ)
    assert not bull.any() and list(np.flatnonzero(bear.to_numpy())) == [t]
    assert STRATEGY_GATES[se.FADE] == {"directions": ()}
    masked_bull, masked_bear = ef.entries_for(se.FADE, df, HZ)
    assert not masked_bull.any() and not masked_bear.any()
    with ef.gate_override(se.FADE, UNMASKED):
        _, bear_1w = ef.entries_for(se.FADE, df, HZ)
        _, bear_2w = ef.entries_for(se.FADE, df, "2w")
    assert list(np.flatnonzero(bear_1w.to_numpy())) == [t] and not bear_2w.any()


def test_short_lists_and_defaults():
    assert se.FADE == FADE_STRATEGY == "Downtrend Overbought Fade"
    assert SHORT_STRATEGIES == V104_SHORTS + (FADE_STRATEGY,)
    assert (se.BULL_TRAP, se.VOL_BREAKDOWN, se.GAP_DRIFT) == V104_SHORTS
    assert ef.DEFAULT_PARAMS[se.FADE] == {"m": 1.0}


def test_structure_at_matches_the_frame_row():
    df, t = fade_df()
    structure = se.structure_at(se.FADE, df, t, HZ)
    close = float(df["Close"].iloc[t])
    assert structure["stop"] == pytest.approx(close * 1.02)
    assert structure["target_a"] == pytest.approx(close * 0.98)
    assert se.structure_at(se.FADE, df, t - 1, HZ) is None
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_fade_entries.py`
Expected: collection error — `ImportError: cannot import name 'FADE_STRATEGY'`.

- [ ] **Step 3: Short lists and the mask.** In `swingbot/core/market/strategy_types.py` replace

```python
SHORT_STRATEGIES = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")
```

with

```python
V104_SHORTS = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")
# v113 Part A: short-only and 1w only; masked until its 2026 holdout shot passes.
FADE_STRATEGY = "Downtrend Overbought Fade"
SHORT_STRATEGIES = V104_SHORTS + (FADE_STRATEGY,)
```

In `STRATEGY_GATES`, directly after the `"Earnings Gap Drift": {"directions": ()},` line, add:

```python
    # v113 Part A ships masked; a holdout pass would admit it as
    # "cells": {("bearish", "1w")} -- see the v113 plan's V113-19.
    "Downtrend Overbought Fade": {"directions": ()},
```

- [ ] **Step 4: The frame.** In `swingbot/core/market/short_entries.py`:
  - Change the first docstring line to `"""v104 Part B's three short-only strategies and v113 Part A's Downtrend Overbought Fade.`
  - Change the indicator/strategy_types imports to:

```python
from swingbot.core.market.indicators import rsi
from swingbot.core.market.strategy_types import (FADE_STRATEGY, HORIZONS, SR_VOLUME_MULTIPLE,
                                                 V104_SHORTS)
```

  - Replace `BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES` with:

```python
BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = V104_SHORTS
FADE = FADE_STRATEGY
```

  - Directly after `DEFAULT_PARAMS[GAP_DRIFT] = {"g": 0.05}`, add:

```python
DEFAULT_PARAMS[FADE] = {"m": 1.0}   # v113 §3 grid m in {1.0, 1.25, 1.5}; frozen by the pre-registration

# v113 §3 -- every value fixed by the spec, never grid-searched.
FADE_SMA = 200
FADE_SLOPE_BARS = 20
FADE_RSI_PERIOD = 2
FADE_RSI_MIN = 90.0
FADE_STOP_PCT = 2.0
FADE_EARNINGS_BARS = 7
```

  - Directly after `gap_drift_frame`, add:

```python
def fade_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """v113 A: at the close of bar t, a stock in a downtrend (close under a
    falling SMA200) whose RSI(2) spikes to >= 90, with no earnings reaction in
    the next 7 bars. level = close_t (the sell limit), stop = entry x 1.02,
    target_a = entry - m x (stop - entry). Horizon-independent; the mask keeps
    it on 1w. Reads bars <= t only, plus the scheduled next report date
    (evt_bars_to_next, the v104 §3.4 exception). Without earnings context there
    is no signal (silent while masked, like B3)."""
    p = _params(FADE, params)
    if "evt_bars_to_next" not in df.columns:
        return _empty(df)
    close = df["Close"]
    sma = close.rolling(FADE_SMA).mean()
    downtrend = (close < sma) & (sma < sma.shift(FADE_SLOPE_BARS))
    spike = rsi(close, FADE_RSI_PERIOD) >= FADE_RSI_MIN
    bars = df["evt_bars_to_next"]
    clear = ~((bars >= 0) & (bars <= FADE_EARNINGS_BARS))
    stop = close * (1.0 + FADE_STOP_PCT / 100.0)
    frame = _empty(df)
    frame["signal"] = (downtrend & spike & clear).fillna(False).astype(bool)
    frame["level"] = close.to_numpy(dtype=float)
    frame["stop"] = stop.to_numpy(dtype=float)
    frame["target_a"] = (close - float(p["m"]) * (stop - close)).to_numpy(dtype=float)
    return frame
```

  - Change `FRAMES = {...}` to `FRAMES = {BULL_TRAP: bull_trap_frame, VOL_BREAKDOWN: vol_breakdown_frame, GAP_DRIFT: gap_drift_frame, FADE: fade_frame}`.
  - Remove `SHORT_STRATEGIES` from the imports if it is now unused in this module.

- [ ] **Step 5: `measure_v104` keeps unpacking three names.** In `scripts/backtest/measure_v104.py` change the `strategy_types` import to `from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS, STRATEGY_GATES, V104_SHORTS  # noqa: E402` (keep whichever of `HORIZONS`/`LEGACY_HORIZONS` V113-4 left in use) and `BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES` to `BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = V104_SHORTS`.

- [ ] **Step 6: Run the tests and the short-strategy neighbours**

Run: `python scripts/dev/testrun.py file tests/market/test_fade_entries.py tests/market/test_short_entries.py tests/market/test_short_entries_b2_b3.py tests/planning/test_stop_scope.py tests/planning/test_strategy_branch_table.py tests/planning/test_short_builders.py tests/scripts/test_measure_v104.py tests/market/test_v113_horizon.py tests/market/test_v113_horizon_witness.py`
Expected: all PASS. (`test_stop_scope`/`test_strategy_branch_table` iterate `SHORT_STRATEGIES`; the fade is in scope and routed to `_short_branch` automatically.)

Run: `python -m radon cc -s -n C swingbot/core/market/short_entries.py`
Expected: `fade_frame` not listed.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/strategy_types.py swingbot/core/market/short_entries.py scripts/backtest/measure_v104.py tests/market/test_fade_entries.py
git commit -m "feat(v113): Downtrend Overbought Fade entries -- close under a falling SMA200, RSI(2)>=90, no earnings in 7 bars; short-only, masked

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-8: The fade's plan — fixed 2% stop, `m`×R target, resting-order shape

**Files:**
- Modify: `swingbot/core/planning/short_builders.py` (import `FADE`; new `_fade_plan`; `plan_short`)
- Modify: `swingbot/core/planning/params.py` (`EXIT_V2_PARAMS` and `PLAN_SHAPES` rows)
- Create: `tests/planning/test_fade_builder.py`

**Interfaces:**
- Consumes: `short_entries.FADE`, `structure_at`, `tests.market.test_fade_entries.fade_df`, `HZ` (V113-7); `params.PLAN_SHAPES`, `_bt_plan`, the `limit` simulator (V113-6); `admits` via `gate_override` (V113-2).
- Produces: `plan_short(df, i, FADE, horizon_key, "bearish", entry=close, atr_val=...) -> (entry*1.02, entry - m*0.02*entry, [tp1])`; `PLAN_SHAPES[FADE] = {"entry_type": "limit", "expiry_bars": 1, "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0}`; `EXIT_V2_PARAMS[FADE] = {"trail_atr_mult": 2.5, "tp2": False}`. `run_backtest(..., FADE, "1w", exit_model="v2", ...)` with the cell admitted produces trades V113-10 measures.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_fade_builder.py`:

```python
"""v113 §3: the fade's plan -- sell limit at the signal close, 2% stop, m x R target, 7-bar hold."""
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override
from swingbot.core.market.short_entries import FADE
from swingbot.core.planning import short_builders as sb
from swingbot.core.planning import stop_scope
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.lifecycle import apply_level_lifecycle
from swingbot.core.planning.params import EXIT_V2_PARAMS, PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.market.test_fade_entries import HZ, UNMASKED, fade_df


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)


@pytest.mark.parametrize("m", [1.0, 1.25, 1.5])
def test_plan_short_fixes_the_geometry(monkeypatch, m):
    df, t = fade_df()
    monkeypatch.setitem(DEFAULT_PARAMS[FADE], "m", m)
    entry = float(df["Close"].iloc[t])
    stop, tp1, candidates = sb.plan_short(df, t, FADE, HZ, "bearish", entry=entry, atr_val=1.0)
    assert stop == pytest.approx(entry * 1.02)
    assert tp1 == pytest.approx(entry - m * (stop - entry))
    assert candidates == [tp1]


def test_plan_short_refuses_bullish_and_a_bar_without_a_signal():
    df, t = fade_df()
    assert sb.plan_short(df, t, FADE, HZ, "bullish", entry=float(df["Close"].iloc[t]), atr_val=1.0) is None
    assert sb.plan_short(df, t - 1, FADE, HZ, "bearish",
                         entry=float(df["Close"].iloc[t - 1]), atr_val=1.0) is None


def test_live_builder_emits_the_resting_order_plan():
    df, t = fade_df()
    entry = float(df["Close"].iloc[t])
    plan = build_strategy_plan(df, t, ticker="T", strategy=FADE, horizon_key=HZ, direction="bearish")
    assert (plan.entry_type, plan.expiry_bars, plan.entry_price, plan.status) == ("limit", 1, None, PlanStatus.PENDING)
    assert plan.trigger_price == pytest.approx(entry)
    assert plan.stop_loss == pytest.approx(entry * 1.02) and plan.tp1 == pytest.approx(entry * 0.98)
    assert plan.tp2 is None and plan.tp1_fraction == 1.0 and plan.breakeven_trigger_fraction == 1.0
    assert stop_scope.in_scope(FADE, "bearish")   # v104 fail-closed dollar-risk sizing applies


def test_the_level_lifecycle_never_moves_the_fade(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", True, raising=False)
    df, t = fade_df()
    entry = float(df["Close"].iloc[t])
    stop, tp1 = entry * 1.02, entry * 0.98
    out = apply_level_lifecycle(df, t, entry=entry, stop=stop, tp1=tp1, atr_val=1.0, direction="bearish",
                                strategy=FADE, horizon_key=HZ, candidate_levels=[tp1])
    assert out[:2] == (stop, tp1)


def _trades(df, gates=UNMASKED):
    with gate_override(FADE, gates):
        return run_backtest("T", df, FADE, HZ, exit_model="v2", scale_out=True, tp2_mode="levels").trades


def test_backtest_fills_on_the_next_bar_and_wins_at_one_r():
    df, t = fade_df()
    (trade,) = _trades(df)
    assert trade.entry_date == str(df.index[t].date()) and trade.direction == "bearish"
    assert trade.outcome == "win" and trade.r_multiple == pytest.approx(1.0) and trade.holding_days == 3


def test_a_masked_fade_trades_nothing():
    df, _ = fade_df()
    assert _trades(df, {"directions": ()}) == []


def test_no_trade_when_the_next_bar_never_reaches_the_limit():
    df, t = fade_df()
    close = float(df["Close"].iloc[t])
    df.iloc[t + 1, :4] = [close * 0.97, close * 0.99, close * 0.96, close * 0.975]
    assert _trades(df) == []


def test_the_time_stop_closes_at_the_seventh_bar_after_entry():
    df, _ = fade_df(tail=12, tail_step=0.999)
    (trade,) = _trades(df)
    assert trade.outcome == "timeout" and trade.holding_days == 8


def test_exit_params_and_plan_shape_rows():
    assert EXIT_V2_PARAMS[FADE] == {"trail_atr_mult": 2.5, "tp2": False}
    assert PLAN_SHAPES[FADE] == {"entry_type": "limit", "expiry_bars": 1,
                                 "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0}
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_fade_builder.py`
Expected: FAIL — `plan_short` routes the fade through the ATR-ladder candidates (wrong target); `KeyError: 'Downtrend Overbought Fade'` on `EXIT_V2_PARAMS`/`PLAN_SHAPES`.

- [ ] **Step 3: The builder.** In `swingbot/core/planning/short_builders.py` change `from swingbot.core.market.short_entries import BULL_TRAP, structure_at` to `from swingbot.core.market.short_entries import BULL_TRAP, FADE, structure_at`. Directly above `def plan_short(` add:

```python
def _fade_plan(df, index, horizon_key, entry):
    """v113 A: the fade's fixed geometry, read from the signal bar's frame row --
    stop = entry x 1.02, TP1 = entry - m x (stop - entry). No target selection:
    the spec fixes m (grid {1.0, 1.25, 1.5}, frozen by the pre-registration).
    A stop beyond the horizon's ceiling drops the plan (never capped)."""
    structure = structure_at(FADE, df, index, horizon_key)
    if structure is None or not _valid_stop(FADE, horizon_key, entry, structure["stop"]):
        return None
    tp1 = structure["target_a"]
    return structure["stop"], tp1, [tp1]
```

In `plan_short`, directly after the `if direction != "bearish" or strategy not in SHORT_STRATEGIES: return None` guard, add:

```python
    if strategy == FADE:
        return _fade_plan(df, index, horizon_key, entry)
```

and change its docstring to `"""(stop, tp1, candidates) for a v104 short or the v113 fade at `index`, else None."""`.

- [ ] **Step 4: Exit params and shape.** In `swingbot/core/planning/params.py`, inside `EXIT_V2_PARAMS` after the `"Earnings Gap Drift"` row add:

```python
    # v113 Part A: one whole-position target, no runner, fixed by spec §3.
    "Downtrend Overbought Fade": {"trail_atr_mult": 2.5, "tp2": False},
```

and change `PLAN_SHAPES: dict[str, dict] = {}` to:

```python
PLAN_SHAPES: dict[str, dict] = {
    # v113 §3: sell limit at the signal close, good for one bar; one target for
    # the whole position; no break-even move (amendment 3).
    "Downtrend Overbought Fade": {"entry_type": "limit", "expiry_bars": 1,
                                  "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0},
}
```

- [ ] **Step 5: Run the tests and the neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_fade_builder.py tests/planning/test_short_builders.py tests/planning/test_plan_shape.py tests/planning/test_limit_entry.py tests/market/test_fade_entries.py tests/market/test_v113_horizon_witness.py`
Expected: all PASS. If `test_backtest_fills_on_the_next_bar_and_wins_at_one_r` finds more than one trade, print `_trades(df)` and fix the fixture (not the assertion): a second trade means a second RSI(2) spike, which `fade_df`'s tail must not produce.

Run: `python -m radon cc -s -n C swingbot/core/planning/short_builders.py`
Expected: nothing listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/short_builders.py swingbot/core/planning/params.py tests/planning/test_fade_builder.py
git commit -m "feat(v113): fade plan -- sell limit at the signal close, 2% stop, m x R target, one leg, 7-bar time stop; v104 dollar-risk sizing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-9: `fetch_backtest_data.py --tickers` (fetch the four ETFs without touching the watchlist)

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py` (new `_tickers`; `--tickers`; `main` uses `_tickers`)
- Create: `tests/scripts/test_fetch_backtest_tickers.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `python scripts/data/fetch_backtest_data.py --tickers SH,PSQ,RWM,DOG --start 2010-01-01 --end 2026-09-26` fetches exactly those tickers into `BACKTEST_CACHE_DIR` (V113-12). `_tickers(args) -> list[str]`.

- [ ] **Step 1: Write the failing test** — `tests/scripts/test_fetch_backtest_tickers.py`:

```python
"""v113 §5: --tickers fetches exactly the named tickers, no watchlist, no benchmark."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import fetch_backtest_data as fbd  # noqa: E402

from tests.helpers import make_ohlcv  # noqa: E402


def test_tickers_flag_fetches_only_the_named_tickers(tmp_path, monkeypatch):
    fetched = []

    def fake_fetch(ticker, start, end):
        fetched.append((ticker, start, end))
        return make_ohlcv([10.0] * 300)

    monkeypatch.setattr(fbd, "fetch", fake_fetch)
    monkeypatch.setattr(fbd, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fbd, "cache_path", lambda t: tmp_path / f"{t}.csv")
    monkeypatch.setattr(fbd, "load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(sys, "argv", ["fetch_backtest_data.py", "--tickers", "sh, PSQ,RWM,DOG",
                                      "--start", "2010-01-01", "--end", "2026-09-26"])
    fbd.main()
    assert sorted(t for t, _, _ in fetched) == ["DOG", "PSQ", "RWM", "SH"]
    assert {(s, e) for _, s, e in fetched} == {("2010-01-01", "2026-09-26")}
    assert sorted(p.stem for p in tmp_path.glob("*.csv")) == ["DOG", "PSQ", "RWM", "SH"]


def test_without_the_flag_the_watchlist_and_benchmark_are_used(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(fbd, "load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY", raising=False)
    args = fbd.argparse.Namespace(tickers=None)
    assert fbd._tickers(args) == ["AAPL", "SPY"]
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fetch_backtest_tickers.py`
Expected: FAIL — `error: unrecognized arguments: --tickers` / `AttributeError: ... '_tickers'`.

- [ ] **Step 3: Implement.** In `scripts/data/fetch_backtest_data.py`, directly above `def main():` add:

```python
def _tickers(args) -> list[str]:
    """--tickers wins outright (v113: the four inverse ETFs, never the
    watchlist). Otherwise the watchlist plus the market-context benchmark (P0):
    it is not necessarily on the watchlist, but every backtest that gates on
    regime needs its history cached like any other ticker."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    tickers = load_watchlist()
    from swingbot import config
    benchmark = config.MARKET_REGIME_TICKER
    if benchmark and benchmark not in tickers:
        tickers = list(tickers) + [benchmark]
        print(f"(+ {benchmark}: market-context benchmark, not on the watchlist)")
    return tickers
```

In `main`, after the `--force` argument add:

```python
    ap.add_argument("--tickers", default=None,
                    help="comma-separated tickers to fetch INSTEAD of the watchlist "
                         "(the market-context benchmark is not added)")
```

and replace the block from `tickers = load_watchlist()` through the `print(f"(+ {benchmark}: ...` line (including its comment) with `tickers = _tickers(args)`.

- [ ] **Step 4: Run it**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fetch_backtest_tickers.py`
Expected: 2 passed.

Run: `python -m radon cc -s -n C scripts/data/fetch_backtest_data.py`
Expected: `main` below its previous `C (13)`; `_tickers` not listed.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/fetch_backtest_data.py tests/scripts/test_fetch_backtest_tickers.py
git commit -m "feat(v113): fetch_backtest_data --tickers -- cache named tickers without touching the watchlist

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
