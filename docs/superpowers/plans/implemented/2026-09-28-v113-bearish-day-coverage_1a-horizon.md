# v113 Part 1a — The `1w` horizon, the `cells` mask key, and horizon vocabulary

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §1, §2, §8.1

Work happens in the worktree `.claude/worktrees/2026-09-28-v113-bearish-day-coverage` on branch `2026-09-28-v113-bearish-day-coverage`, created in V113-1 Step 1 (`worktree-lifecycle` skill). Every path below is relative to that worktree's root; no command uses `cd`.

---

# Phase A — Foundations (worktree branch)

### Task V113-1: Byte-identical witness for the ten existing horizons (golden written before any change)

**Files:**
- Create: `tests/market/test_v113_horizon_witness.py`
- Create: `tests/fixtures/v113/horizon_witness.json` (generated)

**Interfaces:**
- Consumes: `backtest.ALL_STRATEGIES`, `backtest._plan_series`, `backtest._trade_plan_at`, `entry_filters.entries_for`, `builders.build_strategy_plan`, `exit_sim.simulate_exit` — all as they exist on `main` at `a9ee7e24` or later.
- Produces: `witness_rows() -> list` and `pinned_config()` context manager in `tests/market/test_v113_horizon_witness.py`; the golden JSON. Every later v113 task runs this file as its regression witness.

- [ ] **Step 1: Create the worktree.** Load `worktree-lifecycle`. Create `.claude/worktrees/2026-09-28-v113-bearish-day-coverage` on a new branch of the same name from `main`. Run `git -C .claude/worktrees/2026-09-28-v113-bearish-day-coverage log --oneline -1` and confirm it equals `git log --oneline -1 main`. **Do not change any file under `swingbot/` before Step 4 has committed the golden.**

- [ ] **Step 2: Write the witness module.**

```python
"""v113 §1: adding the 1w horizon changes nothing on the ten existing horizons.

The golden (tests/fixtures/v113/horizon_witness.json) was written by this
module's __main__ BEFORE any v113 code landed (Task V113-1). Every later v113
task must leave it byte-identical: entries, backtest sizing (_trade_plan_at),
live sizing (build_strategy_plan) and the v2 exit, for every legacy strategy x
horizon x direction on the frozen TSLA fixture.

Regenerate ONLY on the pre-v113 tree:
    python -m tests.market.test_v113_horizon_witness
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

TESTS = Path(__file__).resolve().parents[1]
GOLDEN = TESTS / "fixtures" / "v113" / "horizon_witness.json"
OHLCV = TESTS / "fixtures" / "ohlcv" / "TSLA.csv"
# Spelled out, NOT read from strategy_types: the witness must not move when HORIZONS does.
LEGACY = ("2w", "4w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m")
PER_CELL = 3
# Every flag that can move a plan independently of v113, pinned so the golden
# measures v113's change only (and never today's date via opex, or the journal).
PINS = {
    "LEVEL_LIFECYCLE_STOPS_ENABLED": False,
    "DATA_DRIVEN_STOPS_ENABLED": False,
    "STALL_EXIT_ENABLED": False,
    "REGIME_GATES_ENABLED": False,
    "STRUCTURAL_STOP_SCOPE": "",
    "OPEX_STOP_WIDEN_PCT": 0.0,
    "FIB_SR_CONFLUENCE_ATR": 0.0,
    "FIB_LEVEL_STOP_ATR": 0.0,
    "MIN_RISK_REWARD_RATIO": 1.5,
    "MAX_RISK_REWARD_RATIO": 2.5,
}
_MISSING = object()


@contextlib.contextmanager
def pinned_config():
    from swingbot import config

    saved = {key: getattr(config, key, _MISSING) for key in PINS}
    try:
        for key, value in PINS.items():
            setattr(config, key, value)
        yield
    finally:
        for key, value in saved.items():
            if value is _MISSING:
                delattr(config, key)
            else:
                setattr(config, key, value)


def _r(value):
    return None if value is None else round(float(value), 6)


def _bt(df, i, direction, strategy, horizon, series) -> list:
    from swingbot.core.backtesting.backtest import _trade_plan_at

    picked = _trade_plan_at(df, i, direction, strategy, horizon, *series)
    return [None, None, None] if picked is None else [_r(value) for value in picked]


def _live(df, i, direction, strategy, horizon) -> list:
    from swingbot.core.planning.builders import build_strategy_plan
    from swingbot.core.planning.exit_sim import simulate_exit

    plan = build_strategy_plan(df, i, ticker="TSLA", strategy=strategy,
                               horizon_key=horizon, direction=direction)
    if plan is None:
        return [None] * 11
    res = simulate_exit(df, i, plan, scale_out=True)
    return [plan.entry_type, _r(plan.trigger_price), _r(plan.stop_loss), _r(plan.tp1),
            _r(plan.tp2), _r(plan.tp1_fraction), plan.expiry_bars,
            _r(plan.breakeven_trigger_fraction), res.outcome, res.exit_index, _r(res.r_total)]


def witness_rows() -> list:
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES, _plan_series
    from swingbot.core.market.entry_filters import entries_for

    df = pd.read_csv(OHLCV, index_col=0, parse_dates=True)
    rows = []
    with pinned_config():
        for strategy in ALL_STRATEGIES:
            for horizon in LEGACY:
                bull, bear = entries_for(strategy, df, horizon)
                series = _plan_series(df, strategy, horizon)
                for direction, mask in (("bullish", bull), ("bearish", bear)):
                    idx = [int(i) for i in np.flatnonzero(mask.to_numpy(dtype=bool))]
                    rows.append([strategy, horizon, direction, "entries", len(idx), sum(idx)])
                    for i in idx[-PER_CELL:]:
                        rows.append([strategy, horizon, direction, i,
                                     *_bt(df, i, direction, strategy, horizon, series),
                                     *_live(df, i, direction, strategy, horizon)])
    return rows


@pytest.mark.slow
def test_legacy_horizons_are_byte_identical_to_the_pre_v113_golden():
    assert witness_rows() == json.loads(GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(witness_rows(), indent=0) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
```

