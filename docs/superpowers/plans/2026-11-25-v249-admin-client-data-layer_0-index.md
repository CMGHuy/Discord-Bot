# v249 — Admin client data layer: keep page data 60 s, stop repeat fetches (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V249-7" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-25-v249-admin-client-data-layer-design.md](../specs/2026-11-25-v249-admin-client-data-layer-design.md)
**Brief:** `.superpowers/briefs/2026-11-25-v249-admin-client-data-layer.md` — its §3 excerpts and §6 traps override the spec's line cites wherever they disagree. The spec's `**Version:**` line (ui 1.49.0 · bot 2.19.10) is stale; VERSION.json reads ui 1.51.0 / bot 2.20.2 at HEAD 02441aa9, and `/close-out` resolves the levels.

## Goal

bomeo-capital.com throws away every page's data the moment the partner
leaves it. Every workspace store is route-scoped and every resolver re-runs,
so Dashboard → Trades → Dashboard costs a second `/dashboard`, and an
Analytics tab switch refetches `/analytics/performance` (median 20.8 s of
server time on production) for the fourth time. Risk reads the whole
`/dashboard` body just to take one balance, Attribution fires four
breakdown requests where one would do, and when the event stream breaks the
client polls *every* event every 5 s, so the page on screen reloads in full
twelve times a minute for as long as the outage lasts. None of this changes a
figure; all of it burns seconds of the single admin worker's time and makes
the phone feel slow.

Once shipped, a page revisited within 60 s of its last successful load
appears at once with an "as of HH:MM · updating" mark and refreshes in the
background; older than that, or invalidated by an event while the partner
was elsewhere, it loads fresh exactly as today. Analytics reads performance
once per scope across its tabs and Attribution makes one
`/analytics/by-dimension?dims=…` request; Risk takes its balance from the
`/risk` body it already fetches; the Dashboard's `mode=today` client
fallback disappears; a degraded stream polls only what the current page
listens to, every 15 s for two minutes and then every 60 s, and the
connection indicator says live updates are paused.

The idea is one small root cache of **API bodies**, never store state. A
page's load runs inside a synchronous "scope": the first time, an HTTP
interceptor records every GET body the load issues under the page's URL;
on a revisit inside 60 s the same load runs twice back to back — once in a
replay scope where the interceptor answers those GETs from memory
synchronously, then once for real in a recording scope. Because replay goes
through the same stores and `next` handlers, the live-values overlay patches
a remembered page exactly like a fresh one and no patched price is ever
stored. Events mark matching entries stale through each entry's own
predicate, every write, logout, 401, stream reconnect or degradation empties
the cache under a generation counter, and late responses from an older
generation are dropped.

What it leaves alone: no server cache, ETag or snapshot change (v250 owns
those and ships first), no layout or content change beyond the mark's one
reserved line, no change to what any figure means, nothing persisted across
a browser reload. Success is measured, not asserted: V249-1's Playwright
script re-baselines production after v250 deploys, and the same script's
after-numbers (request count, API bytes, time to content, 60 s idle) go into
the spec at close-out — the target is the Analytics return turning from a
17–20 s wait into an instant render, and the 60 s Dashboard idle dropping
from 14–19 requests.

## Architecture

```
Router ── startRoute(load) ──► PageLoader.open({key: state.url, staleOn}, load, {background})
                                   │  hit (fresh, not stale, memory enabled, not a background refresh)
                                   │     ├─ memory.within({kind:'replay', entry}, load())   → interceptor answers from entry.bodies (clone)
                                   │     └─ memory.within({kind:'record', recording}, load())→ interceptor fetches + records; settle → mark cleared / "refresh failed"
                                   │  miss
                                   │     └─ memory.within({kind:'record', recording}, load())
DashboardStore first load ─────────┘ (key '/dashboard', DASHBOARD_STALE_ON; the route keeps onEvents())

pageMemoryInterceptor (LAST in app.config's chain)
   GET in replay scope + body known + not fresh-marked → HttpResponse(clone) synchronously
   GET to a SHARED_READS path inside any page scope + fresh shared entry → HttpResponse(clone)
   GET in record scope → track / record body / untrack(ok)
   GET to a SHARED_READS path (any context) 2xx → recordShared
   any 401 → memory.clear()

EventStream.raised ─► RouteRefreshService: memory.markStale(event) FIRST (before the scan throttle,
                      the 300 ms debounce and the loading.pending() early return), then today's refresh
writes (routeRefreshInterceptor, every successful non-GET), requestMutationRefresh, SessionStore.logout/expire,
EventStream.reconnects (every `resync` frame), state 'degraded' (setEnabled(false)) ─► memory.clear()

Degraded poller: EventStream.pollInterest(accepts) registry (RouteRefreshService: current route's
refreshOn; DashboardStore: DASHBOARD_STALE_ON); 15 s for 120 s from degradation, then 60 s.

Server: /analytics/by-dimension?dims=a,b → {"blocks": {a: <single body>, b: {"error": {...}}}},
trades loaded and scoped once; the single dim= form unchanged.
```

