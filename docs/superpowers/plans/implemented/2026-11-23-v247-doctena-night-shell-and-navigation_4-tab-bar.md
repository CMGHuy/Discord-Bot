# v247 — Doctena night, plan 3 of 5: Shell and navigation — Part 4: Tab bar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-12" -A 400 <this file>`).

**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) §6 (phone tab bar: labels, active pill, equal width, default tabs, press and hold, storage, `TabBarPrefs`), §8 (`ui.tabbar` edge cases, a viewer never sees System, mouse never long-presses), §9 (tab bar at 320/390/820/1440), §11 (Tab-bar prefs line, long-press host gate).
**Index:** [2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md](2026-11-23-v247-doctena-night-shell-and-navigation_0-index.md) — Goal, Global Constraints, Decisions (3, 6, 7, 8 and 9 above all), Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks: V247-11 (`TabBarPrefs`, the validated per-browser tab list behind its own `TAB_BAR_STORAGE` token), V247-12 (the phone bar and the More sheet read it; equal-width tabs, the accent pill, 600-weight labels; `PHONE_TABS` deleted), V247-13 (press and hold on a tab shows its rail name above it). They run **in id order**, one commit each: V247-12 consumes V247-11's service and V247-13 edits `phone-tab-bar.ts` after V247-12.

Runs after part 1 (V247-2 exported `DEFAULT_PHONE_TAB_PATHS = ['/dashboard', '/watchlist', '/trades', '/calendar']`, `phoneTabsFor(paths, entries = NAV_ENTRIES)`, the interim `PHONE_TABS` constant and `phoneTabPathFor(url, tabs = PHONE_TABS)`; `/calendar` is a destination after Trades) and part 2 (`HINT_HOVER_DELAY_MS = 300`, `Hint.openDelay`, `Hint.openPinned()`, `Hint.placement = 'beside' | 'above'`, `LongPress`/`sbLongPress` with `LONG_PRESS_MS = 500`, the `.sb-long-press` rule in `styles.css`). Part 3's rail uses the same long-press pattern this part puts on the tabs: `<a #link ... sbLongPress (longPress)="hint.openPinned()">` followed by `<sb-hint #hint [anchor]="link" ...>`.

All frontend commands run from the worktree root; `--include` paths are relative to `frontend/`. Session state in specs comes from `patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' })` (viewer: `role: 'viewer'`). Every spec that mounts something reading `TabBarPrefs` provides an in-memory `TAB_BAR_STORAGE`, so no spec writes jsdom's real `localStorage`. jsdom has no `PointerEvent` constructor: pointer events are a `MouseEvent` with `pointerType` and `pointerId` defined on it, as `ui/long-press.spec.ts` does. Timer tests fake only `setTimeout`/`clearTimeout`; the hint's `requestAnimationFrame` stays real. The popover polyfill is installed for every spec by `src/test-setup.ts`.

The three-width check (spec §9): the tab bar shows only below 640px (the shell renders `sb-phone-tab-bar` when `isPhone()`); at 820 and 1440px it is absent and the rail carries navigation. V247-12's CSS keeps five tabs inside a 320px bar (64px each, a 48px pill, the label truncating with an ellipsis). V247-16 checks the bar at 390px (and 320px), and its absence at 820 and 1440px, in a real browser.

---

# Phase 4 — Tab bar

### Task V247-11: `ui.tabbar` validation and the `TAB_BAR_STORAGE` token

**Model:** sonnet — a pure validator and a storage token with every `ui.tabbar` edge case the spec lists pinned; small, but the contract three later tasks read.

**Split:** this task passed 20 KB whole. V247-11 is the pure half (constants, token, `sanitizeTabPaths`, `readTabPaths`); **V247-11b** adds the `TabBarPrefs` service to the same two files. Run V247-11b straight after.

**Files:**
- Create: `frontend/src/app/shell/tab-bar-prefs.ts`
- Test: `frontend/src/app/shell/tab-bar-prefs.spec.ts` (new)

**Interfaces:**
- Consumes (V247-2, `shell/nav.ts`): `DEFAULT_PHONE_TAB_PATHS: readonly string[]` (`['/dashboard', '/watchlist', '/trades', '/calendar']`), `NavEntry`, `navEntriesFor(isAdmin, entries = NAV_ENTRIES)`.
- Produces (V247-11b, V247-14 and V247-15 consume), exported from `frontend/src/app/shell/tab-bar-prefs.ts`:
  - `export const TAB_BAR_PREF_KEY = 'ui.tabbar'`
  - `export const MAX_TAB_PAGES = 4` (pages, Dashboard included; More is extra)
  - `export interface TabBarStorage { get(key: string): string | null; set(key: string, value: string): void }`
  - `export const TAB_BAR_STORAGE: InjectionToken<TabBarStorage>` (`providedIn: 'root'`, factory wraps `localStorage` in try/catch)
  - `export function sanitizeTabPaths(raw: unknown, visible: readonly NavEntry[]): string[]`
  - `export function readTabPaths(storage: TabBarStorage, visible: readonly NavEntry[]): string[]`
  - module-private `HOME_PATH = '/dashboard'` (V247-11b reads it in the same file)

Spec §6 storage: `localStorage['ui.tabbar']` holds a JSON array of nav paths, in try/catch like `ui.theme`. On read it is validated against `navEntriesFor(isAdmin)`. Unknown, duplicate and admin-only-for-a-viewer paths are dropped, Dashboard is forced first, and the list is truncated to 4. If nothing valid remains, or the value is not JSON, the default is used. `/trades/calendar` maps to `/calendar`. Spec §11 lists the cases: default; valid custom; malformed JSON; empty array; more than 4; duplicates; unknown path; admin-only path for a viewer; `/trades/calendar` migration; Dashboard forced first; storage throwing. Decision 3: its own `TAB_BAR_STORAGE` token, mirroring `THEME_STORAGE` in `ui/theme.service.ts`; no shared wrapper.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/shell/tab-bar-prefs.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { DEFAULT_PHONE_TAB_PATHS, navEntriesFor } from './nav';
import { MAX_TAB_PAGES, TAB_BAR_PREF_KEY, TabBarStorage, readTabPaths, sanitizeTabPaths } from './tab-bar-prefs';

const ADMIN = navEntriesFor(true);
const VIEWER = navEntriesFor(false);
const DEFAULT = [...DEFAULT_PHONE_TAB_PATHS];

/** An in-memory ui.tabbar store, as shell.spec.ts does for ui.theme. */
function memoryStorage(map = new Map<string, string>()): TabBarStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}

function throwingStorage(): TabBarStorage {
  return {
    get: () => { throw new Error('SecurityError'); },
    set: () => { throw new Error('QuotaExceededError'); },
  };
}

describe('TAB_BAR_PREF_KEY and MAX_TAB_PAGES', () => {
  it('stores under ui.tabbar and holds four pages', () => {
    expect(TAB_BAR_PREF_KEY).toBe('ui.tabbar');
    expect(MAX_TAB_PAGES).toBe(4);
  });
});

