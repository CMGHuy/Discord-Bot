# v145 Expert role skills, review panels and per-task model routing: Implementation Plan, part 3 — documentation and verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Header, global constraints, file map and parallelisation: `2026-10-09-v145-expert-roles-model-routing_0-index.md`.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`](../specs/2026-10-09-v145-expert-roles-model-routing.md)

# Phase 4 — Documentation

### Task V145-8: Close-out panel gate, escalation ladder in skills-tools, persona pointer, CLAUDE.md rule

**Model:** haiku — doc and skill-text edits whose every line is given verbatim; two small assertions pin them.

**Files:**
- Modify: `.claude/skills/close-out/SKILL.md` (new Step 2, later steps renumbered; full replacement given)
- Modify: `docs/claude/skills-tools.md` (`## Which agent for what (v107)`: two table rows and the plan-loop paragraph)
- Modify: `docs/claude/persona.md` (one paragraph after the "raises the bar" paragraph)
- Modify: `CLAUDE.md` (one paragraph in `## Naming specs and plans`; one row in `## Reference docs`)
- Modify: `AGENTS.md` (persona section; role-agents paragraph)
- Modify: `tests/hooks/test_role_skills.py` (two tests appended)
- Generated: `.agents/skills/close-out/SKILL.md`

**Interfaces:**
- Consumes: `/panel` (V145-5), `**Panel:**` rules (V145-6), `docs/claude/model-routing.md` (V145-7), `expert-reviewer` (V145-4), the roles table (V145-1..3), `_body` and `_text` and `SKILLS_TOOLS` in `tests/hooks/test_role_skills.py` (V145-1).
- Produces: the final close-out ritual (Step 2 "Clear the panel" stops on an unresolved `BLOCKING` finding); `skills-tools.md` without the "fails review twice" rule.

- [ ] **Step 1: Write the failing tests**

Append to `tests/hooks/test_role_skills.py`:

```python
def test_close_out_stops_on_an_unresolved_blocking_finding():
    body = _body("close-out")
    missing = [p for p in ("/panel", "**Panel:**", "BLOCKING", "main...<branch>")
               if p not in body]
    assert not missing, missing


def test_the_escalation_ladder_replaced_fails_review_twice():
    text = _text(SKILLS_TOOLS)
    assert "fails review twice" not in text
    assert "model-routing.md" in text and "one tier up" in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`
Expected: FAIL — both new tests (close-out has no `/panel`; `skills-tools.md` still says "fails review twice").

- [ ] **Step 3: Add the panel gate to close-out**

Replace the whole of `.claude/skills/close-out/SKILL.md` with exactly the text below (69 lines). The changes against the current file are: a new `## Step 2 — Clear the panel`; old Steps 2–6 become 3–7 with their cross-references renumbered (old "Step 3"/"Step 4"/"Step 5" become "Step 4"/"Step 5"/"Step 6"); the gate gains its first clause.

```markdown
---
name: close-out
description: The plan close-out ritual -- resolve the version bump from VERSION.json, regenerate version_history.json, move the plan document to implemented/ or no-lift/, and remove its worktree. Run as /close-out, or by Claude itself once a plan's final task (the full-suite run) is green and its results are recorded.
---

# Plan close-out

## Step 1 — Read the authority

`docs/claude/document-lifecycle.md` and `docs/claude/working-conventions.md`.
This skill is the checklist; the reasoning behind every step below lives
there, not here.

## Step 2 — Clear the panel

If the plan's spec carries a `**Panel:**` line, run `/panel` with those
roles over the plan's full diff (`main...<branch>`, or `<merge>^1...<branch>`
once merged) and its recorded results. An unresolved `BLOCKING` finding stops
the close-out here. A spec with no `**Panel:**` line (v145 and earlier) skips
this step.

## Step 3 — Resolve the bump from disk

Read `VERSION.json` — never a plan header, never memory, never an earlier
task's note. Increment only the line named by the plan's `Bump:`; leave the
other line untouched. `Bump: none` means no release commit at all — Step 4
(the version-bump mechanics) does not apply, but proceed to Step 5 anyway:
`Bump: none` is itself a prediction that Step 5 must check, not a reason to
skip it.

## Step 4 — Stamp, commit, then regenerate

Set that line's `*_updated` stamp to now, in the existing format, and commit
`VERSION.json` alone: `release(<line>): <version> -- <summary>`. Then run
`python scripts/dev/build_version_matrix.py` and commit the regenerated
`swingbot/admin/version_history.json` as its own next commit:
`chore(<line>): <version> -- <summary>` (the release commit's own summary,
not "regenerate version_history.json for X"). Two commits, bump then
regenerate, in that order — never combined, never reordered. The local gate
runs before the bump, so nothing else catches a missed regeneration.

## Step 5 — Amend a wrong prediction, do not hide it

If the plan predicted a level or an `Edge:` the work did not deliver, amend
the header and say why in one clause — fold it into Step 4's commit if that
ran, otherwise into Step 6's move commit.

## Step 6 — Move the document

`git mv` the plan — and any spec it was built from, if nothing else live
still builds from it — into `implemented/` for work that reached `main`, or
`no-lift/` for a plan whose code deliberately did not.

## Step 7 — Remove the worktree, unless this closed to `no-lift/`

For an `implemented/` close: remove the worktree and its branch, per
`document-lifecycle.md`'s naming. Never delete a branch containing `backup`
— `guardrails.py` denies it, and that deny is correct.

For a `no-lift/` close: leave the worktree and branch in place. They are the
only copy of that unmerged work; deleting them is the human partner's call,
not a default step here.

## The gate

No unresolved `BLOCKING` panel finding; `VERSION.json`, the regenerated
history and the moved plan are all in the log; the worktree is gone for an
`implemented/` close, or deliberately kept for a `no-lift/` one; no full-suite
run happens after a clean merge.
```

