# v230 Plan 1, Part 1 — `SCOPE`, the placebo harness and its CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-3" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A1, A2 `SCOPE`, Testing)
**Index:** [2026-11-16-v230-screen-v2-rescreen_0-index.md](2026-11-16-v230-screen-v2-rescreen_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V230-1..V230-4

What this part builds: the `SCOPE` declaration on ideas (V230-1), the two
no-edge universes (V230-2), the six placebo triggers, the planted drift and
the acceptance arithmetic (V230-3), and the CLI that drives the existing v1
screen pipeline over them (V230-4). Nothing here reads a real idea's outcome;
V230-5 (Part 2) is the first run.

# Phase 1 — the placebo harness

### Task V230-1: `SCOPE` on ideas and the three market-scope declarations

**Model:** sonnet — a frozen-dataclass field, one loader line and registry tests following an existing pattern.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (docstring, constants block after `MODES`, new `_scope_problem`, `Idea` last field + `__post_init__`, `_load`)
- Modify: `swingbot/core/backtesting/screen/ideas/turn_of_month.py`, `.../ideas/bond_spike_rebound.py`, `.../ideas/dollar_drop.py` (one constant each)
- Test: `tests/backtesting/screen/test_ideas_registry.py` (append)

**Interfaces:**
- Consumes: nothing new (`Idea`, `_load`, and the test helpers `_fake_module`, `_events`, `_levels`, `_states` already exist in the registry and its test file).
- Produces: `ideas.SCOPES = ("ticker", "market")`; `Idea.scope: str = "ticker"` as the **last** dataclass field (after `states`); `_scope_problem(scope: str, mode: str, entry: str) -> str | None`; `_load` reads module `SCOPE` (default `"ticker"`); `SCOPE = "market"` in `turn_of_month`, `bond_spike_rebound`, `dollar_drop`; `test_every_registered_idea_pins_its_scope`. V230-3 builds `Idea(..., scope=trigger.scope)`; V230-9 dispatches on `idea.scope`.

Why: spec A2 — a market-wide trigger fires for every member on one date, so
the v2 ticker-scope pool (other tickers on the same date) is empty for it.
Such ideas declare `SCOPE = "market"` and get a trailing same-ticker pool.
`SCOPE` is part of the frozen definition (like `RACE`, `DIRECTION`, `MODE`)
and is pinned per idea. Index decision: a market-scope idea in avoid mode or
with a level entry is refused at registration — the spec defines the market
pool for the next-open edge path only.

The field goes **last** so every positional `Idea(...)` call and the existing
field-order test (`test_mode_and_states_sit_directly_after_context_kind`,
which reads the two fields after `context_kind`) stay valid. `hypothesis()`
in `screen_idea.py` does not print the scope, so every v1 results doc and
ledger text stays byte-identical.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_ideas_registry.py` (the helpers
`_events`, `_levels`, `_states` and `_fake_module` are already defined above
in that file; `dataclasses`, `pytest`, `ideas`, `IDEAS`, `Idea` are already
imported):

```python
MARKET_SCOPE = {"turn_of_month", "bond_spike_rebound", "dollar_drop"}


def test_scopes_and_the_default():
    """v230 A2: SCOPE is part of the frozen definition, default "ticker"."""
    assert ideas.SCOPES == ("ticker", "market")
    assert Idea(name="x", events=_events, time_cap_bars=5).scope == "ticker"


def test_every_registered_idea_pins_its_scope():
    """v230 A2: exactly the three market-wide triggers named by the spec read
    SCOPE = "market"; every other idea (the shock ideas included) is "ticker"."""
    assert {n: i.scope for n, i in IDEAS.items()} == {
        n: ("market" if n in MARKET_SCOPE else "ticker") for n in IDEAS}


def test_scope_is_the_last_field():
    names = [f.name for f in dataclasses.fields(Idea)]
    assert names[-1] == "scope"
    assert names[-3:-1] == ["mode", "states"]


def test_an_unknown_scope_is_refused():
    with pytest.raises(ValueError, match="x: scope 'sector' is not one of"):
        Idea(name="x", events=_events, time_cap_bars=5, scope="sector")


def test_a_market_scope_avoid_idea_is_refused():
    with pytest.raises(ValueError, match="market-scope idea in avoid mode is not built in v230"):
        Idea(name="x", events=_events, time_cap_bars=20, mode="avoid", states=_states,
             scope="market")


def test_a_market_scope_level_idea_is_refused():
    with pytest.raises(ValueError,
                       match="market-scope idea with a level entry is not built in v230"):
        Idea(name="x", events=_events, time_cap_bars=20, direction="short",
             entry="level", levels=_levels, scope="market")


def test_a_market_scope_edge_idea_on_the_next_open_is_accepted():
    idea = Idea(name="x", events=_events, time_cap_bars=4, scope="market")
    assert (idea.scope, idea.mode, idea.entry) == ("market", "edge", "next_open")


@pytest.mark.parametrize("scope, mode, entry, expected", [
    ("ticker", "edge", "next_open", None),
    ("ticker", "avoid", "next_open", None),
    ("ticker", "edge", "level", None),
    ("market", "edge", "next_open", None),
    ("market", "avoid", "next_open", "a market-scope idea in avoid mode is not built in v230"),
    ("market", "edge", "level", "a market-scope idea with a level entry is not built in v230"),
    ("both", "edge", "next_open", "scope 'both' is not one of ('ticker', 'market')"),
])
def test_scope_problem_table(scope, mode, entry, expected):
    assert ideas._scope_problem(scope, mode, entry) == expected


def test_load_reads_scope_and_defaults_to_ticker(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_scope_default", CAP=10)
    market = _fake_module(monkeypatch, "fake_scope_market", CAP=4, SCOPE="market")
    assert ideas._load(plain).scope == "ticker"
    assert ideas._load(market).scope == "market"


def test_load_refuses_an_unknown_scope(monkeypatch):
    bad = _fake_module(monkeypatch, "fake_scope_bad", CAP=4, SCOPE="world")
    with pytest.raises(ValueError, match="scope 'world'"):
        ideas._load(bad)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'SCOPES'` and
`TypeError: Idea.__init__() got an unexpected keyword argument 'scope'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/screen/ideas/__init__.py`:

1. Append to the module docstring, after the v214 paragraph:

```text
v230: a module may also export SCOPE ("ticker" default, or "market"). A
"market" idea fires for every member on one date (a calendar or an
intermarket trigger); the v2 null draws its pool from the same ticker's
trailing sessions instead of other tickers on the same date (spec v230 A2).
A market-scope idea is an edge idea entered at the next open. A changed
SCOPE is a new idea with a new name.
```

2. After the `MODES = ("edge", "avoid")` block add:

```python
#: v230: "ticker" (pool = other tickers on the same date) or "market" (pool =
#: the same ticker's trailing sessions; triggers that fire for every member at once).
SCOPES = ("ticker", "market")
```

3. After `_mode_problem` add:

```python
def _scope_problem(scope: str, mode: str, entry: str) -> str | None:
    """v230: an unknown scope, or a market-scope idea on a path the v2 null
    does not build (avoid mode, level entry), is refused at registration."""
    if scope not in SCOPES:
        return f"scope {scope!r} is not one of {SCOPES}"
    if scope == "market" and mode == "avoid":
        return "a market-scope idea in avoid mode is not built in v230"
    if scope == "market" and entry == "level":
        return "a market-scope idea with a level entry is not built in v230"
    return None
```

4. In `class Idea`, add the field after `states` (it must stay the last field):

```python
    states: Callable[[pd.DataFrame], pd.DataFrame] | None = None
    scope: str = "ticker"
```

and replace the first statement of `__post_init__` with:

```python
    def __post_init__(self):
        scope = _scope_problem(self.scope, self.mode, self.entry)
        problem = (_side_problem(self) or _shape_problem(self)
                   or _context_problem(self) or _mode_problem(self)
                   or (scope and f"{self.name}: {scope}"))
        if problem:
            raise ValueError(problem)
```

(the three `object.__setattr__` lines below it stay as they are).

5. In `_load`, add the scope argument so the call ends:

```python
                mode=getattr(module, "MODE", "edge"),
                states=getattr(module, "states", None),
                scope=getattr(module, "SCOPE", "ticker"))
```

In each of `turn_of_month.py`, `bond_spike_rebound.py` and `dollar_drop.py`
add, directly after the `CAP = ...` line:

```python
#: v230: fires for every member on the same date; the v2 null draws from this
#: ticker's trailing sessions (spec v230 A2).
SCOPE = "market"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS, 0 failed.

Then the neighbours that build or load ideas:
Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_turn_of_month.py`
Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py`
Expected: PASS (the checkpoint manifest hashes `params`, not the field set, so v1 checkpoints are unaffected).

Complexity: `python scripts/dev/complexity_gate.py` — `__post_init__` and `_scope_problem` stay well under 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/__init__.py swingbot/core/backtesting/screen/ideas/turn_of_month.py swingbot/core/backtesting/screen/ideas/bond_spike_rebound.py swingbot/core/backtesting/screen/ideas/dollar_drop.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v230): SCOPE on screen ideas, three market-scope declarations"
```

### Task V230-2: Placebo universes: `gbm` and `shuffled`

**Model:** opus — a synthetic-market generator whose reproducibility and no-edge construction the whole stop gate rests on.

This ledger row is split in two (task size cap): **V230-2** builds the
price-path side (seeds, calendar, ATR% levels, the regime chain and the
`gbm` path); **V230-2b** writes universes to disk (index, layout, `gbm`
universe, `shuffled` universe). Together they produce the ledger row's
symbols.

**Files:**
- Create: `swingbot/core/backtesting/screen/placebo.py`
- Test: `tests/backtesting/screen/test_placebo_universes.py`

**Interfaces:**
- Consumes: `swingbot.core.backtesting.screen.indicators.atr`; `swingbot.core.backtesting.screen.context.CONTEXT_ONLY_STEMS` (both exist).
- Produces: `PLACEBO_SEED = 42`; `GBM_TICKERS = 200`; `INDEX_TICKER = "SPY"`; `MEMBERSHIP_FILE = "membership.csv"`; `MANIFEST_FILE = "universe.json"`; `OHLCV`; `ticker_seed(ticker, base=PLACEBO_SEED) -> list` (`[base, zlib.crc32(ticker)]`); `read_frame(path) -> pd.DataFrame` (V230-2b, V230-3 use it); `trading_calendar(spy_csv, start, end) -> pd.DatetimeIndex`; `atr_pct_quartiles(cache_dir, calendar, tickers=None) -> tuple[float, float, float, float]`; `market_states(calendar, seed) -> np.ndarray` (bool, True = stressed); `gbm_frame(ticker, calendar, *, level, stressed, seed=PLACEBO_SEED) -> pd.DataFrame`. `gbm_frame` carries an optional `seed` keyword beyond the ledger's signature so `gbm_universe(seed=...)` (V230-2b) reaches it; the ledger's call shape still works. `_source_files(cache_dir, tickers=None)` and `_on_calendar(path, calendar)` are reused by V230-2b.

Why: spec A1 — a universe with no edge by construction, on the real trading
calendar. Builder choices fixed here (spec "Left to the builder"):

- **`gbm` volatility.** Calm daily sd `level / ATR_PER_SIGMA`, times
  `STRESS_MULT = 2` when stressed. Stressed = the ticker's own two-state
  Markov chain (enter 0.02, exit 0.10) OR the shared market chain, so
  volatility clusters and ATR14 lags it.
- **`gbm` intraday range model.** Overnight gap sd `0.4 × sd`, open-to-close
  sd `√(1 − 0.16) × sd`, each lognormal with mean `−sd²/2` (a martingale: a
  long trade's expected gross R is zero); high and low are `max/min(open,
  close)` widened by `|N(0, 0.5 × intraday sd)|`. `ATR_PER_SIGMA = 1.9` was
  fitted by simulating this model (median ATR14 % of close / calm sd =
  1.89 ± 0.06 over 20 seeds of 2,516 sessions); a test pins the fit within
  ±15%.
- **`gbm` levels.** The cached universe's per-ticker median ATR% at the
  12.5/37.5/62.5/87.5 percentiles (the midpoints of its quartiles).
- **Source files.** Index (`SPY`), context-only stems
  (`CONTEXT_ONLY_STEMS`) and `^`/`_`-prefixed files are never tickers.

`placebo.py` holds no date literal: the calendar is always a parameter
(scripts pass `screen_idea.WINDOW_START` / `WINDOW_END`).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_placebo_universes.py` (`hashlib` and
`json` are imported now for the V230-2b tests appended to this file):

