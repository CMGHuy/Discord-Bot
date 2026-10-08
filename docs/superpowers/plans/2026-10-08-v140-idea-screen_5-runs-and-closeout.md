# v140 Idea screen: Implementation Plan, part 5 — the four screens, close-out, full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Review Focus, Frozen readings and Parallelisation live in [`_0-index`](2026-10-08-v140-idea-screen_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`.

**Spec:** [`docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`](../specs/2026-10-08-v140-idea-screen-design.md)

# Phase 5 — The four screens (strictly one at a time), close-out, full suite

**Sequential throughout.** Each screen appends to the one shared ledger file, so a run may start only after the previous run's row is committed. Order is the registry order (`IDEA_MODULES`): `high52w`, `uptrend_pullback`, `gap_volume`, `turn_of_month`. The order carries no information: every idea gets exactly one run whatever the others show, and **no result changes any parameter of any idea** (they were frozen in V140-2, before any run).

**What a run may and may not do after it starts:**
- A crash, traceback or `refused:` **before** the ledger row is appended recorded no verdict. Fix the cause in the code with a failing test first (a normal TDD fix on this branch, committed), then dispatch the same run again. Never change a trigger, a cap, K, the seed, the window or the pass rule to make it run.
- Once the row is appended, the idea is closed by its verdict. Never re-run it, never edit or delete its row, never edit its results doc's numbers. A bug found afterwards is reported to the partner (`AskUserQuestion`); a corrected measurement would be a new idea with a new name and its own row, and only the partner can authorise that.

### Task V140-15: Screen `high52w` — 52-week-high momentum (George & Hwang 2004), one shot

**Files:**
- Create (written by the script): `docs/superpowers/results/<run-date>-screen-high52w.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: `scripts/backtest/screen_idea.py` (V140-14), `IDEAS["high52w"]` (V140-2 constants, trigger from its Group A task), the `screen-v1` / `SCREEN-*` vocabulary (V140-10).
- Produces: ledger row `screen-high52w` with verdict `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`, and its results doc. V140-19 reads both.

**Preconditions:**
- V140-1..14 committed on the branch; V140-14's smoke test reported its per-ticker wall time.
- `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen status --short` is empty.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea has never been screened**

Run: `grep -c '"id": "screen-high52w"' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen/docs/superpowers/results/preregistration-ledger.jsonl`
Expected: `0`. Anything else: stop. The idea is closed; this task is already done or must not run.

- [ ] **Step 2: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen
(branch 2026-10-08-v140-idea-screen). Work only there. The only main-tree path
you may touch is the read-only cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext.

Job: the v140 one-shot idea screen of `high52w`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31)
and its own pass rule by design. Do not apply the TRAIN/VALIDATION windows or
the win-rate gates from your instructions; do not pass --start, --end,
--tickers or --dry-run.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the worktree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea high52w --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-high52w.log 2>&1
   The log prints a flushed `[high52w] i/N tickers (P%)` line every 25 tickers.
   Poll `tail -2 logs/screen-high52w.log` at an interval sized from the
   expected duration (~506 tickers x the per-ticker time the controller gives
   you from V140-14's smoke test).
3. Exit 0: the last log line is `screen-high52w: <VERDICT>, N=..., dExpR=...R,
   lower95=...R, k/10 years -> <results path>`. Do not edit, delete or commit
   anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 3: Verify what the run wrote**

Run, in the worktree:
- `git status --short` — Expected: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl` and `?? docs/superpowers/results/<run-date>-screen-high52w.md`.
- `tail -1 docs/superpowers/results/preregistration-ledger.jsonl` — Expected: the `screen-high52w` row, `"instrument": "screen-v1"`, the verdict in the runner's final line.
- `grep -n "^## Verdict" -A 8 docs/superpowers/results/<run-date>-screen-high52w.md` — Expected: the same verdict, its four clause rows, and an N equal to the row's `n`.
- `grep -n "dropped_\|skipped_overlap\|missing from the cache" docs/superpowers/results/<run-date>-screen-high52w.md` — Expected: every counter present (the disclosure the spec requires).