- [ ] **Step 3: Generate the golden on the untouched tree.** Run `git status --short swingbot/` — it must print nothing. Then:

Run: `python -m tests.market.test_v113_horizon_witness`
Expected: `wrote .../tests/fixtures/v113/horizon_witness.json`

Sanity-check that it witnesses real plans, not a wall of `None`:

```bash
python - <<'EOF'
import json
rows = json.load(open("tests/fixtures/v113/horizon_witness.json", encoding="utf-8"))
entries = [r for r in rows if r[3] == "entries"]
plans = [r for r in rows if r[3] != "entries"]
print("cells", len(entries), "signal cells", sum(1 for r in entries if r[4]))
print("plan rows", len(plans), "bt planned", sum(1 for r in plans if r[4] is not None),
      "live planned", sum(1 for r in plans if r[7] is not None))
EOF
```

Required: `cells 220`; at least 60 plan rows; both "planned" counts above 30. If a count is lower, report the numbers rather than changing the fixture ticker silently.

- [ ] **Step 4: Run it.**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon_witness.py`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/market/test_v113_horizon_witness.py tests/fixtures/v113/horizon_witness.json
git commit -m "test(v113): golden witness for the ten existing horizons, written before any v113 change

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-2: The `1w` horizon, `admits` with `cells`, `LEGACY_HORIZONS` and `live_horizons`

**Files:**
- Modify: `swingbot/core/market/strategy_types.py` (`HORIZONS`, `MIN_BARS`, new constants and functions after `STRATEGY_GATES`)
- Modify: `swingbot/core/market/entry_filters.py:128-163` (`entries_for`)
- Create: `tests/horizon_iteration.py` (AST helper consumed by V113-3 and V113-4)
- Create: `tests/market/test_v113_horizon.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (all in `swingbot.core.market.strategy_types`):
  - `HORIZONS["1w"]` — first key; `MIN_BARS["1w"] = 20`.
  - `MASKED_BY_DEFAULT_HORIZONS: tuple[str, ...] = ("1w",)`
  - `LEGACY_HORIZONS: tuple[str, ...]` — the ten pre-v113 keys in `HORIZONS` order.
  - `admits(strategy: str, direction: str, horizon_key: str) -> bool`
  - `live_horizons() -> tuple[str, ...]`
  - In `tests/horizon_iteration.py`: `iterations(path: Path) -> list[tuple[int, str]]`, `offenders(paths, allowed: set[tuple[str, str]]) -> list[str]`, `ROOT: Path`.

- [ ] **Step 1: Write the failing tests** — `tests/market/test_v113_horizon.py`:

```python
"""v113 §1-§2: the 1w horizon ships masked for every strategy; `cells` admits exact pairs."""
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import mtf
from swingbot.core.market import strategy_types as st
from tests.horizon_iteration import iterations, offenders

LEGACY = ("2w", "4w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m")


def test_1w_values_are_the_spec_table():
    assert st.HORIZONS["1w"] == {
        "label": "3-7 day swing", "ema_fast": 5, "ema_slow": 8, "vwap_window": 5,
        "fib_lookback": 10, "sr_lookback": 5, "atr_stop_multiple": 1.5,
        "max_risk_pct": 2.0, "sr_stop_pct": 2.0, "sr_target_min_pct": 2.0,
        "sr_target_max_pct": 5.0, "max_holding_days": 7, "rs_window": 10,
        "min_reward_pct": 2.0,
    }
    assert st.MIN_BARS["1w"] == 20


def test_1w_is_first_and_the_legacy_order_is_unchanged():
    assert list(st.HORIZONS)[0] == "1w"
    assert st.LEGACY_HORIZONS == LEGACY
    assert st.MASKED_BY_DEFAULT_HORIZONS == ("1w",)
    assert all("min_reward_pct" not in st.HORIZONS[hk] for hk in LEGACY)


def test_mtf_ladder_puts_1w_below_2w_and_leaves_the_rest_alone():
    assert mtf.adjacent_horizon("1w") == "2w"
    assert mtf.adjacent_horizon("2w") == "4w"
    assert mtf.adjacent_horizon("9m") is None


def test_every_registered_strategy_is_masked_on_1w_by_default():
    for strategy in ef.ENTRY_FUNCS:
        for direction in ("bullish", "bearish"):
            assert not st.admits(strategy, direction, "1w"), (strategy, direction)


def _pre_v113_allowed(strategy, direction, horizon_key):
    """Verbatim copy of the nested rule entries_for carried before v113."""
    gates = st.STRATEGY_GATES.get(strategy)
    if not gates:
        return True
    horizons = gates.get("horizons")
    by_direction = gates.get("horizons_by_direction") or {}
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return False
    permitted = by_direction.get(direction, horizons)
    return permitted is None or horizon_key in permitted


def test_admits_equals_the_pre_v113_rule_on_every_legacy_pair():
    for strategy in ef.ENTRY_FUNCS:
        for direction in ("bullish", "bearish"):
            for horizon in LEGACY:
                assert st.admits(strategy, direction, horizon) == _pre_v113_allowed(
                    strategy, direction, horizon), (strategy, direction, horizon)


def test_a_cell_admits_exactly_one_pair(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "MACD", {
        "directions": ("bullish",), "horizons": ("3m",), "cells": {("bearish", "1w")}})
    assert st.admits("MACD", "bearish", "1w")
    assert not st.admits("MACD", "bullish", "1w")
    assert not st.admits("MACD", "bearish", "3m")
    assert st.admits("MACD", "bullish", "3m")
    assert not st.admits("MACD", "bullish", "4m")


def test_a_cell_on_a_legacy_horizon_adds_to_the_axes(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "VWAP", {
        "directions": ("bullish",), "horizons": ("4w",), "cells": {("bullish", "2w")}})
    assert st.admits("VWAP", "bullish", "2w") and st.admits("VWAP", "bullish", "4w")
    assert not st.admits("VWAP", "bearish", "2w") and not st.admits("VWAP", "bullish", "2m")


def test_cells_work_on_a_fully_masked_strategy(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert st.admits("Probe", "bearish", "1w")
    assert not st.admits("Probe", "bearish", "2w") and not st.admits("Probe", "bullish", "1w")


def test_live_horizons_is_legacy_until_a_cell_admits_1w(monkeypatch):
    assert st.live_horizons() == LEGACY
    monkeypatch.setitem(st.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert st.live_horizons() == ("1w", *LEGACY)


def test_entries_for_masks_1w_and_honours_a_cell(market_df):
    raw_bull, raw_bear = ef.ENTRY_FUNCS["RSI Divergence"](market_df, "1w", None)
    bull, bear = ef.entries_for("RSI Divergence", market_df, "1w")
    assert not bull.any() and not bear.any()
    with ef.gate_override("RSI Divergence", {"cells": {("bearish", "1w")}}):
        bull, bear = ef.entries_for("RSI Divergence", market_df, "1w")
    assert not bull.any()
    pd.testing.assert_series_equal(bear, raw_bear, check_names=False)
    assert raw_bull.any() or raw_bear.any(), "fixture must fire at least once on 1w"


def test_iteration_finder_catches_every_form(tmp_path):
    source = "\n".join([
        "a = [k for k in HORIZONS]",
        "for k, h in HORIZONS.items(): pass",
        "b = list(HORIZONS.keys())",
        "c = {'all', *HORIZONS.keys()}",
        "d = len(HORIZONS)",
        "e = HORIZONS['2w']",
        "f = 'x' in HORIZONS",
        "g = {k: v for k, v in other.items() if k in HORIZONS}",
    ])
    path = tmp_path / "probe.py"
    path.write_text(source, encoding="utf-8")
    assert [n for n, _ in iterations(path)] == [1, 2, 3, 4, 5]
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon.py`
Expected: collection error — `ModuleNotFoundError: No module named 'tests.horizon_iteration'` (and `AttributeError` on `LEGACY_HORIZONS` once that exists).

- [ ] **Step 3: Create `tests/horizon_iteration.py`**

```python
"""v113: find code that ITERATES strategy_types.HORIZONS.

Since v113, HORIZONS holds a masked-by-default horizon ("1w"). A loop over it
silently scans or measures 1w. Iterate LEGACY_HORIZONS (confluence scans,
replays, measurement scripts) or live_horizons() (strategy vocabulary) instead.
Lookups (HORIZONS[k], HORIZONS.get(k)) and membership (k in HORIZONS) are fine.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = frozenset({"list", "tuple", "set", "frozenset", "len", "enumerate", "sorted", "iter"})
VIEWS = frozenset({"keys", "items", "values"})


def _is_horizons(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "HORIZONS"
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in VIEWS and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "HORIZONS")


def _hit(node) -> bool:
    if isinstance(node, (ast.For, ast.comprehension)):
        return _is_horizons(node.iter)
    if isinstance(node, ast.Starred):
        return _is_horizons(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in WRAPPERS:
        return bool(node.args) and _is_horizons(node.args[0])
    return False


def _line(node) -> int:
    return node.iter.lineno if isinstance(node, (ast.For, ast.comprehension)) else node.lineno


def iterations(path: Path) -> list[tuple[int, str]]:
    """(line number, stripped source line) of every HORIZONS iteration in `path`."""
    source = Path(path).read_text(encoding="utf-8")
    lines = source.splitlines()
    hits = sorted({_line(node) for node in ast.walk(ast.parse(source)) if _hit(node)})
    return [(number, lines[number - 1].strip()) for number in hits]


def offenders(paths, allowed: set[tuple[str, str]]) -> list[str]:
    """`path:line: text` for every iteration not in `allowed` ((posix relpath, stripped line))."""
    found = []
    for path in paths:
        rel = Path(path).resolve().relative_to(ROOT).as_posix()
        found.extend(f"{rel}:{number}: {text}" for number, text in iterations(path)
                     if (rel, text) not in allowed)
    return found
```

