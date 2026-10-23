# v180 — Turtle Soup entry, Part 1: signal, acceptance instrument and plan builder

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V180-3:" -A 400 docs/superpowers/plans/2026-10-21-v180-turtle-soup-entry_1-signal-instrument-and-plan.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Screen:** screen-turtle_soup SCREEN-PASS
**Spec:** [2026-10-21-v180-turtle-soup-entry-design.md](../specs/2026-10-21-v180-turtle-soup-entry-design.md)
**Index:** [2026-10-21-v180-turtle-soup-entry_0-index.md](2026-10-21-v180-turtle-soup-entry_0-index.md) — Goal, Architecture, Global Constraints, Contracts, Parallelisation and the task ledger live there. Every task below implicitly includes the index's Global Constraints.

**Tasks in this part:** V180-1 (live signal and mask), V180-2 (A1/A3 pooled ΔWR), V180-3 (A2 shift-replay permutation), V180-4 (structural plan builder).

**Where:** every task runs in the worktree `.claude/worktrees/2026-10-21-v180-turtle-soup-entry` on the branch of the same name (V180-1 Step 0 creates it). All paths below are relative to the worktree root, and every command runs from there. Commit each task on the worktree branch; never touch the main tree.

## Parallelisation (this part)

See the index's `## Parallelisation`. Inside this part: V180-1 with V180-2 (disjoint files), then V180-3 (needs V180-2's `win_rate_statistic`) with V180-4 (needs V180-1's `TURTLE_SOUP` and shares `strategy_types.py` with it).

## Review Focus

The inputs the spec implies but no headline test exercises, most likely to bite first. Each one has a test in the task that owns the code.

- **Short or gappy frames.** A frame with fewer than 21 bars, or a NaN Low inside the channel, must yield no signal and raise nothing, exactly as the screen does (V180-1, `test_short_and_nan_frames_match_the_screen`).
- **A stop exactly at the 3% ceiling.** `_bounded_stop` keeps a stop whose distance equals the ceiling (`<=`), so a plan at exactly 3.0% survives and 3.01% drops (V180-4, `test_stop_at_the_ceiling_is_kept_and_just_beyond_is_dropped`).
- **A level exactly on a band edge.** A level at exactly 1.5R or 2.5R is inside the band; float noise on a $600 stock must not push it out (V180-4, `test_in_band_keeps_both_edges`).
- **An additive arm whose added rows decide nothing.** The pooled ΔWR is then a pure re-weighting of the baseline (0.0), and a fold whose added decided count is 0 fails the N ≥ 30 floor instead of passing on the baseline's N (V180-2, `test_pooled_row_counts_only_decided_added_trades`).
- **A replay that raises mid-run.** `bt.ENTRY_SHIFT` is process-global; an exception inside a shifted replay must still restore it to 0, or every later replay in the process runs shifted (V180-3, `test_replay_restores_entry_shift_after_an_error`).

---

# Phase A — Signal and acceptance instrument

### Task V180-1: Live Turtle Soup signal, mask and screen parity

**Model:** opus — the live re-implementation must match a frozen statistical trigger bar for bar (tie rule, NaN windows) and stay lookahead-free; a silent parity drift invalidates the whole funnel.

**Files:**
- Create: `swingbot/core/market/turtle_soup.py`
- Create: `tests/market/test_turtle_soup_signal.py`
- Modify: `swingbot/core/market/strategy_types.py` (name constant beside `FIB_LIMIT`, l.24; `STRATEGY_GATES` entry beside `FIB_LIMIT`'s, l.274)
- Modify: `swingbot/core/market/entry_filters.py` (import block l.21-26; new function and registration after `ENTRY_FUNCS[FIB_LIMIT] = fibonacci_limit_entries`, l.562)

**Interfaces:**
- Consumes: the frozen screen `swingbot/core/backtesting/screen/ideas/turtle_soup.py` (`events(df)`, `PARAMS = {"channel": 20, "min_age": 4}`), tests only; `tests/backtesting/screen/helpers.py` (`frame`, `random_walk`, `assert_prefix_stable`); `entry_filters._off`, `admits`, `gate_override`, `entries_for`.
- Produces:
  - `strategy_types.TURTLE_SOUP = "Turtle Soup"`; `STRATEGY_GATES[TURTLE_SOUP] = {"directions": ()}`.
  - `swingbot/core/market/turtle_soup.py`: `CHANNEL = 20`, `MIN_AGE = 4`, `sweep_frame(df: pd.DataFrame) -> pd.DataFrame` (index `df.index`; columns `"prior_low"`, `"age"` (float, NaN until 20 prior bars), `"signal"` (bool)), `turtle_soup_signal(df: pd.DataFrame) -> pd.Series` (bool, name `"turtle_soup"`).
  - `entry_filters.turtle_soup_entries(df, horizon_key, params=None) -> tuple[pd.Series, pd.Series]`; `ENTRY_FUNCS[TURTLE_SOUP] = turtle_soup_entries`.

- [ ] **Step 0: Create the worktree** (`worktree-lifecycle` skill; check `git worktree list` first and reuse the worktree if it already exists)

```bash
git worktree add .claude/worktrees/2026-10-21-v180-turtle-soup-entry -b 2026-10-21-v180-turtle-soup-entry main
cd .claude/worktrees/2026-10-21-v180-turtle-soup-entry
```

Expected: `Preparing worktree (new branch '2026-10-21-v180-turtle-soup-entry')`. Every later step and task runs from this directory.

- [ ] **Step 1: Write the failing tests** — `tests/market/test_turtle_soup_signal.py`

```python
"""v180: the live Turtle Soup trigger -- bar-for-bar parity with the frozen v140 screen,
no lookahead, masked by default. The screen import is test-only: live code never imports it."""
import inspect

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import backtest
from swingbot.core.backtesting.screen.ideas import turtle_soup as screen
from swingbot.core.market import entry_filters as ef
from swingbot.core.market import turtle_soup as live
from swingbot.core.market.strategy_types import STRATEGY_GATES, TURTLE_SOUP, admits
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

CELL = {"directions": (), "cells": {("bullish", "2w")}}
WALKS = [(7, 500), (11, 300), (23, 1200), (42, 60), (99, 2500)]


def _screen_fixture(low25=95.0, low35=94.0, close35=100.0):
    """The screen tests' fixture (tests/backtesting/screen/test_idea_turtle_soup.py), copied:
    40 flat bars (C 100, L 99); bar 25 sets a 95 low; bar 35 breaks it, closes at close35."""
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[25], lows[35] = low25, low35
    closes[35] = close35
    return frame(closes, lows=lows)


def _equal_lows(age):
    """The old 95 low at bar 20, repeated `age` bars before bar 35, which sweeps it to 94."""
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[20], lows[35 - age], lows[35] = 95.0, 95.0, 94.0
    return frame(closes, lows=lows)


def _assert_parity(df):
    pd.testing.assert_series_equal(live.turtle_soup_signal(df), screen.events(df))


@pytest.mark.parametrize("seed, n", WALKS)
def test_random_walks_match_the_screen_bar_for_bar(seed, n):
    _assert_parity(random_walk(n, seed=seed))


def test_the_random_walk_parity_is_not_vacuous():
    assert sum(int(live.turtle_soup_signal(random_walk(n, seed=s)).sum()) for s, n in WALKS) >= 10


@pytest.mark.parametrize("close35", [100.0, 95.01, 95.0, 94.5])
def test_the_screen_fixture_matches(close35):
    _assert_parity(_screen_fixture(close35=close35))


def test_the_screen_fixture_fires_once_on_the_reclaim():
    assert np.flatnonzero(live.turtle_soup_signal(_screen_fixture()).to_numpy()).tolist() == [35]


@pytest.mark.parametrize("age, fires", [(3, False), (4, True)])
def test_equal_lows_age_from_the_latest_bar_holding_the_low(age, fires):
    df = _equal_lows(age)
    _assert_parity(df)
    assert bool(live.turtle_soup_signal(df).iloc[35]) is fires
    assert live.sweep_frame(df)["age"].iloc[35] == age


def test_short_and_nan_frames_match_the_screen():
    for n in (5, 20, 21):
        _assert_parity(random_walk(n))
    assert not live.turtle_soup_signal(random_walk(20)).any()
    df = random_walk(400, seed=5)
    df.iloc[100, df.columns.get_loc("Low")] = np.nan
    _assert_parity(df)
    assert not live.turtle_soup_signal(df).iloc[100:121].any()


def test_sweep_frame_shape_and_frozen_params():
    df = _screen_fixture()
    sweep = live.sweep_frame(df)
    assert list(sweep.columns) == ["prior_low", "age", "signal"]
    assert sweep.index.equals(df.index)
    assert np.isnan(sweep["prior_low"].iloc[19]) and sweep["prior_low"].iloc[20] == 99.0
    assert (sweep["prior_low"].iloc[35], sweep["age"].iloc[35]) == (95.0, 10.0)
    assert sweep["signal"].dtype == bool
    assert (live.CHANNEL, live.MIN_AGE) == (screen.PARAMS["channel"], screen.PARAMS["min_age"])
    assert live.turtle_soup_signal(df).name == "turtle_soup"


def test_reads_no_later_bar():
    assert live.turtle_soup_signal(random_walk(500)).any()      # non-vacuous
    assert_prefix_stable(live.turtle_soup_signal, random_walk(500), [30, 250, 499])
    assert_prefix_stable(lambda df: live.sweep_frame(df)["age"], random_walk(500), [30, 250, 499])
    assert_prefix_stable(live.turtle_soup_signal, _screen_fixture(), [20, 25, 34, 35, 36, 39])


def test_the_live_module_never_imports_the_screen():
    assert "backtesting" not in inspect.getsource(live)


def test_ships_masked_and_out_of_the_backtest_strategy_list():
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}
    assert TURTLE_SOUP not in backtest.ALL_STRATEGIES
    assert ef.ENTRY_FUNCS[TURTLE_SOUP] is ef.turtle_soup_entries
    df = random_walk(1200, seed=23)
    for horizon_key in ("1w", "2w", "4w"):
        assert not admits(TURTLE_SOUP, "bullish", horizon_key)
        bullish, bearish = ef.entries_for(TURTLE_SOUP, df, horizon_key)
        assert not bullish.any() and not bearish.any()


def test_the_masked_entry_function_skips_the_work(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("masked Turtle Soup computed its signal")
    monkeypatch.setattr(live, "turtle_soup_signal", boom)
    bullish, bearish = ef.turtle_soup_entries(random_walk(500), "2w")
    assert not bullish.any() and not bearish.any()


def test_the_research_cell_unmasks_bullish_2w_only():
    df = random_walk(1200, seed=23)
    expected = live.turtle_soup_signal(df)
    assert expected.any()
    with ef.gate_override(TURTLE_SOUP, CELL):
        bullish, bearish = ef.entries_for(TURTLE_SOUP, df, "2w")
        assert bullish.tolist() == expected.tolist() and not bearish.any()
        other, _ = ef.entries_for(TURTLE_SOUP, df, "4w")
        assert not other.any()
    assert STRATEGY_GATES[TURTLE_SOUP] == {"directions": ()}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_turtle_soup_signal.py`
Expected: collection error, `ImportError: cannot import name 'turtle_soup' from 'swingbot.core.market'` (or `TURTLE_SOUP` from `strategy_types`).

- [ ] **Step 3: Add the name and the mask** — `swingbot/core/market/strategy_types.py`

After `FIB_LIMIT = "Fibonacci Limit"` (l.24):

```python
# v180: bullish sweep-and-reclaim of an aged 20-bar low (screen-turtle_soup SCREEN-PASS).
# Masked, out of backtest.ALL_STRATEGIES; measured only inside the ("bullish", "2w")
# research cell via entry_filters.gate_override.
TURTLE_SOUP = "Turtle Soup"
```

In `STRATEGY_GATES`, after the `FIB_LIMIT: {"directions": ()},` entry:

```python
    # v180 ships masked; arms/turtle_soup_research.RESEARCH_CELL unmasks ("bullish", "2w")
    # for the measure_arms.py replay only. Promotion is a follow-on spec.
    TURTLE_SOUP: {"directions": ()},
```

Do **not** add it to `SHORT_STRATEGIES`.

- [ ] **Step 4: Implement the live trigger** — `swingbot/core/market/turtle_soup.py`

Its own implementation, with no import from `swingbot.core.backtesting`. The tie rule and the NaN handling decide parity, so the algorithm is fixed here:

```python
"""v180: the live Turtle Soup trigger -- bar t sweeps an aged 20-bar low and closes back above it.

Frozen from the v140 screen (screen/ideas/turtle_soup.py, which live code never imports):
Low[t] < L and Close[t] > L, where L = min Low of bars t-20..t-1 and the LATEST bar in that
window holding L is >= MIN_AGE bars before t. NO-LOOKAHEAD: bar t reads bars <= t only.
A window with a NaN Low yields no signal (the screen's rolling min_periods rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

CHANNEL = 20
MIN_AGE = 4


def sweep_frame(df: pd.DataFrame) -> pd.DataFrame:
    """prior_low (L), age (bars from the latest bar holding L to t) and the signal, per bar."""
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    n = len(low)
    prior_low = np.full(n, np.nan)
    age = np.full(n, np.nan)
    if n > CHANNEL:
        windows = sliding_window_view(low[:-1], CHANNEL)        # windows[k]: bars k..k+19, prior to bar k+20
        valid = ~np.isnan(windows).any(axis=1)
        latest = CHANNEL - 1 - np.argmin(windows[:, ::-1], axis=1)   # latest bar holding the min
        prior_low[CHANNEL:] = np.where(valid, windows.min(axis=1), np.nan)
        age[CHANNEL:] = np.where(valid, CHANNEL - latest, np.nan)
    with np.errstate(invalid="ignore"):
        signal = (low < prior_low) & (close > prior_low) & (age >= MIN_AGE)
    return pd.DataFrame({"prior_low": prior_low, "age": age, "signal": signal}, index=df.index)


def turtle_soup_signal(df: pd.DataFrame) -> pd.Series:
    """The bullish signal series, named like the screen's events()."""
    return sweep_frame(df)["signal"].astype(bool).rename("turtle_soup")
```

- [ ] **Step 5: Register the masked entry function** — `swingbot/core/market/entry_filters.py`

Add `TURTLE_SOUP` to the `strategy_types` import (l.23-26) and `from swingbot.core.market import turtle_soup as turtle_soup_mod` below it. After `ENTRY_FUNCS[FIB_LIMIT] = fibonacci_limit_entries`:

```python
def turtle_soup_entries(df, horizon_key, params=None):
    """v180 Turtle Soup: bullish sweep-and-reclaim bars; never bearish. `params` is
    accepted for the ENTRY_FUNCS contract and ignored -- the trigger is frozen
    (turtle_soup.CHANNEL, MIN_AGE). While masked (it ships masked) this returns
    all-False without computing the signal, so the live scan pays nothing for it."""
    off = _off(df)
    if not admits(TURTLE_SOUP, "bullish", horizon_key):
        return off, off.copy()
    return turtle_soup_mod.turtle_soup_signal(df).astype(bool), off


ENTRY_FUNCS[TURTLE_SOUP] = turtle_soup_entries
```

No `DEFAULT_PARAMS` entry: nothing may tune the frozen trigger.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_turtle_soup_signal.py`
Expected: all pass, `0 failed`.

- [ ] **Step 7: Run the existing tests that enumerate `ENTRY_FUNCS` or guard the screen**

Run, one at a time:
- `python scripts/dev/testrun.py file tests/market/test_v113_horizon.py`
- `python scripts/dev/testrun.py file tests/marketdata/test_spot_scaling_parity.py`
- `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
- `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_turtle_soup.py`
- `python scripts/dev/testrun.py file tests/planning/test_fib_limit_registration.py`

Expected: each `0 failed`, with no test modified. Then `python scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/market/turtle_soup.py swingbot/core/market/strategy_types.py swingbot/core/market/entry_filters.py tests/market/test_turtle_soup_signal.py
git commit -m "feat(v180): masked Turtle Soup entry -- live sweep-and-reclaim trigger at screen parity" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V180-2: A1/A3 — pooled ΔWR selectable in acceptance, fold rows and validate_component

**Model:** opus — an acceptance-gate statistic: a wrong default or a leaked branch silently changes every past and future verdict, and the amendment must relax nothing.

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (`delta_expectancy_r` l.225 — add after it; `AcceptanceResult` l.430; `_clause_win_rate` l.480; `evaluate` l.586; `render_json` l.615)
- Modify: `swingbot/core/backtesting/backtest_wf.py` (add `win_rate_fold_row` after `gate_win_rate`, l.~248)
- Modify: `scripts/backtest/validate_component.py` (imports l.14 and l.21; `_mde_design` l.72; `stage_mde` l.86; `_fold_row` l.124; `stage_walkforward` l.132; `_evaluate` l.~190; `main` argparse)
- Create: `tests/backtesting/test_acceptance_pooled_wr.py`
- Create: `tests/backtesting/test_wf_pooled_fold_row.py`
- Create: `tests/backtesting/test_validate_component_pooled.py`

**Interfaces:**
- Consumes: `acceptance.win_rate`, `DECIDED`, `population_split`, `bootstrap_delta`, `delta_standardised_win_rate`, `mde_paired` (all exist); `backtest_wf.gate_win_rate` (unchanged).
- Produces (the index's Contracts, verbatim):
  - `acceptance.delta_pooled_win_rate(baseline, component) -> float | None` — `win_rate(component) - win_rate(baseline)` in pp over decided trades; None when either arm decided nothing.
  - `acceptance.WR_STATISTICS: dict[str, Callable] = {"standardised": delta_standardised_win_rate, "pooled": delta_pooled_win_rate}`.
  - `acceptance.win_rate_statistic(name: str) -> Callable` — unknown name raises `ValueError` naming the valid keys.
  - `acceptance.evaluate(baseline, component, *, stage, permutation_p=None, n_resamples=BOOTSTRAP_RESAMPLES, seed=42, cluster="ticker", wr_statistic: str = "standardised") -> AcceptanceResult`.
  - `AcceptanceResult.wr_statistic: str = "standardised"`; `render_json` adds `"wr_statistic"` only when it is not `"standardised"`.
  - `backtest_wf.win_rate_fold_row(test_year: str, baseline, component, *, wr_statistic: str = "standardised") -> dict` — standardised: `{"test_years", "delta_win_rate_pp", "n": min(decided b, decided c)}` (today's row); pooled: `{"test_years", "delta_win_rate_pp": delta_pooled_win_rate(b, c), "n": <decided count of population_split(b, c)["added"]>, "wr_statistic": "pooled"}`.
  - `validate_component.py`: `--wr-statistic {standardised,pooled}` (default `standardised`; `parser.error` when `pooled` is combined with `--gate harvest`); `--train-effect-from-arms` (stage mde: the claimed effect is the selected statistic on the `--arms` pair, printed).
  - Test helpers other tasks reuse: `tests/backtesting/test_acceptance_pooled_wr.py::_trade(ticker, strategy, horizon, day, outcome) -> ArmTrade` and `::_arms(n_tickers=40, lift=4) -> (baseline, component)`.

- [ ] **Step 1: Write the failing acceptance tests** — `tests/backtesting/test_acceptance_pooled_wr.py`

```python
"""v180 A1 (the v119 A1-A4 amendment, adopted verbatim): the pooled, unstandardised dWR.
The standardised dWR weights strata by the BASELINE's mix, so a strategy the baseline lacks
is weightless and dWR is exactly 0 for any additive arm."""
import pytest

from swingbot.core.backtesting.acceptance import (WR_STATISTICS, ArmTrade, delta_pooled_win_rate,
                                                  delta_standardised_win_rate, evaluate,
                                                  render_json, win_rate_statistic)


def _trade(ticker, strategy, horizon, day, outcome):
    r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0)
    return ArmTrade(ticker, strategy, horizon, f"2022-{1 + day // 28:02d}-{1 + day % 28:02d}",
                    outcome, r, 2.0, "strategy", "bullish")


def _arms(n_tickers=40, lift=4):
    """Baseline: 10 MACD/3m trades per ticker, 2 + t % 5 wins (pooled 40% when n_tickers is a
    multiple of 5). Component: the same rows plus 10 Turtle Soup/2w trades per ticker with
    2 + (3t) % 5 + lift wins (pooled 40% + 10 * lift pp). Tickers differ, so the bootstrap has spread."""
    baseline, added = [], []
    for t in range(n_tickers):
        base_wins, added_wins = 2 + t % 5, min(10, 2 + (3 * t) % 5 + lift)
        for i in range(10):
            baseline.append(_trade(f"T{t}", "MACD", "3m", i, "win" if i < base_wins else "loss"))
            added.append(_trade(f"T{t}", "Turtle Soup", "2w", 40 + i,
                                "win" if i < added_wins else "loss"))
    return baseline, baseline + added


def test_the_standardised_statistic_is_blind_to_an_added_strategy():
    baseline, component = _arms()
    assert delta_standardised_win_rate(baseline, component) == pytest.approx(0.0)
    assert delta_pooled_win_rate(baseline, component) == pytest.approx(20.0)   # 40% -> 60%


def test_pooled_counts_decided_trades_only():
    baseline, component = _arms(n_tickers=5, lift=0)                          # 40% -> 40%
    undecided = [_trade("T0", "Turtle Soup", "2w", 80, "timeout"),
                 _trade("T0", "Turtle Soup", "2w", 81, "scratch")]
    assert delta_pooled_win_rate(baseline, component + undecided) == pytest.approx(0.0)


def test_pooled_is_none_when_an_arm_decides_nothing():
    baseline, component = _arms(n_tickers=5)
    undecided = [_trade("T0", "MACD", "3m", 0, "timeout")]
    assert delta_pooled_win_rate(undecided, component) is None
    assert delta_pooled_win_rate(baseline, undecided) is None


def test_statistics_are_name_keyed():
    assert WR_STATISTICS == {"standardised": delta_standardised_win_rate,
                             "pooled": delta_pooled_win_rate}
    assert win_rate_statistic("pooled") is delta_pooled_win_rate
    with pytest.raises(ValueError, match="standardised"):
        win_rate_statistic("mixed")


def test_evaluate_defaults_to_the_standardised_statistic_unchanged():
    baseline, component = _arms()
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200)
    assert result.wr_statistic == "standardised"
    assert result.clause("win_rate").detail.startswith("standardised dWR")
    assert result.clause("win_rate").verdict == "FAIL"          # blind: the point is 0.0
    assert "wr_statistic" not in render_json(result)


