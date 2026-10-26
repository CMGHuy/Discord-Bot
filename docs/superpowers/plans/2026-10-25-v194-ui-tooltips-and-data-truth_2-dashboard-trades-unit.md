# v194 — UI integrity, part 2: Dashboard lifecycle counts, Trades "All" rows, FX rate provider

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V194-5:" -A 400 <this file>`.

**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) — sections B1, B2, B7
**Index:** [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md) — Global Constraints, `### Standard task close`, Handoff, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V194-4, V194-5, V194-6. V194-6b and V194-6c (the B7 conversion seam
and its frontend) are part 2b. Every task runs in the v194 worktree
(`WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v194-ui-tooltips-and-data-truth`,
created by V194-1). Never `cd` in a Bash call: use `--prefix`, `-C` or
absolute paths.

One deviation from the ledger, internal to V194-6 (no other part consumes
it): the ledger names `daily_bars_between` as the rate fetch path, but
`swingbot/core/marketdata/providers/router.py:427-441` is Alpaca-only with
no yfinance fallback, so a Yahoo FX pair (`USDEUR=X`) is never eligible and
always comes back `{}`. V194-6 instead goes through
`swingbot/core/marketdata/data_refresh.py:248` `refresh_symbol` and
`swingbot/core/marketdata/data_store.py:310` `load_normalized` — the
writer and reader of the yfinance daily cache `market_data/daily/`, the same
pair `swingbot/admin/freshness.py:136-148` `_refresh_yf_daily` uses — so the
rates land in an existing cache and no third one is added. The public
signatures (`account_currency_code`, `quote_currency_code`, `fx_rate`) are
exactly the ledger's.

### Task V194-4: B1 — diagnose on the replica; the store's today figures land, fail visibly and never hang

**Model:** opus — the root cause is not established; it needs a live diagnosis and a fix to request ordering in a signal store, a concurrency judgement the rubric puts at the top tier.

**Files:**
- Modify: `frontend/src/app/stores/dashboard.store.ts:14` (rxjs import), `:43-49` (`DashboardSlice`), `:57` (`NOT_RESPONDING`), `:100-106` (`failure`), `:167` (initial state), `:298` (`latestToday`), `:308-326` (`resolve`), `:332-342` (`loadToday`)
- Test: `frontend/src/app/stores/dashboard.store.spec.ts`

The ledger row V194-4 runs past the 400-line task ceiling written in full, so
it is split here: this task is the diagnosis and the store; V194-4b (next) is
the component fallback, the panel's failure line, the component tests and the
replica confirmation. The controller adds the `V194-4b` ledger row; no other
part consumes anything that moved.

**Interfaces:**
- Consumes: `lifecycleOf`, `todayLifecycle`, `loadToday`, `resolve` (all `dashboard.store.ts`); `routeRequest` (`frontend/src/app/routing/route-request.ts`).
- Produces for V194-4b: store state `todayError: string | null` (read as `store.todayError()`), `null` until a today fetch fails, cleared when a today answer lands; the Step 3 cause class (F1-F4) in the task notes; the local admin from Step 1 left running with `$WT/.env`, `$WT/swingbot/admin/static/app` and `$WT/frontend/scripts/diag-b1.tmp.mjs` in place (all untracked; never `git add`ed).

**What the spec asks.** Tab counts equal the API's lifecycle counts at 390,
768 and 1440 after load; Trading performance renders data or `sb-async`'s
error with Retry, never an indefinite skeleton. The root cause is found and
stated in the commit.

**Why three code paths are suspect** (read from the code, not yet observed):

1. `resolve()` (`dashboard.store.ts:308-326`) patches `todayData` only when its
   request is still current. A 1D load superseded by a wider pick (or by a
   second resolver run) is dropped whole, although a `mode=today` answer is
   today's figures whatever the scope became. Until another today fetch
   lands, `todayLifecycle()` is `[]` and every tab reads 0.
2. `loadToday()` (`:332-342`) on error only clears `todayLoading`: with no
   earlier today response the counts stay `[]` ("Open 0") and nothing says why.
3. `routeRequest` (`frontend/src/app/routing/route-request.ts`) calls
   neither `next` nor `error` when its subscriber unsubscribes first (the
   router cancels a resolver on a superseding navigation). `resolve()` then
   leaves `loading: true` and `data: null` for good: `asyncInputs` maps that
   to the skeleton (`frontend/src/app/ui/async.ts:293-310`).

- [ ] **Step 1: Sync the replica and serve a local admin from the worktree**

Run `/replicate-prod-db` (the first database-backed task of this plan; later
tasks reuse the shared `swing-db` container). Then build and serve the
worktree's bundle:

```bash
npm --prefix "$WT/frontend" ci
npm --prefix "$WT/frontend" run build
rm -rf "$WT/swingbot/admin/static/app"
cp -r "$WT/frontend/dist/frontend/browser" "$WT/swingbot/admin/static/app"
cp E:/Documents/Private/Projects/Discord-Bot/.env "$WT/.env"
```

`$WT/.env` is gitignored (`.gitignore:23`); never print, echo or `git add`
it. Point its database at the `swing-db` replica exactly as
`/replicate-prod-db` reports, then start `python "$WT/admin_ui.py"` with
`run_in_background` and sign in once:
`node "$WT/frontend/scripts/browse.mjs" login --base http://localhost:1234`
(it reads `ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env` itself).

- [ ] **Step 2: Capture the network, the panel state and the console at three widths**

Create `$WT/frontend/scripts/diag-b1.tmp.mjs` (a throwaway; deleted in
V194-4b Step 3, never committed):

```js
import { chromium } from 'playwright';
import { homedir } from 'node:os';
import { join } from 'node:path';

const BASE = process.argv[2] ?? 'http://localhost:1234';
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
const context = await chromium.launchPersistentContext(PROFILE, { headless: true, serviceWorkers: 'block' });
const short = (url) => url.replace(BASE, '');
for (const width of [1440, 768, 390]) {
  const page = await context.newPage();
  await page.setViewportSize({ width, height: 900 });
  const log = [];
  const isDashboard = (url) => url.includes('/api/v1/dashboard');
  page.on('console', (m) => log.push(`console.${m.type()}: ${m.text()}`));
  page.on('pageerror', (e) => log.push(`pageerror: ${e.message}`));
  page.on('request', (r) => { if (isDashboard(r.url())) log.push(`-> ${short(r.url())}`); });
  page.on('requestfailed', (r) => { if (isDashboard(r.url())) log.push(`x  ${short(r.url())} ${r.failure()?.errorText}`); });
  page.on('response', async (r) => {
    if (!isDashboard(r.url())) return;
    let lifecycle = null;
    try { lifecycle = (await r.json()).lifecycle; } catch { lifecycle = 'unreadable'; }
    log.push(`<- ${r.status()} ${short(r.url())} lifecycle=${JSON.stringify(lifecycle)}`);
  });
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(6000);
  const tabs = await page.$$eval('[role="tab"] .label', (els) => els.map((e) => e.textContent.replace(/\s+/g, ' ').trim()));
  const skeleton = (await page.$('sb-async.performance-async .skeleton')) !== null;
  const failed = (await page.$('sb-async.performance-async .failed')) !== null;
  console.log(`== ${width}px tabs=${JSON.stringify(tabs)} skeleton=${skeleton} error=${failed}`);
  for (const line of log) console.log(`   ${line}`);
  await page.close();
}
await context.close();
```

