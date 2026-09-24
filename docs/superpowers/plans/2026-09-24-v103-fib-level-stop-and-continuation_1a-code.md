# v103 Part 1a — Code (worktree branch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-24-v103-fib-level-stop-and-continuation_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md`
## Parallelisation

- **Group 1 (parallel):** V103-1, V103-2 here, with V103-6 and V103-7 in `_1b-code.md` (disjoint files, no shared symbols).
- **Sequential:**
  - V103-3 after V103-1 + V103-2.
  - V103-4 after V103-1 (same file).
  - V103-5 after V103-3 + V103-4.
  - V103-6..8 continue in `2026-09-24-v103-fib-level-stop-and-continuation_1b-code.md`.

---

# Phase A — Code

### Task V103-1: Mechanism A entry side — level-stop helper and flags

Load the `no-lookahead` skill first.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (imports; new helpers just above `def fibonacci_entries`; one line inside `fibonacci_entries`)
- Modify: `swingbot/config.py` (two `Field`s directly after the `FIB_SR_CONFLUENCE_ATR` Field)
- Modify: `.env.example` (after `FIB_SR_CONFLUENCE_ATR=0.0`)
- Test: `tests/market/test_fib_level_stop.py` (create)

**Interfaces:**
- Produces:
  - `entry_filters._fib_level_stop_config() -> tuple[float, frozenset[str]]`
  - `entry_filters.fib_level_stop_series(df, horizon_key, direction, b, params=None) -> pd.Series`: float stop per bar, NaN where ineligible.
  - `entry_filters.fib_level_stop_at(df, index, horizon_key, direction, params=None) -> float | None`: None means A is off for that direction. A float may be NaN.
  - `config.FIB_LEVEL_STOP_ATR: float` (default 0.0) and `config.FIB_LEVEL_STOP_DIRECTIONS: str` (default "").

- [ ] **Step 1: Write the failing tests**

```python
"""v103 A: Fibonacci level-stop -- stop just past the tested level; drop, never cap."""
import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import capped_planned_loss_pct
from tests.market.test_fib_sr_confluence import (
    _bear_signal_frame, _bull_signal_frame, _reference_no_confluence,
)


def _set(monkeypatch, b, directions):
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_ATR", b, raising=False)
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_DIRECTIONS", directions, raising=False)


def _independent_stop(df, horizon, direction, b):
    """Row-by-row re-derivation sharing no code with the helper."""
    lb = HORIZONS[horizon]["fib_lookback"]
    ratios = ef.DEFAULT_PARAMS["Fibonacci"]["ratios"]
    a = atr(df, 14)
    cap = capped_planned_loss_pct(HORIZONS[horizon]["max_risk_pct"])
    out = []
    for i in range(len(df)):
        if i < lb - 1 or np.isnan(a.iloc[i]):
            out.append(np.nan)
            continue
        hi = df["High"].iloc[i - lb + 1:i + 1].max()
        lo = df["Low"].iloc[i - lb + 1:i + 1].min()
        close = df["Close"].iloc[i]
        tested = min((hi - r * (hi - lo) for r in ratios), key=lambda lv: abs(lv - close))
        stop = tested - b * a.iloc[i] if direction == "bullish" else tested + b * a.iloc[i]
        losing = stop < close if direction == "bullish" else stop > close
        fits = abs(close - stop) / close * 100 <= cap + 1e-9
        out.append(stop if (losing and fits) else np.nan)
    return pd.Series(out, index=df.index)


def test_flag_off_is_bit_identical_to_an_independent_reference(monkeypatch):
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    ref_bull, _ = _reference_no_confluence(df_bull, "4w")
    _, ref_bear = _reference_no_confluence(df_bear, "4w")
    assert ref_bull.any() and ref_bear.any(), "reference frames must fire"
    for b, directions in ((0.0, ""), (0.25, ""), (0.0, "bullish,bearish")):
        _set(monkeypatch, b, directions)
        bull, _ = ef.fibonacci_entries(df_bull, "4w")
        _, bear = ef.fibonacci_entries(df_bear, "4w")
        pd.testing.assert_series_equal(bull, ref_bull)
        pd.testing.assert_series_equal(bear, ref_bear)


def test_helper_matches_an_independent_rederivation():
    for df in (_bull_signal_frame(), _bear_signal_frame()):
        for direction in ("bullish", "bearish"):
            for b in (0.1, 0.5):
                got = ef.fib_level_stop_series(df, "4w", direction, b)
                pd.testing.assert_series_equal(got, _independent_stop(df, "4w", direction, b),
                                               check_names=False)
    assert ef.fib_level_stop_series(_bull_signal_frame(), "4w", "bullish", 0.1).notna().any()


def test_entries_drop_exactly_the_ineligible_bars(monkeypatch):
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    _set(monkeypatch, 0.0, "")
    bull0, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear0 = ef.fibonacci_entries(df_bear, "4w")
    _set(monkeypatch, 0.1, "bullish,bearish")
    bull1, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear1 = ef.fibonacci_entries(df_bear, "4w")
    keep_bull = ef.fib_level_stop_series(df_bull, "4w", "bullish", 0.1).notna()
    keep_bear = ef.fib_level_stop_series(df_bear, "4w", "bearish", 0.1).notna()
    pd.testing.assert_series_equal(bull1, bull0 & keep_bull, check_names=False)
    pd.testing.assert_series_equal(bear1, bear0 & keep_bear, check_names=False)


def test_direction_scope_leaves_the_other_direction_alone(monkeypatch):
    df_bull = _bull_signal_frame()
    ref_bull, _ = _reference_no_confluence(df_bull, "4w")
    _set(monkeypatch, 0.1, "bearish")
    bull, _ = ef.fibonacci_entries(df_bull, "4w")
    pd.testing.assert_series_equal(bull, ref_bull)


def test_drop_never_cap():
    stops = ef.fib_level_stop_series(_bull_signal_frame(), "4w", "bullish", 50.0)
    assert stops.isna().all(), "a stop past the 2% cap must be dropped, not dragged to the cap"


def test_no_lookahead_truncation():
    df = _bull_signal_frame()
    full = ef.fib_level_stop_series(df, "4w", "bullish", 0.25)
    for k in range(60, len(df), 17):
        trunc = ef.fib_level_stop_series(df.iloc[:k + 1], "4w", "bullish", 0.25).iloc[-1]
        assert (np.isnan(trunc) and np.isnan(full.iloc[k])) or trunc == full.iloc[k]


def test_at_bar_reads_the_same_series(monkeypatch):
    df = _bull_signal_frame()
    _set(monkeypatch, 0.0, "bullish")
    assert ef.fib_level_stop_at(df, 250, "4w", "bullish") is None
    _set(monkeypatch, 0.1, "bullish")
    assert ef.fib_level_stop_at(df, 250, "4w", "bearish") is None
    series = ef.fib_level_stop_series(df, "4w", "bullish", 0.1)
    for k in (120, 250, len(df) - 1):
        got = ef.fib_level_stop_at(df, k, "4w", "bullish")
        assert (np.isnan(got) and np.isnan(series.iloc[k])) or got == series.iloc[k]


def test_at_bar_accepts_negative_index(monkeypatch):
    df = _bull_signal_frame()
    _set(monkeypatch, 0.1, "bullish")
    last = ef.fib_level_stop_at(df, len(df) - 1, "4w", "bullish")
    neg = ef.fib_level_stop_at(df, -1, "4w", "bullish")
    assert (np.isnan(last) and np.isnan(neg)) or last == neg


def test_directions_parsing_is_forgiving(monkeypatch):
    _set(monkeypatch, 0.25, " Bullish , bearish ,sideways")
    assert ef._fib_level_stop_config() == (0.25, frozenset({"bullish", "bearish"}))


def test_nan_bars_give_nan_not_raise():
    df = _bull_signal_frame().copy()
    df.iloc[200:206, :4] = np.nan
    stops = ef.fib_level_stop_series(df, "4w", "bullish", 0.25)
    assert stops.iloc[200:206].isna().all()
```