describe('sanitizeTabPaths (v240 §6, §8)', () => {
  it.each([
    ['missing', null],
    ['an object', { paths: ['/risk'] }],
    ['a string', '/risk'],
    ['a number', 4],
    ['an empty array', []],
    ['only unknown paths', ['/nowhere', '/ui']],
    ['only non-strings', [1, null, { path: '/risk' }]],
  ])('gives the default for %s', (_label, raw) => {
    expect(sanitizeTabPaths(raw, ADMIN)).toEqual(DEFAULT);
  });

  it('keeps a valid custom list as it is', () => {
    expect(sanitizeTabPaths(['/dashboard', '/risk', '/insights'], ADMIN)).toEqual(['/dashboard', '/risk', '/insights']);
  });

  it('keeps the Dashboard alone (the editor minimum)', () => {
    expect(sanitizeTabPaths(['/dashboard'], ADMIN)).toEqual(['/dashboard']);
  });

  it('forces the Dashboard first, moving it or adding it', () => {
    expect(sanitizeTabPaths(['/risk', '/dashboard', '/trades'], ADMIN)).toEqual(['/dashboard', '/risk', '/trades']);
    expect(sanitizeTabPaths(['/risk'], ADMIN)).toEqual(['/dashboard', '/risk']);
  });

  it('drops duplicates, unknown paths and non-strings, keeping the first of each', () => {
    expect(sanitizeTabPaths(['/dashboard', '/risk', '/risk', '/nowhere', 7, '/trades'], ADMIN))
      .toEqual(['/dashboard', '/risk', '/trades']);
  });

  it('truncates an over-long list to four pages', () => {
    expect(sanitizeTabPaths(['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights'], ADMIN))
      .toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('counts the forced Dashboard inside the four', () => {
    expect(sanitizeTabPaths(['/watchlist', '/trades', '/calendar', '/risk'], ADMIN))
      .toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('maps a stored /trades/calendar to /calendar, and dedupes it against /calendar', () => {
    expect(sanitizeTabPaths(['/dashboard', '/trades/calendar'], ADMIN)).toEqual(['/dashboard', '/calendar']);
    expect(sanitizeTabPaths(['/dashboard', '/calendar', '/trades/calendar'], ADMIN)).toEqual(['/dashboard', '/calendar']);
  });

  it('drops System for a viewer and keeps it for an admin', () => {
    expect(sanitizeTabPaths(['/dashboard', '/system', '/risk'], VIEWER)).toEqual(['/dashboard', '/risk']);
    expect(sanitizeTabPaths(['/dashboard', '/system', '/risk'], ADMIN)).toEqual(['/dashboard', '/system', '/risk']);
    expect(sanitizeTabPaths(['/system'], VIEWER)).toEqual(DEFAULT);
  });

  it('gives an empty list for an empty model, never a page it cannot open', () => {
    expect(sanitizeTabPaths(['/dashboard'], [])).toEqual([]);
    expect(sanitizeTabPaths(null, [])).toEqual([]);
  });

  it('never mutates the array it is given', () => {
    const raw = ['/risk', '/dashboard', '/risk'];
    sanitizeTabPaths(raw, ADMIN);
    expect(raw).toEqual(['/risk', '/dashboard', '/risk']);
  });
});

describe('readTabPaths', () => {
  it('reads and validates the stored JSON', () => {
    const storage = memoryStorage(new Map([[TAB_BAR_PREF_KEY, '["/risk","/dashboard"]']]));
    expect(readTabPaths(storage, ADMIN)).toEqual(['/dashboard', '/risk']);
  });

  it.each([
    ['no value', undefined],
    ['malformed JSON', '["/risk",'],
    ['an empty string', ''],
    ['an empty array', '[]'],
    ['JSON null', 'null'],
  ])('gives the default for %s', (_label, stored) => {
    const storage = memoryStorage(stored === undefined ? new Map() : new Map([[TAB_BAR_PREF_KEY, stored]]));
    expect(readTabPaths(storage, ADMIN)).toEqual(DEFAULT);
  });

  it('gives the default when the storage throws', () => {
    expect(readTabPaths(throwingStorage(), ADMIN)).toEqual(DEFAULT);
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-prefs.spec.ts`
Expected: FAIL — the build cannot resolve `./tab-bar-prefs`.

- [ ] **Step 3: Write the validator and the token**

Create `frontend/src/app/shell/tab-bar-prefs.ts`:

```ts
import { InjectionToken } from '@angular/core';

import { DEFAULT_PHONE_TAB_PATHS, NavEntry } from './nav';

/**
 * The pages the phone's bottom tab bar holds -- spec v240 §6 (D9).
 *
 * A per-BROWSER preference in localStorage['ui.tabbar'], not PreferencesStore:
 * the partner chose per browser (a phone and a desktop want different bars),
 * as for ui.theme (theme.service.ts's header records why that exception to
 * the plan v21 rule holds). Its own TAB_BAR_STORAGE token, mirroring
 * THEME_STORAGE, so a spec swaps in an in-memory map.
 *
 * The stored value is a JSON array of nav paths, validated on every read
 * against the pages the login may open (navEntriesFor(isAdmin)): unknown,
 * duplicate and admin-only-for-a-viewer paths drop, the Dashboard is forced
 * first, the list is cut to MAX_TAB_PAGES; nothing valid, or not JSON, gives
 * the default. A stored '/trades/calendar' (pre-v247) is '/calendar'.
 */
export const TAB_BAR_PREF_KEY = 'ui.tabbar';

/** Pages on the bar, the Dashboard included; More is always added after them. */
export const MAX_TAB_PAGES = 4;

/** The pinned first tab; the editor offers it no buttons. */
const HOME_PATH = '/dashboard';

/** Paths a stored list may still hold from before a move (v247: Calendar left Trades). */
const RENAMED_TAB_PATHS: Readonly<Record<string, string>> = { '/trades/calendar': '/calendar' };

/** The two calls the service needs; a spec swaps it for an in-memory map. */
export interface TabBarStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

function localStorageTabBar(): TabBarStorage {
  return {
    get(key: string): string | null {
      try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
    },
    set(key: string, value: string): void {
      try { globalThis.localStorage?.setItem(key, value); } catch { /* Private mode or a full quota: the choice lasts this session. */ }
    },
  };
}

export const TAB_BAR_STORAGE = new InjectionToken<TabBarStorage>('TAB_BAR_STORAGE', {
  providedIn: 'root',
  factory: localStorageTabBar,
});

function defaultPaths(known: ReadonlySet<string>): string[] {
  return DEFAULT_PHONE_TAB_PATHS.filter((path) => known.has(path));
}

/** The valid bar for a raw stored value and the pages the login may open. Pure. */
export function sanitizeTabPaths(raw: unknown, visible: readonly NavEntry[]): string[] {
  const known = new Set(visible.map((entry) => entry.path));
  if (!Array.isArray(raw)) return defaultPaths(known);
  const kept = new Set(
    raw
      .filter((item): item is string => typeof item === 'string')
      .map((path) => RENAMED_TAB_PATHS[path] ?? path)
      .filter((path) => known.has(path)),
  );
  if (kept.size === 0) return defaultPaths(known);
  kept.delete(HOME_PATH);
  const home = known.has(HOME_PATH) ? [HOME_PATH] : [];
  return [...home, ...kept].slice(0, MAX_TAB_PAGES);
}

/** The stored value parsed, or null when it is missing, not JSON or unreadable. */
function parseStored(storage: TabBarStorage): unknown {
  try {
    const text = storage.get(TAB_BAR_PREF_KEY);
    return text === null ? null : JSON.parse(text);
  } catch {
    return null;
  }
}

export function readTabPaths(storage: TabBarStorage, visible: readonly NavEntry[]): string[] {
  return sanitizeTabPaths(parseStored(storage), visible);
}
```

`HOME_PATH` is read by `sanitizeTabPaths` here, so it is not an unused local while V247-11b is pending.

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-prefs.spec.ts`
Expected: PASS, 0 failed. A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/tab-bar-prefs.ts frontend/src/app/shell/tab-bar-prefs.spec.ts
git commit -m "feat(v247): ui.tabbar validation and TAB_BAR_STORAGE token" -m "Unknown, duplicate and admin-only paths drop, Dashboard first, four at most, /trades/calendar -> /calendar; not JSON or a throwing storage gives the default. TabBarPrefs follows in V247-11b."
```

### Task V247-11b: `TabBarPrefs` service: the bar's paths, tabs and More list as signals, with edits

**Model:** sonnet — a root signal service over V247-11's validator; the session-timing and partition cases need care, the code is small.

**Files:**
- Modify: `frontend/src/app/shell/tab-bar-prefs.ts` (V247-11's file: the import lines, then the service appended)
- Test: `frontend/src/app/shell/tab-bar-prefs.spec.ts` (V247-11's file: the import block, then a describe appended)

**Interfaces:**
- Consumes (V247-11, same file): `TAB_BAR_PREF_KEY`, `MAX_TAB_PAGES`, `HOME_PATH` (module-private), `TabBarStorage`, `TAB_BAR_STORAGE`, `sanitizeTabPaths`, `readTabPaths`. (V247-2, `shell/nav.ts`): `DEFAULT_PHONE_TAB_PATHS`, `NAV_ENTRIES`, `NavEntry`, `navEntriesFor`, `phoneTabsFor(paths, entries = NAV_ENTRIES): NavEntry[]` (in the order given, the Dashboard labelled Home, unknown paths dropped). Existing: `SessionStore.isAdmin` (`stores/session.store.ts:102`, a computed signal, false until the session is authenticated as admin).
- Produces (V247-12, V247-14 and V247-15 consume): `@Injectable({ providedIn: 'root' }) export class TabBarPrefs` with
  - `paths: Signal<readonly string[]>`: the bar's pages in order, valid for this login
  - `tabs: Signal<readonly NavEntry[]>`: the bar's entries with phone labels (the Dashboard reads Home)
  - `underMore: Signal<readonly NavEntry[]>`: every other page the login may open, rail order, rail labels
  - `canAdd: Signal<boolean>` (`paths().length < MAX_TAB_PAGES`), `isDefault: Signal<boolean>`
  - `set(paths: readonly string[]): void`, `add(path: string): void`, `remove(path: string): void`, `moveUp(path: string): void`, `moveDown(path: string): void`, `reset(): readonly string[]` (returns the paths it replaced, for V247-15's Undo)

Two design points the tests pin:

1. **Validated on every read, against the login.** The service keeps the stored list in a private signal, validated once against the whole model (`NAV_ENTRIES`). `paths` re-validates it against `navEntriesFor(session.isAdmin())` in a `computed`. The session loads over HTTP after the shell boots, so an admin's stored System tab must survive the moment the role is still unknown, and a viewer must never see it. Reading never rewrites storage; only an edit does.
2. **A throwing storage never breaks the shell.** `get` throwing gives the default (V247-11); `set` throwing still changes the bar for this session.

Edit rules (Decision 14, which V247-14's buttons follow): the Dashboard is pinned at index 0, never moved or removed. `moveUp` does nothing at index 1, `moveDown` nothing at the last index. `add` does nothing while the bar is full, or for a path not in `underMore()`. Every edit goes through `set`, which validates like a read.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/tab-bar-prefs.spec.ts`: replace the import block (the first four imports) with:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, NavEntry, navEntriesFor } from './nav';
import {
  MAX_TAB_PAGES, TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs, TabBarStorage, readTabPaths, sanitizeTabPaths,
} from './tab-bar-prefs';
```

Add below `const DEFAULT = ...`:

```ts
const paths = (entries: readonly NavEntry[]) => entries.map((entry) => entry.path);
```

Append at the end of the file:

```ts
describe('TabBarPrefs (v240 §6)', () => {
  function setup(stored?: string, role: 'admin' | 'viewer' = 'admin', storage: TabBarStorage = memoryStorage()) {
    if (stored !== undefined) storage.set(TAB_BAR_PREF_KEY, stored);
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: TAB_BAR_STORAGE, useValue: storage }],
    });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
    return { prefs: TestBed.inject(TabBarPrefs), storage };
  }

  const savedIn = (storage: TabBarStorage) => JSON.parse(storage.get(TAB_BAR_PREF_KEY) ?? 'null');

  it('defaults to Home, Watchlist, Trades and Calendar, with Risk, Insights and System under More', () => {
    const { prefs } = setup();
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(prefs.underMore().map((entry) => entry.label)).toEqual(['Risk', 'Insights', 'System']);
    expect(prefs.isDefault()).toBe(true);
    expect(prefs.canAdd()).toBe(false);
  });

  it('reads a custom list from storage, without rewriting it', () => {
    const { prefs, storage } = setup('["/risk","/dashboard","/risk"]');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home', 'Risk']);
    expect(prefs.isDefault()).toBe(false);
    expect(prefs.canAdd()).toBe(true);
    expect(storage.get(TAB_BAR_PREF_KEY)).toBe('["/risk","/dashboard","/risk"]');
  });

  it('hides a stored System tab from a viewer and shows it once the login is an admin', () => {
    const { prefs } = setup('["/dashboard","/system","/risk"]', 'viewer');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    expect(paths(prefs.underMore())).not.toContain('/system');
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'admin' });
    expect(prefs.paths()).toEqual(['/dashboard', '/system', '/risk']);
  });

  it('keeps an admin System tab through the moment the session is still loading', () => {
    const storage = memoryStorage(new Map([[TAB_BAR_PREF_KEY, '["/dashboard","/system"]']]));
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: TAB_BAR_STORAGE, useValue: storage }],
    });
    const prefs = TestBed.inject(TabBarPrefs);
    expect(prefs.paths()).toEqual(['/dashboard']);
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
    expect(prefs.paths()).toEqual(['/dashboard', '/system']);
  });

  it.each([
    ['admin', undefined],
    ['admin', '["/dashboard","/system"]'],
    ['admin', '["/risk","/insights","/system","/calendar","/trades"]'],
    ['viewer', undefined],
    ['viewer', '["/dashboard","/system","/watchlist"]'],
    ['viewer', 'not json'],
  ] as const)('partitions every page a %s may see between the bar and More (stored %s)', (role, stored) => {
    const { prefs } = setup(stored, role);
    const visible = paths(navEntriesFor(role === 'admin'));
    const bar = [...prefs.paths()];
    const more = paths(prefs.underMore());
    expect(bar.filter((path) => more.includes(path))).toEqual([]);
    expect([...bar, ...more].sort()).toEqual([...visible].sort());
    expect(bar[0]).toBe('/dashboard');
    expect(bar.length).toBeLessThanOrEqual(MAX_TAB_PAGES);
  });

  it('lists More in rail order under rail labels', () => {
    const { prefs } = setup('["/dashboard","/insights"]');
    expect(prefs.underMore().map((entry) => entry.label))
      .toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'System']);
  });

  it('adds a page at the end and saves the list as JSON', () => {
    const { prefs, storage } = setup('["/dashboard","/watchlist"]');
    prefs.add('/risk');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/risk']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/watchlist', '/risk']);
  });

  it('ignores an add while the bar is full, of a page already on it, or of one the login cannot open', () => {
    const { prefs, storage } = setup(undefined, 'viewer');
    prefs.add('/risk');
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(storage.get(TAB_BAR_PREF_KEY)).toBeNull();
    prefs.remove('/calendar');
    prefs.add('/watchlist');
    prefs.add('/system');
    prefs.add('/nowhere');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/trades']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/watchlist', '/trades']);
  });

  it('removes any page but the Dashboard, down to the Dashboard alone', () => {
    const { prefs } = setup('["/dashboard","/risk"]');
    prefs.remove('/dashboard');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    prefs.remove('/risk');
    expect(prefs.paths()).toEqual(['/dashboard']);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home']);
    prefs.remove('/watchlist');
    expect(prefs.paths()).toEqual(['/dashboard']);
  });

  it('moves a page up or down, never past the pinned Dashboard or off the end', () => {
    const { prefs } = setup();
    prefs.moveUp('/trades');
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    prefs.moveUp('/trades');
    prefs.moveUp('/dashboard');
    prefs.moveDown('/dashboard');
    prefs.moveDown('/calendar');
    prefs.moveUp('/nowhere');
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    prefs.moveDown('/trades');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('resets to the default, saves it and hands back the list it replaced', () => {
    const { prefs, storage } = setup('["/dashboard","/risk"]');
    expect(prefs.reset()).toEqual(['/dashboard', '/risk']);
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(prefs.isDefault()).toBe(true);
    expect(savedIn(storage)).toEqual(DEFAULT);
    prefs.set(['/dashboard', '/risk']);
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
  });

  it('validates a set() like a read', () => {
    const { prefs, storage } = setup();
    prefs.set(['/risk', '/trades/calendar', '/risk', '/nowhere']);
    expect(prefs.paths()).toEqual(['/dashboard', '/risk', '/calendar']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/risk', '/calendar']);
  });

  it('survives a throwing storage: the default on read, and edits that last the session', () => {
    const { prefs } = setup(undefined, 'admin', throwingStorage());
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(() => prefs.remove('/watchlist')).not.toThrow();
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/calendar']);
    expect(() => prefs.reset()).not.toThrow();
    expect(prefs.paths()).toEqual(DEFAULT);
  });

  it('never relabels the nav model', () => {
    setup().prefs.tabs();
    expect(NAV_ENTRIES[0].label).toBe('Dashboard');
  });
});
```

`setup(undefined, 'admin', throwingStorage())` skips `storage.set` (no stored value), so the throwing `set` is first reached by `remove`.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-prefs.spec.ts`
Expected: FAIL — the build errors on `TabBarPrefs` (not exported from `./tab-bar-prefs`).

- [ ] **Step 3: Add the service**

`frontend/src/app/shell/tab-bar-prefs.ts`: replace the three import lines at the top with:

```ts
import { Injectable, InjectionToken, Signal, computed, inject, signal } from '@angular/core';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, NavEntry, navEntriesFor, phoneTabsFor } from './nav';
```

Append at the end of the file:

```ts
const samePaths = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((path, index) => path === b[index]);

/**
 * The phone tab bar's pages as signals (spec v240 §6). PhoneTabBar,
 * MoreSheet and phoneTabPathFor read `tabs()`; the tab-bar editor reads
 * `tabs()`/`underMore()` and calls the edit methods. Every edit goes
 * through set(), which validates like a read and saves the result.
 */
@Injectable({ providedIn: 'root' })
export class TabBarPrefs {
  private readonly storage = inject(TAB_BAR_STORAGE);
  private readonly session = inject(SessionStore);

  /** Validated against the whole model, not the login: the session loads after
   *  the shell boots, and an admin's System tab must survive that moment. */
  private readonly stored = signal<readonly string[]>(readTabPaths(this.storage, NAV_ENTRIES));
  private readonly visible = computed(() => navEntriesFor(this.session.isAdmin()));

  /** The bar's pages in order, valid for this login. */
  readonly paths: Signal<readonly string[]> = computed(
    () => sanitizeTabPaths(this.stored(), this.visible()),
    { equal: samePaths },
  );
  /** The bar's entries, with the phone labels (the Dashboard reads Home). */
  readonly tabs: Signal<readonly NavEntry[]> = computed(() => phoneTabsFor(this.paths(), this.visible()));
  /** Every other page the login may open, in rail order, with rail labels. */
  readonly underMore: Signal<readonly NavEntry[]> = computed(() => {
    const onBar = new Set(this.paths());
    return this.visible().filter((entry) => !onBar.has(entry.path));
  });
  readonly canAdd: Signal<boolean> = computed(() => this.paths().length < MAX_TAB_PAGES);
  readonly isDefault: Signal<boolean> = computed(() =>
    samePaths(this.paths(), sanitizeTabPaths(DEFAULT_PHONE_TAB_PATHS, this.visible())));

  /** Validates `paths` like a read, then saves them. A throwing store keeps the change for this session. */
  set(paths: readonly string[]): void {
    const next = sanitizeTabPaths([...paths], this.visible());
    this.stored.set(next);
    try { this.storage.set(TAB_BAR_PREF_KEY, JSON.stringify(next)); } catch { /* A custom store may throw; the bar still changes. */ }
  }

  add(path: string): void {
    if (!this.canAdd() || !this.underMore().some((entry) => entry.path === path)) return;
    this.set([...this.paths(), path]);
  }

  remove(path: string): void {
    if (path === HOME_PATH || !this.paths().includes(path)) return;
    this.set(this.paths().filter((kept) => kept !== path));
  }

  moveUp(path: string): void {
    this.swap(this.paths().indexOf(path), -1);
  }

  moveDown(path: string): void {
    this.swap(this.paths().indexOf(path), 1);
  }

  /** Back to the default; returns the list it replaced, for an Undo. */
  reset(): readonly string[] {
    const before = this.paths();
    this.set(DEFAULT_PHONE_TAB_PATHS);
    return before;
  }

  /** Swaps index with index + step; the pinned Dashboard (0) never moves. */
  private swap(index: number, step: -1 | 1): void {
    const paths = [...this.paths()];
    const target = index + step;
    if (index < 1 || target < 1 || target >= paths.length) return;
    [paths[index], paths[target]] = [paths[target], paths[index]];
    this.set(paths);
  }
}
```

In the file's header comment, add a last paragraph:

```ts
 *
 * TabBarPrefs (below) re-validates on every read and never rewrites storage
 * by reading; only an edit saves.
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/tab-bar-prefs.spec.ts --include src/app/shell/nav.spec.ts`
Expected: PASS, 0 failed (`nav.spec.ts` rides along to show the model did not move). A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/tab-bar-prefs.ts frontend/src/app/shell/tab-bar-prefs.spec.ts
git commit -m "feat(v247): TabBarPrefs -- the phone bar's pages, tabs and More list as signals, with edits" -m "Re-validated against the login on every read (an admin's System tab survives the session load); edits save through set(); a throwing storage keeps edits for the session."
```

### Task V247-12: Phone bar and More sheet read `TabBarPrefs`; `PHONE_TABS` deleted

**Model:** sonnet — swaps a constant for a signal service across three files and their specs; mechanical, but the specs must seed storage before the service's first injection.

**Split:** this task passed 20 KB whole. V247-12 moves the bar and the More sheet onto `TabBarPrefs`; **V247-12b** restyles the bar (equal-width tabs, the accent pill, 600-weight labels) in `phone-tab-bar.ts` and its spec. Run V247-12b straight after.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (the phone-tab block V247-2 wrote: `PHONE_TABS` deleted, `phoneTabPathFor`'s `tabs` required)
- Modify: `frontend/src/app/shell/phone-tab-bar.ts` (imports, doc comment, the `@for`, the class body; the `styles` block is V247-12b's)
- Modify: `frontend/src/app/shell/more-sheet.ts` (imports, `morePageGroups` signature and doc, `MoreSheet.groups`)
- Test: `frontend/src/app/shell/nav.spec.ts`, `frontend/src/app/shell/phone-tab-bar.spec.ts`, `frontend/src/app/shell/more-sheet.spec.ts`

**Interfaces:**
- Consumes (V247-11, V247-11b): `TabBarPrefs` (`tabs: Signal<readonly NavEntry[]>`, `remove(path)`, `add(path)`), `TAB_BAR_STORAGE`, `TAB_BAR_PREF_KEY` from `shell/tab-bar-prefs.ts`. (V247-2): `DEFAULT_PHONE_TAB_PATHS`, `phoneTabsFor`.
- Produces (V247-12b, V247-13 and V247-15 consume):
  - `PHONE_TABS` no longer exists (spec §6: "`PHONE_TABS` stops being a constant").
  - `export function phoneTabPathFor(url: string, tabs: readonly NavEntry[]): string | null` (tabs required)
  - `export function morePageGroups(entries: readonly NavEntry[], tabs: readonly NavEntry[]): MoreGroup[]` (both required; still pure, so its spec needs no injection)
  - `PhoneTabBar`: `protected readonly tabs = inject(TabBarPrefs).tabs` (a signal). Template shape V247-13 edits: `@for (tab of tabs(); track tab.path) { <a class="tab" ...>…</a> }`, then `<button class="tab more">`.
  - `MoreSheet.groups = computed(() => morePageGroups(navEntriesFor(isAdmin), prefs.tabs()))`.
  - The `phone-tab-bar.spec.ts` describe provides an in-memory `TAB_BAR_STORAGE` over a `stored: Map<string, string>` and has a `labels(el)` helper (V247-12b and V247-13 append to it).

Spec §6: "A `TabBarPrefs` service exposes a `tabs()` signal that `PhoneTabBar`, `MoreSheet` and `phoneTabPathFor` read. `phoneTabPathFor` keeps lighting the right tab for detail routes." `TabBarPrefs` reads storage on its first injection, so a spec seeds `stored` before it mounts the component.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/nav.spec.ts`. In the import block V247-2 wrote, delete `PHONE_TABS, ` and add below the block:

```ts
import * as navModule from './nav';
```

In `describe('phone tabs (v240 §6)')`, replace the first test (`'defaults to Home, Watchlist, Trades and Calendar, ...'`) with:

```ts
  it('defaults to Home, Watchlist, Trades and Calendar, the rail order, each with its destination icon', () => {
    const tabs = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS);
    expect(DEFAULT_PHONE_TAB_PATHS).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
    expect(paths(tabs)).toEqual([...DEFAULT_PHONE_TAB_PATHS]);
    expect(tabs.map((tab) => tab.label)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    for (const tab of tabs) {
      expect(NAV_ENTRIES.find((entry) => entry.path === tab.path)?.icon).toBe(tab.icon);
    }
  });

  it('exports no PHONE_TABS constant: the bar is TabBarPrefs.tabs() (v240 §6)', () => {
    expect('PHONE_TABS' in navModule).toBe(false);
  });
```

Replace the whole `describe('phoneTabPathFor', ...)` with:

```ts
describe('phoneTabPathFor', () => {
  const DEFAULT_TABS = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS);

  it.each([
    ['/calendar/2026-10-01', '/calendar'],
    ['/calendar?month=2026-11', '/calendar'],
    ['/trades', '/trades'],
    ['/trades/812', '/trades'],
    ['/plans/5', '/trades'],
    ['/dashboard', '/dashboard'],
    ['/risk', '/risk'],
    ['/system/versions', '/system'],
    ['/ui', null],
  ])('lights %s on the %j tab of the default bar', (url, expected) => {
    expect(phoneTabPathFor(url, DEFAULT_TABS)).toBe(expected);
  });

  it('reads the tab list it is given', () => {
    expect(phoneTabPathFor('/insights/research', phoneTabsFor(['/dashboard']))).toBe('/insights');
    expect(phoneTabPathFor('/calendar/2026-10-01', phoneTabsFor(['/dashboard', '/calendar']))).toBe('/calendar');
    expect(phoneTabPathFor('/plans/7', phoneTabsFor(['/dashboard', '/risk', '/trades']))).toBe('/trades');
  });

  it('still names the destination for an empty bar, so the caller lights More', () => {
    expect(phoneTabPathFor('/risk', [])).toBe('/risk');
    expect(phoneTabPathFor('/ui', [])).toBeNull();
  });
});
```

`frontend/src/app/shell/more-sheet.spec.ts`. Replace the imports with:

```ts
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MoreSheet, morePageGroups } from './more-sheet';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, phoneTabsFor } from './nav';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs } from './tab-bar-prefs';
import { SessionStore } from '../stores/session.store';

const DEFAULT_TABS = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS);
```

In `describe('morePageGroups (v202 §3)')`, change the two `morePageGroups()` calls (the rail-order test and `'lists no destination the tab bar holds'`) to `morePageGroups(NAV_ENTRIES, DEFAULT_TABS)`, and add after `'keeps every destination when no tab is given ...'`:

```ts
  it('follows the tab list it is given', () => {
    const tabs = phoneTabsFor(['/dashboard', '/risk']);
    expect(morePageGroups(NAV_ENTRIES, tabs).map((group) => group.label))
      .toEqual(['Watchlist', 'Trades', 'Calendar', 'Insights', 'System']);
  });
```

In `describe('MoreSheet (v195 Phase 3)')`, replace the `let` lines and `beforeEach` (from `let fixture: ComponentFixture<MoreSheet>;` through the end of `beforeEach`) with:

```ts
  let fixture: ComponentFixture<MoreSheet>;
  let el: HTMLElement;
  let closed: number;
  let searched: number;
  let stored: Map<string, string>;

  /** An in-memory ui.tabbar, read through the closure so a test may reseed it. */
  const storageProvider = () => ({
    provide: TAB_BAR_STORAGE,
    useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) },
  });

  function configure(role: 'admin' | 'viewer'): void {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([{ path: '**', component: Blank }]), storageProvider()],
    });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
  }

  function create(): void {
    fixture = TestBed.createComponent(MoreSheet);
    el = fixture.nativeElement as HTMLElement;
    closed = 0;
    searched = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    fixture.componentInstance.searchRequested.subscribe(() => (searched += 1));
    fixture.detectChanges();
  }

  beforeEach(() => {
    stored = new Map<string, string>();
    configure('admin');
    create();
  });
```

Append inside that describe:

```ts
  const groupLabels = () => [...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim());

  it('lists what the partner took off the bar, and drops what they put on it (v240 §6)', () => {
    const prefs = TestBed.inject(TabBarPrefs);
    prefs.remove('/watchlist');
    prefs.add('/risk');
    open();
    expect(groupLabels()).toEqual(['Watchlist', 'Insights', 'System']);
    prefs.remove('/risk');
    fixture.detectChanges();
    expect(groupLabels()).toEqual(['Watchlist', 'Risk', 'Insights', 'System']);
  });

  it('reads the stored bar, ignoring a System tab for a viewer', () => {
    TestBed.resetTestingModule();
    stored = new Map([[TAB_BAR_PREF_KEY, '["/dashboard","/system","/insights"]']]);
    configure('viewer');
    create();
    open();
    expect(groupLabels()).toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk']);
  });
```

The existing `'lists only Risk and Insights for a viewer (v207)'` patches the role after `create()`; it still passes, because `TabBarPrefs` re-validates on every read.

`frontend/src/app/shell/phone-tab-bar.spec.ts`. Replace the imports with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS } from './nav';
import { PhoneTabBar } from './phone-tab-bar';
import { TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs } from './tab-bar-prefs';
```

Replace the top of the describe (from `describe('PhoneTabBar (v195 Phase 3)', () => {` through the end of its `beforeEach`) with:

```ts
describe('PhoneTabBar (v195 Phase 3, v240 §6)', () => {
  let stored: Map<string, string>;

  beforeEach(() => {
    stored = new Map<string, string>();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: '**', component: Blank }]),
        { provide: TAB_BAR_STORAGE, useValue: { get: (key: string) => stored.get(key) ?? null, set: (key: string, value: string) => void stored.set(key, value) } },
      ],
    });
  });

  const labels = (el: HTMLElement) => [...el.querySelectorAll('.tab .tab-label')].map((n) => n.textContent!.trim());
  const moreLit = (el: HTMLElement) => el.querySelector('button.tab.more')!.classList.contains('active');
