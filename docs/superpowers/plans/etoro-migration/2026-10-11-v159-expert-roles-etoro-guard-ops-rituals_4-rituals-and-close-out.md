# v159 Four expert seats, a demo-only eToro guard, and the ops/UI rituals. Implementation Plan, part 4 (rituals and close-out)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief ER16` or `grep -n "^### Task ER16" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md`](../../specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md) (§ C2–C5, § Testing, § Rollout)
**Index:** [`2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`](2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md): header block, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints.

**Tasks in this part:** ER15, ER16, ER17, ER18 (phase C, the remaining rituals), then ER19, ER20, ER21 (phase D, the gates). ER15–ER18 run one at a time in id order, because each one appends to the same registries (`TIER_1_AND_3`/`TIER_2`, the `skills-tools.md` tables, `AGENTS.md`). ER18 also edits `test_agent_shape.py` after ER12 (part 3). ER19–ER21 run strictly last.

**Paths.** Every command uses the absolute worktree path
`E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals`,
set as `WT=...` at the top of each command block (shell state does not
persist between calls). Never `cd`. `scripts/dev/testrun.py` and
`scripts/dev/sync_codex.py` resolve the repo root from their own path, so
running the worktree copy runs against the worktree. File edits go through the
Edit/Write tools on `$WT/<path>`. For npm, use `npm --prefix "$WT/frontend" ...`
instead of `cd frontend`.

**Anchors written by part 3.** ER11–ER14 are written in parallel with this part, so a few of the edit anchors below name a *row or entry* an earlier task created (for example "the `soak` row ER13 added") rather than quoting its text. Find that row with `grep -n` and insert immediately after it. If it is missing, the earlier task is not done: stop and report `BLOCKED: <task> not landed`, never invent the row.

# Phase C: Ops and UI rituals (continued)

Three things hold for every skill and agent task in this phase:

- **Skill shape** (`tests/hooks/test_skill_shape.py`): frontmatter `name` + a double-quoted `description` of at least 40 characters; at most 80 lines; no bare threshold (`_THRESHOLD_RE`: no `>= 5`, `< 15`, `= 10`, `3 R`, `2pp`). A model-invocable skill (`TIER_1_AND_3`) carries `## Trigger table` with at least three `Should fire:` and three `Should not fire:` lines and no `disable-model-invocation`. A slash-only ritual (`TIER_2`) carries `disable-model-invocation: true` and no Trigger table. **None of these skills contains a `## Lens` heading**: that heading makes a skill a role (`test_role_skills.lens_skills`).
- **Eval cases** for the model-invocable skills live under `.claude/skills/<name>/evals/<fire-*|no-fire-*>/` as `prompt.md` + `graders/skill-fired.md`. A no-fire grader carries both `min: 0` and `max: 0`. Never run the eval suites (each case is a paid `claude` run).
- **Codex mirror** in the same commit: `python "$WT/scripts/dev/sync_codex.py"`, a backticked mention of the new name in `AGENTS.md`, and a row in the `docs/claude/skills-tools.md` tier table or `## Which agent for what` table. Stage only the generated files of the skills and agents the task touched (`git -C "$WT" add .agents/skills/<name> .codex/agents/<name>.toml`), never `git add -A .agents`.

### Task ER15: `/incident` ritual

**Model:** haiku — one slash-only markdown checklist whose full text is given below, one test, and one-line registry appends; no judgement left to the implementer.

**Files:**
- Create: `.claude/skills/incident/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/incident/SKILL.md`, `.agents/skills/incident/agents/openai.yaml`

**Interfaces:**
- Consumes: `prod-inspector` agent (`.claude/agents/prod-inspector.md`, exists), `mirror-prod` skill (exists); ER13's `soak` entries in `TIER_2`, in the `skills-tools.md` tier table and slash-only prose, and in `AGENTS.md`'s explicit-only list (this task appends directly after each).
- Produces: slash-only skill `incident` (in `TIER_2`, `disable-model-invocation: true`); postmortem path `docs/superpowers/results/YYYY-MM-DD-incident-<name>.md`; `test_skill_shape.test_incident_ritual_triages_mitigates_mirrors_and_writes_a_postmortem`.

- [ ] **Step 1: Write the failing test**

In `$WT/tests/hooks/test_skill_shape.py`, append `"incident"` to `TIER_2`. After ER13 the set ends with `"soak"`; the result is:

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest", "handoff", "screen", "prereg", "data-check",
          "soak", "incident"}        # each ritual task appends its own name
```

(If ER13 formatted its addition differently, keep its formatting and add `"incident"` as the last member; the set's contents are what matter.)

Append at the end of the file:

```python
# v159 § C2: /incident is a slash-only checklist -- triage through
# prod-inspector, mitigate under mirror-prod, mirror, then a postmortem whose
# guard against recurrence is a test or hook rule, or a stated reason why not.
def test_incident_ritual_triages_mitigates_mirrors_and_writes_a_postmortem():
    meta, body = _read_skill("incident")
    assert meta.get("disable-model-invocation") == "true"
    assert "## Trigger table" not in body
    for phrase in ("$ARGUMENTS", "`prod-inspector`", "one question",
                   "`mirror-prod`", "smallest change",
                   "docs/superpowers/results/YYYY-MM-DD-incident-<name>.md",
                   "Timeline", "Cause", "Fix", "Guard against recurrence",
                   "none feasible"):
        assert phrase in body, phrase
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
```

Expected: FAIL. `test_incident_ritual_...` and `test_ritual_skills_are_slash_only` fail with `FileNotFoundError` on `incident/SKILL.md`; `test_every_skill_is_registered_in_exactly_one_tier` fails because `incident` is registered but not on disk.

- [ ] **Step 3: Write `incident/SKILL.md`**

Create `$WT/.claude/skills/incident/SKILL.md` with exactly:

```markdown
---
name: incident
description: "Run a production incident on the Hetzner VM as a four-step ritual: triage with prod-inspector, mitigate with the smallest change under mirror-prod, mirror and commit, then write the postmortem with a guard against recurrence. Invoked explicitly as /incident <name>, never model-triggered."
disable-model-invocation: true
---

# Production incident

Production is the Hetzner VM, reached only through
`scripts/ops/ssh-hetzner.sh`. Arguments: `$ARGUMENTS` (a short kebab-case
name for the incident, written `<name>` below).

## Step 1 — Triage

Dispatch the `prod-inspector` agent with **one question**: what is failing,
since when, and which log shows it. Its answer is read-only evidence; it never
changes the VM. Note the first and last timestamps it cites; they open the
timeline. A second question waits for the first answer.

## Step 2 — Mitigate

Load the `mirror-prod` skill before touching the VM. Make the smallest change
that stops the damage: a restart, a flag turned off, a single file
reverted. A cause fix that needs a plan waits for one; this step only
restores service. `.env` on the VM is a single-file bind mount: edit it in
place, never with `sed -i` or a rename (`docs/claude/known-traps.md`).

## Step 3 — Mirror and commit

Every live change from Step 2 is mirrored into the repo and committed before
the incident counts as handled
(`docs/claude/working-conventions.md` § Mirroring production changes back).
A cron or script change lands under `scripts/ops/`; a setting change lands
in `.env.example` and its `swingbot/config.py` field.

## Step 4 — Postmortem

Write `docs/superpowers/results/YYYY-MM-DD-incident-<name>.md`, dated the day
the incident started, with exactly these sections:

- **Timeline**: UTC timestamps from the first symptom to service restored,
  each with its log line or command.
- **Cause**: the mechanism, with `file:line` or the log excerpt that shows it.
  "Unknown" is allowed and says what evidence is missing.
- **Fix**: the Step 2 mitigation and its mirror commit, then the cause fix
  (its commit, or the plan that will carry it).
- **Guard against recurrence**: a test or a `guardrails.py` hook rule is
  preferred, named by path. "none feasible" is allowed only with a reason.

Commit the postmortem on `main` on its own.

## The gate