Run: `node "$WT/frontend/scripts/diag-b1.tmp.mjs" http://localhost:1234`

Expected before the fix: at 1440 and 768 `tabs` has `"Open 0"` while a
`<- 200 … mode=today` line shows `lifecycle={"ACTIVE":8,…}` (or no such
line), and `skeleton=true`; at 390 the counts match.

- [ ] **Step 3: Name the cause before touching code**

Classify the Step 2 log; write the class and the decisive lines into the
task notes (they go into the commit body in Step 7):

| Class | What the log shows | Fixed by |
|---|---|---|
| F1 superseded | a `-> …mode=today` answered 200 with counts, followed by another `/dashboard` request before it landed (a `mode=range`, or a second `mode=today` from a resolver rerun) | Step 6: a today answer lands whatever the scope became |
| F2 today failed | a `mode=today` request ends `x … net::ERR_…` or `<- 4xx/5xx` | Step 6: `todayError`; V194-4b: the card says so and the counts fall back to the scoped open counts |
| F3 cancelled | a `-> …` with no matching `<-` and a `x … net::ERR_ABORTED`, and `skeleton=true` | Step 6: a cancelled current request ends in an error with Retry |
| F4 other | anything else: a `pageerror`, counts in a 200 the UI never shows with no second request, no `/dashboard` request at all | **stop**: return `BLOCKED:` to the controller with the log; do not guess a fix |

This task's Steps 4-6 and V194-4b harden all of F1-F3 (each is a real defect in the code above, and
each has its own test); F4 means the cause is elsewhere and the hardening
alone would not be the fix.

- [ ] **Step 4: Write the failing store tests**

In `frontend/src/app/stores/dashboard.store.spec.ts`, append inside the
`describe("today's figures and the chart's Latest button", …)` block,
immediately before its closing `  });` on line 771 (it already installs fake
timers and defines `requests`, `modeOf`, `flushScoped`, `flushToday`,
`widenThenPush`, `TODAY`, `SCOPED`):

```ts
    /* -- v194 B1: today's figures never go missing for good ----------- */

    const fail = (req: { flush(body: unknown, opts: { status: number; statusText: string }): void }) =>
      req.flush('boom', { status: 500, statusText: 'Server Error' });

    it("lands a 1D answer as today's figures even after a wider pick superseded it", () => {
      tick();
      const [first] = requests();
      // Picked before the 1D load answered: the 1D request is no longer
      // current for the scoped figures, but its answer is still today's.
      store.setPreset('1M');
      first.flush({ ...RESPONSE, realized: TODAY });
      const closed = store.todayLifecycle().find((row) => row.status === 'CLOSED')?.count;
      expect(closed).toBe(3);
      expect(store.todayRealized()).toEqual(TODAY);
      expect(store.data()).toBeNull();
    });

    it('keeps the newest today answer when an older one lands after it', () => {
      const reqs = widenThenPush();
      flushScoped(reqs);
      flushToday(reqs, { amount: 30, pct: 1, n: 3, wins: 2, losses: 1 });
      // A second push issues a newer today fetch; the older one already landed.
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      const again = requests();
      flushScoped(again);
      flushToday(again, { amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 });
      expect(store.todayRealized()).toEqual({ amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 });
      expect(store.todayLoading()).toBe(false);
    });

    it('reports a failed today fetch instead of loading forever', () => {
      tick();
      const [first] = requests();
      store.setPreset('1M');
      fail(first);
      const reqs = requests();
      reqs.filter((r) => modeOf(r) === 'today').forEach(fail);
      flushScoped(reqs);
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).not.toBeNull();
      expect(store.todayLifecycle()).toEqual([]);
      expect(store.realized()).toEqual(SCOPED);
    });

    it('clears the today error once a today answer lands', () => {
      const reqs = widenThenPush();
      flushScoped(reqs);
      reqs.filter((r) => modeOf(r) === 'today').forEach(fail);
      expect(store.todayError()).not.toBeNull();
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      const again = requests();
      flushScoped(again);
      flushToday(again);
      expect(store.todayError()).toBeNull();
      expect(store.todayLoading()).toBe(false);
    });

    it('ends a request cancelled before it answered with an error, never an endless skeleton', () => {
      // No tick(): the onInit effect has not issued its own load, so this
      // subscription is the only, and current, request.
      const subscription = store.resolve().subscribe();
      expect(store.loading()).toBe(true);
      subscription.unsubscribe();
      expect(store.loading()).toBe(false);
      expect(store.error()).toBe('The dashboard request did not finish.');
      expect(store.todayLoading()).toBe(false);
    });

    it('lets a superseded request go quietly: the newer one owns loading', () => {
      const older = store.resolve().subscribe();
      store.resolve().subscribe();
      older.unsubscribe();
      expect(store.loading()).toBe(true);
      expect(store.error()).toBeNull();
    });
```

- [ ] **Step 5: Run them to see them fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/stores/dashboard.store.spec.ts`
Expected: FAIL — the first test reads `closed` as `undefined`; the
`todayError` tests fail on `store.todayError is not a function`; the
cancelled test reads `loading` as `true`.

- [ ] **Step 6: Make today's figures land, fail visibly and never hang (store)**

`frontend/src/app/stores/dashboard.store.ts`:

Line 14, add `finalize`:

```ts
import { Observable, Subject, debounceTime, defer, finalize } from 'rxjs';
```

`DashboardSlice` (`:43-49`), after `todayLoading: boolean;`:

```ts
  /** The last today fetch failed and no newer one has answered. Kept beside
   *  `todayData` (which keeps the previous figures) so the panel can say
   *  "couldn't load" instead of showing an em dash or a zero as if measured. */
  todayError: string | null;
```

After `const NOT_RESPONDING = 'The admin is not responding.';` (`:57`):

```ts
const NOT_FINISHED = 'The dashboard request did not finish.';
```

`failure` (`:100-106`) old → new:

```ts
function failure(hadData: boolean, error: ApiError): Partial<DashboardSlice> {
  return {
    loading: false,
    stale: hadData,
    error: error.code === 'unavailable' ? NOT_RESPONDING : error.message,
  };
}
```
→
```ts
function messageOf(error: ApiError): string {
  return error.code === 'unavailable' ? NOT_RESPONDING : error.message;
}

function failure(hadData: boolean, error: ApiError): Partial<DashboardSlice> {
  return { loading: false, stale: hadData, error: messageOf(error) };
}

/** A current request unsubscribed before it answered -- the router cancels
 *  a resolver's request when a newer navigation supersedes it. Neither
 *  handler of `routeRequest` runs then, so without this the store keeps
 *  `loading: true` over no data and `sb-async` shows its skeleton for good.
 *  It ends like a failure instead: an error with Retry, or a stale mark. */
