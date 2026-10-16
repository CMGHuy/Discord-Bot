# v171 Shared market-data fetch. Part 6: SPA, D9 report, full suite, production rollout (V171-30..V171-39)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V171-32:" -A 300 docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_6-spa-rollout.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v171-shared-market-data-fetch-design.md`](../specs/2026-10-16-v171-shared-market-data-fetch-design.md) (this part: D2 "Admin rules" (reload and first load fresh, navigation reuses, UX stays light), D5 "price not confirmed live" on the admin side, D7 proxy label and ages, D9 measurement, `## Success` (all six rows, fixed, never retuned), `## Rollout and rollback`)
**Index:** [`2026-10-16-v171-shared-market-data-fetch_0-index.md`](2026-10-16-v171-shared-market-data-fetch_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v171-shared-market-data-fetch` (created in V171-1). Never `cd`; use `git -C $WT`, `python $WT/scripts/dev/testrun.py file <test>` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths in V171-30..V171-35 are relative to `$WT`; V171-36..V171-39 run on `main` in `$R` after the merge. After every code task run `git -C $R status --short` and confirm the main tree is clean.

**Order.** V171-30 any time after V171-1 -> V171-31 (after V171-29's row fields) -> V171-32 (after V171-22 and V171-25) -> V171-33 -> V171-34 (after V171-4; may run in parallel with V171-30..V171-33) -> V171-35 last of the code tasks -> V171-36 -> V171-37 -> V171-38 -> V171-39, strictly in order on production.

**Consumed from earlier parts (ledger names):** `/api/v1/market/tape` rows gain `is_proxy: bool`, `proxy_symbol: str | None`, `age_s: float | None` (proxy rows: `price` null, `change_pct` set) (V171-29). Dashboard open trades, Trades rows and Watchlist market rows gain `price_age_s: float | None` and `price_as_of: str | None` (V171-25). The server header is `X-Swingbot-Fresh: 1` (`freshness.FRESH_HEADER`, V171-25). Plan records carry `quote_at`, `quote_kind`, `quote_age_s`, `quote_session`, `price_confirmed` (V171-17); trade records carry `quote` = `{"at", "kind", "age_s", "session", "confirmed"}` built by `rebuild.quote_record` (V171-18), where `age_s` is the time from quote fetch to persisted plan. Scan telemetry rows carry `rebuild: {"kept", "dropped", "misses"}` when `PLAN_REBUILD_ENABLED` is on (V171-20). `market_shared_repo().count_rows(since, until, *, conn) -> list[dict]` with keys `hour, provider, kind, asker, outcome, n` (V171-3). `swingbot.core.marketdata.shared.tape`: `TAPE_FIXED`, `TapeEntry(symbol, price, change_pct, is_proxy, proxy_symbol, as_of)`, `read_tape(symbols) -> dict[str, TapeEntry]` (V171-28).

**Decisions this part fixes** (inside the ledger's contracts):

- **What "fresh" means in the SPA.** Every `GET` made while the app is in its boot phase (from the first load or a browser reload until the second `NavigationStart`, i.e. the first in-app navigation, or `BOOT_FRESH_WINDOW_MS` = 10 s after the first `NavigationEnd`, whichever comes first) carries `X-Swingbot-Fresh: 1`, and so does every `GET` issued inside `FreshRequestService.markFresh(fn)` or with the `FRESH_REQUEST` context token. Non-`GET` requests never carry it (a mutation reads no market data). A page left open reuses the cache like navigation does: its later event-driven refetches on the same route are unmarked (partner's rule: only an intentional reload, a first load or a Retry click is fresh). The `EventSource` stream cannot set headers and needs none.
- **The page's own refresh control is the `sb-async` Retry button.** No price page has any other refresh control, and the spec forbids new controls. `Async` (`ui/async.ts`) emits `retry` inside `markFresh`, so every Retry on every page is a fresh request with one edit.
- **Windows on the SPA side** are constants in `ui/age-hint.ts`: `DASHBOARD_PRICE_WINDOW_S = 15`, `PAGE_PRICE_WINDOW_S = 60`, `TAPE_WINDOW_S = 60` (the D2 defaults; the server's knobs are not served to the SPA, so a changed `.env` moves only when the hint appears, never what is fetched).
- **Where the new elements sit.** Age hints: the Dashboard positions' live P&L cell (15 s), the Watchlist price cell, the trade detail's "Now / Price" row and every tape tile (60 s). The quote line ("Alert price"): the trade detail's "Opened" panel and the plan page header. The Trades list "Now" column and the Risk page get no hint: V171-25 adds no age to the Risk rows, and the Trades list column is a text-only `value` function (the trade detail carries the hint). Both are listed under OPEN for the controller.
- **The D9 report is the measuring instrument for the Success table, defined before any data exists** (V171-34): provider calls = counter rows with outcome `fetched` or `failed` (a `hit`, `shared-wait` or `budget-deferred` made no provider call), counted per symbol in both modes; an in-session hour is a UTC hour bucket whose midpoint is in the regular session and on an open tape day (`session.is_regular_session` and `session.is_tape_open`); blank tape minutes come from a once-a-minute sampler of the shared tape copy, and the check needs at least 95 % minute coverage of the window's session minutes to count as measured. Two rows (429s, delta parity) are measured by V171-39 from the logs and a parity run, never by the report.
- **Far-off checks run as VM crons** (`docs/claude/working-conventions.md` § Scheduling): `scripts/ops/v171_report_cron.sh` (one window, one label, removes its own crontab line after the window), `scripts/ops/v171_tape_sampler_cron.sh` and one installer `scripts/ops/install_v171_cron.sh`. They are created in V171-34 so they ship with the code deploy (files added to the ledger's V171-34 row; nothing else depends on them).
- **Rollback, lightest first:** a part's flag off (`scripts/ops/env_set.py`, then `docker compose restart bot admin`); then the previous image (`docs/deploy/DEPLOY_HETZNER.md` § Rolling back); `scripts/ops/rollback_to.sh` (whole-bot point-in-time restore, `--dry-run` first) only for damaged data. The `v171_001` tables stay in every case.

---

# Phase 6 — SPA freshness, age hints and the visual pass; D9 report; full suite

### Task V171-30: SPA fresh marking: `freshInterceptor`, `FreshRequestService`, refresh controls mark fresh

**Model:** sonnet — one interceptor and a service with specs

**Files:**
- Create: `frontend/src/app/api/fresh-request.service.ts`
- Create: `frontend/src/app/api/fresh-request.service.spec.ts`
- Modify: `frontend/src/app/api/interceptors.ts` (new `freshInterceptor` after `routeRefreshInterceptor`, end of file)
- Modify: `frontend/src/app/api/interceptors.spec.ts` (the interceptor list in `beforeEach`, plus one new test)
- Modify: `frontend/src/app/app.config.ts` (`withInterceptors([...])` list and its order comment)
- Modify: `frontend/src/app/ui/async.ts` (the Retry button's `(click)`)
- Modify: `frontend/src/app/ui/async.spec.ts` (one new test)

**Interfaces:**
- Consumes: the header name `X-Swingbot-Fresh` and value `1` (V171-25 `freshness.FRESH_HEADER`; the server reads exactly `"1"`).
- Produces:
  - `fresh-request.service.ts`: `export const FRESH_HEADER = 'X-Swingbot-Fresh';`, `export const FRESH_REQUEST = new HttpContextToken<boolean>(() => false);`, `@Injectable({ providedIn: 'root' }) export class FreshRequestService` with `export const BOOT_FRESH_WINDOW_MS = 10_000;`, `isBootPhase(): boolean` (true until the second `NavigationStart` or until `BOOT_FRESH_WINDOW_MS` after the first `NavigationEnd`, whichever comes first), `isMarking(): boolean` (true while a `markFresh` callback runs), `markFresh<T>(fn: () => T): T` (runs `fn` synchronously; every request whose interceptor chain runs inside `fn` carries the mark; nests; the depth is restored when `fn` throws).
  - `interceptors.ts`: `export const freshInterceptor: HttpInterceptorFn`. A `GET` gets `X-Swingbot-Fresh: 1` when `req.context.get(FRESH_REQUEST)`, `fresh.isMarking()` or `fresh.isBootPhase()`; every other request passes unchanged.
  - `Async` (`sb-async`): the Retry button emits `retry` inside `markFresh`, so a parent's synchronous `store.load()` is a fresh request.

Why "the second `NavigationStart`": the first one is the initial navigation of a full page load (first load or browser reload); the second is the first in-app route change (a link click, or a background resolver refresh from `RouteRefreshService`). Why also the 10 s window: a page left open on its first route would otherwise mark every event-driven refetch (the tape's 30 s `scan` refetch, store reloads) fresh until the first navigation. The window keeps the initial page load's GETs (resolvers and the stores' first loads, all issued within a few seconds of the first `NavigationEnd`) and ends there, so the open page reuses the shared cache like navigation does (partner's rule). Requests until the boot phase ends are "the requests a full page load makes" (spec D2).

- [ ] **Step 1: Write the failing service spec**
Create `frontend/src/app/api/fresh-request.service.spec.ts`:

```ts
import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BOOT_FRESH_WINDOW_MS, FRESH_HEADER, FRESH_REQUEST, FreshRequestService } from './fresh-request.service';
import { freshInterceptor } from './interceptors';

@Component({ template: '' })
class Blank {}

