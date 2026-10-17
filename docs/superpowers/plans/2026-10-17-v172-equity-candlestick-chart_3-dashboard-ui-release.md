# v172 Equity candlestick chart, part 3: dashboard UI, full suite, release, VM backfill, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V172-8:" -A 600 docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_3-dashboard-ui-release.md`. **This part holds V172-8 only**; V172-9..V172-10 are in `_3b-equity-candles-component.md` and V172-11..V172-14 in `_3c-suite-release-closeout.md` (split to stay under 1500 lines).

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md) (its `## Corrections from the code brief` win over earlier wording: currency from `connection.currency()`, viewer prefs through the server-backed `PreferencesStore`, account label "Paper account · before tax and costs", the `portfolio-value.spec.ts` "no `1W`" assertion is replaced)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md) — **Global Constraints, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints** (UI copy and UI behaviour bullets above all).

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths, `git -C $WT` and `npm --prefix $WT/frontend`. One frontend spec file runs with `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/<path>.spec.ts`.

**API contract this part builds on** (V172-5, Global Constraints): `GET /api/v1/equity/candles?tf=1H|4H|1D|1W&basis=mtm|realized&limit=1..500` returns exactly `{tf, basis, currency_symbol, candles, recording_since, as_of}`; a candle is exactly `{t, o, h, l, c, change, change_pct, samples, skipped, approx}`; `t` is `YYYY-MM-DD` for 1D/1W and an ISO datetime with the New York offset (`2026-10-16T09:00:00-04:00`) for 1H/4H. The SPA shows the currency from `connection.currency()` (passed down as the `currency` input), not from `currency_symbol`.

# Phase 3 — Dashboard UI

### Task V172-8: SPA models, `ApiClient.equityCandles`, prefs helper, `EquityCandlesStore`

**Model:** sonnet — store + client following the tape store pattern

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append after the `TapeResponse` interface, ~line 1922)
- Modify: `frontend/src/app/api/api-client.ts` (import list ~line 7-30; new method right after `tape(...)`, ~line 534)
- Modify: `frontend/src/app/api/api-client.spec.ts` (append one `describe` block at the end)
- Create: `frontend/src/app/ui/equity-chart-prefs.ts`
- Create: `frontend/src/app/ui/equity-chart-prefs.spec.ts`
- Create: `frontend/src/app/stores/equity-candles.store.ts`
- Create: `frontend/src/app/stores/equity-candles.store.spec.ts`

**Interfaces:**
- Consumes: the API contract at the top of this part (V172-5, built in parallel; no test here calls the server). `PreferencesStore.values()`/`.update(mutate)` (`stores/preferences.store.ts`), `EventStream.changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS })` (`api/event-stream.ts`), `Preferences` (`api/models.ts:1623`).
- Produces (ledger contract, consumed by V172-9 and V172-10):
  - `type EquityTimeframe = '1H' | '4H' | '1D' | '1W'`; `type EquityBasis = 'mtm' | 'realized'`
  - `interface EquityCandle { t: string; o: number; h: number; l: number; c: number; change: number; change_pct: number | null; samples: number; skipped: number; approx: boolean }`
  - `interface EquityCandlesResponse { tf: EquityTimeframe; basis: EquityBasis; currency_symbol: string; candles: EquityCandle[]; recording_since: string | null; as_of: string }`
  - `ApiClient.equityCandles(tf: EquityTimeframe, basis: EquityBasis, limit?: number): Observable<EquityCandlesResponse>`
  - `ui/equity-chart-prefs.ts`: `EQUITY_TF_KEY = 'dashboard.equity.tf'`, `EQUITY_BASIS_KEY = 'dashboard.equity.basis'`, `EQUITY_TIMEFRAMES`, `EQUITY_BASES`, `interface EquityChartPrefs { tf; basis }`, `DEFAULT_EQUITY_CHART_PREFS`, `readEquityChartPrefs(prefs: Preferences): EquityChartPrefs`, `writeEquityChartPrefs(prefs: Preferences, value: EquityChartPrefs): Preferences`
  - `EquityCandlesStore` (`providedIn: 'root'`): signals `tf()`, `basis()`, `data()`, `loading()`, `error()`; methods `load()`, `setTimeframe(tf)`, `setBasis(basis)`; constant `EQUITY_CANDLES_ERROR`.

- [ ] **Step 0: Make sure the worktree has its frontend dependencies**

```bash
test -d $WT/frontend/node_modules || npm --prefix $WT/frontend ci
```

