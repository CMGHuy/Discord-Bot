**Part 2 of 3** — `2026-08-22-v53-pnl-calendar_0-index.md` carries the header
block, goal, Global Constraints and the parallelisation map. **Read the index's
Global Constraints before starting any task here.**

Every task below except Task 8 depends on Part 1 (`_1-backend`) being complete:
the endpoints must exist and their response shapes be final. Task 8
(`calendar.helpers.ts`) is pure date math and may be worked concurrently with
Part 1.

---

# Phase 3 — Frontend data layer

### Task 6: TypeScript models and the two `ApiClient` methods

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append a `/* -- calendar -- */`
  section, following the file's existing section-comment style)
- Modify: `frontend/src/app/api/api-client.ts` (add two methods)

**Interfaces:**
- Consumes: the exact response shapes Tasks 4 and 5 produce.
- Produces: `CalendarDay`, `CalendarTotals`, `CalendarWeekday`,
  `CalendarStreak`, `CalendarFilters`, `CalendarTrade`, `PnlCalendar`,
  `CalendarDayTrades` interfaces; `ApiClient.calendarPnl(query)` and
  `ApiClient.calendarPnlDay(query)`.

- [x] **Step 1: Write the failing check**

`models.ts` is types only and `api-client.ts` is one thin method per
endpoint, so the type-checker is the test here rather than a `.spec.ts` —
Task 7's store spec is what exercises the behaviour. Force the failure by
adding this one line at the top of the `ApiClient` class body in
`frontend/src/app/api/api-client.ts`; Step 3 removes it again:

```ts
  private readonly _v53Check: PnlCalendar | null = null;
```

- [x] **Step 2: Run the build to verify it fails**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: FAIL — `TS2304: Cannot find name 'PnlCalendar'`.

- [x] **Step 3: Write minimal implementation**

Append to `frontend/src/app/api/models.ts`:

```ts
/* -- calendar ----------------------------------------------------------- */

/** One day cell. `net_pnl_amount` and `net_r` are null when nothing on that
 *  day had a computable figure -- which is NOT the same as a flat $0 day,
 *  and the grid must render the two differently. */
export interface CalendarDay {
  date: string;
  net_pnl_amount: number | null;
  net_r: number | null;
  trade_count: number;
  win_rate: number | null;
}

/** The visible month's pooled figures. Same fields as a day, minus the
 *  date -- a month total carrying a `date` invites reading it as a day. */
export interface CalendarTotals {
  net_pnl_amount: number | null;
  net_r: number | null;
  trade_count: number;
  win_rate: number | null;
}

export interface CalendarWeekday {
  weekday: string;
  avg_pnl_amount: number | null;
  avg_r: number | null;
  win_rate: number | null;
  trade_count: number;
}

export interface CalendarStreak {
  direction: string | null;
  days: number;
}

export interface CalendarFilters {
  strategies: string[];
  horizons: string[];
}

/** One row in the day drawer: the trade record joined with its journal
 *  entry. The journal half (`mfe_r`, `mae_r`, `exit_efficiency`, `tags`,
 *  `auto_lesson`) is absent for an unjournaled trade. */
export interface CalendarTrade {
  trade_id: string;
  ticker: string;
  strategy: string;
  horizon: string | null;
  direction: string | null;
  day: string;
  closed_at: string | null;
  outcome: string | null;
  pnl_amount: number | null;
  r_multiple: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  exit_efficiency: number | null;
  tags: string[];
  auto_lesson: string | null;
}

/** `days`/`totals` are the requested month; `day_of_week`, `best_day`,
 *  `worst_day` and `streak` are all of history under the same filter --
 *  a weekday average drawn from one month would be 4-5 observations. */
export interface PnlCalendar {
  month: string;
  days: CalendarDay[];
  totals: CalendarTotals;
  day_of_week: CalendarWeekday[];
  best_day: CalendarDay | null;
  worst_day: CalendarDay | null;
  streak: CalendarStreak;
  filters: CalendarFilters;
}

export interface CalendarDayTrades {
  date: string;
  trades: CalendarTrade[];
}
```

Remove the temporary `_v53Check` line and add to `ApiClient` in
`frontend/src/app/api/api-client.ts` (import the two new names alongside the
existing model imports):

```ts
  /** One month of daily P&L, plus the all-history context beside it. */
  calendarPnl(query: {
    month: string;
    strategy?: string;
    horizon?: string;
  }): Observable<PnlCalendar> {
    let params = new HttpParams().set('month', query.month);
    if (query.strategy) params = params.set('strategy', query.strategy);
    if (query.horizon) params = params.set('horizon', query.horizon);
    return this.http.get<PnlCalendar>(`${this.base}/calendar/pnl`, { params });
  }

  /** Every trade closed on one day. 404s for a day with no closes, which
   *  the store surfaces as an empty drawer rather than an error. */
  calendarPnlDay(query: {
    date: string;
    strategy?: string;
    horizon?: string;
  }): Observable<CalendarDayTrades> {
    let params = new HttpParams().set('date', query.date);
    if (query.strategy) params = params.set('strategy', query.strategy);
    if (query.horizon) params = params.set('horizon', query.horizon);
    return this.http.get<CalendarDayTrades>(`${this.base}/calendar/pnl/day`, {
      params,
    });
  }
```

