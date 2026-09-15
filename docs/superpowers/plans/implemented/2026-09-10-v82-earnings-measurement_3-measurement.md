# v82 — Earnings Blackout Measurement, Part 3: The Measurement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Index, Global Constraints and Parallelisation: `2026-09-10-v82-earnings-measurement_0-index.md`.

**Bump:** none for this part (results docs only; M7 carried the plan's release)
**Edge:** expectancy

## How this part runs

- **All of it runs from the main checkout**, after M7's merge. It changes no
  code: no test runs, no full suite.
- **Sequential throughout.** Each task consumes the previous task's committed
  result, and M10, M11, M12 and M13 each end early by jumping to M14 on a
  negative verdict. A negative verdict is a finished measurement, not a reason
  to adjust anything and retry (`docs/claude/backtest-methodology.md`).
- `<run-date>` below is the date the task's command actually runs,
  `YYYY-MM-DD`. Results docs go to `docs/superpowers/results/`.
- Read `docs/claude/backtest-methodology.md` before M10.

---

### Task M8: Earnings data and a timed dry run

**Files:**
- Create (local, gitignored): `market_data/earnings/<SYM>.csv`
- Create: `docs/superpowers/results/<run-date>-v82-earnings-data.md`

**Interfaces:**
- Consumes: `scripts/data/fetch_earnings_dates.py` (M5), `measure_earnings_blackout.py replay` (M6).
- Produces: the CSV cache Run 1 reads, and a measured per-ticker replay cost for M9's dispatch.

- [x] **Step 1: Confirm the OHLCV cache**

Run: `python -c "from pathlib import Path; print(len(list(Path('data/backtest_cache').glob('*.csv'))))"`
Expected: the cached ticker count (89 on 2026-09-10). If 0, run `python scripts/data/fetch_backtest_data.py` first.

- [x] **Step 2: Fetch earnings dates**

Run: `python scripts/data/fetch_earnings_dates.py`
Expected: one line per ticker and a closing `written N | skipped 0 | ETF E | no data M`. Exit 1 when `M > 0` is **not** a stop: those tickers stay uncovered, and the coverage floor in M10 decides whether that matters. Re-running with the same arguments only fills gaps.

- [x] **Step 3: Time one full-width ticker**

Run, timing it (PowerShell `Measure-Command { ... }` or bash `time`):

```bash
python scripts/backtest/measure_earnings_blackout.py replay --run run1 --tickers AAPL --workers 1 --out-root data/v82-dry
```

Expected: `[1/1] AAPL: N rows` and `complete: N rows`. Record wall-clock seconds `T`. Projected Run 1 wall clock ≈ `T × <cached ticker count> / <worker count>`, where the worker count is the machine's CPU count (the replay's default). Then delete `data/v82-dry/`.

- [x] **Step 4: Write the data record**

Create `docs/superpowers/results/<run-date>-v82-earnings-data.md`:

```markdown
# v82 earnings blackout — earnings data and replay cost

Not a stage. Records the inputs Run 1 reads, before Run 1 starts.

## Earnings dates (Yahoo, scripts/data/fetch_earnings_dates.py)

<paste the fetch script's closing summary line verbatim>

Tickers with no data: <list them, or "none">

## Replay cost

One ticker (AAPL), all 10 horizons, 11 strategies plus the confluence replay,
window 2018-06-01..2023-12-31, serial: <T> s.
Projected Run 1: <T> s × <tickers> / <workers> workers ≈ <hours> h.
```

- [x] **Step 5: Commit**

```bash
git add docs/superpowers/results/<run-date>-v82-earnings-data.md
git commit -m "docs(v82): earnings data coverage and replay cost before Run 1"
```

---

### Task M9: Run 1 — 2018-06-01..2023-12-31

**Files:**
- Create (local, gitignored): `data/v82/run1/*.jsonl`, `data/v82/run1/calendar.json`

**Interfaces:**
- Consumes: M8's CSVs and cost projection.
- Produces: the Run 1 exposure table that M10–M12 read.

- [x] **Step 1: Dispatch `backtest-runner` in the background**

Dispatch the `backtest-runner` subagent (`run_in_background`) with exactly this brief:

> From the main checkout of `E:\Documents\Private\Projects\Discord-Bot`, run
> `python scripts/backtest/measure_earnings_blackout.py replay --run run1`.
> It prints one line per ticker and keeps `data/v82/run1/progress.txt`
> ("N/M tickers (P%)") current; it deletes that file when it ends. If the
> process dies, re-run the same command — finished tickers are skipped. When
> it prints `complete:`, run
> `python scripts/backtest/measure_earnings_blackout.py coverage --run run1 --window 2018-06-01..2023-12-31`.
> Return only: the `complete:` line, the full `coverage` output, and its exit
> code. Never pass `--run run2`. Edit no files.

Expected duration: M8's projection. Answer any "how far along" question from `data/v82/run1/progress.txt`, never from the subagent's transcript.

- [x] **Step 2: Record the result in the task report**

Copy the `complete:` line and the coverage output into the task report. Coverage exit code 2 here is **not** a stop: M10 applies the floor to the selection window specifically.

---

### Task M10: Stage 1 — selection

**Files:**
- Create: `docs/superpowers/results/<run-date>-v82-earnings-blackout-stage1.md` and `.json`

**Interfaces:**
- Consumes: Run 1 rows.
- Produces: the selected K (or a terminal verdict).

- [ ] **Step 1: Run the pre-registered selection**

```bash
python scripts/backtest/measure_earnings_blackout.py select --out-md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage1.md --out-json docs/superpowers/results/<run-date>-v82-earnings-blackout-stage1.json
```

- [ ] **Step 2: Commit the result as written — before reading anything into it**

```bash
git add docs/superpowers/results/<run-date>-v82-earnings-blackout-stage1.md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage1.json
git commit -m "docs(v82): stage 1 selection -- <verdict as printed>"
```

(`INSUFFICIENT_COVERAGE` writes only the `.md`; add just that file.)

- [ ] **Step 3: Branch on the verdict**

- `SELECTED — K = k` → carry `k` to M11.
- `NO_ELIGIBLE_K`, `SPIKE`, or `INSUFFICIENT_COVERAGE` → go to M14 with that verdict. Do not change the grid, window or rule.

---

### Task M11: Stage 0 — minimum detectable effect

**Files:**
- Create (local): `data/v82/arms_mde.json`
- Create: `docs/superpowers/results/<run-date>-v82-earnings-blackout-stage0.md`

**Interfaces:**
- Consumes: M10's `k`; Run 1 rows.
- Produces: RESOLVABLE (continue) or REFUSED (budget intact).

- [ ] **Step 1: Build the selection-window arms**

```bash
python scripts/backtest/measure_earnings_blackout.py arms --stage mde --k <k> --out data/v82/arms_mde.json
```

Expected: a line `--train-effect-pp <effect> --observed-days 945 --target-days 730`. If `<effect>` is `None`, there were no decided trades: record REFUSED and go to M14.

- [ ] **Step 2: Run the MDE gate**

```bash
python scripts/backtest/validate_component.py --stage mde --arms data/v82/arms_mde.json --title "v82 earnings blackout K=<k>" --window "2018-06-01..2020-12-31" --train-effect-pp <effect> --observed-days 945 --target-days 730
```

Expected: ends in `RESOLVABLE` (exit 0) or `REFUSED` (exit 1).

- [ ] **Step 3: Write and commit the record**

Create `docs/superpowers/results/<run-date>-v82-earnings-blackout-stage0.md`:

```markdown
# v82 earnings blackout — Stage 0 (MDE), K = <k>

Window: 2018-06-01..2020-12-31 (fold-train). Pre-registered by spec v82 B4.

    <paste validate_component.py's full printed output verbatim>

**Verdict: <RESOLVABLE | REFUSED>**
```

```bash
git add docs/superpowers/results/<run-date>-v82-earnings-blackout-stage0.md
git commit -m "docs(v82): stage 0 MDE -- <RESOLVABLE|REFUSED>"
```

- [ ] **Step 4: Branch**

RESOLVABLE → M12. REFUSED → M14 ("unresolvable, budget intact").

---

### Task M12: Stage 2 — walk-forward

**Files:**
- Create (local): `data/v82/arms_walkforward.json`
- Create: `docs/superpowers/results/<run-date>-v82-earnings-blackout-stage2.md` and `.json`

