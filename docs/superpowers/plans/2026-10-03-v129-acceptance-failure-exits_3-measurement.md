# v129 — Part 3: measurement, close-out, full suite

> Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-03-v129-acceptance-failure-exits_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-03-v129-acceptance-failure-exits` on branch `2026-10-03-v129-acceptance-failure-exits`. Every path below is relative to that worktree. Never edit the main tree.

**Rules for every task in this part:**

- Invoke the `backtest-gate` skill **before every `measure_acceptance_exits.py` command**, not after.
- Dispatch the `backtest-runner` agent for every run. Give it the exact command, the progress file (`logs/measure_acceptance_exits.arm<ARM>.progress`) and the expected wall time from V129-9 Step 5. Dispatch **one runner at a time** on this machine.
- A stage that does not advance (`UNDERPOWERED`, `NO_ELIGIBLE_CELL`, `FAIL`) **closes that arm**. Record the result as measured and go to the task named in that step. No widened window, looser margin, extra cell or re-run.
- Read numbers only from the stage JSON files. Before quoting ΔExpR, WR or N anywhere (a result doc, a commit message, the closed table), invoke the `pooled-numbers` skill.
- All outputs land in `docs/superpowers/results/v129/`. Rows files are written compact and are committed: they are the evidence a verdict was computed from.
- The driver enforces the stage order. If it prints `refused:`, read the message and stop; never delete a stage file to get past it.

# Phase 4 — Measurement (Group E)

### Task V129-10: Pre-registration record, then arm Z Stage 0

**Files:**
- Create: `docs/superpowers/results/2026-10-03-v129-preregistration.md`
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armZ-train-rows.json`, `...-armZ-stage0.json`

**Interfaces:**
- Consumes: the CLI from V129-9.
- Produces: the committed pre-registration record (V129-12, V129-13 and V129-15 require it) and arm Z's Stage 0 verdict (V129-11 consumes it).

- [ ] **Step 1: Confirm neither arm is a closed row**

Invoke `backtest-gate`. Then run `grep -n "acceptance\|close-based\|sweep" docs/claude/backtest-methodology.md`. Confirm no row of "Closed pre-registrations — do not re-run these" names a close-based exit after entry for confluence or Break & Retest plans. The spec's § Why lists the nearest closed rows (v114, v104, v92 `STALL_EXIT_ENABLED`, v88) and why none is this hypothesis. If a row **does** match, stop and ask the partner.

- [ ] **Step 2: Write the record, before any outcome is read**

Write `docs/superpowers/results/2026-10-03-v129-preregistration.md` with exactly these sections. Quote the spec for the first three; copy the constants from the code, not from memory.

