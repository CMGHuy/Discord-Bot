# v201 Instant admin page loads, part 4: SPA and verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Instant admin page loads](../specs/2026-10-29-v201-instant-admin-page-loads.md)
**Index:** [`_0-index.md`](2026-10-29-v201-instant-admin-page-loads_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract (MarketMeta, Endpoints, SPA contract) live there and bind the tasks below.

Part scope: V201-15 … V201-17 change the Angular SPA (`frontend/src/app`): routes stop blocking, one dashboard load, one shared tape request, the `market` event and live-values store, the `sb-market-value` cell, and the page wiring. V201-19 is the plan's one full-suite run. V201-20 is the post-deploy production check. V201-18 (Risk, Analytics, Calendar and sparkline labels) was retired with the spec split; that work is v204's.

**Paths and commands.** `<wt>` is the implementation worktree's absolute path. SPA paths below are relative to `<wt>/frontend/src/app/`. A single spec runs with `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/<path>.spec.ts` (the Angular unit-test builder compiles templates; a bare `vitest run` does not, so this replaces the index's shorthand). Never `cd`; stage explicit paths with `git -C <wt> add`.

**Shapes the SPA tasks rely on (backend, fixed in the index):** row quote fields `current_price, current_price_stale, price_as_of, price_age_s, price_refreshing, price_error` on trade rows (list and detail), watchlist rows and tape rows; `market_meta: MarketMeta` on `/dashboard`, `/trades` and `/trades/<id>`; `GET /market/updates` and `POST /market/refresh` as in "Endpoints". Every SPA read of a meta field is optional, so an absent key renders "no label" and never throws.

# Phase: SPA (V201-15 … V201-17)

### Task V201-15: SPA: routes stop blocking; one dashboard load; one shared tape request

**Model:** sonnet — the same swap across 15 route files plus one small shared service, with every behaviour pinned by specs written first.

**Files:**
- Modify: `frontend/src/app/routing/route-resolver.ts` (`resolveRoute` replaced by `startRoute`), `frontend/src/app/routing/route-resolver.spec.ts`
- Modify: `frontend/src/app/routing/route-loading.service.ts` (doc comment only), `frontend/src/app/routing/route-loading.service.spec.ts`
- Modify (swap `resolveRoute(` → `startRoute(` and the import): `frontend/src/app/workspaces/analytics/analytics.routes.ts`, `frontend/src/app/workspaces/calendar/calendar.routes.ts` (both routes), `frontend/src/app/workspaces/cancels/cancels.routes.ts`, `frontend/src/app/workspaces/plans/plan-detail.routes.ts`, `frontend/src/app/workspaces/reports/reports.routes.ts`, `frontend/src/app/workspaces/research/research.routes.ts`, `frontend/src/app/workspaces/risk/risk.routes.ts`, `frontend/src/app/workspaces/system/system.routes.ts`, `frontend/src/app/workspaces/trades/trade-detail.routes.ts`, `frontend/src/app/workspaces/trades/trades.routes.ts` (also its doc comment on `savedPerPage`), `frontend/src/app/workspaces/versions/versions.routes.ts`, `frontend/src/app/workspaces/watchlist/ticker-detail.routes.ts`, `frontend/src/app/workspaces/watchlist/watchlist.routes.ts`, and any `*.routes.spec.ts` that names `resolveRoute`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.routes.ts` (drop `resolve` and the `runGuardsAndResolvers` rule), `frontend/src/app/stores/dashboard.store.spec.ts`
- Modify: `frontend/src/app/stores/tape.store.ts`, `frontend/src/app/stores/tape.store.spec.ts`, `frontend/src/app/stores/market-index.store.ts`, `frontend/src/app/stores/market-index.store.spec.ts` (create it if absent)
- Modify: `frontend/src/app/api/interceptors.ts` (`routeRefreshInterceptor` only), `frontend/src/app/api/interceptors.spec.ts`
- Create: `frontend/src/app/stores/tape-feed.ts`, `frontend/src/app/stores/tape-feed.spec.ts`

**Interfaces:**
- Consumes: nothing from backend tasks (fakes stand in). Existing `PreferencesStore.resolve()`, `SessionStore.expire(url)`, `ApiError.isAuth`, `EventStream.changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS })`, `ApiClient.tape(symbols)`.
- Produces: `startRoute(load: (route: ActivatedRouteSnapshot) => Observable<void>): ResolveFn<boolean>`. `resolveRoute` no longer exists: `git -C <wt> grep -n resolveRoute -- frontend/src` is empty when done. The file `route-resolver.ts` stays, holding `startRoute` (a non-blocking start keeps every URL-driven re-run and `RouteRefreshService` reload working without rewriting 16 loads). `TapeFeed` (`stores/tape-feed.ts`, `providedIn: 'root'`): `register(owner: string, symbols: Signal<string[]>): void`, `rows: Signal<Record<string, TapeRow>>` (keyed by upper-case symbol), `asOf: Signal<string | null>`, `loading: Signal<boolean>`, `refresh(): void`. V201-17 adds the `market` trigger to `TapeFeed`.

**Behaviour fixed here:**
- **`startRoute` never blocks.** It *starts* `preferences.resolve().pipe(switchMap(() => runInInjectionContext(injector, () => load(route))))` with `subscribe`, then returns `of(true)`. The injector capture and its comment move over unchanged (the NG0203 trap still applies). Errors in the background load: an `ApiError` with `isAuth` calls `session.expire(state.url)`. Anything else is dropped, because the stores already own their error state through `routeRequest`.
- **One load in flight per route definition.** Background subscriptions sit in a module-level `WeakMap<Route, Subscription>` keyed by `route.routeConfig`. A re-run (query change, or a same-URL reload from `RouteRefreshService`) unsubscribes the previous one first. With no `routeConfig` there is no cancelling. `injector.get(DestroyRef).onDestroy(...)` unsubscribes when the route's environment injector is destroyed.
- The page renders at once. `RouteLoadingService` keeps its code. Its `ResolveStart`/`ResolveEnd` pair now closes within the same navigation, so the 1 s veil never shows, and the spec pins that.
- **Dashboard: one `/dashboard` per navigation.** The route has no `resolve` key and no `runGuardsAndResolvers` rule (the drawer rule only existed to stop resolver re-runs). The store's existing `onInit` effect is the one initial load, and `account`/`trades` events refetch it as today. `routeData('Dashboard', onEvents())` stays.
- **`TapeFeed`: one `/market/tape` per poll.** `register` stores the owner's signal in a signal-held map, replacing an earlier signal for the same owner. `merged = computed(...)` is the union of every owner's symbols: upper-cased, de-duplicated, in registration order and then symbol order, with an `equal` that compares arrays element by element. A constructor `effect` reads the `scan` throttle and `merged()`, then calls `refresh()`. `refresh()` coalesces: it queues one microtask (`queueMicrotask`), so every call in the same tick (both stores' `onInit`, the shell's two `load()` calls) makes **one** `api.tape(merged())` request. An empty union issues nothing and sets `rows` to `{}`. A latest-request counter drops out-of-order replies, and an error keeps the previous rows (the existing tape comment's reasoning).
- `TapeStore` keeps its public surface (`symbols`, `visible`, `rows`, `asOf`, `loading`, `error`, `load`, `toggle`). It calls `feed.register('tape', store.symbols)` in `onInit`. `rows` become `symbols().map((s) => feed.rows()[s]).filter(Boolean)`, sorted as today; `asOf` is `feed.asOf()` and `load()` is `feed.refresh()`. Its own `scan` effect and `api.tape` call go. `MarketIndexStore` does the same with owner `'index'` and the constant `INDEX_SYMBOLS` (rows in `INDEX_SYMBOLS` order; a missing symbol is skipped).
- `routeRefreshInterceptor` skips any request whose URL ends with `/market/refresh`. A Refresh click queues a fetch, and it must never re-navigate and refetch the page.

- [ ] **Step 1: Write the failing resolver specs** (rewrite `routing/route-resolver.spec.ts`: keep its imports, swap `resolveRoute` → `startRoute`, keep the three existing cases, then add the cases below)

```ts
import { EnvironmentInjector, createEnvironmentInjector } from '@angular/core';
import { Route } from '@angular/router';
import { NEVER, Subject, finalize } from 'rxjs';

