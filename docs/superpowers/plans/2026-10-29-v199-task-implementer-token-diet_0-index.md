# Task-implementer token diet implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [Task-implementer token diet](../specs/2026-10-29-v199-task-implementer-token-diet.md)

**Goal:**

A `task-implementer` run costs almost nothing in output and a great deal in
context re-read on every turn: over 185 recorded runs the input side was 206M
tokens against 1.4M output, with a median of 11 turns and 517k input tokens.
The causes are concrete. Each controller hand-writes the dispatch prompt, so
the implementer re-verifies its environment and re-greps code the brief did
not carry (median 8 lookups before the first edit). UI tasks read whole-page
screenshots that then sit in every later turn. Reviewer output is free-form
(7 of 97 reports in the required shape), so nothing counts a missed or
divergent deliverable. And nothing measures any of this, so no agent change
can be shown to help.

Once shipped, the controller runs `scripts/dev/task_handoff.py` for a task
and passes one file path. That file carries the task text verbatim, a
numbered deliverable list `D1`…`Dn` derived mechanically from the task's
`**Files:**` clause and `- [ ]` steps, and the environment facts (worktree,
test command, test database, frontend test wrapper, radon, attribution) that
implementers used to probe for. `/task-brief` fills only its trap preflight
and bounded code excerpts. The implementer stops preloading the verification
skill (TDD stays), ticks each deliverable in its report, and on UI tasks works
from `layout-audit.mjs` findings and element-clipped screenshots
(`browse.mjs shots --clip`), at most four image reads. The reviewer checks
each `Dn` against the diff in a strict line shape. `scripts/dev/agent_cost.py`
turns the transcript analysis behind the baseline into a standing,
reproducible instrument.

Left alone: model tiers and the `Model:` rubric, the reviewer's tier and its
correctness/complexity/test steps, test-first, the complexity gate, the suite
rules, worktree discipline, and `plan-briefer`/`plan-writer` apart from the
one-page UI fix-wave rule. No trading code changes; `Edge: none (integrity)`.

Success is measured by `agent_cost.py` itself: V199-9 first reproduces the
spec's baseline table with `--until 2026-10-29`, so later comparisons are like
for like. After merge, the first ~20 implementer runs are judged against the
spec's targets: median input tokens down at least 30%, median lookups before
first edit 3 or fewer, plan-file touches 0, image reads per UI task 4 or
fewer, reviewer reports in the required shape 90% or more. That post-merge
judgement is outside this plan; a token miss is recorded, not hidden.

**Architecture:** Two new pure-function scripts under `scripts/dev/`
(`task_handoff.py`, `agent_cost.py`) in the `doc_section.py` style, each split
across tasks by seam, with tests in `tests/scripts/` (tooling suite). Two new
pure node libs beside their thin CLI shells in `frontend/scripts/`
(`browse-lib.mjs`, `ng-test-lib.mjs`), tested with `node --test` and brought
under CI by one pytest wrapper. Agent, skill, hook and doc edits come last and
ship with their Codex mirror in the same commit.

**Tech stack:** Python 3.11 stdlib (argparse, json, re, pathlib, subprocess,
statistics), pytest; Node 22+ `node:test`; Playwright (existing in
`browse.mjs`); `scripts/dev/sync_codex.py` for mirrors.

## Global Constraints

