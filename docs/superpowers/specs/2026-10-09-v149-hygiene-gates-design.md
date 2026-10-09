# v149 — Hygiene gates: complexity ratchet, frontend lint, README paths

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** none (CI, dev tooling and docs only; nothing a user sees)
**Edge:** none (integrity) — three guards that stop the codebase silently getting worse. They issue no signal, move no threshold and change no live path; any effect on expectancy is indirect (fewer regressions in the scan and backtest code) and is not claimed.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer
**Status:** spec written 2026-10-09; no plan yet.

## Why

Three rules this repo states in prose are enforced by nothing:

1. **The complexity limit is honour-system.** `CLAUDE.md:136-141` and
   `docs/claude/code-complexity.md:7-10` say every function stays below
   cyclomatic complexity 15, but radon is in no requirements file
   (`code-complexity.md:35`: "not a project dependency"), no CI step and no
   test. The only places that run it are the two role-agent prompts
   (`.claude/agents/task-implementer.md:24`, `.claude/agents/task-reviewer.md:19`)
   and whoever remembers. A main-session fix, a Codex edit or a hurried
   hotfix can push a function to 40 and nothing fails.
2. **The Angular frontend has no linter at all.** `frontend/package.json`
   has no `lint` script and no ESLint dependency, `frontend/angular.json` has
   no `lint` target (architect has only `build` and `test`, the latter at
   `angular.json:72`), and there is no `eslint.config.*` anywhere under
   `frontend/`. CI's `frontend-test` job (`.github/workflows/deploy.yml:327`)
   runs unit tests and a production build only.
3. **`README.md` points at modules that moved.** Its `swingbot/core/` list
   (`README.md:53-75`) names flat files — `levels.py`, `trendlines.py`,
   `confidence.py`, `data.py`, … — that the v27 restructure moved into
   packages (`docs/claude/architecture.md:14-26`; `levels.py` is
   `swingbot/core/market/levels.py`). `README.md:78` names
   `swingbot/commands/scanning.py`, now the package
   `swingbot/commands/scanning/`. `README.md:99` says `HORIZONS` lives in
   `swingbot/core/market/strategy.py`; it lives in
   `swingbot/core/market/strategy_types.py:48`. No test reads the README.

## Scope

In:

- **H1** a ratcheting complexity gate: radon as a pinned dependency, a gate
  script with a checked-in baseline of today's offenders, a pytest test and
  a CI step, and the docs moved from "measure by hand" to "enforced".
- **H2** ESLint for `frontend/` with the angular-eslint recommended configs,
  `npm run lint`, a CI step, and a frozen baseline of today's violations.
- **H3** the README module paths corrected, and a test that every `.py`
  path the README names exists.

Out:

- Fixing any existing complexity offender or any existing lint violation.
  Both gates freeze today's debt and only stop it growing; decomposing a
  legacy function stays its own commit (`code-complexity.md:60-64`).
- Prettier, stylistic ESLint rules, or a lint/format pre-commit hook.
- Rewriting the README beyond the module lists and the `HORIZONS` pointer
  (its admin-UI paragraph at `README.md:87` still describes the deleted
  Jinja pages; noted under "Facts found", not fixed here).
- Changing the role-agent prompts. Their per-file
  `python -m radon cc -s -n C <files>` instruction stays correct and becomes
  cheaper to follow once radon is installed with the rest.

## Measured starting point (2026-10-09, main tree, radon 6.0.1, Python 3.11.9)

Over the 1,113 tracked `.py` files under `swingbot/`, `scripts/`, `tests/`,
`bot.py` and `admin_ui.py`, keyed as described in H1:

| | Count |
|---|---|
| Functions/methods scoring ≥ 15 | **123** (swingbot 86, scripts 32, tests 5; `bot.py`, `admin_ui.py` 0) |
| … scoring 15–19 | 64 |
| … scoring 20–29 | 34 |
| … scoring 30+ | 25 |
| Key collisions (two blocks, one key) | 0 |

Worst five: `swingbot.core.charts.trade_chart:generate_trade_chart` 191
(`trade_chart.py:207`), `swingbot.core.tracking.retrospective:build_daily_retrospective`
106 (`retrospective.py:391`), `swingbot.core.scanning.scan_run:_sync_run_scan`
100 (`scan_run.py:344`; `code-complexity.md:23` still quotes 108),
`swingbot.core.tracking.retrospective:_analyse` 72,
`scripts.backtest.run_backtest_range:main` 65.

