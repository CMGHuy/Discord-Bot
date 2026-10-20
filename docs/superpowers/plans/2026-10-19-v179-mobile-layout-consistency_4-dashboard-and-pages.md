# v179 — Mobile layout consistency, Part 4: the Dashboard trade drawer and page fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §3.2 (Dashboard trade drawer), §3.4 (alignment, copy defects, empty N), §6a.3–§6a.5, §6b.3 and §6b.8.
**Index:** [2026-10-19-v179-mobile-layout-consistency_0-index.md](2026-10-19-v179-mobile-layout-consistency_0-index.md) — Goal, Architecture, **Global Constraints**, **Contracts**, **Parallelisation** and the task ledger live there and bind every task below.

Tasks V179-14..V179-16 are in this file; **V179-17..V179-18 are in [`_4b-page-fixes.md`](2026-10-19-v179-mobile-layout-consistency_4b-page-fixes.md)** — with them this file would pass the 1500-line cap, so Part 4 is two files (same ids, scope and order as the index). Every task runs in the worktree `.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (created by V179-1). Paths under "Files" are full repo paths; commands run from the worktree root. Before this part starts, Parts 1–3 have landed what it consumes: `--font-num`, the floored text tokens, `--hit-min`/`.sb-hit` and `--control-h: 44px` under `(pointer: coarse), (max-width: 1023px)` (V179-1, V179-2); `sb-control-row` on `align-items: last baseline` and the baseline `sb-panel` header (V179-3); `PhoneTap`, `phoneTap` on `sb-data-table` and the `compact` declarations on `tradeColumns` (V179-9..V179-11).

**Four additions to the index, all inside this part's own files** (no other part consumes them, no shared contract changes):

1. **`sb-trade-drawer` owns its `sb-drawer`.** The index Contracts say the trade drawer renders `.paper-marker` with the `drawer-header` attribute, projected into `sb-drawer`'s header. Angular projects only the content its *parent* template writes between `<sb-drawer>` tags, so that is possible only if `TradeDrawer`'s own template contains the `<sb-drawer>`. It does, and therefore it also has two outputs beside the contracted `row` input: `closed = output<void>()` (re-emits `sb-drawer`'s `closed`) and `actionDone = output<void>()` (re-emits `sb-row-actions`' `done`). The Dashboard mounts `<sb-trade-drawer>` only while `drawerTrade()` holds a row.
2. **V179-17 also touches `why/sizing-panel.ts`, `why/if-it-gets-there.ts` and `ui/status-indicator.ts`** (guarded by a source-text test V179-17 adds to `trade-detail.spec.ts`). The brief traced the mixed mono/sans values to bare `<dd>`s; reading the code for this part found the larger cause: `sizing-panel.ts`, `if-it-gets-there.ts` and `why-panel.ts` mark numbers with a class `sb-num` that no stylesheet defines, so "1,000.00" (Deployed) and "5.51%" (Gap risk) render in the sans face. And `sb-status-indicator`'s `.wrap` is `align-items: center` with an empty dot as its first item, so its baseline is the dot's bottom edge, not the "CLOSED" text — `align-items: baseline` on the trade title alone cannot fix the 3px offset. None of these files is in any other task.
3. **Part 4 is two files**: `_4-dashboard-and-pages.md` (V179-14..V179-16) and `_4b-page-fixes.md` (V179-17..V179-18). The index Parts table should list both.
4. **V179-18 also edits `workspaces/dashboard/dashboard.spec.ts`**: its scope test clicks `[data-scope="all"]`, a button the `sb-segmented` header replaces. V179-18 already runs after V179-16 (the index's sequential edge), so the two never edit that spec at once.

---

# Phase 4 — Dashboard trade drawer and page fixes

### Task V179-14: `ActivityEvent.tradeId` and interactive activity rows

**Model:** sonnet — two small files and their specs, one new output; the only judgement is keeping the existing class-based tests valid while the row becomes a button.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/activity.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`

**Interfaces:**
- Consumes: `--control-h` (44px under `(pointer: coarse), (max-width: 1023px)` since V179-2); the `sb-hit` class V179-2 put on the `View all` link (`<a panel-actions class="all-link sb-hit" routerLink="/trades">`) stays as it is.
- Produces (ledger): `ActivityEvent.tradeId: string` — the trade row's `id`, set by `deriveActivity` on every event; `RecentActivity.eventActivate = output<ActivityEvent>()`; each event renders `li.event > button.event-hit` (type `button`, `aria-haspopup="dialog"`) holding the icon, arrow, ticker, detail and time. V179-16 binds `(eventActivate)="openActivity($event)"`.

**Why (spec §6b.3).** Recent activity is a plain `<li>` list today: nothing to tap, so the Dashboard cannot open a trade from it. The event id is `<trade id>:<kind>`; the spec settles on an explicit `tradeId` rather than splitting the id string, so a trade id that ever contains `:` cannot break the lookup.

- [ ] **Step 1: Write the failing tests**

Append inside the `describe('activity derivation', …)` block of `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`:

```ts
  it('carries the trade id on every event, not only inside the event id (v179 §6b.3)', () => {
    const events = deriveActivity([
      row({ id: 'PLAN:7', status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z' }),
      row({ id: 'p2', status: 'CANCELLED', opened_at: null, closed_at: '2026-09-11T12:00:00Z' }),
    ]);
    expect(events.map((e) => [e.kind, e.tradeId])).toEqual([
      ['closed', 'PLAN:7'],
      ['opened', 'PLAN:7'],
      ['cancelled', 'p2'],
    ]);
  });
```

