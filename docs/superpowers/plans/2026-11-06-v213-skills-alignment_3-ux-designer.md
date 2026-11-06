# v213 — Skills alignment, part 3: ux-designer seat, `/panel` table, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v213 — Skills alignment](../specs/2026-11-06-v213-skills-alignment.md) (§ D. ux-designer seat; § Codex mirror; § Testing)
**Index:** [`2026-11-06-v213-skills-alignment_0-index.md`](2026-11-06-v213-skills-alignment_0-index.md) — Goal, Architecture, **Global Constraints**, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

**Tasks:** V213-12..V213-14, in order, after V213-11. V213-12 and V213-13 are implementer tasks in the worktree; V213-14 is the controller's (panel, merge, CI watch, `/close-out`).

**Where to run.** V213-12 and V213-13: every path and command is relative to
the worktree root `.claude/worktrees/2026-11-06-v213-skills-alignment`; the
implementer's session root is that worktree. Never `cd` inside a Bash command.

**Editing skills in this part.**

- Skill, agent and doc files may use CRLF on disk; edit with the Edit tool, matching old text by its words, and keep the file's endings. The tests normalise CRLF.
- **Create every file under an `evals/` folder with the Write tool, never through Bash**: a worktree session refuses any Bash command containing the substring "eval". Stage eval files by their skill folder (`git add .claude/skills/ux-designer`), which carries no such substring.
- "Old" texts below are the files as V213-11 (and, for `/panel`, V213-6 and V213-7) left them. If one does not match, `git grep -n` its first words and stop with `BLOCKED:` if it is gone.
- New prose obeys the lint (index § Global Constraints, "New prose passes the lint"). Every backticked path below was checked with `git ls-files` on `da07fb26`: `frontend/scripts/layout-audit.mjs`, `docs/claude/ui-design.md`, `swingbot/core/scanning/alert_embeds.py`. The one new `§` cite, `docs/claude/ui-design.md` § Tables and pagers, is the heading `## Tables and pagers`. No UPPER_SNAKE name is added anywhere. Do not add a path, a config name or a `§` cite the task does not list.
- No bare thresholds (`_THRESHOLD_RE` in `tests/hooks/test_skill_shape.py`): no pixel widths, no `2%`-style figures in skill text; say "the three widths" and cite `docs/claude/ui-design.md`.
- Evals are written, never run (billed).

# Phase D — ux-designer seat

### Task V213-12: `ux-designer` seat with every wiring point in one commit

**Model:** sonnet — a new role skill written to a fixed shape plus eight wiring edits that must all land together; care, not design.

**Files:**
- Create: `.claude/skills/ux-designer/SKILL.md`
- Create (Write tool): `.claude/skills/ux-designer/evals/{fire-admin-table-phone,fire-embed-phone-truncation,fire-list-without-pager,no-fire-stop-placement,no-fire-backtest-expr,no-fire-alembic-migration}/prompt.md` and `.../graders/skill-fired.md` (twelve files)
- Modify: `tests/hooks/test_role_skills.py` (docstring line 1; `ROLES`)
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`)
- Modify: `tests/hooks/test_agent_shape.py` (`EXPERT_ROLES` and its comment)
- Modify: `.claude/agents/expert-reviewer.md` (description, `## Roles`, the `VERDICT` line)
- Modify: `docs/claude/skills-tools.md` (§ Expert roles (v145): "Nine role skills" and one table row)
- Modify: `docs/claude/persona.md` ("One seat at a time (v145)" paragraph)
- Modify: `AGENTS.md` (the "Expert role skills (v145)" paragraph)
- Generated: `.agents/skills/ux-designer/SKILL.md` (new), `.codex/agents/expert-reviewer.toml` (by `python scripts/dev/sync_codex.py`)

**Interfaces:**
- Consumes: `ROLES`, `BOUNDARY`, `_boundary`, `_checklist`, `LEADS`, `CROSS_CUTTING` in `tests/hooks/test_role_skills.py` (V213-7); `COVERAGE` (V213-8, parametrized over `sorted(COVERAGE)`, so a role without a row is not checked — `ux-designer` gets none).
- Produces: the skill `ux-designer` (reviewer model sonnet), a row of `ROLES`, of `EXPERT_ROLES` and of the skills-tools roles table. V213-13 names it in the `/panel` table.

