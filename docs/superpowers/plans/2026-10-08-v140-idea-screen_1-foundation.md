# v140 Idea screen: Implementation Plan, part 1 — foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Review Focus, Frozen readings and Parallelisation live in [`_0-index`](2026-10-08-v140-idea-screen_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`.

**Spec:** [`docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`](../specs/2026-10-08-v140-idea-screen-design.md)

# Phase 1 — Foundation (sequential)

### Task V140-1: Screen package, causal indicators, test helpers, import guard

**Files:**
- Create: `swingbot/core/backtesting/screen/__init__.py`
- Create: `swingbot/core/backtesting/screen/indicators.py`
- Create: `tests/backtesting/screen/__init__.py` (empty)
- Create: `tests/backtesting/screen/helpers.py`
- Test: `tests/backtesting/screen/test_indicators.py`
- Test: `tests/backtesting/screen/test_import_guard.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `indicators.wilder_mean(values: pd.Series, n: int) -> pd.Series`
  - `indicators.true_range(df: pd.DataFrame) -> pd.Series`
  - `indicators.atr(df: pd.DataFrame, n: int = 14) -> pd.Series`
  - `indicators.rsi(close: pd.Series, n: int) -> pd.Series`
  - `indicators.sma(values: pd.Series, n: int) -> pd.Series`
  - `indicators.rolling_max(values: pd.Series, n: int) -> pd.Series`
  - `tests/backtesting/screen/helpers.py`: `frame(closes, *, start="2010-01-04", opens=None, highs=None, lows=None, volumes=None, index=None) -> pd.DataFrame` (columns `Open, High, Low, Close, Volume`, business-day index; defaults `Open = Close`, `High = Close + 1`, `Low = Close − 1`, `Volume = 1e6`), `random_walk(n, seed=7, start="2010-01-04") -> pd.DataFrame`, `assert_prefix_stable(fn, df, checkpoints, *, skip_last=False) -> None`.

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then from the main tree:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-08-v140-idea-screen -b 2026-10-08-v140-idea-screen main
```

Also invoke the `no-lookahead` skill: this task decides what a bar knew.

- [ ] **Step 1: Write the test helpers**

`tests/backtesting/screen/__init__.py`: empty file.

`tests/backtesting/screen/helpers.py`:

```python
"""Synthetic OHLCV frames and the truncation guard for the v140 screen tests."""
from __future__ import annotations

import numpy as np
import pandas as pd


def frame(closes, *, start="2010-01-04", opens=None, highs=None, lows=None,
          volumes=None, index=None) -> pd.DataFrame:
    """An OHLCV frame. Defaults: Open = Close, High = Close + 1,
    Low = Close - 1, Volume = 1e6, business-day index from ``start``."""
    closes = np.asarray(closes, dtype=float)
    idx = (pd.DatetimeIndex(index) if index is not None
           else pd.bdate_range(start, periods=len(closes)))

    def pick(given, default):
        return default if given is None else np.asarray(given, dtype=float)

    return pd.DataFrame({
        "Open": pick(opens, closes),
        "High": pick(highs, closes + 1.0),
        "Low": pick(lows, closes - 1.0),
        "Close": closes,
        "Volume": pick(volumes, np.full(len(closes), 1e6)),
    }, index=idx)


def random_walk(n, seed=7, start="2010-01-04") -> pd.DataFrame:
    """A plausible daily price path: drift, gaps, volume noise."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0.0, 0.006, n))
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.008, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.008, n)))
    volume = rng.integers(500_000, 3_000_000, n).astype(float)
    return frame(close, start=start, opens=open_, highs=high, lows=low,
                 volumes=volume)


def assert_prefix_stable(fn, df, checkpoints, *, skip_last=False) -> None:
    """``fn(df.iloc[:t+1])`` equals ``fn(df)`` on bars ``<= t``: nothing the
    function says about bar t reads a later bar. ``skip_last`` leaves the
    truncated frame's final bar out of the comparison (frozen reading F1)."""
    full = pd.Series(fn(df), index=df.index)
    for t in checkpoints:
        part = pd.Series(fn(df.iloc[: t + 1]), index=df.index[: t + 1])
        stop = t if skip_last else t + 1
        pd.testing.assert_series_equal(
            part.iloc[:stop], full.iloc[:stop], check_names=False,
            check_exact=False, rtol=1e-12, atol=0.0, obj=f"prefix ending at bar {t}")
```

