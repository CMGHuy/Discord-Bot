# v249 — Admin client data layer: keep page data 60 s, stop repeat fetches

**Version:** ui 1.49.0 · bot 2.19.10
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer, senior-engineer

`Edge: none (integrity)`: no entry, exit, stop, sizing or alert rule changes.
The work makes bomeo-capital.com load less and show the same facts faster.
`Bump: ui minor`: a page revisited within 60 s appears at once with an
"as of" mark, which is a visible change in how the app behaves. `Bump: bot
patch`: `/analytics/by-dimension` gains a multi-dimension form; no
trader-facing behaviour.

Panel choice: the Admin UI default swaps `financial-advisor` for
`senior-engineer` because nothing here changes a figure or how it is framed;
the risk is in store and refresh code, which is that seat's lens. The
ux-designer seat covers the "as of" mark and loading states on all three
device classes.

## Why

Brainstorm with the partner, 2026-11-25. Three pains, in their words: the
same data sits on many pages, pages feel slow, and the phone is painful. On
the phone they check open trades, plans to act on, and "am I making money".

The brainstorm split the answer into three projects:

1. **This spec** — the client data layer: fetch less, reuse what was fetched.
2. Server cache — remembered bodies keyed on ledger changes, ETag/304 beyond
   `/trades`. Own spec, own brainstorm. **Built before this spec** (partner,
   2026-11-25, after the baseline below showed first loads are server-bound:
   only project 2 shortens them).
3. Dashboard/Trades content — Dashboard is "right now" (all five position
   tabs kept, recent slices, no filters), Trades is the filtered history.
   Own spec, own brainstorm.

The v240 restyle (spec committed, no plan) lands after all three; it owns the
look, the icon rail, the phone tab bar and drawers. This spec changes no
layout.

### What the survey found (read-only, 2026-11-25)

- Every workspace store is **route-scoped** and every resolver runs with
  `runGuardsAndResolvers: 'always'`, so leaving a page discards its data and
  returning refetches all of it. Only Research and Guide fetch once
  (`ensureLoaded`).
- `RouteRefreshService` (`frontend/src/app/routing/route-refresh.service.ts`)
  already refreshes only the routes whose `refreshOn` accepts the event, and
  does so by re-navigating to the same URL, which re-runs the whole resolver.
- **Analytics:** `/analytics/performance` is fetched by four tab resolvers
  (overview, attribution, execution, edge — `stores/analytics.store.ts`
  `resolveOverview`/`resolveAttribution`/`resolveExecution`/`resolveEdge`),
  again on each tab switch. Attribution fires **seven** requests: four
  `/analytics/by-dimension` calls (the chosen breakdown, `horizon`,
  `direction`, `dow`), heat-grid, strategies and performance.
- **Risk** reads the whole `/dashboard` body only to take `account_balance`
  (`stores/risk.store.ts` `readBalance`). `/dashboard` is the heaviest read:
  it loads every trade and recomputes all stats per call
  (`swingbot/admin/api_v1/dashboard.py`).
- **Dashboard** has a second `/dashboard?scope=today` call
  (`stores/dashboard.store.ts` `loadToday`) that fires when the wider
  answer carries no `today` block.
- **Degraded stream:** when SSE fails three times in a minute the client
  polls every 5 s and raises **every** event (`api/event-stream.ts`
  `startPolling` → `bumpAll`, `POLL_INTERVAL_MS = 5_000`), so the current
  page reloads in full every 5 s for as long as the stream is down.

### Baseline (production, before)

Playwright, 2026-11-25 18:12–18:42 UTC, fresh browser context per run,
median of 3 runs, phone / desktop. "Req" counts `/api/v1/` requests the step
started (SSE excluded); "Idle" is when the last of them finished.

| Step | Time to content ms | Idle ms | Req |
|---|---|---|---|
| Cold Dashboard | 3419 / 2399 | 7620 / 7476 | 21 / 21 |
| Dashboard → Trades | 923 / 1379 | 598 / 615 | 1 / 1 |
| Back to Dashboard | 868 / 781 | 2448 / 2539 | 3 / 3 |
| Risk | 2115 / 2423 | 2068 / 2386 | 2 / 2 (`/risk` + `/dashboard`) |
| Analytics Overview (return) | — | 19760 / 17071 | 3 |
| Analytics Attribution | — | 17406 / 6854 | 7 / 8 |
| Analytics Cancels | 17143 / 17331 | 24341 / 17273 | 5 |

