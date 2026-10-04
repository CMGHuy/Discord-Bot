# Pullback volume dry-up gate -- part 1: gate and call sites

> Part of `2026-10-02-v122-pullback-volume-dryup-gate_0-index.md` (header, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global constraints with every task. Steps use `- [ ]` for tracking.

**Spec:** `docs/superpowers/specs/2026-10-02-v122-pullback-volume-dryup-gate-design.md`

# Phase 1 — Knobs, predicate, witness

### Task V122-1: v121 contract check and the two knobs

**Files:**
- Modify: `swingbot/config.py` (insert two `Field`s directly after the `FIB_TARGET_1_0_EXTENSION` Field, currently `config.py:218-225`; add one branch to `_cast`)
- Modify: `.env.example` (after the `FIB_TARGET_1_0_EXTENSION=false` block)
- Create: `tests/test_config_pullback_dryup.py`

**Interfaces:**
- Consumes: v121's `swingbot.core.market.structure.pullback_vol_ratio(df, direction) -> float | None`. It is computed at the last row of `df` and is `None` when no pullback is defined.
- Produces: `config.PULLBACK_DRYUP_SCOPE: str` (`"off"`, `"strategy"` or `"confluence"`) and `config.PULLBACK_DRYUP_MAX_RATIO: float`. At this task both keep `search_class="excluded"`. V122-7 makes them `searchable` together with their registry entries, so `test_reachability.py` stays green between tasks.

- [ ] **Step 1: Check that v121 is merged and its contract matches**

Run:
```bash
git log --oneline main | grep -m3 "v121"
git grep -n "def pullback_vol_ratio" -- swingbot/core/market/structure.py
python -c "import inspect; from swingbot.core.market import structure as s; print(inspect.signature(s.pullback_vol_ratio))"
```
Expected: v121 commits on `main`, one `def pullback_vol_ratio` hit, and a signature whose first two positional parameters are the frame and the direction (`"bullish"`/`"bearish"`). **If any check fails, or the function exists only inside `structure_features`, stop and report BLOCKED. Do not write a local re-derivation:** the spec forbids one.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_config_pullback_dryup.py
"""v122 knobs: a three-way scope and a ratio, both off by default."""
from swingbot import config

GRID = (0.60, 0.75, 0.90)


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


def test_scope_is_a_three_way_select_defaulting_off():
    f = _field("PULLBACK_DRYUP_SCOPE")
    assert f.type == "select" and f.default == "off" and f.hot_reloadable
    assert [value for value, _ in f.options] == ["off", "strategy", "confluence"]
    assert config.PULLBACK_DRYUP_SCOPE == "off"


def test_a_malformed_scope_falls_back_to_off():
    f = _field("PULLBACK_DRYUP_SCOPE")
    assert config._cast(f, "Strategy") == "strategy"
    assert config._cast(f, "CONFLUENCE") == "confluence"
    for bad in ("both", "", "strategy,confluence"):
        assert config._cast(f, bad) == "off"


def test_max_ratio_defaults_to_zero_meaning_off():
    f = _field("PULLBACK_DRYUP_MAX_RATIO")
    assert f.type == "float" and config._cast(f, f.default) == 0.0
    assert config.PULLBACK_DRYUP_MAX_RATIO == 0.0


def test_the_frozen_grid_fits_inside_the_field_bounds():
    f = _field("PULLBACK_DRYUP_MAX_RATIO")
    assert all(f.min <= d <= f.max for d in GRID)
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `python scripts/dev/testrun.py file tests/test_config_pullback_dryup.py`
Expected: FAIL with `StopIteration`, because neither field exists yet.

- [ ] **Step 4: Implement**

Insert into `FIELDS` right after the `FIB_TARGET_1_0_EXTENSION` Field:

```python
    Field("PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_SCOPE", "Trade Filters & Risk",
          "Pullback volume dry-up gate: scope (v122)",
          type="select", default="off",
          options=[("off", "Off"),
                   ("strategy", "Strategy entries -- Fibonacci, EMA Crossover (pullback mode), "
                                "Break & Retest, RSI, RSI Divergence, MA Ribbon, VWAP"),
                   ("confluence", "Confluence entries (level touches)")],
          help="v122. Rejects a pullback entry whose pullback leg averaged more than "
               "PULLBACK_DRYUP_MAX_RATIO x its impulse leg's volume "
               "(market/structure.py:pullback_vol_ratio). An undefined ratio always passes. "
               "Ships OFF: each scope is its own pre-registered measurement and flips on only "
               "if its one VALIDATION shot passes."),
    Field("PULLBACK_DRYUP_MAX_RATIO", "PULLBACK_DRYUP_MAX_RATIO", "Trade Filters & Risk",
          "Pullback volume dry-up gate: max pullback/impulse volume ratio",
          type="float", default="0", min=0, max=2, step=0.05,
          help="The gate rejects when the ratio is strictly above this value. 0 turns the "
               "gate off whatever the scope. v122's frozen grid is 0.60 / 0.75 / 0.90."),
```

In `_cast`, after the `STRATEGY_ALERTS_MODE` branch and before `caster = _CASTERS.get(f.type)`:

```python
    if f.attr == "PULLBACK_DRYUP_SCOPE":
        v = str(raw).lower()
        if v not in ("off", "strategy", "confluence"):
            log.warning("invalid PULLBACK_DRYUP_SCOPE=%r, falling back to 'off'", raw)
            return "off"
        return v
```

In `.env.example`, after the `FIB_TARGET_1_0_EXTENSION=false` line:

```
# v122 pullback volume dry-up gate. Rejects a pullback entry whose pullback
# leg averaged more than PULLBACK_DRYUP_MAX_RATIO x its impulse leg's volume.
# Scope: off | strategy | confluence. 0 disables the ratio whatever the scope.
# Ships OFF: each scope is its own pre-registered measurement.
PULLBACK_DRYUP_SCOPE=off
PULLBACK_DRYUP_MAX_RATIO=0
```

- [ ] **Step 5: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/test_config_pullback_dryup.py` then `python scripts/dev/testrun.py file tests/test_env_example_sync.py` then `python -m radon cc -s swingbot/config.py | grep _cast`
Expected: both PASS, and `_cast` at B (10) or lower.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_pullback_dryup.py
git commit -m "feat(v122): PULLBACK_DRYUP_SCOPE / PULLBACK_DRYUP_MAX_RATIO knobs, default off"
```

### Task V122-2: The predicate and its scope rules

**Files:**
- Modify: `swingbot/core/edge/gates.py`
- Create: `tests/edge/pullback_frames.py` (shared fixture builder, not a test module)
- Create: `tests/edge/test_pullback_dryup_gate.py`

**Interfaces:**
- Consumes: `config.PULLBACK_DRYUP_SCOPE` and `config.PULLBACK_DRYUP_MAX_RATIO` (V122-1), and `structure.pullback_vol_ratio` (v121).
- Produces (all in `swingbot.core.edge.gates`):
  - `PULLBACK_DRYUP_STRATEGIES: frozenset[str]` (the seven names) and `PULLBACK_VOLUME_REASON = "pullback_volume"`
  - `ratio_exceeds(ratio: float | None, max_ratio: float) -> bool`, the comparison alone. It is shared with the V122-9 baseline flagging, so the two can never disagree
  - `pullback_dryup_rejects(df, direction: str, max_ratio: float) -> bool`, the spec's predicate
  - `strategy_in_dryup_scope(strategy: str | None) -> bool`, the frozen list plus the EMA Crossover pullback-mode check
  - `pullback_dryup_scoped(source: str, strategy: str | None = None) -> bool`, which reads the scope from config
  - `pullback_dryup_blocks(df, direction, *, source, strategy=None) -> bool`, used by the strategy call sites
  - `filter_pullback_dryup(scenarios, df) -> tuple[list, list]`, which returns `(kept, rejected)` and is used by the confluence call sites
- Produces (tests): `tests.edge.pullback_frames.pullback_frame(pullback_volume) -> DataFrame`, `mirror(df) -> DataFrame`, `IMPULSE_VOLUME`

- [ ] **Step 1: Write the fixture builder**

```python
# tests/edge/pullback_frames.py
"""Hand-built frames with one known impulse leg and one known pullback leg (v122).

Bars 0..79 are flat (no strict fractal pivot). Bar 80 is the swing low SL0,
bars 81..90 climb to the swing high SH at bar 90, and bars 91..96 pull back.
With k=3 pivots SH is confirmed from bar 93, and at t=96 Close (104) is below
High[SH] (112). So the impulse leg is bars 80..90 at IMPULSE_VOLUME and the
pullback leg is bars 91..96 at `pullback_volume`, which makes the ratio
pullback_volume / IMPULSE_VOLUME.
"""
import pandas as pd

IMPULSE_VOLUME = 2_000_000.0
FLAT_BARS = 80


def pullback_frame(pullback_volume: float) -> pd.DataFrame:
    closes, highs, lows = [100.0] * FLAT_BARS, [101.0] * FLAT_BARS, [99.0] * FLAT_BARS
    volumes = [1_000_000.0] * FLAT_BARS
    closes.append(97.0); highs.append(101.0); lows.append(95.0); volumes.append(IMPULSE_VOLUME)
    for step in range(1, 11):
        close = 100.0 + step
        closes.append(close); highs.append(close + (2.0 if step == 10 else 1.0))
        lows.append(close - 1.0); volumes.append(IMPULSE_VOLUME)
    for step in range(1, 7):
        close = 110.0 - step
        closes.append(close); highs.append(close + 1.0); lows.append(close - 1.0)
        volumes.append(pullback_volume)
    opens = [closes[0]] + closes[:-1]
    index = pd.bdate_range("2019-01-01", periods=len(closes))
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes,
                         "Volume": volumes}, index=index)


def mirror(df: pd.DataFrame, pivot: float = 200.0) -> pd.DataFrame:
    """The bearish twin: prices reflected around `pivot`, volume unchanged."""
    out = df.copy()
    out["Open"], out["Close"] = pivot - df["Open"], pivot - df["Close"]
    out["High"], out["Low"] = pivot - df["Low"], pivot - df["High"]
    return out
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/edge/test_pullback_dryup_gate.py
"""v122 predicate and scope rules (spec: Testing -- Predicate, Scope)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.market import entry_filters, structure
from tests.edge.pullback_frames import IMPULSE_VOLUME, mirror, pullback_frame

FROZEN = {"Fibonacci", "EMA Crossover", "Break & Retest", "RSI", "RSI Divergence",
          "MA Ribbon", "VWAP"}


@pytest.fixture
def ratio(monkeypatch):
    """Pin pullback_vol_ratio to a chosen value and record each call."""
    state = {"value": None, "calls": []}

    def fake(df, direction):
        state["calls"].append(direction)
        return state["value"]
    monkeypatch.setattr(gates, "pullback_vol_ratio", fake)
    return state


@pytest.fixture
def scope(monkeypatch):
    def set_scope(value, max_ratio=0.75):
        monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", value)
        monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", max_ratio)
    return set_scope


@pytest.mark.parametrize("value,rejects", [
    (None, False), (0.75, False), (0.75 + 1e-9, True), (0.30, False), (5.0, True),
    (float("nan"), False)])
def test_predicate_boundaries(ratio, value, rejects):
    ratio["value"] = value
    assert gates.pullback_dryup_rejects(object(), "bullish", 0.75) is rejects


@pytest.mark.parametrize("value,max_ratio,expected", [
    (0.75, 0.75, False), (0.7500001, 0.75, True), (None, 0.75, False),
    (float("nan"), 0.75, False), (9.0, 0.0, False)])
def test_ratio_exceeds_is_the_shared_comparison(value, max_ratio, expected):
    assert gates.ratio_exceeds(value, max_ratio) is expected


def test_zero_max_ratio_never_rejects_and_never_computes(ratio):
    ratio["value"] = 99.0
    assert gates.pullback_dryup_rejects(object(), "bullish", 0.0) is False
    assert ratio["calls"] == []


def test_direction_reaches_the_instrument(ratio):
    ratio["value"] = 0.1
    gates.pullback_dryup_rejects(object(), "bearish", 0.6)
    assert ratio["calls"] == ["bearish"]


def test_real_instrument_bullish_and_bearish_mirror():
    frame = pullback_frame(0.9 * IMPULSE_VOLUME)
    assert structure.pullback_vol_ratio(frame, "bullish") == pytest.approx(0.9)
    assert structure.pullback_vol_ratio(mirror(frame), "bearish") == pytest.approx(0.9)
    for df, direction in ((frame, "bullish"), (mirror(frame), "bearish")):
        assert gates.pullback_dryup_rejects(df, direction, 0.75) is True
        assert gates.pullback_dryup_rejects(df, direction, 0.90) is False


def test_frozen_list_is_exact_and_names_real_entry_functions():
    assert gates.PULLBACK_DRYUP_STRATEGIES == frozenset(FROZEN)
    assert FROZEN <= set(entry_filters.ENTRY_FUNCS)


@pytest.mark.parametrize("strategy", ["MACD", "Volume Profile", "Support/Resistance",
                                      "Elliott Wave", "Fibonacci Continuation", None])
def test_strategies_outside_the_list_are_never_in_scope(strategy):
    assert gates.strategy_in_dryup_scope(strategy) is False


def test_ema_crossover_only_in_pullback_mode(monkeypatch):
    assert gates.strategy_in_dryup_scope("EMA Crossover") is True
    monkeypatch.setitem(entry_filters.DEFAULT_PARAMS["EMA Crossover"], "entry_mode", "cross")
    assert gates.strategy_in_dryup_scope("EMA Crossover") is False


def test_scopes_never_cross(scope):
    scope("strategy")
    assert gates.pullback_dryup_scoped("strategy", "Fibonacci") is True
    assert gates.pullback_dryup_scoped("confluence") is False
    scope("confluence")
    assert gates.pullback_dryup_scoped("confluence") is True
    assert gates.pullback_dryup_scoped("strategy", "Fibonacci") is False
    scope("off")
    assert not gates.pullback_dryup_scoped("confluence")
    assert not gates.pullback_dryup_scoped("strategy", "Fibonacci")


def test_scope_flip_takes_effect_on_the_next_call(scope, ratio):
    ratio["value"] = 5.0
    scope("off")
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is False
    scope("strategy")
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is True


def test_blocks_off_scope_never_computes(scope, ratio):
    ratio["value"] = 5.0
    scope("off", 0.6)
    assert gates.pullback_dryup_blocks(object(), "bullish", source="strategy", strategy="RSI") is False
    sentinel = object()
    assert gates.filter_pullback_dryup([sentinel], object()) == ([sentinel], [])
    scope("confluence", 0.0)
    assert gates.filter_pullback_dryup([sentinel], object()) == ([sentinel], [])
    assert ratio["calls"] == []


def test_filter_splits_kept_and_rejected_by_direction(scope, monkeypatch):
    monkeypatch.setattr(gates, "pullback_vol_ratio",
                        lambda df, direction: 0.95 if direction == "bullish" else None)
    scope("confluence", 0.75)
    bull, bear = SimpleNamespace(direction="bullish"), SimpleNamespace(direction="bearish")
    kept, rejected = gates.filter_pullback_dryup([bull, bear], object())
    assert kept == [bear] and rejected == [bull]
```

- [ ] **Step 3: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_pullback_dryup_gate.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.edge.gates' has no attribute 'pullback_vol_ratio'`.

- [ ] **Step 4: Implement in `gates.py`**

Extend the module docstring's first sentence to name the new gate. Add the imports below the existing `from swingbot import config`, then append:

```python
from swingbot.core.market import entry_filters
from swingbot.core.market.structure import pullback_vol_ratio

#: v122 frozen pullback list. Adding a name is a new pre-registration.
PULLBACK_DRYUP_STRATEGIES = frozenset({
    "Fibonacci", "EMA Crossover", "Break & Retest", "RSI", "RSI Divergence",
    "MA Ribbon", "VWAP",
})
PULLBACK_VOLUME_REASON = "pullback_volume"
_EMA_CROSSOVER = "EMA Crossover"


def ratio_exceeds(ratio: float | None, max_ratio: float) -> bool:
    """The comparison alone: known, and strictly above a positive `max_ratio`.
    None passes, and so does NaN (a comparison with NaN is False)."""
    return max_ratio > 0 and ratio is not None and ratio > max_ratio


def pullback_dryup_rejects(df: pd.DataFrame, direction: str, max_ratio: float) -> bool:
    """v122 predicate on a frame of COMPLETED daily bars: reject iff the
    pullback/impulse volume ratio exceeds `max_ratio`. `max_ratio <= 0` is off and
    never computes."""
    if max_ratio <= 0:
        return False
    return ratio_exceeds(pullback_vol_ratio(df, direction), max_ratio)


def _ema_crossover_pullback_mode() -> bool:
    return entry_filters.DEFAULT_PARAMS.get(_EMA_CROSSOVER, {}).get("entry_mode") == "pullback"


def strategy_in_dryup_scope(strategy: str | None) -> bool:
    """The frozen list. EMA Crossover counts only while its entry mode is pullback."""
    if strategy not in PULLBACK_DRYUP_STRATEGIES:
        return False
    return strategy != _EMA_CROSSOVER or _ema_crossover_pullback_mode()


def pullback_dryup_scoped(source: str, strategy: str | None = None) -> bool:
    """Whether this entry source (and strategy) is gated under today's config."""
    if getattr(config, "PULLBACK_DRYUP_SCOPE", "off") != source:
        return False
    return source == "confluence" or strategy_in_dryup_scope(strategy)


def _max_ratio() -> float:
    return float(getattr(config, "PULLBACK_DRYUP_MAX_RATIO", 0.0) or 0.0)


def pullback_dryup_blocks(df, direction: str, *, source: str, strategy: str | None = None) -> bool:
    """The one call every strategy call site makes (live and replay)."""
    if not pullback_dryup_scoped(source, strategy):
        return False
    return pullback_dryup_rejects(df, direction, _max_ratio())


def filter_pullback_dryup(scenarios, df) -> tuple[list, list]:
    """Split confluence scenarios into (kept, rejected). It is a no-op, and computes
    nothing, unless the confluence scope is active."""
    if not pullback_dryup_scoped("confluence"):
        return list(scenarios), []
    max_ratio = _max_ratio()
    kept, rejected = [], []
    for scenario in scenarios:
        bucket = rejected if pullback_dryup_rejects(df, scenario.direction, max_ratio) else kept
        bucket.append(scenario)
    return kept, rejected
```

Import order: `gates.py` already imports `numpy`/`pandas`/`config`. `entry_filters` and `structure` import nothing from `edge`, so this adds no import cycle (`edge/context.py` imports `gates`, and v121's `context.py` imports `structure`).

- [ ] **Step 5: Run the narrow tests, radon, and the no-lookahead review**

Run: `python scripts/dev/testrun.py file tests/edge/test_pullback_dryup_gate.py` then `python scripts/dev/testrun.py file tests/edge/test_edge_gates.py` then `python -m radon cc -s swingbot/core/edge/gates.py`
Expected: PASS, PASS, every function A or B. Invoke `edge-module` and `no-lookahead` on `gates.py`. The predicate only forwards the caller's frame, so the slicing is the call site's responsibility (V122-4 and V122-5).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/edge/gates.py tests/edge/pullback_frames.py tests/edge/test_pullback_dryup_gate.py
git commit -m "feat(v122): pullback_dryup_rejects predicate and frozen scope rules"
```

### Task V122-3: Defaults-off witness, captured before any call site changes

**Files:**
- Create: `tests/backtesting/test_pullback_dryup_witness.py`
- Create: `tests/fixtures/v122/defaults_off_witness.json` (generated)

**Interfaces:**
- Consumes: `arms.engine.run_arm` and `tests.backtesting.test_v74_fixture.load_v74_fixture` (both verified).
- Produces: `witness_rows() -> list` and `WITNESS: Path`. V122-14 edits the knob assertion if a scope ships.

- [ ] **Step 1: Write the test**

```python
# tests/backtesting/test_pullback_dryup_witness.py
"""v122 defaults-off witness: with both knobs at default, replay trades are
byte-identical to the trades captured before the gate existed (spec: Testing)."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WITNESS = Path(__file__).resolve().parent.parent / "fixtures" / "v122" / "defaults_off_witness.json"
HORIZONS = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")


def witness_rows() -> list:
    rows = []
    for ticker, frame in sorted(load_v74_fixture().items()):
        for trade in run_arm(ticker, frame, ("confluence", "strategy"), HORIZONS, WINDOW, {}):
            r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
            rows.append([list(trade.key), trade.outcome, r_multiple, trade.planned_rr])
    return sorted(rows, key=repr)


@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness():
    assert config.PULLBACK_DRYUP_SCOPE == "off"
    assert config.PULLBACK_DRYUP_MAX_RATIO == 0.0
    current = json.loads(json.dumps(witness_rows()))
    assert current, "fixture must produce trades or the witness proves nothing"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Confirm it fails because the witness file is missing**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_witness.py`
Expected: FAIL with `FileNotFoundError` for `defaults_off_witness.json`.

- [ ] **Step 3: Capture the witness on pre-gate code**

First confirm that neither `strategy_engine.py` nor `backtest_scenarios.py` has been edited: `git diff --stat main -- swingbot/core/backtesting/` prints nothing. Then:

```bash
python -c "import json; from tests.backtesting.test_pullback_dryup_witness import WITNESS, witness_rows; WITNESS.parent.mkdir(parents=True, exist_ok=True); WITNESS.write_text(json.dumps(witness_rows(), indent=0), encoding='utf-8')"
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_witness.py`
Expected: PASS.

- [ ] **Step 5: Commit, before V122-4 and V122-5 start**

```bash
git add tests/backtesting/test_pullback_dryup_witness.py tests/fixtures/v122/defaults_off_witness.json
git commit -m "test(v122): defaults-off replay witness captured on pre-gate code"
```

# Phase 2 — Call sites, parity, reachability

### Task V122-4: Live call sites (strategy pass and confluence scan)

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py` (`PassResult`, a new `_dryup_blocked`, and `_emit_signal`)
- Modify: `swingbot/core/scanning/analyze.py` (a new `_apply_pullback_dryup`, the `stats["failed_counts"]` literal in `_scan_one`, and one assignment before `for scenario in scenarios:`)
- Modify: `swingbot/core/scanning/scan_run.py` (`failed_counts` literal, `progress.funnel` dict, `_maybe_run_strategy_pass` return)
- Create: `tests/scanning/test_pullback_dryup_live.py`

**Interfaces:**
- Consumes: `gates.pullback_dryup_blocks`, `gates.filter_pullback_dryup` and `gates.PULLBACK_VOLUME_REASON` (V122-2).
- Consumes, verified: `strategy_pass.completed_frame(df, now)`, which drops today's still-forming daily bar during the regular session and is the helper v119 and `run_strategy_pass` use. `run_strategy_pass` already hands `_emit_signal` a `completed_frame(raw, now)`, so the strategy call site needs no extra trim.
- Produces: `strategy_pass._dryup_blocked(frame, *, ticker, strategy, direction, horizon) -> bool`, `PassResult.pullback_volume: int`, `analyze._apply_pullback_dryup(scenarios, df, stats, ticker, horizon_key, now=None) -> list` (evaluates the gate on `completed_frame(df, now)`), funnel keys `failed_pullback_volume` and `strategy_pullback_volume`. V122-6 calls the two helpers directly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scanning/test_pullback_dryup_live.py
"""v122 live call sites: the strategy pass and the confluence scan ask the gate
before a plan is built, and count each rejection under `pullback_volume`."""
import inspect
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.scanning import analyze, dedup, engine, fetch, runstate, scan_run
from swingbot.core.scanning import strategy_pass as sp
from swingbot.core.scanning.engine import ScanProgress
from swingbot.core.tracking.performance import TradeLog
from tests.helpers import make_ohlcv
from tests.scanning.test_strategy_pass_emit import _Log, _plan, _Store
from tests.store_seed import seed_store


@pytest.fixture
def heavy(monkeypatch):
    calls = []
    monkeypatch.setattr(gates, "pullback_vol_ratio",
                        lambda df, direction: calls.append(len(df)) or 5.0)
    return calls


def _knobs(monkeypatch, scope, max_ratio=0.60):
    monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", scope)
    monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", max_ratio)


def _emit(monkeypatch, strategy, frame=object()):
    built = []
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: built.append(1) or _plan())
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    monkeypatch.setattr(sp, "build_strategy_alert_embed", lambda plan: "embed")
    deps = sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="shadow", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="AAPL", strategy=strategy, direction="bullish",
                    horizon="4w", bar_date="2026-09-25", regime=None, deps=deps)
    return result, built


def test_strategy_scope_rejects_before_the_plan_is_built(monkeypatch, heavy):
    _knobs(monkeypatch, "strategy")
    result, built = _emit(monkeypatch, "Fibonacci")
    assert result.pullback_volume == 1 and built == [] and result.plans == []


@pytest.mark.parametrize("scope,strategy", [("strategy", "MACD"), ("confluence", "Fibonacci"),
                                            ("off", "Fibonacci")])
def test_out_of_scope_strategy_signals_are_untouched(monkeypatch, heavy, scope, strategy):
    _knobs(monkeypatch, scope)
    result, built = _emit(monkeypatch, strategy)
    assert result.pullback_volume == 0 and built == [1]


def test_confluence_helper_drops_and_counts(monkeypatch, heavy):
    _knobs(monkeypatch, "confluence")
    stats = {"failed_counts": {"pullback_volume": 0}}
    kept = analyze._apply_pullback_dryup([SimpleNamespace(direction="bullish")], object(),
                                         stats, "AAPL", "4w")
    assert kept == [] and stats["failed_counts"]["pullback_volume"] == 1


def test_confluence_helper_drops_todays_forming_bar(monkeypatch):
    """Spec amendment: the predicate only ever sees completed daily bars."""
    from datetime import datetime, timezone
    seen = []
    monkeypatch.setattr(gates, "pullback_vol_ratio", lambda df, direction: seen.append(df) or 0.1)
    _knobs(monkeypatch, "confluence")
    df = make_ohlcv([100.0] * 70, start="2026-07-01")
    day = df.index[-1]
    during_rth = datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc)   # 11:00 ET
    after_close = datetime(day.year, day.month, day.day, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
    stats = {"failed_counts": {"pullback_volume": 0}}
    for now in (during_rth, after_close):
        analyze._apply_pullback_dryup([SimpleNamespace(direction="bullish")], df, stats, "T", "4w", now=now)
    assert [len(frame) for frame in seen] == [69, 70]
    assert seen[0].index[-1] < df.index[-1]


def test_both_funnel_literals_have_the_new_slot():
    src = inspect.getsource(analyze) + inspect.getsource(scan_run)
    assert src.count('"pullback_volume": 0') == 2
    assert '"failed_pullback_volume": failed_counts["pullback_volume"]' in inspect.getsource(scan_run)
    assert '"strategy_pullback_volume": result.pullback_volume' in inspect.getsource(scan_run)


def _structured_df():
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.fixture
def live_scan(monkeypatch, tmp_path, stub_batch_fetch):
    """Same harness as test_engine_v2_plans.test_sync_run_scan_gates_attach_plan_v2_on_all_ok."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct",
                           "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}]})
    df = _structured_df()
    for attr, value in (("PLAN_ENGINE_V2", "shadow"), ("MIN_REWARD_PCT", 0.5),
                        ("MIN_STOP_DISTANCE_PCT", 0.0), ("MAX_STOP_LOSS_PCT", 50.0),
                        ("MIN_RISK_REWARD_RATIO", 0.01), ("STRATEGY_ALERTS_MODE", "off")):
        monkeypatch.setattr(config, attr, value)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(scan_run, "trade_log", TradeLog())
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    captured = {}

    def capture(items):
        captured["items"] = list(items)
        return []
    monkeypatch.setattr(dedup, "dedup_scan_items", capture)
    return captured, len(df)


def test_live_confluence_scope_rejects_counts_and_reads_the_full_frame(live_scan, monkeypatch, heavy):
    captured, n_bars = live_scan
    off = ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=off, min_confluence=0)
    assert captured["items"], "fixture must produce at least one scenario"
    found = off.funnel["scenarios_found"]
    assert off.funnel["failed_pullback_volume"] == 0 and heavy == []
    _knobs(monkeypatch, "confluence")
    on = ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=on, min_confluence=0)
    assert captured["items"] == []
    assert on.funnel["failed_pullback_volume"] == found
    # The fixture's last bar is a past session, so completed_frame trims nothing here.
    # The forming-bar trim itself is pinned by test_confluence_helper_drops_todays_forming_bar.
    assert heavy and all(n == n_bars for n in heavy)
