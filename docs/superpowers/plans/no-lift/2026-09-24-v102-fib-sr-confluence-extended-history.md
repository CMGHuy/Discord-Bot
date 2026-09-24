# Fibonacci × Rolling S/R Confluence on Extended History — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-24-v102-fib-sr-confluence-extended-history-design.md`
**Bump:** none until Task V102-9; `bot minor` there only if a direction passes VALIDATION and the flag ships
**Edge:** expectancy

**Goal:** Test whether keeping only Fibonacci signals whose tested retracement level sits within `tol × ATR14` of a Rolling S/R level lifts Fibonacci to the badge bar (WR ≥ 50, ExpR > 0), per direction, on a 2010–2023 training window, with one VALIDATION shot per direction on 2024–25.

**Architecture:**
- A `BACKTEST_CACHE_DIR` override lets a separate extended cache (`data/backtest_cache_ext/`, 2010→2025) serve v102, leaving the shared cache byte-identical.
- A config flag `FIB_SR_CONFLUENCE_ATR` (0 = off) adds the filter inside `fibonacci_entries`, which the backtest and the live scan share.
- A new script, `scripts/backtest/measure_fib_confluence.py`, runs the four funnel stages: `count`, `collect`, `evaluate` and `validation`. It saves raw trade rows once per tolerance, so Stage 1 and Stage 2 are pure re-evaluations of one collection run.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest, yfinance (the fetch only).

## Global Constraints

- **Windows (verbatim from the spec):** `TRAIN_EXT = 2010-01-01..2023-12-31`; walk-forward test years `2013..2023`, anchored, train from 2010-01-01; `VALIDATION = 2024-01-01..2025-12-31`, **one shot per direction, ever**.
- **Grid:** `FIB_SR_CONFLUENCE_ATR ∈ {0.25, 0.5, 0.75, 1.0}`; `0.0` is the reference baseline, never a candidate.
- **Badge clauses:** WR ≥ 50, ExpR > 0, decided N ≥ 30 on TRAIN_EXT (N ≥ 15 on VALIDATION), scratch+timeout share ≤ 50%. Stage 1 plateau: the chosen cell's grid neighbours must also clear. Winner = highest ExpR among plateau-passing cells.
- **Stage 2 fold rule:** of the folds with test N ≥ 15, at least 2/3 have ExpR > 0, and at least 3 folds must have N ≥ 15. Per fold, the tolerance is re-selected on that fold's train span (2010..Y−1) as the highest-ExpR grid cell with decided N ≥ 30. A fold with no such cell is *unselected* and does not qualify.
- **Populations:** bullish from the live gate; bearish unmasked via `entry_filters.gate_override` plus the v93 laggard rule (`measure_bearish_arms.apply_laggard_rule`). v2 exits, scale-out, TP2 levels, frictions on.
- **The shared cache `data/backtest_cache/` is never written.** Every v102 measurement runs with `BACKTEST_CACHE_DIR=data/backtest_cache_ext`, and the script refuses to run otherwise.
- **Survivorship bias is declared, not corrected.** The universe is today's watchlist.
- **No regime condition, no horizon mask, no stop, target or exit change.** Closed rows (v101 #1/#2/#4, v31, v84, v93, v17 `REGIME_ALLOW`) are not re-run.
- **NO-LOOKAHEAD:** the filter at bar i reads only bars ≤ i (the Rolling S/R uses `.shift(1)`). Load the `no-lookahead` skill before Task V102-2.
- **Complexity:** every function written or changed has radon CC < 15 (`python -m radon cc -s -n C <file>`).
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`. The full suite runs once, in Task V102-10.
- **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- No `cd` in Bash commands. Code tasks (V102-1..3) run on a worktree branch; data, run and doc tasks (V102-4..10) run on `main` after the merge.

## Parallelisation

- **Group 1 (parallel):** V102-1 (`backtest_cache.py`) and V102-2 (`entry_filters.py`, `config.py`, `.env.example`) touch disjoint files.
- **Sequential:** V102-3 after Group 1 (it imports both). V102-4 fetch → V102-5 Stage 0 → V102-6 pre-registration → V102-7 Stages 1–2 → V102-8 VALIDATION → V102-9 wiring or close-out → V102-10 verification. Each reads the previous task's output, and V102-6 must be committed before V102-7 measures anything.
- **Cross-plan:** v100 (arm producer) is live and unimplemented. v102 does not use `validate_component.py`, because its Stage 2 rule is its own. If v100 has merged by V102-6, note in the pre-registration that v102's funnel is self-contained and why.

---

# Phase A — Code

### Task V102-1: `BACKTEST_CACHE_DIR` override

**Files:**
- Modify: `swingbot/core/marketdata/backtest_cache.py:28` (the `CACHE_DIR` line)
- Test: `tests/marketdata/test_backtest_cache_dir.py` (create)

**Interfaces:**
- Produces: `backtest_cache._cache_dir() -> Path`; module constant `CACHE_DIR` now equals `_cache_dir()` at import. Every `cache_path()` / `load_cached()` caller follows it.

- [ ] **Step 1: Write the failing tests**

```python
"""v102: BACKTEST_CACHE_DIR redirects the backtest cache; unset keeps the default."""
from pathlib import Path

from swingbot import config
from swingbot.core.marketdata import backtest_cache as bc


def test_default_is_data_backtest_cache(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    assert bc._cache_dir() == Path(config.DATA_DIR) / "backtest_cache"


def test_relative_override_resolves_against_project_root(monkeypatch):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "data/backtest_cache_ext")
    assert bc._cache_dir() == Path(config.DATA_DIR).parent / "data" / "backtest_cache_ext"


def test_absolute_override_is_used_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(tmp_path / "ext"))
    assert bc._cache_dir() == tmp_path / "ext"


def test_empty_override_means_default(monkeypatch):
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "")
    assert bc._cache_dir() == Path(config.DATA_DIR) / "backtest_cache"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_backtest_cache_dir.py`
Expected: FAIL, `AttributeError: module ... has no attribute '_cache_dir'`.

- [ ] **Step 3: Implement**

Add `import os` to the imports and replace line 28 (`CACHE_DIR = Path(config.DATA_DIR) / "backtest_cache"`) with:

```python
def _cache_dir() -> Path:
    """data/backtest_cache/ unless BACKTEST_CACHE_DIR points elsewhere -- the
    v102 extended-history cache (data/backtest_cache_ext/) is the one user.
    A relative override resolves against the project root, not the cwd, so
    every script agrees on it. Read once at import: set it on the command
    line (`BACKTEST_CACHE_DIR=... python ...`), never mid-process."""
    override = os.environ.get("BACKTEST_CACHE_DIR")
    if not override:
        return Path(config.DATA_DIR) / "backtest_cache"
    path = Path(override)
    return path if path.is_absolute() else Path(config.DATA_DIR).parent / path


