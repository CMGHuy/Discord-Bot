# v61 part 3 — `core/planning/plan_engine.py`

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 1419-line `plan_engine.py` into six modules plus a facade,
isolating the exit simulator that the backtest shares.

**Architecture:** ~40 medium functions, no mega-function — this file splits
more cleanly than either earlier part. The prize is `exit_sim.py`: the code
that must stay in lockstep with `backtest.run_backtest(exit_model="v2")` stops
being buried mid-file and becomes the single module to diff when parity is in
question.

**Tech Stack:** Python 3.11+, pandas, pytest. No new dependencies.

**Read first:** `_0-index.md` (Global Constraints C1–C7), plus
`docs/claude/architecture.md` §Plan Engine v2 and
`docs/claude/backtest-methodology.md`.

**Prerequisite:** parts `_1` and `_2` merged.

**Worktree:** `2026-08-25-v61-large-file-decomposition_3-plan-engine`

---

## Why this part is last and alone

`architecture.md` states that `backtesting/backtest.py run_backtest(...,
exit_model="v2", scale_out=True)` uses this file's exit simulator, "so live
behavior equals backtested behavior **by construction**."

That construction is the whole basis on which this bot's validation registry
stamps plans ✅ VALIDATED. A move-bug here does not produce a red test and a
clear stack trace — it produces a bot whose live exits quietly diverge from the
backtest that justified them. Every trade after that is unvalidated.

So this part carries verification the other two do not: a **numerical parity
check** against a real backtest run captured before any code moves.

---

## Global Constraints

All of `_0-index.md`, plus:

**C11 — Parity is the acceptance gate, not the test suite.** Green tests are
necessary and not sufficient. Task 9 compares real backtest output before and
after; a byte-difference in the trade ledger fails this part regardless of what
pytest says.

**C12 — `exit_sim.py` is append-only during this part.** Its bodies move
verbatim and nothing else. No parameter reordering, no default changes, no
extracting a shared helper between `_single_leg_exit_walk` and
`_scale_out_exit_walk` even though they visibly share structure. That
extraction is exactly the kind of "obvious improvement" that breaks parity
subtly, and it is Phase B's business.

**C13 — Frozen constants stay frozen.** `backtest-methodology.md` lists
constants that are pre-registered and must not drift. Anything in `params.py`
that resolves a tunable (`_resolve_stop_mult`, `_resolve_tp2_r`,
`_resolve_time_stop_days`, `exit_params_for`) moves with its defaults
untouched.

---

## Target structure

| Module | Holds (current line) | ~lines |
|---|---|---|
| `plan_types.py` | `PlanStatus` (68), `TradePlanV2` (84), `effective_stop` (143), `plan_to_dict` (150), `plan_from_dict` (157), `record_transition` (1012) | ~140 |
| `targets.py` | `select_structural_target` (165), `_safe_atr_value` (289), `atr_target_candidates` (298), `fib_target_candidates` (463), `sr_target_candidates` (519), `elliott_target_candidates` (571), `select_tp2` (614), `_tp2_from_r` (698) | ~330 |
| `builders.py` | `_atr_plan` (313), `_fibonacci_plan` (492), `_sr_plan` (553), `_elliott_plan` (587), `build_strategy_plan` (719), `scenario_is_breakout` (878), `primary_strategy_for` (903), `build_confluence_plan` (915), `entry_type_for` (987) | ~430 |
| `lifecycle.py` | `_lifecycle_levels` (364), `apply_level_lifecycle` (387), `trigger_hit` (1030), `fill_price` (1041), `pending_expired` (1051), `pending_invalidated` (1058) | ~150 |
| `params.py` | `exit_params_for` (62), `_journal_entries` (645), `_resolve_stop_mult` (654), `_resolve_tp2_r` (671), `_resolve_time_stop_days` (685), `_apply_quality` (855), `stamp_badge` (993), `badge_stats_line` (1006) | ~120 |
| `exit_sim.py` | `ExitResult` (1083), `_not_triggered` (1093), `_single_leg_exit_walk` (1105), `chandelier_stop` (1195), `runner_floor` (1204), `_scale_out_exit_walk` (1224), `simulate_exit` (1355) | ~340 |
| `plan_engine.py` | facade | ~90 |

---

### Task 1: Capture the parity baseline

Nothing moves. This produces the artefact Task 9 compares against, and it must
exist before a single line is touched.

**Files:**
- Create: `.parity/v61-baseline.json` (gitignored working artefact)

- [ ] **Step 1: Confirm the CSV cache is populated**

```bash
ls market_data/ | head -5
```
If empty, run `python scripts/data/fetch_backtest_data.py` first — it needs
network and only has to run once.