- [ ] **Step 4: Add `1w` and `MIN_BARS["1w"]`.** In `swingbot/core/market/strategy_types.py`, insert as the **first** entry of `HORIZONS` (directly after `HORIZONS = {`):

```python
    "1w": {
        # v113 §1: fixed by the spec and its pre-registration -- never grid-searched.
        # Masked for every strategy (MASKED_BY_DEFAULT_HORIZONS) until a
        # STRATEGY_GATES "cells" pair admits it; the confluence scan never runs it.
        "label": "3-7 day swing",
        "ema_fast": 5,
        "ema_slow": 8,
        "vwap_window": 5,
        "fib_lookback": 10,
        "sr_lookback": 5,
        "atr_stop_multiple": 1.5,
        "max_risk_pct": 2.0,
        "sr_stop_pct": 2.0,
        "sr_target_min_pct": 2.0,
        "sr_target_max_pct": 5.0,
        "max_holding_days": 7,
        "rs_window": 10,
        # v113 §1: the only horizon with a strategy-plan reward floor
        # (planning/reward_floor.py). Legacy horizons have none, as before v113.
        "min_reward_pct": 2.0,
    },
```

and as the first entry of `MIN_BARS`:

```python
    "1w": 20,   # v113: the 2w floor already covers every 1w lookback (<= 10) and the 20-bar volume mean
```

Directly after the closing `}` of `HORIZONS`, add:

```python

# v113 §1: horizons every strategy excludes -- and the confluence scan never
# runs -- until a STRATEGY_GATES "cells" pair admits them (see admits()).
MASKED_BY_DEFAULT_HORIZONS: tuple[str, ...] = ("1w",)
# The ten horizons that existed before v113, in HORIZONS order. Confluence
# scans, scenario replays and every measurement script iterate these, never
# HORIZONS itself (tests/horizon_iteration.py guards it).
LEGACY_HORIZONS: tuple[str, ...] = tuple(key for key in HORIZONS if key not in MASKED_BY_DEFAULT_HORIZONS)
```

- [ ] **Step 5: Add `admits` and `live_horizons`.** In the comment block above `STRATEGY_GATES`, replace the line `# A missing key means both directions, all horizons. entry_filters.entries_for` and the line after it with:

```python
# A missing key means both directions, all LEGACY horizons. v113 §2: an optional
# "cells" set of (direction, horizon) pairs is admitted IN ADDITION to what the
# legacy axes admit; it is the only way to admit a MASKED_BY_DEFAULT horizon.
# admits() is the rule; entry_filters.entries_for is its reader, so backtest
# and live signals both respect it.
```

Directly after the closing `}` of `STRATEGY_GATES` (before `# Minimum bars of history ...`), add:

```python


def admits(strategy: str, direction: str, horizon_key: str) -> bool:
    """v113 §2: THE mask rule. A (direction, horizon) pair is admitted when it
    is in the strategy's "cells", or when the horizon is not masked by default
    and the legacy axes (directions, horizons, horizons_by_direction) admit it.
    With no "cells" anywhere this is exactly the pre-v113 rule on every legacy
    horizon (pinned by tests/market/test_v113_horizon.py)."""
    gates = STRATEGY_GATES.get(strategy) or {}
    if (direction, horizon_key) in gates.get("cells", ()):
        return True
    if horizon_key in MASKED_BY_DEFAULT_HORIZONS:
        return False
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return False
    permitted = (gates.get("horizons_by_direction") or {}).get(direction, gates.get("horizons"))
    return permitted is None or horizon_key in permitted


def live_horizons() -> tuple[str, ...]:
    """The strategy vocabulary, in HORIZONS order: LEGACY_HORIZONS plus any
    masked-by-default horizon at least one "cells" pair admits. Read at call
    time, so a cell shipped in code (or a test's gate_override) shows up in
    commands, the admin UI and the live strategy pass without another edit."""
    admitted = {hk for gates in STRATEGY_GATES.values() for _direction, hk in gates.get("cells", ())}
    return tuple(key for key in HORIZONS if key not in MASKED_BY_DEFAULT_HORIZONS or key in admitted)
```

- [ ] **Step 6: `entries_for` reads `admits`.** In `swingbot/core/market/entry_filters.py`, change the import block to include `admits`:

```python
from swingbot.core.market.strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, SR_VOLUME_MULTIPLE,
    STRATEGY_GATES, admits,
)
```

In `entries_for`, replace the whole block from `gates = STRATEGY_GATES.get(strategy)` through `bearish = _off(df)` (the `if gates:` block with its nested `allowed`) with:

```python
    # v113 §2: strategy_types.admits is the mask rule (legacy axes + "cells").
    if not admits(strategy, "bullish", horizon_key):
        bullish = _off(df)
    if not admits(strategy, "bearish", horizon_key):
        bearish = _off(df)
```