const routed = (config: Route = {}) => ({ routeConfig: config }) as unknown as ActivatedRouteSnapshot;

function setup(expire = vi.fn()) {
  TestBed.configureTestingModule({ providers: [
    { provide: PreferencesStore, useValue: { resolve: () => of(undefined) } },
    { provide: SessionStore, useValue: { expire } },
  ] });
  return expire;
}

const pending = (onCancel: () => void) => new Subject<void>().pipe(finalize(onCancel));

describe('startRoute (v201: routes never block)', () => {
  it('resolves true at once while the feature load is still pending', () => {
    setup();
    let value: boolean | undefined;
    const resolver = startRoute(() => NEVER);
    (TestBed.runInInjectionContext(() => resolver(routed(), state)) as Observable<boolean>)
      .subscribe((v) => { value = v; });
    expect(value).toBe(true);
  });

  it('expires the session when the background load fails on auth', () => {
    const expire = setup();
    const resolver = startRoute(() => throwError(() => new ApiError('auth', 401, 'expired')));
    TestBed.runInInjectionContext(() => resolver(routed(), state));
    expect(expire).toHaveBeenCalledWith('/trades?page=2');
  });

  it('drops a non-auth failure without throwing', () => {
    const expire = setup();
    const resolver = startRoute(() => throwError(() => new Error('boom')));
    expect(() => TestBed.runInInjectionContext(() => resolver(routed(), state))).not.toThrow();
    expect(expire).not.toHaveBeenCalled();
  });

  it('a re-run of the same route cancels the previous load', () => {
    setup();
    const config: Route = {};
    let cancelled = 0;
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    TestBed.runInInjectionContext(() => resolver(routed(config), state));
    TestBed.runInInjectionContext(() => resolver(routed(config), state));
    expect(cancelled).toBe(1);
  });

  it('loads of two different routes do not cancel each other', () => {
    setup();
    let cancelled = 0;
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    TestBed.runInInjectionContext(() => resolver(routed({}), state));
    TestBed.runInInjectionContext(() => resolver(routed({}), state));
    expect(cancelled).toBe(0);
  });

  it('stops the load when the route injector is destroyed', () => {
    setup();
    let cancelled = 0;
    const child = createEnvironmentInjector([], TestBed.inject(EnvironmentInjector));
    const resolver = startRoute(() => pending(() => { cancelled += 1; }));
    child.runInContext(() => resolver(routed(), state));
    child.destroy();
    expect(cancelled).toBe(1);
  });
});
```

Update the existing auth case: it now asserts that `expire` was called and that the resolver emitted `true` (it no longer completes empty).

- [ ] **Step 2: Write the failing loading, dashboard, interceptor and tape specs**

In `routing/route-loading.service.spec.ts`, add a new case, `never shows the veil for a route whose data is still loading`. Register a `Router` with one route `{ path: 'x', data: routeData('X', onEvents()), resolve: { ready: startRoute(() => NEVER) }, component: <the spec's stub component> }` and call `vi.useFakeTimers()`. Navigate to `/x`, run `await vi.advanceTimersByTimeAsync(ROUTE_LOADING_DELAY_MS + 500)`, then assert `service.visible() === false` and `service.pending() === false`.

`stores/dashboard.store.spec.ts`, new cases:

```ts
it('the dashboard route has no resolver: the store load is the only one', async () => {
  const { dashboardRoutes } = await import('../workspaces/dashboard/dashboard.routes');
  expect(dashboardRoutes[0].resolve).toBeUndefined();
  expect(dashboardRoutes[0].runGuardsAndResolvers).toBeUndefined();
});

it('issues exactly one GET /dashboard when created', () => {
  const { api } = setup();            // the spec's existing setup helper
  TestBed.tick();
  expect(api.dashboard).toHaveBeenCalledTimes(1);
});
```

In `api/interceptors.spec.ts`, add a new case, `a POST to /api/v1/market/refresh never asks for a route refresh`. Send `POST /api/v1/market/refresh` through the interceptor chain the spec already builds, flush 202, and assert that `RouteRefreshService.requestMutationRefresh` was not called. In the same spec, a `POST /api/v1/trades/x/close` must still call it.

`stores/tape-feed.spec.ts` (fake `ApiClient.tape`, `FakeEventStream` copied from `dashboard.store.spec.ts`, `provideZonelessChangeDetection()`):

```ts
const row = (symbol: string): TapeRow => ({ symbol, price: 1, change_pct: 0, context_kind: null, context_label: null, sort_rank: 2 });
const flush = async () => { TestBed.tick(); await Promise.resolve(); };

it('two owners registered in one tick make one request for the union', async () => {
  feed.register('tape', signal(['nvda', 'MSFT']));
  feed.register('index', signal(['^GSPC', 'MSFT']));
  feed.refresh(); feed.refresh();
  await flush();
  expect(api.tape).toHaveBeenCalledTimes(1);
  expect(api.tape).toHaveBeenCalledWith(['NVDA', 'MSFT', '^GSPC']);
});

it('rows are keyed by upper-case symbol and asOf is the reply stamp', async () => {
  api.tape.mockReturnValue(of({ as_of: '2026-10-29T14:00:00Z', rows: [row('NVDA'), row('^GSPC')] }));
  feed.register('tape', signal(['NVDA'])); feed.register('index', signal(['^GSPC']));
  await flush();
  expect(Object.keys(feed.rows())).toEqual(['NVDA', '^GSPC']);
  expect(feed.asOf()).toBe('2026-10-29T14:00:00Z');
});

it('an empty union sends nothing and clears rows', async () => {
  feed.register('tape', signal([]));
  await flush();
  expect(api.tape).not.toHaveBeenCalled();
  expect(feed.rows()).toEqual({});
});
```

Add these further cases, each as real code: `a throttled scan event refetches once for everyone` (`events.raise('scan')`, flush, `api.tape` called twice in all); `changing one owner's symbols refetches the new union once` (set the owner's signal, flush, two calls, the last argument holds the new symbol); `an error keeps the previous rows` (second reply `throwError`, `rows()` unchanged); `a late reply from an older request is dropped` (two `Subject` replies answered out of order; `rows()` come from the newer one).

`stores/tape.store.spec.ts`: replace the cases that count `api.tape` calls made *by the store* with cases against a fake `TapeFeed` (`{ register: vi.fn(), rows: signal({...}), asOf: signal(null), loading: signal(false), refresh: vi.fn() }`). Keep the sort-by-`sort_rank` and `toggle` cases. Add `registers its symbols with the feed as owner "tape"`. `stores/market-index.store.spec.ts`: `registers INDEX_SYMBOLS as owner "index"` and `rows follow INDEX_SYMBOLS order, skipping a symbol the feed lacks`.

- [ ] **Step 3: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/routing/route-resolver.spec.ts --include src/app/routing/route-loading.service.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/api/interceptors.spec.ts --include src/app/stores/tape-feed.spec.ts --include src/app/stores/tape.store.spec.ts --include src/app/stores/market-index.store.spec.ts`
Expected: FAIL (build error: `startRoute` and `./tape-feed` not found).

- [ ] **Step 4: Implement**

`route-resolver.ts`: `startRoute` as fixed above, under 30 lines. Route files: swap the import and the call only, plus the `trades.routes.ts` comment ("`startRoute` resolves preferences before this runs"). `dashboard.routes.ts`: delete the `resolve` line, the `runGuardsAndResolvers` line and its comment, and the imports that are no longer used (`inject`, `resolveRoute`, `rerunExceptQueryParam`; `DashboardStore` stays in `providers`). `route-rerun.ts` stays unless `git -C <wt> grep -n rerunExceptQueryParam -- frontend/src` shows nothing else imports it, in which case delete it and its spec. Implement `tape-feed.ts`, `tape.store.ts`, `market-index.store.ts` and `interceptors.ts` as fixed above. Update the class comments of `TapeStore`/`MarketIndexStore` to say the request is the feed's.

- [ ] **Step 5: Run every touched spec and the routes specs**

Run: the Step 3 command plus `--include 'src/app/workspaces/**/*.routes.spec.ts' --include src/app/app.routes.spec.ts --include src/app/shell/shell.spec.ts --include src/app/shell/tape/tape.spec.ts`
Expected: PASS. A routes spec that drove `resolve.ready` and then flushed `HttpTestingController` still passes, because the background load issues the same request. If a spec asserted that the resolver *waited*, change it to assert that the request was issued.

- [ ] **Step 6: Verify no blocking resolver is left, then commit**

Run: `git -C <wt> grep -n "resolveRoute" -- frontend/src` → no output.

```bash
git -C <wt> add frontend/src/app/routing frontend/src/app/workspaces/*/*.routes.ts frontend/src/app/workspaces/*/*.routes.spec.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/stores/tape-feed.ts frontend/src/app/stores/tape-feed.spec.ts frontend/src/app/stores/tape.store.ts frontend/src/app/stores/tape.store.spec.ts frontend/src/app/stores/market-index.store.ts frontend/src/app/stores/market-index.store.spec.ts frontend/src/app/api/interceptors.ts frontend/src/app/api/interceptors.spec.ts
git -C <wt> commit -m "feat(v201): SPA routes stop blocking; one dashboard load; one shared tape request"
```

### Task V201-16: SPA: `market` event, live-values store, `sb-market-value` cell, refresh button, stalled banner

**Model:** sonnet — new leaf components and one store against a fixed JSON contract. The partner decisions on spinners and closed-market labels are pinned by specs written first.

**Files:**
- Modify: `frontend/src/app/api/models.ts`, `frontend/src/app/api/api-client.ts`, `frontend/src/app/api/event-stream.ts`, `frontend/src/app/api/event-stream.spec.ts`
- Modify: `frontend/src/app/ui/age-hint.ts`, `frontend/src/app/ui/age-hint.spec.ts`
- Modify: `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts` (provide a fake `LiveValuesStore`)
- Create: `frontend/src/app/stores/live-values.store.ts`, `frontend/src/app/stores/live-values.store.spec.ts`
- Create: `frontend/src/app/ui/market-value.ts`, `frontend/src/app/ui/market-value.spec.ts`, `frontend/src/app/ui/incomplete-note.ts`, `frontend/src/app/ui/incomplete-note.spec.ts`, `frontend/src/app/ui/market-refresh.ts`, `frontend/src/app/ui/market-refresh.spec.ts`
- Create: `frontend/src/app/shell/refresher-banner.ts`, `frontend/src/app/shell/refresher-banner.spec.ts`
- Modify: `tests/admin/test_sse_contract.py` (delete `SPA_PENDING`; V201-6 left it for this task)

**Interfaces:**
- Consumes: the index's "Endpoints" and "MarketMeta" JSON (V201-10, V201-7); `notify.CHANNELS` holds `"market"` (V201-6). Existing `CLOCK` (`ui/clock.ts`), `ageText`, `Spinner` (`sb-spinner`), `EventStream`.
- Produces (the index's "SPA contract", exactly): `MarketMeta`, `QuoteUpdate`, `MarketStatus`, `MarketUpdates`, `RowQuoteFields`; `ApiClient.marketUpdates(since)`, `ApiClient.refreshMarket(body)`; `'market'` in `EventName`/`EVENT_NAMES`; `LiveValuesStore`; `marketAgeLabel`; `sb-market-value`, `sb-incomplete-note`, `sb-market-refresh`, `sb-refresher-banner`. Added for V201-17 (same files): `overlayQuote(row, update)` and `LiveValuesStore.patchRows(rows, symbolOf)`, both specified below. Also the optional `market_meta` fields listed under models. Nothing snapshot-specific is built here (no `SnapshotUpdate`, `snapshot(key)`, `kind`/`staleInputs` inputs or snapshot limit); v204 adds them.

**Behaviour fixed here:**
- **models.ts.** `MarketMeta` mirrors the index's key list (`source: 'request' | 'snapshot'`). `QuoteUpdate {symbol; price: number | null; as_of: string | null; refreshing: boolean; error: string | null}`. `MarketStatus {session: 'regular' | 'extended' | 'closed'; last_close_at: string | null; stale_price_s: number | null; heartbeat: {beat_at: string | null; cadence_s: number; stalled: boolean}}`. `MarketUpdates {cursor: string; quotes: QuoteUpdate[]; status: MarketStatus}`. `RowQuoteFields` has every field optional (`current_price?: number | null; price_as_of?: string | null; price_age_s?: number | null; price_refreshing?: boolean; price_error?: string | null`), so an older server and every existing spec literal still type-check. `TradeRow`, `Ticker` and `TapeRow` `extends RowQuoteFields`. Optional `market_meta?: MarketMeta` goes on `Dashboard`, `TradeCollection` and `TradeDetail`.
- **ApiClient.** `marketUpdates(since: string | null)` is a `GET ${base}/market/updates`, with `params: {since}` only when non-null. `refreshMarket(body)` is a `POST ${base}/market/refresh` with `this.skipRouteRefresh`.
- **event-stream.ts.** `'market'` is appended to `EventName` and as the last element of `EVENT_NAMES`. The class comment gains one sentence: `market` is answered by a catch-up fetch (`/market/updates`), still never a patch from the event itself.
- **`marketAgeLabel(asOf, nowMs, status)`** in `ui/age-hint.ts` (the function only; `sb-age-hint` stays for its remaining callers until V201-17 moves those on its pages):
  1. `status?.heartbeat.stalled` → `{text: ageText(age) , tone: 'stalled'}` (text `null` when `asOf` is null).
  2. else `status?.session === 'closed'` → tone `'closed'`. With `asOf` no more than 1 h before `last_close_at` (or after it): text `last close · <Ddd HH:MM> ET` from `last_close_at`. Otherwise (an older price): `as of <Ddd HH:MM> ET` from `asOf`. `asOf` null → text `null`.
  3. else `age = (nowMs - Date.parse(asOf)) / 1000`; the limit is `status?.stale_price_s`. Tone `'stale'` when the limit is set and `age > limit`, else `'fresh'`. Text `ageText(age)`.
  The ET format is `Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})`, read through `formatToParts` so the output is exactly `Fri 16:00`.
- **`LiveValuesStore`** (`@Injectable({providedIn: 'root'})` class).
  - State: `cursor: string | null` and signal maps `quotes: Record<SYMBOL, QuoteUpdate>` and `local: Record<'quote:SYM', number>` (request time in ms).
  - `sync()` calls `api.marketUpdates(cursor)`. On success it merges every item (last one wins, symbols upper-cased), sets `status` and `cursor`, and clears a `local` key whose update arrived with `refreshing === false`, or with an `error`. If a sync is already in flight it sets `again = true` and returns; the finished sync then runs once more. So no event is lost and no request is cancelled. A failed sync keeps every value and the cursor.
  - **Triggers:** one `sync()` at construction; an effect on `events.changes('market')` (unthrottled; partner decision: the refresher raises it when its marks are set and again when values land, so the spinner shows for its own refreshes); an effect on `events.state()` that syncs on each change to `'live'`; and `setInterval(STATUS_POLL_MS = 60_000)`, skipped while `document.hidden`. The poll is what notices a dead refresher, which raises no events.
  - `quote(symbol)` returns a memoised `computed` per symbol. It is the stored update, with `refreshing: true` while a `local` key is set (a fresh `{price: null, as_of: null, ...}` shell when nothing is stored), else the stored update or `null`.
  - `requestRefresh(symbols)` sets the `local` keys at once, calls `api.refreshMarket`, and clears them on an error or after `LOCAL_REFRESH_TIMEOUT_MS = 120_000` (a spinner never outlives the server's mark timeout). `stalled = computed(() => status()?.heartbeat.stalled === true)`.
  - `patchRows<T extends RowQuoteFields>(rows: T[], symbolOf: (r: T) => string): T[]` maps `overlayQuote(row, this.quote(symbolOf(row))())`. It reads signals, so a `computed` that calls it re-runs on updates.
- **`overlayQuote(row, update)`** (exported, pure): `update === null` returns `row` itself. Otherwise `newer = update.price !== null && update.as_of !== null && (!row.price_as_of || Date.parse(update.as_of) > Date.parse(row.price_as_of))`. When `newer`: `current_price = update.price`, `price_as_of = update.as_of`, `price_age_s = null`. Always: `price_refreshing = update.refreshing`, `price_error = update.error`. It returns a new object only when a field changed.
- **`sb-market-value`** (`ui/market-value.ts`). Inputs: `asOf: string | null`, `refreshing = false`, `error: string | null = null`. It reads `CLOCK` and `LiveValuesStore.status()`; `label = marketAgeLabel(asOf, clock(), status)`, and `tone` is the label's tone. Markup, whose class names V201-20's label check reads:
  `<span class="mv" [attr.data-tone]="tone()"><span class="mv-value"><ng-content /></span><span class="mv-meta">@if (spinning()) {<sb-spinner label="Refreshing" />} @if (label().text; as t) {<span class="mv-age">{{ t }}</span>} @if (error()) {<span class="mv-err" [attr.title]="error()">refresh failed</span>}</span></span>`, where `spinning = refreshing && !error`. With `asOf === null` the value slot is hidden (`.mv-value` gets `hidden`), so a never-priced cell is the spinner alone. Styles: `.mv {display: inline-flex; flex-wrap: wrap; align-items: baseline; column-gap: var(--space-4); max-width: 100%}`, `.mv-meta {display: inline-flex; gap: var(--space-4); font-size: var(--text-micro); color: var(--text-faint); font-variant-numeric: tabular-nums; --spinner-size: 10px}`, `[data-tone=stale] .mv-age, [data-tone=stalled] .mv-age {color: var(--warn)}`, `.mv-err {color: var(--neg)}`, and below `BREAKPOINTS.sm` (640px) `.mv {flex-direction: column; align-items: flex-start} .mv-meta {white-space: normal; overflow-wrap: anywhere}`. The meta wraps under the value and never widens a column.
- **`sb-incomplete-note`**: input `missing: number`; renders `<span class="incomplete" role="note">incomplete: N positions unpriced</span>` (`1 position` singular) in `--warn`, and nothing at 0.
- **`sb-market-refresh`**: input `symbols: string[] = []`. It renders `<button sb-button variant="secondary" type="button" class="sb-hit">Refresh</button>`, disabled when the list is empty, and a click calls `requestRefresh(symbols())`.
- **`sb-refresher-banner`**: `@if (live.stalled()) {<div class="refresher-strip" role="alert">Prices paused: refresher not running</div>}`, styled like `.killswitch-strip` but with `--warn`/`--warn-soft`. `shell.html` places it directly after the killswitch block, and `shell.ts` imports it.

- [ ] **Step 1: Write the failing specs**

`ui/age-hint.spec.ts`, new `describe('marketAgeLabel')`. A status helper: `const st = (session, stalled = false) => ({session, last_close_at: '2026-10-30T20:00:00Z', stale_price_s: 120, heartbeat: {beat_at: null, cadence_s: 30, stalled}})`. `NOW = Date.parse('2026-10-31T15:00:00Z')` (a Saturday).

```ts
it('fresh price in regular hours reads its age', () =>
  expect(marketAgeLabel(new Date(NOW - 12_000).toISOString(), NOW, st('regular'))).toEqual({ text: '12 s ago', tone: 'fresh' }));
