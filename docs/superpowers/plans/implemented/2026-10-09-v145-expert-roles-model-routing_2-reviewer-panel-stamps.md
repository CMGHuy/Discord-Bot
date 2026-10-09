# v145 Expert role skills, review panels and per-task model routing: Implementation Plan, part 2 — reviewer, panel and stamps

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Header, global constraints, file map and parallelisation: `2026-10-09-v145-expert-roles-model-routing_0-index.md`.

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`](../specs/2026-10-09-v145-expert-roles-model-routing.md)

# Phase 2 — Reviewer agent and panel

### Task V145-4: The expert-reviewer agent, and task-reviewer preloads senior-engineer

**Model:** sonnet — a new agent plus agent-shape test changes; the content is given, but the read-only boundary and return shape need care.

**Files:**
- Create: `.claude/agents/expert-reviewer.md`
- Modify: `.claude/agents/task-reviewer.md` (frontmatter `skills:` line 6; one sentence after the `## Order` list)
- Modify: `tests/hooks/test_agent_shape.py` (`EXPECTED`; one new test and constant at the end)
- Modify: `AGENTS.md` (the role-agents paragraph ending `and \`plan-writer\` (a plan from an approved spec).`)
- Generated: `.codex/agents/expert-reviewer.toml`, `.codex/agents/task-reviewer.toml`

**Interfaces:**
- Consumes: the nine role skills (V145-1..3), in particular `senior-engineer` (V145-3).
- Produces: agent `expert-reviewer` — input `role=<name>` plus target paths or a git range; output starts `ROLE: <role>` then `VERDICT: CLEAN | FINDINGS | UNKNOWN ROLE: … | BLOCKED: …`, then numbered `[BLOCKING|ADVISORY] <citation> -- <sentence>` lines. `/panel` (V145-5) dispatches it with the role's model as the `model` override.

- [ ] **Step 1: Write the failing agent-shape tests**

In `tests/hooks/test_agent_shape.py`, change the `task-reviewer` entry of `EXPECTED` to:

```python
    "task-reviewer": {
        "model": "sonnet",
        "skills": {"no-lookahead", "senior-engineer"},
    },
```

add this entry after the `backtest-runner` entry, inside `EXPECTED`:

```python
    # v145: one read-only reviewer parameterised by role. It loads the role
    # skill at run time, so it preloads none.
    "expert-reviewer": {
        "model": "sonnet",
        "skills": set(),
    },
```

and append at the end of the file:

```python
# v145: the nine role skills expert-reviewer must name (spec § 1).
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer")


def test_expert_reviewer_is_read_only_and_knows_every_role():
    meta, body = _read_agent("expert-reviewer")
    tools = {t.strip() for t in meta.get("tools", "").split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash", "Skill"}
    missing = [role for role in EXPERT_ROLES if f"`{role}`" not in body]
    assert not missing, missing
    for word in ("BLOCKING", "ADVISORY", "CLEAN", "UNKNOWN ROLE"):
        assert word in body, word
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py`
Expected: FAIL — `FileNotFoundError` for `.claude/agents/expert-reviewer.md`, and `test_role_agent_pins_model_and_skills[task-reviewer]` (skills `{'no-lookahead'}` != expected).

- [ ] **Step 3: Write `.claude/agents/expert-reviewer.md`**

Exactly:

````markdown
---
name: expert-reviewer
description: Reviews a spec, plan, diff or backtest result through ONE expert role skill (role=<name>; the nine roles are listed in docs/claude/skills-tools.md under Expert roles) and returns numbered BLOCKING or ADVISORY findings, each with a citation, or CLEAN. Read-only. Dispatched by /panel, one role per dispatch, with that role's reviewer model as the override.
tools: Read, Grep, Glob, Bash, Skill
model: sonnet
---

You review through **one** expert role. Your prompt names `role=<name>` and
one or more targets: file paths, or a git range such as `main...<branch>`
(with the worktree path when the range lives there). You change nothing.

## Roles

Valid roles, each a skill at `.claude/skills/<role>/SKILL.md`:
`quant-researcher`, `staff-engineer`, `veteran-trader`, `risk-manager`,
`financial-advisor`, `technical-analyst`, `fundamental-analyst`,
`quant-engineer`, `senior-engineer`.

A role not on this list, or one whose `SKILL.md` is missing, ends the review:
return `VERDICT: UNKNOWN ROLE` naming the valid roles. Never improvise a role
and never substitute the nearest one.

## Order

1. **Load the role.** Invoke the skill `<role>`; if the Skill tool cannot load
   it, Read `.claude/skills/<role>/SKILL.md`. Its Lens, Checklist, Red flags
   and Out of scope are your whole brief.
2. **Read the targets.** For a git range use read-only git only:
   `git diff`, `git log`, `git show`, `git -C <worktree> diff <range>`. Never
   run `checkout`, `commit`, `reset`, `stash`, `push`, `merge`, `rebase` or
   any command that writes, and never run a backtest or the test suite.
3. **Walk the checklist** item by item against the targets. An item that does
   not apply is skipped silently, not reported.
4. **Tag** each finding `BLOCKING` when it matches one of the role's red flags,
   otherwise `ADVISORY`. Something the role's Out of scope hands to another
   role is not yours: at most one `ADVISORY` line naming that role.

