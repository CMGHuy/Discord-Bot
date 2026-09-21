# Skills and tools for this repo

Referenced from the root `CLAUDE.md`.

- `superpowers:subagent-driven-development` — the plans in
  `docs/superpowers/plans/` are written for it (`### Task E42` + checkboxes).
  This is the default loop for plan execution; its `task-brief` and
  `review-package` scripts are what keep giant plans out of context.
- `superpowers:test-driven-development` — matches how entry filters get built
  here (fixture first, REPL-tune until the ungated function fires, freeze).
- `superpowers:systematic-debugging` — before any "fix" to a backtest number
  or a failing gate; guessing at these is expensive.
- `superpowers:verification-before-completion` — this repo has a documented
  history of tasks marked done that weren't. Verify against `git log` and the
  actual files.
- `superpowers:brainstorming` then `superpowers:writing-plans` for new
  components, so the result matches the existing plan format.
- `Explore` subagent for wide code searches; `feature-dev:code-reviewer` or
  `/code-review` for review passes. `backtest-runner` for any backtest/grid/
  walk-forward/fold run over ~2 minutes; `symbol-verifier` to check a plan's
  claimed functions/classes/config fields actually exist before implementing
  against them; `test-runner` for any full-suite or fast-tier pytest run.
- `.mcp.json` provides the `context7` server, scoped to yfinance/pandas-ta/
  discord.py docs — not this repo's own code.
- **At most ONE subagent at a time, by default.** Dispatch one, wait for it to
  return, then decide whether the next is still needed. Spawning several at
  once requires the human partner to ask for it explicitly — "in parallel",
  "fan out", a stated count — and a plan's `## Parallelisation` section is a
  map of what *could* run concurrently, not standing permission to launch it.
  This is a budget rule, not a style one: each agent is a full context that
  re-derives what this session already knows, several at once can exhaust the
  session limit mid-task (which has happened here, killing three of five
  audits and losing their work), and the results land as one undigested wall
  the controller must triage anyway. One agent, read its findings, act,
  repeat — the serial version is usually faster in wall-clock terms too,
  because the first result routinely changes what the second should even
  look for.
- Skip `frontend-design`/`dataviz` conventions for the admin UI unless asked —
  it follows the existing TradingView-style theme.

## The v96 skills layer

Eleven `.claude/skills/` loaders shipped alongside three new `guardrails.py`
deny rules. The division of labour is fixed: **a hook denies, a skill
teaches.** A hook rule blocks a mechanically-detectable pattern outright and
cannot be reasoned with; a skill loads the reasoning behind a rule that can't
be reduced to a regex, and Tier 1 skills are expected to fire unprompted from
their `description` trigger the same way a hook does. The three new hook
rules, all in `.claude/hooks/guardrails.py`: `_rule_protected_branch_delete`
(denies a destructive git command — branch delete, `push --delete`, force
push, `update-ref -d` — targeting a `backup`/`stable-*` ref),
`_rule_closed_preregistration` (denies a `tune_strategy.py`/
`run_backtest_range.py` invocation naming a knob in the CLOSED
pre-registration table), and `_rule_plan_doc_shape` (denies a Write to
`docs/superpowers/{specs,plans}/` whose filename isn't
`YYYY-MM-DD-vN-<name>.md`, or whose content has a two-hash `## Phase`
heading).

| Skill | Tier | Invocation | `docs/claude/*.md` loaded in Step 1 |
|---|---|---|---|
| `backtest-gate` | 1 | model-invocable | `backtest-methodology.md` |
| `no-lookahead` | 1 | model-invocable | `architecture.md`, `known-traps.md` |
| `pooled-numbers` | 1 | model-invocable | `edge-priorities.md`, `backtest-methodology.md` |
| `mirror-prod` | 1 | model-invocable | `working-conventions.md` |
| `edge-module` | 3 | model-invocable | `architecture.md` |
| `alert-surface` | 3 | model-invocable | `known-traps.md` |
| `schema-change` | 3 | model-invocable | none — Step 1 reads code (`swingbot/core/db/repositories/`, `scripts/db/parity_report.py`), not a doc |
| `worktree-lifecycle` | 3 | model-invocable | `document-lifecycle.md`, `working-conventions.md` |
| `close-out` | 2 | slash-only (`/close-out`) | `document-lifecycle.md`, `working-conventions.md` |
| `new-doc` | 2 | slash-only (`/new-doc`) | `document-conventions.md` |
| `deploy` | 2 | slash-only (`/deploy`) | none — Step 1 reads `docs/deploy/DEPLOY_HETZNER.md` and `docs/deploy/DOCKER.md`, not `docs/claude/` |

Tier 1 (integrity gates) and Tier 3 (seam briefings) are both
model-invocable and share one mechanical shape contract — a `Trigger table`
(should-fire / should-not-fire rows) in the body and no
`disable-model-invocation` frontmatter field, tested together as
`TIER_1_AND_3` in `tests/hooks/test_skill_shape.py` — but cover different
ground: Tier 1 blocks an integrity violation (backtest re-runs, lookahead,
pooled numbers, unmirrored prod changes), Tier 3 briefs an architectural seam
before it's crossed (edge module boundaries, the alert surface, a schema
change, worktree lifecycle). Tier 2 skills carry
`disable-model-invocation: true` and no Trigger table — they are checklists
for an explicit slash command (`/close-out`, `/new-doc`, `/deploy`), not
things the model should decide to run on its own.

## Proving a skill fires: the eval suites

Every Tier 1 and Tier 3 trigger table is wired into a runnable suite under
`.claude/skills/<skill>/evals/` — one case per table row, `fire-*` for a
should-fire row and `no-fire-*` for a near-miss. A case is a `prompt.md` (the
request as a session would really phrase it, `allowed_tools: [Read, Glob,
Grep, Skill]`) plus `graders/skill-fired.md`, a `tool_used` grader on the
`Skill` tool: `min: 1` for a fire, `min: 0` **and** `max: 0` for a near-miss.
A near-miss grader must set `min: 0` explicitly — `min` defaults to 1, so a
bare `max: 0` asks for the impossible range `1..0` and fails every case that
behaved correctly.

```bash
claude plugin eval .claude/skills/<skill> --runs 1 --no-publish --trust-plugin --ablation none
```

`--ablation none` keeps the run to a single arm. Omit it and the run defaults
to `with-without`, which adds a no-plugin baseline arm at twice the runs and
cost. That arm is worth paying for when the question is whether the *skill*
rather than the base model produced the behaviour — a should-fire case then
reports `with 1.00 / without 0.00 / Δ +1.00`. It adds nothing on a near-miss,
where the baseline arm trivially scores 1.00.

Each case is a real child `claude` run on your own credential. The full
52-case sweep is about $3.50 and about 8 minutes; per-skill suites are 3–8
cases each. Results land in `.claude/skills/<skill>/evals/results/`, which is
gitignored. Baseline at 2026-09-21: 52/52 cases pass, all eight suites exit 0.
