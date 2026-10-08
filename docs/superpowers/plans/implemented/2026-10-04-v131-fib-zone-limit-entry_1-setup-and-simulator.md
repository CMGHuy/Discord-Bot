# v131 Fibonacci Limit — Part 1: witness, setup function, simulator

Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-04-v131-fib-zone-limit-entry_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-10-04-v131-fib-zone-limit-entry-design.md`.

All of Part 1 runs in the worktree `.claude/worktrees/2026-10-04-v131-fib-zone-limit-entry` on branch `2026-10-04-v131-fib-zone-limit-entry` (`<worktree>` below is its absolute path). Paths in **Files:** are relative to that worktree; pass absolute worktree paths to every tool. `python <worktree>/scripts/dev/testrun.py file <test path>` runs against the worktree (testrun resolves the repo from its own location), so `python scripts/dev/testrun.py ...` below always means the worktree's copy.

# Phase 0 — Byte-identity witness (sequential, alone)

### Task V131-01: Byte-identity witness for every existing strategy, golden written before any change

**Files:**
- Create: `tests/backtesting/test_v131_witness.py`
- Create: `tests/fixtures/v131/witness.json` (generated, ~140 KB)

**Interfaces:**
- Consumes: `backtest.ALL_STRATEGIES`, `run_backtest`, `entry_filters.entries_for`, `gate_override`, `strategy_types.FADE_STRATEGY`, `V104_SHORTS`, `builders.build_strategy_plan`, `plan_types.plan_to_dict`, `tests.backtesting.test_v74_fixture.load_v74_fixture`, `tests.market.test_fib_sr_confluence._trending_frame` (all exist on `main`).
- Produces: `snapshot()`, `write_golden()` and the committed golden that V131-02 … V131-05 must keep green.

- [ ] **Step 1: Create the worktree** (load `worktree-lifecycle` first):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-04-v131-fib-zone-limit-entry -b 2026-10-04-v131-fib-zone-limit-entry main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-04-v131-fib-zone-limit-entry status --short
```

Expected: the second command prints nothing. Every later command in Phases 0–3 runs with `-C <worktree>` or absolute worktree paths.

- [ ] **Step 2: Write the witness test.** Create `tests/backtesting/test_v131_witness.py`:

```python
"""v131 byte-identity witness: with no `limit_price` plan-shape key, every
existing strategy builds the plans and backtest trades it built before v131.

tests/fixtures/v131/witness.json was written by write_golden() on main BEFORE
any v131 code change (plan task V131-01). Never regenerate it to make this
test pass -- a diff here is a behaviour change v131 promised not to make.
"""
import dataclasses
import json
from pathlib import Path

import pytest

from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.market.entry_filters import entries_for, gate_override
from swingbot.core.market.strategy_types import FADE_STRATEGY, V104_SHORTS
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.plan_types import plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.market.test_fib_sr_confluence import _trending_frame

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v131" / "witness.json"
STRATEGIES = ALL_STRATEGIES + V104_SHORTS + (FADE_STRATEGY,)
HORIZONS_UNDER_TEST = ("1w", "2w", "4w", "2m")
# Every strategy unmasked in both directions, 1w admitted too, so masked
# strategies (the v104 shorts, the v113 fade) are witnessed as well.
OPEN_GATES = {"cells": frozenset({("bullish", "1w"), ("bearish", "1w")})}
# The plan fields that decide how a plan trades. plan_id is random and the
# badge fields follow the registry, so neither belongs in a behaviour witness.
PLAN_KEYS = ("created_at", "direction", "entry_type", "trigger_price", "entry_price",
             "expiry_bars", "stop_loss", "tp1", "tp1_fraction", "tp2",
             "breakeven_trigger_fraction", "trail_atr_mult", "hold_cap_bars", "status",
             "stop_mult_applied", "tp2_r_applied", "time_stop_days", "stall_exit_day")


def _frames():
    frames = dict(load_v74_fixture())
    frames["UP"] = _trending_frame(400, 0.06, seed=2)
    frames["DN"] = _trending_frame(400, -0.06, seed=11)
    return frames


def _plan_rows(symbol, frame, strategy, horizon):
    rows = []
    bullish, bearish = entries_for(strategy, frame, horizon)
    for direction, mask in (("bullish", bullish), ("bearish", bearish)):
        for index in [int(i) for i in mask.to_numpy().nonzero()[0]]:
            plan = build_strategy_plan(frame, index, ticker=symbol, strategy=strategy,
                                       horizon_key=horizon, direction=direction)
            if plan is None:
                rows.append([symbol, strategy, horizon, direction, index, None])
                continue
            record = plan_to_dict(plan)
            rows.append([symbol, strategy, horizon, direction, index,
                         [record[key] for key in PLAN_KEYS]])
    return rows


def _trade_rows(symbol, frame, strategy, horizon):
    summary = run_backtest(symbol, frame, strategy, horizon, exit_model="v2",
                           scale_out=True, tp2_mode="levels")
    # context is entry_context's feature snapshot -- v131 does not touch it, and
    # it is most of the bytes; every priced and scored field is kept.
    return [[symbol, strategy, horizon,
             {k: v for k, v in dataclasses.asdict(trade).items() if k != "context"}]
            for trade in summary.trades]


def snapshot() -> dict:
    plans, trades = [], []
    for symbol, frame in _frames().items():
        for strategy in STRATEGIES:
            with gate_override(strategy, OPEN_GATES):
                for horizon in HORIZONS_UNDER_TEST:
                    plans.extend(_plan_rows(symbol, frame, strategy, horizon))
                    trades.extend(_trade_rows(symbol, frame, strategy, horizon))
    # One JSON round trip so the comparison sees exactly what the file stores.
    return json.loads(json.dumps({"plans": plans, "trades": trades}, default=str))


def write_golden() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(snapshot(), separators=(",", ":"), default=str), encoding="utf-8")


def test_golden_is_not_vacuous():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden["trades"]) >= 200
    assert sum(1 for row in golden["plans"] if row[5] is not None) >= 200


def test_existing_strategies_build_the_pre_v131_plans_and_trades():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = snapshot()
    assert now["trades"] == golden["trades"]
    assert len(now["plans"]) == len(golden["plans"])
    for current, before in zip(now["plans"], golden["plans"]):
        assert current == before, current[:5]
```

