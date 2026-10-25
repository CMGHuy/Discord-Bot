# v194 plan part 6 — content audit, docs mirror and release (V194-16, V194-16b, V194-17)

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
Constraints, standard close and parallelisation: see the index `2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md`. Every task runs in the v194 worktree; `WT` is its absolute path. This part runs last: V194-16 audits the copy written by V194-6b..15, V194-16b needs V194-3, V194-17 needs everything.

### Task V194-16: A4 content audit of every hint and chart tooltip

**Model:** opus — judgement task: each hint's claim must be traced to the code that computes the figure, and a wrong call ships a misleading number to a partner placing real orders.

**Files:**
- Modify: only the hint and chart-tooltip sites the audit marks `caveat added`, `fixed text` or `fixed figure`. Candidates: `frontend/src/app/ui/bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`, `histogram.ts`, `share-bar.ts`, `strip-plot.ts`, `waterfall.ts` (consumers of `chart-tooltip.ts`'s `HoverState`), `frontend/src/app/workspaces/analytics/tabs/*.ts` (attribution, edge, execution, override-fidelity-panel, overview, partials, pipeline, tuning, variance-band-panel), and the `dashboard`, `risk`, `trades`, `calendar`, `gallery`, `research`, `system`, `versions` workspaces. Name each touched file in the audit table.
- Modify (only for a `fixed figure` row): the producing function or endpoint helper plus its test; the row names both files.
- Create: `frontend/src/app/ui/hint-copy.spec.ts`.
- Modify: this plan file, appending `## A4 audit table` (the plan's final-task notes; V194-17 links it).

**Interfaces:**
- Consumes: `LEG_HINT_TEXT` (V194-12, `frontend/src/app/workspaces/trades/leg-label.ts`), `StatTile.about` (V194-11), `fx_missing_count` and `fxMissingText` (V194-6b/6c), `TITLE_ALLOW` (V194-14; a `title` kept as echo or control name is not a hint, out of scope), `HoverState` / `TooltipRow` (`frontend/src/app/ui/chart-tooltip.ts:4-5`).
- Produces: the audit table, columns `route | label | claim | computed by | verdict`, verdict one of `correct`, `caveat added`, `fixed text`, `fixed figure`. Nothing later consumes code from this task.

Scope: A4 covers the hints and tooltips not already fixed under B. B3 (legs), B4/B5 (share and risk formats), B6 (sectors), B7 (FX) and B8 (Sharpe / drawdown basis) were corrected by V194-6..13; the audit confirms their new copy and records those rows `correct`, it does not rewrite them.

- [ ] **Step 1: Enumerate every site.** One batch from the worktree; paste the three counts into the audit table header:

```bash
git -C "$WT" grep -nE "<sb-hint|\[about\]|about=|\[description\]|description=|\[hint\]|hint=" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' ':!frontend/src/app/testing/*'
git -C "$WT" grep -nE "hoverPosition|HoverState|TooltipRow|<sb-chart-tooltip" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'
git -C "$WT" grep -nE "HINT|_HELP|_TEXT\b|TOOLTIP" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'
```

  Every `sb-panel` heading with a `description` renders an `sb-hint` (index Traps), so panel descriptions are sites. A constant-text site (`LEG_HINT_TEXT`, a `*_HELP` map) is audited once, with every route that shows it listed in the `route` column.

- [ ] **Step 2: Record claim and code per site.** One row each: the route (and tab); the label; the claim in one clause (population, N, unit, window and cost basis it promises); `computed by` = the repo `path:line` of the function or API field producing the figure (store computed, selector, or `swingbot/...` endpoint helper). Open that code; never infer from the hint text. For chart tooltips the claim is the `title` and each `TooltipRow.label` the component builds, the code is the series the chart is fed.

- [ ] **Step 3: Check each row against the spec's five questions**, in this order:
  1. Population: all closed, range-scoped (Analytics range, calendar month) or the open book; plans versus legs (V194-12: win rate and N count plans).
  2. Sample size: the text names `N`, or the tile shows it beside the figure, wherever a rate, ExpR or average appears.
  3. Unit: R, %, shares, or money in `connection.currency()`. Money is in the account currency after `to_account_currency` (V194-6b); a hint saying `$`, "USD" or a hard-coded symbol is `fixed text`.
  4. Window: an "all-time" hint on a range-scoped figure, or "this range" on an all-time one, is `fixed text`.
  5. Basis: a performance figure's hint states paper (simulated fills), gross or net of commissions and slippage, and pre-tax. Establish gross or net from the producing code (grep `commission` / `slippage` there), never assume. A missing basis on an otherwise right figure is `caveat added`.

- [ ] **Step 4: Write the failing copy-rule test first.** Create `frontend/src/app/ui/hint-copy.spec.ts`. It guards the copy rules so the audit cannot silently regress; per-row cases read the touched file with `readFileSync` (the way `hint.spec.ts` regex-reads `hint.ts`):

```typescript
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { LEG_HINT_TEXT } from '../workspaces/trades/leg-label';

const FORBIDDEN = /\b(take (this|it)|safe(ly)?|buy now|you should)\b/i;

describe('hint copy rules (v194 A4)', () => {
  it('LEG_HINT_TEXT states that win rate and N count plans, not legs', () => {
    expect(LEG_HINT_TEXT).toMatch(/plan/i);
    expect(LEG_HINT_TEXT).toMatch(/win rate/i);
  });
  it('no hint text reads as a recommendation', () => {
    expect(LEG_HINT_TEXT).not.toMatch(FORBIDDEN);
  });
});
```

  Add one `it` per `fixed text` / `caveat added` row: `readFileSync` the file, locate the text and assert the load-bearing words of the new wording (the population word, `N`, `paper`, `gross` or `net`, `pre-tax`) plus `not.toMatch(FORBIDDEN)`. Run `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/hint-copy.spec.ts`: the per-row cases FAIL on the old copy. With zero fixes the file keeps the two cases above and Step 5 is skipped.

- [ ] **Step 5: Fix.** `fixed text` / `caveat added`: edit the string in place under the copy rules (a win-rate hint names ExpR and N beside it; no recommendation words; a performance figure says paper, gross or net, pre-tax). Tile hints use `about` on `sb-stat-tile`, never `title`. `fixed figure` is a number bug: write the failing test against the producing function first (frontend spec, or `tests/admin/test_api_v1_*.py` with a narrow `testrun.py file` run), then correct it, keeping each function under complexity 15. A row that cannot be settled from the code is a spec gap: leave the text, mark the row `correct` only if it is, otherwise report it in the final handback's OPEN list; never guess.

- [ ] **Step 6: Chart tooltips.** For each `chart-tooltip` consumer confirm in its spec that `HoverState.title` and the row labels carry the unit, and that a money value goes through the shared formatter in `frontend/src/app/ui/format.ts` with `connection.currency()`, not a literal `$`. Add one assertion per consumer whose tooltip was `fixed text`.

- [ ] **Step 7: Append the audit table** to this plan file under `## A4 audit table`: a header line with the Step 1 counts, then one row per hint (`| route | label | claim | computed by | verdict |`), verdicts only from the four words, B-row confirmations included. Do not paste the table elsewhere.

- [ ] **Step 8: Close.** Touched specs narrow, then the whole frontend run and `npm --prefix "$WT/frontend" run lint`. Frontend and backend fixes are separate commits; the last commit body carries the verdict counts (`N correct, N caveat added, N fixed text, N fixed figure`).

Close: standard (test: frontend/src/app/ui/hint-copy.spec.ts) — deviations: the commit body states the verdict counts; a `fixed figure` row touching `swingbot/` runs its own `.py` test narrow; the table lands in a separate `docs(v194): A4 audit table (V194-16)` commit.

### Task V194-16b: ui-design.md names the layout audit's `hint` check; AGENTS.md mirror

**Model:** haiku — two prose edits with a fixed sentence and a drift test that says whether they match.

**Files:**
- Modify: `docs/claude/ui-design.md:55` (the Checklist bullet beginning "Before merging any UI change, run the layout audit", the sentence listing the checks, which ends `... off centre, on every route and tab.`)
- Modify: `AGENTS.md:214-220` (the `ui-design.md` bullet, ending `must exit 0 (allow-list entries carry a reason and a date).`)
- Test: `tests/hooks/test_codex_mirror.py` (existing drift test; no new test)

**Interfaces:**
- Consumes: `hintVerdict`, `CHECKS` (V194-3: `hint` is the eighth check).
- Produces: nothing.

- [ ] **Step 1: Edit `docs/claude/ui-design.md`.** In the Checklist's layout-audit bullet, change the end of the check list from `offsets over 2px, and (`vcenter`) table-cell content or an icon more than 2px off centre, on every route and tab.` to the same text followed by:

```
 and (`hint`) every visible `sb-hint` trigger: hovered at 1440, tapped at
  390 and 768, its popover must sit inside the viewport and be the topmost
  element at its centre and its top-left + 8px. A `hint` finding is fixed,
  never allowed. Hints use `sb-hint`, never a native `title` for an
  explanation (`TITLE_ALLOW` in `frontend/src/app/ui/title-usage.allow.ts`
  lists the few echo and control-name titles; v194).
```

  Read the lines first with `sed -n 50,62p docs/claude/ui-design.md` so the replacement keeps the bullet's indentation; the sentence ends with one full stop.

- [ ] **Step 2: Edit `AGENTS.md`** (condensed mirror). In the `ui-design.md` bullet replace `must\n  exit 0 (allow-list entries carry a reason and a date).` with `must\n  exit 0, including its `hint` check (every `sb-hint` popover opens inside the viewport and on top; hints are `sb-hint`, not native `title`); allow-list entries carry a reason and a date.` Keep the two-space continuation indent.

- [ ] **Step 3: Run the drift test.** `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` → green. Also `wc -l CLAUDE.md` is unchanged (this task does not touch it; the file stays under 200 lines).

Close: standard (test: tests/hooks/test_codex_mirror.py) — deviations: no frontend run, no complexity-gate change expected (still run it); commit type `docs`, both files in one commit (CLAUDE.md rule: the `AGENTS.md` mirror ships with the `docs/claude/` edit).

### Task V194-17: Full suite, replica layout audit, merge to main, post-deploy record

**Model:** haiku — runs fixed commands and records results; no design decisions.

**Files:**
- Modify: this plan file (append `## Results`, below).
- No source files.

**Interfaces:**
- Consumes: `hintVerdict`, `CHECKS` (V194-3, run by `layout-audit.mjs`).
- Produces: the `## Results` block.

- [ ] **Step 1: Worktree check.** `git rev-parse --show-toplevel` prints the v194 worktree; `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing written by this plan. `git -C "$WT" status --short` is clean (every earlier task committed).

- [ ] **Step 2: Full suite, once.** Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full` in the worktree (it also runs the complexity gate). Expected: `0 failed`, `0 xfailed`; record the pass count. A failure is fixed and re-run alone (`testrun.py file ...`), never by re-running the whole suite. Then `npm --prefix "$WT/frontend" test -- --watch=false`, `npm --prefix "$WT/frontend" run lint` and `node --test "$WT/frontend/scripts/layout-audit-lib.test.mjs"` all green.

- [ ] **Step 3: Build the replica.** `/replicate-prod-db` into the shared `swing-db` container (once; skip if V194-4 already ran it today). Build the bundle fresh, never reuse an old one (stale-bundle trap): `npm --prefix "$WT/frontend" run build`. Start `python admin_ui.py` from the worktree on port 1234 with the replica's `.env` values (load `ADMIN_USERNAME`/`ADMIN_PASSWORD` inside the script; never print them), then sign in once: `node "$WT/frontend/scripts/browse.mjs" login --base http://localhost:1234`.

- [ ] **Step 4: Layout audit at all three widths.** `node "$WT/frontend/scripts/layout-audit.mjs" --base http://localhost:1234` → exit 0 at 390, 768 and 1440, `hint` included (eight checks in the summary). A `hint` finding is fixed in the owning component (new failing case in `hint.spec.ts` or `hintVerdict`'s test first) and the audit re-run; it is never added to `layout-audit.allow.json`. Record the finding count per width and any `STALE` allow entries (`--prune` only if the list is non-empty, as a separate commit).

- [ ] **Step 5: Merge to main.** Check first: `git worktree list` and `git -C E:/Documents/Private/Projects/Discord-Bot log -3 --oneline`; if another session has touched `main` since V194-1, pause and ask the partner (concurrent-session rule). Then fast-forward or merge the branch `2026-10-25-v194-ui-tooltips-and-data-truth` into `main` from the main tree. **No full suite after the merge** (it ran in Step 2). Do not push or deploy; do not run `/close-out` here, the controller does.

- [ ] **Step 6: Post-deploy check (recorded, run after the partner deploys).** Not run by this task if production is not yet deployed: write `post-deploy: pending` in the Results. When deployed: `node frontend/scripts/layout-audit.mjs --base https://bomeo-capital.com`, driven by Playwright, logging in from `.env` inside the script, at 390, 768 and 1440; expected 0 `hint` findings. Production stays read-only.

- [ ] **Step 7: Append `## Results` to this plan file** and commit it (`docs(v194): results (V194-17)`):

```
## Results
- Full suite: <N passed>, 0 failed, 0 xfailed (<date>)
- Frontend: <N passed>; lint clean; layout-audit-lib.test.mjs <N> passed
- Replica layout audit: 390 <n> findings, 768 <n>, 1440 <n> (hint check included)
- A4 audit table: <link to ## A4 audit table>; verdict counts <...>
- A3 title sites measured by V194-14: <count>
- Merged to main: <sha>
- Post-deploy hint check: <0 findings at 390/768/1440 | pending>
```

Close: standard (test: frontend/scripts/layout-audit-lib.test.mjs) — deviations: this task is the plan's one full-suite run; step 2 of the standard close is replaced by Steps 2-4 above, and the merge (Step 5) replaces nothing in the commit shape.