**Why one commit.** `test_every_lens_skill_is_a_registered_role` needs the skill and its `ROLES` row together; `test_every_skill_is_registered_in_exactly_one_tier` needs `TIER_1_AND_3`; `test_reviewer_model_is_recorded_in_the_roles_table` needs the skills-tools row; `test_expert_reviewer_is_read_only_and_knows_every_role` needs `EXPERT_ROLES` and the agent body; `test_codex_mirror_is_current` needs `` `ux-designer` `` in `AGENTS.md` and the regenerated `.agents/` copy. Any one missing reddens a `tests/hooks/` job (spec § Order, "no push is red").

**Live counts only.** "nine" becomes "ten" in exactly five places: `docs/claude/skills-tools.md` ("Nine role skills"), `.claude/agents/expert-reviewer.md` (description and `VERDICT` line), `docs/claude/persona.md`, the `tests/hooks/test_role_skills.py` docstring and the `EXPERT_ROLES` comment. **Leave** `skills-tools.md` "v145 role suites, 2026-10-09: 54/54 cases pass across the nine role" and "Measured over nine plan-writer runs": they are dated results.

- [ ] **Step 1: Write the failing tests**

`tests/hooks/test_role_skills.py`, line 1, old:

```python
"""v145 § 1: the expert role skills -- one shape for nine lenses.
```

new:

```python
"""v145 § 1: the expert role skills -- one shape for ten lenses (v213 adds ux-designer).
```

In `ROLES`, after `"senior-engineer": "sonnet",` add:

```python
    "ux-designer": "sonnet",
```

`tests/hooks/test_skill_shape.py`, in `TIER_1_AND_3`, the line `"staff-engineer", "quant-engineer", "senior-engineer",` becomes:

```python
                "staff-engineer", "quant-engineer", "senior-engineer", "ux-designer",
```

`tests/hooks/test_agent_shape.py`, old:

```python
# v145: the nine role skills expert-reviewer must name (spec § 1).
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer")
```

new:

```python
# v145: the ten role skills expert-reviewer must name (spec § 1; v213 adds
# ux-designer).
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer",
                "ux-designer")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py
```

Expected: all three `VERDICT: FAIL`, and every failure names `ux-designer`: `test_every_lens_skill_is_a_registered_role` (`ROLES` has a role with no skill), every `[ux-designer]` case of `test_role_skills.py` (no `SKILL.md`), the tier and trigger-table tests of `test_skill_shape.py`, and `test_expert_reviewer_is_read_only_and_knows_every_role` (`missing ['ux-designer']`). A failure that does not name `ux-designer` existed before this task: stop and report it.

- [ ] **Step 3: Write the skill**

Create `.claude/skills/ux-designer/SKILL.md` with exactly this content (the boundary paragraph is the canonical text of index § Global Constraints, wrapped as there; the description is a double-quoted scalar of 257 characters, under the 260 cap):

```markdown
---
name: ux-designer
description: "Use when reviewing a spec, plan, diff or screen from the ux-designer seat -- admin UI and Discord embeds on phone, tablet and desktop: layout, pagers, empty states, truncation. Not for misleading figures (financial-advisor) or screen code (senior-engineer)."
---

# UX designer

You are one seat on a review panel. You raise findings; you never decide, and
you never lower a gate (`docs/claude/persona.md`). No seat's intuition
overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed
pre-registration, and you quote no pooled figure you did not re-derive. Every
finding cites `file:line`, a git range or a doc section, and is tagged
`BLOCKING` (it matches a red flag below) or `ADVISORY`.

## Lens

The admin UI and the Discord embeds as a person reads them on a phone, a
tablet and a desktop: whether a screen fits, whether the plan reads without
hunting for it, and whether every state tells the reader what to do next.

## Checklist

- A changed screen passes `node frontend/scripts/layout-audit.mjs` at the widths `docs/claude/ui-design.md` names (it owns the overflow, target-size and text-size rules).
- The check is driven by Playwright, never claude-in-chrome.
- A wide table scrolls inside its own container, never the page.
- A list longer than one page has a pager.
- Empty, loading and error states exist and say what to do next.
- Per-page defaults follow `docs/claude/ui-design.md` § Tables and pagers.
- Discord embed fields read on a phone (`swingbot/core/scanning/alert_embeds.py`): no truncated entry, stop or target; the plan fits without scrolling past the chart.
- Numbers carry units and sign consistently between the embed and the admin screen showing the same plan.
- A new control is reachable by keyboard and labelled for a screen reader.

## Red flags

- A screen that scrolls sideways at any of the three widths.
- A plan value truncated or hidden on a phone.
- A list with no pager.

## Out of scope

- Whether a figure misleads a retail reader: `financial-advisor`.
- Whether the plan is tradeable: `veteran-trader`.
- The code behind the screen: `senior-engineer`.

## Trigger table

Should fire: asking whether the trades table on the admin dashboard fits a phone without scrolling sideways.
Should fire: asking whether a Discord alert's entry, stop and targets get cut off on a phone.
Should fire: reviewing an admin screen that lists every closed trade on one long page with no pager.
Should not fire: checking whether a stop placement breaches the dollar-risk cap.
Should not fire: asking whether a backtest's ExpR lift survives multiple comparisons.
Should not fire: reviewing the rollback plan of an Alembic migration.
```