- [ ] **Step 2: Capture the baseline**

Dispatch the **`backtest-runner`** subagent (this is a multi-minute job; per
`CLAUDE.md` it must not run in the controlling context):

```bash
python scripts/backtest/run_backtest_range.py --validation \
  --exit-model v2 --scale-out --json .parity/v61-baseline.json
```

- [ ] **Step 3: Record the identifying facts**

In the commit message, record: the exact command, `git rev-parse HEAD`, and
the summary line (trade count, pooled `ExpR`, win rate). Task 9 re-runs the
identical command on the identical data.

- [ ] **Step 4: Re-derive the external surface**

```bash
git grep -ohE "from swingbot\.core\.planning\.plan_engine import [a-zA-Z_, ]+" -- '*.py' | sort -u
git grep -ohE "plan_engine\.[a-zA-Z_]+" -- 'swingbot/' 'scripts/' 'tests/' | sort -u
git grep -nE "setattr\(plan_engine," -- 'tests/'
```

Known from earlier greps: `build_confluence_plan` and `primary_strategy_for`
are imported by `scanning/engine.py`; `_journal_entries` and
`_lifecycle_levels` are monkeypatched by tests and therefore fall under C2.
**The grep is authoritative over this paragraph.**

- [ ] **Step 5: Commit the findings**

```bash
git commit --allow-empty -m "chore(v61): capture plan_engine parity baseline and external surface"
```

---

### Tasks 2–7: the moves

**Shared procedure** — as `_1` Tasks 3–8, with
`HEAD:swingbot/core/planning/plan_engine.py` as the old ref. Leaf-first order
below; each task ends with its own commit.

| Task | Module | Depends on |
|---|---|---|
| 2 | `plan_types.py` | nothing — leaf |
| 3 | `params.py` | `plan_types` |
| 4 | `targets.py` | `plan_types` |
| 5 | `lifecycle.py` | `plan_types` |
| 6 | `exit_sim.py` | `plan_types`, `params` |
| 7 | `builders.py` | all of the above |

**Narrow tests, run after every one of Tasks 2–7:**

```bash
python scripts/dev/testrun.py file tests/planning/test_build_strategy_plan.py
python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py
python scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py
python scripts/dev/testrun.py file tests/backtesting/test_sizing_parity.py
```

The two `parity` files are the fast proxy for Task 9's full check. If either
goes red, stop immediately — do not continue moving and hope the next task
fixes it.

---

### Task 2: `plan_types.py`

**Symbols:** `PlanStatus`, `TradePlanV2`, `effective_stop`, `plan_to_dict`,
`plan_from_dict`, `record_transition`

**Interfaces:**
- Produces: `plan_types.TradePlanV2` (dataclass), `plan_types.PlanStatus`, `plan_types.effective_stop(plan) -> float`, `plan_types.plan_to_dict(plan) -> dict`, `plan_types.plan_from_dict(d: dict) -> TradePlanV2`, `plan_types.record_transition(plan, new_status: str, reason: str | None = None, ...)`.

`plan_to_dict`/`plan_from_dict` are the **persistence contract** for
`data/plans.json`. A field dropped here silently corrupts every stored plan on
the next write. Move both verbatim and confirm
`tests/admin/test_queries_plan_lifecycle.py` passes.

The lifecycle `PENDING → ACTIVE → PARTIAL → CLOSED/CANCELLED` is documented in
`architecture.md`; keep any docstring describing it with `PlanStatus`.

---

### Task 3: `params.py`

**Symbols:** `exit_params_for`, `_journal_entries`, `_resolve_stop_mult`,
`_resolve_tp2_r`, `_resolve_time_stop_days`, `_apply_quality`, `stamp_badge`,
`badge_stats_line`

**Interfaces:**
- Produces: `params.exit_params_for(strategy: str) -> dict`, `params._resolve_stop_mult(strategy) -> float | None`, `params._resolve_tp2_r(strategy) -> float | None`, `params._resolve_time_stop_days(strategy) -> int | None`, `params._journal_entries() -> list`, `params.stamp_badge(plan) -> None`.

**C2 applies to `_journal_entries`** — it is monkeypatched in at least seven
places across `tests/planning/`. Every caller must use
`params._journal_entries()`.

**C13 applies to all four resolvers.** Defaults move untouched.

`stamp_badge` reads `validation_registry.json` via `backtesting/registry.py`.
That file is regenerated only by `run_backtest_range.py --emit-registry` and is
never hand-edited — this move must not touch it.

---

### Task 4: `targets.py`

