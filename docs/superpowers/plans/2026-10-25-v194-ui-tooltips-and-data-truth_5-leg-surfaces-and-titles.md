# v194 — UI integrity, part 5: leg surfaces and the title audit (V194-13..V194-15)

> **For agentic workers:** constraints, `### Standard task close`, `## Handoff` and `## Parallelisation` live in the index: [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md). Pull one task at a time: `grep -n "^### Task V194-14:" -A 400 <this file>`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — § B3, § A3

`WT` below is the v194 worktree's absolute path. Line numbers are those on
`main` at plan time; where an earlier task moved them, the task says "as left
by V194-n" and anchors on the quoted snippet. Edits are by the quoted snippet,
never by line number alone.

# Phase 5 — Legs named, titles that explain become hints

### Task V194-13: B3 surfaces — leg label and hint on Trades and the Dashboard; the row total says "rows"; missing-FX-rate caveat

**Model:** sonnet — template swaps and one helper at known sites, every name fixed by V194-6c and V194-12.

**Spec:** § B3. Two icons stand for "this row is a leg" today (`<sb-icon name="partial" title="Closed after an earlier partial exit …">`), saying nothing a tap can open and nothing about which leg. After this task every leg row shows **"Leg N of M[ · reason]"** beside its id, followed by an `sb-hint` reading `LEG_HINT_TEXT` (plus the open-partial sentence where one applies). The Trades page states what its total counts: **the API's `total` is `len(rows)` after legs are expanded (`swingbot/admin/api_v1/trades.py:1086`), so it counts rows (legs), not plans**; the live-region summary reads "N rows" and a one-line note under the table says so whenever a leg row is on the page. The same task shows the missing-FX-rate caveat (V194-6b/6c) on Trades and the Dashboard.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.columns.ts` (add the exported helper `legHintText` at the end of the file)
- Modify: `frontend/src/app/workspaces/trades/trades.ts:133` (imports array), `:386-397` (`#numCell` leg icons), `:342` (the element carrying `[announce]="announce()"`), `:852-853` (`announce`), `:968-972` (`partialOpenTitle` / `isPartialLeg`), styles near `:563`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:150` (imports array), `:393-402` (`#numCell`), `:201-223` (`<sb-trading-performance …>`), `:983-992`, styles near `:579`
- Modify: `frontend/src/app/workspaces/dashboard/trade-drawer.ts:96-102` (`tradeDrawerFields`), `:104-114` (template)
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes (V194-12): `legLabel(row: LegLike): string | null` and `LEG_HINT_TEXT` from `frontend/src/app/workspaces/trades/leg-label.ts`; `TradeRow.leg_exit_reason?: string | null`. (V194-6c): `fxMissingText(n: number): string` and `fxMissingOf(...payloads): number` from `frontend/src/app/workspaces/analytics/scope-bar.ts`; `TradeRow.fx_missing?: boolean`; `fx_missing_count?: number` on the Dashboard payload interface. Existing: `partialOpenTitle(row)` (`ui/status-cell.ts:230`), `Hint` (`ui/hint.ts`, already imported by `dashboard.ts:51`).
- Produces: `legHintText(row: TradeRow): string | null` exported from `trades.columns.ts` — `null` when the row is neither a leg (`legLabel(row) === null`) nor an open partial (`partialOpenTitle(row) === null`), else `LEG_HINT_TEXT` and the open-partial sentence (each only if present) joined by a space. Class hooks the specs and the V194-17 audit use: `.leg-label`, `.leg-note`, `.fx-note`.

- [ ] **Step 1: Write the failing tests.** Run `git grep -n "leg-icon" -- 'frontend/src/**/*.spec.ts'` first: any spec that reads the old partial `.leg-icon` title moves to the `.leg-label` assertions below.

In `trades.spec.ts`, extend `FooterFixture` with `items?: TradeRow[]` and make `render()` seed `items: footer.items ?? (footer.total > 0 ? [row({})] : [])` (replacing the existing `items:` line in the `patchState` call). Add imports `legLabel, LEG_HINT_TEXT` from `./leg-label` and `fxMissingText` from `../analytics/scope-bar`. Append:

```ts
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

In `dashboard.spec.ts` add imports `legLabel, LEG_HINT_TEXT` (from `../trades/leg-label`), `fxMissingText` (from `../analytics/scope-bar`), `tradeDrawerFields` (from `./trade-drawer`) and append:

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

  it('opens a hint that says plans, not legs', async () => {
    const el = await loadedWithRows(legs);
    expect(el.querySelector('.leg-label + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(LEG_HINT_TEXT);
  });

  it('lists the leg in the row drawer fields, and only for a leg', () => {
    expect(tradeDrawerFields(legs[0], '$', Date.now()).find((f) => f.key === 'leg')!.value).toBe(legLabel(legs[0]));
    const single = tradeDrawerFields(tradeRow({ leg_total: 1, leg_index: 0 }), '$', Date.now());
    expect(single.some((f) => f.key === 'leg')).toBe(false);
  });
});

describe('Dashboard — missing exchange rate caveat (v194 B7)', () => {
  it('shows the count from the payload', async () => {
    const fixture = await loaded({ fx_missing_count: 2 });
    expect((fixture.nativeElement as HTMLElement).querySelector('.fx-note')!.textContent!.trim()).toBe(fxMissingText(2));
  });

  it('shows nothing when no rate is missing', async () => {
    const fixture = await loaded();
    expect((fixture.nativeElement as HTMLElement).querySelector('.fx-note')).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to see them fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts`, then the same with `src/app/workspaces/dashboard/dashboard.spec.ts`. Expected: FAIL (no `.leg-label`, no `.fx-note`, `announce()` reads "2 trades").

- [ ] **Step 3: Add `legHintText(row: TradeRow): string | null` to `trades.columns.ts`** (imports `legLabel, LEG_HINT_TEXT` from `./leg-label` and `partialOpenTitle` from `../../ui/status-cell`). Behaviour is the Produces line; the body is two statements.

- [ ] **Step 4: Trades template and class (`trades.ts`).**
  - Imports: add `Hint` (`'../../ui/hint'`) to the component's `imports:` array (`:133`); import `legLabel, LEG_HINT_TEXT` from `./leg-label`, `legHintText` from `./trades.columns`, `fxMissingText` from `'../analytics/scope-bar'`.
  - `#numCell`, old → new: the `@if (isPartialLeg(row)) {…}` and `@if (partialOpenTitle(row); as openTitle) {…}` blocks (`:389-394`) become the pair below; the `trailing` icon block stays.

```html
@if (legLabel(row); as leg) { <span class="leg-label">{{ leg }}</span> }
@if (legHintText(row); as legHint) { <sb-hint [text]="legHint" label="About leg rows" /> }
```
  Class fields: `protected readonly legLabel = legLabel;`, `protected readonly legHintText = legHintText;`, `protected readonly legNoteHint = LEG_HINT_TEXT;`, `protected readonly fxMissingText = fxMissingText;`. Delete `isPartialLeg` (`:970`) and the `partialOpenTitle` field/import (`:51`, `:968`) once `git grep -n "isPartialLeg\|partialOpenTitle" frontend/src/app/workspaces/trades/trades.ts` shows no other reader.
  - `announce` (`:852-853`): `` return page ? `${page.total} trades` : null; `` → `` return page ? `${page.total} ${page.total === 1 ? 'row' : 'rows'}` : null; `` (the wording of `Pagination.rangeLabel`, `ui/pagination.ts:86`).
  - New computeds: `hasLegRows = computed(() => this.store.rows().some((r) => r.leg_total > 1))` and `fxMissingRows = computed(() => this.store.rows().filter((r) => r.fx_missing).length)` (both `protected readonly`).
  - Immediately after the closing tag of the element that carries `[announce]="announce()"` (`:342`):