The file is 52 lines (budget 80); the checklist has nine items (cap eight to fifteen); no item opens with a shared lead, so `CROSS_CUTTING` gets no row. The checklist is the spec's § D list word for word, plus two citations (`§ Tables and pagers` and `alert_embeds.py`) the lint can check.

- [ ] **Step 4: Write the six eval cases (Write tool, twelve files)**

Each `prompt.md` is the frontmatter below, one blank line, then the prompt line from the table. Each `graders/skill-fired.md` is given whole.

`prompt.md` frontmatter (all six):

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---
```

Prompt lines (no backticks, no paths, no config names: the lint reads them):

| Case folder | Prompt line |
|---|---|
| `fire-admin-table-phone` | The trades table on the admin dashboard has eleven columns. Does it still work on a phone, or does the whole page scroll sideways? |
| `fire-embed-phone-truncation` | On my phone the Discord alert cuts off after the entry line. Are the stop and the targets still readable without opening the full embed? |
| `fire-list-without-pager` | The new closed-trades screen in the admin UI shows every trade since January on one long page. Is that fine on a tablet? |
| `no-fire-stop-placement` | Does this new structural stop rule still keep each trade inside the dollar-risk cap when the stop widens? |
| `no-fire-backtest-expr` | The grid found an ExpR lift on TRAIN for the new filter. Does it survive the multiple comparisons we ran? |
| `no-fire-alembic-migration` | Review the rollback plan for tonight's Alembic migration of the trades table on the VM. |

So `fire-admin-table-phone/prompt.md` reads, whole:

```markdown
---
max_turns: 4
allowed_tools: [Read, Glob, Grep, Skill]
---

The trades table on the admin dashboard has eleven columns. Does it still work on a phone, or does the whole page scroll sideways?
```

Grader for each of the three `fire-*` folders, `graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: ux-designer
min: 1
---

The `ux-designer` skill must load for this prompt: it is a should-fire row of that skill's trigger table.
```

Grader for each of the three `no-fire-*` folders, `graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: ux-designer
min: 0
max: 0
---

The `ux-designer` skill must stay silent on this prompt: it is a should-not-fire row of that skill's trigger table.
```

- [ ] **Step 5: The wiring points**

(a) `.claude/agents/expert-reviewer.md`, description: `the nine roles are listed in docs/claude/skills-tools.md under Expert roles` becomes `the ten roles are listed in docs/claude/skills-tools.md under Expert roles` (nothing else in the description changes). `## Roles`, old:

```markdown
`financial-advisor`, `technical-analyst`, `fundamental-analyst`,
`quant-engineer`, `senior-engineer`.
```

new:

```markdown
`financial-advisor`, `technical-analyst`, `fundamental-analyst`,
`quant-engineer`, `senior-engineer`, `ux-designer`.
```

`## Return shape`: `UNKNOWN ROLE: <given> -- valid: <the nine roles>` becomes `UNKNOWN ROLE: <given> -- valid: <the ten roles>`.

(b) `docs/claude/skills-tools.md`, § Expert roles (v145): `Nine role skills each hold one reviewer's lens` becomes `Ten role skills each hold one reviewer's lens`. Directly after the `` | `senior-engineer` | sonnet | … | `` row, add:

```markdown
| `ux-designer` | sonnet | The admin UI and Discord embeds as a person reads them on phone, tablet and desktop: layout at the three widths, pagers, empty states, embed truncation |
```

(c) `docs/claude/persona.md`, old:

```markdown
reasoned critique, nine role skills hold it — `quant-researcher`,
`staff-engineer`, `veteran-trader`, `risk-manager`, `financial-advisor`,
`technical-analyst`, `fundamental-analyst`, `quant-engineer`,
`senior-engineer` — applied by the `expert-reviewer` agent and run as a panel
```

new:

```markdown
reasoned critique, ten role skills hold it — `quant-researcher`,
`staff-engineer`, `veteran-trader`, `risk-manager`, `financial-advisor`,
`technical-analyst`, `fundamental-analyst`, `quant-engineer`,
`senior-engineer`, `ux-designer` — applied by the `expert-reviewer` agent and
run as a panel
```

and rewrap the rest of that paragraph so no line passes the paragraph's width; words otherwise unchanged.

(d) `AGENTS.md`, old:

```markdown
`quant-engineer` (lookahead, numerics, the OHLCV caches) and `senior-engineer`
(code quality, the complexity limit). A role raises cited `BLOCKING`/`ADVISORY`
findings; it never decides.
```

new:

```markdown
`quant-engineer` (lookahead, numerics, the OHLCV caches), `senior-engineer`
(code quality, the complexity limit) and `ux-designer` (screens and embeds at
phone, tablet and desktop widths). A role raises cited `BLOCKING`/`ADVISORY`
findings; it never decides.
```

(e) Confirm no other live "nine" remains:

```bash
git grep -n -i "\bnine\b" -- AGENTS.md docs/claude/skills-tools.md docs/claude/persona.md .claude/agents/expert-reviewer.md tests/hooks/test_role_skills.py tests/hooks/test_agent_shape.py
```

Expected: exactly the two dated `skills-tools.md` lines ("across the nine role", "Measured over nine plan-writer runs").

- [ ] **Step 6: Regenerate the mirror, run the tests to verify they pass**

```bash
git add .claude/skills/ux-designer
python scripts/dev/sync_codex.py
git add .agents/skills/ux-designer
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/testrun.py file tests/hooks/test_spec_panel_header.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
python scripts/dev/skill_citations.py
git status --porcelain
```

(The first `git add` makes the new skill tracked before the repo-wide citation case reads `git ls-files`; untracked files read as missing.)

Expected: every `testrun.py` call prints `VERDICT: PASS`; the CLI prints `skill citations: clean`; `[ux-designer]` cases appear in `test_role_skills.py` (boundary canonical, four sections, nine items, six cases, the `ux-designer` sonnet row, description cap and hand-off). `git status` lists the new skill folder, `.agents/skills/ux-designer/SKILL.md`, `.codex/agents/expert-reviewer.toml`, the three test files, the agent, the two docs and `AGENTS.md`, and nothing else. If `tests/dev/test_select_tests.py` fails for the new skill folder, stop with `BLOCKED:` naming the assertion (the index authorises only a `DATA_READERS` row, and a skill is not a data file).

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/ux-designer .agents/skills/ux-designer .codex/agents/expert-reviewer.toml .claude/agents/expert-reviewer.md tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py docs/claude/skills-tools.md docs/claude/persona.md AGENTS.md
git commit -m "feat(skills): ux-designer seat -- screens and embeds at three widths (v213)

V213-12. A tenth role skill, reviewer model sonnet: layout audit at the
ui-design widths via Playwright, tables that scroll in their own container,
pagers, empty/loading/error states, embed fields readable on a phone, units
and sign consistent between embed and admin screen, keyboard and screen
reader. Six cases (written, not run). Wired in one commit: ROLES,
TIER_1_AND_3, EXPERT_ROLES, expert-reviewer, the skills-tools roles table,
persona.md, AGENTS.md and the Codex mirror. Live counts nine -> ten; dated
results untouched.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V213-13: `/panel` seat-picking table

**Model:** haiku — one table and one test given verbatim; no judgement calls.

**Files:**
- Modify: `.claude/skills/panel/SKILL.md` (`## Step 2 — Resolve the roles and the target`)
- Modify: `docs/claude/document-conventions.md` (§ The header block, the per-`Edge:` default `Panel:` table: row `| Admin UI | staff-engineer, financial-advisor |` becomes `| Admin UI | ux-designer, staff-engineer, financial-advisor |`; controller decision 2026-11-06, so a UI spec gets the new seat by default)
- Modify: `tests/hooks/test_role_skills.py` (`import re`; `PANEL_STEP_2`, `_panel_seat_rows`, `test_panel_seat_table_names_area_seats`)
- Generated: `.agents/skills/panel/SKILL.md` (by `python scripts/dev/sync_codex.py`)