Files created: `frontend/src/app/routing/page-memory.service.ts`,
`frontend/src/app/routing/page-memory.interceptor.ts`,
`frontend/src/app/routing/page-loader.service.ts`,
`frontend/src/app/ui/as-of-mark.ts`, `frontend/src/app/stores/analytics-breakdowns.ts`,
`frontend/src/app/testing/page-memory-golden.ts`, the per-workspace
`*.memory.spec.ts` / `*.swap.spec.ts` files, `scripts/dev/admin_data_layer_timing.py`,
`frontend/scripts/v249-as-of-mark-check*.mjs`. Everything else is a modification.

## Global Constraints

- **Start gate.** V249-1 (the measurement script) may be implemented and
  merged ahead of everything else — v250's own after-measurement uses it.
  V249-2 onwards starts only after v250 is deployed and V249-1's re-baseline
  is recorded in the spec (spec § 7, Ops and ownership). V249-2 and V249-3
  are written against HEAD 02441aa9: if v250 wrapped
  `analytics_by_dimension` or `/dashboard` (`@read_scope`,
  `default_view_body`, `conditional.py`), keep the wrapper on the single
  form and route each `dims=` block through the same per-dimension path;
  the "dims equals four single calls block for block" test is the arbiter.
- **Bodies only.** The cache holds API response bodies, cloned with
  `structuredClone` on write and on every read; never store state, never
  `localStorage` / `sessionStorage` / IndexedDB.
- **Numbers.** `PAGE_MEMORY_TTL_MS = 60_000` (an entry aged `>= 60_000` ms
  is a miss and is dropped on read); `PAGE_MEMORY_CAP = 12` entries, least
  recently used out. Page key = `RouterStateSnapshot.url` (path + query
  string); the Dashboard's key is `DASHBOARD_PAGE_KEY = '/dashboard'`; a
  shared read's key is the request's `urlWithParams`.
- **Never served from memory:** a non-GET; a GET carrying `X-Swingbot-Fresh`
  (`FRESH_HEADER`: boot phase, Refresh click, Retry); a navigation carrying
  `BACKGROUND_REFRESH_INFO`; anything while the stream is degraded.
- **Clears** (each bumps the generation, empties page and shared entries,
  sets `served` to null): every successful non-GET response (including
  `SKIP_ROUTE_REFRESH` requests and `/market/refresh`),
  `requestMutationRefresh()`, `SessionStore.logout()` and `expire()`, any 401
  response, every `resync` frame (`EventStream.reconnects`), entering
  `degraded`.
- **Stale-marking** runs for every raised event before the scan throttle,
  the 300 ms debounce and the `loading.pending()` early return, and bumps
  the matched key's sequence so an in-flight recording of that key can no
  longer write.
- **Degraded polling:** `POLL_FAST_MS = 15_000` while
  `now - degradedAt < POLL_FAST_WINDOW_MS (120_000)`, then
  `POLL_SLOW_MS = 60_000`; `degradedAt` is set on the first degrade of an
  outage, cleared by `markLive`, untouched by route changes; only events some
  registered `pollInterest` accepts are bumped; hidden tabs skip; the 30 s
  recovery attempt is unchanged. `POLL_INTERVAL_MS` is removed.
