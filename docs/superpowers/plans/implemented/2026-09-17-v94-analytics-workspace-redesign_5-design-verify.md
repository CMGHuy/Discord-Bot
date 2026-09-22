# Analytics Workspace Redesign (v94) — Part 5: Design pass, docs, verification, release

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Header, constraints and prerequisite in `_0-index.md`. **Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` §3.12, §6.

# Phase 5 — Make it look like one instrument, then prove it

## Parallelisation (this phase)

**Sequential throughout.** V1 touches every tab file; V2 screenshots what V1 produced; V3 documents what V2 confirmed; V4 verifies and releases all of it.

## Exit criteria

Six tabs read as one system in light and dark; `python scripts/dev/testrun.py full` and `cd frontend && npm test` each green once; `docs/features/features-admin.md` describes the workspace that now exists; `VERSION.json` bumped and `version_history.json` regenerated.

---

### Task V1: Design pass

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/*.ts` (styles only), `frontend/src/app/workspaces/analytics/scope-bar.ts`, `frontend/src/app/ui/panel-header.ts`, and `frontend/src/styles/tokens.css` **only** if a token is genuinely missing (a new token is a last resort; prefer composing the existing scale).

**Interfaces:** none — this task changes no bindings, no inputs, no payloads. If a change here requires a template restructure, it belongs in the tab's own task, not this one.

- [ ] **Step 1: Load the design skill**

Invoke `frontend-design`. It is the authority for this task; the checklist below is what it must be applied *to*, not a substitute for it.

- [ ] **Step 2: Apply the pass, tab by tab**

For each of the six tabs, in order, with the app running (`cd frontend && npm start`, or the Docker stack per `docs/deploy/DOCKER.md`):

1. **Chrome recedes.** Panel borders are hairline `--border`; grids and axes are `--border`/`--border-strong`, never dashed except the deliberate floor and reference lines; no panel has both a border and a background shift.
2. **One type hierarchy.** `--text-hero` appears at most once per tab (the leading figure); `--text-metric` for KPI values; `--text-subhead` for panel titles; `--text-table` for body; `--text-micro` for axis ticks and N. Nothing invents a size.
3. **Rhythm.** `--section-gap` between panel groups, `--space-14` inside a panel, `--space-8` between a label and its value. A tab scrolls in even bands, not in a ragged column.
4. **Marks stay thin.** 2px lines, 4px rounded data-ends anchored to the baseline, ≥8px markers, a 2px surface gap between adjacent fills. No thick saturated blocks.
5. **Text wears text tokens.** No value, label or legend text is painted in a series colour; a coloured mark beside it carries the identity.
6. **Status colours stay reserved.** `--pos`/`--neg` mean gain/loss and `--warn` means a caveat; none of them is ever "series 4".

- [ ] **Step 3: Check both themes**

