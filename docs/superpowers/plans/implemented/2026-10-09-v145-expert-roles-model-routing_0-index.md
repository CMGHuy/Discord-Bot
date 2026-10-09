# v145 Expert role skills, review panels and per-task model routing: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V145-3` or `grep -n "^### Task V145-3:" -A 360 docs/superpowers/plans/2026-10-09-v145-expert-roles-model-routing_*.md` (V145-1 is the longest task, about 520 lines; V145-6 and V145-7 about 250).

**Bump:** none
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`](../specs/2026-10-09-v145-expert-roles-model-routing.md)

**Goal:** Give the Claude setup nine expert role skills, one read-only `expert-reviewer` agent that applies any one of them, a `/panel` ritual that runs a spec's chosen roles serially and merges their findings, a `**Panel:**` spec header and a per-task `**Model:**` plan stamp (both enforced by tests from v146), and an escalation ladder that replaces "fails review twice → Opus inline" — with the Codex mirror in every commit.

**Architecture:** Each role is a model-invocable skill under `.claude/skills/<role>/` with four fixed sections (Lens, Checklist, Red flags, Out of scope), a Trigger table and v96-style trigger cases; `tests/hooks/test_role_skills.py` pins the shape, and the roles table in `docs/claude/skills-tools.md` is the one place each role's reviewer model is recorded. `expert-reviewer` (sonnet by default, read-only) loads one role skill and returns cited `BLOCKING`/`ADVISORY` findings; `/panel` dispatches it once per role with that role's model as the override. Two new header tests (`test_spec_panel_header.py`, `test_plan_model_stamp.py`) exempt v145 and below by number; `docs/claude/model-routing.md` holds the tier rubric and the escalation ladder.

**Tech Stack:** Markdown skills and agents, Python 3.11 + pytest for the shape tests. Existing, verified with `git grep -n` / `ls`: `tests/hooks/test_skill_shape.py` (`TIER_1_AND_3`, `TIER_2`, `MODEL_RUN_RITUALS`, `_THRESHOLD_RE`, `MAX_SKILL_LINES = 80`), `tests/hooks/test_agent_shape.py` (`EXPECTED`, `_read_agent`, `_skills`), `tests/hooks/test_codex_mirror.py`, `tests/hooks/test_spec_screen_header.py` (the pattern the two header tests copy), `scripts/dev/sync_codex.py` (`check`, `write`, `_missing_mentions`), `scripts/dev/select_tests.py` (`DATA_READERS`), `tests/dev/test_select_tests.py` (`test_no_path_a_test_reads_is_classified_inert`), `scripts/dev/testrun.py`, `.claude/agents/{plan-writer,task-reviewer,task-implementer}.md`, `.claude/skills/{new-doc,close-out,task-brief}/SKILL.md`, `docs/claude/{skills-tools,persona,document-conventions}.md`, `AGENTS.md`, `CLAUDE.md`. Every repo path a role skill cites was checked to exist at writing (see each task's "Cited paths" line).

## Where to work

- **Branch and worktree:** `2026-10-09-v145-expert-roles-model-routing` at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v145-expert-roles-model-routing`. V145-1 Step 0 creates it with the `worktree-lifecycle` skill. Root the controller session in it (`EnterWorktree` with that path) so dispatched implementers can write there; every command below runs from the worktree root. Never `cd` in Bash; use absolute paths or `git -C`.
- **The word "eval" in a command is refused in a worktree-isolated session** (any Bash command containing that substring, however quoted). So: stage a role skill by its directory (`git add .claude/skills/risk-manager`), never by a path through its trigger-case folder; never put the word in a commit message (say "trigger cases"); create case files with the Write tool, not a shell loop naming the folder. V145-9, which runs the cases, runs from the **main-tree** session (`ExitWorktree` with `keep`, ask the partner once first) against the worktree's skill paths, then re-enters the worktree for any fix.
- **Skills to load:** `worktree-lifecycle` before creating, merging or removing the worktree. No task touches `swingbot/`, so `no-lookahead`, `backtest-gate` and `edge-module` do not apply.

## Global constraints

Every task's requirements implicitly include these, copied from the spec and the repo rules:

- `Bump: none` — Claude/Codex tooling only. No change under `swingbot/`, `frontend/`, `bot.py`, `admin_ui.py`. The only non-doc, non-`.claude/` code touched is dev tooling: `scripts/dev/select_tests.py` (three `DATA_READERS` rows) and its test `tests/dev/test_select_tests.py`.
- Nine role skills, exactly these names and reviewer models: `quant-researcher` opus, `staff-engineer` opus, `veteran-trader` sonnet, `risk-manager` sonnet, `financial-advisor` sonnet, `technical-analyst` sonnet, `fundamental-analyst` sonnet, `quant-engineer` sonnet, `senior-engineer` sonnet. No reviewer runs on haiku.
- Each role skill has four sections in this order — `## Lens`, `## Checklist` (8–15 `- ` items, each citing a repo doc or code area), `## Red flags`, `## Out of scope` — then `## Trigger table` with at least three `Should fire:` and three `Should not fire:` rows.
- Every role skill states: it raises findings and **never decides**, **never lowers a gate**, no intuition overrides `backtest-gate`, `pooled-numbers` or a closed pre-registration, and it quotes no pooled figure it did not re-derive. `financial-advisor` states its output is **educational, not personalised financial advice**, and reviews the bot's output, never the partner's finances.
- Every new or edited `SKILL.md` (except the grandfathered `gate` and `task-brief`) stays at or under 80 lines and restates no bare threshold: no `<`, `>`, `<=`, `>=` or `=` followed by a number, and no number directly followed by `R` or `pp` (`_THRESHOLD_RE` in `tests/hooks/test_skill_shape.py`). Cite `docs/claude/` instead.
- Role skills are model-invocable → registered in `TIER_1_AND_3`. `panel` is a model-run ritual → registered in `TIER_2` and `MODEL_RUN_RITUALS`, and its description contains the exact text `Run as /panel, or by Claude itself`.
- `expert-reviewer`: tools exactly `Read, Grep, Glob, Bash, Skill` (Bash for read-only git), default model `sonnet`, preloads no skill, returns numbered findings tagged `BLOCKING`/`ADVISORY` or `CLEAN`, every finding cites `file:line`, a git range or a doc section, an unknown role is an error naming the valid roles.
- `**Panel:**` applies to specs numbered v146 or above; `**Model:**` to plans numbered v146 or above. v145 and earlier are exempt and never retrofitted. (This plan stamps `**Model:**` voluntarily.)
- Escalation ladder replaces "fails review twice → Opus inline": same implementer once (same tier) → fresh implementer one tier up with findings → Opus inline; each step logged in `.superpowers/sdd/progress.md` as `<task id>: <from>→<to> (<reason>)`. `task-reviewer` stays on sonnet whatever the task's tier.
- Every Claude setup change ships its Codex mirror in the same commit: run `python scripts/dev/sync_codex.py`, and `AGENTS.md` names every new skill and agent in backticks and `docs/claude/model-routing.md` by path (`_missing_mentions` in `scripts/dev/sync_codex.py`).
- `CLAUDE.md` stays under 200 lines (`wc -l CLAUDE.md`).
- Any Python written or changed ends at cyclomatic complexity under 15 (`python -m radon cc -s -n C <files>` prints nothing new).
- Per-task check: `python scripts/dev/testrun.py file tests/hooks/` (plus `tests/dev/test_select_tests.py` where a task names it). The full suite runs once, in V145-10.
- Do not run the panel on this plan (v145 has no `**Panel:**` line; the roles do not exist until it lands).

## Parts

| Part | File | Tasks |
|---|---|---|
| 0 | this index | header, constraints, file map, parallelisation |
| 1 | `2026-10-09-v145-expert-roles-model-routing_1-role-skills.md` | Phase 1: V145-1 (`quant-researcher`, `risk-manager`, `financial-advisor`, `test_role_skills.py`, roles table), V145-2 (`veteran-trader`, `technical-analyst`, `fundamental-analyst`), V145-3 (`staff-engineer`, `quant-engineer`, `senior-engineer`) |
| 2 | `2026-10-09-v145-expert-roles-model-routing_2-reviewer-panel-stamps.md` | Phase 2: V145-4 (`expert-reviewer`, `task-reviewer` preload), V145-5 (`/panel`); Phase 3: V145-6 (`**Panel:**` header test and conventions), V145-7 (`model-routing.md`, `**Model:**` stamp test, plan-writer, new-doc, task-brief) |
| 3 | `2026-10-09-v145-expert-roles-model-routing_3-docs-verification.md` | Phase 4: V145-8 (close-out panel gate, skills-tools, persona, CLAUDE.md, AGENTS.md); Phase 5: V145-9 (run the 54 trigger cases), V145-10 (full suite) |

## File map