def test_evaluate_pooled_sees_the_added_strategy():
    baseline, component = _arms()
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200,
                      wr_statistic="pooled")
    clause = result.clause("win_rate")
    assert clause.verdict == "PASS" and clause.value == pytest.approx(20.0)
    assert clause.detail.startswith("pooled dWR")
    assert result.wr_statistic == "pooled"
    assert render_json(result)["wr_statistic"] == "pooled"


def test_pooled_changes_clause_one_only():
    """A4: thresholds, the bootstrap and clauses 2-6 do not depend on the statistic."""
    baseline, component = _arms()
    common = dict(stage="validation", permutation_p=0.01, n_resamples=200)
    std = evaluate(baseline, component, **common)
    pooled = evaluate(baseline, component, wr_statistic="pooled", **common)
    assert ([c for c in std.clauses if c.name != "win_rate"]
            == [c for c in pooled.clauses if c.name != "win_rate"])
    assert (std.strata, std.split, std.seed, std.cluster) == (pooled.strata, pooled.split,
                                                              pooled.seed, pooled.cluster)
    assert pooled.clause("mechanism").verdict == "SKIPPED"


def test_an_unknown_statistic_is_refused_before_any_work():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(ValueError, match="standardised"):
        evaluate(baseline, component, stage="walkforward", n_resamples=50, wr_statistic="mixed")
