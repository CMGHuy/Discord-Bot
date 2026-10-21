# v173 Execution fidelity, part 4b: the "Overrides vs engine" panel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-14:" -A 700 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §5 (panel "Overrides vs engine": tiles, badge copy, caption, exclusion notes, row table and cards) and `## Plan panel review` (the financial-advisor items: "waiting on other conditions", "No conclusion yet.", the open-row note, plurals, a legible caption, modelled position size; the quant-researcher item: recorded figures shown as recorded, live sums labelled)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints, in particular **UI copy (verbatim)** and **UI layout**.

Tasks: V173-14 (moved here from part 4 on 2026-10-19 and rewritten). It needs V173-13 (part 4: the types, the store slice and `override-fidelity.fixture.ts`). It is disjoint from V173-11, V173-12 and V173-27 and may run beside any one of them. Part 5's V173-15 checks this panel at 390, 768 and 1280px and depends on two names fixed here: the selector `sb-override-fidelity-panel`, and cards as `<li class="card">` inside `<ul class="cards">`.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**What V173-13 created** (check with `git -C $WT grep -n "<name>" -- frontend/src/app/`; a missing one means V173-13 is not on the branch: stop and report, never re-create it): in `api/models.ts` `OverrideStatus` (eight, with `unstamped`), `OverrideWaitingOn`, `OverrideRowDto` (with `delta_r_gross`), `OverrideSummary` (with `sum_delta_r_gross`), `OverrideVerdict` (17 fields: `waiting_on`, `mean_delta_r_gross`, `sum_delta_r`, `sum_delta_usd`, `bar_close_n` among them), `OverrideFidelity`; store signals `overrideFidelity`, `overrideFidelityError` and `reload('overrideFidelity')`; in `workspaces/analytics/tabs/override-fidelity.fixture.ts` `OVERRIDE_FIDELITY_FIXTURE` (WAITING, `n` 1; one counted, one approx, one bulk and one stale row, every count 1), `overrideFixture(...)`, `VERDICT_WAITING_ON` (34 counted, 8 of 10 weeks, 2 open, 25% left out), `VERDICT_FLOORS_MET` (34, evaluable, not recorded) and `VERDICT_RECORDED_COST` (recorded 2026-12-04, `n` 31, 12 weeks, mean −0.22, gross −0.20, CI [−0.24, −0.20], Σ −6.82 R / −$1,364, `bar_close_n` 2).

**Frontend specs use stubs**: an `AnalyticsStore` stub with signals, a `PreferencesStore` stub; no HTTP, no database.

# Phase 4: Report, API and panel (continued)

### Task V173-14: Panel "Overrides vs engine" on the Execution tab

**Model:** sonnet — one panel component following the tab's pieces

**Files:**
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts`, `override-fidelity.model.spec.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`, `override-fidelity-panel.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/tabs/execution.ts` (mount the panel), `execution.spec.ts` (store stub, mount test)

**Interfaces:**
- Consumes: V173-13's types (`OverrideFidelity`, `OverrideRowDto`, `OverrideStatus`, `OverrideSummary`, `OverrideVerdict`, `OverrideWaitingOn`), store signals `overrideFidelity`/`overrideFidelityError`, `reload('overrideFidelity')`, and the fixtures `OVERRIDE_FIDELITY_FIXTURE`, `overrideFixture`, `VERDICT_WAITING_ON`, `VERDICT_FLOORS_MET`, `VERDICT_RECORDED_COST`; existing `Panel` (`ui/layout`), `PanelHeader`, `PanelError`, `EmptyStateComponent`, `PaginationComponent` (`ui/pagination`), `createClientPage` (`ui/data-table/client-page`), `tablePerPage` (`ui/table-per-page`), `reasonLabel` (`workspaces/trades/exit-reasons`).
- Produces:
  - `OverrideFidelityPanel` (selector `sb-override-fidelity-panel`; cards `<li class="card">` in `<ul class="cards">`; caption element `p.caption`; net-effect tile `.tiles > .net` with `data-tone`; badge tile `.badge` with `data-tone` and text in `.badge-text`). V173-15 checks it at three widths.
  - In `override-fidelity.model.ts`: `CAPTION`, `EMPTY_COPY`, `APPROX_LABEL`, `COUNTS_HINT`, `STATUS_LABEL: Record<OverrideStatus, string>`, `plural(n: number, one: string, many: string): string`, `signedUsd(x: number | null, currency: string): string`, `signedR(x: number | null): string`, `netEffect(summary: OverrideSummary, currency: string): string`, `netTone(verdict: OverrideVerdict, summary: OverrideSummary): Tone`, `badgeCopy(verdict: OverrideVerdict, currency: string): string`, `badgeTone(verdict: OverrideVerdict): Tone`, `waitingOnLine(verdict: OverrideVerdict): string | null`, `recordedLine(verdict: OverrideVerdict): string | null`, `liveHint(verdict: OverrideVerdict): string | null`, `exclusionNotes(summary: OverrideSummary, verdict: OverrideVerdict): string[]`, `isCounted(row: OverrideRowDto): boolean`, with `type Tone = 'pos' | 'neg' | 'neutral'`.
  - **Deviation from the ledger row:** `badgeCopy` takes `(verdict, currency)`, not `(verdict, summary, currency)`: since 2026-10-19 the COST/SAVED figures are the recorded `verdict.sum_delta_usd`/`verdict.sum_delta_r`, so the summary is no longer read. No other task calls it (V173-15 reads the DOM).

**Copy.** Every string in the index's **UI copy (verbatim)** is used as written: the title, tile order and `counts ignore size` hint, the four WAITING/COST/SAVED/INCONCLUSIVE badge forms, the `Waiting on:` line and its three items, the recorded verdict line, the `live, may have moved since recorded on <recorded_on>` tile hint, the caption (now with `Dollars use the plan's modelled position size.`), every exclusion note in its count-1 and count-many form, the `STATUS_LABEL` entries `unstamped` and `split or dividend adjusted`, the approx label and the empty state. `plural(n, one, many)` is `${n} ${n === 1 ? one : many}`, and each note's verb agrees with its count. The rest of the panel's wording is this plan's own and must be shown to the partner at review (§ Handoff): the tile labels `Net effect vs engine` and `Verdict`, the header hint, the card prefixes `Engine exit:` and `Status:`, the ` · bulk clear` status suffix, the other `STATUS_LABEL` entries (`still open`, `stale data`, `ambiguous`, `replay mismatch`, `unreplayable`), and a COST/SAVED badge that drops `$X (…)` to `Y R` alone when the stored record has no dollar sum (`sum_delta_usd: null`).

