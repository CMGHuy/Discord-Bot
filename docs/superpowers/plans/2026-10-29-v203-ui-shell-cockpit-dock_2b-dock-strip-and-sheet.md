# UI shell cockpit (v203), part 2b: the dock, edge tab, strip and sheet

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) (§3 "Live", §4 "Data source", "Open/collapsed state", "Live strip", §6, §8 "Dock", "Strip and sheet", "Layout")
**Index:** [`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md). Its Global Constraints, Parallelisation, task ledger and cross-task contracts apply to every task here.

Part 2's overflow. Part 2 ([`_2-dock.md`](2026-10-29-v203-ui-shell-cockpit-dock_2-dock.md)) holds the four dock sections (V203-5, V203-5b, V203-6, V203-6b). This file holds V203-7, V203-7b, V203-8 and V203-8b, in that order. Each `b` task is a split that keeps a task under 20 KB: V203-7 and V203-8 build components, V203-7b and V203-8b wire them into the shell. `<wt>` is the plan's worktree root (absolute). FE paths are relative to `frontend/src/app/` unless they start with `frontend/`.

---

### Task V203-7: `sb-live-dock` and `sb-live-edge-tab`

**Model:** sonnet — two components composing finished parts; stub-store tests given here.

Ledger task V203-7 is split in two to stay under 20 KB: this half builds the dock and the edge tab, V203-7b docks them in the shell with the persisted per-page toggle and runs straight after this task.

**Files:**
- Create: `frontend/src/app/shell/live/live-dock.ts`, `frontend/src/app/shell/live/live-dock.spec.ts`
- Create: `frontend/src/app/shell/live/live-edge-tab.ts`, `frontend/src/app/shell/live/live-edge-tab.spec.ts`

**Interfaces:**
- Consumes: `LiveStore` (V203-2), `ConnectionStore` and `CLOCK` (`ui/clock.ts`, `Signal<number>`), each member as read in the code below; `LiveWarning`, `warningLabel` (V203-3); `LiveBotSection` (V203-4), `LiveAwaitingSection` (V203-5), `LiveHeatSection` (V203-5b), `LiveActivitySection` (V203-6b); `Button` (`button[sb-button]`), `Icon` (name `collapse`).
- Produces (index ledger, final): `LiveDock` (`sb-live-dock`), input `variant: 'docked' | 'sheet'`, output `close: void`. `LiveEdgeTab` (`sb-live-edge-tab`), inputs `warnings: readonly LiveWarning[]`, `heatText: string`, `awaitingCount: number | null`; output `expand: void`. Also exported from `live-edge-tab.ts`: `liveSummaryLabel(warnings, heatText, awaitingCount): string`, the accessible label the edge tab and V203-8's strip share, so a collapsed dock and the strip name a warning the same way. V203-7b mounts both; V203-8's sheet mounts `LiveDock` with `variant="sheet"`.

Behaviour pinned here:
- The dock shows, in order: a head (`Live`, then a control: the icon button `Collapse the live dock` when docked, the text button `Close` in the sheet; both emit `close`), then `sb-live-bot`, `sb-live-awaiting`, `sb-live-heat`, `sb-live-activity`. Its data is `LiveStore` and `ConnectionStore` only. Both section retries call `LiveStore.retry()`.
- **It never touches `RiskStore`.** No file under `shell/live/` names `RiskStore`, imports from `workspaces/risk` or calls `api.risk(`. The dock mounts with no `RiskStore` provider at all (it is route-scoped, so an `inject(RiskStore)` would throw) and makes no request of its own.
- The edge tab (spec §4 "Open/collapsed state") is one 40 px wide button: a status dot, `Live` rotated vertically, the heat figure (`heatStripText`'s words, passed in) and the awaiting count. Any warning tones it (`.warn`, today's `--warn`/`--warn-soft`) and is named in its accessible label. It never forces the dock open: only a tap does.

- [ ] **Step 1: Write the failing edge-tab spec**

Create `shell/live/live-edge-tab.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveEdgeTab, liveSummaryLabel } from './live-edge-tab';
import { LiveWarning, warningLabel } from './live-state';

const HEAT = 'Heat 2,010 € · 4.2% / 6%';
const ALL: LiveWarning[] = ['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'];

describe('liveSummaryLabel', () => {
  it('reads the heat and the count when calm', () => {
    expect(liveSummaryLabel([], HEAT, 3)).toBe(`Open the live dock. ${HEAT}. 3 awaiting order`);
    expect(liveSummaryLabel([], 'Heat —', null)).toBe('Open the live dock. Heat —');
  });
  it('names every warning, in order', () => {
    expect(liveSummaryLabel(['heat-near-cap', 'stale'], HEAT, 0))
      .toBe(`Open the live dock. Warning: Heat near cap, Data stale. ${HEAT}. 0 awaiting order`);
  });
});

describe('LiveEdgeTab', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(warnings: LiveWarning[], awaitingCount: number | null = 3) {
    const fixture = TestBed.createComponent(LiveEdgeTab);
    fixture.componentRef.setInput('warnings', warnings);
    fixture.componentRef.setInput('heatText', HEAT);
    fixture.componentRef.setInput('awaitingCount', awaitingCount);
    fixture.detectChanges();
    return { fixture, button: (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button.edge-tab')! };
  }

  it('shows the dot, the word Live, the heat figure and the count', () => {
    const { button } = mount([]);
    expect(button.querySelector('.dot')).not.toBeNull();
    expect(button.querySelector('.word')!.textContent!.trim()).toBe('Live');
    expect(button.querySelector('.heat')!.textContent!.trim()).toBe(HEAT);
    expect(button.querySelector('.count')!.textContent!.trim()).toBe('3');
    expect(button.classList).not.toContain('warn');
    expect(button.classList).toContain('sb-hit');
    expect(button.getAttribute('aria-label')).toBe(`Open the live dock. ${HEAT}. 3 awaiting order`);
  });

  it.each(ALL)('takes the warning tone and names it for %s', (warning) => {
    const { button } = mount([warning]);
    expect(button.classList).toContain('warn');
    expect(button.getAttribute('aria-label')).toContain(`Warning: ${warningLabel(warning)}`);
  });

  it('omits the count before /live answers', () => {
    expect(mount([], null).button.querySelector('.count')).toBeNull();
  });

  it('asks to expand on a tap, and only then', () => {
    const { fixture, button } = mount(['stale']);
    let expanded = 0;
    fixture.componentInstance.expand.subscribe(() => expanded++);
    expect(expanded).toBe(0);
    button.click();
    expect(expanded).toBe(1);
  });
});
```

- [ ] **Step 2: Write the failing dock spec**

Create `shell/live/live-dock.spec.ts`:

```ts
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveAwaiting, LiveEvent, LiveEventsMeta, LiveHeat, LiveKillswitch } from '../../api/models';
import { ConnectionState, ConnectionStore } from '../../stores/connection.store';
import { LiveStore } from '../../stores/live.store';
import { CLOCK } from '../../ui/clock';
import { LiveDock } from './live-dock';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const HEAT: LiveHeat = {
  availability: 'ok', as_of: ago(1), reason: null, open_pct: 5, cap_pct: 6, utilisation_pct: 85, open_amount: 2400,
  cap_amount: 2893, headroom_pct: 1, headroom_amount: 493, balance: 48210, includes_resting: true,
};

describe('LiveDock (v203)', () => {
  const live = {
    heat: signal<LiveHeat | null>(HEAT),
    awaiting: signal<LiveAwaiting | null>({ availability: 'ok', as_of: ago(1), reason: null, count: 3, next_expiry: null }),
    killswitch: signal<LiveKillswitch | null>({ availability: 'ok', as_of: ago(1), reason: null, engaged: true, since: '2026-10-29T08:31:00Z', detail: null }),
    events: signal<readonly LiveEvent[]>([]),
    eventsMeta: signal<LiveEventsMeta | null>({ availability: 'ok', as_of: ago(1), missing: [] }),
    loading: signal(false),
    failed: signal(false),
    retry: vi.fn(),
  };
  const connection = {
    botAlive: signal<boolean | null>(false), botHealthy: signal<boolean | null>(true), scanRunning: signal(false),
    botLastSuccess: signal<string | null>(ago(2)), botLastSeen: signal<string | null>(ago(1)),
    state: signal<ConnectionState>('live'), marketActive: signal<boolean | null>(true), currency: signal('$'),
  };

  beforeEach(() => {
    live.retry.mockClear();
    live.heat.set(HEAT);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: LiveStore, useValue: live },
        { provide: ConnectionStore, useValue: connection },
        { provide: CLOCK, useValue: signal(NOW.getTime()) },
      ],
    });
  });

  function mount(variant: 'docked' | 'sheet') {
    const fixture = TestBed.createComponent(LiveDock);
    fixture.componentRef.setInput('variant', variant);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  it('holds the four sections in order under a Live head', () => {
    const { el } = mount('docked');
    expect(el.querySelector('.dock-head .dock-title')!.textContent!.trim()).toBe('Live');
    expect([...el.querySelectorAll('.dock > *:not(.dock-head)')].map((node) => node.tagName.toLowerCase()))
      .toEqual(['sb-live-bot', 'sb-live-awaiting', 'sb-live-heat', 'sb-live-activity']);
  });

  it('feeds the sections from LiveStore and ConnectionStore, money in the account currency', () => {
    const { el } = mount('docked');
    const text = (selector: string) => el.querySelector(selector)!.textContent!.replace(/\s+/g, ' ').trim();
    expect(text('sb-live-bot dl > div.row dd')).toBe('Down');
    expect(text('sb-live-bot dl > div.row:last-child dd')).toBe('Active: new alerts paused since 09:31');
    expect(text('sb-live-awaiting .figure')).toBe('3 awaiting order');
    expect(text('sb-live-heat .at-risk')).toBe('2,400 $ at risk · 5% of 48,210 $ · cap 6% (2,893 $)');
    expect(el.querySelector('sb-live-heat .at-risk')!.classList).toContain('warn');
    expect(text('sb-live-activity .quiet')).toBe('Nothing yet today');
  });

  it('routes a section retry to LiveStore.retry', () => {
    live.heat.set({ ...HEAT, availability: 'unavailable', open_pct: null });
    const { el } = mount('docked');
    el.querySelector<HTMLButtonElement>('sb-live-heat button.retry')!.click();
    expect(live.retry).toHaveBeenCalledTimes(1);
  });

  it('collapses from an icon button when docked, and closes from a text button in the sheet', () => {
    const docked = mount('docked');
    let closed = 0;
    docked.fixture.componentInstance.close.subscribe(() => closed++);
    const collapse = docked.el.querySelector<HTMLButtonElement>('.dock-head button')!;
    expect(collapse.getAttribute('aria-label')).toBe('Collapse the live dock');
    expect(collapse.classList).toContain('sb-hit');
    collapse.click();
    expect(closed).toBe(1);
    const sheet = mount('sheet');
    expect(sheet.el.querySelector('.dock-head button')!.textContent!.trim()).toBe('Close');
  });

  it('never touches RiskStore or /risk (spec v202 §4 "Data source")', () => {
    mount('docked');                                        // no RiskStore provider: injecting it would throw
    expect(TestBed.inject(HttpTestingController).match(() => true)).toEqual([]);
    const dir = join(process.cwd(), 'src/app/shell/live');
    const sources = readdirSync(dir).filter((name) => name.endsWith('.ts') && !name.endsWith('.spec.ts'))
      .map((name) => [name, readFileSync(join(dir, name), 'utf8')] as const);
    expect(sources.length).toBeGreaterThan(5);
    expect(sources.filter(([, source]) => /RiskStore|workspaces\/risk|api\.risk\(/.test(source)).map(([name]) => name)).toEqual([]);
  });
});
```

- [ ] **Step 3: Run both to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-edge-tab.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-dock.spec.ts
```