```

- [ ] **Step 2: Write the failing fold-row tests** — `tests/backtesting/test_wf_pooled_fold_row.py`

```python
"""v180 A1 at stage 2: fold rows on the pooled dWR; per-fold N counts decided ADDED trades
(spec § The funnel, stage 2), never the pooled book."""
import pytest

from swingbot.core.backtesting.acceptance import delta_standardised_win_rate
from swingbot.core.backtesting.backtest_wf import gate_win_rate, win_rate_fold_row
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade


def test_the_standardised_row_is_todays_row():
    baseline, component = _arms()
    assert win_rate_fold_row("2021", baseline, component) == {
        "test_years": "2021",
        "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
        "n": 400}


def test_pooled_row_counts_only_decided_added_trades():
    baseline, component = _arms(n_tickers=3)                     # 30 added, all decided
    extra = [_trade("T0", "Turtle Soup", "2w", 90, "timeout")]
    row = win_rate_fold_row("2022", baseline, component + extra, wr_statistic="pooled")
    assert set(row) == {"test_years", "delta_win_rate_pp", "n", "wr_statistic"}
    assert (row["test_years"], row["n"], row["wr_statistic"]) == ("2022", 30, "pooled")
    assert row["delta_win_rate_pp"] > 0


def test_a_fold_with_no_decided_added_trade_fails_the_floor():
    baseline, _ = _arms()
    undecided = [_trade(f"T{t}", "Turtle Soup", "2w", 60, "timeout") for t in range(40)]
    row = win_rate_fold_row("2023", baseline, baseline + undecided, wr_statistic="pooled")
    assert row["n"] == 0 and row["delta_win_rate_pp"] == pytest.approx(0.0)
    assert gate_win_rate({"folds": [row, row, row]}) == "FAIL"


def test_the_floor_reads_added_trades_not_the_pooled_book():
    baseline, component = _arms(n_tickers=3)                     # 30 added
    passing = win_rate_fold_row("2021", baseline, component, wr_statistic="pooled")
    thin = win_rate_fold_row("2021", baseline, component[:-1], wr_statistic="pooled")
    assert gate_win_rate({"folds": [passing] * 3}) == "PASS"
    assert thin["n"] == 29 and gate_win_rate({"folds": [thin] * 3}) == "FAIL"


def test_an_unknown_statistic_is_refused():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(ValueError):
        win_rate_fold_row("2021", baseline, component, wr_statistic="mixed")