```markdown
# v129 — Acceptance-failure exits: pre-registration

Written before any measurement. Spec: `docs/superpowers/specs/2026-10-03-v129-acceptance-failure-exits-design.md`.
Gate: the v92 harvest gate (`acceptance_harvest.evaluate_harvest`). The v72 funnel is not used: this is an exit-only (`Edge: harvest`) change.

## Claim
<spec § Pre-registered claim, first paragraph, verbatim>

## Arms and grids (two independent populations; a pass in one never carries the other)
- Arm Z: confluence plans. Intrabar stop moves to the disaster stop `max(level − m·ATR14, entry·0.98)` (bearish mirrored); close exit strictly beyond `level ∓ b·ATR14`. 1R = entry → disaster stop. Grid `m ∈ {0.5, 1.0, 1.5}` × `b ∈ {0, 0.25}`.
- Arm B: Break & Retest plans. Stop unchanged; close exit strictly beyond the broken level `∓ b·ATR14`. Grid `b ∈ {0, 0.25}`.
- `level` and ATR14 are frozen at the plan's creating bar.

## Population and instrument
- Universe: every watchlist ticker with a cached frame (`measure_arms.cached_universe()`), all `LEGACY_HORIZONS`, `scale_out=True`.
- Arm Z entries: `replay_scenarios` with live `ScanParams`. Arm B entries: the plans `run_backtest("Break & Retest", exit_model="v2", scale_out=True, tp2_mode="levels")` builds.
- Entries are built once with `ACCEPTANCE_EXIT_ENABLED` off and re-simulated per cell (`acceptance_replay`), so the design is paired.
- A not-eligible arm Z plan (level beyond the 2% cap, or on the profit side of entry) keeps today's exit in both arms and stays in the population.
- A stop hit books −1.0R in both arms, gaps included.

## Windows
TRAIN 2020-01-01..2023-12-31. VALIDATION 2024-01-01..2025-12-31, one shot per arm.

## Stages (constants frozen in `acceptance_exit_funnel.py`)
- Stage 0: paired MDE (`mde_expectancy_r_paired`, power 0.80), `target_n` projected from TRAIN closed N over 1460 → 730 days. Any cell's MDE above +0.10R, or undefined, closes the arm `UNDERPOWERED`.
- Stage 1: a cell is eligible when `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` all pass on TRAIN. Selected = the eligible cell with the highest lower-95% ΔExpR whose grid neighbours (±1 step in m or b; arm B: the other cell) are all eligible. Tie → the earlier cell in grid order. No such cell → `NO_ELIGIBLE_CELL`.
- Stage 2: four TRAIN calendar-year folds (2020–2023) for the selected cell. FAIL when more than half of the measurable folds have ΔExpR < 0, or none is measurable.
- Stage 3: one VALIDATION replay of the selected cell only. All four harvest clauses. `not_luck` = per-ticker arm-label swap on ΔExpR, n = 200, seed 42, p < 0.05.

## Disclosures (reported, never gating)
ΔWR, N, outcome flips both ways, exit mix by reason, planned-RR shift, arm Z not-eligible count and gap-through count, per-horizon N, entries only one arm triggered.

## On a pass
The arm's result is recorded and the float defaults are set to the selected cell. `ACCEPTANCE_EXIT_ENABLED` is **not** flipped by this plan: live exits run through `plan_manager`, which has no close exit yet (plan index, Spec correction 6). The flip is the partner's call.

## On a fail
A row in "Closed pre-registrations — do not re-run these". Never re-run as specified.
```

- [ ] **Step 3: Commit the record alone**

```bash
git add docs/superpowers/results/2026-10-03-v129-preregistration.md
git commit -m "docs(v129): pre-registration (harvest gate, arms Z and B, one shot each)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Arm Z Stage 0 (TRAIN replay, the long run)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 0
```

Expected last line: `arm Z stage 0: POWERED -> ...armZ-stage0.json` (exit 0) or `UNDERPOWERED` (exit 1).

- [ ] **Step 5: Read the verdict and commit**

Read `docs/superpowers/results/v129/2026-10-03-v129-armZ-stage0.json`: `verdict`, and per cell `observed_n`, `target_n`, `mde_r`.
- `POWERED`: continue to V129-11.
- `UNDERPOWERED`: arm Z closes here, budget intact. Skip V129-11 and V129-12.

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armZ-train-rows.json docs/superpowers/results/v129/2026-10-03-v129-armZ-stage0.json
git commit -m "docs(v129): arm Z Stage 0 -- <POWERED|UNDERPOWERED>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-11: Arm Z Stage 1 (plateau selection) and Stage 2 (folds)

**Files:**
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armZ-stage1.json`, `...-armZ-stage2.json`

**Interfaces:**
- Consumes: arm Z's `stage0.json` (`POWERED`) and `train-rows.json` (V129-10).
- Produces: `stage1.json` (`selected`) and `stage2.json` (V129-12 consumes both).

Skip this task if V129-10 ended `UNDERPOWERED`. Both stages reuse the saved TRAIN rows, so each is a bootstrap over existing data, not a replay.

- [ ] **Step 1: Stage 1**

Invoke `backtest-gate`. Run:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 1
```

Read `...-armZ-stage1.json`: `verdict`, `selected`, and for each of the six cells `eligible`, `plateau`, `delta_expr`, `lo95`, plus its `reports[]` entry.
- `SELECTED`: continue.
- `NO_ELIGIBLE_CELL`: arm Z closes at Stage 1, budget intact. Commit `stage1.json` and skip to the end of this task; skip V129-12.