```

Append inside the describe:

```ts
  it('holds the pages stored for this browser, in their order, then More', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/risk"]');
    const { el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'Risk', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href'))).toEqual(['/dashboard', '/risk']);
  });

  it('falls back to the default bar when the stored value is junk', async () => {
    stored.set(TAB_BAR_PREF_KEY, '{not json');
    const { el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar', 'More']);
    expect([...el.querySelectorAll('a.tab')].map((a) => a.getAttribute('href'))).toEqual([...DEFAULT_PHONE_TAB_PATHS]);
  });

  it('never shows a stored System tab to a viewer, and shows it to an admin', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/system"]');
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'viewer', role: 'viewer' });
    const { fixture, el } = await mount('/dashboard');
    expect(labels(el)).toEqual(['Home', 'More']);
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'admin' });
    fixture.detectChanges();
    expect(labels(el)).toEqual(['Home', 'System', 'More']);
  });

  it('follows an edit at once, and lights a page once the bar holds it', async () => {
    const { fixture, el } = await mount('/risk');
    expect(current(el)).toEqual([]);
    expect(moreLit(el)).toBe(true);
    const prefs = TestBed.inject(TabBarPrefs);
    prefs.remove('/watchlist');
    prefs.add('/risk');
    fixture.detectChanges();
    expect(labels(el)).toEqual(['Home', 'Trades', 'Calendar', 'Risk', 'More']);
    expect(current(el)).toEqual(['Risk']);
    expect(moreLit(el)).toBe(false);
  });

  it('lights More for a calendar day once Calendar left the bar', async () => {
    stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/trades"]');
    const { el } = await mount('/calendar/2026-10-01');
    expect(current(el)).toEqual([]);
    expect(moreLit(el)).toBe(true);
  });