- **Copy, exact:** mark `as of HH:MM · updating` / `as of HH:MM · refresh
  failed` + a `Retry` button (44 px target); `HH:MM` from
  `timeInZone(iso, Intl.DateTimeFormat().resolvedOptions().timeZone)`
  (`ui/format.ts`, the viewer's zone like every other admin time); degraded
  indicator word `Live updates paused (polling)` (replaces
  `Polling (stream down)`).
- **Mark contract:** `aria-live="polite"`; the failed state carries a text
  glyph icon and words, never colour alone; its line height is reserved in
  the `sb-page` heading so nothing reflows when it appears or clears; on
  phone it wraps under the title and never truncates it.
- **Server envelope (V249-2):** `GET /api/v1/analytics/by-dimension?dims=a,b,…&<scope>`
  → 200 `{"blocks": {"a": <body identical to ?dim=a>, "b": {"error": {"code":
  "dimension_failed", "message": "<ExcType>: <msg>"}}}}`, keys in request
  order, duplicates collapsed; all blocks failing → `ApiError("dimension_failed",
  …, 500)`; an unknown name, an empty list, or `dim` and `dims` together →
  `ApiError("invalid", …, 400)`. Closed trades are loaded and scoped once per
  request. The `?dim=` form's body is byte-identical to today's.
- **Server `today` block:** no server code change; V249-3 only extends the
  existing pin. `tests/admin_perf/golden/dashboard.json` and
  `dashboard_today.json` stay byte-identical.
- **Complexity < 15** for every new or changed function
  (`scripts/dev/complexity_gate.py`); `analytics_by_dimension` (cc 33,
  baseline) only shrinks — run `python scripts/dev/complexity_gate.py --update`
  to lock in the drop. Never run radon over `frontend/` (it times out); new
  frontend logic goes in new files, not inside `analytics.store.ts`'s
  `withMethods` closure.
- **Verification is narrow.** Python: `python scripts/dev/testrun.py file <test>`.
  Frontend: `node frontend/scripts/ng-test.mjs frontend --include <spec path
  relative to frontend/>`, lint `npm --prefix frontend run lint`. Node script
  libs: `node --test frontend/scripts/<lib>.test.mjs`. No task runs the full
  suite; CI does. Never `cd` in Bash.
- **Database.** `tests/admin/` reaches Postgres: run `/replicate-prod-db`
  once per session before its first run, in the shared `swing-db` container
  (port 56789), never a per-task database.
- **Suites.** Python tests go into existing files (`tests/admin/test_api_v1_*.py`
  → suite `admin`; `tests/dev/` → suite `dev-setup`); no `tests/suites.toml`
  edit. Frontend specs are Vitest files beside their source (CI runs the
  frontend job), not suites.toml members.
- **UI.** Designed and checked at 390, 768 and 1440 widths
  (`docs/claude/ui-design.md`); tokens only; no layout change beyond the
  mark's reserved line. Browser checks use Playwright only and log in with
  `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD`, loaded in-process and never
  printed.
- **Production measurement** (V249-1): read-only (abort every non-GET to
  `/api/v1/`), off-hours — between 23:15 and 07:00 UTC on a weekday, never
  around the 22:40 UTC jobs — each finished run persisted to disk at once and
  skipped on restart, percent progress printed.
- **Commits.** Scoped, one or two per task, single-line subjects. No task
  bumps `VERSION.json`; `/close-out` does (ui minor, bot patch) and records
  the after-numbers.

## Review Focus

1. **A remembered page that should have been invalidated** (Goal 2): an
   event raised while on another page, a throttled `scan`, an event during a
   pending navigation, a write, a reconnect — each must make the next visit a
   miss (V249-5, V249-8, V249-14).
2. **Late responses**: a background response after a clear, or an older
   refresh landing after a newer one, must never write the cache (generation
   and per-key sequence, V249-5/V249-6).
3. **The mark never lies**: it shows only on a page served from memory,
   clears when the background load settles cleanly, turns to "refresh
   failed" on any failed GET of that load, and never sticks at "updating"
   when the background pass needed no network (V249-7, V249-10).
4. **Overlay integrity**: a remembered body is never a patched one; a page
   from memory gets the overlay pass (V249-5 clone rule, V249-15 overlay
   golden).
5. **Error blocks are measured answers**: a `dims=` error block shows that
   bar list's own error state, never an empty list (V249-11,
   `known-traps.md`).

## Parallelisation

Default: run the tasks in id order, one at a time (the partner's standing
preference). Sequential edges and their reasons:

- V249-1 → V249-2 … V249-18: the start gate (baseline recorded after v250
  deploys).
- V249-5 → V249-6, V249-7, V249-8: they consume `PageMemoryService`,
  `PageRecording`, `MemoryScope`, `SHARED_READS`.
- V249-6 → V249-7: `PageLoader`'s tests drive replay through the
  registered interceptor.
