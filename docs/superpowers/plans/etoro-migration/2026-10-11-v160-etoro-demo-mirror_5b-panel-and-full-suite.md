# v160 eToro demo mirror: plan events become demo-account trades. Part 5b: panel and full suite (EM15–EM16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task EM15" -A 300 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Panel review, § Testing ("Every new function stays below cyclomatic complexity 15"), § Parallelisation ("Final: the full suite, once"))
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here. This file continues part 5 (`..._5-ops-scripts-and-gate.md`, EM13–EM14); it is split off only to keep each file under 1500 lines.

**Conventions:** `WT` is the worktree root, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror`. Never `cd`: use `git -C "$WT" ...` and absolute paths. Both tasks run strictly last, one at a time: EM15 after every task EM1–EM14 is committed on the branch, EM16 after EM15.

# Phase 7 — gate (EM15–EM16)

### Task EM15: Complexity sweep and pre-close-out `/panel`

**Model:** sonnet — a mechanical sweep with exact commands, a two-file wording change with its exact text, and applying panel findings that each cite a `file:line`; any finding that would redesign beyond the spec goes to the partner, not into code.

Spec § Testing ("Every new function stays below cyclomatic complexity 15"), header `**Panel:**` and the note under it (line 11: the seat set changes once v159 lands). CLAUDE.md § "From v146 ... `/panel` runs them ... before close-out". Part 4's EM10 Step 8 hands this task one more item: `CLAUDE.md` and `AGENTS.md` still say the eToro keys are "unused so far", which is false once the mirror reads them; both files change in **one commit** (AGENTS.md is the condensed Codex mirror, `tests/hooks/test_codex_mirror.py` guards it) and `CLAUDE.md` stays under 200 lines.

**Who runs which step.** Steps 1–4 are mechanical and run in a `task-implementer` (sonnet). Steps 5–7 dispatch the `expert-reviewer` agent once per role, serially, through the `panel` skill; a subagent cannot dispatch agents, so **the controller runs Steps 5–7 itself** (and hands each accepted code finding back to a `task-implementer` at this task's tier). The implementer stops after Step 4 and reports `EM15 STEPS 1-4 DONE` with the two commit hashes.

**Files:**
- Modify: `CLAUDE.md` (§ eToro roadmap, the keys sentence)
- Modify: `AGENTS.md` (the eToro paragraph, the keys sentence)
- Modify: `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md` (`## Progress`, the worktree copy)
- Modify: every file a panel finding cites, with its test (Step 6); a stale "unused"/"not read" sentence the Step 3 sweep finds, in its file

**Interfaces:**
- Consumes: every artefact of EM1–EM14 on the branch; the spec's `**Panel:**` line; the `panel` skill (`.claude/skills/panel/SKILL.md`: roles from the spec's Panel line, target a git range, serial dispatch, merged list `BLOCKING` first); `docs/claude/skills-tools.md` § Expert roles (the roster each role must be in).
- Produces: commits on the branch; the merged findings under `### Pre-close-out panel (EM15)` in the index's `## Progress`. EM16 consumes only "EM15 committed, tree clean".

- [ ] **Step 1: Confirm EM1–EM14 are committed and the tree is clean**

```bash
for n in $(seq 1 14); do git -C "$WT" log --format=%s main..HEAD | grep -q "EM$n --" || echo "missing EM$n"; done
git -C "$WT" status --porcelain
```

Expected: no output from either. A `missing EMn` line: check `git -C "$WT" log --oneline main..HEAD` by eye (a task may have used another subject wording); if the task's files are really absent, stop with `BLOCKED: EM15 needs EMn`. Uncommitted changes: stop and report them; never commit someone else's work from here.

- [ ] **Step 2: Complexity sweep over every Python file the branch adds or changes**

