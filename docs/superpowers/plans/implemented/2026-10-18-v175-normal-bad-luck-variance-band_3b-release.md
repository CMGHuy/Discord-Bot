# v175 Normal bad luck, part 3b: full suite, panel review and release, deploy check, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V175-13:" -A 200 docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_3b-release.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md`](../specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md) (`**Panel:**` line, § Testing, § Risks)
**Index:** [`2026-10-18-v175-normal-bad-luck-variance-band_0-index.md`](2026-10-18-v175-normal-bad-luck-variance-band_0-index.md) — Global Constraints, Parallelisation, Task ledger and `$WT`/`$R` live there and bind every task below. Split from part 3 (`_3-panel-release.md`, V175-8..V175-11) to keep each file under 1500 lines; the ledger's "part 3" covers both files.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`, branch `2026-10-18-v175-normal-bad-luck-variance-band`. `$SCRATCH` is the implementing session's scratchpad (absolute path): commit messages are written there and passed with `git commit -F`; VM scripts live there; nothing in it is committed. Never `cd`. Production is reached only through `bash $R/scripts/ops/ssh-hetzner.sh "<cmd>"`; any live fix there is mirrored into this repo and committed before its task counts as done (`mirror-prod` skill).

# Phase D: Verify, release, deploy check, close out (V175-12..V175-15)

### Task V175-12: Full suite (Python + frontend)

**Model:** haiku — run and record, no judgement.

**Files:** none (a failure is fixed in the file that broke, as its own scoped commit, then re-run alone)

**Interfaces:**
- Consumes: every commit of V175-1..V175-11 on the branch.
- Produces: the recorded green counts V175-15 writes into the index's `## Progress`.

- [ ] **Step 1: Check the branch is complete and clean**

```bash
git -C $WT status --short
git -C $WT log --oneline main..HEAD
```

Expected: no uncommitted change; at least one commit per code task V175-1..V175-10 (V175-4 also committed its § Progress note on `main`; V175-11 has a commit only if it fixed a style).

- [ ] **Step 2: Run the Python full suite once**

CLAUDE.md: a task that runs tests against the database runs `/replicate-prod-db` first, so run it (it syncs the local replica; the suite itself uses the per-worker test database, and no v175 test reads either). Then dispatch the `test-runner` subagent (so none of the output lands in this context) with: run `python $WT/scripts/dev/testrun.py full` with the local test Postgres (`db-test`) up; report the pass/fail/xfail/skip counts and the first failure's node id and assertion only.

Expected: `0 failed` and `0 xfailed`. A changed pass count against the last baseline is not a failure (`testing-cost.md`). A DB-skipped run (`db-test` down) does not count: start `db-test` and re-run. The plan-embed tests (`tests/scanning/test_embeds_*.py`) are among the green ones, unchanged by this plan (`git -C $WT diff --stat main...HEAD -- tests/scanning/` prints nothing).