- [ ] **Step 2: Run and confirm failure**

Run: `python scripts/dev/testrun.py file tests/market/test_fib_level_stop.py`
Expected: FAIL. Eight tests fail with `AttributeError: ... has no attribute 'fib_level_stop_series'` / `'_fib_level_stop_config'` / `'fib_level_stop_at'`. `test_flag_off_is_bit_identical...` and `test_direction_scope...` pass already, because the flag does not exist yet and so has no effect. That is expected: they guard the flag-off path. They are not the RED tests.

- [ ] **Step 3: Implement**

In `swingbot/core/market/entry_filters.py`, add to the imports (after the `strategy_types` import block):

```python
from swingbot.core.risk_limits import capped_planned_loss_pct
```

Just above `def fibonacci_entries`, add:

```python
_LEVEL_STOP_DIRECTIONS = ("bullish", "bearish")


def _fib_level_stop_config():
    """(b, directions) for v103 mechanism A, read at call time so a SIGHUP
    reload applies. Parsing forgives case and spaces; unknown names are
    ignored, never matched. b <= 0 or no direction -> A is off."""
    from swingbot import config
    b = float(getattr(config, "FIB_LEVEL_STOP_ATR", 0.0) or 0.0)
    raw = str(getattr(config, "FIB_LEVEL_STOP_DIRECTIONS", "") or "")
    scope = frozenset(v.strip().lower() for v in raw.split(","))
    return b, scope & frozenset(_LEVEL_STOP_DIRECTIONS)


def fib_level_stop_series(df, horizon_key, direction, b, params=None):
    """v103 A: per-bar stop b x ATR14 past the TESTED Fibonacci level -- the
    ratio level nearest the close over fibonacci_entries' own trailing
    swing. NaN where the stop is not on the losing side of the close or its
    planned loss exceeds the 2% hard cap: that signal is DROPPED, never
    capped (v101 #2 capped, and the cap dragged every stop back to an
    arbitrary 2%). Reads bars <= i only."""
    p = _params("Fibonacci", params)
    h = HORIZONS[horizon_key]
    lookback = h["fib_lookback"]
    swing_high = df["High"].rolling(lookback).max()
    swing_low = df["Low"].rolling(lookback).min()
    rng = swing_high - swing_low
    levels = np.column_stack([(swing_high - r * rng).to_numpy(dtype=float) for r in p["ratios"]])
    close = df["Close"].to_numpy(dtype=float)
    dist = np.abs(levels - close[:, None])
    dist = np.where(np.isnan(dist), np.inf, dist)
    tested = levels[np.arange(len(close)), dist.argmin(axis=1)]
    atr14 = atr(df, 14).to_numpy(dtype=float)
    is_bull = direction == "bullish"
    stop = tested - b * atr14 if is_bull else tested + b * atr14
    with np.errstate(invalid="ignore", divide="ignore"):
        losing_side = stop < close if is_bull else stop > close
        loss_pct = np.abs(close - stop) / close * 100
        ok = losing_side & (loss_pct <= capped_planned_loss_pct(h["max_risk_pct"]) + 1e-9)
    return pd.Series(np.where(ok, stop, np.nan), index=df.index)


def fib_level_stop_at(df, index, horizon_key, direction, params=None):
    """Builder-side read of fib_level_stop_series at one bar. None = A off for
    this direction (the builder keeps the legacy swing stop); a float,
    possibly NaN, = A on (NaN -> no plan). Sliced to `index`, so the backtest
    (full-history df) and the live builder see identical input."""
    b, scope = _fib_level_stop_config()
    if b <= 0 or direction not in scope:
        return None
    if index < 0:
        index += len(df)
    sliced = df.iloc[:index + 1]
    return float(fib_level_stop_series(sliced, horizon_key, direction, b, params=params).iloc[-1])


def _apply_fib_level_stop(df, horizon_key, p, bullish, bearish):
    """Drop each in-scope direction's signals whose level-stop is NaN."""
    b, scope = _fib_level_stop_config()
    if b <= 0:
        return bullish, bearish
    if "bullish" in scope:
        bullish = bullish & fib_level_stop_series(df, horizon_key, "bullish", b, params=p).notna()
    if "bearish" in scope:
        bearish = bearish & fib_level_stop_series(df, horizon_key, "bearish", b, params=p).notna()
    return bullish, bearish
```

In `fibonacci_entries`, replace the final three lines:

```python
    confluence = _fib_sr_confluence(df, h, levels, close, g["atr14"])
    bullish, bearish = bullish & confluence, bearish & confluence
    return bullish, bearish
```

with:

```python
    confluence = _fib_sr_confluence(df, h, levels, close, g["atr14"])
    bullish, bearish = bullish & confluence, bearish & confluence
    bullish, bearish = _apply_fib_level_stop(df, horizon_key, p, bullish, bearish)
    return bullish, bearish
```

In `swingbot/config.py`, directly after the `FIB_SR_CONFLUENCE_ATR` `Field(...)`:

```python
    Field("FIB_LEVEL_STOP_ATR", "FIB_LEVEL_STOP_ATR", "Trade Filters & Risk",
          "Fibonacci: stop past the tested level (x ATR)",
          type="float", default="0.0", min=0.0, max=1.0, step=0.05,
          help="v103 mechanism A. Puts a Fibonacci plan's stop this many ATRs past the "
               "retracement level being tested, and DROPS the signal when that stop would "
               "exceed the 2% planned-loss cap (never caps it). 0 disables. Applies only to "
               "the directions in FIB_LEVEL_STOP_DIRECTIONS. Ships OFF: a pre-registered "
               "measurement, not a demonstrated edge."),
    Field("FIB_LEVEL_STOP_DIRECTIONS", "FIB_LEVEL_STOP_DIRECTIONS", "Trade Filters & Risk",
          "Fibonacci level-stop directions",
          type="text", default="",
          help="v103. Comma-separated: bullish, bearish, or both. Empty disables "
               "FIB_LEVEL_STOP_ATR entirely, so it can ship for only the direction(s) whose "
               "VALIDATION shot passed."),
```

In `.env.example`, after the `FIB_SR_CONFLUENCE_ATR=0.0` line:

```
# v103 mechanism A: Fibonacci stop this many ATRs past the tested retracement
# level; a signal whose stop would exceed the 2% cap is dropped, never capped.
# 0 disables. Only the directions listed below. Ships OFF: a pre-registered
# measurement, not a demonstrated edge.
FIB_LEVEL_STOP_ATR=0.0
# Comma-separated: bullish, bearish. Empty = mechanism A off.
FIB_LEVEL_STOP_DIRECTIONS=
```

- [ ] **Step 4: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fib_level_stop.py` → 10 passed.
Run: `python scripts/dev/testrun.py file tests/market/test_fib_sr_confluence.py` → 6 passed.
Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py` → pass.
Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py` → pass.
Run: `python scripts/dev/testrun.py file tests/test_config_flags.py` → pass.
Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`. Only the pre-existing `elliott_wave_entries C (15)` may appear. No new function may be listed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/config.py .env.example tests/market/test_fib_level_stop.py
git commit -m "feat(v103): Fibonacci level-stop helper and flags -- drop, never cap (default off)"
```

---

### Task V103-2: Table-drive `build_strategy_plan`'s strategy dispatch (refactor, no behaviour change)

`build_strategy_plan` is CC 26. C's branch would make it 27, which CLAUDE.md forbids. This task moves each branch into its own function behind a lookup table, following code-complexity.md's "table-drive `if/elif` chains". Behaviour is unchanged, and the existing tests are the guard.

**Files:**
- Modify: `swingbot/core/planning/builders.py` (imports; four branch functions + `_STRUCTURAL_BRANCHES` above `build_strategy_plan`; the body of `build_strategy_plan` from `from swingbot.core.market.indicators import atr as atr_indicator` through the end of the `else:` branch)
- Test: `tests/planning/test_strategy_branch_table.py` (create)

**Interfaces:**
- Produces: `builders._BranchInputs` (frozen dataclass with fields `df, index, strategy, horizon_key, direction, close, atr_val, stop_mult, scan_params`); `builders._STRUCTURAL_BRANCHES: dict[str, callable]`; and the branch callables `_fib_branch`, `_sr_branch`, `_elliott_branch`, `_atr_branch`. Each branch takes `_BranchInputs` and returns `(stop, tp1, candidates, applied_stop_mult) | None`.

- [ ] **Step 1: Record the baseline**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_engine_sizing.py`, then the same for `tests/edge/test_edge_stops.py`, `tests/planning/test_opex_stop_size.py` and `tests/market/test_levels_lifecycle_wiring.py`. All should pass. Write the pass counts down, because Step 4 must reproduce them exactly.
Run: `python -m radon cc -s swingbot/core/planning/builders.py | grep build_strategy_plan` → `D (26)`.

- [ ] **Step 2: Write the failing test**

```python
"""v103: build_strategy_plan's per-strategy dispatch is a table, not an elif chain."""
from swingbot.core.planning import builders


def test_structural_strategies_have_their_own_branch():
    assert set(builders._STRUCTURAL_BRANCHES) == {"Fibonacci", "Support/Resistance", "Elliott Wave"}


def test_every_other_strategy_falls_back_to_the_atr_branch():
    assert builders._STRUCTURAL_BRANCHES.get("MACD", builders._atr_branch) is builders._atr_branch
```

Run: `python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py`
Expected: FAIL, `AttributeError: module ... has no attribute '_STRUCTURAL_BRANCHES'`.

- [ ] **Step 3: Implement**

Add `from dataclasses import dataclass` to the stdlib imports at the top of `builders.py`.

Directly above `def build_strategy_plan`, add:

```python
@dataclass(frozen=True)
class _BranchInputs:
    df: object
    index: int
    strategy: str
    horizon_key: str
    direction: str
    close: float
    atr_val: float
    stop_mult: float | None
    scan_params: object


def _fib_branch(x):
    """Fibonacci: structural stop off the fib swing, risk-capped."""
    h = HORIZONS[x.horizon_key]
    lookback = h["fib_lookback"]
    swing_high = float(x.df["High"].rolling(lookback).max().iloc[x.index])
    swing_low = float(x.df["Low"].rolling(lookback).min().iloc[x.index])
    if not (np.isfinite(swing_high) and np.isfinite(swing_low)):
        return None
    candidates = fib_target_candidates(x.df, x.index, h, x.close)
    result = _fibonacci_plan(x.close, x.atr_val, swing_high, swing_low, x.direction,
                             x.horizon_key, candidate_levels=candidates, params=x.scan_params)
    return None if result is None else (result[0], result[1], candidates, None)


def _sr_branch(x):
    h = HORIZONS[x.horizon_key]
    vol_avg20 = x.df["Volume"].rolling(20).mean()
    ratio = float((x.df["Volume"] / vol_avg20).iloc[x.index])
    candidates = sr_target_candidates(x.df, x.index, h, x.close, ratio)
    result = _sr_plan(x.close, ratio, x.direction, x.horizon_key, candidate_levels=candidates,
                      params=x.scan_params)
    return None if result is None else (result[0], result[1], candidates, None)


def _elliott_branch(x):
    from swingbot.core.market.indicators import elliott_wave3_entries
    h = HORIZONS[x.horizon_key]
    _, _, entry_levels = elliott_wave3_entries(x.df, h["max_risk_pct"])
    if not entry_levels or x.index not in entry_levels:
        return None
    candidates = elliott_target_candidates(entry_levels[x.index], x.direction)
    result = _elliott_plan(x.close, x.atr_val, entry_levels[x.index]["wave2"], x.direction,
                           x.horizon_key, candidate_levels=candidates, params=x.scan_params)
    return None if result is None else (result[0], result[1], candidates, None)


def _atr_branch(x):
    """Only the genuine ATR-multiple path takes the MAE adjustment (edge E31).
    The structural branches put their stop behind real structure -- a fib
    swing, an Elliott wave-2 low, an S/R shelf -- and scaling those would
    slide the stop off the very structure it exists to hide behind. That's a
    different, unvalidated idea from "give the ATR stop the room this
    strategy's winners actually used", so they stay structure-derived on
    purpose. Opex composes ON TOP of whatever multiplier was already resolved
    -- an explicit caller override or E31's per-strategy MAE figure -- so
    neither silently replaces the other. Off an opex day stop_mult() is
    exactly 1.0 and the guarded line is a no-op: `None` is the contract for
    "no multiplier applied" and is asserted on by tests/edge/test_edge_stops.py,
    so an unconditional `or 1.0` would rewrite every ordinary plan's
    stop_mult_applied to 1.0."""
    applied_stop_mult = (x.stop_mult if x.stop_mult is not None
                         else plan_params._resolve_stop_mult(x.strategy))
    _opex_stop_mult = opex.stop_mult()
    if _opex_stop_mult != 1.0:
        applied_stop_mult = (applied_stop_mult or 1.0) * _opex_stop_mult
    candidates = atr_target_candidates(x.close, x.atr_val, x.direction)
    result = _atr_plan(x.close, x.atr_val, x.direction, x.horizon_key, x.strategy,
                       stop_mult=applied_stop_mult, candidate_levels=candidates,
                       params=x.scan_params)
    return None if result is None else (result[0], result[1], candidates, applied_stop_mult)


# Strategies whose stop sits behind their own structure. Everything else is
# sized by _atr_branch. Adding a structural strategy = one entry here.
_STRUCTURAL_BRANCHES = {
    "Fibonacci": _fib_branch,
    "Support/Resistance": _sr_branch,
    "Elliott Wave": _elliott_branch,
}
```