Service restored, every live change mirrored and committed, and the
postmortem committed with all four sections. A guard that is "none
feasible" without a reason is not a postmortem.
```

- [ ] **Step 4: Registry rows in `skills-tools.md`**

In `$WT/docs/claude/skills-tools.md`, in the skill tier table (the `| Skill | Tier | Invocation | ... |` table under § The v96 skills layer), insert directly after the `soak` row ER13 added:

```markdown
| `incident` | 2 | slash-only (`/incident <name>`) | `working-conventions.md` — Step 3 cites the `Mirroring production changes back` section; Step 2 cites `known-traps.md` for the `.env` bind mount |
```

In the prose paragraph below that table, the sentence that lists the `disable-model-invocation: true` rituals (it starts `` `/deploy`, `/stable-snapshot`, ``) gains `/incident` directly after ER13's `/soak`, before `` also carry ``. With ER13 landed, that list ends `` ..., `/data-check`, `/soak` and `/incident` also carry ``; move the word "and" so it sits before the last item only.

- [ ] **Step 5: Condensed mirror in `AGENTS.md`**

In `$WT/AGENTS.md` § Skills, the "Explicit-only rituals" paragraph lists each ritual with a parenthetical. Directly after ER13's `soak (...)` entry, add:

```markdown
`incident` (production incident: triage with `prod-inspector`, smallest
mitigation under `mirror-prod`, mirror and commit, then a postmortem at
`docs/superpowers/results/YYYY-MM-DD-incident-<name>.md` whose guard against
recurrence is a test or hook rule, or a reason why none is feasible)
```

Fix the list's commas and the final "and" so the sentence still reads as one list.

- [ ] **Step 6: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: the script writes `.agents/skills/incident/SKILL.md` and `.agents/skills/incident/agents/openai.yaml` (slash-only, so `allow_implicit_invocation: false`); a second run prints `Codex mirror is current.`; status shows only this task's files.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
wc -l "$WT/.claude/skills/incident/SKILL.md"
```

Expected: all three `0 failed`; `incident/SKILL.md` at most 80 lines. `test_role_skills.py` stays green because the skill has no `## Lens` heading. A threshold-regex hit is reworded, never exempted.

- [ ] **Step 8: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/skills/incident tests/hooks/test_skill_shape.py docs/claude/skills-tools.md AGENTS.md .agents/skills/incident
git -C "$WT" commit -m "feat(v159): /incident ritual

Slash-only four-step checklist: triage through prod-inspector, smallest
mitigation under mirror-prod, mirror and commit, postmortem under
docs/superpowers/results/ with a guard against recurrence. Registered in
TIER_2, the skills-tools.md tier table and AGENTS.md; Codex mirror
regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER16: `frontend` skill

**Model:** sonnet — a model-invocable seam briefing whose facts are given below, two eval cases, one shape test and registry appends; the implementer checks each cited path exists.

**Files:**
- Create: `.claude/skills/frontend/SKILL.md`
- Create: `.claude/skills/frontend/evals/fire-settings-toggle/prompt.md` (+ `graders/skill-fired.md`)
- Create: `.claude/skills/frontend/evals/no-fire-embed-field/prompt.md` (+ `graders/skill-fired.md`)
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/frontend/SKILL.md`

**Interfaces:**
- Consumes: ER15's `TIER_2` (unchanged here); ER11's `order-safety` member of `TIER_1_AND_3` (this task appends after it).
- Produces: model-invocable skill `frontend` (in `TIER_1_AND_3`); `test_skill_shape.test_frontend_skill_maps_the_spa_and_its_gates`. ER17's `chart-render` names `frontend` in its Out-of-scope line; ER18's `ui-verifier` names it as the skill that owns build and serve commands.

**Facts this skill states (verified while writing the plan; re-check each path with `git -C "$WT" ls-files <path>` in Step 3):**
- `frontend/src/app` holds `api/` (`api-client.ts` with `base = '/api/v1'`, `models.ts`, `event-stream.ts`, `interceptors.ts`), `pwa/`, `routing/`, `shell/`, `stores/` (e.g. `system.store.ts`), `testing/` (`dialog-polyfill.ts`, `match-media-polyfill.ts`), `ui/` (`confirm-dialog.ts`, `data-table/`, `chart/`), `workspaces/` (one folder per route: `analytics`, `calendar`, `dashboard`, `gallery`, `risk`, `stubs`, `system`, `trades`, `versions`, `watchlist`), plus `app.routes.ts`.
- Same-origin by design (`frontend/proxy.conf.json`): session-cookie auth, and `EventSource` sends no headers. In development `npm start -- --port 4123` proxies `/api` and `/static` to `python admin_ui.py` on `:1234`. In the image, the `Dockerfile` frontend stage runs `npm ci` then `npm run build` and copies `dist/frontend/browser` to `swingbot/admin/static/app`, which `swingbot/admin/spa.py` serves.
- Tests: Vitest through `@angular/build:unit-test`. Per task `npm test -- --include <spec>`; a bare run once per plan (`docs/claude/document-conventions.md`). A 60-second worker timeout with no tests run is load: re-run (`docs/claude/testing-cost.md` § Frontend). The Python tests write a fake `index.html`, so only `scripts/dev/smoke_spa.py` proves a built bundle serves.
- Theme: **dark only** (`frontend/src/styles/tokens.css` header: no light theme, no `prefers-color-scheme`). Chart PNGs share the palette through `chart_style.py`'s `THEME`, pinned by `tests/charts/test_chart_theme.py`. Spacing is one token, `--section-gap`, pinned by `ui/spacing.spec.ts` and `workspaces/workspace-gaps.spec.ts`; contrast by `ui/contrast.spec.ts`. The `frontend-design` plugin's conventions are skipped for the admin UI unless asked (`docs/claude/skills-tools.md`).

- [ ] **Step 1: Write the failing test**

In `$WT/tests/hooks/test_skill_shape.py`, append `"frontend"` as a new last member of `TIER_1_AND_3` (after ER11's `"order-safety"`; keep the trailing comment):

```python
                "staff-engineer", "quant-engineer", "senior-engineer",
                "execution-specialist", "compliance-reviewer",
                "ux-designer", "sre", "order-safety",
                "frontend"}   # each skill task appends its own name
```

(The lines before `"frontend"` are whatever ER1, ER2 and ER11 left; only add the one member.)

Append at the end of the file:

```python
# v159 § C3: the frontend skill is the seam briefing for frontend/. It names
# the layout, the same-origin API path, the narrow test command and the
# dark-only theme, and hands visual judgement and embeds to their owners.
def test_frontend_skill_maps_the_spa_and_its_gates():
    meta, body = _read_skill("frontend")
    assert len(meta["description"]) <= 260
    for folder in ("api/", "pwa/", "routing/", "shell/", "stores/",
                   "testing/", "ui/", "workspaces/"):
        assert f"`{folder}`" in body, folder
    for phrase in ("`/api/v1`", "proxy.conf.json", "4123", "`--include`",
                   "tokens.css", "dark only", "test_chart_theme.py",
                   "smoke_spa.py", "`ux-designer`", "`alert-surface`"):
        assert phrase in body, phrase
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
```

Expected: FAIL. `test_frontend_skill_...` and `test_model_invocable_skills_carry_a_trigger_table` fail with `FileNotFoundError` on `frontend/SKILL.md`; `test_every_skill_is_registered_in_exactly_one_tier` fails.

- [ ] **Step 3: Write `frontend/SKILL.md`**

First confirm the cited paths exist (any `MISSING` line: stop and report it, never cite a path that is not there):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
for p in frontend/proxy.conf.json frontend/src/styles/tokens.css frontend/src/app/api/api-client.ts frontend/src/app/ui/spacing.spec.ts frontend/src/app/ui/contrast.spec.ts frontend/src/app/workspaces/workspace-gaps.spec.ts tests/charts/test_chart_theme.py scripts/dev/smoke_spa.py swingbot/admin/spa.py; do git -C "$WT" ls-files --error-unmatch "$p" >/dev/null 2>&1 || echo "MISSING $p"; done
```

Create `$WT/.claude/skills/frontend/SKILL.md` with exactly:

```markdown
---
name: frontend
description: "Use when editing the Angular admin SPA under frontend/ -- its src/app layout, how it calls admin_ui.py over /api/v1, build and test commands, the dark-only theme tokens. Not for visual judgement (ux-designer) or Discord alert embeds (alert-surface)."
---

# Frontend (admin SPA)

## Step 1 — Read the authority

`python scripts/dev/doc_section.py docs/claude/architecture.md "Module map"`
(the `frontend/` bullet: the spacing rule), and the `ng test` timeout section
of `docs/claude/testing-cost.md`. Exit code 2 means read the whole file. This
skill is the map; the reasons live there.

## Step 2 — Where a change goes

`frontend/src/app`: `api/` (`api-client.ts`, the typed `models.ts`, the
`event-stream.ts` SSE client), `pwa/`, `routing/`, `shell/` (frame, login,
toasts), `stores/` (signal stores, one per area), `testing/` (polyfills the
specs need), `ui/` (shared components such as `confirm-dialog.ts`),
`workspaces/` (one folder per route; routes in `app.routes.ts`). A component
belongs to the workspace that uses it until a second workspace needs it; then
it moves to `ui/`.

## Step 3 — How it reaches `admin_ui.py`

Same origin by design (`frontend/proxy.conf.json`): the API authenticates by
session cookie and `EventSource` sends no headers. Every call goes through
`api-client.ts` under `/api/v1`; a new endpoint lands in
`swingbot/admin/api_v1/` and its type in `api/models.ts` in the same change.
Local: `python admin_ui.py` on `:1234`, then `npm start -- --port 4123` inside
`frontend/` (never the CLI's default port). In the image the `Dockerfile`
builds the bundle into `swingbot/admin/static/app`, served by
`swingbot/admin/spa.py`.

## Step 4 — Build and test

Per task: `npm test -- --include <the spec file you touched>`. A bare
`npm test` runs once per plan (`docs/claude/document-conventions.md`). A
worker timeout with no tests run is machine load: re-run it. Build with
`npm run build`. The Python suite writes a fake `index.html`, so a change to
routing, `<base href>` or the build only counts once
`scripts/dev/smoke_spa.py` passes against a running instance.

## Step 5 — Theme

The SPA is dark only: the tokens in `frontend/src/styles/tokens.css` carry no
light theme and no `prefers-color-scheme` block. Chart PNGs share that
palette; `tests/charts/test_chart_theme.py` names the chart constant that must
follow a token change. Panel spacing is one token, `--section-gap`
(`ui/spacing.spec.ts`, `workspaces/workspace-gaps.spec.ts`); contrast is
pinned by `ui/contrast.spec.ts`. The `frontend-design` plugin's conventions do
not apply here unless the partner asks.

## Out of scope

Visual judgement (hierarchy, density, mobile): `ux-designer`. Discord embeds
and the alert text: `alert-surface`. Chart image rendering: `chart-render`.

## Trigger table

Should fire: adding a toggle to the Settings tab in the admin SPA.
Should fire: a new workspace route under `frontend/src/app/workspaces/`.
Should fire: a vitest spec in `frontend/` failing after a store change.
Should not fire: adding a field to the Discord trade-plan embed.
Should not fire: changing a Flask route's validation in `swingbot/admin/api_v1/` with no SPA change.
Should not fire: changing how a chart PNG draws its stop line.
```

- [ ] **Step 4: Write the two eval cases**

Under `$WT/.claude/skills/frontend/evals/`:

`fire-settings-toggle/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Add a new toggle to the Settings tab in the admin SPA and wire it to the system store.
```

`fire-settings-toggle/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: frontend
min: 1
---

The `frontend` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`no-fire-embed-field/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Add a "days to earnings" field to the Discord trade-plan embed.
```

`no-fire-embed-field/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: frontend
min: 0
max: 0
---

The `frontend` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

- [ ] **Step 5: Registry rows**

In `$WT/docs/claude/skills-tools.md`, in the skill tier table, insert after the last tier-1/3 row (the row directly above `` | `close-out` | 2 | ``):

```markdown
| `frontend` | 3 | model-invocable | `architecture.md` (`Module map`, the `frontend/` bullet), `testing-cost.md` (the `ng test` timeout section) |
```

In `$WT/AGENTS.md` § Skills, in the `| Situation | Read |` table, insert directly after the `alert-surface` row:

```markdown
| Editing the Angular admin SPA under `frontend/` (layout, API calls, build, tests, theme tokens) | `frontend` |
```

- [ ] **Step 6: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: writes `.agents/skills/frontend/SKILL.md` only (model-invocable, so no `openai.yaml`); a second run prints `Codex mirror is current.`

- [ ] **Step 7: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
wc -l "$WT/.claude/skills/frontend/SKILL.md"
```

Expected: all three `0 failed`; at most 80 lines. A threshold-regex hit is reworded, never exempted (the port numbers and `:1234` carry no comparison operator, so they do not match).

- [ ] **Step 8: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/skills/frontend tests/hooks/test_skill_shape.py docs/claude/skills-tools.md AGENTS.md .agents/skills/frontend
git -C "$WT" commit -m "feat(v159): frontend skill

Model-invocable seam briefing for frontend/: src/app layout, the
same-origin /api/v1 path, narrow and once-per-plan test commands, the
dark-only theme tokens. 1+1 eval cases. Registered in TIER_1_AND_3, the
skills-tools.md tier table and AGENTS.md; Codex mirror regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER17: `chart-render` skill and the `alert-surface` pointer

**Model:** sonnet — a model-invocable seam briefing over five chart modules, with the alert-path map and layering bands verified from code below, a small edit to an existing skill's description, and registry appends.

**Files:**
- Create: `.claude/skills/chart-render/SKILL.md`
- Create: `.claude/skills/chart-render/evals/fire-label-overlap/prompt.md` (+ `graders/skill-fired.md`)
- Create: `.claude/skills/chart-render/evals/no-fire-embed-wording/prompt.md` (+ `graders/skill-fired.md`)
- Modify: `.claude/skills/alert-surface/SKILL.md` (description line 3; trigger-table line 57)
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.agents/skills/chart-render/SKILL.md`, `.agents/skills/alert-surface/SKILL.md`

**Interfaces:**
- Consumes: ER16's `"frontend"` member of `TIER_1_AND_3` and its `AGENTS.md` situation row (this task appends after each).
- Produces: model-invocable skill `chart-render` (in `TIER_1_AND_3`); `test_skill_shape.test_chart_render_skill_maps_paths_layers_and_the_upload_limit`; `test_skill_shape.test_alert_surface_points_at_chart_render`.

**Facts this skill states (verified while writing the plan; Step 3 re-checks the call sites):**
- Which chart each alert path posts:
  - scan alert, `swingbot/core/scanning/scan_run.py` (and the short-side path in `short_run.py`): `render_decision_chart` (`decision_chart.py`) when `config.DECISION_CHART_ENABLED` is on **and** the item has a v2 plan; otherwise `generate_trade_chart` (`trade_chart.py`). The flag off leaves the legacy path unchanged (its `Field` help text in `swingbot/config.py`).
  - lifecycle embeds (`swingbot/core/scanning/lifecycle_embeds.py`): `generate_trade_chart` with MFE/MAE markers.
  - the plan-panel button (`swingbot/commands/views.py`): `generate_trade_chart(..., plan_v2=plan)`.
  - `!strategycharts` (`swingbot/commands/info.py`): `generate_all_strategy_charts`.
- Layering is matplotlib `zorder` bands: FVG zones 2 (`chart_strategy_overlay.py`), matched levels 3, overlay lines and trendlines 4, level lines 5 (`chart_drawing.py`), labels and level tags 6 (`chart_drawing.py`, `chart_annotations.draw_level`), legend text and point markers 7 (`chart_annotations.draw_legend_block`, `chart_strategy_overlay.py`). Overlay geometry is computed in `chart_geometry.overlay_geometry` and only drawn by `chart_strategy_overlay.py`; label collisions go through `chart_drawing._spread_labels`. Colours come from `chart_style.py`'s `THEME`, pinned to the SPA tokens by `tests/charts/test_chart_theme.py`.
- Byte-identical refactors are proved by `scripts/dev/render_chart_fixtures.py` (renders one PNG per overlay kind and hashes it). Render tests live in `tests/charts/` (`test_decision_chart.py`, `test_trade_chart_v2.py`, `test_chart_annotations.py`, `test_plan_chart_overlays.py`, `test_chart_layout.py`, `test_chart_theme.py`, ...).
- The Discord upload limit is not in code (`git grep` for a byte cap under `swingbot/` is empty; index Global Constraints). It is an external fact: Discord caps a message's attachments by the server's boost tier, and an unboosted server's cap is 10 MiB (Discord Help Center, "File Upload Size Limit"). At run time `discord.Guild.filesize_limit` returns the live cap. The skill adds no constant.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/hooks/test_skill_shape.py`, add `"chart-render"` as the new last member of `TIER_1_AND_3`, directly after ER16's `"frontend"`:

```python
                "frontend", "chart-render"}   # each skill task appends its own name
```

Append at the end of the file:

```python
# v159 § C4: chart-render maps which chart each alert path posts, the zorder
# bands, the upload limit as an external fact (no constant), and the
# NO-LOOKAHEAD boundary; alert-surface hands chart images to it.
def test_chart_render_skill_maps_paths_layers_and_the_upload_limit():
    meta, body = _read_skill("chart-render")
    assert len(meta["description"]) <= 260
    for phrase in ("`render_decision_chart`", "`generate_trade_chart`",
                   "`generate_all_strategy_charts`", "`DECISION_CHART_ENABLED`",
                   "zorder", "`overlay_geometry`", "filesize_limit",
                   "adds no constant", "`no-lookahead`",
                   "only bars the alert knew", "render_chart_fixtures.py",
                   "tests/charts/", "`alert-surface`"):
        assert phrase in body, phrase


def test_alert_surface_points_at_chart_render():
    meta, body = _read_skill("alert-surface")
    assert "chart-render" in meta["description"]
    assert "(use `chart-render`)" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
```

Expected: FAIL. `test_chart_render_skill_...` raises `FileNotFoundError`; `test_alert_surface_points_at_chart_render` fails on the description assert; `test_every_skill_is_registered_in_exactly_one_tier` and `test_model_invocable_skills_carry_a_trigger_table` fail.