```

The existing tests stay. `'keeps every glyph out of the accessible name'` and `'draws each tab icon at 24px'` still count 5 icons: the default bar holds four tabs plus More. The `readFileSync`/`join` imports stay for the existing `'sits on the bottom edge ...'` test.

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/more-sheet.spec.ts`
Expected: FAIL. `'PHONE_TABS' in navModule` is true; the bar ignores the stored list and edits; the More sheet ignores `TabBarPrefs`.

- [ ] **Step 3: Delete `PHONE_TABS` and require `tabs`** in `frontend/src/app/shell/nav.ts`.

Delete the `PHONE_TABS` constant and its doc (`/** The default bar. V247-12 replaces it with TabBarPrefs.tabs(). */` and the line after it). Replace `phoneTabPathFor` and its doc with:

```ts
/** The phone tab a URL lights, given the bar's tabs (TabBarPrefs.tabs()):
 *  its section's own tab when a tab holds that section, else its
 *  destination's (a calendar day lights Calendar, a plan lights Trades).
 *  A destination the bar does not hold is still returned, so the caller
 *  lights More; null off the nav. */
export function phoneTabPathFor(url: string, tabs: readonly NavEntry[]): string | null {
  const found = navEntryFor(url);
  if (!found) return null;
  const sectionTab = tabs.find((tab) => tab.path === found.section?.path);
  return sectionTab?.path ?? found.entry.path;
}
```

