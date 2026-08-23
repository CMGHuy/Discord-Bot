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
    /** True until the first response and never again -- a skeleton once. */
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
     *  metric -- the denominator that makes the colour ramp relative to the
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
                  ? 'The admin is not responding -- these figures may be stale.'
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

      /** Metric is a pure view concern -- no refetch. The payload already
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

      /** -1..+1. Sign picks the colour, magnitude picks the intensity, and
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
      //
      // `load()` is called through `untracked` because it READS month,
      // strategy and horizon. Without it those reads register as
      // dependencies of this effect, and every setStrategy/setMonth issues
      // two requests: the explicit `load()` in the method, plus the effect
      // re-running because the state it happened to read has changed.
      const trades = events.changes('trades');
      effect(() => {
        trades();
        untracked(() => store.load());
      });
    },
  }),
);