```html
@if (hasLegRows()) {
  <p class="leg-note">Rows, not plans: a plan closed in parts lists one row per leg.
    <sb-hint [text]="legNoteHint" label="About leg rows" /></p>
}
@if (fxMissingRows() > 0) { <p class="fx-note" role="note">{{ fxMissingText(fxMissingRows()) }}</p> }
```
  - Styles next to `sb-row-link .leg-icon` (`:563`): `.leg-label { color: var(--text-muted); font-size: 0.85em; white-space: nowrap; }` and `.leg-note, .fx-note { margin: 0.5rem 0 0; color: var(--text-muted); font-size: 0.85em; }` — existing tokens only, no new ones.

- [ ] **Step 5: Dashboard (`dashboard.ts`).** The same `#numCell` swap at `:393-398`, the same exposure fields (`legLabel`, `legHintText`), the same two style rules next to `:579`; delete `isPartialLeg` (`:990-992`) and the `partialOpenTitle` field (`:983`) once unread. Above `<sb-trading-performance` (`:201`) add `@if (fxMissing() > 0) { <p class="fx-note" role="note">{{ fxMissingText(fxMissing()) }}</p> }` with `protected readonly fxMissing = computed(() => fxMissingOf(<the payload signal>()))` — the signal is the one `realized` / `todaySub` already read on this page (`git grep -n "realized" frontend/src/app/workspaces/dashboard/dashboard.ts`); no new store signal. Add `protected readonly fxMissingText = fxMissingText;`.

- [ ] **Step 6: Row drawer (`trade-drawer.ts`).** Add above `tradeDrawerFields`:

```ts
/** One "Leg N of M · reason" field, only for a row that is a leg. */
function legFields(row: TradeRow): TradeDrawerField[] {
  const leg = legLabel(row);
  return leg === null ? [] : [field('leg', 'Leg', leg)];
}
```
  insert `...legFields(row),` after the `status` field in `tradeDrawerFields`; in the component add `protected readonly legNote = computed(() => legHintText(this.row()));` and, under `</dl>`, `@if (legNote(); as note) { <p class="leg-note">{{ note }}</p> }` (plain visible text: the drawer has room, so no hint) and `@if (row().fx_missing) { <p class="fx-note" role="note">{{ fxMissingText(1) }}</p> }`. Imports: `legLabel` from `../trades/leg-label`, `legHintText` from `../trades/trades.columns`, `fxMissingText` from `../analytics/scope-bar`. Trades' own row drawer and compact rows render the same `#numCell` template, so they carry the label and hint without further edits (Step 7 proves it for the compact row).

- [ ] **Step 7: Run to see them pass.** The two commands from Step 2. Expected: PASS, including the existing count-footer, plan-cell and Dashboard hint specs. Add one more assertion to the first `trades.spec.ts` leg test if the compact row is reachable through `compactKeys` / `openRowDrawer` (`ui/data-table/testing/reachability`): the drawer's number cell contains `.leg-label`.

- [ ] **Step 8: Screenshot check.** Playwright against the local replica at 390, 768 and 1440 on `/trades` and `/dashboard` with a partially exited plan on screen: the label stays on one line beside the id, the hint opens in the top layer, `.leg-note` wraps. One screenshot per width into the scratchpad directory; the full layout audit still runs once, in V194-17.

Close: standard (test: frontend/src/app/workspaces/trades/trades.spec.ts); also run the narrow `dashboard/dashboard.spec.ts`. Commit: `feat(v194): leg label and plans-not-legs hint on Trades and Dashboard, rows total stated, FX caveat (V194-13)`.

### Task V194-14: A3 part 1 — `title-usage.spec.ts` scanner, allow-list, and every explanation `title` outside Analytics becomes an `sb-hint`

**Model:** sonnet — one scanner spec plus a per-site table of mechanical conversions, every site named with its replacement.

