# v194 — UI integrity: tooltips that open, figures that are true: Part 6 — content audit and release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, Standard task close, Parallelisation and the task ledger live there; every task below inherits them.

Tasks: V194-16 (A4 content audit), V194-16b (A2 docs), V194-17 (verification and merge). All three run after every task in parts 1–5 is merged into the v194 worktree branch: V194-16 audits the hint texts that V194-11, V194-11b, V194-12b, V194-13, V194-14b, V194-15 and V194-15b created, and V194-17 is the plan's one full-suite run. `$WT` is the absolute path of `.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth`.

# Phase 6 — content audit and release

### Task V194-16: A4 content audit — every `sb-hint` text and chart tooltip against the code that computes it

**Model:** opus — each row needs a judgement across frontend and backend code (which population, which unit, gross or net) and a decision on which side is wrong; a wrong `correct` verdict ships a false definition the partner trades on.

**Spec:** A4. Known findings B7 (money in the account currency) and B8 (Sharpe / drawdown basis) were fixed under B (V194-6..6c, V194-10..11b); their hints still get a row here, verdict taken from their state now.

**Files:**
- Modify: only the sites whose row verdict is `caveat added`, `fixed text` or `fixed figure`, each named in its row's `Fix` cell. Candidates (Step 1 enumerates them exactly):
  - hint text sources: `frontend/src/app/workspaces/dashboard/panels/panel-help.ts` (`PANEL_HELP`), every `sb-panel` `description`, every `sb-panel-header` `hint`, every `sb-stat-tile` `about` / `KpiTile.about`, every direct `<sb-hint text=…>` (including the ones V194-14b, V194-15 and V194-15b converted from `title`), `LEG_HINT_TEXT` (`frontend/src/app/workspaces/trades/leg-label.ts`), the `RISK_*_ABOUT` / `ANALYTICS_*_ABOUT` constants, `fxMissingText` (`frontend/src/app/workspaces/analytics/scope-bar.ts`), and the gallery's demo hint (`frontend/src/app/workspaces/gallery/gallery.ts:286`);
  - chart tooltips: the primitives `frontend/src/app/ui/bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`, `histogram.ts`, `share-bar.ts`, `strip-plot.ts`, `waterfall.ts` (their `show()` builds `HoverState.title` / `rows`) and every workspace template that renders one of them (`analytics/tabs/*.ts` and others Step 1 finds), which supplies the labels, `yLabel`, `unit` and `format`.
  - a backend file only for a `fixed figure` row whose computation is server-side (separate commit).
- Modify: `docs/superpowers/plans/2026-10-25-v194-ui-tooltips-and-data-truth_6-content-audit-and-release.md` (the worktree copy): fill `#### A4 audit record` under V194-17.
- Test: the `.spec.ts` beside each changed frontend file (existing ones: e.g. `frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts`; create `<file>.spec.ts` beside a changed file that has none); `tests/admin/test_api_v1_<endpoint>.py` for a server-side figure fix.

