# v139 — Part 3: measurement, record, full suite, close-out

> Index, Spec corrections, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-08-v139-confluence-stop-geometry_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-08-v139-confluence-stop-geometry` on branch `2026-10-08-v139-confluence-stop-geometry`. Every path below is relative to that worktree's root, which is the session root. Never edit the main tree. Never `cd` in Bash.

**Rules for every task in this part:**

- Invoke the `backtest-gate` skill **before every** `measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py` or `permutation_test.py` command, not after.
- Every measurement command runs with both environment variables set (index, Spec correction 9):

  ```bash
  export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
  export MEASURE_ARMS_UNIVERSE=cache
  ```

- Dispatch the `backtest-runner` agent for every producer run: `measure_confluence_stop.py` stages −1, 0 and 3, and every `measure_arms.py`. Give it the exact command, the worktree, the progress file and the wall-time estimate from the V139-10 commit body.
  - Progress files: `logs/measure_confluence_stop.<census|rows>.progress` and `logs/measure_arms.*.progress`.
  - **One runner at a time** on this machine, never two at once.
- Before each producer run, confirm `git status --short -- swingbot/ scripts/backtest/` is empty, and make no edit there while it runs.
- A stage that does not advance **closes that arm**: `refused:zero-diff`, `UNDERPOWERED`, `REFUSED` on every cell, `NO_ELIGIBLE_CELL`, `no-eligible-cell`, `spike` or `FAIL`. Record the result as measured and go to the step the task names. No widened window, looser margin, extra cell or re-run.
- Read numbers only from the stage JSON files and the logs under `logs/v139/`. Before quoting ΔExpR, WR or N anywhere (a result doc, a commit message, the closed table, the ledger), invoke the `pooled-numbers` skill.
- Arm S outputs land in `docs/superpowers/results/v139/`. Its rows files are written compact and are committed: they are the evidence a verdict was computed from. Arm D arm files (`logs/v139/armD-*.json`) are large and are **not** committed (the v128/v135 convention). Their judge outputs and logs are copied into the arm D result doc.
- The arm S driver enforces stage order. If it prints `refused:`, read the message and stop. Never delete a stage file to get past it.

# Phase 4 — Measurement

## Parallelisation (Phase 4)

- **Group C:** V139-11 first. It commits the pre-registration record, then runs Stage −1 for both arms, one runner at a time.
- **Group D (after V139-11):** the arm S chain V139-12 → V139-13 and the arm D chain V139-14 → V139-15. Each stage consumes the previous verdict, so each chain is sequential. The chains have disjoint outputs and may interleave, but only one `backtest-runner` is ever in flight.
- An arm closed at Stage −1 skips its whole chain and goes straight to its result record (V139-13 Step 4 for arm S, V139-15 Step 4 for arm D).

### Task V139-11: Pre-registration record, then Stage −1 for both arms

**Files:**
- Create: `docs/superpowers/results/2026-10-08-v139-preregistration.md`
- Create (generated): `docs/superpowers/results/v139/2026-10-08-v139-armS-census-train-rows.json`, `.../2026-10-08-v139-armS-stageM1.json`
- Create: `docs/superpowers/results/2026-10-08-v139-armD.md` (the Stage −1 section; later stages append)
- Logs, not committed: `logs/v139/armD-pilot-3.0.json`, `logs/v139/armD-reachability.log`

**Interfaces:**
- Consumes: the V139-10 CLI; `measure_arms.py --stage pilot --knob ... --preregistration P --out P`; `validate_component.py --stage reachability --arms P --title T --window W`.
- Produces:
  - The committed record. V139-13 and V139-15 require it, and every arm D producer stamps it.
  - Arm S's Stage −1 verdict, consumed by V139-12.
  - Arm D's reachability verdict, consumed by V139-14.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `--help` on each script this task calls (`measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py`, `permutation_test.py`); for every one that lists `--instrument` (v158 merged), append `--instrument v1` to each of its commands here, and the result record names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V139-11 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judges refuse the arms. (c) The record written in Step 2 names the fill/cost instrument for each arm (lines added below), and, per the partner decision, discloses the v2 reading for arm S when v157 has merged.

- [ ] **Step 1: Confirm neither arm is a closed row**

Invoke `backtest-gate`. Run `grep -n "structural stop\|clamp\|v104\|v114\|v129\|v103\|v101" docs/claude/backtest-methodology.md`. The spec's § Not a re-run argues why v104 Part A, v129 arm Z, v103 A, v101 and v114 are not this hypothesis. Confirm that no **other** row of "Closed pre-registrations — do not re-run these" closes a structural confluence stop sized to dollar risk, or a confluence drop by structural stop distance. If one does, stop and ask the partner (`AskUserQuestion`, one question).

- [ ] **Step 2: Write the record, before any run**

Write `docs/superpowers/results/2026-10-08-v139-preregistration.md` with exactly these sections. Quote the spec where marked. Copy every constant from the code (`confluence_stop_replay.py`, `confluence_stop_funnel.py`, `acceptance_exit_funnel.py`, `windows.py`, `acceptance.py`), not from memory.

```markdown
# v139 — Confluence stop geometry: pre-registration

Written before any measurement. Spec: `docs/superpowers/specs/2026-10-08-v139-confluence-stop-geometry-design.md`.
Plan: `docs/superpowers/plans/2026-10-08-v139-confluence-stop-geometry_0-index.md` (Spec corrections 7-11 are part of this record).

## Claim
<spec § Pre-registered claim, both bullets and the closing sentence, verbatim>

## Definitions (frozen at the plan's creating bar)
<spec § Definitions, verbatim>. Boundaries carry a 1e-9 tolerance: d exactly at c − 0.25 is arm S; d exactly at c is kept by arm D.

