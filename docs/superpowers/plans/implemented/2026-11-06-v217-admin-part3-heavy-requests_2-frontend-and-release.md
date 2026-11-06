# v217 — Admin Part 3: fewer heavy requests per page — Part 2: the two stores, release and the scan probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 2, § Error handling, § Testing, § Rollout and rollback; P3 authority [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Part 3 (P3-a, P3-b), § Testing, § Rollout and rollback.
**Index:** [`2026-11-06-v217-admin-part3-heavy-requests_0-index.md`](2026-11-06-v217-admin-part3-heavy-requests_0-index.md). Goal, architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below implicitly includes the Global Constraints.

All paths are relative to the worktree `.claude/worktrees/2026-11-06-v217-admin-part3-heavy-requests` (branch of the same name), written `<wt>` where a command needs the absolute path; `<main>` is the main checkout `E:/Documents/Private/Projects/Discord-Bot`. Never edit the main tree from V217-4 or V217-5. Commit inside the worktree only. V217-6 is the one task that merges into `main`.

**Server contracts this part consumes (written by Part 1, fixed in the ledger):**

- V217-2: every 200 `GET /api/v1/calendar/pnl/day` carries `prev_day` and `next_day`, each a `YYYY-MM-DD` string or JSON `null`, computed across all history under the request's `strategy`/`horizon` filter. A 404 body is `{"error": {"code": "not_found", "message": ...}}` and carries neither field.
- V217-3: `GET /api/v1/dashboard?mode=all` and `?mode=range&from=..&to=..` carry `today: {realized, lifecycle}`, each the same shape as the top-level field and equal to `?mode=today`'s. A day with no closes is a measured zero (`n: 0`, amounts `null`), never a missing block. Modes `active` and `today` never carry `today`.

In the SPA, `undefined` (field missing: an older backend after a rollback) means "fall back to the old request". `null` is a measured answer and is never fetched again.

# Phase C — The two stores

### Task V217-4: Calendar day store uses server neighbours, `loadEdge` only as fallback

**Model:** sonnet — one store method reshaped around a `forkJoin` ordering rule, with new and kept fallback specs; no cross-package design.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`CalendarDayTrades`, two optional fields after `fx_missing_count`)
- Modify: `frontend/src/app/stores/calendar-day.store.ts` (slice comment, new `landEdge` helper, `resolve`)
- Modify: `frontend/src/app/stores/calendar-day.store.spec.ts` (append one `describe` at the end of the file)

**Interfaces:**
- Consumes: V217-2's response keys `prev_day` / `next_day` on a 200 `GET /api/v1/calendar/pnl/day` (`YYYY-MM-DD` or `null`). The specs mock HTTP, so this task does not wait for V217-2 to merge. Existing: `adjacentTradingDay(days, date, step)` (`frontend/src/app/workspaces/calendar/day/month-context.ts:43`), `shiftMonth` (`frontend/src/app/stores/calendar.store.ts`), `loadEdge`, `prevEdge`/`nextEdge`, `routeRequest` (`frontend/src/app/routing/route-request.ts`; `next(value: T)` receives the `forkJoin` tuple).
- Produces: `CalendarDayTrades.prev_day?: string | null` and `CalendarDayTrades.next_day?: string | null` in `frontend/src/app/api/models.ts`. The store's public surface (`prevDay`, `nextDay`, `prevEdge`, `nextEdge`, `resolve`, `setRoute`, `setSort`) keeps its names and types. V217-5 edits the same `models.ts` (sequential edge, index § Parallelisation group C).

**The rules this task holds:**

1. `prevDay` / `nextDay` keep their computed: the month grid's neighbour first (`adjacentTradingDay(month.days, date, step)`), else `prevEdge` / `nextEdge`. A server neighbour only ever fills `prevEdge` / `nextEdge`, so a month-grid neighbour still wins, as today.
2. Per side: the day response's field is used when it is **not `undefined`**, `null` included. `undefined` (an older backend) runs today's `loadEdge` for that side only.
3. A 404 day (`notFoundAsNull` maps it to `day === null`) has no body to carry the fields, so both sides take `loadEdge`, unchanged.
4. `day$` and `month$` run in `forkJoin`, and either may answer first. The decision runs in `routeRequest`'s `next`, which fires once both have answered, never in a `tap`. A failed member fails the `forkJoin`, so no edge is decided. Today's month `tap` never ran on a failed month either.
5. Every async answer still checks `token === routeToken` before patching.

- [ ] **Step 1: Add the two optional fields to the model**

In `frontend/src/app/api/models.ts`, inside `export interface CalendarDayTrades`, directly after the `fx_missing_count?: number;` line, add:

```ts
  /** v217 (v205 P3-b): the nearest trading days before and after `date`
   *  under the same strategy/horizon filter, across all history. `null` is
   *  measured: no trading day on that side. Missing (`undefined`) only from
   *  a backend older than v217: the store then looks up the adjacent month
   *  itself. */
  prev_day?: string | null;
  next_day?: string | null;
```

- [ ] **Step 2: Write the failing specs**

Append at the end of `frontend/src/app/stores/calendar-day.store.spec.ts`. Every helper used is defined at the top of that file (`DAY_URL`, `MONTH_URL`, `SPARK_URL`, `cell`, `monthBody`, `AUGUST`, `trade`, `dayBody`), and every import is already there.