## Evidence rule

Every finding cites `file:line`, a git range, or a doc section
(`docs/claude/<doc>.md § <heading>`). A finding you cannot cite is not a
finding; the controller drops it. Quote no pooled figure you did not
re-derive (`pooled-numbers`). You raise findings; you never decide, and you
never lower a gate.

## Return shape

```
ROLE: <role>
VERDICT: CLEAN | FINDINGS | UNKNOWN ROLE: <given> -- valid: <the nine roles> | BLOCKED: <one question>
1. [BLOCKING|ADVISORY] <file:line | git range | doc § section> -- <one sentence>
   why: <the checklist item or red flag it breaks>
...
```

At most 12 findings, `BLOCKING` first. `CLEAN` means you walked the whole
checklist and found nothing citable.
````

- [ ] **Step 4: Make task-reviewer preload senior-engineer**

In `.claude/agents/task-reviewer.md`, change the frontmatter line `skills: [no-lookahead]` to:

```yaml
skills: [no-lookahead, senior-engineer]
```

and insert this paragraph directly after the four-item `## Order` list (before `Do not report style preferences, …`):

```markdown
The preloaded `senior-engineer` skill is the checklist for steps 2 to 4; a
diff that matches one of its red flags is always a finding. You stay on
sonnet whatever model implemented the task.
```

- [ ] **Step 5: Mirror to Codex**

In `AGENTS.md`, replace `from a \`task-brief\`), and \`plan-writer\` (a plan from an approved spec).` with:

```markdown
from a `task-brief`), `plan-writer` (a plan from an approved spec), and
`expert-reviewer` (one expert role's read-only review, `role=<name>`, cited
`BLOCKING`/`ADVISORY` findings or `CLEAN`; dispatched by `panel` one role at a
time).
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed` (agent shape, Codex mirror — including `test_generated_agent_toml_parses_and_keeps_the_prompt` for the new TOML — and the rest of `tests/hooks/`).

- [ ] **Step 7: Commit**

```bash
git add .claude/agents/expert-reviewer.md .claude/agents/task-reviewer.md tests/hooks/test_agent_shape.py .codex/agents AGENTS.md
git commit -m "feat(v145): expert-reviewer agent; task-reviewer preloads senior-engineer"
```

### Task V145-5: The /panel skill

**Model:** sonnet — a new ritual skill with tier registration and a content test; text given verbatim.

**Files:**
- Create: `.claude/skills/panel/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_2` line 23, `MODEL_RUN_RITUALS` line 26)
- Modify: `tests/hooks/test_role_skills.py` (one constant and one test, appended)
- Modify: `AGENTS.md` (the rituals paragraph in `## Skills: the same ones Claude uses`)
- Generated: `.agents/skills/panel/SKILL.md`

**Interfaces:**
- Consumes: `expert-reviewer` (V145-4); the roles table in `docs/claude/skills-tools.md` § Expert roles (V145-1..3); `_body` in `tests/hooks/test_role_skills.py` (V145-1).
- Produces: skill `panel`, invoked as `/panel <role>[,<role>…] <target>` or by Claude itself. Spec-review mode appends a `## Panel review` section to the spec; pre-close-out mode is what `close-out` Step 2 runs (V145-8).

- [ ] **Step 1: Write the failing tests**

In `tests/hooks/test_skill_shape.py`, change `TIER_2` and `MODEL_RUN_RITUALS` to:

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel"}        # each ritual task appends its own name
```

```python
MODEL_RUN_RITUALS = {"close-out", "new-doc", "panel"}
```

Append to `tests/hooks/test_role_skills.py`:

```python
PANEL_PHRASES = ("expert-reviewer", "serially", "skills-tools.md", "BLOCKING",
                 "## Panel review", "applied", "rejected: <why>", "/close-out")


def test_panel_dispatches_the_expert_reviewer_serially():
    body = _body("panel")
    missing = [phrase for phrase in PANEL_PHRASES if phrase not in body]
    assert not missing, missing
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: FAIL — `test_every_skill_is_registered_in_exactly_one_tier`, `test_model_run_rituals_are_invocable_and_say_when` (no `panel` skill) and `test_panel_dispatches_the_expert_reviewer_serially` (`FileNotFoundError`).

- [ ] **Step 3: Write `.claude/skills/panel/SKILL.md`**

Exactly (51 lines; no `## Lens`, so `lens_skills()` does not count it as a role):

