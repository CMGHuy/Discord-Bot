# v174 Intermarket shock screens, part 2: the two ideas, diagnostics, the shots, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V174-7:" -A 400 docs/superpowers/plans/2026-10-18-v174-intermarket-shock-screens_2-ideas-diagnostics-shots.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v174-intermarket-shock-screens-design.md`](../specs/2026-10-18-v174-intermarket-shock-screens-design.md) (every applied `## Panel review` finding is a requirement)
**Index:** [`2026-10-18-v174-intermarket-shock-screens_0-index.md`](2026-10-18-v174-intermarket-shock-screens_0-index.md) — **Global Constraints, Review Focus, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints.** Part 1 (`_1-context-hook.md`, V174-1..V174-5) builds `screen/context.py`, `Idea.context`, the runner seam and the TLT/UUP fetch this part consumes.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C $WT`. **A PreToolUse hook rejects Bash commands that contain the string `screen_idea` with an unbalanced quote** (heredocs included): write and edit files with Write/Edit, and keep every Bash command that names the runner free of apostrophes.

# Phase 3 — The two frozen ideas and the diagnostics module

### Task V174-6: The two frozen ideas and their registry pins

**Model:** opus — entry signals in no-lookahead territory

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py`
- Create: `swingbot/core/backtesting/screen/ideas/dollar_drop.py`
- Create: `tests/backtesting/screen/test_idea_bond_spike_rebound.py`
- Create: `tests/backtesting/screen/test_idea_dollar_drop.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES`, line 21)
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (the four exact pins, plus one new context pin)

**Interfaces:**
- Consumes (V174-1, `swingbot/core/backtesting/screen/context.py`): `trailing_z(close: pd.Series, lookback: int = LOOKBACK, window: int = Z_WINDOW) -> pd.Series` (float, NaN where undefined; W = the `window` values of `r` before t, t excluded, population std, NaN when W is short, holds a NaN, `r(t)` is NaN or `std(W) <= STD_FLOOR`); `z_gate(z: pd.Series, threshold: float) -> pd.Series` (`z >= threshold` when `threshold > 0`, else `z <= threshold`; `.fillna(False)`, bool); `context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series` (exact-date reindex onto `df_index`, missing dates `False`, bool, never forward-filled).
- Consumes (V174-3): `Idea.context: tuple[str, ...] = ()`, and `ideas._load` reading `tuple(getattr(module, "CONTEXT", ()))`. The runner calls a context idea as `idea.events(df, {name: frames[name] for name in idea.context})`.
- Produces: `IDEAS["bond_spike_rebound"]`, `IDEAS["dollar_drop"]`; per module `CONTEXT, CAP, RACE, PARAMS, SUMMARY, SOURCE` and `events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series` (bool, indexed on `df.index`, named after the idea). V174-7's tests build fake ideas of the same shape; V174-8's end-to-end test and V174-11/12 run these two.

The ideas are frozen by the spec (§ 3) before any stock outcome is read. Nothing in this task may tune a value: `lookback` 5, `window` 252, `z` +2.0 / −2.0, `CAP = 10`, `RACE = "fixed"`, long only.

- [ ] **Step 1: Write the failing test for `bond_spike_rebound`**

Create `tests/backtesting/screen/test_idea_bond_spike_rebound.py`:

```python
"""v174 bond_spike_rebound: TLT 5-day return z >= +2.0 vs its trailing 252 values."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import bond_spike_rebound
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

SPIKE = 500   # the bar where TLT steps up 12 %


def _tlt(n=600, seed=11):
    """A TLT-like walk from 2009-06-01 with one +12 % step at bar SPIKE."""
    base = random_walk(n, seed=seed, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[SPIKE:] *= 1.12
    return frame(closes, start="2009-06-01")


def _reference_z(close: pd.Series, lookback=5, window=252) -> np.ndarray:
    """Brute force, one bar at a time: W = r[t-252..t-1], t excluded, ddof 0."""
    r = (close / close.shift(lookback) - 1.0).to_numpy()
    out = np.full(len(r), np.nan)
    for t in range(window, len(r)):
        w = r[t - window:t]
        if np.isnan(w).any() or np.isnan(r[t]):
            continue
        sd = w.std(ddof=0)
        if sd > 1e-12:
            out[t] = (r[t] - w.mean()) / sd
    return out


def test_the_constants_are_the_frozen_spec_values():
    assert bond_spike_rebound.CONTEXT == ("TLT",)
    assert bond_spike_rebound.CAP == 10
    assert bond_spike_rebound.RACE == "fixed"
    assert bond_spike_rebound.PARAMS == {"series": "TLT", "lookback": 5, "window": 252,
                                         "z": 2.0, "side": "long"}
    assert bond_spike_rebound.SUMMARY == "TLT 5-day return z >= +2.0 vs its trailing 252 values"
    assert bond_spike_rebound.SOURCE == (
        "Murphy (2004), Intermarket Analysis — shock proxy, "
        "see v174 § What the two shots can and cannot say")


def test_fires_exactly_where_the_reference_z_reaches_plus_two():
    tlt = _tlt()
    out = bond_spike_rebound.events(tlt, {"TLT": tlt})
    expected = np.flatnonzero(np.nan_to_num(_reference_z(tlt["Close"]), nan=-np.inf) >= 2.0)
    assert SPIKE in expected                                  # non-vacuous
    assert np.flatnonzero(out.to_numpy()).tolist() == expected.tolist()
    assert out.dtype == bool and out.name == "bond_spike_rebound"
    assert out.index.equals(tlt.index)


def test_never_fires_before_the_window_is_full():
    tlt = _tlt()
    out = bond_spike_rebound.events(tlt, {"TLT": tlt})
    assert not out.iloc[:257].any()                           # 5 + 252 bars of warm-up


def test_a_stock_date_without_a_tlt_bar_is_false_never_forward_filled():
    tlt = _tlt()
    stock = frame(np.linspace(50, 60, len(tlt)), index=tlt.index)
    thin = tlt.drop(tlt.index[SPIKE + 1])
    out = bond_spike_rebound.events(stock, {"TLT": thin})
    assert out.index.equals(stock.index)
    assert out.loc[tlt.index[SPIKE]]                          # the spike day itself still fires
    assert not out.loc[tlt.index[SPIKE + 1]]                  # no TLT bar -> False, not carried


def test_a_tlt_only_date_is_ignored():
    tlt = _tlt()
    stock = frame(np.linspace(50, 60, len(tlt) - 1), index=tlt.index.delete(SPIKE))
    out = bond_spike_rebound.events(stock, {"TLT": tlt})
    assert out.index.equals(stock.index)
    assert tlt.index[SPIKE] not in out.index


def test_reads_no_later_tlt_bar():
    tlt = _tlt()
    assert bond_spike_rebound.events(tlt, {"TLT": tlt}).any()   # non-vacuous
    assert_prefix_stable(lambda d: bond_spike_rebound.events(d, {"TLT": d}), tlt,
                         [257, 300, SPIKE - 1, SPIKE, SPIKE + 4, 599])


def test_changing_a_tlt_bar_after_t_never_changes_the_event_at_t():
    tlt = _tlt()
    before = bond_spike_rebound.events(tlt, {"TLT": tlt})
    later = tlt.copy()
    later.iloc[SPIKE + 1:, later.columns.get_loc("Close")] *= 0.5
    after = bond_spike_rebound.events(tlt, {"TLT": later})
    pd.testing.assert_series_equal(after.iloc[:SPIKE + 1], before.iloc[:SPIKE + 1])
```

- [ ] **Step 2: Write the failing test for `dollar_drop`**

Create `tests/backtesting/screen/test_idea_dollar_drop.py`:

```python
"""v174 dollar_drop: UUP 5-day return z <= -2.0 vs its trailing 252 values."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import dollar_drop
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

DROP = 500   # the bar where UUP steps down 12 %


def _uup(n=600, seed=13):
    """A UUP-like walk from 2009-06-01 with one -12 % step at bar DROP."""
    base = random_walk(n, seed=seed, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[DROP:] *= 0.88
    return frame(closes, start="2009-06-01")


def _reference_z(close: pd.Series, lookback=5, window=252) -> np.ndarray:
    """Brute force, one bar at a time: W = r[t-252..t-1], t excluded, ddof 0."""
    r = (close / close.shift(lookback) - 1.0).to_numpy()
    out = np.full(len(r), np.nan)
    for t in range(window, len(r)):
        w = r[t - window:t]
        if np.isnan(w).any() or np.isnan(r[t]):
            continue
        sd = w.std(ddof=0)
        if sd > 1e-12:
            out[t] = (r[t] - w.mean()) / sd
    return out


def test_the_constants_are_the_frozen_spec_values():
    assert dollar_drop.CONTEXT == ("UUP",)
    assert dollar_drop.CAP == 10
    assert dollar_drop.RACE == "fixed"
    assert dollar_drop.PARAMS == {"series": "UUP", "lookback": 5, "window": 252,
                                  "z": -2.0, "side": "long"}
    assert dollar_drop.SUMMARY == "UUP 5-day return z <= -2.0 vs its trailing 252 values"
    assert dollar_drop.SOURCE == (
        "Murphy (2004), Intermarket Analysis — shock proxy, "
        "see v174 § What the two shots can and cannot say")


def test_fires_exactly_where_the_reference_z_reaches_minus_two():
    uup = _uup()
    out = dollar_drop.events(uup, {"UUP": uup})
    expected = np.flatnonzero(np.nan_to_num(_reference_z(uup["Close"]), nan=np.inf) <= -2.0)
    assert DROP in expected                                   # non-vacuous
    assert np.flatnonzero(out.to_numpy()).tolist() == expected.tolist()
    assert out.dtype == bool and out.name == "dollar_drop"
    assert out.index.equals(uup.index)


def test_a_rise_never_fires_the_drop_idea():
    base = random_walk(600, seed=13, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[DROP:] *= 1.12
    up = frame(closes, start="2009-06-01")
    assert not dollar_drop.events(up, {"UUP": up}).iloc[DROP:DROP + 5].any()


def test_a_flat_series_has_no_z_and_never_fires():
    flat = frame(np.full(600, 25.0), start="2009-06-01")      # std(W) == 0 everywhere
    assert not dollar_drop.events(flat, {"UUP": flat}).any()


def test_a_stock_date_without_a_uup_bar_is_false_never_forward_filled():
    uup = _uup()
    stock = frame(np.linspace(50, 60, len(uup)), index=uup.index)
    thin = uup.drop(uup.index[DROP + 1])
    out = dollar_drop.events(stock, {"UUP": thin})
    assert out.loc[uup.index[DROP]]
    assert not out.loc[uup.index[DROP + 1]]


def test_reads_no_later_uup_bar():
    uup = _uup()
    assert dollar_drop.events(uup, {"UUP": uup}).any()        # non-vacuous
    assert_prefix_stable(lambda d: dollar_drop.events(d, {"UUP": d}), uup,
                         [257, 300, DROP - 1, DROP, DROP + 4, 599])


def test_changing_a_uup_bar_after_t_never_changes_the_event_at_t():
    uup = _uup()
    before = dollar_drop.events(uup, {"UUP": uup})
    later = uup.copy()
    later.iloc[DROP + 1:, later.columns.get_loc("Close")] *= 2.0
    after = dollar_drop.events(uup, {"UUP": later})
    pd.testing.assert_series_equal(after.iloc[:DROP + 1], before.iloc[:DROP + 1])
```

- [ ] **Step 3: Pin the registry**

In `tests/backtesting/screen/test_ideas_registry.py`, replace the bodies of the four exact pins and add one new test. Leave every other test as it is. If V174-3 added a test that pins `context == ()` over **every** registered idea, narrow it to the six names `("high52w", "uptrend_pullback", "gap_volume", "turn_of_month", "turtle_soup", "quiet_pullback")`; the new test below pins all eight.

```python
def test_registry_holds_the_first_batch_in_spec_order_then_later_ideas():
    assert ideas.IDEA_MODULES == ("high52w", "uptrend_pullback", "gap_volume",
                                  "turn_of_month", "turtle_soup", "quiet_pullback",
                                  "bond_spike_rebound", "dollar_drop")
    assert list(IDEAS) == list(ideas.IDEA_MODULES)
    assert all(IDEAS[name].name == name for name in IDEAS)


def test_time_caps_are_the_spec_values():
    assert {n: i.time_cap_bars for n, i in IDEAS.items()} == {
        "high52w": 60, "uptrend_pullback": 10, "gap_volume": 20, "turn_of_month": 4,
        "turtle_soup": 10, "quiet_pullback": 10, "bond_spike_rebound": 10,
        "dollar_drop": 10}
```

Append to the end of `test_frozen_parameter_sets` (after the `quiet_pullback` assert):

```python
    assert dict(IDEAS["bond_spike_rebound"].params) == {
        "series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}
    assert dict(IDEAS["dollar_drop"].params) == {
        "series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}
```

Replace the dict in `test_every_registered_idea_is_raced_under_one_pinned_shape`:

```python
    assert {n: i.race_shape for n, i in IDEAS.items()} == {
        "high52w": "fixed", "uptrend_pullback": "fixed", "gap_volume": "fixed",
        "turn_of_month": "fixed", "turtle_soup": "fixed", "quiet_pullback": "fixed",
        "bond_spike_rebound": "fixed", "dollar_drop": "fixed"}
```

Add after it:

```python
MURPHY = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def test_only_the_two_intermarket_ideas_read_context_series():
    """v174 § 3: the six older ideas keep `events(df)`; the two new ones
    each name one context series and cite the scope section."""
    assert {n: i.context for n, i in IDEAS.items()} == {
        "high52w": (), "uptrend_pullback": (), "gap_volume": (), "turn_of_month": (),
        "turtle_soup": (), "quiet_pullback": (),
        "bond_spike_rebound": ("TLT",), "dollar_drop": ("UUP",)}
    assert IDEAS["bond_spike_rebound"].source == MURPHY
    assert IDEAS["dollar_drop"].source == MURPHY
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_idea_bond_spike_rebound.py`
Expected: FAIL at collection, `ImportError: cannot import name 'bond_spike_rebound'`.

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL in the four pins and in `test_only_the_two_intermarket_ideas_read_context_series` (the registry still holds six ideas).

- [ ] **Step 5: Write `bond_spike_rebound.py`**

Create `swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py`:

```python
"""Bond spike rebound (v174, frozen 2026-10-18): TLT 5-day return z >= +2.0
against its trailing 252 values, long the stock the next open.

A shock proxy, not Murphy's claim itself: in 2010-19 such a TLT rally was
mostly a flight-to-quality day, so long stocks after it tests a rebound
after a risk-off bond spike (spec § What the two shots can and cannot say).
A fail closes exactly this frozen definition.
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from swingbot.core.backtesting.screen import context as pit

CONTEXT = ("TLT",)
CAP = 10
RACE = "fixed"
PARAMS = {"series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}
SUMMARY = "TLT 5-day return z >= +2.0 vs its trailing 252 values"
SOURCE = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series:
    """True on every stock date whose own TLT bar has z >= +2.0. The z at t
    reads TLT bars dated <= t only; a stock date with no TLT bar is False."""
    close = context[PARAMS["series"]]["Close"]
    z = pit.trailing_z(close, PARAMS["lookback"], PARAMS["window"])
    gate = pit.z_gate(z, PARAMS["z"])
    return pit.context_on(df.index, gate).rename("bond_spike_rebound")
```

- [ ] **Step 6: Write `dollar_drop.py`**

Create `swingbot/core/backtesting/screen/ideas/dollar_drop.py`:

```python
"""Dollar drop (v174, frozen 2026-10-18): UUP 5-day return z <= -2.0
against its trailing 252 values, long the stock the next open.

Closer to Murphy (a falling dollar is bullish for equities), but a lagged
proxy for a trend claim: a dollar drop often accompanies a risk-on rally
already under way (spec § What the two shots can and cannot say). A fail
closes exactly this frozen definition.
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from swingbot.core.backtesting.screen import context as pit

CONTEXT = ("UUP",)
CAP = 10
RACE = "fixed"
PARAMS = {"series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}
SUMMARY = "UUP 5-day return z <= -2.0 vs its trailing 252 values"
SOURCE = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series:
    """True on every stock date whose own UUP bar has z <= -2.0. The z at t
    reads UUP bars dated <= t only; a stock date with no UUP bar is False."""
    close = context[PARAMS["series"]]["Close"]
    z = pit.trailing_z(close, PARAMS["lookback"], PARAMS["window"])
    gate = pit.z_gate(z, PARAMS["z"])
    return pit.context_on(df.index, gate).rename("dollar_drop")
```

- [ ] **Step 7: Register both, in spec order**

In `swingbot/core/backtesting/screen/ideas/__init__.py`, replace the `IDEA_MODULES` assignment (line 21) with:

```python
IDEA_MODULES = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
                "turtle_soup", "quiet_pullback", "bond_spike_rebound", "dollar_drop")
```