it('price older than the regular limit is stale', () =>
  expect(marketAgeLabel(new Date(NOW - 180_000).toISOString(), NOW, st('regular')).tone).toBe('stale'));
it('closed market reads last close, not stale', () =>
  expect(marketAgeLabel('2026-10-30T19:59:58Z', NOW, st('closed'))).toEqual({ text: 'last close · Fri 16:00 ET', tone: 'closed' }));
it('closed market with a price older than the close shows its own time', () =>
  expect(marketAgeLabel('2026-10-28T19:40:00Z', NOW, st('closed'))).toEqual({ text: 'as of Wed 15:40 ET', tone: 'closed' }));
it('stalled feed wins over closed', () =>
  expect(marketAgeLabel('2026-10-30T19:59:58Z', NOW, st('closed', true)).tone).toBe('stalled'));
it('no as-of gives no text', () => expect(marketAgeLabel(null, NOW, st('regular')).text).toBeNull());
it('no status yet reads the age, fresh', () =>
  expect(marketAgeLabel(new Date(NOW - 5_000).toISOString(), NOW, null)).toEqual({ text: '5 s ago', tone: 'fresh' }));
```

`stores/live-values.store.spec.ts` (fake `ApiClient` `{marketUpdates: vi.fn(), refreshMarket: vi.fn(() => of({queued: 1}))}`, the `FakeEventStream` from `dashboard.store.spec.ts` extended with `state = signal('connecting')`, `vi.useFakeTimers()`). Cases, each as real code:
- `syncs once at start with no cursor, then with the returned cursor`: calls are `[null]`, then after `raise('market')` `['c1']`.
- `refetches on every market event` (two raises separated by `TestBed.tick()` → 3 calls in all).
- `shows refreshing from marks the refresher set on its own`: the first event replies `quotes: [{symbol: 'MSFT', price: 410, as_of: A, refreshing: true, error: null}]` → `quote('msft')()?.refreshing === true`. The second replies `refreshing: false, price: 412` → the price is 412 and `refreshing` false.
- `an event during an in-flight sync runs one more sync after it` (a `Subject` reply: raise twice while pending → exactly one extra call after it resolves).
- `requestRefresh marks the keys refreshing at once and posts them`: `quote('NVDA')()` is `{symbol: 'NVDA', price: null, as_of: null, refreshing: true, error: null}`, and `refreshMarket` was called with `{symbols: ['NVDA']}`.
- `a local refresh mark clears after LOCAL_REFRESH_TIMEOUT_MS` (`vi.advanceTimersByTime(120_000)` → `quote('NVDA')()` is `null`).
- `error stops the spinner` (an update with `error: 'no quote'` → `refreshing` false in `overlayQuote(row, q)` and in the cell).
- `polls status every 60 s` and `syncs when the stream goes live`.
- `stalled follows status.heartbeat.stalled`.
- `overlayQuote`: keeps the row when the update is older, takes price and as-of when newer, keeps the last price when the update has `price: null`, and returns the same object when nothing changed.

`ui/market-value.spec.ts` (fixed `CLOCK` signal, fake `LiveValuesStore {status: signal(st('regular'))}`; host component `<sb-market-value [asOf]="a" [refreshing]="r" [error]="e">187.42</sb-market-value>`):
- `shows the value and its age`: text contains `187.42` and `.mv-age` reads `12 s ago`.
- `spinner beside the value while refreshing`: `sb-spinner` present and `.mv-value` visible.
- `spinner alone when no value was ever stored` (`asOf` null, refreshing): `.mv-value` hidden.
- `error stops the spinner`: no `sb-spinner`, `.mv-err` reads `refresh failed`, and `.mv-age` still shows the age.
- `a stale price takes the stale tone`: `asOf` 180 s before the clock in regular hours → `data-tone="stale"`.
- `the age ticks with the clock`: set the clock 60 s later → `1 min ago`.

`ui/incomplete-note.spec.ts`: `0 → empty`, `1 → "incomplete: 1 position unpriced"`, `3 → "incomplete: 3 positions unpriced"`. `ui/market-refresh.spec.ts`: a click calls `requestRefresh(['MSFT'])`; disabled with an empty list. `shell/refresher-banner.spec.ts`: hidden when `stalled()` is false; with `stalled()` true, `role=alert` and the exact copy `Prices paused: refresher not running`. `api/event-stream.spec.ts`: `EVENT_NAMES` ends with `'market'`, and a `market` SSE message bumps `changes('market')`.

`tests/admin/test_sse_contract.py`: delete the `SPA_PENDING` line and restore the final assertion to `assert listened == EXPECTED_EVENTS`.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/ui/age-hint.spec.ts --include src/app/stores/live-values.store.spec.ts --include src/app/ui/market-value.spec.ts --include src/app/ui/incomplete-note.spec.ts --include src/app/ui/market-refresh.spec.ts --include src/app/shell/refresher-banner.spec.ts --include src/app/api/event-stream.spec.ts`, then `python <wt>/scripts/dev/testrun.py file tests/admin/test_sse_contract.py`
Expected: SPA build FAILS on the missing modules. The Python test FAILS (`listened` lacks `"market"`).

