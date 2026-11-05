# v195 — Graphite, Part 8: System regrouping (scan health to System, the Providers tab, System on `sb-page`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body.
**Index:** [2026-10-25-v195-graphite-frontend-redesign_0-index.md](2026-10-25-v195-graphite-frontend-redesign_0-index.md) — Goal, Global Constraints, the Standard task close, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V195-22:" -A 400 <this file>`.

**Scope of this part (V195-22..V195-24):** spec §5.1 (the Risk → System move), corrections 3 and 4, and Phase 4 for the System workspace. V195-22 gives `SystemStore` its own read of the **existing** `GET /risk` (correction 3) and the four scan-health and data-source computeds, adds the `providers` tab value with its resolver, and puts the tab order at Scan · Providers · Settings · Logs with Settings still the default (correction 4). V195-23 builds the Providers tab (Data providers, Data source, Scan health, Swallowed errors), takes those panels off the Scan tab and off Risk, and drops the four computeds from `RiskStore`. V195-24 moves System onto `sb-page`: the tab bar in the scope bar, and the three destructive commands of the System tabs (restart bot, clear log, discard settings) in `[page-actions]`, each `danger-quiet` behind `sb-confirm-dialog`. All three are one lane, run in id order (index § Parallelisation: System + Risk); V195-25 (Part 9) follows them on `risk.ts`.

**Where commands run.** `MAIN` = `E:/Documents/Private/Projects/Discord-Bot`; `WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign`. Never `cd`; edit files only under `$WT/`. Frontend runs through `npm --prefix "$WT/frontend" ...`.

**The state earlier tasks leave (read before editing).** Part 7's and Part 7c's "The state earlier tasks leave" lists bind these tasks, including Part 6's rule on `title` in new templates (no `title`, `[title]` or `[attr.title]` binding on a native element in a `.ts` template; `sb-confirm-dialog`'s static `title="…"` input is the existing, allowed form). On top of that:

- `frontend/src/app/ui/page.ts` (V195-21): `Page` (`sb-page`), `heading`/`description` inputs falling back to `RouteTitleService.title()` / `subtitle()`. Markup: `header.bar` > `div.heading` (`h1.title`, optional `p.description`) + `div.actions.slot`; then `div.scope.slot`, `div.kpis.slot`, `div.primary.slot`, `div.secondary.slot`; then the default `<ng-content />` (dialogs). **Usage rule:** each slot's content is ONE element carrying the slot attribute (`page-actions`, `page-scope`, `page-kpis`, `page-primary`, `page-secondary`); a conditional goes inside that element, never the attribute inside an `@if`. Dialogs need no slot. Destructive controls only in `[page-actions]`: the killswitch `variant="danger"` with `dangerVariant="danger"`, everything else `danger-quiet`.
- `frontend/src/app/ui/button.ts`, `confirm-dialog.ts` (V195-8): `ButtonVariant` has `'danger-quiet'`; the button's host class is its variant; `ConfirmDialog.dangerVariant = input<'danger' | 'danger-quiet'>('danger-quiet')`. V195-8 already renamed the three System call sites: the Restart bot button in `scan-tab.ts` and the `slot="clear"` button in `logs-tab.ts` are `variant="danger-quiet"`, and the settings `Discard` button is `variant="danger-quiet"` (it was `ghost`).
- `frontend/src/app/ui/layout.ts` (V195-9): `sb-panel` renders its `heading` as an `h2`; `sb-tab-bar` renders `button[role="tab"]` with the label in `span.label`.
- `frontend/src/app/shell/palette/palette-items.ts` (V195-19): `TAB_PAGES` already holds `tab('/system', 'System', 'providers', 'Providers')` (query `?tab=providers`) beside `scan` and `logs`. Until V195-22 that link falls back to Settings; V195-22 pins it resolving.
- `frontend/src/app/ui/primitives.spec.ts`: the `no call site hand-rolls a button` / `form control` gates scan every template outside `ui/` (`callSites()`). Every button these tasks add goes through `button[sb-button]`; none needs an allowlist entry.
- `frontend/src/app/workspaces/workspace-consistency.spec.ts` bans `<h1` in workspace sources: `sb-page` renders the page's one `h1`, so `system.ts` writes none.

v194 and V195-1..V195-21 edited several of these files (`scan-tab.ts`, `logs-tab.ts`, `settings-tab.ts`, `risk.ts`): every step below names its edit by symbol or exact string, never by line number. Re-read each file before editing it.

---

# Phase 5 — Workspaces: System

### Task V195-22: `SystemStore` reads `api.risk()` for scan health and data source; `providers` tab and `resolveProviders`; `systemTab` learns `providers`; tab order Scan · Providers · Settings · Logs
**Model:** sonnet — a store gains one existing GET, four computeds and one resolver, and the route learns one tab value; the care is in the default tab staying Settings and a failed `/risk` read never failing the route.