CACHE_DIR = _cache_dir()
```

- [ ] **Step 4: Run and confirm pass, plus the existing cache tests**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_backtest_cache_dir.py` → 4 passed.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_backtest_cache.py` → all pass (its fixture monkeypatches `CACHE_DIR` and is unaffected).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/backtest_cache.py tests/marketdata/test_backtest_cache_dir.py
git commit -m "feat(v102): BACKTEST_CACHE_DIR override for a separate extended-history cache"
```

---

### Task V102-2: `FIB_SR_CONFLUENCE_ATR` flag and the entry filter

Load the `no-lookahead` skill first.

**Files:**
- Modify: `swingbot/config.py` (add a `Field` right after the `FIB_TARGET_1_0_EXTENSION` Field, around line 208)
- Modify: `.env.example` (after the `FIB_TARGET_1_0_EXTENSION=false` block, around line 233)
- Modify: `swingbot/core/market/entry_filters.py` (`fibonacci_entries`, around line 190, plus a new helper just above it)
- Test: `tests/market/test_fib_sr_confluence.py` (create)

**Interfaces:**
- Produces: `config.FIB_SR_CONFLUENCE_ATR: float` (default `0.0`); `entry_filters._fib_sr_confluence(df, h, levels, close, atr14) -> pd.Series[bool]`. `fibonacci_entries` ANDs it into both directions.

- [ ] **Step 1: Write the failing tests**

```python
"""v102: Fibonacci x Rolling S/R confluence filter."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


def _frame(n=300):
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    return make_ohlcv(list(closes), start="2015-01-02")


def _inputs(df, horizon="4w"):
    h = HORIZONS[horizon]
    lb = h["fib_lookback"]
    swing_high, swing_low = df["High"].rolling(lb).max(), df["Low"].rolling(lb).min()
    rng = swing_high - swing_low
    levels = pd.DataFrame({r: swing_high - r * rng for r in (0.382, 0.5, 0.618)})
    atr14 = ef.compute_shared_gates(df)["atr14"]
    return h, levels, df["Close"], atr14


def test_flag_zero_keeps_every_bar(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    df = _frame()
    out = ef._fib_sr_confluence(df, *_inputs(df))
    assert out.all()


def test_flag_zero_leaves_fibonacci_entries_bit_identical(monkeypatch):
    df = _frame()
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, bear0 = ef.fibonacci_entries(df, "4w")
    monkeypatch.delattr(config, "FIB_SR_CONFLUENCE_ATR", raising=False)
    bull1, bear1 = ef.fibonacci_entries(df, "4w")      # attribute absent -> treated as 0
    pd.testing.assert_series_equal(bull0, bull1)
    pd.testing.assert_series_equal(bear0, bear1)


def test_keeps_within_tolerance_and_drops_just_outside(monkeypatch):
    df = _frame()
    h, levels, close, atr14 = _inputs(df)
    i = 250
    lb = h["sr_lookback"]
    support = float(df["Low"].rolling(lb).min().shift(1).iloc[i])
    resistance = float(df["High"].rolling(lb).max().shift(1).iloc[i])
    arr = levels.iloc[i].to_numpy()
    tested = arr[np.argmin(np.abs(arr - close.iloc[i]))]
    gap = min(abs(tested - support), abs(tested - resistance))
    assert gap > 0, "pick another bar: a zero gap makes the 'just outside' tolerance non-positive"
    tol_hit = gap / float(atr14.iloc[i]) + 1e-9
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", tol_hit, raising=False)
    assert bool(ef._fib_sr_confluence(df, h, levels, close, atr14).iloc[i]) is True
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", tol_hit * 0.999 - 1e-9, raising=False)
    assert bool(ef._fib_sr_confluence(df, h, levels, close, atr14).iloc[i]) is False


def test_filter_only_removes_signals(monkeypatch):
    df = _frame(600)
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, bear0 = ef.fibonacci_entries(df, "4w")
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.5, raising=False)
    bull1, bear1 = ef.fibonacci_entries(df, "4w")
    assert not (bull1 & ~bull0).any() and not (bear1 & ~bear0).any()


def test_no_lookahead(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.75, raising=False)
    df = _frame()
    i = 250
    base = ef._fib_sr_confluence(df, *_inputs(df))
    poisoned = df.copy()
    poisoned.iloc[i + 1:, :4] = poisoned.iloc[i + 1:, :4] * 5
    again = ef._fib_sr_confluence(poisoned, *_inputs(poisoned))
    pd.testing.assert_series_equal(base.iloc[:i + 1], again.iloc[:i + 1])


def test_nan_warmup_bars_are_dropped_not_raised(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 1.0, raising=False)
    df = _frame(60)                       # shorter than fib_lookback + sr_lookback warm-up
    out = ef._fib_sr_confluence(df, *_inputs(df))
    assert out.dtype == bool and not out.iloc[:30].any()
```

- [ ] **Step 2: Run and confirm failure**

Run: `python scripts/dev/testrun.py file tests/market/test_fib_sr_confluence.py`
Expected: FAIL, `AttributeError: module ... has no attribute '_fib_sr_confluence'`.

- [ ] **Step 3: Implement the helper and wire it**

In `swingbot/core/market/entry_filters.py`, just above `def fibonacci_entries`:

```python
def _fib_sr_confluence(df, h, levels, close, atr14):
    """v102: True where the tested Fibonacci retracement level (the ratio
    level nearest the close -- the one is_testing found) sits within
    FIB_SR_CONFLUENCE_ATR x ATR14 of the bar's Rolling support or resistance.
    Rolling S/R is levels.py's own definition (rolling sr_lookback extreme,
    shift(1)), the one level family v49 measured as nearly independent of
    Fibonacci. Never compared against the swing extremes: a shorter-window
    rolling low often IS the Fibonacci swing low, which would be trivially
    true. Flag 0 (or absent) -> all True, so entries are bit-identical to
    pre-v102. Reads bars <= i only."""
    from swingbot import config
    tol = float(getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0) or 0.0)
    if tol <= 0:
        return pd.Series(True, index=df.index)
    arr = levels.to_numpy(dtype=float)
    dist = np.abs(arr - close.to_numpy(dtype=float)[:, None])
    dist = np.where(np.isnan(dist), np.inf, dist)
    tested = arr[np.arange(len(arr)), dist.argmin(axis=1)]
    lookback = h["sr_lookback"]
    support = df["Low"].rolling(lookback).min().shift(1).to_numpy(dtype=float)
    resistance = df["High"].rolling(lookback).max().shift(1).to_numpy(dtype=float)
    gap = np.fmin(np.abs(tested - support), np.abs(tested - resistance))
    with np.errstate(invalid="ignore"):
        keep = gap <= tol * atr14.to_numpy(dtype=float)
    return pd.Series(keep, index=df.index)
```