**Interfaces:**
- Consumes: M10's `k`; Run 1 rows.
- Produces: PASS (unlocks Run 2) or FAIL.

- [ ] **Step 1: Build the fold arms**

```bash
python scripts/backtest/measure_earnings_blackout.py arms --stage walkforward --k <k> --out data/v82/arms_walkforward.json
```

Expected exit 0. Exit 2 (a fold below the coverage floor) → record `INSUFFICIENT_COVERAGE` in a Stage 2 doc with the printed lines, commit it, and go to M14.

- [ ] **Step 2: Run the walk-forward gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward --arms data/v82/arms_walkforward.json --title "v82 earnings blackout K=<k>" --window "fold-test 2021 / 2022 / 2023" --out-md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage2.md --out-json docs/superpowers/results/<run-date>-v82-earnings-blackout-stage2.json
```

Expected: `PASS` or `FAIL`; the `.md` ends `**Overall: PASS**` or `**Overall: FAIL**`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/<run-date>-v82-earnings-blackout-stage2.md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage2.json
git commit -m "docs(v82): stage 2 walk-forward -- <PASS|FAIL>"
```

- [ ] **Step 4: Branch**

PASS → M13. FAIL → M14.

---

### Task M13: Run 2 and Stage 3 — the one VALIDATION shot

**Files:**
- Create (local, gitignored): `data/v82/run2/*.jsonl`, `data/v82/arms_validation.json`
- Create: `docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3.md`, `.json`, and `-permutation.json`

**Interfaces:**
- Consumes: M10's `k`; M12's committed PASS doc.
- Produces: the final verdict. **This spends the component's one shot.** Nothing here is ever re-run.

- [ ] **Step 1: Dispatch Run 2 to `backtest-runner` in the background**

Brief:

> From the main checkout, run
> `python scripts/backtest/measure_earnings_blackout.py replay --run run2 --stage2-doc docs/superpowers/results/<stage 2 doc filename>`.
> Progress is `data/v82/run2/progress.txt`; re-run the same command if the
> process dies. When it prints `complete:`, run
> `python scripts/backtest/measure_earnings_blackout.py coverage --run run2 --window 2024-01-01..2025-12-31`.
> Return only the `complete:` line, the coverage output and its exit code.
> Edit no files.

- [ ] **Step 2: Build the validation arms**

```bash
python scripts/backtest/measure_earnings_blackout.py arms --stage validation --k <k> --out data/v82/arms_validation.json
```

Expected exit 0. Exit 2 → record `INSUFFICIENT_COVERAGE` (budget intact — the arms were never scored) in the Stage 3 doc, commit, go to M14.

- [ ] **Step 3: Compute the pre-registered permutation p**

```bash
python scripts/backtest/measure_earnings_blackout.py permute --k <k> --out-json docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3-permutation.json
```

Expected: JSON with `p_value`, `n: 200`, `seed: 42`, `shift_range: [20, 200]`. If `p_value` is `null`, omit `--permutation-p` in Step 4 — the gate then FAILs clause 5 by construction, which is the pre-registered outcome.

- [ ] **Step 4: Run the gate**

```bash
python scripts/backtest/validate_component.py --stage validation --arms data/v82/arms_validation.json --title "v82 earnings blackout K=<k>" --window "2024-01-01..2025-12-31" --permutation-p <p_value> --out-md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3.md --out-json docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3.json --notes "Permutation: calendar shift, n=200, seed=42, U[20,200) sessions (spec v82 B4). Limitations: see the Stage 1 doc."
```

Expected: the rendered clause table and a PASS/FAIL verdict. (The script writes its PRE-REGISTERED skeleton to the same paths before evaluating, by design.)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3.md docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3.json docs/superpowers/results/<run-date>-v82-earnings-blackout-stage3-permutation.json
git commit -m "docs(v82): stage 3 VALIDATION -- <PASS|FAIL>, budget spent"
```

---

### Task M14: Record the outcome and close out

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed-pre-registrations table, after the `DEAD_CAT_BOUNCE_VETO (v68)` row, line 135)
- Modify: `docs/superpowers/specs/2026-09-10-v82-earnings-awareness-design.md` (a `## Status` section directly under the header block)
- Move: `docs/superpowers/plans/2026-09-10-v82-earnings-measurement_*.md` → `docs/superpowers/plans/implemented/`
- Modify: `docs/superpowers/plans/2026-09-10-v82-earnings-measurement_0-index.md` (Progress block, before moving)