```markdown
---
name: panel
description: Dispatch expert role reviewers (/panel role[,role...] target) over a spec, plan, diff or backtest result, one at a time through the expert-reviewer agent, and merge their findings. Run as /panel, or by Claude itself right after committing a spec that carries a Panel header line, and before /close-out of a plan built from such a spec.
---

# Expert panel

## Step 1 — Read the authority

`docs/claude/skills-tools.md` § Expert roles holds the roster and each role's
reviewer model. `docs/claude/document-conventions.md` § The header block holds
the `**Panel:**` line. This skill is the checklist; the reasoning lives there.

## Step 2 — Resolve the roles and the target

Roles come from the argument, or from the spec's `**Panel:**` line when Claude
runs this itself. Every role must be a row of the roles table; an unknown role
stops the panel and names the valid ones -- never substitute a near match. The
target is one or more paths, or a git range (`main...<branch>`).

## Step 3 — Dispatch serially

For each role, in the order given, dispatch the `expert-reviewer` agent with
`role=<role>`, the target, and that role's reviewer model from the roles table
as the `model` override. Wait for it to return before dispatching the next:
serially, one at a time (`skills-tools.md`). Never fan out, even for three
roles.

## Step 4 — Merge

Drop every finding that cites no `file:line`, git range or doc section. Merge
duplicates across roles, keeping the stricter tag. List `BLOCKING` first, then
`ADVISORY`, each line naming its role. A role that returned `CLEAN` is listed
as clean, not omitted.

## Step 5 — Record the outcome

- **Spec review** -- after the spec is committed, before the partner reviews
  it. Revise the spec for each finding you accept, then append a
  `## Panel review` section listing every finding as `<role>: <one line> --
  applied` or `-- rejected: <why>`. Commit on `main`.
- **Pre-close-out** -- the plan's full diff (`main...<branch>`, or
  `<merge>^1...<branch>` once merged) and its recorded results. An unresolved
  `BLOCKING` finding stops `/close-out`: fix it on the branch, or record it in
  `.superpowers/sdd/progress.md` as `rejected: <why>`.
- **On demand** -- return the merged list; record nothing unless asked.

## The gate

Every role returned; every surviving finding cites evidence; every `BLOCKING`
finding is applied or rejected with a reason before the step it guards.
```

- [ ] **Step 4: Mirror to Codex**

In `AGENTS.md`, replace `\`close-out\` once a plan's final full-suite task is green. Skill text names Claude tools` with:

```markdown
`close-out` once a plan's final full-suite task is green. `panel` (dispatch
expert role reviewers one at a time through `expert-reviewer` and merge their
findings) may also run implicitly: right after committing a spec with a
`**Panel:**` line, and before `close-out` of a plan built from one. Skill text names Claude tools
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.` (`panel` is not slash-only, so no `agents/openai.yaml` is generated for it.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/panel tests/hooks/test_skill_shape.py tests/hooks/test_role_skills.py .agents/skills AGENTS.md
git commit -m "feat(v145): /panel ritual dispatches expert reviewers serially and merges findings"
```

# Phase 3 — Header stamps

### Task V145-6: The Panel: spec header — test, conventions, select_tests routing

**Model:** sonnet — a new test module written test-first, plus a `DATA_READERS` row that `tests/dev/test_select_tests.py` checks.

**Files:**
- Create: `tests/hooks/test_spec_panel_header.py`
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`, the `docs/superpowers/specs/` row near line 266)
- Modify: `docs/claude/document-conventions.md` (new `**\`Panel:\`**` block directly after the `**\`Screen:\`**` block, before `**\`## Parallelisation\`**` — its own section, below.`)
- Modify: `AGENTS.md` (after the line `` `tests/hooks/test_spec_screen_header.py` enforces the line.``)

**Interfaces:**
- Consumes: the nine role skills (a role skill is a `SKILL.md` declaring `## Lens`, the same rule as `lens_skills()` in `tests/hooks/test_role_skills.py`); the `panel` skill (V145-5) named in the conventions text.
- Produces: `tests/hooks/test_spec_panel_header.py` with `LAST_EXEMPT = 145`, `panel_problems(text, *, roles) -> list[str]`, `role_skills(skills_dir) -> set[str]`, `checked_specs(specs_dir) -> list[Path]`. The default-panel table in `document-conventions.md` that `/new-doc` (V145-7) points at.

- [ ] **Step 1: Write the test module**

Create `tests/hooks/test_spec_panel_header.py` with exactly:

```python
"""v145 § 3: every spec numbered v146 or above carries a **Panel:** line
directly below **Screen:**, naming one to three expert role skills.

A role skill is a `.claude/skills/<role>/SKILL.md` that declares `## Lens`
(tests/hooks/test_role_skills.py pins the roster). v145 and earlier are
exempt by number. A split spec carries the line in its _0-index part. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "docs/superpowers/specs"
SKILLS_DIR = ROOT / ".claude/skills"
LAST_EXEMPT = 145
MAX_ROLES = 3
PANEL = "**Panel:**"
SCREEN = "**Screen:**"

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_PART = re.compile(r"_(\d+)[a-z]?(?:-[^.]*)?\.md$")


def spec_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def carries_header(path: Path) -> bool:
    part = _PART.search(path.name)
    return part is None or part.group(1) == "0"


def checked_specs(specs_dir: Path = SPECS_DIR) -> list:
    return sorted(p for p in Path(specs_dir).rglob("*.md")
                  if (spec_number(p) or 0) > LAST_EXEMPT and carries_header(p))


def role_skills(skills_dir: Path = SKILLS_DIR) -> set:
    return {p.parent.name for p in Path(skills_dir).glob("*/SKILL.md")
            if "\n## Lens\n" in p.read_text(encoding="utf-8").replace("\r\n", "\n")}


def panel_roles(line: str) -> list:
    value = line[len(PANEL):]
    return [name.strip().strip("`") for name in value.split(",") if name.strip()]


def panel_problems(text: str, *, roles: set) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    at = next((i for i, line in enumerate(lines) if line.startswith(PANEL)), None)
    if at is None:
        return [f"missing {PANEL} line"]
    if at == 0 or not lines[at - 1].startswith(SCREEN):
        return [f"{PANEL} is not directly below {SCREEN}"]
    names = panel_roles(lines[at])
    if not 1 <= len(names) <= MAX_ROLES:
        return [f"{PANEL} names {len(names)} roles; 1 to {MAX_ROLES} allowed"]
    return [f"`{name}` is not a role skill" for name in names if name not in roles]


# -- unit tests -------------------------------------------------------------

ROLES = {"quant-researcher", "risk-manager", "veteran-trader", "staff-engineer"}


def _spec(panel=None, *, below_screen=True):
    lines = ["# v999 demo", "", "**Bump:** none", "**Edge:** none (integrity)"]
    if panel is not None and not below_screen:
        lines.append(f"{PANEL} {panel}")
    lines.append(f"{SCREEN} exempt (integrity)")
    if panel is not None and below_screen:
        lines.append(f"{PANEL} {panel}")
    return "\n".join(lines + ["", "## Why", "text"]) + "\n"


def test_one_to_three_known_roles_pass():
    assert panel_problems(_spec("staff-engineer"), roles=ROLES) == []
    text = _spec("quant-researcher, `risk-manager`, veteran-trader")
    assert panel_problems(text, roles=ROLES) == []


def test_a_missing_panel_line_fails():
    assert panel_problems(_spec(), roles=ROLES) == ["missing **Panel:** line"]


def test_a_panel_line_not_directly_below_screen_fails():
    problems = panel_problems(_spec("staff-engineer", below_screen=False), roles=ROLES)
    assert problems == ["**Panel:** is not directly below **Screen:**"]


def test_four_roles_fail():
    text = _spec("quant-researcher, risk-manager, veteran-trader, staff-engineer")
    assert "names 4 roles" in panel_problems(text, roles=ROLES)[0]


def test_an_empty_panel_fails():
    assert "names 0 roles" in panel_problems(_spec(""), roles=ROLES)[0]


def test_an_unknown_role_fails():
    problems = panel_problems(_spec("staff-engineer, gate"), roles=ROLES)
    assert problems == ["`gate` is not a role skill"]


def test_crlf_text_is_read_like_lf():
    assert panel_problems(_spec("staff-engineer").replace("\n", "\r\n"), roles=ROLES) == []


def test_role_skills_are_the_skills_that_declare_a_lens(tmp_path):
    for name, body in (("risk-manager", "# x\n\n## Lens\n\ntext\n"),
                       ("gate", "# x\n\n## Step 1\n\ntext\n")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}",
                                                  encoding="utf-8")
    assert role_skills(tmp_path) == {"risk-manager"}