```ts
/* v217 V217-4 (v205 P3-b): the day route carries prev_day / next_day, so the
 * day page asks for no neighbouring month. The month lookup (`loadEdge`) is
 * kept only for a field the route did not send (an older backend) and for a
 * 404 day, whose body carries no fields. The existing edge specs above use
 * `dayBody()` without the fields and stay as the fallback path. */
describe('CalendarDayStore server neighbours (v217)', () => {
  let store: InstanceType<typeof CalendarDayStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        CalendarDayStore,
      ],
    });
    store = TestBed.inject(CalendarDayStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (date: string) => {
    store.setRoute(date, null, null);
    store.resolve().subscribe();
  };
  const dayReq = () => backend.expectOne((r) => r.url === DAY_URL);
  const monthReq = (month: string) =>
    backend.expectOne((r) => r.url === MONTH_URL && r.params.get('month') === month);
  const noMonth = (month: string) =>
    backend.expectNone((r) => r.url === MONTH_URL && r.params.get('month') === month);
  const withEdges = (prev: string | null, next: string | null): CalendarDayTrades =>
    ({ ...dayBody([trade()]), prev_day: prev, next_day: next });
  const NOT_FOUND = { error: { code: 'not_found', message: 'no closed trades' } };

  it('takes both neighbours from the day response and asks for no adjacent month', () => {
    open('2026-08-03');                                // first trading day of AUGUST
    dayReq().flush(withEdges('2026-07-28', '2026-08-05'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-05');
    noMonth('2026-07');
    noMonth('2026-09');
    backend.expectOne((r) => r.url === SPARK_URL);     // the day still gets its sparklines
    backend.verify();
  });

  it('finds a neighbour more than a month away from the server field alone', () => {
    open('2026-08-10');                                // last trading day of AUGUST
    dayReq().flush(withEdges('2026-08-05', '2026-11-02'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.nextDay()).toBe('2026-11-02');        // the one-month lookup would have said null
    expect(store.prevDay()).toBe('2026-08-05');
    noMonth('2026-09');
    noMonth('2026-07');
  });

  it('treats null at both ends as measured: no month lookup, no neighbour', () => {
    open('2026-08-05');
    dayReq().flush(withEdges(null, null));
    monthReq('2026-08').flush(monthBody('2026-08', [cell('2026-08-05', 30)]));
    expect(store.prevDay()).toBeNull();
    expect(store.nextDay()).toBeNull();
    expect(store.prevEdge()).toBeNull();
    expect(store.nextEdge()).toBeNull();
    noMonth('2026-07');
    noMonth('2026-09');
  });

  it('lets the month grid neighbour win over the server field, as before', () => {
    open('2026-08-05');
    dayReq().flush(withEdges('2026-07-01', '2026-09-30'));
    monthReq('2026-08').flush(AUGUST);
    expect(store.prevDay()).toBe('2026-08-03');
    expect(store.nextDay()).toBe('2026-08-10');
    noMonth('2026-07');
    noMonth('2026-09');
  });

  it('looks up the adjacent month only for the side the response did not send', () => {
    open('2026-08-10');
    dayReq().flush({ ...dayBody([trade()]), prev_day: '2026-08-05' });   // no next_day: older backend
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-09').flush(monthBody('2026-09', [cell('2026-09-02', 15)]));
    expect(store.nextDay()).toBe('2026-09-02');
    expect(store.prevDay()).toBe('2026-08-05');
    noMonth('2026-07');
  });

  it('decides after both answers when the month answers first: fields present, no lookup', () => {
    open('2026-08-03');
    monthReq('2026-08').flush(AUGUST);
    noMonth('2026-07');                                // nothing decided before the day answers
    dayReq().flush(withEdges('2026-07-28', '2026-08-05'));
    noMonth('2026-07');
    expect(store.prevDay()).toBe('2026-07-28');
  });

  it('decides after both answers when the month answers first: fields missing, one lookup', () => {
    open('2026-08-03');
    monthReq('2026-08').flush(AUGUST);
    noMonth('2026-07');
    dayReq().flush(dayBody([trade()]));                // no fields at all
    monthReq('2026-07').flush(monthBody('2026-07', [cell('2026-07-28', 10)]));
    expect(store.prevDay()).toBe('2026-07-28');
    noMonth('2026-09');
  });

  it('keeps the month lookup for a 404 day at a month edge', () => {
    open('2026-08-01');
    dayReq().flush(NOT_FOUND, { status: 404, statusText: 'Not Found' });
    monthReq('2026-08').flush(AUGUST);
    monthReq('2026-07').flush(monthBody('2026-07', [cell('2026-07-28', 10)]));
    expect(store.empty()).toBe(true);
    expect(store.prevDay()).toBe('2026-07-28');
    expect(store.nextDay()).toBe('2026-08-03');
    noMonth('2026-09');
  });

  it('decides nothing for a route the page has already left', () => {
    open('2026-08-03');
    const day = dayReq();
    const month = monthReq('2026-08');
    store.setRoute('2026-09-02', null, null);
    day.flush(dayBody([trade()]));                     // would have needed a July lookup
    month.flush(AUGUST);
    noMonth('2026-07');
    expect(store.prevEdge()).toBeNull();
  });
});
```

- [ ] **Step 3: Run the specs to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/calendar-day.store.spec.ts`
Expected: FAIL. "takes both neighbours…", "finds a neighbour more than a month away…" and "treats null at both ends…" fail with `Expected no matching requests` for the adjacent month (the month `tap` still runs `loadEdge`) or with a `null` neighbour. Both "decides after both answers…" cases fail at their first `noMonth('2026-07')`, because today the month `tap` looks up July before the day answers. The existing specs in the first `describe` still pass.

- [ ] **Step 4: Reshape the store**

In `frontend/src/app/stores/calendar-day.store.ts`:

(a) Replace the slice comment above `prevEdge` (the line `/** Nearest trading day in the adjacent month, looked up only at the edge. */`) with:

```ts
  /** Nearest trading day beyond this month's grid: the day route's
   *  `prev_day` / `next_day` (v217), or one adjacent-month lookup when the
   *  route did not send the field (older backend) or the day was a 404.
   *  The month grid's own neighbour still wins (`prevDay`/`nextDay`). */
```

(b) Directly after the `loadEdge` arrow function (it ends with `error: () => undefined,` / `});` / `};`), add:

```ts
    /** v217: one side's neighbour from the day route, decided once both the
     *  day and its month have answered. A field the route did not send
     *  (`undefined`: older backend, or a 404 day with no body) falls back to
     *  one adjacent-month lookup. `null` is a measured "no trading day on
     *  that side" and is never looked up. */
    const landEdge = (
      date: string, day: CalendarDayTrades | null, month: PnlCalendar,
      step: 1 | -1, token: number,
    ): void => {
      const served = step === 1 ? day?.next_day : day?.prev_day;
      if (served === undefined) {
        loadEdge(date, month, step, token);
        return;
      }
      patchState(store, step === 1 ? { nextEdge: served } : { prevEdge: served });
    };
```

(c) In `resolve`, replace the `month$` definition and the `routeRequest(...)` call (from `const month$ = ...` down to the `});` that closes `routeRequest`) with:

```ts
      const month$ = api.calendarPnl({ month: monthOf(date), ...filters() }).pipe(
        tap((month) => {
          if (token === routeToken) patchState(store, { month });
        }),
      );
      // The edges are decided here, once BOTH answered: `forkJoin` has no
      // defined order between its members' taps, and whether the month
      // lookup is needed depends on the day response.
      return routeRequest(forkJoin([day$, month$]), {
        start: () => patchState(store, { loading: true, error: null }),
        next: ([day, month]) => {
          if (token !== routeToken) return;
          patchState(store, { loading: false });
          landEdge(date, day, month, -1, token);
          landEdge(date, day, month, 1, token);
        },
        error: (error) => {
          if (token !== routeToken) return;
          patchState(store, {
            loading: false,
            empty: false,
            error: error.code === 'unavailable' ? UNAVAILABLE : error.message,
          });
        },
      });