- [ ] **Step 3: Confirm the branch head is untouched, then write the golden.** `git -C <worktree> diff --stat main` must print nothing (no v131 code yet). Then:

```bash
python -c "import sys; sys.path.insert(0, r'<worktree>'); from tests.backtesting.test_v131_witness import write_golden; write_golden()"
```

The `sys.path.insert(0, ...)` makes both `tests` and `swingbot` resolve to the worktree, not the main tree; the command takes ~30 s. Expected: `tests/fixtures/v131/witness.json` exists, about 140 KB, and

```bash
python -c "import json; g=json.load(open(r'<worktree>/tests/fixtures/v131/witness.json')); print(len(g['trades']), len(g['plans']), sum(1 for r in g['plans'] if r[5]))"
```

prints three numbers, each ≥ 200 (measured while writing this plan: `286 361 309`).

- [ ] **Step 4: Run it.** `python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py` (from the worktree). Expected: 2 passed (~30 s; the file is in the `slow` tier).

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add tests/backtesting/test_v131_witness.py tests/fixtures/v131/witness.json
git -C <worktree> commit -m "test(v131): byte-identity witness for every existing strategy's plans and v2 trades, golden written before any v131 change

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 1 — Group 1 (parallel): setup function, simulator

### Task V131-02: `fibonacci_limit_setups` — arming rule, order book, frozen limit and cancel prices

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (insert after line 427, `ENTRY_FUNCS["Fibonacci Continuation"] = fib_continuation_entries`)
- Create: `tests/market/test_fib_limit_setups.py`

