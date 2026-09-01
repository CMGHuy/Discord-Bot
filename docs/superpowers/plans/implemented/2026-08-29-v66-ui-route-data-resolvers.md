# UI Route Data Resolvers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.9.2 · bot 1.4.5

Bump: ui minor (1.9.x -> 1.10.0)

Edge: none (integrity)

**Goal:** Make every authenticated route resolve its minimum fresh server data before activation, with cancellable requests, a delayed in-shell loading overlay, and debounced server-authoritative refreshes.

**Architecture:** Lazy route files provide each workspace store at route scope so its resolver and component share one instance without making feature stores eager. Shared routing services own request settlement, authentication expiry, delayed progress UI, live-event coalescing, and successful-mutation invalidation; feature stores own only request parameters and state projection.

**Tech Stack:** Angular 21 standalone routes and functional resolvers, NgRx Signal Store 21, RxJS 7.8, Vitest 4, Angular HTTP/router testing, Flask `/api/v1` contract.

**Spec:** `docs/superpowers/specs/2026-08-29-v66-ui-route-data-resolvers-design.md`

## Progress

**Closed 2026-09-01: all 15 tasks landed and merged to `main`** on branch
`75b1ebb..f1b498c`, merge commit `e2902f8` (with one post-merge fixup,
`7b98031`, tightening a Watchlist fixture — no behavior change). Released as
`ui 1.11.0` (commits `38c077c`/`91aebf2`; the plan's `Bump:` line projected
`1.10.0`, drift from unrelated UI work landing between authoring and
execution). Re-verified directly on `main` at close-out, not just trusted:
`cd frontend && npm test` — 88 files / 1769 tests passed, 0 failed.

- [x] R1 Resolver request contract and preference readiness
- [x] R2 Resolver authentication cancellation and return URL
- [x] R3 Delayed route-progress state
- [x] R4 In-shell loading overlay
- [x] R5 Debounced live-event and mutation refresh coordinator
- [x] R6 Dashboard resolver pilot
- [x] R7 Trades list resolver and secondary trade lists
- [x] R8 Trade Detail resolver, chart continuation, and note draft safety
- [x] R9 Analytics selected-tab resolver
- [x] R10 Calendar resolver
- [x] R11 Watchlist and Ticker Detail resolvers
- [x] R12 Risk resolver
- [x] R13 System selected-tab resolver and settings draft safety
- [x] R14 Versions resolver and all-route contract gate
- [x] R15 Full-suite verification and UI release

## Global Constraints

- Preserve `canMatch: [authGuard]` on every authenticated top-level route so unauthenticated navigation does not download a feature chunk.
- Keep components lazy. Route-scoped stores must live in lazily imported `*.routes.ts` files, not as eager imports in `app.routes.ts`.
- Every route visit and relevant query-parameter change refetches; do not render a cached response as the initial state of a new visit.
- Resolver cancellation must unsubscribe Angular `HttpClient` requests. Do not convert blocking route loads to promises.
- A non-auth API failure settles the resolver and activates the workspace with its existing inline error/retry state. An auth failure expires the session, remembers the requested URL, and cancels activation.
- Only data for the initially visible route/tab blocks. Secondary tabs, Dashboard trade groups, detail-page supporting tables, and optional chart panels remain demand-loaded.
- The route overlay appears only after `1000ms`, leaves sidebar/topbar visible, dims the previous workspace, and blocks workspace interaction until resolution settles.
- Coalesce event bursts for `300ms` after the last relevant event. A newer navigation cancels obsolete resolver work.
- Successful state-changing HTTP requests request the same resolver refresh. Login/logout, settings preview, and UI-preference persistence explicitly opt out.
- System settings and Trade Detail notes preserve unsaved drafts and show a data-changed notice; only an explicit reload discards the draft.
- No new runtime dependency and no backend API change.
- Use narrow frontend verification per task: `cd frontend && npm test -- --include <one spec file>`. Run bare `npm test` once, only in R15.
- Stage only files named by the task. Never stage `.parity/` or `data/universe/rs_cache.json`.

## File structure

| File | Responsibility |
|---|---|
| `frontend/src/app/routing/route-request.ts` | Turn one cold API observable into resolver-safe store state: settle non-auth failures, rethrow auth failures, preserve unsubscription. |
| `frontend/src/app/routing/route-resolver.ts` | Wait for preferences, run the feature request, expire auth with the requested URL, and cancel that navigation. |
| `frontend/src/app/routing/route-metadata.ts` | Typed loading labels and event predicates shared by lazy routes, progress, and refresh services. |
| `frontend/src/app/routing/route-loading.service.ts` | Convert router resolve events into delayed overlay signals. |
| `frontend/src/app/routing/route-refresh.service.ts` | Filter live events through active-route metadata, debounce events/mutations, and reload the same URL. |
| `frontend/src/app/workspaces/**/**.routes.ts` | Lazy route providers, resolver, loading label, refresh predicate, and component loader for one route. |
| Existing `*.store.ts` files | Expose cold `resolve...(): Observable<void>` methods and retain imperative `load...(): void` wrappers only for explicit retry/local control paths. |

## Parallelisation

- **Sequential foundation:** R1 -> R2 -> R3 -> R4 -> R5. Each consumes interfaces created by the previous task.
- **Sequential pilot:** R6 follows R5 and proves the complete contract before broad migration.
- **Parallel migration group after R6:** R7, R9, R10, R12, R13, and R14 touch disjoint workspace/store files. R8 follows R7 because Trade Detail consumes the shared `ChartStore` and trade-list changes. R11 follows R7 and R8 because Ticker Detail consumes both `TradesStore` and `ChartStore`.
- **Sequential gate:** R15 follows every migration task and is the plan's only full-suite run and release step.

---

# Phase 1 — Shared routing infrastructure

**Parallelisation:** Sequential throughout: R2 consumes R1's cold request contract; R3 and R4 share progress interfaces; R5 consumes route metadata and changes router/interceptor configuration.

### Task R1: Resolver request contract and preference readiness

**Files:**
- Create: `frontend/src/app/routing/route-request.ts`
- Create: `frontend/src/app/routing/route-request.spec.ts`
- Modify: `frontend/src/app/stores/preferences.store.ts`
- Modify: `frontend/src/app/stores/preferences.store.spec.ts`

**Interfaces:**
- Consumes: `ApiError.isAuth`, cold `Observable<T>` values from `ApiClient`.
- Produces: `routeRequest<T>(source, handlers): Observable<void>`; `PreferencesStore.resolve(): Observable<void>`; existing `PreferencesStore.load(): void` remains callable.

- [ ] **Step 1: Write failing request-contract tests**

```ts
it('settles a non-auth error after projecting it into store state', () => {
  const seen: ApiError[] = [];
  const values: void[] = [];
  routeRequest(throwError(() => new ApiError('unavailable', 0, 'down')), {
    start: vi.fn(), next: vi.fn(), error: (error) => seen.push(error),
  }).subscribe((value) => values.push(value));
  expect(seen).toHaveLength(1);
  expect(values).toEqual([undefined]);
});

it('rethrows auth failures for the resolver and preserves cancellation', () => {
  let tornDown = false;
  const source = new Observable<never>(() => () => { tornDown = true; });
  const sub = routeRequest(source, {
    start: vi.fn(), next: vi.fn(), error: vi.fn(),
  }).subscribe();
  sub.unsubscribe();
  expect(tornDown).toBe(true);
});
```

- [ ] **Step 2: Run the focused tests and confirm the new API is absent**

Run: `cd frontend && npm test -- --include src/app/routing/route-request.spec.ts`

Expected: FAIL because `route-request.ts` and `routeRequest` do not exist.

- [ ] **Step 3: Implement the cold request adapter**

```ts
export interface RouteRequestHandlers<T> {
  start(): void;
  next(value: T): void;
  error(error: ApiError): void;
}

export function routeRequest<T>(
  source: Observable<T>,
  handlers: RouteRequestHandlers<T>,
): Observable<void> {
  return defer(() => {
    handlers.start();
    return source.pipe(
      tap({ next: handlers.next, error: handlers.error }),
      map(() => undefined),
      catchError((error: unknown) =>
        error instanceof ApiError && error.isAuth
          ? throwError(() => error)
          : of(undefined),
      ),
    );
  });
}
```

- [ ] **Step 4: Make preference loading share one resolver-ready request**

```ts
let inFlight: Observable<void> | null = null;

const resolve = (): Observable<void> => {
  if (store.loaded()) return of(undefined);
  if (inFlight) return inFlight;
  inFlight = api.preferences().pipe(
    tap({
      next: ({ preferences }) => patchState(store, { values: preferences ?? {}, loaded: true }),
      error: () => patchState(store, { loaded: true }),
    }),
    catchError(() => of(undefined)),
    map(() => undefined),
    finalize(() => { inFlight = null; }),
    shareReplay({ bufferSize: 1, refCount: true }),
  );
  return inFlight;
};

return {
  resolve,
  load(): void { resolve().subscribe(); },
  // retain the existing values/update/columns/reset/flush methods
};
```

- [ ] **Step 5: Prove concurrent shell and resolver callers share one GET**