**Symbols:** `select_structural_target`, `_safe_atr_value`,
`atr_target_candidates`, `fib_target_candidates`, `sr_target_candidates`,
`elliott_target_candidates`, `select_tp2`, `_tp2_from_r`

**Interfaces:**
- Produces: `targets.select_structural_target(entry, stop_loss, is_bull, ...) -> float`, `targets.atr_target_candidates(entry, atr_val, direction) -> list[float]`, `targets.fib_target_candidates(df, index, h, entry) -> list[float]`, `targets.sr_target_candidates(df, index, h, entry, volume_ratio) -> list[float]`, `targets.elliott_target_candidates(entry_level: dict, direction) -> list[float]`, `targets.select_tp2(levels_above: list, levels_below: list, direction: str, ...) -> float`.

Pure geometry — the lowest-risk task in this part.

---

### Task 5: `lifecycle.py`

**Symbols:** `_lifecycle_levels`, `apply_level_lifecycle`, `trigger_hit`,
`fill_price`, `pending_expired`, `pending_invalidated`

**Interfaces:**
- Produces: `lifecycle.apply_level_lifecycle(df, index, *, entry, stop, tp1, atr_val, direction, ...)`, `lifecycle.trigger_hit(plan, bar_high: float, bar_low: float) -> bool`, `lifecycle.fill_price(plan, bar_open: float) -> float`, `lifecycle.pending_expired(plan, bars_since_created: int) -> bool`, `lifecycle.pending_invalidated(plan, bar_close: float) -> bool`.

**C2 applies to `_lifecycle_levels`** — patched in
`tests/market/test_levels_lifecycle_wiring.py`.

`trigger_hit`/`fill_price` are called from the 60s live monitor
(`plan_manager.py`) **and** from the backtest replay. Both paths must keep
resolving to the same function — that identity is what parity means here.

---

### Task 6: `exit_sim.py` — the prize, and the risk

**Symbols, in original order:** `ExitResult`, `_not_triggered`,
`_single_leg_exit_walk`, `chandelier_stop`, `runner_floor`,
`_scale_out_exit_walk`, `simulate_exit`

**Interfaces:**
- Produces: `exit_sim.simulate_exit(...) -> ExitResult`, `exit_sim.ExitResult` (dataclass), `exit_sim.chandelier_stop(extreme_close_since_tp1: float, atr_value: float, ...) -> float`, `exit_sim.runner_floor(entry: float, tp1: float) -> float`.
- Consumes: `plan_types` (Task 2), `params.exit_params_for` (Task 3).

- [ ] **Step 1: Move verbatim, and obey C12**

`_single_leg_exit_walk` and `_scale_out_exit_walk` share visible structure.
**Do not extract a common helper.** They encode TP1-as-win, scale-out banking
50% at TP1, stop-to-break-even, and the chandelier ATR trail on the runner.
Unifying them is a behaviour change wearing a refactor's clothes.

- [ ] **Step 2: Give the module a docstring stating the contract**

```python
"""The v2 exit simulator -- shared, by construction, with the backtest.

backtesting/backtest.py's run_backtest(..., exit_model="v2", scale_out=True)
calls simulate_exit() here, which is what makes live behaviour equal
backtested behaviour (docs/claude/architecture.md, Plan Engine v2). Split out
of plan_engine.py on 2026-08-25 (v61) precisely so that this contract has one
file to diff when parity is in question.

Any change here changes what the validation registry's VALIDATED badges mean.
Re-run scripts/backtest/run_backtest_range.py --validation and compare before
merging one.
"""
```

- [ ] **Step 3: Purity check**

```bash
python scripts/dev/check_move_purity.py \
  HEAD:swingbot/core/planning/plan_engine.py swingbot/core/planning/exit_sim.py \
  ExitResult _not_triggered _single_leg_exit_walk chandelier_stop runner_floor \
  _scale_out_exit_walk simulate_exit
```
Expected: `OK -- 7 symbol(s) moved unchanged`. **Anything else stops this
task.** For every other module a non-pure report is a mistake to fix; here it
is a parity break.

- [ ] **Step 4: The parity proxies must be green**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py
python scripts/dev/testrun.py file tests/edge/test_edge_stops.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py
```

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/exit_sim.py swingbot/core/planning/plan_engine.py
git commit -m "refactor(v61): isolate the v2 exit simulator into exit_sim.py"
```

---

### Task 7: `builders.py`

**Symbols:** `_atr_plan`, `_fibonacci_plan`, `_sr_plan`, `_elliott_plan`,
`build_strategy_plan`, `scenario_is_breakout`, `primary_strategy_for`,
`build_confluence_plan`, `entry_type_for`

