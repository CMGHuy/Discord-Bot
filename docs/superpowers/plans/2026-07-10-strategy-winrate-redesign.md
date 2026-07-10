# Strategy Win-Rate Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-07-10-strategy-winrate-redesign-design.md` — read it first; it defines every threshold used below.

**Goal:** Every strategy in `swingbot/core` achieves ≥ 80% win rate AND positive expectancy on out-of-sample data (2024–2025), with live signals and backtest running identical entry logic.

**Architecture:** A new `swingbot/core/entry_filters.py` becomes the single source of entry logic (boolean Series over the whole DataFrame); `backtest.py::_vectorized_entries` and the live `signals.py` functions both delegate to it. The backtest exit engine gains a break-even stop (outcome `scratch`) and marks timeouts to market. Reward:risk moves from 0.10–0.12 to 0.35–0.40 (single source in `strategy_types.py`). Tuning happens on 2020–2023 only; 2024–2025 is validated once at the end.

**Tech Stack:** Python 3.11+, pandas 2.3, numpy 2.4, yfinance 0.2.66, pytest (added by Task 1). Windows dev box; run commands with `python` (not `python3`).

## Global Constraints

- **No lookahead:** every entry condition may reference only the current bar and earlier (`shift`, trailing `rolling`). Never `shift(-n)`, never centered windows.
- **Gates never NaN-pass:** every boolean Series ends with `.fillna(False)`.
- **Outcome taxonomy:** `win` (target hit) | `loss` (original stop hit) | `scratch` (break-even stop hit after the move) | `timeout` (max_holding_days elapsed; exit marked-to-market at that bar's close).
- **win_rate = wins / (wins + losses)`** — scratches and timeouts excluded from win rate, included in expectancy.
- **expectancy_r = mean(r_multiple) over ALL closed trades** (win + loss + scratch + timeout).
- **Stop wins same-bar ties** (conservative), unchanged. Within the bar that first reaches the break-even trigger, the ORIGINAL stop still applies; the moved stop protects subsequent bars only.
- **R:R hard floor 0.30.** Never set any `STRATEGY_RR_OVERRIDE` value below 0.30 (break-even win rate at 0.30 is 76.9%; below the floor an 80% win rate loses money).
- **Tuning discipline:** parameter selection reads ONLY the train window (2020-01-01 → 2023-12-31). The validation window (2024-01-01 → 2025-12-31) is run once, in Task 17, and its numbers are reported as-is.
- Tests: `python -m pytest tests -v` from the repo root. Commit after every task.

## File Structure

| File | Role |
|---|---|
| `tests/conftest.py` (create) | Synthetic OHLCV builders + shared fixtures |
| `tests/test_backtest_engine.py` (create) | Exit-engine / metrics tests |
| `tests/test_entry_filters.py` (create) | Shared-gate + per-strategy entry tests |
| `tests/test_trade_plan.py` (create) | R:R single-source tests |
| `swingbot/core/strategy_types.py` (modify) | + `STRATEGY_RR_OVERRIDE` (new values), `BREAKEVEN_TRIGGER_FRACTION`, `STRATEGY_GATES` |
| `swingbot/core/entry_filters.py` (create) | Shared gates, per-strategy entry functions, `entries_for` dispatcher, `DEFAULT_PARAMS` |
| `swingbot/core/backtest.py` (modify) | New exit engine, four-outcome metrics, `_vectorized_entries` delegates to `entry_filters` |
| `swingbot/core/trade_plan.py` (modify) | Consumes `STRATEGY_RR_OVERRIDE`; `management_note` field |
| `swingbot/core/signals.py` (modify) | Live triggers delegate to `entry_filters` |
| `swingbot/core/indicators.py` (modify) | `elliott_wave3_entries` records `wave0` |
| `swingbot/commands/backtest.py` (modify) | Scratch/timeout columns, updated 80% flag + help text |
| `scripts/fetch_backtest_data.py` (create) | One-time CSV cache of watchlist OHLCV 2018-06-01 → 2025-12-31 |
| `scripts/run_backtest_range.py` (create) | Acceptance harness (`--train` / `--validation`) |
| `scripts/tune_strategy.py` (create) | Per-strategy grid sweep on train window |
| `run_backtest_2025.py` (delete) | Replaced by `run_backtest_range.py` |

---

### Task 1: Test infrastructure

**Files:**
- Modify: `requirements.txt` (append pytest)
- Create: `tests/__init__.py` (empty file)
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01") -> pd.DataFrame` with columns `Open/High/Low/Close/Volume`, business-day DatetimeIndex; `make_trend_df(n, daily_pct, start_price=100.0, spread_pct=2.0) -> pd.DataFrame`; fixtures `uptrend_df`, `downtrend_df`, `flat_df`, `market_df`; helper `assert_entry_invariants(bull, bear, df)`.

- [x] **Step 1: Install pytest and record the dependency**

Run: `python -m pip install pytest`

Append to `requirements.txt`:

```
# Test-only dependency (not needed at bot runtime)
pytest>=8.0
```

- [x] **Step 2: Create `tests/__init__.py` (empty) and `tests/conftest.py`**

```python
"""Shared synthetic-OHLCV builders for backtest/entry-filter tests.

All series are deterministic (fixed seed where randomness is used) so
test failures are reproducible.
"""
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01"):
    """Build an OHLCV frame from a close series. High/Low straddle the close
    by spread_pct/2 each side; Open is the prior close."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range(start, periods=n)
    half = closes * (spread_pct / 100) / 2
    open_ = np.concatenate([[closes[0]], closes[:-1]])
    vol = np.full(n, 1_000_000.0) if volumes is None else np.asarray(volumes, dtype=float)
    return pd.DataFrame(
        {"Open": open_, "High": closes + half, "Low": closes - half,
         "Close": closes, "Volume": vol},
        index=idx,
    )


def make_trend_df(n, daily_pct, start_price=100.0, spread_pct=2.0):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=spread_pct)


def assert_entry_invariants(bull, bear, df):
    """Every entry function must return clean, aligned, non-overlapping booleans."""
    for s in (bull, bear):
        assert s.dtype == bool, f"dtype is {s.dtype}, expected bool"
        assert s.index.equals(df.index)
        assert not s.isna().any()
    assert not (bull & bear).any(), "a bar fired bullish AND bearish"


@pytest.fixture
def uptrend_df():
    return make_trend_df(500, +0.20)


@pytest.fixture
def downtrend_df():
    return make_trend_df(500, -0.20)


@pytest.fixture
def flat_df():
    return make_ohlcv(np.full(500, 100.0), spread_pct=0.1)


@pytest.fixture
def market_df():
    """1500 bars of seeded random walk with drift + volatility clustering —
    realistic enough for smoke/invariant tests across strategies."""
    rng = np.random.default_rng(42)
    rets = rng.normal(0.0005, 0.015, 1500)
    closes = 100 * np.cumprod(1 + rets)
    vols = rng.integers(500_000, 3_000_000, 1500).astype(float)
    return make_ohlcv(closes, spread_pct=2.0, volumes=vols)
```

- [x] **Step 3: Smoke-run pytest**

Run: `python -m pytest tests -v`
Expected: `no tests ran` (exit code 5 is fine — collection works, no tests yet).

- [x] **Step 4: Commit**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "test: add pytest + synthetic OHLCV builders for strategy redesign"
```

---

### Task 2: Single-source constants in `strategy_types.py`

**Files:**
- Modify: `swingbot/core/strategy_types.py`
- Modify: `swingbot/core/backtest.py:35-51` (delete its local `STRATEGY_RR_OVERRIDE`, import instead)
- Test: `tests/test_entry_filters.py` (new file, constants section)

**Interfaces:**
- Produces (in `swingbot.core.strategy_types`):
  - `STRATEGY_RR_OVERRIDE: dict[str, float]` — new values below
  - `BREAKEVEN_TRIGGER_FRACTION: float = 0.5`
  - `STRATEGY_GATES: dict[str, dict]` — `{strategy: {"directions": tuple[str, ...], "horizons": tuple[str, ...]}}`, empty until Task 16
- `swingbot.core.backtest` continues to expose `STRATEGY_RR_OVERRIDE` (re-export) so `from swingbot.core.backtest import STRATEGY_RR_OVERRIDE` keeps working.

- [x] **Step 1: Write the failing test** (`tests/test_entry_filters.py`)

```python
"""Tests for strategy_types constants and entry_filters."""
import pytest


def test_rr_override_single_source_and_floor():
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE, BREAKEVEN_TRIGGER_FRACTION
    from swingbot.core.backtest import STRATEGY_RR_OVERRIDE as BT_RR, ALL_STRATEGIES

    assert BT_RR is STRATEGY_RR_OVERRIDE          # same object, not a copy
    assert set(STRATEGY_RR_OVERRIDE) == set(ALL_STRATEGIES)
    assert all(rr >= 0.30 for rr in STRATEGY_RR_OVERRIDE.values()), \
        "R:R below 0.30 makes 80% win rate unprofitable (spec hard floor)"
    assert 0.0 < BREAKEVEN_TRIGGER_FRACTION < 1.0


def test_strategy_gates_shape():
    from swingbot.core.strategy_types import STRATEGY_GATES
    for strat, gates in STRATEGY_GATES.items():
        assert set(gates) <= {"directions", "horizons"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_entry_filters.py -v`
Expected: FAIL — `ImportError: cannot import name 'STRATEGY_RR_OVERRIDE' from 'swingbot.core.strategy_types'`.

- [x] **Step 3: Add constants to `strategy_types.py`** (append after `MACD_PERIODS_BY_HORIZON`)

```python
# ---------------------------------------------------------------------------
# Reward:risk per strategy -- SINGLE SOURCE for backtest.py AND trade_plan.py.
# HARD FLOOR 0.30: break-even win rate at R:R=X is 1/(1+X); at 0.30 that is
# 76.9%, so an 80% win rate is profitable. Below 0.30 a strategy can clear
# 80% win rate and still lose money -- never tune below the floor.
# Mean-reversion-at-structure strategies get 0.40 (they enter at a level, so
# the bounce has room); trend/breakout strategies get 0.35.
# ---------------------------------------------------------------------------
STRATEGY_RR_OVERRIDE: dict[str, float] = {
    "EMA Crossover":      0.35,
    "VWAP":               0.35,
    "Fibonacci":          0.40,
    "Support/Resistance": 0.35,
    "RSI":                0.40,
    "MACD":               0.35,
    "Elliott Wave":       0.35,
    "MA Ribbon":          0.35,
    "Break & Retest":     0.35,
    "RSI Divergence":     0.40,
    "Volume Profile":     0.40,
}

# When a trade's favorable excursion covers this fraction of the distance to
# target, the stop moves to entry (subsequent bars only). Exits at the moved
# stop are "scratch" (~0R), not losses. See backtest.py exit engine.
BREAKEVEN_TRIGGER_FRACTION = 0.5

# Per-strategy gating decided by TRAIN-window tuning (Task 16 fills this in).
# {"Strategy Name": {"directions": ("bullish",), "horizons": ("4w", "2m")}}
# A missing key means both directions, all horizons. entry_filters.entries_for
# applies the mask, so backtest and live signals both respect it.
STRATEGY_GATES: dict[str, dict] = {}
```

- [x] **Step 4: Replace the local table in `backtest.py`**

Delete lines 35–51 (the `STRATEGY_RR_OVERRIDE = {...}` block and its comment). Change line 30 from:

```python
from .strategy import HORIZONS, MIN_BARS, RSI_OVERBOUGHT, RSI_OVERSOLD, FIB_TOLERANCE_PCT, SR_VOLUME_MULTIPLE
```

to:

```python
from .strategy import HORIZONS, MIN_BARS, RSI_OVERBOUGHT, RSI_OVERSOLD, FIB_TOLERANCE_PCT, SR_VOLUME_MULTIPLE
from .strategy_types import BREAKEVEN_TRIGGER_FRACTION, STRATEGY_GATES, STRATEGY_RR_OVERRIDE
```

- [x] **Step 5: Run tests**

Run: `python -m pytest tests/test_entry_filters.py -v`
Expected: PASS (both tests).

- [x] **Step 6: Commit**

```bash
git add swingbot/core/strategy_types.py swingbot/core/backtest.py tests/test_entry_filters.py
git commit -m "feat: single-source R:R overrides (0.35-0.40) + breakeven/gating constants"
```

---

### Task 3: Backtest exit engine — break-even stop, scratch outcome, timeout mark-to-market

**Files:**
- Modify: `swingbot/core/backtest.py` (`BacktestSummary`, `run_backtest` walk-forward + summary block, `run_backtest_daterange` recompute block)
- Test: `tests/test_backtest_engine.py`

**Interfaces:**
- `BacktestSummary` gains field `scratches: int` (after `timeouts`).
- `BacktestTrade.outcome` may now be `"scratch"`; timeout trades now carry real `exit_price`, `return_pct`, `r_multiple`, `holding_days`, `exit_date`.
- `win_rate` definition unchanged (`wins/(wins+losses)`); `expectancy_r` now averages `r_multiple` over ALL closed trades; `evaluated` stays `wins+losses`.
- Consumes: `BREAKEVEN_TRIGGER_FRACTION` from Task 2.

- [x] **Step 1: Write the failing tests** (`tests/test_backtest_engine.py`)

The tests force one entry at a known bar by monkeypatching `_vectorized_entries`, on data crafted so ATR is deterministic (constant closes, fixed spread → ATR(14) = spread). With close=100, spread 1%: ATR=1.0, risk = 2×ATR = 2 (2w cap is 3% so uncapped), stop=98, target=100 + 2×0.35 = 100.70, break-even trigger = 100.35.

```python
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


def _run_with_forced_entry(monkeypatch, df, entry_bar, direction="bullish",
                           strategy="EMA Crossover", horizon="2w"):
    import swingbot.core.backtest as bt
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    (bull if direction == "bullish" else bear).iloc[entry_bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    return bt.run_backtest("TEST", df, strategy, horizon)


def test_scratch_when_trigger_reached_then_returns_to_entry(monkeypatch):
    # Constant 100 with 1% spread: every bar's high=100.5 >= trigger 100.35,
    # and every bar's low=99.5 <= entry 100. Bar e+1 arms the break-even move
    # (original stop 98 not hit, target 100.7 not hit), bar e+2 hits the moved
    # stop at entry -> scratch at ~0R.
    df = make_ohlcv(np.full(60, 100.0), spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.scratches == 1 and s.wins == 0 and s.losses == 0
    t = s.trades[0]
    assert t.outcome == "scratch"
    assert t.exit_price == pytest.approx(100.0)
    assert t.r_multiple == pytest.approx(0.0, abs=1e-9)
    assert s.win_rate is None            # no wins+losses -> undefined, not 100%
    assert s.expectancy_r == pytest.approx(0.0, abs=1e-9)


def test_win_when_target_hit_before_stop(monkeypatch):
    closes = np.full(60, 100.0)
    closes[41:] = 101.0                  # bar e+1 jumps: high 101.5 >= target 100.7
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.wins == 1 and s.losses == 0 and s.scratches == 0
    assert s.win_rate == pytest.approx(100.0)


def test_loss_when_original_stop_hit_before_trigger(monkeypatch):
    closes = np.full(60, 100.0)
    closes[41:] = 97.0                   # bar e+1 collapses: low 96.5 <= stop 98
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.losses == 1 and s.wins == 0 and s.scratches == 0
    assert s.trades[0].r_multiple == pytest.approx(-1.0, abs=0.01)


def test_timeout_is_marked_to_market_and_in_expectancy(monkeypatch):
    # Entry at 100 (bar 40), then price steps down to 99.8 and stays there.
    # Post-entry highs are 99.8+0.5=100.3 < trigger 100.35, lows 99.3 > stop 98,
    # target never reached -> 2w horizon times out after 14 bars, marked to
    # market at 99.8 (a -0.2% / -0.1R "invisible" trade the old engine dropped).
    closes = np.concatenate([np.full(41, 100.0), np.full(19, 99.8)])
    df = make_ohlcv(closes, spread_pct=1.0)
    s = _run_with_forced_entry(monkeypatch, df, entry_bar=40)
    assert s.timeouts == 1 and s.wins == 0 and s.losses == 0
    t = s.trades[0]
    assert t.outcome == "timeout"
    assert t.exit_price is not None and t.return_pct is not None
    assert t.r_multiple < 0              # drifted down -> negative
    assert s.expectancy_r is not None and s.expectancy_r < 0
    assert s.win_rate is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_backtest_engine.py -v`
Expected: FAIL — `AttributeError: 'BacktestSummary' object has no attribute 'scratches'` (and/or timeout trades having `exit_price=None`).

- [x] **Step 3: Implement the engine changes in `backtest.py`**

3a. Add to `BacktestSummary` after `timeouts: int` (NO default — later fields like `win_rate` have no defaults, and a defaulted field before them is a dataclass error):

```python
    scratches: int
```

Update the two zero-trade early-return constructions in `run_backtest` (and the one in `run_backtest_daterange`'s underlying call path if any) to pass `scratches=0`.

3b. Replace the walk-forward block inside `run_backtest` (currently the `outcome, exit_price, exit_i = "timeout", None, None` line through the end of the `for j ...` loop and the `if outcome == "timeout":` block) with:

```python
        close_vals = df["Close"].values
        outcome, exit_price, exit_i = "timeout", None, None
        max_holding_days = HORIZONS[horizon_key]["max_holding_days"]
        end = min(i + max_holding_days, n - 1)

        target_dist = abs(take_profit - entry)
        if direction == "bullish":
            be_trigger = entry + BREAKEVEN_TRIGGER_FRACTION * target_dist
        else:
            be_trigger = entry - BREAKEVEN_TRIGGER_FRACTION * target_dist
        stop_moved = False

        for j in range(i + 1, end + 1):
            hi, lo = float(high[j]), float(low[j])
            cur_stop = entry if stop_moved else stop_loss
            if direction == "bullish":
                hit_stop = lo <= cur_stop
                hit_target = hi >= take_profit
                reached_trigger = hi >= be_trigger
            else:
                hit_stop = hi >= cur_stop
                hit_target = lo <= take_profit
                reached_trigger = lo <= be_trigger

            # Conservative ordering: stop first (original stop still governs
            # the bar that first reaches the trigger), then target. The moved
            # stop only protects bars AFTER the trigger bar.
            if hit_stop:
                outcome = "scratch" if stop_moved else "loss"
                exit_price, exit_i = cur_stop, j
                break
            if hit_target:
                outcome, exit_price, exit_i = "win", take_profit, j
                break
            if reached_trigger and not stop_moved:
                stop_moved = True

        if outcome == "timeout":
            exit_price, exit_i = float(close_vals[end]), end

        _open_until = exit_i
        sign = 1 if direction == "bullish" else -1
        return_pct = (exit_price - entry) / entry * sign * 100
        r_multiple = (exit_price - entry) * sign / risk_per_share
        holding_days = exit_i - i

        trades.append(BacktestTrade(
            entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()),
            direction=direction, entry=round(entry, 4), stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4), outcome=outcome,
            exit_price=round(exit_price, 4), return_pct=round(return_pct, 3),
            r_multiple=round(r_multiple, 3), holding_days=holding_days,
        ))
```

(The old separate timeout `trades.append` with `None` fields is deleted — every trade now gets real exit numbers. Hoist `close_vals = df["Close"].values` up next to `high`/`low` instead of inside the loop.)

3c. Replace the summary block at the end of `run_backtest`:

```python
    evaluated_trades = [t for t in trades if t.outcome in ("win", "loss")]
    wins      = [t for t in evaluated_trades if t.outcome == "win"]
    losses    = [t for t in evaluated_trades if t.outcome == "loss"]
    scratches = [t for t in trades if t.outcome == "scratch"]
    timeouts  = [t for t in trades if t.outcome == "timeout"]

    win_rate = len(wins) / len(evaluated_trades) * 100 if evaluated_trades else None
    avg_return_pct   = float(np.mean([t.return_pct   for t in evaluated_trades])) if evaluated_trades else None
    avg_r_multiple   = float(np.mean([t.r_multiple   for t in evaluated_trades])) if evaluated_trades else None
    avg_holding_days = float(np.mean([t.holding_days for t in evaluated_trades])) if evaluated_trades else None

    # Expectancy over ALL closed trades -- wins, losses, scratches (~0R) and
    # timeouts (marked to market). This is the "does it make money" number.
    expectancy_r = float(np.mean([t.r_multiple for t in trades])) if trades else None

    max_drawdown_pct = None
    if trades:
        equity = [1.0]
        for t in trades:
            equity.append(equity[-1] * (1 + t.return_pct / 100))
        equity = np.array(equity)
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max
        max_drawdown_pct = float(drawdowns.min() * 100)

    return BacktestSummary(
        ticker=ticker, strategy=strategy, horizon_key=horizon_key,
        total_signals=total_signals, evaluated=len(evaluated_trades),
        wins=len(wins), losses=len(losses), timeouts=len(timeouts),
        scratches=len(scratches),
        win_rate=win_rate, avg_return_pct=avg_return_pct, avg_r_multiple=avg_r_multiple,
        expectancy_r=expectancy_r, max_drawdown_pct=max_drawdown_pct,
        avg_holding_days=avg_holding_days, trades=trades,
    )
```

3d. Update the recompute block in `run_backtest_daterange` to the same definitions (scratches list, expectancy over all `summary.trades` in-window, equity curve over all trades):

```python
        ev       = [t for t in summary.trades if t.outcome in ("win", "loss")]
        wins     = [t for t in ev if t.outcome == "win"]
        losses   = [t for t in ev if t.outcome == "loss"]
        scratches = [t for t in summary.trades if t.outcome == "scratch"]
        timeouts  = [t for t in summary.trades if t.outcome == "timeout"]
        summary.total_signals = len(summary.trades)
        summary.evaluated     = len(ev)
        summary.wins          = len(wins)
        summary.losses        = len(losses)
        summary.timeouts      = len(timeouts)
        summary.scratches     = len(scratches)
        summary.win_rate      = len(wins) / len(ev) * 100 if ev else None
        if summary.trades:
            summary.expectancy_r   = float(np.mean([t.r_multiple for t in summary.trades]))
            equity = [1.0]
            for t in summary.trades:
                equity.append(equity[-1] * (1 + t.return_pct / 100))
            equity = np.array(equity)
            running_max = np.maximum.accumulate(equity)
            summary.max_drawdown_pct = float(((equity - running_max) / running_max).min() * 100)
        else:
            summary.expectancy_r = summary.max_drawdown_pct = None
        if ev:
            summary.avg_return_pct   = float(np.mean([t.return_pct   for t in ev]))
            summary.avg_r_multiple   = float(np.mean([t.r_multiple   for t in ev]))
            summary.avg_holding_days = float(np.mean([t.holding_days for t in ev]))
        else:
            summary.avg_return_pct = summary.avg_r_multiple = summary.avg_holding_days = None
```

- [x] **Step 4: Run tests**

Run: `python -m pytest tests/test_backtest_engine.py tests/test_entry_filters.py -v`
Expected: PASS (all).

- [x] **Step 5: Commit**

```bash
git add swingbot/core/backtest.py tests/test_backtest_engine.py
git commit -m "feat: break-even exit engine, scratch outcome, timeout mark-to-market"
```

---

### Task 4: `trade_plan.py` consumes the shared R:R + management note

**Files:**
- Modify: `swingbot/core/trade_plan.py` (imports, `TradePlan` dataclass, the two `rr = h["reward_risk_ratio"]` sites at lines ~416 and ~425)
- Test: `tests/test_trade_plan.py`

**Interfaces:**
- `TradePlan` gains `management_note: str` with default `MANAGEMENT_NOTE` (a module constant) — no construction sites need editing.
- Both ATR-sizing helpers now use `STRATEGY_RR_OVERRIDE.get(result.strategy, h["reward_risk_ratio"])`.

- [x] **Step 1: Write the failing test** (`tests/test_trade_plan.py`)

```python
import numpy as np
import pytest

from tests.conftest import make_trend_df


def _fake_result(strategy, horizon="4w", trend="bullish", close=100.0):
    from swingbot.core.strategy_types import HORIZONS, SignalResult
    return SignalResult(
        ticker="TEST", strategy=strategy, horizon_key=horizon,
        horizon_label=HORIZONS[horizon]["label"], trend=trend,
        triggered=True, close=close, details={},
    )


def test_atr_sized_plan_uses_strategy_rr_override():
    from swingbot.core.trade_plan import compute_trade_plan
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE

    df = make_trend_df(300, +0.1)
    result = _fake_result("EMA Crossover", close=float(df["Close"].iloc[-1]))
    plan = compute_trade_plan(result, df)
    reward = abs(plan.take_profit - plan.entry)
    risk = abs(plan.entry - plan.stop_loss)
    assert reward / risk == pytest.approx(STRATEGY_RR_OVERRIDE["EMA Crossover"], rel=0.01)


def test_plan_carries_management_note():
    from swingbot.core.trade_plan import compute_trade_plan, MANAGEMENT_NOTE
    df = make_trend_df(300, +0.1)
    plan = compute_trade_plan(_fake_result("VWAP", close=float(df["Close"].iloc[-1])), df)
    assert plan.management_note == MANAGEMENT_NOTE
    assert "stop to entry" in MANAGEMENT_NOTE
```

- [x] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_trade_plan.py -v`
Expected: FAIL — `ImportError: cannot import name 'MANAGEMENT_NOTE'` (and the R:R assertion would fail with the horizon ratio 0.50).

- [x] **Step 3: Implement**

3a. Add to `trade_plan.py` imports: `from .strategy_types import BREAKEVEN_TRIGGER_FRACTION, STRATEGY_RR_OVERRIDE` and define below the existing constants:

```python
MANAGEMENT_NOTE = (
    f"After price covers {BREAKEVEN_TRIGGER_FRACTION:.0%} of the distance to target, "
    "move the stop to entry. A break-even exit is a scratch, not a loss -- this is "
    "the rule the backtest numbers assume."
)
```

3b. Add to the `TradePlan` dataclass (last field):

```python
    management_note: str = MANAGEMENT_NOTE
```

3c. At both sites that read `rr = h["reward_risk_ratio"]` (in the ATR-sizing helpers around lines 416 and 425 — find with `grep -n 'reward_risk_ratio' swingbot/core/trade_plan.py`), replace with:

```python
    rr = STRATEGY_RR_OVERRIDE.get(strategy_name, h["reward_risk_ratio"])
```

where `strategy_name` is the strategy string available in that helper's scope — pass `result.strategy` down if the helper doesn't already receive it (check its call sites in `compute_trade_plan` and thread the parameter through).

- [x] **Step 4: Run tests**

Run: `python -m pytest tests/test_trade_plan.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add swingbot/core/trade_plan.py tests/test_trade_plan.py
git commit -m "feat: trade_plan consumes shared R:R override + break-even management note"
```

---

### Task 5: `entry_filters.py` — shared gates + dispatcher

**Files:**
- Create: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Produces:
  - `compute_shared_gates(df) -> dict[str, pd.Series]` with keys `bull_regime`, `bull_regime_slope_only`, `bear_regime`, `trend50_bull`, `trend50_bear`, `atr_floor`, `atr_calm`, `vol_ok` (bool Series) and `rsi14`, `atr14`, `ma50`, `ma200` (float Series).
  - `DEFAULT_PARAMS: dict[str, dict]` — per-strategy tunables (filled per strategy in Tasks 6–12; this task seeds the dict empty).
  - `ENTRY_FUNCS: dict[str, callable]` — registry, filled by Tasks 6–12.
  - `entries_for(strategy, df, horizon_key, params=None) -> tuple[pd.Series, pd.Series]` — dispatch + `STRATEGY_GATES` masking.
  - `_rolling_argmax_pos(s, lookback)` / `_rolling_argmin_pos(s, lookback)` helpers (used by Fibonacci, unit-tested here).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_entry_filters.py`)

```python
import numpy as np
import pandas as pd

from tests.conftest import make_trend_df, make_ohlcv, assert_entry_invariants


def test_shared_gates_uptrend(uptrend_df):
    from swingbot.core.entry_filters import compute_shared_gates
    g = compute_shared_gates(uptrend_df)
    for key in ("bull_regime", "bear_regime", "trend50_bull", "trend50_bear",
                "atr_floor", "atr_calm", "vol_ok"):
        assert g[key].dtype == bool
        assert not g[key].isna().any()
    # 200-SMA + 20-bar slope shift need 220 bars: nothing NaN-passes early
    assert not g["bull_regime"].iloc[:219].any()
    # a steady uptrend is a bull regime at the end, never a bear regime
    assert g["bull_regime"].iloc[-1]
    assert not g["bear_regime"].any()


def test_shared_gates_downtrend(downtrend_df):
    from swingbot.core.entry_filters import compute_shared_gates
    g = compute_shared_gates(downtrend_df)
    assert not g["bull_regime"].iloc[-1]
    # bear regime needs 200-SMA falling for 120 bars -> needs 320 bars, so
    # it can be True only late in the series
    assert g["bear_regime"].iloc[-1]
    assert not g["bear_regime"].iloc[:319].any()


def test_rolling_extreme_position_helpers():
    from swingbot.core.entry_filters import _rolling_argmax_pos, _rolling_argmin_pos
    s = pd.Series([1.0, 5.0, 2.0, 3.0, 4.0])
    amax = _rolling_argmax_pos(s, 3)
    amin = _rolling_argmin_pos(s, 3)
    assert np.isnan(amax.iloc[0]) and np.isnan(amax.iloc[1])
    assert amax.iloc[2] == 1        # window [1,5,2] -> max at position 1
    assert amin.iloc[2] == 0        # min at position 0
    assert amax.iloc[4] == 2        # window [2,3,4] -> max at last position


def test_entries_for_applies_direction_and_horizon_gates(monkeypatch, uptrend_df):
    import swingbot.core.entry_filters as ef

    fired = pd.Series(True, index=uptrend_df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "Stub", lambda df, hk, params=None: (fired.copy(), fired.copy()))

    monkeypatch.setitem(ef.STRATEGY_GATES, "Stub", {"directions": ("bullish",)})
    bull, bear = ef.entries_for("Stub", uptrend_df, "4w")
    assert bull.all() and not bear.any()

    monkeypatch.setitem(ef.STRATEGY_GATES, "Stub", {"horizons": ("2m",)})
    bull, bear = ef.entries_for("Stub", uptrend_df, "4w")
    assert not bull.any() and not bear.any()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_entry_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.entry_filters'`.

- [ ] **Step 3: Create `swingbot/core/entry_filters.py`**

```python
"""
SINGLE SOURCE of entry logic for every strategy -- consumed by BOTH the
backtest (backtest._vectorized_entries) and the live scanner (signals.py).
Change a filter here and both worlds change together; that is the point.

Every function returns (bullish_entries, bearish_entries): boolean Series
aligned to df.index, True on bars where a fresh entry fires.

NO-LOOKAHEAD RULE: conditions may reference only the current bar and
earlier (`shift(+n)`, trailing `rolling`). Never `shift(-n)`, never
centered windows. Every boolean Series is `.fillna(False)` -- a gate that
cannot be computed yet (short history) BLOCKS entries, it never passes.

Tunables live in DEFAULT_PARAMS (per strategy); scripts/tune_strategy.py
sweeps them on the train window only. STRATEGY_GATES (strategy_types.py)
lets tuning disable a direction or horizons per strategy.
"""
import numpy as np
import pandas as pd

from .indicators import atr, ema, macd, rolling_vwap, rsi, elliott_wave3_entries
from .strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE,
    STRATEGY_GATES,
)

ATR_FLOOR_PCT = 0.007   # skip dead-flat tape: ATR must be >= 0.7% of price
ATR_CALM_MULT = 1.4     # skip panic tape: ATR must be <= 1.4x its 60-bar mean
VOL_OK_MULT   = 0.9     # entry bar volume >= 0.9x its 20-bar mean

# Per-strategy tunables. Tasks 6-12 add one entry each; tune_strategy.py
# mutates these in-place per grid point (and restores afterwards).
DEFAULT_PARAMS: dict[str, dict] = {}

# Registry: strategy name -> entry function. Tasks 6-12 populate it.
ENTRY_FUNCS: dict[str, "callable"] = {}


def compute_shared_gates(df: pd.DataFrame) -> dict:
    """Gates applied to (almost) every strategy -- see spec section 5.
    RSI exception: dip-buying uses `bull_regime_slope_only` and skips trend50."""
    close = df["Close"]
    atr14 = atr(df, 14)
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    vol_avg20 = df["Volume"].rolling(20).mean()
    return {
        "bull_regime": ((close > ma200) & (ma200 > ma200.shift(20))).fillna(False),
        "bull_regime_slope_only": (ma200 > ma200.shift(120)).fillna(False),
        "bear_regime": ((ma200 < ma200.shift(120)) & (close < ma200)).fillna(False),
        "trend50_bull": (close > ma50).fillna(False),
        "trend50_bear": (close < ma50).fillna(False),
        "atr_floor": ((atr14 / close.replace(0, np.nan)) >= ATR_FLOOR_PCT).fillna(False),
        "atr_calm": (atr14 <= atr14.rolling(60).mean() * ATR_CALM_MULT).fillna(False),
        "vol_ok": (df["Volume"] >= vol_avg20 * VOL_OK_MULT).fillna(False),
        "rsi14": rsi(close, 14),
        "atr14": atr14,
        "ma50": ma50,
        "ma200": ma200,
    }


def _rolling_argmax_pos(s: pd.Series, lookback: int) -> pd.Series:
    """Position (0..lookback-1) of the max within each trailing window ending
    at the bar (inclusive). NaN until `lookback` bars exist. Higher position
    = the extreme happened more recently."""
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) >= lookback:
        w = np.lib.stride_tricks.sliding_window_view(v, lookback)
        out[lookback - 1:] = w.argmax(axis=1)
    return pd.Series(out, index=s.index)


def _rolling_argmin_pos(s: pd.Series, lookback: int) -> pd.Series:
    v = s.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) >= lookback:
        w = np.lib.stride_tricks.sliding_window_view(v, lookback)
        out[lookback - 1:] = w.argmin(axis=1)
    return pd.Series(out, index=s.index)


def _params(strategy: str, params: dict | None) -> dict:
    merged = dict(DEFAULT_PARAMS.get(strategy, {}))
    if params:
        merged.update(params)
    return merged


def _off(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def entries_for(strategy: str, df: pd.DataFrame, horizon_key: str,
                params: dict | None = None) -> tuple[pd.Series, pd.Series]:
    """Dispatch to the strategy's entry function, then apply STRATEGY_GATES
    (direction/horizon restrictions decided by train-window tuning)."""
    bullish, bearish = ENTRY_FUNCS[strategy](df, horizon_key, params)

    gates = STRATEGY_GATES.get(strategy)
    if gates:
        horizons = gates.get("horizons")
        if horizons is not None and horizon_key not in horizons:
            return _off(df), _off(df)
        directions = gates.get("directions")
        if directions is not None:
            if "bullish" not in directions:
                bullish = _off(df)
            if "bearish" not in directions:
                bearish = _off(df)
    return bullish, bearish
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_entry_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: entry_filters module - shared gates, dispatcher, gating masks"
```

---

### Task 6: Fibonacci entries (swing-direction fix)

**Files:**
- Modify: `swingbot/core/entry_filters.py` (add `fibonacci_entries`, register, add params)
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Produces: `fibonacci_entries(df, horizon_key, params=None)`; `DEFAULT_PARAMS["Fibonacci"] = {"ratios": (0.382, 0.5, 0.618), "rsi_bull": (35, 58), "rsi_bear": (42, 65)}`; `ENTRY_FUNCS["Fibonacci"]`.

- [ ] **Step 1: Write the failing tests**

```python
def _v_shape_down_then_flat():
    # Peak early (bar 350), decline to bar 470, small bounce at the end.
    # The swing HIGH precedes the swing LOW inside any recent window ->
    # down-impulse -> the old code would call a bounce here "bullish
    # retracement"; the fixed code must not.
    closes = np.concatenate([
        100 * 1.002 ** np.arange(350),                       # up to ~201
        100 * 1.002 ** 349 * 0.995 ** np.arange(1, 121),     # down ~45%
        np.full(29, 100 * 1.002 ** 349 * 0.995 ** 120 * 1.002),
    ])
    return make_ohlcv(closes, spread_pct=2.0)


def test_fibonacci_no_bullish_entries_on_down_impulse():
    from swingbot.core.entry_filters import fibonacci_entries
    df = _v_shape_down_then_flat()
    bull, bear = fibonacci_entries(df, "4w")
    assert_entry_invariants(bull, bear, df)
    # last 40 bars: price is bouncing off a decline -- swing direction is
    # DOWN, so no bullish fib-retracement entries are allowed there
    assert not bull.iloc[-40:].any()


def test_fibonacci_bullish_requires_bull_regime(downtrend_df):
    from swingbot.core.entry_filters import fibonacci_entries
    bull, bear = fibonacci_entries(downtrend_df, "4w")
    assert_entry_invariants(bull, bear, downtrend_df)
    assert not bull.any()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_entry_filters.py -k fibonacci -v`
Expected: FAIL — `ImportError: cannot import name 'fibonacci_entries'`.

- [ ] **Step 3: Implement** (append to `entry_filters.py`, and register)

```python
DEFAULT_PARAMS["Fibonacci"] = {
    "ratios": (0.382, 0.5, 0.618),   # 23.6% too shallow, 78.6% = failed impulse
    "rsi_bull": (35, 58),
    "rsi_bear": (42, 65),
}


def fibonacci_entries(df, horizon_key, params=None):
    """Retracement bounce WITH swing-direction awareness: a bullish bounce is
    only valid when the up-impulse is the recent structure (swing low set
    BEFORE swing high). The old rolling-max/min version fired 'bullish' on
    retracements of downtrends, where the fib level is overhead resistance."""
    p = _params("Fibonacci", params)
    h = HORIZONS[horizon_key]
    lookback = h["fib_lookback"]
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]

    swing_high = high.rolling(lookback).max()
    swing_low = low.rolling(lookback).min()
    rng = swing_high - swing_low

    # Swing direction: where in the window did the extremes happen?
    hi_pos = _rolling_argmax_pos(high, lookback)
    lo_pos = _rolling_argmin_pos(low, lookback)
    up_impulse = (hi_pos > lo_pos)       # low first, then high -> uptrend pullback
    down_impulse = (lo_pos > hi_pos)

    levels = pd.DataFrame({r: swing_high - r * rng for r in p["ratios"]})
    nearest_distance = levels.sub(close, axis=0).abs().min(axis=1)
    distance_pct = (nearest_distance / rng * 100).replace([np.inf, -np.inf], np.nan)
    is_testing = (distance_pct <= FIB_TOLERANCE_PCT) & rng.gt(0)

    pulled_back_bull = close.shift(5) > close.shift(1)
    bouncing_bull = close > close.shift(1)
    pulled_back_bear = close.shift(5) < close.shift(1)
    bouncing_bear = close < close.shift(1)
    upper_half = close >= (high + low) / 2   # bounce bar closes strong
    lower_half = close <= (high + low) / 2

    rsi14 = g["rsi14"]
    bullish = (is_testing & up_impulse & pulled_back_bull & bouncing_bull & upper_half
               & g["bull_regime"] & g["trend50_bull"]
               & rsi14.between(*p["rsi_bull"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (is_testing & down_impulse & pulled_back_bear & bouncing_bear & lower_half
               & g["bear_regime"] & g["trend50_bear"]
               & rsi14.between(*p["rsi_bear"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Fibonacci"] = fibonacci_entries
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_entry_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: Fibonacci entries with swing-direction fix + bounce-bar quality"
```

---

### Task 7: EMA Crossover + VWAP entries

**Files:**
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Produces: `ema_cross_entries`, `vwap_entries`; `DEFAULT_PARAMS["EMA Crossover"] = {"rsi_dip": 45, "ext_atr": 1.0}`, `DEFAULT_PARAMS["VWAP"] = {"ext_pct": 1.5, "hold_bars_2w": 3, "hold_bars_other": 2}`; registry entries.

- [ ] **Step 1: Write the failing tests**

```python
GATED_BY_MA50 = ["EMA Crossover", "VWAP", "Fibonacci"]  # extended by later tasks


def test_bullish_entries_respect_trend_gates(market_df):
    """Wiring invariant: every bullish entry bar must satisfy the shared
    trend gates the strategy declares (close above the 50- and 200-SMA)."""
    from swingbot.core.entry_filters import ENTRY_FUNCS, compute_shared_gates
    g = compute_shared_gates(market_df)
    for strat in GATED_BY_MA50:
        if strat not in ENTRY_FUNCS:
            continue
        bull, bear = ENTRY_FUNCS[strat](market_df, "4w")
        assert_entry_invariants(bull, bear, market_df)
        fired = bull[bull].index
        assert g["trend50_bull"].loc[fired].all(), f"{strat}: bull entry below 50-SMA"
        assert g["bull_regime"].loc[fired].all(), f"{strat}: bull entry outside bull regime"


def test_ema_cross_not_extended(market_df):
    """No bullish EMA entry may be more than ext_atr ATRs above the fast EMA."""
    from swingbot.core.entry_filters import ema_cross_entries, compute_shared_gates, DEFAULT_PARAMS
    from swingbot.core.indicators import ema
    from swingbot.core.strategy_types import HORIZONS
    g = compute_shared_gates(market_df)
    bull, _ = ema_cross_entries(market_df, "4w")
    fast = ema(market_df["Close"], HORIZONS["4w"]["ema_fast"])
    cap = DEFAULT_PARAMS["EMA Crossover"]["ext_atr"]
    ext = (market_df["Close"] - fast).abs() / g["atr14"]
    assert (ext[bull] <= cap + 1e-9).all()


def test_vwap_entries_flat_market_produces_nothing(flat_df):
    from swingbot.core.entry_filters import vwap_entries
    bull, bear = vwap_entries(flat_df, "4w")
    assert not bull.any() and not bear.any()   # atr_floor gate blocks dead tape
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_entry_filters.py -k "ema or vwap or trend_gates" -v`
Expected: FAIL — `ImportError: cannot import name 'ema_cross_entries'`.

- [ ] **Step 3: Implement**

```python
DEFAULT_PARAMS["EMA Crossover"] = {"rsi_dip": 45, "ext_atr": 1.0}


def ema_cross_entries(df, horizon_key, params=None):
    p = _params("EMA Crossover", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]
    fast = ema(close, h["ema_fast"])
    slow = ema(close, h["ema_slow"])
    diff = fast - slow
    # 2-bar hold: crossed last bar AND held today (filters one-bar fakeouts)
    held_bull = (diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)
    held_bear = (diff.shift(2) >= 0) & (diff.shift(1) < 0) & (diff < 0)

    rsi14 = g["rsi14"]
    rsi_dipped = rsi14.rolling(5).min().shift(1) < p["rsi_dip"]          # real pullback preceded
    rsi_surged = rsi14.rolling(5).max().shift(1) > (100 - p["rsi_dip"])
    m = macd(close)
    mom_bull = (m["macd"] > 0) | (rsi14 > 60)
    mom_bear = (m["macd"] < 0) | (rsi14 < 40)
    slow_rising = slow > slow.shift(5)      # cross inside a falling slow EMA is a trap
    slow_falling = slow < slow.shift(5)
    not_extended = (close - fast).abs() <= g["atr14"] * p["ext_atr"]

    bullish = (held_bull & slow_rising & not_extended & (rsi14 > 50) & rsi_dipped & mom_bull
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (held_bear & slow_falling & not_extended & (rsi14 < 50) & rsi_surged & mom_bear
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["EMA Crossover"] = ema_cross_entries


DEFAULT_PARAMS["VWAP"] = {"ext_pct": 1.5, "hold_bars_2w": 3, "hold_bars_other": 2}


def vwap_entries(df, horizon_key, params=None):
    p = _params("VWAP", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]
    vwap = rolling_vwap(df, h["vwap_window"])
    diff = close - vwap

    hold = p["hold_bars_2w"] if horizon_key == "2w" else p["hold_bars_other"]
    held_bull = (diff.shift(hold) <= 0)
    held_bear = (diff.shift(hold) >= 0)
    for k in range(hold):
        held_bull = held_bull & (diff.shift(k) > 0)
        held_bear = held_bear & (diff.shift(k) < 0)

    vwap_up = vwap > vwap.shift(3)
    vwap_down = vwap < vwap.shift(3)
    ext = (close - vwap).abs() / vwap.replace(0, np.nan) * 100
    not_extended = ext <= p["ext_pct"]       # reclaim near value, don't chase
    rsi14 = g["rsi14"]

    bullish = (held_bull & vwap_up & not_extended & rsi14.between(50, 65)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (held_bear & vwap_down & not_extended & rsi14.between(35, 50)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["VWAP"] = vwap_entries
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_entry_filters.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: EMA Crossover + VWAP entries with slope, extension and momentum filters"
```

---

### Task 8: MACD + MA Ribbon entries

**Files:**
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append; also append `"MACD", "MA Ribbon"` to `GATED_BY_MA50`)

**Interfaces:**
- Produces: `macd_entries`, `ma_ribbon_entries`; `DEFAULT_PARAMS["MACD"] = {"ext_atr": 1.0}`, `DEFAULT_PARAMS["MA Ribbon"] = {"ext_pct": 8.0}`; registry entries. `RIBBON_PERIODS_BY_HORIZON` module dict (moved from the duplicated inline tables).

- [ ] **Step 1: Write the failing tests**

```python
def test_macd_bullish_entries_have_rising_histogram(market_df):
    from swingbot.core.entry_filters import macd_entries
    from swingbot.core.indicators import macd as macd_fn
    from swingbot.core.strategy_types import MACD_PERIODS_BY_HORIZON
    bull, bear = macd_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    f, s, sig = MACD_PERIODS_BY_HORIZON["4w"]
    hist = macd_fn(market_df["Close"], fast=f, slow=s, signal=sig)["histogram"]
    fired = bull[bull].index
    assert (hist.loc[fired] > hist.shift(1).loc[fired]).all()
    assert (hist.shift(1).loc[fired] > hist.shift(2).loc[fired]).all()


def test_ma_ribbon_slope_agreement(market_df):
    from swingbot.core.entry_filters import ma_ribbon_entries, RIBBON_PERIODS_BY_HORIZON
    bull, bear = ma_ribbon_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    _, _, slow_p = RIBBON_PERIODS_BY_HORIZON["4w"]
    slow_sma = market_df["Close"].rolling(slow_p).mean()
    fired = bull[bull].index
    assert (slow_sma.loc[fired] > slow_sma.shift(10).loc[fired]).all()
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_entry_filters.py -k "macd or ribbon" -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
DEFAULT_PARAMS["MACD"] = {"ext_atr": 1.0}


def macd_entries(df, horizon_key, params=None):
    p = _params("MACD", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    fast_p, slow_p, sig_p = MACD_PERIODS_BY_HORIZON.get(horizon_key, (12, 26, 9))
    m = macd(close, fast=fast_p, slow=slow_p, signal=sig_p)
    macd_line, hist = m["macd"], m["histogram"]
    diff = macd_line - m["signal"]

    crossed_up = (diff.shift(1) <= 0) & (diff > 0)
    crossed_down = (diff.shift(1) >= 0) & (diff < 0)
    hist_held_bull = (hist.shift(2) <= 0) & (hist.shift(1) > 0) & (hist > 0)
    hist_held_bear = (hist.shift(2) >= 0) & (hist.shift(1) < 0) & (hist < 0)
    hist_rising2 = (hist > hist.shift(1)) & (hist.shift(1) > hist.shift(2))   # accelerating
    hist_falling2 = (hist < hist.shift(1)) & (hist.shift(1) < hist.shift(2))
    not_extended = (close - ema(close, fast_p)).abs() <= g["atr14"] * p["ext_atr"]
    rsi14 = g["rsi14"]

    bullish = ((crossed_up | hist_held_bull) & hist_rising2 & (macd_line > 0)
               & (rsi14 > 50) & not_extended
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = ((crossed_down | hist_held_bear) & hist_falling2 & (macd_line < 0)
               & (rsi14 < 50) & not_extended
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["MACD"] = macd_entries


# Ribbon periods per horizon -- shared with signals.py (which had its own copy)
RIBBON_PERIODS_BY_HORIZON = {
    "2w": (10, 20, 50), "4w": (10, 20, 50),
    "2m": (20, 50, 100), "3m": (20, 50, 200),
    "4m": (30, 67, 200), "5m": (40, 83, 200), "6m": (50, 100, 200),
    "7m": (60, 117, 200), "8m": (70, 133, 200), "9m": (80, 150, 200),
}

DEFAULT_PARAMS["MA Ribbon"] = {"ext_pct": 8.0}


def ma_ribbon_entries(df, horizon_key, params=None):
    p = _params("MA Ribbon", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    fast_p, mid_p, slow_p = RIBBON_PERIODS_BY_HORIZON.get(horizon_key, (10, 20, 50))
    fast = ema(close, fast_p)
    mid = ema(close, mid_p)
    slow_sma = close.rolling(slow_p).mean()
    diff = fast - mid

    crossed_up = (diff.shift(1) <= 0) & (diff > 0) & (fast > slow_sma) & (mid > slow_sma)
    crossed_down = (diff.shift(1) >= 0) & (diff < 0) & (fast < slow_sma) & (mid < slow_sma)
    slow_rising = slow_sma > slow_sma.shift(10)    # alignment without slope = chop trap
    slow_falling = slow_sma < slow_sma.shift(10)
    rsi14 = g["rsi14"]
    not_ext_bull = (close <= slow_sma * (1 + p["ext_pct"] / 100)) & rsi14.between(48, 70)
    not_ext_bear = (close >= slow_sma * (1 - p["ext_pct"] / 100)) & rsi14.between(30, 52)
    m = macd(close)

    bullish = (crossed_up & slow_rising & not_ext_bull & (m["macd"] > 0)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (crossed_down & slow_falling & not_ext_bear & (m["macd"] < 0)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["MA Ribbon"] = ma_ribbon_entries
```

Also update the test-file constant: `GATED_BY_MA50 = ["EMA Crossover", "VWAP", "Fibonacci", "MACD", "MA Ribbon"]`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_entry_filters.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: MACD + MA Ribbon entries with acceleration and slope filters"
```

---

### Task 9: Support/Resistance + Break & Retest entries

**Files:**
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append; extend `GATED_BY_MA50` with both names)

**Interfaces:**
- Produces: `support_resistance_entries`, `break_retest_entries`; `DEFAULT_PARAMS["Support/Resistance"] = {"base_atr": 4.0, "close_frac": 0.4, "gap_pct": 3.0}`, `DEFAULT_PARAMS["Break & Retest"] = {"hold_tol_pct": 0.5}`; `BRT_RECENT_BARS` and `BRT_RETEST_PCT` module dicts (shared with signals.py later).

- [ ] **Step 1: Write the failing tests**

```python
def test_sr_bullish_breakout_bar_quality(market_df):
    """Every S/R bullish entry must close in the top 40% of its bar and not
    gap more than 3% above the broken level."""
    from swingbot.core.entry_filters import support_resistance_entries, DEFAULT_PARAMS
    from swingbot.core.strategy_types import HORIZONS
    bull, bear = support_resistance_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    lb = HORIZONS["4w"]["sr_lookback"]
    resistance = market_df["High"].rolling(lb).max().shift(1)
    frac = DEFAULT_PARAMS["Support/Resistance"]["close_frac"]
    for ts in bull[bull].index:
        row = market_df.loc[ts]
        rng = row["High"] - row["Low"]
        assert row["Close"] >= row["High"] - frac * rng
        assert row["Open"] <= resistance.loc[ts] * 1.03


def test_break_retest_entry_bar_bounces(market_df):
    """B&R bullish entries must close above the prior bar's high (the retest
    has already turned, we are not catching the falling knife into the level)."""
    from swingbot.core.entry_filters import break_retest_entries
    bull, bear = break_retest_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    prev_high = market_df["High"].shift(1)
    fired = bull[bull].index
    assert (market_df["Close"].loc[fired] > prev_high.loc[fired]).all()
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_entry_filters.py -k "sr_ or retest" -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
DEFAULT_PARAMS["Support/Resistance"] = {"base_atr": 4.0, "close_frac": 0.4, "gap_pct": 3.0}


def support_resistance_entries(df, horizon_key, params=None):
    p = _params("Support/Resistance", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close, high, low, open_ = df["Close"], df["High"], df["Low"], df["Open"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(1)
    support = low.rolling(lookback).min().shift(1)
    vol_avg20 = df["Volume"].rolling(20).mean()
    volume_confirmed = (df["Volume"] / vol_avg20) >= SR_VOLUME_MULTIPLE
    crossed_up = (close.shift(1) <= resistance.shift(1)) & (close > resistance)
    crossed_down = (close.shift(1) >= support.shift(1)) & (close < support)

    # Base quality: the 10 bars BEFORE the breakout were a tight range.
    base_range = (high.rolling(10).max() - low.rolling(10).min()).shift(1)
    base_tight = base_range <= g["atr14"] * p["base_atr"]

    # Breakout bar quality: closes near its high (bull) / low (bear).
    bar_rng = (high - low).replace(0, np.nan)
    strong_close_bull = close >= high - p["close_frac"] * bar_rng
    strong_close_bear = close <= low + p["close_frac"] * bar_rng

    # No exhaustion gap: don't buy a bar that OPENED far beyond the level.
    no_gap_bull = open_ <= resistance * (1 + p["gap_pct"] / 100)
    no_gap_bear = open_ >= support * (1 - p["gap_pct"] / 100)

    bullish = (crossed_up & volume_confirmed & base_tight & strong_close_bull & no_gap_bull
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (crossed_down & volume_confirmed & base_tight & strong_close_bear & no_gap_bear
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Support/Resistance"] = support_resistance_entries


BRT_RECENT_BARS = {
    "2w": 10, "4w": 15, "2m": 20, "3m": 25,
    "4m": 27, "5m": 28, "6m": 30, "7m": 32, "8m": 33, "9m": 35,
}
BRT_RETEST_PCT = {
    "2w": 1.0, "4w": 1.5, "2m": 1.5, "3m": 1.0,
    "4m": 1.5, "5m": 1.5, "6m": 1.5, "7m": 1.5, "8m": 1.5, "9m": 1.5,
}

DEFAULT_PARAMS["Break & Retest"] = {"hold_tol_pct": 0.5}


def break_retest_entries(df, horizon_key, params=None):
    p = _params("Break & Retest", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(lookback)
    support = low.rolling(lookback).min().shift(lookback)
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
    recent = BRT_RECENT_BARS.get(horizon_key, 10)

    broke_up = (high.rolling(recent).max().shift(1) > resistance) & \
               (vol_ratio.rolling(recent).max().shift(1) >= SR_VOLUME_MULTIPLE)
    broke_dn = (low.rolling(recent).min().shift(1) < support) & \
               (vol_ratio.rolling(recent).max().shift(1) >= SR_VOLUME_MULTIPLE)

    dist_to_res = (close - resistance) / resistance.replace(0, np.nan) * 100
    dist_to_sup = (close - support) / support.replace(0, np.nan) * 100
    retest_pct = BRT_RETEST_PCT.get(horizon_key, 1.0)

    # The retest must HOLD the level and the entry bar must have turned:
    held_level_bull = low >= resistance * (1 - p["hold_tol_pct"] / 100)
    held_level_bear = high <= support * (1 + p["hold_tol_pct"] / 100)
    turned_bull = close > high.shift(1)
    turned_bear = close < low.shift(1)
    rsi14 = g["rsi14"]

    bullish = (broke_up & dist_to_res.between(0, retest_pct) & held_level_bull & turned_bull
               & rsi14.between(42, 63)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (broke_dn & dist_to_sup.between(-retest_pct, 0) & held_level_bear & turned_bear
               & rsi14.between(37, 58)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Break & Retest"] = break_retest_entries
```

Extend the test constant: `GATED_BY_MA50 = [..., "Support/Resistance", "Break & Retest"]`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_entry_filters.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: S/R breakout base-quality + Break&Retest hold-and-turn entries"
```

---

### Task 10: RSI entries (dip-buy with confirmation bar)

**Files:**
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Produces: `rsi_entries`; `DEFAULT_PARAMS["RSI"] = {"os_level": 35, "ob_level": 65, "confirm": "prev_high"}`. NOTE: RSI deliberately does NOT use `bull_regime`/`trend50` (dip-buying happens below the averages) — it uses `bull_regime_slope_only`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rsi_bullish_requires_confirmation_bar(market_df):
    from swingbot.core.entry_filters import rsi_entries
    bull, bear = rsi_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    prev_high = market_df["High"].shift(1)
    fired = bull[bull].index
    assert (market_df["Close"].loc[fired] > prev_high.loc[fired]).all()


def test_rsi_bullish_requires_rising_200sma(market_df):
    from swingbot.core.entry_filters import rsi_entries, compute_shared_gates
    g = compute_shared_gates(market_df)
    bull, _ = rsi_entries(market_df, "4w")
    fired = bull[bull].index
    assert g["bull_regime_slope_only"].loc[fired].all()


def test_rsi_no_bullish_in_sustained_downtrend(downtrend_df):
    from swingbot.core.entry_filters import rsi_entries
    bull, _ = rsi_entries(downtrend_df, "4w")
    assert not bull.any()
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_entry_filters.py -k rsi_ -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
DEFAULT_PARAMS["RSI"] = {"os_level": 35, "ob_level": 65, "confirm": "prev_high"}


def rsi_entries(df, horizon_key, params=None):
    """Oversold bounce inside a structurally healthy uptrend. Dip-buying by
    construction happens BELOW the short MAs, so this strategy uses the
    slope-only regime gate (200-SMA rising) instead of close>MA gates."""
    p = _params("RSI", params)
    g = compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    rsi14 = g["rsi14"]
    os_, ob = p["os_level"], p["ob_level"]

    consec_oversold = (rsi14.shift(1) < os_) & (rsi14.shift(2) < os_)
    consec_overbought = (rsi14.shift(1) > ob) & (rsi14.shift(2) > ob)
    crossed_up = consec_oversold & (rsi14 >= os_)
    crossed_down = consec_overbought & (rsi14 <= ob)

    if p["confirm"] == "prev_high":
        confirm_bull = close > high.shift(1)
        confirm_bear = close < low.shift(1)
    else:  # "prev_close"
        confirm_bull = close > close.shift(1)
        confirm_bear = close < close.shift(1)

    bounce_started = close > close.shift(3)     # not a falling knife
    fade_started = close < close.shift(3)
    ma200 = g["ma200"]
    ma200_down = (ma200 < ma200.shift(120)).fillna(False)

    bullish = (crossed_up & g["bull_regime_slope_only"] & bounce_started & confirm_bull
               & (rsi14 < 40)
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (crossed_down & ma200_down & fade_started & confirm_bear
               & (rsi14 > 60)
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["RSI"] = rsi_entries
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_entry_filters.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: RSI dip-buy entries with confirmation bar + slope-only regime gate"
```

---

### Task 11: RSI Divergence + Volume Profile entries

**Files:**
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Produces: `rsi_divergence_entries`, `volume_profile_entries`; `DEFAULT_PARAMS["RSI Divergence"] = {"rsi_reclaim": 40}`, `DEFAULT_PARAMS["Volume Profile"] = {"node_share": 8.0, "prox_pct": 1.5}`; helper `_vectorized_hvn(df, lookback, n_bins=20) -> tuple[pd.Series, pd.Series]` returning (hvn_price, hvn_share_pct) per bar.

- [ ] **Step 1: Write the failing tests**

```python
def test_hvn_share_sums_correctly():
    """On a series that trades one price 80% of the time, the HVN share must
    reflect that dominance."""
    from swingbot.core.entry_filters import _vectorized_hvn
    closes = np.where(np.arange(300) % 5 == 0, 110.0, 100.0)  # 20% at 110
    df = make_ohlcv(closes, spread_pct=0.5)
    hvn, share = _vectorized_hvn(df, lookback=60)
    assert hvn.iloc[-1] == pytest.approx(100.0, rel=0.05)
    assert share.iloc[-1] > 50.0


def test_volume_profile_entries_respect_node_share(market_df):
    from swingbot.core.entry_filters import volume_profile_entries, _vectorized_hvn, DEFAULT_PARAMS
    from swingbot.core.strategy_types import HORIZONS
    bull, bear = volume_profile_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    _, share = _vectorized_hvn(market_df, HORIZONS["4w"]["sr_lookback"])
    min_share = DEFAULT_PARAMS["Volume Profile"]["node_share"]
    fired = bull[bull].index
    assert (share.loc[fired] >= min_share).all()


def test_rsi_divergence_bull_entries_have_turning_rsi(market_df):
    from swingbot.core.entry_filters import rsi_divergence_entries, DEFAULT_PARAMS
    from swingbot.core.indicators import rsi as rsi_fn
    bull, bear = rsi_divergence_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)
    r = rsi_fn(market_df["Close"], 14)
    reclaim = DEFAULT_PARAMS["RSI Divergence"]["rsi_reclaim"]
    fired = bull[bull].index
    assert (r.loc[fired] > reclaim).all()
    assert (r.loc[fired] > r.shift(1).loc[fired]).all()
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_entry_filters.py -k "hvn or profile or divergence" -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
DEFAULT_PARAMS["RSI Divergence"] = {"rsi_reclaim": 40}


def rsi_divergence_entries(df, horizon_key, params=None):
    """Hidden divergence (trend continuation), rolling formulation, plus a
    confirmation: RSI has actually started turning in the trade direction.
    Divergence alone marks potential -- the reclaim marks the entry."""
    p = _params("RSI Divergence", params)
    g = compute_shared_gates(df)
    close = df["Close"]
    rsi14 = g["rsi14"]
    lb = 20
    reclaim = p["rsi_reclaim"]

    price_hl = close > close.rolling(lb).min().shift(lb)    # higher low
    rsi_ll = rsi14 < rsi14.rolling(lb).min().shift(lb)      # RSI lower low
    price_lh = close < close.rolling(lb).max().shift(lb)
    rsi_hh = rsi14 > rsi14.rolling(lb).max().shift(lb)

    turn_bull = (rsi14 > reclaim) & (rsi14 > rsi14.shift(1))
    turn_bear = (rsi14 < (100 - reclaim)) & (rsi14 < rsi14.shift(1))

    bullish = (price_hl & rsi_ll & turn_bull & rsi14.between(28, 52)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (price_lh & rsi_hh & turn_bear & rsi14.between(48, 72)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["RSI Divergence"] = rsi_divergence_entries


def _vectorized_hvn(df, lookback, n_bins=20):
    """Per-bar High Volume Node price AND its share of window volume (%).
    Same numpy approach as the old backtest.py loop, extended to keep the
    winning bucket's volume share so node significance can gate entries."""
    _high, _low = df["High"].values, df["Low"].values
    _vol = df["Volume"].values
    _mid = (_high + _low) / 2
    n = len(df)
    hvn = np.full(n, np.nan)
    share = np.full(n, np.nan)
    for i in range(lookback, n):
        lo_idx = i - lookback
        pmin = _low[lo_idx:i].min()
        pmax = _high[lo_idx:i].max()
        rng = pmax - pmin
        if rng <= 0:
            continue
        idx = np.minimum(((_mid[lo_idx:i] - pmin) / rng * n_bins).astype(int), n_bins - 1)
        bins = np.bincount(idx, weights=_vol[lo_idx:i], minlength=n_bins)
        total = bins.sum()
        if total <= 0:
            continue
        k = bins.argmax()
        hvn[i] = pmin + (k + 0.5) * rng / n_bins
        share[i] = bins[k] / total * 100
    return pd.Series(hvn, index=df.index), pd.Series(share, index=df.index)


DEFAULT_PARAMS["Volume Profile"] = {"node_share": 8.0, "prox_pct": 1.5}


def volume_profile_entries(df, horizon_key, params=None):
    p = _params("Volume Profile", params)
    h = HORIZONS[horizon_key]
    g = compute_shared_gates(df)
    close = df["Close"]

    hvn, share = _vectorized_hvn(df, h["sr_lookback"])
    dist_pct = (close - hvn) / hvn.replace(0, np.nan) * 100
    significant = share >= p["node_share"]      # marginal argmax nodes are noise
    rsi14 = g["rsi14"]
    bounce_bull = close > close.shift(1)
    bounce_bear = close < close.shift(1)

    bullish = (dist_pct.between(0, p["prox_pct"]) & significant & bounce_bull
               & rsi14.between(44, 64)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (dist_pct.between(-p["prox_pct"], 0) & significant & bounce_bear
               & rsi14.between(36, 56)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Volume Profile"] = volume_profile_entries
```

Extend the test constant: `GATED_BY_MA50 = [..., "RSI Divergence", "Volume Profile"]`.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_entry_filters.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: RSI Divergence reclaim confirmation + Volume Profile node significance"
```

---

### Task 12: Elliott Wave entries + `wave0` in indicators

**Files:**
- Modify: `swingbot/core/indicators.py:255,261` (record `wave0`)
- Modify: `swingbot/core/entry_filters.py`
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- `elliott_wave3_entries` `entry_levels` values become `{"wave0": p0, "wave1": p1, "wave2": p2}` (additive — existing consumers read `wave1`/`wave2` and keep working).
- Produces: `elliott_wave_entries`; `DEFAULT_PARAMS["Elliott Wave"] = {"depth_min": 0.30, "depth_max": 0.80}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_elliott_entry_levels_include_wave0(market_df):
    from swingbot.core.indicators import elliott_wave3_entries
    _, _, levels = elliott_wave3_entries(market_df, 7.0)
    for lv in levels.values():
        assert set(lv) == {"wave0", "wave1", "wave2"}


def test_elliott_only_fires_on_4w(market_df):
    from swingbot.core.entry_filters import elliott_wave_entries
    for hk in ("2w", "2m", "3m", "6m"):
        bull, bear = elliott_wave_entries(market_df, hk)
        assert not bull.any() and not bear.any()
    bull, bear = elliott_wave_entries(market_df, "4w")
    assert_entry_invariants(bull, bear, market_df)


def test_elliott_wave2_depth_gate(market_df):
    """Every fired entry must correspond to a wave-2 retracing 30-80% of wave 1."""
    from swingbot.core.entry_filters import elliott_wave_entries, DEFAULT_PARAMS
    from swingbot.core.indicators import elliott_wave3_entries
    from swingbot.core.strategy_types import HORIZONS
    bull, bear = elliott_wave_entries(market_df, "4w")
    _, _, levels = elliott_wave3_entries(market_df, HORIZONS["4w"]["max_risk_pct"])
    p = DEFAULT_PARAMS["Elliott Wave"]
    positions = {market_df.index.get_loc(ts) for ts in bull[bull].index.union(bear[bear].index)}
    for j in positions:
        lv = levels[j]
        depth = abs(lv["wave1"] - lv["wave2"]) / abs(lv["wave1"] - lv["wave0"])
        assert p["depth_min"] <= depth <= p["depth_max"]
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_entry_filters.py -k elliott -v` — Expected: FAIL (wave0 KeyError / ImportError).

- [ ] **Step 3: Implement**

3a. In `indicators.py`, change both `entry_levels[j] = {"wave1": p1, "wave2": p2}` lines (255 and 261) to:

```python
                    entry_levels[j] = {"wave0": p0, "wave1": p1, "wave2": p2}
```

3b. In `entry_filters.py`:

```python
DEFAULT_PARAMS["Elliott Wave"] = {"depth_min": 0.30, "depth_max": 0.80}


def elliott_wave_entries(df, horizon_key, params=None):
    """Wave-3 breakout approximation. Only the 4w horizon fires: 2w pivots
    are noise, >=2m pivot approximation degrades (documented in the old
    backtest). Adds the textbook wave-2 depth check (30-80% of wave 1)."""
    p = _params("Elliott Wave", params)
    if horizon_key != "4w":
        return _off(df), _off(df)
    g = compute_shared_gates(df)
    threshold_pct = HORIZONS[horizon_key]["max_risk_pct"]
    bull_raw, bear_raw, levels = elliott_wave3_entries(df, threshold_pct)

    depth_ok = _off(df)
    for j, lv in levels.items():
        impulse = abs(lv["wave1"] - lv["wave0"])
        if impulse <= 0:
            continue
        depth = abs(lv["wave1"] - lv["wave2"]) / impulse
        depth_ok.iloc[j] = p["depth_min"] <= depth <= p["depth_max"]

    rsi14 = g["rsi14"]
    rsi_rising = rsi14 > rsi14.shift(2)
    rsi_falling = rsi14 < rsi14.shift(2)

    bullish = (bull_raw & depth_ok & (rsi14 > 55) & rsi_rising
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (bear_raw & depth_ok & (rsi14 < 45) & rsi_falling
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


ENTRY_FUNCS["Elliott Wave"] = elliott_wave_entries
```

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/indicators.py swingbot/core/entry_filters.py tests/test_entry_filters.py
git commit -m "feat: Elliott Wave entries with wave-2 depth gate (wave0 recorded in pivots)"
```

---

### Task 13: `backtest.py` delegates `_vectorized_entries` to `entry_filters`

**Files:**
- Modify: `swingbot/core/backtest.py` (replace the whole `_vectorized_entries` body, ~lines 88–362)
- Test: `tests/test_backtest_engine.py` (append)

**Interfaces:**
- `_vectorized_entries(df, strategy, horizon_key)` keeps its exact signature (`backtest_confluence.py` imports it) but becomes a delegation. All per-strategy `if strategy == ...` blocks and their local indicator code are DELETED from `backtest.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_vectorized_entries_delegates_to_entry_filters(market_df):
    """backtest must produce byte-identical entries to entry_filters for
    every strategy -- no drift, that is the whole point of the redesign."""
    from swingbot.core.backtest import _vectorized_entries, ALL_STRATEGIES
    from swingbot.core.entry_filters import entries_for
    for strat in ALL_STRATEGIES:
        b1, s1 = _vectorized_entries(market_df, strat, "4w")
        b2, s2 = entries_for(strat, market_df, "4w")
        assert b1.equals(b2) and s1.equals(s2), strat
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_backtest_engine.py::test_vectorized_entries_delegates_to_entry_filters -v`
Expected: FAIL — old inline logic differs from `entry_filters` (e.g., Fibonacci direction fix).

- [ ] **Step 3: Implement**

Replace the entire `_vectorized_entries` function in `backtest.py` (keep the name and signature, delete all per-strategy blocks) with:

```python
def _vectorized_entries(df: pd.DataFrame, strategy: str, horizon_key: str):
    """Single source of entry logic lives in entry_filters.py -- shared with
    the live scanner so backtest and live signals cannot drift. Kept as a
    named function here because backtest_confluence.py imports it."""
    from .entry_filters import entries_for
    return entries_for(strategy, df, horizon_key)
```

Remove now-unused imports from `backtest.py` (`ema`, `rsi`, `rolling_vwap`, `elliott_wave3_entries` — keep `atr`; keep `HORIZONS`, `MIN_BARS`; keep `FIB_TOLERANCE_PCT`/`SR_VOLUME_MULTIPLE` only if still referenced by `_trade_plan_at`, check with grep).

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests -v` — Expected: PASS (engine tests from Task 3 still pass because they monkeypatch `_vectorized_entries` itself).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtest.py tests/test_backtest_engine.py
git commit -m "refactor: backtest entries delegate to entry_filters (kills live/backtest drift)"
```

---

### Task 14: Live `signals.py` triggers delegate to `entry_filters`

**Files:**
- Modify: `swingbot/core/signals.py` (11 signal functions — trigger logic only; `details` and non-triggered bias reporting stay)
- Test: `tests/test_entry_filters.py` (append)

**Interfaces:**
- Consumes: `entries_for` from Task 5. Add `from .entry_filters import entries_for` to `signals.py` imports.
- Every signal function keeps its exact signature and `SignalResult` shape.

- [ ] **Step 1: Write the failing test**

```python
def test_live_signals_agree_with_entry_filters(market_df):
    """For every strategy and a spread of horizons, the live signal's
    `triggered` flag must equal the last bar of the entry-filter series."""
    from swingbot.core.strategy import STRATEGY_FUNCS
    from swingbot.core.entry_filters import entries_for
    for strat, func in STRATEGY_FUNCS.items():
        for hk in ("2w", "4w", "2m"):
            res = func("TEST", market_df, hk)
            bull, bear = entries_for(strat, market_df, hk)
            expected = bool(bull.iloc[-1] or bear.iloc[-1])
            assert res.triggered == expected, f"{strat}/{hk}"
            if expected:
                assert res.trend == ("bullish" if bull.iloc[-1] else "bearish")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_entry_filters.py::test_live_signals_agree_with_entry_filters -v`
Expected: FAIL for at least some strategies (live logic is currently much looser).

- [ ] **Step 3: Implement — same mechanical change in each of the 11 functions**

The pattern: compute `bull_e, bear_e = entries_for("<Strategy Name>", df, horizon_key)` and set `trend`/`triggered` from the LAST bar; keep the function's existing indicator computations only where the `details` dict or bias fallback needs them. Exact replacement for each function's trigger block:

`ema_cross_signal` — replace the `crossed_up/crossed_down` + `if/elif/else` block with:

```python
    bull_e, bear_e = entries_for("EMA Crossover", df, horizon_key)
    if bool(bull_e.iloc[-1]):
        trend, triggered = "bullish", True
    elif bool(bear_e.iloc[-1]):
        trend, triggered = "bearish", True
    else:
        trend, triggered = ("bullish" if curr_diff > 0 else "bearish"), False
```

`vwap_signal` — same shape:

```python
    bull_e, bear_e = entries_for("VWAP", df, horizon_key)
    if bool(bull_e.iloc[-1]):
        trend, triggered = "bullish", True
    elif bool(bear_e.iloc[-1]):
        trend, triggered = "bearish", True
    else:
        trend, triggered = ("bullish" if curr_diff >= 0 else "bearish"), False
```

`fibonacci_signal` — keep the level/`details` computation; replace the `if is_testing_level and moving_up: ... elif ... else` block with:

```python
    bull_e, bear_e = entries_for("Fibonacci", df, horizon_key)
    if bool(bull_e.iloc[-1]):
        trend, triggered = "bullish", True
    elif bool(bear_e.iloc[-1]):
        trend, triggered = "bearish", True
    else:
        midpoint = levels[0.5]
        trend, triggered = ("bullish" if close > midpoint else "bearish"), False
```

`support_resistance_signal` — keep resistance/support/volume `details` computation; replace the `breakout_up/breakdown_down` decision block with:

```python
    bull_e, bear_e = entries_for("Support/Resistance", df, horizon_key)
    if bool(bull_e.iloc[-1]):
        trend, triggered = "bullish", True
    elif bool(bear_e.iloc[-1]):
        trend, triggered = "bearish", True
    else:
        midpoint = (resistance + support) / 2 if pd.notna(resistance) and pd.notna(support) else close
        trend, triggered = ("bullish" if close >= midpoint else "bearish"), False
```

`rsi_signal`, `macd_signal`, `elliott_wave_signal`, `ma_ribbon_signal`, `break_retest_signal`, `rsi_divergence_signal`, `volume_profile_signal` — identical mechanical replacement with their strategy names (`"RSI"`, `"MACD"`, `"Elliott Wave"`, `"MA Ribbon"`, `"Break & Retest"`, `"RSI Divergence"`, `"Volume Profile"`), keeping each function's existing `else`-branch bias line and `details` construction. For `rsi_divergence_signal`, the divergence-scan loops remain solely to populate `details` when triggered; the `triggered` flag itself must come from `entries_for`.

- [ ] **Step 4: Run the whole suite** — `python -m pytest tests -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/signals.py tests/test_entry_filters.py
git commit -m "feat: live signal triggers now use the shared entry filters"
```

---

### Task 15: `!backtest` command output — scratch/timeout visibility + honest 80% flag

**Files:**
- Modify: `swingbot/commands/backtest.py` (`_format_backtest_table` ~line 101, `_format_per_strategy_winrate` ~line 119, and the long help text ~line 324)

**Interfaces:**
- Consumes: `BacktestSummary.scratches` from Task 3.
- The pooled 80% flag becomes ✅ only when `win_rate >= 80 AND expectancy > 0 AND (scratches+timeouts) <= 50% of closed trades`.

- [ ] **Step 1: Update `_format_backtest_table`** — add `Scr`/`TO` columns:

```python
def _format_backtest_table(header, summaries):
    lines = [header, "```"]
    lines.append(f"{'Strategy':18s} {'Horiz':5s} {'Sig':>4s} {'Eval':>4s} {'Scr':>4s} {'TO':>4s} {'Win%':>6s} {'ExpR':>6s} {'MaxDD%':>7s} {'AvgDays':>7s}")
    for s in summaries:
        wr = f"{s.win_rate:.0f}" if s.win_rate is not None else "n/a"
        er = f"{s.expectancy_r:.2f}" if s.expectancy_r is not None else "n/a"
        dd = f"{s.max_drawdown_pct:.1f}" if s.max_drawdown_pct is not None else "n/a"
        ad = f"{s.avg_holding_days:.0f}" if s.avg_holding_days is not None else "n/a"
        lines.append(f"{s.strategy:18s} {s.horizon_key:5s} {s.total_signals:4d} {s.evaluated:4d} {s.scratches:4d} {s.timeouts:4d} {wr:>6s} {er:>6s} {dd:>7s} {ad:>7s}")
    lines.append("```")
    lines.append(
        "Sig=signals, Eval=win+loss trades, Scr=break-even scratches, TO=timeouts (marked to market), "
        "Win%=wins/(wins+losses), ExpR=expectancy in R over ALL closed trades (>0 = profitable).\n"
        "⚠️ No fees/slippage, survivorship bias."
    )
    return "\n".join(lines)
```

- [ ] **Step 2: Update `_format_per_strategy_winrate`**:

```python
def _format_per_strategy_winrate(summaries):
    """One row per STRATEGY (all horizons pooled) -- the number that answers
    'does this strategy hit 80% win rate AND make money'. The flag requires
    all three: win rate >= 80, expectancy > 0, and scratches+timeouts <= 50%
    of closed trades (else the win rate is resting on excluded trades)."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"evaluated": 0, "wins": 0, "losses": 0,
                               "scratches": 0, "timeouts": 0, "r_weighted": 0.0})
    for s in summaries:
        closed = s.evaluated + s.scratches + s.timeouts
        if not closed:
            continue
        a = agg[s.strategy]
        a["evaluated"] += s.evaluated
        a["wins"] += s.wins
        a["losses"] += s.losses
        a["scratches"] += s.scratches
        a["timeouts"] += s.timeouts
        if s.expectancy_r is not None:
            a["r_weighted"] += s.expectancy_r * closed

    lines = ["**Win rate by strategy** (all horizons combined):", "```",
             f"{'Strategy':20s} {'Eval':>5s} {'Scr':>4s} {'TO':>4s} {'Win%':>6s} {'ExpR':>7s}  Pass"]
    for strat in ALL_STRATEGIES:
        a = agg.get(strat)
        closed = (a["evaluated"] + a["scratches"] + a["timeouts"]) if a else 0
        if not closed or a["evaluated"] == 0:
            lines.append(f"{strat:20s} {'0':>5s} {'':>4s} {'':>4s}    n/a     n/a  —")
            continue
        wr = a["wins"] / a["evaluated"] * 100
        er = a["r_weighted"] / closed
        excluded_share = (a["scratches"] + a["timeouts"]) / closed
        flag = "✅" if (wr >= 80 and er > 0 and excluded_share <= 0.5) else "❌"
        lines.append(f"{strat:20s} {a['evaluated']:5d} {a['scratches']:4d} {a['timeouts']:4d} {wr:5.1f}% {er:+7.3f}  {flag}")
    lines.append("```")
    lines.append(
        "Pass = win rate ≥80% AND expectancy >0 AND ≤50% of closed trades excluded "
        "(scratches/timeouts). ExpR is averaged over ALL closed trades."
    )
    return "\n".join(lines)
```

- [ ] **Step 3: Rewrite the win-rate-vs-expectancy help text** (~line 324) — replace the paragraph explaining that 80% can be "mechanically cleared" at tiny R:R with:

```
Targets are sized at 0.35–0.40× the stop distance (see STRATEGY_RR_OVERRIDE);
at 80% win rate that is profitable (break-even would be 0.25×). After a trade
covers half the distance to target, the stop moves to entry — those exits are
"scratches" (~0R), shown separately and excluded from the win rate but included
in expectancy. Timeouts are marked to market, not ignored.
```

- [ ] **Step 4: Run the suite + import check**

Run: `python -m pytest tests -v && python -c "import swingbot.commands.backtest"`
Expected: PASS / clean import.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/backtest.py
git commit -m "feat: backtest command shows scratches/timeouts, honest 80%+profitable flag"
```

---

### Task 16: Data cache script

**Files:**
- Create: `scripts/fetch_backtest_data.py`
- Modify: `.gitignore` (add `data/backtest_cache/`)

**Interfaces:**
- Produces: `data/backtest_cache/<sanitized-ticker>.csv` (columns `Date,Open,High,Low,Close,Volume`), 2018-06-01 → 2025-12-31.
- Produces (importable by other scripts via `sys.path` trick or copy): `cache_path(ticker) -> Path`, `load_cached(ticker) -> pd.DataFrame | None`.

- [ ] **Step 1: Create `scripts/fetch_backtest_data.py`**

```python
#!/usr/bin/env python3
"""One-time OHLCV cache for the redesign backtests. Downloads every
watchlist ticker 2018-06-01 -> 2025-12-31 (>=18 months warm-up before the
2020 train window: the regime gate needs 200-SMA + a 120-bar shift) and
saves one CSV per ticker under data/backtest_cache/. Re-running skips
tickers already cached; delete the folder to force a refresh."""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

CACHE_DIR = ROOT / "data" / "backtest_cache"
START, END = "2018-06-01", "2025-12-31"


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def cache_path(ticker: str) -> Path:
    safe = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}.csv"


def load_cached(ticker: str) -> pd.DataFrame | None:
    p = cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def fetch(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    if df is None or df.empty or len(df) < 260:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_watchlist()
    ok, skipped, failed = 0, 0, []
    for t in sorted(tickers):
        if cache_path(t).exists():
            skipped += 1
            continue
        df = fetch(t)
        if df is None:
            print(f"  x {t}: no data")
            failed.append(t)
            continue
        df.to_csv(cache_path(t))
        ok += 1
        print(f"  + {t}: {len(df)} bars ({df.index[0].date()} -> {df.index[-1].date()})")
    print(f"\nDone: {ok} fetched, {skipped} already cached, {len(failed)} failed {failed or ''}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add `data/backtest_cache/` to `.gitignore`**

- [ ] **Step 3: Run it**

Run: `python scripts/fetch_backtest_data.py`
Expected: one `+ TICKER: ~1900 bars` line per ticker; a handful of failures is acceptable (delisted/renamed tickers) — note them.

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch_backtest_data.py .gitignore
git commit -m "feat: cached OHLCV fetcher for redesign backtests"
```

---

### Task 17: Acceptance harness `run_backtest_range.py` (replaces `run_backtest_2025.py`)

**Files:**
- Create: `scripts/run_backtest_range.py`
- Delete: `run_backtest_2025.py`

**Interfaces:**
- CLI: `python scripts/run_backtest_range.py --train` | `--validation` | `--from YYYY-MM-DD --to YYYY-MM-DD` [`--strategy "Name"`] [`--json out.json`].
- Consumes: `load_cached`/`load_watchlist`/`cache_path` from `scripts/fetch_backtest_data.py` (same directory import), `run_backtest`/`ALL_STRATEGIES` from `swingbot.core.backtest`, `HORIZONS` from `swingbot.core.strategy_types`.
- Produces per-strategy pooled table with `N / Win% / ExpR / Scr% / TO% / PASS` where PASS = spec §2 gate, plus a per-strategy×horizon breakdown, saved to `backtest_range_summary.txt` + optional JSON.

- [ ] **Step 1: Create `scripts/run_backtest_range.py`**

```python
#!/usr/bin/env python3
"""Acceptance harness: runs every strategy x horizon x cached ticker and
pools results per strategy over an entry-date window.

    python scripts/run_backtest_range.py --train        # 2020-01-01 .. 2023-12-31
    python scripts/run_backtest_range.py --validation   # 2024-01-01 .. 2025-12-31 (run ONCE, at the end)
    python scripts/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 --strategy "RSI"

PASS gate per spec: win_rate >= 80, expectancy_r > 0, N >= 30 (train) / 15
(validation), scratches+timeouts <= 50% of closed trades."""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")


def window_trades(summary, date_from, date_to):
    return [t for t in summary.trades if date_from <= t.entry_date <= date_to]


def pool(trades):
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = [t for t in ev if t.outcome == "win"]
    scr = [t for t in trades if t.outcome == "scratch"]
    to = [t for t in trades if t.outcome == "timeout"]
    closed = len(trades)
    return {
        "n_eval": len(ev), "wins": len(wins), "losses": len(ev) - len(wins),
        "scratches": len(scr), "timeouts": len(to), "closed": closed,
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": (len(scr) + len(to)) / closed if closed else 0.0,
    }


def passes(stats, min_n):
    return (stats["n_eval"] >= min_n
            and stats["win_rate"] is not None and stats["win_rate"] >= 80
            and stats["expectancy_r"] is not None and stats["expectancy_r"] > 0
            and stats["excluded_share"] <= 0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    if args.train:
        date_from, date_to, min_n, label = *TRAIN, 30, "TRAIN"
    elif args.validation:
        date_from, date_to, min_n, label = *VALIDATION, 15, "VALIDATION"
    else:
        if not (args.date_from and args.date_to):
            ap.error("need --train, --validation, or --from/--to")
        date_from, date_to, min_n, label = args.date_from, args.date_to, 15, "CUSTOM"

    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    by_strategy = defaultdict(list)
    by_combo = defaultdict(list)

    tickers = sorted(load_watchlist())
    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)
        for hk in HORIZONS:
            for strat in strategies:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True)
                except Exception as e:
                    print(f"    ! {strat}/{hk}: {e}")
                    continue
                tr = window_trades(s, date_from, date_to)
                by_strategy[strat].extend(tr)
                by_combo[(strat, hk)].extend(tr)

    lines = [f"== {label} {date_from} .. {date_to} | pass: WR>=80, ExpR>0, N>={min_n}, excl<=50% ==",
             f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s} {'Scr':>5s} {'TO':>5s} {'Excl%':>6s}  PASS"]
    results = {}
    for strat in strategies:
        st = pool(by_strategy[strat])
        results[strat] = st
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        flag = "PASS" if passes(st, min_n) else "FAIL"
        lines.append(f"{strat:22s} {st['n_eval']:5d} {wr:>6s} {er:>7s} {st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%  {flag}")

    lines.append("\n-- per strategy x horizon (for gating decisions) --")
    lines.append(f"{'Strategy':22s} {'Horiz':6s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s}")
    for (strat, hk), tr in sorted(by_combo.items()):
        st = pool(tr)
        if st["closed"] == 0:
            continue
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        lines.append(f"{strat:22s} {hk:6s} {st['n_eval']:5d} {wr:>6s} {er:>7s}")

    report = "\n".join(lines)
    print("\n" + report)
    Path("backtest_range_summary.txt").write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}, indent=2))
    print("\nSaved backtest_range_summary.txt")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete the stale runner**

```bash
git rm run_backtest_2025.py
```

- [ ] **Step 3: Smoke-run on one strategy**

Run: `python scripts/run_backtest_range.py --train --strategy "RSI"`
Expected: a table with one strategy row and per-horizon breakdown; no tracebacks. Record the numbers — this is the pre-tuning baseline.

- [ ] **Step 4: Baseline run for all strategies** (this takes minutes)

Run: `python scripts/run_backtest_range.py --train`
Expected: full table. Save a copy: `cp backtest_range_summary.txt docs/superpowers/results/2026-07-baseline-train.txt` (create the `docs/superpowers/results/` directory).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_backtest_range.py docs/superpowers/results/
git commit -m "feat: train/validation acceptance harness; remove stale 2025 runner"
```

---

### Task 18: Grid-sweep tuner `tune_strategy.py`

**Files:**
- Create: `scripts/tune_strategy.py`

**Interfaces:**
- CLI: `python scripts/tune_strategy.py --strategy "Support/Resistance" [--be-trigger 0.5]` — sweeps that strategy's `PARAM_GRID` on the TRAIN window only, prints ranked configs.
- Mechanism: mutates `entry_filters.DEFAULT_PARAMS[strategy]` in place per grid point (restores after), and sets `swingbot.core.backtest.BREAKEVEN_TRIGGER_FRACTION` module attribute when `--be-trigger` given (a from-import binds it as a module global, so setattr works).

- [ ] **Step 1: Create `scripts/tune_strategy.py`**

```python
#!/usr/bin/env python3
"""Grid sweep of one strategy's tunables over the TRAIN window ONLY
(2020-01-01 .. 2023-12-31). Never point this at the validation window --
that is the whole point of having one.

Selection rule (spec section 9): among configs with WR>=80, ExpR>0, N>=30,
pick max expectancy. If none qualify, the ranking output still shows the
best candidates so the failure policy (gating directions/horizons) can be
applied by hand in Task 19."""
import argparse
import itertools
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
import swingbot.core.backtest as bt
import swingbot.core.entry_filters as ef
from swingbot.core.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")

PARAM_GRID = {
    "EMA Crossover":      {"rsi_dip": [40, 45, 50], "ext_atr": [0.75, 1.0, 1.5]},
    "VWAP":               {"ext_pct": [1.0, 1.5, 2.0], "hold_bars_other": [2, 3]},
    "Fibonacci":          {"ratios": [(0.382, 0.5, 0.618), (0.5, 0.618)],
                           "rsi_bull": [(35, 58), (40, 60)]},
    "Support/Resistance": {"base_atr": [3.0, 4.0, 5.0], "close_frac": [0.3, 0.4, 0.5]},
    "RSI":                {"os_level": [30, 35], "confirm": ["prev_high", "prev_close"]},
    "MACD":               {"ext_atr": [0.75, 1.0, 1.5]},
    "Elliott Wave":       {"depth_min": [0.30, 0.38], "depth_max": [0.78, 0.80]},
    "MA Ribbon":          {"ext_pct": [6.0, 8.0, 10.0]},
    "Break & Retest":     {"hold_tol_pct": [0.3, 0.5, 0.8]},
    "RSI Divergence":     {"rsi_reclaim": [38, 40, 45]},
    "Volume Profile":     {"node_share": [6.0, 8.0, 10.0], "prox_pct": [1.0, 1.5, 2.0]},
}


def run_config(strategy, dfs):
    trades = []
    for ticker, df in dfs.items():
        for hk in HORIZONS:
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True)
            except Exception:
                continue
            trades.extend(t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1])
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))
    return {
        "n_eval": len(ev),
        "win_rate": wins / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--be-trigger", type=float, default=None)
    args = ap.parse_args()
    strategy = args.strategy
    if strategy not in PARAM_GRID:
        ap.error(f"unknown strategy {strategy!r}; one of {list(PARAM_GRID)}")
    if args.be_trigger is not None:
        bt.BREAKEVEN_TRIGGER_FRACTION = args.be_trigger

    dfs = {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}
    print(f"{len(dfs)} tickers loaded from cache")

    grid = PARAM_GRID[strategy]
    keys = list(grid)
    baseline = dict(ef.DEFAULT_PARAMS[strategy])
    rows = []
    try:
        for combo in itertools.product(*(grid[k] for k in keys)):
            params = dict(zip(keys, combo))
            ef.DEFAULT_PARAMS[strategy].update(params)
            stats = run_config(strategy, dfs)
            rows.append((params, stats))
            wr = f"{stats['win_rate']:.1f}" if stats["win_rate"] is not None else "n/a"
            er = f"{stats['expectancy_r']:+.3f}" if stats["expectancy_r"] is not None else "n/a"
            print(f"  {params} -> N={stats['n_eval']} WR={wr} ExpR={er} excl={stats['excluded_share']*100:.0f}%")
    finally:
        ef.DEFAULT_PARAMS[strategy] = baseline

    qualifying = [(p, s) for p, s in rows
                  if s["n_eval"] >= 30 and (s["win_rate"] or 0) >= 80
                  and (s["expectancy_r"] or 0) > 0 and s["excluded_share"] <= 0.5]
    print(f"\n{len(qualifying)}/{len(rows)} configs qualify (WR>=80, ExpR>0, N>=30, excl<=50%)")
    ranked = sorted(qualifying or rows,
                    key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)
    print("Top 5:")
    for p, s in ranked[:5]:
        print(f"  {p} -> N={s['n_eval']} WR={s['win_rate'] and round(s['win_rate'],1)} ExpR={s['expectancy_r'] and round(s['expectancy_r'],3)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run**

Run: `python scripts/tune_strategy.py --strategy "MACD"`
Expected: 3 config lines + ranking, no tracebacks.

- [ ] **Step 3: Commit**

```bash
git add scripts/tune_strategy.py
git commit -m "feat: train-window grid tuner for per-strategy entry params"
```

---

### Task 19: Tune on train, apply parameters + gates

This task is empirical — its outputs depend on the data. Follow the decision rules mechanically; do not improvise new filters here.

**Files:**
- Modify: `swingbot/core/entry_filters.py` (`DEFAULT_PARAMS` values only)
- Modify: `swingbot/core/strategy_types.py` (`STRATEGY_GATES` entries, `BREAKEVEN_TRIGGER_FRACTION` if changed)
- Create: `docs/superpowers/results/2026-07-train-tuning.md`

- [ ] **Step 1: Pick the break-even trigger.** Run `python scripts/tune_strategy.py --strategy "MACD" --be-trigger X` for X in 0.4 / 0.5 / 0.6 and repeat for `"RSI"`. Pick the X whose best configs have the highest expectancy (win-rate ties broken toward higher X — later trigger = fewer scratches). If the winner isn't 0.5, update `BREAKEVEN_TRIGGER_FRACTION` in `strategy_types.py`.

- [ ] **Step 2: Sweep every strategy** — for each of the 11 names in `PARAM_GRID`, run `python scripts/tune_strategy.py --strategy "<name>"` and record the top table in `docs/superpowers/results/2026-07-train-tuning.md`.

- [ ] **Step 3: Apply winners** — for each strategy with ≥1 qualifying config, write the winning values into `DEFAULT_PARAMS` in `entry_filters.py` (values only; structure unchanged).

- [ ] **Step 4: Gate the failures** — for each strategy with NO qualifying config, look at the per-horizon/per-direction breakdown (`python scripts/run_backtest_range.py --train --strategy "<name>"` plus splitting trades by `t.direction` — add a temporary print if needed). Apply, in this order, the mildest gate that makes the strategy qualify on train:
  1. `{"directions": ("bullish",)}` — drop the bearish side (expected for most strategies on this tape).
  2. `{"directions": (...), "horizons": (<only horizons with train WR >= 80 and ExpR > 0 and N >= 10>)}`.
  3. If still failing, leave it ungated, record it as FAILING in the results doc. Do NOT lower R:R below 0.30, do NOT retune on validation.

  Write the chosen `STRATEGY_GATES` into `strategy_types.py` with a comment citing the train numbers.

- [ ] **Step 5: Confirm on train** — `python scripts/run_backtest_range.py --train` — every strategy should now show PASS (or be documented as FAILING). Save the table into the tuning results doc. Run `python -m pytest tests -v` (gates can change entry counts but no test asserts counts; all must still pass).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/entry_filters.py swingbot/core/strategy_types.py docs/superpowers/results/2026-07-train-tuning.md
git commit -m "feat: train-window tuned params + strategy gates"
```

---

### Task 20: Validation run + final report

**Files:**
- Create: `docs/superpowers/results/2026-07-validation.md`
- Modify: `swingbot/core/backtest.py` (module docstring: describe the new engine honestly)

- [ ] **Step 1: Run validation ONCE**

Run: `python scripts/run_backtest_range.py --validation --json validation_results.json`

- [ ] **Step 2: Write `docs/superpowers/results/2026-07-validation.md`** containing: the full PASS/FAIL table (verbatim), the train table for comparison, the tuned parameters and gates, and an honest verdict per strategy — `PASS`, `PASS-GATED` (passed only long-only / restricted horizons), or `FAIL` (with its actual numbers). Do not rerun tuning after seeing these numbers; if something fails, the report says so.

- [ ] **Step 3: Update the `backtest.py` module docstring** — replace the "Important limitations" list's stale parts and document: four-outcome taxonomy, break-even rule, R:R floor rationale, and that entries come from `entry_filters.py` shared with live signals. Keep the survivorship-bias and no-fees caveats.

- [ ] **Step 4: Full suite + final commit**

Run: `python -m pytest tests -v`
Expected: PASS.

```bash
git add docs/superpowers/results/2026-07-validation.md swingbot/core/backtest.py
git commit -m "docs: out-of-sample validation results for strategy redesign"
```

---

## Self-Review Notes (already applied)

- Spec §3.1→Tasks 5–14, §3.2→Tasks 2+4, §3.3→Tasks 16–18, §4→Task 3, §5→Task 5, §6→Task 2, §7→Task 3, §8.1–8.11→Tasks 6–12, §9→Tasks 18–19, acceptance §2→Tasks 17+20. `!backtest` UX (§10 in-scope sliver) → Task 15.
- Type consistency: `entries_for(strategy, df, horizon_key, params=None)` used identically in Tasks 5, 13, 14, 18; `BacktestSummary.scratches` introduced in Task 3, consumed in Tasks 15 and 17; `DEFAULT_PARAMS` keys match `PARAM_GRID` keys per strategy (note: Elliott's grid sweeps `depth_min`/`depth_max` as separate keys, matching its `DEFAULT_PARAMS`).
- Known soft spot: the positive-fire tests rely on `market_df` (seeded random walk) producing at least some entries; the invariant tests are written so they pass vacuously if a strategy never fires on it (`.all()` over an empty index is True). That is intentional — real fire-rate evidence comes from the cached-data harness in Task 17, not synthetic tests.