**Interfaces:**
- Consumes (all exist in `entry_filters.py`): `HORIZONS`, `DEFAULT_PARAMS`, `_params(strategy, params)`, `_rolling_argmax_pos(s, lookback)`, `_rolling_argmin_pos(s, lookback)`, `compute_shared_gates(df)` (keys `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`).
- Produces:
  - `DEFAULT_PARAMS["Fibonacci Limit"] = {"L": 0.618, "N": 5}`; `FIB_LIMIT_MIN_RETRACE = 0.236`; `FIB_LIMIT_MIN_AGE = 3`.
  - `fib_limit_anchors(df, horizon_key) -> pd.DataFrame` — columns `swing_high`, `swing_low`, `swing_high_idx` (absolute bar position, float), `up_leg` (bool).
  - `fibonacci_limit_setups(df, horizon_key, params=None) -> pd.DataFrame` — columns `arm` (bool), `swing_high`, `swing_low`, `swing_high_idx`, `limit_price`.
  - `fib_limit_price_at(df, index, horizon_key, direction, params=None) -> float | None` (the spec's limit-price function).
  - `fib_limit_cancel_at(df, index, horizon_key, direction) -> float | None`.
  - private: `_fib_limit_candidates(df, anchors, ratio)`, `_order_after_bar(order, t, bar_low, bar_high, life)`, `_arm_orders(candidate, leg, low, high, limit, cancel, life) -> np.ndarray`, `_fib_limit_row(df, index, horizon_key)`.
  - The strategy name is the literal `"Fibonacci Limit"` here; V131-05 introduces the `FIB_LIMIT` constant and the entry function.

- [ ] **Step 1: Load the `no-lookahead` skill** and keep its checklist open for Steps 4 and 6.

- [ ] **Step 2: Write the failing tests.** Create `tests/market/test_fib_limit_setups.py`:

```python
"""v131: the Fibonacci Limit arming rule (entry_filters.fibonacci_limit_setups)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from tests.helpers import make_ohlcv
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "4w"                                   # fib_lookback 42: the whole leg stays in the window
PAD = [(100.8, 101.0, 100.6, 100.8)] * 50
IMPULSE = [(100.2, 100.8, 100.0, 100.6), (102.0, 103.5, 101.8, 103.0),
           (105.0, 106.5, 104.8, 106.0), (107.5, 109.0, 107.3, 108.5),
           (109.0, 110.0, 108.8, 109.6)]    # swing low 100.0 at bar 50, swing high 110.0 at bar 54
HIGH_BAR = len(PAD) + len(IMPULSE) - 1      # 54
CELL = {"L": 0.618, "N": 3}


def _pull(closes):
    """Pullback bars that never trade below the 0.618 limit (103.82) or above 110."""
    return [(c + 0.3, c + 0.5, c - 0.2, c) for c in closes]


def _open_gates(df):
    on = pd.Series(True, index=df.index)
    return {"bull_regime": on, "trend50_bull": on, "atr_floor": on, "atr_calm": on}


@pytest.fixture
def gates_open(monkeypatch):
    """Hand-built frames are too short for MA200; the gates get their own test."""
    monkeypatch.setattr(ef, "compute_shared_gates", _open_gates)


def _arms(bars, params=CELL):
    frame = make_ohlcv(bars, start="2015-01-02")
    return [int(i) for i in np.nonzero(ef.fibonacci_limit_setups(frame, HZ, params)["arm"].to_numpy())[0]]


def test_arms_at_a_0_3_retracement_three_bars_after_the_high(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 107.0])
    frame = make_ohlcv(bars, start="2015-01-02")
    setups = ef.fibonacci_limit_setups(frame, HZ, CELL)
    assert _arms(bars) == [HIGH_BAR + 3]
    row = setups.iloc[HIGH_BAR + 3]
    assert (row["swing_high"], row["swing_low"], row["swing_high_idx"]) == (110.0, 100.0, HIGH_BAR)
    assert row["limit_price"] == pytest.approx(110.0 - 0.618 * 10.0)


@pytest.mark.parametrize("closes", [
    [109.2, 108.6, 103.5, 103.5, 103.5],    # retracement 0.65 >= L
    [109.2, 108.6, 108.0, 108.0, 108.0],    # retracement 0.20 < 0.236
    [109.2, 108.6, 107.7, 107.7, 107.7],    # retracement 0.23 < 0.236
])
def test_does_not_arm_outside_the_zone(gates_open, closes):
    assert _arms(PAD + IMPULSE + _pull(closes)) == []


def test_arms_just_inside_the_shallow_edge(gates_open):
    assert _arms(PAD + IMPULSE + _pull([109.2, 108.6, 107.6])) == [HIGH_BAR + 3]


def test_does_not_arm_while_the_swing_high_is_under_three_bars_old(gates_open):
    assert _arms(PAD + IMPULSE + _pull([107.0, 107.0])) == []
    assert _arms(PAD + IMPULSE + _pull([107.0, 107.0, 107.0])) == [HIGH_BAR + 3]


def test_the_shallower_limit_shrinks_the_zone(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 104.5])        # retracement 0.55
    assert _arms(bars, {"L": 0.618, "N": 3}) == [HIGH_BAR + 3]
    assert _arms(bars, {"L": 0.5, "N": 3}) == []


def test_does_not_re_arm_the_same_leg_after_the_order_expires(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 107.0]) + _pull([107.0] * 8)
    assert _arms(bars) == [HIGH_BAR + 3]


def test_no_second_arm_while_an_order_is_live(gates_open):
    """A new leg whose high stays under the old one cannot appear here, so pin
    the order book directly: the leg changes but the first order is live."""
    candidate = np.array([True, True, True, True])
    leg = np.array([10.0, 11.0, 12.0, 13.0])
    low = np.full(4, 105.0)
    high = np.full(4, 108.0)
    limit = np.full(4, 104.0)
    cancel = np.full(4, 110.0)
    # Armed at 0 with life 2: live for bars 1 and 2, gone after bar 2's close,
    # so bar 2's close may arm again; that order is live through bar 4.
    assert list(ef._arm_orders(candidate, leg, low, high, limit, cancel, 2)) == [
        True, False, True, False]


@pytest.mark.parametrize("low, high, expect_free", [
    (103.9, 108.0, True),     # Low < limit: filled, no longer a resting order
    (104.0, 108.0, False),    # an exact touch does not fill
    (105.0, 110.1, True),     # High > swing high: cancelled
    (105.0, 110.0, False),    # an equal high does not cancel
])
def test_order_book_fill_and_cancel_edges(low, high, expect_free):
    order = (0, 104.0, 110.0)
    after = ef._order_after_bar(order, 1, low, high, 5)
    assert (after is None) is expect_free


def test_re_arms_on_a_new_leg(gates_open):
    leg_one = PAD + IMPULSE + _pull([109.2, 108.6, 107.0]) + _pull([107.0] * 8)
    new_high = [(110.5, 111.0, 110.2, 110.8)]
    leg_two = new_high + _pull([110.2, 109.5, 107.7]) + _pull([107.7] * 2)
    second_high = len(leg_one)
    assert _arms(leg_one + leg_two) == [HIGH_BAR + 3, second_high + 3]
    frame = make_ohlcv(leg_one + leg_two, start="2015-01-02")
    row = ef.fibonacci_limit_setups(frame, HZ, CELL).iloc[second_high + 3]
    assert (row["swing_high"], row["swing_low"], row["swing_high_idx"]) == (111.0, 100.0, second_high)


def test_gates_block_the_arm_on_real_indicators():
    frame = _trending_frame(400, 0.06, seed=2)
    setups = ef.fibonacci_limit_setups(frame, "2w")
    gates = ef.compute_shared_gates(frame)
    allowed = gates["bull_regime"] & gates["trend50_bull"] & gates["atr_floor"] & gates["atr_calm"]
    assert setups["arm"].any(), "fixture must arm for this to mean anything"
    assert not (setups["arm"] & ~allowed).any()


@pytest.mark.parametrize("horizon", ["2w", "4w"])
def test_truncation_invariance_every_cut(horizon):
    """No lookahead: row t of the full-frame result equals the last row of the
    result on df.iloc[:t+1], for every t."""
    frame = _trending_frame(300, 0.06, seed=2)
    full = ef.fibonacci_limit_setups(frame, horizon)
    for t in range(len(frame)):
        cut = ef.fibonacci_limit_setups(frame.iloc[:t + 1], horizon).iloc[-1]
        pd.testing.assert_series_equal(cut, full.iloc[t], check_names=False)


@pytest.mark.parametrize("horizon", ["2w", "4w"])
def test_price_and_cancel_functions_match_the_setup_frame(horizon):
    frame = _trending_frame(300, 0.06, seed=2)
    setups = ef.fibonacci_limit_setups(frame, horizon)
    for t in np.nonzero(setups["arm"].to_numpy())[0]:
        t = int(t)
        assert ef.fib_limit_price_at(frame, t, horizon, "bullish") == pytest.approx(
            setups["limit_price"].iloc[t])
        assert ef.fib_limit_cancel_at(frame, t, horizon, "bullish") == setups["swing_high"].iloc[t]
        # truncation: the frozen prices read bars <= t only
        assert ef.fib_limit_price_at(frame.iloc[:t + 1], t, horizon, "bullish") == pytest.approx(
            setups["limit_price"].iloc[t])


def test_price_function_is_bullish_only_and_refuses_a_short_window():
    frame = _trending_frame(300, 0.06, seed=2)
    assert ef.fib_limit_price_at(frame, 250, "2w", "bearish") is None
    assert ef.fib_limit_cancel_at(frame, 250, "2w", "bearish") is None
    assert ef.fib_limit_price_at(frame, 5, "2w", "bullish") is None
```

- [ ] **Step 3: Run to verify it fails.** `python scripts/dev/testrun.py file tests/market/test_fib_limit_setups.py`. Expected: FAIL — `AttributeError: module ... has no attribute 'fibonacci_limit_setups'` (and `_arm_orders`, `_order_after_bar`, `fib_limit_price_at`).

- [ ] **Step 4: Implement.** In `swingbot/core/market/entry_filters.py`, directly after line 427 (`ENTRY_FUNCS["Fibonacci Continuation"] = fib_continuation_entries`), insert:

```python


# --- v131: Fibonacci Limit -- a resting buy limit inside the retracement zone --
#
# Armed at the close of bar t, from bars <= t only, while the pullback is still
# above the order. Bullish only. Masked in STRATEGY_GATES; the v131 measurement
# unmasks it through gate_override. The plan side (entry at the limit, stop and
# target priced from it) lives in planning/builders.py.

DEFAULT_PARAMS["Fibonacci Limit"] = {
    "L": 0.618,   # limit sits L of the leg below the swing high; grid {0.5, 0.618}
    "N": 5,       # order life in bars after t; grid {3, 5, 10}; == PLAN_SHAPES expiry_bars
}
FIB_LIMIT_MIN_RETRACE = 0.236   # the close must already be this deep into the leg
FIB_LIMIT_MIN_AGE = 3           # the swing-high bar is at least this many bars old


def fib_limit_anchors(df, horizon_key):
    """Rolling swing anchors at each bar -- the same rolling `fib_lookback`
    max High / min Low fibonacci_entries uses -- plus the swing-high bar's
    absolute position (the leg's identity) and whether the low came first.
    Trailing windows only: row t reads bars <= t."""
    lookback = HORIZONS[horizon_key]["fib_lookback"]
    high, low = df["High"], df["Low"]
    hi_pos = _rolling_argmax_pos(high, lookback)
    lo_pos = _rolling_argmin_pos(low, lookback)
    bar = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    return pd.DataFrame({
        "swing_high": high.rolling(lookback).max(),
        "swing_low": low.rolling(lookback).min(),
        "swing_high_idx": bar - (lookback - 1) + hi_pos,
        "up_leg": hi_pos > lo_pos,
    }, index=df.index)


def _fib_limit_candidates(df, anchors, ratio):
    """Conditions 1-4 of the v131 arming rule, per bar (no order bookkeeping)."""
    gates = compute_shared_gates(df)
    leg = anchors["swing_high"] - anchors["swing_low"]
    retrace = (anchors["swing_high"] - df["Close"]) / leg.where(leg > 0)
    age = pd.Series(np.arange(len(df), dtype=float), index=df.index) - anchors["swing_high_idx"]
    ok = (anchors["up_leg"] & (age >= FIB_LIMIT_MIN_AGE)
          & (retrace >= FIB_LIMIT_MIN_RETRACE) & (retrace < ratio)
          & gates["bull_regime"] & gates["trend50_bull"]
          & gates["atr_floor"] & gates["atr_calm"])
    return ok.fillna(False).astype(bool)


def _order_after_bar(order, t, bar_low, bar_high, life):
    """The resting order still live after bar t's close, else None: it filled
    (Low < limit, strictly), cancelled (High > the frozen swing high) or
    reached the end of its `life` bars. Reads bar t only."""
    if order is None:
        return None
    armed_at, limit, cancel = order
    done = bar_low < limit or bar_high > cancel or t - armed_at >= life
    return None if done else order


def _arm_orders(candidate, leg, low, high, limit, cancel, life):
    """Walk the bars in order. Arm at t when conditions 1-4 hold, no order is
    live and this leg (its swing-high bar) has never armed -- an expired or
    cancelled order never re-arms the same leg. The live-order state at t is
    built from bars <= t, so the mask is causal."""
    arm = np.zeros(len(candidate), dtype=bool)
    armed_legs = set()
    order = None
    for t in range(len(candidate)):
        order = _order_after_bar(order, t, low[t], high[t], life)
        if order is None and candidate[t] and leg[t] not in armed_legs:
            arm[t] = True
            armed_legs.add(leg[t])
            order = (t, limit[t], cancel[t])
    return arm


def fibonacci_limit_setups(df, horizon_key, params=None):
    """v131 arming mask plus the frozen order geometry, per bar:
    `arm`, `swing_high`, `swing_low`, `swing_high_idx` and
    `limit_price = swing_high - L * (swing_high - swing_low)`."""
    p = _params("Fibonacci Limit", params)
    anchors = fib_limit_anchors(df, horizon_key)
    limit = anchors["swing_high"] - p["L"] * (anchors["swing_high"] - anchors["swing_low"])
    arm = _arm_orders(
        _fib_limit_candidates(df, anchors, p["L"]).to_numpy(),
        anchors["swing_high_idx"].to_numpy(), df["Low"].to_numpy(dtype=float),
        df["High"].to_numpy(dtype=float), limit.to_numpy(dtype=float),
        anchors["swing_high"].to_numpy(dtype=float), int(p["N"]))
    return pd.DataFrame({"arm": arm, "swing_high": anchors["swing_high"],
                         "swing_low": anchors["swing_low"],
                         "swing_high_idx": anchors["swing_high_idx"],
                         "limit_price": limit}, index=df.index)


def _fib_limit_row(df, index, horizon_key):
    """The anchors row at `index`, computed from bars <= index only; None when
    the window is incomplete or the leg is flat."""
    if index < 0:
        index += len(df)
    lookback = HORIZONS[horizon_key]["fib_lookback"]
    window = df.iloc[max(0, index + 1 - lookback):index + 1]   # the rolling window itself
    row = fib_limit_anchors(window, horizon_key).iloc[-1]
    high, low = float(row["swing_high"]), float(row["swing_low"])
    if not (np.isfinite(high) and np.isfinite(low)) or high <= low:
        return None
    return row


def fib_limit_price_at(df, index, horizon_key, direction, params=None):
    """The v131 limit price frozen at bar `index`: swing_high - L * leg.
    Bullish only; None for bearish or an unusable window."""
    row = _fib_limit_row(df, index, horizon_key) if direction == "bullish" else None
    if row is None:
        return None
    ratio = _params("Fibonacci Limit", params)["L"]
    return float(row["swing_high"] - ratio * (row["swing_high"] - row["swing_low"]))


def fib_limit_cancel_at(df, index, horizon_key, direction):
    """The frozen swing high: a bar trading above it cancels the unfilled order."""
    row = _fib_limit_row(df, index, horizon_key) if direction == "bullish" else None
    return None if row is None else float(row["swing_high"])
```

- [ ] **Step 5: Run to verify it passes.** `python scripts/dev/testrun.py file tests/market/test_fib_limit_setups.py`. Expected: 20 passed. Then `python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py` — 2 passed (nothing existing moved).

- [ ] **Step 6: No-lookahead self-check (skill checklist).** Confirm, by reading the inserted code: no `shift(-n)`, no centred window; every rolling call is trailing; `_order_after_bar` at bar `t` reads only bar `t`; `_fib_limit_row` slices `df.iloc[:index+1]`'s last `fib_lookback` bars. The truncation tests in Step 2 are the proof; record "no-lookahead: truncation-tested, no forward reads" in the commit body.

- [ ] **Step 7: Complexity.** `python -m radon cc -s -n C swingbot/core/market/entry_filters.py` — none of the new functions may appear (measured: all ≤ 5).

- [ ] **Step 8: Commit**

```bash
git -C <worktree> add swingbot/core/market/entry_filters.py tests/market/test_fib_limit_setups.py
git -C <worktree> commit -m "feat(v131): fibonacci_limit_setups -- arming rule, causal order book, frozen limit and cancel prices

no-lookahead: truncation-tested every cut, no forward reads.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V131-03: Strict trade-through fill and pre-fill cancel in the limit simulator

**Files:**
- Modify: `swingbot/core/planning/plan_types.py:134` (two fields after `time_exit_notified_date`)
- Modify: `swingbot/core/planning/lifecycle.py:155-161` (`limit_hit`; new `limit_cancelled` after it)
- Modify: `swingbot/core/planning/exit_sim.py:17-18` (import), `:30-31` (`ExitResult` comment), `:398-416` (`_limit_entry_exit`; new `_limit_unfilled` before it)
- Create: `tests/planning/test_limit_cancel.py`

**Interfaces:**
- Consumes: `exit_sim._not_triggered(cancel_reason)`, `_fill_bar_exit`, `_walk_for`, `lifecycle.limit_fill_price` (all exist).
- Produces:
  - `TradePlanV2.limit_cancel_level: float | None = None`, `TradePlanV2.limit_strict_fill: bool = False`.
  - `lifecycle.limit_hit(plan, bar_high, bar_low)` — strict (`<` / `>`) when `plan.limit_strict_fill`, unchanged otherwise.
  - `lifecycle.limit_cancelled(plan, bar_high, bar_low) -> bool` — bullish `High > level`, bearish `Low < level`, False when the level is None.
  - `exit_sim._limit_unfilled(plan, cancelled) -> ExitResult` — `cancel_reason` `"cancelled"`/`"expired"` only when `limit_cancel_level` is set, else `None` (the v113 row).

- [ ] **Step 1: Write the failing tests.** Create `tests/planning/test_limit_cancel.py`:

```python
"""v131: strict trade-through fills and the pre-fill cancel for a resting buy limit."""
import pytest

from swingbot.core.planning import lifecycle
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv

SIGNAL = (101.5, 102.0, 101.0, 101.5)    # bar t: the arming bar
ABOVE = (101.0, 101.5, 100.5, 101.0)     # stays above the 100 limit and under the 105 cancel
LIMIT, STOP, TP1, CANCEL = 100.0, 98.0, 103.0, 105.0


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="limit", trigger_price=LIMIT, entry_price=None, expiry_bars=5,
        stop_loss=STOP, tp1=TP1, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=3.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
        limit_cancel_level=CANCEL, limit_strict_fill=True,
    )
    base.update(kw)
    return TradePlanV2(**base)


