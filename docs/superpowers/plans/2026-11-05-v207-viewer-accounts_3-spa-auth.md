# v207 part 3 — SPA auth: session role, admin guard, `*ifAdmin`, nav + badge, 403 toast, preferences no-save, write-call inventory

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md) (§ SPA, § Testing "Frontend")
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V207-9..V207-12 (index group E). V207-9 goes first; V207-10, V207-11 and V207-12 touch disjoint files and may run in parallel after it. None of them needs the backend tasks merged: they consume only the HTTP contracts the ledger fixes — `GET|POST /api/v1/session` body `{authenticated, username, role}` with `role: "admin" | "viewer" | null` (V207-4b) and the 403 body `{"error": {"code": "forbidden", "message": "Read-only account."}}` (V207-5). `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command names that path, never the main tree. Frontend specs run narrow: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include <spec>` (the path after `--include` is relative to `<wt>/frontend`). No task runs the full suite; no task here touches the database.

**One test idiom for every spec below.** After V207-9, `SessionStore.isAdmin()` is false until a session with `role: "admin"` has been booted, so any spec that renders a role-aware component against the *real* store sets the role directly — `patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' })` (`patchState` from `@ngrx/signals`, `unprotected` from `@ngrx/signals/testing`; precedent `workspaces/trades/trades.spec.ts:124`). Specs that only need the guard's members keep a `useValue` stub, as `app.routes.spec.ts` does today. The parts after this one (V207-13..V207-17) use the same idiom.

## Review focus (this part)

1. **A `/session` body without `role`** (a stale cached response, or an older server answering during a rolling deploy): `role` resolves to `null`, `isAdmin()` is false, so the SPA fails closed — the viewer layout, never the admin one. Test in V207-9.
2. **A viewer deep-linking or bookmarking a System URL** (`/system?tab=users`, `/system/versions`, `/system/anything`): lands on `/dashboard`, never a blank outlet or a 403 burst. Test in V207-9.
3. **A role change inside one page life** (a viewer session expiring, then an admin signing in on the same tab without a reload): `*ifAdmin` content appears and disappears with the signal, and `expire()` clears the role. Tests in V207-9.
4. **A burst of 403s** (a page that fires several admin-only reads at once for a viewer): one "Read-only account" toast on screen, not a stack. Test in V207-11.
5. **A 64-character username on a 390 px phone**: the badge keeps the bar from overflowing (compact "Read-only" text on a phone, ellipsis elsewhere, the full name in `aria-label`/`title`). Test in V207-10.

# Phase E — SPA auth

### Task V207-9: SPA: `role` on Identity/SessionStore, `adminGuard`, `*ifAdmin`

**Model:** sonnet — three small Angular primitives over one new signal, with every assertion spelled out; the one judgement (fail closed on a missing `role`) is made here.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`Identity`, :84-87)
- Modify: `frontend/src/app/stores/session.store.ts`; `frontend/src/app/stores/session.store.spec.ts`
- Create: `frontend/src/app/auth/admin.guard.ts`; `frontend/src/app/auth/admin.guard.spec.ts`
- Create: `frontend/src/app/auth/if-admin.directive.ts`; `frontend/src/app/auth/if-admin.directive.spec.ts`
- Modify: `frontend/src/app/app.routes.ts` (`system/versions` ~:117 and `system` ~:125); `frontend/src/app/app.routes.spec.ts`

**Interfaces:**
- Consumes: `GET /api/v1/session` and `POST /api/v1/session` body `{authenticated: boolean, username: string | null, role: "admin" | "viewer" | null}` (V207-4b); existing `authGuard` (`shell/auth.guard.ts:21`), `SessionStore` (`stores/session.store.ts`).
- Produces (ledger contract — later tasks import exactly these):
  - `models.ts`: `export type Role = 'admin' | 'viewer';` and `Identity { authenticated: boolean; username: string | null; role: Role | null }`.
  - `SessionStore`: state key `role: Role | null` (initial `null`), so `role: Signal<Role | null>` is the state signal; computed `isAdmin: Signal<boolean>` = `status() === 'authenticated' && role() === 'admin'`, `isViewer: Signal<boolean>` = `status() === 'authenticated' && role() === 'viewer'`.
  - `auth/admin.guard.ts`: `export const adminGuard: CanMatchFn` — `true` for an admin, otherwise `inject(Router).createUrlTree(['/dashboard'])`.
  - `auth/if-admin.directive.ts`: `export class IfAdminDirective`, selector `[ifAdmin]`, standalone, used as `*ifAdmin` with no expression; renders its template once while `isAdmin()` is true and clears it when false, reacting to the signal.

- [ ] **Step 1: Add `role` to the session spec (failing)**