```

`make_ohlcv` dates bars on business days, so the forming-bar test's last bar is a weekday, and both `now` values derive from it. If the e2e frame-length assertion fails, the live scan trimmed or extended the frame before the gate. Stop and report what it did. Do not loosen the assertion.

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_pullback_dryup_live.py`
Expected: FAIL with `AttributeError: 'PassResult' object has no attribute 'pullback_volume'`, plus the missing `_apply_pullback_dryup`.

- [ ] **Step 3: Implement the strategy-pass call site**

In `strategy_pass.py` add `from swingbot.core.edge.gates import PULLBACK_VOLUME_REASON, pullback_dryup_blocks` beside the other `edge` import, add `pullback_volume: int = 0` as the last field of `PassResult`, and add above `_emit_signal`:

```python
def _dryup_blocked(frame, *, ticker, strategy, direction, horizon) -> bool:
    """v122: the pullback dry-up gate, after the signal is known and before the plan."""
    if not pullback_dryup_blocks(frame, direction, source="strategy", strategy=strategy):
        return False
    log.debug("gate: %s (%s) %s %s rejected -- %s", ticker, horizon, strategy, direction,
              PULLBACK_VOLUME_REASON)
    return True
```

In `_emit_signal`, directly after the `_rs_blocked` block and before `plan = build_strategy_plan_at(`:

```python
    if _dryup_blocked(frame, ticker=ticker, strategy=strategy, direction=direction, horizon=horizon):
        result.pullback_volume += 1
        return
```

- [ ] **Step 4: Implement the confluence call site and the funnel slots**

In `analyze.py`, add above `_scan_one`:

```python
def _apply_pullback_dryup(scenarios, df, stats, ticker, horizon_key, now=None) -> list:
    """v122: drop confluence scenarios the pullback dry-up gate rejects, counted in the
    funnel. The predicate sees COMPLETED daily bars only: today's still-forming bar is
    dropped first (strategy_pass.completed_frame, as v119 does), so live matches replay."""
    from swingbot.core.scanning.strategy_pass import completed_frame  # lazy: avoids an import cycle
    completed = completed_frame(df, now or datetime.now(timezone.utc))
    kept, rejected = gates_mod.filter_pullback_dryup(scenarios, completed)
    stats["failed_counts"]["pullback_volume"] += len(rejected)
    for scenario in rejected:
        log.debug("gate: %s (%s) %s rejected -- %s", ticker, horizon_key,
                  scenario.direction, gates_mod.PULLBACK_VOLUME_REASON)
    return kept
```

In `_scan_one`'s `stats` literal, change the `failed_counts` second line to:

```python
            "min_risk_reward": 0, "min_confluence": 0, "min_confidence": 0, "opex_close_window": 0,
            "pullback_volume": 0,
```