**Interfaces:**
- Produces: `builders.build_strategy_plan(df, index, *, ticker, strategy, horizon_key, ...) -> TradePlanV2`, `builders.build_confluence_plan(scenario, df, *, ticker, horizon_key, ...) -> TradePlanV2`, `builders.primary_strategy_for(scenario) -> str`, `builders.scenario_is_breakout(scenario, df) -> bool`, `builders.entry_type_for(strategy: str, source: str) -> str`.
- Consumes: every module from Tasks 2–6.

**External surface:** `build_confluence_plan` and `primary_strategy_for` are
imported by `swingbot/core/scanning/engine.py` (lines 83–84, now its facade).
Both must be re-exported from `plan_engine.py` or part `_2`'s work breaks.

---

### Task 8: Facade and structure guard

**Files:**
- Modify: `swingbot/core/planning/plan_engine.py`
- Create: `tests/planning/test_plan_engine_structure.py`

- [ ] **Step 1: Reduce to a facade with `__all__`**

Reconcile against Task 1 Step 4's grep, not against this plan.

- [ ] **Step 2: Guard test**

```python
# tests/planning/test_plan_engine_structure.py
"""Guards the v61 split of plan_engine.py."""
import ast
import pathlib

from swingbot.core.planning import plan_engine

PKG = pathlib.Path(plan_engine.__file__).parent


def test_every_exported_name_resolves():
    for name in plan_engine.__all__:
        assert getattr(plan_engine, name, None) is not None, f"{name} exported but missing"


def test_scanning_still_gets_what_it_imports():
    """scanning/engine.py imports these two by name -- part _2 depends on it."""
    assert plan_engine.build_confluence_plan is not None
    assert plan_engine.primary_strategy_for is not None


def test_backtest_and_live_share_one_simulator():
    """The parity contract: both paths must reach the same function object."""
    from swingbot.core.backtesting import backtest
    from swingbot.core.planning import exit_sim
    assert backtest.simulate_exit is exit_sim.simulate_exit


def test_no_submodule_imports_the_facade():
    offenders = []
    for path in PKG.glob("*.py"):
        if path.name == "plan_engine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                a.name == "plan_engine" for a in node.names
            ):
                offenders.append(path.name)
    assert offenders == [], f"import cycle risk: {offenders}"
```

`test_backtest_and_live_share_one_simulator` is the most valuable test in this
plan. It converts "live equals backtested by construction" from a paragraph in
`architecture.md` into something CI enforces. If `backtest.py` imports
`simulate_exit` by a path that no longer resolves to `exit_sim`'s object, this
fails — which is exactly the silent divergence this part exists to prevent.

Adjust the import in that test to however `backtest.py` actually reaches the
simulator (Task 1's grep shows it); the assertion of object identity is the
point, not the spelling.

- [ ] **Step 3: Run and commit**

---

### Task 9: Parity verification and close-out

- [ ] **Step 1: Full suite via subagent**

Dispatch `test-runner`: `python scripts/dev/testrun.py full`.
Expected: `0 failed, 0 xfailed`.

- [ ] **Step 2: Re-run the backtest, identically**

Dispatch `backtest-runner` with the **exact** command from Task 1:

```bash
python scripts/backtest/run_backtest_range.py --validation \
  --exit-model v2 --scale-out --json .parity/v61-after.json
```

- [ ] **Step 3: Compare**

```bash
python -c "
import json
a = json.load(open('.parity/v61-baseline.json'))
b = json.load(open('.parity/v61-after.json'))
print('IDENTICAL' if a == b else 'DIVERGED')
"
```

**Expected: `IDENTICAL`.** This is the acceptance gate for the whole part
(C11).

If it prints `DIVERGED`, the refactor changed behaviour. Do not merge, do not
rationalise it as noise, and do not "re-run to see". Bisect the six move
commits — `check_move_purity.py` against each will usually name the file
immediately. A diverged ledger with green tests is precisely the failure this
part was ordered last to catch.

- [ ] **Step 4: Confirm the shape**

```bash
wc -l swingbot/core/planning/*.py
```
Expected: `plan_engine.py` under ~90 lines, no module over ~450.

- [ ] **Step 5: Close out the program**

Merge to `main` and remove the worktree and branch. Then, per
`docs/claude/document-lifecycle.md`, `git mv` **all four v61 plan files and the
v61 spec** into `implemented/` as part of the closing commit — the top level of
`plans/` and `specs/` must show only live work.

Record in that commit message: the final `wc -l` for all three split packages,
and the parity result. Those two facts are what a future session needs to know
this landed correctly.

Do not bump `VERSION.json` — this program produced no observable difference,
which is the test `working-conventions.md` sets for a bump.