In `fibonacci_entries`, after the `bullish = (...)` and `bearish = (...)` assignments and before `return bullish, bearish`, add:

```python
    confluence = _fib_sr_confluence(df, h, levels, close, g["atr14"])
    bullish, bearish = bullish & confluence, bearish & confluence
```

`h`, `levels`, `close` and `g` are already local names in `fibonacci_entries`. Check this, and use the existing names if any differ.

In `swingbot/config.py`, directly after the `FIB_TARGET_1_0_EXTENSION` `Field(...)`:

```python
    Field("FIB_SR_CONFLUENCE_ATR", "FIB_SR_CONFLUENCE_ATR", "Trade Filters & Risk",
          "Fibonacci: Rolling S/R confluence tolerance (x ATR)",
          type="float", default="0.0", min=0.0, max=2.0, step=0.25,
          help="Keeps a Fibonacci entry only when the tested retracement level sits "
               "within this many ATRs of the bar's rolling support or resistance -- "
               "the one level family nearly independent of Fibonacci (v49). 0 disables "
               "the filter. Ships OFF: a pre-registered measurement (v102), not a "
               "demonstrated edge; it changes only if its VALIDATION shot passes."),
```

In `.env.example`, after the `FIB_TARGET_1_0_EXTENSION=false` line:

```
# Keeps a Fibonacci entry only when the tested retracement level sits within
# this many ATRs of the bar's rolling support/resistance (v102). 0 disables
# the filter. Ships OFF: a pre-registered measurement, not a demonstrated
# edge -- changes only if its VALIDATION shot passes.
FIB_SR_CONFLUENCE_ATR=0.0
```

- [ ] **Step 4: Run tests**

Run: `python scripts/dev/testrun.py file tests/market/test_fib_sr_confluence.py` → 6 passed.
Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py` → pass.
Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py` → pass (flag off, unchanged).
Run: `python scripts/dev/testrun.py file tests/test_config_flags.py` → pass.
Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`. `fibonacci_entries` must not rise to 15 or more. If it does, lift the two new lines' logic into the helper (already done) and report the score.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/config.py .env.example tests/market/test_fib_sr_confluence.py
git commit -m "feat(v102): FIB_SR_CONFLUENCE_ATR flag -- Fibonacci x Rolling S/R entry filter, default off"
```

---

### Task V102-3: `measure_fib_confluence.py` — the four funnel stages

**Files:**
- Create: `scripts/backtest/measure_fib_confluence.py`
- Test: `tests/scripts/test_measure_fib_confluence.py` (create)

**Interfaces:**
- Consumes: `config.FIB_SR_CONFLUENCE_ATR` (V102-2); `backtest_cache.CACHE_DIR` (V102-1); `run_backtest_range` (sibling) `_build_asof_map`, `_tickers_for_run`, `_with_context`, `load_cached`, `window_trades`, `merge_registry`; `measure_bearish_arms` (sibling) `_unmasked_gates`, `apply_laggard_rule`; `swingbot.core.backtesting.backtest.run_backtest`; `swingbot.core.backtesting.arm_rule.pooled_stats(trades) -> {n, wins, losses, win_rate, expectancy_r, scratch_timeout_share}`; `entry_filters.entries_for`, `gate_override`; `universe.liquidity_reason`, `data_quality_issues`.
- Produces (module `measure_fib_confluence`): constants `TRAIN_EXT`, `VALIDATION`, `GRID`, `BASELINE_TOL`, `FOLD_YEARS`, `TRAIN_START_YEAR`, `WR_FLOOR`, `MIN_N_TRAIN`, `MIN_N_VALIDATION`, `MAX_SCRATCH_SHARE`, `FOLD_MIN_N`, `FOLD_POSITIVE_SHARE`, `MIN_QUALIFYING_FOLDS`, `EXT_CACHE_NAME`; functions `tol_key(tol) -> str`, `require_ext_cache()`, `confluence_tol(tol)` (context manager), `collect_trades(frames, asof_map, tol, window, *, horizons, run_fn, progress) -> list[dict]`, `count_signals(frames, tols, *, horizons) -> dict`, `pooled(rows) -> dict`, `badge_verdict(stats, min_n) -> dict`, `stage1(rows_by_tol, direction) -> dict`, `fold_pick(rows_by_tol, direction, year) -> float | None`, `stage2(rows_by_tol, direction) -> dict`, `fold_verdict(folds) -> dict`, `registry_record(rows, run_date) -> dict`, `main(argv=None) -> int`. A row is `{"ticker", "horizon_key", "direction", "entry_date", "outcome", "r_multiple"}`.

- [ ] **Step 1: Write the failing tests**