Replace the `DEFAULT_PHONE_TAB_PATHS` doc with:

```ts
/** The phone bottom bar's default pages, in rail order (v240 §6); TabBarPrefs
 *  falls back to them and PhoneTabBar adds More last. Risk, Insights and
 *  System live in the More sheet until the partner moves them. */
```

- [ ] **Step 4: Point the More sheet at `TabBarPrefs`** in `frontend/src/app/shell/more-sheet.ts`.

Replace the nav import with:

```ts
import { NavEntry, navEntriesFor } from './nav';
import { TabBarPrefs } from './tab-bar-prefs';
```

Replace the `morePageGroups` doc and signature (lines 17-26) with:

```ts
/**
 * The destinations the phone's tab bar does not hold, in rail order (v202
 * §3), each with its sections as links; a single page links to itself.
 * With the default bar: Risk, Insights (Analytics, Research, Reports,
 * Guide) and, for the admin only, System (Health, Versions). The bar is
 * the partner's choice (v240 §6), so the caller passes it: MoreSheet hands
 * in TabBarPrefs.tabs(). Pure.
 */
export function morePageGroups(entries: readonly NavEntry[], tabs: readonly NavEntry[]): MoreGroup[] {
```

In `MoreSheet`, replace the `groups` line with:

```ts
  private readonly prefs = inject(TabBarPrefs);
  protected readonly groups = computed(() =>
    morePageGroups(navEntriesFor(this.session.isAdmin()), this.prefs.tabs()));
```