**Which figures are recorded, which live.** Once `verdict.recorded` is true the badge and the recorded line show the stored figures (`n`, `weeks`, mean, CI, Σ, `bar_close_n`, `recorded_on`); the net-effect and `Overrides counted` tiles keep showing the live summary and carry the `live, may have moved since recorded on …` hint, so a reader never takes a live sum for the frozen one. While `WAITING`, the net-effect tile is neutral-toned whatever its sign: no colour suggests a conclusion before one is recorded. Once recorded, it is toned by the live sum's sign (`pos` above 0, `neg` below).

**Layout per device class** (`ui-design.md`; media queries only at the declared breakpoints 639/640/1023/1024):

- **Desktop (≥ 1024px):** four tiles in one row; the waiting-on or recorded line, the caption and the notes below them; the row table below, Δ cells right-aligned, tabular figures.
- **Tablet (640–1023px):** tiles two per row; the same table inside `.table-wrap` (`overflow-x: auto`), so a narrow viewport scrolls the table box, never the page.
- **Phone (< 640px):** tiles two per row; tile values and the badge text wrap and never truncate (`overflow-wrap: break-word`, no `text-overflow`, no fixed heights); the table is hidden and each row is a card: the lead line is ticker, close date and Δ ($ and R), then secondary lines for engine exit and status, and the estimate label on approx rows.
- **Caption legibility:** `p.caption` at `var(--text-body)` (the panel's body size, never `--text-micro`), `line-height: 1.5`, colour `var(--text-secondary)`, full width under the tiles, no clamp or ellipsis; the notes, the waiting-on and the recorded lines at `var(--text-table)` in `var(--text-secondary)`. V173-15 asserts the caption visible and unclipped at 390px.
- **Pager:** client-paged with `tablePerPage('override-fidelity')` (default 10 desktop, 5 tablet/phone, saved per device class); no pager at 5 rows or fewer. The pager's controls and the retry button are the panel's only touch targets, both at least 44px (`sb-pagination`/`sb-panel-error` already are). Cards are not interactive.
- Rows that are not counted (bulk, approx, or a status other than `resolved`) are dimmed, shown and never summed.

- [ ] **Step 1: Write the failing model test**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  APPROX_LABEL, CAPTION, COUNTS_HINT, EMPTY_COPY, STATUS_LABEL, badgeCopy, badgeTone,
  exclusionNotes, isCounted, liveHint, netEffect, netTone, plural, recordedLine, signedR,
  signedUsd, waitingOnLine,
} from './override-fidelity.model';
import {
  OVERRIDE_FIDELITY_FIXTURE, VERDICT_FLOORS_MET, VERDICT_RECORDED_COST, VERDICT_WAITING_ON,
} from './override-fidelity.fixture';

const F = OVERRIDE_FIDELITY_FIXTURE;
const M = '\u2212';                              // the true minus the formatters print