Change nothing else in the file (V174-3 owns the `Idea.context` field and the module docstring).

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_idea_bond_spike_rebound.py`
Expected: PASS (7 tests).

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_idea_dollar_drop.py`
Expected: PASS (8 tests).

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS.

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (both new modules live under `swingbot/core/backtesting/`).

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
Expected: PASS. `build_parser` lists `IDEAS` as the `--idea` choices, so the two names become valid there; no older pin changes.

- [ ] **Step 9: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py $WT/swingbot/core/backtesting/screen/ideas/dollar_drop.py | head`
Expected: no output (every function below rank C).

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py swingbot/core/backtesting/screen/ideas/dollar_drop.py tests/backtesting/screen/test_idea_bond_spike_rebound.py tests/backtesting/screen/test_idea_dollar_drop.py
git -C $WT commit -m "feat(screen): bond_spike_rebound and dollar_drop, frozen v174 intermarket ideas (V174-6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $WT add swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_ideas_registry.py
git -C $WT commit -m "feat(screen): register the two intermarket ideas and pin their context (V174-6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V174-7: Diagnostics module: effective sample, null overlap, selloff split, concentration, screen-family q, scope

**Model:** opus — statistical read-outs printed beside a pre-registered verdict, with signal-day mapping

**Files:**
- Create: `swingbot/core/backtesting/screen/diagnostics.py`
- Create: `tests/backtesting/screen/test_diagnostics.py`

**Interfaces:**
- Consumes (V174-1, `screen/context.py`): `r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series` (`close(t) / close(t-5) - 1` by row offset).
- Consumes (V174-2, `screen/context.py`): `@dataclass(frozen=True) ContextData(frames: Mapping[str, pd.DataFrame], calendar: pd.DataFrame, records: Mapping[str, dict])`; `calendar` is the loaded SPY frame (`load_frame(cache_dir / "SPY.csv", CONTEXT_START, end)`), each record has keys `ticker, rows, first, last, fetched, sha256`.
- Consumes (V174-3): `Idea(..., context=("TLT",))`; a context idea is called `idea.events(df, {name: frames[name] for name in idea.context})`.
- Consumes (existing): `verdict.PairedEvent`, `verdict.decide`, `verdict.mean_d`, `verdict.YEARS` (`screen/verdict.py:32/117/57/24`); `stats.group_by_week` (`instrument/stats.py:40`), `stats.ledger_qvalues` (`:223`).
- Produces (V174-8 calls these, names and shapes final):
  - `EPISODE_GAP = 5`; `HEADING = "## Intermarket diagnostics (printed, never gating)"`.
  - `shock_days(idea, data: ContextData, *, event_start: str, event_end: str) -> pd.DatetimeIndex` — the SPY sessions in `[event_start, event_end]` where `idea.events(data.calendar, frames)` is true.
  - `signal_days(entry_dates: list[str], sessions: pd.DatetimeIndex) -> list[pd.Timestamp]` — the last session strictly before each entry date (the signal day t; entry is t+1's open); `pd.NaT` when none.
  - `episodes(days: pd.DatetimeIndex, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[pd.DatetimeIndex]` — a new episode starts when two consecutive shock days sit more than `gap` sessions apart.
  - `screen_family_q(rows: list[dict], row: dict, instrument: str) -> float | None` — `stats.ledger_qvalues([r for r in rows + [row] if r["instrument"] == instrument])` at `row["id"]`.
  - `scope_sentence(idea) -> str` — the frozen-definition wording, built from `idea.params` and `idea.time_cap_bars`.
  - `compute(idea, events: list[dict], restricted: list[dict] | None, data: ContextData, *, event_start: str, event_end: str) -> dict` with keys `sample, overlap, selloff, concentration` (shapes below). `events` are the summary's kept event rows (`entry_date`, `r_event`, `r_null`, ...); `restricted` the restricted-null pairs (`entry_date`, `r_event`, `r_null`) pooled over tickers, or `None` when that pass did not run.
  - `render(diag: dict, data: ContextData, *, context_start: str, window_start: str, screen_q: float | None, scope: str) -> list[str]`, first line `HEADING`.

`compute` returns, exactly:

```text
sample:        {"n": int, "shock_days": int, "episodes": int, "weeks": int,
                "per_year": {year: (shock_days, kept_events) for year in verdict.YEARS}}
overlap:       {"cap": int, "n": int, "official": float | None, "restricted": Verdict | None}
selloff:       {"shock_down": int, "shock_up": int, "shock_mean": float | None,
                "down": Verdict | None, "up": Verdict | None, "undefined": int}
concentration: {"rows": [(label, kept_events, contribution)] largest first,
                "unmatched": int, "delta": float | None}
```

**Never gating.** Nothing here reads or writes a summary's `verdict`. Every `decide` goes through `verdict.decide` looked up on the module at call time, so the runner tests' autouse 500-resample patch (`monkeypatch.setattr(screen_idea.verdict, "decide", ...)` patches this same module object) reaches it. The official ΔExpR uses `verdict.mean_d`, so no second 10,000-resample bootstrap runs for it.

**Why signal days come from SPY sessions:** `_event_rows` keeps only `entry_date` (`screen_idea.py:103`), the session after the signal bar. A context event fires on the shock day itself, so the session before the entry date in the SPY calendar is the shock day for every stock that traded both days. A stock that skipped a session maps elsewhere and is counted as `unmatched`, never forced into an episode.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_diagnostics.py`:

```python
"""v174 § 5: intermarket diagnostics, printed beside the verdict, never gating."""
import functools
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import diagnostics, verdict
from swingbot.core.backtesting.screen.context import ContextData
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import frame

N_BARS = 800
SHOCKS = (300, 450, 451, 452, 460, 600)    # 300 falls in 2010, before the event window
DIP = 460                                  # SPY closes far lower here: r5 < 0 on that shock day


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(verdict, "decide", functools.partial(verdict.decide, n_resamples=300))


def _calendar() -> pd.DataFrame:
    closes = 100.0 + 0.1 * np.arange(N_BARS)
    closes[DIP] = 90.0
    return frame(closes, start="2009-06-01")


def _shock_events(df, context):
    days = context["TLT"].index[list(SHOCKS)]
    return pd.Series(df.index.isin(days), index=df.index, name="fake_ctx")


def _idea():
    return Idea(name="fake_ctx", events=_shock_events, time_cap_bars=10,
                params={"series": "TLT", "lookback": 5, "window": 252, "z": 2.0,
                        "side": "long"},
                summary="s", source="src", context=("TLT",))


def _data() -> ContextData:
    cal = _calendar()
    tlt = frame(50.0 + 0.01 * np.arange(N_BARS), start="2009-06-01")
    record = {"ticker": "TLT", "rows": N_BARS, "first": "2009-06-01",
              "last": cal.index[-1].strftime("%Y-%m-%d"), "fetched": "2026-10-18",
              "sha256": "ab" * 32}
    return ContextData(frames={"TLT": tlt}, calendar=cal, records={"TLT": record})


def _entry(pos: int) -> str:
    return _calendar().index[pos + 1].strftime("%Y-%m-%d")


def _row(ticker, signal_pos, r_event, r_null):
    return {"ticker": ticker, "entry_date": _entry(signal_pos), "exit_date": _entry(signal_pos + 5),
            "r_event": r_event, "r_null": r_null, "outcome": "timeout"}


def _events():
    """d = +0.5, +0.3 (episode 450-452), -0.2 (episode 460), +0.1 (episode 600),
    0.0 on a non-shock signal day (470): N = 5, mean d = +0.14."""
    return [_row("AAA", 450, 0.6, 0.1), _row("BBB", 450, 0.4, 0.1),
            _row("AAA", 460, -0.1, 0.1), _row("AAA", 600, 0.3, 0.2),
            _row("BBB", 470, 0.2, 0.2)]


def _window():
    return {"event_start": "2011-01-01", "event_end": "2019-12-31"}


# --- signal days and episodes ---------------------------------------------

def test_a_signal_day_is_the_session_before_the_entry():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    out = diagnostics.signal_days(["2011-03-07", "2011-03-02"], sessions)
    assert out == [pd.Timestamp("2011-03-04"), pd.Timestamp("2011-03-01")]   # Monday -> Friday


def test_an_entry_off_the_calendar_maps_to_the_last_session_before_it():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    assert diagnostics.signal_days(["2011-03-05"], sessions) == [pd.Timestamp("2011-03-04")]


def test_an_entry_on_the_first_session_has_no_signal_day():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    assert pd.isna(diagnostics.signal_days(["2011-03-01"], sessions)[0])


def test_episodes_split_on_a_gap_of_more_than_five_sessions():
    sessions = pd.bdate_range("2011-01-03", periods=100)
    days = sessions[[10, 11, 12, 18, 30, 35]]
    out = diagnostics.episodes(days, sessions)
    assert [list(run) for run in out] == [list(sessions[[10, 11, 12]]), [sessions[18]],
                                          list(sessions[[30, 35]])]   # 30 -> 35 is exactly 5
    assert diagnostics.EPISODE_GAP == 5


def test_no_shock_day_is_no_episode():
    assert diagnostics.episodes(pd.DatetimeIndex([]), pd.bdate_range("2011-01-03", periods=5)) == []


def test_shock_days_are_the_calendar_dates_the_idea_fires_inside_the_event_window():
    data = _data()
    out = diagnostics.shock_days(_idea(), data, **_window())
    assert list(out) == list(data.calendar.index[[450, 451, 452, 460, 600]])   # 300 is 2010


# --- screen-family q and scope ----------------------------------------------

def test_the_screen_family_q_counts_screen_rows_only():
    rows = [{"id": "v139-arm-d", "instrument": "v1", "p": 0.001},
            {"id": "v139-arm-e", "instrument": "v1", "p": 0.9},
            {"id": "screen-a", "instrument": "screen-v1", "p": 0.04},
            {"id": "screen-b", "instrument": "screen-v1", "p": None}]
    row = {"id": "screen-new", "instrument": "screen-v1", "p": 0.03}
    family = diagnostics.screen_family_q(rows, row, "screen-v1")
    whole = stats.ledger_qvalues(rows + [row])["screen-new"]
    assert family == pytest.approx(stats.bh_qvalues([0.04, 0.03])[1])
    assert family == pytest.approx(0.04)
    assert whole == pytest.approx(0.04 * 4 / 3)
    assert family != pytest.approx(whole)


def test_the_screen_family_q_is_none_without_a_p():
    row = {"id": "screen-new", "instrument": "screen-v1", "p": None}
    assert diagnostics.screen_family_q([], row, "screen-v1") is None


def test_the_scope_sentence_closes_the_frozen_definition_only():
    text = diagnostics.scope_sentence(_idea())
    for needle in ("TLT 5-day return z >= +2.0", "trailing 252 values", "long only",
                   "fixed 10-bar race", "closes exactly this frozen definition",
                   "not intermarket analysis", "not a slow-regime test",
                   "not a bearish or longer-horizon variant"):
        assert needle in text, needle


def test_the_scope_sentence_reads_a_negative_threshold_as_at_most():
    idea = Idea(name="fake_drop", events=_shock_events, time_cap_bars=10,
                params={"series": "UUP", "lookback": 5, "window": 252, "z": -2.0,
                        "side": "long"}, summary="s", source="src", context=("UUP",))
    assert "UUP 5-day return z <= -2.0" in diagnostics.scope_sentence(idea)


# --- compute ----------------------------------------------------------------

def test_the_effective_sample_counts_shock_days_episodes_and_weeks():
    data = _data()
    sample = diagnostics.compute(_idea(), _events(), None, data, **_window())["sample"]
    assert (sample["n"], sample["shock_days"], sample["episodes"]) == (5, 5, 3)
    assert sample["weeks"] == 4                       # entries 451 (twice), 461, 471, 601
    shocks = Counter(data.calendar.index[p].year for p in (450, 451, 452, 460, 600))
    kept = Counter(int(row["entry_date"][:4]) for row in _events())
    assert sample["per_year"] == {year: (shocks.get(year, 0), kept.get(year, 0))
                                  for year in verdict.YEARS}


def test_the_null_overlap_recomputes_delta_on_the_restricted_pairs():
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3},
                  {"entry_date": _entry(600), "r_event": 0.3, "r_null": 0.3}]
    out = diagnostics.compute(_idea(), _events(), restricted, _data(), **_window())["overlap"]
    assert out["cap"] == 10 and out["n"] == 5
    assert out["official"] == pytest.approx(0.14)
    assert out["restricted"].n == 2
    assert out["restricted"].delta_exp_r == pytest.approx(0.15)


def test_no_restricted_pass_reports_none():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["overlap"]
    assert out["restricted"] is None


def test_the_selloff_split_reads_spy_r5_at_each_signal_day():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["selloff"]
    assert (out["shock_down"], out["shock_up"]) == (1, 4)
    assert out["down"].n == 1 and out["down"].delta_exp_r == pytest.approx(-0.2)
    assert out["up"].n == 4 and out["up"].delta_exp_r == pytest.approx(0.225)
    assert out["undefined"] == 0
    assert out["shock_mean"] is not None


def test_concentration_sorts_episode_contributions_largest_first():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["concentration"]
    cal = _calendar().index
    labels = [f"{cal[450]:%Y-%m-%d}..{cal[452]:%Y-%m-%d}", f"{cal[600]:%Y-%m-%d}",
              f"{cal[460]:%Y-%m-%d}"]
    assert [row[0] for row in out["rows"]] == labels
    assert [row[1] for row in out["rows"]] == [2, 1, 1]
    assert [row[2] for row in out["rows"]] == pytest.approx([0.16, 0.02, -0.04])
    assert out["unmatched"] == 1                      # the signal day 470 is no shock day
    assert out["delta"] == pytest.approx(0.14)


def test_every_decide_goes_through_the_module_attribute(monkeypatch):
    calls = []
    real = verdict.decide

    def spy(events, **kw):
        calls.append(len(list(events)))
        return real(events, n_resamples=200)

    monkeypatch.setattr(verdict, "decide", spy)
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3}]
    diagnostics.compute(_idea(), _events(), restricted, _data(), **_window())
    assert sorted(calls) == [1, 1, 4]                 # restricted, selloff down, selloff up


def test_compute_never_mutates_the_event_rows():
    events = _events()
    snapshot = [dict(row) for row in events]
    diagnostics.compute(_idea(), events, None, _data(), **_window())
    assert events == snapshot


# --- render -------------------------------------------------------------------

def _rendered(restricted=None, screen_q=0.0421):
    data = _data()
    diag = diagnostics.compute(_idea(), _events(), restricted, data, **_window())
    return diagnostics.render(diag, data, context_start="2009-06-01",
                              window_start="2010-01-01", screen_q=screen_q,
                              scope=diagnostics.scope_sentence(_idea()))


def test_render_opens_with_the_never_gating_heading():
    lines = _rendered()
    assert lines[0] == "## Intermarket diagnostics (printed, never gating)"
    assert all(isinstance(line, str) for line in lines)


def test_render_prints_all_six_diagnostics():
    text = "\n".join(_rendered())
    for needle in ("### 1. Effective sample", "### 2. Null overlap",
                   "### 3. SPY selloff split", "### 4. Concentration by shock episode",
                   "### 5. Multiple comparisons", "### 6. Scope",
                   "5 shock days in 3 episodes", "4 distinct ISO entry weeks",
                   "undercovers", "Restricted null not run",
                   "| < 0 | 1 |", "| >= 0 | 4 |", "mean-reversion effect",
                   "BH q = 0.0421 across the `screen-v1` family",
                   "closes exactly this frozen definition"):
        assert needle in text, needle


def test_render_records_both_starts_and_every_context_file():
    text = "\n".join(_rendered())
    assert "loaded from 2009-06-01" in text and "stock window starts 2010-01-01" in text
    assert "| TLT | 800 | 2009-06-01 |" in text
    assert "ab" * 32 in text and "2026-10-18" in text


def test_render_prints_the_restricted_delta_when_the_pass_ran():
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3},
                  {"entry_date": _entry(600), "r_event": 0.3, "r_null": 0.3}]
    text = "\n".join(_rendered(restricted))
    assert "at least 10 sessions from any shock day" in text
    assert "ΔExpR +0.1500R" in text and "N = 2" in text


def test_render_prints_n_a_without_a_screen_q():
    assert "BH q = n/a across" in "\n".join(_rendered(screen_q=None))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py`
Expected: FAIL at collection, `ImportError: cannot import name 'diagnostics'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/diagnostics.py`:

```python
"""v174 § 5: intermarket diagnostics for a context idea's results doc.

Six read-outs printed beside the verdict and never part of it: effective
sample, null overlap, SPY selloff split, per-episode concentration, the
screen-family BH q, and the scope sentence. Nothing here reads or writes a
summary's verdict. Every decide is ``verdict.decide`` looked up at call
time, so a patched decide (the runner tests' 500 resamples) reaches it.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import context as pit
from swingbot.core.backtesting.screen import verdict

EPISODE_GAP = 5    # a new shock episode starts more than 5 sessions after the last shock day
HEADING = "## Intermarket diagnostics (printed, never gating)"
SPEC_FILE = "2026-10-18-v174-intermarket-shock-screens-design.md"
HASH_FILE = "docs/superpowers/results/2026-10-18-v174-context-hashes.json"


# --- dates ------------------------------------------------------------------

def shock_days(idea, data, *, event_start: str, event_end: str) -> pd.DatetimeIndex:
    """SPY sessions in [event_start, event_end] where the idea fires on the
    calendar itself (one shock day fires every member with a bar on it)."""
    frames = {name: data.frames[name] for name in idea.context}
    fired = idea.events(data.calendar, frames).reindex(data.calendar.index, fill_value=False)
    days = data.calendar.index[np.asarray(fired, dtype=bool)]
    inside = (days >= pd.Timestamp(event_start)) & (days <= pd.Timestamp(event_end))
    return pd.DatetimeIndex(days[inside])


def signal_days(entry_dates, sessions) -> list:
    """The session before each entry date: the signal day t (entry is t+1's
    open). ``pd.NaT`` when no session precedes the entry."""
    sessions = pd.DatetimeIndex(sessions)
    entries = pd.DatetimeIndex(pd.to_datetime(list(entry_dates)))
    positions = sessions.searchsorted(entries, side="left") - 1
    return [sessions[p] if p >= 0 else pd.NaT for p in positions]


def episodes(days, sessions, gap: int = EPISODE_GAP) -> list:
    """Shock days grouped into runs; two days more than ``gap`` sessions
    apart start a new episode."""
    days = pd.DatetimeIndex(sorted(days))
    if not len(days):
        return []
    positions = pd.DatetimeIndex(sessions).get_indexer(days)
    breaks = np.flatnonzero(np.diff(positions) > gap) + 1
    starts, stops = np.r_[0, breaks], np.r_[breaks, len(days)]
    return [days[a:b] for a, b in zip(starts, stops)]


# --- ledger family and scope -------------------------------------------------

def screen_family_q(rows, row, instrument: str) -> float | None:
    """BH q of ``row`` across the rows of one instrument only (§ 5.5)."""
    family = [r for r in [*rows, row] if r["instrument"] == instrument]
    return stats.ledger_qvalues(family).get(row["id"])


def scope_sentence(idea) -> str:
    """The frozen-definition wording of spec § What the two shots can and
    cannot say, for the ledger hypothesis and the results doc."""
    p = idea.params
    op = ">=" if p["z"] > 0 else "<="
    return ("Scope: a shock proxy, not Murphy's intermarket claim itself; a fail "
            f"closes exactly this frozen definition ({p['series']} {p['lookback']}-day "
            f"return z {op} {p['z']:+.1f} vs its trailing {p['window']} values, long "
            f"only, the fixed {idea.time_cap_bars}-bar race) and nothing broader: not "
            "intermarket analysis, not a slow-regime test, not a bearish or "
            "longer-horizon variant.")


# --- compute ----------------------------------------------------------------

def _paired(rows) -> list:
    return [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
            for row in rows]


def _decide(rows):
    """``verdict.decide`` at call time; None for no rows."""
    return verdict.decide(_paired(rows)) if rows else None


def _per_year(days, events) -> dict:
    shock = Counter(day.year for day in days)
    kept = Counter(int(row["entry_date"][:4]) for row in events)
    return {year: (shock.get(year, 0), kept.get(year, 0)) for year in verdict.YEARS}


def _sample(events, days, runs) -> dict:
    return {"n": len(events), "shock_days": len(days), "episodes": len(runs),
            "weeks": len(stats.group_by_week(_paired(events))),
            "per_year": _per_year(days, events)}


def _overlap(events, restricted, cap: int) -> dict:
    return {"cap": cap, "n": len(events),
            "official": verdict.mean_d([], _paired(events)),
            "restricted": None if restricted is None else _decide(restricted)}


def _bucket(value) -> str:
    if value is None or not np.isfinite(value):
        return "undefined"
    return "down" if value < 0 else "up"


def _selloff(events, signals, days, spy_r5) -> dict:
    groups = {"down": [], "up": [], "undefined": []}
    for row, day in zip(events, signals):
        value = np.nan if pd.isna(day) else spy_r5.get(day, np.nan)
        groups[_bucket(value)].append(row)
    on_shock = spy_r5.reindex(days).dropna()
    return {"shock_down": int((on_shock < 0).sum()), "shock_up": int((on_shock >= 0).sum()),
            "shock_mean": float(on_shock.mean()) if len(on_shock) else None,
            "down": _decide(groups["down"]), "up": _decide(groups["up"]),
            "undefined": len(groups["undefined"])}


def _label(run) -> str:
    first, last = run[0].strftime("%Y-%m-%d"), run[-1].strftime("%Y-%m-%d")
    return first if first == last else f"{first}..{last}"


def _concentration(events, signals, runs) -> dict:
    """Each episode's share of mean(d): sum of its d over the total N."""
    where = {day: i for i, run in enumerate(runs) for day in run}
    sums, counts, unmatched = Counter(), Counter(), 0
    for row, day in zip(events, signals):
        i = None if pd.isna(day) else where.get(day)
        if i is None:
            unmatched += 1
            continue
        sums[i] += row["r_event"] - row["r_null"]
        counts[i] += 1
    rows = sorted(((_label(runs[i]), counts[i], sums[i] / len(events)) for i in counts),
                  key=lambda item: item[2], reverse=True)
    return {"rows": rows, "unmatched": unmatched,
            "delta": verdict.mean_d([], _paired(events))}


def compute(idea, events, restricted, data, *, event_start: str, event_end: str) -> dict:
    """The four computed diagnostics (§ 5.1-5.4); q and scope are rendered
    from their own inputs. Pure: ``events`` and ``restricted`` are only read."""
    sessions = data.calendar.index
    days = shock_days(idea, data, event_start=event_start, event_end=event_end)
    runs = episodes(days, sessions)
    signals = signal_days([row["entry_date"] for row in events], sessions)
    spy_r5 = pit.r_lookback(data.calendar["Close"])
    return {"sample": _sample(events, days, runs),
            "overlap": _overlap(events, restricted, idea.time_cap_bars),
            "selloff": _selloff(events, signals, days, spy_r5),
            "concentration": _concentration(events, signals, runs)}


# --- render -------------------------------------------------------------------

def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _render_data(data, context_start: str, window_start: str) -> list:
    lines = [f"**Context data** (v174 spec `{SPEC_FILE}`): context series loaded from "
             f"{context_start} for the z warm-up; the stock window starts {window_start}. "
             f"Adjusted closes, the bytes pinned by SHA-256 in `{HASH_FILE}`.", "",
             "| Series | rows | first bar | last bar | fetched | SHA-256 |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r['ticker']} | {r['rows']} | {r['first']} | {r['last']} | "
              f"{r['fetched']} | `{r['sha256']}` |"
              for _, r in sorted(data.records.items())]
    return lines


def _render_sample(sample) -> list:
    lines = ["### 1. Effective sample", "",
             f"Kept ticker events N = {sample['n']}, from {sample['shock_days']} shock days "
             f"in {sample['episodes']} episodes (runs more than {EPISODE_GAP} sessions "
             f"apart) over {sample['weeks']} distinct ISO entry weeks. One shock day fires "
             "every member with a bar, so the screen tests the episodes, not N, and the "
             f"N >= {verdict.MIN_N} clause cannot see that. The week-clustered percentile "
             "bootstrap undercovers with this few clusters, so the lower bound is looser "
             "than nominal.", "",
             "| Year | shock days | kept events |", "|---|---|---|"]
    lines += [f"| {year} | {shocks} | {kept} |"
              for year, (shocks, kept) in sample["per_year"].items()]
    return lines


def _render_overlap(overlap) -> list:
    head = f"Official ΔExpR {_fmt(overlap['official'])}R over N = {overlap['n']}."
    v = overlap["restricted"]
    if v is None:
        return ["### 2. Null overlap", "", head + " Restricted null not run."]
    return ["### 2. Null overlap", "",
            head + f" With the null pool restricted to bars at least {overlap['cap']} "
            "sessions from any shock day (same seed, K and cap; an event left with fewer "
            f"than 5 candidates drops out): ΔExpR {_fmt(v.delta_exp_r)}R, 95% "
            f"week-clustered interval {_fmt(v.ci_low)}R to {_fmt(v.ci_high)}R, N = {v.n}. "
            "The gap shows how far pre-shock and post-shock null races moved the "
            "official figure."]


def _split_row(label: str, v) -> str:
    if v is None:
        return f"| {label} | 0 | n/a | n/a |"
    return (f"| {label} | {v.n} | {_fmt(v.delta_exp_r)}R | "
            f"{_fmt(v.ci_low)}R to {_fmt(v.ci_high)}R |")


def _render_selloff(selloff) -> list:
    mean = selloff["shock_mean"]
    mean_text = "n/a" if mean is None else f"{100.0 * mean:+.2f}%"
    return ["### 3. SPY selloff split", "",
            f"SPY's own 5-day return on the shock days: {selloff['shock_down']} below 0, "
            f"{selloff['shock_up']} at or above 0, mean {mean_text}.", "",
            "| SPY 5-day return at the signal day | N | ΔExpR | 95% interval |",
            "|---|---|---|---|",
            _split_row("< 0", selloff["down"]), _split_row(">= 0", selloff["up"]), "",
            f"Kept events with no SPY 5-day return at their signal day: "
            f"{selloff['undefined']}. A pass carried by the < 0 half is a mean-reversion "
            "effect, not an intermarket one."]


def _render_concentration(conc) -> list:
    top_two = sum(row[2] for row in conc["rows"][:2]) if conc["rows"] else None
    lines = ["### 4. Concentration by shock episode", "",
             "Each episode's contribution to ΔExpR = (sum of its d) / N, largest first. "
             f"ΔExpR {_fmt(conc['delta'])}R; the two largest episodes add "
             f"{_fmt(top_two)}R.", "",
             "| Episode (signal days) | kept events | contribution to ΔExpR |",
             "|---|---|---|"]
    lines += [f"| {label} | {n} | {_fmt(share)}R |" for label, n, share in conc["rows"]]
    return lines + ["", "Kept events whose signal day is no shock day (a gap in the "
                        f"stock's own calendar): {conc['unmatched']}."]


def _render_family(screen_q) -> list:
    return ["### 5. Multiple comparisons", "",
            f"BH q = {_fmt(screen_q, '.4f')} across the `screen-v1` family (this idea "
            "plus every earlier screen row); the head line's q runs across the whole "
            "ledger. Reported, never gating."]


def render(diag, data, *, context_start: str, window_start: str, screen_q, scope: str) -> list:
    """The § 5 section as lines; the caller joins them like every other section."""
    parts = [_render_data(data, context_start, window_start),
             _render_sample(diag["sample"]), _render_overlap(diag["overlap"]),
             _render_selloff(diag["selloff"]),
             _render_concentration(diag["concentration"]),
             _render_family(screen_q), ["### 6. Scope", "", scope]]
    lines = [HEADING, "", "None of these lines is a clause of the verdict above; the "
             "verdict is computed exactly as for every other screen."]
    for part in parts:
        lines += [""] + part
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py`
Expected: PASS (22 tests).

If `test_the_selloff_split_reads_spy_r5_at_each_signal_day` fails on `shock_up`, check the fixture, not the code: SPY closes rise 0.1 a bar except bar 460 (90.0), so r5 is positive at 450, 451, 452 and 600 and negative only at 460.

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (the module lives under `swingbot/core/backtesting/`, and nothing outside imports it).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/screen/diagnostics.py | head`
Expected: no output (the largest, `_concentration`, is rank A/B).

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/screen/diagnostics.py tests/backtesting/screen/test_diagnostics.py
git -C $WT commit -m "feat(screen): intermarket diagnostics module, printed beside the verdict, never gating (V174-7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — Runner wiring

### Task V174-8: Restricted null per ticker; diagnostics, context data and scope wired into the results doc and ledger row

**Model:** opus — touches the matched-null path that feeds the verdict, under byte-identity pins

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (`TickerScreen` :92-100, `_books` :120-131, `screen_ticker` :156-176, `render_results` :466-474, `hypothesis` :485-494, `publish` :514-531, `main` :543-560, as left by V174-3/V174-4; line numbers drift, anchor on the text)
- Modify: `tests/backtest_scripts/test_screen_context_runner.py` (created by V174-3, extended by V174-4)
- Test (run, never edited): `tests/backtest_scripts/test_screen_idea.py` (the `FIXED_DOC` / `FIXED_HYPOTHESIS` pins at :411 and :417)

**Interfaces:**
- Consumes (V174-1): `context.near_mask(raw: np.ndarray, cap: int) -> np.ndarray` (True at i when some True p has |i − p| < cap).
- Consumes (V174-2): `context.ContextData(frames, calendar, records)`.
- Consumes (V174-3): `raw_events(idea, df, context)`, `screen_ticker(..., context: Mapping | None = None)`, test helpers `_digest(screen) -> str` (hashes the eight pre-v174 `TickerScreen` fields only, so the new `restricted` field never moves it) and `_ctx_cache(tmp_path, *, tickers=("AAA", "BBB"), context=("TLT", "UUP")) -> Path` (`tmp_path / "cache"`: stock CSVs from 2010-01-04, `SPY.csv` and the context CSVs from 2009-06-01 on one business-day calendar; also writes `tmp_path / "membership.csv"`), `ALWAYS`, autouse `fast_bootstrap`.
- Consumes (V174-4): `screen_idea.CONTEXT_START`; CLI `--context-hashes`; `_context_step(args, idea) -> tuple[ContextData | None, str | None]`, whose `ContextData` `main` holds before `screen_universe`; `write_hashes(records, path)` called inside `publish` between the doc write and the ledger append.
- Consumes (V174-6): `IDEAS["bond_spike_rebound"]`, `IDEAS["dollar_drop"]`.
- Consumes (V174-7): `diagnostics.compute(idea, events, restricted, data, *, event_start, event_end) -> dict`, `diagnostics.render(diag, data, *, context_start, window_start, screen_q, scope) -> list[str]`, `diagnostics.screen_family_q(rows, row, instrument) -> float | None`, `diagnostics.scope_sentence(idea) -> str`, `diagnostics.HEADING`.
- Produces: `TickerScreen.restricted: list | None = None`; `_books(idea, ticker, df, ctx, costs, exclude: np.ndarray | None = None)`; `_restricted(idea, ticker, df, ctx, costs) -> list | None`; `_restricted_pairs(screens) -> list | None`; `with_diagnostics(summary: dict, screens, idea, data, *, end: str) -> dict`; `_context_hypothesis(idea) -> str`; `_context_run(run: dict, idea, rows: list, row: dict, data) -> dict`; `_render_context(idea, summary, run) -> list`. Nothing later consumes them except the two shots, through `main`.

**What must not move.** `summary["verdict"]` is computed by `summarise` exactly as today; `with_diagnostics` returns a new dict with one more key (`"context"`) and the same verdict object. An idea with `context == ()` gets `restricted=None`, one `matched_null` call per ticker, no `"context"` key, the same `run` dict, the same doc and the same hypothesis, byte for byte. The restricted pass uses the same seed (`null.null_seed(idea.name, ticker)`), the same `null.K` and the same cap; its smaller pool changes which bars are drawn and may drop events with fewer than 5 candidates. That is what it measures.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_screen_context_runner.py`. V174-3 created the file with `hashlib`, `json`, `numpy as np`, `pandas as pd`, `pytest`, `screen_idea`, `verdict`, `IDEAS`, `random_walk`, `ALWAYS`, the autouse 500-resample `fast_bootstrap` fixture, and `_ctx_cache` (which also writes `tmp_path / "membership.csv"`). Reuse them; add only the imports below:

```python
# --- V174-8: restricted null, diagnostics, scope ----------------------------

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import diagnostics, null  # noqa: E402

def _tlt_like(n=2600, seed=21):
    """A context series on the same business days as random_walk(n)."""
    return random_walk(n, seed=seed)


def _spy_matched_null(monkeypatch):
    calls = []
    real = null.matched_null

    def spy(df, event_pos, eligible, k, seed, **kw):
        calls.append({"eligible": np.asarray(eligible, dtype=bool).copy(), "k": k,
                      "seed": list(seed), "cap": kw["cap"]})
        return real(df, event_pos, eligible, k, seed, **kw)

    monkeypatch.setattr(screen_idea.null, "matched_null", spy)
    return calls


def test_a_context_idea_draws_a_second_null_without_bars_near_a_shock(monkeypatch):
    df, tlt = random_walk(2600), _tlt_like()
    idea = IDEAS["bond_spike_rebound"]
    raw = np.asarray(idea.events(df, {"TLT": tlt}), dtype=bool)
    assert raw.any()                                       # non-vacuous: shocks exist
    calls = _spy_matched_null(monkeypatch)
    screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, context={"TLT": tlt})
    assert len(calls) == 2                                 # official, then restricted
    official, restricted = calls
    assert (restricted["seed"], restricted["k"], restricted["cap"]) == \
        (official["seed"], official["k"], official["cap"]) == \
        (null.null_seed(idea.name, "AAA"), null.K, idea.time_cap_bars)
    near = pit.near_mask(raw, idea.time_cap_bars)
    assert np.array_equal(restricted["eligible"], official["eligible"] & ~near)
    assert restricted["eligible"].sum() < official["eligible"].sum()


def test_an_old_idea_draws_one_null_and_keeps_no_restricted_book(monkeypatch):
    calls = _spy_matched_null(monkeypatch)
    out = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", random_walk(2600),
                                    ALWAYS)
    assert len(calls) == 1
    assert out.restricted is None


def test_restricted_pairs_race_the_same_events_as_the_official_book():
    df, tlt = random_walk(2600), _tlt_like()
    out = screen_idea.screen_ticker(IDEAS["bond_spike_rebound"], "AAA", df, ALWAYS,
                                    context={"TLT": tlt})
    assert out.events and out.restricted is not None
    official = {row["entry_date"]: row["r_event"] for row in out.events}
    for row in out.restricted:
        assert set(row) == {"entry_date", "r_event", "r_null"}
        assert official[row["entry_date"]] == row["r_event"]   # same race, other null


def test_exclude_cuts_the_null_pool_and_nothing_else():
    df, tlt = random_walk(2600), _tlt_like()
    idea = IDEAS["bond_spike_rebound"]
    atr = screen_idea.indicators.atr(df)
    sma = screen_idea.indicators.sma(df["Close"], 200)
    ctx = {"raw": np.asarray(idea.events(df, {"TLT": tlt}), dtype=bool),
           "member": np.ones(len(df), dtype=bool),
           "warm": screen_idea.race.warm_mask(atr, sma)
           & (df.index >= pd.Timestamp(screen_idea.EVENT_START)),
           "atr": atr, "trend": null.trend_state(df, sma)}
    costs = {"slippage_bps": None, "commission": None}
    plain = screen_idea._books(idea, "AAA", df, ctx, costs)
    no_cut = screen_idea._books(idea, "AAA", df, ctx, costs,
                                exclude=np.zeros(len(df), dtype=bool))
    assert np.array_equal(plain[0].event_pos, no_cut[0].event_pos)
    assert np.array_equal(plain[2].null_mean_r, no_cut[2].null_mean_r)
    cut = screen_idea._books(idea, "AAA", df, ctx, costs,
                             exclude=pit.near_mask(ctx["raw"], idea.time_cap_bars))
    assert set(cut[0].event_pos) <= set(plain[0].event_pos)   # a smaller pool may drop events


def test_the_restricted_pass_is_deterministic():
    df, tlt = random_walk(2600), _tlt_like()
    idea = IDEAS["bond_spike_rebound"]
    first = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, context={"TLT": tlt})
    second = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, context={"TLT": tlt})
    assert first.events == second.events and first.restricted == second.restricted


def _context_data(tlt, spy):
    record = {"ticker": "TLT", "rows": len(tlt), "first": "2010-01-04",
              "last": tlt.index[-1].strftime("%Y-%m-%d"), "fetched": "2026-10-18",
              "sha256": "cd" * 32}
    return pit.ContextData(frames={"TLT": tlt}, calendar=spy, records={"TLT": record})


def test_diagnostics_are_added_beside_the_verdict_never_into_it():
    tlt, spy = _tlt_like(), random_walk(2600, seed=5)
    idea = IDEAS["bond_spike_rebound"]
    screens = [screen_idea.screen_ticker(idea, t, random_walk(2600, seed=s), ALWAYS,
                                         context={"TLT": tlt})
               for s, t in ((1, "AAA"), (2, "BBB"))]
    summary = screen_idea.summarise(screens)
    out = screen_idea.with_diagnostics(summary, screens, idea, _context_data(tlt, spy),
                                       end="2019-12-31")
    assert out["verdict"] is summary["verdict"]
    assert set(out) == set(summary) | {"context"}
    assert "context" not in summary                        # the input is not mutated
    assert set(out["context"]) == {"sample", "overlap", "selloff", "concentration"}
    assert out["context"]["overlap"]["restricted"] is not None


def test_an_old_idea_summary_passes_through_untouched():
    screens = [screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", random_walk(2600),
                                         ALWAYS)]
    summary = screen_idea.summarise(screens)
    assert screen_idea.with_diagnostics(summary, screens, IDEAS["turn_of_month"], None,
                                        end="2019-12-31") is summary


def test_restricted_pairs_pool_over_tickers_and_are_none_for_an_old_idea():
    class S:
        def __init__(self, restricted):
            self.restricted = restricted
    assert screen_idea._restricted_pairs([S(None), S(None)]) is None
    assert screen_idea._restricted_pairs([S([{"a": 1}]), S([]), S([{"b": 2}])]) == \
        [{"a": 1}, {"b": 2}]


def test_a_context_idea_hypothesis_carries_the_scope_sentence():
    idea = IDEAS["bond_spike_rebound"]
    text = screen_idea.hypothesis(idea)
    assert text.startswith(
        "bond_spike_rebound: TLT 5-day return z >= +2.0 vs its trailing 252 values; "
        "fixed 1.5/3.0 ATR race vs K=20 matched null, cap 10, PIT S&P 500 2010-2019, "
        "context TLT adjusted closes from 2009-06-01, after costs (v174 intermarket "
        "screen). ")
    assert text.endswith(diagnostics.scope_sentence(idea))
    v = screen_idea.verdict.Verdict("SCREEN-FAIL", 412, 0.01, -0.02, 0.04, 0.3, 4, {},
                                    {"exp_r": False, "ci": False, "years": False, "n": True})
    row = screen_idea.ledger_row(idea, v, "docs/x.md", "2026-10-19")
    stats.validate_ledger_row(row)                         # no new field: scope lives in hypothesis
    assert (row["instrument"], row["data_source"]) == ("screen-v1", "yfinance")


def test_the_run_dict_of_an_old_idea_is_unchanged():
    run = {"ledger_id": "screen-gap_volume", "q": 0.1}
    assert screen_idea._context_run(run, IDEAS["gap_volume"], [], {"id": "x"}, None) is run


def test_the_run_dict_of_a_context_idea_carries_the_screen_family_q():
    rows = [{"id": "v1-a", "instrument": "v1", "p": 0.001},
            {"id": "v1-b", "instrument": "v1", "p": 0.9},
            {"id": "screen-a", "instrument": "screen-v1", "p": 0.04}]
    row = {"id": "screen-bond_spike_rebound", "instrument": "screen-v1", "p": 0.03}
    out = screen_idea._context_run({"q": 0.5}, IDEAS["bond_spike_rebound"], rows, row, "DATA")
    assert out["context"] == "DATA" and out["q"] == 0.5
    assert out["screen_q"] == pytest.approx(0.04)


def _ctx_argv(tmp_path, cache, idea, *extra):
    return ["--idea", idea, "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-10-19",
            "--context-hashes", str(tmp_path / "hashes.json"), *extra]


def test_a_context_run_writes_the_diagnostics_section_and_the_scope(tmp_path):
    cache = _ctx_cache(tmp_path)
    assert screen_idea.main(_ctx_argv(tmp_path, cache, "bond_spike_rebound")) == 0
    text = (tmp_path / "results" / "2026-10-19-screen-bond_spike_rebound.md").read_text(
        encoding="utf-8")
    heading = "## Intermarket diagnostics (printed, never gating)"
    assert text.index("## Forward drift") < text.index(heading)   # the last section
    for needle in ("### 1. Effective sample", "### 2. Null overlap",
                   "### 3. SPY selloff split", "### 4. Concentration by shock episode",
                   "### 5. Multiple comparisons", "### 6. Scope", "undercovers",
                   "loaded from 2009-06-01", "stock window starts 2010-01-01",
                   "across the `screen-v1` family", "across the ledger",
                   "closes exactly this frozen definition",
                   hashlib.sha256((cache / "TLT.csv").read_bytes()).hexdigest()):
        assert needle in text, needle
    rows = stats.load_ledger(tmp_path / "ledger.jsonl")
    assert [row["id"] for row in rows] == ["screen-bond_spike_rebound"]
    assert rows[0]["hypothesis"].endswith(
        diagnostics.scope_sentence(IDEAS["bond_spike_rebound"]))
    assert f"-> {rows[0]['verdict']}" in text.splitlines()[0]
    pinned = json.loads((tmp_path / "hashes.json").read_text(encoding="utf-8"))
    assert set(pinned) == {"TLT", "UUP"}


def test_a_context_dry_run_prints_the_diagnostics_and_writes_nothing(tmp_path, capsys):
    cache = _ctx_cache(tmp_path)
    assert screen_idea.main(_ctx_argv(tmp_path, cache, "dollar_drop", "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "## Intermarket diagnostics (printed, never gating)" in out
    assert "UUP 5-day return z <= -2.0" in out
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "hashes.json").exists()
    assert not (tmp_path / "results").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: the V174-3/V174-4 tests pass; the new ones FAIL (`AttributeError: ... has no attribute 'with_diagnostics'`, `'_restricted_pairs'`, `'_context_run'`, `TickerScreen` has no `restricted`, one `matched_null` call where two are expected, the hypothesis has no scope).

- [ ] **Step 3: Import the diagnostics module**

In `scripts/backtest/screen_idea.py`, after the existing `from swingbot.core.backtesting.screen ...` import lines (V174-4 may have added `context` there; leave them), add:

```python
from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import diagnostics  # noqa: E402
```

`pit` is a separate alias on purpose: `screen_ticker` and `screen_universe` have a parameter named `context`, which shadows a module of that name inside them.

- [ ] **Step 4: Add the `restricted` field and the `exclude` pool cut**

Replace the `TickerScreen` dataclass's last field line:

```python
    stressed: list | None = None                          # v163: trail only, 2 x slippage pairs
```

with:

```python
    stressed: list | None = None                          # v163: trail only, 2 x slippage pairs
    restricted: list | None = None                        # v174: context only, null pool off shock windows
```

Replace `_books` with:

```python
def _books(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict,
           exclude: np.ndarray | None = None):
    """The kept event book, its counters and its matched null at one cost
    setting, both raced under the idea's own shape (v163). ``exclude`` drops
    bars from the null pool only (v174 restricted null); the event book and
    the seed are the same either way."""
    cap, shape = idea.time_cap_bars, idea.race_shape
    booked, counts = race.run_book(df, ctx["raw"], cap, member=ctx["member"],
                                   warm=ctx["warm"], atr=ctx["atr"], shape=shape, **costs)
    eligible = null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], cap)
    if exclude is not None:
        eligible = eligible & ~exclude
    draw = null.matched_null(df, booked.event_pos, eligible,
                             null.K, null.null_seed(idea.name, ticker), cap=cap,
                             atr=ctx["atr"], trend=ctx["trend"], shape=shape, **costs)
    counts["dropped_no_match"] = draw.dropped_no_match
    return booked.take(np.isin(booked.event_pos, draw.event_pos)), counts, draw
