# v172 Equity candlestick chart, part 3c: full suite, release, VM backfill, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V172-12:" -A 200 docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_3c-suite-release-closeout.md`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md) (§ 3 "VM run", `## Success criteria`, `**Panel:**` line)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md) — **Global Constraints, Parallelisation, the task ledger and `$WT`/`$R` are defined there.** Split from part 3 (`_3-dashboard-ui-release.md` V172-8, `_3b-equity-candles-component.md` V172-9..V172-10) to keep each file under 1500 lines.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`, branch `2026-10-17-v172-equity-candlestick-chart`. Never `cd`; use absolute paths and `git -C`. Production is reached only through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"`; any live fix made there is mirrored into this repo and committed before the task counts as done (`mirror-prod` skill).

# Phase 4 — Verify, release, backfill, close out

### Task V172-11: Full suite (Python + frontend)

**Model:** haiku — run and record, no judgement

**Files:** none (a failure is fixed in the file that broke, as its own scoped commit, then re-run alone)

**Interfaces:**
- Consumes: every commit of V172-1..V172-10 on the branch.
- Produces: the recorded green counts V172-14 writes into the index `## Progress` block.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: no uncommitted change; one commit (or more) per task V172-1..V172-10, ten task subjects in all.

- [ ] **Step 2: Run the Python full suite once**

Dispatch the `test-runner` subagent (so none of the output lands in this context) with: run `python $WT/scripts/dev/testrun.py full` with the local test Postgres (`db-test`) up; report the pass/fail/xfail/skip counts and the first failure's node id and assertion only.

Expected: `0 failed` and `0 xfailed`. A changed pass count against the last baseline is not a failure (`testing-cost.md`). A DB-skipped run (db-test down) does not count: start `db-test` and re-run.

- [ ] **Step 3: Run the frontend suite and production build once**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
npm --prefix $WT/frontend run build
```

Expected: Vitest `0 failed`; the build ends without errors (CI runs the same two commands, `deploy.yml` "Unit tests" and "Production build").

- [ ] **Step 4: Complexity of every Python function the plan wrote or changed**

```bash
python -m radon cc -s -n C $WT/swingbot/core/tracking/equity.py $WT/swingbot/core/tracking/equity_candles.py $WT/swingbot/core/db/repositories/equity_samples.py $WT/swingbot/commands/scanning/equity_recorder.py $WT/swingbot/commands/scanning/loops.py $WT/swingbot/admin/api_v1/equity.py $WT/swingbot/admin/api_v1/dashboard.py $WT/swingbot/admin/api_v1/trades.py $WT/swingbot/admin/dashboard.py $WT/scripts/data/backfill_equity_samples.py
```

Expected: every function listed scores below 15, except legacy functions this plan did not touch (`dashboard` 21 in `api_v1/dashboard.py`; compare any other ≥ 15 entry with `git -C $WT show main:<path>` run through the same command, and it must be unchanged). `trade_monitor` scores ≤ 14.

- [ ] **Step 5: Fix any failure alone, then record**

A failing test is fixed in its own scoped commit on the branch (`fix(<area>): ... (v172)`) and re-run alone (`python $WT/scripts/dev/testrun.py file <test>` or the one `ng test --include <spec>`), never by re-running the whole suite. Record in the task report: the Python counts (passed / skipped / 0 failed / 0 xfailed), the Vitest count, the build result, and the radon line for `trade_monitor`.

- [ ] **Step 6: Commit**

Nothing to commit when the suite was green on the first run. Otherwise the fix commits from Step 5 are this task's commits; end each message with the attribution line from the session's system reminder, then `git -C $R status --short` shows no change from this task.

### Task V172-12: Panel, merge to `main`, release bump (ui minor, bot minor), push and deploy

**Model:** sonnet — panel findings and merge need judgement

**Files:**
- Modify: `VERSION.json` (two release commits: `ui` minor, then `bot` minor)
- Modify: `swingbot/admin/version_history.json` (regenerated after each release commit)

**Interfaces:**
- Consumes: V172-11's green run on the branch.
- Produces: `main` carrying the merge and four release commits; a deployed build on the VM with Alembic at `v172_001` (consumed by V172-13).

- [ ] **Step 1: Run the panel over the full diff**

The spec carries `**Panel:** staff-engineer, financial-advisor, quant-engineer`. Run:

```
/panel staff-engineer,financial-advisor,quant-engineer main...2026-10-17-v172-equity-candlestick-chart
```

with V172-11's recorded results as context. A `BLOCKING` finding stops this task: fix it on the branch as its own scoped commit (`fix(<area>): ... (v172 panel)`), re-run only the tests of the files it touched (`testrun.py file ...` / `ng test --include ...`), and re-run the panel for that role. Each `ADVISORY` finding is applied the same way or recorded with a one-line reason in the task report. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 2: Bring `main` into the branch, then check the migration chain**

Follow the `worktree-lifecycle` skill (other sessions share `$R`):

```bash
git -C $R status --short
git -C $WT merge main -m "merge: main into v172 equity candlestick chart before release"
python $WT/scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `$R` has no change of this plan's files pending; the merge is clean or its conflicts are resolved file by file; `test_migrations.py` passes, which asserts a single Alembic head (`alembic.ini`'s `script_location` is cwd-relative, so the test, not a bare `alembic heads` from another directory, is the check). If `main` gained a revision after V172-2, set `down_revision` in `swingbot/core/db/migrations/versions/v172_001_equity_samples.py` to that revision (`schema-evolution.md` § Revision ids), commit it on the branch (`fix(db): rebase v172_001 onto <rev>`), and re-run `tests/db/test_migrations.py` and `tests/db/test_v172_tables.py` alone. Re-run alone the tests of any file the merge conflicted in. No full suite here: it ran in V172-11.