A whole-tree scan took **18.8 s** serial on this machine; the first, cold run
took 176 s. The baseline is regenerated at implementation time from the
committed tree, never copied from this table (the main tree had another
session's uncommitted edits when it was measured).

## H1 — Complexity gate

### Dependency

`requirements.txt` is the only requirements file (no `requirements-dev.txt`,
`pyproject.toml` or `setup.cfg` exists), and it already carries the
test-only tools under the comment at `requirements.txt:92` — `pytest`,
`pytest-xdist`, and `pyflakes==3.4.0` (`requirements.txt:98-99`) for the
undefined-name gate. Add `radon==6.0.1` beside `pyflakes`, exact-pinned like
every runtime pin (the file's header, `requirements.txt:1-7`, explains why),
with a one-line comment naming `scripts/dev/complexity_gate.py`. Every CI
shard installs from this file (`deploy.yml:88`, `:138`, `:193`, `:246`,
`:300`). It also lands in the Docker image (`Dockerfile:83-88`), as pytest
and pyflakes already do; radon is pure Python and small.

### Keying

A function is keyed **`<dotted module path>:<radon fullname>`**:

```
swingbot.core.charts.trade_chart:generate_trade_chart
swingbot.commands.views:SomeView.on_timeout
scripts.backtest.run_backtest_range:main
```

The module part is the repo-relative path with `/` → `.` and `.py` dropped;
the name part is radon's `Function.fullname` (`Class.method` for a method,
bare name for a function). No line number, so a function moving within its
file, or code above it growing, never touches the baseline. Closures are not
keyed and not measured: radon 6.0.1 neither folds a closure's branches into
its parent's score (radon issue #68) nor reports the closure as a top-level
block, so neither the CLI nor the gate sees them. `code-complexity.md:40-41`
claims the opposite; the plan corrects that sentence.

If two blocks ever share a key (a conditional redefinition), the gate keeps
the higher score. There are none today.

### Files scanned

`git ls-files --cached --others --exclude-standard` filtered to `*.py` under
`swingbot/`, `scripts/`, `tests/`, plus `bot.py` and `admin_ui.py` — the
scope `code-complexity.md:8-9` already states. Including untracked files
means a new module is gated before its first commit. `.claude/` (hook
scripts) stays out, as the rule never covered it. A file radon cannot parse
fails the gate with its path (compileall in every CI shard,
`deploy.yml:91`, catches the same thing first).

### Baseline file

`scripts/dev/complexity_baseline.json`, next to the script:

```json
{
  "threshold": 15,
  "functions": {
    "scripts.backtest.run_backtest_range:main": 65,
    "swingbot.core.charts.trade_chart:generate_trade_chart": 191
  }
}
```

Keys sorted, two-space indent, trailing newline, so every change is a
one-line diff that review can read.

### Verdicts

The gate compares the scan against the baseline and sorts every finding
into one of four kinds:

| Kind | Meaning | Gate |
|---|---|---|
| `new` | scores ≥ 15, key not in the baseline | **fail** |
| `risen` | in the baseline, scores higher than recorded | **fail** |
| `improved` | in the baseline, scores lower than recorded (still ≥ 15) | **fail** — "run `--update`" |
| `gone` | in the baseline, now < 15 or no longer exists | **fail** — "run `--update`" |

`improved` and `gone` fail on purpose: a baseline left at the old, higher
score lets the function climb back to it unnoticed. Locking a gain costs one
`--update` and a one-line diff.

### `--update` only shrinks the baseline

`python scripts/dev/complexity_gate.py --update` rewrites the baseline with
every `improved` score lowered and every `gone` key dropped. It **never adds
a key and never raises a score**: if `new` or `risen` findings exist it
writes the shrink, prints them, and exits 1. Otherwise `--update` would be a
one-word way to accept any regression, which is the ratchet's whole point.

The one legitimate way a key appears is a **move or rename** of a legacy
offender (a pure refactor that relocates a function). The gate reports that
as a `gone` key plus a `new` key with the same score, and prints a hint
naming the pair. The author edits the key in the JSON by hand; the diff
shows one key renamed with an unchanged score, which a reviewer can confirm
in seconds. The baseline is generated once, at implementation, by a
`--init` flag that refuses to run if the file already exists.

### Script shape

`scripts/dev/complexity_gate.py`, every function under 15 (it is gated by
itself):

- `python_files(repo) -> list[str]` — the file list above.
- `measure(repo, paths) -> dict[str, int]` — keys scoring ≥ threshold.
- `load_baseline(path) -> dict[str, int]` / `write_baseline(path, scores)`.
- `compare(current, baseline) -> list[Finding]` — pure; `Finding` is a small
  frozen dataclass (`kind`, `key`, `old`, `new`).
- `shrink(baseline, current) -> dict[str, int]` — pure; the `--update` rule.
- `main(argv) -> int` — `check` (default), `--update`, `--init`; prints a
  one-line verdict in the style of `testrun.py` (`VERDICT: PASS …` /
  `VERDICT: FAIL  N finding(s)` followed by at most 20 lines).

### Enforcement

- **pytest:** `tests/dev/test_complexity_gate.py`. Fast unit tests of
  `compare`, `shrink` and the keying against tiny source strings written to
  `tmp_path`, plus one `@pytest.mark.slow` test that runs `measure` over the
  real tree and asserts `compare` returns nothing. Marked `slow`
  (`pytest.ini` markers) because ~19 s does not belong in the ~27 s `fast`
  tier; `testrun.py full` — the pre-commit gate — runs it, and so does CI.
- **CI:** `tests/dev/` is already in the `backend-test-misc` shard
  (`deploy.yml:305-307`), so the slow test runs there with no edit. A
  separate named step, `python scripts/dev/complexity_gate.py`, goes in the
  same job after "Compile every module" (`deploy.yml:302-303`), so a
  regression shows up as a red step named for what it is rather than one
  failure among a suite's output. It is the same check twice in one job
  (~19 s); the named step is the readable one.
- `testrun.py changed` selects tests by import graph
  (`scripts/dev/select_tests.py`), so it will not pick up the gate test for
  an arbitrary edit. That is acceptable: `full` and CI are the gates.

### Docs, and their Codex mirror (one commit)

- `CLAUDE.md:136-141`: replace the hand-measure wording with "enforced by
  `scripts/dev/complexity_gate.py` against `complexity_baseline.json`
  (`testrun.py full` and CI); `--update` only shrinks it". Same number of
  lines; `CLAUDE.md` is 169 lines today and stays under 200.
- `docs/claude/code-complexity.md`: § Measuring (`:32-41`) loses "once; not a
  project dependency" and gains the gate command, the four verdicts and the
  move/rename hand-edit; § Legacy functions (`:60-64`) names the baseline as
  the record of who is legacy.
- `AGENTS.md:319-336` (§ Function complexity limit): drop "install radon
  once; it is not a project dependency" (`AGENTS.md:322-323`), add the gate
  in one or two condensed lines. `tests/hooks/test_codex_mirror.py` checks
  coverage, not meaning (`working-conventions.md` § Codex mirror), so the
  condensation is by hand and lands in the same commit as `CLAUDE.md`.

## H2 — Frontend lint

### Setup

Run angular-eslint's schematic (`ng add angular-eslint`, at the major that
matches `@angular/core ~21.2.21`) in `frontend/`. It adds the dev
dependencies (`eslint`, `angular-eslint`, `typescript-eslint`), an
`eslint.config.js` flat config and a `lint` architect target. Keep what it
generates: `tseslint.configs.recommended`, angular-eslint's
`tsRecommended` with `processInlineTemplates`, and `templateRecommended` plus
`templateAccessibility` for `*.html`. Set the component/directive selector
rules to the project prefix `sb` (`angular.json:15`). Lint `src/` only —
`chart-harness/` is a standalone dev harness and the config files at the
root are not app code. Commit the updated `package-lock.json`; CI and the
Dockerfile's frontend stage both run `npm ci` (`deploy.yml:345-346`,
`Dockerfile:23`), which installs exactly what the lock pins. The Docker
stage gains the lint packages but never runs them.