In `frontend/src/app/stores/session.store.spec.ts`, change the `boot` helper and every existing `/api/v1/session` flush to carry `role` (the spec's one deliberate exact-shape change):

```ts
  const boot = (
    authenticated: boolean,
    username: string | null = 'admin',
    role: 'admin' | 'viewer' | null = authenticated ? 'admin' : null,
  ) => {
    const done = store.boot();
    backend.expectOne('/api/v1/session').flush({ authenticated, username, role });
    return done;
  };
```

Every literal `.flush({ authenticated: true, username: 'admin' })` (today :94, :164) and `.flush({ authenticated, username: 'admin' })` (:257) gains `role: 'admin'`; `.flush({ authenticated: false, username: null })` (:222) gains `role: null`. Then append:

```ts
  /* -- v207: role ------------------------------------------------------- */

  describe('role (v207)', () => {
    const postSession = (req: { method: string; url: string }) =>
      req.method === 'POST' && req.url === '/api/v1/session';

    it('is admin for the .env account', async () => {
      await boot(true, 'admin', 'admin');
      expect(store.role()).toBe('admin');
      expect(store.isAdmin()).toBe(true);
      expect(store.isViewer()).toBe(false);
    });

    it('is viewer for a database account', async () => {
      await boot(true, 'viewer1', 'viewer');
      expect(store.role()).toBe('viewer');
      expect(store.isAdmin()).toBe(false);
      expect(store.isViewer()).toBe(true);
      expect(store.displayName()).toBe('viewer1');
    });

    it('fails closed when the body carries no role', async () => {
      const done = store.boot();
      backend.expectOne('/api/v1/session').flush({ authenticated: true, username: 'admin' });
      await done;
      expect(store.isAuthenticated()).toBe(true);
      expect(store.role()).toBeNull();
      expect(store.isAdmin()).toBe(false);
      expect(store.isViewer()).toBe(false);
    });

    it('ignores a role on an anonymous answer', async () => {
      await boot(false, null, 'admin');
      expect(store.role()).toBeNull();
      expect(store.isAdmin()).toBe(false);
    });

    it('has no role before boot or when the admin is unreachable', async () => {
      expect(store.role()).toBeNull();
      const done = store.boot();
      backend.expectOne('/api/v1/session').error(new ProgressEvent('error'), { status: 0 });
      await done;
      expect(store.role()).toBeNull();
    });

    it('takes the role from a successful login', async () => {
      const done = store.login('viewer1', 'viewer-password-1');
      backend.expectOne(postSession).flush({ authenticated: true, username: 'viewer1', role: 'viewer' });
      await done;
      expect(store.isViewer()).toBe(true);
    });

    it('clears the role on a rejected login', async () => {
      await boot(true, 'admin', 'admin');
      const done = store.login('admin', 'wrong');
      backend.expectOne(postSession).flush(
        { error: { code: 'auth', message: 'Invalid username or password.' } },
        { status: 401, statusText: 'Unauthorized' },
      );
      await done;
      expect(store.role()).toBeNull();
    });

    it('clears the role when the session expires', async () => {
      await boot(true, 'viewer1', 'viewer');
      store.expire('/trades');
      expect(store.role()).toBeNull();
      expect(store.isViewer()).toBe(false);
    });
  });
```

- [ ] **Step 2: Write the guard spec** — `frontend/src/app/auth/admin.guard.spec.ts`

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Route, Router, UrlTree, provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { adminGuard } from './admin.guard';

function run(isAdmin: boolean): boolean | UrlTree {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      { provide: SessionStore, useValue: { isAdmin: signal(isAdmin) } },
    ],
  });
  return TestBed.runInInjectionContext(() => adminGuard({} as Route, [])) as boolean | UrlTree;
}

describe('adminGuard (v207)', () => {
  it('lets the admin match', () => {
    expect(run(true)).toBe(true);
  });

  it('sends anyone else to the dashboard with a UrlTree, not a bare false', () => {
    const result = run(false);
    expect(result).toBeInstanceOf(UrlTree);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/dashboard');
  });
});
```

- [ ] **Step 3: Write the directive spec** — `frontend/src/app/auth/if-admin.directive.spec.ts`

```ts
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import type { Role } from '../api/models';
import { SessionStore } from '../stores/session.store';
import { IfAdminDirective } from './if-admin.directive';

@Component({
  imports: [IfAdminDirective],
  template: `<button *ifAdmin type="button" class="write">Close</button><p class="read">Book</p>`,
})
class Host {}

describe('IfAdminDirective (v207)', () => {
  let fixture: ComponentFixture<Host>;
  const el = () => fixture.nativeElement as HTMLElement;

  const as = (role: Role | null) => {
    patchState(unprotected(TestBed.inject(SessionStore)), {
      status: role ? 'authenticated' : 'anonymous', username: role ? 'someone' : null, role,
    });
    fixture.detectChanges();
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(Host);
  });

  it('renders the control for the admin', () => {
    as('admin');
    expect(el().querySelectorAll('button.write')).toHaveLength(1);
  });

  it('renders nothing for a viewer, and leaves the rest of the page alone', () => {
    as('viewer');
    expect(el().querySelector('button.write')).toBeNull();
    expect(el().querySelector('p.read')).not.toBeNull();
  });

  it('renders nothing without a role', () => {
    as(null);
    expect(el().querySelector('button.write')).toBeNull();
  });

  it('follows the role as it changes, never rendering twice', () => {
    as('viewer');
    as('admin');
    as('admin');
    expect(el().querySelectorAll('button.write')).toHaveLength(1);
    as('viewer');
    expect(el().querySelector('button.write')).toBeNull();
  });
});
```

- [ ] **Step 4: Extend the routing spec** — `frontend/src/app/app.routes.spec.ts`

Change `configure` to stub both guard members (functions, so a mounted workspace's `*ifAdmin` reads the same stub):

```ts
function configure(authenticated: boolean, isAdmin = authenticated) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideLocationMocks(),
      { provide: SessionStore, useValue: { isAuthenticated: () => authenticated, isAdmin: () => isAdmin } },
    ],
  });
}
```

The other stub (~:215, `{ isAuthenticated: () => true }`) gains `isAdmin: () => true`. Import `adminGuard` from `./auth/admin.guard` and append:

```ts
describe('routing, viewer (v207)', () => {
  beforeEach(() => configure(true, false));

  it.each(['/system', '/system?tab=users', '/system?tab=settings', '/system/versions', '/system/anything'])(
    'sends %s to the dashboard', async (url) => {
      await RouterTestingHarness.create(url);
      expect(TestBed.inject(Router).url).toBe('/dashboard');
    },
  );

  it.each(['/dashboard', '/trades', '/trades/calendar', '/watchlist', '/risk', '/insights/analytics'])(
    'still mounts %s', async (url) => {
      const harness = await RouterTestingHarness.create(url);
      expect(TestBed.inject(Router).url).toBe(url);
      expect(harness.routeNativeElement).not.toBeNull();
    },
  );
});

describe('route guards (v207)', () => {
  it('puts adminGuard after authGuard on every system route, and on nothing else', () => {
    const system = routes.filter((route) => route.path?.startsWith('system'));
    expect(system.map((route) => route.path)).toEqual(['system/versions', 'system']);
    expect(routes.filter((route) => route.canMatch?.includes(adminGuard))).toEqual(system);
    for (const route of system) expect(route.canMatch).toEqual([authGuard, adminGuard]);
  });
});
```

- [ ] **Step 5: Run the four specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/session.store.spec.ts --include src/app/auth/admin.guard.spec.ts --include src/app/auth/if-admin.directive.spec.ts --include src/app/app.routes.spec.ts`
Expected: FAIL — `store.role is not a function`, cannot resolve `./admin.guard` / `./if-admin.directive`, and the viewer `/system` cases stay on `/system`.

- [ ] **Step 6: Implement**

