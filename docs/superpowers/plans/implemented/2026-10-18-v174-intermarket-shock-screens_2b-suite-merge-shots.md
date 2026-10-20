# v174 Intermarket shock screens, part 2b: full suite, merge, the two shots, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V174-11:" -A 200 docs/superpowers/plans/implemented/2026-10-18-v174-intermarket-shock-screens_2b-suite-merge-shots.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-18-v174-intermarket-shock-screens-design.md`](../../specs/implemented/2026-10-18-v174-intermarket-shock-screens-design.md) (every applied `## Panel review` finding is a requirement)
**Index:** [`2026-10-18-v174-intermarket-shock-screens_0-index.md`](2026-10-18-v174-intermarket-shock-screens_0-index.md) — **Global Constraints, Review Focus, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints.** Split from part 2 (`_2-ideas-diagnostics-shots.md`, V174-6..V174-8) to keep each file under 1500 lines.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C`. **A PreToolUse hook rejects Bash commands that contain the string `screen_idea` with an unbalanced quote** (heredocs included): keep every Bash command that names the runner free of apostrophes.

# Phase 5 — Full suite and merge

### Task V174-9: Full suite

**Model:** haiku — one command through the `test-runner` agent

**Files:** none (verification only).

**Interfaces:**
- Consumes: every code task, V174-1..V174-4 and V174-6..V174-8, committed on the branch.
- Produces: a green suite on the branch (`0 failed`, `0 xfailed`), which V174-10 needs before it merges.

**Preconditions:** `git -C $WT status --short` is empty, and `git -C $WT log --oneline main..HEAD` lists the commits of V174-1..V174-4 and V174-6..V174-8.

- [ ] **Step 1: Dispatch the `test-runner` agent with exactly this brief**

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens
(branch 2026-10-18-v174-intermarket-shock-screens). Work only there; edit nothing.

Run once, from the worktree root:
  python scripts/dev/testrun.py full

This is the plan's one full-suite run (it includes the complexity gate,
scripts/dev/complexity_gate.py). Return under 20 lines: the final pass/fail/
xfail/skip counts, wall time, and for every failure or xfail its node id and
the last 10 lines of its traceback. Do not re-run anything.
```

- [ ] **Step 2: Read the result**

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`): the branch adds about 60 tests.

On a failure: fix it with a failing test first, in the task whose files it touches, commit on the branch, and re-run **only** that test (`python $WT/scripts/dev/testrun.py file <test file>`), never the whole suite. A complexity-gate failure names a function: split it into named helpers without changing behaviour (`docs/claude/code-complexity.md`), never `--update` the baseline upward.

- [ ] **Step 3: Record the run**

Nothing to commit unless Step 2 needed a fix. Note the counts and wall time in the index's `## Progress` block in the main tree only at close-out (V174-13); do not edit the plan on the branch.

### Task V174-10: Merge the branch into `main`

**Model:** sonnet — merge with the `worktree-lifecycle` skill, conflict judgement

**Files:** none (a merge commit on `main`).

**Interfaces:**
- Consumes: V174-9's green suite on the branch.
- Produces: the merged code on `main`: `screen/context.py`, `screen/diagnostics.py`, the two idea modules, the runner changes and their tests. V174-11 and V174-12 run from the main tree.

- [ ] **Step 1: Invoke the `worktree-lifecycle` skill and check both trees**

Run:

```bash
git -C $WT status --short
git -C $R status --short
git -C $R log --oneline -5
git -C $R rev-list --count main..2026-10-18-v174-intermarket-shock-screens
```

Expected: the worktree is clean; the branch is ahead of `main` by the plan's commits. The main tree may show other sessions' uncommitted files (for example plan files of other plans, `.admin_*.log`): leave them alone and never stage them. If a main-tree change touches any file the branch changed (`git -C $R diff --name-only main...2026-10-18-v174-intermarket-shock-screens` against `git -C $R status --short`), stop and ask the partner which one wins (`AskUserQuestion`).

- [ ] **Step 2: Merge**