### Ratchet: ESLint bulk suppressions

The first run's violations are frozen in `frontend/eslint-suppressions.json`
using ESLint's bulk suppressions (`eslint --suppress-all`, ESLint ≥ 9.24).
The file records a count per file per rule; a run fails on any violation
beyond those counts. This is chosen over `--max-warnings N` because a single
global count lets one fix elsewhere pay for one new violation anywhere, and
because rules stay at `error` severity instead of being downgraded to warn
for everyone.

When a suppressed violation is fixed, the unused entry is pruned with
`eslint --prune-suppressions` in the same commit, the same lock-the-gain
rule as H1's `--update`.

`npm run lint` is `eslint src` — the ESLint CLI directly, because the
suppressions file is a CLI feature and whether `ng lint`'s builder applies it
is unverified. The plan's first H2 task verifies three things and records
the answers in the task: the ESLint version `ng add` resolved supports bulk
suppressions; a deliberately added violation fails `npm run lint`; and a
fixed-but-unpruned suppression fails or passes it. If the resolved ESLint
cannot do suppressions, the fallback is `--max-warnings <first-run count>`
with every rule set to `warn`, and the spec's status line records the
downgrade.

### CI

A `Lint` step, `npm run lint`, in `frontend-test` between "Install"
(`deploy.yml:345-346`) and "Unit tests" (`deploy.yml:348-349`): seconds,
and it fails before the slower build.