function unfinished(hadData: boolean): Partial<DashboardSlice> {
  return { loading: false, stale: hadData, error: NOT_FINISHED };
}
```

Initial state (`:167`): `todayData: null, todayLoading: false,` →
`todayData: null, todayLoading: false, todayError: null,`

Line 298, `let latestToday = 0;` → the shared today stamps and their two
landing helpers:

```ts
    // Today's figures arrive by two roads -- a 1D scoped fetch and the
    // today-only fetch -- stamped on one counter. Any today answer is
    // today's, whatever the scope became meanwhile, so it lands unless a
    // newer today answer already has; `todayLoading` clears only once the
    // newest stamp has settled.
    let todayIssued = 0;
    let todayLanded = 0;
    const landToday = (stamp: number, data: Dashboard): void => {
      if (stamp < todayLanded) return;
      todayLanded = stamp;
      patchState(store, {
        todayData: data,
        todayError: null,
        ...(stamp === todayIssued ? { todayLoading: false } : {}),
      });
    };
    const failToday = (stamp: number, error: ApiError): void => {
      if (stamp === todayIssued) patchState(store, { todayLoading: false, todayError: messageOf(error) });
    };
```

`resolve` (`:308-326`) becomes:

```ts
    const resolve = (): Observable<void> => defer(() => {
      const request = ++latestRequest;
      const current = (): boolean => request === latestRequest;
      const { mode, window } = scopeToRequest(untracked(() => store.selection()), new Date());
      // Under 1D the scoped response is today's: stamped like a today fetch.
      const todayStamp = mode === 'today' ? ++todayIssued : 0;
      let settled = false;
      return routeRequest(api.dashboard(mode, window), {
        start: () => patchState(store, { loading: true }),
        next: (data) => {
          settled = true;
          if (todayStamp) landToday(todayStamp, data);
          if (current()) patchState(store, { data, loading: false, error: null, stale: false });
        },
        error: (error) => {
          settled = true;
          if (todayStamp) failToday(todayStamp, error);
          if (current()) patchState(store, failure(untracked(() => store.data()) !== null, error));
        },
      }).pipe(finalize(() => {
        if (settled || !current()) return;
        patchState(store, unfinished(untracked(() => store.data()) !== null));
        if (todayStamp === todayIssued) patchState(store, { todayLoading: false });
      }));
    });
```

`loadToday` (`:332-342`) becomes:

```ts
    /** Today's response alone, for the today-only figures when the scope is
     *  wider. A failure keeps the previous figures and says so. */
    const loadToday = (): void => {
      const stamp = ++todayIssued;
      patchState(store, { todayLoading: true });
      api.dashboard('today').subscribe({
        next: (data) => landToday(stamp, data),
        error: (error: ApiError) => failToday(stamp, error),
      });
    };
```

Run Step 5's command. Expected: PASS, the existing tests in the file too.

- [ ] **Step 7: Close**

Close: standard (test: `frontend/src/app/stores/dashboard.store.spec.ts`), with these deviations: commit
`fix(v194): dashboard store -- today answers land, fail visibly, never hang (V194-4)`
whose body states the Step 3 class (F1/F2/F3) and the decisive log lines
(URLs and status codes only -- no cookies, no payload values beyond the
lifecycle counts). Leave the local admin, the copied bundle, `$WT/.env` and
the diagnosis script for V194-4b.

### Task V194-4b: B1 — tab counts fall back to the scoped open counts; Realised today says when it failed; replica confirmed

**Model:** sonnet — two small bindings and a computed over a store contract V194-4 fixed, with tests in an existing spec pattern.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts:214` (`sb-trading-performance` bindings), `:715-717` (`lifecycleCounts`), plus one module constant after the imports
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts:225` (inputs), `:300` (`todaySub`), plus one module constant after the imports
- Test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`

**Interfaces:**
- Consumes: `store.todayError()` (V194-4); `todayLifecycle`, `lifecycle` (`dashboard.store.ts:276-279`); `lifecycleCounts` (`dashboard.ts:715`); `todaySub` (`trading-performance.ts:298-305`); `PositionsTable.counts` (`positions-table.ts:110`); V194-4's Step 3 class and its running local admin.
- Produces (local, no other task consumes them): `TradingPerformance.todayError` (`input<string | null>(null)`); `ALL_TIME_STATUSES` (module constant in `dashboard.ts`).

- [ ] **Step 1: Write the failing component tests**