```bash
python - "$WT" <<'EOF'
"""Every function the branch adds is < 15; a legacy function >= 15 is no worse than on main."""
import json, subprocess, sys, tempfile
from pathlib import Path

wt = sys.argv[1]
names = subprocess.run(["git", "-C", wt, "diff", "--name-only", "--diff-filter=AM",
                        "main...HEAD", "--", "*.py"],
                       capture_output=True, text=True, check=True).stdout.split()


def blocks(path):
    raw = subprocess.run([sys.executable, "-m", "radon", "cc", "-j", path],
                         capture_output=True, text=True, check=True).stdout
    out = {}
    for items in json.loads(raw).values():
        for item in items if isinstance(items, list) else []:
            for block in [item, *item.get("methods", [])]:
                name = f"{block.get('classname') + '.' if block.get('classname') else ''}{block['name']}"
                out[name] = max(out.get(name, 0), block["complexity"])
    return out


bad = []
for rel in names:
    new = blocks(str(Path(wt) / rel))
    shown = subprocess.run(["git", "-C", wt, "show", f"main:{rel}"], capture_output=True, text=True)
    old = {}
    if shown.returncode == 0:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(shown.stdout)
        old = blocks(tmp.name)
    for name, cc in new.items():
        if cc >= 15 and cc > old.get(name, 0) and not (name in old and old[name] >= 15 and cc <= old[name]):
            bad.append(f"{rel}:{name} CC {cc} (main: {old.get(name, 'new')})")
print("\n".join(bad) or f"OK: {len(names)} files, every new or changed function < 15, no legacy one worse")
EOF
```

Expected: `OK: <n> files, ...`. Each other line names a function to split into named helpers **without changing behaviour** (`docs/claude/code-complexity.md`): split it, re-run that file's narrow tests (`python "$WT/scripts/dev/testrun.py" file <its test>`), re-run this sweep, and commit per function: `refactor(v160): EM15 -- split <function> below complexity 15`. Also confirm `trade_monitor` is still the grade EM10 recorded: `python -m radon cc -s "$WT/swingbot/commands/scanning/loops.py" | grep trade_monitor` prints `C (13)` (or EM10's recorded number).

- [ ] **Step 3: Sweep for wording the mirror made false**

```bash
git -C "$WT" grep -n -i "unused so far\|nothing reads these yet\|no code reads it yet\|nothing consumes them yet\|nothing reads them yet\|until the eToro paper integration is built" -- CLAUDE.md AGENTS.md swingbot .env.example docs/claude
git -C "$WT" grep -n "pre_open" -- docs/claude/architecture.md docs/claude/etoro-roadmap.md swingbot/core/broker
```

Expected before Step 4: the first command prints exactly the `CLAUDE.md` and `AGENTS.md` lines Step 4 rewrites (CLAUDE.md wraps it as `unused` / `so far.`, so its hit may be the second line only). Any other hit (a `config.py` help text, an `.env.example` comment, a `docs/claude` sentence) says the keys are unread: rewrite it in place to say the v160 demo mirror reads them (only when `ETORO_MIRROR_ENABLED` is on), and commit it with Step 4's commit if it is under `docs/claude`, else on its own (`docs(v160): EM15 -- <file>: the mirror reads the eToro keys`), after its file's narrow test (`tests/infra/test_config_etoro.py`, `tests/infra/test_env_example_sync.py`). The second command prints nothing (index § Global Constraints: there is no `pre_open.py`); a hit is rewritten to `checks.py`.

- [ ] **Step 4: Rewrite the keys sentence in `CLAUDE.md` and `AGENTS.md`, one commit**

In `CLAUDE.md` (§ eToro roadmap), replace

```
`.env` (`ETORO_USER_KEY`, `ETORO_API_KEY`, section "eToro Paper Trading"), unused
so far. Skill: `etoro-public-api-operations`. Detail: `docs/claude/etoro-roadmap.md`.
```

with (same two lines, so the line count does not move)

```
`.env` (`ETORO_USER_KEY`, `ETORO_API_KEY`, section "eToro Paper Trading"), read
only by the v160 demo mirror. Skill: `etoro-public-api-operations`. Detail: `docs/claude/etoro-roadmap.md`.
```

In `AGENTS.md`, replace

```
`ETORO_USER_KEY` / `ETORO_API_KEY` in `.env`, unused so far. Detail:
```

with

```
`ETORO_USER_KEY` / `ETORO_API_KEY` in `.env`, read only by the v160 demo mirror. Detail:
```