- [ ] **Step 2: Sanity-check the disclosures before going on**

In the selected cell's `reports[]` entry check three things. Each is a "stop and report a bug" condition, never a result:
- `exit_mix.component` has an `acceptance_exit` count above 0. Zero means the rule never fired: the trap the spec designed out. Stop.
- `not_eligible + (rows that are eligible)` equals the row count, and `not_eligible` is below the row count. All-not-eligible means arm Z changed nothing. Stop.
- `median_planned_rr.component` is at or below `median_planned_rr.baseline` (arm Z widens the stop by construction). Higher means 1R is not being measured to the disaster stop. Stop.

- [ ] **Step 3: Stage 2**

Invoke `backtest-gate`. Run:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 2
```

Read `...-armZ-stage2.json`: `verdict`, `measurable`, `reversed`, and each fold's `n` and `delta_expr`.
- `PASS`: continue to V129-12.
- `FAIL`: arm Z closes at Stage 2, budget intact. Skip V129-12.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armZ-stage1.json docs/superpowers/results/v129/2026-10-03-v129-armZ-stage2.json
git commit -m "docs(v129): arm Z Stage 1 <verdict, selected cell> and Stage 2 <verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(If Stage 2 never ran, add only `stage1.json`.)

---

### Task V129-12: Arm Z Stage 3 — the one VALIDATION shot

**Files:**
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armZ-validation-rows.json`, `...-armZ-stage3.json`
- Create: `docs/superpowers/results/2026-10-03-v129-armZ.md`

**Interfaces:**
- Consumes: arm Z's `stage1.json` and `stage2.json` (`PASS`), and the committed pre-registration record.
- Produces: arm Z's final verdict and result record (V129-16 consumes both).

If V129-10 or V129-11 closed the arm, skip Steps 1–2 and write the result record (Step 3) for the stage it ended at.

- [ ] **Step 1: Pre-flight (nothing here reads VALIDATION)**

- `git log --oneline -- docs/superpowers/results/2026-10-03-v129-preregistration.md` prints the V129-10 commit.
- `git status --short docs/superpowers/results/v129/` is clean: every earlier stage file is committed.
- `ls docs/superpowers/results/v129/ | grep armZ-stage3` prints nothing.
- Invoke `backtest-gate` and state, in the session, the selected cell and that this is arm Z's single shot.

- [ ] **Step 2: Fire the shot**

Dispatch `backtest-runner` with:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 3 --preregistration docs/superpowers/results/2026-10-03-v129-preregistration.md
```

Expected last line: `arm Z stage 3: PASS -> ...` (exit 0) or `FAIL` (exit 1). **Whatever it prints is final.** If the process crashes after writing `-validation-rows.json`, run the same command again: the driver reuses the saved rows and does not replay. If it crashes before that file exists, nothing was read; run it again.

Commit the two generated files immediately, before interpreting them:

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armZ-validation-rows.json docs/superpowers/results/v129/2026-10-03-v129-armZ-stage3.json
git commit -m "docs(v129): arm Z Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Write the result record**

Invoke `pooled-numbers`. Write `docs/superpowers/results/2026-10-03-v129-armZ.md`, reading every number from the stage JSON files:

- **Verdict line:** the stage the arm ended at, its verdict, and whether the VALIDATION budget is spent.
- **Stage 0 table:** per cell `observed_n`, `target_n`, `mde_r`, `powered`.
- **Stage 1 table** (if run): per cell `delta_expr`, `lo95`, `hi95`, `eligible`, `plateau`, the three clause verdicts from `gate.clauses`, and the selected cell. Quote the selection rule from the pre-registration.
- **Stage 2 table** (if run): per fold year `n`, `delta_expr`, `reversed`; `measurable`, `reversed`.
- **Stage 3** (if run): the four clauses with `detail`, `permutation_p`.
- **Disclosures** for the selected cell on TRAIN and, if run, VALIDATION: ΔWR, N per arm, flips both ways, exit mix, median planned RR per arm, `not_eligible`, `gap_through`, `only_baseline_triggered` / `only_cell_triggered`, per-horizon N.
- **Observations:** what the numbers do and do not show. Say plainly when a positive ΔExpR is partly an R-unit effect (arm Z's 1R is larger, so the same price move is a smaller R), and whether one horizon carries the result.

```bash
git add docs/superpowers/results/2026-10-03-v129-armZ.md
git commit -m "docs(v129): arm Z result record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-13: Arm B Stage 0

