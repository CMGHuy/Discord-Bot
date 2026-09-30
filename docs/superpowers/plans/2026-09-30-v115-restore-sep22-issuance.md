# v115 — Restore pre-09-23 issuance (clamp wide stops to 1.75%, floor back to 2.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md`](../specs/2026-09-30-v115-restore-sep22-issuance-design.md) (partner-approved 2026-09-30, committed at `5c52ee69`)
**Bump:** bot minor
**Edge:** volume

**Goal:** Issue trades the way the bot did before 2026-09-23. A confluence setup whose natural stop is wider than 2% is issued with its stop moved to 1.75% from the trigger, 0.25% inside the cap, so a fill a little past the trigger is not cancelled `risk_cap`. The stop floor goes back to 2.0. The futures/FX/index dollar-volume exemption and the post-09-22 strategy work (v92/v103/v104/v108/v113) are switched off, and a test keeps them off.

**Architecture:** Two new `.env` flags in `swingbot/config.py`. `CLAMP_STOP_TO_HARD_CAP` (default `true`) is read by a new helper `_clamp_stop_to_hard_cap` in `swingbot/core/planning/builders.py`. `build_confluence_plan` calls the helper before target selection, so the target, TP2 and the plan all use the clamped stop. The clamp lands at `HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT` (a 0.25 module constant) because `plan_manager._step_pending` cancels a fill past 2.0% with no tolerance. Replay calls the same builder, so it clamps by default. `LIQUIDITY_EXEMPT_NON_EQUITY` (default `false`) is read by a new helper `_dollar_volume_exempt` in `swingbot/core/marketdata/universe.py`. The helper decides whether `liquidity_reason` skips the dollar-volume floor. v109 spot metals (from `spot_metals.is_spot_metal`) always skip it, and futures/FX/indices skip it only while the flag is on (partner decision 2026-09-30). A guaranteed-off test pins every value in the spec's § Strategy work table, at the code default and as parsed from `.env.example`. The last task runs the suite and ships the release. Then it edits the production `.env` in place, sets `MIN_STOP_DISTANCE_PCT=2.0` and mirrors the change back.

**Tech Stack:** Python 3.11, pytest, python-dotenv, radon, Docker Compose on the Hetzner VM (`scripts/ops/ssh-hetzner.sh`).

## Global Constraints

- Flag defaults are fixed by the spec: `CLAMP_STOP_TO_HARD_CAP` = `true`, `LIQUIDITY_EXEMPT_NON_EQUITY` = `false`, `MIN_STOP_DISTANCE_PCT` = `2.0` (code default is already `"2.0"`, `swingbot/config.py:154-157`; `.env.example:83` currently ships `1.0`). `SIGNAL_CONFIRMATION_SCANS` stays `1`. Do not change it anywhere.
- No `git revert`. No strategy code is deleted. `a356c7f2` (lifecycle ceiling at 2%) and `1eb9a194` stay.
- The `f01e87e2` `risk_cap` reject in `attach_plan_v2` (`swingbot/core/scanning/analyze.py:375`) **stays as a safety net**. Do not edit it.
- Only the confluence builder clamps. Scenario building, the admission gate (`MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT`), `gating.scenario_gate_inputs` and the scan funnel counts are untouched.
- Clamp formula (spec § Behaviour and § Headroom, revision 3): when on and `planned_loss_pct(entry, stop) > HARD_MAX_PLANNED_LOSS_PCT` (2.0), the stop becomes `entry -/+ entry * (2.0 - CLAMP_HEADROOM_PCT) / 100` (long/short), i.e. **1.75%** from `entry = scenario.entry` (the trigger). `CLAMP_HEADROOM_PCT = 0.25` is a module constant in `builders.py`, not a flag. The following are returned unchanged: a stop already within 2.0% (including 1.75-2.0), a `None` stop, a stop on the wrong side of the entry, and any stop when the entry is invalid.
- `plan_manager._step_pending`'s fill check, `analyze.py` and `lifecycle.py` are **not edited**. A fill more than about 0.25% past the trigger is still cancelled `risk_cap`. That is the 2% policy working as designed.
- Every function written or changed ends at radon cyclomatic complexity **< 15** (`python -m radon cc -s <file>`). `build_confluence_plan` is **already C (14)**. The clamp must live in the helper. Adding any `if`, `and`, `or` or conditional expression to `build_confluence_plan` itself takes it to 15.
- New config fields keep the default `search_class="excluded"`. Do not add them to `ScanParams` or `_SEARCH_CLASSES` (`tests/test_scan_params_coverage.py` requires ScanParams to cover exactly the searchable/frozen/never fields).
- Production `.env` is edited **in place** (`cat new > .env`), never with `sed -i` (`docs/claude/known-traps.md` § "Editing production `.env` with `sed -i` changes nothing live"). Always go through `scripts/ops/ssh-hetzner.sh`. It is uncommitted, so it exists only in the main tree at `E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh`, not in the worktree.
- Production `MIN_STOP_DISTANCE_PCT=2.0` is set **only after** the v115 code is running on production. With the old image, 2.0 brings back "posts nothing".
- Code lives on the worktree branch `2026-09-30-v115-restore-sep22-issuance` (`.claude/worktrees/2026-09-30-v115-restore-sep22-issuance/`). Stage files by name. Keep commits small and single-purpose. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Per-task checks: `python scripts/dev/testrun.py file <test path>`. The full suite runs once, in V115-07.

## Parallelisation

- **Sequential:** V115-01 before everything. It creates the worktree every other task works in, and its production read decides whether V115-07's `.env` edit touches any key besides `MIN_STOP_DISTANCE_PCT`.
- **Group 1 (parallel):** V115-02, V115-05. They touch different files. V115-02 edits `swingbot/config.py` and `.env.example` and creates `tests/test_v115_flags.py`. V115-05 creates `tests/test_v115_strategy_work_off.py`. V115-05 only *reads* `.env.example` keys that V115-02 does not change. Neither task uses a symbol the other one introduces.
- **Group 2 (parallel, after V115-02):** V115-03, V115-04, V115-06. They touch different files. V115-03 edits `builders.py`, the `CLAMP_STOP_TO_HARD_CAP` help text in `config.py`, two `.env.example` comments and four existing test files, and creates `tests/planning/test_confluence_stop_clamp.py`. V115-04 edits `universe.py` and `tests/marketdata/test_universe.py`. V115-06 edits `docs/claude/known-traps.md` and `AGENTS.md`. All three come after V115-02: V115-03 and V115-04 read `config.CLAMP_STOP_TO_HARD_CAP` / `config.LIQUIDITY_EXEMPT_NON_EQUITY`, which V115-02 creates, and V115-06 documents those flag names.
- **Sequential:** V115-07 runs last. It runs the full suite over everything above, then does the release, the deploy and the production edit, in that order. The production edit needs the deployed image, the deploy needs a green `main`, and `main` needs the suite.

---

# Phase A — Build (worktree branch)

### Task V115-01: Worktree and read-only production snapshot

**Files:**
- Create: none in the repo. `v115_read_config.py` goes in your session scratchpad, **never** in the repo.

**Interfaces:**
- Consumes: nothing.
- Produces: the worktree `.claude/worktrees/2026-09-30-v115-restore-sep22-issuance/` on branch `2026-09-30-v115-restore-sep22-issuance`. A written note in your progress log: the effective production values of every key below, and which § Strategy work keys differ from the spec's table. V115-07 uses both.

- [ ] **Step 1: Create the worktree** (use the `worktree-lifecycle` skill)

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git fetch origin && git status -sb
git worktree add .claude/worktrees/2026-09-30-v115-restore-sep22-issuance -b 2026-09-30-v115-restore-sep22-issuance main
```

Expected: a new worktree at `main`'s HEAD (which contains `5c52ee69` and this plan's commit).

- [ ] **Step 2: Re-verify the symbols this plan edits** (from the worktree root)

```bash
git grep -n "def build_confluence_plan\|def _clamp_stop_to_hard_cap" -- swingbot/core/planning/builders.py
git grep -n "HARD_MAX_PLANNED_LOSS_PCT = 2.0\|def planned_loss_pct" -- swingbot/core/risk_limits.py
git grep -n "def liquidity_reason\|def _volume_is_not_shares\|_VOLUME_NOT_SHARES = " -- swingbot/core/marketdata/universe.py
git grep -n "HARD_MAX_PLANNED_LOSS_PCT + 1e-9" -- swingbot/core/scanning/analyze.py
git grep -n '"MIN_STOP_DISTANCE_PCT", "MIN_STOP_DISTANCE_PCT"' -A 1 -- swingbot/config.py
git grep -n "CLAMP_STOP_TO_HARD_CAP\|LIQUIDITY_EXEMPT_NON_EQUITY" -- swingbot tests .env.example
python -m radon cc -s swingbot/core/planning/builders.py swingbot/core/marketdata/universe.py | grep -E "build_confluence_plan|liquidity_reason"
```

Expected: `build_confluence_plan` at `builders.py:360` and no `_clamp_stop_to_hard_cap`. `HARD_MAX_PLANNED_LOSS_PCT = 2.0`. `liquidity_reason` at `universe.py:39`. The `risk_cap` line at `analyze.py:375`. `MIN_STOP_DISTANCE_PCT` Field with `default="2.0"`. **No** hit for either new flag. Radon: `build_confluence_plan - C (14)`, `liquidity_reason - B (9)`. If a line number moved, use the new one. If either flag already exists, stop and report: another session has started this work.

- [ ] **Step 3: Write the production read script** to `<scratchpad>/v115_read_config.py`

```python
"""v115: print the effective config the bot container resolves (missing key -> code default)."""
from swingbot import config
from swingbot.core.market import strategy_types as st
from swingbot.core.market.entry_filters import DEFAULT_PARAMS