In `_scan_one`, insert one line directly above `        for scenario in scenarios:` (after the `if not scenarios:` no-entry-point block, so `no_entry_point` keeps its meaning):

```python
        scenarios = _apply_pullback_dryup(scenarios, df, stats, ticker, horizon_key)
```

In `scan_run.py`, change the merge-loop `failed_counts` literal in the same way (append `"pullback_volume": 0,`). In the `progress.funnel = {` dict, after `"failed_opex_close_window": ...`, add `"failed_pullback_volume": failed_counts["pullback_volume"],`. In `_maybe_run_strategy_pass`, change the final return to:

```python
    return {"strategy_plans": len(result.plans), "strategy_opened": result.opened,
            "strategy_pullback_volume": result.pullback_volume}
```

- [ ] **Step 5: Run the narrow tests, neighbours and radon**

Run: `python scripts/dev/testrun.py file tests/scanning/test_pullback_dryup_live.py`, then `... file tests/scanning/test_strategy_pass_emit.py`, `... file tests/scanning/test_opex_gates.py`, `... file tests/scanning/test_engine_v2_plans.py`, then `python -m radon cc -s swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/analyze.py | grep -E "_emit_signal|_dryup_blocked|_apply_pullback_dryup|_scan_one"`
Expected: all PASS. `_emit_signal` at B (11), the new helpers at A, and `_scan_one` unchanged at E (39). Invoke `no-lookahead` on the two call sites. Both evaluate the gate on `completed_frame` output: the strategy frame already is one, and the confluence helper trims its own frame. `analyze.py` already imports `datetime` and `timezone`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/analyze.py swingbot/core/scanning/scan_run.py tests/scanning/test_pullback_dryup_live.py
git commit -m "feat(v122): live pullback dry-up call sites; pullback_volume funnel counts"
```

### Task V122-5: Replay call sites (strategy arm engine and confluence replay)

**Files:**
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (a new `_gated_plan`; `iter_trades` calls it instead of `build_strategy_plan`)
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (a new `_dryup_kept`; one assignment in `replay_scenarios`)
- Create: `tests/backtesting/arms/test_pullback_dryup_replay.py`

**Interfaces:**
- Consumes: `gates.pullback_dryup_blocks` and `gates.filter_pullback_dryup` (V122-2).
- Produces: `StrategyEngine._gated_plan(window, index, *, ticker, strategy, horizon_key, direction, level_map, params)` (staticmethod; returns a `TradePlanV2` or `None`) and `backtest_scenarios._dryup_kept(scenarios, window) -> list`. V122-6 calls both directly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backtesting/arms/test_pullback_dryup_replay.py
"""v122 replay call sites: same decision point as live -- after the signal, before the plan."""
import pytest

from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.edge import gates
from swingbot.core.market import entry_filters
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
STRATEGY_ON = {"PULLBACK_DRYUP_SCOPE": "strategy", "PULLBACK_DRYUP_MAX_RATIO": 0.60}
CONFLUENCE_ON = {"PULLBACK_DRYUP_SCOPE": "confluence", "PULLBACK_DRYUP_MAX_RATIO": 0.60}


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


@pytest.fixture
def heavy(monkeypatch):
    monkeypatch.setattr(gates, "pullback_vol_ratio", lambda df, direction: 5.0)


@pytest.fixture
def must_not_compute(monkeypatch):
    def boom(df, direction):
        raise AssertionError("pullback_vol_ratio computed while the gate is off")
    monkeypatch.setattr(gates, "pullback_vol_ratio", boom)


def test_defaults_never_compute_the_ratio(frame, must_not_compute):
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW,
                   {"PULLBACK_DRYUP_SCOPE": "confluence"}) is not None   # ratio still 0 => off


def test_confluence_scope_removes_heavy_pullbacks(frame, heavy):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert base
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, CONFLUENCE_ON) == []


def test_strategy_scope_leaves_confluence_untouched(frame, heavy):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, STRATEGY_ON) == base


@pytest.mark.slow
def test_strategy_scope_gates_only_the_frozen_list(frame, heavy):
    base = run_arm("AAPL", frame, ("strategy",), ("4w", "3m"), WINDOW, {})
    gated = run_arm("AAPL", frame, ("strategy",), ("4w", "3m"), WINDOW, STRATEGY_ON)
    assert any(t.strategy in gates.PULLBACK_DRYUP_STRATEGIES for t in base)
    assert gated == [t for t in base if t.strategy not in gates.PULLBACK_DRYUP_STRATEGIES]


def test_gated_plan_respects_ema_entry_mode(monkeypatch, frame, heavy):
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *a, **k: "plan")
    monkeypatch.setattr("swingbot.config.PULLBACK_DRYUP_SCOPE", "strategy")
    monkeypatch.setattr("swingbot.config.PULLBACK_DRYUP_MAX_RATIO", 0.60)
    kwargs = dict(ticker="AAPL", strategy="EMA Crossover", horizon_key="4w",
                  direction="bullish", level_map=None, params=None)
    assert strategy_engine.StrategyEngine._gated_plan(frame, len(frame) - 1, **kwargs) is None
    monkeypatch.setitem(entry_filters.DEFAULT_PARAMS["EMA Crossover"], "entry_mode", "cross")
    assert strategy_engine.StrategyEngine._gated_plan(frame, len(frame) - 1, **kwargs) == "plan"
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_pullback_dryup_replay.py`
Expected: FAIL. `test_confluence_scope_removes_heavy_pullbacks` returns the base trades, and `_gated_plan` does not exist.