**Files:**
- Modify: `frontend/src/app/stores/system.store.ts` (`SYSTEM_TABS`, new `systemTabFrom`, `SystemSlice`, the initial state, one new `withComputed` block, `resolveRisk`, `resolveProviders`, `resolveTab`, `loadProviders`, the store's doc comment)
- Modify: `frontend/src/app/stores/system.store.spec.ts` (imports; two appended `describe` blocks)
- Modify: `frontend/src/app/workspaces/system/system.routes.ts` (`systemTab`, `refreshOnSystem`, now exported)

**Interfaces:**
- Consumes: `ApiClient.risk(): Observable<Risk>` (`GET /api/v1/risk`, `api/api-client.ts`; the endpoint `RiskStore` already reads); `Risk.scan_health: ScanHealth { durations_s: number[]; latest_s: number | null; slowdown: boolean; data_sources?: DataSourcesHealth | null }` and `DataSourcesHealth { enabled; feed; breaker_open; fallback_rate: number | null; scans }` (`api/models.ts`); `routeRequest` (`routing/route-request.ts`: a non-auth failure runs `error` and completes with `undefined`); the store's existing `resolveHealth()`, `resolveSettings`, `resolveLogs`, `resolveScan`; `TAB_PAGES` (`shell/palette/palette-items.ts`, V195-19, spec only); `RefreshPredicate` (`routing/route-metadata.ts`).
- Produces:
  - `SYSTEM_TABS = ['scan', 'providers', 'settings', 'logs'] as const` (bar order, correction 4); `SystemTab` gains `'providers'`.
  - `systemTabFrom(raw: string | null | undefined): SystemTab` — a known value opens its tab; absent, empty or unknown opens `'settings'` (V195-23's `System.activeTab` uses it too).
  - `SystemStore` state `risk: Risk | null`, `riskError: string | null`; computeds `scanDurations: Signal<readonly number[]>`, `scanLatestS: Signal<number | null>`, `scanSlowdown: Signal<boolean>`, `dataSources: Signal<DataSourcesHealth | null>`; methods `resolveRisk(): Observable<void>`, `resolveProviders(): Observable<void>` (`forkJoin` of `resolveHealth()` and `resolveRisk()`), `loadProviders(): void`; `resolveTab('providers')` runs `resolveProviders`.
  - `system.routes.ts`: `refreshOnSystem` exported; the Providers tab refreshes on `scan` and `bot` events, like Scan.

**What changes, and what is already there.** Scan health (latest duration, recent durations, the slowdown flag) and the data source (Alpaca feed, fallback rate, breaker) are today computeds on the route-scoped `RiskStore`, read from the `scan_health` block of `GET /risk`, and shown on Risk. Spec §5.1 moves them to System's new Providers tab beside *Data providers*. `SystemStore` cannot inject `RiskStore` (each is provided by its own route), so, per correction 3, `SystemStore` reads the **same existing** `api.risk()` itself; no endpoint is added. This task adds the data side only: the state, the four computeds (the same expressions `RiskStore` uses, on the new `risk` slice), the `providers` tab value and its resolver, and the route's refresh rule. Nothing renders them yet: V195-23 builds the tab and removes the Risk panels and the `RiskStore` computeds. Settings stays the landing tab (correction 4: it holds the unsaved draft) even though Scan is now first in the bar, and `systemTabFrom` is the one place that rule lives. Until V195-23 adds a Providers entry to the tab bar, `?tab=providers` resolves its data and the component falls through to its `@default` (Settings); the branch merges only at V195-36. The palette's `/system?tab=providers` link (V195-19's `TAB_PAGES`) resolves from this task on, and a test pins that every System tab the palette links is a real tab.

- [ ] **Step 1: Write the failing tests**

In `$WT/frontend/src/app/stores/system.store.spec.ts`:

1. Add to the imports at the top of the file (keep the existing ones):

```ts
import { ActivatedRouteSnapshot, convertToParamMap } from '@angular/router';

import { TAB_PAGES } from '../shell/palette/palette-items';
import { refreshOnSystem } from '../workspaces/system/system.routes';
```

2. Change `import { SettingField, Settings } from '../api/models';` to `import { Risk, SettingField, Settings } from '../api/models';` and `import { SystemStore } from './system.store';` to `import { SYSTEM_TABS, SystemStore, systemTabFrom } from './system.store';`.

3. Append at the end of the file, after the closing `});` of `describe('SystemStore', ...)`:

```ts
/* -- v195 §5.1: scan health and the data source move to System → Providers -- */

const RISK = {
  heat: { open_pct: 3, cap_pct: 6, utilisation_pct: 50 },
  positions: [],
  sector_heat: [],
  clusters: [],
  throttle: { multiplier: 1, paused: false },
  killswitch: { on: false, reason: null, at: null },
  scan_health: {
    durations_s: [12, 14, 31],
    latest_s: 31,
    slowdown: true,
    data_sources: {
      enabled: true, feed: 'iex', breaker_open: false, fallback_rate: 0.05, scans: 20,
    },
  },
  metrics: null,
  correlation: null,
} as unknown as Risk;

const routeFor = (tab: string | null) =>
  ({ queryParamMap: convertToParamMap(tab === null ? {} : { tab }) }) as ActivatedRouteSnapshot;

describe('System tabs (v195 §5.1, correction 4)', () => {
  it('orders the bar Scan, Providers, Settings, Logs', () => {
    expect([...SYSTEM_TABS]).toEqual(['scan', 'providers', 'settings', 'logs']);
  });

  it('opens every known tab by its query value', () => {
    for (const tab of SYSTEM_TABS) {
      expect(systemTabFrom(tab)).toBe(tab);
    }
  });

  it('lands on Settings when the value is absent, empty or unknown, not on the first tab', () => {
    expect(systemTabFrom(null)).toBe('settings');
    expect(systemTabFrom(undefined)).toBe('settings');
    expect(systemTabFrom('')).toBe('settings');
    expect(systemTabFrom('health')).toBe('settings');
  });

  it('resolves every System tab the command palette links to (V195-19 TAB_PAGES)', () => {
    const linked = TAB_PAGES
      .filter((item) => item.route === '/system')
      .map((item) => item.queryParams?.['tab'] ?? '');
    expect(linked).toContain('providers');
    for (const tab of linked) {
      expect(systemTabFrom(tab)).toBe(tab);
    }
  });

  it('refreshes the Providers tab on scan and bot events, as the Scan tab does', () => {
    for (const tab of ['providers', 'scan']) {
      expect(refreshOnSystem('scan', routeFor(tab))).toBe(true);
      expect(refreshOnSystem('bot', routeFor(tab))).toBe(true);
      expect(refreshOnSystem('settings', routeFor(tab))).toBe(false);
    }
    expect(refreshOnSystem('settings', routeFor(null))).toBe(true);
    expect(refreshOnSystem('scan', routeFor('logs'))).toBe(false);
  });
});

describe('SystemStore scan health and data source (v195 §5.1, correction 3)', () => {
  let store: InstanceType<typeof SystemStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        SystemStore,
      ],
    });
    store = TestBed.inject(SystemStore);
    backend = TestBed.inject(HttpTestingController);
  });

  it('reads nothing until a tab asks, and starts from empty, not zero', () => {
    backend.expectNone('/api/v1/risk');
    expect(store.risk()).toBeNull();
    expect(store.scanDurations()).toEqual([]);
    expect(store.scanLatestS()).toBeNull();
    expect(store.scanSlowdown()).toBe(false);
    expect(store.dataSources()).toBeNull();
  });

  it('resolves the Providers tab from the health and risk reads, and nothing else', () => {
    store.resolveTab('providers').subscribe();
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush(RISK);
    backend.expectNone('/api/v1/system/settings');
    backend.expectNone('/api/v1/system/scan');

    expect(store.health()).toEqual(HEALTH);
    expect(store.scanDurations()).toEqual([12, 14, 31]);
    expect(store.scanLatestS()).toBe(31);
    expect(store.scanSlowdown()).toBe(true);
    expect(store.dataSources()).toEqual({
      enabled: true, feed: 'iex', breaker_open: false, fallback_rate: 0.05, scans: 20,
    });
    expect(store.riskError()).toBeNull();
  });

  it('reads a payload from before v106 as no data-source reading, not as a broken one', () => {
    store.resolveProviders().subscribe();
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush({
      ...RISK, scan_health: { durations_s: [], latest_s: null, slowdown: false },
    });

    expect(store.dataSources()).toBeNull();
    expect(store.scanLatestS()).toBeNull();
  });

  it('keeps the last good reading, says so, and still finishes the route when /risk fails', () => {
    store.resolveProviders().subscribe();
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush(RISK);

    let finished = 0;
    store.resolveProviders().subscribe({ complete: () => { finished += 1; } });
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(store.scanLatestS()).toBe(31);
    expect(store.riskError()).toBe('The admin is not responding.');
    expect(store.health()).toEqual(HEALTH);
    expect(finished).toBe(1);
  });

  it('shows the server message for a risk error that is not unavailability', () => {
    store.resolveRisk().subscribe();
    backend.expectOne('/api/v1/risk').flush(
      { error: { code: 'invalid', message: 'bad scan_health row' } },
      { status: 400, statusText: 'Bad Request' },
    );

    expect(store.riskError()).toBe('bad scan_health row');
  });

  it('leaves the Scan tab on its own reads', () => {
    store.resolveTab('scan').subscribe();
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectNone('/api/v1/risk');
  });
});
```

`FakeEventStream`, `HEALTH` and `SCAN` are the file's existing top-level declarations; `EventStream`, `TestBed`, `HttpTestingController`, `provideHttpClient`, `withInterceptors`, `provideHttpClientTesting`, `provideZonelessChangeDetection`, the three interceptors, `beforeEach`, `describe`, `expect` and `it` are already imported.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/stores/system.store.spec.ts
```

Expected: FAIL. The bar-order case reads `['settings', 'logs', 'scan']`; `systemTabFrom`, `refreshOnSystem`, `resolveRisk`, `resolveProviders` and the four computeds are not functions; `resolveTab('providers')` throws. Every case already in `describe('SystemStore', ...)` passes.

- [ ] **Step 3: `system.store.ts` — the tab list and its fallback**

In `$WT/frontend/src/app/stores/system.store.ts`:

1. In the `from '../api/models'` import list, add `DataSourcesHealth` and `Risk` (alphabetical with the rest: `DataSourcesHealth, Logs, Risk, ScanStatus, SettingField, …`).

2. Replace

```ts
export const SYSTEM_TABS = ['settings', 'logs', 'scan'] as const;
export type SystemTab = (typeof SYSTEM_TABS)[number];
```

with

```ts
/** v195 §5.1 and correction 4: the bar reads Scan · Providers · Settings ·
 *  Logs. The order is the bar's; the landing tab is not the first one, see
 *  `systemTabFrom`. */
export const SYSTEM_TABS = ['scan', 'providers', 'settings', 'logs'] as const;
export type SystemTab = (typeof SYSTEM_TABS)[number];

/**
 * The tab a `?tab=` value opens. Settings stays the landing tab (correction
 * 4): it holds the unsaved draft, and moving the landing tab would put a
 * reader somewhere they did not expect with edits still pending. So an
 * absent, empty or unknown value falls back to Settings, not to the first
 * tab in the bar -- which also keeps a hand-edited URL showing something.
 *
 * One rule for the route resolver and the component, so the data the route
 * loads and the tab the page shows can never disagree.
 */
export function systemTabFrom(raw: string | null | undefined): SystemTab {
  return (SYSTEM_TABS as readonly string[]).includes(raw ?? '') ? (raw as SystemTab) : 'settings';
}
```

- [ ] **Step 4: `system.store.ts` — the `/risk` slice, its computeds and the Providers resolver**

1. In `interface SystemSlice`, directly after `healthError: string | null;`, add:

```ts
  /** v195 §5.1 — the `GET /risk` payload, read here for its `scan_health`
   *  block only (scan durations, the slowdown flag, the data source), which
   *  the Providers tab shows beside the provider rows. The existing
   *  endpoint `RiskStore` reads; System cannot inject that route-scoped
   *  store, so it reads the endpoint itself (correction 3). Null until the
   *  first answer; a failed refresh keeps the last good payload and says so
   *  in `riskError`, as `health` does. */
  risk: Risk | null;
  riskError: string | null;
```

2. In the initial state passed to `withState<SystemSlice>({ ... })`, directly after `healthError: null,`, add:

```ts
    risk: null,
    riskError: null,
```

3. After the second `withComputed` block (the one that returns `visibleFields`) and before `withComputed(({ logs, logLevels }) => {`, add a block:

```ts
  // v195 §5.1: scan health and the data source, moved here from RiskStore.
  // The same expressions, on this store's own read of GET /risk.
  withComputed(({ risk }) => ({
    /** Oldest first, as the server sends them -- the sparkline's order. */
    scanDurations: computed<readonly number[]>(
      () => risk()?.scan_health?.durations_s ?? [],
    ),
    scanLatestS: computed(() => risk()?.scan_health?.latest_s ?? null),
    scanSlowdown: computed(() => risk()?.scan_health?.slowdown ?? false),
    /** Null before v106 and before the first answer: "no reading yet", which
     *  the panel says in words, never an empty source name. */
    dataSources: computed<DataSourcesHealth | null>(
      () => risk()?.scan_health?.data_sources ?? null,
    ),
  })),
```

4. In the `withMethods` block, directly after the `resolveHealth` constant, add:

```ts
    /** v195 correction 3: the scan-health and data-source figures come from
     *  GET /risk. Same error wording as the other reads. */
    const resolveRisk = (): Observable<void> => routeRequest(api.risk(), {
      start: () => undefined,
      next: (risk) => patchState(store, { risk, riskError: null }),
      error: (error) => patchState(store, {
        riskError: error.code === 'unavailable'
          ? 'The admin is not responding.' : error.message,
      }),
    });

    /** v195 §5.1: the Providers tab is the provider rows and swallowed
     *  errors (`/system/health`) and scan health and the data source
     *  (`/risk`). `routeRequest` completes a non-auth failure with
     *  `undefined`, so one failed read never blocks the other or the route. */
    const resolveProviders = (): Observable<void> =>
      forkJoin([resolveHealth(), resolveRisk()]).pipe(map(() => undefined));
```

5. Replace

```ts
    const resolveTab = (tab: SystemTab): Observable<void> =>
      ({ settings: resolveSettings, logs: resolveLogs, scan: resolveScan })[tab]();
```

with

```ts
    const resolveTab = (tab: SystemTab): Observable<void> =>
      ({
        scan: resolveScan,
        providers: resolveProviders,
        settings: resolveSettings,
        logs: resolveLogs,
      })[tab]();
```

6. After `const loadScan = (): void => { resolveScan().subscribe(); };` add `const loadProviders = (): void => { resolveProviders().subscribe(); };`. In the returned object, after `resolveHealth,` add `resolveRisk,` and `resolveProviders,`, and after `loadScan,` add `loadProviders,`.

7. In the store's doc comment, replace `Settings, logs and scan control — the three tabs of the System workspace.` with `Settings, logs, scan control and provider health — the four tabs of the System workspace.`

- [ ] **Step 5: `system.routes.ts` — the route learns `providers`**

Replace the whole of `$WT/frontend/src/app/workspaces/system/system.routes.ts` with:

```ts
import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { SystemStore, SystemTab, systemTabFrom } from '../../stores/system.store';

const systemTab = (route: ActivatedRouteSnapshot): SystemTab =>
  systemTabFrom(route.queryParamMap.get('tab'));

/** Scan and Providers both move with every scan (v195 §5.1: scan health and
 *  the provider rows are written per scan), so both refresh on `scan` and
 *  `bot`. Logs has no event and refreshes by its button. */
export const refreshOnSystem: RefreshPredicate = (event, route) => {
  switch (systemTab(route)) {
    case 'settings': return event === 'settings';
    case 'scan':
    case 'providers': return event === 'scan' || event === 'bot';
    default: return false;
  }
};

export const systemRoutes: Routes = [{
  path: '', providers: [SystemStore], runGuardsAndResolvers: 'always',
  data: routeData('System', refreshOnSystem),
  resolve: { ready: resolveRoute((route) => inject(SystemStore).resolveTab(systemTab(route))) },
  loadComponent: () => import('./system').then((m) => m.System),
}];
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/stores/system.store.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/workspaces/system/logs-tab.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. If the palette case fails on a value other than `providers`, `TAB_PAGES` links a System tab that `SYSTEM_TABS` lacks: fix the link in `palette-items.ts` only if it is a typo, otherwise stop and report (the tab set is this task's contract). If a Providers read is left pending, `resolveTab`'s map is missing `providers`. If `refreshOnSystem` is `undefined`, the `export` was not added.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green. `system.ts` still compiles: its `TAB_IDS` is built from `SYSTEM_TABS`, and its bar still lists three tabs until V195-23.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/stores/system.store.spec.ts`). No browser pass: nothing renders the new data until V195-23. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/stores/system.store.ts frontend/src/app/stores/system.store.spec.ts frontend/src/app/workspaces/system/system.routes.ts
git -C "$WT" commit -m "feat(v195): SystemStore reads scan health and data source; providers tab value (V195-22)" -m "Spec §5.1 and corrections 3 and 4: SystemStore reads the existing GET /risk itself (System cannot inject the route-scoped RiskStore) and exposes scanDurations, scanLatestS, scanSlowdown and dataSources on it. SYSTEM_TABS becomes scan, providers, settings, logs; systemTabFrom keeps Settings the landing tab for an absent or unknown ?tab=. resolveTab('providers') reads /system/health and /risk together, and the route refreshes Providers on scan and bot events. A spec pins every System tab the command palette links as a real tab." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

### Task V195-23: Providers tab (Data providers, Data source, Scan health, Swallowed errors); Scan tab and Risk lose those panels; `RiskStore` drops the four computeds
**Model:** sonnet — panels move between three components and two stores with their tests; the care is in moving every v106 data-source case rather than deleting it, in the Scan tab no longer reading health, and in Risk losing nothing but the two panels.

**Files:**
- Create: `frontend/src/app/workspaces/system/providers-tab.ts`
- Create: `frontend/src/app/workspaces/system/providers-tab.spec.ts`
- Create: `frontend/src/app/workspaces/system/system.spec.ts`
- Modify: `frontend/src/app/workspaces/system/system.ts` (`TABS`, `TAB_IDS` removed, `activeTab`, `imports`, the `@switch`, doc comment)
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts` (the two health panels and the health-error line removed)
- Modify: `frontend/src/app/workspaces/system/scan-tab.spec.ts` (one appended `describe`)
- Modify: `frontend/src/app/stores/system.store.ts` (`resolveScan` reads the scan status only; the `health` doc comment)
- Modify: `frontend/src/app/stores/system.store.spec.ts` (`boot`, `bootWithLog`, the three v148 resolver cases and V195-22's Scan-tab case)
- Modify: `frontend/src/app/workspaces/risk/risk.ts` (the Scan health and Data source panels, `sourceName`, `fallbackText`, `Sparkline`, `DataSourcesHealth`, their styles and three comments)
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts` (the v106 data-source cases move out; one absence case; one case renamed)
- Modify: `frontend/src/app/stores/risk.store.ts` (the four computeds and `DataSourcesHealth` removed; doc comment)
- Modify: `frontend/src/app/stores/risk.store.spec.ts` (one appended case)

**Interfaces:**
- Consumes: from V195-22, `SystemStore.scanDurations()`, `scanLatestS()`, `scanSlowdown()`, `dataSources()`, `health()`, `healthError()`, `riskError()`, `loadProviders()`, `resolveProviders()`, `systemTabFrom(raw)`, `SYSTEM_TABS` (`['scan', 'providers', 'settings', 'logs']`); `ProviderHealthPanel` (`sb-provider-health-panel`, `health = input<SystemHealth | null>(null)`, panel heading `Data providers`) and `SwallowedErrorsPanel` (`sb-swallowed-errors-panel`, same input, heading `Swallowed errors`), both in `workspaces/system/`; `Sparkline` (`sb-sparkline`, `points = input.required<readonly number[]>()`, `label`); `num` (`ui/format.ts`, `num(null)` is the em dash `ABSENT`); `Panel` (`sb-panel`, `heading` rendered as an `h2`); `TabBar` (`button[role="tab"]` with `span.label`, `aria-selected`).
- Produces:
  - `ProvidersTab` (`sb-providers-tab`, `workspaces/system/providers-tab.ts`): panels in this order, Data providers, Data source, Scan health, Swallowed errors; then `p.error[role="alert"]` lines for `healthError` and `riskError`. Exported pure helpers `dataSourceName(ds: DataSourcesHealth): string`, `fallbackText(ds: DataSourcesHealth): string`, `scanSecondsText(seconds: number | null): string`.
  - `System`'s bar reads Scan · Providers · Settings · Logs; `?tab=providers` renders `sb-providers-tab`; `activeTab` is `systemTabFrom(tab())`.
  - `SystemStore.resolveScan()` reads `/system/scan` only.
  - `RiskStore` no longer has `scanDurations`, `scanLatestS`, `scanSlowdown`, `dataSources`.
  - `frontend/src/app/workspaces/system/system.spec.ts` (created here; V195-24 extends it): helpers `mount(tab?: string)` and `tabLabels(el)`.

**What changes, and what is already there.** Spec §5.1: System's tabs become Scan · Providers · Settings · Logs, and Providers holds *Data providers*, *Data source*, *Scan health* and *Swallowed errors*. Today *Data providers* and *Swallowed errors* (v148) sit at the foot of the Scan tab, fed by `SystemStore.health` through `resolveScan`, and *Scan health* and *Data source* (v106) sit at the foot of Risk, fed by four `RiskStore` computeds. V195-22 gave `SystemStore` those four computeds on its own `/risk` read and a `resolveProviders` that reads both. This task builds `sb-providers-tab` from the four panels (the two v148 components reused as they are; the two Risk panels moved with their markup, wording and styles), adds it to System's bar second, and removes the panels from where they were: the Scan tab keeps the scan status, the scan commands and the bot process; Risk keeps only risk (heat, exposure, sectors, clusters, metrics, the killswitch); `RiskStore` drops the four computeds; `resolveScan` stops reading `/system/health`, which only the Providers tab shows now. A bookmark to `?tab=scan` that expected the provider rows finds them one tab over (spec §5.1). Every v106 data-source case in `risk.spec.ts` moves to `providers-tab.spec.ts`, and every v148 health-resolver case in `system.store.spec.ts` is repointed from the Scan resolver to the Providers resolver: moved, not deleted. One wording fix rides along: an unknown latest duration now reads `—`, where Risk printed `—s`. If v194 gave either Risk panel a hint or description, it moves with the panel, verbatim. `system.spec.ts` is new here (System had no component spec); V195-24 extends it when System moves onto `sb-page`.

- [ ] **Step 1: Write the failing tests**

1. Create `$WT/frontend/src/app/workspaces/system/providers-tab.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { DataSourcesHealth, SystemHealth } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { ProvidersTab, dataSourceName, fallbackText, scanSecondsText } from './providers-tab';

const HEALTH: SystemHealth = {
  providers: [],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [],
  bot_counts_since: null,
};

const ALPACA: DataSourcesHealth = {
  enabled: true, feed: 'iex', breaker_open: false, fallback_rate: 0.05, scans: 20,
};

interface Reading {
  scanHealth?: Record<string, unknown>;
  riskFails?: boolean;
}

async function render(reading: Reading = {}): Promise<HTMLElement> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  const fixture = TestBed.createComponent(ProvidersTab);
  const backend = TestBed.inject(HttpTestingController);
  TestBed.inject(SystemStore).loadProviders();
  backend.expectOne('/api/v1/system/health').flush(HEALTH);
  const risk = backend.expectOne('/api/v1/risk');
  if (reading.riskFails) {
    risk.flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );
  } else {
    risk.flush({
      scan_health: reading.scanHealth ?? {
        durations_s: [12, 14, 31], latest_s: 31, slowdown: false, data_sources: ALPACA,
      },
    });
  }
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const headings = (el: HTMLElement) =>
  [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent!.trim());

describe('Providers tab helpers (moved from risk.ts, v195 §5.1)', () => {
  it('names the Alpaca feed, or yfinance alone when Alpaca is off', () => {
    expect(dataSourceName(ALPACA)).toBe('Alpaca · IEX');
    expect(dataSourceName({ ...ALPACA, enabled: false })).toBe('yfinance only');
  });

  it('gives the fallback rate over its sample, or says there was no traffic', () => {
    expect(fallbackText(ALPACA)).toBe('5.0% fallback (20 scans)');
    expect(fallbackText({ ...ALPACA, fallback_rate: null, scans: 3 }))
      .toBe('no Alpaca traffic yet (3 scans)');
  });

  it('prints the last duration in seconds, and an unknown one as a bare dash', () => {
    expect(scanSecondsText(31)).toBe('31.0s');
    expect(scanSecondsText(null)).toBe('—');
  });
});

describe('Providers tab (v195 §5.1)', () => {
  it('holds Data providers, Data source, Scan health and Swallowed errors, in that order', async () => {
    expect(headings(await render())).toEqual([
      'Data providers', 'Data source', 'Scan health', 'Swallowed errors',
    ]);
  });

  it('shows the last scan duration and the recent durations', async () => {
    const el = await render();
    expect(el.querySelector('.scan-latest')!.textContent!.trim()).toBe('31.0s');
    expect(el.querySelector('sb-sparkline')).toBeTruthy();
    expect(el.textContent).not.toContain('Scans are running slower');
  });

  it('warns in amber when scans run slower than usual', async () => {
    const el = await render({
      scanHealth: { durations_s: [12, 40], latest_s: 40, slowdown: true, data_sources: ALPACA },
    });
    const note = [...el.querySelectorAll('p.note')]
      .find((p) => p.textContent!.includes('Scans are running slower'))!;
    expect(note.classList).toContain('warn');
  });

  it('draws no sparkline before any scan was timed', async () => {
    const el = await render({ scanHealth: { durations_s: [], latest_s: null, slowdown: false } });
    expect(el.querySelector('sb-sparkline')).toBeNull();
    expect(el.querySelector('.scan-latest')!.textContent!.trim()).toBe('—');
  });

  /* v106 cases, moved from risk.spec.ts with the panel. */

  it('names the Alpaca feed and the fallback rate over its sample', async () => {
    const el = await render();
    expect(el.textContent).toContain('Alpaca · IEX');
    expect(el.textContent).toContain('5.0% fallback (20 scans)');
    expect(el.querySelector('.sources.warn')).toBeNull();
  });

  it('flags an open breaker as a warning', async () => {
    const el = await render({
      scanHealth: {
        durations_s: [], latest_s: 1.2, slowdown: false,
        data_sources: { ...ALPACA, breaker_open: true, fallback_rate: 0.4 },
      },
    });
    expect(el.querySelector('.sources.warn')).toBeTruthy();
    expect(el.textContent).toContain('Alpaca breaker open');
  });

  it('says yfinance only when Alpaca is off', async () => {
    const el = await render({
      scanHealth: {
        durations_s: [], latest_s: 1.2, slowdown: false,
        data_sources: { ...ALPACA, enabled: false, fallback_rate: null, scans: 0 },
      },
    });
    expect(el.textContent).toContain('yfinance only');
    expect(el.textContent).not.toContain('fallback (');
  });

  it('says there is no reading yet rather than naming no source', async () => {
    const el = await render({ scanHealth: { durations_s: [], latest_s: null, slowdown: false } });
    expect(el.textContent).toContain('No data-source reading yet.');
  });

  it('keeps the provider panels and says which read failed when /risk is down', async () => {
    const el = await render({ riskFails: true });
    expect(headings(el)).toContain('Data providers');
    const alert = el.querySelector('p.error[role="alert"]')!;
    expect(alert.textContent).toContain('Scan health and data source');
    expect(alert.textContent).toContain('The admin is not responding.');
  });
});
```

2. Create `$WT/frontend/src/app/workspaces/system/system.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { SystemStore } from '../../stores/system.store';
import { System } from './system';

async function mount(tab?: string): Promise<{ fixture: ComponentFixture<System>; el: HTMLElement }> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  const fixture = TestBed.createComponent(System);
  if (tab !== undefined) fixture.componentRef.setInput('tab', tab);
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

const tabLabels = (el: HTMLElement) =>
  [...el.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent!.trim());

const selected = (el: HTMLElement) =>
  el.querySelector('[role="tab"][aria-selected="true"]')!.textContent!.trim();

describe('System tabs (v195 §5.1, correction 4)', () => {
  it('orders the bar Scan, Providers, Settings, Logs', async () => {
    const { el } = await mount();
    expect(tabLabels(el)).toEqual(['Scan', 'Providers', 'Settings', 'Logs']);
  });

  it('opens the Providers tab from ?tab=providers', async () => {
    const { el } = await mount('providers');
    expect(selected(el)).toBe('Providers');
    expect(el.querySelector('sb-providers-tab')).toBeTruthy();
    expect(el.querySelector('sb-scan-tab')).toBeNull();
  });

  it('lands on Settings with no ?tab=, though Scan is first in the bar', async () => {
    const { el } = await mount();
    expect(selected(el)).toBe('Settings');
    expect(el.querySelector('sb-settings-tab')).toBeTruthy();
  });

  it('falls back to Settings for an unknown ?tab=', async () => {
    const { el } = await mount('health');
    expect(selected(el)).toBe('Settings');
  });

  it('writes the tab to the URL, and drops it for Settings', async () => {
    const { fixture, el } = await mount();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const tab = (label: string) => [...el.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
      .find((button) => button.textContent!.trim() === label)!;

    tab('Providers').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { tab: 'providers' }, queryParamsHandling: 'merge', replaceUrl: true,
    }));

    tab('Settings').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenLastCalledWith([], expect.objectContaining({
      queryParams: { tab: null },
    }));
  });
});
```

3. In `$WT/frontend/src/app/workspaces/system/scan-tab.spec.ts`, add at the top `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` (above the existing import) and append:

```ts
describe('Scan tab after the Providers split (v195 §5.1)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/system/scan-tab.ts'), 'utf8');

  it('no longer carries the provider and swallowed-error panels; Providers does', () => {
    expect(src).not.toContain('sb-provider-health-panel');
    expect(src).not.toContain('sb-swallowed-errors-panel');
    expect(src).not.toContain('store.health');
  });
});
```

4. In `$WT/frontend/src/app/stores/risk.store.spec.ts`, inside `describe('RiskStore', ...)`, after its last case (`holds a command error until the next attempt`), add:

```ts
  it('keeps only risk: scan health and the data source moved to SystemStore (v195 §5.1)', () => {
    for (const key of ['scanDurations', 'scanLatestS', 'scanSlowdown', 'dataSources']) {
      expect(key in store).toBe(false);
    }
  });