**Interfaces:**
- Consumes: `ROLES` (with `ux-designer`, V213-12), `_body`, `_section` in `tests/hooks/test_role_skills.py`.
- Produces: nothing later tasks call. V213-14's panel is convened by name (`staff-engineer,senior-engineer`), so it does not read this table.

**Why.** Spec § D: "`/panel` gains a short table mapping a target's type to suggested seats (spec by `Edge:`, backtest result, diff touching `frontend/` or embeds, diff touching `swingbot/core/market/`), so `technical-analyst` and `ux-designer` are picked when their area is touched." The table only suggests: roles named in the argument, or a spec's `**Panel:**` line, still decide (Step 2's first sentence is unchanged). The per-`Edge:` defaults stay in one place, `docs/claude/document-conventions.md` § The header block, and the spec row points there instead of copying them, so the two tables cannot drift apart.

- [ ] **Step 1: Write the failing test**

In `tests/hooks/test_role_skills.py`, add `import re` directly after `import pathlib` if the file does not import it yet (V213-7..V213-11 add no import). Then append at the end of the file:

```python


# v213 § D: /panel suggests seats from the target's type, so the area seats
# (technical-analyst, ux-designer) are picked when their area is touched.
PANEL_STEP_2 = "## Step 2 — Resolve the roles and the target"


def _panel_seat_rows():
    """Target cell -> seats cell of the seat-picking table in /panel Step 2."""
    rows = {}
    for line in _section(_body("panel"), PANEL_STEP_2).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 2 and set(cells[0]) - set("-: "):
            rows[cells[0]] = cells[1]
    rows.pop("Target", None)
    return rows


def test_panel_seat_table_names_area_seats():
    rows = _panel_seat_rows()
    named = {seat for cell in rows.values()
             for seat in re.findall(r"`([a-z-]+)`", cell)}
    assert named and named <= set(ROLES), sorted(named - set(ROLES))

    def seats_for(area):
        return " ".join(cell for target, cell in rows.items() if area in target)

    assert "`ux-designer`" in seats_for("`frontend/`")
    assert "`ux-designer`" in seats_for("embed")
    assert "`technical-analyst`" in seats_for("`swingbot/core/market/`")
    assert "`quant-researcher`" in seats_for("Backtest")
    assert "**Panel:**" in seats_for("Spec") and "`Edge:`" in seats_for("Spec")
```

The `` `([a-z-]+)` `` pattern reads seat names only: `` `**Panel:**` ``, `` `Edge:` `` and `` `document-conventions.md` `` never match it, so `named <= set(ROLES)` fails a misspelt or unknown seat and nothing else.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: `VERDICT: FAIL`, exactly one test: `test_panel_seat_table_names_area_seats` (`assert named and ...`: the table does not exist, so `named` is empty). Every other case passes.

- [ ] **Step 3: Add the table to `/panel`**

In `.claude/skills/panel/SKILL.md`, `## Step 2 — Resolve the roles and the target`, the paragraph stays as it is:

```markdown
Roles come from the argument, or from the spec's `**Panel:**` line when Claude
runs this itself. Every role must be a row of the roles table; an unknown role
stops the panel and names the valid ones -- never substitute a near match. The
target is one or more paths, or a git range (`main...<branch>`).
```

Directly after it (one blank line between), insert:

```markdown
With neither (an on-demand panel Claude convenes itself), suggest seats from
the target's type and say which you picked; an argument always wins.

| Target | Suggested seats |
|---|---|
| Spec | its `**Panel:**` line; with none, the default for its `Edge:` (`document-conventions.md` § The header block) |
| Backtest result, grid or screen verdict | `quant-researcher`, `quant-engineer` |
| Diff touching `frontend/` or a Discord embed | `ux-designer`, `senior-engineer` |
| Diff touching `swingbot/core/market/` | `technical-analyst`, `quant-engineer` |
```

Nothing else in the skill changes. It grows by ten lines and stays under the 80-line budget (`wc -l .claude/skills/panel/SKILL.md` prints at most 65). Lint check, by hand: `document-conventions.md` is a bare doc name, so it resolves from `docs/claude/`, and its `## The header block` heading starts the cite; `frontend/` and `swingbot/core/market/` carry no file extension, so the path rule skips them; no UPPER_SNAKE word is added.