If v159 reworded either paragraph so the old text is not there verbatim, replace whichever phrase says the keys are unused or unread with `read only by the v160 demo mirror`, keep the rest of v159's wording, and keep `CLAUDE.md`'s line count unchanged.

```bash
wc -l "$WT/CLAUDE.md"
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
git -C "$WT" grep -n "unused so far" -- CLAUDE.md AGENTS.md
```

Expected: `CLAUDE.md` under 200 lines (198 on 2026-10-14; it must not grow here); the mirror test `0 failed`; the grep prints nothing.

```bash
git -C "$WT" add CLAUDE.md AGENTS.md
git -C "$WT" commit -m "docs(v160): EM15 -- the eToro keys are read by the demo mirror

CLAUDE.md and its condensed Codex mirror AGENTS.md said the eToro keys were
unused; the v160 demo mirror reads them (only while ETORO_MIRROR_ENABLED is
on). Same line count in CLAUDE.md.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

The implementer stops here and reports `EM15 STEPS 1-4 DONE` with the commit hashes. Steps 5–7 are the controller's.

- [ ] **Step 5: Run the pre-close-out panel (controller)**

Resolve the roles:

```bash
git -C "$WT" show main:docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md | grep -n "^\*\*Panel:\*\*"
test -e "$WT/.claude/skills/execution-specialist/SKILL.md" && echo SEAT-EXISTS || echo no-seat
```

The roles are the spec's `**Panel:**` line (`staff-engineer, quant-engineer, risk-manager` as written on 2026-10-11). Spec line 11: once v159 has landed (`SEAT-EXISTS`), the line should read `execution-specialist, risk-manager, staff-engineer`; if it still lacks `execution-specialist`, run that v159 set, and tell the partner the spec line on `main` is stale (the spec is amended on `main`, never from this worktree). Every role must be a row of `docs/claude/skills-tools.md` § Expert roles; an unknown role stops the panel (the skill's rule), never a near-match substitute.

Invoke the `panel` skill with the roles (comma-separated, no spaces) and the target range `main...2026-10-11-v160-etoro-demo-mirror`, for example `/panel staff-engineer,quant-engineer,risk-manager main...2026-10-11-v160-etoro-demo-mirror`. It dispatches `expert-reviewer` once per role, **serially**, and returns one merged list, `BLOCKING` first, each finding citing a `file:line`, range or doc section.

- [ ] **Step 6: Apply the findings (controller dispatches, implementer at sonnet)**

For each finding, in the merged order:

- **BLOCKING, inside the spec:** fix it in the cited file with a test that fails before the fix (same TDD cycle as the task that wrote the file), run that file's narrow test plus any test file of the module it touches (`python "$WT/scripts/dev/testrun.py" file <test>`; a DB test must run, not skip), re-run the Step 2 sweep if a function changed, and commit one finding per commit: `fix(v160): EM15 -- <role>: <one line>`.
- **ADVISORY, inside the spec:** apply it the same way, or reject it with a one-line reason.
- **Any finding that would change the spec's design** (a new setting, a new skip reason, real-account anything, a different order type, scope the spec's § Out of scope excludes): do not implement. Ask the partner with `AskUserQuestion` (one question, recommended option first); a BLOCKING one the partner declines is recorded as `rejected: <why>` in `.superpowers/sdd/progress.md` as well as in the index (the `panel` skill's rule; an unresolved BLOCKING finding stops `/close-out`).

Never touch `ETORO_ALLOW_REAL`/`ETORO_REAL_SIGNOFF` or any `.env*` value while applying a finding (index § Global Constraints).

- [ ] **Step 7: Record the panel in the index and commit (controller)**

In `$WT/docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`, under `## Progress` (after whatever the earlier phases wrote there), append:

```markdown
### Pre-close-out panel (EM15)

Run <YYYY-MM-DD> on `main...2026-10-11-v160-etoro-demo-mirror` at <short sha>: <roles>.

- BLOCKING <role>: <one line> -- applied (<commit short sha>)
- ADVISORY <role>: <one line> -- applied (<sha>) | rejected: <why>
- <role>: CLEAN

Complexity sweep: <n> Python files, every new or changed function < 15, no legacy function worse.
CLAUDE.md / AGENTS.md: the eToro keys sentence now names the demo mirror (<sha>).
```

