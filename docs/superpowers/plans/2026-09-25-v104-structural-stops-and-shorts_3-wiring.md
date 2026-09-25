# v104 Part 3 — Wiring (passes only), documentation, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-25-v104-structural-stops-and-shorts_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §6

---

### Task V104-19: Wire what passed

Do only the blocks whose candidate has a scored `PASS` in `results/<date>-v104-holdout.md`. With no pass at all, skip to V104-20.

Work on a short branch/worktree named `2026-09-25-v104-structural-stops-and-shorts-wiring` (`worktree-lifecycle` skill). Iterate with `testrun.py file`, then run `testrun.py fast` once at the end.

**Part A passed (≥ 1 cell):**

- [ ] **A0: Production sizing precheck (read-only; real money).** Every in-scope plan needs risk-based sizing, or V104-5's fail-closed guard silently blocks it. Read the production account's sizing mode without changing anything: `scripts/ops/ssh-hetzner.sh "grep -o '\"sizing_mode\": *\"[a-z_]*\"' /opt/swing-bot/data/account.json"`. If the file lives elsewhere, find it read-only (`docs/deploy/DEPLOY_HETZNER.md` names the data mount).
  - If the mode is `account_pct`, **stop and ask the partner** (`AskUserQuestion`) whether to switch to risk sizing (`!account sizing risk`) before the scope ships. Never change production from this task (`mirror-prod`).
  - Any other mode resolves to risk-based sizing and passes.

- [ ] **A1: Default the scope.** In `swingbot/config.py`, set the `STRUCTURAL_STOP_SCOPE` Field's `default` to the passing pairs, comma-joined in `PART_A` order (e.g. `"Fibonacci:bullish,Support/Resistance:bullish"`). Prefix its help with `Validated in v104 (<date>): <pairs>, Tier <t> each. `. Set the same value in `.env.example`.

- [ ] **A2: Pin the parity witnesses off.** The sizing-parity harness compares against a frozen pre-v31 copy, and structural stops are a deliberate change:
  - In `tests/backtesting/test_sizing_parity.py`, inside `_lifecycle_off`, directly after its `LEVEL_LIFECYCLE_STOPS_ENABLED` `monkeypatch.setattr(...)`, add:

```python
    # v104 structural stops change sizing on purpose; the frozen side predates them.
    monkeypatch.setattr("swingbot.config.STRUCTURAL_STOP_SCOPE", "", raising=False)
```

  - In `scripts/reports/parity_sizing.py` `main()`, directly after `config.LEVEL_LIFECYCLE_STOPS_ENABLED = False`, add `config.STRUCTURAL_STOP_SCOPE = ""  # v104: frozen side predates structural stops`.

- [ ] **A3: Tests that assert today's capped stop.** Run `python scripts/dev/testrun.py fast`. For each failure that names a stop or plan of a now-in-scope strategy:
  - If it is a frozen **no-behaviour-change witness** (its docstring says it pins a pre-change result), pin `STRUCTURAL_STOP_SCOPE` to `""` with `monkeypatch` and a one-line reason.
  - Otherwise it asserts production behaviour: update the expected stop to what `stop_scope.stop_ceiling` implies, computed in the test, not hard-coded.

  Never loosen an assertion or add an `xfail`. If the category is unclear, stop and ask.

- [ ] **A4: Pin test.** Append to `tests/planning/test_stop_scope.py`:

```python
def test_v104_validated_scope_default():
    assert config.STRUCTURAL_STOP_SCOPE == "<the exact A1 value>"
```

- [ ] **A5: Registry.** Group the passing Part A holdout JSONs by strategy. For each strategy whose passing directions equal `measure_v104.admitted_directions(strategy)` (index amendment 2):