def _df(*bars):
    return make_ohlcv([SIGNAL, *bars])


def test_an_exact_touch_does_not_fill():
    df = _df((100.5, 101.0, 100.0, 100.6), *[ABOVE] * 6)
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


def test_a_trade_through_fills_at_the_limit():
    df = _df((100.5, 101.0, 99.9, 100.6), (101.0, 103.2, 100.8, 103.0))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_index, res.entry_price, res.exit_index) == ("win", 1, 100.0, 2)
    assert res.r_total == pytest.approx(1.5)


def test_a_gap_down_fills_at_the_open_and_r_is_measured_from_the_fill():
    df = _df((99.5, 99.8, 99.0, 99.6), (100.0, 103.2, 99.8, 103.0))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_price) == ("win", 99.5)
    assert res.r_total == pytest.approx((TP1 - 99.5) / (99.5 - STOP), abs=1e-3)


def test_a_new_high_before_any_fill_cancels():
    df = _df(ABOVE, (104.0, 105.5, 102.0, 105.2), (100.5, 101.0, 99.0, 99.5))
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.cancel_reason, res.entry_index) == ("not_triggered", "cancelled", None)


def test_a_high_equal_to_the_cancel_level_does_not_cancel():
    df = _df((104.0, 105.0, 102.0, 104.5), (100.5, 101.0, 99.5, 100.2), (100.2, 103.5, 100.0, 103.2))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.outcome, res.entry_index) == ("win", 2)