Append to `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (after
the last `describe`; `seed`, `loaded`, `payload`, `flushTradeGroups` and the
`afterEach(() => vi.restoreAllMocks())` that undoes the width spy are at the
top of the file):

```ts
describe('Dashboard lifecycle tab counts (v194 B1)', () => {
  const LIFECYCLE = { PENDING: 2, ACTIVE: 8, PARTIAL: 1, CLOSED: 4, CANCELLED: 0 };
  const OPEN_COUNTS = { PENDING: 2, ACTIVE: 8, PARTIAL: 1 };
  const counts = (fixture: ComponentFixture<Dashboard>) =>
    (fixture.debugElement.query(By.directive(PositionsTable)).componentInstance as PositionsTable).counts();
  const tabLabels = (el: HTMLElement) => [...el.querySelectorAll('[role="tab"] .label')]
    .map((node) => node.textContent?.replace(/\s+/g, ' ').trim());
  const fail = (req: { flush(body: unknown, opts: { status: number; statusText: string }): void }) =>
    req.flush('boom', { status: 500, statusText: 'Server Error' });

  for (const width of [1440, 768, 390]) {
    it(`feeds the API's counts to the tabs at ${width}px`, async () => {
      // ViewportService reads innerWidth when created; seed() resets the module first.
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(width);
      const fixture = await loaded({ lifecycle: LIFECYCLE as never });
      expect(counts(fixture)).toEqual(LIFECYCLE);
    });
  }

  it('labels the tabs with those counts on desktop', async () => {
    const fixture = await loaded({ lifecycle: LIFECYCLE as never });
    expect(tabLabels(fixture.nativeElement as HTMLElement).slice(0, 3)).toEqual(['Pending 2', 'Open 8', 'Partial 1']);
  });

  /** 1D load superseded by 1M, then every today request fails; the 1M answer carries the counts. */
  async function todayFailedInPeriod(): Promise<ComponentFixture<Dashboard>> {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushTradeGroups(backend);
    const store = TestBed.inject(DashboardStore);
    const first = backend.expectOne('/api/v1/dashboard?mode=today');
    store.setPreset('1M');
    fail(first);
    for (const req of backend.match((r) => r.url === '/api/v1/dashboard')) {
      if (req.request.params.get('mode') === 'today') fail(req);
      else req.flush(payload({ scope: { mode: 'range' }, lifecycle: { ...LIFECYCLE, CLOSED: 40 } as never }));
    }
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it("falls back to the scoped answer's open counts when today's fetch failed", async () => {
    const fixture = await todayFailedInPeriod();
    // PENDING/ACTIVE/PARTIAL are all-time in every scope (dashboard.py
    // _lifecycle_counts); CLOSED/CANCELLED are today's only, so they stay unknown.
    expect(counts(fixture)).toEqual(OPEN_COUNTS);
  });

  it("says today's figures could not load instead of ringing forever", async () => {
    const fixture = await todayFailedInPeriod();
    const card = [...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('sb-metric-card')]
      .find((c) => c.querySelector('.label')!.textContent!.trim() === 'Realised today')!;
    expect(card.classList.contains('loading')).toBe(false);
    expect(card.textContent).toContain("couldn't load today's figures");
  });
});
```

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: FAIL — the fallback test reads `{}`; the card test misses the
text. The three width tests pass already (the counts path is fine once the
store has today's answer); they are the spec's required regression guard.

- [ ] **Step 2: Fall back to the scoped open counts; say when today failed (component and panel)**

`frontend/src/app/workspaces/dashboard/dashboard.ts`, after the last import:

```ts
/** Lifecycle statuses the server counts all-time in every scope
 *  (`_lifecycle_counts`): the scoped answer's numbers for these are as true
 *  as today's, so they stand in when today's fetch has failed. */
const ALL_TIME_STATUSES = new Set(['PENDING', 'ACTIVE', 'PARTIAL']);
```

`lifecycleCounts` (`:715-717`) old → new:

```ts
  protected readonly lifecycleCounts = computed(() =>
    Object.fromEntries(this.store.todayLifecycle().map((e) => [e.status, e.count])),
  );
```
→
```ts
  protected readonly lifecycleCounts = computed(() => {
    const today = this.store.todayLifecycle();
    const rows = today.length > 0
      ? today
      : this.store.lifecycle().filter((e) => ALL_TIME_STATUSES.has(e.status));
    return Object.fromEntries(rows.map((e) => [e.status, e.count]));
  });
```

Line 214, after `[todayLoading]="store.todayLoading()"` add:

```html
      [todayError]="store.todayError()"
```

`frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`, after
the last import:

```ts
/** The Realised today sub-line when today's fetch failed and nothing
 *  earlier landed: an em dash alone would read as "nothing closed". */
const TODAY_UNAVAILABLE = "couldn't load today's figures";
```

After `readonly todayLoading = input(false);` (`:225`):

```ts
  /** Today's fetch failed (`DashboardStore.todayError`); the card says so. */
  readonly todayError = input<string | null>(null);
```

`todaySub` (`:300`), `if (today === null) return null;` →

```ts
    if (today === null) return this.todayError() === null ? null : TODAY_UNAVAILABLE;
```

Run Step 1's command. Expected: PASS, the rest of the file too.

- [ ] **Step 3: Confirm on the replica, clean up, close**

Rebuild and re-serve (V194-4 Step 1's `npm run build`, `rm -rf`, `cp -r`;
restart the background `admin_ui.py`), then re-run V194-4 Step 2's script. Expected: at
1440, 768 and 390 the `Open N` label equals the `ACTIVE` of the
`mode=today` answer, and `skeleton=false` (data, or `error=true` with Retry
if a request truly failed). Then delete the throwaway script, the copied
bundle and the copied `.env`:

```bash
rm "$WT/frontend/scripts/diag-b1.tmp.mjs"
rm -rf "$WT/swingbot/admin/static/app"
rm "$WT/.env"
```

If a width still shows a wrong count or a lasting skeleton, the cause is not
the one V194-4 named: stop and return `BLOCKED:` with the new log.

Close: standard (test: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`), with this deviation: commit
`fix(v194): dashboard tab counts fall back, Realised today says when it failed (V194-4b)`,
body: the three widths' confirmed `Open N` against the API's `ACTIVE`.

### Task V194-5: B2 — "All" rows asks for `per_page=200`, fresh and restored from prefs

**Model:** sonnet — a contained route-resolver fix with a known root cause and a pure function to test.

**Files:**
- Modify: `frontend/src/app/workspaces/trades/trades.routes.ts:1-15` (whole file: imports, `queryFor`, the resolver)
- Create: `frontend/src/app/workspaces/trades/trades.routes.spec.ts`

**Interfaces:**
- Consumes: `ALL_PER_PAGE`, `API_MAX_PER_PAGE`, `PER_PAGE_OPTIONS`, `perPageForApi`, `readTablePerPage` (`frontend/src/app/ui/table-prefs.ts:26,31,38,58,121`); `TRADES_TABLE_ID` (`frontend/src/app/workspaces/trades/trades.columns.ts:101`); `PreferencesStore.values` (`frontend/src/app/stores/preferences.store.ts:87`); `ViewportService.isNarrow` (`frontend/src/app/ui/breakpoints.ts:49`); `resolveRoute` (`frontend/src/app/routing/route-resolver.ts`); `TradesStore.setQuery` / `resolve` (`frontend/src/app/stores/trades.store.ts:141-152`).
- Produces (local; no other task consumes it): `queryFor` becomes exported with a second parameter, `queryFor(route: ActivatedRouteSnapshot, savedPerPage: number): TradeQuery`. `DEFAULT_PER_PAGE` is no longer imported here (it stays exported from `trades.store.ts`).

**Root cause (known, Handoff).** `queryFor`
(`trades.routes.ts:8-14`) reads `per_page` as
`Number(raw ?? DEFAULT_PER_PAGE) || DEFAULT_PER_PAGE`: "All" is `0` in the URL
(`ALL_PER_PAGE`), `0 || 10` is 10, and the resolver's `store.resolve()`
fetches 10 rows. The component's effect (`trades.ts:880-916`) does compute
`perPageForApi(this.perPage())` = 200, but it calls `setQuery(query, false)`,
which never loads — so the page shows the resolver's 10 rows under a pager
whose `perPageChoice` is "All": "1–10 of 1272 (capped)". With no `per_page`
in the URL, the resolver also ignores the saved preference that
`tablePerPage` (`frontend/src/app/ui/table-per-page.ts:16-23`) gives the
component. `runGuardsAndResolvers: 'always'` reruns the resolver on every
`navigate`, so each filter change repeats it.

**Fix.** The resolver reads the same value the component shows: the URL's
`per_page` when it names an offered choice (`PER_PAGE_OPTIONS`, "All"
included), else the saved choice for this table and device class
(`readTablePerPage`, whose fallback is the device default 10 / 5), and sends
it through `perPageForApi`, which turns "All" into the API's 200-row cap. The
"(capped)" label needs no change: `sb-pagination`'s `rangeLabel`
(`frontend/src/app/ui/pagination.ts:86`) already prints it when the choice is
"All" and the total exceeds the 200 rows served, and
`frontend/src/app/ui/pagination.spec.ts:144-153` covers it.

Behaviour change to state in the commit: with nothing saved and no URL
`per_page`, a phone or tablet now asks for 5 rows — the number its pager
already showed — instead of 10.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/trades/trades.routes.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  ResolveFn,
  RouterStateSnapshot,
  convertToParamMap,
} from '@angular/router';
import { Observable, of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Preferences } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { SessionStore } from '../../stores/session.store';
import { TradesStore } from '../../stores/trades.store';
import { ViewportService } from '../../ui/breakpoints';
import { ALL_PER_PAGE, API_MAX_PER_PAGE } from '../../ui/table-prefs';
import { queryFor, tradesRoutes } from './trades.routes';

/* v194 B2 -- "All" rows asks the API for its 200-row cap, whether the
 * choice arrives in the URL or is restored from the saved preference. */