- `/analytics/performance` is fetched 5–6 times per pass over the nine tabs;
  clicking the already-active Overview tab refetches its three reads.
- 60 s idle on Dashboard: 19 / 14 requests, mostly `/dashboard` (5–6 a
  minute) and `/live`; the same refreshes fire on Risk and Analytics.
- Server time dominates; bodies are 1–32 KB. Median total per request:
  `/analytics/performance` 20.8 s, `variance-band` 17.2 s,
  `cancel-precision` 17.1 s, `override-fidelity` 13.9 s, `equity-curve`
  12.3 s, `/analytics/by-dimension` 7.0 s, `/equity/candles` 6.7 s,
  `/dashboard?mode=today` 5.8 s (p90 14.6 s), `/risk` 2.3 s.

**What this means for this spec.** Every repeat read removed here saves
seconds of server time, not bytes, and the 60 s page memory turns a 17–20 s
Analytics return into an instant one. It does not make any first load
faster: that is project 2's job, and the numbers above are its baseline too.

## Goals

1. A page revisited **within 60 s** of its last successful load shows its
   data at once, with an "as of HH:MM · updating" mark, and refreshes in the
   background. Older than 60 s: today's loading state (partner's choice).
2. A page whose data an event invalidated while the partner was elsewhere is
   **never** shown from memory — it loads fresh, whatever its age.
3. Analytics fetches `/analytics/performance` once per scope and serves it to
   every tab under the same 60 s rule; Attribution's four breakdown reads
   become one request.
4. Risk takes its balance from the `/risk` body it already fetches, not
   `/dashboard`.
5. The `/dashboard?scope=today` client fallback is deleted; the server
   already sends the `today` block where it is needed.
6. A degraded stream polls only what the current page listens to, every 15 s,
   backing off to 60 s after two minutes; page memory is off while degraded.
7. The same Playwright script measures before and after on production;
   the after numbers go into this spec's close-out commit.

## Non-goals

- No server-side caching, ETag or snapshot change (project 2).
- No layout, tab, navigation or content change on any page (project 3, v240).
- No change to what any figure means or how it is computed.
- No persistence across browser reloads (no localStorage/IndexedDB cache of
  API bodies): a full page load or the Refresh button always fetches fresh,
  as `freshInterceptor` already arranges.
- `/risk` readers (Risk page, System Providers) stay as they are; `/risk`
  already has a 15 s single-flight TTL on the server.

## Anti-goals

- **Showing a figure as current when it is not.** Every page served from
  memory carries its "as of" time until the background refresh lands. A
  failed background refresh keeps the mark and says it failed, as the
  existing per-panel error states do; it never silently drops the mark.
- **Showing stale prices as live.** The live-values overlay
  (`live-values.store.ts`) keeps patching prices on a page served from
  memory exactly as it does on a fresh one.
- **A cache that outlives a write.** Any mutation the partner makes
  (`requestMutationRefresh`) clears every remembered page, not just the
  current one.
- **Growing memory without bound.** The cache holds a bounded number of
  entries (a small fixed cap, least-recently-used out) and drops anything
  older than 60 s on read.

## Design

### 1. Page memory (the 60 s rule)

A root-provided cache keyed by **resolved route URL** (path + query string)
holds, per entry, the resolver's result, its fetch time, and a `stale` flag.

- On navigation, the resolver asks the cache first. An entry that is not
  `stale` and is younger than 60 s is handed to the route at once; the
  resolver then refetches in the background and swaps the result in when it
  lands. Otherwise the resolver runs as today.
- `RouteRefreshService` marks **every cached entry** whose route's
  `refreshOn` accepts a raised event as `stale`, not only the current route.
  The current route still refreshes as today.
