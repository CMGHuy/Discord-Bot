# v27 — Repository Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.2.3 · bot 1.1.2
Bump: `bot patch (1.1.2 → 1.1.3)` · `ui none`
Spec: `docs/superpowers/specs/2026-08-15-v26-repo-restructure-design.md`
Blocked on: `v24-control-alignment` and `v25-trade-chart` merged to `main`.

**Goal:** Group `swingbot/core`'s 45 flat modules into six sub-packages, group
`scripts/` and `tests/`, move five documents off the repo root, and rewrite every
reference that points at any of it — with zero behaviour change.

**Architecture:** Five sequential phases, each ending green. Documentation and
scripts move first because they cannot break an import. The core re-package runs
last, one sub-package per task, each task moving files *and* rewriting all
references to them so every commit is independently green. A single throwaway
tool (Task 7) performs the rewrite; it is deleted in the final task.

**Tech Stack:** Python 3.11+, pytest, `git mv`, `python -m compileall`.

## Progress

> All 15 tasks complete, 2026-08-15. Final suite: **1663 passed, 136 skipped,
> 0 failed** — exactly the Task 1 baseline, restored after Tasks 7–14's
> +12-test tool interval. Version bumped `bot 1.1.3 → 1.1.4` (the plan's
> header predicted `1.1.2 → 1.1.3`; `main` had already consumed 1.1.3 for an
> unrelated release before this plan ran — bumped one more patch instead).
>
> **Deviations and gaps this plan's text didn't anticipate**, found and fixed
> while executing (all verified against the full suite before commit):
> - Task 4: moving `scripts/` broke ~34 `ROOT = Path(__file__).resolve()
>   .parent.parent`-style computations (one directory level short) and ~20
>   sibling-script imports, across code the plan's five named executable
>   references didn't cover. `deploy/deploy.sh`'s live smoke-test invocation
>   needed the same fix.
> - Task 6: grouping `tests/` broke 16 cross-test-file imports
>   (`tests.test_X` helper imports) and 5 more `ROOT`/`CACHE`-style
>   computations, for the same one-level-short reason.
> - Tasks 8–12: the repackage tool's Task-7-documented design — rewrite
>   every module's reference to its FINAL package on the very first
>   invocation, using the complete map, while only physically moving that
>   task's own modules — means the suite cannot collect cleanly between
>   Task 8 and Task 13. Verified each intermediate task compiled clean and
>   diffed to import/path-only changes; deferred the full-suite pytest
>   check to Task 13, where it passed with one more fix (a relative
>   `from .. import config` in `data_refresh.py`, invisible to the tool
>   because `config` isn't a tracked core module).
> - Task 15: the repo-wide dangling-path sweep caught 22 more stale
>   `swingbot/core/*.py` references beyond the task's named file list
>   (README.md, docs/features.md, docs/superpowers/edge-premortem.md,
>   swingbot/config.py, .env.example, bot.py, requirements.txt, and others).
>   Separately, regenerating `version_history.json` for the bump surfaced a
>   `Path(__file__).resolve().parents[1]` in `build_version_matrix.py` —
>   the `.parents[N]` indexing idiom, which Task 4's `.parent.parent` /
>   `dirname(dirname(...))` sweep pattern didn't match — silently pointed
>   at `scripts/` instead of the repo root once the script moved into
>   `scripts/dev/`. Fixed; it was the only such instance repo-wide.
>
> **Deliberately left as-is:** the v27 plan's and v26 spec's own bodies,
> and `docs/superpowers/plans/v27-baseline.md` (deleted in Task 15 anyway),
> keep their old flat-path prose — they narrate the move itself and
> rewriting them mid-narrative would make the history unreadable, not more
> accurate. Two `scripts/*.py` mentions in
> `docs/MANUAL_VERIFICATION_CHECKLIST.md` (`gate_fold_run.py`,
> `macro_smoke.py`) were never real paths — they describe scripts a future,
> unrelated task creates — and were left alone.

## Global Constraints

- **No behaviour changes.** A diff hunk that is not a file move, an import line, a
  path string, or a documentation reference is a bug in this plan's execution.
- **No new compatibility shims.** The two that exist (`core/scan_engine.py`,
  `core/trade_plan.py`) are deleted by Task 14.
- **No package may share a name with a module inside it.** This is why the
  packages are `marketdata/` and `backtesting/`, not `data/` and `backtest/`.
- **Every relative import touching a moved module becomes absolute.**
- **Never edit files under `.claude/worktrees/`** from this working tree.
- **The verification gate is the count recorded in Task 1**, not a literal 1686.
  `0 failed` and `0 xfailed` are absolute.
- **Use `git mv`**, never delete-and-recreate — rename detection is what keeps
  this reviewable.
- Run the suite through `python scripts/testrun.py full` (path becomes
  `scripts/dev/testrun.py` after Task 4), never raw pytest, so one verdict line
  reaches the session instead of ~1150 progress lines.

---

# Phase 1 — Baseline and documentation

## Parallelisation

**Sequential throughout.** Task 1 produces the baseline number every later task
gates against. Tasks 2 and 3 both edit `README.md`, so they cannot be grouped.

---

### Task 1: Record the baseline and reconcile the spec's inventories

The spec's module tables were measured on 2026-08-15, before v24 and v25 landed.
This task replaces them with the truth on disk and records the test count every
subsequent task must match.

**Files:**
- Create: `docs/superpowers/plans/v27-baseline.md` (working notes, deleted in Task 15)

- [ ] **Step 1: Confirm the predecessors have landed**

```bash
git fetch origin
git log --oneline -15 origin/main
ls docs/superpowers/plans/*.md
```

Expected: `2026-08-14-v24-control-alignment.md` and `2026-08-14-v25-trade-chart.md`
are **no longer** at the top level of `plans/` (they moved to `implemented/` when
they closed). If either is still there, **stop — this plan is not ready to run.**

- [ ] **Step 2: Confirm a clean tree at origin/main**

```bash
git status --porcelain
git rev-list --count origin/main..main
git rev-list --count main..origin/main
```

Expected: no output from the first, `0` from both counts.

- [ ] **Step 3: Record the baseline test count**

```bash
python scripts/testrun.py full
```

Write the exact verdict line into `docs/superpowers/plans/v27-baseline.md`, e.g.
`BASELINE: 1702 passed, 66 skipped, 0 failed, 0 xfailed`. Every later task
compares against this number. If it does not show `0 failed, 0 xfailed`, stop and
fix `main` before restructuring anything.

- [ ] **Step 4: Reconcile the three inventories against the spec**

```bash
git ls-files 'swingbot/core' | awk -F/ 'NF==3' | grep '\.py$'
git ls-files 'tests'   | awk -F/ 'NF==2'
git ls-files 'scripts' | awk -F/ 'NF==2'
```

Diff each against the spec's tables. Expect v25 to have added
`swingbot/core/charts/trendline_fit.py` (in `charts/`, which does not move — no
action) and three test files: `tests/test_trendline_fit.py`,
`tests/test_trade_chart_stored_fit.py`, `tests/test_trendline_fit_persistence.py`.

For every file present on disk but absent from a spec table, assign it using the
spec's grouping rule and **write the assignment into `v27-baseline.md`**:

- `core/` — fetches or caches market data → `marketdata/`; computes an indicator,
  level or signal from bars → `market/`; constructs or tracks a live plan →
  `planning/`; offline replay and validation → `backtesting/`; writes or reports
  the trade log → `tracking/`; JSON, locks, delivery channels → `infra/`.
- `tests/` — mirrors the package of the module under test. The three v25 files
  above all test chart code, so they go to `tests/charts/`.
- `scripts/` — `backtest/`, `data/`, `reports/`, `dev/` by primary purpose.

- [ ] **Step 5: Commit the baseline notes**

```bash
git add docs/superpowers/plans/v27-baseline.md
git commit -m "chore: record the v27 restructure baseline and reconciled inventories"
```

---

### Task 2: Split README.md into four documents

`README.md` is 788 lines across 33 `##` sections that are really three documents.

**Files:**
- Create: `docs/strategy.md`, `docs/setup.md`, `docs/commands.md`, `docs/features.md`
- Modify: `README.md` (reduced to overview + index)

- [ ] **Step 1: Confirm the section boundaries still hold**

```bash
grep -n '^## ' README.md
```

v25 may have added or moved sections. The line numbers below are from
2026-08-15; **re-derive them from this output** rather than trusting them.

- [ ] **Step 2: Carve out the four documents**

Move the sections verbatim — no rewriting of prose in this task:

| New file | Sections (by heading, not line number) |
|---|---|
| `docs/strategy.md` | "The core idea" through "Command hints" — the conceptual run: levels, filters, horizons, entry/stop rules, confidence, regime filter, symbol resolution |
| `docs/setup.md` | "1. Create the Discord bot", "2. Configure", "3. Install & run", "5. Running it 24/7" |
| `docs/commands.md` | "4. Commands" |
| `docs/features.md` | "Event loop responsiveness", "Plan Engine v2", "Analytics core", "Admin cockpit", "Admin UI", "The growth playbook" |

`README.md` keeps its intro (through the first `##`), plus the "Files" and
"Customizing" sections.

Give each new file an `# H1` title matching its subject and demote nothing else —
the `##` levels stay as they are.

- [ ] **Step 3: Add the index to README.md**

Insert after the intro, before "Files":

```markdown
## Documentation

| Document | What's in it |
|---|---|
| [docs/strategy.md](docs/strategy.md) | How the bot decides: levels, filters, horizons, confidence, regime |
| [docs/setup.md](docs/setup.md) | Creating the Discord bot, configuring `.env`, installing, running 24/7 |
| [docs/commands.md](docs/commands.md) | Every Discord command |
| [docs/features.md](docs/features.md) | Plan Engine v2, analytics, the admin cockpit and SPA |
| [DOCKER.md](docs/DOCKER.md) · [DEPLOY_HETZNER.md](docs/DEPLOY_HETZNER.md) | Container build and deployment |
```

The `docs/DOCKER.md` and `docs/DEPLOY_HETZNER.md` links point at where Task 3
puts them, so they dangle until Task 3 lands. That is intentional — Task 3 is the
next commit and moving them here would mean editing this table twice.

- [ ] **Step 4: Verify nothing was lost**

```bash
wc -l README.md docs/strategy.md docs/setup.md docs/commands.md docs/features.md
```

Expected: the four new files plus the reduced README total roughly 788 lines plus
the index table and four H1s. A total more than ~20 lines short means a section
was dropped.

```bash
python scripts/testrun.py full
```

Expected: matches the Task 1 baseline exactly. (Docs-only change; this is a
regression check on the split, not on the docs.)

- [ ] **Step 5: Commit**

```bash
git add README.md docs/strategy.md docs/setup.md docs/commands.md docs/features.md
git commit -m "docs: README was three documents in one file"
```

---

### Task 3: Move root documents and stray artifacts

**Files:**
- Move: `DOCKER.md`, `DEPLOY_HETZNER.md`, `MANUAL_VERIFICATION_CHECKLIST.md` → `docs/`
- Move: `exit_v2_validation.json`, `rescue_rsi_validation.json` → `docs/superpowers/results/`
- Delete: `.env.bak`, `backtest_range_summary.txt` (both untracked)
- Modify: every file referencing the moved paths

- [ ] **Step 1: Find every reference before moving anything**

```bash
git grep -n 'DOCKER\.md\|DEPLOY_HETZNER\.md\|MANUAL_VERIFICATION_CHECKLIST\.md' -- . ':!docs/superpowers/plans/implemented' ':!docs/superpowers/specs/implemented'
git grep -n 'exit_v2_validation\.json\|rescue_rsi_validation\.json'
```

Record the list. Historical documents under `implemented/` are excluded
deliberately — they are a record of what was true when written, not live
references, and rewriting them destroys that.

- [ ] **Step 2: Move the files**

```bash
git mv DOCKER.md DEPLOY_HETZNER.md MANUAL_VERIFICATION_CHECKLIST.md docs/
git mv exit_v2_validation.json rescue_rsi_validation.json docs/superpowers/results/
```

- [ ] **Step 3: Delete the untracked strays**

```bash
git status --porcelain --ignored=no    # confirm neither is tracked
rm -f .env.bak backtest_range_summary.txt
```

`.env.bak` is a stale copy of `.env` from 2026-07-05 and is not the live config.
Confirm `.env` itself is untouched and still present before finishing this step.

- [ ] **Step 4: Update every reference found in Step 1**

Including the `README.md` index rows added in Task 2, `CLAUDE.md`, the
`.github/workflows/`, `deploy/deploy.sh`, and any `docs/claude/*.md` that cite
them.

- [ ] **Step 5: Verify no dangling references**

```bash
git grep -n '\](DOCKER\.md\|\](DEPLOY_HETZNER\.md\|\](MANUAL_VERIFICATION_CHECKLIST\.md'
```

Expected: no output. Then:

```bash
python scripts/testrun.py full
```

Expected: matches the Task 1 baseline.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: five documents that were never repo-root material"
```

---

# Phase 2 — scripts/

## Parallelisation

**Sequential: Task 4 before Task 5.** Task 5's sweep searches for the old paths
Task 4 creates the new homes for. The four script folders inside Task 4 are
disjoint and could in principle be moved concurrently, but the move is one
`git mv` batch in one commit, so there is nothing to parallelise across sessions.

---

### Task 4: Group scripts/ and fix the five executable references

**Files:**
- Create: `scripts/backtest/`, `scripts/data/`, `scripts/reports/`, `scripts/dev/`
- Move: all 32 scripts (re-derive the list — v25 may have added some)
- Modify: `swingbot/admin/jobs.py`, `scripts/backtest/quarterly_revalidation.py`,
  `.github/workflows/deploy.yml`

- [ ] **Step 1: Move the scripts**

```bash
mkdir -p scripts/backtest scripts/data scripts/reports scripts/dev

git mv scripts/run_backtest_range.py scripts/tune_strategy.py scripts/tune_exit_v2.py \
       scripts/tune_confluence_gates.py scripts/run_confluence_validation.py \
       scripts/wf_run.py scripts/wf_components.py scripts/permutation_test.py \
       scripts/ablation.py scripts/reversal_ab.py scripts/quarterly_revalidation.py \
       scripts/backtest/

git mv scripts/fetch_backtest_data.py scripts/fetch_intraday_cache.py \
       scripts/build_universe.py scripts/fmp_crawl.py scripts/migrate_market_data.py \
       scripts/record_option_snapshots.py scripts/validate_data.py \
       scripts/fill_regime_allow.py scripts/backfill_journal.py \
       scripts/data/

git mv scripts/shadow_parity_report.py scripts/shadow_component_report.py \
       scripts/sizing_shadow_report.py scripts/parity_exits.py scripts/parity_sizing.py \
       scripts/export_analytics.py scripts/audit_quality_score.py \
       scripts/reports/

git mv scripts/testrun.py scripts/smoke_spa.py scripts/render_chart_fixtures.py \
       scripts/seed_parity_fixtures.py scripts/dump_chart_payloads.py \
       scripts/dev/
```

Then confirm nothing is left behind:

```bash
git ls-files 'scripts/*' | awk -F/ 'NF==2'
```

Expected: no output. Anything listed is a script added after 2026-08-15 — place
it by the rule recorded in Task 1 and note it.

- [ ] **Step 2: Fix the executable reference in the admin's job runner**

This is the one that breaks a live feature. In `swingbot/admin/jobs.py` around
line 202:

```python
script = os.path.join(config._PROJECT_ROOT, "scripts", "tune_strategy.py")
```

becomes:

```python
script = os.path.join(config._PROJECT_ROOT, "scripts", "backtest", "tune_strategy.py")
```

- [ ] **Step 3: Fix the three subprocess calls in quarterly_revalidation.py**

In `scripts/backtest/quarterly_revalidation.py`:

```python
# line ~63
subprocess.run([sys.executable, "scripts/data/fetch_backtest_data.py", "--force"],
# line ~111
wf = subprocess.run([sys.executable, "scripts/backtest/wf_run.py", "--full", "--portfolio",
# line ~119
perm = subprocess.run([sys.executable, "scripts/backtest/permutation_test.py",
```

- [ ] **Step 4: Fix the CI workflow**

In `.github/workflows/deploy.yml` line ~63:

```yaml
        run: python scripts/dev/testrun.py full
```

Line ~58 (`python -m compileall -q swingbot bot.py admin_ui.py scripts tests`)
names the directory, not a file — **leave it alone.**

- [ ] **Step 5: Verify no executable path was missed**

```bash
git grep -nE '(subprocess|sys\.executable|"scripts"|python )[^\n]*scripts/[a-z_]+\.py' -- swingbot scripts .github deploy
```

Every hit must name a path that exists:

```bash
git grep -ohE 'scripts/[a-z_/]+\.py' -- swingbot scripts .github deploy | sort -u | while read p; do [ -e "$p" ] || echo "DANGLING: $p"; done
```

Expected: no `DANGLING` lines.

- [ ] **Step 6: Run the suite**

```bash
python scripts/dev/testrun.py full
```

Note the new path. Expected: matches the Task 1 baseline. `tests/admin/test_jobs.py`
and `tests/admin/test_api_v1_jobs.py` cover the Step 2 change;
`tests/scripts/test_quarterly_revalidation.py` covers Step 3.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: scripts/ by purpose, and the five paths that actually execute"
```

---

### Task 5: Sweep the prose references to script paths

~72 references name script paths in documentation, comments and docstrings. None
break a run; all mislead the next session.

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/**`, `.claude/agents/*.md`,
  `.claude/skills/gate/SKILL.md`, `.claude/settings.json`, `.env.example`,
  `pytest.ini`, `.gitignore`, `frontend/chart-harness/README.md`,
  `frontend/src/app/stores/analytics.store.ts`, and docstrings across
  `swingbot/` and `scripts/`

- [ ] **Step 1: Enumerate what is now stale**

```bash
git grep -ohE 'scripts/[a-z_]+\.py' -- . ':!docs/superpowers/plans/implemented' ':!docs/superpowers/specs/implemented' ':!docs/superpowers/results' \
  | sort -u | while read p; do [ -e "$p" ] || echo "$p"; done
```

Every path printed is stale and needs rewriting to its new home.

- [ ] **Step 2: Rewrite them**

Work file by file from the Step 1 list. The high-traffic ones:

- `CLAUDE.md` — the whole `## Commands` block, plus the `scripts/testrun.py`
  mentions in the token-discipline section.
- `.claude/agents/test-runner.md` and `.claude/agents/backtest-runner.md` — these
  tell subagents which command to run; a stale path here silently degrades every
  future test dispatch.
- `.claude/skills/gate/SKILL.md` and `.claude/settings.json`.
- `pytest.ini`'s header comment block.

Leave `docs/superpowers/plans/implemented/**`, `specs/implemented/**` and
`results/**` untouched — historical record.

- [ ] **Step 3: Verify**

Re-run the Step 1 command. Expected: no output.

```bash
python scripts/dev/testrun.py full
```

Expected: matches the Task 1 baseline.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: re-point every script path the move invalidated"
```

---

# Phase 3 — tests/

## Parallelisation

**Sequential, single task.** Nothing to parallelise: one `git mv` batch and one
suite run.

---

### Task 6: Group tests/ to mirror the core packages

**Files:**
- Create: `tests/marketdata/`, `tests/market/`, `tests/planning/`,
  `tests/backtesting/`, `tests/tracking/`, `tests/infra/`, `tests/edge/`,
  `tests/charts/`, `tests/scanning/`, `tests/analytics/`
- Move: the flat `tests/test_*.py` files
- Unchanged: `tests/admin/`, `tests/scripts/`, `tests/fixtures/`, `tests/conftest.py`

- [ ] **Step 1: Check for basename collisions before moving**

With no `__init__.py` files, pytest derives module names from basenames, so two
same-named files in different directories abort collection.

```bash
git ls-files 'tests/**/*.py' | xargs -n1 basename | sort | uniq -d
```

Expected: no output. If a name is printed, rename one of the pair before moving.

- [ ] **Step 2: Move the test files**

Group each `tests/test_X.py` into the directory matching the package its subject
now lives in. Use the assignments recorded in Task 1 for any file the spec did
not name. The v25 additions — `test_trendline_fit.py`,
`test_trade_chart_stored_fit.py`, `test_trendline_fit_persistence.py` — go to
`tests/charts/`.

`tests/conftest.py` stays at `tests/` root so every subdirectory keeps inheriting
it.

`tests/admin/conftest.py` builds module names at runtime (`_RELOAD_MODULES`, fed
to `importlib.import_module`) — the one place in the repo a module path is
assembled rather than written, so no rewrite can see it. **It has already been
checked: every entry is `swingbot.admin.*`, none are `swingbot.core.*`**, so
neither this task nor the Phase 4 moves affect it. Leave it alone, and do not
re-derive this.

- [ ] **Step 3: Verify collection did not change**

```bash
python -m pytest tests/ --collect-only -q | tail -3
```

Expected: the same collected count as the Task 1 baseline's passed+skipped total.
**A lower number means a file stopped being collected** — the characteristic
symptom of a move that escaped `testpaths` or lost its `conftest.py`. Do not
proceed until the count matches.

- [ ] **Step 4: Run the suite**

```bash
python scripts/dev/testrun.py full
```

Expected: matches the Task 1 baseline exactly.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: group the suite to mirror the packages it exercises"
```

---

# Phase 4 — swingbot/core re-package

## Parallelisation

**Sequential throughout: Tasks 7 → 15.** Task 7 builds the tool the rest use.
Tasks 8–13 each rewrite imports across `swingbot/`, `tests/` and `scripts/`, so
every one of them touches `commands/scanning.py`, `admin/helpers.py` and `bot.py`
— overlapping files in a shared working tree, which is the exact case that
overwrites rather than merges. Do not dispatch these concurrently.

Order within 8–13 is deliberate: `infra/` first (leaf dependencies, smallest
blast radius, proves the tool), `market/` late (largest, 16 modules).

---

### Task 7: Build the one-shot move tool

Six near-identical package moves, each needing five distinct rewrite forms. Doing
that by hand six times is where this plan would go wrong.

**Files:**
- Create: `scripts/dev/_repackage.py` (deleted in Task 15)

- [ ] **Step 1: Write the tool**

```python
#!/usr/bin/env python3
"""One-shot helper for the v26 core re-package. Deleted by Task 15 of plan v27.

Moves one sub-package's modules under swingbot/core/<pkg>/ and rewrites every
reference to them across the repo.

    python scripts/dev/_repackage.py infra

Rewrites five distinct forms:
  1. from swingbot.core.MOD import X   -> from swingbot.core.PKG.MOD import X
  2. import swingbot.core.MOD [as A]   -> import swingbot.core.PKG.MOD [as A]
  3. "swingbot.core.MOD..." strings    -> "swingbot.core.PKG.MOD..."
  4. from swingbot.core import MOD     -> from swingbot.core.PKG import MOD
  5. from .MOD / from ..MOD relatives  -> absolute swingbot.core.PKG.MOD
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The COMPLETE final map. Every move needs the whole map, not just its own
# package: a module being moved may relatively-import a sibling that has not
# moved yet, and that import must be rewritten to the sibling's FINAL home.
_LAYOUT = {
    "marketdata": "data data_store data_refresh backtest_cache fmp_client "
                  "export_data ticker_directory ticker_utils universe watchlist",
    "market": "indicators candlestick_patterns fvg levels levels_lifecycle "
              "trendlines volatility market_context signals strategy "
              "strategy_types entry_filters reversal explain events market_events",
    "planning": "plan_engine plan_manager plan_store quality account",
    "backtesting": "backtest backtest_wf backtest_scenarios registry shadow_log",
    "tracking": "performance retrospective risk_metrics",
    "infra": "jsonio state notifier silent_channel",
}
MAP = {m: pkg for pkg, mods in _LAYOUT.items() for m in mods.split()}

SEARCH_ROOTS = ["swingbot", "tests", "scripts", "bot.py", "admin_ui.py"]


def source_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", *SEARCH_ROOTS],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / p for p in out.stdout.split() if p.endswith(".py")]


def rewrite(text: str) -> str:
    """Apply all five forms. Idempotent: re-running changes nothing."""

    # Forms 1-3: any dotted swingbot.core.MOD reference, in code or in a string.
    # MAP lookup means already-moved modules and never-moving packages
    # (charts, edge, scanning, analytics) are left alone.
    def _dotted(m: re.Match) -> str:
        mod = m.group(1)
        return f"swingbot.core.{MAP[mod]}.{mod}" if mod in MAP else m.group(0)

    text = re.sub(r"swingbot\.core\.([a-z_][a-z0-9_]*)\b", _dotted, text)

    # Form 4: the package-attribute import. Must split a comma list whose names
    # land in different packages.
    #
    # The parenthesised form `from swingbot.core import (\n  a,\n  b,\n)` does
    # not exist in the repo today. Guard rather than handle it: the regex below
    # excludes "(", so such a line would be SKIPPED SILENTLY and ship a broken
    # import. Fail loudly instead and hand-edit the one line.
    if re.search(r"^[ \t]*from swingbot\.core import \(", text, flags=re.M):
        raise SystemExit(
            "parenthesised 'from swingbot.core import (...)' found; "
            "rewrite it as a single line by hand, then re-run")

    def _pkg_attr(m: re.Match) -> str:
        indent, names = m.group(1), m.group(2)
        groups: dict[str, list[str]] = {}
        for spec in (n.strip() for n in names.split(",")):
            mod = spec.split()[0]              # "data as data_module" -> "data"
            groups.setdefault(MAP.get(mod, ""), []).append(spec)
        lines = []
        for pkg, specs in groups.items():
            target = f"swingbot.core.{pkg}" if pkg else "swingbot.core"
            lines.append(f"{indent}from {target} import {', '.join(specs)}")
        return "\n".join(lines)

    text = re.sub(r"^([ \t]*)from swingbot\.core import ([^\n(]+)$",
                  _pkg_attr, text, flags=re.M)

    # Form 5: relative imports, one dot (sibling) or two (parent), including
    # the `from .. import MOD` package-attribute variant.
    def _rel(m: re.Match) -> str:
        indent, mod = m.group(1), m.group(2)
        return (f"{indent}from swingbot.core.{MAP[mod]}.{mod} import"
                if mod in MAP else m.group(0))

    text = re.sub(r"^([ \t]*)from \.\.?([a-z_][a-z0-9_]*) import", _rel,
                  text, flags=re.M)

    def _rel_attr(m: re.Match) -> str:
        indent, mod = m.group(1), m.group(2)
        return (f"{indent}from swingbot.core.{MAP[mod]} import {mod}"
                if mod in MAP else m.group(0))

    text = re.sub(r"^([ \t]*)from \.\.? import ([a-z_][a-z0-9_]*)$", _rel_attr,
                  text, flags=re.M)
    return text


def main(pkg: str) -> None:
    if pkg not in _LAYOUT:
        raise SystemExit(f"unknown package {pkg!r}; expected one of {list(_LAYOUT)}")

    dest = ROOT / "swingbot" / "core" / pkg
    dest.mkdir(exist_ok=True)
    init = dest / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
        subprocess.run(["git", "add", str(init)], cwd=ROOT, check=True)

    moved = []
    for mod in _LAYOUT[pkg].split():
        src = ROOT / "swingbot" / "core" / f"{mod}.py"
        if not src.exists():
            print(f"  skip {mod}.py (already moved or absent)")
            continue
        subprocess.run(["git", "mv", str(src), str(dest / f"{mod}.py")],
                       cwd=ROOT, check=True)
        moved.append(mod)
    print(f"moved {len(moved)} modules into swingbot/core/{pkg}/")

    changed = 0
    for path in source_files():
        before = path.read_text(encoding="utf-8")
        after = rewrite(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed += 1
    print(f"rewrote references in {changed} files")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
```

- [ ] **Step 2: Prove the rewrite logic before trusting it on the repo**

Save as `tests/dev/test_repackage_rewrite.py`:

```python
"""Unit tests for the one-shot v27 re-package tool. Deleted with it in Task 15."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_repackage", Path(__file__).resolve().parents[2] / "scripts" / "dev" / "_repackage.py")
_repackage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repackage)
rewrite = _repackage.rewrite


def test_absolute_module_import():
    assert rewrite("from swingbot.core.jsonio import atomic_write_json") == \
        "from swingbot.core.infra.jsonio import atomic_write_json"


def test_string_literal_patch_target():
    assert rewrite('mock.patch("swingbot.core.data.fetch_ohlc")') == \
        'mock.patch("swingbot.core.marketdata.data.fetch_ohlc")'


def test_package_attribute_import_with_alias():
    assert rewrite("from swingbot.core import data as data_module") == \
        "from swingbot.core.marketdata import data as data_module"


def test_package_attribute_split_across_packages():
    out = rewrite("from swingbot.core import levels, jsonio")
    assert "from swingbot.core.market import levels" in out
    assert "from swingbot.core.infra import jsonio" in out


def test_sibling_relative_becomes_absolute():
    assert rewrite("from .indicators import atr") == \
        "from swingbot.core.market.indicators import atr"


def test_parent_relative_becomes_absolute():
    assert rewrite("from ..volatility import bollinger_bands") == \
        "from swingbot.core.market.volatility import bollinger_bands"


def test_parent_relative_package_attribute():
    assert rewrite("from .. import levels") == \
        "from swingbot.core.market import levels"


def test_indented_relative_import_keeps_indent():
    assert rewrite("        from ..indicators import atr as a") == \
        "        from swingbot.core.market.indicators import atr as a"


def test_non_moving_packages_untouched():
    for line in ("from swingbot.core.charts.trade_chart import render",
                 "from swingbot.core.edge.sizing import size_position",
                 "from swingbot.core.scanning.engine import run_scan"):
        assert rewrite(line) == line


def test_multiline_import_prefix_only():
    src = "from .plan_engine import (\n    build_strategy_plan,\n)"
    assert rewrite(src) == \
        "from swingbot.core.planning.plan_engine import (\n    build_strategy_plan,\n)"


def test_idempotent():
    once = rewrite("from swingbot.core.jsonio import atomic_write_json")
    assert rewrite(once) == once


def test_parenthesised_package_import_fails_loudly():
    """The one form the rewriter cannot see must abort, not pass through."""
    import pytest
    with pytest.raises(SystemExit, match="parenthesised"):
        rewrite("from swingbot.core import (\n    levels,\n    jsonio,\n)")
```

- [ ] **Step 3: Run the tool's tests**

```bash
python -m pytest tests/dev/test_repackage_rewrite.py -v
```

Expected: 12 passed. Fix the tool until they pass — **do not run it against the
repo until they do.**

- [ ] **Step 4: Commit**

```bash
git add scripts/dev/_repackage.py tests/dev/test_repackage_rewrite.py
git commit -m "chore: a tested one-shot tool for the core re-package"
```

Note: this commit changes the suite count by +12. Record the new number; it
becomes the baseline for Tasks 8–14, and Task 15 removes it again.

---

### Task 8: Move infra/

Smallest package, leaf dependencies — proves the tool on low stakes.

**Files:**
- Move: `jsonio.py`, `state.py`, `notifier.py`, `silent_channel.py` →
  `swingbot/core/infra/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py infra
```

Expected: `moved 4 modules into swingbot/core/infra/` and a nonzero rewrite count.

- [ ] **Step 2: Check the diff is only moves and import lines**

```bash
git status --short
git diff -- swingbot tests scripts bot.py admin_ui.py | grep -E '^[+-]' | grep -vE '^[+-]{3}' | grep -vE 'import|^[+-]\s*$' | head -20
```

Expected: no output from the last command. Any line shown is a non-import change
— a bug in the tool. Stop and investigate.

- [ ] **Step 3: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: compile clean; suite matches the Task 7 baseline.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(core): infra/ — json, locks and delivery channels"
```

---

### Task 9: Move marketdata/

**Files:**
- Move: `data.py`, `data_store.py`, `data_refresh.py`, `backtest_cache.py`,
  `fmp_client.py`, `export_data.py`, `ticker_directory.py`, `ticker_utils.py`,
  `universe.py`, `watchlist.py` → `swingbot/core/marketdata/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py marketdata
```

Expected: `moved 10 modules into swingbot/core/marketdata/`.

- [ ] **Step 2: Confirm the package-attribute imports resolved correctly**

This package contains `data.py`, the module whose name most nearly collided.

```bash
git grep -n 'from swingbot.core import data\b\|from swingbot.core import universe\b\|from swingbot.core import data_refresh\b'
```

Expected: no output — all should now read `from swingbot.core.marketdata import …`.

```bash
python -c "from swingbot.core.marketdata import data; print(data.__file__)"
```

Expected: prints the path to `swingbot/core/marketdata/data.py`, **not** a
package `__init__.py`. This is the check that the collision was actually avoided.

- [ ] **Step 3: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(core): marketdata/ — fetching and caching, both OHLCV caches together"
```

---

### Task 10: Move market/

The largest package, and the one `charts/` reaches into with the ten
parent-relative imports.

**Files:**
- Move: `indicators.py`, `candlestick_patterns.py`, `fvg.py`, `levels.py`,
  `levels_lifecycle.py`, `trendlines.py`, `volatility.py`, `market_context.py`,
  `signals.py`, `strategy.py`, `strategy_types.py`, `entry_filters.py`,
  `reversal.py`, `explain.py`, `events.py`, `market_events.py` →
  `swingbot/core/market/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py market
```

Expected: `moved 16 modules into swingbot/core/market/`.

- [ ] **Step 2: Verify the charts/ parent-relative imports were rewritten**

```bash
git grep -nE '^\s*from \.\.(fvg|indicators|strategy|volatility|trendlines|levels)\b' -- swingbot/core
git grep -nE '^\s*from \.\. import levels' -- swingbot/core
```

Expected: no output from either. These ten imports in
`charts/chart_geometry.py`, `charts/chart_volume_profile.py` and
`charts/trade_chart.py` are the ones that break silently if missed.

- [ ] **Step 3: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline. Chart tests are the ones to watch here.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(core): market/ — everything computed from bars"
```

---

### Task 11: Move planning/

**Files:**
- Move: `plan_engine.py`, `plan_manager.py`, `plan_store.py`, `quality.py`,
  `account.py` → `swingbot/core/planning/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py planning
```

Expected: `moved 5 modules into swingbot/core/planning/`.

`trade_plan.py` is **not** in this list — it is a shim, deleted in Task 14.

- [ ] **Step 2: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline. `plan_engine` is the most-imported module
in the repo (49 import sites), so this is the widest single rewrite.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(core): planning/ — plan construction, lifecycle and sizing"
```

---

### Task 12: Move backtesting/

**Files:**
- Move: `backtest.py`, `backtest_wf.py`, `backtest_scenarios.py`, `registry.py`,
  `shadow_log.py` → `swingbot/core/backtesting/`
- Move: `swingbot/core/validation_registry.json` → `swingbot/core/backtesting/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py backtesting
```

- [ ] **Step 2: Move the JSON the tool does not know about**

`registry.py:13` locates it as `Path(__file__).with_name("validation_registry.json")`
— coupled by directory adjacency, not by an import, so the tool cannot see it.

```bash
git mv swingbot/core/validation_registry.json swingbot/core/backtesting/
```

- [ ] **Step 3: Prove the registry still loads**

```bash
python -c "from swingbot.core.backtesting import registry; print(len(registry.load()))"
```

Expected: a nonzero count, not `FileNotFoundError`. If `load()` is not the
loader's name, check the module and use the real entry point — the point of this
step is to force the file read, which no import alone does.

- [ ] **Step 4: Verify backtest.py's six broken relative imports resolved**

```bash
git grep -nE '^\s*from \.(entry_filters|indicators|levels|plan_engine|strategy|strategy_types)\b' -- swingbot/core
```

Expected: no output.

- [ ] **Step 5: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(core): backtesting/ — offline replay, walk-forward and the validation registry"
```

---

### Task 13: Move tracking/

**Files:**
- Move: `performance.py`, `retrospective.py`, `risk_metrics.py` →
  `swingbot/core/tracking/`

- [ ] **Step 1: Run the tool**

```bash
python scripts/dev/_repackage.py tracking
```

Expected: `moved 3 modules into swingbot/core/tracking/`.

- [ ] **Step 2: Confirm swingbot/core is now flat-module-free**

```bash
git ls-files 'swingbot/core' | awk -F/ 'NF==3' | grep '\.py$'
```

Expected: exactly three files — `__init__.py`, `scan_engine.py`, `trade_plan.py`.
The latter two are the shims Task 14 deletes. Anything else is a module the
reconciliation in Task 1 missed; place it before continuing.

- [ ] **Step 3: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(core): tracking/ — the trade log's write path"
```

---

### Task 14: Delete the two shims

`scan_engine.py` re-exports `scanning/engine.py` and is still imported by eight
live call sites. `trade_plan.py` re-exports `plan_engine.build_strategy_plan`.

**Files:**
- Delete: `swingbot/core/scan_engine.py`, `swingbot/core/trade_plan.py`
- Modify: `swingbot/admin/app.py`, `swingbot/admin/helpers.py`,
  `swingbot/commands/{history,info,scanning,slash,trades}.py`, `bot.py`,
  `tests/test_trade_plan.py`

- [ ] **Step 1: Find every reference**

```bash
git grep -n 'scan_engine\|trade_plan' -- swingbot tests scripts bot.py admin_ui.py
```

- [ ] **Step 2: Rewrite the scan_engine call sites**

Two forms are in use. Named imports:

```python
# swingbot/admin/app.py
from swingbot.core.scanning.engine import is_scan_running
# swingbot/admin/helpers.py
from swingbot.core.scanning.engine import CONFIDENCE_COLORS
```

And module imports, in `commands/history.py`, `commands/info.py`,
`commands/scanning.py`, `commands/slash.py`, `commands/trades.py`:

```python
from swingbot.core.scanning import engine as scan_engine
```

Binding it back to the name `scan_engine` keeps every usage site
(`scan_engine.run_scan(...)`, `scan_engine.trade_log`, `scan_engine.get_regime()`)
unchanged. That is deliberate: this task removes a module, not a vocabulary, and
renaming ~15 usage sites in `commands/scanning.py` would bury the deletion in
noise.

- [ ] **Step 3: Rewrite the trade_plan call sites**

Only `tests/test_trade_plan.py` imports it in live code:

```python
from swingbot.core.planning.plan_engine import build_strategy_plan
```

Keep the test file and its assertions — it tests real behaviour that still
exists, and it moved to `tests/planning/` in Task 6.

- [ ] **Step 4: Delete the shims**

```bash
git rm swingbot/core/scan_engine.py swingbot/core/trade_plan.py
```

- [ ] **Step 5: Verify nothing still reaches for them**

```bash
git grep -n 'core\.scan_engine\|core import scan_engine\|core\.trade_plan\|core import trade_plan' -- swingbot tests scripts bot.py admin_ui.py
```

Expected: no output. Docstring mentions like `bot.py:24`'s file-map comment need
updating too — that line describes a file that no longer exists.

- [ ] **Step 6: Compile and test**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the Task 7 baseline.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(core): delete the two shims the carve-outs left behind"
```

---

### Task 15: Remove the tool and re-point the documentation

**Files:**
- Delete: `scripts/dev/_repackage.py`, `tests/dev/test_repackage_rewrite.py`,
  `docs/superpowers/plans/v27-baseline.md`
- Modify: `CLAUDE.md`, `docs/claude/architecture.md`, `docs/claude/known-traps.md`,
  `.claude/agents/symbol-verifier.md`, `.claude/skills/task-brief/SKILL.md`,
  `README.md`, `docs/features.md`

- [ ] **Step 1: Delete the throwaway tool and its tests**

```bash
git rm scripts/dev/_repackage.py tests/dev/test_repackage_rewrite.py docs/superpowers/plans/v27-baseline.md
rmdir tests/dev 2>/dev/null || true
```

This returns the suite count to the **Task 1** baseline. From here on, that is
the number again.

- [ ] **Step 2: Update the architecture and trap documents**

- `docs/claude/architecture.md` — the core module map is now six packages plus
  four; rewrite the map section.
- `docs/claude/known-traps.md` — the "two parallel OHLCV caches" entry should now
  say both live in `swingbot/core/marketdata/`, and the "legacy shims" entry
  should be replaced with a note that they were removed on 2026-08-15 by v27,
  so a future session does not go looking for them.
- `.claude/agents/symbol-verifier.md` and `.claude/skills/task-brief/SKILL.md`
  both cite `scan_engine`/`trade_plan` as known shims — remove those citations.

- [ ] **Step 3: Update CLAUDE.md**

The "Token discipline" section's Glob guidance (`Glob("swingbot/**/*.py")`) still
holds. What changes: the README is no longer 645 lines, so replace that bullet
with a pointer to the four `docs/` files, and add one line naming the six core
packages so a fresh session does not have to `ls` to find out.

- [ ] **Step 4: Check for dangling references repo-wide**

```bash
git grep -ohE 'swingbot/core/[a-z_]+\.py' -- . ':!docs/superpowers/plans/implemented' ':!docs/superpowers/specs/implemented' ':!docs/superpowers/results' \
  | sort -u | while read p; do [ -e "$p" ] || echo "DANGLING: $p"; done
```

Expected: no output.

- [ ] **Step 5: Confirm no relative imports remain across package boundaries**

```bash
git grep -nE '^\s*from \.\.' -- swingbot/core
```

Expected: no output. Same-package single-dot imports inside `analytics/`,
`charts/`, `edge/` and `scanning/` are fine and may remain.

- [ ] **Step 6: Full verification**

```bash
python -m compileall -q swingbot bot.py admin_ui.py scripts tests
python scripts/dev/testrun.py full
```

Expected: matches the **Task 1** baseline exactly (the +12 tool tests are gone).

- [ ] **Step 7: Bump the version**

`VERSION.json`: `bot` `1.1.2` → `1.1.3`, and set `bot_updated` to the current
timestamp in the file's existing `YYYY-MM-DD HH-MM-SS` format. Leave `ui`
untouched — the SPA was not modified.

- [ ] **Step 8: Close the spec and this plan**

```bash
git mv docs/superpowers/specs/2026-08-15-v26-repo-restructure-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-15-v27-repo-restructure.md docs/superpowers/plans/implemented/
```

Add a Progress block to the plan before moving it, recording the final test count
and anything deliberately left undone.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: close the v26 restructure — docs re-pointed, tool removed"
```

---

## Verification summary

| After task | Expected suite result |
|---|---|
| 1 | baseline recorded — call it **B** |
| 2, 3, 4, 5, 6 | exactly **B** |
| 7 | **B + 12** (the tool's own tests) |
| 8–14 | exactly **B + 12** |
| 15 | exactly **B** |

`0 failed` and `0 xfailed` at every step, without exception. A count that moves
in any other way means a test file stopped being collected — investigate rather
than accept it.
