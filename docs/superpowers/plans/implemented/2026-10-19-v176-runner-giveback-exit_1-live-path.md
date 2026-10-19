# v176 — Runner give-back exit: Part 1, live path (V176-1..V176-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-19-v176-runner-giveback-exit-design.md](../specs/2026-10-19-v176-runner-giveback-exit-design.md)
**Index:** [2026-10-19-v176-runner-giveback-exit_0-index.md](2026-10-19-v176-runner-giveback-exit_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Scope of this part: the pure give-back helpers and the two config fields
(V176-1), the live tick path in `PlanManager._step_partial` (V176-2), the bar
catch-up path `_check_bar_partial` (V176-3) and the close-embed line
(V176-4). The simulators are part 2; the ship tooling is part 3.

Shared facts every task below relies on:

- `direction` values are `"bullish"` / `"bearish"`.
- `runner_floor(entry, tp1) = entry + (2/3) × (tp1 − entry)`.
- PlanManager tests use a real `PlanStore()` on the Postgres test database
  (autouse `_store_database` in `tests/conftest.py`). Run `/replicate-prod-db`
  once before the first test run of the session (CLAUDE.md rule).
- Per-task verification is `python scripts/dev/testrun.py file <test>`, never
  the full suite (V176-10 runs it once).
- No function written or changed may reach cyclomatic complexity 15
  (`_step_partial` is C=11 today, `_check_bar_partial` C=9): new logic lives
  in new helpers; the two step methods only gain plain calls.

---

# Phase 1 — Helpers and config

### Task V176-1: `giveback_stop` helpers + config fields

**Model:** sonnet — five small pure functions and two schema fields following existing templates, no cross-module design.

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (after `chandelier_stop`, ~:227-233)
- Modify: `swingbot/core/planning/plan_engine.py` (the `from .exit_sim import (...)` block :17-19 and `__all__` :38-53)
- Modify: `swingbot/config.py` (after the `TIGHTEN_ATR_MULT` `Field`, "Exit quality" section, ~:1219-1223)
- Modify: `.env.example` (after `TIGHTEN_ATR_MULT=1.75`, "Exit quality" block ~:700)
- Create: `tests/planning/test_giveback_stop.py`
- Create: `tests/infra/test_runner_giveback_config.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (all in `swingbot/core/planning/exit_sim.py`, the five functions re-exported from `swingbot/core/planning/plan_engine.py`):
  - `GIVEBACK_PCT_BOUNDS = (0.5, 49.0)`
  - `giveback_stop(extreme: float, pct: float, direction: str) -> float` — pct in percent; `ValueError` unless `0 < pct < 100`.
  - `runner_giveback_pct() -> float` — `config.RUNNER_GIVEBACK_PCT` clamped to `GIVEBACK_PCT_BOUNDS`, read at call time.
  - `giveback_level(extreme: float | None, direction: str) -> float | None` — `None` when the flag is off or `extreme is None`.
  - `tighter_stop(stop: float, other: float | None, is_bull: bool) -> float`
  - `runner_stop_source(stop: float, floor: float, giveback: float | None) -> str` — `"floor"` if `stop == floor`, else `"giveback"` if `stop == giveback`, else `"trail"`.
  - `config.RUNNER_GIVEBACK_ENABLED: bool` (default `True`), `config.RUNNER_GIVEBACK_PCT: float` (default `5.0`), both section `"Exit quality"`, `search_class="excluded"`, hot-reloadable.

**Why a clamp and not a cast check:** `config._cast` (config.py:1427) enforces no
`min`/`max`; only the admin save path (`swingbot/admin/api_v1/system.py:154-157`)
does. The spec asks for the `trail_notify_min_r()` precedent
(`plan_manager.py:132`): the Field carries `min=0.5, max=49.0` for the admin
path, and every reader goes through `runner_giveback_pct()`, so a hand-edited
`.env` with `RUNNER_GIVEBACK_PCT=0` or `60` cannot reach `giveback_stop`.

- [ ] **Step 1: Write the failing helper tests**

Create `tests/planning/test_giveback_stop.py`:

```python
"""v176: the give-back arithmetic, in one pure place shared by live and backtest."""
import pytest

from swingbot import config
from swingbot.core.planning import plan_engine
from swingbot.core.planning.exit_sim import (GIVEBACK_PCT_BOUNDS, giveback_level,
                                             giveback_stop, runner_giveback_pct,
                                             runner_stop_source, tighter_stop)


def test_long_giveback_is_pct_below_the_extreme():
    # The spec's worked example: long, best price 100, 5% -> 95.
    assert giveback_stop(100.0, 5.0, "bullish") == pytest.approx(95.0)


def test_short_giveback_is_pct_above_the_extreme():
    # RKLB short: best (lowest) price 49.94 -> 52.437.
    assert giveback_stop(49.94, 5.0, "bearish") == pytest.approx(52.437)


@pytest.mark.parametrize("pct", [0.0, -1.0, 100.0, 150.0])
def test_pct_outside_open_unit_interval_is_rejected(pct):
    with pytest.raises(ValueError):
        giveback_stop(100.0, pct, "bullish")


def test_pct_bounds_are_the_documented_range():
    assert GIVEBACK_PCT_BOUNDS == (0.5, 49.0)


@pytest.mark.parametrize("raw, expected", [(5.0, 5.0), (0.1, 0.5), (0.5, 0.5),
                                           (49.0, 49.0), (60.0, 49.0), (-3.0, 0.5)])
def test_runner_giveback_pct_clamps_the_config_value(monkeypatch, raw, expected):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", raw)
    assert runner_giveback_pct() == expected


def test_giveback_level_reads_the_flag_and_pct_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 10.0)
    assert giveback_level(200.0, "bullish") == pytest.approx(180.0)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    assert giveback_level(200.0, "bullish") == pytest.approx(190.0)
    assert giveback_level(200.0, "bearish") == pytest.approx(210.0)