Expected: FAIL to compile: `./live-edge-tab` and `./live-dock` do not exist.

- [ ] **Step 4: Write the edge tab**

Create `shell/live/live-edge-tab.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { LiveWarning, warningLabel } from './live-state';

/** The collapsed dock's and the strip's accessible label: every warning named. */
export function liveSummaryLabel(warnings: readonly LiveWarning[], heatText: string, awaitingCount: number | null): string {
  const parts = ['Open the live dock'];
  if (warnings.length > 0) parts.push(`Warning: ${warnings.map(warningLabel).join(', ')}`);
  parts.push(heatText);
  if (awaitingCount !== null) parts.push(`${awaitingCount} awaiting order`);
  return parts.join('. ');
}

/**
 * The collapsed Live dock -- v203 (spec v202 §4, D4). A 40px edge tab: a
 * status dot, "Live" rotated, the heat figure and the awaiting count. Any
 * warning tones it and is named in its label, so a collapsed choice can
 * never hide an alarm; it never forces the dock open.
 */
@Component({
  selector: 'sb-live-edge-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="edge-tab sb-hit" [class.warn]="warn()" [attr.aria-label]="label()" (click)="expand.emit()">
      <span class="dot" aria-hidden="true"></span>
      <span class="word" aria-hidden="true">Live</span>
      <span class="heat" aria-hidden="true">{{ heatText() }}</span>
      @if (awaitingCount() !== null) { <span class="count" aria-hidden="true">{{ awaitingCount() }}</span> }
    </button>
  `,
  styles: `
    :host { display: block; height: 100%; }
    .edge-tab {
      display: flex; flex-direction: column; align-items: center; gap: var(--space-10);
      width: 40px; height: 100%; padding: var(--space-10) 0;
      border: 0; background: transparent; color: var(--text-secondary);
      font: inherit; font-size: var(--text-micro); cursor: pointer;
      transition: background var(--transition), color var(--transition);
    }
    .edge-tab:hover { background: var(--surface-raised); color: var(--text); }
    .edge-tab:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--pos); }
    .word, .heat { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
    .word { color: var(--text); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    .heat { font-variant-numeric: tabular-nums; }
    .count { min-width: 20px; padding: 2px 4px; border-radius: var(--radius-sm); background: var(--surface-raised); color: var(--text); text-align: center; font-variant-numeric: tabular-nums; }
    .warn { background: var(--warn-soft); color: var(--warn); }
    .warn .dot { background: var(--warn); }
    .warn .word { color: var(--warn); }
  `,
})
export class LiveEdgeTab {
  readonly warnings = input<readonly LiveWarning[]>([]);
  readonly heatText = input.required<string>();
  readonly awaitingCount = input<number | null>(null);
  readonly expand = output<void>();