- `models.ts`: `export type Role = 'admin' | 'viewer';` above `Identity`, and `role: Role | null;` inside it with a one-line doc comment ("v207: who the session is; null when anonymous, and when an older server omits it, so the SPA shows the viewer layout").
- `session.store.ts`: `role: Role | null` in `SessionState` (doc comment: presentation only, the server is the boundary) and `role: null` in `initial`. One module-level helper `fromIdentity(identity: Identity): Pick<SessionState, 'status' | 'username' | 'role'>` returning `{ status: identity.authenticated ? 'authenticated' : 'anonymous', username: identity.username, role: identity.authenticated ? identity.role ?? null : null }`, used by both the `boot()` and `login()` success paths; every other `patchState` that sets `username: null` (boot catch, login catch, `logout`, `expire`) also sets `role: null`. In `withComputed` destructure `status`, `username`, `role` and add `isAdmin` and `isViewer` exactly as the Interfaces block states.
- `auth/admin.guard.ts` (doc comment: a `UrlTree`, not `false`, because a `false` falls through to `**`, which is `/dashboard` only by accident; listed after `authGuard`, so an anonymous visitor still gets `authGuard`'s answer first):

```ts
export const adminGuard: CanMatchFn = () =>
  inject(SessionStore).isAdmin() ? true : inject(Router).createUrlTree(['/dashboard']);
```

- `auth/if-admin.directive.ts`: `@Directive({ selector: '[ifAdmin]' })`; the constructor injects `SessionStore`, `TemplateRef<unknown>` and `ViewContainerRef` and registers one `effect()` that calls `createEmbeddedView(template)` when `isAdmin()` is true and the container is empty, and `clear()` when it is false. Doc comment: hides, never disables (Global Constraints); presentation only; no `else` branch — a control with a read-only stand-in (the trade note, V207-13) uses `@if (session.isAdmin()) { … } @else { … }` in its own template.
- `app.routes.ts`: `system/versions` and `system` both get `canMatch: [authGuard, adminGuard]` and a one-line comment ("v207: System is admin-only; a viewer is sent to the Dashboard"). No new route: the Users page is `/system?tab=users` (V207-17), served by the `system` route.

- [ ] **Step 7: Run the specs to see them pass**

Run: the Step 5 command.
Expected: PASS, `0 failed`.

- [ ] **Step 8: Commit**

```bash
cd "<wt>" && git add frontend/src/app/api/models.ts frontend/src/app/stores/session.store.ts frontend/src/app/stores/session.store.spec.ts frontend/src/app/auth/admin.guard.ts frontend/src/app/auth/admin.guard.spec.ts frontend/src/app/auth/if-admin.directive.ts frontend/src/app/auth/if-admin.directive.spec.ts frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts
git commit -m "feat(v207): session role, adminGuard on System routes, *ifAdmin directive (V207-9)"
```

### Task V207-10: Nav hiding (rail, More sheet, palette) + read-only badge

**Model:** sonnet — one filter applied at three known consumers plus a presentational badge; the layout decisions for three widths are fixed below.

**Files:**
- Modify: `frontend/src/app/shell/nav.ts` (`NavEntry`, `NAV_ENTRIES` System entry); `frontend/src/app/shell/nav.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts` (`railWork`/`railFoot` :105-106, imports); `frontend/src/app/shell/shell.html` (rail :13-37, `.status-cluster` :68-71); `frontend/src/app/shell/shell.spec.ts`
- Modify: `frontend/src/app/shell/more-sheet.ts` (`MoreSheet.groups` :140 and its template loop :63); `frontend/src/app/shell/more-sheet.spec.ts`
- Modify: `frontend/src/app/shell/palette/palette-items.ts` (`pageItems` :91); `frontend/src/app/shell/palette/command-palette.ts` (`pages` :221, `items` :223-228); `frontend/src/app/shell/palette/palette-items.spec.ts`; `frontend/src/app/shell/palette/command-palette.spec.ts`
- Create: `frontend/src/app/shell/read-only-badge.ts`; `frontend/src/app/shell/read-only-badge.spec.ts`

**Interfaces:**
- Consumes: `SessionStore.isAdmin()`, `.isViewer()`, `.displayName()` (V207-9; `displayName` exists today).
- Produces:
  - `nav.ts`: `NavEntry.adminOnly?: boolean` (true on System only); `export function navEntriesFor(isAdmin: boolean, entries: readonly NavEntry[] = NAV_ENTRIES): readonly NavEntry[]` — `entries` unchanged for an admin, without the `adminOnly` entries otherwise.
  - `palette-items.ts`: `pageItems(entries = NAV_ENTRIES, tabs: readonly PaletteItem[] = TAB_PAGES)`; `export function pageItemsFor(isAdmin: boolean): PaletteItem[]` (admin: `pageItems()`; viewer: no `/system…` route and no Analytics `tuning` tab).
  - `read-only-badge.ts`: `ReadOnlyBadge`, selector `sb-read-only-badge`, inputs `username = input.required<string>()`, `compact = input(false)`.

**Layout (three widths).** The badge sits first in the top bar's `.status-cluster`, before the alarm and killswitch chips, rendered only `@if (session.isViewer())`. Desktop 1440 and tablet 820: text `Read-only · <username>`, the name truncated with an ellipsis past `max-width: 16rem`. Phone 390 (`[compact]="isPhone()"`): text `Read-only` only, so a 64-character name cannot push the bar into overflow; the full `Read-only account, signed in as <username>` is in `title` and in a visually hidden span on every width. It is a non-interactive label (no link, no focus stop), styled like the killswitch chip's border/radius/size tokens with `--text-secondary`, so it needs no 44 px target. The rail on tablet/desktop drops its `System` foot list for a viewer (the `ul.rail-foot` is not rendered at all, and `.rail-version` takes `margin-top: auto` so the version hint stays at the foot); the phone tab bar never held System; the More sheet lists Risk and Insights only.

- [ ] **Step 1: Write the failing pure specs**

Append to `frontend/src/app/shell/nav.spec.ts` (import `navEntriesFor`):

```ts
describe('navEntriesFor (v207)', () => {
  it('marks System, and only System, admin-only', () => {
    expect(paths(NAV_ENTRIES.filter((entry) => entry.adminOnly))).toEqual(['/system']);
  });

  it('keeps every destination for the admin, the same array', () => {
    expect(navEntriesFor(true)).toBe(NAV_ENTRIES);
  });

  it('drops System for a viewer and keeps the rest in rail order', () => {
    expect(paths(navEntriesFor(false))).toEqual(['/dashboard', '/watchlist', '/trades', '/risk', '/insights']);
  });

  it('filters the entries it is given', () => {
    expect(navEntriesFor(false, [])).toEqual([]);
    expect(paths(navEntriesFor(false, NAV_ENTRIES.slice(-1)))).toEqual([]);
  });
});
```

Append to `frontend/src/app/shell/palette/palette-items.spec.ts` (import `pageItemsFor`, `pageItems`):

```ts
describe('pageItemsFor (v207)', () => {
  const routesOf = (items: PaletteItem[]) =>
    items.map((item) => `${item.route}${item.queryParams ? `?tab=${item.queryParams['tab']}` : ''}`);

  it('is every page for the admin', () => {
    expect(pageItemsFor(true)).toEqual(pageItems());
  });

  it('offers a viewer no System page, no System tab and no Tuning tab', () => {
    const routes = routesOf(pageItemsFor(false));
    expect(routes.filter((route) => route.startsWith('/system'))).toEqual([]);
    expect(routes).not.toContain('/insights/analytics?tab=tuning');
    expect(routes).toContain('/insights/analytics?tab=partials');
    expect(routes).toContain('/watchlist?tab=earnings');
    expect(routes).toContain('/trades/calendar');
  });
});
```

(`PaletteItem` is already exported by `palette-items.ts`; import it if the spec does not.)

- [ ] **Step 2: Write the badge spec** — `frontend/src/app/shell/read-only-badge.spec.ts`

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ReadOnlyBadge } from './read-only-badge';

