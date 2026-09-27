# v107 — Token Budget Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** none
**Edge:** none (integrity)
**Spec:** `docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md`

**Goal:** Cut Opus token spend by moving mechanical work onto pinned-model role
agents with preloaded skills, forking two mechanical slash skills, and
shrinking the fixed per-session startup load.

**Architecture:** Four new agent files under `.claude/agents/`, one frontmatter
edit to `backtest-runner`, two frontmatter edits to repo skills, a
project-scoped `enabledPlugins` block in `.claude/settings.json`, and a trim
of the always-loaded text (`CLAUDE.md`, `MEMORY.md`). A new shape test
(`tests/hooks/test_agent_shape.py`) pins every agent's model and contract the
way `test_skill_shape.py` already pins skills.

**Tech Stack:** Claude Code agent/skill frontmatter, settings.json, pytest.

## Global Constraints

- One subagent at a time (`docs/claude/skills-tools.md`) — unchanged.
- Specs, plans, backtest interpretation and gate calls stay on Opus.
- `plan-writer` model: `opus`. `task-implementer`, `task-reviewer`: `sonnet`. `prod-inspector`: `haiku`.
- `prod-inspector` is read-only; production writes stay in the main session under `mirror-prod`.
- Plugin/MCP disabling is **project-scoped only** — user-level settings untouched.
- `CLAUDE.md` target ≤ 9 KB (`wc -c`), hard limit < 200 lines unchanged.
- Startup success criterion: ≥ 30% fewer tokens in system prompt + tools + memory per `/context`.
- Every function < complexity 15 (the test file's helpers included).
- Full suite runs once, in TB13 only.

## Parallelisation

**Sequential throughout.** TB3–TB7 each append an entry to the shared
`tests/hooks/test_agent_shape.py` `EXPECTED` map (shared file), TB1 decides the
frontmatter syntax every later task writes, TB2's baseline must precede TB9–TB11,
and the one-subagent rule applies anyway.

---

### Task TB1: Verify frontmatter and settings support

**Files:**
- Modify: `docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md` (append `## Verified support`)

**Interfaces:**
- Produces: the exact syntax later tasks use for (a) agent `skills:` (comma list vs YAML list), (b) skill `context: fork` + `agent:` + `model:`, (c) project-scope `enabledPlugins` override of a user-enabled plugin, (d) disabling a plugin-provided MCP server at project scope.

- [ ] **Step 1:** Dispatch `claude-code-guide` (one agent) with this prompt:

```
Answer from current Claude Code docs, citing the doc page for each:
1. Subagent frontmatter (.claude/agents/*.md): is there a `skills` field that
   preloads skill content at startup? Exact syntax (comma string or YAML list)?
   Does it accept plugin-namespaced skills like `superpowers:test-driven-development`?
2. Skill frontmatter (SKILL.md): `context: fork`, `agent:`, `model:` — exist?
   Does a forked skill's intermediate tool output stay out of the caller's
   context, and what is returned to the caller? Compatible with
   `disable-model-invocation: true`?
3. Can a project `.claude/settings.json` `enabledPlugins: {"x@m": false}`
   disable a plugin that the user-level settings enable? Precedence order?
4. How to disable a single plugin-provided MCP server for one project
   (e.g. `disabledMcpjsonServers`, `/mcp disable`, or plugin disable only)?
Answer each in ≤ 5 lines.
```

- [ ] **Step 2:** Append its answers verbatim-condensed to the spec under `## Verified support`, one subsection per question. For any "unsupported" answer write the fallback in one line:
  - (1) unsupported → agent body gets a `## Conventions` block of ≤ 10 lines summarising the skill instead of `skills:`.
  - (2) unsupported → TB8 is skipped and recorded as such in the spec.
  - (3)/(4) unsupported → TB9 records the plugin in `skills-tools.md` instead of disabling it.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
git commit -m "docs(v107): TB1 -- verified agent/skill/settings frontmatter support"
```

---

### Task TB2: Baseline startup measurement (human step)

**Files:**
- Modify: `docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md` (append `## Measurements`)

- [ ] **Step 1:** Ask the human partner (AskUserQuestion is not needed — a plain request) to open a **fresh** session in this repo and run `/context`, then paste the output. A session cannot measure its own startup cost reliably after work has begun.

- [ ] **Step 2:** Record in the spec under `## Measurements`:

```markdown
| Bucket | Before (tokens) | After (tokens) |
|---|---|---|
| System prompt | <n> | — |
| System tools | <n> | — |
| MCP tools | <n> | — |
| Custom agents | <n> | — |
| Memory files | <n> | — |
| Skills | <n> | — |
| **Total startup** | <n> | — |
```

Fill `<n>` from the pasted output; leave "After" as `—` until TB13.

- [ ] **Step 3:** Also record `wc -c CLAUDE.md` and the memory index size (`wc -c "$CLAUDE_CONFIG_DIR/projects/E--Documents-Private-Projects-Discord-Bot/memory/MEMORY.md"`, falling back to the `config-meo` path if the variable is unset).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
git commit -m "docs(v107): TB2 -- baseline /context startup measurement"
```

---

### Task TB3: Agent shape test + `task-implementer`

**Files:**
- Create: `tests/hooks/test_agent_shape.py`
- Create: `.claude/agents/task-implementer.md`

**Interfaces:**
- Produces: `EXPECTED` dict in `test_agent_shape.py`, `name -> {"model": str, "skills": set[str]}`; later tasks append one entry each. `_read_agent(name) -> (meta: dict, body: str)`; `_skills(meta) -> set[str]`.

- [ ] **Step 1: Write the failing test**

```python
"""Shape contract for .claude/agents/*.md -- v107.

Pins each role agent's model and preloaded skills so a cost decision made in
the v107 spec cannot drift silently. See
docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
"""
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"

# Each v107 agent task appends its own entry.
EXPECTED = {
    "task-implementer": {
        "model": "sonnet",
        "skills": {"superpowers:test-driven-development",
                   "superpowers:verification-before-completion"},
    },
}

VALID_MODELS = {"haiku", "sonnet", "opus"}


def _agent_files():
    if not AGENTS_DIR.is_dir():
        return []
    return sorted(AGENTS_DIR.glob("*.md"))


def _read_agent(name):
    """Return (frontmatter dict, body) -- the simple `key: value` subset."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def _skills(meta):
    raw = meta.get("skills", "").strip("[]")
    return {s.strip().strip("'\"") for s in raw.split(",") if s.strip()}


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_every_agent_declares_name_description_model(path):
    meta, _ = _read_agent(path.stem)
    assert meta.get("name") == path.stem
    assert len(meta.get("description", "")) >= 40
    assert meta.get("model") in VALID_MODELS


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_role_agent_pins_model_and_skills(name):
    meta, _ = _read_agent(name)
    assert meta.get("model") == EXPECTED[name]["model"]
    assert _skills(meta) == EXPECTED[name]["skills"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_role_agent_has_fixed_return_shape(name):
    _, body = _read_agent(name)
    assert "## Return shape" in body
    assert "BLOCKED:" in body
```

If TB1 found `skills:` must be a YAML list, replace `_read_agent`'s skip of
`-` lines with collection of `- item` lines under `skills:` and keep `_skills`
returning a set — the tests themselves do not change.

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py`
Expected: FAIL — `FileNotFoundError` for `task-implementer.md`.

- [ ] **Step 3: Write `.claude/agents/task-implementer.md`**

````markdown
---
name: task-implementer
description: Implements exactly one plan task from a /task-brief output, test-first, in the worktree it is given, and returns a short report. Use for plan-task implementation so the work runs on Sonnet and only the summary reaches the Opus controller.
tools: Bash, Read, Edit, Write, Grep, Glob, Skill
model: sonnet
skills: superpowers:test-driven-development, superpowers:verification-before-completion
---

You implement **one** task of a plan for a Discord swing-trade bot. The
controller (Opus) has already extracted the task with `/task-brief` and pasted
it into your prompt, along with the worktree path. That brief is your whole
scope.

## Rules

- **Never open a plan file.** Plans here are hundreds of KB. If the brief is
  missing something, return `BLOCKED:` — do not go looking.
- Work only in the worktree path given. Never edit `.claude/worktrees/*` from
  the main tree, never touch another worktree.
- Test-first (preloaded TDD skill). Iterate with
  `python scripts/dev/testrun.py file <test file>` — never the full suite,
  never `fast`; the plan's last task owns the full run.
- Every function you write or change stays below cyclomatic complexity 15:
  `python -m radon cc -s -n C <files>` must print nothing for your changes.
- Area skills (`no-lookahead`, `alert-surface`, `edge-module`,
  `schema-change`) fire on their own when you touch their area — follow them.
- Never `cd` in a Bash command (it breaks the repo hooks); use absolute paths
  or `git -C <path>`.
- Commit when the brief's steps say so, with the brief's message, ending with
  the attribution lines the controller passes you.

## Return shape

Return **only** this, nothing else:

```
STATUS: DONE | BLOCKED: <one question>
COMMITS: <sha> <subject>   (one line each)
FILES: <path>              (one line each)
TESTS: <testrun.py verdict line, verbatim>
RADON: clean | <function: grade>
NOTES: <= 3 lines, only what the reviewer must know
```
````

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py`
Expected: PASS (the three existing agents pass the generic test too).

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_agent_shape.py .claude/agents/task-implementer.md
git commit -m "feat(v107): TB3 -- agent shape test and task-implementer agent"
```

---

### Task TB4: `task-reviewer`

**Files:**
- Create: `.claude/agents/task-reviewer.md`
- Modify: `tests/hooks/test_agent_shape.py` (append to `EXPECTED`)

- [ ] **Step 1: Append the failing expectation**

```python
    "task-reviewer": {
        "model": "sonnet",
        "skills": {"no-lookahead"},
    },
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py` — Expected: FAIL (file missing).

- [ ] **Step 3: Write `.claude/agents/task-reviewer.md`**

````markdown
---
name: task-reviewer
description: Reviews one implemented plan task's commits against its /task-brief -- spec compliance first, then code quality and complexity -- and returns numbered findings or CLEAN. Read-only. Use after task-implementer so review runs on Sonnet and only findings reach Opus.
tools: Bash, Read, Grep, Glob, Skill
model: sonnet
skills: no-lookahead
---

You review **one** task. You get the task brief, the worktree path and a
commit range. You change nothing.

## Order

1. **Spec compliance.** Every step and deliverable in the brief exists in
   the diff (`git -C <wt> diff <range>`). Anything missing, extra, or
   different from the brief is a finding.
2. **Correctness.** Lookahead (preloaded skill), off-by-one on bar indices,
   silent no-op shims (`docs/claude/known-traps.md`), untested branches.
3. **Complexity.** `python -m radon cc -s -n C <changed .py files>` — any
   function at C or worse that the diff created or made worse is a finding.
4. **Tests.** `python scripts/dev/testrun.py file <each changed test file>`;
   a failure is a finding with the verdict line quoted.

Do not report style preferences, and do not suggest refactors outside the
diff. A finding you cannot tie to a line is not a finding.

## Return shape

```
VERDICT: CLEAN | FINDINGS | BLOCKED: <one question>
1. [spec|correctness|complexity|test] <file>:<line> -- <one sentence>
   fix: <one sentence>
...
```

At most 10 findings, most severe first.
````

- [ ] **Step 4:** Run the test file — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_agent_shape.py .claude/agents/task-reviewer.md
git commit -m "feat(v107): TB4 -- task-reviewer agent"
```

---

### Task TB5: `plan-writer`

**Files:**
- Create: `.claude/agents/plan-writer.md`
- Modify: `tests/hooks/test_agent_shape.py` (append to `EXPECTED`)

- [ ] **Step 1: Append the failing expectation**

```python
    "plan-writer": {
        "model": "opus",
        "skills": {"superpowers:writing-plans", "new-doc"},
    },
```

- [ ] **Step 2:** Run the test file — Expected: FAIL.

- [ ] **Step 3: Write `.claude/agents/plan-writer.md`**

````markdown
---
name: plan-writer
description: Writes an implementation plan from an already-approved spec, following this repo's document conventions (vN counter, Bump/Edge header, ### Task ids, Parallelisation, 1500-line split rule). Runs on Opus. Use after brainstorming has produced and the user has approved a spec.
tools: Bash, Read, Write, Grep, Glob, Skill
model: opus
skills: superpowers:writing-plans, new-doc
---

You turn **one approved spec** into a plan. The spec path is in your prompt.
Brainstorming is over: do not redesign, do not add scope. A spec gap you
cannot fill from the code is a `BLOCKED:` question, not an invention.

## Rules

- Read `docs/claude/document-conventions.md` before writing.
- Plan file name reuses the spec's `vN` and date; parts over 1500 lines split
  into `_N` files — never compress a task to fit.
- `Bump:` states a level only, never a version number.
- Task headings are `### Task <PREFIX><n>:` so `/task-brief` can find them.
- Verify every symbol you name exists (`git grep -n`), or mark it as created
  by an earlier task in that task's **Interfaces** block.
- Exactly one full-suite run, as the final task.
- **Do not commit.** The controller reviews and commits.

## Return shape

```
STATUS: DONE | BLOCKED: <one question>
FILES: <plan path(s)> (<line count> each)
TASKS: <first id>..<last id> (<count>)
OPEN: <= 3 lines -- decisions the controller should check
```
````

- [ ] **Step 4:** Run the test file — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_agent_shape.py .claude/agents/plan-writer.md
git commit -m "feat(v107): TB5 -- plan-writer agent (opus)"
```

---

### Task TB6: `prod-inspector`

**Files:**
- Create: `.claude/agents/prod-inspector.md`
- Modify: `tests/hooks/test_agent_shape.py` (append to `EXPECTED`, add one test)

- [ ] **Step 1: Append the failing expectation and read-only test**

```python
    "prod-inspector": {
        "model": "haiku",
        "skills": set(),
    },
```

```python
def test_prod_inspector_is_read_only():
    meta, body = _read_agent("prod-inspector")
    assert "Edit" not in meta.get("tools", "")
    assert "Write" not in meta.get("tools", "")
    for forbidden in ("restart", ".env", "docker compose up", "sed -i"):
        assert forbidden in body, f"body must name {forbidden!r} as forbidden"
```

- [ ] **Step 2:** Run the test file — Expected: FAIL.

- [ ] **Step 3: Write `.claude/agents/prod-inspector.md`**

````markdown
---
name: prod-inspector
description: Answers one read-only question about the production Hetzner VM -- logs, container status, disk, last scan -- and returns a short summary with excerpts. Never changes anything. Use for any production investigation so log volume stays out of the Opus context.
tools: Bash, Read, Grep
model: haiku
---

You inspect the production VM (Hetzner, `167.233.26.185`) through
`scripts/ops/ssh-hetzner.sh "<command>"`. You answer **one** question.

## Where the truth is

- Error history: `/opt/swing-bot/logs/*.log` (bind-mounted, rotated). Grep
  these first. `docker logs` is empty after a deploy and hides outages —
  use it only for the current container's last minutes.
- Status: `docker compose ps`, `df -h`, `uptime`.

## Forbidden — refuse and hand back

You are read-only. Never run, even if asked: any `restart`,
`docker compose up`/`down`/`pull`, `git pull`, `sed -i` or any edit of
`.env` or any other file, `rm`, `kill`, `make deploy`. If the question needs a write, return
`BLOCKED: needs a production write -- <what>`; the controller does it under
the `mirror-prod` skill.

## Return shape

```
ANSWER: <= 5 lines
EVIDENCE: <= 8 excerpt lines, each prefixed with file:line or command
BLOCKED: <only if a write is needed>
```
````

- [ ] **Step 4:** Run the test file — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_agent_shape.py .claude/agents/prod-inspector.md
git commit -m "feat(v107): TB6 -- read-only prod-inspector agent (haiku)"
```

---

### Task TB7: Preload `backtest-gate` into `backtest-runner`

**Files:**
- Modify: `.claude/agents/backtest-runner.md` (frontmatter only)
- Modify: `tests/hooks/test_agent_shape.py` (append to `EXPECTED`)

- [ ] **Step 1: Append the failing expectation**

```python
    "backtest-runner": {
        "model": "sonnet",
        "skills": {"backtest-gate"},
    },
```

- [ ] **Step 2:** Run the test file — Expected: FAIL (`set() != {'backtest-gate'}`), and `test_role_agent_has_fixed_return_shape[backtest-runner]` may also fail.

- [ ] **Step 3:** Add `skills: backtest-gate` after the `model: sonnet` line. If the return-shape test fails, check the body: if it already defines a fixed report format under another heading, rename that heading to `## Return shape` and add one line `If the run cannot start or the brief is ambiguous, return BLOCKED: <one question>.` — change nothing else in the body.

- [ ] **Step 4:** Run the test file — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_agent_shape.py .claude/agents/backtest-runner.md
git commit -m "feat(v107): TB7 -- backtest-runner preloads backtest-gate"
```

---

### Task TB8: Fork `/gate` and `/task-brief`

Skip entirely (record "skipped: unsupported" in the spec) if TB1 answer (2) said forking is unsupported.

**Files:**
- Modify: `.claude/skills/gate/SKILL.md` (frontmatter)
- Modify: `.claude/skills/task-brief/SKILL.md` (frontmatter)
- Modify: `tests/hooks/test_skill_shape.py` (one new test)

- [ ] **Step 1: Write the failing test** (append to `test_skill_shape.py`)

```python
# v107: mechanical slash skills run forked on a cheaper model.
FORKED = {"gate": "sonnet", "task-brief": "haiku"}


@pytest.mark.parametrize("name", sorted(FORKED))
def test_mechanical_skills_run_forked(name):
    meta, _ = _read_skill(name)
    assert meta.get("context") == "fork"
    assert meta.get("model") == FORKED[name]
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py` — Expected: FAIL.

- [ ] **Step 3:** Add to `gate/SKILL.md` frontmatter (before the closing `---`):

```yaml
context: fork
model: sonnet
```

and to `task-brief/SKILL.md`:

```yaml
context: fork
model: haiku
```

Plus `agent:` if TB1 answer (2) says it is required for a fork, with the value TB1 recorded.

- [ ] **Step 4:** Run the test file — Expected: PASS.

- [ ] **Step 5: Manual check.** Run `/task-brief TB1` in the session. The main context must receive the brief text only, with no intermediate grep output. Record the result in one line in the spec under `## Verified support`.

- [ ] **Step 6: Commit**

```bash
git add tests/hooks/test_skill_shape.py .claude/skills/gate/SKILL.md .claude/skills/task-brief/SKILL.md docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
git commit -m "feat(v107): TB8 -- /gate and /task-brief run forked on cheaper models"
```

---

### Task TB9: Disable unused plugins and MCP servers for this project

**Files:**
- Modify: `.claude/settings.json` (add `enabledPlugins`, and the MCP key TB1 named)
- Modify: `docs/claude/skills-tools.md` (one bullet listing what was disabled and what could not be)

- [ ] **Step 1: Find the active config dir and the installed plugin ids.**

```bash
echo "$CLAUDE_CONFIG_DIR"
cat "$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json" | python -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(sorted(d.get('plugins', d).keys())))"
```

The superpowers skill resolves from `config-personal`, while the memory lives in `config-meo`, so check both dirs if the variable is unset. The ids are needed as `name@marketplace`.

- [ ] **Step 2: Decide the keep list.** Keep: `superpowers`, `claude-md-management`, `security-guidance`. Disable every installed plugin whose skills or MCP tools showed up in this session's list and that this repo does not use: `small-business`, `legal`, `finance`, `product-management`, `data`, `engineering`, `productivity`, `pdf-viewer`, `chrome-devtools-mcp`, `playwright` (the repo uses `npx playwright` per `skills-tools.md`). Use the exact ids from Step 1.

- [ ] **Step 3: Write the block** into `.claude/settings.json`, as a sibling of `"permissions"`:

```json
  "enabledPlugins": {
    "small-business@<marketplace>": false,
    "legal@<marketplace>": false
  },
```

with one line per plugin from Step 2, `<marketplace>` taken literally from Step 1's ids. Add the MCP-disable key TB1 answer (4) named for `definite` and any other MCP that is not tied to a disabled plugin.

- [ ] **Step 4: Validate the JSON:** `python -c "import json; json.load(open('.claude/settings.json'))"` — Expected: no output.

- [ ] **Step 5:** Anything served by claude.ai instead of a local plugin (`anthropic-skills:*`, the Claude Docs connector) or that TB1 says cannot be disabled at project scope gets one line in `skills-tools.md`: `- Not locally disableable (v107): <name> -- <source>.`

- [ ] **Step 6: Commit**

```bash
git add .claude/settings.json docs/claude/skills-tools.md
git commit -m "chore(v107): TB9 -- disable unused plugins and MCP servers for this project"
```

---

### Task TB10: Trim the `MEMORY.md` index

`MEMORY.md` lives in the user config dir, outside git, so this task has no commit. Record the before/after size in the spec in TB13.

**Files:**
- Modify: `<config dir>/projects/E--Documents-Private-Projects-Discord-Bot/memory/MEMORY.md`
- Delete: memory files that are fully superseded (see Step 2)

- [ ] **Step 1:** Rewrite each index line as `- [Title](file.md) — <≤ 12-word hook>`. Keep every link.

- [ ] **Step 2:** For each memory, `git grep -n -i "<its key phrase>" -- CLAUDE.md docs/claude` to check whether a committed doc already states the fact. Delete the memory file and its index line **only** when the committed doc states the whole fact, not just part of it. The likely candidates are `bash-cd-breaks-hooks` and `stale-checkout-hazard`, but check each one; do not assume.

- [ ] **Step 3:** `wc -c MEMORY.md` — Expected: at most 3 KB. If it's over, shorten the hooks further, but never drop a live memory.

---

### Task TB11: Trim `CLAUDE.md` to ≤ 9 KB

**Files:**
- Modify: `CLAUDE.md`
- Create: `docs/claude/persona.md`
- Modify: `docs/claude/working-conventions.md` (append `## Codex mirror`)

- [ ] **Step 1:** Move the body of `## Who you are on this repo` into `docs/claude/persona.md` (title `# Persona and questioning`, first line `Referenced from the root CLAUDE.md.`). In `CLAUDE.md`, keep only:

```markdown
## Who you are on this repo

Senior trader/quant, software architect, senior developer and UX designer at
once — the persona raises the bar, never lowers a gate; rules below win.
**Ask via `AskUserQuestion`, one question per message, recommended option
first**, whenever something is ambiguous or the call is the partner's; once a
plan task's scope is clear, run it straight through. Detail: `persona.md`.
```

- [ ] **Step 2:** Move the body of `## Claude is the operator; Codex follows` into `working-conventions.md` under `## Codex mirror`, word for word. In `CLAUDE.md`, keep:

```markdown
## Claude is the operator; Codex follows

Root `AGENTS.md` is a condensed one-way mirror for Codex; Claude updates it,
never the reverse. Detail: `working-conventions.md` § Codex mirror.
```

- [ ] **Step 3:** Add `| persona.md | deciding how to question the partner, or what bar a change must meet |` to the reference table.

- [ ] **Step 4:** Run `wc -c CLAUDE.md`. Expected: at most 9216. If it's still over, condense `## Current status is not tracked here` into two sentences that keep the "verify the NEXT id with grep" rule, and move its prose into `document-lifecycle.md`. Also confirm `wc -l CLAUDE.md` is under 200.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/claude/persona.md docs/claude/working-conventions.md
git commit -m "docs(v107): TB11 -- trim CLAUDE.md, move persona and Codex detail to docs/claude"
```

---

### Task TB12: Dispatch table and the `AGENTS.md` mirror

**Files:**
- Modify: `docs/claude/skills-tools.md` (new `## Which agent for what` section)
- Modify: `CLAUDE.md` (pointer, one line under Token discipline)
- Modify: `AGENTS.md` (one condensed line)

- [ ] **Step 1:** Append to `skills-tools.md`:

```markdown
## Which agent for what (v107)

Serial, one at a time. Opus (main session) decides; agents do.

| Work | Agent | Model |
|---|---|---|
| Implement one plan task from `/task-brief` | `task-implementer` | sonnet |
| Review that task's commits | `task-reviewer` | sonnet |
| Draft a plan from an approved spec | `plan-writer` | opus |
| Read-only production question | `prod-inspector` | haiku |
| Backtest / grid / fold run > ~2 min | `backtest-runner` | sonnet |
| Full or fast suite run | `test-runner` | sonnet |
| Check a plan's symbols exist | `symbol-verifier` | haiku |

Plan loop: `/task-brief` → `task-implementer` → `task-reviewer` → Opus reads
findings → fix via `SendMessage` to the same implementer, or next task. A task
that fails review twice is implemented by Opus directly. Brainstorming never
goes to an agent — it needs the partner.
```

- [ ] **Step 2:** In `CLAUDE.md`'s Token discipline list, add:

```markdown
- **Route mechanical work to the role agents** (`task-implementer`,
  `task-reviewer`, `prod-inspector`, …) — table: `skills-tools.md` § Which agent for what.
```

Re-check `wc -c CLAUDE.md`. It must still be at most 9216.

- [ ] **Step 3:** In `AGENTS.md`, beside its existing subagent mention (find it with `grep -n -i "subagent\|agent" AGENTS.md | head`), add one line: `Claude-side role agents (v107) are Claude-only; Codex has no equivalent and needs none.`

- [ ] **Step 4: Commit**

```bash
git add docs/claude/skills-tools.md CLAUDE.md AGENTS.md
git commit -m "docs(v107): TB12 -- agent dispatch table, CLAUDE.md pointer, AGENTS.md mirror"
```

---

### Task TB13: Smoke-dispatch, after-measurement, full suite, close-out

**Files:**
- Modify: `docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md` (`## Measurements` "After" column, smoke results)
- Move: the spec and plan into `implemented/` or `no-lift/` per `document-lifecycle.md`

- [ ] **Step 1: Smoke each new agent once, serially.**
  - `task-implementer`: a fixture brief. "Add a module docstring line `# v107 smoke` to `scripts/dev/testrun.py`, run `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py`, **do not commit**." Expect the return shape. Then run `git checkout -- scripts/dev/testrun.py`.
  - `task-reviewer`: the TB6 commit against the TB6 brief. Expect `VERDICT:` plus its shape.
  - `prod-inspector`: first "How many ERROR lines in today's bot log?" Expect `ANSWER:`. Then "restart the bot container". Expect `BLOCKED:` and no command run.
  - `plan-writer`: no smoke run, because it costs an Opus spawn. Its frontmatter is covered by the shape test.
  - Preload check: none of the implementer transcripts should show a `Skill` call for TDD or verification.

  Record one line per agent in the spec.

- [ ] **Step 2: After-measurement (human step).** Ask the partner for a fresh session plus `/context`, then fill the "After" column. Compute `(before - after) / before` for the total. Target: at least 30%. If it's lower, record the real figure and which bucket dominates. Do not re-run anything to chase the number.

- [ ] **Step 3: Full suite, once.** Dispatch `test-runner` for `python scripts/dev/testrun.py full`. Green means `0 failed` and `0 xfailed`.

- [ ] **Step 4: Close-out.** Run `/close-out`. `Bump: none` means no `VERSION.json` change. Move the spec and plan to `implemented/` if the 30% target was met, or to `implemented/` with a "partial" note if the agents shipped but startup fell short.

- [ ] **Step 5: Commit**

```bash
git add -A docs/superpowers
git commit -m "docs(v107): TB13 -- smoke results, after-measurement, close-out"
```
