# v145 — Expert role skills, review panels, and per-task model routing

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** none (Claude/Codex tooling only; no bot or ui code changes)
**Edge:** none (integrity) — review and dispatch tooling. It changes who checks a spec, plan or diff and which model implements a plan task; it issues no signal and moves no threshold. Any effect on expectancy is indirect (fewer fake edges shipped, fewer mis-implemented tasks) and is not claimed.
**Screen:** exempt (integrity)
**Status:** spec written 2026-10-09; no plan yet.

## Why

Two gaps in the current Claude setup:

1. **Expertise is one blended persona.** `docs/claude/persona.md` makes the main
   session hold four seats at once. There is no way to ask *one* lens — a
   risk manager, a fundamental analyst — for a focused, separately-reasoned
   critique of a spec or diff. The partner asked for named expert roles
   (financial advisor, veteran trader, senior/staff engineer, quant engineer,
   technical and fundamental analysis) available as skills.
2. **Every implementation task runs on Sonnet.** `task-implementer` is pinned
   to `sonnet` (`.claude/agents/task-implementer.md`). A version bump and an
   entry-signal rewiring get the same model. Plans carry no model tier, and the
   only escalation is "fails review twice → Opus inline"
   (`docs/claude/skills-tools.md` § Which agent for what).

## Decisions (taken in brainstorming, 2026-10-09)

| Question | Decision |
|---|---|
| Form of a role | **Both**: a skill holds the knowledge and checklist; a reviewer agent loads it |
| Roster | 8 consolidated roles **plus a literal financial-advisor** (9 total) |
| Agent structure | **9 skills + 1 parameterised `expert-reviewer` agent** (not one agent per role) |
| Model choice for plan tasks | **Plan-writer stamps a `Model:` tier per task, plus an escalation ladder** |
| When reviewers run | **The spec stamps a `Panel:`**; it runs at spec review and before close-out; otherwise on demand via `/panel` |

## Design

### 1. Role skills

Nine new skills under `.claude/skills/<role>/SKILL.md`. Each has four sections,
in this order: **Lens** (what this role alone owns), **Checklist** (8–15
concrete checks, each citing the repo doc or code area it applies to),
**Red flags** (what earns a `BLOCKING` finding) and **Out of scope** (what it
hands to which other role, so panel findings do not overlap). Each skill passes
`tests/hooks/test_skill_shape.py` as it stands. Each gets an `evals/`
directory in the v96 style, checking it fires on its own lens and not on a
neighbouring role's.

| Role | Reviewer model | Lens |
|---|---|---|
| `quant-researcher` | opus | Sample size, overfitting, multiple comparisons, pre-registration discipline, whether an ExpR claim holds up |
| `staff-engineer` | opus | Cross-cutting design: seams, migrations, VM ops, blast radius, long-run cost |
| `veteran-trader` | sonnet | Tradeability: fills, gaps, liquidity, regime, whether an alert is actionable before the open |
| `risk-manager` | sonnet | 2% dollar risk, portfolio heat, correlated exposure, stop placement |
| `financial-advisor` | sonnet | Allocation, account fit, tax drag of swing turnover, whether alert frequency and risk suit a real-money retail trader |
| `technical-analyst` | sonnet | S/R, pattern and indicator logic: correct in code and true to how the setup is traded |
| `fundamental-analyst` | sonnet | Earnings, catalysts, sector and macro concentration: the bot's blind spot |
| `quant-engineer` | sonnet | Backtest and data plumbing: lookahead (loads `no-lookahead`), numerics, the two OHLCV caches, reproducibility |
| `senior-engineer` | sonnet | Code-level quality, complexity < 15, reads like its surroundings. `task-reviewer` loads this skill too |

No reviewer runs on Haiku: reviewing means judging.

**Hard boundaries, stated in every role skill:**
- A role **raises findings; it never decides** and never lowers a gate. The
  `persona.md` rule "raises the bar, never lowers a gate" applies verbatim. No
  trader intuition overrides `backtest-gate`, `pooled-numbers` or a closed
  pre-registration.