- [ ] **Step 3b: Make `ux-designer` a default seat for UI specs**

In `docs/claude/document-conventions.md` § The header block, change the row `| Admin UI | staff-engineer, financial-advisor |` to `| Admin UI | ux-designer, staff-engineer, financial-advisor |` (three seats, the `Panel:` maximum). Change nothing else in that file. If `AGENTS.md` mirrors that table row, update the mirror the same way.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/skill_citations.py
git status --porcelain
```

Expected: every `testrun.py` call prints `VERDICT: PASS` (`test_panel_dispatches_the_expert_reviewer_serially` still finds every `PANEL_PHRASES` entry); the CLI prints `skill citations: clean`; `git status` lists `.claude/skills/panel/SKILL.md`, `.agents/skills/panel/SKILL.md` and `tests/hooks/test_role_skills.py`, nothing else.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/panel/SKILL.md .agents/skills/panel/SKILL.md tests/hooks/test_role_skills.py docs/claude/document-conventions.md AGENTS.md
git commit -m "docs(skills): /panel suggests seats by target type (v213)

V213-13. With no role argument and no Panel: line, /panel suggests seats
from the target: a spec defers to its Edge: default in
document-conventions.md, a backtest result to quant-researcher and
quant-engineer, a frontend or embed diff to ux-designer and
senior-engineer, a swingbot/core/market/ diff to technical-analyst and
quant-engineer. test_role_skills pins that every named seat is a role and
that the area seats are picked.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase E — Panel, merge, close-out

### Task V213-14: Pre-close-out panel (staff-engineer, senior-engineer), merge, CI watch, `/close-out` with Step 5b

**Model:** sonnet — the controller's ritual: follow the `panel`, `worktree-lifecycle` and `close-out` skills in order; judgement only in triaging findings and CI failures.

**Who runs it.** The controller, in the main session on `main` — not a `task-implementer`. Standing permission covers `/close-out` once every task is merged (root `CLAUDE.md` § Naming specs and plans). **No step runs the full suite locally**: CI runs it after the push, and a failing test is fixed and re-run alone.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-v213-skills-alignment.md` (`## Panel review`, a new "Implementation review" block; committed on the branch, before the merge)
- Move (by `/close-out` Step 6): `docs/superpowers/plans/2026-11-06-v213-skills-alignment_{0-index,1-lint-and-drift,1b-drift-cleanup,2-seat-coverage,3-ux-designer}.md` to `docs/superpowers/plans/implemented/`; the spec to `docs/superpowers/specs/implemented/`
- Fix commits, only if the panel or CI asks for them: any file inside the index's Global Constraints list

**Interfaces:**
- Consumes: the branch `2026-11-06-v213-skills-alignment` with V213-1..V213-13 committed; `scripts/dev/skill_citations.py` (CLI prints `skill citations: clean` when green, V213-2); the `panel`, `worktree-lifecycle` and `close-out` skills.
- Produces: v213 merged on `main`, CI green, plan and spec in `implemented/`, worktree and branch removed.

`WT` below stands for `.claude/worktrees/2026-11-06-v213-skills-alignment`; `BR` for the branch `2026-11-06-v213-skills-alignment`. Write them out in full in each command.

- [ ] **Step 1: The branch is complete and the main tree untouched**

```bash
git -C .claude/worktrees/2026-11-06-v213-skills-alignment log --oneline main..HEAD
git -C .claude/worktrees/2026-11-06-v213-skills-alignment status --porcelain
git status --porcelain
```

Expected: the log carries a commit for each of V213-1..V213-13 (V213-3's body records the red list); the worktree prints nothing; the main tree shows only what it showed before the run started (other sessions' files such as `.claude/settings.json`), no file v213 touches. A v213 file modified in the main tree is a subagent that wrote to the wrong tree: compare it with the branch's commit and revert it only if the diff matches that commit.

- [ ] **Step 2: Scope gate — nothing outside the Global Constraints list changed**

