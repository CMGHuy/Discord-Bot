# v211 — Shock-conditioned short screens, Part 5: the data build, the two shots, the records and the close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md) — § Track 2 (opening paragraph: one shot each, frozen at the spec's commit), § Printed alongside each verdict (the outcome-blind preflight), § What the screens can and cannot say, § Follow-on pre-registrations, § Track 1 → `MARKET_SHOCK_MODE` binding note (partner, 2026-11-06).
**Index:** [2026-11-06-v211-shock-short-screens_0-index.md](2026-11-06-v211-shock-short-screens_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Where:** every task in this part runs **on `main` in the main checkout** (`E:/Documents/Private/Projects/Discord-Bot`), never in the v211 worktree: the cache (`data/backtest_cache_ext/`, gitignored) lives only in the main tree, and the records belong on `main` (index § Global Constraints: *Shots run only on `main`*).

**Tasks:** V211-13 → V211-14 → V211-15 → V211-16, strictly sequential (index § Parallelisation, group E). Shot 2 follows shot 1 so its results doc cites shot 1's BH q; V211-15 needs both ledger rows; V211-16 closes.

**One shot each — read this before any step.** The spec froze both definitions at its commit (`backtest-methodology.md` § Funnel stages, § Closed pre-registrations). Whatever a real run prints — `SCREEN-PASS`, `SCREEN-FAIL` or `SCREEN-UNDERPOWERED` — is the result. No retry with another flag, no edit of an idea, the window, the costs or the data afterwards, no "second look" with `--dry-run` over the universe. The preflight (V211-13) prints effective N; it **never** decides whether to shoot: the shot is run as registered, and if a fail is mostly empty years, the summary says so (spec § Printed alongside each verdict).

**Restarts are not re-runs.** A shot runs with `--checkpoint-dir data/screen_checkpoints/screen-<idea>` (V211-6): each finished ticker is pickled as it completes. If the process dies **before** its results doc exists, it is resumed with **the identical command line** — same script path invoked as `python scripts/backtest/screen_idea.py`, same flags, same `--date` — because the pickles hold `__main__.TickerScreen` and are read back only by the entry point that wrote them (never resume through `python -m`, an import, or a test). A resume reads no outcome the first attempt did not finish; it is the same shot. Once the results doc exists, the shot is spent: a crash between the doc write and the ledger append is reported to the partner, never re-run (`.claude/hooks/guardrails.py` `_screen_record_reason` denies it anyway). A refusal (`exit 2`, `refused: …`, or `ValueError: checkpoint … belongs to another run`) is reported to the partner; never delete or edit a checkpoint to get past it.

**The guardrail hook reads every Bash line that names the screen script.** Never wrap a screen command in quotes, `bash -c`, a heredoc or an ssh string; the hook denies a line it cannot tokenise. Commit messages in this part never quote a screen command line. `--pin-context` and `--checkpoint-dir` are not in the hook's option list, so a `--pin-context` line is read as a real run of its `--idea`: always name an idea **not yet screened** there (`shock_support_break_short`, before shot 1).

**Long runs go to `backtest-runner`.** The shots and the two outcome-blind counts are dispatched to the `backtest-runner` agent, so none of the run's output lands in the controller's context. The runner's progress line flushes a percent per ticker, so a run of 15 minutes or more reports progress.

**`data/screen_checkpoints/` is not gitignored** (`git check-ignore` finds no rule; `data/backtest_cache_ext/` and `logs/` are). Stage named files only (`git add <path>`), never `git add -A`/`.`, and remove a shot's checkpoint directory only after its doc and ledger row are committed (Step "Commit the record" of V211-13/14). The run logs go to `logs/` (gitignored).

**Run date.** Git Bash here has no timezone data (`TZ=Europe/Berlin date` prints UTC). Compute the Berlin day from `date -u +%Y-%m-%dT%H:%M`: add 1 hour in November–March (CET), 2 hours late March–late October (CEST). `<run-date>` below is that Berlin day, fixed once per task.

**Contracts from earlier parts this part consumes** (index ledger, Produces column):

- V211-2: `python scripts/data/fetch_backtest_data.py --vix-context --cache-dir PATH [--start] [--end] [--force]` writes `<cache_dir>/^VIX.csv` after `check_vix_sessions` (exit 2 on an existing file without `--force` or on a `ContextError`).
- V211-3: `python scripts/data/build_breadth_context.py --cache-dir PATH [--membership] [--end] [--out]` writes `<cache_dir>/BREADTH_ATR1.csv`, refuses an existing output (`refusing: <out> exists; BREADTH_ATR1 is built once and pinned`, exit 2), prints per-year coverage lines (`<year>: <x> of <y> PIT members with a finite move per session (<share>)`).
- V211-4: `--pin-context` → `pinned <ticker> <sha256> -> <path>` per added file, or `nothing to pin: …`; exit 2 on a differing SHA; never rewrites a pinned entry.
- V211-6: `--checkpoint-dir PATH`; `<dir>/manifest.json` + `<ticker>.pkl`; the `[<idea>] checkpoint <dir>: <k> ticker(s) already screened` line.
- V211-8/9: `IDEAS["shock_support_break_short"]`, `IDEAS["shock_failed_bounce_short"]` (`context_kind == "level"`); ledger ids `screen-shock_support_break_short`, `screen-shock_failed_bounce_short`.
- V211-11/11b: the level results doc carries `## Shock read-outs (v211; descriptive, never gating)` (with `**Shock-day null**`, `**Re-priced at 3 x slippage**`, `**Gap split**`, `**Day of the episode**`, `**Unconditional control**`, `(`skipped_overlap`) = `) and `## Context series (v211 level)` (rows `| BREADTH_ATR1 |`, `| ^VIX |`), and `**Short-family BH q**` across `screen_idea.SHORT_SCREEN_IDS` via `screen_idea.short_family_q`.
- V211-12: `--count-only` for a level idea loads and hash-checks the context (exit 2 on a context or hash error) and ends with the per-year table `year · shock days · shock weeks · events` (2011–2019) and the totals.

---

# Phase E — Shots and records

### Task V211-13: Build `^VIX`/`BREADTH_ATR1` on the real cache, pin, preflight, shot 1 (`shock_support_break_short`)

**Model:** sonnet — the screen ritual: preconditions, two data builds, a pin, two dispatched counts, one dispatched shot and four scoped commits; the only judgement is stopping when a precondition fails.

**Files:**
- Create (by the scripts, gitignored, never committed): `data/backtest_cache_ext/^VIX.csv`, `data/backtest_cache_ext/BREADTH_ATR1.csv`
- Modify: `docs/superpowers/results/2026-10-18-v174-context-hashes.json` (two keys added by `--pin-context`; `TLT`, `UUP` untouched)
- Create: `docs/superpowers/results/<run-date>-v211-shock-preflight.md` (by hand, from the two count printouts)
- Create: `docs/superpowers/results/<run-date>-screen-shock_support_break_short.md` (written by the script)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row appended by the script)