describe('override-fidelity model', () => {
  it('pluralises a count of one and of many', () => {
    expect(plural(1, 'row', 'rows')).toBe('1 row');
    expect(plural(0, 'row', 'rows')).toBe('0 rows');
    expect(plural(15, 'close', 'closes')).toBe('15 closes');
  });

  it('signs dollars and R with a true minus, and prints a dash for none', () => {
    expect(signedUsd(59.35, '$')).toBe('+$59.35');
    expect(signedUsd(-1234.5, '€')).toBe(`${M}€1,234.50`);
    expect(signedUsd(0, '$')).toBe('$0.00');
    expect(signedUsd(null, '$')).toBe('—');
    expect(signedR(1.187)).toBe('+1.19 R');
    expect(signedR(-0.3)).toBe(`${M}0.30 R`);
    expect(signedR(null)).toBe('—');
  });

  it('leads the net effect with dollars, then R', () => {
    expect(netEffect(F.summary, '$')).toBe('+$59.35 · +1.19 R');
  });

  it('keeps the net-effect tile neutral while WAITING, whatever its sign', () => {
    expect(F.summary.sum_delta_r).toBeGreaterThan(0);
    expect(netTone(F.verdict, F.summary)).toBe('neutral');
    expect(netTone(VERDICT_FLOORS_MET, F.summary)).toBe('neutral');
    expect(netTone(VERDICT_RECORDED_COST, F.summary)).toBe('pos');               // live sum > 0
    expect(netTone(VERDICT_RECORDED_COST, { ...F.summary, sum_delta_r: -2.4 })).toBe('neg');
    expect(netTone(VERDICT_RECORDED_COST, { ...F.summary, sum_delta_r: 0 })).toBe('neutral');
  });

  it('words WAITING below the count floor as "N of 30 needed"', () => {
    expect(badgeCopy(F.verdict, '$')).toBe('1 of 30 needed. No conclusion yet.');
    expect(waitingOnLine(F.verdict)).toBeNull();                 // the count is the reason
  });

  it('words a met count with other floors failing as waiting on other conditions', () => {
    expect(badgeCopy(VERDICT_WAITING_ON, '$'))
      .toBe('34 of 30 counted. Waiting on other conditions. No conclusion yet.');
    expect(waitingOnLine(VERDICT_WAITING_ON)).toBe('Waiting on: at least 10 distinct weeks '
      + '(now 8); no open rows (now 2 open); left-out rows at most 20% (now 25%)');
    expect(waitingOnLine({ ...VERDICT_WAITING_ON, weeks: 11, excluded_share: 0.1, open_n: 1,
      waiting_on: ['open'] })).toBe('Waiting on: no open rows (now 1 open)');
  });

  it('words floors met but not yet recorded without a target or an action', () => {
    expect(badgeCopy(VERDICT_FLOORS_MET, '$'))
      .toBe('Floors met (34 of 30). Awaiting the one recorded evaluation. No conclusion yet.');
    expect(waitingOnLine(VERDICT_FLOORS_MET)).toBeNull();
    expect(recordedLine(VERDICT_FLOORS_MET)).toBeNull();
    expect(liveHint(VERDICT_FLOORS_MET)).toBeNull();
  });

  it('words a recorded verdict from the recorded figures', () => {
    expect(badgeCopy(VERDICT_RECORDED_COST, '$'))
      .toBe('Your overrides cost $1,364.00 (6.82 R) vs the engine');
    expect(badgeCopy({ ...VERDICT_RECORDED_COST, state: 'SAVED', sum_delta_usd: 59.35,
      sum_delta_r: 1.187 }, '$')).toBe('Your overrides saved $59.35 (1.19 R) vs the engine');
    expect(badgeCopy({ ...VERDICT_RECORDED_COST, state: 'INCONCLUSIVE' }, '$'))
      .toBe('No clear difference vs the engine');
    expect(badgeCopy({ ...VERDICT_RECORDED_COST, sum_delta_usd: null }, '$'))
      .toBe('Your overrides cost 6.82 R vs the engine');
    expect(waitingOnLine(VERDICT_RECORDED_COST)).toBeNull();
  });

  it('writes the recorded line, with the bar-close count pluralised', () => {
    const head = `Recorded on 2026-12-04 from 31 overrides over 12 weeks: mean ${M}0.22 R per `
      + `override, 95% CI ${M}0.24 to ${M}0.20 R. Before costs: ${M}0.20 R.`;
    expect(recordedLine(VERDICT_RECORDED_COST))
      .toBe(`${head} 2 overrides priced from a bar close, not a quote.`);
    expect(recordedLine({ ...VERDICT_RECORDED_COST, bar_close_n: 1 }))
      .toBe(`${head} 1 override priced from a bar close, not a quote.`);
    expect(recordedLine({ ...VERDICT_RECORDED_COST, bar_close_n: 0 })).toBe(head);
    expect(recordedLine(F.verdict)).toBeNull();
  });

  it('labels the live tiles once a verdict is recorded', () => {
    expect(liveHint(VERDICT_RECORDED_COST)).toBe('live, may have moved since recorded on 2026-12-04');
    expect(liveHint(F.verdict)).toBeNull();
  });

  it('tones only a recorded direction on the badge', () => {
    expect(badgeTone(F.verdict)).toBe('neutral');
    expect(badgeTone(VERDICT_FLOORS_MET)).toBe('neutral');
    expect(badgeTone(VERDICT_RECORDED_COST)).toBe('neg');
    expect(badgeTone({ ...VERDICT_RECORDED_COST, state: 'SAVED' })).toBe('pos');
    expect(badgeTone({ ...VERDICT_RECORDED_COST, state: 'INCONCLUSIVE' })).toBe('neutral');
  });

  it('writes one exclusion note per non-zero count, singular for one', () => {
    expect(exclusionNotes(F.summary, F.verdict)).toEqual([
      '1 close from one bulk clear on 2026-09-30 is not a decision, so it is left out',
      '1 estimated row is shown but not counted',
      '1 stale data row is left out',
    ]);
    expect(exclusionNotes(F.summary, { ...F.verdict, open_n: 1 })).toContain(
      '1 row is still open and not counted yet. No conclusion is recorded while any are open.');
  });

  it('writes the plural forms, in the order bulk, estimated, open, then statuses', () => {
    const many = { ...F.summary, bulk_dates: { '2026-09-30': 15 }, approx_n: 3,
      n_by_status: { ...F.summary.n_by_status, open: 2, unstamped: 1, stale: 2, split_affected: 2 } };
    expect(exclusionNotes(many, { ...F.verdict, open_n: 2 })).toEqual([
      '15 closes from one bulk clear on 2026-09-30 are not decisions, so they are left out',
      '3 estimated rows are shown but not counted',
      '2 rows are still open and not counted yet. No conclusion is recorded while any are open.',
      '1 unstamped row is left out',
      '2 stale data rows are left out',
      '2 split or dividend adjusted rows are left out',
    ]);
    const quiet = { ...F.summary, bulk_dates: {}, approx_n: 0,
      n_by_status: { ...F.summary.n_by_status, stale: 0 } };
    expect(exclusionNotes(quiet, F.verdict)).toEqual([]);
  });

  it('counts only individual, stamped, resolved rows', () => {
    expect(F.rows.map(isCounted)).toEqual([true, false, false, false]);
  });

  it('keeps the fixed copy verbatim', () => {
    expect(CAPTION).toBe('Compares the overrides you made with what the engine would have done. '
      + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
      + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
      + "and before tax. Dollars use the plan's modelled position size. Closing early can also "
      + 'change the tax holding period. There is no target number of overrides.');
    expect(EMPTY_COPY).toBe('No manual overrides in scope.');
    expect(APPROX_LABEL).toBe('estimated exit: daily close, not your fill');
    expect(COUNTS_HINT).toBe('counts ignore size');
    expect(STATUS_LABEL.unstamped).toBe('unstamped');
    expect(STATUS_LABEL.split_affected).toBe('split or dividend adjusted');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
```

Expected: FAIL, cannot resolve `./override-fidelity.model`.

- [ ] **Step 3: Write the model**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts`. The constants are fixed copy, so they are given whole:

```ts
import {
  OverrideRowDto, OverrideStatus, OverrideSummary, OverrideVerdict, OverrideWaitingOn,
} from '../../../api/models';

/* v173 — copy and formatting for "Overrides vs engine". Every figure is
 * computed server-side; these helpers only word it. The copy is frozen by
 * the spec (§5 and its plan panel review): scoped to overrides already
 * made, never a policy, and no conclusion before one is recorded. */

export type Tone = 'pos' | 'neg' | 'neutral';

export const CAPTION = 'Compares the overrides you made with what the engine would have done. '
  + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
  + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
  + "and before tax. Dollars use the plan's modelled position size. Closing early can also "
  + 'change the tax holding period. There is no target number of overrides.';
export const EMPTY_COPY = 'No manual overrides in scope.';
export const APPROX_LABEL = 'estimated exit: daily close, not your fill';
export const COUNTS_HINT = 'counts ignore size';

/** Lower-case: each label also sits inside an exclusion sentence. */
export const STATUS_LABEL: Record<OverrideStatus, string> = {
  resolved: 'resolved', open: 'still open', unstamped: 'unstamped', stale: 'stale data',
  ambiguous: 'ambiguous', parity_mismatch: 'replay mismatch',
  split_affected: 'split or dividend adjusted', unreplayable: 'unreplayable',
};

/** The excluded statuses after `open`, in the order their notes are printed. */
const LEFT_OUT: OverrideStatus[] =
  ['unstamped', 'stale', 'ambiguous', 'parity_mismatch', 'split_affected', 'unreplayable'];

/** The `Waiting on:` items; `count` is never listed (the badge already says it). */
const WAITING_ITEM: Record<Exclude<OverrideWaitingOn, 'count'>, (v: OverrideVerdict) => string> = {
  weeks: (v) => `at least ${v.week_floor} distinct weeks (now ${v.weeks})`,
  open: (v) => `no open rows (now ${v.open_n} open)`,
  excluded: (v) => `left-out rows at most 20% (now ${Math.round(v.excluded_share * 100)}%)`,
};
```

Then the functions, each a few lines (behaviour pinned by Step 1; keep every one well under complexity 15):

- `MINUS = '\u2212'` (negatives line up with positives in tabular figures); `sign(x)` gives `+`, `MINUS` or `''` for zero; `known(x)` is `x !== null && Number.isFinite(x)`; `magnitude(x, currency)` is `currency` + `Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })`; `fixed2(x)` is the signed `Math.abs(x).toFixed(2)` with `sign`, or `—` when not `known` (used by the recorded line).
- `plural(n, one, many)` = `` `${n} ${n === 1 ? one : many}` ``. A local `be(n)` gives `'is'`/`'are'` for the notes' verb agreement.
- `signedUsd(x, currency)` = `sign + magnitude`, or `—`; `signedR(x)` = `sign + abs.toFixed(2) + ' R'`, or `—`.
- `netEffect(summary, currency)` = `` `${signedUsd(summary.sum_delta_usd, currency)} · ${signedR(summary.sum_delta_r)}` ``.
- `netTone(verdict, summary)`: `'neutral'` while `verdict.state === 'WAITING'`; otherwise `'pos'` / `'neg'` / `'neutral'` by the sign of `summary.sum_delta_r`.
- `badgeCopy(verdict, currency)`: the amount is `` `${magnitude(verdict.sum_delta_usd, currency)} (${Math.abs(verdict.sum_delta_r ?? 0).toFixed(2)} R)` `` when `sum_delta_usd` is known, else `` `${Math.abs(verdict.sum_delta_r ?? 0).toFixed(2)} R` ``; `COST` → `` `Your overrides cost ${amount} vs the engine` ``; `SAVED` → `` `Your overrides saved ${amount} vs the engine` ``; `INCONCLUSIVE` → `'No clear difference vs the engine'`; `WAITING` → (evaluable) `` `Floors met (${n} of ${needed}). Awaiting the one recorded evaluation. No conclusion yet.` ``, else (`n >= needed`) `` `${n} of ${needed} counted. Waiting on other conditions. No conclusion yet.` ``, else `` `${n} of ${needed} needed. No conclusion yet.` ``.
- `badgeTone(verdict)`: `COST` → `'neg'`, `SAVED` → `'pos'`, else `'neutral'`.
- `waitingOnLine(verdict)`: `null` unless `state === 'WAITING'`, not `evaluable`, and `n >= needed`; the items are `verdict.waiting_on` without `'count'`, mapped through `WAITING_ITEM` in the order given; `null` when none remain; else `` `Waiting on: ${items.join('; ')}` ``.
- `recordedLine(verdict)`: `null` unless `recorded`; else `` `Recorded on ${recorded_on} from ${n} overrides over ${weeks} weeks: mean ${fixed2(mean_delta_r)} R per override, 95% CI ${fixed2(lo)} to ${fixed2(hi)} R. Before costs: ${fixed2(mean_delta_r_gross)} R.` `` with `[lo, hi] = verdict.ci ?? [null, null]`, plus `` ` ${plural(bar_close_n, 'override', 'overrides')} priced from a bar close, not a quote.` `` when `bar_close_n > 0`.
- `liveHint(verdict)`: `` `live, may have moved since recorded on ${recorded_on}` `` when `recorded`, else `null`.
- `exclusionNotes(summary, verdict)`: in this order, one line per non-zero count, each count through `plural` with its verb from `be(n)`:
  - per `bulk_dates` entry: `` `${plural(n, 'close', 'closes')} from one bulk clear on ${day} ${n === 1 ? 'is not a decision, so it is' : 'are not decisions, so they are'} left out` ``;
  - `approx_n`: `` `${plural(n, 'estimated row', 'estimated rows')} ${be(n)} shown but not counted` ``;
  - `verdict.open_n`: `` `${plural(n, 'row', 'rows')} ${be(n)} still open and not counted yet. No conclusion is recorded while any are open.` ``;
  - each status in `LEFT_OUT` with `summary.n_by_status[s] > 0`: `` `${plural(n, `${STATUS_LABEL[s]} row`, `${STATUS_LABEL[s]} rows`)} ${be(n)} left out` ``.
  `n_by_status` counts eligible rows only, so no row appears in two notes; the open count is read from `verdict.open_n` (the same eligible rows, always live).
- `isCounted(row)` = `!row.bulk && !row.approx && row.status === 'resolved'`.

- [ ] **Step 4: Run the model test to verify it passes**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
```

Expected: PASS. Never loosen a copy assertion to make it pass: the strings are frozen by the spec, so a mismatch is a model bug.

- [ ] **Step 5: Write the failing panel test**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { OverrideFidelity } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverrideFidelityPanel } from './override-fidelity-panel';
import { APPROX_LABEL, CAPTION } from './override-fidelity.model';
import {
  OVERRIDE_FIDELITY_FIXTURE, VERDICT_FLOORS_MET, VERDICT_RECORDED_COST, VERDICT_WAITING_ON,
  overrideFixture,
} from './override-fidelity.fixture';

function render(payload: OverrideFidelity | null, error: string | null = null) {
  const reloads: string[] = [];
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { overrideFidelity: signal(payload),
        overrideFidelityError: signal(error), reload: (k: string) => reloads.push(k) } },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
    ],
  });
  const fixture = TestBed.createComponent(OverrideFidelityPanel);
  fixture.detectChanges();
  return { el: fixture.nativeElement as HTMLElement, reloads };
}

const text = (el: Element | null): string => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
const tone = (el: HTMLElement, selector: string): string | null =>
  el.querySelector(selector)?.getAttribute('data-tone') ?? null;

describe('OverrideFidelityPanel', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('leads with net dollars and R, then counted, helped/hurt/neutral, the badge', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const tiles = [...el.querySelectorAll('.tiles > div')].map((t) => text(t.querySelector('dt')));
    expect(tiles).toEqual(['Net effect vs engine', 'Overrides counted', 'Helped / hurt / neutral', 'Verdict']);
    expect(text(el.querySelector('.tiles > .net dd'))).toBe('+$59.35 · +1.19 R');
    expect(text(el.querySelector('.tiles'))).toContain('counts ignore size');
    expect(text(el.querySelector('.badge-text'))).toBe('1 of 30 needed. No conclusion yet.');
    expect(text(el.querySelector('h2'))).toBe('Overrides vs engine');
  });

  it('keeps the net-effect tile neutral while WAITING and shows no recorded figures', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);           // live sum is positive
    expect(tone(el, '.tiles > .net')).toBe('neutral');
    expect(tone(el, '.badge')).toBe('neutral');
    expect(el.querySelectorAll('.live').length).toBe(0);
    expect(el.querySelector('.recorded')).toBeNull();
    expect(el.querySelector('.waiting-on')).toBeNull();
  });

  it('says what it is waiting on once the count is met', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_WAITING_ON }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('34 of 30 counted. Waiting on other conditions. No conclusion yet.');
    expect(text(el.querySelector('.waiting-on'))).toBe('Waiting on: at least 10 distinct weeks '
      + '(now 8); no open rows (now 2 open); left-out rows at most 20% (now 25%)');
  });

  it('says the floors are met without claiming a result', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_FLOORS_MET }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('Floors met (34 of 30). Awaiting the one recorded evaluation. No conclusion yet.');
    expect(el.querySelector('.waiting-on')).toBeNull();
    expect(tone(el, '.tiles > .net')).toBe('neutral');
  });

  it('shows a recorded verdict from the record and labels the live tiles', () => {
    const { el } = render(overrideFixture({ verdict: VERDICT_RECORDED_COST }));
    expect(text(el.querySelector('.badge-text')))
      .toBe('Your overrides cost $1,364.00 (6.82 R) vs the engine');
    expect(tone(el, '.badge')).toBe('neg');
    expect(tone(el, '.tiles > .net')).toBe('pos');              // the live sum, labelled live
    expect([...el.querySelectorAll('.tiles .live')].map(text)).toEqual([
      'live, may have moved since recorded on 2026-12-04',
      'live, may have moved since recorded on 2026-12-04',
    ]);
    expect(text(el.querySelector('.recorded'))).toContain('Recorded on 2026-12-04 from 31 overrides over 12 weeks');
    expect(text(el.querySelector('.recorded'))).toContain('2 overrides priced from a bar close, not a quote.');
  });

  it('prints the fixed caption legibly and one note per exclusion, singular for one', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    expect(text(el.querySelector('p.caption'))).toBe(CAPTION);
    expect([...el.querySelectorAll('.note')].map(text)).toEqual([
      '1 close from one bulk clear on 2026-09-30 is not a decision, so it is left out',
      '1 estimated row is shown but not counted',
      '1 stale data row is left out',
    ]);
  });

  it('labels the estimated row beside its delta, in the table and the card', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const rows = el.querySelectorAll('table.rows tbody tr');
    expect(rows.length).toBe(4);
    expect(text(rows[1].querySelector('td.delta'))).toContain(APPROX_LABEL);
    expect(text(rows[0].querySelector('td.delta'))).not.toContain(APPROX_LABEL);
    expect(rows[1].classList.contains('excluded')).toBe(true);
    expect([...el.querySelectorAll('table.rows th')].map(text)).toEqual(
      ['Close date', 'Ticker', 'Horizon', 'State at close', 'Actual', 'Engine', 'Δ', 'Engine exit', 'Status']);
  });

  it('builds one card per row, leading with ticker, close date and delta in $ and R', () => {
    const { el } = render(OVERRIDE_FIDELITY_FIXTURE);
    const cards = el.querySelectorAll('ul.cards > li.card');
    expect(cards.length).toBe(4);
    const lead = text(cards[0].querySelector('.lead'));
    expect(lead.indexOf('AAA')).toBeLessThan(lead.indexOf('2026-10-07'));
    expect(lead).toContain('+$59.35 · +1.19 R');
    expect([...cards[1].querySelectorAll('.sub')].map(text)).toContain(APPROX_LABEL);
    expect(text(cards[2])).toContain('bulk clear');
  });

  it('pages only past five rows', () => {
    expect(render(OVERRIDE_FIDELITY_FIXTURE).el.querySelector('sb-pagination')).toBeNull();
    TestBed.resetTestingModule();
    const six = Array.from({ length: 6 }, (_, i) => ({ ...OVERRIDE_FIDELITY_FIXTURE.rows[0], plan_id: `r${i}` }));
    expect(render(overrideFixture({ rows: six })).el.querySelector('sb-pagination')).not.toBeNull();
  });

  it('says so plainly when there are no overrides', () => {
    const { el } = render(overrideFixture({ rows: [] }));
    expect(text(el)).toContain('No manual overrides in scope.');
    expect(el.querySelector('.tiles')).toBeNull();
  });

  it('keeps its own error and retries only itself', () => {
    const { el, reloads } = render(null, 'boom');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    (el.querySelector('sb-panel-error button') as HTMLButtonElement | null)?.click();
    expect(reloads).toEqual(['overrideFidelity']);
  });
});

describe('override-fidelity-panel.ts styles', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/analytics/tabs/override-fidelity-panel.ts'), 'utf8');

  it('uses only declared breakpoint values in width queries', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('sets the caption at body size in the secondary text colour, never clipped', () => {
    const rule = src.match(/\.caption\{([^}]*)\}/)?.[1] ?? '';
    expect(rule).toContain('font-size:var(--text-body)');
    expect(rule).toContain('color:var(--text-secondary)');
    expect(rule).not.toMatch(/text-overflow|line-clamp|max-height|white-space:nowrap/);
  });

  it('never truncates the badge text', () => {
    expect(src).not.toMatch(/text-overflow:\s*ellipsis/);
  });
});
```

If `sb-panel-error`'s retry button has a different selector, read `ui/panel-error.ts` and use its button; keep the assertion that only `'overrideFidelity'` is reloaded.

- [ ] **Step 6: Write the panel**

Create `$WT/frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { OverrideRowDto } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { createClientPage } from '../../../ui/data-table/client-page';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Panel } from '../../../ui/layout';
import { PaginationComponent } from '../../../ui/pagination';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { tablePerPage } from '../../../ui/table-per-page';
import { reasonLabel } from '../../trades/exit-reasons';
import {
  APPROX_LABEL, CAPTION, COUNTS_HINT, EMPTY_COPY, STATUS_LABEL, badgeCopy, badgeTone, exclusionNotes,
  isCounted, liveHint, netEffect, netTone, recordedLine, signedR, signedUsd, waitingOnLine,
} from './override-fidelity.model';

/* v173 — manual overrides vs the engine left alone. Descriptive until the
 * frozen verdict is recorded; the badge shows that recorded verdict or WAITING. */
@Component({
  selector: 'sb-override-fidelity-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, EmptyStateComponent, PaginationComponent],
  template: `
    <sb-panel><sb-panel-header title="Overrides vs engine" [n]="data()?.summary?.counted_n ?? null"
      hint="Each manual close replayed through the engine from its real fill. Δ is your exit minus the engine's, in dollars and R." />
      @if (store.overrideFidelityError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('overrideFidelity')" />
      } @else if (data(); as d) {
        @if (!d.rows.length) { <sb-empty-state [title]="emptyCopy" reason="measured-zero" /> }
        @else {
          <dl class="tiles">
            <div class="net" [attr.data-tone]="netToneValue()"><dt>Net effect vs engine</dt><dd>{{ net() }}</dd>@if (hint(); as h) { <small class="live">{{ h }}</small> }</div>
            <div><dt>Overrides counted</dt><dd>{{ d.summary.counted_n }}</dd>@if (hint(); as h) { <small class="live">{{ h }}</small> }</div>
            <div><dt>Helped / hurt / neutral</dt><dd>{{ d.summary.helped }} / {{ d.summary.hurt }} / {{ d.summary.neutral }}</dd><small>{{ countsHint }}</small></div>
            <div class="badge" [attr.data-tone]="tone()"><dt>Verdict</dt><dd class="badge-text">{{ badge() }}</dd></div>
          </dl>
          @if (waitingOn(); as line) { <p class="waiting-on">{{ line }}</p> }
          @if (recorded(); as line) { <p class="recorded">{{ line }}</p> }
          <p class="caption">{{ caption }}</p>
          @for (note of notes(); track note) { <p class="note">{{ note }}</p> }
          <div class="table-wrap"><table class="rows">
            <thead><tr><th>Close date</th><th>Ticker</th><th>Horizon</th><th>State at close</th><th class="num">Actual</th><th class="num">Engine</th><th class="num">Δ</th><th>Engine exit</th><th>Status</th></tr></thead>
            <tbody>@for (r of page.visible(); track r.plan_id) {
              <tr [class.excluded]="!counted(r)">
                <td>{{ r.close_date ?? '—' }}</td><td>{{ r.ticker }}</td><td>{{ r.horizon }}</td><td>{{ r.state_at_close }}</td>
                <td class="num">{{ pair(r.actual_usd, r.actual_r) }}</td><td class="num">{{ pair(r.engine_usd, r.engine_r) }}</td>
                <td class="num delta">{{ pair(r.delta_usd, r.delta_r) }}@if (r.approx) { <small class="approx">{{ approxLabel }}</small> }</td>
                <td>{{ exit(r) }}</td><td>{{ status(r) }}</td>
              </tr>
            }</tbody>
          </table></div>
          <ul class="cards">@for (r of page.visible(); track r.plan_id) {
            <li class="card" [class.excluded]="!counted(r)">
              <div class="lead"><strong>{{ r.ticker }}</strong><span>{{ r.close_date ?? '—' }}</span><span class="num">{{ pair(r.delta_usd, r.delta_r) }}</span></div>
              <div class="sub">Engine exit: {{ exit(r) }}</div><div class="sub">Status: {{ status(r) }}</div>
              @if (r.approx) { <div class="sub approx">{{ approxLabel }}</div> }
            </li>
          }</ul>
          @if (d.rows.length > 5) {
            <sb-pagination [pagination]="page.pageSpec()" [showPerPage]="true" [announce]="true"
              (pageChange)="page.setPage($event)" (perPageChange)="perPage.set($event)" />
          }
        }
      }
    </sb-panel>
  `,
  styles: `.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-10);margin:0}.tiles>div{min-width:0;padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}dt{font-size:var(--text-micro);text-transform:uppercase;letter-spacing:.1em;color:var(--text-faint)}dd{margin:var(--space-4) 0;color:var(--text);font-variant-numeric:tabular-nums;white-space:normal;overflow-wrap:break-word}small{display:block;font-size:var(--text-micro);color:var(--text-faint)}.net[data-tone=pos] dd,.badge[data-tone=pos] .badge-text{color:var(--pos)}.net[data-tone=neg] dd,.badge[data-tone=neg] .badge-text{color:var(--neg)}.caption{margin:var(--space-10) 0 0;font-size:var(--text-body);line-height:1.5;color:var(--text-secondary)}.note,.waiting-on,.recorded{margin:var(--space-8) 0 0;font-size:var(--text-table);color:var(--text-secondary)}.table-wrap{overflow-x:auto;margin-top:var(--space-10)}.rows{width:100%;border-collapse:collapse;font-size:var(--text-table)}.rows th,.rows td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border)}.rows .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.excluded,.excluded td{color:var(--text-faint)}.approx{display:block;color:var(--warn);white-space:normal}.cards{display:none;list-style:none;margin:var(--space-10) 0 0;padding:0;gap:var(--space-8)}.cards li{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}.lead{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-6) var(--space-10)}.lead .num{margin-left:auto;font-variant-numeric:tabular-nums}.sub{font-size:var(--text-micro);color:var(--text-secondary)}@media(max-width:1023px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){.table-wrap{display:none}.cards{display:grid}}`,
})
export class OverrideFidelityPanel {
  readonly store = inject(AnalyticsStore);
  readonly data = computed(() => this.store.overrideFidelity());
  readonly perPage = tablePerPage('override-fidelity');
  readonly page = createClientPage<OverrideRowDto>(() => this.data()?.rows ?? [], () => this.perPage.value());
  readonly caption = CAPTION;
  readonly emptyCopy = EMPTY_COPY;
  readonly approxLabel = APPROX_LABEL;
  readonly countsHint = COUNTS_HINT;
  readonly counted = isCounted;

  private readonly currency = computed(() => this.data()?.currency_symbol ?? '');
  readonly net = computed(() => { const d = this.data(); return d ? netEffect(d.summary, this.currency()) : ''; });
  readonly netToneValue = computed(() => { const d = this.data(); return d ? netTone(d.verdict, d.summary) : 'neutral'; });
  readonly badge = computed(() => { const d = this.data(); return d ? badgeCopy(d.verdict, this.currency()) : ''; });
  readonly tone = computed(() => { const d = this.data(); return d ? badgeTone(d.verdict) : 'neutral'; });
  readonly waitingOn = computed(() => { const d = this.data(); return d ? waitingOnLine(d.verdict) : null; });
  readonly recorded = computed(() => { const d = this.data(); return d ? recordedLine(d.verdict) : null; });
  readonly hint = computed(() => { const d = this.data(); return d ? liveHint(d.verdict) : null; });
  readonly notes = computed(() => { const d = this.data(); return d ? exclusionNotes(d.summary, d.verdict) : []; });

  /** Every R figure carries its signed dollars beside it (the v170 convention). */
  pair(usd: number | null, r: number | null): string {
    return `${signedUsd(usd, this.currency())} · ${signedR(r)}`;
  }

  exit(r: OverrideRowDto): string {
    return reasonLabel(r.engine_exit_reason) ?? '—';
  }

  status(r: OverrideRowDto): string {
    return r.bulk ? `${STATUS_LABEL[r.status]} · bulk clear` : STATUS_LABEL[r.status];
  }
}
```