```python
"""v230 A1: the placebo universes reproduce from their seeds and carry no
serial structure (shuffled) or drift (gbm) by construction."""
import hashlib
import json
import zlib

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, placebo
from tests.backtesting.screen.helpers import random_walk

CAL = pd.bdate_range("2010-01-04", periods=600)


def _source(tmp_path, n=600, tickers=("AAA", "BBB", "CCC")):
    """A fake cache: three tickers, SPY, two context-only stems, a coverage file."""
    src = tmp_path / "src"
    src.mkdir()
    for seed, t in enumerate(tickers, start=1):
        random_walk(n, seed=seed).to_csv(src / f"{t}.csv", index_label="Date")
    random_walk(n, seed=99).to_csv(src / "SPY.csv", index_label="Date")
    for stem in ("^VIX", "BREADTH_ATR1"):
        random_walk(n, seed=98).to_csv(src / f"{stem}.csv", index_label="Date")
    (src / "_coverage_sp500_pit.json").write_text("{}", encoding="utf-8")
    return src


def test_ticker_seed_is_the_base_and_the_crc_of_the_name():
    assert placebo.ticker_seed("G001") == [42, zlib.crc32(b"G001")]
    assert placebo.ticker_seed("G001", base=7) == [7, zlib.crc32(b"G001")]


def test_trading_calendar_cuts_and_sorts(tmp_path):
    src = _source(tmp_path)
    cal = placebo.trading_calendar(src / "SPY.csv", "2010-02-01", "2010-03-31")
    assert cal[0] == pd.Timestamp("2010-02-01") and cal[-1] == pd.Timestamp("2010-03-31")
    assert cal.is_monotonic_increasing and cal.is_unique
    with pytest.raises(ValueError, match="no session"):
        placebo.trading_calendar(src / "SPY.csv", "2030-01-01", "2030-12-31")


def test_read_frame_keeps_ohlcv_sorted_and_unique(tmp_path):
    df = random_walk(5, seed=1)
    shuffled = pd.concat([df.iloc[[3, 1, 0, 2, 4]], df.iloc[[1]]])
    shuffled.assign(Extra=1).to_csv(tmp_path / "X.csv", index_label="Date")
    out = placebo.read_frame(tmp_path / "X.csv")
    assert list(out.columns) == list(placebo.OHLCV)
    assert out.index.is_monotonic_increasing and out.index.is_unique and len(out) == 5


def test_market_states_are_seeded_and_switch():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    a, b = placebo.market_states(cal, 42), placebo.market_states(cal, 42)
    assert a.dtype == bool and np.array_equal(a, b)
    assert not np.array_equal(a, placebo.market_states(cal, 43))
    assert 0.05 < a.mean() < 0.35


def test_gbm_frame_is_seeded_per_ticker_and_consistent():
    stressed = np.zeros(len(CAL), dtype=bool)
    one = placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed)
    pd.testing.assert_frame_equal(one, placebo.gbm_frame("G001", CAL, level=0.02,
                                                         stressed=stressed))
    other = placebo.gbm_frame("G002", CAL, level=0.02, stressed=stressed)
    assert not one["Close"].equals(other["Close"])
    assert not one["Close"].equals(
        placebo.gbm_frame("G001", CAL, level=0.02, stressed=stressed, seed=7)["Close"])
    assert list(one.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert (one["High"] >= one[["Open", "Close"]].max(axis=1)).all()
    assert (one["Low"] <= one[["Open", "Close"]].min(axis=1)).all()
    assert one.index.equals(CAL)


def test_gbm_median_atr_pct_lands_on_its_level():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = placebo.market_states(cal, 42)
    ratios = []
    for i in range(10):
        df = placebo.gbm_frame(f"G{i:03d}", cal, level=0.02, stressed=stressed)
        ratios.append(np.nanmedian(indicators.atr(df) / df["Close"]) / 0.02)
    assert 0.85 < np.mean(ratios) < 1.15


def test_gbm_is_driftless():
    cal = pd.bdate_range("2010-01-04", periods=2516)
    stressed = np.zeros(len(cal), dtype=bool)
    gross = [df["Close"].iloc[-1] / df["Close"].iloc[0]
             for df in (placebo.gbm_frame(f"G{i:03d}", cal, level=0.015, stressed=stressed)
                        for i in range(60))]
    assert abs(np.mean(gross) - 1.0) < 0.25


def test_atr_pct_quartiles_skip_index_and_context_files(tmp_path):
    src = _source(tmp_path)
    assert [p.stem for p in placebo._source_files(src)] == ["AAA", "BBB", "CCC"]
    q = placebo.atr_pct_quartiles(src, CAL)
    assert len(q) == 4 and list(q) == sorted(q) and all(v > 0 for v in q)
    only = placebo.atr_pct_quartiles(src, CAL, tickers=["AAA"])
    assert len(set(only)) == 1
    with pytest.raises(ValueError, match="no ATR%"):
        placebo.atr_pct_quartiles(src, CAL, tickers=["ZZZ"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_universes.py`