```

- [ ] **Step 5: Add `_restricted` and call it from `screen_ticker`**

Insert after `_stressed`:

```python
def _restricted(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Context ideas only (v174 § 5.2): every event raced again against a
    null pool without the bars closer than CAP sessions to any shock day.
    For a context idea the raw mask IS the shock-day mask on this ticker's
    dates. Same seed, K and cap; printed, never gating."""
    if not idea.context:
        return None
    near = pit.near_mask(ctx["raw"], idea.time_cap_bars)
    kept, _, draw = _books(idea, ticker, df, ctx, costs, exclude=near)
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, df.index, kept, draw.null_mean_r)]
```

In `screen_ticker`, replace the last line of the `TickerScreen(...)` call:

```python
        stressed=_stressed(idea, ticker, df, ctx, costs))
```

with:

```python
        stressed=_stressed(idea, ticker, df, ctx, costs),
        restricted=_restricted(idea, ticker, df, ctx, costs))
```

- [ ] **Step 6: Add the diagnostics beside the summary**

Insert after `summarise` (leave `summarise` itself unchanged):

```python
def _restricted_pairs(screens):
    """Every ticker's restricted-null pairs, pooled; None for an old idea."""
    if all(screen.restricted is None for screen in screens):
        return None
    return [row for screen in screens if screen.restricted for row in screen.restricted]


def with_diagnostics(summary: dict, screens, idea: Idea, data, *, end: str) -> dict:
    """The summary plus ``"context"`` (v174 § 5) for a context idea; the same
    dict, untouched, for any other. The verdict object is never rebuilt."""
    if not idea.context or data is None:
        return summary
    diag = diagnostics.compute(idea, summary["events"], _restricted_pairs(screens), data,
                               event_start=EVENT_START, event_end=end)
    return {**summary, "context": diag}
```

- [ ] **Step 7: The context hypothesis**

Replace `hypothesis` with:

```python
def _context_hypothesis(idea) -> str:
    """v174: the fixed-race text naming the context series, then the scope
    sentence (the ledger has no note field; validate_ledger_row rejects one)."""
    return (f"{idea.name}: {idea.summary}; fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} "
            f"ATR race vs K={null.K} matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
            f"2010-2019, context {', '.join(idea.context)} adjusted closes from "
            f"{CONTEXT_START}, after costs (v174 intermarket screen). "
            + diagnostics.scope_sentence(idea))


def hypothesis(idea) -> str:
    """The ledger hypothesis, naming the shape and cap; the fixed text is
    today's, byte for byte."""
    if idea.context:
        return _context_hypothesis(idea)
    if idea.race_shape == "trail":
        return (f"{idea.name}: {idea.summary}; chandelier {trail.TRAIL_ATR} ATR trail race, "
                f"initial stop {race.STOP_ATR} ATR, cap {idea.time_cap_bars} vs K={null.K} "
                "matched null, PIT S&P 500 2010-2019, after costs (v163 trail screen)")
    return (f"{idea.name}: {idea.summary}; fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race vs K={null.K} "
            f"matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
            "2010-2019, after costs (v140 screen)")
```

The two old branches are copied unchanged from today's function; `FIXED_HYPOTHESIS` pins the fixed one.

- [ ] **Step 8: Render the section and pass the context to it**

Insert before `render_results`:

```python
def _render_context(idea, summary, run) -> list:
    """v174 § 5, the last section of a context idea's doc."""
    return diagnostics.render(summary["context"], run["context"],
                              context_start=CONTEXT_START, window_start=run["start"],
                              screen_q=run["screen_q"],
                              scope=diagnostics.scope_sentence(idea))
```

Replace `render_results` with:

```python
def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v),
                _render_arms(summary, race.SHAPE_OUTCOMES[idea.race_shape])]
    if idea.race_shape == "trail":
        sections.append(_render_trail(summary, run))
    sections += [_render_years(v), _render_drift(summary)]
    if idea.context:
        sections.append(_render_context(idea, summary, run))
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"
```

Insert after `_run_info`:

```python
def _context_run(run: dict, idea, rows, row: dict, data) -> dict:
    """A context idea's run dict also carries its ContextData and the
    screen-family BH q (§ 5.5); any other idea's run dict is returned as is."""
    if not idea.context:
        return run
    return {**run, "context": data,
            "screen_q": diagnostics.screen_family_q(rows, row, INSTRUMENT)}
