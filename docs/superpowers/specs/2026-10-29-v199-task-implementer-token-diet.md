# Task-implementer token diet

**Version:** ui 1.36.2 · bot 2.15.5
**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer

## Goal

Cut what a `task-implementer` run costs, in tokens first and wall time
second, without loosening any gate, and make plan conformance countable.
The partner ranked tokens first (2026-10-29), with fidelity to the plan as
a requirement rather than a trade-off.

Cost here is almost entirely context re-read per turn, not output. Over the
185 recorded implementer runs (session transcripts under
`~/.claude/projects/<repo>/*/subagents/`, deduplicated by message id), the
input side was 206M tokens against 1.4M output. A median run was 11 turns
and 517k input tokens (p90 32 turns). So the levers are fewer turns and
less carried per turn.

## Evidence (baseline, 2026-10-29)

| Measure | Value |
|---|---|
| Runs / real turns | 185 / 3216 |
| Input-side tokens, total / median run | 206M / 517k |
| Starting context per turn | ~33k tokens (system, tools, `CLAUDE.md`, two preloaded skills) |
| Preloaded skills share | TDD ~2.6k + verification ~1k tokens per turn; together ~5.6% of all input |
| Bash calls that are lookups (grep/sed/cat/head) | 1139 of 2803 (~40%) |
| Lookup calls before the first edit | median 8, p90 20 |
| Runs that touched a plan file | 99 of 185, though the agent file forbids it |
| UI-ish runs | 110 of 185, ~68% of input tokens; all top-10 runs were Playwright audit/fix waves of 40–110 min |
| Full-page screenshot reads | 49 |
| `task-reviewer` reports in the required `VERDICT:` shape | 7 of 97 |

Causes, as read from the transcripts:

- **No standard handoff.** Each controller session hand-writes the
  dispatch prompt: worktree, `TEST_DATABASE_URL` and DB creation, the
  `ng.js` frontend wrapper, attribution. Several told the agent to `sed -n`
  the plan section. The implementer then re-verifies the environment and
  re-greps code the brief did not carry.
- **UI tasks read whole screenshots**, which stay in context for every
  later turn, and open-ended "fix all audit findings" tasks run for an hour.
- **Fidelity is unmeasurable**: reviewer output is free-form, so nothing
  counts missed or divergent deliverables.

## Decisions (partner, 2026-10-29)

1. **Priority:** tokens first.
2. **Preloaded skills:** drop `superpowers:verification-before-completion`
   from the implementer's preload; **keep** `superpowers:test-driven-development`.
   The report's verbatim `TESTS:` line already carries the verification
   rule. Dropping TDD was rejected: it is what keeps tests ahead of code,
   and nothing else checks the order.
3. **Handoff:** a script writes the deterministic parts of a handoff file;
   `/task-brief` adds only its trap preflight and code excerpts. The
   controller passes the file path.
4. **UI:** audit first; element-clipped screenshots only; at most 4 image
   reads per task; plan writers cap UI fix waves at one page per task.
5. **Fidelity:** lightweight. Numbered deliverables in the handoff, ticked
   by the implementer, verified one by one by the reviewer in a strict
   shape, counted by the measurement script.

## Design

### 1. The handoff file

A new script, `scripts/dev/task_handoff.py <plan-index-or-file> <task-id>
--worktree <path>`, writes
`.superpowers/sdd/<plan base>/task-<id>-handoff.md` (gitignored, like the
existing `task-*-brief.md` files there). Sections, in order:

- **Task** — the `### Task <id>` section copied verbatim from whichever
  plan part holds it, including its `**Model:**` line. Located by the
  existing `^### Task` grep convention; a split plan is searched across its
  parts via the index.
- **Deliverables** — a numbered list, one per plan step / `Create:` /
  `Modify:` / `Test:` line of the task, `D1`…`Dn`. Derived mechanically;
  where the task has no such lines, each top-level step is one item.
- **Environment** — worktree path and branch; "use `git -C <wt>` and
  absolute paths, never `cd`"; the exact `testrun.py file` command form;
  the test database URL and how to create/drop it when the task's files
  touch the DB (from `replicate-prod-db` / `test-infra` conventions); the
  frontend test wrapper when the task touches `frontend/`; the radon
  command; the commit attribution line passed by the controller.
- **Preflight** and **Code** — left as marked slots for `/task-brief`.

`/task-brief` is changed to take the handoff path, fill **Preflight** (its
existing 3a–3h checks, unchanged) and **Code**: bounded excerpts (signature
plus the lines the task changes, with line numbers) of every symbol and
file the task names. Where a `plan-briefer` brief exists for the plan,
excerpts are taken from it and re-checked against the worktree, not
re-derived. Budget for **Code**: about 12 KB; above that, list
`path:line-range` pointers instead of bodies.

The controller's dispatch prompt becomes fixed: task id, handoff path,
model tier, and "return the report shape in your agent file". It is
documented once in `skills-tools.md` § Which agent for what; ad-hoc prompts
that restate environment or point at plan files are no longer the pattern.

### 2. The agent file

`task-implementer.md` (and its Codex mirror):

- `skills:` keeps `superpowers:test-driven-development`, drops
  `superpowers:verification-before-completion`.
- New rules: read the handoff first and trust its **Code** excerpts before
  searching; batch independent lookups into one call; read files by line
  range; no environment probing the handoff already answers.
- The existing "never open a plan file" rule stays and now has no
  exception, since the handoff carries the task text.
- Report shape gains `DELIVERABLES: D1 done | D2 done | D3 deviated: <why>`.