def test_exempt_and_non_index_specs_are_skipped(tmp_path):
    names = ["2026-10-09-v145-roles.md", "2026-10-10-v146-a-design.md",
             "implemented/2026-10-11-v147-b-design.md",
             "2026-10-12-v148-c_0-index.md", "2026-10-12-v148-c_1-detail.md"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert {p.name for p in checked_specs(tmp_path)} == {
        "2026-10-10-v146-a-design.md", "2026-10-11-v147-b-design.md",
        "2026-10-12-v148-c_0-index.md"}


# -- the repository gate ----------------------------------------------------

def test_every_spec_above_v145_carries_a_valid_panel_line():
    roles = role_skills()
    problems = {p.relative_to(ROOT).as_posix():
                panel_problems(p.read_text(encoding="utf-8"), roles=roles)
                for p in checked_specs()}
    assert {path: found for path, found in problems.items() if found} == {}
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/hooks/test_spec_panel_header.py`
Expected: PASS, 10 tests. Like `test_spec_screen_header.py`, this module holds its checking functions beside their unit tests, so the unit tests are the specification of `panel_problems` and there is no separate red run. The repository gate passes vacuously: no spec numbered above v145 exists yet. If one has landed on `main` meanwhile without a `**Panel:**` line, the gate fails here: stop and ask the partner (amend that spec, or agree it predates the rule) rather than raising `LAST_EXEMPT`.

- [ ] **Step 3: Route spec edits to the new test**

`docs/superpowers/specs/` already has a `DATA_READERS` row, so `tests/dev/test_select_tests.py` passes either way; the edit makes a spec edit also select the new test under `testrun.py changed`.

In `scripts/dev/select_tests.py`, change the specs row of `DATA_READERS` from:

```python
    # Every spec past v140 must carry a valid **Screen:** header line.
    ("docs/superpowers/specs/", ("tests/hooks/test_spec_screen_header.py",)),
```

to:

```python
    # Every spec past v140 must carry a valid **Screen:** header line, and
    # every spec past v145 a valid **Panel:** line.
    ("docs/superpowers/specs/", ("tests/hooks/test_spec_screen_header.py",
                                 "tests/hooks/test_spec_panel_header.py")),
```

- [ ] **Step 4: Document the header**

In `docs/claude/document-conventions.md`, insert directly after the paragraph ending ``Why the screen exists, its pass rule and its one-shot discipline: `backtest-methodology.md` § Stage −2.`` (and before ``**`## Parallelisation`** — its own section, below.``):

```markdown
**`Panel:`** — specs only, and only specs numbered **v146 or above** (v145 and
earlier are exempt by number and never retrofitted). It sits directly under
`Screen:` and names one to three expert role skills (`skills-tools.md`
§ Expert roles), comma-separated:
`**Panel:** quant-researcher, veteran-trader, technical-analyst`. `/new-doc`
suggests the default for the spec's subject; the author may override it, and
the header records the final choice.

| Spec is about… | Default panel |
|---|---|
| New entry strategy or filter (`Edge: expectancy`) | quant-researcher, veteran-trader, technical-analyst |
| Exits, sizing, stops (`Edge: harvest`) | risk-manager, veteran-trader, quant-researcher |
| Alert volume or cadence (`Edge: volume`) | veteran-trader, financial-advisor, risk-manager |
| Earnings, catalysts, sector filters | fundamental-analyst, quant-researcher, risk-manager |
| Infra, schema, ops (`Edge: none (integrity)`) | staff-engineer, quant-engineer |
| Admin UI | staff-engineer, financial-advisor |

The panel runs through the `panel` skill at two fixed points. **Spec review:**
after the spec is committed and before the partner reviews it, the roles run
serially; Opus merges their findings, revises the spec, and records each
finding's outcome (`applied` / `rejected: <why>`) in a `## Panel review`
section of the spec. **Pre-close-out:** the same panel reviews the plan's full
diff (`main...<branch>`) and its recorded results, and an unresolved
`BLOCKING` finding stops `/close-out`. Any other time, `/panel` runs on demand.
`tests/hooks/test_spec_panel_header.py` fails a spec whose line is missing, is
not directly below `Screen:`, names fewer than one or more than three roles,
or names a skill that declares no `## Lens`. A split spec carries the line in
its `_0-index` part.
```

- [ ] **Step 5: Mirror to Codex**

In `AGENTS.md`, insert directly after the line `` `tests/hooks/test_spec_screen_header.py` enforces the line.`` (same paragraph, new sentences):

```markdown
Specs numbered v146 or above also carry `**Panel:**` directly below
`**Screen:**`: one to three expert role skills (defaults by subject in
`document-conventions.md`), run through `panel` after the spec is committed
and again over the plan's diff before close-out, where an unresolved
`BLOCKING` finding stops the close. `tests/hooks/test_spec_panel_header.py`
enforces it.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/` then `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: both PASS, `0 failed`. Then `python -m radon cc -s -n C tests/hooks/test_spec_panel_header.py scripts/dev/select_tests.py` lists nothing the diff created or made worse.

- [ ] **Step 7: Commit**

```bash
git add tests/hooks/test_spec_panel_header.py scripts/dev/select_tests.py docs/claude/document-conventions.md AGENTS.md
git commit -m "feat(v145): Panel spec header from v146, enforced by test_spec_panel_header"
```

### Task V145-7: Model routing — the rubric doc, the Model: stamp test, plan-writer, new-doc and task-brief

**Model:** sonnet — a new test module written test-first, a new reference doc, and three setup files that must stay in step with it.

**Files:**
- Create: `docs/claude/model-routing.md`
- Create: `tests/hooks/test_plan_model_stamp.py`
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`: new `docs/superpowers/plans/` row)
- Modify: `docs/claude/document-conventions.md` (new `**\`Model:\`**` block directly after the `**\`Panel:\`**` block V145-6 added)
- Modify: `.claude/agents/plan-writer.md` (one bullet in `## Conventions`)
- Modify: `.claude/skills/new-doc/SKILL.md` (Step 3 and Step 7; full replacement given)
- Modify: `.claude/skills/task-brief/SKILL.md` (Step 5)
- Modify: `AGENTS.md` (reference-doc list; `## Specs, plans and versioning`)
- Generated: `.codex/agents/plan-writer.toml`, `.agents/skills/new-doc/SKILL.md`, `.agents/skills/task-brief/SKILL.md`