```bash
git -C $R merge --no-ff 2026-10-18-v174-intermarket-shock-screens -m "merge: v174 intermarket context hook, two frozen ideas and diagnostics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

On a conflict: the branch touched only `swingbot/core/backtesting/screen/`, `scripts/backtest/screen_idea.py` and their tests. A conflict there means another plan changed the screen runner since the branch started. Resolve it keeping both changes, then re-run the conflicted files' tests alone (Step 3) before committing the merge; if the two changes cannot both hold, abort (`git -C $R merge --abort`) and ask the partner.

- [ ] **Step 3: Narrow check on `main`**

No full suite after the merge (root `CLAUDE.md`: it ran once, before). Run only the files this plan touched:

```bash
python $R/scripts/dev/testrun.py file tests/backtesting/screen/test_context.py
python $R/scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py
python $R/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python $R/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python $R/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
```

Expected: every file `0 failed`.

- [ ] **Step 4: Leave the worktree in place**

Do not remove the worktree or delete the branch here; V174-13's `/close-out` does both. Check: `git -C $R status --short` shows no change from this task beyond what Step 1 saw.

# Phase 6 — The two shots (strictly one at a time), close-out

**Sequential throughout.** Both shots append to the one ledger file, and the second checks the hash JSON the first one commits. Order is the registry order: `bond_spike_rebound`, then `dollar_drop`. The order carries no information: each idea gets exactly one run whatever the other shows, and **no result changes any parameter of either idea** (frozen in V174-6, before any stock outcome was read).

**What a run may and may not do after it starts** (as in v140):
- A crash, traceback or `refused:` **before** the ledger row is appended recorded no verdict. Fix the cause in the code with a failing test first (a normal TDD fix, committed on `main` with the partner's go-ahead, since the branch is merged), then dispatch the same run again. Never change a trigger, a cap, K, the seed, the window, the context window, the pass rule or the cache bytes to make it run. Never refetch TLT or UUP (Global Constraints, Data).
- Once the row is appended, the idea is closed by its verdict. Never re-run it, never edit or delete its row, never edit its results doc's numbers. A bug found afterwards goes to the partner (`AskUserQuestion`); a corrected measurement would be a new idea with a new name, and only the partner can authorise that.

### Task V174-11: Shot 1: `bond_spike_rebound`

**Model:** sonnet — dispatch to `backtest-runner` under `backtest-gate`, record and commit

**Files:**
- Create (written by the script): `docs/superpowers/results/2026-10-18-v174-context-hashes.json`
- Create (written by the script): `docs/superpowers/results/<run date>-screen-bond_spike_rebound.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: the merged runner (V174-10), `IDEAS["bond_spike_rebound"]` (V174-6), the TLT/UUP files (V174-5) in `$R/data/backtest_cache_ext`.
- Produces: ledger row `screen-bond_spike_rebound` (`SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED`), its results doc, and the committed hash JSON (`{"TLT": <sha256>, "UUP": <sha256>}`) that V174-12's run checks.

**Preconditions:**
- V174-10 merged; `git -C $R log --oneline -1` is the merge or later.
- V174-5 done: `$R/data/backtest_cache_ext/TLT.csv` and `UUP.csv` exist.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea has never been screened and nothing is pinned yet**

Run:

```bash
grep -c "screen-bond_spike_rebound" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl
ls E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-10-18-v174-context-hashes.json
sha256sum E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/TLT.csv E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/UUP.csv
```

Expected: `0`; `No such file or directory`; two hashes (note them for Step 4). Anything else on the first two: stop. A row means the idea is closed; an existing hash file means a run already wrote one, so find out which before going on.

- [ ] **Step 2: Smoke the load path without a verdict worth reading**