## Arm S — structural stop, dollar sizing
- Rule: <spec § Arm S, the three bullets, verbatim>. Arm S never adds or removes a plan (plan index, Spec correction 8); the replay asserts it.
- Gate: the v92 harvest gate, paired, exactly as v129 ran it (constants imported from `acceptance_exit_funnel.py`), bootstrap clustered by ISO week (instrument v2).
- Fills and costs: instrument v1, as pre-registered (`--instrument v1` pinned on every command when the scripts accept the flag). "instrument v2" in the Gate line above names v129's ISO-week bootstrap design, not the v157 fill/cost instrument.
- Disclosure only (partner decision 2026-10-10): if `swingbot/core/planning/exit_sim_v2.py` exists when Stage 1 runs (v157 merged), the Stage-1 TRAIN paired ΔExpR is also reported with `instrument=resolve("v2")` fills and costs. It never gates, never selects a cell, and is labelled "v2 disclosure, non-gating" wherever it appears.
- Universe: every ticker with a cached CSV in the main tree's `data/backtest_cache` (`BACKTEST_CACHE_DIR`, `MEASURE_ARMS_UNIVERSE=cache`; the v129 precedent, partner-approved 2026-10-08), all `LEGACY_HORIZONS`, `replay_scenarios` with live `ScanParams`, `scale_out=True`.
- Windows: TRAIN 2020-01-01..2023-12-31; VALIDATION 2024-01-01..2025-12-31, one shot.
- Stage −1: the census (plans only, no exit simulated). `refused:zero-diff` when no cell changes any plan. Identical adjacent cells are reported and put to the partner before Stage 0.
- Stage 0: paired MDE (`mde_expectancy_r_paired`, power 0.80), `target_n` projected from TRAIN closed N over 1460 → 730 days. Any cell above +0.10R, or undefined, closes the arm `UNDERPOWERED`.
- Stage 1: eligible = `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` all PASS on TRAIN. Selected = the eligible cell with the highest lower-95% ΔExpR whose ±1-step neighbours in c are all eligible; a tie goes to the smaller c. None → `NO_ELIGIBLE_CELL`.
- Stage 2: four TRAIN calendar-year folds (2020–2023) for the selected cell. FAIL when more than half the measurable folds have ΔExpR < 0, or none is measurable.
- Stage 3: one VALIDATION replay of the selected cell only. All four harvest clauses. `not_luck` = per-ticker arm-label swap on ΔExpR, n = 200, seed 42, p < 0.05.
- A stop hit books −1.0R in both geometries, gaps included; gap-throughs are disclosed (plan index, Spec correction 6).

## Arm D — no plan beyond the ceiling
- Rule: <spec § Arm D, the two bullets, verbatim>.
- Gate: the standard v72 funnel through `measure_arms.py --knob CONFLUENCE_STOP_DROP_PCT=c` and `validate_component.py` (`--gate win_rate`, all six clauses at Stage 3), instrument v1 (ticker bootstrap).
- Fills and costs: instrument v1 (`--instrument v1` pinned on every command when the scripts accept the flag).
- Population: the pooled book (`DEFAULT_ENGINES` = confluence + strategy; the knob reaches only confluence rows). Clause 3's volume cut is measured on the pooled book; the confluence-only cut is disclosed. A cut past `VOLUME_MAX_CUT_PCT` (25%) fails clause 3, recorded and not rescued.
- Universe: as arm S (`MEASURE_ARMS_UNIVERSE=cache`), stamped by `measure_arms.py` and checked by every judge.
- Windows (`windows.STAGES`): pilot 2018-06-01..2020-12-31 (first 10 tickers); fold-train selection 2018-06-01..2022-12-31; walk-forward test years 2021/2022/2023; VALIDATION 2024-01-01..2025-12-31, one shot.
- Stage −1: pilot reachability at c = 3.0 (the cell that drops most). The census numbers are disclosure.
- Stage 0: paired MDE per cell against its fold-train ΔWR (`validate_component.py --stage mde`). Stage 1: `--stage selection` over the three cells, `--mde-refused` for any cell Stage 0 refused. Stage 2: `--stage walkforward`. Stage 3: `permutation_test.py --n 200 --seed 42`, then `--stage validation --permutation-p p`.
- Dropping a plan frees the 5-bar cooldown, so the component may ADD entries; clause 6 is then SKIPPED (not a subset). Disclosed.
- The selection judge prints its plateau label as `PULLBACK_DRYUP_MAX_RATIO`; cosmetic, no verdict reads it.

## Disclosures (reported, never gating)
N per arm, ΔExpR with its 95% interval, ΔWR, outcome flips both ways, exit mix by reason, median planned RR per arm, per-horizon N, entries only one side triggered. Arm S: changed, rollback, gap-through and fill-beyond-ceiling counts, median d of the changed plans. Arm D: removed / added / changed counts, volume cut % (pooled and confluence-only).

## On a pass
The arm's result is recorded. Its knob default **stays 0** (plan index, Spec correction 7): the selected c goes into the result record, the Field help and the `.env.example` comment, and the partner decides. Arm S changes what the alert tells the partner to do (a wider stop, fewer shares on resting orders); nothing goes live without that answer.

## On a fail
One row per arm in "Closed pre-registrations — do not re-run these", and one ledger row per arm. Reopen clauses (spec § On a fail): arm S needs "a stop rule other than the confluence level itself up to a ceiling `c`, sized to fixed dollar risk"; arm D needs "a drop rule other than structural distance beyond `c`". Another grid, window or MDE ceiling is not a new mechanism.
```

- [ ] **Step 3: Commit the record alone**

```bash
git add docs/superpowers/results/2026-10-08-v139-preregistration.md
git commit -m "docs(v139): pre-registration (arm S harvest gate, arm D v72 funnel, one shot each)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Arm S Stage −1, the census (plans only)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with the two exports and:

```bash
python scripts/backtest/measure_confluence_stop.py --stage -1
```