def test_the_same_bar_new_high_and_trade_through_is_a_fill():
    df = _df((101.0, 105.5, 99.8, 104.0), (104.0, 104.5, 103.5, 104.2))
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert (res.entry_index, res.entry_price, res.outcome) == (1, 100.0, "win")


def test_the_same_bar_new_high_and_fill_still_takes_the_fill_bar_stop():
    df = _df((101.0, 105.5, 97.5, 98.5), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)


def test_expiry_without_a_fill():
    df = _df(*[ABOVE] * 5, (100.0, 100.2, 95.0, 96.0))   # the trade-through is bar t+6
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


def test_a_fill_at_or_beyond_the_stop_scores_a_scratch():
    df = _df((97.5, 98.0, 97.0, 97.8), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_price, res.r_total) == ("scratch", 97.5, 0.0)
    assert res.legs[0]["reason"] == "gap_through_stop"


def test_a_stop_touch_on_the_fill_bar_is_a_full_loss():
    df = _df((100.5, 100.8, 97.9, 98.5), ABOVE)
    res = simulate_exit(df, 0, _plan(), scale_out=True)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 1, 1, -1.0)
    assert res.legs[0]["exit_price"] == STOP


def test_the_target_is_not_checked_on_the_fill_bar():
    df = _df((100.5, 103.5, 99.9, 103.2), *[ABOVE] * 3)
    res = simulate_exit(df, 0, _plan(), scale_out=False)
    assert res.entry_index == 1 and res.outcome != "win"