KEYS = [
    "PLAN_ENGINE_V2", "SIGNAL_CONFIRMATION_SCANS", "MIN_STOP_DISTANCE_PCT",
    "MAX_STOP_LOSS_PCT", "MIN_REWARD_PCT", "MIN_RISK_REWARD_RATIO",
    "UNIVERSE_MIN_DOLLAR_VOL",
    # spec § Strategy work
    "ADAPTIVE_RUNNER_TRAIL_ENABLED", "DATA_DRIVEN_STOPS_ENABLED", "STALL_EXIT_ENABLED",
    "FIB_LEVEL_STOP_ATR", "FIB_LEVEL_STOP_DIRECTIONS", "STRUCTURAL_STOP_SCOPE",
    # v115 flags (absent until the v115 image is deployed)
    "CLAMP_STOP_TO_HARD_CAP", "LIQUIDITY_EXEMPT_NON_EQUITY",
]
for key in KEYS:
    print(f"{key} = {getattr(config, key, '<absent: pre-v115 image>')!r}")
for name in ("Fibonacci Continuation", *st.SHORT_STRATEGIES):
    print(f"STRATEGY_GATES[{name!r}] = {st.STRATEGY_GATES.get(name)!r}")
print(f"MASKED_BY_DEFAULT_HORIZONS = {st.MASKED_BY_DEFAULT_HORIZONS!r}")
print(f"gates with cells = {[k for k, g in st.STRATEGY_GATES.items() if g.get('cells')]!r}")
ema = DEFAULT_PARAMS["EMA Crossover"]
print(f"EMA Crossover touches = {ema.get('max_touches_bull')!r}/{ema.get('max_touches_bear')!r}")
```

- [ ] **Step 4: Run it inside the bot container (read-only)**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <scratchpad>/v115_read_config.py
```

Expected today: `MIN_STOP_DISTANCE_PCT = 1.0`, `SIGNAL_CONFIRMATION_SCANS = 1`, both v115 flags `<absent: pre-v115 image>`. Record every line in your progress log. Then compare the § Strategy work lines to the spec's table: `False`, `False`, `False`, `0.0`, `''`, `''`, every masked gate `{'directions': ()}`, `('1w',)`, `[]`, `1/1`. List every key that differs. **If `PLAN_ENGINE_V2` is not `'on'`, stop and ask the partner** (via `AskUserQuestion`). Embeds only show v2 plan numbers when it is `'on'` (`swingbot/core/scanning/plan_table.py:17`). In `shadow`, alerts still post the scenario's unclamped stop, so the clamp would not reach an alert.

- [ ] **Step 5: No commit** (nothing in the repo changed).

---

### Task V115-02: The two v115 flags and the 2.0 floor in `.env.example`

**Files:**
- Modify: `swingbot/config.py` (insert one Field after the `MAX_STOP_LOSS_PCT` Field, about line 161; insert one Field after the `UNIVERSE_MIN_PRICE` Field, about line 752)
- Modify: `.env.example` (the `MIN_STOP_DISTANCE_PCT` block, lines 78-83; after the `MAX_STOP_LOSS_PCT` line 87; after `UNIVERSE_MIN_PRICE=5.0`, line 469)
- Test: `tests/test_v115_flags.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `config.CLAMP_STOP_TO_HARD_CAP: bool` (default `True`) and `config.LIQUIDITY_EXEMPT_NON_EQUITY: bool` (default `False`), both hot-reloadable module globals. `.env.example` ships `MIN_STOP_DISTANCE_PCT=2.0`, `CLAMP_STOP_TO_HARD_CAP=true` and `LIQUIDITY_EXEMPT_NON_EQUITY=false`.

- [ ] **Step 1: Write the failing test** at `tests/test_v115_flags.py`

```python
"""v115: the two issuance flags and the 2.0 stop floor, in the schema and in .env.example."""
from pathlib import Path

from dotenv import dotenv_values

from swingbot import config

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


def test_clamp_flag_is_a_default_on_checkbox_outside_the_search():
    f = _field("CLAMP_STOP_TO_HARD_CAP")
    assert (f.attr, f.type, f.default, f.section) == (
        "CLAMP_STOP_TO_HARD_CAP", "checkbox", "true", "Trade Filters & Risk")
    assert f.search_class == "excluded"
    assert config._cast(f, f.default) is True


def test_liquidity_flag_is_a_default_off_checkbox_outside_the_search():
    f = _field("LIQUIDITY_EXEMPT_NON_EQUITY")
    assert (f.attr, f.type, f.default, f.section) == (
        "LIQUIDITY_EXEMPT_NON_EQUITY", "checkbox", "false", "Universe & Scanning")
    assert f.search_class == "excluded"
    assert config._cast(f, f.default) is False


def test_stop_floor_code_default_is_two():
    assert _field("MIN_STOP_DISTANCE_PCT").default == "2.0"


def test_env_example_ships_the_v115_values():
    values = dotenv_values(ENV_EXAMPLE)
    assert values.get("MIN_STOP_DISTANCE_PCT") == "2.0"
    assert values.get("CLAMP_STOP_TO_HARD_CAP") == "true"
    assert values.get("LIQUIDITY_EXEMPT_NON_EQUITY") == "false"
    assert values.get("SIGNAL_CONFIRMATION_SCANS") == "1"   # spec: stays 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_v115_flags.py`
Expected: FAIL. The first two tests fail with `StopIteration` (field not defined), and `test_env_example_ships_the_v115_values` fails on `'1.0' == '2.0'`.

- [ ] **Step 3: Add the `CLAMP_STOP_TO_HARD_CAP` Field** to `swingbot/config.py`, directly after the `MAX_STOP_LOSS_PCT` Field (the one whose help ends `"...realised fills remain reported honestly."),`)

```python
    Field("CLAMP_STOP_TO_HARD_CAP", "CLAMP_STOP_TO_HARD_CAP", "Trade Filters & Risk",
          "Clamp wide confluence stops to the 2% cap",
          type="checkbox", default="true",
          help="v115. A confluence setup whose natural stop sits further than 2% from the entry "
               "is still issued, with its stop moved to exactly 2% from the entry. The target is "
               "then chosen against that tighter risk, and the setup is dropped if no level pays "
               "the min reward:risk ratio. Off: the stop stays where the levels put it and any plan "
               "beyond 2% is rejected (risk_cap), which at a 2.0% stop floor posts almost nothing. "
               "Historical replay clamps too. An unmeasured live change (v115, Edge: volume)."),
```

- [ ] **Step 4: Add the `LIQUIDITY_EXEMPT_NON_EQUITY` Field** to `swingbot/config.py`, directly after the `UNIVERSE_MIN_PRICE` Field (the one whose help ends `"...bot is tuned for."),`)

```python
    Field("LIQUIDITY_EXEMPT_NON_EQUITY", "LIQUIDITY_EXEMPT_NON_EQUITY", "Universe & Scanning",
          "Exempt futures/FX/indices from the dollar-volume floor",
          type="checkbox", default="false",
          help="v115. On: futures, FX and indices skip the average dollar-volume floor, because "
               "Yahoo reports their volume in contracts or as 0, so Close x Volume understates "
               "them. Off (default, the 09-22 behaviour): they must clear UNIVERSE_MIN_DOLLAR_VOL, "
               "so a thin-contract future such as SI=F is skipped for new signals. Spot metals "
               "(XAUUSD, XAGUSD) are exempt either way. History and price floors always apply."),
```

- [ ] **Step 5: Edit `.env.example`.** Replace the `MIN_STOP_DISTANCE_PCT` block:

```
# Hard filter: dropped entirely if the stop sits closer than this to
# entry -- too exposed to ordinary daily noise. No exceptions.
# 1.0 on production since 2026-09-30: at 2.0 the only stop that survived
# plan build's 2% risk cap was exactly 2.0%, so 0 setups posted for days.
# Unmeasured live stopgap -- v114 validates the stop band properly.
MIN_STOP_DISTANCE_PCT=1.0
```

with:

```
# Hard filter: dropped entirely if the stop sits closer than this to
# entry -- too exposed to ordinary daily noise. No exceptions.
# 2.0 again since v115: CLAMP_STOP_TO_HARD_CAP (below) moves a wider stop to
# exactly 2%, so this floor no longer leaves an empty band. Production ran
# 1.0 as a stopgap on 2026-09-30.
MIN_STOP_DISTANCE_PCT=2.0
```

Directly after the line `MAX_STOP_LOSS_PCT=7.0`, insert:

```

# v115: a confluence stop wider than 2% is moved to exactly 2% from the
# entry (the target is re-chosen against that risk) instead of the plan being
# rejected. false = reject such plans (risk_cap); at a 2.0 stop floor that
# posts almost nothing. Historical replay clamps too.
CLAMP_STOP_TO_HARD_CAP=true
```

Directly after the line `UNIVERSE_MIN_PRICE=5.0`, insert:

```

# v115: true exempts futures/FX/indices from the dollar-volume floor above
# (their Yahoo volume is contracts or 0). false = they must clear it, the
# 09-22 behaviour. Spot metals (XAUUSD, XAGUSD) are exempt either way.
LIQUIDITY_EXEMPT_NON_EQUITY=false
```

- [ ] **Step 6: Run the new test and the schema-parity tests**

Run: `python scripts/dev/testrun.py file tests/test_v115_flags.py`
Expected: PASS (4 tests).
Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/test_scan_params_coverage.py`
Expected: PASS. Both new fields are `excluded`, so ScanParams still covers exactly the searchable/frozen/never set.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py .env.example tests/test_v115_flags.py
git commit -m "feat(v115): CLAMP_STOP_TO_HARD_CAP and LIQUIDITY_EXEMPT_NON_EQUITY flags; .env.example floor back to 2.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V115-03: Clamp a confluence stop beyond the 2% cap to 1.75% before target selection

**Files:**
- Modify: `swingbot/core/planning/builders.py` (imports at lines 1-20; new constant and helpers directly above `def build_confluence_plan`, line 360; the body of `build_confluence_plan`, lines 376-409)
- Modify: `swingbot/config.py` (the `CLAMP_STOP_TO_HARD_CAP` help text V115-02 added) and `.env.example` (the two comments V115-02 wrote that say "exactly 2%")
- Test: `tests/planning/test_confluence_stop_clamp.py` (create)
- Modify: `tests/scanning/test_engine_v2_plans.py` (the `f01e87e2` test at lines 310-322, plus imports)
- Modify: `tests/planning/test_build_confluence_plan.py` (add an autouse fixture)
- Modify: `tests/backtesting/test_v74_no_behaviour_change.py` (pin the flag off)
- Modify: `tests/backtesting/test_armed_replay.py` (a module-level autouse fixture pinning the flag off)

**Interfaces:**
- Consumes: `config.CLAMP_STOP_TO_HARD_CAP: bool` (V115-02). `swingbot.core.risk_limits.HARD_MAX_PLANNED_LOSS_PCT: float` (= 2.0). `planned_loss_pct(entry_price, stop_loss) -> float`.
- Produces: `builders.CLAMP_HEADROOM_PCT: float = 0.25` (a module constant, not a flag). `builders._stop_is_clampable(entry, stop_loss, is_bull) -> bool`. `builders._clamp_stop_to_hard_cap(entry: float, stop_loss: float | None, is_bull: bool) -> float | None`. `build_confluence_plan` returns plans whose `stop_loss` is the clamped stop, with `tp1`/`tp2` chosen against it.

**Rule (spec § Behaviour and § Headroom, revision 3, partner 2026-09-30).** With the flag on and `planned_loss_pct(entry, stop) > HARD_MAX_PLANNED_LOSS_PCT` (2.0), the stop becomes `entry -/+ entry * (2.0 - CLAMP_HEADROOM_PCT) / 100`, i.e. **1.75% from the trigger**. The following are returned unchanged:
- a stop already within 2.0% (including 1.75-2.0%);
- a `None` stop;
- a stop on the wrong side of the entry;
- any stop when the entry is invalid.

Why not exactly 2%: `plan_manager._step_pending` (`swingbot/core/planning/plan_manager.py:564-570`) cancels a stop-entry fill `risk_cap` when `planned_loss_pct(fill, stop) > HARD_MAX_PLANNED_LOSS_PCT`, with **no tolerance**. A 2.0% stop is cancelled on any fill past the trigger, and float rounding alone puts about half of such plans over by an ulp. With 0.25% of headroom, a fill can land about 0.25% past the trigger. A worse gap is still cancelled, as the 2% policy intends. **Do not edit** the fill check, `analyze.py` or `lifecycle.py`.

Why the four existing test files change: this was measured before writing the plan. A pytest plugin wrapped `build_confluence_plan` with a clamp that fires on the same `> 2.0%` condition. It was run over `tests/backtesting`, `tests/planning/test_build_confluence_plan.py`, `tests/planning/test_plan_engine_structure.py`, `tests/scanning/test_engine_v2_plans.py`, `tests/scanning/test_decision_debug_logs.py`, `tests/scanning/test_live_context_stamp.py`, `tests/scripts/test_training_universe.py` and `tests/edge/test_edge_stops.py`. It failed exactly these tests:
- `test_build_confluence_plan.py`: `test_tp1_is_the_scenarios_own_target_when_it_sits_in_the_band`, `test_tp1_is_capped_when_the_nearest_level_is_beyond_max_rr` and all six `test_reward_always_at_least_min_times_risk` cases. They pin target selection against a 4% scenario risk.
- `test_v74_no_behaviour_change.py::test_from_config_reproduces_pre_v74_golden_plans`. It pins pre-v74 replay plans, which were unclamped.
- `test_armed_replay.py::test_m1_issues_a_stop_entry_above_the_reaction_high`. Its stop is 2.11% from a 99.6 trigger.
- `test_armed_replay.py::test_the_widened_scenario_issues_once_its_stop_is_re_anchored`. This one fails only with the 1.75% clamp: the 2% clamp would have left a 2.0% stop, while the 1.75% clamp gives 1.743%, below the test's `>= 2.0` assertion (found in the dry run of this revision). It asserts the armed stop clears the 2.0 floor. Under v115, a clamped plan's stop sits **below** `MIN_STOP_DISTANCE_PCT` by design: admission checks the scenario, and the clamp then tightens the plan.
- `test_engine_v2_plans.py::test_attach_plan_v2_rejects_a_plan_whose_stop_is_beyond_the_hard_cap` (the `f01e87e2` test).

The first three pin pre-v115 geometry on purpose, so they get the flag pinned off; the clamp has its own tests. The `f01e87e2` test is rewritten for the clamp, as the spec requires. Replay output changes by default (known-traps note, V115-06). `armed_replay.plan_at` keeps the scenario's unclamped `stop_distance_pct` while its plan carries the clamped stop. The spec records this as known, and this task does not change it.

- [ ] **Step 1: Write the failing clamp tests** at `tests/planning/test_confluence_stop_clamp.py`

```python
"""v115: build_confluence_plan clamps a stop beyond the 2% hard cap to 1.75%
from the trigger (cap minus CLAMP_HEADROOM_PCT), BEFORE target selection, so
tp1 pays the min R:R against the clamped risk, and a fill a little past the
trigger still clears plan_manager's no-tolerance fill guard.
Spec: docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md"""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


def _params():
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])


def _build(scenario, level_map=None):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=level_map, params=_params())


@pytest.fixture
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def test_headroom_is_a_quarter_percent_inside_the_cap():
    assert builders.CLAMP_HEADROOM_PCT == 0.25
    assert HARD_MAX_PLANNED_LOSS_PCT - builders.CLAMP_HEADROOM_PCT == pytest.approx(1.75)