Append to `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts` — the two `node:` imports go at the top of the file beside the existing imports; the rest goes after the existing `describe` block:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
```

```ts
const SOURCE = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/panels/recent-activity.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) => SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('recent activity rows open a trade (v179 §3.2, §6b.3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  const EVENTS = [
    { kind: 'opened', at: '2026-09-11T15:00:00Z', ticker: 'ASTS', direction: 'bullish', status: 'ACTIVE',
      detail: 'at 60.54', r: null, id: 't1:opened', tradeId: 't1' },
    { kind: 'closed', at: '2026-09-11T14:00:00Z', ticker: 'HOOD', direction: 'bearish', status: 'CLOSED',
      detail: 'Closed at +1.20R', r: 1.2, id: 't2:closed', tradeId: 't2' },
  ];

  function mount() {
    const f = TestBed.createComponent(RecentActivity);
    f.componentRef.setInput('events', EVENTS);
    f.detectChanges();
    return f;
  }

  it('renders each event as one button inside its list item', () => {
    const el = mount().nativeElement as HTMLElement;
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('li.event > button.event-hit')];
    expect(buttons).toHaveLength(2);
    expect(buttons.every((b) => b.type === 'button')).toBe(true);
    expect(buttons[0].getAttribute('aria-haspopup')).toBe('dialog');
    expect(buttons[0].textContent).toContain('ASTS');
    expect(buttons[0].querySelector('time.at')).not.toBeNull();
  });

  it('emits the event it was activated for', () => {
    const f = mount();
    const picked: unknown[] = [];
    f.componentInstance.eventActivate.subscribe((e) => picked.push(e));
    (f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button.event-hit')[1].click();
    expect(picked).toEqual([EVENTS[1]]);
  });

  it('gives each row a touch-sized hit area and one text baseline', () => {
    const hit = rule('.event-hit');
    expect(hit).toContain('min-height: var(--control-h)');
    expect(hit).toContain('align-items: baseline');
    expect(hit).toContain('width: 100%');
    // The glyphs carry no text baseline of their own: centred, not dropped
    // onto the text line by a synthesized baseline.
    expect(rule('.event-hit sb-icon')).toContain('align-self: center');
    expect(rule('.event-hit sb-direction-arrow')).toContain('align-self: center');
    expect(SOURCE).not.toMatch(/\.event \{[^}]*display: grid/);
  });

  it('shows the keyboard focus on the row button', () => {
    expect(rule('.event-hit:focus-visible')).toContain('outline');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/activity.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts`
Expected: FAIL — `tradeId` is `undefined` in the derivation test; no `button.event-hit` exists; `eventActivate` is not a member of `RecentActivity`; `.event-hit` has no rule.

- [ ] **Step 3: Add `tradeId` to `ActivityEvent`**

In `frontend/src/app/workspaces/dashboard/panels/activity.ts`, after the `id` member of `interface ActivityEvent` add:

```ts
  /** The trade row this event came from (v179 §6b.3). The Dashboard opens
   *  its trade drawer from this, never by splitting `id` -- a trade id that
   *  contained ':' would split wrong, and the field costs nothing. */
  tradeId: string;
```

and in `deriveActivity` add `tradeId: row.id,` to both pushed objects, directly after their `id:` line:

```ts
        id: `${row.id}:${cancelled ? 'cancelled' : 'closed'}`,
        tradeId: row.id,
```

```ts
        id: `${row.id}:opened`,
        tradeId: row.id,
```

- [ ] **Step 4: Make each event a button and add the output**

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`:

Change the Angular core import to include `output`:

```ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
```

Replace the `@for` body (the whole `<li …> … </li>`) with:

```html
            <li [class]="'event ' + event.kind">
              <!-- v179 §3.2: a row opens the Dashboard's trade drawer. A real
                   button, so Enter/Space and focus come from the browser. -->
              <button type="button" class="event-hit" aria-haspopup="dialog"
                      (click)="eventActivate.emit(event)">
                <sb-icon [name]="icon(event)" [title]="statusLabel(event)"
                         [attr.aria-label]="statusLabel(event)" />
                <sb-direction-arrow [direction]="event.direction" />
                <span class="ticker">{{ event.ticker }}</span>
                <span class="detail" [class.pos]="(event.r ?? 0) > 0" [class.neg]="(event.r ?? 0) < 0">{{ event.detail }}</span>
                <time class="at" [attr.datetime]="event.at">{{ fmt(event.at) }}</time>
              </button>
            </li>
```

Replace the `.event { … }` rule with these rules (the grid moves from the `li` to the button; the `li` keeps its kind class for the existing tests):

```css
    .event { display: block; }
    /* One button per row (v179 §3.2). Baseline, not centre: the ticker is
       mono and the time is muted text, and centring two faces leaves their
       text at two heights (spec §3.4). The glyphs are centred on their own
       below because an SVG has no text baseline to align. --control-h is
       44px under a coarse pointer or below 1024px (V179-2). */
    .event-hit {
      display: grid;
      grid-template-columns: auto auto auto 1fr auto;
      align-items: baseline;
      gap: var(--space-8);
      width: 100%;
      min-height: var(--control-h);
      padding: 0;
      background: none;
      border: 0;
      border-radius: var(--radius-sm);
      color: inherit;
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .event-hit sb-icon { align-self: center; }
    .event-hit sb-direction-arrow { align-self: center; }
    .event-hit:hover .ticker { text-decoration: underline; }
    .event-hit:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
```

In the existing `sb-icon { color: var(--text-muted); cursor: help; }` rule change `cursor: help` to `cursor: inherit` (the whole row is the pointer target now; a help cursor on part of a button reads as a second control). The title tooltip stays.

Add the output to the class, directly under `events`:

```ts
  /** v179 §3.2: the Dashboard opens its trade drawer for this event's
   *  `tradeId`. The panel itself never navigates. */
  readonly eventActivate = output<ActivityEvent>();
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/activity.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS, 0 failed. (`dashboard.spec.ts` mounts the panel; nothing on the Dashboard changes before V179-16 wires the output.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/activity.ts frontend/src/app/workspaces/dashboard/panels/activity.spec.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts
git commit -m "feat(v179): activity events carry tradeId; each activity row is a button

The Dashboard trade drawer (V179-16) opens from eventActivate. Rows are
44px under a coarse pointer or below 1024px and align on the text baseline."
```

---

### Task V179-15: `sb-trade-drawer` content and the drawer header slot

**Model:** sonnet — one new presentational component plus a one-slot change to `sb-drawer`; the money/paper-trade rules make it worth a careful hand but the logic is a pure field table.

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/trade-drawer.ts`
- Create: `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts`
- Modify: `frontend/src/app/ui/layout.ts`
- Modify: `frontend/src/app/ui/layout.spec.ts`

**Interfaces:**
- Consumes: `Drawer` (`sb-drawer`, `ui/layout.ts`: `open`, `heading`, `closed`); `RowActions` (`sb-row-actions`, `workspaces/dashboard/row-actions.ts`: `row = input.required<TradeRow>()`, `done = output<void>()`); `livePnlPct`, `liveUnrealizedAmount` (`workspaces/dashboard/dashboard.helpers.ts`); `sideLabel` (`workspaces/trades/trade-figures.ts`); `ABSENT`, `num`, `pct`, `money`, `held`, `elapsedHours`, `dateTime`, `text` (`ui/format.ts`); `ConnectionStore.currency()`; `CLOCK` (`ui/clock.ts`); `.sb-hit` and `.num` (V179-1, V179-2).
- Produces (ledger): in `sb-drawer`, `<ng-content select="[drawer-header]" />` inside `<header>`, after the `h2`; `TradeDrawer`, selector `sb-trade-drawer`, `row = input.required<TradeRow>()`, plus (this part's addition, see the part header) `closed = output<void>()` and `actionDone = output<void>()`; exported `PAPER_MARKER = 'Paper trade'`, `TradeDrawerField { key: string; label: string; value: string; numeric: boolean; tone: 'pos' | 'neg' | null }`, `drawerPnl(row: TradeRow): { pct: number | null; amount: number | null }` and `tradeDrawerFields(row: TradeRow, currency: string, nowMs: number): TradeDrawerField[]`. DOM: `sb-drawer` whose header holds `span.paper-marker[drawer-header]`; body `dl.fields > div.field[data-field="<key>"] > dt + dd`; `div.drawer-actions` with `sb-row-actions` and `a.full-trade` ("Open full trade →", `routerLink ['/trades', row.id]`). V179-16 mounts it.

**What goes in (spec §3.2, §6a.3).** Everything comes from the `TradeRow` already loaded — no fetch: ticker (the drawer heading), direction, status, P&L as a percentage **and** an amount in the account currency (realised for a closed row, live for an open or pending one — the same split the Dashboard's P&L cell makes, `dashboard.ts` `#pnlCell`), the plan levels (Entry, or Trigger while a plan is pending; Stop; TP1; TP2; R:R), opened and held, strategy and horizon, the row's existing actions and "Open full trade →". The header carries "Paper trade": the bot is paper-only, and a drawer styled like a position ticket must not read as a live position (spec §3.2, financial-advisor). Every absent value renders as the em dash `ABSENT`, never `NaN`, `undefined` or an empty cell.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/layout.spec.ts`. Add `Drawer` to the existing `import { Panel, Tab, TabBar } from './layout';` line, and these imports at the top beside the others:

```ts
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { provideMotion } from './motion/motion.service';
```

```ts
/** The Drawer component's own source: `rule('header')` alone would match
 *  sb-panel's header, which comes first in this file. */
const DRAWER_SOURCE = SOURCE.slice(SOURCE.indexOf("selector: 'sb-drawer'"));
const drawerRule = (selector: string) =>
  DRAWER_SOURCE.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

@Component({
  imports: [Drawer],
  template: `
    <sb-drawer [open]="true" heading="AAPL">
      <span drawer-header class="mark">Paper trade</span>
      <p class="content">Body</p>
    </sb-drawer>
  `,
})
class DrawerSlotHost {}

describe('sb-drawer header slot (v179 §3.2)', () => {
  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('off')] });
  });

  it('projects [drawer-header] content into the header, after the heading', () => {
    const fixture = TestBed.createComponent(DrawerSlotHost);
    fixture.detectChanges();
    const header = (fixture.nativeElement as HTMLElement).querySelector('sb-drawer header')!;
    const children = [...header.children].map((child) => child.tagName.toLowerCase() + (child.className ? `.${child.className}` : ''));
    expect(children[0]).toBe('h2');
    expect(header.querySelector('.mark')?.textContent).toBe('Paper trade');
    expect(header.querySelector('.mark')?.previousElementSibling?.tagName).toBe('H2');
    const body = (fixture.nativeElement as HTMLElement).querySelector('sb-drawer .body')!;
    expect(body.querySelector('.content')).not.toBeNull();
    expect(body.querySelector('.mark')).toBeNull();
  });

  it('keeps heading, marker and close on one baseline with the close pushed to the end', () => {
    const header = drawerRule('header');
    expect(header).toContain('align-items: baseline');
    expect(header).toContain('flex-wrap: wrap');
    expect(header).not.toContain('align-items: center');
    expect(header).not.toContain('justify-content: space-between');
    expect(drawerRule('.close')).toContain('margin-left: auto');
  });
});
```

Create `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { provideMotion } from '../../ui/motion/motion.service';
import { PAPER_MARKER, TradeDrawer, drawerPnl, tradeDrawerFields } from './trade-drawer';

const NOW = Date.parse('2026-10-20T12:00:00Z');

function tradeRow(overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'ACTIVE', ticker: 'AAPL',
    direction: 'bullish', strategy: 'RSI', horizon: '2w', tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: 120,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: 2, shares: 10, open_shares: 10, position_value: 1000,
    current_price: 105, current_price_stale: false, exit_price: null, realized_pnl_amount: null,
    pnl_pct: null, r_multiple: null, held_hours: null, opened_at: '2026-10-19T12:00:00Z', closed_at: null,
    has_note: false, today: false, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'Open', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  } as TradeRow;
}

describe('tradeDrawerFields (v179 §3.2)', () => {
  it('lists the summary in reading order', () => {
    expect(tradeDrawerFields(tradeRow(), '€', NOW).map((f) => f.key)).toEqual([
      'direction', 'status', 'pnl', 'entry', 'stop', 'tp1', 'tp2', 'rr', 'opened', 'held', 'strategy', 'horizon',
    ]);
  });

  it('shows the live P&L of an open position as a percentage and an amount', () => {
    expect(drawerPnl(tradeRow())).toEqual({ pct: 5, amount: 50 });
    const pnl = tradeDrawerFields(tradeRow(), '€', NOW).find((f) => f.key === 'pnl')!;
    expect(pnl.value).toBe('+5.00% (+50.00 €)');
    expect(pnl.tone).toBe('pos');
    expect(pnl.numeric).toBe(true);
  });

  it('shows the realised P&L of a closed leg, signed and toned by its sign', () => {
    const row = tradeRow({ status: 'CLOSED', pnl_pct: -4, realized_pnl_amount: -40, current_price: null });
    const pnl = tradeDrawerFields(row, '€', NOW).find((f) => f.key === 'pnl')!;
    expect(pnl.value).toBe('-4.00% (-40.00 €)');
    expect(pnl.tone).toBe('neg');
  });

  it('labels the level a pending plan waits on as its trigger', () => {
    const row = tradeRow({ status: 'PENDING', entry: null, trigger_price: 101, open_shares: null, opened_at: null });
    const fields = tradeDrawerFields(row, '€', NOW);
    expect(fields.find((f) => f.key === 'trigger')).toMatchObject({ label: 'Trigger', value: '101.00', numeric: true });
    expect(fields.find((f) => f.key === 'entry')).toBeUndefined();
  });

  it('measures held time from the open while the server has not computed it', () => {
    const held = tradeDrawerFields(tradeRow(), '€', NOW).find((f) => f.key === 'held')!;
    expect(held.value).toBe('1d 0h 0m');
    const closed = tradeRow({ status: 'CLOSED', held_hours: 2.5, pnl_pct: 1, realized_pnl_amount: 10 });
    expect(tradeDrawerFields(closed, '€', NOW).find((f) => f.key === 'held')!.value).toBe('2h 30m');
  });

  it('renders every absent value as an em dash, never NaN or undefined', () => {
    const bare = tradeRow({
      direction: '', status_label: '', strategy: null, horizon: null, entry: null, trigger_price: null,
      stop_loss: null, target: null, target2: null, risk_reward: null, current_price: null,
      open_shares: null, opened_at: null, held_hours: null,
    });
    for (const field of tradeDrawerFields(bare, '€', NOW)) {
      expect(field.value, field.key).not.toMatch(/NaN|undefined|null/);
      expect(field.value.trim(), field.key).not.toBe('');
    }
    expect(tradeDrawerFields(bare, '€', NOW).find((f) => f.key === 'pnl')!.value).toBe('—');
  });
});

describe('sb-trade-drawer (v179 §3.2)', () => {
  let fixture: ComponentFixture<TradeDrawer>;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideMotion('off'),
        { provide: ConnectionStore, useValue: { currency: signal('€') } },
      ],
    });
  });

  function mount(row: TradeRow = tradeRow()): HTMLElement {
    fixture = TestBed.createComponent(TradeDrawer);
    fixture.componentRef.setInput('row', row);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('opens a drawer headed by the ticker, marked as a paper trade', () => {
    const el = mount();
    const dialog = el.querySelector<HTMLDialogElement>('sb-drawer dialog')!;
    expect(dialog.open).toBe(true);
    expect(el.querySelector('sb-drawer header h2')!.textContent!.trim()).toBe('AAPL');
    const marker = el.querySelector('sb-drawer header .paper-marker')!;
    expect(marker.textContent!.trim()).toBe(PAPER_MARKER);
    expect(PAPER_MARKER).toBe('Paper trade');
  });

  it('renders each field as a label/value pair, numbers in the numeric face', () => {
    const el = mount();
    const rows = [...el.querySelectorAll('dl.fields > div.field')];
    expect(rows.map((r) => r.getAttribute('data-field'))).toContain('pnl');
    const stop = el.querySelector('[data-field="stop"]')!;
    expect(stop.querySelector('dt')!.textContent!.trim()).toBe('Stop');
    expect(stop.querySelector('dd')!.textContent!.trim()).toBe('95.00');
    expect(stop.querySelector('dd')!.classList).toContain('num');
    expect(el.querySelector('[data-field="strategy"] dd')!.classList).not.toContain('num');
    expect(el.querySelector('[data-field="pnl"] dd')!.classList).toContain('pos');
  });

  it('offers the row actions and the full trade page', () => {
    const el = mount();
    expect(el.querySelector('.drawer-actions sb-row-actions')).not.toBeNull();
    const link = el.querySelector<HTMLAnchorElement>('.drawer-actions a.full-trade')!;
    expect(link.textContent!.trim()).toBe('Open full trade →');
    expect(link.getAttribute('href')).toBe('/trades/t1');
    expect(link.classList).toContain('sb-hit');
  });

  it('reports the close the drawer makes', () => {
    const el = mount();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    el.querySelector<HTMLButtonElement>('sb-drawer .close')!.click();
    fixture.detectChanges();
    expect(closed).toBe(1);
  });

  it('aligns each field and the action line on the text baseline', () => {
    const css = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/trade-drawer.ts'), 'utf8');
    expect(css).toMatch(/\.field \{[^}]*align-items: baseline/);
    expect(css).toMatch(/\.drawer-actions \{[^}]*align-items: baseline/);
    // No workspace media query (spec §4 anti-goal): the drawer's phone,
    // tablet and desktop geometry is sb-drawer's own.
    expect(css).not.toMatch(/@media/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts`
Expected: FAIL — `trade-drawer.spec.ts` cannot resolve `./trade-drawer`; in `layout.spec.ts` the `.mark` element is not inside `header` (there is no `[drawer-header]` slot, so it lands in `.body`) and the drawer header rule still says `align-items: center` and `justify-content: space-between`.

- [ ] **Step 3: Add the header slot to `sb-drawer`**

In `frontend/src/app/ui/layout.ts`, in the `Drawer` template, replace

```html
          <header>
            <h2>{{ heading() }}</h2>
            <button type="button" class="close" aria-label="Close" (click)="requestClose()">×</button>
          </header>
```

with

```html
          <header>
            <h2>{{ heading() }}</h2>
            <!-- v179 §3.2: a marker beside the heading (the Dashboard trade
                 drawer's "Paper trade"). Content without the attribute
                 still goes to the body below. -->
            <ng-content select="[drawer-header]" />
            <button type="button" class="close" aria-label="Close" (click)="requestClose()">×</button>
          </header>
```

and in the `Drawer` styles replace the `header { … }` rule with

```css
    /* One baseline for the heading, an optional [drawer-header] marker and
       the close glyph (v179 §3.4); the close button takes the free space on
       its left, so it stays at the end of the line with or without a marker. */
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--space-10);
      padding: var(--space-14);
      border-bottom: 1px solid var(--border);
    }
```

and add `margin-left: auto;` as the first declaration of the `.close { … }` rule (its `min-width`/`min-height: var(--control-h)` stay). Update the `Drawer` docstring's last paragraph by appending: "`[drawer-header]` content goes beside the heading (v179); everything else goes to the body."

- [ ] **Step 4: Create `sb-trade-drawer`**

Create `frontend/src/app/workspaces/dashboard/trade-drawer.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { CLOCK } from '../../ui/clock';
import { ABSENT, dateTime, elapsedHours, held, money, num, pct, text } from '../../ui/format';
import { Drawer } from '../../ui/layout';
import { sideLabel } from '../trades/trade-figures';
import { livePnlPct, liveUnrealizedAmount } from './dashboard.helpers';
import { RowActions } from './row-actions';

/** The header marker. The bot only paper-trades (CLAUDE.md, eToro roadmap
 *  stage 0); a drawer that looks like a position ticket must say so. */
export const PAPER_MARKER = 'Paper trade';

export interface TradeDrawerField {
  key: string;
  label: string;
  value: string;
  numeric: boolean;
  tone: 'pos' | 'neg' | null;
}

type Tone = TradeDrawerField['tone'];

/** Realised for a closed leg, live for an open or pending one -- the same
 *  split the Dashboard's P&L cell makes (`dashboard.ts` `#pnlCell`), from
 *  the same helpers, so the drawer can never disagree with the table. */
export function drawerPnl(row: TradeRow): { pct: number | null; amount: number | null } {
  if (row.pnl_pct !== null) return { pct: row.pnl_pct, amount: row.realized_pnl_amount };
  return { pct: livePnlPct(row), amount: liveUnrealizedAmount(row) };
}

function toneOf(value: number | null): Tone {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

/** Percentage first, the amount beside it -- the money floor (spec §3.1):
 *  P&L is never shown as a percentage alone when an amount exists. */
function pnlText(row: TradeRow, currency: string): string {
  const { pct: percent, amount } = drawerPnl(row);
  if (percent === null && amount === null) return ABSENT;
  if (amount === null) return pct(percent);
  return `${pct(percent)} (${money(amount, currency)})`;
}

function field(key: string, label: string, value: string, numeric = false, tone: Tone = null): TradeDrawerField {
  return { key, label, value, numeric, tone };
}

/** A pending plan has no fill yet: the level it waits on is its trigger. */
function entryField(row: TradeRow): TradeDrawerField {
  return row.entry === null
    ? field('trigger', 'Trigger', num(row.trigger_price), true)
    : field('entry', 'Entry', num(row.entry), true);
}

/** Everything the drawer shows, from the loaded row alone (spec §3.2: no
 *  fetch). Absent values are the em dash, never NaN or an empty cell. */
export function tradeDrawerFields(row: TradeRow, currency: string, nowMs: number): TradeDrawerField[] {
  return [
    field('direction', 'Direction', sideLabel(row.direction) ?? ABSENT),
    field('status', 'Status', text(row.status_label || row.status)),
    field('pnl', 'P&L', pnlText(row, currency), true, toneOf(drawerPnl(row).pct)),
    entryField(row),
    field('stop', 'Stop', num(row.stop_loss), true),
    field('tp1', 'TP1', num(row.target), true),
    field('tp2', 'TP2', num(row.target2), true),
    field('rr', 'R:R', num(row.risk_reward), true),
    field('opened', 'Opened', dateTime(row.opened_at)),
    field('held', 'Held', held(row.held_hours ?? elapsedHours(row.opened_at, nowMs)), true),
    field('strategy', 'Strategy', text(row.strategy)),
    field('horizon', 'Horizon', text(row.horizon)),
  ];
}

/**
 * One trade, summarised in a drawer — v179 §3.2.
 *
 * Owns its `sb-drawer` so the "Paper trade" marker can be projected into the
 * drawer's header (`[drawer-header]`): Angular projects only what the
 * parent template writes between the `<sb-drawer>` tags. The Dashboard mounts
 * this only while a trade is open; `closed` tells it the drawer closed itself
 * (×, Escape, backdrop), `actionDone` that a row action changed the trade.
 *
 * Desktop: the drawer's side panel; phone: its bottom sheet. No media query
 * here -- the geometry is `sb-drawer`'s.
 */
@Component({
  selector: 'sb-trade-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Drawer, RowActions, RouterLink],
  template: `
    <sb-drawer [open]="true" [heading]="row().ticker" (closed)="closed.emit()">
      <span drawer-header class="paper-marker"
            title="The bot places no orders: every trade on this page is a paper trade.">{{ paperMarker }}</span>
      <dl class="fields">
        @for (item of fields(); track item.key) {
          <div class="field" [attr.data-field]="item.key">
            <dt>{{ item.label }}</dt>
            <dd [class.num]="item.numeric" [class.pos]="item.tone === 'pos'" [class.neg]="item.tone === 'neg'">{{ item.value }}</dd>
          </div>
        }
      </dl>
      <div class="drawer-actions">
        <sb-row-actions [row]="row()" (done)="actionDone.emit()" />
        <a class="full-trade sb-hit" [routerLink]="['/trades', row().id]">Open full trade →</a>
      </div>
    </sb-drawer>
  `,
  styles: `
    :host { display: contents; }
    .paper-marker {
      padding: 0 var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      letter-spacing: .04em;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .fields { display: grid; gap: var(--space-6); margin: 0; }
    /* Label and value at two faces (UI and numeric) on one line: baseline,
       never centre (spec §3.4). */
    .field {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: var(--space-10);
      min-width: 0;
    }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { margin: 0; min-width: 0; font-size: var(--text-table); text-align: right; overflow-wrap: anywhere; }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .drawer-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-10);
      margin-top: var(--space-14);
      padding-top: var(--space-10);
      border-top: 1px solid var(--border);
    }
    .full-trade { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .full-trade:hover { text-decoration: underline; }
  `,
})
export class TradeDrawer {
  readonly row = input.required<TradeRow>();
  readonly closed = output<void>();
  readonly actionDone = output<void>();

  private readonly connection = inject(ConnectionStore);
  private readonly now = inject(CLOCK);

  protected readonly paperMarker = PAPER_MARKER;
  protected readonly fields = computed(() =>
    tradeDrawerFields(this.row(), this.connection.currency(), this.now()));
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/layout.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts --include src/app/ui/controls.spec.ts --include src/app/workspaces/research/research.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts`
Expected: PASS, 0 failed. `controls.spec.ts` drives the drawer's exit paths and Research is the existing drawer consumer — both must be unaffected by the slot; `workspace-consistency.spec.ts` scans the new workspace file. If the `held` expectation differs by the minute ladder, read `ui/format.ts` `held()` again rather than changing the helper: `24` hours renders `1d 0h 0m`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/layout.ts frontend/src/app/ui/layout.spec.ts frontend/src/app/workspaces/dashboard/trade-drawer.ts frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts
git commit -m "feat(v179): sb-trade-drawer summary and a [drawer-header] slot on sb-drawer

The drawer shows the loaded row only (no fetch): direction, status, P&L as
% and amount, plan levels, opened/held, strategy/horizon, row actions and
Open full trade. The header carries a Paper trade marker."
```

---

### Task V179-16: Dashboard drawer wiring: `trade` param, rerun rule, redirect, positions `emit`

**Model:** opus — router history semantics (push vs replace, Back, cold links), a resolver rerun rule that must not break SSE refresh, and an effect that must not race an in-flight navigation.

**Files:**
- Create: `frontend/src/app/routing/route-rerun.ts`
- Create: `frontend/src/app/routing/route-rerun.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.routes.ts`
- Modify: `frontend/src/app/app.routes.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.ts`
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: `PhoneTap` (`ui/data-table/data-table.types.ts`, V179-9) and `sb-data-table`'s `phoneTap` input (V179-10); `compact` declarations on `tradeColumns` (V179-11 — the Dashboard positions table already renders compact rows on a phone); `ActivityEvent.tradeId`, `RecentActivity.eventActivate` (V179-14); `TradeDrawer` (`sb-trade-drawer`: `row`, `closed`, `actionDone`, V179-15).
- Produces (ledger): `rerunExceptQueryParam(name: string): (from: ActivatedRouteSnapshot, to: ActivatedRouteSnapshot) => boolean`; `PositionsTable.phoneTap = input<PhoneTap>('drawer')`, passed to its `sb-data-table`; on `Dashboard`: query parameter `trade`, `protected readonly drawerTrade = signal<TradeRow | null>(null)`, `protected openTrade(row: TradeRow): void`, `protected openActivity(event: ActivityEvent): void`, `protected closeTrade(): void` (the old `open(row)` is removed). V179-20 drives the round trip in a browser.

**Behaviour, decided (spec §3.2, §6a.5, §6b.8; index Global Constraints and Review Focus):**
- **Open in page** (a position row, any device — the positions table emits instead of opening the generic drawer — or an activity row): the drawer shows the row at once, and `router.navigate([], { queryParams: { trade: id }, queryParamsHandling: 'merge' })` **pushes** `?trade=<id>`; other Dashboard parameters survive.
- **Back** removes the parameter; the Dashboard sees it gone and closes the drawer.
- **× / Escape / backdrop** after an in-page open → `Location.back()` (no second entry for Back to reopen). After a **cold open** (reload, shared link, Forward) there is no pushed entry of ours → remove the parameter with `replaceUrl: true`.
- **Cold link**: wait until the activity `TradesStore` has answered (rows or an error), then open the row with that id; if it is absent, `navigate(['/trades', id], { replaceUrl: true })`. Rows from the positions table cannot be looked up (that component owns its own `TradesStore`, spec "Row source"), so a reload on a position that is not in the last 20 activity rows lands on the full trade page — the spec's stated fallback.
- **No fetch, no resolver re-run** when only `trade` changes: the Dashboard route's `runGuardsAndResolvers: 'always'` becomes `rerunExceptQueryParam('trade')`, which is `false` only when path params are equal and the query params differ in `trade` alone. Identical URLs still return `true`, so `RouteRefreshService`'s same-URL `onSameUrlNavigation: 'reload'` refresh keeps re-resolving exactly as `'always'` did.
- A row action in the drawer (close, cancel) reloads the summary and the activity feed and closes the drawer — its row is stale after the action.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/routing/route-rerun.spec.ts`:

```ts
import { ActivatedRouteSnapshot } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { rerunExceptQueryParam } from './route-rerun';

const snap = (queryParams: Record<string, unknown>, params: Record<string, string> = {}) =>
  ({ params, queryParams }) as unknown as ActivatedRouteSnapshot;

describe('rerunExceptQueryParam (v179 §6b.8)', () => {
  const rule = rerunExceptQueryParam('trade');

  it('skips the resolvers when only the named parameter is added, changed or removed', () => {
    expect(rule(snap({}), snap({ trade: 't1' }))).toBe(false);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't2' }))).toBe(false);
    expect(rule(snap({ trade: 't1', status: 'ACTIVE' }), snap({ status: 'ACTIVE' }))).toBe(false);
  });

  it('re-runs an identical URL, as "always" did (the SSE refresh re-navigates the same URL)', () => {
    expect(rule(snap({}), snap({}))).toBe(true);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't1' }))).toBe(true);
  });

  it('re-runs when anything besides the named parameter changes', () => {
    expect(rule(snap({ scope: 'today' }), snap({ scope: 'all' }))).toBe(true);
    expect(rule(snap({ trade: 't1' }), snap({ trade: 't2', scope: 'all' }))).toBe(true);
    expect(rule(snap({}, { id: 'a' }), snap({ trade: 't1' }, { id: 'b' }))).toBe(true);
  });

  it('compares multi-valued parameters by value', () => {
    expect(rule(snap({ tag: ['a', 'b'] }), snap({ tag: ['a', 'b'], trade: 't1' }))).toBe(false);
    expect(rule(snap({ tag: ['a', 'b'] }), snap({ tag: ['a'], trade: 't1' }))).toBe(true);
  });
});
```

In `frontend/src/app/app.routes.spec.ts`, add `ActivatedRouteSnapshot` to the `@angular/router` import, then in `'keeps every authenticated workspace lazy, scoped, and resolver-backed'` replace

```ts
      expect(child.runGuardsAndResolvers).toBe('always');