- `Bump: none`. No `VERSION.json` or `version_history.json` change in any task.
- Implement in a worktree under `.claude/worktrees/`. Every command uses absolute paths or `git -C <wt>`; never `cd` (repo hook).
- Stage explicit paths only; never `git add -A` / `git add .`. The main tree's `.codex/agents/plan-writer.toml` carries an uncommitted line-ending-only change from another session (0-line `git diff --stat` at authoring); no task stages or commits that main-tree file. V199-12 commits the **worktree's** regenerated `.codex/agents/plan-writer.toml`, because it is the generated mirror of that task's own `plan-writer.md` edit and `tests/hooks/test_codex_mirror.py` fails without it.
- Codex mirror ships in the same commit as its source: `.claude/agents/*` and `.claude/skills/task-brief/` via `python <wt>/scripts/dev/sync_codex.py`; `skills-tools.md` and `ui-design.md` changes as condensed `AGENTS.md` lines. `python <wt>/scripts/dev/sync_codex.py --check` prints `Codex mirror is current.` after every task that touches `.claude/` or `docs/claude/`.
- Every new or changed function stays below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>` prints nothing). New `.py` files are `git add`ed before `python scripts/dev/complexity_gate.py` so they are measured.
- New Python tests go in `tests/scripts/` (suite `tooling`), except agent-file tests, which sit beside `tests/hooks/test_agent_shape.py` (suite `dev-setup`). No new `tests/` directory; no `tests/suites.toml` change.
- Scripts in `scripts/dev/` have no `__init__.py`: tests load them with `importlib.util.spec_from_file_location`, as `tests/hooks/test_codex_mirror.py:12-16` does. A script imports a sibling by inserting its own directory on `sys.path`, as `scripts/dev/testrun.py:56` does.
- Pure tests only: no task needs the database, the network or production. `/replicate-prod-db` is not required by any task.
- Transcripts are read-only input: `agent_cost.py` never writes under the transcript root.
- The spec's metric definitions are fixed verbatim: **Lookup** = a Read, Grep or Glob call, or a Bash call matching `\b(grep|rg|cat|sed -n|head|tail|ls|find)\b`; **First edit** = the first Edit or Write tool call; **Turn** = a distinct assistant `message.id`; **Input tokens** = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. Only V199-9 may change a definition, and only by recording why in the spec.
- The handoff file is never edited after `/task-brief` fills it. Deliverable ticks live in the implementer's report only.
- Per-task verification is the narrow run `python <wt>/scripts/dev/testrun.py file <test>`; the single full-suite run is V199-13.
- No change to model tiers, the `Model:` rubric, the escalation ladder, the reviewer's tier, or the TDD preload. Nothing billed beyond the subscription.

## Review Focus

- Task id prefixes and `b` splits: `V198-2` must not match `### Task V198-2b:` and `E5` must not match `E53`. Pinned in V199-4 (`test_b_suffix_is_not_a_prefix_match`).
- Plan files with CRLF line endings (Windows checkouts): section extraction and fence tracking must behave as with LF. Pinned in V199-4 (`test_crlf_plan_extracts_the_same_section`).
- `**Files:**` written as bullet lines (`- Create: \`x\``, the superpowers template this plan itself uses) as well as prose: both yield one deliverable per path. Pinned in V199-5 (`test_bullet_files_block_yields_one_deliverable_per_path`).
- A subagent transcript whose `.meta.json` is missing or unreadable: it is counted, not crashed on and not silently dropped. Pinned in V199-7 (`test_find_runs_counts_a_run_without_meta_as_unknown`).
- `--clip` on a selector whose first match has no box (hidden, `display:none`): exits non-zero naming the selector, never a full-page fallback. Pinned in V199-2 (`clipBox returns null for a missing or zero-size box`, and the `browse.mjs` exit path).

## Parallelisation

Three independent chains, files disjoint, no contract between them until Phase 4:

- **Chain A (node tooling):** V199-1, V199-2, V199-3. Disjoint files; may run in parallel with each other. V199-1's wrapper discovers `*.test.mjs` by glob, so the order among them does not matter.
- **Chain B (handoff):** V199-4 → V199-5 → V199-6. Sequential: all three edit `scripts/dev/task_handoff.py`, and V199-6 consumes `files_paths` from V199-5. V199-6 also needs V199-3 merged first, because its test asserts the `NG_TEST_WRAPPER` file exists.
- **Chain C (measurement):** V199-7 → V199-8 → V199-9. Sequential: V199-7 and V199-8 edit `scripts/dev/agent_cost.py`; V199-9 runs it. V199-8 imports `NO_HANDOFF_LINE` and `REVIEWER_STATES` from `task_handoff.py`, so it needs V199-4 merged.

