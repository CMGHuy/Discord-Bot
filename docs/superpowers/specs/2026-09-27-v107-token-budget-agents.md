# v107 — Token budget: role agents with preloaded skills + startup-cost cut

**Bump:** none (dev tooling only — no observable bot or ui difference)
**Edge:** none (integrity) — frees session budget for expectancy work; changes no trading behaviour
**Plan:** `docs/superpowers/plans/2026-09-27-v107-token-budget-agents.md`

## Problem

Three token costs, all hit equally:

1. **Usage limits** — the Opus session cap runs out (97% observed 2026-09-27).
   Mechanical work (implementing a well-briefed task, running checks, reading
   logs) runs on Opus when Sonnet/Haiku would do.
2. **Main-context bloat** — test output, greps, diffs and logs land in the
   Opus context and force compaction.
3. **Plan-execution loops** — `subagent-driven-development` dispatches
   general-purpose agents that start cold and re-derive repo conventions in
   every prompt.

Plus a fixed cost paid before the first keystroke of every session: the
system prompt carries ~150 skills and a large deferred-tool list from plugins
never used in this repo (small-business, legal, finance, product-management,
data, pdf-viewer, engineering, productivity), four MCP servers that time out
(chrome-devtools, playwright, pdf, definite), a 13 KB `CLAUDE.md` and a 4.6 KB
`MEMORY.md` index.

## Non-goals

- Not relaxing the one-subagent-at-a-time rule (`skills-tools.md`). More
  agents in parallel costs *more*, not less.
- Not moving judgment off Opus: specs, plans, reviews-of-reviews, backtest
  interpretation and acceptance-gate calls stay on Opus.
- Not changing `AGENTS.md` beyond a condensed mirror of the new dispatch table.

## Part 1 — Role agents

Agents live in `.claude/agents/*.md`. Each pins `model:` and preloads its
skills through the `skills:` frontmatter field, so the skill body is in the
agent's context from turn one — no discovery round trip, no conventions
restated in the dispatch prompt.

| Agent | Model | Tools | Preloaded skills | Contract (input → output) |
|---|---|---|---|---|
| `task-implementer` (new) | sonnet | Bash, Read, Edit, Write, Grep, Glob, Skill | `superpowers:test-driven-development`, `superpowers:verification-before-completion` | One `/task-brief` output + worktree path → files changed, commit SHA, `testrun.py file` verdict line, open questions. Never reads a plan file; never runs the full suite. |
| `task-reviewer` (new) | sonnet | Bash, Read, Grep, Glob, Skill | `no-lookahead` | Task brief + commit range → numbered findings (spec-compliance, then quality incl. radon cc ≥ 15), or `CLEAN`. Read-only. |
| `plan-writer` (new) | **opus** | Bash, Read, Write, Grep, Glob, Skill | `superpowers:writing-plans`, `new-doc` | Approved spec path → plan file(s) obeying `document-conventions.md` (≤ 1500 lines/part, `Bump:`/`Edge:`, `### Task` IDs). Does not commit. |
| `prod-inspector` (new) | haiku | Bash, Read, Grep | — (recipe inline: `/opt/swing-bot/logs/*.log`, never `docker logs` alone) | Question → ≤ 15-line answer with log excerpts. **Read-only**: body forbids `.env` edits, restarts, compose commands; any write is refused and handed back (mirror-prod stays in the main session). |
| `backtest-runner` (existing) | sonnet | unchanged | **add** `backtest-gate` | unchanged |
| `test-runner`, `symbol-verifier` (existing) | unchanged | unchanged | — | unchanged |

Area skills (`alert-surface`, `edge-module`, `schema-change`, …) are **not**
preloaded — they self-trigger inside the agent via `Skill` when the task
touches that area. Preloading everything would re-create the bloat.

Brainstorming stays in the main Opus session: a subagent cannot ask the user
questions.

**Loop it enables** (serial, one agent at a time):
`/task-brief Xn` (main) → `task-implementer` → `task-reviewer` → Opus reads
findings only, decides fix-loop or next task → final `test-runner` full run
once per plan.

**Failure handling.** Every agent body ends with a fixed return shape; an
agent that hits ambiguity returns `BLOCKED: <question>` rather than guessing.
Opus answers and re-dispatches via `SendMessage` (context intact), not a
fresh spawn.

## Part 1b — Forked slash skills

Add `context: fork` + `model:` to mechanical repo skills so their tool output
never enters the Opus context:

- `/gate` → fork, sonnet (runs checks, returns verdict).
- `/task-brief` → fork, haiku (extracts one task, returns it verbatim).

Other skills stay inline; each fork is a cold start and only pays off when the
skill's own output is large.

## Part 2 — Startup cost

1. **Plugins/MCP.** Locate where each unused plugin is enabled (user
   `settings.json` in the active config dir, org-managed via claude.ai, or
   marketplace). Disable at project scope in `.claude/settings.json`
   `enabledPlugins` where the source allows; for the MCPs, disable
   chrome-devtools, playwright, pdf-viewer (repo uses `npx playwright`, per
   `skills-tools.md`). Anything that cannot be disabled locally is recorded
   in `skills-tools.md` with its source, not silently skipped.
2. **MEMORY.md** — shorten each index line to title + ≤ 12-word hook; delete
   memories superseded by committed docs (e.g. ones restating a CLAUDE.md rule).
3. **CLAUDE.md** — target ≤ 9 KB: move the persona section and long rationale
   paragraphs into `docs/claude/*.md` behind one-line pointers. Rules that
   must fire unprompted stay.
4. **Dispatch table** — add a 6-row "which agent for what" table to
   `skills-tools.md`, a two-line pointer in `CLAUDE.md`, condensed mirror in
   `AGENTS.md`.

## Parallelisation

**Sequential throughout.** The agent tasks share one shape-test file, the
frontmatter-support check gates the syntax every later task writes, the
baseline measurement must precede the startup trims, and the
one-subagent-at-a-time rule applies regardless.

## Measurement (success criteria)

- **Startup:** `/context` token count of a fresh session in this repo,
  recorded before and after Part 2. Target: ≥ 30% reduction in system
  prompt + tools + memory.
- **Agents fire correctly:** each new agent dispatched once on a real or
  fixture task and returns its contract shape; `prod-inspector` refuses a
  write request.
- **Skill preload works:** in a `task-implementer` run, no `Skill` call for
  the preloaded skills appears (they are already loaded).
- **Forked skills:** `/gate` output in the main context is the verdict only.
- No per-plan token benchmark beyond that — timings/usage here swing with
  load (`benchmarking-restraint`); verify behaviour and move on.

## Risks

- **Sonnet implementation quality** — mitigated by `task-reviewer` plus Opus
  reading every finding; a task that loops twice through review escalates to
  Opus implementing it directly.
- **`skills:` / `context: fork` field support** — verify against current
  Claude Code docs (claude-code-guide) in the plan's first task before
  writing any agent file; fall back to inlining a short skill summary in the
  agent body if a field is unsupported.
- **Disabling a plugin another project needs** — changes are project-scoped
  only; user-level settings untouched.