describe('ReadOnlyBadge (v207)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(username: string, compact = false): HTMLElement {
    const fixture = TestBed.createComponent(ReadOnlyBadge);
    fixture.componentRef.setInput('username', username);
    fixture.componentRef.setInput('compact', compact);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const visible = (el: HTMLElement) => el.querySelector('[aria-hidden="true"]')!.textContent!.trim();
  const spoken = (el: HTMLElement) => el.querySelector('.sr-only')!.textContent!.trim();

  it('reads "Read-only · <name>" on a tablet or desktop', () => {
    const el = render('viewer1');
    expect(visible(el)).toBe('Read-only · viewer1');
    expect(spoken(el)).toBe('Read-only account, signed in as viewer1');
    expect(el.querySelector('.badge')!.getAttribute('title')).toBe('Read-only account, signed in as viewer1');
  });

  it('drops the name from the visible text on a phone, never from the spoken one', () => {
    const name = 'a'.repeat(64);
    const el = render(name, true);
    expect(visible(el)).toBe('Read-only');
    expect(spoken(el)).toBe(`Read-only account, signed in as ${name}`);
  });

  it('is a label, not a control: no link, no button, no tab stop', () => {
    const el = render('viewer1');
    expect(el.querySelector('a, button, [tabindex]')).toBeNull();
  });

  it('truncates a long name rather than growing the bar', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/read-only-badge.ts'), 'utf8');
    expect(source).toMatch(/max-width:\s*16rem/);
    expect(source).toMatch(/text-overflow:\s*ellipsis/);
    expect(source).toMatch(/white-space:\s*nowrap/);
  });
});
```

- [ ] **Step 3: Add viewer cases to the component specs (failing)**

All three component specs render against the real `SessionStore`, which now has no role until one is set. At **every** place that calls `TestBed.configureTestingModule` in `shell.spec.ts` (four today: ~:109, ~:381, ~:516, ~:613), `more-sheet.spec.ts` (:49) and `command-palette.spec.ts` (:50), add right after it, before any `createComponent`:

```ts
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
```

so every existing assertion keeps describing the admin. (In `more-sheet.spec.ts` the `createComponent` call sits in the same `beforeEach`: put the line between the two. Imports: `patchState` from `@ngrx/signals`, `unprotected` from `@ngrx/signals/testing`, `SessionStore` from `../stores/session.store` or `../../stores/session.store`.)

Then add the viewer cases. `shell.spec.ts`, inside the describe that has `mount()` (~:516):

```ts
  const asViewer = (name = 'viewer1') =>
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: name, role: 'viewer' });

  it('drops the System foot list for a viewer and keeps the version hint at the foot (v207)', async () => {
    asViewer();
    const { el } = await mount();
    const rail = el.querySelector('nav.rail')!;
    const lists = [...rail.querySelectorAll(':scope > ul.nav')];
    expect(lists.map((ul) => ul.className)).toEqual(['nav rail-work']);
    expect([...lists[0].querySelectorAll('a.rail-link')].map(labelOf))
      .toEqual(['Dashboard', 'Watchlist', 'Trades', 'Risk', 'Insights']);
    expect(rail.querySelector('a[href="/system"]')).toBeNull();
    const version = lists[0].nextElementSibling as HTMLElement;
    expect(version.matches('.rail-version')).toBe(true);
    expect(version.style.marginTop).toBe('auto');
  });

  it('shows the read-only badge first in the status cluster for a viewer only (v207)', async () => {
    asViewer('viewer1');
    const { el } = await mount();
    const cluster = el.querySelector('.status-cluster')!;
    expect(cluster.firstElementChild!.tagName.toLowerCase()).toBe('sb-read-only-badge');
    expect(cluster.querySelector('sb-read-only-badge')!.textContent).toContain('Read-only · viewer1');
    expect(cluster.querySelector('sb-killswitch-chip')).not.toBeNull();
  });

  it('shows no badge to the admin (v207)', async () => {
    const { el } = await mount();
    expect(el.querySelector('sb-read-only-badge')).toBeNull();
  });
```

`more-sheet.spec.ts`, inside `describe('MoreSheet …')` — the role is read through a signal, so flipping it after creation is enough:

```ts
  it('lists only Risk and Insights for a viewer (v207)', () => {
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'viewer' });
    open();
    expect([...el.querySelectorAll('.group-label')].map((n) => n.textContent!.trim())).toEqual(['Risk', 'Insights']);
    expect([...el.querySelectorAll('a.page')].map((a) => a.getAttribute('href')))
      .toEqual(['/risk', '/insights/analytics', '/insights/research', '/insights/reports']);
  });