Chains A, B and C may run concurrently (at most 2 implementers at once, per `CLAUDE.md`), given the cross-chain edges above.

**Phase 4 is sequential:** V199-10 → V199-11 → V199-12. Each runs `sync_codex.py`, which regenerates every mirror file and checks `AGENTS.md` as a whole, so two of them in flight would commit each other's regenerated files. V199-10 needs V199-6 (its wiring test imports the handoff constants). V199-11 needs V199-6 (the slot markers it fills). V199-12 needs V199-2, V199-3, V199-6 and V199-8 (it documents their CLIs).

V199-13 follows every task.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V199-1 | Run frontend node tests under the tooling suite | 1 | haiku | Create `tests/scripts/test_node_scripts.py` | `node_test_files() -> list[Path]` (sorted `frontend/scripts/*.test.mjs`); test skips with reason when `shutil.which("node")` is None. Brings `layout-audit-lib.test.mjs` (35 pass at authoring) under CI |
| V199-2 | Element-clipped screenshots in `browse.mjs shots --clip` | 1 | sonnet | Create `frontend/scripts/browse-lib.mjs`, `frontend/scripts/browse-lib.test.mjs`; modify `frontend/scripts/browse.mjs` | `export const CLIP_MARGIN_PX = 8`; `export function clipBox(box, page, margin = CLIP_MARGIN_PX) -> {x, y, width, height} \| null`; `export function parseArgs(argv)` moved from `browse.mjs` with new `clip: string \| null` option (`--clip <css selector>`). CLI: `node frontend/scripts/browse.mjs shots --path <p> [--clip <sel>]`; no match exits 1 naming the selector |
| V199-3 | Cwd-free Angular test wrapper `ng-test.mjs` | 1 | sonnet | Create `frontend/scripts/ng-test-lib.mjs`, `frontend/scripts/ng-test-lib.test.mjs`, `frontend/scripts/ng-test.mjs` | `export function parseNgTestArgs(argv) -> {frontend: string, includes: string[]}`; `export function ngTestInvocation(opts, execPath) -> {command, args, cwd}`. CLI: `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend [--include <spec>]...` runs `<frontend>/node_modules/@angular/cli/bin/ng.js test --watch=false` with `cwd=<frontend>`, exit code passed through |
| V199-4 | Locate a task exactly across a plan's files | 2 | sonnet | Create `scripts/dev/task_handoff.py`, `tests/scripts/test_task_handoff_locate.py` | `class HandoffError(Exception)`; `task_section(text: str, task_id: str) -> str \| None`; `find_task(files: list[Path], task_id: str) -> tuple[Path, str]`; `plan_base(plan: Path) -> str`; constants `SECTIONS = ("Task", "Deliverables", "Environment", "Preflight", "Code")`, `PREFLIGHT_SLOT = "<!-- task-brief: fill Preflight -->"`, `CODE_SLOT = "<!-- task-brief: fill Code -->"`, `REPORT_PREFIX = "DELIVERABLES:"`, `IMPLEMENTER_STATES = ("done", "deviated")`, `REVIEWER_STATES = ("done", "missing", "different")`, `NO_HANDOFF_LINE = "DELIVERABLES: n/a (no handoff)"`. Reuses `plan_lint.plan_files` and `plan_lint.FENCE_RE` |
| V199-5 | Derive numbered deliverables by the spec grammar | 2 | sonnet | Modify `scripts/dev/task_handoff.py`; create `tests/scripts/test_task_handoff_deliverables.py` | `class Deliverable(NamedTuple): id: str; text: str` (`"D3"`, `"D3.2"`); `FILES_VERBS = ("modify", "create", "update", "test", "delete")`; `files_paths(section: str) -> list[tuple[str, str]]` (verb as written, path); `derive_deliverables(section: str, task_id: str) -> list[Deliverable]`, raising `HandoffError("no deliverables derivable for <id>")` |
| V199-6 | Environment block, handoff rendering and CLI | 2 | sonnet | Modify `scripts/dev/task_handoff.py`; create `tests/scripts/test_task_handoff_render.py` | `DB_PREFIXES`, `FRONTEND_PREFIXES = ("frontend/",)`; `needs_db(paths) -> bool`; `needs_frontend(paths) -> bool`; `TEST_DB_URL` (= `testrun.TEST_DB_URL_DEFAULT`), `TEST_DB_CONTAINER = "swing-db-test"`, `TEST_DB_SERVICE = "db-test"`, `NG_TEST_WRAPPER = "frontend/scripts/ng-test.mjs"`; `environment_block(worktree: Path, branch: str, paths: list[str], attribution: str) -> str`; `render_handoff(task_text: str, deliverables: list[Deliverable], environment: str) -> str`; `main_checkout(start: Path) -> Path`; `handoff_path(main_root: Path, plan: Path, task_id: str) -> Path` = `<main>/.superpowers/sdd/<plan_base>/task-<id>-handoff.md`. CLI: `python scripts/dev/task_handoff.py <plan file> <task id> --worktree <path> --attribution "<line>"`; prints the absolute handoff path as its last line; exit 2 with the message on `HandoffError` |
| V199-7 | Transcript discovery, events, dedup and lookups | 3 | sonnet | Create `scripts/dev/agent_cost.py`, `tests/scripts/test_agent_cost.py` | `repo_slug(path: Path) -> str`; `transcript_root(env: Mapping[str, str], home: Path, slug: str) -> Path`; `class RunFile(NamedTuple): path: Path; agent: str` (`"unknown"` without readable meta); `find_runs(root: Path) -> list[RunFile]`; `class Event(NamedTuple): kind: str; msg_id: str \| None; usage: dict \| None; blocks: tuple; timestamp: str \| None` (`kind == "unparsed"` for bad lines); `iter_events(lines) -> Iterator[Event]`; `dedup(events) -> list[Event]`; `LOOKUP_RE`; `is_lookup(name: str, tool_input: Mapping) -> bool`; `is_image_read(block: Mapping) -> bool` (shape confirmed from a real transcript first) |
| V199-8 | Run metrics, reviewer shape, table and CLI | 3 | sonnet | Modify `scripts/dev/agent_cost.py`; create `tests/scripts/test_agent_cost_metrics.py` | `@dataclass(frozen=True) class RunMetrics` (fields in the part); `run_metrics(events: list[Event], agent: str) -> RunMetrics`; `report_shaped(text: str) -> bool`; `render_table(rows: list[RunMetrics]) -> str`. CLI: `python scripts/dev/agent_cost.py [--agent task-implementer] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--root <dir>]`; dates inclusive on a run's first timestamp; exit 1 with a message when no transcripts match. Imports `NO_HANDOFF_LINE`, `REVIEWER_STATES` from `task_handoff.py` |
| V199-9 | Reproduce the spec's baseline table | 3 | opus | Modify `docs/superpowers/specs/2026-10-29-v199-task-implementer-token-diet.md` (append `## Baseline reproduction`); `scripts/dev/agent_cost.py` and its tests only if a definition must be reconciled | No code contract; records the reproduced table, every delta and any definition change. Unreconcilable delta beyond rounding is `BLOCKED:` |
| V199-10 | Implementer and reviewer agents read the handoff | 4 | sonnet | Modify `.claude/agents/task-implementer.md`, `.claude/agents/task-reviewer.md`, `tests/hooks/test_agent_shape.py`; regenerate `.codex/agents/task-implementer.toml`, `.codex/agents/task-reviewer.toml`; create `tests/hooks/test_handoff_wiring.py` | Implementer `skills: [superpowers:test-driven-development]`; report line `DELIVERABLES: D1 done \| D2 deviated: <why>`; reviewer lines `D<n> done` / `D<n> missing -- <what>` / `D<n> different -- <what>` before findings; the wiring test pins both files to the V199-4 constants |
| V199-11 | `/task-brief` fills the handoff; plan-read guard names it | 4 | sonnet | Modify `.claude/skills/task-brief/SKILL.md`, `.claude/hooks/guardrails.py`, `tests/hooks/test_guardrails.py`; regenerate `.agents/skills/task-brief/SKILL.md` | `/task-brief <handoff path>` replaces `PREFLIGHT_SLOT` and `CODE_SLOT` only (Code budget ~12 KB, else `path:line-range` pointers); deny reason names `task_handoff.py` and keeps `task-brief` |
| V199-12 | Controller, UI and plan-writer docs with their mirrors | 4 | haiku | Modify `docs/claude/skills-tools.md`, `docs/claude/ui-design.md`, `.claude/agents/plan-writer.md`, `AGENTS.md`; regenerate `.codex/agents/plan-writer.toml` | Fixed dispatch prompt text; `agent_cost.py` named as the standing cost check; one page per UI fix-wave task; audit-first, clipped shots, 4-image cap |
| V199-13 | Full suite and end-to-end verification | 4 | sonnet | Fix observed defects in the owning task's files only | Full suite green (`0 failed`, `0 xfailed`); `sync_codex.py --check`; `complexity_gate.py`; `task_handoff.py` smoke run on V198-1 and on V199-5; `agent_cost.py` smoke run |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-29-v199-task-implementer-token-diet_1-node-tooling.md` | V199-1, V199-2, V199-3 | Node test runner, `--clip`, `ng-test.mjs` |
| 2 | `2026-10-29-v199-task-implementer-token-diet_2-handoff-script.md` | V199-4, V199-5, V199-6 | `task_handoff.py` locate, deliverable grammar, environment and CLI |
| 3 | `2026-10-29-v199-task-implementer-token-diet_3-agent-cost.md` | V199-7, V199-8, V199-9 | `agent_cost.py` and the baseline reproduction |
| 4 | `2026-10-29-v199-task-implementer-token-diet_4-agents-docs-verification.md` | V199-10, V199-11, V199-12, V199-13 | Agent files, `/task-brief`, guard hook, docs, mirrors, full suite |