  protected readonly warn = computed(() => this.warnings().length > 0);
  protected readonly label = computed(() => liveSummaryLabel(this.warnings(), this.heatText(), this.awaitingCount()));
}
```

- [ ] **Step 5: Write the dock**

Create `shell/live/live-dock.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { ConnectionStore } from '../../stores/connection.store';
import { LiveStore } from '../../stores/live.store';
import { Button } from '../../ui/button';
import { CLOCK } from '../../ui/clock';
import { Icon } from '../../ui/icon';
import { LiveActivitySection } from './live-activity-section';
import { LiveAwaitingSection } from './live-awaiting-section';
import { LiveBotSection } from './live-bot-section';
import { LiveHeatSection } from './live-heat-section';

/**
 * The Live dock -- v203 (spec v202 §4). Four sections: Bot, Plans awaiting
 * order, Portfolio heat, Activity. It reads LiveStore (/live) and the root
 * ConnectionStore and nothing else: never RiskStore, never /risk. The same
 * component is the docked column (desktop) and the sheet's body (tablet,
 * phone); only the head's control differs.
 */
@Component({
  selector: 'sb-live-dock',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Icon, LiveBotSection, LiveAwaitingSection, LiveHeatSection, LiveActivitySection],
  template: `
    <div class="dock">
      <div class="dock-head">
        <span class="dock-title">Live</span>
        @if (variant() === 'docked') {
          <button sb-button variant="icon" type="button" class="dock-close sb-hit"
                  aria-label="Collapse the live dock" (click)="close.emit()">
            <sb-icon name="collapse" />
          </button>
        } @else {
          <button sb-button variant="secondary" type="button" class="dock-close sb-hit" (click)="close.emit()">Close</button>
        }
      </div>
      <sb-live-bot
        [botAlive]="connection.botAlive()" [botHealthy]="connection.botHealthy()" [scanRunning]="connection.scanRunning()"
        [lastSuccess]="connection.botLastSuccess()" [lastSeen]="connection.botLastSeen()" [streamState]="connection.state()"
        [marketActive]="connection.marketActive()" [killswitch]="live.killswitch()" [now]="now()" />
      <sb-live-awaiting [awaiting]="live.awaiting()" [loading]="live.loading()" [now]="now()" />
      <sb-live-heat [heat]="live.heat()" [loading]="live.loading()" [currency]="connection.currency()" [now]="now()"
                    (retry)="live.retry()" />
      <sb-live-activity [events]="live.events()" [meta]="live.eventsMeta()" [loading]="live.loading()"
                        [lastSuccess]="connection.botLastSuccess()" [now]="now()" [currency]="connection.currency()"
                        (retry)="live.retry()" />
    </div>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .dock { display: flex; flex-direction: column; gap: var(--space-14); padding: var(--space-14); }
    .dock-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-8); }
    .dock-title { color: var(--text); font-size: var(--text-body); font-weight: 600; }
    .dock > :not(.dock-head) { padding-top: var(--space-14); border-top: 1px solid var(--border); }
  `,
})
export class LiveDock {
  readonly variant = input<'docked' | 'sheet'>('docked');
  readonly close = output<void>();