- [ ] **Step 2: Write the failing indicator tests**

`tests/backtesting/screen/test_indicators.py`:

```python
"""v140 screen indicators: hand-computed values and the truncation guard."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _values(series):
    return [None if np.isnan(v) else round(float(v), 6) for v in series]


def test_wilder_mean_seeds_with_the_simple_mean_then_smooths():
    out = indicators.wilder_mean(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 2)
    assert _values(out) == [None, 1.5, 2.25, 3.125, 4.0625]


def test_wilder_mean_skips_leading_nans():
    out = indicators.wilder_mean(pd.Series([np.nan, 2.0, 4.0, 6.0]), 2)
    assert _values(out) == [None, None, 3.0, 4.5]


def test_wilder_mean_is_all_nan_when_too_short():
    out = indicators.wilder_mean(pd.Series([1.0, 2.0]), 3)
    assert out.isna().all()


def test_true_range_and_atr_hand_computed():
    df = frame([9.0, 10.0, 13.0], highs=[10.0, 11.0, 14.0], lows=[8.0, 9.0, 12.0])
    assert _values(indicators.true_range(df)) == [2.0, 2.0, 4.0]
    assert _values(indicators.atr(df, n=2)) == [None, 2.0, 3.0]


def test_rsi_hand_computed():
    out = indicators.rsi(pd.Series([10.0, 11.0, 10.0, 12.0, 13.0]), 2)
    assert _values(out) == [None, None, 50.0, 83.333333, 90.0]


def test_rsi_is_100_when_there_are_no_losses():
    out = indicators.rsi(pd.Series([1.0, 2.0, 3.0, 4.0]), 2)
    assert _values(out) == [None, None, 100.0, 100.0]


def test_sma_and_rolling_max():
    s = pd.Series([1.0, 3.0, 2.0, 5.0])
    assert _values(indicators.sma(s, 2)) == [None, 2.0, 2.5, 3.5]
    assert _values(indicators.rolling_max(s, 2)) == [None, 3.0, 3.0, 5.0]


@pytest.mark.parametrize("name, fn", [
    ("atr14", lambda d: indicators.atr(d)),
    ("rsi2", lambda d: indicators.rsi(d["Close"], 2)),
    ("sma200", lambda d: indicators.sma(d["Close"], 200)),
    ("max252", lambda d: indicators.rolling_max(d["High"], 252)),
])
def test_every_indicator_reads_no_later_bar(name, fn):
    df = random_walk(320)
    assert_prefix_stable(fn, df, [30, 210, 260, 319])
```

- [ ] **Step 3: Write the failing import-guard test**

`tests/backtesting/screen/test_import_guard.py`:

```python
"""v140: the screen is research tooling. Nothing under swingbot/ outside
swingbot/core/backtesting/ may import it (no research code in the live path)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREEN = "swingbot.core.backtesting.screen"
BACKTESTING = ROOT / "swingbot" / "core" / "backtesting"


def imported_names(text: str) -> set:
    """Every dotted module name an import statement can bind, including
    ``from pkg import mod`` as ``pkg.mod``."""
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _reaches_screen(names) -> bool:
    return any(n == SCREEN or n.startswith(SCREEN + ".") for n in names)


def test_the_guard_sees_both_import_forms():
    assert _reaches_screen(imported_names("from swingbot.core.backtesting import screen"))
    assert _reaches_screen(imported_names("import swingbot.core.backtesting.screen.race"))
    assert not _reaches_screen(imported_names("from swingbot.core.backtesting import acceptance"))


def test_nothing_outside_backtesting_imports_the_screen():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "swingbot").rglob("*.py"))
        if BACKTESTING not in path.parents
        and _reaches_screen(imported_names(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_indicators.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.screen'`.

- [ ] **Step 5: Write the package and the indicators**

`swingbot/core/backtesting/screen/__init__.py`:

```python
"""v140 idea screen: a cheap information test before any spec.

Research tooling only -- nothing outside swingbot/core/backtesting/ imports
this package (tests/backtesting/screen/test_import_guard.py). See
docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md.
"""
```

`swingbot/core/backtesting/screen/indicators.py`:

```python
"""Causal indicators for the v140 idea screen.

Every value at bar t reads bars <= t only (pinned by a truncation test).
Wilder smoothing is seeded with the simple mean of the first n valid values,
then y[t] = ((n - 1) * y[t-1] + x[t]) / n.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def wilder_mean(values: pd.Series, n: int) -> pd.Series:
    """Wilder's running mean; NaN until n valid values have been seen."""
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.notna().to_numpy()
    if not valid.any():
        return out
    first = int(np.argmax(valid))
    seed_at = first + n - 1
    if seed_at >= len(values):
        return out
    tail = values.iloc[seed_at:].astype(float).copy()
    tail.iloc[0] = float(values.iloc[first:seed_at + 1].mean())
    out.iloc[seed_at:] = tail.ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    """max(H - L, |H - prev C|, |L - prev C|); bar 0 is H - L."""
    prev = df["Close"].shift(1)
    ranges = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(),
                        (df["Low"] - prev).abs()], axis=1)
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR(n)."""
    return wilder_mean(true_range(df), n)


def rsi(close: pd.Series, n: int) -> pd.Series:
    """Wilder RSI(n); 100 where the average loss is zero."""
    delta = close.diff()
    gain = wilder_mean(delta.clip(lower=0.0), n)
    loss = wilder_mean((-delta).clip(lower=0.0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        value = 100.0 - 100.0 / (1.0 + gain / loss)
    return value.where(loss != 0, 100.0).where(gain.notna())


def sma(values: pd.Series, n: int) -> pd.Series:
    """Simple moving average over the last n bars, t included."""
    return values.rolling(n, min_periods=n).mean()


def rolling_max(values: pd.Series, n: int) -> pd.Series:
    """Maximum over the last n bars, t included."""
    return values.rolling(n, min_periods=n).max()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_indicators.py`
Expected: PASS (all).
Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (2 tests).

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/indicators.py tests/backtesting/screen/helpers.py tests/backtesting/screen/test_import_guard.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/screen/__init__.py swingbot/core/backtesting/screen/indicators.py tests/backtesting/screen/__init__.py tests/backtesting/screen/helpers.py tests/backtesting/screen/test_indicators.py tests/backtesting/screen/test_import_guard.py
git commit -m "feat(screen): causal indicators and import guard for the v140 idea screen (V140-1)"
```

### Task V140-2: Idea registry with the four frozen parameter sets

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/__init__.py`
- Create: `swingbot/core/backtesting/screen/ideas/high52w.py`
- Create: `swingbot/core/backtesting/screen/ideas/uptrend_pullback.py`
- Create: `swingbot/core/backtesting/screen/ideas/gap_volume.py`
- Create: `swingbot/core/backtesting/screen/ideas/turn_of_month.py`
- Test: `tests/backtesting/screen/test_ideas_registry.py`

**Interfaces:**
- Consumes: nothing from V140-1 at runtime (the trigger modules import `indicators` only from V140-6..9 on).
- Produces:
  - `ideas.Idea` — frozen dataclass: `name: str`, `events: Callable[[pd.DataFrame], pd.Series]`, `time_cap_bars: int`, `direction: str = "long"`, `params: Mapping` (read-only `MappingProxyType`), `summary: str`, `source: str`. Raises `ValueError` on a non-`"long"` direction or a cap < 1.
  - `ideas.IDEA_MODULES = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month")`
  - `ideas.IDEAS: dict[str, Idea]`, in `IDEA_MODULES` order.
  - Each trigger module: `CAP: int`, `PARAMS: dict`, `SUMMARY: str`, `SOURCE: str`, `events(df) -> pd.Series[bool]`. This task writes the final constants and an `events` that raises `NotImplementedError` naming the task that implements it. **It must raise, never return all-False**: an all-False stub would screen as `SCREEN-UNDERPOWERED` and close the idea forever.

- [ ] **Step 1: Write the failing test**

`tests/backtesting/screen/test_ideas_registry.py`:

```python
"""v140 idea registry: four frozen triggers, one parameter set each."""
import dataclasses

import pytest

from swingbot.core.backtesting.screen import ideas
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea


def test_registry_holds_the_first_batch_in_spec_order():
    assert ideas.IDEA_MODULES == ("high52w", "uptrend_pullback", "gap_volume",
                                  "turn_of_month")
    assert list(IDEAS) == list(ideas.IDEA_MODULES)
    assert all(IDEAS[name].name == name for name in IDEAS)


def test_time_caps_are_the_spec_values():
    assert {n: i.time_cap_bars for n, i in IDEAS.items()} == {
        "high52w": 60, "uptrend_pullback": 10, "gap_volume": 20, "turn_of_month": 4}


def test_frozen_parameter_sets():
    assert dict(IDEAS["high52w"].params) == {
        "near_high": 0.95, "lookback": 252, "fast_sma": 50, "slow_sma": 200,
        "quiet_bars": 20}
    assert dict(IDEAS["uptrend_pullback"].params) == {
        "trend_sma": 200, "rsi_n": 2, "rsi_below": 10}
    assert dict(IDEAS["gap_volume"].params) == {
        "gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
    assert dict(IDEAS["turn_of_month"].params) == {
        "day": "last trading day of the calendar month"}


def test_every_idea_is_long_and_cites_its_source():
    for idea in IDEAS.values():
        assert idea.direction == "long"
        assert idea.summary.strip() and idea.source.strip()
        assert callable(idea.events)


def test_params_are_read_only_and_the_idea_is_frozen():
    idea = IDEAS["high52w"]
    with pytest.raises(TypeError):
        idea.params["near_high"] = 0.9
    with pytest.raises(dataclasses.FrozenInstanceError):
        idea.time_cap_bars = 5


def test_an_idea_refuses_a_short_direction_and_a_zero_cap():
    def events(df):
        return df["Close"] > 0
    with pytest.raises(ValueError):
        Idea(name="x", events=events, time_cap_bars=5, direction="short")
    with pytest.raises(ValueError):
        Idea(name="x", events=events, time_cap_bars=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.screen.ideas'`.

- [ ] **Step 3: Write the registry**

`swingbot/core/backtesting/screen/ideas/__init__.py`:

```python
"""The v140 idea registry: one frozen trigger per published effect.

A trigger module exports CAP, PARAMS, SUMMARY, SOURCE and events(df). A
changed parameter is a new idea with a new name (and a new ledger row),
never an edit here: each idea is screened once.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping

import pandas as pd

#: Batch order of the spec, and the run order of V140-15..18.
IDEA_MODULES = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month")


@dataclass(frozen=True)
class Idea:
    name: str
    events: Callable[[pd.DataFrame], pd.Series]
    time_cap_bars: int
    direction: str = "long"
    params: Mapping = field(default_factory=dict)
    summary: str = ""
    source: str = ""

    def __post_init__(self):
        if self.direction != "long":
            raise ValueError(f"{self.name}: v140 screens long ideas only")
        if self.time_cap_bars < 1:
            raise ValueError(f"{self.name}: time cap must be at least one bar")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE)


IDEAS: dict[str, Idea] = {name: _load(name) for name in IDEA_MODULES}
```

- [ ] **Step 4: Write the four constant-carrying modules**

`swingbot/core/backtesting/screen/ideas/high52w.py`:

```python
"""52-week-high momentum (George & Hwang 2004). Trigger: V140-6."""
from __future__ import annotations

import pandas as pd

CAP = 60
PARAMS = {"near_high": 0.95, "lookback": 252, "fast_sma": 50, "slow_sma": 200,
          "quiet_bars": 20}
SUMMARY = ("close >= 0.95 x the 252-bar high with SMA50 > SMA200; first true "
           "bar after >= 20 consecutive computable false bars")
SOURCE = "George & Hwang (2004)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-6 implements the high52w trigger")
```

`swingbot/core/backtesting/screen/ideas/uptrend_pullback.py`:

```python
"""Uptrend RSI(2) pullback (Connors & Alvarez 2008). Trigger: V140-7."""
from __future__ import annotations

import pandas as pd

CAP = 10
PARAMS = {"trend_sma": 200, "rsi_n": 2, "rsi_below": 10}
SUMMARY = "close > SMA200 and Wilder RSI(2) < 10"
SOURCE = "Connors & Alvarez (2008)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-7 implements the uptrend_pullback trigger")
```

`swingbot/core/backtesting/screen/ideas/gap_volume.py`:

```python
"""Gap + volume continuation (earnings/news gap drift). Trigger: V140-8."""
from __future__ import annotations

import pandas as pd

CAP = 20
PARAMS = {"gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
SUMMARY = ("open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar "
           "mean volume ending the prior bar, close >= open")
SOURCE = "earnings/news gap drift; volume as the news proxy"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-8 implements the gap_volume trigger")
```

`swingbot/core/backtesting/screen/ideas/turn_of_month.py`:

```python
"""Turn of the month (Ariel 1987; Lakonishok & Smidt 1988). Trigger: V140-9."""
from __future__ import annotations

import pandas as pd

CAP = 4
PARAMS = {"day": "last trading day of the calendar month"}
SUMMARY = "t is the last trading day of its calendar month (ticker's own bar dates)"
SOURCE = "Ariel (1987); Lakonishok & Smidt (1988)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-9 implements the turn_of_month trigger")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS (6 tests).

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/ideas`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(screen): idea registry with the four frozen parameter sets (V140-2)"
```

### Task V140-3: The fixed trade race and the one-open-race book

**Files:**
- Create: `swingbot/core/backtesting/screen/race.py`
- Test: `tests/backtesting/screen/test_race.py`

**Interfaces:**
- Consumes: `indicators.atr` (V140-1); `swingbot.core.edge.frictions.apply_frictions(fill_price, side, slippage_bps=None)`, `commission_r(risk_dollars=None, commission=None)` (existing).
- Produces:
  - Constants `STOP_ATR = 1.5`, `REWARD_RISK = 2.0`, `OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout")`, `COUNTERS = ("dropped_nonmember", "dropped_warmup", "dropped_window", "skipped_overlap")`.
  - `RaceResult` — frozen dataclass of equal-length numpy arrays `event_pos` (int), `exit_pos` (int), `entry`, `risk`, `gross_r`, `r` (net of costs), `outcome` (str, one of `OUTCOMES`); `RaceResult.empty()`, `len(result)`, `result.take(mask_or_index) -> RaceResult`.
  - `race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None) -> RaceResult` — raises `ValueError` if any `event_pos + cap > len(df) - 1` or `cap < 1`. `commission` is an R deduction; `None` means `commission_r()`. `slippage_bps=None` means `config.SLIPPAGE_BPS`.
  - `warm_mask(atr, sma200) -> np.ndarray[bool]` — finite ATR > 0 and finite SMA200 (frozen reading F8).
  - `candidate_events(events, member, warm, cap) -> tuple[np.ndarray, dict]` — positions passing membership, warm-up and window, plus counts for the first three counters.
  - `non_overlapping(event_pos, exit_pos) -> np.ndarray[bool]` (frozen reading F4).
  - `run_book(df, events, cap, *, member, warm, atr, slippage_bps=None, commission=None) -> tuple[RaceResult, dict]` — dict has every key in `COUNTERS`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/backtesting/screen/test_race.py`:

```python
"""v140 fixed trade: entry next open, 1.5 ATR stop, 3 ATR target, gaps at the open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import frame

QUIET = (100.0, 101.0, 99.0, 100.0)     # never reaches stop 97 or target 106


def _frame(bars):
    """Bar 0 is the signal bar; ``bars`` are (O, H, L, C) for bars 1.."""
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # risk 3.0: stop 97, target 106


def _one(bars, cap, **costs):
    df = _frame(bars)
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return race_mod.race(df, [0], cap, atr=_atr(df), **costs)


def test_stop_is_checked_first_on_a_bar_touching_both():
    out = _one([(100.0, 107.0, 96.0, 100.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]
    assert out.exit_pos.tolist() == [1]


def test_target_hit_exits_at_the_target():
    out = _one([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["target"]
    assert out.gross_r.tolist() == [pytest.approx(2.0)]
    assert out.exit_pos.tolist() == [2]


def test_gap_through_the_stop_exits_at_the_open_below_minus_one_r():
    out = _one([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-5.0 / 3.0)
    assert out.gross_r[0] < -1.0


def test_gap_over_the_target_exits_at_the_open():
    out = _one([QUIET, (108.0, 109.0, 107.0, 108.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_target"]
    assert out.gross_r[0] == pytest.approx(8.0 / 3.0)


def test_time_cap_exits_at_the_close_of_the_last_bar():
    out = _one([QUIET, QUIET, (100.0, 102.0, 99.0, 101.5), QUIET], cap=3)
    assert out.outcome.tolist() == ["timeout"]
    assert out.gross_r[0] == pytest.approx(0.5)
    assert out.exit_pos.tolist() == [3]


def test_costs_are_slippage_on_both_fills_plus_commission_in_r():
    out = _one([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET], cap=3,
               slippage_bps=5.0, commission=0.02)
    entry_fill, exit_fill = 100.0 * 1.0005, 106.0 * 0.9995
    assert out.r[0] == pytest.approx((exit_fill - entry_fill) / 3.0 - 0.02)
    assert out.r[0] == pytest.approx(1.945667, abs=1e-6)
    assert out.gross_r[0] == pytest.approx(2.0)


def test_default_costs_come_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    df = _frame([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET])
    out = race_mod.race(df, [0], 3, atr=_atr(df))
    assert out.r[0] == pytest.approx(2.0 - 0.02)


def test_a_race_that_would_read_past_the_frame_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError):
        race_mod.race(df, [0], 3, atr=_atr(df))


def test_no_events_is_an_empty_result():
    df = _frame([QUIET, QUIET])
    out = race_mod.race(df, [], 2, atr=_atr(df))
    assert len(out) == 0 and out.r.size == 0


def test_warm_mask_needs_positive_atr_and_sma200():
    atr = pd.Series([np.nan, 0.0, 2.0, 2.0])
    sma = pd.Series([100.0, 100.0, np.nan, 100.0])
    assert race_mod.warm_mask(atr, sma).tolist() == [False, False, False, True]


def _book_frame(n=30):
    return frame(np.full(n, 100.0))     # quiet bars: every race times out


def test_run_book_counts_every_drop_and_skip():
    df = _book_frame()
    events = np.zeros(len(df), dtype=bool)
    events[[2, 4, 7, 9, 20, 27]] = True
    member = np.ones(len(df), dtype=bool)
    member[9] = False
    warm = np.ones(len(df), dtype=bool)
    warm[20] = False
    booked, counts = race_mod.run_book(
        df, events, 5, member=member, warm=warm, atr=_atr(df),
        slippage_bps=0.0, commission=0.0)
    assert booked.event_pos.tolist() == [2, 7]          # 4 sits inside 2's race
    assert booked.exit_pos.tolist() == [7, 12]
    assert counts == {"dropped_nonmember": 1, "dropped_warmup": 1,
                      "dropped_window": 1, "skipped_overlap": 1}


def test_an_event_on_the_exit_bar_opens_a_new_race():
    keep = race_mod.non_overlapping(np.array([2, 6, 7]), np.array([7, 11, 12]))
    assert keep.tolist() == [True, False, True]


def test_take_filters_every_field():
    df = _book_frame()
    out = race_mod.race(df, [1, 3], 5, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    kept = out.take(np.array([False, True]))
    assert kept.event_pos.tolist() == [3] and len(kept.outcome) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_race.py`
Expected: FAIL — `ImportError: cannot import name 'race'`.

- [ ] **Step 3: Write `race.py`**

`swingbot/core/backtesting/screen/race.py`:

```python
"""The v140 screen's fixed trade (spec § The fixed trade). Long only.

