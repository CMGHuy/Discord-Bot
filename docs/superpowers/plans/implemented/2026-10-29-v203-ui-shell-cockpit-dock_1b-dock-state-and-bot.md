# UI shell cockpit (v203), part 1b: `DockState` and the dock's Bot section

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) (§4 "Bot", "Open/collapsed state", §6, §8 "Dock")
**Index:** [`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md). Its Global Constraints, Parallelisation, task ledger and cross-task contracts apply to every task here.

Part 1's overflow. Part 1 ([`_1-rail-and-live-state.md`](2026-10-29-v203-ui-shell-cockpit-dock_1-rail-and-live-state.md)) holds V203-1, V203-1b, V203-2 and V203-3. This file holds V203-3b and V203-4, which follow V203-3 in that order. The two `b` tasks are splits that keep each task under 20 KB. `<wt>` is the plan's worktree root (absolute). FE paths are relative to `frontend/src/app/` unless they start with `frontend/`.

---

### Task V203-3b: `DockState`: destination, per-page default, persisted toggle, sheet

**Model:** sonnet — one small root service over the V203-3 rules, with router and viewport fakes.

The second half of ledger task V203-3, split to stay under 20 KB. It runs straight after V203-3.

**Files:**
- Create: `frontend/src/app/shell/live/dock-state.ts`, `frontend/src/app/shell/live/dock-state.spec.ts`

**Interfaces:**
- Consumes: `dockDefaultOpen`, `readDockOpen`, `writeDockOpen`, `DOCK_PREF_KEY` (V203-3); `PreferencesStore` (`values()`, `isLoaded()`, `update(mutate)`), `ViewportService.isNarrow` (`ui/breakpoints.ts`), and `destinationFor(url)` from v202 (merged; `null` off the nav model, e.g. `/ui`).
- Produces (index § "DockState", final): `DockState` (root) with `destination: Signal<string | null>`, `docked: Signal<boolean>`, `open: Signal<boolean>`, `sheetOpen: Signal<boolean>`, `toggle()`, `reveal()`, `openSheet()`, `closeSheet()`. V203-7 (dock and edge tab), V203-8 (strip and sheet) and V203-9 (alarm chip `reveal`) inject it.

Behaviour pinned here:
- The destination comes from the router URL after each `NavigationEnd`, through `destinationFor`. A section (`/trades/calendar`), a query and fragment, and an old path that redirects (`/calendar`) all key `/trades`.
- `open` is the per-page default before the preference read and after a failed one (`isLoaded()` true with no stored key). Otherwise it is the stored boolean.
- `toggle()` writes only through `PreferencesStore.update`, never browser storage. Off the nav model it writes nothing.
- `docked` is `!isNarrow()`, so 1024 px and wider. `reveal()` opens a collapsed docked dock (one write, none if it is already open), and below 1024 px it opens the sheet and writes nothing.
- The sheet closes on every `NavigationEnd`, on `closeSheet()`, and when the window widens to docked.

- [ ] **Step 1: Write the failing spec**


Create `shell/live/dock-state.spec.ts`:

```ts
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, Routes, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Preferences } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { ViewportService } from '../../ui/breakpoints';
import { DockState } from './dock-state';
import { DOCK_PREF_KEY } from './live-state';

@Component({ template: '' })
class Blank {}

const ROUTES: Routes = [
  ...['dashboard', 'risk', 'trades', 'trades/calendar', 'insights/analytics', 'ui'].map((path) => ({ path, component: Blank })),
  { path: 'calendar', redirectTo: 'trades/calendar' },
];