  protected readonly live = inject(LiveStore);
  protected readonly connection = inject(ConnectionStore);
  private readonly clock = inject(CLOCK);
  /** One clock for every section, so their ages agree to the tick. */
  protected readonly now = computed(() => new Date(this.clock()));
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-edge-tab.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-dock.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. If `ConnectionStore.scanRunning` is not a signal on this `main`, read `stores/connection.store.ts` for its name and use that; do not add a member to the store.

Complexity: `liveSummaryLabel` 3; nothing else branches outside templates.

Layout: no screen shows these until V203-7b mounts them; its three-width audit covers the docked dock and the edge tab, so record that the visual check is deferred there.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-edge-tab.ts frontend/src/app/shell/live/live-edge-tab.spec.ts \
  frontend/src/app/shell/live/live-dock.ts frontend/src/app/shell/live/live-dock.spec.ts
git -C <wt> commit -m "feat(v203): the Live dock and its edge tab

sb-live-dock holds Bot, Plans awaiting order, Portfolio heat and
Activity, reading only LiveStore and ConnectionStore (a spec pins that
it never touches RiskStore or /risk). sb-live-edge-tab is the collapsed
40px tab: dot, Live, heat and awaiting count, warning-toned with the
warning named in its label whenever one applies.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task V203-7b: Desktop docking with the persisted per-page toggle

**Model:** sonnet — shell wiring over finished contracts; every edit given here.

The second half of ledger task V203-7, split to stay under 20 KB. It runs straight after V203-7.

**Files:**
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `LiveDock`, `LiveEdgeTab` (V203-7); `DockState` (V203-3b: `docked()`, `open()`, `toggle()`); `LiveStore` (V203-2: `heat()`, `awaiting()`); `liveWarnings`, `heatStripText` (V203-3); the shell's own `connection`, `clock` and `killswitchOn()`.
- Produces (index ledger, final): the shell grid `.workspace-row` = `main.workspace` + `aside.live-column` (320 px open / 40 px collapsed, only when `dock.docked()`). On `Shell` (protected, for V203-8b and V203-9): `dock: DockState`, `live: LiveStore`, `liveNow: Signal<Date>`, `dockWarnings: Signal<LiveWarning[]>`, `heatText: Signal<string>`, `awaitingCount: Signal<number | null>`.

Behaviour pinned here (spec v202 §4 "Open/collapsed state", §8 "Dock"):
- From 1024 px the workspace and the dock sit side by side in `.workspace-row`. Open, the column is 320 px and holds `sb-live-dock`; collapsed, 40 px and holds the edge tab. The column is sticky under the bar and scrolls on its own, so it never covers the page. Below 1024 px there is no column at all (V203-8b adds the strip and sheet).
- Open on `/dashboard` and `/risk` by default, collapsed elsewhere. The collapse button and the edge tab both call `dock.toggle()`, which stores the choice per destination through `PreferencesStore` (key `shell.dock`), never browser storage.
- `dockWarnings` is `liveWarnings` over the `/live` heat utilisation, `ConnectionStore`'s last success, stream state and bot liveness, and the shell's `killswitchOn()` (the reading the killswitch chip and strip show, so the top bar and the tab never disagree). The edge tab shows each one as its warning tone and in its label.

`shell.spec.ts` assertion changes, listed as the v195 `fdf6b78a` precedent requires:
- Moved: "runs the tape as a strip under the top bar" expected `.main` children `['header', 'div', 'main']`; they are now `['header', 'div', 'div']`, the third being `.workspace-row` with `main.workspace` inside it.

- [ ] **Step 1: Write the failing shell spec**

In `shell/shell.spec.ts`, in "runs the tape as a strip under the top bar, not inside it (v195 Phase 3)", replace

```ts
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'div', 'main']);
```

with

```ts
    // v203 Moved: the workspace now sits in .workspace-row beside the Live column.
    expect(Array.from(main.children).map((c) => c.tagName.toLowerCase()))
      .toEqual(['header', 'div', 'div']);
    expect(main.children[2].classList).toContain('workspace-row');
    expect(main.querySelector(':scope > .workspace-row > main.workspace')).not.toBeNull();
```

Then append this describe at the end of the file:

```ts
describe('shell live dock (v203)', () => {
  const NOW = Date.parse('2026-10-29T13:00:00Z');
  const narrow = signal(false);
  const at = '2026-10-29T12:59:00Z';
  const SNAPSHOT = {
    heat: { availability: 'ok', as_of: at, reason: null, open_pct: 5.1, cap_pct: 6, utilisation_pct: 85, open_amount: 2459,
            cap_amount: 2893, headroom_pct: 0.9, headroom_amount: 434, balance: 48210, includes_resting: true },
    awaiting: { availability: 'ok', as_of: at, reason: null, count: 3, next_expiry: null },
    killswitch: { availability: 'ok', as_of: at, reason: null, engaged: false, since: null, detail: null },
    events: [], events_meta: { availability: 'ok', as_of: at, missing: [] },
  };
  const scan = (botAlive: boolean) => ({
    pending: false, triggered_at: null, paused: false, paused_at: null, running: false, bot_alive: botAlive,
    bot_last_seen: '2026-10-29T12:58:00Z', bot_healthy: true, bot_last_success: '2026-10-29T12:58:00Z',
    bot_consecutive_failures: 0, bot_session_active: true, bot_scan_paused: false, progress: null,
  });

  beforeEach(() => {
    narrow.set(false);
    TestBed.configureTestingModule({ providers: shellProviders(['dashboard', 'trades', 'risk'].map((path) => ({ path, component: Blank }))) });
    TestBed.overrideProvider(CLOCK, { useValue: signal(NOW) });
    TestBed.overrideProvider(ViewportService, { useValue: { isPhone: signal(false), isNarrow: narrow, viewport: signal('lg') } });
  });

  async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function mount(url: string) {
    await TestBed.inject(Router).navigateByUrl(url);
    const fixture = TestBed.createComponent(Shell);
    await settle(fixture);
    const backend = TestBed.inject(HttpTestingController);
    for (const request of backend.match((r) => r.url.endsWith('/system/preferences'))) request.flush({ preferences: {} });
    for (const request of backend.match((r) => r.url.endsWith('/live'))) request.flush(SNAPSHOT);
    await settle(fixture);
    return { fixture, el: fixture.nativeElement as HTMLElement, backend };
  }

  it('docks the open dock on Dashboard, beside the workspace', async () => {
    const { el } = await mount('/dashboard');
    const row = el.querySelector('.main > .workspace-row')!;
    expect(row.classList).toContain('dock-open');
    expect(row.querySelector(':scope > main.workspace + aside.live-column[aria-label="Live"] > sb-live-dock')).not.toBeNull();
    expect(row.querySelector('sb-live-edge-tab')).toBeNull();
  });

  it('collapses to the edge tab elsewhere, warning-toned and named', async () => {
    const { el } = await mount('/trades');
    expect(el.querySelector('.workspace-row')!.classList).toContain('dock-collapsed');
    const tab = el.querySelector<HTMLButtonElement>('aside.live-column > sb-live-edge-tab button.edge-tab')!;
    expect(tab.classList).toContain('warn');
    expect(tab.getAttribute('aria-label')).toBe('Open the live dock. Warning: Heat near cap. Heat 2,459 € · 5.1% / 6%. 3 awaiting order');
    expect(el.querySelector('sb-live-dock')).toBeNull();
  });

  it('names a downed bot on the edge tab', async () => {
    const { fixture, el, backend } = await mount('/trades');
    for (const request of backend.match((r) => r.url.endsWith('/system/scan'))) request.flush(scan(false));
    await settle(fixture);
    expect(el.querySelector('button.edge-tab')!.getAttribute('aria-label')).toContain('Warning: Heat near cap, Bot down.');
  });

  it('remembers the toggle per destination, through PreferencesStore', async () => {
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.edge-tab')!.click();
    await settle(fixture);
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();
    expect(TestBed.inject(PreferencesStore).values()['shell.dock']).toEqual({ '/trades': true });
    el.querySelector<HTMLButtonElement>('sb-live-dock .dock-head button')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-edge-tab')).not.toBeNull();
    expect(TestBed.inject(PreferencesStore).values()['shell.dock']).toEqual({ '/trades': false });
  });

  it('never docks below 1024 px', async () => {
    narrow.set(true);
    const { el } = await mount('/dashboard');
    expect(el.querySelector('aside.live-column')).toBeNull();
    expect(el.querySelector('sb-live-dock')).toBeNull();
    expect(el.querySelector('.workspace-row')!.className).not.toMatch(/dock-/);
  });

  it('sizes the column from one token: 320px open, 40px collapsed, sticky under the bar', () => {
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    const rule = (selector: string) => css.match(new RegExp(`^${selector.replace(/[.]/g, '\\.')} \\{[^}]*\\}`, 'm'))?.[0] ?? '';
    expect(rule('.dock-open')).toContain('--dock-width: 320px;');
    expect(rule('.dock-collapsed')).toContain('--dock-width: 40px;');
    for (const declaration of ['width: var(--dock-width);', 'position: sticky;', 'top: var(--topbar-h);', 'overflow-y: auto;']) {
      expect(rule('.live-column')).toContain(declaration);
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
```