**Files:**
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armB-train-rows.json`, `...-armB-stage0.json`

**Interfaces:**
- Consumes: the CLI (V129-9) and the committed pre-registration record (V129-10 Step 3).
- Produces: arm B's Stage 0 verdict (V129-14 consumes it).

Arm B is a separate budget. Its verdict never depends on arm Z's, and the two are never pooled.

- [ ] **Step 1: Confirm the pre-registration is committed**

`git log --oneline -- docs/superpowers/results/2026-10-03-v129-preregistration.md` must print the V129-10 commit. If it prints nothing, stop: V129-10 Steps 1–3 run first.

- [ ] **Step 2: Stage 0**

Invoke `backtest-gate`. Dispatch `backtest-runner` with:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm B --stage 0
```

- [ ] **Step 3: Read the verdict and commit**

Read `...-armB-stage0.json`. The spec expects arm B (TRAIN N ≈ 105) to be the likely `UNDERPOWERED` arm. That is a finished, valid result.
- `POWERED`: continue to V129-14.
- `UNDERPOWERED`: arm B closes here, budget intact. Skip V129-14; in V129-15 write only the result record.

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armB-train-rows.json docs/superpowers/results/v129/2026-10-03-v129-armB-stage0.json
git commit -m "docs(v129): arm B Stage 0 -- <POWERED|UNDERPOWERED>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-14: Arm B Stage 1 (both cells) and Stage 2 (folds)

**Files:**
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armB-stage1.json`, `...-armB-stage2.json`

**Interfaces:**
- Consumes: arm B's `stage0.json` (`POWERED`) and `train-rows.json` (V129-13).
- Produces: `stage1.json` (`selected`) and `stage2.json` (V129-15 consumes both).

Skip this task if V129-13 ended `UNDERPOWERED`.

- [ ] **Step 1: Stage 1**

Invoke `backtest-gate`. Run:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm B --stage 1
```

Read `...-armB-stage1.json`. Arm B selects only when **both** cells are eligible, taking the higher lower-95% ΔExpR.
- `SELECTED`: continue.
- `NO_ELIGIBLE_CELL`: arm B closes at Stage 1, budget intact. Commit `stage1.json`; in V129-15 write only the result record.

- [ ] **Step 2: Sanity-check the disclosures**

In the selected cell's `reports[]` entry:
- `exit_mix.component.acceptance_exit` is above 0. Zero means the rule never fired. Stop and report a bug.
- `only_baseline_triggered` and `only_cell_triggered` are both 0, and `median_planned_rr.component == median_planned_rr.baseline`. Arm B does not move the stop, so anything else is a bug. Stop.
- Note `delta_wr_pp` and `flips`. The spec expects arm B can lower WR (a dip that would have recovered becomes a small loss). The −2.0pp floor is live; the gate already applied it.

- [ ] **Step 3: Stage 2**