```

`command-palette.spec.ts`, beside the existing `/system?tab=logs` test (~:184), using that file's own open-and-type helpers:

```ts
  it('offers a viewer no System or Tuning page (v207)', async () => {
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'viewer' });
    const { fixture, el } = await mount();
    for (const query of ['system', 'health', 'versions', 'scan', 'providers', 'logs', 'tuning']) {
      await type(fixture, el, query);
      for (const option of options(el)) {
        expect(option.querySelector('.label')!.textContent!.trim()).not.toMatch(/^(Health|Versions|Scan|Providers|Logs|Tuning)$/);
      }
    }
    await type(fixture, el, 'partials');
    expect(optionLabels(el)).toContain('Partials');
  });
```

(`mount`, `type`, `options` and `optionLabels` are the file's own helpers, :70-93.)

- [ ] **Step 4: Run the six specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/shell/nav.spec.ts --include src/app/shell/palette/palette-items.spec.ts --include src/app/shell/read-only-badge.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/more-sheet.spec.ts --include src/app/shell/palette/command-palette.spec.ts`
Expected: FAIL — `navEntriesFor`/`pageItemsFor` not exported, `./read-only-badge` missing, the viewer cases still see System. The admin cases pass.

- [ ] **Step 5: Implement**

- `nav.ts`: `adminOnly?: boolean` on `NavEntry` (doc: "v207: hidden from viewers; the server refuses its API anyway"); `adminOnly: true` on the System entry; `navEntriesFor` returns `entries` itself when `isAdmin`, else `entries.filter((entry) => !entry.adminOnly)`. Update the `NAV_ENTRIES` doc comment to say every consumer reads it through `navEntriesFor`.
- `shell.ts`: `railWork` and `railFoot` become `computed(() => navEntriesFor(this.session.isAdmin()).filter(…))` with today's predicates; import `navEntriesFor` and `ReadOnlyBadge` (add it to `imports`).
- `shell.html`: `@for (entry of railWork(); …)`, and the whole `<ul class="nav rail-foot" aria-label="System">` wrapped in `@if (railFoot().length) { … }` iterating `railFoot()`; on `.rail-version` add `[style.margin-top]="railFoot().length ? null : 'auto'"` (the foot list carries `margin-top: auto` in `shell.css:54-58`; without it the hint must take the push itself). In `.status-cluster`, first child: `@if (session.isViewer()) { <sb-read-only-badge [username]="session.displayName()" [compact]="isPhone()" /> }`, with an HTML comment naming v207 and the three-width rule above.
- `more-sheet.ts`: inject `SessionStore`; `groups = computed(() => morePageGroups(navEntriesFor(this.session.isAdmin())))`; the template loops `groups()`. Update the `morePageGroups` doc comment ("System … for the admin only").
- `palette-items.ts`: `pageItems` takes `tabs: readonly PaletteItem[] = TAB_PAGES` and spreads `tabs` instead of `TAB_PAGES`; private `isAdminOnlyPage(item: PaletteItem): boolean` = route is `/system` or starts with `/system/`, or route is `/insights/analytics` with `queryParams?.['tab'] === 'tuning'`; `pageItemsFor(isAdmin)` = `isAdmin ? pageItems() : pageItems(navEntriesFor(false), TAB_PAGES.filter((item) => !isAdminOnlyPage(item)))`.
- `command-palette.ts`: inject `SessionStore`; `pages = computed(() => pageItemsFor(this.session.isAdmin()))`; `items` spreads `this.pages()`.
- `read-only-badge.ts`: standalone, `ChangeDetectionStrategy.OnPush`, no imports. Template: `<span class="badge" [attr.title]="spoken()"><span aria-hidden="true">{{ visible() }}</span><span class="sr-only">{{ spoken() }}</span></span>` where `visible = computed(() => this.compact() ? 'Read-only' : \`Read-only · ${this.username()}\`)` and `spoken = computed(() => \`Read-only account, signed in as ${this.username()}\`)`. Styles: `:host { display: inline-flex; min-width: 0; }`; `.badge` with `display: inline-block; max-width: 16rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 2px var(--space-6); border: 1px solid var(--border-strong); border-radius: var(--chip-radius); color: var(--text-secondary); font-size: var(--text-chip);`; `.sr-only` the standard clip pattern (`position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap;`). Doc comment: presentation only, and why the phone text is shorter.

- [ ] **Step 6: Run the six specs to see them pass**

Run: the Step 4 command.
Expected: PASS, `0 failed`.

- [ ] **Step 7: Check the three widths**

Needs V207-1..V207-4b merged in `<wt>` (a viewer must be able to sign in). Follow `docs/claude/ui-design.md` § layout audit: `/replicate-prod-db`, `cd "<wt>/frontend" && npm run build`, `cd "<wt>" && python admin_ui.py`, sign in with `node frontend/scripts/browse.mjs login --base http://localhost:1234`, then `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` must exit 0 (admin shell unchanged). For the viewer, create a throwaway account in the local replica, check, and delete it:

```bash
cd "<wt>" && python - <<'EOF'
from swingbot.admin import principals
from swingbot.core.db.repositories.admin_users import admin_users_repo
admin_users_repo().create_user("v207-check-" + "x" * 53, principals.hash_password("v207-check-password"))
EOF
```

With a Playwright script in the scratchpad (never in the repo; the password above is a local throwaway, not a `.env` value), sign in through the web login as that 64-character user and, at 390×844, 820×1180 and 1440×900 on `/dashboard`, assert: `.topbar` `scrollWidth <= clientWidth`; `sb-read-only-badge` visible and fully inside the viewport; on 390 its visible text is `Read-only`; on 820/1440 no `a[href="/system"]` in `nav.rail`; on 390 the More sheet (tap the More tab) lists Risk and Insights only. Keep the three screenshots in the scratchpad for the reviewer. Then remove the account: `python -c "from swingbot.core.db.repositories.admin_users import admin_users_repo as r; [r().delete_user(u['id']) for u in r().list_users() if u['username'].startswith('v207-check-')]"`. If V207-4b is not merged yet, say so in the task result and run this step once it is, before review.

- [ ] **Step 8: Commit**

```bash
cd "<wt>" && git add frontend/src/app/shell/nav.ts frontend/src/app/shell/nav.spec.ts frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.spec.ts frontend/src/app/shell/more-sheet.ts frontend/src/app/shell/more-sheet.spec.ts frontend/src/app/shell/palette/palette-items.ts frontend/src/app/shell/palette/palette-items.spec.ts frontend/src/app/shell/palette/command-palette.ts frontend/src/app/shell/palette/command-palette.spec.ts frontend/src/app/shell/read-only-badge.ts frontend/src/app/shell/read-only-badge.spec.ts
git commit -m "feat(v207): hide System from viewers in rail, More sheet and palette; read-only badge (V207-10)"
```