```

`day$` is unchanged. `CalendarDayTrades` and `PnlCalendar` are already imported at the top of the file.

- [ ] **Step 5: Run the specs to see them pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/calendar-day.store.spec.ts`
Expected: PASS, every case in both `describe` blocks. The old edge specs ("looks one month back…", "looks one month ahead…", "treats a 404 day as the empty state…") still pass: their `dayBody()` sends no fields, so they now exercise the fallback.

- [ ] **Step 6: Check the page specs that sit on this store**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/calendar/day/calendar-day.spec.ts`
Expected: PASS. They mock the day response without the new fields, so they take the fallback path, which is today's behaviour. No template or style changed, so the page renders the same at mobile, tablet and desktop (index § Global Constraints).

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git -C "<wt>" add frontend/src/app/api/models.ts
git -C "<wt>" commit -m "feat(ui): CalendarDayTrades carries optional prev_day / next_day (v217 V217-4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "<wt>" add frontend/src/app/stores/calendar-day.store.ts frontend/src/app/stores/calendar-day.store.spec.ts
git -C "<wt>" commit -m "feat(ui): calendar day takes its neighbours from the day route, month lookup only as fallback (v217 V217-4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V217-5: Dashboard store lands `today` from the scoped response

**Model:** opus — a two-road stamp/race rule in a signal store, with existing race specs to rewrite without losing what they pin.

**Split:** this task passed the 20 KB cap, so its extra pinning specs are task V217-5b (`SPLIT: V217-5 -> V217-5b`). This task leaves every spec green on its own.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`Dashboard.today?`, new `DashboardToday` directly after `Dashboard`)
- Modify: `frontend/src/app/stores/dashboard.store.ts` (slice type and comment, `lifecycleOf` parameter, `landToday` parameter, today roads, `resolve`/`refetch`/`load`/`select`)
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts` (v181 helper comment; rewrite and add cases in `describe("today's figures and the chart's Latest button")`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (`todayFailedInPeriod` fails the fallback today request too). **Not in the index ledger's file list for this task**: found while writing it. Without it, that helper leaves the fallback request open and "says today's figures could not load…" fails. V217-1 appends to the same file, so V217-5 runs after V217-1 (the index's suggested waves already order them).

**Interfaces:**
- Consumes: V217-3's response key `today` = `{realized, lifecycle}` on `/dashboard` modes `all`/`range` (the specs mock HTTP, so no wait on V217-3's merge); V217-4 has already edited `models.ts` (sequential edge). Existing: `landToday`, `failToday`, `loadToday`, `todayIssued`/`todayLanded`, `scopeToRequest` (`frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts:348`, maps 1D→`today`, All→`all`, other presets and a Range→`range`).
- Produces: `export interface DashboardToday { realized: Dashboard['realized']; lifecycle: Dashboard['lifecycle']; }` and `Dashboard.today?: DashboardToday` in `models.ts`; store slice `todayData: DashboardToday | null`. Public `todayRealized`, `todayLifecycle`, `todayLoading`, `todayError`, `resolve`, `load`, `setPreset`, `setRange`, `resetView`, `setScope` keep their names and types. No reader outside the store touches `todayData` (`git grep -n todayData -- frontend/src` lists only `dashboard.store.ts`).

**The rules this task holds:**

1. **1D** is unchanged: one `mode=today` request, its response is today's figures, stamped like a today fetch.
2. **Wider scope** (`all`/`range`): one request. Its `today` block lands through `landToday` under a stamp taken **when the request is issued** (`++todayIssued`), so a today fetch issued earlier can never overwrite it.
3. **Block missing** (`undefined`, an older backend): fall back to `loadToday()` **only where today was owed before v217**. On `load()` (first load, event refresh) it is always owed. On a selection change (`select`) it is owed only while `todayData()` is still `null`. That keeps "keeps today … when a wider preset is picked after a 1D load", and the component spec's "Realised today" card does not ring on a preset click.
4. `todayLoading` is set at issue only where today is owed, and clears when the block lands, the fallback answers, or the request fails or is cancelled while it holds the newest stamp.
5. A failed wider request with today owed is a failed today answer (`failToday`). It sends no fallback, because the box just failed.
6. A zero-close block (`n: 0`, amounts `null`) lands as a measured zero, never a fetch.

- [ ] **Step 1: Model**

In `frontend/src/app/api/models.ts`, inside `export interface Dashboard`, directly after the `default_expiry_bars: number;` line, add:

```ts
  /** v217 (v205 P3-a): today's figures inside a wider-scope response (modes
   *  `all` and `range` only), so the SPA needs no second `mode=today` call.
   *  Missing on modes `active`/`today` and on a backend older than v217. */
  today?: DashboardToday;
```

Directly after the closing `}` of `interface Dashboard` (before `export type DashboardScope`), add:

```ts
/** v217: `Dashboard.today` -- the same two blocks `GET /dashboard?mode=today`
 *  answers, computed from the same trades. A day with no closes is a
 *  measured zero (`n: 0`, amounts null), never a missing block. */
export interface DashboardToday {
  realized: Dashboard['realized'];
  lifecycle: Dashboard['lifecycle'];
}
```

- [ ] **Step 2: Rewrite the always-fetch-today specs (they must fail first)**

In `frontend/src/app/stores/dashboard.store.spec.ts`:

(a) In `describe('the v181 scope selection')`, replace the two comment lines above `const scoped = ...` (starting `// The today-only fetch (mode=today, the Realised today card)`) with:

```ts
    // The today-only fetch (mode=today, the Realised today card) is, since v217, only a fallback
    // after a wider answer without a `today` block; its own describe below covers it. These
    // helpers see the scoped requests only.
```

The `scoped` filter itself stays: it still hides that fallback request.

(b) In `describe("today's figures and the chart's Latest button")`, replace the `flushScoped` helper with one that can carry a block, and add `FRESH`, `closed` and `block` beside `TODAY`/`SCOPED`:

```ts
    const FRESH = { amount: 30, pct: 1, n: 3, wins: 2, losses: 1 };
    const closed = (rows: { status: string; count: number }[]) => rows.find((row) => row.status === 'CLOSED')?.count;
    const block = (realized: Dashboard['realized'], closedToday = 3) =>
      ({ today: { realized, lifecycle: { ...RESPONSE.lifecycle, CLOSED: closedToday } } });
    const flushScoped = (reqs: ReturnType<typeof requests>, extra: Partial<Dashboard> = {}) => {
      reqs.filter((r) => modeOf(r) !== 'today')
        .forEach((r) => r.flush({ ...RESPONSE, scope: { mode: 'range' }, realized: SCOPED, ...extra }));
    };
```