**Interfaces:**
- Consumes: `LEG_HINT_TEXT` (V194-12b); `StatTile.about` (V194-11); `fx_missing_count` (V194-6b / V194-6c); `TITLE_ALLOW` (V194-14, `frontend/src/app/ui/title-usage.allow.ts`: the `title` sites left after A3 are `echo` / `control-name`, so they are not A4 sites); `PERFORMANCE_CAVEAT` (exported by V194-11 from `frontend/src/app/ui/stat-tile.ts`: `'Paper trades (simulated fills), gross of commissions and slippage, pre-tax.'`) as the one wording of the performance caveat; `Hint.text` / `Hint.label` (signal inputs, `frontend/src/app/ui/hint.ts:130,132`).
- Produces: the A4 audit table (in V194-17's notes). No new exported name. A fix that needs one (for example a new input on a chart primitive) is outside the ledger: stop and report that row to the controller instead of adding it.

**What is a site.**
- *Hint site:* one (route, visible label) pair whose `sb-hint` popover shows a text. A text reaches `Hint.text` only through a forwarder: `<sb-hint>` itself, `sb-panel`'s `description` (`frontend/src/app/ui/layout.ts:52`), `sb-panel-header`'s `hint` (`frontend/src/app/ui/panel-header.ts:17`), `sb-stat-tile`'s `about` (V194-11), plus any forwarder Step 1's first command prints that is not in this list. A constant used on two routes is two rows (the population can differ per route). **Not sites:** `sb-stat-tile`'s `hint` and `sb-empty-state`'s `hint` (plain visible text, no popover), the native `title` sites in `TITLE_ALLOW`, the dashboard's lifecycle `?` hint only if it states no figure (it still gets a row; verdict `correct` with "no figure" in the claim cell when that is so).
- *Chart tooltip site:* one chart element in a workspace template (route, chart title). Its claim is the tooltip title plus every row label and unit the primitive's `show()` prints for that consumer's data.

- [ ] **Step 1: Enumerate every site into an inventory (throwaway, gitignored)**

```bash
OUT="$WT/.superpowers/v194-a4-inventory.txt"; mkdir -p "$WT/.superpowers"
# forwarders: every component template that renders an sb-hint, and what it passes
git -C "$WT" grep -n -A3 "<sb-hint" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' > "$OUT"
# sb-panel descriptions (template bindings and config-object keys)
git -C "$WT" grep -n -E "description=\"|\[description\]=\"|description:" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' >> "$OUT"
# sb-panel-header hints (drop the sb-stat-tile / sb-empty-state lines: plain text, not sites)
git -C "$WT" grep -n -E "(^|\s)hint=\"|\[hint\]=\"" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' >> "$OUT"
# stat-tile and KPI about texts
git -C "$WT" grep -n -E "about=\"|\[about\]=\"|about:" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' >> "$OUT"
# shared hint constants and where each is used
git -C "$WT" grep -n -E "PANEL_HELP|LEG_HINT_TEXT|PERFORMANCE_CAVEAT|_ABOUT\b|fxMissingText" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' >> "$OUT"
# chart tooltips: the consumer set must still be exactly the seven primitives plus the gallery
git -C "$WT" grep -l "sb-chart-tooltip" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'
# every workspace use of a tooltip-bearing chart (gallery included: it is a route)
git -C "$WT" grep -n -E "<sb-(bar-list|dot-plot|heat-grid|histogram|share-bar|strip-plot|waterfall)\b" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts' >> "$OUT"
# each primitive's tooltip text (title / rows)
git -C "$WT" grep -n -o -E "title: ?[^,]+,rows: ?\[[^]]*\]|title: [^,]+, rows: \[[^]]*\]" -- frontend/src/app/ui/bar-list.ts frontend/src/app/ui/dot-plot.ts frontend/src/app/ui/heat-grid.ts frontend/src/app/ui/histogram.ts frontend/src/app/ui/share-bar.ts frontend/src/app/ui/strip-plot.ts frontend/src/app/ui/waterfall.ts
wc -l < "$OUT"
```

Expected: the `sb-chart-tooltip` list is `bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`, `histogram.ts`, `share-bar.ts`, `strip-plot.ts`, `waterfall.ts`, `chart-tooltip.ts`, `gallery.ts`. A new file in that list is a new primitive: add its selector to the `<sb-(…)` regex and re-run. A primitive whose `show()` the last command does not print (multi-line object) is read by hand at its `hover.set(` line (`git -C "$WT" grep -n "hover.set(" -- frontend/src/app/ui`). If the `about` command prints no `sb-stat-tile` site, or `LEG_HINT_TEXT` has no use outside `leg-label.ts`, parts 4–5 are not merged into this branch: stop and report.

Map each file to its route with `ROUTES` in `frontend/scripts/layout-audit-lib.mjs` (`git -C "$WT" grep -n "path:" -- frontend/scripts/layout-audit-lib.mjs`); a `ui/` primitive's text belongs to every route that renders it (find the users with `git -C "$WT" grep -n "<sb-<selector>"`).

- [ ] **Step 2: Mechanical pre-scan of the copy rules**

```bash
FILES=$(cut -d: -f1 "$WT/.superpowers/v194-a4-inventory.txt" | grep "^frontend/" | sort -u)
# recommendation words, scope words, cost words, currency words: each hit is checked by hand in Step 3
git -C "$WT" grep -n -i -E "\b(take|safe|buy|all-time|all time|since inception|lifetime|after costs|net of|USD|dollars?)\b" -- $FILES
# win-rate claims: each must name ExpR and N in the same hint text
git -C "$WT" grep -n -i -E "win rate|win-rate|winrate|hit rate" -- $FILES
```

Every hit is a row to look at first; a hit is not a verdict on its own (for example "take profit" names an exit, not a recommendation).

- [ ] **Step 3: Trace each site's figure and judge it**

For each site, in this order, writing the evidence (file:line) as you go:

1. **Label** — the visible text beside the trigger (`label` input minus `About `, the panel title, the tile label, the chart title).
2. **Claim** — the hint text, or the tooltip title and row labels, verbatim (shortened in the table only).
3. **Figure** — the template expression that renders the number the hint explains → its store `computed` (`git -C "$WT" grep -n "<signal name>" -- frontend/src/app/stores frontend/src/app/workspaces`) → the `ApiClient` method and endpoint (`git -C "$WT" grep -n "<method>" -- frontend/src/app/api/api-client.ts`) → the backend handler and the function that computes the value (`git -C "$WT" grep -n "<response field>" -- swingbot/admin/api_v1 swingbot/core`). A figure computed in the browser stops at the store.
4. **The five checks** (spec A4), each answered from that code:
   - *Population:* which rows the computation iterates — all closed, range-scoped, or the open book; plans or legs (rows built by `_row_from_leg` in `swingbot/admin/api_v1/trades.py` are legs).
   - *Sample size:* any N the text names is the length of that same population (a hint saying "trades" over a leg count is wrong).
   - *Unit:* R, %, or money. Money must reach the browser through `to_account_currency` (`swingbot/admin/api_v1/money.py`, V194-6b) and show `connection.currency()`'s symbol; a hint that says `$`, "USD" or "dollars" for an account-currency figure is wrong unless it names the account currency generically.
   - *Scope:* "all-time" / "since inception" / "lifetime" on a range-scoped figure, or "this period" / "selected range" on an all-time figure, is wrong.
   - *Basis:* a performance figure (P&L, return, win rate, ExpR, Sharpe, drawdown, equity) states paper (simulated fills), gross or net of commissions and slippage, and pre-tax. Gross unless the computing path subtracts costs: `git -C "$WT" grep -n -i -E "commission|slippage|fee" -- <the computing file>`.
   - Plus the index's copy rules: a win-rate hint names ExpR and N beside it; no hint reads as a recommendation.
5. **Verdict** — `correct` (all checks pass) / `caveat added` (figure right, a population, N or cost caveat missing) / `fixed text` (the text claims something the code does not do; the code is the intended definition) / `fixed figure` (the code disagrees with the documented intent: the spec, a plan, the backend docstring or the column definition; cite which).

A `fixed figure` candidate whose computing function has callers outside `swingbot/admin/` and `frontend/` (`git -C "$WT" grep -n "<function>(" -- swingbot ':!swingbot/admin'`) feeds signals, gates, sizing or badges (this plan is `Edge: none (integrity)`): do not change it; record `fixed text` (make the hint true to the code) and add the row to the report as `OPEN`. A row where the intended definition cannot be told from the code and documents: stop and report it to the controller (it asks the partner); do not guess.

- [ ] **Step 4: Write the audit record**

Fill `#### A4 audit record` under V194-17 in this part file (the worktree copy) with one row per site, numbered, grouped by route in `ROUTES` order, chart tooltips after hints on each route:

```markdown
| # | Route | Label | Site | Claim (short) | Figure computed by | Verdict | Fix |
|---|---|---|---|---|---|---|---|
| 1 | /dashboard | Trading performance | `workspaces/dashboard/panels/panel-help.ts:10` | paper account, selected period, simulated, before tax and costs | `stores/dashboard.store.ts:<n>` ← `swingbot/admin/api_v1/dashboard.py:<n>` | correct | — |
| 2 | /analytics?tab=edge | Expectancy by strategy (tooltip) | `ui/dot-plot.ts:6` via `analytics/tabs/edge.ts:<n>` | value = ExpR, "trades" = n | `stores/analytics.store.ts:<n>` ← `swingbot/admin/api_v1/analytics.py:<n>` | fixed text | `edge.ts:<n>` yLabel `'ExpR (R)'`; test `edge.spec.ts` `'…'` |
```

(The two rows show the format only; their verdicts come from Step 3.) `Site` and `Figure computed by` are repo paths relative to `frontend/src/app/` or the repo root, with line numbers from the worktree at audit time. `Fix` names the changed file:line and the test name, or `—`. A B7 / B8 row ends its `Fix` cell with `(B7, V194-6c)` or `(B8, V194-11)`. Close the table with one line: `Sites: <n> hint, <m> chart tooltip; verdicts: <a> correct, <b> caveat added, <c> fixed text, <d> fixed figure.` and check that `<n> + <m>` equals the number of numbered rows (`grep -c "^| [0-9]" <part file>` inside the record).

- [ ] **Step 5: Write the failing test for each non-`correct` row (one pattern per verdict)**

Shared helper, defined locally at the top of each `.spec.ts` that tests a rendered hint (it is not exported; two copies in two specs are fine, a shared testing file would be a ledger change):

```ts
import { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { Hint } from '<relative path>/ui/hint';

/** The text of the sb-hint whose aria label is `label` (A4 audit). */
function hintText(fixture: ComponentFixture<unknown>, label: string): string {
  const hint = fixture.debugElement
    .queryAll(By.directive(Hint))
    .map((debug) => debug.componentInstance as Hint)
    .find((h) => h.label() === label);
  if (!hint) throw new Error(`no sb-hint labelled "${label}"`);
  return hint.text();
}
```

For a chart tooltip, defined locally the same way:

```ts
import { ComponentFixture } from '@angular/core/testing';

/** Focus the first hit matching `hitSelector` and return the chart tooltip's text (A4 audit). */
async function tooltipText(fixture: ComponentFixture<unknown>, hitSelector: string): Promise<string> {
  const hit = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(hitSelector);
  if (!hit) throw new Error(`no chart hit "${hitSelector}"`);
  hit.dispatchEvent(new FocusEvent('focus'));
  fixture.detectChanges();
  await fixture.whenStable();
  const tip = (fixture.nativeElement as HTMLElement).querySelector('sb-chart-tooltip .tooltip');
  return tip?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}
```

(`hitSelector` is the primitive's focusable mark: `td.sb-hit` for `sb-heat-grid`; for the others read the `(focus)=` element in its template.)

Pattern **caveat added**, a constant (`PANEL_HELP` and the `*_ABOUT` constants) — test in the constant's spec (here `frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts`):

```ts
import { PERFORMANCE_CAVEAT } from '../../../ui/stat-tile';
import { PANEL_HELP } from './panel-help';

describe('PANEL_HELP copy (A4 audit)', () => {
  it('<key> states the paper, gross, pre-tax basis', () => {
    expect(PANEL_HELP.<key>).toContain(PERFORMANCE_CAVEAT);
  });
});
```

Pattern **caveat added**, an inline template text — in the component's spec, after the existing fixture setup:

```ts
it('<Label> hint names its population and basis (A4 audit)', () => {
  const text = hintText(fixture, 'About <Label>');
  expect(text).toContain('<population phrase, e.g. "closed plans in the selected range">');
  expect(text).toContain(PERFORMANCE_CAVEAT);
});
```

Pattern **fixed text** — assert the true phrase and the absence of the false one:

```ts
it('<Label> hint matches what the figure counts (A4 audit)', () => {
  const text = hintText(fixture, 'About <Label>');
  expect(text).toContain('<true phrase from Step 3>');
  expect(text).not.toContain('<false phrase from the old text>');
});
```

Pattern **fixed text** on a chart tooltip:

```ts
it('<chart title> tooltip names its unit and population (A4 audit)', async () => {
  const text = await tooltipText(fixture, '<hitSelector>');
  expect(text).toContain('<true label, e.g. "ExpR (R)">');
  expect(text).not.toContain('<false label>');
});
```

Pattern **fixed figure** — a fixture with two populations that the old and the new code count differently (for example one plan closed inside the selected range and one before it, or one plan closed in two legs), and an exact expected value. Frontend computation: in the store's spec, `expect(store.<signal>()).toBe(<exact value>)`; server-side computation: in `tests/admin/test_api_v1_<endpoint>.py`, built with that file's existing fixtures, `assert body["<field>"] == <exact value>` on the same two-population data. The test name ends `_a4_<row #>`.

Run each new test: `npm --prefix "$WT/frontend" test -- --watch=false --include <spec path without frontend/>` (or `python scripts/dev/testrun.py file <test path>`).
Expected: FAIL — the `toContain` of the new phrase (or the exact value) misses, quoting the old text or value.

- [ ] **Step 6: Make the fix, row by row**

- *Constant caveat:* old → new in the constant, keeping the old sentence first:
  `  <key>:\n    '<old text>',` → `  <key>:\n    \`<old text> ${PERFORMANCE_CAVEAT}\`,` and `import { PERFORMANCE_CAVEAT } from '<relative path>/ui/stat-tile';` at the top of the constants file. A text that already states the basis in other words (as `PANEL_HELP.tradingPerformance` does: "Simulated trades, before tax and costs.") is `correct` if it says all three of paper, gross/net and pre-tax; otherwise its basis sentence is replaced by `PERFORMANCE_CAVEAT`, never duplicated.
- *Inline text:* old → new string at the site's line; when the text grows past one line of template, move it into a `protected readonly <name>About = '…';` field on the component (the `PANEL_HELP` style) and bind `[text]="<name>About"`.
- *Chart tooltip:* change only what the consumer passes (the data `label`, `yLabel`, `unit`, `format`); a label hard-coded in a primitive's `show()` (`'trades'` in `bar-list.ts`, `dot-plot.ts`, `heat-grid.ts`; `'observations'` in `histogram.ts`) that is wrong for one consumer but right for others is a new input — report the row to the controller (Interfaces above), do not add it.
- *Fixed figure:* change the computing function's population or unit to the documented intent; keep every function you change below complexity 15 (extract a helper rather than add a branch).

Run each test again, same commands. Expected: PASS. Then the whole frontend run and lint (`npm --prefix "$WT/frontend" test -- --watch=false`; `npm --prefix "$WT/frontend" run lint`), and for any backend change `python scripts/dev/testrun.py changed`.

- [ ] **Step 7: Commit in scoped commits**

One frontend commit per route touched (`fix(v194): A4 hint and tooltip copy on <route> (V194-16)`), one backend commit per server-side figure fix (`fix(v194): <figure> counts <population> (V194-16)`), then the record (`docs(v194): A4 content audit record (V194-16)`, the part file only). No commit contains `$WT/.superpowers/`. If every row is `correct`, the only commit is the record.

Close: standard (test: frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts) — deviations: step 2 of the standard close runs every spec and test file this task changed (listed in the record's `Fix` cells), not only the one named; step 4 is Step 7's several commits.

### Task V194-16b: `ui-design.md` § Checklist names the layout audit's `hint` check; `AGENTS.md` mirror

**Model:** haiku — two prose edits at given lines plus one existing test run; no judgement beyond the given text.

**Spec:** A2 ("from this spec on, the `hint` check is the probe"). Runs after V194-3 (the check exists) and may run in parallel with V194-16 (disjoint files).

**Files:**
- Modify: `docs/claude/ui-design.md:53-56` (§ Checklist for every screen or control, the layout-audit bullet)
- Modify: `AGENTS.md:219-220` (the condensed `ui-design.md` bullet)
- Test: `tests/hooks/test_codex_mirror.py` (existing; fails when `docs/claude/` and `AGENTS.md` drift)

**Interfaces:**
- Consumes: `hintVerdict`, `CHECKS` (V194-3: `CHECKS` ends `'vcenter', 'hint'`; the check hovers at 1440, taps at 390 and 768, and fails a popover that is zero-size, off-screen, or not topmost at its centre and its top-left + 8px).
- Produces: nothing other tasks read.

- [ ] **Step 1: Confirm the check the docs will name exists in the branch**

Run: `git -C "$WT" grep -n "'hint'" -- frontend/scripts/layout-audit-lib.mjs`
Expected: the `CHECKS` line ends `'vcenter', 'hint']);`. If not, V194-3 is not merged: stop.

- [ ] **Step 2: Edit `docs/claude/ui-design.md:53-56`**

Old:

```markdown
  must exit 0 at 390, 768 and 1440. It checks page overflow, off-screen and
  clipped text, sub-44px targets (phone/tablet), sub-11px text, baseline
  offsets over 2px, and (`vcenter`) table-cell content or an icon more than
  2px off centre, on every route and tab. A finding is fixed, not allowed;
```

New:

```markdown
  must exit 0 at 390, 768 and 1440. It checks page overflow, off-screen and
  clipped text, sub-44px targets (phone/tablet), sub-11px text, baseline
  offsets over 2px, (`vcenter`) table-cell content or an icon more than
  2px off centre, and (`hint`) every visible `sb-hint`: it opens each one
  (hover at 1440, tap at 390 and 768) and fails a popover that is
  zero-size, outside the viewport, or not the topmost element at its centre
  and at its top-left + 8px; the finding names the trigger's `aria-label`.
  The `hint` check is the only tooltip probe: never an ad-hoc script. It
  runs on every route and tab. A finding is fixed, not allowed;
```

Lines 57 onwards (`only canvas/third-party chart internals …`) stay as they are; a `hint` finding is never an allow-list entry (the next sentence's exceptions are canvas internals and browser-native parts only).

- [ ] **Step 3: Edit `AGENTS.md:219-220`**

Old:

```markdown
  `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` must
  exit 0 (allow-list entries carry a reason and a date).
```

New:

```markdown
  `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` must
  exit 0 (allow-list entries carry a reason and a date); its `hint` check
  opens every `sb-hint` and fails a popover that is off-screen or covered,
  and a `hint` finding is fixed, never allowed.
```

- [ ] **Step 4: Run the mirror test**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` (from `$WT`'s copy: `python "$WT/scripts/dev/testrun.py" file "$WT/tests/hooks/test_codex_mirror.py"`)
Expected: PASS, `0 failed`. A failure names the drifting section: align the `AGENTS.md` wording with it, never weaken the test.

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add docs/claude/ui-design.md AGENTS.md
git -C "$WT" commit -m "docs(v194): ui-design checklist names the layout audit hint check, AGENTS.md mirror (V194-16b)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Close: standard (test: tests/hooks/test_codex_mirror.py) — deviation: no frontend run (docs only); the complexity gate still runs.

### Task V194-17: Full suite; replica layout audit (`hint` included) at 390/768/1440; merge to `main`; post-deploy check recorded

**Model:** haiku — runs fixed commands and records their output; any failure or audit finding escalates to sonnet per `docs/claude/model-routing.md` (a fix is never made at haiku tier).

**Spec:** Verification (full suite once, layout audit with `hint` exit 0 on a replica before merge, `hint` check against production after deploy: 0 findings).

**Files:**
- Modify: this part file's notes below (`#### Verification record`, `#### Post-deploy record`), the worktree copy before the merge, the `main` copy for the post-deploy line.
- No code. A fix a step needs is committed as `fix(v194): <what> (V194-17)` in the file of the task that owns it, after escalation.

**Interfaces:**
- Consumes: `hintVerdict`, `CHECKS` (V194-3; `audit.json`'s findings carry `check: 'hint'`).
- Produces: the plan's verification record; the merged branch on `main`.

- [ ] **Step 1: Every ledger task is committed on the branch**

```bash
for id in 1 1b 2 2b 3 4 4b 5 6 6a 6b 6c 7 8 9 10 11 11b 12 12b 13 14 14b 15 15b 16 16b; do
  git -C "$WT" log --oneline main..HEAD | grep -q "(V194-$id)" || echo "MISSING V194-$id"
done
git -C "$WT" status --short
```

Expected: no `MISSING` line, and an empty status except the untracked, gitignored `.superpowers/` and `.env`. A missing id: stop and report.

- [ ] **Step 2: The full suite, once (dispatch the `test-runner` subagent)**

Dispatch `test-runner` with: worktree `$WT`, command `python "$WT/scripts/dev/testrun.py" full`, then `npm --prefix "$WT/frontend" test -- --watch=false`, `npm --prefix "$WT/frontend" run lint`, `node --test "$WT/frontend/scripts/layout-audit-lib.test.mjs"`, `python "$WT/scripts/dev/complexity_gate.py"`.
Expected: `0 failed`, `0 xfailed` on the full suite; the frontend run green; lint clean; `node --test` all pass (its `CHECKS` test lists eight checks); complexity gate exit 0. A changed pass count alone is not a failure (`docs/claude/testing-cost.md`). A failure: escalate, fix in the owning task's file, re-run **that test alone** (`testrun.py file …` or the narrow `--include` run), never the whole suite again.

- [ ] **Step 3: Rebuild the bundle and serve the replica**

The shared `swing-db` replica from V194-4 (or V194-8) is reused; run `/replicate-prod-db` again only if `docker ps --filter name=swing-db` shows it stopped or missing. Rebuild — never audit a stale bundle:

```bash
npm --prefix "$WT/frontend" run build
rm -rf "$WT/swingbot/admin/static/app"
cp -r "$WT/frontend/dist/frontend/browser" "$WT/swingbot/admin/static/app"
test -f "$WT/.env" || cp E:/Documents/Private/Projects/Discord-Bot/.env "$WT/.env"
```

`$WT/.env` points at the replica as set in V194-4 Step 1 (part 2); never print, echo or `git add` it. Stop any `admin_ui.py` still running from an earlier task, start `python "$WT/admin_ui.py"` with `run_in_background`, then sign in once: `node "$WT/frontend/scripts/browse.mjs" login --base http://localhost:1234` (it reads `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env` itself).

- [ ] **Step 4: Run the layout audit at three widths**

```bash
node "$WT/frontend/scripts/layout-audit.mjs" --base http://localhost:1234 --widths 390,768,1440 --out "$WT/.superpowers/v194-audit"; echo "exit=$?"
node -e "const a=require(process.argv[1]);const h=a.unallowed.filter((f)=>f.check==='hint');console.log('unallowed',a.unallowed.length,'hint',h.length);for(const f of a.unallowed)console.log(f.route,f.width,f.check,f.detail)" "$WT/.superpowers/v194-audit/audit.json"
```

Expected: `exit=0` and `unallowed 0 hint 0`. Any finding: escalate; fix it in the owning file (a `hint` finding is fixed, never allow-listed), rebuild (Step 3's first three commands, restart `admin_ui.py`), re-run Step 4. `STALE` allow-list lines are reported, not a failure; do not `--prune` in this task.

- [ ] **Step 5: Write the verification record and commit it**

Fill `#### Verification record` below with: the date (Berlin time from `date -u`, +1h in winter), the full-suite line (`<passed> passed, 0 failed, 0 xfailed`), the frontend counts, and the audit line (`layout audit 390/768/1440: exit 0, unallowed 0, hint 0`). Then:

```bash
git -C "$WT" add docs/superpowers/plans/2026-10-25-v194-ui-tooltips-and-data-truth_6-content-audit-and-release.md
git -C "$WT" commit -m "docs(v194): verification record (V194-17)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Merge to `main` (skill `worktree-lifecycle`)**

Stop the background `admin_ui.py`. Check for concurrent work before merging: `git -C E:/Documents/Private/Projects/Discord-Bot status --short` and `git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -5`. Uncommitted changes to files the branch touches, or a branch commit `main` already moved past in the same files: pause and ask the controller. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-25-v194-ui-tooltips-and-data-truth -m "merge(v194): UI integrity -- tooltips that open, figures that are true" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -1
```

Expected: a merge commit on `main`. No full suite after the merge (it ran once in Step 2). Do not remove the worktree or bump `VERSION.json`: `/close-out` does both.

- [ ] **Step 7: Post-deploy `hint` check against production (after the partner deploys)**

Deploying is not this plan's step. Once the merged build is live on bomeo-capital.com, from the main tree:

```bash
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/browse.mjs login --base https://bomeo-capital.com
node E:/Documents/Private/Projects/Discord-Bot/frontend/scripts/layout-audit.mjs --base https://bomeo-capital.com --widths 390,768,1440 --out "C:/Users/HuyCao/AppData/Local/Temp/v194-prod-audit"; echo "exit=$?"
node -e "const a=require(process.argv[1]);console.log('hint',a.unallowed.filter((f)=>f.check==='hint').length)" "C:/Users/HuyCao/AppData/Local/Temp/v194-prod-audit/audit.json"
```

Expected: `hint 0`. Record the line (date, `hint 0`, the deployed `VERSION.json` ui version) in `#### Post-deploy record` on `main` and commit it (`docs(v194): post-deploy hint check (V194-17)`). If the deploy has not happened when Step 6 lands, record `post-deploy: pending deploy (<date>)` there instead and report it as OPEN to the controller; a `hint` finding in production is a new fix, escalated, not a re-run.

Close: standard (test: frontend/scripts/layout-audit-lib.test.mjs) — deviations: Step 2 replaces the narrow run (this is the plan's one full-suite run); commits are Step 5's record, Step 6's merge and Step 7's record; standard step 1 checks the worktree before Step 6 only.

#### A4 audit record

(Filled by V194-16 Step 4.)

| # | Route | Label | Site | Claim (short) | Figure computed by | Verdict | Fix |
|---|---|---|---|---|---|---|---|

#### Verification record

(Filled by Step 5.)

#### Post-deploy record

(Filled by Step 7.)