- [ ] **Step 3: Run the frontend suite and production build once**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false
npm --prefix $WT/frontend run build
```

Expected: Vitest `0 failed`; the build ends without errors (CI runs the same two commands).

- [ ] **Step 4: Complexity of every Python function the plan wrote or changed**

```bash
python -m radon cc -s -n C $WT/swingbot/core/analytics/variance_band.py $WT/swingbot/admin/api_v1/analytics.py $WT/swingbot/core/presentation/kinds.py $WT/swingbot/commands/scanning/book_status.py
python -m radon cc -s $WT/swingbot/commands/scanning/loops.py | grep _session_scan_tick
python $WT/scripts/dev/complexity_gate.py
```

Expected: the first command lists nothing from `variance_band.py` or `book_status.py`, and any line from `analytics.py`/`kinds.py` names a legacy function this plan did not touch (compare with `git -C $WT show main:<path>` through the same command: unchanged); `_session_scan_tick` reads `C (15)`; the gate passes.

- [ ] **Step 5: Fix any failure alone, then record**

A failing test is fixed in its own scoped commit on the branch (`fix(<area>): ... (v175)`) and re-run alone (`python $WT/scripts/dev/testrun.py file <test>` or the one `ng test --include <spec>`), never by re-running the whole suite. Record in the task report: the Python counts (passed / skipped / 0 failed / 0 xfailed), the Vitest count, the build result, and the `_session_scan_tick` radon line.

- [ ] **Step 6: Commit**

Nothing to commit when the suite was green on the first run. Otherwise the fix commits of Step 5 are this task's commits, each message written to `$SCRATCH/v175-12-fix-<n>-msg.txt` ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and committed with `git -C $WT commit -F`; `git -C $R status --short` shows no change from this task.

### Task V175-13: `/panel`, merge to `main`, release bump (bot minor, ui minor), push

**Model:** sonnet — panel findings and the merge need judgement.

**Files:**
- Modify: `VERSION.json` (two release lines: `bot` minor, then `ui` minor)
- Modify: `swingbot/admin/version_history.json` (regenerated after each release commit)

**Interfaces:**
- Consumes: V175-12's green run on the branch.
- Produces: `main` carrying the merge and four release commits, pushed (CI deploys it; V175-14 watches and checks it).

- [ ] **Step 1: Run the panel over the full diff**

The spec carries `**Panel:** quant-researcher, financial-advisor, veteran-trader`. Run:

```
/panel quant-researcher,financial-advisor,veteran-trader main...2026-10-18-v175-normal-bad-luck-variance-band
```

with V175-12's recorded results and V175-4's measured calibration rates (index § Progress) as context. Each seat checks the spec's own `## Panel review` findings landed: the quant-researcher the close-day netting, week blocks, the 50-day window statistic, the calibration rates against the caption's wording; the financial-advisor the verb-free, "edge"-free copy, ExpR always beside the band with the caveat, "≈ $" with its derivation, "Paper book, before tax"; the veteran-trader that plan embeds are untouched and the message fires only on a zone rise. A `BLOCKING` finding stops this task: fix it on the branch as its own scoped commit (`fix(<area>): ... (v175 panel)`), re-run only the tests of the files it touched (`testrun.py file ...` / `ng test --include ...`), and re-run the panel for that role. Each `ADVISORY` finding is applied the same way or recorded with a one-line reason in the task report. Expected: no unresolved `BLOCKING` finding.

- [ ] **Step 2: Bring `main` into the branch**

Follow the `worktree-lifecycle` skill (other sessions share `$R`):

```bash
git -C $R status --short
git -C $WT merge main -m "merge: main into v175 normal bad luck variance band before release"
```

Expected: `$R` has no change of this plan's files pending; the merge is clean or its conflicts are resolved file by file. v175 adds no Alembic revision, so there is no migration chain to rebase. Re-run alone the tests of any file the merge conflicted in (for `loops.py`, `tests/commands/test_book_status_latch.py` and the `_session_scan_tick` radon line from V175-12 Step 4; for `analytics.store.ts`, the V175-8 spec). No full suite here: it ran in V175-12.

- [ ] **Step 3: Merge the branch into `main`**

Write `$SCRATCH/v175-13-merge-msg.txt`:

```text
merge: v175 normal bad luck (variance band, API, book-status message, Overview panel)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R switch main
git -C $R merge --no-ff 2026-10-18-v175-normal-bad-luck-variance-band -F "$SCRATCH/v175-13-merge-msg.txt"
git -C $R log --oneline -3
```

Expected: a merge commit on `main`. No full suite after this merge (CLAUDE.md).

- [ ] **Step 4: Release the bot line (minor)**