Also change the docstring's first sentence to `Dispatch to the strategy's entry function, then apply the mask (strategy_types.admits: STRATEGY_GATES' direction/horizon axes plus v113 "cells").`

- [ ] **Step 7: Run the new tests, the witness and the neighbours**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon.py`
Expected: all PASS. If `test_entries_for_masks_1w_and_honours_a_cell` fails only on its last assertion (the fixture never fires RSI Divergence on 1w), switch the strategy to `"EMA Crossover"` in all four places and re-run; do not delete the assertion.

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon_witness.py tests/market/test_horizons.py tests/market/test_mtf.py tests/market/test_entry_filters.py tests/market/test_short_entries.py`
Expected: all PASS.

Run: `python -m radon cc -s -n C swingbot/core/market/strategy_types.py swingbot/core/market/entry_filters.py`
Expected: no `entries_for`, `admits` or `live_horizons` line (all below C).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/market/strategy_types.py swingbot/core/market/entry_filters.py tests/horizon_iteration.py tests/market/test_v113_horizon.py
git commit -m "feat(v113): 1w horizon masked by default, cells mask key via strategy_types.admits, LEGACY_HORIZONS and live_horizons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-3: Every `swingbot/` loop over horizons picks legacy or live vocabulary; gate description renders `cells`

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py:25,89,257`
- Modify: `swingbot/core/market/strategy.py:64-67,98`
- Modify: `swingbot/core/backtesting/backtest.py:529`
- Modify: `swingbot/core/backtesting/backtest_scenarios.py:20,241`
- Modify: `swingbot/core/backtesting/backtest_wf.py:129-133,475-479`
- Modify: `swingbot/core/backtesting/arms/windows.py:10,13`
- Modify: `swingbot/commands/info.py:12,44,138-139`
- Modify: `swingbot/commands/backtest.py:20,47,196`
- Modify: `swingbot/commands/history.py:23,208`
- Modify: `swingbot/commands/scanning/commands.py:10,69`
- Modify: `swingbot/commands/slash.py:20,27,119`
- Modify: `swingbot/admin/queries.py:44,164-183,238`
- Modify: `swingbot/admin/api_v1/analytics.py:477-482`
- Create: `tests/market/test_v113_horizon_vocab.py`
- Modify: `tests/admin/test_gate_description.py` (append)

**Interfaces:**
- Consumes: `LEGACY_HORIZONS`, `live_horizons()`, `admits` (V113-2); `tests.horizon_iteration.offenders`, `ROOT` (V113-2).
- Produces: the invariant "no `swingbot/` code iterates `HORIZONS` except three allow-listed lines", enforced by `tests/market/test_v113_horizon_vocab.py::test_no_swingbot_code_iterates_horizons`. `queries._gate_description` renders `cells`.

The rule per site: **confluence** (scan, `!check`, scenario replay, walk-forward, arm producer) → `LEGACY_HORIZONS`; **strategy vocabulary** (commands, admin, strategy pass, `evaluate_all`, `run_full_backtest`) → `live_horizons()`; **lookups and membership filters over real data** stay on `HORIZONS`.

- [ ] **Step 1: Write the failing tests** — `tests/market/test_v113_horizon_vocab.py`:

```python
"""v113: no swingbot/ code iterates HORIZONS (which now holds masked 1w)."""
import numpy as np

from swingbot.core.market import strategy_types as st
from tests.helpers import make_ohlcv
from tests.horizon_iteration import ROOT, offenders

# Deliberate: an ORDER map (1w first is harmless), the MTF ladder (1w sits below
# 2w and never becomes anyone's "next horizon up"), and an analytics filter's
# accepted values (a real 1w trade must be filterable once one exists).
ALLOWED = {
    ("swingbot/admin/api_v1/analytics.py", "order = {h: i for i, h in enumerate(HORIZONS)}"),
    ("swingbot/core/market/mtf.py", "_LADDER = list(HORIZONS.keys())"),
    ("swingbot/core/analytics/scope.py", 'horizon=_choice(args, "horizon", tuple(HORIZONS), None),'),
}


def _package_files():
    files = sorted((ROOT / "swingbot").rglob("*.py")) + [ROOT / "bot.py", ROOT / "admin_ui.py"]
    return [f for f in files if f.name != "strategy_types.py"]


def test_no_swingbot_code_iterates_horizons():
    assert offenders(_package_files(), ALLOWED) == []


def test_slash_horizon_choices_are_the_live_vocabulary():
    from swingbot.commands import slash
    assert [choice.value for choice in slash.HORIZON_CHOICES] == [*st.LEGACY_HORIZONS, "all"]


def test_evaluate_all_never_reports_1w():
    from swingbot.core.market.strategy import evaluate_all
    rng = np.random.default_rng(7)
    df = make_ohlcv(100 * np.cumprod(1 + rng.normal(0.0005, 0.015, 420)))
    assert "1w" not in {result.horizon_key for result in evaluate_all("X", df)}


def test_run_full_backtest_walks_the_live_vocabulary(monkeypatch):
    from swingbot.core.backtesting import backtest
    seen = []
    monkeypatch.setattr(backtest, "run_backtest",
                        lambda ticker, df, strategy, horizon, frictions=True: seen.append(horizon))
    backtest.run_full_backtest("X", None)
    assert sorted(set(seen)) == sorted(st.LEGACY_HORIZONS)


def test_arm_producer_vocabulary_stays_legacy():
    from swingbot.core.backtesting.arms import windows
    assert windows.ALL_HORIZONS == st.LEGACY_HORIZONS
```

Append to `tests/admin/test_gate_description.py`:

```python


def test_cells_are_rendered(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert queries._gate_description("Probe") == "only bearish 1w"
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {
        "directions": ("bullish",), "horizons": ("3m",), "cells": {("bearish", "1w")}})
    assert queries._gate_description("Probe") == "bullish only {3m} + bearish 1w"
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"cells": {("bullish", "1w")}})
    assert queries._gate_description("Probe") == "no gate (all directions, all horizons) + bullish 1w"
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon_vocab.py tests/admin/test_gate_description.py`
Expected: FAIL — the guard lists ~15 offenders; `HORIZON_CHOICES` starts with `1w`; `ALL_HORIZONS` includes `1w`; the cells description tests fail.

- [ ] **Step 3: Confluence sites → `LEGACY_HORIZONS`.**
  - `swingbot/core/scanning/scan_run.py`: change `from swingbot.core.market.strategy import HORIZONS` to `from swingbot.core.market.strategy import HORIZONS, LEGACY_HORIZONS, live_horizons`. At the `horizons_to_scan = [...]` line change `for hk in HORIZONS` to `for hk in LEGACY_HORIZONS` and add above it `# v113: the confluence scan never runs a masked-by-default horizon (1w).`
  - `swingbot/commands/scanning/commands.py`: import `LEGACY_HORIZONS` alongside `HORIZONS` from `swingbot.core.market.strategy`; change `if tl in ("all", *HORIZONS.keys()):` to `if tl in ("all", *LEGACY_HORIZONS):` (`!check` runs the confluence scan).
  - `swingbot/core/backtesting/backtest_scenarios.py`: import `LEGACY_HORIZONS` with `HORIZONS, MIN_BARS`; change `horizons = horizons or list(HORIZONS)` to `horizons = horizons or list(LEGACY_HORIZONS)`.
  - `swingbot/core/backtesting/backtest_wf.py`: in both local imports (`from swingbot.core.market.strategy_types import HORIZONS`) add `LEGACY_HORIZONS`, and change both `horizons = list(HORIZONS) if horizons is None else horizons` to `horizons = list(LEGACY_HORIZONS) if horizons is None else horizons`.
  - `swingbot/core/backtesting/arms/windows.py`: add `LEGACY_HORIZONS` to the `strategy_types` import; `ALL_HORIZONS: tuple[str, ...] = LEGACY_HORIZONS` (v100 provenance stamps compare against this tuple; it must not grow).

