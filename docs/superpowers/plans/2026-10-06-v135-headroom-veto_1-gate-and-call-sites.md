# v135 Headroom veto -- part 1: gate and call sites

> Part of `2026-10-06-v135-headroom-veto_0-index.md` (header, where to work, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global Constraints with every task. Steps use `- [ ]` for tracking. All paths are relative to the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v135-headroom-veto`.

**Spec:** `docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md`

# Phase 1 — Knobs, predicate, witness

### Task V135-1: Worktree and the two knobs

**Files:**
- Modify: `swingbot/config.py` (two `Field`s directly after the `PULLBACK_DRYUP_MAX_RATIO` Field, and one `_MODE_VALUES` entry)
- Modify: `.env.example` (after the `PULLBACK_DRYUP_MAX_RATIO=0` line)
- Create: `tests/test_config_headroom.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.HEADROOM_SCOPE: str` (`"off"`, `"strategy"` or `"confluence"`) and `config.HEADROOM_MIN_R: float`. At this task both keep the default `search_class="excluded"`. V135-7 makes them `searchable` together with their `ScanParams` fields and registry entries, so `tests/backtesting/arms/test_reachability.py` and `tests/infra/test_scan_params_coverage.py` stay green between tasks.

- [ ] **Step 0: Create the worktree**

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-06-v135-headroom-veto -b 2026-10-06-v135-headroom-veto main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v135-headroom-veto log --oneline -1
```

Expected: the worktree's HEAD is `main`'s HEAD. Every later command in this plan runs inside that worktree.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_headroom.py
"""v135 knobs: a three-way scope and a minimum-room multiple, both off by default."""

from swingbot import config


GRID = (0.5, 0.75, 1.0)


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


def test_scope_is_a_three_way_select_defaulting_off():
    field = _field("HEADROOM_SCOPE")
    assert field.type == "select" and field.default == "off" and field.hot_reloadable
    assert [value for value, _ in field.options] == ["off", "strategy", "confluence"]
    assert config.HEADROOM_SCOPE == "off"


def test_a_malformed_scope_falls_back_to_off():
    field = _field("HEADROOM_SCOPE")
    assert config._cast(field, "Strategy") == "strategy"
    assert config._cast(field, "CONFLUENCE") == "confluence"
    for bad in ("both", "", "strategy,confluence"):
        assert config._cast(field, bad) == "off"


def test_min_r_defaults_to_zero_meaning_off():
    field = _field("HEADROOM_MIN_R")
    assert field.type == "float" and config._cast(field, field.default) == 0.0
    assert config.HEADROOM_MIN_R == 0.0


def test_the_frozen_grid_fits_inside_the_field_bounds():
    field = _field("HEADROOM_MIN_R")
    assert all(field.min <= value <= field.max for value in GRID)


def test_the_field_cannot_exceed_one_r():
    """Above 1.0 the plan's own TP1 (floor MIN_RISK_REWARD_RATIO = 1.5) could become its blocker."""
    assert _field("HEADROOM_MIN_R").max == 1
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python scripts/dev/testrun.py file tests/test_config_headroom.py`
Expected: FAIL with `StopIteration`, because neither field exists yet.

- [ ] **Step 3: Implement**

In `swingbot/config.py`, insert into `FIELDS` directly after the `PULLBACK_DRYUP_MAX_RATIO` Field (and before `FIB_SR_CONFLUENCE_ATR`):

```python
    Field("HEADROOM_SCOPE", "HEADROOM_SCOPE", "Trade Filters & Risk",
          "Headroom veto: scope (v135)",
          type="select", default="off",
          options=[("off", "Off"),
                   ("strategy", "Strategy entries -- EMA Crossover, VWAP, Fibonacci, "
                                "Support/Resistance, RSI, Elliott Wave, MA Ribbon, "
                                "Break & Retest, RSI Divergence"),
                   ("confluence", "Confluence entries (both directions)")],
          help="v135. Skips a plan when an opposing level confirmed by at least two "
               "detector families sits beyond entry and nearer than HEADROOM_MIN_R x the "
               "plan's own risk. Targets and stops are never moved. Ships OFF: each scope "
               "is its own pre-registered measurement and flips on only if its one "
               "VALIDATION shot passes."),
    Field("HEADROOM_MIN_R", "HEADROOM_MIN_R", "Trade Filters & Risk",
          "Headroom veto: minimum clear room to the nearest confirmed opposing level (x risk)",
          type="float", default="0", min=0, max=1, step=0.25,
          help="The veto rejects when a confirmed opposing level is strictly nearer than "
               "this multiple of the plan's risk. 0 turns the veto off whatever the scope. "
               "v135's frozen grid is 0.5 / 0.75 / 1.0; the field stops at 1.0 so a plan's "
               "own first target can never be its blocker."),
```

In the `_MODE_VALUES` dict, add after the `"PULLBACK_DRYUP_SCOPE"` entry:

```python
    "HEADROOM_SCOPE": ("off", "strategy", "confluence"),
```

`_cast` already lower-cases every `_MODE_VALUES` attr and falls back to `"off"` with a warning, so it needs no new branch.

In `.env.example`, after the `PULLBACK_DRYUP_MAX_RATIO=0` line:

```
# v135 headroom veto. Skips a plan when an opposing level confirmed by at least
# two detector families sits beyond entry and nearer than HEADROOM_MIN_R x the
# plan's risk. Scope: off | strategy | confluence. 0 disables it whatever the
# scope. Ships OFF: each scope is its own pre-registered measurement.
HEADROOM_SCOPE=off
HEADROOM_MIN_R=0
```

- [ ] **Step 4: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/test_config_headroom.py`, then `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`, then `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`, then `python -m radon cc -s swingbot/config.py | grep _cast`
Expected: all PASS, and `_cast` unchanged at B (6).

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_headroom.py
git commit -m "feat(v135): HEADROOM_SCOPE / HEADROOM_MIN_R knobs, default off"
```

### Task V135-2: The predicate and its scope rules

**Files:**
- Modify: `swingbot/core/edge/gates.py`
- Create: `tests/edge/test_headroom_gate.py`

**Interfaces:**
- Consumes: `config.HEADROOM_SCOPE`, `config.HEADROOM_MIN_R` (V135-1); `levels.strategy_family(label) -> str`; `strategy_types.SHORT_STRATEGIES`.
- Produces (all in `swingbot.core.edge.gates`):
  - `HEADROOM_MIN_FAMILIES = 2`, `HEADROOM_STRATEGIES: frozenset[str]` (nine names), `HEADROOM_REASON = "headroom"`, `HEADROOM_SCOPES = ("strategy", "confluence")`
  - `nearest_blocker(entry, stop, direction, levels) -> tuple[float, float] | None`: `(distance, risk)` to the nearest confirmed level strictly beyond `entry` on the target side, or `None`
  - `blocker_inside(reading, min_r) -> bool`: the comparison alone, shared with the V135-10 baseline flags
  - `headroom_rejects(entry, stop, direction, levels, min_r) -> bool`: the spec's predicate
  - `strategy_in_headroom_scope(strategy) -> bool`
  - `headroom_active(source, strategy=None) -> bool`: scope matches **and** `HEADROOM_MIN_R > 0` (and, for `strategy`, the frozen list)
  - `planned_entry(plan) -> float`: `entry_price` when set, else `trigger_price`
  - `level_map_levels(level_map) -> list`: flattens a `(supports, resistances)` pair; `None` gives `[]`
  - `headroom_blocks_plan(plan, level_map, *, strategy) -> bool`: the one call both strategy call sites make
  - `filter_headroom(scenarios, supports, resistances) -> tuple[list, list]`: `(kept, rejected)`, the one call both confluence call sites make

- [ ] **Step 1: Invoke `no-lookahead` and `edge-module`, then write the failing tests**

```python
# tests/edge/test_headroom_gate.py
"""v135 predicate and scope rules (spec: The predicate, Scope, Testing)."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import SHORT_STRATEGIES

TWO = ("EMA50", "Rolling S/R")        # two families
ONE = ("Bollinger Bands",)            # one family
SAME = ("EMA20", "EMA50")             # two labels, one family (EMA)
ENTRY, LONG_STOP, SHORT_STOP = 100.0, 98.0, 102.0   # risk 2.0; at h=0.75 the bound is 1.5 away


def lv(price, *sources):
    return Level(price=price, sources=list(sources))


@pytest.fixture
def scope(monkeypatch):
    def set_scope(value, min_r=0.75):
        monkeypatch.setattr(config, "HEADROOM_SCOPE", value)
        monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    return set_scope


@pytest.fixture
def must_not_compute(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("an inactive headroom veto must not read any level")
    monkeypatch.setattr(gates, "nearest_blocker", boom)


@pytest.mark.parametrize("levels,expected", [
    (None, False),
    ([], False),
    ([lv(101.0, *ONE)], False),                      # single family inside the bound
    ([lv(101.0, *TWO)], True),                       # two families inside
    ([lv(101.5, *TWO)], False),                      # exactly at min_r x risk
    ([lv(101.4999, *TWO)], True),
    ([lv(99.0, *TWO)], False),                       # behind entry
    ([lv(100.0, *TWO)], False),                      # at entry: not strictly beyond
    ([lv(101.0, *SAME)], False),                     # EMA20 + EMA50 count as one family
    ([lv(103.0, *TWO), lv(101.0, *ONE)], False),     # the near one is unconfirmed, the confirmed one is far
    ([lv(103.0, *TWO), lv(101.2, *TWO)], True),
])
def test_bullish_predicate(levels, expected):
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", levels, 0.75) is expected


@pytest.mark.parametrize("levels,expected", [
    ([lv(99.0, *TWO)], True),
    ([lv(98.5, *TWO)], False),                       # exactly at the bound
    ([lv(101.0, *TWO)], False),                      # behind a short entry
    ([lv(99.0, *ONE)], False),
])
def test_bearish_mirror(levels, expected):
    assert gates.headroom_rejects(ENTRY, SHORT_STOP, "bearish", levels, 0.75) is expected


def test_zero_min_r_and_zero_risk_never_reject():
    near = [lv(100.01, *TWO)]
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", near, 0.0) is False
    assert gates.headroom_rejects(ENTRY, ENTRY, "bullish", near, 1.0) is False


def test_zero_min_r_never_computes(must_not_compute):
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", [lv(100.5, *TWO)], 0.0) is False


def test_non_finite_prices_pass():
    nan = float("nan")
    assert gates.headroom_rejects(nan, LONG_STOP, "bullish", [lv(101.0, *TWO)], 1.0) is False
    assert gates.headroom_rejects(ENTRY, nan, "bullish", [lv(101.0, *TWO)], 1.0) is False
    assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", [lv(nan, *TWO)], 1.0) is False


def test_nearest_blocker_reports_the_nearest_confirmed_level_and_the_risk():
    levels = [lv(104.0, *TWO), lv(100.5, *ONE), lv(101.0, *TWO), lv(97.0, *TWO)]
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", levels) == (1.0, 2.0)
    assert gates.nearest_blocker(ENTRY, SHORT_STOP, "bearish", levels) == (3.0, 2.0)
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", [lv(100.5, *ONE)]) is None
    assert gates.nearest_blocker(ENTRY, ENTRY, "bullish", levels) is None
    assert gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", None) is None


@pytest.mark.parametrize("reading,min_r,expected", [
    ((1.0, 2.0), 0.5, False),            # exactly at the bound
    ((1.0, 2.0), 0.75, True),
    ((1.0, 2.0), 0.0, False),            # off
    (None, 1.0, False),                  # no confirmed level ahead
])
def test_blocker_inside_is_the_shared_comparison(reading, min_r, expected):
    assert gates.blocker_inside(reading, min_r) is expected


def test_the_predicate_is_the_two_shared_steps_composed():
    levels = [lv(101.0, *TWO), lv(103.0, *TWO)]
    for min_r in (0.5, 0.75, 1.0):
        reading = gates.nearest_blocker(ENTRY, LONG_STOP, "bullish", levels)
        assert gates.headroom_rejects(ENTRY, LONG_STOP, "bullish", levels, min_r) \
            is gates.blocker_inside(reading, min_r)


def test_frozen_constants():
    assert gates.HEADROOM_MIN_FAMILIES == 2
    assert gates.HEADROOM_STRATEGIES == frozenset(backtest.ALL_STRATEGIES) - {"MACD", "Volume Profile"}
    assert len(gates.HEADROOM_STRATEGIES) == 9
    assert not gates.HEADROOM_STRATEGIES & set(SHORT_STRATEGIES)
    assert gates.HEADROOM_REASON == "headroom"


@pytest.mark.parametrize("strategy", ["MACD", "Volume Profile", None, *SHORT_STRATEGIES])
def test_strategies_outside_the_list_are_never_in_scope(strategy):
    assert gates.strategy_in_headroom_scope(strategy) is False


def test_scopes_never_cross(scope):
    scope("strategy")
    assert gates.headroom_active("strategy", "Fibonacci") is True
    assert gates.headroom_active("strategy", "MACD") is False
    assert gates.headroom_active("confluence") is False
    scope("confluence")
    assert gates.headroom_active("confluence") is True
    assert gates.headroom_active("strategy", "Fibonacci") is False
    scope("off")
    assert not gates.headroom_active("confluence")
    assert not gates.headroom_active("strategy", "Fibonacci")


def test_a_scope_with_zero_min_r_is_inactive(scope):
    scope("strategy", 0.0)
    assert gates.headroom_active("strategy", "Fibonacci") is False
    scope("confluence", 0.0)
    assert gates.headroom_active("confluence") is False


def _plan(entry_price=None):
    return SimpleNamespace(trigger_price=ENTRY, entry_price=entry_price, stop_loss=LONG_STOP,
                           direction="bullish")


def test_plan_gate_flips_with_the_scope_on_the_next_call(scope):
    level_map = ([], [lv(101.0, *TWO)])
    scope("off")
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="RSI") is False
    scope("strategy")
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="RSI") is True
    assert gates.headroom_blocks_plan(_plan(), level_map, strategy="MACD") is False
    assert gates.headroom_blocks_plan(_plan(), None, strategy="RSI") is False
    assert gates.headroom_blocks_plan(None, level_map, strategy="RSI") is False


def test_plan_gate_reads_the_filled_price_only_when_the_plan_has_one(scope):
    scope("strategy")
    level_map = ([], [lv(101.0, *TWO)])
    assert gates.planned_entry(_plan()) == ENTRY
    assert gates.planned_entry(_plan(entry_price=101.0)) == 101.0
    assert gates.planned_entry(SimpleNamespace(trigger_price=ENTRY)) == ENTRY
    assert gates.headroom_blocks_plan(_plan(entry_price=101.0), level_map, strategy="RSI") is False


def test_an_inactive_plan_gate_never_touches_the_plan(scope, must_not_compute):
    scope("off")
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="RSI") is False
    scope("strategy", 0.0)
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="RSI") is False
    scope("strategy")
    assert gates.headroom_blocks_plan(object(), ([], [lv(101.0, *TWO)]), strategy="MACD") is False


def _scenario(direction, stop):
    return SimpleNamespace(direction=direction, entry=ENTRY, stop_loss=stop)


def test_filter_splits_kept_and_rejected_by_direction(scope):
    scope("confluence")
    bull, bear = _scenario("bullish", LONG_STOP), _scenario("bearish", SHORT_STOP)
    kept, rejected = gates.filter_headroom([bull, bear], [lv(95.0, *TWO)], [lv(101.0, *TWO)])
    assert kept == [bear] and rejected == [bull]


def test_an_inactive_filter_returns_everything_and_never_computes(scope, must_not_compute):
    sentinel = object()
    for value, min_r in (("off", 0.75), ("strategy", 0.75), ("confluence", 0.0)):
        scope(value, min_r)
        assert gates.filter_headroom([sentinel], [], [lv(101.0, *TWO)]) == ([sentinel], [])


def test_level_map_levels_flattens_or_empties():
    below, above = lv(95.0, *TWO), lv(101.0, *TWO)
    assert gates.level_map_levels(([below], [above])) == [below, above]
    assert gates.level_map_levels(None) == []
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_headroom_gate.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.edge.gates' has no attribute 'nearest_blocker'` (or `headroom_rejects`).

- [ ] **Step 3: Implement in `gates.py`**

Extend the module docstring's first sentence to name the new gate ("... pullback volume dry-up (v122), headroom veto (v135), and earnings blackout (E18)"). Add two imports below the existing `from swingbot.core.market.structure import pullback_vol_ratio`:

```python
from swingbot.core.market.levels import strategy_family
from swingbot.core.market.strategy_types import SHORT_STRATEGIES
```

Append at the end of the module:

```python
#: v135 frozen constant -- not a knob, not a grid axis. Two is the smallest family count
#: that excludes a lone Bollinger band or floor pivot. Changing it is a new pre-registration.
HEADROOM_MIN_FAMILIES = 2
#: v135 frozen list: backtest.ALL_STRATEGIES minus the two VALIDATED badges. Adding a name
#: is a new pre-registration, and no strategy_types.SHORT_STRATEGIES name may ever join it.
HEADROOM_STRATEGIES = frozenset({
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence",
})
HEADROOM_REASON = "headroom"
HEADROOM_SCOPES = ("strategy", "confluence")


def _confirmed(level) -> bool:
    """A level at least HEADROOM_MIN_FAMILIES independent detector families agree on."""
    return len({strategy_family(source) for source in level.sources}) >= HEADROOM_MIN_FAMILIES


def nearest_blocker(entry: float, stop: float, direction: str, levels) -> tuple[float, float] | None:
    """(distance, risk) to the nearest confirmed level strictly beyond `entry` on the target
    side (above for bullish, below for bearish). None when risk is not positive, there are
    no levels, or no confirmed level lies ahead. A NaN price never qualifies."""
    risk = abs(entry - stop)
    if risk <= 0 or not levels:
        return None
    sign = 1.0 if direction == "bullish" else -1.0
    ahead = [sign * (level.price - entry) for level in levels if _confirmed(level)]
    ahead = [distance for distance in ahead if distance > 0]
    return (min(ahead), risk) if ahead else None


def blocker_inside(reading, min_r: float) -> bool:
    """The comparison alone, shared by the gate and the clause-6 baseline flags: a confirmed
    level exists and sits strictly nearer than `min_r` x risk. A level exactly at the bound
    does not block."""
    if min_r <= 0 or reading is None:
        return False
    distance, risk = reading
    return bool(distance < min_r * risk)


def headroom_rejects(entry: float, stop: float, direction: str, levels, min_r: float) -> bool:
    """v135 predicate: reject iff a confirmed opposing level sits strictly beyond `entry` and
    strictly nearer than `min_r` x |entry - stop|. `min_r <= 0` is off and never computes.

    Pure: it reads only the prices and levels the caller hands it. The caller owns handing
    it levels built from bars at or before the decision bar."""
    if min_r <= 0:
        return False
    return blocker_inside(nearest_blocker(entry, stop, direction, levels), min_r)


def strategy_in_headroom_scope(strategy: str | None) -> bool:
    """The frozen list. A SHORT_STRATEGIES name is never gated, whatever the list says."""
    return strategy in HEADROOM_STRATEGIES and strategy not in SHORT_STRATEGIES


def _headroom_min_r() -> float:
    return float(getattr(config, "HEADROOM_MIN_R", 0.0) or 0.0)


def headroom_active(source: str, strategy: str | None = None) -> bool:
    """Whether the veto gates this entry source (and strategy) under today's config. It is
    inert unless the scope matches AND HEADROOM_MIN_R > 0, so an inactive call site builds
    no level map."""
    if getattr(config, "HEADROOM_SCOPE", "off") != source or _headroom_min_r() <= 0:
        return False
    return source == "confluence" or strategy_in_headroom_scope(strategy)


def planned_entry(plan) -> float:
    """The plan's planned entry: its filled price when it has one, else its trigger."""
    entry = getattr(plan, "entry_price", None)
    return plan.trigger_price if entry is None else entry


def level_map_levels(level_map) -> list:
    """Flatten a build_level_map (supports, resistances) pair; None means no map."""
    if not level_map:
        return []
    supports, resistances = level_map
    return [*supports, *resistances]


def headroom_blocks_plan(plan, level_map, *, strategy: str | None) -> bool:
    """The one call every strategy call site makes (live and replay), after the plan is
    built. An inactive gate returns before touching the plan or the map."""
    if plan is None or not headroom_active("strategy", strategy):
        return False
    return headroom_rejects(planned_entry(plan), plan.stop_loss, plan.direction,
                            level_map_levels(level_map), _headroom_min_r())


def filter_headroom(scenarios, supports, resistances) -> tuple[list, list]:
    """Split confluence scenarios into (kept, rejected) against the very lists they were
    built from. A no-op that computes nothing unless the confluence scope is active."""
    if not headroom_active("confluence"):
        return list(scenarios), []
    min_r, levels = _headroom_min_r(), [*supports, *resistances]
    kept, rejected = [], []
    for scenario in scenarios:
        blocked = headroom_rejects(scenario.entry, scenario.stop_loss, scenario.direction,
                                   levels, min_r)
        (rejected if blocked else kept).append(scenario)
    return kept, rejected
```

Import check: `market/levels.py` imports only `market/*` modules and `market/strategy_types.py` imports nothing from the package, so neither import can form a cycle with `edge/`.

- [ ] **Step 4: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/edge/test_headroom_gate.py`, then `python scripts/dev/testrun.py file tests/edge/test_pullback_dryup_gate.py`, then `python scripts/dev/testrun.py file tests/edge/test_edge_gates.py`, then `python -m radon cc -s swingbot/core/edge/gates.py`
Expected: all PASS; every function A or B. The predicate forwards only what it is handed, so slicing is the call sites' duty (V135-4, V135-5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/gates.py tests/edge/test_headroom_gate.py
git commit -m "feat(v135): headroom_rejects predicate, frozen family count and strategy list"
```

### Task V135-3: Defaults-off witness, captured before any call site changes

**Files:**
- Create: `tests/backtesting/test_headroom_witness.py`
- Create: `tests/fixtures/v135/defaults_off_witness.json` (generated)

**Interfaces:**
- Consumes: `arms.engine.run_arm`, `strategy_engine.build_level_map` (the module-level name the engine calls), `tests.backtesting.test_v74_fixture.load_v74_fixture`; `config.HEADROOM_SCOPE` / `HEADROOM_MIN_R` (V135-1).
- Produces: `witness(delta=None) -> dict` with keys `rows` (sorted replay rows) and `strategy_level_map_builds` (how many maps the strategy engine itself built), and `WITNESS: Path`. V135-5 and V135-8 re-run this test; V135-15 edits its knob assertion if a scope ships.

- [ ] **Step 1: Write the test**

```python
# tests/backtesting/test_headroom_witness.py
"""v135 defaults-off witness: with both knobs at default, replay trades are byte-identical
to the trades captured before the veto existed, and the strategy engine builds exactly the
level maps it built before (spec: Testing -- Defaults-off witness)."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WITNESS = Path(__file__).resolve().parent.parent / "fixtures" / "v135" / "defaults_off_witness.json"
HORIZONS = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")


def witness(delta=None) -> dict:
    """Replay rows plus the number of level maps the strategy engine built on its own."""
    builds = []
    original = strategy_engine.build_level_map

    def counting(*args, **kwargs):
        builds.append(1)
        return original(*args, **kwargs)

    strategy_engine.build_level_map = counting
    try:
        rows = []
        for ticker, frame in sorted(load_v74_fixture().items()):
            for trade in run_arm(ticker, frame, ("confluence", "strategy"), HORIZONS, WINDOW,
                                 delta or {}):
                r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
                rows.append([list(trade.key), trade.outcome, r_multiple, trade.planned_rr])
    finally:
        strategy_engine.build_level_map = original
    return {"rows": sorted(rows, key=repr), "strategy_level_map_builds": len(builds)}


@pytest.mark.slow
def test_defaults_off_replay_matches_the_pre_gate_witness():
    assert config.HEADROOM_SCOPE == "off"
    assert config.HEADROOM_MIN_R == 0.0
    current = json.loads(json.dumps(witness()))
    assert current["rows"], "fixture must produce trades or the witness proves nothing"
    assert current["strategy_level_map_builds"] > 0, "fixture must exercise the TP2 map build"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Confirm it fails because the witness file is missing**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_headroom_witness.py`
Expected: FAIL with `FileNotFoundError` for `defaults_off_witness.json`.

- [ ] **Step 3: Capture the witness on pre-gate code**

First confirm that no call site has been edited: `git diff --stat main -- swingbot/core/backtesting/ swingbot/core/scanning/` prints nothing. Then:

```bash
python -c "import json; from tests.backtesting.test_headroom_witness import WITNESS, witness; WITNESS.parent.mkdir(parents=True, exist_ok=True); WITNESS.write_text(json.dumps(witness(), indent=0), encoding='utf-8')"
```

Run the command twice and confirm `git diff --stat` shows no change after the second run. If the file differs between two captures, stop and report BLOCKED: the fixture replay is not deterministic and cannot serve as a witness.

- [ ] **Step 4: Run it to confirm it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_headroom_witness.py`
Expected: PASS.

- [ ] **Step 5: Commit, before V135-4 and V135-5 start**

```bash
git add tests/backtesting/test_headroom_witness.py tests/fixtures/v135/defaults_off_witness.json
git commit -m "test(v135): defaults-off replay witness captured on pre-gate code"
```

# Phase 2 — Call sites, parity, reachability

### Task V135-4: Live call sites (strategy pass and confluence scan)

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py` (imports, `PassResult`, a new `_headroom_blocked`, one block in `_emit_signal`)
- Modify: `swingbot/core/scanning/analyze.py` (a new `_apply_headroom`, the `stats["failed_counts"]` literal in `_scan_one`, one assignment after the `_apply_pullback_dryup` line)
- Modify: `swingbot/core/scanning/scan_run.py` (the `failed_counts` literal, the `progress.funnel` dict, both `_maybe_run_strategy_pass` returns)
- Modify: `tests/backtesting/test_compression_reachability.py` (one expected dict gains a key)
- Create: `tests/scanning/test_headroom_live.py`

**Interfaces:**
- Consumes: `gates.headroom_active`, `gates.headroom_blocks_plan`, `gates.filter_headroom`, `gates.HEADROOM_REASON` (V135-2); `levels.build_level_map(df, h, current_price)`; `strategy_types.HORIZONS`.
- Consumes, verified: `run_strategy_pass` hands `_emit_signal` a `completed_frame(raw, now)`, so the strategy call site's frame is already free of today's forming bar. In `_scan_one` the names `supports` and `resistances` are the pair `levels.build_scenarios` was just called with.
- Produces: `strategy_pass._headroom_blocked(plan, frame, *, ticker, strategy, horizon) -> bool`, `PassResult.headroom: int`, `analyze._apply_headroom(scenarios, supports, resistances, stats, ticker, horizon_key) -> list`, funnel keys `failed_headroom` and `strategy_headroom`. V135-6 calls the two helpers directly.

- [ ] **Step 1: Invoke `no-lookahead` and `alert-surface`, then write the failing tests**

```python
# tests/scanning/test_headroom_live.py
"""v135 live call sites: the strategy pass vetoes a built plan before it is stored, the
confluence scan vetoes a scenario before it is scored, and both count under `headroom`."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze, dedup, engine, scan_run
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv
from tests.scanning.test_engine_v2_plans import _setup_minimal_scan
from tests.scanning.test_strategy_pass_emit import _Log, _plan, _Store

# test_strategy_pass_emit._plan(): bullish, trigger 100.0, stop 94.0 -> risk 6.0.
# A two-family resistance at 101.0 is 0.167R beyond entry: inside every grid value.
BLOCKED_MAP = ([], [Level(101.0, ["EMA50", "Rolling S/R"])])
CLEAR_MAP = ([], [Level(120.0, ["EMA50", "Rolling S/R"])])


def _knobs(monkeypatch, scope, min_r=0.75):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)


def _emit(monkeypatch, strategy, level_map=BLOCKED_MAP):
    builder, maps = Mock(return_value=_plan()), Mock(return_value=level_map)
    monkeypatch.setattr(sp, "build_strategy_plan_at", builder)
    monkeypatch.setattr(sp, "build_level_map", maps)
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    deps = sp._PassDeps(_Store(), _Log(), "paper", set(), lambda ticker: None)
    result, frame = sp.PassResult(), make_ohlcv([100.0] * 70)
    sp._emit_signal(result, frame, ticker="TEST", strategy=strategy, direction="bullish",
                    horizon="4w", bar_date="2024-04-08", regime=None, deps=deps)
    return result, builder, maps, frame


@pytest.mark.parametrize("scope,min_r,strategy,blocked,builds_map", [
    ("strategy", 0.75, "Fibonacci", True, True),
    ("strategy", 0.75, "MACD", False, False),
    ("strategy", 0.0, "Fibonacci", False, False),
    ("confluence", 0.75, "Fibonacci", False, False),
    ("off", 0.75, "Fibonacci", False, False),
])
def test_strategy_veto_after_the_plan_is_built(monkeypatch, scope, min_r, strategy, blocked, builds_map):
    _knobs(monkeypatch, scope, min_r)
    result, builder, maps, _frame = _emit(monkeypatch, strategy)
    assert builder.call_count == 1                      # the veto reads the built plan
    assert result.headroom == int(blocked)
    assert len(result.plans) == int(not blocked)
    assert maps.call_count == int(builds_map)           # an inactive gate builds no map


def test_a_clear_path_is_not_vetoed(monkeypatch):
    _knobs(monkeypatch, "strategy")
    result, _builder, maps, _frame = _emit(monkeypatch, "Fibonacci", CLEAR_MAP)
    assert result.headroom == 0 and len(result.plans) == 1 and maps.call_count == 1


def test_the_live_map_is_built_on_the_frame_the_pass_handed_over(monkeypatch):
    """NO-LOOKAHEAD: the map reads the completed frame itself, split at its last close."""
    _knobs(monkeypatch, "strategy")
    _result, _builder, maps, frame = _emit(monkeypatch, "Fibonacci")
    df, horizon, price = maps.call_args.args
    assert df is frame and horizon is HORIZONS["4w"]
    assert price == float(frame["Close"].iloc[-1])


def _scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=98.0)


def test_confluence_helper_drops_and_counts(monkeypatch):
    _knobs(monkeypatch, "confluence")
    stats = {"failed_counts": {"headroom": 0}}
    kept = analyze._apply_headroom([_scenario()], *BLOCKED_MAP, stats, "TEST", "4w")
    assert kept == [] and stats["failed_counts"]["headroom"] == 1


@pytest.mark.parametrize("scope,min_r", [("off", 0.75), ("strategy", 0.75), ("confluence", 0.0)])
def test_confluence_helper_is_a_no_op_when_inactive(monkeypatch, scope, min_r):
    _knobs(monkeypatch, scope, min_r)
    stats, scenario = {"failed_counts": {"headroom": 0}}, _scenario()
    assert analyze._apply_headroom([scenario], *BLOCKED_MAP, stats, "TEST", "4w") == [scenario]
    assert stats["failed_counts"]["headroom"] == 0


def _strategy_summary(monkeypatch):
    monkeypatch.setattr(sp, "strategy_signals", lambda *a, **k: [("Fibonacci", "bullish")])
    monkeypatch.setattr(sp, "_shadow_step", lambda *a, **k: None)
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: _plan())
    monkeypatch.setattr(sp, "build_level_map", lambda *a, **k: BLOCKED_MAP)
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    monkeypatch.setattr(scan_run, "live_horizons", lambda: ["4w"])
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    monkeypatch.setattr(scan_run, "_compression_hooks", lambda *a: (None, None))
    monkeypatch.setattr(scan_run, "_compression_seen", set)
    return scan_run._maybe_run_strategy_pass(
        tickers=["TEST"], fresh_data={"TEST": make_ohlcv([100.0] * 70)}, spy_df=None,
        regimes=None, rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
        sector_etf_frames={}, trade_log=_Log(), alerts=[], require_confirmation=False)


def test_strategy_funnel_counts_real_rejections(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "shadow")
    _knobs(monkeypatch, "strategy")
    summary = _strategy_summary(monkeypatch)
    assert summary["strategy_headroom"] == 1 and summary["strategy_plans"] == 0


def test_strategy_funnel_off_includes_a_zero_headroom_count(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "off")
    summary = scan_run._maybe_run_strategy_pass(
        tickers=[], fresh_data={}, spy_df=None, regimes=None, rs_cache=None,
        sector_of_ticker={}, etf_symbol_of_sector={}, sector_etf_frames={},
        trade_log=_Log(), alerts=[], require_confirmation=False)
    assert summary["strategy_headroom"] == 0


def test_live_scan_off_then_confluence(monkeypatch, tmp_path, stub_batch_fetch):
    """End to end through _sync_run_scan: off reads nothing; confluence hands the predicate
    the scan's own levels and counts every rejection in the funnel."""
    _setup_minimal_scan(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 1.0)
    seen = []

    def rejects(entry, stop, direction, levels, min_r):
        seen.append(list(levels))
        return True
    monkeypatch.setattr(gates, "headroom_rejects", rejects)
    monkeypatch.setattr(dedup, "dedup_scan_items", lambda items: [])
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "off")
    before = engine.ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=before, min_confluence=0)
    assert before.funnel["scenarios_found"] > 0
    assert seen == [] and before.funnel["failed_headroom"] == 0
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "confluence")
    after = engine.ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=after, min_confluence=0)
    assert after.funnel["scenarios_found"] == 0
    assert after.funnel["failed_headroom"] == before.funnel["scenarios_found"]
    assert seen and all(levels and all(isinstance(level, Level) for level in levels)
                        for levels in seen)
```

`_plan()` in `tests/scanning/test_strategy_pass_emit.py` has no `entry_price` attribute; `gates.planned_entry` reads it with `getattr`, so the stub works unchanged. Do not edit that helper.

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_headroom_live.py`
Expected: FAIL with `AttributeError: <module 'swingbot.core.scanning.strategy_pass'> does not have the attribute 'build_level_map'`, plus the missing `_apply_headroom`.

- [ ] **Step 3: Implement the strategy-pass call site**

In `strategy_pass.py`, replace the existing `gates` import line with the first line below and add the other two beside the other `swingbot.core.market` imports:

```python
from swingbot.core.edge.gates import (HEADROOM_REASON, PULLBACK_VOLUME_REASON, headroom_active,
                                      headroom_blocks_plan, pullback_dryup_blocks)
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.strategy_types import HORIZONS
```

Add `headroom: int = 0` as the last field of `PassResult` (after `pullback_volume`). Add directly above `_emit_signal`:

```python
def _headroom_blocked(plan, frame, *, ticker, strategy, horizon) -> bool:
    """v135: veto a built plan whose path to TP1 is blocked. The level map is built here, on
    the pass's completed daily frame, and only while the strategy scope is active."""
    if not headroom_active("strategy", strategy):
        return False
    level_map = build_level_map(frame, HORIZONS[horizon], float(frame["Close"].iloc[-1]))
    if not headroom_blocks_plan(plan, level_map, strategy=strategy):
        return False
    log.debug("%s (%s, %s, %s): rejected %s", ticker, horizon, strategy,
              plan.direction, HEADROOM_REASON)
    return True
```

In `_emit_signal`, directly after the `if plan is None:` block (the one that calls `_count_plan_none` and returns) and before `plan.entry_context = {**(plan.entry_context or {}), **stamp}`:

```python
    if _headroom_blocked(plan, frame, ticker=ticker, strategy=strategy, horizon=horizon):
        result.headroom += 1
        return
```

- [ ] **Step 4: Implement the confluence call site and the funnel slots**

In `analyze.py`, add directly below `_apply_pullback_dryup`:

```python
def _apply_headroom(scenarios, supports, resistances, stats, ticker, horizon_key) -> list:
    """v135: drop confluence scenarios whose path to target 1 is blocked, counted in the
    funnel. It reads the very lists the scenarios were built from: no map build, no frame."""
    kept, rejected = gates_mod.filter_headroom(scenarios, supports, resistances)
    stats["failed_counts"]["headroom"] += len(rejected)
    for scenario in rejected:
        log.debug("%s (%s, %s): rejected %s", ticker, horizon_key,
                  scenario.direction, gates_mod.HEADROOM_REASON)
    return kept
```

In `_scan_one`'s `stats` literal, extend the `failed_counts` second line so it ends `"opex_close_window": 0, "pullback_volume": 0, "headroom": 0,`.

In `_scan_one`, insert one line directly after `scenarios = _apply_pullback_dryup(scenarios, df, stats, ticker, horizon_key)`:

```python
        scenarios = _apply_headroom(scenarios, supports, resistances, stats, ticker, horizon_key)
```

In `scan_run.py`:
- extend the merge-loop `failed_counts` literal the same way (`"pullback_volume": 0, "headroom": 0,`);
- in the `progress.funnel = {` dict, after `"failed_pullback_volume": failed_counts["pullback_volume"],` add `"failed_headroom": failed_counts["headroom"],`;
- in `_maybe_run_strategy_pass`, add `"strategy_headroom": 0` to the dict returned when the mode is `off`, and `"strategy_headroom": result.headroom` to the final return, each after its `strategy_pullback_volume` entry.

In `tests/backtesting/test_compression_reachability.py::test_off_mode_scan_returns_zero_compression_funnel_keys`, add `"strategy_headroom": 0` to the expected dict.

- [ ] **Step 5: Run the narrow tests, neighbours and radon**

Run: `python scripts/dev/testrun.py file tests/scanning/test_headroom_live.py`, then `... file tests/scanning/test_pullback_dryup_live.py`, `... file tests/scanning/test_strategy_pass_emit.py`, `... file tests/scanning/test_engine_v2_plans.py`, `... file tests/backtesting/test_compression_reachability.py`, then `python -m radon cc -s swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/analyze.py | grep -E "_emit_signal|_headroom_blocked|_apply_headroom|_scan_one"`
Expected: all PASS. `_emit_signal` at C (12), the two new helpers at A, `_scan_one` unchanged at E (36). If the top-level `build_level_map` import raises an import cycle, move those two imports inside `_headroom_blocked` and patch `swingbot.core.market.levels.build_level_map` in the test's `_emit` and `_strategy_summary` instead of `sp.build_level_map`; report the cycle in the task notes.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/analyze.py swingbot/core/scanning/scan_run.py tests/scanning/test_headroom_live.py tests/backtesting/test_compression_reachability.py
git commit -m "feat(v135): live headroom veto call sites; headroom funnel counts"
```

### Task V135-5: Replay call sites (strategy arm engine and confluence replay)

**Files:**
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (a new module function `level_map_at`, and `StrategyEngine._gated_plan`; `iter_trades` and `_candidate_plan` are **not** edited)
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (a new `_headroom_kept`; one assignment in `replay_scenarios`)
- Create: `tests/backtesting/arms/test_headroom_replay.py`

**Cross-plan (audit 2026-10-10):** v146 V146-7 may have split `replay_scenarios` into helpers. Check `git grep -n "def replay_scenarios_detailed\|def _bar_scenarios" -- swingbot/core/backtesting/backtest_scenarios.py`. **If both exist (v146 merged),** Step 4's insertion point `scenarios = _dryup_kept(scenarios, window)` no longer exists: instead, in `_bar_scenarios`, change `return window, price, (supports, resistances), _dryup_kept(scenarios, window)` to `return window, price, (supports, resistances), _headroom_kept(_dryup_kept(scenarios, window), supports, resistances)`, and in Step 5's radon line expect `_bar_scenarios` below 15 (it gains no branch) in place of `replay_scenarios` C (15). **Otherwise** as written.

**Interfaces:**
- Consumes: `gates.headroom_active`, `gates.headroom_blocks_plan`, `gates.filter_headroom` (V135-2); the V135-3 witness.
- Produces:
  - `strategy_engine.level_map_at(df, index, horizon_key) -> tuple[list, list]`: the `(supports, resistances)` map built on `df.iloc[:index + 1]`, split at `Close[index]`
  - `StrategyEngine._gated_plan(window, index, *, ticker, strategy, horizon_key, direction, level_map, params)`: signature unchanged; returns a `TradePlanV2` or `None`. While the strategy scope is active it builds `level_map_at(window, index, horizon_key)` for every in-scope signal whose plan was built, and vetoes on that map
  - `backtest_scenarios._headroom_kept(scenarios, supports, resistances) -> list`

**The strategy map (partner decision, 2026-10-06; spec "Live / replay parity").** The veto reads a map built **at the signal bar itself**, on the frame truncated at that bar. It never reads the engine's 5-bar TP2 bucket. The `level_map` argument is that bucket and keeps its one job: it is handed to `build_strategy_plan`, only `if wants_tp2`, exactly as today. So live (`strategy_pass._headroom_blocked`), replay (this task) and the clause-6 reading (V135-10) all judge a plan against the same map.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

```python
# tests/backtesting/arms/test_headroom_replay.py
"""v135 replay call sites: the same decision points as live. Strategy: after the plan is
built, on a level map built at the signal bar itself (never the engine's 5-bar TP2 bucket).
Confluence: on the lists the scenario came from."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
STRATEGY_ON = {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 1.0}
CONFLUENCE_ON = {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 1.0}
INACTIVE = [{"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 1.0},
            {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 0.0},
            {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 0.0}]
# The stub plan below is bullish, entry 100.0, stop 98.0 (risk 2.0).
BLOCKED_MAP = ([], [Level(101.0, ["EMA50", "Rolling S/R"])])    # 0.5R ahead: inside 0.75R
CLEAR_MAP = ([], [Level(120.0, ["EMA50", "Rolling S/R"])])      # 10R ahead


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


def boom(*args, **kwargs):
    raise AssertionError("an inactive headroom veto must not read or build any level")


@pytest.fixture
def always(monkeypatch):
    monkeypatch.setattr(gates, "headroom_rejects", lambda *args: True)


def _map_builds(monkeypatch, frame, delta) -> int:
    calls = []
    original = strategy_engine.build_level_map
    monkeypatch.setattr(strategy_engine, "build_level_map",
                        lambda *args, **kwargs: calls.append(1) or original(*args, **kwargs))
    run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, delta)
    monkeypatch.setattr(strategy_engine, "build_level_map", original)
    return len(calls)


@pytest.mark.parametrize("delta", INACTIVE)
def test_inactive_gate_never_computes_and_changes_nothing(frame, monkeypatch, delta):
    base = run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, delta) == base


def test_confluence_scope_removes_what_the_predicate_rejects(frame, always):
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, CONFLUENCE_ON) == []


def test_strategy_scope_leaves_confluence_untouched(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, STRATEGY_ON) == base


def test_confluence_scope_leaves_strategy_untouched(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, "nearest_blocker", boom)
    assert run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, CONFLUENCE_ON) == base


@pytest.mark.slow
@pytest.mark.parametrize("horizon", ["4w", "3m"])
def test_strategy_scope_gates_only_the_frozen_list(frame, always, horizon):
    base = run_arm("AAPL", frame, ("strategy",), (horizon,), WINDOW, {})
    assert any(trade.strategy in gates.HEADROOM_STRATEGIES for trade in base)
    gated = run_arm("AAPL", frame, ("strategy",), (horizon,), WINDOW, STRATEGY_ON)
    assert gated == [trade for trade in base if trade.strategy not in gates.HEADROOM_STRATEGIES]


@pytest.mark.slow
def test_an_inactive_gate_builds_no_extra_level_map(frame, monkeypatch):
    """Spec: with the gate off the strategy engine builds nothing it did not build before."""
    baseline = _map_builds(monkeypatch, frame, {})
    assert baseline > 0
    for delta in INACTIVE + [CONFLUENCE_ON]:
        assert _map_builds(monkeypatch, frame, delta) == baseline
    assert _map_builds(monkeypatch, frame, STRATEGY_ON) > baseline


def test_strategy_map_at_bar_t_ignores_every_later_bar(frame):
    """NO-LOOKAHEAD: truncating or rewriting the frame after t leaves the map at t unchanged."""
    t = 300
    full = strategy_engine.level_map_at(frame, t, "4w")
    assert full[0] or full[1], "fixture must yield levels or the test proves nothing"
    assert strategy_engine.level_map_at(frame.iloc[:t + 1], t, "4w") == full
    poisoned = frame.copy()
    poisoned.iloc[t + 1:] = poisoned.iloc[t + 1:] * 10.0
    assert strategy_engine.level_map_at(poisoned, t, "4w") == full


def _stub_plan():
    return SimpleNamespace(trigger_price=100.0, entry_price=None, stop_loss=98.0,
                           direction="bullish")


def _gated(frame, monkeypatch, strategy, *, bucket_map, signal_map, min_r=0.75):
    """Run _gated_plan the way iter_trades does: window = frame up to the signal bar.
    `bucket_map` is the engine's TP2 bucket argument; `signal_map` is what a map build at the
    signal bar returns. Returns (result, plan, maps the builder got, map builds asked for)."""
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    plan, built, asked = _stub_plan(), [], []
    monkeypatch.setattr(strategy_engine, "build_strategy_plan",
                        lambda *args, **kwargs: built.append(kwargs["level_map"]) or plan)
    monkeypatch.setattr(strategy_engine, "build_level_map",
                        lambda df, h, price: asked.append((len(df), price)) or signal_map)
    index = len(frame) - 10
    result = strategy_engine.StrategyEngine._gated_plan(
        frame.iloc[:index + 1], index, ticker="AAPL", strategy=strategy, horizon_key="4w",
        direction="bullish", level_map=bucket_map, params=None)
    return result, plan, built, asked, index


@pytest.mark.parametrize("strategy,blocked", [("Fibonacci", True), ("MACD", False)])
def test_gated_plan_vetoes_after_the_plan_is_built(frame, monkeypatch, strategy, blocked):
    result, plan, built, asked, _index = _gated(frame, monkeypatch, strategy,
                                                bucket_map=None, signal_map=BLOCKED_MAP)
    assert result is (None if blocked else plan)
    assert built == [None]                              # the builder's own argument is unchanged
    assert len(asked) == int(blocked)                   # an out-of-scope strategy builds no map


def test_the_veto_map_is_built_at_the_signal_bar(frame, monkeypatch):
    """The map is built on the frame truncated at the signal bar, split at that bar's close."""
    _result, _plan, _built, asked, index = _gated(frame, monkeypatch, "Fibonacci",
                                                  bucket_map=None, signal_map=CLEAR_MAP)
    assert asked == [(index + 1, float(frame["Close"].iloc[index]))]


def test_the_veto_never_reads_the_tp2_bucket_map(frame, monkeypatch):
    """Partner decision 2026-10-06. When the bucket lags, its map and the signal-bar map
    differ. The verdict must follow the signal-bar map in both directions, and the builder
    must still receive the bucket map untouched."""
    result, plan, built, _asked, _index = _gated(frame, monkeypatch, "Fibonacci",
                                                 bucket_map=BLOCKED_MAP, signal_map=CLEAR_MAP)
    assert result is plan and built == [BLOCKED_MAP]    # a stale blocker in the bucket is ignored
    result, plan, built, _asked, _index = _gated(frame, monkeypatch, "Fibonacci",
                                                 bucket_map=CLEAR_MAP, signal_map=BLOCKED_MAP)
    assert result is None and built == [CLEAR_MAP]      # a fresh blocker the bucket misses still vetoes


@pytest.mark.parametrize("scope,min_r", [("off", 0.75), ("confluence", 0.75), ("strategy", 0.0)])
def test_an_inactive_gated_plan_builds_no_map_and_returns_the_plan(frame, monkeypatch, scope, min_r):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)
    sentinel = object()
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *args, **kwargs: sentinel)
    monkeypatch.setattr(strategy_engine, "build_level_map", boom)
    result = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", level_map=None, params=None)
    assert result is sentinel


def test_no_plan_means_no_map_build(frame, monkeypatch):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 0.75)
    monkeypatch.setattr(strategy_engine, "build_strategy_plan", lambda *args, **kwargs: None)
    monkeypatch.setattr(strategy_engine, "build_level_map", boom)
    assert strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", level_map=None, params=None) is None
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_headroom_replay.py`
Expected: FAIL. `level_map_at` does not exist, `_gated_plan` never vetoes, and the confluence scope removes nothing.

- [ ] **Step 3: Implement the strategy replay call site**

In `strategy_engine.py`, add a module-level function above `class StrategyEngine`. It must call the module-level name `build_level_map`, because the V135-3 witness and the tests above count calls through that name:

```python
def level_map_at(df, index: int, horizon_key: str):
    """(supports, resistances) as of bar `index`: built on df.iloc[:index + 1] only and split
    at that bar's close. NO-LOOKAHEAD: no bar after `index` is read."""
    return build_level_map(df.iloc[:index + 1], HORIZONS[horizon_key],
                           float(df["Close"].iloc[index]))
```

Replace `_gated_plan` with:

```python
    @staticmethod
    def _gated_plan(window, index, *, ticker, strategy, horizon_key, direction,
                    level_map, params) -> TradePlanV2 | None:
        """Admit the signal on completed bars through index. v122's dry-up gate runs before
        the plan is built; v135's headroom veto runs after, on the built plan's own entry and
        stop. A rejection returns no plan, so it never occupies the one-position slot.

        `level_map` is the engine's 5-bar TP2 bucket and goes to the builder only. The veto
        never reads it: while the strategy scope is active it builds its own map at the
        signal bar (`window` ends there), the same map live builds on its completed frame."""
        if gates.pullback_dryup_blocks(window, direction, source="strategy", strategy=strategy):
            return None
        plan = build_strategy_plan(
            window, index, ticker=ticker, strategy=strategy,
            horizon_key=horizon_key, direction=direction,
            level_map=level_map, scan_params=params,
        )
        if plan is None or not gates.headroom_active("strategy", strategy):
            return plan
        signal_map = level_map_at(window, index, horizon_key)
        if gates.headroom_blocks_plan(plan, signal_map, strategy=strategy):
            return None
        return plan
```

Do not edit `iter_trades` or `_candidate_plan`. The TP2 bucket build (`if wants_tp2 and index // 5 != level_map_key:`) and the `level_map if wants_tp2 else None` argument stay exactly as they are, which is what keeps the plan handed to `build_strategy_plan` unchanged and the baseline byte-identical. `iter_trades` already passes `window = df.iloc[:index + 1]`, so `level_map_at(window, index, ...)` reads nothing after the signal bar.

- [ ] **Step 4: Implement the confluence replay call site**

In `backtest_scenarios.py`, add directly below `_dryup_kept`:

```python
def _headroom_kept(scenarios, supports, resistances) -> list:
    """v135: the confluence-scope headroom veto at analyze._apply_headroom's point, on the
    re-split lists the scenarios were just built from. A rejection sets no cooldown."""
    return edge_gates.filter_headroom(scenarios, supports, resistances)[0]
```

In `replay_scenarios`, insert one line directly after `scenarios = _dryup_kept(scenarios, window)`:

```python
        scenarios = _headroom_kept(scenarios, supports, resistances)
```

- [ ] **Step 5: Run the narrow tests, the witness and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_headroom_replay.py`, then `... file tests/backtesting/arms/test_pullback_dryup_replay.py`, `... file tests/backtesting/arms/test_strategy_engine.py`, `... file tests/backtesting/arms/test_confluence_engine.py`, `... file tests/backtesting/test_headroom_witness.py`, `... file tests/backtesting/test_pullback_dryup_witness.py`, then `python -m radon cc -s swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest_scenarios.py | grep -E "iter_trades |_candidate_plan|_gated_plan|level_map_at|replay_scenarios|_headroom_kept"`
Expected: all PASS, with both witnesses still byte-identical and the witness's level-map build count unchanged. `iter_trades` C (14) and `_candidate_plan` B (8) are untouched, `replay_scenarios` stays C (15) (legacy, not worse), `_gated_plan` A (5), the new helpers A. A witness failure means the baseline changed: fix the call site, never the witness file.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/arms/test_headroom_replay.py
git commit -m "feat(v135): replay headroom veto call sites; strategy veto reads a signal-bar map"
```

### Task V135-6: Live and replay parity on one fixture

**Files:**
- Create: `tests/backtesting/test_headroom_parity.py`

**Interfaces:**
- Consumes: `strategy_pass._emit_signal`, `strategy_pass.completed_frame`, `PassResult.headroom`, `analyze._apply_headroom` (V135-4); `StrategyEngine._gated_plan`, `backtest_scenarios._headroom_kept` (V135-5). It uses the **real** predicate and the **real** `build_level_map`; the only patches on the map builder are spies that pass through. Both strategy call sites build their map at the signal bar, so they must agree exactly, with no tolerance.
- Produces: nothing new.

- [ ] **Step 1: Write the test**

```python
# tests/backtesting/test_headroom_parity.py
"""v135 parity: one fixture through the live and the replay call site of each scope gives
the same accept/reject, for both directions and both sides of the boundary, including a
frame that carries today's forming bar (spec: Live / replay parity, Testing -- Parity)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.market.levels import build_level_map, strategy_family
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze
from swingbot.core.scanning import strategy_pass as sp
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.test_strategy_pass_emit import _Log, _Store

FRAME = _structured_df()
CLOSE = float(FRAME["Close"].iloc[-1])
BLOCKER_R = 0.6                              # the fixture's nearest confirmed level sits 0.6R away
BOUNDARY = [(0.75, True), (0.5, False)]      # 0.6R is inside 0.75R and outside 0.5R


def _level_map():
    return build_level_map(FRAME, HORIZONS["4w"], CLOSE)


def _blocker(direction):
    supports, resistances = _level_map()
    side = resistances if direction == "bullish" else supports
    return next(level for level in side
                if len({strategy_family(source) for source in level.sources}) >= 2)


def _stop(direction):
    """A stop that puts the nearest confirmed opposing level exactly BLOCKER_R x risk away."""
    risk = abs(_blocker(direction).price - CLOSE) / BLOCKER_R
    return CLOSE - risk if direction == "bullish" else CLOSE + risk


def _plan(direction, strategy):
    return SimpleNamespace(plan_id="p1", source="strategy", strategy=strategy, direction=direction,
                           horizon_key="4w", trigger_price=CLOSE, entry_price=None,
                           stop_loss=_stop(direction), tp1=None, tp2=None, badge="WEAK",
                           quality_score=0, cohort_label="COHORT_UNKNOWN", cohort_stats={},
                           risk_features={}, ledger="weak", entry_context={}, ticker="T")


def _knobs(monkeypatch, scope, min_r):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)


def _live_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: _plan(direction, strategy))
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    deps = sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="shadow", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="T", strategy=strategy, direction=direction,
                    horizon="4w", bar_date=frame.index[-1].date().isoformat(), regime=None,
                    deps=deps)
    assert (result.headroom == 1) == (result.plans == [])
    return result.headroom == 1


def _replay_strategy_rejects(monkeypatch, frame, direction, strategy):
    monkeypatch.setattr(strategy_engine, "build_strategy_plan",
                        lambda *a, **k: _plan(direction, strategy))
    plan = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker="T", strategy=strategy, horizon_key="4w",
        direction=direction, level_map=None, params=None)
    return plan is None


def test_the_fixture_holds_a_confirmed_level_on_both_sides():
    assert _blocker("bullish").price > CLOSE > _blocker("bearish").price


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("min_r,rejects", BOUNDARY)
@pytest.mark.parametrize("strategy", ["Fibonacci", "MACD"])
def test_strategy_live_and_replay_agree(monkeypatch, direction, min_r, rejects, strategy):
    _knobs(monkeypatch, "strategy", min_r)
    live = _live_strategy_rejects(monkeypatch, FRAME, direction, strategy)
    replay = _replay_strategy_rejects(monkeypatch, FRAME, direction, strategy)
    assert live == replay == (rejects and strategy == "Fibonacci")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("min_r,rejects", BOUNDARY)
def test_confluence_live_and_replay_agree(monkeypatch, direction, min_r, rejects):
    _knobs(monkeypatch, "confluence", min_r)
    supports, resistances = _level_map()
    scenario = SimpleNamespace(direction=direction, entry=CLOSE, stop_loss=_stop(direction))
    stats = {"failed_counts": {"headroom": 0}}
    live = analyze._apply_headroom([scenario], supports, resistances, stats, "T", "4w") == []
    replay = backtest_scenarios._headroom_kept([scenario], supports, resistances) == []
    assert live == replay == rejects
    assert stats["failed_counts"]["headroom"] == int(rejects)


@pytest.mark.parametrize("scope", ["strategy", "confluence"])
def test_scopes_never_cross_at_the_call_sites(monkeypatch, scope):
    """`strategy` never touches a confluence scenario and vice versa."""
    _knobs(monkeypatch, scope, 0.75)
    supports, resistances = _level_map()
    scenario = SimpleNamespace(direction="bullish", entry=CLOSE, stop_loss=_stop("bullish"))
    confluence_rejects = backtest_scenarios._headroom_kept([scenario], supports, resistances) == []
    strategy_rejects = _replay_strategy_rejects(monkeypatch, FRAME, "bullish", "Fibonacci")
    assert confluence_rejects == (scope == "confluence")
    assert strategy_rejects == (scope == "strategy")


def _with_forming_bar(frame):
    """Append today's unfinished bar, far above the fixture's range. If it reached the map
    builder, the map would be split at a different price and built on a different frame."""
    nxt = frame.index[-1] + pd.offsets.BDay(1)
    last = float(frame["Close"].iloc[-1])
    bar = pd.DataFrame({"Open": [last], "High": [last * 1.2], "Low": [last],
                        "Close": [last * 1.2], "Volume": [10_000_000.0]}, index=[nxt])
    return pd.concat([frame, bar]), datetime(nxt.year, nxt.month, nxt.day, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_live_and_replay_build_the_identical_signal_bar_map(monkeypatch, direction):
    """Live composes completed_frame(raw, now) then _emit_signal, exactly as
    run_strategy_pass does. Replay builds its map at the signal bar. Both must ask the map
    builder for the same frame and the same split price, and today's forming bar must reach
    neither."""
    raw, now = _with_forming_bar(FRAME)
    completed = sp.completed_frame(raw, now)
    assert len(completed) == len(FRAME) and completed.index[-1] == FRAME.index[-1]
    live_seen, replay_seen = [], []
    live_real, replay_real = sp.build_level_map, strategy_engine.build_level_map
    monkeypatch.setattr(sp, "build_level_map", lambda df, h, price:
                        live_seen.append((len(df), df.index[-1], price)) or live_real(df, h, price))
    monkeypatch.setattr(strategy_engine, "build_level_map", lambda df, h, price:
                        replay_seen.append((len(df), df.index[-1], price)) or replay_real(df, h, price))
    _knobs(monkeypatch, "strategy", 0.75)
    live = _live_strategy_rejects(monkeypatch, completed, direction, "Fibonacci")
    replay = _replay_strategy_rejects(monkeypatch, FRAME, direction, "Fibonacci")
    assert live is True and replay is True
    assert live_seen == replay_seen == [(len(FRAME), FRAME.index[-1], CLOSE)]
```

16:00 UTC is 12:00 ET, inside the regular session, so `completed_frame` drops the appended bar. `_structured_df()` dates its bars on business days from 2024-01-02, so the appended bar is a weekday.

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_headroom_parity.py`
Expected: PASS (17 cases: 1 fixture check, 8 strategy, 4 confluence, 2 scope, 2 identical-map). A failure here is a real parity bug in V135-4 or V135-5: the two strategy call sites build the same signal-bar map, so any disagreement is a defect, not a tolerance. Fix the call site; never fix the test by loosening it, and never change `build_level_map` from this plan.

- [ ] **Step 3: Commit**

```bash
git add tests/backtesting/test_headroom_parity.py
git commit -m "test(v135): live/replay headroom veto parity on one fixture"
```

### Task V135-7: Searchable classification, ScanParams and the reachability registry

**Files:**
- Modify: `swingbot/config.py` (`_SEARCH_CLASSES["searchable"]`)
- Modify: `swingbot/scan_params.py` (two fields and their `from_config` lines)
- Modify: `swingbot/core/backtesting/arms/reachability.py`
- Modify: `tests/backtesting/arms/test_reachability.py`

**Interfaces:**
- Consumes: the replay call sites (V135-5).
- Produces: `reachability.classify("HEADROOM_SCOPE") == REACHABLE` and the same for `HEADROOM_MIN_R`, with `observed_by=CS` and `fixture_observable=False` (a lone perturbation at the default is inert, the pattern `_DRYUP` uses). `config.searchable_attrs()` includes both. `ScanParams.headroom_scope: str = "off"` and `ScanParams.headroom_min_r: float = 0.0` (defaulted, at the end of the field list). `measure_arms.py --knob` then accepts both knobs.

All three source edits land in **one** commit: `test_reachability.py` requires the registry to equal `searchable_attrs()`, and `test_scan_params_coverage.py` requires a `ScanParams` field per searchable knob.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtesting/arms/test_reachability.py`)

```python
HEADROOM = ("HEADROOM_SCOPE", "HEADROOM_MIN_R")


def test_headroom_knobs_are_searchable_and_reachable_by_both_engines():
    for attr in HEADROOM:
        assert attr in config.searchable_attrs()
        assert r.classify(attr) == r.REACHABLE
        assert r.REGISTRY[attr].observed_by == r.CS
        assert r.REGISTRY[attr].fixture_observable is False
        assert "Stage -1" in r.reason(attr)


def test_headroom_knobs_are_threaded_through_scan_params():
    from swingbot.scan_params import ScanParams

    params = ScanParams.from_config()
    assert params.headroom_scope == "off" and params.headroom_min_r == 0.0


@pytest.mark.slow
def test_headroom_knobs_change_outcomes_together_on_the_fixture(monkeypatch):
    """Fixture-level stand-in for the Stage -1 pilot: both scopes reach trades."""
    from swingbot.core.backtesting.arms.engine import run_arm
    from swingbot.core.edge import gates
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    monkeypatch.setattr(gates, "headroom_rejects", lambda *args: True)
    frame, window = load_v74_fixture()["AAPL"], ("1900-01-01", "2100-12-31")
    for scope, engines in (("confluence", ("confluence",)), ("strategy", ("strategy",))):
        base = run_arm("AAPL", frame, engines, ("4w", "3m"), window, {})
        gated = run_arm("AAPL", frame, engines, ("4w", "3m"), window,
                        {"HEADROOM_SCOPE": scope, "HEADROOM_MIN_R": 1.0})
        assert gated != base, scope
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`
Expected: FAIL. The knobs are not searchable and the registry has no entry for them.

- [ ] **Step 3: Implement**

In `config.py`, in `_SEARCH_CLASSES["searchable"]`, change the line that ends `"PULLBACK_DRYUP_SCOPE", "PULLBACK_DRYUP_MAX_RATIO",` by adding a new line directly below it:

```python
        "HEADROOM_SCOPE", "HEADROOM_MIN_R",
```

In `scan_params.py`, add two **defaulted** dataclass fields at the **end** of the `ScanParams` field list (after the last field, today `fvg_displacement_atr_k: float = 1.5`, and beside v139's defaulted `confluence_structural_stop_pct` / `confluence_stop_drop_pct` if those landed first; above `__post_init__`). The defaults make the fields order-safe and mean v147's `_scan_params_of`, which rebuilds stored rows into `ScanParams`, never raises on a row that predates these keys (audit 2026-10-10):

```python
    headroom_scope: str = "off"             # v135: off | strategy | confluence
    headroom_min_r: float = 0.0             # v135: 0 disables the gate
```

and in `from_config`, directly after the last keyword already there (today `fvg_displacement_atr_k=...`, or v139's lines if present):

```python
            headroom_scope=config.HEADROOM_SCOPE,
            headroom_min_r=config.HEADROOM_MIN_R,
```

Then run `git grep -n "ScanParams(" -- swingbot scripts tests`. The fields are defaulted, so a hand-built `ScanParams(...)` keeps working; on 2026-10-06 there were none.

In `reachability.py`, add beside `_DRYUP`:

```python
_HEADROOM = ("v135 headroom veto (edge/gates.py), applied to the built plan in "
             "StrategyEngine._gated_plan and to each scenario in "
             "backtest_scenarios._headroom_kept. Inert unless HEADROOM_SCOPE != off and "
             "HEADROOM_MIN_R > 0 together, so a lone perturbation at the default is inert "
             "by design. Stage -1: measure_arms.py --stage pilot --knob "
             "HEADROOM_SCOPE=<scope> --knob HEADROOM_MIN_R=1.0, then "
             "validate_component.py --stage reachability.")
```

and in `REGISTRY`, after `"PULLBACK_DRYUP_MAX_RATIO"`:

```python
    "HEADROOM_SCOPE": Reach(REACHABLE, _HEADROOM, CS),
    "HEADROOM_MIN_R": Reach(REACHABLE, _HEADROOM, CS),
```

v139 (V139-2) also appends `reachability.REGISTRY` rows and `searchable` entries in `config._SEARCH_CLASSES` (and `ScanParams` fields); whichever of v135 and v139 lands second rebases onto the other's rows, keeping both (audit 2026-10-10).

- [ ] **Step 4: Run the narrow tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`, then `... file tests/backtesting/test_knob_observability.py`, `... file tests/infra/test_scan_params_coverage.py`, `... file tests/test_config_headroom.py`
Expected: all PASS. The observability test skips both knobs because `fixture_observable=False`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py tests/backtesting/arms/test_reachability.py
git commit -m "feat(v135): classify the headroom knobs searchable and reachable; Stage -1 command in the registry"
```