```

- [ ] **Step 3: Write the failing CLI tests** — `tests/backtesting/test_validate_component_pooled.py`

```python
"""v180: validate_component.py --wr-statistic pooled (A1 clause 1 and fold rows) and
--train-effect-from-arms (A3: the TRAIN effect is the A1 point on the same arms)."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from tests.backtesting.test_acceptance_pooled_wr import _arms  # noqa: E402

BESPOKE = ["--bespoke-instrument", "v180 unit fixture"]
MDE_ARGS = ["--title", "t", "--window", "w", "--resamples", "200",
            "--observed-days", "365", "--target-days", "730"]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot import config
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def _run(*args):
    return vc.main([*args, *BESPOKE])


def _write_arms(tmp_path, baseline, component):
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def _write_folds(tmp_path, lift):
    folds = []
    for year in ("2021", "2022", "2023"):
        baseline, component = _arms(n_tickers=5, lift=lift)
        folds.append({"test_year": year, "baseline": [asdict(t) for t in baseline],
                      "component": [asdict(t) for t in component]})
    path = tmp_path / "folds.json"
    path.write_text(json.dumps({"folds": folds}), encoding="utf-8")
    return path


def test_pooled_walkforward_passes_an_additive_arm(tmp_path):
    out = tmp_path / "wf.json"
    rc = _run("--stage", "walkforward", "--wr-statistic", "pooled", "--arms",
              str(_write_folds(tmp_path, lift=4)), "--title", "t", "--window", "w",
              "--out-json", str(out))
    assert rc == 0
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["verdict"] == "PASS"
    assert all(row["wr_statistic"] == "pooled" and row["n"] == 50 for row in blob["folds"])


def test_the_standardised_walkforward_cannot_see_the_same_arm(tmp_path):
    assert _run("--stage", "walkforward", "--arms", str(_write_folds(tmp_path, lift=4)),
                "--title", "t", "--window", "w") == 1


def test_pooled_validation_scores_clause_one_on_the_pooled_statistic(tmp_path):
    out = tmp_path / "gate.json"
    rc = _run("--stage", "validation", "--wr-statistic", "pooled",
              "--arms", str(_write_arms(tmp_path, *_arms())), "--title", "t", "--window", "w",
              "--permutation-p", "0.01", "--resamples", "200", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 0 and blob["verdict"] == "PASS" and blob["wr_statistic"] == "pooled"
    clause = next(c for c in blob["clauses"] if c["name"] == "win_rate")
    assert clause["verdict"] == "PASS" and clause["detail"].startswith("pooled dWR")


def test_train_effect_from_arms_resolves_a_real_effect(tmp_path, capsys):
    rc = _run("--stage", "mde", "--wr-statistic", "pooled", "--train-effect-from-arms",
              "--arms", str(_write_arms(tmp_path, *_arms(lift=4))), *MDE_ARGS)
    out = capsys.readouterr().out
    assert "train effect (pooled, from --arms): +20.0000pp" in out
    assert rc == 0 and "RESOLVABLE" in out


def test_train_effect_from_arms_refuses_no_effect(tmp_path, capsys):
    rc = _run("--stage", "mde", "--wr-statistic", "pooled", "--train-effect-from-arms",
              "--arms", str(_write_arms(tmp_path, *_arms(lift=0))), *MDE_ARGS)
    out = capsys.readouterr().out
    assert "+0.0000pp" in out
    assert rc == 1 and "REFUSED" in out


def test_pooled_is_refused_with_the_harvest_gate(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run("--stage", "walkforward", "--gate", "harvest", "--wr-statistic", "pooled",
             "--arms", str(_write_folds(tmp_path, lift=4)), "--title", "t", "--window", "w")
    assert exc.value.code == 2
```

- [ ] **Step 4: Run the new tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_pooled_wr.py`
Expected: collection error, `ImportError: cannot import name 'WR_STATISTICS'`. The other two files fail the same way on import.

- [ ] **Step 5: Implement the statistic and its selection** — `swingbot/core/backtesting/acceptance.py`

- After `delta_expectancy_r`: `delta_pooled_win_rate(baseline, component) -> float | None` with the same None guards as `delta_expectancy_r`, over `win_rate`. Docstring cites "v180 A1 (v119 amendment A1): pooled, unstandardised dWR over decided trades; the only win-rate statistic that sees a strategy the baseline lacks". Then `WR_STATISTICS` and `win_rate_statistic(name)`, which raises `ValueError(f"wr_statistic must be one of {sorted(WR_STATISTICS)}, got {name!r}")`.
- `AcceptanceResult`: add `wr_statistic: str = "standardised"` after `cluster` (a default, so `acceptance_harvest` and `validate_component._write_skeleton` keep constructing it unchanged).
- `_clause_win_rate(baseline, component, n_resamples, seed, cluster="ticker", wr_statistic="standardised")`: bootstrap `win_rate_statistic(wr_statistic)` instead of the hard-coded `delta_standardised_win_rate`; the detail string's leading word becomes `f"{wr_statistic} dWR ..."`, so the standardised detail stays byte-identical.
- `evaluate(..., wr_statistic="standardised")`: call `win_rate_statistic(wr_statistic)` right after `_check_cluster(cluster)` (refuses before any work), pass `wr_statistic` to `_clause_win_rate`, and to the `AcceptanceResult`.
- `render_json`: after the `cluster` line, `if result.wr_statistic != "standardised": out["wr_statistic"] = result.wr_statistic` (comment: "v180: standardised output stays key-for-key identical").

No threshold, constant or other clause changes.

- [ ] **Step 6: Implement the fold row** — `swingbot/core/backtesting/backtest_wf.py`

Import `DECIDED, population_split, win_rate_statistic` from `swingbot.core.backtesting.acceptance` (top of module; `acceptance` imports only numpy, so there is no cycle). After `gate_win_rate`, add `win_rate_fold_row(test_year, baseline, component, *, wr_statistic="standardised") -> dict` per the Interfaces block: resolve the statistic first (unknown → `ValueError`); `"standardised"` returns exactly today's three-key row; anything else returns the four-key row whose `n` counts decided trades in `population_split(baseline, component)["added"]`. Docstring: "v180 A1: per-fold N of an additive arm counts its own decided trades, never the pooled book (spec § The funnel, stage 2)". `gate_win_rate` itself is not touched.

- [ ] **Step 7: Wire the CLI** — `scripts/backtest/validate_component.py`

- Imports: add `WR_STATISTICS, win_rate_statistic` to the `acceptance` import line and `win_rate_fold_row` to the `backtest_wf` import line. Drop `delta_standardised_win_rate` from the import only if nothing references it any more.
- `_mde_design`: `statistic = delta_expectancy_r if harvest else win_rate_statistic(args.wr_statistic)`.
- New helper `_claimed_effect(args, baseline, component, harvest) -> float | None`: without `--train-effect-from-arms` it returns `args.train_effect_r if harvest else args.train_effect_pp` (today's behaviour). With it, it computes the gate's statistic (`delta_expectancy_r` for harvest, else `win_rate_statistic(args.wr_statistic)`) on the `--arms` pair and prints, for the win-rate gate, `f"train effect ({args.wr_statistic}, from --arms): {value:+.4f}pp"` (`n/a` when None; for harvest the label is `dExpR` and the unit `R`).
- `stage_mde`: `claimed = _claimed_effect(args, baseline, component, harvest)`; refuse when `mde is None or claimed is None or claimed < mde`.
- `_fold_row(fold, harvest, wr_statistic="standardised")`: the win-rate branch returns `win_rate_fold_row(fold["test_year"], b, c, wr_statistic=wr_statistic)`; the harvest branch is unchanged. `stage_walkforward` passes `args.wr_statistic`.
- `_evaluate`: the win-rate branch calls `evaluate(baseline, component, wr_statistic=args.wr_statistic, **common)`.
- `main`: `parser.add_argument("--wr-statistic", choices=tuple(WR_STATISTICS), default="standardised")` and `parser.add_argument("--train-effect-from-arms", action="store_true")`. After the existing `--gate harvest` checks: `if args.wr_statistic != "standardised" and args.gate == "harvest": parser.error("--wr-statistic selects the v72 win-rate clause-1 statistic; the v92 harvest gate has no win-rate clause")`.

- [ ] **Step 8: Run the new tests to verify they pass**

Run, one at a time:
- `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_pooled_wr.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_wf_pooled_fold_row.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_pooled.py`

Expected: each `0 failed`.

- [ ] **Step 9: Run the existing gate tests unmodified**

Run, one at a time: `tests/backtesting/test_acceptance_gate.py`, `tests/backtesting/test_acceptance_render.py`, `tests/backtesting/test_acceptance_harvest.py`, `tests/backtesting/test_wf_gate_winrate.py`, `tests/backtesting/test_validate_component_cli.py`, `tests/backtesting/test_validate_component_v128.py`, `tests/backtesting/test_validate_component_stamps.py`, `tests/backtesting/test_validate_component_selection.py`, `tests/backtesting/arms/test_mde_paired.py` — each via `python scripts/dev/testrun.py file <path>`.
Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` exits 0 (`stage_mde` and `main` stay below 15).

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/backtest_wf.py scripts/backtest/validate_component.py tests/backtesting/test_acceptance_pooled_wr.py tests/backtesting/test_wf_pooled_fold_row.py tests/backtesting/test_validate_component_pooled.py
git commit -m "feat(v180): A1/A3 -- pooled dWR selectable in the acceptance gate, fold rows and validate_component" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V180-3: A2 — circular-shift replay permutation on the A1 statistic

**Model:** opus — a null distribution for the one-shot VALIDATION clause 5: the draw, the replay fidelity check and the process-global `ENTRY_SHIFT` restore must all be exact, or the p-value is meaningless.

**Files:**
- Create: `swingbot/core/backtesting/arms/shift_permutation.py`
- Create: `tests/backtesting/arms/test_shift_permutation.py`
- Create: `tests/backtesting/test_permutation_shift_replay.py`
- Modify: `scripts/backtest/permutation_test.py` (`_arms_main` l.173 — extract its stamp gate; `_parser` l.200; `main` l.~232; new `_shift_replay_main` and helpers)

**Interfaces:**
- Consumes: V180-2 `acceptance.win_rate_statistic(name)`, `delta_pooled_win_rate`, `WR_STATISTICS`; `acceptance.population_split`; `arms.knobs.apply_knobs(delta)`; `arms.strategy_engine.StrategyEngine(strategies=..., instrument=...)` and its `run_ticker(ticker, df, horizons, signal_window, params) -> list[ArmTrade]` (which rolls entries by `bt.ENTRY_SHIFT` in `iter_trades`, l.236); `scan_params.ScanParams.from_config()`; `scripts.backtest.measure_arms.load_frame(ticker)`; the existing `permutation_test._load_arm_pair`, `_stamp_refusal`; test helpers `_arms`, `_trade` from V180-2.
- Produces (the index's Contracts, verbatim):
  - `shift_permutation.SHIFT_RANGE = (20, 200)`; `class NotAdditive(ValueError)`; `class ReplayMismatch(ValueError)`.
  - `additive_added(baseline, component) -> list[ArmTrade]` — raises `NotAdditive` when the component removes or changes any baseline row.
  - `shift_permutation(baseline, component, replay_added: Callable[[int], list], statistic, *, n_perm: int = 200, seed: int = 42, verify_zero: bool = True, progress: Callable[[int, int], None] | None = None) -> dict` with keys `{"observed", "p_value", "n", "n_valid", "seed", "shift_range", "added", "statistic"}`.
  - `strategy_shift_replay(frames: dict, strategy: str, horizons, window: tuple[str, str], delta: dict, *, instrument=None) -> Callable[[int], list]`.
  - CLI: `permutation_test.py --arms FILE --shift-replay [--wr-statistic pooled] [--n 200 --seed 42 --out-json F --data-source alpaca]`.
- Contract the V180-7 engine change must keep (it is how the replay reproduces the component's rows): `StrategyEngine(strategies=(TURTLE_SOUP,))` under the knob runs Turtle Soup exactly once (the compression precedent: `_run_strategies` returns `self.strategies` when the strategy is already in it), and Turtle Soup's one-open-position slot is per `(ticker, strategy, horizon)` cell, so replaying it alone yields the same rows as the full component run. `verify_zero` turns any break of this into a loud `ReplayMismatch`.

- [ ] **Step 1: Write the failing module tests** — `tests/backtesting/arms/test_shift_permutation.py`

```python
"""v180 A2 (v119 amendment A2): the circular entry-shift null for an ADDITIVE arm.
permutation_test.arm_pair_permutation's removal-label null cannot model an arm that removes
nothing (its null equals the component for every shift, so p == 1.0). This replays only the
added strategy with bt.ENTRY_SHIFT rolled and keeps the real baseline fixed."""
import dataclasses
import runpy
from pathlib import Path

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import ArmTrade, delta_pooled_win_rate
from swingbot.core.backtesting.arms import shift_permutation as sp
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade

ROOT = Path(__file__).resolve().parents[3]
KEYS = {"observed", "p_value", "n", "n_valid", "seed", "shift_range", "added", "statistic"}


def _added(baseline, component):
    keys = {t.key for t in baseline}
    return [t for t in component if t.key not in keys]


def _no_edge_replay(added, calls=None):
    """Shift 0 reproduces the observed added rows; any other shift redraws their outcomes at
    the baseline's 40% win rate -- a trigger with no edge."""
    def replay(shift):
        if calls is not None:
            calls.append(shift)
        if shift == 0:
            return list(added)
        rng = np.random.default_rng(shift)
        return [dataclasses.replace(t, outcome="win" if rng.random() < 0.4 else "loss")
                for t in added]
    return replay


def test_additive_added_returns_the_added_rows():
    baseline, component = _arms(n_tickers=5)
    assert sp.additive_added(baseline, component) == component[50:]


def test_a_removal_or_a_changed_outcome_is_not_additive():
    baseline, component = _arms(n_tickers=5)
    with pytest.raises(sp.NotAdditive):
        sp.additive_added(baseline, component[1:])
    flipped = [dataclasses.replace(component[0], outcome="loss")] + component[1:]
    assert component[0].outcome == "win"
    with pytest.raises(sp.NotAdditive):
        sp.additive_added(baseline, flipped)


def test_a_real_effect_beats_the_shifted_null():
    baseline, component = _arms()
    out = sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component)),
                               delta_pooled_win_rate, n_perm=200, seed=42)
    assert set(out) == KEYS
    assert out["observed"] == pytest.approx(20.0) and out["p_value"] < 0.05
    assert (out["n"], out["n_valid"], out["seed"], out["added"]) == (200, 200, 42, 400)
    assert out["shift_range"] == [20, 200] and out["statistic"] == "delta_pooled_win_rate"


