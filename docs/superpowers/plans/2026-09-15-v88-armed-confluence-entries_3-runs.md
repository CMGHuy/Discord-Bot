# v88 Armed Confluence Entries — Part 3: the runs

> Header, global constraints, parallelisation and outcomes live in `2026-09-15-v88-armed-confluence-entries_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 3 — Measurement runs (on `main`, after AR8's merge)

Every task here runs on `main` in the main tree. `<run-date>` is the date (`YYYY-MM-DD`) the command in that task finishes; `<cell>` is the cell id AR10 selects. **Commit each result as written before reading anything into it.** A verdict that ends the measurement goes straight to AR14 — the grid, windows, rule and constants never change.

### Task AR9: Run 1 replay

**Files:**
- Create (local, not committed): `data/v88/run1/*.jsonl`, `*.counts.json`, `run.json`
- Create: `docs/superpowers/results/<run-date>-v88-armed-run1.md`

**Interfaces:**
- Consumes: the merged code (AR1–AR7); `data/backtest_cache/*.csv`.
- Produces: Run 1 rows (2018-06-01..2023-12-31) for the baseline and all 24 cells.

- [ ] **Step 1: Confirm the cache covers both runs**

```bash
python -c "import pandas as pd, glob; f=sorted(glob.glob('data/backtest_cache/*.csv')); d=[pd.read_csv(p, index_col='Date', parse_dates=True).index for p in f]; print(len(f), 'files', min(i.min() for i in d).date(), '->', min(i.max() for i in d).date())"
```

Expected: ~89 files, earliest `2018-06-01`, and the smallest last date on or after `2025-12-31` (Run 2 needs it; exits near a window's end need bars past it). If the last date falls short, run `python scripts/data/fetch_backtest_data.py` once and re-check. Do not start the replay on a short cache — `run.json` pins the file list, and a later refetch would refuse the resume.

- [ ] **Step 2: Dispatch the replay to `backtest-runner`**

Brief: run `python scripts/backtest/measure_armed_entries.py replay --run run1` from the repo root; it is resumable (re-running skips finished tickers); answer progress questions from `data/v88/run1/progress.txt`; report the final `complete: N rows` line, the elapsed time, and any traceback verbatim.

Expected: exit 0, `complete: <N> rows`, no `progress.txt` left behind.

- [ ] **Step 3: Summarise and commit**

```bash
python scripts/backtest/measure_armed_entries.py summary --run run1 --window 2018-06-01..2023-12-31 --out-md docs/superpowers/results/<run-date>-v88-armed-run1.md
git add docs/superpowers/results/<run-date>-v88-armed-run1.md
git commit -m "docs(v88): run 1 replay complete"
```

---

### Task AR10: Stage 1 — selection

**Files:**
- Create: `docs/superpowers/results/<run-date>-v88-armed-stage1.md` and `.json`

**Interfaces:**
- Consumes: Run 1 rows.
- Produces: `<cell>` and its selection-window `ΔWR`, or a terminal verdict.

- [ ] **Step 1: Run the pre-registered selection**

```bash
python scripts/backtest/measure_armed_entries.py select --out-md docs/superpowers/results/<run-date>-v88-armed-stage1.md --out-json docs/superpowers/results/<run-date>-v88-armed-stage1.json
```

Expected: `verdict: SELECTED; selected: <cell>` (exit 0), or `NO_ELIGIBLE_CELL` / `SPIKE` (exit 1), or exit 2 if the window holds no rows (a broken run — stop and debug; that is not a verdict).

- [ ] **Step 2: Commit the result as written**

```bash
git add docs/superpowers/results/<run-date>-v88-armed-stage1.md docs/superpowers/results/<run-date>-v88-armed-stage1.json
git commit -m "docs(v88): stage 1 selection -- <verdict as printed>"
```

- [ ] **Step 3: Branch on the verdict**

- `SELECTED` → read `<cell>`'s `delta_win_rate_pp` from the JSON's `scores` list; carry both to AR11.
- `NO_ELIGIBLE_CELL` or `SPIKE` → go to AR14 with that verdict.

---

### Task AR11: Stage 0 — minimum detectable effect

**Files:**
- Create (local): `data/v88/arms_mde.json`
- Create: `docs/superpowers/results/<run-date>-v88-armed-stage0.md`

**Interfaces:**
- Consumes: AR10's `<cell>` and `<effect>` (its `delta_win_rate_pp`).
- Produces: RESOLVABLE (continue) or REFUSED (budget intact).

- [ ] **Step 1: Build the selection-window arms**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage mde --cell <cell> --out data/v88/arms_mde.json
```

Expected: exit 0.

- [ ] **Step 2: Run the MDE gate**

```bash
python scripts/backtest/validate_component.py --stage mde --arms data/v88/arms_mde.json --title "v88 armed confluence entries <cell>" --window "2018-06-01..2020-12-31" --train-effect-pp <effect> --observed-days 945 --target-days 730
```

Expected: ends in `RESOLVABLE` (exit 0) or `REFUSED` (exit 1).

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v88-armed-stage0.md`:

```markdown
# v88 armed confluence entries — Stage 0 (MDE)

**Verdict: <RESOLVABLE | REFUSED>**

Cell: <cell>. Window: 2018-06-01..2020-12-31. Train effect: <effect>pp.
Observed/target days: 945 / 730.

## Gate output (verbatim)

<paste the command's full stdout>
```

```bash
git add docs/superpowers/results/<run-date>-v88-armed-stage0.md
git commit -m "docs(v88): stage 0 MDE -- <verdict>"
```

`REFUSED` → AR14, budget intact.

---

### Task AR12: Stage 2 — walk-forward

**Files:**
- Create (local): `data/v88/arms_walkforward.json`
- Create: `docs/superpowers/results/<run-date>-v88-armed-stage2.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; Run 1 rows for 2021, 2022, 2023.
- Produces: the doc AR13's replay lock reads.

- [ ] **Step 1: Build the fold arms**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage walkforward --cell <cell> --out data/v88/arms_walkforward.json
```

Expected: exit 0 (exit 2 means a fold year has no baseline rows — a broken run, not a verdict).

- [ ] **Step 2: Run the gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward --arms data/v88/arms_walkforward.json --title "v88 armed confluence entries <cell>" --window "fold-test 2021 / 2022 / 2023" --out-md docs/superpowers/results/<run-date>-v88-armed-stage2.md --out-json docs/superpowers/results/<run-date>-v88-armed-stage2.json
```

Expected: `PASS` (exit 0) or `FAIL` (exit 1); the `.md` ends `**Overall: <verdict>**`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/<run-date>-v88-armed-stage2.md docs/superpowers/results/<run-date>-v88-armed-stage2.json
git commit -m "docs(v88): stage 2 walk-forward -- <verdict>"
```

`FAIL` → AR14, budget intact.

---

### Task AR13: Stage 3 — VALIDATION, one shot

**This spends the budget. It runs once, ever.** Nothing after Step 1 may be retried with a different cell, window, seed, or rule; a crash is resumed, never re-scored.

**Files:**
- Create (local): `data/v88/run2/*`, `data/v88/arms_validation.json`
- Create: `docs/superpowers/results/<run-date>-v88-armed-run2.md`, `<run-date>-v88-armed-permutation.json`, `<run-date>-v88-armed-validation.md` and `.json`

**Interfaces:**
- Consumes: `<cell>`; AR12's PASS doc.
- Produces: the VALIDATION verdict.

- [ ] **Step 1: Dispatch the Run 2 replay to `backtest-runner`**

Brief: run `python scripts/backtest/measure_armed_entries.py replay --run run2 --stage2-doc docs/superpowers/results/<AR12 run-date>-v88-armed-stage2.md`; resumable; progress from `data/v88/run2/progress.txt`; report `complete: N rows`, elapsed time, any traceback verbatim.

Expected: exit 0. Exit 3 means the doc does not read `**Overall: PASS**` — stop; do not edit the doc.

- [ ] **Step 2: Summarise Run 2 and commit**

```bash
python scripts/backtest/measure_armed_entries.py summary --run run2 --window 2024-01-01..2025-12-31 --out-md docs/superpowers/results/<run-date>-v88-armed-run2.md
git add docs/superpowers/results/<run-date>-v88-armed-run2.md
git commit -m "docs(v88): run 2 replay complete"
```

- [ ] **Step 3: Dispatch the permutation to `backtest-runner`**

Brief: run `python scripts/backtest/measure_armed_entries.py permute --cell <cell> --out-json docs/superpowers/results/<run-date>-v88-armed-permutation.json`; progress from `data/v88/run2/progress.txt`; report the `permutation p = ...` line.

Expected: exit 0 and a numeric `p`. A `None` p is carried into Step 5 as a missing permutation — which the gate scores FAIL. Do not re-run with another seed.

```bash
git add docs/superpowers/results/<run-date>-v88-armed-permutation.json
git commit -m "docs(v88): permutation null -- p=<p>"
```

- [ ] **Step 4: Build the VALIDATION arms**

```bash
python scripts/backtest/measure_armed_entries.py arms --stage validation --cell <cell> --out data/v88/arms_validation.json
```

- [ ] **Step 5: Run the gate — once**

```bash
python scripts/backtest/validate_component.py --stage validation --arms data/v88/arms_validation.json --title "v88 armed confluence entries <cell>" --window "2024-01-01..2025-12-31" --permutation-p <p> --notes "Clause 6 is SKIPPED by design: armed entries change which trades are taken, so population_split sees added and changed trades (spec §4.1). Recorded limitations: daily-bar ordering is conservative (stop before target on the same bar); the universe is today's cached tickers (survivorship); M2's market entry fills at a daily close a live reader could not have traded." --out-md docs/superpowers/results/<run-date>-v88-armed-validation.md --out-json docs/superpowers/results/<run-date>-v88-armed-validation.json
```

If `<p>` was `None`, omit `--permutation-p`; the gate records the missing null as FAIL.

Expected: `PASS` (exit 0) or `FAIL` (exit 1). The gate writes a PENDING skeleton before scoring; both files are overwritten with the verdict.

- [ ] **Step 6: Commit the verdict as written**

```bash
git add docs/superpowers/results/<run-date>-v88-armed-validation.md docs/superpowers/results/<run-date>-v88-armed-validation.json
git commit -m "docs(v88): VALIDATION -- <verdict>"
```

---

### Task AR14: Close-out

Runs whatever verdict ended the measurement.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Move: `docs/superpowers/plans/2026-09-15-v88-armed-confluence-entries_*.md` and `docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md` → `implemented/` (the code reached `main`, so not `no-lift/`; `document-lifecycle.md`)

- [ ] **Step 1: Add the closed-table row**

Append a row to `### Closed pre-registrations — do not re-run these` in `docs/claude/backtest-methodology.md`, in the table's existing three-column shape. The component cell reads `Armed confluence entries — test + reaction at the stop level (v88)`. The outcome cell states, in this order: the verdict in bold with `budget intact` or `budget spent`; the stage it ended at; the selected cell (or that none was selected); the numbers that decided it (Stage 1: the best cell's cut %, ΔWR, ΔExpR; Stage 2: per-fold ΔWR; Stage 3: every clause's detail line); and one sentence on what reopening would need (**a new mechanism**, not a looser threshold or another grid over these knobs). The record cell lists the results docs by path.

- [ ] **Step 2: Record A2's status in the spec**

Append to the spec's §4.4: `**Outcome (<date>):** <verdict> at <stage>; A2 <is not written | is brainstormed next>.` If the verdict is PASS, also say so in the close-out commit message so the next session picks A2 up.

- [ ] **Step 3: Amend `Edge:` only if the prediction was wrong**

A negative measurement stays `Edge: expectancy` with `Bump: none` (`document-conventions.md`: removing or failing to find edge is still an expectancy result). Change nothing unless the work turned out to buy something other than what was predicted, and then say why in one clause.

- [ ] **Step 4: Move the documents and commit**

```bash
git mv docs/superpowers/plans/2026-09-15-v88-armed-confluence-entries_0-index.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-15-v88-armed-confluence-entries_1-replay.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-15-v88-armed-confluence-entries_2-instrument.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-15-v88-armed-confluence-entries_3-runs.md docs/superpowers/plans/implemented/
git mv docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md docs/superpowers/specs/implemented/
git add docs/claude/backtest-methodology.md
git commit -m "docs(v88): close out armed confluence entries -- <verdict>"
```

- [ ] **Step 5: Remove the worktree**

Per `document-lifecycle.md`: confirm the branch is merged (`git rev-list --count main..2026-09-15-v88-armed-confluence-entries` prints `0`), then `git worktree remove .claude/worktrees/2026-09-15-v88-armed-confluence-entries`. The branch name contains neither `backup` nor `stable-`; still, delete the branch only if `document-lifecycle.md` says to, and never with a non-zero count.