Add a preference-store test that calls `store.load()` and subscribes to `store.resolve()` before flushing. Assert `HttpTestingController.expectOne('/api/v1/preferences')`, flush once, and assert both observe `isLoaded() === true`.

Run: `cd frontend && npm test -- --include src/app/stores/preferences.store.spec.ts`

Expected: PASS with one preferences request.

- [ ] **Step 6: Commit R1**

```bash
git add frontend/src/app/routing/route-request.ts frontend/src/app/routing/route-request.spec.ts frontend/src/app/stores/preferences.store.ts frontend/src/app/stores/preferences.store.spec.ts
git commit -m "refactor(v66): add resolver-safe request contract"
```

### Task R2: Resolver authentication cancellation and return URL

**Files:**
- Create: `frontend/src/app/routing/route-resolver.ts`
- Create: `frontend/src/app/routing/route-resolver.spec.ts`
- Modify: `frontend/src/app/stores/session.store.ts`
- Modify: `frontend/src/app/stores/session.store.spec.ts`

**Interfaces:**
- Consumes: `PreferencesStore.resolve(): Observable<void>` and a feature `load(): Observable<void>` callback.
- Produces: `resolveRoute(load: (route: ActivatedRouteSnapshot) => Observable<void>): ResolveFn<boolean>`; `SessionStore.expire(redirectTo?: string): void`.

- [ ] **Step 1: Write failing resolver tests**

```ts
it('waits for preferences before starting feature data', () => {
  const order: string[] = [];
  preferences.resolve.mockReturnValue(of(undefined).pipe(tap(() => order.push('preferences'))));
  const resolver = resolveRoute(() => of(undefined).pipe(tap(() => order.push('feature'))));
  TestBed.runInInjectionContext(() => resolver(route, state)).subscribe();
  expect(order).toEqual(['preferences', 'feature']);
});

it('remembers the requested URL and cancels an auth failure', () => {
  const resolver = resolveRoute(() => throwError(() => new ApiError('auth', 401, 'expired')));
  let completed = false;
  TestBed.runInInjectionContext(() => resolver(route, { ...state, url: '/trades?page=2' }))
    .subscribe({ complete: () => { completed = true; } });
  expect(session.expire).toHaveBeenCalledWith('/trades?page=2');
  expect(completed).toBe(true);
});
```

- [ ] **Step 2: Confirm the resolver tests fail**

Run: `cd frontend && npm test -- --include src/app/routing/route-resolver.spec.ts`

Expected: FAIL because `resolveRoute` does not exist.

- [ ] **Step 3: Implement preference-first resolution and auth cancellation**

```ts
export function resolveRoute(
  load: (route: ActivatedRouteSnapshot) => Observable<void>,
): ResolveFn<boolean> {
  return (route, state) => {
    const preferences = inject(PreferencesStore);
    const session = inject(SessionStore);
    return preferences.resolve().pipe(
      switchMap(() => load(route)),
      map(() => true),
      catchError((error: unknown) => {
        if (error instanceof ApiError && error.isAuth) {
          session.expire(state.url);
          return EMPTY;
        }
        return of(true);
      }),
    );
  };
}
```

- [ ] **Step 4: Preserve an explicit deep link on mid-session expiry**

Change `SessionStore.expire` to accept an optional URL, write it to `redirectTo` unless it is `/`, and retain the existing rejected-login error rule.

```ts
expire(redirectTo?: string): void {
  const fallback = `${location.pathname}${location.search}`;
  const requested = redirectTo ?? fallback;
  const remembered = requested && requested !== '/' ? requested : null;
  patchState(store, {
    status: 'anonymous',
    username: null,
    redirectTo: redirectTo !== undefined
      ? remembered
      : store.redirectTo() ?? remembered,
    error: store.status() === 'authenticated' ? null : store.error(),
  });
}
```

Add an ordering test that calls `expire()` first (simulating the interceptor effect), then `expire('/trades?page=2')` (the resolver), and asserts the explicit resolver URL wins. Call `expire()` once more and assert it does not overwrite that remembered URL.

- [ ] **Step 5: Verify expiry and resolver behavior**

Run: `cd frontend && npm test -- --include src/app/stores/session.store.spec.ts`

Expected: PASS, including a new assertion that `expire('/analytics?tab=tuning')` is returned once by `takeRedirect()` after login.

- [ ] **Step 6: Commit R2**

```bash
git add frontend/src/app/routing/route-resolver.ts frontend/src/app/routing/route-resolver.spec.ts frontend/src/app/stores/session.store.ts frontend/src/app/stores/session.store.spec.ts
git commit -m "feat(v66): cancel resolved routes on session expiry"
```

### Task R3: Delayed route-progress state

**Files:**
- Create: `frontend/src/app/routing/route-metadata.ts`
- Create: `frontend/src/app/routing/route-loading.service.ts`
- Create: `frontend/src/app/routing/route-loading.service.spec.ts`

**Interfaces:**
- Consumes: Angular `ResolveStart`, `ResolveEnd`, `NavigationCancel`, `NavigationError`, and `NavigationEnd` events.
- Produces: `routeData(label, refreshOn)` metadata; `resolvedRoute(snapshot)` traversal; `RouteLoadingService.visible`, `.label`, and `.pending` signals; constants `ROUTE_LOADING_DELAY_MS = 1000` and `LIVE_REFRESH_DEBOUNCE_MS = 300`.

- [ ] **Step 1: Write fake-timer tests for the fast and slow paths**

```ts
function routeState(label: string): RouterStateSnapshot {
  return {
    root: {
      data: {},
      firstChild: {
        data: routeData(label, () => true),
        firstChild: null,
      },
    },
  } as unknown as RouterStateSnapshot;
}

const resolveStart = (label: string) =>
  new ResolveStart(1, '/target', '/target', routeState(label));
const resolveEnd = (label: string) =>
  new ResolveEnd(1, '/target', '/target', routeState(label));
const navigationCancel = () =>
  new NavigationCancel(1, '/target', 'superseded');
const navigationError = () =>
  new NavigationError(1, '/target', new Error('navigation failed'));

it('suppresses fast resolution and exposes slow resolution after one second', () => {
  vi.useFakeTimers();
  events.next(resolveStart('Trades'));
  vi.advanceTimersByTime(999);
  expect(service.visible()).toBe(false);
  vi.advanceTimersByTime(1);
  expect(service.visible()).toBe(true);
  expect(service.label()).toBe('Loading Trades');
  events.next(resolveEnd('Trades'));
  expect(service.visible()).toBe(false);
});

it.each([navigationCancel(), navigationError()])('clears progress on cancellation/error', (end) => {
  events.next(resolveStart('Risk'));
  vi.advanceTimersByTime(1000);
  events.next(end);
  expect(service.pending()).toBe(false);
  expect(service.visible()).toBe(false);
});
```

- [ ] **Step 2: Confirm the progress tests fail**

Run: `cd frontend && npm test -- --include src/app/routing/route-loading.service.spec.ts`

Expected: FAIL because the metadata and service do not exist.

- [ ] **Step 3: Implement typed route metadata**

```ts
export type RefreshPredicate = (event: EventName, route: ActivatedRouteSnapshot) => boolean;
export interface ResolverRouteData {
  loadingLabel: string;
  refreshOn: RefreshPredicate;
}
export const RESOLVER_ROUTE_DATA = 'resolverRouteData';
export const onEvents = (...names: EventName[]): RefreshPredicate =>
  (event) => names.includes(event);
export const routeData = (loadingLabel: string, refreshOn: RefreshPredicate): Data => ({
  [RESOLVER_ROUTE_DATA]: { loadingLabel, refreshOn } satisfies ResolverRouteData,
});

export function resolvedRoute(root: ActivatedRouteSnapshot): ActivatedRouteSnapshot | null {
  let route: ActivatedRouteSnapshot | null = root;
  let match: ActivatedRouteSnapshot | null = null;
  while (route) {
    if (route.data[RESOLVER_ROUTE_DATA]) match = route;
    route = route.firstChild;
  }
  return match;
}
```

- [ ] **Step 4: Implement delayed progress from router events**

```ts
@Injectable({ providedIn: 'root' })
export class RouteLoadingService {
  private readonly _pending = signal(false);
  private readonly _visible = signal(false);
  private readonly _label = signal('Loading');
  private timer: ReturnType<typeof setTimeout> | null = null;
  readonly pending = this._pending.asReadonly();
  readonly visible = this._visible.asReadonly();
  readonly label = this._label.asReadonly();

  constructor() {
    inject(Router).events.subscribe((event) => {
      if (event instanceof ResolveStart) this.start(event.state.root);
      if (event instanceof ResolveEnd || event instanceof NavigationEnd ||
          event instanceof NavigationCancel || event instanceof NavigationError) this.finish();
    });
  }

  private start(root: ActivatedRouteSnapshot): void {
    this.finish();
    const route = resolvedRoute(root);
    const meta = route?.data[RESOLVER_ROUTE_DATA] as ResolverRouteData | undefined;
    if (!meta) return;
    this._pending.set(true);
    this._label.set(meta.loadingLabel);
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this._pending()) this._visible.set(true);
    }, ROUTE_LOADING_DELAY_MS);
  }

  private finish(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this._pending.set(false);
    this._visible.set(false);
  }
}
```