Invoke `backtest-gate`. Run:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm B --stage 2
```

- `PASS`: continue to V129-15.
- `FAIL`: arm B closes at Stage 2, budget intact. In V129-15 write only the result record.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armB-stage1.json docs/superpowers/results/v129/2026-10-03-v129-armB-stage2.json
git commit -m "docs(v129): arm B Stage 1 <verdict, selected cell> and Stage 2 <verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(If Stage 2 never ran, add only `stage1.json`.)

---

### Task V129-15: Arm B Stage 3 — the one VALIDATION shot

**Files:**
- Create (generated): `docs/superpowers/results/v129/2026-10-03-v129-armB-validation-rows.json`, `...-armB-stage3.json`
- Create: `docs/superpowers/results/2026-10-03-v129-armB.md`

**Interfaces:**
- Consumes: arm B's `stage1.json` and `stage2.json` (`PASS`), and the committed pre-registration record.
- Produces: arm B's final verdict and result record (V129-16 consumes both).

If V129-13 or V129-14 closed the arm, skip Steps 1–2 and write the result record (Step 3) for the stage it ended at.

- [ ] **Step 1: Pre-flight (nothing here reads VALIDATION)**

- `git log --oneline -- docs/superpowers/results/2026-10-03-v129-preregistration.md` prints the V129-10 commit.
- `git status --short docs/superpowers/results/v129/` is clean.
- `ls docs/superpowers/results/v129/ | grep armB-stage3` prints nothing.
- Invoke `backtest-gate` and state the selected cell and that this is arm B's single shot.

- [ ] **Step 2: Fire the shot**

Dispatch `backtest-runner` with:

```bash
python scripts/backtest/measure_acceptance_exits.py --arm B --stage 3 --preregistration docs/superpowers/results/2026-10-03-v129-preregistration.md
```

Whatever it prints is final. The crash rule is the same as V129-12 Step 2: re-running after `-validation-rows.json` exists reuses the saved rows. Commit the two generated files before interpreting them:

```bash
git add docs/superpowers/results/v129/2026-10-03-v129-armB-validation-rows.json docs/superpowers/results/v129/2026-10-03-v129-armB-stage3.json
git commit -m "docs(v129): arm B Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Write the result record**

Invoke `pooled-numbers`. Write `docs/superpowers/results/2026-10-03-v129-armB.md` with the same sections as arm Z's record (verdict line; Stage 0, 1, 2, 3 tables for the stages that ran; disclosures; observations), every number read from arm B's stage JSON files. Arm B has no `not_eligible` or planned-RR shift to explain; say so in one line instead of leaving the rows out. In Observations, state the WR direction and what the flips were (timeout/win → loss versus loss → smaller loss), because that is the trade-off this arm makes.