**Interfaces:**
- Consumes: the default-panel table and `**Panel:**` rules in `document-conventions.md` (V145-6), which the new `/new-doc` text points at; `expert-reviewer` and `/panel` (named in `model-routing.md`).
- Produces: `docs/claude/model-routing.md` (§ The stamp, § The rubric, § The escalation ladder, § Retuning the rubric) that V145-8's `skills-tools.md`, `CLAUDE.md` and `AGENTS.md` text points at; `tests/hooks/test_plan_model_stamp.py` with `LAST_EXEMPT = 145`, `stamp_problems(text) -> list[str]`, `checked_plans(plans_dir) -> list[Path]`, `task_headings(lines) -> list[int]`.

- [ ] **Step 1: Write the test module**

Create `tests/hooks/test_plan_model_stamp.py` with exactly:

```python
"""v145 § 4: in every plan numbered v146 or above, the first non-blank line
under each `### Task` heading is `**Model:** <haiku|sonnet|opus> — <reason>`.

The controller passes that tier as the `model` override when it dispatches
task-implementer; the rubric is docs/claude/model-routing.md. v145 and earlier
are exempt by number. Every part of a split plan is checked, since tasks live
in the parts. Headings inside fenced code blocks are examples, not tasks. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = ROOT / "docs/superpowers/plans"
LAST_EXEMPT = 145

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_TASK = re.compile(r"^### Task ")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_STAMP = re.compile(r"^\*\*Model:\*\* (haiku|sonnet|opus) (—|--) \S")