describe('DockState (v203)', () => {
  const data = signal<Preferences>({});
  const loaded = signal(false);
  const narrow = signal(false);
  const prefs = { values: () => data(), isLoaded: () => loaded(), update: vi.fn((m: (p: Preferences) => Preferences) => data.set(m(data()))) };
  let dock: DockState;
  const go = (url: string) => TestBed.inject(Router).navigateByUrl(url);

  beforeEach(() => {
    data.set({});
    loaded.set(true);
    narrow.set(false);
    prefs.update.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter(ROUTES),
        { provide: PreferencesStore, useValue: prefs },
        { provide: ViewportService, useValue: { isNarrow: narrow, isPhone: signal(false) } },
      ],
    });
    dock = TestBed.inject(DockState);
  });

  it.each([['/trades/calendar', '/trades'], ['/insights/analytics?tab=tuning#x', '/insights'], ['/calendar', '/trades'], ['/ui', null]])(
    'keys %s by destination %s', async (url, destination) => {
      await go(url);
      expect(dock.destination()).toBe(destination);
    });

  it('opens by default on Dashboard and Risk, and is collapsed elsewhere', async () => {
    await go('/dashboard');
    expect(dock.open()).toBe(true);
    await go('/risk');
    expect(dock.open()).toBe(true);
    await go('/trades');
    expect(dock.open()).toBe(false);
  });

  it('uses the default before preferences load, and after a failed read', async () => {
    data.set({ [DOCK_PREF_KEY]: { '/dashboard': false } });
    loaded.set(false);
    await go('/dashboard');
    expect(dock.open()).toBe(true);
    data.set({});                   // a failed read: loaded, empty
    loaded.set(true);
    expect(dock.open()).toBe(true);
  });

  it('remembers a toggle per destination, through PreferencesStore', async () => {
    await go('/trades/calendar');
    dock.toggle();
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/trades': true });
    await go('/risk');
    expect(dock.open()).toBe(true);
    dock.toggle();
    expect(dock.open()).toBe(false);
    await go('/calendar');          // an old path keys the same destination
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/trades': true, '/risk': false });
  });

  it('writes nothing off the nav model', async () => {
    await go('/ui');
    dock.toggle();
    expect(prefs.update).not.toHaveBeenCalled();
    expect(dock.open()).toBe(false);
  });

  it('docks only at 1024 px and wider', () => {
    expect(dock.docked()).toBe(true);
    narrow.set(true);
    expect(dock.docked()).toBe(false);
  });

  it('reveals by opening a collapsed docked dock, or the sheet below 1024 px', async () => {
    await go('/trades');
    dock.reveal();
    expect(dock.open()).toBe(true);
    dock.reveal();                  // already open: no second write
    expect(prefs.update).toHaveBeenCalledTimes(1);
    expect(dock.sheetOpen()).toBe(false);
    narrow.set(true);
    dock.reveal();
    expect(dock.sheetOpen()).toBe(true);
    expect(prefs.update).toHaveBeenCalledTimes(1);
  });

  it('closes the sheet on navigation, on closeSheet and when the window docks', async () => {
    narrow.set(true);
    await go('/trades');
    dock.openSheet();
    await go('/risk');
    expect(dock.sheetOpen()).toBe(false);
    dock.openSheet();
    dock.closeSheet();
    expect(dock.sheetOpen()).toBe(false);
    dock.openSheet();
    narrow.set(false);
    TestBed.tick();
    expect(dock.sheetOpen()).toBe(false);
  });
});
```


- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/dock-state.spec.ts
```

Expected: FAIL to compile: `./dock-state` does not exist.

- [ ] **Step 3: Write `DockState`**


Create `shell/live/dock-state.ts`:

```ts
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, map } from 'rxjs';

import { PreferencesStore } from '../../stores/preferences.store';
import { ViewportService } from '../../ui/breakpoints';
import { destinationFor } from '../nav';
import { dockDefaultOpen, readDockOpen, writeDockOpen } from './live-state';

/**
 * Where the Live dock is and whether it is open -- v203 (spec v202 §4, D4).
 * Keyed by the destination (`/trades`), never a section or an old path, so
 * a redirect or a tab change cannot fork the choice. Stored only through
 * PreferencesStore (server-side, no browser storage). Before the read, or
 * after a failed one, the per-page default applies. Below 1024 px the dock
 * never docks; it opens as a sheet.
 */
@Injectable({ providedIn: 'root' })
export class DockState {
  private readonly router = inject(Router);
  private readonly preferences = inject(PreferencesStore);
  private readonly viewport = inject(ViewportService);
  private readonly url = toSignal(
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd), map(() => this.router.url)),
    { initialValue: this.router.url },
  );
  private readonly sheet = signal(false);

  readonly destination = computed(() => destinationFor(this.url()));
  readonly docked = computed(() => !this.viewport.isNarrow());
  readonly open = computed(() => {
    const destination = this.destination();
    const fallback = dockDefaultOpen(destination);
    if (destination === null || !this.preferences.isLoaded()) return fallback;
    return readDockOpen(this.preferences.values(), destination, fallback);
  });
  readonly sheetOpen = this.sheet.asReadonly();

  constructor() {
    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd), takeUntilDestroyed())
      .subscribe(() => this.sheet.set(false));
    effect(() => {
      if (this.docked()) untracked(() => this.sheet.set(false));
    });
  }

  /** Flips the current destination's choice; off the nav model it writes nothing. */
  toggle(): void {
    const destination = this.destination();
    if (destination === null) return;
    const next = !this.open();
    this.preferences.update((prefs) => writeDockOpen(prefs, destination, next));
  }

  /** What an alarm or a strip tap asks for: the docked dock open, or the sheet. */
  reveal(): void {
    if (!this.docked()) {
      this.openSheet();
      return;
    }
    if (!this.open()) this.toggle();
  }

  openSheet(): void {
    this.sheet.set(true);
  }

  closeSheet(): void {
    this.sheet.set(false);
  }
}
```


- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/dock-state.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-state.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `open` 3, `reveal` 3, `toggle` 2, and the constructor's effect 2.

Layout: no UI in this task. V203-7 and V203-8 check the docked dock and the sheet at three widths.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/dock-state.ts frontend/src/app/shell/live/dock-state.spec.ts
git -C <wt> commit -m "feat(v203): DockState, the dock's place and open state

Root service: the destination from the router URL (sections and old
paths key their destination), the per-page default until preferences
load or when a read failed, a toggle persisted per destination through
PreferencesStore, docking only at 1024 px and wider, and a sheet that
closes on navigation and when the window docks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-4: Dock Bot section (scanner, last scan, freshness, stream, market, killswitch wording)

**Model:** sonnet — one pure-input component over a table-driven row builder, all wording given here.

**Files:**
- Create: `frontend/src/app/shell/live/live-bot-section.ts`, `frontend/src/app/shell/live/live-bot-section.spec.ts`

**Interfaces:**
- Consumes: `LiveKillswitch` (V203-2), `isStale` and `liveTime` (V203-3), `ConnectionState` (`stores/connection.store.ts`), `scanAge` (`shell/freshness-chip.ts`), `timeInZone` and `ABSENT` (`ui/format.ts`).
- Produces (index ledger, final): `LiveBotSection` (`sb-live-bot`) with inputs `botAlive: boolean | null`, `botHealthy: boolean | null`, `scanRunning: boolean`, `lastSuccess: string | null`, `lastSeen: string | null`, `streamState: ConnectionState`, `marketActive: boolean | null`, `killswitch: LiveKillswitch | null` and `now: Date`. Also exported, for its own spec only: `BotRow { key; label; value; warn }`, `BotSectionInput`, `botRows(input: BotSectionInput): BotRow[]` and `killswitchText(k: LiveKillswitch | null): string`. V203-7's dock feeds it from `ConnectionStore`, `LiveStore.killswitch()` and the shell clock.

The rows, in order (spec v202 §4 "Bot", §6):

| Key | Label | Value | Warning tone |
|---|---|---|---|
| `scanner` | Scanner | `—` before `/system/scan` answers (`botAlive === null`); `Down` (`botAlive === false`); `Failing` (`botHealthy === false`); `Running` while a scan runs; else `Idle` | Down, Failing |
| `last-scan` | Last scan | `liveTime(lastSuccess, now)`: `14:32 · 6m ago` (Berlin), `—` when none | stale (`isStale`), once `botAlive !== null` |
| `freshness` | Data | the freshness chip's words for `lastSuccess ?? lastSeen`: `Scan 6m ago`, or `No scan yet`; `—` before the first answer | the same stale rule |
| `stream` | Event stream | `Connecting`, `Live`, `Polling (stream down)`, `Offline` | degraded, dead |
| `market` | Market | `Open` / `Closed`; `—` before `/health` answers | never |
| `killswitch` | Killswitch | `Active: new alerts paused since 09:31` (Berlin `since`; without one, `Active: new alerts paused`), `Clear`, or the chip's `Killswitch ?` when unknown or unavailable | Active |

No row claims "Running" (or "Clear", or "Open") before its source has answered. "Failing" is a fourth scanner word beyond the spec's running/idle/down, because a bot that is alive but whose ticks fail must not read "Idle". It is the word `sb-connection-status` already shows ("bot failing").