- [ ] **Step 3: Re-check the call sites, then write `chart-render/SKILL.md`**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" grep -n "render_decision_chart(\|generate_trade_chart\b\|generate_all_strategy_charts(" -- swingbot/core/scanning swingbot/commands
git -C "$WT" grep -n "zorder=" -- swingbot/core/charts
git -C "$WT" grep -n -i "filesize\|upload.*limit\|MAX_.*BYTES" -- swingbot
```

Expected: the four call sites in the facts list (`scan_run.py`, `short_run.py`, `lifecycle_embeds.py`, `views.py`, `info.py`); `zorder` values 2–7 only; the third grep finds no byte cap. If a call site moved or a new one exists, write the map from what the grep shows and note the difference in the commit message. Never invent a path.

Create `$WT/.claude/skills/chart-render/SKILL.md` with exactly:

```markdown
---
name: chart-render
description: "Use when editing a chart renderer under swingbot/core/charts/ -- which chart each alert path posts, annotation layering, the Discord upload limit, render tests, and the rule that a chart draws only bars the alert knew. Not for embed text (alert-surface) or the SPA (frontend)."
---

# Chart render

## Step 1 — Read the authority

`python scripts/dev/doc_section.py docs/claude/architecture.md "NO-LOOKAHEAD"`.
Exit code 2 means read the whole file. When an annotation is drawn from a
computed level (S/R, Fibonacci, FVG, a trendline fit), load the
`no-lookahead` skill as well.

## Step 2 — Which chart this alert path posts

- Scan alert (`swingbot/core/scanning/scan_run.py`, short side in
  `short_run.py`): `render_decision_chart` (`decision_chart.py`) when
  `DECISION_CHART_ENABLED` is on and a v2 plan exists, else
  `generate_trade_chart` (`trade_chart.py`). Flag off keeps the legacy chart
  unchanged.
- Lifecycle embeds (`lifecycle_embeds.py`): `generate_trade_chart` with
  MFE/MAE markers.
- Plan-panel button (`swingbot/commands/views.py`): `generate_trade_chart`
  with the v2 plan.
- `!strategycharts` (`swingbot/commands/info.py`):
  `generate_all_strategy_charts`.

Name the path you are changing before you change a renderer it shares.

## Step 3 — Layering

Artists stack by matplotlib `zorder` bands: zones lowest, then matched
levels, overlay lines and trendlines, level lines, labels and tags, and the
legend and point markers on top (`chart_strategy_overlay.py`,
`chart_drawing.py`, `chart_annotations.py`). Put a new artist in the band of
its kind, never a fresh number. Geometry is computed in
`chart_geometry.py`'s `overlay_geometry` and only drawn by
`chart_strategy_overlay.py`; colliding labels go through `_spread_labels`;
colours come from `chart_style.py`'s `THEME`.

## Step 4 — Only bars the alert knew

A chart draws only bars the alert knew about at its decision time: no level,
fit or marker computed from a later bar. Lifecycle charts do show later
bars (their MFE/MAE markers are after the fact by design), but a trendline
on them is the fit stored at alert time, drawn rather than recomputed
(`tests/charts/test_trade_chart_stored_fit.py`).

## Step 5 — Image size

Discord caps a message's attachments by the server's boost tier; an
unboosted server's cap is 10 MiB (Discord Help Center, "File Upload Size
Limit"). `discord.Guild.filesize_limit` gives the live cap. No byte cap
exists in `swingbot/`, and this skill adds no constant; a change that grows
the figure size or DPI states the PNG size it measured.

## Step 6 — Render tests

`tests/charts/` holds the render tests (`test_decision_chart.py`,
`test_trade_chart_v2.py`, `test_chart_annotations.py`, `test_chart_theme.py`,
...). A refactor that claims no visual change proves it with
`scripts/dev/render_chart_fixtures.py`: render before, render after, compare
the hashes.

## Out of scope

Embed fields and alert text: `alert-surface`. The admin SPA: `frontend`.
Whether the chart reads well: `ux-designer`.

## Trigger table

Should fire: the stop label on the decision chart overlaps the target label.
Should fire: adding a new overlay line to `generate_trade_chart`.
Should fire: a chart PNG posted to Discord is too large to upload.
Should not fire: changing the wording of the stop field in an alert embed.
Should not fire: adding a toggle to the admin Settings tab.
Should not fire: tuning a strategy's entry threshold under `swingbot/core/edge/`.
```

- [ ] **Step 4: Point `alert-surface` at it**

In `$WT/.claude/skills/alert-surface/SKILL.md`, line 3, replace the end of the description:

```
Not for chart image generation and not for the admin UI."
```

with:

```
Not for chart image generation (chart-render) and not for the admin UI (frontend)."
```

and in its trigger table replace:

```markdown
Should not fire: editing a chart image renderer under `swingbot/core/charts/`.
```

with:

```markdown
Should not fire: editing a chart image renderer under `swingbot/core/charts/`
(use `chart-render`).
```

- [ ] **Step 5: Write the two eval cases**

Under `$WT/.claude/skills/chart-render/evals/`:

`fire-label-overlap/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

On the decision chart the stop label is drawn on top of the target label. Fix the layering in swingbot/core/charts.
```

`fire-label-overlap/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: chart-render
min: 1
---

The `chart-render` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

`no-fire-embed-wording/prompt.md`:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

Change the wording of the stop-loss field in the Discord alert embed to say "Stop (hard)".
```

`no-fire-embed-wording/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: chart-render
min: 0
max: 0
---

The `chart-render` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

- [ ] **Step 6: Registry rows**

In `$WT/docs/claude/skills-tools.md`, in the skill tier table, insert directly after ER16's `frontend` row:

```markdown
| `chart-render` | 3 | model-invocable | `architecture.md` (`NO-LOOKAHEAD`) |
```

In `$WT/AGENTS.md` § Skills, in the `| Situation | Read |` table, insert directly after ER16's `frontend` row:

```markdown
| Editing a chart renderer under `swingbot/core/charts/` (which chart an alert posts, annotation layers, image size) | `chart-render` |
```

- [ ] **Step 7: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: writes `.agents/skills/chart-render/SKILL.md` and rewrites `.agents/skills/alert-surface/SKILL.md`; a second run prints `Codex mirror is current.`

- [ ] **Step 8: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_skill_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_role_skills.py
wc -l "$WT/.claude/skills/chart-render/SKILL.md" "$WT/.claude/skills/alert-surface/SKILL.md"
```

Expected: all three `0 failed`; both SKILL.md files at most 80 lines. "10 MiB" carries no comparison operator and is not a `pp`/`R` unit, so `_THRESHOLD_RE` does not match it; any other hit is reworded, never exempted.

- [ ] **Step 9: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/skills/chart-render .claude/skills/alert-surface/SKILL.md tests/hooks/test_skill_shape.py docs/claude/skills-tools.md AGENTS.md .agents/skills/chart-render .agents/skills/alert-surface
git -C "$WT" commit -m "feat(v159): chart-render skill; alert-surface points at it

Model-invocable seam briefing for swingbot/core/charts/: which chart each
alert path posts, the zorder bands, the Discord upload limit as an
external fact (discord.Guild.filesize_limit, no constant), render tests
and the bars-the-alert-knew boundary. 1+1 eval cases. alert-surface's
description and trigger table hand chart images to it. Codex mirror
regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER18: `ui-verifier` agent

**Model:** haiku — one agent contract whose full text (including the Playwright walk script) is given below, one shape test and registry appends; nothing is executed against a live UI in this task.

**Files:**
- Create: `.claude/agents/ui-verifier.md`
- Modify: `tests/hooks/test_agent_shape.py`
- Modify: `docs/claude/skills-tools.md`
- Modify: `AGENTS.md`
- Generated: `.codex/agents/ui-verifier.toml`

**Interfaces:**
- Consumes: ER12's `reconciler` entries in `test_agent_shape.py`, in the `skills-tools.md` `## Which agent for what` table and in `AGENTS.md`'s role-agent list (this task appends after each); ER2's `ux-designer` skill, which already cites `ui-verifier` screenshots; ER16's `frontend` skill (named as the owner of the serve commands).
- Produces: agent `ui-verifier` (sonnet; tools `Bash, Read`); return shape `FINDINGS: ... / SCREENSHOTS: <paths> / BLOCKED: ...`; `EXPECTED["ui-verifier"] = {"model": "sonnet", "skills": set()}`; `test_agent_shape.test_ui_verifier_never_writes`.

**Two decisions taken from the repo, not the spec's wording (recorded for the controller):**
- **Browser.** The spec names "Claude in Chrome, or the built-in browser where available". `docs/claude/skills-tools.md` (§ Repo tooling, "Driving a browser") rules **Playwright, never `claude-in-chrome`**, because the extension is not connected in this repo's sessions. The agent drives Playwright through Bash and lists no MCP browser tools.
- **Themes.** The spec asks for light and dark screenshots. The SPA is dark only (`frontend/src/styles/tokens.css`: no light theme, no `prefers-color-scheme`). The agent captures every route under Playwright `colorScheme: 'dark'` and `'light'`. The two must look the same; a difference is a finding (something follows the OS scheme).

- [ ] **Step 1: Write the failing test**

In `$WT/tests/hooks/test_agent_shape.py`, add a new last entry to `EXPECTED`, after `"expert-reviewer"` (ER12's `"reconciler"` entry sits after `"prod-inspector"`; dict order does not matter):

```python
    # v159 § C5: drives Playwright through Bash; preloads nothing. The
    # frontend skill holds the serve commands it repeats.
    "ui-verifier": {
        "model": "sonnet",
        "skills": set(),
    },
}
```

Append at the end of the file:

```python
# v159 § C5: ui-verifier only looks. It has no Edit/Write tools, never
# submits a form or opens a dialog, logs in with the default or exported
# credentials (never from .env), and hands back screenshot paths.
def test_ui_verifier_never_writes():
    meta, body = _read_agent("ui-verifier")
    tools = {t.strip() for t in meta.get("tools", "").split(",")}
    assert tools == {"Bash", "Read"}
    for phrase in ("never submits", "never opens a dialog", "Playwright",
                   "scratchpad", "console", "colorScheme", "4123",
                   "/api/v1/session", "never read `.env`",
                   "FINDINGS:", "SCREENSHOTS:", "BLOCKED:"):
        assert phrase in body, phrase
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py
```

Expected: FAIL. `test_ui_verifier_never_writes` and the two parametrised `ui-verifier` cases (`test_role_agent_pins_model_and_skills`, `test_role_agent_has_fixed_return_shape`) fail with `FileNotFoundError`.

- [ ] **Step 3: Write `ui-verifier.md`**

Create `$WT/.claude/agents/ui-verifier.md` with exactly the text between the two `~~~~` fence lines below (the fence is four tildes because the agent body contains its own triple-backtick blocks):

~~~~markdown
---
name: ui-verifier
description: "Opens the admin SPA (local ng serve or a given URL) with Playwright, walks the routes a diff touches, saves dark and light screenshots to the session scratchpad and reads the console. Looks only: never submits a form or opens a dialog. Returns findings and screenshot paths."
tools: Bash, Read
model: sonnet
---

You look at the admin SPA and report what you see. You are given a base URL
(default: local `ng serve` at `http://localhost:4123`), the routes a diff
touches (for example `system`, `risk`, `trades`), and the session
scratchpad path. You change nothing.

## Getting a UI to look at

- Local: the controller has `python admin_ui.py` on `:1234` and
  `npm start -- --port 4123` running inside `frontend/` (the `frontend`
  skill). If `http://localhost:4123` does not answer, return
  `BLOCKED: no UI at <url> -- start admin_ui.py and ng serve on 4123?`;
  do not start servers yourself.
- Playwright, never the Chrome extension (`docs/claude/skills-tools.md`).
  If `require('playwright')` fails, run once
  `npm --prefix <repo>/frontend install --no-save playwright` and
  `npx --prefix <repo>/frontend playwright install chromium`.
- Login: `POST /api/v1/session` with `ADMIN_USERNAME`/`ADMIN_PASSWORD` from
  the environment, default `admin`/`admin`. You never read `.env` to find a
  real password; if the default is refused, return `BLOCKED:` and ask.

## The walk

Write this script to `<scratchpad>/ui-verifier/walk.cjs` and run it with
`NODE_PATH=<repo>/frontend/node_modules node <scratchpad>/ui-verifier/walk.cjs <baseUrl> <scratchpad>/ui-verifier <route>...`:

```js
// walk.cjs -- looks only: GETs the routes, never clicks, never submits.
const { chromium } = require('playwright');
const [base, out, ...routes] = process.argv.slice(2);
const root = base.replace(/\/$/, '');
const login = { username: process.env.ADMIN_USERNAME || 'admin',
                password: process.env.ADMIN_PASSWORD || 'admin' };
(async () => {
  const browser = await chromium.launch();
  for (const colorScheme of ['dark', 'light']) {
    const context = await browser.newContext({ colorScheme, viewport: { width: 1440, height: 900 } });
    const auth = await context.request.post(`${root}/api/v1/session`, { data: login });
    if (!auth.ok()) { console.log(JSON.stringify({ blocked: `login ${auth.status()}` })); process.exit(2); }
    const page = await context.newPage();
    page.on('dialog', (d) => d.dismiss());
    for (const route of routes) {
      const errors = [];
      const onConsole = (m) => { if (m.type() === 'error') errors.push(m.text()); };
      const onPageError = (e) => errors.push(String(e));
      page.on('console', onConsole);
      page.on('pageerror', onPageError);
      await page.goto(`${root}/${route.replace(/^\//, '')}`, { waitUntil: 'load' });
      await page.waitForTimeout(1500);   // the SSE stream never goes idle
      const file = `${out}/${route.replace(/[^\w-]+/g, '_') || 'root'}-${colorScheme}.png`;
      await page.screenshot({ path: file, fullPage: true });
      console.log(JSON.stringify({ route, colorScheme, file, errors }));
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
    }
    await context.close();
  }
  await browser.close();
})();
```

Then `Read` each screenshot and compare the dark and light capture of the
same route. The SPA is dark only (`frontend/src/styles/tokens.css`), so the
two should match; any difference is a finding.

## Never

- It never submits a form, never opens a dialog, and never clicks a save,
  toggle or delete control. The script only navigates; you add no clicks to
  it. The only POST is the login.
- Never point it at production unless the controller gave you that URL in
  the prompt, and then only with the same script.
- Never write outside `<scratchpad>/ui-verifier/`; never edit repo files.

## What counts as a finding

A console error or page error (quote it), a route that renders blank or an
error state with data present, a dark/light difference, text cut off or
overlapping, or a route that redirects somewhere other than itself. Visual
judgement (hierarchy, density) is `ux-designer`'s; you state what is on the
screen and leave judging to them.

## Return shape

```
FINDINGS: <= 10 lines, each `<route> <dark|light>: <what>` with the console excerpt, or `none`
SCREENSHOTS: <one absolute path per line>
BLOCKED: <only if the UI could not be reached or logged into -- one question>
```
~~~~

- [ ] **Step 4: Registry rows**

In `$WT/docs/claude/skills-tools.md` § Which agent for what (v107), insert directly after ER12's `reconciler` row:

```markdown
| Dark and light screenshots plus console errors for the admin SPA routes a diff touches (looks only, Playwright) | `ui-verifier` | sonnet |
```

In `$WT/AGENTS.md`, in the role-agent list ("Claude's role agents are mirrored as Codex agents ..."), directly after ER12's `reconciler` entry, add:

```markdown
`ui-verifier` (opens the admin SPA with Playwright, walks the routes a diff
touches, returns dark and light screenshot paths and console errors; never
submits a form or opens a dialog),
```

keeping the list's punctuation consistent.

- [ ] **Step 5: Regenerate the Codex mirror**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/sync_codex.py"
git -C "$WT" status --short
```

Expected: writes `.codex/agents/ui-verifier.toml` (sonnet is a `CODEX_TIERS` key); a second run prints `Codex mirror is current.`

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_agent_shape.py
python "$WT/scripts/dev/testrun.py" file tests/hooks/test_codex_mirror.py
```

Expected: both `0 failed`. `test_every_agent_description_is_read_without_its_quotes` passes because the description is one double-quoted scalar.

- [ ] **Step 7: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add .claude/agents/ui-verifier.md tests/hooks/test_agent_shape.py docs/claude/skills-tools.md AGENTS.md .codex/agents/ui-verifier.toml
git -C "$WT" commit -m "feat(v159): ui-verifier agent

Sonnet, tools Bash and Read. Walks the admin SPA routes a diff touches
with Playwright (skills-tools.md rules out the Chrome extension), saves a
dark and a light capture per route to the scratchpad (the SPA is dark
only, so a difference is a finding), reads console errors. Never submits
a form or opens a dialog; logs in via /api/v1/session with default or
exported credentials, never .env. Registered in EXPECTED, the agent
table and AGENTS.md; Codex mirror regenerated.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase D: Gates and close-out

ER19–ER21 run strictly in order, after ER1–ER18 are all committed on the branch. No task in this phase adds a feature. A failure found here is fixed in the file the failing test names, as its own `fix(v159): ...` commit on the branch. It is never fixed by weakening a test, raising a cap or adding an exemption.

### Task ER19: Full suite, frontend tests, complexity sweep

**Model:** haiku — runs fixed commands and reads one-line verdicts; any failure is handed back, not diagnosed here.

**Files:**
- Modify: none, unless a check below fails (then only the file the failure names, in a separate `fix(v159):` commit)

**Interfaces:**
- Consumes: every artefact of ER1–ER18 on branch `2026-10-11-v159-expert-roles-etoro-guard-ops-rituals`.
- Produces: the green gate ER20 and ER21 rely on: one full-suite verdict line, one frontend verdict line and a radon listing, recorded under `## Progress` in the worktree copy of the index (`docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md`).

- [ ] **Step 1: Every task is committed**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" status --short
git -C "$WT" log --oneline main..HEAD
```

Expected: status prints nothing. The log shows a `feat(v159)`/`fix(v159)` commit for each of ER1–ER18 (ER3 and ER4 may share wording; count by subject). A missing task: stop and report `BLOCKED: ER<n> has no commit`.

- [ ] **Step 2: Structural invariants**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
wc -l "$WT/CLAUDE.md"
ls "$WT/swingbot/core/broker"
python "$WT/scripts/dev/sync_codex.py" --check
git -C "$WT" grep -n "ETORO_ALLOW_REAL=true\|ETORO_ALLOW_REAL=1" -- ".env*"
git -C "$WT" grep -n "^ETORO_REAL_SIGNOFF=." -- ".env*"
python "$WT/scripts/dev/plan_lint.py" "$WT/docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md"
```

Expected:
- `CLAUDE.md` at most 199 lines.
- `swingbot/core/broker` lists only `__init__.py` and `guard.py` (plus `__pycache__` if present). No `sizing.py` or `pre_open.py`; those are v160's.
- `Codex mirror is current.`
- Both `git grep` lines print nothing. No tracked `.env*` file unlocks real money.
- `plan_lint` verdict passes for the whole split plan.

- [ ] **Step 3: Full Python suite**

Dispatch the `test-runner` agent (sonnet) with: "Run `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals/scripts/dev/testrun.py full` and return its one-line verdict." When running inline instead:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
python "$WT/scripts/dev/testrun.py" full
```

Expected: `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md` § What the pass count means when it changes). Any failure: hand back the failing test ids. Fix in a `fix(v159):` commit, re-run that one file with `testrun.py file <test>`, then re-run `full` once.

- [ ] **Step 4: Frontend suite, once (ER10 touched `frontend/`)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
test -d "$WT/frontend/node_modules" || npm --prefix "$WT/frontend" ci
npm --prefix "$WT/frontend" test -- --watch=false
```

Expected: Vitest reports every test file passed, `0 failed`. Exactly 60 seconds then `Timeout waiting for worker to respond` with no tests run is machine load (`docs/claude/testing-cost.md` § Frontend): re-run once, never count it as a pass or a fail.

- [ ] **Step 5: Complexity sweep over every changed Python file**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" diff --name-only main...HEAD -- "*.py"
git -C "$WT" diff --name-only main...HEAD -- "*.py" | sed "s|^|$WT/|" | xargs python -m radon cc -s -n C
TMP=$(mktemp -d)
git -C "$WT" show main:swingbot/admin/api_v1/system.py > "$TMP/system_main.py"
python -m radon cc -s -n C "$TMP/system_main.py"
rm -r "$TMP"
```

Expected: the only function at C or worse with a score of at least 15 in the branch listing is `swingbot/admin/api_v1/system.py` `_validate`, and its score equals the `main` copy's (D 21 when the plan was written). Every function ER5–ER14 added or changed (`_rule_etoro_real_account`, `_rules_for`, `_patch_sections`, `_rule_apply_patch`, `_soak_block`, `_rule_soak_prereg_locked`, `evaluate`, `signoff_valid`, `real_unlocked`, `assert_demo`, `_real_money_problem`, `save_settings`, the preview route, `env_set.main`, `unguarded_etoro_modules`) scores below 15. Anything else at 15 or above, or a higher `_validate` score: split it into named helpers without changing behaviour (`docs/claude/code-complexity.md`), commit as `fix(v159): ...`, and re-run Steps 3 and 5.

- [ ] **Step 6: Record the gate**

In the worktree copy of the index, under `## Progress`, append this line (keep whatever earlier phases wrote there; if the block still reads only `Not started. ...`, replace that sentence):

```markdown
- ER19 gate (<YYYY-MM-DD>, <HEAD short sha>): python full `<verdict line>`; frontend `<verdict line>`; radon: only `_validate` at D <score> (unchanged from main).
```

with the real values filled in.

- [ ] **Step 7: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md
git -C "$WT" commit -m "docs(v159): ER19 gate green -- full suite, frontend, complexity

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task ER20: Pre-close-out `/panel` (execution-specialist, compliance-reviewer, risk-manager)

**Model:** sonnet — dispatches three reviewers serially and sorts their findings into fixed buckets; each `BLOCKING` fix on v159's own diff is a small, test-backed edit in the file the finding cites.

**Files:**
- Modify: `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md` (`## Progress`: the merged findings)
- Modify: `.superpowers/sdd/progress.md` (one line per rejected or deferred `BLOCKING` finding, per the `panel` skill's Step 5)
- Modify, only if a finding is applied: the v159 file that finding cites (never a file outside this plan's diff, and never the v160 spec)

**Interfaces:**
- Consumes: ER19's green gate; the roles `execution-specialist` (opus), `compliance-reviewer` (opus) from ER1 and `risk-manager` (sonnet, existing), with their reviewer models in the `skills-tools.md` roles table; the `expert-reviewer` roster of thirteen from ER3.
- Produces: the merged panel list under `## Progress`, each line `<role>: <one line> -- applied (<sha>)`, `-- rejected: <why>`, or `-- v160 spec: recorded for the partner`. ER21 reads it: no `BLOCKING` line may remain without one of those three endings.

**Why these three seats, not the spec's `**Panel:**` line.** The spec's `**Panel:**` line (staff-engineer, risk-manager, financial-advisor) was its *spec* review, run before the new seats existed. Spec § Rollout names the pre-close-out panel: `execution-specialist, compliance-reviewer, risk-manager`. The new seats review the guard and the publication wording they were created for, and `risk-manager` re-checks that its blocking findings landed in v160's spec. ER21's `/close-out` Step 2 ("Clear the panel") is satisfied by this task and is not run a second time.

- [ ] **Step 1: Fix the target**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" rev-parse --short HEAD
git -C "$WT" diff --stat main...HEAD
```

The target is the range `main...2026-10-11-v159-expert-roles-etoro-guard-ops-rituals` plus the ER19 gate line under `## Progress`. Note the HEAD sha; every finding is judged against it.

- [ ] **Step 2: Run `/panel`, serially**

Invoke the `panel` skill: `/panel execution-specialist,compliance-reviewer,risk-manager main...2026-10-11-v159-expert-roles-etoro-guard-ops-rituals`. It dispatches `expert-reviewer` once per role, in that order, each with the role's model from the roles table as the `model` override (opus, opus, sonnet), and waits for each to return before the next. Never fan out.

Give each dispatch this focus line after the target (the reviewer still applies its whole checklist):

- `execution-specialist`: "Focus: is there any path to a real-account eToro call that skips both layers? Hook `_rule_etoro_real_account` over MCP, Bash, PowerShell and `.env` Edit/Write/`apply_patch`. `swingbot/core/broker/guard.py:assert_demo` and its AST scan. `save_settings`/preview `_real_money_problem`. `env_set.REFUSED_KEYS`. The typed-date dialog. Also the `order-safety` checklist and the `reconciler` contract against your red flags. Sizing and pre-open checks are v160's by partner decision; flag only that the skills name them as v160's."
- `compliance-reviewer`: "Focus: `docs/claude/compliance-publication.md`. Are the EU/UK/US regimes, paper/demo/real separation, publish-all-or-state-the-filter, and the draft disclosure (marked `draft — partner to approve`) sound? A doubtful point is `needs counsel`, never a ruling, and you do not write final disclosure text."
- `risk-manager`: "Focus: confirm that your blocking findings from v159's spec review landed in v160's spec, `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (read it at `main`'s HEAD). Those findings are risk-manager B1 (heat, correlated heat, `MAX_STOP_LOSS_PCT` at send time), B2 (code-level sizing clamped through `capped_planned_loss_pct`), B3 (stop at order time, stops only tighten), B4 (`ETORO_ACCOUNT_SIZE` + `ETORO_MAX_TRADE_USD`), A7 (rejection reason journalled) and A8 (tests tying order params to the plan), listed in v159's spec § Panel review. Name each one landed / not landed with the v160 line. Also check v159's diff creates no `broker/sizing.py`, `broker/pre_open.py` or v160 setting."

**Known at plan-writing time (2026-10-11), for the risk-manager seat to confirm or clear.** v160's spec on `main` still describes an older v159. Its `**Depends on:**` line and § Sizing name `swingbot/core/planning/broker_guard.py` with `validate_order`, `BrokerOrder`, `OpenBook`, `OrderRejected` and an `ETORO_MAX_TRADE_EUR` setting as v159 § B2 deliverables. Its § Panel review marks risk-manager 1–3 "superseded" by that `validate_order`. Its line 11 says v159's plan amends v160's `**Panel:**` line to add `execution-specialist`. v159 as specced builds none of that: only `broker/guard.py:assert_demo`, with sizing, pre-open, `ETORO_MAX_TRADE_USD` and `ETORO_ACCOUNT_SIZE` assigned to v160, and no task touches v160's spec. If this is still true at ER20, each mismatch is a **recorded finding for the partner, not a v159 code change** (controller decision, 2026-10-11): v160's spec belongs to another session.

- [ ] **Step 3: Sort every surviving finding into one bucket**

Apply the `panel` skill's Step 4 merge (drop uncited findings, merge duplicates keeping the stricter tag, `BLOCKING` first). Then, for each finding:

| The finding cites… | Do |
|---|---|
| a file in v159's diff, and it is `BLOCKING` | Fix it on the branch: write the failing test first where the fix is code, make the smallest change, run `python "$WT/scripts/dev/testrun.py" file <that test file>`, and commit `fix(v159): <finding> (panel: <role>)`. Line ends `-- applied (<sha>)`. |
| a file in v159's diff, `ADVISORY` | Apply it if it is a wording or one-line fix inside the plan's scope (same commit rules); otherwise `-- rejected: <why>`. |
| v160's spec, or v160's not-yet-built code | Never edit v160. Line ends `-- v160 spec: recorded for the partner`. |
| anything that asks to add order-risk code (`sizing.py`, `pre_open.py`, `ETORO_MAX_TRADE_USD`, `ETORO_ACCOUNT_SIZE`) to v159 | `-- rejected: order-risk checks are v160's (partner, 2026-10-11)`. |
| the draft disclosure's final wording | `-- rejected: final disclosure is the partner's; the doc stays marked draft`. |

A fix that would need a new design (for example a different unlock path) is not applied here: stop and report `BLOCKED: <role> BLOCKING finding needs a partner decision -- <one line>`.

If any fix commit landed, re-run the narrow test files it touched, then `python "$WT/scripts/dev/testrun.py" changed`. A fix to `.py` code also re-runs `python -m radon cc -s -n C <file>` (every function below 15).

- [ ] **Step 4: Record**

Under `## Progress` in the worktree copy of the index, append:

```markdown
- ER20 pre-close-out panel (<YYYY-MM-DD>, over <HEAD sha>): execution-specialist (opus), compliance-reviewer (opus), risk-manager (sonnet).
  - <role> BLOCKING: <one line> -- applied (<sha>) | rejected: <why> | v160 spec: recorded for the partner
  - <role> ADVISORY: <one line> -- ...
  - <role>: CLEAN    (for a seat that returned no findings)
```

with one line per merged finding. Append one line per `BLOCKING` finding that is not `applied` to `E:/Documents/Private/Projects/Discord-Bot/.superpowers/sdd/progress.md` (append only; never read it whole, `tail` it): `v159 ER20 <role> BLOCKING <one line> -- <rejected: why | v160 spec: recorded for the partner>`.

- [ ] **Step 5: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$WT" add docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md
git -C "$WT" commit -m "docs(v159): ER20 pre-close-out panel recorded

execution-specialist, compliance-reviewer, risk-manager over
main...2026-10-11-v159-expert-roles-etoro-guard-ops-rituals. BLOCKING
findings on v159's diff applied; findings against v160's spec recorded
for the partner, not changed here.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Hand back to the controller, verbatim, every line ending `v160 spec: recorded for the partner`. The controller puts them to the partner (one `AskUserQuestion` per decision). They do not block ER21: v159's own diff is clean once every v159-diff `BLOCKING` line is `applied` or `rejected`.

### Task ER21: `/close-out` into `plans/etoro-migration/implemented/`

**Model:** haiku — the `close-out` ritual's fixed steps with every path, version line and commit message spelled out; the one judgement (is the merge clean) stops rather than decides.

**Files:**
- Modify: `VERSION.json` (`bot` patch + `bot_updated`, then `ui` patch + `ui_updated`)
- Modify: `swingbot/admin/version_history.json` (regenerated twice, once after each release commit)
- Move: `docs/superpowers/plans/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_{0-index,1-expert-roles,2-hook-and-code-guard,2b-server-signoff,3-unlock-ui-order-safety-soak,4-rituals-and-close-out}.md` → `docs/superpowers/plans/etoro-migration/implemented/`
- Move: `docs/superpowers/specs/etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md` → `docs/superpowers/specs/etoro-migration/implemented/`

**Interfaces:**
- Consumes: ER19's green gate and ER20's panel record (no `BLOCKING` line on v159's diff without `applied` or `rejected`); the plan header `**Bump:** bot patch + ui patch`, `**Edge:** none (integrity)`.
- Produces: the closed plan. The SessionStart hook stops listing it, because `implemented/` inside a program folder is skipped (`docs/claude/document-lifecycle.md` § Program folders). v160's eToro-code tasks may start once this merge is on `main` (v159 spec § Risks).

Invoke the `close-out` skill; the steps below are its checklist made concrete for this plan. **Its Step 2 ("Clear the panel") is ER20**, with the seats spec § Rollout names. Do not run `/panel` again.

- [ ] **Step 1: Merge the branch into `main`**

Load the `worktree-lifecycle` skill first: another session may be working on `main`.

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
BR=2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$MAIN" fetch --quiet
git -C "$MAIN" status --short -- docs/superpowers/plans/etoro-migration docs/superpowers/specs/etoro-migration VERSION.json swingbot/admin/version_history.json
git -C "$MAIN" log --oneline -1 origin/main
git -C "$MAIN" log --oneline -1 main
git -C "$MAIN" merge --no-ff "$BR" -m "Merge branch '$BR'"
```

Expected: the `status` line prints nothing for those paths. The uncommitted `.agents/skills/*` line-ending noise elsewhere on `main` is not touched. `main` equals or is ahead of `origin/main`, and the merge completes without conflicts. **A conflict, or `main` behind `origin/main`: stop and report `BLOCKED: merge of v159 needs a decision -- <what>`.** Never resolve a conflict in another session's files by choosing a side. After a clean merge no full-suite run follows (`close-out` § The gate). Run only `python "$MAIN/scripts/dev/testrun.py" changed --dry-run` to confirm it selects nothing unexpected.

- [ ] **Step 2: Resolve the bump from disk**

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
cat "$MAIN/VERSION.json"
```

Read the current `bot` and `ui` values from this output, never from this plan (when it was written they were `bot` 2.4.0 and `ui` 1.22.1, but another release may have landed since). `Bump: bot patch + ui patch` increments the **third** integer of each line by one (`docs/claude/working-conventions.md` § Each part is an integer, not a digit). Check the prediction too: bot patch (new settings, a guard module the bot imports, a server-side save check) and ui patch (the typed-date dialog) both shipped. If either did not, amend the header per `close-out` Step 5.

- [ ] **Step 3: `bot` release, then regenerate**

Edit `$MAIN/VERSION.json`: set `"bot"` to the incremented value and `"bot_updated"` to now in UTC, format `YYYY-MM-DD HH-MM-SS`. Leave both `ui` keys untouched.

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" add VERSION.json
git -C "$MAIN" commit -m "release(bot): <new bot version> -- demo-only eToro guard: broker/guard.assert_demo, real-money unlock only via the admin UI (v159)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python "$MAIN/scripts/dev/build_version_matrix.py"
git -C "$MAIN" add swingbot/admin/version_history.json
git -C "$MAIN" commit -m "chore(bot): <new bot version> -- demo-only eToro guard: broker/guard.assert_demo, real-money unlock only via the admin UI (v159)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: `ui` release, then regenerate**

Edit `$MAIN/VERSION.json`: set `"ui"` to the incremented value and `"ui_updated"` to now (UTC, same format). Leave both `bot` keys as Step 3 left them.

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" add VERSION.json
git -C "$MAIN" commit -m "release(ui): <new ui version> -- typed-date confirm before the real-money unlock on the Settings page (v159)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python "$MAIN/scripts/dev/build_version_matrix.py"
git -C "$MAIN" add swingbot/admin/version_history.json
git -C "$MAIN" commit -m "chore(ui): <new ui version> -- typed-date confirm before the real-money unlock on the Settings page (v159)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python "$MAIN/scripts/dev/testrun.py" file tests/scripts/test_build_version_matrix.py
```

Expected: the last command `0 failed`. The suite before the bump could not see this mismatch (`working-conventions.md` § How), so this one file is the check.

- [ ] **Step 5: Move the plan and the spec into the program folder's `implemented/`**

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
PL=docs/superpowers/plans/etoro-migration
SP=docs/superpowers/specs/etoro-migration
for part in 0-index 1-expert-roles 2-hook-and-code-guard 2b-server-signoff 3-unlock-ui-order-safety-soak 4-rituals-and-close-out; do
  git -C "$MAIN" mv "$PL/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_$part.md" "$PL/implemented/"
done
git -C "$MAIN" mv "$SP/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals-design.md" "$SP/implemented/"
git -C "$MAIN" grep -n "etoro-migration/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals" -- docs AGENTS.md CLAUDE.md .claude
```

Destination is **`etoro-migration/implemented/`**, never the top-level `plans/implemented/` or `specs/implemented/` (`docs/claude/document-lifecycle.md` § Program folders). The spec moves too: v160's plan builds from v160's own spec, which only cites v159 by section, so nothing live builds from v159's spec.

The final `grep` lists remaining references to the old paths:

- **Inside the six moved plan files and the moved spec:** update each to the new location. The part headers' relative spec link `../../specs/etoro-migration/...` becomes `../../../specs/etoro-migration/implemented/...`; `grep -n "^### Task\|# Phase"` must still list every task afterwards.
- **In any other file:** do not edit it here (v160's spec belongs to another session). List each `file:line` in the hand-back for the controller.

- [ ] **Step 6: Commit the move**

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$MAIN" status --short -- docs/superpowers
git -C "$MAIN" commit -m "docs(v159): close out -- plan and spec to etoro-migration/implemented/

Bump: bot patch + ui patch applied (release/chore pairs above). Pre-close-out
panel (execution-specialist, compliance-reviewer, risk-manager) recorded in
the index's Progress; findings against v160's spec handed to the partner.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python "$MAIN/scripts/dev/plan_lint.py" "$MAIN/docs/superpowers/plans/etoro-migration/implemented/2026-10-11-v159-expert-roles-etoro-guard-ops-rituals_0-index.md"
```

Expected: status before the commit shows only the seven renames (plus any link fixes inside them); `plan_lint` passes on the moved plan.

- [ ] **Step 7: Remove the worktree and its branch**

This closed to `implemented/`, so the worktree goes. The branch name contains neither `backup` nor `stable-`; still run the git-safety check first (`docs/claude/git-safety.md`):

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
BR=2026-10-11-v159-expert-roles-etoro-guard-ops-rituals
git -C "$MAIN" rev-list --count "main..$BR"
git -C "$MAIN" worktree remove "$MAIN/.claude/worktrees/$BR"
git -C "$MAIN" branch -d "$BR"
git -C "$MAIN" worktree list
```

Expected: the count is `0` (anything else: stop, do not delete; report it). `branch -d` (never `-D`) succeeds; `worktree list` no longer shows the v159 worktree. Do not push; the controller decides when `main` goes to `origin`.

- [ ] **Step 8: Hand back**

Report to the controller: the two new version numbers; the commit shas of the merge, the four release/chore commits and the move; every `v160 spec: recorded for the partner` line from ER20; and any out-of-plan file still referencing v159's old paths (Step 5). The close-out gate holds when no unresolved `BLOCKING` panel line exists on v159's diff, `VERSION.json`, both regenerations and the moved documents are in the log, and the worktree is gone.