Toggle the theme (the app's own control; `grep -n "data-theme" frontend/src/app -r --include=*.ts | head`). For each tab in each theme: no text below the contrast the rest of the app holds, no chart surface that disappears into the page, no `color-mix` step that collapses to the background. Fix in the component's styles, not by hard-coding a hex.

- [ ] **Step 4: Re-run the palette validator** (P10's command) if any `--chart-*` token moved. Any FAIL reverts the change.

- [ ] **Step 5: Verify nothing broke**

```bash
cd frontend && npm test -- --include src/app/workspaces/analytics/tabs/overview.spec.ts
```

and the other five specs individually. A style-only pass must leave every spec green without edits; a spec that needed editing means the pass changed structure, which belongs in that tab's task.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/analytics frontend/src/app/ui/panel-header.ts frontend/src/styles/tokens.css
git commit -m "style(v94): one visual system across the six analytics tabs, light and dark"
```

---

### Task V2: Screenshot pass, six tabs × two themes

**Files:** none committed — screenshots are evidence, written to the scratchpad directory, not the repo.

- [ ] **Step 1: Get a browser driver working**

Three MCP servers that could drive this were failing to connect on 2026-09-17 (`chrome-devtools`, `playwright`, plus `ide`). Retry them first (they re-attempt every 15 minutes, or edit the plugin config to retry now). **If none connects, do not skip this task** — fall back, in order:

1. `claude-in-chrome` skill, if this session has it.
2. `npx playwright screenshot --viewport-size=1440,900 "http://localhost:4200/analytics?tab=overview" <out>.png` from the `frontend/` directory (Playwright is not a repo dependency; use `npx --yes`, and do not add it to `package.json`).
3. Manual: ask the human partner for six screenshots per theme.

Never claim this task done from a rendered spec snapshot — a vitest DOM is not the app.

- [ ] **Step 2: Capture twelve shots**

For each `tab` in `overview attribution execution edge pipeline tuning`, in each theme, with a scope that has data (`?from=` covering a month with closed trades):

```
<scratchpad>/v94-<tab>-<theme>.png
```

- [ ] **Step 3: Read each shot against the spec's success criteria**

For each: does every panel show its N or an all-time badge? Is the bar's N equal to each scoped panel's N? Is any cell under the floor showing a rate? Does any metric appear twice on one tab outside a hover or Table view? Are rolling win rate, rolling ExpR, cumulative-R multiples and SPY (in `%`) actually on screen?

- [ ] **Step 4: Fix what the shots show**

Anything wrong here is a defect in the tab that owns it. Fix it in that file, re-run that file's spec, commit as `fix(v94): <what the screenshot showed>`. Re-capture the affected shot.

- [ ] **Step 5: Report**

Post a short list to the human partner: one line per tab per theme, plus every defect found and fixed. No commit if nothing needed fixing.

---

### Task V3: Documentation

**Files:**
- Modify: `docs/features/features-admin.md` (§"Analytics core" L7–40, §SPA/IA L62–75)
- Modify: `docs/commands.md` **only** if a Discord command's output changed (it did not — this plan is admin-only; confirm with `git diff --stat main...HEAD -- swingbot/bot swingbot/core/presentation` returning nothing)
- Modify: `.codex/AGENTS.md` **only** if a convention changed (it did not; skip unless the executing session changed one)

- [ ] **Step 1: Update the analytics-core table** — add the one new module:

```markdown
| `scope.py` | `BookScope` — the one filter (date range, ledger, strategy, horizon, direction) every `/analytics/*` route parses, applies and echoes, so one query string means one population everywhere. |
```

and extend `aggregate.py`'s row to say the dimension count is 10 with `ledger` (v93).

- [ ] **Step 2: Rewrite the SPA/IA paragraph** for the six tabs. Keep it to one short paragraph plus the table:

```markdown
**The Analytics workspace is six tabs, in the order a trader asks** (spec
v94): **Overview** (am I making money), **Attribution** (where does it come
from), **Execution** (am I executing well), **Edge** (is the edge holding,
is the model calibrated), **Pipeline** (what is coming), **Tuning**
(operations). One control bar under the tab strip scopes every panel —
range, ledger, strategy, horizon, direction, plus an R/%/currency unit
toggle — and reports the closed-trade count it produced. Panels that are
all-time by design (calibration, the strategy registry, the plan funnel)
say so with a badge rather than pretending to be scoped. A cell with fewer
than `MIN_CELL_N` closed trades never shows a rate: the server sends null
and the cell renders blank with its N.
```

- [ ] **Step 3: Note the snapshot's narrowed role** — after the `data/analytics_snapshot.json` paragraph, one sentence: "The Analytics workspace no longer reads it (v94); it serves the Dashboard and Discord, where an all-time pre-built blob is the right artefact."

- [ ] **Step 4: Verify** — `grep -n "heatmap\|five tabs\|Performance tab" docs/features/features-admin.md` returns nothing stale.

- [ ] **Step 5: Commit**

```bash
git add docs/features/features-admin.md
git commit -m "docs(v94): six-tab analytics workspace, BookScope, and the snapshot's narrowed role"
```

---

### Task V4: Full-suite verification, release, close-out

- [ ] **Step 1: Run each suite once, over everything this plan implemented**

```bash
python scripts/dev/testrun.py full
```

(or dispatch the `test-runner` subagent so ~1150 lines stay out of context). Expect `0 failed`, `0 xfailed`.

```bash
cd frontend && npm test
```

Expect green. **If either is not green, fix forward from those failures** — they are this plan's regressions, and the task is not done until both runs are. Do not re-litigate earlier tasks.

- [ ] **Step 2: Merge the branch**

Follow `superpowers:finishing-a-development-branch`. **Before deleting anything, re-read `docs/claude/git-safety.md`** — no branch with `backup` in its name, and no `stable-*` branch, is ever deleted. **Check for concurrent sessions first** (`git log --oneline -5 main`, `git worktree list`): if another session has been committing to `main` or to a shared branch, pause and confirm with the human partner before merging.

**After a conflict-free merge, do not re-run either suite** (`docs/claude/document-conventions.md`). If the merge resolved conflicts, that resolution is new code: run both once more.

- [ ] **Step 3: Resolve the version numbers — from disk, not from this plan**

```bash
cat VERSION.json
```

Increment `ui` at the **minor** level and `bot` at the **patch** level (`Bump: ui minor · bot patch`), set each line's `*_updated` to now in `YYYY-MM-DD HH-MM-SS`, leave nothing else touched. The spec's header stamp (`ui 1.18.3 · bot 1.9.2`) records what this was *written against* and is never a target.

If the realised impact came out smaller than `ui minor` — it should not, six tabs is the canonical "someone who used this yesterday has to look at it anew" — amend the spec's `Bump:` line in this commit with one clause saying why.

```bash
git add VERSION.json
git commit -m "release(ui,bot): <ui> / <bot> -- Analytics workspace redesign: six tabs, one scope, honest charts"
```

- [ ] **Step 4: Regenerate the version history — with the bump already committed**

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(ui,bot): regenerate version_history.json for <ui> / <bot> -- Analytics workspace redesign"
```

The generator walks `git log` for `VERSION.json`; running it before the bump commit records the placeholder `"commit": "uncommitted"`. Order is bump commit → regenerate → commit the artifact.

- [ ] **Step 5: Close the documents out**

Per `docs/claude/document-lifecycle.md`:

```bash
git mv docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_0-index.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_1-backend-scope.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_2-primitives.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_3-shell-store.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_4-tabs.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_5-design-verify.md docs/superpowers/plans/implemented/
git commit -m "docs(v94): close out the Analytics workspace redesign"
```

Remove the worktree if one was used (`git worktree remove`, then `git worktree prune`).

- [ ] **Step 6: Deploy and mirror**

Deploying is the human partner's call. If they ask for it, follow `docs/deploy/DEPLOY_HETZNER.md`. **Anything fixed live on production must be mirrored back into this repo and committed before this task is done** (`CLAUDE.md`).

- [ ] **Step 7: Report against the spec's success criteria**

State, one line each, with evidence:

- Every scoped panel's N equals the bar's N (V2's screenshots).
- No metric appears twice on a tab outside a hover or Table view.
- No cell with `n < 20` shows a rate anywhere (B4/B5 tests plus V2).
- Rolling win rate, rolling ExpR, cumulative R per strategy and SPY are visible for the first time.
- A killed endpoint produces a Retry surface (kill the admin container, reload one tab, screenshot).
- Both suites green once; palette validator passes both themes.