**Interfaces:**
- Consumes: every V211-1..V211-12 commit, merged to `main` with the CI run on that push green; the contracts listed in this part's header.
- Produces: the pin file with `BREADTH_ATR1` and `^VIX`; the preflight doc (both ideas' per-year tables, committed **before** the shot); ledger row `screen-shock_support_break_short` and its results doc. V211-14 reads the **definition commit** recorded in Step 2.

- [ ] **Step 1: The code is on `main` and CI is green**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot branch --show-current
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot merge-base --is-ancestor 2026-11-06-v211-shock-short-screens main && echo MERGED
gh run list --branch main --limit 1 --json headSha,status,conclusion
git -C E:/Documents/Private/Projects/Discord-Bot rev-parse origin/main main
```

Expected: branch `main`; `status --short` shows no change under `docs/superpowers/results/`, `swingbot/core/backtesting/screen/` or `scripts/` (other sessions' unrelated edits may be present: leave them alone and stage only this task's files); `MERGED`; the newest run is `completed`/`success` and its `headSha` equals `origin/main`, which contains the merge.

Not merged yet: invoke the `worktree-lifecycle` skill and follow its merge steps (another session may be on `main`; pause and confirm with the partner if concurrent activity shows): `git merge --no-ff 2026-11-06-v211-shock-short-screens` with the message `merge(v211): shock-conditioned short screen code (V211-1..12)` and the `Co-Authored-By` line, `git push`, then follow the CI run to its end (`docs/claude/working-conventions.md` § Pipeline watch). A failing test is fixed on `main` in its own commit, re-run alone (`python scripts/dev/testrun.py file <test>`), pushed, and watched again. **No step below runs until CI is green on the merge**: a shot on unverified code cannot be taken back. No full suite locally.

- [ ] **Step 2: Committed definition, clean screen package, not screened before**

```bash
git status --short swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py
git log -1 --format=%H -- swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py
grep -n '"id": "screen-shock_' docs/superpowers/results/preregistration-ledger.jsonl
ls docs/superpowers/results/*-screen-shock_*.md docs/superpowers/results/*-v211-shock-preflight.md
ls data/screen_checkpoints/
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_support_break_short.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py
```

Expected: the first `status` prints nothing; note the hash as the **definition commit**; the `grep` finds nothing; the `ls` lines find nothing (a missing `data/screen_checkpoints/` is fine); all three test files `0 failed`, `0 xfailed`. Any ledger hit, any results doc, or an existing `data/screen_checkpoints/screen-shock_support_break_short/` from an earlier attempt of this task: stop and read **Resume** below before going on.

**Resume** (this task cut off part-way): `git log --oneline -8 -- docs/superpowers/results/` tells which commits already landed. Pin committed → skip Steps 4–6. Preflight doc committed → skip Steps 7–8. A checkpoint directory but no results doc → go to Step 9 and resume the shot with the identical command, with the `<run-date>` of the checkpointed attempt (the `--date` in `logs/v211-screen-shock_support_break_short.cmd`, which Step 9 writes before the run). A results doc or a ledger row already present → the shot is spent: go to Step 10.

- [ ] **Step 3: Fix the run date**

Run `date -u +%Y-%m-%dT%H:%M` and convert to the Berlin day (this part's header). `<run-date>` is that day; the preflight doc, the `--date` of shot 1 and its log use the same value.

- [ ] **Step 4: Fetch `^VIX` once**

```bash
ls data/backtest_cache_ext/^VIX.csv data/backtest_cache_ext/_VIX.csv data/backtest_cache_ext/BREADTH_ATR1.csv
python scripts/data/fetch_backtest_data.py --vix-context --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext
head -3 data/backtest_cache_ext/^VIX.csv
python -c "import pandas as pd; f = pd.read_csv('data/backtest_cache_ext/^VIX.csv', parse_dates=['Date']); print(len(f), f.Date.min().date(), f.Date.max().date(), int(f.Close.isna().sum()))"
```

Expected: the `ls` finds none of the three files (an unpinned `^VIX.csv` from this task's own earlier attempt may be kept: skip the fetch line; never pass `--force`); the fetch exits 0; the header is `Date,Open,High,Low,Close,Volume`; the rows are SPY's sessions 2009-01-01..2019-12-31 (first date in early January 2009, last 2019-12-31), 0 NaN closes. A `ContextError` (a session missing or extra against SPY) writes nothing: report the message to the partner and stop. Never patch the calendar by hand.

- [ ] **Step 5: Build `BREADTH_ATR1` once**

```bash
mkdir -p logs
python scripts/data/build_breadth_context.py --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v211-breadth-build.log 2>&1; echo exit=$?
tail -15 logs/v211-breadth-build.log
python -c "import pandas as pd; f = pd.read_csv('data/backtest_cache_ext/BREADTH_ATR1.csv', parse_dates=['Date']); print(len(f), f.Date.min().date(), f.Date.max().date(), round(f.Close.min(), 3), round(f.Close.max(), 3), int(f.Close.isna().sum()), int((f.Close >= 0.40).sum()))"
```

Expected: `exit=0`; the log ends with one coverage line per year (2009–2019); the frame spans the same sessions as `^VIX.csv`, `Close` within [0, 1], 0 NaN, and a non-zero count of sessions at or above 0.40 (outcome-blind; it decides nothing). A coverage share under about 80 % in any year is reported in the preflight doc, never fixed: the definition is frozen.

- [ ] **Step 6: Pin both files, and commit the pin before anything reads them**

```bash
python scripts/backtest/screen_idea.py --idea shock_support_break_short --pin-context --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext
git diff docs/superpowers/results/2026-10-18-v174-context-hashes.json
```

Expected: exit 0 and exactly two lines, `pinned BREADTH_ATR1 <sha> -> …` and `pinned ^VIX <sha> -> …`; the diff adds those two keys and changes no existing line (`TLT`, `UUP` byte-identical). Exit 2 (`… differs from … pinned …`) means a pinned context file changed under the cache: stop and report it. Then:

```bash
git add docs/superpowers/results/2026-10-18-v174-context-hashes.json
git commit -m "data(v211): pin BREADTH_ATR1 and ^VIX context hashes before the shock screens" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

From here on neither file is rebuilt, refetched or touched (index § Global Constraints).

- [ ] **Step 7: Outcome-blind counts for both ideas, through `backtest-runner`**

Dispatch the `backtest-runner` agent (main checkout, `E:/Documents/Private/Projects/Discord-Bot`) with exactly these two commands, one after the other:

```bash
python scripts/backtest/screen_idea.py --idea shock_support_break_short --count-only --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v211-count-shock_support_break_short.md 2>&1
python scripts/backtest/screen_idea.py --idea shock_failed_bounce_short --count-only --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > logs/v211-count-shock_failed_bounce_short.md 2>&1
```

Ask the runner to return only each exit code and each log's last 16 lines (the per-year preflight table and its totals). Expected: both exit 0; each log ends with the 2011–2019 table and the totals. The counts race nothing and read no R. Exit 2 (a context or hash refusal) is reported to the partner; nothing is re-pinned to get past it.

- [ ] **Step 8: Write and commit the preflight doc, before the shot**

Create `docs/superpowers/results/<run-date>-v211-shock-preflight.md` from this skeleton; paste each count log verbatim under its heading and the coverage lines from `logs/v211-breadth-build.log` as a list:

  ```markdown
  # v211 shock-short screens — outcome-blind preflight

  **Spec:** `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md` § Track 2 → Printed alongside each verdict
  **Plan:** `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_0-index.md` (V211-13)
  **Definition commit:** <hash from Step 2>
  **Context pins:** `results/2026-10-18-v174-context-hashes.json`: `BREADTH_ATR1` <first 12 of its SHA>, `^VIX` <first 12 of its SHA> (commit <hash of Step 6's commit>)

  Printed before either shot and before any race. **It decides nothing:** both shots run as registered (spec § Printed alongside each verdict). Shock weeks are the bootstrap's clusters (ISO weeks), so they state the effective N; a year with no events counts against the 7-of-9 rule.

  ## Context build

  - `^VIX.csv`: <rows> sessions, <first>..<last>, aligned to SPY's sessions.
  - `BREADTH_ATR1.csv`: <rows> sessions; sessions at `BREADTH_ATR1 >= 0.40`: <count>. Coverage per year (members with a finite move / PIT members):

  <coverage lines, one per year>

  ## `shock_support_break_short`

  <logs/v211-count-shock_support_break_short.md, verbatim>

  ## `shock_failed_bounce_short`

  <logs/v211-count-shock_failed_bounce_short.md, verbatim>

  ## Reading (outcome-blind)

  <one or two sentences per idea, from the tables only: total events, total shock weeks, the years with zero events. If a count is under 300 or has empty years: the shot still runs as registered, and a SCREEN-UNDERPOWERED or a year-rule fail driven by empty years will be read as such. No R, no win rate, no guess at the verdict.>
  ```

If a count printout carries a `**Gate:** … no run …` line, keep it verbatim and add under the Reading: *"That gate line is the v182 convention; spec v209 § Track 2 overrides it for these two ideas: the preflight never decides whether to shoot."* Then:

```bash
git add docs/superpowers/results/<run-date>-v211-shock-preflight.md
git commit -m "docs(v211): outcome-blind preflight for both shock-short screens" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Shot 1, through `backtest-runner`, once**

First record the exact line for a resume: `echo "--date <run-date>" > logs/v211-screen-shock_support_break_short.cmd`. Then dispatch the `backtest-runner` agent (main checkout) with exactly this command; every flag not named stays default, so the default `--ledger` and `--results-dir` the hook requires:

```bash
python scripts/backtest/screen_idea.py --idea shock_support_break_short --date <run-date> --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext --checkpoint-dir data/screen_checkpoints/screen-shock_support_break_short > logs/v211-screen-shock_support_break_short.log 2>&1
```

Tell the runner: the progress line flushes a percent per ticker; report it while the run is long (15 minutes or more). If the process dies with no results doc on disk, re-issue **this identical line** (it resumes from the checkpoint; the log's line `[shock_support_break_short] checkpoint …: <k> ticker(s) already screened` confirms it). Never change a flag, never use `python -m`, never delete the checkpoint. Ask it to return only the exit code and the log's last line (`screen-shock_support_break_short: <VERDICT>, N=…, dExpR=…R, lower95=…R, …/9 years -> docs/superpowers/results/<run-date>-screen-shock_support_break_short.md`). Relay that line only.

Expected: exit 0, the results doc on disk and one new last ledger line. A refusal (exit 2) or a crash after the doc was written: **do not run it again**; report the exit code and the log's last 20 lines to the partner and wait.

- [ ] **Step 10: Verify the record**

```bash
tail -1 docs/superpowers/results/preregistration-ledger.jsonl
head -10 docs/superpowers/results/<run-date>-screen-shock_support_break_short.md
grep -c "^## Shock read-outs (v211; descriptive, never gating)\|^## Context series (v211 level)\|^\*\*Shock-day null\*\*\|^\*\*Re-priced at 3 x slippage\*\*\|^\*\*Gap split\*\*\|^\*\*Day of the episode\*\*\|^\*\*Unconditional control\*\*\|^\*\*Short-family BH q\*\*\|^| BREADTH_ATR1 |\|^| ^VIX |" docs/superpowers/results/<run-date>-screen-shock_support_break_short.md
grep -n "skipped_overlap\|not the live market-shock detector" docs/superpowers/results/<run-date>-screen-shock_support_break_short.md
```

Expected: the last ledger line has `"id": "screen-shock_support_break_short"`, the relayed verdict, `"record": "docs/superpowers/results/<run-date>-screen-shock_support_break_short.md"` and a hypothesis starting `shock_support_break_short: ` that names `BREADTH_ATR1, ^VIX levels`; the `grep -c` prints `10`; the last grep shows `skipped_overlap` and the level scope sentence (index § Global Constraints, exact copy). A missing block is a V211-11/11b defect: report it to the partner. The shot is still spent, and the doc is never regenerated by a second run.

- [ ] **Step 11: Commit the record, then drop the checkpoint**

Edit the results doc: directly under its H1 line insert one blank line and `**Definition commit:** <hash from Step 2>` (screen skill Step 8). Then:

```bash
git add docs/superpowers/results/<run-date>-screen-shock_support_break_short.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v211): screen shock_support_break_short -- <VERDICT exactly as printed>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short docs/superpowers/results/
rm -r data/screen_checkpoints/screen-shock_support_break_short
```

Expected: one commit with exactly those two files; `git status --short docs/superpowers/results/` prints nothing; the checkpoint directory is gone (the record is committed, so no restart can need it). Report the verdict line to the partner as printed, nothing more; the family reading waits for V211-15.

### Task V211-14: Shot 2 (`shock_failed_bounce_short`)

**Model:** sonnet — the same ritual as V211-13's shot, on data already built and pinned; one dispatched run and one commit.

**Files:**
- Create: `docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md` (written by the script)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row appended by the script)

**Interfaces:**
- Consumes: V211-13's committed pin, preflight doc and shot-1 record (ledger row `screen-shock_support_break_short`); V211-13 Step 2's definition commit; the idea `IDEAS["shock_failed_bounce_short"]` (V211-9).
- Produces: ledger row `screen-shock_failed_bounce_short` and its results doc, whose `**Short-family BH q**` table includes shot 1's row (`screen_idea.short_family_q` reads the ledger as it stands, so shot 1 must be committed first). V211-15 reads both docs.

**One shot, never re-run**, exactly as V211-13. The data files are not rebuilt, refetched or re-pinned; the preflight for this idea is already committed in V211-13's preflight doc and is not recomputed.

- [ ] **Step 1: Shot 1 is recorded, nothing moved since**

```bash
git log --oneline -6 -- docs/superpowers/results/
grep -n '"id": "screen-shock_' docs/superpowers/results/preregistration-ledger.jsonl
ls docs/superpowers/results/*-v211-shock-preflight.md data/screen_checkpoints/
git status --short swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py docs/superpowers/results/
git log -1 --format=%H -- swingbot/core/backtesting/screen/ scripts/backtest/screen_idea.py
git diff HEAD --stat -- docs/superpowers/results/2026-10-18-v174-context-hashes.json
```

Expected: the log shows V211-13's three commits (pin, preflight, `docs(v211): screen shock_support_break_short -- …`); the `grep` finds exactly one row, `screen-shock_support_break_short`; the preflight doc exists; `data/screen_checkpoints/` holds no `screen-shock_failed_bounce_short/` (an existing one means this task was cut off mid-shot: go to Step 4 and resume with the identical command from `logs/v211-screen-shock_failed_bounce_short.cmd`); `status` prints nothing; the definition hash **equals** V211-13's (read it from the preflight doc's `**Definition commit:**` line — a different hash means screen code changed between the shots: stop and report it to the partner); the pin file has no diff. A row or results doc for `shock_failed_bounce_short` already present: the shot is spent; go to Step 5.

- [ ] **Step 2: The idea's tests and the pinned context still pass**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_failed_bounce_short.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
```

Expected: both `0 failed`, `0 xfailed`. A failure here is reported to the partner; the shot does not run on a red idea.

- [ ] **Step 3: Fix the run date**

Run `date -u +%Y-%m-%dT%H:%M` and convert to the Berlin day (this part's header). `<run-date>` is that day; it may differ from V211-13's.

- [ ] **Step 4: Shot 2, through `backtest-runner`, once**

Record the line for a resume: `echo "--date <run-date>" > logs/v211-screen-shock_failed_bounce_short.cmd`. Then dispatch the `backtest-runner` agent (main checkout, `E:/Documents/Private/Projects/Discord-Bot`) with exactly this command (defaults for everything not named):

```bash
python scripts/backtest/screen_idea.py --idea shock_failed_bounce_short --date <run-date> --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext --checkpoint-dir data/screen_checkpoints/screen-shock_failed_bounce_short > logs/v211-screen-shock_failed_bounce_short.log 2>&1
```

Tell the runner what V211-13 Step 9 told it: report the flushed percent while the run is long; a process that dies with no results doc on disk is resumed with **this identical line** (the log line `[shock_failed_bounce_short] checkpoint …: <k> ticker(s) already screened` confirms the resume); never change a flag, never `python -m`, never delete the checkpoint. Ask for only the exit code and the log's last line (`screen-shock_failed_bounce_short: <VERDICT>, N=…, dExpR=…R, lower95=…R, …/9 years -> docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md`). Relay that line only.

Expected: exit 0, the results doc on disk and one new last ledger line. A refusal (exit 2) or a crash after the doc was written: **do not run it again**; report the exit code and the log's last 20 lines to the partner and wait.

- [ ] **Step 5: Verify the record, including shot 1 in the family q**

```bash
tail -1 docs/superpowers/results/preregistration-ledger.jsonl
head -10 docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md
grep -c "^## Shock read-outs (v211; descriptive, never gating)\|^## Context series (v211 level)\|^\*\*Shock-day null\*\*\|^\*\*Re-priced at 3 x slippage\*\*\|^\*\*Gap split\*\*\|^\*\*Day of the episode\*\*\|^\*\*Unconditional control\*\*\|^\*\*Short-family BH q\*\*\|^| BREADTH_ATR1 |\|^| ^VIX |" docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md
grep -n "screen-shock_support_break_short\|screen-shock_failed_bounce_short\|screen-range_breakdown_close\|v104-b-short-mechanisms" docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md
grep -n "| BREADTH_ATR1 |\|| ^VIX |" docs/superpowers/results/*-screen-shock_*.md
```

Expected: the last ledger line has `"id": "screen-shock_failed_bounce_short"`, the relayed verdict, its doc as `record`, and a hypothesis starting `shock_failed_bounce_short: `; the `grep -c` prints `10`; the q table lists `screen-shock_support_break_short` and `screen-shock_failed_bounce_short` beside `screen-range_breakdown_close` (and `v104-b-short-mechanisms` as `n/a` if its row has no p); the two docs' context rows carry the **same** SHA-256 for each series (the data did not move between the shots). A missing block or a q table without shot 1 is a V211-11b defect: report it to the partner. The shot is still spent.

- [ ] **Step 6: Commit the record, then drop the checkpoint**

Edit the results doc: directly under its H1 line insert one blank line and `**Definition commit:** <hash from Step 1>`. Then:

```bash
git add docs/superpowers/results/<run-date>-screen-shock_failed_bounce_short.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v211): screen shock_failed_bounce_short -- <VERDICT exactly as printed>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short docs/superpowers/results/
rm -r data/screen_checkpoints/screen-shock_failed_bounce_short
rmdir data/screen_checkpoints
```

Expected: one commit with exactly those two files; `status` prints nothing; both checkpoint paths are gone (`rmdir` fails harmlessly if another run's directory is still there — leave that one alone). Report both verdict lines to the partner as printed, nothing more; the family reading is V211-15's.

### Task V211-15: Record the verdicts: closed list, summary doc

**Model:** sonnet — transcription of two recorded verdicts into a fixed table and a templated doc; the only judgement is picking the spec's reading for the case that occurred, word for word.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (two rows appended to the table under `### Closed pre-registrations — do not re-run these`, directly after the `range_breakdown_stop` [v182] row)
- Modify: `AGENTS.md` only if it mirrors that table (Step 1 decides; today it does not)
- Create: `docs/superpowers/results/<date>-v211-shock-short-screens.md`

**Interfaces:**
- Consumes: the two committed results docs and ledger rows (V211-13, V211-14); the preflight doc (V211-13); `screen_idea.SHORT_SCREEN_IDS` and the `**Short-family BH q**` table printed in shot 2's doc (V211-11b) — that table is the family q, never recomputed by hand.
- Produces: the summary doc (both verdicts, the short-family q-values, what a pass or a fail opens) and the two closed-list rows. V211-16's panel reads all three docs; its close-out reads the verdicts for the `Edge:` amendment.

**Nothing here changes a recorded number.** Every figure is copied from a results doc or the preflight doc, with its doc named. No figure is re-derived, rounded differently, or recomputed from the ledger. A verdict is quoted exactly as printed.

- [ ] **Step 1: Read the inputs (bounded) and check the mirror**

```bash
tail -2 docs/superpowers/results/preregistration-ledger.jsonl
for f in docs/superpowers/results/*-screen-shock_*.md; do echo "== $f"; head -14 "$f"; grep -n -A 12 "^\*\*Short-family BH q\*\*\|^\*\*Unconditional control\*\*\|^\*\*Shock-day null\*\*\|^\*\*Re-priced at 3 x slippage\*\*" "$f" | head -60; done
grep -n -A 12 "^## Reading" docs/superpowers/results/*-v211-shock-preflight.md
grep -n "range_breakdown_stop\` -- same range" docs/claude/backtest-methodology.md
grep -n -i "closed pre-registrations\|range_breakdown" AGENTS.md
```

Expected: the two ledger rows `screen-shock_support_break_short`, `screen-shock_failed_bounce_short`; per doc: verdict, N, ΔExpR, lower 95 %, years positive, the event arm's mean R after costs, the control's ΔExpR, the shock-day null's ΔExpR, the 3× re-price ΔExpR, `skipped_overlap`; shot 2's q table; one line number for the v182 stop row. The `AGENTS.md` grep finds nothing (the mirror carries no closed list): leave `AGENTS.md` alone. If it does find the table, add the same two rows there, condensed to the component name, the verdict and the record.

- [ ] **Step 2: Append the two closed-list rows**

Insert directly after the `range_breakdown_stop` [v182] row, one row per idea, in the table's existing format (`| component [vN] | **outcome** | record |`), filled from the docs:

  ```markdown
  | `shock_support_break_short` -- breadth-shock-conditioned support break: SHOCK_D on `t` (enter `BREADTH_ATR1 >= 0.40`; release on `BREADTH_ATR1 <= 0.10` with `^VIX` down, the release day still SHOCK), `Close[t] < min(Low[t-20..t-1])`, first such close in the episode; short at the next open, fixed 1.5/3.0 ATR race vs K=20 matched null raced short, cap 10, 5 bps, commission, borrow; PIT S&P 500 2010-2019 [v211] | **<VERDICT>, one shot spent.** N <n>, ΔExpR <x>R, lower95 <x>R, <k> of 9 years; event arm <x>R after costs; unconditional control ΔExpR <x>R; shock-day null ΔExpR <x>R; 3x slippage ΔExpR <x>R; `skipped_overlap` <n>; short-family BH q <q>. Effective N: <total shock weeks> shock weeks, zero-event years <list or "none"> (preflight). Never re-run; a changed threshold, window, trigger or release rule is a new idea with a new name; a pass does not license the live detector's labels. | `results/<run-date>-screen-shock_support_break_short.md`, `results/<run-date>-v211-shock-preflight.md` |
  | `shock_failed_bounce_short` -- breadth-shock-conditioned failed bounce: SHOCK_D on `t`; decline ≥ 1.0 × `ATR14[b-2]` from `max(High[b-10..b-2])`, bounce bar `b ∈ t-5..t-1` with `Close[b] > Close[b-1]` and `High[b] < max(High[b-10..b-2])`, first `Close[t] < Low[b]`, latest `b`; same race, costs and universe [v211] | **<VERDICT>, one shot spent.** <the same fields, from its own doc>. Same family as `shock_support_break_short` (`FAMILY` `shock_breakdown`); never re-run. | `results/<run-date>-screen-shock_failed_bounce_short.md`, `results/<run-date>-v211-shock-preflight.md` |
  ```

A `SCREEN-PASS` row replaces the last sentence's "Never re-run" with "Never re-run; the follow-on spec is `results/<date>-v211-shock-short-screens.md` § What follows". The q column cites the value printed in **shot 2's** doc for that id (it includes both rows).

- [ ] **Step 3: Write the summary doc**

Create `docs/superpowers/results/<date>-v211-shock-short-screens.md` (`<date>` = today's Berlin day, this part's header) from this template. Every `<…>` is filled from the docs; of the three `What follows` cases keep **only** the one that occurred and delete the other two:

  ```markdown
  # v211 shock-conditioned short screens — summary

  **Spec:** `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md` § Track 2
  **Plan:** `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_0-index.md`
  **Pass rule (frozen, unchanged):** ΔExpR ≥ +0.10R after costs, lower 95 % week-cluster bound > 0, ≥ 7 of 9 years (2011–2019) positive, N ≥ 300 (`docs/claude/backtest-methodology.md` § Stage −2). One shot each.
  **Preflight (outcome-blind, committed before shot 1):** `results/<run-date>-v211-shock-preflight.md`

  | Idea | Verdict | N | ΔExpR | 95 % interval | Years positive | Shock weeks | Record |
  |---|---|---|---|---|---|---|---|
  | `shock_support_break_short` | <VERDICT> | <n> | <x>R | [<lo>, <hi>] | <k>/9 | <weeks> | `results/<run-date>-screen-shock_support_break_short.md` |
  | `shock_failed_bounce_short` | <VERDICT> | <n> | <x>R | [<lo>, <hi>] | <k>/9 | <weeks> | `results/<run-date>-screen-shock_failed_bounce_short.md` |

  **<m> of 2 passed.**

  ## Printed beside each verdict (never gating)

  | Idea | Event arm R | Unconditional control ΔExpR | Shock-day null ΔExpR | 3x slippage ΔExpR | `skipped_overlap` | Gap `>= +1%` ΔExpR (n) | `peak` vs `later` ΔExpR |
  |---|---|---|---|---|---|---|---|
  | `shock_support_break_short` | <x>R | <x>R | <x>R | <x>R | <n> | <x>R (<n>) | <x>R / <x>R |
  | `shock_failed_bounce_short` | <x>R | <x>R | <x>R | <x>R | <n> | <x>R (<n>) | <x>R / <x>R |

  **Short-family BH q** (every short idea screened so far, `screen_idea.SHORT_SCREEN_IDS`, as printed in shot 2's doc): <id = q, one per id; `v104-b-short-mechanisms` n/a (no p)>.

  ## What the screens can and cannot say (spec § What the screens can and cannot say)

  - They test the daily `SHOCK_D` proxy on the point-in-time S&P 500. **A pass does not license the Track 1 detector's labels** (no sector clause, no fast path, no VIX relief, no RECOVERY tier; index membership, not the watchlist).
  - The year rule may sink a crash-only edge: <the preflight's zero-event years, or "no year was empty">. <If a fail rests mainly on empty years, say so here in one sentence.> A `SCREEN-FAIL` or `SCREEN-UNDERPOWERED` is closed and never re-run with a looser definition.
  - The shadow log (plans v209, v210) can motivate a new idea; it can never license one.

  ## What follows

  **Both `SCREEN-PASS`:** <case text A>
  **Only `<idea>` passes:** <case text B>
  **Neither passes:** <case text C>

  ## Binding on any follow-on (partner, 2026-11-06; spec § Track 1, `MARKET_SHOCK_MODE` note)

  The focus is SHORT performance, and **LONG issuing works as normal on a bullish day**. Any live behaviour may touch longs only while the label is SHOCK (or RECOVERY, if screened); under NORMAL the long lane stays **byte-identical to `MARKET_SHOCK_MODE=off`**, pinned by a regression test, and the follow-on's screen must show NORMAL-day longs unchanged. Nothing in this plan changed a live path: LONG issuing is byte-for-byte what it was.
  ```

The three case texts (spec § What the screens can and cannot say, § Follow-on pre-registrations; write the one that occurred, verbatim apart from the idea names):

- **A — both pass:** "Both triggers carry information at daily resolution while a breadth shock is on. They are one family (`shock_breakdown`, BH q above), so the follow-on picks one trigger or justifies both. The follow-on is a **spec for the live meaning of `MARKET_SHOCK_MODE=live`**, carrying `**Screen:** screen-<idea> SCREEN-PASS` and `Edge: expectancy`, and it replays the live detector itself first: Stage −1 reachability on the bot's own replay over the 15-minute Alpaca store (v162, history from about 2016), then the unchanged funnel. Its order path must handle the short-sale uptick rule (SSR), hard-to-borrow/no-locate names and squeeze risk, starting from v183's gap-aware short sizing and squeeze notice; Idea 2's placeable stop is a buy-stop above `High[b]`. A long block in SHOCK opens only together with that passing short arm (gate tightening ships paired with a widening) and is judged on the bot's replay; a stop move-up for open longs needs its own `harvest-headroom` doc and the exit funnel. A pass whose ΔExpR is not clearly above its unconditional control or its shock-day null is credited to the market's drift, not to the trigger: both figures are in the table above."
- **B — one passes:** case A's text for the passing idea only, plus: "`<other idea>` failed and is closed; the pass is weaker than a lone pass because the two triggers overlap (one family, BH q above)."
- **C — neither passes:** "Both definitions are closed: breadth-shock-conditioned breakdown shorts at daily resolution, this frozen `SHOCK_D` (enter 0.40, release 0.10 with `^VIX` down), these two triggers, the fixed 10-bar race, short only. That does not close shorting in a shock in general. Live shock behaviour now needs a new idea that passes its own screen, or the bot's-replay funnel on the live detector; `MARKET_SHOCK_MODE` stays `shadow` and the follow-on spec is not written. No re-run, no looser threshold, no other release rule under these names."

- [ ] **Step 4: Check the docs render and the mirror holds**

```bash
grep -n "\[v211\]" docs/claude/backtest-methodology.md
grep -nE "<[^>]{1,60}>" docs/superpowers/results/*-v211-shock-short-screens.md
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: two rows tagged `[v211]`, directly after the v182 stop row; the placeholder `grep` prints nothing (no unfilled `<…>` left in the summary); the mirror test `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/results/<date>-v211-shock-short-screens.md
git commit -m "docs(v211): close both shock-short screens in the methodology list; summary of the verdicts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --short docs/
```

Add `AGENTS.md` to the `git add` only if Step 1 found the mirrored table. Expected: one commit; `status` shows nothing under `docs/` from this task. Report the summary's `<m> of 2 passed.` line and the case that occurred to the partner.

### Task V211-16: `/panel` (staff-engineer, quant-researcher, veteran-trader) + `/close-out`

**Model:** sonnet — two skills run as written over a known range; findings are triaged by fixed rules, and the spec move is one existence check.

**Files:**
- Move (by `/close-out`): `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_{0-index,1-data,2-runner-level-kind,3-ideas,4-readouts,5-shots-closeout}.md` → `docs/superpowers/plans/implemented/`
- Move (by `/close-out`, only when plans v209 **and** v210 are already closed): `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md` → `docs/superpowers/specs/implemented/`; otherwise it stays in `specs/`
- Modify (only if both shots failed): the index's `**Edge:**` line (close-out Step 5)
- Not modified: `VERSION.json`, `swingbot/admin/version_history.json` (`Bump: none`)

**Interfaces:**
- Consumes: the merge of `2026-11-06-v211-shock-short-screens` on `main` (V211-13 Step 1); the records of V211-13..15.
- Produces: nothing for a later task (last task). The plan leaves the live-plan list; the worktree is removed.

**Destination is `implemented/` whatever the verdicts.** The screen code reached `main` (merged in V211-13), and `docs/claude/document-lifecycle.md` § A plan whose code never reached `main` reserves `no-lift/` for plans whose code was deliberately never merged; v182 (one fail, one unspent) closed to `implemented/` the same way. Two fails show up as the `Edge:` amendment below, not as the folder.

- [ ] **Step 1: The panel**

```bash
git log --merges --oneline -1 --grep "merge(v211)" main
git log --oneline -12 -- docs/superpowers/results/ docs/claude/backtest-methodology.md
```

Run `/panel staff-engineer,quant-researcher,veteran-trader` (the spec's `**Panel:**` line) over the merged diff `git diff <merge>^1..<merge>` (`<merge>` from the first command) **together with** the preflight doc, both screen results docs and the summary doc (`docs/superpowers/results/*-v211-shock-preflight.md`, `*-screen-shock_*.md`, `*-v211-shock-short-screens.md`). Handle each finding as the panel skill says, under these fixed rules:

- A code defect gets a failing test and a fix, committed on `main` in its own scoped commit (`fix(v211): …`, `Co-Authored-By` line), run narrowly (`python scripts/dev/testrun.py file <test>`). A fix to `swingbot/core/backtesting/screen/` or `scripts/backtest/screen_idea.py` cannot change a recorded result: report it to the partner beside the fix.
- **Nothing edits a results doc, the preflight doc, a ledger row, the pin file or a context CSV, and nothing re-runs a count or a screen.** A finding that questions a recorded number (a lookahead suspicion, a wrong friction, a miscounted overlap) goes to the partner as a finding, with the doc and line it concerns; the partner decides whether the definition is a new idea under a new name.
- A finding about the summary doc's wording (not its numbers) is fixed in a `docs(v211): …` commit.
- An unresolved `BLOCKING` finding stops this task here: report it and wait (close-out skill Step 2).

Expected: the panel's merged findings reported to the partner; every non-blocking fix committed; no `BLOCKING` left open.

- [ ] **Step 2: Decide the spec's move**

```bash
ls docs/superpowers/plans/ | grep -E "^2026-11-0[56]-v209-|^2026-11-06-v210-"
ls docs/superpowers/plans/implemented/ | grep -E "v209-market-shock-detector|v210-market-shock-notices"
```

Expected, one of two:
- The first `ls` prints nothing and the second lists both plans' files: v209 and v210 are closed, nothing else live builds from the spec → `/close-out` moves the spec to `docs/superpowers/specs/implemented/` with this plan.
- The first `ls` prints any v209 or v210 file: that plan still builds from the spec → the spec **stays** in `docs/superpowers/specs/`; the close-out move commit carries the line `spec stays: plan <v209 | v210 | v209 and v210> still holds it (live in docs/superpowers/plans/)`, naming the plan(s) the `ls` found. The last of the three plans to close moves it.

- [ ] **Step 3: `/close-out`**

Run `/close-out` (standing permission, `docs/claude/document-lifecycle.md` § Close-out needs no go-ahead) with these inputs fixed in advance:

- **Bump:** `none` → no `VERSION.json` edit, no release commit, no `version_history.json` regeneration (skill Step 3–4 skipped; Step 5 still runs).
- **Step 5, `Edge:` check:** both verdicts `SCREEN-FAIL`/`SCREEN-UNDERPOWERED` → amend the index's `**Edge:**` line to `**Edge:** expectancy, measured none — both one-shot screens failed (<run-date docs>); no live change shipped, as predicted.` in the move commit. One or two `SCREEN-PASS` → the prediction held (a passing short arm exists to build on); no amendment.
- **Step 5b, skills:** `git grep -n "count-only\|--checkpoint-dir\|--pin-context\|CONTEXT_KIND\|screen_idea" -- .claude/skills .claude/agents` and align any skill or agent whose text the v211 diff made stale (new runner flags, the level context kind), with its Codex mirror (`python scripts/dev/sync_codex.py`) in a `docs(skills): align <skill> with v211` commit; otherwise write `skills: none affected` in the move commit.
- **Step 6, move:** all six plan files to `docs/superpowers/plans/implemented/` (this task's header); the spec per Step 2.
- **Step 7, worktree:** remove `.claude/worktrees/2026-11-06-v211-shock-short-screens` and its branch per `document-lifecycle.md` § Worktrees are named after the plan. Before deleting the branch: `git rev-list --count main..2026-11-06-v211-shock-short-screens` must print `0` (stop on any other number and ask the partner); never touch a branch whose name contains `backup` or starts `stable-` (`docs/claude/git-safety.md`).

Expected:

```bash
git status --short docs/
ls docs/superpowers/plans/ | grep v211
git worktree list
git branch --list "2026-11-06-v211-*"
```

`status` prints nothing under `docs/`; no v211 plan file is left at the top of `plans/`; the worktree list and the branch list no longer show v211. No full suite runs (CI ran it on the merge). Report to the partner: the two verdicts, where the spec went (moved, or which plan still holds it), the `Edge:` line as it now reads, and the panel's outcome.