```

with

```ts
      // v179 §6b.8: the Dashboard alone skips its resolver for a drawer toggle.
      if (path === 'dashboard') expect(child.runGuardsAndResolvers).toBeTypeOf('function');
      else expect(child.runGuardsAndResolvers).toBe('always');
```

and add inside `describe('route data readiness contract', …)`:

```ts
  it('re-resolves the Dashboard on every navigation except a trade-drawer toggle (v179 §6b.8)', async () => {
    const child = (await routes.find((route) => route.path === 'dashboard')!.loadChildren!() as Routes)[0]!;
    const rule = child.runGuardsAndResolvers as (a: ActivatedRouteSnapshot, b: ActivatedRouteSnapshot) => boolean;
    const snap = (queryParams: Record<string, string>) => ({ params: {}, queryParams }) as unknown as ActivatedRouteSnapshot;
    expect(rule(snap({}), snap({ trade: 't1' }))).toBe(false);
    expect(rule(snap({}), snap({}))).toBe(true);
    expect(rule(snap({}), snap({ scope: 'all' }))).toBe(true);
  });
```

Append inside `describe('positions table', …)` of `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` (add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` at the top):

```ts
  it('passes its phone-tap choice to the table, the generic drawer by default (v179 §6a.4)', () => {
    const f = mount();
    expect((f.componentInstance as unknown as { phoneTap: () => string }).phoneTap()).toBe('drawer');
    f.componentRef.setInput('phoneTap', 'emit');
    f.detectChanges();
    expect((f.componentInstance as unknown as { phoneTap: () => string }).phoneTap()).toBe('emit');
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/positions-table.ts'), 'utf8');
    expect(source).toMatch(/<sb-data-table[^>]*\[phoneTap\]="phoneTap\(\)"/);
  });
```

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`:

Add these imports beside the existing ones, and extend the existing lines rather than duplicating them: `Component` joins the `@angular/core` import, `Router` joins `provideRouter` in the `@angular/router` import.

```ts
import { Location } from '@angular/common';
import { SpyLocation, provideLocationMocks } from '@angular/common/testing';
import { By } from '@angular/platform-browser';
import { RouterTestingHarness } from '@angular/router/testing';

