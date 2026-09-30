# v114 Part 1 — Build: integrity, shared admission band, instrument

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. The header, Global Constraints and Parallelisation in `2026-09-30-v114-scenario-stop-band_0-index.md` bind every task here.

**Spec:** `docs/superpowers/specs/implemented/2026-09-30-v114-scenario-stop-band-design.md`

---

# Phase A — Integrity and the shared admission band

### Task V114-01: Worktree and symbol inventory

**Files:**
- Create: `docs/superpowers/results/2026-09-30-v114-preregistration.md` (on `main`; this task writes §1 only)

**Interfaces:**
- Consumes: nothing.
- Produces: worktree `.claude/worktrees/2026-09-30-v114-scenario-stop-band/` on branch `2026-09-30-v114-scenario-stop-band`, and the §1 inventory table that V114-02 … V114-05 edit against.

- [ ] **Step 1: Create the worktree.** Load the `worktree-lifecycle` skill and create worktree + branch `2026-09-30-v114-scenario-stop-band` from `main`. All code tasks (V114-02 … V114-08) run inside it.

- [ ] **Step 2: Re-verify every symbol this plan names.** From the worktree root, run each command below and check that the output matches the Expected column. If any line differs (moved, renamed, value changed), stop and report it. Do not guess.

```bash
git grep -n "HARD_MAX_PLANNED_LOSS_PCT = 2.0" swingbot/core/risk_limits.py
git grep -n "def capped_planned_loss_pct\|def planned_loss_pct" swingbot/core/risk_limits.py
git grep -n "def stop_ceiling\|def plan_stop_ceiling" swingbot/core/planning/stop_scope.py
git grep -n "def attach_plan_v2\|def _scan_one\|def _reject_plan\|effective_max_stop = max" swingbot/core/scanning/analyze.py
git grep -n "def scenario_gate_inputs\|def passes_confluence" swingbot/core/scanning/gating.py
git grep -n "CONFLUENCE_GATES = {\|\"min_stop_distance_pct\": 2.0\|def replay_scenarios" swingbot/core/backtesting/backtest_scenarios.py
git grep -n "min_stop_distance_pct=0.0" swingbot/core/backtesting/armed_replay.py
git grep -n "def _hard_filters_snapshot" swingbot/core/scanning/scan_run.py
git grep -n "\"MIN_STOP_DISTANCE_PCT\": Reach\|\"MAX_STOP_LOSS_PCT\": Reach" swingbot/core/backtesting/arms/reachability.py
git grep -n "needs {config.MIN_STOP_DISTANCE_PCT\|needs ≤{config.MAX_STOP_LOSS_PCT" swingbot/core/scanning/requirements.py
git grep -n "Field(\"MIN_STOP_DISTANCE_PCT\"" -A 1 swingbot/config.py
git grep -n "max_stop = max(config.MAX_STOP_LOSS_PCT\|ms = max(config.MAX_STOP_LOSS_PCT" scripts/dev/
git grep -n "def _clause_win_rate_floor\|WIN_RATE_FLOOR_PP = " swingbot/core/backtesting/acceptance_harvest.py
git grep -n "NON_INFERIORITY_R = \|GEOMETRY_MAX_DROP_PCT = \|def _clause_profit_floor\|def _clause_geometry\|def arm_trade_from_plan" swingbot/core/backtesting/acceptance.py
git grep -n "GATE_MIN_N_PER_FOLD = \|GATE_MIN_IMPROVING_FOLDS = " swingbot/core/backtesting/backtest_wf.py
git grep -n "\"Bull Trap\": {\"directions\": ()}" swingbot/core/market/strategy_types.py
python -m radon cc -s swingbot/core/scanning/analyze.py | grep -E "_scan_one|attach_plan_v2"
```

| Command subject | Expected |
|---|---|
| cap constant | `risk_limits.py:9` `HARD_MAX_PLANNED_LOSS_PCT = 2.0` |
| cap helpers | `capped_planned_loss_pct` (l.12), `planned_loss_pct` (l.17) |
| stop scope | `stop_ceiling` (l.34), `plan_stop_ceiling` (l.47) |
| analyze | `_reject_plan` (~121), `attach_plan_v2` (~347), `_scan_one` (~539), `effective_max_stop = max(` (~774) |
| gating | `scenario_gate_inputs`, `passes_confluence` |
| replay | `CONFLUENCE_GATES` with `"min_stop_distance_pct": 2.0` (~l.53), `replay_scenarios` |
| armed replay | one hit, `arm_candidates` passes `min_stop_distance_pct=0.0` |
| hard-filter snapshot | `_hard_filters_snapshot` in `scan_run.py` (~l.172) |
| reachability | both entries `REACHABLE`, confluence-observed |
| requirement text | two f-strings reading `config.MIN_STOP_DISTANCE_PCT` / `config.MAX_STOP_LOSS_PCT` |
| config field | `default="2.0"` for `MIN_STOP_DISTANCE_PCT` |
| dev scripts | `diagnose_funnel.py:92` and `diagnose_funnel2.py:64` copy the inline formula |
| harvest floor | `_clause_win_rate_floor`, `WIN_RATE_FLOOR_PP = -2.0` |
| v72 clauses | `NON_INFERIORITY_R = -0.01`, `GEOMETRY_MAX_DROP_PCT = 2.0`, both clause functions, `arm_trade_from_plan` |
| wf fold rules | `GATE_MIN_N_PER_FOLD = 30`, `GATE_MIN_IMPROVING_FOLDS = 2` |
| shorts masked | `"Bull Trap": {"directions": ()}` (and the other two `SHORT_STRATEGIES`) |
| complexity | `_scan_one - E (39)`, `attach_plan_v2 - B (7)` |

- [ ] **Step 3: Write §1 of the pre-registration document on `main`.** In the main tree (not the worktree), create `docs/superpowers/results/2026-09-30-v114-preregistration.md` with this exact content:

````markdown
# v114 pre-registration — scenario stop floor 2.0% -> 1.5%

**Spec:** `docs/superpowers/specs/implemented/2026-09-30-v114-scenario-stop-band-design.md`
**Plan:** `docs/superpowers/plans/implemented/2026-09-30-v114-scenario-stop-band_0-index.md`
**Status:** §1 written (V114-01). §2-§7 are written by V114-09 **before any run**.

## 1. Code inventory (verified by `git grep`, V114-01)

| Where | Today | After v114 |
|---|---|---|
| `swingbot/core/risk_limits.py` `HARD_MAX_PLANNED_LOSS_PCT` | 2.0 | unchanged (single source of the cap) |
| `analyze._scan_one` admission ceiling | `max(MAX_STOP_LOSS_PCT, h["max_risk_pct"])` = 7-11% | `gating.admission_gates` -> the cap (V114-03) |
| `gating.scenario_gate_inputs` (replay, armed replay) | same 7-11% formula | delegates to `admission_gates` (V114-03) |
| `analyze.attach_plan_v2` `risk_cap` reject | backstop at the cap | unchanged; tested per horizon x direction (V114-02) |
| `stop_scope.stop_ceiling` / `plan_stop_ceiling` | cap for every live strategy; horizon max for the masked `SHORT_STRATEGIES` | unchanged; tested (V114-02) |
| `config` `MIN_STOP_DISTANCE_PCT` default | 2.0 | 1.5 (V114-05) |
| `backtest_scenarios.CONFLUENCE_GATES["min_stop_distance_pct"]` | 2.0 | 1.5 (V114-05) |
| `scan_params.ScanParams.from_config` | reads config | unchanged (follows the default) |
| `scan_run._hard_filters_snapshot` | reads `ScanParams` | unchanged |
| `armed_replay.arm_candidates` floor | 0.0 at arm time | unchanged |
| `arms/reachability.py` `MAX_STOP_LOSS_PCT` | REACHABLE (admission) | OUTSIDE_REPLAY (V114-04) |
| `requirements._build_requirement_checks` stop text | "needs X%+" / "needs ≤7.0%" | states the 1.5-2.0% band (V114-04) |
| `scripts/dev/diagnose_funnel.py`, `diagnose_funnel2.py` | copy the inline formula | call `gating.admission_gates` (V114-03) |
| `scripts/backtest/measure_dcb_veto.py`, `tune_confluence_gates.py` `BASE_GATES` | 2.0 floor | **untouched** — instruments of closed pre-registrations |
| production `.env` | `MIN_STOP_DISTANCE_PCT=2.0` set explicitly | 1.5 only on a PASS (V114-15) |
| `.env.example` | `MIN_STOP_DISTANCE_PCT=2.0` | 1.5 only on a PASS (V114-14) |
| `docs/strategy/strategy-plans.md:41` | "default **2%**" | 1.5% only on a PASS (V114-14) |
````