Expected: FAIL: the shell has no `.workspace-row`, `aside.live-column` or edge tab.

- [ ] **Step 3: Wire the dock into the shell**

In `shell/shell.ts`, add these imports beside the other shell imports:

```ts
import { LiveStore } from '../stores/live.store';
import { DockState } from './live/dock-state';
import { LiveDock } from './live/live-dock';
import { LiveEdgeTab } from './live/live-edge-tab';
import { heatStripText, liveWarnings } from './live/live-state';
```

add `LiveDock, LiveEdgeTab` to the component's `imports` array, and add this block after the killswitch members (`killswitchOn`, `killswitchStale`) and before the constructor:

```ts
  /* -- v203: the Live dock (spec v202 §4) ------------------------------ */

  /** Where the dock is and whether it is open, per destination. */
  protected readonly dock = inject(DockState);
  /** /live: the dock's, the edge tab's and the strip's only data. */
  protected readonly live = inject(LiveStore);
  /** The shell clock as a Date, so every live surface ages on one tick. */
  protected readonly liveNow = computed(() => new Date(this.clock()));
  /** Every warning that applies, worded once in live-state.ts. The
   *  killswitch reading is the chip's own, so the bar and the tab agree. */
  protected readonly dockWarnings = computed(() => liveWarnings({
    utilisationPct: this.live.heat()?.utilisation_pct ?? null,
    lastSuccess: this.connection.botLastSuccess(),
    now: this.liveNow(),
    streamState: this.connection.state(),
    botAlive: this.connection.botAlive(),
    killswitchOn: this.killswitchOn(),
  }));
  protected readonly heatText = computed(() => heatStripText(this.live.heat(), this.connection.currency()));
  protected readonly awaitingCount = computed(() => this.live.awaiting()?.count ?? null);
```

In `shell/shell.html`, wrap the existing `<main class="workspace" …>…</main>` element, unchanged, in the row and add the column after it:

```html
    <!-- v203 (spec v202 §4): the workspace and, from 1024px, the Live dock
         beside it -- 320px open, a 40px edge tab collapsed. Below 1024px the
         dock never docks; the live strip opens it as a sheet. -->
    <div class="workspace-row" [class.dock-open]="dock.docked() && dock.open()"
         [class.dock-collapsed]="dock.docked() && !dock.open()">
      <main class="workspace" [class.route-pending]="routeLoading.visible()" [attr.aria-busy]="routeLoading.visible() ? 'true' : null">
        <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null"><router-outlet /></div>
        @if (routeLoading.visible()) {
          <div class="route-loading-overlay" role="status" aria-live="polite"><span class="route-loading-mark" aria-hidden="true"></span><span>{{ routeLoading.label() }}</span></div>
        }
      </main>
      @if (dock.docked()) {
        <aside class="live-column" aria-label="Live">
          @if (dock.open()) {
            <sb-live-dock variant="docked" (close)="dock.toggle()" />
          } @else {
            <sb-live-edge-tab [warnings]="dockWarnings()" [heatText]="heatText()" [awaitingCount]="awaitingCount()"
                              (expand)="dock.toggle()" />
          }
        </aside>
      }
    </div>
```

In `shell/shell.css`, after the `.workspace { position: relative; }` group, add:

```css
/* v203 (spec v202 §4): the workspace and the docked Live column side by
   side, from 1024px only (DockState.docked). The column is sticky under the
   bar and scrolls on its own: a long page never scrolls the dock away, and
   the dock takes its own width rather than covering the page. */
.workspace-row { display: flex; flex: 1; min-width: 0; align-items: flex-start; }
.workspace-row > .workspace { align-self: stretch; }
.dock-open { --dock-width: 320px; }
.dock-collapsed { --dock-width: 40px; }
.live-column {
  flex: 0 0 var(--dock-width);
  width: var(--dock-width);
  position: sticky;
  top: var(--topbar-h);
  height: calc(100dvh - var(--topbar-h));
  overflow-y: auto;
  overscroll-behavior: contain;
  border-left: 1px solid var(--border);
  background: var(--surface);
}
```

No new `@media` rule: docking is `DockState.docked()` (`ViewportService.isNarrow`), so the breakpoint stays in `ui/breakpoints.ts` and the shell spec's declared-breakpoints check is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-dock.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. Other shell describes never flush `/live`, so their dock sections read `Loading…`; that is expected. If an older shell assertion counts shell-wide buttons or landmarks and now sees the edge tab or the `aside`, update it as **Moved** (name the new element in a comment), never delete it, and list it in the report.

Complexity: the shell's new computeds are 1–2 each.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. Report: no horizontal scroll at any width; at 1440 the dock is open on `/dashboard` and `/risk` (320 px) and collapsed to the 40 px edge tab on `/trades`, `/watchlist`, `/insights/analytics` and `/system`, the workspace narrows beside it and nothing overlaps; the edge tab, the collapse button and every dock link meet the 44 px target under touch; the dock scrolls inside its column on a short window. At 768 and 390 there is no column (the strip arrives in V203-8b). V203-10 adds the audit's own `dock` check.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git -C <wt> commit -m "feat(v203): dock the Live column beside the workspace from 1024px

The workspace and an aside.live-column share .workspace-row: 320px
holding sb-live-dock when open, a 40px sb-live-edge-tab when collapsed.
Open on Dashboard and Risk by default; the choice is stored per
destination through PreferencesStore. The edge tab takes the warning
tone and names every warning, so a collapsed dock never hides an alarm.

Moved: the tape test's .main children are header, tape and the row.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-8: `sb-live-strip` and `sb-live-sheet`

**Model:** sonnet — two small components on the More-sheet pattern; every word and test given here.

Ledger task V203-8 is split in two to stay under 20 KB: this half builds the strip and the sheet, V203-8b mounts them in the shell for tablet and phone and runs straight after this task.

**Files:**
- Create: `frontend/src/app/shell/live/live-strip.ts`, `frontend/src/app/shell/live/live-strip.spec.ts`
- Create: `frontend/src/app/shell/live/live-sheet.ts`, `frontend/src/app/shell/live/live-sheet.spec.ts`

**Interfaces:**
- Consumes: `LiveWarning`, `warningLabel` (V203-3); `liveSummaryLabel` (V203-7, `live-edge-tab.ts`); `LiveDock` (V203-7); `scanAge` (`shell/freshness-chip.ts`); `FocusTrap` (`[sbFocusTrap]`, `ui/focus-trap.ts`: focuses the first focusable on init, wraps Tab, returns focus on destroy).
- Produces (index ledger, final): `LiveStrip` (`sb-live-strip`), inputs `warnings: readonly LiveWarning[]`, `heatText: string`, `awaitingCount: number | null`, `lastSuccess: string | null`, `now: Date`; output `opened: void`. `LiveSheet` (`sb-live-sheet`), inputs `open: boolean`, `side: 'right' | 'bottom'`; output `closed: void`. V203-8b mounts both.