def test_giveback_level_is_none_without_an_extreme(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    assert giveback_level(None, "bullish") is None


def test_giveback_level_is_none_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    assert giveback_level(200.0, "bullish") is None


@pytest.mark.parametrize("stop, other, is_bull, expected", [
    (106.0, 114.0, True, 114.0),     # long: the higher stop is tighter
    (115.0, 114.0, True, 115.0),     # long: never loosens
    (59.11, 52.437, False, 52.437),  # short: the lower stop is tighter
    (50.0, 52.437, False, 50.0),     # short: never loosens
    (106.0, None, True, 106.0),      # no give-back term
])
def test_tighter_stop(stop, other, is_bull, expected):
    assert tighter_stop(stop, other, is_bull) == expected


def test_runner_stop_source_names_the_term_that_set_the_stop():
    assert runner_stop_source(106.0, 106.0, 101.0) == "floor"
    assert runner_stop_source(114.0, 106.0, 114.0) == "giveback"
    assert runner_stop_source(115.0, 106.0, 114.0) == "trail"
    assert runner_stop_source(115.0, 106.0, None) == "trail"


def test_floor_wins_a_tie_with_the_giveback():
    # The reason label keys off the floor (tp1_runner_be); the source must agree.
    assert runner_stop_source(106.0, 106.0, 106.0) == "floor"


def test_helpers_are_re_exported_from_plan_engine():
    for name in ("giveback_stop", "runner_giveback_pct", "giveback_level",
                 "tighter_stop", "runner_stop_source"):
        assert name in plan_engine.__all__
        assert callable(getattr(plan_engine, name))
```

Create `tests/infra/test_runner_giveback_config.py`:

```python
"""v176: RUNNER_GIVEBACK_ENABLED / RUNNER_GIVEBACK_PCT in the schema and .env.example."""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from swingbot import config

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_enabled_flag_is_a_default_on_checkbox_outside_the_search():
    f = _field("RUNNER_GIVEBACK_ENABLED")
    assert (f.attr, f.type, f.default, f.section) == (
        "RUNNER_GIVEBACK_ENABLED", "checkbox", "true", "Exit quality")
    assert f.search_class == "excluded"
    assert f.hot_reloadable is True
    assert config._cast(f, f.default) is True


def test_pct_is_a_float_with_the_clamp_range():
    f = _field("RUNNER_GIVEBACK_PCT")
    assert (f.attr, f.type, f.default, f.section) == (
        "RUNNER_GIVEBACK_PCT", "float", "5.0", "Exit quality")
    assert (f.min, f.max) == (0.5, 49.0)
    assert f.search_class == "excluded"
    assert f.hot_reloadable is True
    assert config._cast(f, f.default) == 5.0


def test_module_globals_carry_the_types():
    assert isinstance(config.RUNNER_GIVEBACK_ENABLED, bool)
    assert isinstance(config.RUNNER_GIVEBACK_PCT, float)


def test_env_example_lists_both_keys_at_their_defaults():
    values = dotenv_values(ENV_EXAMPLE)
    assert values["RUNNER_GIVEBACK_ENABLED"] == "true"
    assert values["RUNNER_GIVEBACK_PCT"] == "5.0"


def test_absent_keys_take_the_defaults(monkeypatch, restore_config):
    monkeypatch.delenv("RUNNER_GIVEBACK_ENABLED", raising=False)
    monkeypatch.delenv("RUNNER_GIVEBACK_PCT", raising=False)
    config._apply_env()
    assert config.RUNNER_GIVEBACK_ENABLED is True
    assert config.RUNNER_GIVEBACK_PCT == 5.0


def test_a_reload_picks_up_a_changed_percent(monkeypatch, restore_config):
    # _apply_env() is what config.reload() (SIGHUP) runs after re-reading .env.
    from swingbot.core.planning.exit_sim import giveback_level
    monkeypatch.setenv("RUNNER_GIVEBACK_PCT", "7.5")
    monkeypatch.setenv("RUNNER_GIVEBACK_ENABLED", "true")
    config._apply_env()
    assert config.RUNNER_GIVEBACK_PCT == 7.5
    assert giveback_level(100.0, "bullish") == pytest.approx(92.5)


def test_a_reload_can_turn_the_flag_off(monkeypatch, restore_config):
    from swingbot.core.planning.exit_sim import giveback_level
    monkeypatch.setenv("RUNNER_GIVEBACK_ENABLED", "false")
    config._apply_env()
    assert config.RUNNER_GIVEBACK_ENABLED is False
    assert giveback_level(100.0, "bullish") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_giveback_stop.py`
Expected: FAIL at collection — `ImportError: cannot import name 'GIVEBACK_PCT_BOUNDS' from 'swingbot.core.planning.exit_sim'`.

Run: `python scripts/dev/testrun.py file tests/infra/test_runner_giveback_config.py`
Expected: FAIL — `StopIteration` from `_field("RUNNER_GIVEBACK_ENABLED")` and `KeyError: 'RUNNER_GIVEBACK_ENABLED'` from `dotenv_values`.

- [ ] **Step 3: Add the helpers to `exit_sim.py`**

In `swingbot/core/planning/exit_sim.py`, directly after `chandelier_stop` (its body
ends `return extreme_close_since_tp1 + mult * atr_value`), insert:

```python
#: v176: RUNNER_GIVEBACK_PCT's safe range in percent. The config Field carries
#: the same min/max for the admin save path; runner_giveback_pct() enforces it
#: for a hand-edited .env, which config._cast does not range-check.
GIVEBACK_PCT_BOUNDS = (0.5, 49.0)


def giveback_stop(extreme: float, pct: float, direction: str) -> float:
    """v176 give-back level: ``pct`` percent back from the runner's best price
    since TP1 -- ``E x (1 - p)`` for a long, ``E x (1 + p)`` for a short."""
    if not 0 < pct < 100:
        raise ValueError(f"give-back pct must be in (0, 100), got {pct!r}")
    p = pct / 100.0
    if direction == "bullish":
        return extreme * (1.0 - p)
    return extreme * (1.0 + p)


def runner_giveback_pct() -> float:
    """config.RUNNER_GIVEBACK_PCT clamped to GIVEBACK_PCT_BOUNDS, read at call
    time so a SIGHUP reload takes effect on the next tick."""
    low, high = GIVEBACK_PCT_BOUNDS
    return min(high, max(low, float(config.RUNNER_GIVEBACK_PCT)))


def giveback_level(extreme: float | None, direction: str) -> float | None:
    """The give-back term for a runner, or None (flag off, or no extreme yet)."""
    if extreme is None or not config.RUNNER_GIVEBACK_ENABLED:
        return None
    return giveback_stop(float(extreme), runner_giveback_pct(), direction)


def tighter_stop(stop: float, other: float | None, is_bull: bool) -> float:
    """The tighter of two runner stops; a missing term never loosens ``stop``."""
    if other is None:
        return stop
    return max(stop, other) if is_bull else min(stop, other)


def runner_stop_source(stop: float, floor: float, giveback: float | None) -> str:
    """Which term set the runner stop that fired: floor, giveback or trail.

    The floor is tested first so the source agrees with the unchanged
    ``runner_be`` / ``tp1_runner_be`` label, which keys off ``stop == floor``."""
    if stop == floor:
        return "floor"
    if giveback is not None and stop == giveback:
        return "giveback"
    return "trail"
```

- [ ] **Step 4: Re-export from `plan_engine.py`**

In `swingbot/core/planning/plan_engine.py`, replace the import block

```python
from .exit_sim import (ExitResult, _not_triggered, _single_leg_exit_walk,
                       chandelier_stop, runner_floor, _scale_out_exit_walk,
                       simulate_exit)
```

with

```python
from .exit_sim import (ExitResult, _not_triggered, _single_leg_exit_walk,
                       chandelier_stop, runner_floor, _scale_out_exit_walk,
                       simulate_exit, giveback_stop, runner_giveback_pct,
                       giveback_level, tighter_stop, runner_stop_source)
```

and in `__all__` replace the line

```python
    "_single_leg_exit_walk", "chandelier_stop", "runner_floor", "_scale_out_exit_walk",
```

with

```python
    "_single_leg_exit_walk", "chandelier_stop", "runner_floor", "_scale_out_exit_walk",
    "giveback_stop", "runner_giveback_pct", "giveback_level", "tighter_stop",
    "runner_stop_source",
```

- [ ] **Step 5: Add the two config fields**

In `swingbot/config.py`, directly after the `TIGHTEN_ATR_MULT` `Field(...)` entry
(its help ends `"other of v92 Hypothesis 1's two TRAIN grid dimensions."),`), insert:

```python
    Field("RUNNER_GIVEBACK_ENABLED", "RUNNER_GIVEBACK_ENABLED", "Exit quality",
          "Close the runner on a give-back from its best price",
          type="checkbox", default="true",
          help="v176: after TP1, the runner's stop is also held at "
               "RUNNER_GIVEBACK_PCT percent back from its best price since TP1 "
               "(long: best x (1 - p), short: best x (1 + p)); the tightest of "
               "the floor, the ATR chandelier and this level wins. Live and "
               "backtest share exit_sim.giveback_stop. Turning it off stops NEW "
               "tightening only -- a stop already tightened is never widened. "
               "On by the partner's decision, not by a backtest "
               "(docs/superpowers/specs/2026-10-19-v176-runner-giveback-exit-design.md)."),
    Field("RUNNER_GIVEBACK_PCT", "RUNNER_GIVEBACK_PCT", "Exit quality",
          "Runner give-back (% of the best price since TP1)",
          type="float", default="5.0", min=0.5, max=49.0, step=0.5,
          help="Percent of the runner's best price since TP1 it may give back "
               "before the give-back stop closes it. Read through a clamp to "
               "0.5-49 at every tick (exit_sim.runner_giveback_pct). Changing "
               "it is the partner's call; a re-tuned value is a new "
               "pre-registration, not a tweak."),