The two `.live` hints sit inside the net-effect and `Overrides counted` tiles only; the helped/hurt tile keeps its `counts ignore size` hint. The waiting-on and recorded lines sit under the tiles at full width, so a long line never squeezes the badge tile. If `PaginationComponent`'s inputs differ from the ones `tuning.ts:214` uses (`pagination`, `showPerPage`, `announce`, `pageChange`, `perPageChange`), follow `tuning.ts`.

- [ ] **Step 7: Mount it on the Execution tab**

In `$WT/frontend/src/app/workspaces/analytics/tabs/execution.ts`: add `import { OverrideFidelityPanel } from './override-fidelity-panel';`, add `OverrideFidelityPanel` to the component's `imports: [...]`, and insert `<sb-override-fidelity-panel />` on its own line between the closing `</sb-panel>` of "Execution verdict" and `<div class="panels">`. It sits full width, after the verdict tiles and before the charts: it is a second verdict, on the human's exits.

In `$WT/frontend/src/app/workspaces/analytics/tabs/execution.spec.ts`:

1. Add `import { OVERRIDE_FIDELITY_FIXTURE } from './override-fidelity.fixture';`.
2. In `render()`'s `AnalyticsStore` stub add `overrideFidelity: signal(OVERRIDE_FIDELITY_FIXTURE), overrideFidelityError: signal(null),`, and give the `PreferencesStore` stub `update: () => {}` beside `values`.
3. Add inside `describe('ExecutionTab', ...)`:

```ts
  it('mounts Overrides vs engine full width after the verdict, before the charts', () => { const { el } = render(); const panel = el.querySelector('sb-override-fidelity-panel')!; expect(panel).not.toBeNull(); expect(panel.parentElement?.classList.contains('panels')).toBe(false); expect(el.querySelector('.verdict')!.compareDocumentPosition(panel)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); expect(panel.compareDocumentPosition(el.querySelector('sb-histogram')!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); });
```

(One line, matching the file's dense style.)

- [ ] **Step 8: Run the three specs**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/execution.spec.ts
```

Expected: all PASS. Never loosen a copy assertion to make one pass: the strings are frozen by the spec, so a mismatch is a template bug.

- [ ] **Step 9: Type-check the app build**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/frontend exec -- ng build --configuration development
```

Expected: the build succeeds with no new errors or warnings in the four files. The real three-width check (390, 768, 1280px; caption visible and unclipped at 390px; net-effect tile untinted while WAITING) runs in V173-15.

- [ ] **Step 10: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity.model.spec.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.ts frontend/src/app/workspaces/analytics/tabs/override-fidelity-panel.spec.ts frontend/src/app/workspaces/analytics/tabs/execution.ts frontend/src/app/workspaces/analytics/tabs/execution.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(ui): Overrides vs engine panel on the Execution tab (v173)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits. At review, show the partner the writer's own copy listed under **Copy** above.
