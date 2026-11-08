---
name: gate
description: "Pre-push gate -- CPU check, syntax pass, complexity gate, diff-selected tests, frontend specs when frontend/ changed, scoped commits, then push and watch the CI run until it is green."
---
<!-- GENERATED from .claude/skills/gate/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Pre-push gate

Green means **`0 failed`** and **`0 xfailed`**, nothing subtler. A changed
pass count is not a failure; a new `xfailed` is a quarantine someone added, so
find out why.

This gate never runs the whole suite locally: the CI pipeline runs it on every
push (root `CLAUDE.md`: no plan or merge runs the full suite locally). The gate
runs what reaches the diff, commits in scoped pieces, pushes, then watches CI
until it is green. Paste the verdict line of every step; a step with no pasted
line did not run.

## Step 1 — Do not fight another session for the CPU

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object CPU -gt 300 |
  Select-Object Id, StartTime, CPU
```

A hit means a multi-hour walk-forward run is live. Wait, or run only the
touched file. Contention does not change counts, but it wrecks timings.

## Step 2 — Syntax pass

No `make` on Windows:

```powershell
python -m py_compile bot.py admin_ui.py
python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('swingbot', quiet=2) else 1)"
```

## Step 3 — Complexity gate

```bash
python scripts/dev/complexity_gate.py
```

Every function the diff wrote or changed stays under the limit in
`docs/claude/code-complexity.md`, and a legacy function already over it got no
worse. A new offender is a FAIL: split it into named helpers. `--update` only
ever shrinks the baseline; never use it to admit a new offender.

## Step 4 — Diff-selected tests

```bash
python scripts/dev/testrun.py changed
```

`changed` runs the tests that reach the diff and widens when unsure
(`--dry-run` prints the selection). While iterating on one file use
`python scripts/dev/testrun.py file <test>`. Output is parked in
`.pytest-last-run.log`; stdout is one verdict line:

- `VERDICT: PASS` — proceed.
- `VERDICT: FAIL` — yours. Fix it and re-run that test alone
  (`testrun.py file <test>` or `pytest <path>::<test>`); load
  `superpowers:systematic-debugging` before proposing a fix.
- `VERDICT: UNKNOWN` — the output could not be parsed: a tooling problem,
  **never** a success.

Never run bare `pytest` for a gate (`pytest.ini` sets `-q`, which prints no
summary counts line), and never `testrun.py full` here: that run is CI's.

## Step 5 — Frontend specs, when `frontend/` changed

Skip this step when `git diff --name-only` lists nothing under `frontend/`.
Otherwise run the spec of every changed component. The wrapper runs
`ng test --watch=false` from `frontend/` without a `cd`, which the repo hooks
forbid:

```bash
node frontend/scripts/ng-test.mjs frontend --include <spec path under frontend/>
```

A worker start timeout under load is cured by one re-run
(`docs/claude/testing-cost.md`).

## Step 6 — Stage narrowly, commit in scoped pieces

Concurrent sessions share this tree, and uncommitted generated state has been
silently wiped before.

```bash
git add <explicit paths>      # never git add -A
```

Several scoped commits, never one large one: each carries one meaningful
change with its own tests (`docs/claude/working-conventions.md`). Commit
generated artifacts (especially `validation_registry.json`) at once, and a
skill, agent or `docs/claude/` change ships its Codex mirror
(`python scripts/dev/sync_codex.py`) in the same commit.

## Step 7 — Push, then watch CI until green

CI runs only on pushes to `main`, so on a worktree branch the push starts no
run: stop after the push and watch after the merge. On `main`, push, then
follow the run it started
(`docs/claude/working-conventions.md` § Pipeline watch):

```bash
git push
gh run list --branch <branch> --limit 1 --json databaseId,status,conclusion
gh run watch <id> --exit-status
```

Red: `gh run view <id> --log-failed`, fix each failing test, re-run it alone,
commit scoped, push, and watch the new run; repeat until green. A deploy-job
failure touches production (rollback: `docs/deploy/DEPLOY_HETZNER.md`): stop
and tell the partner. Never state PASS
without pasting the run's conclusion.