def test_a_trigger_with_no_edge_is_indistinguishable():
    baseline, component = _arms()
    added = _added(baseline, component)
    out = sp.shift_permutation(baseline, component, lambda shift: list(added),
                               delta_pooled_win_rate, n_perm=50)
    assert out["p_value"] == 1.0


def test_the_shift_draw_is_the_permutation_scripts():
    baseline, component = _arms(n_tickers=5)
    calls = []
    sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component), calls),
                         delta_pooled_win_rate, n_perm=50, seed=42)
    assert calls[0] == 0
    assert calls[1:] == [int(s) for s in np.random.default_rng(42).integers(20, 200, size=50)]
    script = runpy.run_path(str(ROOT / "scripts" / "backtest" / "permutation_test.py"))
    assert sp.SHIFT_RANGE == script["SHIFT_RANGE"]


def test_verify_zero_catches_a_replay_that_does_not_reproduce_the_arm():
    baseline, component = _arms(n_tickers=5)
    added = _added(baseline, component)
    broken = lambda shift: added[:-1] if shift == 0 else list(added)   # noqa: E731
    with pytest.raises(sp.ReplayMismatch):
        sp.shift_permutation(baseline, component, broken, delta_pooled_win_rate, n_perm=5)
    calls = []
    sp.shift_permutation(baseline, component, _no_edge_replay(added, calls),
                         delta_pooled_win_rate, n_perm=5, verify_zero=False)
    assert 0 not in calls and len(calls) == 5


def test_a_non_additive_arm_is_refused_before_any_replay():
    baseline, component = _arms(n_tickers=5)

    def never(_shift):
        raise AssertionError("replayed a non-additive arm")
    with pytest.raises(sp.NotAdditive):
        sp.shift_permutation(baseline, component[1:], never, delta_pooled_win_rate, n_perm=5)


def test_progress_reports_every_shift():
    baseline, component = _arms(n_tickers=5)
    seen = []
    sp.shift_permutation(baseline, component, _no_edge_replay(_added(baseline, component)),
                         delta_pooled_win_rate, n_perm=10,
                         progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, 10) for i in range(1, 11)]


class _FakeEngine:
    seen: list = []
    fail = False

    def __init__(self, strategies=None, instrument=None, **_kwargs):
        self.strategies, self.instrument = strategies, instrument

    def run_ticker(self, ticker, df, horizons, signal_window, params):
        if _FakeEngine.fail:
            raise RuntimeError("engine blew up")
        _FakeEngine.seen.append((ticker, self.strategies, tuple(horizons), tuple(signal_window),
                                 bt.ENTRY_SHIFT, config.STALL_EXIT_ENABLED, type(params).__name__))
        return [_trade(ticker, "Turtle Soup", "2w", 0, "win"),               # 2022-01-01
                ArmTrade(ticker, "Turtle Soup", "2w", "2021-12-31", "win", 2.0, 2.0,
                         "strategy", "bullish")]


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(sp, "StrategyEngine", _FakeEngine)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False, raising=False)
    _FakeEngine.seen, _FakeEngine.fail = [], False
    return _FakeEngine


def test_replay_runs_one_strategy_shifted_under_the_knobs(fake_engine):
    window = ("2022-01-01", "2022-12-31")
    replay = sp.strategy_shift_replay({"B": None, "A": None}, "Turtle Soup", ["2w"], window,
                                      {"STALL_EXIT_ENABLED": True})
    rows = replay(37)
    assert [r.ticker for r in rows] == ["A", "B"]
    assert all(window[0] <= r.entry_date <= window[1] for r in rows)
    assert [s[:6] for s in fake_engine.seen] == [
        (t, ("Turtle Soup",), ("2w",), window, 37, True) for t in ("A", "B")]
    assert fake_engine.seen[0][6] == "ScanParams"
    assert bt.ENTRY_SHIFT == 0 and config.STALL_EXIT_ENABLED is False


def test_replay_restores_entry_shift_after_an_error(fake_engine):
    fake_engine.fail = True
    replay = sp.strategy_shift_replay({"A": None}, "Turtle Soup", ["2w"],
                                      ("2022-01-01", "2022-12-31"), {"STALL_EXIT_ENABLED": True})
    with pytest.raises(RuntimeError):
        replay(55)
    assert bt.ENTRY_SHIFT == 0 and config.STALL_EXIT_ENABLED is False


def test_shift_zero_reproduces_the_real_engine():
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.scan_params import ScanParams
    from tests.backtesting.screen.helpers import random_walk

    frames = {"RW": random_walk(700, seed=3, start="2019-01-02")}
    window = ("2020-01-01", "2021-06-30")
    expected = StrategyEngine(strategies=("RSI",)).run_ticker(
        "RW", frames["RW"], ("4w",), window, ScanParams.from_config())
    rows = sp.strategy_shift_replay(frames, "RSI", ("4w",), window, {})(0)
    assert rows == [t for t in expected if window[0] <= t.entry_date <= window[1]]
```

- [ ] **Step 2: Write the failing CLI tests** — `tests/backtesting/test_permutation_shift_replay.py`

```python
"""v180 A2 CLI: permutation_test.py --arms F --shift-replay --wr-statistic pooled."""
import contextlib
import dataclasses
import io
import json
import runpy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.test_acceptance_pooled_wr import _arms, _trade

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "backtest" / "permutation_test.py"
UNIVERSE = [f"T{n}" for n in range(40)]
ARGV = ["--shift-replay", "--wr-statistic", "pooled", "--n", "50", "--data-source", "yfinance"]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot import config
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def _write(tmp_path, baseline, component, stamped=True):
    blob = {"baseline": [asdict(t) for t in baseline],
            "component": [asdict(t) for t in component]}
    if stamped:
        blob["provenance"] = build_stamp(
            stage="validation", signal_window=STAGES["validation"].signal_window,
            universe=UNIVERSE, horizons=ALL_HORIZONS, engines=("confluence", "strategy"),
            knob_delta={"TURTLE_SOUP_RESEARCH_MODE": "structural"},
            engine_hash_baseline="h", engine_hash_component="h",
            changed_outcomes=len(component) - len(baseline),
            preregistration="synthetic-v180-test")
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


def _added(baseline, component):
    keys = {t.key for t in baseline}
    return [t for t in component if t.key not in keys]


def _no_edge(added):
    def replay(shift):
        if shift == 0:
            return list(added)
        rng = np.random.default_rng(shift)
        return [dataclasses.replace(t, outcome="win" if rng.random() < 0.4 else "loss")
                for t in added]
    return replay


def _run(argv, replay, seen=None):
    main = runpy.run_path(str(SCRIPT))["main"]
    main.__globals__["_full_universe"] = lambda: UNIVERSE
    main.__globals__["_replay_frames"] = lambda universe: {t: None for t in universe}

    def factory(frames, strategy, stamp):
        if seen is not None:
            seen.append((sorted(frames), strategy, stamp["knob_delta"]))
        return replay
    main.__globals__["_shift_replay_for"] = factory
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()


def test_a_real_effect_is_real(tmp_path):
    baseline, component = _arms()
    seen = []
    code, out = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV],
                     _no_edge(_added(baseline, component)), seen)
    blob = json.loads(out)
    assert code == 0 and blob["verdict"] == "REAL" and blob["p_value"] < 0.05
    assert (blob["n"], blob["added"], blob["wr_statistic"], blob["strategy"]) == (
        50, 400, "pooled", "Turtle Soup")
    assert seen == [(sorted(UNIVERSE), "Turtle Soup", {"TURTLE_SOUP_RESEARCH_MODE": "structural"})]


def test_out_json_matches_stdout(tmp_path):
    baseline, component = _arms(n_tickers=5)
    target = tmp_path / "perm.json"
    code, out = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV,
                      "--out-json", str(target)], _no_edge(_added(baseline, component)))
    assert code == 0 and json.loads(target.read_text(encoding="utf-8")) == json.loads(out)


def test_a_non_additive_arm_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component[1:])), *ARGV],
                   _no_edge([]))
    assert code == 1 and "refused:not-additive" in capsys.readouterr().err


def test_two_added_strategies_are_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    component = component + [_trade("T0", "Fibonacci Limit", "2w", 70, "win")]
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV], _no_edge([]))
    assert code == 1 and "refused:not-single-strategy" in capsys.readouterr().err


def test_a_replay_that_misses_the_observed_rows_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component)), *ARGV],
                   lambda shift: [])
    assert code == 1 and "refused:replay-mismatch" in capsys.readouterr().err


def test_an_unstamped_arm_is_refused(tmp_path, capsys):
    baseline, component = _arms(n_tickers=5)
    code, _ = _run(["--arms", str(_write(tmp_path, baseline, component, stamped=False)), *ARGV],
                   _no_edge(_added(baseline, component)))
    assert code == 1 and "refused:unstamped" in capsys.readouterr().err


def test_shift_replay_needs_arms():
    with pytest.raises(SystemExit) as exc:
        _run(ARGV, _no_edge([]))
    assert exc.value.code == 2
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_shift_permutation.py`
Expected: collection error, `ImportError: cannot import name 'shift_permutation' from 'swingbot.core.backtesting.arms'`.
Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_shift_replay.py`
Expected: FAIL — argparse rejects `--shift-replay` (`SystemExit: 2`) in every test but the last.

- [ ] **Step 4: Implement the module** — `swingbot/core/backtesting/arms/shift_permutation.py`

Module docstring: v180 A2 (the v119 amendment A2, adopted verbatim): `permutation_test.py`'s circular entry shift, n = 200, seed 42, scored with the A1 statistic; why the removal-label null cannot see an additive arm; that the null replays only the added strategy with `bt.ENTRY_SHIFT` rolled and keeps the real baseline fixed; and that `bt.ENTRY_SHIFT` and the knob deltas are process-global, so this is for offline scripts only.

Imports: `numpy as np`; `from swingbot.core.backtesting import backtest as bt`; `from swingbot.core.backtesting.acceptance import population_split`; `from swingbot.core.backtesting.arms.knobs import apply_knobs`; `from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine` (module-level, so tests can monkeypatch `sp.StrategyEngine`).