- V249-7 → V249-9, V249-10, V249-12, V249-15, V249-17: they call
  `PageLoader.open` / `retry`.
- V249-3 → V249-9: same file (`dashboard.store.ts` and its spec); V249-9
  builds on the fallback-free `resolveScoped`.
- V249-8 → V249-14: same file (`route-refresh.service.ts`).
- V249-9 → V249-14: same file (`dashboard.store.ts`); V249-14 registers
  `DASHBOARD_STALE_ON` as a poll interest.
- V249-5 → V249-14: same file (`page-memory.service.ts`) gains the stream
  wiring.
- V249-13 → V249-14: V249-14 consumes `pollInterest` and `reconnects`.
- V249-11 → V249-12: V249-12's four-tab test flushes Attribution's single
  `dims=` request.
- V249-2 → V249-11 (contract only): the client models the envelope fixed in
  Global Constraints; the frontend tests use `HttpTestingController`, so
  V249-11 does not need the server code to run.
- V249-10 → V249-15, V249-18: the golden harness strips `sb-as-of-mark`;
  the UI check measures it.
- V249-15 → V249-16, V249-17: they use `renderFreshThenFromMemory`.
- V249-14 → V249-18: the check also captures the degraded indicator.

Safe in parallel if the controller wants to (disjoint files, no contract
between them): **V249-2 ∥ V249-3 ∥ V249-4 ∥ V249-5 ∥ V249-11 ∥ V249-13**
(server analytics; dashboard fallback; risk store; new cache file;
analytics client; event stream). **V249-6 ∥ V249-8** (new interceptor +
`app.config.ts` vs `route-refresh.service.ts`, `interceptors.ts`,
`session.store.ts`). **V249-16 ∥ V249-17** (distinct new spec files). At
most two writers at once.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V249-1 | Playwright measurement script (read-only, checkpointed) + pure-helper tests + production re-baseline after v250 | 1 | sonnet | C `scripts/dev/admin_data_layer_timing.py`, C `tests/dev/test_admin_data_layer_timing.py`, M `docs/superpowers/specs/2026-11-25-v249-admin-client-data-layer-design.md` (baseline section) | CLI `python scripts/dev/admin_data_layer_timing.py --base-url URL --out DIR [--runs 3] [--widths phone,desktop] [--steps …]`; JSONL rows `{step, width, run, ttc_ms, idle_ms, requests, api_bytes}` in `DIR/runs.jsonl`; `summarise(rows) -> list[dict]` (median per step × width); `STEPS` tuple of step names; `is_api_request(url: str) -> bool` |
| V249-2 | `/analytics/by-dimension?dims=` multi-dimension form: trades scoped once, per-block error, split the cc 33 handler | 1 | opus | M `swingbot/admin/api_v1/analytics.py`, M `tests/admin/test_api_v1_analytics.py`, M `scripts/dev/complexity_baseline.json` | Response envelope as in Global Constraints; helpers `_dimension_body(scoped: list[dict], scope, dim: str) -> dict`, `_dims_param() -> list[str] \| None`, `_multi_dimension_body(scoped, scope, dims: list[str]) -> dict` |
| V249-3 | Delete the Dashboard `mode=today` client fallback (`loadToday`, `TodayFallback`) + extend the server `today` pin | 1 | sonnet | M `frontend/src/app/stores/dashboard.store.ts`, M `frontend/src/app/stores/dashboard.store.spec.ts`, M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, M `tests/admin/test_api_v1_dashboard.py` | `resolveScoped()` takes no argument; `resolve()` / `load()` signatures unchanged |
| V249-4 | Risk balance from the `/risk` body: delete `readBalance`, the `balance` slice and the `/dashboard` call | 1 | sonnet | M `frontend/src/app/stores/risk.store.ts`, M `frontend/src/app/stores/risk.store.spec.ts`, M `frontend/src/app/workspaces/risk/risk.spec.ts` | `RiskStore.accountBalance: Signal<number \| null>` = `finiteOrNull(data()?.account?.balance)` (no fallback) |
| V249-5 | `PageMemoryService`: entries, 60 s rule, LRU cap, stale marking, generation + per-key sequence, shared reads, scopes, served mark state | 2 | sonnet | C `frontend/src/app/routing/page-memory.service.ts`, C `frontend/src/app/routing/page-memory.service.spec.ts` | `PAGE_MEMORY_TTL_MS = 60_000`; `PAGE_MEMORY_CAP = 12`; `type StalePredicate = (event: EventName) => boolean`; `interface SharedRead { readonly path: string; readonly staleOn: StalePredicate }`; `SHARED_READS: readonly SharedRead[]` = `[{ path: '/api/v1/analytics/performance', staleOn: (e) => e === 'analytics' }]`; `interface PageEntry { readonly key; readonly staleOn; readonly fetchedAt: number; readonly bodies: Map<string, unknown>; stale: boolean }`; `class PageRecording { readonly key: string; readonly staleOn; readonly generation: number; readonly seq: number; readonly settled: Observable<boolean>; track(): void; untrack(ok: boolean): void; seal(): void }` (settled emits once, when sealed and nothing in flight; `false` if any untrack(false)); `type MemoryScope = { readonly kind: 'record'; readonly recording: PageRecording } \| { readonly kind: 'replay'; readonly entry: PageEntry }`; `type ServedStatus = 'updating' \| 'failed'`; `interface ServedMark { readonly key: string; readonly fetchedAt: number; readonly status: ServedStatus }`; `PageMemoryService` (root): `served: Signal<ServedMark \| null>`, `enabled: Signal<boolean>`, `generation(): number`, `currentScope(): MemoryScope \| null`, `within<T>(scope: MemoryScope, source: Observable<T>): Observable<T>`, `hit(key: string, now?: number): PageEntry \| null`, `entryBody(entry: PageEntry, url: string): unknown \| undefined` (clone), `beginRecording(key: string, staleOn: StalePredicate): PageRecording`, `recordBody(recording: PageRecording, url: string, body: unknown, now?: number): void`, `sharedReadFor(url: string): SharedRead \| null`, `sharedTicket(url: string): number`, `sharedHit(url: string, now?: number): unknown \| undefined` (clone), `recordShared(url: string, body: unknown, ticket: number, now?: number): void`, `markStale(event: EventName): void`, `clear(): void`, `setEnabled(on: boolean): void` (off clears), `showServed(key: string, fetchedAt: number): void`, `settleServed(key: string, ok: boolean): void`, `markServedUpdating(key: string): void`, `clearServed(): void` (also on NavigationStart to a URL other than `served().key`) |
| V249-6 | `pageMemoryInterceptor`: replay, record, shared reads, fresh bypass, 401 clear; registered last | 2 | sonnet | C `frontend/src/app/routing/page-memory.interceptor.ts`, C `frontend/src/app/routing/page-memory.interceptor.spec.ts`, M `frontend/src/app/app.config.ts` | `export const pageMemoryInterceptor: HttpInterceptorFn`; chain becomes `[loadingInterceptor, forbiddenInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor, freshInterceptor, pageMemoryInterceptor]` |
| V249-7 | `PageLoader.open` / `retry` and `startRoute` through it (hit → replay + background, miss → record, background refresh bypass) | 2 | sonnet | C `frontend/src/app/routing/page-loader.service.ts`, C `frontend/src/app/routing/page-loader.service.spec.ts`, M `frontend/src/app/routing/route-resolver.ts`, M `frontend/src/app/routing/route-resolver.spec.ts`, M `frontend/src/app/routing/route-loading.service.ts` | `interface PageOpen { readonly key: string; readonly staleOn: StalePredicate }`; `interface PageOpenOptions { readonly background?: boolean }`; `export function staleOnRoute(route: ActivatedRouteSnapshot): StalePredicate`; `PageLoader` (root): `open(page: PageOpen, load: () => Observable<void>, options?: PageOpenOptions): Observable<void>` (hit: `merge(replay, background)`), `retry(): void` (re-runs the served page's last load in a record scope inside `FreshRequestService.markFresh`, mark → `updating`); `export const isBackgroundRefresh: (info: unknown) => boolean` (now exported from `route-loading.service.ts`) |
| V249-8 | Stale-mark every raised event before throttle/debounce/pending; clear on every write, mutation refresh, logout, expire | 2 | sonnet | M `frontend/src/app/routing/route-refresh.service.ts`, M `frontend/src/app/routing/route-refresh.service.spec.ts`, M `frontend/src/app/api/interceptors.ts`, M `frontend/src/app/api/interceptors.spec.ts`, M `frontend/src/app/stores/session.store.ts`, M `frontend/src/app/stores/session.store.spec.ts` | none new (`requestMutationRefresh()` now also clears) |
| V249-9 | Dashboard joins page memory: first load through `PageLoader.open('/dashboard', DASHBOARD_STALE_ON)` | 2 | sonnet | M `frontend/src/app/stores/dashboard.store.ts`, M `frontend/src/app/stores/dashboard.store.spec.ts` | `export const DASHBOARD_PAGE_KEY = '/dashboard'`; `export const DASHBOARD_STALE_ON: StalePredicate` (`account`, `trades`, `market`) |
| V249-10 | `sb-as-of-mark` (updating / refresh failed + Retry, aria-live, reserved line) placed in `sb-page`'s heading | 3 | sonnet | C `frontend/src/app/ui/as-of-mark.ts`, C `frontend/src/app/ui/as-of-mark.spec.ts`, M `frontend/src/app/ui/page.ts`, M `frontend/src/app/ui/page.spec.ts` | `AsOfMark` (`sb-as-of-mark`, no inputs, reads `PageMemoryService.served`, Retry calls `PageLoader.retry()`); `export function asOfText(mark: ServedMark, timeZone?: string): string`; root element class `as-of`, failed state class `as-of--failed` |
| V249-11 | Attribution: one `dims=` breakdown request (api client, models, `analytics-breakdowns.ts`, store) | 3 | sonnet | C `frontend/src/app/stores/analytics-breakdowns.ts`, C `frontend/src/app/stores/analytics-breakdowns.spec.ts`, M `frontend/src/app/api/api-client.ts`, M `frontend/src/app/api/api-client.spec.ts`, M `frontend/src/app/api/models.ts`, M `frontend/src/app/stores/analytics.store.ts`, M `frontend/src/app/stores/analytics.store.spec.ts` | `ApiClient.analyticsByDimensions(dims: readonly string[], scope?: Partial<BookScope> \| null): Observable<AnalyticsByDimensions>`; models `interface AnalyticsDimensionError { error: { code: string; message: string } }`, `interface AnalyticsByDimensions { blocks: Record<string, AnalyticsByDimension \| AnalyticsDimensionError> }`, `isDimensionError(block): block is AnalyticsDimensionError`; `ATTRIBUTION_FIXED_DIMS = ['horizon', 'direction', 'dow'] as const`; `attributionDims(breakdown: string): string[]`; `breakdownPatch(body: AnalyticsByDimensions, breakdown: string): BreakdownPatch`; `breakdownFailure(error: ApiError): BreakdownPatch` |
| V249-12 | Analytics: one performance request across Overview/Attribution/Execution/Edge inside 60 s; per-panel skeletons on every tab while loading | 3 | sonnet | C `frontend/src/app/stores/analytics.page-memory.spec.ts`, C `frontend/src/app/workspaces/analytics/analytics.loading.spec.ts`, M `frontend/src/app/workspaces/analytics/tabs/*.ts` only where a tab renders no skeleton | none |
| V249-13 | Degraded poller: `pollInterest` registry, 15 s → 60 s back-off with outage clock, `reconnects` stream | 3 | sonnet | M `frontend/src/app/api/event-stream.ts`, M `frontend/src/app/api/event-stream.spec.ts` | `POLL_FAST_MS = 15_000`, `POLL_SLOW_MS = 60_000`, `POLL_FAST_WINDOW_MS = 120_000` (exported; `POLL_INTERVAL_MS` removed); `EventStream.pollInterest(accepts: (event: EventName) => boolean): () => void`; `EventStream.reconnects: Observable<void>` (one emission per `resync` frame) |
| V249-14 | Degraded wiring: route and Dashboard poll interests, memory clear on reconnect and off while degraded, "Live updates paused" indicator | 4 | sonnet | M `frontend/src/app/routing/route-refresh.service.ts`, M `frontend/src/app/routing/route-refresh.service.spec.ts`, M `frontend/src/app/stores/dashboard.store.ts`, M `frontend/src/app/stores/dashboard.store.spec.ts`, M `frontend/src/app/routing/page-memory.service.ts`, M `frontend/src/app/routing/page-memory.service.spec.ts`, M `frontend/src/app/shell/live/live-bot-section.ts`, M `frontend/src/app/shell/live/live-bot-section.spec.ts` | `STREAM_WORDS.degraded = 'Live updates paused (polling)'` |
| V249-15 | Golden harness + "from memory renders identically" for Dashboard, Trades, Risk (with live overlay) and Analytics | 4 | sonnet | C `frontend/src/app/testing/page-memory-golden.ts`, C `frontend/src/app/workspaces/dashboard/dashboard.memory.spec.ts`, C `frontend/src/app/workspaces/trades/trades.memory.spec.ts`, C `frontend/src/app/workspaces/risk/risk.memory.spec.ts`, C `frontend/src/app/workspaces/analytics/analytics.memory.spec.ts` | `interface PageGoldenCase { key: string; staleOn?: StalePredicate; providers: Provider[]; component: Type<unknown>; load: (injector: Injector) => Observable<void>; respond: (backend: HttpTestingController) => void; afterRender?: (fixture: ComponentFixture<unknown>) => void }`; `interface PageGoldenResult { fresh: string; memory: string; replayedRequests: number }`; `renderFreshThenFromMemory(c: PageGoldenCase): Promise<PageGoldenResult>`; `stripAsOfMark(html: string): string` |
| V249-16 | Goldens for the remaining resolver workspaces (calendar, guide, plan detail, reports, research, system, trade detail, versions, ticker detail, watchlist) | 4 | sonnet | C `frontend/src/app/workspaces/calendar/calendar.memory.spec.ts`, C `frontend/src/app/workspaces/guide/guide.memory.spec.ts`, C `frontend/src/app/workspaces/plans/plan-detail.memory.spec.ts`, C `frontend/src/app/workspaces/reports/reports.memory.spec.ts`, C `frontend/src/app/workspaces/research/research.memory.spec.ts`, C `frontend/src/app/workspaces/system/system.memory.spec.ts`, C `frontend/src/app/workspaces/trades/trade-detail.memory.spec.ts`, C `frontend/src/app/workspaces/versions/versions.memory.spec.ts`, C `frontend/src/app/workspaces/watchlist/ticker-detail.memory.spec.ts`, C `frontend/src/app/workspaces/watchlist/watchlist.memory.spec.ts` | none |
| V249-17 | Background swap preserves pager page, filters, expanded rows and scroll (Trades, Dashboard positions, Analytics Tuning) | 4 | sonnet | C `frontend/src/app/workspaces/trades/trades.swap.spec.ts`, C `frontend/src/app/workspaces/dashboard/dashboard.swap.spec.ts`, C `frontend/src/app/workspaces/analytics/analytics.swap.spec.ts`; M the matching store or page file only if a swap resets state | none |
| V249-18 | UI check: the mark at 390/768/1440 with the longest workspace title, the degraded indicator, `layout-audit.mjs` | 4 | sonnet | C `frontend/scripts/v249-as-of-mark-check.mjs`, C `frontend/scripts/v249-as-of-mark-check-lib.mjs`, C `frontend/scripts/v249-as-of-mark-check-lib.test.mjs`; M `frontend/src/app/ui/as-of-mark.ts` / `frontend/src/app/ui/page.ts` only for layout fixes found | none |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-25-v249-admin-client-data-layer_1-baseline-and-server.md` | V249-1..V249-4 | Measurement script and re-baseline, the `dims=` server form, the Dashboard fallback deletion, Risk balance from `/risk` |
| 2 | `2026-11-25-v249-admin-client-data-layer_2-page-memory-core.md` | V249-5..V249-9 | Cache service, interceptor, `PageLoader` + `startRoute`, stale-marking and clears, Dashboard participation |
| 3 | `2026-11-25-v249-admin-client-data-layer_3-mark-analytics-poller.md` | V249-10..V249-13 | The "as of" mark, Attribution's one breakdown request, shared performance + skeleton check, the degraded poller |
| 4 | `2026-11-25-v249-admin-client-data-layer_4-degraded-and-verification.md` | V249-14..V249-18 | Degraded wiring and indicator, goldens, swap preservation, the three-width UI check |

## Handoff

- Close-out (not a plan task): deploy, run V249-1's script off-hours
  against production, put the after-numbers into the spec's close-out commit
  (Goal 7), and check the removal condition (spec § 7: if return visits
  without the cache measure within 300 ms of a memory hit, the 60 s layer is
  removed in a follow-up).
- Accepted trade-offs to keep visible in review: `market` marks the
  Dashboard entry stale, so during market hours a Dashboard revisit is
  usually a miss (Goal 2 wins over hit rate); in a replay pass a GET with no
  remembered body goes to the network unrecorded and is fetched again by the
  background pass; while degraded, shell-level counters (connection, live
  values, shell risk) are no longer bumped by the poller — only the current
  page's interests are (spec § 5).