```python
"""v102: Fibonacci x Rolling S/R confluence funnel (pure logic + collection shape)."""
import sys
from pathlib import Path
from types import SimpleNamespace as T

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _m():
    import measure_fib_confluence as m
    return m


def _rows(direction, n_win, n_loss, year="2015", win_r=2.0, horizon="3m"):
    rows = [{"ticker": "AAA", "horizon_key": horizon, "direction": direction,
             "entry_date": f"{year}-06-01", "outcome": "win", "r_multiple": win_r} for _ in range(n_win)]
    rows += [{"ticker": "AAA", "horizon_key": horizon, "direction": direction,
              "entry_date": f"{year}-06-01", "outcome": "loss", "r_multiple": -1.0} for _ in range(n_loss)]
    return rows


def test_tol_key_is_stable():
    m = _m()
    assert [m.tol_key(t) for t in (0.0, 0.25, 0.5, 1.0)] == ["0", "0.25", "0.5", "1"]


def test_badge_verdict_needs_every_clause():
    m = _m()
    ok = m.pooled(_rows("bullish", 20, 10))
    assert m.badge_verdict(ok, 30)["clears"] is True
    assert m.badge_verdict(ok, 31)["clears"] is False                 # N
    low = m.pooled(_rows("bullish", 14, 16))
    assert m.badge_verdict(low, 30)["clauses"]["wr"] is False          # WR 46.7
    neg = m.pooled(_rows("bullish", 16, 14, win_r=0.5))
    assert m.badge_verdict(neg, 30)["clauses"]["exp_r"] is False       # ExpR < 0


def _by_tol(passing_tols, direction="bullish"):
    m = _m()
    out = {m.tol_key(m.BASELINE_TOL): _rows(direction, 10, 25)}
    for tol in m.GRID:
        wins = 25 if tol in passing_tols else 10
        out[m.tol_key(tol)] = _rows(direction, wins, 15, win_r=2.0 + tol)
    return out


def test_stage1_requires_plateau_and_picks_highest_expr():
    m = _m()
    out = m.stage1(_by_tol({0.5, 0.75, 1.0}), "bullish")
    # 0.5's neighbour 0.25 fails -> not plateau; 0.75 and 1.0 plateau; 1.0 has higher ExpR
    assert out["plateau_passing"] == [0.75, 1.0] and out["winner"] == 1.0


def test_stage1_isolated_spike_has_no_winner():
    m = _m()
    assert m.stage1(_by_tol({0.5}), "bullish")["winner"] is None


def test_fold_pick_uses_only_the_train_span():
    m = _m()
    rows = {m.tol_key(t): [] for t in (m.BASELINE_TOL, *m.GRID)}
    rows[m.tol_key(0.25)] = _rows("bullish", 20, 15, year="2011") + _rows("bullish", 0, 40, year="2016")
    rows[m.tol_key(0.5)] = _rows("bullish", 5, 30, year="2011") + _rows("bullish", 40, 0, year="2016")
    assert m.fold_pick(rows, "bullish", 2013) == 0.25       # 2016 rows are invisible to the 2013 fold
    assert m.fold_pick(rows, "bullish", 2011) is None       # train span 2010 only: no cell has N >= 30
    assert m.fold_pick(rows, "bullish", 2017) == 0.5        # 2011 + 2016 both visible: 0.5 now leads


def test_fold_verdict_two_thirds_and_minimum_three():
    m = _m()
    good = {"n": 20, "expectancy_r": 0.2}
    bad = {"n": 20, "expectancy_r": -0.1}
    thin = {"n": 5, "expectancy_r": 1.0}
    folds = [{"tol": 0.5, "stats": s} for s in (good, good, bad, thin)]
    assert m.fold_verdict(folds)["clears"] is True           # 2 of 3 qualifying positive
    folds = [{"tol": 0.5, "stats": s} for s in (good, bad, bad)]
    assert m.fold_verdict(folds)["clears"] is False
    folds = [{"tol": 0.5, "stats": good}, {"tol": 0.5, "stats": good}, {"tol": None, "stats": None}]
    v = m.fold_verdict(folds)
    assert v["clears"] is False and v["unselected"] == 1     # only 2 qualifying


def test_confluence_tol_restores_the_flag():
    m = _m()
    from swingbot import config
    before = getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0)
    with m.confluence_tol(0.75):
        assert config.FIB_SR_CONFLUENCE_ATR == 0.75
    assert config.FIB_SR_CONFLUENCE_ATR == before


def test_require_ext_cache_refuses_the_shared_cache(monkeypatch, tmp_path):
    m = _m()
    from swingbot.core.marketdata import backtest_cache as bc
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    with pytest.raises(SystemExit):
        m.require_ext_cache()
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / m.EXT_CACHE_NAME)
    m.require_ext_cache()


def test_collect_trades_populations_and_window(monkeypatch):
    m = _m()
    frame = make_ohlcv([100.0] * 300, start="2012-01-02")
    seen = []

    def run_fn(ticker, df, strategy, horizon, **kw):
        from swingbot import config
        seen.append((dict(m.STRATEGY_GATES.get(strategy) or {}).get("directions"),
                     config.FIB_SR_CONFLUENCE_ATR))
        return T(trades=[
            T(direction="bullish", entry_date="2012-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bullish", entry_date="2024-06-01", outcome="win", r_multiple=2.0, context={}),
            T(direction="bearish", entry_date="2012-06-01", outcome="loss", r_multiple=-1.0,
              context={"rs_combined": 10.0}),
            T(direction="bearish", entry_date="2012-06-01", outcome="win", r_multiple=2.0,
              context={"rs_combined": 80.0}),
        ])

    progress = T(tick=lambda label: None)
    rows = m.collect_trades({"AAA": frame}, {}, 0.5, m.TRAIN_EXT, horizons=("3m",),
                            run_fn=run_fn, progress=progress)
    assert [(r["direction"], r["entry_date"]) for r in rows] == [("bullish", "2012-06-01"),
                                                                ("bearish", "2012-06-01")]
    assert seen[0] == (("bullish",), 0.5) and seen[1] == (("bullish", "bearish"), 0.5)
    assert set(rows[0]) == {"ticker", "horizon_key", "direction", "entry_date", "outcome", "r_multiple"}


def test_count_signals_by_year(monkeypatch):
    m = _m()
    frame = make_ohlcv([100.0] * 10, start="2012-12-27")
    import pandas as pd

    def fake_entries(strategy, df, horizon):
        s = pd.Series(True, index=df.index)
        return s, s

    monkeypatch.setattr(m, "entries_for", fake_entries)
    out = m.count_signals({"AAA": frame}, (0.0, 0.5), horizons=("3m",))
    assert out["0.5|bullish"] == {"2012": 3, "2013": 7}
    assert set(out) == {"0|bullish", "0|bearish", "0.5|bullish", "0.5|bearish"}


def test_registry_record_status_is_derived_from_the_validation_clauses():
    m = _m()
    rec = m.registry_record(_rows("bullish", 10, 5), "2026-10-01")     # N=15, WR 66.7, ExpR +1.0
    assert rec["source"] == "strategy" and rec["strategy"] == "Fibonacci" and rec["horizon"] is None
    assert rec["status"] == "VALIDATED"
    assert rec["window"] == "2024-01-01..2025-12-31" and rec["run_date"] == "2026-10-01"
    assert m.registry_record(_rows("bullish", 9, 5), "2026-10-01")["status"] == "WEAK"   # N=14


def test_validation_refuses_without_preregistration(tmp_path):
    m = _m()
    with pytest.raises(SystemExit):
        m.main(["validation", "--tol", "0.5", "--direction", "bullish",
                "--preregistration", str(tmp_path / "missing.md"), "--out", str(tmp_path / "v.json")])
```