import { provideMotion } from '../../ui/motion/motion.service';
import { dashboardRoutes } from './dashboard.routes';
import { PositionsTable } from './positions-table';
```

and append at the end of the file:

```ts
/* v179 §3.2: the trade drawer, driven through a real router so the URL,
 * history and the route's rerun rule are what is tested. The route copies
 * the production rerun rule and counts its resolver runs. */
@Component({ template: '' })
class TradePage {}

let resolverRuns = 0;

const ACTIVITY_ROW = tradeRow({
  id: 't1', ticker: 'AAPL', status: 'ACTIVE', status_label: 'Open', opened_at: '2026-10-20T10:00:00Z',
  pnl_pct: null, realized_pnl_amount: null, exit_price: null, current_price: 105, open_shares: 5,
});

/** Answers the page's own requests: the activity feed's trades query (no
 *  status) gets `recentRows`, the positions table's (status set) nothing. */
async function answer(harness: RouterTestingHarness, backend: HttpTestingController, recentRows: TradeRow[]) {
  for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
    const rows = req.request.params.has('status') ? [] : recentRows;
    req.flush({ items: rows, total: rows.length, page: 1, per_page: 20 });
  }
  for (const req of backend.match('/api/v1/dashboard?mode=today')) req.flush(payload());
  await harness.fixture.whenStable();
  harness.detectChanges();
}