- [x] **Step 4: Run the build to verify it passes**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: PASS — no errors

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts
git commit -m "feat(v53): add calendar models and ApiClient methods"
```

---

### Task 7: `CalendarStore`

**Files:**
- Create: `frontend/src/app/stores/calendar.store.ts`
- Test: `frontend/src/app/stores/calendar.store.spec.ts`

**Interfaces:**
- Consumes: `ApiClient.calendarPnl` / `calendarPnlDay` (Task 6),
  `PnlCalendar`, `CalendarDay`, `CalendarTrade` (Task 6), `EventStream`
  (`frontend/src/app/api/event-stream.ts`), `ApiError`
  (`frontend/src/app/api/api-error.ts`).
- Produces: `CalendarMetric = 'money' | 'r'`; `CalendarStore` exposing
  signals `data`, `loading`, `error`, `month`, `metric`, `strategy`,
  `horizon`, `selectedDay`, `dayTrades`, `dayLoading`; computed `dayIndex`,
  `scale`, `strategyOptions`, `horizonOptions`, `empty`; methods `load()`,
  `setMonth(month)`, `stepMonth(delta)`, `setMetric(metric)`,
  `setStrategy(value)`, `setHorizon(value)`, `selectDay(date)`,
  `closeDay()`, `valueFor(day)`, `signedIntensity(day)`.

- [x] **Step 1: Write the failing test**

Create `frontend/src/app/stores/calendar.store.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { PnlCalendar } from '../api/models';
import { CalendarStore } from './calendar.store';

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const RESPONSE: PnlCalendar = {
  month: '2026-08',
  days: [
    { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
    { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  ],
  totals: { net_pnl_amount: -60, net_r: -0.6, trade_count: 3, win_rate: 33.33 },
  day_of_week: [
    { weekday: 'Mon', avg_pnl_amount: 15, avg_r: 0.6, win_rate: 50, trade_count: 2 },
    { weekday: 'Tue', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Wed', avg_pnl_amount: -90, avg_r: -1.8, win_rate: 0, trade_count: 1 },
    { weekday: 'Thu', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Fri', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
  ],
  best_day: { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
  worst_day: { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  streak: { direction: 'losing', days: 1 },
  filters: { strategies: ['EMA20', 'VWAP'], horizons: ['3m', '4w'] },
};

describe('CalendarStore', () => {
  let store: InstanceType<typeof CalendarStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        CalendarStore,
      ],
    });
    store = TestBed.inject(CalendarStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const respond = (body: Partial<PnlCalendar> = {}) =>
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl')
      .flush({ ...RESPONSE, ...body });

  it('loads the current month on creation', () => {
    tick();
    respond();

    expect(store.days()).toHaveLength(2);
    expect(store.empty()).toBe(false);
    expect(store.strategyOptions().map((o) => o.value)).toEqual(['EMA20', 'VWAP']);
  });

  it('defaults to the money metric, not R', () => {
    tick();
    respond();

    expect(store.metric()).toBe('money');
    expect(store.valueFor(RESPONSE.days[0])).toBe(30);
  });

  it('valueFor follows the metric toggle', () => {
    tick();
    respond();

    store.setMetric('r');
    expect(store.valueFor(RESPONSE.days[0])).toBe(1.2);
  });

  it('scales intensity against the largest magnitude in the month', () => {
    tick();
    respond();

    // |−90| is the month's largest, so it saturates and +30 is a third of it.
    expect(store.signedIntensity(RESPONSE.days[1])).toBeCloseTo(-1);
    expect(store.signedIntensity(RESPONSE.days[0])).toBeCloseTo(1 / 3);
  });

  it('gives a null-valued day zero intensity, not a faint tint', () => {
    tick();
    respond();

    expect(
      store.signedIntensity({
        date: '2026-08-09',
        net_pnl_amount: null,
        net_r: null,
        trade_count: 1,
        win_rate: null,
      }),
    ).toBe(0);
  });

  it('stepMonth refetches the neighbouring month, crossing a year', () => {
    tick();
    respond({ month: '2026-01' });

    store.setMonth('2026-01');
    tick();
    backend.expectOne((r) => r.params.get('month') === '2026-01').flush(RESPONSE);

    store.stepMonth(-1);
    tick();
    backend.expectOne((r) => r.params.get('month') === '2025-12').flush(RESPONSE);
    expect(store.month()).toBe('2025-12');
  });

  it('sends the strategy filter and refetches', () => {
    tick();
    respond();

    store.setStrategy('EMA20');
    tick();
    backend.expectOne((r) => r.params.get('strategy') === 'EMA20').flush(RESPONSE);
  });

  it('fetches a day lazily, only once selected', () => {
    tick();
    respond();

    expect(store.dayTrades()).toBeNull();

    store.selectDay('2026-08-03');
    tick();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades: [] });

    expect(store.selectedDay()).toBe('2026-08-03');
    expect(store.dayTrades()).toEqual([]);
  });

  it('closeDay clears the selection and the fetched rows', () => {
    tick();
    respond();
    store.selectDay('2026-08-03');
    tick();
    backend
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades: [] });

    store.closeDay();
    expect(store.selectedDay()).toBeNull();
    expect(store.dayTrades()).toBeNull();
  });

  it('keeps the grid and shows a message when a refetch fails', () => {
    tick();
    respond();

    store.setStrategy('VWAP');
    tick();
    backend
      .expectOne((r) => r.params.get('strategy') === 'VWAP')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });

    // Stale numbers beside a warning beat an error panel where the grid was.
    expect(store.days()).toHaveLength(2);
    expect(store.error()).toBeTruthy();
  });

  it('refetches on a trades event', () => {
    tick();
    respond();

    events.raise('trades');
    tick();
    respond({ totals: { ...RESPONSE.totals, trade_count: 9 } });

    expect(store.totals()?.trade_count).toBe(9);
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/stores/calendar.store.spec.ts`
Expected: FAIL — `Cannot find module './calendar.store'`

- [x] **Step 3: Write minimal implementation**

Create `frontend/src/app/stores/calendar.store.ts`:

```ts
import { computed, effect, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import {
  CalendarDay,
  CalendarTotals,
  CalendarTrade,
  PnlCalendar,
} from '../api/models';
import { SelectOption } from '../ui/form-controls';

/** Which figure the grid shows and colours by. Money is the default: the
 *  dollar swing is what the page is for, and R lives one toggle away for
 *  when position size should be factored out. */
export type CalendarMetric = 'money' | 'r';

/** `YYYY-MM` for today, in the browser's own calendar. The server defaults
 *  to its month when `?month=` is absent, but sending it explicitly keeps
 *  the store's `month` signal and the response in agreement from the first
 *  request rather than after it. */
function currentMonth(now = new Date()): string {
  const month = `${now.getMonth() + 1}`.padStart(2, '0');
  return `${now.getFullYear()}-${month}`;
}

/** Shift a `YYYY-MM` by whole months, carrying the year. Built on Date's
 *  own month arithmetic (which normalises month 12 and -1 for us) rather
 *  than hand-rolled modulo, where the December/January edge is the bug. */
export function shiftMonth(month: string, delta: number): string {
  const [year, index] = month.split('-').map(Number);
  return currentMonth(new Date(year, index - 1 + delta, 1));
}

interface CalendarSlice {
  data: PnlCalendar | null;
  loading: boolean;
  error: string | null;
  month: string;
  metric: CalendarMetric;
  strategy: string;
  horizon: string;
  selectedDay: string | null;
  dayTrades: CalendarTrade[] | null;
  dayLoading: boolean;
}

export const CalendarStore = signalStore(
  withState<CalendarSlice>({
    data: null,
    loading: false,
    error: null,
    month: currentMonth(),
    metric: 'money',
    strategy: '',
    horizon: '',
    selectedDay: null,
    dayTrades: null,
    dayLoading: false,
  }),
  withComputed(({ data, metric }) => ({
    /** True until the first response and never again — a skeleton once. */
    empty: computed(() => data() === null),

    days: computed<CalendarDay[]>(() => data()?.days ?? []),
    totals: computed<CalendarTotals | null>(() => data()?.totals ?? null),
    weekdays: computed(() => data()?.day_of_week ?? []),
    bestDay: computed(() => data()?.best_day ?? null),
    worstDay: computed(() => data()?.worst_day ?? null),
    streak: computed(() => data()?.streak ?? null),

    /** `date -> day`, so the grid does not linear-scan per cell. */
    dayIndex: computed(() => {
      const index = new Map<string, CalendarDay>();
      for (const day of data()?.days ?? []) index.set(day.date, day);
      return index;
    }),

    /** The largest absolute value in the visible month, under the CURRENT
     *  metric — the denominator that makes the colour ramp relative to the
     *  month you are looking at rather than to some global constant. 0 when
     *  nothing is computable, and callers must guard against dividing by it. */
    scale: computed(() => {
      const pick = (day: CalendarDay) =>
        metric() === 'money' ? day.net_pnl_amount : day.net_r;
      const magnitudes = (data()?.days ?? [])
        .map((day) => pick(day))
        .filter((value): value is number => value !== null)
        .map(Math.abs);
      return magnitudes.length ? Math.max(...magnitudes) : 0;
    }),

    strategyOptions: computed<SelectOption[]>(() =>
      (data()?.filters.strategies ?? []).map((value) => ({ value, label: value })),
    ),
    horizonOptions: computed<SelectOption[]>(() =>
      (data()?.filters.horizons ?? []).map((value) => ({ value, label: value })),
    ),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const fetchDay = (date: string): void => {
      patchState(store, { dayLoading: true });
      api
        .calendarPnlDay({
          date,
          strategy: store.strategy() || undefined,
          horizon: store.horizon() || undefined,
        })
        .subscribe({
          next: (body) =>
            patchState(store, { dayTrades: body.trades, dayLoading: false }),
          // A 404 means the day holds nothing under this filter. That is an
          // empty drawer, not an error banner over the whole workspace.
          error: () => patchState(store, { dayTrades: [], dayLoading: false }),
        });
    };

    const load = (): void => {
      patchState(store, { loading: true });
      api
        .calendarPnl({
          month: store.month(),
          strategy: store.strategy() || undefined,
          horizon: store.horizon() || undefined,
        })
        .subscribe({
          next: (data) => patchState(store, { data, loading: false, error: null }),
          error: (error: ApiError) =>
            patchState(store, {
              loading: false,
              // `data` is deliberately untouched: a stale grid beside a
              // warning beats an error panel where the numbers were.
              error:
                error.code === 'unavailable'
                  ? 'The admin is not responding — these figures may be stale.'
                  : error.message,
            }),
        });
    };

    return {
      load,

      setMonth(month: string): void {
        patchState(store, { month, selectedDay: null, dayTrades: null });
        load();
      },

      stepMonth(delta: number): void {
        patchState(store, {
          month: shiftMonth(store.month(), delta),
          selectedDay: null,
          dayTrades: null,
        });
        load();
      },

      /** Metric is a pure view concern — no refetch. The payload already
       *  carries both units for every day. */
      setMetric(metric: CalendarMetric): void {
        patchState(store, { metric });
      },

      setStrategy(strategy: string): void {
        patchState(store, { strategy, selectedDay: null, dayTrades: null });
        load();
      },

      setHorizon(horizon: string): void {
        patchState(store, { horizon, selectedDay: null, dayTrades: null });
        load();
      },

      /** Lazy by design: a month of drawer payloads nobody opens is 20-odd
       *  requests for one the user might make. */
      selectDay(date: string): void {
        patchState(store, { selectedDay: date, dayTrades: null });
        fetchDay(date);
      },

      closeDay(): void {
        patchState(store, { selectedDay: null, dayTrades: null });
      },

      /** The number a cell shows, under the current metric. */
      valueFor(day: CalendarDay): number | null {
        return store.metric() === 'money' ? day.net_pnl_amount : day.net_r;
      },

      /** −1..+1. Sign picks the colour, magnitude picks the intensity, and
       *  a day with no computable figure gets exactly 0 so "no data" and
       *  "a genuinely flat day" do not paint the same. */
      signedIntensity(day: CalendarDay): number {
        const value = store.metric() === 'money' ? day.net_pnl_amount : day.net_r;
        const scale = store.scale();
        if (value === null || scale === 0) return 0;
        return Math.max(-1, Math.min(1, value / scale));
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      // Reading the counter inside the effect IS the subscription, and the
      // first run is the initial load -- so load and refetch are one path.
      const trades = events.changes('trades');
      effect(() => {
        trades();
        store.load();
      });
    },
  }),
);
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/stores/calendar.store.spec.ts`
Expected: PASS — 12 passed

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/stores/calendar.store.ts \
        frontend/src/app/stores/calendar.store.spec.ts
git commit -m "feat(v53): add the calendar store with money/R metric toggle"
```

---

### Task 8: Month-grid date math

**Files:**
- Create: `frontend/src/app/workspaces/calendar/calendar.helpers.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts`

**Interfaces:**
- Consumes: nothing. Pure functions over strings and numbers — this is why
  the task may run concurrently with Phase 1.
- Produces: `GridCell { date: string; dayOfMonth: number; inMonth: boolean;
  weekend: boolean }`; `monthMatrix(month: string) -> GridCell[][]`;
  `monthLabel(month: string) -> string`.

- [x] **Step 1: Write the failing test**

Create `frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { monthLabel, monthMatrix } from './calendar.helpers';

describe('monthMatrix', () => {
  it('lays out Monday-first weeks of seven', () => {
    const weeks = monthMatrix('2026-08');
    expect(weeks.every((week) => week.length === 7)).toBe(true);
    // 2026-08-01 is a Saturday, so the first row starts on Mon 2026-07-27.
    expect(weeks[0][0].date).toBe('2026-07-27');
    expect(weeks[0][0].inMonth).toBe(false);
  });

  it('marks the days that belong to the requested month', () => {
    const inMonth = monthMatrix('2026-08')
      .flat()
      .filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(31);
    expect(inMonth[0].date).toBe('2026-08-01');
    expect(inMonth[30].date).toBe('2026-08-31');
  });

  it('marks weekends, which never carry a close', () => {
    const cells = monthMatrix('2026-08').flat();
    const saturday = cells.find((cell) => cell.date === '2026-08-01');
    const monday = cells.find((cell) => cell.date === '2026-08-03');
    expect(saturday?.weekend).toBe(true);
    expect(monday?.weekend).toBe(false);
  });

  it('handles February in a leap year', () => {
    const inMonth = monthMatrix('2024-02')
      .flat()
      .filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(29);
    expect(inMonth[28].date).toBe('2024-02-29');
  });

  it('handles a month that starts on a Monday without a blank leading week', () => {
    // 2026-06-01 is a Monday.
    const weeks = monthMatrix('2026-06');
    expect(weeks[0][0].date).toBe('2026-06-01');
    expect(weeks[0][0].inMonth).toBe(true);
  });

  it('pads the trailing week rather than emitting a short row', () => {
    const weeks = monthMatrix('2026-08');
    const last = weeks[weeks.length - 1];
    expect(last).toHaveLength(7);
    expect(last[6].inMonth).toBe(false);
  });

  it('zero-pads dates so they match the API day keys exactly', () => {
    // A `2026-8-3` here would silently miss every dayIndex lookup.
    const cells = monthMatrix('2026-08').flat();
    expect(cells.every((cell) => /^\d{4}-\d{2}-\d{2}$/.test(cell.date))).toBe(true);
  });
});

describe('monthLabel', () => {
  it('renders a human month and year', () => {
    expect(monthLabel('2026-08')).toBe('August 2026');
    expect(monthLabel('2026-01')).toBe('January 2026');
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.helpers.spec.ts`
Expected: FAIL — `Cannot find module './calendar.helpers'`

- [x] **Step 3: Write minimal implementation**

Create `frontend/src/app/workspaces/calendar/calendar.helpers.ts`:

```ts
/**
 * Month-grid geometry. Pure string/number math, no store and no HTTP, so
 * the awkward parts -- leap years, a month starting on a Sunday, the
 * December/January boundary -- are testable without standing anything up.
 *
 * `Date` is used only as a calendar oracle (how long is this month, what
 * weekday is the 1st). Every value that leaves this module is a
 * `YYYY-MM-DD` string, because that is the key the API's `days` array uses
 * and a `Date` round-trip through a timezone is exactly how a grid ends up
 * one day out.
 */

export interface GridCell {
  /** `YYYY-MM-DD`, zero-padded to match the API's day keys byte for byte. */
  date: string;
  dayOfMonth: number;
  /** False for the leading/trailing days borrowed from adjacent months. */
  inMonth: boolean;
  /** Saturday or Sunday. No trade ever closes on one, so the grid renders
   *  these inert rather than as an empty-but-clickable trading day. */
  weekend: boolean;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function iso(year: number, month: number, day: number): string {
  const mm = `${month}`.padStart(2, '0');
  const dd = `${day}`.padStart(2, '0');
  return `${year}-${mm}-${dd}`;
}

/**
 * Whole weeks covering `month` (`YYYY-MM`), Monday first.
 *
 * Always full rows of seven: the leading and trailing cells come from the
 * adjacent months, flagged `inMonth: false`. A short final row would make
 * the grid's last week a different width from the rest.
 */
export function monthMatrix(month: string): GridCell[][] {
  const [year, index] = month.split('-').map(Number);

  // Day 0 of the next month is the last day of this one -- the standard
  // trick, and the reason leap years need no special case here.
  const daysInMonth = new Date(year, index, 0).getDate();

  // getDay() is Sunday-0; the grid is Monday-first, so Sunday becomes 6.
  const firstWeekday = (new Date(year, index - 1, 1).getDay() + 6) % 7;

  const weeks: GridCell[][] = [];
  let week: GridCell[] = [];

  const push = (offset: number) => {
    // `new Date(year, index - 1, offset)` normalises out of range in both
    // directions, so offset 0 is the previous month's last day and
    // daysInMonth + 1 is the next month's first.
    const d = new Date(year, index - 1, offset);
    const cellMonth = d.getMonth() + 1;
    const weekday = d.getDay();
    week.push({
      date: iso(d.getFullYear(), cellMonth, d.getDate()),
      dayOfMonth: d.getDate(),
      inMonth: cellMonth === index && d.getFullYear() === year,
      weekend: weekday === 0 || weekday === 6,
    });
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  };

  for (let offset = 1 - firstWeekday; offset <= daysInMonth; offset += 1) push(offset);
  // Fill the final row out to seven.
  for (let offset = daysInMonth + 1; week.length > 0; offset += 1) push(offset);

  return weeks;
}

/** `"2026-08"` -> `"August 2026"`. */
export function monthLabel(month: string): string {
  const [year, index] = month.split('-').map(Number);
  return `${MONTH_NAMES[index - 1]} ${year}`;
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.helpers.spec.ts`
Expected: PASS — 8 passed

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.helpers.ts \
        frontend/src/app/workspaces/calendar/calendar.helpers.spec.ts
git commit -m "feat(v53): add month-grid date math for the calendar"
```

---

# Phase 4 — The calendar page

### Task 9: The month grid, metric toggle and filters

**Files:**
- Create: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts`

**Interfaces:**
- Consumes: `CalendarStore` (Task 7), `monthMatrix` / `monthLabel` (Task 8),
  `Panel` (`sb-panel`), `Select` (`sb-select`), `Button` (`sb-button`) from
  `frontend/src/app/ui/`, `money` / `rMultiple` / `ABSENT` from
  `frontend/src/app/ui/format.ts`.
- Produces: `export class Calendar` with selector `sb-calendar`, plus the
  protected members Tasks 10 and 11 extend.

- [x] **Step 1: Write the failing test**

Create `frontend/src/app/workspaces/calendar/calendar.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { PnlCalendar } from '../../api/models';
import { Calendar } from './calendar';

const RESPONSE: PnlCalendar = {
  month: '2026-08',
  days: [
    { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
    { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  ],
  totals: { net_pnl_amount: -60, net_r: -0.6, trade_count: 3, win_rate: 33.33 },
  day_of_week: [
    { weekday: 'Mon', avg_pnl_amount: 15, avg_r: 0.6, win_rate: 50, trade_count: 2 },
    { weekday: 'Tue', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Wed', avg_pnl_amount: -90, avg_r: -1.8, win_rate: 0, trade_count: 1 },
    { weekday: 'Thu', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
    { weekday: 'Fri', avg_pnl_amount: null, avg_r: null, win_rate: null, trade_count: 0 },
  ],
  best_day: { date: '2026-08-03', net_pnl_amount: 30, net_r: 1.2, trade_count: 2, win_rate: 50 },
  worst_day: { date: '2026-08-05', net_pnl_amount: -90, net_r: -1.8, trade_count: 1, win_rate: 0 },
  streak: { direction: 'losing', days: 1 },
  filters: { strategies: ['EMA20', 'VWAP'], horizons: ['3m', '4w'] },
};

/**
 * Stand the component up and pin it to August 2026.
 *
 * The store's first load asks for whatever month the machine clock is in,
 * so it is answered and then followed by an explicit `setMonth('2026-08')`.
 * Without that second step the grid geometry would be laid out for the
 * current month while `dayIndex` held August dates, and every
 * `[data-date]` lookup below would miss for reasons that have nothing to
 * do with the code under test.
 */
export function seed(payload: PnlCalendar = RESPONSE): ComponentFixture<Calendar> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(
        withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor]),
      ),
      provideHttpClientTesting(),
    ],
  });
  const fixture = TestBed.createComponent(Calendar);
  fixture.detectChanges();

  const backend = TestBed.inject(HttpTestingController);
  backend.expectOne((r) => r.url === '/api/v1/calendar/pnl').flush(payload);

  fixture.componentInstance.store.setMonth('2026-08');
  backend.expectOne((r) => r.params.get('month') === '2026-08').flush(payload);
  fixture.detectChanges();
  return fixture;
}

const el = (fixture: ComponentFixture<Calendar>) =>
  fixture.nativeElement as HTMLElement;

describe('Calendar grid', () => {
  it('renders full weeks of seven cells', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // August 2026 starts on a Saturday and runs 31 days, so the grid is six
    // rows: 5 leading cells + 31 + 6 trailing = 42.
    const rows = el(fixture).querySelectorAll('.week');
    expect(rows).toHaveLength(6);
    rows.forEach((row) => expect(row.querySelectorAll('.cell')).toHaveLength(7));
    // The first cell is the Monday before the 1st.
    expect(rows[0].querySelector('.cell')?.getAttribute('data-date')).toBe('2026-07-27');
  });

  it('shows money by default, not R', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const cell = el(fixture).querySelector('.cell[data-date="2026-08-03"] .value');
    expect(cell?.textContent).toContain('30');
    expect(cell?.textContent).not.toContain('R');
  });

  it('switches every cell to R when the metric toggles', async () => {
    const fixture = seed();
    await fixture.whenStable();

    fixture.componentInstance.store.setMetric('r');
    fixture.detectChanges();

    const cell = el(fixture).querySelector('.cell[data-date="2026-08-03"] .value');
    expect(cell?.textContent).toContain('R');
  });

  it('signs the cell class so colour follows the displayed number', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const win = el(fixture).querySelector('.cell[data-date="2026-08-03"]');
    const loss = el(fixture).querySelector('.cell[data-date="2026-08-05"]');
    expect(win?.classList.contains('pos')).toBe(true);
    expect(loss?.classList.contains('neg')).toBe(true);
  });

  it('renders weekend and no-trade cells as inert, and differently', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    // 2026-08-01 is a Saturday; 2026-08-04 is a Tuesday with no closes.
    const weekend = el(fixture).querySelector('.cell[data-date="2026-08-01"]');
    const quiet = el(fixture).querySelector('.cell[data-date="2026-08-04"]');
    expect(weekend?.classList.contains('weekend')).toBe(true);
    expect(weekend?.querySelector('button')).toBeNull();
    expect(quiet?.classList.contains('weekend')).toBe(false);
    expect(quiet?.classList.contains('pos')).toBe(false);
    expect(quiet?.classList.contains('neg')).toBe(false);
    // A quiet trading day is not clickable either -- there is nothing to open.
    expect(quiet?.querySelector('button')).toBeNull();
  });

  it('offers the strategy and horizon vocabularies from the payload', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.strategyOptions()).toEqual([
      { value: 'EMA20', label: 'EMA20' },
      { value: 'VWAP', label: 'VWAP' },
    ]);
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — `Cannot find module './calendar'`

- [x] **Step 3: Write minimal implementation**

Create `frontend/src/app/workspaces/calendar/calendar.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CalendarDay } from '../../api/models';
import { CalendarMetric, CalendarStore } from '../../stores/calendar.store';
import { Button } from '../../ui/button';
import { ABSENT, money, rMultiple } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Select } from '../../ui/form-controls';
import { GridCell, monthLabel, monthMatrix } from './calendar.helpers';

/** Monday-first, matching `monthMatrix` and the API's weekday breakdown. */
const WEEKDAY_HEADS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const METRICS: { value: CalendarMetric; label: string }[] = [
  { value: 'money', label: '$' },
  { value: 'r', label: 'R' },
];

@Component({
  selector: 'sb-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Panel, Select],
  // Provided on the component: created on entry, destroyed on exit, so the
  // workspace cannot hold a stale month while you are looking elsewhere.
  providers: [CalendarStore],
  template: `
    <header class="head">
      <h1>Calendar</h1>
      @if (store.error(); as message) {
        <span class="stale" role="status">{{ message }}</span>
      }
    </header>

    <div class="controls">
      <div class="months">
        <sb-button (click)="store.stepMonth(-1)" aria-label="Previous month">‹</sb-button>
        <span class="month">{{ label() }}</span>
        <sb-button (click)="store.stepMonth(1)" aria-label="Next month">›</sb-button>
      </div>

      <div class="metric" role="group" aria-label="Metric">
        @for (option of metrics; track option.value) {
          <button
            type="button"
            [class.active]="store.metric() === option.value"
            (click)="store.setMetric(option.value)"
          >
            {{ option.label }}
          </button>
        }
      </div>

      <sb-select
        label="Strategy"
        placeholder="Any strategy"
        [options]="store.strategyOptions()"
        [value]="store.strategy()"
        (valueChange)="store.setStrategy($event)"
      />
      <sb-select
        label="Horizon"
        placeholder="Any horizon"
        [options]="store.horizonOptions()"
        [value]="store.horizon()"
        (valueChange)="store.setHorizon($event)"
      />
    </div>

    <sb-panel [flush]="true">
      <div class="grid" role="grid" [attr.aria-label]="label()">
        <!-- NOT class="week": the grid tests assert every `.week` holds
             exactly 7 `.cell` children, and a header row sharing that class
             would contribute a row of zero. -->
        <div class="weekhead" role="row">
          @for (head of weekdayHeads; track head) {
            <div class="head-cell" role="columnheader">{{ head }}</div>
          }
        </div>
        @for (week of weeks(); track week[0].date) {
          <div class="week" role="row">
            @for (cell of week; track cell.date) {
              <div
                class="cell"
                role="gridcell"
                [attr.data-date]="cell.date"
                [class.outside]="!cell.inMonth"
                [class.weekend]="cell.weekend"
                [class.pos]="intensity(cell) > 0"
                [class.neg]="intensity(cell) < 0"
                [style.--heat]="magnitude(cell)"
              >
                <span class="dom">{{ cell.dayOfMonth }}</span>
                @if (dayFor(cell); as day) {
                  <button type="button" class="value" (click)="store.selectDay(day.date)">
                    {{ display(day) }}
                    <span class="n">{{ day.trade_count }}</span>
                  </button>
                }
              </div>
            }
          </div>
        }
      </div>
    </sb-panel>
  `,
  styles: `
    /* No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }
    .head { display: flex; align-items: baseline; gap: var(--space-14); }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .stale { color: var(--warn); font-size: var(--text-table); }

    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: var(--space-14);
    }
    .months { display: flex; align-items: center; gap: var(--space-8); }
    .month { min-width: 10ch; font-weight: 600; }

    .metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); }
    .metric button {
      height: var(--control-h);
      padding: 0 var(--space-10);
      background: none;
      border: 0;
      color: var(--text-secondary);
      font: inherit;
      cursor: pointer;
    }
    .metric button.active { background: var(--surface-raised); color: var(--text); }

    .grid { display: grid; }
    .week, .weekhead { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
    .head-cell {
      padding: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      letter-spacing: 0.1em;
      text-align: center;
      text-transform: uppercase;
    }
    .cell {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      min-height: 4.5rem;
      padding: var(--space-6);
      border-top: 1px solid var(--border);
      border-left: 1px solid var(--border);
    }
    .week .cell:last-child { border-right: 1px solid var(--border); }
    .dom { color: var(--text-secondary); font-size: var(--text-micro); }
    .outside .dom { color: var(--text-faint); }

    /* Weekends carry no closes, ever. Hatching them says "not a trading day"
       rather than "a trading day that happened to be quiet" -- the same
       distinction the payload makes by omitting empty days. */
    .weekend { background: var(--surface-sunken, transparent); }
    .weekend .dom { color: var(--text-faint); }

    /* Signed ramp off --heat (0..1), the same [style.--heat] + color-mix
       mechanism the Analytics win-rate heatmap uses. Green/red are reserved
       for P&L direction, which is exactly what this grid shows. */
    .cell.pos { background: color-mix(in srgb, var(--pos) calc(var(--heat, 0) * 55%), transparent); }
    .cell.neg { background: color-mix(in srgb, var(--neg) calc(var(--heat, 0) * 55%), transparent); }

    .value {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-6);
      padding: 0;
      background: none;
      border: 0;
      color: var(--text);
      font: inherit;
      font-family: var(--font-mono);
      font-size: var(--text-table);
      cursor: pointer;
      text-align: left;
    }
    .value:hover { text-decoration: underline; }
    .value:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    .n { color: var(--text-secondary); font-size: var(--text-micro); }
  `,
})
export class Calendar {
  readonly store = inject(CalendarStore);

  protected readonly weekdayHeads = WEEKDAY_HEADS;
  protected readonly metrics = METRICS;

  protected readonly label = computed(() => monthLabel(this.store.month()));
  protected readonly weeks = computed<GridCell[][]>(() =>
    monthMatrix(this.store.month()),
  );

  /** The day behind a cell, or null. Cells outside the month and weekends
   *  never resolve: a close cannot land on either, so offering a click
   *  target would promise a drawer that must come back empty. */
  protected dayFor(cell: GridCell): CalendarDay | null {
    if (!cell.inMonth || cell.weekend) return null;
    return this.store.dayIndex().get(cell.date) ?? null;
  }

  /** −1..+1 for the cell's day, 0 for a cell with no day. */
  protected intensity(cell: GridCell): number {
    const day = this.dayFor(cell);
    return day ? this.store.signedIntensity(day) : 0;
  }

  /** The 0..1 the CSS ramp consumes; sign is carried by the class instead. */
  protected magnitude(cell: GridCell): number {
    return Math.abs(this.intensity(cell));
  }

  /** The cell's number, formatted for the metric on show. */
  protected display(day: CalendarDay): string {
    if (this.store.metric() === 'r') return rMultiple(day.net_r);
    return day.net_pnl_amount === null ? ABSENT : money(day.net_pnl_amount, '$', 0);
  }
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS — 6 passed

Note on the `sb-select` binding: `value` is declared `model<string>('')`
(`frontend/src/app/ui/form-controls.ts:68`), and a `model()` generates a
matching `valueChange` output. So `[value]` + `(valueChange)` is the correct
form here — `[(value)]="…"` would need a writable target and cannot call a
store method.

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts \
        frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v53): render the month P&L grid with a money/R toggle"
```

---

### Task 10: The summary strip

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts` (template,
  styles and members)
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (append)

**Interfaces:**
- Consumes: `store.totals()`, `store.weekdays()`, `store.bestDay()`,
  `store.worstDay()`, `store.streak()` (Task 7); `MetricCard`
  (`sb-metric-card`) from `frontend/src/app/ui/metric-card.ts`.
- Produces: `streakLabel()`, `weekdayValue(weekday)`, `extremeLabel(day)`
  on `Calendar`.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/workspaces/calendar/calendar.spec.ts`:

```ts
describe('Calendar summary strip', () => {
  it("shows the visible month's pooled totals", async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const strip = el(fixture).querySelector('.totals');
    expect(strip?.textContent).toContain('60');   // net -60
    expect(strip?.textContent).toContain('3');    // 3 trades
    expect(strip?.textContent).toContain('33');   // 33.33% WR
  });

  it('lists all five weekdays even where there is no data', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const rows = el(fixture).querySelectorAll('.dow-row');
    expect(rows).toHaveLength(5);
    expect(rows[0].textContent).toContain('Mon');
    // Tuesday has n=0 and must read as absent, never as 0.00.
    expect(rows[1].textContent).toContain('—');
  });

  it('reports best day, worst day and the current streak', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    const callouts = el(fixture).querySelector('.callouts');
    expect(callouts?.textContent).toContain('2026-08-03');
    expect(callouts?.textContent).toContain('2026-08-05');
    expect(callouts?.textContent).toContain('losing');
    expect(callouts?.textContent).toContain('1');
  });

  it('says so plainly when there is no streak at all', async () => {
    const fixture = seed({
      ...RESPONSE,
      streak: { direction: null, days: 0 },
      best_day: null,
      worst_day: null,
    });
    await fixture.whenStable();
    fixture.detectChanges();

    const callouts = el(fixture).querySelector('.callouts');
    expect(callouts?.textContent).toContain('—');
  });

  it('switches the weekday table to R with the metric toggle', async () => {
    const fixture = seed();
    await fixture.whenStable();

    fixture.componentInstance.store.setMetric('r');
    fixture.detectChanges();

    const monday = el(fixture).querySelectorAll('.dow-row')[0];
    expect(monday.textContent).toContain('R');
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — the four new tests get `null` from
`querySelector('.totals')` / `.callouts` and `0` rows for `.dow-row`.

- [x] **Step 3: Write minimal implementation**

In `frontend/src/app/workspaces/calendar/calendar.ts`, add `MetricCard` to
the `imports` array and its import line:

```ts
import { MetricCard } from '../../ui/metric-card';
```

Insert this block into the template, between the `.controls` div and the
`<sb-panel [flush]="true">` that holds the grid:

```html
    <div class="totals">
      <sb-metric-card
        label="Net this month"
        [value]="store.metric() === 'r' ? (store.totals()?.net_r ?? null) : (store.totals()?.net_pnl_amount ?? null)"
        [unit]="store.metric() === 'r' ? 'R' : '$'"
        [tone]="totalsTone()"
      />
      <sb-metric-card label="Trades" [value]="store.totals()?.trade_count ?? null" [decimals]="0" />
      <sb-metric-card label="Win rate" [value]="store.totals()?.win_rate ?? null" unit="%" [decimals]="1" />
    </div>

    <div class="callouts">
      <sb-panel heading="Best day">
        <p class="callout">{{ extremeLabel(store.bestDay()) }}</p>
      </sb-panel>
      <sb-panel heading="Worst day">
        <p class="callout">{{ extremeLabel(store.worstDay()) }}</p>
      </sb-panel>
      <sb-panel heading="Current streak">
        <p class="callout">{{ streakLabel() }}</p>
      </sb-panel>
    </div>
```

And this panel after the grid's `</sb-panel>`:

```html
    <sb-panel heading="By weekday (all history)">
      <table class="dow">
        <thead>
          <tr><th>Day</th><th class="num">Avg</th><th class="num">Win rate</th><th class="num">n</th></tr>
        </thead>
        <tbody>
          @for (weekday of store.weekdays(); track weekday.weekday) {
            <tr class="dow-row">
              <th scope="row">{{ weekday.weekday }}</th>
              <td class="num">{{ weekdayValue(weekday) }}</td>
              <td class="num">{{ weekdayWinRate(weekday) }}</td>
              <td class="num">{{ weekday.trade_count }}</td>
            </tr>
          }
        </tbody>
      </table>
    </sb-panel>
```

No `number` pipe and no `DecimalPipe` import: formatting goes through a
class method the way `format.ts` is used everywhere else in this repo, so a
null win rate renders as `—` rather than as `0%`.

Add to the styles:

```css
    .totals { display: flex; flex-wrap: wrap; gap: var(--space-14); }
    .callouts {
      display: grid;
      gap: var(--space-14);
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    }
    .callout { margin: 0; font-family: var(--font-mono); font-size: var(--text-table); }
    .dow { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .dow th, .dow td { padding: var(--space-6) var(--space-10); border-bottom: 1px solid var(--border); }
    .dow thead th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      text-align: left;
    }
    .dow .num { font-family: var(--font-mono); text-align: right; }
```

Add these members to the `Calendar` class:

```ts
  /** `plain` while there is nothing to colour, so a loading strip is not
   *  briefly green. */
  protected readonly totalsTone = computed(() => {
    const totals = this.store.totals();
    const value =
      this.store.metric() === 'r' ? totals?.net_r : totals?.net_pnl_amount;
    if (value === null || value === undefined) return 'plain' as const;
    return value >= 0 ? ('pos' as const) : ('neg' as const);
  });

  /** `"50%"`, or ABSENT at n=0 — never `"0%"`, which would read as a real
   *  all-losses weekday rather than as no data. */
  protected weekdayWinRate(weekday: CalendarWeekday): string {
    return weekday.win_rate === null ? ABSENT : `${weekday.win_rate.toFixed(0)}%`;
  }

  /** A weekday's average, in the metric on show. */
  protected weekdayValue(weekday: CalendarWeekday): string {
    if (this.store.metric() === 'r') return rMultiple(weekday.avg_r);
    return weekday.avg_pnl_amount === null
      ? ABSENT
      : money(weekday.avg_pnl_amount, '$', 2);
  }

  /** "2026-08-05 · -$90" — the date is the point, so it leads. */
  protected extremeLabel(day: CalendarDay | null): string {
    if (!day) return ABSENT;
    return `${day.date} · ${this.display(day)}`;
  }

  /** "1 losing day", or ABSENT when there is no run to report. */
  protected streakLabel(): string {
    const streak = this.store.streak();
    if (!streak || streak.direction === null || streak.days === 0) return ABSENT;
    const unit = streak.days === 1 ? 'day' : 'days';
    return `${streak.days} ${streak.direction} ${unit}`;
  }
```

Import `CalendarWeekday` alongside `CalendarDay` from `../../api/models`.

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS — 11 passed

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts \
        frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v53): add month totals, weekday breakdown and streak callouts"
```

---

### Task 11: The day drill-down drawer

**Files:**
- Modify: `frontend/src/app/workspaces/calendar/calendar.ts`
- Test: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (append)

**Interfaces:**
- Consumes: `store.selectedDay()`, `store.dayTrades()`, `store.dayLoading()`,
  `store.closeDay()` (Task 7); `Drawer` (`sb-drawer`) from
  `frontend/src/app/ui/layout.ts` — inputs `open`, `heading`, output `closed`.
- Produces: `tradeValue(trade)` on `Calendar`. No new exports.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/workspaces/calendar/calendar.spec.ts`:

Add `CalendarTrade` to the existing `../../api/models` import at the top of
the file rather than opening a second import statement mid-file:

```ts
const TRADE: CalendarTrade = {
  trade_id: 'a'.repeat(16),
  ticker: 'AAPL',
  strategy: 'EMA20',
  horizon: '4w',
  direction: 'bullish',
  day: '2026-08-03',
  closed_at: '2026-08-03T20:00:00+00:00',
  outcome: 'win',
  pnl_amount: 50,
  r_multiple: 2,
  mfe_r: 2.4,
  mae_r: -0.3,
  exit_efficiency: 83,
  tags: ['clean-exit'],
  auto_lesson: 'Held to target.',
};

describe('Calendar day drawer', () => {
  const openDay = async (fixture: ComponentFixture<Calendar>, trades: CalendarTrade[]) => {
    // `seed()` already pinned the month and flushed both grid requests.
    fixture.componentInstance.store.selectDay('2026-08-03');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ date: '2026-08-03', trades });
    await fixture.whenStable();
    fixture.detectChanges();
  };

  it('stays closed until a day is chosen', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el(fixture).querySelector('.day-row')).toBeNull();
  });

  it('lists every trade closed that day', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE, { ...TRADE, trade_id: 'b'.repeat(16), ticker: 'MSFT' }]);

    const rows = el(fixture).querySelectorAll('.day-row');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('AAPL');
    expect(rows[1].textContent).toContain('MSFT');
  });

  it('shows the journal half when the join found one', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);

    const row = el(fixture).querySelector('.day-row');
    expect(row?.textContent).toContain('Held to target.');
    expect(row?.textContent).toContain('clean-exit');
  });

  it('omits the journal half for an unjournaled trade rather than showing blanks', async () => {
    const fixture = seed();
    await openDay(fixture, [
      { ...TRADE, tags: [], auto_lesson: null, mfe_r: null, mae_r: null, exit_efficiency: null },
    ]);

    const row = el(fixture).querySelector('.day-row');
    expect(row?.textContent).toContain('AAPL');
    expect(row?.querySelector('.lesson')).toBeNull();
    expect(row?.querySelector('.tags')).toBeNull();
  });

  it('says so when a day comes back with nothing under the current filter', async () => {
    const fixture = seed();
    await openDay(fixture, []);

    expect(el(fixture).querySelector('.day-empty')).not.toBeNull();
    expect(el(fixture).querySelectorAll('.day-row')).toHaveLength(0);
  });

  it('clears the selection when the drawer is dismissed', async () => {
    const fixture = seed();
    await openDay(fixture, [TRADE]);

    fixture.componentInstance.store.closeDay();
    fixture.detectChanges();

    expect(fixture.componentInstance.store.selectedDay()).toBeNull();
    expect(el(fixture).querySelector('.day-row')).toBeNull();
  });
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: FAIL — the five new drawer tests find no `.day-row` /
`.day-empty` elements.

- [x] **Step 3: Write minimal implementation**

Add `Drawer` to the `imports` array and its import:

```ts
import { Drawer, Panel } from '../../ui/layout';
```

Append to the template, after the weekday panel:

```html
    <sb-drawer
      [open]="store.selectedDay() !== null"
      [heading]="store.selectedDay() ?? ''"
      (closed)="store.closeDay()"
    >
      @if (store.dayLoading()) {
        <p class="day-loading">Loading…</p>
      } @else if ((store.dayTrades() ?? []).length === 0) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else {
        @for (trade of store.dayTrades() ?? []; track trade.trade_id) {
          <article class="day-row">
            <header>
              <strong>{{ trade.ticker }}</strong>
              <span class="meta">{{ trade.strategy }} · {{ trade.horizon }}</span>
              <span class="amount" [class.pos]="(trade.pnl_amount ?? 0) >= 0"
                    [class.neg]="(trade.pnl_amount ?? 0) < 0">
                {{ tradeValue(trade) }}
              </span>
            </header>
            <p class="meta">
              {{ trade.outcome }} · {{ rLabel(trade.r_multiple) }}
              @if (trade.mfe_r !== null) { · MFE {{ rLabel(trade.mfe_r) }} }
              @if (trade.mae_r !== null) { · MAE {{ rLabel(trade.mae_r) }} }
            </p>
            @if (trade.auto_lesson; as lesson) {
              <p class="lesson">{{ lesson }}</p>
            }
            @if (trade.tags.length) {
              <p class="tags">
                @for (tag of trade.tags; track tag) {
                  <span class="tag">{{ tag }}</span>
                }
              </p>
            }
          </article>
        }
      }
    </sb-drawer>
```

Add to the styles:

```css
    .day-row { padding: var(--space-10) 0; border-bottom: 1px solid var(--border); }
    .day-row header { display: flex; align-items: baseline; gap: var(--space-8); }
    .day-row .amount { margin-left: auto; font-family: var(--font-mono); }
    .day-row .amount.pos { color: var(--pos); }
    .day-row .amount.neg { color: var(--neg); }
    .day-row .meta { margin: var(--space-4) 0 0; color: var(--text-secondary); font-size: var(--text-micro); }
    .lesson { margin: var(--space-6) 0 0; font-size: var(--text-table); }
    .tags { display: flex; flex-wrap: wrap; gap: var(--space-4); margin: var(--space-6) 0 0; }
    .tag {
      padding: 0 var(--space-6);
      background: var(--surface-raised);
      border-radius: var(--radius);
      color: var(--text-secondary);
      font-size: var(--text-micro);
    }
    .day-empty, .day-loading { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
```

Add these members:

```ts
  /** One trade's headline figure, in the metric on show — so the drawer
   *  and the cell that opened it never disagree about units. */
  protected tradeValue(trade: CalendarTrade): string {
    if (this.store.metric() === 'r') return rMultiple(trade.r_multiple);
    return trade.pnl_amount === null ? ABSENT : money(trade.pnl_amount, '$', 2);
  }

  protected rLabel(value: number | null): string {
    return rMultiple(value);
  }
```

Import `CalendarTrade` alongside the other model types.

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/app/workspaces/calendar/calendar.spec.ts`
Expected: PASS — 17 passed

- [x] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/calendar/calendar.ts \
        frontend/src/app/workspaces/calendar/calendar.spec.ts
git commit -m "feat(v53): open a day's closed trades in the calendar drawer"
```

---

# Phase 5 — Wiring

### Task 12: Route, nav entry and icon

**Files:**
- Modify: `frontend/src/app/app.routes.ts` (add the `calendar` route)
- Modify: `frontend/src/app/app.routes.spec.ts` (assert it)
- Modify: `frontend/src/app/ui/icon.ts:21-62` (`ICON_NAMES` + `PATHS`)
- Modify: `frontend/src/app/shell/shell.ts:65-73` (the `nav` array)

**Interfaces:**
- Consumes: `Calendar` from Task 9.
- Produces: the `/calendar` route and its sidebar entry. Nothing else
  consumes these.

- [x] **Step 1: Write the failing test**

Append to `frontend/src/app/app.routes.spec.ts` (match the file's existing
style — read it first; it already walks the `routes` table):

```ts
  it('serves the calendar workspace behind the auth guard', async () => {
    const route = routes.find((r) => r.path === 'calendar');
    expect(route).toBeDefined();
    expect(route?.canMatch).toEqual([authGuard]);

    // The lazy chunk must actually resolve to the component, not just exist.
    const loaded = await route!.loadComponent!();
    expect(loaded).toBeDefined();
  });
```

Append to `frontend/src/app/ui/icon.spec.ts`:

```ts
  it('has a path for the calendar icon', () => {
    expect(ICON_NAMES).toContain('calendar');
  });
```

Those two assertions are the whole test surface for this task. There is
deliberately **no** test that walks the sidebar's `nav` array: `nav` is a
protected field initializer (`shell.ts:65`), so it exists only on a
constructed instance, and standing up `Shell` drags in the router, the event
stream and the session store for a one-line array check. The typing already
carries it — `icon` is declared `IconName`, so a nav entry naming an icon
that does not exist fails the build rather than a test.

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/app.routes.spec.ts src/app/ui/icon.spec.ts`
Expected: FAIL — `expected undefined to be defined` for the route, and
`ICON_NAMES` does not contain `'calendar'`.

- [x] **Step 3: Write minimal implementation**

In `frontend/src/app/app.routes.ts`, add after the `analytics` route (the
IA's order is: what is true now, the entities, then the analysis — the
calendar is analysis):

```ts
  {
    path: 'calendar',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./workspaces/calendar/calendar').then((m) => m.Calendar),
  },
```

In `frontend/src/app/ui/icon.ts`, add `'calendar'` to `ICON_NAMES` and a
16×16 stroke path to `PATHS` (a grid outline plus a header bar, matching the
hand-authored 1.5px-stroke style of the others):

```ts
  calendar:
    'M2.5 3.5h11v10h-11z M2.5 6.5h11 M5.5 1.5v2 M10.5 1.5v2 M5.5 9.5h1 M9.5 9.5h1 M5.5 11.5h1 M9.5 11.5h1',
```

In `frontend/src/app/shell/shell.ts`, add the nav entry after Analytics:

```ts
    { path: '/calendar', label: 'Calendar', icon: 'calendar' },
```

Update that array's doc comment — it says "The six workspaces"; it is now
seven plus Versions. Say what is actually there rather than leaving a
comment that miscounts.

- [x] **Step 4: Run the frontend suite to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — all suites green, including the new
`calendar.spec.ts`, `calendar.helpers.spec.ts` and `calendar.store.spec.ts`.

- [x] **Step 5: Run the full backend gate**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. The pass count rises from the 1686
baseline by the 21 core + 15 route tests this plan adds. A *changed* count
is not a failure — only `failed` is.

- [x] **Step 6: Commit**

```bash
git add frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts \
        frontend/src/app/ui/icon.ts frontend/src/app/ui/icon.spec.ts \
        frontend/src/app/shell/shell.ts
git commit -m "feat(v53): route and navigate to the calendar workspace"
```

- [x] **Step 7: Close out the plan**

This is the last task of the last part, so follow the **Close-out** section
in `2026-08-22-v53-pnl-calendar_0-index.md` — it covers moving all three
parts plus the spec into `implemented/`, and the version bump and
`version_history.json` regeneration that must follow it. Do not close out
from here alone: parts `_0-index` and `_1-backend` move in the same commit.

---