def plan_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def checked_plans(plans_dir: Path = PLANS_DIR) -> list:
    return sorted(p for p in Path(plans_dir).rglob("*.md")
                  if (plan_number(p) or 0) > LAST_EXEMPT)


def _fence_after(fence: str | None, marker: str) -> str | None:
    """The open fence after a fence line: a closing marker must use the
    opening character and be at least as long (CommonMark)."""
    if fence is None:
        return marker
    return None if marker[0] == fence[0] and len(marker) >= len(fence) else fence


def task_headings(lines: list) -> list:
    """Indexes of `### Task` lines outside fenced code blocks."""
    found, fence = [], None
    for i, line in enumerate(lines):
        match = _FENCE.match(line)
        if match:
            fence = _fence_after(fence, match.group(1))
        elif fence is None and _TASK.match(line):
            found.append(i)
    return found


def _first_line_after(lines: list, index: int) -> str:
    return next((line for line in lines[index + 1:] if line.strip()), "")


def stamp_problems(text: str) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    return [f"{lines[i].strip()}: first line is not a valid **Model:** stamp"
            for i in task_headings(lines)
            if not _STAMP.match(_first_line_after(lines, i))]


# -- unit tests -------------------------------------------------------------

def _plan(*stamps):
    body = ["# v999 plan", "", "**Bump:** none", ""]
    for n, stamp in enumerate(stamps, 1):
        body += [f"### Task V999-{n}: thing {n}", ""]
        if stamp is not None:
            body.append(stamp)
        body += ["", "- [ ] **Step 1: do it**", ""]
    return "\n".join(body)


def test_every_tier_with_a_reason_passes():
    text = _plan("**Model:** haiku — doc edit", "**Model:** sonnet -- one module",
                 "**Model:** opus — entry signal")
    assert stamp_problems(text) == []


def test_a_missing_stamp_names_the_task():
    problems = stamp_problems(_plan("**Model:** sonnet — fine", None))
    assert problems == ["### Task V999-2: thing 2: first line is not a valid **Model:** stamp"]


def test_an_unknown_tier_fails():
    assert stamp_problems(_plan("**Model:** gpt — no")) != []


def test_a_stamp_without_a_reason_fails():
    assert stamp_problems(_plan("**Model:** opus")) != []


def test_the_stamp_must_be_the_first_line():
    text = "### Task V999-1: x\n\n**Files:** a.py\n**Model:** sonnet — late\n"
    assert stamp_problems(text) != []


def test_task_headings_inside_fences_are_ignored():
    text = _plan("**Model:** haiku — x") + "\n```markdown\n### Task A9: example\n```\n"
    assert stamp_problems(text) == []


def test_a_longer_fence_is_not_closed_by_a_shorter_one():
    text = (_plan("**Model:** haiku — x")
            + "\n````markdown\n```bash\n### Task A9: example\n````\n")
    assert stamp_problems(text) == []


def test_crlf_text_is_read_like_lf():
    assert stamp_problems(_plan("**Model:** haiku — x").replace("\n", "\r\n")) == []