Behaviour pinned here (spec v202 §4 "Live strip", §8 "Strip and sheet"):
- **Strip:** one 40 px button under the tape: a status dot, the last scan age (`6m ago`, or `No scan yet`), the heat words (`Heat 2,010 € · 4.2% / 6%`, amber near the cap, `· Over cap` above it, both from `heatStripText`), `3 awaiting order` (absent before `/live` answers) and `Live ›`. It takes the edge tab's warning tone for every warning, and its accessible label is `liveSummaryLabel`'s, plus `. Last scan 6m ago`, so the strip and the collapsed dock name a warning in the same words. A tap emits `opened`.
- **Sheet:** nothing while closed. Open, a scrim and a `role=dialog` `aria-modal` panel labelled `Live` holding `sb-live-dock variant="sheet"`: from the right on a tablet (`side="right"`), from the bottom on a phone (`side="bottom"`, with the More sheet's `sb-sheet-in` entrance). Focus is trapped (`sbFocusTrap`, as `more-sheet.ts` does). Escape, a scrim tap and the dock's `Close` all emit `closed`; an Escape while closed emits nothing.

- [ ] **Step 1: Write the failing strip spec**

Create `shell/live/live-strip.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveWarning, warningLabel } from './live-state';
import { LiveStrip } from './live-strip';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const HEAT = 'Heat 2,010 € · 4.2% / 6%';
const ALL: LiveWarning[] = ['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'];

describe('LiveStrip (v203)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(warnings: LiveWarning[], awaitingCount: number | null = 3, lastSuccess: string | null = ago(6)) {
    const fixture = TestBed.createComponent(LiveStrip);
    fixture.componentRef.setInput('warnings', warnings);
    fixture.componentRef.setInput('heatText', HEAT);
    fixture.componentRef.setInput('awaitingCount', awaitingCount);
    fixture.componentRef.setInput('lastSuccess', lastSuccess);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, button: (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button.live-strip')! };
  }
  const text = (button: HTMLElement, selector: string) => button.querySelector(selector)?.textContent?.trim() ?? null;

  it('reads dot, scan age, heat, awaiting count and Live ›, in that order', () => {
    const { button } = mount([]);
    expect([...button.children].map((child) => child.className.split(' ')[0])).toEqual(['dot', 'age', 'heat', 'count', 'go']);
    expect(text(button, '.age')).toBe('6m ago');
    expect(text(button, '.heat')).toBe(HEAT);
    expect(text(button, '.count')).toBe('3 awaiting order');
    expect(text(button, '.go')).toBe('Live ›');
    expect(button.classList).not.toContain('warn');
    expect(button.classList).toContain('sb-hit');
    expect(button.getAttribute('aria-haspopup')).toBe('dialog');
    expect(button.getAttribute('aria-label')).toBe(`Open the live dock. ${HEAT}. 3 awaiting order. Last scan 6m ago`);
  });

  it.each(ALL)('takes the edge tab warning tone and names %s', (warning) => {
    const { button } = mount([warning]);
    expect(button.classList).toContain('warn');
    expect(button.getAttribute('aria-label')).toContain(`Warning: ${warningLabel(warning)}`);
  });

  it('turns the heat amber only for a heat warning', () => {
    expect(mount(['heat-near-cap']).button.querySelector('.heat')!.classList).toContain('near');
    expect(mount(['over-cap']).button.querySelector('.heat')!.classList).toContain('near');
    expect(mount(['stale']).button.querySelector('.heat')!.classList).not.toContain('near');
  });

  it('says No scan yet without a success, and omits the count before /live answers', () => {
    const { button } = mount([], null, null);
    expect(text(button, '.age')).toBe('No scan yet');
    expect(button.querySelector('.count')).toBeNull();
  });

  it('asks for the sheet on a tap', () => {
    const { fixture, button } = mount([]);
    let opened = 0;
    fixture.componentInstance.opened.subscribe(() => opened++);
    button.click();
    expect(opened).toBe(1);
  });
});
```

- [ ] **Step 2: Write the failing sheet spec**

Create `shell/live/live-sheet.spec.ts`. It swaps the real dock for a stub, so the sheet is tested alone:

```ts
import { Component, input, output, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveDock } from './live-dock';
import { LiveSheet } from './live-sheet';

@Component({
  selector: 'sb-live-dock',
  template: '<button type="button" class="first">First</button><button type="button" class="dock-close" (click)="close.emit()">Close</button>',
})
class StubDock {
  readonly variant = input<'docked' | 'sheet'>('docked');
  readonly close = output<void>();
}

describe('LiveSheet (v203)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    TestBed.overrideComponent(LiveSheet, { remove: { imports: [LiveDock] }, add: { imports: [StubDock] } });
  });

  function mount(open: boolean, side: 'right' | 'bottom' = 'right') {
    const fixture = TestBed.createComponent(LiveSheet);
    fixture.componentRef.setInput('open', open);
    fixture.componentRef.setInput('side', side);
    fixture.detectChanges();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => closed++);
    return { fixture, el: fixture.nativeElement as HTMLElement, closed: () => closed };
  }
  const escape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

  it('renders nothing while closed, and ignores Escape then', () => {
    const { el, closed } = mount(false);
    expect(el.querySelector('[role=dialog]')).toBeNull();
    expect(el.querySelector('.scrim')).toBeNull();
    escape();
    expect(closed()).toBe(0);
  });

  it('opens from the right as a labelled modal holding the dock in its sheet variant', () => {
    const { fixture, el } = mount(true, 'right');
    const dialog = el.querySelector('[role=dialog]')!;
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe('Live');
    expect(dialog.classList).toContain('right');
    expect(dialog.classList).not.toContain('sb-sheet-in');
    expect(fixture.debugElement.query(By.directive(StubDock)).componentInstance.variant()).toBe('sheet');
  });

  it('rises from the bottom on a phone', () => {
    const dialog = mount(true, 'bottom').el.querySelector('[role=dialog]')!;
    expect(dialog.classList).toContain('bottom');
    expect(dialog.classList).toContain('sb-sheet-in');
  });

  it('traps focus: the first control takes it, and Tab wraps from the last', () => {
    const { el } = mount(true);
    expect(document.activeElement).toBe(el.querySelector('button.first'));
    const last = el.querySelector<HTMLButtonElement>('button.dock-close')!;
    last.focus();
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(el.querySelector('button.first'));
  });

  it('closes on Escape, on a scrim tap and from the dock', () => {
    const { el, closed } = mount(true);
    escape();
    el.querySelector<HTMLElement>('.scrim')!.click();
    el.querySelector<HTMLButtonElement>('button.dock-close')!.click();
    expect(closed()).toBe(3);
  });
});
```

- [ ] **Step 3: Run both to verify they fail**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-strip.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-sheet.spec.ts
```

Expected: FAIL to compile: `./live-strip` and `./live-sheet` do not exist.

- [ ] **Step 4: Write the strip**

Create `shell/live/live-strip.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { scanAge } from '../freshness-chip';
import { liveSummaryLabel } from './live-edge-tab';
import { LiveWarning } from './live-state';

const HEAT_WARNINGS: ReadonlySet<LiveWarning> = new Set(['heat-near-cap', 'over-cap']);

/**
 * The live strip -- v203 (spec v202 §4 "Live strip"). Tablet and phone
 * only: one 40px line under the tape that opens the dock as a sheet. It
 * takes the edge tab's warning tone and label, so a state reads the same
 * on both.
 */
@Component({
  selector: 'sb-live-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="live-strip sb-hit" [class.warn]="warnings().length > 0"
            aria-haspopup="dialog" [attr.aria-label]="label()" (click)="opened.emit()">
      <span class="dot" aria-hidden="true"></span>
      <span class="age" aria-hidden="true">{{ age() }}</span>
      <span class="heat" [class.near]="heatWarn()" aria-hidden="true">{{ heatText() }}</span>
      @if (awaitingCount() !== null) { <span class="count" aria-hidden="true">{{ awaitingCount() }} awaiting order</span> }
      <span class="go" aria-hidden="true">Live ›</span>
    </button>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .live-strip {
      display: flex; align-items: center; gap: var(--space-10);
      width: 100%; height: 40px; padding: 0 var(--space-14); overflow: hidden;
      border: 0; border-bottom: 1px solid var(--border); background: var(--surface);
      color: var(--text-secondary); font: inherit; font-size: var(--text-chip); text-align: left; cursor: pointer;
    }
    .live-strip:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--pos); }
    .age, .count, .go { flex: none; white-space: nowrap; }
    .heat { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); font-variant-numeric: tabular-nums; }
    .heat.near { color: var(--warn); }
    .go { margin-left: auto; color: var(--accent); }
    .warn { background: var(--warn-soft); }
    .warn .dot { background: var(--warn); }
  `,
})
export class LiveStrip {
  readonly warnings = input<readonly LiveWarning[]>([]);
  readonly heatText = input.required<string>();
  readonly awaitingCount = input<number | null>(null);
  readonly lastSuccess = input<string | null>(null);
  readonly now = input.required<Date>();
  readonly opened = output<void>();

  protected readonly age = computed(() => scanAge(this.lastSuccess(), this.now().getTime()) ?? 'No scan yet');
  protected readonly heatWarn = computed(() => this.warnings().some((warning) => HEAT_WARNINGS.has(warning)));
  protected readonly label = computed(() =>
    `${liveSummaryLabel(this.warnings(), this.heatText(), this.awaitingCount())}. Last scan ${this.age()}`);
}
```

