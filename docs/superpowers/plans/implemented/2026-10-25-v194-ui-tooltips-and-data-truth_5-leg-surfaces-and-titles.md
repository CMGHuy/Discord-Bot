# v194 — UI integrity: tooltips that open, figures that are true — Part 5: leg surfaces and title conversions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md)
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, Parallelisation and the task ledger live there; every task below inherits them.

# Phase 5 — B3 surfaces and A3 title conversions

### Task V194-13: B3 surfaces — leg label and hint on Trades (table, compact rows, drawer) and the Dashboard; Trades total stated as rows; missing-FX-rate caveat on Trades and Dashboard

**Model:** sonnet — template and pure-helper wiring across two pages against contracts V194-12 and V194-6c already fixed; no design choice left open.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts:143` (the `num` column) and its imports
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (imports `:40-51`, component `imports` array, `#numCell` `:381-398`, count line `:376-378`, expansion `Detail` group `:497-509`, styles `:558-563`, `announce` `:850-854`, `countText` `:868-878`, `isPartialLeg` `:962-972`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (imports `:33`, `.performance-stack` `:201-224`, `#numCell` `:387-404`, styles `:579`, `isPartialLeg` `:983-992`)
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts` (imports `:1-11`, `tradeDrawerFields` `:76-91`, template `:113-119`, component `imports` `:106`)
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes (V194-12, `frontend/src/app/workspaces/trades/leg-label.ts`): `legLabel(row: LegLike): string | null` (`"Leg N of M"`, `" · <reasonLabel>"` appended when a reason is present, `null` for a single-leg row) and `LEG_HINT_TEXT`; `TradeRow.leg_exit_reason?: string | null`.
- Consumes (V194-6c): `TradeRow.fx_missing?: boolean`; `Dashboard.fx_missing_count?: number`; `fxMissingText(n: number): string` from `frontend/src/app/workspaces/analytics/scope-bar.ts` (`''` for 0).
- Existing: `partialOpenTitle` (`ui/status-cell.ts:230`), `Hint` (`ui/hint.ts`, inputs `text`, `label`, `align`), `DashboardStore.data` (state, `stores/dashboard.store.ts:29`), `TradesStore.data` (state, `stores/trades.store.ts:20`).
- Produces: `numText(row: TradeRow): string` (exported from `trades.columns.ts`); `ROW_COUNT_NOTE` (exported from `trades.ts`). Nothing later in the ledger consumes them.

**What the Trades total counts (stated, as the spec requires).** Rows, not plans. `swingbot/admin/api_v1/trades.py:766` expands every plan into one row per realised leg plus one for a still-open remainder (`_expand_plan_row`, `:561-579`), and `:1086` takes `total = len(rows)` after that expansion; `tests/admin/test_api_v1_trades.py:246` (`test_status_filter_returns_the_closed_leg_and_the_open_remainder_separately`) already pins a closed leg and its open remainder as two rows of one plan. The page therefore says "rows" (the live-region summary and a count note under the table), and this task's tests pin that wording.

**Removed, not kept:** both `isPartialLeg` methods and the `title="Closed after an earlier partial exit of the same position"` icon they guarded. The label and its `sb-hint` replace the icon on every leg row (leg 1 too: spec B3 labels every leg). The `partialOpenTitle` and trailing-stop icons stay as they are; V194-14 classifies them. Before deleting, `git -C "$WT" grep -n "isPartialLeg" frontend/src/app` must list only the two definitions and their two template uses.

- [ ] **Step 1: Write the failing Trades tests.** In `frontend/src/app/workspaces/trades/trades.spec.ts`, extend the imports:

```ts
import { LEG_HINT_TEXT } from './leg-label';
import { numText } from './trades.columns';
import { fxMissingText } from '../analytics/scope-bar';
import { ROW_COUNT_NOTE, Trades, TRADES_CONTROLS } from './trades';
```

(`import { Trades, TRADES_CONTROLS } from './trades';` becomes the last line above.) Append at the end of the file:

```ts
/* -- v194 B3 -- leg rows say which part of the plan they are ------------- */

/** Mount Trades with `items` as the loaded page, in full density so the
 *  `#` column (and its `#numCell` template) is inline at jsdom's width. */