Event on bar t (known at t's close). Entry = open of t+1; risk = 1.5 x
ATR14[t]; stop = entry - risk; target = entry + 2 x risk. Bars t+1..t+cap:
an open at/below the stop exits at the open (a gap loss, can exceed -1R);
else an open at/above the target exits at the open; else a low touching the
stop exits at the stop (checked first); else a high touching the target
exits at the target. After bar t+cap, exit at its close. Costs: both fills
worsened by SLIPPAGE_BPS, then commission_r() in R.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.edge.frictions import apply_frictions, commission_r

STOP_ATR = 1.5
REWARD_RISK = 2.0
OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout")
COUNTERS = ("dropped_nonmember", "dropped_warmup", "dropped_window",
            "skipped_overlap")
_FIELDS = ("event_pos", "exit_pos", "entry", "risk", "gross_r", "r", "outcome")


@dataclass(frozen=True, eq=False)
class RaceResult:
    event_pos: np.ndarray
    exit_pos: np.ndarray
    entry: np.ndarray
    risk: np.ndarray
    gross_r: np.ndarray
    r: np.ndarray
    outcome: np.ndarray

    @classmethod
    def empty(cls) -> "RaceResult":
        ints, floats = np.array([], dtype=int), np.array([], dtype=float)
        return cls(ints, ints.copy(), floats, floats.copy(), floats.copy(),
                   floats.copy(), np.asarray(OUTCOMES)[ints])

    def __len__(self) -> int:
        return len(self.event_pos)

    def take(self, selector) -> "RaceResult":
        return RaceResult(*(getattr(self, name)[selector] for name in _FIELDS))


def warm_mask(atr, sma200) -> np.ndarray:
    """Warm-up complete: finite ATR14 > 0 and a finite SMA200 (reading F8)."""
    a = pd.Series(atr).to_numpy(dtype=float)
    s = pd.Series(sma200).to_numpy(dtype=float)
    return np.isfinite(a) & (a > 0) & np.isfinite(s)


def _check_positions(event_pos: np.ndarray, cap: int, n: int) -> None:
    if cap < 1:
        raise ValueError("a race needs a time cap of at least one bar")
    if event_pos.size and (event_pos.min() < 0 or event_pos.max() + cap > n - 1):
        raise ValueError("a race would read past the frame; count the event "
                         "as dropped_window instead")


def _first_exit(O, H, L, C, stop, target):
    """Exit price, outcome code (index into OUTCOMES) and bar offset."""
    stop_c, target_c = stop[:, None], target[:, None]
    gap_stop = O <= stop_c
    gap_target = ~gap_stop & (O >= target_c)
    hit_stop = L <= stop_c
    hit_target = H >= target_c
    hit = gap_stop | gap_target | hit_stop | hit_target
    any_hit = hit.any(axis=1)
    rows = np.arange(len(O))
    j = np.where(any_hit, hit.argmax(axis=1), O.shape[1] - 1)
    code = np.select([gap_stop[rows, j], gap_target[rows, j],
                      hit_stop[rows, j], hit_target[rows, j]],
                     [0, 1, 2, 3], default=4)
    code = np.where(any_hit, code, 4)
    price = np.choose(code, [O[rows, j], O[rows, j], stop, target, C[rows, j]])
    return price, code, j


def race(df: pd.DataFrame, event_pos, cap: int, *, atr=None,
         slippage_bps=None, commission=None) -> RaceResult:
    """Race every event in ``event_pos`` (bar positions) at once."""
    event_pos = np.asarray(event_pos, dtype=int)
    _check_positions(event_pos, cap, len(df))
    if event_pos.size == 0:
        return RaceResult.empty()
    atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)
    o, h, l, c = (df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low", "Close"))
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[event_pos + 1]
    risk = STOP_ATR * atr_v[event_pos]
    price, code, offset = _first_exit(o[bars], h[bars], l[bars], c[bars],
                                      entry - risk, entry + REWARD_RISK * risk)
    cost = commission_r() if commission is None else commission
    net = (apply_frictions(price, "sell", slippage_bps)
           - apply_frictions(entry, "buy", slippage_bps)) / risk - cost
    return RaceResult(event_pos, event_pos + 1 + offset, entry, risk,
                      (price - entry) / risk, net, np.asarray(OUTCOMES)[code])


def _drop_reason(pos: int, member, warm, cap: int, n: int) -> str | None:
    if not member[pos]:
        return "dropped_nonmember"
    if not warm[pos]:
        return "dropped_warmup"
    if pos + cap > n - 1:
        return "dropped_window"
    return None


def candidate_events(events, member, warm, cap: int):
    """Event positions that can be raced, and the drop counts for the rest."""
    events = np.asarray(events, dtype=bool)
    counts = dict.fromkeys(COUNTERS, 0)
    keep = []
    for pos in np.flatnonzero(events):
        reason = _drop_reason(pos, member, warm, cap, len(events))
        if reason is None:
            keep.append(pos)
        else:
            counts[reason] += 1
    return np.asarray(keep, dtype=int), counts


def non_overlapping(event_pos, exit_pos) -> np.ndarray:
    """One open race per ticker: skip an event while it is before the
    running race's exit bar (reading F4)."""
    keep = np.zeros(len(event_pos), dtype=bool)
    busy_until = -1
    for i, (pos, out) in enumerate(zip(event_pos, exit_pos)):
        if pos >= busy_until:
            keep[i] = True
            busy_until = out
    return keep


def run_book(df, events, cap: int, *, member, warm, atr, slippage_bps=None,
             commission=None):
    """Race the eligible events, then keep one open race at a time."""
    cand, counts = candidate_events(events, member, warm, cap)
    raced = race(df, cand, cap, atr=atr, slippage_bps=slippage_bps,
                 commission=commission)
    keep = non_overlapping(raced.event_pos, raced.exit_pos)
    counts["skipped_overlap"] = int((~keep).sum())
    return raced.take(keep), counts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_race.py`
Expected: PASS (13 tests).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/screen/race.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/race.py tests/backtesting/screen/test_race.py
git commit -m "feat(screen): fixed ATR trade race and one-open-race book (V140-3)"
```