const snapshot = (params: Record<string, string>) =>
  ({ queryParamMap: convertToParamMap(params) }) as ActivatedRouteSnapshot;

describe('queryFor', () => {
  it('turns "All" in the URL into the API cap, not the default 10', () => {
    expect(queryFor(snapshot({ per_page: String(ALL_PER_PAGE) }), 10).per_page).toBe(API_MAX_PER_PAGE);
  });

  it('uses the saved choice when the URL names none', () => {
    expect(queryFor(snapshot({}), ALL_PER_PAGE).per_page).toBe(API_MAX_PER_PAGE);
    expect(queryFor(snapshot({}), 50).per_page).toBe(50);
  });

  it('lets an offered URL choice win over the saved one', () => {
    expect(queryFor(snapshot({ per_page: '50' }), ALL_PER_PAGE).per_page).toBe(50);
    expect(queryFor(snapshot({ per_page: '0' }), 20).per_page).toBe(API_MAX_PER_PAGE);
  });

  it('ignores a URL value that is not an offered choice', () => {
    for (const raw of ['', ' ', 'abc', '7', '-1', '1e2', '500']) {
      expect(queryFor(snapshot({ per_page: raw }), 20).per_page).toBe(20);
    }
  });

  it('still reads page, sort and the filters as before', () => {
    const query = queryFor(snapshot({ page: '3', sort: '-pnl_pct', status: 'open', ticker: 'AAPL' }), 10);
    expect(query).toEqual({ page: 3, per_page: 10, sort: '-pnl_pct', status: 'open', ticker: 'AAPL' });
    expect(queryFor(snapshot({ page: 'x' }), 10).page).toBe(1);
  });
});