Expected: FAIL — `ImportError: cannot import name 'placebo'`.

- [ ] **Step 3: Implement**

Create `swingbot/core/backtesting/screen/placebo.py` (V230-2b appends the
writers; `hashlib` and `json` are imported now for them):

```python
"""v230 A1: the placebo harness -- universes with no edge by construction.

Each universe is a screen cache directory on a given trading calendar:
<T>.csv (Date,Open,High,Low,Close,Volume), membership.csv (one span per
ticker from the first session, open end), a synthetic SPY.csv built as the
equal-weight index after generation, and universe.json (written last: its
presence marks a complete universe).

gbm: driftless (martingale) geometric random walks. Daily sd = level /
ATR_PER_SIGMA, x STRESS_MULT while stressed; stressed = the ticker's own
two-state Markov chain OR one shared market chain, so volatility clusters
and ATR14 lags it. Overnight gap and open-to-close legs split the variance
(GAP_SHARE); wicks widen max/min(open, close). ATR_PER_SIGMA (1.9) was
fitted by simulating this model: median ATR14 % of close / calm sd = 1.89.
One seed per ticker, [seed, crc32(ticker)], so a ticker's path does not
depend on the ticker count.

shuffled: the real cached bars with whole trading days 1..n-1 permuted, one
permutation shared by every ticker. Each day carries its close-to-close
return, open/high/low-to-close ratios and volume, so each day's
cross-section survives and no serial structure does.

No date literal lives here: the calendar is always a parameter.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.context import CONTEXT_ONLY_STEMS

PLACEBO_SEED = 42
GBM_TICKERS = 200
INDEX_TICKER = "SPY"
MEMBERSHIP_FILE = "membership.csv"
MANIFEST_FILE = "universe.json"
OHLCV = ("Open", "High", "Low", "Close", "Volume")

STRESS_ENTER = 0.02     # P(calm -> stressed) per session
STRESS_EXIT = 0.10      # P(stressed -> calm) per session
STRESS_MULT = 2.0
GAP_SHARE = 0.4         # overnight gap sd as a share of the daily sd
WICK_SHARE = 0.5        # wick sd as a share of the open-to-close sd
ATR_PER_SIGMA = 1.9     # median ATR14 % of close per unit of calm daily sd (simulated)
QUARTILE_POINTS = (12.5, 37.5, 62.5, 87.5)
GBM_VOLUME = 1_000_000.0
PRICE_FORMAT = "%.6f"
_MARKET_STREAM = zlib.crc32(b"market")
_LEVEL_STREAM = 1


def ticker_seed(ticker: str, base: int = PLACEBO_SEED) -> list:
    return [base, zlib.crc32(ticker.encode("utf-8"))]


def read_frame(path) -> pd.DataFrame:
    """One cache CSV, tz-naive, sorted, duplicates dropped, OHLCV only."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df.loc[:, list(OHLCV)].dropna()


def trading_calendar(spy_csv, start: str, end: str) -> pd.DatetimeIndex:
    """The index ticker's sessions in [start, end]."""
    idx = read_frame(spy_csv).index
    idx = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if len(idx) == 0:
        raise ValueError(f"{spy_csv}: no session in {start}..{end}")
    return pd.DatetimeIndex(idx, name="Date")


def _source_files(cache_dir, tickers=None) -> list[Path]:
    """Ticker CSVs only: no index, context-only, ^-prefixed or _-prefixed files."""
    paths = sorted(Path(cache_dir).glob("*.csv"))
    keep = [p for p in paths if p.stem != INDEX_TICKER and p.stem not in CONTEXT_ONLY_STEMS
            and not p.stem.startswith(("^", "_"))]
    return keep if tickers is None else [p for p in keep if p.stem in set(tickers)]


def _on_calendar(path, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = read_frame(path)
    return df.loc[(df.index >= calendar[0]) & (df.index <= calendar[-1])]


def atr_pct_quartiles(cache_dir, calendar, tickers=None) -> tuple[float, float, float, float]:
    """Quartile midpoints (QUARTILE_POINTS) of the per-ticker median ATR14 % of close."""
    medians = []
    for path in _source_files(cache_dir, tickers):
        df = _on_calendar(path, calendar)
        if len(df) < 15:
            continue
        value = float(np.nanmedian((indicators.atr(df) / df["Close"]).to_numpy(dtype=float)))
        if np.isfinite(value):
            medians.append(value)
    if not medians:
        raise ValueError(f"no ATR% could be measured in {cache_dir}")
    return tuple(float(v) for v in np.percentile(medians, QUARTILE_POINTS))


def _markov(rng, n: int) -> np.ndarray:
    """A two-state chain starting calm; True = stressed."""
    draws = rng.random(n)
    out = np.zeros(n, dtype=bool)
    for t in range(1, n):
        out[t] = draws[t] >= STRESS_EXIT if out[t - 1] else draws[t] < STRESS_ENTER
    return out


def market_states(calendar, seed) -> np.ndarray:
    """The shared market chain (True = stressed), one per universe seed."""
    return _markov(np.random.default_rng([seed, _MARKET_STREAM]), len(calendar))


def _lognormal(rng, sd: np.ndarray) -> np.ndarray:
    """Log-returns with mean -sd^2/2: exp() of them has expectation one."""
    return rng.normal(-sd ** 2 / 2.0, sd)


def gbm_frame(ticker: str, calendar, *, level: float, stressed,
              seed: int = PLACEBO_SEED) -> pd.DataFrame:
    """One driftless OHLCV path whose median ATR14 % of close sits near ``level``."""
    rng = np.random.default_rng(ticker_seed(ticker, seed))
    n = len(calendar)
    regime = _markov(rng, n) | np.asarray(stressed, dtype=bool)
    sd = level / ATR_PER_SIGMA * np.where(regime, STRESS_MULT, 1.0)
    day_sd = np.sqrt(1.0 - GAP_SHARE ** 2) * sd
    gap, day = _lognormal(rng, GAP_SHARE * sd), _lognormal(rng, day_sd)
    close = rng.uniform(20.0, 200.0) * np.exp(np.cumsum(gap + day))
    open_ = close * np.exp(-day)
    up = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    down = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * np.exp(up),
                         "Low": np.minimum(open_, close) * np.exp(-down), "Close": close,
                         "Volume": np.full(n, GBM_VOLUME)},
                        index=pd.DatetimeIndex(calendar, name="Date"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_universes.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (`placebo.py` lives inside the screen package).

If `test_gbm_median_atr_pct_lands_on_its_level` misses its band, re-fit
`ATR_PER_SIGMA` by the same simulation (median of `ATR14 / close / calm sd`
over 20 tickers of 2,516 sessions), update the constant and the docstring
figure; never widen the test band.

Complexity: `python scripts/dev/complexity_gate.py` — every function above is < 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/placebo.py tests/backtesting/screen/test_placebo_universes.py
git commit -m "feat(v230): placebo price paths -- seeds, calendar, ATR% levels, gbm"
```

### Task V230-2b: Placebo universes on disk: index, layout, `gbm` and `shuffled`

**Model:** opus — the on-disk universes the screen pipeline reads unchanged; the shuffle must keep each day's cross-section and destroy serial structure.

Second half of ledger row V230-2 (split for the task size cap). Needs
V230-2 (`placebo.py` exists with its constants, `read_frame`,
`_source_files`, `_on_calendar`, `ticker_seed`, `market_states`,
`gbm_frame`).

**Files:**
- Modify: `swingbot/core/backtesting/screen/placebo.py` (append)
- Test: `tests/backtesting/screen/test_placebo_universes.py` (append)