- A mutation refresh empties the cache.
- The "as of HH:MM · updating" mark appears only on a page served from
  memory, from the moment it renders until its background refresh lands
  (then it disappears) or fails (then it reads "as of HH:MM · refresh
  failed"). One shared component, placed where each workspace already shows
  its header meta; on phone it wraps under the title, never truncates the
  title.

Builder's call: whether the cache keeps whole store states or resolver
outputs, as long as a page served from memory renders identically to a fresh
one with the same data (golden test per workspace).

### 2. Analytics: one performance read, one breakdown read

- `/analytics/performance` for a given scope is held at store level and
  reused by every tab under the 60 s rule and the stale flag, instead of
  being refetched in four resolvers.
- `/analytics/by-dimension` accepts several dimensions in one call
  (e.g. `dims=strategy,horizon,direction,dow`) and returns one block per
  dimension, each identical to today's single-dimension body. The single
  `dim` form stays working for any other caller. Attribution makes one
  breakdown request instead of four.
- A dimension that fails comes back as its own error block
  (`{"error": ...}` in place of its body) while the others succeed, so each
  bar list keeps its own error state as today. An unknown dimension name is
  a 400 for the whole request, as an unknown `dim` is today.

### 3. Risk balance from the read it already makes

`/risk` already returns `account.balance` (`risk.py` `_account_balance`),
and the Risk page already fetches `/risk`. `readBalance` and its
`/dashboard` call are deleted; the balance comes from the `/risk` body.
No new endpoint. (Author's call after the builder check: `/risk`'s value
falls back to `base_balance` and ignores a non-positive balance, where
`/dashboard` passes the raw config value. Taking every Risk-page figure from
one body is the more consistent of the two; a test pins that the KPI shows
`/risk`'s balance.)

### 4. Dashboard `today` fallback

The server already sends a `today` block for `all` and `range`
(`_TODAY_BLOCK_MODES`); `loadToday` only fires against an older backend. The
client fallback is deleted with its tests. A server test pins the `today`
block for `all` and `range`. The `active`/`today` responses and their frozen
goldens under `tests/admin_perf/golden/` stay byte-identical (author's call
after the builder check).

### 5. Degraded-stream polling

While degraded, the poller raises only the events the current route's
`refreshOn` accepts, every 15 s for the first 2 minutes of the outage, then
every 60 s until the stream recovers (author's call after the builder check:
a time-based back-off needs no change signal from the server, where an
"unchanged data" back-off would). Hidden tabs still skip; the 30 s SSE
recovery attempt stays.

**Page memory is off while degraded.** Events are no longer raised for other
routes, so their entries could not be marked `stale`; entering the degraded
state empties the cache and no page is served from memory until the stream
is live again. This keeps Goal 2 true during an outage.

### 6. Measurement

A Playwright script (kept under `scripts/dev/`, credentials from `.env`
loaded inside it and never printed) measures, at phone (390×844) and desktop
(1440×900), median of three runs: cold Dashboard, Dashboard→Trades→Dashboard,
Risk, and each Analytics tab in turn plus the return to Overview — request
count, API bytes, time-to-content — and 60 s idle on Dashboard. Its before
numbers are above; the after numbers are recorded at close-out.

## Testing

- Frontend: cache hit under 60 s, miss at 60 s, `stale` forces a miss,
  mutation empties the cache, LRU cap, "as of" mark lifecycle (shown,
  cleared on success, "refresh failed" on error), a page from memory renders
  identically to a fresh one (golden per workspace), live-values still patch
  a page from memory.
- Analytics: one performance request across all four tabs inside 60 s; one
  breakdown request on Attribution.
- Degraded poller: only current-route events raised; 15 s for two minutes,
  then 60 s; hidden tab skips; entering degraded empties page memory and
  nothing is served from memory until live again.
- Risk: the KPI balance is `/risk`'s `account.balance`; no `/dashboard`
  request from the Risk page.
- Backend: multi-dimension `by-dimension` equals the four single calls
  block for block; one failing dimension yields its error block while the
  others return; an unknown name is a 400; `/dashboard` carries `today` for
  `all` and `range`, and the `active`/`today` goldens are unchanged.
- UI checked at phone, tablet and desktop widths (`ui-design.md`).

## What follows

Project 2 (server cache) and project 3 (Dashboard/Trades content) each get
their own brainstorm and spec; then v240's plan.