- [ ] **Step 4: Strategy vocabulary → `live_horizons()`.**
  - `swingbot/core/market/strategy.py`: add `LEGACY_HORIZONS, live_horizons,` to the `strategy_types` re-export import (keep `# noqa: F401`); in `evaluate_all` change `for horizon_key in HORIZONS:` to `for horizon_key in live_horizons():`.
  - `swingbot/core/scanning/scan_run.py` `_maybe_run_strategy_pass`: change `horizons=list(HORIZONS)` to `horizons=list(live_horizons())`.
  - `swingbot/core/backtesting/backtest.py` `run_full_backtest`: add `from swingbot.core.market.strategy_types import live_horizons` inside the function and change `for horizon_key in HORIZONS:` to `for horizon_key in live_horizons():`.
  - `swingbot/commands/info.py`: import `live_horizons` from `swingbot.core.market.strategy`; `for key, h in HORIZONS.items():` → `for key in live_horizons():` with `h = HORIZONS[key]` as the loop body's first line; `if horizon not in HORIZONS:` → `if horizon not in live_horizons():`; `', '.join(HORIZONS.keys())` → `', '.join(live_horizons())`.
  - `swingbot/commands/backtest.py`: import `live_horizons`; `horizons = list(HORIZONS.keys())` → `horizons = list(live_horizons())`; `valid_horizons = {"all", *HORIZONS.keys()}` → `valid_horizons = {"all", *live_horizons()}`.
  - `swingbot/commands/history.py`: import `live_horizons`; `list(HORIZONS.keys())` → `list(live_horizons())`.
  - `swingbot/commands/slash.py`: import `live_horizons`; `for k in HORIZONS]` → `for k in live_horizons()]`; in `slash_strategies`, `for key, h in HORIZONS.items():` → `for key in live_horizons():` with `h = HORIZONS[key]` as the body's first line.
  - `swingbot/admin/queries.py`: import `live_horizons` with `HORIZONS, STRATEGY_GATES`; `horizons = list(HORIZONS.keys())` → `horizons = list(live_horizons())`.
  - `swingbot/admin/api_v1/analytics.py` `analytics_heat_grid`: change the local import to `from swingbot.core.market.strategy_types import HORIZONS, live_horizons` and `cols = list(HORIZONS)` → `cols = list(live_horizons())`. Leave the `in HORIZONS` membership filter: a real 1w trade must not be dropped once 1w ships.

- [ ] **Step 5: `_gate_description` renders `cells`.** In `swingbot/admin/queries.py` replace `_gate_description` with:

```python
def _cells_text(gate: dict) -> str:
    """v113 §2: "bearish 1w, bullish 1w" for a gate's extra (direction, horizon) cells."""
    return ", ".join(f"{direction} {horizon}" for direction, horizon in sorted(gate.get("cells", ())))


def _gate_description(strategy: str) -> str:
    """Human-readable rendering of a STRATEGY_GATES entry -- e.g.
    Fibonacci's real current {"directions": ("bullish",)} becomes
    "bullish only"; VWAP's {"directions": ("bullish",),
    "horizons": ("4w","6m","7m","8m","9m")} becomes
    "bullish only {4w,6m,7m,8m,9m}". A missing key means no gate at all
    (both directions, every legacy horizon). v113 "cells" pairs are appended
    ("+ bearish 1w"), or stand alone ("only bearish 1w") on a strategy whose
    legacy directions are empty."""
    gate = STRATEGY_GATES.get(strategy)
    if not gate:
        return "no gate (all directions, all horizons)"
    cells = _cells_text(gate)
    directions = gate.get("directions")
    if directions is not None and len(directions) == 0:
        return f"only {cells}" if cells else "disabled (no direction allowed)"
    parts = []
    if directions:
        parts.append(f"{'/'.join(directions)} only" if len(directions) == 1 else "/".join(directions))
    horizons = gate.get("horizons")
    if horizons:
        parts.append("{" + ",".join(horizons) + "}")
    base = " ".join(parts) if parts else "no gate (all directions, all horizons)"
    return f"{base} + {cells}" if cells else base
```