Expected last line: `arm S stage -1: REACHABLE -> ...stageM1.json` (exit 0) or `refused:zero-diff` (exit 1).

- [ ] **Step 5: Sanity-check the census before any outcome is read**

Read `docs/superpowers/results/v139/2026-10-08-v139-armS-stageM1.json`: `verdicts`, `totals` (`plans`, `clamped`, `d_buckets`, `arm_s`, `arm_d`), `by_stratum` and `identical_adjacent`. Each check below is a "stop and report a bug" condition, never a result:
- `totals.clamped` > 0. Zero means no plan reaches the clamp: either the replay changed, or the 65% estimate in the spec was wrong. Stop.
- `arm_s[c].applies == changed + rollback` for every c, and `applies` does not decrease from c3 to c5. `arm_d[c].dropped` does not increase from c3 to c5. A violation is a code bug. Stop.
- `arm_s.c5.changed` ≤ `totals.clamped`, and `arm_d.c3.dropped` ≤ `totals.clamped`.

Then:
- `verdicts.S == "refused:zero-diff"` closes arm S at Stage −1, budget intact. Skip V139-12 and go to V139-13 Step 4.
- `identical_adjacent.arm_s` or `identical_adjacent.arm_d` non-empty: ask the partner, `AskUserQuestion`, one question, recommended option first. Question: "v139 census: <arm> cells <pair> change the identical plan set on TRAIN (no outcome read). The grid was pre-registered as {3, 4, 5}. How do we proceed?" Options:
  1. "Run the grid as pre-registered and disclose the identical pair (Recommended)": the plateau rule treats identical neighbours as one shape, and amending a grid after seeing counts invites a garden of forking paths.
  2. "Amend the record before Stage 0": a new grid, written into the record and committed before any outcome is read.

  Record the answer in the record under `## Amendments` and commit it before Stage 0.

- [ ] **Step 6: Arm D Stage −1, pilot reachability**

Invoke `backtest-gate`. Dispatch `backtest-runner` with the two exports and:

```bash
PREREG=docs/superpowers/results/2026-10-08-v139-preregistration.md
mkdir -p logs/v139
python scripts/backtest/measure_arms.py --stage pilot --knob CONFLUENCE_STOP_DROP_PCT=3.0 --preregistration $PREREG --out logs/v139/armD-pilot-3.0.json
```

Then, with the same exports:

```bash
python scripts/backtest/validate_component.py --stage reachability --arms logs/v139/armD-pilot-3.0.json --title "v139 arm D c=3.0 pilot" --window "2018-06-01..2020-12-31" | tee logs/v139/armD-reachability.log
```

Pass: `REACHABLE`. **Stop rule:** `refused:zero-diff` (from either command) closes arm D at Stage −1, budget intact. Skip V139-14 and go to V139-15 Step 4.

- [ ] **Step 7: Write the arm D Stage −1 section**

Create `docs/superpowers/results/2026-10-08-v139-armD.md` with a `## Stage −1` section:
- the record's path and commit hash;
- the `knobs:` and `split` lines from `logs/v139/armD-reachability.log`;
- the census `arm_d` totals and per-stratum `dropped` counts from `stageM1.json`;
- the verdict.

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/results/v139/2026-10-08-v139-armS-census-train-rows.json docs/superpowers/results/v139/2026-10-08-v139-armS-stageM1.json docs/superpowers/results/2026-10-08-v139-armD.md
git commit -m "docs(v139): Stage -1 -- arm S census <verdict>, arm D pilot <verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V139-12: Arm S Stage 0, Stage 1 and Stage 2

**Files:**
- Create (generated): `docs/superpowers/results/v139/2026-10-08-v139-armS-train-rows.json`, `...-armS-stage0.json`, `...-armS-stage1.json`, `...-armS-stage2.json`