- [ ] **Step 5: Write the sheet**

Create `shell/live/live-sheet.ts`:

```ts
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { FocusTrap } from '../../ui/focus-trap';
import { LiveDock } from './live-dock';

/**
 * The Live dock as a sheet -- v203 (spec v202 §3, §4). Below 1024px the
 * dock never docks: the strip opens this instead, from the right on a
 * tablet and from the bottom on a phone. Focus is trapped (the More
 * sheet's pattern); Escape, the scrim and the dock's Close all close it.
 * `display: contents` on the host: the shell's grid gives it no cell.
 */
@Component({
  selector: 'sb-live-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FocusTrap, LiveDock],
  host: { '(document:keydown.escape)': 'onEscape()' },
  template: `
    @if (open()) {
      <div class="scrim" aria-hidden="true" (click)="closed.emit()"></div>
      <div class="sheet elev-overlay" [class.right]="side() === 'right'" [class.bottom]="side() === 'bottom'"
           [class.sb-sheet-in]="side() === 'bottom'" role="dialog" aria-modal="true" aria-label="Live" sbFocusTrap>
        <sb-live-dock variant="sheet" (close)="closed.emit()" />
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .scrim { position: fixed; inset: 0; z-index: 30; background: var(--scrim-soft); }
    .sheet { position: fixed; z-index: 31; overflow-y: auto; overscroll-behavior: contain; background: var(--surface-overlay); }
    .right { inset: 0 0 0 auto; width: min(360px, calc(100vw - 48px)); border-left: 1px solid var(--border-strong); }
    .bottom {
      inset: auto 0 0 0; max-height: 85dvh; padding-bottom: env(safe-area-inset-bottom);
      border-top: 1px solid var(--border-strong); border-radius: var(--panel-radius) var(--panel-radius) 0 0;
    }
  `,
})
export class LiveSheet {
  readonly open = input(false);
  readonly side = input<'right' | 'bottom'>('right');
  readonly closed = output<void>();

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }
}
```

The scrim, `z-index` pair, `--surface-overlay`, `--scrim-soft`, `elev-overlay` and `sb-sheet-in` are the More sheet's own (`shell/more-sheet.ts`), so the two sheets look and stack alike with no new style.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-strip.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-sheet.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/motion-css.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. `motion-css.spec.ts` runs because the sheet reuses `sb-sheet-in`; if it pins the list of components that use the class, add `shell/live/live-sheet.ts` to that list as a **Moved/added** line and say so in the report.

Complexity: `onEscape` 2; the strip's computeds 1–2 each.

Layout: no screen shows these until V203-8b mounts them; its three-width audit covers the strip and both sheet sides, so record that the visual check is deferred there.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-strip.ts frontend/src/app/shell/live/live-strip.spec.ts \
  frontend/src/app/shell/live/live-sheet.ts frontend/src/app/shell/live/live-sheet.spec.ts
git -C <wt> commit -m "feat(v203): the live strip and the live sheet

sb-live-strip is the tablet/phone line under the tape: scan age, heat,
awaiting count and Live, warning-toned and labelled like the edge tab.
sb-live-sheet holds the dock in its sheet variant, from the right on a
tablet and from the bottom on a phone, focus-trapped, closing on Escape,
a scrim tap or the dock's Close.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-8b: The strip and sheet in the shell, for tablet and phone

**Model:** sonnet — shell wiring over finished components; every edit and test given here.

The second half of ledger task V203-8, split to stay under 20 KB. It runs straight after V203-8, and V203-9 follows it (both edit the shell files).

**Files:**
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts`
- `frontend/src/app/shell/shell.css` (in the ledger row): **no edit needed.** The strip and the sheet style themselves, and the phone block's existing `.tape-strip { display: none; }` already leaves the strip directly under the bar on a phone.

**Interfaces:**
- Consumes: `LiveStrip`, `LiveSheet` (V203-8); `DockState` (`docked()`, `sheetOpen()`, `openSheet()`, `closeSheet()`, V203-3b); the shell members V203-7b added (`dock`, `liveNow`, `dockWarnings`, `heatText`, `awaitingCount`) and the existing `connection` and `isPhone`.
- Produces: the final shell order under the tape: `.tape-strip`, then `sb-live-strip` while `!dock.docked()`; `sb-live-sheet` after the phone tab bar and More sheet, before `sb-command-palette`. V203-9's alarm chip calls `dock.reveal()`, which opens this sheet below 1024 px.

Behaviour pinned here (spec v202 §3 "Live", §4 "Live strip", §8 "Strip and sheet"):
- Below 1024 px (tablet and phone) the strip sits right under the tape and there is no dock column. At 1024 px and wider there is no strip.
- A strip tap opens the sheet through `dock.openSheet()`: from the right on a tablet, from the bottom on a phone (`isPhone()`). Escape, a scrim tap and the dock's `Close` close it through `dock.closeSheet()`. `DockState` also closes it on navigation and when the window widens to docked, and the sheet's `open` input is `dock.sheetOpen() && !dock.docked()`, so a docked window never shows it.
- The strip reads the same `dockWarnings` as the edge tab, so it takes the same warning tone in every condition.

- [ ] **Step 1: Write the failing shell spec**

In `shell/shell.spec.ts`, in `describe('shell live dock (v203)', …)` (V203-7b), add `const phone = signal(false);` under `const narrow = signal(false);`, add `phone.set(false);` under `narrow.set(false);` in its `beforeEach`, and change its `ViewportService` override to `{ isPhone: phone, isNarrow: narrow, viewport: signal('lg') }`. Then add these tests at the end of that describe:

```ts
  it('shows the strip under the tape below 1024 px, and opens the dock from the right on a tablet', async () => {
    narrow.set(true);
    const { fixture, el } = await mount('/trades');
    const strip = el.querySelector<HTMLButtonElement>('.main > .tape-strip + sb-live-strip button.live-strip')!;
    expect(strip).not.toBeNull();
    expect(strip.classList).toContain('warn');                 // heat at 85 % of the cap
    expect(el.querySelector('aside.live-column')).toBeNull();
    strip.click();
    await settle(fixture);
    const dialog = el.querySelector('sb-live-sheet [role=dialog]')!;
    expect(dialog.classList).toContain('right');
    expect(dialog.querySelector('sb-live-dock')).not.toBeNull();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });

  it('opens from the bottom on a phone, and the scrim closes it', async () => {
    narrow.set(true);
    phone.set(true);
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')!.classList).toContain('bottom');
    el.querySelector<HTMLElement>('sb-live-sheet .scrim')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });

  it('closes the sheet on navigation, and when the window widens to docked', async () => {
    narrow.set(true);
    const { fixture, el } = await mount('/trades');
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    await TestBed.inject(Router).navigateByUrl('/risk');
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
    el.querySelector<HTMLButtonElement>('button.live-strip')!.click();
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).not.toBeNull();
    narrow.set(false);
    await settle(fixture);
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
    expect(el.querySelector('sb-live-strip')).toBeNull();
    expect(el.querySelector('aside.live-column > sb-live-dock')).not.toBeNull();   // Risk opens by default
  });

  it('shows no strip and no sheet at 1024 px and wider', async () => {
    const { el } = await mount('/trades');
    expect(el.querySelector('sb-live-strip')).toBeNull();
    expect(el.querySelector('sb-live-sheet [role=dialog]')).toBeNull();
  });
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
```

Expected: FAIL: the four new tests find no `sb-live-strip` and no `sb-live-sheet`; the rest of the file passes.

- [ ] **Step 3: Mount the strip and the sheet**

In `shell/shell.ts`, add beside the other `./live/` imports:

```ts
import { LiveSheet } from './live/live-sheet';
import { LiveStrip } from './live/live-strip';
```

and add `LiveStrip, LiveSheet` to the component's `imports` array.

In `shell/shell.html`, directly after the `<div class="tape-strip">…</div>` block, add:

```html
    <!-- v203 (spec v202 §3, §4): below 1024px the dock never docks. This
         40px line under the tape carries its state and opens it as a sheet. -->
    @if (!dock.docked()) {
      <sb-live-strip [warnings]="dockWarnings()" [heatText]="heatText()" [awaitingCount]="awaitingCount()"
                     [lastSuccess]="connection.botLastSuccess()" [now]="liveNow()" (opened)="dock.openSheet()" />
    }