```

5. In `$WT/frontend/src/app/workspaces/risk/risk.spec.ts`:
   - Rename `it('does not claim the scan-health panel is as fresh as the metrics', ...)` to `it('dates each metrics panel by its own bar, not one stamp for the page', ...)`; its body is unchanged.
   - Replace everything from the comment `/* -- v106 -- the data-source panel -- */` through the closing `});` of `describe('Risk data-source panel', ...)` (the `renderDataSources` helper and its three cases) with:

```ts
/* -- v195 §5.1 -- scan health and the data source moved to System → Providers.
 * Their v106 cases moved with them, to system/providers-tab.spec.ts. -- */

describe('Risk keeps only risk (v195 §5.1)', () => {
  it('shows no Scan health or Data source panel, whatever the payload carries', async () => {
    const el = (await render({
      scan_health: {
        durations_s: [12, 14], latest_s: 14, slowdown: true,
        data_sources: {
          enabled: true, feed: 'iex', breaker_open: true, fallback_rate: 0.4, scans: 20,
        },
      },
    } as Partial<RiskData>)).nativeElement as HTMLElement;
    const headings = [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent!.trim());

    expect(headings).not.toContain('Scan health');
    expect(headings).not.toContain('Data source');
    expect(el.querySelector('sb-sparkline')).toBeNull();
    expect(el.textContent).not.toContain('Alpaca');
    expect(el.textContent).not.toContain('Scans are running slower');
  });
});
```

6. In `$WT/frontend/src/app/stores/system.store.spec.ts` (the Scan tab stops reading health):
   - In `const boot = ...` and in `const bootWithLog = ...`, delete the line `backend.expectOne('/api/v1/system/health').flush(HEALTH);`.
   - Under `/* -- v148: system health ---- */`, replace the case `resolves health together with the scan status` with:

```ts
  it('resolves health with the Providers tab, and the Scan tab no longer reads it (v195 §5.1)', () => {
    store.resolveProviders().subscribe();
    backend.expectOne('/api/v1/system/health').flush(HEALTH);
    backend.expectOne('/api/v1/risk').flush({});

    expect(store.health()).toEqual(HEALTH);
    expect(store.healthError()).toBeNull();

    store.resolveScan().subscribe();
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectNone('/api/v1/system/health');
  });