A dry run over three tickers proves the load checks, the hash check and the doc path work on the real files, and times one ticker. It spends nothing: `--dry-run` writes no doc, no hash file and no ledger row, and three tickers measure nothing. Run from the main tree root (`run_in_background: true` is not needed; it takes about a minute):

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/backtest/screen_idea.py --idea bond_spike_rebound --dry-run --tickers AAPL,MSFT,JNJ --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > E:/Documents/Private/Projects/Discord-Bot/logs/smoke-bond_spike_rebound.log 2>&1; echo exit=$?
grep -n "refused\|Traceback\|shock days in\|Context data\|TLT |\|UUP |" E:/Documents/Private/Projects/Discord-Bot/logs/smoke-bond_spike_rebound.log
```

Expected: `exit=0`; no `refused` and no `Traceback`; the effective-sample line `... from <S> shock days in <E> episodes ...` and one context-data row per series. Read only those lines, never the verdict or any ΔExpR of the smoke doc: three tickers say nothing, and a frozen idea gives nothing to adjust anyway. For a sanity check only: the spec counted 68 TLT shock days and 24 episodes over 2010-19 (feasibility table), so the 2011-19 window should show somewhat fewer days and about 20-24 episodes. A count of 0, or one far above 68, means the series or the z is wrong: stop and report to the partner before any real run.

On `exit=2`: the `refused:` reason names the failed load check (missing file, raw index, missing SPY session, z coverage). Report it to the partner; never fix data by refetching. Then delete the smoke log.

- [ ] **Step 3: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Main tree: E:/Documents/Private/Projects/Discord-Bot (branch main). Work only there.
The cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext is read-only.

Job: the v174 one-shot intermarket screen of `bond_spike_rebound`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31,
context series from 2009-06-01) and its own pass rule by design. Do not apply
the TRAIN/VALIDATION windows or the win-rate gates from your instructions; do
not pass --start, --end, --tickers, --dry-run or --context-hashes.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the main tree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea bond_spike_rebound --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-bond_spike_rebound.log 2>&1
   The log prints a flushed `[bond_spike_rebound] i/N tickers (P%)` line every
   25 tickers. Poll `tail -2 logs/screen-bond_spike_rebound.log` at an interval
   sized from the expected duration (about 506 tickers x the per-ticker time the
   controller gives you from the smoke run; a context idea races its null twice).
3. Exit 0: the last log line is `screen-bond_spike_rebound: <VERDICT>, N=...,
   dExpR=...R, lower95=...R, k/9 years -> <results path>`. Do not edit, delete
   or commit anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 4: Verify what the run wrote**

Run:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short docs/superpowers/results
tail -1 E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl
cat E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-10-18-v174-context-hashes.json
grep -n "^# v140 screen\|^## Verdict\|^## Intermarket diagnostics\|^### \|BH q" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/*-screen-bond_spike_rebound.md
```

Expected:
- status: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl`, `?? docs/superpowers/results/2026-10-18-v174-context-hashes.json` and `?? docs/superpowers/results/<run date>-screen-bond_spike_rebound.md`.
- the last ledger row is `screen-bond_spike_rebound`, `"instrument": "screen-v1"`, `"data_source": "yfinance"`, the verdict of the runner's final line, and a `hypothesis` ending in `... not a bearish or longer-horizon variant.`
- the hash JSON holds `TLT` and `UUP`, equal to Step 1's `sha256sum` values.
- the doc's head verdict matches the row; both BH q lines are present (whole ledger in the head, `screen-v1` family in § 5); the diagnostics section has its six `###` subsections and the context-data table.

If the run crashed before the row existed, follow the phase rule above; this task is not done until a row exists. Then delete `logs/screen-bond_spike_rebound.log` and `logs/smoke-bond_spike_rebound.log`.

- [ ] **Step 5: Commit on `main`**

Stage only these three paths (other sessions' files may sit in the main tree):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/2026-10-18-v174-context-hashes.json docs/superpowers/results/*-screen-bond_spike_rebound.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "results(screen): bond_spike_rebound one-shot intermarket screen, <VERDICT> (V174-11)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Replace `<VERDICT>` with the ledger verdict before committing. Report to the partner in two lines: the verdict with N, ΔExpR and the lower bound, and the § 5 lines that qualify it (episodes, the SPY `< 0` / `>= 0` split, the top two episodes' share). Say plainly that a fail closes only the frozen definition.

### Task V174-12: Shot 2: `dollar_drop`