describe('FreshRequestService (v171 D2: reload means fresh, navigation means reuse)', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let router: Router;
  let fresh: FreshRequestService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }]),
        provideHttpClient(withInterceptors([freshInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    fresh = TestBed.inject(FreshRequestService);
  });

  const header = (url: string) => {
    const req = backend.expectOne(url);
    const value = req.request.headers.get(FRESH_HEADER);
    req.flush({});
    return value;
  };

  it('marks every GET of a full page load', () => {
    http.get('/api/v1/dashboard').subscribe();
    expect(header('/api/v1/dashboard')).toBe('1');
  });

  it('still marks after the initial navigation (one NavigationStart)', async () => {
    await router.navigateByUrl('/a');
    expect(fresh.isBootPhase()).toBe(true);
    http.get('/api/v1/trades').subscribe();
    expect(header('/api/v1/trades')).toBe('1');
  });

  it('stops marking at the first in-app navigation', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    expect(fresh.isBootPhase()).toBe(false);
    http.get('/api/v1/watchlist/tickers').subscribe();
    expect(header('/api/v1/watchlist/tickers')).toBeNull();
  });

  it('ends the boot phase 10 s after the first NavigationEnd on the same route', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });   // zoneless app, no zone.js: vitest clock, not fakeAsync
    try {
      await router.navigateByUrl('/a');
      vi.setSystemTime(Date.now() + BOOT_FRESH_WINDOW_MS - 1);
      expect(fresh.isBootPhase()).toBe(true);
      vi.setSystemTime(Date.now() + 2);
      expect(fresh.isBootPhase()).toBe(false);
      http.get('/api/v1/market/tape').subscribe();
      expect(header('/api/v1/market/tape')).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it('marks requests issued inside markFresh after the boot phase', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    fresh.markFresh(() => http.get('/api/v1/trades').subscribe());
    expect(header('/api/v1/trades')).toBe('1');
    http.get('/api/v1/trades?x=1').subscribe();
    expect(header('/api/v1/trades?x=1')).toBeNull();
  });

  it('marks a request carrying the FRESH_REQUEST context token', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    http.get('/api/v1/risk', { context: new HttpContext().set(FRESH_REQUEST, true) }).subscribe();
    expect(header('/api/v1/risk')).toBe('1');
  });

  it('never marks a mutation, even in the boot phase', () => {
    http.post('/api/v1/trades/x/close', {}).subscribe();
    expect(header('/api/v1/trades/x/close')).toBeNull();
  });

  it('returns the callback value, nests, and restores the depth when the callback throws', () => {
    expect(fresh.markFresh(() => fresh.markFresh(() => fresh.isMarking()))).toBe(true);
    expect(fresh.isMarking()).toBe(false);
    expect(() => fresh.markFresh(() => { throw new Error('boom'); })).toThrow('boom');
    expect(fresh.isMarking()).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**
Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/api/fresh-request.service.spec.ts`. Expected: FAIL, the build cannot resolve `./fresh-request.service` and `freshInterceptor`.

- [ ] **Step 3: Implement `FreshRequestService` in `frontend/src/app/api/fresh-request.service.ts`**

```ts
import { HttpContextToken } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';

/** v171 D2. The admin server reads exactly this header with value `1` and
 *  then skips the shared cache's reuse window for that request's market
 *  data (still single-flighted, still at admin priority, tier 5). */
export const FRESH_HEADER = 'X-Swingbot-Fresh';

/** Per-request opt-in, for a caller that is a refresh but not a Retry. */
export const FRESH_REQUEST = new HttpContextToken<boolean>(() => false);

/** How long after the first NavigationEnd the page load's GETs stay fresh. */
export const BOOT_FRESH_WINDOW_MS = 10_000;

/**
 * Which requests are "fresh" (spec v171 D2, the partner's rule): the ones a
 * full page load makes (first load or browser reload) and the ones an
 * explicit refresh click makes. In-app navigation reuses the shared cache.
 *
 * The boot phase ends at the second NavigationStart (the first in-app route
 * change, or a background resolver refresh) or BOOT_FRESH_WINDOW_MS after the
 * first NavigationEnd, whichever comes first: a page left open then reuses
 * the cache for its event-driven refetches, like navigation does.
 */
@Injectable({ providedIn: 'root' })
export class FreshRequestService {
  private navigationStarts = 0;
  private bootEndsAt: number | null = null;
  private depth = 0;

  constructor() {
    inject(Router).events.subscribe((event) => {
      if (event instanceof NavigationStart) this.navigationStarts++;
      if (event instanceof NavigationEnd && this.bootEndsAt === null) {
        this.bootEndsAt = Date.now() + BOOT_FRESH_WINDOW_MS;
      }
    });
  }

  isBootPhase(): boolean {
    return this.navigationStarts < 2 && (this.bootEndsAt === null || Date.now() < this.bootEndsAt);
  }

  isMarking(): boolean {
    return this.depth > 0;
  }

  /** Requests whose interceptor chain runs inside `fn` carry the mark.
   *  HttpClient runs the chain at subscribe time, so `fn` must subscribe
   *  synchronously; every store `load()` in this app does. */
  markFresh<T>(fn: () => T): T {
    this.depth++;
    try {
      return fn();
    } finally {
      this.depth--;
    }
  }
}
```

- [ ] **Step 4: Add `freshInterceptor` at the end of `frontend/src/app/api/interceptors.ts`**
Import `FRESH_HEADER`, `FRESH_REQUEST`, `FreshRequestService` from `./fresh-request.service`.

```ts
/** v171 D2: mark the requests of a full page load and of explicit refresh
 *  clicks as fresh. Reads only: a mutation reads no market data. */
export const freshInterceptor: HttpInterceptorFn = (req, next) => {
  const fresh = inject(FreshRequestService);
  const marked = req.method === 'GET'
    && (req.context.get(FRESH_REQUEST) || fresh.isMarking() || fresh.isBootPhase());
  return next(marked ? req.clone({ setHeaders: { [FRESH_HEADER]: '1' } }) : req);
};
```

- [ ] **Step 5: Run the service spec to verify it passes**
Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/api/fresh-request.service.spec.ts`. Expected: PASS (8 tests).

- [ ] **Step 6: Register it, keeping the interceptor spec in the app's order**
In `frontend/src/app/app.config.ts`, import `freshInterceptor` with the other interceptors and make the list `withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor, freshInterceptor])`. Extend the order comment above `provideHttpClient` with one line: `fresh is innermost: it only adds a header on the way out and never sees a response, so its position changes nothing else.`

In `frontend/src/app/api/interceptors.spec.ts`, import `freshInterceptor` and `provideRouter` (`@angular/router`); add `freshInterceptor` at the end of the `withInterceptors([...])` list in the top-level `beforeEach` (same order as `app.config.ts`, as that file's header comment requires) and add `provideRouter([])` to its providers. Append inside the top-level `describe`:

```ts
  /* -- fresh (v171 D2) ------------------------------------------------- */

  it('sends the fresh header on a GET of the page load, after the other interceptors', () => {
    http.get('/api/v1/dashboard').subscribe();
    const req = backend.expectOne('/api/v1/dashboard');
    expect(req.request.headers.get('X-Swingbot-Fresh')).toBe('1');
    expect(req.request.withCredentials).toBe(true);
    req.flush({});
  });
```

- [ ] **Step 7: Write the failing `Async` test**
In `frontend/src/app/ui/async.spec.ts`, import `FreshRequestService` from `../api/fresh-request.service` and append inside `describe('Async', ...)`:

```ts
  it('emits Retry inside markFresh, so the reload it triggers is fresh (v171 D2)', () => {
    const fresh = TestBed.inject(FreshRequestService);
    const { f, el } = render({ error: 'The admin could not be reached.' });
    let markingDuringRetry: boolean | null = null;
    f.componentInstance.onRetried = () => { markingDuringRetry = fresh.isMarking(); };
    (el.querySelector('button.retry') as HTMLButtonElement).click();
    expect(f.componentInstance.retried).toBe(1);
    expect(markingDuringRetry).toBe(true);
    expect(fresh.isMarking()).toBe(false);
  });
```

and give the spec's `Host` a hook the handler calls: the template's `(retry)="retried = retried + 1"` becomes `(retry)="retried = retried + 1; onRetried()"`, and `Host` gains `onRetried: () => void = () => undefined;`.

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/async.spec.ts`. Expected: FAIL on `markingDuringRetry` (`false`: the button emits outside `markFresh`).

- [ ] **Step 8: Emit Retry inside `markFresh` in `frontend/src/app/ui/async.ts`**
Import `inject` from `@angular/core` and `FreshRequestService` from `../api/fresh-request.service`. Change the button to `(click)="onRetry()"` and add to the class:

```ts
  private readonly fresh = inject(FreshRequestService);

  /** v171 D2: Retry is each page's own refresh control, so the reload it
   *  triggers fetches fresh market data instead of reusing the cache. The
   *  parent's handler runs synchronously inside emit(). */
  protected onRetry(): void {
    this.fresh.markFresh(() => this.retry.emit());
  }
```

- [ ] **Step 9: Run every spec this task touched, plus the guards over `ui/`**
Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/api/fresh-request.service.spec.ts --include src/app/api/interceptors.spec.ts --include src/app/ui/async.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/primitives.spec.ts`. Expected: PASS, 0 failed.

- [ ] **Step 10: Commit**

```bash
git -C $WT add frontend/src/app/api/fresh-request.service.ts frontend/src/app/api/fresh-request.service.spec.ts frontend/src/app/api/interceptors.ts frontend/src/app/api/interceptors.spec.ts frontend/src/app/app.config.ts frontend/src/app/ui/async.ts frontend/src/app/ui/async.spec.ts
git -C $WT commit -m "feat(v171): SPA marks page-load and Retry requests fresh (X-Swingbot-Fresh)

Spec D2: reload means fresh, navigation and an open page reuse. The boot
phase ends at the second NavigationStart or 10 s after the first
NavigationEnd; sb-async Retry emits inside markFresh.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V171-31: `sb-age-hint` and the tape proxy label with age

**Model:** sonnet — one UI primitive and one shell component change, three widths

**Files:**
- Create: `frontend/src/app/ui/age-hint.ts`
- Create: `frontend/src/app/ui/age-hint.spec.ts`
- Modify: `frontend/src/app/api/models.ts` (`TapeRow`, :1863-1874)
- Modify: `frontend/src/app/shell/tape/tape.ts` (`Tile`, `tiles`, the tile template)
- Modify: `frontend/src/app/shell/tape/tape.spec.ts`

**Interfaces:**
- Consumes: `/api/v1/market/tape` rows `is_proxy`, `proxy_symbol`, `age_s` (V171-29). With `TAPE_SHARED_ENABLED` off the server sends none of them, and the tape renders exactly as today.
- Produces (V171-32 and V171-33 use these):
  - `ui/age-hint.ts`: `export const DASHBOARD_PRICE_WINDOW_S = 15;`, `export const PAGE_PRICE_WINDOW_S = 60;`, `export const TAPE_WINDOW_S = 60;`, `export function ageText(ageS: number | null): string | null`, component `AgeHint` (selector `sb-age-hint`, standalone, OnPush) with `ageS = input<number | null>(null)` and `windowS = input.required<number>()`; renders `<span class="age-hint">` only when the US market is open (`ConnectionStore.marketActive() === true`, the SR58 `/health` `market_active` flag the shell already polls; `null` = not known yet counts as closed) and `ageS !== null && ageS > windowS`. V171-25 reports a quote's own age, so outside the session every price is "old"; the hint stays silent then (partner: the UI must not feel heavier).
  - `TapeRow` gains `is_proxy?: boolean`, `proxy_symbol?: string | null`, `age_s?: number | null`.
  - Tape tile DOM: a proxy tile shows its index label, the change % and `<span class="ctx proxy">SPY proxy</span>`, never a price and never "no price"; every tile ends with `<sb-age-hint>` (window 60 s).

`ageText` rules (spec D2 "12 s ago" / "1 min ago"): `null`, `NaN` or a negative age -> `null`; under 60 -> `` `${Math.round(ageS)} s ago` ``; under 3600 -> `` `${Math.floor(ageS / 60)} min ago` ``; else `` `${Math.floor(ageS / 3600)} h ago` ``. The hint is quiet text in the existing styling: `font-size: var(--text-micro)`, `color: var(--text-faint)`, `white-space: nowrap`, `margin-inline-start: var(--space-4)`, `font-variant-numeric: tabular-nums`; no colour change, no icon, no animation (spec D2 "UX stays light"). It carries `title="Price is <text> old"` for hover and is plain text for screen readers.

- [ ] **Step 1: Write the failing `AgeHint` spec**
Create `frontend/src/app/ui/age-hint.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConnectionStore } from '../stores/connection.store';
import { AgeHint, PAGE_PRICE_WINDOW_S, ageText } from './age-hint';

let marketActive: boolean | null = true;

function render(ageS: number | null, windowS = PAGE_PRICE_WINDOW_S): HTMLElement {
  const f = TestBed.createComponent(AgeHint);
  f.componentRef.setInput('ageS', ageS);
  f.componentRef.setInput('windowS', windowS);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('ageText (v171 D2)', () => {
  it('reads seconds under a minute', () => expect(ageText(12)).toBe('12 s ago'));
  it('rounds seconds', () => expect(ageText(12.6)).toBe('13 s ago'));
  it('reads whole minutes', () => {
    expect(ageText(60)).toBe('1 min ago');
    expect(ageText(119)).toBe('1 min ago');
    expect(ageText(180)).toBe('3 min ago');
  });
  it('reads hours past an hour', () => expect(ageText(7300)).toBe('2 h ago'));
  it('is null for no age, NaN or a negative age', () => {
    expect(ageText(null)).toBeNull();
    expect(ageText(Number.NaN)).toBeNull();
    expect(ageText(-1)).toBeNull();
  });
});

describe('AgeHint (sb-age-hint)', () => {
  beforeEach(() => {
    marketActive = true;
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(),
      { provide: ConnectionStore, useValue: { marketActive: () => marketActive } }] });
  });

  it('renders nothing while the market is closed or its state is unknown, however old', () => {
    marketActive = false;
    expect(render(7200).querySelector('.age-hint')).toBeNull();
    marketActive = null;
    expect(render(7200).querySelector('.age-hint')).toBeNull();
  });

  it('renders nothing inside the window', () => {
    expect(render(60).querySelector('.age-hint')).toBeNull();
    expect(render(14, 15).querySelector('.age-hint')).toBeNull();
  });

  it('renders the age once the price is older than its window', () => {
    expect(render(61).querySelector('.age-hint')?.textContent?.trim()).toBe('1 min ago');
    expect(render(16, 15).querySelector('.age-hint')?.textContent?.trim()).toBe('16 s ago');
  });

  it('renders nothing for an unknown age (pre-v171 rows, flag off)', () => {
    expect(render(null).querySelector('.age-hint')).toBeNull();
  });

  it('is plain text: no spinner, no icon, never the word live', () => {
    const el = render(240);
    expect(el.querySelector('svg, .spinner, sb-icon')).toBeNull();
    expect(el.textContent?.toLowerCase()).not.toContain('live');
    expect(el.querySelector('.age-hint')?.getAttribute('title')).toBe('Price is 4 min old');
  });
});
```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/age-hint.spec.ts`. Expected: FAIL, `./age-hint` does not exist.

- [ ] **Step 2: Implement `frontend/src/app/ui/age-hint.ts`**

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { ConnectionStore } from '../stores/connection.store';

/** The D2 windows as the SPA sees them. The server's `.env` knobs are not
 *  served to the SPA; changing one moves what is fetched, and only these
 *  decide when the hint appears. */
export const DASHBOARD_PRICE_WINDOW_S = 15;
export const PAGE_PRICE_WINDOW_S = 60;
export const TAPE_WINDOW_S = 60;

export function ageText(ageS: number | null): string | null {
  if (ageS === null || Number.isNaN(ageS) || ageS < 0) return null;
  if (ageS < 60) return `${Math.round(ageS)} s ago`;
  if (ageS < 3600) return `${Math.floor(ageS / 60)} min ago`;
  return `${Math.floor(ageS / 3600)} h ago`;
}