Read the current values from disk (never from this plan), bump `bot` by one minor and stamp it:

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
```

Expected: only `bot` and `bot_updated` change. Write `$SCRATCH/v175-13-bot-release.txt` and `$SCRATCH/v175-13-bot-chore.txt`, identical except the first word (`release(bot):` / `chore(bot):`), replacing `<bot version>` with the printed value:

```text
release(bot): <bot version> -- book-status message when the losing-run zone rises, variance-band API (v175)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R add VERSION.json
git -C $R commit -F "$SCRATCH/v175-13-bot-release.txt"
python $R/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -F "$SCRATCH/v175-13-bot-chore.txt"
```

- [ ] **Step 5: Release the ui line (minor)**

The same with `ui`/`ui_updated`:

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

Write `$SCRATCH/v175-13-ui-release.txt` and `$SCRATCH/v175-13-ui-chore.txt` (`release(ui):` / `chore(ui):`):

```text
release(ui): <ui version> -- Normal bad luck panel on Analytics -> Overview: losing-run and 50-day drawdown bands, whole book (v175)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R add VERSION.json
git -C $R commit -F "$SCRATCH/v175-13-ui-release.txt"
python $R/scripts/dev/build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -F "$SCRATCH/v175-13-ui-chore.txt"
python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
```

Expected: only the `ui` lines change in the diff; the version-matrix test passes (the one check the pre-bump suite cannot make).

- [ ] **Step 6: Push**

```bash
git -C $R push origin main
gh run list --branch main --limit 1
```

Expected: the push is accepted and a workflow run for the new `main` head is listed (V175-14 watches it). A rejected push (another session pushed first) is resolved by `git -C $R pull --no-rebase origin main` and a re-push, never by force.

- [ ] **Step 7: Commit**

The commits of Steps 3-5 are this task's commits (merge, `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)`). `git -C $R status --short` shows nothing from this task.

### Task V175-14: Deploy; check the band and the hook against the live book

**Model:** sonnet — reads production output and judges it.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md` (`## Progress`, on `main`)
- Create (session scratchpad only): `$SCRATCH/v175-live-band.py`
- VM: read-only. Any live fix is mirrored into this repo and committed on `main` before the task counts as done (`mirror-prod`).

**Interfaces:**
- Consumes: V175-13's pushed `main`; V175-3's `variance_band(closed) -> Band`; V175-7's `ZONE_JOB = "variance_band:zone"` and swallowed tag `scan.book_status`; V175-5's route; existing `scheduled_repo().fired_on(job) -> str | None` (`swingbot/core/db/repositories/scheduled.py:12`), `TradeLog().get_trades(status=None, limit=None, ledger=None)` (`performance.py:1204`), `scope.closed_only`.
- Produces: the live band summary (N, window, source) recorded in the index's `## Progress`.

**Pooled figures.** Every ExpR, N or window written in this task's report or in § Progress is re-derived here from the live production book and stated with its N, window and source (`pooled-numbers` skill: invoke it before writing any of them). A replica or fixture figure is never quoted as the book's.

- [ ] **Step 1: Watch the deploy**

```bash
gh run list --branch main --limit 1
gh run watch <run id from the line above> --exit-status
```

Expected: every suite job, the frontend "Unit tests" and "Production build", and the deploy job succeed. A red job is fixed on `main` as its own scoped commit and pushed again; never re-run blindly.

- [ ] **Step 2: Compute the band on the VM from the live book**

Write `$SCRATCH/v175-live-band.py`:

```python
"""v175 deploy check: the band over the live closed book, as the API computes it."""
import json
import time

from swingbot.core.analytics.scope import closed_only
from swingbot.core.analytics.variance_band import variance_band
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking.performance import TradeLog

closed = closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])
started = time.perf_counter()
band = variance_band(closed)
seconds = round(time.perf_counter() - started, 2)
summary = {key: band.get(key) for key in ("status", "scope", "asof", "days", "weeks", "pool", "composition", "current", "expr")}
summary["horizons"] = [{"horizon": h["horizon"], "weeks_span": h["weeks_span"], "run": h["run"], "drawdown": h["drawdown"]}
                       for h in band.get("horizons", [])]
summary["dollars"] = band.get("dollars", "omitted")
summary["closed_trades"] = len(closed)
summary["seconds"] = seconds
summary["stored_zone"] = scheduled_repo().fired_on("variance_band:zone")
print(json.dumps(summary, indent=2, default=str))
```

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCH/v175-live-band.py"
```

Expected: `scope` `whole_book`; `status` `ok` or `insufficient` (with `days`/`weeks` showing why); for `ok`: two horizons (20, 50), `p80 <= p95` and `p95_lo <= p95 <= p95_hi` in each, `current.zone` the worse of `run_zone` and `drawdown_zone`, `expr.n` equal to the number of pool trades with a computable R, `seconds` well under 5. `stored_zone` is `None` until the first scan tick after the deploy, then a zone string.

- [ ] **Step 3: Check the scan hook after one scan tick**

During a scan session, after at least one `SCAN_INTERVAL_MINUTES` tick since the deploy:

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 40m bot 2>&1 | grep -iE 'book_status|variance|Traceback' | tail -20"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCH/v175-live-band.py"
```

Expected: no traceback and no `scan.book_status` swallow line. Then, by the live zone:
- `insufficient`: `stored_zone` stays `None` and nothing posted.
- `normal`: `stored_zone` is `None` (nothing to store on a non-rise from the default) or `normal`, nothing posted.
- `rough` / `outside`: `stored_zone` equals the zone and exactly one `📉 BOOK STATUS` message is in the alerts channel (the first tick rose from the default `normal`; this is the designed behaviour, not noise). Ask the partner to confirm the message is there and reads as the spec's line (`AskUserQuestion`, one question). Later ticks at the same zone post nothing.
If the hook did nothing when it should have, report it with the log lines; do not patch production by hand.

- [ ] **Step 4: Check the API answers the same band**

```bash
node $R/frontend/scripts/browse.mjs api --path "api/v1/analytics/variance-band"
node $R/frontend/scripts/browse.mjs api --path "api/v1/analytics/variance-band?ledger=main"
```

(`browse.mjs` signs in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, kept in its own process.) Expected: the first body has the same `status`, `asof`, `days`, `weeks`, `current` and `horizons` as Step 2 (the bootstrap is seeded; a trade closing in between changes them, so re-run Step 2 once before calling a difference a defect); the second is a 400 with `unknown parameter 'ledger'; allowed: []`.

- [ ] **Step 5: Look at the panel on production at three widths**

```bash
node $R/frontend/scripts/browse.mjs shots --out "$SCRATCH/v175-prod" --path "app/analytics?tab=overview" --widths 1280,768,390
```

Open the three `*.png` files with the Read tool and check each `*.txt`: `page-scroll-x: 0` at every width; the "Normal bad luck" panel spans the tab; at 390 the two bars stack and every line wraps; the text shows the header, both bar labels, the zone copy, the `now:` lines, the ExpR line with N and window, the composition line and the caption (or the insufficient line). If V175-11's local check could not run, this step is that check; record the measurements by eye in the task report.

- [ ] **Step 6: Record the live band in the index**

Invoke the `pooled-numbers` skill, then add one line under the index's `## Progress` block on `main` (`$R/docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md`):

```markdown
Live check <YYYY-MM-DD> (production book via `ssh-hetzner.sh`, `variance_band` over every ledger's closed trades): status <ok|insufficient>, <days> close days over <weeks> weeks, pool <v2|all>; 50-day p95 run <p95> (<lo>–<hi>), p95 drawdown <p95>R; now run <k>, drawdown <dd>R, zone <zone>; ExpR <value> (N=<n>, <start> to <end>, CI <lo>..<hi>, not_positive <bool>); computed in <seconds> s; stored zone after one tick: <zone|None>.
```

filled from Step 3's output.

Write `$SCRATCH/v175-14-msg.txt`:

```text
docs(v175): record the live variance-band check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R add docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md
git -C $R commit -F "$SCRATCH/v175-14-msg.txt"
git -C $R status --short
```

Expected: one docs commit on `main`. A live fix made on the VM (none is planned) would be its own `fix(<area>): ... (v175, mirrored from production)` commit on `main` before this one.

