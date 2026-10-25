# v194 — UI integrity, part 5: leg surfaces and the title audit (V194-13..V194-15)

> **For agentic workers:** constraints, `### Standard task close`, `## Handoff` and `## Parallelisation` live in the index: [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md). Pull one task at a time: `grep -n "^### Task V194-14:" -A 400 <this file>`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — § B3, § A3

`WT` below is the v194 worktree's absolute path; all frontend paths are under `frontend/src/app/`. Line numbers are those on `main` at plan time; where an earlier task moved them, the task says "as left by V194-n" and the edit anchors on the quoted snippet, never on a line number alone.

# Phase 5 — Legs named, titles that explain become hints

### Task V194-13: B3 surfaces — leg label and hint on Trades and the Dashboard; the row total says "rows"; missing-FX-rate caveat

**Model:** sonnet — template swaps and one helper at known sites, every name fixed by V194-6c and V194-12.

**Spec:** § B3. Two icons stand for "this row is a leg" today (`<sb-icon name="partial" title="Closed after an earlier partial exit …">`), saying nothing a tap can open and nothing about which leg. After this task every leg row shows **"Leg N of M[ · reason]"** beside its id, followed by an `sb-hint` reading `LEG_HINT_TEXT` (plus the open-partial sentence where one applies). The Trades page states what its total counts: **the API's `total` is `len(rows)` after legs are expanded (`swingbot/admin/api_v1/trades.py:1086`), so it counts rows (legs), not plans**; the live-region summary reads "N rows" and a one-line note under the table says so whenever a leg row is on the page. The same task shows the missing-FX-rate caveat (V194-6b/6c) on Trades and the Dashboard. The label and hint sit **beside** the `sb-row-link`, not inside it: the link renders an `<a>`, and a hint button nested in an anchor would navigate on tap.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts` (add the exported helper `legHintText` at the end of the file)
- Modify: `frontend/src/app/workspaces/trades/trades.ts:51` (status-cell import), `:133` (imports array), `:364` (`</sb-async>`), `:386-397` (`#numCell` leg icons), `:563` (styles), `:850-853` (`announce`), `:962-972` (`partialOpenTitle` / `isPartialLeg`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:33` (status-cell import), `:150` (imports array), `:200-201` (`<sb-trading-performance`), `:390-402` (`#numCell`), `:579` (styles), `:983-992`
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts:72-90` (`tradeDrawerFields`), `:104-122` (template), `:190-194` (class)
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes (V194-12): `legLabel(row: LegLike): string | null` and `LEG_HINT_TEXT` from `workspaces/trades/leg-label.ts`; `TradeRow.leg_exit_reason?: string | null`. (V194-6c): `fxMissingText(n: number): string` and `fxMissingOf(...payloads): number` from `workspaces/analytics/scope-bar.ts`; `TradeRow.fx_missing?: boolean`; `fx_missing_count?: number` on `Dashboard` and `Dashboard.realized`. Existing: `partialOpenTitle(row)` (`ui/status-cell.ts:230`, returns `string | null`), `Hint` (`ui/hint.ts`).
- Produces: `legHintText(row: TradeRow): string | null` exported from `trades.columns.ts`. Class hooks the specs and the V194-17 audit use: `.leg-label`, `.leg-note`, `.fx-note`.

- [ ] **Step 1: Write the failing tests.** Run `git grep -n "leg-icon" -- 'frontend/src/**/*.spec.ts'` first: any spec that reads the old partial `.leg-icon` title moves to the `.leg-label` assertions below.

In `trades.spec.ts`: extend `FooterFixture` (`:80-85`) with `items?: TradeRow[]`, and in `render()` (`:93`) replace the seeded `items: footer.total > 0 ? [row({})] : [],` inside its `patchState` call with `items: footer.items ?? (footer.total > 0 ? [row({})] : []),`. Add imports `legLabel, LEG_HINT_TEXT` from `./leg-label`, `legHintText` from `./trades.columns`, `partialOpenTitle` from `../../ui/status-cell`, `fxMissingText` from `../analytics/scope-bar`. Append:

```ts
describe('legHintText (v194 B3)', () => {
  it('is null for a plain single-leg row', () => {
    expect(legHintText(row({ leg_index: 0, leg_total: 1 }))).toBeNull();
  });

  it('is the plans-not-legs sentence for a leg row', () => {
    expect(legHintText(row({ leg_index: 1, leg_total: 2 }))).toBe(LEG_HINT_TEXT);
  });

  it('adds the open-partial sentence after it when both apply', () => {
    const open = row({ leg_index: 0, leg_total: 2, status: 'TP1_HIT', open_shares: 3 });
    expect(partialOpenTitle(open), 'fixture must be an open partial').not.toBeNull();
    expect(legHintText(open)).toBe(`${LEG_HINT_TEXT} ${partialOpenTitle(open)}`);
  });

  it('is only the open-partial sentence for a single-leg open partial', () => {
    const open = row({ leg_index: 0, leg_total: 1, status: 'TP1_HIT', open_shares: 3 });
    expect(partialOpenTitle(open), 'fixture must be an open partial').not.toBeNull();
    expect(legHintText(open)).toBe(partialOpenTitle(open));
  });
});

describe('Trades — leg rows (v194 B3)', () => {
  const legs = [
    row({ id: 'plan-abc123', leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' }),
    row({ id: 'plan-abc123', leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' }),
  ];
  const mount = (items: TradeRow[]) =>
    render({ total: items.length, page: 1, perPage: 12, items }).nativeElement as HTMLElement;
  const announceOf = (f: ComponentFixture<Trades>) =>
    (f.componentInstance as unknown as { announce(): string | null }).announce();

  it('names each leg beside its id, with its exit reason', () => {
    const labels = [...mount(legs).querySelectorAll('.leg-label')].map((el) => el.textContent!.trim());
    expect(labels).toEqual([legLabel(legs[0])!, legLabel(legs[1])!]);
    expect(labels[0]).toMatch(/^Leg 1 of 2 · /);
    expect(labels[1]).toMatch(/^Leg 2 of 2 · /);
  });

  it('keeps the label and hint out of the row link', () => {
    const el = mount(legs);
    expect(el.querySelector('a.row-link .leg-label')).toBeNull();
    expect(el.querySelector('a.row-link sb-hint')).toBeNull();
  });

  it('shows no label and no note for a single-leg trade', () => {
    const el = mount([row({ leg_index: 0, leg_total: 1 })]);
    expect(el.querySelector('.leg-label')).toBeNull();
    expect(el.querySelector('.leg-note')).toBeNull();
  });

  it('puts the plans-not-legs hint beside the label', () => {
    const tip = mount(legs).querySelector('.leg-label + sb-hint [role="tooltip"]')!;
    expect(tip.textContent!.trim()).toBe(LEG_HINT_TEXT);
    expect(LEG_HINT_TEXT).toContain('plans, not legs');
  });

  it('states that the total counts rows, not plans', () => {
    const fixture = render({ total: 2, page: 1, perPage: 12, items: legs });
    expect(announceOf(fixture)).toBe('2 rows');
    expect((fixture.nativeElement as HTMLElement).querySelector('.leg-note')!.textContent).toContain('Rows, not plans');
  });

  it('says "1 row" for a lone row', () => {
    expect(announceOf(render({ total: 1, page: 1, perPage: 12 }))).toBe('1 row');
  });
});

describe('Trades — missing exchange rate caveat (v194 B7)', () => {
  it('names how many rows on the page lack a rate', () => {
    const items = [row({ fx_missing: true }), row({ id: 't2', fx_missing: true }), row({ id: 't3' })];
    const el = render({ total: 3, page: 1, perPage: 12, items }).nativeElement as HTMLElement;
    expect(el.querySelector('.fx-note')!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('prints nothing when every row has a rate', () => {
    const el = render({ total: 1, page: 1, perPage: 12 }).nativeElement as HTMLElement;
    expect(el.querySelector('.fx-note')).toBeNull();
  });
});
```

(If the two open-partial fixtures do not satisfy `partialOpenTitle`, read how `ui/status-cell.spec.ts` builds an open partial and reuse that row shape rather than guessing fields.)

In `dashboard.spec.ts` add imports `legLabel, LEG_HINT_TEXT` (from `../trades/leg-label`), `fxMissingText` (from `../analytics/scope-bar`), `tradeDrawerFields` (from `./trade-drawer`) and append (`tradeRow` is the spec's own factory at `:125`, `loadedWithRows` at `:409`, `loaded` at `:223`):

```ts
describe('Dashboard — leg rows (v194 B3)', () => {
  const legs = [
    tradeRow({ id: 'plan-xyz789', leg_index: 0, leg_total: 3, leg_exit_reason: 'tp1' }),
    tradeRow({ id: 'plan-xyz789', leg_index: 1, leg_total: 3, leg_exit_reason: 'timeout' }),
    tradeRow({ id: 'plan-xyz789', leg_index: 2, leg_total: 3, leg_exit_reason: 'stop' }),
  ];

  it('labels every leg of a three-leg plan, with its reason', async () => {
    const el = await loadedWithRows(legs);
    const labels = [...el.querySelectorAll('.leg-label')].map((n) => n.textContent!.trim());
    expect(labels).toEqual(legs.map((r) => legLabel(r)!));
    expect(labels[2]).toMatch(/^Leg 3 of 3/);
  });

  it('labels a leg with no recorded reason by the bare label', async () => {
    const el = await loadedWithRows([tradeRow({ leg_index: 0, leg_total: 2, leg_exit_reason: null })]);
    expect(el.querySelector('.leg-label')!.textContent!.trim()).toBe('Leg 1 of 2');
  });

  it('shows no label for a single-leg trade', async () => {
    const el = await loadedWithRows([tradeRow({ leg_index: 0, leg_total: 1 })]);
    expect(el.querySelector('.leg-label')).toBeNull();
  });

  it('opens a hint that says plans, not legs, outside the row link', async () => {
    const el = await loadedWithRows(legs);
    expect(el.querySelector('.leg-label + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(LEG_HINT_TEXT);
    expect(el.querySelector('a.row-link sb-hint')).toBeNull();
  });

  it('lists the leg in the row drawer fields, and only for a leg', () => {
    expect(tradeDrawerFields(legs[0], '$', Date.now()).find((f) => f.key === 'leg')!.value).toBe(legLabel(legs[0]));
    const single = tradeDrawerFields(tradeRow({ leg_total: 1, leg_index: 0 }), '$', Date.now());
    expect(single.some((f) => f.key === 'leg')).toBe(false);
  });
});

describe('Dashboard — missing exchange rate caveat (v194 B7)', () => {
  it('shows the count from the realised block', async () => {
    const fixture = await loaded({ realized: { amount: 42.5, pct: 0.6, n: 3, wins: 2, losses: 1, fx_missing_count: 2 } });
    expect((fixture.nativeElement as HTMLElement).querySelector('.fx-note')!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('shows nothing when no rate is missing', async () => {
    const fixture = await loaded();
    expect((fixture.nativeElement as HTMLElement).querySelector('.fx-note')).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts`, then the same with `src/app/workspaces/dashboard/dashboard.spec.ts`. Expected: FAIL (`legHintText` undefined, no `.leg-label`, no `.fx-note`, `announce()` reads "2 trades").

- [ ] **Step 3: Add `legHintText` to `trades.columns.ts`.** Add `import { legLabel, LEG_HINT_TEXT } from './leg-label';` and `import { partialOpenTitle } from '../../ui/status-cell';` (and `TradeRow` from `'../../api/models'` if the file does not already import it), then append:

```ts
/** The hint beside a leg row's label: the plans-not-legs sentence for any leg, then
 *  the open-partial sentence where the row is a still-open partial. Null for a plain row. */
export function legHintText(row: TradeRow): string | null {
  const parts = [legLabel(row) === null ? null : LEG_HINT_TEXT, partialOpenTitle(row)];
  const present = parts.filter((p): p is string => p !== null);
  return present.length > 0 ? present.join(' ') : null;
}
```

- [ ] **Step 4: Trades template and class (`trades.ts`).**
  - Imports: add `import { Hint } from '../../ui/hint';` next to the other `ui/` imports and `Hint,` to the component `imports: [` array (`:133`, after `Async,`); add `import { legLabel, LEG_HINT_TEXT } from './leg-label';`, `legHintText` to the existing `./trades.columns` import, and `import { fxMissingText } from '../analytics/scope-bar';`. `:51`: `import { StatusCell, partialOpenTitle } from '../../ui/status-cell';` → `import { StatusCell } from '../../ui/status-cell';`.
  - `#numCell` (`:383-399`), old → new. The two icon blocks leave the link, the trailing icon stays inside it, and the pair lands right after the link:

```html
OLD (:389-397)
        @if (isPartialLeg(row)) {
          <sb-icon name="partial" class="leg-icon" title="Closed after an earlier partial exit of the same position" />
        }
        @if (partialOpenTitle(row); as openTitle) {
          <sb-icon name="partial" class="leg-icon" [title]="openTitle" />
        }
        @if (row.bar_kind === 'trailing') {
          <sb-icon name="trailing" class="leg-icon" title="Trailing stop" />
        }
      </sb-row-link>
NEW
        @if (row.bar_kind === 'trailing') {
          <sb-icon name="trailing" class="leg-icon" title="Trailing stop" />
        }
      </sb-row-link>
      @if (legLabel(row); as leg) { <span class="leg-label">{{ leg }}</span> }
      @if (legHintText(row); as legHint) { <sb-hint [text]="legHint" label="About leg rows" /> }
```
  - Class (`:962-972`): delete the doc comment, `protected readonly partialOpenTitle = partialOpenTitle;` (`:968`) and `isPartialLeg` (`:970-972`) once `git grep -n "isPartialLeg\|partialOpenTitle" frontend/src/app/workspaces/trades/trades.ts` shows no other reader; in their place:

```ts
  protected readonly legLabel = legLabel;
  protected readonly legHintText = legHintText;
  protected readonly legNoteHint = LEG_HINT_TEXT;
  protected readonly fxMissingText = fxMissingText;
  /** A leg row is on this page: the total counts rows, and the note under the table says so. */
  protected readonly hasLegRows = computed(() => this.store.rows().some((r) => r.leg_total > 1));
  protected readonly fxMissingRows = computed(() => this.store.rows().filter((r) => r.fx_missing).length);
```
  - `announce` (`:850-853`), the wording of `Pagination.rangeLabel` (`ui/pagination.ts:86`):

```ts
OLD   return page ? `${page.total} trades` : null;
NEW   return page ? `${page.total} ${page.total === 1 ? 'row' : 'rows'}` : null;
```
  - After `</sb-async>` (`:364`) add:

```html
    @if (hasLegRows()) {
      <p class="leg-note">Rows, not plans: a plan closed in parts lists one row per leg.
        <sb-hint [text]="legNoteHint" label="About leg rows" /></p>
    }
    @if (fxMissingRows() > 0) { <p class="fx-note" role="note">{{ fxMissingText(fxMissingRows()) }}</p> }
```
  - Styles (`:563`), existing tokens only:

```css
OLD     sb-row-link .leg-icon { color: var(--text-muted); flex: none; }
NEW     sb-row-link .leg-icon { color: var(--text-muted); flex: none; }
        .leg-label { color: var(--text-muted); font-size: 0.85em; white-space: nowrap; }
        .leg-note, .fx-note { margin: 0.5rem 0 0; color: var(--text-muted); font-size: 0.85em; }
```

- [ ] **Step 5: Dashboard (`dashboard.ts`).**
  - `:33` `import { StatusCell, partialOpenTitle } from '../../ui/status-cell';` → `import { StatusCell } from '../../ui/status-cell';`; `Hint` is already imported (`:51`) and listed in `imports:`; add `import { legLabel } from '../trades/leg-label';`, `legHintText` to the `../trades/trades.columns` import (add the import if the file has none), `import { fxMissingOf, fxMissingText } from '../analytics/scope-bar';`.
  - `#numCell` (`:390-402`): the same old → new as Trades Step 4 (the two icon blocks at `:394-399` go, the trailing icon stays in the link, the label and hint pair follows `</sb-row-link>`); the v79 comment above stays.
  - Class (`:983-992`): delete the doc comment, `partialOpenTitle` (`:988`) and `isPartialLeg` (`:990-992`) once `git grep -n "isPartialLeg\|partialOpenTitle" frontend/src/app/workspaces/dashboard/dashboard.ts` shows no other reader; add

```ts
  protected readonly legLabel = legLabel;
  protected readonly legHintText = legHintText;
  protected readonly fxMissingText = fxMissingText;
  protected readonly fxMissing = computed(() => fxMissingOf(this.store.realized(), this.store.todayRealized()));
```
  - Styles (`:579`): the same two-rule addition as Trades (`.leg-label`, `.leg-note, .fx-note`).
  - Template (`:200-201`):

```html
OLD     <div class="performance-stack">
        <sb-trading-performance
NEW     <div class="performance-stack">
        @if (fxMissing() > 0) { <p class="fx-note" role="note">{{ fxMissingText(fxMissing()) }}</p> }
        <sb-trading-performance
```

- [ ] **Step 6: Row drawer (`trade-drawer.ts`).** Imports: `import { legLabel } from '../trades/leg-label';`, `import { legHintText } from '../trades/trades.columns';`, `import { fxMissingText } from '../analytics/scope-bar';`. Above the `tradeDrawerFields` doc comment (`:72`) add:

```ts
/** One "Leg N of M · reason" field, only for a row that is a leg. */
function legFields(row: TradeRow): TradeDrawerField[] {
  const leg = legLabel(row);
  return leg === null ? [] : [field('leg', 'Leg', leg)];
}
```
  In `tradeDrawerFields` (`:78`):

```ts
OLD     field('status', 'Status', text(row.status_label || row.status)),
NEW     field('status', 'Status', text(row.status_label || row.status)),
        ...legFields(row),
```
  Class (`:190-194`) gains `protected readonly legNote = computed(() => legHintText(this.row()));` and `protected readonly fxMissingText = fxMissingText;`. Template, directly under `</dl>` (`:121`), plain visible text because the drawer has room (no hint):

```html
      </dl>
      @if (legNote(); as note) { <p class="leg-note">{{ note }}</p> }
      @if (row().fx_missing) { <p class="fx-note" role="note">{{ fxMissingText(1) }}</p> }
```
  and the styles gain `.leg-note, .fx-note { margin: 0.5rem 0 0; color: var(--text-muted); font-size: 0.85em; }`. Trades' own row drawer and compact rows render the same `#numCell` template, so they carry the label and hint with no further edit.

- [ ] **Step 7: Run to see them pass.** The two commands from Step 2. Expected: PASS, including the existing count-footer, plan-cell and Dashboard hint specs. If the compact row is reachable through `compactKeys` / `openRowDrawer` (`ui/data-table/testing/reachability`), add one assertion to the first leg test in `trades.spec.ts`: the drawer's number cell contains `.leg-label`.

- [ ] **Step 8: Screenshot check.** Playwright against the local replica at 390, 768 and 1440 on `/trades` and `/dashboard` with a partially exited plan on screen: the label stays on one line beside the id, the hint opens in the top layer, `.leg-note` wraps. One screenshot per width into the scratchpad directory; the full layout audit still runs once, in V194-17.

Close: standard (test: frontend/src/app/workspaces/trades/trades.spec.ts); also run the narrow `dashboard/dashboard.spec.ts`. Commit: `feat(v194): leg label and plans-not-legs hint on Trades and Dashboard, rows total stated, FX caveat (V194-13)`.

### Task V194-14: A3 part 1 — `title-usage.spec.ts` scanner, allow-list, and every explanation `title` outside Analytics becomes an `sb-hint`

**Model:** sonnet — one scanner spec plus per-site mechanical conversions, every site written as its own old → new.

**Spec:** § A3. A native `title` answers a mouse hover only; a tap or a keyboard focus never opens it. Each site is classified once (measured on `main` at plan time with the A3 counting rule in the index): **echo** (repeats a truncated or labelled value the row already shows) and **control name** (names an icon-only control) stay; **explanation** becomes an `sb-hint` beside the thing it explains, with the same words. A scanner spec then fails on any `title` binding not in the allow-list, so new explanation cannot hide in a `title` again. Analytics was inventoried too: its tab files hold no native-title explanation (every `title=` there is an `sb-panel-header` / `sb-confirm-dialog` input, which the scanner skips by element), so `TITLE_PENDING` starts empty and V194-15 only locks that in. `workspaces/gallery/gallery.ts` appears in the ledger but holds only `sb-empty-state` / `sb-panel-header` / `sb-confirm-dialog` inputs: no edit.

**Files:**
- Create: `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`, `frontend/src/app/testing/hint-text.ts`
- Modify (conversions, Step 3; each adds `Hint` to the component's `imports:` and an import line when it renders one): `shell/tape/tape.ts`, `ui/layout.ts`, `ui/metric-card.ts`, `ui/stat-tile.ts`, `ui/plan-cell.ts`, `ui/status-cell.ts`, `workspaces/calendar/day/calendar-day.ts`, `workspaces/calendar/day/day-trade-card.ts`, `workspaces/calendar/day/trade-sparkline.ts`, `workspaces/cancels/cancels-summary.ts`, `workspaces/dashboard/dashboard.ts`, `workspaces/dashboard/panels/equity-candles.ts`, `workspaces/dashboard/trade-drawer.ts`, `workspaces/trades/position-card.ts`, `workspaces/trades/why/sizing-panel.ts`, `workspaces/trades/why/why-panel.ts`, `workspaces/trades/trade-detail.ts`, `workspaces/trades/trades.ts`, `workspaces/versions/versions.ts`, `workspaces/watchlist/watchlist.ts`, `workspaces/system/settings-tab.ts` (all under `frontend/src/app/`)
- Modify (specs that read a converted `title`, Step 5; the list is closed by Step 7): `shell/tape/tape.spec.ts`, `ui/layout.spec.ts`, `ui/metric-card.spec.ts`, `ui/stat-tile.spec.ts`, `ui/plan-cell.spec.ts`, `ui/status-cell.spec.ts` (grep), `workspaces/calendar/day/calendar-day.spec.ts`, `workspaces/calendar/day/day-trade-card.spec.ts`, `workspaces/dashboard/dashboard.spec.ts`, `workspaces/dashboard/panels/trading-performance.spec.ts`, `workspaces/dashboard/panels/equity-candles.spec.ts`, `workspaces/trades/trade-detail.spec.ts`, `workspaces/trades/why/sizing-panel.spec.ts`, `workspaces/trades/why/why-panel.spec.ts`

**Interfaces:**
- Consumes: `Hint` (`ui/hint.ts`; inputs `text`, `label`, `align`), `StatTile.about` (V194-11: `input<string | undefined>`, renders an `sb-hint` beside the label).
- Produces: `TitleSite { file: string; binding: string; kind: 'echo' | 'control-name' | 'explanation-pending'; note: string }` (`file` relative to `frontend/src/app/`, `binding` the matched attribute text exactly as written, or `host '[attr.title]'` for a component-metadata key); `TITLE_ALLOW: readonly TitleSite[]`; `TITLE_PENDING: readonly TitleSite[]` (the `explanation-pending` subset, empty); `TITLE_INPUT_ELEMENTS: readonly string[]` (`['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog']`); `hintTexts(root: ParentNode): string[]` in `testing/hint-text.ts` (the whitespace-collapsed text of every `sb-hint [role="tooltip"]` under `root`, in document order: the pop-up is in the DOM whether or not it is open, so specs read hint copy without opening it).

- [ ] **Step 1: Write the helper and the scanner spec.** `frontend/src/app/testing/hint-text.ts`:

```ts
/** The copy of every `sb-hint` under `root`, whitespace-collapsed, in document order. */
export function hintTexts(root: ParentNode): string[] {
  return [...root.querySelectorAll('sb-hint [role="tooltip"]')].map(
    (el) => el.textContent?.replace(/\s+/g, ' ').trim() ?? '',
  );
}
```

`frontend/src/app/ui/title-usage.spec.ts` (a source scan like `hint.spec.ts`'s `readFileSync`; `process.cwd()` is `frontend/`):

```ts
import { readdirSync, readFileSync } from 'node:fs';
import { join, sep } from 'node:path';

import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS } from './title-usage.allow';

const APP = join(process.cwd(), 'src/app');
const ATTR = /(?:^|\s)(\[attr\.title\]|\[title\]|title)="([^"]*)"/g;
const HOST = /'\[attr\.title\]'\s*:/;

interface Found { file: string; binding: string; element: string }

function sourceFiles(): string[] {
  return (readdirSync(APP, { recursive: true }) as string[])
    .map((p) => p.split(sep).join('/'))
    .filter((p) => p.endsWith('.ts') && !p.endsWith('.spec.ts') && !p.startsWith('testing/'));
}

/** The tag a binding at `index` belongs to: the nearest `<name` before it. */
function elementAt(src: string, index: number): string {
  const open = src.lastIndexOf('<', index);
  return /^<([a-z][\w-]*)/.exec(src.slice(open, open + 48))?.[1] ?? '';
}

function scan(): Found[] {
  const found: Found[] = [];
  for (const file of sourceFiles()) {
    const src = readFileSync(join(APP, file), 'utf8');
    for (const m of src.matchAll(ATTR)) {
      const element = elementAt(src, m.index!);
      if (TITLE_INPUT_ELEMENTS.includes(element)) continue; // a heading input, not a tooltip
      found.push({ file, binding: `${m[1]}="${m[2]}"`, element });
    }
    if (HOST.test(src)) found.push({ file, binding: "host '[attr.title]'", element: 'host' });
  }
  return found;
}

const key = (s: { file: string; binding: string }) => `${s.file}::${s.binding}`;

describe('native title usage (v194 A3)', () => {
  const found = scan();

  it('finds the title sites it is meant to police (the scan is not vacuous)', () => {
    expect(found.length).toBeGreaterThan(10);
    expect(found.some((s) => s.file === 'ui/icon.ts' && s.element === 'host')).toBe(true);
  });

  it('allows only echoes and control names: explanation belongs in an sb-hint', () => {
    const allowed = new Set(TITLE_ALLOW.map(key));
    const rogue = found.filter((s) => !allowed.has(key(s))).map((s) => `${s.file} <${s.element}> ${s.binding}`);
    expect(rogue, `${found.length} sites scanned, ${rogue.length} unclassified`).toEqual([]);
  });

  it('has no stale allow-list entry', () => {
    const seen = new Set(found.map(key));
    expect(TITLE_ALLOW.filter((s) => !seen.has(key(s))).map(key)).toEqual([]);
  });
});
```

Create `title-usage.allow.ts` now with the types and three exports shown in Step 4 and `TITLE_ALLOW = []`, so the spec compiles and fails on every site.

- [ ] **Step 2: Run it to see it fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`. Expected: FAIL on "allows only echoes…" with the message `N sites scanned, N unclassified` and the list. **Record N: the commit message states it** (A3 counting rule). The list must match Steps 3 and 4; a site in it that neither names is classified at the site by the A3 rule and added to Step 4's entries (say so in the commit).

- [ ] **Step 3: Convert the explanation sites, shell and `ui/` first.** One recipe: delete the `title` binding, put `<sb-hint … label="About …" />` directly after the element it explained (same words as the old title; `[text]` for a binding, `text` for a literal), add `Hint` to the component's `imports:` and an `import { Hint } from '<relative>/ui/hint';` line (`'./hint'` inside `ui/`, `'../../ui/hint'` from `shell/tape/` and `workspaces/<x>/`, `'../../../ui/hint'` from `workspaces/<x>/<y>/`). Each block is one site, `-` the line as it stands on `main`, `+` its replacement; edit by the quoted text.

`shell/tape/tape.ts` (`imports: [RouterLink, Flash, AgeHint]` `:61` gains `Hint`):

```diff
 :65-67   the whole-lane tooltip leaves the region; the as-of time becomes a hint on the caption
-    <div class="lane" role="region" aria-label="Market tape"
-         [attr.title]="asOfTime() === ABSENT ? null : 'Tape data as of ' + asOfTime()">
-      <div class="cap">mkt</div>
+    <div class="lane" role="region" aria-label="Market tape">
+      <div class="cap">mkt@if (asOfTime() !== ABSENT) { <sb-hint [text]="'Tape data as of ' + asOfTime()" label="About the tape" /> }</div>
 :80      the proxy chip
-                  <span class="ctx proxy" title="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price.">{{ tile.proxyLabel }}</span>
+                  <span class="ctx proxy">{{ tile.proxyLabel }}<sb-hint text="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price." label="About this proxy" /></span>
```

`ui/layout.ts` (`sb-panel`; `Hint` is already imported). The host title is deleted with its comment; the header hint at `:52` already carries `description()`:

```diff
 :39-41   delete the `host` entry and the two comment lines above it
-  host: { '[attr.title]': 'description()' },
```
Then `git grep -n "description=\|\[description\]" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'`: every `<sb-panel>` that passes a description must also pass a heading, because without one no hint renders; fix any that does not. The `:261` `[attr.title]="tab.icon ? tab.label : null"` stays (control name).

`ui/metric-card.ts` (`:41` `imports: [CountUp, Spinner]` → `[CountUp, Spinner, Hint]`; `import { Hint } from './hint';`):

```diff
 :47      host entry deleted
-    '[attr.title]': 'description()',
 :52      template, after the label span
       <span class="label sb-label">{{ label() }}</span>
+      @if (description(); as about) { <sb-hint [text]="about" [label]="'About ' + label()" /> }
```

`ui/stat-tile.ts` (`:37` `imports: [Sparkline, CountUp]` → `[Sparkline, CountUp, Hint]`; `import { Hint } from './hint';`). The `.sample` div keeps `thin()`; the hint goes inside it, after the N text:

```diff
 :45-46
-        <div class="sample" [title]="sampleTitle()">
-          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample</span>}
+        <div class="sample">
+          N={{ sample() }}@if (thin()) {<span class="flag"> · thin sample</span>}@if (sampleTitle()) {<sb-hint [text]="sampleTitle()!" label="About this sample size" />}
```

`ui/plan-cell.ts` (the component has no `imports:` today: add `imports: [Hint],` after `changeDetection:` at `:26`; `import { Hint } from './hint';`). `:30` (`planTooltip`) and `:49` (`tooltip()`) stay as echoes; only the trail line converts:

```diff
 :39 and the `</span>` closing `.l2`
-          <span class="line l2" [title]="trailTooltip()">
+          <span class="line l2">
 …(body unchanged)…
           </span>
+          <sb-hint [text]="trailTooltip()" label="About the trailing stop" />
```

`ui/status-cell.ts` (`:74` `imports: [StatusIndicator]` → `[StatusIndicator, Hint]`; `import { Hint } from './hint';`). `:95` `[title]="row().status_label"` stays (echo of the progressbar's `aria-label`):

```diff
 :86
-          <span class="end neg" title="P&L if the trailing stop is hit">{{ e.stop }}</span>
+          <span class="end neg">{{ e.stop }}</span><sb-hint text="P&L if the trailing stop is hit" label="About the stop P&L" />
 :103
-          <span class="end pos" title="P&L at the best price since TP1">{{ e.best }}</span>
+          <span class="end pos">{{ e.best }}</span><sb-hint text="P&L at the best price since TP1" label="About the best-price P&L" />
 :107-112
-          <span
-            class="hint stale"
-            title="This position's price could not be freshly fetched -- the number shown may be delayed."
-          >delayed</span>
+          <span class="hint stale">delayed</span>
+          <sb-hint text="This position's price could not be freshly fetched -- the number shown may be delayed." label="About the delayed price" />
```

**Workspaces** (same recipe and notation):

`workspaces/calendar/day/calendar-day.ts` (`:105` imports gain `Hint`). The three `[attr.title]="rTooltip"` on stat tiles become V194-11's `about` input; the others get a hint beside the figure (the `<p class="r-note">` at `:139` keeps printing the same text, untouched):

```diff
 :131, :136, :137   the end of each of the three `sb-stat-tile`s (Total, Average trade, Worst drawdown)
-        <sb-stat-tile label="Total" [value]="r(day.total_r)" [sample]="day.trade_count" [attr.title]="rTooltip" />
+        <sb-stat-tile label="Total" [value]="r(day.total_r)" [sample]="day.trade_count" [about]="rTooltip" />
 (Average trade and Worst drawdown: ` [attr.title]="rTooltip" />` → ` [about]="rTooltip" />`, the rest of each line unchanged)
 :170
-            <span class="mtd-r" [title]="rTooltip">{{ r(store.monthCtx()?.mtdR ?? null) }}</span>
+            <span class="mtd-r">{{ r(store.monthCtx()?.mtdR ?? null) }}</span><sb-hint [text]="rTooltip" label="About R" />
 :184
-              <th class="num r-head" [title]="rTooltip">R</th>
+              <th class="num r-head">R<sb-hint [text]="rTooltip" label="About R" /></th>
 :196     the win-rate cell: the note appears only where the rate is withheld
-                <td class="num win" [class.withheld]="breakdownWinRate(row) === absent" [attr.title]="breakdownWinRate(row) === absent ? winNote : null">{{ breakdownWinRate(row) }}</td>
+                <td class="num win" [class.withheld]="breakdownWinRate(row) === absent">{{ breakdownWinRate(row) }}@if (breakdownWinRate(row) === absent) { <sb-hint [text]="winNote" label="Why no win rate" /> }</td>
```

`day-trade-card.ts`, `trade-sparkline.ts`, `cancels-summary.ts`, `trade-drawer.ts`, `trade-detail.ts`, `watchlist.ts`, `settings-tab.ts` each add `Hint` to `imports:` (`day-trade-card` `:40`, `trade-sparkline` `[RouterLink]` `:99`, `cancels-summary` `:34`, `trade-drawer` `:107`, `trade-detail` `:107`, `watchlist` `:174`, `settings-tab` `:33`). Staying: `trade-detail.ts:182` (echo), `settings-tab.ts:175` (echo) and `:201` (control name), `watchlist.ts:375` (a dialog input). `trade-drawer.ts` was edited by V194-13, so anchor on the quoted text:

```diff
 workspaces/calendar/day/day-trade-card.ts:54
-          <span class="r" [title]="rTooltip" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span>
+          <span class="r" [class.pos]="rSign() === 'pos'" [class.neg]="rSign() === 'neg'">{{ r(t.r_multiple) }}</span>
+          <sb-hint [text]="rTooltip" label="About R" />
 workspaces/calendar/day/trade-sparkline.ts:122
-      <span class="spark-empty" title="No cached daily bars for this row">—</span>
+      <span class="spark-empty">—<sb-hint text="No cached daily bars for this row" label="Why no chart" /></span>
 workspaces/cancels/cancels-summary.ts:38
-        <span class="small-n" title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate">N &lt; {{ data().small_n_threshold }}</span>
+        <span class="small-n">N &lt; {{ data().small_n_threshold }}<sb-hint [text]="'Fewer than ' + data().small_n_threshold + ' resolved plans: an anecdote, not a rate'" label="About small samples" /></span>
 workspaces/dashboard/trade-drawer.ts:110-111
-      <span drawer-header class="paper-marker"
-            title="The bot places no orders: every trade on this page is a paper trade.">{{ paperMarker }}</span>
+      <span drawer-header class="paper-marker">{{ paperMarker }}<sb-hint text="The bot places no orders: every trade on this page is a paper trade." label="About paper trades" /></span>
 workspaces/trades/trade-detail.ts:174
-              <sb-chip [label]="cohortChipLabel()" [tone]="tone" [title]="cohortTooltip()" />
+              <sb-chip [label]="cohortChipLabel()" [tone]="tone" /><sb-hint [text]="cohortTooltip()" label="About this cohort" />
 workspaces/watchlist/watchlist.ts:416
-        <span class="source-badge" title="Alpaca missed this quote; yfinance answered instead">fallback</span>
+        <span class="source-badge">fallback</span><sb-hint text="Alpaca missed this quote; yfinance answered instead" label="About the fallback quote" />
 workspaces/system/settings-tab.ts:181
-                    <span class="restart" title="Restart required to take effect">restart</span>
+                    <span class="restart">restart<sb-hint text="Restart required to take effect" label="About restart" /></span>
```

`workspaces/dashboard/dashboard.ts` (`Hint` already imported and listed; `:401` `title="Trailing stop"` stays, and `:395`/`:398` are V194-13's). Both sites lose the title and a hint follows the element:

```diff
 :437-441
         <span
           class="pnl-plan"
-          title="Live P&L, then projected P&L at target and at stop"
         >
 …                                  (the span's body and closing tag are unchanged)
+        <sb-hint text="Live P&L, then projected P&L at target and at stop" label="About this P&L" />
 :480-484   (the `.expected` span; its closing `</span>` is on the line with `{{ fmtSigned(expectedR(row)) }}`)
           [class]="pnlClass(expectedR(row))"
-          title="Projected R if price reaches target"
         >{{ fmtSigned(expectedR(row)) }}</span>
+        <sb-hint text="Projected R if price reaches target" label="About expected R" />
```

`workspaces/dashboard/panels/equity-candles.ts` (`:113` `imports: [Async, Segmented, Button]` gains `Hint`). `:163` `title="Back to today: chart and figures"` stays (control name). The hint sits between readout parts, so the middle-dot separator rule must also match a part that follows a hint, and the dotted-underline `help` cue that keyed on `[title]` goes:

```diff
 :134-135
-          <span class="part" [attr.data-tone]="part.tone"
-                [attr.title]="isChangePart(part.text) ? changeTooltip : null">{{ part.text }}</span>
+          <span class="part" [attr.data-tone]="part.tone">{{ part.text }}</span>
+          @if (isChangePart(part.text)) { <sb-hint [text]="changeTooltip" label="About this change" /> }
 :205-206   styles
-    .part + .part::before { content: '·'; margin: 0 var(--space-4); color: var(--text-faint); }
-    .part[title] { text-decoration: underline dotted; cursor: help; }
+    .part + .part::before, sb-hint + .part::before { content: '·'; margin: 0 var(--space-4); color: var(--text-faint); }
```

`workspaces/trades/position-card.ts` (`:41` `imports: [Panel, Chip]` gains `Hint`) and `workspaces/trades/why/sizing-panel.ts` (`:9` `imports: [Panel, Chip]` gains `Hint`) carry the same two lines, at `:52-53` and `:26-27`:

```diff
-                <sb-chip label="fragile" tone="warn" [caps]="false"
-                  title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." />
+                <sb-chip label="fragile" tone="warn" [caps]="false" />
+                <sb-hint text="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." label="About fragile stops" />
```

`workspaces/trades/why/why-panel.ts` (`:27` `imports: [Panel, Chip, InlineMd]` gains `Hint`):

```diff
 :60
-                    <sb-chip label="unevaluated" tone="muted" [caps]="false" title="no data — neutral points awarded" />
+                    <sb-chip label="unevaluated" tone="muted" [caps]="false" /><sb-hint text="no data — neutral points awarded" label="About unevaluated" />
 :92
-                @if (!gate.applies) { <sb-chip label="off" [caps]="false" title="off in current config" /> }
+                @if (!gate.applies) { <sb-chip label="off" [caps]="false" /><sb-hint text="off in current config" label="About this gate" /> }
```

`workspaces/trades/trades.ts` (V194-13 already added `Hint` to its imports). The export anchor is projected into `sb-toolbar` by its `slot` attribute and reparented as one element (`ui/toolbar.ts:25-37`), so a second `slot="export"` element is not safe: the anchor and its hint share one wrapper that carries the slot:

```diff
 :217-224
-      <a
-        slot="export"
-        class="export"
-        [href]="store.exportUrl()"
-        title="Downloads the entire trade log. The filters above do not narrow it."
-        download
-        >Export CSV</a
-      >
+      <span slot="export" class="export-group">
+        <a class="export" [href]="store.exportUrl()" download>Export CSV</a>
+        <sb-hint text="Downloads the entire trade log. The filters above do not narrow it." label="About the export" />
+      </span>
```
(`:396` `title="Trailing stop"` stays. If a style selector or spec reads `a[slot="export"]` or `.export` as the slotted element, move it to `.export-group`: `git grep -n "slot=\"export\"\|\[slot=.export.\]" -- frontend/src` finds them.)

`workspaces/versions/versions.ts` (`:47` `imports` gain `Hint`). An empty bar is a non-focusable `<div>`, so a hint cannot sit on it; the two titles become one row-level hint each. `:91` `[attr.title]="component + ' ' + version + ' — click to filter'"` stays (control name):

```diff
 :105-106   the absent bar loses its title
-                     [style.width.%]="lane.absentWidth * 100"
-                     title="This component did not exist yet"></div>
+                     [style.width.%]="lane.absentWidth * 100"></div>
 :99      the lane's name cell, first line inside `<div class="lane">`
             <span class="lane-name">{{ lane.component }}</span>
+            @if (lane.absentWidth > 0) { <sb-hint text="A bar with no fill means this component did not exist yet at that release." label="About empty bars" /> }
 :120-123 the bracket
-          <div class="bracket" [style.left.%]="store.bracket().start * 100"
-               [style.width.%]="store.bracket().width * 100"
-               title="The releases listed below"></div>
+          <div class="bracket" [style.left.%]="store.bracket().start * 100"
+               [style.width.%]="store.bracket().width * 100"></div>
+          <sb-hint text="The bar spans the releases listed below." label="About the bars" />
```

- [ ] **Step 4: Write `title-usage.allow.ts` in full** (echoes and control names only; anything else Step 2 listed is classified now by the A3 rule, added here and named in the commit):

```ts
export interface TitleSite {
  file: string;
  binding: string;
  kind: 'echo' | 'control-name' | 'explanation-pending';
  note: string;
}
export const TITLE_INPUT_ELEMENTS: readonly string[] = ['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog'];
const echo = (file: string, binding: string, note: string): TitleSite => ({ file, binding, kind: 'echo', note });
const control = (file: string, binding: string, note: string): TitleSite => ({ file, binding, kind: 'control-name', note });

export const TITLE_ALLOW: readonly TitleSite[] = [
  control('shell/connection-status.ts', '[title]="hint()"', 'icon-only status dot: aria-label names it, the title gives the detail'),
  control('shell/profile-menu.ts', '[attr.title]="haloTitle()"', 'names the avatar button'),
  echo('ui/age-hint.ts', `[attr.title]="'Price is ' + t.replace(' ago', '') + ' old'"`, 'restates the visible age'),
  echo('ui/bar-list.ts', '[title]="row.label"', 'the full label of a truncated bar label'),
  control('ui/direction-arrow.ts', '[title]="text"', 'glyph-only, same text as its aria-label'),
  control('ui/icon.ts', "host '[attr.title]'", "an icon's own name (LABELS)"),
  control('ui/layout.ts', '[attr.title]="tab.icon ? tab.label : null"', 'icon-only tab label'),
  echo('ui/matrix.ts', '[attr.title]="cellTitle(row, col, r, c)"', 'row and column names for a value the cell prints'),
  echo('ui/plan-cell.ts', '[title]="planTooltip"', 'the full text of the truncated plan line'),
  echo('ui/plan-cell.ts', '[title]="tooltip()"', 'the full text of the truncated plan line'),
  echo('ui/status-cell.ts', '[title]="row().status_label"', 'same text as the progressbar aria-label'),
  control('workspaces/dashboard/dashboard.ts', 'title="Trailing stop"', 'icon name'),
  control('workspaces/trades/trades.ts', 'title="Trailing stop"', 'icon name'),
  control('workspaces/dashboard/panels/equity-candles.ts', 'title="Back to today: chart and figures"', 'the button name, which also has an aria-label'),
  echo('workspaces/dashboard/panels/recent-activity.ts', '[title]="statusLabel(event)"', 'status name of an icon inside a button that names the event'),
  echo('workspaces/research/research.ts', '[attr.title]="row.hypothesis"', 'full text of a truncated cell'),
  echo('workspaces/system/settings-tab.ts', 'title="Default value"', 'names the badge printing the default'),
  control('workspaces/system/settings-tab.ts', `[title]="'Reset to ' + field.default"`, 'icon button name'),
  echo('workspaces/system/swallowed-errors-panel.ts', '[attr.title]="line.lastSeenAt"', 'the exact timestamp behind a relative time'),
  echo('workspaces/trades/trade-detail.ts', `[title]="'Trade ID: ' + trade.id"`, 'the full id the page prints'),
  control('workspaces/versions/versions.ts', `[attr.title]="component + ' ' + version + ' — click to filter'"`, 'names the filter button'),
];
export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
```

- [ ] **Step 5: Flip the specs that read a converted `title`** (import `hintTexts` from the `testing/hint-text` path as fits; every hint is in the DOM, so no spec opens one). Mechanical flips, `X.getAttribute('title')` → `hintTexts(C)[0]` and `X.hasAttribute('title')).toBe(false)` → `expect(hintTexts(C)).toEqual([])`, with `C` the container named:

| Spec (lines on `main`) | `C` |
|---|---|
| `shell/tape/tape.spec.ts:63` | `.cap` |
| `ui/layout.spec.ts:124,132,143`; `ui/metric-card.spec.ts:190,194` | the `sb-panel` / `sb-metric-card` host |
| `ui/stat-tile.spec.ts:64,84` | `.sample` |
| `ui/plan-cell.spec.ts:327,338,343,399` (the `.l2` reads; `.l1` and `.plan` reads are echoes and stay) | the render root: the trail hint is its first hint |
| `workspaces/calendar/day/calendar-day.spec.ts:220` / `:272` / `:280` | each stat tile / `.mtd` / `th.r-head` |
| `workspaces/calendar/day/day-trade-card.spec.ts:111` | `.figures` |
| `workspaces/dashboard/dashboard.spec.ts:371,374,382,385` | each panel's `header` / each `sb-metric-card` |
| `workspaces/dashboard/panels/trading-performance.spec.ts:346,348` | `sb-panel header` / each `sb-metric-card` |
| `workspaces/trades/why/sizing-panel.spec.ts:45` | `chip.parentElement` |

The four that change shape, old → new (anchor on the quoted call):

```diff
 workspaces/dashboard/panels/equity-candles.spec.ts:434
-    expect(pctPart.getAttribute('title'))
+    expect(pctPart.nextElementSibling!.querySelector('[role="tooltip"]')!.textContent!.trim())
 workspaces/trades/trade-detail.spec.ts:430-431, :464
-    expect(host.getAttribute('title')).toContain('41.2% WR');
+    expect(hintTexts(el).find((t) => t.includes('41.2% WR'))).toBeDefined();
-    const title = host.getAttribute('title') ?? '';
+    const title = hintTexts(el).find((t) => t.includes('Not enough closed trades')) ?? '';
 workspaces/trades/why/why-panel.spec.ts:105, :145
-    expect(f.nativeElement.querySelector('[title="no data — neutral points awarded"]')).not.toBeNull();
+    expect(hintTexts(f.nativeElement)).toContain('no data — neutral points awarded');
-    expect(f.nativeElement.querySelector('[title="off in current config"]').textContent).toContain('off');
+    expect(hintTexts(f.nativeElement)).toContain('off in current config');
```
  Where a panel renders its own richer header hint (`descriptionHint()` false), assert that header hint is non-empty instead of equal to the shared description, and say so in the commit.

- [ ] **Step 6: Re-run, then close the list.** `title-usage.spec.ts` PASS (zero unclassified, zero stale), then every spec named under **Files**. `git grep -n "getAttribute('title')" -- 'frontend/src/**/*.spec.ts'`: each remaining hit must sit on an allow-listed site; any other spec failing in the whole-frontend run reads a converted title: flip it by the same rule.

Close: standard (test: frontend/src/app/ui/title-usage.spec.ts); the whole-frontend run is the real gate here (many specs). Commit: `feat(v194): explanatory titles become sb-hints, scanner and allow-list for the rest (V194-14)`, stating the measured site count N from Step 2.

### Task V194-15: A3 part 2 — Analytics explanation sites converted; `TITLE_PENDING` empty and locked

**Model:** sonnet — an inventory command, four assertions, and the V194-14 recipe applied to whatever the inventory still finds.

**Spec:** § A3 (Analytics batch). The index's ledger reserves Analytics for this task because it holds the largest hint surface (`hint=` / `[hint]=` on `sb-panel-header`). The plan-time inventory (`git grep` over `frontend/src/app/workspaces/analytics/`, with the scanner's element rule) found **no native-title explanation there**: every `title=` in `partials.ts`, `attribution.ts`, `tuning.ts`, `pipeline.ts`, `edge.ts`, `overview.ts`, `execution.ts`, `override-fidelity-panel.ts`, `variance-band-panel.ts` is an input of `sb-panel-header` (a visible heading) or `sb-confirm-dialog` (`tuning.ts:236,249`), which the scanner skips by element. This task therefore (1) re-checks that with the scanner as built in V194-14, (2) converts any Analytics site the scan does report, by the V194-14 recipe, and (3) makes "no pending title" an assertion instead of a convention.

**Files:**
- Modify: `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`
- Modify (only if Step 1 lists a site there): the `frontend/src/app/workspaces/analytics/tabs/*.ts` file it names (candidates: `partials.ts`, `attribution.ts`, `tuning.ts`, `pipeline.ts`, `edge.ts`, `overview.ts`, `execution.ts`, `override-fidelity-panel.ts`, `variance-band-panel.ts`) and its spec

**Interfaces:**
- Consumes: `TITLE_ALLOW`, `TITLE_PENDING`, `TitleSite`, `TITLE_INPUT_ELEMENTS` (V194-14), `hintTexts` (`testing/hint-text.ts`).
- Produces: nothing new; `TITLE_PENDING` stays exported and is the constant `[]`; `TitleSite['kind']` narrows to `'echo' | 'control-name'`.

- [ ] **Step 1: Inventory.** Temporarily add `console.info(found.filter((s) => s.file.startsWith('workspaces/analytics/')));` as the first line of the first `it` in `title-usage.spec.ts`, run `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`, read the output, remove the line. Expected: an empty array. For each site it does list: classify by the A3 rule (echo / control name → a `TITLE_ALLOW` entry in the `echo(...)` / `control(...)` shape of V194-14 Step 4; explanation → the V194-14 recipe: delete the `title`, put `<sb-hint [text]="…" label="About …" />` right after the element, `Hint` into `imports:`, wording kept, no word that reads as a recommendation, a win-rate hint naming ExpR and N, a performance figure saying paper / gross or net / pre-tax) and flip the spec that read it with `hintTexts`.

- [ ] **Step 2: Write the locking tests.** In `title-usage.spec.ts` change the import line, then append the four tests inside the `describe`:

```ts
OLD   import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS } from './title-usage.allow';
NEW   import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS, TITLE_PENDING } from './title-usage.allow';
```

```ts
  it('leaves no explanation pending: every Analytics title is converted', () => {
    expect(TITLE_PENDING).toEqual([]);
  });

  it('keeps native-title explanation out of the Analytics tabs entirely', () => {
    const inTabs = found.filter((s) => s.file.startsWith('workspaces/analytics/'));
    const allowed = new Set(TITLE_ALLOW.map(key));
    expect(inTabs.filter((s) => !allowed.has(key(s))).map(key)).toEqual([]);
  });

  it('gives every entry a class and a reason', () => {
    for (const s of TITLE_ALLOW) {
      expect(['echo', 'control-name'], key(s)).toContain(s.kind);
      expect(s.note.length, key(s)).toBeGreaterThan(10);
    }
  });

  it('skips exactly the heading-input elements', () => {
    expect(TITLE_INPUT_ELEMENTS).toEqual(['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog']);
  });
```
  Run the spec. Expected: PASS when Step 1 found nothing (the first test guards a retired mechanism, the second the invariant); if Step 1 found sites not yet converted, the second FAILs until Step 1's conversions are done.

- [ ] **Step 3: Narrow the type.** In `title-usage.allow.ts`:

```ts
OLD   kind: 'echo' | 'control-name' | 'explanation-pending';
NEW   kind: 'echo' | 'control-name';
OLD   export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
NEW   /** The pending batch is retired: every explanation title is an sb-hint, so nothing waits. */
NEW   export const TITLE_PENDING: readonly TitleSite[] = [];
```

- [ ] **Step 4: Run to see it pass.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`. Expected: PASS with zero unclassified and zero stale; `npm --prefix "$WT/frontend" run lint` clean.

Close: standard (test: frontend/src/app/ui/title-usage.spec.ts). Commit: `test(v194): lock the title audit, no pending Analytics explanation (V194-15)`; if Step 1 converted a site, name each in the body.