async function routed(url: string) {
  resolverRuns = 0;
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([
        {
          path: 'dashboard', component: Dashboard,
          runGuardsAndResolvers: dashboardRoutes[0].runGuardsAndResolvers,
          resolve: { ready: () => { resolverRuns += 1; return true; } },
        },
        { path: 'trades/:id', component: TradePage },
      ]),
      provideLocationMocks(),
      provideMotion('off'),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      DashboardStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
      { provide: EquityCandlesStore, useValue: equityCandlesStoreStub(CANDLES) },
    ],
  });
  const harness = await RouterTestingHarness.create(url);
  const backend = TestBed.inject(HttpTestingController);
  const location = TestBed.inject(Location) as SpyLocation;
  return { harness, backend, location };
}

async function settled(harness: RouterTestingHarness) {
  await harness.fixture.whenStable();
  harness.detectChanges();
}

const drawer = (harness: RouterTestingHarness) =>
  harness.routeNativeElement!.querySelector('sb-trade-drawer');

describe('Dashboard trade drawer (v179 §3.2)', () => {
  it('opens an activity row in the drawer and pushes ?trade=', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    const before = location.urlChanges.length;
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('AAPL');
    expect(location.path()).toBe('/dashboard?trade=t1');
    expect(location.urlChanges.slice(before)).toEqual(['/dashboard?trade=t1']);
  });

  it('fetches nothing and re-runs no resolver when only the trade changes', async () => {
    const { harness, backend } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    backend.match(() => true);              // drain anything unrelated to the drawer
    const runs = resolverRuns;
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    expect(drawer(harness)).not.toBeNull();
    expect(backend.match(() => true)).toEqual([]);
    expect(resolverRuns).toBe(runs);
  });

  it('closes on Back', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    location.back();
    await settled(harness);
    expect(location.path()).toBe('/dashboard');
    expect(drawer(harness)).toBeNull();
  });

  it('goes back on × after an in-page open, adding no history entry', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    const back = vi.spyOn(location, 'back');
    const before = location.urlChanges.length;
    drawer(harness)!.querySelector<HTMLButtonElement>('.close')!.click();
    await settled(harness);
    expect(back).toHaveBeenCalledTimes(1);
    expect(location.path()).toBe('/dashboard');
    // Router bookkeeping may re-write the current entry; a push would be a
    // plain URL in urlChanges, a replace is prefixed 'replace: '.
    expect(location.urlChanges.slice(before).filter((url) => !url.startsWith('replace: '))).toEqual([]);
    expect(drawer(harness)).toBeNull();
  });

  it('opens a position row on every device: the table emits, the Dashboard holds the row', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, []);
    const table = harness.routeDebugElement!.query(By.directive(PositionsTable));
    expect((table.componentInstance as { phoneTap: () => string }).phoneTap()).toBe('emit');
    const position = tradeRow({ id: 'p9', ticker: 'HOOD', status: 'ACTIVE', opened_at: '2026-10-20T09:00:00Z' });
    (table.componentInstance as PositionsTable).rowActivate.emit(position);
    await settled(harness);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('HOOD');
    expect(location.path()).toBe('/dashboard?trade=p9');
  });

  it('waits for the activity rows on a cold link, then opens the trade', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=t1');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    harness.detectChanges();
    expect(drawer(harness)).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
    await answer(harness, backend, [ACTIVITY_ROW]);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('AAPL');
    expect(location.path()).toBe('/dashboard?trade=t1');
  });

  it('removes the parameter with replaceUrl on × after a cold open', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=t1');
    await answer(harness, backend, [ACTIVITY_ROW]);
    const back = vi.spyOn(location, 'back');
    drawer(harness)!.querySelector<HTMLButtonElement>('.close')!.click();
    await settled(harness);
    expect(back).not.toHaveBeenCalled();
    expect(location.path()).toBe('/dashboard');
    expect(location.urlChanges.at(-1)).toBe('replace: /dashboard');
    expect(drawer(harness)).toBeNull();
  });

  it('sends a link whose trade is not loaded to the full trade page, replacing the entry', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=gone');
    await answer(harness, backend, [ACTIVITY_ROW]);
    await settled(harness);
    expect(location.path()).toBe('/trades/gone');
    expect(location.urlChanges.at(-1)).toBe('replace: /trades/gone');
  });

  it('opens the full trade page from the drawer link', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    drawer(harness)!.querySelector<HTMLAnchorElement>('a.full-trade')!.click();
    await settled(harness);
    expect(location.path()).toBe('/trades/t1');
  });
});
```


- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/routing/route-rerun.spec.ts --include src/app/app.routes.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — `./route-rerun` does not resolve; the Dashboard route still says `'always'`; `phoneTap` is not a `PositionsTable` member; clicking an activity row navigates nowhere and no `sb-trade-drawer` exists.

- [ ] **Step 3: Create the rerun rule**

Create `frontend/src/app/routing/route-rerun.ts`:

```ts
import { ActivatedRouteSnapshot, Params } from '@angular/router';