def test_a_plan_without_a_cancel_level_keeps_the_v113_rules():
    """The v113 fade's limit: touch fills, never cancels, reason-less no-fill."""
    plain = _plan(limit_cancel_level=None, limit_strict_fill=False)
    touch = _df((100.5, 101.0, 100.0, 100.6), (101.0, 103.2, 100.8, 103.0))
    assert simulate_exit(touch, 0, plain, scale_out=False).entry_price == 100.0
    run_away = _df((104.0, 106.0, 102.0, 105.5), *[ABOVE] * 5)
    res = simulate_exit(run_away, 0, plain, scale_out=False)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def test_truncating_after_the_cancel_bar_changes_nothing():
    full = _df(ABOVE, (104.0, 105.5, 102.0, 105.2), (100.5, 101.0, 99.0, 99.5))
    a = simulate_exit(full, 0, _plan(), scale_out=True)
    b = simulate_exit(full.iloc[:3], 0, _plan(), scale_out=True)
    assert (a.outcome, a.cancel_reason) == (b.outcome, b.cancel_reason)


def test_lifecycle_helpers():
    strict, plain = _plan(), _plan(limit_cancel_level=None, limit_strict_fill=False)
    assert not lifecycle.limit_hit(strict, 101.0, 100.0) and lifecycle.limit_hit(strict, 101.0, 99.99)
    assert lifecycle.limit_hit(plain, 101.0, 100.0)
    assert lifecycle.limit_cancelled(strict, 105.01, 101.0)
    assert not lifecycle.limit_cancelled(strict, 105.0, 101.0)
    assert not lifecycle.limit_cancelled(plain, 999.0, 101.0)
    short = _plan(direction="bearish", trigger_price=100.0, stop_loss=102.0, tp1=97.0,
                  limit_cancel_level=95.0)
    assert not lifecycle.limit_hit(short, 100.0, 99.0) and lifecycle.limit_hit(short, 100.01, 99.0)
    assert lifecycle.limit_cancelled(short, 99.0, 94.99) and not lifecycle.limit_cancelled(short, 99.0, 95.0)