`additive_added`: `population_split(baseline, component)`; raise `NotAdditive(f"{len(removed)} removed, {len(changed)} changed")` when either is non-empty; return `split["added"]`.

The draw and the verification order are fixed by the tests; the body is:

```python
def shift_permutation(baseline, component, replay_added, statistic, *, n_perm=200, seed=42,
                      verify_zero=True, progress=None) -> dict:
    added = additive_added(baseline, component)
    if verify_zero:
        replayed = {trade.key for trade in replay_added(0)}
        if replayed != {trade.key for trade in added}:
            raise ReplayMismatch(f"shift 0 replayed {len(replayed)} rows, the arm added {len(added)}")
    observed = statistic(baseline, component)
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = []
    for done, shift in enumerate(shifts, start=1):
        null.append(statistic(baseline, list(baseline) + list(replay_added(int(shift)))))
        if progress is not None:
            progress(done, int(n_perm))
    valid = [value for value in null if value is not None]
    p = None if observed is None or not valid else float(np.mean([v >= observed for v in valid]))
    return {"observed": observed, "p_value": p, "n": int(n_perm), "n_valid": len(valid),
            "seed": seed, "shift_range": list(SHIFT_RANGE), "added": len(added),
            "statistic": getattr(statistic, "__name__", str(statistic))}
```

`strategy_shift_replay` returns a closure `replay(shift) -> list[ArmTrade]`: set `bt.ENTRY_SHIFT = int(shift)`, then inside `with apply_knobs(delta):` build `ScanParams.from_config()` and one `StrategyEngine(strategies=(strategy,), instrument=instrument)`, and extend rows with `engine.run_ticker(ticker, frames[ticker], tuple(horizons), tuple(window), params)` for `ticker in sorted(frames)`; reset `bt.ENTRY_SHIFT = 0` in a `finally`; return the rows with `window[0] <= entry_date <= window[1]` (the producer's `_rows` filter).

- [ ] **Step 5: Wire the CLI** — `scripts/backtest/permutation_test.py`

- Extract `_stamp_gate_refused(blob, baseline, component) -> bool` from `_arms_main`: the `OperationalError` → `refused:universe-unavailable` message and the `refusal` message, both on stderr, unchanged. `_arms_main` calls it; its output stays byte-identical.
- `_parser`: add `--shift-replay` (`store_true`), `--wr-statistic` (choices `tuple(WR_STATISTICS)` from `swingbot.core.backtesting.acceptance`, default `"standardised"`), `--out-json` (default None) and `--data-source` (`choices=training_data.DATA_SOURCES`, default None, from `swingbot.core.marketdata.training_data`, so the fold path does not import yfinance).
- `main`: right after `require_v1`: `if args.shift_replay:` → `_parser().error("--shift-replay needs --arms")` when `args.arms` is None, else `return _shift_replay_main(args)`.
- Module-level seams the tests patch:
  - `_replay_frames(universe) -> dict` — `{t: f for t in universe if (f := load_frame(t)) is not None}` with `from scripts.backtest.measure_arms import load_frame`; prints `loaded N/M frames` to stderr.
  - `_shift_replay_for(frames, strategy, stamp)` — `strategy_shift_replay(frames, strategy, stamp["horizons"], tuple(stamp["signal_window"]), stamp.get("knob_delta") or {})`, lazily imported.
  - `_select_source(args)` — `training_data.select(args.data_source)` and the `training data: <source> (<k> excluded)` line on **stderr**, so stdout stays one JSON document.
- `_shift_replay_main(args) -> int`, in order: `_load_arm_pair` (None → 1); `_stamp_gate_refused` (→ 1); `additive_added` (`NotAdditive` → stderr `refused:not-additive -- <detail>. Budget intact.`, 1); the added rows must carry exactly one strategy (else stderr `refused:not-single-strategy -- added rows carry <sorted names>. Budget intact.`, 1); `_select_source(args)`; `frames = _replay_frames(stamp["universe"])`; `replay = _shift_replay_for(frames, strategy, stamp)`; `shift_permutation(baseline, component, replay, win_rate_statistic(args.wr_statistic), n_perm=args.n, seed=args.seed, progress=_print_progress)` (`ReplayMismatch` → stderr `refused:replay-mismatch -- <detail>. Budget intact.`, 1). Then add `strategy`, `wr_statistic`, `instrument` (`"v180 A2: circular entry-shift replay of the added strategy, real baseline fixed"`) and `verdict` (`"REAL"` when `p_value` is not None and `< 0.05`, else `"INDISTINGUISHABLE FROM LUCK"`), print `json.dumps(out, indent=1)` to stdout, write the same JSON to `--out-json` when given, return 0. Split it into a `_shift_inputs(args)` helper if it nears complexity 10.
- `_print_progress(done, total)`: stderr `shift replay {done}/{total} ({done / total * 100:.0f}%)`, flushed (long-run rule: a run over 15 min prints a percent).

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_shift_permutation.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_shift_replay.py`
Expected: each `0 failed`.

- [ ] **Step 7: Run the existing permutation tests unmodified** (the fold-path witness pins the old output byte for byte)

Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_permutation.py`
Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/arms/shift_permutation.py scripts/backtest/permutation_test.py tests/backtesting/arms/test_shift_permutation.py tests/backtesting/test_permutation_shift_replay.py
git commit -m "feat(v180): A2 -- circular entry-shift replay permutation for additive arms" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task V180-4: Structural plan — drop scope, plan shape, Turtle Soup branch

**Model:** opus — the stop scope decides drop-versus-squeeze for every long, the target must never take the synthetic cap fallback, and the change touches `build_strategy_plan`'s dispatch, which has no complexity headroom (cc 14).

**Files:**
- Create: `swingbot/core/planning/turtle_soup_plan.py`
- Create: `tests/planning/test_turtle_soup_plan.py`
- Modify: `swingbot/core/market/strategy_types.py` (`STRUCTURAL_DROP_STRATEGIES` directly after `SHORT_STRATEGIES`, l.27)
- Modify: `swingbot/core/planning/stop_scope.py` (import and `_ALWAYS_IN_SCOPE`, l.4-9)
- Modify: `swingbot/core/planning/params.py` (import l.8; `EXIT_V2_PARAMS` entry after `FIB_LIMIT`'s; `PLAN_SHAPES` entry after `FIB_LIMIT`'s)
- Modify: `swingbot/core/planning/builders.py` (import l.13-14; `_turtle_soup_branch` after `_short_branch`; `_STRUCTURAL_BRANCHES[TURTLE_SOUP]` after the `FIB_LIMIT` registration, l.~299; `_LIFECYCLE_EXEMPT` and `_lifecycle_pair`, l.~384)
- Modify: `tests/planning/test_strategy_branch_table.py` (the exact-set pin of `_STRUCTURAL_BRANCHES` gains `TURTLE_SOUP`, as it gained `"Fibonacci Limit"` in v131. This is the only existing test edited, because it pins the key set by design.)

**Interfaces:**
- Consumes: `strategy_types.TURTLE_SOUP` (V180-1); `builders._bounded_stop(entry, stop_loss, is_bull, strategy, direction, horizon_key)`, `builders._BranchInputs`, `builders.apply_level_lifecycle`, `builders.plan_shape_for`; `params.STRUCTURE_BUFFER_ATR` (0.25); `targets.select_structural_target`, `targets._safe_atr_value`; `levels.build_level_map(df, h, current_price)` → `(supports, resistances)` of `Level(price, sources)`; `indicators.atr(df, 14)`; `ScanParams.from_config()` (`min_risk_reward_ratio`, `max_risk_reward_ratio`); `stop_scope.in_scope`, `stop_ceiling`, `plan_stop_ceiling`, `risk_sizing_ok`, `CAP`, `DROP`.
- Produces:
  - `strategy_types.STRUCTURAL_DROP_STRATEGIES: tuple[str, ...] = (TURTLE_SOUP,)`. `stop_scope._ALWAYS_IN_SCOPE` covers `SHORT_STRATEGIES + STRUCTURAL_DROP_STRATEGIES`, so `stop_ceiling(TURTLE_SOUP, "bullish", "2w") == (3.0, DROP)` and `plan_stop_ceiling(<Turtle Soup strategy plan>) == 3.0` (V180-5 reads this at the fill).
  - `params.EXIT_V2_PARAMS[TURTLE_SOUP] = {"trail_atr_mult": 2.5, "tp2": False}`; `params.PLAN_SHAPES[TURTLE_SOUP] = {"entry_type": "market", "expiry_bars": 1, "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0, "hold_cap_bars": 10}`.
  - `swingbot/core/planning/turtle_soup_plan.py`: `RISK_CAP = "risk_cap"`, `NO_LEVEL_IN_BAND = "no_level_in_band"`, `PLAN_OTHER = "plan_other"`; frozen dataclass `TurtleSoupLevels(stop: float | None, tp1: float | None, candidates: tuple[float, ...], reason: str | None)`; `in_band(entry, stop, prices, min_rr, max_rr) -> list[float]` (nearest first); `turtle_soup_levels(df, index, horizon_key, *, entry, atr_val, level_map=None, scan_params=None) -> TurtleSoupLevels`; `turtle_soup_branch(inputs) -> tuple | None` (`(stop, tp1, list(candidates), None)`); `turtle_soup_rejection_reason(df, index, horizon_key, scan_params=None, level_map=None) -> str` (V180-7/V180-8 consume this for the `plan_none` drop shares).
  - `builders._turtle_soup_branch` (lazy wrapper), `builders._STRUCTURAL_BRANCHES[TURTLE_SOUP]`, `builders._LIFECYCLE_EXEMPT = frozenset({COMPRESSION_SHORT, TURTLE_SOUP})`.

Run every step from the worktree `.claude/worktrees/2026-10-21-v180-turtle-soup-entry`. First check that V180-1 has landed: `git grep -n "^TURTLE_SOUP = " swingbot/core/market/strategy_types.py` must print one line. If it prints nothing, stop.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_turtle_soup_plan.py`

```python
"""V180-4: Turtle Soup plan -- DROP scope, single market leg, stop Low[t] - 0.25 x ATR14 via
_bounded_stop, target = nearest resistance INSIDE the R band (no synthetic cap), no lifecycle."""
import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import (COMPRESSION_SHORT, HORIZONS, SHORT_STRATEGIES,
                                                  STRUCTURAL_DROP_STRATEGIES, TURTLE_SOUP)
from swingbot.core.planning import builders
from swingbot.core.planning import turtle_soup_plan as tsp
from swingbot.core.planning.params import EXIT_V2_PARAMS, PLAN_SHAPES, STRUCTURE_BUFFER_ATR
from swingbot.core.planning.stop_scope import (CAP, DROP, in_scope, plan_stop_ceiling,
                                               risk_sizing_ok, stop_ceiling)
from swingbot.core.planning.targets import select_structural_target

HZ = "2w"
T = 50          # the sweep bar


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)