- [ ] **Step 3: Implement** the files above as fixed. `LiveValuesStore`'s private helpers (`merge`, `clearLocal`, `startPoll`) keep each method short. Clear the poll interval on `DestroyRef` (root: on app teardown and in TestBed resets).

- [ ] **Step 4: Run the specs, the shell spec and the contract test**

Run: the Step 2 commands plus `--include src/app/shell/shell.spec.ts --include src/app/api/api-client.spec.ts`
Expected: PASS. `test_sse_contract.py` PASS (the SPA now subscribes to `market`).

- [ ] **Step 5: Check the cell at three widths**

Add one `sb-market-value` example (value, age, spinner, error, closed label) to `workspaces/gallery/gallery.ts` beside the existing `sb-age-hint` example. Run `npm --prefix <wt>/frontend exec -- ng serve`, open `/app/ui` at 390, 768 and 1440 px (Playwright, `frontend/scripts/browse.mjs shots --base http://localhost:4200 --path /app/ui --widths 1440,768,390`), and confirm the meta wraps under the value at 390 px with no horizontal page scroll (`page-scroll-x: 0`).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/event-stream.ts frontend/src/app/api/event-stream.spec.ts frontend/src/app/ui/age-hint.ts frontend/src/app/ui/age-hint.spec.ts frontend/src/app/stores/live-values.store.ts frontend/src/app/stores/live-values.store.spec.ts frontend/src/app/ui/market-value.ts frontend/src/app/ui/market-value.spec.ts frontend/src/app/ui/incomplete-note.ts frontend/src/app/ui/incomplete-note.spec.ts frontend/src/app/ui/market-refresh.ts frontend/src/app/ui/market-refresh.spec.ts frontend/src/app/shell/refresher-banner.ts frontend/src/app/shell/refresher-banner.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts frontend/src/app/workspaces/gallery/gallery.ts tests/admin/test_sse_contract.py
git -C <wt> commit -m "feat(v201): SPA market event, live values, market-value cell, refresh control, stalled banner"
```

### Task V201-17: SPA: Dashboard, Trades, Trade detail, Watchlist and tape render market cells; Refresh controls

**Model:** sonnet — template and store wiring over the V201-16 primitives across four workspaces, each pinned by a spec.

> The Dashboard equity sparkline's label is not in this task: it moves to v204 with the snapshot pages, and the sparkline renders as today.

**Files:**
- Modify: `frontend/src/app/stores/trades.store.ts` (+spec), `frontend/src/app/stores/trade-detail.store.ts` (+spec), `frontend/src/app/stores/watchlist.store.ts` (+spec), `frontend/src/app/stores/dashboard.store.ts` (+spec), `frontend/src/app/stores/tape-feed.ts` (+spec)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (`pnlCell` and the second P&L cell, KPI wiring, positions panel actions), `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` (+spec), `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (page actions, `now` column cell), `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/trades/trades.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/outcome-tiles.ts` (+spec), `frontend/src/app/workspaces/trades/outcome-strip.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/trade-detail.spec.ts`
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (`priceCell`), `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`
- Modify: `frontend/src/app/shell/tape/tape.ts`, `frontend/src/app/shell/tape/tape.spec.ts`