```bash
git add docs/superpowers/results/2026-10-03-v129-armB.md
git commit -m "docs(v129): arm B result record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# Phase 5 — Close-out (sequential tail)

### Task V129-16: Record both arms; on a pass set the float defaults and ask about the flip

**Files:**
- Modify: `docs/claude/backtest-methodology.md` ("Closed pre-registrations — do not re-run these")
- Modify: `swingbot/config.py` (the four v129 Fields' `help` text; on a pass, the two float defaults)
- On a pass only: `.env.example`, `tests/planning/test_acceptance_levels.py`
- Check, edit only if a condensed rule changes: `AGENTS.md`

**Interfaces:**
- Consumes: `docs/superpowers/results/2026-10-03-v129-armZ.md`, `...-armB.md` and the stage JSON files.
- Produces: the closed-table rows and the final config state V129-17 verifies.

`ACCEPTANCE_EXIT_ENABLED` stays `false` in every outcome of this task (index, Spec correction 6).

- [ ] **Step 1: One row per arm in the closed table**

Invoke `pooled-numbers`. Append two rows to "Closed pre-registrations — do not re-run these" in `docs/claude/backtest-methodology.md`, one per arm, in the table's three columns (Component | Outcome | Record).

- **Component:** `Acceptance-failure exit, arm Z — confluence disaster stop + close exit, m ∈ {0.5, 1.0, 1.5} × b ∈ {0, 0.25} (v129)` and `Acceptance-failure exit, arm B — Break & Retest close exit at the broken level, b ∈ {0, 0.25} (v129)`.
- **Outcome:** bold lead with the stage it ended at and the budget state, for example `**UNDERPOWERED at Stage 0, budget intact.**`, `**NO_ELIGIBLE_CELL at Stage 1, budget intact.**`, `**FAILED its one VALIDATION shot. Spent and final.**` or `**PASS on VALIDATION, shot spent. Flag NOT flipped.**`. Then the measured numbers for that stage (TRAIN N, the MDE or the per-cell ΔExpR and lower bounds, fold counts, VALIDATION clauses). Then the reopen clause, verbatim: `Reopening needs a mechanism other than "exit on a daily close beyond the plan's own level ∓ b·ATR14"` (arm Z: add `"with the intrabar stop m·ATR14 past the level, capped at 2%"`). A looser MDE ceiling, another grid or another window is not a new mechanism.
- For a **PASS** row add: `Code ships merged and inert: live exits run through plan_manager, which has no close exit, so ACCEPTANCE_EXIT_ENABLED stays false until a follow-up spec wires it.`
- **Record:** the arm's result record and `results/2026-10-03-v129-preregistration.md`.

- [ ] **Step 2: Update the Field help text**

In `swingbot/config.py`, extend the `help` of `ACCEPTANCE_EXIT_ENABLED` with one sentence citing the closed rows ("v129: arm Z <verdict>, arm B <verdict>; see backtest-methodology.md"), as the `ADAPTIVE_RUNNER_TRAIL_ENABLED` Field does for v92. Run `git grep -n "ADAPTIVE_RUNNER_TRAIL_ENABLED" -- swingbot/config.py` to see the pattern.

- [ ] **Step 3: If an arm passed VALIDATION, set the float defaults**

Skip this step when neither arm passed.

- Arm Z passed: set `ACCEPTANCE_DISASTER_ATR_M`'s default to the selected `m` and `ACCEPTANCE_CLOSE_BUFFER_ATR`'s default to the selected `b`, in `config.py` and `.env.example`. Drop the word "Interim" from the `.env.example` comment and name the cell.
- Arm B passed alone: set only `ACCEPTANCE_CLOSE_BUFFER_ATR` to arm B's selected `b`.
- **Both passed with different `b`:** the one shared buffer Field cannot carry both. Do not pick. Ask the partner (Step 5) and leave the defaults as they are.
- Set `ACCEPTANCE_EXIT_ARMS`'s default to the passing arm letters only (`"Z"`, `"B"` or `"Z,B"`). It is still unread while the flag is off.
- Run `git grep -n "ACCEPTANCE_DISASTER_ATR_M\|ACCEPTANCE_CLOSE_BUFFER_ATR\|ACCEPTANCE_EXIT_ARMS" -- tests/` and update any assertion that pins the old default (V129-5's flag-parsing tests in `tests/planning/test_acceptance_levels.py`).
- Run:
  - `python scripts/dev/testrun.py file tests/planning/test_acceptance_levels.py`
  - `python scripts/dev/testrun.py file tests/test_v115_strategy_work_off.py`
  - `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`

  Expected: all pass. The golden is flag-off, so a default change cannot move it; if it moves, a default is being read with the flag off. That is a bug: stop.

- [ ] **Step 4: Codex mirror**

`docs/claude/` changed, so check the mirror: `grep -n "closed pre-registration\|backtest-methodology" AGENTS.md`. `AGENTS.md` condenses the rule, not the table. If no condensed sentence changes, leave it untouched and say so in the commit body. Run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`. Expected: pass.

- [ ] **Step 5: If an arm passed, ask the partner — one question**

Skip when neither arm passed. Use `AskUserQuestion`, one question, recommended option first:

- Question: "v129 arm <Z|B|Z and B> passed VALIDATION (ΔExpR <point> [<lo>, <hi>]R at cell <cell>). The flag is still off because live exits (`plan_manager`) have no close exit. What next?"
- Options:
  1. "Write the follow-up spec to wire the close exit into `plan_manager`, then flip (Recommended)". Flipping without it would widen live arm Z stops with no close exit behind them.
  2. "Leave it merged and inert for now".
  3. (Only when both arms passed with different `b`) "Add a second buffer Field so each arm keeps its own `b`": new scope, goes into the same follow-up spec.

Record the answer in the result record(s) under a `## Decision` heading. Do not start the follow-up spec in this plan. Also record there Spec correction 5's open question for a later arm Z flip: a stop-entry Z plan whose disaster stop sits exactly on the 2% cap is cancelled by `plan_manager._step_pending` (`cancelled_risk_cap`) on any fill past the trigger.

- [ ] **Step 6: Commit**