- [ ] **Step 3: Implement the strategy replay call site**

In `strategy_engine.py` add `from swingbot.core.edge.gates import pullback_dryup_blocks` and this method to `StrategyEngine`:

```python
    @staticmethod
    def _gated_plan(window, index, *, ticker, strategy, horizon_key, direction, level_map, params):
        """v122: the pullback dry-up gate at strategy_pass._emit_signal's point -- after the
        signal, before the plan. A rejection does not occupy the one-at-a-time slot, which
        matches live, where a rejected signal opens nothing."""
        if pullback_dryup_blocks(window, direction, source="strategy", strategy=strategy):
            return None
        return build_strategy_plan(
            window, index, ticker=ticker, strategy=strategy, horizon_key=horizon_key,
            direction=direction, level_map=level_map, scan_params=params,
        )
```

In `iter_trades`, replace the `plan = build_strategy_plan(...)` call with:

```python
            plan = self._gated_plan(
                window, index, ticker=ticker, strategy=strategy,
                horizon_key=horizon_key, direction=direction,
                level_map=level_map if wants_tp2 else None, params=params,
            )
```

- [ ] **Step 4: Implement the confluence replay call site**

In `backtest_scenarios.py` add `from swingbot.core.edge.gates import filter_pullback_dryup` and, above `replay_scenarios`:

```python
def _dryup_kept(scenarios, window) -> list:
    """v122: the confluence-scope pullback dry-up gate, at analyze._apply_pullback_dryup's point."""
    return filter_pullback_dryup(scenarios, window)[0]
```

In `replay_scenarios`, insert directly after the `scenarios = levels.build_scenarios(...)` statement and before `for sc in scenarios:`:

```python
        scenarios = _dryup_kept(scenarios, window)
```

- [ ] **Step 5: Run the narrow tests, the witness and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_pullback_dryup_replay.py`, then `... file tests/backtesting/arms/test_strategy_engine.py`, `... file tests/backtesting/arms/test_confluence_engine.py`, `... file tests/backtesting/test_pullback_dryup_witness.py`, then `python -m radon cc -s swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest_scenarios.py | grep -E "iter_trades|_gated_plan|replay_scenarios|_dryup_kept"`
Expected: all PASS, with the witness still byte-identical. `iter_trades` stays C (14), `replay_scenarios` stays C (15) (legacy, not worse), and the new helpers are A.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/arms/test_pullback_dryup_replay.py
git commit -m "feat(v122): replay pullback dry-up call sites in the strategy and confluence engines"
```

### Task V122-6: Live and replay parity on one fixture

**Files:**
- Create: `tests/backtesting/test_pullback_dryup_parity.py`