## H3 — README paths

### Fix

- `README.md:53-75`: every `swingbot/core/` bullet names its module by full
  repo path (`swingbot/core/market/levels.py`, `swingbot/core/charts/trade_chart.py`,
  …). Where a name now has two homes the README means the one its text
  describes (`indicators.py` → `swingbot/core/market/indicators.py`;
  `watchlist.py` → `swingbot/core/marketdata/watchlist.py`; `account.py` →
  `swingbot/core/planning/account.py`; `events.py` →
  `swingbot/core/market/events.py`; `risk_metrics.py` →
  `swingbot/core/tracking/risk_metrics.py`); the plan's task confirms each
  against the module docstring. Add one line pointing at
  `docs/claude/architecture.md` for the full package map.
- `README.md:77-84`: the `swingbot/commands/` bullets get full paths;
  `scanning.py` becomes `swingbot/commands/scanning/commands.py`
  (`!check` is defined at `commands.py:48`).
- `README.md:86-87`: `app.py` → `swingbot/admin/app.py`.
- `README.md:99`: `HORIZONS` → `swingbot/core/market/strategy_types.py`.

### Test

`tests/dev/test_readme_paths.py`: every backticked token in `README.md`
ending in `.py` must be a repo-relative path that exists. Asserting only on
tokens that start with `swingbot/` would pass on today's README, because the
stale entries are bare names (`levels.py`); requiring every `.py` token to
be a full existing path is what gives the test teeth, and it is why the fix
writes full paths everywhere. `bot.py` and `admin_ui.py` pass as they are,
being real root paths. The failure message lists every missing path.

## Testing

- H1: `tests/dev/test_complexity_gate.py` — `compare` returns each of the
  four kinds on a constructed pair; `shrink` lowers and drops, never adds or
  raises; keying gives `Class.method`, survives a blank-line insertion above
  a function, and takes the max on a duplicate; `--init` refuses an
  existing file; the slow whole-tree test passes on the committed tree.
- H2: `npm run lint` exits 0 on the committed tree and non-zero after a
  deliberate violation (checked by hand in the task, then reverted; not a
  committed test).
- H3: `tests/dev/test_readme_paths.py` fails on today's README (verify
  before the fix) and passes after it.
- The plan's last task runs the full suite once (`document-conventions.md`
  § One full suite run).

## Facts found while writing (not fixed here)

- `docs/claude/architecture.md:14-15` and `CLAUDE.md:76` say no flat module
  remains under `swingbot/core/`, but `swingbot/core/risk_limits.py` is a
  tracked flat module (added `eb74053c`, 2026-09-14).
- `README.md:87` describes `swingbot/admin/app.py` as three server-rendered
  pages; that UI was deleted 2026-08-14 (`architecture.md:9-11`).
- v145 (`docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md`)
  also edits `CLAUDE.md`, `AGENTS.md` and the role agents; whichever plan
  implements second rebases its doc edits onto the first.

## Parallelisation

- **Group 1 (parallel):** H1's gate (script, baseline, `requirements.txt`,
  tests), H2's setup and suppressions (`frontend/` only), and H3 entire
  (`README.md`, `tests/dev/test_readme_paths.py`) — disjoint files, no
  symbol any other consumes.
- **Sequential:**
  - H1 script and tests before H1's CI step and docs (the step runs the
    script; the docs describe its flags).
  - H1's CI step and H2's CI step both edit `.github/workflows/deploy.yml`:
    one after the other, never in parallel, even though the hunks are in
    different jobs.
  - H1's `CLAUDE.md` / `code-complexity.md` / `AGENTS.md` edit is one task
    and one commit (Codex-mirror rule), and runs after any concurrent v145
    edit to those files has landed.
  - H1's baseline is generated (`--init`) after H3's test file exists in the
    branch, so the whole-tree test scans the final file set. H3's helpers
    are tiny, so this is ordering hygiene, not a real dependency.
  - The full suite last, after every group.