```bash
python - <<'PY'
import subprocess
WT = ".claude/worktrees/2026-11-06-v213-skills-alignment"
names = subprocess.run(["git", "-C", WT, "diff", "--name-only", "main...HEAD"],
                       capture_output=True, text=True, check=True).stdout.split()
prefixes = (".claude/skills/", ".claude/agents/", ".agents/", ".codex/agents/", "tests/hooks/")
exact = {"AGENTS.md", "scripts/dev/skill_citations.py", "docs/claude/skills-tools.md",
         "docs/claude/persona.md", "docs/claude/testing-cost.md",
         "docs/claude/document-lifecycle.md"}
authorised = {"scripts/dev/select_tests.py"}   # one DATA_READERS row only (index OPEN)
bad = [n for n in names if not n.startswith(prefixes) and n not in exact | authorised]
print("files:", len(names), "| outside scope:", bad or "none")
print("authorised extras:", [n for n in names if n in authorised] or "none")
PY
```

Expected: `outside scope: none`. Anything under `swingbot/`, `frontend/`, `bot.py` or `admin_ui.py` is a review stop: revert it on the branch before the panel. If `scripts/dev/select_tests.py` is listed, `git -C .claude/worktrees/2026-11-06-v213-skills-alignment diff main...HEAD -- scripts/dev/select_tests.py` must show one added `DATA_READERS` row for `tests/hooks/skill_citation_allowlist.txt` and nothing else.

- [ ] **Step 3: Narrow verification on the branch tip**

From a session rooted in the worktree (`EnterWorktree` on `WT`, or dispatch `test-runner` naming `WT`; never `cd` inside a Bash command), run:

```bash
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_gate_skill.py
python scripts/dev/testrun.py file tests/hooks/test_handoff_wiring.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
python scripts/dev/testrun.py file tests/hooks/test_spec_panel_header.py
python scripts/dev/sync_codex.py --check
python scripts/dev/skill_citations.py
python scripts/dev/complexity_gate.py
```

Expected: nine `VERDICT: PASS` lines; `sync_codex.py --check` exits 0 with no drift listed; `skill citations: clean`; the complexity gate passes (`scripts/dev/skill_citations.py` is the only new Python, every function under fifteen). Leave the worktree session (`ExitWorktree`, action `keep`) before Step 6.

- [ ] **Step 4: Pre-close-out panel**

Invoke the `panel` skill:

```text
/panel staff-engineer,senior-engineer main...2026-11-06-v213-skills-alignment (worktree .claude/worktrees/2026-11-06-v213-skills-alignment)
```

The roles are the spec's `**Panel:**` line; they run serially through `expert-reviewer`. For each surviving finding:

- `BLOCKING`: fix it on the branch in a scoped commit (with its Codex mirror if it touches a skill, agent or rule), re-run only the test file it touches with `testrun.py file`, and record `-- applied (<sha>)`.
- `ADVISORY`: apply it the same way, or record `-- rejected: <why>`.
- A finding asking to change anything under `swingbot/` or `frontend/` is rejected: the spec's § What stays.

Then append to the spec's `## Panel review` section, on the branch, after the spec-review list:

```markdown

Implementation review, <YYYY-MM-DD>, on `main...2026-11-06-v213-skills-alignment` at `<branch sha before fixes>`.

- staff-engineer: <one line> -- applied (<sha>)
- senior-engineer: <one line> -- rejected: <why>
```

A role that returned `CLEAN` gets one line, `- <role>: CLEAN`. Commit on the branch:

```bash
git -C .claude/worktrees/2026-11-06-v213-skills-alignment add docs/superpowers/specs/2026-11-06-v213-skills-alignment.md
git -C .claude/worktrees/2026-11-06-v213-skills-alignment commit -m "docs(v213): implementation panel review recorded

staff-engineer and senior-engineer over main...2026-11-06-v213-skills-alignment;
every BLOCKING finding applied or rejected with a reason.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

No `BLOCKING` finding may stay unresolved past this step (`/close-out` Step 2 would stop on it).

- [ ] **Step 5: Merge**

Invoke the `worktree-lifecycle` skill first (concurrent sessions share this tree). Then, from the main tree on `main`:

```bash
git fetch origin
git status -sb
git worktree list
git log --oneline -3 main
git merge --no-ff 2026-11-06-v213-skills-alignment -m "merge: v213 skills alignment -- citation lint, drift fixes, seat coverage, ux-designer seat

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `main` is not behind `origin/main` before the merge (pull first if it is, and re-check that nothing another session merged touches a v213 file); the merge completes with no conflict. Never stash, reset or check out the main tree's unrelated local changes; if the merge refuses because one of them would be overwritten, stop and ask the partner with `AskUserQuestion`.