### Task V175-15: Close-out: move plan and spec to `implemented/`, remove worktree

**Model:** haiku — the close-out checklist.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md` (`## Progress`), then `git mv` every `docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_*.md` (`_0-index`, `_1-core-band`, `_2-api-message`, `_3-panel-release`, `_3b-release`) into `docs/superpowers/plans/implemented/`
- Move: `docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md` → `docs/superpowers/specs/implemented/`

**Interfaces:**
- Consumes: V175-12's recorded counts, V175-13's panel result and release commits, V175-14's live check line.
- Produces: nothing; the plan leaves the live set and the SessionStart `PLAN WIP` line stops naming it.

- [ ] **Step 1: Run the `close-out` skill, with two of its steps already done**

Invoke `/close-out`. Its panel step ran in V175-13 Step 1 and its bump and regeneration steps ran in V175-13 Steps 4-5: confirm both from the log rather than repeating them:

```bash
git -C $R log --oneline -8 -- VERSION.json swingbot/admin/version_history.json
python -c "import json; print(json.load(open(r'E:/Documents/Private/Projects/Discord-Bot/VERSION.json')))"
```

Expected: `release(bot)`, `chore(bot)`, `release(ui)`, `chore(ui)` commits naming v175, and both lines one minor above their values before V175-13. Do not bump again. The header said `Bump: bot minor; ui minor` and `Edge: none (integrity)`; both held, so nothing is amended (if one did not, amend the header and say why in one clause in Step 4's commit).

- [ ] **Step 2: Record the results in the index**

Replace the `## Progress` block's opening `Not started. ...` line in `$R/docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md` (keep V175-4's calibration rates and V175-14's live line below it) with:

```markdown
Done <YYYY-MM-DD>. V175-1..V175-15 complete. Full suite (V175-12): Python <passed> passed, <skipped> skipped, 0 failed, 0 xfailed; Vitest <n> passed; production build green. Panel (V175-13): <n> BLOCKING resolved, <n> ADVISORY (<applied>/<recorded>). Released bot <version>, ui <version>. Three-width check: local (V175-11) <ran|could not run: reason>, production (V175-14) page-scroll-x 0 at 1280/768/390.
```

filled from the task reports.

- [ ] **Step 3: Remove the worktree and its branch**

The branch name contains no `backup` and is not `stable-*`. Check it is fully merged first; non-zero means stop and ask the partner:

```bash
git -C $R rev-list --count main..2026-10-18-v175-normal-bad-luck-variance-band
git -C $R worktree remove .claude/worktrees/2026-10-18-v175-normal-bad-luck-variance-band
git -C $R branch -d 2026-10-18-v175-normal-bad-luck-variance-band
git -C $R worktree list
```

Expected: `0`; the worktree and branch are gone (`branch -d`, never `-D`); `worktree list` no longer shows it. A `worktree remove` that refuses because of untracked files means something was left uncommitted: look at it before deciding, never `--force` by default.

- [ ] **Step 4: Move the documents and commit on `main`**

```bash
ls $R/docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_*.md
for f in $R/docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_*.md; do git -C $R mv "$f" $R/docs/superpowers/plans/implemented/; done
git -C $R mv docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md docs/superpowers/specs/implemented/
git -C $R add docs/superpowers/plans/implemented/2026-10-18-v175-normal-bad-luck-variance-band_0-index.md
```

Write `$SCRATCH/v175-15-msg.txt`:

```text
docs(v175): close out -- plan and spec to implemented/, results recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $R commit -F "$SCRATCH/v175-15-msg.txt"
git -C $R status --short
git -C $R push origin main
```

Expected: the `ls` lists exactly the five files named under **Files** (a missing or extra file is checked before moving); one commit that moves the plan files and the spec and carries the index's Progress edit from Step 2; `git status` clean for these paths; no full suite after this (CLAUDE.md: it ran once, in V175-12).
