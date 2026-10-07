# v137 Instrument v2, phase 1: one plan constructor. Part 2: parity, diagnostic migration, retirement, full suite (IC4-IC7)

> Index, Global Constraints, Where to work and Parallelisation: `2026-10-06-v137-instrument-v2-one-constructor_0-index.md`. Every task here implicitly includes the index's Global Constraints. Pull one task with `grep -n "^### Task IC<n>" -A 200 docs/superpowers/plans/2026-10-06-v137-instrument-v2-one-constructor_*.md`.

# Phase B (continued): one constructor

### Task IC4: Constructor parity test against the live scan's `build_strategy_plan_at`

**Files:**
- Create: `tests/backtesting/instrument/test_constructor_parity.py`

**Interfaces:**
- Consumes: `bt._live_plan_at`, `bt._signal_masks`, `bt.MIN_BARS`, `bt.simulate_exit`, `run_backtest(..., instrument=)` (IC3); `resolve` (IC2); `swingbot.core.scanning.strategy_pass.build_strategy_plan_at(df_completed, *, ticker, strategy, horizon_key, direction, regime2_state, asof=None)`; `PARITY_CASES`, `load_ohlcv`; `pin_code_defaults`.
- Produces: `CONSTRUCTOR_FIELDS` (the field list phases 2 and 5 extend when they add constructor inputs).

- [ ] **Step 1: Write the test.** It has to pass against IC3 as soon as it is written. It is a regression guard for the spec's parity requirement, so instead of a red step, Step 2 proves it can fail.

```python
"""v136 section 3 / rule 3: under the v2 instrument the backtest's plan IS the live plan.

At sampled signal bars, backtest._live_plan_at (the v2 replay's only constructor
call) must equal what the live scan's strategy_pass.build_strategy_plan_at returns
for the same completed frame, on every constructor field, not only stop and target.
build_strategy_plan_at then adds issuance stamps (cohort, entry context, ledger);
those belong to the scan, which spec phase 5 replays, and are not compared here.
"""
import numpy as np
import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.scanning.strategy_pass import build_strategy_plan_at
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv

CONSTRUCTOR_FIELDS = (
    "ticker", "created_at", "source", "strategy", "horizon_key", "direction",
    "entry_type", "trigger_price", "entry_price", "expiry_bars", "stop_loss", "tp1",
    "tp1_fraction", "tp2", "breakeven_trigger_fraction", "trail_atr_mult",
    "hold_cap_bars", "stop_mult_applied", "tp2_r_applied", "time_stop_days",
    "stall_exit_day", "badge", "badge_stats", "status",
)
SAMPLES_PER_CASE = 12


def _first_case_per_strategy():
    cases = {}
    for case in PARITY_CASES:
        cases.setdefault(case[1], case)
    return list(cases.values())


CASES = _first_case_per_strategy()


def _fields(plan):
    return {name: getattr(plan, name) for name in CONSTRUCTOR_FIELDS}


def _live(df, i, ticker, strategy, horizon, direction):
    return build_strategy_plan_at(df.iloc[:i + 1], ticker=ticker, strategy=strategy,
                                  horizon_key=horizon, direction=direction, regime2_state=None)


def _sampled_signals(df, strategy, horizon):
    bullish, bearish = bt._signal_masks(df, strategy, horizon)
    bars = [int(i) for i in np.where(bullish.values | bearish.values)[0]
            if i >= bt.MIN_BARS[horizon]]
    step = max(1, len(bars) // SAMPLES_PER_CASE)
    return [(i, "bullish" if bullish.values[i] else "bearish") for i in bars[::step]]


def test_cases_cover_every_parity_strategy():
    assert {case[1] for case in CASES} == {case[1] for case in PARITY_CASES}


@pytest.mark.slow
@pytest.mark.parametrize(("ticker", "strategy", "horizon"), CASES)
def test_v2_replay_plan_equals_the_live_constructor_at_sampled_bars(monkeypatch, ticker,
                                                                     strategy, horizon):
    pin_code_defaults(monkeypatch)
    df = load_ohlcv(ticker)
    signals = _sampled_signals(df, strategy, horizon)
    assert signals, f"{ticker}/{strategy}/{horizon} has no signal bar on the fixture"
    built = 0
    for i, direction in signals:
        replay = bt._live_plan_at(df, i, ticker=ticker, strategy=strategy,
                                  horizon_key=horizon, direction=direction)
        live = _live(df, i, ticker, strategy, horizon, direction)
        assert (replay is None) == (live is None), (ticker, strategy, horizon, i)
        if replay is not None:
            assert _fields(replay) == _fields(live), (ticker, strategy, horizon, i)
            built += 1
    assert built, f"no sampled bar built a plan for {ticker}/{strategy}/{horizon}"


def test_run_backtest_v2_simulates_exactly_the_live_plans(monkeypatch):
    """End to end: every plan the v2 replay hands simulate_exit is the live plan
    at that bar (fields snapshotted before the simulator can touch the plan)."""
    pin_code_defaults(monkeypatch)
    ticker, strategy, horizon = "DOCU", "RSI", "4w"
    df = load_ohlcv(ticker)
    seen = []
    real = bt.simulate_exit

    def spy(frame, index, plan, **kwargs):
        seen.append((int(index), plan.direction, _fields(plan)))
        return real(frame, index, plan, **kwargs)

    monkeypatch.setattr(bt, "simulate_exit", spy)
    bt.run_backtest(ticker, df, strategy, horizon, one_at_a_time=False,
                    exit_model="v2", scale_out=True, instrument=resolve("v2"))
    assert seen
    for index, direction, fields in seen:
        live = _live(df, index, ticker, strategy, horizon, direction)
        assert live is not None and fields == _fields(live), index
```

