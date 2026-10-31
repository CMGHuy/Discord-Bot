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

Audited by V194-16 on the worktree at its HEAD of 2026-10-28; line numbers are from that tree.

| # | Route | Label | Site | Claim (short) | Figure computed by | Verdict | Fix |
|---|---|---|---|---|---|---|---|
| 1 | /dashboard | About proxy figures (shell tape, every route) | `shell/tape/tape.ts:61` | ETF stands in for a missing index; change only | `shell/tape/tape.ts:129` tape rows | correct | — |
| 2 | /dashboard | Trading performance | `workspaces/dashboard/panels/panel-help.ts:12` | paper account, selected period, simulated, before tax and costs | `stores/dashboard.store.ts:347` ← `swingbot/admin/api_v1/dashboard.py:338` | correct | — |
| 3 | /dashboard | About open positions (lifecycle ?) | `workspaces/dashboard/dashboard.ts:247` | no figure: which plans are logged, lifecycle, P&L and Expected R columns | `ui/status-cell.ts`, `ui/plan-cell.ts` | correct | — |
| 4 | /dashboard | Recent activity | `workspaces/dashboard/panels/panel-help.ts:19` | no figure: latest plan events, newest first | `workspaces/dashboard/panels/recent-activity.ts:107` | correct | — |
| 5 | /dashboard | Market movers | `workspaces/dashboard/panels/panel-help.ts:21` | no figure: biggest moves today on the watchlist | `workspaces/dashboard/panels/market-movers.ts:73` tape `change_pct` | correct | — |
| 6 | /dashboard | Exposure by horizon | `workspaces/dashboard/panels/panel-help.ts:23` | share of open risk per horizon "(short, medium, long)" | `workspaces/dashboard/panels/exposure-by-horizon.ts:54` shares × entry-to-original-stop, in the browser | fixed text | `workspaces/dashboard/panels/panel-help.ts:23` names the risk measure, drops three horizons that do not exist (`swingbot/core/market/strategy_types.py:56` has 1w..8m); test `panel-help.spec.ts` 'names how open risk is measured…'. OPEN: risk summed in quote currencies, unconverted |
| 7 | /dashboard | Watchlist | `workspaces/dashboard/panels/panel-help.ts:26` | no figure: scanned symbols, latest price, day change | `workspaces/dashboard/panels/watchlist-panel.ts:64` | correct | — |
| 8 | /dashboard | Open P&L | `workspaces/dashboard/panels/panel-help.ts:31` | open positions "as a percentage and in money" | `swingbot/admin/api_v1/dashboard.py:326` mean of unrealised %, total via `convert_amount` | fixed text | `workspaces/dashboard/panels/panel-help.ts:31` average % across positions, total in the account currency, basis; test 'says Open P&L is an average percentage…' (B7, V194-6c) |
| 9 | /dashboard | Win rate | `workspaces/dashboard/panels/panel-help.ts:35` | share of closed trades in profit, selected period; N = closed trades | `swingbot/admin/api_v1/dashboard.py:368` `m.win_rate(closed_scoped)` over realised legs (`swingbot/admin/api_v1/dashboard.py:205`) | caveat added | `workspaces/dashboard/panels/panel-help.ts:35` names ExpR beside N, basis; test 'names ExpR and N beside the win rate'; says each realised leg counts as its own trade (test 'says the Dashboard counts each realised leg as a trade') |
| 10 | /dashboard | Expectancy | `workspaces/dashboard/panels/panel-help.ts:39` | average R per closed trade | `swingbot/admin/api_v1/dashboard.py:370` over realised legs | caveat added | `workspaces/dashboard/panels/panel-help.ts:39` basis; test 'states the paper, gross, pre-tax basis…'; says each realised leg counts as its own trade (same test) |
| 11 | /dashboard | Payoff ratio | `workspaces/dashboard/panels/panel-help.ts:42` | mean win R ÷ mean loss R, with example | `swingbot/admin/api_v1/dashboard.py:374` `payoff_ratio_from_rs(scoped_rs)` | caveat added | `workspaces/dashboard/panels/panel-help.ts:42` basis; same test |
| 12 | /dashboard | Realised today | `workspaces/dashboard/panels/panel-help.ts:46` | closed today "(New York day)" | `swingbot/admin/api_v1/dashboard.py:225` `is_today_berlin` (`swingbot/admin/dashboard.py:95`); 1D maps to mode `today` (`workspaces/dashboard/panels/equity-range.model.ts:353`) | fixed text | `workspaces/dashboard/panels/panel-help.ts:46` Berlin day, basis; test 'says Realised today runs on the Berlin day…' |
| 13 | /dashboard | Realised in period | `workspaces/dashboard/panels/panel-help.ts:49` | closed in the selected period, "in money" | `swingbot/admin/api_v1/dashboard.py:228` `_realized` via `to_account_currency` | caveat added | `workspaces/dashboard/panels/panel-help.ts:49` account currency, basis; test 'states the paper, gross, pre-tax basis…' (B7, V194-6c) |
| 14 | /dashboard | Open trades | `workspaces/dashboard/panels/panel-help.ts:52` | positions open right now | `swingbot/admin/api_v1/dashboard.py:328` live main-ledger positions | correct | — |
| 15 | /dashboard | Avg confidence | `workspaces/dashboard/panels/panel-help.ts:53` | alerts behind trades "in the selected period" | `swingbot/admin/api_v1/dashboard.py:329` over open positions, date scope ignored (`swingbot/admin/api_v1/dashboard.py:307`) | fixed text | `workspaces/dashboard/panels/panel-help.ts:53` positions open right now; test 'says Avg confidence reads the open positions…' |
| 16 | /dashboard | About the change figure | `workspaces/dashboard/panels/equity-candles.model.ts:24` | change from the previous candle's close, not a return on capital | equity candles ← `swingbot/admin/api_v1/equity.py` | caveat added | `equity-candles.model.ts:24` basis; test `equity-candles.model.spec.ts` 'keeps its definition and states…'; pin in `equity-candles.spec.ts` updated |
| 17 | /dashboard | About this partial position | `ui/status-cell.ts:239` via `workspaces/dashboard/dashboard.ts:416` | partially closed, X% still open | `banked_fraction` ← `swingbot/admin/api_v1/trades.py` | correct | — |
| 18 | /dashboard | About Leg N of M | `workspaces/trades/leg-label.ts:24` via `workspaces/dashboard/dashboard.ts:421` | parts of one plan; win rate and N count plans, not legs | the Dashboard chips count legs: `swingbot/admin/api_v1/dashboard.py:352` `_realized_parts` ← `swingbot/core/tracking/performance.py:485` | fixed text | `workspaces/dashboard/dashboard.ts:1010` `legHint` = base + "win rate and N count each realised leg as its own trade; Analytics counts plans"; `workspaces/trades/leg-label.ts:27` base drops the plans-not-legs claim; test `dashboard.spec.ts` leg-row test |
| 19 | /dashboard | About leg rows (trade drawer) | `workspaces/dashboard/trade-drawer.ts:129` | same `LEG_HINT_TEXT` | as above | fixed text | `workspaces/dashboard/trade-drawer.ts:209` `legHint` (Dashboard legs sentence); test `trade-drawer.spec.ts` 'explains the leg field with how the Dashboard counts legs' |
| 20 | /dashboard | About paper trades (trade drawer) | `workspaces/dashboard/trade-drawer.ts:18` | no figure: the bot places no orders | — | correct | — |
| 21 | /dashboard | About the two P&L figures | `ui/status-cell.ts:74` | left: P&L at the trailing stop; right: at the best price since TP1 | `swingbot/admin/api_v1/trades.py:1197` `_trailing_pnl_ends`, % vs the original entry | caveat added | `ui/status-cell.ts:74` per share from the entry, in percent, basis; test `status-cell.spec.ts` 'says the two ends are percent…' |
| 22 | /dashboard | About delayed prices | `ui/status-cell.ts:77` | no figure: price not freshly fetched | `current_price_stale` | correct | — |
| 23 | /dashboard | About this runner's plan | `ui/plan-cell.ts:328` + `:193` | original plan levels; trail % per share from entry, before costs and tax, paper level | `swingbot/admin/api_v1/trades.py:399` `_runner_pnl_fields` | correct | — |
| 24 | /trades | About the CSV export | `workspaces/trades/trades.ts:119` | whole trade log; the filters do not narrow it | `api/api-client.ts:224` `tradesExportUrl()` takes no query | correct | — |
| 25 | /trades | About this partial position | `ui/status-cell.ts:239` via `workspaces/trades/trades.ts:407` | partially closed, X% still open | `banked_fraction` | correct | — |
| 26 | /trades | About Leg N of M | `workspaces/trades/leg-label.ts:24` via `workspaces/trades/trades.ts:414` | parts of one plan; win rate and N count plans, not legs | no win rate on /trades; true of Analytics (`swingbot/admin/api_v1/analytics.py:198` `closed_only`), false of Dashboard and Calendar | fixed text | `workspaces/trades/trades.ts:1006` `legHint`: Analytics counts plans, Dashboard and Calendar count legs; test `trades.spec.ts` leg-row test; `leg-label.spec.ts` base test |
| 27 | /trades | About leg rows (drawer) | `workspaces/trades/trades.ts:529` | same `LEG_HINT_TEXT` | as above | fixed text | the /trades leg row's `legHint` |
| 28 | /trades | About the two P&L figures | `ui/status-cell.ts:74` | as on /dashboard | `swingbot/admin/api_v1/trades.py:1197` | caveat added | the /dashboard row's change |
| 29 | /trades | About delayed prices | `ui/status-cell.ts:77` | no figure | `current_price_stale` | correct | — |
| 30 | /trades | About this runner's plan | `ui/plan-cell.ts:328` + `:193` | as on /dashboard | `swingbot/admin/api_v1/trades.py:399` | correct | — |
| 31 | /trades/:id | About the cohort chip | `workspaces/trades/trade-detail.ts:723` | regime cohort WR / ExpR (n, frozen date) | `swingbot/core/planning/params.py:213` ← `swingbot/core/backtesting/cohort_registry.py:92` (live + replay prior) | correct | — (names WR, ExpR and n; the replay prior's cost basis not traced, see report) |
| 32 | /trades/:id | About fragile stops | `workspaces/trades/why/sizing-panel.ts:8` via `workspaces/trades/position-card.ts:54` | stop inside 90th-percentile gap noise | `swingbot/core/edge/context.py:107` `stop_beyond_gap_noise(stop_pct, gap_p90_pct)` | correct | — |
| 33 | /trades/:id?tab=why | About unevaluated factors | `workspaces/trades/why/why-panel.ts:25` | no figure: no data, neutral points | `confidence_unevaluated` (v146 I1) | correct | — |
| 34 | /trades/:id?tab=why | About gates that are off | `workspaces/trades/why/why-panel.ts:26` | no figure: gate off in config | `gate.applies` | correct | — |
| 35 | /plans/:plan | About unevaluated factors | `workspaces/trades/why/why-panel.ts:25` | as above | as above | correct | — |
| 36 | /plans/:plan | About gates that are off | `workspaces/trades/why/why-panel.ts:26` | as above | as above | correct | — |
| 37 | /plans/:plan | About fragile stops | `workspaces/trades/why/sizing-panel.ts:30` | as above | `swingbot/core/edge/context.py:107` | correct | — |
| 38 | /analytics | Sharpe · annualised, selected range | `workspaces/analytics/tabs/overview.ts:27` | annualised, closed trades in range and filters; N; basis | `swingbot/admin/api_v1/analytics.py:260` `sharpe_ann` | correct | — (B8, V194-11) |
| 39 | /analytics | Max drawdown · cumulative R, selected range | `workspaces/analytics/tabs/overview.ts:31` | fall of cumulative R in range; money in the account currency; N = curve points; basis | `overview.ts` `drawdownR` ← `/analytics/equity-curve` | correct | — (B8, V194-11) |
| 40 | /analytics | Win rate (tile) | `workspaces/analytics/tabs/overview.ts:38` `ANALYTICS_WIN_RATE_ABOUT` | new hint: closed plans in range and filters, a scaled-out plan counts once; N; ExpR; basis | `swingbot/admin/api_v1/analytics.py:237` `m.win_rate(closed)` over `closed_only` plans | caveat added | `overview.ts` Win rate tile `about`; test 'Win rate tile says Analytics counts plans…' |
| 41 | /analytics | Equity definition | `workspaces/analytics/tabs/overview.ts:191` | cumulative unit per closed trade, by close date | `/analytics/equity-curve` points | caveat added | `overview.ts:191` `equityHint` basis; test `overview.spec.ts` 'Equity and R distribution hints state…' |
| 42 | /analytics | Outcome definition | `workspaces/analytics/tabs/overview.ts:119` | Win = TP1 touched; avg win and loss are R means | bar: `swingbot/admin/api_v1/analytics.py:230` `relocated.wins/losses` from `get_stats(all_raw)`: whole book, legs expanded, scope ignored; the panel's N and the Win rate tile are scoped plans | caveat added | `overview.ts` `outcomeHint`: the bar covers the whole main-ledger book, counts legs, ignores scope and filters (partner: text, not figure); test 'Outcome hint says its bar covers the whole book…' |
| 43 | /analytics | R distribution definition | `workspaces/analytics/tabs/overview.ts:141` | every closed trade's realised R | `swingbot/admin/api_v1/analytics.py:287` `histogram(r_multiples(scoped))` | caveat added | `overview.ts` `rDistributionHint` basis; same test |
| 44 | /analytics | By month definition | `workspaces/analytics/tabs/overview.ts:150` | "realised result" per month | `swingbot/core/analytics/metrics.py:974` `calendar_returns`: compounded % of the month's opening balance | fixed text | `overview.ts:199` `monthHint`; test 'By month hint names a percent return…' |
| 45 | /analytics | Outcome (tooltip) | `ui/share-bar.ts:17` via `workspaces/analytics/tabs/overview.ts:124` | Wins / Losses: count · share | as the Outcome definition row | caveat added | covered by the Outcome definition caveat; tooltip unchanged |
| 46 | /analytics | R distribution (tooltip) | `ui/histogram.ts:155` via `workspaces/analytics/tabs/overview.ts:143` | bin; observations = trades in the bin | `swingbot/admin/api_v1/analytics.py:287` | correct | — |
| 47 | /analytics | By month (tooltip) | `ui/bar-list.ts:24` via `workspaces/analytics/tabs/overview.ts:152` | value in the R/%/money toggle unit (`+1.20R` for a 1.2% month); trades = n | `metrics.py:974` `return_pct` | fixed text | `overview.ts:202` `monthFormat` reads percent; test 'By month tooltip reads the return in percent…' |
| 48 | /analytics?tab=attribution | Contribution definition | `workspaces/analytics/tabs/attribution.ts:174` | total R per strategy, top eight plus Other | `strategies().contribution` ← `/analytics/strategies` | caveat added | `attribution.ts:174` `contributionHint` basis; test `attribution.spec.ts` 'Contribution and Strategy x horizon hints…' |
| 49 | /analytics?tab=attribution | ExpR vs sample size definition | `workspaces/analytics/tabs/attribution.ts:180` | "Each point is one strategy" | `stores/analytics.store.ts:722` `analyticsByDimension(store.breakdown())`: the Group by control, default strategy | fixed text | `attribution.ts:180` `dotHint`; test 'dot plot hint says a point is one group…' |
| 50 | /analytics?tab=attribution | Strategy x horizon definition | `workspaces/analytics/tabs/attribution.ts:184` | colour ramp; dotted cell below the floor | `/analytics/heat-grid` cells | caveat added | `attribution.ts:184` `heatHint` basis; the Contribution row's test |
| 51 | /analytics?tab=attribution | Contribution (tooltip) | `ui/waterfall.ts:20` via `attribution.ts:71` | contribution `2.50`, no unit; trades = n | `strategies().contribution.total_r` | fixed text | `attribution.ts:71` `[format]="rFormat"`; test 'Contribution tooltip names its unit, R' |
| 52 | /analytics?tab=attribution | Measure vs sample size (tooltip) | `ui/dot-plot.ts:6` via `attribution.ts:80` | yLabel = the measure, R or %; trades = n | `byDimension().rows` | correct | — |
| 53 | /analytics?tab=attribution | Strategy x horizon (tooltip) | `ui/heat-grid.ts:2` via `attribution.ts:89` | value `0.25`, no unit; trades = n | `heatGrid().cells` (`heatCell` default `exp_r`) | fixed text | `attribution.ts:189` `heatFormat()`; test 'Strategy x horizon tooltip names its unit…' |
| 54 | /analytics?tab=attribution | By horizon (tooltip) | `ui/bar-list.ts:24` via `attribution.ts:100` | measure value; trades = n | `byHorizon().rows` | correct | — |
| 55 | /analytics?tab=attribution | By direction (tooltip) | `ui/bar-list.ts:24` via `attribution.ts:110` | as above | `byDirection().rows` | correct | — |
| 56 | /analytics?tab=attribution | By day of week (tooltip) | `ui/bar-list.ts:24` via `attribution.ts:120` | as above | `byDow().rows` | correct | — |
| 57 | /analytics?tab=attribution | By month (tooltip) | `ui/bar-list.ts:24` via `attribution.ts:130` | % return (`pctFormat`); trades = n | `metrics.py:974` | correct | — |
| 58 | /analytics?tab=execution | Execution verdict definition | `workspaces/analytics/tabs/execution.ts:16` | exit quality for the scoped closed book | `swingbot/admin/api_v1/analytics.py:688` `select(closed_only(...), scope)` | correct | — |
| 59 | /analytics?tab=execution | Overrides vs engine definition | `workspaces/analytics/tabs/override-fidelity-panel.ts:79` | Δ "in dollars and R" | `swingbot/core/analytics/override_fidelity.py:372` `to_usd`: R × shares × stop distance, quote currency, never converted; R net of modelled costs | fixed text | `override-fidelity-panel.ts:79` `headerHint`: quote currency, net of modelled costs, pre-tax; test 'Overrides vs engine hint matches…'. OPEN: B7 conversion missing (core, called by the daily verdict job) |
| 60 | /analytics?tab=execution | Exit reasons (tooltip) | `ui/share-bar.ts:17` via `execution.ts:20` | reason: count · share | `swingbot/admin/api_v1/analytics.py:699` `exit_reason_split(scoped)` | correct | — |
| 61 | /analytics?tab=execution | Hold time by outcome (tooltip) | `ui/strip-plot.ts:3` via `execution.ts:21` | held Nd | `hold_points` days | correct | — |
| 62 | /analytics?tab=execution | Exit efficiency (tooltip) | `ui/histogram.ts:155` via `execution.ts:22` | observations = trades in the bin | `efficiency.bins` | correct | — |
| 63 | /analytics?tab=edge | Live loss watch definition | `workspaces/analytics/tabs/edge.ts:71` | opened on/after 2026-10-16, both ledgers, manual closes, ignores scope | `swingbot/core/analytics/calibration.py:160` `EXPR_WATCH_START`; `swingbot/core/tracking/live_loss_watch.py:83` | caveat added | `edge.ts:71` basis; test `edge.spec.ts` 'Live loss watch hint names…' |
| 64 | /analytics?tab=edge | Win-rate drift definition | `workspaces/analytics/tabs/edge.ts:83` | live WR vs OOS WR of validated rows | `calibration().drift` (the table carries OOS N and Live N, no ExpR) | caveat added | `edge.ts:83` names N, points at Live ExpR, basis; test 'Win-rate drift hint names N and ExpR…' |
| 65 | /analytics?tab=edge | Calibration deciles (tooltip) | `ui/histogram.ts:155` via `edge.ts:33` | "observations" printed for the decile's win rate % | `edge.ts` `decileBins` (count = win_rate) | PENDING | needs a new `sb-histogram` input (label hard-coded in `show()`): reported, not added |
| 66 | /analytics?tab=pipeline | Plan funnel definition | `workspaces/analytics/tabs/pipeline.ts:11` | lifecycle counts posted through closed, all-time | `plans().funnel` ← `/analytics/plans` | correct | — |
| 67 | /analytics?tab=pipeline | Plan funnel (tooltip) | `ui/histogram.ts:155` via `pipeline.ts:11` | observations = plans per stage | `plans().funnel` | correct | — |
| 68 | /analytics?tab=pipeline | Badges (tooltip) | `ui/histogram.ts:155` via `pipeline.ts:14` | observations = strategies per badge | `plans().badges` | correct | — |
| 69 | /analytics?tab=pipeline | Tiers (tooltip) | `ui/histogram.ts:155` via `pipeline.ts:17` | observations = strategies per tier | `plans().tiers` | correct | — |
| 70 | /analytics?tab=partials | Funnel definition | `workspaces/analytics/tabs/partials.ts:163` | share of filled trades per stage | `swingbot/core/analytics/partials.py:207` | correct | — |
| 71 | /analytics?tab=partials | Runner outcome mix definition | `workspaces/analytics/tabs/partials.ts:165` | how each runner ended, avg runner R | `partials.py:213` | correct | — |
| 72 | /analytics?tab=partials | Does the runner pay? definition | `workspaces/analytics/tabs/partials.ts:219` | all-out ExpR plus the runner's delta | `partials.py:249` `counterfactuals` | caveat added | `partials.ts:219` basis; test `partials.spec.ts` 'the three ExpR panels…' |
| 73 | /analytics?tab=partials | TP2 ladder definition | `workspaces/analytics/tabs/partials.ts:220` | counterfactual ExpR per TP2 level; touch share | `partials.py:224` `_ladder_row` | caveat added | `partials.ts:220` basis; same test |
| 74 | /analytics?tab=partials | Split what-if definition | `workspaces/analytics/tabs/partials.ts:222` | ExpR at other TP1 shares | `partials.py:233` `_split_row` | caveat added | `partials.ts:222` basis; same test |
| 75 | /analytics?tab=partials | Giveback definition | `workspaces/analytics/tabs/partials.ts:174` | best R seen minus R banked | `partials.py:238` `mfe_r - r_runner` | correct | — |
| 76 | /analytics?tab=partials | Hold times definition | `workspaces/analytics/tabs/partials.ts:176` | sessions per stage; open runners only pre-TP1 | `partials.py:272` `holds` | correct | — |
| 77 | /analytics?tab=partials | Breakdown definition | `workspaces/analytics/tabs/partials.ts:224` | rows under N = thin_n dimmed | `partials.py:27` `THIN_N` | correct | — |
| 78 | /analytics?tab=partials | Funnel (tooltip) | `ui/bar-list.ts:24` via `partials.ts:164` | stage share %; trades = count | `partials.py:207` | correct | — |
| 79 | /analytics?tab=partials | Runner outcomes (tooltip) | `ui/share-bar.ts:17` via `partials.ts:166` | bucket and avg R: count · share | `partials.py:213` | correct | — |
| 80 | /analytics?tab=partials | Does the runner pay? (tooltip) | `ui/waterfall.ts:20` via `partials.ts:168` | contribution in R (`rFmt`) | `partials.py:249` | correct | — |
| 81 | /analytics?tab=partials | TP2 ladder (tooltip) | `ui/bar-list.ts:24` via `partials.ts:170` | ExpR in R; trades = n | `partials.py:224` | correct | — |
| 82 | /analytics?tab=partials | TP2 touches (tooltip) | `ui/bar-list.ts:24` via `partials.ts:171` | touch share %; trades = n | `partials.py:224` | correct | — |
| 83 | /analytics?tab=partials | Split what-if (tooltip) | `ui/bar-list.ts:24` via `partials.ts:173` | ExpR in R; trades = n | `partials.py:233` | correct | — |
| 84 | /analytics?tab=partials | Giveback (tooltip) | `ui/histogram.ts:155` via `partials.ts:175` | observations = runners in the bin | `partials.py:238` | correct | — |
| 85 | /analytics?tab=partials | Hold times (tooltip) | `ui/strip-plot.ts:3` via `partials.ts:177` | held N sessions | `partials.py:272` | correct | — |
| 86 | /calendar | About leg rows | `workspaces/calendar/calendar.ts:301` | same `LEG_HINT_TEXT` | Calendar counts legs: `swingbot/core/analytics/pnl_calendar.py:245` `expand_realized_legs` | fixed text | `workspaces/calendar/calendar.ts:496` `legHint` (legs sentence); test `calendar.spec.ts` 'lists both legs of a scaled-out trade…' |
| 87 | /calendar/:date | About R (month to date) | `workspaces/calendar/day/calendar-day.ts:171` | R = initial risk; +1R made what was risked | `swingbot/core/analytics/metrics.py:173` `r_multiple` | correct | — (basis is the page's visible `PAPER_CAPTION`, `day-copy.ts:7`, v165 D7 verbatim) |
| 88 | /calendar/:date | What drove it | `workspaces/calendar/day/calendar-day.ts:177` | `R_TOOLTIP` | as above | correct | — |
| 89 | /calendar/:date | About Total | `workspaces/calendar/day/calendar-day.ts:132` | `R_TOOLTIP` | `day.total_r` ← `pnl_calendar.py:653` | correct | — |
| 90 | /calendar/:date | About Average trade | `workspaces/calendar/day/calendar-day.ts:137` | `R_TOOLTIP` | `day.avg_trade_r` | correct | — |
| 91 | /calendar/:date | About Worst drawdown | `workspaces/calendar/day/calendar-day.ts:138` | `R_TOOLTIP` | `day.worst_drawdown_r` | correct | — |
| 92 | /calendar/:date | About leg rows (trade card) | `workspaces/calendar/day/day-trade-card.ts:46` | same `LEG_HINT_TEXT` | `pnl_calendar.py:245` legs | fixed text | `workspaces/calendar/day/day-trade-card.ts:134` `legHint`; test `day-trade-card.spec.ts` 'explains leg rows with a hint that says how this page counts them' |
| 93 | /calendar/:date | About R (trade card) | `workspaces/calendar/day/day-trade-card.ts:51` | `R_TOOLTIP` | the leg's own `r` | correct | — |
| 94 | /watchlist | About fallback prices | `workspaces/watchlist/watchlist.ts:173` | no figure: Alpaca missed, yfinance answered | quote `source` | correct | — |
| 95 | /risk | Exact portfolio heat | `workspaces/risk/risk.ts:294` (text `:66`) | exact % of the account balance | `swingbot/admin/api_v1/risk.py` `heat.open_pct` | correct | — |
| 96 | /risk | Exact budget cap | `workspaces/risk/risk.ts:368` | as above | `heatCapPct` | correct | — |
| 97 | /risk | Exact budget used | `workspaces/risk/risk.ts:371` | as above | `openHeatPct` | correct | — |
| 98 | /risk | Exact budget remaining | `workspaces/risk/risk.ts:374` | as above | cap − used, floored at 0 | correct | — |
| 99 | /risk | Exact sector heat | `workspaces/risk/risk.ts:415` | as above | `sectorHeat().heat_pct` | correct | — |
| 100 | /risk | Exposure by position | `workspaces/risk/risk.ts:36` | paper shares under the 2% cap; Risk % of balance; <0.01% exact in a hint | `swingbot/admin/api_v1/risk.py:80` `trade_risk_pct` | correct | — |
| 101 | /risk | Exact risk for <ticker> | `workspaces/risk/risk.ts:542` | exact % of the account balance | `risk.py:80` | correct | — |
| 102 | /risk | Exact Risk % total | `workspaces/risk/risk.ts:814` (table footer) | as above | sum of row `risk_pct` | correct | — |
| 103 | /risk | Sharpe · per-trade R, all closed | `workspaces/risk/risk.ts:86` | mean R ÷ sd R, every closed main-ledger trade, all time; N; basis | `swingbot/admin/api_v1/risk.py:317` | correct | — (B8, V194-11) |
| 104 | /risk | Max drawdown · cumulative R, all closed | `workspaces/risk/risk.ts:90` | cumulative R fall; money at exit-day FX; N; basis | `risk.py:318`, `risk.py:235` | correct | — (B8, V194-11) |
| 105 | /system | About restart | `workspaces/system/settings-tab.ts:31` | no figure: restart required | settings schema | correct | — |
| 106 | /reports | Live (tooltip) | `ui/bar-list.ts:24` via `workspaces/reports/attribution-tab.ts:110` | ExpR per bucket (`formatR`); trades = n | report payload | correct | — |
| 107 | /reports | TRAIN (tooltip) | `ui/bar-list.ts:24` via `workspaces/reports/attribution-tab.ts:116` | as above | report payload | correct | — |
| 108 | /cancels | About small samples | `workspaces/cancels/cancels-summary.ts:203` | fewer than N resolved plans: an anecdote, not a rate | `small_n_threshold` | correct | — |
| 109 | /ui | About expectancy (demo) | `workspaces/gallery/gallery.ts:286` | "after costs" | demo; the book is gross (`metrics.py:173`) | fixed text | `gallery.ts:904` `expectancyHint`; test `gallery.spec.ts` 'Expectancy demo hint matches…' |
| 110 | /ui | Sample panel definition (demo) | `workspaces/gallery/gallery.ts:543` | no figure: demo text | — | correct | — |
| 111 | /ui | Primitive demos (status cell, plan cell) | `workspaces/gallery/gallery.ts` | the shared constants of the /dashboard rows | — | correct | — (texts covered by the /dashboard rows) |
| 112 | /ui | Histogram demos (tooltip) | `ui/histogram.ts:155` via `gallery.ts:468`, `:529` | demo bins | demo data | correct | — |
| 113 | /ui | Bar list demo (tooltip) | `ui/bar-list.ts:24` via `gallery.ts:469` | demo | demo data | correct | — |
| 114 | /ui | Share bar demo (tooltip) | `ui/share-bar.ts:17` via `gallery.ts:545` | demo | demo data | correct | — |
| 115 | /ui | Dot plot demo (tooltip) | `ui/dot-plot.ts:6` via `gallery.ts:553` | demo | demo data | correct | — |
| 116 | /ui | Heat grid demo (tooltip) | `ui/heat-grid.ts:2` via `gallery.ts:556` | demo | demo data | correct | — |
| 117 | /ui | Strip plot demo (tooltip) | `ui/strip-plot.ts:3` via `gallery.ts:562` | demo | demo data | correct | — |
| 118 | /ui | Waterfall demo (tooltip) | `ui/waterfall.ts:20` via `gallery.ts:565` | demo | demo data | correct | — |

Sites: 84 hint, 34 chart tooltip; verdicts: 81 correct, 19 caveat added, 17 fixed text, 0 fixed figure (plus 1 PENDING a partner decision or a new primitive input, reported).

Not sites (checked, no popover): `fxMissingText` (`workspaces/analytics/scope-bar.ts:143`) renders as visible `role="note"` text on Analytics, Calendar, Dashboard and Trades; `PANEL_HELP.openPositions` is bound with `[descriptionHint]="false"` (`workspaces/dashboard/dashboard.ts:242`), so the lifecycle `?` hint (row 3) is the panel's only popover; `sb-stat-tile` `hint` and `sb-empty-state` `hint` are plain text (the Profit factor tile's "Gross realised win ÷ gross realised loss." included).

Partner decision (2026-10-28, through the controller): fix the text, not the figures. Rows 18, 19, 26, 27, 42, 45, 86, 92 were PENDING on which population win rate and N count. The Dashboard chips (`swingbot/admin/api_v1/dashboard.py:352`) and the Calendar (`swingbot/core/analytics/pnl_calendar.py:245`) count each realised leg as a trade; Analytics counts plans (`swingbot/admin/api_v1/analytics.py:198`); the Outcome bar reads `get_stats(all_raw)` (whole main-ledger book, legs, scope ignored). Each surface now states its own basis, and no figure or backend changed.

Still PENDING: row 65. The Calibration deciles tooltip prints a win-rate % under "observations", which is hard-coded in `ui/histogram.ts:155` `show()`. The fix is a new primitive input, outside this task's ledger. Reported, not fixed.

OPEN (recorded, not changed): row 6, Exposure by horizon sums risk in each instrument's quote currency in the browser; row 59, override-fidelity money is never converted to the account currency (B7 gap; `override_verdict.build_report` also feeds the bot's daily verdict job). Row 31: the cohort chip names WR, ExpR and n, but the cost basis of its frozen replay prior was not traced.

