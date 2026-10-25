# v193 — Plan-writer pipeline: write as you go, split right first time, shorter tasks, stable contracts: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V193-5:" -A 300 docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_2-ledger-slice-and-agents.md`.

**Bump:** none
**Edge:** none (integrity) — faster, cheaper, visibly progressing plan writing; no signal, gate, stop, size or badge changes.
**Screen:** exempt (integrity)
**Spec:** [2026-10-25-v193-plan-writer-pipeline.md](../specs/2026-10-25-v193-plan-writer-pipeline.md)
**Brief:** `.superpowers/briefs/2026-10-25-v193-plan-writer-pipeline.md`
**Worktree:** every task runs in `.claude/worktrees/2026-10-25-v193-plan-writer-pipeline` (branch of the same name, created in V193-1's first step; `docs/claude/document-lifecycle.md`). The merge to `main` is V193-9's last step.

## Goal

Plan writing is now the slowest and most expensive step between an approved
spec and working code. The last three plans (v189, v191, v192) show why:
parts spilled past the 1500-line cap after they were written and were
re-split by hand (an index edit, a ledger fix-up and an extra commit each
time); the writer's "150–300 lines per task" estimate is about half the
measured size; tasks paste whole stretches of existing code and repeat the
same close-out boilerplate; a shared contract changed after parts already
used it; and every part writer re-read the whole spec, brief and index.

Once this ships, a plan is sized from measured numbers
(`plan_lint.py --stats`, p90 lines per task over the last five implemented
plans), a part writer that runs long opens its own `_<N>b` spill file
instead of waiting for a re-split, and `plan_lint.py --fix-parts`
regenerates the index's parts table from the files on disk. Tasks get
shorter: the standard close (worktree check, narrow run, complexity gate,
commit shape) is stated once in the index under `### Standard task close`,
each task ends with a `Close:` line, existing code is cited by repo path
and line range instead of pasted, and a task over ~400 lines is split into
two ledger rows. Contracts are checked before any part is written:
`plan_lint.py --ledger` verifies every consumed symbol exists or is created
by an earlier row and every `Spec §` cell names a real spec heading.
Each part writer reads one slice (`scripts/dev/plan_slice.py <index> <N>`)
instead of three whole documents.

In idea: everything a script can check or generate is moved out of the
model. The write pattern itself stays as it is — one append per task, index
and ledger first — and becomes visibly steadier because tasks are shorter
and each write re-reads a smaller context.

Left alone: the 2-writer and 2-plan caps, the 1500-line file cap, the
existing plans (v192 and older lint exactly as today: the new per-task
checks apply from v194), the bot and the admin UI. Nothing served changes;
no version bump.

Success is measured on the next plans written: no post-hoc re-split commit,
no hand-edited parts table, `--ledger` PASS before parts are dispatched,
and median plan lines per task 30–45% below v192's ~300.

## Architecture

- `scripts/dev/plan_doc.py` (new, V193-1) holds the shared, side-effect-free
  markdown parsing: ledger rows keyed by header cell, `##` sections,
  backticked tokens, `Spec §` references and their resolution against spec
  headings, symbol-name extraction. `plan_lint.py` and `plan_slice.py` both
  import it (`sys.path` insert of `scripts/dev`), so there is one ledger
  parser.
- `scripts/dev/plan_lint.py` keeps its single-positional lint
  (`plan_lint.py <file>`) and gains a table-driven flag dispatch
  (`COMMANDS`): `--stats [dir]`, `--fix-parts <index>`, `--ledger <index>`.
  The per-task checks (`Close:` line, `TASK_CEILING` lines, `Modify:` range
  within the file) run inside the existing lint, gated by
  `plan_number >= NEW_RULES_FROM` (194), the same pattern as today's
  `needs_model` (> 145).
- `scripts/dev/plan_slice.py` (new) prints one part writer's whole context:
  index preamble, `## Global Constraints`, `## Handoff` (if any), `## Task
  ledger`; the spec sections the part's rows cite; the brief sections
  (`## <repo path>`) for the files the rows touch, plus `## Traps`; and a
  `MISSING:` line for anything it could not find.
- `.claude/agents/plan-writer.md` and `plan-briefer.md` adopt the new rules
  (stats-based sizing, self-spill, `Close:`/cite/ceiling, slice reading,
  `Spec §` and `Consumes` ledger columns, brief keyed by file); the Codex
  mirror (`sync_codex.py`, `AGENTS.md`) ships in the same commit.
- `docs/claude/skills-tools.md` § Plan writing, `document-conventions.md`
  § Splitting and `model-routing.md` describe the new controller steps
  (`--ledger` after `mode=index`, `--fix-parts` before committing parts,
  `model: sonnet` for prose-only parts).

Ledger shape this plan introduces (and dogfoods below):

```
| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |
```

`Files created / modified`: `C \`path\``, `M \`path\`` items. `Creates` and
`Consumes`: backticked tokens; the name checked is `plan_doc.symbol_name`
of each token (repo path if it contains `/`; a flag if it starts with `-`;
otherwise the last `.`/`::` segment before any `(`). A literal `|` inside a
cell is written `\|`.

## Global Constraints

- Python 3.11+, standard library only in `scripts/dev/` (no new
  dependency).
- Every function written or changed ends at cyclomatic complexity **< 15**
  (`scripts/dev/complexity_gate.py`); `plan_lint.main` is table-driven, one
  helper per check.
- Existing behaviour is preserved: `python scripts/dev/plan_lint.py <file>`
  keeps its output format (`PLAN LINT: PASS|FAIL  N file(s), M problem(s)`),
  exit codes (0/1/2) and every existing check; every plan numbered 193 or
  below lints exactly as before.
- New per-task checks apply when `plan_number(files) >= NEW_RULES_FROM`
  (`NEW_RULES_FROM = 194`): missing `Close:` line, task over
  `TASK_CEILING = 400` lines, `Modify: \`path:a-b\`` whose end line is past
  the file's length.
- Tests live under `tests/dev/` (suite `dev-setup`, `tests/suites.toml`; no
  suites.toml edit; 407 tests in the suite against the 1200 cap). They run
  the scripts as subprocesses with `cwd=ROOT` and fixtures in `tmp_path`,
  as `tests/dev/test_plan_lint.py` does; `plan_doc.py` may be imported
  directly via `importlib.util.spec_from_file_location`.
- Every `.claude/agents/*.md` change ships `python scripts/dev/sync_codex.py`
  output and the hand-condensed `AGENTS.md` edit in the same commit;
  `tests/hooks/test_codex_mirror.py` stays green. `CLAUDE.md` is not edited
  (it must stay under 200 lines).
- `.superpowers/briefs/` is gitignored and absent from worktrees: no test,
  agent rule or plan cites a brief path as a source of code; plans cite repo
  files.
- No `VERSION.json` change (`Bump: none`).

### Standard task close

Every task ends with `Close: standard (test: <path>)`, meaning these steps,
in order, and spells out only its deviations:

1. `git rev-parse --show-toplevel` prints the v193 worktree, and
   `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows
   nothing this task wrote into the main tree.
2. `python scripts/dev/testrun.py file <path>` → `0 failed`, `0 xfailed`.
3. `python scripts/dev/complexity_gate.py` → exit 0.
4. `git add` the task's files by name and commit
   `<feat|test|docs|chore>(v193): <summary> (V193-<n>)`, ending with the
   `Co-Authored-By:` trailer from the session's attribution reminder.

## Review Focus

1. **Old plans keep passing.** A v192-numbered plan with no `Close:` lines
   and a 709-line task lints PASS; the four existing v900 fixtures in
   `tests/dev/test_plan_lint.py` gain a `Close:` line so they keep passing
   under the new rules. Owner: V193-2 (`test_v192_plan_skips_new_rules`).
2. **`Modify:` cite variants.** `path` (no range), `path:120` (single line),
   `path:120-180 (fn)`, and a range on a file created by an earlier task (no
   length check — the file does not exist yet) must neither crash nor
   false-fail. Owner: V193-2 (`test_modify_range_variants`).
3. **`--fix-parts` is surgical and idempotent.** Only the `## Parts` table
   changes; existing Scope cells survive by part label; a spill file `_2b`
   gets a row; a second run leaves the index byte-identical. Owner: V193-4
   (`test_fix_parts_idempotent`).
4. **Escaped pipes in ledger cells.** A `Creates` cell such as
   `` `f(x) -> Path \| None` `` stays one cell. Owner: V193-1
   (`test_ledger_rows_escaped_pipe`).
5. **Slice in a worktree (no brief) or for an unknown part.** The slice still
   prints the index and spec sections with `MISSING: brief file …`; a part
   with no ledger rows exits 2 with a one-line message. Owner: V193-6
   (`test_slice_without_brief`, `test_slice_unknown_part`).

## Parallelisation

- V193-1 (`plan_doc.py`) and V193-2 (`plan_lint.py` per-task checks) touch
  disjoint files and share no contract: **parallel**.
- V193-2 → V193-3 → V193-4 → V193-5: **sequential**, all edit
  `scripts/dev/plan_lint.py` (V193-3 creates the `COMMANDS` dispatch that
  V193-4 and V193-5 extend).
- V193-5 and V193-6 consume `plan_doc` (V193-1): both start after V193-1.
  V193-6 (`plan_slice.py`, its own test file) may run **parallel** to
  V193-2..V193-5.
- V193-7 (agent files + Codex mirror) names the commands and their output
  lines, so it starts after V193-3..V193-6 are merged into the worktree
  branch (contract: the exact flag names and `MISSING:` / `PASS` lines).
- V193-8 (docs/claude + `AGENTS.md`) after V193-7: both edit `AGENTS.md`.
- V193-9 (full suite, merge) last.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-25-v193-plan-writer-pipeline_1-parser-lint-checks-stats-parts.md` | V193-1..V193-4 | worktree; shared parser `plan_doc.py`; per-task lint checks; `--stats`; `--fix-parts` |
| 2 | `2026-10-25-v193-plan-writer-pipeline_2-ledger-slice-and-agents.md` | V193-5..V193-9 | `--ledger`; `plan_slice.py`; plan-writer/plan-briefer agents with Codex mirror; docs; full suite and merge |

## Task ledger

| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |
|---|---|---|---|---|---|---|---|
| V193-1 | Worktree; shared plan-document parser `plan_doc.py` | 1 | sonnet | C | C `scripts/dev/plan_doc.py`, `tests/dev/test_plan_doc.py` | worktree branch `2026-10-25-v193-plan-writer-pipeline`; `backticked(cell: str) -> list[str]`; `sections(text: str, level: int = 2) -> dict[str, str]` (heading text → section incl. heading line, up to the next heading of the same or higher level); `ledger_rows(text: str) -> list[dict[str, str]]` (table under `## Task ledger`, keyed by stripped header cells, `\|` honoured); `spec_refs(cell: str) -> list[str]` (split on `;`/`,`, strip `§`); `resolve_ref(ref: str, headings: list[str]) -> str \| None` (heading == ref, or starts with ref + `.` or ref + space); `spec_path(index: Path, index_text: str) -> Path \| None` (target of the `**Spec:**` link, resolved against the index's folder, else repo-relative); `symbol_name(token: str) -> str`; constants `COL_TASK`, `COL_PART`, `COL_SPEC`, `COL_FILES`, `COL_CREATES`, `COL_CONSUMES` | — |
| V193-2 | Per-task lint checks: `Close:` line, task ceiling, `Modify:` range (from v194) | 1 | sonnet | B | M `scripts/dev/plan_lint.py`, `tests/dev/test_plan_lint.py` | `NEW_RULES_FROM = 194`; `TASK_CEILING = 400`; `MODIFY_RANGE_RE`; `CLOSE_RE`; `task_spans(lines: list[str]) -> list[tuple[str, int, int]]` (task id, start index, end index exclusive); `check_task_body(name: str, task: str, body: list[str]) -> list[str]`; `check_modify_range(name: str, line: str, created: set[str]) -> list[str]`; ctx key `new_rules` | `plan_lint.plan_number`, `plan_lint.scan_file` |
| V193-3 | `plan_lint.py --stats` and the `COMMANDS` flag dispatch | 1 | sonnet | A | M `scripts/dev/plan_lint.py`; C `tests/dev/test_plan_lint_stats.py` | `COMMANDS: dict[str, Callable[[list[str]], int]]`; `cmd_lint(args: list[str]) -> int`; `cmd_stats(args: list[str]) -> int`; `recent_plans(directory: Path, n: int = 5) -> list[list[Path]]`; `task_line_counts(files: list[Path]) -> list[int]`; `plan_stats(directory: Path, n: int = 5) -> dict[str, int]` (keys `plans`, `tasks`, `median`, `p90`, `per_part`); `STATS_DIR`; `PART_BUDGET = 1400`; output `PLAN STATS: …` | `task_spans`, `plan_lint.plan_files` |
| V193-4 | `plan_lint.py --fix-parts <index>` regenerates the parts table | 1 | sonnet | A | M `scripts/dev/plan_lint.py`; C `tests/dev/test_plan_lint_fix_parts.py` | `cmd_fix_parts(args: list[str]) -> int`; `parts_table(index: Path, old_scopes: dict[str, str]) -> list[str]`; `fix_parts(index: Path) -> int` (rows written; −1 when no `## Parts`); output `PARTS TABLE: …` | `COMMANDS`, `task_spans`, `plan_lint.plan_files` |
| V193-5 | `plan_lint.py --ledger <index>` contract check | 2 | sonnet | C | M `scripts/dev/plan_lint.py`; C `tests/dev/test_plan_lint_ledger.py` | `cmd_ledger(args: list[str]) -> int`; `check_contracts(index: Path) -> list[str]`; output `LEDGER CHECK: PASS\|FAIL  N row(s), M problem(s)` | `COMMANDS`, `ledger_rows`, `spec_refs`, `resolve_ref`, `spec_path`, `sections`, `backticked`, `symbol_name`, `plan_lint.tracked_paths` |
| V193-6 | `scripts/dev/plan_slice.py <index> <part>` | 2 | sonnet | C | C `scripts/dev/plan_slice.py`, `tests/dev/test_plan_slice.py` | `slice_part(index: Path, part: str, brief: Path \| None = None) -> tuple[str, list[str]]` (slice text, missing items); `default_brief(index: Path) -> Path`; `main(argv: list[str]) -> int`; output lines `MISSING: spec section '<ref>'`, `MISSING: brief section '<path>'`, `MISSING: brief file <path>` | `ledger_rows`, `sections`, `spec_refs`, `resolve_ref`, `spec_path`, `backticked` |
| V193-7 | plan-writer and plan-briefer agents adopt the pipeline; Codex mirror | 2 | sonnet | A; B; C; D; Model tier | M `.claude/agents/plan-writer.md`, `.claude/agents/plan-briefer.md`, `.codex/agents/plan-writer.toml`, `.codex/agents/plan-briefer.toml`, `AGENTS.md` | agent rules every later plan follows (stats sizing, self-spill `_<N>b`, `Close:` + cite + ceiling, slice reading, `Spec §`/`Consumes` columns, brief keyed by `## <repo path>`) | `scripts/dev/plan_slice.py`, `--stats`, `--fix-parts`, `--ledger` |
| V193-8 | Controller docs: skills-tools, document-conventions, model-routing; `AGENTS.md` | 2 | haiku | A; B; C; Model tier | M `docs/claude/skills-tools.md`, `docs/claude/document-conventions.md`, `docs/claude/model-routing.md`, `AGENTS.md` | — | `--ledger`, `--fix-parts`, `scripts/dev/plan_slice.py` |
| V193-9 | Full suite; merge to `main` | 2 | haiku | Testing | — | — | — |