In the component doc, replace `every destination the tab bar does not hold` with `every destination the tab bar does not hold (TabBarPrefs, v240 §6)`.

- [ ] **Step 5: Read the bar from `TabBarPrefs`** in `frontend/src/app/shell/phone-tab-bar.ts`.

Replace the nav import with:

```ts
import { phoneTabPathFor } from './nav';
import { TabBarPrefs } from './tab-bar-prefs';
```

Replace the doc comment's first two paragraphs (from `The phone's bottom tab bar -- v195 Phase 3.` through `and a page the bar does not hold lights More.`) with:

```ts
 * The phone's bottom tab bar -- v195 Phase 3, v240 §6.
 *
 * The pages come from TabBarPrefs: by default Home (the Dashboard) ·
 * Watchlist · Trades · Calendar, then More; the partner may keep 1 to 4
 * pages, the Dashboard always first. The current tab comes from the nav
 * model, not RouterLinkActive, so a plan detail lights Trades and a page
 * the bar does not hold lights More.
```

In the template, `@for (tab of tabs; track tab.path) {` becomes `@for (tab of tabs(); track tab.path) {`. In the class, replace `protected readonly tabs = PHONE_TABS;` with:

```ts
  protected readonly tabs = inject(TabBarPrefs).tabs;
```

and the two computeds with:

```ts
  /** The tab the current page belongs to; null off the nav (the /ui gallery). */
  protected readonly activePath = computed(() => phoneTabPathFor(this.url(), this.tabs()));

  protected readonly moreActive = computed(() => {
    if (this.moreOpen()) return true;
    const path = this.activePath();
    return path !== null && !this.tabs().some((tab) => tab.path === path);
  });
```

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/nav.spec.ts --include src/app/shell/phone-tab-bar.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/tab-bar-prefs.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, 0 failed. `shell.spec.ts` proves the shell's phone describes (the More tab, the sheet) still mount with the real `TabBarPrefs` over jsdom's empty `localStorage`. A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts frontend/src/app/shell/more-sheet.ts frontend/src/app/shell/more-sheet.spec.ts
git commit -m "feat(v247): phone tab bar and More sheet read TabBarPrefs; PHONE_TABS deleted" -m "phoneTabPathFor and morePageGroups take the tabs explicitly. The bar's restyle follows in V247-12b."
```

### Task V247-12b: Phone bar restyle: equal-width tabs, the accent-soft pill, 600-weight labels

**Model:** haiku — one component's `styles` block and source-scan pins, fully specified below; no logic.

**Files:**
- Modify: `frontend/src/app/shell/phone-tab-bar.ts` (the `styles` block and one doc-comment paragraph)
- Test: `frontend/src/app/shell/phone-tab-bar.spec.ts` (helpers and three tests appended to the describe V247-12 rewrote)

**Interfaces:**
- Consumes (V247-12): `PhoneTabBar` reading `TabBarPrefs.tabs()`; the spec's describe `'PhoneTabBar (v195 Phase 3, v240 §6)'` and its `readFileSync`/`join` imports.
- Produces: the CSS class contract V247-13 and V247-16 rely on. `.tabs` is a grid with `grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr)`. Each `.tab` cell has `min-width: 0`. `.glyph` is the 48×28 pill with `border-radius: var(--pill-radius)`, and `.tab.active .glyph` fills it with `--accent-soft` behind an `--accent` icon. `.tab-label` is `var(--text-micro)` at weight 600 and truncates with an ellipsis.

Spec §6: "Labels always shown, under each icon, 11px, weight 600. The active tab gets the `--accent-soft` pill with the icon in `--accent` (not mint, §1) and `aria-current="page"`... Tabs share the bar's width equally, whether it holds 2 or 5, and the 5-tab bar is checked at 320px." Decision 8 (accepted): the label keeps `var(--text-micro)` (the repo's 12px readability floor) and gains weight 600, and no 11px literal or token is added. Gates: nav and active rules never read `--pos`/`--neg` (`ui/money-colour.spec.ts` `NAV_FILES` lists `phone-tab-bar.ts`), there is no hex in a `.ts` file and no px radius literal (`ui/primitives.spec.ts`), and no text rule reads `--text-faint`. Five tabs at 320px are 64px each, which holds the 48px pill and the `--space-4` side padding; a label too long for its column truncates instead of widening it.

The 2px accent top border on the active tab goes. The pill and the label stepping from `--text-muted` to `--text` carry the state, so it is never colour alone.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/phone-tab-bar.spec.ts`: below the `moreLit` helper V247-12 added, add:

```ts
  const styles = () => readFileSync(join(process.cwd(), 'src/app/shell/phone-tab-bar.ts'), 'utf8');
  /** One CSS rule of the component's styles block, by its exact selector. */
  const rule = (selector: string) =>
    styles().match(new RegExp(`^\\s*${selector.replace(/[.*]/g, '\\$&')} \\{[^}]*\\}`, 'm'))?.[0] ?? '';
```

Append inside the describe:

```ts
  it('shares the width equally between however many tabs it holds (v240 §6)', () => {
    const bar = rule('.tabs');
    expect(bar).toContain('grid-auto-flow: column;');
    expect(bar).toContain('grid-auto-columns: minmax(0, 1fr);');
    expect(styles()).not.toMatch(/repeat\(5/);
    expect(rule('.tab')).toContain('min-width: 0;');
  });

  it('marks the active tab with the accent-soft pill and an accent icon, not a top border (v240 §6)', () => {
    const pill = rule('.glyph');
    expect(pill).toContain('border-radius: var(--pill-radius);');
    expect(pill).toContain('width: 48px;');
    expect(pill).toContain('height: 28px;');
    const active = rule('.tab.active .glyph');
    expect(active).toContain('background: var(--accent-soft);');
    expect(active).toContain('color: var(--accent);');
    expect(rule('.tab.active')).toContain('color: var(--text);');
    expect(styles()).not.toMatch(/border-top: 2px|border-top-color/);
  });

  it('labels every tab at the 12px micro size, weight 600, truncating rather than widening (Decision 8)', () => {
    const label = rule('.tab-label');
    for (const declaration of ['font-size: var(--text-micro);', 'font-weight: 600;', 'overflow: hidden;',
      'text-overflow: ellipsis;', 'white-space: nowrap;', 'max-width: 100%;']) {
      expect(label, declaration).toContain(declaration);
    }
    expect(styles()).not.toMatch(/11px|--text-faint/);
  });

  it('keeps the pill on the More button while the sheet is open', async () => {
    const { fixture, el } = await mount('/dashboard');
    fixture.componentRef.setInput('moreOpen', true);
    fixture.detectChanges();
    const more = el.querySelector('button.tab.more')!;
    expect(more.classList).toContain('active');
    expect(more.querySelector('.glyph')).not.toBeNull();
  });
```

`rule('.tab')` matches only the rule whose selector is exactly `.tab` (the pattern needs ` {` straight after it), never `.tab.active` or `.tab-label`.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/phone-tab-bar.spec.ts`
Expected: FAIL. The CSS pins find `repeat(5, 1fr)`, the 2px top border, a `.glyph` rule without the pill, and a `.tab-label` with no rule of its own. The More-button test passes already, which is expected: it pins that the pill selector also reaches More.

- [ ] **Step 3: Restyle the bar** in `frontend/src/app/shell/phone-tab-bar.ts`.

In the doc comment, after the paragraph V247-12 wrote (ending `... the bar does not hold lights More.`), add:

```ts
 *
 * The tabs share the width equally, 2 to 5 of them. The active tab shows
 * the --accent-soft pill behind an --accent icon, and its label steps to
 * full text: never colour alone.
```

Replace the whole `styles` block with:

```ts
  styles: `
    :host {
      position: fixed;
      inset: auto 0 0 0;
      z-index: 8;
      display: block;
    }
    /* One equal column per tab, 2 to 5 of them; five fit a 320px phone. */
    .tabs {
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(0, 1fr);
      box-sizing: border-box;
      height: calc(56px + env(safe-area-inset-bottom));
      padding-bottom: env(safe-area-inset-bottom);
      background: var(--surface);
      border-top: 1px solid var(--border);
    }
    .tab {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      min-width: 0;
      min-height: var(--hit-min);
      margin: 0;
      padding: 0 var(--space-4);
      border: 0;
      background: none;
      color: var(--text-muted);
      font: inherit;
      text-decoration: none;
      cursor: pointer;
      transition: color var(--transition);
    }
    .tab.active { color: var(--text); }
    /* The pill the active tab fills: --accent-soft behind an --accent icon (v240 §6). */
    .glyph {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 48px;
      height: 28px;
      border-radius: var(--pill-radius);
      line-height: 0;
      transition: background var(--transition), color var(--transition);
    }
    .tab.active .glyph { background: var(--accent-soft); color: var(--accent); }
    /* The 12px floor (--text-micro, Decision 8) at weight 600; a long label
       truncates instead of widening its column. */
    .tab-label {
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--text-micro);
      font-weight: 600;
    }
  `,
```

`sb-icon` draws in `currentColor`, so `.tab.active .glyph { color: var(--accent) }` colours the icon while the label keeps `--text` from `.tab.active`. The More button is a `.tab` with a `.glyph` too, so it takes the same pill while the sheet is open or the page is not on the bar. The `56px` height and `z-index: 8` the existing `'sits on the bottom edge ...'` test pins are unchanged.

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/phone-tab-bar.spec.ts --include src/app/ui/money-colour.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/type-gates.spec.ts`
Expected: PASS, 0 failed. The three gate specs prove the new rules read no `--pos`/`--neg`, carry no hex or px radius, and break no type rule. A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts
git commit -m "feat(v247): phone tab bar -- equal-width tabs, accent-soft pill with accent icon, 600-weight labels" -m "Labels stay at the --text-micro 12px floor (Decision 8) and truncate; the 2px top border goes."
```

### Task V247-13: Tab press-and-hold shows the tab's name above it

**Model:** sonnet — wires part 2's `Hint` and `sbLongPress` contracts into the tab bar under fake timers, with geometry stubs for the above placement.

**Files:**
- Modify: `frontend/src/app/shell/phone-tab-bar.ts` (imports, the `imports` array, the `@for` block, a doc paragraph, two class members)
- Test: `frontend/src/app/shell/phone-tab-bar.spec.ts` (imports, helpers and a nested describe appended)

**Interfaces:**
- Consumes (V247-5, V247-6, `ui/hint.ts`): `Hint` (selector `sb-hint`; anchor mode via `[anchor]`; `openDelay` input; `placement = input<'beside' | 'above'>('beside')`; `openPinned(): void`, which opens and pins at once, closes on the next `pointerdown` anywhere or Escape anywhere, and is not closed by hover or focus ending; one open hint app-wide), `HINT_HOVER_DELAY_MS = 300`. The popover is `[role="tooltip"]`, its `id` is in the anchor's `aria-describedby`, and an open one carries `POPOVER_OPEN_ATTR` (`testing/popover-polyfill.ts`).
- Consumes (V247-7, `ui/long-press.ts`): `LongPress` (selector `[sbLongPress]`, output `longPress`, host class `sb-long-press`, `touch`/`pen` only, swallows the click after a fired press), `LONG_PRESS_MS = 500`.
- Consumes (V247-12, V247-12b): the `@for (tab of tabs(); track tab.path)` template and `TabBarPrefs`; the spec's in-memory `stored` map, `mount`, `labels`, `current` helpers.
- Produces: `PhoneTabBar` tab hints. Each `<a class="tab">` is `#link` with `sbLongPress (longPress)="hint.openPinned()"`, followed by `<sb-hint #hint [anchor]="link" [text]="railLabelOf(tab.path)" placement="above" [openDelay]="hintDelay" />`. The text is the destination's rail label (Decision 9: the Home tab's tooltip reads "Dashboard"). The More button gets no hint and no long-press.

Spec §6: "a touch held for 500ms without moving more than 10px opens that tab's tooltip above it, using the same `sb-hint` as the rail, and navigates nowhere. The tooltip stays until the next touch anywhere, or Escape (no timed close...). The click that follows a long-press is swallowed." Spec §8: a mouse never triggers it; hover covers a mouse (after `HINT_HOVER_DELAY_MS`, Decision 6). Spec §11: long-press host links carry `-webkit-touch-callout: none` (the `.sb-long-press` rule V247-7 put in `styles.css`). The anchor-mode `sb-hint` host is `display: contents` and its `.pop` is `position: fixed`, so it adds no grid column to the bar: V247-12b's equal-width grid still counts only the tabs.

- [ ] **Step 1: Write the failing tests**

`frontend/src/app/shell/phone-tab-bar.spec.ts`. Change the vitest import to:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
```

and add below the `TabBarPrefs` import:

```ts
import { POPOVER_OPEN_ATTR } from '../testing/popover-polyfill';
import { HINT_HOVER_DELAY_MS } from '../ui/hint';
import { LONG_PRESS_MS } from '../ui/long-press';
```

Append a nested describe at the end of `describe('PhoneTabBar (v195 Phase 3, v240 §6)')`:

```ts
  describe('press and hold (v240 §6, Decision 9)', () => {
    const root = document.documentElement;

    afterEach(() => {
      // Undo the viewport stub: the own properties shadow Element.prototype's getters.
      delete (root as unknown as Record<string, unknown>)['clientWidth'];
      delete (root as unknown as Record<string, unknown>)['clientHeight'];
    });

    const tabLink = (el: HTMLElement, path: string) => el.querySelector<HTMLAnchorElement>(`a.tab[href="${path}"]`)!;
    /** The role="tooltip" popover the tab's aria-describedby points at (its sb-hint). */
    const tooltipOf = (el: HTMLElement, link: Element) =>
      el.querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
    const isOpen = (tooltip: HTMLElement) => tooltip.hasAttribute(POPOVER_OPEN_ATTR);
    async function settle(fixture: { detectChanges(): void; whenStable(): Promise<unknown> }) {
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    }

    /** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
     *  is what sbLongPress reads (ui/long-press.spec.ts does the same). */
    function pointer(type: string, pointerType = 'touch'): MouseEvent {
      const event = new MouseEvent(type, { bubbles: true, cancelable: true, clientX: 100, clientY: 810 });
      Object.defineProperty(event, 'pointerType', { value: pointerType });
      Object.defineProperty(event, 'pointerId', { value: 1 });
      return event;
    }

    /** Holds a pointer on the tab for LONG_PRESS_MS and lifts it. Only
     *  setTimeout is faked: the hint's requestAnimationFrame stays real. */
    async function hold(fixture: Parameters<typeof settle>[0], link: Element, pointerType = 'touch') {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      try {
        link.dispatchEvent(pointer('pointerdown', pointerType));
        vi.advanceTimersByTime(LONG_PRESS_MS);
        link.dispatchEvent(pointer('pointerup', pointerType));
      } finally {
        vi.useRealTimers();
      }
      await settle(fixture);
    }

    const tap = () => new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });

    it('gives every tab one tooltip naming its page as the rail does, and More none', async () => {
      const { el } = await mount('/dashboard');
      const links = [...el.querySelectorAll('a.tab')];
      expect(links).toHaveLength(4);
      expect(links.map((link) => tooltipOf(el, link).textContent!.trim()))
        .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Calendar']);
      for (const link of links) {
        expect(tooltipOf(el, link).getAttribute('role')).toBe('tooltip');
        expect(isOpen(tooltipOf(el, link))).toBe(false);
      }
      const more = el.querySelector('button.tab.more')!;
      expect(more.hasAttribute('aria-describedby')).toBe(false);
      expect(el.querySelectorAll('[role="tooltip"]')).toHaveLength(4);
    });

    it('names the tabs of a custom bar too', async () => {
      stored.set(TAB_BAR_PREF_KEY, '["/dashboard","/risk","/insights"]');
      const { el } = await mount('/dashboard');
      expect([...el.querySelectorAll('a.tab')].map((link) => tooltipOf(el, link).textContent!.trim()))
        .toEqual(['Dashboard', 'Risk', 'Insights']);
    });

    it('makes every tab a long-press host and the More button not one', async () => {
      const { el } = await mount('/dashboard');
      for (const link of el.querySelectorAll('a.tab')) expect(link.classList).toContain('sb-long-press');
      expect(el.querySelector('button.tab.more')!.classList).not.toContain('sb-long-press');
    });

    it('opens the tab tooltip on a 500ms touch hold and not a moment before', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/calendar');
      const tooltip = tooltipOf(el, link);
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      try {
        link.dispatchEvent(pointer('pointerdown'));
        vi.advanceTimersByTime(LONG_PRESS_MS - 1);
        fixture.detectChanges();
        expect(isOpen(tooltip)).toBe(false);
        vi.advanceTimersByTime(1);
      } finally {
        vi.useRealTimers();
      }
      await settle(fixture);
      expect(isOpen(tooltip)).toBe(true);
      expect(tooltip.textContent!.trim()).toBe('Calendar');
    });

    it('keeps the held-open tooltip after the finger lifts, and swallows the click so it navigates nowhere', async () => {
      const { fixture, el } = await mount('/dashboard');
      const router = TestBed.inject(Router);
      const link = tabLink(el, '/trades');
      await hold(fixture, link);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
      link.dispatchEvent(tap());
      await settle(fixture);
      expect(router.url).toBe('/dashboard');
      expect(isOpen(tooltipOf(el, link))).toBe(true);
    });

    it('closes the held-open tooltip on the next touch anywhere, and on Escape', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
      await hold(fixture, link);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
      document.body.dispatchEvent(pointer('pointerdown'));
      await settle(fixture);
      expect(isOpen(tooltipOf(el, link))).toBe(false);

      await hold(fixture, link);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await settle(fixture);
      expect(isOpen(tooltipOf(el, link))).toBe(false);
    });

    it('never opens on a mouse held down, and that click still navigates', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/trades');
      await hold(fixture, link, 'mouse');
      expect(isOpen(tooltipOf(el, link))).toBe(false);
      link.dispatchEvent(tap());
      await settle(fixture);
      expect(TestBed.inject(Router).url).toBe('/trades');
    });

    it('opens on a mouse hover only after the hover delay (Decision 6)', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      try {
        link.dispatchEvent(new MouseEvent('mouseenter'));
        vi.advanceTimersByTime(HINT_HOVER_DELAY_MS - 1);
        fixture.detectChanges();
        expect(isOpen(tooltipOf(el, link))).toBe(false);
        vi.advanceTimersByTime(1);
      } finally {
        vi.useRealTimers();
      }
      await settle(fixture);
      expect(isOpen(tooltipOf(el, link))).toBe(true);
    });

    it('moves a held-open tooltip to the tab held next (one at a time)', async () => {
      const { fixture, el } = await mount('/dashboard');
      const first = tabLink(el, '/dashboard');
      const second = tabLink(el, '/calendar');
      await hold(fixture, first);
      expect(isOpen(tooltipOf(el, first))).toBe(true);
      await hold(fixture, second);
      expect(isOpen(tooltipOf(el, second))).toBe(true);
      expect(isOpen(tooltipOf(el, first))).toBe(false);
    });

    it('places the tooltip above its tab, centred, 8px off it', async () => {
      const { fixture, el } = await mount('/dashboard');
      const link = tabLink(el, '/watchlist');
      link.getBoundingClientRect = () =>
        ({ top: 788, bottom: 844, left: 78, right: 156, width: 78, height: 56, x: 78, y: 788, toJSON: () => ({}) }) as DOMRect;
      const pop = tooltipOf(el, link);
      Object.defineProperty(pop, 'offsetWidth', { configurable: true, value: 70 });
      Object.defineProperty(pop, 'offsetHeight', { configurable: true, value: 24 });
      Object.defineProperty(root, 'clientWidth', { configurable: true, value: 390 });
      Object.defineProperty(root, 'clientHeight', { configurable: true, value: 844 });
      await hold(fixture, link);
      expect(pop.style.top).toBe('756px');
      expect(pop.style.left).toBe('82px');
    });
  });