- [ ] **Step 4: Commit on `main`.**

```bash
git add docs/superpowers/results/2026-09-30-v114-preregistration.md
git commit -m "docs(v114): pre-registration §1 -- code inventory

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-02: Cap integrity tests — no plan above 2.0%, every horizon, both directions

These tests describe backstops that already hold today, so they pass as soon as they are written. They are written first so that V114-03's admission change cannot loosen any of them.

**Files:**
- Create: `tests/planning/test_v114_cap_integrity.py`

**Interfaces:**
- Consumes: `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, `capped_planned_loss_pct`; `stop_scope.stop_ceiling(strategy, direction, horizon_key, raw=None) -> (float, str)`, `stop_scope.plan_stop_ceiling(plan) -> float`, `stop_scope.CAP`; `analyze.attach_plan_v2(item, scenario, df, ticker, horizon_key, level_map=None, ...)`; `backtest.ALL_STRATEGIES`; `strategy_types.HORIZONS`, `SHORT_STRATEGIES`, `STRATEGY_GATES`; test helpers `tests.helpers.make_ohlcv`, `tests.scanning.test_engine_v2_plans._item`, `_scenario`.
- Produces: the integrity guard later tasks must keep green.

- [ ] **Step 1: Write the tests.**

```python
"""v114 integrity requirement: no plan is issued above the 2.0% planned-loss
cap, for any horizon or direction (spec § Integrity requirement).

Not subject to validation. These pin the backstops that already hold, so the
admission change (V114-03) cannot loosen them.
"""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES, STRATEGY_GATES
from swingbot.core.planning import stop_scope as ss
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct
from swingbot.core.scanning import analyze, engine
from tests.helpers import make_ohlcv
from tests.scanning.test_engine_v2_plans import _item, _scenario

DIRECTIONS = ("bullish", "bearish")
HORIZON_KEYS = sorted(HORIZONS)


def test_the_cap_is_two_percent():
    assert HARD_MAX_PLANNED_LOSS_PCT == 2.0


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_live_strategy_ceiling_is_the_cap(horizon_key, direction):
    for strategy in ALL_STRATEGIES:
        ceiling, mode = ss.stop_ceiling(strategy, direction, horizon_key, raw="")
        assert ceiling <= HARD_MAX_PLANNED_LOSS_PCT + 1e-9, (strategy, direction, horizon_key)
        assert mode == ss.CAP, (strategy, direction, horizon_key)


def test_short_strategies_keep_a_wider_ceiling_only_while_masked():
    """stop_scope keeps SHORT_STRATEGIES always in scope (v104 Part B), so
    their ceiling is the horizon's max_risk_pct. That is safe only while every
    one of them is masked out of the live stream. Unmasking one must fail
    here and force the cap question to be asked again."""
    for name in SHORT_STRATEGIES:
        assert STRATEGY_GATES[name]["directions"] == (), name


def test_structural_stop_scope_stays_empty():
    assert config.STRUCTURAL_STOP_SCOPE == ""


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_confluence_plan_ceiling_is_the_cap(horizon_key, direction):
    plan = SimpleNamespace(source="confluence", strategy="Support/Resistance",
                           direction=direction, horizon_key=horizon_key)
    assert ss.plan_stop_ceiling(plan) == HARD_MAX_PLANNED_LOSS_PCT


@pytest.mark.parametrize("configured", [0.5, 1.5, 2.0, 7.0, 11.0])
def test_capped_planned_loss_never_exceeds_the_cap(configured):
    assert capped_planned_loss_pct(configured) <= HARD_MAX_PLANNED_LOSS_PCT


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("stop", [97.99, 102.01])   # 2.01% below / above a 100.0 entry
def test_attach_plan_v2_rejects_a_plan_just_over_the_cap(monkeypatch, horizon_key, stop):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    over = SimpleNamespace(trigger_price=100.0, stop_loss=stop)
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: over)
    item = _item()
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60), "AAPL",
                          horizon_key, level_map=None)
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "risk_cap"
```

- [ ] **Step 2: Run the tests.**

Run: `python scripts/dev/testrun.py file tests/planning/test_v114_cap_integrity.py`
Expected: PASS. Every test here describes behaviour that already exists. If one fails, stop: the failure is an integrity finding for the partner, not something to adjust the test around.

- [ ] **Step 3: Commit (on the branch).**

```bash
git add tests/planning/test_v114_cap_integrity.py
git commit -m "test(v114): no plan above the 2% cap, every horizon and direction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-03: One admission function for scan and replay; ceiling = the cap

**Files:**
- Modify: `swingbot/core/scanning/gating.py` (whole file, 15 lines)
- Modify: `swingbot/core/scanning/analyze.py` (~743-779: the comment block and the two inline bounds in `_scan_one`; add `_admission_gates` near `_reject_plan`; the `risk_cap` comment at ~375-381)
- Modify: `scripts/dev/diagnose_funnel.py:91-94`, `scripts/dev/diagnose_funnel2.py:63-65`
- Modify: `tests/scanning/test_gating.py`
- Create: `tests/scanning/test_v114_admission_parity.py`
- Modify (only if they fail after the change, see Step 6): `tests/scanning/test_engine_v2_plans.py`, `tests/scanning/test_engine_quality_inputs.py`, `tests/scanning/test_mtf_gate.py`, `tests/scanning/test_rs_gate_wiring.py`

**Interfaces:**
- Consumes: `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, `planned_loss_pct`; `ScanParams`; `scan_run._hard_filters_snapshot(params) -> dict`; `backtest_scenarios.replay_scenarios(ticker, df, horizon_key, *, params=...) -> list[(int, TradePlanV2)]`; `tests.backtesting.test_v74_fixture.load_v74_fixture`.
- Produces: `gating.admission_gates(min_reward_pct: float, min_stop_distance_pct: float, min_risk_reward: float, horizon: dict) -> dict` with keys `min_reward_pct`, `min_stop_distance_pct`, `max_stop_distance_pct`, `min_risk_reward`; `gating.scenario_gate_inputs(params, horizon)` now delegates to it; `analyze._admission_gates(hard_filters: dict, h: dict) -> dict`.

- [ ] **Step 1: Write the failing parity tests.** Create `tests/scanning/test_v114_admission_parity.py`:

```python
"""v114 Design §2-3: the scenario admission ceiling is the planned-loss cap,
and the live scan and replay admit through one function."""
import dataclasses
import inspect

import pytest

from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.core.scanning import analyze, gating
from swingbot.core.scanning.scan_run import _hard_filters_snapshot
from swingbot.scan_params import ScanParams
from tests.backtesting.test_v74_fixture import load_v74_fixture

GATE_VALUES = [
    # production today
    dict(min_reward_pct=2.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0, min_risk_reward_ratio=1.5),
    # the v114 candidate
    dict(min_reward_pct=2.0, min_stop_distance_pct=1.5, max_stop_loss_pct=7.0, min_risk_reward_ratio=1.5),
    # an arbitrary off-default point, so equality is not a coincidence of defaults
    dict(min_reward_pct=3.0, min_stop_distance_pct=0.5, max_stop_loss_pct=11.0, min_risk_reward_ratio=2.5),
]
HORIZON_KEYS = sorted(HORIZONS)


def _params(values):
    return dataclasses.replace(ScanParams.from_config(), **values)


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("values", GATE_VALUES)
def test_admission_ceiling_is_the_cap(horizon_key, values):
    gates = gating.scenario_gate_inputs(_params(values), HORIZONS[horizon_key])
    assert gates["max_stop_distance_pct"] == HARD_MAX_PLANNED_LOSS_PCT


@pytest.mark.parametrize("horizon_key", HORIZON_KEYS)
@pytest.mark.parametrize("values", GATE_VALUES)
def test_live_and_replay_admission_gates_are_identical(horizon_key, values):
    params = _params(values)
    live = analyze._admission_gates(_hard_filters_snapshot(params), HORIZONS[horizon_key])
    replay = gating.scenario_gate_inputs(params, HORIZONS[horizon_key])
    assert live == replay


def test_scan_one_admits_through_the_shared_gates():
    source = inspect.getsource(analyze._scan_one)
    assert "_admission_gates(hard_filters, h)" in source
    assert "max_risk_pct" not in source


def test_replayed_plans_never_exceed_the_cap():
    frame = load_v74_fixture()["AAPL"]
    params = _params(dict(min_reward_pct=1.0, min_stop_distance_pct=0.0,
                          max_stop_loss_pct=11.0, min_risk_reward_ratio=1.5))
    plans = replay_scenarios("AAPL", frame, "4w", params=params)
    assert plans, "fixture should still yield confluence plans inside the cap"
    assert all(planned_loss_pct(plan.trigger_price, plan.stop_loss)
               <= HARD_MAX_PLANNED_LOSS_PCT + 1e-9 for _, plan in plans)
```

- [ ] **Step 2: Run the new tests and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v114_admission_parity.py`
Expected: FAIL. `test_admission_ceiling_is_the_cap` fails with 7.0-11.0 != 2.0. `_admission_gates` fails with AttributeError. The source test fails. `test_replayed_plans_never_exceed_the_cap` fails with a plan above 2%. If the replay test passes because `plans` is empty, change `"4w"` to the first horizon in `("4w", "2w", "2m")` that yields plans, and record which one was used in the commit message.

- [ ] **Step 3: Replace `swingbot/core/scanning/gating.py` with:**

```python
"""Shared confluence gate arithmetic for live scans and historical replay."""
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT
from swingbot.scan_params import ScanParams

#: Share of a horizon's sr_target_min_pct that the reward floor demands.
HORIZON_REWARD_SHARE = 0.15


def admission_gates(min_reward_pct: float, min_stop_distance_pct: float,
                    min_risk_reward: float, horizon: dict) -> dict:
    """The levels.build_scenarios admission bounds, for the live scan
    (analyze._scan_one) and every replay path alike.

    The reward floor scales with the horizon. The stop ceiling is the
    planned-loss cap, not the horizon's max_risk_pct (v114): attach_plan_v2
    rejects any plan beyond the cap (`risk_cap`), so admitting such a scenario
    only built candidates that could never trade.
    """
    return {
        "min_reward_pct": max(min_reward_pct,
                              horizon.get("sr_target_min_pct", 0) * HORIZON_REWARD_SHARE),
        "min_stop_distance_pct": min_stop_distance_pct,
        "max_stop_distance_pct": HARD_MAX_PLANNED_LOSS_PCT,
        "min_risk_reward": min_risk_reward,
    }


def scenario_gate_inputs(params: ScanParams, horizon: dict) -> dict:
    return admission_gates(params.min_reward_pct, params.min_stop_distance_pct,
                           params.min_risk_reward_ratio, horizon)


def passes_confluence(n_confluent: int, params: ScanParams) -> bool:
    return n_confluent >= params.min_target_confluence_count
```

The reward term matches both old formulas byte for byte. Live used `max(x, h.get(k, x) * 0.15)` and replay used `max(x, h.get(k, 0) * 0.15)`. Both reduce to `x` when the key is missing and are identical when it is present.

- [ ] **Step 4: Wire `analyze._scan_one` through it.** In `swingbot/core/scanning/analyze.py`:

(a) Add the import next to the other scanning imports (after `from .confidence import score_confidence`):

```python
from .gating import admission_gates
```

(b) Add this helper directly after `_reject_plan`:

```python
def _admission_gates(hard_filters: dict, h: dict) -> dict:
    """build_scenarios bounds from the per-scan hard-filter snapshot, through
    the same function replay uses (gating.admission_gates), so scan and
    replay admit identical candidates (v114)."""
    return admission_gates(hard_filters["min_reward_pct"],
                           hard_filters["min_stop_distance_pct"],
                           hard_filters["min_risk_reward_ratio"], h)
```

(c) In `_scan_one`, replace the comment block that begins `# Reward/stop bounds are widened toward this horizon's OWN scale` and ends at `# continue to evaluate the same candidates.`, together with the two `effective_*` lines and the `levels.build_scenarios(...)` call, with:

```python
        # Admission bounds come from gating.admission_gates, the same function
        # historical replay calls, so scan and replay admit the same
        # candidates. The reward floor still scales with the horizon (15% of
        # its sr_target_min_pct). The stop ceiling is the planned-loss cap
        # (v114): a stop beyond it is rejected at issue anyway (risk_cap).
        gates = _admission_gates(hard_filters, h)
        scenarios = levels.build_scenarios(current_price, supports, resistances, gates["min_reward_pct"],
                                            atr_floor=floor_pct, min_stop_distance_pct=gates["min_stop_distance_pct"],
                                            max_stop_distance_pct=gates["max_stop_distance_pct"],
                                            min_risk_reward=gates["min_risk_reward"],
                                            block_bullish=veto_bullish_for(df))
```

Check first that no later line in `_scan_one` reads `effective_min_reward` or `effective_max_stop`: `grep -n "effective_min_reward\|effective_max_stop" swingbot/core/scanning/analyze.py` must print nothing after the edit.

(d) In `attach_plan_v2`, replace the six-line comment under `if planned_loss_pct(...) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9:` with:

```python
            # Backstop. Admission is already capped at the same constant
            # (gating.admission_gates, v114), so a confluence plan should
            # never reach this; it stays so that no plan past the 2% cap can
            # be posted, whichever builder produced it.
```

- [ ] **Step 5: Point the two dev funnel scripts at the shared function.** In `scripts/dev/diagnose_funnel.py`, replace lines 91-94 (`min_reward = …` through `min_rr = …`) with:

```python
            gates = admission_gates(config.MIN_REWARD_PCT, config.MIN_STOP_DISTANCE_PCT,
                                    config.MIN_RISK_REWARD_RATIO, h)
            min_reward, max_stop = gates["min_reward_pct"], gates["max_stop_distance_pct"]
            min_stop, min_rr = gates["min_stop_distance_pct"], gates["min_risk_reward"]
```

In `scripts/dev/diagnose_funnel2.py`, replace lines 63-65 (`mr = …` through `mn, rr_min = …`) with:

```python
            gates = admission_gates(config.MIN_REWARD_PCT, config.MIN_STOP_DISTANCE_PCT,
                                    config.MIN_RISK_REWARD_RATIO, h)
            mr, ms = gates["min_reward_pct"], gates["max_stop_distance_pct"]
            mn, rr_min = gates["min_stop_distance_pct"], gates["min_risk_reward"]
```

Add `from swingbot.core.scanning.gating import admission_gates` to each script's import block, beside its existing `swingbot` imports.

- [ ] **Step 6: Update `tests/scanning/test_gating.py`.** Replace `test_gate_inputs_use_the_larger_horizon_bounds` with:

```python
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT


def test_gate_inputs_scale_the_reward_floor_but_cap_the_stop():
    params = dataclasses.replace(ScanParams.from_config(), min_reward_pct=3.0, max_stop_loss_pct=7.0)
    got = scenario_gate_inputs(params, HORIZON)
    assert got["min_reward_pct"] == 3.0                       # max(3.0, 8.0 * 0.15)
    assert got["max_stop_distance_pct"] == HARD_MAX_PLANNED_LOSS_PCT   # not the horizon's 9.0
```

(Put the new import with the file's other imports.)

- [ ] **Step 7: Run the touched files, then the fast tier.**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v114_admission_parity.py`, then `... file tests/scanning/test_gating.py`, then `... file tests/planning/test_v114_cap_integrity.py`.
Expected: PASS.

Run: `python scripts/dev/testrun.py fast` (the change reaches every scan and replay test).
Expected: `0 failed`. The likely failures are scan tests that loosen admission with `monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)` so they can build wide-stop scenarios: `tests/scanning/test_engine_v2_plans.py` (l.240, 357, 517, 605), `test_engine_quality_inputs.py:57`, `test_mtf_gate.py:88`, `test_rs_gate_wiring.py:77`. That setting no longer loosens admission. For each of those tests that fails, add the equivalent loosening beside the existing line, keeping the test's intent, which is to admit wide stops in a unit fixture:

```python
    monkeypatch.setattr(gating, "HARD_MAX_PLANNED_LOSS_PCT", 50.0)   # v114: admission reads the cap
```

(use `mp.setattr` where the file uses `mp`, and add `from swingbot.core.scanning import gating` to that file). Patch only the tests that actually fail. If any other test fails, stop and diagnose (`superpowers:systematic-debugging`). Do not edit a golden value to make it pass.

- [ ] **Step 8: Complexity.**

Run: `python -m radon cc -s swingbot/core/scanning/gating.py swingbot/core/scanning/analyze.py | grep -E "admission_gates|scenario_gate_inputs|_admission_gates|_scan_one"`
Expected: new functions A. `_scan_one` scores E (39) or lower, never higher.

- [ ] **Step 9: Commit (two commits).**

```bash
git add swingbot/core/scanning/gating.py swingbot/core/scanning/analyze.py tests/scanning/test_gating.py tests/scanning/test_v114_admission_parity.py
git add -u tests/scanning/        # only the files Step 7 had to patch
git commit -m "fix(v114): scenario admission ceiling is the 2% cap, one function for scan and replay

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add scripts/dev/diagnose_funnel.py scripts/dev/diagnose_funnel2.py
git commit -m "chore(v114): funnel diagnostics read gating.admission_gates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-04: Reachability and requirement text follow the band

**Files:**
- Modify: `swingbot/core/backtesting/arms/reachability.py:40`
- Modify: `swingbot/core/scanning/requirements.py` (the `min_stop_distance` and `max_stop_distance` `RequirementCheck`s, ~l.49-56; one import)
- Create: `tests/scanning/test_v114_requirement_band.py`

**Interfaces:**
- Consumes: V114-03 (admission no longer reads `MAX_STOP_LOSS_PCT`); `tests.scanning.test_opex_gates._checks(conf_level, min_confluence, min_confidence, ...)` (its `_Scenario` has `stop_distance_pct = 2.0`).
- Produces: `REGISTRY["MAX_STOP_LOSS_PCT"].cls == OUTSIDE_REPLAY`; stop-check detail text `"<d>% away (band <floor>-<cap>%)"`.

- [ ] **Step 1: Write the failing tests.**

```python
"""v114 Design §3-4: the requirement table states the 1.5-2.0% band, and the
reachability registry no longer claims MAX_STOP_LOSS_PCT moves replay."""
from swingbot import config
from swingbot.core.backtesting.arms import reachability as r
from tests.scanning.test_opex_gates import _checks


def _detail(checks, key):
    return next(c.detail for c in checks if c.key == key)


def test_stop_checks_state_the_band(monkeypatch):
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.5)
    checks = _checks(4, 2, 4)
    assert _detail(checks, "min_stop_distance") == "2.0% away (band 1.5-2.0%)"
    assert _detail(checks, "max_stop_distance") == "2.0% away (band 1.5-2.0%)"


def test_the_band_ceiling_ignores_max_stop_loss_pct(monkeypatch):
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.5)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 7.0)     # production's explicit value
    assert _detail(_checks(4, 2, 4), "max_stop_distance").endswith("(band 1.5-2.0%)")


def test_max_stop_loss_pct_is_outside_replay():
    assert r.classify("MAX_STOP_LOSS_PCT") == r.OUTSIDE_REPLAY
    assert "HARD_MAX_PLANNED_LOSS_PCT" in r.reason("MAX_STOP_LOSS_PCT")


def test_min_stop_distance_stays_reachable():
    assert r.classify("MIN_STOP_DISTANCE_PCT") == r.REACHABLE
```

- [ ] **Step 2: Run and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v114_requirement_band.py`
Expected: FAIL on the band text ("needs 1.5%+" / "needs ≤7.0%") and on `OUTSIDE_REPLAY`. `test_min_stop_distance_stays_reachable` passes.

- [ ] **Step 3: Implement.** In `requirements.py`, add `from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT` after `from swingbot import config`, and replace the two stop checks with:

```python
        RequirementCheck(
            key="min_stop_distance", label="Min stop distance %", passed=c.get("min_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (band {config.MIN_STOP_DISTANCE_PCT:.1f}-{HARD_MAX_PLANNED_LOSS_PCT:.1f}%)",
        ),
        RequirementCheck(
            key="max_stop_distance", label="Max stop-loss %", passed=c.get("max_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (band {config.MIN_STOP_DISTANCE_PCT:.1f}-{HARD_MAX_PLANNED_LOSS_PCT:.1f}%)",
        ),
```

In `reachability.py`, replace the `"MAX_STOP_LOSS_PCT"` entry with:

```python
    "MAX_STOP_LOSS_PCT": _outside("v114: scenario admission reads HARD_MAX_PLANNED_LOSS_PCT (gating.admission_gates), so this setting no longer moves replay."),
```

- [ ] **Step 4: Run the touched tests.**

Run: `python scripts/dev/testrun.py file tests/scanning/test_v114_requirement_band.py`, then `... file tests/backtesting/arms/test_reachability.py`, `... file tests/backtesting/test_knob_observability.py`, `... file tests/scanning/test_opex_gates.py`.
Expected: PASS. If some other test pins the old "needs …" text, find it with `git grep -n "needs ≤\|% away (needs" tests` and update it to the band text. The strings are display text, and this change is the point of the task.

- [ ] **Step 5: Complexity.** `python -m radon cc -s -n C swingbot/core/scanning/requirements.py` must show no block you touched at 15 or above. `_build_requirement_checks` should not change score, since f-strings add no branches.

- [ ] **Step 6: Commit (two commits).**

```bash
git add swingbot/core/scanning/requirements.py tests/scanning/test_v114_requirement_band.py
git commit -m "feat(v114): requirement table states the stop band

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add swingbot/core/backtesting/arms/reachability.py
git commit -m "fix(v114): MAX_STOP_LOSS_PCT no longer moves replay admission -- reclassify

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`test_v114_requirement_band.py` goes in with the first commit, and its reachability test starts passing with the second. Both commits are on the branch, and the branch is only checked once Step 4 is green.)

### Task V114-05: Floor default 2.0 -> 1.5, config and replay together

This task is the default flip. It lives only on the branch, and the branch reaches `main` only on a PASS (V114-14). A NO-LIFT leaves this commit unmerged (V114-13).

**Files:**
- Modify: `swingbot/config.py` (`Field("MIN_STOP_DISTANCE_PCT", …)`, ~l.154-157)
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`CONFLUENCE_GATES`, ~l.44-54)
- Create: `tests/backtesting/test_v114_band_defaults.py`