## Cross-task contracts

- **Handoff file layout** (V199-6 renders, V199-10/11 consume): `# Handoff: Task <id>` then exactly the headings `## Task`, `## Deliverables`, `## Environment`, `## Preflight`, `## Code`, in `SECTIONS` order. `## Deliverables` lines are `- D<n> <text>` and `  - D<n>.<k> <test name>`. `## Preflight` holds only `PREFLIGHT_SLOT`, `## Code` only `CODE_SLOT`, until `/task-brief` replaces each marker line.
- **Plan files of a plan:** `plan_lint.plan_files(any_file)` (index plus every sibling part, the index first) is the one definition used by both `plan_lint.py` and `task_handoff.py`.
- **Test database facts:** `scripts/dev/testrun.py:64` `TEST_DB_URL_DEFAULT` is the one URL source; `tests/db/conftest.py:14` stays pinned equal by `tests/dev/test_testrun_db_preflight.py`. Container `swing-db-test`, compose service `db-test`, profile `test`, port 55432 (`docker-compose.yml:83-94`); V199-6 pins both names against the compose file text.
- **Deliverable states:** implementer report states come from `IMPLEMENTER_STATES`, reviewer lines from `REVIEWER_STATES`; `agent_cost.py` counts reviewer `missing`/`different` lines and `NO_HANDOFF_LINE` using the same constants.