```

   - Replace the case `refreshes health with the scan tab, so scan and bot events update both panels` with:

```ts
  it('refreshes health with the Providers tab, so scan and bot events update both panels', () => {
    store.resolveTab('providers').subscribe();
    backend.expectOne('/api/v1/system/health').flush({ ...HEALTH, swallowed: [] });
    backend.expectOne('/api/v1/risk').flush({});

    expect(store.health()?.swallowed).toEqual([]);
    backend.expectNone('/api/v1/system/settings');
  });
```

   - Replace the case `keeps the scan status and finishes the route when health fails` with:

```ts
  it('keeps the scan-health reading and finishes the route when health fails', () => {
    let finished = 0;
    store.resolveProviders().subscribe({ complete: () => { finished += 1; } });
    backend.expectOne('/api/v1/risk').flush({ scan_health: { durations_s: [], latest_s: 9, slowdown: false } });
    backend.expectOne('/api/v1/system/health').flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );

    expect(store.scanLatestS()).toBe(9);
    expect(store.health()).toBeNull();
    expect(store.healthError()).toBe('The admin is not responding.');
    expect(finished).toBe(1);
  });
```

   - In V195-22's `describe('SystemStore scan health and data source ...')`, replace the case `leaves the Scan tab on its own reads` with:

```ts
  it('reads only the scan status for the Scan tab', () => {
    store.resolveTab('scan').subscribe();
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
    backend.expectNone('/api/v1/system/health');
    backend.expectNone('/api/v1/risk');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/system/providers-tab.spec.ts --include src/app/workspaces/system/system.spec.ts --include src/app/workspaces/system/scan-tab.spec.ts --include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/stores/system.store.spec.ts
```

Expected: FAIL. `providers-tab.spec.ts` cannot resolve `./providers-tab`; `system.spec.ts` reads `['Settings', 'Logs', 'Scan', …]` and finds no `sb-providers-tab`; the scan-tab source case finds both panel tags; the `RiskStore` case finds `scanDurations`; the Risk absence case finds the `Scan health` heading; the store's Scan-tab cases find a pending `/system/health` request.

- [ ] **Step 3: Create `providers-tab.ts`**

Create `$WT/frontend/src/app/workspaces/system/providers-tab.ts`. If v194 gave Risk's `Scan health` or `Data source` `sb-panel` a hint or description input, copy that input onto the matching panel below, verbatim (v194 hint text is never dropped).

```ts
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { DataSourcesHealth } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { num } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Sparkline } from '../../ui/sparkline';
import { ProviderHealthPanel } from './provider-health-panel';
import { SwallowedErrorsPanel } from './swallowed-errors-panel';

/** v106: "Alpaca · IEX" when Alpaca serves the live path, else the plain
 *  pre-v106 source. Moved from risk.ts with its panel (v195 §5.1). */
export function dataSourceName(ds: DataSourcesHealth): string {
  return ds.enabled ? `Alpaca · ${ds.feed.toUpperCase()}` : 'yfinance only';
}

/** How often the live path fell back to yfinance, over how many scans. */
export function fallbackText(ds: DataSourcesHealth): string {
  if (ds.fallback_rate === null) return `no Alpaca traffic yet (${ds.scans} scans)`;
  return `${(ds.fallback_rate * 100).toFixed(1)}% fallback (${ds.scans} scans)`;
}

/** The last scan's duration. An unknown one is the bare em dash: a unit
 *  after "no value" (Risk printed `—s`) reads like a measurement. */
export function scanSecondsText(seconds: number | null): string {
  return seconds === null ? num(null) : `${num(seconds, 1)}s`;
}

/**
 * System → Providers (v195 §5.1): where the data comes from and whether the
 * scanner is keeping up. Four panels, one question -- "can I trust what the
 * other pages show right now?":
 *
 * - *Data providers* and *Swallowed errors* (v148, `GET /system/health`),
 *   reused as they were on the Scan tab.
 * - *Data source* and *Scan health* (v106, the `scan_health` block of
 *   `GET /risk`), moved from Risk, which now shows only risk. The freshness
 *   chip in the top bar (V195-17) carries the one figure that must stay
 *   visible everywhere; this tab is the detail behind it.
 *
 * Each read fails on its own: a failed `/risk` keeps the provider rows and
 * says which read is stale, and the reverse.
 */
@Component({
  selector: 'sb-providers-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Sparkline, ProviderHealthPanel, SwallowedErrorsPanel],
  template: `
    <sb-provider-health-panel [health]="store.health()" />

    <!-- v106: where live bars and prices come from, and how often Alpaca
         misses. A fallback price is still a real price, so the rate is
         information; an open breaker is the caution -- every eligible
         symbol is on yfinance until it closes. -->
    <sb-panel heading="Data source">
      @if (store.dataSources(); as ds) {
        <div class="sources" [class.warn]="ds.breaker_open">
          <span class="source-name">{{ sourceName(ds) }}</span>
          @if (ds.enabled) {
            <span class="source-rate num">{{ fallback(ds) }}</span>
          }
        </div>
        @if (ds.enabled && ds.breaker_open) {
          <p class="note warn">
            Alpaca breaker open — live prices are coming from yfinance until it closes.
          </p>
        }
      } @else {
        <p class="none">No data-source reading yet.</p>
      }
    </sb-panel>

    <sb-panel heading="Scan health">
      <div class="scan">
        <div class="scan-figures">
          <span class="scan-latest num">{{ seconds(store.scanLatestS()) }}</span>
          <span class="scan-label">last scan</span>
        </div>
        @if (store.scanDurations().length) {
          <sb-sparkline
            [points]="store.scanDurations()"
            label="Recent scan durations, in seconds"
          />
        }
      </div>
      @if (store.scanSlowdown()) {
        <!-- Amber, not red: a slow scan is a caution about freshness, not a
             loss. It matters because stale scans mean every figure on the
             other pages is older than it looks. -->
        <p class="note warn">
          Scans are running slower than usual — setups and prices may be stale.
        </p>
      }
    </sb-panel>

    <sb-swallowed-errors-panel [health]="store.health()" />

    @if (store.healthError(); as message) {
      <p class="error" role="alert">Data providers and swallowed errors: {{ message }}</p>
    }
    @if (store.riskError(); as message) {
      <p class="error" role="alert">Scan health and data source: {{ message }}</p>
    }
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track: one un-shrinkable panel
       must not stretch the tab past the viewport (the Scan tab's rule).
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }

    /* -- data source (v106, moved from risk.ts) -- */
    .sources { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .source-name { font-weight: 600; }
    .source-rate { color: var(--text-secondary); font-size: var(--text-table); }
    .sources.warn .source-name { color: var(--warn); }

    /* -- scan health (moved from risk.ts) -- */
    .scan { display: flex; align-items: center; gap: var(--register-pad); }
    .scan-figures { display: flex; align-items: baseline; gap: var(--space-6); }
    .scan-latest { font-size: var(--text-subhead); font-weight: 600; }
    /* --text-micro: an eyebrow caption, uppercase is kept for micro labels only (spec §1.3). */
    .scan-label {
      color: var(--text-muted);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .scan sb-sparkline { flex: 1 1 auto; min-width: 80px; max-width: 320px; }

    .note { margin-top: var(--space-8); color: var(--text-secondary); font-size: var(--text-table); }
    .warn { color: var(--warn); }
    .none { color: var(--text-muted); font-size: var(--text-table); }
    .error { color: var(--neg); font-size: var(--text-table); }
  `,
})
export class ProvidersTab {
  protected readonly store = inject(SystemStore);

  protected readonly sourceName = dataSourceName;
  protected readonly fallback = fallbackText;
  protected readonly seconds = scanSecondsText;
}
```

`.none` and `.scan-label` take `--text-muted`, not the `--text-faint` / `--text-secondary` Risk used: correction 13 makes `--text-faint` a rule colour, never text, and micro captions use `--text-muted`.

- [ ] **Step 4: Add the tab to `system.ts`**

In `$WT/frontend/src/app/workspaces/system/system.ts`:

1. Replace `import { SYSTEM_TABS, SystemStore, SystemTab } from '../../stores/system.store';` with `import { SystemStore, SystemTab, systemTabFrom } from '../../stores/system.store';`, and after `import { LogsTab } from './logs-tab';` add `import { ProvidersTab } from './providers-tab';`.

2. Replace

```ts
/** Settings · Logs · Scan — spec v14 Decision 8, in its order. */
const TABS: Tab[] = [
  { id: 'settings', label: 'Settings' },
  { id: 'logs', label: 'Logs' },
  { id: 'scan', label: 'Scan' },
];

const TAB_IDS = new Set<string>(SYSTEM_TABS);
```

with

```ts
/** Scan · Providers · Settings · Logs — v195 §5.1, the order of
 *  `SYSTEM_TABS`. Settings stays the landing tab (correction 4). */
const TABS: Tab[] = [
  { id: 'scan', label: 'Scan' },
  { id: 'providers', label: 'Providers' },
  { id: 'settings', label: 'Settings' },
  { id: 'logs', label: 'Logs' },
];
```

3. In the class doc comment, replace `System — the administrative workspace: configuration, logs, scan control.` with `System — the administrative workspace: configuration, logs, scan control, provider health.` and `A shell over three tab components` with `A shell over four tab components`.

4. In the `@Component` `imports` array, replace `[TabBar, SettingsTab, LogsTab, ScanTab, SectionHead]` with `[TabBar, SettingsTab, LogsTab, ScanTab, ProvidersTab, SectionHead]`.

5. In the template's `@switch (activeTab())`, directly after the `@case ('scan') { <sb-scan-tab /> }` block, add:

```html
      @case ('providers') {
        <sb-providers-tab />
      }
```

6. Replace the body of `activeTab`:

```ts
  protected readonly activeTab = computed<SystemTab>(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? (requested as SystemTab) : 'settings';
  });