(c) In "keeps today, fetching nothing extra, when a wider preset is picked after a 1D load", append after its last `expect`:

```ts
      expect(requests()).toHaveLength(0);                // no block, but today was not owed
      expect(store.todayLoading()).toBe(false);
```

(d) Replace the whole case "fetches today beside the scoped figures when the scope is wider" with:

```ts
    it('lands today from the wider response: one request, no today fetch', () => {
      const reqs = widenThenPush();
      expect(reqs.map(modeOf)).toEqual(['range']);
      expect(store.todayLoading()).toBe(true);
      flushScoped(reqs, block(FRESH, 5));
      expect(store.todayLoading()).toBe(false);
      expect(store.todayRealized()).toEqual(FRESH);
      expect(closed(store.todayLifecycle())).toBe(5);
      expect(store.realized()).toEqual(SCOPED);
      expect(requests()).toHaveLength(0);
    });

    it('falls back to the today request when the wider response has no block (older backend)', () => {
      const reqs = widenThenPush();
      expect(reqs.map(modeOf)).toEqual(['range']);
      flushScoped(reqs);
      expect(store.todayLoading()).toBe(true);
      const fallback = requests();
      expect(fallback.map(modeOf)).toEqual(['today']);
      flushToday(fallback, FRESH);
      expect(store.todayLoading()).toBe(false);
      expect(store.todayRealized()).toEqual(FRESH);
      expect(store.realized()).toEqual(SCOPED);
    });
```

(e) Replace the whole case "keeps the previous today figures and stops loading when the today fetch fails" with:

```ts
    it('keeps the previous today figures and stops loading when the fallback today fetch fails', () => {
      flushScoped(widenThenPush());
      requests().filter((r) => modeOf(r) === 'today')
        .forEach((r) => r.flush('boom', { status: 500, statusText: 'Server Error' }));
      expect(store.todayLoading()).toBe(false);
      expect(store.todayRealized()).toEqual(TODAY);
    });
```

(f) In "keeps today's lifecycle counts while a wider scope's counts differ", delete its local `const closed = ...` line (the describe-level `closed` from (b) replaces it).

(g) Replace the whole case "keeps the newest today answer when an older one lands after it" with:

```ts
    it('keeps the newest today answer when an older fallback lands after it', () => {
      flushScoped(widenThenPush());                      // no block: fallback 1 goes out
      const older = requests();
      expect(older.map(modeOf)).toEqual(['today']);
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      flushScoped(requests());                           // no block again: fallback 2
      const newer = requests();
      expect(newer.map(modeOf)).toEqual(['today']);
      const newerFigures = { amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 };
      flushToday(newer, newerFigures);
      flushToday(older, FRESH);
      expect(store.todayRealized()).toEqual(newerFigures);
      expect(store.todayLoading()).toBe(false);
    });
```

(h) Replace the body of "reports a failed today fetch instead of loading forever" with:

```ts
      tick();
      const [first] = requests();
      store.setPreset('1M');                             // before any today answer: today owed
      fail(first);
      flushScoped(requests());                           // no block: the fallback goes out now
      const fallback = requests();
      expect(fallback.map(modeOf)).toEqual(['today']);
      fallback.forEach(fail);
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).not.toBeNull();
      expect(store.todayLifecycle()).toEqual([]);
      expect(store.realized()).toEqual(SCOPED);
```

(i) Replace the body of "clears the today error once a today answer lands" with:

```ts
      flushScoped(widenThenPush());
      requests().filter((r) => modeOf(r) === 'today').forEach(fail);
      expect(store.todayError()).not.toBeNull();
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      flushScoped(requests(), block(TODAY));             // a block clears it like a fetch would
      expect(store.todayError()).toBeNull();
      expect(store.todayLoading()).toBe(false);
      expect(requests()).toHaveLength(0);
```

V217-5b adds the remaining pinning cases (a zero-close block, an All pick, a failed or cancelled wider request, an older fetch against a newer block) to this describe. Every other case in the file stays as written ("is the scoped block itself under 1D…", "opens on 1D on every visit…", the resetView cases, "lands a 1D answer as today's figures even after a wider pick superseded it", the cancel cases).

(j) In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, inside `async function todayFailedInPeriod()`, directly after the `for (const req of backend.match((r) => r.url === '/api/v1/dashboard')) { ... }` loop, add:

```ts
    // v217: the 1M answer has no `today` block (an older backend) and no today
    // answer has landed, so the store falls back to a today request: it fails too.
    for (const req of backend.match('/api/v1/dashboard?mode=today')) fail(req);
```

- [ ] **Step 3: Run the specs to see them fail**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/dashboard.store.spec.ts`
Expected: FAIL. "lands today from the wider response…" sees `['range', 'today']`, "falls back to the today request…" sees two requests up front, and the rewritten race cases fail on `toEqual(['today'])`.

- [ ] **Step 4: Implement in the store**

In `frontend/src/app/stores/dashboard.store.ts`:

(a) Import: change `import { Dashboard, DashboardScope } from '../api/models';` to `import { Dashboard, DashboardScope, DashboardToday } from '../api/models';`.

(b) In `interface DashboardSlice`, replace the `todayData` comment and line with:

```ts
  /** Today's realised block and lifecycle counts, kept beside the scoped
   *  response: the Realised today card and the Open positions tabs read
   *  today in every mode. Under 1D it is the scoped response itself; under
   *  a wider scope it is that response's `today` block (v217), or a
   *  today-only fetch's answer when the block is missing (older backend).
   *  Null until one lands. */
  todayData: DashboardToday | null;
```

(c) Replace the line `const isDay = (selection: ScopeSelection): boolean => isPreset(selection, '1D');` (used only by the old `load`/`select`, so it would be an unused local) with:

```ts
/** Whether a wider answer without a `today` block (older backend) sends the
 *  today-only fetch: always on a load, only while nothing landed on a pick. */
type TodayFallback = 'always' | 'when-empty';