describe('the Trades route resolver', () => {
  /** Runs the real resolver with the given saved preferences, URL params and
   *  device class; returns the one /api/v1/trades request it made. */
  function resolveWith(prefs: Preferences, params: Record<string, string>, narrow = false) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: { changes: () => signal(0) } },
        { provide: PreferencesStore, useValue: { resolve: () => of(undefined), values: () => prefs } },
        { provide: SessionStore, useValue: { expire: () => undefined } },
        { provide: ViewportService, useValue: { isNarrow: signal(narrow) } },
        TradesStore,
      ],
    });
    const resolver = tradesRoutes[0].resolve!['ready'] as ResolveFn<boolean>;
    const state = { url: '/trades' } as RouterStateSnapshot;
    (TestBed.runInInjectionContext(() => resolver(snapshot(params), state)) as Observable<boolean>).subscribe();
    return TestBed.inject(HttpTestingController).expectOne((r) => r.url === '/api/v1/trades');
  }

  it('requests per_page=200 when "All" is chosen (it lands in the URL as 0)', () => {
    const request = resolveWith({} as Preferences, { per_page: String(ALL_PER_PAGE) });
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('requests per_page=200 for a saved "All" with no per_page in the URL', () => {
    const request = resolveWith({ 'tables.trades.desktop.per_page': ALL_PER_PAGE } as Preferences, {});
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('restores a saved "All" on a phone or tablet from that device class\'s key', () => {
    const request = resolveWith({ 'tables.trades.compact.per_page': ALL_PER_PAGE } as Preferences, {}, true);
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('asks for the desktop default when nothing is saved', () => {
    expect(resolveWith({} as Preferences, {}).request.params.get('per_page')).toBe('10');
  });

  it('asks for the compact default on a phone or tablet when nothing is saved', () => {
    expect(resolveWith({} as Preferences, {}, true).request.params.get('per_page')).toBe('5');
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.routes.spec.ts`
Expected: FAIL — compile error, `queryFor` is not exported from `./trades.routes`.

- [ ] **Step 3: Rewrite `trades.routes.ts`**

Replace the whole of `frontend/src/app/workspaces/trades/trades.routes.ts`
(15 lines; the old `queryFor` is quoted under **Root cause**) with:

```ts
import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { PreferencesStore } from '../../stores/preferences.store';
import { TradesStore } from '../../stores/trades.store';
import { TradeQuery } from '../../api/models';
import { ViewportService } from '../../ui/breakpoints';
import { PER_PAGE_OPTIONS, perPageForApi, readTablePerPage } from '../../ui/table-prefs';
import { TRADES_TABLE_ID } from './trades.columns';

/** An offered per-page choice spelled in the URL, else null. Digits only:
 *  `Number('')` is 0, which is "All", and an empty `?per_page=` must not ask
 *  for 200 rows. */
function urlPerPage(raw: string | null): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return (PER_PAGE_OPTIONS as readonly number[]).includes(value) ? value : null;
}

/**
 * The request the resolver sends. `per_page` is the value the component
 * shows: the URL's when it names an offered choice, else `savedPerPage` (the
 * saved choice for this table and device class). Either way `perPageForApi`
 * turns "All" (0) into the API's 200-row cap.
 *
 * v194 B2: this used to read `Number(raw ?? 10) || 10`, which turned "All"
 * into 10 rows under a pager that said "All", and never read the saved
 * choice at all.
 */
export const queryFor = (route: ActivatedRouteSnapshot, savedPerPage: number): TradeQuery => ({
  page: Number(route.queryParamMap.get('page') ?? 1) || 1,
  per_page: perPageForApi(urlPerPage(route.queryParamMap.get('per_page')) ?? savedPerPage),
  sort: route.queryParamMap.get('sort') ?? undefined,
  status: route.queryParamMap.get('status') ?? undefined,
  ticker: route.queryParamMap.get('ticker') ?? undefined,
});

/** The saved per-page choice, read the way `tablePerPage` reads it for the
 *  component. `resolveRoute` resolves preferences before this runs. */
function savedPerPage(): number {
  const preferences = inject(PreferencesStore);
  const viewport = inject(ViewportService);
  return readTablePerPage(preferences.values(), TRADES_TABLE_ID, viewport.isNarrow());
}

export const tradesRoutes: Routes = [{
  path: '',
  providers: [TradesStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Trades', onEvents('trades')),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(TradesStore);
      store.setQuery(queryFor(route, savedPerPage()), false);
      return store.resolve();
    }),
  },
  loadComponent: () => import('./trades').then((m) => m.Trades),
}];
```

- [ ] **Step 4: Run it to see it pass**

Run Step 2's command. Expected: PASS (10 tests). Then
`npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/trades/trades.spec.ts`
→ PASS unchanged (the component's own effect and `onPerPage` are untouched).

- [ ] **Step 5: Close**

Close: standard (test: `frontend/src/app/workspaces/trades/trades.routes.spec.ts`), with this deviation: commit
`fix(v194): Trades "All" rows asks for the 200-row cap, from the URL or the saved choice (V194-5)`,
body: the root cause line above and the compact-default behaviour change.

### Task V194-6: B7 FX — `prod-inspector` check; `fx_rate` over the yfinance daily cache

**Model:** sonnet — a new pure-ish module with injected I/O seams and table-driven tests; the read-only production check is routed to `prod-inspector` (haiku).

**Files:**
- Create: `swingbot/core/marketdata/fx.py`
- Create: `tests/marketdata/test_fx.py` (suite `market-data`, `tests/suites.toml:21-23`; the directory is already listed)

**Interfaces:**
- Consumes: `refresh_symbol(symbol, timeframe, …)` (`swingbot/core/marketdata/data_refresh.py:248`); `load_normalized(ticker, interval, …)` (`swingbot/core/marketdata/data_store.py:310`); `asker_scope` (`swingbot/core/marketdata/providers/router.py:125`); `resolve_asker`, `Asker.ADMIN_PAGE` (`swingbot/core/marketdata/shared/kinds.py:42,156`); `swallowed` (`swingbot/core/infra/swallowed.py:62`).
The ledger row V194-6 runs past the 400-line task ceiling written in full, so
it is split: this task is the production check and `fx_rate`; V194-6a (next)
adds `account_currency_code` and `quote_currency_code` to the same module.
The controller adds the `V194-6a` ledger row; the public contract is
unchanged and V194-6b consumes it once both are done.

- Produces (the ledger contract V194-6b consumes, exactly; the first two land in V194-6a):
  - `account_currency_code() -> str` — ISO code from `CURRENCY_SYMBOL` via the inverse of `CURRENCY_SYMBOLS` (first upper-case code in dict order, so `$` → `USD`, `£` → `GBP`, `¥` → `JPY`); a symbol that is itself a listed code is that code; `EUR` when unknown.
  - `quote_currency_code(ticker: str) -> str | None` — the ticker's own quote currency as Yahoo reports it (`'USD'`, `'EUR'`, or a minor unit such as `'GBp'`), memoised per process; `None` when it cannot be determined.
  - `fx_rate(from_code: str, to_code: str, on: date) -> float | None` — the multiplier that turns an amount in `from_code` into `to_code`: `1.0` when the codes are equal (no fetch); else the `{FROM}{TO}=X` daily close on `on`, else the last prior close within `FALLBACK_DAYS = 7` days, else `None`. Minor units scale (`GBp` → `GBP` × 0.01). A `datetime` `on` is read as its date. Never a silent 1.0 for a missing rate.

**Deviation from the ledger's fetch path** (see this part's header): rates go
through `data_refresh.refresh_symbol` + `data_store.load_normalized`, the
yfinance daily cache's writer and reader, because `daily_bars_between` is
Alpaca-only and never returns an FX pair. A pair file lands at
`market_data/daily/<safe symbol>.csv` beside every other yfinance daily
frame: no third cache (`docs/claude/known-traps.md` § Two OHLCV caches,
§ Shared market-data layer). `fx.py` imports no provider SDK; the only
provider call is the existing `refresh_symbol` writer, run under
`asker_scope(ADMIN_PAGE)` because the conversion is display-only (admin).

- [ ] **Step 1: Ask production what currencies the book actually holds (read-only)**

Dispatch `prod-inspector` with one question: "Which quote currencies do the
closed trades' tickers have, what is the account's currency symbol, and are
any FX pair files already cached?" — and this script, piped in (nothing on
the VM is changed):

```python
# stdin script for: bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < this
import os
from collections import Counter

from swingbot import config
from swingbot.commands.scanning.equity_recorder import load_trades
from swingbot.core.marketdata import data, data_store

closed = [t for t in load_trades() if str(t.get("status", "")).upper() == "CLOSED"]
tickers = sorted({str(t.get("ticker") or "").upper().strip() for t in closed} - {""})
codes, unresolved = Counter(), []
for ticker in tickers:
    code, answered = data._provider_currency_code(ticker)
    if code:
        codes[str(code)] += 1
    else:
        unresolved.append((ticker, answered))
print("account symbol:", config.CURRENCY_SYMBOL, "| layer:", config.MARKETDATA_LAYER)
print("closed trades:", len(closed), "| distinct tickers:", len(tickers))
print("quote currencies (tickers per code):", dict(codes))
print("unresolved:", len(unresolved), unresolved[:20])
for pair in ("USDEUR=X", "GBPEUR=X", "EURUSD=X"):
    print(pair, "cached:", os.path.exists(data_store.cache_path(pair, "daily")))
```

Record the answer in the task notes (V194-6b reads it): the account code,
the distinct quote codes with counts, how many tickers are unresolved
(those rows will be flagged `fx_missing`), and whether any code is a minor
unit (`GBp`, `ZAc`, `ILA`). Expected: account `€`; quote codes dominated by
`USD`. If the account symbol is not `€`, `$` or `£`, stop and return
`BLOCKED:` (the setting's options are those three, `swingbot/config.py:512`).

- [ ] **Step 2: Write the failing tests**

Create `tests/marketdata/test_fx.py`:

```python
"""v194 B7: the FX rate provider behind the admin's account-currency money.

Every test isolates the module's two per-process memos and replaces the
cache writer/reader, so nothing here touches the network or `market_data/`.
"""
from datetime import date, datetime

import pandas as pd
import pytest

from swingbot.core.marketdata import fx


def _frame(closes: dict[str, float]) -> pd.DataFrame:
    index = pd.DatetimeIndex(list(closes))
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "High": values, "Low": values,
                         "Close": values, "Volume": [0] * len(values)}, index=index)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(fx, "_frames", {})


@pytest.fixture
def cache(monkeypatch):
    """The pair files a test puts here are what `load_normalized` returns;
    `refreshed` records every `refresh_symbol` call."""
    frames: dict[str, pd.DataFrame] = {}
    refreshed: list[tuple[str, str]] = []

    def refresh(symbol, timeframe, *args, **kwargs):
        refreshed.append((symbol, timeframe))
        return {"status": "fresh"}

    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", refresh)
    monkeypatch.setattr(fx.data_store, "load_normalized", lambda symbol, interval, *a, **k: frames.get(symbol))
    return frames, refreshed


# -- fx_rate ----------------------------------------------------------------

def test_same_currency_is_identity_with_no_fetch(cache):
    _, refreshed = cache
    assert fx.fx_rate("EUR", "EUR", date(2026, 10, 20)) == 1.0
    assert fx.fx_rate("usd", "USD", date(2026, 10, 20)) == 1.0
    assert refreshed == []


def test_converts_at_the_exit_dates_close(cache):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92, "2026-10-21": 0.93})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.92)
    assert refreshed == [("USDEUR=X", "daily")]


def test_falls_back_to_the_last_prior_trading_days_close(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-16": 0.90, "2026-10-19": 0.91})
    # Sunday 2026-10-18 has no bar: Friday's close stands.
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 18)) == pytest.approx(0.90)


def test_never_reaches_past_the_fallback_window(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-01": 0.90})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 1 + fx.FALLBACK_DAYS)) == pytest.approx(0.90)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 2 + fx.FALLBACK_DAYS)) is None


def test_never_uses_a_later_close(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-21": 0.93})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None


def test_a_missing_pair_is_none_never_one(cache):
    _, refreshed = cache
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None
    # The miss is remembered: a page of 200 rows asks the cache once.
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 21)) is None
    assert refreshed == [("USDEUR=X", "daily")]