```

In `publish`, replace the one line

```python
    text = render_results(idea, summary, universe, _run_info(args, q))
```

with

```python
    run = _context_run(_run_info(args, q), idea, rows, row, data)
    text = render_results(idea, summary, universe, run)
```

V174-4 does **not** give `publish` the `ContextData`: its signature stays `publish(args, idea, universe, summary, rows)`, and its hash write is `_pin_context_hashes(args, idea)`, which reads the cache dir itself. So add a keyword parameter `data=None` to `publish` (`def publish(args, idea, universe, summary, rows, data=None)`) and pass it from `main` as `data=data`. Keep V174-4's `_pin_context_hashes(args, idea)` call exactly where it is: after `path.write_text(...)`, before `stats.append_ledger_row(...)`.

In `main`, where `publish` is called, wrap the summary (the `ContextData` from `_context_step` is the same `data` passed to `publish`; it is `None` for an old idea):

```python
    summary = with_diagnostics(summarise(screens, skipped), screens, idea, data, end=args.end)
    return publish(args, idea, universe, summary, rows, data=data)
```

Keep the rest of `main` (V174-4's refusals, `_context_step`, the `context=` passed to `screen_universe`) as it is.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: PASS, every V174-3/V174-4 test included. The real-call-path parity digests for the six old ideas are unchanged: `_digest` hashes only the eight pre-v174 fields, and an old idea gets `restricted=None` anyway. If the parity test fails, the change moved an old idea's book: fix the code, never the digests.

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
Expected: PASS, in particular `test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` and `test_a_fixed_idea_ledger_row_is_unchanged` (an old idea's doc and hypothesis never reach the new branches; `_fixed_doc_inputs` has no `"context"` key and is never asked for one).

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py`
Expected: PASS.

- [ ] **Step 10: Complexity check**

Run: `python -m radon cc -s -n C $WT/scripts/backtest/screen_idea.py | head`
Expected: no output. `_books` B(2), `render_results` A(3), `hypothesis` A(3), `publish`, `main` and `screen_ticker` no higher than V174-4 left them.

- [ ] **Step 11: Commit**

```bash
git -C $WT add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_context_runner.py
git -C $WT commit -m "feat(screen): restricted null per ticker, intermarket diagnostics and scope in the results doc and ledger row (V174-8)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: one commit on the branch; the main tree shows no new change from this task.