### 3. UI tasks

- `frontend/scripts/browse.mjs shots` gains `--clip <css selector>`:
  captures only the first match's bounding box (plus a small margin)
  instead of the full page. Full-page stays the default for callers that
  do not pass it.
- Implementer rule for UI tasks: run `frontend/scripts/layout-audit.mjs`
  first and work from its findings; read a screenshot only for a named
  element, clipped; **at most 4 image reads per task**. Needing more is a
  `BLOCKED:` with the reason, not a silent overrun.
- `ui-design.md` and the plan-writer agent: a UI fix-wave task covers one
  page (all three widths); an audit that finds issues on several pages
  produces one task per page.

### 4. Fidelity check

`task-reviewer.md` (and Codex mirror): step 1 becomes "for each
deliverable `Dn` in the handoff, verify against the diff: `done`,
`missing`, or `different`". Return shape adds one line per deliverable
before findings:

```
VERDICT: CLEAN | FINDINGS | BLOCKED: <one question>
D1 done
D2 missing -- <file or step>
...
1. [spec|correctness|complexity|test] <file>:<line> -- <one sentence>
```

Any `missing`/`different` is automatically a `[spec]` finding. The
reviewer gets the handoff path rather than a pasted brief.

### 5. Measurement

The transcript analysis used for the baseline becomes
`scripts/dev/agent_cost.py [--agent task-implementer] [--since DATE]`:
runs, turns, input tokens (dedup by message id), lookups before first
edit, image reads, plan-file touches; for `task-reviewer`, share of reports
in the required shape and `missing`/`different` counts. Read-only over
local transcripts; prints a table. It is the before/after instrument for
this spec.

## Success

Judged with `agent_cost.py` over the first ~20 implementer runs after
merge, against the baseline above:

- median input tokens per run down at least 30%;
- median lookups before first edit 3 or fewer;
- plan-file touches 0;
- image reads per UI task 4 or fewer;
- reviewer reports in the required shape 90% or more.

A miss on the token target is recorded, not hidden; the rules stay if the
fidelity and plan-touch targets are met.

## Non-goals

- No change to model tiers, the `Model:` rubric, or the escalation ladder.
- No change to the reviewer's tier or its correctness/complexity/test steps.
- No change to test-first, complexity < 15, the test-suite rules, or
  worktree discipline.
- No change to `plan-briefer` / `plan-writer` beyond the one-page UI
  fix-wave rule.
- Nothing billed beyond the subscription.

## Anti-goals

- A cheaper run that ships a task differing from its plan. Fidelity
  regressions outweigh any token saving.
- A handoff so large it costs more per turn than the lookups it replaces
  (hence the **Code** budget).
- Hiding a UI check the screenshots used to catch: the audit plus clipped
  shots must still cover all three widths.

## Constraints

- Codex mirror ships in the same commits: `.claude/agents/*` via
  `python scripts/dev/sync_codex.py`, doc changes into `AGENTS.md`;
  `tests/hooks/test_codex_mirror.py` must stay green.
- New scripts ship unit tests (handoff extraction on a single-file plan, a
  split plan, a task with no `Create:/Modify:` lines, a missing task id;
  `agent_cost.py` on fixture transcripts including a duplicated-message-id
  case; `browse.mjs --clip` argument parsing) and join an existing suite.
- Every function under complexity 15.

## Author's calls (settled from the builder check, not partner decisions)

- **Deliverable derivation.** Plan tasks are written as a `**Files:**`
  line plus `- [ ]` checkbox steps (e.g. V198-1). One `Dn` per `- [ ]`
  step, plus one per file named in `**Files:**`. A task with neither
  falls back to one item per top-level paragraph, flagged in the
  handoff as `derivation: fallback`.
- **Ticks live in the report only.** The handoff file is never edited
  after `/task-brief` fills it. The reviewer reads the untouched handoff
  and the diff, never the implementer's ticks, so it is not anchored on
  the implementer's claims.
- **Environment block trigger.** Path prefixes in `**Files:**`: any
  `swingbot/core/db/`, `alembic/`, store/repository path or `tests/db/`
  adds the database block; any `frontend/` adds the frontend block.
  The task's text is not keyword-scanned.
- **Database rule.** The root `CLAUDE.md` is authoritative: tests run
  against the one shared `swing-db` container after `/replicate-prod-db`.
  Its rule wins over the older per-implementer database note in session
  memory. The handoff names the container and the URL form and never
  creates a per-task container.
- **Attribution.** `task_handoff.py` takes `--attribution "<line>"`; the
  controller passes the line from its own system reminder.
- **The 4-image cap** is a prompt rule. `agent_cost.py` counts image
  reads per run; `browse.mjs` does not enforce it.
- **`--clip` with no match** exits non-zero and names the selector; it
  never falls back silently to a full page. An element taller than the
  viewport is captured whole (element screenshot), not cropped to the
  viewport.
- **Transcript fixtures** for `agent_cost.py` are trimmed copies of real
  jsonl lines: `type`, `message.id`, `message.usage`, `tool_use` and
  `tool_result` blocks. They include a message id repeated across lines.

## Left to the plan writer

- Which test suite each new test file joins, checked against `max_tests`.
- Whether the environment facts (container name, URL form, wrapper path)
  are read from `swingbot/config.py`/`tests/` helpers or held as
  constants, as long as one source is shared with the test tooling.
- Whether `/task-brief` stays a forked Sonnet skill or becomes a step the
  handoff script prompts for; either is acceptable if the controller still
  passes one path.