Expected: nothing (already installed) or `added N packages`. The worktree does not share `$R/frontend/node_modules`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/frontend/src/app/ui/equity-chart-prefs.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  EQUITY_BASIS_KEY,
  EQUITY_TF_KEY,
  readEquityChartPrefs,
  writeEquityChartPrefs,
} from './equity-chart-prefs';

describe('equity-chart-prefs', () => {
  it('defaults to daily candles on the open + closed basis', () => {
    expect(readEquityChartPrefs({})).toEqual({ tf: '1D', basis: 'mtm' });
  });

  it('reads a stored timeframe and basis', () => {
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '4H', 'dashboard.equity.basis': 'realized' }))
      .toEqual({ tf: '4H', basis: 'realized' });
  });

  it('falls back per key when a stored value is unreadable', () => {
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '1M', 'dashboard.equity.basis': 7 }))
      .toEqual({ tf: '1D', basis: 'mtm' });
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '1W', 'dashboard.equity.basis': null }))
      .toEqual({ tf: '1W', basis: 'mtm' });
  });

  it('tolerates a missing preferences object', () => {
    expect(readEquityChartPrefs(undefined as never)).toEqual({ tf: '1D', basis: 'mtm' });
  });

  it('writes both keys and leaves every other key alone', () => {
    const next = writeEquityChartPrefs({ 'tape.symbols': ['NVDA'] }, { tf: '1H', basis: 'realized' });
    expect(next[EQUITY_TF_KEY]).toBe('1H');
    expect(next[EQUITY_BASIS_KEY]).toBe('realized');
    expect(next['tape.symbols']).toEqual(['NVDA']);
  });

  it('never writes a value the reader would reject', () => {
    const next = writeEquityChartPrefs({}, { tf: 'bogus' as never, basis: 'mtm' });
    expect(next[EQUITY_TF_KEY]).toBe('1D');
  });
});
```

Create `$WT/frontend/src/app/stores/equity-candles.store.spec.ts`:

```ts
import { ApplicationRef, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import {
  EquityBasis,
  EquityCandle,
  EquityCandlesResponse,
  EquityTimeframe,
  Preferences,
} from '../api/models';
import { EQUITY_CANDLES_ERROR, EquityCandlesStore } from './equity-candles.store';
import { PreferencesStore } from './preferences.store';

const CANDLE: EquityCandle = {
  t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
  change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false,
};

function response(tf: EquityTimeframe = '1D', basis: EquityBasis = 'mtm',
                  candles: EquityCandle[] = [CANDLE]): EquityCandlesResponse {
  return { tf, basis, currency_symbol: '€', candles, recording_since: null,
           as_of: '2026-10-17T14:00:00+00:00' };
}

function okApi() {
  return {
    equityCandles: vi.fn().mockImplementation(
      (tf: EquityTimeframe, basis: EquityBasis) => of(response(tf, basis))),
  };
}

function pendingApi(pending: Subject<EquityCandlesResponse>[]) {
  return {
    equityCandles: vi.fn().mockImplementation(() => {
      const subject = new Subject<EquityCandlesResponse>();
      pending.push(subject);
      return subject;
    }),
  };
}

/** A signal-backed PreferencesStore fake: `update` really changes `values()`,
 *  so the store's tf/basis computeds and the onInit effect react to a write
 *  exactly as they do against the real store. */
function setup(stored: Preferences = {}, api: { equityCandles: ReturnType<typeof vi.fn> } = okApi()) {
  const prefs = signal<Preferences>(stored);
  const scan = signal(0);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: ApiClient, useValue: api },
      { provide: EventStream, useValue: { changes: () => scan.asReadonly() } },
      { provide: PreferencesStore, useValue: {
          values: () => prefs(),
          update: (mutate: (p: Preferences) => Preferences) => prefs.update(mutate),
          isLoaded: () => true,
        } },
    ],
  });
  const store = TestBed.inject(EquityCandlesStore);
  const tick = () => TestBed.inject(ApplicationRef).tick();
  tick();
  return { api, store, prefs, scan, tick };
}