function renderRows(items: TradeRow[]): HTMLElement {
  const fixture = render();
  (fixture.componentInstance as unknown as { setDensity(d: 'full' | 'compact'): void }).setDensity('full');
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 50 },
    query: { page: 1, per_page: 50 },
  });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('Trades — leg rows (v194 B3)', () => {
  it('labels both legs of a two-leg plan with their exit reason', () => {
    const el = renderRows([
      row({ id: 'plan-aaaaaa', leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' }),
      row({ id: 'plan-aaaaaa', leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' }),
    ]);
    const labels = [...el.querySelectorAll('.leg')].map((n) => n.firstChild!.textContent!.trim());
    expect(labels[0]).toMatch(/^Leg 1 of 2 · /);
    expect(labels[1]).toMatch(/^Leg 2 of 2 · /);
  });

  it('labels a leg with no recorded reason by its position alone', () => {
    const el = renderRows([row({ leg_index: 2, leg_total: 3, leg_exit_reason: null })]);
    expect(el.querySelector('.leg')!.firstChild!.textContent!.trim()).toBe('Leg 3 of 3');
  });

  it('shows no label and no leg hint on a single-leg trade', () => {
    const el = renderRows([row({ leg_index: 0, leg_total: 1 })]);
    expect(el.querySelector('.leg')).toBeNull();
    expect(el.querySelector('.leg sb-hint')).toBeNull();
  });

  it('puts an sb-hint naming plans-not-legs on every leg row, in place of the old icon', () => {
    const el = renderRows([
      row({ leg_index: 0, leg_total: 2 }),
      row({ leg_index: 1, leg_total: 2 }),
    ]);
    const hints = [...el.querySelectorAll('.leg sb-hint')];
    expect(hints).toHaveLength(2);
    expect(hints[0].textContent).toContain(LEG_HINT_TEXT);
    expect(el.querySelector('[title="Closed after an earlier partial exit of the same position"]')).toBeNull();
  });

  it('carries the label into the expansion the phone drawer reuses', () => {
    const el = renderRows([row({ leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' })]);
    // The expansion template is stamped only for an expanded row; the
    // numText value is what the drawer's "Hidden in this view" list prints
    // for the `#` column whenever that column is not inline.
    expect(numText(row({ id: 'plan-123456', leg_index: 1, leg_total: 2, leg_exit_reason: null })))
      .toBe('123456 · Leg 2 of 2');
    expect(el.querySelector('.leg')).not.toBeNull();
  });
});

describe('numText', () => {
  it('is the short id alone for a single-leg trade', () => {
    expect(numText(row({ id: 'abcdefghij', leg_total: 1 }))).toBe('efghij');
  });

  it('keeps a short id whole', () => {
    expect(numText(row({ id: 't1', leg_total: 1 }))).toBe('t1');
  });
});

describe('Trades — the total counts rows, not plans (v194 B3)', () => {
  it('says so under a non-empty table, and the pager still prints the range once', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent!.trim()).toBe(ROW_COUNT_NOTE);
    expect(el.querySelectorAll('.bar .range')).toHaveLength(1);
  });

  it('announces rows, not trades', () => {
    const fixture = render({ total: 3, page: 1, perPage: 12 });
    const announce = (fixture.componentInstance as unknown as { announce: () => string | null }).announce;
    expect(announce()).toBe('3 rows');
  });
});

describe('Trades — missing FX rate caveat (v194 B7)', () => {
  it('names how many rows on the page have no rate', () => {
    const el = renderRows([
      row({ id: 'a', fx_missing: true, realized_pnl_amount: null }),
      row({ id: 'b', fx_missing: true, realized_pnl_amount: null }),
      row({ id: 'c', fx_missing: false }),
    ]);
    expect(el.querySelector('.fx-caveat')!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('is absent when every row converted', () => {
    const el = renderRows([row({ fx_missing: false }), row({ id: 'b' })]);
    expect(el.querySelector('.fx-caveat')).toBeNull();
  });
});
```

Also replace the first count-footer test (`:261-266`), whose premise this task changes:

```ts
  it('leaves the non-empty range to the pager, printed once', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')).toBeNull();
```
→
```ts
  it('leaves the non-empty range to the pager, printed once', () => {
    const el = render({ total: 142, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('p.count')!.textContent).not.toMatch(/\d+–\d+/);
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts`. Expected: FAIL — `numText` and `ROW_COUNT_NOTE` are not exported (compile error naming them).

- [ ] **Step 3: `numText` and the `num` column value.** In `frontend/src/app/workspaces/trades/trades.columns.ts`, add the import and the helper after the imports:

```ts
import { legLabel } from './leg-label';

/** What the `#` cell says as text -- the short plan id, then "Leg N of M"
 *  for a leg row (v194 B3). The table renders `#numCell`; this is what the
 *  phone drawer's "Hidden in this view" list and the compact card print
 *  when the column is not inline. Same 6-character trim as `shortId` in
 *  trades.ts and dashboard.ts. */
export function numText(row: TradeRow): string {
  const id = row.id.length > 6 ? row.id.slice(-6) : row.id;
  const leg = legLabel(row);
  return leg ? `${id} · ${leg}` : id;
}
```

and at `:143`:

```ts
    { key: 'num', header: '#', width: '3rem', inlineFrom: 'sm' },
```
→
```ts
    // No fixed width: a leg row's "Leg 2 of 2 · stop" sits under the id
    // (v194 B3); a page with no leg rows still sizes to the 6-char id.
    { key: 'num', header: '#', value: (row) => numText(row), inlineFrom: 'sm' },
```

- [ ] **Step 4: Trades template, count note and caveat.** In `frontend/src/app/workspaces/trades/trades.ts`:
  - imports: after `import { StatusCell, partialOpenTitle } from '../../ui/status-cell';` add
    ```ts
    import { Hint } from '../../ui/hint';
    import { fxMissingText } from '../analytics/scope-bar';
    import { LEG_HINT_TEXT, legLabel } from './leg-label';
    ```
    and add `Hint` to the `@Component` `imports: [...]` array.
  - after the `export const` block nearest the top of the file (or directly above `@Component`), add
    ```ts
    /** v194 B3: what the Trades total counts. The API expands every plan
     *  into one row per realised leg plus its open remainder
     *  (`swingbot/admin/api_v1/trades.py` `_expand_plan_row`) before it
     *  counts, so the pager's "1–50 of 120" is rows. */
    export const ROW_COUNT_NOTE = 'Counts rows, not plans: a plan closed in parts lists one row per leg.';
    ```
  - `:376-378`:
    ```html
        @if (countText(); as count) {
          <p class="count">{{ count }}</p>
        }
    ```
    →
    ```html
        @if (countText(); as count) {
          <p class="count">{{ count }}</p>
        }
        <!-- v194 B7: a row with no exchange rate for its exit date shows no
             amount; say how many on this page rather than let a dash pass
             for a zero. -->
        @if (fxMissing() > 0) {
          <p class="fx-caveat" role="note">{{ fxText(fxMissing()) }}</p>
        }
    ```
  - `#numCell` `:381-398`:
    ```html
        <ng-template #numCell let-row>
          <sb-row-link [link]="['/trades', row.id]">
            {{ shortId(row) }}
            <!-- v79 split a scaled-out position into one row per leg, both
                 carrying the same id -- unmarked, the later-closing leg reads
                 as a duplicate of the earlier partial exit it shares an id
                 with. -->
            @if (isPartialLeg(row)) {
              <sb-icon name="partial" class="leg-icon" title="Closed after an earlier partial exit of the same position" />
            }
            @if (partialOpenTitle(row); as openTitle) {
    ```
    →
    ```html
        <ng-template #numCell let-row>
          <sb-row-link [link]="['/trades', row.id]">
            {{ shortId(row) }}
            @if (partialOpenTitle(row); as openTitle) {
    ```
    and after that template's `</sb-row-link>` (before `</ng-template>`) add
    ```html
          <!-- v79 split a scaled-out position into one row per leg, all
               carrying the same id. v194 B3: every leg says which part it
               is, and the hint (outside the link: a button cannot sit in an
               anchor) says what a leg row's P&L and the page's N mean. -->
          @if (legLabel(row); as leg) {
            <span class="leg">{{ leg }}<sb-hint [text]="legHint" [label]="'About ' + leg" align="left" /></span>
          }
    ```
  - expansion `Detail` group: after `<div><dt>Note</dt><dd>{{ row.has_note ? 'Yes' : 'No' }}</dd></div>` (`:508`) add
    ```html
              @if (legLabel(row); as leg) {
                <div class="leg-detail">
                  <dt>Leg</dt>
                  <dd>{{ leg }} <sb-hint [text]="legHint" label="About leg rows" align="left" /></dd>
                </div>
              }
    ```
  - styles: after `.count { ... }` (`:558`) add
    ```css
    .fx-caveat { color: var(--text-secondary); font-size: var(--text-table); margin: 0; }
    .leg { display: flex; align-items: center; gap: var(--space-4); color: var(--text-muted); font-size: var(--text-chip); white-space: nowrap; }
    ```
  - `announce` `:850-854`: `` return page ? `${page.total} trades` : null; `` → `` return page ? `${page.total} rows` : null; ``
  - `countText` `:868-878`: the final `return null;` → `return ROW_COUNT_NOTE;`, and its doc comment's last paragraph gains: "A non-zero total is rows, not plans (v194 B3): the note says so; the range itself stays the pager's."
  - add, next to `announce`:
    ```ts
      /** v194 B7: rows on this page whose amount has no exchange rate. */
      protected readonly fxMissing = computed(
        () => (this.store.data()?.items ?? []).filter((r) => r.fx_missing === true).length,
      );
      protected readonly fxText = fxMissingText;
    ```
  - `:962-972`: delete the `isPartialLeg` doc comment and method, keep `protected readonly partialOpenTitle = partialOpenTitle;`, and add
    ```ts
      /** v194 B3: "Leg N of M[ · reason]" for a leg row, null otherwise. */
      protected readonly legLabel = legLabel;
      protected readonly legHint = LEG_HINT_TEXT;
    ```

- [ ] **Step 5: Run the Trades spec.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts`. Expected: PASS, the three existing count-footer tests included.

- [ ] **Step 6: Write the failing Dashboard tests.** In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` add the imports
```ts
import { LEG_HINT_TEXT } from '../trades/leg-label';
import { fxMissingText } from '../analytics/scope-bar';
import { tradeDrawerFields } from './trade-drawer';
```
and append:

```ts
describe('Dashboard — leg rows and missing FX rates (v194 B3, B7)', () => {
  it('labels each leg of a split plan in the positions table, with the plans-not-legs hint', async () => {
    const el = await loadedWithRows([
      tradeRow({ id: 'p1', leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' }),
      tradeRow({ id: 'p1', leg_index: 1, leg_total: 2, leg_exit_reason: null }),
    ]);
    const legs = [...el.querySelectorAll('sb-positions-table .leg')];
    expect(legs.map((n) => n.firstChild!.textContent!.trim())).toEqual([
      expect.stringMatching(/^Leg 1 of 2 · /),
      'Leg 2 of 2',
    ]);
    expect(legs[0].querySelector('sb-hint')!.textContent).toContain(LEG_HINT_TEXT);
    expect(el.querySelector('[title="Closed after an earlier partial exit of the same position"]')).toBeNull();
  });

  it('shows no leg label for a single-leg row', async () => {
    const el = await loadedWithRows([tradeRow({ leg_index: 0, leg_total: 1 })]);
    expect(el.querySelector('sb-positions-table .leg')).toBeNull();
  });

  it('names the trades left out of the money figures', async () => {
    const fixture = await loaded({ fx_missing_count: 2 } as Partial<DashboardData>);
    const caveat = (fixture.nativeElement as HTMLElement).querySelector('.performance-stack .fx-caveat');
    expect(caveat!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('shows no caveat when every rate was found or the field is absent', async () => {
    for (const overrides of [{ fx_missing_count: 0 }, {}] as Partial<DashboardData>[]) {
      const fixture = await loaded(overrides);
      expect((fixture.nativeElement as HTMLElement).querySelector('.fx-caveat')).toBeNull();
    }
  });

  it('lists the leg in the trade drawer for a leg row only', () => {
    const leg = tradeDrawerFields(tradeRow({ leg_index: 1, leg_total: 3, leg_exit_reason: null }), '$', 0);
    expect(leg.find((f) => f.key === 'leg')?.value).toBe('Leg 2 of 3');
    const single = tradeDrawerFields(tradeRow({ leg_index: 0, leg_total: 1 }), '$', 0);
    expect(single.some((f) => f.key === 'leg')).toBe(false);
  });
});
```

- [ ] **Step 7: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`. Expected: FAIL — no `.leg`, no `.fx-caveat`, no `leg` drawer field.

- [ ] **Step 8: Dashboard template and drawer.** In `frontend/src/app/workspaces/dashboard/dashboard.ts`:
  - imports: after `import { StatusCell, partialOpenTitle } from '../../ui/status-cell';` (`:33`) add
    ```ts
    import { fxMissingText } from '../analytics/scope-bar';
    import { LEG_HINT_TEXT, legLabel } from '../trades/leg-label';
    ```
    (`Hint` is already imported at `:51` and in the component's `imports`.)
  - `.performance-stack`: after the `<sb-trading-performance ... />` element's closing `/>` (`:224`) and before `</div>` add
    ```html
        <!-- v194 B7: closes and positions with no exchange rate are left out
             of the money figures above; say how many. -->
        @if (fxMissing() > 0) {
          <p class="fx-caveat" role="note">{{ fxText(fxMissing()) }}</p>
        }
    ```
  - `#numCell` `:387-404`: the same edit as Trades' — delete the `<!-- v79 split ... -->` comment and the `@if (isPartialLeg(row)) { ... }` block inside `sb-row-link`, and after `</sb-row-link>` add
    ```html
          <!-- v194 B3: every leg says which part of the plan it is; the hint
               sits outside the link (a button cannot nest in an anchor). -->
          @if (legLabel(row); as leg) {
            <span class="leg">{{ leg }}<sb-hint [text]="legHint" [label]="'About ' + leg" align="left" /></span>
          }
    ```
  - styles: after `sb-row-link .leg-icon { color: var(--text-muted); flex: none; }` (`:579`) add
    ```css
    .fx-caveat { color: var(--text-secondary); font-size: var(--text-table); margin: 0; }
    .leg { display: flex; align-items: center; gap: var(--space-4); color: var(--text-muted); font-size: var(--text-chip); white-space: nowrap; }
    ```
  - `:983-992`: delete the `isPartialLeg` doc comment and method; keep `partialOpenTitle`; add
    ```ts
      /** v194 B3: "Leg N of M[ · reason]" for a leg row, null otherwise. */
      protected readonly legLabel = legLabel;
      protected readonly legHint = LEG_HINT_TEXT;

      /** v194 B7: the main ledger's rows left out of the money figures. */
      protected readonly fxMissing = computed(() => this.store.data()?.fx_missing_count ?? 0);
      protected readonly fxText = fxMissingText;
    ```

  In `frontend/src/app/workspaces/dashboard/trade-drawer.ts`:
  - imports: add `import { Hint } from '../../ui/hint';` and `import { LEG_HINT_TEXT, legLabel } from '../trades/leg-label';`; the component's `imports: [Drawer, RowActions, RouterLink]` → `imports: [Drawer, Hint, RowActions, RouterLink]`.
  - `tradeDrawerFields`:
    ```ts
        field('status', 'Status', text(row.status_label || row.status)),
    ```
    →
    ```ts
        field('status', 'Status', text(row.status_label || row.status)),
        ...legFields(row),
    ```
    with, above `tradeDrawerFields`:
    ```ts
    /** v194 B3: a leg row says which part of the plan it is; a single-leg
     *  trade gets no field at all. */
    function legFields(row: TradeRow): TradeDrawerField[] {
      const leg = legLabel(row);
      return leg ? [field('leg', 'Leg', leg)] : [];
    }
    ```
  - template, `:116`: `<dt>{{ item.label }}</dt>` →
    ```html
            <dt>{{ item.label }}@if (item.key === 'leg') { <sb-hint [text]="legHint" label="About leg rows" align="left" /> }</dt>
    ```
    and in the class add `protected readonly legHint = LEG_HINT_TEXT;` after `paperMarker`.

- [ ] **Step 9: Run the Dashboard spec.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`, then `--include src/app/workspaces/dashboard/trade-drawer.spec.ts` (unchanged, must stay green: a single-leg row adds no field). Expected: PASS.

- [ ] **Step 10: Three widths.** With the frontend dev server on the local replica (Global Constraints: `.env` login loaded inside the script, never printed), one Playwright screenshot of `/app/trades?status=CLOSED` at 390, 768 and 1440 with at least one split plan on the page: the `#` column holds the id and "Leg N of M · reason" without overlapping the Status column, the hint glyph is a 44px target at 390/768 (the coarse-pointer `@media` in `hint.ts`), and the page shows the count note. Note the result in the commit body.

Close: standard (test: `frontend/src/app/workspaces/trades/trades.spec.ts`), plus the narrow run of `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`; one commit `feat(v194): leg labels and plans-not-legs hint on Trades and Dashboard; rows count note; FX caveat (V194-13)`.

### Task V194-14: A3 part 1 — `title-usage.spec.ts` scanner and allow-list (classifies every site, converts nothing)

**Model:** sonnet — a source scanner and a classified list; the classification is fixed below, the scanner is plain string work.

**Files:**
- Create: `frontend/src/app/ui/title-usage.allow.ts`
- Create: `frontend/src/app/ui/title-usage.spec.ts`

**Interfaces:**
- Consumes: nothing at runtime. `Hint` and `StatTile.about` are what V194-14b/15/15b convert *to*; this task only names the sites.
- Produces (all exported from `title-usage.allow.ts`): `interface TitleSite { file: string; binding: string; kind: 'echo' | 'control-name' | 'explanation-pending'; note: string }`; `TITLE_ALLOW: readonly TitleSite[]`; `TITLE_PENDING: readonly TitleSite[]` (the `explanation-pending` subset — no site in `workspaces/analytics/`, which holds none); `TITLE_INPUT_ELEMENTS: readonly string[]`. V194-14b, V194-15 and V194-15b delete `explanation-pending` entries as they convert them; V194-15b asserts `TITLE_PENDING` is empty.

**The counting rule (index § Global Constraints, A3).** A site is `title="`, `[title]="` or `[attr.title]="` preceded by whitespace, or a host-metadata key `'[attr.title]': '…'`, in `frontend/src/app/**/*.ts` minus `*.spec.ts` and `src/app/testing/**`, minus occurrences inside an element named in `TITLE_INPUT_ELEMENTS` (their `title` is an input that renders visible heading text). The element is found by looking back from the occurrence to the nearest `<` with no `>` between, so a multi-line `<sb-confirm-dialog … title="…">` is excluded like a one-line one. Occurrences are counted, not lines: three identical `[attr.title]="rTooltip"` in one file are three entries.

**Measured on `main` after V194-13 (2026-10-25): 55 sites** — 21 stay (echo / control-name), 34 explanation (9 for V194-14b, 20 for V194-15, 5 for V194-15b). Analytics: 0 (its 49 `title=` are `sb-panel-header`, `sb-empty-state` and `sb-confirm-dialog` inputs). If the scan in Step 3 finds a site not listed (an earlier v194 task moved or added one), classify it by spec A3 (definition, caveat or why-absent → `explanation-pending`; repeats a value the row drawer or detail view shows → `echo`; names an icon-only control → `control-name`), add it, and say so in the commit.

- [ ] **Step 1: Write the allow-list.** Create `frontend/src/app/ui/title-usage.allow.ts`:

```ts
/**
 * v194 A3 -- every native `title` left in `src/app`, classified once.
 *
 * A `title` only answers a mouse hover: a phone, a keyboard and a screen
 * reader never see it. So a `title` may only carry what is said elsewhere
 * too (`echo`) or name an icon-only control (`control-name`, beside an
 * `aria-label`). Anything that explains -- a definition, a caveat, why a
 * value is absent -- is an `sb-hint` or visible text instead.
 * `explanation-pending` marks the sites a later v194 task converts; it is
 * empty once V194-15b lands, and `title-usage.spec.ts` fails on any
 * `title` binding not listed here.
 *
 * `binding` is the attribute exactly as written (whitespace runs collapsed
 * to one space); `file` is relative to `src/app`.
 */
export interface TitleSite {
  file: string;
  binding: string;
  kind: 'echo' | 'control-name' | 'explanation-pending';
  note: string;
}

/** Elements whose `title` is a component input rendering visible heading
 *  text, not a tooltip. */
export const TITLE_INPUT_ELEMENTS: readonly string[] = ['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog'];

const FRAGILE = 'title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it."';

export const TITLE_ALLOW: readonly TitleSite[] = [
  // -- shell ---------------------------------------------------------------
  { file: 'shell/connection-status.ts', binding: '[title]="hint()"', kind: 'control-name', note: 'status dot; aria-label carries the state word, panels carry data age' },
  { file: 'shell/profile-menu.ts', binding: '[attr.title]="haloTitle()"', kind: 'control-name', note: 'the avatar menu button: bot up/down beside its aria-label' },
  { file: 'shell/tape/tape.ts', binding: "[attr.title]=\"asOfTime() === ABSENT ? null : 'Tape data as of ' + asOfTime()\"", kind: 'echo', note: 'as-of time; each tile shows its own age' },
  { file: 'shell/tape/tape.ts', binding: 'title="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF\'s price."', kind: 'explanation-pending', note: 'V194-14b: proxy caveat' },
  // -- ui primitives ---------------------------------------------------------
  { file: 'ui/age-hint.ts', binding: "[attr.title]=\"'Price is ' + t.replace(' ago', '') + ' old'\"", kind: 'echo', note: 'restates the visible age' },
  { file: 'ui/bar-list.ts', binding: '[title]="row.label"', kind: 'echo', note: 'full text of a truncated bar label' },
  { file: 'ui/direction-arrow.ts', binding: '[title]="text"', kind: 'control-name', note: 'glyph name, same as its aria-label' },
  { file: 'ui/icon.ts', binding: "'[attr.title]': 'tip()'", kind: 'control-name', note: 'names an icon' },
  { file: 'ui/layout.ts', binding: "'[attr.title]': 'description()'", kind: 'explanation-pending', note: 'V194-14b: sb-panel description; the header sb-hint already says it' },
  { file: 'ui/layout.ts', binding: '[attr.title]="tab.icon ? tab.label : null"', kind: 'control-name', note: 'icon-only tab, beside its aria-label' },
  { file: 'ui/matrix.ts', binding: '[attr.title]="cellTitle(row, col, r, c)"', kind: 'echo', note: 'row, column and value the cell colour encodes' },
  { file: 'ui/metric-card.ts', binding: "'[attr.title]': 'description()'", kind: 'explanation-pending', note: 'V194-14b: card definition' },
  { file: 'ui/plan-cell.ts', binding: '[title]="planTooltip"', kind: 'explanation-pending', note: 'V194-14b: runner line 1 definition' },
  { file: 'ui/plan-cell.ts', binding: '[title]="trailTooltip()"', kind: 'explanation-pending', note: 'V194-14b: runner line 2 definition and caveats' },
  { file: 'ui/plan-cell.ts', binding: '[title]="tooltip()"', kind: 'echo', note: 'the levels the trade detail plan card shows, spelled out' },
  { file: 'ui/stat-tile.ts', binding: '[title]="sampleTitle()"', kind: 'explanation-pending', note: 'V194-14b: thin-sample shortfall' },
  { file: 'ui/status-cell.ts', binding: 'title="P&L if the trailing stop is hit"', kind: 'explanation-pending', note: 'V194-14b: bar end definition' },
  { file: 'ui/status-cell.ts', binding: '[title]="row().status_label"', kind: 'echo', note: 'the status label the cell prints' },
  { file: 'ui/status-cell.ts', binding: 'title="P&L at the best price since TP1"', kind: 'explanation-pending', note: 'V194-14b: bar end definition' },
  { file: 'ui/status-cell.ts', binding: 'title="This position\'s price could not be freshly fetched -- the number shown may be delayed."', kind: 'explanation-pending', note: 'V194-14b: stale-price caveat' },
  // -- calendar --------------------------------------------------------------
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Total tile, R definition' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Average trade tile' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Worst drawdown tile' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: month-to-date R' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: breakdown R column head' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="breakdownWinRate(row) === absent ? winNote : null"', kind: 'explanation-pending', note: 'V194-15: why win % is withheld' },
  { file: 'workspaces/calendar/day/day-trade-card.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: R definition' },
  { file: 'workspaces/calendar/day/trade-sparkline.ts', binding: 'title="No cached daily bars for this row"', kind: 'explanation-pending', note: 'V194-15: why the sparkline is absent' },
  // -- cancels / dashboard ---------------------------------------------------
  { file: 'workspaces/cancels/cancels-summary.ts', binding: 'title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate"', kind: 'explanation-pending', note: 'V194-15b: small-N caveat' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: '[title]="openTitle"', kind: 'explanation-pending', note: 'V194-15: share still open on a PARTIAL row' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Live P&L, then projected P&L at target and at stop"', kind: 'explanation-pending', note: 'V194-15: P&L cell reading order' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Projected R if price reaches target"', kind: 'explanation-pending', note: 'V194-15: expected R definition' },
  { file: 'workspaces/dashboard/panels/equity-candles.ts', binding: '[attr.title]="isChangePart(part.text) ? changeTooltip : null"', kind: 'explanation-pending', note: 'V194-15: change is not a return on capital' },
  { file: 'workspaces/dashboard/panels/equity-candles.ts', binding: 'title="Back to today: chart and figures"', kind: 'control-name', note: 'reset button, beside its aria-label' },
  { file: 'workspaces/dashboard/panels/recent-activity.ts', binding: '[title]="statusLabel(event)"', kind: 'control-name', note: 'status icon, beside its aria-label' },
  { file: 'workspaces/dashboard/trade-drawer.ts', binding: 'title="The bot places no orders: every trade on this page is a paper trade."', kind: 'explanation-pending', note: 'V194-15: paper-trade caveat' },
  // -- research / system -----------------------------------------------------
  { file: 'workspaces/research/research.ts', binding: '[attr.title]="row.hypothesis"', kind: 'echo', note: 'full text of a truncated hypothesis' },
  { file: 'workspaces/system/settings-tab.ts', binding: 'title="Default value"', kind: 'echo', note: 'names the default badge the row prints' },
  { file: 'workspaces/system/settings-tab.ts', binding: 'title="Restart required to take effect"', kind: 'explanation-pending', note: 'V194-15b: restart caveat' },
  { file: 'workspaces/system/settings-tab.ts', binding: "[title]=\"'Reset to ' + field.default\"", kind: 'echo', note: 'the default the badge beside it shows' },
  { file: 'workspaces/system/swallowed-errors-panel.ts', binding: '[attr.title]="line.lastSeenAt"', kind: 'echo', note: 'exact timestamp of the relative time shown' },
  // -- trades ----------------------------------------------------------------
  { file: 'workspaces/trades/position-card.ts', binding: FRAGILE, kind: 'explanation-pending', note: 'V194-15: gap-fragile stop caveat' },
  { file: 'workspaces/trades/trade-detail.ts', binding: '[title]="cohortTooltip()"', kind: 'explanation-pending', note: 'V194-15: cohort chip meaning' },
  { file: 'workspaces/trades/trade-detail.ts', binding: "[title]=\"'Trade ID: ' + trade.id\"", kind: 'echo', note: 'the id printed beside it' },
  { file: 'workspaces/trades/trades.ts', binding: 'title="Downloads the entire trade log. The filters above do not narrow it."', kind: 'explanation-pending', note: 'V194-15: export scope caveat' },
  { file: 'workspaces/trades/trades.ts', binding: '[title]="openTitle"', kind: 'explanation-pending', note: 'V194-15: share still open on a PARTIAL row' },
  { file: 'workspaces/trades/trades.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  { file: 'workspaces/trades/why/sizing-panel.ts', binding: FRAGILE, kind: 'explanation-pending', note: 'V194-15: gap-fragile stop caveat' },
  { file: 'workspaces/trades/why/why-panel.ts', binding: 'title="no data — neutral points awarded"', kind: 'explanation-pending', note: 'V194-15: unevaluated factor' },
  { file: 'workspaces/trades/why/why-panel.ts', binding: 'title="off in current config"', kind: 'explanation-pending', note: 'V194-15: gate switched off' },
  // -- versions / watchlist --------------------------------------------------
  { file: 'workspaces/versions/versions.ts', binding: "[attr.title]=\"component + ' ' + version + ' — click to filter'\"", kind: 'control-name', note: 'filter chip button: names what a click does' },
  { file: 'workspaces/versions/versions.ts', binding: 'title="This component did not exist yet"', kind: 'explanation-pending', note: 'V194-15b: hatched lane segment' },
  { file: 'workspaces/versions/versions.ts', binding: 'title="The releases listed below"', kind: 'explanation-pending', note: 'V194-15b: bracket under the lanes' },
  { file: 'workspaces/watchlist/watchlist.ts', binding: 'title="Alpaca missed this quote; yfinance answered instead"', kind: 'explanation-pending', note: 'V194-15b: fallback badge' },
];

/** Sites a later v194 task converts. Empty once V194-15b lands. */
export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
```

- [ ] **Step 2: Write the scanner spec.** Create `frontend/src/app/ui/title-usage.spec.ts`:

```ts
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS, TITLE_PENDING } from './title-usage.allow';

const ROOT = join(process.cwd(), 'src/app');

/** `title="…"`, `[title]="…"`, `[attr.title]="…"` after whitespace, or the
 *  host-metadata key `'[attr.title]': '…'`. */
const SITE = /(?<=\s)(?:\[attr\.title\]|\[title\]|title)="[^"]*"|'\[attr\.title\]':\s*'[^']*'/g;

interface Found { file: string; binding: string }

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return path === join(ROOT, 'testing') ? [] : sourceFiles(path);
    return name.endsWith('.ts') && !name.endsWith('.spec.ts') ? [path] : [];
  });
}

/** The element an attribute at `index` sits on: the nearest `<` before it
 *  with no `>` in between. Null outside a tag (host metadata). */
function enclosingTag(source: string, index: number): string | null {
  const open = source.lastIndexOf('<', index);
  if (open < 0 || source.lastIndexOf('>', index) > open) return null;
  return /^<([a-z][\w-]*)/i.exec(source.slice(open))?.[1].toLowerCase() ?? null;
}

function findTitleSites(file: string, source: string): Found[] {
  const found: Found[] = [];
  for (const match of source.matchAll(SITE)) {
    const tag = enclosingTag(source, match.index!);
    if (tag !== null && TITLE_INPUT_ELEMENTS.includes(tag)) continue;
    found.push({ file, binding: match[0].replace(/\s+/g, ' ') });
  }
  return found;
}

function scan(): Found[] {
  return sourceFiles(ROOT).flatMap((path) =>
    findTitleSites(relative(ROOT, path).split('\\').join('/'), readFileSync(path, 'utf8')));
}

const key = (s: Found): string => `${s.file} :: ${s.binding}`;

describe('findTitleSites', () => {
  it('finds plain, bound and attr titles, and host metadata', () => {
    const src = `template: \`<span title="a">x</span> <b [title]="b()"></b> <i [attr.title]="c"></i>\`,
      host: { '[attr.title]': 'd()' },`;
    expect(findTitleSites('f.ts', src).map((s) => s.binding)).toEqual([
      'title="a"', '[title]="b()"', '[attr.title]="c"', "'[attr.title]': 'd()'",
    ]);
  });

  it('skips title inputs of heading components, one line or several', () => {
    const src = `<sb-panel-header title="Equity" [n]="3" />
      <sb-confirm-dialog
        [open]="x"
        title="Delete this?"
      />
      <sb-empty-state [title]="error()!" />`;
    expect(findTitleSites('f.ts', src)).toEqual([]);
  });

  it('ignores names that only end in "title"', () => {
    const src = `<x subtitle="a" data-title="b" [pageTitle]="c"></x>`;
    expect(findTitleSites('f.ts', src)).toEqual([]);
  });

  it('counts two identical bindings in one file twice', () => {
    expect(findTitleSites('f.ts', `<a [title]="r"></a> <b [title]="r"></b>`)).toHaveLength(2);
  });
});

describe('native title usage (v194 A3)', () => {
  const found = scan();

  it('lists every title binding in the allow-list, so no new explanation hides in a title', () => {
    const allowed = new Map<string, number>();
    for (const s of TITLE_ALLOW) allowed.set(key(s), (allowed.get(key(s)) ?? 0) + 1);
    const unlisted = found.filter((s) => {
      const left = allowed.get(key(s)) ?? 0;
      allowed.set(key(s), left - 1);
      return left <= 0;
    });
    expect(unlisted.map(key)).toEqual([]);
  });

  it('keeps no stale allow-list entry once a site is converted', () => {
    expect(found.map(key).sort()).toEqual(TITLE_ALLOW.map(key).sort());
  });

  it('gives every entry a reason', () => {
    expect(TITLE_ALLOW.filter((s) => s.note.trim() === '')).toEqual([]);
  });

  it('marks as pending exactly the explanation sites', () => {
    expect(TITLE_PENDING).toEqual(TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending'));
    expect(TITLE_PENDING.some((s) => s.file.startsWith('workspaces/analytics/'))).toBe(false);
  });
});
```

- [ ] **Step 3: Run it.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`. Expected: PASS, 8 tests. A failure in the first `native title usage` test prints each unlisted `file :: binding` — classify it (rule above) and add it; a failure in the second prints a stale entry (a site already moved by an earlier task) — remove it. Then count for the commit message: `grep -c "^  { file:" "$WT/frontend/src/app/ui/title-usage.allow.ts"` (total, expected 55) and `grep -c "kind: 'explanation-pending', note" "$WT/frontend/src/app/ui/title-usage.allow.ts"` (pending, expected 34).

Close: standard (test: `frontend/src/app/ui/title-usage.spec.ts`); commit `test(v194): title-usage scanner and classified allow-list, <total> sites, <pending> pending (V194-14)` with the measured counts.

### Task V194-14b: A3 part 2 — convert the shared primitives' explanation titles (`sb-panel`, `sb-metric-card`, `sb-stat-tile`, `sb-plan-cell`, `sb-status-cell`, the tape)

**Model:** sonnet — nine mechanical title → `sb-hint` / visible-text conversions in shared components, each with its spec updated.

**Files:**
- Modify: `frontend/src/app/ui/layout.ts:39-41,47-53` (`Panel`)
- Modify: `frontend/src/app/ui/metric-card.ts:41-56` (`MetricCard`)
- Modify: `frontend/src/app/ui/stat-tile.ts:45-46,158-164` (`StatTile`)
- Modify: `frontend/src/app/ui/plan-cell.ts:30,39,46-47,188-190` (`PlanCell`)
- Modify: `frontend/src/app/ui/status-cell.ts:74,85-87,102-104,107-111` (`StatusCell`)
- Modify: `frontend/src/app/shell/tape/tape.ts:61,66-67,80,117` (`Tape`)
- Modify: `frontend/src/app/ui/title-usage.allow.ts` (delete the 9 entries noted `V194-14b`)
- Test: `frontend/src/app/ui/layout.spec.ts:122-145`, `frontend/src/app/ui/metric-card.spec.ts:188-195`, `frontend/src/app/ui/stat-tile.spec.ts`, `frontend/src/app/ui/plan-cell.spec.ts:313-347`, `frontend/src/app/ui/status-cell.spec.ts`, `frontend/src/app/shell/tape/tape.spec.ts` (these existing specs assert the old `title` attributes, so they change with the components; the ledger row lists only the components)

**Interfaces:**
- Consumes: `Hint` (`ui/hint.ts`; inputs `text`, `label`, `align`; its tooltip text is in the element with `role="tooltip"`, its trigger is a `button` whose `aria-label` is `label`), `TITLE_ALLOW` / `TITLE_PENDING` (V194-14).
- Produces: `STATUS_ENDS_HINT`, `STATUS_STALE_HINT` (exported from `status-cell.ts`), `TAPE_PROXY_HINT` (exported from `tape.ts`); `PlanCell.runnerHint` (protected computed). Nothing later in the ledger consumes them.

**Rule for every site:** a `title` that explains becomes an `sb-hint` beside the thing it explains (never inside an `<a>`: a button cannot nest in an anchor), or visible text when it is short. The text keeps its meaning; copy fixes belong to V194-16.

- [ ] **Step 1: Update the specs to the new behaviour (they fail first).**

`frontend/src/app/ui/layout.spec.ts`, the three tests at `:122-145`:

```ts
    it('explains itself through the header hint, not a native title', () => {
      const el = mount('Profit already locked in.');
      expect(el.hasAttribute('title')).toBe(false);
      const hint = el.querySelector('header sb-hint')!;
      expect(hint.querySelector('[role="tooltip"]')!.textContent!.trim()).toBe('Profit already locked in.');
      expect(hint.querySelector('button')!.getAttribute('aria-label')).toBe('About Realised P&L');
    });

    it('adds neither a tooltip nor a hint when it has no description', () => {
      const el = mount(null);
      expect(el.hasAttribute('title')).toBe(false);
      expect(el.querySelector('sb-hint')).toBeNull();
    });

    it('adds no title and no hint when the panel has a hint of its own', () => {
      const f = TestBed.createComponent(Panel);
      f.componentRef.setInput('heading', 'Open positions');
      f.componentRef.setInput('description', 'Every plan by stage.');
      f.componentRef.setInput('descriptionHint', false);
      f.detectChanges();
      const el = f.nativeElement as HTMLElement;
      expect(el.hasAttribute('title')).toBe(false);
      expect(el.querySelector('sb-hint')).toBeNull();
    });
```

`frontend/src/app/ui/metric-card.spec.ts`, the two tests at `:188-195`:

```ts
  it('explains itself through a hint beside its label when given a description', () => {
    const { host } = mount({ description: 'The share of closed trades that won.' });
    expect(host.hasAttribute('title')).toBe(false);
    const hint = host.querySelector('.label-row sb-hint')!;
    expect(hint.querySelector('[role="tooltip"]')!.textContent!.trim()).toBe('The share of closed trades that won.');
    expect(hint.querySelector('button')!.getAttribute('aria-label')).toMatch(/^About /);
    expect(host.querySelector('.label')!.textContent).not.toContain('The share of closed trades');
  });

  it('has no tooltip and no hint without a description', () => {
    const { host } = mount({});
    expect(host.hasAttribute('title')).toBe(false);
    expect(host.querySelector('sb-hint')).toBeNull();
  });
```

`frontend/src/app/ui/stat-tile.spec.ts`, append inside its top-level `describe` (its `render(inputs)` helper is at `:12`):

```ts
  it('says inline how many more trades a thin sample needs, with no native title (v194 A3)', () => {
    const el = render({ label: 'Win rate', value: '50%', sample: 12 });
    expect(el.querySelector('.sample')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.flag')!.textContent).toContain(`thin sample, ${MIN_SAMPLE_N - 12} more needed`);
  });

  it('prints no shortfall once the sample is large enough', () => {
    const el = render({ label: 'Win rate', value: '50%', sample: MIN_SAMPLE_N });
    expect(el.querySelector('.flag')).toBeNull();
  });
```

(add `MIN_SAMPLE_N` to the spec's import from `./stat-tile`; the existing `toContain('thin sample')` checks at `:74` and `:201` stay valid).

`frontend/src/app/ui/plan-cell.spec.ts`: add below `const text = …` (`:274`)

```ts
const hintText = (el: Element): string =>
  el.querySelector('.plan.runner sb-hint [role="tooltip"]')!.textContent!.replace(/\s+/g, ' ').trim();
```

and replace the five tests `:313-347` (`puts the tooltips on the lines…` through `names a derived floor…`) with:

```ts
  it('explains both runner lines in one hint, with no native titles', () => {
    const el = renderWith(RKLB_RUNNER);
    expect(el.querySelector('.plan.runner [title]')).toBeNull();
    expect(el.querySelector('.plan.runner')!.hasAttribute('title')).toBe(false);
    expect(el.querySelectorAll('.plan.runner sb-hint')).toHaveLength(1);
  });

  it('explains line 1 as the original plan', () => {
    expect(hintText(renderWith(RKLB_RUNNER)).startsWith(
      'Original plan (TP1 already filled): entry → TP1 / original stop. '
      + 'Percentages are the distance from the entry to each level. '
      + 'The stop shown is the original; the live exit is on the next line.')).toBe(true);
  });

  it('explains line 2: unrealised peak, per share, before costs, paper level', () => {
    expect(hintText(renderWith(RKLB_RUNNER))).toContain(
      'Trailing stop. Best price so far → price the trailing stop would exit at. '
      + '+17.7% is the peak since TP1 (unrealised); +13.6% is the result if the stop '
      + 'fills at 52.44, per share from the original entry, before costs and tax. '
      + `A short gains when price falls. ${PAPER_LEVEL}`);
  });

  it('reads a long runner the same way, with the long sentence', () => {
    const el = renderWith(LONG_RUNNER);
    expect(text(el.querySelector('.l1'))).toBe('100.00 → 120.00 / 90.00 (20.0% - 10.0%)');
    expect(text(el.querySelector('.l2'))).toBe('Trail 130.00 → 113.33 (+30.0% / +13.3%)');
    expect(hintText(el)).toContain('A long gains when price rises.');
  });

  it('names a derived floor "Locked-in floor" in the hint', () => {
    const hint = hintText(renderWith({ ...RKLB_RUNNER, stopKind: 'derived_floor' }));
    expect(hint).toContain('Locked-in floor. Best price so far → price the locked-in floor would exit at. ');
    expect(hint).toContain('is the result if the stop fills at 52.44');
  });
```

`frontend/src/app/ui/status-cell.spec.ts`: hoist the row literal the existing trailing-ends test renders at `:58-62` (the one ending `stop_pnl_pct: 1.25, best_pnl_pct: 6 }`) into `const TRAILING = { … };` above that test, have that test call `render(TRAILING)`, add `STATUS_ENDS_HINT, STATUS_STALE_HINT` to the import from `./status-cell`, and append inside `describe('StatusCell')`:

```ts
  it('explains the two trailing P&L ends in one hint, not two titles (v194 A3)', () => {
    const el = render(TRAILING);
    expect(el.querySelector('.end[title]')).toBeNull();
    expect(el.querySelector('sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(STATUS_ENDS_HINT);
  });

  it('explains a delayed price in a hint beside the word', () => {
    const el = render({ ...live, current_price_stale: true });
    expect(el.querySelector('.stale')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.stale')!.textContent!.trim()).toBe('delayed');
    expect(el.querySelector('.stale + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(STATUS_STALE_HINT);
  });
```

`frontend/src/app/shell/tape/tape.spec.ts`: add `TAPE_PROXY_HINT` to the import from `./tape` and append after the proxy test at `:75`:

```ts
  it('explains proxy figures once, beside the lane caption, never inside a tile link (v194 A3)', () => {
    const el = setup([proxy], []).nativeElement as HTMLElement;
    expect(el.querySelector('.proxy')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('a sb-hint')).toBeNull();
    expect(el.querySelector('.cap-row sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(TAPE_PROXY_HINT);
  });

  it('shows no proxy hint when no tile is a proxy', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelector('.cap-row sb-hint')).toBeNull();
  });
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/layout.spec.ts --include src/app/ui/metric-card.spec.ts --include src/app/ui/stat-tile.spec.ts --include src/app/ui/plan-cell.spec.ts --include src/app/ui/status-cell.spec.ts --include src/app/shell/tape/tape.spec.ts`. Expected: FAIL — titles still present, `STATUS_ENDS_HINT` / `TAPE_PROXY_HINT` not exported, no `.label-row`.

- [ ] **Step 3: `sb-panel`** (`ui/layout.ts`). Delete `:39-41`:

```ts
  // The tooltip sits on the host, so any hover inside the panel shows it; a
  // child with a title of its own (an icon, a cell) still wins over it.
  host: { '[attr.title]': 'description()' },
```

and in the header (`:50-52`) the comment

```html
            <!-- The host's native title answers a hover; the hint answers a
                 tap or a keyboard focus, which a title never does. A panel
                 with a richer hint of its own turns this one off. -->
```
→
```html
            <!-- v194 A3: the hint answers hover, tap and keyboard focus alike;
                 the host carries no native title. A panel with a richer hint
                 of its own turns this one off. -->
```

- [ ] **Step 4: `sb-metric-card`** (`ui/metric-card.ts`). Add `import { Hint } from './hint';`; `imports: [CountUp, Spinner],` → `imports: [CountUp, Spinner, Hint],`; delete the host line `'[attr.title]': 'description()',` (`:47`); and in the template

```html
      <span class="label sb-label">{{ label() }}</span>
```
→
```html
      <span class="label-row">
        <span class="label sb-label">{{ label() }}</span>
        @if (description(); as about) {
          <sb-hint [text]="about" [label]="'About ' + label()" align="left" />
        }
      </span>
```

with, in `styles`, `.label-row { display: flex; align-items: center; gap: var(--space-4); min-width: 0; }`.

- [ ] **Step 5: `sb-stat-tile`** (`ui/stat-tile.ts`). Template `:45-46`:

```html
        <div class="sample" [title]="sampleTitle()">
          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample</span>}
```
→
```html
        <div class="sample">
          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample, {{ shortfall() }} more needed</span>}
```

and replace `sampleTitle` (`:158-164`) with

```ts
  /** v194 A3: how many more closed trades before the figure is worth
   *  reading -- printed inline beside "thin sample" (it used to hide in a
   *  native title a phone never shows). */
  protected readonly shortfall = computed(() => {
    const n = this.sample();
    return n === null ? 0 : Math.max(0, this.minimumSample() - n);
  });
```

- [ ] **Step 6: `sb-plan-cell`** (`ui/plan-cell.ts`). Add `import { Hint } from './hint';` and `imports: [Hint],` to the `@Component` (it has none today). Template: `:30` `<span class="line l1" [title]="planTooltip">` → `<span class="line l1">`; `:39` `<span class="line l2" [title]="trailTooltip()">` → `<span class="line l2">`; between the trail block's closing `}` (`:46`) and the runner span's `</span>` (`:47`) add

```html
        <sb-hint [text]="runnerHint()" label="About this runner's plan" align="left" />
```

After `protected readonly trailTooltip = computed(...)` add

```ts
  /** v194 A3: one hint for both runner lines -- what line 1 is and, when
   *  line 2 shows, what its trail figures mean. */
  protected readonly runnerHint = computed(() => {
    const trail = this.trailTooltip();
    return trail ? `${this.planTooltip} ${trail}` : this.planTooltip;
  });
```

The legacy `<span class="plan" [title]="tooltip()">` (`:49`) stays (`echo`).

- [ ] **Step 7: `sb-status-cell`** (`ui/status-cell.ts`). Add `import { Hint } from './hint';`; `imports: [StatusIndicator],` → `imports: [StatusIndicator, Hint],`. Above the `@Component` add

```ts
/** v194 A3: what the two ends of a trailing runner's bar are. */
export const STATUS_ENDS_HINT = 'Left figure: P&L if the trailing stop is hit. Right figure: P&L at the best price since TP1.';
/** v194 A3: why "delayed" shows. */
export const STATUS_STALE_HINT = "This position's price could not be freshly fetched; the number shown may be delayed.";
```

Template `:86`: `<span class="end neg" title="P&L if the trailing stop is hit">{{ e.stop }}</span>` → `<span class="end neg">{{ e.stop }}</span>`. `:103`: `<span class="end pos" title="P&L at the best price since TP1">{{ e.best }}</span>` →

```html
          <span class="end pos">{{ e.best }}</span>
          <sb-hint [text]="endsHint" label="About the two P&L figures" align="left" />
```

`:107-111`:

```html
          <span
            class="hint stale"
            title="This position's price could not be freshly fetched -- the number shown may be delayed."
          >delayed</span>
```
→
```html
          <span class="hint stale">delayed</span>
          <sb-hint [text]="staleHint" label="About delayed prices" align="left" />
```

In the class: `protected readonly endsHint = STATUS_ENDS_HINT;` and `protected readonly staleHint = STATUS_STALE_HINT;`.

- [ ] **Step 8: the tape** (`shell/tape/tape.ts`). Add `import { Hint } from '../../ui/hint';`; `imports: [RouterLink, Flash, AgeHint],` → `imports: [RouterLink, Flash, AgeHint, Hint],`. Above the `@Component`:

```ts
/** v194 A3: what a proxy tile's figure is. One hint for the lane: the tiles
 *  are links, and a hint button cannot sit inside a link. */
export const TAPE_PROXY_HINT = "Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price.";
```

`:80`: `<span class="ctx proxy" title="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price.">{{ tile.proxyLabel }}</span>` → `<span class="ctx proxy">{{ tile.proxyLabel }}</span>`. `:67` `<div class="cap">mkt</div>` →

```html
      <div class="cap-row">
        <div class="cap">mkt</div>
        @if (hasProxy()) {
          <sb-hint [text]="proxyHint" label="About proxy figures" align="left" />
        }
      </div>
```

After `protected readonly tiles = computed<Tile[]>(…)` (`:117`) add

```ts
  protected readonly hasProxy = computed(() => this.tiles().some((t) => t.proxyLabel !== null));
  protected readonly proxyHint = TAPE_PROXY_HINT;
```

In `tape.css`, `.cap-row` takes the box `.cap` had in the lane: `.cap-row { display: flex; align-items: center; gap: var(--space-4); flex: none; }` (move `.cap`'s `flex`/margin declarations onto `.cap-row` if it has any).

- [ ] **Step 9: Allow-list.** In `frontend/src/app/ui/title-usage.allow.ts` delete the nine entries whose note starts `V194-14b:` (tape proxy, `sb-panel` host, metric-card host, plan-cell `planTooltip` and `trailTooltip()`, stat-tile `sampleTitle()`, the two status-cell ends and the stale caveat).

- [ ] **Step 10: Run.** The Step 2 command plus `--include src/app/ui/title-usage.spec.ts`. Expected: PASS. Then the whole frontend run: specs that read a panel's or metric card's host `title` elsewhere fail here — `git -C "$WT" grep -n "getAttribute('title')" frontend/src/app -- '*.spec.ts'` lists them; move each to the hint's `[role="tooltip"]` text the same way as Step 1.

Close: standard (test: `frontend/src/app/ui/title-usage.spec.ts`); commit `feat(v194): shared primitives explain through sb-hint, not native titles (V194-14b)`.

### Task V194-15: A3 part 3 — convert the Calendar, Dashboard and Trades explanation titles

**Model:** sonnet — twenty title → `sb-hint` / visible-text conversions across known templates, each with its spec assertion moved.

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/day/calendar-day.ts:105,131,136,137,170,176,184,196`
- Modify: `frontend/src/app/workspaces/calendar/day/day-trade-card.ts:40,54`
- Modify: `frontend/src/app/workspaces/calendar/day/trade-sparkline.ts:122`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (`#numCell` partial icon, `:243`, `:439`, `:483`)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts:113,135,276`
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts:110-111`
- Modify: `frontend/src/app/workspaces/trades/trades.ts:217-224` and the `#numCell` partial icon
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts:107,174`
- Modify: `frontend/src/app/workspaces/trades/position-card.ts:52-53`, `frontend/src/app/workspaces/trades/why/sizing-panel.ts:9,26-27`, `frontend/src/app/workspaces/trades/why/why-panel.ts:27,60,92`
- Modify: `frontend/src/app/ui/title-usage.allow.ts` (delete the 20 entries noted `V194-15`)
- Test: `calendar/day/calendar-day.spec.ts:272,280,290-295`, `calendar/day/day-trade-card.spec.ts`, `calendar/day/trade-sparkline.spec.ts:139`, `dashboard/dashboard.spec.ts`, `dashboard/panels/equity-candles.spec.ts:428-436`, `dashboard/trade-drawer.spec.ts`, `trades/trades.spec.ts`, `trades/trade-detail.spec.ts:~428-431`, `trades/position-card.spec.ts:30-37`, `trades/why/sizing-panel.spec.ts:40-47`, `trades/why/why-panel.spec.ts:105,145` (all under `frontend/src/app/workspaces/`; existing specs asserting the old titles move with the templates)

**Interfaces:**
- Consumes: `Hint`; `StatTile.about` (V194-11, `input<string | undefined>`, renders `<sb-hint>` labelled `'About ' + label()`); `R_TOOLTIP` (`calendar/day/day-copy.ts:13`); `CHANGE_PCT_TOOLTIP` (`dashboard/panels/equity-candles.model.ts:23`); `partialOpenTitle` (`ui/status-cell.ts:230`); V194-13's `#numCell` layout (link, then `.leg` span); `TITLE_ALLOW`.
- Produces: `EXPORT_HINT` (`trades.ts`), `PAPER_HINT` (`trade-drawer.ts`), `GAP_FRAGILE_HINT` (`why/sizing-panel.ts`), `WHY_UNEVALUATED_HINT`, `WHY_GATE_OFF_HINT` (`why/why-panel.ts`). Nothing later consumes them.

**Depends on V194-13** (same `#numCell` templates in `trades.ts` and `dashboard.ts`) and V194-11 (`StatTile.about`). A hint never goes inside an `<a>`/`sb-row-link`.

- [ ] **Step 1: Move the spec assertions (they fail first).** Paths below are under `frontend/src/app/workspaces/`.

`calendar/day/calendar-day.spec.ts`: `:272`
```ts
    expect(root.querySelector('.mtd-r')?.getAttribute('title')).toBe(R_TOOLTIP);
```
→
```ts
    expect(root.querySelector('.mtd-r')?.hasAttribute('title')).toBe(false);
    expect(root.querySelector('.mtd-r + sb-hint [role="tooltip"]')?.textContent?.trim()).toBe(R_TOOLTIP);
```
`:280`
```ts
    expect(el(fixture).querySelector('.breakdown thead th.r-head')?.getAttribute('title')).toBe(R_TOOLTIP);
```
→
```ts
    expect(el(fixture).querySelector('.breakdown thead th.r-head')?.hasAttribute('title')).toBe(false);
    const drove = [...el(fixture).querySelectorAll('sb-panel')].find((p) => p.querySelector('h2')?.textContent?.trim() === 'What drove it')!;
    expect(drove.querySelector('header sb-hint [role="tooltip"]')?.textContent?.trim()).toBe(R_TOOLTIP);
    const tileHints = el(fixture).querySelectorAll('.tiles sb-stat-tile sb-hint');
    expect(tileHints).toHaveLength(3);
    expect(el(fixture).querySelector('.tiles [title]')).toBeNull();
```
and in `greys win% out below five rows…` after `expect(cellOf(thin)?.classList.contains('withheld')).toBe(true);` add `expect(cellOf(thin)?.hasAttribute('title')).toBe(false);` (the `.win-note` line already says it visibly).

`calendar/day/day-trade-card.spec.ts`: the assertion that reads `R_TOOLTIP` off the `.r` figure's `title` becomes
```ts
    expect(el.querySelector('.r')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.r + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(R_TOOLTIP);
```
(using that test's own root element variable; if no test reads it yet, add these two lines to the first test that renders `TRADE`).

`calendar/day/trade-sparkline.spec.ts:139`: `.toBe('—')` → `.toBe('no cached bars')`, and add `expect(el.querySelector('.spark-empty')?.hasAttribute('title')).toBe(false);`.

`dashboard/panels/equity-candles.spec.ts:434-435`:
```ts
    expect(pctPart.getAttribute('title'))
      .toBe("Change from the previous candle's close, not a return on capital");
```
→
```ts
    expect(pctPart.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.readout sb-hint [role="tooltip"]')!.textContent!.trim())
      .toBe("Change from the previous candle's close, not a return on capital");
```

`dashboard/dashboard.spec.ts`: add `import { partialOpenTitle } from '../../ui/status-cell';` and append
```ts
describe('Dashboard — explanations are hints, not titles (v194 A3)', () => {
  it('explains a partly closed position in a hint outside the row link', async () => {
    const row = tradeRow({ id: 'p9', status: 'PARTIAL', status_label: 'PARTIAL', banked_fraction: 0.5 });
    const el = await loadedWithRows([row]);
    expect(el.querySelector('sb-row-link sb-hint')).toBeNull();
    const texts = [...el.querySelectorAll('sb-positions-table sb-hint [role="tooltip"]')].map((n) => n.textContent!.trim());
    expect(texts).toContain(partialOpenTitle(row)!);
    expect(el.querySelector('.leg-icon[title]')).toBeNull();
  });

  it('defines the P&L and expected-R cells in the positions help, not on each cell', async () => {
    const el = await loadedWithRows([tradeRow({ status: 'ACTIVE', status_label: 'ACTIVE', exit_price: null, pnl_pct: null })]);
    expect(el.querySelector('.pnl-plan[title], .expected[title]')).toBeNull();
    const help = el.querySelector('.lifecycle-hint')!.textContent!;
    expect(help).toContain('live P&L, then projected P&L at target and at stop');
    expect(help).toContain('projected R if price reaches target');
  });
});
```

`dashboard/trade-drawer.spec.ts`: add `PAPER_HINT` to its import from `./trade-drawer` and append inside its top-level `describe` (mount it the way its existing "Paper trade" marker test does):
```ts
  it('explains the paper marker in a hint, not a native title (v194 A3)', () => {
    const el = mountDrawer(tradeRow());
    expect(el.querySelector('.paper-marker')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.paper-marker-row sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(PAPER_HINT);
  });
```
where `mountDrawer` is that existing marker test's mounting lines extracted into `function mountDrawer(row: TradeRow): HTMLElement` beside `tradeRow` (`:22`), and the marker test calls it.

`trades/trades.spec.ts`: add `EXPORT_HINT` to the import from `./trades` (now `ROW_COUNT_NOTE, EXPORT_HINT, Trades, TRADES_CONTROLS`), add `import { partialOpenTitle } from '../../ui/status-cell';`, and append
```ts
describe('Trades — explanations are hints, not titles (v194 A3)', () => {
  it('says the export ignores the filters, in a hint beside the link', () => {
    const el = render().nativeElement as HTMLElement;
    expect(el.querySelector('a.export')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.export-wrap sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(EXPORT_HINT);
  });

  it('explains a partly closed position in a hint outside the row link', () => {
    const r = row({ status: 'PARTIAL', status_label: 'PARTIAL', banked_fraction: 0.25, exit_price: null });
    const el = renderRows([r]);
    expect(el.querySelector('sb-row-link sb-hint')).toBeNull();
    const texts = [...el.querySelectorAll('sb-hint [role="tooltip"]')].map((n) => n.textContent!.trim());
    expect(texts).toContain(partialOpenTitle(r)!);
  });
});
```

`trades/trade-detail.spec.ts`, the COHORT_POOR test's two host-title lines and the comment above them:
```ts
    const host = el.querySelector('.tags > sb-chip')!;
    expect(host.getAttribute('title')).toContain('41.2% WR');
    expect(host.getAttribute('title')).toContain('-0.38R');
```
→
```ts
    expect(el.querySelector('.tags > sb-chip')!.hasAttribute('title')).toBe(false);
    const hint = el.querySelector('.tags > sb-chip + sb-hint [role="tooltip"]')!.textContent!;
    expect(hint).toContain('41.2% WR');
    expect(hint).toContain('-0.38R');
```

`trades/position-card.spec.ts`, after `expect(el.querySelector('sb-chip')?.textContent).toContain('fragile');` (`:36`) add
```ts
    expect(el.querySelector('sb-chip')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('sb-chip + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(GAP_FRAGILE_HINT);
```
with `import { GAP_FRAGILE_HINT } from './why/sizing-panel';`.

`trades/why/sizing-panel.spec.ts:44-45`:
```ts
    expect(chip?.getAttribute('title'))
      .toBe('The stop sits inside 90th-percentile gap noise: an overnight gap can jump it.');
```
→
```ts
    expect(chip!.hasAttribute('title')).toBe(false);
    expect(f.nativeElement.querySelector('dl > div:last-child sb-hint [role="tooltip"]')!.textContent!.trim())
      .toBe('The stop sits inside 90th-percentile gap noise: an overnight gap can jump it.');
```

`trades/why/why-panel.spec.ts`: add `WHY_GATE_OFF_HINT, WHY_UNEVALUATED_HINT` to the import from `./why-panel`; `:105`
```ts
    expect(f.nativeElement.querySelector('[title="no data — neutral points awarded"]')).not.toBeNull();
```
→
```ts
    const factorHints = [...f.nativeElement.querySelectorAll('.factor-row sb-hint [role="tooltip"]')].map((n: Element) => n.textContent!.trim());
    expect(factorHints).toContain(WHY_UNEVALUATED_HINT);
```
`:145`
```ts
    expect(f.nativeElement.querySelector('[title="off in current config"]').textContent).toContain('off');
```
→
```ts
    expect(f.nativeElement.querySelector('.gate-summary sb-chip').textContent).toContain('off');
    expect(f.nativeElement.querySelector('.gate-summary sb-hint [role="tooltip"]').textContent.trim()).toBe(WHY_GATE_OFF_HINT);
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/day --include src/app/workspaces/dashboard --include src/app/workspaces/trades`. Expected: FAIL — titles present, new constants not exported.

- [ ] **Step 3: Calendar** (`calendar/day/`).
  - `calendar-day.ts`: add `import { Hint } from '../../../ui/hint';`, add `Hint` to `imports` (`:105`).
  - `:131`, `:136`, `:137`: `[attr.title]="rTooltip"` → `[about]="rTooltip"` on each of the three `sb-stat-tile`s (Total, Average trade, Worst drawdown).
  - `:170`: `<span class="mtd-r" [title]="rTooltip">{{ r(store.monthCtx()?.mtdR ?? null) }}</span>` → `<span class="mtd-r">{{ r(store.monthCtx()?.mtdR ?? null) }}</span><sb-hint [text]="rTooltip" label="About R" align="left" />`.
  - `:176`: `<sb-panel heading="What drove it" [divided]="true">` → `<sb-panel heading="What drove it" [divided]="true" [description]="rTooltip">`; `:184`: `<th class="num r-head" [title]="rTooltip">R</th>` → `<th class="num r-head">R</th>` (a hint inside the `th` would join the column heads' text).
  - `:196`: delete ` [attr.title]="breakdownWinRate(row) === absent ? winNote : null"` from the `td.win`; the `.win-note` line already prints `winNote`.
  - `day-trade-card.ts`: add the `Hint` import and to `imports: [Chip, RouterLink, TradeSparkline]` (`:40`); `:54` `<span class="r" [title]="rTooltip" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span>` → `<span class="r" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span><sb-hint [text]="rTooltip" label="About R" align="left" />` (the card is an `<article>`, not a link).
  - `trade-sparkline.ts:122`: `<span class="spark-empty" title="No cached daily bars for this row">—</span>` → `<span class="spark-empty">no cached bars</span>`.

- [ ] **Step 4: Dashboard.**
  - `dashboard.ts` `#numCell` (as left by V194-13): inside `sb-row-link`
    ```html
            @if (partialOpenTitle(row); as openTitle) {
              <sb-icon name="partial" class="leg-icon" [title]="openTitle" />
            }
    ```
    →
    ```html
            @if (partialOpenTitle(row)) {
              <sb-icon name="partial" class="leg-icon" />
            }
    ```
    and directly after `</sb-row-link>` (before V194-13's `@if (legLabel(row); as leg)`):
    ```html
          @if (partialOpenTitle(row); as openTitle) {
            <sb-hint [text]="openTitle" label="About this partial position" align="left" />
          }
    ```
  - `:439`: delete the line `title="Live P&L, then projected P&L at target and at stop"` from `<span class="pnl-plan">`; `:483`: delete `title="Projected R if price reaches target"` from the `.expected` span.
  - `:243`, after `<sb-plan-lifecycle-diagram />` in the `.lifecycle-hint`:
    ```html
            <span class="hint-heading">Columns</span>
            <span class="hint-copy">
              <strong>P&amp;L:</strong> live P&L, then projected P&L at target and at stop.
              <strong>Expected R:</strong> projected R if price reaches target.
            </span>
    ```
  - `panels/equity-candles.ts`: add the `Hint` import (`'../../../ui/hint'`) and to `imports: [Async, Segmented, Button]` (`:113`); `:134-135`
    ```html
          <span class="part" [attr.data-tone]="part.tone"
                [attr.title]="isChangePart(part.text) ? changeTooltip : null">{{ part.text }}</span>
    ```
    →
    ```html
          <span class="part" [attr.data-tone]="part.tone">{{ part.text }}</span>
    ```
    and after that `@for` block, still inside `<p class="readout">`:
    ```html
        @if (hasChange()) {
          <sb-hint [text]="changeTooltip" label="About the change figure" align="left" />
        }
    ```
    with, after `protected readonly isChangePart = isChangePart;` (`:276`):
    ```ts
      /** v194 A3: the change figure's definition, once, when the readout has one. */
      protected readonly hasChange = computed(() => this.readout().some((p) => isChangePart(p.text)));
    ```
  - `trade-drawer.ts`: above `PAPER_MARKER` add
    ```ts
    /** v194 A3: what the marker means, in a hint (a native title never shows on a phone). */
    export const PAPER_HINT = 'The bot places no orders: every trade on this page is a paper trade.';
    ```
    `:110-111`
    ```html
          <span drawer-header class="paper-marker"
                title="The bot places no orders: every trade on this page is a paper trade.">{{ paperMarker }}</span>
    ```
    →
    ```html
          <span drawer-header class="paper-marker-row">
            <span class="paper-marker">{{ paperMarker }}</span>
            <sb-hint [text]="paperHint" label="About paper trades" align="left" />
          </span>
    ```
    styles: `.paper-marker-row { display: inline-flex; align-items: center; gap: var(--space-4); }`; class: `protected readonly paperHint = PAPER_HINT;` (`Hint` is already imported by V194-13).

- [ ] **Step 5: Trades.**
  - `trades.ts`: beside `ROW_COUNT_NOTE` add `export const EXPORT_HINT = 'Downloads the entire trade log. The filters above do not narrow it.';`; `:217-224`
    ```html
          <a
            slot="export"
            class="export"
            [href]="store.exportUrl()"
            title="Downloads the entire trade log. The filters above do not narrow it."
            download
            >Export CSV</a
          >
    ```
    →
    ```html
          <span slot="export" class="export-wrap">
            <a class="export" [href]="store.exportUrl()" download>Export CSV</a>
            <sb-hint [text]="exportHint" label="About the CSV export" align="left" />
          </span>
    ```
    style `.export-wrap { display: inline-flex; align-items: center; gap: var(--space-4); }`; class `protected readonly exportHint = EXPORT_HINT;`. The comment above (`:212-216`) ends "The title names what comes out" → "The hint names what comes out".
  - `#numCell`: the same two edits as the Dashboard's in Step 4.
  - `trade-detail.ts`: `Hint` import and into the `imports` array (`:107`); `:174` `<sb-chip [label]="cohortChipLabel()" [tone]="tone" [title]="cohortTooltip()" />` → `<sb-chip [label]="cohortChipLabel()" [tone]="tone" /><sb-hint [text]="cohortTooltip()" label="About the cohort chip" align="left" />`.
  - `why/sizing-panel.ts`: export `GAP_FRAGILE_HINT = 'The stop sits inside 90th-percentile gap noise: an overnight gap can jump it.';` above its `@Component`; `imports: [Panel, Chip]` → `[Panel, Chip, Hint]` (import from `'../../../ui/hint'`); `:26-27`
    ```html
              <sb-chip label="fragile" tone="warn" [caps]="false"
                title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." />
    ```
    → `<sb-chip label="fragile" tone="warn" [caps]="false" /><sb-hint [text]="fragileHint" label="About fragile stops" align="left" />`, class `protected readonly fragileHint = GAP_FRAGILE_HINT;`.
  - `position-card.ts:52-53`: the same chip edit; `import { GAP_FRAGILE_HINT } from './why/sizing-panel';`, `Hint` into its `imports`, class `protected readonly fragileHint = GAP_FRAGILE_HINT;`.
  - `why/why-panel.ts`: export
    ```ts
    export const WHY_UNEVALUATED_HINT = 'No data: neutral points awarded.';
    export const WHY_GATE_OFF_HINT = 'This gate is off in the current config.';
    ```
    `imports: [Panel, Chip, InlineMd]` → add `Hint`; `:60` `<sb-chip label="unevaluated" tone="muted" [caps]="false" title="no data — neutral points awarded" />` → `<sb-chip label="unevaluated" tone="muted" [caps]="false" /><sb-hint [text]="unevaluatedHint" label="About unevaluated factors" align="left" />`; `:92` `@if (!gate.applies) { <sb-chip label="off" [caps]="false" title="off in current config" /> }` → `@if (!gate.applies) { <sb-chip label="off" [caps]="false" /><sb-hint [text]="gateOffHint" label="About gates that are off" align="left" /> }`; class `protected readonly unevaluatedHint = WHY_UNEVALUATED_HINT;` and `protected readonly gateOffHint = WHY_GATE_OFF_HINT;`.

- [ ] **Step 6: Allow-list.** Delete the 20 entries whose note starts `V194-15:` from `frontend/src/app/ui/title-usage.allow.ts`.

- [ ] **Step 7: Run.** The Step 2 command plus `--include src/app/ui/title-usage.spec.ts`. Expected: PASS. One Playwright screenshot of the Calendar day view and the Dashboard positions table at 390 (hint glyphs 44px, nothing overlapping the `#` column).

Close: standard (test: `frontend/src/app/ui/title-usage.spec.ts`); commit `feat(v194): Calendar, Dashboard and Trades explain through sb-hint, not native titles (V194-15)`.