- [ ] **Step 4: Replace the escalation rule in `docs/claude/skills-tools.md`**

In `## Which agent for what (v107)`, replace the row

```markdown
| Implement one plan task from `/task-brief` | `task-implementer` | sonnet |
```

with

```markdown
| Implement one plan task from `/task-brief` | `task-implementer` | the task's `**Model:**` tier (default sonnet) |
```

insert directly below the `task-reviewer` row:

```markdown
| Review a spec, plan, diff or result through one expert role (via `/panel`) | `expert-reviewer` | the role's model from § Expert roles |
```

and replace the paragraph

```markdown
Plan loop: `/task-brief` → `task-implementer` → `task-reviewer` → Opus reads
findings → fix via `SendMessage` to the same implementer, or next task. A task
that fails review twice is implemented by Opus directly. Brainstorming never
goes to an agent — it needs the partner. `/gate` and `/task-brief` run forked
on sonnet, so their tool output never reaches the Opus context.
```

with

```markdown
Plan loop: `/task-brief` → `task-implementer`, dispatched with the task's
`**Model:**` tier as the `model` override (plans above v145; default sonnet)
→ `task-reviewer` (always sonnet) → Opus reads findings → next task, or the
escalation ladder in `model-routing.md`: `SendMessage` the same implementer
once, then a fresh implementer one tier up with the findings attached, then
Opus inline, each step logged in `.superpowers/sdd/progress.md`.
Brainstorming never goes to an agent — it needs the partner. `/gate` and
`/task-brief` run forked on sonnet, so their tool output never reaches the
Opus context.
```

- [ ] **Step 5: Point persona.md at the role skills**

In `docs/claude/persona.md`, insert directly after the paragraph ending `Where this section appears to conflict with any rule below it, the rule wins.` (one blank line before and after):

```markdown
**One seat at a time (v145).** The four seats above stay blended in the main
session. When a spec, plan, diff or result needs one lens's separately
reasoned critique, nine role skills hold it — `quant-researcher`,
`staff-engineer`, `veteran-trader`, `risk-manager`, `financial-advisor`,
`technical-analyst`, `fundamental-analyst`, `quant-engineer`,
`senior-engineer` — applied by the `expert-reviewer` agent and run as a panel
by `/panel` (`skills-tools.md` § Expert roles). A role raises findings; it
never decides, and the bar-not-gate rule above applies to it verbatim.
```

- [ ] **Step 6: Add the rule and the reference row to `CLAUDE.md`**

In `## Naming specs and plans`, insert after the first paragraph (the one ending `` `document-conventions.md`, `document-lifecycle.md`.``), separated by one blank line:

```markdown
From v146, **specs carry a `Panel:` line** (1–3 expert role skills under
`Screen:`; `/panel` runs them after the spec commits and before close-out)
**and plans stamp `Model:`** under every `### Task` — dispatch
`task-implementer` at that tier and escalate per `model-routing.md`.
```

In `## Reference docs`, insert directly below the `document-lifecycle.md` row:

```markdown
| `model-routing.md` | writing a plan or dispatching a plan task — the `Model:` tier rubric and the escalation ladder |
```

Check: `wc -l CLAUDE.md` prints a number under 200 (169 before this task, 175 after).

- [ ] **Step 7: Mirror to Codex**

In `AGENTS.md`, insert after the line `output. Where the persona appears to conflict with a rule, the rule wins.` (same paragraph, new sentence):

```markdown
For one lens's separate critique, the expert role skills apply one seat at a
time through `expert-reviewer` and `panel` (Skills section below); a role
raises findings and never decides.
```

and in the role-agents paragraph, after the sentence V145-4 added (ending `dispatched by \`panel\` one role at a time).`), append:

```markdown
Dispatch `task-implementer` at the plan task's `**Model:**` tier. When
`task-reviewer` (always sonnet) keeps blocking, climb the ladder in
`docs/claude/model-routing.md`: the same implementer once, then a fresh one a
tier up with the findings, then the main session implements the task; log
each step in `.superpowers/sdd/progress.md`.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed` (both new tests; `close-out` stays within 80 lines and still says `Run as /close-out, or by Claude itself`).

- [ ] **Step 9: Commit**