```

and directly before `<sb-command-palette …>`, after the phone tab bar and More sheet block, add:

```html
  <!-- v203: the Live dock as a sheet below 1024px -- from the right on a
       tablet, from the bottom on a phone. DockState closes it on navigation
       and when the window widens to docked; a docked window never shows it. -->
  <sb-live-sheet [open]="dock.sheetOpen() && !dock.docked()" [side]="isPhone() ? 'bottom' : 'right'"
                 (closed)="dock.closeSheet()" />
```

Placing the sheet before the palette keeps the More sheet's ordering rule (the palette's comment): the palette, opened last, records the right element to return focus to.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/shell.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-strip.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-sheet.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/dock-state.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. The phone-width describe (`isNarrow: signal(true)`) now renders a strip in `.main`. If one of its assertions counts `.main`'s children or pins what follows the tape, update it as **Moved** (name `sb-live-strip` in a comment), never delete it, and list it in the report.

Complexity: no new function; the template's conditions are DockState's.

Layout, at all three widths: build and serve the SPA locally with the `.env` admin credentials (loaded inside the script, never printed), then run `node <wt>/frontend/scripts/layout-audit.mjs --base <local> --widths 390,768,1440`. Report: no horizontal scroll at any width. At 768 the strip is one 40 px line under the tape whose heat words ellipsize rather than wrap, with no dock column; a tap opens the right sheet (360 px, scrim behind), focus moves into it, Tab stays inside it, and Escape, the scrim and Close each close it. At 390 the strip sits under the bar (the tape is hidden there), the sheet rises from the bottom above the tab bar, scrolls on its own and leaves no content hidden behind the tab bar. Touch targets are 44 px (the strip is `sb-hit`, the dock's controls too). At 1440 there is no strip and no sheet. V203-10 adds the audit's own `dock` check for the sheet leaving the viewport.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git -C <wt> commit -m "feat(v203): the live strip and sheet on tablet and phone

Below 1024px the dock never docks: a 40px strip under the tape carries
its state, warning-toned like the edge tab, and opens the dock as a
sheet from the right on a tablet and from the bottom on a phone. It
closes on Escape, the scrim, Close, navigation, and when the window
widens to docked.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