- A role quotes no pooled figure it did not re-derive (`pooled-numbers`).
- `financial-advisor` states that its output is **educational, not
  personalised financial advice**. It reviews whether the *bot's output* is
  suitable for a retail real-money trader, not the partner's personal finances.

### 2. `expert-reviewer` agent

`.claude/agents/expert-reviewer.md`, passing `tests/hooks/test_agent_shape.py`.

- **Tools:** Read, Grep, Glob, Bash (git read commands only), Skill. No Edit,
  Write or NotebookEdit: it is read-only.
- **Default model:** sonnet. The controller passes the role's model from the
  table above as the dispatch `model` override.
- **Input:** `role=<name>` plus one or more target paths or a git range.
- **Behaviour:** load `.claude/skills/<role>/SKILL.md`, apply its checklist
  to the target, and return numbered findings, each tagged `BLOCKING` or
  `ADVISORY`, or the single word `CLEAN`.
- **Evidence rule:** every finding cites `file:line`, a git range or a doc
  section. The controller drops a finding with no citation.
- **Unknown role:** return an error naming the valid roles; never improvise one.

### 3. Panels

**Spec header.** Every spec numbered v146 or above carries
`**Panel:** <role>[, <role>[, <role>]]`, placed directly below `**Screen:**`,
with 1–3 roles that each exist as a skill. (v145 itself is exempt, because the
roles do not exist until it is implemented.) `/new-doc` suggests a default:

| Spec is about… | Default panel |
|---|---|
| New entry strategy or filter (`Edge: expectancy`) | quant-researcher, veteran-trader, technical-analyst |
| Exits, sizing, stops (`Edge: harvest`) | risk-manager, veteran-trader, quant-researcher |
| Alert volume or cadence (`Edge: volume`) | veteran-trader, financial-advisor, risk-manager |
| Earnings, catalysts, sector filters | fundamental-analyst, quant-researcher, risk-manager |
| Infra, schema, ops (`Edge: none (integrity)`) | staff-engineer, quant-engineer |
| Admin UI | staff-engineer, financial-advisor |

The author may override the default. The header records the final choice.

**When a panel runs:**
1. **Spec review:** after the spec is written and committed, before the
   partner's review. The roles are dispatched **serially**, following the
   standing "serial, one at a time" rule. Opus merges their findings, revises
   the spec, and records each finding's outcome (`applied` / `rejected: <why>`)
   in a `## Panel review` section of the spec.
2. **Pre-close-out:** the same panel reviews the plan's full diff
   (`main...<branch>`) and its recorded results. An unresolved `BLOCKING`
   finding stops `/close-out`. The `close-out` skill gains this check.
3. **On demand:** `/panel <role>[,<role>…] <target>` runs any roles on any
   spec, plan, diff or backtest result. `/panel` is a new skill that only
   dispatches `expert-reviewer` and merges the findings.

### 4. Per-task model routing

**New doc `docs/claude/model-routing.md`**, which holds the rubric:

| Tier | A task gets it when… | Examples |
|---|---|---|
| `haiku` | Fully specified, no judgement, the diff is fixed by the brief | Doc/config edits, `VERSION.json` bump, a fixture, a rename, a copied pattern |
| `sonnet` (default) | A normal TDD task inside one module, with the behaviour given by the spec | A new metric, an embed field, a store method, an admin endpoint |
| `opus` | Any of: entry signals or no-lookahead territory, a schema migration, crosses at least 2 `swingbot/core` packages, splits a legacy function at complexity ≥ 15, statistical code that feeds a gate | Edge module wiring, an Alembic revision, a backtest gate change |

When a task matches more than one row, the higher tier wins.