/** How one scoped request serves today's figures. */
interface TodayRoad {
  next(data: Dashboard): void;
  error(error: ApiError): void;
  cancel(): void;
}
```

(d) Change `function lifecycleOf(data: Dashboard | null)` to `function lifecycleOf(data: Pick<Dashboard, 'lifecycle'> | null)`. The body stays.

(e) Change `const landToday = (stamp: number, data: Dashboard): void => {` to `const landToday = (stamp: number, data: DashboardToday): void => {`. The body stays.

(f) Replace everything from the comment `// \`defer\`: the request number and the window are taken when the route` through the end of `const select = ...;` (the old `resolve`, `refetch`, `loadToday`, `load`, `select`) with:

```ts
    /** Today's response alone: the fallback when a wider answer carries no
     *  `today` block. A failure keeps the previous figures and says so. */
    const loadToday = (): void => {
      const stamp = ++todayIssued;
      patchState(store, { todayLoading: true });
      api.dashboard('today').subscribe({
        next: (data) => landToday(stamp, data),
        error: (error: ApiError) => failToday(stamp, error),
      });
    };

    /** Under 1D the scoped response is today's: stamped like a today fetch. */
    const dayRoad = (): TodayRoad => {
      const stamp = ++todayIssued;
      return {
        next: (data) => landToday(stamp, data),
        error: (error) => failToday(stamp, error),
        cancel: () => {
          if (stamp === todayIssued) patchState(store, { todayLoading: false });
        },
      };
    };

    /** v217 (v205 P3-a): a wider answer carries today's figures as its
     *  `today` block, so no second request goes out. The stamp is taken at
     *  issue: a today fetch issued earlier never lands on top of the block.
     *  Without a block (older backend) the today-only fetch follows, but
     *  only where today was owed before v217 (see `TodayFallback`). */
    const widerRoad = (fallback: TodayFallback): TodayRoad => {
      const owed = fallback === 'always' || untracked(() => store.todayData()) === null;
      const stamp = ++todayIssued;
      if (owed) patchState(store, { todayLoading: true });
      const settle = (): void => {
        if (stamp === todayIssued) patchState(store, { todayLoading: false });
      };
      return {
        next: (data) => {
          if (data.today !== undefined) landToday(stamp, data.today);
          else if (owed) loadToday();
          else settle();
        },
        error: (error) => {
          if (owed) failToday(stamp, error);
          else settle();
        },
        cancel: settle,
      };
    };

    // `defer`: the request number and the window are taken when a method
    // subscribes. `untracked`: `load()` runs inside the onInit effect, and a
    // tracked read would refetch on every selection change on top of the
    // method's own refetch.
    const resolveScoped = (fallback: TodayFallback): Observable<void> => defer(() => {
      const request = ++latestRequest;
      const current = (): boolean => request === latestRequest;
      const { mode, window } = scopeToRequest(untracked(() => store.selection()), new Date());
      const today = mode === 'today' ? dayRoad() : widerRoad(fallback);
      let settled = false;
      return routeRequest(api.dashboard(mode, window), {
        start: () => patchState(store, { loading: true }),
        next: (data) => {
          settled = true;
          today.next(data);
          if (current()) patchState(store, { data, loading: false, error: null, stale: false });
        },
        error: (error) => {
          settled = true;
          today.error(error);
          if (current()) patchState(store, failure(untracked(() => store.data()) !== null, error));
        },
      }).pipe(finalize(() => {
        if (settled || !current()) return;
        patchState(store, unfinished(untracked(() => store.data()) !== null));
        today.cancel();
      }));
    });

    /** Public: a full load's rules (today owed). */
    const resolve = (): Observable<void> => resolveScoped('always');

    const refetch = (fallback: TodayFallback): void => {
      resolveScoped(fallback).subscribe({ error: () => undefined });
    };

    /** First load and every event refresh. One request in every scope. */
    const load = (): void => refetch('always');

    const select = (selection: ScopeSelection): void => {
      patchState(store, { selection });
      refetch('when-empty');
    };
```

Check nothing else names `isDay`: `git grep -n "isDay" -- frontend/src/app/stores/dashboard.store.ts` prints nothing.

- [ ] **Step 5: Run the store and component specs to see them pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts`
Expected: PASS, every case. In `dashboard.spec.ts`, "switches to Period on a wider preset: Realised today stays today…" still finds "Realised today" not loading (today not owed after a 1D load), and both `todayFailedInPeriod` cases pass with the added fallback failure.

- [ ] **Step 6: Check the panels that read today's figures**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts`
Expected: PASS. No template or style changed, so the Dashboard renders the same at mobile, tablet and desktop.

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git -C "<wt>" add frontend/src/app/api/models.ts
git -C "<wt>" commit -m "feat(ui): Dashboard carries an optional today block, DashboardToday (v217 V217-5)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "<wt>" add frontend/src/app/stores/dashboard.store.ts frontend/src/app/stores/dashboard.store.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git -C "<wt>" commit -m "feat(ui): a wider Dashboard scope lands today from its own response, today fetch only as fallback (v217 V217-5)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V217-5b: Dashboard store today block: the remaining pinning specs

**Model:** sonnet — spec-only additions that pin rules V217-5 already implements, reusing its helpers; no production code.

Split from V217-5 at the 20 KB cap (`SPLIT: V217-5 -> V217-5b`). The controller adds the ledger row below V217-5. Same files as V217-5's spec side. No production code changes here: these cases pin V217-5's rules 2, 4, 5 and 6 and the `all` mode, and they pass against V217-5's store. **If one fails, the store is wrong, not the spec:** fix `frontend/src/app/stores/dashboard.store.ts` within V217-5's rules (or report `BLOCKED` with the assertion), never loosen the case.

**Files:**
- Modify: `frontend/src/app/stores/dashboard.store.spec.ts` (four `it` blocks inside `describe("today's figures and the chart's Latest button")`)

**Interfaces:**
- Consumes: V217-5's store (`resolveScoped`/`widerRoad`/`dayRoad` behind the public `resolve`, `load`, `setPreset`) and its spec helpers in that describe: `FRESH`, `closed(rows)`, `block(realized, closedToday = 3)`, `flushScoped(reqs, extra = {})`, `flushToday(reqs, realized = TODAY)`, `widenThenPush()`, `requests()`, `modeOf(req)`, plus `TODAY`, `RESPONSE`, `events`, `tick`, `vi`.
- Produces: nothing for a later task.

- [ ] **Step 1: Add the zero-block and All cases**

In `frontend/src/app/stores/dashboard.store.spec.ts`, directly after the case "lands today from the wider response: one request, no today fetch" (added by V217-5), insert:

```ts
    it('lands a zero-close today block as a measured zero, with no fetch', () => {
      const zero = { amount: null, pct: null, n: 0, wins: 0, losses: 0 };
      flushScoped(widenThenPush(), block(zero, 0));
      expect(store.todayRealized()).toEqual(zero);
      expect(closed(store.todayLifecycle())).toBe(0);
      expect(store.todayLoading()).toBe(false);
      expect(requests()).toHaveLength(0);
    });

    it('lands the block of an All pick after 1D, one request', () => {
      tick();
      requests()[0].flush({ ...RESPONSE, realized: TODAY });
      store.setPreset('All');
      const reqs = requests();
      expect(reqs.map(modeOf)).toEqual(['all']);
      flushScoped(reqs, block(FRESH));
      expect(store.todayRealized()).toEqual(FRESH);
      expect(requests()).toHaveLength(0);
    });
```

The zero case is the measured-zeros rule (`docs/claude/known-traps.md`): a day with no closes arrives as a block with `n: 0` and `null` amounts. It must land as such, because absence (`undefined`) is the only signal that sends a fetch.

- [ ] **Step 2: Add the failed and cancelled wider request cases**

Directly after the case "keeps the previous today figures and stops loading when the fallback today fetch fails" (added by V217-5), insert:

```ts
    it('keeps the previous today figures, sending no fallback, when the wider request fails', () => {
      const [scopedReq] = widenThenPush();
      scopedReq.flush('boom', { status: 500, statusText: 'Server Error' });
      expect(store.todayLoading()).toBe(false);
      expect(store.todayError()).not.toBeNull();
      expect(store.todayRealized()).toEqual(TODAY);
      expect(requests()).toHaveLength(0);
    });

    it('stops today loading when a wider request is cancelled before it answered', () => {
      tick();
      requests()[0].flush({ ...RESPONSE, realized: TODAY });
      store.setPreset('1M');
      flushScoped(requests());
      const subscription = store.resolve().subscribe();  // a full load's rules: today owed
      expect(store.todayLoading()).toBe(true);
      subscription.unsubscribe();
      expect(store.todayLoading()).toBe(false);
    });
```

- [ ] **Step 3: Add the older-fetch-against-a-newer-block case**

Directly after the case "keeps the newest today answer when an older fallback lands after it" (added by V217-5), insert:

```ts
    it('never lets an older today fetch overwrite a newer block', () => {
      flushScoped(widenThenPush());                      // no block: a fallback goes out, left in flight
      const older = requests();
      expect(older.map(modeOf)).toEqual(['today']);
      events.raise('trades');
      tick();
      vi.advanceTimersByTime(300);
      const newerFigures = { amount: 45, pct: 1.5, n: 4, wins: 3, losses: 1 };
      flushScoped(requests(), block(newerFigures));      // the newer wider answer carries the block
      expect(store.todayRealized()).toEqual(newerFigures);
      flushToday(older, FRESH);                          // the older fetch answers last
      expect(store.todayRealized()).toEqual(newerFigures);
      expect(store.todayLoading()).toBe(false);
    });
```

Why it holds: the newer wider request took its stamp when it was issued, after the fallback's stamp, so `landToday` drops the fallback's answer (`stamp < todayLanded`).

- [ ] **Step 4: Run the spec file**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/dashboard.store.spec.ts`
Expected: PASS, every case, the four new ones included. There is no red step: the behaviour shipped in V217-5. A failure is a store bug (see the rule above the steps).

- [ ] **Step 5: Commit**

```bash
git -C "<wt>" add frontend/src/app/stores/dashboard.store.spec.ts
git -C "<wt>" commit -m "test(ui): pin the today block's measured zero, All mode, failed/cancelled wider requests and stamp order (v217 V217-5b)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase D — Release and measure

### Task V217-6: Release, deploy, probe during a scan, Results

**Model:** sonnet — a scripted release, a gated merge and a measurement run with read-only production checks; every figure is generated, none judged.

**Files:**
- Modify: `VERSION.json` (ui patch, bot patch; index header `Bump: ui patch, bot patch`)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 2 after (committed probe)`, below V217-1's `### Plan 2 boot merge (V217-1)`)

**Interfaces:**
- Consumes: every task V217-1..V217-5b committed on the worktree branch, including V217-1's spec heading `### Plan 2 boot merge (V217-1)`; the probe CLI `scripts/ops/admin_browser_probe.py` (`--date --out [--image-tag]`), its `probe.json` shape `{"raw": {meta, pages[{round, route, calls[{url, ttfb_ms, start_s}], scan_running, ...}], idle}, "report": {meta, label, goal, rounds, endpoints, pages, idle}}`, and `normalise_endpoint(url)` from the same script. Page routes are recorded formatted (`trades/calendar/2026-11-03`).
- Produces: the deployed release and the table the spec's Plan 2 result rests on.

**Gates (in this order, none skipped):**

1. **Partner approval before anything reaches `main`.** A push to `main` deploys to production by itself (CI → Hetzner, `docs/deploy/DEPLOY_HETZNER.md`). So the merge and the push wait for the partner's explicit yes in Step 5, asked through `AskUserQuestion`. No yes, no merge and no push. The branch stays as it is, and the task stops there.
2. **`mirror-prod` rules.** The deploy is the CI pipeline. Nothing is changed by hand on the VM. Production is touched read-only, only through `bash scripts/ops/ssh-hetzner.sh` (standing permission for read-only checks). If anything on the VM ever has to change by hand (a restart, an `.env` edit, a hotfix), stop, invoke the `mirror-prod` skill, and mirror the change into the repo and commit it before this task counts as done.
3. **A probe run counts only with label `scan`**, and only when the credentials are absent from its output (Step 11).

No full-suite run: CI runs it after the push (Step 7).

- [ ] **Step 1: Check the preconditions**

```bash
git -C "<wt>" log --oneline main..HEAD
grep -n "^### Plan 2 boot merge (V217-1)" "<wt>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md"
git -C "<wt>" status --short
```

Expected: commits for V217-1, 2, 3, 4, 5 and 5b; the heading found; a clean status. **No heading: stop.** V217-1 has not landed.

- [ ] **Step 2: Narrow verification of everything this plan touched**

The `admin` and `admin-perf` tests reach Postgres: run `/replicate-prod-db` first if no task in this session has (shared `swing-db`, port 56789). Then, one file at a time (never the full suite):

```bash
cd "<wt>" && for t in tests/analytics/test_pnl_calendar.py tests/admin/test_api_v1_calendar.py tests/admin/test_api_v1_dashboard.py tests/admin_perf/test_today_block.py tests/admin_perf/test_golden_endpoints.py tests/admin_perf/test_budgets.py; do python scripts/dev/testrun.py file "$t" > "<wt>/.superpowers/v217-$(basename "$t" .py).log" 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
cd "<wt>" && python scripts/dev/complexity_gate.py > "<wt>/.superpowers/v217-complexity.log" 2>&1 && echo "PASS complexity" || echo "FAIL complexity"
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/calendar-day.store.spec.ts --include src/app/workspaces/calendar/day/calendar-day.spec.ts --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/exposure-by-horizon.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts > "<wt>/.superpowers/v217-ng.log" 2>&1 && echo "PASS ng" || echo "FAIL ng"
```

Expected: six `PASS` test lines, `PASS complexity`, `PASS ng`. A `FAIL`: read only that log's failing test names and assertion lines, fix, and rerun that one file alone.

- [ ] **Step 3: Bump `ui` and `bot` as two release commits**

`VERSION.json` is checked out with CRLF line endings: the script keeps whatever the file has. Read the current values, never assume them:

```bash
python - "<wt>/VERSION.json" ui <<'EOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, line = Path(sys.argv[1]), sys.argv[2]
raw = path.read_bytes()
nl = "\r\n" if b"\r\n" in raw else "\n"
data = json.loads(raw.decode("utf-8"))
major, minor, patch = (int(x) for x in data[line].split("."))
data[line] = f"{major}.{minor}.{patch + 1}"
data[f"{line}_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_bytes((json.dumps(data, indent=2).replace("\n", nl) + nl).encode("utf-8"))
print(line, data[line])
EOF
git -C "<wt>" diff --stat VERSION.json
```

Expected: `ui <x.y.z+1>`, and the diff touches 2 lines. If it shows the whole file, the line endings or indent differ: restore with `git -C "<wt>" checkout VERSION.json` and match the original format. Commit:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(ui): <new ui> -- the Dashboard lands today from its scoped answer, the day page takes its neighbours from the server (v217)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run the same script with `bot` instead of `ui`, then:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(bot): <new bot> -- /dashboard carries today for all/range, /calendar/pnl/day carries prev_day/next_day (v217)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Regenerate the version history and check it**

The generator walks `git log` for `VERSION.json`, so it runs **after** both release commits:

```bash
cd "<wt>" && python scripts/dev/build_version_matrix.py
cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C "<wt>" add swingbot/admin/version_history.json
git -C "<wt>" commit -m "chore(ui,bot): <new ui> / <new bot> -- fewer heavy requests per page (v217)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: the test passes. `git -C "<wt>" show --stat HEAD` lists only `swingbot/admin/version_history.json`, and its newest pair is the two new versions, never `"commit": "uncommitted"`.

- [ ] **Step 5: Deploy gate: ask the partner**

Ask through `AskUserQuestion`, one question, recommended option first:

- Question: "v217 is released on its branch (ui <new ui>, bot <new bot>; narrow tests green). Merging into `main` and pushing deploys it to production through CI. Deploy now?"
- Options: "Merge and deploy now (Recommended)" / "Not yet: leave the branch unmerged".

"Not yet": stop here and report the branch head and the two versions. Do not merge, push or probe. Any other answer is not a yes: ask again or stop.

- [ ] **Step 6: Merge into `main` and push (only after the yes)**

Invoke the `worktree-lifecycle` skill for the merge, because another session may be committing on `main`. Then:

```bash
git -C "<main>" fetch origin
git -C "<main>" status --short --branch
git -C "<main>" log --oneline -1 origin/main
```

Expected: `main` is not behind `origin/main` (pull with `--ff-only` first if it is), and no uncommitted change in `<main>` touches a file this plan changed. Uncommitted files of another session stay as they are. Never stash or reset them.

```bash
git -C "<main>" merge --no-ff 2026-11-06-v217-admin-part3-heavy-requests -m "merge: v217 -- admin Part 3: today rides the scoped /dashboard, the day route carries its neighbours, boot /trades calls stay two"
git -C "<main>" push origin main
```

- [ ] **Step 7: Watch the pipeline**

```bash
gh run list --branch main --limit 1 --json databaseId,status,conclusion
```

Then run `gh run watch <id> --exit-status` with `run_in_background` and wait for its exit notification (do not poll). Green: continue. Red: `gh run view <id> --log-failed > <scratchpad>/v217-ci.log`, read only the failing test names and assertion lines, fix each in `<main>` (one file at a time with `testrun.py file`), commit scoped, push, watch again (`working-conventions.md` § Pipeline watch). Each fix push deploys too, and the Step 5 yes covers fixes to this release only.

- [ ] **Step 8: Confirm production runs the new code (read-only)**

The deploy follows a green run by itself. Write `<scratchpad>/v217_check.py`:

```python
from swingbot.admin.api_v1 import dashboard
from swingbot.core.analytics import pnl_calendar

print("today_block:", hasattr(dashboard, "_today_block"),
      "| adjacent_trading_days:", hasattr(pnl_calendar, "adjacent_trading_days"))
```

Then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps --format '{{.Image}}' admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" < "<scratchpad>/v217_check.py"
```

Expected: an image reference (keep it as `<tag>`) and `today_block: True | adjacent_trading_days: True`. A `False` means the deploy has not landed: wait a few minutes and repeat. Never probe the old image.

- [ ] **Step 9: Wait for a scan, then confirm it**

The session scan runs in US hours (15:30–22:00 Berlin). Git Bash has no timezone data, so Berlin is `date -u` plus 1 h in winter.

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.core.scanning.runstate import is_scan_running; print(is_scan_running())'"
```

Expected: `True`. On `False`, check again every few minutes. Never start the run on `False`.

- [ ] **Step 10: Run the probe in the background**

The output goes under `<main>` so it survives `/close-out` removing the worktree (`.superpowers/` is git-ignored). The run takes about an hour: start it with `run_in_background` and wait for the exit notification.

```bash
python "<main>/scripts/ops/admin_browser_probe.py" --date 2026-11-03 --out "<main>/.superpowers/probe/v217-after" --image-tag "<tag>" > "<main>/.superpowers/probe/v217-after.log" 2>&1
```

Expected: exit 0 and the last log line `probe: scan run, 36 pages -> ...`. Exit 2 is a failed login (the log names the HTTP status only): fix the cause and rerun from Step 9.

- [ ] **Step 11: Verify the run: label, shape, no credential**

The same check as v206 V206-3 Step 5: the two `.env` values are read inside the script and only a boolean is printed.

```bash
python - "<main>/.superpowers/probe/v217-after" "<main>/.env" <<'EOF'
import json, re, sys
from pathlib import Path
out, env = Path(sys.argv[1]), Path(sys.argv[2])
pattern = re.compile(r"\s*(?:export\s+)?(ADMIN_USERNAME|ADMIN_PASSWORD)\s*=\s*(.*?)\s*$")
values = [m.group(2).strip('"').strip("'") for m in map(pattern.match, env.read_text(encoding="utf-8").splitlines()) if m]
texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8")]
print("credentials absent:", len(values) == 2 and all(v not in t for v in values for t in texts))
report = json.loads(texts[0])["report"]
print("label:", report["label"], "| pages:", len(report["pages"]), "| idle rpm:", report["idle"]["rpm"])
assert report["label"] == "scan", "not a scan run: keep it as not-evidence, rerun from Step 9 during a scan"
assert len(report["pages"]) == 36
EOF
```

Expected: `credentials absent: True`, `label: scan | pages: 36 | idle rpm: <n>`, no assertion error. `credentials absent: False`: delete the run directory and its log at once, tell the partner, and do not record the run. A `mixed` or `quiet` run: rename its directory to `v217-after-<label>-1`, keep it for Step 13's "Not evidence" line, and rerun from Step 9.

- [ ] **Step 12: Generate the table from the runs**

No figure is retyped. The reference is v206 Plan 1's `scan` after-run, if one exists. The script looks for it in the two places V206-13 could have left it and uses it only if its label is `scan`. With no such run the table has one column, and Step 13 says so.

```bash
python - "<main>/.superpowers/probe/v217-after" "<main>/scripts/ops" "<main>/.superpowers/probe/v206-after" "<main>/.claude/worktrees/2026-11-05-v206-admin-under-load/.superpowers/probe/v206-after" > "<main>/.superpowers/probe/v217-compare.md" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
import admin_browser_probe as probe

def load(d):
    f = Path(d) / "probe.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

after = load(sys.argv[1])
ref = next((doc for doc in map(load, sys.argv[3:]) if doc and doc["report"]["label"] == "scan"), None)
DAY_ROUTE = "trades/calendar/2026-11-03"
WATCHED = ("/dashboard", "/calendar/pnl", "/calendar/pnl/day", "/trades")

def per_visit(raw, route, endpoint):
    visits = [p for p in raw["pages"] if p["route"] == route]
    n = sum(1 for p in visits for c in p["calls"] if probe.normalise_endpoint(c["url"]) == endpoint)
    return round(n / len(visits), 2) if visits else "-"

def fmt(s):
    tail = f"max {s['max']} (thin)" if s["thin"] else f"p90 {s['p90']}, max {s['max']}"
    return f"n {s['n']}, median {s['median']}, {tail}"

def spread(rows, endpoint):
    s = next((r for r in rows if r["endpoint"] == endpoint), None)
    return "-" if s is None else fmt(s)

def rows(doc):
    report, raw = doc["report"], doc["raw"]
    out = {"Label": report["label"], "Idle tab, requests per minute": report["goal"]["idle_rpm"],
           "First heavy call per page (ms)": fmt(report["goal"]["first_heavy_ms"]),
           "Endpoints over 5 s": ", ".join(report["goal"]["endpoints_over_5s"]) or "none"}
    for route in ("dashboard", DAY_ROUTE):
        for name in WATCHED:
            out[f"`{name}` calls per `{route}` visit"] = per_visit(raw, route, name)
    for name in ("/dashboard", "/calendar/pnl/day", "/calendar/pnl"):
        out[f"`{name}` TTFB (ms)"] = spread(report["endpoints"], name)
    return out

a = rows(after)
if ref is None:
    print("| Measure | v217 after |")
    print("|---|---|")
    for key, value in a.items():
        print(f"| {key} | {value} |")
else:
    r = rows(ref)
    print("| Measure | v206 Plan 1 after | v217 after |")
    print("|---|---|---|")
    for key, value in a.items():
        print(f"| {key} | {r.get(key, '-')} | {value} |")
print()
print("reference:", "v206-after (scan)" if ref else "none found")
EOF
cat "<main>/.superpowers/probe/v217-compare.md"
```

Expected: a markdown table of about 15 rows, label `scan` in the v217 column, and a last line naming the reference. A `KeyError` means the report shape differs from the probe's contract: fix the script to read the field that exists, never edit `probe.json`.

- [ ] **Step 13: Record the result in the spec**

In `<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`, append at the end of `## Results` (the end of the file), below `### Plan 2 boot merge (V217-1)` and any section added after it:

```markdown
### Plan 2 after (committed probe)

After plan v217 deployed (ui <new ui>, bot <new bot>), with
`scripts/ops/admin_browser_probe.py` at `<probe_sha>`, against image `<tag>`,
`<berlin_time>` Berlin, `--date 2026-11-03`, 3 rounds × 12 pages, cap 90 s,
quiet 2 s. Label **scan** (every page sampled `running: true`). Reference:
<v206 Plan 1 scan after-run | none: no scan-labelled v206 after-run existed, so the table has one column>.

<the table from v217-compare.md, pasted unchanged, without its "reference:" line>

**What the probe can and cannot show.** The probe opens the Dashboard on 1D,
which sent one `/dashboard` before v217 as well, so the wider-scope saving (one
`/dashboard` instead of two on 1W/1M/All/a range) does not appear in its
counts. It is pinned by `dashboard.store.spec.ts` ("lands today from the
wider response: one request, no today fetch") and by V217-3's
`tests/admin_perf/test_today_block.py` (one `get_trades` per request, within
the `dashboard` SQL budget). The day page row shows the `/calendar/pnl` calls
per visit to `trades/calendar/2026-11-03`. A mid-month day had one month call
before and should have one after. The removed calls are the second month at a
month edge, pinned by `calendar-day.store.spec.ts` ("takes both neighbours
from the day response and asks for no adjacent month").

<the body of the v217-after probe.md from "## Goal" to the end, with every "##" heading demoted to "####">
```

Fill `<probe_sha>` and `<berlin_time>` from the run's `probe.json` `report.meta`, `<tag>` from Step 8, and the versions from `VERSION.json`. If the day page row shows more than one `/calendar/pnl` call per visit after v217, say so plainly with the figure and tell the partner. Change no code here. Any `mixed`/`quiet` run from Step 11 goes below as `#### Not evidence: <label> run, <berlin_time>` with its Goal lines only.

- [ ] **Step 14: Check the section reads back, then commit on `main`**

```bash
python "<main>/scripts/dev/doc_section.py" "<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md" "Plan 2 after (committed probe)" | head -30
git -C "<main>" add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git -C "<main>" commit -m "docs(v206): Plan 2 after-probe during a scan (v217 V217-6)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "<main>" push origin main
```

Expected: the provenance paragraph and the table print (exit 2 from `doc_section.py` means: read the file at `## Results` directly). The push is docs-only. Watch its run as in Step 7. Then run `/close-out` for v217 (standing permission, `document-lifecycle.md`). Its Step 5b aligns any skill that cites `/dashboard`'s or `/calendar/pnl/day`'s fields.