```

with

```ts
  protected readonly activeTab = computed<SystemTab>(() => systemTabFrom(this.tab()));
```

(keep the doc comment above it).

- [ ] **Step 5: Take the panels off the Scan tab and stop reading health for it**

1. In `$WT/frontend/src/app/workspaces/system/scan-tab.ts`: delete the imports `import { ProviderHealthPanel } from './provider-health-panel';` and `import { SwallowedErrorsPanel } from './swallowed-errors-panel';`; replace the `imports: [ … ]` array (which lists `ProviderHealthPanel, SwallowedErrorsPanel`) with `imports: [Panel, Button, ConfirmDialog, Toolbar, Freshness],`; in the template delete these five lines:

```html
    <sb-provider-health-panel [health]="store.health()" />
    <sb-swallowed-errors-panel [health]="store.health()" />
    @if (store.healthError(); as message) {
      <p class="error" role="alert">Health panels: {{ message }}</p>
    }
```

2. In `$WT/frontend/src/app/stores/system.store.ts`, replace

```ts
    /** v148: the Scan tab is the status AND the two health panels. One
     *  resolver for both means the route's existing `scan`/`bot` refresh
     *  updates all three; `routeRequest` turns a non-auth failure into a
     *  completed `undefined`, so a health failure never blocks the status. */
    const resolveScan = (): Observable<void> =>
      forkJoin([resolveScanStatus(), resolveHealth()]).pipe(map(() => undefined));