**Spec:** § A3. A native `title` answers a mouse hover only; a tap or a keyboard focus never opens it. Each site is classified once (table below, measured on `main` at plan time with the A3 counting rule in the index): **echo** (repeats a truncated or labelled value the row already shows) and **control name** (names an icon-only control) stay; **explanation** becomes an `sb-hint` beside the thing it explains, with the same words. A scanner spec then fails on any `title` binding not in the allow-list, so new explanation cannot hide in a `title` again. Analytics was inventoried too: its tab files hold no native-title explanation (every `title=` there is an `sb-panel-header` / `sb-confirm-dialog` input, which the scanner skips by element), so `TITLE_PENDING` starts empty and V194-15 only locks that in.

**Files:**
- Create: `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`, `frontend/src/app/testing/hint-text.ts`
- Modify (conversions; each adds `Hint` to the component's `imports:` when it renders one): `frontend/src/app/shell/tape/tape.ts`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/metric-card.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/status-cell.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, `frontend/src/app/workspaces/calendar/day/day-trade-card.ts`, `frontend/src/app/workspaces/calendar/day/trade-sparkline.ts`, `frontend/src/app/workspaces/cancels/cancels-summary.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, `frontend/src/app/workspaces/dashboard/trade-drawer.ts`, `frontend/src/app/workspaces/trades/position-card.ts`, `frontend/src/app/workspaces/trades/why/sizing-panel.ts`, `frontend/src/app/workspaces/trades/why/why-panel.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/versions/versions.ts`, `frontend/src/app/workspaces/watchlist/watchlist.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`
- Modify (specs that read a converted `title`; the list is closed by Step 7): `shell/tape/tape.spec.ts:63`, `ui/layout.spec.ts:124,143`, `ui/metric-card.spec.ts:190`, `ui/stat-tile.spec.ts:64,84`, `ui/plan-cell.spec.ts:327,338,343` (and any `querySelector('[title]')` that matched `.l2`), `ui/status-cell.spec.ts` (grep), `workspaces/calendar/day/calendar-day.spec.ts:220,272,280`, `workspaces/calendar/day/day-trade-card.spec.ts:111`, `workspaces/dashboard/dashboard.spec.ts:366-385`, `workspaces/dashboard/panels/trading-performance.spec.ts:346-348`, `workspaces/dashboard/panels/equity-candles.spec.ts:434`, `workspaces/trades/trade-detail.spec.ts:427-431,464`, `workspaces/trades/why/sizing-panel.spec.ts:45`, `workspaces/trades/why/why-panel.spec.ts:105,145` (all under `frontend/src/app/`)

**Interfaces:**
- Consumes: `Hint` (`ui/hint.ts`, `[text]`, `[label]`, `align`), `StatTile.about` (V194-11: `input<string | undefined>`, renders an `sb-hint` beside the label), `legLabel` is not used here.
- Produces: `TitleSite { file: string; binding: string; kind: 'echo' | 'control-name' | 'explanation-pending'; note: string }` (`file` relative to `frontend/src/app/`, `binding` the matched attribute text exactly as written, or `host '[attr.title]'` for a component-metadata key); `TITLE_ALLOW: readonly TitleSite[]`; `TITLE_PENDING: readonly TitleSite[]` (the `explanation-pending` subset, empty); `TITLE_INPUT_ELEMENTS: readonly string[]` (`['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog']`); `hintTexts(root: ParentNode): string[]` in `testing/hint-text.ts` (the whitespace-collapsed text of every `sb-hint [role="tooltip"]` under `root`, in document order — the pop-up is in the DOM whether or not it is open, so specs read hint copy without opening it).

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

import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS, TITLE_PENDING } from './title-usage.allow';

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

  it('gives every entry a class and a reason', () => {
    for (const s of TITLE_ALLOW) {
      expect(['echo', 'control-name', 'explanation-pending'], key(s)).toContain(s.kind);
      expect(s.note.length, key(s)).toBeGreaterThan(10);
    }
  });

  it('keeps explanation-pending to the Analytics batch', () => {
    for (const s of TITLE_PENDING) expect(s.file, key(s)).toMatch(/^workspaces\/analytics\//);
  });

  it('skips exactly the heading-input elements', () => {
    expect(TITLE_INPUT_ELEMENTS).toEqual(['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog']);
  });
});
```

`title-usage.allow.ts` starts with the types and exports and an empty `TITLE_ALLOW` (filled in Step 4):

```ts
export interface TitleSite {
  file: string;
  binding: string;
  kind: 'echo' | 'control-name' | 'explanation-pending';
  note: string;
}
export const TITLE_INPUT_ELEMENTS: readonly string[] = ['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog'];
export const TITLE_ALLOW: readonly TitleSite[] = [];
export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
```

- [ ] **Step 2: Run it to see it fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`. Expected: FAIL on "allows only echoes…" with the message `N sites scanned, N unclassified` and the list. **Record N: the commit message states it** (A3 counting rule). The list should match the table in Steps 3-4; a site in the list that no table row names is classified at the site by the A3 rule and added to the table row set in this step's notes.

