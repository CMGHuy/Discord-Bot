# v99 — Change-aware test selection

**Version:** ui 1.19.0 · bot 1.10.1
**Bump:** none
**Edge:** none (integrity)

Ships no product code — a developer-loop tool under `scripts/dev/`. `Edge:` is
`none (integrity)` by the letter of the taxonomy: it buys iteration speed, not
expectancy. Stating that plainly matters, because faster iteration is the kind
of work that most easily borrows the language of an edge improvement it does
not deliver.

## The problem

Every bugfix and feature lands the same way today: run the whole suite. The
four existing profiles in `scripts/dev/testrun.py` are all *fixed-width* —
none of them looks at what changed to decide what to run.

| Profile | What it runs | Measured (2026-08-07, 1145 tests) |
|---|---|---|
| `full` | everything, `-n 4` | 40.2s |
| `fast` | `-m "not slow"`, serial | 27.1s |
| `file <path>` | one path, serial | ~7s |
| `lf` | `--lf`, serial | seconds |

`fast` is a two-tier cut, and only 17 of 392 test files carry `slow`. A
one-line change in `swingbot/core/planning/` therefore runs ~375 unrelated
files. The suite has since grown from 1145 to 1686+ passed, so the table's
timings are a floor, not a current reading.

`file` is the only genuinely narrow option, and it puts the selection burden on
the human: you have to already know which test files cover your change. That
knowledge is exactly what gets lost between sessions, and guessing it wrong is
silent — you get a green run over the wrong tests.

The one place the diff *is* consulted, `should_escalate()`, only ever widens
the run (`fast` → `full` when charts or design tokens are dirty). Nothing in
the repo narrows it.

## What this is not