def _frame(sweep_low=98.5, n=60):
    """Flat 100 closes, lows 99.5; bar 40 sets the 20-bar low 99.0 (age 10 at T); bar T
    sweeps it to `sweep_low` and closes back at 100 -- a live Turtle Soup bar."""
    idx = pd.bdate_range("2024-01-02", periods=n)
    close = np.full(n, 100.0)
    low = np.full(n, 99.5)
    low[40] = 99.0
    low[T] = sweep_low
    return pd.DataFrame({"Open": close, "High": close + 0.5, "Low": low, "Close": close,
                         "Volume": np.full(n, 1e6)}, index=idx)


def _map(*prices):
    return [], [Level(price=p, sources=["Swing high", "Pivot high"]) for p in prices]


def _real_stop_and_target(df, r=2.0):
    """The stop build_strategy_plan will compute (its own ATR14) and a level r R above 100."""
    stop = 98.5 - STRUCTURE_BUFFER_ATR * float(atr(df, 14).iloc[T])
    return stop, 100.0 + r * (100.0 - stop)


def _built(df, level_map, direction="bullish"):
    return builders.build_strategy_plan(df, T, ticker="TS", strategy=TURTLE_SOUP, horizon_key=HZ,
                                        direction=direction, level_map=level_map)


def test_turtle_soup_is_a_long_that_is_always_dropped_never_capped():
    assert STRUCTURAL_DROP_STRATEGIES == (TURTLE_SOUP,)
    assert TURTLE_SOUP not in SHORT_STRATEGIES
    assert in_scope(TURTLE_SOUP, "bullish", raw="")
    assert stop_ceiling(TURTLE_SOUP, "bullish", HZ, raw="") == (3.0, DROP)
    assert stop_ceiling("RSI", "bullish", HZ, raw="")[1] == CAP          # unchanged for other longs
    assert stop_ceiling("Bull Trap", "bearish", HZ, raw="") == (3.0, DROP)  # unchanged for shorts


def test_the_fill_reads_the_three_percent_drop_ceiling_and_sizing_caps_dollar_risk():
    plan = SimpleNamespace(source="strategy", strategy=TURTLE_SOUP, direction="bullish",
                           horizon_key=HZ, stop_ceiling_pct=None, trigger_price=100.0,
                           stop_loss=97.5)
    assert plan_stop_ceiling(plan) == 3.0
    budget = {"mode": "risk_pct", "balance": 10_000.0, "risk_pct": 2.0}
    assert risk_sizing_ok(plan, lambda e, s: {**budget, "shares": 80})       # 80 x 2.5 = 200 = 2%
    assert not risk_sizing_ok(plan, lambda e, s: {**budget, "shares": 81})


def test_plan_shape_is_one_market_leg_with_a_ten_session_cap():
    assert PLAN_SHAPES[TURTLE_SOUP] == {"entry_type": "market", "expiry_bars": 1,
                                        "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0,
                                        "hold_cap_bars": 10}
    shape = builders.plan_shape_for(TURTLE_SOUP)
    assert (shape["entry_type"], shape["tp1_fraction"], shape["hold_cap_bars"]) == ("market", 1.0, 10)
    assert EXIT_V2_PARAMS[TURTLE_SOUP] == {"trail_atr_mult": 2.5, "tp2": False}
    assert HORIZONS[HZ]["max_holding_days"] >= PLAN_SHAPES[TURTLE_SOUP]["hold_cap_bars"] == 10


def test_in_band_keeps_levels_between_floor_and_cap_nearest_first():
    prices = [106.0, 105.0, 103.0, 101.0, 99.0, 104.0, 105.01, 102.99]
    assert tsp.in_band(100.0, 98.0, prices, 1.5, 2.5) == [103.0, 104.0, 105.0]
    assert tsp.in_band(100.0, 100.0, [103.0], 1.5, 2.5) == []


def test_stop_is_the_buffered_sweep_low_and_the_target_the_nearest_level_in_band():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=1.0,
                                 level_map=_map(102.0, 103.0, 104.0, 110.0))
    assert out.stop == pytest.approx(98.25)              # 98.5 - 0.25 x 1.0; risk 1.75
    assert out.candidates == (103.0, 104.0)              # band [102.625, 104.375]
    assert (out.tp1, out.reason) == (103.0, None)


def test_a_stop_beyond_three_percent_is_dropped_never_squeezed():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=8.0, level_map=_map(105.0))
    # 98.5 - 2.0 = 96.5: 3.5% from the close, beyond the 2w DROP ceiling of 3.0%
    assert (out.stop, out.tp1, out.candidates, out.reason) == (None, None, (), tsp.RISK_CAP)


def test_no_level_in_band_is_no_plan_never_the_synthetic_cap_target():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=1.0,
                                 level_map=_map(110.0, 101.0))
    assert (out.tp1, out.candidates, out.reason) == (None, (), tsp.NO_LEVEL_IN_BAND)
    assert out.stop == pytest.approx(98.25)
    # Unfiltered, the selector would price a synthetic entry + 2.5R target here.
    assert select_structural_target(100.0, 98.25, True, [110.0, 101.0], 1.5, 2.5) == pytest.approx(104.375)


def test_a_stop_at_or_above_the_entry_is_plan_other():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=98.0, atr_val=0.0, level_map=_map(103.0))
    assert (out.stop, out.reason) == (None, tsp.PLAN_OTHER)


def test_a_missing_level_map_is_built_from_bars_up_to_the_signal(monkeypatch):
    seen = {}

    def fake(window, h, price, *args, **kwargs):
        seen.update(last=window.index[-1], price=price, h=h)
        return _map(103.0)

    monkeypatch.setattr(levels_mod, "build_level_map", fake)
    df = _frame()
    out = tsp.turtle_soup_levels(df, T, HZ, entry=100.0, atr_val=1.0)
    assert seen == {"last": df.index[T], "price": 100.0, "h": HORIZONS[HZ]}
    assert out.tp1 == 103.0


def test_reads_no_bar_after_the_signal():
    df = _frame()
    later = df.copy()
    later.iloc[T + 1:, later.columns.get_loc("High")] = 130.0
    later.iloc[T + 1:, later.columns.get_loc("Low")] = 60.0
    assert (tsp.turtle_soup_levels(df, T, HZ, entry=100.0, atr_val=1.0)
            == tsp.turtle_soup_levels(later, T, HZ, entry=100.0, atr_val=1.0))


def test_the_branch_is_bullish_only_and_returns_the_builder_tuple():
    inputs = builders._BranchInputs(_frame(), T, TURTLE_SOUP, HZ, "bullish", 100.0, 1.0,
                                    None, None, _map(103.0, 104.0))
    stop, tp1, candidates, applied = tsp.turtle_soup_branch(inputs)
    assert stop == pytest.approx(98.25)
    assert (tp1, candidates, applied) == (103.0, [103.0, 104.0], None)
    assert tsp.turtle_soup_branch(dataclasses.replace(inputs, direction="bearish")) is None
    assert builders._STRUCTURAL_BRANCHES[TURTLE_SOUP] is builders._turtle_soup_branch


def test_build_strategy_plan_makes_a_single_leg_market_plan():
    df = _frame()
    stop, target = _real_stop_and_target(df)
    plan = _built(df, _map(target))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(stop)
    assert plan.tp1 == pytest.approx(target)
    assert (plan.entry_type, plan.trigger_price, plan.entry_price) == ("market", 100.0, 100.0)
    assert (plan.tp1_fraction, plan.breakeven_trigger_fraction,
            plan.hold_cap_bars, plan.tp2) == (1.0, 1.0, 10, None)
    assert (plan.source, plan.strategy, plan.direction) == ("strategy", TURTLE_SOUP, "bullish")
    assert _built(df, _map(target), direction="bearish") is None
    assert _built(_frame(sweep_low=95.0), _map(110.0)) is None