In `build_strategy_plan`, replace everything from `from swingbot.core.market.indicators import atr as atr_indicator` down to and including the `else:` branch's final `stop, tp1 = result` (the line just before the `# P1: the same adjuster backtest._trade_plan_at calls` comment) with:

```python
    from swingbot.core.market.indicators import atr as atr_indicator

    close = float(df["Close"].iloc[index])
    atr_series = atr_indicator(df, 14)
    atr_val = _safe_atr_value(close, float(atr_series.iloc[index]))
    branch = _STRUCTURAL_BRANCHES.get(strategy, _atr_branch)
    picked = branch(_BranchInputs(df, index, strategy, horizon_key, direction, close,
                                  atr_val, stop_mult, scan_params))
    if picked is None:
        return None
    stop, tp1, candidates, applied_stop_mult = picked
```

Everything from the `# P1:` comment onward stays exactly as it is.

- [ ] **Step 4: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py` → 2 passed.
Re-run the four files from Step 1. Expected: the same pass counts as Step 1, 0 failed.
Run: `python scripts/dev/testrun.py fast`. The refactor crosses files, so the fast tier is justified here. Expected: `0 failed`.
Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py`. `build_strategy_plan` must be **below 26** (expected ~C 11-14). No new function may appear at C or worse.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/builders.py tests/planning/test_strategy_branch_table.py
git commit -m "refactor(v103): table-drive build_strategy_plan's strategy dispatch (no behaviour change)"
```

---

### Task V103-3: Mechanism A builder side — `_fibonacci_plan` takes the level-stop

**Files:**
- Modify: `swingbot/core/planning/builders.py` (`risk_limits` import; `_fibonacci_plan` signature and body; `_fib_branch`)
- Modify: `swingbot/core/backtesting/backtest.py` (`_trade_plan_at`, Fibonacci branch)
- Test: `tests/planning/test_fib_level_stop_builder.py` (create)

**Interfaces:**
- Consumes: `entry_filters.fib_level_stop_at` (V103-1); `builders._fib_branch` (V103-2).
- Produces: `_fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key, candidate_levels=None, params=None, level_stop=None)`. With `level_stop=None`, behaviour is unchanged. A finite value is used verbatim, or the function returns None if the value is NaN, sits on the wrong side, or exceeds the cap.

- [ ] **Step 1: Write the failing tests**

```python
"""v103 A builder side: the level-stop is used verbatim, or no plan is built."""
import math

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import _plan_series, _trade_plan_at
from swingbot.core.market import entry_filters as ef
from swingbot.core.planning.builders import _fibonacci_plan, build_strategy_plan
from tests.market.test_fib_sr_confluence import _bull_signal_frame


def test_level_stop_is_used_verbatim():
    stop, tp1 = _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w",
                                candidate_levels=[105.0], level_stop=99.0)
    assert stop == 99.0 and tp1 == pytest.approx(102.5)      # 105 is past 2.5R -> synthetic 2.5R


def test_level_stop_over_the_cap_builds_nothing():
    assert _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w",
                           candidate_levels=[105.0], level_stop=97.9) is None   # 2.1% -- never capped to 98


def test_level_stop_on_the_wrong_side_or_nan_builds_nothing():
    kw = dict(candidate_levels=[105.0, 95.0])
    assert _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w", level_stop=100.5, **kw) is None
    assert _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w", level_stop=math.nan, **kw) is None
    assert _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bearish", "4w", level_stop=99.5, **kw) is None


def test_no_level_stop_keeps_the_swing_stop():
    legacy = _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w", candidate_levels=[105.0])
    same = _fibonacci_plan(100.0, 1.0, 110.0, 90.0, "bullish", "4w", candidate_levels=[105.0],
                           level_stop=None)
    assert legacy == same and legacy[0] == pytest.approx(98.0)      # swing stop, capped at 2%


def test_backtest_and_live_build_the_same_level_stop_plan(monkeypatch):
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_ATR", 0.1, raising=False)
    monkeypatch.setattr(config, "FIB_LEVEL_STOP_DIRECTIONS", "bullish", raising=False)
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df = _bull_signal_frame()
    helper = ef.fib_level_stop_series(df, "4w", "bullish", 0.1)
    atr_s, sh, sl, vr, el = _plan_series(df, "Fibonacci", "4w")
    checked = 0
    for k in [i for i in range(len(df)) if not math.isnan(helper.iloc[i])]:
        bt = _trade_plan_at(df, k, "bullish", "Fibonacci", "4w", atr_s, sh, sl, vr, el)
        if bt is None:
            continue
        _, bt_stop, bt_tp = bt
        assert bt_stop == helper.iloc[k]
        plan = build_strategy_plan(df.iloc[:k + 1], k, ticker="TST", strategy="Fibonacci",
                                   horizon_key="4w", direction="bullish")
        assert plan is not None and plan.stop_loss == bt_stop and plan.tp1 == pytest.approx(bt_tp)
        checked += 1
        if checked == 5:
            break
    assert checked > 0, "the frame must yield at least one eligible level-stop plan"