```bash
python scripts/backtest/measure_v104.py emit-registry --holdout-json <that strategy's passing holdout JSONs> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

  A strategy with only some admitted directions passing gets **no row**. `emit-registry` refuses it anyway; record it in V104-20.

**Part B passed (a mechanism):**

- [ ] **B0: Is it wireable now?** Two outcomes are **recorded but not unmasked** in this plan, because live would not equal the measured backtest:
  - a winner with `earnings == "exit_before"`: live `plan_manager` never closes a position on `hold_cap_bars`, so it needs a forced-exit follow-up plan;
  - **B3 Earnings Gap Drift** in any setting: live strategy frames carry no `evt_*` columns, so it needs a live earnings-context follow-up plan.

  For either, write the gap into V104-20's methodology row as `PASS — blocked on <follow-up>`, keep the gate masked, and continue with the next block.

- [ ] **B1: Unmask and freeze.** For a wireable pass:
  - In `swingbot/core/market/strategy_types.py`, set `STRATEGY_GATES["<name>"] = {"directions": ("bearish",)}`, with a comment giving the TRAIN and holdout N / WR / ExpR, the window and the tier.
  - In `swingbot/core/market/short_entries.py`, set its `DEFAULT_PARAMS` row to the winning cell, e.g. `{"k": 2, "earnings": "hold"}`.

- [ ] **B2: Strategy lists.**
  - Add the name at the end of `backtest.ALL_STRATEGIES`.
  - In `swingbot/commands/backtest.py` `STRATEGY_MAP`, add aliases: `"bulltrap"`/`"trap"` for Bull Trap, `"volbreak"`/`"vbd"` for Vol Expansion Breakdown.
  - In `swingbot/commands/slash.py` `STRATEGY_CHOICES`, add `app_commands.Choice(name="<name>", value="<first alias>")` after the Volume Profile choice, and append the name to the strategies help line.
  - Then run `git grep -n '"Volume Profile"' -- swingbot frontend/src` and add the name to every other list that enumerates all strategies.

- [ ] **B3: Parity exclusion.** The frozen `legacy_trade_plan_at` has no shorts. In `tests/backtesting/test_sizing_parity.py`, parametrise over `PARITY_STRATEGIES`, defined below the imports:

```python
from swingbot.core.market.strategy_types import SHORT_STRATEGIES
# The frozen side predates v104's shorts (and v103's continuation) and must never learn them.
PARITY_STRATEGIES = tuple(s for s in ALL_STRATEGIES if s not in SHORT_STRATEGIES + ("Fibonacci Continuation",))
```

  Apply the same exclusion wherever `scripts/reports/parity_sizing.py` iterates `ALL_STRATEGIES`.

- [ ] **B4: Registry.** Run `emit-registry` with the mechanism's passing holdout JSON. Then `tests/backtesting/test_registry.py::test_all_eleven_strategies_present` fails on the new count: rename it to match the new total (e.g. `test_all_twelve_strategies_present`) and assert that number.

- [ ] **B5: Pin test.** Append to `tests/market/test_short_entries.py`:

```python
def test_v104_validated_short_defaults():
    assert STRATEGY_GATES["<name>"] == {"directions": ("bearish",)}
    assert ef.DEFAULT_PARAMS["<name>"] == <the frozen winning cell dict>
```

**Both:**

- [ ] **Soak, not alerts.** Leave `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES` alone. Going live stays behind `!soak`.
- [ ] **Commit and merge.** Run `python scripts/dev/testrun.py fast` once (`0 failed`, `0 xfailed`), then commit with message `feat(v104): wire <passes> -- <tier> on the 2026 holdout` and the trailer. Merge per `worktree-lifecycle` after checking `git log main` for other sessions' commits.

---

### Task V104-20: Methodology rows and strategy docs (every outcome)

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (the closed pre-registrations table)
- Modify: `docs/strategy-types/shared-mechanics.md`, the affected strategy pages, and `docs/strategy-types/README.md`
- Create: `docs/strategy-types/bull-trap.md`, `vol-expansion-breakdown.md`, `earnings-gap-drift.md`

- [ ] **Step 1: Methodology rows.** Load `pooled-numbers`. Add rows matching the v101–v103 style, with no ALL-CAPS token in backticks unless it is a closed knob. `tests/hooks/test_guardrails.py` checks this, so write "the structural-stop scope list" rather than the config name.
  - **One row for Part A as a whole:** how many of the 15 cells ended at Stage 1, Stage 2 and holdout pass/fail/sealed-thin; the passing pairs with TRAIN and holdout N / WR / ExpR; the registry outcome under amendment 2; and what reopening a failed cell needs (a stop rule other than "the strategy's own structure up to max_risk_pct").
  - **One row per short mechanism:** the stage it ended at; per earnings setting, the figures with N and window; the hold-vs-exit_before comparison; whether the holdout was spent, sealed-thin or unspent; and any "PASS — blocked on …" from V104-19 B0.

- [ ] **Step 2: Strategy docs.**
  - In `shared-mechanics.md` §4a, mark the finding **fixed by v104 V104-2**, and add a §4b "Structural stops (v104)" describing `stop_ceiling`, the scope list, the fail-closed sizing guard and the current scope value.
  - On each Part A strategy page, add the v104 in/out figures to `## Measured`.
  - Create the three short pages in the existing page format: idea, entry rule, plan, measured, pseudocode. Source them from `short_entries.py` / `short_builders.py` and V104-17/18's results.
  - Add the three shorts to the README table.

- [ ] **Step 3: Commit on `main`**

```bash
git add docs/claude/backtest-methodology.md docs/strategy-types/
git commit -m "docs(v104): methodology rows and strategy-type pages -- <one-line outcome>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`. Expected: PASS.

---

### Task V104-21: Full-suite verification and close-out

- [ ] **Step 1:** Dispatch `test-runner` for `python scripts/dev/testrun.py full` on `main`. Require `0 failed` and `0 xfailed`. If a failure passes in isolation and sits in code v104 never touched, report it with both outputs, and don't call the suite green.
- [ ] **Step 2:** Invoke `/close-out v104`. It resolves the bump from the then-current `VERSION.json`: `bot minor` if V104-19 shipped anything, otherwise no release commit. It regenerates `version_history.json`, moves the spec and all six plan files (`_0-index`, `_1a`, `_1b`, `_1c`, `_2`, `_3`) to `implemented/`, and removes the worktrees. The code reached `main` either way (inert when nothing passed), so the destination is `implemented/`, not `no-lift/`. Add the spec Status line `**Status:** <Shipped <list> | Closed no-lift> <date>; holdout spent: <list>; sealed-thin: <list or none>.`
- [ ] **Step 3:** If any candidate is `sealed-thin`, record a project memory: the candidate list, "retry once when HOLDOUT_END ≥ 2026-12-31", and the command to run (V104-18 Step 2). Otherwise no session will remember the shot.