### Task V207-11: 403 toast interceptor + preferences no-save for viewers

**Model:** sonnet — one interceptor and one store guard, each with its position and exact behaviour fixed below.

**Files:**
- Create: `frontend/src/app/auth/forbidden.interceptor.ts`; `frontend/src/app/auth/forbidden.interceptor.spec.ts`
- Modify: `frontend/src/app/app.config.ts` (the `withInterceptors([...])` array, :82, and its ordering comment above it)
- Modify: `frontend/src/app/stores/preferences.store.ts`; `frontend/src/app/stores/preferences.store.spec.ts`

**Interfaces:**
- Consumes: `SessionStore.isAdmin()` (V207-9); `ApiError` (`api/api-error.ts`, `code`/`status`); `errorInterceptor` (`api/interceptors.ts:40`); `ToastService.show(message, kind, ms)` and `.toasts()` (`shell/toast.service.ts`); the v1 403 body `{"error": {"code": "forbidden", "message": "Read-only account."}}` (V207-5).
- Produces:
  - `export const FORBIDDEN_TOAST = 'Read-only account';`
  - `export const forbiddenInterceptor: HttpInterceptorFn` — on an `ApiError` with `code === 'forbidden'` whose request URL does not end in `/system/preferences`, shows `FORBIDDEN_TOAST` as a `'warn'` toast unless one with that message is already on screen; always rethrows the same error. Array position: directly after `loadingInterceptor`, before `errorInterceptor` (so on the way back it runs after `errorInterceptor` has built the `ApiError`).
  - `PreferencesStore`: unchanged public surface; never calls `api.savePreferences` unless `SessionStore.isAdmin()` is true at the moment the write would fire.

- [ ] **Step 1: Write the interceptor spec** — `frontend/src/app/auth/forbidden.interceptor.spec.ts`

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/api-error';
import { errorInterceptor } from '../api/interceptors';
import { ToastService } from '../shell/toast.service';
import { FORBIDDEN_TOAST, forbiddenInterceptor } from './forbidden.interceptor';

const FORBIDDEN = { error: { code: 'forbidden', message: 'Read-only account.' } };

describe('forbiddenInterceptor (v207)', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let toasts: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([forbiddenInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    toasts = TestBed.inject(ToastService);
  });

  afterEach(() => vi.useRealTimers());

  function call(method: string, url: string, body: object, status: number): unknown {
    let caught: unknown = null;
    http.request(method, url, { body: {} }).subscribe({ error: (error: unknown) => (caught = error) });
    backend.expectOne(url).flush(body, { status, statusText: String(status) });
    return caught;
  }

  it('toasts "Read-only account" once and still hands the caller the ApiError', () => {
    const error = call('POST', '/api/v1/trades/7/close', FORBIDDEN, 403);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('forbidden');
    expect((error as ApiError).status).toBe(403);
    expect(toasts.toasts().map((t) => [t.message, t.kind])).toEqual([[FORBIDDEN_TOAST, 'warn']]);
    expect(FORBIDDEN_TOAST).toBe('Read-only account');
  });

  it.each(['PUT', 'GET'])('stays silent for a %s on /system/preferences', (method) => {
    const error = call(method, '/api/v1/system/preferences', FORBIDDEN, 403);
    expect((error as ApiError).code).toBe('forbidden');
    expect(toasts.toasts()).toEqual([]);
  });

  it('shows one toast for a burst, and toasts again once it has gone', () => {
    call('GET', '/api/v1/jobs', FORBIDDEN, 403);
    call('GET', '/api/v1/versions', FORBIDDEN, 403);
    call('DELETE', '/api/v1/trades/7', FORBIDDEN, 403);
    expect(toasts.toasts()).toHaveLength(1);
    vi.advanceTimersByTime(4000);
    expect(toasts.toasts()).toEqual([]);
    call('POST', '/api/v1/watchlist/tickers', FORBIDDEN, 403);
    expect(toasts.toasts()).toHaveLength(1);
  });

  it.each([
    [401, { error: { code: 'auth', message: 'Authentication required.' } }],
    [404, { error: { code: 'not_found', message: 'No such trade.' } }],
    [500, { error: { code: 'unavailable', message: 'Boom.' } }],
    [403, '<html>proxy says no</html>'],
  ])('ignores a %s that is not a v1 forbidden', (status, body) => {
    call('POST', '/api/v1/trades/7/close', body as object, status as number);
    expect(toasts.toasts()).toEqual([]);
  });

  it('passes a success through untouched', () => {
    let answer: unknown = null;
    http.get('/api/v1/dashboard').subscribe((value) => (answer = value));
    backend.expectOne('/api/v1/dashboard').flush({ ok: true });
    expect(answer).toEqual({ ok: true });
    expect(toasts.toasts()).toEqual([]);
  });
});