```

with

```ts
    /** The Scan tab is the scan status and the bot process. v148's two
     *  health panels moved to the Providers tab (v195 §5.1), which reads
     *  them through `resolveProviders` on the same `scan`/`bot` refresh. */
    const resolveScan = (): Observable<void> => resolveScanStatus();
```

and in `SystemSlice`, in the comment above `health: SystemHealth | null;`, replace `v148 — provider rows and swallowed-error counts for the Scan tab's two` / `health panels.` with `v148 — provider rows and swallowed-error counts for the Providers tab's` / `two health panels (on the Scan tab until v195).` (two comment lines; the rest of the comment is unchanged).

- [ ] **Step 6: Take scan health and the data source off Risk**

1. `$WT/frontend/src/app/stores/risk.store.ts`: delete the whole `/* -- scan health -- */` group (the comment line and the four computeds `scanDurations`, `scanLatestS`, `scanSlowdown`, `dataSources`); in the `from '../api/models'` import drop `DataSourcesHealth`; in the store's doc comment replace `the drawdown throttle and scan health included.` with `and the drawdown throttle included. Scan health and the data source, which the same payload carries, are shown on System → Providers and read there by SystemStore (v195 §5.1).`

2. `$WT/frontend/src/app/workspaces/risk/risk.ts`:
   - Delete `import { Sparkline } from '../../ui/sparkline';`; remove `Sparkline` from the `imports` array; change `import { DataSourcesHealth, RiskPosition } from '../../api/models';` to `import { RiskPosition } from '../../api/models';`.
   - In the template, delete the `<sb-panel heading="Scan health">` panel, the `<!-- v106: where live bars and prices come from, … -->` comment and the `<sb-panel heading="Data source">` panel, each whole (from its opening tag to its `</sb-panel>`).
   - In the class, delete `sourceName(ds: DataSourcesHealth)` and `fallbackText(ds: DataSourcesHealth)` with the `v106: "Alpaca · IEX" …` comment above them.
   - In the styles, delete the `/* -- scan health -- */` rules (`.scan`, `.scan-figures`, `.scan-latest`, the `--text-micro` comment, `.scan-label`, `.scan sb-sparkline`) and the `/* -- data source (v106) -- */` rules (`.sources`, `.source-name`, `.source-rate`, `.sources.warn .source-name`).
   - Comments that named scan health: in the class doc comment replace `Four panels below the fold -- sector heat, correlated clusters, the` / `drawdown throttle, scan health -- carry over from the Jinja page. The specs` / `are silent on all four, and silence is not a decision to drop them.` with `Three panels below the fold -- sector heat, correlated clusters, the` / `drawdown throttle -- carry over from the Jinja page. The specs are silent on` / `all three, and silence is not a decision to drop them. Scan health and the` / `data source moved to System → Providers (v195 §5.1).`; in the `host` comment replace `(heat, sectors, clusters, scan health)` with `(heat, sectors, clusters)`; in the section-head comment replace `the killswitch and` / `scan-health panels below stay outside the sb-async wrap (see` / `its comment) and have no error surface of their own -- this is` / `the only place their staleness shows.` with `the killswitch panel` / `below stays outside the sb-async wrap (see its comment) and has` / `no error surface of its own -- this is the only place its` / `staleness shows.`; in the `<!-- heat, exposure, sector/cluster breakdown` comment replace `The killswitch panel above and the scan-health` / `panel below stay outside it deliberately: the killswitch is an` with `The killswitch panel above stays outside it` / `deliberately: it is an`, and delete `, and scan health answers "is the scanner` / `healthy", a question that has nothing to do with whether risk` / `exposure happens to be zero right now. Both already degrade` and replace it with `. It already degrades`, so the sentence reads `… to stop the bot opening anything new). It already degrades gracefully via the store's own null-safe defaults while the first fetch is in flight.`