/** Values compared as data: a repeated query key arrives as an array. */
function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function sameParams(a: Params, b: Params, ignore: string | null): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].every((key) => key === ignore || sameValue(a[key], b[key]));
}

/**
 * A `runGuardsAndResolvers` rule: re-run on every navigation (like
 * `'always'`) except one whose only change is the query parameter `name`
 * — v179 §6b.8.
 *
 * The Dashboard's trade drawer writes `?trade=<id>` as a pushed history entry.
 * Under `'always'` that push re-ran the route resolver and refetched the
 * page, which the spec forbids (§3.2: the drawer fetches nothing). An
 * identical URL still returns `true`: `RouteRefreshService` refreshes a page
 * by re-navigating its own URL with `onSameUrlNavigation: 'reload'`, and that
 * must keep re-resolving.
 */
export function rerunExceptQueryParam(
  name: string,
): (from: ActivatedRouteSnapshot, to: ActivatedRouteSnapshot) => boolean {
  return (from, to) => {
    const onlyNameChanged = sameParams(from.params, to.params, null)
      && !sameValue(from.queryParams[name], to.queryParams[name])
      && sameParams(from.queryParams, to.queryParams, name);
    return !onlyNameChanged;
  };
}
```

- [ ] **Step 4: Use it on the Dashboard route**

In `frontend/src/app/workspaces/dashboard/dashboard.routes.ts` add `import { rerunExceptQueryParam } from '../../routing/route-rerun';` beside the other routing imports, and replace `runGuardsAndResolvers: 'always',` with:

```ts
  // v179 §6b.8: 'always', except a change to the trade drawer's own
  // parameter (dashboard.ts TRADE_PARAM) -- opening a trade fetches nothing.
  runGuardsAndResolvers: rerunExceptQueryParam('trade'),