- [ ] **Step 3: Convert the explanation sites.** One recipe: delete the `title` binding, put `<sb-hint [text]="…" label="About …" />` directly after the element it explained (same words as the old title; `[text]` for a binding, `text` for a literal), add `Hint` (`'../../ui/hint'` path as fits) to `imports:`. Sites (all under `frontend/src/app/`; the old text is kept verbatim unless a row says otherwise):

| File (site) | Replacement |
|---|---|
| `shell/tape/tape.ts:66` `[attr.title]` on `.lane` | drop it; inside `.cap` after `mkt`: `@if (asOfTime() !== ABSENT) { <sb-hint [text]="'Tape data as of ' + asOfTime()" label="About the tape" /> }` |
| `shell/tape/tape.ts:80` proxy `title` | `<span class="ctx proxy">{{ tile.proxyLabel }} <sb-hint text="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price." label="About this proxy" /></span>` |
| `ui/layout.ts:41` host `'[attr.title]': 'description()'` | delete the `host` entry and its comment; the header `sb-hint` (`:52`) already carries `description()`. Then `git grep -n "description=\|\[description\]" -- 'frontend/src/app/**/*.ts' ':!*.spec.ts'`: every `<sb-panel>` that passes a description must also pass a heading (else no hint renders); fix any that does not |
| `ui/metric-card.ts:47` host `'[attr.title]': 'description()'` | delete the host entry; after the `.label` span: `@if (description(); as about) { <sb-hint [text]="about" [label]="'About ' + label()" /> }`; `imports: [CountUp, Spinner, Hint]` |
| `ui/stat-tile.ts:45` `.sample [title]="sampleTitle()"` | drop the binding; inside `.sample`, after the N text: `@if (sampleTitle()) { <sb-hint [text]="sampleTitle()!" label="About this sample size" /> }` (the existing `thin` flag stays) |
| `ui/plan-cell.ts:39` `.l2 [title]="trailTooltip()"` | drop it; after the `.l2` span: `<sb-hint [text]="trailTooltip()" label="About the trailing stop" />`. `:30` (`planTooltip`) and `:49` (`tooltip()`) stay: echoes |
| `ui/status-cell.ts:86`, `:103`, `:110` | `<span class="end neg">{{ e.stop }}</span><sb-hint text="P&L if the trailing stop is hit" label="About the stop P&L" />`; `<span class="end pos">{{ e.best }}</span><sb-hint text="P&L at the best price since TP1" label="About the best-price P&L" />`; the `delayed` span keeps its word and gains `<sb-hint text="This position's price could not be freshly fetched -- the number shown may be delayed." label="About the delayed price" />` |
| `workspaces/calendar/day/calendar-day.ts:131,136,137` stat tiles `[attr.title]="rTooltip"` | `[about]="rTooltip"` (V194-11's input) |
| `calendar-day.ts:170` `.mtd-r`, `:184` `th.r-head` | after the span / the `R` text: `<sb-hint [text]="rTooltip" label="About R" />` |
| `calendar-day.ts:196` withheld win-rate `[attr.title]` | drop it; inside the cell `@if (breakdownWinRate(row) === absent) { <sb-hint [text]="winNote" label="Why no win rate" /> }` |
| `workspaces/calendar/day/day-trade-card.ts:54` `.r [title]="rTooltip"` | drop it; after the span `<sb-hint [text]="rTooltip" label="About R" />` |
| `workspaces/calendar/day/trade-sparkline.ts:122` | `<span class="spark-empty">—<sb-hint text="No cached daily bars for this row" label="Why no chart" /></span>` |
| `workspaces/cancels/cancels-summary.ts:38` | `<span class="small-n">N &lt; {{ data().small_n_threshold }}<sb-hint [text]="'Fewer than ' + data().small_n_threshold + ' resolved plans: an anecdote, not a rate'" label="About small samples" /></span>` |
| `workspaces/dashboard/dashboard.ts:439`, `:483` | after each span: `<sb-hint text="Live P&L, then projected P&L at target and at stop" label="About this P&L" />` and `<sb-hint text="Projected R if price reaches target" label="About expected R" />` (the `title="Trailing stop"` at `:401` stays: control name) |
| `workspaces/dashboard/panels/equity-candles.ts:135` | drop `[attr.title]`; after the span `@if (isChangePart(part.text)) { <sb-hint [text]="changeTooltip" label="About this change" /> }` (`:163` stays: control name) |
| `workspaces/dashboard/trade-drawer.ts:111` | `<span drawer-header class="paper-marker">{{ paperMarker }}<sb-hint text="The bot places no orders: every trade on this page is a paper trade." label="About paper trades" /></span>`; add `Hint` to `imports` |
| `workspaces/trades/position-card.ts:53`, `workspaces/trades/why/sizing-panel.ts:27` (`sb-chip … title=`) | drop it; after the chip `<sb-hint text="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." label="About fragile stops" />` |
| `workspaces/trades/why/why-panel.ts:60`, `:92` (`sb-chip` titles) | after each chip `<sb-hint text="no data — neutral points awarded" label="About unevaluated" />` and `<sb-hint text="off in current config" label="About this gate" />` |
| `workspaces/trades/trade-detail.ts:174` `sb-chip [title]="cohortTooltip()"` | drop it; after the chip `<sb-hint [text]="cohortTooltip()" label="About this cohort" />` (`:182` stays: echo) |
| `workspaces/trades/trades.ts:221` export `<a>` | drop the title; right after the anchor `<sb-hint slot="export" text="Downloads the entire trade log. The filters above do not narrow it." label="About the export" />` |
| `workspaces/versions/versions.ts:106`, `:123` empty bar `<div>`s | drop both titles (a non-focusable element is touch-inaccessible). The component's name cell gets `<sb-hint text="A bar with no fill means this component did not exist yet at that release." label="About empty bars" />`; the releases column header gets `<sb-hint text="The bar spans the releases listed below." label="About the bars" />` (`:91` stays: control name) |
| `workspaces/watchlist/watchlist.ts:416` | `<span class="source-badge">fallback</span><sb-hint text="Alpaca missed this quote; yfinance answered instead" label="About the fallback quote" />` |
| `workspaces/system/settings-tab.ts:181` | `<span class="restart">restart<sb-hint text="Restart required to take effect" label="About restart" /></span>` |

- [ ] **Step 4: Fill `TITLE_ALLOW`** with exactly these entries (`file` / `binding` / kind / note), one per line in the file:
  - `shell/connection-status.ts` · `[title]="hint()"` · control-name · the status dot is icon-only; `aria-label` carries the name, the title the detail
  - `shell/profile-menu.ts` · `[attr.title]="haloTitle()"` · control-name · avatar button name
  - `ui/age-hint.ts` · `[attr.title]="'Price is ' + t.replace(' ago', '') + ' old'"` · echo · restates the visible age
  - `ui/bar-list.ts` · `[title]="row.label"` · echo · the full label of a truncated bar label
  - `ui/direction-arrow.ts` · `[title]="text"` · control-name · glyph-only; same text as its `aria-label`
  - `ui/icon.ts` · `host '[attr.title]'` · control-name · an icon's own name (`LABELS`)
  - `ui/layout.ts` · `[attr.title]="tab.icon ? tab.label : null"` · control-name · icon-only tab label
  - `ui/matrix.ts` · `[attr.title]="cellTitle(row, col, r, c)"` · echo · row and column names for a value the cell already prints
  - `ui/plan-cell.ts` · `[title]="planTooltip"` · echo · the full text of the truncated plan line
  - `ui/plan-cell.ts` · `[title]="tooltip()"` · echo · the full text of the truncated plan line
  - `ui/status-cell.ts` · `[title]="row().status_label"` · echo · same text as the progressbar's `aria-label`
  - `workspaces/dashboard/dashboard.ts` · `title="Trailing stop"` · control-name · icon name
  - `workspaces/trades/trades.ts` · `title="Trailing stop"` · control-name · icon name
  - `workspaces/dashboard/panels/equity-candles.ts` · `title="Back to today: chart and figures"` · control-name · the button's name (it has an `aria-label`)
  - `workspaces/dashboard/panels/recent-activity.ts` · `[title]="statusLabel(event)"` · echo · the status name of an icon inside a button that already names the event
  - `workspaces/research/research.ts` · `[attr.title]="row.hypothesis"` · echo · full text of a truncated cell
  - `workspaces/system/settings-tab.ts` · `title="Default value"` · echo · names the badge printing the default
  - `workspaces/system/settings-tab.ts` · `[title]="'Reset to ' + field.default"` · control-name · icon button name
  - `workspaces/system/swallowed-errors-panel.ts` · `[attr.title]="line.lastSeenAt"` · echo · the exact timestamp behind a relative time
  - `workspaces/trades/trade-detail.ts` · `[title]="'Trade ID: ' + trade.id"` · echo · the full id the page prints
  - `workspaces/versions/versions.ts` · `[attr.title]="component + ' ' + version + ' — click to filter'"` · control-name · names the filter button
  Any site Step 2 listed that is in neither the table nor this list is classified now by the A3 rule; add it to whichever applies, and say so in the commit.

- [ ] **Step 5: Flip the specs that read a converted `title`** (the list under **Files**): `el.getAttribute('title')` → `hintTexts(el)[0]` (import `hintTexts` from `../../testing/hint-text`, path as fits), and `querySelector('[title]')` assertions that matched a converted element → `hintTexts(root)` containing the same text. Where `sb-panel` shows its own richer hint instead of the shared one (`descriptionHint()` false), assert against the header's `sb-hint` text, not the panel description. `dashboard.spec.ts:366-385` keeps both claims: every panel and every KPI card still has a hint, and the payoff-ratio card's text still contains "average winning trade divided by the average losing trade".

- [ ] **Step 6: Re-run the scanner spec, then each flipped spec.** `title-usage.spec.ts` PASS (zero unclassified, zero stale), then every spec named under **Files** by `--include`. Any other spec that failed in the whole-frontend run reads a converted title: flip it by the same rule and add it to the commit.

- [ ] **Step 7: Close the list.** `git grep -n "getAttribute('title')" -- 'frontend/src/**/*.spec.ts'`: each remaining hit must sit on an allow-listed site (`aria`, icon, echo); anything else is a spec you missed.

Close: standard (test: frontend/src/app/ui/title-usage.spec.ts); the whole-frontend run is the real gate for this task (many specs). Commit: `feat(v194): explanatory titles become sb-hints, scanner and allow-list for the rest (V194-14)`, stating the measured site count N from Step 2.

### Task V194-15: A3 part 2 — Analytics explanation sites converted; `TITLE_PENDING` empty and locked

**Model:** sonnet — an inventory command, an assertion, and the V194-14 recipe applied to whatever the inventory still finds.

**Spec:** § A3 (Analytics batch). The index's ledger reserves Analytics for this task because it holds the largest hint surface (`hint=` / `[hint]=` on `sb-panel-header`). The plan-time inventory (`git grep` over `frontend/src/app/workspaces/analytics/`, with the scanner's element rule) found **no native-title explanation there**: every `title=` in `partials.ts`, `attribution.ts`, `tuning.ts`, `pipeline.ts`, `edge.ts`, `overview.ts`, `execution.ts`, `override-fidelity-panel.ts`, `variance-band-panel.ts` is an input of `sb-panel-header` (a visible heading) or `sb-confirm-dialog` (`tuning.ts:236,249`), which the scanner skips by element. This task therefore (1) re-checks that with the scanner as built in V194-14, (2) converts any Analytics site the scan does report, by the V194-14 recipe, and (3) makes "no pending title" an assertion instead of a convention.