- [ ] **Step 6: Run the tests, the witness and each touched module's own tests**

First remove any `HORIZONS` import this task left unused (run `python -m pyflakes <each file in Files>`; fix only `imported but unused` lines this task caused).

Run: `python scripts/dev/testrun.py file tests/market/test_v113_horizon_vocab.py tests/admin/test_gate_description.py tests/market/test_v113_horizon_witness.py`
Expected: all PASS. If the guard still lists a line, fix that line by the rule above; only the three `ALLOWED` lines may remain.

Run: `python scripts/dev/testrun.py file tests/test_slash_commands.py tests/commands/ tests/admin/test_api_v1_analytics.py tests/backtesting/arms/ tests/backtesting/test_scenario_parallel.py tests/backtesting/test_wf_engine.py tests/scanning/test_engine_v2_plans.py`
Expected: PASS, except possibly `tests/backtesting/test_scenario_parallel.py` (it slices `list(HORIZONS)[:3]`, fixed in V113-4 — note it and move on if that is the only failure).

Run: `python -m radon cc -s -n C swingbot/admin/queries.py swingbot/commands/info.py swingbot/commands/slash.py`
Expected: `_gate_description` and `_cells_text` absent (below C); no function's grade worse than before this task.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/core/market/strategy.py swingbot/core/backtesting/backtest.py swingbot/core/backtesting/backtest_scenarios.py swingbot/core/backtesting/backtest_wf.py swingbot/core/backtesting/arms/windows.py swingbot/commands/info.py swingbot/commands/backtest.py swingbot/commands/history.py swingbot/commands/scanning/commands.py swingbot/commands/slash.py swingbot/admin/queries.py swingbot/admin/api_v1/analytics.py tests/market/test_v113_horizon_vocab.py tests/admin/test_gate_description.py
git commit -m "feat(v113): confluence and replays iterate LEGACY_HORIZONS, strategy vocabulary iterates live_horizons(); gate description renders cells

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-4: Scripts and tests stop iterating `HORIZONS`

**Files:**
- Modify (one import line plus the listed lines each):
  `scripts/backtest/measure_adaptive_trail.py:76`, `measure_alert_density.py:513,555-558`, `measure_armed_entries.py:137`, `measure_bearish_arms.py:18`, `measure_earnings_blackout.py:66`, `measure_factor_lift.py:159`, `measure_fib_confluence.py:52`, `measure_fib_diagnostic.py:142`, `measure_fib_extension.py:77`, `measure_fib_v103.py:30`, `measure_rs_gate_effect.py:98`, `measure_stall_exit.py:75`, `measure_strategy_arm.py:122`, `measure_trend_signal_overlap.py:70,212-213`, `measure_v104.py:41`, `run_backtest_range.py:191,206,434`, `run_confluence_validation.py:178,187,196,201,210,239`, `tune_exit_v2.py:32`, `tune_strategy.py:68`, `v32_factor_correlation.py:89`, `v32_validation.py:65`, `wf_components.py:228`; `scripts/data/fill_regime_allow.py:104,178,238`; `scripts/dev/diagnose_funnel.py:81`, `diagnose_funnel2.py:54`, `seed_parity_fixtures.py:111`; `scripts/reports/audit_quality_score.py:29`, `parity_exits.py:83`, `parity_sizing.py:94`
- Modify: `tests/admin/test_api_analytics.py:420`, `tests/backtesting/test_scenario_parallel.py:43,61,97,117`, `tests/backtesting/test_arm_rule.py:36`, `tests/scripts/test_measure_v104.py:40`
- Create: `tests/scripts/test_v113_script_horizons.py`

**Interfaces:**
- Consumes: `LEGACY_HORIZONS` (V113-2); `tests.horizon_iteration.offenders`, `ROOT` (V113-2).
- Produces: the invariant "no `scripts/` code iterates `HORIZONS`", enforced by `tests/scripts/test_v113_script_horizons.py`. `measure_v104.ALL_HZ == LEGACY_HORIZONS` (V113-7 edits the same file afterwards).

Every script here measures, replays or diagnoses the pre-v113 horizons; closed pre-registrations must stay reproducible, so each iterates `LEGACY_HORIZONS`. `scripts/backtest/measure_v113.py` (V113-10) names `"1w"` explicitly and never iterates.

- [ ] **Step 1: Write the failing guard** — `tests/scripts/test_v113_script_horizons.py`:

```python
"""v113: no script iterates HORIZONS -- closed measurements stay on the ten legacy horizons."""
from tests.horizon_iteration import ROOT, offenders


def test_no_script_iterates_horizons():
    assert offenders(sorted((ROOT / "scripts").rglob("*.py")), set()) == []
```

Run: `python scripts/dev/testrun.py file tests/scripts/test_v113_script_horizons.py`
Expected: FAIL listing the script lines in **Files** above (about 40).