**This does not touch the gate.** `/gate`, and a plan's single final
full-suite verification task (`document-conventions.md`, "One full suite run,
at the end of the plan"), are unchanged and still run everything. This is an
inner-loop tool only.

That boundary is the whole safety argument. A selection bug costs a slow
feedback cycle and nothing else, because the full suite still stands between
the work and a commit. Any future proposal to let selection gate a commit is a
separate spec, and needs the audit evidence described under "Accuracy audit"
before it is worth writing.

## Approach

A static import graph over tracked Python, inverted into a reverse-dependency
map: changed source file → the test modules that transitively import it.

Two alternatives were considered and rejected:

- **A hand-written directory map** (`swingbot/core/planning/*` → `tests/planning/`).
  Ships in an hour, but under-selects badly here. `plan_engine` alone is
  imported from tests in `scanning/`, `backtesting/` and `admin/`; a package
  map misses every one of those edges. A selector that shows green and is then
  contradicted by the gate stops being used within a week.
- **A coverage index** (`pytest-testmon` or equivalent). Precise at per-test
  granularity, but adds a dependency, adds a state file that goes stale
  silently, and fights `xdist`. Precision that cannot be audited from the
  source tree is the wrong trade for an inner loop.

The import graph wins on one property the other two lack: **it is derived from
the code, so it cannot drift.** There is no map to maintain and no index to
refresh. Its cost is a single AST pass at each invocation.

### Why the graph is accurate enough here

Tests import their subject directly and specifically — 130 distinct
`swingbot.*` import targets across `tests/`. The ~20 test files with no direct
`swingbot` import are almost all `tests/admin/` API tests that reach the app
through `tests/admin/conftest.py`, and script tests that import from
`scripts/`. Both are handled: conftest membership and `scripts/` are nodes in
the same graph.

Hub modules over-select — a change to `swingbot/config.py` reaches nearly
every test — and that is the correct answer, not a defect.

### The blind spot, named

**A static graph cannot see registry and string-lookup wiring.** Strategy
modules under `swingbot/core/edge/` are reached by name through the registry,
not by import, so the tests that exercise them do not import them. This is
precisely where a miss is expensive.

This is handled by declaration, not by cleverness: a `REGISTRY_PREFIXES`
constant whose members force a full run, each entry carrying a comment saying
why it cannot be graph-resolved. That is the convention `ESCALATE_PREFIXES`
already uses in `testrun.py`.

Initial members:

| Prefix | Why the graph cannot see it |
|---|---|
| `swingbot/core/edge/` | strategy modules dispatched by registry name |
| `swingbot/core/market/strategy_types.py` | `HORIZONS`/strategy identity consumed by name across the scan pipeline |
| `swingbot/config.py` | `.env`-driven schema read by attribute across the tree; also a hub that would select nearly everything anyway |

`ESCALATE_PREFIXES` (charts, design tokens) keeps its current meaning and
applies to the new profile too.

## Architecture

### Unit boundary

Selection lives in a **new module**, `scripts/dev/select_tests.py`. It does
not go into `testrun.py`.

`testrun.py` is 293 lines already carrying three responsibilities — fast-tier
escalation, the pyflakes undefined-name gate, and run/stream/parse. Selection
is a fourth with real branching logic and its own failure modes, and it needs
tests that do not involve launching pytest. Adding it in place would make the
largest file in `scripts/dev/` the one hardest to reason about.

`select_tests.py` imports nothing from pytest and nothing from `swingbot`. It
is a pure function of the repo's files plus a list of changed paths, which is
what makes it directly unit-testable against a fixture tree.

**Public interface:**

```python
@dataclass(frozen=True)
class Selection:
    targets: list[str]        # test paths to pass to pytest; empty means nothing to run
    full: bool                # True -> caller must run the full suite instead
    reason: str               # one line, always populated, always printable
    changed: list[str]        # the changed paths the decision was made from

def build_import_graph(repo: Path) -> dict[str, set[str]]:
    """file -> set of repo-relative files that import it (reverse edges)."""

def select(changed: list[str] | None, repo: Path) -> Selection:
    """Map changed paths to test paths. Widens to full on any uncertainty.

    `changed=None` means the caller's git query failed -> Selection(full=True).
    """
```

`changed` is a parameter, not something `select()` discovers: `testrun.py`
owns the git query (it already has `changed_paths()`, which returns `None`
when git cannot answer) and passes the result in. That is what keeps
`select_tests.py` a pure function of (files on disk, changed paths) and
testable against a fixture tree with no git repo in it.

`testrun.py` calls `changed_paths()`, then `select()`, prints `reason`, and
either runs `targets` or falls through to its existing `full` path. Nothing
else in `testrun.py` changes.

### Graph construction

1. `git ls-files '*.py'` — tracked files only. This is what keeps
   `.claude/worktrees/` out (four live worktrees at time of writing; `.ignore`
   hides them from Grep but not from a filesystem walk).
2. `ast.parse` each file; collect `Import` and `ImportFrom` nodes, including
   relative imports resolved against the importing file's package.
3. Resolve each dotted name to a repo-relative path, trying both `pkg/mod.py`
   and `pkg/__init__.py`. Names that resolve to neither are third-party and
   are dropped.
4. Invert into the reverse map.

### Selection algorithm

Evaluated in order; the first matching rule decides.

1. The caller supplies `changed` from `changed_paths()` — the existing
   function in `testrun.py`, reused, not reimplemented. Working tree + staged
   + untracked against `HEAD`.
2. `changed is None` (git could not answer) → **full**, reason
   `git unavailable`.
3. Any changed path under `ESCALATE_PREFIXES` or `REGISTRY_PREFIXES` →
   **full**, reason naming the first hit.
4. Any changed path that is neither Python nor on the inert allowlist
   (`docs/**`, `*.md`, `.claude/**`, `.superpowers/**`) → **full**, reason
   naming it. A changed `.json`, `.css`, `.yml` or `Dockerfile` is unplaceable
   by a Python import graph, and unplaceable means widen.
5. Otherwise, per changed Python path:
   - under `tests/` → selects itself.
   - a `conftest.py` → selects its entire directory subtree (there are four:
     `tests/`, `tests/admin/`, `tests/db/`, `tests/scanning/`).
   - anything else (`swingbot/**`, `bot.py`, `admin_ui.py`, `scripts/**`) →
     transitive closure over the reverse map, filtered to paths under `tests/`.
6. Selected set larger than `FULL_THRESHOLD` of all test files → **full**,
   reason naming the fraction. Past some breadth, `-n 4` over everything beats
   serial over most of it.
7. Nothing selectable — either no changed paths at all, or every changed path
   was on the inert allowlist — → `targets` empty, `full=False`, reason
   `nothing to test (N inert path(s))`, exit 0 without invoking pytest.

   Rules 4 and 7 are the two halves of one decision and must not be confused:
   an **inert** path (a `.md`, a file under `docs/`) is known to affect no
   test, so it selects nothing; an **unplaceable** path (a `.css`, a
   `.json`, a `Dockerfile`) is one the graph has no opinion about, so it
   widens to full. Silence and ignorance get opposite treatment.

**`FULL_THRESHOLD` ships as an unmeasured constant at `0.4`, and its comment
must say so.** The crossover between "serial over N files" and "`-n 4` over
everything" has not been measured, and `testing-cost.md` is explicit that
timings on this box swing up to 4x under load — deriving it properly needs a
cooled, idle box. A named constant with an honest comment is the correct
shape; a number quoted as if measured is not.

### The invariant

**Every failure mode widens. None narrows.**

An unparseable file → full (it has a syntax error; the suite is about to tell
you anyway). An unresolvable import → full. An unknown extension → full. A
`git` call that fails → full. The selector may waste your time; it may not
cost you coverage.

This mirrors the comment already on `should_escalate()`: *"Fail safe, not
fast: if we cannot tell what changed, run everything."*

## CLI

```bash
python scripts/dev/testrun.py changed             # select, then run
python scripts/dev/testrun.py changed --dry-run   # print the selection, run nothing
python scripts/dev/testrun.py changed --audit     # run the selection, then full; report misses
```

`changed` runs its targets **serially** with the existing `BASE` args. Below
the threshold the set is small, and xdist's worker startup dominates at that
size — the same reason `fast` is serial today.

The verdict line carries the selection so it is auditable at a glance:

```
VERDICT: PASS  84 passed  in 9.3s  (12 test files selected from 3 changed)
```

When the selector widens, it says so before running:

```
NOTE: swingbot/core/edge/rsi.py touched (registry dispatch) -> full suite
```

`--dry-run` exists so a wrong selection is *visible* rather than inferred from
a suspiciously fast green run. It prints the reason, the changed paths and the
selected targets, and exits 0.

## Accuracy audit

`--audit` runs the selection, then the full suite, and reports any test that
failed in the full run but was not in the selection. That set is the only
thing that matters: a miss is a regression the inner loop would have hidden.

It is not part of anyone's routine. It exists to accumulate evidence, and it
is the input to a later, separate decision about whether selection could ever
gate a commit. Without it that question can only be answered by assertion.

## Error handling

| Condition | Behaviour |
|---|---|
| `git` unavailable or non-zero | full, reason printed |
| `ast.parse` raises on any file | full, reason names the file |
| import resolves to no repo file | dropped as third-party (not an error) |
| changed path with unhandled extension | full, reason names the path |
| selection exceeds `FULL_THRESHOLD` | full, reason names the fraction |
| nothing changed | run nothing, exit 0 |

No condition results in a narrowed run. There is no `--force-narrow` escape
hatch; `file <path>` already covers the case where you want to override the
tool's judgement, and adding a second way to do it would be the one flag that
can turn a selector bug into a missed regression.

## Testing

`tests/dev/test_select_tests.py`, alongside the two existing dev tests. Every
case runs against a small fixture tree under `tmp_path`, not against the real
repo — the real repo's graph changes every commit and would make the tests
drift.

| Case | Asserts |
|---|---|
| graph build | direct, relative and `__init__` imports all produce reverse edges |
| third-party import | `import pandas` produces no edge, raises nothing |
| transitive selection | A imports B imports C; change C → A's test selected |
| test file changed | selects itself, nothing else |
| conftest changed | selects the whole subtree |
| registry prefix | `swingbot/core/edge/x.py` → `full=True`, reason names it |
| escalate prefix | `swingbot/core/charts/x.py` → `full=True` |
| unplaceable extension | a changed `.css` → `full=True`, reason names it |
| inert path | a changed `.md` alone → nothing selected, `full=False` |
| unparseable file | a file with a syntax error → `full=True`, reason names it |
| threshold | a selection over the fraction → `full=True` |
| nothing changed | empty targets, `full=False`, reason `nothing changed` |

One integration test in the same file drives `select()` against the real repo
and asserts only that it returns without raising and that a change to
`swingbot/config.py` widens — a smoke test, not a fixed expected set, because
a fixed set would need editing on every unrelated commit.

## Documentation

- `docs/claude/testing-cost.md` — a section describing the profile, the
  widen-never-narrow invariant, and `FULL_THRESHOLD` being unmeasured.
- `CLAUDE.md` — one line in the Commands block. The file is near its 200-line
  cap; if the line does not fit, the token-discipline bullet about `testrun.py`
  absorbs it rather than the block growing.
- `.codex/AGENTS.md` — mirrored condensed, one-way, per `CLAUDE.md`.

## Explicitly not building

- Per-test granularity. File granularity is what an import graph can support
  honestly.
- Caching the graph to disk. It is one AST pass over ~620 tracked Python
  files. Measure the build cost on a cooled box before deciding it needs a
  cache; a stale cache is the exact failure mode this design rejected in the
  coverage-index alternative.
- A watch mode.
- Any change to `/gate`, to `.claude/hooks/guardrails.py`, or to the plan-final
  full-suite verification task.
- Reducing the cost of the runs themselves — the five chart files at ~43% of
  serial runtime are a real target, and a separate spec.

## Parallelisation

- **Sequential throughout.** Three of the four units are a chain:
  `select_tests.py` must exist before `testrun.py` can call it, and before its
  tests can be written against a settled interface. The `Selection` dataclass
  is the contract every later unit consumes.
- **Group 1 (parallel), after the module and its tests are green:** the
  `testrun.py` wiring and the documentation updates touch disjoint files
  (`scripts/dev/testrun.py` versus `docs/claude/testing-cost.md`, `CLAUDE.md`,
  `.codex/AGENTS.md`) and neither consumes a symbol the other introduces.
- `--audit` is last regardless: it needs both the selector and the wiring.