```

- [ ] **Step 5: Let the positions table pass its phone-tap choice through**

In `frontend/src/app/workspaces/dashboard/positions-table.ts`:
- change the types import to `import { ColumnDef, EmptyState, PhoneTap } from '../../ui/data-table/data-table.types';`
- add `[phoneTap]="phoneTap()"` to the `<sb-data-table …>` attributes, directly after `[rowKey]="rowKey()"`;
- add to the class, directly after `rowKey`:

```ts
  /** What a phone row tap does (v179 §6a.4). The Dashboard sets 'emit': it
   *  opens its own trade drawer on every device, so the table's generic
   *  drawer must not open a second one. */
  readonly phoneTap = input<PhoneTap>('drawer');
```

- [ ] **Step 6: Wire the Dashboard**

In `frontend/src/app/workspaces/dashboard/dashboard.ts`:

Imports — extend `import { Router } from '@angular/router';` to `import { ActivatedRoute, Router } from '@angular/router';` and add:

```ts
import { Location } from '@angular/common';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { ActivityEvent, deriveActivity } from './panels/activity';
import { TradeDrawer } from './trade-drawer';
```

(the existing `import { deriveActivity } from './panels/activity';` line is replaced by the one above). Add `TradeDrawer` to the component's `imports` array, after `RecentActivity, MarketMovers`.

Above `@Component`, after `DASHBOARD_COLUMNS`, add:

```ts
/** The trade drawer's query parameter (v179 §3.2). dashboard.routes.ts's
 *  rerun rule names the same string. */