```bash
git add .claude/skills/close-out/SKILL.md docs/claude/skills-tools.md docs/claude/persona.md CLAUDE.md AGENTS.md tests/hooks/test_role_skills.py .agents/skills
git commit -m "docs(v145): close-out clears the panel; escalation ladder replaces fails-twice; CLAUDE.md rule"
```

# Phase 5 — Verification

### Task V145-9: Run the 54 role-skill trigger cases

**Model:** sonnet — runs nine suites and, on a miss, judges whether the description or the lens boundary is at fault; never edits a case to make it pass.

**Files:**
- Modify (only on a miss): `.claude/skills/<role>/SKILL.md` `description:` lines, plus `.agents/skills/<role>/SKILL.md` via `python scripts/dev/sync_codex.py`
- Modify: `docs/claude/skills-tools.md` (one results line in `## Proving a skill fires: the eval suites`)

**Interfaces:**
- Consumes: the nine role skills and their 54 cases (V145-1..3) with their final descriptions (V145-8 changed none).
- Produces: a recorded pass count; nothing later tasks call.

- [ ] **Step 1: Leave the worktree session**

The cases cannot run from a worktree-isolated session (it refuses any command containing the substring `eval`). Ask the partner once, via `AskUserQuestion`, to exit; then `ExitWorktree` with action `keep`. Results land under each skill's gitignored `evals/results/`.

- [ ] **Step 2: Run the nine suites, one at a time**

From the main-tree session, for each role in this order — `quant-researcher`, `risk-manager`, `financial-advisor`, `veteran-trader`, `technical-analyst`, `fundamental-analyst`, `staff-engineer`, `quant-engineer`, `senior-engineer` — run:

```bash
claude plugin eval E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v145-expert-roles-model-routing/.claude/skills/<role> --runs 1 --no-publish --trust-plugin --ablation none
```

Expected: each suite exits 0 with 6/6 cases passing (54/54 overall). Cost is roughly what `skills-tools.md` records for the v96 sweep (52 cases); `--ablation none` keeps it to one arm.

- [ ] **Step 3: On a miss, fix the description, not the case**

Re-enter the worktree (`EnterWorktree` with its path). A `fire-*` miss: bring the role's `description:` closer to how that request is phrased (the trigger-table row stays as written). A `no-fire-*` false fire: add a `Not for … (<neighbour role>)` clause naming the lens that owns the prompt. Then `python scripts/dev/sync_codex.py`, `python scripts/dev/testrun.py file tests/hooks/`, and re-run only that role's suite (Step 2 command, from the main tree). At most two description revisions per role: a third miss stops the task with a `BLOCKED:` question to the partner naming the case and both revisions.

- [ ] **Step 4: Record the result**

In `docs/claude/skills-tools.md`, append to the paragraph ending `Baseline at 2026-09-21: 52/52 cases pass, all eight suites exit 0.`:

```markdown
v145 role suites, <YYYY-MM-DD>: <n>/54 cases pass across the nine role
suites (<"no description revisions" or the roles revised and why, one clause each>).
```

filled with the actual date, count and revisions from Steps 2–3.

- [ ] **Step 5: Run the hook tests**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit**

From the worktree session:

```bash
git add docs/claude/skills-tools.md .claude/skills .agents/skills
git commit -m "docs(v145): record the role-skill trigger-case results"
```

(`git add .claude/skills` stages only changed `SKILL.md` files: the run artefacts under each skill's results folder are gitignored.)

### Task V145-10: Full-suite verification

**Model:** sonnet — one full run via `test-runner`; any red is this plan's regression and is fixed forward from the failures it names.

**Files:**
- None expected. A fix-forward touches only the files the failing tests name.

**Interfaces:**
- Consumes: everything V145-1..V145-9 delivered.
- Produces: the green gate `/close-out` needs.

- [ ] **Step 1: Run the full suite once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) once, over all of v145, from the worktree.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`); the new tests add to it. No `frontend/` file changed, so `npm test` does not run.

- [ ] **Step 2: Check the standing limits**

Run each and compare:
- `python scripts/dev/sync_codex.py --check` → `Codex mirror is current.`
- `wc -l CLAUDE.md` → under 200.
- `wc -l .claude/skills/*/SKILL.md` → every file except `gate` and `task-brief` at 80 or less.
- `python -m radon cc -s -n C tests/hooks/test_role_skills.py tests/hooks/test_spec_panel_header.py tests/hooks/test_plan_model_stamp.py tests/hooks/test_agent_shape.py` → prints nothing.

- [ ] **Step 3: Fix forward if anything is red**

A failure is this plan's regression: fix it from what the run names, commit the fix in the worktree, and re-run only the failing file with `python scripts/dev/testrun.py file <test>`, then the full suite once more. Do not re-run the full suite after a clean merge.

- [ ] **Step 4: Hand off to close-out**

v145's spec has no `**Panel:**` line (exempt), so `/close-out` skips its panel step. `Bump: none`: no release commit. Merge to `main` with the `worktree-lifecycle` skill, then `/close-out` moves this plan's four parts and the spec to `implemented/` and removes the worktree.