**Model:** sonnet — dispatch to `backtest-runner` under `backtest-gate`, record and commit

**Files:**
- Create (written by the script): `docs/superpowers/results/<run date>-screen-dollar_drop.md`
- Modify (one line appended by the script): `docs/superpowers/results/preregistration-ledger.jsonl`

**Interfaces:**
- Consumes: V174-11's committed ledger row and hash JSON (`docs/superpowers/results/2026-10-18-v174-context-hashes.json`); `IDEAS["dollar_drop"]` (V174-6); the same, never refetched, TLT/UUP files.
- Produces: ledger row `screen-dollar_drop` and its results doc. V174-13 reads both rows.

**Preconditions:** V174-11 committed (`git -C $R log --oneline -3` shows its `results(screen): bond_spike_rebound ...` commit); `git -C $R status --short docs/superpowers/results` is empty.

- [ ] **Step 1: Invoke `backtest-gate`, then confirm the idea is unscreened and the bytes are the pinned ones**

Run:

```bash
grep -c "screen-dollar_drop" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl
cat E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/2026-10-18-v174-context-hashes.json
sha256sum E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/TLT.csv E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/UUP.csv
```

Expected: `0`; the JSON's `TLT` and `UUP` equal the two `sha256sum` values. A mismatch means the files changed since shot 1 (a refetch, an edit): the run would refuse by itself, and it must. Stop and report to the partner; never refetch, never edit the JSON.

- [ ] **Step 2: Smoke the load path without a verdict worth reading**

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/backtest/screen_idea.py --idea dollar_drop --dry-run --tickers AAPL,MSFT,JNJ --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > E:/Documents/Private/Projects/Discord-Bot/logs/smoke-dollar_drop.log 2>&1; echo exit=$?
grep -n "refused\|Traceback\|shock days in\|Context data\|TLT |\|UUP |" E:/Documents/Private/Projects/Discord-Bot/logs/smoke-dollar_drop.log
```

Expected: `exit=0`; no `refused`, no `Traceback`; the effective-sample line and the context-data rows. Read only those lines. Sanity only: the spec counted 57 UUP shock days and 28 episodes over 2010-19, so the 2011-19 window should show somewhat fewer days and about 24-28 episodes; 0, or far above 57, means stop and report to the partner. A `refused:` naming the hash file is the refetch guard working: stop and report, as in Step 1.

- [ ] **Step 3: Dispatch the `backtest-runner` agent with exactly this brief**

```text
Main tree: E:/Documents/Private/Projects/Discord-Bot (branch main). Work only there.
The cache E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext is read-only.

Job: the v174 one-shot intermarket screen of `dollar_drop`. Run it exactly once.

This script fixes its own window (point-in-time S&P 500, 2010-01-01..2019-12-31,
context series from 2009-06-01) and its own pass rule by design. It refuses by
itself if the TLT/UUP bytes differ from the committed hash file. Do not apply
the TRAIN/VALIDATION windows or the win-rate gates from your instructions; do
not pass --start, --end, --tickers, --dry-run or --context-hashes.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the main tree root, with run_in_background: true:
     mkdir -p logs
     python scripts/backtest/screen_idea.py --idea dollar_drop --date $(date -u +%Y-%m-%d) --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/screen-dollar_drop.log 2>&1
   The log prints a flushed `[dollar_drop] i/N tickers (P%)` line every 25
   tickers. Poll `tail -2 logs/screen-dollar_drop.log` at an interval sized from
   shot 1's wall time, which the controller gives you.
3. Exit 0: the last log line is `screen-dollar_drop: <VERDICT>, N=..., dExpR=...R,
   lower95=...R, k/9 years -> <results path>`. Do not edit, delete or commit
   anything.
4. Exit 2 (`refused: ...`) or a traceback: do NOT re-run and do NOT change any
   flag. Return the last 30 log lines.