**Stamp.** In plans numbered v146 or above, `plan-writer` writes
`**Model:** <haiku|sonnet|opus> — <one-clause reason>` as the first line under
every `### Task` heading. `/task-brief` copies it into the brief. The controller
passes the tier as the `model` override when it dispatches `task-implementer`,
whose own default stays `sonnet`.

**Escalation ladder.** This replaces "fails review twice → Opus inline":
1. `task-reviewer` returns blocking findings: SendMessage the same implementer
   once (same tier).
2. Still blocking: re-dispatch a fresh implementer **one tier up**, with the
   findings attached.
3. Still blocking at opus: Opus implements the task inline in the main session.

Each escalation is logged in `.superpowers/sdd/progress.md` as
`<task id>: <from>→<to> (<reason>)`. The logs are the evidence for retuning the
rubric. `task-reviewer` stays on sonnet whatever the task's tier, so review is
never weaker than a haiku implementation.

### 5. Documentation and the Codex mirror

All in the same commit as the code they describe:
- `CLAUDE.md`: one short rule naming the `Panel:` and `Model:` stamps, with a
  pointer to `model-routing.md` and a new reference-table row. It must stay
  under 200 lines.
- `docs/claude/skills-tools.md`: add `expert-reviewer` to § Which agent for
  what, add a roles table, and replace the escalation sentence.
- `docs/claude/persona.md`: one paragraph pointing at the role skills.
- `docs/claude/document-conventions.md`: the `Panel:` and `Model:` headers.
- `plan-writer` agent, `new-doc` skill, `task-brief` skill, `close-out` skill:
  each learns its part of the stamps.
- `AGENTS.md`: condensed mirror. Run `python scripts/dev/sync_codex.py` so the
  ten new skills and the agent reach Codex.

### 6. Model tiers in Codex (amendment, 2026-10-09)

The partner asked that the roles and their models hold in Codex as well as
Claude. Before this amendment, `sync_codex.py` dropped `model:`, so every Codex
agent ran on the session default. `CODEX_TIERS` in `scripts/dev/sync_codex.py`
now maps each Claude tier to a Codex model and reasoning effort, taken from the
partner's local Codex model list and chosen by the partner:

| Tier | Codex model | Reasoning effort |
|---|---|---|
| `haiku` | `gpt-6-luna` | `low` |
| `sonnet` | `gpt-6.1-sol` | `medium` |
| `opus` | `gpt-6-astra` | `high` |

The generator writes `model` and `model_reasoning_effort` into every
`.codex/agents/*.toml`. `AGENTS.md` carries the same table, so a `Model:` stamp
or an expert-role reviewer tier means the same thing when Codex dispatches it.
`tests/hooks/test_codex_mirror.py` fails if an agent's tier is unmapped, if a
TOML lacks the mapped pair, or if `AGENTS.md` omits a tier row.
`docs/claude/model-routing.md` (V145-7) points at this map.

## Testing

- `tests/hooks/test_codex_mirror.py`: already exists and must stay green.
- `tests/hooks/test_skill_shape.py` / `test_agent_shape.py`: already exist, and
  the new files must pass them.
- **New** `tests/hooks/test_plan_model_stamp.py`: every `### Task` in a plan
  numbered v146 or above has a valid `**Model:**` line as its first line.
  Earlier plans are exempt.
- **New** `tests/hooks/test_spec_panel_header.py`: every spec numbered v146 or
  above has a `**Panel:**` line naming 1–3 roles, each an existing
  `.claude/skills/<role>/` directory.
- **New** `tests/hooks/test_role_skills.py`: each role skill has the four
  sections in order, and a non-empty `evals/`.
- Role-skill trigger evals, in the v96 style.
- The full suite runs once, as the plan's final task.

## Out of scope

- One agent file per role (rejected: 18 files to mirror, two places to edit).
- Automatic panels on every plan task (cost, and it duplicates `task-reviewer`).
- Retrofitting `Panel:` or `Model:` onto v145 or earlier documents.
- Any role touching production, placing orders, or editing files.