```

- [ ] **Step 2: Run to verify it fails.** `python scripts/dev/testrun.py file tests/planning/test_limit_cancel.py`. Expected: FAIL — `TypeError: TradePlanV2.__init__() got an unexpected keyword argument 'limit_cancel_level'`.

- [ ] **Step 3: Add the plan fields.** In `swingbot/core/planning/plan_types.py`, after line 134 (`    time_exit_notified_date: str | None = None`), insert:

```python
    # v131 resting limit (planning/builders.LIMIT_PRICERS): the frozen level
    # whose trade-through cancels the still-unfilled order (bullish: a High
    # above it; bearish: a Low below it), and whether the limit fills only on
    # a strict trade-through (an exact touch does not fill). Defaults leave
    # every pre-v131 plan -- including the v113 fade's limit -- unchanged.
    limit_cancel_level: float | None = None
    limit_strict_fill: bool = False
```

These are add-only keys in `plans.doc` (`docs/claude/schema-evolution.md`, "add": no revision). `plan_from_dict` ignores unknown keys and defaults missing ones, so every persisted plan still loads.

- [ ] **Step 4: Strict fill and the cancel test.** In `swingbot/core/planning/lifecycle.py`, replace `limit_hit` (lines 155-161) with:

```python
def limit_hit(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """v113: a resting LIMIT order at trigger_price trades on this bar -- a sell
    limit (bearish) when the high reaches it, a buy limit (bullish) when the
    low does. Touching the limit exactly counts, unless the plan asks for a
    strict trade-through (v131 limit_strict_fill): then price must trade
    beyond the limit."""
    if plan.limit_strict_fill:
        if plan.direction == "bullish":
            return bar_low < plan.trigger_price
        return bar_high > plan.trigger_price
    if plan.direction == "bullish":
        return bar_low <= plan.trigger_price
    return bar_high >= plan.trigger_price


def limit_cancelled(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """v131: the still-unfilled limit is cancelled on this bar -- the leg
    extended beyond its frozen limit_cancel_level (bullish: High above it;
    bearish: Low below it). An equal print does not cancel. Plans without a
    cancel level never cancel."""
    level = plan.limit_cancel_level
    if level is None:
        return False
    if plan.direction == "bullish":
        return bar_high > level
    return bar_low < level
```

- [ ] **Step 5: The simulator.** In `swingbot/core/planning/exit_sim.py`:

Replace the import at lines 17-18 with:

```python
from .lifecycle import (at_or_beyond_stop, fill_price, limit_cancelled, limit_fill_price,
                        limit_hit, pending_expired, pending_invalidated, stop_touched,
                        trigger_hit)
```

Replace the two comment lines above `cancel_reason` (lines 30-31) with:

```python
    # Why a not_triggered row was excluded: the compression short's
    # "risk_cap"|"expired"|"invalidated", or a v131 cancellable limit's
    # "expired"|"cancelled". None everywhere else.
```

Replace `_limit_entry_exit` (lines 398-416) with:

```python
def _limit_unfilled(plan: TradePlanV2, cancelled: bool) -> ExitResult:
    """An unfilled limit. Only a v131 cancellable limit says why (its
    measurement counts expired and cancelled orders apart); every other limit
    keeps the reason-less row it always produced."""
    if plan.limit_cancel_level is None:
        return _not_triggered()
    return _not_triggered("cancelled" if cancelled else "expired")


def _limit_entry_exit(df, signal_index: int, plan: TradePlanV2, scale_out: bool,
                      max_holding_days: int) -> ExitResult:
    """v113 §3: a resting limit at trigger_price, live for the plan's
    expiry_bars bars after the signal bar (Part A: 1, so bar t+1 only). Fills on
    the first bar that trades through it, at limit_fill_price; the fill bar is
    checked against the stop (_fill_bar_exit), then the normal exit walk runs
    from the fill bar, so the time stop counts bars after ENTRY.

    v131: a bar that does not fill but trades beyond limit_cancel_level
    cancels the order. The fill is checked first, so a bar that both fills
    and extends the leg is a fill, and the fill-bar stop rule applies."""
    high, low, open_ = df["High"].values, df["Low"].values, df["Open"].values
    last = min(signal_index + plan.expiry_bars, len(df) - 1)
    for j in range(signal_index + 1, last + 1):
        bar_high, bar_low = float(high[j]), float(low[j])
        if not limit_hit(plan, bar_high, bar_low):
            if limit_cancelled(plan, bar_high, bar_low):
                return _limit_unfilled(plan, cancelled=True)
            continue
        entry_price = limit_fill_price(plan, float(open_[j]))
        early = _fill_bar_exit(df, j, entry_price, plan)
        if early is not None:
            return early
        return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)
    return _limit_unfilled(plan, cancelled=False)
```

- [ ] **Step 6: Run to verify it passes.**

```bash
python scripts/dev/testrun.py file tests/planning/test_limit_cancel.py
python scripts/dev/testrun.py file tests/planning/test_limit_entry.py
python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py
```

Expected: 14 passed; the v113 file unchanged and green; the witness 2 passed.

- [ ] **Step 7: Complexity.** `python -m radon cc -s -n C swingbot/core/planning/exit_sim.py swingbot/core/planning/lifecycle.py` — no new entries (measured: `limit_hit` 4, `limit_cancelled` 3, `_limit_unfilled` 3, `_limit_entry_exit` 5; `simulate_exit` stays 11).

- [ ] **Step 8: Commit**

```bash
git -C <worktree> add swingbot/core/planning/plan_types.py swingbot/core/planning/lifecycle.py swingbot/core/planning/exit_sim.py tests/planning/test_limit_cancel.py
git -C <worktree> commit -m "feat(v131): strict trade-through fill and pre-fill cancel for a resting limit, fill first on the same bar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