- [ ] **Step 2: Run and confirm failure**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_confluence.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'measure_fib_confluence'`.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""v102: Fibonacci x Rolling S/R confluence on extended history.

Spec: docs/superpowers/specs/2026-09-24-v102-fib-sr-confluence-extended-history-design.md
Reads the EXTENDED cache only -- run with BACKTEST_CACHE_DIR=data/backtest_cache_ext.
The shared cache starts 2018-06 and would silently shrink TRAIN_EXT, so the
script refuses to run against it.

Stages (one verdict per direction):
  count       Stage 0: raw signal survivors per tolerance/direction/year (no backtest)
  collect     backtest trades for 0.0 + every GRID tolerance, TRAIN_EXT entries only
  evaluate    Stage 1 selection + Stage 2 walk-forward, pure over a collect JSON
  validation  Stage 3: ONE tolerance, one direction, VALIDATION entries only;
              requires the committed pre-registration

Run (from the repo root):
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py count --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py collect --out <json>
  python scripts/backtest/measure_fib_confluence.py evaluate --rows <collect json> --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py validation \\
      --tol 0.5 --direction bullish --preregistration <md> --out <json>
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from measure_bearish_arms import _unmasked_gates, apply_laggard_rule  # noqa: E402
from run_backtest_range import (  # noqa: E402
    _build_asof_map, _tickers_for_run, _with_context, load_cached, merge_registry, window_trades,
)
from swingbot.core.backtesting import arm_rule  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import entries_for, gate_override  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402

STRATEGY = "Fibonacci"
DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)
EXT_CACHE_NAME = "backtest_cache_ext"

# --- pre-registered constants (spec "Windows and funnel") ---
TRAIN_EXT = ("2010-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
TRAIN_START_YEAR = 2010
FOLD_YEARS = tuple(range(2013, 2024))
GRID = (0.25, 0.5, 0.75, 1.0)
BASELINE_TOL = 0.0
WR_FLOOR = 50.0
MIN_N_TRAIN = 30
MIN_N_VALIDATION = 15
MAX_SCRATCH_SHARE = 0.5
FOLD_MIN_N = 15
FOLD_POSITIVE_SHARE = 2 / 3
MIN_QUALIFYING_FOLDS = 3


def tol_key(tol) -> str:
    return f"{float(tol):g}"


def require_ext_cache():
    from swingbot.core.marketdata import backtest_cache
    if backtest_cache.CACHE_DIR.name != EXT_CACHE_NAME:
        raise SystemExit(f"v102 reads the extended cache only: run with "
                         f"BACKTEST_CACHE_DIR=data/{EXT_CACHE_NAME} (got {backtest_cache.CACHE_DIR})")


@contextlib.contextmanager
def confluence_tol(tol):
    from swingbot import config
    previous = getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0)
    config.FIB_SR_CONFLUENCE_ATR = float(tol)
    try:
        yield
    finally:
        config.FIB_SR_CONFLUENCE_ATR = previous


class Progress:
    """Flushed `[k/N] P% label` lines -- the percent answers "how far along"."""

    def __init__(self, total):
        self.total, self.done = max(total, 1), 0

    def tick(self, label):
        self.done += 1
        print(f"[{self.done}/{self.total}] {self.done / self.total * 100:.0f}% {label}", flush=True)


def _direction_gate(direction):
    if direction == "bearish":
        return gate_override(STRATEGY, _unmasked_gates(STRATEGY))
    return contextlib.nullcontext()


def _row(ticker, horizon_key, trade):
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple}


def _direction_pass(frames, asof_map, direction, window, horizons, run_fn, progress, label):
    raw = []
    with _direction_gate(direction):
        for ticker, frame in sorted(frames.items()):
            progress.tick(f"{label} {direction} {ticker}")
            for h in horizons:
                summary = run_fn(ticker, frame, STRATEGY, h, one_at_a_time=True, exit_model="v2",
                                 scale_out=True, tp2_mode="levels", frictions=True,
                                 asof=asof_map.get(ticker))
                raw.extend({"ticker": ticker, "horizon_key": h, "trade": t}
                           for t in window_trades(summary, *window) if t.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(r["ticker"], r["horizon_key"], r["trade"]) for r in raw]


def collect_trades(frames, asof_map, tol, window, *, horizons=ALL_HZ, run_fn=None, progress=None):
    """Bullish from the LIVE gate; bearish unmasked + v93 laggard rule."""
    run_fn = run_fn or run_backtest
    progress = progress or Progress(len(frames) * len(DIRECTIONS))
    rows = []
    with confluence_tol(tol):
        for direction in DIRECTIONS:
            rows.extend(_direction_pass(frames, asof_map, direction, window, horizons, run_fn,
                                        progress, f"tol={tol_key(tol)}"))
    return rows


def _signal_years(frame, horizon, direction):
    bullish, bearish = entries_for(STRATEGY, frame, horizon)
    series = bullish if direction == "bullish" else bearish
    dates = frame.index[series.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
    return [d[:4] for d in dates if TRAIN_EXT[0] <= d <= TRAIN_EXT[1]]


def count_signals(frames, tols, *, horizons=ALL_HZ):
    """Stage 0: raw signal counts -- an UPPER bound on decided trades
    (one-at-a-time, no-target drops and the bearish laggard rule only remove)."""
    out = {}
    for tol in tols:
        with confluence_tol(tol):
            for direction in DIRECTIONS:
                by_year = collections.Counter()
                with _direction_gate(direction):
                    for frame in frames.values():
                        for h in horizons:
                            by_year.update(_signal_years(frame, h, direction))
                out[f"{tol_key(tol)}|{direction}"] = dict(sorted(by_year.items()))
    return out


def pooled(rows):
    return arm_rule.pooled_stats([SimpleNamespace(**r) for r in rows])


def badge_verdict(stats, min_n):
    clauses = {
        "wr": stats.get("win_rate") is not None and stats["win_rate"] >= WR_FLOOR,
        "exp_r": stats.get("expectancy_r") is not None and stats["expectancy_r"] > 0,
        "n": (stats.get("n") or 0) >= min_n,
        "scratch": (stats.get("scratch_timeout_share") is not None
                    and stats["scratch_timeout_share"] <= MAX_SCRATCH_SHARE),
    }
    return {"clears": all(clauses.values()), "clauses": clauses}


def _dir(rows, direction):
    return [r for r in rows if r["direction"] == direction]


def _years(rows, first, last):
    return [r for r in rows if first <= int(r["entry_date"][:4]) <= last]


def _plateau_ok(cells, tol):
    i = GRID.index(tol)
    neighbours = [GRID[j] for j in (i - 1, i + 1) if 0 <= j < len(GRID)]
    return all(cells[n]["verdict"]["clears"] for n in neighbours)


def stage1(rows_by_tol, direction):
    cells = {}
    for tol in GRID:
        stats = pooled(_dir(rows_by_tol[tol_key(tol)], direction))
        cells[tol] = {"stats": stats, "verdict": badge_verdict(stats, MIN_N_TRAIN)}
    passing = [t for t in GRID if cells[t]["verdict"]["clears"] and _plateau_ok(cells, t)]
    winner = max(passing, key=lambda t: cells[t]["stats"]["expectancy_r"]) if passing else None
    baseline = pooled(_dir(rows_by_tol[tol_key(BASELINE_TOL)], direction))
    return {"baseline": baseline, "cells": {tol_key(t): c for t, c in cells.items()},
            "plateau_passing": passing, "winner": winner}


def fold_pick(rows_by_tol, direction, year):
    """Train span TRAIN_START_YEAR..year-1: the highest-ExpR grid tolerance
    among cells with decided N >= MIN_N_TRAIN. None when no cell qualifies."""
    best = None
    for tol in GRID:
        stats = pooled(_dir(_years(rows_by_tol[tol_key(tol)], TRAIN_START_YEAR, year - 1), direction))
        if stats["n"] < MIN_N_TRAIN or stats["expectancy_r"] is None:
            continue
        if best is None or stats["expectancy_r"] > best[1]:
            best = (tol, stats["expectancy_r"])
    return None if best is None else best[0]


def fold_verdict(folds):
    qualifying = [f for f in folds if f["stats"] is not None and f["stats"]["n"] >= FOLD_MIN_N]
    positive = sum(1 for f in qualifying
                   if f["stats"]["expectancy_r"] is not None and f["stats"]["expectancy_r"] > 0)
    clears = (len(qualifying) >= MIN_QUALIFYING_FOLDS
              and positive >= FOLD_POSITIVE_SHARE * len(qualifying))
    return {"clears": clears, "qualifying": len(qualifying), "positive": positive,
            "unselected": sum(1 for f in folds if f["tol"] is None)}


def stage2(rows_by_tol, direction):
    folds = []
    for year in FOLD_YEARS:
        tol = fold_pick(rows_by_tol, direction, year)
        stats = (pooled(_dir(_years(rows_by_tol[tol_key(tol)], year, year), direction))
                 if tol is not None else None)
        folds.append({"test_year": year, "tol": tol, "stats": stats})
    return {"folds": folds, "verdict": fold_verdict(folds)}


def registry_record(rows, run_date):
    stats = pooled(rows)
    status = "VALIDATED" if badge_verdict(stats, MIN_N_VALIDATION)["clears"] else "WEAK"
    return {"source": "strategy", "strategy": STRATEGY, "horizon": None, "status": status,
            "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{VALIDATION[0]}..{VALIDATION[1]}", "run_date": run_date}


def _load_frames(universe=None, tickers=None):
    names = tickers.split(",") if tickers else _tickers_for_run(universe)
    frames = {t: _with_context(load_cached(t)) for t in names}
    return {t: f for t, f in frames.items()
            if f is not None and liquidity_reason(f) is None and not data_quality_issues(f, t)}


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")


def _cmd_count(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    _write(args.out, {"universe_n": len(frames),
                      "counts": count_signals(frames, (BASELINE_TOL, *GRID))})


def _cmd_collect(args):
    require_ext_cache()
    started = time.monotonic()
    frames = _load_frames(args.universe, args.tickers)
    asof_map = _build_asof_map(list(frames), frames, args.universe)
    tols = (BASELINE_TOL, *GRID)
    progress = Progress(len(tols) * len(frames) * len(DIRECTIONS))
    rows_by_tol = {tol_key(t): collect_trades(frames, asof_map, t, TRAIN_EXT, progress=progress)
                   for t in tols}
    _write(args.out, {"window": TRAIN_EXT, "universe_n": len(frames), "rows_by_tol": rows_by_tol,
                      "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_evaluate(args):
    rows_by_tol = json.loads(Path(args.rows).read_text(encoding="utf-8"))["rows_by_tol"]
    out = {}
    for direction in DIRECTIONS:
        s1 = stage1(rows_by_tol, direction)
        s2 = stage2(rows_by_tol, direction)
        proceed = s1["winner"] is not None and s2["verdict"]["clears"]
        out[direction] = {"stage1": s1, "stage2": s2, "proceed_to_validation": proceed,
                          "validation_tol": s1["winner"] if proceed else None}
    _write(args.out, out)


def _cmd_validation(args):
    prereg = Path(args.preregistration)
    if not prereg.is_file():
        raise SystemExit(f"VALIDATION needs the committed pre-registration; not found: {prereg}")
    if float(args.tol) not in GRID:
        raise SystemExit(f"--tol must be a GRID value {GRID}, got {args.tol}")
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    asof_map = _build_asof_map(list(frames), frames, args.universe)
    rows = _dir(collect_trades(frames, asof_map, float(args.tol), VALIDATION), args.direction)
    stats = pooled(rows)
    _write(args.out, {"direction": args.direction, "tol": float(args.tol),
                      "preregistration": str(prereg), "stats": stats,
                      "verdict": badge_verdict(stats, MIN_N_VALIDATION), "rows": rows})


def _cmd_emit(args):
    rows = []
    for path in args.validation_json:
        rows.extend(json.loads(Path(path).read_text(encoding="utf-8"))["rows"])
    merge_registry(args.registry, [registry_record(rows, args.run_date)])


def _parser():
    ap = argparse.ArgumentParser(description="v102 Fibonacci x Rolling S/R confluence funnel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect", "validation"):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True)
        p.add_argument("--universe")
        p.add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["validation"].add_argument("--tol", required=True)
    sub.choices["validation"].add_argument("--direction", required=True, choices=DIRECTIONS)
    sub.choices["validation"].add_argument("--preregistration", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--rows", required=True)
    ev.add_argument("--out", required=True)
    em = sub.add_parser("emit-registry")
    em.add_argument("--validation-json", nargs="+", required=True)
    em.add_argument("--registry", required=True)
    em.add_argument("--run-date", required=True)
    return ap


COMMANDS = {"count": _cmd_count, "collect": _cmd_collect, "evaluate": _cmd_evaluate,
            "validation": _cmd_validation, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v102 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_confluence.py` → 12 passed.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fib_confluence.py` → no block at 15 or more.

- [ ] **Step 5: Smoke-run `count` on the shared cache and confirm the refusal**

Run: `python scripts/backtest/measure_fib_confluence.py count --tickers AAPL --out "$TMPDIR/v102_count.json"` (use the session scratchpad if `$TMPDIR` is unset)
Expected: exits with `v102 reads the extended cache only: ...`. This is correct; the extended cache doesn't exist until Task V102-4.

- [ ] **Step 6: Commit, review, merge**

```bash
git add scripts/backtest/measure_fib_confluence.py tests/scripts/test_measure_fib_confluence.py
git commit -m "feat(v102): measure_fib_confluence -- count/collect/evaluate/validation funnel"
```

After the final whole-branch review of V102-1..3, fast-forward `main` per the `worktree-lifecycle` skill. Check `git log main` for other sessions' commits first; use a rebase or merge commit if main moved.

---

# Phase B — Data and measurement (on `main`)

### Task V102-4: Fetch the extended cache and check it against v101

**Files:**
- Create (git-ignored): `data/backtest_cache_ext/*.csv`
- Create: `docs/superpowers/results/2026-MM-DD-v102-ext-cache-check.md` (run date)

- [ ] **Step 1: Fetch** (network; minutes)

Run: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --start 2010-01-01 --end 2025-12-31`
Expected: `Done: N fetched, 0 already cached, K failed [...]`. The failed list should match the tickers that are also absent from `data/backtest_cache/` (on 2026-09-24: CRWV, SNDK, SPCX, and the futures `GC=F`/`SI=F` cached as `GC_F`/`SI_F`).

- [ ] **Step 2: Coverage check**

```bash
python - <<'EOF'
import pathlib, pandas as pd
main = {p.stem for p in pathlib.Path("data/backtest_cache").glob("*.csv")}
ext = {p.stem for p in pathlib.Path("data/backtest_cache_ext").glob("*.csv")}
print("missing_in_ext", sorted(main - ext)); print("extra_in_ext", sorted(ext - main))
firsts = {p.stem: pd.read_csv(p, index_col=0, nrows=1).index[0] for p in pathlib.Path("data/backtest_cache_ext").glob("*.csv")}
early = sum(1 for d in firsts.values() if str(d)[:10] <= "2010-01-05")
print("tickers_with_2010_data", early, "of", len(firsts))
print("SPY_first", firsts.get("SPY"))
EOF
```

Required: `missing_in_ext` is empty, and SPY starts at or before 2010-01-05. If `missing_in_ext` is not empty, re-run the fetch with `--force` for those names (as listed in `data/watchlist.json`) before going on.

- [ ] **Step 3: Equivalence check against v101 (data sanity, not a gate on the hypothesis)**

Dispatch to `backtest-runner`: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_diagnostic.py --out <scratchpad>/v102_equiv.json --md <scratchpad>/v102_equiv.md`, with progress to a log that is deleted on success.
Compare with v101's current-arithmetic baselines (`results/2026-09-24-v101-fib-diagnostic.md`): bullish N 288 / WR 28.8% / ExpR +0.039, bearish N 94 / 25.5% / −0.091. **Tolerance:** N within ±5%, WR within ±1.5pp, ExpR within ±0.03 per direction. Deeper warm-up and re-based adjusted prices cause small drift. Outside tolerance → **stop**: find the cause (adjusted-price rebasing, a ticker whose history changed, the universe filter) and record it before V102-5.

- [ ] **Step 4: Write the check doc and commit**

`docs/superpowers/results/<date>-v102-ext-cache-check.md`: the fetch summary, coverage output, tickers with 2010 data, the equivalence table (v101 vs ext cache, per direction) and a pass/stop line.

```bash
git add docs/superpowers/results/*-v102-ext-cache-check.md
git commit -m "docs(v102): extended 2010-2025 cache fetched and checked against v101"
```

---

### Task V102-5: Stage 0 — signal counts

- [ ] **Step 1: Load `backtest-gate`.** Stage 0 is free: counts only, no backtest, no VALIDATION data (`count` filters to TRAIN_EXT).

- [ ] **Step 2: Run**

Run: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py count --out docs/superpowers/results/<date>-v102-stage0-count.json`
Short run (entries only). If it exceeds 2 minutes, dispatch it to `backtest-runner` instead.

- [ ] **Step 3: Decide per direction**

For each direction, total the TRAIN_EXT signals at the loosest tolerance (`"1|bullish"`, `"1|bearish"`). The count is an upper bound on decided trades. **Below 30 → that direction closes no-lift at Stage 0.** Also record the `"0|..."` baseline totals and the per-year spread at each tolerance. Years with 0–5 signals show where the Stage 2 folds will be thin.

- [ ] **Step 4: Write `docs/superpowers/results/<date>-v102-stage0.md`** (the counts table: tolerance × direction × total, plus per-year rows; the per-direction decision) **and commit**

```bash
git add docs/superpowers/results/*-v102-stage0*
git commit -m "docs(v102): Stage 0 signal counts -- <directions entering Stage 1 | NO-LIFT>"
```

If both directions close here, go to Task V102-9 (NO-LIFT path).

---

### Task V102-6: Pre-registration (committed before any backtest of a tolerance)

**Files:**
- Create: `docs/superpowers/results/<date>-v102-preregistration.md`

- [ ] **Step 1: Write it.** It must state, verbatim from Global Constraints and the script's constants:
  - the directions entering Stage 1 (from V102-5) and why any direction was dropped;
  - `TRAIN_EXT`, `FOLD_YEARS`, `VALIDATION`, `GRID`, the `BASELINE_TOL` role (reference only), and all badge and fold constants;
  - the Stage 1 plateau and winner rules, the Stage 2 per-fold re-selection rule, the definition of an unselected fold, and the fold verdict;
  - the populations (live-gate bullish, unmasked + laggard bearish) and the arithmetic (v2, scale-out, TP2 levels, frictions);
  - the extended cache and the V102-4 equivalence result;
  - survivorship bias: stated, not corrected, and the direction it biases (toward higher WR and ExpR in the early years);
  - **the one-shot rule:** at most one `validation` run per direction, at the evaluate output's `validation_tol`, and never at another tolerance;
  - if v100 has merged: v102's funnel is self-contained (its own Stage 2 rule) and does not go through `validate_component.py`.

- [ ] **Step 2: Commit on `main` before V102-7**

```bash
git add docs/superpowers/results/*-v102-preregistration.md
git commit -m "docs(v102): pre-register Fibonacci x Rolling S/R confluence (TRAIN_EXT, 11 folds, one shot per direction)"
```

---

### Task V102-7: Stages 1–2 — collect once, evaluate

- [ ] **Step 1: Load `backtest-gate`.** Confirm the pre-registration commit exists (`git log --oneline -3 -- docs/superpowers/results/*-v102-preregistration.md`).

- [ ] **Step 2: Collect.** Dispatch to `backtest-runner`, running in the background (expect tens of minutes; 5 tolerances × 2 passes × ~73 tickers × 10 horizons over 16 years):

> From the repo root, no `cd`: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py collect --out data/v102_collect.json > <scratchpad>/v102_collect.log 2>&1`. Progress lines are `[k/N] P% tol=… direction TICKER`. Answer "how far along" from the last log line's percent. On success, return the final line and `universe_n` / `elapsed_s` from the JSON, and delete the log. On failure, return the last 40 log lines.

`data/v102_collect.json` stays local (git-ignored, like v93's arm files). The evaluate output is what gets committed.

- [ ] **Step 3: Evaluate**

Run: `python scripts/backtest/measure_fib_confluence.py evaluate --rows data/v102_collect.json --out docs/superpowers/results/<date>-v102-stage12.json`

- [ ] **Step 4: Write `docs/superpowers/results/<date>-v102-stage12.md`**
  - per direction: the baseline (tol 0) N / WR / ExpR; every grid cell's N / WR / ExpR / scratch share / clears / plateau; the winner or none;
  - Stage 2: the fold table (year, selected tolerance, N, ExpR) and the verdict (qualifying, positive, unselected);
  - `## Verdict` per direction: `PROCEED-VALIDATION at tol=<x>` or `NO-LIFT at Stage 1|2`;
  - invoke `pooled-numbers` before writing any figure, and state N and the window with every figure.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/*-v102-stage12*
git commit -m "docs(v102): Stages 1-2 on TRAIN_EXT -- <per-direction verdict>"
```

If no direction proceeds, go to Task V102-9 (NO-LIFT path).

---

### Task V102-8: Stage 3 — VALIDATION (one shot per proceeding direction)

- [ ] **Step 1: Load `backtest-gate`.** For each proceeding direction, confirm that no `*-v102-validation-<direction>.json` exists yet. **Its existence means the shot is spent, so stop.**

- [ ] **Step 2: Run each proceeding direction exactly once** (dispatched to `backtest-runner`):

`BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py validation --tol <validation_tol from stage12.json> --direction <d> --preregistration docs/superpowers/results/<date>-v102-preregistration.md --out docs/superpowers/results/<date>-v102-validation-<d>.json`

- [ ] **Step 3: Write `docs/superpowers/results/<date>-v102-validation.md`**: per direction, N / WR / ExpR / scratch share, each clause, and `PASS` or `FAIL`. A FAIL is final. No re-run, and no other tolerance.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/*-v102-validation*
git commit -m "docs(v102): VALIDATION -- <per-direction PASS/FAIL>"
```

---

### Task V102-9: Wiring (any PASS) or close-out (NO-LIFT)

**PASS path** (one or both directions passed VALIDATION). Do this on a short worktree branch, then merge:

- [ ] **Step 1:** In `swingbot/config.py`, set the `FIB_SR_CONFLUENCE_ATR` Field's `default` to the validated tolerance (as a string, e.g. `"0.5"`). Update its help text: `Validated in v102 (<date>): <direction(s)> at <tol>`. Set `.env.example` to the same value.
- [ ] **Step 2:** In `swingbot/core/market/strategy_types.py`, replace the `"Fibonacci"` entry of `STRATEGY_GATES` and its comment:

```python
    # v102, CURRENT arithmetic (2% cap), FIB_SR_CONFLUENCE_ATR=<tol>:
    # TRAIN_EXT 2010-2023 <dir> N=<n> WR=<wr> ExpR=<e>; VALIDATION 2024-25 N=<n> WR=<wr> ExpR=<e>.
    # <other direction>: <v102 result or "v93: fail, no mechanism passed">.
    "Fibonacci": {"directions": (<passing directions>,)},
```

If both directions passed, the entry becomes `{}`, the key is removed, and the comment records both.
- [ ] **Step 3:** Add a test in `tests/market/test_fib_sr_confluence.py` asserting `config.FIB_SR_CONFLUENCE_ATR` defaults to the validated tolerance and `STRATEGY_GATES["Fibonacci"]` allows exactly the passing directions. Run it, plus `tests/test_env_example_sync.py` and `tests/market/test_entry_filters.py`.
- [ ] **Step 4:** Emit the registry row, never by hand:
`python scripts/backtest/measure_fib_confluence.py emit-registry --validation-json <the passing directions' validation JSONs> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>`
With two files, the row pools both directions: that is the population the live gate then lets through.
- [ ] **Step 5:** Add the closed row to `docs/claude/backtest-methodology.md` (PASS: tolerance, figures, windows, results links). Commit code and docs, then merge per `worktree-lifecycle`.

**NO-LIFT path:**

- [ ] **Step 1:** Add the closed row to `docs/claude/backtest-methodology.md`: the stage it ended at, the per-direction figures with N and window, and "reopening needs a mechanism other than Rolling S/R confluence at 0.25–1.0 ATR".
- [ ] **Step 2:** `git mv` the spec to `docs/superpowers/specs/no-lift/` and this plan to `docs/superpowers/plans/no-lift/`. Add under the spec's headers: `**Status:** Closed no-lift <date> at Stage <n>; VALIDATION <spent: FAIL | not spent>.`
- [ ] **Step 3:** Keep `FIB_SR_CONFLUENCE_ATR` in the code at default 0 (inert, like `FIB_TARGET_1_0_EXTENSION`), and keep the extended cache and `BACKTEST_CACHE_DIR` for later tests. Commit: `docs(v102): close Fibonacci confluence no-lift at Stage <n>`.

---

### Task V102-10: Full-suite verification and close-out

- [ ] **Step 1:** Dispatch `test-runner` for `python scripts/dev/testrun.py full`. Require `0 failed` and `0 xfailed`. If a failure passes in isolation and is in code v102 never touched, report it with both outputs. Don't call the suite green.
- [ ] **Step 2 (PASS path only):** bump `VERSION.json` `bot` minor per `docs/claude/working-conventions.md`, regenerate and commit `version_history.json` (memory `version-bump-needs-regeneration`), and `git mv` the spec and plan to `implemented/`.
- [ ] **Step 3:** Remove the worktree and delete the merged branch (`git rev-list --count main..<branch>` must be 0; never a `backup`/`stable-*` branch).