**Interfaces:**
- Consumes: `stageM1.json` (`REACHABLE`) and the committed record.
- Produces: `stage1.json` (`selected`) and `stage2.json`, which V139-13 consumes.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `--help` on each script this task calls (`measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py`, `permutation_test.py`); for every one that lists `--instrument` (v158 merged), append `--instrument v1` to each of its commands here, and the result record names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V139-11 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judges refuse the arms. (c) **Partner decision (arm S on v1, v2 disclosed):** arm S runs on v1 as pre-registered, with `--instrument v1` pinned when the flag exists. If `swingbot/core/planning/exit_sim_v2.py` exists (v157 merged), also report the Stage-1 TRAIN paired ΔExpR with `instrument=resolve("v2")` fills and costs (`swingbot/core/backtesting/instrument/contract.py:resolve`), as a disclosure only — it never gates and is labelled as such in the record. Compute it after Step 3, on the same TRAIN plans, into a separate file (`docs/superpowers/results/v139/2026-10-08-v139-armS-stage1-v2-disclosure.json`, added to Step 5's commit) that no later stage reads; Stage 2 and Stage 3 consume only the v1 `stage1.json`.

Skip this task if V139-11 closed arm S.

- [ ] **Step 1: Stage 0 (the TRAIN replay, the long run)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with the two exports and:

```bash
python scripts/backtest/measure_confluence_stop.py --stage 0
```

Expected last line: `arm S stage 0: POWERED -> ...` (exit 0) or `UNDERPOWERED` (exit 1). Read `...-armS-stage0.json`: `verdict`, and per cell `observed_n`, `target_n`, `mde_r`, `powered`. `UNDERPOWERED` closes arm S at Stage 0, budget intact: commit (Step 5) and skip to V139-13 Step 4.

- [ ] **Step 2: Stage 1**

Invoke `backtest-gate`. Run (a bootstrap over the saved TRAIN rows, not a replay):

```bash
python scripts/backtest/measure_confluence_stop.py --stage 1
```

Read `...-armS-stage1.json`: `verdict`, `selected`, and for each cell `eligible`, `plateau`, `delta_expr`, `lo95`, `hi95`, plus its `reports[]` entry.

- [ ] **Step 3: Sanity-check the disclosures before reading further**

Do this whatever the Stage 1 verdict. In every cell's `reports[]` entry, check the conditions below. Each is a "stop and report a bug" condition, never a result:
- `changed` > 0, and `changed` ≤ that cell's census `arm_s[c].changed` on the same TRAIN window. Both come from the same plans, but a row is dropped when neither side triggered, so the rows count can only be lower. A higher count means the replay is not the census replay. Stop.
- The three cells' `(n_component, expr_component, changed)` triples are not all identical. Identical triples mean the c axis is degenerate (the v129 `m` lesson). If the census already showed it and the partner chose option 1 in V139-11, note it and go on. Otherwise stop.
- `median_d_changed` lies in (2.0, c − 0.25] for that cell's c. Outside means arm S kept a stop it should not have. Stop.
- `fill_beyond_ceiling.baseline` and `.component` are recorded. A large component count is a finding for the record (live would cancel those fills), not a stop.
- `median_planned_rr.component` is noted beside `.baseline`. The spec says arm S lowers RR; it is disclosed, not gated, and not a stop either way.

Then:
- `SELECTED`: continue.
- `NO_ELIGIBLE_CELL`: arm S closes at Stage 1, budget intact. Commit (Step 5) and skip to V139-13 Step 4.

- [ ] **Step 4: Stage 2**

Invoke `backtest-gate`. Run:

```bash
python scripts/backtest/measure_confluence_stop.py --stage 2
```

Read `...-armS-stage2.json`: `verdict`, `measurable`, `reversed`, and each fold's `n` and `delta_expr`. `PASS`: continue to V139-13. `FAIL`: arm S closes at Stage 2, budget intact; skip to V139-13 Step 4.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/v139/2026-10-08-v139-armS-train-rows.json docs/superpowers/results/v139/2026-10-08-v139-armS-stage0.json docs/superpowers/results/v139/2026-10-08-v139-armS-stage1.json docs/superpowers/results/v139/2026-10-08-v139-armS-stage2.json
git commit -m "docs(v139): arm S Stage 0 <verdict>, Stage 1 <verdict, selected c>, Stage 2 <verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Add only the files that exist: a stage that never ran has no file.

---

### Task V139-13: Arm S Stage 3 — the one VALIDATION shot — and the arm S result record

**Files:**
- Create (generated): `docs/superpowers/results/v139/2026-10-08-v139-armS-validation-rows.json`, `...-armS-stage3.json`
- Create: `docs/superpowers/results/2026-10-08-v139-armS.md`

**Interfaces:**
- Consumes: arm S's `stage1.json` and `stage2.json` (`PASS`), and the committed record.
- Produces: arm S's final verdict and result record, which V139-16 consumes.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `--help` on each script this task calls (`measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py`, `permutation_test.py`); for every one that lists `--instrument` (v158 merged), append `--instrument v1` to each of its commands here, and the result record names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V139-11 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judges refuse the arms. If V139-12 wrote the v2 disclosure file, the Step 4 record quotes it in its own subsection headed "v2 disclosure (non-gating)"; it never enters the verdict.

If arm S closed earlier, skip Steps 1–3 and write the record (Step 4) for the stage it ended at.

- [ ] **Step 1: Pre-flight (nothing here reads VALIDATION)**

- `git log --oneline -- docs/superpowers/results/2026-10-08-v139-preregistration.md` prints the V139-11 commit.
- `git status --short docs/superpowers/results/v139/` is clean: every earlier stage file is committed.
- `ls docs/superpowers/results/v139/ | grep armS-stage3` prints nothing.
- Invoke `backtest-gate` and state, in the session, the selected c and that this is arm S's single shot.

- [ ] **Step 2: Fire the shot**

Dispatch `backtest-runner` with the two exports and:

```bash
python scripts/backtest/measure_confluence_stop.py --stage 3 --preregistration docs/superpowers/results/2026-10-08-v139-preregistration.md
```

Expected last line: `arm S stage 3: PASS -> ...` (exit 0) or `FAIL` (exit 1). **Whatever it prints is final.**
- If the process crashes after writing `-validation-rows.json`, run the same command again: the driver reuses the saved rows and does not replay.
- If it crashes before that file exists, nothing was read; run it again.

- [ ] **Step 3: Commit the generated files before interpreting them**

```bash
git add docs/superpowers/results/v139/2026-10-08-v139-armS-validation-rows.json docs/superpowers/results/v139/2026-10-08-v139-armS-stage3.json
git commit -m "docs(v139): arm S Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Write the arm S result record**

Invoke `pooled-numbers`. Write `docs/superpowers/results/2026-10-08-v139-armS.md`, reading every number from the stage JSON files:

- **Verdict line:** the stage the arm ended at, its verdict, and whether the VALIDATION budget is spent.
- **Stage −1 table:** per horizon/direction `plans`, `clamped`, the `d` buckets, and per c `applies` / `changed` / `rollback`; `identical_adjacent` and the partner's answer if asked.
- **Stage 0 table** (if run): per cell `observed_n`, `target_n`, `mde_r`, `powered`.
- **Stage 1 table** (if run): per cell `delta_expr`, `lo95`, `hi95`, `eligible`, `plateau`, the three clause verdicts from `gate.clauses`, and the selected c. Quote the selection rule from the record.
- **Stage 2 table** (if run): per fold year `n`, `delta_expr`, `reversed`; `measurable`, `reversed`.
- **Stage 3** (if run): the four clauses with `detail`, and `permutation_p`.
- **Disclosures** for the selected cell (or every cell, if Stage 1 did not select) on TRAIN and, if run, VALIDATION:
  - N per arm, ΔExpR and its 95% interval, ΔWR, flips both ways, exit mix;
  - median planned RR per arm;
  - `changed`, `rollback`, `median_d_changed`, `gap_through`, `fill_beyond_ceiling`;
  - `only_baseline_triggered` / `only_cell_triggered`, per-horizon N.
- **Observations:** what the numbers do and do not show.
  - Say plainly that 1R is larger in arm S, so the same price move is a smaller R. A ΔExpR in R is a ΔExpR in dollars only under fixed-dollar sizing (spec § Why).
  - Say how many fills the live path would have cancelled (`fill_beyond_ceiling`), and whether one horizon carries the result.

```bash
git add docs/superpowers/results/2026-10-08-v139-armS.md
git commit -m "docs(v139): arm S result record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V139-14: Arm D Stage 0, Stage 1 and Stage 2 (the v72 funnel)

**Files:**
- Modify: `docs/superpowers/results/2026-10-08-v139-armD.md` (append a section per stage)
- Create on Stage 1: `docs/superpowers/results/v139/2026-10-08-v139-armD-stage1.json`
- Create on Stage 2: `docs/superpowers/results/v139/2026-10-08-v139-armD-walkforward.json`
- Logs, not committed: `logs/v139/armD-selection-{3.0,4.0,5.0}.json`, `logs/v139/armD-mde-*.log`, `logs/v139/armD-disclosure.log`, `logs/v139/armD-stage1.log`, `logs/v139/armD-walkforward.json`

**Interfaces:**
- Consumes: arm D's `REACHABLE` (V139-11), the committed record, and these verified CLIs:
  - `measure_arms.py --stage {selection,walkforward} --knob A=v --out P --preregistration P`
  - `validate_component.py --stage {mde,selection,walkforward} [--arms P] --title T --window W [--train-effect-pp X] [--grid-arms V=P] [--mde-refused V] [--out-json P]`
- Produces: arm D's selected c and walk-forward verdict, which V139-15 consumes.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `--help` on each script this task calls (`measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py`, `permutation_test.py`); for every one that lists `--instrument` (v158 merged), append `--instrument v1` to each of its commands here, and the result record names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V139-11 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judges refuse the arms.

Skip this task if V139-11 closed arm D. **Stop on the first refusing or failing stage:** append its numbers to `...-armD.md`, commit (Step 6) and go to V139-15 Step 4.

- [ ] **Step 1: The three fold-train arms**

Invoke `backtest-gate`. One `backtest-runner` dispatch per cell, serially, each with the two exports:

```bash
PREREG=docs/superpowers/results/2026-10-08-v139-preregistration.md
python scripts/backtest/measure_arms.py --stage selection --knob CONFLUENCE_STOP_DROP_PCT=3.0 --preregistration $PREREG --out logs/v139/armD-selection-3.0.json
python scripts/backtest/measure_arms.py --stage selection --knob CONFLUENCE_STOP_DROP_PCT=4.0 --preregistration $PREREG --out logs/v139/armD-selection-4.0.json
python scripts/backtest/measure_arms.py --stage selection --knob CONFLUENCE_STOP_DROP_PCT=5.0 --preregistration $PREREG --out logs/v139/armD-selection-5.0.json
```

- [ ] **Step 2: Disclosure and sanity check (before any gate is read)**

```bash
for c in 3.0 4.0 5.0; do python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c_ = vc.load_arms('logs/v139/armD-selection-$c.json'); conf = lambda arm: sum(t.source == 'confluence' for t in arm); print('$c', json.dumps(removed_disclosure(b, c_)), 'confluence', conf(b), '->', conf(c_))"; done | tee logs/v139/armD-disclosure.log
```

Each check below is a "stop and report a bug" condition:
- `removed` > 0 in every cell, and `removed` strictly decreases from 3.0 to 5.0. Equal adjacent counts mean a degenerate cell. Compare with the census; if the census flagged it and the partner chose option 1, note it and go on, otherwise stop.
- Every removed trade is confluence: the strategy rows are byte-identical across arms. `changed` > 0 means a surviving trade's outcome moved, which arm D cannot do. Stop.

Record per cell in `...-armD.md`: `removed`, `added`, `changed`, `is_subset`, the pooled and confluence-only volume cut %, and the per-direction ΔWR / ΔExpR.

- [ ] **Step 3: Stage 0 MDE per cell**

Print each cell's fold-train ΔWR and ΔExpR:

```bash
for c in 3.0 4.0 5.0; do python -c "import sys; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.acceptance import delta_standardised_win_rate as dwr, delta_expectancy_r as dexp; b, c_ = vc.load_arms('logs/v139/armD-selection-$c.json'); print('$c', 'N', len(b), len(c_), 'dWR', dwr(b, c_), 'dExpR', dexp(b, c_))"; done
```

Then, with the two exports, one call per cell, passing that cell's printed ΔWR (a zero or negative ΔWR is passed as printed; it is refused, which is correct):

```bash
python scripts/backtest/validate_component.py --stage mde --arms logs/v139/armD-selection-3.0.json --train-effect-pp <dWR for 3.0> --title "v139 arm D c=3.0 MDE" --window "2018-06-01..2022-12-31" | tee logs/v139/armD-mde-3.0.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v139/armD-selection-4.0.json --train-effect-pp <dWR for 4.0> --title "v139 arm D c=4.0 MDE" --window "2018-06-01..2022-12-31" | tee logs/v139/armD-mde-4.0.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v139/armD-selection-5.0.json --train-effect-pp <dWR for 5.0> --title "v139 arm D c=5.0 MDE" --window "2018-06-01..2022-12-31" | tee logs/v139/armD-mde-5.0.log
```

Record per cell: baseline / component N, ΔWR, ΔExpR, paired and unpaired MDE, and `RESOLVABLE` or `REFUSED`. **Stop rule:** all three `REFUSED` closes arm D at Stage 0, budget intact.

- [ ] **Step 4: Stage 1 selection (fold-train only)**

With the two exports, adding one `--mde-refused <c>` per cell Stage 0 refused:

```bash
python scripts/backtest/validate_component.py --stage selection --grid-arms 3.0=logs/v139/armD-selection-3.0.json --grid-arms 4.0=logs/v139/armD-selection-4.0.json --grid-arms 5.0=logs/v139/armD-selection-5.0.json --title CONFLUENCE_STOP_DROP_PCT --window "2018-06-01..2022-12-31" --out-json docs/superpowers/results/v139/2026-10-08-v139-armD-stage1.json | tee logs/v139/armD-stage1.log
```

Copy every printed cell line (`eligible`, `failed`, ΔWR, ExpR, the disclosure including `added`) into `...-armD.md`. The printed plateau label reads `PULLBACK_DRYUP_MAX_RATIO`; that label is cosmetic (record). Pass: `verdict=selected`, and that c goes to Stage 2. **Stop rule:** `no-eligible-cell` or `spike` closes arm D at Stage 1, budget intact.

- [ ] **Step 5: Stage 2 walk-forward (free)**

One `backtest-runner` dispatch, with the two exports:

```bash
PREREG=docs/superpowers/results/2026-10-08-v139-preregistration.md
python scripts/backtest/measure_arms.py --stage walkforward --knob CONFLUENCE_STOP_DROP_PCT=<selected c> --preregistration $PREREG --out logs/v139/armD-walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --arms logs/v139/armD-walkforward.json --title "v139 arm D c=<selected c> walk-forward" --window "2021..2023 folds" --out-json docs/superpowers/results/v139/2026-10-08-v139-armD-walkforward.json
```

Pass: `PASS`. Record the three fold rows. **Stop rule:** anything else closes arm D at Stage 2, VALIDATION unspent.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/results/2026-10-08-v139-armD.md docs/superpowers/results/v139/2026-10-08-v139-armD-stage1.json docs/superpowers/results/v139/2026-10-08-v139-armD-walkforward.json
git commit -m "docs(v139): arm D Stage 0 <verdicts>, Stage 1 <verdict, selected c>, Stage 2 <verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Add only the files that exist.

---

### Task V139-15: Arm D Stage 3 — the one VALIDATION shot — and the arm D result record

**Files:**
- Create: `docs/superpowers/results/v139/2026-10-08-v139-armD-validation.md`, `.../2026-10-08-v139-armD-validation.json`
- Modify: `docs/superpowers/results/2026-10-08-v139-armD.md`
- Logs, not committed: `logs/v139/armD-validation.json`, `logs/v139/armD-permutation.log`

**Interfaces:**
- Consumes: arm D's Stage 2 `PASS` (V139-14), the committed record, `permutation_test.py --arms P --n 200 --seed 42`, `validate_component.py --stage validation --arms P --permutation-p p --title T --window W --out-md P --out-json P`.
- Produces: arm D's final verdict and its complete result record, which V139-16 consumes.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `--help` on each script this task calls (`measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py`, `permutation_test.py`); for every one that lists `--instrument` (v158 merged), append `--instrument v1` to each of its commands here, and the result record names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V139-11 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judges refuse the arms.

If arm D closed earlier, skip Steps 1–3 and finish the record (Step 4) for the stage it ended at.

- [ ] **Step 1: Pre-flight**

- `git log --oneline -- docs/superpowers/results/2026-10-08-v139-preregistration.md` prints the V139-11 commit.
- `git status --short -- swingbot/ scripts/backtest/ docs/superpowers/results/` is clean.
- `ls docs/superpowers/results/v139/ | grep armD-validation` prints nothing.
- Stages −1 to 2 all passed for arm D.
- Invoke `backtest-gate`, and state the selected c and that this is arm D's single shot.

- [ ] **Step 2: Fire the shot**

One `backtest-runner` dispatch for the producer, with the two exports:

```bash
PREREG=docs/superpowers/results/2026-10-08-v139-preregistration.md
python scripts/backtest/measure_arms.py --stage validation --knob CONFLUENCE_STOP_DROP_PCT=<selected c> --preregistration $PREREG --out logs/v139/armD-validation.json
```

Then, with the two exports:

```bash
python scripts/backtest/permutation_test.py --arms logs/v139/armD-validation.json --n 200 --seed 42 | tee logs/v139/armD-permutation.log
python scripts/backtest/validate_component.py --stage validation --arms logs/v139/armD-validation.json --permutation-p <p_value printed above> --title "v139 arm D c=<selected c> VALIDATION" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/v139/2026-10-08-v139-armD-validation.md --out-json docs/superpowers/results/v139/2026-10-08-v139-armD-validation.json
python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c = vc.load_arms('logs/v139/armD-validation.json'); print(json.dumps(removed_disclosure(b, c), indent=1))"
```

- If `permutation_test.py` prints a null `p_value`, omit `--permutation-p`: the missing p is a FAIL, as pre-registered.
- If it prints `refused:changed-outcomes`, a surviving trade's outcome moved. Arm D cannot do that (V139-14 Step 2 checked it on TRAIN), so stop and report a bug. The shot is spent either way; record it as it stands.

**Whatever the judge prints is final.**

- [ ] **Step 3: Commit the judge outputs before interpreting them**

```bash
git add docs/superpowers/results/v139/2026-10-08-v139-armD-validation.md docs/superpowers/results/v139/2026-10-08-v139-armD-validation.json
git commit -m "docs(v139): arm D Stage 3 VALIDATION -- <PASS|FAIL>, shot spent

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Finish the arm D result record**

Invoke `pooled-numbers`. Complete `docs/superpowers/results/2026-10-08-v139-armD.md`, modelled on `docs/superpowers/results/2026-10-05-v122-confluence.md`. Include:
- the verdict line, with the stage the arm ended at and the budget state;
- one section per stage reached, with its source arm file, window, universe size and the measured numbers;
- the pre-registered rule for that stage, quoted verbatim;
- the disclosure block: removed / added / changed, pooled and confluence-only volume cut, per-direction ΔWR and ΔExpR, the top-2 horizon share, and the one-direction statement;
- an honest observations section that says whether the dropped plans were the bad ones (clause 6, or why it was SKIPPED).

Every figure comes from a log under `logs/v139/` or a judge JSON.

```bash
git add docs/superpowers/results/2026-10-08-v139-armD.md
git commit -m "docs(v139): arm D result record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# Phase 5 — Close-out (sequential tail)

## Parallelisation (Phase 5)

Sequential: V139-16 records both arms (closed table and ledger, one commit). V139-17 runs the full suite after V139-16's possible help-text edit, then the release step and the close-out.

### Task V139-16: Record both arms — closed table and ledger together; on a pass, ask

**Files:**
- Modify: `docs/claude/backtest-methodology.md` ("Closed pre-registrations — do not re-run these")
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (via the script)
- Modify: `swingbot/config.py` (the two v139 Fields' `help`)
- On a pass only: `.env.example` (the v139 comment)
- Check, and edit only if a condensed rule changes: `AGENTS.md`

**Interfaces:**
- Consumes: `docs/superpowers/results/2026-10-08-v139-armS.md`, `...-armD.md` and the stage files.
- Produces: the closed-table rows, the ledger rows and the final config text that V139-17 verifies.

**Cross-plan (audit 2026-10-10):** no merge of `main` into the worktree before this task commits (the arms' `code_hash()` stamps must still match if a judge output is re-read); the merge happens in V139-17. The ledger rows' `--instrument` values stay as written below (they name each arm's gate instrument from the record).

Both knob defaults stay **0** in every outcome (index, Spec correction 7). `tests/backtesting/test_preregistration_ledger_file.py` fails when a closed-table row has no ledger row, so Steps 1 and 2 land in one commit.

- [ ] **Step 1: One row per arm in the closed table**

Invoke `pooled-numbers`. Insert two rows directly under the header separator of "Closed pre-registrations — do not re-run these" in `docs/claude/backtest-methodology.md` (newest first), in the table's columns (Component | Outcome | Record).

- **Component:**
  - `Confluence structural stop, arm S — keep the confluence level as the stop up to c ∈ {3, 4, 5}% less 0.25 headroom, target re-chosen, sized to fixed dollar risk (v139)`
  - `Confluence stop drop, arm D — no plan when the structural stop is beyond c ∈ {3, 4, 5}% (v139)`
- **Outcome:** a bold lead with the stage and the budget state, for example:
  - `**refused:zero-diff at Stage −1, budget intact.**`
  - `**UNDERPOWERED at Stage 0, budget intact.**`
  - `**NO_ELIGIBLE_CELL at Stage 1, budget intact.**`
  - `**FAILED its one VALIDATION shot. Spent and final.**`
  - `**PASS on VALIDATION at c = <c>, shot spent. Default stays 0 pending the partner.**`

  Then the measured numbers for that stage: TRAIN N, the MDEs or per-cell ΔExpR and lower bounds, fold counts, the VALIDATION clauses, and arm D's volume cut. Then the reopen clause, verbatim from the spec: arm S `Reopening needs "a stop rule other than the confluence level itself up to a ceiling c, sized to fixed dollar risk"`; arm D `Reopening needs "a drop rule other than structural distance beyond c"`. End with `Another grid, window or MDE ceiling is not a new mechanism.`
- **Record:** the arm's result record and `results/2026-10-08-v139-preregistration.md`.

- [ ] **Step 2: One ledger row per arm**

Invoke `pooled-numbers`. Map each verdict to the ledger enum:
- `refused:zero-diff` → `UNMEASURABLE` (the v123 precedent).
- `UNDERPOWERED`, `NO_ELIGIBLE_CELL` / `no-eligible-cell` / `spike`, or a Stage 2 `FAIL` → `NO-LIFT` (the v129 precedent).
- A VALIDATION `FAIL` → `FAIL`. A VALIDATION `PASS` → `PASS`.

`--n` is the decisive population the record names (the baseline N of the last stage run). `--exp-r` and `--p` are the VALIDATION component ExpR and permutation p when Stage 3 ran, else `null`.

```bash
python scripts/reports/preregistration_ledger.py --id v139-arm-s --date <verdict date> --hypothesis "Confluence structural stop, arm S: keep the level up to c in {3,4,5} less 0.25 headroom, dollar sizing (v139)" --instrument v2 --n <N> --exp-r <value|null> --p <value|null> --verdict <enum> --record docs/superpowers/results/2026-10-08-v139-armS.md
python scripts/reports/preregistration_ledger.py --id v139-arm-d --date <verdict date> --hypothesis "Confluence stop drop, arm D: no plan beyond structural distance c in {3,4,5} (v139)" --instrument v1 --n <N> --exp-r <value|null> --p <value|null> --verdict <enum> --record docs/superpowers/results/2026-10-08-v139-armD.md
```

Each call prints the BH q-value: reported, never gating. Then run `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`. Expected: pass.

- [ ] **Step 3: The Field help text**

In `swingbot/config.py`, replace the closing sentence of each v139 Field's `help` with the measured one. Use `CONFLUENCE_STRUCTURAL_STOP_PCT` for arm S and `CONFLUENCE_STOP_DROP_PCT` for arm D, for example: `"Closed: <verdict at stage> -- see the v139 closed row in docs/claude/backtest-methodology.md. Keep 0."` On a pass, write instead: `"Passed VALIDATION at c = <c> (results/2026-10-08-v139-arm<S|D>.md); default stays 0 until the partner decides."` On a pass, also name the selected c in the `.env.example` comment above that knob. Run:
- `python scripts/dev/testrun.py file tests/test_config_v139_confluence_stop.py`
- `python scripts/dev/testrun.py file tests/market/test_v115_strategy_work_off.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`

Expected: all pass. The defaults are unchanged, so the golden cannot move.

- [ ] **Step 4: Codex mirror**

`docs/claude/` changed. Check the mirror: `grep -n "closed pre-registration\|backtest-methodology" AGENTS.md`. `AGENTS.md` condenses the rule, not the table. If no condensed sentence changes, leave it untouched and say so in the commit body. Run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/results/preregistration-ledger.jsonl swingbot/config.py
# on a pass also: .env.example
git commit -m "docs(v139): close-out record -- arm S <verdict>, arm D <verdict>; ledger rows; defaults stay 0

AGENTS.md: <unchanged, no condensed rule moved | updated: ...>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: If an arm passed, ask the partner, one question per arm**

Skip when neither arm passed. Use `AskUserQuestion`, one question per message, recommended option first, and a separate question for each passing arm (the arms are never pooled).

- **Arm S passed.** Question: "v139 arm S passed VALIDATION at c = <c> (ΔExpR <point> [<lo>, <hi>]R). Live arm S plans carry a wider stop and fewer shares on resting orders, and are rejected unless the account sizes in `risk_pct` mode. What next?" Options:
  1. "Set CONFLUENCE_STRUCTURAL_STOP_PCT=<c> in production after I confirm risk_pct sizing (Recommended)": a production change, mirrored back per `mirror-prod`, outside this plan.
  2. "Leave it merged and inert for now".
- **Arm D passed.** Question: "v139 arm D passed VALIDATION at c = <c> (ΔWR <pp>, volume cut <pct>%). What next?" Options:
  1. "Set CONFLUENCE_STOP_DROP_PCT=<c> in production (Recommended)": also outside this plan.
  2. "Leave it merged and inert for now".

Record each answer in that arm's result record under `## Decision` and commit it (`docs(v139): partner decision on arm <S|D>`). This plan never sets a non-zero default or touches production.

---

### Task V139-17: Full-suite verification, complexity, release step and close-out

**Files:**
- No new feature files. Fix only failures this plan caused, through their narrow tests.
- Move: the index, the three parts and the spec into their `implemented/` folders.

**Interfaces:**
- Consumes: everything V139-0..16 changed.
- Produces: a green suite, the release decision and the closed plan.

- [ ] **Step 1: Full suite, once**

Dispatch the `test-runner` agent with `python scripts/dev/testrun.py full`. Green means `0 failed` and `0 xfailed`. A changed pass count is not a failure. If it is not green, fix forward from the failures the run names: they are this plan's regressions. Before blaming a change for a failure in a shared-DB test, run that file alone and compare with `main` (`docs/claude/testing-cost.md`).

- [ ] **Step 2: The repository round trip is not skipped**

```bash
docker compose --profile test up -d db-test
python -m pytest tests/db/test_plans_repository.py -k v139 -rs -v
```

Expected: `test_v139_stop_ceiling_pct_rides_in_the_doc PASSED`, and no `SKIPPED` line (spec § Testing).

- [ ] **Step 3: Complexity over every file the plan touched**

```bash
python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/planning/stop_scope.py swingbot/core/planning/plan_types.py swingbot/core/scanning/analyze.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py swingbot/core/backtesting/confluence_stop_replay.py swingbot/core/backtesting/confluence_stop_funnel.py scripts/backtest/measure_confluence_stop.py scripts/backtest/measure_arms.py
```

No function this plan wrote or changed may be listed: `build_confluence_plan` must be absent. These pre-existing entries may remain, because this plan did not touch them:
- `build_strategy_plan - C (13)`;
- `_scan_one - E (36)` and `build_decision_context - D (24)` in `analyze.py`.

Confirm any other listed function was already there with `git show main:<file> | python -m radon cc -s -n C -`.

- [ ] **Step 4: Release step (header: `Bump: none`)**

Read `VERSION.json` now, as it is on disk at this moment (concurrent sessions bump it): never a number from this plan, the spec or memory. `Bump: none` holds in every outcome: both knobs ship at 0, the only live-path differences are inert at 0, and `stop_ceiling_pct` is `null` on every plan (index, Spec correction 7). So make **no** `VERSION.json` edit and no version-matrix regeneration. Say so in the close-out commit body. If the partner's V139-16 answer changed a production setting, that change is its own mirrored commit with its own bump, outside this plan.

- [ ] **Step 5: Close the plan out**

Read `docs/claude/document-lifecycle.md` and invoke the `worktree-lifecycle` skill before merging.
- Amend `Edge:` in the index header with one clause when the outcome differs from the prediction, for example `Edge: expectancy — predicted; measured no lift, arm S <verdict>, arm D <verdict>`. Amend `Bump:` only if Step 4 found a reason (it should not).
- Move the index, the three parts and the spec to `docs/superpowers/plans/implemented/` and `docs/superpowers/specs/implemented/`. The code merges inert, so this is `implemented/`, not `no-lift/` (the v129 precedent). Fix the index's `**Spec:**` link and every cross-link the move breaks: `git grep -n "v139-confluence-stop-geometry" -- docs/ CLAUDE.md AGENTS.md swingbot/ tests/ .claude/`.
- Merge the branch to `main` per the skill. A conflict-free merge gets no second suite run. A merge that resolved conflicts is new code: run `python scripts/dev/testrun.py full` once more through `test-runner`. Conflicts are most likely with v135 in `config.py`, `scan_params.py`, `reachability.py`, `analyze.py` or `backtest_scenarios.py` (index, Cross-plan overlap). After any such resolution, also re-run `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`.
- Remove the worktree per `document-lifecycle.md`. Never delete a branch whose name contains `backup` or starts with `stable-`.

```bash
git add -A docs/superpowers/plans docs/superpowers/specs
git commit -m "docs(v139): close out confluence stop geometry into implemented/

Bump: none -- both knobs ship at 0; VERSION.json untouched.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