**Interfaces:**
- Consumes: whichever results docs M8–M13 committed.
- Produces: the permanent record. The spec **stays** at the top level — Plan A still builds from it.

- [ ] **Step 1: Add the closed-pre-registrations row**

Insert one row, filling every `<…>` **verbatim from the committed results docs** (numbers copied, never recomputed or rounded differently):

```markdown
| `EARNINGS_BLACKOUT_SESSIONS` (v82) | **<PASS | FAIL | REFUSED | NO ELIGIBLE K | SPIKE | INSUFFICIENT COVERAGE>, <budget spent | budget intact>.** Exposure = next earnings reaction session 1..K sessions after the signal bar; grid K ∈ {1, 2, 3, 5}; confluence replay + 11 strategy backtests, all horizons, <tickers> cached tickers. Stage 1 (2018-06..2020-12): <verdict, selected K, its dWR and dExpR>. <Stage 0: MDE <x>pp vs effect <y>pp — only if reached.> <Stage 2: per-fold dWR 2021/2022/2023 — only if reached.> <Stage 3: clause verdicts and permutation p — only if reached.> Default <stays 0 | flips to K=<k> in Plan A's C4 release>. <For any verdict other than PASS: Do not re-run; a genuinely different exposure rule needs a new pre-registration.> | <every committed results doc path from M8-M13> |
```

A stage that was never reached is left out of the row, not written as "n/a".

- [ ] **Step 2: Add a Status section to the spec**

Directly below the spec's header block (after the `**Depends on:**` paragraph), insert:

```markdown
## Status

| Part | State |
|---|---|
| Phase A — label, notice, stored fields | not started (Plan A; needs v81 merged) |
| Phase B — measurement | **<verdict>**, <budget spent | budget intact> — `docs/superpowers/plans/implemented/2026-09-10-v82-earnings-measurement_0-index.md` and the results docs it lists |
| C1 — wiring into `scan_run.py` | not started (Plan A) |
| C2/C3 — rename, frozen class, wf_components note | done in Plan B M3 |
| C4 — default flip | <"to K=<k>, in Plan A, as its own release" if PASS; otherwise "void — default stays 0"> |
```

- [ ] **Step 3: Close the plan**

Tick M8–M14 in the index's Progress block. If the plan ended early, tick the tasks that ran and add one line under Progress: `Ended at <task> with <verdict>; later tasks correctly not run.` Then:

```bash
git mv docs/superpowers/plans/2026-09-10-v82-earnings-measurement_0-index.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v82-earnings-measurement_1-foundation.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v82-earnings-measurement_2-instrument.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v82-earnings-measurement_3-measurement.md docs/superpowers/plans/implemented/
```

Re-point references (`document-lifecycle.md` "Fix the references in the same commit"):

Run: `git grep -n "plans/2026-09-10-v82-earnings-measurement"`
Expected after fixing: every hit reads `plans/implemented/2026-09-10-v82-earnings-measurement`.

- [ ] **Step 4: Commit**

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/specs/2026-09-10-v82-earnings-awareness-design.md docs/superpowers/plans/implemented/
git commit -m "docs(v82): close earnings blackout measurement -- <verdict>"
```

- [ ] **Step 5: Remove the worktree**

```bash
git rev-list --count main..2026-09-10-v82-earnings-measurement
```

Expected `0` (everything merged in M7). Then `git worktree remove .claude/worktrees/2026-09-10-v82-earnings-measurement`. **Leave the branch** — deleting it is the human partner's call (`docs/claude/git-safety.md`). Delete `data/v82/arms_*.json` only if the partner agrees; the shards under `data/v82/run*/` are regenerable but hours of compute.

- [ ] **Step 6: Tell the human partner**

Report: the verdict, the committed results docs, whether Plan A's C4 now has a K to flip, and that Plan A (label, notice, wiring) is next once v81 is merged.