One line per surviving finding, every role listed (a `CLEAN` role is listed, not omitted).

```bash
git -C "$WT" add docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md
git -C "$WT" commit -m "docs(v160): EM15 -- record the pre-close-out panel

Merged findings of the pre-close-out panel and the complexity sweep, in the
index's Progress block.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C "$WT" status --porcelain
```

Expected: the commit succeeds and `status --porcelain` prints nothing. If `.superpowers/sdd/progress.md` gained a `rejected:` line in Step 6, add it to this commit.

### Task EM16: Full suite

**Model:** haiku — run one command through the `test-runner` agent and read a one-line verdict; a failure is fixed by escalating per `docs/claude/model-routing.md`, not inside this task.

Spec § Parallelisation ("Final: the full suite, once"); CLAUDE.md § Commands ("Green means `0 failed` and `0 xfailed`"; "A failed test is fixed and re-run alone ... never by re-running the whole suite"; "No full suite after merging back to `main`"). Index § Global Constraints (the full suite runs once, here; DB tests must run, not skip). The bump (`bot minor`) is **not** this task's: the controller applies it at `/close-out` after this task is green.

**Files:**
- None. A failing test is fixed in the file the failure names, under the task that owns that file (Step 4).

**Interfaces:**
- Consumes: EM15 committed and the worktree clean.
- Produces: the suite's one-line verdict, reported to the controller for `/close-out`.

- [ ] **Step 1: Confirm EM15 is committed and the tree is clean**

```bash
git -C "$WT" log --format=%s main..HEAD | grep -c "EM15 --"
git -C "$WT" status --porcelain
```

Expected: a count of at least 2 (EM15's Step 4 and Step 7 commits), and no output from `status`. Otherwise stop with `BLOCKED: EM16 needs EM15`.

- [ ] **Step 2: Prove the db-test Postgres is up**

```bash
python "$WT/scripts/dev/testrun.py" file tests/db/test_migrations.py
```

Expected: `0 failed` and **0 skipped**. A skip means db-test is down: its skip message prints the start command; run it, then repeat this step. Never start the full suite with db-test down: every repository and migration test would skip and the run would look green without testing `broker_orders`.

- [ ] **Step 3: Run the full suite once, through the `test-runner` agent**

Dispatch the `test-runner` subagent (so none of the ~1150 progress lines reach this context) with exactly:

```bash
python "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror/scripts/dev/testrun.py" full
```

Expected: a one-line verdict with `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Check the skip count against the verdict main reported most recently (`tail -n 40 .superpowers/sdd/progress.md` or the controller's last full run): a jump of more than the handful of known environment skips means db-test dropped mid-run; restart it and re-run **only** the skipped files with `testrun.py file`.

- [ ] **Step 4: If anything failed, fix it and re-run that test alone**

For each failure the verdict names:

1. Re-run it alone to confirm it is real: `python -m pytest "$WT/<path>::<test>" -v`.
2. Find the task that owns the file (index § Task ledger) and fix it there, with the TDD cycle of that task; escalate the model per `docs/claude/model-routing.md` (haiku → sonnet → opus) if the cause is not obvious.
3. Re-run **that file only**: `python "$WT/scripts/dev/testrun.py" file <path>`. Never re-run the whole suite for one fix.
4. Commit one fix per commit:

```bash
git -C "$WT" add <the files the fix touched>
git -C "$WT" commit -m "fix(v160): EM16 -- <test name>: <one-line cause>

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

A failure in a file v160 never touched, which also fails on `main`, is not v160's: record it for the controller with its node id and the `main` evidence, do not fix it on this branch.

- [ ] **Step 5: Report the verdict**

Report to the controller: the verdict line from Step 3, any Step 4 fix commits (hash + test), and `git -C "$WT" log --oneline main..HEAD | wc -l`. Nothing is committed here when the suite was green first time. The controller then runs `/close-out` (bump `bot minor`, regenerate `version_history.json`, move the plan to `implemented/`, merge, remove the worktree); no full suite runs after the merge to `main`.