**Files:**
- Modify: `frontend/src/app/ui/title-usage.spec.ts`, `frontend/src/app/ui/title-usage.allow.ts`
- Modify (only if Step 1 lists a site there): the `frontend/src/app/workspaces/analytics/tabs/*.ts` file it names (candidates: `partials.ts`, `attribution.ts`, `tuning.ts`, `pipeline.ts`, `edge.ts`, `overview.ts`, `execution.ts`, `override-fidelity-panel.ts`, `variance-band-panel.ts`) and its spec

**Interfaces:**
- Consumes: `TITLE_ALLOW`, `TITLE_PENDING`, `TitleSite` (V194-14), `hintTexts` (`testing/hint-text.ts`).
- Produces: nothing new; `TITLE_PENDING` stays exported and is asserted empty.

- [ ] **Step 1: Inventory.** Run the V194-14 scanner's view of Analytics: temporarily add `console.info(found.filter((s) => s.file.startsWith('workspaces/analytics/')))` to the first `it` of `title-usage.spec.ts`, run `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`, read the output, remove the line. Expected: an empty array. For each site it does list: classify by the A3 rule (echo / control name → a `TITLE_ALLOW` entry with its note; explanation → the V194-14 recipe: delete the `title`, put `<sb-hint [text]="…" label="About …" />` right after the element, `Hint` into `imports:`, wording kept, no word that reads as a recommendation, a win-rate hint naming ExpR and N, a performance figure saying paper / gross or net / pre-tax) and flip the spec that read it with `hintTexts`.