@pytest.mark.parametrize("closes", [
    {},
    {"2026-10-20": float("nan")},
    {"2026-10-20": 0.0},
    {"2026-10-20": -1.0},
])
def test_an_unusable_close_is_none(cache, closes):
    frames, _ = cache
    frames["USDEUR=X"] = _frame(closes)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) is None


@pytest.mark.parametrize("src,dst", [("", "EUR"), ("USD", ""), (None, "EUR"), ("USD", None)])
def test_an_unknown_code_is_none(cache, src, dst):
    assert fx.fx_rate(src, dst, date(2026, 10, 20)) is None


def test_minor_units_scale_to_their_major_currency(cache):
    frames, _ = cache
    frames["GBPEUR=X"] = _frame({"2026-10-20": 1.15})
    assert fx.fx_rate("GBp", "GBP", date(2026, 10, 20)) == pytest.approx(0.01)
    assert fx.fx_rate("GBp", "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)


def test_a_datetime_is_read_as_its_date(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})
    assert fx.fx_rate("USD", "EUR", datetime(2026, 10, 20, 21, 5)) == pytest.approx(0.92)


def test_a_failed_refresh_still_reads_what_the_cache_has(cache, monkeypatch):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})

    def boom(*args, **kwargs):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", boom)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.92)


def test_a_loaded_pair_is_reused_within_the_ttl(cache, monkeypatch):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-20": 0.92})
    clock = iter([1000.0, 1000.0 + fx.FRAME_TTL_S - 1, 1000.0 + fx.FRAME_TTL_S + 1])
    monkeypatch.setattr(fx, "_clock", lambda: next(clock))
    for _ in range(3):
        fx.fx_rate("USD", "EUR", date(2026, 10, 20))
    assert len(refreshed) == 2


```

- [ ] **Step 3: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fx.py`
Expected: FAIL — `ImportError: cannot import name 'fx' from 'swingbot.core.marketdata'`.

- [ ] **Step 4: Write `swingbot/core/marketdata/fx.py`**

```python
"""Read-side FX for the admin's money figures (v194 B7).

Every stored `realized_pnl_amount` is `shares * (exit - entry)` in its
instrument's quote currency; the admin shows money in the account currency.
This module answers the three questions that conversion needs and nothing
more: what the account currency is, what a ticker is quoted in, and what one
unit of one currency was worth in another on a given day.

Rates are Yahoo FX pairs (`USDEUR=X` is EUR per USD), daily closes, kept in
the yfinance daily cache `market_data/daily/` through
`data_refresh.refresh_symbol` -- the writer every other yfinance daily frame
uses -- so there is no third cache (docs/claude/known-traps.md). Not
`router.daily_bars_between`: that path is Alpaca-only and never serves an FX
pair.

Display only. Nothing here feeds sizing, the account balance, the
kill-switch or a stored record; a missing rate is `None`, never 1.0, so a
caller can flag the row instead of showing a dollar amount as euros.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import pandas as pd

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.kinds import Asker

log = logging.getLogger(__name__)

#: How far back a missing exit-date bar may fall back. A long weekend plus a
#: holiday is four days; a week covers every market closure without letting
#: a stale rate stand in for a missing one.
FALLBACK_DAYS = 7

#: How long this process trusts a loaded pair frame (or a miss) before asking
#: the cache again: one admin page converts hundreds of rows.
FRAME_TTL_S = 15 * 60

#: Yahoo quotes some exchanges in a minor unit: LSE pence, JSE cents, TASE agorot.
MINOR_UNITS: dict[str, tuple[str, float]] = {
    "GBp": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01),
}

_frames: dict[str, tuple[float, pd.DataFrame | None]] = {}


def fx_rate(from_code: str, to_code: str, on: date) -> float | None:
    """The multiplier turning an amount in `from_code` into `to_code` on `on`.

    1.0 for equal codes, with no fetch. Otherwise the `{FROM}{TO}=X` close on
    `on`, else the last close within FALLBACK_DAYS before it, else None.
    Minor units scale (GBp -> GBP x 0.01).
    """
    if not from_code or not to_code:
        return None
    src, src_scale = _major(from_code)
    dst, dst_scale = _major(to_code)
    scale = src_scale / dst_scale
    if src == dst:
        return scale
    day = on.date() if isinstance(on, datetime) else on
    close = _close_on_or_before(_pair_frame(f"{src}{dst}=X"), day)
    return None if close is None else close * scale


def _major(code: str) -> tuple[str, float]:
    raw = str(code).strip()
    if raw in MINOR_UNITS:
        return MINOR_UNITS[raw]
    return raw.upper(), 1.0


def _clock() -> float:
    """The memo's clock; a seam so tests never patch the stdlib `time`."""
    return time.monotonic()


def _pair_frame(pair: str) -> pd.DataFrame | None:
    """The pair's cached daily frame, refreshed at most once per FRAME_TTL_S."""
    now = _clock()
    hit = _frames.get(pair)
    if hit is not None and now - hit[0] < FRAME_TTL_S:
        return hit[1]
    frame = _refreshed_frame(pair)
    _frames[pair] = (now, frame)
    return frame


def _refreshed_frame(pair: str) -> pd.DataFrame | None:
    """Bring the cache file up to date (a fresh file costs one mtime check),
    then read it. A failed refresh still serves whatever is on disk."""
    try:
        with router.asker_scope(kinds.resolve_asker(Asker.ADMIN_PAGE)):
            data_refresh.refresh_symbol(pair, "daily")
    except Exception as exc:
        swallowed(log, "marketdata.fx.refresh", exc, "FX refresh failed for %s: %s",
                  pair, exc, level=logging.DEBUG)
    return data_store.load_normalized(pair, "daily")


def _close_on_or_before(frame: pd.DataFrame | None, day: date) -> float | None:
    """The last positive close dated within [day - FALLBACK_DAYS, day]."""
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return None
    earliest = day - timedelta(days=FALLBACK_DAYS)
    dates = [stamp.date() for stamp in pd.to_datetime(frame.index)]
    keep = [earliest <= d <= day for d in dates]
    closes = pd.to_numeric(frame["Close"][keep], errors="coerce").dropna()
    closes = closes[closes > 0]
    return float(closes.iloc[-1]) if len(closes) else None
```