**Interfaces:**
- Consumes: `config.FIELDS`; `backtest_scenarios.CONFLUENCE_GATES`; `gating.scenario_gate_inputs` (V114-03).
- Produces: the default `MIN_STOP_DISTANCE_PCT = 1.5` wherever no `.env` value overrides it, and `CONFLUENCE_GATES["min_stop_distance_pct"] == 1.5`.

- [ ] **Step 1: Write the failing tests.**

```python
"""v114 Design §1 and §3: the stop floor default moves to 1.5 in config and
in the replay defaults together, and nothing else moves."""
import dataclasses

from swingbot import config
from swingbot.core.backtesting.backtest_scenarios import CONFLUENCE_GATES
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT
from swingbot.core.scanning.gating import scenario_gate_inputs
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.scan_params import ScanParams


def _default(attr):
    return float(next(f for f in config.FIELDS if f.attr == attr).default)


def test_the_floor_default_is_one_and_a_half():
    assert _default("MIN_STOP_DISTANCE_PCT") == 1.5


def test_replay_defaults_move_in_lockstep_with_config():
    assert CONFLUENCE_GATES["min_stop_distance_pct"] == _default("MIN_STOP_DISTANCE_PCT")


def test_the_other_band_settings_do_not_move():
    assert _default("MIN_RISK_REWARD_RATIO") == 1.5
    assert _default("MAX_RISK_REWARD_RATIO") == 2.5
    assert HARD_MAX_PLANNED_LOSS_PCT == 2.0
    assert CONFLUENCE_GATES["min_risk_reward"] == 1.5


def test_the_default_band_is_one_and_a_half_to_two_on_every_horizon():
    params = dataclasses.replace(ScanParams.from_config(), min_stop_distance_pct=_default("MIN_STOP_DISTANCE_PCT"))
    for horizon in HORIZONS.values():
        gates = scenario_gate_inputs(params, horizon)
        assert (gates["min_stop_distance_pct"], gates["max_stop_distance_pct"]) == (1.5, 2.0)
```

- [ ] **Step 2: Run and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v114_band_defaults.py`
Expected: FAIL on the two 1.5 assertions (currently 2.0).

- [ ] **Step 3: Implement.** In `swingbot/config.py`, change the field to:

```python
    Field("MIN_STOP_DISTANCE_PCT", "MIN_STOP_DISTANCE_PCT", "Trade Filters & Risk", "Min stop distance %",
          type="float", default="1.5", min=0, step=0.5,
          help="Hard filter, enforced exactly as set: dropped entirely if the stop sits closer than this -- "
               "too exposed to ordinary daily noise. The band's ceiling is the 2% planned-loss cap. "
               "No exceptions for a close miss."),
```

In `backtest_scenarios.py`, set `"min_stop_distance_pct": 1.5,` in `CONFLUENCE_GATES` and add one line to the comment block above it (after `# precedent, itself never grid-validated).`):

```python
# v114: min_stop_distance_pct follows the config default (1.5) in lockstep.
```

- [ ] **Step 4: Run the touched tests, then the fast tier.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v114_band_defaults.py`, then `python scripts/dev/testrun.py fast`.
Expected: `0 failed`. A test that pins a replay result under `CONFLUENCE_GATES` (a closed pre-registration's golden, such as `test_v74_no_behaviour_change.py` or `test_acceptance_v68_regression.py`) may now fail. Fix it by passing that test its own historical gates explicitly (`dict(CONFLUENCE_GATES, min_stop_distance_pct=2.0)`), so it keeps measuring what it recorded. Never regenerate a golden. List every test adjusted this way in the commit body.

- [ ] **Step 5: Commit.**

```bash
git add swingbot/config.py swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_v114_band_defaults.py
git add -u tests/            # only goldens Step 4 had to pin to their historical gates
git commit -m "feat(v114): stop floor default 2.0 -> 1.5, config and replay in lockstep

Branch-only until the v114 validation passes.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase B — The instrument

### Task V114-06: Arm rows carry `tight_stop`

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (`ArmTrade`, `arm_trade_from_plan`)
- Modify: `swingbot/core/backtesting/arms/confluence_engine.py`
- Modify: `tests/backtesting/arms/test_confluence_engine.py` (append)

**Interfaces:**
- Consumes: `levels.atr_floor_pct(df, current_price, h) -> float`, `levels.build_level_map(df, h, price) -> (supports, resistances)`, `levels.build_scenarios(...)`, `risk_limits.planned_loss_pct`.
- Produces: `ArmTrade.tight_stop: bool | None = None`; `arm_trade_from_plan(plan, *, entry_date, outcome, r_multiple, tight_stop=None)`; `confluence_engine.tight_stop_at(window, entry: float, stop: float, horizon: dict) -> bool`. Confluence rows carry a bool, strategy rows `None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtesting/arms/test_confluence_engine.py`):

```python
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS


def test_confluence_rows_carry_a_tight_stop_flag(frame):
    trades = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert trades and all(isinstance(trade.tight_stop, bool) for trade in trades)


def test_tight_stop_at_agrees_with_build_scenarios(frame):
    """Same rule build_scenarios stamps: stop distance below the horizon's
    ATR cushion, measured on the as-of window only."""
    from swingbot.core.backtesting.arms.confluence_engine import tight_stop_at
    horizon = HORIZONS["4w"]
    checked = 0
    for end in range(200, len(frame), 25):
        window = frame.iloc[:end]
        price = float(window["Close"].iloc[-1])
        supports, resistances = levels.build_level_map(window, horizon, price)
        floor = levels.atr_floor_pct(window, price, horizon)
        for scenario in levels.build_scenarios(price, supports, resistances, 0.0, atr_floor=floor):
            assert tight_stop_at(window, price, scenario.stop_loss, horizon) == scenario.tight_stop
            checked += 1
    assert checked


def test_rows_written_before_v114_still_load():
    row = {"ticker": "T", "strategy": "MACD", "horizon_key": "3m", "entry_date": "2021-01-04",
           "outcome": "win", "r_multiple": 1.5, "planned_rr": 1.5,
           "source": "confluence", "direction": "bullish"}
    assert ArmTrade(**row).tight_stop is None
```

- [ ] **Step 2: Run and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_confluence_engine.py`
Expected: FAIL. `ArmTrade` has no `tight_stop`, and `tight_stop_at` cannot be imported.

- [ ] **Step 3: Implement.** In `acceptance.py`, add the field as the last `ArmTrade` field (after `direction`), leaving `key` and `stratum` unchanged:

```python
    tight_stop: bool | None = None  # v114: stop inside the horizon's ATR cushion; confluence rows only