**Interfaces:**
- Consumes: V230-2's `PLACEBO_SEED`, `GBM_TICKERS`, `INDEX_TICKER`, `MEMBERSHIP_FILE`, `MANIFEST_FILE`, `OHLCV`, `PRICE_FORMAT`, `_LEVEL_STREAM`, `ticker_seed`, `read_frame`, `_source_files`, `_on_calendar`, `market_states`, `gbm_frame`.
- Produces (index ledger, final): `equal_weight_index(frames) -> pd.DataFrame`; `write_universe(out_dir, frames, *, kind, meta) -> Path` (`<T>.csv` with `Date,Open,High,Low,Close,Volume`, `membership.csv` one span per ticker from the first session with blank end, synthetic `SPY.csv`, `universe.json` `{kind, seed, tickers, calendar_start, calendar_end, **meta}`, written last); `gbm_universe(out_dir, calendar, quartiles, *, n_tickers=GBM_TICKERS, seed=PLACEBO_SEED) -> Path` (tickers `G000`..); `shuffled_universe(out_dir, source_dir, calendar, *, seed=PLACEBO_SEED, copies=1) -> Path` (`meta["source_sha256"] = {file: sha256}`, `meta["copies"]`). Public helpers `day_permutation(n, seed) -> np.ndarray`, `shuffle_frame(df, perm) -> pd.DataFrame`. V230-3 (`plant_universe`) and V230-4 (`build_universes`) call `write_universe`, `gbm_universe`, `shuffled_universe`.

Why: spec A1 — each universe is written to its own cache directory with a
membership file giving every synthetic ticker one all-window span and a
synthetic `SPY` built as the universe's equal-weight index after
generation; `shuffled` keeps each day's cross-section and no serial
structure, seed 42, and records the source files' hashes. Builder choices
fixed here:

- **Equal-weight index.** Level `100 × cumprod(1 + mean daily close
  return)`; open/high/low = level × the mean of each ticker's
  open/high/low-to-close ratio (so high ≥ max(open, close) holds); volume =
  sum.
- **`gbm` levels.** Each ticker draws one of the four ATR% levels from its
  own stream `[seed, crc32(ticker), 1]`, so ticker `G007` is identical in a
  200- and a 400-ticker universe (spec: "the universe does not change with
  the ticker count").
- **`shuffled` rebuild.** Day 0 stays. Days 1..n−1 are permuted by one
  permutation shared by every ticker; each permuted day carries its
  close-to-close return, its open/high/low-to-close ratios and its volume.
  Close = `close[0] × cumprod(return[perm])`; open/high/low = close ×
  ratio[perm]. A day's overnight gap moves with it. Only source tickers with
  a bar on every calendar session are kept (index decision). Copy `c ≥ 1`
  (enlarging) uses seed `[seed, c]` and names its tickers `<T>_c<c>`.
- **Files.** Prices `%.6f`, LF line ends, `universe.json` written **last**:
  its presence marks a complete universe (V230-4's resume check).

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_placebo_universes.py` (`hashlib`,
`json`, `np`, `pd`, `pytest`, `placebo`, `random_walk`, `CAL` and `_source`
are already in the file from V230-2):

```python
def _digest(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.iterdir())}


def test_equal_weight_index_averages_returns_and_ratios():
    idx = pd.bdate_range("2010-01-04", periods=2)
    up = pd.DataFrame({"Open": [10.0, 11.0], "High": [10.5, 11.5], "Low": [9.5, 10.5],
                       "Close": [10.0, 11.0], "Volume": [1.0, 1.0]}, index=idx)
    flat = pd.DataFrame({"Open": [20.0, 20.0], "High": [21.0, 22.0], "Low": [19.0, 18.0],
                         "Close": [20.0, 20.0], "Volume": [2.0, 2.0]}, index=idx)
    out = placebo.equal_weight_index({"A": up, "B": flat})
    assert out["Close"].tolist() == pytest.approx([100.0, 105.0])
    assert out["High"].iloc[1] == pytest.approx(105.0 * (11.5 / 11.0 + 22.0 / 20.0) / 2)
    assert out["Volume"].tolist() == [3.0, 3.0]
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1)).all()


def test_write_universe_lays_out_a_screen_cache(tmp_path):
    calm = np.zeros(len(CAL), dtype=bool)
    frames = {"B": placebo.gbm_frame("B", CAL, level=0.02, stressed=calm),
              "A": placebo.gbm_frame("A", CAL, level=0.02, stressed=calm)}
    out = placebo.write_universe(tmp_path / "u", frames, kind="test", meta={"extra": 1})
    assert sorted(p.name for p in out.iterdir()) == [
        "A.csv", "B.csv", "SPY.csv", "membership.csv", "universe.json"]
    assert (out / "membership.csv").read_text(encoding="utf-8") == (
        "ticker,start_date,end_date\nA,2010-01-04,\nB,2010-01-04,\n")
    manifest = json.loads((out / "universe.json").read_text(encoding="utf-8"))
    assert manifest == {"kind": "test", "seed": 42, "tickers": ["A", "B"],
                        "calendar_start": "2010-01-04",
                        "calendar_end": CAL[-1].strftime("%Y-%m-%d"), "extra": 1}
    head = (out / "A.csv").read_text(encoding="utf-8").splitlines()[0]
    assert head == "Date,Open,High,Low,Close,Volume"
    assert b"\r\n" not in (out / "A.csv").read_bytes()
    assert placebo.read_frame(out / "SPY.csv").index.equals(CAL)
    with pytest.raises(ValueError, match="SPY"):
        placebo.write_universe(tmp_path / "v", {"SPY": frames["A"]}, kind="test", meta={})