- [ ] **Step 3: Merge the branch into `main`**

```bash
git -C $R switch main
git -C $R merge --no-ff 2026-10-17-v172-equity-candlestick-chart -m "merge: v172 equity candlestick chart (equity samples recorder, candles API, raw-bar backfill, dashboard candles)"
git -C $R log --oneline -3
```

End the merge message with the attribution line from the session's system reminder. Expected: a merge commit on `main`. No full suite after this merge (CLAUDE.md).

- [ ] **Step 4: Release the ui line (minor)**

Read the current values from disk (never from this plan): `python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"`. Then bump `ui` by one minor and stamp it:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, _patch = (int(part) for part in version["ui"].split("."))
version["ui"] = f"{major}.{minor + 1}.0"
version["ui_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["ui"])
EOF
git -C $R diff VERSION.json
```

Expected: only the `ui` and `ui_updated` lines change. Commit, regenerate, commit (two commits, in this order):

```bash
git -C $R add VERSION.json
git -C $R commit -m "release(ui): <ui version> -- equity candlestick chart on the Dashboard: 1H/4H/1D/1W, open + closed or closed-only, OHLC readout (v172)"
python $R/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -m "chore(ui): <ui version> -- equity candlestick chart on the Dashboard: 1H/4H/1D/1W, open + closed or closed-only, OHLC readout (v172)"
```

Replace `<ui version>` with the printed value. End each message with the attribution line from the session's system reminder.

- [ ] **Step 5: Release the bot line (minor)**

The same as Step 4 with `bot`/`bot_updated`:

```bash
python - <<'EOF'
import datetime
import json
import pathlib

path = pathlib.Path(r"E:/Documents/Private/Projects/Discord-Bot/VERSION.json")
version = json.loads(path.read_text(encoding="utf-8"))
major, minor, _patch = (int(part) for part in version["bot"].split("."))
version["bot"] = f"{major}.{minor + 1}.0"
version["bot_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
print(version["bot"])
EOF
git -C $R diff VERSION.json
git -C $R add VERSION.json
git -C $R commit -m "release(bot): <bot version> -- equity samples recorded by the trade monitor, equity candles API, raw-bar backfill script (v172)"
python $R/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -m "chore(bot): <bot version> -- equity samples recorded by the trade monitor, equity candles API, raw-bar backfill script (v172)"
python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: only the `bot` lines change in the diff; the version-matrix test passes (it is the one check the pre-bump suite cannot make).

- [ ] **Step 6: Push and watch the deploy**

```bash
git -C $R push origin main
gh run list --branch main --limit 1
gh run watch <run id from the line above> --exit-status
```

Expected: every suite job, the frontend "Unit tests" and "Production build", and the deploy job succeed. `deploy/deploy.sh` runs `alembic upgrade head` on the VM. A red job is fixed on `main` as its own scoped commit and pushed again; never re-run blindly.

- [ ] **Step 7: Verify the deploy on the VM (read-only)**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current </dev/null"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 20m bot 2>&1 | grep -iE 'equity|Traceback' | tail -20"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c \"from swingbot.core.db.repositories.equity_samples import equity_samples_repo as r; print(r().latest_at('live'))\" </dev/null"
```

Expected: `v172_001 (head)`; no traceback mentioning the recorder (one logged warning per error type is the designed behaviour, and is reported if present); `latest_at('live')` is a recent timestamp during the regular US session, or `None` when the deploy landed outside it (the recorder writes only while `is_regular_session(now)`). If it is still `None` 10 minutes into a regular session, report it with the bot log lines; do not patch production by hand.

- [ ] **Step 8: Commit**

The commits of Steps 3-5 are this task's commits (merge, `release(ui)`, `chore(ui)`, `release(bot)`, `chore(bot)`). `git -C $R status --short` shows nothing from this task.

### Task V172-13: VM backfill: dry run, read coverage, `--apply`, verify

**Model:** sonnet — reads a coverage report and decides on gaps

**Files:** none (VM only). Any live fix made on the VM is mirrored into this repo and committed on `main` before the task counts as done (`mirror-prod` skill).

**Interfaces:**
- Consumes: V172-12's deployed build (`v172_001` migrated, `scripts/data/backfill_equity_samples.py` in the image); V172-7's CLI: dry run by default, `--apply`, `--replace`, `--allow-gaps`, `--recompute-realized`; `main()`'s summary keys `run_id, bars_asof, days, rows, written, gaps, skipped, recomputed`; V172-2's `equity_samples_repo()`.
- Produces: `source="backfill"` rows on production from the first main-book trade to the session before the first live sample.

- [ ] **Step 1: Dry run and read the coverage report**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py </dev/null"
```

Expected: the run id, the bars as-of date, the days covered (first day = the earliest main-book `opened_at` date), each skipped position with its reason (`no size`, `no entry`, `no exit price`, `fetch failed`, `no bar`), the gap count, and the dry-run notice; nothing is written. The VM needs network access to yfinance for this fetch.

- [ ] **Step 2: Handle gaps**

No gap → go to Step 3. A gap (`fetch failed` / `no bar`) → re-run Step 1 once, since a yfinance fetch can fail transiently (spec § 3). Still gapped → ask the partner with `AskUserQuestion`, one question, listing each gapped ticker and day count: recommended option first, "Apply with `--allow-gaps` (these positions are left out on those days and counted in `skipped_n`)", then "Do not backfill yet; I will look at the tickers". Never pass `--allow-gaps` without that answer.

- [ ] **Step 3: Apply**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py --apply </dev/null"
```

(add `--allow-gaps` only on the partner's yes from Step 2). Expected: the same run id/bars as-of shape as the dry run, `written` = 4 × the days covered, gaps 0 (or the approved count).

- [ ] **Step 4: Verify the rows and that a re-run writes nothing**

Write `<scratchpad>/v172-verify.py` (session scratchpad, never the repo):

```python
from collections import Counter

from swingbot.core.db.repositories.equity_samples import equity_samples_repo

repo = equity_samples_repo()
rows = repo.list_rows(sources=("backfill",))
print("backfill rows:", len(rows), dict(Counter(r["kind"] for r in rows)))
print("first:", rows[0]["at"] if rows else None, "last:", rows[-1]["at"] if rows else None)
print("runs:", sorted({r["backfill_run"] for r in rows}))
print("live since:", repo.earliest_at("live"))
```

Pipe it in (the documented stdin form), then dry-run again:

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "<scratchpad>/v172-verify.py"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_equity_samples.py </dev/null"
```

Expected: `point` = 2 × days, `day_high` = `day_low` = days; one `backfill_run` value of the form `<run id>@bars-asof-<date>`; the last backfill `at` is before `live since` (or before today when there is no live row); the second dry run reports 0 days left to write.

- [ ] **Step 5: Look at the chart on production at three widths (Playwright)**

```bash
node $R/frontend/scripts/browse.mjs shots --out "<scratchpad>/v172-prod" --path "app/" --widths 1280,768,390
```

The window is headed; the partner types the production credentials if the profile's session has expired (never script, ask for or store them). If `app/` does not land on the Dashboard, re-run with the path the address bar shows for it. Open the three `*.png` files with the Read tool and confirm: daily candles back to the first trade, rebuilt candles hollow, the caption `Before <date>: rebuilt from daily bars — ranges are outer bounds`, the `Recording started` line once live samples exist, `Paper account · before tax and costs` under the chart, and no horizontal scroll at 390. Check the `*.txt` files for the readout text. If V172-10's local three-width check could not run, this step is that check; record the measurements by eye in the task report.

- [ ] **Step 6: Commit**

Nothing to commit when nothing was changed on the VM. A live fix is mirrored into the repo and committed on `main` as its own scoped commit (`fix(<area>): ... (v172, mirrored from production)`), ending with the attribution line from the session's system reminder. Record the dry-run summary, the applied summary and Step 4's counts in the task report.

### Task V172-14: Close-out: move plan and spec to `implemented/`, remove worktree

**Model:** haiku — the close-out checklist

**Files:**
- Modify: `docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_0-index.md` (`## Progress` block), then `git mv` it and every part file into `docs/superpowers/plans/implemented/`:
  every `docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_*.md` (the index's `## Parts` table lists them: `_0-index`, `_1-core`, `_1b-candles`, `_2-recorder-api-backfill`, `_2b-backfill-cli`, `_3-dashboard-ui-release`, `_3b-equity-candles-component`, `_3c-suite-release-closeout`)
- Move: `docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md` → `docs/superpowers/specs/implemented/`

**Interfaces:**
- Consumes: V172-11's recorded counts, V172-12's panel result and release commits, V172-13's backfill summary.
- Produces: nothing; the plan leaves the live set and the SessionStart `PLAN WIP` line stops naming it.

- [ ] **Step 1: Run the `close-out` skill, with two of its steps already done**

Invoke `/close-out`. Its Step 2 (panel) ran in V172-12 Step 1, and Steps 3-4 (bump and regeneration) ran in V172-12 Steps 4-5: confirm both from the log rather than repeating them:

```bash
git -C $R log --oneline -8 -- VERSION.json swingbot/admin/version_history.json
python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"
```

Expected: `release(ui)`, `chore(ui)`, `release(bot)`, `chore(bot)` commits naming v172, and `VERSION.json` showing both lines one minor above the values before V172-12. Do not bump again. Step 5 of the skill: the header said `Bump: ui minor; bot minor` and `Edge: none (integrity)`; both held, so nothing is amended (if one did not, amend the header and say why in one clause in Step 4's commit).

- [ ] **Step 2: Record the results in the index**

Replace the `## Progress` block's `Not started. Update this block when a phase closes.` line in `$R/docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_0-index.md` with:

```markdown
Done <YYYY-MM-DD>. V172-1..V172-14 complete. Full suite (V172-11): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; production build green. Panel (V172-12): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released ui <version>, bot <version>. VM backfill (V172-13): run `<backfill_run>`, <days> days, <written> rows, <gaps> gaps<, --allow-gaps on the partner's yes>.
```

filled from the task reports.

- [ ] **Step 3: Remove the worktree and its branch**

The branch name contains no `backup` and is not `stable-*`. Check it is fully merged first; non-zero means stop and ask the partner:

```bash
git -C $R rev-list --count main..2026-10-17-v172-equity-candlestick-chart
git -C $R worktree remove .claude/worktrees/2026-10-17-v172-equity-candlestick-chart
git -C $R branch -d 2026-10-17-v172-equity-candlestick-chart
git -C $R worktree list
```

Expected: `0`; the worktree and branch are gone (`branch -d`, never `-D`); `worktree list` no longer shows it. A `worktree remove` that refuses because of untracked files means something was left uncommitted: look at it before deciding, never `--force` by default.

- [ ] **Step 4: Move the documents and commit on `main`**

```bash
ls $R/docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_*.md
for f in $R/docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_*.md; do git -C $R mv "$f" $R/docs/superpowers/plans/implemented/; done
git -C $R mv docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md docs/superpowers/specs/implemented/
git -C $R add docs/superpowers/plans/implemented/2026-10-17-v172-equity-candlestick-chart_0-index.md
git -C $R commit -m "docs(v172): close out -- plan and spec to implemented/, results recorded"
git -C $R status --short
git -C $R push origin main
```

The index's `## Progress` edit from Step 2 rides in this commit (it is staged by the final `git add` after the move). End the commit message with the attribution line from the session's system reminder. Expected: the `ls` lists every row of the index's `## Parts` table (a part missing from it, or an extra file, is checked before moving); one commit that moves the plan parts and the spec and changes the index's Progress block; `git status` clean for these paths; no full suite after this (CLAUDE.md: it ran once, in V172-11).