**Interfaces:**
- Consumes: `strategy_pass._emit_signal`, `strategy_pass.completed_frame` and `PassResult.pullback_volume`, `analyze._apply_pullback_dryup(..., now=)` (V122-4); `StrategyEngine._gated_plan` and `backtest_scenarios._dryup_kept` (V122-5); `tests.edge.pullback_frames` (V122-2). It uses the **real** `pullback_vol_ratio`, not a monkeypatch.
- Produces: nothing new.

- [ ] **Step 1: Write the test**

```python
# tests/backtesting/test_pullback_dryup_parity.py
"""v122 parity: one fixture fed through the live and the replay call site gives the
same accept/reject, for both sources, both directions, both sides of the boundary,
and a frame that carries today's forming bar (spec amendment: completed bars only)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.edge import gates
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp
from tests.edge.pullback_frames import IMPULSE_VOLUME, mirror, pullback_frame
from tests.scanning.test_strategy_pass_emit import _Log, _Store

# The fixture ratio is 0.9: above 0.75 it rejects, and equal to 0.90 it passes.
BOUNDARY = [(0.75, True), (0.90, False)]


def _frame(direction):
    frame = pullback_frame(0.9 * IMPULSE_VOLUME)
    return frame if direction == "bullish" else mirror(frame)


def _knobs(monkeypatch, scope, max_ratio):
    monkeypatch.setattr(config, "PULLBACK_DRYUP_SCOPE", scope)
    monkeypatch.setattr(config, "PULLBACK_DRYUP_MAX_RATIO", max_ratio)


def _live_strategy_rejects(monkeypatch, frame, direction, strategy):
    built = []
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: built.append(1) or None)
    deps = sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="shadow", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="T", strategy=strategy, direction=direction,
                    horizon="4w", bar_date=frame.index[-1].date().isoformat(), regime=None, deps=deps)
    assert (result.pullback_volume == 1) == (not built)
    return result.pullback_volume == 1


def _replay_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *a, **k: "plan")
    plan = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="T", strategy=strategy, horizon_key="4w",
        direction=direction, level_map=None, params=None)
    return plan is None


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("max_ratio,rejects", BOUNDARY)
@pytest.mark.parametrize("strategy", ["Fibonacci", "MACD"])
def test_strategy_live_and_replay_agree(monkeypatch, direction, max_ratio, rejects, strategy):
    _knobs(monkeypatch, "strategy", max_ratio)
    frame = _frame(direction)
    live = _live_strategy_rejects(monkeypatch, frame, direction, strategy)
    replay = _replay_strategy_rejects(monkeypatch, frame, direction, strategy)
    assert live == replay == (rejects and strategy == "Fibonacci")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("max_ratio,rejects", BOUNDARY)
def test_confluence_live_and_replay_agree(monkeypatch, direction, max_ratio, rejects):
    _knobs(monkeypatch, "confluence", max_ratio)
    frame, scenario = _frame(direction), SimpleNamespace(direction=direction)
    stats = {"failed_counts": {"pullback_volume": 0}}
    live = analyze._apply_pullback_dryup([scenario], frame, stats, "T", "4w") == []
    replay = backtest_scenarios._dryup_kept([scenario], frame) == []
    assert live == replay == rejects
    assert stats["failed_counts"]["pullback_volume"] == int(rejects)


def _with_forming_bar(frame, direction):
    """Append today's unfinished bar: 10x impulse volume, still inside the pullback.
    If it reached the predicate, the 0.90 cell would flip from pass to reject."""
    nxt = frame.index[-1] + pd.offsets.BDay(1)
    last = float(frame["Close"].iloc[-1])
    close = last - 1.0 if direction == "bullish" else last + 1.0
    bar = pd.DataFrame({"Open": [last], "High": [max(last, close) + 0.5],
                        "Low": [min(last, close) - 0.5], "Close": [close],
                        "Volume": [10 * IMPULSE_VOLUME]}, index=[nxt])
    return pd.concat([frame, bar]), datetime(nxt.year, nxt.month, nxt.day, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_forming_bar_never_reaches_the_predicate(monkeypatch, direction):
    """Live drops the forming bar and matches replay on the completed frame. The
    raw frame would have rejected, so this test bites."""
    completed = _frame(direction)
    raw, now = _with_forming_bar(completed, direction)
    assert gates.pullback_dryup_rejects(raw, direction, 0.90) is True        # the trap is real
    _knobs(monkeypatch, "strategy", 0.90)
    live = _live_strategy_rejects(monkeypatch, sp.completed_frame(raw, now), direction, "Fibonacci")
    replay = _replay_strategy_rejects(monkeypatch, completed, direction, "Fibonacci")
    assert live is False and replay is False
    _knobs(monkeypatch, "confluence", 0.90)
    stats = {"failed_counts": {"pullback_volume": 0}}
    scenario = SimpleNamespace(direction=direction)
    assert analyze._apply_pullback_dryup([scenario], raw, stats, "T", "4w", now=now) == [scenario]
    assert backtest_scenarios._dryup_kept([scenario], completed) == [scenario]
```