**Interfaces:**
- Consumes (V201-16): `LiveValuesStore.patchRows(rows, symbolOf)`, `.quote(symbol)`, `overlayQuote`; `sb-market-value` (`MarketValue`), `sb-incomplete-note` (`IncompleteNote`), `sb-market-refresh` (`MarketRefresh`); `MarketMeta`, `RowQuoteFields`. (V201-15): `TapeFeed`. Backend shapes: row quote fields on trade, watchlist and tape rows; `market_meta` on `/dashboard`, `/trades` and `/trades/<id>`.
- Produces: `liveMeta(meta: MarketMeta | null | undefined, rows: RowQuoteFields[]): MarketMeta | null`, exported from `stores/trades.store.ts`. It returns `null` when `meta` is absent. Otherwise it returns `meta` with `as_of` = the oldest non-null `price_as_of` among `rows` (falling back to `meta.as_of`) and `refreshing = meta.refreshing || rows.some((r) => r.price_refreshing === true)`. Other keys are unchanged: `missing_count` stays the server's, because it includes FX misses the rows cannot show.

**Behaviour fixed here:**
- **Rows patch in place.** `TradesStore.rows` becomes `live.patchRows(data()?.items ?? [], (r) => r.ticker)`. Every consumer (Trades list, the Dashboard's `sb-positions-table`, ticker detail) gets live prices with no other change. `TradeDetailStore`'s trade computed is `overlayQuote(trade, live.quote(trade.ticker)())`. `WatchlistStore`'s rows are `live.patchRows(rows, (r) => r.symbol)`.
- **Totals.** `TradesStore` gains `meta = computed(() => liveMeta(data()?.market_meta, rows()))`. `DashboardStore` gains `openMeta = computed(() => data()?.market_meta ?? null)`. Its `onInit` also refetches through the existing debounced `refresh` subject on `events.changes('market', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS })`, because the open-P&L KPIs are server totals that per-row patching cannot move. The first run of that effect is skipped, so the creation load stays the only one (V201-15's pin).
- **Cells.** Every displayed price and every P&L derived from one is projected into `sb-market-value [asOf]="row.price_as_of ?? null" [refreshing]="row.price_refreshing ?? false" [error]="row.price_error ?? null"`. That covers the Dashboard's two P&L cells (replacing both `sb-age-hint`s), the Trades `now` column (it gains a `nowCell` template, registered like `pnlCell`), the Watchlist `priceCell` (replacing its `sb-age-hint`; the bar-date `.as-of` span and the fallback badge stay), and the tape tiles (replacing its `sb-age-hint`; `asOf` from the row's `price_as_of`).
- **Stop/target proximity carries the price's age.** `OutcomeTile` drops `ageS` and gains `asOf: string | null`, `refreshing: boolean`, `error: string | null`. `openTiles` fills them on the `price` and `unrealised` tiles from the trade's row quote fields. `sb-outcome-strip` wraps both the tile value and its `sub` (the "to stop · to T1" line) in `sb-market-value`. It shows `STALE_FLAG` when `current_price_stale` is true (refresher off) or when the cell's tone is `stale` (`marketAgeLabel(...).tone === 'stale'`).
- **KPIs.** `trading-performance.ts` gains the input `openMeta: MarketMeta | null`. Under the "Open P&L" card it renders `<sb-market-value [asOf]="openMeta()?.as_of ?? null" [refreshing]="openMeta()?.refreshing ?? false" [error]="openMeta()?.error ?? null" />` and `<sb-incomplete-note [missing]="openMeta()?.missing_count ?? 0" />`. `dashboard.ts` binds `[openMeta]="store.openMeta()"`. Without a meta (old server) nothing renders.
- **Trades list header.** In `page-actions`: `<sb-market-value>` labelled `Prices` with `meta()?.as_of`, `<sb-incomplete-note [missing]="meta()?.missing_count ?? 0">`, and `<sb-market-refresh [symbols]="liveSymbols()">`, where `liveSymbols` holds the unique tickers of rows whose status is `PENDING`, `ACTIVE` or `PARTIAL`. The `prices_as_of` text, if the page shows one, is replaced by this label.
- **Refresh controls.** Dashboard: an `sb-market-refresh` in the open-positions panel's actions, with the open rows' tickers. Trade detail: one in `page-actions` with `[symbols]="[trade.ticker]"`, shown only while the trade is not terminal. Watchlist and the tape get no Refresh control (the spec names Dashboard, Trades and Trade detail; Risk gets one in v204).
- **Tape.** `TapeFeed`'s effect also reads `events.changes('market', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS })`, so landed values reach the strip within 30 s with one merged request.

- [ ] **Step 1: Write the failing specs**

`stores/trades.store.spec.ts`:

```ts
describe('liveMeta', () => {
  const meta = { as_of: '2026-10-29T14:00:00Z', refreshing: false, stale_count: 0, missing_count: 1,
    incomplete: true, computed_at: null, stale_inputs: false, source: 'request', error: null } as MarketMeta;
  it('is null without a server meta', () => expect(liveMeta(undefined, [])).toBeNull());
  it('takes the oldest row as-of', () =>
    expect(liveMeta(meta, [{ price_as_of: '2026-10-29T14:05:00Z' }, { price_as_of: '2026-10-29T14:02:00Z' }])?.as_of)
      .toBe('2026-10-29T14:02:00Z'));
  it('is refreshing when any row is', () =>
    expect(liveMeta(meta, [{ price_refreshing: true }])?.refreshing).toBe(true));
  it('keeps the server missing count (FX misses included)', () =>
    expect(liveMeta(meta, [{ price_as_of: '2026-10-29T14:05:00Z' }])?.missing_count).toBe(1));
});

it('rows take a newer live quote in place', () => {
  // fake LiveValuesStore whose quote('MSFT') signal returns {price: 412, as_of: later, refreshing: false, error: null}
  // TradesStore data with one MSFT row at 410 / earlier  ->  store.rows()[0].current_price === 412
});
```

Write the second case as real code with the fake `LiveValuesStore` (`patchRows` delegating to the real `overlayQuote`). Add the same "patched in place" case to `trade-detail.store.spec.ts` (`trade()` takes the live price) and to `watchlist.store.spec.ts` (keyed by `symbol`).

`stores/dashboard.store.spec.ts`: `refetches on a market event, throttled` (raise `market` after creation → `api.dashboard` called twice after the debounce; a second raise inside 30 s adds none) and `still loads once at creation` (no `market` raise → 1 call).

`stores/tape-feed.spec.ts`: `a market event refetches the union once`.

`workspaces/trades/outcome-tiles.spec.ts`: an open trade with `price_as_of: A, price_refreshing: true` gives a `price` tile with `asOf: A, refreshing: true, error: null`, and the `unrealised` tile carries the same three. Delete the `ageS` assertions.

Component specs (each mounts the component with a fake `LiveValuesStore` and asserts on DOM):
- `dashboard.spec.ts`: `the open P&L cell renders through sb-market-value with its age` (`sb-market-value` inside the P&L cell; no `sb-age-hint` left in `dashboard.ts`'s template). Also `the open-positions panel has a Refresh control for the open tickers`.
- `trading-performance.spec.ts`: `shows the open P&L as-of and an incomplete note` (`openMeta` with `missing_count: 2` → text `incomplete: 2 positions unpriced`) and `renders no label without a meta`.
- `trades.spec.ts`: `the Now column shows price and age` (one `sb-market-value` per row with a `current_price`), `the header shows prices as-of, the incomplete note and Refresh`, and `Refresh asks for the live tickers only` (rows `MSFT ACTIVE`, `AAPL CLOSED` → `requestRefresh(['MSFT'])`).
- `trade-detail.spec.ts`: `stop and target proximity carry the price age` (the `.tile-sub` of the price tile sits inside `sb-market-value`) and `no Refresh on a closed trade`.
- `watchlist.spec.ts`: `price cell renders through sb-market-value and keeps the bar date`.
- `shell/tape/tape.spec.ts`: `tiles carry the price age through sb-market-value`.

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false --include src/app/stores/trades.store.spec.ts --include src/app/stores/trade-detail.store.spec.ts --include src/app/stores/watchlist.store.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/stores/tape-feed.spec.ts --include src/app/workspaces/trades/outcome-tiles.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/shell/tape/tape.spec.ts`
Expected: FAIL (`liveMeta` not exported; no `sb-market-value` in the templates).

- [ ] **Step 3: Implement** as fixed above. Keep each changed template block's existing comments, and add one line where a cell changes ("v201: price, age and refresh spinner through sb-market-value"). Where a spec fixture builds full `TradeRow`/`Ticker` literals, the new fields are optional, so the fixtures need no change. `git -C <wt> grep -n "sb-age-hint" -- frontend/src/app/workspaces/dashboard frontend/src/app/workspaces/trades frontend/src/app/workspaces/watchlist frontend/src/app/shell` must print nothing afterwards (the gallery example stays).

- [ ] **Step 4: Run the specs again plus the stores' neighbours**

Run: the Step 2 command plus `--include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/watchlist/ticker-detail.spec.ts --include src/app/workspaces/trades/outcome-card.spec.ts`
Expected: PASS.

- [ ] **Step 5: Check three widths**

With `ng serve` and a local admin backed by the `swing-db` replica (`/replicate-prod-db` first; log in with `.env`'s admin credentials loaded inside the script, never printed), capture `/app/dashboard`, `/app/trades`, one open `/app/trades/<id>` and `/app/watchlist` at 390, 768 and 1440 px through `frontend/scripts/browse.mjs shots --base http://localhost:4200`. Confirm in each `.txt` that `page-scroll-x: 0`, and in the PNGs that the age label wraps under the value at 390 px and no table column widened.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add frontend/src/app/stores/trades.store.ts frontend/src/app/stores/trades.store.spec.ts frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.store.spec.ts frontend/src/app/stores/watchlist.store.ts frontend/src/app/stores/watchlist.store.spec.ts frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/stores/tape-feed.ts frontend/src/app/stores/tape-feed.spec.ts frontend/src/app/workspaces/dashboard frontend/src/app/workspaces/trades frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/watchlist/watchlist.spec.ts frontend/src/app/shell/tape/tape.ts frontend/src/app/shell/tape/tape.spec.ts
git -C <wt> commit -m "feat(v201): Dashboard, Trades, Trade detail, Watchlist and tape show price age, spinner and Refresh"
```

# Phase: verification (V201-19 … V201-20)

### Task V201-19: Full suite

**Model:** sonnet — a gate run: run, read, and fix only what it names in the owning task's files.

**Files:**
- No new files. A fix touches only the files of the task that owns the failing code, and it is committed as `fix(v201): <what> (V201-<n>)`.

**Interfaces:**
- Consumes: every task V201-1 … V201-11 and V201-15 … V201-17 committed on the worktree branch.
- Produces: the plan's one green full-suite run, whose numbers are recorded in the hand-back report and quoted at `/close-out`.

- [ ] **Step 1: Sync the database replica**

Run `/replicate-prod-db` into the shared `swing-db` container (never a per-task container). The full suite includes the `storage`, `refresher` and `admin` suites, which read it.

- [ ] **Step 2: Run the backend full suite through the `test-runner` subagent**

Dispatch `test-runner` with: `python <wt>/scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count alone is not a failure (`testing-cost.md`). Check that `tests/refresher/` and `tests/admin_market/` ran under `[suites.refresher]`: `python <wt>/scripts/dev/testrun.py suites` lists `refresher`, and `python <wt>/scripts/dev/testrun.py suite refresher` passes on its own.

- [ ] **Step 3: Run the complexity gate**

Run: `python <wt>/scripts/dev/complexity_gate.py`
Expected: clean. `list_trades` and `build_open_trade_views` are at or below their baseline scores (34, 17). Never run `--update` to pass; it only ever shrinks the baseline after a real reduction.

- [ ] **Step 4: Run the whole SPA suite and the production build**

Run: `npm --prefix <wt>/frontend exec -- ng test --watch=false`
Expected: every spec passes; no `.only`/`.skip` added by this plan (`git -C <wt> diff main --stat -- frontend/src | grep spec` lists the specs; `git -C <wt> grep -n "\.only(\|\.skip(" -- frontend/src` adds no hit compared with `main`).

Run: `npm --prefix <wt>/frontend exec -- ng build`
Expected: build succeeds with no new budget warning.

Run: `npm --prefix <wt>/frontend run lint`
Expected: no errors.

- [ ] **Step 5: Fix any failure narrowly**

For each failure: read the assertion, find the task that owns the file (the index's ledger), fix the code in that task's files, and re-run **only that test** (`python <wt>/scripts/dev/testrun.py file <test>` or `ng test --include <spec>`). Never re-run the whole suite for one fix. A failure in a test this plan did not touch, which also fails on `main` (`python <R>/scripts/dev/testrun.py file <test>` on the main tree), is reported to the controller, not fixed here.

- [ ] **Step 6: Confirm the kill switch path once more**

Run: `python <wt>/scripts/dev/testrun.py suite admin`
Expected: PASS with `tests/admin/conftest.py` pinning `ADMIN_REFRESHER="off"`. This is the spec's "`ADMIN_REFRESHER=off` restores the request-time fetch path", run as a whole suite.

- [ ] **Step 7: Commit fixes, if any; report**

```bash
git -C <wt> status --short          # only the fixed files
git -C <wt> add <each fixed path>
git -C <wt> commit -m "fix(v201): <what> (V201-<n>)"
```

Report: backend passed/failed/xfailed counts and wall time, SPA spec count, `ng build` result, gate result, and each fix with its owning task id. After this the controller merges the branch to `main` (no second full suite after the merge) and the partner deploys. V201-20 waits for that deploy.

### Task V201-20: Post-deploy production timing and label check

**Model:** sonnet — a bounded read-only browser probe and a results document, with every wait, pass rule and the credential handling fixed here.

> **Why Node.** Python Playwright is not installed on this machine, while Node Playwright is a `frontend` devDependency already used by `frontend/scripts/browse.mjs`. The probe is therefore `frontend/scripts/admin-page-timing.mjs` (the ledger names it). No other task consumes this file.

> **Scope (spec Goal 6 and Verification).** The probe times and label-checks Dashboard, Trades, Trade detail and Watchlist only, plus `/system/scan` ≤ 0.5 s throughout. Risk, Analytics and Calendar are verified by v204, which extends `PAGES`.

**Runs when:** after V201-19 is green, the branch is merged to `main`, and the partner has deployed it. It runs on `main` in the main tree `<R>` (`E:/Documents/Private/Projects/Discord-Bot`), not in the worktree. It touches production read-only, as the only task allowed to (index Global Constraints).

**Files:**
- Create: `frontend/scripts/admin-page-timing.mjs`, `frontend/scripts/admin-page-timing.test.mjs`
- Create: `docs/superpowers/results/2026-10-29-v201-page-timing.md`

**Interfaces:**
- Consumes: production endpoints `GET /api/v1/system/health` (`refresher.status`, V201-10), `GET /api/v1/market/updates` (V201-10), `GET /api/v1/system/scan` (`running`), `GET /api/v1/trades?status=open&per_page=1`, `POST /api/v1/session` (login, once). DOM contract from V201-16: `sb-market-value`, `.mv-age`, `.mv-err`, `.mv-value[hidden]`. Rail links `a.rail-link[aria-label="<Page>"]`; data shown = `main.workspace sb-async .content`.
- Produces: `results/page-timing.jsonl` (one line per page visit, appended as it goes) and the results document.

**Bounds (the previous unbounded run hung for 28 minutes).** `context.setDefaultTimeout(20_000)` (every action) and `setDefaultNavigationTimeout(30_000)`. Each page waits at most 30 s for data (`PAGE_WAIT_MS`), then 3 s to settle (`SETTLE_MS`; never `networkidle`, which an open SSE stream never reaches). The scan wait is at most `--scan-wait-min` (default 20) of 10 s polls. A global watchdog calls `process.exit(3)` after 30 min. Results already appended stay on disk. Each visit's line is appended before the next page starts.

**Safety.** Headless, with a fresh non-persistent context (a cold browser cache) per pass. Credentials come from `process.loadEnvFile(<R>/.env)` inside the script. They are never printed, logged, put in argv or written to the JSONL, and there is exactly one login attempt (the login limiter counts failures). `page.route('**/api/v1/**')` aborts every non-GET request except that one `POST /api/v1/session`, and counts the aborts. The probe cannot change production even if the SPA tries (a preference write, a Refresh click).

- [ ] **Step 1: Write the failing unit test** `frontend/scripts/admin-page-timing.test.mjs`

```js
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { labelOk, visitVerdict, renderTable } from './admin-page-timing.mjs';

test('a cell labelled with an age, last close or as-of passes', () => {
  for (const text of ['12 s ago', 'last close · Fri 16:00 ET', 'as of Wed 15:40 ET', '3 min ago']) {
    assert.equal(labelOk({ age: text, valueHidden: false }), true);
  }
});
test('a spinner-only cell (never priced) passes; an unlabelled value fails', () => {
  assert.equal(labelOk({ age: '', valueHidden: true }), true);
  assert.equal(labelOk({ age: '', valueHidden: false }), false);
});
test('a visit passes only within every limit', () => {
  const ok = { firstDataMs: 900, calls: [{ path: '/api/v1/trades', ms: 400, excluded: false }],
    scanMs: [80, 120], cells: 5, unlabelled: 0, timedOut: false };
  assert.equal(visitVerdict(ok).pass, true);
  assert.equal(visitVerdict({ ...ok, firstDataMs: 2100 }).pass, false);
  assert.equal(visitVerdict({ ...ok, calls: [{ path: '/api/v1/dashboard', ms: 2500, excluded: false }] }).pass, false);
  assert.equal(visitVerdict({ ...ok, calls: [{ path: '/api/v1/equity/candles', ms: 9000, excluded: true }] }).pass, true);
  assert.equal(visitVerdict({ ...ok, scanMs: [600] }).pass, false);
  assert.equal(visitVerdict({ ...ok, unlabelled: 1 }).pass, false);
  assert.equal(visitVerdict({ ...ok, timedOut: true }).pass, false);
});
test('the table has one row per visit with its verdict', () => {
  const md = renderTable([{ pass: 'cold', page: 'Trades', firstDataMs: 900, slowest: '/api/v1/trades 400 ms',
    scanMaxMs: 120, cells: 5, unlabelled: 0, verdict: 'PASS' }]);
  assert.match(md, /\| cold \| Trades \| 0\.9 s \| \/api\/v1\/trades 400 ms \| 120 ms \| 5 \/ 0 \| PASS \|/);
});
```

Run: `node --test <R>/frontend/scripts/admin-page-timing.test.mjs`
Expected: FAIL (`Cannot find module './admin-page-timing.mjs'`).

- [ ] **Step 2: Write the probe** `frontend/scripts/admin-page-timing.mjs`

Fixed values and the pure functions (as code; the test pins them):

```js
export const ACTION_TIMEOUT_MS = 20_000;
export const PAGE_WAIT_MS = 30_000;
export const SETTLE_MS = 3_000;
export const GLOBAL_DEADLINE_MS = 30 * 60_000;
export const LIMITS = { firstDataMs: 2_000, callMs: 2_000, scanMs: 500 };
/** Out of scope by the index's endpoint sweep: bar-backed charts load behind their own spinner. */
export const EXCLUDED = [/\/api\/v1\/equity\/candles/, /\/chart/, /\/events$/];
export const PAGES = [
  { name: 'Dashboard', rail: 'Dashboard' }, { name: 'Trades', rail: 'Trades' },
  { name: 'Trade detail', path: 'TRADE' }, { name: 'Watchlist', rail: 'Watchlist' },
];
const LABEL = /\bago\b|last close|\bas of\b/;

export const labelOk = ({ age, valueHidden }) => valueHidden || LABEL.test(age ?? '');

export function visitVerdict(v) {
  const reasons = [];
  if (v.timedOut || v.firstDataMs === null || v.firstDataMs > LIMITS.firstDataMs) reasons.push('first data');
  if (v.calls.some((c) => !c.excluded && (c.ms === null || c.ms > LIMITS.callMs))) reasons.push('call > 2 s');
  if (v.scanMs.some((ms) => ms === null || ms > LIMITS.scanMs)) reasons.push('/system/scan > 0.5 s');
  if (v.unlabelled > 0) reasons.push('unlabelled value');
  return { pass: reasons.length === 0, reasons };
}

export function renderTable(rows) {
  const head = '| Pass | Page | First data | Slowest page-load call | Max /system/scan | Cells / unlabelled | Verdict |\n|---|---|---|---|---|---|---|';
  const sec = (ms) => (ms === null ? 'timeout' : `${(ms / 1000).toFixed(1)} s`);
  return [head, ...rows.map((r) => `| ${r.pass} | ${r.page} | ${sec(r.firstDataMs)} | ${r.slowest} | ${r.scanMaxMs ?? '–'} ms | ${r.cells} / ${r.unlabelled} | ${r.verdict} |`)].join('\n');
}
```

`main()` runs only when executed directly (`import.meta.url === pathToFileURL(process.argv[1]).href`). Flags: `--base` (default `https://bomeo-capital.com`), `--out <dir>` (required; the session scratchpad), `--scan-wait-min` (default 20), `--passes cold,warm,scan` (default all three). Its steps, each a helper under 40 lines:
1. `setTimeout(() => { console.error('global deadline hit'); process.exit(3); }, GLOBAL_DEADLINE_MS).unref()`.
2. `preflight(page)`: `GET /api/v1/system/health` must report `refresher.status === 'ok'`, and `GET /api/v1/market/updates` must answer 200. Otherwise print `v201 not deployed or refresher not ok: <status>` and exit 2. This is the check that the partner's deploy is the v201 build.
3. `login(page)`: one `POST /api/v1/session` through `page.evaluate(fetch)` with the `.env` credentials (the `envCredentials` pattern from `browse.mjs`). On a refusal, print `login refused` (no values) and exit 2.
4. `visit(page, spec, passName)`: record `t0`, click `a.rail-link[aria-label="<rail>"]`, or `page.goto(base + '/trades/' + tradeId)` for Trade detail. The `tradeId` is read once with `GET /api/v1/trades?status=open&per_page=1`; with none, that row is `skipped: no open trade`. Then `locator('main.workspace sb-async .content').first().waitFor({state: 'visible', timeout: PAGE_WAIT_MS})`; a timeout sets `timedOut`. After `waitForTimeout(SETTLE_MS)` it collects the API calls started after `t0` (from `requestfinished`/`requestfailed` listeners: `ms = request.timing().responseEnd`, `null` when failed or still pending; `excluded` per `EXCLUDED`), the `/api/v1/system/scan` timings in the window, and the label scan below. It takes a full-page screenshot `<out>/<pass>-<slug>.png`, and appends one JSON line (no credentials, no cookies) to `<out>/page-timing.jsonl` before it returns.
5. Label scan (`page.evaluate`): for every `main.workspace sb-market-value`, `{age: .mv-age text, valueHidden: .mv-value has hidden, error: !!.mv-err}`, so `cells` and `unlabelled = !labelOk`.
6. Passes. `cold`: a fresh context, login, the four pages in order. `warm`: the same context, the four pages again. `scan`: poll `GET /api/v1/system/scan` every 10 s for at most `--scan-wait-min` minutes, then run the four pages once `running` is true. If no scan starts, write one line `{pass: 'scan', skipped: 'no scan observed in N min'}` and finish.
7. At the end, print `renderTable(...)` of every visit to stdout. stdout carries only timings, paths and verdicts.

- [ ] **Step 3: Run the unit test**

Run: `node --test <R>/frontend/scripts/admin-page-timing.test.mjs`
Expected: PASS (4 tests).

- [ ] **Step 4: Check the deploy, then run the probe in US regular hours**

Run during a weekday 15:30–22:00 Berlin, when auto-scans run (compute Berlin time from `date -u`; Git Bash has no zone data), with a Bash `timeout` of 2 400 000 ms:
`node <R>/frontend/scripts/admin-page-timing.mjs --out <scratchpad>/v201-timing`
Expected: exit 0. Preflight passes, `page-timing.jsonl` has 12 lines (4 pages × 3 passes), or 8 lines plus a `scan skipped` line. If the scan pass was skipped, re-run with `--passes scan` later in the session; the plan is not done without a during-scan row. Exit 2 or 3 is reported to the controller as is (never retried in a loop: the login limiter).

- [ ] **Step 5: Review the screenshots for the label check**

Open each `<pass>-<slug>.png` from the cold pass. Every displayed price, total and P&L must carry an age, `last close` or `as of` label. Note any figure the automatic scan cannot see (a number drawn outside `sb-market-value`) as a finding, naming page and figure.

- [ ] **Step 6: Write the results document** `docs/superpowers/results/2026-10-29-v201-page-timing.md`

Sections: **Before** (the spec's "Measured on production, 2026-10-29" table, copied verbatim; its Risk, Analytics and Calendar rows stay as the baseline v204 compares against); **After** (date, deployed versions from `/api/v1/health`, and the `renderTable` output for all three passes); **`/system/scan`** (the largest value seen in any pass); **Label check** (per page: cells and unlabelled, plus the screenshot review's findings); **Excluded calls** (the out-of-scope chart calls with their times, for the record); **Verdict**. Pass requires every visit `PASS`: first data ≤ 2 s, every in-scope page-load call ≤ 2 s and `/system/scan` ≤ 0.5 s in cold, warm and during-scan, plus zero unlabelled figures. Any `FAIL` row is listed with its reasons, and the plan reports it to the controller rather than claiming success. No credential, cookie or `.env` value appears in the document.

- [ ] **Step 7: Commit on `main`**

```bash
git -C <R> add frontend/scripts/admin-page-timing.mjs frontend/scripts/admin-page-timing.test.mjs docs/superpowers/results/2026-10-29-v201-page-timing.md
git -C <R> commit -m "docs(v201): post-deploy page timing and label check on production"
```