Return (under 25 lines): exit code, wall time, the final log line verbatim,
the results-doc path, the absolute log path, and any anomaly (an empty-frame
count above zero, a counter that looks wrong).
```

- [ ] **Step 4: Verify what the run wrote**

Run:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short docs/superpowers/results
tail -1 E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl
git -C E:/Documents/Private/Projects/Discord-Bot diff --stat docs/superpowers/results/2026-10-18-v174-context-hashes.json
grep -n "^# v140 screen\|^## Verdict\|^## Intermarket diagnostics\|^### \|BH q" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/*-screen-dollar_drop.md
```

Expected:
- status: exactly ` M docs/superpowers/results/preregistration-ledger.jsonl` and `?? docs/superpowers/results/<run date>-screen-dollar_drop.md`; the hash JSON is untouched (empty `diff --stat`: a real run writes it only when absent).
- the last ledger row is `screen-dollar_drop`, `"instrument": "screen-v1"`, `"data_source": "yfinance"`, the runner's verdict, and a `hypothesis` ending in `... not a bearish or longer-horizon variant.`
- the doc's head verdict matches the row; both BH q lines are present; the six `###` subsections and the context-data table are there. Its screen-family q now counts `screen-bond_spike_rebound` too.

If the run crashed before the row existed, follow the phase rule above. Then delete `logs/screen-dollar_drop.log` and `logs/smoke-dollar_drop.log`.

- [ ] **Step 5: Commit on `main`**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/preregistration-ledger.jsonl docs/superpowers/results/*-screen-dollar_drop.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "results(screen): dollar_drop one-shot intermarket screen, <VERDICT> (V174-12)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Replace `<VERDICT>` with the ledger verdict before committing. Report to the partner as in V174-11 Step 5.

### Task V174-13: Close-out

**Model:** haiku — the `/close-out` ritual, no code

**Files:**
- Modify: `docs/superpowers/plans/implemented/2026-10-18-v174-intermarket-shock-screens_0-index.md` (`## Progress`, then moved with the parts)
- Modify: `swingbot/admin/version_history.json` only if the ritual regenerates it (`Bump: none`, so normally unchanged)

**Interfaces:**
- Consumes: both ledger rows and results docs (V174-11, V174-12), V174-9's suite counts.
- Produces: the plan files under `docs/superpowers/plans/implemented/`, the worktree and branch removed.

**Preconditions:** V174-11 and V174-12 committed on `main`; `git -C $R status --short docs/superpowers` shows no change from this plan.

- [ ] **Step 1: Write the outcome into the index's `## Progress` block**

Replace the `## Progress` body of `$R/docs/superpowers/plans/implemented/2026-10-18-v174-intermarket-shock-screens_0-index.md` with five lines: the full-suite counts (V174-9); `screen-bond_spike_rebound` verdict, N, ΔExpR, lower bound, results-doc path; the same for `screen-dollar_drop`; one line on what each verdict licenses (a `SCREEN-PASS` licenses only a later `Edge: expectancy` filter spec; a fail closes exactly the frozen definition, nothing broader); and the hash JSON path.

- [ ] **Step 2: Run `/close-out`**

Invoke the `close-out` skill (standing permission, root `CLAUDE.md`). The code reached `main` in V174-10, so the plan's four files (`_0-index`, `_1-context-hook`, `_2-ideas-diagnostics-shots`, `_2b-suite-merge-shots`) go to `docs/superpowers/plans/implemented/`, whatever the two verdicts are (`docs/claude/document-lifecycle.md`: `no-lift/` is only for a plan whose code never reached `main`). `Bump: none`: the ritual resolves no version change. It removes the worktree `2026-10-18-v174-intermarket-shock-screens` and its branch after `git -C $R rev-list --count main..2026-10-18-v174-intermarket-shock-screens` returns `0` (the branch name holds no `backup`, `docs/claude/git-safety.md`).

- [ ] **Step 3: Verify**

```bash
ls E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/plans/implemented/ | grep v174
git -C E:/Documents/Private/Projects/Discord-Bot worktree list
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -3
```

Expected: the four plan files listed under `implemented/`; no `2026-10-18-v174-intermarket-shock-screens` worktree; the close-out commit on top. If the spec has a `/panel` close-out step pending (spec header `Panel:`), the skill runs it before moving the files.