- [ ] **Step 5: Verify timer cleanup and reduced-motion-independent state**

Run: `cd frontend && npm test -- --include src/app/routing/route-loading.service.spec.ts`

Expected: PASS with no pending Vitest timers after each case.

- [ ] **Step 6: Commit R3**

```bash
git add frontend/src/app/routing/route-metadata.ts frontend/src/app/routing/route-loading.service.ts frontend/src/app/routing/route-loading.service.spec.ts
git commit -m "feat(v66): track delayed route resolution"
```

### Task R4: In-shell loading overlay

**Files:**
- Modify: `frontend/src/app/shell/shell.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `frontend/src/app/shell/shell.css`
- Modify: `frontend/src/app/shell/shell.spec.ts`

**Interfaces:**
- Consumes: `RouteLoadingService.visible(): boolean` and `label(): string` from R3.
- Produces: one accessible, non-interactive overlay inside `.workspace`; no change to sidebar or topbar layout.

- [ ] **Step 1: Write the failing shell behavior test**

```ts
const routeLoading = { visible: signal(false), label: signal('Loading Trades') };
TestBed.overrideProvider(RouteLoadingService, { useValue: routeLoading });
const fixture = TestBed.createComponent(Shell);
fixture.detectChanges();
routeLoading.visible.set(true);
fixture.detectChanges();
const workspace = fixture.nativeElement.querySelector('.workspace') as HTMLElement;
expect(workspace.classList.contains('route-pending')).toBe(true);
expect(workspace.querySelector('[role="status"]')?.textContent).toContain('Loading Trades');
expect(workspace.querySelector('.route-loading-overlay')).not.toBeNull();
```

- [ ] **Step 2: Confirm the shell test fails**

Run: `cd frontend && npm test -- --include src/app/shell/shell.spec.ts`

Expected: FAIL because the shell has no route-loading state or overlay.

- [ ] **Step 3: Bind progress in the shell component and template**

```ts
protected readonly routeLoading = inject(RouteLoadingService);
```

```html
<main class="workspace" [class.route-pending]="routeLoading.visible()"
      [attr.aria-busy]="routeLoading.visible() ? 'true' : null">
  <div class="workspace-content" [attr.inert]="routeLoading.visible() ? '' : null">
    <router-outlet />
  </div>
  @if (routeLoading.visible()) {
    <div class="route-loading-overlay" role="status" aria-live="polite">
      <span class="route-loading-mark" aria-hidden="true"></span>
      <span>{{ routeLoading.label() }}</span>
    </div>
  }
</main>
```

- [ ] **Step 4: Add the dimmed, non-interactive presentation**

```css
.workspace { position: relative; }
.workspace-content { min-width: 0; transition: opacity var(--transition); }
.route-pending .workspace-content { opacity: 0.32; pointer-events: none; user-select: none; }
.route-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: var(--space-10);
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--surface) 58%, transparent);
  backdrop-filter: blur(1px);
}
.route-loading-mark {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: route-spin 700ms linear infinite;
}
@keyframes route-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .route-loading-mark { animation: none; } }
```

- [ ] **Step 5: Verify visibility, accessibility, and reduced motion**

Run: `cd frontend && npm test -- --include src/app/shell/shell.spec.ts`

Expected: PASS; the topbar and sidebar remain outside the dimmed workspace.

- [ ] **Step 6: Commit R4**

```bash
git add frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(v66): show delayed route loading overlay"
```

### Task R5: Debounced live-event and mutation refresh coordinator

**Files:**
- Create: `frontend/src/app/routing/route-refresh.service.ts`
- Create: `frontend/src/app/routing/route-refresh.service.spec.ts`
- Modify: `frontend/src/app/api/event-stream.ts`
- Modify: `frontend/src/app/api/event-stream.spec.ts`
- Modify: `frontend/src/app/api/interceptors.ts`
- Modify: `frontend/src/app/api/interceptors.spec.ts`
- Modify: `frontend/src/app/api/api-client.ts`
- Modify: `frontend/src/app/app.config.ts`
- Modify: `frontend/src/app/shell/shell.ts`

**Interfaces:**
- Consumes: active `ResolverRouteData.refreshOn`, `EventStream.raised: Observable<EventName>`, and successful non-GET responses.
- Produces: `RouteRefreshService.requestMutation(): void`; `SKIP_ROUTE_REFRESH` HTTP context token; same-URL reload with `replaceUrl: true` after `300ms` quiet time.

- [ ] **Step 1: Write failing coalescing and relevance tests**

```ts
it('coalesces relevant events and reloads the current URL once', () => {
  vi.useFakeTimers();
  raised.next('trades');
  raised.next('account');
  vi.advanceTimersByTime(299);
  expect(router.navigateByUrl).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(router.navigateByUrl).toHaveBeenCalledOnce();
  expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard', {
    onSameUrlNavigation: 'reload', replaceUrl: true,
  });
});