```

The numbers in the last test are V247-6's `placeAbove` case: top `788 - 24 - 8 = 756`, left `78 + 78/2 - 70/2 = 82`.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/phone-tab-bar.spec.ts`
Expected: FAIL. No tab has an `aria-describedby` or a `[role="tooltip"]`, so `tooltipOf` returns null and the reads throw; no tab carries `sb-long-press`. The mouse test fails at `tooltipOf` too (it needs the hint to exist).

- [ ] **Step 3: Add the hints and the long-press** in `frontend/src/app/shell/phone-tab-bar.ts`.

Imports become:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';

import { HINT_HOVER_DELAY_MS, Hint } from '../ui/hint';
import { Icon } from '../ui/icon';
import { LongPress } from '../ui/long-press';
import { NAV_ENTRIES, phoneTabPathFor } from './nav';
import { TabBarPrefs } from './tab-bar-prefs';
```

and the component's `imports` array:

```ts
  imports: [RouterLink, Icon, Hint, LongPress],
```

Replace the `@for` block of the template with:

```html
      @for (tab of tabs(); track tab.path) {
        <a
          #link
          class="tab"
          [routerLink]="tab.path"
          [class.active]="activePath() === tab.path"
          [attr.aria-current]="activePath() === tab.path ? 'page' : null"
          sbLongPress
          (longPress)="hint.openPinned()"
        >
          <span class="glyph" aria-hidden="true"><sb-icon [name]="tab.icon" [size]="24" /></span>
          <span class="tab-label">{{ tab.label }}</span>
        </a>
        <sb-hint #hint [anchor]="link" [text]="railLabelOf(tab.path)" placement="above" [openDelay]="hintDelay" />
      }