- [ ] **Step 2: Write the failing test.** Append to `title-usage.spec.ts`'s `describe`:

```ts
  it('leaves no explanation pending: every Analytics title is converted', () => {
    expect(TITLE_PENDING).toEqual([]);
    expect(TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending')).toEqual([]);
  });

  it('keeps native-title explanation out of the Analytics tabs entirely', () => {
    const inTabs = found.filter((s) => s.file.startsWith('workspaces/analytics/'));
    const allowed = new Set(TITLE_ALLOW.map(key));
    expect(inTabs.filter((s) => !allowed.has(key(s))).map(key)).toEqual([]);
  });
```
  Run it. Expected: PASS if Step 1 found nothing (these two guard the invariant); if Step 1 found sites and they are not yet converted, they FAIL until Step 3 is done.

- [ ] **Step 3: Narrow the type.** In `title-usage.allow.ts` remove `'explanation-pending'` from `TitleSite['kind']` and make `export const TITLE_PENDING: readonly TitleSite[] = [];` (a constant: the batch mechanism is retired); update the "keeps explanation-pending to the Analytics batch" and "gives every entry a class" tests in `title-usage.spec.ts` to the two remaining kinds, and drop the `.filter(kind === 'explanation-pending')` assertion from Step 2 (`TITLE_PENDING` is `[]` by construction, the first expectation stays).

- [ ] **Step 4: Run to see it pass.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/ui/title-usage.spec.ts`. Expected: PASS with zero unclassified and zero stale.

Close: standard (test: frontend/src/app/ui/title-usage.spec.ts). Commit: `test(v194): lock the title audit, no pending Analytics explanation (V194-15)`; if Step 1 converted a site, name each in the body.