it('ignores an event rejected by active-route metadata', () => {
  raised.next('jobs');
  vi.advanceTimersByTime(300);
  expect(router.navigateByUrl).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Expose event names without removing existing counters**

Add a private `Subject<EventName>`, expose `raised = this.raisedSubject.asObservable()`, and emit from the existing `bump(name)` after the counter update. Add an event-stream test that a `resync` emits every name while existing `changes(name)` assertions still pass.

```ts
private readonly raisedSubject = new Subject<EventName>();
readonly raised = this.raisedSubject.asObservable();

private bump(name: EventName): void {
  this.counterFor(name).update((n) => n + 1);
  this.raisedSubject.next(name);
}
```

- [ ] **Step 3: Implement the active-route refresh coordinator**

```ts
@Injectable({ providedIn: 'root' })
export class RouteRefreshService {
  private readonly router = inject(Router);
  private readonly routeLoading = inject(RouteLoadingService);
  private readonly settle = new Subject<void>();
  private readonly pendingEvents = new Set<EventName>();
  private mutationPending = false;

  constructor() {
    const events = inject(EventStream);
    events.raised.subscribe((event) => {
      this.pendingEvents.add(event);
      this.settle.next();
    });
    this.router.events.pipe(filter((event) =>
      event instanceof NavigationEnd || event instanceof NavigationCancel ||
      event instanceof NavigationError,
    )).subscribe(() => {
      if (this.pendingEvents.size || this.mutationPending) this.settle.next();
    });
    this.settle.pipe(debounceTime(LIVE_REFRESH_DEBOUNCE_MS)).subscribe(() => {
      if (this.routeLoading.pending()) return;
      const active = resolvedRoute(this.router.routerState.snapshot.root);
      const meta = active?.data[RESOLVER_ROUTE_DATA] as ResolverRouteData | undefined;
      const relevantEvent = !!active && !!meta &&
        [...this.pendingEvents].some((event) => meta.refreshOn(event, active));
      const shouldRefresh = this.mutationPending || relevantEvent;
      this.pendingEvents.clear();
      this.mutationPending = false;
      if (shouldRefresh && this.router.url !== '/') {
        void this.router.navigateByUrl(this.router.url, {
          onSameUrlNavigation: 'reload', replaceUrl: true,
        });
      }
    });
  }

  requestMutation(): void {
    this.mutationPending = true;
    this.settle.next();
  }
}
```

- [ ] **Step 4: Refresh after successful state-changing requests**

```ts
export const SKIP_ROUTE_REFRESH = new HttpContextToken(() => false);

export const routeRefreshInterceptor: HttpInterceptorFn = (req, next) => {
  const refresh = inject(RouteRefreshService);
  return next(req).pipe(tap((event) => {
    if (event instanceof HttpResponse && req.method !== 'GET' &&
        !req.context.get(SKIP_ROUTE_REFRESH)) refresh.requestMutation();
  }));
};
```

Set `SKIP_ROUTE_REFRESH` on login, logout, settings preview, and preferences save requests in `ApiClient`. Register the interceptor after `authInterceptor` in the outbound list, enable `withRouterConfig({ onSameUrlNavigation: 'reload' })`, and inject `RouteRefreshService` in `Shell` so its event subscription starts with the authenticated shell.

- [ ] **Step 5: Verify mutation inclusion and opt-outs**

```ts
it('refreshes only after a successful state-changing response', () => {
  client.post('/api/v1/trades/t1/close', {}).subscribe();
  backend.expectOne('/api/v1/trades/t1/close').flush({});
  expect(refresh.requestMutation).toHaveBeenCalledOnce();

  client.get('/api/v1/trades').subscribe();
  backend.expectOne('/api/v1/trades').flush({ items: [] });
  expect(refresh.requestMutation).toHaveBeenCalledOnce();
});

it('honours the explicit refresh opt-out', () => {
  client.post('/api/v1/system/settings/preview', {}, {
    context: new HttpContext().set(SKIP_ROUTE_REFRESH, true),
  }).subscribe();
  backend.expectOne('/api/v1/system/settings/preview').flush({ diff: [] });
  expect(refresh.requestMutation).not.toHaveBeenCalled();
});
```

Run: `cd frontend && npm test -- --include src/app/api/interceptors.spec.ts`

Expected: PASS without altering auth/error/loading interceptor behavior.

- [ ] **Step 6: Verify live-event coalescing**

Run: `cd frontend && npm test -- --include src/app/routing/route-refresh.service.spec.ts`

Expected: PASS with one same-URL navigation per settled burst.

- [ ] **Step 7: Commit R5**

```bash
git add frontend/src/app/routing/route-refresh.service.ts frontend/src/app/routing/route-refresh.service.spec.ts frontend/src/app/api/event-stream.ts frontend/src/app/api/event-stream.spec.ts frontend/src/app/api/interceptors.ts frontend/src/app/api/interceptors.spec.ts frontend/src/app/api/api-client.ts frontend/src/app/app.config.ts frontend/src/app/shell/shell.ts
git commit -m "feat(v66): coordinate live route refreshes"
```

# Phase 2 — Resolver pilot and trade routes

**Parallelisation:** R6 is sequential after the foundation. R7 follows R6. R8 follows R7 because both detail views consume the stores whose automatic hooks R7 removes.

### Task R6: Dashboard resolver pilot

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/dashboard.routes.ts`
- Create: `frontend/src/app/workspaces/dashboard/dashboard.routes.spec.ts`
- Modify: `frontend/src/app/stores/dashboard.store.ts`
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: `routeRequest`, `resolveRoute`, `routeData`, `onEvents`.
- Produces: `DashboardStore.resolve(): Observable<void>`; lazy `dashboardRoutes`; refresh on `account` and `trades`.

- [ ] **Step 1: Write the failing cold-store test**

```ts
it('does not request until resolve is subscribed and cancels on unsubscribe', () => {
  const pending = store.resolve();
  backend.expectNone('/api/v1/dashboard?mode=today');
  const sub = pending.subscribe();
  const request = backend.expectOne('/api/v1/dashboard?mode=today');
  sub.unsubscribe();
  expect(request.cancelled).toBe(true);
});
```

- [ ] **Step 2: Convert DashboardStore to a cold resolver plus retry wrapper**

```ts
const resolve = (): Observable<void> => routeRequest(api.dashboard(store.scope()), {
  start: () => patchState(store, { loading: true }),
  next: (data) => patchState(store, { data, loading: false, error: null }),
  error: (error) => patchState(store, {
    loading: false,
    error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
  }),
});
const load = (): void => { resolve().subscribe({ error: () => undefined }); };
return {
  resolve,
  load,
  setScope(scope: DashboardScope): void {
    if (scope === store.scope()) return;
    patchState(store, { scope });
    load();
  },
};
```

Remove the DashboardStore `withHooks` event effect. Keep `setScope` as an explicit in-workspace request path.

- [ ] **Step 3: Define the lazy route provider and resolver**

```ts
export const dashboardRoutes: Routes = [{
  path: '',
  providers: [DashboardStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Loading Dashboard', onEvents('account', 'trades')),
  resolve: { ready: resolveRoute(() => inject(DashboardStore).resolve()) },
  loadComponent: () => import('./dashboard').then((m) => m.Dashboard),
}];
```

Remove `providers: [DashboardStore]` from `Dashboard` and change the top-level route to guarded lazy children:

```ts
{
  path: 'dashboard', canMatch: [authGuard],
  loadChildren: () => import('./workspaces/dashboard/dashboard.routes')
    .then((m) => m.dashboardRoutes),
}
```

- [ ] **Step 4: Prove activation waits and failure still activates**

```ts
it('waits for Dashboard data before activation', async () => {
  let activated = false;
  const navigation = RouterTestingHarness.create('/dashboard')
    .then((harness) => { activated = true; return harness; });
  await Promise.resolve();
  expect(activated).toBe(false);
  backend.expectOne('/api/v1/dashboard?mode=today').flush(DASHBOARD);
  expect((await navigation).routeNativeElement?.textContent).toContain('Dashboard');
});

it('activates the existing error state after a non-auth failure', async () => {
  const navigation = RouterTestingHarness.create('/dashboard');
  backend.expectOne('/api/v1/dashboard?mode=today').flush(
    { error: { code: 'unavailable', message: 'down' } },
    { status: 503, statusText: 'Unavailable' },
  );
  expect((await navigation).routeNativeElement?.textContent)
    .toContain('The admin is not responding.');
});
```

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/dashboard.routes.spec.ts`

Expected: PASS; no component-level duplicate GET.

- [ ] **Step 5: Run existing Dashboard store/component tests**

Run: `cd frontend && npm test -- --include src/app/stores/dashboard.store.spec.ts`

Expected: PASS after tests explicitly subscribe to `resolve()` or call `load()`.

- [ ] **Step 6: Commit R6**

```bash
git add frontend/src/app/workspaces/dashboard/dashboard.routes.ts frontend/src/app/workspaces/dashboard/dashboard.routes.spec.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Dashboard before activation"
```

### Task R7: Trades list resolver and secondary trade lists

**Files:**
- Create: `frontend/src/app/workspaces/trades/trades.query.ts`
- Create: `frontend/src/app/workspaces/trades/trades.query.spec.ts`
- Create: `frontend/src/app/workspaces/trades/trades.routes.ts`
- Create: `frontend/src/app/workspaces/trades/trades.routes.spec.ts`
- Modify: `frontend/src/app/stores/trades.store.ts`
- Modify: `frontend/src/app/stores/trades.store.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.ts`
- Modify: `frontend/src/app/workspaces/dashboard/trade-group.ts`
- Modify: `frontend/src/app/workspaces/dashboard/trade-group.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: route query params, `PreferencesStore.values()`, `readTablePerPage`, `perPageForApi`, and R1's cold request adapter.
- Produces: `tradeQueryFromRoute(params: ParamMap, perPage: number): TradeQuery`; `TradesStore.resolve(query?: TradeQuery): Observable<void>`; lazy `tradesRoutes`; secondary callers explicitly own their initial/event loads.

- [ ] **Step 1: Pin the complete URL-to-API mapping in a pure test**

```ts
it('maps every list query parameter without collapsing tri-state booleans', () => {
  const params = convertToParamMap({
    page: '3', sort: '-opened_at', status: 'CLOSED', outcome: 'win', ticker: 'AAPL',
    strategy: 'EMA20', horizon: '3m', direction: 'bullish', tier: 'A', origin: 'plan',
    badge: 'VALIDATED', confidence: '5', has_note: '0', today: '1',
  });
  expect(tradeQueryFromRoute(params, 50)).toEqual({
    page: 3, per_page: 50, sort: '-opened_at', status: 'CLOSED', outcome: 'win',
    ticker: 'AAPL', strategy: 'EMA20', horizon: '3m', direction: 'bullish', tier: 'A',
    origin: 'plan', badge: 'VALIDATED', confidence: '5', has_note: false, today: true,
  });
});
```

- [ ] **Step 2: Extract and verify the query builder**

```ts
export function tradeQueryFromRoute(params: ParamMap, perPage: number): TradeQuery {
  const triState = (name: string): boolean | undefined => {
    const value = params.get(name);
    return value === null ? undefined : value === '1';
  };
  return {
    page: Number(params.get('page') ?? 1) || 1,
    per_page: perPage,
    sort: params.get('sort') ?? undefined,
    status: params.get('status') ?? undefined,
    outcome: params.get('outcome') ?? undefined,
    ticker: params.get('ticker') ?? undefined,
    strategy: params.get('strategy') ?? undefined,
    horizon: params.get('horizon') ?? undefined,
    direction: params.get('direction') ?? undefined,
    tier: params.get('tier') ?? undefined,
    origin: params.get('origin') ?? undefined,
    badge: params.get('badge') ?? undefined,
    confidence: params.get('confidence') ?? undefined,
    has_note: triState('has_note'),
    today: triState('today'),
  };
}
```

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.query.spec.ts`

Expected: PASS for `1`, `0`, and absent boolean cases.

- [ ] **Step 3: Convert TradesStore to explicit cold resolution**

```ts
const resolve = (query: TradeQuery = store.query()): Observable<void> => {
  patchState(store, { query, queryReady: true });
  return routeRequest(api.trades(query), {
    start: () => patchState(store, { loading: true }),
    next: (data) => patchState(store, { data, loading: false, error: null }),
    error: (error) => patchState(store, {
      loading: false,
      error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
    }),
  });
};
return {
  setQuery(query: TradeQuery): void { patchState(store, { query, queryReady: true }); },
  resolve,
  load(): void { resolve().subscribe({ error: () => undefined }); },
};
```

Remove `withHooks`. Retain the existing `latestRequest` guard inside the `next` and `error` handlers because explicit secondary loads can overlap outside router cancellation.

- [ ] **Step 4: Add the route-scoped list resolver**

```ts
resolve: { ready: resolveRoute((route) => {
  const prefs = inject(PreferencesStore).values();
  return inject(TradesStore).resolve(tradeQueryFromRoute(
    route.queryParamMap,
    perPageForApi(readTablePerPage(prefs, TRADES_TABLE_ID)),
  ));
}) },
```

- [ ] **Step 5: Move the store provider off the component**

Create `tradesRoutes` with `providers: [TradesStore]`, `runGuardsAndResolvers: 'always'`, label `Loading Trades`, and `onEvents('trades')`. Remove the component provider and its constructor query effect. Keep query input signals for form values; page-size changes write preferences then navigate, and same-URL reload reads the updated preference.

- [ ] **Step 6: Preserve explicit secondary loaders**

`TradeGroup` owns its status/event effect after the generic store hook is removed:

```ts
const changes = inject(EventStream).changes('trades');
effect(() => {
  changes();
  const status = this.status();
  untracked(() => {
    this.store.setQuery({ status, sort: '-created_at', page: 1, per_page: this.cap() });
    this.store.load();
  });
});
```

Keep the three sibling providers so PENDING/ACTIVE/PARTIAL remain isolated.

- [ ] **Step 7: Verify list activation, query reruns, and group isolation**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trades.routes.spec.ts`

Expected: PASS for blocked activation, `?page=2` cancellation/rerun, and one final response committed.

Run: `cd frontend && npm test -- --include src/app/workspaces/dashboard/trade-group.spec.ts`

Expected: PASS with three independent initial requests and one request per group after a `trades` event.

- [ ] **Step 8: Commit R7**

```bash
git add frontend/src/app/workspaces/trades/trades.query.ts frontend/src/app/workspaces/trades/trades.query.spec.ts frontend/src/app/workspaces/trades/trades.routes.ts frontend/src/app/workspaces/trades/trades.routes.spec.ts frontend/src/app/stores/trades.store.ts frontend/src/app/stores/trades.store.spec.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/dashboard/trade-group.ts frontend/src/app/workspaces/dashboard/trade-group.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Trades queries before activation"
```

### Task R8: Trade Detail resolver, chart continuation, and note draft safety

**Files:**
- Create: `frontend/src/app/workspaces/trades/trade-detail.routes.ts`
- Create: `frontend/src/app/workspaces/trades/trade-detail.routes.spec.ts`
- Modify: `frontend/src/app/stores/trade-detail.store.ts`
- Modify: `frontend/src/app/stores/trade-detail.store.spec.ts`
- Modify: `frontend/src/app/stores/chart.store.ts`
- Modify: `frontend/src/app/stores/chart.store.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: route `:id`, R1 request adapter, R5 mutation refresh, route-scoped `TradeDetailStore` and `ChartStore`.
- Produces: `TradeDetailStore.resolve(id?: string): Observable<void>`; `ChartStore.resolve(ticker?, tradeId?): Observable<void>`; `noteStale(): boolean`; `discardNoteAndReload(): void`.

- [ ] **Step 1: Write draft-preservation and cancellation tests**

```ts
it('keeps a dirty note and marks newer server data', () => {
  store.setId('trade-1');
  store.editNote('local draft');
  store.resolve().subscribe();
  backend.expectOne('/api/v1/trades/trade-1').flush(detail({ note: 'remote edit' }));
  backend.expectOne('/api/v1/trades/trade-1/journal').flush({ journaled: true, entry: null });
  expect(store.noteText()).toBe('local draft');
  expect(store.noteStale()).toBe(true);
});

it('cancels both detail requests when navigation is superseded', () => {
  const sub = store.resolve('trade-1').subscribe();
  const detailRequest = backend.expectOne('/api/v1/trades/trade-1');
  const journalRequest = backend.expectOne('/api/v1/trades/trade-1/journal');
  sub.unsubscribe();
  expect(detailRequest.cancelled).toBe(true);
  expect(journalRequest.cancelled).toBe(true);
});
```

- [ ] **Step 2: Resolve the primary detail and journal together**

Use `forkJoin` over two `routeRequest` observables. `resolve(id)` calls `setId(id)` first, then waits for both requests. The trade response always updates `data`; when `noteDirty()` is true and the response note differs from `noteText()`, it also sets `noteStale: true` without clearing `noteDraft`.

```ts
const setId = (id: string): void => {
  if (id === store.id()) return;
  patchState(store, {
    id, data: null, error: null, noteDraft: null, noteAcked: null,
    noteError: null, noteUnjournaled: false, noteStale: false,
  });
};

const resolve = (id = store.id()): Observable<void> => {
  if (!id) return of(undefined);
  if (id !== store.id()) setId(id);
  return forkJoin([
    routeRequest(api.trade(id), {
      start: () => patchState(store, { loading: true }),
      next: (data) => patchState(store, {
        data, loading: false, error: null,
        noteStale: store.noteDirty() && data.detail.note !== store.noteText(),
      }),
      error: (error) => patchState(store, {
        loading: false,
        error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
      }),
    }),
    routeRequest(api.tradeJournal(id), {
      start: () => patchState(store, { journalAnswered: false }),
      next: (response) => patchState(store, {
        journal: response.entry, journalAnswered: true, journalError: null,
      }),
      error: (error) => patchState(store, {
        journalAnswered: true,
        journalError: error.code === 'unavailable'
          ? 'The admin is not responding.' : error.message,
      }),
    }),
  ]).pipe(map(() => undefined));
};
```

Remove the event hook. Add `discardNoteAndReload()` that clears `noteDraft`, `noteAcked`, and `noteStale`, then subscribes to `resolve()`.

- [ ] **Step 3: Convert ChartStore to explicit loading**

```ts
const resolve = (
  ticker = store.ticker(),
  tradeId = store.tradeId(),
): Observable<void> => {
  if (!ticker) return of(undefined);
  if (ticker !== store.ticker() || tradeId !== store.tradeId()) setTarget(ticker, tradeId);
  return routeRequest(api.chart(ticker, {
    ...(tradeId === null ? {} : { trade_id: tradeId }),
    ...(store.window() === null ? {} : { window: store.window()! }),
  }), {
    start: () => patchState(store, { loading: true, error: null }),
    next: (data) => patchState(store, { data, loading: false, error: null }),
    error: (error) => patchState(store, {
      loading: false,
      error: error.code === 'not_found'
        ? `No chart data for ${tradeId ? `trade ${tradeId}` : ticker}.`
        : error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
    }),
  });
};
const load = (): void => { resolve().subscribe({ error: () => undefined }); };
```

Expose `resolve`, `load`, and `retry: load`; remove ChartStore's event hook. Retain the current `latestRequest` response guard for explicit window changes that can overlap outside router cancellation.

- [ ] **Step 4: Create the Trade Detail lazy route**

```ts
export const tradeDetailRoutes: Routes = [{
  path: '', providers: [TradeDetailStore, ChartStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Loading Trade', onEvents('trades', 'journal')),
  resolve: { ready: resolveRoute((route) =>
    inject(TradeDetailStore).resolve(route.paramMap.get('id') ?? undefined)) },
  loadComponent: () => import('./trade-detail').then((m) => m.TradeDetail),
}];
```

Remove component providers and the constructor `setId` effect. Keep strategy data deferred. Load chart data only when the chart-bearing tab is active and a trade exists; its effect calls both `setTarget` and `load` so a refreshed trade reloads chart overlays even when the ticker/id pair is unchanged.

- [ ] **Step 5: Add the note data-changed notice**

```html
@if (store.noteStale()) {
  <p class="stale-note" role="alert">
    This note changed on the server while you were editing. Your draft is preserved.
    <button sb-button variant="ghost" type="button"
            (click)="store.discardNoteAndReload()">Reload server note</button>
  </p>
}
```

- [ ] **Step 6: Verify route readiness, draft safety, and deferred chart loading**

Run: `cd frontend && npm test -- --include src/app/workspaces/trades/trade-detail.routes.spec.ts`

Expected: PASS; detail activation waits for detail+journal, non-auth failure activates error UI, and strategy/chart requests are absent on the default plan tab.

Run: `cd frontend && npm test -- --include src/app/stores/trade-detail.store.spec.ts`

Expected: PASS for draft preservation and explicit discard/reload.

- [ ] **Step 7: Commit R8**

```bash
git add frontend/src/app/workspaces/trades/trade-detail.routes.ts frontend/src/app/workspaces/trades/trade-detail.routes.spec.ts frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.store.spec.ts frontend/src/app/stores/chart.store.ts frontend/src/app/stores/chart.store.spec.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Trade Detail with draft safety"
```

# Phase 3 — Independent workspace migrations

**Parallelisation:** R9, R10, R12, R13, and R14 are parallel after R6 because their files are disjoint. R11 waits for R7/R8's shared `TradesStore` and `ChartStore` contracts.

### Task R9: Analytics selected-tab resolver

**Files:**
- Create: `frontend/src/app/workspaces/analytics/analytics.routes.ts`
- Create: `frontend/src/app/workspaces/analytics/analytics.routes.spec.ts`
- Modify: `frontend/src/app/stores/analytics.store.ts`
- Modify: `frontend/src/app/stores/analytics.store.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: `?tab=performance|strategies|calibration|tuning|plans` and existing date-range state.
- Produces: `AnalyticsStore.resolveTab(tab: AnalyticsTab): Observable<void>`; tuning refreshes only on `jobs`, other tabs only on `analytics`.

- [ ] **Step 1: Write selected-tab request tests**

```ts
it('blocks only on the selected Analytics tab payload', () => {
  store.resolveTab('calibration').subscribe();
  backend.expectOne('/api/v1/analytics/calibration').flush(CALIBRATION);
  backend.expectNone('/api/v1/analytics/performance');
  backend.expectNone('/api/v1/jobs');
});
```

- [ ] **Step 2: Return cold observables from every tab loader**

```ts
const loadPerformance = (): Observable<void> => forkJoin([
  routeRequest(api.analyticsPerformance({ from: store.rangeFrom(), to: store.rangeTo() }), {
    start: () => patchState(store, { loading: true }),
    next: (performance) => patchState(store, { performance, loading: false, error: null }),
    error: fail,
  }),
  routeRequest(api.analyticsSnapshot(), {
    start: () => undefined,
    next: (snapshot) => patchState(store, { snapshot, snapshotError: null }),
    error: (error) => patchState(store, { snapshotError: error.message }),
  }),
  routeRequest(api.analyticsJournal(), {
    start: () => undefined,
    next: (journal) => patchState(store, { journal, journalError: null }),
    error: (error) => patchState(store, { journalError: error.message }),
  }),
]).pipe(map(() => undefined));

const loadStrategies = (): Observable<void> => routeRequest(api.analyticsStrategies(), {
  start: () => patchState(store, { loading: true }),
  next: (strategies) => patchState(store, { strategies, loading: false, error: null }),
  error: fail,
});
const loadCalibration = (): Observable<void> => routeRequest(api.analyticsCalibration(), {
  start: () => patchState(store, { loading: true }),
  next: (calibration) => patchState(store, { calibration, loading: false, error: null }),
  error: fail,
});
const loadPlans = (): Observable<void> => routeRequest(api.analyticsPlans(), {
  start: () => patchState(store, { loading: true }),
  next: (plans) => patchState(store, { plans, loading: false, error: null }),
  error: fail,
});
```

Implement `loadProposals(): Observable<void>` with `routeRequest(api.proposals(), ...)`. Implement `loadJob(id)` as `forkJoin` of `api.job(id)` and `api.jobResult(id)` adapters. Implement `loadTuning()` by resolving jobs first, then `switchMap` to `forkJoin` of proposals, a strategy-registry request only when `strategies() === null`, and the tracked job request only when a job exists. Every absent conditional branch returns `of(undefined)`.

```ts
const resolveTab = (tab: AnalyticsTab): Observable<void> => {
  patchState(store, { tab });
  return ({
    performance: loadPerformance,
    strategies: loadStrategies,
    calibration: loadCalibration,
    tuning: loadTuning,
    plans: loadPlans,
  } satisfies Record<AnalyticsTab, () => Observable<void>>)[tab]();
};
```

Keep `load(): void` as a subscribing wrapper for explicit retry/date-range controls. Remove `withHooks`.

- [ ] **Step 3: Route the normalized tab through the resolver**

```ts
const ANALYTICS_ROUTE_TABS = new Set<AnalyticsTab>(ANALYTICS_TABS);
const analyticsTab = (raw: string | null): AnalyticsTab =>
  raw && ANALYTICS_ROUTE_TABS.has(raw as AnalyticsTab)
    ? raw as AnalyticsTab : 'performance';
const refreshOnAnalytics: RefreshPredicate = (event, route) =>
  analyticsTab(route.queryParamMap.get('tab')) === 'tuning'
    ? event === 'jobs'
    : event === 'analytics';
```

The lazy route provides `AnalyticsStore`, always reruns guards/resolvers, resolves `resolveTab(analyticsTab(...))`, and labels the overlay `Loading Analytics`. Remove the component provider and `effect(() => store.setTab(activeTab()))`.

- [ ] **Step 4: Verify tab query cancellation and event relevance**

```ts
it('cancels Performance when the URL switches to Tuning', async () => {
  const first = router.navigateByUrl('/analytics');
  const performance = backend.expectOne('/api/v1/analytics/performance');
  const second = router.navigateByUrl('/analytics?tab=tuning');
  expect(performance.cancelled).toBe(true);
  backend.expectOne('/api/v1/jobs').flush({ jobs: [] });
  backend.expectOne('/api/v1/analytics/tuning/proposals').flush({ proposals: [] });
  backend.expectOne('/api/v1/analytics/strategies').flush({ strategies: [], heatmap: null });
  await second;
  expect(router.url).toBe('/analytics?tab=tuning');
  await first;
});
```

In the same spec, emit `analytics` while Tuning is active and assert no navigation; emit three `jobs` events, advance `300ms`, and assert one same-URL navigation.

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.routes.spec.ts`

Expected: PASS with no eager requests for hidden tabs.

- [ ] **Step 5: Commit R9**

```bash
git add frontend/src/app/workspaces/analytics/analytics.routes.ts frontend/src/app/workspaces/analytics/analytics.routes.spec.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/analytics.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve the selected Analytics tab"
```

### Task R10: Calendar resolver

**Files:**
- Create: `frontend/src/app/workspaces/calendar/calendar.routes.ts`
- Create: `frontend/src/app/workspaces/calendar/calendar.routes.spec.ts`
- Modify: `frontend/src/app/stores/calendar.store.ts`
- Modify: `frontend/src/app/stores/calendar.store.spec.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: current CalendarStore month/strategy/horizon defaults and explicit in-workspace controls.
- Produces: `CalendarStore.resolve(): Observable<void>`; route refresh on `trades`; day drawer stays lazy.

- [ ] **Step 1: Write the cold month-load test**

```ts
it('resolves the selected month but not a day drawer', () => {
  store.resolve().subscribe();
  backend.expectOne((req) => req.url === '/api/v1/calendar/pnl').flush(MONTH);
  backend.expectNone((req) => req.url.includes('/calendar/pnl/day'));
});
```

- [ ] **Step 2: Convert only the month request to resolver form**

```ts
const resolve = (): Observable<void> => routeRequest(api.calendarPnl({
  month: store.month(),
  strategy: store.strategy() || undefined,
  horizon: store.horizon() || undefined,
}), {
  start: () => patchState(store, { loading: true }),
  next: (data) => patchState(store, { data, loading: false, error: null }),
  error: (error) => patchState(store, {
    loading: false,
    error: error.code === 'unavailable'
      ? 'The admin is not responding -- these figures may be stale.' : error.message,
  }),
});
const load = (): void => { resolve().subscribe({ error: () => undefined }); };
```

Return `resolve` and `load`; keep `setMonth`, `stepMonth`, `setStrategy`, and `setHorizon` calling `load`, keep `selectDay` demand-loaded, and remove the `trades` event hook.

- [ ] **Step 3: Add route scope and remove component scope**

Create `calendarRoutes` with `providers: [CalendarStore]`, `runGuardsAndResolvers: 'always'`, `Loading Calendar`, `onEvents('trades')`, and `resolveRoute(() => inject(CalendarStore).resolve())`. Remove `providers: [CalendarStore]` from the component and make `/calendar` load the route file behind `authGuard`.

- [ ] **Step 4: Verify first activation and later local month changes**

Run: `cd frontend && npm test -- --include src/app/workspaces/calendar/calendar.routes.spec.ts`

Expected: PASS; initial activation waits, a 503 activates the inline error, and clicking next month makes one explicit request without a duplicate event-hook request.

- [ ] **Step 5: Commit R10**

```bash
git add frontend/src/app/workspaces/calendar/calendar.routes.ts frontend/src/app/workspaces/calendar/calendar.routes.spec.ts frontend/src/app/stores/calendar.store.ts frontend/src/app/stores/calendar.store.spec.ts frontend/src/app/workspaces/calendar/calendar.ts frontend/src/app/workspaces/calendar/calendar.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Calendar before activation"
```

### Task R11: Watchlist and Ticker Detail resolvers

**Files:**
- Create: `frontend/src/app/workspaces/watchlist/watchlist.routes.ts`
- Create: `frontend/src/app/workspaces/watchlist/watchlist.routes.spec.ts`
- Create: `frontend/src/app/workspaces/watchlist/ticker-detail.routes.ts`
- Create: `frontend/src/app/workspaces/watchlist/ticker-detail.routes.spec.ts`
- Modify: `frontend/src/app/stores/watchlist.store.ts`
- Modify: `frontend/src/app/stores/watchlist.store.spec.ts`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: R7 `TradesStore.resolve/load`, R8 `ChartStore.resolve/load`, route `:symbol`, R5 mutation refresh.
- Produces: `WatchlistStore.resolve(): Observable<void>`; Watchlist blocks on ticker rows; Ticker Detail blocks on chart data while its capped trade list remains secondary.

- [ ] **Step 1: Write route-specific blocking tests**

```ts
it('blocks Watchlist on ticker rows', async () => {
  const navigation = RouterTestingHarness.create('/watchlist');
  backend.expectOne('/api/v1/watchlist/tickers').flush({ tickers: WATCHLIST });
  expect((await navigation).routeNativeElement?.textContent).toContain('AAPL');
});

it('blocks Ticker Detail on chart but not its supporting trade table', async () => {
  const navigation = RouterTestingHarness.create('/watchlist/AAPL');
  backend.expectOne('/api/v1/market/chart/AAPL').flush(CHART);
  const harness = await navigation;
  expect(harness.routeNativeElement?.textContent).toContain('AAPL');
  backend.expectOne((req) => req.url === '/api/v1/trades' && req.params.get('ticker') === 'AAPL');
});
```

- [ ] **Step 2: Convert WatchlistStore to cold resolution**

```ts
const resolve = (): Observable<void> => routeRequest(api.tickers(), {
  start: () => patchState(store, { loading: true }),
  next: ({ tickers }) => patchState(store, {
    tickers, loading: false, error: null, loadedAt: new Date().toISOString(),
  }),
  error: (error) => patchState(store, {
    loading: false,
    error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
  }),
});
const load = (): void => { resolve().subscribe({ error: () => undefined }); };
```

Expose `resolve` and `load`, remove `withHooks`, and remove immediate `load()` calls after add/remove success; mutation response and `watchlist` event coalesce through R5.

- [ ] **Step 3: Add the Watchlist lazy route**

Create `watchlistRoutes` with `providers: [WatchlistStore]`, `runGuardsAndResolvers: 'always'`, `Loading Watchlist`, `onEvents('watchlist')`, and `resolveRoute(() => inject(WatchlistStore).resolve())`. Remove the component provider.

- [ ] **Step 4: Add the Ticker Detail lazy route**

```ts
export const tickerDetailRoutes: Routes = [{
  path: '', providers: [TradesStore, ChartStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Loading Ticker', onEvents('scan', 'trades', 'watchlist')),
  resolve: { ready: resolveRoute((route) =>
    inject(ChartStore).resolve(route.paramMap.get('symbol'))) },
  loadComponent: () => import('./ticker-detail').then((m) => m.TickerDetail),
}];
```

Remove component providers and the chart target effect. The resolver owns chart target/loading. Add an explicit secondary trade effect that reads `symbol` and `EventStream.changes('trades')`, sets the capped ticker query, and calls `trades.load()` once initially and after each trade event.

```ts
const tradeChanges = inject(EventStream).changes('trades');
effect(() => {
  tradeChanges();
  const ticker = this.symbol();
  untracked(() => {
    this.trades.setQuery({
      ticker, sort: '-opened_at', page: 1, per_page: TICKER_TRADES_CAP,
    });
    this.trades.load();
  });
});
```

- [ ] **Step 5: Verify Watchlist actions and ticker navigation cancellation**

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/watchlist.routes.spec.ts`

Expected: PASS with one refresh after add/remove success.

Run: `cd frontend && npm test -- --include src/app/workspaces/watchlist/ticker-detail.routes.spec.ts`

Expected: PASS; navigating AAPL -> MSFT cancels AAPL chart/trade requests and commits only MSFT.

- [ ] **Step 6: Commit R11**

```bash
git add frontend/src/app/workspaces/watchlist/watchlist.routes.ts frontend/src/app/workspaces/watchlist/watchlist.routes.spec.ts frontend/src/app/workspaces/watchlist/ticker-detail.routes.ts frontend/src/app/workspaces/watchlist/ticker-detail.routes.spec.ts frontend/src/app/stores/watchlist.store.ts frontend/src/app/stores/watchlist.store.spec.ts frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/workspaces/watchlist/ticker-detail.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Watchlist routes before activation"
```

### Task R12: Risk resolver

**Files:**
- Create: `frontend/src/app/workspaces/risk/risk.routes.ts`
- Create: `frontend/src/app/workspaces/risk/risk.routes.spec.ts`
- Modify: `frontend/src/app/stores/risk.store.ts`
- Modify: `frontend/src/app/stores/risk.store.spec.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.ts`
- Modify: `frontend/src/app/workspaces/risk/risk.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: `/api/v1/risk`, route request adapter, mutation refresh.
- Produces: `RiskStore.resolve(): Observable<void>`; refresh on `risk` or `trades`; shell killswitch request remains independent.

- [ ] **Step 1: Write failure-with-stale-data and cancellation tests**

```ts
it('keeps prior exposure when a refresh fails', () => {
  store.resolve().subscribe();
  backend.expectOne('/api/v1/risk').flush(RISK);
  store.resolve().subscribe();
  backend.expectOne('/api/v1/risk').flush(
    { error: { code: 'unavailable', message: 'down' } },
    { status: 503, statusText: 'Unavailable' },
  );
  expect(store.data()).toEqual(RISK);
  expect(store.error()).toContain('not responding');
});

it('cancels superseded risk resolution', () => {
  const sub = store.resolve().subscribe();
  const request = backend.expectOne('/api/v1/risk');
  sub.unsubscribe();
  expect(request.cancelled).toBe(true);
});
```

- [ ] **Step 2: Convert the primary risk request**

```ts
const resolve = (): Observable<void> => routeRequest(api.risk(), {
  start: () => patchState(store, { loading: true }),
  next: (data) => patchState(store, { data, loading: false, error: null }),
  error: (error) => patchState(store, {
    loading: false,
    error: error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
  }),
});
```

Expose `resolve`, retain a subscribing `load` for Retry, and remove the `risk`/`trades` event hook. Do not alter killswitch command response/error projection.

- [ ] **Step 3: Add route scope and readiness tests**

```ts
export const riskRoutes: Routes = [{
  path: '', providers: [RiskStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Loading Risk', onEvents('risk', 'trades')),
  resolve: { ready: resolveRoute(() => inject(RiskStore).resolve()) },
  loadComponent: () => import('./risk').then((m) => m.Risk),
}];
```

Remove the component provider. Add a route test that flushes `/api/v1/risk` with 503 and expects the existing error state; add a mutation-interceptor assertion that a successful killswitch POST calls `request('mutation')` once.

Run: `cd frontend && npm test -- --include src/app/workspaces/risk/risk.routes.spec.ts`

Expected: PASS.

- [ ] **Step 4: Commit R12**

```bash
git add frontend/src/app/workspaces/risk/risk.routes.ts frontend/src/app/workspaces/risk/risk.routes.spec.ts frontend/src/app/stores/risk.store.ts frontend/src/app/stores/risk.store.spec.ts frontend/src/app/workspaces/risk/risk.ts frontend/src/app/workspaces/risk/risk.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve Risk before activation"
```

### Task R13: System selected-tab resolver and settings draft safety

**Files:**
- Create: `frontend/src/app/workspaces/system/system.routes.ts`
- Create: `frontend/src/app/workspaces/system/system.routes.spec.ts`
- Modify: `frontend/src/app/stores/system.store.ts`
- Modify: `frontend/src/app/stores/system.store.spec.ts`
- Modify: `frontend/src/app/workspaces/system/system.ts`
- Modify: `frontend/src/app/workspaces/system/settings-tab.spec.ts`
- Modify: `frontend/src/app/app.routes.ts`

**Interfaces:**
- Consumes: `?tab=settings|logs|scan`, existing `dirty()`/`settingsStale()` contract, R5 mutation refresh.
- Produces: `SystemStore.resolveTab(tab: SystemTab): Observable<void>`; Settings reacts to `settings`, Scan to `scan|bot`, Logs to no push event; dirty Settings settles without overwriting.

- [ ] **Step 1: Write selected-tab and dirty-refresh tests**

```ts
it('loads only the selected System tab', () => {
  store.resolveTab('logs').subscribe();
  backend.expectOne((req) => req.url === '/api/v1/system/logs').flush(LOGS);
  backend.expectNone('/api/v1/system/settings');
  backend.expectNone('/api/v1/system/scan');
});

it('marks settings stale instead of requesting over a draft', () => {
  seedSettings();
  store.edit(field, 'local');
  store.resolveTab('settings').subscribe();
  backend.expectNone('/api/v1/system/settings');
  expect(store.settingsStale()).toBe(true);
  expect(store.currentValue(field)).toBe('local');
});
```

- [ ] **Step 2: Convert the three loaders to observables**

```ts
const resolveSettings = (): Observable<void> => {
  if (store.dirty()) {
    patchState(store, { settingsStale: true });
    return of(undefined);
  }
  return routeRequest(api.settings(), {
    start: () => patchState(store, { settingsLoading: true }),
    next: (settings) => patchState(store, {
      settings, settingsLoading: false, settingsError: null, settingsStale: false,
    }),
    error: (error) => patchState(store, {
      settingsLoading: false,
      settingsError: error.code === 'unavailable'
        ? 'The admin is not responding.' : error.message,
    }),
  });
};
const resolveLogs = (): Observable<void> => routeRequest(
  api.logs(store.logSource(), store.logLines()), {
    start: () => patchState(store, { logsLoading: true }),
    next: (logs) => patchState(store, { logs, logsLoading: false, logsError: null }),
    error: (error) => patchState(store, { logsLoading: false, logsError: error.message }),
  },
);
const resolveScan = (): Observable<void> => routeRequest(api.scanStatus(), {
  start: () => undefined,
  next: (scan) => patchState(store, { scan, scanError: null }),
  error: (error) => patchState(store, { scanError: error.message }),
});
const resolveTab = (tab: SystemTab): Observable<void> =>
  ({ settings: resolveSettings, logs: resolveLogs, scan: resolveScan })[tab]();
```

Expose subscribing `loadSettings/loadLogs/loadScan` wrappers for Retry, log controls, and explicit stale-data discard. Remove all SystemStore event hooks.

- [ ] **Step 3: Remove post-mutation duplicate reads**

After settings save/import, log clear, and scan commands, retain response projection but remove direct follow-up GETs that the mutation interceptor replaces. Keep `discardDraftAndReload()` explicit: it clears `draft`, `preview`, `formError`, and `settingsStale`, then calls `loadSettings()` because the user requested that reload directly.

```ts
discardDraftAndReload(): void {
  patchState(store, {
    draft: {}, preview: null, formError: null, settingsStale: false,
  });
  loadSettings();
}
```

- [ ] **Step 4: Add tab-aware route metadata**

```ts
const systemTab = (raw: string | null): SystemTab =>
  raw === 'logs' || raw === 'scan' ? raw : 'settings';
const refreshOnSystem: RefreshPredicate = (event, route) => {
  const tab = systemTab(route.queryParamMap.get('tab'));
  return tab === 'settings' ? event === 'settings'
    : tab === 'scan' ? event === 'scan' || event === 'bot'
    : false;
};
```

Create the lazy route with `providers: [SystemStore]`, always-run resolution, `Loading System`, and `resolveTab(systemTab(...))`. Remove the component provider.

- [ ] **Step 5: Verify query reruns and draft notice behavior**

Run: `cd frontend && npm test -- --include src/app/workspaces/system/system.routes.spec.ts`

Expected: PASS; `?tab=logs` waits only for logs, `?tab=scan` only for scan, and a settings event over a draft activates immediately with the existing data-changed notice.

Run: `cd frontend && npm test -- --include src/app/workspaces/system/settings-tab.spec.ts`

Expected: PASS; the notice preserves local input and explicit reload discards it.

- [ ] **Step 6: Commit R13**

```bash
git add frontend/src/app/workspaces/system/system.routes.ts frontend/src/app/workspaces/system/system.routes.spec.ts frontend/src/app/stores/system.store.ts frontend/src/app/stores/system.store.spec.ts frontend/src/app/workspaces/system/system.ts frontend/src/app/workspaces/system/settings-tab.spec.ts frontend/src/app/app.routes.ts
git commit -m "feat(v66): resolve the selected System tab"
```

### Task R14: Versions resolver and all-route contract gate

**Files:**
- Create: `frontend/src/app/workspaces/versions/versions.routes.ts`
- Create: `frontend/src/app/workspaces/versions/versions.routes.spec.ts`
- Modify: `frontend/src/app/stores/versions.store.ts`
- Modify: `frontend/src/app/stores/versions.store.spec.ts`
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/app.routes.spec.ts`
- Modify: `docs/features/features-admin.md`

**Interfaces:**
- Consumes: version-history endpoint and every lazy route exported by R6-R13.
- Produces: `VersionsStore.resolve(): Observable<void>`; static contract proving every in-scope authenticated route has route scope, resolver metadata, and `runGuardsAndResolvers: 'always'`.

- [ ] **Step 1: Convert VersionsStore and route scope**

```ts
const resolve = (): Observable<void> => routeRequest(api.versionHistory(), {
  start: () => patchState(store, { loading: true }),
  next: (data) => patchState(store, { data, loading: false, error: null }),
  error: (error) => patchState(store, {
    loading: false,
    error: error.code === 'unavailable'
      ? 'The admin is not responding -- the version history is unavailable.'
      : error.message,
  }),
});
```

Expose `resolve` and subscribing `load`, remove the `onInit` hook, and move `VersionsStore` to `versionsRoutes` with `runGuardsAndResolvers: 'always'`, `Loading Versions`, `onEvents('bot')`, and `resolveRoute(() => inject(VersionsStore).resolve())`.

- [ ] **Step 2: Write the complete route contract table**

```ts
const expected = [
  ['dashboard', ['account', 'trades']],
  ['trades', ['trades']],
  ['trades/:id', ['trades', 'journal']],
  ['analytics', ['analytics', 'jobs']],
  ['calendar', ['trades']],
  ['watchlist', ['watchlist']],
  ['watchlist/:symbol', ['scan', 'trades', 'watchlist']],
  ['risk', ['risk', 'trades']],
  ['system', ['settings', 'scan', 'bot']],
  ['versions', ['bot']],
] as const;
```

For every row, assert the top-level route retains `[authGuard]` and a lazy `loadChildren`; load its child route and assert route providers exist, `resolve.ready` exists, metadata has a non-empty loading label, and `runGuardsAndResolvers === 'always'`. For Analytics/System, invoke their predicate with each event and matching tab query maps rather than comparing a static list.

- [ ] **Step 3: Add navigation-level cancellation coverage**

```ts
it('cancels obsolete route and query resolutions', async () => {
  const dashboardNavigation = router.navigateByUrl('/dashboard');
  const dashboard = backend.expectOne('/api/v1/dashboard?mode=today');
  const riskNavigation = router.navigateByUrl('/risk');
  expect(dashboard.cancelled).toBe(true);
  backend.expectOne('/api/v1/risk').flush(RISK);
  await riskNavigation;
  expect(router.url).toBe('/risk');
  await dashboardNavigation;

  const pageOneNavigation = router.navigateByUrl('/trades?page=1');
  const pageOne = backend.expectOne((req) =>
    req.url === '/api/v1/trades' && req.params.get('page') === '1');
  const pageTwoNavigation = router.navigateByUrl('/trades?page=2');
  expect(pageOne.cancelled).toBe(true);
  const pageTwo = backend.expectOne((req) =>
    req.url === '/api/v1/trades' && req.params.get('page') === '2');
  pageTwo.flush(TRADES_PAGE_2);
  await pageTwoNavigation;
  expect(router.url).toBe('/trades?page=2');
  await pageOneNavigation;
});
```

- [ ] **Step 4: Document the UI data-readiness contract**

Add a concise Admin UI subsection stating: authenticated routes use lazy route-scoped resolvers; only initially visible data blocks; a one-second delayed overlay keeps shell chrome visible; non-auth errors enter inline workspace errors; live events and successful domain mutations debounce through same-URL resolver refresh; dirty settings/notes are preserved.

- [ ] **Step 5: Run the contract and Versions tests**

Run: `cd frontend && npm test -- --include src/app/app.routes.spec.ts`

Expected: PASS for all ten route shapes, cancellation, query reruns, and guard preservation.

Run: `cd frontend && npm test -- --include src/app/workspaces/versions/versions.routes.spec.ts`

Expected: PASS with one blocking version-history request.

- [ ] **Step 6: Commit R14**

```bash
git add frontend/src/app/workspaces/versions/versions.routes.ts frontend/src/app/workspaces/versions/versions.routes.spec.ts frontend/src/app/stores/versions.store.ts frontend/src/app/stores/versions.store.spec.ts frontend/src/app/workspaces/versions/versions.ts frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts docs/features/features-admin.md
git commit -m "test(v66): gate resolver coverage for every route"
```

# Phase 4 — Verification and release

**Parallelisation:** Sequential. R15 begins only after R6-R14 are committed; it is the sole full-suite run and the release marker follows that green result.

### Task R15: Full-suite verification and UI release

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json`

**Interfaces:**
- Consumes: all completed v66 route/store/UI tasks.
- Produces: one green full frontend suite, production Angular build, UI `1.10.0` release marker, regenerated version history, and no bot-version change.

- [ ] **Step 1: Run the frontend full suite once**

Run: `cd frontend && npm test`

Expected: PASS with no failed or skipped-by-error specs. If it is red, fix forward from the named regression and rerun this same gate until green; do not create a second verification task.

- [ ] **Step 2: Build the production bundle**

Run: `cd frontend && npm run build`

Expected: exit 0 with Angular production bundles emitted and no TypeScript/template error.

- [ ] **Step 3: Perform the manual timing and interaction check**

Run the app through the existing frontend dev/proxy workflow. Verify a sub-second route response shows no overlay; a throttled response shows `Loading <Route>` after one second; sidebar/topbar remain visible; the prior workspace is dimmed and cannot be clicked; rapid route changes render only the last route; a failed API response enters the destination's existing Retry state.

- [ ] **Step 4: Commit the UI release marker**

Compute the UTC stamp at execution time with PowerShell:

```powershell
(Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH-mm-ss')
```

Use `apply_patch` to set `VERSION.json` `ui` to `1.10.0` and `ui_updated` to that printed stamp. Leave `bot` and `bot_updated` unchanged.

```bash
git add VERSION.json
git commit -m "release(ui): 1.10.0 -- route-resolved data loading"
```

- [ ] **Step 5: Regenerate and verify version history**

Run: `python scripts/dev/build_version_matrix.py`

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`

Expected: `0 failed`, `0 xfailed`; the newest history pair is UI `1.10.0` with a real release commit, not `uncommitted`.

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(ui): 1.10.0 -- route-resolved data loading"
```

- [ ] **Step 6: Hand off branch completion**

Use `superpowers:finishing-a-development-branch`. After merge, follow `docs/claude/document-lifecycle.md`: remove the plan-named worktree/branch, move this plan and its v66 spec into their `implemented/` directories, repair references, and commit that close-out on `main`. Do not rerun either suite after a conflict-free merge.