#### Verification record

2026-10-28 (Berlin 15:26 CET, from `date -u` 14:26 UTC).

- Full suite on the branch after merging `main` in: 14676 passed, 6 failed, 4 skipped. Triage: 3 were v194's (portfolio_state `exc_info`, swallowed ratchet 244 vs 243, AGENTS.md 32900 B over the 32768 cap) -- fixed, each re-run alone green (38c1a2b2, 4bedf955, c21739c8; ratchet baseline lowered 243 -> 241, never raised). 2 scan tests (`test_scan_rebuild_wiring`, `test_scan_telemetry_sources`) failed under a 19-minute contended run and pass alone on `main` and the branch. 1 (`test_skill_shape` replicate-prod-db 90 > 80 lines) fails on `main` too, from the v196 skill commits -- not v194's, left open.
- Frontend: 237 files, 5536 passed, 4 skipped, 0 failed; lint clean; `layout-audit-lib.test.mjs` 35 pass; complexity gate PASS.
- Layout audit 390/768/1440 on the replica: exit 1, unallowed 292, **hint 0**. 291 are shell-wide (topbar baseline on every route, ticker-tape clipping, 200x19px tape-tile taps at 768; the topbar and tape clipping at 1440 were already seen in the v188 audit) and none are in the v194 surfaces; the 768 tape and tap findings were not compared against `main`. 1 was v194's (`/trades` 768 vcenter, the leg-label hint's 44px tap area) -- fixed in 759226af, verified by replaying the audit geometry (max offset 0.2px at 768 and 1440), full audit not rerun.
- A4 audit: row 65 (Calibration deciles "observations") reported, not fixed; rows 6 and 59 (two money figures never converted to the account currency) open.

#### Post-deploy record

post-deploy: pending deploy (2026-10-28) -- production `hint` check not yet run; OPEN.