```bash
git add docs/claude/backtest-methodology.md swingbot/config.py
# on a pass also: .env.example tests/planning/test_acceptance_levels.py docs/superpowers/results/2026-10-03-v129-arm*.md
git commit -m "docs(v129): close-out -- arm Z <verdict>, arm B <verdict>; flag stays off

AGENTS.md: <unchanged, no condensed rule moved | updated: ...>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V129-17: Full-suite verification, then the release bump

**Files:**
- No new feature files. Fix only failures this plan caused, through their narrow tests.
- Modify: `VERSION.json` and the version-matrix output of `scripts/dev/build_version_matrix.py`.
- Move: the three plan parts and the index into `docs/superpowers/plans/implemented/`; the spec into `docs/superpowers/specs/implemented/` (check `document-lifecycle.md` for the exact targets).

**Interfaces:**
- Consumes: everything V129-0..16 changed.
- Produces: a green suite, the bumped version and the closed plan.

- [ ] **Step 1: Full suite, once**

Dispatch the `test-runner` agent with `python scripts/dev/testrun.py full`. Green means `0 failed` and `0 xfailed`. A changed pass count is not a failure. If it is not green, fix forward from the failures the run names: they are this plan's regressions. Before blaming a change for a failure in a shared-DB test, run that file alone and compare with `main` (`docs/claude/testing-cost.md`).

- [ ] **Step 2: Complexity over every file the plan touched**

```bash
python -m radon cc -s -n C swingbot/core/planning/acceptance_levels.py swingbot/core/planning/exit_sim.py swingbot/core/planning/builders.py swingbot/core/planning/plan_types.py swingbot/core/market/entry_filters.py swingbot/core/backtesting/backtest.py swingbot/core/backtesting/acceptance_harvest.py swingbot/core/backtesting/acceptance_replay.py swingbot/core/backtesting/acceptance_exit_funnel.py scripts/backtest/measure_acceptance_exits.py
```

No function this plan wrote or changed may be listed. `_single_leg_exit_walk` and `_scale_out_exit_walk` must be absent (V129-6 brought both under 15). A legacy function that was already listed on `main` and that this plan did not touch may remain. Confirm it was already there with `git show main:<file> | python -m radon cc -s -n C -`.

- [ ] **Step 3: Release bump (level from the header: `bot patch`)**

Follow `docs/claude/document-conventions.md` § The header block, steps 1–4:
1. Read `VERSION.json` now. Never use a number from this plan, the spec or memory.
2. Increment `bot` at patch level. Leave `ui` untouched.
3. Set `bot_updated` to the current time in the existing `YYYY-MM-DD HH-MM-SS` format.
4. Run `python scripts/dev/build_version_matrix.py` and commit its output **with** the bump.

The patch is warranted in every outcome: live scans now record `acceptance_level` on confluence and Break & Retest plans. If the partner's review concludes that is not an observable difference, amend the header to `Bump: none` in the closing commit with one clause saying why, and skip this step.

```bash
git add VERSION.json <the files build_version_matrix.py rewrote, from git status>
git commit -m "chore(v129): bump bot patch -- plans record acceptance_level; exits unchanged (flag off)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Close the plan out**

Read `docs/claude/document-lifecycle.md` and invoke the `worktree-lifecycle` skill before merging.
- Amend `Edge:` in the index header with one clause if the outcome differs from the `harvest` prediction (for example `Edge: harvest — predicted; measured no lift, both arms closed`).
- Move the index, the three parts and the spec to their `implemented/` folders (the code is merged even though it is inert). Fix the index's `**Spec:**` link and any cross-link the move breaks: `git grep -n "v129-acceptance-failure-exits" -- docs/ CLAUDE.md AGENTS.md`.
- Merge the branch to `main` per the skill. A conflict-free merge gets no second suite run. A merge that resolved conflicts (most likely with v123 in `exit_sim.py` or `config.py`) is new code: run `python scripts/dev/testrun.py full` once more through `test-runner`.
- Remove the worktree per `document-lifecycle.md`. Never delete a branch whose name contains `backup` or starts with `stable-`.

```bash
git add -A docs/superpowers/plans docs/superpowers/specs
git commit -m "docs(v129): close out acceptance-failure exits into implemented/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