After the edits, `git grep -n -i "scan health\|scanLatestS\|dataSources\|sparkline" -- frontend/src/app/workspaces/risk/risk.ts frontend/src/app/stores/risk.store.ts` prints nothing.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/system/providers-tab.spec.ts --include src/app/workspaces/system/system.spec.ts --include src/app/workspaces/system/scan-tab.spec.ts --include src/app/stores/risk.store.spec.ts --include src/app/workspaces/risk/risk.spec.ts --include src/app/stores/system.store.spec.ts --include src/app/workspaces/system/provider-health-panel.spec.ts --include src/app/workspaces/system/swallowed-errors-panel.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: PASS, `0 failed`, `0 xfailed`. If the panel-order case finds an extra `h2`, one of the two v148 panels renders a heading inside its body: compare against `provider-health-panel.ts` / `swallowed-errors-panel.ts` and match on `sb-panel > section > header h2` (the panel's own header) instead, in both new specs. If the `/risk`-down case finds no alert, `riskError` is not read in the template. If `system.spec.ts`'s navigation case sees no call, the `[role="tab"]` button's click is not reaching `goToTab`: check `(activeChange)="goToTab($event)"` is still on `sb-tab-bar`. If a `system.store.spec.ts` case reports an unmatched `/system/health` request, a `boot` helper still expects it or `resolveScan` still forks it.

Then the whole frontend and lint:

```bash
npm --prefix "$WT/frontend" test -- --watch=false
npm --prefix "$WT/frontend" run lint
```

Expected: green.

- [ ] **Step 8: Check it in a browser**

One Playwright pass against `ng serve`, logged in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script and never printed; enter at `/app/dashboard`, then click through the rail to System. At 1440, 768 and 390: the tab bar reads Scan · Providers · Settings · Logs with Settings selected; clicking Providers sets `?tab=providers` and shows Data providers, Data source (Alpaca feed and fallback rate, or `yfinance only`), Scan health (last duration and the sparkline) and Swallowed errors, nothing overflowing (`document.documentElement.scrollWidth <= innerWidth`); the Scan tab shows the scan status, the commands and Bot process only; Risk shows no Scan health or Data source panel. Save the PNGs under the session scratchpad.

- [ ] **Step 9: Close**

Close: standard (test: `frontend/src/app/workspaces/system/providers-tab.spec.ts`), plus `frontend/src/app/workspaces/system/system.spec.ts`, `frontend/src/app/workspaces/system/scan-tab.spec.ts`, `frontend/src/app/stores/system.store.spec.ts`, `frontend/src/app/stores/risk.store.spec.ts` and `frontend/src/app/workspaces/risk/risk.spec.ts` in step 2 of the close. One frontend commit:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign
git -C "$WT" add frontend/src/app/workspaces/system/providers-tab.ts frontend/src/app/workspaces/system/providers-tab.spec.ts frontend/src/app/workspaces/system/system.spec.ts frontend/src/app/workspaces/system/system.ts frontend/src/app/workspaces/system/scan-tab.ts frontend/src/app/workspaces/system/scan-tab.spec.ts frontend/src/app/stores/system.store.ts frontend/src/app/stores/system.store.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts
git -C "$WT" commit -m "feat(v195): System Providers tab; scan health and data source leave Risk (V195-23)" -m "Spec §5.1: System's bar reads Scan, Providers, Settings, Logs (Settings still the landing tab). sb-providers-tab holds Data providers and Swallowed errors (from the Scan tab) and Data source and Scan health (from Risk), each read failing on its own. The Scan tab keeps the status, commands and bot process and no longer reads /system/health; RiskStore drops scanDurations, scanLatestS, scanSlowdown and dataSources; Risk shows only risk. An unknown latest duration reads as a bare dash, not a dash with a unit." -m "Moved, not dropped: the three v106 data-source cases go from risk.spec.ts to providers-tab.spec.ts, and the three v148 health-resolver cases in system.store.spec.ts are repointed from the Scan resolver to the Providers resolver. system.spec.ts is new (tab order, landing tab, URL)." -m "<Co-Authored-By trailer from the session's attribution reminder>"
```