```

Do **not** add either key to `_SEARCH_CLASSES`: the default `search_class="excluded"` is intended, so `reachability.REGISTRY`, `ScanParams` and the guardrails' `CLOSED_PREREGISTRATION_KNOBS` need no edit.

- [ ] **Step 6: Document the keys in `.env.example`**

In `.env.example`, directly after the line `TIGHTEN_ATR_MULT=1.75` and its trailing blank line, insert:

```
# v176: after TP1, also hold the runner's stop RUNNER_GIVEBACK_PCT percent back
# from its best price since TP1 (long: best x (1 - p), short: best x (1 + p)).
# The tightest of the floor, the ATR chandelier and this level wins. Turning it
# off stops new tightening only; a stop already tightened is never widened.
RUNNER_GIVEBACK_ENABLED=true

# Percent of the best price since TP1; clamped to 0.5-49 at read time.
RUNNER_GIVEBACK_PCT=5.0

```

- [ ] **Step 7: Run the new tests and the config neighbours**

Run: `python scripts/dev/testrun.py file tests/planning/test_giveback_stop.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/infra/test_runner_giveback_config.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS (every schema key is in `.env.example`, no unknown key).

Run: `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`
Expected: PASS (an `excluded` field needs no `ScanParams` entry).

- [ ] **Step 8: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0, no new offender (each new helper is C ≤ 3).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/exit_sim.py swingbot/core/planning/plan_engine.py swingbot/config.py .env.example tests/planning/test_giveback_stop.py tests/infra/test_runner_giveback_config.py
git commit -m "feat(v176): giveback_stop helpers and RUNNER_GIVEBACK_* config fields"
```

# Phase 2 — Live paths

### Task V176-2: Live tick path: track extreme, apply give-back, `stop_source`

**Model:** sonnet — a contained refactor of one method into three helpers with a fixed contract and complete tests; the ordering trap is spelled out below.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (imports :26-29; `_step_partial` :1031-1090; `_ratchet_chandelier` :1092-1109; new helpers next to it)
- Create: `tests/planning/test_plan_manager_giveback.py`
- Modify: `tests/planning/test_plan_manager_structure_exit.py` (new autouse fixture after the imports; one new test at the end)

**Interfaces:**
- Consumes (V176-1, from `swingbot.core.planning.plan_engine`): `giveback_level(extreme, direction) -> float | None`, `runner_giveback_pct() -> float`, `tighter_stop(stop, other, is_bull) -> float`, `runner_stop_source(stop, floor, giveback) -> str`; `config.RUNNER_GIVEBACK_ENABLED`, `config.RUNNER_GIVEBACK_PCT`.
- Produces (consumed by V176-3, V176-4, V176-9):
  - `PlanManager._track_extreme(self, plan, price: float, is_bull: bool) -> bool` — True when `plan.runner_high_close` moved; persists only then.
  - `PlanManager._apply_giveback(self, plan, price: float) -> None` — tightens `plan.working_stop` to the give-back level; persists and logs `_plan_line("giveback stop", …)` only when the stop moves.
  - `PlanManager._ratchet_chandelier(self, plan, is_bull: bool, entry: float, moved: bool) -> None` — no `price` argument; reads `plan.runner_high_close`.
  - `PlanManager._runner_stop_extra(self, plan, stop: float) -> dict` — leg keys: always `"stop_source"` (`"floor"` / `"trail"` / `"giveback"`); when `"giveback"` also `"giveback_pct": float`, `"giveback_extreme": float`, `"giveback_stop": float`.

**The ordering this task fixes (spec § Where it changes, brief § 9):**
1. `runner_high_close` is updated on **every** tick, before anything else, by
   `_track_extreme` — today it is updated only inside `_ratchet_chandelier`
   behind `if self.atr_fn is None: return`, so a manager without `atr_fn`
   would leave `E` stale and the give-back would do nothing.
2. `_apply_giveback` runs on **every** tick (not only on a new extreme), so a
   runner open at deploy whose extreme never changes (RKLB) still tightens.
3. Both run **before** `_structure_runner_step`, and before the `stop` read
   (:1042), so the first tick past the level closes on it.
4. The chandelier keeps its exact behaviour: it still ratchets at the end of
   the tick, only when the extreme moved, and only with `atr_fn`.

`_step_partial` gains only straight-line calls and one keyword argument — no
new branch, so it stays at C=11.

- [ ] **Step 1: Write the failing live-path tests**

Create `tests/planning/test_plan_manager_giveback.py`:

```python
"""v176: the runner give-back on the live tick path (PlanManager._step_partial)."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

FLOOR = runner_floor(100.0, 110.0)                   # 106.6667
# RKLB short, plan 47f7fd16-...-376c85: best price 49.94, working stop 59.11
# (the runner floor). Entry/TP1 are back-solved so runner_floor() == 59.11.
RKLB_ENTRY, RKLB_STOP, RKLB_TP1, RKLB_E = 63.0, 66.0, 57.165, 49.94


@pytest.fixture(autouse=True)
def _giveback_on(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _runner(direction="bullish", entry=100.0, stop=95.0, tp1=110.0,
            extreme=None, working=None, ticker="AAPL"):
    """A plan already in PARTIAL: TP1 banked, runner open at its floor."""
    p = _plan(ticker=ticker, entry_type="market", direction=direction,
              trigger_price=entry, entry_price=entry, stop_loss=stop, tp1=tp1, tp2=None)
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    record_transition(p, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    p.legs_realized = [{"fraction": 0.5, "exit_price": tp1, "r": 2.0, "reason": "tp1"}]
    p.working_stop = runner_floor(entry, tp1) if working is None else working
    p.runner_floor_session = "2000-01-01"
    p.runner_high_close = extreme
    return p


def _rklb(**kw):
    return _runner(direction="bearish", entry=RKLB_ENTRY, stop=RKLB_STOP, tp1=RKLB_TP1,
                   extreme=RKLB_E, ticker="RKLB", **kw)


def _env(plan, atr_fn=None):
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, FakePriceFeed().get_price, atr_fn=atr_fn)


def step(store, mgr, price):
    return mgr._step_partial(store.get("p1"), price)


def test_rklb_fixture_floor_is_the_live_working_stop():
    assert runner_floor(RKLB_ENTRY, RKLB_TP1) == pytest.approx(59.11)


def test_long_runner_tightens_to_the_giveback_level():
    store, mgr = _env(_runner())
    assert step(store, mgr, 120.0) == []
    plan = store.get("p1")
    assert plan.runner_high_close == 120.0
    assert plan.working_stop == pytest.approx(114.0)        # 120 x 0.95 > floor 106.67
    assert plan.status == PlanStatus.PARTIAL


def test_short_runner_with_an_unchanged_extreme_still_tightens():
    # RKLB at deploy: E = 49.94 never changes, price bounced to 52.30.
    store, mgr = _env(_rklb())
    assert step(store, mgr, 52.30) == []
    plan = store.get("p1")
    assert plan.runner_high_close == RKLB_E
    assert plan.working_stop == pytest.approx(52.437)       # 49.94 x 1.05, was 59.11
    assert plan.status == PlanStatus.PARTIAL


def test_first_tick_already_past_the_level_moves_and_closes_on_one_tick():
    store, mgr = _env(_rklb())
    events = step(store, mgr, 52.60)                         # >= 52.437 for a short
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_trail"   # no new reason string
    assert events[0].detail["exit_price"] == 52.60            # live fill = the tick
    leg = events[0].detail["leg"]
    assert leg["stop_source"] == "giveback"
    assert leg["giveback_pct"] == 5.0
    assert leg["giveback_extreme"] == RKLB_E
    assert leg["giveback_stop"] == pytest.approx(52.437)
    assert leg["r"] == pytest.approx((RKLB_ENTRY - 52.60) / (RKLB_STOP - RKLB_ENTRY))
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED
    assert plan.working_stop == pytest.approx(52.437)


def test_never_loosens_when_the_trail_is_already_tighter():
    store, mgr = _env(_runner(extreme=120.0, working=118.0))
    step(store, mgr, 119.0)
    assert store.get("p1").working_stop == 118.0             # give-back 114 is looser


def test_never_loosens_when_the_floor_is_already_tighter():
    store, mgr = _env(_runner())
    step(store, mgr, 107.5)                                   # give-back 102.1 < floor
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_no_extreme_means_no_giveback_term():
    store, mgr = _env(_runner())
    plan = store.get("p1")
    mgr._apply_giveback(plan, 120.0)                          # E is None: nothing to do
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_flag_off_never_loosens_a_stop_already_tightened(monkeypatch):
    store, mgr = _env(_runner(extreme=120.0, working=114.0))
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    step(store, mgr, 116.0)
    assert store.get("p1").working_stop == 114.0


def test_flag_off_stops_new_tightening(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    store, mgr = _env(_runner())
    step(store, mgr, 120.0)
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


@pytest.mark.parametrize("enabled", [False, True])
def test_trail_path_is_unchanged_when_the_chandelier_is_tighter(monkeypatch, enabled):
    # ATR 2.0 x trail_atr_mult 2.5 -> trail = extreme - 5.0; give-back is
    # extreme x 0.95, looser at these prices, so both arms match pre-v176.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", enabled)
    store, mgr = _env(_runner(), atr_fn=lambda t: 2.0)
    assert step(store, mgr, 120.0) == []
    assert store.get("p1").working_stop == 115.0
    assert step(store, mgr, 118.0) == []
    assert store.get("p1").working_stop == 115.0
    events = step(store, mgr, 114.9)
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert events[0].detail["leg"]["stop_source"] == "trail"
    assert "giveback_stop" not in events[0].detail["leg"]


def test_isolated_spike_print_sets_the_extreme_for_good():
    # Accepted behaviour (spec § Risks): an extended-hours spike to 130 sets
    # E = 130 permanently; the give-back then sits at 123.5.
    store, mgr = _env(_runner())
    step(store, mgr, 130.0)
    assert store.get("p1").working_stop == pytest.approx(123.5)
    events = step(store, mgr, 122.0)
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert events[0].detail["leg"]["stop_source"] == "giveback"
    assert events[0].detail["leg"]["giveback_extreme"] == 130.0


def test_manager_without_atr_fn_still_tracks_the_extreme_and_applies_it():
    store, mgr = _env(_runner(), atr_fn=None)
    step(store, mgr, 120.0)
    step(store, mgr, 125.0)
    plan = store.get("p1")
    assert plan.runner_high_close == 125.0
    assert plan.working_stop == pytest.approx(118.75)


def test_floor_close_carries_stop_source_floor():
    store, mgr = _env(_runner())
    events = step(store, mgr, 106.0)                          # below the floor 106.67
    assert events[0].detail["reason"] == "tp1_runner_be"
    leg = events[0].detail["leg"]
    assert leg["stop_source"] == "floor"
    assert "giveback_pct" not in leg


def test_giveback_line_is_logged_only_when_the_stop_moves(caplog):
    store, mgr = _env(_runner())
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.plan_manager"):
        step(store, mgr, 120.0)
        step(store, mgr, 119.0)                               # same E, same level
    lines = [r.getMessage() for r in caplog.records if "giveback stop" in r.getMessage()]
    assert len(lines) == 1
    assert "AAPL" in lines[0]
```

In `tests/planning/test_plan_manager_structure_exit.py`, directly after the
imports (before `def at(day, hour):`), add:

```python
@pytest.fixture(autouse=True)
def _giveback_off(monkeypatch):
    """v176: isolate the structure rule; the give-back-first tests turn it on."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