```

and extend `arm_trade_from_plan`:

```python
def arm_trade_from_plan(plan, *, entry_date: str, outcome: str,
                        r_multiple: float | None,
                        tight_stop: bool | None = None) -> ArmTrade:
    """Adapt a TradePlanV2 (what replay_scenarios yields) plus its outcome."""
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return ArmTrade(ticker=plan.ticker, strategy=plan.strategy,
                    horizon_key=plan.horizon_key, entry_date=entry_date,
                    outcome=outcome, r_multiple=r_multiple,
                    planned_rr=planned_rr(entry, plan.stop_loss, plan.tp1),
                    source=plan.source, direction=plan.direction,
                    tight_stop=tight_stop)
```

Replace `swingbot/core/backtesting/arms/confluence_engine.py` with:

```python
"""Confluence population: scenario replay followed by the shared exit model."""
from __future__ import annotations

from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_engine import simulate_exit
from swingbot.core.risk_limits import planned_loss_pct

SKIPPED = ("not_triggered", "no_trade")


def tight_stop_at(window, entry: float, stop: float, horizon: dict) -> bool:
    """build_scenarios' tight_stop rule, recomputed on the as-of window."""
    return planned_loss_pct(entry, stop) < levels.atr_floor_pct(window, entry, horizon)


class ConfluenceEngine:
    engine_id = "confluence"

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        """Produce closed confluence trades with signal dates in the window."""
        start, end = signal_window
        signal_df = df.loc[:end]
        out = []
        for horizon_key in horizons:
            for index, plan in replay_scenarios(ticker, signal_df, horizon_key, params=params):
                entry_date = str(df.index[index].date())
                if entry_date < start:
                    continue
                result = simulate_exit(df, index, plan, scale_out=True)
                if result.outcome in SKIPPED:
                    continue
                tight = tight_stop_at(df.iloc[:index + 1], plan.trigger_price,
                                      plan.stop_loss, HORIZONS[horizon_key])
                out.append(arm_trade_from_plan(
                    plan, entry_date=entry_date, outcome=result.outcome,
                    r_multiple=result.r_total, tight_stop=tight,
                ))
        return out
```

`df.iloc[:index + 1]` is the as-of window that `replay_scenarios` used at bar `index` (its price is `Close[index]` = `plan.trigger_price`), so no later bar is read.

- [ ] **Step 4: Run the touched tests.**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_confluence_engine.py`, then `... file tests/backtesting/test_acceptance_records.py`, `... file tests/backtesting/arms/test_pairing.py`, `... file tests/backtesting/test_validate_component_stamps.py`.
Expected: PASS.

- [ ] **Step 5: Complexity.** `python -m radon cc -s swingbot/core/backtesting/arms/confluence_engine.py` shows `run_ticker` under 15. It adds no branches.

- [ ] **Step 6: Commit.**