/**
 * v171 D2: "12 s ago" beside a price older than its page's window, and
 * nothing otherwise. Prices render at once from the shared cache; this is
 * the only sign that one is older than the page promises (no spinner, no
 * veil, no colour). It does not tick: the page's own refetch moves it,
 * as with sb-freshness.
 */
@Component({
  selector: 'sb-age-hint',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (text(); as t) {
      <span class="age-hint" [attr.title]="'Price is ' + t.replace(' ago', '') + ' old'">{{ t }}</span>
    }
  `,
  styles: `
    :host { display: inline; }
    .age-hint {
      font-size: var(--text-micro);
      color: var(--text-faint);
      white-space: nowrap;
      margin-inline-start: var(--space-4);
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class AgeHint {
  readonly ageS = input<number | null>(null);
  readonly windowS = input.required<number>();
  private readonly connection = inject(ConnectionStore);

  /** Market closed (or not known yet): every quote is "old", so say nothing. */
  protected readonly text = computed(() => {
    const age = this.ageS();
    if (this.connection.marketActive() !== true) return null;
    return age !== null && age > this.windowS() ? ageText(age) : null;
  });
}
```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/age-hint.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts`. Expected: PASS, 0 failed.

- [ ] **Step 3: Extend `TapeRow` in `frontend/src/app/api/models.ts`**
Add after `sort_rank: number;`:

```ts
  /** v171 D7: true when Yahoo came back blank and the tape shows an Alpaca
   *  ETF proxy instead. A proxy row has `price` null and `change_pct` set:
   *  an ETF price must never be read as an index level. Absent when the
   *  server's TAPE_SHARED_ENABLED is off. */
  is_proxy?: boolean;
  /** The proxy's own symbol (SPY, QQQ, DIA, VIXY, SLV), shown as its label. */
  proxy_symbol?: string | null;
  /** Seconds since the value was fetched, from the shared copy. */
  age_s?: number | null;
```

- [ ] **Step 4: Write the failing tape specs**
Append inside `describe('Tape', ...)` in `frontend/src/app/shell/tape/tape.spec.ts`:

```ts
  const proxy = { symbol: '^GSPC', price: null, change_pct: 0.42, is_proxy: true, proxy_symbol: 'SPY', age_s: 20 };
  // setup() gains `{ provide: ConnectionStore, useValue: { marketActive: () => true } }` in its providers
  // (import from '../../stores/connection.store'), so the age tests run with the market open.

  it('labels a proxy row and shows its change only, never a level (v171 D7)', () => {
    const el = setup([proxy], []).nativeElement as HTMLElement;
    const tile = el.querySelector('.tile')!;
    expect(tile.querySelector('.sym')?.textContent).toBe('S&P 500');
    expect(tile.querySelector('.ctx.proxy')?.textContent?.trim()).toBe('SPY proxy');
    expect(tile.textContent).toContain('+0.42%');
    expect(tile.querySelector('.px')).toBeNull();
    expect(tile.textContent).not.toContain('no price');
  });

  it('shows the age of a value older than the tape window', () => {
    const el = setup([{ ...index, age_s: 240 }], []).nativeElement as HTMLElement;
    expect(el.querySelector('.tile .age-hint')?.textContent?.trim()).toBe('4 min ago');
  });

  it('shows no age inside the window, nor when the server sends none (flag off)', () => {
    expect((setup([{ ...index, age_s: 30 }], []).nativeElement as HTMLElement).querySelector('.age-hint')).toBeNull();
    TestBed.resetTestingModule();
    expect((setup([index], []).nativeElement as HTMLElement).querySelector('.age-hint')).toBeNull();
  });
```

(`pct` in `ui/format.ts` signs a positive change: `pct(0.42)` is `+0.42%`.)

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/tape/tape.spec.ts`. Expected: FAIL on the three new tests (no `.proxy`, no `.age-hint`; the proxy tile still reads "no price").

- [ ] **Step 5: Render proxies and ages in `frontend/src/app/shell/tape/tape.ts`**
- `Tile` gains `proxyLabel: string | null` and `ageS: number | null`. The index mapping sets `proxyLabel: r.is_proxy ? \`${r.proxy_symbol ?? 'ETF'} proxy\` : null` and `ageS: r.age_s ?? null`; the stock mapping sets the same two fields from its row (a flagged `SI=F` can be a proxy too).
- Import `AgeHint` and `TAPE_WINDOW_S` from `../../ui/age-hint`; add `AgeHint` to `imports`; expose `protected readonly tapeWindowS = TAPE_WINDOW_S;`.
- Replace the price block of the tile template (the `@if (tile.price !== null) { ... } @else { <span class="ctx muted">no price</span> }`) with:

```html
                @if (tile.proxyLabel) {
                  @if (tile.change_pct !== null) {
                    <span [class.up]="up(tile)" [class.down]="down(tile)">{{ pct(tile.change_pct) }}</span>
                  }
                  <span class="ctx proxy" title="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF's price.">{{ tile.proxyLabel }}</span>
                } @else if (tile.price !== null) {
                  <span class="px" [class.up]="up(tile)" [class.down]="down(tile)">{{ num(tile.price) }}</span>
                  @if (tile.change_pct !== null) {
                    <span [class.up]="up(tile)" [class.down]="down(tile)">{{ pct(tile.change_pct) }}</span>
                  }
                } @else {
                  <span class="ctx muted">no price</span>
                }
```

  and add `<sb-age-hint [ageS]="tile.ageS" [windowS]="tapeWindowS" />` as the last child of the `<a class="tile">`, after the `context_label` block. `.ctx.proxy` uses the existing `.ctx` rule in `tape.css` unchanged (no new colour); the tile stays one line: `.tile` is `inline-flex` with `align-items: baseline` (`tape.css` :69), so both new spans sit on its baseline, and the hint's own `nowrap` keeps "4 min ago" whole. Below the tape's narrow breakpoint `tape.css` hides `.px`; a proxy tile has no `.px`, so it reads the same at every width.

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/shell/tape/tape.spec.ts --include src/app/ui/age-hint.spec.ts`. Expected: PASS, 0 failed (the existing "never shows the word live" test still passes: "SPY proxy" and "4 min ago" contain no "live").

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/ui/age-hint.ts frontend/src/app/ui/age-hint.spec.ts frontend/src/app/api/models.ts frontend/src/app/shell/tape/tape.ts frontend/src/app/shell/tape/tape.spec.ts
git -C $WT commit -m "feat(v171): sb-age-hint; tape shows labelled ETF proxies (change only) and ages

Spec D2 age hint and D7 proxy label. Nothing renders without the server's
v171 fields, so the tape is unchanged with TAPE_SHARED_ENABLED off.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V171-32: Page wiring: age hints on Dashboard (15 s), Watchlist, Trades and Risk (60 s); plan/trade quote line with `n/a` and "price not confirmed live"

**Model:** sonnet — template additions across a few pages, rules fixed by D2/D5

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (new `_quote_stamp` before `_plan_detail` :665; one key in `_plan_detail` and in `_legacy_detail`)
- Create: `tests/admin/test_api_quote_fields.py`
- Modify: `frontend/src/app/api/models.ts` (`TradeRow` after `current_price_stale` :126; `TradeDetailFields` after `acceptance_level`; `Ticker` after `price_source` :1065; new `QuoteStamp`)
- Create: `frontend/src/app/workspaces/trades/quote-line.ts`
- Create: `frontend/src/app/workspaces/trades/quote-line.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (`#pnlCell` live branch :396-410, `imports`, one field)
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts` (`#priceCell` :402-411, `imports`, one field)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` ("Now" panel Price row :315-325, "Opened" panel after "Entry type" :260-263, `imports`, two members)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts` (`.tags` after the `created` span :~118, `imports`, one member)

**Interfaces:**
- Consumes: `AgeHint`, `DASHBOARD_PRICE_WINDOW_S`, `PAGE_PRICE_WINDOW_S` (V171-31); row fields `price_age_s`, `price_as_of` (V171-25, on `/api/v1/trades` rows (which the Dashboard positions table and the trade detail read) and on `/api/v1/watchlist/tickers` rows); plan record fields `quote_at`, `quote_kind`, `quote_age_s`, `quote_session`, `price_confirmed` (V171-17) and the trade record's `quote` dict (V171-18 `quote_record`).
- Produces:
  - `trades._quote_stamp(plan: dict | None, trade: dict | None) -> dict | None` (`{"at", "kind", "age_s", "session", "confirmed"}`; the trade record's `quote` wins; otherwise the plan's flat fields when `quote_kind` is set; else `None`). `GET /api/v1/trades/<id>` `detail.quote` carries it for plan-backed and legacy rows alike (one detail shape).
  - `models.ts`: `export interface QuoteStamp { at: string | null; kind: string | null; age_s: number | null; session: string | null; confirmed: boolean | null; }`; `TradeDetailFields.quote?: QuoteStamp | null`; `TradeRow.price_age_s?: number | null`, `TradeRow.price_as_of?: string | null`; `Ticker.price_age_s?: number | null`, `Ticker.price_as_of?: string | null` (optional, so existing fixtures and the gallery still compile).
  - `quote-line.ts`: `export function quoteLine(q: QuoteStamp | null | undefined): string`.

`quoteLine` wording (the admin twin of V171-22's embed line, without its "Price:" prefix because the page labels the row "Alert price"):

| Stamp | Text |
|---|---|
| `null` / absent (pre-v171, rebuild off) | `n/a` |
| `confirmed === false` or `kind === 'scan'` | `Price not confirmed live`, plus `, <session>` when the session is set and not `regular` |
| `kind` `trade` / `mid` / `yf-1m` | `Live trade` / `Bid/ask mid` / `Yahoo 1-min bar`, then `, <age_s with 1 decimal> s to post` when `age_s` is set, then `, <session>` when not `regular` |
| any other `kind` | the kind itself, same suffixes |

`age_s` is the time from the quote fetch to the persisted plan (the D5 5 s clock), which is what "to post" names.

Placement (part header, "Where the new elements sit"): Dashboard positions' live P&L cell, window 15 s; Watchlist price cell, trade detail "Now / Price", window 60 s; quote line in the trade detail's "Opened" panel (`<dt>Alert price</dt>`) and in the plan page's header tags (`Alert price: ...`). The Risk page and the Trades list "Now" column get no hint (no age on Risk rows from V171-25; the list column is a text `value` function); the trade detail carries the Trades hint.

- [ ] **Step 1: Write the failing API test**
Create `tests/admin/test_api_quote_fields.py`:

```python
"""v171 D2: the trade and plan detail carry the quote a posted plan was built from; n/a before v171."""
import pytest

from tests.admin.test_api_v1_trades import _plan, _trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"
_AT = "2026-10-15T13:00:01+00:00"
_PLAN_QUOTE = {"quote_at": _AT, "quote_kind": "mid", "quote_age_s": 1.7,
               "quote_session": "pre-market", "price_confirmed": True}
_TRADE_QUOTE = {"at": _AT, "kind": "trade", "age_s": 2.4, "session": "regular", "confirmed": True}


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _quote(client, row_id):
    return client.get(f"/api/v1/trades/{row_id}").get_json()["detail"]["quote"]


def test_plan_without_a_trade_row_reads_the_plan_fields(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID), **_PLAN_QUOTE}])
    assert _quote(logged_in, _PLAN_ID) == {"at": _AT, "kind": "mid", "age_s": 1.7,
                                           "session": "pre-market", "confirmed": True}


def test_the_trade_record_quote_wins_over_the_plan_fields(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID, status="ACTIVE"), **_PLAN_QUOTE}],
         trades=[{**_trade(_TRADE_ID, plan_id=_PLAN_ID), "quote": _TRADE_QUOTE}])
    assert _quote(logged_in, _PLAN_ID) == _TRADE_QUOTE


def test_legacy_trade_carries_its_quote(seed, logged_in):
    seed(trades=[{**_trade(_TRADE_ID), "quote": _TRADE_QUOTE}])
    assert _quote(logged_in, _TRADE_ID) == _TRADE_QUOTE


def test_unconfirmed_price_is_passed_through(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID), **_PLAN_QUOTE, "quote_kind": "scan", "price_confirmed": False}])
    quote = _quote(logged_in, _PLAN_ID)
    assert (quote["kind"], quote["confirmed"]) == ("scan", False)


@pytest.mark.parametrize("row_id, plans, trades", [
    (_PLAN_ID, [_plan(_PLAN_ID)], []),
    (_TRADE_ID, [], [_trade(_TRADE_ID)]),
])
def test_pre_v171_rows_carry_no_quote(seed, logged_in, row_id, plans, trades):
    seed(plans=plans, trades=trades)
    assert _quote(logged_in, row_id) is None
```

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_quote_fields.py`. Expected: FAIL with `KeyError: 'quote'` (6 failed).

- [ ] **Step 2: Implement `_quote_stamp` in `swingbot/admin/api_v1/trades.py`**
Add before `_plan_detail`:

```python
# v171 D2: response key -> the plan record's flat field (V171-17).
_QUOTE_PLAN_FIELDS = (("at", "quote_at"), ("kind", "quote_kind"), ("age_s", "quote_age_s"),
                      ("session", "quote_session"), ("confirmed", "price_confirmed"))


def _quote_stamp(plan: dict | None, trade: dict | None) -> dict | None:
    """The quote a posted plan was built from (v171 D2), or None before v171.

    The trade record's `quote` is written with the trade (V171-20) and wins;
    a plan with no trade row carries the same values as flat fields. No
    read-time upcasting: a row without them answers None and the SPA shows
    n/a (docs/claude/schema-evolution.md).
    """
    quote = (trade or {}).get("quote")
    if isinstance(quote, dict):
        return {key: quote.get(key) for key, _ in _QUOTE_PLAN_FIELDS}
    if not plan or plan.get("quote_kind") is None:
        return None
    return {key: plan.get(field) for key, field in _QUOTE_PLAN_FIELDS}
```

Add `"quote": _quote_stamp(plan, trade),` as the last key of `_plan_detail`'s dict and `"quote": _quote_stamp(None, t),` as the last key of `_legacy_detail`'s dict (one detail shape, as `_legacy_detail`'s docstring requires).

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_quote_fields.py` then `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`. Expected: PASS, 0 failed, both files.

- [ ] **Step 3: Write the failing SPA spec**
Create `frontend/src/app/workspaces/trades/quote-line.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { QuoteStamp } from '../../api/models';
import { quoteLine } from './quote-line';

const stamp = (patch: Partial<QuoteStamp> = {}): QuoteStamp => ({
  at: '2026-10-15T13:00:01+00:00', kind: 'trade', age_s: 2.4, session: 'regular', confirmed: true, ...patch,
});

describe('quoteLine (v171 D2/D5)', () => {
  it('reads n/a before v171', () => {
    expect(quoteLine(null)).toBe('n/a');
    expect(quoteLine(undefined)).toBe('n/a');
  });
  it('names the kind and the time to post', () => {
    expect(quoteLine(stamp())).toBe('Live trade, 2.4 s to post');
    expect(quoteLine(stamp({ kind: 'mid', age_s: 0.8 }))).toBe('Bid/ask mid, 0.8 s to post');
    expect(quoteLine(stamp({ kind: 'yf-1m', age_s: 3 }))).toBe('Yahoo 1-min bar, 3.0 s to post');
  });
  it('adds the session outside regular hours', () => {
    expect(quoteLine(stamp({ kind: 'mid', age_s: 1.7, session: 'pre-market' })))
      .toBe('Bid/ask mid, 1.7 s to post, pre-market');
  });
  it('says the price was not confirmed live', () => {
    expect(quoteLine(stamp({ kind: 'scan', confirmed: false, session: 'pre-market' })))
      .toBe('Price not confirmed live, pre-market');
    expect(quoteLine(stamp({ kind: 'scan', confirmed: false, age_s: null }))).toBe('Price not confirmed live');
  });
  it('omits an unknown age', () => {
    expect(quoteLine(stamp({ age_s: null }))).toBe('Live trade');
  });
});

/* Source pins: jsdom does not lay these pages out; V171-33 checks them rendered. */
const src = (path: string) => readFileSync(join(process.cwd(), 'src/app', path), 'utf8');

describe('v171 page wiring', () => {
  it('dashboard live P&L carries a 15 s age hint', () => {
    const text = src('workspaces/dashboard/dashboard.ts');
    expect(text).toMatch(/<sb-age-hint \[ageS\]="row\.price_age_s \?\? null" \[windowS\]="dashboardWindowS"/);
    expect(text).toContain('DASHBOARD_PRICE_WINDOW_S');
  });
  it('watchlist price and trade detail price carry a 60 s age hint', () => {
    expect(src('workspaces/watchlist/watchlist.ts')).toMatch(/<sb-age-hint \[ageS\]="row\.price_age_s \?\? null" \[windowS\]="pageWindowS"/);
    expect(src('workspaces/trades/trade-detail.ts')).toMatch(/<sb-age-hint \[ageS\]="trade\.price_age_s \?\? null" \[windowS\]="pageWindowS"/);
  });
  it('trade detail and plan page show the alert price line', () => {
    expect(src('workspaces/trades/trade-detail.ts')).toContain('<dt>Alert price</dt>');
    expect(src('workspaces/trades/trade-detail.ts')).toContain('quoteLine(store.detail()?.quote ?? null)');
    expect(src('workspaces/plans/plan-detail.ts')).toContain('Alert price: {{ quoteLine(store.detail()?.quote ?? null) }}');
  });
});
```

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/quote-line.spec.ts`. Expected: FAIL, `./quote-line` and `QuoteStamp` do not exist.

- [ ] **Step 4: Add the model fields and `quoteLine`**
In `frontend/src/app/api/models.ts`: add `QuoteStamp` (Interfaces block, with a doc comment naming V171-17/18 and "n/a before v171") just above `TradeDetailFields`; add `quote?: QuoteStamp | null;` as the last member of `TradeDetailFields`; add to `TradeRow` after `current_price_stale` and to `Ticker` after `price_source`:

```ts
  /** v171 D2: seconds since `current_price` (Ticker: `price`) was fetched,
   *  from the shared cache; null when unknown (pre-v171 server, layer off). */
  price_age_s?: number | null;
  /** ISO-8601 UTC instant of that fetch. */
  price_as_of?: string | null;
```

Create `frontend/src/app/workspaces/trades/quote-line.ts`:

```ts
import { QuoteStamp } from '../../api/models';

const KIND_WORDS: Record<string, string> = {
  trade: 'Live trade',
  mid: 'Bid/ask mid',
  'yf-1m': 'Yahoo 1-min bar',
};

/** v171 D2/D5: the price a posted plan was built from, as one line. The
 *  admin twin of the Discord embed's quote line (alert_embeds.quote_line). */
export function quoteLine(q: QuoteStamp | null | undefined): string {
  if (!q) return 'n/a';
  const session = q.session && q.session !== 'regular' ? `, ${q.session}` : '';
  if (q.confirmed === false || q.kind === 'scan') return `Price not confirmed live${session}`;
  if (q.kind === null) return 'n/a';
  const age = q.age_s === null ? '' : `, ${q.age_s.toFixed(1)} s to post`;
  return `${KIND_WORDS[q.kind] ?? q.kind}${age}${session}`;
}
```

- [ ] **Step 5: Wire the four pages**
- `dashboard.ts`: import `AgeHint`, `DASHBOARD_PRICE_WINDOW_S` from `../../ui/age-hint`; add `AgeHint` to `imports`; add `protected readonly dashboardWindowS = DASHBOARD_PRICE_WINDOW_S;` beside the other protected helpers (:~951); in `#pnlCell`'s live branch, right after the closing `</span>` of the `livePnlPct(row)` span and before `<span class="sep">`, add `<sb-age-hint [ageS]="row.price_age_s ?? null" [windowS]="dashboardWindowS" />`.
- `watchlist.ts`: import `AgeHint`, `PAGE_PRICE_WINDOW_S`; add `AgeHint` to `imports`; add `protected readonly pageWindowS = PAGE_PRICE_WINDOW_S;`; in `#priceCell`, after `<span class="as-of">{{ text(row.as_of) }}</span>`, add `<sb-age-hint [ageS]="row.price_age_s ?? null" [windowS]="pageWindowS" />`.
- `trade-detail.ts`: import `AgeHint`, `PAGE_PRICE_WINDOW_S` and `quoteLine` (`./quote-line`); add `AgeHint` to `imports`; add `protected readonly pageWindowS = PAGE_PRICE_WINDOW_S;` and `protected readonly quoteLine = quoteLine;`; in the "Now" panel's Price `<dd>`, after the `current_price_stale` block, add `<sb-age-hint [ageS]="trade.price_age_s ?? null" [windowS]="pageWindowS" />`; in the "Opened" panel, after the "Entry type" `<div>`, add:

```html
                <div>
                  <dt>Alert price</dt>
                  <dd>{{ quoteLine(store.detail()?.quote ?? null) }}</dd>
                </div>
```

- `plan-detail.ts`: import `quoteLine` from `../trades/quote-line`; add `protected readonly quoteLine = quoteLine;`; in `.tags`, after the `@if (createdAt(); as at) { ... }` block, add `<span class="created">Alert price: {{ quoteLine(store.detail()?.quote ?? null) }}</span>` (the existing `.created` style; no new colour or chip).

- [ ] **Step 6: Run the specs of every page touched**
Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/quote-line.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/watchlist/watchlist.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/spacing.spec.ts`. Expected: PASS, 0 failed. A page spec that pins exact text (for example a header's tag list in `plan-detail.spec.ts`) and now also sees `Alert price: n/a` is updated in this commit to expect it, and the commit body names the test.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/admin/api_v1/trades.py tests/admin/test_api_quote_fields.py frontend/src/app/api/models.ts frontend/src/app/workspaces/trades/quote-line.ts frontend/src/app/workspaces/trades/quote-line.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/watchlist/watchlist.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/plans/plan-detail.ts
git -C $WT commit -m "feat(v171): price age hints and the alert-price quote line in the admin

Spec D2: Dashboard 15 s, Watchlist and trade detail 60 s; detail.quote on
/trades/<id> with n/a before v171 and 'Price not confirmed live' (D5).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V171-33: Playwright pass at 390/768/1440: tape proxy label, age hints, quote line; no new spinner or blank state

**Model:** sonnet — runs the stack and judges screenshots

**Files:**
- Modify: `docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md` (records the pass under `## Progress`)
- Modify (only if the pass finds a defect): the files V171-31/V171-32 touched (`frontend/src/app/ui/age-hint.ts`, `frontend/src/app/shell/tape/tape.ts`, the four page files), never another `ui/` primitive
- Scratch, git-ignored, never committed: `.superpowers/v171-probe.mjs`, `.superpowers/v171-shots/`

**Interfaces:**
- Consumes: `sb-age-hint` `.age-hint`, tape `.ctx.proxy` (V171-31); `<dt>Alert price</dt>` and the plan header's `Alert price:` line (V171-32); the `X-Swingbot-Fresh` header (V171-30); `frontend/scripts/browse.mjs` (`login`, its persistent profile under `%LOCALAPPDATA%\swingbot-playwright\profile`). Playwright only, never claude-in-chrome (CLAUDE.md).
- Produces: nothing a later task reads, beyond the `## Progress` record.

**The acceptance rule** (spec D2 "UX stays light", `docs/claude/ui-design.md` § Checklist): at 390, 768 and 1440 px, on the Dashboard, the Watchlist, one trade detail (`?tab=live` and the default tab) and one plan page: the proxy label, the age hint and the quote line are visible, unclipped and on the line they belong to; the page never scrolls sideways; no spinner, veil or blank state appears that the same page without the v171 fields does not show; first-load requests carry `X-Swingbot-Fresh: 1` and requests after an in-app navigation do not.

**Data.** The local stack has no bot feeding the shared tape and the main-tree API has no v171 fields, so the probe rewrites the API responses in the browser (Playwright `page.route`): `^GSPC` becomes an SPY proxy (`price` null, `change_pct` 0.42, `age_s` 20), `^VIX` gets `age_s` 240, every other tape row `age_s` 5; `/health` answers `market_active: true` (the age hint shows only while the market is open); the first `/trades` row and every trade detail get `price_age_s` 75 (and 30 on the Dashboard's second row, to show the 15 s window); the first watchlist ticker gets `price_age_s` 90; the trade detail gets `detail.quote` = `{kind: 'mid', age_s: 1.7, session: 'pre-market', confirmed: true}` and the plan page `{kind: 'scan', age_s: null, session: 'regular', confirmed: false}`. Real responses are fetched first and only these fields are added, so layout comes from real data.

- [ ] **Step 1: Check the tools**

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
npm --prefix $WT/frontend exec -- playwright --version
node --check $WT/frontend/scripts/browse.mjs
```
Expected: a `Version 1.x` line and no output from `node --check`. If Chromium is missing: `npm --prefix $WT/frontend exec -- playwright install chromium` once.

- [ ] **Step 2: Write the probe** to `$WT/.superpowers/v171-probe.mjs`:

```js
// v171 V171-33 probe: route-patched v171 fields, shots and checks at 390/768/1440.
// usage: node v171-probe.mjs <frontendDir> <base> <outDir> <tradeId> <planId>
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
const [frontend, base, out, tradeId, planId] = process.argv.slice(2);
const { chromium } = createRequire(join(frontend, 'package.json'))('playwright');
const PROFILE = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'swingbot-playwright', 'profile');
mkdirSync(out, { recursive: true });

const patchTape = (b) => ({ ...b, rows: b.rows.map((r) => r.symbol === '^GSPC'
  ? { ...r, price: null, change_pct: 0.42, is_proxy: true, proxy_symbol: 'SPY', age_s: 20 }
  : { ...r, is_proxy: false, proxy_symbol: null, age_s: r.symbol === '^VIX' ? 240 : 5 }) });
const patchList = (b) => ({ ...b, items: b.items.map((r, i) => ({ ...r, price_age_s: [75, 30][i] ?? 5 })) });
const patchDetail = (b) => ({ ...b, price_age_s: 75, detail: { ...b.detail, quote: b.id === planId
  ? { at: null, kind: 'scan', age_s: null, session: 'regular', confirmed: false }
  : { at: '2026-10-15T12:00:01+00:00', kind: 'mid', age_s: 1.7, session: 'pre-market', confirmed: true } } });
const patchTickers = (b) => ({ ...b, tickers: b.tickers.map((t, i) => ({ ...t, price_age_s: i === 0 ? 90 : 5 })) });
const ROUTES = [[/\/api\/v1\/health$/, (b) => ({ ...b, market_active: true })], [/\/api\/v1\/market\/tape/, patchTape], [/\/api\/v1\/trades\?|\/api\/v1\/trades$/, patchList],
  [/\/api\/v1\/trades\/[^/?]+$/, patchDetail], [/\/api\/v1\/watchlist\/tickers$/, patchTickers]];

const ctx = await chromium.launchPersistentContext(PROFILE, { headless: false });
const page = ctx.pages()[0] ?? await ctx.newPage();
for (const [re, fn] of ROUTES) {
  await page.route((url) => re.test(url.pathname + (url.search ? '?' : '')), async (route) => {
    const res = await route.fetch();
    if (route.request().method() !== 'GET' || !res.ok()) return route.fulfill({ response: res });
    return route.fulfill({ response: res, json: fn(await res.json()) });
  });
}
const fresh = [];
page.on('request', (r) => { if (r.url().includes('/api/v1/') && r.method() === 'GET')
  fresh.push({ url: r.url().replace(base, ''), fresh: r.headers()['x-swingbot-fresh'] ?? null }); });

const PAGES = ['dashboard', 'watchlist', `trades/${tradeId}`, `trades/${tradeId}?tab=live`, `plans/${planId}`];
const report = [];
for (const width of [390, 768, 1440]) {
  await page.setViewportSize({ width, height: 900 });
  for (const path of PAGES) {
    await page.goto(`${base}/${path}`, { waitUntil: 'networkidle' });
    const slug = `${path.replace(/[/?=]/g, '_')}@${width}`;
    await page.screenshot({ path: join(out, `${slug}.png`), fullPage: true });
    report.push({ slug, ...(await page.evaluate(() => {
      const vw = window.innerWidth;
      const seen = (sel) => [...document.querySelectorAll(sel)].map((e) => {
        const r = e.getBoundingClientRect();
        return { text: e.textContent.trim(), h: Math.round(r.height), inView: r.right <= vw + 1 || !!e.closest('.track') };
      });
      return {
        sideways: document.scrollingElement.scrollWidth > vw + 1,
        spinners: document.querySelectorAll('.spinner, .veil, [class*="veil"]').length,
        ageHints: seen('.age-hint'), proxies: seen('.ctx.proxy'),
        alertPrice: [...document.querySelectorAll('dt, .created')].filter((e) => e.textContent.includes('Alert price'))
          .map((e) => (e.tagName === 'DT' ? e.nextElementSibling : e).textContent.trim()),
      };
    })) });
  }
}
// Fresh-header check: a reload marks, an in-app navigation does not.
fresh.length = 0;
await page.goto(`${base}/dashboard`, { waitUntil: 'networkidle' });
const firstLoad = fresh.splice(0);
await page.click('a[href="/watchlist"]');
await page.waitForLoadState('networkidle');
const afterNav = fresh.splice(0);
writeFileSync(join(out, 'report.json'), JSON.stringify({ report, firstLoad, afterNav }, null, 2));
const bad = report.filter((r) => r.sideways || r.spinners);
console.log(`shots ${report.length}, sideways/spinner ${bad.length}, firstLoad fresh ${firstLoad.every((r) => r.fresh === '1')}, afterNav unmarked ${afterNav.every((r) => r.fresh === null)}`);
await ctx.close();
```

Run: `node --check $WT/.superpowers/v171-probe.mjs`. Expected: no output.

- [ ] **Step 3: Start the local stack**
Each is long-running: start it with the Bash tool's `run_in_background`, never with `&`, and wait for its ready line.

```bash
python $R/admin_ui.py
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

The API runs from the main tree (`$R` has the `.env`; the worktree has none). It lacks the v171 API fields, which the probe adds. `:4123` is this repo's `ng serve` port; if taken, use `4124` everywhere below. Ready when `ng serve` prints `Local: http://localhost:4123/`. If `admin_ui.py` exits, stop and report `BLOCKED:` with its last log lines.

- [ ] **Step 4: Sign in once, then pick the ids**

```bash
node $WT/frontend/scripts/browse.mjs login --base http://localhost:4123
node $WT/frontend/scripts/browse.mjs api --base http://localhost:4123 --path "api/v1/trades?status=OPEN"
```
Tell the controller the browser window waits for the partner to type the local admin login (never scripted, asked for or stored). From the JSON, take one row `id` that is 16 characters (a trade) and one that is 36 characters with four dashes (a plan); with `?status=OPEN` empty, use `api/v1/trades` (any status). A missing kind is recorded as "not in the local data" in Step 7, never manufactured.

- [ ] **Step 5: Run the probe**

```bash
node $WT/.superpowers/v171-probe.mjs $WT/frontend http://localhost:4123 $WT/.superpowers/v171-shots <tradeId> <planId>
```
Expected: `shots 15, sideways/spinner 0, firstLoad fresh true, afterNav unmarked true`. In `report.json`: every Dashboard shot lists `ageHints` entries `1 min ago` (the 75 s row) and `30 s ago` (the 30 s row: past the Dashboard's 15 s window, inside the 60 s one); the Watchlist lists `1 min ago`; the trade detail `?tab=live` lists `1 min ago`; every page lists the tape's `S&P 500` proxy `SPY proxy` and `4 min ago` for VIX; the trade detail's `alertPrice` is `Bid/ask mid, 1.7 s to post, pre-market` and the plan page's `Alert price: Price not confirmed live`. Any `inView: false` entry outside the tape track is a defect.

- [ ] **Step 6: Judge the shots**
Open every PNG under `$WT/.superpowers/v171-shots/` with the Read tool. One line per shot: page, width, then yes/no for: a new element clipped, overlapping or wrapping onto a line of its own where its neighbours stay on one line; sideways scroll; a spinner, veil, skeleton or empty state that is not on the same page without the probe (compare against one `browse.mjs shots` run of the same paths without the probe if unsure); the tape tile with "SPY proxy" taller than its neighbours. At 390 px, the Dashboard live P&L cell may wrap the hint under the percentage; that is acceptable when the cell keeps its own width (ui-design.md: wrapping stated, no sideways scroll).

- [ ] **Step 7: Fix a defect, if one was found**
A defect is fixed in the file that renders the element (`ui/age-hint.ts` styles, `shell/tape/tape.ts`, or the page template from V171-32), with only the existing tokens and breakpoints. After each fix run the specs of that file (V171-31 Step 5 or V171-32 Step 6 command) and re-run Steps 5-6 for the affected pages, then commit:

```bash
git -C $WT add <the fixed files>
git -C $WT commit -m "fix(v171): <what the shots showed, in one line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Record the pass and stop the stack**
Stop both background processes. Under `## Progress` in `$WT/docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md` add: `V171-33 Playwright pass <date>: 15 shots at 390/768/1440 (Dashboard, Watchlist, trade <id> default and live tab, plan <id>); sideways 0, spinners 0; fresh header on first load yes, after navigation no; fixes: <commit ids or none>; missing local data: <none or which>.` Show the partner the shot folder path and ask for sign-off before committing (one question, recommended option first: "Looks right, commit the record").

```bash
git -C $WT add docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md
git -C $WT commit -m "docs(v171): V171-33 three-width Playwright pass recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V171-34: D9 report script: hourly counts by provider/kind/asker/outcome, baseline-vs-week comparison, success-table checks

**Model:** sonnet — a read-only report over V171-3's table and existing records

**Files:**
- Create: `scripts/reports/market_fetch_report.py`
- Create: `tests/infra/test_market_fetch_report.py`
- Create: `scripts/ops/v171_tape_sampler.py`
- Create: `scripts/ops/v171_report_cron.sh`, `scripts/ops/v171_tape_sampler_cron.sh`, `scripts/ops/install_v171_cron.sh`

**Interfaces:**
- Consumes: `market_shared_repo().count_rows(since, until, *, conn)` (V171-3) inside `swingbot.core.db.engine.transaction()`; `telemetry.TELEMETRY_PATH` rows (`at`, `tickers`, `errors`, `data_skips`, and `rebuild` from V171-20); `PlanStore().records()` (`swingbot/core/planning/plan_store.py:43`; plan dicts with `issued_at`, `created_at`, `plan_id`, `quote_age_s` from V171-17); `session.is_regular_session`, `session.is_tape_open` (`swingbot/core/market/session.py`); `tape.TAPE_FIXED`, `tape.read_tape` (V171-28).
- Produces (V171-36..V171-39 run these):
  - CLI `python scripts/reports/market_fetch_report.py --since YYYY-MM-DD --until YYYY-MM-DD [--baseline-since D --baseline-until D] [--tape-samples PATH] [--json OUT]` (dates UTC and inclusive). Runs from the repo or piped over stdin into the bot container (`docker compose exec -T bot python - <args> < scripts/reports/market_fetch_report.py`), so it never reads `__file__`. Prints one fixed-width table and the six check rows; exit 0 always (a report, not a gate).
  - Pure functions: `window(since: date, until: date) -> tuple[datetime, datetime]` (`[since 00:00 UTC, until + 1 day 00:00 UTC)`); `in_session_hour(hour: datetime) -> bool` (`is_regular_session(m) and is_tape_open(m)` with `m = hour + 30 min`); `calls_per_hour(rows: list[dict]) -> dict` (`hours`, `calls`, `mean`, `by_provider`, `by_kind`, `by_asker`, `by_outcome`, `days`); `scan_quality(rows: list[dict], start, end) -> dict` (`scans`, `tickers`, `errors`, `data_skips`, `per_ticker`); `quote_ages(plans: list[dict], start, end) -> dict` (`stamped`, `misses`, `max_s`, `miss_ids`); `rebuild_totals(rows, start, end) -> dict` (`kept`, `dropped`, `misses`); `blank_tape(samples: list[dict], start, end) -> dict` (`samples`, `session_minutes`, `coverage`, `blank_minutes`, `errors`); `checks(week: dict, baseline: dict | None) -> list[dict]` (six rows `{check, threshold, value, verdict}`, verdict `PASS`/`MISS`/`UNMEASURED`); `build_report(*, since, until, baseline=None, count_rows, telemetry_rows, plans, samples) -> dict`.
  - `scripts/ops/v171_tape_sampler.py --out PATH [--until-utc HH:MM]`: one JSON line per minute while it runs, `{"at", "in_session", "blank": [symbols] | null, "error": str | null}`; `blank_symbols(entries: dict, symbols) -> list[str]`.
  - `scripts/ops/install_v171_cron.sh report LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL]` and `... sampler START END`: idempotent crontab lines; each job appends to `logs/v171_<label>_cron.log` / `logs/v171_tape_samples.jsonl`, writes `logs/v171_<label>.json`, and removes its own line after its last day.

**Definitions, fixed now, before any count exists (Success table, never retuned):**
- Provider calls = counter rows with outcome `fetched` or `failed`; `hit`, `shared-wait` and `budget-deferred` made no call. The layer counts per symbol in both `count` and `on` mode, so the baseline and the week are counted alike. `mean` = calls / in-session hours that have at least one row (an hour with the bot down has no rows and drops out of both). `days` = per UTC date, the number of in-session hours with rows. `by_provider`, `by_kind` and `by_asker` sum provider calls; `by_outcome` sums every outcome (hits included); all of them over in-session hours only.
- Quote-age miss = a plan whose `issued_at` (else `created_at`) is in the window, `quote_age_s` is not None and `quote_age_s > QUOTE_AGE_LIMIT_S`, where `QUOTE_AGE_LIMIT_S = 5.0` is a module constant, never read from config.
- Errors per ticker = (Σ `errors` + Σ `data_skips`) / Σ `tickers` over telemetry rows in the window that carry `tickers` (scan rows; deploy markers carry none).
- Blank tape minute = an in-session sample whose `blank` list is non-empty. `coverage` = in-session samples / in-session minutes of the window (each minute checked with the same two session functions).
- Verdicts: `quote_age` PASS when `stamped > 0` and `misses == 0`, MISS when `misses > 0`, else UNMEASURED; `blank_tape` MISS when `blank_minutes > 0`, PASS when 0 with `coverage >= 0.95` and no sample `error`, else UNMEASURED; `errors_per_ticker` PASS when the week's value <= the baseline's, MISS when above, UNMEASURED without a baseline or scans; `calls_per_hour` PASS when the week's mean <= 0.5 × the baseline's mean, MISS when above, UNMEASURED when either mean is None; `provider_429s` and `delta_parity` always UNMEASURED here, value `"see V171-39"` (measured from the logs and a parity run).

- [ ] **Step 1: Write the failing tests**
Create `tests/infra/test_market_fetch_report.py`:

```python
"""v171 D9: the success-week report and the tape sampler (scripts, loaded by path)."""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rpt = _load("scripts/reports/market_fetch_report.py", "market_fetch_report")
smp = _load("scripts/ops/v171_tape_sampler.py", "v171_tape_sampler")

# Thursday 2026-10-15: 14:00 UTC = 10:00 ET (in session); 03:00 UTC is not.
H_IN = datetime(2026, 10, 15, 14, tzinfo=timezone.utc)
H_OUT = datetime(2026, 10, 15, 3, tzinfo=timezone.utc)
START, END = rpt.window(date(2026, 10, 15), date(2026, 10, 15))


def _count(hour, outcome, n, provider="alpaca", kind="quote", asker="STOP_MONITOR"):
    return {"hour": hour, "provider": provider, "kind": kind, "asker": asker, "outcome": outcome, "n": n}


def test_window_is_inclusive_utc_days():
    assert (START, END) == (datetime(2026, 10, 15, tzinfo=timezone.utc), datetime(2026, 10, 16, tzinfo=timezone.utc))


def test_session_hours_use_the_bucket_midpoint():
    assert rpt.in_session_hour(H_IN) and rpt.in_session_hour(H_IN.replace(hour=13))   # 09:00 ET bucket, midpoint 09:30
    assert not rpt.in_session_hour(H_OUT) and not rpt.in_session_hour(H_IN.replace(hour=20))
    assert not rpt.in_session_hour(datetime(2026, 10, 17, 14, tzinfo=timezone.utc))  # Saturday


def test_calls_count_only_provider_outcomes_in_session_hours():
    rows = [_count(H_IN, "fetched", 10), _count(H_IN, "failed", 2), _count(H_IN, "hit", 50),
            _count(H_IN, "shared-wait", 5), _count(H_IN, "budget-deferred", 3),
            _count(H_IN + timedelta(hours=1), "fetched", 4, provider="yfinance", asker="ADMIN_PAGE"),
            _count(H_OUT, "fetched", 99)]
    got = rpt.calls_per_hour(rows)
    assert (got["hours"], got["calls"], got["mean"]) == (2, 16, 8.0)
    assert got["by_provider"] == {"alpaca": 12, "yfinance": 4}
    assert got["by_outcome"]["hit"] == 50 and got["days"] == {"2026-10-15": 2}


def test_calls_mean_is_none_without_session_rows():
    assert rpt.calls_per_hour([_count(H_OUT, "fetched", 3)])["mean"] is None


def test_scan_quality_skips_rows_without_tickers():
    rows = [{"at": "2026-10-15T14:05:00+00:00", "tickers": 100, "errors": 1, "data_skips": 1},
            {"at": "2026-10-15T14:06:00+00:00", "type": "deploy"},
            {"at": "2026-10-14T14:05:00+00:00", "tickers": 100, "errors": 50, "data_skips": 0}]
    assert rpt.scan_quality(rows, START, END) == {"scans": 1, "tickers": 100, "errors": 1,
                                                  "data_skips": 1, "per_ticker": 0.02}


def test_quote_age_misses_use_the_fixed_five_seconds():
    plans = [{"plan_id": "a", "issued_at": "2026-10-15T14:00:00+00:00", "quote_age_s": 5.0},
             {"plan_id": "b", "issued_at": "2026-10-15T15:00:00+00:00", "quote_age_s": 5.01},
             {"plan_id": "c", "created_at": "2026-10-15T15:00:00+00:00", "quote_age_s": None},
             {"plan_id": "d", "issued_at": "2026-10-14T15:00:00+00:00", "quote_age_s": 9.0}]
    assert rpt.QUOTE_AGE_LIMIT_S == 5.0
    assert rpt.quote_ages(plans, START, END) == {"stamped": 2, "misses": 1, "max_s": 5.01, "miss_ids": ["b"]}


def test_rebuild_totals_sum_the_telemetry_key():
    rows = [{"at": "2026-10-15T14:05:00+00:00", "rebuild": {"kept": 2, "dropped": 1, "misses": 0}},
            {"at": "2026-10-15T14:10:00+00:00", "rebuild": {"kept": 1, "dropped": 0, "misses": 1}},
            {"at": "2026-10-15T14:15:00+00:00", "tickers": 3}]
    assert rpt.rebuild_totals(rows, START, END) == {"kept": 3, "dropped": 1, "misses": 1}


def _samples(n, blank=(), error=None, start=datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)):
    return [{"at": (start + timedelta(minutes=i)).isoformat(), "in_session": True,
             "blank": None if error else list(blank), "error": error} for i in range(n)]


def test_blank_tape_needs_coverage_to_pass():
    full = rpt.blank_tape(_samples(390), START, END)
    assert (full["session_minutes"], full["blank_minutes"], full["coverage"]) == (390, 0, 1.0)
    assert rpt.blank_tape(_samples(10, blank=["^VIX"]), START, END)["blank_minutes"] == 10


def _week(**over):
    base = {"calls": {"mean": 100.0}, "scan": {"scans": 10, "per_ticker": 0.01},
            "quotes": {"stamped": 3, "misses": 0},
            "tape": {"blank_minutes": 0, "coverage": 0.99, "errors": 0}}
    base.update(over)
    return base


def _verdicts(week, baseline):
    return {c["check"]: c["verdict"] for c in rpt.checks(week, baseline)}


def test_checks_against_the_fixed_thresholds():
    baseline = {"calls": {"mean": 200.0}, "scan": {"scans": 10, "per_ticker": 0.01}}
    assert _verdicts(_week(), baseline) == {
        "quote_age": "PASS", "blank_tape": "PASS", "provider_429s": "UNMEASURED",
        "errors_per_ticker": "PASS", "calls_per_hour": "PASS", "delta_parity": "UNMEASURED"}
    assert _verdicts(_week(calls={"mean": 100.01}), baseline)["calls_per_hour"] == "MISS"
    assert _verdicts(_week(scan={"scans": 10, "per_ticker": 0.011}), baseline)["errors_per_ticker"] == "MISS"
    assert _verdicts(_week(quotes={"stamped": 3, "misses": 1}), baseline)["quote_age"] == "MISS"
    assert _verdicts(_week(quotes={"stamped": 0, "misses": 0}), baseline)["quote_age"] == "UNMEASURED"
    assert _verdicts(_week(tape={"blank_minutes": 0, "coverage": 0.94, "errors": 0}), baseline)["blank_tape"] == "UNMEASURED"
    assert _verdicts(_week(tape={"blank_minutes": 1, "coverage": 0.5, "errors": 0}), baseline)["blank_tape"] == "MISS"
    assert _verdicts(_week(), None)["calls_per_hour"] == "UNMEASURED"


def test_build_report_wires_the_loaders():
    out = rpt.build_report(since=date(2026, 10, 15), until=date(2026, 10, 15), baseline=None,
                           count_rows=lambda s, u: [_count(H_IN, "fetched", 6)],
                           telemetry_rows=[], plans=[], samples=[])
    assert out["week"]["calls"]["calls"] == 6 and out["baseline"] is None
    assert [c["check"] for c in out["checks"]] == ["quote_age", "blank_tape", "provider_429s",
                                                   "errors_per_ticker", "calls_per_hour", "delta_parity"]


def test_sampler_counts_a_symbol_with_neither_price_nor_change_as_blank():
    entry = lambda price, chg: SimpleNamespace(price=price, change_pct=chg)
    entries = {"^GSPC": entry(None, 0.4), "^NDX": entry(20000.0, None), "^DJI": entry(None, None)}
    assert smp.blank_symbols(entries, ("^GSPC", "^NDX", "^DJI", "^VIX")) == ["^DJI", "^VIX"]
```

Run: `python $WT/scripts/dev/testrun.py file tests/infra/test_market_fetch_report.py`. Expected: FAIL at collection (`FileNotFoundError` for `scripts/reports/market_fetch_report.py`).

- [ ] **Step 2: Implement `scripts/reports/market_fetch_report.py`**
Module docstring: what it measures, the definitions above (copied as the source of record), and the two run forms. Stdlib plus `swingbot` imports only inside the loader functions (`_load_counts(start, end)` via `transaction()` + `market_shared_repo().count_rows`, `_load_telemetry()` reading `telemetry.TELEMETRY_PATH` line by line and skipping unparseable lines, `_load_plans()` = `PlanStore().records()`, `_load_samples(path)` = JSON lines, `[]` when the file is missing), so the pure functions import cleanly in the test. Timestamps parse with `datetime.fromisoformat` and compare as aware UTC. `checks` builds each row through one small helper per check (`_quote_check`, `_tape_check`, `_ratio_check`), so every function stays under complexity 15. `build_report` returns `{"since", "until", "week": {"calls", "scan", "quotes", "rebuild", "tape"}, "baseline": {"calls", "scan"} | None, "checks"}`; `main(argv=None)` parses the flags, calls the loaders and `build_report`, prints the table (`by_provider`, `by_kind`, `by_asker`, `by_outcome`, `days`, then the six checks), writes `--json` when given, returns 0. End with `if __name__ == "__main__": sys.exit(main())` (true when piped over stdin too).

- [ ] **Step 3: Implement `scripts/ops/v171_tape_sampler.py`**
`blank_symbols(entries, symbols)` returns, in `symbols` order, every symbol whose entry is missing or has both `price` and `change_pct` None (a proxy row has `change_pct`, so it is not blank). `sample(now) -> dict`: `in_session = is_regular_session(now) and is_tape_open(now)`; when in session, `blank = blank_symbols(tape.read_tape(list(tape.TAPE_FIXED)), tape.TAPE_FIXED)`, an exception gives `blank: None, error: f"{type(exc).__name__}: {exc}"`; out of session `blank: []`. `main(argv=None)`: `--out` (required), `--until-utc` (default `21:15`); loop: append `json.dumps(sample(now))` plus newline to `--out` (open, append, close each time, so a killed run loses at most one line), sleep to the next whole minute, stop once UTC time passes `--until-utc`. Imports of `swingbot` sit inside `sample` and `main`, so the test loads the module without them.

- [ ] **Step 4: Run the tests**
Run: `python $WT/scripts/dev/testrun.py file tests/infra/test_market_fetch_report.py`. Expected: PASS (11 tests). Then `python -m radon cc -s -n C $WT/scripts/reports/market_fetch_report.py $WT/scripts/ops/v171_tape_sampler.py`: no output (nothing at C or worse).

- [ ] **Step 5: Write the cron wrappers** (pattern: `scripts/ops/v106_soak_cron.sh`, `install_v106_soak_cron.sh`)

`scripts/ops/v171_report_cron.sh`:

```bash
#!/usr/bin/env bash
# One run of the v171 D9 report for one window (plan v171 V171-37..V171-39).
# Pipes scripts/reports/market_fetch_report.py into the bot container over
# stdin. Appends to logs/v171_<LABEL>_cron.log and rewrites
# logs/v171_<LABEL>.json; after the window's last day it writes FINAL and
# removes its own crontab line. Usage: LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL]
set -uo pipefail
LABEL=${1:?label}; SINCE=${2:?since}; UNTIL=${3:?until}; BASE_SINCE=${4:-}; BASE_UNTIL=${5:-}
cd /opt/swing-bot
LOG=/opt/swing-bot/logs/v171_${LABEL}_cron.log
ARGS=(--since "$SINCE" --until "$UNTIL" --json "logs/v171_${LABEL}.json" --tape-samples logs/v171_tape_samples.jsonl)
[ -n "$BASE_SINCE" ] && ARGS+=(--baseline-since "$BASE_SINCE" --baseline-until "$BASE_UNTIL")
{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    /usr/bin/docker compose exec -T bot python - "${ARGS[@]}" < scripts/reports/market_fetch_report.py
} >> "$LOG" 2>&1
if [ ! "$(date -u +%Y-%m-%d)" \< "$UNTIL" ]; then
    crontab -l 2>/dev/null | grep -vF "v171_report_cron.sh $LABEL " | crontab -
    echo "FINAL: window $SINCE..$UNTIL closed; crontab line removed" >> "$LOG"
fi
```

`scripts/ops/v171_tape_sampler_cron.sh` (same header style): `START END`; exits 0 when today (UTC) is before `START`; runs `/usr/bin/docker compose exec -T bot python - --out logs/v171_tape_samples.jsonl --until-utc 21:15 < scripts/ops/v171_tape_sampler.py >> logs/v171_tape_sampler.log 2>&1`; when today is not before `END`, removes every crontab line containing `v171_tape_sampler_cron.sh` and logs `one-shot done`.

`scripts/ops/install_v171_cron.sh`: `MODE=${1:?report|sampler}`; `report` takes `LABEL SINCE UNTIL [BASE_SINCE BASE_UNTIL]` and installs `15 21 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v171_report_cron.sh <args>` under the marker `# v171 report <LABEL> (install_v171_cron.sh)` (21:15 UTC is after the US close in summer and winter time); `sampler` takes `START END` and installs `20 13 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v171_tape_sampler_cron.sh START END` under `# v171 tape sampler (install_v171_cron.sh)` (13:20 UTC is before the earliest open, 13:30 UTC; the sampler itself samples only in session). Each mode first drops its own old marker and line (`grep -vF`), so a re-run replaces, never duplicates, then prints `crontab -l`. Run on the VM as `bash scripts/ops/ssh-hetzner.sh "bash -s -- report baseline 2026-10-19 2026-10-23" < scripts/ops/install_v171_cron.sh`.

Run: `bash -n $WT/scripts/ops/v171_report_cron.sh && bash -n $WT/scripts/ops/v171_tape_sampler_cron.sh && bash -n $WT/scripts/ops/install_v171_cron.sh` then `git -C $WT update-index --chmod=+x scripts/ops/v171_report_cron.sh scripts/ops/v171_tape_sampler_cron.sh scripts/ops/install_v171_cron.sh` after `git add`.
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/reports/market_fetch_report.py scripts/ops/v171_tape_sampler.py scripts/ops/v171_report_cron.sh scripts/ops/v171_tape_sampler_cron.sh scripts/ops/install_v171_cron.sh tests/infra/test_market_fetch_report.py
git -C $WT update-index --chmod=+x scripts/ops/v171_report_cron.sh scripts/ops/v171_tape_sampler_cron.sh scripts/ops/install_v171_cron.sh
git -C $WT commit -m "feat(v171): D9 market-fetch report, tape sampler and their VM crons

Success-table definitions fixed before any count exists: provider calls are
fetched+failed per in-session hour, quote-age misses over a fixed 5 s, blank
tape minutes from a once-a-minute sampler with 95 % coverage.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V171-35: Full Python suite, frontend spec run, radon check

**Model:** haiku — runs commands, no code

**Files:** none (a failure is fixed in the file of the task that owns it, then re-run alone).

- [ ] **Step 1: Full Python suite, once**
Dispatch the `test-runner` subagent (so the output stays out of this context) for `python $WT/scripts/dev/testrun.py full`.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Each failed test is fixed in its owning task's files and re-run alone (`python $WT/scripts/dev/testrun.py file <test>`), never by re-running the whole suite.

- [ ] **Step 2: Frontend, once**
Run: `npm --prefix $WT/frontend exec -- ng test --watch=false` then `npm --prefix $WT/frontend run build`. Expected: every spec passes; the production build completes with no error (CI runs the same two, `docs/deploy/DEPLOY_HETZNER.md` § How it works).

- [ ] **Step 3: Complexity and syntax**

```bash
git -C $WT diff --name-only main...HEAD -- '*.py' | sed "s|^|$WT/|" | xargs python -m py_compile
git -C $WT diff --name-only main...HEAD -- '*.py' | sed "s|^|$WT/|" | xargs python -m radon cc -s -n C
```
Expected: `py_compile` prints nothing. `radon` lists only the legacy functions named in the index's Global Constraints (Complexity), each at or below its listed grade and score (`_scan_one` lower than E(36)); any other function at C (15) or worse is a defect, split per `docs/claude/code-complexity.md` in its owning task's files, then re-run that task's narrow test.

- [ ] **Step 4: Record**
Under `## Progress` in `$WT/docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md`: `V171-35 <date>: full suite <passed> passed, 0 failed, 0 xfailed; ng test <n> passed; ng build ok; radon: legacy list only.`

```bash
git -C $WT add docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md
git -C $WT commit -m "docs(v171): V171-35 full suite, frontend and radon green

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 7 — Production rollout (on `main`, after the merge, strictly in order)

Every task here uses the `mirror-prod` skill, connects only through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin piped for scripts), edits the VM's `.env` only with `python3 scripts/ops/env_set.py KEY value` (in place; a `sed -i` rename leaves the containers on the old file) and then `docker compose restart bot admin` (the admin has no reload hook), and restarts only outside the regular session (after 20:15 UTC in summer time, 21:15 UTC in winter time, or on a weekend). Berlin time is UTC+2 until 2026-10-25, UTC+1 after (Git Bash has no timezone data: compute it from `date -u`). Every production change is mirrored into the repo and committed before the task counts as done.

### Task V171-36: Production: merge, deploy with `MARKETDATA_LAYER=count` (other flags off), migration applied, counts flowing

**Model:** sonnet — production change under `mirror-prod`, verified by read-back

**Files:**
- Modify: `.env.example` (one comment line above the `MARKETDATA_LAYER=` line V171-1 added)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (new subsection `### v171 market-data layer rollout` at the end of `## Updating settings without a code deploy`)

Every push to `main` runs the deploy pipeline and restarts both containers (`.github/workflows/deploy.yml`), so every push in Phase 7 happens outside the regular session.

- [ ] **Step 1: Merge and push**
Use the `worktree-lifecycle` skill: check for concurrent sessions on `main`, merge branch `2026-10-16-v171-shared-market-data-fetch` into `main` in `$R` (no full suite after the merge: V171-35 ran it), push outside the session, and follow the run with `gh run watch`. Expected: every job green, `deploy` done.

- [ ] **Step 2: Read the deploy back (flags at their code defaults)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps && docker compose exec -T bot alembic current"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot import config as c; print(c.MARKETDATA_LAYER, c.DAILY_DELTA_FETCH, c.PLAN_REBUILD_ENABLED, c.TAPE_SHARED_ENABLED)'"
```
Expected: both containers `healthy`; `v171_001 (head)`; `off False False False`. Then the slash-command sync check (`docs/deploy/DEPLOY_HETZNER.md` § After every deploy or rollback). Anything else: stop, roll back the image (`DEPLOY_HETZNER.md` § Rolling back) and report `BLOCKED:` with the output.

- [ ] **Step 3: Switch the layer to count-only (outside the session)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py MARKETDATA_LAYER count && docker compose restart bot admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in bot admin; do docker compose exec -T \$s python -c 'from swingbot import config; print(config.MARKETDATA_LAYER)'; done"
```
Expected: `count` twice. Record the UTC time of the switch.

- [ ] **Step 4: Counts flow from every process, and count mode never serves from cache**
Wait three minutes (the trade monitor ticks every 60 s around the clock and the counters flush every 60 s), open one admin page, then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -c \"select provider, kind, asker, outcome, sum(n) from market_fetch_counts where hour >= now() - interval '2 hours' group by 1,2,3,4 order by 1,2,3,4\""
```
Expected: rows for asker `STOP_MONITOR` (bot) and an `ADMIN_*` asker (admin); outcomes only `fetched` or `failed` (pass-through: a `hit`, `shared-wait` or `budget-deferred` row means count mode is serving from the cache, which is a defect: switch back to `off` with Step 3's commands and report `BLOCKED:`). `SCAN` and `BACKGROUND` rows appear with the next scan and refresh; the first daily baseline report (V171-37) confirms them.

- [ ] **Step 5: Mirror and commit**
`.env.example`, above `MARKETDATA_LAYER=`: `# Production: count since <UTC date> (v171 V171-36); on after the baseline week (V171-38).` `DEPLOY_HETZNER.md`, new subsection `### v171 market-data layer rollout`: a table of the four flags (`MARKETDATA_LAYER`, `DAILY_DELTA_FETCH`, `PLAN_REBUILD_ENABLED`, `TAPE_SHARED_ENABLED`) with their production value and the date set, then the rollback order in three lines (a flag off with `env_set.py` + `docker compose restart bot admin`; the previous image per § Rolling back; `scripts/ops/rollback_to.sh` with `--dry-run` first, only for damaged data), and one line that the `v171_001` tables stay on every rollback.

```bash
git -C $R add .env.example docs/deploy/DEPLOY_HETZNER.md
git -C $R commit -m "ops(v171): production runs MARKETDATA_LAYER=count (mirror of the live .env)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Push outside the session.

### Task V171-37: Production: five in-session trading days of baseline counts recorded

**Model:** haiku — runs the report over fixed dates and records it

**Files:**
- Create: `docs/superpowers/results/2026-10-16-v171-baseline-week.md`

**The baseline window, fixed before it starts (D9):** `START` = the first NYSE trading day that begins after V171-36 Step 3's switch; `END` = the fifth trading day from `START`, inclusive (skip NYSE full-day closures). A day counts only when its `days` entry in the report has at least 5 of its 7 in-session hours with rows; a day with fewer (bot or database down) is replaced by the next trading day, by re-running Step 1 with `END` moved one trading day. Nothing else about the window may change after data exists.

- [ ] **Step 1: Install the baseline cron on the VM**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- report baseline START END" < scripts/ops/install_v171_cron.sh
```
with the two dates written in. Expected: the printed crontab holds `# v171 report baseline (install_v171_cron.sh)` and `15 21 * * 1-5 /bin/bash /opt/swing-bot/scripts/ops/v171_report_cron.sh baseline START END`. Tell the partner: the report runs at 21:15 UTC each weekday, the log is `logs/v171_baseline_cron.log` on the VM, and the final run is END's.

- [ ] **Step 2: After END, read the final run** (the next session, which reads this log first)

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && tail -n 60 logs/v171_baseline_cron.log && cat logs/v171_baseline.json"
```
Expected: the last block ends with `FINAL: window START..END closed`. Check, in this order: every `days` entry has at least 5 in-session hours (else apply the replacement rule above and wait); `by_asker` holds `STOP_MONITOR`, `SCAN`, `BACKGROUND` and at least one `ADMIN_*`; `by_outcome` holds only `fetched` and `failed`; `calls.mean` and `scan.per_ticker` are numbers. A missing asker means a consumer bypasses the layer's counting: report it as a defect (`BLOCKED:`) before V171-38, never switch on over it.

- [ ] **Step 3: Record and commit**
Create `docs/superpowers/results/2026-10-16-v171-baseline-week.md`: title, the window and the switch time from V171-36, the replacement days if any, the report's table (`calls.mean`, `calls.calls`, `calls.hours`, `by_provider`, `by_kind`, `by_asker`, `by_outcome`, `days`, `scan.scans`, `scan.tickers`, `scan.errors`, `scan.data_skips`, `scan.per_ticker`), the full JSON in a fenced block, and the two baseline numbers the success check compares against, stated once: `calls_per_hour baseline = <mean>` (the success threshold is half of it) and `errors_per_ticker baseline = <per_ticker>`. Also update `## Progress` in the index.

```bash
git -C $R add docs/superpowers/results/2026-10-16-v171-baseline-week.md docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md
git -C $R commit -m "docs(v171): D9 baseline week START..END recorded (count-only)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Push outside the session.

### Task V171-38: Production: switch on (layer `on`, then `DAILY_DELTA_FETCH`, `PLAN_REBUILD_ENABLED`, `TAPE_SHARED_ENABLED`, one at a time with a read-back between)

**Model:** sonnet — staged production flag flips with checks and rollback steps

**Files:**
- Modify: `.env.example` (the production comment lines above the four flags)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (the `### v171 market-data layer rollout` table from V171-36)

**Staging, fixed now:** one flag per trading day, each flipped outside the session after the previous one's read-back passed: day A `MARKETDATA_LAYER=on`, day B `DAILY_DELTA_FETCH=true`, day C `PLAN_REBUILD_ENABLED=true`, day D `TAPE_SHARED_ENABLED=true`. A failed read-back turns that flag back off (and only that one) and stops the staging until the cause is fixed; the earlier flags stay on. Every flip uses the same two commands, with `KEY` and `VALUE` written in:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py KEY VALUE && docker compose restart bot admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && for s in bot admin; do docker compose exec -T \$s python -c 'from swingbot import config; print(config.KEY)'; done"
```
Expected: the new value twice. Rollback of one flag: the same two commands with the off value (`off` / `false`).

- [ ] **Step 1: Install the staging report cron** (before the day-A flip)

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- report staging A D BASE_SINCE BASE_UNTIL" < scripts/ops/install_v171_cron.sh
```
with day A, day D and the baseline window from V171-37 written in. Each weekday's 21:15 UTC run lands in `logs/v171_staging_cron.log`; each read-back below starts from that log (the next session reads it first) and adds the spot checks named.

- [ ] **Step 2: Day A, `MARKETDATA_LAYER=on`; read back after day A's session**
Expected in the log: `by_outcome` now holds `hit` (and usually `shared-wait`); provider calls per in-session hour below the baseline's; `failed` not above the baseline's share. Spot checks: `grep -c "fail open" logs/bot.log logs/admin.log` (exact log file names: `ls logs/` on the VM) is a handful, not a storm (one warning per minute per operation and error class is the cap, so a storm is hundreds); the trade monitor ticked every minute (`grep -c trade_monitor` over the session hours); `grep -ciE "429|too many requests"` on both logs is 0. A breach of any: `MARKETDATA_LAYER=count` and stop.

- [ ] **Step 3: Day B, `DAILY_DELTA_FETCH=true`; read back after day B's session**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && ls market_data/daily_alpaca | head && ls market_data/daily_alpaca/*.csv | wc -l && ls market_data/daily_alpaca/*.meta.json | wc -l && tail -n 3 data/scan_telemetry.jsonl"
```
Expected: one CSV and one `.meta.json` per Alpaca-eligible watchlist symbol, none for `XAUUSD`/`XAGUSD`; telemetry `errors` and `data_skips` per scan at the baseline level; the log's `scan.per_ticker` not above the baseline's. Breach: `DAILY_DELTA_FETCH=false` (files stay valid for the flag-off path, spec Rollout) and stop.

- [ ] **Step 4: Day C, `PLAN_REBUILD_ENABLED=true`; read back after day C's session**
Expected: the log's `rebuild` totals are present (`kept`, `dropped`, `misses`) and `quotes.stamped` equals the number of main-scan and SHORT plans posted that day; `quotes.misses` is 0; any posted alert in Discord shows the quote line (`Price: ...` or `Price not confirmed live (scan price)`). `dropped` reasons: `grep "not posted -- rebuild:" logs/bot.log` lists each with its reason. A miss here is not yet a success-table verdict (the week has not started) but it is a defect to investigate before day D: `PLAN_REBUILD_ENABLED=false` while it is.

- [ ] **Step 5: Day D, `TAPE_SHARED_ENABLED=true`; read back after day D's session**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -c 'from swingbot.core.marketdata.shared import tape; print(tape.read_tape(list(tape.TAPE_FIXED)))'"
```
Expected: four entries, each with a price or (proxy) a change %, ages under 180 s during the session; the admin tape at 390, 768 and 1440 px shows the four indices, with a "proxy" label only where Yahoo was blank (`node frontend/scripts/browse.mjs shots --out .superpowers/v171-prod --widths 390,768,1440 --path dashboard`, the partner signs in; read the PNGs). `grep -c "possibly delisted" logs/admin.log` far below the pre-v171 bursts. Breach: `TAPE_SHARED_ENABLED=false` and stop.

- [ ] **Step 6: Start the success week**
The success window, fixed now: `S` = the first trading day after day D, `E` = the fifth trading day from `S`, inclusive; same replacement rule as the baseline (a day with fewer than 5 of 7 in-session hours with rows is replaced by the next trading day). Install both crons:

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s -- report success S E BASE_SINCE BASE_UNTIL" < scripts/ops/install_v171_cron.sh
bash scripts/ops/ssh-hetzner.sh "bash -s -- sampler S E" < scripts/ops/install_v171_cron.sh
```
Expected: `crontab -l` holds the `success` report line and the tape sampler line (the staging line removed itself after day D). Tell the partner: the week runs S..E, logs `logs/v171_success_cron.log`, `logs/v171_tape_samples.jsonl` and `logs/v171_tape_sampler.log` on the VM; the verdict is read in V171-39 after E.

- [ ] **Step 7: Mirror and commit** (after each flip that stays on, or once after Step 6 with every date)

Update the `.env.example` comment lines above the four flags (`# Production: on since <UTC date> (v171 V171-38)`) and the `DEPLOY_HETZNER.md` rollout table (value and date per flag, plus any flag turned back off and why). Update `## Progress` in the index with days A-D and the success window.

```bash
git -C $R add .env.example docs/deploy/DEPLOY_HETZNER.md docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md
git -C $R commit -m "ops(v171): market-data layer, delta fetch, plan rebuild and shared tape on in production

Mirror of the live .env; success week S..E scheduled on the VM.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Push outside the session.

### Task V171-39: Production: one-week success check against the spec's table; record pass or miss

**Model:** sonnet — judges six fixed thresholds, never retuned

**Files:**
- Create: `docs/superpowers/results/2026-10-16-v171-success-week.md`
- Modify: `docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md` (`## Progress`, `## What follows`)
- Scratch, never committed: `.superpowers/v171-parity.py`

The thresholds are the spec's `## Success` table, copied, never changed: posted plans with quote age > 5 s = 0; blank tape minutes in session = 0; Alpaca or yfinance 429s = 0; scan errors + data skips per ticker not above the baseline; provider calls per hour in session at most half the baseline; cache+delta vs full download bar-for-bar equal on every check. Measurement definitions are V171-34's. A miss is recorded as a miss; a row that could not be measured is recorded as UNMEASURED, never as a pass.

- [ ] **Step 1: Read the week** (after E's 21:15 UTC run; the next session reads these first)

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && tail -n 80 logs/v171_success_cron.log && cat logs/v171_success.json && tail -n 5 logs/v171_tape_sampler.log && crontab -l"
```
Expected: the last block ends with `FINAL: window S..E closed`; `crontab -l` no longer holds either v171 line. Apply the replacement rule (V171-38 Step 6) to `days` first; if a day was replaced, wait for the moved END and start again. Copy the four measured rows (`quote_age`, `blank_tape`, `errors_per_ticker`, `calls_per_hour`) with their values and verdicts.

- [ ] **Step 2: 429s in the window**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && ls -la logs/ && for d in S_DATES; do grep -hiE '429|too many requests' logs/*.log* 2>/dev/null | grep \"^\$d\" | grep -viE 'discord|message' ; done | sort | uniq -c"
```
with `S_DATES` the window's dates (`2026-..-.. 2026-..-..`, one per trading day) and the log line date prefix confirmed from `ls`/`head` first (adjust the `^$d` match to the log's timestamp format). Discord 429s are out of scope (spec Non-goals) and excluded by the `discord|message` filter; read every remaining line. Verdict: PASS when no Alpaca or yfinance 429 remains, MISS otherwise (quote the lines); UNMEASURED if the logs for a window day have rotated away.

- [ ] **Step 3: Delta parity on production** (outside the session, a weekend if possible)

Write `$R/.superpowers/v171-parity.py`:

```python
"""v171 Success row 6: each daily cache file (its own basis) vs a fresh full download, bar for bar.
Read-only: nothing is written to market_data. Runs in the bot container over stdin."""
import pandas as pd

from swingbot import config
from swingbot.core.marketdata import daily_delta, spot_metals, yf_safe
from swingbot.core.marketdata.adjustments import DELTA_OVERLAP_TOLERANCE
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker
from swingbot.core.marketdata.watchlist import load_watchlist

COLS = ["Open", "High", "Low", "Close", "Volume"]


def norm(df):
    df = df[COLS].astype(float).copy()
    idx = pd.DatetimeIndex(df.index)
    df.index = (idx.tz_convert(None) if idx.tz is not None else idx).normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def compare(cached, fresh):
    c, f = norm(cached), norm(fresh)
    end = f.index.max() - pd.Timedelta(days=3)        # skip the forming bar and the SIP-delayed edge
    start = max(c.index.min(), f.index.min())
    c, f = c[(c.index >= start) & (c.index <= end)], f[(f.index >= start) & (f.index <= end)]
    common = c.index.intersection(f.index)
    rel = ((c.loc[common] - f.loc[common]).abs() / f.loc[common].abs().clip(lower=1e-12)).max().max()
    return len(f.index.difference(c.index)), len(c.index.difference(f.index)), float(rel)


def fresh_frames(symbols):
    alp = [s for s in symbols if daily_delta.basis_for(s) == daily_delta.BASIS_ALPACA]
    out = {}
    with router.asker_scope(Asker.BACKGROUND):
        for sym, df in (router.daily_bars(alp, config.DEFAULT_HISTORY_PERIOD, lambda g: {}) or {}).items():
            if df is not None and df.attrs.get("source") == "alpaca":
                out[sym] = df
        for sym in [s for s in symbols if s not in alp]:
            got = yf_safe.download([sym], period="max", auto_adjust=True, actions=True,
                                   group_by="ticker", progress=False)
            if got is not None and not got.empty:
                out[sym] = got[sym].dropna(how="all")
    return out


_, symbols = spot_metals.split_spot(load_watchlist())
fresh = fresh_frames(symbols)
fails, unmeasured = [], []
for sym in symbols:
    cached = daily_delta.read_daily(sym)
    if cached is None or sym not in fresh:
        unmeasured.append(sym)
        continue
    missing, extra, rel = compare(cached, fresh[sym])
    ok = missing == 0 and extra == 0 and rel <= DELTA_OVERLAP_TOLERANCE
    print(f"{sym:8} {daily_delta.basis_for(sym):22} missing={missing} extra={extra} max_rel={rel:.2e} {'OK' if ok else 'FAIL'}", flush=True)
    if not ok:
        fails.append(sym)
verdict = "MISS" if fails else ("UNMEASURED" if unmeasured else "PASS")
print(f"PARITY {verdict}: {len(symbols) - len(fails) - len(unmeasured)} equal, fails={fails}, unmeasured={unmeasured}")
```

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < $R/.superpowers/v171-parity.py`. Expected: one line per symbol and a final `PARITY <verdict>` line. `DELTA_OVERLAP_TOLERANCE` (1e-4 relative) is the spec's rounding-noise bound; a real re-adjustment is far above it. An unmeasured symbol (fetch failed) is retried once on the next day before the verdict stays UNMEASURED. **A FAIL is a data-integrity miss (spec Anti-goals): set `DAILY_DELTA_FETCH=false` at once (V171-38's flip commands), then record it;** repairing a file is `scripts/ops/market_cache_repair.py`'s job and the partner's call, never row deletion.

- [ ] **Step 4: Record the verdict and commit**
Create `docs/superpowers/results/2026-10-16-v171-success-week.md`: the window `S..E`, the flag dates from V171-38, the baseline file link, then the six-row table copied from the spec (`Check | Threshold | Measured | Verdict`), each verdict PASS, MISS or UNMEASURED with its evidence (report JSON in a fenced block, the 429 lines or "none", the parity summary line and any FAIL rows), the tape coverage and sample count, and the rebuild totals (`kept`, `dropped`, `misses`). Overall: **PASS** only when all six rows are PASS.

In the index: `## Progress` gets the week and the overall verdict. `## What follows`: on PASS, keep the first bullet (the follow-up plan that removes `count` mode and the per-part flags; `loops.daily_reanchor` stays) and mark it due; on any MISS or UNMEASURED, add one bullet per such row naming the row, its value and the flag it belongs to, and leave the flags as they are.

```bash
git -C $R add docs/superpowers/results/2026-10-16-v171-success-week.md docs/superpowers/plans/2026-10-16-v171-shared-market-data-fetch_0-index.md
git -C $R commit -m "docs(v171): success week S..E -- <PASS|MISS: rows>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Push outside the session.

- [ ] **Step 5: Hand the outcome to the partner**
On PASS: report the six rows and that the plan is ready for `/close-out` (release lines are resolved there, not here). On any MISS or UNMEASURED: ask the partner one question (`AskUserQuestion`, recommended option first) per row, the options being to turn that row's flag off (quote age -> `PLAN_REBUILD_ENABLED`; blank tape -> `TAPE_SHARED_ENABLED`; 429s or calls per hour -> `MARKETDATA_LAYER=count`; errors per ticker -> `DAILY_DELTA_FETCH`), to keep it on and open a fix plan, or (UNMEASURED only) to re-measure a further week with the same definitions. Thresholds are never offered as an option.