describe('EquityCandlesStore', () => {
  it('loads daily mark-to-market candles when nothing is stored', () => {
    const { api, store } = setup();
    expect(api.equityCandles).toHaveBeenCalledTimes(1);
    expect(api.equityCandles).toHaveBeenCalledWith('1D', 'mtm');
    expect(store.data()?.candles).toEqual([CANDLE]);
    expect(store.loading()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('loads the stored timeframe and basis', () => {
    const { api, store } = setup({ 'dashboard.equity.tf': '4H', 'dashboard.equity.basis': 'realized' });
    expect(api.equityCandles).toHaveBeenCalledWith('4H', 'realized');
    expect(store.tf()).toBe('4H');
    expect(store.basis()).toBe('realized');
  });

  it('writes the timeframe through PreferencesStore and refetches once', () => {
    const { api, store, prefs, tick } = setup();
    store.setTimeframe('1W');
    tick();
    expect(prefs()['dashboard.equity.tf']).toBe('1W');
    expect(prefs()['dashboard.equity.basis']).toBe('mtm');
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
    expect(api.equityCandles).toHaveBeenLastCalledWith('1W', 'mtm');
  });

  it('writes the basis through PreferencesStore and refetches once', () => {
    const { api, store, prefs, tick } = setup();
    store.setBasis('realized');
    tick();
    expect(prefs()['dashboard.equity.basis']).toBe('realized');
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
    expect(api.equityCandles).toHaveBeenLastCalledWith('1D', 'realized');
  });

  it('does not refetch on an unrelated preference write', () => {
    const { api, prefs, tick } = setup();
    prefs.update((p) => ({ ...p, 'tape.symbols': ['NVDA'] }));
    tick();
    expect(api.equityCandles).toHaveBeenCalledTimes(1);
  });

  it('refetches when a scan event arrives', () => {
    const { api, scan, tick } = setup();
    scan.update((n) => n + 1);
    tick();
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
  });

  it('keeps the candles it has when a refetch fails', () => {
    const { api, store } = setup();
    api.equityCandles.mockReturnValue(throwError(() => new Error('boom')));
    store.load();
    expect(store.data()?.candles).toEqual([CANDLE]);
    expect(store.error()).toBeNull();
  });

  it('reports an error when the first load fails', () => {
    const api = { equityCandles: vi.fn().mockReturnValue(throwError(() => new Error('boom'))) };
    const { store } = setup({}, api);
    expect(store.data()).toBeNull();
    expect(store.error()).toBe(EQUITY_CANDLES_ERROR);
  });

  it('drops the previous view candles while a new timeframe loads', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store, tick } = setup({}, pendingApi(pending));
    pending[0].next(response('1D'));
    expect(store.data()?.tf).toBe('1D');

    store.setTimeframe('1H');
    tick();
    expect(store.data()).toBeNull();
    expect(store.loading()).toBe(true);
    pending[1].next(response('1H'));
    expect(store.data()?.tf).toBe('1H');
  });

  it('applies only the later of two overlapping loads', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store } = setup({}, pendingApi(pending));
    store.load();
    const stale = pending[0];
    const fresh = pending[1];
    fresh.next(response('1D', 'mtm', [{ ...CANDLE, c: 2 }]));
    stale.next(response('1D', 'mtm', [{ ...CANDLE, c: 1 }]));
    expect(store.data()?.candles[0].c).toBe(2);
  });
});
```

Append to the end of `$WT/frontend/src/app/api/api-client.spec.ts` (the file's existing imports already cover everything used here):

```ts
describe('ApiClient — equity candles', () => {
  let api: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    api = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('sends the timeframe and basis, and a limit only when one is given', () => {
    const empty = { currency_symbol: '€', candles: [], recording_since: null,
                    as_of: '2026-10-17T14:00:00+00:00' };
    api.equityCandles('4H', 'realized').subscribe();
    const first = http.expectOne((r) => r.url.endsWith('/api/v1/equity/candles'));
    expect(first.request.method).toBe('GET');
    expect(first.request.params.get('tf')).toBe('4H');
    expect(first.request.params.get('basis')).toBe('realized');
    expect(first.request.params.has('limit')).toBe(false);
    first.flush({ tf: '4H', basis: 'realized', ...empty });

    api.equityCandles('1D', 'mtm', 30).subscribe();
    const second = http.expectOne((r) => r.url.endsWith('/api/v1/equity/candles'));
    expect(second.request.params.get('limit')).toBe('30');
    second.flush({ tf: '1D', basis: 'mtm', ...empty });
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/equity-chart-prefs.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/stores/equity-candles.store.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/api/api-client.spec.ts
```

Expected: the first two fail to resolve `./equity-chart-prefs` / `./equity-candles.store`; the third fails on `api.equityCandles` (not a function / does not exist on `ApiClient`).

- [ ] **Step 3: Add the models**

In `$WT/frontend/src/app/api/models.ts`, directly after the closing `}` of `export interface TapeResponse { ... }`, add:

```ts

/* -- equity candles (v172) ------------------------------------------------ */

/** Candle width. Buckets are New York wall clock: 4H starts at
 *  00/04/08/12/16/20 NY, 1W on Monday. */
export type EquityTimeframe = '1H' | '4H' | '1D' | '1W';

/** `mtm` = realized balance + open positions' unrealized P&L ("Open +
 *  closed"); `realized` = closed legs only ("Closed trades only"). */
export type EquityBasis = 'mtm' | 'realized';

/** One equity candle — mirrors `tests/admin/test_api_v1_equity.py`.
 *
 *  `t` is the bucket start: `YYYY-MM-DD` for 1D/1W, an ISO datetime with the
 *  New York offset for 1H/4H. `change`/`change_pct` are measured against the
 *  previous candle's close (the first candle against its own open);
 *  `change_pct` is null when that base is 0. `approx` marks a candle built
 *  from backfilled daily bars, whose high/low are outer bounds. `skipped` is
 *  the most open positions any sample in the bucket left unpriced. */
export interface EquityCandle {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  change: number;
  change_pct: number | null;
  samples: number;
  skipped: number;
  approx: boolean;
}

/** `GET /api/v1/equity/candles`. `recording_since` is the first live sample
 *  (ISO UTC) or null before the monitor has recorded one. The SPA shows the
 *  currency from `ConnectionStore.currency()`; `currency_symbol` is the same
 *  config value, carried for API consumers. */
export interface EquityCandlesResponse {
  tf: EquityTimeframe;
  basis: EquityBasis;
  currency_symbol: string;
  candles: EquityCandle[];
  recording_since: string | null;
  as_of: string;
}
```

- [ ] **Step 4: Add the client method**

In `$WT/frontend/src/app/api/api-client.ts`, add `EquityBasis,`, `EquityCandlesResponse,` and `EquityTimeframe,` to the `import { ... } from './models';` list (where they fall alphabetically). Then, directly after the `tape(symbols: string[]): Observable<TapeResponse> { ... }` method, add:

```ts

  /** Equity candles for the Dashboard chart (v172). `limit` is left to the
   *  server's default (120) unless given. */
  equityCandles(tf: EquityTimeframe, basis: EquityBasis, limit?: number): Observable<EquityCandlesResponse> {
    let params = new HttpParams().set('tf', tf).set('basis', basis);
    if (limit !== undefined) params = params.set('limit', String(limit));
    return this.http.get<EquityCandlesResponse>(`${this.base}/equity/candles`, { params });
  }
```

- [ ] **Step 5: Write the prefs helper**

Create `$WT/frontend/src/app/ui/equity-chart-prefs.ts`:

```ts
import { EquityBasis, EquityTimeframe, Preferences } from '../api/models';

/**
 * The Dashboard equity chart's timeframe and basis — spec v172 § 5.
 *
 * Flat dotted keys in the server-backed preferences, like `tape-prefs.ts`,
 * never localStorage (`preferences.store.ts`): the same viewer on a laptop and
 * a phone sees the same chart.
 *
 * **The read is tolerant.** The value is hand-editable on the server and is
 * written by one version of the app and read by the next, so anything the
 * reader does not recognise falls back to the default for that key alone.
 */
export const EQUITY_TF_KEY = 'dashboard.equity.tf';
export const EQUITY_BASIS_KEY = 'dashboard.equity.basis';

export const EQUITY_TIMEFRAMES: readonly EquityTimeframe[] = ['1H', '4H', '1D', '1W'];
export const EQUITY_BASES: readonly EquityBasis[] = ['mtm', 'realized'];

export interface EquityChartPrefs {
  tf: EquityTimeframe;
  basis: EquityBasis;
}

/** 1D and mark-to-market: this is a swing system, and the daily candle is
 *  the one that answers "how did the account do". */
export const DEFAULT_EQUITY_CHART_PREFS: EquityChartPrefs = { tf: '1D', basis: 'mtm' };

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

export function readEquityChartPrefs(prefs: Preferences): EquityChartPrefs {
  return {
    tf: pick(prefs?.[EQUITY_TF_KEY], EQUITY_TIMEFRAMES, DEFAULT_EQUITY_CHART_PREFS.tf),
    basis: pick(prefs?.[EQUITY_BASIS_KEY], EQUITY_BASES, DEFAULT_EQUITY_CHART_PREFS.basis),
  };
}

export function writeEquityChartPrefs(prefs: Preferences, value: EquityChartPrefs): Preferences {
  // Normalised through the reader, so a bad value is never persisted.
  const clean = readEquityChartPrefs({ [EQUITY_TF_KEY]: value.tf, [EQUITY_BASIS_KEY]: value.basis });
  return { ...prefs, [EQUITY_TF_KEY]: clean.tf, [EQUITY_BASIS_KEY]: clean.basis };
}
```

- [ ] **Step 6: Write the store**

Create `$WT/frontend/src/app/stores/equity-candles.store.ts`:

```ts
import { computed, effect, inject, untracked } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../api/models';
import {
  EquityChartPrefs,
  readEquityChartPrefs,
  writeEquityChartPrefs,
} from '../ui/equity-chart-prefs';
import { PreferencesStore } from './preferences.store';

interface EquityCandlesSlice {
  data: EquityCandlesResponse | null;
  loading: boolean;
  error: string | null;
}

export const EQUITY_CANDLES_ERROR = 'Equity candles could not be loaded.';

/**
 * The Dashboard's equity candles — spec v172 § 5.
 *
 * **Refetch, never push**, like `TapeStore`: the onInit effect runs on the
 * throttled `scan` event and whenever the chosen timeframe or basis changes,
 * and its first run is the initial load. The trade monitor's samples raise no
 * SSE event of their own, so the newest candle grows with the scan cadence.
 *
 * `tf`/`basis` are two string computeds over the server-backed preferences,
 * so an unrelated preference write (a column width) compares equal and does
 * not refetch.
 *
 * **A failed refetch keeps the candles already shown**; only a failed first
 * load (nothing to show) surfaces `error` for `sb-async`'s retry. Switching
 * timeframe or basis drops the other view's candles at once, so a 1H request
 * in flight never sits under daily candles.
 */
export const EquityCandlesStore = signalStore(
  { providedIn: 'root' },
  withState<EquityCandlesSlice>({ data: null, loading: false, error: null }),
  withComputed((_store, prefs = inject(PreferencesStore)) => ({
    tf: computed<EquityTimeframe>(() => readEquityChartPrefs(prefs.values()).tf),
    basis: computed<EquityBasis>(() => readEquityChartPrefs(prefs.values()).basis),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;

    const load = (): void => {
      const tf = store.tf();
      const basis = store.basis();
      // untracked: `load()` runs inside the onInit effect, and a tracked read
      // of `data` would make every response re-trigger the effect.
      const previous = untracked(() => store.data());
      const sameView = previous !== null && previous.tf === tf && previous.basis === basis;
      const request = ++latestRequest;
      patchState(store, { loading: true, error: null, data: sameView ? previous : null });
      api.equityCandles(tf, basis).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.candles)) {
            patchState(store, { loading: false });
            return;
          }
          patchState(store, { data: response, loading: false, error: null });
        },
        error: () => {
          if (request !== latestRequest) return;
          // untracked for the same reason: a synchronous error (a test's
          // throwError) lands inside the effect's run.
          const shown = untracked(() => store.data());
          patchState(store, { loading: false, error: shown ? null : EQUITY_CANDLES_ERROR });
        },
      });
    };

    // Does not call `load()`: the write changes `tf()`/`basis()`, and the
    // tracked onInit effect refetches once as a result.
    const write = (value: EquityChartPrefs): void =>
      prefs.update((current) => writeEquityChartPrefs(current, value));

    return {
      load,
      setTimeframe(tf: EquityTimeframe): void {
        write({ tf, basis: store.basis() });
      },
      setBasis(basis: EquityBasis): void {
        write({ tf: store.tf(), basis });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const scan = events.changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
      effect(() => {
        scan();
        store.load();
      });
    },
  }),
);
```

- [ ] **Step 7: Run the tests to see them pass**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/equity-chart-prefs.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/stores/equity-candles.store.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/api/api-client.spec.ts
```

Expected: all pass, 0 failed. If "drops the previous view candles" fails with `data()` still set, check that `load()` passes `data: null` when `sameView` is false; if a test loops or times out, a `store.data()` read inside `load()` escaped `untracked`.

- [ ] **Step 8: Commit on the branch**

```bash
git -C $WT add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts frontend/src/app/ui/equity-chart-prefs.ts frontend/src/app/ui/equity-chart-prefs.spec.ts frontend/src/app/stores/equity-candles.store.ts frontend/src/app/stores/equity-candles.store.spec.ts
git -C $WT commit -m "feat(ui): equity candles client, server-backed chart prefs and store (v172)"
git -C $R status --short
```

End the commit message with the attribution line from the session's system reminder. Expected: one commit on the branch; `$R`'s status shows no change from this task.