def test_gbm_universe_reproduces_and_ignores_the_ticker_count(tmp_path):
    q = (0.01, 0.015, 0.02, 0.03)
    a = placebo.gbm_universe(tmp_path / "a", CAL, q, n_tickers=5)
    b = placebo.gbm_universe(tmp_path / "b", CAL, q, n_tickers=5)
    c = placebo.gbm_universe(tmp_path / "c", CAL, q, n_tickers=3)
    assert _digest(a) == _digest(b)
    for t in ("G000", "G001", "G002"):
        assert (a / f"{t}.csv").read_bytes() == (c / f"{t}.csv").read_bytes()
    manifest = json.loads((a / "universe.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "gbm" and manifest["tickers"] == [f"G{i:03d}" for i in range(5)]
    assert manifest["quartiles"] == list(q) and manifest["seed"] == 42
    d = placebo.gbm_universe(tmp_path / "d", CAL, q, n_tickers=3, seed=7)
    assert (d / "G000.csv").read_bytes() != (c / "G000.csv").read_bytes()


def test_day_permutation_keeps_day_zero():
    perm = placebo.day_permutation(50, 42)
    assert perm[0] == 0 and sorted(perm) == list(range(50))
    assert np.array_equal(perm, placebo.day_permutation(50, 42))
    assert not np.array_equal(perm, placebo.day_permutation(50, [42, 1]))


def test_shuffle_frame_moves_whole_days():
    df = random_walk(40, seed=3)
    perm = placebo.day_permutation(40, 42)
    out = placebo.shuffle_frame(df, perm)
    ret = df["Close"].pct_change().to_numpy()
    new = out["Close"].pct_change().to_numpy()
    assert out["Close"].iloc[0] == df["Close"].iloc[0]
    assert np.allclose(new[1:], ret[perm][1:])
    assert np.allclose((out["Open"] / out["Close"]).to_numpy(),
                       (df["Open"] / df["Close"]).to_numpy()[perm])
    assert np.array_equal(out["Volume"].to_numpy(), df["Volume"].to_numpy()[perm])
    assert out.index.equals(df.index)


def test_shuffled_universe_keeps_cross_sections_and_reproduces(tmp_path):
    src = _source(tmp_path)
    random_walk(500, seed=5).to_csv(src / "DDD.csv", index_label="Date")   # short: dropped
    a = placebo.shuffled_universe(tmp_path / "a", src, CAL)
    b = placebo.shuffled_universe(tmp_path / "b", src, CAL)
    assert _digest(a) == _digest(b)
    manifest = json.loads((a / "universe.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "shuffled" and manifest["tickers"] == ["AAA", "BBB", "CCC"]
    assert sorted(manifest["source_sha256"]) == ["AAA.csv", "BBB.csv", "CCC.csv"]
    assert manifest["source_sha256"]["AAA.csv"] == hashlib.sha256(
        (src / "AAA.csv").read_bytes()).hexdigest()
    rets = {t: placebo.read_frame(a / f"{t}.csv")["Close"].pct_change() for t in ("AAA", "BBB")}
    orig = {t: placebo.read_frame(src / f"{t}.csv")["Close"].pct_change() for t in ("AAA", "BBB")}
    pairs = sorted(zip(rets["AAA"].round(4)[1:], rets["BBB"].round(4)[1:]))
    assert pairs == sorted(zip(orig["AAA"].round(4)[1:], orig["BBB"].round(4)[1:]))


def test_shuffled_copies_add_suffixed_tickers(tmp_path):
    src = _source(tmp_path)
    out = placebo.shuffled_universe(tmp_path / "u", src, CAL, copies=2)
    manifest = json.loads((out / "universe.json").read_text(encoding="utf-8"))
    assert manifest["tickers"] == ["AAA", "AAA_c1", "BBB", "BBB_c1", "CCC", "CCC_c1"]
    assert manifest["copies"] == 2
    assert (out / "AAA.csv").read_bytes() != (out / "AAA_c1.csv").read_bytes()


def test_shuffled_universe_refuses_a_cache_without_full_tickers(tmp_path):
    src = _source(tmp_path, n=500)
    with pytest.raises(ValueError, match="every calendar session"):
        placebo.shuffled_universe(tmp_path / "u", src, CAL)
```

(The cross-section test compares rounded return pairs: the CSV holds six
decimals, so a fourth-decimal return is exact enough, and one permutation
per ticker instead of one shared would break almost every pair.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_universes.py`
Expected: FAIL — `AttributeError: module ... placebo has no attribute 'equal_weight_index'` (and the other new names); V230-2's tests still pass.

- [ ] **Step 3: Implement**

Append to `swingbot/core/backtesting/screen/placebo.py`:

```python
def equal_weight_index(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Level 100 x cumprod(1 + mean daily return); O/H/L from the mean ratios to close."""
    names = sorted(frames)
    close = pd.DataFrame({t: frames[t]["Close"] for t in names})
    level = 100.0 * (1.0 + close.pct_change(fill_method=None).mean(axis=1).fillna(0.0)).cumprod()

    def ratio(col):
        return pd.DataFrame({t: frames[t][col] / frames[t]["Close"] for t in names}).mean(axis=1)

    volume = pd.DataFrame({t: frames[t]["Volume"] for t in names}).sum(axis=1)
    return pd.DataFrame({"Open": level * ratio("Open"), "High": level * ratio("High"),
                         "Low": level * ratio("Low"), "Close": level, "Volume": volume},
                        index=pd.DatetimeIndex(close.index, name="Date"))


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.loc[:, list(OHLCV)].to_csv(path, index_label="Date", date_format="%Y-%m-%d",
                                  float_format=PRICE_FORMAT, lineterminator="\n")


def write_universe(out_dir, frames: Mapping[str, pd.DataFrame], *, kind: str,
                   meta: Mapping) -> Path:
    """One screen cache directory; universe.json is written last."""
    if INDEX_TICKER in frames:
        raise ValueError(f"{INDEX_TICKER} is the synthetic index; no ticker may use the name")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = sorted(frames)
    for ticker in names:
        _write_csv(out / f"{ticker}.csv", frames[ticker])
    index = equal_weight_index(frames)
    _write_csv(out / f"{INDEX_TICKER}.csv", index)
    first, last = (d.strftime("%Y-%m-%d") for d in (index.index[0], index.index[-1]))
    (out / MEMBERSHIP_FILE).write_text(
        "ticker,start_date,end_date\n" + "".join(f"{t},{first},\n" for t in names),
        encoding="utf-8", newline="\n")
    manifest = {"kind": kind, "seed": PLACEBO_SEED, "tickers": names,
                "calendar_start": first, "calendar_end": last, **meta}
    (out / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n",
                                     encoding="utf-8", newline="\n")
    return out


def _level_for(ticker: str, quartiles, seed: int) -> float:
    rng = np.random.default_rng(ticker_seed(ticker, seed) + [_LEVEL_STREAM])
    return float(quartiles[int(rng.integers(len(quartiles)))])


def gbm_universe(out_dir, calendar, quartiles, *, n_tickers: int = GBM_TICKERS,
                 seed: int = PLACEBO_SEED) -> Path:
    """G000.. tickers; each path depends on its name and ``seed`` only."""
    market = market_states(calendar, seed)
    frames = {}
    for i in range(n_tickers):
        ticker = f"G{i:03d}"
        frames[ticker] = gbm_frame(ticker, calendar, level=_level_for(ticker, quartiles, seed),
                                   stressed=market, seed=seed)
    return write_universe(out_dir, frames, kind="gbm",
                          meta={"seed": seed, "n_tickers": n_tickers,
                                "quartiles": [float(q) for q in quartiles]})


def day_permutation(n: int, seed) -> np.ndarray:
    """Day 0 fixed; days 1..n-1 permuted."""
    return np.r_[0, 1 + np.random.default_rng(seed).permutation(n - 1)]


def shuffle_frame(df: pd.DataFrame, perm: np.ndarray) -> pd.DataFrame:
    """Rebuild ``df`` on its own index from the permuted days."""
    close = df["Close"].to_numpy(dtype=float)
    ret = np.r_[1.0, close[1:] / close[:-1]]
    rebuilt = close[0] * np.cumprod(ret[perm])
    cols = {c: rebuilt * (df[c].to_numpy(dtype=float) / close)[perm]
            for c in ("Open", "High", "Low")}
    return pd.DataFrame({**cols, "Close": rebuilt,
                         "Volume": df["Volume"].to_numpy(dtype=float)[perm]},
                        index=df.index)


def _full_sources(source_dir, calendar) -> tuple[dict, dict]:
    """Tickers with a bar on every calendar session, and their files' sha256."""
    frames, hashes = {}, {}
    for path in _source_files(source_dir):
        df = _on_calendar(path, calendar)
        if len(df) == len(calendar) and np.array_equal(df.index.values, calendar.values):
            frames[path.stem] = df
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not frames:
        raise ValueError(f"no ticker in {source_dir} has a bar on every calendar session")
    return frames, hashes


def shuffled_universe(out_dir, source_dir, calendar, *, seed: int = PLACEBO_SEED,
                      copies: int = 1) -> Path:
    """The real bars, whole days permuted alike across tickers; copy c >= 1 is <T>_c<c>."""
    sources, hashes = _full_sources(source_dir, calendar)
    frames = {}
    for c in range(copies):
        perm = day_permutation(len(calendar), seed if c == 0 else [seed, c])
        suffix = "" if c == 0 else f"_c{c}"
        for ticker, df in sources.items():
            frames[ticker + suffix] = shuffle_frame(df, perm)
    return write_universe(out_dir, frames, kind="shuffled",
                          meta={"seed": seed, "copies": copies, "source_sha256": hashes})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_universes.py`
Expected: PASS, 0 failed.

Complexity: `python scripts/dev/complexity_gate.py` — every function above is < 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/placebo.py tests/backtesting/screen/test_placebo_universes.py
git commit -m "feat(v230): write placebo universes -- equal-weight SPY, gbm, shuffled days"
```

### Task V230-3: Placebo triggers, planted drift, cells and the acceptance rule

**Model:** opus — six causal triggers and a planted edge whose recovery is half of the v2 stop gate.

This ledger row is split in two (task size cap): **V230-3** builds the
triggers, the placebo `Idea` and the planted-edge universe; **V230-3b**
adds `Cell`, the per-cell statistic and the acceptance rule. Together they
produce the ledger row's symbols.

**Files:**
- Modify: `swingbot/core/backtesting/screen/placebo.py` (imports, append)
- Test: `tests/backtesting/screen/test_placebo_triggers.py` (create)

**Interfaces:**
- Consumes: V230-1 `Idea(..., scope=...)`; V230-2/2b `read_frame`, `write_universe`, `gbm_universe`, `INDEX_TICKER`, `MANIFEST_FILE`; existing `indicators.atr/rsi/sma/rolling_max/rolling_min`.
- Produces (index ledger, final): `PLACEBO_CAP = 10`; `PLANT_ATR = 0.5`; `TOLERANCE_R = 0.02`; `PlaceboTrigger(name, scope, events)` (`events(ticker_frame, index_frame) -> pd.Series`); `TRIGGERS` (`p_high20`, `p_rsi2_dip`, `p_gap_up`, `p_sweep20` ticker scope; `p_market_down`, `p_month_turn` market scope); `placebo_idea(trigger, index_frame) -> Idea`; `plant_drift(df, events, atr, *, cap=PLACEBO_CAP, atr_mult=PLANT_ATR) -> pd.DataFrame`; `plant_universe(base_dir, out_dir) -> Path` (planted frames plus `planted_events.json` `{ticker: [ISO dates]}`); `planted_trigger(universe_dir) -> PlaceboTrigger` (`p_high20_planted`); `planted_value(base_rows, planted_rows) -> float | None`. Also `PLANT_SPACING = 120`, `PLANTED_FILE = "planted_events.json"`.

Why: spec A1 — six placebo triggers copying the shapes of real ones, never
registered as ideas, and a +0.5 ATR drift planted after `p_high20` events
so the v2 null is shown not to be blind. Decisions fixed here:

- **One frozen race** (index decision): long, fixed 1.5/3 ATR, next open,
  cap 10. Triggers read bars ≤ *t* only (truncation tests below);
  `p_month_turn` reads whether the next session opens a new month, exactly
  like the registered `turn_of_month`.
- **`p_market_down`**: the universe's own synthetic `SPY` close-to-close
  return at *t* below −1.5 × the sd of the 20 returns before *t*.
- **Planted drift**: for an event at *t*, bar *t+j*'s close (and high) gains
  `a·min(j, cap)/cap` and its open (and low) `a·min(j−1, cap)/cap`, with
  `a = 0.5 × ATR14[t]`; the shift persists after the cap, so every
  overnight gap is unchanged and the entry open (*t+1*) carries none of it.
  Planted events are `p_high20` events at least `PLANT_SPACING = 120` bars
  apart per ticker, so few null bars sit inside another event's ramp.
- **Planted trigger identity**: the screen hands `events(df)` a frame
  without its ticker name, so `planted_trigger` keys each ticker by the
  first five closes of its CSV (identical in the base and planted universe,
  because no drift starts before bar 21); a collision raises.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_placebo_triggers.py`:

```python
"""v230 A1: placebo triggers (causal), planted drift, cells and acceptance."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import placebo
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

CAL = pd.bdate_range("2010-01-04", periods=600)


def test_trigger_registry_and_scopes():
    assert {n: t.scope for n, t in placebo.TRIGGERS.items()} == {
        "p_high20": "ticker", "p_rsi2_dip": "ticker", "p_gap_up": "ticker",
        "p_sweep20": "ticker", "p_market_down": "market", "p_month_turn": "market"}
    assert all(t.name == n for n, t in placebo.TRIGGERS.items())


@pytest.mark.parametrize("name", ["p_high20", "p_rsi2_dip", "p_gap_up", "p_sweep20",
                                  "p_market_down"])
def test_triggers_read_no_later_bar(name):
    df, index = random_walk(400, seed=11), random_walk(400, seed=12)
    trig = placebo.TRIGGERS[name]
    assert_prefix_stable(lambda d: trig.events(d, index.loc[d.index]), df, [250, 320, 399])


def test_month_turn_reads_only_the_next_session_date():
    trig = placebo.TRIGGERS["p_month_turn"]
    df = random_walk(120, seed=3)
    assert_prefix_stable(lambda d: trig.events(d, d), df, [40, 80], skip_last=True)
    flags = trig.events(df, df)
    month = df.index.year * 12 + df.index.month
    assert flags.to_numpy().tolist() == list(np.r_[month[1:] != month[:-1], True])


def test_high20_fires_on_a_close_above_the_prior_twenty_highs():
    df = frame([100.0] * 25 + [105.0, 105.0])          # High = Close + 1
    flags = placebo.TRIGGERS["p_high20"].events(df, df)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [25]


def test_sweep20_needs_the_low_under_and_the_close_back_above():
    lows = [99.0] * 25 + [97.0, 97.0]
    closes = [100.0] * 25 + [99.5, 98.0]
    df = frame(closes, lows=lows, highs=np.array(closes) + 1)
    flags = placebo.TRIGGERS["p_sweep20"].events(df, df)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [25]


def test_gap_up_compares_with_half_the_prior_atr():
    df = frame([100.0] * 30, opens=[100.0] * 29 + [101.0])   # ATR14 = 2 (High-Low)
    assert placebo.TRIGGERS["p_gap_up"].events(df, df).to_numpy()[-1]
    df = frame([100.0] * 30, opens=[100.0] * 29 + [100.99])
    assert not placebo.TRIGGERS["p_gap_up"].events(df, df).to_numpy()[-1]


def test_market_down_reads_the_index_not_the_ticker():
    idx = pd.bdate_range("2010-01-04", periods=40)
    closes = 100.0 * np.cumprod(np.r_[1.0, np.where(np.arange(39) % 2, 1.001, 0.999)])
    closes[30:] = closes[29] * 0.97
    index = frame(closes, index=idx)
    ticker = frame(np.full(40, 50.0), index=idx)
    flags = placebo.TRIGGERS["p_market_down"].events(ticker, index)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [30]


def test_placebo_idea_is_one_frozen_long_next_open_race():
    index = random_walk(300, seed=2)
    idea = placebo.placebo_idea(placebo.TRIGGERS["p_month_turn"], index)
    assert (idea.name, idea.time_cap_bars, idea.direction, idea.race_shape, idea.entry,
            idea.scope, idea.context) == ("p_month_turn", 10, "long", "fixed", "next_open",
                                          "market", ())
    flags = idea.events(random_walk(300, seed=5))
    assert flags.dtype == bool and len(flags) == 300


def test_plant_drift_ramps_after_the_entry_open_and_keeps_gaps():
    df = frame(np.full(30, 100.0))
    events = np.zeros(30, dtype=bool)
    events[5] = True
    out = placebo.plant_drift(df, events, pd.Series(2.0, index=df.index))
    add_close = (out["Close"] - df["Close"]).to_numpy()
    add_open = (out["Open"] - df["Open"]).to_numpy()
    assert np.allclose(add_close[:6], 0.0) and np.allclose(add_open[:7], 0.0)
    assert add_close[6] == pytest.approx(0.1) and add_close[15] == pytest.approx(1.0)
    assert add_close[29] == pytest.approx(1.0) and add_open[16] == pytest.approx(1.0)
    assert np.allclose(add_open[7:], add_close[6:-1])          # gaps unchanged
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1)).all()
    assert (out["Low"] <= out[["Open", "Close"]].min(axis=1)).all()


def test_plant_universe_and_its_trigger(tmp_path):
    base = placebo.gbm_universe(tmp_path / "base", CAL, (0.01, 0.015, 0.02, 0.03), n_tickers=3)
    out = placebo.plant_universe(base, tmp_path / "planted")
    planted = json.loads((out / placebo.PLANTED_FILE).read_text(encoding="utf-8"))
    assert sorted(planted) == ["G000", "G001", "G002"] and any(planted.values())
    trig = placebo.planted_trigger(out)
    assert (trig.name, trig.scope) == ("p_high20_planted", "ticker")
    for t, days in planted.items():
        pos = placebo.read_frame(base / f"{t}.csv").index.get_indexer(pd.DatetimeIndex(days))
        assert (np.diff(pos) >= placebo.PLANT_SPACING).all()
        for root in (base, out):
            df = placebo.read_frame(root / f"{t}.csv")
            hits = df.index[trig.events(df, df).to_numpy()]
            assert [d.strftime("%Y-%m-%d") for d in hits] == days
    manifest = json.loads((out / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["kind"] == "planted" and manifest["base"] == "gbm"


def test_planted_value_is_the_mean_event_r_gain_on_shared_events():
    base = [{"ticker": "A", "entry_date": "2011-01-04", "r_event": 0.1},
            {"ticker": "A", "entry_date": "2011-02-01", "r_event": -1.0}]
    planted = [{"ticker": "A", "entry_date": "2011-01-04", "r_event": 0.5},
               {"ticker": "B", "entry_date": "2011-01-04", "r_event": 9.0}]
    assert placebo.planted_value(base, planted) == pytest.approx(0.4)
    assert placebo.planted_value(base, []) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_triggers.py`
Expected: FAIL — `AttributeError: module ... placebo has no attribute 'TRIGGERS'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/screen/placebo.py`, replace the `typing` import and
the two `swingbot.core.backtesting.screen` import lines with (`asdict`, `fields`,
`stats` and `verdict` serve V230-3b):

```python
from dataclasses import asdict, dataclass, fields
from typing import Callable, Mapping

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import indicators, verdict
from swingbot.core.backtesting.screen.context import CONTEXT_ONLY_STEMS
from swingbot.core.backtesting.screen.ideas import Idea
```

and append:

```python
PLACEBO_CAP = 10
PLANT_ATR = 0.5
PLANT_SPACING = 12 * PLACEBO_CAP     # bars between planted events on one ticker
PLANTED_FILE = "planted_events.json"
TOLERANCE_R = 0.02
FINGERPRINT_BARS = 5
_PLACES = 10


@dataclass(frozen=True)
class PlaceboTrigger:
    name: str
    scope: str
    events: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]   # (ticker frame, index frame)


def _high20(df, index):
    return df["Close"] > indicators.rolling_max(df["High"], 20).shift(1)


def _rsi2_dip(df, index):
    close = df["Close"]
    return (close > indicators.sma(close, 200)) & (indicators.rsi(close, 2) < 10)


def _gap_up(df, index):
    return df["Open"] >= df["Close"].shift(1) + 0.5 * indicators.atr(df).shift(1)


def _sweep20(df, index):
    low20 = indicators.rolling_min(df["Low"], 20).shift(1)
    return (df["Low"] < low20) & (df["Close"] > low20)


def _market_down(df, index):
    ret = index["Close"].pct_change(fill_method=None)
    flag = ret < -1.5 * ret.rolling(20, min_periods=20).std().shift(1)
    return flag.reindex(df.index, fill_value=False)


def _month_turn(df, index):
    month = df.index.year * 12 + df.index.month
    return pd.Series(np.r_[month[1:] != month[:-1], True], index=df.index)


TRIGGERS: dict[str, PlaceboTrigger] = {t.name: t for t in (
    PlaceboTrigger("p_high20", "ticker", _high20),
    PlaceboTrigger("p_rsi2_dip", "ticker", _rsi2_dip),
    PlaceboTrigger("p_gap_up", "ticker", _gap_up),
    PlaceboTrigger("p_sweep20", "ticker", _sweep20),
    PlaceboTrigger("p_market_down", "market", _market_down),
    PlaceboTrigger("p_month_turn", "market", _month_turn))}


def placebo_idea(trigger: PlaceboTrigger, index_frame: pd.DataFrame) -> Idea:
    """The trigger as an unregistered Idea: long, fixed race, next open, cap 10."""
    def events(df):
        flags = trigger.events(df, index_frame).reindex(df.index, fill_value=False)
        return flags.fillna(False).astype(bool)

    return Idea(name=trigger.name, events=events, time_cap_bars=PLACEBO_CAP,
                params={"placebo": trigger.name, "cap": PLACEBO_CAP},
                summary=f"v230 placebo trigger {trigger.name}", source="spec v230 A1",
                scope=trigger.scope)


def plant_drift(df, events, atr, *, cap: int = PLACEBO_CAP,
                atr_mult: float = PLANT_ATR) -> pd.DataFrame:
    """+atr_mult x ATR14[t] spread over bars t+1..t+cap, persisting after."""
    n = len(df)
    add_close, add_open = np.zeros(n), np.zeros(n)
    atr_v = np.asarray(atr, dtype=float)
    for t in np.flatnonzero(np.asarray(events, dtype=bool)):
        if t + 1 >= n or not np.isfinite(atr_v[t]):
            continue
        steps = np.arange(1, n - t)
        add_close[t + 1:] += atr_mult * atr_v[t] * np.minimum(steps, cap) / cap
        add_open[t + 1:] += atr_mult * atr_v[t] * np.minimum(steps - 1, cap) / cap
    out = df.copy()
    for col, add in (("Open", add_open), ("High", add_close), ("Low", add_open),
                     ("Close", add_close)):
        out[col] = df[col].to_numpy(dtype=float) + add
    return out


def _spaced(pos: np.ndarray, spacing: int) -> list[int]:
    kept: list[int] = []
    for p in pos:
        if not kept or p - kept[-1] >= spacing:
            kept.append(int(p))
    return kept


def plant_universe(base_dir, out_dir) -> Path:
    """The base universe with drift planted after spaced p_high20 events."""
    base = Path(base_dir)
    manifest = json.loads((base / MANIFEST_FILE).read_text(encoding="utf-8"))
    index = read_frame(base / f"{INDEX_TICKER}.csv")
    frames, planted = {}, {}
    for ticker in manifest["tickers"]:
        df = read_frame(base / f"{ticker}.csv")
        atr = indicators.atr(df)
        fired = TRIGGERS["p_high20"].events(df, index).to_numpy(dtype=bool)
        ok = fired & np.isfinite(atr.to_numpy()) & (np.arange(len(df)) + 1 < len(df))
        pos = _spaced(np.flatnonzero(ok), PLANT_SPACING)
        flags = np.zeros(len(df), dtype=bool)
        flags[pos] = True
        frames[ticker] = plant_drift(df, flags, atr)
        planted[ticker] = [d.strftime("%Y-%m-%d") for d in df.index[pos]]
    out = write_universe(out_dir, frames, kind="planted",
                         meta={"seed": manifest["seed"], "base": manifest["kind"],
                               "plant_atr": PLANT_ATR, "cap": PLACEBO_CAP,
                               "spacing": PLANT_SPACING})
    (out / PLANTED_FILE).write_text(json.dumps(planted, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8", newline="\n")
    return out


def _fingerprint(df: pd.DataFrame) -> tuple:
    return tuple(np.round(df["Close"].to_numpy(dtype=float)[:FINGERPRINT_BARS], 6))


def planted_trigger(universe_dir) -> PlaceboTrigger:
    """Fires on the planted dates, on the planted universe and its base alike."""
    root = Path(universe_dir)
    planted = json.loads((root / PLANTED_FILE).read_text(encoding="utf-8"))
    lookup: dict[tuple, pd.DatetimeIndex] = {}
    for ticker, days in planted.items():
        key = _fingerprint(read_frame(root / f"{ticker}.csv"))
        if key in lookup:
            raise ValueError(f"{ticker}: first closes collide with another ticker")
        lookup[key] = pd.DatetimeIndex(days)

    def events(df, index):
        days = lookup.get(_fingerprint(df))
        flags = np.zeros(len(df), bool) if days is None else df.index.isin(days)
        return pd.Series(flags, index=df.index)

    return PlaceboTrigger("p_high20_planted", "ticker", events)


def planted_value(base_rows, planted_rows) -> float | None:
    """Mean event-arm R gain on events booked in both universes."""
    base = {(r["ticker"], str(r["entry_date"])[:10]): r["r_event"] for r in base_rows}
    gains = [r["r_event"] - base[key] for r in planted_rows
             if (key := (r["ticker"], str(r["entry_date"])[:10])) in base]
    return float(np.mean(gains)) if gains else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_triggers.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_universes.py`
Expected: PASS, 0 failed.

Complexity: `python scripts/dev/complexity_gate.py` — `plant_universe` (the largest) stays under 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/placebo.py tests/backtesting/screen/test_placebo_triggers.py
git commit -m "feat(v230): placebo triggers and the planted-edge universe"
```

### Task V230-3b: Placebo cells and the acceptance rule

**Model:** opus — the acceptance arithmetic is the stop gate; boundary inclusivity must be exact.

Second half of ledger row V230-3 (split for the task size cap). Needs
V230-3 (`TOLERANCE_R`, `_PLACES`, and the `asdict`/`fields`/`stats`/`verdict`
imports in `placebo.py`).

**Files:**
- Modify: `swingbot/core/backtesting/screen/placebo.py` (append)
- Test: `tests/backtesting/screen/test_placebo_triggers.py` (append)

**Interfaces:**
- Consumes: V230-3 `TOLERANCE_R`, `_PLACES`; existing `verdict.PairedEvent(entry_date, d)`, `verdict.bootstrap(events, *, n_resamples, seed) -> (low, high, p)` (week-clustered), `stats.WEEK_BOOTSTRAP_RESAMPLES`, `stats.WEEK_BOOTSTRAP_SEED`.
- Produces (index ledger, final): `@dataclass(frozen=True) Cell(universe, trigger, null, n, mean_r_event, mean_r_null, delta, ci_low, ci_high)` with `.half_width`, `to_dict()`, `Cell.from_dict(d)`; `cell_from_rows(universe, trigger, null_version, rows, *, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, seed=stats.WEEK_BOOTSTRAP_SEED) -> Cell` (rows are the screen's event rows: `ticker`, `entry_date`, `r_event`, `r_null`); `accept_cell(cell) -> str` in `("PASS", "FAIL", "NOISY")`; `v1_premise_holds(cells) -> bool`; `planted_recovered(cell, value) -> bool`; `acceptance(cells, planted_cell, value) -> dict` with keys `verdict` (`ACCEPT`/`STOP`/`ENLARGE`), `cells` (`{"<universe>/<trigger>": verdict}`), `planted` (`value`, `cell`, `recovered`, `noisy`). V230-4 and V230-13 consume all of them.

Why: spec A1 — one row per universe × trigger × null with N, mean R_event,
mean R_null, Δ and its 95% interval; under v1 the table is the measurement
of Defect 1 (premise wrong if every |Δ| ≤ 0.02R); under v2 every cell needs
|Δ| ≤ 0.02R and half-width ≤ 0.02R, both inclusive, a noisy cell is
enlarged and never waved through, and the planted value must sit inside the
planted cell's interval. Δ's interval is the screen's own week-clustered
bootstrap (`verdict.bootstrap` over `PairedEvent(entry_date, r_event − r_null)`).
Decisions fixed here:

- **Cell verdict**: an interval wholly outside ±0.02R is `FAIL` even when
  wide (it fails at any size); otherwise half-width > 0.02R is `NOISY`;
  otherwise |Δ| decides `PASS`/`FAIL`. Comparisons round to 10 decimals so
  0.02 computed as 0.020000000000000004 stays inclusive. No events → `NOISY`.
- **Acceptance**: any `FAIL` → `STOP`; else any `NOISY` cell or a noisy or
  missing planted cell → `ENLARGE`; else planted value outside the planted
  cell's interval → `STOP`; else `ACCEPT`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_placebo_triggers.py` (`json`, `pytest`
and `placebo` are already imported there):

```python
def _cell(delta, low, high, n=500, trigger="p_high20"):
    return placebo.Cell("gbm-200", trigger, "v2", n, 0.1, 0.1 - (delta or 0.0),
                        delta, low, high)


def test_cell_from_rows_and_round_trip():
    rows = [{"ticker": "A", "entry_date": f"2011-{m:02d}-03", "r_event": 0.3, "r_null": 0.1}
            for m in range(1, 13)]
    cell = placebo.cell_from_rows("gbm-200", "p_high20", "v1", rows, n_resamples=200)
    assert (cell.n, cell.mean_r_event, cell.mean_r_null) == (12, pytest.approx(0.3),
                                                             pytest.approx(0.1))
    assert cell.delta == pytest.approx(0.2) and cell.ci_low == pytest.approx(0.2)
    assert cell.half_width == pytest.approx(0.0)
    assert placebo.Cell.from_dict(json.loads(json.dumps(cell.to_dict()))) == cell
    empty = placebo.cell_from_rows("gbm-200", "p_high20", "v1", [])
    assert (empty.n, empty.delta, empty.half_width) == (0, None, None)


@pytest.mark.parametrize("delta, low, high, expected", [
    (0.02, 0.0, 0.04, "PASS"),          # |Δ| = 0.02 and half-width = 0.02, both inclusive
    (-0.02, -0.04, 0.0, "PASS"),
    (0.03, 0.01, 0.05, "FAIL"),         # half-width computes as 0.020000000000000004
    (0.0201, 0.0001, 0.0401, "FAIL"),
    (0.0, -0.0201, 0.0201, "NOISY"),
    (0.3, 0.21, 0.39, "FAIL"),          # wide, but wholly outside the band
    (0.03, -0.02, 0.08, "NOISY"),
    (None, None, None, "NOISY"),
])
def test_accept_cell_boundaries(delta, low, high, expected):
    assert placebo.accept_cell(_cell(delta, low, high)) == expected


def test_v1_premise_holds_only_past_the_tolerance():
    calm = [_cell(0.02, 0.0, 0.04), _cell(-0.02, -0.04, 0.0)]
    assert placebo.v1_premise_holds(calm) is False
    assert placebo.v1_premise_holds(calm + [_cell(-0.0201, -0.05, 0.0)]) is True


def test_planted_recovered_is_interval_containment():
    cell = _cell(0.3, 0.28, 0.32)
    assert placebo.planted_recovered(cell, 0.28) and placebo.planted_recovered(cell, 0.32)
    assert not placebo.planted_recovered(cell, 0.3201)
    assert not placebo.planted_recovered(cell, None)


def test_acceptance_verdicts():
    good, planted = [_cell(0.0, -0.01, 0.01)], _cell(0.3, 0.29, 0.31)
    assert placebo.acceptance(good, planted, 0.3)["verdict"] == "ACCEPT"
    assert placebo.acceptance(good + [_cell(0.05, 0.04, 0.06)], planted, 0.3)["verdict"] == "STOP"
    assert placebo.acceptance(good + [_cell(0.0, -0.03, 0.03)], planted, 0.3)["verdict"] == "ENLARGE"
    assert placebo.acceptance(good, planted, 0.35)["verdict"] == "STOP"
    assert placebo.acceptance(good, _cell(0.3, 0.2, 0.4), 0.3)["verdict"] == "ENLARGE"
    assert placebo.acceptance(good, None, None)["verdict"] == "ENLARGE"
    out = placebo.acceptance(good, planted, 0.3)
    assert out["cells"] == {"gbm-200/p_high20": "PASS"}
    assert out["planted"]["recovered"] is True and out["planted"]["value"] == 0.3
    with pytest.raises(ValueError, match="no cells"):
        placebo.acceptance([], planted, 0.3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_triggers.py`
Expected: FAIL — `AttributeError: module ... placebo has no attribute 'Cell'`; V230-3's tests still pass.

- [ ] **Step 3: Implement**

Append to `swingbot/core/backtesting/screen/placebo.py`:

```python
@dataclass(frozen=True)
class Cell:
    universe: str
    trigger: str
    null: str
    n: int
    mean_r_event: float | None
    mean_r_null: float | None
    delta: float | None
    ci_low: float | None
    ci_high: float | None

    @property
    def half_width(self) -> float | None:
        if self.ci_low is None or self.ci_high is None:
            return None
        return (self.ci_high - self.ci_low) / 2.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> "Cell":
        return cls(**{f.name: d[f.name] for f in fields(cls)})


def cell_from_rows(universe: str, trigger: str, null_version: str, rows, *,
                   n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
                   seed: int = stats.WEEK_BOOTSTRAP_SEED) -> Cell:
    """N, mean R per arm, Δ and its week-clustered 95% interval."""
    if not rows:
        return Cell(universe, trigger, null_version, 0, None, None, None, None, None)
    event = np.array([float(r["r_event"]) for r in rows])
    null_r = np.array([float(r["r_null"]) for r in rows])
    paired = [verdict.PairedEvent(str(r["entry_date"])[:10], float(e - z))
              for r, e, z in zip(rows, event, null_r)]
    low, high, _ = verdict.bootstrap(paired, n_resamples=n_resamples, seed=seed)
    return Cell(universe, trigger, null_version, len(rows), float(event.mean()),
                float(null_r.mean()), float((event - null_r).mean()), low, high)


def _r(x: float) -> float:
    return round(float(x), _PLACES)


def accept_cell(cell: Cell) -> str:
    """PASS / FAIL / NOISY under the inclusive 0.02R rule."""
    if cell.n == 0 or cell.delta is None or cell.half_width is None:
        return "NOISY"
    if _r(cell.ci_low) > TOLERANCE_R or _r(cell.ci_high) < -TOLERANCE_R:
        return "FAIL"
    if _r(cell.half_width) > TOLERANCE_R:
        return "NOISY"
    return "PASS" if _r(abs(cell.delta)) <= TOLERANCE_R else "FAIL"


def v1_premise_holds(cells) -> bool:
    """True when some cell's |Δ| exceeds the tolerance (Defect 1 measured)."""
    return any(c.delta is not None and _r(abs(c.delta)) > TOLERANCE_R for c in cells)


def planted_recovered(cell: Cell, value) -> bool:
    if value is None or cell.half_width is None:
        return False
    return _r(cell.ci_low) <= _r(value) <= _r(cell.ci_high)


def _noisy(cell: Cell | None) -> bool:
    """The planted cell is judged for noise only: its Δ is meant to be large."""
    return cell is None or cell.n == 0 or cell.half_width is None or         _r(cell.half_width) > TOLERANCE_R


def _planted_block(planted_cell, value) -> dict:
    return {"value": value, "cell": None if planted_cell is None else planted_cell.to_dict(),
            "recovered": planted_cell is not None and planted_recovered(planted_cell, value),
            "noisy": _noisy(planted_cell)}


def acceptance(cells, planted_cell, value) -> dict:
    """ACCEPT / STOP / ENLARGE over every placebo cell plus the planted check."""
    if not cells:
        raise ValueError("acceptance needs placebo cells; no cells given")
    verdicts = {f"{c.universe}/{c.trigger}": accept_cell(c) for c in cells}
    planted = _planted_block(planted_cell, value)
    if "FAIL" in verdicts.values():
        outcome = "STOP"
    elif "NOISY" in verdicts.values() or planted["noisy"]:
        outcome = "ENLARGE"
    else:
        outcome = "ACCEPT" if planted["recovered"] else "STOP"
    return {"verdict": outcome, "cells": verdicts, "planted": planted}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_placebo_triggers.py`
Expected: PASS, 0 failed.

Complexity: `python scripts/dev/complexity_gate.py` — `accept_cell` and `acceptance` stay well under 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/placebo.py tests/backtesting/screen/test_placebo_triggers.py
git commit -m "feat(v230): placebo cells and the inclusive 0.02R acceptance rule"
```