```

Run: `python scripts/dev/testrun.py file tests/planning/test_fib_level_stop_builder.py`
Expected: FAIL, `TypeError: _fibonacci_plan() got an unexpected keyword argument 'level_stop'`.

- [ ] **Step 2: Implement**

In `builders.py`, change the `risk_limits` import to:

```python
from swingbot.core.risk_limits import capped_planned_loss_pct, planned_loss_pct
```

Replace `_fibonacci_plan` whole with:

```python
def _level_stop_or_none(entry, level_stop, is_bull, h):
    """v103 A: the level-stop verbatim, or None (no plan) when it is NaN, on
    the wrong side of entry, or over the 2% cap. Never capped."""
    if not np.isfinite(level_stop):
        return None
    if (level_stop >= entry) if is_bull else (level_stop <= entry):
        return None
    if planned_loss_pct(entry, level_stop) > capped_planned_loss_pct(h["max_risk_pct"]) + 1e-9:
        return None
    return float(level_stop)


def _fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key,
                    candidate_levels=None, params=None, level_stop=None):
    """Structural sizing off the fib swing, risk-capped -- or, when v103 A
    passes `level_stop`, that stop verbatim (None if it doesn't fit). Target
    is the nearest real Fibonacci level (fib_target_candidates) that pays at
    least MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31) -- see
    select_structural_target. Returns None when no candidate clears the
    floor: no fallback to a fixed fraction of risk."""
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    if level_stop is not None:
        stop_loss = _level_stop_or_none(entry, level_stop, is_bull, h)
        if stop_loss is None:
            return None
    else:
        buffer = STRUCTURE_BUFFER_ATR * atr_val
        stop_loss = swing_low - buffer if is_bull else swing_high + buffer
        max_risk_amount = entry * (capped_planned_loss_pct(h["max_risk_pct"]) / 100)
        if abs(entry - stop_loss) > max_risk_amount:
            stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    if take_profit is None:
        return None
    return stop_loss, take_profit
```

In `_fib_branch`, replace the `result = _fibonacci_plan(...)` statement with:

```python
    from swingbot.core.market.entry_filters import fib_level_stop_at
    result = _fibonacci_plan(x.close, x.atr_val, swing_high, swing_low, x.direction,
                             x.horizon_key, candidate_levels=candidates, params=x.scan_params,
                             level_stop=fib_level_stop_at(x.df, x.index, x.horizon_key,
                                                          x.direction))
```

In `backtest.py` `_trade_plan_at`, replace the Fibonacci branch's `result = _fibonacci_plan(...)` statement with:

```python
        from swingbot.core.market.entry_filters import fib_level_stop_at
        result = _fibonacci_plan(
            entry, atr_val, float(swing_high_series.iloc[i]),
            float(swing_low_series.iloc[i]), direction, horizon_key,
            candidate_levels=candidates,
            level_stop=fib_level_stop_at(df, i, horizon_key, direction))
```

- [ ] **Step 3: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/planning/test_fib_level_stop_builder.py` → 5 passed. If the parity test reports `checked == 0`, the frame yields no eligible plan. That is a test-data problem: report it rather than weaken the assertion.
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_engine_sizing.py` → pass (flag off, golden swing stop unchanged).
Run: `python scripts/dev/testrun.py file tests/edge/test_edge_stops.py` → pass (`_fibonacci_plan` still takes no `stop_mult`).
Run: `python scripts/dev/testrun.py file tests/backtesting/test_sizing_parity.py` → pass or skip (the flag is off).
Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py`. No new C or worse, and `_trade_plan_at` stays below 15.

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py tests/planning/test_fib_level_stop_builder.py
git commit -m "feat(v103): _fibonacci_plan uses the level-stop verbatim or builds nothing (default off)"
```

---

### Task V103-4: Mechanism C entry side — Fibonacci Continuation signal

Load the `no-lookahead` and `edge-module` skills first.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (new block after `ENTRY_FUNCS["Fibonacci"] = fibonacci_entries`)
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES`, one entry)
- Test: `tests/market/test_fib_continuation.py` (create)

**Interfaces:**
- Produces:
  - `DEFAULT_PARAMS["Fibonacci Continuation"] = {"d_min": 0.382, "d_max": 0.618, "min_pullback_bars": 2}`.
  - `FIB_CONTINUATION_STOP_ATR = 0.25`.
  - `fib_continuation_frame(df, horizon_key, direction, params=None) -> pd.DataFrame`, with columns `level, impulse, retrace, depth, stop, signal`.
  - `fib_continuation_at(df, index, horizon_key, direction, params=None) -> dict | None`, with keys `level, impulse, retrace, stop`.
  - `fib_continuation_entries(df, horizon_key, params=None) -> (bullish, bearish)`.
  - `ENTRY_FUNCS["Fibonacci Continuation"]`.
  - `STRATEGY_GATES["Fibonacci Continuation"] = {"directions": ()}`.

- [ ] **Step 1: Write the failing tests**