const TRADE_PARAM = 'trade';

/** First row with this id: a scaled-out trade's legs share it, leg 0 first. */
function findTrade(rows: readonly TradeRow[], id: string): TradeRow | null {
  return rows.find((row) => row.id === id) ?? null;
}
```

Template — on `<sb-positions-table …>` replace `(rowActivate)="open($event)"` with

```html
        phoneTap="emit"
        (rowActivate)="openTrade($event)"
```

replace `<sb-recent-activity [events]="activity()" />` with

```html
        <sb-recent-activity [events]="activity()" (eventActivate)="openActivity($event)" />
```

and directly after the `<sb-confirm-dialog … />` element add

```html
    <!-- v179 §3.2: one trade in a drawer on every device (a side panel on
         desktop, a bottom sheet on a phone). Mounted only while a trade is
         open; the open trade lives in ?trade= (see openTrade). -->
    @if (drawerTrade(); as trade) {
      <sb-trade-drawer [row]="trade" (closed)="closeTrade()" (actionDone)="onTradeAction()" />
    }
```

Class — directly after the `activityAsync` field (it must follow `recent`, which it reads), add:

```ts
  private readonly route = inject(ActivatedRoute);
  private readonly location = inject(Location);
  private readonly tradeParam = toSignal(
    this.route.queryParamMap.pipe(map((params) => params.get(TRADE_PARAM))),
    { initialValue: null },
  );

  /** The trade in the drawer, held here because a position row comes from
   *  sb-positions-table's own TradesStore, which this page cannot read
   *  (spec §3.2 "Row source"); an activity row comes from `recent`. */
  protected readonly drawerTrade = signal<TradeRow | null>(null);
  /** Opened from a link (reload, shared URL, Forward): there is no entry of
   *  ours for × to go back over, so × replaces the URL instead. */
  private coldOpen = false;
  /** The id an in-page open is pushing, until the URL carries it -- so a
   *  refresh landing mid-navigation cannot read the still-empty parameter
   *  as "closed". */
  private pendingId: string | null = null;
  /** The activity rows have answered (rows or an error): only then may a
   *  link whose trade is absent redirect (index Review Focus). */
  private readonly recentSettled = computed(() =>
    !this.recent.loading() && (!this.recent.empty() || this.recent.error() !== null));

  private readonly syncTradeFromUrl = effect(() => {
    const id = this.tradeParam();
    const settled = this.recentSettled();
    untracked(() => this.syncTrade(id, settled));
  });
```

Replace the `open(row)` method and its docstring with:

```ts
  /** A position or activity row: show it at once, then push ?trade= so Back
   *  closes it and the link can be shared. Pushed, never replaceUrl (spec
   *  §3.2). The ticker cell's anchor still goes to the full page. */
  protected openTrade(row: TradeRow): void {
    this.coldOpen = false;
    this.pendingId = row.id;
    this.drawerTrade.set(row);
    void this.router
      .navigate([], { relativeTo: this.route, queryParams: { [TRADE_PARAM]: row.id }, queryParamsHandling: 'merge' })
      .finally(() => { this.pendingId = null; });
  }

  /** Activity events derive from `recent`'s rows, so the row is there; the
   *  full page is the fallback if a refresh dropped it in between. */
  protected openActivity(event: ActivityEvent): void {
    const row = findTrade(this.recent.rows(), event.tradeId);
    if (row) this.openTrade(row);
    else void this.router.navigate(['/trades', event.tradeId]);
  }

  /** The drawer closed itself (×, Escape, backdrop) or an action finished.
   *  After Back the parameter is already gone: nothing to undo. */
  protected closeTrade(): void {
    const cold = this.coldOpen;
    this.drawerTrade.set(null);
    this.coldOpen = false;
    if (this.tradeParam() === null) return;
    if (!cold) {
      this.location.back();
      return;
    }
    void this.router.navigate([], {
      relativeTo: this.route, queryParams: { [TRADE_PARAM]: null }, queryParamsHandling: 'merge', replaceUrl: true,
    });
  }

  /** A close or cancel from the drawer changed the trade: refresh what shows
   *  it and close the now-stale summary. */
  protected onTradeAction(): void {
    this.store.load();
    this.recent.load();
    this.closeTrade();
  }

  /** URL → drawer. Back (no id) closes; a new id from a link opens the row
   *  once the activity rows have answered, or redirects with replaceUrl. */
  private syncTrade(id: string | null, settled: boolean): void {
    if (id === null) {
      if (this.pendingId === null) this.drawerTrade.set(null);
      return;
    }
    if (this.drawerTrade()?.id === id || !settled) return;
    const row = findTrade(this.recent.rows(), id);
    if (row === null) {
      void this.router.navigate(['/trades', id], { replaceUrl: true });
      return;
    }
    this.coldOpen = true;
    this.drawerTrade.set(row);
  }
```

Then `git grep -n "open(" frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts` — no caller of the removed `open(` may remain (the `toggleCloseAllMenu`/`closeAllMenuOpen` names are unrelated).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/routing/route-rerun.spec.ts --include src/app/app.routes.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/trade-drawer.spec.ts --include src/app/routing/route-refresh.service.spec.ts`
Expected: PASS, 0 failed. If the cold-link test sees the redirect before the rows arrive, `recentSettled` is reading a store that has not started loading — the Dashboard constructor's `setQuery` must still run before the effect's first flush; do not loosen the test.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/routing/route-rerun.ts frontend/src/app/routing/route-rerun.spec.ts frontend/src/app/workspaces/dashboard/dashboard.routes.ts frontend/src/app/app.routes.spec.ts
git commit -m "feat(v179): rerunExceptQueryParam -- the Dashboard skips its resolver for ?trade= alone

Identical URLs still re-resolve, so the SSE same-URL refresh is unchanged."
git add frontend/src/app/workspaces/dashboard/positions-table.ts frontend/src/app/workspaces/dashboard/positions-table.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git commit -m "feat(v179): Dashboard opens trades in a drawer on every device

Position rows emit (phoneTap=emit), activity rows open by tradeId; ?trade=
is pushed so Back closes it; x goes back after an in-page open and replaces
after a cold link; a link whose trade is not loaded goes to /trades/:id
with replaceUrl. No extra request, no resolver re-run."
```

---