def test_the_level_lifecycle_never_moves_a_turtle_soup_plan(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("level lifecycle ran for Turtle Soup")

    monkeypatch.setattr(builders, "apply_level_lifecycle", boom)
    df = _frame()
    _, target = _real_stop_and_target(df)
    assert _built(df, _map(target)) is not None
    assert builders._LIFECYCLE_EXEMPT == frozenset({COMPRESSION_SHORT, TURTLE_SOUP})


def test_rejection_reason_names_why_no_plan_was_built():
    assert tsp.turtle_soup_rejection_reason(_frame(sweep_low=95.0), T, HZ,
                                            level_map=_map(110.0)) == tsp.RISK_CAP
    assert tsp.turtle_soup_rejection_reason(_frame(), T, HZ,
                                            level_map=_map(130.0)) == tsp.NO_LEVEL_IN_BAND
    df = _frame()
    _, target = _real_stop_and_target(df)
    assert tsp.turtle_soup_rejection_reason(df, T, HZ, level_map=_map(target)) == tsp.PLAN_OTHER
```

Update the pin in `tests/planning/test_strategy_branch_table.py`: the import becomes `from swingbot.core.market.strategy_types import SHORT_STRATEGIES, TURTLE_SOUP`, and the set literal's line `"Fibonacci Limit",` becomes `"Fibonacci Limit", TURTLE_SOUP,`. Nothing else in that file changes.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_turtle_soup_plan.py`
Expected: collection error, `ImportError: cannot import name 'STRUCTURAL_DROP_STRATEGIES'`.
Run: `python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py`
Expected: `test_structural_strategies_have_their_own_branch` FAILS (`'Turtle Soup'` missing from the key set).

- [ ] **Step 3: Add the drop scope** — `swingbot/core/market/strategy_types.py` and `swingbot/core/planning/stop_scope.py`

In `strategy_types.py`, directly after `SHORT_STRATEGIES = V104_SHORTS + (FADE_STRATEGY, COMPRESSION_SHORT)`:

```python
# v180: long strategies whose structural stop is always in the v104 DROP scope -- a stop
# beyond the horizon's max_risk_pct drops the plan and is never squeezed to the 2% cap.
# Kept apart from SHORT_STRATEGIES, which also routes to _short_branch and short-only code.
STRUCTURAL_DROP_STRATEGIES: tuple[str, ...] = (TURTLE_SOUP,)
```

In `stop_scope.py`, replace the import and `_ALWAYS_IN_SCOPE`:

```python
from swingbot.core.market.strategy_types import (HORIZONS, SHORT_STRATEGIES,
                                                  STRUCTURAL_DROP_STRATEGIES)
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct

CAP = "cap"
DROP = "drop"
# Shorts (v104) and v180's structural-drop longs keep their stop or drop the plan,
# whatever STRUCTURAL_STOP_SCOPE says.
_ALWAYS_IN_SCOPE = frozenset(name.lower()
                             for name in SHORT_STRATEGIES + STRUCTURAL_DROP_STRATEGIES)
```

- [ ] **Step 4: Add the plan shape** — `swingbot/core/planning/params.py`

Import: `from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION, FIB_LIMIT, TURTLE_SOUP`.

In `EXIT_V2_PARAMS`, after `FIB_LIMIT: {"trail_atr_mult": 3.0, "tp2": False},`:

```python
    # v180: one whole-position target, no runner, fixed by spec § 3 (not a TRAIN-grid result).
    TURTLE_SOUP: {"trail_atr_mult": 2.5, "tp2": False},
```

In `PLAN_SHAPES`, after the `FIB_LIMIT` entry:

```python
    # v180 § 3: market-on-open the next session (exit_sim's next-open fill, V180-5); one
    # whole-position target; no break-even move; hard exit 10 sessions with the fill as
    # session 1 (exit_sim.SESSION_ONE_HOLD_CAP).
    TURTLE_SOUP: {"entry_type": "market", "expiry_bars": 1, "tp1_fraction": 1.0,
                  "breakeven_trigger_fraction": 1.0, "hold_cap_bars": 10},
```

- [ ] **Step 5: Implement the levels** — `swingbot/core/planning/turtle_soup_plan.py`

```python
"""v180: Turtle Soup plan levels. Every level is an absolute price known at the signal close,
so the alert can rest as orders before the open.

Stop: Low[t] - STRUCTURE_BUFFER_ATR x ATR14[t] through builders._bounded_stop. TURTLE_SOUP is in
strategy_types.STRUCTURAL_DROP_STRATEGIES, so a stop beyond the 2w max_risk_pct (3.0%) from the
signal close DROPS the plan (RISK_CAP); it is never squeezed to 2%.
Target: select_structural_target over the level map's resistances PRE-FILTERED to the frozen
min/max R:R band, measured from the signal close. Pre-filtering is the spec's "no plan when no
level falls in the band": unfiltered, the selector returns a synthetic entry + max_rr x R price
whenever the nearest qualifying level lies beyond the cap.
NO-LOOKAHEAD: reads bars <= index only. A level map built here comes from df.iloc[:index + 1]."""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS, TURTLE_SOUP
from .builders import _bounded_stop
from .params import STRUCTURE_BUFFER_ATR
from .targets import _safe_atr_value, select_structural_target

RISK_CAP = "risk_cap"
NO_LEVEL_IN_BAND = "no_level_in_band"
PLAN_OTHER = "plan_other"
_DIRECTION = "bullish"


@dataclass(frozen=True)
class TurtleSoupLevels:
    """stop/tp1 None with `reason` set when no plan exists at this bar."""

    stop: float | None
    tp1: float | None
    candidates: tuple[float, ...]
    reason: str | None


def in_band(entry: float, stop: float, prices, min_rr: float, max_rr: float) -> list[float]:
    """Prices above `entry` paying between min_rr and max_rr times the risk, nearest first.
    Same relative epsilon as select_structural_target, so a level exactly on either edge counts."""
    risk = entry - stop
    if risk <= 0:
        return []
    eps = 1e-9 * max(1.0, abs(entry))
    low, high = risk * min_rr - eps, risk * max_rr + eps
    return sorted(float(p) for p in prices if p and low <= float(p) - entry <= high)


def _scan_params(scan_params):
    if scan_params is not None:
        return scan_params
    from swingbot.scan_params import ScanParams
    return ScanParams.from_config()


def _resistance_prices(df, index, horizon_key, level_map) -> list[float]:
    """The level map's resistances; built from bars <= index when the caller passed none."""
    if level_map is None:
        level_map = levels.build_level_map(df.iloc[:index + 1], HORIZONS[horizon_key],
                                           float(df["Close"].iloc[index]))
    return [float(lv.price) for lv in level_map[1]]


def turtle_soup_levels(df, index, horizon_key, *, entry, atr_val, level_map=None,
                       scan_params=None) -> TurtleSoupLevels:
    """Stop, target and in-band candidates for a bullish Turtle Soup at bar `index`."""
    raw_stop = float(df["Low"].iloc[index]) - STRUCTURE_BUFFER_ATR * atr_val
    if raw_stop >= entry:
        return TurtleSoupLevels(None, None, (), PLAN_OTHER)
    stop = _bounded_stop(entry, raw_stop, True, TURTLE_SOUP, _DIRECTION, horizon_key)
    if stop is None:
        return TurtleSoupLevels(None, None, (), RISK_CAP)
    params = _scan_params(scan_params)
    min_rr, max_rr = params.min_risk_reward_ratio, params.max_risk_reward_ratio
    band = tuple(in_band(entry, stop, _resistance_prices(df, index, horizon_key, level_map),
                         min_rr, max_rr))
    if not band:
        return TurtleSoupLevels(stop, None, (), NO_LEVEL_IN_BAND)
    tp1 = select_structural_target(entry, stop, True, band, min_rr, max_rr)
    return TurtleSoupLevels(stop, tp1, band, None)


def turtle_soup_branch(inputs):
    """builders._STRUCTURAL_BRANCHES entry: (stop, tp1, candidates, None), or None."""
    if inputs.direction != _DIRECTION:
        return None
    picked = turtle_soup_levels(inputs.df, inputs.index, inputs.horizon_key, entry=inputs.close,
                                atr_val=inputs.atr_val, level_map=inputs.level_map,
                                scan_params=inputs.scan_params)
    if picked.reason is not None:
        return None
    return picked.stop, picked.tp1, list(picked.candidates), None


def turtle_soup_rejection_reason(df, index, horizon_key, scan_params=None, level_map=None) -> str:
    """Why build_strategy_plan returned None for a Turtle Soup signal at `index`: RISK_CAP,
    NO_LEVEL_IN_BAND, or PLAN_OTHER (the levels were fine, so a gate or the geometry check
    said no). Sized exactly as build_strategy_plan sizes it: signal close, safe ATR14."""
    from swingbot.core.market.indicators import atr as atr_indicator

    entry = float(df["Close"].iloc[index])
    atr_val = _safe_atr_value(entry, float(atr_indicator(df, 14).iloc[index]))
    picked = turtle_soup_levels(df, index, horizon_key, entry=entry, atr_val=atr_val,
                                level_map=level_map, scan_params=scan_params)
    return picked.reason or PLAN_OTHER
```

- [ ] **Step 6: Register the branch and the lifecycle exemption** — `swingbot/core/planning/builders.py`

Import (l.13-14):

```python
from swingbot.core.market.strategy_types import (BREAKEVEN_TRIGGER_FRACTION, COMPRESSION_SHORT,
                                                  FIB_LIMIT, HORIZONS, SHORT_STRATEGIES,
                                                  TURTLE_SOUP)
```

After `_short_branch`:

```python
def _turtle_soup_branch(inputs):
    """v180: planning/turtle_soup_plan.py (imported lazily: it imports _bounded_stop from here)."""
    from .turtle_soup_plan import turtle_soup_branch

    return turtle_soup_branch(inputs)
```

After `_STRUCTURAL_BRANCHES[FIB_LIMIT] = _fib_limit_branch`:

```python
_STRUCTURAL_BRANCHES[TURTLE_SOUP] = _turtle_soup_branch
```

Replace `_lifecycle_pair`'s exemption test (`build_strategy_plan` is not touched, so its complexity stays 14):

```python
# Strategies whose stop and target are exact structure the level-lifecycle adjuster's
# re-selection may not move: the v119 compression short and the v180 Turtle Soup.
_LIFECYCLE_EXEMPT = frozenset({COMPRESSION_SHORT, TURTLE_SOUP})


def _lifecycle_pair(df, index, entry, stop, tp1, atr_val, direction, strategy,
                    horizon_key, level_map, candidates):
    """(stop, tp1) after the level lifecycle. _LIFECYCLE_EXEMPT strategies keep their own
    structural stop and in-band target unchanged."""
    if strategy in _LIFECYCLE_EXEMPT:
        return stop, tp1
    stop, tp1, _meta = apply_level_lifecycle(
        df, index, entry=entry, stop=stop, tp1=tp1, atr_val=atr_val,
        direction=direction, strategy=strategy, horizon_key=horizon_key,
        level_map=level_map, candidate_levels=candidates)
    return stop, tp1
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_turtle_soup_plan.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_strategy_branch_table.py`
Expected: each `0 failed`.

- [ ] **Step 8: Run the neighbouring plan tests unmodified** (scope, shapes, the compression lifecycle exemption, the v139 golden)

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_plan_shape.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_compression_short_plan.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_fib_limit_registration.py`
Run: `python scripts/dev/testrun.py file tests/planning/test_tp2.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`
Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` exits 0. If you are unsure what else reaches the diff, run `python scripts/dev/testrun.py changed`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/turtle_soup_plan.py tests/planning/test_turtle_soup_plan.py swingbot/core/market/strategy_types.py swingbot/core/planning/stop_scope.py swingbot/core/planning/params.py swingbot/core/planning/builders.py tests/planning/test_strategy_branch_table.py
git commit -m "feat(v180): Turtle Soup structural plan -- drop scope, single-leg market shape, in-band level target" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