```bash
git add swingbot/core/backtesting/acceptance.py swingbot/core/backtesting/arms/confluence_engine.py tests/backtesting/arms/test_confluence_engine.py
git commit -m "feat(v114): confluence arm rows carry tight_stop for stratified reporting

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-07: Volume-edge gate built only from existing clauses

The spec's Validation section reads the volume clause as a floor on gain, and the win-rate and expectancy clauses as non-inferiority constraints. Thresholds come from `acceptance.py` / `acceptance_harvest.py` and are never invented. This module wires that reading together, and every threshold in it is imported.

**Files:**
- Create: `swingbot/core/backtesting/acceptance_volume.py`
- Create: `tests/backtesting/test_acceptance_volume.py`

**Interfaces:**
- Consumes: `acceptance.ArmTrade` (with `tight_stop`, V114-06), `ClauseResult`, `AcceptanceResult`, `population_split`, `stratum_table`, `_clause_profit_floor`, `_clause_geometry`, `render_markdown`, `win_rate`, `expectancy_r`, `_fmt_pct`, `_fmt_r`, `ALPHA`, `BOOTSTRAP_RESAMPLES`; `acceptance_harvest._clause_win_rate_floor`; `backtest_wf.GATE_MIN_N_PER_FOLD`, `GATE_MIN_IMPROVING_FOLDS`.
- Produces: `evaluate_volume(baseline, component, *, stage: str, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult` (clauses `volume_gain`, `win_rate_floor`, `profit_floor`, `geometry`, `not_luck`; `stage` in `STAGES = ("train", "walkforward", "validation")`); `walkforward_verdict(folds: list[dict]) -> str` (each fold dict has `test_year`, `verdict`, `n`); `tight_stop_table(baseline, component) -> list[dict]`; `render_volume_markdown(result, baseline, component, *, title, window, notes=None) -> str`; `render_walkforward_markdown(rows, *, title, window, verdict) -> str`; `VOLUME_VERSION = 1`.

- [ ] **Step 1: Write the failing tests.**

```python
import pytest

from swingbot.core.backtesting import acceptance_volume as av
from swingbot.core.backtesting.acceptance import ArmTrade


def _t(ticker, i, win, tight=False, rr=2.0):
    return ArmTrade(ticker=ticker, strategy="Support/Resistance", horizon_key="4w",
                    entry_date=f"2021-01-{i + 1:02d}", outcome="win" if win else "loss",
                    r_multiple=2.0 if win else -1.0, planned_rr=rr,
                    source="confluence", direction="bullish", tight_stop=tight)


def _arm(n_tickers, per_ticker, wins_per_ticker, **kw):
    return [_t(f"T{k}", i, i < wins_per_ticker, **kw)
            for k in range(n_tickers) for i in range(per_ticker)]


def test_a_same_quality_superset_passes():
    baseline = _arm(40, 2, 1)             # 50% WR, ExpR +0.5 in every ticker
    component = _arm(40, 4, 2)            # twice the trades, identical per-ticker mix
    result = av.evaluate_volume(baseline, component, stage="validation", n_resamples=500, seed=1)
    assert result.verdict == "PASS", [(c.name, c.verdict, c.detail) for c in result.clauses]
    assert result.clause("not_luck").verdict == "SKIPPED"


def test_no_extra_trades_fails_the_objective():
    baseline = _arm(40, 2, 1)
    result = av.evaluate_volume(baseline, list(baseline), stage="train", n_resamples=500, seed=1)
    assert result.clause("volume_gain").verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_more_trades_at_a_collapsed_win_rate_fails_the_floor():
    baseline = _arm(40, 4, 2)             # 50%
    component = _arm(40, 8, 1)            # 12.5%, twice the trades
    result = av.evaluate_volume(baseline, component, stage="walkforward", n_resamples=500, seed=1)
    assert result.clause("volume_gain").verdict == "PASS"
    assert result.clause("win_rate_floor").verdict == "FAIL"
    assert result.verdict == "FAIL"


def test_geometry_lock_still_applies():
    baseline = _arm(40, 2, 1, rr=2.0)
    component = _arm(40, 4, 2, rr=1.5)    # 25% lower planned RR
    result = av.evaluate_volume(baseline, component, stage="train", n_resamples=500, seed=1)
    assert result.clause("geometry").verdict == "FAIL"


def test_unknown_stage_is_an_error():
    with pytest.raises(ValueError):
        av.evaluate_volume([], [], stage="pilot")


def test_walkforward_needs_two_passing_folds_each_with_thirty_decided():
    ok = [{"test_year": y, "verdict": v, "n": 30} for y, v in (("2021", "PASS"), ("2022", "PASS"), ("2023", "FAIL"))]
    assert av.walkforward_verdict(ok) == "PASS"
    one = [dict(f, verdict="FAIL") if f["test_year"] == "2022" else f for f in ok]
    assert av.walkforward_verdict(one) == "FAIL"
    thin = [dict(f, n=29) if f["test_year"] == "2023" else f for f in ok]
    assert av.walkforward_verdict(thin) == "FAIL"


def test_tight_stop_table_splits_by_flag():
    baseline = _arm(2, 2, 1, tight=False)
    component = baseline + _arm(2, 2, 0, tight=True)
    rows = {row["tight_stop"]: row for row in av.tight_stop_table(baseline, component)}
    assert rows[False]["baseline_n"] == 4 and rows[False]["component_n"] == 4
    assert rows[True]["baseline_n"] == 0 and rows[True]["component_n"] == 4
    assert rows[True]["component_win_rate"] == 0.0


def test_markdown_carries_the_tight_stop_section():
    baseline = _arm(40, 2, 1)
    component = _arm(40, 4, 2)
    result = av.evaluate_volume(baseline, component, stage="train", n_resamples=200, seed=1)
    text = av.render_volume_markdown(result, baseline, component, title="t", window="w")
    assert "## By tight_stop (disclosure, not a gate)" in text
    assert "`volume_gain`" in text
```

- [ ] **Step 2: Run and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_volume.py`
Expected: FAIL with `ModuleNotFoundError: swingbot.core.backtesting.acceptance_volume`.

- [ ] **Step 3: Implement** `swingbot/core/backtesting/acceptance_volume.py`:

```python
"""v114 volume-edge acceptance gate, composed only of existing clauses.

`Edge: volume` work claims more accepted trades, not better ones. The objective
is therefore a volume gain, and the win-rate and expectancy clauses become
non-inferiority constraints (v114 spec, Validation). No threshold is restated
or tuned here; each comes from the module named:

| Clause | Source | Threshold |
|---|---|---|
| volume_gain (objective) | this module | component closed trades > baseline |
| win_rate_floor | acceptance_harvest._clause_win_rate_floor | lower 95% >= WIN_RATE_FLOOR_PP |
| profit_floor | acceptance._clause_profit_floor | lower 95% > NON_INFERIORITY_R |
| geometry | acceptance._clause_geometry | drop <= GEOMETRY_MAX_DROP_PCT |
| not_luck | -- | SKIPPED: no improvement is claimed |

Stage 2 reuses backtest_wf's fold rules verbatim (GATE_MIN_N_PER_FOLD,
GATE_MIN_IMPROVING_FOLDS), applied to fold verdicts from this gate.
"""
from __future__ import annotations

from swingbot.core.backtesting import acceptance as acc
from swingbot.core.backtesting.acceptance_harvest import _clause_win_rate_floor
from swingbot.core.backtesting.backtest_wf import GATE_MIN_IMPROVING_FOLDS, GATE_MIN_N_PER_FOLD

VOLUME_VERSION = 1
STAGES = ("train", "walkforward", "validation")
_TIGHT_LABELS = {True: "tight", False: "not tight", None: "n/a (strategy rows)"}


def _clause_volume_gain(baseline, component) -> acc.ClauseResult:
    if not baseline:
        return acc.ClauseResult("volume_gain", "FAIL", "empty baseline arm", None, 0.0)
    gain = 100.0 * (len(component) - len(baseline)) / len(baseline)
    return acc.ClauseResult(
        "volume_gain", "PASS" if gain > 0.0 else "FAIL",
        f"closed trades {len(baseline)} -> {len(component)} ({gain:+.2f}%)", gain, 0.0)


def _clause_not_luck() -> acc.ClauseResult:
    return acc.ClauseResult(
        "not_luck", "SKIPPED",
        "non-inferiority design: no win-rate or expectancy gain is claimed, so "
        "there is no improvement to test against a permutation null", None, acc.ALPHA)


def evaluate_volume(baseline, component, *, stage: str,
                    n_resamples: int = acc.BOOTSTRAP_RESAMPLES,
                    seed: int = 42) -> acc.AcceptanceResult:
    """The volume gate. Every non-SKIPPED clause must PASS."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    split = acc.population_split(baseline, component)
    clauses = (
        _clause_volume_gain(baseline, component),
        _clause_win_rate_floor(baseline, component, n_resamples, seed, split=split),
        acc._clause_profit_floor(baseline, component, n_resamples, seed),
        acc._clause_geometry(baseline, component),
        _clause_not_luck(),
    )
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return acc.AcceptanceResult(
        stage=stage, verdict=verdict, clauses=clauses,
        strata=acc.stratum_table(baseline, component),
        split={k: len(v) if isinstance(v, list) else v for k, v in split.items()},
        seed=seed, version=VOLUME_VERSION)


def walkforward_verdict(folds: list[dict]) -> str:
    """PASS iff every fold holds GATE_MIN_N_PER_FOLD decided trades on both
    arms and at least GATE_MIN_IMPROVING_FOLDS folds PASS evaluate_volume."""
    if any(fold["n"] < GATE_MIN_N_PER_FOLD for fold in folds):
        return "FAIL"
    passing = sum(fold["verdict"] == "PASS" for fold in folds)
    return "PASS" if passing >= GATE_MIN_IMPROVING_FOLDS else "FAIL"


def _tight_row(flag, baseline, component) -> dict:
    return {"tight_stop": flag, "baseline_n": len(baseline), "component_n": len(component),
            "baseline_win_rate": acc.win_rate(baseline), "component_win_rate": acc.win_rate(component),
            "baseline_expectancy_r": acc.expectancy_r(baseline),
            "component_expectancy_r": acc.expectancy_r(component)}


def tight_stop_table(baseline, component) -> list[dict]:
    """Disclosure, not a gate: N / WR / ExpR per arm, split by tight_stop."""
    rows = []
    for flag in (True, False, None):
        b = [t for t in baseline if t.tight_stop is flag]
        c = [t for t in component if t.tight_stop is flag]
        if b or c:
            rows.append(_tight_row(flag, b, c))
    return rows


def render_volume_markdown(result, baseline, component, *, title: str, window: str,
                           notes: str | None = None) -> str:
    body = acc.render_markdown(result, title=title, window=window, notes=notes)
    lines = ["", "## By tight_stop (disclosure, not a gate)", "",
             "| tight_stop | Base N | Comp N | Base WR | Comp WR | Base ExpR | Comp ExpR |",
             "|---|---|---|---|---|---|---|"]
    for row in tight_stop_table(baseline, component):
        lines.append(
            f"| {_TIGHT_LABELS[row['tight_stop']]} | {row['baseline_n']} | {row['component_n']} | "
            f"{acc._fmt_pct(row['baseline_win_rate'])} | {acc._fmt_pct(row['component_win_rate'])} | "
            f"{acc._fmt_r(row['baseline_expectancy_r'])} | {acc._fmt_r(row['component_expectancy_r'])} |")
    return body + "\n".join(lines) + "\n"


def render_walkforward_markdown(rows: list[dict], *, title: str, window: str, verdict: str) -> str:
    lines = [f"# {title} — WALKFORWARD", "",
             f"Procedure: **v114 volume gate v{VOLUME_VERSION}** "
             f"(`swingbot/core/backtesting/acceptance_volume.py`), fold rules from `backtest_wf.py`.",
             f"**Window:** {window}", "",
             "| Test year | Verdict | Decided N (min of arms) | Clauses |", "|---|---|---|---|"]
    for row in rows:
        clauses = "; ".join(f"{c['name']} {c['verdict']}" for c in row["clauses"])
        lines.append(f"| {row['test_year']} | **{row['verdict']}** | {row['n']} | {clauses} |")
    lines += ["", f"**Overall: {verdict}**"]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_volume.py`
Expected: PASS. If `test_a_same_quality_superset_passes` fails only on `profit_floor` or `win_rate_floor` with a nonzero point estimate, check that the fixture really gives every ticker the same mix in both arms. The per-resample delta must be exactly 0 there. Fix the fixture, never the clause.

- [ ] **Step 5: Complexity.** `python -m radon cc -s -n C swingbot/core/backtesting/acceptance_volume.py` prints nothing (every block under C).

- [ ] **Step 6: Commit.**

```bash
git add swingbot/core/backtesting/acceptance_volume.py tests/backtesting/test_acceptance_volume.py
git commit -m "feat(v114): volume-edge gate from existing clauses, tight_stop disclosure

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V114-08: `validate_component.py --gate volume`

**Files:**
- Modify: `scripts/backtest/validate_component.py`
- Create: `tests/backtesting/test_validate_component_volume.py`

**Interfaces:**
- Consumes: V114-07 (`evaluate_volume`, `walkforward_verdict`, `render_volume_markdown`, `render_walkforward_markdown`); existing `load_arms`, `load_folds`, `_folds_are_well_formed`, `_notes`, `render_json`, `check_stamp`, `DECIDED`.
- Produces: CLI `--gate volume` for `--stage train` (selection-window arms, stamp-checked as producer stage `selection`), `--stage walkforward` and `--stage validation`; `vc._funnel_stage(stage: str) -> str`.

- [ ] **Step 1: Write the failing tests.**

```python
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from tests.backtesting.test_validate_component_stamps import UNIVERSE, write  # noqa: E402


def _rows(per_ticker_component):
    baseline, component = [], []
    for ticker in range(25):
        for index in range(per_ticker_component):
            win = index % 2 == 0
            row = {"ticker": f"T{ticker}", "strategy": "Support/Resistance", "horizon_key": "4w",
                   "entry_date": f"2019-03-{index + 1:02d}", "outcome": "win" if win else "loss",
                   "r_multiple": 2.0 if win else -1.0, "planned_rr": 2.0,
                   "source": "confluence", "direction": "bullish", "tight_stop": index >= 2}
            component.append(row)
            if index < 2:
                baseline.append(row)
    return baseline, component


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)