- [ ] **Step 1: Write the failing spec**

Create `shell/live/live-bot-section.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveKillswitch } from '../../api/models';
import { BotSectionInput, LiveBotSection, botRows, killswitchText } from './live-bot-section';

const NOW = new Date('2026-10-29T13:00:00Z');              // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const killswitch = (over: Partial<LiveKillswitch> = {}): LiveKillswitch => ({
  availability: 'ok', as_of: ago(0), reason: null, engaged: false, since: null, detail: null, ...over,
});
const healthy: BotSectionInput = {
  botAlive: true, botHealthy: true, scanRunning: false, lastSuccess: ago(6), lastSeen: ago(1),
  streamState: 'live', marketActive: true, killswitch: killswitch(), now: NOW,
};
const value = (input: BotSectionInput, key: string) => botRows(input).find((row) => row.key === key)!;

describe('botRows (spec v202 §4 Bot, §6)', () => {
  it('lists the six rows in order', () => {
    expect(botRows(healthy).map((row) => [row.label, row.value])).toEqual([
      ['Scanner', 'Idle'], ['Last scan', '13:54 · 6m ago'], ['Data', 'Scan 6m ago'],
      ['Event stream', 'Live'], ['Market', 'Open'], ['Killswitch', 'Clear'],
    ]);
    expect(botRows(healthy).some((row) => row.warn)).toBe(false);
  });

  it('claims nothing before the first answer', () => {
    const cold: BotSectionInput = { ...healthy, botAlive: null, botHealthy: null, lastSuccess: null, lastSeen: null,
      streamState: 'connecting', marketActive: null, killswitch: null };
    expect(botRows(cold).map((row) => row.value)).toEqual(['—', '—', '—', 'Connecting', '—', 'Killswitch ?']);
    expect(botRows(cold).some((row) => row.warn)).toBe(false);
  });

  it.each<[Partial<BotSectionInput>, string, boolean]>([
    [{ botAlive: false }, 'Down', true],
    [{ botHealthy: false }, 'Failing', true],
    [{ botAlive: false, botHealthy: false }, 'Down', true],
    [{ scanRunning: true }, 'Running', false],
    [{ botHealthy: null }, 'Idle', false],
  ])('words the scanner for %o as %s', (change, word, warn) => {
    expect(value({ ...healthy, ...change }, 'scanner')).toMatchObject({ value: word, warn });
  });

  it('warns on a stale last scan and data row, and still says when it was', () => {
    const stale = { ...healthy, lastSuccess: ago(300), lastSeen: ago(300) };
    expect(value(stale, 'last-scan')).toMatchObject({ value: '09:00 · 5h ago', warn: true });
    expect(value(stale, 'freshness')).toMatchObject({ value: 'Scan 5h ago', warn: true });
  });

  it('ages the data row from the last heartbeat when no tick ever succeeded', () => {
    expect(value({ ...healthy, lastSuccess: null, lastSeen: ago(2) }, 'freshness').value).toBe('Scan 2m ago');
    expect(value({ ...healthy, lastSuccess: null, lastSeen: null }, 'freshness')).toMatchObject({ value: 'No scan yet', warn: true });
  });

  it.each([['connecting', 'Connecting', false], ['live', 'Live', false], ['degraded', 'Polling (stream down)', true], ['dead', 'Offline', true]] as const)(
    'words the %s stream as %s', (state, word, warn) => {
      expect(value({ ...healthy, streamState: state }, 'stream')).toMatchObject({ value: word, warn });
    });

  it('reads the market as open or closed', () => {
    expect(value({ ...healthy, marketActive: false }, 'market')).toMatchObject({ value: 'Closed', warn: false });
  });
});

describe('killswitchText', () => {
  it.each<[LiveKillswitch | null, string]>([
    [killswitch({ engaged: true, since: '2026-10-29T08:31:00Z' }), 'Active: new alerts paused since 09:31'],
    [killswitch({ engaged: true, since: null }), 'Active: new alerts paused'],
    [killswitch({ engaged: false }), 'Clear'],
    [killswitch({ engaged: null }), 'Killswitch ?'],
    [killswitch({ availability: 'unavailable', engaged: null, reason: 'db down' }), 'Killswitch ?'],
    [null, 'Killswitch ?'],
  ])('%o reads %s', (state, text) => expect(killswitchText(state)).toBe(text));

  it('warns only while engaged', () => {
    expect(value({ ...healthy, killswitch: killswitch({ engaged: true }) }, 'killswitch').warn).toBe(true);
    expect(value({ ...healthy, killswitch: null }, 'killswitch').warn).toBe(false);
  });
});

describe('LiveBotSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(input: BotSectionInput) {
    const fixture = TestBed.createComponent(LiveBotSection);
    for (const [key, val] of Object.entries(input)) fixture.componentRef.setInput(key, val);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders a titled section of label/value rows, warning rows marked', () => {
    const el = mount({ ...healthy, botAlive: false, killswitch: killswitch({ engaged: true, since: '2026-10-29T08:31:00Z' }) });
    const section = el.querySelector('section[aria-labelledby]')!;
    expect(section.querySelector(`#${section.getAttribute('aria-labelledby')}`)!.textContent!.trim()).toBe('Bot');
    const rows = [...el.querySelectorAll('dl > div.row')];
    expect(rows.map((row) => row.querySelector('dt')!.textContent!.trim()))
      .toEqual(['Scanner', 'Last scan', 'Data', 'Event stream', 'Market', 'Killswitch']);
    expect(rows.filter((row) => row.classList.contains('warn')).map((row) => row.querySelector('dt')!.textContent!.trim()))
      .toEqual(['Scanner', 'Killswitch']);
    expect(rows[5].querySelector('dd')!.textContent!.trim()).toBe('Active: new alerts paused since 09:31');
  });

  it('re-renders when an input changes', () => {
    const fixture = TestBed.createComponent(LiveBotSection);
    for (const [key, val] of Object.entries(healthy)) fixture.componentRef.setInput(key, val);
    fixture.detectChanges();
    fixture.componentRef.setInput('scanRunning', true);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('dl > div.row dd')!.textContent!.trim()).toBe('Running');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-bot-section.spec.ts
```

Expected: FAIL to compile: `./live-bot-section` does not exist.

- [ ] **Step 3: Write the section**

Create `shell/live/live-bot-section.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { LiveKillswitch } from '../../api/models';
import { ConnectionState } from '../../stores/connection.store';
import { ABSENT, timeInZone } from '../../ui/format';
import { scanAge } from '../freshness-chip';
import { isStale, liveTime } from './live-state';

export interface BotRow { key: string; label: string; value: string; warn: boolean; }

export interface BotSectionInput {
  botAlive: boolean | null; botHealthy: boolean | null; scanRunning: boolean;
  lastSuccess: string | null; lastSeen: string | null; streamState: ConnectionState;
  marketActive: boolean | null; killswitch: LiveKillswitch | null; now: Date;
}

const STREAM_WORDS: Readonly<Record<ConnectionState, string>> = {
  connecting: 'Connecting', live: 'Live', degraded: 'Polling (stream down)', dead: 'Offline',
};
const STREAM_DOWN: ReadonlySet<ConnectionState> = new Set(['degraded', 'dead']);

/** Scanner state: never "Running" or "Idle" before /system/scan answers. */
function scannerWord(i: BotSectionInput): string {
  if (i.botAlive === null) return ABSENT;
  if (i.botAlive === false) return 'Down';
  if (i.botHealthy === false) return 'Failing';
  return i.scanRunning ? 'Running' : 'Idle';
}

/** The freshness chip's words, as a row. */
function freshnessWord(i: BotSectionInput): string {
  if (i.botAlive === null) return ABSENT;
  const age = scanAge(i.lastSuccess ?? i.lastSeen, i.now.getTime());
  return age === null ? 'No scan yet' : `Scan ${age}`;
}

function marketWord(active: boolean | null): string {
  if (active === null) return ABSENT;
  return active ? 'Open' : 'Closed';
}

/** The killswitch in plain language (spec v202 §4); unknown reads as the chip does. */
export function killswitchText(k: LiveKillswitch | null): string {
  if (k === null || k.availability === 'unavailable' || k.engaged === null) return 'Killswitch ?';
  if (!k.engaged) return 'Clear';
  return k.since ? `Active: new alerts paused since ${timeInZone(k.since, 'Europe/Berlin')}` : 'Active: new alerts paused';
}

/** The Bot section's rows, in order, each with its words and warning tone. */
export function botRows(i: BotSectionInput): BotRow[] {
  const stale = i.botAlive !== null && isStale(i.lastSuccess, i.now);
  return [
    { key: 'scanner', label: 'Scanner', value: scannerWord(i), warn: i.botAlive === false || i.botHealthy === false },
    { key: 'last-scan', label: 'Last scan', value: liveTime(i.lastSuccess, i.now), warn: stale },
    { key: 'freshness', label: 'Data', value: freshnessWord(i), warn: stale },
    { key: 'stream', label: 'Event stream', value: STREAM_WORDS[i.streamState], warn: STREAM_DOWN.has(i.streamState) },
    { key: 'market', label: 'Market', value: marketWord(i.marketActive), warn: false },
    { key: 'killswitch', label: 'Killswitch', value: killswitchText(i.killswitch), warn: i.killswitch?.engaged === true },
  ];
}

let nextId = 0;

/**
 * The Live dock's Bot section -- v203 (spec v202 §4.1). It absorbs the top
 * bar's freshness and connection chips and the clock. Pure inputs: the
 * dock (V203-7) wires ConnectionStore, LiveStore.killswitch() and the shell
 * clock, so every state is a one-line test. Wording lives in botRows.
 */
@Component({
  selector: 'sb-live-bot',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Bot</h2>
      <dl class="rows">
        @for (row of rows(); track row.key) {
          <div class="row" [class.warn]="row.warn">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </div>
        }
      </dl>
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    .rows { display: flex; flex-direction: column; gap: var(--space-4); margin: 0; }
    .row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0 var(--space-8); min-width: 0; font-size: var(--text-table); }
    dt { color: var(--text-secondary); }
    dd { margin: 0; min-width: 0; color: var(--text); font-variant-numeric: tabular-nums; text-align: right; overflow-wrap: anywhere; }
    .warn dd { color: var(--warn); }
  `,
})
export class LiveBotSection {
  readonly botAlive = input<boolean | null>(null);
  readonly botHealthy = input<boolean | null>(null);
  readonly scanRunning = input(false);
  readonly lastSuccess = input<string | null>(null);
  readonly lastSeen = input<string | null>(null);
  readonly streamState = input.required<ConnectionState>();
  readonly marketActive = input<boolean | null>(null);
  readonly killswitch = input<LiveKillswitch | null>(null);
  readonly now = input.required<Date>();

  protected readonly headingId = `live-bot-${nextId++}`;
  protected readonly rows = computed(() => botRows({
    botAlive: this.botAlive(), botHealthy: this.botHealthy(), scanRunning: this.scanRunning(),
    lastSuccess: this.lastSuccess(), lastSeen: this.lastSeen(), streamState: this.streamState(),
    marketActive: this.marketActive(), killswitch: this.killswitch(), now: this.now(),
  }));
}
```

The warning colour is `--warn`, today's amber token (no new colour, Phase 1). The sheet and the docked dock share this component, so one wrapping rule (a row wraps its value under its label when it cannot fit) serves both 320 px and the phone sheet.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-bot-section.spec.ts
npm --prefix <wt>/frontend test -- --watch=false --include src/app/ui/hit-area.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. The section has no control, so `hit-area.spec.ts` gains no row. It runs only to show that nothing there regressed.

Complexity: `botRows` 3 (two `||`/`&&` plus the optional chain), `scannerWord` 4, `killswitchText` 5, `freshnessWord` 2, `marketWord` 2.

Layout: no screen renders this section until V203-7 mounts it in the docked dock (320 px, desktop) and V203-8 in the sheet (tablet and phone). Their three-width audits cover it, so record in the report that the visual check is deferred to those two tasks. Do not add the section to the `/ui` gallery to check it sooner: that would change a page (Global Constraints).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-bot-section.ts frontend/src/app/shell/live/live-bot-section.spec.ts
git -C <wt> commit -m "feat(v203): the dock's Bot section

Scanner (Running, Idle, Failing or Down), last scan in Berlin time
with its age, data freshness, event stream, market open or closed, and
the killswitch in plain language: \"Active: new alerts paused since
09:31\" or \"Clear\". No row claims a state before its source answered,
and stale, down and disconnected rows take the warning tone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