```

and at the end of the file append:

```python
def test_giveback_closes_before_hl_trail_can_pre_empt_it(monkeypatch):
    # v176: track + give-back run before _structure_runner_step. Price 113.0,
    # hl_trail level 104.895, stored extreme 125.0 -> give-back 118.75 > price.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    df = sawtooth(4)
    confirm = WARMUP + 9
    plan = partial_plan(df)
    plan.runner_high_close = 125.0
    store, mgr = manager(df, plan, [confirm + 2])
    price = float(df["Open"].iloc[confirm + 1])
    assert price == pytest.approx(113.0)
    events = step(store, mgr, price, at(df.index[confirm + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_trail"]
    assert events[0].detail["leg"]["stop_source"] == "giveback"
    assert events[0].detail["leg"]["giveback_stop"] == pytest.approx(118.75)


def test_giveback_is_applied_even_on_a_tick_the_stall_closes(monkeypatch):
    # The stall closes at the tick price either way; the give-back has already
    # tightened and persisted the stop before the structure step ran.
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.70)
    df = stall_frame()
    j = _stall_bar(df)
    plan = partial_plan(df)
    plan.runner_high_close = 125.0                     # give-back 118.75 < price 120.4
    store, mgr = manager(df, plan, [j + 2])
    events = step(store, mgr, float(df["Open"].iloc[j + 1]), at(df.index[j + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_progress_stall"]
    assert store.get("p1").working_stop == pytest.approx(118.75)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_giveback.py`
Expected: FAIL — e.g. `test_long_runner_tightens_to_the_giveback_level` with `assert None == 120.0` (no `atr_fn`, so the extreme never updates today) and `KeyError: 'stop_source'` in the close tests; `test_no_extreme_means_no_giveback_term` with `AttributeError: 'PlanManager' object has no attribute '_apply_giveback'`.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_structure_exit.py`
Expected: the two new tests FAIL (`KeyError: 'stop_source'` / working stop still the floor); every existing test PASSES.

- [ ] **Step 3: Import the helpers in `plan_manager.py`**

Replace

```python
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       chandelier_stop, pending_expired,
                                       pending_invalidated, record_transition,
                                       runner_floor)
```

with

```python
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       chandelier_stop, giveback_level,
                                       pending_expired, pending_invalidated,
                                       record_transition, runner_floor,
                                       runner_giveback_pct, runner_stop_source,
                                       tighter_stop)
```

- [ ] **Step 4: Rewire `_step_partial`**

In `PlanManager._step_partial`, replace

```python
        risk = abs(entry - plan.stop_loss)
        structure = self._structure_runner_step(plan, price, now)
```

with

```python
        risk = abs(entry - plan.stop_loss)
        # v176: the extreme is tracked and the give-back applied on EVERY tick,
        # before the structure step and before the stop is read below, so a
        # runner open at deploy tightens on its first tick and a structure
        # exit can never skip the give-back.
        moved = self._track_extreme(plan, price, is_bull)
        self._apply_giveback(plan, price)
        structure = self._structure_runner_step(plan, price, now)
```

replace the stop-hit close

```python
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, price, reason, risk, sign)
```

with

```python
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, price, reason, risk, sign,
                                      extra=self._runner_stop_extra(plan, stop))
```

and replace the last two lines of the method

```python
        self._ratchet_chandelier(plan, price, is_bull, entry)
        return []
```

with

```python
        self._ratchet_chandelier(plan, is_bull, entry, moved)
        return []
```

- [ ] **Step 5: Replace `_ratchet_chandelier` and add the three helpers**

Replace the whole `_ratchet_chandelier` method (from
`def _ratchet_chandelier(self, plan, price, is_bull, entry) -> None:` through its
final `self.store.update(plan)`) with:

```python
    def _track_extreme(self, plan, price: float, is_bull: bool) -> bool:
        """v176: the runner's best tick since TP1 (bearish: lowest), on every
        tick and independent of atr_fn. True when it moved; persisted then."""
        old = plan.runner_high_close
        extreme = price if old is None else (max(old, price) if is_bull
                                             else min(old, price))
        if extreme == old:
            return False
        plan.runner_high_close = extreme
        self.store.update(plan)
        return True

    def _apply_giveback(self, plan, price: float) -> None:
        """v176: tighten working_stop to the give-back level off the tracked
        extreme. Never loosens; persists and logs only when the stop moves."""
        level = giveback_level(plan.runner_high_close, plan.direction)
        if level is None:
            return
        current = (plan.working_stop if plan.working_stop is not None
                   else runner_floor(plan.entry_price, plan.tp1))
        new_stop = tighter_stop(current, level, plan.direction == "bullish")
        if new_stop == current:
            return
        plan.working_stop = new_stop
        self.store.update(plan)
        _plan_line("giveback stop", plan, price,
                   f" stop={new_stop:.2f} from={current:.2f}"
                   f" extreme={plan.runner_high_close:.2f}")

    def _ratchet_chandelier(self, plan, is_bull: bool, entry: float, moved: bool) -> None:
        """Live chandelier ratchet off the extreme tick since TP1 (Task 66).

        v176: the extreme is tracked by _track_extreme; the chandelier still
        moves only on a new extreme and only with atr_fn wired."""
        if self.atr_fn is None or not moved:
            return
        atr_val = float(self.atr_fn(plan.ticker))
        trail = chandelier_stop(plan.runner_high_close, atr_val,
                                plan.trail_atr_mult, plan.direction)
        floor = (plan.working_stop if plan.working_stop is not None
                 else runner_floor(entry, plan.tp1))
        new_stop = tighter_stop(floor, trail, is_bull)
        if new_stop != plan.working_stop:
            plan.working_stop = new_stop
            self.store.update(plan)

    def _runner_stop_extra(self, plan, stop: float) -> dict:
        """v176: the closing runner leg's stop_source, plus the give-back
        level's inputs when the give-back set the stop that fired."""
        floor = runner_floor(plan.entry_price, plan.tp1)
        level = giveback_level(plan.runner_high_close, plan.direction)
        source = runner_stop_source(stop, floor, level)
        if source != "giveback":
            return {"stop_source": source}
        return {"stop_source": source, "giveback_pct": runner_giveback_pct(),
                "giveback_extreme": float(plan.runner_high_close),
                "giveback_stop": level}
```

Why `stop == level` is exact: `_apply_giveback` wrote `working_stop` from
`giveback_level(plan.runner_high_close, …)` on this same tick and
`_runner_stop_extra` recomputes it from the same `E` and the same config
values, so the float is bit-identical. A hand-flip of the flag between the
two calls (impossible within one tick) would only relabel the leg `"trail"`.

- [ ] **Step 6: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_giveback.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_structure_exit.py`
Expected: PASS (existing tests run flag-off through the autouse fixture; the two new tests pass).

- [ ] **Step 7: Run the live-behaviour neighbours (re-pin only if moved)**

Run each:

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py
python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gaps.py
```

Expected: PASS. Pre-checked against the brief: `test_trail_ratchets_and_closes`
(give-back 114.0 looser than trail 115.0), `test_price_just_above_the_floor_keeps_the_runner_open`
(give-back 101.65 looser than the floor) and `test_tp2_none_runner_ignores_high_prices`
(stop now 133.0, but only the `["stop_moved"]` transition list and `PARTIAL` are asserted) keep their numbers.

Decision rule for any test that fails here (index § Pinned-test decisions: these
test **live behaviour**, which is default-on, so they are **re-pinned**, never
pinned flag-off):
1. Confirm the failure is the give-back: the new value must equal
   `giveback_stop(E, 5.0, direction)` for the test's own `E`, or a transition
   list that differs only by a `stop_moved` / close caused by that level.
   Anything else is a bug in this task — fix the code, not the test.
2. Re-pin the assertion to the new value and add an inline comment
   `# v176: give-back on -- E x 0.95 = <value>` (`x 1.05` for a short).
3. Re-run that file alone with `python scripts/dev/testrun.py file <file>`.
List every re-pinned assertion (file, test, old → new) in the task report.

- [ ] **Step 8: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_step_partial` stays at C=11 (no branch added); each new helper is C ≤ 4.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_giveback.py tests/planning/test_plan_manager_structure_exit.py
git commit -m "feat(v176): live runner give-back -- track extreme every tick, tighten before the structure step, stop_source on the leg"
```

If Step 7 re-pinned anything, add those files to the same `git add`.

### Task V176-3: Bar catch-up path tightens before the bar test

**Model:** opus — a no-lookahead boundary: the bar path must tighten from the stored extreme only, and a wrong read of the checked bar's own high/low would pass most tests silently.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (`_check_bar_partial` :1323-1347)
- Modify: `tests/planning/test_plan_manager_giveback.py` (created by V176-2; append bar-path tests)

**Interfaces:**
- Consumes (V176-2): `PlanManager._apply_giveback(self, plan, price: float) -> None`, `PlanManager._runner_stop_extra(self, plan, stop: float) -> dict`; test helpers `_runner`, `_rklb`, `_env`, `FLOOR`, `RKLB_E` and the autouse `_giveback_on` fixture in `tests/planning/test_plan_manager_giveback.py`.
- Produces: `_check_bar_partial` calls `self._apply_giveback(plan, bar_open)` before its stop test and passes `extra=self._runner_stop_extra(plan, stop)` on a stop close. No new symbol.

**The rule (spec § Where it changes, item 2; Global Constraints):** the bar
path uses the **stored** `plan.runner_high_close`, never the checked bar's
own `bar_high` / `bar_low`. Reading the bar's own extreme would set a level
from a price that, intrabar, may have printed *after* the low that tests the
stop — lookahead. The bar path also does not update `runner_high_close`
(it never did), so its semantics stay: the stop it tests is the stop the
plan held when the bar opened, now including the give-back. The bar path is
unwired in production today (`check_bar` comment, plan_manager.py:1262);
this keeps it in parity with the tick path for when it is wired.

Fill is unchanged: `gap_stop_fill(bar_open, stop, direction)` — a bar that
opens through the give-back level fills at the open, which can be worse
than the level (spec § The rule: "the fill is not guaranteed to be" a win).

- [ ] **Step 1: Write the failing bar-path tests**

Append to `tests/planning/test_plan_manager_giveback.py`:

```python
# -- V176-3: the bar catch-up path (check_bar -> _check_bar_partial) ----------


def bar(store, mgr, o, h, l):
    return mgr.check_bar("p1", bar_open=o, bar_high=h, bar_low=l)


def test_bar_path_tightens_from_the_stored_extreme_before_its_test():
    store, mgr = _env(_runner(extreme=120.0))
    events = bar(store, mgr, 115.0, 116.0, 113.5)       # low 113.5 <= give-back 114.0
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_trail"
    # gap_stop_fill(115.0, 114.0, "bullish") == 114.0: opened above the level.
    assert events[0].detail["exit_price"] == pytest.approx(114.0)
    leg = events[0].detail["leg"]
    assert leg["stop_source"] == "giveback"
    assert leg["giveback_stop"] == pytest.approx(114.0)
    assert leg["giveback_extreme"] == 120.0


def test_bar_path_never_reads_the_checked_bars_own_extreme():
    # No stored extreme. If the bar's own high (130) were used, the level
    # would be 123.5 > low 120 and the runner would close: lookahead.
    store, mgr = _env(_runner())
    assert bar(store, mgr, 125.0, 130.0, 120.0) == []
    plan = store.get("p1")
    assert plan.working_stop == pytest.approx(FLOOR)
    assert plan.runner_high_close is None


def test_bar_path_uses_the_stored_extreme_not_a_higher_bar_high():
    # Stored E = 120 -> 114.0. The bar's high of 140 would give 133.0 > low 115.
    store, mgr = _env(_runner(extreme=120.0))
    assert bar(store, mgr, 121.0, 140.0, 115.0) == []
    plan = store.get("p1")
    assert plan.working_stop == pytest.approx(114.0)
    assert plan.runner_high_close == 120.0              # the bar path never moves E


def test_bar_path_gap_through_the_giveback_fills_at_the_open():
    store, mgr = _env(_runner(extreme=120.0))
    events = bar(store, mgr, 110.0, 111.0, 109.0)       # opened below 114.0
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert events[0].detail["exit_price"] == pytest.approx(110.0)   # worse than the level
    assert events[0].detail["leg"]["stop_source"] == "giveback"
    assert events[0].detail["leg"]["giveback_stop"] == pytest.approx(114.0)


def test_bar_path_short_runner_closes_on_its_giveback():
    store, mgr = _env(_rklb())
    events = bar(store, mgr, 52.0, 52.8, 51.5)          # high 52.8 >= 52.437
    assert events[0].detail["reason"] == "tp1_runner_trail"
    # gap_stop_fill(52.0, 52.437, "bearish") == max(52.0, 52.437) == 52.437
    assert events[0].detail["exit_price"] == pytest.approx(52.437)
    assert events[0].detail["leg"]["stop_source"] == "giveback"
    assert events[0].detail["leg"]["giveback_extreme"] == RKLB_E


def test_bar_path_flag_off_is_unchanged(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    store, mgr = _env(_runner(extreme=120.0))
    assert bar(store, mgr, 115.0, 116.0, 113.5) == []   # floor 106.67 still holds
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_bar_path_floor_close_carries_stop_source_floor():
    store, mgr = _env(_runner())
    events = bar(store, mgr, 107.0, 107.5, 100.0)
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(FLOOR)
    assert events[0].detail["leg"]["stop_source"] == "floor"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_giveback.py`
Expected: the V176-2 tests PASS; `test_bar_path_tightens_from_the_stored_extreme_before_its_test`,
`test_bar_path_uses_the_stored_extreme_not_a_higher_bar_high`, `test_bar_path_gap_through_the_giveback_fills_at_the_open`
and `test_bar_path_short_runner_closes_on_its_giveback` FAIL (no close / stop still the floor);
`test_bar_path_floor_close_carries_stop_source_floor` FAILS with `KeyError: 'stop_source'`.
`test_bar_path_never_reads_the_checked_bars_own_extreme` and `test_bar_path_flag_off_is_unchanged` already PASS (they pin what must not change).

- [ ] **Step 3: Tighten before the bar test and tag the leg**

In `PlanManager._check_bar_partial`, replace

```python
        risk = abs(plan.entry_price - plan.stop_loss)
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(plan.entry_price, plan.tp1))

        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            # v39: "tp1_runner_be" == "closed at the initial post-TP1 floor".
            reason = ("tp1_runner_be"
                      if stop == runner_floor(plan.entry_price, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, fill, reason, risk, sign)
```

with

```python
        risk = abs(plan.entry_price - plan.stop_loss)
        # v176: tighten from the STORED extreme before the bar test. Never the
        # checked bar's own high/low (no intrabar lookahead), and the bar path
        # never moves runner_high_close itself.
        self._apply_giveback(plan, bar_open)
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(plan.entry_price, plan.tp1))

        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            # v39: "tp1_runner_be" == "closed at the initial post-TP1 floor".
            reason = ("tp1_runner_be"
                      if stop == runner_floor(plan.entry_price, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, fill, reason, risk, sign,
                                      extra=self._runner_stop_extra(plan, stop))
```

The TP2 branch below is unchanged (a TP2 close carries no `stop_source`).

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_giveback.py`
Expected: PASS (all V176-2 and V176-3 tests).

Run each bar-path neighbour:

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gaps.py
```

Expected: PASS. The existing `check_bar` tests reach PARTIAL through `_check_bar_active`,
which never sets `runner_high_close`, so the give-back has no term there and
their floor fills are unchanged. If one fails anyway, apply V176-2 Step 7's
decision rule (re-pin with a `# v176: give-back on` comment only when the new
value equals the give-back level from that test's own stored `E`; otherwise
fix the code).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_check_bar_partial` stays at C=9 (one plain call and one keyword argument added).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_giveback.py
git commit -m "feat(v176): bar catch-up path tightens to the give-back from the stored extreme"
```

# Phase 3 — Telling the reader

### Task V176-4: Close embed give-back line

**Model:** sonnet — one pure formatting helper and one field append, tested in isolation against a fixed leg-key contract.

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`_closed_fields` :362-365; new helper directly above it)
- Create: `tests/scanning/test_giveback_embed.py`

**Interfaces:**
- Consumes (the leg-key contract fixed in the index ledger, produced by V176-2/V176-3 — this task does **not** import their code and may run in parallel with them): `event.detail["leg"]` may carry `"stop_source"` ∈ {`"floor"`, `"trail"`, `"giveback"`}; when `"giveback"` it also carries `"giveback_pct": float`, `"giveback_extreme": float`, `"giveback_stop": float`. Events built by older code or by tests carry no `"leg"` key at all.
- Produces: `lifecycle_embeds._giveback_line(plan, detail: dict) -> str | None` — e.g. `"5% give-back from the low of 49.94: stop 52.44"` (`high` for bullish, `low` for bearish; pct via `f"{pct:g}%"`, prices `:.2f`). `_closed_fields` adds a field named `"Give-back"`, `inline=False`, only when the helper returns a line.

**Why the leg, not config or the plan:** the percent can be changed by a
SIGHUP between the close and a later re-render, and `plan.working_stop` is
the stop *held* at close, which a structure step could in principle have
set. The leg records the exact inputs of the level that fired, so the line
is always the one that closed the runner. The reason string and
`CLOSE_REASON_STYLES` are untouched (`tp1_runner_trail` stays "trail locked
profit").

- [ ] **Step 1: Write the failing embed tests**

Create `tests/scanning/test_giveback_embed.py`:

```python
"""v176: a give-back close names the level and the best price it came from."""
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.scanning.embeds import build_plan_event_embed
from swingbot.core.scanning.lifecycle_embeds import _giveback_line
from tests.planning.test_plan_engine_model import _plan

RKLB = dict(ticker="RKLB", direction="bearish", entry_price=63.0, stop_loss=66.0,
            tp1=57.165, tp2=None)
LONG = dict(direction="bullish", entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None)


def _giveback_leg(pct=5.0, extreme=49.94, stop=52.437):
    return {"fraction": 0.5, "exit_price": 52.60, "r": 3.47, "reason": "tp1_runner_trail",
            "stop_source": "giveback", "giveback_pct": pct,
            "giveback_extreme": extreme, "giveback_stop": stop}


def _closed(detail, **plan_kw):
    return build_plan_event_embed(_plan(**plan_kw), PlanEvent("p1", "closed", detail))


def _field(embed, name):
    return next((f for f in embed.fields if f.name == name), None)


def test_short_giveback_line_matches_the_spec_example():
    line = _giveback_line(_plan(**RKLB), {"leg": _giveback_leg()})
    assert line == "5% give-back from the low of 49.94: stop 52.44"


def test_long_giveback_line_says_high():
    leg = _giveback_leg(pct=5.0, extreme=120.0, stop=114.0)
    assert _giveback_line(_plan(**LONG), {"leg": leg}) == (
        "5% give-back from the high of 120.00: stop 114.00")


def test_fractional_percent_is_kept():
    leg = _giveback_leg(pct=7.5, extreme=120.0, stop=111.0)
    assert _giveback_line(_plan(**LONG), {"leg": leg}).startswith("7.5% give-back")


def test_no_line_for_a_trail_or_floor_close():
    for source in ("trail", "floor"):
        leg = {"reason": "tp1_runner_trail", "stop_source": source}
        assert _giveback_line(_plan(**LONG), {"leg": leg}) is None


def test_no_line_without_a_leg_or_a_stop_source():
    assert _giveback_line(_plan(**LONG), {}) is None
    assert _giveback_line(_plan(**LONG), {"leg": None}) is None
    assert _giveback_line(_plan(**LONG), {"leg": {"reason": "tp1_runner_trail"}}) is None


def test_no_line_when_a_giveback_leg_lacks_its_inputs():
    leg = {"reason": "tp1_runner_trail", "stop_source": "giveback"}
    assert _giveback_line(_plan(**LONG), {"leg": leg}) is None


def test_closed_embed_adds_the_giveback_field():
    e = _closed({"reason": "tp1_runner_trail", "exit_price": 52.60,
                 "leg": _giveback_leg()}, **RKLB)
    field = _field(e, "Give-back")
    assert field is not None
    assert field.value == "5% give-back from the low of 49.94: stop 52.44"
    assert field.inline is False
    assert _field(e, "Exit").value == "52.60"         # the existing field is kept


def test_closed_embed_has_no_giveback_field_for_a_trail_close():
    e = _closed({"reason": "tp1_runner_trail", "exit_price": 114.9,
                 "leg": {"reason": "tp1_runner_trail", "stop_source": "trail"}}, **LONG)
    assert _field(e, "Give-back") is None


def test_closed_embed_without_a_leg_is_unchanged():
    e = _closed({"reason": "loss", "exit_price": 94.0}, **LONG)
    assert _field(e, "Give-back") is None
    assert [f.name for f in e.fields] == ["Plan (v2)", "Exit"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_giveback_embed.py`
Expected: FAIL at collection — `ImportError: cannot import name '_giveback_line' from 'swingbot.core.scanning.lifecycle_embeds'`.

- [ ] **Step 3: Add the helper and the field**

In `swingbot/core/scanning/lifecycle_embeds.py`, replace

```python
def _closed_fields(embed, plan, d) -> None:
    exit_price = d.get("exit_price")
    embed.description = plan_result_block(plan, exit_price, total_r(plan, exit_price))
    embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")
```

with

```python
def _giveback_line(plan, detail: dict) -> str | None:
    """v176: one line naming the give-back level that closed the runner, from
    the closing leg's own record; None for every other close."""
    leg = detail.get("leg") or {}
    if leg.get("stop_source") != "giveback":
        return None
    pct, extreme, stop = (leg.get("giveback_pct"), leg.get("giveback_extreme"),
                          leg.get("giveback_stop"))
    if pct is None or extreme is None or stop is None:
        return None
    side = "high" if plan.direction == "bullish" else "low"
    return f"{pct:g}% give-back from the {side} of {extreme:.2f}: stop {stop:.2f}"


def _closed_fields(embed, plan, d) -> None:
    exit_price = d.get("exit_price")
    embed.description = plan_result_block(plan, exit_price, total_r(plan, exit_price))
    embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")
    giveback = _giveback_line(plan, d)
    if giveback:
        embed.add_field(name="Give-back", value=giveback, inline=False)
```

- [ ] **Step 4: Run the new tests and the embed neighbours**

Run: `python scripts/dev/testrun.py file tests/scanning/test_giveback_embed.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: PASS (closed events there carry no `leg`, so no new field appears).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_giveback_line` C=5, `_closed_fields` C=2).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_giveback_embed.py
git commit -m "feat(v176): close embed names the give-back level and its best price"
```