```

`#link` and `#hint` are per-iteration template refs (part 3's rail uses the same pattern). The More button is unchanged.

In the doc comment, after the paragraph V247-12b added (ending `... full text: never colour alone.`), add:

```ts
 *
 * Press and hold (v240 §6): a 500ms touch on a tab opens its name above it
 * (sbLongPress -> sb-hint openPinned(), placement "above") and navigates
 * nowhere; it stays until the next touch or Escape. A mouse hovers instead,
 * after HINT_HOVER_DELAY_MS. The name is the rail's, so Home reads
 * "Dashboard" (Decision 9). More has no hint: its label is its name.
```

In the class, add below `protected readonly tabs = inject(TabBarPrefs).tabs;`:

```ts
  /** The hover delay the rail's hints use too (Decision 6). */
  protected readonly hintDelay = HINT_HOVER_DELAY_MS;

  /** A tab's tooltip is its page's rail name: the Home tab reads "Dashboard". */
  protected railLabelOf(path: string): string {
    return NAV_ENTRIES.find((entry) => entry.path === path)?.label ?? path;
  }
```

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/shell/phone-tab-bar.spec.ts --include src/app/ui/long-press.spec.ts --include src/app/ui/hint.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, 0 failed. `shell.spec.ts` rides along because the shell mounts the bar on a phone width and now gets four more `role="tooltip"` popovers there. If a shell test counts tooltips page-wide at phone width and fails, scope its query to `nav.rail` (the rail is hidden on a phone), as part 3's rail tests do. A 60s `Timeout waiting for worker` is load: re-run once.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/phone-tab-bar.ts frontend/src/app/shell/phone-tab-bar.spec.ts
git commit -m "feat(v247): tab press-and-hold shows the tab's rail name above it" -m "sbLongPress -> sb-hint openPinned(), placement above; hover after HINT_HOVER_DELAY_MS; More has no hint (Decision 9)."
```