```python
"""v103 C: Fibonacci Continuation -- a held retracement's break of the swing extreme."""
import numpy as np
import pandas as pd

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR
from tests.helpers import make_ohlcv
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "2w"


def _breakout_bars(retrace_low=105.0, pullback_bars=3, breakout_close=110.5):
    """Flat pad; impulse A=100.0 -> H=110.0; pullback to `retrace_low`; one breakout bar."""
    lb = HORIZONS[HZ]["fib_lookback"]
    assert lb >= 5 + pullback_bars + 1, "window must reach back to the swing low"
    pad = [(100.8, 101.0, 100.6, 100.8)] * (lb + 30)
    impulse = [(100.2, 100.8, 100.0, 100.6)]
    for c in (103.0, 106.0, 108.5):
        impulse.append((c - 1.0, c + 0.5, c - 1.2, c))
    impulse.append((109.0, 110.0, 108.8, 109.6))
    pull = []
    for k in range(1, pullback_bars + 1):
        low = 110.0 - (110.0 - retrace_low) * k / pullback_bars
        pull.append((low + 0.8, low + 1.0, low, low + 0.5))
    breakout = [(109.8, breakout_close + 0.2, 109.5, breakout_close)]
    after = [(breakout_close, breakout_close + 0.3, breakout_close - 0.3, breakout_close)] * 3
    bars = pad + impulse + pull + breakout + after
    return bars, len(pad) + len(impulse) + len(pull)


def _frame(**kw):
    bars, i = _breakout_bars(**kw)
    return make_ohlcv(bars, start="2015-01-02"), i


def _mirror(bars):
    return [(210 - o, 210 - lo, 210 - hi, 210 - c) for o, hi, lo, c in bars]


def test_breakout_fires_exactly_once():
    df, i = _frame()
    sig = ef.fib_continuation_frame(df, HZ, "bullish")["signal"]
    assert bool(sig.iloc[i]) and int(sig.sum()) == 1


def test_structure_values_at_the_breakout():
    df, i = _frame()
    row = ef.fib_continuation_frame(df, HZ, "bullish").iloc[i]
    assert row["level"] == 110.0 and row["impulse"] == 10.0 and row["retrace"] == 105.0
    assert row["depth"] == 0.5
    assert row["stop"] == 110.0 - ef.FIB_CONTINUATION_STOP_ATR * float(atr(df, 14).iloc[i])


def test_too_deep_does_not_fire_unless_d_max_allows():
    df, i = _frame(retrace_low=103.0)                    # depth 0.7
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()
    wide = ef.fib_continuation_frame(df, HZ, "bullish", params={"d_max": 0.786})
    assert bool(wide["signal"].iloc[i])


def test_too_shallow_does_not_fire():
    df, _ = _frame(retrace_low=107.0)                    # depth 0.3
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_one_bar_pullback_does_not_fire():
    df, _ = _frame(pullback_bars=1)
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_extended_breakout_bar_is_dropped_not_capped():
    df, _ = _frame(breakout_close=113.0)                 # stop under 110 is > 2% below 113
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].any()


def test_bearish_mirror_fires_once():
    bars, i = _breakout_bars()
    df = make_ohlcv(_mirror(bars), start="2015-01-02")
    frame = ef.fib_continuation_frame(df, HZ, "bearish")
    assert bool(frame["signal"].iloc[i]) and int(frame["signal"].sum()) == 1
    assert frame["level"].iloc[i] == 100.0 and frame["retrace"].iloc[i] == 105.0


def test_flat_frame_never_fires():
    df = make_ohlcv([100.0] * 120, start="2015-01-02", spread=0.0)     # impulse 0 everywhere
    for direction in ("bullish", "bearish"):
        frame = ef.fib_continuation_frame(df, HZ, direction)
        assert not frame["signal"].any() and frame["depth"].isna().all()


def test_nan_bars_do_not_fire():
    df, i = _frame()
    df = df.copy()
    df.iloc[i - 2, :4] = np.nan
    assert not ef.fib_continuation_frame(df, HZ, "bullish")["signal"].iloc[i]


def test_no_lookahead_truncation():
    df = _trending_frame(400, 0.06, seed=2)
    full = ef.fib_continuation_frame(df, "4w", "bullish")
    for k in range(60, len(df), 13):
        trunc = ef.fib_continuation_frame(df.iloc[:k + 1], "4w", "bullish").iloc[-1]
        pd.testing.assert_series_equal(trunc, full.iloc[k], check_names=False)


def test_at_bar_returns_structure_only_on_a_signal():
    df, i = _frame()
    got = ef.fib_continuation_at(df, i, HZ, "bullish")
    assert got["level"] == 110.0 and set(got) == {"level", "impulse", "retrace", "stop"}
    assert ef.fib_continuation_at(df, i + 1, HZ, "bullish") is None


def test_continuation_at_accepts_negative_index():
    df, i = _frame()
    df = df.iloc[:i + 1]
    assert ef.fib_continuation_at(df, -1, HZ, "bullish") == ef.fib_continuation_at(df, i, HZ, "bullish")


def test_entries_compose_the_shared_gates():
    df = _trending_frame(400, 0.06, seed=2)
    g = ef.compute_shared_gates(df)
    bull, bear = ef.fib_continuation_entries(df, "4w")
    raw_bull = ef.fib_continuation_frame(df, "4w", "bullish")["signal"]
    want = (raw_bull & g["bull_regime"] & g["trend50_bull"] & g["atr_floor"]
            & g["atr_calm"] & g["vol_ok"]).fillna(False).astype(bool)
    pd.testing.assert_series_equal(bull, want, check_names=False)
    assert bear.dtype == bool


def test_ships_masked_in_entries_for():
    df, _ = _frame()
    regimes = pd.Series("unknown", index=df.index)
    bull, bear = ef.entries_for("Fibonacci Continuation", df, HZ, regimes=regimes)
    assert not bull.any() and not bear.any()


def test_registered_once_and_buffer_matches_planning():
    assert ef.ENTRY_FUNCS["Fibonacci Continuation"] is ef.fib_continuation_entries
    assert ef.FIB_CONTINUATION_STOP_ATR == STRUCTURE_BUFFER_ATR
```

Run: `python scripts/dev/testrun.py file tests/market/test_fib_continuation.py`
Expected: FAIL, `AttributeError: ... has no attribute 'fib_continuation_frame'` (and a `KeyError` for the `ENTRY_FUNCS` test).

- [ ] **Step 2: Implement**

In `entry_filters.py`, directly after `ENTRY_FUNCS["Fibonacci"] = fibonacci_entries`:

```python
# --- v103 C: Fibonacci Continuation ----------------------------------------

DEFAULT_PARAMS["Fibonacci Continuation"] = {
    # Pre-registered (v103). d_max is the TRAIN grid axis {0.5, 0.618, 0.786};
    # 0.618 is its centre, not a tuned value.
    "d_min": 0.382, "d_max": 0.618, "min_pullback_bars": 2,
}
# = planning.params.STRUCTURE_BUFFER_ATR; a copy so market/ never imports
# planning/. tests/market/test_fib_continuation.py pins the two equal.
FIB_CONTINUATION_STOP_ATR = 0.25


def _extreme_after(values, lookback, pos, fn):
    """For each trailing `lookback` window of `values`, fn's extreme
    (np.minimum / np.maximum) over the window's bars strictly AFTER window
    position `pos`. NaN when pos is the window's last bar or unknown."""
    v = np.asarray(values, dtype=float)
    out = np.full(len(v), np.nan)
    if len(v) < lookback:
        return out
    w = np.lib.stride_tricks.sliding_window_view(v, lookback)
    suffix = fn.accumulate(w[:, ::-1], axis=1)[:, ::-1]      # suffix[r, j] = extreme of w[r, j:]
    p = np.asarray(pos, dtype=float)[lookback - 1:]
    rows = np.nonzero(np.isfinite(p) & (p < lookback - 1))[0]
    out[lookback - 1 + rows] = suffix[rows, p[rows].astype(int) + 1]
    return out


def _continuation_sides(prior_high, prior_low, lookback, direction):
    """(level, anchor, level_pos, anchor_pos, retrace, fn_sign) for one
    direction: bullish breaks the swing HIGH after a held pullback low,
    bearish breaks the swing LOW after a held bounce high."""
    hi_pos = _rolling_argmax_pos(prior_high, lookback).to_numpy()
    lo_pos = _rolling_argmin_pos(prior_low, lookback).to_numpy()
    swing_high = prior_high.rolling(lookback).max().to_numpy(dtype=float)
    swing_low = prior_low.rolling(lookback).min().to_numpy(dtype=float)
    if direction == "bullish":
        retrace = _extreme_after(prior_low.to_numpy(), lookback, hi_pos, np.minimum)
        return swing_high, swing_low, hi_pos, lo_pos, retrace, 1.0
    retrace = _extreme_after(prior_high.to_numpy(), lookback, lo_pos, np.maximum)
    return swing_low, swing_high, lo_pos, hi_pos, retrace, -1.0


def fib_continuation_frame(df, horizon_key, direction, params=None):
    """v103 C structure per bar. Structure comes from bars STRICTLY BEFORE i
    (High/Low shifted one bar); only the trigger reads bar i's close.
    `signal` = impulse (anchor before level) & >= min_pullback_bars after the
    level & d_min <= depth <= d_max & close crosses the level & the stop
    (level -/+ FIB_CONTINUATION_STOP_ATR x ATR14) fits the 2% cap -- a stop
    that doesn't fit DROPS the signal. Crossing is a first cross by
    construction: the level is the prior window's extreme, so no earlier
    close in it crossed. Shared gates are NOT applied here."""
    p = _params("Fibonacci Continuation", params)
    h = HORIZONS[horizon_key]
    lookback = h["fib_lookback"]
    level, anchor, pos, other, retrace, sign = _continuation_sides(
        df["High"].shift(1), df["Low"].shift(1), lookback, direction)
    close = df["Close"].to_numpy(dtype=float)
    atr14 = atr(df, 14).to_numpy(dtype=float)
    stop = level - sign * FIB_CONTINUATION_STOP_ATR * atr14
    with np.errstate(invalid="ignore", divide="ignore"):
        impulse = np.abs(level - anchor)
        depth = np.where(impulse > 0, np.abs(level - retrace) / np.where(impulse > 0, impulse, 1.0), np.nan)
        structure = (other < pos) & ((lookback - 1 - pos) >= p["min_pullback_bars"])
        held = (depth >= p["d_min"]) & (depth <= p["d_max"])
        crossed = sign * (close - level) > 0
        fits = np.abs(close - stop) / close * 100 <= capped_planned_loss_pct(h["max_risk_pct"]) + 1e-9
        signal = structure & held & crossed & fits & (impulse > 0)
    return pd.DataFrame({"level": level, "impulse": impulse, "retrace": retrace, "depth": depth,
                         "stop": stop, "signal": signal.astype(bool)}, index=df.index)


def fib_continuation_at(df, index, horizon_key, direction, params=None):
    """One bar of fib_continuation_frame, sliced to `index` (backtest and live
    see identical input). None unless that bar is a signal."""
    if index < 0:
        index += len(df)
    row = fib_continuation_frame(df.iloc[:index + 1], horizon_key, direction, params).iloc[-1]
    if not bool(row["signal"]):
        return None
    return {k: float(row[k]) for k in ("level", "impulse", "retrace", "stop")}


def fib_continuation_entries(df, horizon_key, params=None):
    """v103 C: a completed measured move. After an impulse and a HELD
    retracement (d_min..d_max of the impulse), the first close back through
    the swing extreme -- momentum, not the retracement bounce Fibonacci
    trades. Shared gates as every strategy."""
    g = compute_shared_gates(df)
    common = g["atr_floor"] & g["atr_calm"] & g["vol_ok"]
    bull = fib_continuation_frame(df, horizon_key, "bullish", params)["signal"]
    bear = fib_continuation_frame(df, horizon_key, "bearish", params)["signal"]
    bullish = (bull & g["bull_regime"] & g["trend50_bull"] & common).fillna(False).astype(bool)
    bearish = (bear & g["bear_regime"] & g["trend50_bear"] & common).fillna(False).astype(bool)
    return bullish, bearish


ENTRY_FUNCS["Fibonacci Continuation"] = fib_continuation_entries
```

In `strategy_types.py` `STRATEGY_GATES`, directly after the `"Fibonacci"` entry:

```python
    # v103 C: ships MASKED -- both directions off until one passes its
    # pre-registered VALIDATION shot. Measurement unmasks via gate_override.
    # (The v93 strategy pass loops ENTRY_FUNCS, so without this it would build
    # shadow plans for an unmeasured strategy the moment it merged.)
    "Fibonacci Continuation": {"directions": ()},
```

- [ ] **Step 3: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/market/test_fib_continuation.py` → 15 passed.
Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py` → pass (`set(gates) <= {"directions","horizons"}` still holds).
Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass.py` → pass. If the file doesn't exist, run `git grep -ln "strategy_pass" -- tests` and run those files instead. The masked strategy must produce no signals.
Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`. Only the pre-existing `elliott_wave_entries C (15)` may appear.

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py tests/market/test_fib_continuation.py
git commit -m "feat(v103): Fibonacci Continuation entry signal -- held retracement, first close through the extreme (masked)"
```

---

### Task V103-5: Mechanism C builder side — targets, sizing, both plan paths

**Files:**
- Modify: `swingbot/core/planning/targets.py` (new `fib_continuation_targets`)
- Modify: `swingbot/core/planning/builders.py` (`targets` import; `risk_limits` import; `_fib_continuation_plan`; `_fib_continuation_branch`; the `_STRUCTURAL_BRANCHES` entry)
- Modify: `swingbot/core/planning/params.py` (`EXIT_V2_PARAMS` entry)
- Modify: `swingbot/core/backtesting/backtest.py` (`_trade_plan_at`, one `elif`)
- Modify: `tests/planning/test_strategy_branch_table.py` (the key set gains C)
- Test: `tests/planning/test_fib_continuation_builder.py` (create)

**Interfaces:**
- Consumes: `entry_filters.fib_continuation_at` (V103-4); `builders._STRUCTURAL_BRANCHES`, `_BranchInputs` (V103-2).
- Produces:
  - `targets.fib_continuation_targets(level, impulse, retrace, direction) -> list[float]`.
  - `builders._fib_continuation_plan(entry, structure, direction, horizon_key, candidate_levels, params=None) -> (stop, tp1) | None`.
  - `EXIT_V2_PARAMS["Fibonacci Continuation"] = {"trail_atr_mult": 2.5, "tp2": True}`.

- [ ] **Step 1: Write the failing tests**

```python
"""v103 C builder side: own targets, drop-don't-cap sizing, backtest == live."""
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import _plan_series, _trade_plan_at
from swingbot.core.planning import builders
from swingbot.core.planning.builders import _fib_continuation_plan, build_strategy_plan
from swingbot.core.planning.params import exit_params_for
from swingbot.core.planning.targets import fib_continuation_targets, select_structural_target
from tests.market.test_fib_continuation import HZ, _frame

C = "Fibonacci Continuation"