- [ ] **Step 2: Rewrite each offender.** For every file: add `LEGACY_HORIZONS` to its existing `from swingbot.core.market.strategy_types import ...` line (or add `from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402` under its imports when HORIZONS comes from `swingbot.core.market.strategy`), then apply the matching form:

| Form found | Replace with |
|---|---|
| `for hk in HORIZONS:` / `for horizon_key in HORIZONS:` | `for hk in LEGACY_HORIZONS:` (same loop variable) |
| `list(HORIZONS)` / `list(HORIZONS.keys())` / `HORIZONS.keys()` as a default | `list(LEGACY_HORIZONS)` |
| `tuple(HORIZONS)` | `tuple(LEGACY_HORIZONS)` |
| `len(HORIZONS)` | `len(LEGACY_HORIZONS)` |
| `{hk: [] for hk in HORIZONS}` | `{hk: [] for hk in LEGACY_HORIZONS}` |
| `for hk, h in HORIZONS.items():` | `for hk in LEGACY_HORIZONS:` and insert `h = HORIZONS[hk]` as the loop body's first line (same indentation as the body) |

Three sites need a specific shape:
  - `scripts/backtest/measure_trend_signal_overlap.py:212-213` becomes

```python
        hz_ema = {hk: (ema(close, HORIZONS[hk]["ema_fast"]), ema(close, HORIZONS[hk]["ema_slow"]))
                  for hk in LEGACY_HORIZONS}
```

  - `scripts/backtest/measure_alert_density.py`: the function-local import at line 513 gains `LEGACY_HORIZONS`; line 555's default becomes `list(LEGACY_HORIZONS)`, line 556 `if h not in LEGACY_HORIZONS`, line 558 `known: {list(LEGACY_HORIZONS)}`.
  - `scripts/backtest/tune_exit_v2.py:32`: `return list(gates.get("horizons", LEGACY_HORIZONS))`.

Leave every `HORIZONS[hk]` lookup as it is.

- [ ] **Step 3: Tests that slice or enumerate `HORIZONS`.** Import `LEGACY_HORIZONS` from `swingbot.core.market.strategy_types` in each and:
  - `tests/admin/test_api_analytics.py:420`: `horizons = list(LEGACY_HORIZONS)[:3]`.
  - `tests/backtesting/test_scenario_parallel.py:43,61,97,117`: every `list(HORIZONS)[:3]` / `list(HORIZONS)[:2]` → `list(LEGACY_HORIZONS)[:3]` / `[:2]`.
  - `tests/backtesting/test_arm_rule.py:36`: `tuple(HORIZONS)` → `LEGACY_HORIZONS`.
  - `tests/scripts/test_measure_v104.py:40`: `== tuple(HORIZONS)` → `== LEGACY_HORIZONS` (and import it).

Remove a `HORIZONS` import that becomes unused (pyflakes runs in `testrun.py`).

- [ ] **Step 4: Run the guard, the script tests and the touched test files**

Run: `python scripts/dev/testrun.py file tests/scripts/test_v113_script_horizons.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scripts/ tests/admin/test_api_analytics.py tests/backtesting/test_scenario_parallel.py tests/backtesting/test_arm_rule.py tests/backtesting/test_sizing_parity.py tests/backtesting/test_exit_parity.py`
Expected: all PASS.

Run: `python -m py_compile scripts/dev/diagnose_funnel.py scripts/dev/diagnose_funnel2.py scripts/data/fill_regime_allow.py scripts/reports/audit_quality_score.py scripts/backtest/v32_validation.py scripts/backtest/v32_factor_correlation.py`
Expected: no output (these have no tests; compile is the check).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_adaptive_trail.py scripts/backtest/measure_alert_density.py scripts/backtest/measure_armed_entries.py scripts/backtest/measure_bearish_arms.py scripts/backtest/measure_earnings_blackout.py scripts/backtest/measure_factor_lift.py scripts/backtest/measure_fib_confluence.py scripts/backtest/measure_fib_diagnostic.py scripts/backtest/measure_fib_extension.py scripts/backtest/measure_fib_v103.py scripts/backtest/measure_rs_gate_effect.py scripts/backtest/measure_stall_exit.py scripts/backtest/measure_strategy_arm.py scripts/backtest/measure_trend_signal_overlap.py scripts/backtest/measure_v104.py scripts/backtest/run_backtest_range.py scripts/backtest/run_confluence_validation.py scripts/backtest/tune_exit_v2.py scripts/backtest/tune_strategy.py scripts/backtest/v32_factor_correlation.py scripts/backtest/v32_validation.py scripts/backtest/wf_components.py scripts/data/fill_regime_allow.py scripts/dev/diagnose_funnel.py scripts/dev/diagnose_funnel2.py scripts/dev/seed_parity_fixtures.py scripts/reports/audit_quality_score.py scripts/reports/parity_exits.py scripts/reports/parity_sizing.py tests/admin/test_api_analytics.py tests/backtesting/test_scenario_parallel.py tests/backtesting/test_arm_rule.py tests/scripts/test_measure_v104.py tests/scripts/test_v113_script_horizons.py
git commit -m "refactor(v113): scripts and horizon-slicing tests iterate LEGACY_HORIZONS -- closed measurements never pick up 1w

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If `git add` reports a path that did not change (a listed file had no offender after all), drop it from the command rather than editing it.