describe('app.config interceptor order (v207)', () => {
  it('puts forbiddenInterceptor after loading and before error', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/app.config.ts'), 'utf8');
    const list = /withInterceptors\(\[([^\]]*)\]\)/.exec(source)![1].split(',').map((name) => name.trim()).filter(Boolean);
    expect(list).toEqual([
      'loadingInterceptor', 'forbiddenInterceptor', 'errorInterceptor',
      'authInterceptor', 'routeRefreshInterceptor', 'freshInterceptor',
    ]);
  });
});
```

- [ ] **Step 2: Add viewer cases to the preferences spec (failing)**

In `frontend/src/app/stores/preferences.store.spec.ts`: import `patchState` (`@ngrx/signals`), `unprotected` (`@ngrx/signals/testing`), `SessionStore` (`./session.store`), `readFileSync`/`readdirSync`/`statSync` (`node:fs`) and `join`/`relative` (`node:path`). In the existing `beforeEach`, right after `configureTestingModule`, make the session the admin so every existing write test keeps its meaning:

```ts
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
```

Append inside `describe('PreferencesStore', …)`:

```ts
  /* -- v207: viewers read the admin's record and never write it ---------- */

  describe('as a viewer (v207)', () => {
    const asViewer = () =>
      patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'viewer1', role: 'viewer' });
    const noWrite = () => backend.expectNone((req) => req.method !== 'GET');

    it('still reads the shared record', () => {
      asViewer();
      loadWith({ tables: { trades: ['ticker'] } });
      expect(store.columns('trades')).toEqual(['ticker']);
    });

    it('keeps column changes in memory and never saves them', () => {
      asViewer();
      loadWith({ tables: { trades: ['ticker'] } });
      store.setColumns('trades', ['ticker', 'pnl']);
      store.setColumns('analytics', ['edge']);
      store.resetColumns('analytics');
      store.update((prefs) => ({ ...prefs, 'shell.zoom': 110 }));
      vi.advanceTimersByTime(WRITE_DEBOUNCE_MS * 3);
      noWrite();
      expect(store.columns('trades')).toEqual(['ticker', 'pnl']);
      expect(store.columns('analytics')).toBeNull();
      expect(store.values()).toMatchObject({ 'shell.zoom': 110 });
    });

    it('writes nothing on flush either', () => {
      asViewer();
      loadWith({});
      store.setColumns('trades', ['ticker']);
      store.flush();
      vi.advanceTimersByTime(WRITE_DEBOUNCE_MS * 3);
      noWrite();
    });

    it('checks the role when the write fires, not when it was queued', () => {
      loadWith({});
      store.setColumns('trades', ['ticker']);
      asViewer();
      vi.advanceTimersByTime(WRITE_DEBOUNCE_MS);
      noWrite();
    });
  });

  it('is the only caller of savePreferences outside the client itself (v207)', () => {
    const root = join(process.cwd(), 'src/app');
    const walk = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? walk(path) : [path];
    });
    const callers = walk(root)
      .filter((path) => path.endsWith('.ts') && !path.endsWith('.spec.ts'))
      .filter((path) => readFileSync(path, 'utf8').includes('savePreferences'))
      .map((path) => relative(root, path).replaceAll('\\', '/'))
      .sort();
    expect(callers).toEqual(['api/api-client.ts', 'stores/preferences.store.ts']);
  });
```

(`'shell.zoom'` is the flat dotted key the shell itself writes, `shell.ts:234`.)

- [ ] **Step 3: Run both specs to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/auth/forbidden.interceptor.spec.ts --include src/app/stores/preferences.store.spec.ts`
Expected: FAIL — `./forbidden.interceptor` missing; the viewer cases see a `PUT /api/v1/system/preferences`.

- [ ] **Step 4: Implement**