def test_long_four_percent_stop_is_clamped_to_one_seventy_five(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 96.0, 104.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(104.0)                        # 2.29R
    assert (plan.tp1 - 100.0) / (100.0 - plan.stop_loss) >= 1.5 - 1e-9


def test_short_four_percent_stop_is_clamped_to_one_seventy_five(clamp_on):
    plan = _build(_scenario("bearish", 100.0, 104.0, 96.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(101.75)
    assert plan.tp1 == pytest.approx(96.0)
    assert (100.0 - plan.tp1) / (plan.stop_loss - 100.0) >= 1.5 - 1e-9


def test_target_is_chosen_against_the_clamped_risk(clamp_on):
    # Clamped risk 1.75 -> band [102.625, 104.375]: the nearest qualifying level
    # is 103. Unclamped (risk 5) the floor would be 107.5 and tp1 would be 112.
    resistances = [levels.Level(p, ["Fibonacci"]) for p in (103.0, 104.5, 112.0)]
    supports = [levels.Level(90.0, ["Rolling S/R"])]
    plan = _build(_scenario("bullish", 100.0, 95.0, 112.0), level_map=(supports, resistances))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(103.0)


def test_no_target_paying_min_rr_at_the_clamped_risk_returns_none(clamp_on):
    # 102.5 is 1.43R against the clamped 1.75% risk: the no_qualifying_target path.
    assert _build(_scenario("bullish", 100.0, 96.0, 102.5)) is None


@pytest.mark.parametrize("stop", [98.5, 98.1, 98.0])   # 1.5%, 1.9%, exactly the cap
def test_a_stop_within_the_cap_is_untouched(clamp_on, stop):
    plan = _build(_scenario("bullish", 100.0, stop, 104.0))
    assert plan.stop_loss == stop


def test_flag_off_restores_the_unclamped_stop(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    plan = _build(_scenario("bullish", 100.0, 96.0, 108.0))
    assert plan.stop_loss == 96.0
    assert plan.tp1 == pytest.approx(108.0)


def test_a_clamped_plan_survives_a_small_gap_past_the_trigger(clamp_on):
    # GC=F 2026-09-28 prices. plan_manager._step_pending cancels risk_cap when
    # planned_loss_pct(fill, stop) > HARD_MAX_PLANNED_LOSS_PCT, no tolerance.
    plan = _build(_scenario("bearish", 4194.30, 4278.68, 4066.11))
    assert plan is not None
    assert planned_loss_pct(plan.trigger_price, plan.stop_loss) == pytest.approx(1.75)
    fill_0_2 = plan.trigger_price * (1 - 0.002)     # a short fills below its trigger
    assert planned_loss_pct(fill_0_2, plan.stop_loss) <= HARD_MAX_PLANNED_LOSS_PCT
    fill_0_3 = plan.trigger_price * (1 - 0.003)     # past the headroom: still cancelled
    assert planned_loss_pct(fill_0_3, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT


@pytest.mark.parametrize("entry,stop,is_bull", [
    (0.0, 5.0, True),        # invalid entry
    (100.0, None, True),     # no stop
    (100.0, 105.0, True),    # long stop above entry (wrong side)
    (100.0, 95.0, False),    # short stop below entry (wrong side)
])
def test_helper_leaves_an_unclampable_stop_alone(clamp_on, entry, stop, is_bull):
    assert builders._clamp_stop_to_hard_cap(entry, stop, is_bull) == stop
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py`
Expected: FAIL. `test_headroom_...` and the four `test_helper_...` cases fail with `AttributeError` (no `CLAMP_HEADROOM_PCT` / `_clamp_stop_to_hard_cap`). The long, short, target-choice and gap tests fail on `stop_loss`/`tp1` (for example `96.0 != 98.25`). The no-target, within-cap and flag-off tests already pass: they pin behaviour the clamp must not change.

- [ ] **Step 3: Implement the constant and helpers** in `swingbot/core/planning/builders.py`

Add `from swingbot import config` to the imports (after `import numpy as np`). Change line 11 to:

```python
from swingbot.core.risk_limits import (HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct,
                                       planned_loss_pct)
```

Insert directly above `def build_confluence_plan(`:

```python
# v115 rev 3: a clamped confluence stop sits this far INSIDE the 2% hard cap.
# plan_manager._step_pending cancels a stop-entry fill risk_cap when
# planned_loss_pct(fill, stop) > HARD_MAX_PLANNED_LOSS_PCT with no tolerance,
# so a stop at exactly 2% is cancelled on any fill past the trigger (and float
# rounding alone tips half of them over). Not a flag: the partner fixed it.
CLAMP_HEADROOM_PCT = 0.25


def _stop_is_clampable(entry, stop_loss, is_bull) -> bool:
    """True when the v115 clamp may move this stop: the flag is on, the entry
    is valid, and the stop sits on the loss side of it."""
    if not config.CLAMP_STOP_TO_HARD_CAP or entry is None or stop_loss is None or entry <= 0:
        return False
    return stop_loss < entry if is_bull else stop_loss > entry


def _clamp_stop_to_hard_cap(entry, stop_loss, is_bull):
    """v115: a confluence stop further than HARD_MAX_PLANNED_LOSS_PCT from the
    trigger moves to cap - CLAMP_HEADROOM_PCT (1.75%) from it, so the setup is
    issued instead of rejected by attach_plan_v2's risk_cap safety net, and a
    fill a little past the trigger is not cancelled risk_cap. A stop within
    the cap, or one _stop_is_clampable refuses, is returned unchanged."""
    if not _stop_is_clampable(entry, stop_loss, is_bull):
        return stop_loss
    if planned_loss_pct(entry, stop_loss) <= HARD_MAX_PLANNED_LOSS_PCT:
        return stop_loss
    offset = entry * (HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT) / 100.0
    return entry - offset if is_bull else entry + offset
```

- [ ] **Step 4: Use it in `build_confluence_plan`.** Three edits, and no new branch in this function (it is at CC 14):

After `is_bull = scenario.direction == "bullish"`, add:

```python
    stop_loss = _clamp_stop_to_hard_cap(entry, scenario.stop_loss, is_bull)
```

Change the target call from `select_structural_target(entry, scenario.stop_loss, is_bull, candidates,` to:

```python
    tp1 = select_structural_target(entry, stop_loss, is_bull, candidates,
                                   params.min_risk_reward_ratio, params.max_risk_reward_ratio)
```

In the `TradePlanV2(...)` constructor, change `stop_loss=scenario.stop_loss,` to `stop_loss=stop_loss,`. Add one sentence to the docstring: `v115: a stop beyond the 2% hard cap is first clamped to 1.75% (_clamp_stop_to_hard_cap), so tp1/tp2 and the plan use the clamped risk.`

- [ ] **Step 5: Correct the "exactly 2%" wording V115-02 shipped.** In `swingbot/config.py`, in the `CLAMP_STOP_TO_HARD_CAP` Field, replace

```python
          help="v115. A confluence setup whose natural stop sits further than 2% from the entry "
               "is still issued, with its stop moved to exactly 2% from the entry. The target is "
```

with

```python
          help="v115. A confluence setup whose natural stop sits further than 2% from the entry "
               "is still issued, with its stop moved to 1.75% from the entry (0.25% inside the "
               "cap, so a fill a little past the trigger is not cancelled). The target is "
```

In `.env.example`, replace `# 2.0 again since v115: CLAMP_STOP_TO_HARD_CAP (below) moves a wider stop to\n# exactly 2%, so this floor` with `# 2.0 again since v115: CLAMP_STOP_TO_HARD_CAP (below) moves a wider stop to\n# 1.75%, so this floor`. Also replace `# v115: a confluence stop wider than 2% is moved to exactly 2% from the\n# entry` with `# v115: a confluence stop wider than 2% is moved to 1.75% from the entry\n# (0.25% headroom under the cap)`. Leave every other line of those comments unchanged.

- [ ] **Step 6: Run the clamp tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py`
Expected: PASS (14 tests).

- [ ] **Step 7: Rewrite the `f01e87e2` attach test** in `tests/scanning/test_engine_v2_plans.py`

Add to the imports: `from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct`. Replace the whole of `test_attach_plan_v2_rejects_a_plan_whose_stop_is_beyond_the_hard_cap` (lines 310-322) with:

```python
def _gc_scenario():
    return SimpleNamespace(direction="bearish", entry=4194.30, stop_loss=4278.68,
                           take_profit=4066.11, target_sources=["FVG (bullish)"],
                           stop_sources=["Rolling resistance"])


def test_attach_plan_v2_clamps_a_stop_beyond_the_hard_cap_and_issues(monkeypatch):
    # Production 2026-09-28: GC=F plans with a 2.01% trigger-to-stop loss were
    # posted, then cancelled_risk_cap on fill, and f01e87e2 then rejected them.
    # v115: the stop is clamped to 1.75% from the trigger and the plan issues.
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    item = _item()
    engine.attach_plan_v2(item, _gc_scenario(), make_ohlcv([4194.30] * 60),
                          "GC=F", "4w", level_map=None)
    assert item.plan_v2 is not None
    assert getattr(item, "plan_v2_rejected", None) is None
    assert item.plan_v2.stop_loss == pytest.approx(4194.30 * 1.0175)
    assert planned_loss_pct(item.plan_v2.trigger_price,
                            item.plan_v2.stop_loss) < HARD_MAX_PLANNED_LOSS_PCT


def test_attach_plan_v2_issues_a_four_percent_stop_at_one_seventy_five(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    item = _item()
    scenario = SimpleNamespace(direction="bullish", entry=100.0, stop_loss=96.0,
                               take_profit=104.0, target_sources=["EMA21"],
                               stop_sources=["Rolling support"])
    engine.attach_plan_v2(item, scenario, make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=None)
    assert item.plan_v2 is not None
    assert getattr(item, "plan_v2_rejected", None) is None
    assert item.plan_v2.stop_loss == pytest.approx(98.25)
    assert item.plan_v2.tp1 == pytest.approx(104.0)


def test_attach_plan_v2_still_rejects_beyond_the_cap_when_the_clamp_is_off(monkeypatch):
    # The f01e87e2 safety net is unchanged: with the clamp off, the 2.01% GC=F
    # plan builds (tp 4066.11 is 1.52R) and is rejected as risk_cap.
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    item = _item()
    engine.attach_plan_v2(item, _gc_scenario(), make_ohlcv([4194.30] * 60),
                          "GC=F", "4w", level_map=None)
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "risk_cap"
```

Leave `test_attach_plan_v2_keeps_a_plan_exactly_at_the_hard_cap` as it is. Its 2.0% stop is within the cap, so it is untouched.

- [ ] **Step 8: Pin the flag off in the three pre-v115-geometry tests**

In `tests/planning/test_build_confluence_plan.py`, add `from swingbot import config` to the imports and this fixture right after the imports:

```python
@pytest.fixture(autouse=True)
def _unclamped_stops(monkeypatch):
    # These tests pin target selection against the scenario's OWN risk (4%
    # stops). v115's CLAMP_STOP_TO_HARD_CAP would first move those stops to
    # 1.75%; the clamp has its own tests in tests/planning/test_confluence_stop_clamp.py.
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
```

In `tests/backtesting/test_v74_no_behaviour_change.py`, add `from swingbot import config` to the imports. Change the test to take `monkeypatch`, and add this as its first statement:

```python
def test_from_config_reproduces_pre_v74_golden_plans(monkeypatch):
    # The golden file is pre-v74 replay output, which predates v115's stop
    # clamp; the clamp is covered by tests/planning/test_confluence_stop_clamp.py.
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
```

(the rest of the body is unchanged).

In `tests/backtesting/test_armed_replay.py`, add `from swingbot import config` to the imports and this fixture right after `CELL = ar.Cell(5, 0.25, 0.10)`:

```python
@pytest.fixture(autouse=True)
def _unclamped_arm_stops(monkeypatch):
    # The arm tests pin pre-v115 stop geometry (97.5 = 2.11% from a 99.6
    # trigger; a re-anchored stop >= the 2.0 floor). v115's CLAMP_STOP_TO_HARD_CAP
    # would move those stops to 1.75%; the clamp has its own tests.
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
```

- [ ] **Step 9: Run every file that calls the builder, plus the config parity tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py
python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py
python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python scripts/dev/testrun.py file tests/scanning/test_decision_debug_logs.py
python scripts/dev/testrun.py file tests/backtesting
python scripts/dev/testrun.py file tests/test_v115_flags.py
python scripts/dev/testrun.py file tests/test_env_example_sync.py
```

Expected: all PASS. `test_decision_debug_logs.py::test_a_risk_cap_rejection_is_logged_with_its_reason` stubs the builder with a 50% plan, so it still exercises the safety net unchanged. If any other `tests/backtesting` test fails, check whether the diff is a stop moved to 1.75% from the trigger. If it is, the test pins pre-v115 replay numbers: pin the flag off in that test with the same comment pattern, and report it in the task's review note. Otherwise, debug it as a real regression.

- [ ] **Step 10: Complexity check**

Run: `python -m radon cc -s swingbot/core/planning/builders.py | grep -E "build_confluence_plan|_clamp_stop_to_hard_cap|_stop_is_clampable"`
Expected (dry-run figures): `build_confluence_plan - C (14)`, unchanged. `_stop_is_clampable - B (6)`. `_clamp_stop_to_hard_cap - A (4)`. Anything under 15 passes. If `build_confluence_plan` shows 15, a branch was added inline: move it into a helper.

- [ ] **Step 11: Commit** (three commits: the behaviour, the wording fix, then the pre-v115 pins)

```bash
git add swingbot/core/planning/builders.py tests/planning/test_confluence_stop_clamp.py tests/scanning/test_engine_v2_plans.py
git commit -m "feat(v115): clamp a confluence stop beyond the 2% cap to 1.75% (0.25% headroom) before target selection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add swingbot/config.py .env.example
git commit -m "docs(v115): CLAMP_STOP_TO_HARD_CAP help and .env.example say 1.75%, not exactly 2%

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add tests/planning/test_build_confluence_plan.py tests/backtesting/test_v74_no_behaviour_change.py tests/backtesting/test_armed_replay.py
git commit -m "test(v115): pin CLAMP_STOP_TO_HARD_CAP off where a test asserts pre-v115 stop geometry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V115-04: Futures/FX/index liquidity exemption behind `LIQUIDITY_EXEMPT_NON_EQUITY`; v109 spot metals always exempt

**Files:**
- Modify: `swingbot/core/marketdata/universe.py` (new helper after `_volume_is_not_shares`, lines 22-24; `liquidity_reason`, lines 39-57)
- Test: `tests/marketdata/test_universe.py` (the parametrized exemption test at lines 32-39, plus new tests)

**Interfaces:**
- Consumes: `config.LIQUIDITY_EXEMPT_NON_EQUITY: bool` (V115-02). `swingbot.core.marketdata.spot_metals.is_spot_metal(symbol) -> bool` and `SPOT_PAIRS: dict[str, tuple[str, str]]` (today `{"XAUUSD": ("XAU", "GC=F"), "XAGUSD": ("XAG", "SI=F")}`). v109 names `SPOT_PAIRS` "the single source of truth", and `asset_class.classify` returns `"spot_metal"` through `is_spot_metal`.
- Produces: `universe._dollar_volume_exempt(symbol: str | None) -> bool`. `liquidity_reason(df, min_avg_dollar_vol=None, min_price=None, symbol=None)` keeps its signature. A spot metal skips the dollar-volume floor whatever the flag says. Futures, FX and indices skip it only while the flag is on.

Partner decision (2026-09-30, after the spec's first approval): keep the v109 spot metals exempt with the flag off, and filter futures, FX and indices again, as on 09-22. The spot-metal set comes from `spot_metals.is_spot_metal`, never a hand-written list. A new `SPOT_PAIRS` entry is exempt without touching this code.

- [ ] **Step 1: Write the failing tests.** In `tests/marketdata/test_universe.py`, add `from swingbot import config` and `from swingbot.core.marketdata.spot_metals import SPOT_PAIRS` to the imports. Change the existing parametrized test so that it sets the flag on:

```python
@pytest.mark.parametrize("symbol", ["SI=F", "XAGUSD", "XAUUSD", "GC=F", "EURUSD=X", "^GSPC"])
def test_non_share_symbols_skip_the_dollar_volume_floor(symbol, monkeypatch):
    # Production 2026-09-28: SI=F read as $0.1M/day and was skipped every
    # scan. Yahoo reports futures volume in contracts (5,000 oz each) and FX
    # volume as 0, so Close x Volume says nothing about these markets.
    # v115: futures/FX/indices are exempt only while LIQUIDITY_EXEMPT_NON_EQUITY is on.
    monkeypatch.setattr(config, "LIQUIDITY_EXEMPT_NON_EQUITY", True)
    from swingbot.core.marketdata.universe import liquidity_reason
    df = make_ohlcv(np.full(60, 61.5), volumes=np.full(60, 1_400.0))
    assert liquidity_reason(df, symbol=symbol) is None
```

Add after it:

```python
@pytest.mark.parametrize("symbol", ["SI=F", "GC=F", "EURUSD=X", "^GSPC"])
def test_flag_off_puts_futures_fx_and_indices_back_under_the_floor(symbol, monkeypatch):
    # v115 default: the 09-22 behaviour for futures/FX/indices.
    monkeypatch.setattr(config, "LIQUIDITY_EXEMPT_NON_EQUITY", False)
    from swingbot.core.marketdata.universe import liquidity_reason
    df = make_ohlcv(np.full(60, 61.5), volumes=np.full(60, 1_400.0))
    assert "avg dollar vol" in liquidity_reason(df, symbol=symbol)


def test_the_spot_metal_set_is_v109s_and_holds_gold_and_silver():
    assert {"XAUUSD", "XAGUSD"} <= set(SPOT_PAIRS)


@pytest.mark.parametrize("symbol", sorted(SPOT_PAIRS))
def test_flag_off_keeps_every_v109_spot_metal_exempt(symbol, monkeypatch):
    # Partner decision 2026-09-30: spot metals carry their future's contract
    # volume, so the floor would silently drop the v109 feature. Derived from
    # spot_metals.SPOT_PAIRS, v109's single source of truth.
    monkeypatch.setattr(config, "LIQUIDITY_EXEMPT_NON_EQUITY", False)
    from swingbot.core.marketdata.universe import liquidity_reason
    df = make_ohlcv(np.full(60, 61.5), volumes=np.full(60, 1_400.0))
    assert liquidity_reason(df, symbol=symbol) is None


def test_flag_off_spot_metals_pass_where_their_futures_do_not(monkeypatch):
    # The same thin volume: XAUUSD/XAGUSD pass, GC=F/SI=F (their underlyings) do not.
    monkeypatch.setattr(config, "LIQUIDITY_EXEMPT_NON_EQUITY", False)
    from swingbot.core.marketdata.universe import liquidity_reason
    df = make_ohlcv(np.full(60, 61.5), volumes=np.full(60, 1_400.0))
    assert liquidity_reason(df, symbol="XAUUSD") is None
    assert liquidity_reason(df, symbol="XAGUSD") is None
    assert "avg dollar vol" in liquidity_reason(df, symbol="GC=F")
    assert "avg dollar vol" in liquidity_reason(df, symbol="SI=F")


def test_flag_on_still_floors_shares(monkeypatch):
    monkeypatch.setattr(config, "LIQUIDITY_EXEMPT_NON_EQUITY", True)
    from swingbot.core.marketdata.universe import liquidity_reason
    df = make_ohlcv(np.full(60, 30.0), volumes=np.full(60, 100_000.0))
    assert "avg dollar vol" in liquidity_reason(df, symbol="THIN")
```

Leave `test_spot_metal_class_is_volume_exempt`, `test_spot_metals_still_need_history_and_price`, `test_symbol_aware_floor_still_applies_to_shares` and `test_non_share_symbols_still_need_history_and_price` unchanged. They hold under either flag value. `_VOLUME_NOT_SHARES` keeps `"spot_metal"`, and the flag-on path still uses it.

- [ ] **Step 2: Run to verify the right tests fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_universe.py`
Expected: FAIL, 5 failed (checked in a dry run). The four `test_flag_off_puts_futures_fx_and_indices_back_under_the_floor` cases fail with `TypeError: argument of type 'NoneType' is not iterable`, and `test_flag_off_spot_metals_pass_where_their_futures_do_not` fails on its `GC=F` line. The exemption is still unconditional. The `test_flag_off_keeps_every_v109_spot_metal_exempt` cases already pass: they pin behaviour this task must not break.

- [ ] **Step 3: Implement.** In `swingbot/core/marketdata/universe.py`, add directly after `_volume_is_not_shares`:

```python
def _dollar_volume_exempt(symbol: str | None) -> bool:
    """v115: which symbols skip the dollar-volume floor. v109 spot metals
    (spot_metals.SPOT_PAIRS, the single source of truth) always do: their bars
    carry the future's contract volume, and the partner kept them scanning
    (2026-09-30). 4a649b36's futures/FX/index exemption applies only while
    LIQUIDITY_EXEMPT_NON_EQUITY is on (default off = the 09-22 floor)."""
    if symbol is None:
        return False
    from swingbot.core.marketdata.spot_metals import is_spot_metal
    if is_spot_metal(symbol):
        return True
    return bool(config.LIQUIDITY_EXEMPT_NON_EQUITY) and _volume_is_not_shares(symbol)
```

In `liquidity_reason`, replace

```python
    if symbol is not None and _volume_is_not_shares(symbol):
        return None
```

with

```python
    if _dollar_volume_exempt(symbol):
        return None
```

and change its docstring's second sentence to: `Passing `symbol` always exempts v109 spot metals from the dollar-volume floor, and exempts futures/FX/indices only while LIQUIDITY_EXEMPT_NON_EQUITY is on (v115; default off).`

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_universe.py`
Expected: PASS.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s swingbot/core/marketdata/universe.py | grep -E "liquidity_reason|_dollar_volume_exempt"`
Expected (dry-run figures): `liquidity_reason - B (8)` (it was 9, and one `and` moved out) and `_dollar_volume_exempt - A (4)`. Anything under 15 passes.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/marketdata/universe.py tests/marketdata/test_universe.py
git commit -m "feat(v115): futures/FX/index dollar-volume exemption behind LIQUIDITY_EXEMPT_NON_EQUITY (default off); v109 spot metals stay exempt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V115-05: Guaranteed-off test for the § Strategy work table

**Files:**
- Test: `tests/test_v115_strategy_work_off.py` (create)

**Interfaces:**
- Consumes: symbols that exist today (verified 2026-09-30 by `git grep`). `config.FIELDS` and `config._cast` (`swingbot/config.py`). The `ADAPTIVE_RUNNER_TRAIL_ENABLED`, `DATA_DRIVEN_STOPS_ENABLED`, `STALL_EXIT_ENABLED`, `FIB_LEVEL_STOP_ATR`, `FIB_LEVEL_STOP_DIRECTIONS` and `STRUCTURAL_STOP_SCOPE` Fields. `strategy_types.STRATEGY_GATES`, `admits`, `HORIZONS`, `MASKED_BY_DEFAULT_HORIZONS`, `LEGACY_HORIZONS`, `live_horizons`, `V104_SHORTS` (= `("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")`) and `FADE_STRATEGY` (= `"Downtrend Overbought Fade"`), all in `swingbot/core/market/strategy_types.py`. `entry_filters.DEFAULT_PARAMS["EMA Crossover"]` (`swingbot/core/market/entry_filters.py:430-445`). `scan_run.LEGACY_HORIZONS` (`swingbot/core/scanning/scan_run.py:26,307`).
- Produces: nothing other tasks consume.

This test has nothing to turn red first. It pins values that are already off (V115-01 Step 2 and the plan author's `git grep` confirmed each one). Its value is that a later change which switches one on fails here, with the spec named in the message. Step 2 proves that the test can fail.

- [ ] **Step 1: Write the test** at `tests/test_v115_strategy_work_off.py`

```python
"""v115 § Strategy work: the post-09-22 strategy work (v92, v103, v104, v108,
v113) closed no-lift or ships default-off, and must STAY off -- at the code
default and in .env.example -- so a later change cannot silently switch one on.
Spec: docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md"""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.market import strategy_types as st
from swingbot.core.market.entry_filters import DEFAULT_PARAMS
from swingbot.core.scanning import scan_run

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
WHY = "must stay off (v115 § Strategy work)"

FLAGS_OFF = [
    ("v92", "ADAPTIVE_RUNNER_TRAIL_ENABLED", False),
    ("v92", "DATA_DRIVEN_STOPS_ENABLED", False),
    ("v92", "STALL_EXIT_ENABLED", False),
    ("v103", "FIB_LEVEL_STOP_ATR", 0.0),
    ("v103", "FIB_LEVEL_STOP_DIRECTIONS", ""),
    ("v104", "STRUCTURAL_STOP_SCOPE", ""),
]

MASKED_STRATEGIES = [
    ("v103", "Fibonacci Continuation"),
    ("v104", "Bull Trap"),
    ("v104", "Vol Expansion Breakdown"),
    ("v104", "Earnings Gap Drift"),
    ("v113", "Downtrend Overbought Fade"),
]


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


@pytest.mark.parametrize("spec,key,off", FLAGS_OFF)
def test_flag_code_default_is_off(spec, key, off):
    value = config._cast(_field(key), _field(key).default)
    assert value == off, f"{spec}: {key} code default is {value!r}, {WHY}: {off!r}"


@pytest.mark.parametrize("spec,key,off", FLAGS_OFF)
def test_flag_in_env_example_is_off(spec, key, off):
    raw = dotenv_values(ENV_EXAMPLE).get(key)
    assert raw is not None, f"{spec}: {key} is missing from .env.example, {WHY}"
    value = config._cast(_field(key), raw)
    assert value == off, f"{spec}: .env.example ships {key}={raw!r}, {WHY}: {off!r}"


def test_the_masked_names_are_the_real_strategy_names():
    assert st.V104_SHORTS == ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift"), \
        "v104: the short-strategy names changed -- update MASKED_STRATEGIES here"
    assert st.FADE_STRATEGY == "Downtrend Overbought Fade", \
        "v113: the fade strategy's name changed -- update MASKED_STRATEGIES here"


@pytest.mark.parametrize("spec,name", MASKED_STRATEGIES)
def test_masked_strategy_admits_no_direction_and_no_horizon(spec, name):
    gates = st.STRATEGY_GATES.get(name)
    assert gates is not None and gates.get("directions") == (), \
        f"{spec}: STRATEGY_GATES[{name!r}] = {gates!r}, {WHY}: directions=()"
    admitted = [(d, hk) for d in ("bullish", "bearish") for hk in st.HORIZONS
                if st.admits(name, d, hk)]
    assert admitted == [], f"{spec}: {name!r} admits {admitted}, {WHY}"


def test_v108_ema_crossover_takes_the_first_touch_only():
    p = DEFAULT_PARAMS["EMA Crossover"]
    assert (p["max_touches_bull"], p["max_touches_bear"]) == (1, 1), \
        f"v108: EMA Crossover max_touches = {p['max_touches_bull']}/{p['max_touches_bear']}, {WHY}: 1/1"


def test_v113_one_week_horizon_stays_masked():
    assert "1w" in st.MASKED_BY_DEFAULT_HORIZONS, f"v113: 1w left MASKED_BY_DEFAULT_HORIZONS, {WHY}"
    cells = {k: g["cells"] for k, g in st.STRATEGY_GATES.items() if g.get("cells")}
    assert cells == {}, f"v113: STRATEGY_GATES cells {cells} admit a masked horizon, {WHY}"
    assert "1w" not in st.live_horizons(), f"v113: 1w is a live strategy horizon, {WHY}"


def test_v113_confluence_scan_skips_one_week():
    assert "1w" not in st.LEGACY_HORIZONS, f"v113: 1w is in LEGACY_HORIZONS, {WHY}"
    assert "1w" not in scan_run.LEGACY_HORIZONS, \
        f"v113: the confluence scan (scan_run) iterates 1w, {WHY}"
```

- [ ] **Step 2: Prove it can fail, then restore.** Temporarily edit `.env.example` so that it reads `STALL_EXIT_ENABLED=true`.

Run: `python scripts/dev/testrun.py file tests/test_v115_strategy_work_off.py`
Expected: exactly one FAIL, `test_flag_in_env_example_is_off[v92-STALL_EXIT_ENABLED-False]`, with a message naming `v92`. Restore `STALL_EXIT_ENABLED=false`, then confirm `git diff --stat .env.example` is empty. (If V115-02 is running in parallel and has already edited `.env.example`, make this temporary edit in a scratch copy instead: set `ENV_EXAMPLE` to point at it for this one run, then revert that line.)

- [ ] **Step 3: Run it green**

Run: `python scripts/dev/testrun.py file tests/test_v115_strategy_work_off.py`
Expected: PASS (21 tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_v115_strategy_work_off.py
git commit -m "test(v115): pin v92/v103/v104/v108/v113 strategy work off at code default and in .env.example

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V115-06: known-traps.md and its Codex mirror

**Files:**
- Modify: `docs/claude/known-traps.md` (replace the whole `## Stop floor and 2% cap leave an empty band (2026-09-30)` section at lines 311-318; append one new section at the end of the file)
- Modify: `AGENTS.md` (the `known-traps.md` bullet in "Read before acting", lines 158-159)

**Interfaces:**
- Consumes: the flag names from V115-02 and the behaviour from V115-03/V115-04.
- Produces: the doc text V115-07 Step 12 completes with the production date.

The backtest harness **does** call `build_confluence_plan`: `swingbot/core/backtesting/backtest_scenarios.py:145` (`replay_scenarios`) and `swingbot/core/backtesting/armed_replay.py:189` (`plan_at`). So the clamp creates no live-versus-backtest gap. What changes is comparability with replay numbers from before v115, and that is what the note records.

- [ ] **Step 1: Replace the section.** The new text for the whole `## Stop floor and 2% cap leave an empty band (2026-09-30)` section (heading included):

```markdown
## Stop floor and 2% cap: the empty band, and the v115 clamp

`f01e87e2` rejects any plan with a stop over 2% (`risk_cap` in
`attach_plan_v2`). With `MIN_STOP_DISTANCE_PCT` >= 2.0, only a stop of exactly
2.0% survived, and production posted nothing from Sep 25 to Sep 30. A replay
on live data gave 0 setups at a 2.0 or 1.5 floor and 10 at 1.0, so production
ran 1.0 as a stopgap on 2026-09-30.

**v115 (`CLAMP_STOP_TO_HARD_CAP`, default on)** moves a wider confluence stop
to **1.75%** from the trigger inside `build_confluence_plan`, before target
selection. That is the 2% cap minus `CLAMP_HEADROOM_PCT` (0.25, a constant in
`builders.py`). The floor is back at 2.0 (production returns to it when v115
deploys). The `risk_cap` reject in `attach_plan_v2` stays as a safety net.

- **Why 1.75, not 2.0.** `plan_manager._step_pending` cancels a stop-entry
  fill `risk_cap` when `planned_loss_pct(fill, stop) > 2.0`, with no
  tolerance. A stop at exactly 2% is cancelled on any fill past the trigger,
  and float rounding alone tips about half of such stops over the cap.
  0.25% of headroom absorbs a small gap. A fill more than about 0.25% past
  the trigger is still cancelled `risk_cap`: that is the 2% policy working,
  not a bug.

- **With the clamp off, the empty band comes back.** A funnel of "N checked ->
  N no entry point" or a run of `risk_cap` rejects is this band, not a data
  fault.
- **Replay clamps by default.** `replay_scenarios` and `armed_replay.plan_at`
  call `build_confluence_plan`. Confluence replay numbers produced before
  v115 used the unclamped stop and are not comparable to later ones. To
  reproduce them, set `CLAMP_STOP_TO_HARD_CAP=false`. The backtest has no
  fill guard, so it never models a gap cancel: live can cancel a clamped
  plan that replay fills.
- `armed_replay.plan_at` stores the scenario's **unclamped**
  `stop_distance_pct` while its plan carries the clamped stop. Read the stop
  off the plan, never off that field. This is known and deliberately left
  unchanged.
- A clamped stop sits at no structural level. It reaches an alert only with
  `PLAN_ENGINE_V2=on`; in `shadow`, the scenario's unclamped stop is what
  posts. With `on` and a priced v2 plan, every stop number in the alert comes
  from the clamped plan: plan table, chart, ticket, headline stop % and R,
  the "If it gets there" line and `explain.py`. An alert showing two
  different stops is a regression. Target text and target % still come from
  the scenario, as they have since v31.
- v114 (a 1.5-2.0 band, measured before shipping) was abandoned before any
  build on 2026-09-30 (`no-lift/`), with its VALIDATION shot unspent. It is
  still the measured route if the partner later wants the band instead of
  the clamp.
```

- [ ] **Step 2: Append a new section** at the end of `docs/claude/known-traps.md`:

```markdown
## Futures skipped for dollar volume is deliberate (v115)

`SI=F: skipping new-signal scan -- avg dollar vol $0.1M < $20M floor` is the
configured behaviour, not a bug. Yahoo reports futures volume in contracts and
FX/index volume as 0. `4a649b36` exempted those classes. v115 put that
exemption behind `LIQUIDITY_EXEMPT_NON_EQUITY`, default **off**, to restore
the 09-22 scan. Turn it on to scan thin-contract futures again. The v109 spot
metals (`spot_metals.SPOT_PAIRS`: XAUUSD, XAGUSD) stay exempt either way
(partner, 2026-09-30). They carry their future's contract volume, so XAGUSD
scans while SI=F, on the same bars, is skipped. That is by design.
```

- [ ] **Step 3: Update the Codex mirror.** In `AGENTS.md`, replace

```
- `docs/claude/known-traps.md` before changing data caching, scan output or
  embeds.
```

with

```
- `docs/claude/known-traps.md` before changing data caching, scan output,
  embeds, the 2% stop cap/clamp or the liquidity floor, or editing production
  `.env` (edit in place, never `sed -i`).
```

- [ ] **Step 4: Check the mirror test**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS. It checks the skills/agents/hooks sync, and none of those changed. The AGENTS.md edit is the condensed mirror that `working-conventions.md` § Codex mirror requires for a `docs/claude/` change.

- [ ] **Step 5: Commit** (the docs/claude change and its mirror go in one commit)

```bash
git add docs/claude/known-traps.md AGENTS.md
git commit -m "docs(v115): known-traps -- the stop clamp ends the empty band; futures liquidity skip is deliberate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# Phase B — Verify, release, production

### Task V115-07: Full suite, release, deploy, production `.env`, mirror, close-out

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json` (release)
- Modify on production: `/opt/swing-bot/.env` (in place)
- Modify: `docs/claude/known-traps.md` (the production date, Step 12)
- Scratchpad: `v115_read_config.py` (from V115-01) and `v115_set_env.sh` (new)

**Interfaces:**
- Consumes: everything from V115-02..06. The V115-01 production snapshot (which § Strategy work keys differ).
- Produces: the bot minor release on `main`, the v115 image running on production, and the production `.env` holding `MIN_STOP_DISTANCE_PCT=2.0` and every § Strategy work value.

- [ ] **Step 1: Full suite, once** (dispatch the `test-runner` subagent from the worktree root)

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. **If it is not green, fix forward from the failures it names.** They are this plan's regressions. The typical case is another builder caller asserting a pre-v115 stop: apply the V115-03 Step 8 rule. Re-run only the failing files with `testrun.py file` until each is green, then run `full` once more. Frontend is untouched, so there is no `npm test`.

- [ ] **Step 2: Complexity sweep over every touched Python file**

Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/marketdata/universe.py swingbot/config.py`
Expected: `build_confluence_plan` still at `C (14)`. No other function that this plan wrote or changed is listed. Pre-existing C+ entries in those files are fine if their score did not rise.

- [ ] **Step 3: Merge the branch to `main`** (use the `worktree-lifecycle` skill; another session may share `main`)

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git fetch origin && git status -sb && git log --oneline -5
git merge --no-ff 2026-09-30-v115-restore-sep22-issuance -m "merge(v115): restore pre-09-23 issuance -- clamp wide stops to 1.75%, floor 2.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If the merge resolved conflicts, run `python scripts/dev/testrun.py full` once more on `main`. Otherwise do not re-run.

- [ ] **Step 4: Release commit, then the regeneration commit** (`docs/claude/working-conventions.md` § Versioning)

Read `VERSION.json` from disk now (not from this plan). Increment `bot` at **minor** (`X.Y.Z` -> `X.(Y+1).0`). Leave `ui` untouched. Set `bot_updated` to the current UTC time in `YYYY-MM-DD HH-MM-SS`. Then:

```bash
git add VERSION.json
git commit -m "release(bot): <new version> -- setups with a stop wider than 2% issue again, clamped to 1.75%; stop floor back to 2.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new version> -- setups with a stop wider than 2% issue again, clamped to 1.75%; stop floor back to 2.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: the version-matrix test PASSES.

- [ ] **Step 5: Deploy.** Ask the partner (`AskUserQuestion`, recommended option first: "Push `main` now; push-to-deploy ships v115"), because a push to `main` deploys to production (`docs/deploy/DEPLOY_HETZNER.md`). On yes, run `git push origin main` and watch the "Deploy to Hetzner" workflow until it finishes (`gh run watch`).

- [ ] **Step 6: Confirm that the v115 image is live (read-only)**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <scratchpad>/v115_read_config.py
```

Expected: `CLAMP_STOP_TO_HARD_CAP = True`, `LIQUIDITY_EXEMPT_NON_EQUITY = False`, `PLAN_ENGINE_V2 = 'on'`. If either flag still reads `<absent: pre-v115 image>`, the deploy has not landed: **stop, and do not touch `.env`**. Record the § Strategy work lines again, and re-derive the list of differing keys (it may have changed since V115-01).

- [ ] **Step 7: Write the in-place edit script** to `<scratchpad>/v115_set_env.sh`. Add one `set_key` line for every § Strategy work key that Step 6 showed differing from the spec's table. Table values: `ADAPTIVE_RUNNER_TRAIL_ENABLED false`, `DATA_DRIVEN_STOPS_ENABLED false`, `STALL_EXIT_ENABLED false`, `FIB_LEVEL_STOP_ATR 0.0`, `FIB_LEVEL_STOP_DIRECTIONS ""`, `STRUCTURAL_STOP_SCOPE ""`. Leave `SIGNAL_CONFIRMATION_SCANS` alone.

```bash
set -euo pipefail
cd /opt/swing-bot
cp -p .env ".env.bak-v115-$(date -u +%Y%m%dT%H%M%SZ)"
set_key() {
  awk -v k="$1" -v v="$2" 'BEGIN { FS = "=" }
    $1 == k { print k "=" v; found = 1; next }
    { print }
    END { if (!found) print k "=" v }' .env > /tmp/env.v115
  cat /tmp/env.v115 > .env   # in place: same inode, so the bind mount sees it (never sed -i)
}
set_key MIN_STOP_DISTANCE_PCT 2.0
# one set_key line per differing § Strategy work key from Step 6, for example:
#   set_key STALL_EXIT_ENABLED false
rm -f /tmp/env.v115
grep -nE '^(MIN_STOP_DISTANCE_PCT|SIGNAL_CONFIRMATION_SCANS)=' .env
```

- [ ] **Step 8: Apply it**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "bash -s" < <scratchpad>/v115_set_env.sh
```

Expected output: `MIN_STOP_DISTANCE_PCT=2.0` and `SIGNAL_CONFIRMATION_SCANS=1`.

- [ ] **Step 9: Reload the bot (SIGHUP) and verify**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose kill -s HUP bot"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot grep -E '^(MIN_STOP_DISTANCE_PCT|SIGNAL_CONFIRMATION_SCANS)=' /app/.env"
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "grep -n 'MIN_STOP_DISTANCE_PCT' /opt/swing-bot/logs/bot.log | tail -3"
```

Expected: the container's `/app/.env` shows `2.0` and `1`, and `bot.log` has a `MIN_STOP_DISTANCE_PCT: 1.0 -> 2.0` reload line. If the container still reads `1.0`, the bind mount is on an orphaned inode: recreate the containers as `known-traps.md` § "Editing production `.env` with `sed -i`" describes:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && IMG=\$(docker inspect --format '{{.Config.Image}}' \$(docker compose ps -q bot)) && SWING_BOT_IMAGE=\$IMG docker compose up -d --force-recreate --no-build --wait bot admin"
```

Then repeat the `grep` against `/app/.env`.

- [ ] **Step 10: Re-read the effective config**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < <scratchpad>/v115_read_config.py
```

Expected: `MIN_STOP_DISTANCE_PCT = 2.0`, `SIGNAL_CONFIRMATION_SCANS = 1`, `CLAMP_STOP_TO_HARD_CAP = True`, `LIQUIDITY_EXEMPT_NON_EQUITY = False`, and every § Strategy work line at the spec's table value.

- [ ] **Step 11: First-scan sanity check (read-only, during the next in-session scan)**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "grep -nE 'plan rejected -- risk_cap|no_qualifying_target|skipping new-signal scan' /opt/swing-bot/logs/bot.log | tail -20"
```

Expected: no new `risk_cap` rejections after the reload time. Some `no_qualifying_target` lines are normal. For each alert posted after the reload, check its stop against its entry: a clamped plan's stop is **1.75%** from the trigger (`abs(entry - stop) / entry * 100` rounds to 1.75), not 2.0%. An unclamped plan is one whose natural stop was already within the cap; at floor 2.0, that stop is about 2.0%. Any stop above 2.0% means the clamp is not live (re-check Step 6). Open at least one posted alert in Discord and check that it shows **one stop only**: the headline SL price and stop %, the R, the plan table, the "If it gets there" line and the explanation must all agree. Two different stops in one alert is a regression; report it. A `cancelled_risk_cap` on a clamped plan is expected only for a fill more than about 0.25% past the trigger; report any that occur with their `planned_loss_pct`. Illiquid-skip lines for thin futures (for example `SI=F`) are now expected. None should appear for `XAUUSD` or `XAGUSD`. Report what you see to the partner. Tell them it is an unmeasured live change (`Edge: volume`); give no win-rate or expectancy claim.

- [ ] **Step 12: Mirror the production change into the repo and commit** (on `main`; `mirror-prod` skill)

`.env.example` already carries `MIN_STOP_DISTANCE_PCT=2.0` and every § Strategy work value (V115-02, pinned by V115-05). In `docs/claude/known-traps.md`, replace the clause `(production returns to it when v115 deploys)` with `(production back on 2.0 since <UTC date and time of Step 9>)`. If Step 7 reset any § Strategy work key, append the sentence `Production also reset <KEY>=<value>, ... to the § Strategy work values.` to the same paragraph. AGENTS.md carries only the pointer, so it needs no change for this edit.

```bash
git add docs/claude/known-traps.md
git commit -m "ops(v115): production MIN_STOP_DISTANCE_PCT 1.0 -> 2.0 with the stop clamp live; mirrored

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Ask the partner before pushing this commit (a push redeploys).

- [ ] **Step 13: Close out** — run the `close-out` skill (`docs/claude/document-lifecycle.md`). It moves the spec and this plan to `implemented/` and removes the worktree `.claude/worktrees/2026-09-30-v115-restore-sep22-issuance/` and its branch. The branch name has no `backup`. Still, run `git rev-list --count main..2026-09-30-v115-restore-sep22-issuance` before deleting it, and expect `0`.