The frame is read in index order; `load_normalized` returns it sorted
ascending (the scan's consumers rely on that), so `iloc[-1]` is the latest
kept close.

- [ ] **Step 5: Run them to see them pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fx.py`
Expected: PASS (all tests, `0 failed`, `0 xfailed`). Then
`python scripts/dev/testrun.py suite market-data` → green (nothing imports
`fx` yet; this catches an import-time cycle through `data_refresh`).

- [ ] **Step 6: Close**

Close: standard (test: `tests/marketdata/test_fx.py`), with this deviation: commit
`feat(v194): fx_rate over the yfinance daily cache (V194-6)`, body:
the Step 1 answer (account code, quote codes with counts, unresolved
count) and the `daily_bars_between` → `refresh_symbol` deviation with its
reason.

### Task V194-6a: B7 FX — `account_currency_code` and `quote_currency_code`

**Model:** sonnet — two small lookups added to the module V194-6 created, with table-driven tests.

**Files:**
- Modify: `swingbot/core/marketdata/fx.py` (created by V194-6: its imports, its constants block, and two functions inserted before `fx_rate`)
- Modify: `tests/marketdata/test_fx.py` (created by V194-6: one import, the autouse fixture, two test sections appended)

**Interfaces:**
- Consumes: `fx.py` and `test_fx.py` from V194-6 (`_isolated` fixture, `MINOR_UNITS`); `CURRENCY_SYMBOLS` (`swingbot/core/marketdata/data.py:460-465`); `_provider_currency_code(key) -> (code, answered)` (`swingbot/core/marketdata/data.py:655-663`); `config.CURRENCY_SYMBOL` (`swingbot/config.py:510-513`); `asker_scope`, `resolve_asker`, `Asker.ADMIN_PAGE` (already imported by V194-6).
- Produces (ledger contract for V194-6b): `account_currency_code() -> str`; `quote_currency_code(ticker: str) -> str | None`, exactly as V194-6's **Interfaces** states them. `quote_currency_code` returns Yahoo's code **unnormalised** (`'GBp'` stays `'GBp'`): the minor unit is resolved in one place, `fx_rate` (`_major`, V194-6), so V194-6b passes the code straight through and `fx_rate('GBp', 'EUR', d)` is `fx_rate('GBP', 'EUR', d) × 0.01` (V194-6's `test_minor_units_scale_to_their_major_currency`). The `GBp` case is also tested end to end below.

- [ ] **Step 1: Write the failing tests**

In `tests/marketdata/test_fx.py`: change the import block's
`from swingbot.core.marketdata import fx` to

```python
from swingbot import config
from swingbot.core.marketdata import fx
```

add `    monkeypatch.setattr(fx, "_quote_codes", {})` as the second line of the
autouse `_isolated` fixture, and append at the end of the file:

```python
# -- account_currency_code ----------------------------------------------------

@pytest.mark.parametrize("symbol,code", [
    ("€", "EUR"), ("$", "USD"), ("£", "GBP"), ("¥", "JPY"), ("CHF", "CHF"),
    ("USD", "USD"), (" € ", "EUR"), ("?", "EUR"), ("", "EUR"), ("GBp", "EUR"),
])
def test_account_currency_code_inverts_the_symbol_table(monkeypatch, symbol, code):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", symbol)
    assert fx.account_currency_code() == code


# -- quote_currency_code ------------------------------------------------------

def test_quote_currency_code_is_the_tickers_own_and_memoised(monkeypatch):
    calls = []

    def lookup(key):
        calls.append(key)
        return {"AAPL": ("USD", True), "ASML.AS": ("EUR", True), "VOD.L": ("GBp", True)}[key]

    monkeypatch.setattr(fx.data, "_provider_currency_code", lookup)
    assert fx.quote_currency_code(" aapl ") == "USD"
    assert fx.quote_currency_code("ASML.AS") == "EUR"
    assert fx.quote_currency_code("VOD.L") == "GBp"
    assert fx.quote_currency_code("AAPL") == "USD"
    assert calls == ["AAPL", "ASML.AS", "VOD.L"]


@pytest.mark.parametrize("reply", [(None, True), ("", True), ("USD", False), (None, False)])
def test_quote_currency_code_is_none_when_unknown_and_not_remembered(monkeypatch, reply):
    calls = []
    monkeypatch.setattr(fx.data, "_provider_currency_code", lambda key: calls.append(key) or reply)
    assert fx.quote_currency_code("XYZ") is None
    assert fx.quote_currency_code("XYZ") is None
    assert calls == ["XYZ", "XYZ"]


def test_quote_currency_code_survives_a_failed_lookup(monkeypatch):
    def boom(key):
        raise RuntimeError("metadata down")

    monkeypatch.setattr(fx.data, "_provider_currency_code", boom)
    assert fx.quote_currency_code("AAPL") is None
    assert fx.quote_currency_code("") is None
    assert fx.quote_currency_code(None) is None


def test_a_pence_quoted_ticker_converts_at_one_hundredth_of_the_pound(cache, monkeypatch):
    frames, _ = cache
    frames["GBPEUR=X"] = _frame({"2026-10-20": 1.15})
    monkeypatch.setattr(fx.data, "_provider_currency_code", lambda key: ("GBp", True))
    code = fx.quote_currency_code("VOD.L")
    assert code == "GBp"
    assert fx.fx_rate(code, "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fx.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.marketdata.fx' has no attribute '_quote_codes'` (from the fixture), and the new tests error.

- [ ] **Step 3: Add the two lookups to `fx.py`**

Imports: `from swingbot.core.marketdata import data_refresh, data_store` →

```python
from swingbot import config
from swingbot.core.marketdata import data, data_refresh, data_store
```

(`from swingbot import config` goes above the `swallowed` import, keeping the
block sorted.) Constants: replace
`_frames: dict[str, tuple[float, pd.DataFrame | None]] = {}` with

```python
#: `CURRENCY_SYMBOL`'s default (swingbot/config.py) and the answer for an
#: unrecognised symbol.
DEFAULT_ACCOUNT_CODE = "EUR"

_frames: dict[str, tuple[float, pd.DataFrame | None]] = {}
_quote_codes: dict[str, str] = {}
```

Insert immediately before `def fx_rate(`:

```python
def account_currency_code() -> str:
    """The account currency's ISO code, from `CURRENCY_SYMBOL`.

    The inverse of `data.CURRENCY_SYMBOLS`, first upper-case code in its
    order: '$' is USD (not MXN), '£' is GBP (not pence), '¥' is JPY. A symbol
    that is itself a listed code ('USD') is that code; anything else is EUR.
    """
    symbol = str(getattr(config, "CURRENCY_SYMBOL", "") or "").strip()
    if symbol.isupper() and symbol in data.CURRENCY_SYMBOLS:
        return symbol
    for code, sign in data.CURRENCY_SYMBOLS.items():
        if code.isupper() and symbol and sign.strip() == symbol:
            return code
    return DEFAULT_ACCOUNT_CODE


def quote_currency_code(ticker: str) -> str | None:
    """The currency `ticker` is quoted in, as Yahoo reports it ('USD', 'EUR',
    'GBp'), or None. A known answer is remembered for the process; an
    unknown one is not, so a later lookup can still succeed."""
    key = str(ticker or "").upper().strip()
    if not key:
        return None
    if key in _quote_codes:
        return _quote_codes[key]
    try:
        with router.asker_scope(kinds.resolve_asker(Asker.ADMIN_PAGE)):
            code, answered = data._provider_currency_code(key)
    except Exception as exc:
        swallowed(log, "marketdata.fx.quote_code", exc, level=logging.DEBUG)
        return None
    if not answered or not code:
        return None
    _quote_codes[key] = str(code)
    return _quote_codes[key]
```

- [ ] **Step 4: Run them to see them pass**

Run Step 2's command. Expected: PASS, V194-6's tests included. Then
`python scripts/dev/testrun.py suite market-data` → green.

- [ ] **Step 5: Close**

Close: standard (test: `tests/marketdata/test_fx.py`), with this deviation: commit
`feat(v194): account and quote currency codes for the FX seam (V194-6a)`.