- `auth/forbidden.interceptor.ts`: `inject(ToastService)` at the top of the function (interceptors run in an injection context), then `next(req).pipe(catchError((error: unknown) => { … return throwError(() => error); }))`. The toast condition is one private predicate `shouldToast(error: unknown, url: string, toasts: ToastService): boolean` — `error instanceof ApiError && error.code === 'forbidden' && !url.endsWith('/system/preferences') && !toasts.toasts().some((t) => t.message === FORBIDDEN_TOAST)`; show with `toasts.show(FORBIDDEN_TOAST, 'warn')`. Doc comment: a fallback, not a normal path (controls are hidden); why preferences is exempt (spec § SPA: a viewer's layout tweak never toasts; the store guard below means it should never be sent anyway); why one toast per burst.
- `app.config.ts`: import `forbiddenInterceptor` from `./auth/forbidden.interceptor`; the array becomes `[loadingInterceptor, forbiddenInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor, freshInterceptor]`; add one line to the ordering comment above it: "forbidden sits outside error, so on the way back it sees the ApiError error built, and can branch on `code === 'forbidden'`".
- `preferences.store.ts`: `withMethods((store, api = inject(ApiClient), session = inject(SessionStore)) => …)`; one inner helper `write()` that returns at once unless `session.isAdmin()` and otherwise does today's `api.savePreferences(store.data()).subscribe({ error: () => undefined })`; `scheduleWrite`'s timer callback and `flush()` both call `write()` (so the role is read when the write fires). Extend the store's doc comment: viewers read the admin's shared record (spec Decision 5) and their edits last for this page life only.

- [ ] **Step 5: Run both specs to see them pass**

Run: the Step 3 command.
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit**

```bash
cd "<wt>" && git add frontend/src/app/auth/forbidden.interceptor.ts frontend/src/app/auth/forbidden.interceptor.spec.ts frontend/src/app/app.config.ts frontend/src/app/stores/preferences.store.ts frontend/src/app/stores/preferences.store.spec.ts
git commit -m "feat(v207): read-only 403 toast, viewers never save preferences (V207-11)"
```

### Task V207-12: Write-call inventory + completeness spec

**Model:** sonnet — a checked-in table transcribed from the brief's traced inventory, plus a source-scanning spec; no runtime code changes.

**Files:**
- Create: `frontend/src/app/auth/write-calls.ts`
- Create: `frontend/src/app/auth/write-calls.spec.ts`

**Interfaces:**
- Consumes: `frontend/src/app/api/api-client.ts` as source text (the spec reads it; nothing imports `ApiClient`).
- Produces (V207-16 adds its five Users rows here, all `'admin-route'`):
  - `export type WriteGate = 'public' | 'admin-route' | 'if-admin' | 'hidden-tab' | 'store-no-save';`
  - `export const WRITE_CALLS: Readonly<Record<string, WriteGate>>` keyed by `ApiClient` method name, one row per method whose body calls `this.http.post|put|patch|delete|request`.
  - `export const GATED_CALLERS: Readonly<Partial<Record<WriteGate, readonly string[]>>>` — for `'admin-route'`, `'hidden-tab'` and `'store-no-save'`, the source paths (relative to `src/app`, a trailing `/` meaning a folder) that are allowed to call a method with that gate.

What each gate means (the doc comment on `WriteGate` says this, one line each):
- `public` — sign-in/out; every principal may call it.
- `admin-route` — called only from System (route-guarded by `adminGuard`, V207-9) and its stores.
- `if-admin` — its control renders inside `*ifAdmin` (V207-13..V207-15 place the directive).
- `hidden-tab` — its only UI is the Analytics Tuning tab, which viewers never see (V207-15).
- `store-no-save` — the store skips the call for viewers (V207-11).

- [ ] **Step 1: Write the spec** — `frontend/src/app/auth/write-calls.spec.ts`

```ts
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { GATED_CALLERS, WRITE_CALLS, WriteGate } from './write-calls';

const ROOT = join(process.cwd(), 'src/app');
const read = (path: string) => readFileSync(join(ROOT, path), 'utf8');

const walk = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
  const path = join(dir, name);
  return statSync(path).isDirectory() ? walk(path) : [path];
});
const SOURCES = walk(ROOT)
  .filter((path) => path.endsWith('.ts') && !path.endsWith('.spec.ts'))
  .map((path) => relative(ROOT, path).replaceAll('\\', '/'));

/** ApiClient methods whose body makes a non-GET call: the method name is the
 *  last two-space-indented `name(` line above the `this.http.<verb>` call. */
function mutatingMethods(): string[] {
  const found = new Set<string>();
  let current: string | null = null;
  for (const line of read('api/api-client.ts').split('\n')) {
    const signature = /^ {2}([A-Za-z]\w*)\s*\(/.exec(line);
    if (signature) current = signature[1];
    if (current && /this\.http\.(post|put|patch|delete|request)\b/.test(line)) found.add(current);
  }
  return [...found].sort();
}

describe('WRITE_CALLS (v207)', () => {
  it('lists every mutating ApiClient method, and nothing else', () => {
    expect(mutatingMethods().length).toBeGreaterThanOrEqual(26);
    expect(Object.keys(WRITE_CALLS).sort()).toEqual(mutatingMethods());
  });

  it('has no HttpClient write outside ApiClient, so the list above is the whole surface', () => {
    const writers = SOURCES
      .filter((path) => path !== 'api/api-client.ts')
      .filter((path) => /\b(?:http|httpClient|client)\.(post|put|patch|delete|request)\s*[<(]/.test(read(path)));
    expect(writers).toEqual([]);
  });

  it('keeps sign-in and sign-out public, and only those', () => {
    const publicCalls = Object.entries(WRITE_CALLS).filter(([, gate]) => gate === 'public').map(([name]) => name).sort();
    expect(publicCalls).toEqual(['login', 'logout']);
  });

  it.each(['admin-route', 'hidden-tab', 'store-no-save'] as WriteGate[])(
    'calls every %s method only from the places that gate allows',
    (gate) => {
      const allowed = GATED_CALLERS[gate]!;
      const inside = (path: string) => allowed.some((place) => (place.endsWith('/') ? path.startsWith(place) : path === place));
      const methods = Object.entries(WRITE_CALLS).filter(([, g]) => g === gate).map(([name]) => name);
      expect(methods.length).toBeGreaterThan(0);
      const strays = methods.flatMap((method) => SOURCES
        .filter((path) => path !== 'api/api-client.ts' && read(path).includes(`.${method}(`) && !inside(path))
        .map((path) => `${method} <- ${path}`));
      expect(strays).toEqual([]);
    },
  );
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/auth/write-calls.spec.ts`
Expected: FAIL — cannot resolve `./write-calls`.

- [ ] **Step 3: Write `frontend/src/app/auth/write-calls.ts`**

Module doc comment: the spec v207 § SPA inventory as code; the server is the boundary and this list only proves no write control was forgotten; a new mutating `ApiClient` method fails `write-calls.spec.ts` until it gets a row here. Each row carries a trailing comment naming where its control lives (from the traced inventory):

```ts
export const WRITE_CALLS: Readonly<Record<string, WriteGate>> = {
  login: 'public',                 // session.store
  logout: 'public',                // session.store
  refreshMarket: 'if-admin',       // <sb-market-refresh> at dashboard.ts and trades/trade-detail.ts
  closeTrade: 'if-admin',          // trade-actions.ts <- trades.ts rows, trade-detail.ts, dashboard row-actions
  cancelTrade: 'if-admin',         // same callers as closeTrade
  deleteTrade: 'if-admin',         // same callers as closeTrade
  closeOpenTrades: 'if-admin',     // dashboard.ts header menu, data-action="close-all"
  clearOpenTrades: 'if-admin',     // trades.ts data-action="clear-open"
  clearTradeHistory: 'if-admin',   // trades.ts data-action="clear-history"
  setTradeNote: 'if-admin',        // trade-detail.ts #trade-note (read-only text for viewers)
  startTuneJob: 'hidden-tab',      // analytics.store <- Tuning tab
  createProposal: 'hidden-tab',    // analytics.store <- Tuning tab
  deleteProposal: 'hidden-tab',    // analytics.store <- Tuning tab
  addTickers: 'if-admin',          // watchlist.ts add box
  removeTicker: 'if-admin',        // watchlist.ts remove + confirm
  setKillswitch: 'if-admin',       // risk.ts .kill-actions Engage / Release
  previewSettings: 'admin-route',  // system.store <- settings tab
  saveSettings: 'admin-route',     // system.store <- settings tab
  importSettings: 'admin-route',   // system.store <- settings tab
  clearLogs: 'admin-route',        // system.store <- system.ts
  triggerScan: 'admin-route',      // system.store <- scan-tab.ts
  stopScan: 'admin-route',         // system.store <- scan-tab.ts
  pauseScan: 'admin-route',        // system.store <- scan-tab.ts
  resumeScan: 'admin-route',       // system.store <- scan-tab.ts
  restartBot: 'admin-route',       // system.store <- system.ts
  savePreferences: 'store-no-save', // preferences.store (V207-11)
};

export const GATED_CALLERS: Readonly<Partial<Record<WriteGate, readonly string[]>>> = {
  'admin-route': [
    'stores/system.store.ts', 'stores/users.store.ts', 'stores/versions.store.ts',
    'workspaces/system/', 'workspaces/versions/',
  ],
  'hidden-tab': ['stores/analytics.store.ts', 'workspaces/analytics/tabs/tuning.ts'],
  'store-no-save': ['stores/preferences.store.ts'],
};
```

`stores/users.store.ts` is listed ahead of V207-16, which creates it; a path that does not exist yet allows nothing.

- [ ] **Step 4: Run it to see it pass**

Run: the Step 2 command.
Expected: PASS, `0 failed`. If the first test fails, the diff names a method the brief's trace missed or that was renamed: add or correct its row with the right gate (and, for an `if-admin` row, tell the controller which component renders it, so a part-4 task gates it), never delete the assertion.

- [ ] **Step 5: Commit**

```bash
cd "<wt>" && git add frontend/src/app/auth/write-calls.ts frontend/src/app/auth/write-calls.spec.ts
git commit -m "test(v207): checked-in write-call inventory, fails on an unlisted mutating ApiClient method (V207-12)"
```