def test_exempt_plans_are_skipped_and_parts_are_checked(tmp_path):
    names = ["2026-10-09-v145-roles_1-skills.md", "2026-10-10-v146-a.md",
             "implemented/2026-10-11-v147-b.md", "2026-10-12-v148-c_0-index.md",
             "2026-10-12-v148-c_1-detail.md", "notes.md"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert {p.name for p in checked_plans(tmp_path)} == {
        "2026-10-10-v146-a.md", "2026-10-11-v147-b.md",
        "2026-10-12-v148-c_0-index.md", "2026-10-12-v148-c_1-detail.md"}


# -- the repository gate ----------------------------------------------------

def test_every_plan_above_v145_stamps_a_model_on_every_task():
    problems = {p.relative_to(ROOT).as_posix(): stamp_problems(p.read_text(encoding="utf-8"))
                for p in checked_plans()}
    assert {path: found for path, found in problems.items() if found} == {}
```

- [ ] **Step 2: Run it, then the inert-path check (fails)**

Run: `python scripts/dev/testrun.py file tests/hooks/test_plan_model_stamp.py`
Expected: PASS, 10 tests (the repository gate passes: no plan above v145 exists; this plan is v145 and exempt). Like `test_spec_screen_header.py`, the module holds its checking functions beside their unit tests, so there is no separate red run for it; the red run is the routing check below.

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: FAIL in `test_no_path_a_test_reads_is_classified_inert`: the new module names `docs/superpowers/plans`, which no `DATA_READERS` row routes, so a plan edit would select nothing.

- [ ] **Step 3: Route plan edits to the new test**

In `scripts/dev/select_tests.py`, insert directly after the specs row of `DATA_READERS` (the one V145-6 edited):

```python
    # Every plan past v145 must stamp **Model:** under each ### Task.
    ("docs/superpowers/plans/", ("tests/hooks/test_plan_model_stamp.py",)),
```

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: PASS, `0 failed`.

- [ ] **Step 4: Write `docs/claude/model-routing.md`**

Exactly:

````markdown
# Model routing — which model implements a plan task

Referenced from the root `CLAUDE.md`. Introduced by v145
(`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`).
Before it, every implementation task ran on `task-implementer`'s pinned
`sonnet`: a version bump and an entry-signal rewiring got the same model.

## The stamp

In every plan numbered **v146 or above**, the first line under each
`### Task` heading is:

```
**Model:** <haiku|sonnet|opus> — <one-clause reason>
```

- `plan-writer` writes it, from the rubric below.
- `/task-brief` copies it to the top of the brief.
- The controller passes the tier as the `model` override when it dispatches
  `task-implementer`. The agent's own default stays `sonnet`, so a dispatch
  without an override behaves as before.
- `tests/hooks/test_plan_model_stamp.py` fails a plan above v145 with any
  task, in any part, whose first non-blank line is not a valid stamp. Plans
  v145 and earlier are exempt by number and never retrofitted.

## The rubric

| Tier | A task gets it when… | Examples |
|---|---|---|
| `haiku` | Fully specified, no judgement, the diff is fixed by the brief | Doc/config edits, `VERSION.json` bump, a fixture, a rename, a copied pattern |
| `sonnet` (default) | A normal TDD task inside one module, with the behaviour given by the spec | A new metric, an embed field, a store method, an admin endpoint |
| `opus` | Any of: entry signals or no-lookahead territory, a schema migration, crosses at least 2 `swingbot/core` packages, splits a legacy function at complexity ≥ 15, statistical code that feeds a gate | Edge module wiring, an Alembic revision, a backtest gate change |

When a task matches more than one row, **the higher tier wins**.

Review is never weaker than the implementation: `task-reviewer` stays on
`sonnet` whatever the task's tier. Expert reviewers (`expert-reviewer`,
dispatched by `/panel`) run at their role's model from `skills-tools.md`
§ Expert roles, never on haiku.

## The escalation ladder

This replaces the old rule "a task that fails review twice is implemented by
Opus directly".

1. `task-reviewer` returns blocking findings: `SendMessage` the same
   implementer once, at the same tier.
2. Still blocking: dispatch a **fresh** implementer **one tier up**
   (haiku → sonnet → opus), with the findings attached.
3. Still blocking at opus: Opus implements the task inline in the main
   session.

Log each escalation as one line in `.superpowers/sdd/progress.md`:

```
<task id>: <from>→<to> (<reason>)
```

for example `V146-4: sonnet→opus (review: rolling window reads bar k+1)`, and
`V146-4: opus→inline (review: same finding after re-dispatch)` for step 3.

## Retuning the rubric

The escalation lines are the evidence. Retune the rubric here, in its own
commit that cites the lines that motivated it — never per task, and never by
editing a plan's stamps after the fact.
````

- [ ] **Step 5: Document the stamp in `document-conventions.md`**

Insert directly after the `**\`Panel:\`**` block (after its sentence ending `A split spec carries the line in its \`_0-index\` part.`):

```markdown
**`Model:`** — plans only, and only plans numbered **v146 or above**. It is
not a header-block line: it is the first line under every `### Task` heading,
`**Model:** <haiku|sonnet|opus> — <one-clause reason>`, chosen from the rubric
in `model-routing.md` (when a task matches more than one row, the higher tier
wins). `/task-brief` copies it into the brief and the controller dispatches
`task-implementer` at that tier; repeated review failures climb the
escalation ladder in the same doc. `tests/hooks/test_plan_model_stamp.py`
fails any task in such a plan, in any part, whose first non-blank line is not
a valid stamp.
```

- [ ] **Step 6: Teach plan-writer the stamp**

In `.claude/agents/plan-writer.md`, insert directly after the bullet starting `- \`### Task <PREFIX><n>:\` headings`:

```markdown
- Plans numbered above v145: the first line under every `### Task` is `**Model:** <haiku|sonnet|opus> — <one-clause reason>`, from the rubric in `docs/claude/model-routing.md` (the higher tier wins).
```

- [ ] **Step 7: Teach new-doc the Panel and Model stamps**

Replace the whole of `.claude/skills/new-doc/SKILL.md` with exactly the text below (80 lines — the budget's ceiling; the only changes are the end of Step 3's second paragraph and the last sentence of Step 7):

````markdown
---
name: new-doc
description: Ritual for creating a new spec or plan -- recompute the repo-wide vN counter immediately before the commit, write the header block, and keep the document addressable and splittable. Run as /new-doc, or by Claude itself immediately before it creates a numbered spec or plan file.
---

# New spec or plan

## Step 1 — Read the authority

`docs/claude/document-conventions.md`. This skill is the checklist; the
reasoning behind every step below lives there, not here.

## Step 2 — Compute the number immediately before the commit

Not once at the start of the session -- concurrent sessions share this
counter, and a number that was free five minutes ago may not be now. Run
this verbatim, from the repo root:

```bash
{ find docs/superpowers/specs docs/superpowers/plans -name '*.md' | grep -oE 'v[0-9]+'
  git log --oneline --all | grep -oE '\(v[0-9]+\)' | grep -oE '[0-9]+' | sed 's/^/v/'
} | sort -V | tail -1
```

The printed value is the highest number already claimed, not the free one
-- your document takes that number plus one.

`find` recurses into `implemented/`/`no-lift/` on its own -- closed docs
live one level down, and an `ls` that misses them returns a stale max. The
`git log` half exists because an informal `vN` in a commit subject with no
matching doc file has burned a number before.

## Step 3 — Write the header block

`Version:` on a spec only (never a plan) -- `ui X.Y.Z · bot A.B.C` copied
from `VERSION.json` as of this commit, never refreshed afterwards. `Bump:`
as a level, with no numbers in it. `Edge:` as one of `expectancy` /
`harvest` / `volume` / `none (integrity)`. A plan built from an
already-numbered spec reuses that spec's number and links back with a
`**Spec:**` line.

A spec numbered above v140 also carries `**Screen:**` under `Edge:` -- a
`SCREEN-PASS` ledger id, a `harvest-headroom` results path, or `exempt
(integrity)`. From v146 a spec carries `**Panel:**` directly below
`Screen:`: one to three role skills, defaulting by `Edge:` from the table in
`document-conventions.md`, overridable by the author. From v146 a plan's
first line under every `### Task` is `**Model:**`, per
`docs/claude/model-routing.md`. Which value, and why: `document-conventions.md`.

## Step 4 — Keep it addressable

`### Task <id>:` one line, no prose before the colon. `# Phase N —` with
one hash, however wrong that looks beside the `##` sections around it.
`guardrails.py` denies a two-hash phase heading and a non-conforming
filename -- treat both denies as correct, never work around them.

## Step 5 — Respect the length cap

Over the cap, split into `_N` parts sharing the parent's number (a part
that itself splits becomes `_2a`/`_2b`). Split, never compress -- a
compressed task is a task that gets re-derived wrong later.

## Step 6 — Add `## Parallelisation`

Name the groups and, more importantly, the reason on every sequential
edge. Be honest about a group of one -- a chain that says so saves the
next session from re-deriving the dependency graph.

## Step 7 — Commit on `main`

Specs and plans are written and committed on `main`, never a branch --
branch only to implement one. If the number collided while you were
writing, rename before your own commit, never after one has landed. A spec
with a `**Panel:**` line then gets `/panel` before the partner reviews it.

## The gate

The file name matches the convention, the counter was recomputed in the
same minute as the commit, and the plan ends with a single full-suite
verification task.
````

Check: `wc -l .claude/skills/new-doc/SKILL.md` prints `80` or less.

- [ ] **Step 8: Teach task-brief to copy the stamp**

In `.claude/skills/task-brief/SKILL.md`, replace the first sentence of `## Step 5 — Emit the brief`:

```markdown
Task id and title, files to create/modify (corrected paths), interfaces, the TDD
steps verbatim from the plan, then a **Preflight** section listing every 3a-3h
result with the corrections made.
```

with:

```markdown
Task id and title, then the task's `**Model:**` line verbatim (plans numbered
above v145 — if it is missing there, say so in Preflight rather than guessing a
tier; the controller dispatches `task-implementer` at that tier), files to
create/modify (corrected paths), interfaces, the TDD steps verbatim from the
plan, then a **Preflight** section listing every 3a-3h result with the
corrections made.
```

- [ ] **Step 9: Mirror to Codex**

In `AGENTS.md`, insert after the line `- \`docs/claude/code-complexity.md\` before writing or changing any function.`:

```markdown
- `docs/claude/model-routing.md` before writing a plan or dispatching a plan
  task: the `**Model:**` tier rubric and the escalation ladder.
```

and in `## Specs, plans and versioning`, insert after the paragraph ending ``release versions are independent (`document-conventions.md`).``:

```markdown
Plans numbered v146 or above stamp `**Model:** <haiku|sonnet|opus> — <reason>`
as the first line under every `### Task`, from the rubric in
`docs/claude/model-routing.md`; dispatch `task-implementer` at that tier.
`tests/hooks/test_plan_model_stamp.py` enforces it; v145 and earlier are
exempt.
```

Then run: `python scripts/dev/sync_codex.py`
Expected: `Codex mirror is current.` (`model-routing.md` is now a reference doc, so `_missing_mentions` requires the path above.)

- [ ] **Step 10: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/` then `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: both PASS, `0 failed`. Then `python -m radon cc -s -n C tests/hooks/test_plan_model_stamp.py` prints nothing.

- [ ] **Step 11: Commit**

```bash
git add docs/claude/model-routing.md tests/hooks/test_plan_model_stamp.py scripts/dev/select_tests.py docs/claude/document-conventions.md .claude/agents/plan-writer.md .claude/skills/new-doc/SKILL.md .claude/skills/task-brief/SKILL.md .codex/agents .agents/skills AGENTS.md
git commit -m "feat(v145): per-task Model stamp from v146 -- model-routing.md rubric and escalation ladder"
```