- [ ] **Step 2: Prove the guard can fail.** Temporarily edit `_live_plan_at` in `$WT/swingbot/core/backtesting/backtest.py` so that it drops the signal bar: change `window = df.iloc[:i + 1]` to `window = df.iloc[:i]`. Then:

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_constructor_parity.py`
Expected: FAIL in the sampled-bar cases and the end-to-end test (`created_at` and `trigger_price` now come from bar `i - 1`). If anything passes, the guard is not comparing what it claims to compare: stop and report. **Revert the edit** (`git -C $WT checkout swingbot/core/backtesting/backtest.py`) and confirm `git -C $WT status --short swingbot/` is empty.

- [ ] **Step 3: Run the test on the real code.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_constructor_parity.py`
Expected: `12 passed` (1 coverage test + 10 strategy cases + 1 end-to-end).

- [ ] **Step 4: Commit.**

```bash
git -C $WT add tests/backtesting/instrument/test_constructor_parity.py
git -C $WT commit -m "test(v137): v2 replay plan equals the live scan's build_strategy_plan_at (IC4)"
```

---

### Task IC5: Migrate `measure_fib_diagnostic.py` off `_trade_plan_at`

v101 Phase A is closed, so its committed numbers must not move. The migration calls `build_strategy_plan` on the **full** frame at the same bar, which is the input `_trade_plan_at` had. An equivalence test over every Fibonacci signal bar of the fixture proves the swap is behaviour-neutral before the old function is retired.

**Files:**
- Modify: `scripts/backtest/measure_fib_diagnostic.py`: import line 53; docstrings at lines 172–179 (`trade_features`), 373–389 (`_stop_mismatch`), 395–400 (`_reclaim_result`); functions `_reclaim_result` (393–411) and `_features_for` (414–425)
- Modify: `tests/scripts/test_measure_fib_diagnostic.py`: lines 108–155 (three `_reclaim_result` tests) and 228–244 (the stop-mismatch test); add one test

**Interfaces:**
- Consumes: `swingbot.core.planning.builders.build_strategy_plan`; `bt._trade_plan_at`, `bt._plan_series`, `bt._vectorized_entries`, `bt.MIN_BARS` (still present until IC6); `PARITY_CASES`, `load_ohlcv`; `pin_code_defaults`.
- Produces:
  - `measure_fib_diagnostic._production_plan(frame, idx, direction, horizon_key) -> tuple[float, float, float] | None`, the (entry, stop, target) of the live constructor
  - the new signature `_reclaim_result(frame, i, trade, direction, horizon_key, high, low, close, hold)`. The three series parameters are dropped.

- [ ] **Step 1: Write the failing equivalence test.** Append to `$WT/tests/scripts/test_measure_fib_diagnostic.py`:

```python
def _fib_cases():
    from tests.fixtures.ohlcv_parity import PARITY_CASES
    return [case for case in PARITY_CASES if case[1] == "Fibonacci"]


@pytest.mark.slow
@pytest.mark.parametrize(("ticker", "strategy", "horizon"), _fib_cases())
def test_production_plan_reproduces_the_v1_backtest_plan_at_every_fib_signal(
        monkeypatch, ticker, strategy, horizon):
    """v137 IC5: moving this closed diagnostic off backtest._trade_plan_at onto
    build_strategy_plan must not move v101's numbers. On the full frame at the
    same bar both read the same rolling swings, fib_level_stop_at, lifecycle
    step and reward floor; this pins that on every fixture Fibonacci signal."""
    from swingbot.core.backtesting import backtest as bt
    from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
    from tests.fixtures.ohlcv_parity import load_ohlcv

    pin_code_defaults(monkeypatch)
    mfd = _mfd()
    frame = load_ohlcv(ticker)
    atr_s, sh_s, sl_s, _, _ = bt._plan_series(frame, strategy, horizon)
    bullish, bearish = bt._vectorized_entries(frame, strategy, horizon)
    compared = 0
    for i in np.where(bullish.values | bearish.values)[0]:
        if i < bt.MIN_BARS[horizon]:
            continue
        direction = "bullish" if bullish.values[i] else "bearish"
        expected = bt._trade_plan_at(frame, i, direction, strategy, horizon, atr_s, sh_s, sl_s)
        assert mfd._production_plan(frame, int(i), direction, horizon) == expected, (ticker, horizon, i)
        compared += expected is not None
    assert compared, f"no Fibonacci plan built on {ticker}/{horizon}"
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: the 4 new cases FAIL with `AttributeError: module 'measure_fib_diagnostic' has no attribute '_production_plan'`; the existing tests pass.

- [ ] **Step 3: Migrate the script.** In `$WT/scripts/backtest/measure_fib_diagnostic.py`:

(a) Replace

```python
from swingbot.core.backtesting.backtest import _plan_series, _trade_plan_at, run_backtest  # noqa: E402
```

with

```python
from swingbot.core.backtesting.backtest import _plan_series, run_backtest  # noqa: E402
from swingbot.core.planning.builders import build_strategy_plan  # noqa: E402
```

(b) In `trade_features`'s docstring, replace

```
    `stop_mismatch` is computed by the caller (_features_for) against
    _trade_plan_at's own (stop, target) -- the full production pipeline
    including apply_level_lifecycle -- and passed in so this function stays
    free of the series plumbing _trade_plan_at needs. `reclaim` (I3) is
    computed by the caller too, via `_reclaim_result`, which needs the
    atr/swing_high/swing_low *series* (not just this bar's floats) to call
    _trade_plan_at at the reclaim bar j."""
```

with

```
    `stop_mismatch` is computed by the caller (_features_for) against
    _production_plan's own (stop, target) -- the live constructor, including
    apply_level_lifecycle -- and passed in so this function stays free of
    plan construction. `reclaim` (I3) is computed by the caller too, via
    `_reclaim_result`, which builds the production plan at the reclaim bar j."""
```

(c) In `_stop_mismatch`'s docstring, replace each of the three occurrences of `_trade_plan_at` with `_production_plan`. These are the first line ("does the trade carry _trade_plan_at's own"), "None means _trade_plan_at found no qualifying target", and "_trade_plan_at's unrounded value".

(d) Replace the whole `_reclaim_result` function and `_features_for` with:

```python
def _production_plan(frame, idx, direction, horizon_key):
    """(entry, stop, target) of the live constructor at bar idx, or None when it
    finds no qualifying plan. v137: replaced backtest._trade_plan_at here. On the
    full frame at idx the Fibonacci branch reads the same rolling swings,
    fib_level_stop_at, lifecycle step and reward floor, so v101's numbers do not
    move (tests/scripts/test_measure_fib_diagnostic.py pins the equivalence)."""
    plan = build_strategy_plan(frame, idx, ticker="v101-diagnostic", strategy=STRATEGY,
                               horizon_key=horizon_key, direction=direction)
    return None if plan is None else (plan.trigger_price, plan.stop_loss, plan.tp1)


def _reclaim_result(frame, i, trade, direction, horizon_key, high, low, close, hold):
    """#4 arm: the full production plan at the reclaim bar j -- _production_plan,
    which applies _fibonacci_plan's cap at entry_j and the lifecycle step
    itself (I3; supersedes the plan's "same stop" wording). Invalidated
    first if any bar in (i, j] trades through the bar-i trade's stop: live
    cancels a pending stop-entry plan on that touch (lifecycle.py), so the
    reclaim could never have entered."""
    j = reclaim_bar(high, low, close, i, direction)
    if j is None:
        return "no_reclaim", None
    stop_i, bull = trade.stop_loss, direction == "bullish"
    if any((low[k] <= stop_i) if bull else (high[k] >= stop_i) for k in range(i + 1, j + 1)):
        return "invalidated", None
    plan_at = _production_plan(frame, j, direction, horizon_key)
    if plan_at is None:
        return "no_target", None
    entry_j, stop_j, target_j = plan_at
    return simulate_first_touch(high, low, close, j, entry_j, stop_j, target_j, direction, hold)


def _features_for(frame, horizon_key, trade, series, rr):
    atr_s, sh_s, sl_s = series
    i = frame.index.get_loc(pd.Timestamp(trade.entry_date))
    atr_val = _safe_atr_value(trade.entry, float(atr_s.iloc[i]))
    plan_at = _production_plan(frame, i, trade.direction, horizon_key)
    high, low, close = frame["High"].values, frame["Low"].values, frame["Close"].values
    hold = HORIZONS[horizon_key]["max_holding_days"]
    reclaim = _reclaim_result(frame, i, trade, trade.direction, horizon_key, high, low, close, hold)
    return trade_features(frame, i, horizon_key, trade, atr_val, float(sh_s.iloc[i]), float(sl_s.iloc[i]),
                          cap_distance(trade.entry, horizon_key), *rr, _stop_mismatch(trade, plan_at),
                          reclaim=reclaim)
```

- [ ] **Step 4: Update the four existing tests** in `$WT/tests/scripts/test_measure_fib_diagnostic.py`.

(a) In `test_reclaim_result_is_invalidated_when_a_bar_before_the_reclaim_trades_through_the_stop`, replace

```python
    result = mfd._reclaim_result(None, 0, trade, "bullish", "4w", None, None, None,
                                 high, low, close, 5)
```

with

```python
    result = mfd._reclaim_result(None, 0, trade, "bullish", "4w", high, low, close, 5)
```

(b) Replace the whole `test_reclaim_result_calls_trade_plan_at_the_reclaim_bar_and_simulates_from_there` with:

```python
def test_reclaim_result_builds_the_production_plan_at_the_reclaim_bar_and_simulates_from_there(monkeypatch):
    """I3: the #4 arm is the full production plan at the reclaim bar j
    (_production_plan, which applies _fibonacci_plan's cap at entry_j and the
    lifecycle step itself) -- supersedes the plan's "same stop" wording."""
    mfd = _mfd()
    calls = []

    def fake_production_plan(frame, idx, direction, horizon_key):
        calls.append(idx)
        return 102.0, 99.5, 110.0   # entry_j, capped stop_j, target_j

    monkeypatch.setattr(mfd, "_production_plan", fake_production_plan)
    high = np.array([101, 100, 103, 111.0])
    low = np.array([99, 100, 100, 100.0])
    close = np.array([100, 100, 102.0, 110.0])
    trade = T(stop_loss=90.0)  # far below every bar's low -- never invalidated
    result = mfd._reclaim_result(object(), 0, trade, "bullish", "4w", high, low, close, 5)
    assert calls == [2]   # the reclaim bar, not the signal bar
    assert result == mfd.simulate_first_touch(high, low, close, 2, 102.0, 99.5, 110.0, "bullish", 5)
```

(c) In `test_reclaim_result_is_no_target_when_the_production_plan_finds_none`, replace

```python
    monkeypatch.setattr(mfd, "_trade_plan_at", lambda *a, **kw: None)
```

with

```python
    monkeypatch.setattr(mfd, "_production_plan", lambda *a, **kw: None)
```

and

```python
    result = mfd._reclaim_result(object(), 0, trade, "bullish", "4w", object(), object(), object(),
                                 high, low, close, 5)
```

with

```python
    result = mfd._reclaim_result(object(), 0, trade, "bullish", "4w", high, low, close, 5)
```

(d) Replace the whole `test_features_for_stop_mismatch_is_false_when_trade_carries_trade_plan_ats_own_stop` with:

```python
def test_features_for_stop_mismatch_is_false_when_trade_carries_the_production_plans_own_stop():
    """stop_mismatch compares against _production_plan's own (stop, target) --
    the live constructor, including apply_level_lifecycle -- not the
    pre-lifecycle structural_stop/apply_cap geometry."""
    mfd = _mfd()
    frame, horizon, i = _impulse_frame(), "4w", 44
    atr_s, sh_s, sl_s, _, _ = mfd._plan_series(frame, mfd.STRATEGY, horizon)
    plan_at = mfd._production_plan(frame, i, "bullish", horizon)
    assert plan_at is not None
    entry, stop, target = plan_at
    trade = T(entry_date=str(frame.index[i].date()), direction="bullish", entry=entry,
              stop_loss=stop, take_profit=target, outcome="win", r_multiple=1.0)
    params = mfd.ScanParams.from_config()
    rr = (params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    features = mfd._features_for(frame, horizon, trade, (atr_s, sh_s, sl_s), rr)
    assert features["stop_mismatch"] is False
```

- [ ] **Step 5: Run the tests.**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_fib_diagnostic.py`
Expected: `0 failed, 0 xfailed`, with the four new parametrised cases passing. If an equivalence case fails, stop: the swap is not behaviour-neutral. Report the bar and both tuples. Do not loosen the comparison.

- [ ] **Step 6: Check that no old name is left and that complexity holds.**

Run: `git -C $WT grep -n "_trade_plan_at" -- scripts/backtest/measure_fib_diagnostic.py`
Expected: no output.
Run: `python -m radon cc -s -n C $WT/scripts/backtest/measure_fib_diagnostic.py`
Expected: only `direction_summary` (11) and `collect` (11), unchanged.

- [ ] **Step 7: Commit.**

```bash
git -C $WT add scripts/backtest/measure_fib_diagnostic.py tests/scripts/test_measure_fib_diagnostic.py
git -C $WT commit -m "refactor(v137): measure_fib_diagnostic builds through build_strategy_plan, equivalence pinned (IC5)"
```

---

### Task IC6: Retire `_trade_plan_at`; confine the frozen v1 path

`_trade_plan_at` stops existing. Its arithmetic stays, byte for byte, as `_v1_plan_levels`, private to the frozen v1 instrument (rule 1). A guard test keeps every other caller out.

**Files:**
- Modify (mechanical rename `_trade_plan_at` → `_v1_plan_levels`, word-bounded):
  - `swingbot/core/backtesting/backtest.py`
  - `swingbot/core/market/levels_lifecycle.py`
  - `swingbot/core/planning/builders.py`
  - `swingbot/core/planning/reward_floor.py`
  - `swingbot/core/planning/short_builders.py`
  - `swingbot/core/planning/targets.py`
  - `scripts/backtest/wf_components.py`
  - `scripts/reports/parity_exits.py`
  - `scripts/reports/parity_sizing.py`
  - `tests/backtesting/test_sizing_parity.py`
  - `tests/backtesting/test_compression_reachability.py`
  - `tests/market/test_levels_lifecycle_wiring.py`
  - `tests/edge/test_edge_stops.py`
  - `tests/scripts/test_measure_fib_diagnostic.py` (IC5's equivalence test)
  - `tests/backtesting/instrument/test_live_constructor_replay.py` (IC3's `_forbidden` monkeypatch)
  - `docs/claude/testing-cost.md`
- Modify (hand-written prose, Step 3): `backtest.py` (`_v1_plan_levels` docstring), `levels_lifecycle.py` (WIRING NOTE), `builders.py` (level-lifecycle comment block), `wf_components.py` (the `DATA_DRIVEN_STOPS_ENABLED` reason), `docs/claude/testing-cost.md`, `docs/claude/architecture.md`
- Create: `tests/backtesting/instrument/test_one_constructor_guard.py`
- Not touched: `tests/fixtures/legacy_trade_plan_at.py` (a frozen historical copy whose docstring describes history; the guard scans only `swingbot/` and `scripts/`), and every file under `docs/superpowers/` (history).

**Interfaces:**
- Consumes: `_live_plan_at`, `_replay_live_constructor` (IC3); `_production_plan` (IC5).
- Produces: `backtest._v1_plan_levels(df, i, direction, strategy, horizon_key, atr_series, swing_high_series=None, swing_low_series=None, volume_ratio_series=None, entry_levels=None) -> tuple[float, float, float] | None`. It has the same signature and body as the old `_trade_plan_at`.

- [ ] **Step 1: Write the failing guard test**, `$WT/tests/backtesting/instrument/test_one_constructor_guard.py`:

```python
"""v136 rule 3: one plan constructor.

`_trade_plan_at` is gone from production code. The frozen v1 instrument keeps
its arithmetic as `_v1_plan_levels`, reachable only from run_backtest's v1 loop
and the two v1 parity reports. Inside backtest.py, plans are constructed in
exactly two places: `_bt_plan` (v1) and `_live_plan_at` (v2, via
build_strategy_plan).
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKTEST = ROOT / "swingbot" / "core" / "backtesting" / "backtest.py"
RETIRED = re.compile(r"(?<![A-Za-z0-9_])_trade_plan_at(?![A-Za-z0-9_])")
V1_ONLY = "_v1_plan_levels"
V1_CALLERS = {
    "swingbot/core/backtesting/backtest.py",
    "scripts/reports/parity_exits.py",
    "scripts/reports/parity_sizing.py",
}


def _sources():
    for top in ("swingbot", "scripts"):
        for path in sorted((ROOT / top).rglob("*.py")):
            yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8", errors="replace")


def _references(text, name):
    """True when code (not a comment or string) names `name`: a bare name, an
    attribute, or an import alias. Prose in comments may mention the v1 path."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.alias) and node.name == name:
            return True
    return False


def _callers_by_name(path):
    """{called bare name: {enclosing top-level function names}} for one module."""
    found = {}
    for fn in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                found.setdefault(node.func.id, set()).add(fn.name)
    return found


def test_the_retired_constructor_name_is_gone_from_production_code():
    assert [rel for rel, text in _sources() if RETIRED.search(text)] == []


def test_only_frozen_v1_code_reaches_the_v1_plan_path():
    assert [rel for rel, text in _sources()
            if rel not in V1_CALLERS and _references(text, V1_ONLY)] == []


def test_backtest_constructs_plans_in_exactly_two_places():
    calls = _callers_by_name(BACKTEST)
    assert calls.get("TradePlanV2") == {"_bt_plan"}
    assert calls.get("build_strategy_plan") == {"_live_plan_at"}
    assert calls.get("_bt_plan") == {"run_backtest"}
    assert calls.get("_v1_plan_levels") == {"run_backtest"}
    assert calls.get("_live_plan_at") == {"_replay_live_constructor"}
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_one_constructor_guard.py`
Expected: FAIL. The first test lists the production files that still name `_trade_plan_at`, and the third fails on `_v1_plan_levels` being absent.

- [ ] **Step 3: Rename mechanically.** The pattern is word-bounded, so `legacy_trade_plan_at` and `trade_plan_ats` are left alone:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v137-instrument-v2-one-constructor
perl -pi -e 's/(?<![A-Za-z0-9_])_trade_plan_at(?![A-Za-z0-9_])/_v1_plan_levels/g' \
  $WT/swingbot/core/backtesting/backtest.py \
  $WT/swingbot/core/market/levels_lifecycle.py \
  $WT/swingbot/core/planning/builders.py \
  $WT/swingbot/core/planning/reward_floor.py \
  $WT/swingbot/core/planning/short_builders.py \
  $WT/swingbot/core/planning/targets.py \
  $WT/scripts/backtest/wf_components.py \
  $WT/scripts/reports/parity_exits.py \
  $WT/scripts/reports/parity_sizing.py \
  $WT/tests/backtesting/test_sizing_parity.py \
  $WT/tests/backtesting/test_compression_reachability.py \
  $WT/tests/market/test_levels_lifecycle_wiring.py \
  $WT/tests/edge/test_edge_stops.py \
  $WT/tests/scripts/test_measure_fib_diagnostic.py \
  $WT/tests/backtesting/instrument/test_live_constructor_replay.py \
  $WT/docs/claude/testing-cost.md
git -C $WT grep -nw "_trade_plan_at" -- swingbot scripts tests docs/claude
```

Expected from the final grep: hits **only** in `docs/claude/backtest-methodology.md` (its two history rows). **Leave those rows alone**: they record what happened under that name. `tests/fixtures/legacy_trade_plan_at.py` and the `legacy_trade_plan_at` symbol are not matched (`-w`). Any other hit is a missed file: add it to the perl list and re-run.

- [ ] **Step 4: Rewrite the prose that the rename made inaccurate.**

(a) `$WT/swingbot/core/backtesting/backtest.py`: replace `_v1_plan_levels`'s docstring (the text from `"""Sizing lives in plan_engine (single source of truth shared with live` through `at this bar, not a crash."""`) with:

```python
    """(entry, stop, target) for the FROZEN v1 instrument, or None.

    v136 rule 3 retired this as a plan constructor (it was `_trade_plan_at`
    until v137): every replay under the v2 instrument builds through
    builders.build_strategy_plan (`_live_plan_at`). It survives only because v1
    must stay byte-identical until the v136 cutover. It differs from the live
    builder by design: no journal-resolved stop_mult/TP2, no opex widening, no
    level_map, and series precomputed once on the full frame. Callers:
    run_backtest's v1 loop and the two v1 parity reports in scripts/reports/;
    tests/backtesting/instrument/test_one_constructor_guard.py keeps it that way.
    Do not change its arithmetic, because test_v1_golden.py pins its output. Sizing itself
    lives in plan_engine (shared with live); this only picks the branch from the
    precomputed series. Returns None when the chosen builder finds no target
    that clears MIN_RISK_REWARD_RATIO -- no qualifying setup at this bar."""
```

Do not touch the function body.

(b) `$WT/swingbot/core/market/levels_lifecycle.py`: replace the WIRING NOTE paragraph (from `There are two plan paths: \`backtest._v1_plan_levels\` (what the backtest sizes` through `construction.`) with:

```
There are two plan paths: `backtest._v1_plan_levels` (the frozen v1 backtest
instrument) and `builders.build_strategy_plan` (what live builds through, and,
since v137, what every replay under the v2 backtest instrument builds through).
edge-engine-v4's `DATA_DRIVEN_STOPS_ENABLED` scored exactly 0.0000 and burned
its pre-registered validation shot because it reached only the second one.
Until the v136 cutover retires v1, any consumer added here must be routed
through BOTH or the v1 numbers cannot see it.
```

(c) `$WT/swingbot/core/planning/builders.py`: replace the comment block under `# --- level lifecycle (P1) ---` (from `# Deliberately lives HERE, next to the sizing builders, and not in either` through `# it is unmeasurable by construction.`) with:

```python
# Deliberately lives HERE, next to the sizing builders, and not in either
# caller. backtest._v1_plan_levels (the frozen v1 backtest instrument) and
# build_strategy_plan are two separate plan paths, and edge-engine-v4's
# DATA_DRIVEN_STOPS_ENABLED scored exactly 0.0000 -- burning its one
# pre-registered validation shot -- because it reached only
# build_strategy_plan while the backtest sized through the v1 path. Under the
# v2 instrument (v137) every replay builds through build_strategy_plan; until
# the v136 cutover anything that touches stop/target must still be shared by
# both or the v1 numbers cannot see it.
```

(d) `$WT/scripts/backtest/wf_components.py`: replace the `"DATA_DRIVEN_STOPS_ENABLED":` reason string (the three lines beginning `"E31/E32 reach plan_engine.build_strategy_plan only; the backtest "`) with:

```python
        "E31/E32 reach plan_engine.build_strategy_plan only; the v1 "
        "backtest instrument sizes through backtest._v1_plan_levels, which "
        "takes no stop_mult/tp2_r. Measurable only under the v2 instrument "
        "(v136/v137), where run_backtest builds through build_strategy_plan.",
```

(e) `$WT/docs/claude/testing-cost.md`: after the rename, the paragraph begins "`test_sizing_parity.py` compares the current `backtest._v1_plan_levels` against". Change it to "the current `backtest._v1_plan_levels` (the frozen v1 instrument's plan path, `_trade_plan_at` until v137) against". Leave the rest of the paragraph alone.

(f) `$WT/docs/claude/architecture.md`: in the Plan Engine v2 bullet, replace

```
  `swingbot/core/backtesting/backtest.py run_backtest(..., exit_model="v2",
  scale_out=True)` uses the same simulator, so live behavior equals
  backtested behavior.
```

with

```
  `swingbot/core/backtesting/backtest.py run_backtest(..., exit_model="v2",
  scale_out=True)` uses the same simulator, so live behavior equals
  backtested behavior. Plans: under `instrument=resolve("v2")`
  (`backtesting/instrument/contract.py`, v136/v137) every plan is built by
  `builders.build_strategy_plan` on the frame truncated at the signal bar; the
  v1 instrument (the default until the v136 cutover) keeps its frozen
  `_v1_plan_levels` path, pinned by `tests/backtesting/instrument/test_v1_golden.py`.
```

- [ ] **Step 5: Run the guard, the golden, and the renamed tests.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_one_constructor_guard.py`
Expected: `3 passed`.
Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed, 0 xfailed`. The selection includes the golden, `test_sizing_parity.py`, `test_levels_lifecycle_wiring.py`, `test_edge_stops.py`, `test_compression_reachability.py`, `test_measure_fib_diagnostic.py` and the IC3/IC4 instrument tests.

- [ ] **Step 6: Check the Codex mirror.** The edits to `docs/claude/` change detail that the condensed `AGENTS.md` does not carry.

Run: `git -C $WT grep -n "_trade_plan_at\|_v1_plan_levels" -- AGENTS.md`
Expected: no output.
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: `0 failed`.

- [ ] **Step 7: Complexity.**

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/backtest.py $WT/scripts/reports/parity_exits.py $WT/scripts/reports/parity_sizing.py`
Expected: `run_backtest` at IC3's value, `run_backtest_daterange` 25, `_v1_plan_levels` 13, `parity_exits.main` 21, `parity_sizing.main` 18. Nothing new and nothing higher.

- [ ] **Step 8: Commit.**

```bash
git -C $WT add -A swingbot scripts tests docs/claude
git -C $WT status --short   # confirm only the files listed in this task
git -C $WT commit -m "refactor(v137): retire _trade_plan_at -- v1 keeps its frozen arithmetic as _v1_plan_levels, guarded (IC6)"
```

---

# Phase C: verification

### Task IC7: Full-suite verification

**Files:** none modified.

**Interfaces:**
- Consumes: everything from IC1–IC6.
- Produces: a green full run on the branch head, recorded in the task report and quoted in the merge commit.

- [ ] **Step 1: Run the full suite through the `test-runner` subagent**, so that none of its output lands in the controller's context. Point it at the worktree:

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v137-instrument-v2-one-constructor/scripts/dev/testrun.py full`
Expected: `0 failed, 0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Hand any failure to `superpowers:systematic-debugging`. Never regenerate the v1 golden to turn the run green.

- [ ] **Step 2: Run the syntax pass and the complexity pass over every touched module.**

```bash
python -m py_compile $WT/swingbot/core/backtesting/backtest.py $WT/swingbot/core/backtesting/instrument/contract.py $WT/scripts/backtest/measure_fib_diagnostic.py $WT/scripts/backtest/wf_components.py $WT/scripts/reports/parity_exits.py $WT/scripts/reports/parity_sizing.py
python -m radon cc -s -n C $WT/swingbot/core/backtesting/backtest.py $WT/swingbot/core/backtesting/instrument/contract.py $WT/scripts/backtest/measure_fib_diagnostic.py
```

Expected: `py_compile` is silent. In radon, the only functions listed are the legacy ones named in Global Constraints, each at or below its recorded value.

- [ ] **Step 3: Confirm the main tree is untouched and the branch is clean.**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: the main tree shows only what it showed before IC1. The worktree is clean. Six commits, IC1–IC6. Report the full-suite verdict line together with these. Merging, the `bot` minor bump and close-out belong to the controller (`/close-out`).