def test_targets_use_correct_extension_arithmetic():
    assert fib_continuation_targets(110.0, 10.0, 105.0, "bullish") == pytest.approx([115.0, 112.72, 116.18])
    assert fib_continuation_targets(100.0, 10.0, 105.0, "bearish") == pytest.approx([95.0, 97.28, 93.82])


def test_nearest_target_inside_the_band_is_chosen():
    structure = {"level": 99.5, "impulse": 10.0, "retrace": 95.0, "stop": 99.0}
    stop, tp1 = _fib_continuation_plan(100.0, structure, "bullish", HZ, [102.0, 103.0, 104.0])
    assert stop == 99.0 and tp1 == 102.0


def test_stop_over_the_cap_builds_nothing():
    structure = {"level": 98.5, "impulse": 10.0, "retrace": 95.0, "stop": 97.5}
    assert _fib_continuation_plan(100.0, structure, "bullish", HZ, [105.0]) is None


def test_exit_params_are_the_pre_registered_defaults():
    p = exit_params_for(C)
    assert p["trail_atr_mult"] == 2.5 and p["tp2"] is True


def test_branch_table_routes_continuation():
    assert builders._STRUCTURAL_BRANCHES[C] is builders._fib_continuation_branch


def test_backtest_and_live_build_the_same_plan(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df, i = _frame()
    atr_s, sh, sl, vr, el = _plan_series(df, C, HZ)
    entry, stop, tp = _trade_plan_at(df, i, "bullish", C, HZ, atr_s, sh, sl, vr, el)
    assert entry == 110.5 and stop < 110.0
    want = select_structural_target(entry, stop, True,
                                    fib_continuation_targets(110.0, 10.0, 105.0, "bullish"), 1.5, 2.5)
    assert tp == pytest.approx(want)
    plan = build_strategy_plan(df.iloc[:i + 1], i, ticker="TST", strategy=C,
                               horizon_key=HZ, direction="bullish")
    assert plan.stop_loss == stop and plan.tp1 == pytest.approx(tp)


def test_no_signal_bar_builds_nothing_on_either_path(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    df, i = _frame()
    atr_s, sh, sl, vr, el = _plan_series(df, C, HZ)
    assert _trade_plan_at(df, i + 1, "bullish", C, HZ, atr_s, sh, sl, vr, el) is None
    assert build_strategy_plan(df, i + 1, ticker="TST", strategy=C, horizon_key=HZ,
                               direction="bullish") is None
```

In `tests/planning/test_strategy_branch_table.py`, change the expected set in `test_structural_strategies_have_their_own_branch` to:

```python
    assert set(builders._STRUCTURAL_BRANCHES) == {"Fibonacci", "Support/Resistance", "Elliott Wave",
                                                  "Fibonacci Continuation"}
```

Run: `python scripts/dev/testrun.py file tests/planning/test_fib_continuation_builder.py`
Expected: FAIL, `ImportError: cannot import name '_fib_continuation_plan'`.

- [ ] **Step 2: Implement**

In `targets.py`, after `fib_target_candidates`:

```python
def fib_continuation_targets(level, impulse, retrace, direction) -> list[float]:
    """v103 C's OWN targets, with conventional extension arithmetic: the
    measured move (impulse length added to the pullback extreme) and the
    1.272 / 1.618 extensions of the impulse beyond the broken level.
    (fib_target_candidates' "1.272" is swing_high + 1.272 x range, a 2.272
    extension -- recorded in the v103 spec, deliberately not fixed there.)"""
    if direction == "bullish":
        return [retrace + impulse, level + 0.272 * impulse, level + 0.618 * impulse]
    return [retrace - impulse, level - 0.272 * impulse, level - 0.618 * impulse]
```

In `builders.py`, add `fib_continuation_targets` to the `from .targets import (...)` list. Then, directly after `_level_stop_or_none`:

```python
def _fib_continuation_plan(entry, structure, direction, horizon_key, candidate_levels,
                           params=None):
    """v103 C sizing: the structure's own stop (broken level -/+ 0.25 ATR),
    re-checked against the 2% cap -- drop, never cap -- and the nearest
    target in the 1.5-2.5R band. None -> no plan."""
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
    is_bull = direction == "bullish"
    stop_loss = _level_stop_or_none(entry, structure["stop"], is_bull, HORIZONS[horizon_key])
    if stop_loss is None:
        return None
    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels,
        params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    if take_profit is None:
        return None
    return stop_loss, take_profit
```

Directly after `_elliott_branch`:

```python
def _fib_continuation_branch(x):
    from swingbot.core.market.entry_filters import fib_continuation_at
    structure = fib_continuation_at(x.df, x.index, x.horizon_key, x.direction)
    if structure is None:
        return None
    candidates = fib_continuation_targets(structure["level"], structure["impulse"],
                                          structure["retrace"], x.direction)
    result = _fib_continuation_plan(x.close, structure, x.direction, x.horizon_key,
                                    candidates, params=x.scan_params)
    return None if result is None else (result[0], result[1], candidates, None)
```

Add to `_STRUCTURAL_BRANCHES`:

```python
    "Fibonacci Continuation": _fib_continuation_branch,
```

In `params.py` `EXIT_V2_PARAMS`, after the `"Volume Profile"` row:

```python
    # v103 C: an explicit copy of the missing-key defaults, fixed BEFORE any
    # scoring (a breakout keeps its runner). Not derived from validation data.
    "Fibonacci Continuation": {"trail_atr_mult": 2.5, "tp2": True},
```

In `backtest.py` `_trade_plan_at`, add this branch immediately before the final `else:`:

```python
    elif strategy == "Fibonacci Continuation":
        from swingbot.core.market.entry_filters import fib_continuation_at
        from swingbot.core.planning.builders import _fib_continuation_plan
        from swingbot.core.planning.targets import fib_continuation_targets
        structure = fib_continuation_at(df, i, horizon_key, direction)
        candidates = ([] if structure is None else fib_continuation_targets(
            structure["level"], structure["impulse"], structure["retrace"], direction))
        result = (None if structure is None else _fib_continuation_plan(
            entry, structure, direction, horizon_key, candidates))
```

- [ ] **Step 3: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/planning/test_fib_continuation_builder.py` → 7 passed.
Run: `python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py` → 2 passed.
Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py` → pass (C is not in `ALL_STRATEGIES`).
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_engine_sizing.py` → pass.
Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py swingbot/core/planning/targets.py`. No new C or worse, and `_trade_plan_at` stays below 15.

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/planning/targets.py swingbot/core/planning/builders.py swingbot/core/planning/params.py swingbot/core/backtesting/backtest.py tests/planning/test_fib_continuation_builder.py tests/planning/test_strategy_branch_table.py
git commit -m "feat(v103): Fibonacci Continuation sizing -- own extension targets, drop-don't-cap, backtest == live"
```