- [ ] **Step 6: Push and watch CI until green**

```bash
git push origin main
gh run list --branch main --limit 3
gh run watch <run-id> --exit-status
```

Expected: every job green (`0 failed`, `0 xfailed`), the `tests/hooks/` job included. On a red job: `gh run view <run-id> --log-failed`, fix on `main` in a scoped commit, re-run that test alone (`python scripts/dev/testrun.py file <test>` or `python -m pytest <path>::<test>`), push, and watch the new run. Repeat until green (`docs/claude/working-conventions.md` § Pipeline watch). Never re-run the whole suite locally.

- [ ] **Step 7: `/close-out`, Step 5b included**

Invoke the `close-out` skill. v213 specifics, step by step:

- **Step 2 (panel):** satisfied by this task's Step 4 when no commit after it changed a skill, agent or rule. If a CI fix in Step 6 did, run `/panel staff-engineer,senior-engineer` over just those commits (`<first fix>^..main`) and record them the same way.
- **Step 3/4 (bump):** `Bump: none`, so no release commit and no `version_history.json` regeneration.
- **Step 5 (prediction):** check `Bump: none` and `Edge: none (integrity)` held:

  ```bash
  git diff --name-only "$(git log --merges -1 --format=%H main)^1" main -- swingbot frontend bot.py admin_ui.py
  ```

  It compares `main` before the merge with `main` now (merge plus any CI fix) and must print nothing. A non-empty list means the header's prediction failed: amend it per the skill.
- **Step 5b (align skills):** v213's diff is itself skill text, so grep for every rule it replaced, across everything an agent reads:

  ```bash
  git grep -n -i "pre-commit gate\|nine role\|both containers\|testrun.py full" -- .claude/skills .claude/agents AGENTS.md docs/claude
  git grep -n "radon cc" -- .claude/skills .claude/agents AGENTS.md
  git grep -n "swingbot/commands/scanning.py\|jsonio.write_json\|all_trades()" -- .claude/skills .claude/agents AGENTS.md
  ```

  Every hit must be one of: a dated result (`docs/claude/skills-tools.md` "across the nine role"), the shared complexity wording ("... is for iterating"), a `testrun.py full` line that also says "never" or "CI" (the `gate` structural test's rule), or a line the citation allowlist names on purpose (`task-brief` 3e's deleted-shim list). Fix any other hit in a `docs(skills): align <skill> with v213` commit with its Codex mirror (`python scripts/dev/sync_codex.py`, `testrun.py file tests/hooks/test_codex_mirror.py`); otherwise write `skills: none affected` in the move commit body.
- **Step 6 (move):**

  ```bash
  git mv docs/superpowers/plans/2026-11-06-v213-skills-alignment_0-index.md docs/superpowers/plans/implemented/
  git mv docs/superpowers/plans/2026-11-06-v213-skills-alignment_1-lint-and-drift.md docs/superpowers/plans/implemented/
  git mv docs/superpowers/plans/2026-11-06-v213-skills-alignment_1b-drift-cleanup.md docs/superpowers/plans/implemented/
  git mv docs/superpowers/plans/2026-11-06-v213-skills-alignment_2-seat-coverage.md docs/superpowers/plans/implemented/
  git mv docs/superpowers/plans/2026-11-06-v213-skills-alignment_3-ux-designer.md docs/superpowers/plans/implemented/
  git mv docs/superpowers/specs/2026-11-06-v213-skills-alignment.md docs/superpowers/specs/implemented/
  git commit -m "docs(v213): close out -- plan and spec to implemented/

  Merged and CI green. Bump: none held (no swingbot/ or frontend/ change).
  skills: none affected

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

  Replace `skills: none affected` with `skills: aligned in <sha>` when Step 5b made a commit.
- **Step 7 (worktree):**

  ```bash
  git rev-list --count main..2026-11-06-v213-skills-alignment
  git worktree remove .claude/worktrees/2026-11-06-v213-skills-alignment
  git branch -d 2026-11-06-v213-skills-alignment
  git push origin main
  ```

  The count must print `0` before anything is removed; non-zero means stop (`docs/claude/git-safety.md`). Use `branch -d`, never `-D`. The branch name carries no `backup`.

Expected at the end: `git log --oneline -4` shows the move commit above the merge (and any fix or align commits); `git worktree list` no longer lists `WT`; the CI run for the last push is green; no full-suite run happened locally at any step.