`_live_strategy_rejects` is handed `sp.completed_frame(raw, now)`. That is the same composition `run_strategy_pass` uses: `frame = completed_frame(raw, now)`, then `_emit_signal`. 16:00 UTC is 12:00 ET, inside the regular session.

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_parity.py`
Expected: PASS (14 cases: 8 strategy, 4 confluence, 2 forming-bar). A failure here is a real parity bug in V122-4 or V122-5, or a v121 ratio that disagrees with the spec's leg definition on the hand-built frame. Fix the call site. Never fix the test, and never change v121 from this plan.

- [ ] **Step 3: Commit**

```bash
git add tests/backtesting/test_pullback_dryup_parity.py
git commit -m "test(v122): live/replay pullback dry-up parity on one fixture"
```

### Task V122-7: Searchable classification and the reachability registry

**Files:**
- Modify: `swingbot/config.py` (`_SEARCH_CLASSES["searchable"]`)
- Modify: `swingbot/core/backtesting/arms/reachability.py`
- Modify: `tests/backtesting/arms/test_reachability.py`

**Interfaces:**
- Consumes: the replay call sites (V122-5).
- Produces: `reachability.classify("PULLBACK_DRYUP_SCOPE") == REACHABLE` and the same for `PULLBACK_DRYUP_MAX_RATIO`, with `observed_by=CS` and `fixture_observable=False` (a lone perturbation at default is inert, the same pattern as `_TIGHTEN`). `config.searchable_attrs()` includes both. `measure_arms.py --knob` then accepts them.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtesting/arms/test_reachability.py`, adding `import pytest` at its top)

```python
DRYUP = ("PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO")


def test_dryup_knobs_are_searchable_and_reachable_by_both_engines():
    for attr in DRYUP:
        assert attr in config.searchable_attrs()
        assert r.classify(attr) == r.REACHABLE
        assert r.REGISTRY[attr].observed_by == r.CS
        assert r.REGISTRY[attr].fixture_observable is False
        assert "Stage -1" in r.reason(attr)


@pytest.mark.slow
def test_dryup_knobs_change_outcomes_together_on_the_fixture(monkeypatch):
    """Fixture-level stand-in for the Stage -1 pilot: both scopes reach trades."""
    from swingbot.core.backtesting.arms.engine import run_arm
    from swingbot.core.edge import gates
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    monkeypatch.setattr(gates, "pullback_vol_ratio", lambda df, direction: 5.0)
    frame, window = load_v74_fixture()["AAPL"], ("1900-01-01", "2100-12-31")
    for scope, engines in (("confluence", ("confluence",)), ("strategy", ("strategy",))):
        base = run_arm("AAPL", frame, engines, ("4w", "3m"), window, {})
        gated = run_arm("AAPL", frame, engines, ("4w", "3m"), window,
                        {"PULLBACK_DRYUP_SCOPE": scope, "PULLBACK_DRYUP_MAX_RATIO": 0.60})
        assert gated != base, scope
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`
Expected: FAIL. The knobs are not searchable, so the registry has no entry for them.

- [ ] **Step 3: Implement**

In `config.py`, add `"PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO",` to the `"searchable"` set after `"FIB_TARGET_1_0_EXTENSION",`. In `reachability.py`, add beside `_TIGHTEN`:

```python
_DRYUP = ("v122 pullback dry-up gate (edge/gates.py), applied before plan construction in "
          "StrategyEngine._gated_plan and backtest_scenarios._dryup_kept. Inert unless "
          "PULLBACK_DRYUP_SCOPE != off and PULLBACK_DRYUP_MAX_RATIO > 0 together, so a lone "
          "perturbation at the default is inert by design. Stage -1: measure_arms.py --stage "
          "pilot --knob PULLBACK_DRYUP_SCOPE=<scope> --knob PULLBACK_DRYUP_MAX_RATIO=0.60, "
          "then validate_component.py --stage reachability.")
```

and in `REGISTRY`, after `"TIGHTEN_ATR_MULT"`:

```python
    "PULLBACK_DRYUP_SCOPE": Reach(REACHABLE, _DRYUP, CS),
    "PULLBACK_DRYUP_MAX_RATIO": Reach(REACHABLE, _DRYUP, CS),
```

- [ ] **Step 4: Run the narrow tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py` then `... file tests/backtesting/test_knob_observability.py` then `... file tests/test_config_pullback_dryup.py`
Expected: all PASS. The observability test skips both knobs because `fixture_observable=False`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py swingbot/core/backtesting/arms/reachability.py tests/backtesting/arms/test_reachability.py
git commit -m "feat(v122): classify the dry-up knobs searchable and reachable; Stage -1 command in the registry"
```