def test_train_maps_to_the_selection_stamp():
    assert vc._funnel_stage("train") == "mde"
    assert vc._funnel_stage("validation") == "validation"


def test_train_stage_runs_the_volume_gate(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_STOP_DISTANCE_PCT": 1.5}, *_rows(4))
    out_md = tmp_path / "train.md"
    code = vc.main(["--stage", "train", "--gate", "volume", "--arms", str(arms), "--title", "v114",
                    "--window", "2018-06-01..2022-12-31", "--resamples", "300", "--out-md", str(out_md)])
    text = capsys.readouterr().out
    assert code == 0, text
    assert "`volume_gain`" in text and "By tight_stop" in out_md.read_text(encoding="utf-8")


def test_train_stage_refuses_the_win_rate_gate(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_STOP_DISTANCE_PCT": 1.5}, *_rows(4))
    assert vc.main(["--stage", "train", "--arms", str(arms), "--title", "t", "--window", "w"]) == 1
    assert "--gate volume" in capsys.readouterr().out


def test_walkforward_volume_uses_fold_verdicts(tmp_path, capsys):
    baseline, component = _rows(4)
    folds = [{"test_year": year, "baseline": baseline, "component": component} for year in ("2021", "2022", "2023")]
    arms = tmp_path / "wf.json"
    arms.write_text(json.dumps({"folds": folds}))
    out_json = tmp_path / "wf-out.json"
    code = vc.main(["--stage", "walkforward", "--gate", "volume", "--arms", str(arms), "--title", "t",
                    "--window", "2021..2023", "--resamples", "300", "--out-json", str(out_json),
                    "--bespoke-instrument", "unit fixture"])
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert [fold["test_year"] for fold in blob["folds"]] == ["2021", "2022", "2023"]
    assert blob["verdict"] == ("PASS" if code == 0 else "FAIL")
```

- [ ] **Step 2: Run and confirm they fail.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_volume.py`
Expected: FAIL. `_funnel_stage` is missing, and argparse rejects `train` / `volume`.

- [ ] **Step 3: Implement.** Keep the file's compact style. Make these edits to `scripts/backtest/validate_component.py`:

(a) After the existing `acceptance_harvest` import:

```python
from swingbot.core.backtesting.acceptance_volume import evaluate_volume, render_volume_markdown, render_walkforward_markdown, walkforward_verdict  # noqa: E402
```

(b) Add after `_full_universe`:

```python
def _funnel_stage(stage):
    """`train` is the v114 volume gate's TRAIN check on selection-window arms."""
    return "mde" if stage == "train" else stage

def _write_outputs(args, markdown, blob):
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(blob, indent=1), encoding="utf-8")
```

(c) In `_stamp_gate`, change `funnel_stage=args.stage` to `funnel_stage=_funnel_stage(args.stage)`.

(d) Add the volume paths before `stage_validation`:

```python
def _run_volume_gate(args, stage):
    baseline, component = load_arms(args.arms)
    result = evaluate_volume(baseline, component, stage=stage, n_resamples=args.resamples, seed=args.seed)
    markdown = render_volume_markdown(result, baseline, component, title=args.title, window=args.window, notes=_notes(args)); print(markdown)
    _write_outputs(args, markdown, render_json(result))
    return 0 if result.verdict == "PASS" else 1

def _fold_row(args, fold):
    result = evaluate_volume(fold["baseline"], fold["component"], stage="walkforward", n_resamples=args.resamples, seed=args.seed)
    n = min(sum(t.outcome in DECIDED for t in fold["baseline"]), sum(t.outcome in DECIDED for t in fold["component"]))
    return {"test_year": fold["test_year"], "verdict": result.verdict, "n": n, "clauses": render_json(result)["clauses"]}

def _walkforward_volume(args, folds):
    rows = [_fold_row(args, fold) for fold in folds]
    verdict = walkforward_verdict(rows)
    markdown = render_walkforward_markdown(rows, title=args.title, window=args.window, verdict=verdict); print(markdown)
    _write_outputs(args, markdown, {"verdict": verdict, "folds": rows})
    return 0 if verdict == "PASS" else 1

def stage_train(args):
    if args.gate != "volume":
        print("REFUSED -- --stage train is the v114 volume gate's TRAIN check; pass --gate volume."); return 1
    return _run_volume_gate(args, "train")
```

(e) In `stage_walkforward`, directly after the `_folds_are_well_formed` refusal line, add:

```python
    if args.gate == "volume": return _walkforward_volume(args, folds)
```

(f) Replace `def stage_validation(args): return _run_gate(args, "validation")` with:

```python
def stage_validation(args): return _run_volume_gate(args, "validation") if args.gate == "volume" else _run_gate(args, "validation")
```

(g) In `main`: add `"train"` to the `--stage` choices, add `"volume"` to the `--gate` choices, and add `"train": stage_train` to the dispatch dict.

- [ ] **Step 4: Run the touched tests.**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_volume.py`, then `... file tests/backtesting/test_validate_component_stamps.py`, then `... file tests/backtesting/test_validate_component_cli.py`.
Expected: PASS. The existing CLI and stamp tests still pass, because the default `--gate win_rate` paths are untouched.

- [ ] **Step 5: Complexity.** `python -m radon cc -s -n C scripts/backtest/validate_component.py` shows no block at 15 or above (`main` stays a dispatch).

- [ ] **Step 6: Commit.**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_volume.py
git commit -m "feat(v114): validate_component --gate volume for train, walkforward and validation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