If the run crashed before the row existed (brief point 4), follow the phase rule above; this task is not done until a row exists. Then delete `logs/screen-high52w.log`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/*-screen-high52w.md
git commit -m "results(screen): high52w one-shot screen, <VERDICT> (V140-15)"
```

Replace `<VERDICT>` with the ledger verdict before committing.

### Task V140-16: Screen `uptrend_pullback` — uptrend RSI(2) pullback (Connors & Alvarez 2008), one shot

**Files:**
- Create (written by the script): `docs/superpowers/results/<run-date>-screen-uptrend_pullback.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: `scripts/backtest/screen_idea.py` (V140-14), `IDEAS["uptrend_pullback"]` (V140-2 constants, trigger from its Group A task), the `screen-v1` / `SCREEN-*` vocabulary (V140-10).
- Produces: ledger row `screen-uptrend_pullback` with verdict `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`, and its results doc. V140-19 reads both.

**Preconditions:**
- V140-15 committed (its row is in the ledger); the ledger is shared, so runs never overlap.
- `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen status --short` is empty.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea has never been screened**

Run: `grep -c '"id": "screen-uptrend_pullback"' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen/docs/superpowers/results/preregistration-ledger.jsonl`
Expected: `0`. Anything else: stop. The idea is closed; this task is already done or must not run.

- [ ] **Step 2: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen
(branch 2026-10-08-v140-idea-screen). Work only there. The only main-tree path
you may touch is the read-only cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext.

Job: the v140 one-shot idea screen of `uptrend_pullback`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31)
and its own pass rule by design. Do not apply the TRAIN/VALIDATION windows or
the win-rate gates from your instructions; do not pass --start, --end,
--tickers or --dry-run.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the worktree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea uptrend_pullback --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-uptrend_pullback.log 2>&1
   The log prints a flushed `[uptrend_pullback] i/N tickers (P%)` line every 25 tickers.
   Poll `tail -2 logs/screen-uptrend_pullback.log` at an interval sized from the
   expected duration (~506 tickers x the per-ticker time the controller gives
   you from V140-14's smoke test).
3. Exit 0: the last log line is `screen-uptrend_pullback: <VERDICT>, N=..., dExpR=...R,
   lower95=...R, k/10 years -> <results path>`. Do not edit, delete or commit
   anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 3: Verify what the run wrote**

Run, in the worktree:
- `git status --short` — Expected: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl` and `?? docs/superpowers/results/<run-date>-screen-uptrend_pullback.md`.
- `tail -1 docs/superpowers/results/preregistration-ledger.jsonl` — Expected: the `screen-uptrend_pullback` row, `"instrument": "screen-v1"`, the verdict in the runner's final line.
- `grep -n "^## Verdict" -A 8 docs/superpowers/results/<run-date>-screen-uptrend_pullback.md` — Expected: the same verdict, its four clause rows, and an N equal to the row's `n`.
- `grep -n "dropped_\|skipped_overlap\|missing from the cache" docs/superpowers/results/<run-date>-screen-uptrend_pullback.md` — Expected: every counter present (the disclosure the spec requires).

If the run crashed before the row existed (brief point 4), follow the phase rule above; this task is not done until a row exists. Then delete `logs/screen-uptrend_pullback.log`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/*-screen-uptrend_pullback.md
git commit -m "results(screen): uptrend_pullback one-shot screen, <VERDICT> (V140-16)"
```

Replace `<VERDICT>` with the ledger verdict before committing.

### Task V140-17: Screen `gap_volume` — gap + volume continuation, one shot

**Files:**
- Create (written by the script): `docs/superpowers/results/<run-date>-screen-gap_volume.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: `scripts/backtest/screen_idea.py` (V140-14), `IDEAS["gap_volume"]` (V140-2 constants, trigger from its Group A task), the `screen-v1` / `SCREEN-*` vocabulary (V140-10).
- Produces: ledger row `screen-gap_volume` with verdict `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`, and its results doc. V140-19 reads both.

**Preconditions:**
- V140-16 committed (its row is in the ledger); the ledger is shared, so runs never overlap.
- `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen status --short` is empty.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea has never been screened**

Run: `grep -c '"id": "screen-gap_volume"' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen/docs/superpowers/results/preregistration-ledger.jsonl`
Expected: `0`. Anything else: stop. The idea is closed; this task is already done or must not run.

- [ ] **Step 2: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen
(branch 2026-10-08-v140-idea-screen). Work only there. The only main-tree path
you may touch is the read-only cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext.

Job: the v140 one-shot idea screen of `gap_volume`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31)
and its own pass rule by design. Do not apply the TRAIN/VALIDATION windows or
the win-rate gates from your instructions; do not pass --start, --end,
--tickers or --dry-run.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the worktree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea gap_volume --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-gap_volume.log 2>&1
   The log prints a flushed `[gap_volume] i/N tickers (P%)` line every 25 tickers.
   Poll `tail -2 logs/screen-gap_volume.log` at an interval sized from the
   expected duration (~506 tickers x the per-ticker time the controller gives
   you from V140-14's smoke test).
3. Exit 0: the last log line is `screen-gap_volume: <VERDICT>, N=..., dExpR=...R,
   lower95=...R, k/10 years -> <results path>`. Do not edit, delete or commit
   anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 3: Verify what the run wrote**

Run, in the worktree:
- `git status --short` — Expected: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl` and `?? docs/superpowers/results/<run-date>-screen-gap_volume.md`.
- `tail -1 docs/superpowers/results/preregistration-ledger.jsonl` — Expected: the `screen-gap_volume` row, `"instrument": "screen-v1"`, the verdict in the runner's final line.
- `grep -n "^## Verdict" -A 8 docs/superpowers/results/<run-date>-screen-gap_volume.md` — Expected: the same verdict, its four clause rows, and an N equal to the row's `n`.
- `grep -n "dropped_\|skipped_overlap\|missing from the cache" docs/superpowers/results/<run-date>-screen-gap_volume.md` — Expected: every counter present (the disclosure the spec requires).

If the run crashed before the row existed (brief point 4), follow the phase rule above; this task is not done until a row exists. Then delete `logs/screen-gap_volume.log`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/*-screen-gap_volume.md
git commit -m "results(screen): gap_volume one-shot screen, <VERDICT> (V140-17)"
```

Replace `<VERDICT>` with the ledger verdict before committing.

### Task V140-18: Screen `turn_of_month` — turn of the month (Ariel 1987; Lakonishok & Smidt 1988), one shot

**Files:**
- Create (written by the script): `docs/superpowers/results/<run-date>-screen-turn_of_month.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: `scripts/backtest/screen_idea.py` (V140-14), `IDEAS["turn_of_month"]` (V140-2 constants, trigger from its Group A task), the `screen-v1` / `SCREEN-*` vocabulary (V140-10).
- Produces: ledger row `screen-turn_of_month` with verdict `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`, and its results doc. V140-19 reads both.

**Preconditions:**
- V140-17 committed (its row is in the ledger); the ledger is shared, so runs never overlap.
- `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen status --short` is empty.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea has never been screened**

Run: `grep -c '"id": "screen-turn_of_month"' E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen/docs/superpowers/results/preregistration-ledger.jsonl`
Expected: `0`. Anything else: stop. The idea is closed; this task is already done or must not run.

- [ ] **Step 2: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen
(branch 2026-10-08-v140-idea-screen). Work only there. The only main-tree path
you may touch is the read-only cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext.

Job: the v140 one-shot idea screen of `turn_of_month`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31)
and its own pass rule by design. Do not apply the TRAIN/VALIDATION windows or
the win-rate gates from your instructions; do not pass --start, --end,
--tickers or --dry-run.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the worktree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea turn_of_month --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-turn_of_month.log 2>&1
   The log prints a flushed `[turn_of_month] i/N tickers (P%)` line every 25 tickers.
   Poll `tail -2 logs/screen-turn_of_month.log` at an interval sized from the
   expected duration (~506 tickers x the per-ticker time the controller gives
   you from V140-14's smoke test).
3. Exit 0: the last log line is `screen-turn_of_month: <VERDICT>, N=..., dExpR=...R,
   lower95=...R, k/10 years -> <results path>`. Do not edit, delete or commit
   anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 3: Verify what the run wrote**

Run, in the worktree:
- `git status --short` — Expected: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl` and `?? docs/superpowers/results/<run-date>-screen-turn_of_month.md`.
- `tail -1 docs/superpowers/results/preregistration-ledger.jsonl` — Expected: the `screen-turn_of_month` row, `"instrument": "screen-v1"`, the verdict in the runner's final line.
- `grep -n "^## Verdict" -A 8 docs/superpowers/results/<run-date>-screen-turn_of_month.md` — Expected: the same verdict, its four clause rows, and an N equal to the row's `n`.
- `grep -n "dropped_\|skipped_overlap\|missing from the cache" docs/superpowers/results/<run-date>-screen-turn_of_month.md` — Expected: every counter present (the disclosure the spec requires).

If the run crashed before the row existed (brief point 4), follow the phase rule above; this task is not done until a row exists. Then delete `logs/screen-turn_of_month.log`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/*-screen-turn_of_month.md
git commit -m "results(screen): turn_of_month one-shot screen, <VERDICT> (V140-18)"
```

Replace `<VERDICT>` with the ledger verdict before committing.

### Task V140-19: Results close-out

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (four rows at the top of "Closed pre-registrations — do not re-run these")
- Create: `docs/superpowers/results/<date>-v140-screen-summary.md`
- Modify: `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md` (`**Status:**` line only)

**Interfaces:**
- Consumes: the four results docs and ledger rows written by V140-15..18.
- Produces: the closed-table rows that make each screen un-re-runnable by convention as well as by code, and the one-page answer to "which passed".

- [ ] **Step 1: Collect the four verdicts from the files, not from memory**

Run: `grep -n '"id": "screen-' docs/superpowers/results/preregistration-ledger.jsonl`
Expected: four rows, one per idea. For each results doc run `grep -n "^## Verdict" -A 8` and `grep -n "^Mean R_event"` to read N, ΔExpR, the 95% interval, years positive, mean R_event and mean R_null. Every number written below is copied from those lines.

- [ ] **Step 2: Add the four closed-table rows**

In `docs/claude/backtest-methodology.md`, insert directly below the `|---|---|---|` line of "### Closed pre-registrations — do not re-run these" one row per idea, in registry order, in this exact shape (fill every `<...>` from Step 1):

```markdown
| Idea screen `<idea>` — <SUMMARY from the idea module>, fixed 1.5/3 ATR race vs a K=20 matched null, cap <cap>, PIT S&P 500 2010-2019, after costs (v140 Stage −2) | **<VERDICT>.** N=<n> kept events, ΔExpR <+x.xxxx>R (95% [<lo>, <hi>]), <k> of 10 years positive; mean R_event <..>R vs mean R_null <..>R. <CLOSING SENTENCE> | `results/<run-date>-screen-<idea>.md`, ledger `screen-<idea>` |
```

`<CLOSING SENTENCE>` is, for `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`: `Closed: no spec, never re-screened; a changed parameter is a new idea with a new name.` For `SCREEN-PASS`: `Has earned a spec, nothing more: it next runs the unchanged funnel (v72 for a filter, the badge path for a strategy) with live-trigger/screen-trigger parity pinned by a test.`

- [ ] **Step 3: Write the summary doc**

`docs/superpowers/results/<date>-v140-screen-summary.md` (fill every `<...>` from Step 1; keep exactly one of the two "What follows" paragraphs):

```markdown
# v140 first screen batch — summary

**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`
**Pass rule:** ΔExpR ≥ +0.10R after costs, lower 95% week-cluster bound > 0, ≥ 7 of 9 years (2011–2019) positive, N ≥ 300 (`docs/claude/backtest-methodology.md` § Stage −2).

| Idea | Verdict | N | ΔExpR | 95% interval | Years positive | Record |
|---|---|---|---|---|---|---|
| `high52w` | <..> | <..> | <..>R | [<..>, <..>] | <k>/10 | `results/<run-date>-screen-high52w.md` |
| `uptrend_pullback` | <..> | <..> | <..>R | [<..>, <..>] | <k>/10 | `results/<run-date>-screen-uptrend_pullback.md` |
| `gap_volume` | <..> | <..> | <..>R | [<..>, <..>] | <k>/10 | `results/<run-date>-screen-gap_volume.md` |
| `turn_of_month` | <..> | <..> | <..>R | [<..>, <..>] | <k>/10 | `results/<run-date>-screen-turn_of_month.md` |

**<p> of 4 passed.**

## What follows (spec § What follows a result)

Each `SCREEN-PASS` idea (<names>) earns its own later spec — a strategy or a filter — carrying `**Screen:** screen-<idea> SCREEN-PASS`, with live-trigger/screen-trigger parity pinned by a test there. Not part of v140. A pass buys a spec, not a verdict: the idea still runs the unchanged funnel.

Zero passes is a measured answer: these well-known effects do not survive costs on S&P 500 daily bars at this geometry. The next batch moves to a different information source (earnings calendars, sector flows), not to looser bars or re-parameterised versions of these four.

## Disclosure

Every results doc carries the PIT members missing from the cache (survivorship that remains), every drop/skip counter, both arms' exit mix, the per-year table and the forward-drift table. `high52w` cannot fire in 2010 (its 252-bar high needs a year of history and the cache starts 2010-01-04), so its year clause was effectively ≥ 7 of 9 computable years; the spec's "a year with no events counts against" fixed that before any run.
```

Delete the `high52w` sentence if its per-year table shows events in 2010.

- [ ] **Step 4: Update the spec's Status line**

In `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`, replace the `**Status:**` line with:

```markdown
**Status:** implemented <date>; first batch screened once each: <p> of 4 `SCREEN-PASS` (<names, or none>). Summary: `docs/superpowers/results/<date>-v140-screen-summary.md`.
```

- [ ] **Step 5: Verify the header gate and commit**

Run: `python scripts/dev/testrun.py file tests/hooks/test_spec_screen_header.py` — Expected: PASS.

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/results/*-v140-screen-summary.md docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md
git commit -m "docs(screen): close out the v140 first batch, <p> of 4 passed (V140-19)"
```

### Task V140-20: Full-suite verification

**Files:** none (fix-forward edits only if the run is red).

- [ ] **Step 1: Run the full suite once**

Dispatch the `test-runner` agent (worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`) to run `python scripts/dev/testrun.py full` once, over everything V140-1..19 implemented.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 2: If it is not green, fix forward**

The failures it names are this plan's regressions. Fix each with a failing test first, commit, and re-dispatch the one run. The task is not done until the run is green.

- [ ] **Step 3: Hand back for merge and close-out**

Report the one-line verdict to the controller. Merging the branch to `main` (`worktree-lifecycle`; no second suite run unless the merge resolved conflicts) and `/close-out` (`Bump: none`; the plan moves to `implemented/`) are the controller's.