| File | Created / modified by | Responsibility |
|---|---|---|
| `.claude/skills/{quant-researcher,risk-manager,financial-advisor}/SKILL.md` + trigger cases | V145-1 | three role lenses |
| `.claude/skills/{veteran-trader,technical-analyst,fundamental-analyst}/SKILL.md` + trigger cases | V145-2 | three role lenses |
| `.claude/skills/{staff-engineer,quant-engineer,senior-engineer}/SKILL.md` + trigger cases | V145-3 | three role lenses |
| `tests/hooks/test_role_skills.py` | V145-1 (create), V145-2, V145-3 (`ROLES` rows), V145-5 (panel test), V145-8 (close-out and ladder tests) | role-skill shape, cases, reviewer-model table |
| `tests/hooks/test_skill_shape.py` | V145-1..3 (`TIER_1_AND_3`), V145-5 (`TIER_2`, `MODEL_RUN_RITUALS`) | tier registration |
| `docs/claude/skills-tools.md` | V145-1 (§ Expert roles), V145-2, V145-3 (rows), V145-8 (agent table, plan loop, ladder), V145-9 (case results line) | roster + reviewer models; agent routing |
| `.claude/agents/expert-reviewer.md` | V145-4 | one-role read-only review |
| `.claude/agents/task-reviewer.md` | V145-4 | preloads `senior-engineer` |
| `tests/hooks/test_agent_shape.py` | V145-4 | pins the two agents |
| `.claude/skills/panel/SKILL.md` | V145-5 | dispatch serially, merge, record |
| `tests/hooks/test_spec_panel_header.py` | V145-6 | `**Panel:**` gate from v146 |
| `tests/hooks/test_plan_model_stamp.py` | V145-7 | `**Model:**` gate from v146 |
| `scripts/dev/select_tests.py` | V145-1 (`docs/claude/` row), V145-6 (specs row), V145-7 (plans row) | route doc edits to the new tests |
| `tests/dev/test_select_tests.py` | V145-1 | fixture readers and expected routing for `docs/claude/` |
| `docs/claude/document-conventions.md` | V145-6 (`Panel:`), V145-7 (`Model:`) | header rules |
| `docs/claude/model-routing.md` | V145-7 | tier rubric, stamp, escalation ladder |
| `.claude/agents/plan-writer.md`, `.claude/skills/new-doc/SKILL.md`, `.claude/skills/task-brief/SKILL.md` | V145-7 | write / suggest / copy the stamps |
| `.claude/skills/close-out/SKILL.md` | V145-8 | pre-close-out panel gate |
| `docs/claude/persona.md`, `CLAUDE.md` | V145-8 | pointer paragraph; one rule + reference row |
| `AGENTS.md` | every task V145-1..V145-8 | condensed Codex mirror |
| `.agents/skills/*/SKILL.md`, `.codex/agents/*.toml` | every task that changes a skill or agent (generated by `sync_codex.py`) | Codex copies |

## Parallelisation

**Sequential throughout — no parallel group exists in this plan.** Every task V145-1..V145-8 edits `AGENTS.md` (the Codex mirror must land in the same commit as the setup change it mirrors), so no two of them have disjoint files. The edges, in order:

- **V145-1 → V145-2 → V145-3:** each appends to `TIER_1_AND_3` in `tests/hooks/test_skill_shape.py`, to `ROLES` in `tests/hooks/test_role_skills.py` (created by V145-1), to the roles table in `docs/claude/skills-tools.md` (created by V145-1) and to the role paragraph in `AGENTS.md`. V145-1 also edits `scripts/dev/select_tests.py`, which V145-6 and V145-7 edit again.
- **V145-3 → V145-4:** `task-reviewer` preloads `senior-engineer`, which V145-3 creates; `expert-reviewer` lists all nine roles, the last three of which V145-3 creates.
- **V145-4 → V145-5:** `/panel` dispatches `expert-reviewer` (contract dependency); both edit `AGENTS.md`.
- **V145-5 → V145-6:** the `**Panel:**` rules in `document-conventions.md` name the `panel` skill and the roster; both tasks edit `AGENTS.md`.
- **V145-6 → V145-7:** both edit `docs/claude/document-conventions.md`, the `DATA_READERS` table in `scripts/dev/select_tests.py` and `AGENTS.md`.
- **V145-7 → V145-8:** V145-8's docs point at `docs/claude/model-routing.md` (created by V145-7) and its close-out step runs `/panel` (V145-5); both edit `AGENTS.md`.
- **V145-8 → V145-9:** the trigger cases run against the final descriptions; V145-9 records its result in `skills-tools.md`, which V145-8 edits.
- **V145-10 last:** the one full-suite run over everything.

The standing one-subagent-at-a-time rule (`docs/claude/skills-tools.md`) would serialise these anyway; this section records that the files force it too.
